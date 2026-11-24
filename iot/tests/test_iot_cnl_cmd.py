# Pruebas de IOT-CNL-CMD · Cancelar Comando (docs/casos_de_uso/iot/cancelar_comando.md, con «Cómo se aplica en la ronda «IoT 1»») y de lo que cita: D-78 (puntos 3, 6 y 11), D-36 y D-28.
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban (iot/servicios/comandos.py), tomados del módulo dentro de cada prueba:
#   cancelar_comando(actor, comando_id, ahora) -> Comando
#   cancelar_comando_incluido(comando, motivo, ahora, responsable=None) -> RegistroComando     (``ahora`` es un parámetro más que el extracto: los servicios no leen la hora)
#   segundos_para_cancelar(comando, ahora) -> int                                               (0 si se puede cancelar; si no, cuánto falta: ``ultimo_intento_en + intervalo - ahora``, D-78 punto 6)
#   registrar_resultado(sistema_id, comando_id, ResultadoRecibido(resultado, detalle, estado, informado_en), ahora) -> ResultadoDeComando(resultado, estado_comando)   (paso 4; acá solo «ya_resuelto»)
# Errores: ``PermissionDenied`` (otro rol), ``Http404`` (comando inexistente o fuera del alcance de consulta), ``ValidationError`` general: ``fuera_de_alcance`` (regla 1),
# ``comando_no_pendiente`` (precondición b) y ``comando_en_curso`` (reglas 2 y 5: el mensaje dice cuánto falta).

from datetime import datetime, timedelta, timezone as zona
from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import Comando, NodoCentral, RegistroComando
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.servicios import configuracion
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_invernadero, crear_tecnico, error_de

comandos = perezoso("iot.servicios.comandos")
AHORA = datetime(2026, 11, 23, 15, 0, tzinfo=zona.utc)


class IotCnlCmdServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-CNL-CMD."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        self.tipo = fabricas.tipo_actuador("Extractor")
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/extractor")
        self.encender = self.tipo.acciones.order_by("id").first()
        self.comando = fabricas.comando(self.actuador, self.encender)  # pendiente, sin retirar (0 intentos)

    # ---- ayudas ----

    def retirado_hace(self, segundos, intentos=1):
        """El nodo retiró el comando hace ``segundos``: está en su intento ``intentos`` (la espera es de 60 s con la configuración inicial)."""
        Comando.objects.filter(pk=self.comando.pk).update(cantidad_intentos=intentos, ultimo_intento_en=AHORA - timedelta(seconds=segundos))

    def cancelar(self, actor=None, comando=None):
        return comandos.cancelar_comando(actor or self.laura, (comando or self.comando).pk, AHORA)

    def general(self, llamada):
        return error_de(llamada)

    def sigue_pendiente(self):
        self.comando.refresh_from_db()
        self.assertEqual(self.comando.estado_comando, "pendiente")
        self.assertEqual(RegistroComando.objects.filter(resultado="cancelado").count(), 0)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_comando").count(), 0)

    # ---- postcondiciones ----

    def test_post_a_el_comando_queda_cancelado_con_su_momento_de_resolucion(self):
        """Postcondición a: estado «cancelado» y ``resuelto_en`` = ahora (lo exige la restricción de la base)."""
        devuelto = self.cancelar()
        self.comando.refresh_from_db()
        self.assertEqual((self.comando.estado_comando, self.comando.resuelto_en, devuelto.pk), ("cancelado", AHORA, self.comando.pk))

    def test_post_b_crea_el_registro_de_bitacora_de_la_cancelacion(self):
        """Postcondición b y D-78 punto 3: un RegistroComando «cancelado», sin lote, con el actuador y la acción en la descripción y quien canceló como responsable."""
        self.cancelar()
        registro = RegistroComando.objects.get()
        self.assertEqual((registro.comando_id, registro.resultado, registro.numero_intento), (self.comando.pk, "cancelado", None))
        self.assertEqual((registro.tipo_evento, registro.invernadero_id, registro.lote_id, registro.responsable_id), ("comando", self.norte.pk, None, self.laura.pk))
        for texto in ("Extractor", "norte/extractor", "Encender", "cancelado"):
            self.assertIn(texto, registro.descripcion_evento)

    def test_post_c_audita_la_cancelacion_con_el_cambio_de_estado(self):
        """Postcondición c y D-36: ``cancelacion_comando``, el usuario, los afectados (comando y registro) y el cambio de estado de pendiente a cancelado."""
        self.cancelar()
        auditoria = RegistroAuditoria.objects.get(accion="cancelacion_comando")
        self.assertEqual(auditoria.usuario_id, self.laura.pk)
        self.assertEqual({(a["modelo"], a["id"]) for a in auditoria.afectados}, {("iot.comando", self.comando.pk), ("iot.registrocomando", RegistroComando.objects.get().pk)})
        self.assertEqual(auditoria.detalle["cambios"]["estado_comando"], {"antes": "pendiente", "despues": "cancelado"})

    def test_garantia_si_falla_la_auditoria_no_se_cancela_nada(self):
        """Atomicidad: si falla la auditoría, el comando sigue pendiente y no queda el registro."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.cancelar()
        self.sigue_pendiente()

    # ---- precondición a, regla 1 (alcance) y regla 3 ----

    def test_regla_1_otros_roles_reciben_403(self):
        """Precondición a: solo Agrónomo y Gerente activos."""
        for otro in (crear_tecnico(), crear_capataz()):
            with self.assertRaises(PermissionDenied):
                self.cancelar(actor=otro)
        self.laura.is_active = False
        self.laura.save()
        with self.assertRaises(PermissionDenied):
            self.cancelar()
        self.sigue_pendiente()

    def test_regla_1_un_agronomo_de_otro_invernadero_y_un_comando_inexistente_dan_404(self):
        """D-28: fuera del alcance de consulta, o inexistente, el comando no existe."""
        with self.assertRaises(Http404):
            self.cancelar(actor=crear_agronomo("otro@infoponia.com"))
        with self.assertRaises(Http404):
            comandos.cancelar_comando(self.laura, 99999, AHORA)

    def test_regla_1_el_gerente_no_cancela_con_agronomo_activo_y_si_sin_el(self):
        """Regla 1 (la de IOT-DSC-SIS): el Gerente opera solo los invernaderos sin Agrónomo activo."""
        self.assertEqual(codigos_de(self.general(lambda: self.cancelar(actor=self.gerente)), NON_FIELD_ERRORS), ["fuera_de_alcance"])
        self.sigue_pendiente()
        self.norte.agronomo = None
        self.norte.save()
        self.cancelar(actor=self.gerente)
        self.assertEqual(RegistroAuditoria.objects.get(accion="cancelacion_comando").usuario_id, self.gerente.pk)
        self.assertEqual(RegistroComando.objects.get().responsable_id, self.gerente.pk)

    def test_regla_3_se_cancelan_tambien_los_comandos_de_una_regla_de_actuacion(self):
        """Regla 3: manuales y automáticos."""
        regla = fabricas.regla(fabricas.sensor(self.sistema), self.actuador)
        Comando.objects.filter(pk=self.comando.pk).update(regla=regla)
        self.cancelar()
        self.comando.refresh_from_db()
        self.assertEqual(self.comando.estado_comando, "cancelado")

    # ---- precondición b ----

    def test_precondicion_b_un_comando_resuelto_no_se_cancela(self):
        """Precondición b: el comando tiene que estar pendiente (ejecutado, fallido o cancelado ya no)."""
        for estado in ("ejecutado", "fallido", "cancelado"):
            Comando.objects.filter(pk=self.comando.pk).update(estado_comando=estado, resuelto_en=AHORA)
            self.assertEqual(codigos_de(self.general(self.cancelar), NON_FIELD_ERRORS), ["comando_no_pendiente"], estado)
        self.assertEqual(RegistroComando.objects.count(), 0)

    # ---- regla 2 y regla 5 ----

    def test_regla_2_un_comando_que_el_nodo_no_retiro_se_cancela(self):
        """Regla 2 y D-78 punto 6: sin retirar (0 intentos), se cancela."""
        self.assertEqual(comandos.segundos_para_cancelar(self.comando, AHORA), 0)
        self.cancelar()

    def test_regla_2_un_comando_con_el_ultimo_intento_vencido_se_cancela(self):
        """Regla 2: «cuando su último intento ya venció sin respuesta» (60 s con la configuración inicial)."""
        self.retirado_hace(61)
        self.comando.refresh_from_db()
        self.assertEqual(comandos.segundos_para_cancelar(self.comando, AHORA), 0)
        self.cancelar()

    def test_regla_2_justo_al_vencer_el_intento_ya_se_cancela(self):
        """D-78 punto 6: ``ultimo_intento_en + intervalo <= ahora`` (el límite inclusive)."""
        self.retirado_hace(60)
        self.cancelar()

    def test_regla_2_dentro_de_la_espera_no_se_cancela_y_dice_cuanto_falta(self):
        """Regla 2: mientras el nodo puede estar ejecutándolo no se cancela, y el mensaje informa cuánto falta (60 − 20 = 40 s)."""
        self.retirado_hace(20)
        self.comando.refresh_from_db()
        self.assertEqual(comandos.segundos_para_cancelar(self.comando, AHORA), 40)
        error = self.general(self.cancelar)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["comando_en_curso"])
        self.assertIn("en 40 s", error.messages[0])
        self.sigue_pendiente()

    def test_regla_2_el_intervalo_es_el_de_la_configuracion_operativa(self):
        """Regla 2: la espera es ``segundos_intervalo_reintento`` de la Configuración Operativa, leída en cada uso."""
        config = configuracion.obtener()
        config.segundos_intervalo_reintento = 600
        config.save()
        self.retirado_hace(120)
        self.comando.refresh_from_db()
        self.assertEqual(comandos.segundos_para_cancelar(self.comando, AHORA), 480)

    def test_regla_5_si_el_nodo_acaba_de_retirarlo_no_se_cancela_y_se_informa(self):
        """Regla 5: entre que se mostró el botón y se confirmó, el nodo retiró el comando; el servicio lo ve bajo el bloqueo y responde con el texto de «Cómo se aplica»."""
        self.assertEqual(comandos.segundos_para_cancelar(self.comando, AHORA), 0)  # la pantalla lo veía cancelable
        self.retirado_hace(1)
        error = self.general(self.cancelar)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["comando_en_curso"])
        self.assertIn("El nodo acaba de retirar el comando: no se canceló. Podés cancelarlo cuando venza el intento (en 59 s).", error.messages[0])
        self.sigue_pendiente()

    # ---- regla 4 ----

    def test_regla_4_un_cancelado_no_genera_alertas_ni_cambia_el_actuador(self):
        """Regla 4: un comando cancelado no genera alertas ni órdenes de mantenimiento y no toca al actuador."""
        self.cancelar()
        self.actuador.refresh_from_db()
        self.assertEqual((Alerta.objects.count(), self.actuador.estado_hardware), (0, "activo"))

    def test_regla_4_el_actuador_queda_libre_para_otro_comando(self):
        """Objetivo del caso de uso: liberar al actuador para poder enviarle otro comando."""
        self.cancelar()
        fabricas.comando(self.actuador, self.encender)  # el índice único de pendientes ya no choca

    def test_regla_4_un_resultado_posterior_del_nodo_es_ya_resuelto_y_no_cambia_nada(self):
        """Regla 4 y extensión 4d de IOT-RSV-CMD: el resultado tardío de un cancelado se ignora (``ya_resuelto``, con su estado final)."""
        self.retirado_hace(100, intentos=1)
        self.cancelar()
        respuesta = comandos.registrar_resultado(
            self.sistema.pk, self.comando.pk, comandos.ResultadoRecibido(resultado="ejecutado", detalle="", estado=None, informado_en=None), AHORA
        )
        self.assertEqual((respuesta.resultado, respuesta.estado_comando), ("ya_resuelto", "cancelado"))
        self.comando.refresh_from_db()
        self.assertEqual((self.comando.estado_comando, RegistroComando.objects.count()), ("cancelado", 1))

    # ---- cancelar_comando_incluido ----

    def test_incluido_cancela_sin_alcance_ni_auditoria_propia_y_deja_su_registro_con_el_motivo(self):
        """``cancelar_comando_incluido``: la misma cancelación para quien cancela dentro de otro caso de uso (2c de IOT-RSV-CMD, IOT-06): sin verificación de alcance ni auditoría propia, y
        con el motivo en la bitácora. Devuelve el registro."""
        registro = comandos.cancelar_comando_incluido(self.comando, "Actuador fuera de servicio", AHORA)
        self.comando.refresh_from_db()
        self.assertEqual((self.comando.estado_comando, self.comando.resuelto_en), ("cancelado", AHORA))
        self.assertEqual((registro.resultado, registro.responsable_id), ("cancelado", None))
        self.assertIn("Actuador fuera de servicio", registro.descripcion_evento)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_comando").count(), 0)

    def test_incluido_cancela_tambien_uno_que_esta_en_curso(self):
        """Quien cancela como parte de otro caso de uso (el actuador ya no está activo, se desactiva el sistema) no espera al intento."""
        self.retirado_hace(5)
        self.comando.refresh_from_db()
        comandos.cancelar_comando_incluido(self.comando, "Sistema desactivado", AHORA)
        self.comando.refresh_from_db()
        self.assertEqual(self.comando.estado_comando, "cancelado")

    def test_incluido_con_responsable_lo_deja_en_la_bitacora(self):
        """D-78 punto 3: el responsable es quien canceló (nulo si fue InfoPonia o el nodo)."""
        registro = comandos.cancelar_comando_incluido(self.comando, "Sistema desactivado", AHORA, responsable=self.laura)
        self.assertEqual(registro.responsable_id, self.laura.pk)

    def test_incluido_un_comando_que_no_esta_pendiente_es_un_error_de_programacion(self):
        """El que llama ya bloqueó y verificó; un comando resuelto es un ``ValueError``, no un error de usuario."""
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="ejecutado", resuelto_en=AHORA)
        self.comando.refresh_from_db()
        with self.assertRaises(ValueError):
            comandos.cancelar_comando_incluido(self.comando, "x", AHORA)
