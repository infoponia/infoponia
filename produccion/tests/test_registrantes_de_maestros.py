# Pruebas de lo que `produccion` registra en `maestros` desde `ProduccionConfig.ready()` (PRD-01, paso 4; docs/api/produccion.md,
# sección 3; docs/api/extensiones_de_maestros.md; docs/patrones/bloqueos.md). Cada registrante lleva sus tres pruebas mínimas (con
# datos, neutro sin datos, sin consultas por fila) y hay una de punta a punta por punto: se llama a la función pública de
# `maestros` con el registrante REAL, no con uno falso. Las órdenes de entrega y mantenimiento son sueltas (`orden_suelta`, D-67
# punto 1): la baja del invernadero las cuenta aunque `produccion` no las muestre.

from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros import extensiones
from maestros.servicios import invernaderos, sectores
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_capataz_activo, crear_sector, error_de, tipo_etapa
from maestros.tests.test_prod_mod_inv import datos_de
from produccion.models import Lote, OrdenTrabajo, ReservaInsumo, Siembra
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo, orden_de_siembra, orden_suelta

Tipo = OrdenTrabajo.Tipo


def consultas(llamada):
    """Cuántas consultas hace `llamada()`."""
    with CaptureQueriesContext(connection) as capturadas:
        llamada()
    return len(capturadas)


def codigos(impedimentos):
    """Los códigos de una lista de impedimentos."""
    return [i.codigo for i in impedimentos]


class BaseDeRegistrantes(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.germinacion = cls.e.sectores["germinacion"]


class AgujerosDeSectorTests(BaseDeRegistrantes):
    """`registrar_agujeros_de_sector`: `(ocupados, comprometidos)` derivados de las ocupaciones (D-50 punto 4)."""

    def test_ext_con_datos_ocupados_son_los_del_lote_y_comprometidos_los_de_las_ordenes_a_realizar(self):
        """Regla 4 de 8.13: comprometidos = planificados de las órdenes «a realizar»; ocupados = los del lote. Una orden cancelada no compromete."""
        lote_activo(self.e, cantidad=30)
        orden_de_siembra(self.e, plantines=10)
        orden_de_siembra(self.e, plantines=7, estado="cancelada")
        self.assertEqual(extensiones.agujeros_registrados([self.germinacion.pk]), {self.germinacion.pk: (30, 10)})

    def test_ext_sin_datos_es_cero_cero(self):
        """Neutro: un sector sin ocupaciones tiene (0, 0)."""
        self.assertEqual(extensiones.agujeros_registrados([self.germinacion.pk]), {self.germinacion.pk: (0, 0)})

    def test_ext_no_hace_consultas_por_fila(self):
        """Una consulta para toda la lista de sectores."""
        ids = [s.pk for s in self.e.sectores.values()]
        con_uno = consultas(lambda: extensiones.agujeros_registrados(ids[:1]))
        con_todos = consultas(lambda: extensiones.agujeros_registrados(ids))
        self.assertEqual(con_uno, con_todos)

    def test_punta_a_punta_agujeros_de_descuenta_ocupados_y_comprometidos_de_la_capacidad_libre(self):
        """`maestros.servicios.sectores.agujeros_de`: libres = total − ocupados − comprometidos."""
        lote_activo(self.e, cantidad=30)
        orden_de_siembra(self.e, plantines=10)
        agujeros = sectores.agujeros_de([self.germinacion])[self.germinacion.pk]
        self.assertEqual((agujeros.total, agujeros.ocupados, agujeros.comprometidos, agujeros.libres), (100, 30, 10, 60))


class ImpedimentosDeBajaDeSectorTests(BaseDeRegistrantes):
    """`registrar_impedimento_de_baja_de_sector`: `agujeros_ocupados` y `agujeros_comprometidos`, con los lotes y las órdenes."""

    def test_ext_con_datos_informa_los_lotes_que_ocupan_y_las_ordenes_que_comprometen(self):
        """Regla 2 de PROD-BAJ-SCT: informa los lotes que lo ocupan y las órdenes que lo tienen reservado, y ofrece ponerlo fuera de servicio."""
        lote = lote_activo(self.e, cantidad=30)
        orden = orden_de_siembra(self.e, plantines=10)
        impedimentos = extensiones.impedimentos_registrados_de_sector(self.germinacion)
        self.assertEqual(codigos(impedimentos), ["agujeros_ocupados", "agujeros_comprometidos"])
        self.assertIn(lote.codigo, impedimentos[0].texto)
        self.assertIn(orden.codigo, impedimentos[1].texto)
        for impedimento in impedimentos:
            self.assertIn("fuera de servicio", impedimento.como_resolver)

    def test_ext_sin_datos_no_hay_impedimentos(self):
        """Neutro: un sector vacío o con solo una orden cancelada no impide la baja."""
        orden_de_siembra(self.e, plantines=5, estado="cancelada")
        self.assertEqual(extensiones.impedimentos_registrados_de_sector(self.germinacion), [])

    def test_ext_no_hace_consultas_por_fila(self):
        """La cantidad de consultas no crece con los lotes y las órdenes del sector."""
        lote_activo(self.e, cantidad=5)
        con_uno = consultas(lambda: extensiones.impedimentos_registrados_de_sector(self.germinacion))
        for _ in range(3):
            lote_activo(self.e, cantidad=5)
            orden_de_siembra(self.e, plantines=1)
        self.assertEqual(con_uno, consultas(lambda: extensiones.impedimentos_registrados_de_sector(self.germinacion)))

    def test_punta_a_punta_baja_sector_rechaza_un_sector_con_lote_y_con_orden(self):
        """PROD-BAJ-SCT precondiciones d y e: `baja_sector` rechaza con los dos códigos y no cambia nada."""
        lote_activo(self.e, cantidad=30)
        orden_de_siembra(self.e, plantines=10)
        error = error_de(lambda: sectores.baja_sector(self.e.agronomo, self.germinacion.pk))
        self.assertEqual(sorted(set(codigos_de(error))), ["agujeros_comprometidos", "agujeros_ocupados"])
        self.germinacion.refresh_from_db()
        self.assertEqual(self.germinacion.estado_sector, "activo")


class ContenidoDeSectorTests(BaseDeRegistrantes):
    """`registrar_contenido_de_sector`: los lotes que lo ocupan y las órdenes «a realizar» que lo reservan (regla 3 de PROD-CNS-SCT)."""

    def test_ext_con_datos_lista_lotes_y_ordenes_con_su_cantidad_y_fecha(self):
        """Un `Contenido` de tipo «lote» (plantas en el sector) y uno de tipo «orden» (agujeros reservados y fecha programada)."""
        lote = lote_activo(self.e, cantidad=30)
        orden = orden_de_siembra(self.e, plantines=10, dias=2)
        orden_de_siembra(self.e, plantines=4, estado="cancelada")
        contenido = extensiones.contenido_registrado([self.germinacion])[self.germinacion.pk]
        self.assertEqual([c.tipo for c in contenido], ["lote", "orden"])
        self.assertIn(lote.codigo, contenido[0].texto)
        self.assertIn(str(self.e.variedad), contenido[0].texto)
        self.assertEqual(contenido[0].cantidad, 30)
        self.assertIn(orden.codigo, contenido[1].texto)
        self.assertEqual((contenido[1].cantidad, contenido[1].fecha), (10, timezone.localdate() + timedelta(days=2)))

    def test_ext_sin_datos_la_lista_esta_vacia(self):
        """Neutro: sin lotes ni órdenes, lista vacía para el sector."""
        self.assertEqual(extensiones.contenido_registrado([self.germinacion]), {self.germinacion.pk: []})

    def test_ext_no_hace_consultas_por_fila(self):
        """Una consulta por tabla para todos los sectores."""
        lote_activo(self.e, cantidad=5)
        todos = list(self.e.sectores.values())
        con_uno = consultas(lambda: extensiones.contenido_registrado(todos[:1]))
        self.assertEqual(con_uno, consultas(lambda: extensiones.contenido_registrado(todos)))


class PerfilDeSectorTests(BaseDeRegistrantes):
    """`registrar_perfil_de_sector`: el perfil familiar de lo que hay en el sector."""

    def test_ext_con_datos_es_el_de_la_variedad(self):
        """El de la variedad del lote que lo ocupa o de la orden «a realizar» que lo usa."""
        lote_activo(self.e, cantidad=10)
        orden_de_siembra(self.e, plantines=2, sector="crecimiento")
        perfiles = extensiones.perfiles_registrados([self.germinacion.pk, self.e.sectores["crecimiento"].pk])
        self.assertEqual(list(perfiles.values()), ["hoja_verde", "hoja_verde"])

    def test_ext_sin_datos_es_none(self):
        """Neutro: sin plantas, `None`."""
        self.assertEqual(extensiones.perfiles_registrados([self.germinacion.pk]), {self.germinacion.pk: None})

    def test_ext_no_hace_consultas_por_fila(self):
        """Una consulta para toda la lista."""
        ids = [s.pk for s in self.e.sectores.values()]
        self.assertEqual(consultas(lambda: extensiones.perfiles_registrados(ids[:1])), consultas(lambda: extensiones.perfiles_registrados(ids)))


class AvisoDeCambioDeTipoTests(BaseDeRegistrantes):
    """`registrar_aviso_de_cambio_de_tipo`: lotes que deben pasar por la etapa (con la fecha) y siembras a realizar."""

    def test_ext_con_datos_avisa_de_los_lotes_con_su_fecha_y_de_las_siembras(self):
        """Regla 4 de PROD-MOD-SCT: los lotes que todavía deben pasar por esa etapa, con la fecha en que la necesitan (el fin de su
        etapa actual), y las siembras a realizar afectadas."""
        lote = lote_activo(self.e, cantidad=10)
        orden = orden_de_siembra(self.e, plantines=2, sector="crecimiento")
        avisos = extensiones.avisos_registrados_de_cambio_de_tipo(self.e.invernadero, tipo_etapa("crecimiento"))
        self.assertEqual([a.cantidad for a in avisos], [1, 1])
        self.assertIn(lote.codigo, avisos[0].texto)
        self.assertIn((timezone.localdate() + timedelta(days=10)).strftime("%d/%m/%Y"), avisos[0].texto)
        self.assertIn(orden.codigo, avisos[1].texto)

    def test_ext_un_lote_que_ya_esta_en_la_etapa_no_la_necesita_de_nuevo(self):
        """Un lote en Germinación no «debe pasar» por Germinación; la siembra a realizar sí la usa."""
        lote_activo(self.e, cantidad=10)
        orden_de_siembra(self.e, plantines=2)
        avisos = extensiones.avisos_registrados_de_cambio_de_tipo(self.e.invernadero, tipo_etapa("germinacion"))
        self.assertEqual(len(avisos), 1)
        self.assertNotIn("L-", avisos[0].texto)

    def test_ext_sin_datos_no_avisa(self):
        """Neutro: sin lotes ni órdenes, ningún aviso."""
        self.assertEqual(extensiones.avisos_registrados_de_cambio_de_tipo(self.e.invernadero, tipo_etapa("crecimiento")), [])

    def test_ext_no_hace_consultas_por_fila(self):
        """La cantidad de consultas no crece con los lotes y las siembras."""
        lote_activo(self.e, cantidad=1)
        orden_de_siembra(self.e, plantines=1)
        etapa = tipo_etapa("crecimiento")
        con_uno = consultas(lambda: extensiones.avisos_registrados_de_cambio_de_tipo(self.e.invernadero, etapa))
        for _ in range(3):
            lote_activo(self.e, cantidad=1)
            orden_de_siembra(self.e, plantines=1)
        self.assertEqual(con_uno, consultas(lambda: extensiones.avisos_registrados_de_cambio_de_tipo(self.e.invernadero, etapa)))


class ImpedimentosDeBajaDelInvernaderoTests(BaseDeRegistrantes):
    """`registrar_impedimento_de_baja` (invernadero): `lotes_activos` y `ordenes_a_realizar` (de TODOS los tipos, D-64 punto 12)."""

    def codigos_de_produccion(self):
        """Los códigos que pone `produccion` (los demás registrantes, como el stock, ponen los suyos)."""
        return [c for c in codigos(extensiones.impedimentos_de_baja(self.e.invernadero)) if c in ("lotes_activos", "ordenes_a_realizar")]

    def test_ext_con_datos_un_lote_activo_y_una_orden_impiden_la_baja(self):
        """Precondiciones c y d de PROD-BAJ-INV: lotes activos y órdenes «a realizar» (los textos dicen cuántos)."""
        lote_activo(self.e, cantidad=10)
        orden_de_siembra(self.e, plantines=2)
        self.assertEqual(self.codigos_de_produccion(), ["lotes_activos", "ordenes_a_realizar"])

    def test_d64_solo_una_entrega_suelta_a_realizar_impide_la_baja(self):
        """Punto 5 de «Tipos futuros» (D-64 punto 12): el impedimento cuenta las órdenes «a realizar» de todos los tipos, no solo las que muestra `produccion`."""
        orden_suelta(self.e.invernadero, Tipo.ENTREGA)
        self.assertEqual(self.codigos_de_produccion(), ["ordenes_a_realizar"])

    def test_d64_solo_un_mantenimiento_suelto_a_realizar_impide_la_baja(self):
        """Punto 5 de «Tipos futuros»: lo mismo con un mantenimiento."""
        orden_suelta(self.e.invernadero, Tipo.MANTENIMIENTO)
        self.assertEqual(self.codigos_de_produccion(), ["ordenes_a_realizar"])

    def test_ext_sin_datos_o_canceladas_no_impide_la_baja(self):
        """Neutro: sin lotes activos ni órdenes «a realizar» (canceladas y concretadas no cuentan; un lote finalizado tampoco)."""
        orden_suelta(self.e.invernadero, Tipo.ENTREGA, estado="cancelada")
        orden_suelta(self.e.invernadero, Tipo.MANTENIMIENTO, estado="cancelada")
        terminado = lote_activo(self.e, cantidad=5, costo="0.00")
        Lote.objects.filter(pk=terminado.pk).update(cantidad_actual=0, estado_lote="finalizado")
        self.assertEqual(self.codigos_de_produccion(), [])

    def test_ext_no_hace_consultas_por_fila(self):
        """La cantidad de consultas de `produccion` no crece con los lotes y las órdenes."""
        orden_suelta(self.e.invernadero, Tipo.ENTREGA)
        con_una = consultas(lambda: extensiones.impedimentos_de_baja(self.e.invernadero))
        for _ in range(3):
            orden_suelta(self.e.invernadero, Tipo.MANTENIMIENTO)
            lote_activo(self.e, cantidad=1)
        con_varias = consultas(lambda: extensiones.impedimentos_de_baja(self.e.invernadero))
        self.assertEqual(con_una, con_varias)

    def test_punta_a_punta_baja_invernadero_se_rechaza_con_solo_una_entrega_suelta_y_se_acepta_si_esta_cancelada(self):
        """PROD-BAJ-INV (punto 5): rechazada con `ordenes_a_realizar`; con la entrega cancelada, el impedimento de `produccion` desaparece."""
        entrega = orden_suelta(self.e.invernadero, Tipo.ENTREGA)
        error = error_de(lambda: invernaderos.baja_invernadero(crear_gerente(), self.e.invernadero.pk))
        self.assertIn("ordenes_a_realizar", codigos_de(error))
        OrdenTrabajo.objects.filter(pk=entrega.pk).update(
            estado_orden="cancelada", fecha_resolucion_orden=timezone.localdate(), motivo_cancelacion="x"
        )
        self.assertEqual(self.codigos_de_produccion(), [])


class TraspasoDeOrdenesTests(BaseDeRegistrantes):
    """`registrar_traspaso` (rol Capataz): las órdenes «a realizar» del invernadero pasan al Capataz nuevo (regla 3 de 8.22, D-53)."""

    def setUp(self):
        self.nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")

    def test_ext_contar_informa_las_ordenes_a_realizar_del_saliente(self):
        """`contar` alimenta el aviso de la regla 2 y la notificación de la postcondición c de PROD-MOD-INV."""
        orden_de_siembra(self.e, plantines=1)
        orden_de_siembra(self.e, plantines=1, sector="crecimiento")
        orden_de_siembra(self.e, plantines=1, sector="floracion", estado="cancelada")
        recibe = extensiones.contar_traspaso(self.e.invernadero, "capataz", self.e.capataz, self.nuevo)
        self.assertEqual(recibe, [("órdenes de trabajo a realizar", 2)])

    def test_ext_contar_neutro_si_no_es_el_rol_capataz_o_no_hay_entrante_o_no_hay_ordenes(self):
        """Neutro: otro rol, sin persona entrante o sin órdenes, nada."""
        orden_de_siembra(self.e, plantines=1)
        self.assertEqual(extensiones.contar_traspaso(self.e.invernadero, "agronomo", self.e.agronomo, crear_agronomo("a2@infoponia.com")), [])
        self.assertEqual(extensiones.contar_traspaso(self.e.invernadero, "capataz", self.e.capataz, None), [])
        OrdenTrabajo.objects.all().update(estado_orden="concretada", fecha_resolucion_orden=timezone.localdate())
        self.assertEqual(extensiones.contar_traspaso(self.e.invernadero, "capataz", self.e.capataz, self.nuevo), [])

    def test_ext_traspasar_pasa_solo_las_a_realizar_de_ese_invernadero_y_devuelve_lo_que_toco(self):
        """D-53: actualiza `capataz` en cada hija. Las concretadas y las canceladas no cambian; las de otro invernadero, tampoco."""
        pendiente = orden_de_siembra(self.e, plantines=1)
        cancelada = orden_de_siembra(self.e, plantines=1, sector="crecimiento", estado="cancelada")
        otro = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2")
        de_otro = orden_de_siembra(otro, plantines=1)
        afectados = extensiones.traspasar(self.e.agronomo, self.e.invernadero, "capataz", self.e.capataz, self.nuevo)
        self.assertEqual([a.pk for a in afectados], [pendiente.pk])
        self.assertEqual(Siembra.objects.get(pk=pendiente.pk).capataz, self.nuevo)
        self.assertEqual(Siembra.objects.get(pk=cancelada.pk).capataz, self.e.capataz)
        self.assertEqual(Siembra.objects.get(pk=de_otro.pk).capataz, otro.capataz)

    def test_ext_traspasar_si_el_rol_estaba_vacio_pasan_a_quien_se_asigna_despues(self):
        """MD-60: con `saliente=None` (el rol había quedado vacío), las órdenes «a realizar» del invernadero pasan al entrante."""
        pendiente = orden_de_siembra(self.e, plantines=1)
        extensiones.traspasar(self.e.agronomo, self.e.invernadero, "capataz", None, self.nuevo)
        self.assertEqual(Siembra.objects.get(pk=pendiente.pk).capataz, self.nuevo)

    def test_ext_traspasar_no_hace_nada_con_otro_rol_o_sin_entrante(self):
        """Neutro: el campo `capataz` es obligatorio: sin entrante, o con otro rol, nada cambia y devuelve vacío."""
        pendiente = orden_de_siembra(self.e, plantines=1)
        self.assertEqual(extensiones.traspasar(self.e.agronomo, self.e.invernadero, "capataz", self.e.capataz, None), [])
        self.assertEqual(extensiones.traspasar(self.e.agronomo, self.e.invernadero, "tecnico", None, crear_agronomo("t@infoponia.com")), [])
        self.assertEqual(Siembra.objects.get(pk=pendiente.pk).capataz, self.e.capataz)

    def test_ext_traspasar_no_hace_consultas_por_fila(self):
        """Una consulta por tabla hija: la cantidad no crece con las órdenes."""
        orden_de_siembra(self.e, plantines=1)
        con_una = consultas(lambda: extensiones.traspasar(self.e.agronomo, self.e.invernadero, "capataz", self.e.capataz, self.nuevo))
        for sector in ("crecimiento", "floracion", "fructificacion"):
            orden_de_siembra(self.e, plantines=1, sector=sector)
        Siembra.objects.update(capataz=self.e.capataz)
        con_varias = consultas(lambda: extensiones.traspasar(self.e.agronomo, self.e.invernadero, "capataz", self.e.capataz, self.nuevo))
        self.assertEqual(con_una, con_varias)

    def test_punta_a_punta_modificar_invernadero_traspasa_las_ordenes_y_las_deja_en_su_registro(self):
        """PROD-MOD-INV postcondición b y D-36: el Capataz nuevo recibe la orden y esta queda entre los afectados de
        `modificacion_invernadero` (un solo registro)."""
        pendiente = orden_de_siembra(self.e, plantines=1)
        invernaderos.modificar_invernadero(
            crear_gerente(), self.e.invernadero.pk, **(datos_de(self.e.invernadero) | {"capataz_id": self.nuevo.pk, "personal_confirmado": True})
        )
        self.assertEqual(Siembra.objects.get(pk=pendiente.pk).capataz, self.nuevo)
        registro = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_INVERNADERO).latest("id")
        self.assertIn(("produccion.siembra", pendiente.pk), [(a["modelo"], a["id"]) for a in registro.afectados])


class PestanaLotesActivosTests(BaseDeRegistrantes):
    """`registrar_pestana_de_invernadero("lotes", "Lotes activos", ...)`."""

    def pestana(self, actor):
        coincidencias = [p for p in extensiones.pestanas_de_invernadero(actor, self.e.invernadero) if p.clave == "lotes"]
        return coincidencias[0] if coincidencias else None

    def test_ext_con_datos_muestra_los_lotes_activos_y_escapa_los_nombres(self):
        """El HTML ya armado y escapado: el código del lote y la variedad; un nombre con `<` no se interpreta como HTML."""
        lote = lote_activo(self.e, cantidad=10)
        type(self.e.variedad).objects.filter(pk=self.e.variedad.pk).update(nombre_variedad="Crespa <i>x</i>")
        pestana = self.pestana(self.e.agronomo)
        self.assertEqual(pestana.titulo, "Lotes activos")
        self.assertIn(lote.codigo, pestana.html)
        self.assertIn("&lt;i&gt;", pestana.html)
        self.assertNotIn("<i>x</i>", pestana.html)

    def test_ext_sin_datos_dice_que_no_hay_lotes(self):
        """Neutro: sin lotes activos muestra el estado vacío, no una tabla sin filas."""
        self.assertIn("Sin lotes activos", self.pestana(self.e.agronomo).html)

    def test_ext_la_ven_el_agronomo_y_el_gerente_y_nadie_mas(self):
        """Solo quien ve la ficha: el Agrónomo a cargo y el Gerente (solo lectura); otro rol, `None`."""
        self.assertIsNotNone(self.pestana(self.e.agronomo))
        self.assertIsNotNone(self.pestana(crear_gerente()))
        self.assertIsNone(self.pestana(self.e.capataz))

    def test_ext_no_hace_consultas_por_fila(self):
        """La cantidad de consultas no crece con los lotes."""
        lote_activo(self.e, cantidad=1)
        con_uno = consultas(lambda: self.pestana(self.e.agronomo))
        for _ in range(3):
            lote_activo(self.e, cantidad=1)
        self.assertEqual(con_uno, consultas(lambda: self.pestana(self.e.agronomo)))
