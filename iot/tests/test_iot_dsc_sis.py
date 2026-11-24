# Pruebas de IOT-DSC-SIS · Desactivar Sistema IoT (docs/casos_de_uso/iot/sistema_iot.md, con «IOT-DSC-SIS, IOT-ACT-SIS e IOT-BAJ-SIS (IOT-06)» de «Cómo se aplica») y de lo que cita: D-78 (puntos 3 y 11), D-36 y D-28.
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicio que se prueba (iot/servicios/sistemas.py), tomado del módulo dentro de cada prueba:
#   desactivar_sistema_iot(actor, sistema_id, ahora) -> SistemaIoT          (``ahora`` es un parámetro más que el extracto: los servicios no leen la hora)
#   acciones_permitidas(actor, sistema)                                      (suma ``desactivar``, ``activar`` y ``baja``: D-30, ningún botón lleva a un 403)
# Errores: ``PermissionDenied`` (otro rol), ``Http404`` (sistema inexistente o fuera del alcance de consulta), ``ValidationError`` general: ``fuera_de_alcance`` (regla 1) y
# ``sistema_no_activo`` (precondición b).
# Cancela con ``comandos.cancelar_comando_incluido`` (IOT-05) y resuelve las alertas con ``AlertaIot.sistema`` = el sistema (``resolver_alerta_de_estado``).

import json
from unittest import mock

from django.core.cache import cache
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import Client, TestCase

from core.enlaces import resumen_de
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz
from inventario.tests.fabricas import perezoso
from iot.models import AlertaIot, Comando, Hardware, NodoCentral, RegistroComando, SistemaIoT
from iot.servicios import alertas_iot, revision
from iot.tests import fabricas
from iot.tests.escena_de_reglas import AHORA, ConEscenaDeReglas
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_tecnico, error_de

sistemas = perezoso("iot.servicios.sistemas")
TOKEN = "token-de-prueba-que-no-es-secreto"


class IotDscSisServicioTests(ConEscenaDeReglas, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-DSC-SIS."""

    def setUp(self):
        cache.clear()
        super().setUp()
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(token_resumen=resumen_de(TOKEN))
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.regla = fabricas.regla(self.temp, self.ventilador, self.encender, ultima_evaluacion="cumplida", contador_confirmacion=0)

    def desactivar(self, actor=None):
        return sistemas.desactivar_sistema_iot(actor or self.laura, self.sistema.pk, AHORA)

    def alerta(self, tipo, clave, descripcion="x", hardware=None):
        return alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, tipo, clave, descripcion, hardware=hardware).alerta

    def activas(self):
        return Alerta.objects.filter(estado_alerta="activa")

    # ---- postcondiciones ----

    def test_post_a_el_sistema_queda_desconectado_y_su_nodo_su_hardware_y_sus_reglas_no_cambian(self):
        """Postcondición a y regla 5: estado «desconectado»; el nodo, el hardware (también uno fuera de servicio) y las reglas (con su evaluación) quedan como estaban."""
        type(self.ventana).objects.filter(pk=self.ventana.pk).update(estado_hardware="fuera_de_servicio")
        estados = dict(Hardware.objects.values_list("pk", "estado_hardware"))
        self.desactivar()
        self.sistema.refresh_from_db()
        self.assertEqual(self.sistema.estado_sistema, "desconectado")
        self.assertEqual(dict(Hardware.objects.values_list("pk", "estado_hardware")), estados)
        self.regla.refresh_from_db()
        self.assertEqual((self.regla.estado_regla, self.regla.ultima_evaluacion), ("activa", "cumplida"))
        self.assertIsNotNone(self.sistema.token_resumen)

    def test_post_b_los_comandos_pendientes_pasan_a_cancelado_con_su_bitacora(self):
        """Postcondición b y D-78 punto 3: cada pendiente queda «cancelado» con ``resuelto_en`` = ahora y su ``RegistroComando`` «cancelado», con quien desactivó como responsable; no se espera a que venza un intento en curso."""
        manual = fabricas.comando(self.ventilador, self.encender)
        en_curso = fabricas.comando(self.ventana, self.fijar, valor_comando=40, cantidad_intentos=1, ultimo_intento_en=AHORA)
        resuelto = fabricas.comando(self.ventilador, self.apagar, estado="ejecutado")
        self.desactivar()
        for comando in (manual, en_curso):
            comando.refresh_from_db()
            self.assertEqual((comando.estado_comando, comando.resuelto_en), ("cancelado", AHORA))
        resuelto.refresh_from_db()
        self.assertEqual(resuelto.estado_comando, "ejecutado")
        registros = RegistroComando.objects.filter(resultado="cancelado")
        self.assertEqual({r.comando_id for r in registros}, {manual.pk, en_curso.pk})
        self.assertEqual({r.responsable_id for r in registros}, {self.laura.pk})

    def test_post_c_resuelve_las_alertas_activas_del_sistema_y_solo_esas(self):
        """Postcondición c: las alertas con ``AlertaIot.sistema`` = este sistema pasan a «resuelta» (sin actividad, nodo sin comunicación, dispositivo no registrado); las de otro invernadero y la del Técnico no se tocan."""
        propias = [
            self.alerta("iot_dispositivo_sin_actividad", f"hw:{self.temp.pk}", hardware=self.temp),
            self.alerta("iot_nodo_sin_comunicacion", f"nodo:{self.nodo.pk}", hardware=self.nodo),
            self.alerta("iot_dispositivo_no_registrado", "id:co2"),
        ]
        api_alertas.sincronizar_alertas_de_personal(self.norte, roles=["tecnico"])  # «invernadero sin Técnico activo»: no es una alerta del IoT
        del_tecnico = Alerta.objects.get(tipo_alerta="sin_tecnico", estado_alerta="activa")
        sur = crear_invernadero_sur()
        sistema_sur = fabricas.sistema(sur)
        ajena = alertas_iot.asegurar_alerta_iot(sur.pk, sistema_sur, "iot_dispositivo_no_registrado", "id:co2", "x").alerta
        self.desactivar()
        for alerta in propias:
            alerta.refresh_from_db()
            self.assertEqual(alerta.estado_alerta, "resuelta")
        for alerta in (del_tecnico, ajena):
            alerta.refresh_from_db()
            self.assertEqual(alerta.estado_alerta, "activa")

    def test_post_d_audita_un_registro_con_el_cambio_de_estado_los_comandos_y_las_alertas(self):
        """Postcondición d y D-36 (un registro por caso de uso): ``desactivacion_sistema_iot`` con el usuario, el cambio de estado y, como afectados, el sistema, cada comando y su registro de bitácora y cada alerta resuelta."""
        comando = fabricas.comando(self.ventilador, self.encender)
        alerta = self.alerta("iot_dispositivo_no_registrado", "id:co2")
        self.desactivar()
        auditoria = RegistroAuditoria.objects.get(accion="desactivacion_sistema_iot")
        self.assertEqual(auditoria.usuario_id, self.laura.pk)
        self.assertEqual(auditoria.detalle["cambios"]["estado_sistema"], {"antes": "activo", "despues": "desconectado"})
        afectados = {(a["modelo"], a["id"]) for a in auditoria.afectados}
        self.assertTrue({("iot.sistemaiot", self.sistema.pk), ("iot.comando", comando.pk), ("iot.registrocomando", RegistroComando.objects.get().pk), ("maestros.alerta", alerta.pk)} <= afectados)

    def test_garantia_si_falla_la_auditoria_no_se_cancela_ni_se_resuelve_nada(self):
        """Atomicidad: si falla la auditoría, el sistema sigue activo, el comando pendiente y la alerta activa."""
        comando = fabricas.comando(self.ventilador, self.encender)
        alerta = self.alerta("iot_dispositivo_no_registrado", "id:co2")
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.desactivar()
        self.sistema.refresh_from_db(), comando.refresh_from_db(), alerta.refresh_from_db()
        self.assertEqual((self.sistema.estado_sistema, comando.estado_comando, alerta.estado_alerta), ("activo", "pendiente", "activa"))
        self.assertEqual(RegistroComando.objects.filter(resultado="cancelado").count(), 0)

    # ---- precondiciones y regla 1 ----

    def test_regla_1_otros_roles_reciben_403_y_un_sistema_ajeno_o_inexistente_da_404(self):
        """Precondición a y D-28."""
        for otro in (crear_tecnico(), crear_capataz()):
            with self.assertRaises(PermissionDenied):
                self.desactivar(actor=otro)
        with self.assertRaises(Http404):
            self.desactivar(actor=crear_agronomo("otro@infoponia.com"))
        with self.assertRaises(Http404):
            sistemas.desactivar_sistema_iot(self.laura, 99999, AHORA)

    def test_regla_1_el_gerente_no_desactiva_con_agronomo_activo_y_si_sin_el(self):
        """Regla 1: el Gerente opera solo los invernaderos sin Agrónomo activo."""
        self.assertEqual(codigos_de(error_de(lambda: self.desactivar(actor=self.gerente)), NON_FIELD_ERRORS), ["fuera_de_alcance"])
        self.sistema.refresh_from_db()
        self.assertEqual(self.sistema.estado_sistema, "activo")
        self.norte.agronomo = None
        self.norte.save()
        self.desactivar(actor=self.gerente)
        self.assertEqual(RegistroAuditoria.objects.get(accion="desactivacion_sistema_iot").usuario_id, self.gerente.pk)

    def test_precondicion_b_solo_se_desactiva_un_sistema_activo(self):
        """Precondición b: uno desconectado o dado de baja no se desactiva."""
        for estado in ("desconectado", "inactivo"):
            SistemaIoT.objects.filter(pk=self.sistema.pk).update(estado_sistema=estado)
            self.assertEqual(codigos_de(error_de(self.desactivar), NON_FIELD_ERRORS), ["sistema_no_activo"], estado)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="desactivacion_sistema_iot").count(), 0)

    # ---- regla 2 (desconectado), regla 3 y regla 5 ----

    def test_regla_2_la_api_responde_403_y_no_registra_la_comunicacion(self):
        """Regla 2: el sistema desconectado no acepta telemetría, estados ni anuncios: la API responde 403 ``sistema_desconectado`` y el nodo no se comunica."""
        self.desactivar()
        respuesta = Client(enforce_csrf_checks=True).post("/api/iot/v1/lecturas", data=b'{"lecturas": []}', content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        self.assertEqual((respuesta.status_code, json.loads(respuesta.content)["error"]), (403, "sistema_desconectado"))
        self.nodo.refresh_from_db()
        self.assertIsNone(self.nodo.ultima_comunicacion)

    def test_regla_2_no_se_emiten_comandos_ni_se_generan_alertas_del_sistema_y_la_revision_lo_saltea(self):
        """Regla 2: no se emiten comandos (``sistema_no_activo``) y la revisión periódica no revisa su nodo ni sus equipos (no genera «dispositivo sin actividad» ni «nodo sin comunicación»)."""
        from iot.servicios import comandos

        self.desactivar()
        self.assertEqual(codigos_de(error_de(lambda: comandos.emitir_comando(self.laura, self.ventilador.pk, comandos.DatosDeComando(accion_id=self.encender.pk), AHORA)), NON_FIELD_ERRORS), ["sistema_no_activo"])
        fabricas.telemetria(self.temp, 21, medida_en=AHORA.replace(hour=1))
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=AHORA.replace(hour=1))
        resumen = revision.revisar(AHORA.replace(hour=23))
        self.assertEqual(len(resumen.sistemas), 0)
        self.assertEqual(AlertaIot.objects.count(), 0)

    def test_regla_3_los_comandos_cancelados_no_se_reintentan_ni_generan_alertas(self):
        """Regla 3: un comando cancelado no genera «comando fallido» ni otra alerta, y el retiro del nodo (que ya no llega) no lo entrega."""
        fabricas.comando(self.ventilador, self.encender, cantidad_intentos=1, ultimo_intento_en=AHORA)
        self.desactivar()
        self.assertEqual(Alerta.objects.filter(tipo_alerta="iot_comando_fallido").count(), 0)
        self.assertEqual(Comando.objects.filter(estado_comando="pendiente").count(), 0)

    def test_regla_5_no_cancela_las_ordenes_de_mantenimiento_a_realizar(self):
        """Regla 5: desactivar no toca las órdenes de mantenimiento. Hasta IOT-07 no existen: ``ordenes_a_realizar_del_sistema`` queda vacía y la desactivación no la consulta ni la cambia."""
        with mock.patch("iot.servicios.sistemas.ordenes_a_realizar_del_sistema", return_value=["orden"]) as ordenes:
            self.desactivar()
        ordenes.assert_not_called()

    # ---- D-30: los botones ----

    def test_d30_quien_opera_ve_desactivar_solo_con_el_sistema_activo(self):
        """D-30: ``desactivar`` para quien opera y con el sistema activo; con el sistema desconectado se ofrece ``activar``; el Gerente con Agrónomo activo, ninguna."""
        self.assertIn("desactivar", sistemas.acciones_permitidas(self.laura, self.sistema))
        self.assertNotIn("activar", sistemas.acciones_permitidas(self.laura, self.sistema))
        self.assertEqual(sistemas.acciones_permitidas(self.gerente, self.sistema), frozenset())
        self.desactivar()
        self.sistema.refresh_from_db()
        acciones = sistemas.acciones_permitidas(self.laura, self.sistema)
        self.assertIn("activar", acciones)
        self.assertNotIn("desactivar", acciones)


def crear_invernadero_sur():
    """Un invernadero de otro Agrónomo."""
    from maestros.tests.fabricas import crear_invernadero

    return crear_invernadero("Sur", agronomo=crear_agronomo("sur@infoponia.com"))
