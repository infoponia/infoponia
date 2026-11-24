# Pruebas de IOT-BAJ-RGL · Baja Regla de Actuación (docs/casos_de_uso/iot/reglas_de_actuacion.md, con «Cómo se aplica en la ronda «IoT 1»») y de lo que cita: D-36 y D-28.
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicio que se prueba (iot/servicios/reglas.py), tomado del módulo dentro de cada prueba:
#   baja_regla(actor, regla_id, ahora) -> ReglaActuacion
# Errores: ``PermissionDenied`` (otro rol), ``Http404`` (regla inexistente o fuera del alcance de consulta), ``ValidationError`` general:
#   ``fuera_de_alcance`` (regla 1), ``regla_no_activa`` (precondición b).

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


class IotBajRglServicioTests(ConEscenaDeReglas, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-BAJ-RGL."""

    def setUp(self):
        super().setUp()
        self.regla = self.alta()

    def baja(self, actor=None, regla=None):
        return reglas.baja_regla(actor or self.laura, (regla or self.regla).pk, AHORA)

    def test_post_a_la_regla_queda_inactiva_y_conserva_su_historial(self):
        """Postcondición a: baja lógica, con sus comandos y las lecturas que la dispararon intactos."""
        lectura = fabricas.telemetria(self.temp, 40)
        self.regla.telemetrias.add(lectura)
        comando = fabricas.comando(self.ventilador, self.encender, estado="ejecutado", regla=self.regla)
        self.baja()
        self.regla.refresh_from_db()
        self.assertEqual(self.regla.estado_regla, "inactiva")
        self.assertEqual(list(self.regla.telemetrias.all()), [lectura])
        comando.refresh_from_db()
        self.assertEqual(comando.regla_id, self.regla.pk)

    def test_post_b_audita_la_baja_con_el_cambio_de_estado(self):
        """Postcondición b y D-36: ``baja_regla_actuacion``, el usuario, la regla y el cambio de estado."""
        self.baja()
        auditoria = RegistroAuditoria.objects.get(accion="baja_regla_actuacion")
        self.assertEqual(auditoria.usuario_id, self.laura.pk)
        self.assertEqual([(a["modelo"], a["id"]) for a in auditoria.afectados], [("iot.reglaactuacion", self.regla.pk)])
        self.assertEqual(auditoria.detalle["cambios"]["estado_regla"], {"antes": "activa", "despues": "inactiva"})

    def test_garantia_si_falla_la_auditoria_la_regla_sigue_activa(self):
        """Atomicidad."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.baja()
        self.regla.refresh_from_db()
        self.assertEqual(self.regla.estado_regla, "activa")

    def test_regla_1_otros_roles_reciben_403_y_una_regla_ajena_da_404(self):
        """Precondición a y D-28."""
        for otro in (crear_tecnico(), crear_capataz()):
            with self.assertRaises(PermissionDenied):
                self.baja(actor=otro)
        with self.assertRaises(Http404):
            self.baja(actor=crear_agronomo("otro@infoponia.com"))
        with self.assertRaises(Http404):
            reglas.baja_regla(self.laura, 99999, AHORA)

    def test_regla_1_el_gerente_no_da_de_baja_con_agronomo_activo_y_si_sin_el(self):
        """Regla 1 (la de IOT-DSC-SIS)."""
        self.assertEqual(codigos_de(error_de(lambda: self.baja(actor=self.gerente)), NON_FIELD_ERRORS), ["fuera_de_alcance"])
        self.norte.agronomo = None
        self.norte.save()
        self.baja(actor=self.gerente)
        self.assertEqual(RegistroAuditoria.objects.get(accion="baja_regla_actuacion").usuario_id, self.gerente.pk)

    def test_precondicion_b_una_regla_inactiva_no_se_da_de_baja_otra_vez(self):
        """Precondición b: la regla tiene que estar activa."""
        self.baja()
        self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["regla_no_activa"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_regla_actuacion").count(), 1)

    def test_regla_2_los_comandos_pendientes_de_la_regla_siguen_su_curso(self):
        """Regla 2: la baja no cancela lo que la regla ya emitió; el comando sigue pendiente y no se le agrega ningún registro de bitácora."""
        comando = fabricas.comando(self.ventilador, self.encender, regla=self.regla)
        self.baja()
        comando.refresh_from_db()
        self.assertEqual(comando.estado_comando, "pendiente")
        self.assertEqual(Comando.objects.filter(estado_comando="pendiente").count(), 1)

    def test_regla_4_se_reactiva_con_modificar_y_vuelve_a_poder_darse_de_baja(self):
        """Regla 4: la reactivación es de IOT-MOD-RGL; después, la baja vuelve a ser posible."""
        self.baja()
        reglas.reactivar_regla(self.laura, self.regla.pk, AHORA)
        self.baja()
        self.assertEqual(ReglaActuacion.objects.get().estado_regla, "inactiva")
