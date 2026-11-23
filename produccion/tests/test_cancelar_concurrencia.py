# Pruebas de concurrencia de PROD-CNL-ORD (PRD-01, paso 7; docs/patrones/bloqueos.md, sección `produccion`): cancelar contra concretar y
# cancelar dos veces. Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py); son ``TransactionTestCase``
# (el ``flush`` vacía los tipos de etapa, las categorías y Georef: cada prueba arma su invernadero con geografía propia y asegura los
# datos en ``setUp``). Garantías mínimas del CU: «solo se cancelan órdenes a realizar; una orden concretada o cancelada nunca cambia de
# estado, aun cuando se cancela y se concreta al mismo tiempo».
# PRD-02 suma al final las de la cancelación de una transición (incluida «cancelar contra planificar otra transición del mismo lote»).

from decimal import Decimal

from django.test import TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from inventario.models import LoteInsumo
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, perezoso
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Lote, OrdenTrabajo, ReservaInsumo, TransicionEtapa
from produccion.servicios import transiciones
from produccion.tests.fabricas import (
    codigos_del_rechazo,
    invernadero_con_produccion,
    lote_con_ciclo,
    orden_de_siembra,
    orden_de_transicion,
    separar,
)
from produccion.tests.test_prod_pnf_trn import datos as datos_de_planificacion

ordenes = perezoso("produccion.servicios.ordenes")
siembras = perezoso("produccion.servicios.siembras")


@tag("concurrencia")
class CancelarOrdenConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de `cancelar_orden`: cuentas → invernadero → variedad → sectores → insumos → la orden y sus reservas."""

    def setUp(self):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = invernadero_con_produccion(geografia_propia=True)
        self.orden = orden_de_siembra(self.e, plantines=50)

    def cancelar(self):
        return lambda: ordenes.cancelar_orden(self.e.agronomo, self.orden.pk, "Se cambiaron los planes")

    def concretar(self):
        return lambda: siembras.concretar_siembra(self.e.capataz, self.orden.pk, siembras.DatosDeConcrecion())

    def test_garantia_concretar_primero_la_cancelacion_espera_y_ve_la_orden_concretada(self):
        """Extensión 8a: la cancelación espera a la concreción (los dos toman antes el invernadero), relee la orden «concretada» y se
        rechaza con `orden_no_pendiente`. La orden NO pasa de «concretada» a «cancelada»; queda su lote y su stock descontado."""
        resultados = correr_a_la_vez(self.concretar(), self.cancelar(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["orden_no_pendiente"])
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.orden.pk).estado_orden, "concretada")
        self.assertEqual(Lote.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_orden").count(), 0)

    def test_garantia_cancelar_primero_la_concrecion_espera_y_ve_la_orden_cancelada(self):
        """Extensión 19a de PROD-CNC-SMB: si la cancelación confirma primero, la concreción relee la orden «cancelada» y se rechaza con
        `orden_no_pendiente` y el estado actual. No hay lote ni descuento de stock."""
        resultados = correr_a_la_vez(self.cancelar(), self.concretar(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["orden_no_pendiente"])
        self.assertIn("cancelada", rechazos[0].mensaje)
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.orden.pk).estado_orden, "cancelada")
        self.assertEqual(Lote.objects.count(), 0)
        self.assertEqual(LoteInsumo.objects.get(pk=self.e.lote_de_semillas.pk).cantidad_disponible, Decimal("1000"))
        self.assertEqual(ReservaInsumo.objects.get(orden=self.orden).estado, "cancelada")

    def test_garantia_cancelar_dos_veces_la_segunda_se_rechaza_y_queda_un_solo_registro(self):
        """Dos cancelaciones simultáneas de la misma orden: la segunda espera, ve la orden ya «cancelada» y se rechaza con
        `orden_no_pendiente`. Un solo registro de auditoría y un solo aviso."""
        resultados = correr_a_la_vez(self.cancelar(), self.cancelar(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["orden_no_pendiente"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_orden").count(), 1)


@tag("concurrencia")
class CancelarTransicionConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """PRD-02, paso 6: bloqueos de `cancelar_orden` con una transición: cuentas → invernadero → variedad del lote → sectores destino → lote
    → la orden. «Concretar contra cancelar» está en `test_transiciones_concurrencia.py`."""

    def setUp(self):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = invernadero_con_produccion(geografia_propia=True)
        self.lote = lote_con_ciclo(self.e, cantidad=10)
        self.orden = orden_de_transicion(self.e, self.lote)

    def cancelar(self):
        return lambda: ordenes.cancelar_orden(self.e.agronomo, self.orden.pk, "Se cambiaron los planes")

    def planificar_otra(self):
        return lambda: transiciones.planificar_transicion(self.e.agronomo, datos_de_planificacion(self.e, self.lote))

    def test_garantia_cancelar_primero_planificar_otra_del_mismo_lote_espera_y_la_planifica(self):
        """Regla 4 de 8.21 (disparador «Cuando exista TransicionEtapa», punto 3): si la cancelación confirma primero, planificar otra
        transición del mismo lote espera, relee el lote (ya sin transición «a realizar») y la planifica. Las dos pasan; al final el lote
        tiene una sola «a realizar» (la nueva) y la vieja queda cancelada. Ninguna se rechaza de más por haber leído antes la orden vieja."""
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(), self.planificar_otra(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "cancelada")
        self.assertEqual(TransicionEtapa.objects.filter(lote=self.lote, estado_orden="a_realizar").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="planificacion_transicion").count(), 1)
        sector = self.e.sectores["floracion"]
        self.assertEqual(api_sectores.agujeros_de([sector])[sector.pk].comprometidos, 10)

    def test_garantia_cancelar_dos_veces_la_segunda_se_rechaza_y_queda_un_solo_registro(self):
        """Dos cancelaciones simultáneas de la misma transición: la segunda espera, ve la orden ya «cancelada» y se rechaza con
        `orden_no_pendiente`. Un solo registro de auditoría y un solo aviso."""
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(), self.cancelar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["orden_no_pendiente"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_orden").count(), 1)
        self.assertEqual(api_sectores.agujeros_de([self.e.sectores["floracion"]])[self.e.sectores["floracion"].pk].comprometidos, 0)
