# Pruebas de `cancelar_orden_incluida` (PRD-01, paso 7; docs/api/produccion.md, sección 1 y sección 9; docs/casos_de_uso/produccion/
# cancelar_orden.md, «Ejecución desde los casos de uso que lo incluyen»; D-67 punto 1, punto 3 de «Tipos futuros»).
#
# `ordenes.cancelar_orden_incluida(actor, orden, motivo, *, avisar=False) -> CancelacionIncluida(orden, reservas, sectores_afectados,
# alertas_resueltas, notificar_a)` es para un caso de uso que INCLUYE la cancelación de una orden (PRD-04: sector fuera de servicio;
# COM-05a1: la entrega; IOT-07: el mantenimiento). Corre en la transacción de su llamador (el llamador ya tiene bloqueados el invernadero,
# la variedad y los sectores), NO abre una propia, NO audita y NO notifica: devuelve lo que el llamador necesita para su único
# registro de auditoría y a quién avisar. `actor` puede ser `None` (cancela InfoPonia). Acepta CUALQUIER tipo de orden: no da por hecho
# que tenga Capataz ni sectores, y funciona con o sin reservas de insumo. Estas pruebas usan órdenes sueltas de entrega y de
# mantenimiento (`orden_suelta`): sus hijas llegan con COM-05a1 e IOT-07 y las pruebas siguen valiendo sin cambios.

from decimal import Decimal
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import Capataz, Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario, perezoso
from produccion.errores import ErrorDeProduccion
from maestros.servicios import sectores as api_sectores
from produccion.models import Lote, OrdenTrabajo, ReservaInsumo, TransicionEtapa
from produccion.tests.fabricas import (
    insumo_adicional,
    invernadero_con_produccion,
    lote_con_ciclo,
    orden_de_siembra,
    orden_de_transicion,
    orden_suelta,
)

ordenes = perezoso("produccion.servicios.ordenes")
D = Decimal


def hoy():
    return timezone.localdate()


class Base(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = invernadero_con_produccion()

    def incluir(self, orden, motivo="Sector fuera de servicio: Germ 1. Se rompió el riego", actor=None, **opciones):
        return ordenes.cancelar_orden_incluida(actor, orden, motivo, **opciones)

    def recargada(self, orden):
        return OrdenTrabajo.objects.get(pk=orden.pk)


class CancelarOrdenIncluidaDeSiembraTests(Base):
    def setUp(self):
        super().setUp()
        self.orden = orden_de_siembra(self.e, plantines=50)

    def test_regla_con_actor_none_cancela_y_devuelve_lo_que_necesita_el_llamador(self):
        """«Ejecución desde los casos de uso que lo incluyen»: con `actor=None` (InfoPonia) la orden queda cancelada con su fecha y su
        motivo, las reservas «canceladas» sin cantidades, y se devuelven la orden, las reservas y los sectores con su cambio de comprometidos."""
        resultado = self.incluir(self.orden)
        orden = self.recargada(self.orden)
        self.assertEqual((orden.estado_orden, orden.fecha_resolucion_orden, orden.motivo_cancelacion), ("cancelada", hoy(), "Sector fuera de servicio: Germ 1. Se rompió el riego"))
        self.assertEqual(resultado.orden.pk, self.orden.pk)
        self.assertEqual([(r.estado, r.cantidad_utilizada, r.cantidad_devuelta) for r in resultado.reservas], [("cancelada", None, None)])
        self.assertEqual([(a.sector.pk, a.antes, a.despues) for a in resultado.sectores_afectados], [(self.e.sectores["germinacion"].pk, 50, 0)])
        self.assertEqual(resultado.alertas_resueltas, [])

    def test_regla_el_aviso_al_capataz_solo_si_se_pide_y_esta_activo(self):
        """`notificar_a`: el Capataz si `avisar=True` y está activo; con `avisar=False` (el valor por omisión), nadie. La función NO notifica."""
        self.assertEqual(self.incluir(self.orden).notificar_a, [])
        otra = orden_de_siembra(self.e, plantines=5, sector="crecimiento")
        self.assertEqual([c.pk for c in self.incluir(otra, avisar=True).notificar_a], [self.e.capataz.pk])
        inactivo = orden_de_siembra(self.e, plantines=5, sector="floracion")
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.assertEqual(self.incluir(inactivo, avisar=True).notificar_a, [])
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_regla_no_audita_ni_abre_una_transaccion_propia(self):
        """«Corre en la transacción del llamador y no audita ni notifica por su cuenta» (API, sección 1, y D-36: un registro por caso de uso)."""
        with mock.patch("produccion.servicios.ordenes.transaction.atomic", side_effect=AssertionError("no abre una transacción propia")):
            self.incluir(self.orden)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_un_motivo_de_mas_de_300_se_recorta_con_puntos_suspensivos_sin_fallar(self):
        """Regla «Desde otro caso de uso»: el motivo ya armado se recorta a 300 con «…» (el «…» cuenta dentro de los 300); no lanza `motivo_largo`."""
        self.incluir(self.orden, motivo="m" * 450)
        motivo = self.recargada(self.orden).motivo_cancelacion
        self.assertEqual((len(motivo), motivo[-1], motivo[:299]), (300, "…", "m" * 299))

    def test_ext_8a_una_orden_que_ya_no_esta_a_realizar_lanza_orden_no_pendiente(self):
        """«Cancela solo órdenes «a realizar»»: si ya no lo está, `orden_no_pendiente` (el llamador decide) y no cambia nada."""
        concretada = orden_de_siembra(self.e, plantines=5, sector="crecimiento", estado="concretada", con_reserva=False)
        with self.assertRaises(ErrorDeProduccion) as contexto:
            self.incluir(concretada)
        self.assertEqual(contexto.exception.codigo, "orden_no_pendiente")
        self.assertEqual(self.recargada(concretada).estado_orden, "concretada")

    def test_regla_con_dos_reservas_cancela_las_dos_y_resuelve_las_alertas_cubiertas(self):
        """Postcondiciones b y c, también desde otro caso de uso: todas las reservas activas pasan a «cancelada»."""
        adicional = insumo_adicional(self.e, "Fertilizante", stock=50)
        from produccion.tests.fabricas import reservar

        reservar(self.orden, adicional, "7")
        resultado = self.incluir(self.orden)
        self.assertEqual({r.estado for r in resultado.reservas}, {"cancelada"})
        self.assertEqual(ReservaInsumo.objects.filter(orden=self.orden, estado="activa").count(), 0)


class CancelarOrdenIncluidaDeCualquierTipoTests(Base):
    """D-67 punto 1 (punto 3 de «Tipos futuros»): acepta cualquier tipo, sin dar por hecho Capataz ni sectores."""

    def test_d67_una_entrega_suelta_con_dos_reservas_se_cancela_sin_consumo_sin_sectores_y_sin_capataz(self):
        """Una entrega suelta con dos reservas de insumo queda cancelada, con sus reservas «canceladas» y sin consumo; `sectores_afectados` y
        `notificar_a` quedan vacíos aunque `avisar=True` (la entrega no tiene Capataz)."""
        adicional = insumo_adicional(self.e, "Envase", stock=50, unidad="unidad")
        entrega = orden_suelta(self.e.invernadero, "entrega", reservas=[(self.e.existencia_semilla, 3), (adicional, 2)])
        resultado = self.incluir(entrega, actor=self.e.agronomo, avisar=True)
        self.assertEqual(self.recargada(entrega).estado_orden, "cancelada")
        self.assertEqual({(r.estado, r.cantidad_utilizada, r.cantidad_devuelta) for r in resultado.reservas}, {("cancelada", None, None)})
        self.assertEqual(len(resultado.reservas), 2)
        self.assertEqual((resultado.sectores_afectados, resultado.notificar_a), ([], []))

    def test_d67_un_mantenimiento_suelto_sin_reservas_devuelve_reservas_vacio(self):
        """Un mantenimiento suelto sin reservas de insumo: se cancela y `reservas` queda vacío."""
        mantenimiento = orden_suelta(self.e.invernadero, "mantenimiento")
        resultado = self.incluir(mantenimiento, avisar=True)
        self.assertEqual(self.recargada(mantenimiento).estado_orden, "cancelada")
        self.assertEqual((resultado.reservas, resultado.sectores_afectados, resultado.notificar_a), ([], [], []))

    def test_d67_ninguna_de_las_dos_consulta_las_ocupaciones_de_sector(self):
        """Punto 3 de «Tipos futuros»: una orden sin sectores no consulta ocupaciones de más (ni la tabla de ocupaciones ni la de las hijas
        con Capataz)."""
        entrega = orden_suelta(self.e.invernadero, "entrega", reservas=[(self.e.existencia_semilla, 3)])
        mantenimiento = orden_suelta(self.e.invernadero, "mantenimiento")
        for orden in (entrega, mantenimiento):
            with self.subTest(tipo=orden.tipo_orden), CaptureQueriesContext(connection) as consultas:
                self.incluir(orden, avisar=True)
            sql = " ".join(q["sql"] for q in consultas)
            self.assertNotIn("produccion_ocupacionsector", sql)
            self.assertNotIn("produccion_siembra", sql)

    def test_d67_cualquier_tipo_se_cancela_y_no_se_audita(self):
        """Ningún tipo audita ni notifica por su cuenta."""
        for tipo in ("entrega", "mantenimiento", "cosecha"):
            with self.subTest(tipo=tipo):
                self.incluir(orden_suelta(self.e.invernadero, tipo), avisar=True)
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), (0, 0))


class CancelarOrdenIncluidaDeTransicionTests(ConDatosDeInventario, TestCase):
    """PRD-02, paso 6: `cancelar_orden_incluida` con una transición (la usará PRD-04, PROD-PNR-FDS, que cancela las órdenes que
    comprometían el sector): sin reservas, con sus sectores destino y con el Capataz de su hija."""

    def setUp(self):
        self.e = invernadero_con_produccion()
        self.lote = lote_con_ciclo(self.e, cantidad=50)
        self.orden = orden_de_transicion(self.e, self.lote)
        self.destino = self.e.sectores["floracion"]

    def incluir(self, motivo="Sector fuera de servicio: Floración. Se rompió el riego", actor=None, **opciones):
        return ordenes.cancelar_orden_incluida(actor, self.orden, motivo, **opciones)

    def test_regla_con_actor_none_cancela_la_transicion_y_devuelve_sus_sectores_sin_reservas(self):
        """«Ejecución desde los casos de uso que lo incluyen»: con `actor=None` la transición queda cancelada con su fecha y su motivo; no
        hay reservas; los sectores traen el cambio de agujeros comprometidos (50 → 0) para el registro del llamador."""
        resultado = self.incluir()
        orden = TransicionEtapa.objects.get(pk=self.orden.pk)
        self.assertEqual((orden.estado_orden, orden.fecha_resolucion_orden), ("cancelada", hoy()))
        self.assertEqual(resultado.orden.pk, self.orden.pk)
        self.assertEqual(resultado.reservas, [])
        self.assertEqual([(a.sector.pk, a.antes, a.despues) for a in resultado.sectores_afectados], [(self.destino.pk, 50, 0)])

    def test_regla_el_aviso_al_capataz_de_la_transicion_solo_si_se_pide_y_esta_activo(self):
        """El Capataz sale de la hija `TransicionEtapa` (D-53): con `avisar=False` no se avisa a nadie; con `avisar=True` y Capataz
        activo, `notificar_a` lo trae; inactivo, vacío. La función no notifica por su cuenta."""
        self.assertEqual(self.incluir(avisar=False).notificar_a, [])
        otra = orden_de_transicion(self.e, lote_con_ciclo(self.e, cantidad=5))
        self.assertEqual([c.pk for c in ordenes.cancelar_orden_incluida(None, otra, "Sector fuera de servicio", avisar=True).notificar_a], [self.e.capataz.pk])
        self.assertEqual(Notificacion.objects.count(), 0)
        tercera = orden_de_transicion(self.e, lote_con_ciclo(self.e, cantidad=5))
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.assertEqual(ordenes.cancelar_orden_incluida(None, tercera, "Sector fuera de servicio", avisar=True).notificar_a, [])

    def test_regla_no_audita_no_toca_el_lote_y_libera_los_agujeros(self):
        """No audita (lo hace el llamador en su único registro); el lote conserva etapa, cantidad y costo; los agujeros dejan de estar
        comprometidos."""
        antes = Lote.objects.values_list("etapa_id", "cantidad_actual", "costo_acumulado").get(pk=self.lote.pk)
        self.incluir()
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_orden").count(), 0)
        self.assertEqual(Lote.objects.values_list("etapa_id", "cantidad_actual", "costo_acumulado").get(pk=self.lote.pk), antes)
        self.assertEqual(api_sectores.agujeros_de([self.destino])[self.destino.pk].comprometidos, 0)

    def test_ext_8a_una_transicion_que_ya_no_esta_a_realizar_lanza_orden_no_pendiente(self):
        """Extensión 8a: si el llamador la encuentra cancelada, `orden_no_pendiente` (el llamador decide)."""
        self.incluir()
        with self.assertRaises(ErrorDeProduccion) as rechazo_:
            self.incluir()
        self.assertEqual(rechazo_.exception.codigo, "orden_no_pendiente")
