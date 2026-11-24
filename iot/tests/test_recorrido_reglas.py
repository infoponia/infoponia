# Recorrido de punta a punta de las reglas de actuación y del ciclo de vida del IoT (IOT-06): los pasos 1 a 6 de la «Verificación a mano» de la tarea y los escenarios 3, 4, 5, 10 y 14 de
# `docs/api/nodo/escenarios.md`, hechos por una prueba con el cliente de Django, en el orden en que los haría una persona (docs/patrones/verificacion_a_mano.md). La persona que opera
# usa las pantallas; el nodo central, la API (`POST lecturas`, `GET comandos`, `POST comandos/<id>/resultado` y `POST modo`) con su token, como lo hace Node-RED. El reloj es uno solo y se
# adelanta a mano. Cada paso nombra el caso de uso y la regla que verifica. Es una sola prueba larga a propósito: lo que se verifica es que el flujo completo encadena bien, no cada regla
# suelta (eso lo hacen `test_iot_alt_rgl.py`, `test_iot_mod_rgl.py`, `test_iot_baj_rgl.py`, `test_iot_cns_rgl.py`, `test_iot_ent_inf_reglas.py`, `test_iot_dsc_sis.py`,
# `test_iot_act_sis.py`, `test_iot_baj_sis.py`, `test_iot_baj_hdw.py` y `test_reglas_vistas.py`).

import json
import re
from datetime import timedelta
from html import unescape
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.enlaces import resumen_de
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.tests.fabricas import variedad_con_semilla, variedades_presentes_de_prueba
from iot.models import Comando, NodoCentral, ReglaActuacion, SistemaIoT, TipoActuador
from iot.servicios import sistemas
from iot.tests import fabricas
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_tecnico

TOKEN = "token-del-recorrido-de-reglas-no-es-secreto"
HX = {"HTTP_HX_REQUEST": "true"}
Accion = RegistroAuditoria.Accion


class RecorridoDeReglasTests(fabricas.ConCatalogoIot, TestCase):
    """Fuente: docs/casos_de_uso/iot/reglas_de_actuacion.md, sistema_iot.md, hardware.md y entregar_informacion.md («Reglas de actuación»), docs/api/nodo/escenarios.md, D-30, D-36, D-78 y D-82."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.reloj = timezone.now().replace(microsecond=0)
        self.enterContext(mock.patch("django.utils.timezone.now", side_effect=lambda: self.reloj))
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.tecnico = crear_tecnico("tecnico@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=self.tecnico)
        self.libre = crear_invernadero("Libre")  # sin Agrónomo: lo opera el Gerente
        # El umbral efectivo de «Crespa» (temperatura 18 a 24 °C; histéresis de 1 °C) y 2 lecturas de confirmación: como el «Antes de empezar» de los escenarios.
        self.enterContext(variedades_presentes_de_prueba({self.norte.pk: {variedad_con_semilla(nombre="Crespa").pk}}))
        config = configuracion.obtener()
        config.cant_lecturas_confirmacion, config.cant_reintentos_comando, config.segundos_intervalo_reintento = 2, 1, 10
        config.save()
        self.sistema = fabricas.sistema(self.norte, token_resumen=resumen_de(TOKEN))
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.temp = fabricas.sensor(self.sistema, "norte/temperatura")
        self.ventilador = fabricas.actuador(self.sistema, TipoActuador.objects.get(nombre_actuador="Ventilador"), "norte/ventilador", ultimo_mensaje_en=self.reloj)
        self.encender = self.ventilador.tipo_actuador.acciones.get(nombre_accion="Encender")
        self.apagar = self.ventilador.tipo_actuador.acciones.get(nombre_accion="Apagar")
        self.cliente = Client()
        self.nodo_http = Client()
        self.avanzar(0, comunicar=True)

    # ---- ayudas ----

    def avanzar(self, segundos, comunicar=False):
        """Adelanta el reloj de todo el sistema; con ``comunicar``, el nodo se comunicó en ese momento (``en línea``)."""
        self.reloj += timedelta(seconds=segundos)
        if comunicar:
            NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=self.reloj)

    def url(self, nombre, *args, **consulta):
        ruta = reverse(f"iot:{nombre}", args=args)
        return ruta + ("?" + "&".join(f"{k}={v}" for k, v in consulta.items()) if consulta else "")

    def ver(self, respuesta):
        return unescape(respuesta.content.decode())

    def entrar(self, cuenta):
        self.cliente.force_login(cuenta)

    def lista(self, **consulta):
        return self.ver(self.cliente.get(self.url("reglas", invernadero=self.norte.pk, **consulta)))

    def fila(self, regla, **consulta):
        """El HTML de la fila de la lista de reglas de ``regla`` (para mirar solo su situación)."""
        coincide = re.search(rf"<tr[^>]*>(?:(?!</tr>).)*RGL-{regla.pk}(?!\d)(?:(?!</tr>).)*</tr>", self.lista(**consulta), re.S)
        self.assertIsNotNone(coincide, f"RGL-{regla.pk} no está en la lista")
        return coincide.group(0)

    def post_de_regla(self, condicion, accion, sensor=None, actuador=None):
        return {"sensor": (sensor or self.temp).pk, "condicion": condicion, "actuador": (actuador or self.ventilador).pk, "accion": accion.pk, "valor": ""}

    def crear_regla(self, condicion, accion):
        antes = set(ReglaActuacion.objects.values_list("pk", flat=True))
        respuesta = self.cliente.post(self.url("regla_nueva", invernadero=self.norte.pk), self.post_de_regla(condicion, accion))
        self.assertEqual(respuesta.status_code, 302, self.ver(respuesta)[:800])
        return ReglaActuacion.objects.exclude(pk__in=antes).get()

    def lectura(self, valor):
        """El nodo manda UNA lectura de temperatura (``POST lecturas``) con su token, 10 s después de la anterior."""
        self.avanzar(10, comunicar=True)
        respuesta = self.nodo_http.post(
            "/api/iot/v1/lecturas", data=json.dumps({"lecturas": [{"identificador": "norte/temperatura", "valor": valor}]}), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
        return respuesta

    def retiro(self):
        respuesta = self.nodo_http.get("/api/iot/v1/comandos", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        self.assertEqual(respuesta.status_code, 200)
        return json.loads(respuesta.content)["comandos"]

    def resultado(self, comando, estado):
        respuesta = self.nodo_http.post(
            f"/api/iot/v1/comandos/{comando.pk}/resultado", data=json.dumps({"resultado": "ejecutado", "estado": estado}), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
        self.assertEqual(respuesta.status_code, 200)

    def modo(self, modo):
        respuesta = self.nodo_http.post("/api/iot/v1/modo", data=json.dumps({"modo": modo}), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        self.assertEqual(respuesta.status_code, 200)

    def auditorias(self, accion):
        return RegistroAuditoria.objects.filter(accion=accion).count()

    # ---- el recorrido ----

    def test_recorrido_de_reglas_de_actuacion_y_ciclo_de_vida(self):
        # ===== IOT-CNS-RGL regla 1 y 5 · quién ve qué =====
        self.entrar(crear_capataz())
        self.assertEqual(self.cliente.get(self.url("reglas", invernadero=self.norte.pk)).status_code, 403)
        self.entrar(self.gerente)  # Norte tiene Agrónomo activo: el Gerente solo consulta
        sin_reglas = self.ver(self.cliente.get(self.url("reglas", invernadero=self.norte.pk)))
        self.assertIn("No hay reglas en este invernadero.", sin_reglas)
        self.assertNotIn("Nueva regla", sin_reglas)
        self.assertEqual(self.cliente.get(self.url("regla_nueva", invernadero=self.norte.pk)).status_code, 302)
        self.entrar(self.laura)
        self.assertIn("Nueva regla", self.lista())

        # ===== IOT-ALT-RGL · el formulario: elegir el actuador ofrece sus acciones y la frase de vista previa; errores por campo =====
        formulario = self.ver(self.cliente.post(self.url("regla_nueva", invernadero=self.norte.pk), self.post_de_regla("supera_maximo", self.encender) | {"refrescar": "1"}, **HX))
        self.assertIn("Cuando Temperatura norte/temperatura supera el máximo del umbral efectivo, Ventilador norte/ventilador: Encender", formulario)
        self.assertFalse(ReglaActuacion.objects.exists())  # «refrescar» no guarda
        incompleto = self.ver(self.cliente.post(self.url("regla_nueva", invernadero=self.norte.pk), {"sensor": "", "condicion": "", "actuador": self.ventilador.pk, "accion": ""}))
        self.assertIn("Seleccioná un sensor.", incompleto)
        self.assertIn("Seleccioná la condición.", incompleto)
        self.assertIn("Seleccioná la acción.", incompleto)

        # ===== IOT-ALT-RGL · dos reglas: «supera el máximo → encender» y «vuelve al rango → apagar»; la repetida se rechaza (verificación a mano 1) =====
        r1 = self.crear_regla("supera_maximo", self.encender)
        self.assertEqual((r1.estado_regla, r1.ultima_evaluacion, r1.contador_confirmacion), ("activa", "sin_evaluar", 0))
        repetida = self.ver(self.cliente.post(self.url("regla_nueva", invernadero=self.norte.pk), self.post_de_regla("supera_maximo", self.encender)))
        self.assertIn("Ya hay una regla activa igual: Cuando Temperatura norte/temperatura supera el máximo", repetida)
        r2 = self.crear_regla("vuelve_al_rango", self.apagar)
        self.assertEqual(ReglaActuacion.objects.count(), 2)
        self.assertIn("Sin evaluar", self.fila(r1))

        # ===== Escenario 3 · Respuesta automática: a la segunda lectura fuera, InfoPonia emite =====
        self.assertEqual(self.lectura(35).status_code, 200)
        self.assertIn("Confirmando 1 de 2", self.fila(r1))
        self.assertFalse(Comando.objects.exists())
        self.assertEqual(self.lectura(35).status_code, 200)
        (c1,) = Comando.objects.all()
        self.assertEqual((c1.regla_id, c1.accion_id, c1.estado_comando, c1.agronomo_id), (r1.pk, self.encender.pk, "pendiente", None))
        self.assertIn("Se cumple", self.fila(r1))
        self.assertEqual([(c["id"], c["comando"]) for c in self.retiro()], [(c1.pk, "ENCENDER")])
        self.resultado(c1, "encendido")
        comandos = self.ver(self.cliente.get(self.url("comandos", invernadero=self.norte.pk)))
        self.assertIn(f"Regla de actuación · RGL-{r1.pk}", comandos)
        self.assertIn("Ejecutado", comandos)
        ficha = self.ver(self.cliente.get(self.url("regla_ficha", r1.pk)))  # IOT-CNS-RGL regla 4: el historial de la regla
        self.assertIn(f"CMD-{c1.pk}", ficha)

        # ===== Escenario 4 · Sin repetir: la temperatura sigue alta y la regla no vuelve a emitir (6b) =====
        self.avanzar(61)
        self.lectura(35)
        self.lectura(35)
        self.assertEqual(Comando.objects.count(), 1)
        self.assertIn("Se cumple", self.fila(r1))

        # ===== Escenario 5 · Vuelta a la normalidad: a más de la histéresis del límite, la primera se apaga y la segunda emite «Apagar» =====
        self.avanzar(61)
        self.lectura(20)
        self.assertIn("Confirmando 1 de 2", self.fila(r2))
        self.lectura(20)
        self.assertIn("No se cumple", self.fila(r1))
        c2 = Comando.objects.exclude(pk=c1.pk).get()
        self.assertEqual((c2.regla_id, c2.accion_id, c2.estado_comando), (r2.pk, self.apagar.pk, "pendiente"))

        # ===== IOT-BAJ-RGL regla 2 · dar de baja una regla con un comando pendiente: el comando sigue y se ejecuta (verificación a mano 3) =====
        ventana = self.ver(self.cliente.get(self.url("regla_baja", r2.pk), **HX))
        self.assertIn(f"CMD-{c2.pk}", ventana)
        self.assertIn("siguen su curso y se ejecutan igual", ventana)
        respuesta = self.cliente.post(self.url("regla_baja", r2.pk))
        self.assertEqual(respuesta.status_code, 302)
        r2.refresh_from_db()
        c2.refresh_from_db()
        self.assertEqual((r2.estado_regla, c2.estado_comando), ("inactiva", "pendiente"))
        self.assertEqual([c["id"] for c in self.retiro()], [c2.pk])
        self.resultado(c2, "apagado")
        c2.refresh_from_db()
        self.assertEqual(c2.estado_comando, "ejecutado")
        self.assertIn("Dada de baja", self.fila(r2))
        self.assertNotIn(f"RGL-{r2.pk}", self.lista(estado="activa"))  # el filtro de estado (IOT-CNS-RGL regla 3)
        # IOT-MOD-RGL postcondición b y regla 6 · Reactivar
        self.cliente.post(self.url("regla_reactivar", r2.pk))
        r2.refresh_from_db()
        self.assertEqual((r2.estado_regla, r2.ultima_evaluacion), ("activa", "sin_evaluar"))

        # ===== IOT-MOD-RGL regla 4 · modificar una regla: su situación vuelve a «Sin evaluar» (verificación a mano 2) =====
        self.lectura(35)
        self.assertIn("Confirmando 1 de 2", self.fila(r1))
        respuesta = self.cliente.post(self.url("regla_modificar", r1.pk), self.post_de_regla("baja_del_minimo", self.encender))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("Sin evaluar", self.fila(r1))
        self.assertIn("baja del mínimo", self.fila(r1))
        self.cliente.post(self.url("regla_modificar", r1.pk), self.post_de_regla("supera_maximo", self.encender))

        # ===== IOT-BAJ-HDW precondición e · dar de baja un actuador con una regla activa: no deja y explica que hay que dar de baja la regla (verificación a mano 4) =====
        ventana = self.ver(self.cliente.get(self.url("hardware_baja", self.ventilador.pk), **HX))
        self.assertIn("No se puede dar de baja todavía", ventana)
        self.assertIn(f"RGL-{r1.pk}", ventana)
        self.assertIn("Dalas de baja primero desde Reglas de actuación", ventana)
        self.cliente.post(self.url("hardware_baja", self.ventilador.pk))
        self.ventilador.refresh_from_db()
        self.assertEqual(self.ventilador.estado_hardware, "activo")

        # ===== Escenario 10 · Modo local: las reglas no se evalúan; al volver a remoto, empiezan de cero (IOT-ENT-INF 1b.3 y 6d) =====
        self.lectura(35)
        self.assertIn("Confirmando 1 de 2", self.fila(r1))
        self.modo("local")
        self.assertIn("No se evalúa: nodo en modo local", self.fila(r1))
        self.lectura(35)
        self.assertIn("Confirmando 1 de 2", self.fila(r1))  # en modo local no avanzó
        self.modo("remoto")
        self.assertIn("Sin evaluar", self.fila(r1))

        # ===== Escenario 14 · Desconectar el sistema: se cancelan los pendientes, el nodo recibe 403, y al activar las reglas empiezan de cero (IOT-DSC-SIS, IOT-ACT-SIS) =====
        self.avanzar(61)
        pendiente = fabricas.comando(self.ventilador, self.apagar)
        ventana = self.ver(self.cliente.get(self.url("sistema_desactivar", self.sistema.pk), **HX))
        self.assertIn("Los comandos pendientes se cancelan", ventana)
        self.cliente.post(self.url("sistema_desactivar", self.sistema.pk))
        pendiente.refresh_from_db()
        self.assertEqual((SistemaIoT.objects.get(pk=self.sistema.pk).estado_sistema, pendiente.estado_comando), ("desconectado", "cancelado"))
        self.assertEqual(self.lectura(35).status_code, 403)
        self.assertEqual(self.nodo_http.get("/api/iot/v1/comandos", HTTP_AUTHORIZATION=f"Bearer {TOKEN}").status_code, 403)
        self.assertIn("No se evalúa: sistema desconectado", self.fila(r1))
        self.cliente.post(self.url("sistema_activar", self.sistema.pk))
        self.assertEqual(SistemaIoT.objects.get(pk=self.sistema.pk).estado_sistema, "activo")
        self.assertIn("Sin evaluar", self.fila(r1))
        self.assertEqual(self.lectura(20).status_code, 200)

        # ===== IOT-BAJ-SIS · dar de baja el sistema: con un comando pendiente no deja; después, todo inactivo y el token deja de servir (verificación a mano 5) =====
        bloqueo = fabricas.comando(self.ventilador, self.encender)
        ventana = self.ver(self.cliente.get(self.url("sistema_baja", self.sistema.pk), **HX))
        self.assertIn("No se puede dar de baja todavía", ventana)
        self.assertIn(f"CMD-{bloqueo.pk}", ventana)
        self.cliente.post(self.url("sistema_baja", self.sistema.pk))
        self.assertEqual(SistemaIoT.objects.get(pk=self.sistema.pk).estado_sistema, "activo")
        Comando.objects.filter(pk=bloqueo.pk).update(estado_comando="cancelado", resuelto_en=self.reloj)
        ventana = self.ver(self.cliente.get(self.url("sistema_baja", self.sistema.pk), **HX))
        self.assertIn("La baja es <b>definitiva</b>", ventana)
        self.assertIn("norte/temperatura", ventana)
        self.assertIn("norte/ventilador", ventana)
        self.assertIn(f"RGL-{r1.pk}", ventana)
        self.assertIn("último estado: apagado", ventana)
        self.cliente.post(self.url("sistema_baja", self.sistema.pk))
        sistema = SistemaIoT.objects.get(pk=self.sistema.pk)
        r1.refresh_from_db()
        self.temp.refresh_from_db()
        self.assertEqual((sistema.estado_sistema, sistema.token_resumen, r1.estado_regla, self.temp.estado_hardware), ("inactivo", None, "inactiva", "inactivo"))
        self.assertEqual(self.lectura(35).status_code, 401)  # el token dejó de servir
        self.assertEqual(sistemas.impedimentos_de_baja_del_invernadero(self.norte), [])  # el invernadero ya se puede dar de baja en Datos maestros
        self.assertIn("no tiene Sistema IoT", self.lista())

        # ===== «Auditoría» · las acciones nuevas (verificación a mano 6) =====
        for accion, cuantas in (
            (Accion.ALTA_REGLA_ACTUACION, 2),
            (Accion.BAJA_REGLA_ACTUACION, 1),
            (Accion.DESACTIVACION_SISTEMA_IOT, 1),
            (Accion.ACTIVACION_SISTEMA_IOT, 1),
            (Accion.BAJA_SISTEMA_IOT, 1),
        ):
            with self.subTest(accion=accion):
                self.assertEqual(self.auditorias(accion), cuantas)
        self.assertGreaterEqual(self.auditorias(Accion.MODIFICACION_REGLA_ACTUACION), 3)  # dos modificaciones y una reactivación

    def test_recorrido_del_gerente_en_un_invernadero_sin_agronomo(self):
        """IOT-CNS-RGL regla 5 y D-30: el Gerente opera Libre (sin Agrónomo): ve «Nueva regla», crea una regla y da de baja un equipo sin reglas."""
        sistema = fabricas.sistema(self.libre)
        sensor = fabricas.sensor(sistema, "libre/temp")
        actuador = fabricas.actuador(sistema, self.ventilador.tipo_actuador, "libre/ventilador")
        self.entrar(self.gerente)
        self.assertIn("Nueva regla", self.ver(self.cliente.get(self.url("reglas", invernadero=self.libre.pk))))
        datos = {"sensor": sensor.pk, "condicion": "supera_maximo", "actuador": actuador.pk, "accion": self.encender.pk, "valor": ""}
        self.assertEqual(self.cliente.post(self.url("regla_nueva", invernadero=self.libre.pk), datos).status_code, 302)
        regla = ReglaActuacion.objects.get(sensor=sensor)
        self.assertIn("Dar de baja", self.ver(self.cliente.get(self.url("regla_ficha", regla.pk))))
        self.cliente.post(self.url("regla_baja", regla.pk))
        self.cliente.post(self.url("hardware_baja", actuador.pk))
        actuador.refresh_from_db()
        self.assertEqual(actuador.estado_hardware, "inactivo")
