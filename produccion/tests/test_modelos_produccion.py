# Pruebas de los modelos de `produccion` (PRD-01, paso 1): cada restricción de la base (viola y no viola), la herencia multitabla,
# los códigos y los invariantes de las ocupaciones. Fuente: docs/modelo/produccion.md («Restricciones de la base» de cada ficha).

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from contabilidad.models import OrigenDocumento
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.models import Bitacora, Consumo, Lote, OcupacionSector, OrdenTrabajo, ReservaInsumo, Siembra
from produccion.servicios import ordenes
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo, orden_de_siembra, orden_suelta, reservar

Tipo = OrdenTrabajo.Tipo


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


def orden_con(invernadero, **campos):
    """Crea una `OrdenTrabajo` suelta con lo mínimo y los `campos` que se quieran pisar (para probar restricciones)."""
    valores = dict(
        tipo_orden=Tipo.ENTREGA,
        numero=ordenes.siguiente_numero(),
        fecha_programada_orden=timezone.localdate(),
        invernadero=invernadero,
    )
    valores.update(campos)
    return OrdenTrabajo.objects.create(**valores)


class ModelosDeProduccionTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    # ---- OrdenTrabajo ----

    def test_regla_orden_la_siembra_es_una_orden_de_trabajo_con_su_tipo(self):
        """docs/modelo/produccion.md, «OrdenTrabajo» y D-50: la `Siembra` es una `OrdenTrabajo` (multitabla) de tipo siembra y su
        documento de origen es una orden de trabajo (D-52)."""
        siembra = orden_de_siembra(self.e)
        orden = OrdenTrabajo.objects.get(pk=siembra.pk)
        self.assertEqual(orden.tipo_orden, Tipo.SIEMBRA)
        self.assertEqual(orden.tipo, OrigenDocumento.Tipo.ORDEN_DE_TRABAJO)
        self.assertEqual(Siembra.objects.get(pk=orden.pk).capataz, self.e.capataz)

    def test_regla_orden_codigos_legibles(self):
        """«Códigos legibles» de la ficha: `OT-{numero:04d}` y `L-{id}`."""
        siembra = orden_de_siembra(self.e)
        self.assertEqual(siembra.codigo, f"OT-{siembra.numero:04d}")
        self.assertEqual(str(siembra), siembra.codigo)
        lote = lote_activo(self.e)
        self.assertEqual(lote.codigo, f"L-{lote.pk}")

    def test_regla_orden_numero_unico(self):
        """`numero` único (lo asigna la secuencia)."""
        orden = orden_suelta(self.e.invernadero, Tipo.ENTREGA)
        viola(self, lambda: orden_con(self.e.invernadero, numero=orden.numero))

    def test_d67_se_guardan_ordenes_sueltas_de_los_tipos_futuros(self):
        """D-67 punto 1 (punto 0): `tipo_orden` nace con los cinco valores, y entrega y mantenimiento se guardan sin hija."""
        for tipo in (Tipo.ENTREGA, Tipo.MANTENIMIENTO, Tipo.COSECHA):
            self.assertEqual(OrdenTrabajo.objects.get(pk=orden_suelta(self.e.invernadero, tipo).pk).tipo_orden, tipo)

    def test_d67_un_tipo_fuera_de_la_lista_viola_la_restriccion(self):
        """D-67 punto 1: el `CheckConstraint` «tipo dentro de su lista» rechaza un valor desconocido."""
        viola(self, lambda: orden_con(self.e.invernadero, tipo_orden="otro"))

    def test_regla_orden_estado_y_prioridad_dentro_de_su_lista(self):
        """`estado_orden` dentro de su lista; `prioridad_orden` nula o dentro de la lista."""
        viola(self, lambda: orden_con(self.e.invernadero, estado_orden="rota"))
        viola(self, lambda: orden_con(self.e.invernadero, prioridad_orden="urgente"))
        orden_con(self.e.invernadero, prioridad_orden="alta")

    def test_regla_orden_fecha_de_resolucion_nula_si_y_solo_si_a_realizar(self):
        """`fecha_resolucion_orden` es nula si y solo si la orden está «a realizar»."""
        hoy = timezone.localdate()
        viola(self, lambda: orden_con(self.e.invernadero, fecha_resolucion_orden=hoy))
        viola(self, lambda: orden_con(self.e.invernadero, estado_orden="concretada"))
        orden_con(self.e.invernadero, estado_orden="concretada", fecha_resolucion_orden=hoy)

    def test_regla_orden_motivo_de_cancelacion_segun_estado(self):
        """`motivo_cancelacion` no nulo y no vacío si y solo si la orden está «cancelada»: viola una cancelada sin motivo o con
        motivo vacío, y una no cancelada con motivo; no viola una cancelada con motivo."""
        cancelada = dict(estado_orden="cancelada", fecha_resolucion_orden=timezone.localdate())
        viola(self, lambda: orden_con(self.e.invernadero, **cancelada))
        viola(self, lambda: orden_con(self.e.invernadero, motivo_cancelacion="", **cancelada))
        viola(self, lambda: orden_con(self.e.invernadero, motivo_cancelacion="x"))
        orden_con(self.e.invernadero, motivo_cancelacion="Ya no hace falta", **cancelada)

    def test_regla_orden_programada_no_anterior_a_la_creacion(self):
        """`fecha_programada_orden >= fecha_creacion_orden`."""
        hoy = timezone.localdate()
        viola(self, lambda: orden_con(self.e.invernadero, fecha_creacion_orden=hoy, fecha_programada_orden=hoy - timedelta(days=1)))
        orden_con(self.e.invernadero, fecha_creacion_orden=hoy, fecha_programada_orden=hoy)

    # ---- ReservaInsumo ----

    def test_regla_reserva_a_lo_sumo_una_activa_por_orden_e_insumo(self):
        """Ficha «ReservaInsumo»: único `(orden, insumo_invernadero)` solo entre las «activa» (D-66 punto 8, COM-05a2). Reemplaza a la de PRD-01, que
        afirmaba «sin condición»: dos activas violan; una cancelada y una activa no."""
        orden = orden_suelta(self.e.invernadero, Tipo.ENTREGA)
        reservar(orden, self.e.existencia_semilla, 5)
        viola(self, lambda: reservar(orden, self.e.existencia_semilla, 3))
        otra = orden_suelta(self.e.invernadero, Tipo.ENTREGA)
        reservar(otra, self.e.existencia_semilla, 5, estado="cancelada")
        reservar(otra, self.e.existencia_semilla, 3)

    def test_regla_reserva_cantidad_reservada_positiva(self):
        """`cantidad_reservada > 0`."""
        orden = orden_suelta(self.e.invernadero, Tipo.ENTREGA)
        viola(self, lambda: reservar(orden, self.e.existencia_semilla, 0))

    def test_regla_reserva_utilizada_mayor_que_la_reservada_viola(self):
        """`cantidad_utilizada <= cantidad_reservada` para siempre (D-68 punto 2)."""
        reserva = reservar(orden_suelta(self.e.invernadero, Tipo.ENTREGA), self.e.existencia_semilla, 5)
        consumida = dict(estado="consumida", cantidad_devuelta=Decimal("0"))
        viola(self, lambda: ReservaInsumo.objects.filter(pk=reserva.pk).update(cantidad_utilizada=Decimal("6"), **consumida))
        ReservaInsumo.objects.filter(pk=reserva.pk).update(cantidad_utilizada=Decimal("5"), **consumida)

    def test_regla_reserva_devuelta_hasta_lo_no_utilizado(self):
        """`cantidad_devuelta <= cantidad_reservada − cantidad_utilizada`."""
        reserva = reservar(orden_suelta(self.e.invernadero, Tipo.ENTREGA), self.e.existencia_semilla, 5)
        consumida = dict(estado="consumida", cantidad_utilizada=Decimal("3"))
        viola(self, lambda: ReservaInsumo.objects.filter(pk=reserva.pk).update(cantidad_devuelta=Decimal("3"), **consumida))
        ReservaInsumo.objects.filter(pk=reserva.pk).update(cantidad_devuelta=Decimal("2"), **consumida)

    def test_regla_reserva_cantidades_segun_estado(self):
        """Activa: utilizada y devuelta nulas. Consumida: ambas cargadas. Cancelada: ambas nulas o ambas cargadas."""
        reserva = reservar(orden_suelta(self.e.invernadero, Tipo.ENTREGA), self.e.existencia_semilla, 5)
        viola(self, lambda: ReservaInsumo.objects.filter(pk=reserva.pk).update(cantidad_utilizada=Decimal("1")))
        viola(self, lambda: ReservaInsumo.objects.filter(pk=reserva.pk).update(estado="consumida"))
        ReservaInsumo.objects.filter(pk=reserva.pk).update(
            estado="cancelada", cantidad_utilizada=Decimal("0"), cantidad_devuelta=Decimal("0")
        )  # concreción con consumo 0

    # ---- Siembra ----

    def test_regla_siembra_plantines_positivos(self):
        """`cant_plantines_siembra > 0`."""
        viola(self, lambda: orden_de_siembra(self.e, plantines=0, agujeros=1))

    def _siembra_de_carga_inicial(self, **cambios):
        """Una `Siembra` de carga inicial cruda (sin Capataz), con las tres fechas de la orden en hoy y `fecha_siembra` pasada."""
        hoy = timezone.localdate()
        valores = dict(
            tipo_orden=Tipo.SIEMBRA,
            numero=ordenes.siguiente_numero(),
            fecha_creacion_orden=hoy,
            fecha_programada_orden=hoy,
            fecha_resolucion_orden=hoy,
            estado_orden="concretada",
            agronomo=self.e.agronomo,
            invernadero=self.e.invernadero,
            capataz=None,
            tipo_siembra=Siembra.TipoSiembra.CARGA_INICIAL,
            cant_plantines_siembra=10,
            fecha_siembra=hoy - timedelta(days=30),
            variedad=self.e.variedad,
        )
        valores.update(cambios)
        return Siembra.objects.create(**valores)

    def test_d92_las_siembras_existentes_quedan_normales_y_con_capataz(self):
        """D-92 punto 12 (migración de `produccion`): `tipo_siembra` por defecto `normal`; una siembra normal sigue con Capataz."""
        siembra = Siembra.objects.get(pk=orden_de_siembra(self.e).pk)
        self.assertEqual(siembra.tipo_siembra, "normal")
        self.assertEqual(siembra.capataz, self.e.capataz)

    def test_d92_check_siembra_tipo_valido(self):
        """CHECK `siembra_tipo_valido` (D-92 punto 12): solo `normal` y `carga_inicial`."""
        siembra = orden_de_siembra(self.e)
        viola(self, lambda: Siembra.objects.filter(pk=siembra.pk).update(tipo_siembra="otra"))

    def test_d92_check_siembra_capataz_segun_tipo(self):
        """CHECK `siembra_capataz_segun_tipo` (D-92 punto 12, L1): el Capataz es nulo si y solo si la siembra es de carga inicial."""
        carga = self._siembra_de_carga_inicial()
        self.assertIsNone(Siembra.objects.get(pk=carga.pk).capataz_id)
        viola(self, lambda: self._siembra_de_carga_inicial(capataz=self.e.capataz))  # carga inicial con Capataz
        viola(self, lambda: self._siembra_de_carga_inicial(tipo_siembra="normal"))  # normal sin Capataz
        normal = orden_de_siembra(self.e)
        viola(self, lambda: Siembra.objects.filter(pk=normal.pk).update(capataz=None))

    def test_d92_la_carga_inicial_cumple_el_check_de_fechas_con_las_tres_fechas_en_hoy(self):
        """PRD-05, decisión del estudiante (25/11/2026): `fecha_creacion_orden = fecha_programada_orden = fecha_resolucion_orden = hoy` cumple
        `orden_trabajo_programada_desde_creacion`; `fecha_siembra` es la pasada indicada. Con la programada en el pasado, el CHECK la rechaza."""
        hoy = timezone.localdate()
        carga = Siembra.objects.get(pk=self._siembra_de_carga_inicial().pk)
        self.assertEqual((carga.fecha_creacion_orden, carga.fecha_programada_orden, carga.fecha_resolucion_orden), (hoy, hoy, hoy))
        self.assertLess(carga.fecha_siembra, hoy)
        viola(self, lambda: self._siembra_de_carga_inicial(fecha_programada_orden=hoy - timedelta(days=30)))

    def test_d92_la_bitacora_acepta_el_tipo_carga_inicial(self):
        """CHECK `bitacora_tipo_evento_valido` (D-92 punto 12): suma `carga_inicial`."""
        hoy = timezone.localdate()
        registro = Bitacora.objects.create(
            invernadero=self.e.invernadero,
            fecha_bitacora=hoy,
            hora_bitacora=timezone.localtime().time(),
            tipo_evento=Bitacora.TipoEvento.CARGA_INICIAL,
        )
        self.assertEqual(Bitacora.objects.get(pk=registro.pk).tipo_evento, "carga_inicial")

    # ---- Lote ----

    def test_regla_lote_cantidad_actual_no_supera_la_inicial_ni_el_costo_es_negativo(self):
        """Ficha «Lote»: `cantidad_actual <= cantidad_inicial` y `costo_acumulado >= 0`."""
        lote = lote_activo(self.e, cantidad=10)
        viola(self, lambda: Lote.objects.filter(pk=lote.pk).update(cantidad_actual=11))
        viola(self, lambda: Lote.objects.filter(pk=lote.pk).update(costo_acumulado=Decimal("-1")))

    def test_regla_lote_finalizado_si_y_solo_si_no_quedan_plantas(self):
        """`estado_lote = finalizado` si y solo si `cantidad_actual = 0`, y con 0 plantas el costo es 0."""
        lote = lote_activo(self.e, cantidad=10)
        viola(self, lambda: Lote.objects.filter(pk=lote.pk).update(estado_lote="finalizado"))
        viola(self, lambda: Lote.objects.filter(pk=lote.pk).update(cantidad_actual=0))
        viola(self, lambda: Lote.objects.filter(pk=lote.pk).update(cantidad_actual=0, estado_lote="finalizado"))  # costo 100 sin plantas
        Lote.objects.filter(pk=lote.pk).update(cantidad_actual=0, estado_lote="finalizado", costo_acumulado=Decimal("0"))

    # ---- OcupacionSector ----

    def test_regla_ocupacion_cantidades_y_unico_por_orden_y_sector(self):
        """Ficha «OcupacionSector»: planificados > 0; ocupados <= planificados; único `(orden, sector)`."""
        siembra = orden_de_siembra(self.e, plantines=10)
        ocupacion = OcupacionSector.objects.get(orden=siembra)
        viola(self, lambda: OcupacionSector.objects.filter(pk=ocupacion.pk).update(cant_agujeros_ocupados=11))
        viola(self, lambda: OcupacionSector.objects.filter(pk=ocupacion.pk).update(cant_agujeros_planificados=0))
        viola(
            self,
            lambda: OcupacionSector.objects.create(
                orden=siembra, sector=self.e.sectores["germinacion"], cant_agujeros_planificados=5
            ),
        )

    # ---- Bitácora y consumo ----

    def test_regla_bitacora_tipo_de_evento_dentro_de_su_lista_y_consumo_con_siembra(self):
        """`tipo_evento` dentro de la lista (siembra, transicion y merma nacen acá); el consumo de PRD-01 exige `siembra`."""
        hoy = timezone.localdate()
        base = dict(invernadero=self.e.invernadero, fecha_bitacora=hoy, hora_bitacora=timezone.localtime().time())
        viola(self, lambda: Bitacora.objects.create(tipo_evento="otro", **base))
        for tipo in ("siembra", "transicion", "merma"):
            self.assertEqual(Bitacora.objects.create(tipo_evento=tipo, **base).tipo, OrigenDocumento.Tipo.BITACORA)
        siembra = orden_de_siembra(self.e)
        consumo = dict(
            monto_consumo=Decimal("1"), cant_consumo=Decimal("1"), fecha_consumo=hoy,
            insumo_invernadero=self.e.existencia_semilla, tipo_evento="siembra", **base,
        )
        viola(self, lambda: Consumo.objects.create(**consumo))  # sin siembra
        Consumo.objects.create(siembra=siembra, **consumo)

    # ---- Invariantes ----

    def test_invariante_cada_ocupacion_con_lote_tiene_su_orden_concretada_y_ninguna_cuenta_duplica(self):
        """Invariante (docs/modelo/produccion.md, «OcupacionSector»): cada ocupación con lote pertenece a una orden concretada; los
        agujeros ocupados de un lote suman su `cantidad_actual`; y ninguna orden usa un sector dos veces."""
        lote_activo(self.e, cantidad=30)
        orden_de_siembra(self.e, plantines=10)
        for ocupacion in OcupacionSector.objects.filter(lote__isnull=False).select_related("orden"):
            self.assertEqual(ocupacion.orden.estado_orden, OrdenTrabajo.Estado.CONCRETADA)
        for lote in Lote.objects.all():
            self.assertEqual(sum(o.cant_agujeros_ocupados for o in lote.ocupaciones.all()), lote.cantidad_actual)
        pares = list(OcupacionSector.objects.values_list("orden_id", "sector_id"))
        self.assertEqual(len(pares), len(set(pares)))
