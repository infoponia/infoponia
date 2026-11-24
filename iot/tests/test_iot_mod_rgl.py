# Pruebas de IOT-MOD-RGL · Modificar Regla de Actuación, con reactivar (docs/casos_de_uso/iot/reglas_de_actuacion.md, con «Cómo se aplica en la ronda «IoT 1»») y de lo que cita: D-82, D-36 y D-28.
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban (iot/servicios/reglas.py), tomados del módulo dentro de cada prueba (``DatosDeRegla`` y ``alta_regla``: ver test_iot_alt_rgl.py):
#   modificar_regla(actor, regla_id, datos, ahora) -> ReglaActuacion     (cambia condición, acción y valor; el sensor y el actuador de ``datos`` se ignoran, regla 3)
#   reactivar_regla(actor, regla_id, ahora) -> ReglaActuacion
# Errores: ``PermissionDenied`` (otro rol), ``Http404`` (regla inexistente o fuera del alcance de consulta), ``ValidationError``:
#   general: ``fuera_de_alcance`` (regla 1), ``sistema_dado_de_baja`` (precondición b), ``regla_inactiva`` (regla 6: una inactiva no se modifica), ``regla_no_inactiva`` (reactivar una activa),
#   ``regla_repetida`` (regla 5 y 6), ``sensor_no_activo`` y ``actuador_no_activo`` (regla 6); por campo ``condicion``, ``accion`` y ``valor``: los códigos del alta.

from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz
from iot.models import Comando, ReglaActuacion
from iot.tests import fabricas
from iot.tests.escena_de_reglas import AHORA, ConEscenaDeReglas, reglas
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_tecnico, error_de


class IotModRglServicioTests(ConEscenaDeReglas, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-MOD-RGL."""

    def setUp(self):
        super().setUp()
        self.regla = self.alta()

    def modificar(self, actor=None, regla=None, **datos):
        return reglas.modificar_regla(actor or self.laura, (regla or self.regla).pk, self.datos(**datos), AHORA)

    def dar_de_baja(self, regla=None):
        ReglaActuacion.objects.filter(pk=(regla or self.regla).pk).update(estado_regla="inactiva")

    def reactivar(self, actor=None, regla=None):
        return reglas.reactivar_regla(actor or self.laura, (regla or self.regla).pk, AHORA)

    # ---- postcondiciones ----

    def test_post_a_actualiza_la_condicion_la_accion_y_el_valor(self):
        """Postcondición a: la condición, la acción o el valor a aplicar cambian."""
        self.modificar(condicion="vuelve_al_rango", accion=self.apagar)
        self.regla.refresh_from_db()
        self.assertEqual((self.regla.condicion, self.regla.accion_id, self.regla.aplicar_valor), ("vuelve_al_rango", self.apagar.pk, None))
        valor = self.alta(actuador=self.ventana, valor="10")
        self.modificar(regla=valor, actuador=self.ventana, valor="70")
        valor.refresh_from_db()
        self.assertEqual(valor.aplicar_valor, 70)

    def test_post_b_reactivar_deja_la_regla_activa(self):
        """Postcondición b: la regla dada de baja vuelve a «activa»."""
        self.dar_de_baja()
        self.reactivar()
        self.regla.refresh_from_db()
        self.assertEqual(self.regla.estado_regla, "activa")

    def test_post_c_audita_los_cambios_con_antes_y_despues(self):
        """Postcondición c y D-36: ``modificacion_regla_actuacion`` con el usuario, la regla y el antes y el después de lo que cambió (nada de lo que no cambió)."""
        self.modificar(condicion="baja_del_minimo", accion=self.apagar)
        auditoria = RegistroAuditoria.objects.get(accion="modificacion_regla_actuacion")
        self.assertEqual(auditoria.usuario_id, self.laura.pk)
        self.assertEqual([(a["modelo"], a["id"]) for a in auditoria.afectados], [("iot.reglaactuacion", self.regla.pk)])
        self.assertEqual(auditoria.detalle["cambios"]["condicion"], {"antes": "supera_maximo", "despues": "baja_del_minimo"})
        self.assertEqual(set(auditoria.detalle["cambios"]), {"condicion", "accion"})
        self.assertNotIn("reactivada", auditoria.detalle.get("datos", {}))

    def test_post_c_reactivar_audita_el_cambio_de_estado_con_datos_reactivada(self):
        """Postcondición c: al reactivar, el cambio de estado y ``datos.reactivada``, con la misma acción de auditoría que la modificación."""
        self.dar_de_baja()
        self.reactivar()
        auditoria = RegistroAuditoria.objects.get(accion="modificacion_regla_actuacion")
        self.assertEqual(auditoria.detalle["cambios"]["estado_regla"], {"antes": "inactiva", "despues": "activa"})
        self.assertIs(auditoria.detalle["datos"]["reactivada"], True)

    def test_garantia_si_falla_la_auditoria_no_se_cambia_nada(self):
        """Atomicidad: si falla la auditoría, la regla queda como estaba."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.modificar(condicion="baja_del_minimo")
        self.regla.refresh_from_db()
        self.assertEqual(self.regla.condicion, "supera_maximo")

    def test_regla_d28_sin_cambios_no_se_escribe_ni_se_audita(self):
        """D-28: una modificación sin cambios no guarda ni audita, y tampoco reinicia la evaluación."""
        ReglaActuacion.objects.filter(pk=self.regla.pk).update(ultima_evaluacion="cumplida", contador_confirmacion=2)
        self.modificar()
        self.regla.refresh_from_db()
        self.assertEqual((self.regla.ultima_evaluacion, self.regla.contador_confirmacion), ("cumplida", 2))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_regla_actuacion").count(), 0)

    # ---- alcance y precondiciones ----

    def test_regla_1_otros_roles_reciben_403_y_una_regla_ajena_da_404(self):
        """Precondición a y D-28: solo Agrónomo y Gerente activos; fuera del alcance de consulta, o inexistente, la regla no existe."""
        for otro in (crear_tecnico(), crear_capataz()):
            with self.assertRaises(PermissionDenied):
                self.modificar(actor=otro)
        with self.assertRaises(Http404):
            self.modificar(actor=crear_agronomo("otro@infoponia.com"))
        with self.assertRaises(Http404):
            reglas.modificar_regla(self.laura, 99999, self.datos(), AHORA)

    def test_regla_1_el_gerente_no_modifica_con_agronomo_activo_y_si_sin_el(self):
        """Regla 1 (la de IOT-DSC-SIS)."""
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(actor=self.gerente, condicion="baja_del_minimo")), NON_FIELD_ERRORS), ["fuera_de_alcance"])
        self.norte.agronomo = None
        self.norte.save()
        self.modificar(actor=self.gerente, condicion="baja_del_minimo")
        self.assertEqual(RegistroAuditoria.objects.get(accion="modificacion_regla_actuacion").usuario_id, self.gerente.pk)

    def test_precondicion_b_con_el_sistema_dado_de_baja_no_se_modifica(self):
        """Precondición b: el sistema está activo o desconectado (desconectado sí: regla 9 del alta)."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        self.modificar(condicion="baja_del_minimo")
        self.sistema.estado_sistema = "inactivo"
        self.sistema.save()
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(condicion="vuelve_al_rango")), NON_FIELD_ERRORS), ["sistema_dado_de_baja"])

    # ---- reglas 2 y 3 ----

    def test_regla_2_la_condicion_la_accion_y_el_valor_siguen_las_reglas_del_alta(self):
        """Regla 2: las reglas 3 a 5 y 7 del alta, con los mismos códigos (la acción y el valor, los de ``validar_comando``)."""
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(condicion="x")), "condicion"), ["condicion_invalida"])
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(accion=self.fijar)), "accion"), ["accion_no_disponible"])
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(valor="3")), "valor"), ["valor_de_mas"])
        ventana = self.alta(actuador=self.ventana, valor="10")
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(regla=ventana, actuador=self.ventana, valor="500")), "valor"), ["valor_invalido"])
        self.ventilador.acciones_incompatibles.add(self.apagar)
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(accion=self.apagar)), "accion"), ["accion_incompatible"])

    def test_regla_3_el_sensor_y_el_actuador_no_se_cambian(self):
        """Regla 3: aunque ``datos`` traiga otro sensor y otro actuador, la regla conserva los suyos (para otros, se da de alta una regla nueva)."""
        self.modificar(sensor=self.hum, actuador=self.ventana, condicion="baja_del_minimo", accion=self.encender)
        self.regla.refresh_from_db()
        self.assertEqual((self.regla.sensor_id, self.regla.actuador_id, self.regla.condicion), (self.temp.pk, self.ventilador.pk, "baja_del_minimo"))

    # ---- regla 4 (reinicio) ----

    def test_regla_4_modificar_reinicia_la_evaluacion_y_el_contador(self):
        """Regla 4 y «Disparo de una regla»: la regla vuelve a «sin evaluar» con la confirmación desde cero."""
        ReglaActuacion.objects.filter(pk=self.regla.pk).update(ultima_evaluacion="cumplida", contador_confirmacion=2)
        self.modificar(condicion="baja_del_minimo")
        self.regla.refresh_from_db()
        self.assertEqual((self.regla.ultima_evaluacion, self.regla.contador_confirmacion), ("sin_evaluar", 0))

    def test_regla_4_los_comandos_ya_emitidos_no_cambian(self):
        """Regla 4: lo que la regla ya emitió conserva su acción, su valor y su estado."""
        comando = fabricas.comando(self.ventilador, self.encender, regla=self.regla)
        self.modificar(condicion="baja_del_minimo", accion=self.apagar)
        comando.refresh_from_db()
        self.assertEqual((comando.accion_id, comando.estado_comando, comando.regla_id), (self.encender.pk, "pendiente", self.regla.pk))

    # ---- regla 5 (unicidad) ----

    def test_regla_5_no_puede_quedar_igual_a_otra_regla_activa(self):
        """Regla 5: sensor, condición y actuador de otra regla activa."""
        otra = self.alta(condicion="baja_del_minimo")
        error = error_de(lambda: self.modificar(regla=otra, condicion="supera_maximo"))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["regla_repetida"])
        self.assertIn("Ya hay una regla activa igual", error.messages[0])
        otra.refresh_from_db()
        self.assertEqual(otra.condicion, "baja_del_minimo")

    def test_regla_5_si_la_base_rechaza_el_cambio_el_error_es_el_mismo_y_no_un_500(self):
        """Dos cambios a la vez: el índice único parcial respalda y su ``IntegrityError`` se traduce a ``regla_repetida``."""
        otra = self.alta(condicion="baja_del_minimo")
        with mock.patch.object(reglas, "_regla_igual_activa", return_value=None):
            error = error_de(lambda: self.modificar(regla=otra, condicion="supera_maximo"))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["regla_repetida"])

    # ---- regla 6 (inactiva: solo se reactiva) ----

    def test_regla_6_una_regla_inactiva_no_se_modifica(self):
        """Regla 6: solo se reactiva."""
        self.dar_de_baja()
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(condicion="baja_del_minimo")), NON_FIELD_ERRORS), ["regla_inactiva"])

    def test_regla_6_reactivar_una_activa_no_se_puede(self):
        """Regla 6: reactivar es para las dadas de baja."""
        self.assertEqual(codigos_de(error_de(self.reactivar), NON_FIELD_ERRORS), ["regla_no_inactiva"])

    def test_regla_6_reactivar_reinicia_la_evaluacion(self):
        """Regla 6 y regla 4: la regla reactivada empieza de cero."""
        ReglaActuacion.objects.filter(pk=self.regla.pk).update(estado_regla="inactiva", ultima_evaluacion="cumplida", contador_confirmacion=3)
        self.reactivar()
        self.regla.refresh_from_db()
        self.assertEqual((self.regla.ultima_evaluacion, self.regla.contador_confirmacion), ("sin_evaluar", 0))

    def test_regla_6_reactivar_exige_el_sensor_y_el_actuador_activos(self):
        """Regla 6: «con el sensor dado de baja no se puede»; tampoco con el actuador fuera de servicio."""
        self.dar_de_baja()
        for modelo, campo, codigo in ((self.temp, "estado_hardware", "sensor_no_activo"), (self.ventilador, "estado_hardware", "actuador_no_activo")):
            for estado in ("inactivo", "fuera_de_servicio"):
                type(modelo).objects.filter(pk=modelo.pk).update(**{campo: estado})
                self.assertEqual(codigos_de(error_de(self.reactivar), NON_FIELD_ERRORS), [codigo], f"{codigo} {estado}")
            type(modelo).objects.filter(pk=modelo.pk).update(**{campo: "activo"})
        self.reactivar()

    def test_regla_6_reactivar_exige_que_no_haya_otra_regla_activa_igual(self):
        """Regla 6: mientras tanto se dio de alta otra igual."""
        self.dar_de_baja()
        self.alta()
        self.assertEqual(codigos_de(error_de(self.reactivar), NON_FIELD_ERRORS), ["regla_repetida"])

    def test_regla_6_reactivar_vuelve_a_validar_la_accion(self):
        """Regla 6 y «Comando válido»: si la acción dejó de estar disponible mientras tanto, no se reactiva y el error es el de ``validar_comando``."""
        self.dar_de_baja()
        self.encender.estado = "inactiva"
        self.encender.save()
        self.assertEqual(codigos_de(error_de(self.reactivar), "accion"), ["accion_no_disponible"])

    def test_regla_6_reactivar_con_el_sistema_dado_de_baja_no_se_puede(self):
        """Precondición b: un sistema dado de baja no reactiva sus reglas."""
        self.dar_de_baja()
        self.sistema.estado_sistema = "inactivo"
        self.sistema.save()
        self.assertEqual(codigos_de(error_de(self.reactivar), NON_FIELD_ERRORS), ["sistema_dado_de_baja"])
