# Recorrido de punta a punta de los comandos del IoT (IOT-05): los pasos 1 a 4 de la «Verificación a mano» de la tarea y los escenarios 6, 7, 8, 9 y 13 de `docs/api/nodo/escenarios.md`,
# hechos por una prueba con el cliente de Django, en el orden en que los haría una persona (docs/patrones/verificacion_por_claude.md). La persona que opera usa las pantallas; el nodo
# central, la API (`GET comandos` y `POST comandos/<id>/resultado`) con su token, como lo hace el flujo de Node-RED. El reloj es uno solo y se adelanta a mano: así los intentos, las esperas
# y el «sin señal» pasan en segundos. Cada paso nombra el caso de uso y la regla que verifica. Es una sola prueba larga a propósito: lo que se verifica es que el flujo completo encadena bien,
# no cada regla suelta (eso lo hacen `test_iot_emt_cmd.py`, `test_iot_cnl_cmd.py`, `test_iot_rsv_cmd.py`, `test_api_comandos.py` y `test_comandos_vistas.py`).

import json
import re
from datetime import timedelta
from html import unescape
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.enlaces import resumen_de
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from iot.models import Actuador, AlertaIot, Comando, MantenimientoTecnico, NodoCentral, RegistroComando, TipoActuador
from iot.servicios import revision
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_sector, crear_tecnico

TOKEN = "token-del-recorrido-no-es-secreto"
HX = {"HTTP_HX_REQUEST": "true"}


@override_settings(CORREO_CONFIGURADO=True)
class RecorridoDeComandosTests(fabricas.ConCatalogoIot, TestCase):
    """Fuente: docs/casos_de_uso/iot/emitir_comando.md, resolver_comando.md y cancelar_comando.md, docs/api/nodo/ (contrato y escenarios), D-30, D-36, D-77 y D-78."""

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
        self.sistema = fabricas.sistema(self.norte, token_resumen=resumen_de(TOKEN))
        self.sistema_libre = fabricas.sistema(self.libre)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        sector = crear_sector(self.norte, "Sector A")
        self.ventilador = fabricas.actuador(
            self.sistema, TipoActuador.objects.get(nombre_actuador="Ventilador"), "norte/sectorA/ventilador", sector=sector,
            ultimo_mensaje_en=self.reloj, estado_informado="encendido", estado_informado_en=self.reloj - timedelta(hours=1),
        )
        self.ventana = fabricas.actuador(
            self.sistema, TipoActuador.objects.get(nombre_actuador="Ventana"), "norte/sectorA/ventana", sector=sector, ultimo_mensaje_en=self.reloj
        )
        self.libre_ventilador = fabricas.actuador(self.sistema_libre, self.ventilador.tipo_actuador, "libre/ventilador", ultimo_mensaje_en=self.reloj)
        # Para no esperar: un reintento (2 intentos) e intervalo de 10 s (los valores mínimos); al final se vuelve a 3 y 60 (no hace falta: la base de la prueba se deshace).
        config = configuracion.obtener()
        config.cant_reintentos_comando, config.segundos_intervalo_reintento = 1, 10
        config.save()
        self.nodo_http = Client()
        self.cliente = Client()
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

    def accion(self, actuador, nombre):
        return actuador.tipo_actuador.acciones.get(nombre_accion=nombre)

    def formulario(self, actuador, nombre_de_la_accion, valor="", descripcion="", cuenta=None, invernadero=None):
        """Los datos que manda la persona al formulario de emisión."""
        return {"actuador": actuador.pk, "accion": self.accion(actuador, nombre_de_la_accion).pk, "valor": valor, "descripcion": descripcion}

    def resumen(self, *args, **kwargs):
        """Paso 6: «Ver resumen». Devuelve el HTML (el servicio no escribe nada)."""
        invernadero = kwargs.pop("invernadero", self.norte)
        respuesta = self.cliente.post(self.url("comandos", invernadero=invernadero.pk), {"paso": "resumen"} | self.formulario(*args, **kwargs))
        self.assertEqual(respuesta.status_code, 200)
        return self.ver(respuesta)

    def emitir(self, *args, **kwargs):
        """Pasos 7 y 8: «Confirmar y emitir». Devuelve el comando emitido (la pantalla redirige a la lista con el aviso del paso 9)."""
        invernadero = kwargs.pop("invernadero", self.norte)
        antes = set(Comando.objects.values_list("pk", flat=True))
        respuesta = self.cliente.post(self.url("comandos", invernadero=invernadero.pk), {"paso": "emitir"} | self.formulario(*args, **kwargs))
        self.assertEqual(respuesta.status_code, 302, self.ver(respuesta)[:600])
        nuevo = Comando.objects.exclude(pk__in=antes).get()
        self.assertEqual((nuevo.estado_comando, nuevo.cantidad_intentos), ("pendiente", 0))
        return nuevo

    def lista(self, invernadero=None, **consulta):
        return self.ver(self.cliente.get(self.url("comandos", invernadero=(invernadero or self.norte).pk, **consulta)))

    def retiro(self, token=TOKEN):
        """El nodo pide sus comandos: ``GET comandos`` con su token."""
        respuesta = self.nodo_http.get("/api/iot/v1/comandos", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(respuesta.status_code, 200)
        return json.loads(respuesta.content)

    def resultado(self, comando, que, **datos):
        """El nodo informa el resultado: ``POST comandos/<id>/resultado``."""
        respuesta = self.nodo_http.post(
            f"/api/iot/v1/comandos/{comando.pk}/resultado", data=json.dumps({"resultado": que} | datos), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
        self.assertEqual(respuesta.status_code, 200)
        return json.loads(respuesta.content)

    def modo(self, modo):
        respuesta = self.nodo_http.post(
            "/api/iot/v1/modo", data=json.dumps({"modo": modo}), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {TOKEN}"
        )
        self.assertEqual(respuesta.status_code, 200)

    def alerta(self, tipo):
        return Alerta.objects.filter(tipo_alerta=tipo, estado_alerta="activa").first()

    def recargar(self, *objetos):
        for objeto in objetos:
            objeto.refresh_from_db()

    # ---- el recorrido ----

    def test_recorrido_de_comandos_de_punta_a_punta(self):
        self.entrar(self.laura)

        # ===== Paso 1 de la «Verificación a mano» · IOT-EMT-CMD 6c: «Ventilador · Encender» con el ventilador ya encendido =====
        html = self.resumen(self.ventilador, "Encender")
        self.assertIn("Según el último estado que informó el nodo, el actuador ya está encendido.", html)  # 6c
        self.assertEqual(Comando.objects.count(), 0)  # el resumen no escribe
        c1 = self.emitir(self.ventilador, "Encender")  # el confirmar lo deja pendiente
        self.assertIn(f"Comando CMD-{c1.pk} pendiente. El nodo lo retira en su próxima consulta", self.lista())  # paso 9
        self.assertIn("Pendiente", self.lista())
        # IOT-RSV-CMD paso 2 y 5: el nodo lo retira, «ejecuta» (nada cambia en el equipo) y lo informa como ejecutado
        self.avanzar(5, comunicar=True)
        entregado = self.retiro()["comandos"]
        self.assertEqual([(c["id"], c["identificador"], c["comando"], c["valor"], c["intento"]) for c in entregado], [(c1.pk, "norte/sectorA/ventilador", "ENCENDER", None, 1)])
        respuesta = self.resultado(c1, "ejecutado", detalle="Ya estaba encendido.", estado="encendido")
        self.assertEqual((respuesta["resultado"], respuesta["estado_comando"]), ("aceptado", "ejecutado"))
        self.assertIn("Ejecutado", self.lista())
        # IOT-EMT-CMD 6f: justo después de un comando ejecutado, otro al mismo actuador advierte el tiempo mínimo (60 s) y deja continuar
        html = self.resumen(self.ventilador, "Apagar")
        self.assertIn("El actuador cambió de estado hace", html)
        self.assertIn("Podés emitirlo igual.", html)
        self.avanzar(61)

        # ===== Escenario 6 · Comando manual: Ventana · Fijar posición 40 =====
        html = self.resumen(self.ventana, "Fijar posición", valor="40")
        self.assertIn("40 %", html)
        c6 = self.emitir(self.ventana, "Fijar posición", valor="40")
        self.assertEqual(self.retiro()["comandos"][0]["valor"], 40)
        self.avanzar(2, comunicar=True)
        self.resultado(c6, "ejecutado", detalle="Posición al 40 %.", estado="posicion:40")
        self.recargar(self.ventana, c6)
        self.assertEqual((c6.estado_comando, self.ventana.estado_informado, self.ventana.cambiado_en_invernadero), ("ejecutado", "posicion:40", False))
        ficha = self.ver(self.cliente.get(self.url("hardware_ficha", self.ventana.pk)))
        self.assertIn("Posición 40", ficha)
        self.assertIn(f"CMD-{c6.pk}", ficha)  # el historial de comandos de la ficha
        self.assertIn("Ejecutado", ficha)
        # El valor fuera del rango o decimal se rechaza junto al campo (6a) y no deja nada
        self.avanzar(61)
        self.assertIn("Ingresá un número entero entre 0 y 100 %, sin decimales.", self.resumen(self.ventana, "Fijar posición", valor="12.5"))
        self.assertIn("Ingresá un número entero entre 0 y 100 %, sin decimales.", self.resumen(self.ventana, "Fijar posición", valor="101"))

        # ===== Escenario 7 · Falla del actuador (1 reintento, 10 s): cada intento falla; al último, fallido + fuera de servicio + alerta crítica =====
        c7 = self.emitir(self.ventilador, "Apagar")
        self.avanzar(1, comunicar=True)
        self.assertEqual(self.retiro()["comandos"][0]["intento"], 1)
        self.assertEqual(self.resultado(c7, "fallo", detalle="Relé trabado")["estado_comando"], "pendiente")  # 4a: le quedan intentos
        self.assertEqual(self.retiro()["comandos"], [])  # no se vuelve a entregar dentro de la espera
        self.avanzar(11, comunicar=True)
        self.assertEqual(self.retiro()["comandos"][0]["intento"], 2)
        self.assertEqual(self.resultado(c7, "fallo", detalle="Relé trabado")["estado_comando"], "fallido")  # 4b: agotó los intentos
        self.recargar(self.ventilador, c7)
        self.assertEqual((c7.estado_comando, self.ventilador.estado_hardware), ("fallido", "fuera_de_servicio"))
        critica = self.alerta("iot_comando_fallido")
        self.assertEqual(critica.nivel_severidad, "critica")
        self.assertIn("no se ejecutó en 2 intentos (último: falló: Relé trabado)", critica.descripcion_alerta)
        self.assertIsNone(AlertaIot.objects.get(alerta=critica).correo_enviado_en)  # el correo lo manda la revisión (D-71)
        panel = self.ver(self.cliente.get(self.url("monitoreo", invernadero=self.norte.pk)))
        self.assertIn("Comando fallido", panel)
        self.assertIn("Fuera de servicio", panel)
        self.assertIn("El actuador falló en 2 intentos", self.lista())
        revision.revisar(self.reloj)  # «en la vuelta siguiente de la revisión, el correo»
        self.assertIsNotNone(AlertaIot.objects.get(alerta=critica).correo_enviado_en)
        self.assertTrue(any("Comando fallido" in m.subject for m in mail.outbox))
        # Un actuador fuera de servicio no recibe comandos: la pantalla lo dice y la ficha no ofrece «Emitir comando» (D-30)
        self.assertIn("Volvé a activarlo desde Hardware antes de emitir comandos.", self.ver(self.cliente.get(self.url("comandos", invernadero=self.norte.pk, actuador=self.ventilador.pk))))
        self.assertNotIn("Emitir comando", self.ver(self.cliente.get(self.url("hardware_ficha", self.ventilador.pk))))
        # IOT-MOD-HDW: volver a activar el actuador (resuelve la alerta) para seguir
        # IOT-07 (regla 8 de IOT-MOD-HDW): el escalamiento creó la orden de mantenimiento del Técnico; al volver a activar hay que elegir qué hacer con ella (D-79, punto 8).
        orden = MantenimientoTecnico.objects.get()
        self.cliente.post(self.url("hardware_volver_a_activar", self.ventilador.pk), {f"decision_{orden.pk}": "cancelar"})
        self.recargar(self.ventilador)
        self.assertEqual(self.ventilador.estado_hardware, "activo")
        self.assertIsNone(self.alerta("iot_comando_fallido"))

        # ===== Escenario 8 · El nodo no reconoce el comando: fallido sin reintentos, acción incompatible, alerta, actuador activo =====
        self.avanzar(61)
        c8 = self.emitir(self.ventana, "Cerrar")
        self.avanzar(1, comunicar=True)
        self.retiro()
        respuesta = self.resultado(c8, "rechazado", detalle="CERRAR no está configurado para esta ventana.")
        self.assertEqual(respuesta["estado_comando"], "fallido")
        self.recargar(self.ventana, c8)
        self.assertEqual((c8.cantidad_intentos, c8.resultado_comando, self.ventana.estado_hardware, self.ventana.compatibilidad), (1, "rechazado", "activo", "incompatible"))
        self.assertEqual(list(self.ventana.acciones_incompatibles.values_list("nombre_accion", flat=True)), ["Cerrar"])
        incompatible = self.alerta("iot_configuracion_incompatible")
        self.assertIn("el nodo rechazó CERRAR (acción «Cerrar»)", incompatible.descripcion_alerta)
        self.assertIn("Rechazado por el nodo", self.lista())
        self.assertIn("El nodo no reconoció el comando", self.lista())
        formulario = self.ver(self.cliente.get(self.url("comandos", invernadero=self.norte.pk, actuador=self.ventana.pk)))
        self.assertNotIn(f'<option value="{self.accion(self.ventana, "Cerrar").pk}"', formulario)  # la acción deja de ofrecerse
        self.assertIn("El nodo no soporta:", formulario)

        # ===== Escenario 9 · Caída del nodo: no consume intentos, la revisión alerta, al volver se resuelve y el comando se ejecuta =====
        self.avanzar(61)
        c9 = self.emitir(self.ventilador, "Encender")
        self.avanzar(1, comunicar=True)
        self.assertEqual(self.retiro()["comandos"][0]["intento"], 1)  # lo retiró y «cae»: no responde
        self.avanzar(600)  # 10 minutos sin comunicación (el límite son 3)
        revision.revisar(self.reloj)
        self.assertIsNotNone(self.alerta("iot_nodo_sin_comunicacion"))
        self.recargar(self.ventilador, c9)
        self.assertEqual((c9.estado_comando, c9.cantidad_intentos, self.ventilador.estado_hardware), ("pendiente", 1, "activo"))  # nada consumido ni fuera de servicio
        self.assertEqual(RegistroComando.objects.filter(comando=c9, resultado="intento_fallido").count(), 0)
        volvio = self.retiro()["comandos"]  # el nodo vuelve (el retiro es una comunicación)
        self.assertEqual([(c["id"], c["intento"]) for c in volvio], [(c9.pk, 1)])  # se le descontó el intento vencido (2a.1a)
        self.assertIsNone(self.alerta("iot_nodo_sin_comunicacion"))  # al volver, se resuelve
        self.resultado(c9, "ejecutado", estado="encendido")
        self.recargar(c9)
        self.assertEqual(c9.estado_comando, "ejecutado")

        # ===== Escenario 13 · Cancelar un comando trabado: antes de vencer, cuánto falta; después, «Cancelado» y la ventana admite otro =====
        self.avanzar(61)
        c13 = self.emitir(self.ventilador, "Apagar")
        self.avanzar(1, comunicar=True)
        self.retiro()  # el nodo lo tiene y «no responde»
        self.avanzar(3)
        ventana = self.ver(self.cliente.get(self.url("comando_cancelar", c13.pk, volver="comandos"), **HX))
        self.assertIn("El nodo puede estar ejecutándolo: podés cancelarlo en 7 s.", ventana)
        self.assertNotIn("Cancelar comando", ventana)  # no ofrece confirmar
        self.assertIn("El nodo acaba de retirar el comando: no se canceló.", self.ver(self.cliente.post(self.url("comando_cancelar", c13.pk), {"volver": "comandos"}, **HX)))
        self.avanzar(8)  # venció el intento
        ventana = self.ver(self.cliente.get(self.url("comando_cancelar", c13.pk, volver="comandos"), **HX))
        self.assertIn(f"Cancelar CMD-{c13.pk}: Apagar sobre Ventilador norte/sectorA/ventilador. El nodo no lo va a recibir y no se reintenta.", ventana)
        respuesta = self.cliente.post(self.url("comando_cancelar", c13.pk), {"volver": "comandos"})
        self.assertEqual(respuesta.status_code, 302)
        self.recargar(c13)
        self.assertEqual(c13.estado_comando, "cancelado")
        self.assertIn("Cancelado", self.lista())
        self.assertEqual(self.resultado(c13, "ejecutado")["resultado"], "ya_resuelto")  # un resultado posterior se ignora (regla 4)
        self.assertEqual(self.retiro()["comandos"], [])  # y no se vuelve a entregar
        self.assertIn("Fijar velocidad", self.ver(self.cliente.get(self.url("comandos", invernadero=self.norte.pk, actuador=self.ventilador.pk))))
        self.emitir(self.ventilador, "Apagar")  # el actuador quedó libre: se admite otro
        Comando.objects.filter(estado_comando="pendiente").update(estado_comando="cancelado", resuelto_en=self.reloj)

        # ===== Paso 2 de la «Verificación a mano» · modo local: el resumen lo avisa y el comando espera con 0 intentos hasta «remoto» =====
        self.avanzar(61)
        self.modo("local")
        html = self.resumen(self.ventana, "Abrir")
        self.assertIn("El nodo está operando en modo local.", html)
        c2 = self.emitir(self.ventana, "Abrir")
        self.avanzar(30, comunicar=True)
        self.assertEqual(self.retiro()["comandos"], [])
        self.recargar(c2)
        self.assertEqual((c2.estado_comando, c2.cantidad_intentos), ("pendiente", 0))
        self.modo("remoto")
        self.assertEqual([c["intento"] for c in self.retiro()["comandos"]], [1])
        self.resultado(c2, "ejecutado", estado="abierto")

        # ===== Paso 3 · Producción · Bitácora: los registros de tipo «Comando», con cada intento =====
        bitacora = self.ver(self.cliente.get(reverse("produccion:bitacora"), {"invernadero": self.norte.pk}))
        self.assertIn("Comando", bitacora)
        self.assertIn("Falló: Relé trabado", bitacora)
        self.assertIn("Extractor" if False else "Ventilador norte/sectorA/ventilador: Apagar", bitacora)
        registros = RegistroComando.objects.filter(comando=c7).order_by("pk")
        self.assertEqual([(r.resultado, r.numero_intento) for r in registros], [("emitido", None), ("intento_fallido", 1), ("fallido", None)])
        self.assertEqual({r.tipo_evento for r in RegistroComando.objects.all()}, {"comando"})

        # ===== Paso 4 · Auditoría: emisión, cancelación y resolución del comando (el Gerente las ve) =====
        for accion in ("emision_comando", "cancelacion_comando", "resolucion_comando_iot"):
            self.assertTrue(RegistroAuditoria.objects.filter(accion=accion).exists(), accion)
        self.assertTrue(RegistroAuditoria.objects.filter(accion="resolucion_comando_iot", usuario__isnull=True).exists())  # InfoPonia, por el nodo
        self.entrar(self.gerente)
        auditoria = self.ver(self.cliente.get(reverse("core:auditoria")))
        for texto in ("Emisión de comando", "Cancelación de comando", "Resolución de comando (IoT)"):
            self.assertIn(texto, auditoria)

        # ===== Por rol y por estado =====
        # El Gerente con Agrónomo activo solo consulta: ve la lista, sin formulario ni botones; un POST a mano no escribe
        lista_del_gerente = self.lista()
        self.assertIn(f"CMD-{c13.pk}", lista_del_gerente)
        self.assertNotIn('name="paso"', lista_del_gerente)
        total = Comando.objects.count()
        self.assertEqual(self.cliente.post(self.url("comandos", invernadero=self.norte.pk), {"paso": "emitir"} | self.formulario(self.ventana, "Abrir")).status_code, 403)
        self.assertEqual(Comando.objects.count(), total)
        # ...pero opera donde no hay Agrónomo (Libre): emite y su comando queda sin Agrónomo, con su nombre en la auditoría
        self.assertIn("Operás este invernadero como Gerente", self.ver(self.cliente.get(self.url("comandos", invernadero=self.libre.pk))))
        libre = self.emitir(self.libre_ventilador, "Encender", invernadero=self.libre)
        self.assertIsNone(libre.agronomo_id)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="emision_comando").latest("pk").usuario_id, self.gerente.pk)
        # Técnico y Capataz: 403; un Agrónomo de otro invernadero: 404; sin sesión, al ingreso
        for otro in (self.tecnico, crear_capataz()):
            self.entrar(otro)
            self.assertEqual(self.cliente.get(self.url("comandos", invernadero=self.norte.pk)).status_code, 403)
        ajeno = crear_agronomo("ajeno@infoponia.com")
        crear_invernadero("Sur", agronomo=ajeno)
        self.entrar(ajeno)
        self.assertEqual(self.cliente.get(self.url("comandos", invernadero=self.norte.pk)).status_code, 404)
        self.assertEqual(self.cliente.get(self.url("comando_cancelar", c13.pk)).status_code, 404)
        self.cliente.logout()
        self.assertEqual(self.cliente.get(self.url("comandos", invernadero=self.norte.pk)).status_code, 302)
        # Con otro token, la API no entrega nada (IOT-RSV-CMD *a)
        self.assertEqual(self.nodo_http.get("/api/iot/v1/comandos", HTTP_AUTHORIZATION="Bearer otro").status_code, 401)
        self.assertEqual(Actuador.objects.get(pk=self.ventilador.pk).estado_hardware, "activo")
