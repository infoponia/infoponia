# Pruebas de los modelos de PRD-04 (paso 1): `FueraDeServicio`, `Reubicacion`, el cambio de `OcupacionSector` (`orden` nula y
# `reubicacion`, «exactamente una de las dos»), los tipos de bitácora nuevos, la acción de auditoría y la migración `0004`.
# Fuente: docs/modelo/produccion.md («FueraDeServicio», «Reubicacion», «Cambios a las fichas del lote 4 por el lote 5»), D-51 punto 1.
# La de la migración lleva la etiqueta «migracion»: desarma y vuelve a armar el esquema (en local se excluye; el CI la corre).

from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, tag
from django.utils import timezone

from core.models import ACCIONES_DE_NEGOCIO, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Bitacora, FueraDeServicio, Lote, OcupacionSector, Reubicacion
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo, orden_de_siembra


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


def datos_de_bitacora(escenario, tipo, **campos):
    """Lo mínimo de una `Bitacora` hija: invernadero, tipo, fecha y hora de hoy y el Agrónomo como responsable."""
    valores = dict(
        invernadero=escenario.invernadero,
        tipo_evento=tipo,
        fecha_bitacora=timezone.localdate(),
        hora_bitacora=timezone.localtime().time(),
        responsable=escenario.agronomo,
    )
    valores.update(campos)
    return valores


def fuera_de_servicio_de(escenario, sector, **campos):
    """Un registro `FueraDeServicio` del sector, abierto por defecto."""
    valores = datos_de_bitacora(escenario, "fuera_de_servicio", **campos)
    valores.setdefault("motivo_fuera_de_servicio", "Se rompió el canal de retorno")
    valores.setdefault("sector", sector)
    registro = FueraDeServicio.objects.create(**valores)
    registro.sectores.add(sector)
    return registro


class ModelosDeFueraDeServicioTests(ConDatosDeInventario, TestCase):
    """Los modelos nuevos y las restricciones de la base."""

    @classmethod
    def setUpTestData(cls):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        cls.e = invernadero_con_produccion()
        cls.sector = cls.e.sectores["germinacion"]

    def test_regla_un_solo_registro_abierto_por_sector(self):
        """Modelo `FueraDeServicio`: a lo sumo un registro abierto (`fecha_fin` nula) por sector."""
        fuera_de_servicio_de(self.e, self.sector)
        viola(self, lambda: fuera_de_servicio_de(self.e, self.sector))

    def test_regla_un_registro_cerrado_no_impide_abrir_otro(self):
        """Modelo `FueraDeServicio`: la restricción solo mira los abiertos; un sector que volvió a servicio puede salir de nuevo."""
        anterior = fuera_de_servicio_de(self.e, self.sector)
        anterior.fecha_fin = timezone.localdate()
        anterior.save(update_fields=["fecha_fin"])
        nuevo = fuera_de_servicio_de(self.e, self.sector)
        self.assertEqual(FueraDeServicio.objects.filter(sector=self.sector).count(), 2)
        self.assertIsNone(nuevo.fecha_fin)

    def test_regla_dos_sectores_pueden_estar_fuera_de_servicio_a_la_vez(self):
        """Modelo `FueraDeServicio`: la unicidad es por sector."""
        fuera_de_servicio_de(self.e, self.sector)
        fuera_de_servicio_de(self.e, self.e.sectores["crecimiento"])
        self.assertEqual(FueraDeServicio.objects.filter(fecha_fin__isnull=True).count(), 2)

    def test_regla_la_fecha_efectiva_es_la_fecha_de_la_bitacora(self):
        """Modelo `FueraDeServicio`: `fecha_efectiva` es la `fecha_bitacora` del registro (puede ser anterior a hoy)."""
        ayer = timezone.localdate() - timedelta(days=1)
        registro = fuera_de_servicio_de(self.e, self.sector, fecha_bitacora=ayer)
        self.assertEqual(registro.fecha_efectiva, ayer)

    def test_regla_el_registro_es_una_bitacora_de_tipo_fuera_de_servicio(self):
        """D-51 punto 2 y la restricción de tipos de la bitácora: el nuevo tipo es válido y la hija se lista como `Bitacora`."""
        registro = fuera_de_servicio_de(self.e, self.sector)
        self.assertEqual(Bitacora.objects.get(pk=registro.pk).tipo_evento, "fuera_de_servicio")
        self.assertEqual(list(registro.sectores.all()), [self.sector])

    def test_regla_el_tipo_de_evento_invalido_se_rechaza(self):
        """La restricción `bitacora_tipo_evento_valido` sigue rechazando un tipo desconocido."""
        viola(self, lambda: Bitacora.objects.create(**datos_de_bitacora(self.e, "inventado")))

    def test_regla_una_reubicacion_es_una_bitacora_de_tipo_reubicacion_con_lote(self):
        """Modelo `Reubicacion`: hija de `Bitacora` con lote y el sector de origen en `sectores`."""
        lote = lote_activo(self.e)
        reubicacion = Reubicacion.objects.create(**datos_de_bitacora(self.e, "reubicacion", lote=lote))
        reubicacion.sectores.add(self.sector)
        self.assertEqual(Bitacora.objects.get(pk=reubicacion.pk).lote_id, lote.pk)

    def test_regla_c9_una_ocupacion_de_reubicacion_no_lleva_orden(self):
        """D-51 punto 1 / C9: una ocupación puede pertenecer a una reubicación (sin orden), con lote y planificados = ocupados."""
        lote = lote_activo(self.e)
        reubicacion = Reubicacion.objects.create(**datos_de_bitacora(self.e, "reubicacion", lote=lote))
        ocupacion = OcupacionSector.objects.create(
            reubicacion=reubicacion, sector=self.e.sectores["germinacion"], lote=lote, cant_agujeros_planificados=10, cant_agujeros_ocupados=10
        )
        self.assertIsNone(ocupacion.orden_id)

    def test_regla_c9_una_ocupacion_sin_orden_ni_reubicacion_se_rechaza(self):
        """C9: exactamente una de las dos."""
        viola(self, lambda: OcupacionSector.objects.create(sector=self.sector, cant_agujeros_planificados=5))

    def test_regla_c9_una_ocupacion_con_orden_y_reubicacion_se_rechaza(self):
        """C9: exactamente una de las dos."""
        lote = lote_activo(self.e)
        orden = orden_de_siembra(self.e, plantines=5, sector="crecimiento", con_reserva=False)
        reubicacion = Reubicacion.objects.create(**datos_de_bitacora(self.e, "reubicacion", lote=lote))
        viola(
            self,
            lambda: OcupacionSector.objects.create(
                orden=orden, reubicacion=reubicacion, sector=self.e.sectores["floracion"], cant_agujeros_planificados=5
            ),
        )

    def test_regla_c9_una_reubicacion_usa_un_sector_una_sola_vez(self):
        """D-51 punto 1: único `(reubicacion, sector)`."""
        lote = lote_activo(self.e)
        reubicacion = Reubicacion.objects.create(**datos_de_bitacora(self.e, "reubicacion", lote=lote))
        datos = dict(reubicacion=reubicacion, sector=self.sector, lote=lote, cant_agujeros_planificados=3, cant_agujeros_ocupados=3)
        OcupacionSector.objects.create(**datos)
        viola(self, lambda: OcupacionSector.objects.create(**datos))

    def test_regla_c9_una_orden_sigue_usando_un_sector_una_sola_vez(self):
        """D-50: el único `(orden, sector)` condicional sigue valiendo para las órdenes."""
        orden = orden_de_siembra(self.e, plantines=5, sector="germinacion", con_reserva=False)
        viola(self, lambda: OcupacionSector.objects.create(orden=orden, sector=self.sector, cant_agujeros_planificados=1))

    def test_regla_el_mismo_sector_puede_estar_en_una_orden_y_en_una_reubicacion(self):
        """Los dos únicos son independientes: un sector con ocupación de una orden recibe también una reubicación."""
        lote = lote_activo(self.e, sector="crecimiento", etapa="crecimiento")
        reubicacion = Reubicacion.objects.create(**datos_de_bitacora(self.e, "reubicacion", lote=lote))
        OcupacionSector.objects.create(
            reubicacion=reubicacion, sector=self.e.sectores["crecimiento"], lote=lote, cant_agujeros_planificados=2, cant_agujeros_ocupados=2
        )
        self.assertEqual(OcupacionSector.objects.filter(sector=self.e.sectores["crecimiento"]).count(), 2)

    def test_post_i_la_accion_de_auditoria_existe_y_es_de_negocio(self):
        """D-51 punto 9: `fuera_de_servicio_sector` es acción de negocio, con etiqueta."""
        accion = RegistroAuditoria.Accion.FUERA_DE_SERVICIO_SECTOR
        self.assertEqual(accion.value, "fuera_de_servicio_sector")
        self.assertIn(accion, ACCIONES_DE_NEGOCIO)
        self.assertTrue(accion.label)


ANTERIOR = ("produccion", "0003_aplicaciones")
ESTA = ("produccion", "0004_fuera_de_servicio")


def restricciones_de(tabla):
    """Los nombres de las restricciones de la tabla, tal como las ve la base."""
    with connection.cursor() as cursor:
        return set(connection.introspection.get_constraints(cursor, tabla))


@tag("migracion")
class MigracionDeFueraDeServicioTests(ConDatosDeInventario, TransactionTestCase):
    """Migra hacia atrás y hacia adelante con un lote y su ocupación ya cargados. Al terminar deja la base en la última migración."""

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.migrate([destino])

    def test_regla_la_migracion_conserva_las_ocupaciones_con_su_orden(self):
        """PRD-04 paso 1: con un lote ya ocupando un sector, la `0004` (y su vuelta atrás) conserva la ocupación y su `orden`; la
        restricción «exactamente una» se agrega y se quita."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        e = invernadero_con_produccion(geografia_propia=True)
        lote = lote_activo(e)
        ocupacion = OcupacionSector.objects.get(lote=lote)
        self.assertIn("ocupacion_orden_o_reubicacion", restricciones_de("produccion_ocupacionsector"))

        self.migrar(ANTERIOR)
        self.assertNotIn("ocupacion_orden_o_reubicacion", restricciones_de("produccion_ocupacionsector"))
        self.assertNotIn("produccion_reubicacion", connection.introspection.table_names())

        self.migrar(ESTA)
        self.assertIn("ocupacion_orden_o_reubicacion", restricciones_de("produccion_ocupacionsector"))
        conservada = OcupacionSector.objects.get(pk=ocupacion.pk)
        self.assertEqual(conservada.orden_id, ocupacion.orden_id)
        self.assertIsNone(conservada.reubicacion_id)
        self.assertEqual(Lote.objects.get(pk=lote.pk).cantidad_actual, lote.cantidad_actual)
