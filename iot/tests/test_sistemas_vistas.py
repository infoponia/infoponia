# Pruebas de las pantallas del Sistema IoT (IOT-02, paso 6; docs/casos_de_uso/iot/sistema_iot.md, «Cómo se aplica» y «Pantallas»; D-29, D-30, D-70). Integración con el cliente de
# prueba de Django: permisos y alcance (otros roles 403, un invernadero fuera del alcance 404, el Gerente con Agrónomo activo en solo lectura, ningún botón lleva a un 403), el
# flujo de registrar en tres pantallas, el token que se ve una sola vez (con ``no-store``), modificar, regenerar, y el flujo con HTMX y sin él. Las reglas de negocio las prueban
# ``test_iot_reg_sis.py`` y ``test_iot_mod_sis.py``.

import re
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.enlaces import resumen_de
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from iot.models import NodoCentral, SistemaIoT
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_tecnico, crear_vendedor


class SistemaVistasBase(fabricas.ConCatalogoIot, TestCase):
    """Cuentas e invernaderos de las pruebas: Laura es la Agrónoma de Norte; Libre no tiene Agrónomo (lo opera el Gerente)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.tecnico = crear_tecnico("tecnico@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=self.tecnico)
        self.libre = crear_invernadero("Libre")
        self.insumo = fabricas.insumo_de_hardware("Raspberry Pi 4")

    def url(self, nombre, *args, invernadero=None):
        ruta = reverse(f"iot:{nombre}", args=args)
        return f"{ruta}?invernadero={invernadero.pk}" if invernadero else ruta

    def post_del_registro(self, invernadero=None, **cambios):
        """Lo que manda el formulario de registrar."""
        datos = {
            "invernadero": (invernadero or self.norte).pk,
            "nombre": "Raspberry del galpón",
            "modelo": "Raspberry Pi 4",
            "numero_serie": "",
            "fecha_instalacion": (timezone.localdate() - timedelta(days=1)).isoformat(),
            "insumo": self.insumo.pk,
            "temp_min": "",
            "temp_max": "",
        }
        return datos | cambios


class AccesoASistemaVistaTests(SistemaVistasBase):
    """SEG-13 y D-30: quién llega a cada pantalla."""

    def rutas(self):
        sistema = fabricas.sistema(self.norte)
        return [
            self.url("sistema"),
            self.url("sistema_registrar"),
            self.url("sistema_modificar", sistema.pk),
            self.url("sistema_regenerar_token", sistema.pk),
        ]

    def test_pre_a_los_demas_roles_reciben_403_con_get_y_con_post(self):
        """IOT-REG-SIS e IOT-MOD-SIS precondición a: Capataz, Vendedor, Técnico y Administrador, 403 en cada ruta."""
        rutas = self.rutas()
        for cuenta in (crear_capataz(), crear_vendedor(), crear_tecnico("otro@infoponia.com"), crear_administrador()):
            self.client.force_login(cuenta)
            for ruta in rutas:
                for metodo in (self.client.get, self.client.post):
                    with self.subTest(cuenta=cuenta.email, ruta=ruta, metodo=metodo.__name__):
                        self.assertEqual(metodo(ruta).status_code, 403)

    def test_pre_a_sin_sesion_se_va_al_inicio_de_sesion(self):
        """D-25: toda pantalla exige sesión."""
        for ruta in self.rutas():
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta["Location"].startswith(reverse(settings.LOGIN_URL)))

    def test_un_invernadero_fuera_del_alcance_da_404(self):
        """«Para los cinco», «Elección del invernadero»: con un invernadero fuera del alcance, 404."""
        otra = crear_agronomo("otra@infoponia.com")
        ajeno = crear_invernadero("Ajeno", agronomo=otra)
        sistema_ajeno = fabricas.sistema(ajeno)
        self.client.force_login(self.laura)
        self.assertEqual(self.client.get(self.url("sistema", invernadero=ajeno)).status_code, 404)
        self.assertEqual(self.client.get(self.url("sistema_modificar", sistema_ajeno.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url("sistema_regenerar_token", sistema_ajeno.pk)).status_code, 404)
        self.assertEqual(self.client.post(self.url("sistema_regenerar_token", sistema_ajeno.pk)).status_code, 404)

    def test_un_sistema_dado_de_baja_no_se_modifica_y_da_404(self):
        """IOT-MOD-SIS regla 6 y «Cómo se aplica»: «404 desde la URL; sin botón»."""
        baja = fabricas.sistema(self.norte, "inactivo")
        self.client.force_login(self.laura)
        for nombre in ("sistema_modificar", "sistema_regenerar_token"):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.get(self.url(nombre, baja.pk)).status_code, 404)

    def test_inicio_lleva_a_la_pestana_monitoreo(self):
        """«Ruta y pestaña» de IOT-CNS-LEC (IOT-04): ``/iot/`` redirige a «Monitoreo» (IOT-02 la llevaba a «Sistema IoT»)."""
        self.client.force_login(self.laura)
        self.assertRedirects(self.client.get(reverse("iot:inicio")), reverse("iot:monitoreo"), fetch_redirect_response=False)

    def test_las_pantallas_de_lectura_solo_aceptan_get(self):
        """SEG-14: la consulta no cambia nada: un POST a la ficha es un 405."""
        self.client.force_login(self.laura)
        self.assertEqual(self.client.post(self.url("sistema")).status_code, 405)


class IotCnsSistemaVistaTests(SistemaVistasBase):
    """La pestaña «Sistema IoT»: la ficha del nodo, el vacío, la barra de contexto y los botones."""

    def test_flujo_principal_sin_sistema_el_agronomo_ve_el_vacio_con_el_enlace_para_registrar(self):
        """IOT-REG-SIS paso 1 y «Verificación a mano» 1: «Este invernadero no tiene Sistema IoT» y «Registrar sistema IoT»."""
        self.client.force_login(self.laura)
        respuesta = self.client.get(self.url("sistema"))
        self.assertContains(respuesta, "Norte no tiene Sistema IoT")
        self.assertContains(respuesta, "Registrar sistema IoT")
        self.assertContains(respuesta, self.url("sistema_registrar", invernadero=self.norte).replace("&", "&amp;"))

    def test_sin_insumo_de_hardware_no_ofrece_registrar_y_lo_explica(self):
        """IOT-REG-SIS precondición c y «Cómo se aplica»: «Primero registrá en Compras e Inventario el insumo del nodo…», con el enlace al alta de insumo."""
        self.insumo.delete()
        self.client.force_login(self.laura)
        respuesta = self.client.get(self.url("sistema"))
        self.assertContains(respuesta, "Primero registrá en Compras e Inventario el insumo del nodo, en la categoría «Repuestos de hardware».")
        self.assertNotContains(respuesta, "Registrar sistema IoT")
        self.assertContains(respuesta, reverse("inventario:insumo_nuevo"))

    def test_el_gerente_con_agronomo_activo_ve_el_aviso_y_ningun_boton_de_escritura(self):
        """«Para los cinco» (``opBanner``): el Gerente consulta, pero lo opera solo si no hay Agrónomo activo; en solo lectura, sin botones ni enlaces que lleven a un 403."""
        fabricas.sistema(self.norte)
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.url("sistema", invernadero=self.norte))
        self.assertContains(respuesta, "Norte tiene Agrónomo activo")
        self.assertNotContains(respuesta, "Modificar")
        self.assertNotContains(respuesta, "Regenerar token")
        self.assertNotContains(respuesta, "Registrar sistema IoT")

    def test_el_gerente_sin_agronomo_activo_opera_y_lo_ve_en_el_aviso(self):
        """IOT-REG-SIS regla «Alcance»: sin Agrónomo activo el Gerente opera: «Operás este invernadero como Gerente…» y ve «Registrar sistema IoT»."""
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.url("sistema", invernadero=self.libre))
        self.assertContains(respuesta, "Operás este invernadero como Gerente porque no tiene Agrónomo activo.")
        self.assertContains(respuesta, "Registrar sistema IoT")

    def test_la_ficha_muestra_el_nodo_la_conectividad_y_los_botones_de_quien_opera(self):
        """IOT-CNS-HDW regla 2 y IOT-MOD-SIS: estado, conectividad «sin señal» («Todavía no se comunicó»), modo, rango, API, guía y los botones Modificar y Regenerar token."""
        sistema = fabricas.sistema(self.norte, temp_solucion_min="18.0", temp_solucion_max="24.0", token_generado_en=timezone.now())
        self.client.force_login(self.laura)
        respuesta = self.client.get(self.url("sistema"))
        self.assertContains(respuesta, "Nodo de prueba")
        self.assertContains(respuesta, "Sin señal")
        self.assertContains(respuesta, "Todavía no se comunicó")
        self.assertContains(respuesta, "Remoto")
        self.assertContains(respuesta, "18,0 a 24,0 °C")
        self.assertContains(respuesta, "/api/iot/v1/")
        self.assertContains(respuesta, "https://github.com/infoponia/infoponia/blob/main/docs/api/nodo/README.md")
        self.assertContains(respuesta, self.url("sistema_modificar", sistema.pk))
        self.assertContains(respuesta, self.url("sistema_regenerar_token", sistema.pk))
        self.assertNotContains(respuesta, sistema.token_resumen or "sin-resumen")

    def test_la_ficha_muestra_en_linea_si_el_nodo_se_comunico_hace_poco(self):
        """«Para los cinco», «Conectividad»: «En línea» si la última comunicación es más reciente que el plazo. Se busca la insignia: desde
        UI-02 (UX-21) el pie de toda pantalla también dice «En línea», y el texto suelto pasaría aunque la ficha dijera «Sin señal»."""
        sistema = fabricas.sistema(self.norte)
        NodoCentral.objects.filter(sistema=sistema).update(ultima_comunicacion=timezone.now() - timedelta(minutes=1))
        self.client.force_login(self.laura)
        respuesta = self.client.get(self.url("sistema"))
        self.assertContains(respuesta, '<span class="status-badge status-ok">En línea</span>')
        self.assertNotContains(respuesta, "Sin señal")

    def test_la_barra_de_contexto_recuerda_el_invernadero_elegido_en_la_sesion(self):
        """«Para los cinco», «Elección del invernadero»: ``?invernadero=`` y la sesión ``iot_invernadero``; sin ninguno, el primero por nombre."""
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(self.url("sistema")), "Libre no tiene Sistema IoT")  # el primero por nombre
        self.client.get(self.url("sistema", invernadero=self.norte))
        self.assertContains(self.client.get(self.url("sistema")), "Norte no tiene Sistema IoT")  # el recordado
        self.assertEqual(self.client.session["iot_invernadero"], self.norte.pk)

    def test_las_pestanas_llevan_a_hardware_y_a_tipos(self):
        """D-25: las pestañas «Hardware», «Sistema IoT» y «Tipos de actuador» son enlaces."""
        self.client.force_login(self.laura)
        respuesta = self.client.get(self.url("sistema"))
        for nombre in ("hardware", "sistema", "tipos"):
            self.assertContains(respuesta, f'href="{reverse("iot:" + nombre)}')

    def test_ningun_enlace_de_la_ficha_lleva_a_un_403(self):
        """D-30: cada enlace de la pestaña, para cada actor que la ve, se puede abrir (nunca 403)."""
        fabricas.sistema(self.norte)
        for cuenta in (self.laura, self.gerente):
            self.client.force_login(cuenta)
            html = self.client.get(self.url("sistema", invernadero=self.norte)).content.decode()
            for ruta in set(re.findall(r'href="(/iot/[^"#]*)"', html)):
                with self.subTest(cuenta=cuenta.email, ruta=ruta):
                    self.assertNotEqual(self.client.get(ruta.replace("&amp;", "&")).status_code, 403)


class IotRegSisVistaTests(SistemaVistasBase):
    """IOT-REG-SIS en tres pantallas: elegir el invernadero, datos y resumen, y confirmación con el token."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.laura)
        self.registrar = reverse("iot:sistema_registrar")

    def test_paso_2_elige_el_invernadero_entre_los_que_opera_con_su_tecnico(self):
        """IOT-REG-SIS paso 2: la lista de invernaderos que puede registrar, cada uno con su Técnico o «Sin Técnico»."""
        sin_tecnico = crear_invernadero("Sin tecnico", agronomo=self.laura)
        respuesta = self.client.get(self.registrar)
        self.assertContains(respuesta, "Norte")
        self.assertContains(respuesta, "Técnico: ")
        self.assertContains(respuesta, "Sin Técnico")
        self.assertContains(respuesta, f"?invernadero={sin_tecnico.pk}")
        self.assertNotContains(respuesta, "Libre")

    def test_paso_2_el_gerente_ve_solo_los_invernaderos_sin_agronomo_activo(self):
        """IOT-REG-SIS extensión 1a."""
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.registrar)
        self.assertContains(respuesta, "Libre")
        self.assertNotContains(respuesta, ">Norte<")

    def test_paso_2_un_invernadero_que_ya_tiene_sistema_vuelve_a_la_eleccion_con_un_aviso(self):
        """IOT-REG-SIS extensión 8a: un invernadero con sistema no se ofrece; ir directo por la URL vuelve al paso 2 con un aviso."""
        fabricas.sistema(self.norte)
        respuesta = self.client.get(f"{self.registrar}?invernadero={self.norte.pk}", follow=True)
        self.assertRedirects(respuesta, self.registrar)
        self.assertContains(respuesta, "ya tiene un sistema IoT")

    def test_paso_5_el_formulario_pide_los_datos_del_nodo(self):
        """IOT-REG-SIS paso 5: nombre, modelo, serie, fecha de instalación, insumo y el rango de la solución."""
        respuesta = self.client.get(f"{self.registrar}?invernadero={self.norte.pk}")
        for texto in ("Nombre", "Modelo", "Número de serie", "Fecha de instalación", "Insumo", "Mínimo (°C)", "Máximo (°C)", "Revisar", "Raspberry Pi 4"):
            self.assertContains(respuesta, texto)

    def test_ext_6a_los_errores_salen_por_campo_y_conservan_lo_escrito(self):
        """IOT-REG-SIS extensión 6a (y «Verificación a mano» 2): un rango de un solo valor es un error del rango y el formulario conserva lo escrito."""
        respuesta = self.client.post(self.registrar, self.post_del_registro(revisar="1", temp_min="18") | {"nombre": "Mi nodo"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Completá mínimo y máximo, o dejá los dos vacíos.")
        self.assertContains(respuesta, 'value="Mi nodo"')
        self.assertFalse(SistemaIoT.objects.exists())

    def test_paso_6_revisar_muestra_el_resumen_sin_registrar(self):
        """IOT-REG-SIS paso 6: el resumen con el invernadero, el nodo y el aviso del token; no escribe nada."""
        respuesta = self.client.post(self.registrar, self.post_del_registro(revisar="1", temp_min="18", temp_max="24"))
        self.assertContains(respuesta, "Revisá el registro")
        self.assertContains(respuesta, "Raspberry del galpón")
        self.assertContains(respuesta, "18,0 a 24,0 °C")
        self.assertContains(respuesta, "una sola vez")
        self.assertContains(respuesta, "Registrar y generar token")
        self.assertFalse(SistemaIoT.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion="alta_sistema_iot").exists())

    def test_ext_6b_el_resumen_avisa_de_la_alerta_del_tecnico_si_no_hay_tecnico_activo(self):
        """IOT-REG-SIS extensión 6b: el texto completo del aviso."""
        sin = crear_invernadero("Sin tecnico", agronomo=self.laura)
        respuesta = self.client.post(self.registrar, self.post_del_registro(sin, revisar="1"))
        self.assertContains(respuesta, "Se generará para el Gerente la alerta «invernadero sin Técnico activo». Nadie podrá concretar los mantenimientos del hardware hasta que se asigne uno.")
        self.assertNotContains(self.client.post(self.registrar, self.post_del_registro(revisar="1")), "Nadie podrá concretar")

    def test_ext_7a_cambiar_datos_vuelve_al_formulario_con_lo_escrito(self):
        """IOT-REG-SIS extensión 7a: «Cambiar datos» vuelve al paso 5 sin perder lo escrito ni registrar."""
        respuesta = self.client.post(self.registrar, self.post_del_registro(editar="1", nombre="Otro nodo"))
        self.assertContains(respuesta, 'value="Otro nodo"')
        self.assertContains(respuesta, "Revisar")
        self.assertFalse(SistemaIoT.objects.exists())

    def test_flujo_principal_confirmar_registra_y_muestra_el_token_una_sola_vez(self):
        """IOT-REG-SIS pasos 8 a 10 y «Verificación a mano» 2: la respuesta al POST RENDERIZA el token (sin redirigir), con la dirección de la API, la guía y «Ya guardé el token»."""
        respuesta = self.client.post(self.registrar, self.post_del_registro(confirmar="1"))
        self.assertEqual(respuesta.status_code, 200)
        sistema = SistemaIoT.objects.get()
        self.assertContains(respuesta, "Sistema IoT registrado")
        self.assertContains(respuesta, "/api/iot/v1/")
        self.assertContains(respuesta, "Ya guardé el token")
        self.assertContains(respuesta, "docs/api/nodo/README.md")
        token = re.search(r'id="valor-del-token">([^<]+)<', respuesta.content.decode()).group(1)
        self.assertEqual(sistema.token_resumen, resumen_de(token))
        self.assertContains(respuesta, "Registrar hardware")

    def test_el_token_se_ve_con_no_store_y_no_se_vuelve_a_mostrar(self):
        """D-70 y «Mostrar el token una sola vez»: ``Cache-Control: no-store``; un GET posterior (recargar la ficha) no tiene el token ni el resumen."""
        respuesta = self.client.post(self.registrar, self.post_del_registro(confirmar="1"))
        self.assertIn("no-store", respuesta["Cache-Control"])
        token = re.search(r'id="valor-del-token">([^<]+)<', respuesta.content.decode()).group(1)
        sistema = SistemaIoT.objects.get()
        despues = self.client.get(self.url("sistema", invernadero=self.norte))
        self.assertNotContains(despues, token)
        self.assertNotContains(despues, sistema.token_resumen)
        self.assertEqual(self.client.get(self.registrar + f"?invernadero={self.norte.pk}", follow=True).status_code, 200)

    def test_el_token_no_queda_en_la_sesion_ni_en_los_mensajes(self):
        """D-70: el token no se guarda en ningún lado para mostrarlo después: ni en la sesión ni en los avisos."""
        respuesta = self.client.post(self.registrar, self.post_del_registro(confirmar="1"))
        token = re.search(r'id="valor-del-token">([^<]+)<', respuesta.content.decode()).group(1)
        self.assertNotIn(token, str(dict(self.client.session)))
        self.assertNotIn(token, " ".join(str(m) for m in respuesta.context["messages"]))

    def test_ext_8a_si_otro_actor_lo_registro_antes_vuelve_al_paso_2_con_el_motivo(self):
        """IOT-REG-SIS extensión 8a: al confirmar, el invernadero ya tiene un sistema: no se registra nada, se informa y vuelve al paso 2."""
        fabricas.sistema(self.norte)
        respuesta = self.client.post(self.registrar, self.post_del_registro(confirmar="1"), follow=True)
        self.assertRedirects(respuesta, self.registrar)
        self.assertContains(respuesta, "ya tiene un sistema IoT")
        self.assertEqual(SistemaIoT.objects.count(), 1)

    def test_ext_8b_si_el_agronomo_dejo_de_tenerlo_a_cargo_vuelve_al_paso_2_con_el_motivo(self):
        """IOT-REG-SIS extensión 8b: «Ya no operás el IoT de este invernadero: …»."""
        datos = self.post_del_registro(confirmar="1")
        self.norte.agronomo = crear_agronomo("nueva@infoponia.com")
        self.norte.save()
        respuesta = self.client.post(self.registrar, datos, follow=True)
        self.assertRedirects(respuesta, self.registrar, fetch_redirect_response=False)
        self.assertFalse(SistemaIoT.objects.exists())

    def test_post_e_registrar_sin_tecnico_activo_crea_la_alerta_para_el_gerente(self):
        """IOT-REG-SIS postcondición e y «Verificación a mano» 3: aparece «Invernadero sin Técnico activo» para el Gerente."""
        sin = crear_invernadero("Sin tecnico", agronomo=self.laura)
        self.client.post(self.registrar, self.post_del_registro(sin, confirmar="1"))
        self.assertTrue(Alerta.objects.filter(tipo_alerta="sin_tecnico", invernadero=sin, estado_alerta="activa", para_gerente=True).exists())

    def test_post_e_la_ficha_del_invernadero_y_la_lista_muestran_el_estado_del_iot(self):
        """«Verificación a mano» 1 y 3: antes, «Sin registrar» con el enlace; después, «Activo» en la ficha y «Con IoT» en la lista (los registrantes reales de `iot`)."""
        ficha = reverse("maestros:invernadero", args=[self.norte.pk])
        self.assertContains(self.client.get(ficha), "Sin registrar")
        self.assertContains(self.client.get(ficha), "Registrar sistema IoT")
        self.client.post(self.registrar, self.post_del_registro(confirmar="1"))
        self.assertContains(self.client.get(ficha), ">Activo</a>")
        self.assertContains(self.client.get(reverse("maestros:invernaderos")), "Con IoT")

    def test_sin_javascript_cada_paso_es_una_pagina_completa(self):
        """«Verificación a mano» 9: sin JavaScript (sin ``HX-Request``) cada pantalla es una página completa."""
        for respuesta in (
            self.client.get(self.registrar),
            self.client.get(f"{self.registrar}?invernadero={self.norte.pk}"),
            self.client.post(self.registrar, self.post_del_registro(revisar="1")),
            self.client.post(self.registrar, self.post_del_registro(confirmar="1")),
        ):
            self.assertContains(respuesta, "<html")


class IotModSisVistaTests(SistemaVistasBase):
    """IOT-MOD-SIS: modificar el nodo y regenerar el token."""

    def setUp(self):
        super().setUp()
        self.sistema = fabricas.sistema(self.norte, token_resumen=resumen_de("token-original"), token_generado_en=timezone.now())
        self.client.force_login(self.laura)

    def test_el_formulario_de_modificar_trae_los_datos_actuales_sin_fecha_ni_insumo(self):
        """IOT-MOD-SIS reglas 2 y 7: nombre, modelo, serie y rango; no pide fecha ni insumo; ofrece regenerar el token."""
        respuesta = self.client.get(self.url("sistema_modificar", self.sistema.pk))
        self.assertContains(respuesta, 'value="Nodo de prueba"')
        self.assertContains(respuesta, "Guardar cambios")
        self.assertNotContains(respuesta, "Fecha de instalación")
        self.assertNotContains(respuesta, 'name="insumo"')
        self.assertContains(respuesta, "Regenerar token")

    def test_modificar_guarda_avisa_y_vuelve_a_la_ficha(self):
        """IOT-MOD-SIS regla 2: guarda, avisa con un aviso breve (D-29) y vuelve a la ficha."""
        respuesta = self.client.post(
            self.url("sistema_modificar", self.sistema.pk), {"nombre": "Nodo nuevo", "modelo": "Pi 5", "numero_serie": "SN-1", "temp_min": "18", "temp_max": "24"}, follow=True
        )
        self.assertRedirects(respuesta, self.url("sistema", invernadero=self.norte))
        self.assertContains(respuesta, "Sistema IoT modificado correctamente.")
        self.assertEqual(NodoCentral.objects.get(sistema=self.sistema).nombre_nodo, "Nodo nuevo")

    def test_modificar_con_errores_los_muestra_por_campo(self):
        """IOT-MOD-SIS regla 2: errores por campo, con lo escrito."""
        respuesta = self.client.post(self.url("sistema_modificar", self.sistema.pk), {"nombre": "", "modelo": "Pi", "temp_min": "30", "temp_max": "20"})
        self.assertContains(respuesta, "Ingresá el nombre del nodo.")
        self.assertContains(respuesta, "El mínimo tiene que ser menor que el máximo.")
        self.assertContains(respuesta, 'value="Pi"')

    def test_el_gerente_con_agronomo_activo_no_modifica_y_vuelve_a_la_ficha_sin_403(self):
        """D-30: aunque llegue por la URL, solo consulta: vuelve a la ficha con un aviso (nunca un 403 ni un cambio)."""
        self.client.force_login(self.gerente)
        for metodo in (self.client.get, self.client.post):
            respuesta = metodo(self.url("sistema_modificar", self.sistema.pk), {"nombre": "X", "modelo": "Y"}, follow=True)
            self.assertContains(respuesta, "Solo consultás este sistema IoT")
        self.assertEqual(NodoCentral.objects.get(sistema=self.sistema).nombre_nodo, "Nodo de prueba")

    def test_la_ventana_de_regenerar_advierte_y_no_cambia_nada(self):
        """IOT-MOD-SIS regla 3: abrir la ventana (GET) advierte que el token actual deja de funcionar y que la conectividad pasa a «sin señal»; no cambia el token."""
        respuesta = self.client.get(self.url("sistema_regenerar_token", self.sistema.pk))
        self.assertContains(respuesta, "deja de funcionar de inmediato")
        self.assertContains(respuesta, "sin señal")
        self.sistema.refresh_from_db()
        self.assertEqual(self.sistema.token_resumen, resumen_de("token-original"))

    def test_con_htmx_la_ventana_de_regenerar_es_un_fragmento_y_sin_htmx_la_ficha_con_la_ventana(self):
        """D-29 y docs/patrones/abm.md, sección 7: con HTMX, solo la ventana; sin JavaScript, la ficha entera con la ventana abierta."""
        con = self.client.get(self.url("sistema_regenerar_token", self.sistema.pk), headers={"HX-Request": "true"})
        self.assertNotContains(con, "<html")
        self.assertContains(con, "Regenerar token")
        sin = self.client.get(self.url("sistema_regenerar_token", self.sistema.pk))
        self.assertContains(sin, "<html")
        self.assertContains(sin, "Nodo de prueba")

    def test_regenerar_muestra_el_token_nuevo_una_sola_vez_sin_cache(self):
        """IOT-MOD-SIS postcondición b y «Verificación a mano» 4: el token nuevo se muestra una sola vez (``no-store``), el anterior deja de servir y recargar no lo vuelve a mostrar."""
        respuesta = self.client.post(self.url("sistema_regenerar_token", self.sistema.pk))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("no-store", respuesta["Cache-Control"])
        self.assertContains(respuesta, "Nuevo token del nodo")
        self.assertContains(respuesta, "El token anterior dejó de funcionar")
        token = re.search(r'id="valor-del-token">([^<]+)<', respuesta.content.decode()).group(1)
        self.sistema.refresh_from_db()
        self.assertEqual(self.sistema.token_resumen, resumen_de(token))
        self.assertNotContains(self.client.get(self.url("sistema", invernadero=self.norte)), token)
        self.assertNotContains(self.client.get(self.url("sistema_regenerar_token", self.sistema.pk)), token)

    def test_regenerar_no_deja_el_token_en_la_auditoria_ni_en_los_avisos(self):
        """D-70 y «Verificación a mano» 4: en «Auditoría» queda ``regeneracion_token_iot`` sin el token."""
        respuesta = self.client.post(self.url("sistema_regenerar_token", self.sistema.pk))
        token = re.search(r'id="valor-del-token">([^<]+)<', respuesta.content.decode()).group(1)
        registro = RegistroAuditoria.objects.get(accion="regeneracion_token_iot")
        self.assertNotIn(token, str(registro.detalle) + str(registro.afectados))

    def test_el_gerente_con_agronomo_activo_no_regenera(self):
        """D-30: solo consulta: el token no cambia."""
        self.client.force_login(self.gerente)
        self.client.post(self.url("sistema_regenerar_token", self.sistema.pk), follow=True)
        self.sistema.refresh_from_db()
        self.assertEqual(self.sistema.token_resumen, resumen_de("token-original"))


class IotCicloSisVistaTests(SistemaVistasBase):
    """IOT-DSC-SIS, IOT-ACT-SIS e IOT-BAJ-SIS (IOT-06, paso 5): las ventanas de desconectar y de dar de baja, el botón «Activar» y sus permisos. Las reglas de negocio las prueban
    ``test_iot_dsc_sis.py``, ``test_iot_act_sis.py`` y ``test_iot_baj_sis.py``."""

    def setUp(self):
        super().setUp()
        self.enterContext(fabricas.con_iot_registrado())
        self.sistema = fabricas.sistema(self.norte)
        self.sensor = fabricas.sensor(self.sistema, "norte/temp")
        self.actuador = fabricas.actuador(self.sistema, fabricas.tipo_actuador("Extractor"), "norte/ventilador")
        self.client.force_login(self.laura)

    def estado(self):
        return SistemaIoT.objects.get(pk=self.sistema.pk).estado_sistema

    def test_pre_a_los_demas_roles_reciben_403(self):
        """Precondición a de DSC, ACT y BAJ: Capataz, Vendedor, Técnico y Administrador, 403 (con GET y con POST)."""
        rutas = [self.url(n, self.sistema.pk) for n in ("sistema_desactivar", "sistema_activar", "sistema_baja")]
        for cuenta in (crear_capataz(), crear_vendedor(), crear_tecnico("otro@infoponia.com"), crear_administrador()):
            self.client.force_login(cuenta)
            for ruta in rutas:
                for metodo in (self.client.get, self.client.post):
                    with self.subTest(cuenta=cuenta.email, ruta=ruta, metodo=metodo.__name__):
                        self.assertEqual(metodo(ruta).status_code, 403)

    def test_regla_1_un_sistema_fuera_del_alcance_da_404(self):
        """Regla 1 de DSC (D-28): el Agrónomo de otro invernadero recibe 404 en las tres ventanas."""
        self.client.force_login(crear_agronomo("otra@infoponia.com"))
        for nombre in ("sistema_desactivar", "sistema_activar", "sistema_baja"):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.post(self.url(nombre, self.sistema.pk)).status_code, 404)
        self.assertEqual(self.estado(), "activo")

    def test_la_ficha_ofrece_desconectar_y_dar_de_baja_con_el_sistema_activo(self):
        """D-30: con el sistema activo, la ficha ofrece «Desconectar» y «Dar de baja», no «Activar»."""
        pagina = self.client.get(self.url("sistema", invernadero=self.norte))
        self.assertContains(pagina, "Desconectar")
        self.assertContains(pagina, "Dar de baja")
        self.assertNotContains(pagina, "Activando…")

    def test_la_ficha_ofrece_activar_con_el_sistema_desconectado(self):
        """D-30: desconectado, la ficha ofrece «Activar» y no «Desconectar»."""
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(estado_sistema="desconectado")
        pagina = self.client.get(self.url("sistema", invernadero=self.norte))
        self.assertContains(pagina, "Activando…")
        self.assertNotContains(pagina, self.url("sistema_desactivar", self.sistema.pk))

    def test_el_gerente_con_agronomo_activo_no_ve_botones_y_escribir_a_mano_no_cambia_nada(self):
        """D-30 y regla 1: solo consulta; los POST vuelven a la ficha con un aviso (nunca un 403) y el sistema queda como estaba."""
        self.client.force_login(self.gerente)
        pagina = self.client.get(self.url("sistema", invernadero=self.norte))
        for texto in ("Desconectar", "Dar de baja", "Activando…"):
            with self.subTest(texto=texto):
                self.assertNotContains(pagina, texto)
        for nombre in ("sistema_desactivar", "sistema_activar", "sistema_baja"):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.post(self.url(nombre, self.sistema.pk)).status_code, 302)
        self.assertEqual(self.estado(), "activo")

    def test_post_b_desconectar_abre_la_ventana_sin_cambiar_y_el_post_desconecta_cancelando_los_pendientes(self):
        """IOT-DSC-SIS postcondiciones a y b: abrir la ventana (GET) no cambia nada; el POST desconecta y cancela el comando pendiente."""
        pendiente = fabricas.comando(self.actuador, self.actuador.tipo_actuador.acciones.first())
        ventana = self.client.get(self.url("sistema_desactivar", self.sistema.pk), headers={"HX-Request": "true"})
        self.assertContains(ventana, "Desconectar el sistema")
        self.assertContains(ventana, "Los comandos pendientes se cancelan")
        self.assertNotContains(ventana, "<html")
        self.assertEqual(self.estado(), "activo")
        pagina = self.client.get(self.url("sistema_desactivar", self.sistema.pk))  # sin JavaScript: la ficha con la ventana abierta
        self.assertContains(pagina, "<html")
        self.assertContains(pagina, "Desconectar el sistema")
        respuesta = self.client.post(self.url("sistema_desactivar", self.sistema.pk), follow=True)
        self.assertRedirects(respuesta, self.url("sistema", invernadero=self.norte))
        self.assertContains(respuesta, "Sistema IoT desconectado")
        pendiente.refresh_from_db()
        self.assertEqual((self.estado(), pendiente.estado_comando), ("desconectado", "cancelado"))

    def test_post_a_activar_es_un_post_directo_y_deja_el_sistema_activo(self):
        """IOT-ACT-SIS postcondición a: «Activar» es un POST (un GET da 405) y el sistema vuelve a «activo»."""
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(estado_sistema="desconectado")
        self.assertEqual(self.client.get(self.url("sistema_activar", self.sistema.pk)).status_code, 405)
        respuesta = self.client.post(self.url("sistema_activar", self.sistema.pk), follow=True)
        self.assertContains(respuesta, "Sistema IoT activado")
        self.assertEqual(self.estado(), "activo")

    def test_regla_2_de_baj_un_sistema_dado_de_baja_no_se_activa_y_lo_avisa(self):
        """Un sistema dado de baja no se desconecta ni se activa: vuelve a la ficha con el aviso de que la baja es definitiva."""
        SistemaIoT.objects.filter(pk=self.sistema.pk).update(estado_sistema="inactivo")
        respuesta = self.client.post(self.url("sistema_activar", self.sistema.pk), follow=True)
        self.assertContains(respuesta, "la baja es definitiva")

    def test_regla_8_la_ventana_de_baja_lista_lo_que_se_da_de_baja_y_advierte(self):
        """IOT-BAJ-SIS regla 8: el nodo, cada equipo con su estado, el último estado de cada actuador y cada regla activa; y que la baja es definitiva y no habrá más comandos."""
        regla = fabricas.regla(self.sensor, self.actuador)
        ventana = self.client.get(self.url("sistema_baja", self.sistema.pk), headers={"HX-Request": "true"})
        self.assertContains(ventana, "La baja es <b>definitiva</b>")
        self.assertContains(ventana, "Nodo de prueba")
        self.assertContains(ventana, "norte/temp")
        self.assertContains(ventana, "norte/ventilador")
        self.assertContains(ventana, "último estado: desconocido")
        self.assertContains(ventana, f"RGL-{regla.pk}")
        self.assertContains(ventana, "InfoPonia no podrá enviar comandos a estos actuadores")
        self.assertContains(ventana, "Dar de baja definitivamente")
        self.assertEqual(self.estado(), "activo")

    def test_regla_4_con_comandos_pendientes_la_ventana_no_deja_confirmar_y_explica_como_resolverlo(self):
        """IOT-BAJ-SIS precondición c y regla 4: lista los comandos pendientes con cómo resolverlos y sin botón de confirmar; el POST a mano tampoco da de baja."""
        pendiente = fabricas.comando(self.actuador, self.actuador.tipo_actuador.acciones.first())
        ventana = self.client.get(self.url("sistema_baja", self.sistema.pk), headers={"HX-Request": "true"})
        self.assertContains(ventana, "No se puede dar de baja todavía")
        self.assertContains(ventana, f"CMD-{pendiente.pk}")
        self.assertContains(ventana, "desactivando el sistema")
        self.assertNotContains(ventana, "Dar de baja definitivamente")
        respuesta = self.client.post(self.url("sistema_baja", self.sistema.pk), headers={"HX-Request": "true"})
        self.assertContains(respuesta, "No se puede dar de baja todavía")
        self.assertEqual(self.estado(), "activo")

    def test_post_a_la_baja_deja_todo_inactivo_sin_token_y_vuelve_a_la_ficha(self):
        """IOT-BAJ-SIS postcondiciones a a c: el sistema, el nodo y los equipos quedan inactivos, el token se anula y la ficha pasa a «no tiene Sistema IoT»."""
        regla = fabricas.regla(self.sensor, self.actuador)
        respuesta = self.client.post(self.url("sistema_baja", self.sistema.pk), follow=True)
        self.assertRedirects(respuesta, self.url("sistema", invernadero=self.norte))
        self.assertContains(respuesta, "Sistema IoT dado de baja")
        self.assertContains(respuesta, "no tiene Sistema IoT")
        sistema = SistemaIoT.objects.get(pk=self.sistema.pk)
        regla.refresh_from_db()
        self.sensor.refresh_from_db()
        self.assertEqual((sistema.estado_sistema, sistema.token_resumen, regla.estado_regla, self.sensor.estado_hardware), ("inactivo", None, "inactiva", "inactivo"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.BAJA_SISTEMA_IOT).count(), 1)
