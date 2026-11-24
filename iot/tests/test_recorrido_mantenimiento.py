# Recorrido de punta a punta de las órdenes de mantenimiento del IoT (IOT-07): los pasos de la «Verificación a mano» de la tarea y los escenarios 7, 15 y 16 de `docs/api/nodo/escenarios.md`, hechos por una
# prueba con el cliente de Django, en el orden en que los haría una persona (docs/patrones/verificacion_a_mano.md, D-96). El escalamiento del comando (el último intento que falla) se hace con el servicio
# de resultados de `comandos.py` y no por la API del nodo: la API ya la recorre `test_recorrido_comandos.py` (escenario 7), que además ve la orden creada. Cada paso nombra el caso de uso y la regla que
# verifica. Es una sola prueba larga a propósito: lo que se verifica es que el flujo completo encadena bien por rol y por estado, no cada regla suelta (eso lo hacen `test_iot_rsv_cmd_mantenimiento.py`,
# `test_cancelar_mantenimiento.py`, `test_iot_mod_hdw_ordenes.py`, `test_traspaso_tecnico.py`, `test_inicio_tecnico.py` y `test_mantenimiento_vistas.py`).

from datetime import datetime, timedelta, timezone as zona
from html import unescape

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from iot.models import Actuador, Comando, MantenimientoTecnico, NodoCentral, SistemaIoT
from iot.servicios import comandos
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.servicios import invernaderos
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_tecnico
from maestros.tests.test_prod_mod_inv import datos_de

AHORA = datetime(2026, 11, 23, 15, 0, tzinfo=zona.utc)
HX = {"HTTP_HX_REQUEST": "true"}
MOTIVO = "Se revisó el extractor en el invernadero"
ELIGE = "Elegí qué hacer con cada orden de mantenimiento."


class RecorridoDeMantenimientoTests(fabricas.ConCatalogoIot, TestCase):
    """Fuente: docs/casos_de_uso/iot/mantenimiento_automatico.md, resolver_comando.md, modificar_hardware.md (regla 8), baja_hardware.md y baja_sistema.md (precondición d), D-73, D-79 y D-98."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.tecnico = crear_tecnico("tecnico@infoponia.com", nombre="Tomás", apellido="Quiroga")
        self.nuevo = crear_tecnico("nuevo@infoponia.com", nombre="Nora", apellido="Paz")
        self.otro_tecnico = crear_tecnico("otro@infoponia.com", nombre="Omar", apellido="Gil")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=self.tecnico)
        self.libre = crear_invernadero("Libre")  # sin Agrónomo y, al principio, sin Técnico: lo opera el Gerente
        self.sistema = fabricas.sistema(self.norte)
        self.sistema_libre = fabricas.sistema(self.libre)
        for sistema in (self.sistema, self.sistema_libre):
            NodoCentral.objects.filter(sistema=sistema).update(ultima_comunicacion=AHORA - timedelta(seconds=30))
        self.tipo = fabricas.tipo_actuador("Extractor")
        self.encender = self.tipo.acciones.order_by("id").first()
        self.extractor = fabricas.actuador(self.sistema, self.tipo, "norte/extractor", ultimo_mensaje_en=AHORA - timedelta(hours=1))
        self.libre_extractor = fabricas.actuador(self.sistema_libre, self.tipo, "libre/extractor", ultimo_mensaje_en=AHORA - timedelta(hours=1))
        self.cliente = Client()

    # ---- ayudas ----

    def url(self, nombre, *args):
        return reverse(f"iot:{nombre}", args=args)

    def ver(self, respuesta):
        return unescape(respuesta.content.decode())

    def entrar(self, cuenta):
        self.cliente.force_login(cuenta)

    def fallar(self, actuador):
        """El nodo informa «falló» en el último intento de un comando del actuador: el escalamiento (IOT-RSV-CMD, extensión 4b)."""
        sistema = actuador.sistema
        comando = fabricas.comando(actuador, self.encender)
        Comando.objects.filter(pk=comando.pk).update(cantidad_intentos=4, ultimo_intento_en=AHORA - timedelta(seconds=10))
        informe = comandos.ResultadoRecibido(resultado="fallo", detalle="Sin corriente", estado=None, informado_en=None)
        comandos.registrar_resultado(sistema.pk, comando.pk, informe, AHORA)
        actuador.refresh_from_db()

    def alerta_de(self, actuador):
        return Alerta.objects.filter(tipo_alerta="iot_comando_fallido", estado_alerta="activa", descripcion_alerta__startswith=actuador.identificador_equipo).first()

    def ordenes(self, actuador):
        return list(MantenimientoTecnico.objects.filter(hardware=actuador).order_by("pk"))

    def a_realizar(self, actuador):
        return [o for o in self.ordenes(actuador) if o.estado_orden == "a_realizar"]

    def ficha(self, equipo=None):
        return self.url("hardware_ficha", (equipo or self.extractor).pk)

    def cancelar_orden(self, orden, motivo=MOTIVO, equipo=None):
        return self.cliente.post(self.url("hardware_cancelar_orden", (equipo or self.extractor).pk, orden.pk), {"motivo": motivo}, follow=True)

    def volver_a_activar(self, equipo, **decisiones):
        return self.cliente.post(self.url("hardware_volver_a_activar", equipo.pk), {f"decision_{pk}": valor for pk, valor in decisiones.items()}, follow=True)

    def inicio_de(self, cuenta):
        cliente = Client()
        cliente.force_login(cuenta)
        return self.ver(cliente.get("/"))

    # ---- el recorrido ----

    def test_recorrido_de_mantenimiento_de_punta_a_punta(self):
        # ===== Escenario 7 (sin Técnico) · IOT-RSV-CMD 4b.4a: Libre no tiene Técnico: no se crea la orden y la alerta lo dice =====
        self.fallar(self.libre_extractor)
        self.assertEqual(self.libre_extractor.estado_hardware, "fuera_de_servicio")
        self.assertEqual(self.ordenes(self.libre_extractor), [])
        self.assertIn("El invernadero no tiene Técnico: la orden de mantenimiento deberá planificarse cuando se asigne uno.", self.alerta_de(self.libre_extractor).descripcion_alerta)
        self.assertEqual(Notificacion.objects.filter(destinatario__in=[self.tecnico, self.nuevo, self.otro_tecnico]).count(), 0)

        # ===== Escenario 7 · IOT-RSV-CMD 4b.4 y postcondiciones k y l: Norte sí tiene Técnico: orden «revisión» alta para hoy, alerta que la nombra y aviso =====
        self.fallar(self.extractor)
        (orden,) = self.ordenes(self.extractor)
        self.assertEqual((orden.estado_orden, orden.prioridad_orden, orden.tipo_mantenimiento, orden.tecnico_id, orden.agronomo_id), ("a_realizar", "alta", "revision", self.tecnico.pk, None))
        self.assertIn(f"Orden de mantenimiento {orden.codigo} asignada a Tomás Quiroga.", self.alerta_de(self.extractor).descripcion_alerta)
        self.assertEqual(orden.alerta_id, self.alerta_de(self.extractor).pk)
        (aviso,) = Notificacion.objects.filter(destinatario=self.tecnico)
        self.assertEqual(aviso.titulo, f"Orden {orden.codigo} de mantenimiento asignada")
        self.assertIn("resolucion_comando_iot", set(RegistroAuditoria.objects.values_list("accion", flat=True)))

        # ===== IOT-CNS-HDW regla 6 y D-30: la ficha muestra la orden; «Cancelar orden» solo para quien opera =====
        self.entrar(self.laura)
        ficha = self.ver(self.cliente.get(self.ficha()))
        for texto in ("Órdenes de mantenimiento", orden.codigo, "A realizar", "Alta", "Tomás Quiroga", "Cancelar orden"):
            self.assertIn(texto, ficha)
        self.entrar(self.gerente)  # Norte tiene Agrónomo activo: el Gerente consulta
        ficha = self.ver(self.cliente.get(self.ficha()))
        self.assertIn(orden.codigo, ficha)
        self.assertNotIn("Cancelar orden", ficha)
        ruta_de_cancelar = self.url("hardware_cancelar_orden", self.extractor.pk, orden.pk)
        self.assertEqual(self.cliente.get(ruta_de_cancelar).status_code, 403)
        self.assertEqual(self.cliente.post(ruta_de_cancelar, {"motivo": MOTIVO}).status_code, 403)
        for cuenta, estado in ((self.tecnico, 403), (crear_capataz(), 403), (crear_agronomo("otra@infoponia.com"), 404)):
            self.entrar(cuenta)
            self.assertEqual(self.cliente.get(self.ficha()).status_code, estado)
            self.assertEqual(self.cliente.post(ruta_de_cancelar, {"motivo": MOTIVO}).status_code, estado)
        self.assertEqual(self.a_realizar(self.extractor), [orden])

        # ===== Escenario 7 · el Técnico ve la orden en su Inicio; otro rol no tiene la sección =====
        self.assertIn(orden.codigo, self.inicio_de(self.tecnico))
        self.assertIn("Mantenimientos a realizar", self.inicio_de(self.tecnico))
        self.assertNotIn("Mantenimientos a realizar", self.inicio_de(self.laura))
        self.assertNotIn(orden.codigo, self.inicio_de(self.nuevo))

        # ===== IOT-BAJ-HDW e IOT-BAJ-SIS, precondición d: con la orden a realizar, ni el equipo ni el sistema se dan de baja =====
        self.entrar(self.laura)
        ventana = self.ver(self.cliente.get(self.url("hardware_baja", self.extractor.pk), **HX))
        self.assertIn(f"Está en la orden de mantenimiento {orden.codigo}, a realizar: cancelala desde «Órdenes de mantenimiento», en la ficha del equipo.", ventana)
        self.cliente.post(self.url("hardware_baja", self.extractor.pk))
        self.assertEqual(Actuador.objects.get(pk=self.extractor.pk).estado_hardware, "fuera_de_servicio")
        ventana = self.ver(self.cliente.get(self.url("sistema_baja", self.sistema.pk), **HX))
        self.assertIn(f"Hay 1 orden(es) de mantenimiento a realizar ({orden.codigo}): cancelalas desde la ficha de cada equipo.", ventana)
        self.cliente.post(self.url("sistema_baja", self.sistema.pk))
        self.assertEqual(SistemaIoT.objects.get(pk=self.sistema.pk).estado_sistema, "activo")

        # ===== PROD-CNL-ORD para un mantenimiento · Escenario 15: cancelar desde la ficha (motivo obligatorio) =====
        ventana = self.ver(self.cliente.get(ruta_de_cancelar, **HX))
        for texto in (f"Cancelar la orden {orden.codigo}", "norte/extractor", "Tomás Quiroga", "La alerta «comando fallido» sigue activa", "Motivo de la cancelación"):
            self.assertIn(texto, ventana)
        self.assertIn("Indicá el motivo de la cancelación.", self.ver(self.cliente.post(ruta_de_cancelar, {"motivo": "  "})))  # 6a
        self.assertIn("El motivo no puede pasar de 300 caracteres.", self.ver(self.cliente.post(ruta_de_cancelar, {"motivo": "x" * 301})))
        self.assertEqual(self.a_realizar(self.extractor), [orden])
        respuesta = self.cancelar_orden(orden)
        self.assertRedirects(respuesta, self.ficha())
        self.assertIn(f"{orden.codigo} cancelada.", self.ver(respuesta))
        orden.refresh_from_db()
        self.extractor.refresh_from_db()
        self.assertEqual((orden.estado_orden, orden.motivo_cancelacion, self.extractor.estado_hardware), ("cancelada", MOTIVO, "fuera_de_servicio"))  # postcondición j: el equipo no cambia
        self.assertIsNotNone(self.alerta_de(self.extractor))  # D-73, punto 4: la alerta sigue activa
        self.assertEqual(Notificacion.objects.filter(destinatario=self.tecnico, titulo__endswith="cancelada").count(), 1)  # postcondición k
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_orden").count(), 1)  # postcondición m
        self.assertEqual(self.ver(self.cliente.get(self.url("hardware_cancelar_orden", self.extractor.pk, orden.pk), follow=True)).count("La orden ya no está a realizar"), 1)  # 8a
        self.assertNotIn(orden.codigo, self.inicio_de(self.tecnico))
        # La cancelada queda en la ficha con su motivo y sin botón
        ficha = self.ver(self.cliente.get(self.ficha()))
        self.assertIn(f"Motivo: {MOTIVO}", ficha)
        self.assertNotIn("Cancelar orden", ficha)

        # ===== IOT-MOD-HDW regla 8 · sin órdenes a realizar, volver a activar es el de IOT-02: resuelve la alerta =====
        self.assertEqual(self.volver_a_activar(self.extractor).status_code, 200)
        self.extractor.refresh_from_db()
        self.assertEqual(self.extractor.estado_hardware, "activo")
        self.assertIsNone(self.alerta_de(self.extractor))

        # ===== Nuevo fallo → nueva orden → volver a activar eligiendo «Mantenerla» (escenario 16) =====
        self.fallar(self.extractor)
        (_, segunda) = self.ordenes(self.extractor)
        self.assertEqual(segunda.estado_orden, "a_realizar")
        ventana = self.ver(self.cliente.get(self.url("hardware_volver_a_activar", self.extractor.pk), **HX))
        self.assertIn("Órdenes de mantenimiento a realizar", ventana)
        self.assertIn(f'name="decision_{segunda.pk}" value="cancelar" checked', ventana)
        self.assertIn(ELIGE, self.ver(self.cliente.post(self.url("hardware_volver_a_activar", self.extractor.pk), {})))  # sin elegir no activa
        self.assertEqual(Actuador.objects.get(pk=self.extractor.pk).estado_hardware, "fuera_de_servicio")
        self.volver_a_activar(self.extractor, **{str(segunda.pk): "mantener"})
        self.extractor.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual((self.extractor.estado_hardware, segunda.estado_orden), ("activo", "a_realizar"))
        # IOT-RSV-CMD 4b.4b: otro fallo con la orden «a realizar» todavía vigente no crea otra y la alerta la nombra
        self.fallar(self.extractor)
        self.assertEqual(self.a_realizar(self.extractor), [segunda])
        self.assertEqual(len(self.ordenes(self.extractor)), 2)
        self.assertIn(f"Ya está en la orden de mantenimiento {segunda.codigo}, a realizar.", self.alerta_de(self.extractor).descripcion_alerta)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.tecnico, titulo__endswith="asignada").count(), 2)  # la 2.ª no avisó otra vez

        # ===== Volver a activar eligiendo «Cancelarla» =====
        self.volver_a_activar(self.extractor, **{str(segunda.pk): "cancelar"})
        self.extractor.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual((self.extractor.estado_hardware, segunda.estado_orden, segunda.motivo_cancelacion), ("activo", "cancelada", "Se volvió a activar el equipo norte/extractor."))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="reactivacion_hardware", detalle__datos__ordenes_canceladas=[segunda.codigo]).count(), 1)

        # ===== Una orden que incluye otro equipo fuera de servicio solo se puede mantener (D-79, punto 8) =====
        otro = fabricas.actuador(self.sistema, self.tipo, "norte/otro", estado="fuera_de_servicio")
        compartida = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.extractor, otro])
        Actuador.objects.filter(pk=self.extractor.pk).update(estado_hardware="fuera_de_servicio")
        ventana = self.ver(self.cliente.get(self.url("hardware_volver_a_activar", self.extractor.pk), **HX))
        self.assertIn("Incluye otros equipos fuera de servicio: ", ventana)
        self.assertNotIn(f'name="decision_{compartida.pk}" value="cancelar"', ventana)
        self.volver_a_activar(self.extractor, **{str(compartida.pk): "cancelar"})  # pedirla igual no la cancela
        compartida.refresh_from_db()
        self.assertEqual(compartida.estado_orden, "a_realizar")
        self.entrar(self.laura)
        self.cancelar_orden(compartida)  # la cancelación desde la ficha sí puede
        compartida.refresh_from_db()
        self.assertEqual(compartida.estado_orden, "cancelada")
        Actuador.objects.filter(pk=self.extractor.pk).update(estado_hardware="activo")
        Actuador.objects.filter(pk=otro.pk).update(estado_hardware="inactivo")

        # ===== Escenario 16 · PROD-MOD-INV regla 3: al asignar otro Técnico a Norte, las órdenes a realizar pasan a él =====
        self.fallar(self.extractor)
        (tercera,) = self.a_realizar(self.extractor)
        self.assertEqual(tercera.tecnico_id, self.tecnico.pk)
        self.entrar(self.gerente)
        invernaderos.modificar_invernadero(self.gerente, self.norte.pk, **(datos_de(self.norte) | {"tecnico_id": self.nuevo.pk, "personal_confirmado": True}))
        tercera.refresh_from_db()
        self.assertEqual(tercera.tecnico_id, self.nuevo.pk)
        aviso = Notificacion.objects.get(destinatario=self.nuevo, titulo="Quedó a cargo de Norte")
        self.assertIn("mantenimientos técnicos a realizar: 1", aviso.detalle)
        self.assertIn(tercera.codigo, self.inicio_de(self.nuevo))
        self.assertNotIn(tercera.codigo, self.inicio_de(self.tecnico))
        self.assertTrue(RegistroAuditoria.objects.filter(accion="modificacion_invernadero").exists())

        # ===== Quien cancela avisa al Técnico de ahora, no al anterior; después la baja del equipo se confirma =====
        self.entrar(self.laura)
        avisos_del_anterior = Notificacion.objects.filter(destinatario=self.tecnico).count()
        self.cancelar_orden(tercera)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.nuevo, titulo__endswith="cancelada").count(), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.tecnico).count(), avisos_del_anterior)
        self.cliente.post(self.url("hardware_baja", self.extractor.pk))
        self.assertEqual(Actuador.objects.get(pk=self.extractor.pk).estado_hardware, "inactivo")

        # ===== Gerente sin Agrónomo activo (Libre): opera él. Asignar un Técnico al invernadero y volver a fallar crea la orden; el Gerente la cancela =====
        invernaderos.modificar_invernadero(self.gerente, self.libre.pk, **(datos_de(self.libre) | {"tecnico_id": self.otro_tecnico.pk, "personal_confirmado": True}))
        self.entrar(self.gerente)
        self.volver_a_activar(self.libre_extractor)  # la alerta anterior se resuelve
        self.fallar(self.libre_extractor)
        (de_libre,) = self.ordenes(self.libre_extractor)
        self.assertEqual(de_libre.tecnico_id, self.otro_tecnico.pk)
        self.assertIn("Cancelar orden", self.ver(self.cliente.get(self.ficha(self.libre_extractor))))
        self.cancelar_orden(de_libre, equipo=self.libre_extractor)
        de_libre.refresh_from_db()
        self.assertEqual(de_libre.estado_orden, "cancelada")
