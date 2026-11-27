# Pruebas del modelo `MantenimientoTecnico` (IOT-07, paso 1; docs/modelo/iot.md, «MantenimientoTecnico»; docs/casos_de_uso/iot/mantenimiento_automatico.md, «Modelo y migraciones»;
# D-53 punto 6, D-73 punto 3, D-79) y de la restricción `ordentrabajo_prioridad_en_mantenimiento` de `produccion`. La de la migración lleva la etiqueta «migracion»: desarma y vuelve
# a armar el esquema (en local se excluye; el CI la corre).

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, tag
from django.utils import timezone

from iot.models import MantenimientoTecnico
from iot.tests import fabricas
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_tecnico
from produccion.models import OrdenTrabajo
from produccion.tests.fabricas import invernadero_con_produccion, orden_de_siembra


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


class MantenimientoTecnicoModeloTests(fabricas.ConCatalogoIot, TestCase):
    """El modelo, su fábrica y las restricciones de la base."""

    def setUp(self):
        self.tecnico = crear_tecnico("tecnico@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"), tecnico=self.tecnico)
        self.sistema = fabricas.sistema(self.norte)
        self.actuador = fabricas.actuador(self.sistema, fabricas.tipo_actuador(), identificador="norte/extractor")

    def alerta(self):
        """Una alerta «comando fallido» del actuador, creada con la API de alertas (la base exige su destinatario)."""
        return api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_comando_fallido", f"hw:{self.actuador.pk}", "x")

    def datos(self, **extra):
        """Lo mínimo de una orden de mantenimiento para crearla a mano (sin la fábrica); `extra` pisa campos."""
        from produccion.servicios import ordenes

        hoy = timezone.localdate()
        base = dict(
            numero=ordenes.siguiente_numero(), fecha_programada_orden=hoy, prioridad_orden="alta", invernadero=self.norte, tecnico=self.tecnico
        )
        return base | extra

    def test_md111_crear_una_orden_le_pone_tipo_mantenimiento_y_su_codigo_es_ot_nnnn(self):
        """`save()` fija `tipo_orden = mantenimiento` aunque se pida otro; el código sale del `numero` (D-52 punto 3): `OT-NNNN`."""
        orden = MantenimientoTecnico.objects.create(**self.datos(tipo_orden="siembra"))
        orden.refresh_from_db()
        self.assertEqual(orden.tipo_orden, OrdenTrabajo.Tipo.MANTENIMIENTO)
        self.assertRegex(orden.codigo, r"^OT-\d{4,}$")
        self.assertEqual(orden.codigo, f"OT-{orden.numero:04d}")
        self.assertTrue(OrdenTrabajo.objects.filter(pk=orden.pk, tipo_orden="mantenimiento").exists())

    def test_md111_el_tipo_de_mantenimiento_nace_en_revision_y_tiene_los_cinco_valores(self):
        """MD-111: revisión (la automática), reparación, calibración, reemplazo y mantenimiento general."""
        orden = MantenimientoTecnico.objects.create(**self.datos())
        self.assertEqual(orden.tipo_mantenimiento, "revision")
        self.assertEqual(
            [valor for valor, _ in MantenimientoTecnico.TipoMantenimiento.choices],
            ["revision", "reparacion", "calibracion", "reemplazo", "mantenimiento_general"],
        )
        self.assertEqual(MantenimientoTecnico.TipoMantenimiento.REVISION.label, "Revisión")

    def test_regla_prioridad_obligatoria_un_mantenimiento_sin_prioridad_no_se_guarda(self):
        """D-53 punto 6: la restricción `ordentrabajo_prioridad_en_mantenimiento` de la base."""
        viola(self, lambda: MantenimientoTecnico.objects.create(**self.datos(prioridad_orden=None)))
        self.assertFalse(MantenimientoTecnico.objects.exists())

    def test_regla_prioridad_obligatoria_tambien_vale_para_una_orden_suelta_de_mantenimiento(self):
        """La restricción es del padre y por `tipo_orden`: una `OrdenTrabajo` de tipo mantenimiento sin prioridad tampoco se guarda."""
        from produccion.servicios import ordenes

        def crear():
            OrdenTrabajo.objects.create(
                tipo_orden="mantenimiento", numero=ordenes.siguiente_numero(), fecha_programada_orden=timezone.localdate(), invernadero=self.norte
            )

        viola(self, crear)

    def test_regla_prioridad_obligatoria_no_toca_a_las_otras_ordenes(self):
        """Una orden de otro tipo sin prioridad (una entrega suelta) se sigue guardando: la restricción es solo del mantenimiento."""
        from produccion.servicios import ordenes

        orden = OrdenTrabajo.objects.create(
            tipo_orden="entrega", numero=ordenes.siguiente_numero(), fecha_programada_orden=timezone.localdate(), invernadero=self.norte
        )
        self.assertIsNone(orden.prioridad_orden)

    def test_regla_prioridad_obligatoria_una_siembra_sin_prioridad_se_sigue_guardando(self):
        """MD-73: la prioridad de una siembra es opcional. Con una siembra real, sin prioridad."""
        escenario = invernadero_con_produccion()
        siembra = orden_de_siembra(escenario, prioridad=None)
        self.assertIsNone(siembra.prioridad_orden)
        self.assertTrue(OrdenTrabajo.objects.filter(pk=siembra.pk).exists())

    def test_r047_el_tecnico_es_obligatorio(self):
        """R047: `tecnico` no admite nulo."""
        viola(self, lambda: MantenimientoTecnico.objects.create(**self.datos(tecnico=None)))

    def test_r047_el_tecnico_se_alcanza_por_mantenimientos_asignados(self):
        """`related_name = mantenimientos_asignados` (extracto, «Modelo y migraciones»)."""
        orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        self.assertEqual(list(self.tecnico.mantenimientos_asignados.all()), [orden])

    def test_r057_el_equipo_se_alcanza_por_mantenimientos(self):
        """`hardware` es un `ManyToManyField` con `related_name = mantenimientos`."""
        orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        self.assertEqual(list(self.actuador.mantenimientos.all()), [orden])

    def test_r048_la_alerta_es_opcional_y_se_alcanza_por_mantenimiento_tecnico(self):
        """R048: `alerta` es un `OneToOne` nulo con `related_name = mantenimiento_tecnico`."""
        sin_alerta = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        self.assertIsNone(sin_alerta.alerta)
        alerta = self.alerta()
        con_alerta = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador], alerta=alerta)
        self.assertEqual(alerta.mantenimiento_tecnico, con_alerta)

    def test_r048_una_alerta_tiene_a_lo_sumo_una_orden(self):
        """R048 es 0..1 – 0..1: dos órdenes no comparten alerta."""
        alerta = self.alerta()
        fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador], alerta=alerta)
        viola(self, lambda: fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador], alerta=alerta))

    def test_invariante_r057_una_orden_de_la_fabrica_tiene_al_menos_un_equipo(self):
        """R057 (1..*): la base no lo garantiza, lo garantiza el servicio y lo prueba esta prueba de invariante con la fábrica."""
        orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        self.assertGreaterEqual(orden.hardware.count(), 1)

    def test_la_fabrica_arma_la_orden_automatica_por_defecto(self):
        """La fábrica deja una orden como la automática: «revisión», prioridad alta, hoy, sin Agrónomo y «a realizar»."""
        orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        self.assertEqual(
            (orden.tipo_mantenimiento, orden.prioridad_orden, orden.fecha_programada_orden, orden.agronomo, orden.estado_orden),
            ("revision", "alta", timezone.localdate(), None, "a_realizar"),
        )

    def test_la_fabrica_arma_una_cancelada_con_su_motivo_y_su_fecha(self):
        """Las restricciones del padre exigen fecha de resolución y motivo en una orden cancelada: la fábrica los carga."""
        orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador], estado="cancelada")
        self.assertEqual((orden.estado_orden, orden.fecha_resolucion_orden, bool(orden.motivo_cancelacion)), ("cancelada", timezone.localdate(), True))

    def test_la_orden_de_mantenimiento_es_una_fila_del_origen_de_documento(self):
        """D-52: una `OrdenTrabajo` es hija directa de `OrigenDocumento`; el mantenimiento, nieta."""
        from contabilidad.models import OrigenDocumento

        orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        self.assertEqual(OrigenDocumento.objects.get(pk=orden.pk).tipo, OrigenDocumento.Tipo.ORDEN_DE_TRABAJO)


def restricciones_de(tabla):
    """Los nombres de las restricciones de la tabla, según la base."""
    with connection.cursor() as cursor:
        return set(connection.introspection.get_constraints(cursor, tabla))


@tag("migracion")
class MigracionDeMantenimientoTests(TransactionTestCase):
    """Las dos migraciones de IOT-07 migran y vuelven atrás: `produccion/0007` (la restricción) e `iot/0005` (la tabla). Al terminar deja la base en la última migración."""

    ANTERIOR_DE_PRODUCCION = ("produccion", "0006_bitacora_tipo_comando")
    ANTERIOR_DE_IOT = ("iot", "0004_registro_comando")
    ESTA_DE_PRODUCCION = ("produccion", "0007_ordentrabajo_prioridad_en_mantenimiento")
    ESTA_DE_IOT = ("iot", "0005_mantenimiento_tecnico")

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrar(self, *destinos):
        executor = MigrationExecutor(connection)
        executor.migrate(list(destinos))

    def test_la_migracion_de_iot_crea_la_tabla_y_vuelve_atras(self):
        """`iot/0005` crea `iot_mantenimientotecnico` (y la tabla de sus equipos) y, al volver atrás, las quita."""
        self.assertIn("iot_mantenimientotecnico", connection.introspection.table_names())
        self.migrar(self.ANTERIOR_DE_IOT)
        self.assertNotIn("iot_mantenimientotecnico", connection.introspection.table_names())
        self.assertNotIn("iot_mantenimientotecnico_hardware", connection.introspection.table_names())
        self.migrar(self.ESTA_DE_IOT)
        self.assertIn("iot_mantenimientotecnico", connection.introspection.table_names())
        self.assertIn("iot_mantenimientotecnico_hardware", connection.introspection.table_names())

    def test_la_migracion_de_produccion_agrega_la_restriccion_y_vuelve_atras(self):
        """`produccion/0007` agrega solo `ordentrabajo_prioridad_en_mantenimiento` y, al volver atrás, la quita. Para volver atrás primero se deshace la de `iot`, que depende de ella."""
        self.assertIn("ordentrabajo_prioridad_en_mantenimiento", restricciones_de("produccion_ordentrabajo"))
        self.migrar(self.ANTERIOR_DE_IOT, self.ANTERIOR_DE_PRODUCCION)
        self.assertNotIn("ordentrabajo_prioridad_en_mantenimiento", restricciones_de("produccion_ordentrabajo"))
        self.assertIn("orden_trabajo_cosecha_con_prioridad", restricciones_de("produccion_ordentrabajo"))  # la de la cosecha no se tocó
        self.migrar(self.ESTA_DE_PRODUCCION, self.ESTA_DE_IOT)
        self.assertIn("ordentrabajo_prioridad_en_mantenimiento", restricciones_de("produccion_ordentrabajo"))
        self.assertIn("orden_trabajo_cosecha_con_prioridad", restricciones_de("produccion_ordentrabajo"))
