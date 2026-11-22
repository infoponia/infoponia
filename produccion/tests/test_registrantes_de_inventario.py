# Pruebas de lo que `produccion` registra en `inventario` desde `ProduccionConfig.ready()` (PRD-01, paso 4; docs/api/produccion.md,
# sección 3; docs/api/extensiones_de_inventario.md): las reservas de insumo, las órdenes que reservan y los tres puntos de
# variedades. Cada registrante lleva sus tres pruebas mínimas (con datos, neutro, sin consultas por fila) y hay una de punta a
# punta con la función pública de `inventario` y el registrante REAL. Las órdenes de entrega y mantenimiento son sueltas
# (`orden_suelta`, D-67 punto 1): sus reservas restan del stock libre aunque `produccion` no muestre esas órdenes.
# Cierra el disparador «Cuando exista PRD-01» punto 1 (pruebas de INV-03 con registrantes falsos → con los reales).

from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from inventario import extensiones
from inventario.servicios import stock, variedades
from inventario.tests.fabricas import ConDatosDeInventario
from inventario.tests.test_prod_mod_var import datos_de
from maestros.tests.fabricas import codigos_de, error_de
from produccion.models import Lote, OrdenTrabajo, ReservaInsumo
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo, orden_de_siembra, orden_suelta

Tipo = OrdenTrabajo.Tipo
D = Decimal


def consultas(llamada):
    """Cuántas consultas hace `llamada()`."""
    with CaptureQueriesContext(connection) as capturadas:
        llamada()
    return len(capturadas)


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.iin = cls.e.existencia_semilla.pk


class ReservasDeInsumoTests(Base):
    """`registrar_reservas_de_insumo`: lo reservado por las reservas ACTIVAS de cualquier tipo de orden."""

    def test_ext_con_datos_suma_las_reservas_activas_incluida_la_de_una_entrega_suelta(self):
        """Punto 4 de «Tipos futuros»: `reservado_de` suma las reservas «activas» de cualquier tipo de orden; las canceladas no."""
        orden_de_siembra(self.e, plantines=50)
        orden_de_siembra(self.e, plantines=9, sector="crecimiento", estado="cancelada")
        orden_suelta(self.e.invernadero, Tipo.ENTREGA, reservas=[(self.e.existencia_semilla, 5)])
        self.assertEqual(extensiones.reservado_de([self.iin]), {self.iin: D("55")})

    def test_ext_sin_datos_es_cero(self):
        """Neutro: sin reservas, 0."""
        self.assertEqual(extensiones.reservado_de([self.iin]), {self.iin: D("0")})

    def test_ext_no_hace_consultas_por_fila(self):
        """Una consulta para toda la lista de existencias."""
        orden_de_siembra(self.e, plantines=1)
        con_una = consultas(lambda: extensiones.reservado_de([self.iin]))
        for sector in ("crecimiento", "floracion"):
            orden_de_siembra(self.e, plantines=1, sector=sector)
        self.assertEqual(con_una, consultas(lambda: extensiones.reservado_de([self.iin])))

    def test_punta_a_punta_el_stock_libre_descuenta_la_reserva_activa_y_deja_de_hacerlo_al_cancelarla(self):
        """INV-02: el stock libre resta lo reservado (también de una entrega suelta) y el actual no cambia; al cancelar la reserva vuelve."""
        orden_de_siembra(self.e, plantines=50)
        entrega = orden_suelta(self.e.invernadero, Tipo.ENTREGA, reservas=[(self.e.existencia_semilla, 5)])
        existencia = stock.existencias([self.iin])[self.iin]
        self.assertEqual((existencia.actual, existencia.reservado, existencia.libre), (D("1000"), D("55"), D("945")))
        ReservaInsumo.objects.filter(orden=entrega).update(estado="cancelada")
        existencia = stock.existencias([self.iin])[self.iin]
        self.assertEqual((existencia.actual, existencia.reservado, existencia.libre), (D("1000"), D("50"), D("950")))


class OrdenesQueReservanTests(Base):
    """`registrar_ordenes_que_reservan`: las órdenes que tienen reservado el insumo."""

    def test_ext_con_datos_nombra_la_siembra_con_su_enlace_y_las_sueltas_sin_enlace(self):
        """Punto 4 de «Tipos futuros»: la siembra, con su enlace; una entrega suelta, «OT-NNNN · Entrega», y un mantenimiento,
        «OT-NNNN · Mantenimiento técnico», ambas con `url=None` (`produccion` no conoce esas pantallas, D-30)."""
        siembra = orden_de_siembra(self.e, plantines=50, dias=1)
        entrega = orden_suelta(self.e.invernadero, Tipo.ENTREGA, reservas=[(self.e.existencia_semilla, 5)])
        mantenimiento = orden_suelta(self.e.invernadero, Tipo.MANTENIMIENTO, reservas=[(self.e.existencia_semilla, 2)])
        ordenes = {o.orden_id: o for o in extensiones.ordenes_que_reservan([self.iin])[self.iin]}
        self.assertEqual(set(ordenes), {siembra.pk, entrega.pk, mantenimiento.pk})
        self.assertTrue(ordenes[siembra.pk].texto.startswith(siembra.codigo))
        self.assertTrue(ordenes[siembra.pk].url)
        self.assertEqual(ordenes[siembra.pk].cantidad, D("50"))
        self.assertEqual(ordenes[siembra.pk].fecha_programada, timezone.localdate() + timedelta(days=1))
        self.assertEqual((ordenes[entrega.pk].texto, ordenes[entrega.pk].url), (f"{entrega.codigo} · Entrega", None))
        self.assertEqual(
            (ordenes[mantenimiento.pk].texto, ordenes[mantenimiento.pk].url), (f"{mantenimiento.codigo} · Mantenimiento técnico", None)
        )

    def test_ext_una_reserva_cancelada_no_nombra_su_orden(self):
        """Solo las reservas activas."""
        orden_de_siembra(self.e, plantines=9, estado="cancelada")
        self.assertEqual(extensiones.ordenes_que_reservan([self.iin]), {self.iin: []})

    def test_ext_sin_datos_la_lista_esta_vacia(self):
        """Neutro."""
        self.assertEqual(extensiones.ordenes_que_reservan([self.iin]), {self.iin: []})

    def test_ext_no_hace_consultas_por_fila(self):
        """Una consulta para toda la lista de existencias."""
        orden_de_siembra(self.e, plantines=1)
        con_una = consultas(lambda: extensiones.ordenes_que_reservan([self.iin]))
        for _ in range(3):
            orden_suelta(self.e.invernadero, Tipo.ENTREGA, reservas=[(self.e.existencia_semilla, 1)])
        self.assertEqual(con_una, consultas(lambda: extensiones.ordenes_que_reservan([self.iin])))


class UsoDeVariedadTests(Base):
    """`registrar_uso_de_variedad`: lotes y órdenes de cada variedad."""

    def test_ext_con_datos_cuenta_lotes_activos_ordenes_a_realizar_e_invernaderos(self):
        """`con_lotes` (aunque esté terminado), `lotes_activos`, `ordenes_a_realizar` (siembras) e invernaderos con lotes activos."""
        lote_activo(self.e, cantidad=10)
        terminado = lote_activo(self.e, cantidad=5, costo="0.00")
        Lote.objects.filter(pk=terminado.pk).update(cantidad_actual=0, estado_lote="finalizado")
        orden_de_siembra(self.e, plantines=2)
        orden_de_siembra(self.e, plantines=2, estado="cancelada")
        uso = extensiones.uso_de_variedades([self.e.variedad.pk])[self.e.variedad.pk]
        self.assertEqual(
            (uso.con_lotes, uso.lotes_activos, uso.ordenes_a_realizar, uso.invernaderos_con_lotes_activos),
            (True, 1, 1, frozenset({self.e.invernadero.pk})),
        )

    def test_ext_sin_datos_es_el_neutro(self):
        """Neutro: `UsoDeVariedad(False, 0, 0, frozenset())`."""
        self.assertEqual(extensiones.uso_de_variedades([self.e.variedad.pk])[self.e.variedad.pk], extensiones.USO_NEUTRO)

    def test_ext_no_hace_consultas_por_fila(self):
        """La cantidad de consultas no crece con las variedades."""
        otra = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2")
        lote_activo(self.e, cantidad=1)
        lote_activo(otra, cantidad=1)
        uno = consultas(lambda: extensiones.uso_de_variedades([self.e.variedad.pk]))
        dos = consultas(lambda: extensiones.uso_de_variedades([self.e.variedad.pk, otra.variedad.pk]))
        self.assertEqual(uno, dos)


class VariedadesPresentesTests(Base):
    """`registrar_variedades_presentes`: las variedades de lotes activos y de siembras a realizar, por invernadero."""

    def test_ext_con_datos_cuenta_lotes_activos_y_siembras_a_realizar_pero_no_las_canceladas(self):
        """La misma definición del «umbral efectivo» de PROD-PNF-SMB."""
        orden_de_siembra(self.e, plantines=2)
        otra = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2")
        lote_activo(otra, cantidad=3)
        orden_de_siembra(otra, plantines=1, sector="crecimiento", estado="cancelada")
        presentes = extensiones.variedades_presentes([self.e.invernadero.pk, otra.invernadero.pk])
        self.assertEqual(presentes, {self.e.invernadero.pk: {self.e.variedad.pk}, otra.invernadero.pk: {otra.variedad.pk}})

    def test_ext_sin_datos_es_un_conjunto_vacio(self):
        """Neutro."""
        self.assertEqual(extensiones.variedades_presentes([self.e.invernadero.pk]), {self.e.invernadero.pk: set()})

    def test_ext_no_hace_consultas_por_fila(self):
        """Una consulta para todos los invernaderos."""
        otra = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2")
        uno = consultas(lambda: extensiones.variedades_presentes([self.e.invernadero.pk]))
        dos = consultas(lambda: extensiones.variedades_presentes([self.e.invernadero.pk, otra.invernadero.pk]))
        self.assertEqual(uno, dos)

    def test_punta_a_punta_umbral_efectivo_cuenta_el_lote_activo_y_la_siembra_a_realizar_y_deja_de_contar_la_cancelada(self):
        """PROD-PNF-SMB, nota «Umbral efectivo»: cuenta la variedad de un lote activo y la de una siembra a realizar, y deja de
        contar la de una siembra cancelada."""
        inv = self.e.invernadero.pk
        self.assertIsNone(variedades.umbral_efectivo([inv])[inv])
        siembra = orden_de_siembra(self.e, plantines=2)
        self.assertEqual(variedades.umbral_efectivo([inv])[inv].variedad_ids, frozenset({self.e.variedad.pk}))
        OrdenTrabajo.objects.filter(pk=siembra.pk).update(
            estado_orden="cancelada", fecha_resolucion_orden=timezone.localdate(), motivo_cancelacion="x"
        )
        self.assertIsNone(variedades.umbral_efectivo([inv])[inv])
        lote_activo(self.e, cantidad=3)
        self.assertEqual(variedades.umbral_efectivo([inv])[inv].variedad_ids, frozenset({self.e.variedad.pk}))


class ImpedimentosDeBajaDeVariedadTests(Base):
    """`registrar_impedimento_de_baja_de_variedad`: `lotes_activos` y `ordenes_a_realizar`."""

    def codigos(self):
        return [i.codigo for i in extensiones.impedimentos_de_baja_de_variedad(self.e.variedad)]

    def test_ext_con_datos_informa_cuantos_lotes_y_ordenes(self):
        """Regla 2 de PROD-BAJ-VAR: los textos dicen cuántos."""
        lote_activo(self.e, cantidad=10)
        orden_de_siembra(self.e, plantines=2)
        impedimentos = extensiones.impedimentos_de_baja_de_variedad(self.e.variedad)
        self.assertEqual([i.codigo for i in impedimentos], ["lotes_activos", "ordenes_a_realizar"])
        self.assertIn("1 lote", impedimentos[0].texto)
        self.assertIn("1 orden", impedimentos[1].texto)

    def test_ext_sin_datos_no_hay_impedimentos(self):
        """Neutro: sin lotes activos ni órdenes a realizar (una cancelada no cuenta)."""
        orden_de_siembra(self.e, plantines=2, estado="cancelada")
        self.assertEqual(self.codigos(), [])

    def test_ext_no_hace_consultas_por_fila(self):
        """La cantidad de consultas no crece con los lotes y las órdenes."""
        lote_activo(self.e, cantidad=1)
        con_uno = consultas(lambda: self.codigos())
        for _ in range(3):
            lote_activo(self.e, cantidad=1)
            orden_de_siembra(self.e, plantines=1)
        self.assertEqual(con_uno, consultas(lambda: self.codigos()))

    def test_punta_a_punta_baja_variedad_rechaza_una_variedad_con_lotes_y_con_ordenes(self):
        """PROD-BAJ-VAR: `baja_variedad` informa TODOS los impedimentos juntos y no cambia nada."""
        lote_activo(self.e, cantidad=10)
        orden_de_siembra(self.e, plantines=2)
        error = error_de(lambda: variedades.baja_variedad(self.e.agronomo, self.e.variedad.pk))
        self.assertEqual(sorted(codigos_de(error)), ["lotes_activos", "ordenes_a_realizar"])
        self.e.variedad.refresh_from_db()
        self.assertEqual(self.e.variedad.estado_variedad, "activo")

    def test_punta_a_punta_modificar_el_perfil_con_lotes_reales_se_rechaza(self):
        """Regla 4 de PROD-MOD-VAR (disparador «Cuando exista PRD-01», punto 1): con un lote activo no se cambia el perfil."""
        lote_activo(self.e, cantidad=10)
        error = error_de(
            lambda: variedades.modificar_variedad(self.e.agronomo, self.e.variedad.pk, datos_de(self.e.variedad, perfil_familia="hierbas"))
        )
        self.assertEqual(codigos_de(error, "perfil_familia"), ["perfil_con_lotes_u_ordenes"])
