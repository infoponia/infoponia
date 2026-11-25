# Pruebas de las pantallas de «Configuración» (MAE-04: ADM-MOD-CFG y ADM-MOD-ORG): permisos, errores por campo con y sin HTMX,
# todo o nada, el mensaje de guardado tras la redirección, la advertencia de la regla 5, sin logo (D-45) y la entrada del menú.

import re

from django.test import TestCase
from django.urls import reverse

from core.models import RegistroAuditoria
from core.tests.fabricas import CLAVE, crear_administrador, crear_capataz, crear_gerente
from maestros.models import PARAMETROS_DE_CONFIGURACION, ConfiguracionOperativa, PerfilOrganizacion
from maestros.tests.fabricas import ConDatosDeMaestros, crear_agronomo

HTMX = {"HTTP_HX_REQUEST": "true"}
URL = reverse("configuracion:pantalla")
URL_ORGANIZACION_PANTALLA = URL + "?pestana=organizacion"
URL_PARAMETROS = reverse("configuracion:guardar_parametros")
URL_ORGANIZACION = reverse("configuracion:guardar_organizacion")
CAMPOS_DEL_PERFIL = (
    "nombre_organizacion", "cuit_organizacion", "telefono_organizacion", "email_organizacion", "direccion_organizacion",
    "color_primario", "color_secundario", "color_terciario", "color_cuaternario",
)


def parametros(**cambios):
    """Los 14 parámetros guardados como se envía el formulario (texto), con ``cambios`` encima."""
    fila = ConfiguracionOperativa.objects.get()
    return {c: str(getattr(fila, c)) for c, *_ in PARAMETROS_DE_CONFIGURACION} | {k: str(v) for k, v in cambios.items()}


def organizacion(**cambios):
    """El perfil guardado como se envía el formulario, con ``cambios`` encima."""
    fila = PerfilOrganizacion.objects.get()
    return {c: getattr(fila, c) for c in CAMPOS_DEL_PERFIL} | cambios


def auditorias():
    """Los registros de modificación de configuración y de perfil."""
    return RegistroAuditoria.objects.filter(accion__in=["modificacion_configuracion", "modificacion_perfil"])


class ConfiguracionVistasTests(ConDatosDeMaestros, TestCase):
    """Las vistas de «Configuración»."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.login(username=self.gerente.email, password=CLAVE)

    # ---- permisos ----

    def test_pre_a_solo_el_gerente_entra_a_las_tres_vistas(self):
        """ADM-MOD-CFG y ADM-MOD-ORG precondición a: Agrónomo, Capataz y Administrador reciben 403 en la pantalla y en cada
        guardado; sin sesión, van al inicio de sesión. Un POST sin permiso no cambia nada."""
        cuentas = {"agronomo": crear_agronomo(), "capataz": crear_capataz(), "administrador": crear_administrador()}
        for nombre, cuenta in cuentas.items():
            self.client.logout()
            self.client.login(username=cuenta.email, password=CLAVE)
            for url, metodo in ((URL, "get"), (URL_PARAMETROS, "post"), (URL_ORGANIZACION, "post")):
                with self.subTest(rol=nombre, url=url):
                    self.assertEqual(getattr(self.client, metodo)(url).status_code, 403)
        self.client.logout()
        for url, metodo in ((URL, "get"), (URL_PARAMETROS, "post"), (URL_ORGANIZACION, "post")):
            with self.subTest(rol="sin sesión", url=url):
                respuesta = getattr(self.client, metodo)(url)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn(reverse("core:iniciar_sesion"), respuesta["Location"])
        self.assertEqual(auditorias().count(), 0)

    def test_los_guardados_solo_aceptan_post(self):
        """Un GET a un guardado da 405: ninguna pantalla modifica con un enlace."""
        self.assertEqual(self.client.get(URL_PARAMETROS).status_code, 405)
        self.assertEqual(self.client.get(URL_ORGANIZACION).status_code, 405)

    # ---- la entrada del menú ----

    def test_regla_1_la_entrada_del_menu_es_solo_del_gerente(self):
        """D-30 y D-25: «Configuración» está en el menú del Gerente (activa en su pantalla, al final) y no en el del Agrónomo
        ni en el del Administrador."""
        menu = self.client.get(URL).context["menu"]
        entrada = [e for e in menu if e["texto"] == "Configuración"]
        self.assertEqual([(e["url"], e["activo"]) for e in entrada], [(URL, True)])
        self.assertEqual(menu[-1]["texto"], "Configuración")
        self.assertFalse(any(e["texto"] == "Producción" and e["activo"] for e in menu))
        for cuenta, destino in ((crear_agronomo(), "core:inicio"), (crear_administrador(), "core:usuarios")):
            self.client.logout()
            self.client.login(username=cuenta.email, password=CLAVE)
            textos = [e["texto"] for e in self.client.get(reverse(destino)).context["menu"]]
            self.assertNotIn("Configuración", textos)

    # ---- lectura ----

    def test_flujo_principal_muestra_los_quince_parametros_y_ninguno_del_logo(self):
        """Regla 1 y 2 de ADM-MOD-CFG: la pantalla tiene los 15 parámetros (COM-04b suma el aviso de cámara y CMP-07, el margen del pedido automático) con sus
        valores actuales, el de faltante dentro de «Comercial», y la lectura no audita (SEG-14)."""
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.status_code, 200)
        form = respuesta.context["form"]
        self.assertEqual(len(form.fields), 15)
        self.assertEqual([t for t, _ in form.grupos], ["Producción", "Insumos", "Comercial", "Compras", "Entregas"])
        comercial = dict(form.grupos)["Comercial"]
        self.assertIn("dias_vigencia_enlace_faltante", [c.name for c, _ in comercial])
        self.assertContains(respuesta, "Vigencia del enlace de decisión ante un faltante")
        self.assertIn("dias_aviso_vencimiento_camara", [c.name for c, _ in comercial])  # COM-04b, MD-134
        self.assertContains(respuesta, "Aviso de vencimiento de cámara")
        self.assertContains(respuesta, "0 desactiva el aviso")
        self.assertContains(respuesta, 'name="porc_merma_maxima"')
        self.assertContains(respuesta, 'value="15"')
        self.assertNotRegex(respuesta.content.decode(), r'name="[^"]*logo')  # «logo» es también la clase del marco
        self.assertEqual(auditorias().count(), 0)

    def test_d104_el_margen_del_pedido_automatico_esta_en_compras_y_se_guarda_desde_la_pantalla(self):
        """CMP-07 (D-104 punto 3): «Compras» muestra el margen con su ayuda y su valor inicial (20); guardar otro valor lo cambia y lo audita con su antes y después."""
        respuesta = self.client.get(URL)
        compras = dict(respuesta.context["form"].grupos)["Compras"]
        self.assertIn("porc_margen_pedido_automatico", [c.name for c, _ in compras])
        self.assertContains(respuesta, "Margen del pedido automático")
        self.assertContains(respuesta, "Con 0 pide justo lo que falta")
        self.assertEqual(respuesta.context["form"]["porc_margen_pedido_automatico"].value(), 20)
        self.client.post(URL_PARAMETROS, parametros(porc_margen_pedido_automatico="35"))
        self.assertEqual(ConfiguracionOperativa.objects.get().porc_margen_pedido_automatico, 35)
        registro = RegistroAuditoria.objects.get(accion="modificacion_configuracion")
        self.assertEqual(registro.detalle["cambios"], {"porc_margen_pedido_automatico": {"antes": 20, "despues": 35}})

    def test_d104_un_margen_fuera_de_0_a_100_marca_su_campo_y_no_guarda(self):
        """CMP-07 (D-104 punto 3): 101 da el error en el campo del margen y no se guarda nada (todo o nada, regla 6)."""
        respuesta = self.client.post(URL_PARAMETROS, parametros(porc_margen_pedido_automatico="101", porc_merma_maxima="20"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("porc_margen_pedido_automatico", respuesta.context["form"].errors)
        fila = ConfiguracionOperativa.objects.get()
        self.assertEqual((fila.porc_margen_pedido_automatico, fila.porc_merma_maxima), (20, 15))
        self.assertEqual(auditorias().count(), 0)

    def test_flujo_principal_la_pestana_organizacion_no_tiene_logo(self):
        """ADM-MOD-ORG regla 1 y D-45: se muestran los datos actuales y cuatro colores, sin campo de archivo ni de logo."""
        respuesta = self.client.get(URL_ORGANIZACION_PANTALLA)
        self.assertEqual(respuesta.status_code, 200)
        for nombre in CAMPOS_DEL_PERFIL:
            self.assertContains(respuesta, f'name="{nombre}"')
        self.assertNotContains(respuesta, 'type="file"')
        self.assertNotRegex(respuesta.content.decode(), r'name="[^"]*logo')  # «logo» es también la clase del marco
        self.assertEqual(auditorias().count(), 0)

    # ---- guardar: parámetros ----

    def test_regla_6_errores_por_campo_y_todo_o_nada_sin_javascript(self):
        """ADM-MOD-CFG regla 3 y 6: con dos valores inválidos y uno válido, cada error sale en su campo (la página entera) y
        no se guarda ninguno, ni el válido."""
        respuesta = self.client.post(
            URL_PARAMETROS, parametros(porc_merma_maxima="0", dias_limite_cotizacion="", dias_aviso_vencimiento="20")
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(set(respuesta.context["form"].errors), {"porc_merma_maxima", "dias_limite_cotizacion"})
        self.assertContains(respuesta, "El mínimo es 1.")
        self.assertContains(respuesta, "Ingresá un valor.")
        self.assertContains(respuesta, "<title>")  # la página completa
        fila = ConfiguracionOperativa.objects.get()
        self.assertEqual((fila.porc_merma_maxima, fila.dias_aviso_vencimiento), (15, 15))
        self.assertEqual(auditorias().count(), 0)

    def test_regla_6_con_htmx_vuelve_solo_el_formulario_con_los_errores(self):
        """Con HTMX el servidor responde el fragmento del formulario (sin la página entera), con los errores por campo."""
        respuesta = self.client.post(URL_PARAMETROS, parametros(porc_merma_maxima="101"), **HTMX)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'id="form-parametros"')
        self.assertContains(respuesta, "El máximo es 100.")
        self.assertNotContains(respuesta, "<title>")
        self.assertEqual(ConfiguracionOperativa.objects.get().porc_merma_maxima, 15)

    def test_regla_4_la_anticipacion_mayor_que_la_pre_reserva_marca_su_campo(self):
        """ADM-MOD-CFG regla 4: el error sale en el campo de la anticipación de cosecha del suministro."""
        respuesta = self.client.post(
            URL_PARAMETROS, parametros(dias_pre_reserva_suministro="5", dias_anticipacion_cosecha_suministro="6")
        )
        self.assertEqual(set(respuesta.context["form"].errors), {"dias_anticipacion_cosecha_suministro"})
        self.assertContains(respuesta, "No puede superar la pre-reserva de suministros.")

    def test_regla_5_la_advertencia_del_horizonte_se_muestra_y_deja_guardar(self):
        """ADM-MOD-CFG regla 5: horizonte 10 con pre-reserva 14 guarda y la pantalla advierte junto al formulario."""
        respuesta = self.client.post(URL_PARAMETROS, parametros(dias_horizonte_cosecha="10"), follow=True)
        self.assertEqual(ConfiguracionOperativa.objects.get().dias_horizonte_cosecha, 10)
        self.assertContains(respuesta, "El horizonte de cosecha es menor que la pre-reserva de suministros")

    def test_regla_5_sin_horizonte_menor_no_hay_advertencia(self):
        """ADM-MOD-CFG regla 5: con los valores iniciales la pantalla no advierte."""
        self.assertNotContains(self.client.get(URL), "El horizonte de cosecha es menor")

    def test_flujo_principal_guardar_sin_javascript_redirige_y_muestra_el_mensaje(self):
        """Sin JavaScript: el POST guarda, redirige a la pantalla y ahí se ve «Se guardó la configuración.»; queda un registro
        de auditoría con el antes y el después (postcondición b)."""
        respuesta = self.client.post(URL_PARAMETROS, parametros(porc_merma_maxima="20"))
        self.assertRedirects(respuesta, URL, fetch_redirect_response=False)  # no consumir el mensaje
        pantalla = self.client.get(URL)
        self.assertContains(pantalla, "Se guardó la configuración.")
        self.assertEqual(pantalla.context["form"]["porc_merma_maxima"].value(), 20)
        registro = RegistroAuditoria.objects.get(accion="modificacion_configuracion")
        self.assertEqual(registro.detalle["cambios"], {"porc_merma_maxima": {"antes": 15, "despues": 20}})

    def test_flujo_principal_guardar_con_htmx_redirige_y_el_mensaje_llega_tras_la_recarga(self):
        """Con HTMX, guardar responde ``HX-Redirect`` a la pantalla; al recargar (el navegador hace el GET) llega el mensaje
        «Se guardó la configuración.» y el valor nuevo. El mensaje se muestra una sola vez."""
        respuesta = self.client.post(URL_PARAMETROS, parametros(porc_merma_maxima="20"), **HTMX)
        self.assertEqual(respuesta.status_code, 204)
        self.assertEqual(respuesta["HX-Redirect"], URL)
        recarga = self.client.get(respuesta["HX-Redirect"])
        self.assertContains(recarga, "Se guardó la configuración.")
        self.assertEqual(recarga.context["form"]["porc_merma_maxima"].value(), 20)
        self.assertNotContains(self.client.get(URL), "Se guardó la configuración.")

    def test_d28_guardar_sin_cambios_no_audita(self):
        """D-28: guardar sin cambiar nada no deja registro en la auditoría (y igual confirma el guardado)."""
        respuesta = self.client.post(URL_PARAMETROS, parametros(), follow=True)
        self.assertContains(respuesta, "Se guardó la configuración.")
        self.assertEqual(auditorias().count(), 0)

    def test_post_b_cambiar_dos_valores_deja_un_registro_con_el_antes_y_el_despues_de_cada_uno(self):
        """Postcondición b: dos valores cambiados, un solo registro con el antes y el después de cada uno."""
        self.client.post(URL_PARAMETROS, parametros(porc_merma_maxima="20", dias_limite_cotizacion="5"))
        (registro,) = auditorias()
        self.assertEqual(registro.detalle["cambios"], {
            "porc_merma_maxima": {"antes": 15, "despues": 20},
            "dias_limite_cotizacion": {"antes": 3, "despues": 5},
        })

    # ---- guardar: organización ----

    def test_regla_7_errores_por_campo_y_todo_o_nada_en_la_organizacion(self):
        """ADM-MOD-ORG regla 2, 3, 5 y 7: nombre vacío, CUIT inválido, email sin arroba y color mal escrito: cada error sale en
        su campo y no se guarda nada, ni la dirección válida."""
        antes = PerfilOrganizacion.objects.values().get()
        respuesta = self.client.post(URL_ORGANIZACION, organizacion(
            nombre_organizacion="", cuit_organizacion="30-71234567-2", email_organizacion="sin-arroba",
            color_primario="rojo", direccion_organizacion="Av. Uruguay 2450"))
        self.assertEqual(set(respuesta.context["form"].errors),
                         {"nombre_organizacion", "cuit_organizacion", "email_organizacion", "color_primario"})
        self.assertContains(respuesta, "Ingresá el nombre de la organización.")
        self.assertContains(respuesta, "Ingresá el color con el formato #RRGGBB.")
        self.assertEqual(PerfilOrganizacion.objects.values().get(), antes)
        self.assertEqual(auditorias().count(), 0)

    def test_regla_5_cargar_el_color_2_sin_el_1_da_error_en_el_color_2(self):
        """ADM-MOD-ORG regla 5: los colores se cargan en orden."""
        respuesta = self.client.post(URL_ORGANIZACION, organizacion(color_secundario="#112233"))
        self.assertEqual(set(respuesta.context["form"].errors), {"color_secundario"})
        self.assertContains(respuesta, "Cargá primero el color 1.")

    def test_regla_7_con_htmx_vuelve_solo_el_formulario_de_la_organizacion(self):
        """Con HTMX el servidor responde el fragmento de la pestaña con los errores, sin la página entera."""
        respuesta = self.client.post(URL_ORGANIZACION, organizacion(nombre_organizacion=""), **HTMX)
        self.assertContains(respuesta, 'id="form-organizacion"')
        self.assertNotContains(respuesta, "<title>")

    def test_flujo_principal_guardar_la_organizacion_con_htmx_muestra_el_mensaje_y_tine_el_sistema(self):
        """Guardar la organización con HTMX: ``HX-Redirect`` a la misma pestaña, el mensaje llega tras la recarga, el CUIT con
        guiones se acepta y se guarda sin ellos, y el color 1 tiñe el marco desde esa carga (D-48)."""
        respuesta = self.client.post(URL_ORGANIZACION, organizacion(
            nombre_organizacion="Vivero Los Álamos", cuit_organizacion="30-71234567-1", color_primario="#2e7d32"), **HTMX)
        self.assertEqual(respuesta.status_code, 204)
        self.assertEqual(respuesta["HX-Redirect"], URL_ORGANIZACION_PANTALLA)
        recarga = self.client.get(respuesta["HX-Redirect"])
        self.assertContains(recarga, "Se guardó la configuración.")
        self.assertContains(recarga, "--primary:#2E7D32")
        self.assertContains(recarga, "Vivero Los Álamos")
        self.assertEqual(PerfilOrganizacion.objects.get().cuit_organizacion, "30712345671")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_perfil").count(), 1)

    def test_flujo_principal_guardar_la_organizacion_sin_javascript(self):
        """Sin JavaScript el POST redirige a la pestaña «Organización» y ahí se ve el aviso."""
        respuesta = self.client.post(URL_ORGANIZACION, organizacion(email_organizacion="contacto@vivero.com.ar"))
        self.assertRedirects(respuesta, URL_ORGANIZACION_PANTALLA, fetch_redirect_response=False)
        self.assertContains(self.client.get(URL_ORGANIZACION_PANTALLA), "Se guardó la configuración.")

    def test_las_muestras_de_color_solo_usan_colores_validos(self):
        """Seguridad: lo escrito en un color nunca llega a un ``style`` si no es ``#RRGGBB`` (no hay inyección de CSS)."""
        respuesta = self.client.post(URL_ORGANIZACION, organizacion(color_primario="red;background:url(x)"))
        estilos = " ".join(re.findall(r'style="([^"]*)"', respuesta.content.decode()))
        self.assertNotIn("url(", estilos)
        self.assertNotIn("red", estilos)
