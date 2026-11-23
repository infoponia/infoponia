# Pruebas de PROD-CNL-ORD · Cancelar Orden, solo órdenes de siembra (PRD-01, paso 7; docs/casos_de_uso/produccion/cancelar_orden.md,
# «Cómo se aplica en la ronda «Producción 1»»). La transición la suma PRD-02; la cosecha, el contrato y el mantenimiento son Fuera de la
# ronda (D-45) y de otras tareas.
#
# Servicios que se prueban (produccion/servicios/ordenes.py), tomados del módulo dentro de cada prueba:
# - resumen_de_cancelacion(actor, orden_id): el detalle del paso 4 y el resumen del paso 6 (lo que libera). No escribe.
# - cancelar_orden(actor, orden_id, motivo) -> OrdenTrabajo: la cancelación del Agrónomo; solo siembra y transición
#   (`TIPOS_QUE_CANCELA_PRODUCCION`, D-67 punto 1): con otro tipo lanza `orden_no_cancelable` ANTES de bloquear nada.
#
# Códigos y campos: sin_permiso; orden_no_cancelable (D-67 punto 1); orden_no_pendiente (8a, con el estado actual); motivo_obligatorio y
# motivo_largo (campo motivo); cambio_simultaneo (8b: cambiaron las reservas). Nunca hay un 500.
#
# Una prueba por regla y por postcondición a, b, c, d, k, m y n. Cada una arma sus datos.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from core.models import Capataz, Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.models import LoteInsumo, MovimientoInsumo
from inventario.servicios import alertas_de_stock
from inventario.tests.fabricas import ConDatosDeInventario, perezoso
from maestros.models import Alerta, Invernadero
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import crear_agronomo
from produccion.servicios import lotes as api_lotes, transiciones
from produccion.errores import ErrorDeProduccion
from produccion.models import Consumo, Lote, OcupacionSector, OrdenTrabajo, ReservaInsumo, TransicionEtapa
from produccion.tests.fabricas import (
    insumo_adicional,
    invernadero_con_produccion,
    lote_con_ciclo,
    orden_de_siembra,
    orden_de_transicion,
    orden_suelta,
    reservar,
)
from produccion.tests.test_prod_pnf_trn import datos as datos_de_planificacion

ordenes = perezoso("produccion.servicios.ordenes")
D = Decimal


def hoy():
    return timezone.localdate()


def rechazo(llamada):
    """Ejecuta `llamada()` y devuelve el `ErrorDeProduccion` que lanza; si no lanza ninguno, la prueba falla."""
    try:
        llamada()
    except ErrorDeProduccion as error:
        return error
    raise AssertionError("Se esperaba un ErrorDeProduccion y no se lanzó ninguno.")


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero completo y una siembra «a realizar» de 50 plantines con la reserva de la semilla (y, si se pide, un adicional)."""

    def setUp(self):
        self.e = invernadero_con_produccion()
        self.orden = orden_de_siembra(self.e, plantines=50)

    def cancelar(self, orden=None, actor=None, motivo="Se cambiaron los planes"):
        return ordenes.cancelar_orden(actor or self.e.agronomo, (orden or self.orden).pk, motivo)

    def rechazo(self, orden=None, actor=None, motivo="Se cambiaron los planes"):
        return rechazo(lambda: self.cancelar(orden, actor, motivo))

    def sin_cambios(self, orden=None):
        """La orden sigue «a realizar» con sus reservas «activas», sin notificaciones ni registro de auditoría."""
        orden = orden or self.orden
        orden = OrdenTrabajo.objects.get(pk=orden.pk)
        self.assertEqual((orden.estado_orden, orden.fecha_resolucion_orden, orden.motivo_cancelacion), ("a_realizar", None, None))
        self.assertEqual(set(ReservaInsumo.objects.filter(orden=orden).values_list("estado", flat=True)), {"activa"})
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="cancelacion_orden").exists())


class ResumenDeCancelacionTests(Base):
    def test_paso_4_el_resumen_dice_que_reservas_se_cancelan_y_que_agujeros_se_liberan(self):
        """Pasos 4 y 6: las reservas de insumo activas (insumo y cantidad) y los sectores con los agujeros comprometidos que se liberan."""
        adicional = insumo_adicional(self.e, "Fertilizante", stock=50)
        reservar(self.orden, adicional, "7")
        resumen = ordenes.resumen_de_cancelacion(self.e.agronomo, self.orden.pk)
        self.assertEqual(resumen.orden.pk, self.orden.pk)
        self.assertEqual([(r.nombre, r.cantidad) for r in resumen.reservas], [(self.e.semilla.nombre_insumo, D("50")), ("Fertilizante", D("7"))])
        self.assertEqual([(s.pk, n) for s, n in resumen.sectores], [(self.e.sectores["germinacion"].pk, 50)])
        self.sin_cambios()

    def test_regla_el_resumen_se_rechaza_igual_que_la_cancelacion(self):
        """El resumen valida permiso, tipo y estado como `cancelar_orden`, y no escribe."""
        entrega = orden_suelta(self.e.invernadero, "entrega")
        self.assertEqual(rechazo(lambda: ordenes.resumen_de_cancelacion(self.e.agronomo, entrega.pk)).codigo, "orden_no_cancelable")
        self.assertEqual(rechazo(lambda: ordenes.resumen_de_cancelacion(crear_gerente(), self.orden.pk)).codigo, "sin_permiso")


class CancelarOrdenTests(Base):
    # ---- Permisos, tipo y estado ----

    def test_regla_8_22_2_solo_el_agronomo_a_cargo_cancela_aunque_la_haya_planificado_infoponia(self):
        """Regla 2 de 8.22 y «Permisos»: el Agrónomo a cargo del invernadero de la orden, aunque la planificó InfoPonia; el Gerente, un
        Capataz o un Agrónomo ajeno reciben `sin_permiso`."""
        de_infoponia = orden_de_siembra(self.e, plantines=5, sector="crecimiento", agronomo=False)
        for actor in (crear_gerente(), self.e.capataz, crear_agronomo(email="ajeno@infoponia.com")):
            with self.subTest(actor=actor):
                self.assertEqual(self.rechazo(actor=actor).codigo, "sin_permiso")
        self.assertEqual(self.cancelar(de_infoponia).estado_orden, "cancelada")
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.orden.pk).estado_orden, "a_realizar")  # las rechazadas no tocaron la otra

    def test_pre_a_una_orden_inexistente_da_404(self):
        """Un id inexistente da `Http404`."""
        with self.assertRaises(Http404):
            ordenes.cancelar_orden(self.e.agronomo, 999999, "x")

    def test_d67_punto_2_una_entrega_un_mantenimiento_o_una_cosecha_no_se_cancelan_con_esta_funcion(self):
        """D-67 punto 1 (punto 2 de «Tipos futuros»): `orden_no_cancelable` ANTES de bloquear nada y sin cambiar la orden ni sus reservas
        (la cosecha se cancela con `comercial.cancelar_cosecha`, D-64)."""
        for tipo in ("entrega", "mantenimiento", "cosecha"):
            with self.subTest(tipo=tipo):
                suelta = orden_suelta(self.e.invernadero, tipo, reservas=[(self.e.existencia_semilla, 3)])
                with mock.patch("produccion.servicios.ordenes.bloquear_invernadero_activo", side_effect=AssertionError("no tiene que bloquear nada")):
                    self.assertEqual(self.rechazo(suelta).codigo, "orden_no_cancelable")
                self.sin_cambios(suelta)

    def test_d67_las_dos_constantes_dicen_que_tipos_cancela_produccion(self):
        """D-67 punto 1: `cancelar_orden` acepta `TIPOS_QUE_CANCELA_PRODUCCION` (siembra y transición)."""
        self.assertEqual(ordenes.TIPOS_QUE_CANCELA_PRODUCCION, ("siembra", "transicion"))

    def test_ext_8a_una_orden_ya_concretada_o_cancelada_informa_su_estado(self):
        """Extensión 8a: si ya no está «a realizar», no cambia nada e informa el estado actual (`orden_no_pendiente`)."""
        concretada = orden_de_siembra(self.e, plantines=5, sector="crecimiento", estado="concretada", con_reserva=False)
        cancelada = orden_de_siembra(self.e, plantines=5, sector="floracion", estado="cancelada")
        for orden, estado in ((concretada, "concretada"), (cancelada, "cancelada")):
            with self.subTest(estado=estado):
                error = self.rechazo(orden)
                self.assertEqual(error.codigo, "orden_no_pendiente")
                self.assertIn(estado, error.mensaje)
        self.assertEqual(OrdenTrabajo.objects.get(pk=concretada.pk).estado_orden, "concretada")

    # ---- Motivo ----

    def test_ext_6a_el_motivo_es_obligatorio_y_los_espacios_no_cuentan(self):
        """Extensión 6a: vacío o solo espacios → `motivo_obligatorio` (campo motivo)."""
        for motivo in ("", "   ", "\n\t "):
            with self.subTest(motivo=repr(motivo)):
                error = self.rechazo(motivo=motivo)
                self.assertEqual((error.codigo, error.campo), ("motivo_obligatorio", "motivo"))
        self.sin_cambios()

    def test_regla_el_motivo_tiene_hasta_300_caracteres(self):
        """Paso 5 y modelo (`motivo_cancelacion`): 301 → `motivo_largo` (campo motivo); 300 pasa y queda entero."""
        error = self.rechazo(motivo="x" * 301)
        self.assertEqual((error.codigo, error.campo), ("motivo_largo", "motivo"))
        self.sin_cambios()
        self.assertEqual(self.cancelar(motivo="y" * 300).motivo_cancelacion, "y" * 300)

    # ---- Postcondiciones ----

    def test_post_a_la_orden_queda_cancelada_con_la_fecha_de_hoy_y_el_motivo(self):
        """Postcondición a y H2: «cancelada», `fecha_resolucion_orden` = hoy, `motivo_cancelacion` guardado (sin espacios al borde)."""
        devuelta = self.cancelar(motivo="  Se cambiaron los planes  ")
        orden = OrdenTrabajo.objects.get(pk=self.orden.pk)
        self.assertEqual((devuelta.pk, orden.estado_orden, orden.fecha_resolucion_orden, orden.motivo_cancelacion), (self.orden.pk, "cancelada", hoy(), "Se cambiaron los planes"))

    def test_post_b_cada_reserva_activa_queda_cancelada_sin_cantidades_y_deja_de_restar_del_stock_libre(self):
        """Postcondición b: reservas «canceladas», sin utilizada ni devuelta; su cantidad deja de restar del stock libre."""
        adicional = insumo_adicional(self.e, "Fertilizante", stock=50)
        reservar(self.orden, adicional, "7")
        self.cancelar()
        reservas = ReservaInsumo.objects.filter(orden=self.orden)
        self.assertEqual({(r.estado, r.cantidad_utilizada, r.cantidad_devuelta) for r in reservas}, {("cancelada", None, None)})
        from inventario.servicios import stock

        self.assertEqual(stock.existencias([self.e.existencia_semilla.pk])[self.e.existencia_semilla.pk].reservado, D("0"))

    def test_post_c_la_alerta_de_stock_inconsistente_que_queda_cubierta_se_resuelve(self):
        """Postcondición c: si el insumo tenía la alerta «stock inconsistente» y con la cancelación el stock cubre las reservas, pasa
        a «resuelta» con su fecha."""
        LoteInsumo.objects.filter(pk=self.e.lote_de_semillas.pk).update(cantidad_disponible=30)  # 30 de stock y 50 reservados
        alertas_de_stock.reevaluar_alertas_del_insumo(self.e.existencia_semilla.pk)
        alerta = Alerta.objects.get(tipo_alerta="inv_stock_inconsistente", clave_estado=f"insumo:{self.e.existencia_semilla.pk}")
        self.assertEqual(alerta.estado_alerta, "activa")
        self.cancelar()
        alerta.refresh_from_db()
        self.assertEqual((alerta.estado_alerta, timezone.localtime(alerta.fecha_resolucion).date()), ("resuelta", hoy()))

    def test_post_d_las_ocupaciones_se_conservan_y_los_agujeros_dejan_de_estar_comprometidos(self):
        """Postcondición d: las ocupaciones se conservan, sin lote y con cero ocupados, y lo planificado deja de contar como comprometido."""
        sector = self.e.sectores["germinacion"]
        self.assertEqual(api_sectores.agujeros_de([sector])[sector.pk].comprometidos, 50)
        self.cancelar()
        ocupacion = OcupacionSector.objects.get(orden=self.orden)
        self.assertEqual((ocupacion.cant_agujeros_planificados, ocupacion.cant_agujeros_ocupados, ocupacion.lote_id), (50, 0, None))
        agujeros = api_sectores.agujeros_de([sector])[sector.pk]
        self.assertEqual((agujeros.comprometidos, agujeros.ocupados, agujeros.libres), (0, 0, 100))

    def test_garantia_no_hay_consumos_ni_movimientos_ni_cambios_en_el_stock_ni_en_los_lotes(self):
        """Garantías mínimas: la cancelación no genera consumos ni movimientos de stock ni toca la cantidad de ningún lote."""
        movimientos = MovimientoInsumo.objects.count()
        self.cancelar()
        self.assertEqual((Consumo.objects.count(), Lote.objects.count(), MovimientoInsumo.objects.count()), (0, 0, movimientos))
        self.assertEqual(LoteInsumo.objects.get(pk=self.e.lote_de_semillas.pk).cantidad_disponible, D("1000"))

    # ---- Postcondición k: aviso al Capataz ----

    def test_post_k_el_capataz_recibe_la_cancelacion_con_el_motivo_entero(self):
        """Postcondición k y «Notificación»: título «Orden OT-… cancelada»; detalle «Motivo: …. Siembra del dd/mm/aaaa en … , cancelada por …»."""
        self.cancelar(motivo="Falló el riego")
        aviso = Notificacion.objects.get(destinatario=self.e.capataz)
        self.assertEqual(aviso.titulo, f"Orden {self.orden.codigo} cancelada")
        self.assertTrue(aviso.detalle.startswith("Motivo: Falló el riego. Siembra del "))
        self.assertIn(self.e.invernadero.nombre_invernadero, aviso.detalle)
        self.assertIn("cancelada por", aviso.detalle)
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_post_k_el_aviso_lleva_el_motivo_entero_aun_con_motivo_de_300_invernadero_de_80_y_nombre_largo(self):
        """Regla del largo: el detalle no pasa de 500; se acorta primero el nombre de quien cancela y después el del invernadero; el motivo no
        se recorta nunca y el aviso no hace fallar la cancelación."""
        motivo = "m" * 300
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(nombre_invernadero="I" * 80)
        type(self.e.agronomo).objects.filter(pk=self.e.agronomo.pk).update(first_name="N" * 100, last_name="A" * 50)
        agronomo = type(self.e.agronomo).objects.get(pk=self.e.agronomo.pk)
        ordenes.cancelar_orden(agronomo, self.orden.pk, motivo)
        aviso = Notificacion.objects.get(destinatario=self.e.capataz)
        self.assertLessEqual(len(aviso.detalle), 500)
        self.assertTrue(aviso.detalle.startswith(f"Motivo: {motivo}."))
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.orden.pk).estado_orden, "cancelada")

    def test_ext_9a_sin_capataz_activo_no_avisa_y_cancela_igual(self):
        """Extensión 9a: con el Capataz inactivo (o sin Capataz) no se notifica a nadie y la cancelación se registra igual."""
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.cancelar()
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.orden.pk).estado_orden, "cancelada")

    # ---- Extensión 8b ----

    def test_ext_8b_si_las_reservas_cambiaron_mientras_tanto_no_se_cancela_nada(self):
        """Extensión 8b: entre leer y bloquear cambió una reserva de la orden: no se registra nada y se informa (`cambio_simultaneo`)."""
        real = ordenes.bloquear_invernadero_activo

        def cambia_y_bloquea(invernadero_id):
            ReservaInsumo.objects.filter(orden=self.orden).update(cantidad_reservada=D("40"))
            return real(invernadero_id)

        with mock.patch("produccion.servicios.ordenes.bloquear_invernadero_activo", side_effect=cambia_y_bloquea):
            self.assertEqual(self.rechazo().codigo, "cambio_simultaneo")
        self.sin_cambios()

    # ---- Auditoría ----

    def test_post_m_n_un_solo_registro_con_la_orden_las_reservas_los_sectores_y_las_alertas(self):
        """Postcondiciones m y n (D-36): `cancelacion_orden` con la orden, sus reservas, sus sectores (cambio de «agujeros comprometidos»
        antes → después) y las alertas resueltas; el cambio de estado, fecha de resolución y motivo."""
        LoteInsumo.objects.filter(pk=self.e.lote_de_semillas.pk).update(cantidad_disponible=30)
        alertas_de_stock.reevaluar_alertas_del_insumo(self.e.existencia_semilla.pk)
        self.cancelar(motivo="Error de planificación")
        registro = RegistroAuditoria.objects.get(accion="cancelacion_orden")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_orden").count(), 1)
        self.assertEqual(registro.usuario_id, self.e.agronomo.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        reserva = ReservaInsumo.objects.get(orden=self.orden)
        self.assertLessEqual(
            {("produccion.siembra", self.orden.pk), ("produccion.reservainsumo", reserva.pk), ("maestros.sectorproduccion", self.e.sectores["germinacion"].pk)},
            afectados,
        )
        self.assertIn("maestros.alerta", {m for m, _ in afectados})
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["estado"], {"antes": "a_realizar", "despues": "cancelada"})
        self.assertEqual(cambios["fecha_resolucion_orden"]["despues"], f"{hoy():%d/%m/%Y}")
        self.assertEqual(cambios["motivo_cancelacion"], {"antes": None, "despues": "Error de planificación"})
        sector = self.e.sectores["germinacion"].nombre_sector
        self.assertEqual(cambios["agujeros_comprometidos"], {"antes": [f"{sector}: 50"], "despues": [f"{sector}: 0"]})
        self.assertEqual(len(registro.detalle["datos"]["alertas_resueltas"]), 1)

    # ---- Todo o nada ----

    def test_garantia_si_falla_el_aviso_no_queda_nada(self):
        """Garantías mínimas y D-22: si el aviso falla, la orden sigue «a realizar», las reservas «activas» y no queda registro."""
        with mock.patch("core.notificaciones.notificar_a_varios", side_effect=RuntimeError("falla del aviso")):
            with self.assertRaises(RuntimeError):
                self.cancelar()
        self.sin_cambios()
        sector = self.e.sectores["germinacion"]
        self.assertEqual(api_sectores.agujeros_de([sector])[sector.pk].comprometidos, 50)


# ============================================================================================================================
# PRD-02, paso 6: la cancelación de una TRANSICIÓN (extensión 4a de PROD-CNL-ORD)
# ============================================================================================================================
# `cancelar_orden` y `cancelar_orden_incluida` ya existen (PRD-01): acá se completan para `TransicionEtapa`. Sin reservas de insumo; el lote
# conserva su etapa, su fecha de entrada y su cantidad, y queda sin transición «a realizar» (puede planificarse otra). El resumen suma el
# lote y sus etapas (`lote`, `etapa_origen`, `etapa_destino`: nombres; `None` en una siembra).


class CancelarTransicionTests(ConDatosDeInventario, TestCase):
    """Una transición «a realizar» de un lote de 50 plantas en Crecimiento hacia el sector de Floración."""

    def setUp(self):
        self.e = invernadero_con_produccion()
        self.lote = lote_con_ciclo(self.e, cantidad=50, costo="100.00")
        self.orden = orden_de_transicion(self.e, self.lote)
        self.destino = self.e.sectores["floracion"]

    def cancelar(self, actor=None, motivo="Se cambiaron los planes", orden=None):
        return ordenes.cancelar_orden(actor or self.e.agronomo, (orden or self.orden).pk, motivo)

    def rechazo(self, **cambios):
        return rechazo(lambda: self.cancelar(**cambios))

    def sin_cambios(self):
        """La transición sigue «a realizar», sin notificaciones ni registro de auditoría de la cancelación."""
        orden = TransicionEtapa.objects.get(pk=self.orden.pk)
        self.assertEqual((orden.estado_orden, orden.fecha_resolucion_orden, orden.motivo_cancelacion), ("a_realizar", None, None))
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="cancelacion_orden").exists())

    def test_ext_4a_el_resumen_presenta_el_lote_sus_etapas_y_los_sectores_destino_sin_reservas(self):
        """Extensión 4a: presenta el lote, su etapa actual y la etapa destino, y los sectores destino con los agujeros comprometidos que
        se liberan; informa que la transición no tiene reservas de insumo."""
        resumen = ordenes.resumen_de_cancelacion(self.e.agronomo, self.orden.pk)
        self.assertEqual((resumen.lote.pk, resumen.etapa_origen, resumen.etapa_destino), (self.lote.pk, "Crecimiento", "Floración"))
        self.assertEqual([(s.pk, n) for s, n in resumen.sectores], [(self.destino.pk, 50)])
        self.assertEqual(resumen.reservas, [])
        self.sin_cambios()

    def test_ext_4a_el_resumen_de_una_siembra_no_trae_lote_ni_etapas(self):
        """Una siembra no tiene lote ni etapa destino: los tres campos nuevos del resumen valen `None`."""
        siembra = orden_de_siembra(self.e, plantines=5)
        resumen = ordenes.resumen_de_cancelacion(self.e.agronomo, siembra.pk)
        self.assertEqual((resumen.lote, resumen.etapa_origen, resumen.etapa_destino), (None, None, None))

    def test_regla_8_22_2_solo_el_agronomo_a_cargo_cancela_aunque_la_haya_planificado_infoponia(self):
        """Regla 2 de 8.22: el Agrónomo a cargo cancela la transición aunque la haya planificado InfoPonia; otro rol, no (`sin_permiso`);
        el Gerente no cancela."""
        TransicionEtapa.objects.filter(pk=self.orden.pk).update(agronomo=None)
        for actor in (crear_gerente(), self.e.capataz, crear_agronomo(email="ajeno@infoponia.com")):
            with self.subTest(actor=actor):
                self.assertEqual(self.rechazo(actor=actor).codigo, "sin_permiso")
        self.sin_cambios()
        self.assertEqual(self.cancelar().estado_orden, "cancelada")

    def test_post_a_la_transicion_queda_cancelada_con_la_fecha_de_hoy_y_el_motivo(self):
        """Postcondición a: «cancelada», con la fecha actual como fecha de resolución y el motivo indicado; sin cantidad transferida ni
        fecha efectiva."""
        self.cancelar(motivo="El sector no está listo")
        orden = TransicionEtapa.objects.get(pk=self.orden.pk)
        self.assertEqual((orden.estado_orden, orden.fecha_resolucion_orden, orden.motivo_cancelacion), ("cancelada", hoy(), "El sector no está listo"))
        self.assertEqual((orden.cant_transferido, orden.fecha_transicion), (None, None))

    def test_post_b_la_transicion_no_tiene_reservas_ni_toca_el_stock(self):
        """Postcondición b: la transición no reserva insumos; cancelarla no genera consumos ni movimientos ni cambia el stock."""
        movimientos = MovimientoInsumo.objects.count()
        self.cancelar()
        self.assertEqual((ReservaInsumo.objects.filter(orden=self.orden).count(), Consumo.objects.count()), (0, 0))
        self.assertEqual(MovimientoInsumo.objects.count(), movimientos)
        self.assertEqual(LoteInsumo.objects.get(pk=self.e.lote_de_semillas.pk).cantidad_disponible, D("1000"))

    def test_post_d_las_ocupaciones_se_conservan_sin_lote_y_los_agujeros_dejan_de_estar_comprometidos(self):
        """Postcondición d: las ocupaciones destino se conservan, sin lote y con cero ocupados, y lo planificado deja de contar como
        comprometido en cada sector."""
        self.assertEqual(api_sectores.agujeros_de([self.destino])[self.destino.pk].comprometidos, 50)
        self.cancelar()
        ocupacion = OcupacionSector.objects.get(orden=self.orden)
        self.assertEqual((ocupacion.cant_agujeros_planificados, ocupacion.cant_agujeros_ocupados, ocupacion.lote_id), (50, 0, None))
        agujeros = api_sectores.agujeros_de([self.destino])[self.destino.pk]
        self.assertEqual((agujeros.comprometidos, agujeros.ocupados, agujeros.libres), (0, 0, 100))

    def test_post_e_el_lote_conserva_su_etapa_su_fecha_de_entrada_y_sus_plantas_y_puede_recibir_otra_transicion(self):
        """Postcondición e: el lote conserva su etapa y su fecha de entrada a la etapa, y queda sin transición «a realizar»: vuelve a
        ser trasladable y se puede planificar otra."""
        entrada = api_lotes.fecha_de_entrada_a_la_etapa(Lote.objects.get(pk=self.lote.pk))
        antes = Lote.objects.values_list("etapa_id", "cantidad_actual", "costo_acumulado").get(pk=self.lote.pk)
        self.cancelar()
        lote = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual((lote.etapa_id, lote.cantidad_actual, lote.costo_acumulado), antes)
        self.assertEqual(api_lotes.fecha_de_entrada_a_la_etapa(lote), entrada)
        self.assertEqual(
            {f.lote_id: f.motivo for f in transiciones.lotes_trasladables(self.e.agronomo)}[self.lote.pk], None
        )
        nueva = transiciones.planificar_transicion(self.e.agronomo, datos_de_planificacion(self.e, lote))
        self.assertEqual(nueva.estado_orden, "a_realizar")
        self.assertEqual(TransicionEtapa.objects.filter(lote=lote, estado_orden="a_realizar").count(), 1)

    def test_post_k_el_capataz_recibe_la_cancelacion_con_el_motivo_y_el_tipo_de_orden(self):
        """Postcondición k y «Notificación»: título «Orden OT-… cancelada»; detalle «Motivo: …. Transición de etapa del dd/mm/aaaa en …,
        cancelada por …»; sin Capataz activo no avisa y cancela igual (extensión 9a)."""
        self.cancelar(motivo="Falló el riego")
        aviso = Notificacion.objects.get(destinatario=self.e.capataz)
        self.assertEqual(aviso.titulo, f"Orden {self.orden.codigo} cancelada")
        self.assertTrue(aviso.detalle.startswith("Motivo: Falló el riego. Transición de etapa del "))
        self.assertIn(self.e.invernadero.nombre_invernadero, aviso.detalle)
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_ext_9a_sin_capataz_activo_no_avisa_y_cancela_igual(self):
        """Extensión 9a: con el Capataz inactivo no se notifica a nadie y la cancelación se registra igual."""
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.cancelar()
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "cancelada")

    def test_ext_8a_una_transicion_ya_concretada_o_cancelada_informa_su_estado(self):
        """Extensión 8a: una transición que ya no está «a realizar» se rechaza con `orden_no_pendiente` y su estado actual."""
        otra = lote_con_ciclo(self.e, cantidad=5)
        concretada = orden_de_transicion(self.e, otra, estado="concretada")
        error = self.rechazo(orden=concretada)
        self.assertEqual(error.codigo, "orden_no_pendiente")
        self.assertIn("concretada", error.mensaje)
        self.cancelar()
        self.assertIn("cancelada", self.rechazo().mensaje)

    def test_ext_6a_el_motivo_es_obligatorio_y_de_hasta_300_caracteres(self):
        """Extensión 6a: sin motivo, `motivo_obligatorio`; de 301, `motivo_largo`; no cambia nada."""
        self.assertEqual(self.rechazo(motivo="   ").codigo, "motivo_obligatorio")
        self.assertEqual(self.rechazo(motivo="m" * 301).codigo, "motivo_largo")
        self.sin_cambios()

    def test_post_m_n_un_solo_registro_con_la_transicion_el_lote_y_los_sectores(self):
        """Postcondiciones m y n (D-36): `cancelacion_orden` con la transición y sus sectores (cambio de «agujeros comprometidos»
        antes → después) y el cambio de estado, fecha de resolución y motivo. El lote no cambia: no es un afectado."""
        self.cancelar(motivo="Error de planificación")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_orden").count(), 1)
        registro = RegistroAuditoria.objects.get(accion="cancelacion_orden")
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        self.assertLessEqual({("produccion.transicionetapa", self.orden.pk), ("maestros.sectorproduccion", self.destino.pk)}, afectados)
        self.assertNotIn(("produccion.lote", self.lote.pk), afectados)
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["estado"], {"antes": "a_realizar", "despues": "cancelada"})
        self.assertEqual(cambios["motivo_cancelacion"], {"antes": None, "despues": "Error de planificación"})
        self.assertEqual(
            cambios["agujeros_comprometidos"],
            {"antes": [f"{self.destino.nombre_sector}: 50"], "despues": [f"{self.destino.nombre_sector}: 0"]},
        )

    def test_garantia_si_falla_el_aviso_no_queda_nada(self):
        """Garantías mínimas y D-22: si el aviso falla, la transición sigue «a realizar», sus agujeros comprometidos y no queda registro."""
        with mock.patch("core.notificaciones.notificar_a_varios", side_effect=RuntimeError("falla del aviso")):
            with self.assertRaises(RuntimeError):
                self.cancelar()
        self.sin_cambios()
        self.assertEqual(api_sectores.agujeros_de([self.destino])[self.destino.pk].comprometidos, 50)

    def test_garantia_cancelar_una_transicion_no_cancela_la_siembra_ni_cambia_el_resto_de_las_ordenes(self):
        """Solo cambia la orden pedida: otra transición «a realizar» y una siembra «a realizar» siguen igual."""
        siembra = orden_de_siembra(self.e, plantines=5)
        otra = orden_de_transicion(self.e, lote_con_ciclo(self.e, cantidad=5))
        self.cancelar()
        self.assertEqual(OrdenTrabajo.objects.get(pk=siembra.pk).estado_orden, "a_realizar")
        self.assertEqual(OrdenTrabajo.objects.get(pk=otra.pk).estado_orden, "a_realizar")
