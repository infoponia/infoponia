# Pruebas de las pantallas de las reglas de actuación (IOT-06, paso 5; docs/casos_de_uso/iot/reglas_de_actuacion.md, «Cómo se aplica» y «Pantallas»; D-29, D-30): la pestaña «Reglas de actuación»
# (lista con filtros y situación, ficha con su historial), el formulario con la frase de vista previa (IOT-ALT-RGL e IOT-MOD-RGL), la ventana de baja (IOT-BAJ-RGL) y «Reactivar». Integración
# con el cliente de prueba de Django: permisos y alcance (otros roles 403, fuera del alcance 404, el Gerente con Agrónomo activo en solo lectura, ningún botón lleva a un 403) y el flujo con
# HTMX y sin él. Las reglas de negocio las prueban ``test_iot_alt_rgl.py``, ``test_iot_mod_rgl.py``, ``test_iot_baj_rgl.py`` y ``test_iot_cns_rgl.py``.

from django.test import TestCase
from django.urls import reverse

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz
from iot.models import Comando, ReglaActuacion
from iot.tests import fabricas
from iot.servicios import reglas as api_reglas
from iot.tests.escena_de_reglas import AHORA, ConEscenaDeReglas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_tecnico, crear_vendedor

HX = {"HTTP_HX_REQUEST": "true"}


class ReglasVistasBase(ConEscenaDeReglas, TestCase):
    """La escena de ``escena_de_reglas.py`` (Laura, Agrónoma de Norte, con sensores y actuadores) más «Libre», un invernadero sin Agrónomo que opera el Gerente."""

    def setUp(self):
        super().setUp()
        self.libre = crear_invernadero("Libre")
        self.sistema_libre = fabricas.sistema(self.libre)
        self.temp_libre = fabricas.sensor(self.sistema_libre, "libre/temp", "temperatura")
        self.ventilador_libre = fabricas.actuador(self.sistema_libre, self.tipo_ventilador, "libre/ventilador")

    def url(self, nombre, *args, invernadero=None, **consulta):
        ruta = reverse(f"iot:{nombre}", args=args)
        if invernadero is not None:
            consulta = {"invernadero": invernadero.pk} | consulta
        return ruta + ("?" + "&".join(f"{k}={v}" for k, v in consulta.items()) if consulta else "")

    def post_de_regla(self, **cambios):
        """Lo que manda el formulario de una regla nueva: «temperatura supera el máximo → Ventilador: Encender»."""
        datos = {"sensor": self.temp.pk, "condicion": "supera_maximo", "actuador": self.ventilador.pk, "accion": self.encender.pk, "valor": ""}
        return datos | cambios


class AccesoAReglasVistaTests(ReglasVistasBase):
    """SEG-13 y D-30: quién llega a cada pantalla."""

    def rutas(self):
        regla = self.alta()
        return [
            self.url("reglas"),
            self.url("regla_nueva"),
            self.url("regla_ficha", regla.pk),
            self.url("regla_modificar", regla.pk),
            self.url("regla_baja", regla.pk),
            self.url("regla_reactivar", regla.pk),
        ]

    def test_pre_a_los_demas_roles_reciben_403_con_get_y_con_post(self):
        """IOT-CNS-RGL precondición a: Capataz, Vendedor, Técnico y Administrador, 403 en cada ruta."""
        rutas = self.rutas()
        for cuenta in (crear_capataz(), crear_vendedor(), crear_tecnico("otro@infoponia.com"), crear_administrador()):
            self.client.force_login(cuenta)
            for ruta in rutas:
                for metodo in (self.client.get, self.client.post):
                    with self.subTest(cuenta=cuenta.email, ruta=ruta, metodo=metodo.__name__):
                        self.assertEqual(metodo(ruta).status_code, 403)

    def test_regla_1_una_regla_o_un_invernadero_fuera_del_alcance_da_404(self):
        """IOT-CNS-RGL regla 1 (D-28): el Agrónomo de otro invernadero no ve la lista, la ficha ni los formularios de una regla ajena."""
        regla = self.alta()
        self.client.force_login(crear_agronomo("otra@infoponia.com"))
        self.assertEqual(self.client.get(self.url("reglas", invernadero=self.norte)).status_code, 404)
        for nombre in ("regla_ficha", "regla_modificar", "regla_baja"):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.get(self.url(nombre, regla.pk)).status_code, 404)
        self.assertEqual(self.client.post(self.url("regla_reactivar", regla.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url("regla_ficha", 999999)).status_code, 404)

    def test_la_lista_y_la_ficha_solo_aceptan_get(self):
        """SEG-14: consultar no cambia nada."""
        regla = self.alta()
        self.client.force_login(self.laura)
        self.assertEqual(self.client.post(self.url("reglas")).status_code, 405)
        self.assertEqual(self.client.post(self.url("regla_ficha", regla.pk)).status_code, 405)
        self.assertEqual(self.client.get(self.url("regla_reactivar", regla.pk)).status_code, 405)

    def test_regla_5_el_gerente_con_agronomo_activo_solo_consulta_y_no_ve_botones(self):
        """IOT-CNS-RGL regla 5 y D-30: el Gerente ve la lista y la ficha de Norte (tiene Agrónomo activo) sin «Nueva regla», «Modificar» ni «Dar de baja»; escrito a mano, vuelve con un aviso."""
        regla = self.alta()
        self.client.force_login(self.gerente)
        lista = self.client.get(self.url("reglas", invernadero=self.norte))
        self.assertContains(lista, f"RGL-{regla.pk}")
        for texto in ("Nueva regla", "Modificar", "Dar de baja", "Reactivar"):
            with self.subTest(texto=texto):
                self.assertNotContains(lista, texto)
        ficha = self.client.get(self.url("regla_ficha", regla.pk))
        self.assertEqual(ficha.status_code, 200)
        self.assertNotContains(ficha, "Dar de baja")
        self.assertNotContains(ficha, self.url("regla_modificar", regla.pk))
        for ruta, metodo in ((self.url("regla_nueva", invernadero=self.norte), self.client.get), (self.url("regla_modificar", regla.pk), self.client.get), (self.url("regla_baja", regla.pk), self.client.get)):
            with self.subTest(ruta=ruta):
                respuesta = metodo(ruta)
                self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.client.post(self.url("regla_baja", regla.pk)).status_code, 302)
        self.assertEqual(self.client.post(self.url("regla_reactivar", regla.pk)).status_code, 302)
        regla.refresh_from_db()
        self.assertEqual(regla.estado_regla, "activa")

    def test_regla_5_el_gerente_opera_el_invernadero_sin_agronomo(self):
        """IOT-CNS-RGL regla 5: en Libre (sin Agrónomo) el Gerente ve «Nueva regla» y puede crear una."""
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(self.url("reglas", invernadero=self.libre)), "Nueva regla")
        datos = self.post_de_regla(sensor=self.temp_libre.pk, actuador=self.ventilador_libre.pk, accion=self.encender.pk)
        self.assertEqual(self.client.post(self.url("regla_nueva", invernadero=self.libre), datos).status_code, 302)
        self.assertEqual(ReglaActuacion.objects.filter(sensor=self.temp_libre).count(), 1)


class IotCnsRglVistaTests(ReglasVistasBase):
    """IOT-CNS-RGL: la lista, sus filtros y la ficha."""

    def test_flujo_principal_la_lista_muestra_el_codigo_el_texto_y_la_situacion(self):
        """Reglas 2 y 3: cada regla con su código, su frase y su situación («Sin evaluar»); sin umbral efectivo dice por qué no se evalúa."""
        regla = self.alta()
        self.client.force_login(self.laura)
        pagina = self.client.get(self.url("reglas", invernadero=self.norte))
        self.assertContains(pagina, f"RGL-{regla.pk}")
        self.assertContains(pagina, "Cuando Temperatura norte/temp supera el máximo del umbral efectivo")
        self.assertContains(pagina, "Sin evaluar")
        self.assertContains(pagina, "No se evalúa: sin umbral efectivo")
        self.assertContains(pagina, "Nueva regla")
        self.assertContains(pagina, self.url("regla_modificar", regla.pk))

    def test_regla_3_los_filtros_por_estado_sensor_y_actuador(self):
        """Regla 3: filtra por estado, por sensor y por actuador; con HTMX responde solo la tabla."""
        activa = self.alta()
        baja = self.alta(sensor=self.hum, condicion="baja_del_minimo")
        self.client.force_login(self.laura)
        api_reglas.baja_regla(self.laura, baja.pk, AHORA)
        base = self.url("reglas", invernadero=self.norte)
        todo = self.client.get(base)
        self.assertContains(todo, f"RGL-{activa.pk}")
        self.assertContains(todo, f"RGL-{baja.pk}")
        solo_activas = self.client.get(base + "&estado=activa")
        self.assertContains(solo_activas, f"RGL-{activa.pk}")
        self.assertNotContains(solo_activas, f"RGL-{baja.pk}")
        solo_bajas = self.client.get(base + "&estado=inactiva")
        self.assertContains(solo_bajas, "Dada de baja")
        self.assertContains(solo_bajas, "Reactivar")
        por_sensor = self.client.get(base + f"&sensor={self.hum.pk}")
        self.assertContains(por_sensor, f"RGL-{baja.pk}")
        self.assertNotContains(por_sensor, f"RGL-{activa.pk}")
        por_actuador = self.client.get(base + f"&actuador={self.ventana.pk}")
        self.assertContains(por_actuador, "Ninguna regla coincide con los filtros.")
        fragmento = self.client.get(base + "&estado=activa", **HX)
        self.assertNotContains(fragmento, "<html")
        self.assertContains(fragmento, f"RGL-{activa.pk}")

    def test_regla_2_la_situacion_muestra_cada_motivo_de_no_emite(self):
        """Regla 2: el actuador fuera de servicio y la acción incompatible se ven en la fila."""
        regla = self.alta()
        self.ventilador.estado_hardware = "fuera_de_servicio"
        self.ventilador.save(update_fields=["estado_hardware"])
        self.ventilador.acciones_incompatibles.add(self.encender)
        self.client.force_login(self.laura)
        pagina = self.client.get(self.url("reglas", invernadero=self.norte))
        self.assertContains(pagina, "No emite: actuador fuera de servicio")
        self.assertContains(pagina, "No emite: acción incompatible con el nodo")
        self.assertContains(pagina, f"RGL-{regla.pk}")

    def test_regla_4_la_ficha_muestra_el_historial_de_comandos_de_la_regla(self):
        """Regla 4: la ficha lista los comandos que generó la regla (y no los manuales)."""
        regla = self.alta()
        generado = fabricas.comando(self.ventilador, self.encender, estado="ejecutado", regla=regla)
        manual = fabricas.comando(self.ventilador, self.apagar, estado="ejecutado")
        self.client.force_login(self.laura)
        ficha = self.client.get(self.url("regla_ficha", regla.pk))
        self.assertContains(ficha, f"CMD-{generado.pk}")
        self.assertNotContains(ficha, f"CMD-{manual.pk}")
        self.assertContains(ficha, "Comandos que generó")

    def test_regla_4_la_ficha_sin_comandos_lo_dice(self):
        """Regla 4: una regla que todavía no disparó muestra «todavía no generó comandos»."""
        regla = self.alta()
        self.client.force_login(self.laura)
        self.assertContains(self.client.get(self.url("regla_ficha", regla.pk)), "Esta regla todavía no generó comandos.")

    def test_sin_sistema_iot_la_lista_lo_avisa_y_no_ofrece_crear(self):
        """Un invernadero sin sistema IoT no tiene reglas: la pantalla lo dice y no ofrece «Nueva regla»."""
        sin = crear_invernadero("Sin sistema", agronomo=self.laura)
        self.client.force_login(self.laura)
        pagina = self.client.get(self.url("reglas", invernadero=sin))
        self.assertContains(pagina, "Este invernadero no tiene Sistema IoT")
        self.assertNotContains(pagina, "Nueva regla")
        self.assertRedirects(self.client.get(self.url("regla_nueva", invernadero=sin)), self.url("sistema", invernadero=sin), fetch_redirect_response=False)


class IotAltRglVistaTests(ReglasVistasBase):
    """IOT-ALT-RGL: el formulario de una regla nueva."""

    def test_flujo_principal_crea_la_regla_y_vuelve_a_la_lista(self):
        """Postcondiciones a y b: el POST crea la regla activa «sin evaluar», audita y vuelve a la lista con el aviso."""
        self.client.force_login(self.laura)
        respuesta = self.client.post(self.url("regla_nueva", invernadero=self.norte), self.post_de_regla(), follow=True)
        regla = ReglaActuacion.objects.get()
        self.assertEqual((regla.estado_regla, regla.ultima_evaluacion, regla.contador_confirmacion), ("activa", "sin_evaluar", 0))
        self.assertRedirects(respuesta, self.url("reglas", invernadero=self.norte))
        self.assertContains(respuesta, f"RGL-{regla.pk} creada")
        self.assertContains(respuesta, "Este invernadero no tiene umbral efectivo")  # regla 7: advierte y deja continuar
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA_REGLA_ACTUACION).count(), 1)

    def test_el_formulario_ofrece_solo_sensores_que_admiten_reglas_y_actuadores_activos(self):
        """Reglas 2 y 5: el sensor de nivel de la solución no se ofrece; la advertencia de la regla 7 se ve antes de guardar."""
        self.client.force_login(self.laura)
        pagina = self.client.get(self.url("regla_nueva", invernadero=self.norte))
        self.assertContains(pagina, "norte/temp")
        self.assertContains(pagina, "norte/hum")
        self.assertNotContains(pagina, "norte/nivel")
        self.assertContains(pagina, "norte/ventilador")
        self.assertContains(pagina, "Este invernadero no tiene umbral efectivo")
        self.assertContains(pagina, "Primero elegí el actuador")

    def test_regla_4_elegir_el_actuador_ofrece_sus_acciones_y_la_vista_previa(self):
        """Pasos de ``r-act`` y ``r-acc``: «refrescar» vuelve a dibujar SIN guardar, con las acciones del actuador y la frase de la regla."""
        self.client.force_login(self.laura)
        ruta = self.url("regla_nueva", invernadero=self.norte)
        elegido = self.client.post(ruta, self.post_de_regla(accion="") | {"refrescar": "1"}, **HX)
        self.assertContains(elegido, "Encender")
        self.assertContains(elegido, "Apagar")
        self.assertNotContains(elegido, "Vista previa")
        completo = self.client.post(ruta, self.post_de_regla() | {"refrescar": "1"}, **HX)
        self.assertContains(completo, "Vista previa")
        self.assertContains(completo, "Cuando Temperatura norte/temp supera el máximo del umbral efectivo, Ventilador norte/ventilador: Encender")
        self.assertFalse(ReglaActuacion.objects.exists())

    def test_regla_4_una_accion_con_valor_pide_el_valor_y_lo_incluye_en_la_frase(self):
        """Regla 4: «Fijar posición» (Ventana) pide un valor entre su mínimo y su máximo; la frase lo incluye en su unidad."""
        self.client.force_login(self.laura)
        ruta = self.url("regla_nueva", invernadero=self.norte)
        datos = self.post_de_regla(actuador=self.ventana.pk, accion=self.fijar.pk, valor="40") | {"refrescar": "1"}
        pagina = self.client.post(ruta, datos, **HX)
        self.assertContains(pagina, "Valor (%)")
        self.assertContains(pagina, "Número entero entre 0 y 100 %.")
        self.assertContains(pagina, "Ventana norte/ventana: Fijar posición 40 %")

    def test_cambiar_el_actuador_limpia_la_accion_elegida(self):
        """Al cambiar de actuador la acción elegida ya no es de su tipo: se limpia (como ``r-act`` del prototipo)."""
        self.client.force_login(self.laura)
        ruta = self.url("regla_nueva", invernadero=self.norte)
        pagina = self.client.post(ruta, self.post_de_regla(actuador=self.ventana.pk, accion=self.encender.pk) | {"refrescar": "1"}, **HX)
        self.assertNotContains(pagina, "Vista previa")

    def test_errores_por_campo_sin_guardar_ni_perder_lo_escrito(self):
        """Los errores del servicio salen debajo de cada campo y el formulario conserva lo escrito."""
        self.client.force_login(self.laura)
        respuesta = self.client.post(self.url("regla_nueva", invernadero=self.norte), self.post_de_regla(sensor="", condicion="", accion=""))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Seleccioná un sensor.")
        self.assertContains(respuesta, "Seleccioná la condición.")
        self.assertContains(respuesta, "Seleccioná la acción.")
        self.assertFalse(ReglaActuacion.objects.exists())

    def test_regla_6_una_regla_igual_a_una_activa_se_rechaza_con_su_texto(self):
        """Regla 6: «Ya hay una regla activa igual: …», como error general, sin 500."""
        self.alta()
        self.client.force_login(self.laura)
        respuesta = self.client.post(self.url("regla_nueva", invernadero=self.norte), self.post_de_regla())
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ya hay una regla activa igual: Cuando Temperatura norte/temp supera el máximo")
        self.assertEqual(ReglaActuacion.objects.count(), 1)

    def test_regla_9_con_el_sistema_desconectado_se_crea_igual_y_lo_avisa(self):
        """Regla 9: una regla de un sistema desconectado se crea igual; el formulario avisa que empieza a evaluarse al activarlo."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        self.client.force_login(self.laura)
        ruta = self.url("regla_nueva", invernadero=self.norte)
        self.assertContains(self.client.get(ruta), "El sistema IoT está desconectado")
        self.assertEqual(self.client.post(ruta, self.post_de_regla()).status_code, 302)
        self.assertEqual(ReglaActuacion.objects.count(), 1)

    def test_sin_javascript_el_formulario_es_una_pagina_completa_con_su_boton_de_actualizar(self):
        """Respaldo sin JavaScript: la página completa trae el botón «Actualizar la frase» y el título."""
        self.client.force_login(self.laura)
        pagina = self.client.get(self.url("regla_nueva", invernadero=self.norte))
        self.assertContains(pagina, "<html")
        self.assertContains(pagina, "Actualizar la frase")
        self.assertContains(pagina, "Nueva regla de actuación")


class IotModRglVistaTests(ReglasVistasBase):
    """IOT-MOD-RGL: modificar y reactivar."""

    def test_regla_3_el_formulario_muestra_deshabilitados_el_sensor_y_el_actuador(self):
        """Regla 3: el sensor y el actuador no se cambian: se ven deshabilitados con el texto del prototipo."""
        regla = self.alta()
        self.client.force_login(self.laura)
        pagina = self.client.get(self.url("regla_modificar", regla.pk))
        self.assertContains(pagina, "El sensor y el actuador no se cambian: para otros, se crea una regla nueva.")
        self.assertContains(pagina, "Temperatura · norte/temp")
        self.assertNotContains(pagina, 'name="sensor"')
        self.assertNotContains(pagina, 'name="actuador"')
        self.assertContains(pagina, "Guardar cambios")

    def test_regla_4_modificar_reinicia_la_evaluacion_y_audita(self):
        """Regla 4 y postcondición c: guardar un cambio vuelve a «sin evaluar» con el contador en 0, aunque el POST traiga otro sensor."""
        regla = self.alta()
        ReglaActuacion.objects.filter(pk=regla.pk).update(ultima_evaluacion="cumplida", contador_confirmacion=2)
        self.client.force_login(self.laura)
        datos = self.post_de_regla(condicion="baja_del_minimo", accion=self.apagar.pk, sensor=self.hum.pk, actuador=self.ventana.pk)
        respuesta = self.client.post(self.url("regla_modificar", regla.pk), datos, follow=True)
        regla.refresh_from_db()
        self.assertEqual((regla.condicion, regla.accion_id, regla.sensor_id, regla.actuador_id), ("baja_del_minimo", self.apagar.pk, self.temp.pk, self.ventilador.pk))
        self.assertEqual((regla.ultima_evaluacion, regla.contador_confirmacion), ("sin_evaluar", 0))
        self.assertContains(respuesta, "modificada")
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_REGLA_ACTUACION).count(), 1)

    def test_una_regla_dada_de_baja_no_se_modifica_solo_se_reactiva(self):
        """Regla 6: el formulario de una regla inactiva vuelve a su ficha con un aviso; la ficha ofrece «Reactivar» y no «Modificar»."""
        regla = self.alta()
        api_reglas.baja_regla(self.laura, regla.pk, AHORA)
        self.client.force_login(self.laura)
        self.assertRedirects(self.client.get(self.url("regla_modificar", regla.pk)), self.url("regla_ficha", regla.pk), fetch_redirect_response=False)
        ficha = self.client.get(self.url("regla_ficha", regla.pk))
        self.assertContains(ficha, "Reactivar")
        self.assertNotContains(ficha, self.url("regla_modificar", regla.pk))

    def test_regla_6_reactivar_deja_la_regla_activa_y_sin_evaluar(self):
        """Postcondición b y regla 6: «Reactivar» (un POST) vuelve la regla a «activa»."""
        regla = self.alta()
        api_reglas.baja_regla(self.laura, regla.pk, AHORA)
        self.client.force_login(self.laura)
        respuesta = self.client.post(self.url("regla_reactivar", regla.pk), follow=True)
        regla.refresh_from_db()
        self.assertEqual(regla.estado_regla, "activa")
        self.assertContains(respuesta, "reactivada")

    def test_regla_6_reactivar_con_el_sensor_dado_de_baja_explica_por_que_no(self):
        """Regla 6: con el sensor sin activar, el servicio rechaza y la pantalla muestra el motivo; la regla sigue dada de baja."""
        regla = self.alta()
        api_reglas.baja_regla(self.laura, regla.pk, AHORA)
        self.temp.estado_hardware = "inactivo"
        self.temp.save(update_fields=["estado_hardware"])
        self.client.force_login(self.laura)
        respuesta = self.client.post(self.url("regla_reactivar", regla.pk), follow=True)
        regla.refresh_from_db()
        self.assertEqual(regla.estado_regla, "inactiva")
        self.assertContains(respuesta, "El sensor de la regla no está activo")


class IotBajRglVistaTests(ReglasVistasBase):
    """IOT-BAJ-RGL: la ventana de baja."""

    def test_abrir_la_ventana_no_cambia_nada_y_con_htmx_es_un_fragmento(self):
        """Abrirla (GET) no da de baja; con HTMX es solo la ventana, sin ella es la ficha con la ventana abierta."""
        regla = self.alta()
        self.client.force_login(self.laura)
        fragmento = self.client.get(self.url("regla_baja", regla.pk), **HX)
        self.assertContains(fragmento, f"Dar de baja RGL-{regla.pk}")
        self.assertContains(fragmento, "La regla deja de evaluarse. Su historial se conserva")
        self.assertNotContains(fragmento, "<html")
        pagina = self.client.get(self.url("regla_baja", regla.pk))
        self.assertContains(pagina, "<html")
        self.assertContains(pagina, f"Dar de baja RGL-{regla.pk}")
        regla.refresh_from_db()
        self.assertEqual(regla.estado_regla, "activa")

    def test_regla_2_dar_de_baja_deja_seguir_los_comandos_pendientes_y_lo_dice(self):
        """Postcondición a y regla 2: el POST da de baja y audita; el comando pendiente de la regla sigue pendiente; la ventana lo avisa."""
        regla = self.alta()
        pendiente = fabricas.comando(self.ventilador, self.encender, regla=regla)
        self.client.force_login(self.laura)
        self.assertContains(self.client.get(self.url("regla_baja", regla.pk), **HX), f"CMD-{pendiente.pk}")
        respuesta = self.client.post(self.url("regla_baja", regla.pk), follow=True)
        regla.refresh_from_db()
        pendiente.refresh_from_db()
        self.assertEqual(regla.estado_regla, "inactiva")
        self.assertEqual(pendiente.estado_comando, Comando.Estado.PENDIENTE)
        self.assertRedirects(respuesta, self.url("reglas", invernadero=self.norte))
        self.assertContains(respuesta, "dada de baja")
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.BAJA_REGLA_ACTUACION).count(), 1)

    def test_una_regla_ya_dada_de_baja_no_ofrece_la_baja(self):
        """D-30: la ventana de una regla inactiva vuelve a su ficha con un aviso (ningún botón lleva a un error)."""
        regla = self.alta()
        api_reglas.baja_regla(self.laura, regla.pk, AHORA)
        self.client.force_login(self.laura)
        self.assertRedirects(self.client.get(self.url("regla_baja", regla.pk)), self.url("regla_ficha", regla.pk), fetch_redirect_response=False)
