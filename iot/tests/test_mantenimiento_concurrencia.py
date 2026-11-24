# Pruebas de concurrencia de las órdenes de mantenimiento del IoT (IOT-07, paso 8; docs/casos_de_uso/iot/mantenimiento_automatico.md, «Bloqueos»; docs/patrones/bloqueos.md; D-73; D-78, punto 11; D-79):
# (a) cancelar una orden desde la ficha y volver a activar el equipo a la vez, (b) dos cancelaciones, (c) el traspaso del Técnico (PROD-MOD-INV) y una cancelación, y (d) el escalamiento de un
# comando y la cancelación de la orden anterior del mismo actuador. Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). ``TransactionTestCase``: su ``flush``
# vacía todas las tablas al terminar, así que cada prueba vuelve a asegurar los datos en ``setUp`` (docs/patrones/datos_de_migracion.md) y limpia la caché.
#
# Orden de bloqueo de las operaciones de esta tarea (sin tipo de actuador: D-82 no aplica):
#   cancelar:        cuentas (actor y Técnico) → invernadero → sistemas y equipos de la orden → orden (y reservas).
#   volver a activar: cuentas → invernadero → sistemas → equipo y demás equipos de las órdenes → órdenes.
#   traspaso:        cuentas → invernadero → órdenes «a realizar» (en orden de id).
#   escalamiento:    invernadero → sistema → nodo → actuador → comando → la orden existente del actuador.
# Las pruebas con barrera (``detener_antes_de``) detienen a una operación justo ANTES de bloquear el invernadero y dejan correr entera a la otra: con este orden las dos terminan; con el invertido
# (la orden antes que el invernadero) la base detecta el ciclo y aborta una (``DeadlockDetected``).

from datetime import datetime, timedelta, timezone

from django.core.cache import cache
from django.test import TransactionTestCase, tag

from core.models import Notificacion, RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from iot.models import Comando, Hardware, MantenimientoTecnico, NodoCentral
from iot.servicios import comandos, hardware, mantenimiento
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion, invernaderos
from maestros.tests.fabricas import crear_agronomo, crear_invernadero_con_geografia_propia, crear_tecnico
from maestros.tests.test_prod_mod_inv import datos_de

AHORA = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
ANTES_DEL_INVERNADERO = (api_alertas, "bloquear_invernadero_para_alertas")
MOTIVO = "El equipo se reemplazó."


@tag("concurrencia")
class MantenimientoConcurrenciaTests(fabricas.ConCatalogoIot, TransactionTestCase):
    """Cancelar, volver a activar, traspasar y escalar a la vez."""

    def setUp(self):
        cache.clear()
        fabricas.asegurar_datos_de_iot()
        from maestros.tests.fabricas import asegurar_datos_de_maestros

        asegurar_datos_de_maestros()
        self.enterContext(fabricas.con_iot_registrado())
        configuracion.obtener()
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.tecnico = crear_tecnico("tecnico@infoponia.com", nombre="Tomás", apellido="Quiroga")
        self.nuevo = crear_tecnico("nuevo@infoponia.com", nombre="Nora", apellido="Paz")
        self.norte = crear_invernadero_con_geografia_propia("Norte", agronomo=self.laura, tecnico=self.tecnico)
        self.sistema = fabricas.sistema(self.norte)
        NodoCentral.objects.filter(sistema=self.sistema).update(ultima_comunicacion=AHORA - timedelta(seconds=30))
        self.tipo = fabricas.tipo_actuador("Extractor")
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/extractor", estado="fuera_de_servicio", ultimo_mensaje_en=AHORA - timedelta(hours=1))
        self.encender = self.tipo.acciones.order_by("id").first()
        self.orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])

    # ---- ayudas ----

    def cancelar(self, orden=None):
        return lambda: mantenimiento.cancelar_mantenimiento(self.laura, (orden or self.orden).pk, MOTIVO)

    def volver_a_activar(self, decision="cancelar"):
        return lambda: hardware.volver_a_activar(self.laura, self.actuador.pk, {self.orden.pk: decision})

    def traspasar(self):
        """El Gerente asigna a ``nuevo`` como Técnico de Norte (con la ventana de confirmación ya aceptada)."""
        return lambda: invernaderos.modificar_invernadero(
            self.gerente, self.norte.pk, **(datos_de(self.norte) | {"tecnico_id": self.nuevo.pk, "personal_confirmado": True})
        )

    def escalar(self):
        """El nodo informa «falló» en el último intento de un comando del actuador."""
        Hardware.objects.filter(pk=self.actuador.pk).update(estado_hardware="activo")  # el escalamiento lo pasa a «fuera de servicio»
        comando = fabricas.comando(self.actuador, self.encender, agronomo=self.laura)
        Comando.objects.filter(pk=comando.pk).update(cantidad_intentos=4, ultimo_intento_en=AHORA - timedelta(seconds=10))
        informe = comandos.ResultadoRecibido(resultado="fallo", detalle="Sin corriente", estado=None, informado_en=None)
        return lambda: comandos.registrar_resultado(self.sistema.pk, comando.pk, informe, AHORA)

    def a_realizar(self):
        return MantenimientoTecnico.objects.filter(estado_orden="a_realizar")

    # ---- (a) cancelar desde la ficha y volver a activar el equipo a la vez ----

    def test_regla_8_si_la_cancelacion_va_primero_volver_a_activar_recibe_ordenes_cambiaron(self):
        """IOT-MOD-HDW regla 8 y PROD-CNL-ORD: gana la cancelación; volver a activar, que esperaba, ve que la orden ya no está «a realizar» y pide revisar (``ordenes_cambiaron``): el equipo sigue fuera de servicio."""
        resultados = correr_a_la_vez(self.cancelar(), self.volver_a_activar("cancelar"), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["ordenes_cambiaron"])
        self.assertEqual(MantenimientoTecnico.objects.get(pk=self.orden.pk).estado_orden, "cancelada")
        self.assertEqual(Hardware.objects.get(pk=self.actuador.pk).estado_hardware, "fuera_de_servicio")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_orden").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="reactivacion_hardware").count(), 0)

    def test_regla_8_si_volver_a_activar_va_primero_la_cancelacion_recibe_orden_no_pendiente(self):
        """Lo mismo al revés: volver a activar cancela la orden y activa el equipo; la cancelación, que esperaba, recibe ``orden_no_pendiente`` (nunca un 500 ni dos cancelaciones)."""
        resultados = correr_a_la_vez(self.cancelar(), self.volver_a_activar("cancelar"), primera="b")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["orden_no_pendiente"])
        self.assertEqual(MantenimientoTecnico.objects.get(pk=self.orden.pk).estado_orden, "cancelada")
        self.assertEqual(Hardware.objects.get(pk=self.actuador.pk).estado_hardware, "activo")
        # volver a activar audita la cancelación dentro de su propio registro (``reactivacion_hardware``); la cancelación rechazada no audita.
        self.assertEqual(RegistroAuditoria.objects.filter(accion="reactivacion_hardware").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_orden").count(), 0)

    def test_regla_8_si_la_cancelacion_va_primero_mantener_una_orden_ya_cancelada_recibe_ordenes_cambiaron(self):
        """Con «Mantenerla» sobre una orden que otra operación acaba de cancelar, volver a activar también pide revisar (``ordenes_cambiaron``): la decisión era sobre una orden que ya no está «a realizar»."""
        resultados = correr_a_la_vez(self.cancelar(), self.volver_a_activar("mantener"), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["ordenes_cambiaron"])
        self.assertEqual(Hardware.objects.get(pk=self.actuador.pk).estado_hardware, "fuera_de_servicio")

    def test_regla_8_si_volver_a_activar_manteniendo_va_primero_la_cancelacion_tambien_se_hace(self):
        """Volver a activar con «Mantenerla» no toca la orden: la cancelación, que esperaba, la cancela. Las dos terminan; el equipo queda activo y la orden cancelada."""
        resultados = correr_a_la_vez(self.cancelar(), self.volver_a_activar("mantener"), primera="b")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(MantenimientoTecnico.objects.get(pk=self.orden.pk).estado_orden, "cancelada")
        self.assertEqual(Hardware.objects.get(pk=self.actuador.pk).estado_hardware, "activo")

    # ---- (b) dos cancelaciones a la vez ----

    def test_ext_8a_dos_cancelaciones_a_la_vez_una_gana_y_la_otra_recibe_orden_no_pendiente(self):
        """PROD-CNL-ORD extensión 8a: una cancelación gana y la otra recibe ``orden_no_pendiente``: un solo registro de auditoría y un solo aviso al Técnico."""
        resultados = correr_a_la_vez(self.cancelar(), self.cancelar(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["orden_no_pendiente"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_orden").count(), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.tecnico).count(), 1)

    def test_ext_8a_dos_cancelaciones_de_ordenes_distintas_se_hacen_las_dos(self):
        """Dos órdenes distintas no se rechazan entre sí: se serializan por el invernadero y terminan las dos."""
        otra = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        resultados = correr_a_la_vez(self.cancelar(), self.cancelar(otra), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(self.a_realizar().count(), 0)

    # ---- (c) el traspaso del Técnico y la cancelación a la vez ----

    def test_regla_3_si_el_traspaso_va_primero_la_cancelacion_recibe_cambio_simultaneo(self):
        """PROD-MOD-INV regla 3 y PROD-CNL-ORD: el traspaso pasa la orden al Técnico nuevo; la cancelación, que había leído al anterior, se rechaza con ``cambio_simultaneo`` (que reabra la ventana). La orden sigue «a realizar», del Técnico nuevo."""
        resultados = correr_a_la_vez(self.traspasar(), self.cancelar(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["cambio_simultaneo"])
        orden = MantenimientoTecnico.objects.get(pk=self.orden.pk)
        self.assertEqual((orden.estado_orden, orden.tecnico_id), ("a_realizar", self.nuevo.pk))

    def test_regla_3_si_la_cancelacion_va_primero_el_traspaso_no_toca_la_orden_cancelada(self):
        """Al revés: la cancelación gana y el traspaso, que esperaba, relee las órdenes «a realizar» y no ve la cancelada: termina sin tocarla (queda con el Técnico anterior)."""
        resultados = correr_a_la_vez(self.cancelar(), self.traspasar(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        orden = MantenimientoTecnico.objects.get(pk=self.orden.pk)
        self.assertEqual((orden.estado_orden, orden.tecnico_id), ("cancelada", self.tecnico.pk))

    # ---- (d) el escalamiento de un comando y la cancelación de la orden anterior del mismo actuador ----

    def test_ext_4b_4b_si_la_cancelacion_va_primero_el_escalamiento_crea_una_orden_nueva(self):
        """IOT-RSV-CMD extensión 4b.4b: la cancelación gana; el escalamiento, que esperaba, relee y ya no ve una orden «a realizar»: crea la nueva. Nunca dos «a realizar»."""
        resultados = correr_a_la_vez(self.cancelar(), self.escalar(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(MantenimientoTecnico.objects.get(pk=self.orden.pk).estado_orden, "cancelada")
        (nueva,) = self.a_realizar()
        self.assertNotEqual(nueva.pk, self.orden.pk)
        self.assertIn(nueva.codigo, Alerta.objects.get(tipo_alerta="iot_comando_fallido").descripcion_alerta)

    def test_ext_4b_4b_si_el_escalamiento_va_primero_la_alerta_nombra_la_orden_existente_y_despues_se_cancela(self):
        """El escalamiento gana: ve la orden «a realizar», no crea otra y la alerta la nombra; la cancelación, que esperaba, la cancela. Nunca dos «a realizar»."""
        resultados = correr_a_la_vez(self.cancelar(), self.escalar(), primera="b")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(MantenimientoTecnico.objects.count(), 1)
        self.assertEqual(MantenimientoTecnico.objects.get(pk=self.orden.pk).estado_orden, "cancelada")
        self.assertIn(self.orden.codigo, Alerta.objects.get(tipo_alerta="iot_comando_fallido").descripcion_alerta)

    def test_d78_el_escalamiento_corre_entero_antes_de_que_la_cancelacion_tome_el_invernadero(self):
        """D-78 punto 11 (invernadero antes que orden), con barrera: la cancelación se detiene justo ANTES de bloquear el invernadero y el escalamiento corre entero (invernadero, sistema, nodo, actuador, comando y
        la orden existente). Con el orden inverso (la orden antes que el invernadero) la cancelación tendría la orden y esperaría el invernadero mientras el escalamiento espera la orden: ciclo, ``DeadlockDetected``."""
        resultados = correr_a_la_vez(self.cancelar(), self.escalar(), primera="a", detener_antes_de=ANTES_DEL_INVERNADERO)
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(MantenimientoTecnico.objects.get(pk=self.orden.pk).estado_orden, "cancelada")
        self.assertEqual(self.a_realizar().count(), 0)
