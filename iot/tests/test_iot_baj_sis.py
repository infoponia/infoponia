# Pruebas de IOT-BAJ-SIS · Baja Sistema IoT (docs/casos_de_uso/iot/sistema_iot.md, con «IOT-DSC-SIS, IOT-ACT-SIS e IOT-BAJ-SIS (IOT-06)» de «Cómo se aplica») y de lo que cita: D-70 (token), D-78 (punto 11), D-36 y D-28.
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban (iot/servicios/sistemas.py), tomados del módulo dentro de cada prueba:
#   datos_de_baja_del_sistema(actor, sistema_id) -> DatosDeBajaDelSistema(sistema, nodo, equipos, reglas, impedimentos)
#       lo que muestra la ventana (regla 8): el nodo, cada sensor y actuador NO dado de baja (con su estado), cada regla activa y los impedimentos (``maestros.extensiones.Impedimento``:
#       ``codigo``, ``texto`` y ``como_resolver``) de las precondiciones c y d. No escribe ni audita.
#   baja_sistema_iot(actor, sistema_id, ahora) -> SistemaIoT
#   ordenes_a_realizar_del_sistema(sistema) -> list          (precondición d; hasta IOT-07, vacía)
# Errores: ``PermissionDenied`` (otro rol), ``Http404`` (sistema inexistente o fuera del alcance de consulta), ``ValidationError`` general: ``fuera_de_alcance`` (regla 1),
# ``sistema_dado_de_baja`` (precondición b), ``comandos_pendientes`` (c) y ``ordenes_de_mantenimiento`` (d); los impedimentos llegan juntos (regla 4).

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
from iot.models import Comando, Hardware, ReglaActuacion, SistemaIoT
from iot.servicios import alertas_iot
from iot.tests import fabricas
from iot.tests.escena_de_reglas import AHORA, ConEscenaDeReglas
from maestros.extensiones import Impedimento
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_tecnico, error_de

sistemas = perezoso("iot.servicios.sistemas")
TOKEN = "token-de-prueba-que-no-es-secreto"


class IotBajSisServicioTests(ConEscenaDeReglas, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-BAJ-SIS."""

    def setUp(self):
        cache.clear()
        super().setUp()
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(token_resumen=resumen_de(TOKEN))
        self.nodo = Hardware.objects.get(sistema=self.sistema, clase="nodo")
        type(self.ventana).objects.filter(pk=self.ventana.pk).update(estado_hardware="fuera_de_servicio")
        self.viejo = fabricas.sensor(self.sistema, "norte/viejo", estado="inactivo", fecha_baja=AHORA.date().replace(day=1))
        self.regla = fabricas.regla(self.temp, self.ventilador, self.encender, ultima_evaluacion="cumplida")
        self.otra = fabricas.regla(self.hum, self.ventilador, self.apagar, "baja_del_minimo")
        self.de_baja = fabricas.regla(self.hum, self.ventilador, self.encender, "vuelve_al_rango", estado_regla="inactiva")

    def baja(self, actor=None):
        return sistemas.baja_sistema_iot(actor or self.laura, self.sistema.pk, AHORA)

    def alerta(self, tipo, clave, hardware=None):
        return alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, tipo, clave, "x", hardware=hardware).alerta

    def recargar(self, *objetos):
        for objeto in objetos:
            objeto.refresh_from_db()

    # ---- postcondiciones ----

    def test_post_a_todo_queda_inactivo_con_su_fecha_de_baja_y_se_conserva_el_historial(self):
        """Postcondición a: el sistema, el nodo y todo el hardware (activo o fuera de servicio) quedan «inactivo» con ``fecha_baja`` = hoy; uno que ya estaba dado de baja conserva su fecha; no se borra nada (telemetría, comandos)."""
        lectura = fabricas.telemetria(self.temp, 21)
        resuelto = fabricas.comando(self.ventilador, self.encender, estado="ejecutado")
        self.baja()
        self.sistema.refresh_from_db()
        self.assertEqual((self.sistema.estado_sistema, self.sistema.fecha_baja), ("inactivo", AHORA.date()))
        for equipo in Hardware.objects.filter(sistema=self.sistema).exclude(pk=self.viejo.pk):
            self.assertEqual((equipo.estado_hardware, equipo.fecha_baja), ("inactivo", AHORA.date()), equipo.identificador_equipo)
        self.viejo.refresh_from_db()
        self.assertEqual(self.viejo.fecha_baja, AHORA.date().replace(day=1))
        self.assertTrue(type(lectura).objects.filter(pk=lectura.pk).exists() and Comando.objects.filter(pk=resuelto.pk).exists())

    def test_post_b_las_reglas_activas_quedan_inactivas(self):
        """Postcondición b: las reglas activas del sistema pasan a «inactiva» (las que ya lo estaban no cambian)."""
        self.baja()
        self.assertEqual(dict(ReglaActuacion.objects.values_list("pk", "estado_regla")), {self.regla.pk: "inactiva", self.otra.pk: "inactiva", self.de_baja.pk: "inactiva"})

    def test_post_c_el_token_deja_de_servir_y_la_api_responde_401(self):
        """Postcondición c y D-70: ``token_resumen`` queda nulo y la API responde 401 ``token_invalido`` al mismo token."""
        pedido = dict(data=b'{"lecturas": []}', content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        cliente = Client(enforce_csrf_checks=True)
        self.assertEqual(cliente.post("/api/iot/v1/lecturas", **pedido).status_code, 200)
        self.baja()
        self.sistema.refresh_from_db()
        self.assertIsNone(self.sistema.token_resumen)
        respuesta = cliente.post("/api/iot/v1/lecturas", **pedido)
        self.assertEqual((respuesta.status_code, json.loads(respuesta.content)["error"]), (401, "token_invalido"))

    def test_post_d_resuelve_las_alertas_del_sistema_y_la_del_tecnico_del_invernadero(self):
        """Postcondición d: las alertas activas del sistema pasan a «resuelta», y también «invernadero sin Técnico activo», porque sin sistema IoT el invernadero deja de necesitar Técnico (regla 7)."""
        propias = [self.alerta("iot_dispositivo_sin_actividad", f"hw:{self.temp.pk}", self.temp), self.alerta("iot_dispositivo_no_registrado", "id:co2")]
        api_alertas.sincronizar_alertas_de_personal(self.norte, roles=["tecnico"])
        del_tecnico = Alerta.objects.get(tipo_alerta="sin_tecnico", estado_alerta="activa")
        self.baja()
        for alerta in (*propias, del_tecnico):
            alerta.refresh_from_db()
            self.assertEqual(alerta.estado_alerta, "resuelta", alerta.tipo_alerta)

    def test_post_e_audita_un_solo_registro_con_todo_lo_que_cambio(self):
        """Postcondición e y D-36 (un registro por caso de uso): ``baja_sistema_iot`` con el usuario y el cambio de estado, y como afectados el sistema, el nodo, cada equipo dado de baja ahora, cada regla y cada alerta resuelta; sin el token ni su resumen."""
        alerta = self.alerta("iot_dispositivo_no_registrado", "id:co2")
        self.baja()
        auditoria = RegistroAuditoria.objects.get(accion="baja_sistema_iot")
        self.assertEqual(auditoria.usuario_id, self.laura.pk)
        self.assertEqual(auditoria.detalle["cambios"]["estado_sistema"], {"antes": "activo", "despues": "inactivo"})
        afectados = [(a["modelo"], a["id"]) for a in auditoria.afectados]
        self.assertIn(("iot.sistemaiot", self.sistema.pk), afectados)
        self.assertIn(("maestros.alerta", alerta.pk), afectados)
        ids_de_equipos = {i for m, i in afectados if m in ("iot.hardware", "iot.sensor", "iot.actuador", "iot.nodocentral")}
        self.assertEqual(ids_de_equipos, {self.nodo.pk, self.temp.pk, self.hum.pk, self.nivel.pk, self.ventilador.pk, self.ventana.pk})  # el que ya estaba dado de baja no figura
        self.assertEqual({i for m, i in afectados if m == "iot.reglaactuacion"}, {self.regla.pk, self.otra.pk})
        self.assertNotIn(resumen_de(TOKEN), json.dumps(auditoria.detalle))
        self.assertNotIn(TOKEN, json.dumps(auditoria.detalle))

    def test_garantia_si_falla_la_auditoria_no_se_da_de_baja_nada(self):
        """Atomicidad: si falla la auditoría, todo sigue como estaba (sistema, equipos, reglas, token y alertas)."""
        alerta = self.alerta("iot_dispositivo_no_registrado", "id:co2")
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.baja()
        self.recargar(self.sistema, self.temp, self.regla, alerta)
        self.assertEqual((self.sistema.estado_sistema, self.temp.estado_hardware, self.regla.estado_regla, alerta.estado_alerta), ("activo", "activo", "activa", "activa"))
        self.assertIsNotNone(self.sistema.token_resumen)

    # ---- precondiciones, regla 1 ----

    def test_regla_1_otros_roles_reciben_403_y_un_sistema_ajeno_o_inexistente_da_404(self):
        """Precondición a y D-28."""
        for otro in (crear_tecnico(), crear_capataz()):
            with self.assertRaises(PermissionDenied):
                self.baja(actor=otro)
            with self.assertRaises(PermissionDenied):
                sistemas.datos_de_baja_del_sistema(otro, self.sistema.pk)
        with self.assertRaises(Http404):
            self.baja(actor=crear_agronomo("otro@infoponia.com"))
        with self.assertRaises(Http404):
            sistemas.baja_sistema_iot(self.laura, 99999, AHORA)

    def test_regla_1_el_gerente_no_da_de_baja_con_agronomo_activo_y_si_sin_el(self):
        """Regla 1 (la de IOT-DSC-SIS)."""
        self.assertEqual(codigos_de(error_de(lambda: self.baja(actor=self.gerente)), NON_FIELD_ERRORS), ["fuera_de_alcance"])
        self.norte.agronomo = None
        self.norte.save()
        self.baja(actor=self.gerente)
        self.assertEqual(RegistroAuditoria.objects.get(accion="baja_sistema_iot").usuario_id, self.gerente.pk)

    def test_precondicion_b_se_da_de_baja_un_sistema_activo_o_desconectado_pero_no_dos_veces(self):
        """Precondición b y regla 5: también con el invernadero activo y con el sistema desconectado; uno ya dado de baja no se vuelve a dar de baja."""
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(estado_sistema="desconectado")
        self.baja()
        self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["sistema_dado_de_baja"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_sistema_iot").count(), 1)

    def test_precondicion_c_con_un_comando_pendiente_no_deja_confirmar_y_explica_como_resolverlo(self):
        """Precondición c y regla 4: no se da de baja, no cambia nada, y el error dice cuántos comandos son y cómo resolverlos (cancelarlos uno por uno o desactivar el sistema)."""
        comando = fabricas.comando(self.ventilador, self.encender)
        error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["comandos_pendientes"])
        self.assertIn(f"CMD-{comando.pk}", " ".join(error.messages))
        self.recargar(self.sistema, comando)
        self.assertEqual((self.sistema.estado_sistema, comando.estado_comando), ("activo", "pendiente"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_sistema_iot").count(), 0)

    def test_precondicion_d_con_una_orden_de_mantenimiento_a_realizar_no_se_da_de_baja(self):
        """Precondición d: hasta IOT-07 ``ordenes_a_realizar_del_sistema`` devuelve una lista vacía y la baja procede; con una orden, no, y el impedimento se informa junto con los demás."""
        self.assertEqual(sistemas.ordenes_a_realizar_del_sistema(self.sistema), [])
        fabricas.comando(self.ventilador, self.encender)
        with mock.patch("iot.servicios.sistemas.ordenes_a_realizar_del_sistema", return_value=["OT-1"]):
            self.assertEqual(sorted(codigos_de(error_de(self.baja), NON_FIELD_ERRORS)), ["comandos_pendientes", "ordenes_de_mantenimiento"])

    # ---- regla 3 y regla 6 (después de la baja) ----

    def test_regla_3_se_puede_registrar_un_sistema_nuevo_con_los_mismos_identificadores(self):
        """Regla 3: el invernadero vuelve a necesitar IoT: un sistema nuevo y equipos con los mismos identificadores (los de los dados de baja quedan libres)."""
        self.baja()
        nuevo = fabricas.sistema(self.norte)
        fabricas.sensor(nuevo, "norte/temp")
        self.assertEqual(SistemaIoT.objects.exclude(estado_sistema="inactivo").get().pk, nuevo.pk)

    def test_regla_6_el_invernadero_ya_se_puede_dar_de_baja_en_datos_maestros(self):
        """Regla 6 y PROD-BAJ-INV (precondición h): con el sistema activo es un impedimento; después de la baja, no."""
        self.assertEqual([i.codigo for i in sistemas.impedimentos_de_baja_del_invernadero(self.norte)], ["sistema_iot"])
        self.baja()
        self.assertEqual(sistemas.impedimentos_de_baja_del_invernadero(self.norte), [])

    # ---- regla 8: lo que muestra la ventana ----

    def test_regla_8_la_ventana_muestra_el_nodo_los_equipos_con_su_estado_las_reglas_activas_y_nada_que_impida(self):
        """Regla 8: el nodo, cada equipo NO dado de baja con su estado (activo o fuera de servicio), cada regla ACTIVA, y sin impedimentos si no hay pendientes."""
        datos = sistemas.datos_de_baja_del_sistema(self.laura, self.sistema.pk)
        self.assertEqual(datos.nodo.pk, self.nodo.pk)
        self.assertEqual({e.pk: e.estado_hardware for e in datos.equipos}, {self.temp.pk: "activo", self.hum.pk: "activo", self.nivel.pk: "activo", self.ventilador.pk: "activo", self.ventana.pk: "fuera_de_servicio"})
        self.assertEqual({r.pk for r in datos.reglas}, {self.regla.pk, self.otra.pk})
        self.assertEqual(datos.impedimentos, [])

    def test_regla_8_la_ventana_con_pendientes_trae_el_impedimento_con_como_resolverlo(self):
        """Regla 4 y 8: con un comando pendiente, la ventana trae el impedimento (código, texto y cómo resolverlo) y no deja confirmar."""
        fabricas.comando(self.ventilador, self.encender)
        impedimentos = sistemas.datos_de_baja_del_sistema(self.laura, self.sistema.pk).impedimentos
        self.assertEqual([i.codigo for i in impedimentos], ["comandos_pendientes"])
        self.assertIsInstance(impedimentos[0], Impedimento)
        self.assertIn("desactiv", impedimentos[0].como_resolver.lower())

    def test_regla_8_la_ventana_no_audita_ni_cambia_nada(self):
        """La ventana es una consulta (SEG-14): no escribe ni audita."""
        antes = RegistroAuditoria.objects.count()
        sistemas.datos_de_baja_del_sistema(self.laura, self.sistema.pk)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        self.sistema.refresh_from_db()
        self.assertEqual(self.sistema.estado_sistema, "activo")

    def test_regla_8_la_ventana_muestra_el_ultimo_estado_informado_de_cada_actuador(self):
        """Regla 8 y regla 7 de IOT-BAJ-HDW: de cada actuador, su último estado informado por el nodo (el actuador trae ``estado_informado`` y ``estado_informado_en``; ``None`` = «desconocido»)."""
        type(self.ventilador).objects.filter(pk=self.ventilador.pk).update(estado_informado="encendido", estado_informado_en=AHORA)
        datos = sistemas.datos_de_baja_del_sistema(self.laura, self.sistema.pk)
        estados = {e.pk: e.estado_informado for e in datos.equipos if e.clase == "actuador"}
        self.assertEqual(estados, {self.ventilador.pk: "encendido", self.ventana.pk: None})

    # ---- D-30 ----

    def test_d30_ofrece_baja_a_quien_opera_con_el_sistema_activo_o_desconectado(self):
        """D-30: ``baja`` para quien opera, con el sistema activo o desconectado; el Gerente con Agrónomo activo y un sistema ya dado de baja, ninguna."""
        self.assertIn("baja", sistemas.acciones_permitidas(self.laura, self.sistema))
        self.assertEqual(sistemas.acciones_permitidas(self.gerente, self.sistema), frozenset())
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(estado_sistema="desconectado")
        self.sistema.refresh_from_db()
        self.assertIn("baja", sistemas.acciones_permitidas(self.laura, self.sistema))
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(estado_sistema="inactivo")
        self.sistema.refresh_from_db()
        self.assertEqual(sistemas.acciones_permitidas(self.laura, self.sistema), frozenset())
