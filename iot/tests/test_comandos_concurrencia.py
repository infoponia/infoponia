# Pruebas de concurrencia de los comandos del IoT (IOT-05, paso 6; docs/casos_de_uso/iot/emitir_comando.md, resolver_comando.md y cancelar_comando.md, «Concurrencia»;
# docs/patrones/bloqueos.md; D-78, punto 11; D-82): dos emisiones sobre el mismo actuador, dos retiros, un retiro y una cancelación (en los dos órdenes), dos resultados iguales y
# el orden de bloqueo «tipo de actuador antes que invernadero» contra IOT-MOD-TAC. Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py).
# ``TransactionTestCase``: su ``flush`` vacía todas las tablas al terminar, así que cada prueba vuelve a asegurar los datos en ``setUp``
# (docs/patrones/datos_de_migracion.md) y limpia la caché.
#
# El retiro solo audita si canceló o dio por vencido algo, así que la parada por defecto (después de auditar) no sirve: se detiene a ``primera`` justo ANTES de leer la
# configuración operativa (``configuracion.obtener``), que el retiro hace con el invernadero, el sistema y el nodo ya bloqueados.

from datetime import datetime, timezone

from django.core.cache import cache
from django.test import TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from iot.models import Comando, NodoCentral, RegistroComando
from iot.servicios import comandos, tipos_actuador as tipos
from iot.tests import fabricas
from iot.tests.fabricas import accion_de_formulario as accion
from iot.tests.fabricas import datos_de
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo, crear_invernadero_con_geografia_propia

AHORA = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
DETENER_EL_RETIRO = (configuracion, "obtener")


def sin_resultado():
    return comandos.ResultadoRecibido(resultado="ejecutado", detalle="", estado=None, informado_en=None)


@tag("concurrencia")
class ComandosConcurrenciaTests(fabricas.ConCatalogoIot, TransactionTestCase):
    """Emitir, retirar, cancelar y resolver a la vez."""

    def setUp(self):
        cache.clear()
        fabricas.asegurar_datos_de_iot()
        from maestros.tests.fabricas import asegurar_datos_de_maestros

        asegurar_datos_de_maestros()
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero_con_geografia_propia("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        self.tipo = fabricas.tipo_actuador("Extractor")
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/extractor", ultimo_mensaje_en=AHORA)
        self.encender, self.apagar = self.tipo.acciones.order_by("id")
        NodoCentral.objects.filter(sistema=self.sistema).update(ultima_comunicacion=AHORA)

    # ---- ayudas ----

    def emitir(self, accion_emitida=None):
        return lambda: comandos.emitir_comando(
            self.laura, self.actuador.pk, comandos.DatosDeComando(accion_id=(accion_emitida or self.encender).pk), AHORA
        )

    def retirar(self):
        return lambda: comandos.retirar_comandos(self.sistema.pk, AHORA)

    def cancelar(self, comando):
        return lambda: comandos.cancelar_comando(self.laura, comando.pk, AHORA)

    def resolver(self, comando):
        return lambda: comandos.registrar_resultado(self.sistema.pk, comando.pk, sin_resultado(), AHORA)

    def pendiente(self, **extra):
        return fabricas.comando(self.actuador, self.encender, **extra)

    # ---- dos emisiones a la vez ----

    def test_ext_8a_dos_emisiones_a_la_vez_sobre_el_mismo_actuador_una_gana_y_la_otra_recibe_8a(self):
        """IOT-EMT-CMD extensión 8a y requisito de concurrencia: una emisión gana y la otra recibe ``comando_pendiente`` (nunca un 500 ni dos pendientes)."""
        resultados = correr_a_la_vez(self.emitir(self.encender), self.emitir(self.apagar), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["comando_pendiente"])
        self.assertEqual(Comando.objects.filter(actuador=self.actuador, estado_comando="pendiente").count(), 1)
        self.assertEqual((RegistroComando.objects.count(), RegistroAuditoria.objects.filter(accion="emision_comando").count()), (1, 1))

    def test_ext_8a_el_orden_inverso_tambien_deja_un_solo_pendiente(self):
        """Lo mismo cuando la que se detiene primero es la otra emisión."""
        resultados = correr_a_la_vez(self.emitir(self.encender), self.emitir(self.apagar), primera="b")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(Comando.objects.filter(actuador=self.actuador, estado_comando="pendiente").count(), 1)

    def test_ext_8a_dos_emisiones_sobre_actuadores_distintos_se_crean_las_dos(self):
        """El bloqueo del tipo y del invernadero serializa pero no rechaza lo que no choca."""
        otro = fabricas.actuador(self.sistema, self.tipo, "norte/otro", ultimo_mensaje_en=AHORA)
        resultados = correr_a_la_vez(
            self.emitir(self.encender),
            lambda: comandos.emitir_comando(self.laura, otro.pk, comandos.DatosDeComando(accion_id=self.encender.pk), AHORA),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))

    # ---- dos retiros a la vez ----

    def test_regla_comando_disponible_dos_retiros_a_la_vez_entregan_cada_comando_una_sola_vez(self):
        """IOT-RSV-CMD, «Requisitos especiales»: un comando se entrega a un solo retiro por intento. El segundo retiro espera al primero y ve el comando dentro de su espera."""
        comando = self.pendiente()
        resultados = correr_a_la_vez(self.retirar(), self.retirar(), primera="a", detener_antes_de=DETENER_EL_RETIRO)
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        entregados = [c.id for retiro in exitos for c in retiro.comandos]
        self.assertEqual(entregados, [comando.pk])
        comando.refresh_from_db()
        self.assertEqual(comando.cantidad_intentos, 1)

    # ---- un retiro y una cancelación a la vez ----

    def test_regla_5_si_la_cancelacion_va_primero_el_retiro_ya_no_lo_entrega(self):
        """IOT-RSV-CMD y regla 5 de IOT-CNL-CMD: gana la cancelación (el comando queda «cancelado») y el retiro, que esperaba, no lo entrega ni le suma un intento."""
        comando = self.pendiente()
        resultados = correr_a_la_vez(self.cancelar(comando), self.retirar(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(resultados["b"].comandos, [])
        comando.refresh_from_db()
        self.assertEqual((comando.estado_comando, comando.cantidad_intentos), ("cancelado", 0))

    def test_regla_5_si_el_retiro_va_primero_la_cancelacion_se_niega_con_el_texto_de_la_regla_5(self):
        """Regla 5 de IOT-CNL-CMD: el nodo acaba de retirar el comando, así que no se cancela y se informa cuánto falta (el bloqueo del comando resuelve la carrera)."""
        comando = self.pendiente()
        resultados = correr_a_la_vez(self.retirar(), self.cancelar(comando), primera="a", detener_antes_de=DETENER_EL_RETIRO)
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual([c.id for c in resultados["a"].comandos], [comando.pk])
        self.assertEqual(codigos(rechazos[0]), ["comando_en_curso"])
        self.assertIn("El nodo acaba de retirar el comando: no se canceló.", rechazos[0].messages[0])
        comando.refresh_from_db()
        self.assertEqual((comando.estado_comando, comando.cantidad_intentos), ("pendiente", 1))

    # ---- dos resultados iguales a la vez ----

    def test_ext_4d_dos_resultados_iguales_a_la_vez_uno_es_aceptado_y_el_otro_ya_resuelto(self):
        """IOT-RSV-CMD extensión 4d: el comando se resuelve una sola vez; el segundo resultado espera y recibe ``ya_resuelto``, sin duplicar la bitácora ni la auditoría."""
        comando = self.pendiente(cantidad_intentos=1, ultimo_intento_en=AHORA)
        resultados = correr_a_la_vez(self.resolver(comando), self.resolver(comando), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(sorted(r.resultado for r in exitos), ["aceptado", "ya_resuelto"])
        self.assertEqual(RegistroComando.objects.filter(comando=comando, resultado="ejecutado").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="resolucion_comando_iot").count(), 1)

    def test_ext_4d_un_resultado_y_una_cancelacion_a_la_vez_una_sola_resuelve_el_comando(self):
        """Garantías mínimas: «el nodo y un usuario (IOT-CNL-CMD) actúan al mismo tiempo»: el resultado, que va primero, resuelve el comando y la cancelación se niega porque ya no está pendiente."""
        comando = self.pendiente(cantidad_intentos=1, ultimo_intento_en=AHORA)
        resultados = correr_a_la_vez(self.resolver(comando), self.cancelar(comando), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["comando_no_pendiente"])
        comando.refresh_from_db()
        self.assertEqual(comando.estado_comando, "ejecutado")

    # ---- D-82: el tipo de actuador antes que el invernadero ----

    def modificar_el_tipo_con_una_accion_mas(self):
        """La modificación del tipo (agrega «Abrir»): recalcula la compatibilidad de sus actuadores, y eso bloquea sus invernaderos DESPUÉS del tipo."""
        datos = datos_de(self.tipo)
        datos.acciones.append(accion("Abrir", "ABRIR"))
        return lambda: tipos.modificar_tipo_actuador(self.gerente, self.tipo.pk, datos)

    def test_d82_emitir_a_la_vez_que_se_modifica_el_tipo_de_ese_actuador_no_se_cruzan(self):
        """D-82 (tipo, invernadero, sistema, actuador): emitir bloquea primero el tipo del actuador y después el invernadero. Con barrera: IOT-MOD-TAC (``a``) se detiene justo ANTES
        de bloquear el invernadero, con el tipo ya tomado; arranca la emisión (``b``), que espera el tipo y no toma el invernadero. Las dos terminan, sin bloqueo cruzado ni 500.
        Con el orden inverso (invernadero y después tipo), ``b`` tomaría el invernadero y esperaría el tipo mientras ``a`` espera el invernadero: ``DeadlockDetected``."""
        fabricas.equipo_anunciado(self.sistema, "norte/extractor", ("ENCENDER", "APAGAR"))
        resultados = correr_a_la_vez(
            self.modificar_el_tipo_con_una_accion_mas(),
            self.emitir(self.encender),
            primera="a",
            detener_antes_de=(api_alertas, "bloquear_invernadero_para_alertas"),
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Comando.objects.filter(actuador=self.actuador, estado_comando="pendiente").count(), 1)
