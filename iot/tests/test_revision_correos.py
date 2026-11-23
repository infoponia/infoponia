# Pruebas del correo de las alertas críticas del IoT (IOT-04, paso 3; IOT-ENT-INF, regla «Alertas», extensiones 1a y 5g; D-71 punto 3 y D-76 punto 7;
# docs/casos_de_uso/iot/entregar_informacion.md, «La revisión periódica», «Correos»). Se escribieron ANTES que el servicio (`.claude/rules/pruebas.md`).
#
# Servicio que se prueba (iot/servicios/revision.py):
#   enviar_correos_pendientes(ahora) -> ResumenDeCorreos(enviados, fallidos, pendientes_sin_servidor)   (cuenta ALERTAS, no destinatarios)
#   revisar(ahora)                   -> ... y al final llama a la anterior, fuera de toda transacción
#   _destinatarios_de(alerta)        -> las cuentas a las que va hoy (se reemplaza con ``mock`` solo para probar «salió al menos a uno»: hoy hay a lo sumo un
#                                       Gerente activo, D-09, y una alerta del IoT va a uno o al otro)
# ``core.correo.enviar_correo`` se reemplaza con ``mock`` (`core.correo`, el logger «core.correo» y la plantilla de la app que llama: docs/api/correo.md).
#
# DECISIÓN de IOT-04 (a anotar en el «Cierre»): dos revisiones simultáneas no mandan el mismo correo dos veces porque la alerta se RESERVA antes de enviar, con un
# ``UPDATE`` condicional (``correo_enviado_en`` nulo y alerta activa → ``correo_enviado_en = ahora``) fuera del envío; quien no logra reservar, salta esa alerta. Si el
# envío falla a todos, se libera (``correo_enviado_en`` nulo) y se suma un intento. Costo aceptado: si el proceso muere entre reservar y enviar, ese correo no se
# reintenta (no hay duplicados nunca). El bloqueo de filas no sirve acá: hay que mandar fuera de la transacción (D-14).

from datetime import datetime, timedelta
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.template.loader import render_to_string
from django.test import TestCase, TransactionTestCase, override_settings, tag

from core.identidad import nombre_de_la_organizacion
from core.models import Usuario
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import AlertaIot, NodoCentral
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_invernadero_con_geografia_propia

revision = perezoso("iot.servicios.revision")
alertas_iot = perezoso("iot.servicios.alertas_iot")

LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")
AHORA = datetime(2026, 11, 23, 12, 0, tzinfo=LOCAL)
PLANTILLA = "iot/correo/alerta_critica.txt"
TOKEN = "ab" * 32  # el resumen del token del sistema: nunca debe aparecer en un correo


def critica_del_nodo(invernadero, sistema, descripcion=None, hace_minutos=10):
    """Una alerta crítica «nodo sin comunicación» activa del sistema, con su fecha y hora fijas (``ahora − hace_minutos``)."""
    nodo = NodoCentral.objects.get(sistema=sistema)
    alerta = alertas_iot.asegurar_alerta_iot(
        invernadero.pk, sistema, "iot_nodo_sin_comunicacion", f"nodo:{nodo.pk}", descripcion or f"{nodo.nombre_nodo} · sin comunicación desde las 11:50 del 23/11"
    ).alerta
    Alerta.objects.filter(pk=alerta.pk).update(fecha_hora_alerta=AHORA - timedelta(minutes=hace_minutos))
    return alerta


@override_settings(CORREO_CONFIGURADO=True)
class RevisionCorreosServicioTests(fabricas.ConCatalogoIot, TestCase):
    """`enviar_correos_pendientes`: a quién, cuándo cuenta como enviado, los intentos, qué alertas y qué dice."""

    def setUp(self):
        cache.clear()
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte, token_resumen=TOKEN)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)

    # ---- ayudas ----

    def con_envio(self, **extra):
        """Reemplaza ``core.correo.enviar_correo`` (por omisión, sale siempre) y devuelve el ``mock``."""
        return self.enterContext(mock.patch("core.correo.enviar_correo", **({"return_value": True} | extra)))

    def un_invernadero_sin_agronomo(self, nombre="Sur"):
        """Otro invernadero SIN Agrónomo (sus alertas van al Gerente) con su sistema."""
        invernadero = crear_invernadero(nombre)
        return invernadero, fabricas.sistema(invernadero)

    def vinculo(self, alerta):
        return AlertaIot.objects.get(alerta=alerta)

    def enviar(self, ahora=AHORA):
        return revision.enviar_correos_pendientes(ahora)

    def destinatarios(self, envio):
        """Los ids de las cuentas a las que se mandó, en orden de llamada."""
        return [llamada.args[0].pk for llamada in envio.call_args_list]

    # ---- cuándo se manda ----

    def test_regla_correos_una_critica_sin_correo_se_manda_una_vez_y_la_segunda_corrida_no_la_repite(self):
        """Regla «Alertas» (D-71 punto 3): «una sola vez». La crítica nace con `correo_enviado_en` nulo; la corrida la manda y carga `correo_enviado_en = ahora`; otra corrida con
        el mismo `ahora` manda 0."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        envio = self.con_envio()
        primera = self.enviar()
        segunda = self.enviar()
        self.assertEqual((primera.enviados, primera.fallidos), (1, 0))
        self.assertEqual((segunda.enviados, segunda.fallidos), (0, 0))
        self.assertEqual(envio.call_count, 1)
        self.assertEqual(self.vinculo(alerta).correo_enviado_en, AHORA)

    def test_regla_correos_solo_salen_las_criticas_activas_de_cualquier_origen(self):
        """Regla «Alertas»: crítica es «comando fallido, nodo sin comunicación, nivel de solución bajo y dispositivo en falla», de origen en la telemetría, en el equipo o
        ninguno. Las advertencias, las informativas y las resueltas no salen."""
        nivel = fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        sensor = fabricas.sensor(self.sistema, "norte/sectorA/temperatura")
        lectura = fabricas.telemetria(nivel)
        criticas = [
            critica_del_nodo(self.norte, self.sistema),
            alertas_iot.asegurar_alerta_iot(
                self.norte.pk, self.sistema, "iot_nivel_solucion_bajo", f"sensor:{nivel.pk}", "norte/tanque1/nivel · informa «bajo»", telemetria=lectura
            ).alerta,
            alertas_iot.asegurar_alerta_iot(
                self.norte.pk, self.sistema, "iot_dispositivo_en_falla", f"hw:{sensor.pk}", "norte/sectorA/temperatura · en falla", hardware=sensor
            ).alerta,
        ]
        alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, "iot_dispositivo_sin_actividad", f"hw:{sensor.pk}", "advertencia", hardware=sensor)
        alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, "iot_dispositivo_no_registrado", "id:otro", "informativa")
        resuelta = alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, "iot_comando_fallido", f"hw:{sensor.pk}", "resuelta", hardware=sensor).alerta
        alertas_iot.resolver_alerta_iot(self.norte.pk, "iot_comando_fallido", f"hw:{sensor.pk}")
        envio = self.con_envio()
        resumen = self.enviar()
        self.assertEqual(resumen.enviados, 3)
        self.assertEqual(envio.call_count, 3)
        for alerta in criticas:
            self.assertEqual(self.vinculo(alerta).correo_enviado_en, AHORA)
        self.assertIsNone(self.vinculo(resuelta).correo_enviado_en)

    def test_regla_correos_una_alerta_resuelta_antes_de_mandarse_no_se_manda(self):
        """Regla «Alertas» y «Correos» de «La revisión periódica»: «una alerta que se resolvió antes de mandarse ya no se manda (solo las activas)»."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        alertas_iot.resolver_alerta_iot(self.norte.pk, "iot_nodo_sin_comunicacion", f"nodo:{self.nodo.pk}")
        envio = self.con_envio()
        self.assertEqual(self.enviar().enviados, 0)
        envio.assert_not_called()
        self.assertIsNone(self.vinculo(alerta).correo_enviado_en)

    # ---- a quién ----

    def test_regla_correos_va_al_agronomo_de_la_alerta(self):
        """D-76 punto 7 y regla «Alertas»: la recibe el Agrónomo del invernadero (`Alerta.agronomo`)."""
        critica_del_nodo(self.norte, self.sistema)
        envio = self.con_envio()
        self.enviar()
        self.assertEqual(self.destinatarios(envio), [self.laura.pk])

    def test_regla_correos_una_alerta_para_el_gerente_va_al_gerente_activo(self):
        """D-76 punto 7: «si va al Gerente, cada cuenta activa de rol Gerente con email». Un invernadero sin Agrónomo activo manda la alerta al Gerente (`para_gerente`)."""
        sur, sistema_sur = self.un_invernadero_sin_agronomo()
        critica_del_nodo(sur, sistema_sur)
        envio = self.con_envio()
        self.enviar()
        self.assertEqual(self.destinatarios(envio), [self.gerente.pk])

    def test_regla_correos_un_gerente_inactivo_o_sin_email_no_recibe(self):
        """D-76 punto 7: solo las cuentas ACTIVAS de rol Gerente y CON email. Con un Gerente anterior inactivo, solo sale al activo."""
        crear_gerente("anterior@infoponia.com", activo=False)
        sur, sistema_sur = self.un_invernadero_sin_agronomo()
        critica_del_nodo(sur, sistema_sur)
        envio = self.con_envio()
        self.enviar()
        self.assertEqual(self.destinatarios(envio), [self.gerente.pk])

    def test_regla_correos_un_gerente_sin_email_deja_la_alerta_sin_destinatarios_y_suma_un_intento(self):
        """D-76 punto 7: si no sale a nadie (el único Gerente no tiene email), no se marca como enviado y se suma un intento."""
        Usuario.objects.filter(pk=self.gerente.pk).update(email="")
        sur, sistema_sur = self.un_invernadero_sin_agronomo()
        alerta = critica_del_nodo(sur, sistema_sur)
        envio = self.con_envio()
        resumen = self.enviar()
        envio.assert_not_called()
        vinculo = self.vinculo(alerta)
        self.assertEqual((vinculo.correo_enviado_en, vinculo.intentos_correo), (None, 1))
        self.assertEqual((resumen.enviados, resumen.fallidos), (0, 1))

    def test_regla_correos_el_traspaso_del_agronomo_entre_la_creacion_y_el_envio_cambia_el_destinatario(self):
        """D-76 punto 7 («a los destinatarios que tiene la alerta AL ENVIARSE») y D-41: «así sigue los traspasos sin lógica propia». La alerta nace para Laura; el invernadero
        pasa a otro Agrónomo (`traspasar_alertas_del_agronomo`); el correo va al nuevo."""
        otro = crear_agronomo("otro@infoponia.com")
        critica_del_nodo(self.norte, self.sistema)
        api_alertas.traspasar_alertas_del_agronomo(self.norte, self.laura, otro)
        envio = self.con_envio()
        self.enviar()
        self.assertEqual(self.destinatarios(envio), [otro.pk])

    def test_regla_correos_si_el_invernadero_se_queda_sin_agronomo_la_alerta_va_al_gerente(self):
        """D-41 y D-76 punto 7: sin entrante, la alerta queda para el Gerente (`para_gerente`) y el correo va a él."""
        critica_del_nodo(self.norte, self.sistema)
        api_alertas.traspasar_alertas_del_agronomo(self.norte, self.laura, None)
        envio = self.con_envio()
        self.enviar()
        self.assertEqual(self.destinatarios(envio), [self.gerente.pk])

    # ---- cuándo cuenta como enviado y los intentos ----

    def test_regla_correos_cuenta_como_enviado_si_salio_al_menos_a_uno(self):
        """D-76 punto 7 («cuándo cuenta como enviado»): con dos destinatarios, si uno falla y el otro sale, se carga `correo_enviado_en` (y no suma intento). Se prueba con
        ``_destinatarios_de`` reemplazado: hoy hay a lo sumo un Gerente activo (D-09)."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        envio = self.con_envio(side_effect=[False, True])
        # Se reemplaza ``_destinatarios_de`` porque D-09 limita a UN Gerente activo (`un_solo_gerente_activo`) y una alerta del IoT va al Gerente o al Agrónomo, nunca a
        # los dos: con datos reales no hay forma de armar una alerta con dos destinatarios.
        with mock.patch("iot.servicios.revision._destinatarios_de", return_value=[self.gerente, self.laura]):
            resumen = self.enviar()
        self.assertEqual(envio.call_count, 2)
        vinculo = self.vinculo(alerta)
        self.assertEqual((vinculo.correo_enviado_en, vinculo.intentos_correo), (AHORA, 0))
        self.assertEqual((resumen.enviados, resumen.fallidos), (1, 0))

    def test_regla_correos_si_no_salio_a_ninguno_suma_un_intento_y_la_alerta_sigue_pendiente(self):
        """D-71 punto 3 y D-76 punto 7: si el envío falla a todos, `correo_enviado_en` queda nulo y `intentos_correo` suma 1; sin `logger.error` antes del quinto fallo."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        self.con_envio(return_value=False)
        with self.assertNoLogs("iot.revision", level="ERROR"):
            resumen = self.enviar()
        vinculo = self.vinculo(alerta)
        self.assertEqual((vinculo.correo_enviado_en, vinculo.intentos_correo), (None, 1))
        self.assertEqual((resumen.enviados, resumen.fallidos), (0, 1))

    def test_regla_correos_se_reintenta_en_la_corrida_siguiente_y_sale(self):
        """D-71 punto 3: «lo vuelve a probar en la revisión siguiente»: tras un fallo, la corrida siguiente lo manda y cuenta como enviado."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        self.con_envio(side_effect=[False, True])
        self.enviar()
        self.enviar(AHORA + timedelta(minutes=5))
        vinculo = self.vinculo(alerta)
        self.assertEqual((vinculo.correo_enviado_en, vinculo.intentos_correo), (AHORA + timedelta(minutes=5), 1))

    def test_regla_correos_al_quinto_fallo_deja_un_logger_error_con_el_id_de_la_alerta_y_deja_de_intentar(self):
        """D-71 punto 3: «hasta 5 intentos; después queda registrado en el registro técnico de errores»: al quinto fallo, `logger.error` (registrador `iot.revision`) con el id
        de la alerta; la corrida siguiente ya no intenta."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        AlertaIot.objects.filter(alerta=alerta).update(intentos_correo=4)
        envio = self.con_envio(return_value=False)
        with self.assertLogs("iot.revision", level="ERROR") as registros:
            self.enviar()
        self.assertTrue(any(str(alerta.pk) in linea for linea in registros.output))
        self.assertEqual(self.vinculo(alerta).intentos_correo, 5)
        llamadas = envio.call_count
        self.enviar(AHORA + timedelta(minutes=5))
        self.assertEqual(envio.call_count, llamadas)

    def test_regla_correos_una_excepcion_durante_el_envio_libera_la_reserva_y_suma_un_intento(self):
        """Decisión de la reserva (try/finally): si `enviar_correo` lanza una excepción, la reserva se libera igual (`correo_enviado_en` nulo, con un `UPDATE` condicional a la
        marca reservada) y se suma un intento; durante el envío la alerta estaba reservada."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        durante = []

        def revienta(*args, **kwargs):
            durante.append(self.vinculo(alerta).correo_enviado_en)
            raise RuntimeError("falla de prueba")

        self.con_envio(side_effect=revienta)
        with self.assertLogs("iot.revision", level="ERROR"):
            resumen = self.enviar()
        vinculo = self.vinculo(alerta)
        self.assertEqual(durante, [AHORA])
        self.assertEqual((vinculo.correo_enviado_en, vinculo.intentos_correo), (None, 1))
        self.assertEqual((resumen.enviados, resumen.fallidos), (0, 1))

    def test_regla_correos_un_envio_fallido_a_todos_libera_la_reserva_y_la_corrida_siguiente_reintenta(self):
        """D-71 punto 3 («lo vuelve a probar en la revisión siguiente») con la reserva: la primera corrida reserva, falla y libera (intento 1); la segunda reserva de nuevo, sale
        y queda enviada."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        reservas = []
        resultados = iter([False, True])

        def envia(*args, **kwargs):
            reservas.append(self.vinculo(alerta).correo_enviado_en)
            return next(resultados)

        self.con_envio(side_effect=envia)
        self.enviar()
        self.assertEqual((self.vinculo(alerta).correo_enviado_en, self.vinculo(alerta).intentos_correo), (None, 1))
        otra_hora = AHORA + timedelta(minutes=5)
        self.enviar(otra_hora)
        self.assertEqual(reservas, [AHORA, otra_hora])
        self.assertEqual((self.vinculo(alerta).correo_enviado_en, self.vinculo(alerta).intentos_correo), (otra_hora, 1))

    def test_regla_correos_un_envio_exitoso_deja_intentos_correo_en_cero(self):
        """`AlertaIot.intentos_correo` cuenta los FALLOS (docs/modelo/iot.md): reservar para enviar no suma; un envío que sale lo deja en 0."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        self.con_envio()
        self.enviar()
        vinculo = self.vinculo(alerta)
        self.assertEqual((vinculo.correo_enviado_en, vinculo.intentos_correo), (AHORA, 0))

    def test_regla_correos_un_agronomo_inactivo_sin_para_gerente_no_recibe_suma_un_intento_y_queda_avisado(self):
        """D-76 punto 7 («si no salió a ninguno, se suma un intento»): la alerta quedó con un Agrónomo cuya cuenta se dio de baja y sin `para_gerente`; no hay a quién
        mandarla. No se pierde en silencio: no se marca como enviada, suma un intento y deja un `logger.warning` con el id de la alerta."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        Usuario.objects.filter(pk=self.laura.pk).update(is_active=False)
        envio = self.con_envio()
        with self.assertLogs("iot.revision", level="WARNING") as registros:
            resumen = self.enviar()
        envio.assert_not_called()
        self.assertTrue(any(str(alerta.pk) in linea and "destinatarios" in linea for linea in registros.output))
        vinculo = self.vinculo(alerta)
        self.assertEqual((vinculo.correo_enviado_en, vinculo.intentos_correo), (None, 1))
        self.assertEqual((resumen.enviados, resumen.fallidos), (0, 1))

    def test_regla_correos_una_alerta_sin_destinatarios_llega_al_quinto_intento_y_queda_en_el_registro_de_errores(self):
        """D-71 punto 3: tampoco una alerta sin destinatarios se reintenta para siempre: al quinto intento queda en el registro de errores con el id de la alerta."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        Usuario.objects.filter(pk=self.laura.pk).update(is_active=False)
        AlertaIot.objects.filter(alerta=alerta).update(intentos_correo=4)
        self.con_envio()
        with self.assertLogs("iot.revision", level="ERROR") as registros:
            self.enviar()
        self.assertTrue(any(str(alerta.pk) in linea for linea in registros.output))
        self.assertEqual(self.vinculo(alerta).intentos_correo, 5)

    # ---- sin servidor de correo ----

    @override_settings(CORREO_CONFIGURADO=False)
    def test_regla_correos_sin_servidor_no_se_intenta_no_se_suman_intentos_y_el_resumen_lo_dice(self):
        """«Correos» de «La revisión periódica»: sin servidor (`correo_configurado()` falso) no se intenta nada, no se cuentan intentos y la salida lo dice
        (`pendientes_sin_servidor`). Cuando se configure, el correo sale."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        envio = self.con_envio()
        resumen = self.enviar()
        envio.assert_not_called()
        vinculo = self.vinculo(alerta)
        self.assertEqual((vinculo.correo_enviado_en, vinculo.intentos_correo), (None, 0))
        self.assertEqual((resumen.enviados, resumen.fallidos, resumen.pendientes_sin_servidor), (0, 0, 1))
        with override_settings(CORREO_CONFIGURADO=True):
            self.assertEqual(self.enviar().enviados, 1)

    # ---- fallas inesperadas y simultaneidad ----

    def test_regla_correos_una_excepcion_inesperada_en_una_alerta_no_frena_a_las_siguientes(self):
        """Robustez (D-71 punto 2, el mismo espíritu para los correos): si el envío de una alerta lanza una excepción inesperada, se registra con `logger.exception`, cuenta
        como intento fallido de esa alerta y se sigue con las demás."""
        sur, sistema_sur = self.un_invernadero_sin_agronomo()
        primera = critica_del_nodo(self.norte, self.sistema)
        segunda = critica_del_nodo(sur, sistema_sur)
        self.con_envio(side_effect=[RuntimeError("falla de prueba"), True])
        with self.assertLogs("iot.revision", level="ERROR"):
            resumen = self.enviar()
        self.assertEqual((resumen.enviados, resumen.fallidos), (1, 1))
        self.assertEqual((self.vinculo(primera).correo_enviado_en, self.vinculo(primera).intentos_correo), (None, 1))
        self.assertEqual(self.vinculo(segunda).correo_enviado_en, AHORA)

    def test_regla_correos_dos_revisiones_simultaneas_mandan_el_correo_una_sola_vez(self):
        """DECISIÓN de IOT-04: la alerta se reserva (`correo_enviado_en = ahora`) ANTES de enviar, con un `UPDATE` condicional fuera del envío. Mientras la primera revisión
        está dentro de `enviar_correo`, una segunda corrida no ve la alerta pendiente y no la manda: el correo sale una sola vez."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        vistos = {}

        def mientras_se_envia(*args, **kwargs):
            vistos["reservada"] = AlertaIot.objects.get(alerta=alerta).correo_enviado_en
            vistos["segunda"] = self.enviar()
            return True

        envio = self.con_envio(side_effect=mientras_se_envia)
        primera = self.enviar()
        self.assertEqual(vistos["reservada"], AHORA)
        self.assertEqual((vistos["segunda"].enviados, vistos["segunda"].fallidos), (0, 0))
        self.assertEqual((envio.call_count, primera.enviados), (1, 1))

    def test_regla_correos_una_falla_libera_la_reserva_para_que_la_proxima_corrida_reintente(self):
        """Consecuencia de la decisión anterior: durante el envío la alerta está reservada (`correo_enviado_en = ahora`); si el envío falla a todos, la reserva se libera
        (`correo_enviado_en` nulo) y se suma el intento; si no, la alerta no se reintentaría nunca."""
        alerta = critica_del_nodo(self.norte, self.sistema)
        durante = []

        def falla(*args, **kwargs):
            durante.append(self.vinculo(alerta).correo_enviado_en)
            return False

        self.con_envio(side_effect=falla)
        self.enviar()
        self.assertEqual(durante, [AHORA])
        self.assertIsNone(self.vinculo(alerta).correo_enviado_en)

    # ---- qué dice ----

    def test_regla_correos_asunto_y_cuerpo_son_los_de_d76_punto_7_sin_enlace_ni_token(self):
        """D-76 punto 7: asunto «Alerta crítica: {tipo} · {invernadero}»; cuerpo en texto plano con el tipo, el invernadero, la descripción, la fecha y hora y «Para verla, entrá a
        InfoPonia: menú «Alertas».»; sin enlace (no hay dirección del sitio) y sin el token ni su resumen; con `nombre_organizacion`. La plantilla es de la app (`iot/correo/`)."""
        critica_del_nodo(self.norte, self.sistema, "Nodo de prueba · sin comunicación desde las 11:50 del 23/11", hace_minutos=10)
        envio = self.con_envio()
        self.enviar()
        cuenta, asunto, plantilla, contexto = envio.call_args.args
        self.assertEqual((cuenta.pk, asunto, plantilla), (self.laura.pk, "Alerta crítica: Nodo sin comunicación · Norte", PLANTILLA))
        cuerpo = render_to_string(plantilla, {**contexto, "nombre_organizacion": "Vivero Los Álamos"})
        for texto in (
            "Nodo sin comunicación",
            "Norte",
            "Nodo de prueba · sin comunicación desde las 11:50 del 23/11",
            "23/11/2026 11:50",
            "Para verla, entrá a InfoPonia: menú «Alertas».",
            "Vivero Los Álamos",
        ):
            self.assertIn(texto, cuerpo)
        self.assertNotIn("http", cuerpo)
        self.assertNotIn(TOKEN, cuerpo + repr(contexto))
        self.assertNotIn("token", cuerpo.lower())

    def test_regla_correos_el_cuerpo_no_trae_datos_de_otro_invernadero(self):
        """Alcance (D-28) y D-76 punto 7: el correo de una alerta lleva solo el invernadero y la descripción de esa alerta; ni el nombre ni la descripción de la otra."""
        sur, sistema_sur = self.un_invernadero_sin_agronomo()
        critica_del_nodo(self.norte, self.sistema, "Descripción del norte")
        critica_del_nodo(sur, sistema_sur, "Descripción del sur")
        envio = self.con_envio()
        self.enviar()
        cuerpos = {}
        for llamada in envio.call_args_list:
            _, asunto, plantilla, contexto = llamada.args
            cuerpos[asunto] = render_to_string(plantilla, {**contexto, "nombre_organizacion": "Vivero"})
        norte, sur_cuerpo = cuerpos["Alerta crítica: Nodo sin comunicación · Norte"], cuerpos["Alerta crítica: Nodo sin comunicación · Sur"]
        self.assertNotIn("Sur", norte)
        self.assertNotIn("Descripción del sur", norte)
        self.assertNotIn("Norte", sur_cuerpo)
        self.assertNotIn("Descripción del norte", sur_cuerpo)

    def test_regla_correos_de_punta_a_punta_sale_un_correo_de_texto_plano_con_el_nombre_de_la_organizacion(self):
        """D-54 y D-76 punto 7, sin reemplazar `enviar_correo`: sale un solo correo a la cuenta, en texto plano, con el asunto y el nombre de la organización."""
        critica_del_nodo(self.norte, self.sistema)
        self.enviar()
        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual((mensaje.to, mensaje.subject, mensaje.content_subtype), ([self.laura.email], "Alerta crítica: Nodo sin comunicación · Norte", "plain"))
        self.assertIn(nombre_de_la_organizacion(), mensaje.body)

    # ---- desde revisar ----

    def test_regla_correos_revisar_los_manda_al_final_en_la_misma_corrida_y_fuera_de_las_transacciones_de_los_sistemas(self):
        """D-71 punto 3 y «Correos»: `revisar` manda los correos DESPUÉS de todos los sistemas y fuera de toda transacción: la alerta que generó esta corrida sale en esta
        corrida, y al enviar no hay un `atomic` abierto (la profundidad de savepoints es la de antes de llamar; la prueba absoluta, con `in_atomic_block` falso, está en
        `RevisionCorreosFueraDeTransaccionTests`)."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=AHORA - timedelta(minutes=10))
        base = len(connection.savepoint_ids)
        profundidades = []
        self.con_envio(side_effect=lambda *a, **k: profundidades.append(len(connection.savepoint_ids)) or True)
        resumen = revision.revisar(AHORA)
        self.assertEqual(resumen.sistemas[0].alertas_generadas, 1)
        self.assertEqual((resumen.correos.enviados, profundidades), (1, [base]))


@tag("concurrencia")
@override_settings(CORREO_CONFIGURADO=True)
class RevisionCorreosFueraDeTransaccionTests(fabricas.ConCatalogoIot, TransactionTestCase):
    """«Fuera de toda transacción» en términos absolutos: dentro de `enviar_correo`, `connection.in_atomic_block` es falso. Hace falta un ``TransactionTestCase`` (un
    ``TestCase`` siempre corre dentro de una transacción); por eso lleva ``@tag("concurrencia")`` y se corre con ``--tag concurrencia``."""

    def setUp(self):
        fabricas.asegurar_datos_de_iot()
        from maestros.tests.fabricas import asegurar_datos_de_maestros

        asegurar_datos_de_maestros()
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero_con_geografia_propia("Norte", agronomo=laura)
        self.sistema = fabricas.sistema(self.norte)
        NodoCentral.objects.filter(sistema=self.sistema).update(ultima_comunicacion=AHORA - timedelta(minutes=10))
        self.en_bloque = []
        self.enterContext(
            mock.patch("core.correo.enviar_correo", side_effect=lambda *a, **k: self.en_bloque.append(connection.in_atomic_block) or True)
        )

    def test_regla_correos_revisar_llama_a_enviar_correo_sin_transaccion_abierta(self):
        """D-14, D-54 y «Correos»: `revisar` llama a `enviar_correo` con `connection.in_atomic_block` falso."""
        revision.revisar(AHORA)
        self.assertEqual(self.en_bloque, [False])

    def test_regla_correos_el_comando_llama_a_enviar_correo_sin_transaccion_abierta(self):
        """Igual, desde `python manage.py revision_iot --ahora …`."""
        call_command("revision_iot", "--ahora", "2026-11-23T12:00", stdout=StringIO())
        self.assertEqual(self.en_bloque, [False])
