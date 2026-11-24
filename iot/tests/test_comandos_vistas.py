# Pruebas de las pantallas de comandos (IOT-05, paso 7; docs/casos_de_uso/iot/emitir_comando.md y cancelar_comando.md, «Cómo se aplica» y «Pantallas»; D-29, D-30): la pestaña «Comandos»
# (formulario de emisión, resumen con sus advertencias, lista con filtros y paginación), la ventana de cancelar, y lo que suma a la ficha del actuador y al panel de monitoreo.
# Integración con el cliente de prueba de Django: permisos y alcance (otros roles 403, fuera del alcance 404, el Gerente con Agrónomo activo en solo lectura, ningún botón lleva a
# un 403) y el flujo con HTMX y sin él. Las reglas de negocio las prueban ``test_iot_emt_cmd.py``, ``test_iot_cnl_cmd.py`` y ``test_iot_rsv_cmd.py``.

import re
from datetime import timedelta
from html import unescape

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from iot.models import Comando, NodoCentral, RegistroComando
from iot.tests import fabricas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_sector, crear_tecnico, crear_vendedor

HX = {"HTTP_HX_REQUEST": "true"}
ACCIONES = [("Encender", "ENCENDER"), ("Apagar", "APAGAR"), ("Fijar velocidad", "FIJAR_NIVEL", 0, 100, "%")]


class ComandosVistasBase(fabricas.ConCatalogoIot, TestCase):
    """Laura es la Agrónoma de Norte (con sistema, un sector y un extractor); Libre no tiene Agrónomo (lo opera el Gerente)."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=crear_tecnico("t@infoponia.com"))
        self.libre = crear_invernadero("Libre")
        self.sistema = fabricas.sistema(self.norte)
        self.sistema_libre = fabricas.sistema(self.libre)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=timezone.now())
        self.sector = crear_sector(self.norte, "Sector A")
        self.tipo = fabricas.tipo_actuador("Extractor", acciones=ACCIONES)
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/extractor", sector=self.sector, ultimo_mensaje_en=timezone.now())
        self.encender, self.apagar, self.velocidad = self.tipo.acciones.order_by("id")
        self.actuador_libre = fabricas.actuador(self.sistema_libre, self.tipo, "libre/extractor", ultimo_mensaje_en=timezone.now())

    def url(self, nombre, *args, invernadero=None, **consulta):
        ruta = reverse(f"iot:{nombre}", args=args)
        if invernadero is not None:
            consulta = {"invernadero": invernadero.pk} | consulta
        return ruta + ("?" + "&".join(f"{k}={v}" for k, v in consulta.items()) if consulta else "")

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def pagina(self, cuenta=None, **consulta):
        self.entrar(cuenta or self.laura)
        return self.client.get(self.url("comandos", invernadero=self.norte, **consulta))

    def paso(self, paso, actuador=None, accion=None, valor="", descripcion="", cuenta=None, invernadero=None, htmx=False, **extra):
        """Un POST del formulario de emisión."""
        self.entrar(cuenta or self.laura)
        datos = {"paso": paso, "actuador": (actuador or self.actuador).pk, "accion": (accion or self.encender).pk, "valor": valor, "descripcion": descripcion}
        return self.client.post(self.url("comandos", invernadero=invernadero or self.norte), datos | extra, **(HX if htmx else {}))

    def pendiente(self, **extra):
        return fabricas.comando(self.actuador, self.encender, agronomo=self.laura, **extra)

    def texto(self, respuesta):
        return unescape(respuesta.content.decode())

    def botones(self, html, texto):
        return len(re.findall(rf">\s*{re.escape(texto)}\s*<", html))


class AccesoAComandosVistaTests(ComandosVistasBase):
    """Permisos y alcance."""

    def test_el_agronomo_y_el_gerente_ven_la_pestana(self):
        for cuenta in (self.laura, self.gerente):
            self.assertEqual(self.pagina(cuenta).status_code, 200)

    def test_otros_roles_reciben_403(self):
        for cuenta in (crear_capataz(), crear_administrador(), crear_vendedor(), crear_tecnico("otro@infoponia.com")):
            self.assertEqual(self.pagina(cuenta).status_code, 403)

    def test_un_agronomo_de_otro_invernadero_recibe_404_y_sin_sesion_va_al_ingreso(self):
        otro = crear_agronomo("otro@infoponia.com")
        crear_invernadero("Sur", agronomo=otro)
        self.assertEqual(self.pagina(otro).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url("comandos", invernadero=self.norte)).status_code, 302)

    def test_la_pestana_comandos_esta_en_el_modulo_y_activa(self):
        html = self.texto(self.pagina())
        pestanas = re.findall(r'<a class="tab"[^>]*>([^<]+)</a>', html)
        self.assertEqual(pestanas, ["Monitoreo", "Comandos", "Reglas de actuación", "Hardware", "Sistema IoT", "Tipos de actuador"])
        self.assertIn('aria-selected="true"', re.search(r'<a class="tab"[^>]*>Comandos</a>', html).group(0))

    def test_el_gerente_con_agronomo_activo_solo_consulta_sin_formulario_ni_botones(self):
        """Regla «Alcance»: el Gerente solo consulta donde hay un Agrónomo activo: sin formulario y sin «Cancelar»; el aviso lo dice."""
        self.pendiente()
        html = self.texto(self.pagina(self.gerente))
        self.assertNotIn("Emitir comando", html)
        self.assertNotIn('name="paso"', html)
        self.assertEqual(self.botones(html, "Cancelar"), 0)
        self.assertIn("tiene Agrónomo activo", html)
        self.assertIn("CMD-", html)  # pero ve la lista

    def test_el_gerente_opera_un_invernadero_sin_agronomo(self):
        self.entrar(self.gerente)
        html = self.texto(self.client.get(self.url("comandos", invernadero=self.libre)))
        self.assertIn("Emitir comando", html)
        self.assertIn("Operás este invernadero como Gerente", html)

    def test_un_post_de_quien_solo_consulta_es_403_y_no_escribe(self):
        respuesta = self.paso("emitir", cuenta=self.gerente)
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(Comando.objects.count(), 0)

    def test_un_invernadero_sin_sistema_lo_dice_y_no_ofrece_formulario(self):
        sin = crear_invernadero("Sin sistema", agronomo=self.laura)
        self.entrar(self.laura)
        html = self.texto(self.client.get(self.url("comandos", invernadero=sin)))
        self.assertIn("no tiene Sistema IoT", html)
        self.assertNotIn('name="paso"', html)

    def test_el_metodo_no_permitido_es_405(self):
        self.entrar(self.laura)
        self.assertEqual(self.client.put(self.url("comandos", invernadero=self.norte)).status_code, 405)


class EmitirDesdeLaPantallaVistaTests(ComandosVistasBase):
    """El formulario, el resumen y la emisión."""

    def test_el_formulario_lista_los_actuadores_activos_con_su_sector(self):
        html = self.texto(self.pagina())
        self.assertIn("Extractor · norte/extractor (Sector A)", html)
        self.assertNotIn("libre/extractor", html)
        self.assertIn('name="paso" value="resumen"', html)

    def test_con_actuador_en_la_url_desde_la_ficha_ya_viene_elegido_con_sus_acciones(self):
        """Extensión 1b: «Emitir comando» desde la ficha abre la pantalla con ``?actuador=``."""
        html = self.texto(self.pagina(actuador=self.actuador.pk))
        self.assertRegex(html, rf'<option value="{self.actuador.pk}" selected>')
        for nombre in ("Encender", "Apagar", "Fijar velocidad"):
            self.assertIn(f">{nombre}</option>", html)

    def test_el_campo_valor_aparece_solo_si_la_accion_lo_lleva_con_su_rango(self):
        sin = self.texto(self.paso("refrescar", accion=self.encender))
        self.assertNotIn('name="valor"', sin)
        con = self.texto(self.paso("refrescar", accion=self.velocidad))
        self.assertIn('name="valor"', con)
        self.assertIn("Número entero entre 0 y 100 %.", con)

    def test_refrescar_no_valida_ni_escribe(self):
        """Interacción HTMX: elegir el actuador o la acción vuelve a dibujar el formulario sin errores y sin escribir."""
        respuesta = self.paso("refrescar", accion=self.velocidad, valor="abc")
        self.assertNotIn("sin decimales", self.texto(respuesta))
        self.assertEqual(Comando.objects.count(), 0)

    def test_con_htmx_el_refresco_devuelve_solo_el_formulario(self):
        respuesta = self.paso("refrescar", accion=self.velocidad, htmx=True)
        html = self.texto(respuesta)
        self.assertIn('id="emision"', html)
        self.assertNotIn("<html", html)
        self.assertNotIn('id="tabla-de-comandos"', html)

    def test_el_resumen_muestra_los_datos_y_pide_confirmar_sin_escribir(self):
        respuesta = self.paso("resumen", accion=self.velocidad, valor="60", descripcion="Ventilar")
        html = self.texto(respuesta)
        self.assertIn("Resumen del comando", html)
        self.assertIn("Fijar velocidad", html)
        self.assertIn("60 %", html)
        self.assertIn("Ventilar", html)
        self.assertIn('name="paso" value="emitir"', html)
        self.assertIn(">Cambiar<", html)
        self.assertEqual((Comando.objects.count(), RegistroComando.objects.count(), RegistroAuditoria.objects.filter(accion="emision_comando").count()), (0, 0, 0))

    def test_el_resumen_con_sus_advertencias_y_sus_textos(self):
        """Extensiones 6c a 6g con los textos de «Cómo se aplica»."""
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_informado="encendido", estado_informado_en=timezone.now(), ultimo_mensaje_en=None)
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local", ultima_comunicacion=timezone.now() - timedelta(hours=1))
        html = self.texto(self.paso("resumen", accion=self.encender))
        self.assertIn("el actuador ya está encendido", html)
        self.assertIn("Del actuador nunca llegó ningún mensaje.", html)
        self.assertIn("El nodo está sin señal.", html)
        self.assertIn("El nodo está operando en modo local.", html)
        self.assertLess(html.index("ya está encendido"), html.index("nunca llegó ningún mensaje"))
        self.assertLess(html.index("nunca llegó ningún mensaje"), html.index("sin señal"))
        self.assertLess(html.index("sin señal"), html.index("modo local"))

    def test_los_errores_van_junto_al_campo_y_no_se_escribe(self):
        """Extensión 6a: el error por campo, con el rango; falta el actuador o la acción."""
        malo = self.texto(self.paso("resumen", accion=self.velocidad, valor="150"))
        self.assertIn("Ingresá un número entero entre 0 y 100 %, sin decimales.", malo)
        self.assertEqual(self.texto(self.paso("resumen", accion=self.velocidad, valor="")).count("Ingresá el valor"), 1)
        self.entrar(self.laura)
        sin_actuador = self.texto(self.client.post(self.url("comandos", invernadero=self.norte), {"paso": "resumen"}))
        self.assertIn("Seleccioná un actuador.", sin_actuador)
        self.assertEqual(Comando.objects.count(), 0)

    def test_confirmar_emite_el_comando_avisa_y_vuelve_a_la_lista(self):
        """Paso 9: el aviso con el código; el comando, pendiente, con su bitácora y su auditoría."""
        respuesta = self.paso("emitir", accion=self.velocidad, valor="60", descripcion="Antes del mediodía")
        self.assertRedirects(respuesta, self.url("comandos", invernadero=self.norte), fetch_redirect_response=False)
        comando = Comando.objects.get()
        self.assertEqual((comando.estado_comando, comando.valor_comando, comando.agronomo_id), ("pendiente", 60, self.laura.pk))
        html = self.texto(self.client.get(respuesta["Location"]))
        self.assertIn(f"Comando CMD-{comando.pk} pendiente. El nodo lo retira en su próxima consulta; el resultado se verá en Monitoreo y en la ficha del actuador.", html)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="emision_comando").count(), 1)

    def test_el_gerente_emite_donde_no_hay_agronomo(self):
        respuesta = self.paso("emitir", actuador=self.actuador_libre, cuenta=self.gerente, invernadero=self.libre)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIsNone(Comando.objects.get().agronomo_id)

    def test_ext_8a_un_actuador_con_comando_pendiente_bloquea_y_ofrece_cancelar(self):
        """Extensión 3a: informa el pendiente («Cancelalo o esperá su resultado») y ofrece «Cancelar» si se puede; no ofrece emitir."""
        pendiente = self.pendiente()
        html = self.texto(self.pagina(actuador=self.actuador.pk))
        self.assertIn(f"Ya hay un comando pendiente para este actuador (CMD-{pendiente.pk}). Cancelalo o esperá su resultado", html)
        self.assertIn(f"Cancelar CMD-{pendiente.pk}", html)
        self.assertRegex(html, r'name="paso" value="resumen"[^>]*disabled')

    def test_ext_8a_si_otro_lo_emitio_antes_la_emision_informa_el_pendiente_y_no_escribe_de_mas(self):
        self.pendiente()
        html = self.texto(self.paso("emitir", accion=self.apagar))
        self.assertIn("Ya hay un comando pendiente", html)
        self.assertEqual(Comando.objects.count(), 1)

    def test_ext_8b_un_sistema_desconectado_lo_informa(self):
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        html = self.texto(self.paso("emitir"))
        self.assertIn("El sistema IoT está desconectado", html)
        self.assertEqual(Comando.objects.count(), 0)

    def test_un_actuador_fuera_de_servicio_dice_que_hay_que_volver_a_activarlo(self):
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_hardware="fuera_de_servicio")
        html = self.texto(self.pagina(actuador=self.actuador.pk))
        self.assertIn("Volvé a activarlo desde Hardware antes de emitir comandos.", html)

    def test_un_actuador_de_otro_invernadero_en_la_url_es_404(self):
        self.entrar(self.laura)
        self.assertEqual(self.client.get(self.url("comandos", invernadero=self.norte, actuador=self.actuador_libre.pk)).status_code, 404)

    def test_las_acciones_incompatibles_no_se_ofrecen_y_se_avisa(self):
        self.actuador.acciones_incompatibles.add(self.apagar)
        html = self.texto(self.pagina(actuador=self.actuador.pk))
        self.assertNotIn(f'<option value="{self.apagar.pk}"', html)
        self.assertIn("El nodo no soporta:", html)
        self.assertIn("Apagar", html)


class ListaDeComandosVistaTests(ComandosVistasBase):
    """La lista, sus filtros y su paginación."""

    def armar(self):
        ahora = timezone.now()
        self.ejecutado = fabricas.comando(self.actuador, self.encender, estado="ejecutado", resuelto_en=ahora, cantidad_intentos=1, ultimo_intento_en=ahora, agronomo=self.laura)
        self.fallido = fabricas.comando(self.actuador, self.apagar, estado="fallido", resuelto_en=ahora, cantidad_intentos=4, resultado_comando="fallo", detalle_resultado="Sin corriente")
        regla = fabricas.regla(fabricas.sensor(self.sistema), self.actuador)
        self.de_regla = fabricas.comando(self.actuador, self.encender, estado="cancelado", resuelto_en=ahora, regla=regla)
        self.pend = self.pendiente()

    def test_la_lista_trae_las_columnas_y_el_mas_reciente_primero(self):
        self.armar()
        html = self.texto(self.pagina())
        for encabezado in ("Código", "Actuador y acción", "Origen", "Estado", "Intentos", "Último intento"):
            self.assertIn(f"<th>{encabezado}</th>", html)
        self.assertLess(html.index(f"CMD-{self.pend.pk}"), html.index(f"CMD-{self.ejecutado.pk}"))
        self.assertIn("Regla de actuación · RGL-", html)
        self.assertIn("0 de 4", html)
        self.assertIn("1 de 4", html)

    def test_el_origen_manual_dice_quien_lo_emitio(self):
        self.paso("emitir", accion=self.encender)
        self.assertIn("Manual · ", self.texto(self.client.get(self.url("comandos", invernadero=self.norte))))

    def test_un_fallido_explica_que_paso_y_un_rechazado_se_distingue(self):
        self.armar()
        self.assertIn("El actuador falló en 4 intentos", self.texto(self.pagina()))
        Comando.objects.filter(pk=self.fallido.pk).update(resultado_comando="rechazado", detalle_resultado="No lo conozco")
        html = self.texto(self.pagina())
        self.assertIn("Rechazado por el nodo", html)
        self.assertIn("El nodo no reconoció el comando: No lo conozco.", html)

    def test_los_filtros_por_estado_actuador_y_origen(self):
        self.armar()
        solo_pendientes = self.texto(self.pagina(estado="pendiente"))
        self.assertIn(f"CMD-{self.pend.pk}", solo_pendientes)
        self.assertNotIn(f"CMD-{self.ejecutado.pk}", solo_pendientes)
        automaticos = self.texto(self.pagina(origen="regla"))
        self.assertIn(f"CMD-{self.de_regla.pk}", automaticos)
        self.assertNotIn(f"CMD-{self.ejecutado.pk}", automaticos)
        manuales = self.texto(self.pagina(origen="manual"))
        self.assertNotIn(f"CMD-{self.de_regla.pk}", manuales)
        otro = fabricas.actuador(self.sistema, self.tipo, "norte/otro")
        del_otro = fabricas.comando(otro, self.encender)
        por_actuador = self.texto(self.pagina(filtro_actuador=otro.pk))
        self.assertIn(f"CMD-{del_otro.pk}", por_actuador)
        self.assertNotIn(f"CMD-{self.ejecutado.pk}", por_actuador)
        self.assertIn("Limpiar filtros", por_actuador)

    def test_un_filtro_desconocido_no_filtra_ni_rompe(self):
        self.armar()
        self.assertEqual(self.pagina(estado="inventado", origen="x", filtro_actuador="abc").status_code, 200)

    def test_sin_resultados_lo_dice(self):
        self.assertIn("Todavía no se emitió ningún comando", self.texto(self.pagina()))
        self.armar()
        self.assertIn("No hay comandos con estos filtros.", self.texto(self.pagina(estado="pendiente", filtro_actuador=fabricas.actuador(self.sistema, self.tipo, "norte/vacio").pk)))

    def test_con_htmx_el_filtro_devuelve_solo_la_tabla(self):
        self.armar()
        self.entrar(self.laura)
        html = self.texto(self.client.get(self.url("comandos", invernadero=self.norte, estado="ejecutado"), **HX))
        self.assertIn("<table", html)
        self.assertNotIn("<html", html)
        self.assertNotIn(f"CMD-{self.fallido.pk}", html)

    def test_la_paginacion_es_de_a_25_y_conserva_los_filtros(self):
        for _ in range(30):
            fabricas.comando(self.actuador, self.encender, estado="ejecutado")
        html = self.texto(self.pagina(estado="ejecutado"))
        self.assertEqual(len(re.findall(r'<span class="id">CMD-', html)), 25)
        self.assertIn("Página 1 de 2", html)
        self.assertIn("estado=ejecutado&pagina=2", html)
        segunda = self.texto(self.pagina(estado="ejecutado", pagina=2))
        self.assertEqual(len(re.findall(r'<span class="id">CMD-', segunda)), 5)
        self.assertEqual(self.pagina(pagina=99).status_code, 200)  # fuera de rango: se acota

    def test_cancelar_aparece_en_los_pendientes_de_quien_opera_y_deshabilitado_dentro_de_la_espera(self):
        pendiente = self.pendiente()
        html = self.texto(self.pagina())
        self.assertIn(self.url("comando_cancelar", pendiente.pk, volver="comandos"), html)
        Comando.objects.filter(pk=pendiente.pk).update(cantidad_intentos=1, ultimo_intento_en=timezone.now())
        html = self.texto(self.pagina())
        self.assertIn("El nodo puede estar ejecutándolo: podés cancelarlo en", html)
        self.assertNotIn(self.url("comando_cancelar", pendiente.pk, volver="comandos"), html)


class CancelarDesdeLaPantallaVistaTests(ComandosVistasBase):
    """La ventana y el POST de cancelar."""

    def test_la_ventana_con_htmx_es_un_fragmento_con_el_texto_del_extracto(self):
        pendiente = self.pendiente()
        self.entrar(self.laura)
        respuesta = self.client.get(self.url("comando_cancelar", pendiente.pk, volver="comandos"), **HX)
        html = self.texto(respuesta)
        self.assertNotIn("<html", html)
        self.assertIn(f"Cancelar CMD-{pendiente.pk}: Encender sobre Extractor norte/extractor. El nodo no lo va a recibir y no se reintenta.", html)
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado_comando, "pendiente")  # abrir la ventana no cambia nada

    def test_sin_javascript_es_la_pagina_de_comandos_con_la_ventana_abierta(self):
        pendiente = self.pendiente()
        self.entrar(self.laura)
        html = self.texto(self.client.get(self.url("comando_cancelar", pendiente.pk)))
        self.assertIn("<html", html)
        self.assertIn('data-ventana', html)
        self.assertIn("Cancelar comando", html)
        self.assertIn("Emitir comando", html)

    def test_confirmar_cancela_audita_y_vuelve_de_donde_vino(self):
        pendiente = self.pendiente()
        self.entrar(self.laura)
        for volver, destino in (("comandos", self.url("comandos", invernadero=self.norte)), ("monitoreo", self.url("monitoreo", invernadero=self.norte))):
            Comando.objects.filter(pk=pendiente.pk).update(estado_comando="pendiente", resuelto_en=None)
            respuesta = self.client.post(self.url("comando_cancelar", pendiente.pk), {"volver": volver})
            self.assertRedirects(respuesta, destino, fetch_redirect_response=False)
        ficha = fabricas.comando(self.actuador, self.apagar)
        respuesta = self.client.post(self.url("comando_cancelar", ficha.pk), {"volver": "ficha"})
        self.assertIn(f"/iot/hardware/{self.actuador.pk}/", respuesta["Location"])
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado_comando, "cancelado")
        self.assertGreaterEqual(RegistroAuditoria.objects.filter(accion="cancelacion_comando").count(), 2)

    def test_un_volver_desconocido_va_a_la_lista(self):
        pendiente = self.pendiente()
        self.entrar(self.laura)
        respuesta = self.client.post(self.url("comando_cancelar", pendiente.pk), {"volver": "https://otro.sitio"})
        self.assertRedirects(respuesta, self.url("comandos", invernadero=self.norte), fetch_redirect_response=False)

    def test_dentro_de_la_espera_la_ventana_dice_cuanto_falta_y_no_ofrece_confirmar(self):
        pendiente = self.pendiente(cantidad_intentos=1, ultimo_intento_en=timezone.now() - timedelta(seconds=20))
        self.entrar(self.laura)
        html = self.texto(self.client.get(self.url("comando_cancelar", pendiente.pk), **HX))
        self.assertIn("El nodo puede estar ejecutándolo: podés cancelarlo en", html)
        self.assertNotIn("Cancelar comando", html)

    def test_regla_5_si_el_nodo_lo_retiro_entre_la_pantalla_y_la_confirmacion_el_servicio_lo_informa(self):
        pendiente = self.pendiente()
        self.entrar(self.laura)
        Comando.objects.filter(pk=pendiente.pk).update(cantidad_intentos=1, ultimo_intento_en=timezone.now())
        html = self.texto(self.client.post(self.url("comando_cancelar", pendiente.pk), {"volver": "comandos"}, **HX))
        self.assertIn("El nodo acaba de retirar el comando: no se canceló.", html)
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado_comando, "pendiente")

    def test_un_comando_ya_resuelto_lo_dice(self):
        resuelto = fabricas.comando(self.actuador, self.encender, estado="ejecutado")
        self.entrar(self.laura)
        html = self.texto(self.client.get(self.url("comando_cancelar", resuelto.pk), **HX))
        self.assertIn("ya no está pendiente", html)

    def test_permisos_y_alcance_de_la_ventana(self):
        pendiente = self.pendiente()
        for cuenta in (crear_capataz(), crear_tecnico("otro@infoponia.com")):
            self.entrar(cuenta)
            self.assertEqual(self.client.get(self.url("comando_cancelar", pendiente.pk)).status_code, 403)
        otro = crear_agronomo("ajeno@infoponia.com")
        crear_invernadero("Sur", agronomo=otro)
        self.entrar(otro)
        self.assertEqual(self.client.get(self.url("comando_cancelar", pendiente.pk)).status_code, 404)
        self.assertEqual(self.client.post(self.url("comando_cancelar", pendiente.pk)).status_code, 404)
        self.entrar(self.laura)
        self.assertEqual(self.client.get(self.url("comando_cancelar", 99999)).status_code, 404)

    def test_el_gerente_con_agronomo_activo_ve_la_ventana_sin_confirmar_y_su_post_no_cancela(self):
        """Ningún botón lo lleva ahí, pero escrita a mano la ventana no ofrece confirmar y el servicio rechaza (regla 1)."""
        pendiente = self.pendiente()
        self.entrar(self.gerente)
        html = self.texto(self.client.get(self.url("comando_cancelar", pendiente.pk), **HX))
        self.assertNotIn("Cancelar comando", html)
        self.assertIn("lo opera su Agrónomo", html)
        html = self.texto(self.client.post(self.url("comando_cancelar", pendiente.pk), **HX))
        self.assertIn("Ya no operás el IoT de este invernadero", html)
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado_comando, "pendiente")


class ComandosEnLaFichaYElPanelVistaTests(ComandosVistasBase):
    """Lo que IOT-05 suma a la ficha del actuador (Hardware) y al panel de monitoreo."""

    def ficha(self, cuenta=None, actuador=None):
        self.entrar(cuenta or self.laura)
        return self.texto(self.client.get(self.url("hardware_ficha", (actuador or self.actuador).pk)))

    def panel(self, cuenta=None):
        self.entrar(cuenta or self.laura)
        return self.texto(self.client.get(self.url("monitoreo", invernadero=self.norte)))

    def test_la_ficha_ofrece_emitir_comando_a_quien_opera_y_apunta_al_actuador(self):
        html = self.ficha()
        self.assertIn("Emitir comando", html)
        self.assertIn(self.url("comandos", invernadero=self.norte, actuador=self.actuador.pk).replace("&", "&"), html)

    def test_la_ficha_de_un_sensor_no_trae_comandos(self):
        sensor = fabricas.sensor(self.sistema, "norte/temp")
        html = self.ficha(actuador=sensor)
        self.assertNotIn("Emitir comando", html)
        self.assertNotIn("Últimos comandos", html)

    def test_quien_solo_consulta_ve_el_historial_pero_ningun_boton(self):
        self.pendiente()
        html = self.ficha(self.gerente)
        self.assertIn("Últimos comandos del actuador", html)
        self.assertNotIn("Emitir comando", html)
        self.assertEqual(self.botones(html, "Cancelar"), 0)

    def test_no_se_ofrece_emitir_si_el_actuador_o_el_sistema_no_estan_activos(self):
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_hardware="fuera_de_servicio")
        self.assertNotIn("Emitir comando", self.ficha())
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_hardware="activo")
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        self.assertNotIn("Emitir comando", self.ficha())

    def test_el_historial_de_la_ficha_trae_los_ultimos_10_y_ver_todos_filtrado(self):
        for _ in range(12):
            fabricas.comando(self.actuador, self.encender, estado="ejecutado")
        html = self.ficha()
        self.assertEqual(len(re.findall(r'<span class="id">CMD-', html)), 10)
        self.assertIn("Ver todos (12)", html)
        self.assertIn(f"filtro_actuador={self.actuador.pk}", html)

    def test_la_ficha_con_un_pendiente_muestra_la_situacion_y_cancelar(self):
        pendiente = self.pendiente()
        html = self.ficha()
        self.assertIn("Comando pendiente", html)
        self.assertIn(self.url("comando_cancelar", pendiente.pk, volver="ficha"), html)
        self.assertIn('id="ventana-confirmar"', html)

    def test_el_panel_cuenta_los_comandos_pendientes_y_marca_la_situacion(self):
        self.pendiente()
        html = self.panel()
        self.assertIn("Comandos pendientes", html)
        self.assertRegex(html, r'Comandos pendientes</div><div class="v">1<')
        self.assertIn("Comando pendiente", html)

    def test_el_panel_no_resta_de_los_operativos_a_un_actuador_que_espera_un_comando(self):
        """El indicador «Actuadores operativos» cuenta la situación sin el comando pendiente."""
        self.pendiente()
        self.assertRegex(self.panel(), r"Actuadores operativos</div><div class=\"v\">1<small> de 1<")

    def test_el_panel_ofrece_emitir_o_cancelar_a_quien_opera_y_nada_a_quien_solo_consulta(self):
        html = self.panel()
        self.assertIn("Emitir comando", html)
        pendiente = self.pendiente()
        html = self.panel()
        self.assertIn(self.url("comando_cancelar", pendiente.pk, volver="monitoreo"), html)
        self.assertNotIn(">Emitir comando<", html)
        consulta = self.panel(self.gerente)
        self.assertNotIn("Emitir comando", consulta)
        self.assertNotIn("Cancelar", consulta)

    def test_el_panel_con_el_comando_en_curso_muestra_cancelar_deshabilitado(self):
        Comando.objects.filter(pk=self.pendiente().pk).update(cantidad_intentos=1, ultimo_intento_en=timezone.now())
        html = self.panel()
        self.assertIn("El nodo puede estar ejecutándolo: podés cancelarlo en", html)
        self.assertIn('id="ventana-confirmar"', html)


class ReglasEnEmitirComandoVistaTests(ComandosVistasBase):
    """IOT-EMT-CMD paso 4 y 6b (IOT-06): las reglas de actuación activas del actuador elegido, en el formulario y como advertencia del resumen."""

    def setUp(self):
        super().setUp()
        self.sensor = fabricas.sensor(self.sistema, "norte/temp")

    def test_paso_4_el_formulario_muestra_las_reglas_activas_del_actuador_elegido(self):
        """Paso 4: al elegir el actuador, el formulario lista sus reglas activas (código con enlace a la ficha y la frase); sin reglas no muestra el recuadro."""
        regla = fabricas.regla(self.sensor, self.actuador, self.encender)
        self.entrar(self.laura)
        con = self.client.get(self.url("comandos", invernadero=self.norte, actuador=self.actuador.pk))
        self.assertContains(con, "Este actuador tiene 1 regla de actuación activa")
        self.assertContains(con, f"RGL-{regla.pk}")
        self.assertContains(con, "Cuando Temperatura norte/temp supera el máximo del umbral efectivo, Extractor norte/extractor: Encender")
        self.assertContains(con, self.url("regla_ficha", regla.pk))
        sin = self.client.get(self.url("comandos", invernadero=self.norte))
        self.assertNotContains(sin, "regla de actuación activa")

    def test_paso_4_las_reglas_dadas_de_baja_no_se_muestran(self):
        """Paso 4: solo las reglas activas."""
        fabricas.regla(self.sensor, self.actuador, self.encender, estado_regla="inactiva")
        self.entrar(self.laura)
        self.assertNotContains(self.client.get(self.url("comandos", invernadero=self.norte, actuador=self.actuador.pk)), "regla de actuación activa")

    def test_ext_6b_el_resumen_advierte_que_el_comando_puede_contradecir_las_reglas(self):
        """Extensión 6b: con reglas activas, el resumen advierte (en azul) y deja continuar."""
        fabricas.regla(self.sensor, self.actuador, self.encender)
        respuesta = self.paso("resumen")
        self.assertContains(respuesta, "El actuador tiene 1 regla(s) activa(s): este comando puede contradecirlas.")
        self.assertContains(respuesta, "Confirmar y emitir")
