# Pruebas de IOT-ACT-SIS · Activar Sistema IoT (docs/casos_de_uso/iot/sistema_iot.md, con «IOT-DSC-SIS, IOT-ACT-SIS e IOT-BAJ-SIS (IOT-06)» de «Cómo se aplica») y de lo que cita: D-78 (punto 8), D-36 y D-28.
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicio que se prueba (iot/servicios/sistemas.py), tomado del módulo dentro de cada prueba:
#   activar_sistema_iot(actor, sistema_id, ahora) -> SistemaIoT
# Errores: ``PermissionDenied`` (otro rol), ``Http404`` (sistema inexistente o fuera del alcance de consulta), ``ValidationError`` general: ``fuera_de_alcance`` (regla 1; también si el
# invernadero no está activo, precondición b) y ``sistema_no_desconectado`` (precondición c; uno dado de baja es ``sistema_dado_de_baja``: la baja es definitiva).

import json
from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import Client, TestCase

from core.enlaces import resumen_de
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz
from inventario.tests.fabricas import perezoso, variedad_con_semilla, variedades_presentes_de_prueba
from iot.api.traduccion import LecturaRecibida
from iot.models import Comando, Hardware, ReglaActuacion, SistemaIoT
from iot.tests import fabricas
from iot.tests.escena_de_reglas import AHORA, ConEscenaDeReglas
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_tecnico, error_de

sistemas = perezoso("iot.servicios.sistemas")
lecturas = perezoso("iot.servicios.lecturas")
TOKEN = "token-de-prueba-que-no-es-secreto"


class IotActSisServicioTests(ConEscenaDeReglas, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-ACT-SIS."""

    def setUp(self):
        cache.clear()
        super().setUp()
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(token_resumen=resumen_de(TOKEN), estado_sistema="desconectado")
        self.sistema.refresh_from_db()
        self.regla = fabricas.regla(self.temp, self.ventilador, self.encender, ultima_evaluacion="cumplida")
        self.a_medias = fabricas.regla(self.temp, self.ventilador, self.apagar, "baja_del_minimo", ultima_evaluacion="no_cumplida", contador_confirmacion=2)
        self.inactiva = fabricas.regla(self.hum, self.ventilador, self.apagar, "vuelve_al_rango", estado_regla="inactiva", ultima_evaluacion="cumplida")

    def activar(self, actor=None):
        return sistemas.activar_sistema_iot(actor or self.laura, self.sistema.pk, AHORA)

    # ---- postcondiciones ----

    def test_post_a_el_sistema_queda_activo_con_su_nodo_su_hardware_y_sus_reglas_sin_cambios(self):
        """Postcondición a: estado «activo»; el nodo, el hardware y el estado de las reglas (activa o no) quedan como estaban."""
        estados = dict(Hardware.objects.values_list("pk", "estado_hardware"))
        self.activar()
        self.sistema.refresh_from_db()
        self.assertEqual(self.sistema.estado_sistema, "activo")
        self.assertEqual(dict(Hardware.objects.values_list("pk", "estado_hardware")), estados)
        self.assertEqual(dict(ReglaActuacion.objects.values_list("pk", "estado_regla")), {self.regla.pk: "activa", self.a_medias.pk: "activa", self.inactiva.pk: "inactiva"})

    def test_post_b_audita_el_cambio_de_estado(self):
        """Postcondición b y D-36: ``activacion_sistema_iot`` con el usuario, el sistema como afectado y el cambio de estado; sin ningún token."""
        self.activar()
        auditoria = RegistroAuditoria.objects.get(accion="activacion_sistema_iot")
        self.assertEqual(auditoria.usuario_id, self.laura.pk)
        self.assertIn(("iot.sistemaiot", self.sistema.pk), {(a["modelo"], a["id"]) for a in auditoria.afectados})
        self.assertEqual(auditoria.detalle["cambios"]["estado_sistema"], {"antes": "desconectado", "despues": "activo"})
        self.assertNotIn(resumen_de(TOKEN), json.dumps(auditoria.detalle))

    def test_garantia_si_falla_la_auditoria_el_sistema_sigue_desconectado(self):
        """Atomicidad: si falla la auditoría, el sistema sigue desconectado y las reglas no se reinician."""
        from unittest import mock

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.activar()
        self.sistema.refresh_from_db(), self.regla.refresh_from_db()
        self.assertEqual((self.sistema.estado_sistema, self.regla.ultima_evaluacion), ("desconectado", "cumplida"))

    # ---- precondiciones y regla 1 ----

    def test_regla_1_otros_roles_reciben_403_y_un_sistema_ajeno_o_inexistente_da_404(self):
        """Precondición a y D-28."""
        for otro in (crear_tecnico(), crear_capataz()):
            with self.assertRaises(PermissionDenied):
                self.activar(actor=otro)
        with self.assertRaises(Http404):
            self.activar(actor=crear_agronomo("otro@infoponia.com"))
        with self.assertRaises(Http404):
            sistemas.activar_sistema_iot(self.laura, 99999, AHORA)

    def test_regla_1_el_gerente_no_activa_con_agronomo_activo_y_si_sin_el(self):
        """Regla 1 (la de IOT-DSC-SIS)."""
        self.assertEqual(codigos_de(error_de(lambda: self.activar(actor=self.gerente)), NON_FIELD_ERRORS), ["fuera_de_alcance"])
        self.norte.agronomo = None
        self.norte.save()
        self.activar(actor=self.gerente)
        self.assertEqual(RegistroAuditoria.objects.get(accion="activacion_sistema_iot").usuario_id, self.gerente.pk)

    def test_precondicion_b_el_invernadero_tiene_que_estar_activo(self):
        """Precondición b: con el invernadero dado de baja no se activa. El Agrónomo ya no lo consulta (D-28: 404); el Gerente, que consulta todos, recibe ``fuera_de_alcance`` con el motivo."""
        self.norte.estado_invernadero = "inactivo"
        self.norte.save()
        with self.assertRaises(Http404):
            self.activar()
        error = error_de(lambda: self.activar(actor=self.gerente))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["fuera_de_alcance"])
        self.assertIn("dado de baja", error.messages[0])

    def test_precondicion_c_solo_se_activa_un_sistema_desconectado(self):
        """Precondición c: uno activo no se activa; uno dado de baja tampoco (la baja es definitiva)."""
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(estado_sistema="activo")
        self.assertEqual(codigos_de(error_de(self.activar), NON_FIELD_ERRORS), ["sistema_no_desconectado"])
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(estado_sistema="inactivo")
        self.assertEqual(codigos_de(error_de(self.activar), NON_FIELD_ERRORS), ["sistema_dado_de_baja"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="activacion_sistema_iot").count(), 0)

    # ---- reglas 2 y 4 ----

    def test_regla_2_la_api_vuelve_a_aceptar_los_mensajes_del_nodo(self):
        """Regla 2: desde la activación el sistema vuelve a aceptar telemetría, estados y anuncios (la API ya no responde 403)."""
        cliente = Client(enforce_csrf_checks=True)
        pedido = dict(data=b'{"lecturas": []}', content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        self.assertEqual(cliente.post("/api/iot/v1/lecturas", **pedido).status_code, 403)
        self.activar()
        self.assertEqual(cliente.post("/api/iot/v1/lecturas", **pedido).status_code, 200)

    def test_regla_4_las_reglas_activas_vuelven_a_sin_evaluar_con_la_confirmacion_desde_cero(self):
        """Regla 4 y «Disparo de una regla»: todas las reglas ACTIVAS del sistema quedan «sin evaluar» con el contador en 0 (una dada de baja no se toca)."""
        self.activar()
        for regla in (self.regla, self.a_medias):
            regla.refresh_from_db()
            self.assertEqual((regla.ultima_evaluacion, regla.contador_confirmacion), ("sin_evaluar", 0))
        self.inactiva.refresh_from_db()
        self.assertEqual(self.inactiva.ultima_evaluacion, "cumplida")

    def test_regla_4_la_regla_se_dispara_con_las_lecturas_de_confirmacion_que_llegan_despues(self):
        """Regla 4: se evalúa desde la primera lectura válida que llega después de la activación, como si antes no se cumpliera: con 3 lecturas fuera del umbral dispara; con 2, no."""
        self.enterContext(variedades_presentes_de_prueba({self.norte.pk: {variedad_con_semilla(nombre="Crespa").pk}}))
        self.activar()
        from datetime import timedelta

        for n in range(1, 4):
            ahora = AHORA + timedelta(seconds=10 * n)
            contexto = lecturas.contexto_del_mensaje(self.sistema, ahora)
            lectura = LecturaRecibida(n, "norte/temp", "norte/temp", Decimal("30"), (ahora - timedelta(seconds=5)).isoformat())
            lecturas.registrar_lectura(contexto, lectura, ahora)
            self.assertEqual(Comando.objects.count(), 1 if n == 3 else 0, n)

    # ---- D-30 ----

    def test_d30_ofrece_activar_solo_a_quien_opera_y_con_el_sistema_desconectado(self):
        """D-30: ``activar`` para quien opera y con el sistema desconectado; el Gerente con Agrónomo activo, ninguna; uno dado de baja, ninguna."""
        self.assertIn("activar", sistemas.acciones_permitidas(self.laura, self.sistema))
        self.assertEqual(sistemas.acciones_permitidas(self.gerente, self.sistema), frozenset())
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(estado_sistema="inactivo")
        self.sistema.refresh_from_db()
        self.assertEqual(sistemas.acciones_permitidas(self.laura, self.sistema), frozenset())
