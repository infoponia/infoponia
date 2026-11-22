# Pruebas de CMP-CNS-IIN · Consultar Existencias de Insumos (docs/casos_de_uso/inventario/insumo_invernadero.md; INV-02, paso 3).
#
# Servicios que se prueban (inventario/servicios/insumos_invernadero.py), tomados del módulo dentro de cada prueba:
#   consultar_existencias(actor, invernadero_id=None, categoria_id=None, con_vencimientos=False, bajo_minimo=False, hoy=None)
#       -> list[FilaDeExistencia]
#     Cada fila: ``iin`` (el InsumoInvernadero con su insumo, categoría e invernadero), ``stock`` (el ``Existencia`` de stock.py),
#     ``lotes`` (lista de ``LoteConEstado(lote, estado)`` con estado «vencido», «por_vencer», «al_dia», «sin_vencimiento», «agotado» o
#     «faltante»), ``vencido`` y ``por_vencer`` (cantidades en esos estados) y ``marca`` («stock_negativo», «no_cubre_reservas» o None).
#     - Precondición a: Agrónomo activo; el Gerente no consulta existencias (regla 1: PermissionDenied).
#     - Regla 1: los insumos habilitados (activos) de los invernaderos ACTIVOS a su cargo. Regla 2: filtros por invernadero (uno ajeno da
#       PermissionDenied), categoría, «con vencimientos» (vencidos o por vencer) y «bajo el mínimo».
#     - Regla 3: stock libre sobre total, reservado, tránsito, mínimo y «bajo el mínimo», estado del vencimiento y marcas. Regla 4: los
#       lotes con ingreso, disponible sobre ingresado, vencimiento y estado. Regla 6: no audita (SEG-14). Sin consultas por fila.
#   habilitados(invernadero_id) -> list[InsumoInvernadero]: los activos de un invernadero activo (para listas de elección).

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    faltante,
    insumo,
    lote,
    perezoso,
    reservas_de_prueba,
    tipo_de_insumo,
)
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

iin_servicio = perezoso("inventario.servicios.insumos_invernadero")
HOY = date(2026, 12, 10)


class CmpCnsIinServicioTests(ConDatosDeInventario, TestCase):
    """Reglas de CMP-CNS-IIN."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Gómez")
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.nutrientes = tipo_de_insumo("Nutrientes")
        self.envases = tipo_de_insumo("Envasado")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.agronomo)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.agronomo)
        self.nutriente = insumo("Nutriente A", tipo=self.nutrientes, unidad="l", controla_vencimiento=True)
        self.bolsas = insumo("Bolsas", tipo=self.envases, unidad="unidad")

    def consultar(self, actor=None, **filtros):
        return iin_servicio.consultar_existencias(actor or self.agronomo, hoy=HOY, **filtros)

    def ids(self, filas):
        return [f.iin.pk for f in filas]

    # ---- precondición y regla 1 ----

    def test_regla_1_el_gerente_y_los_demas_roles_no_consultan_existencias(self):
        """Regla 1: el Gerente no consulta existencias; tampoco los otros roles."""
        for actor in (crear_gerente(), crear_capataz(), crear_administrador()):
            with self.subTest(actor=actor.email), self.assertRaises(PermissionDenied):
                self.consultar(actor)

    def test_regla_1_solo_los_invernaderos_activos_a_cargo_del_agronomo(self):
        """Regla 1: no ve los de otro Agrónomo ni los invernaderos inactivos."""
        mio = existencia(self.nutriente, self.norte)
        ajeno = existencia(self.nutriente, crear_invernadero("Ajeno", agronomo=self.otro))
        viejo = crear_invernadero("Viejo", activo=False, agronomo=self.agronomo)
        en_viejo = existencia(self.bolsas, viejo)
        filas = self.ids(self.consultar())
        self.assertEqual(filas, [mio.pk])
        self.assertNotIn(ajeno.pk, filas)
        self.assertNotIn(en_viejo.pk, filas)

    def test_regla_1_los_insumos_deshabilitados_no_aparecen(self):
        """Regla 1: «insumos habilitados»."""
        activo = existencia(self.nutriente, self.norte)
        existencia(self.bolsas, self.norte, activo=False)
        self.assertEqual(self.ids(self.consultar()), [activo.pk])

    def test_regla_1_se_ordena_por_invernadero_y_por_nombre_de_insumo(self):
        """Orden estable de la pantalla."""
        a = existencia(self.nutriente, self.sur)
        b = existencia(self.bolsas, self.sur)
        c = existencia(self.nutriente, self.norte)
        self.assertEqual(self.ids(self.consultar()), [c.pk, b.pk, a.pk])

    # ---- regla 2: filtros ----

    def test_regla_2_filtra_por_invernadero(self):
        """Regla 2: por invernadero."""
        norte = existencia(self.nutriente, self.norte)
        existencia(self.nutriente, self.sur)
        self.assertEqual(self.ids(self.consultar(invernadero_id=self.norte.pk)), [norte.pk])

    def test_regla_2_filtrar_por_un_invernadero_ajeno_da_permiso_denegado(self):
        """D-28: un invernadero fuera del alcance da 403, no una lista vacía."""
        ajeno = crear_invernadero("Ajeno", agronomo=self.otro)
        with self.assertRaises(PermissionDenied):
            self.consultar(invernadero_id=ajeno.pk)

    def test_regla_2_filtra_por_categoria(self):
        """Regla 2: por categoría del insumo."""
        existencia(self.nutriente, self.norte)
        bolsas = existencia(self.bolsas, self.norte)
        self.assertEqual(self.ids(self.consultar(categoria_id=self.envases.pk)), [bolsas.pk])

    def test_regla_2_con_vencimientos_deja_los_que_tienen_lotes_vencidos_o_por_vencer(self):
        """Regla 2: «con vencimientos» = vencidos o por vencer; uno al día queda afuera."""
        vencido = existencia(self.nutriente, self.norte)
        lote(vencido, 5, vence=HOY - timedelta(days=1))
        por_vencer = existencia(self.nutriente, self.sur)
        lote(por_vencer, 5, vence=HOY + timedelta(days=3))
        al_dia = existencia(insumo("Fertilizante", tipo=self.nutrientes, unidad="kg", controla_vencimiento=True), self.norte)
        lote(al_dia, 5, vence=HOY + timedelta(days=200))
        self.assertEqual(set(self.ids(self.consultar(con_vencimientos=True))), {vencido.pk, por_vencer.pk})

    def test_regla_2_bajo_el_minimo_deja_solo_los_que_estan_bajo_el_minimo(self):
        """Regla 2: «bajo el mínimo»."""
        bajo = existencia(self.nutriente, self.norte, minimo=20)
        lote(bajo, 5)
        bien = existencia(self.bolsas, self.norte, minimo=2)
        lote(bien, 50)
        self.assertEqual(self.ids(self.consultar(bajo_minimo=True)), [bajo.pk])

    # ---- regla 3: qué se ve de cada insumo ----

    def test_regla_3_muestra_stock_libre_total_reservado_transito_y_minimo(self):
        """Regla 3: el stock libre sobre el total, lo reservado, lo que está en tránsito y el mínimo."""
        iin = existencia(self.nutriente, self.norte, minimo=20, transito="6")
        lote(iin, 30, vence=HOY + timedelta(days=90))
        with reservas_de_prueba(reservado={iin.pk: "10"}):
            fila = self.consultar()[0]
        s = fila.stock
        self.assertEqual((s.libre, s.actual, s.reservado, s.transito, s.minimo), (Decimal("20"), Decimal("30"), Decimal("10"), Decimal("6"), Decimal("20")))
        self.assertFalse(s.bajo_minimo)

    def test_regla_3_marca_bajo_el_minimo(self):
        """Regla 3: marca «bajo el mínimo»."""
        iin = existencia(self.nutriente, self.norte, minimo=20)
        lote(iin, 5)
        self.assertTrue(self.consultar()[0].stock.bajo_minimo)

    def test_regla_3_marca_stock_negativo(self):
        """Regla 3: «stock negativo» cuando hay faltante sin lote."""
        iin = existencia(self.nutriente, self.norte)
        faltante(iin, 3)
        fila = self.consultar()[0]
        self.assertEqual(fila.marca, "stock_negativo")

    def test_regla_3_marca_no_cubre_las_reservas(self):
        """Regla 3: «no cubre las reservas» cuando el stock vigente no alcanza y no es negativo."""
        iin = existencia(self.nutriente, self.norte)
        lote(iin, 4, vence=HOY + timedelta(days=90))
        with reservas_de_prueba(reservado={iin.pk: "9"}):
            self.assertEqual(self.consultar()[0].marca, "no_cubre_reservas")

    def test_regla_3_sin_problemas_no_hay_marca(self):
        """Sin inconsistencia la marca es None."""
        iin = existencia(self.nutriente, self.norte)
        lote(iin, 4, vence=HOY + timedelta(days=90))
        self.assertIsNone(self.consultar()[0].marca)

    def test_regla_3_resume_lo_vencido_y_lo_que_esta_por_vencer(self):
        """Regla 3: estado del vencimiento: cantidad vencida y cantidad por vencer (15 días por defecto, MD-89)."""
        iin = existencia(self.nutriente, self.norte)
        lote(iin, 5, vence=HOY - timedelta(days=2))
        lote(iin, 7, vence=HOY + timedelta(days=15))
        lote(iin, 11, vence=HOY + timedelta(days=16))
        fila = self.consultar()[0]
        self.assertEqual((fila.vencido, fila.por_vencer), (Decimal("5"), Decimal("7")))

    # ---- regla 4: los lotes ----

    def test_regla_4_cada_fila_trae_sus_lotes_con_su_estado(self):
        """Regla 4: ingreso, disponible sobre ingresado, vencimiento y estado de cada lote."""
        iin = existencia(self.nutriente, self.norte)
        vencido = lote(iin, 5, vence=HOY - timedelta(days=1))
        hoy_mismo = lote(iin, 5, vence=HOY)
        por_vencer = lote(iin, 5, vence=HOY + timedelta(days=15))
        al_dia = lote(iin, 5, vence=HOY + timedelta(days=16))
        agotado = lote(iin, 0, vence=HOY + timedelta(days=40), ingresada=5)
        falta = faltante(iin, 2)
        estados = {l.lote.pk: l.estado for l in self.consultar()[0].lotes}
        self.assertEqual(
            estados,
            {
                vencido.pk: "vencido",
                hoy_mismo.pk: "por_vencer",  # el día del vencimiento todavía se puede usar (regla 4 de CMP-REV-VNC)
                por_vencer.pk: "por_vencer",
                al_dia.pk: "al_dia",
                agotado.pk: "agotado",
                falta.pk: "faltante",
            },
        )

    def test_regla_4_un_lote_de_un_insumo_que_no_vence_es_sin_vencimiento(self):
        """Regla 4: sin fecha de vencimiento."""
        iin = existencia(self.bolsas, self.norte)
        l = lote(iin, 5)
        self.assertEqual([x.estado for x in self.consultar()[0].lotes], ["sin_vencimiento"])
        self.assertEqual(self.consultar()[0].lotes[0].lote.pk, l.pk)

    # ---- acciones, habilitados, auditoría y consultas ----

    def test_regla_5_las_acciones_de_cada_fila_son_las_del_agronomo_a_cargo(self):
        """Regla 5: desde cada fila se inicia modificar, deshabilitar o ajustar (D-30: ningún botón lleva a un 403)."""
        iin = existencia(self.nutriente, self.norte)
        self.assertEqual(iin_servicio.acciones_permitidas(self.agronomo, iin), frozenset({"modificar", "deshabilitar", "ajustar"}))
        self.assertEqual(iin_servicio.acciones_permitidas(self.otro, iin), frozenset())

    def test_habilitados_lista_los_activos_de_un_invernadero_activo_por_nombre(self):
        """docs/api/stock.md: ``habilitados(invernadero_id)`` para listas de elección."""
        b = existencia(self.bolsas, self.norte)
        a = existencia(self.nutriente, self.norte)
        existencia(insumo("Zeta", tipo=self.envases), self.norte, activo=False)
        self.assertEqual([i.pk for i in iin_servicio.habilitados(self.norte.pk)], [b.pk, a.pk])

    def test_habilitados_de_un_invernadero_inactivo_es_vacio(self):
        """Un invernadero inactivo no ofrece insumos."""
        viejo = crear_invernadero("Viejo", activo=False, agronomo=self.agronomo)
        existencia(self.bolsas, viejo)
        self.assertEqual(list(iin_servicio.habilitados(viejo.pk)), [])

    def test_regla_6_la_consulta_no_audita(self):
        """Regla 6 y SEG-14."""
        existencia(self.nutriente, self.norte)
        antes = RegistroAuditoria.objects.count()
        self.consultar()
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_la_cantidad_de_consultas_no_depende_de_la_cantidad_de_filas(self):
        """Nada de consultas por fila: la lista de 1 y la de 6 hacen las mismas."""
        uno = existencia(self.nutriente, self.norte)
        lote(uno, 5, vence=HOY + timedelta(days=3))
        with CaptureQueriesContext(connection) as con_una:
            self.consultar()
        for n in range(5):
            iin = existencia(insumo(f"Insumo {n}", tipo=self.nutrientes, unidad="l", controla_vencimiento=True), self.norte)
            lote(iin, 3, vence=HOY + timedelta(days=n))
            lote(iin, 2, vence=HOY - timedelta(days=1))
        with CaptureQueriesContext(connection) as con_seis:
            filas = self.consultar()
        self.assertEqual(len(filas), 6)
        self.assertEqual(len(con_seis), len(con_una))
