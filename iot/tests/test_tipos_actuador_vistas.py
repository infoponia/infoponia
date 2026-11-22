# Pruebas de las pantallas de tipos de actuador de IOT-01 (paso 4; integración con el cliente de prueba de Django): «IoT» → «Tipos de
# actuador» (IOT-CNS-TAC) y el formulario y las ventanas de alta, modificación, baja y reactivación (IOT-ALT-TAC, IOT-MOD-TAC, IOT-BAJ-TAC),
# más la entrada «IoT» del menú. Consultan el Gerente y el Agrónomo; solo el Gerente escribe. El formulario y la baja funcionan con HTMX
# (``HX-Request``: fragmento) y sin JavaScript (página completa). Clases ``<CodigoCu>VistaTests`` de .claude/rules/pruebas.md.

import re
from unittest import mock

from django.apps import apps
from django.test import TestCase
from django.urls import reverse

from core.menu import menu_de
from core.models import RegistroAuditoria, Usuario
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from iot.models import Accion, TipoActuador
from iot.servicios.tipos_actuador import UsoDeAccion
from iot.tests import fabricas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_tecnico, crear_vendedor

HX = {"HTTP_HX_REQUEST": "true"}
EN_USO = "iot.servicios.tipos_actuador.acciones_en_uso"


class TiposVistasBase(fabricas.ConCatalogoIot, TestCase):
    """Un Gerente y un Agrónomo con sesión a elección, y las rutas del módulo."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.client.force_login(self.gerente)
        self.lista = reverse("iot:tipos")
        self.url_nuevo = reverse("iot:tipo_nuevo")
        self.tipo = fabricas.tipo_actuador("Extractor", 30, [("Encender", "ENCENDER"), ("Fijar velocidad", "FIJAR_NIVEL", 0, 100, "%")])
        self.encender, self.fijar = self.tipo.acciones.order_by("id")

    def url(self, nombre, tipo=None):
        """La URL ``iot:<nombre>`` del tipo de la prueba (o de ``tipo``)."""
        return reverse(f"iot:{nombre}", args=[(tipo or self.tipo).pk])

    def post_del_tipo(self, nombre="Extractor", tiempo="30", filas=None):
        """Lo que manda el formulario: ``filas`` es una lista de diccionarios con ``id``, ``nombre``, ``comando`` y, si lleva valor,
        ``minimo``, ``maximo`` y ``unidad``."""
        datos = {"nombre": nombre, "tiempo_minimo": tiempo, "acciones_total": str(len(filas))}
        for i, fila in enumerate(filas):
            for campo, valor in fila.items():
                datos[f"accion_{i}_{campo}"] = valor
        return datos

    def post_actual(self, **cambios):
        """El formulario de ``self.tipo`` sin cambios, con ``cambios`` encima."""
        filas = [
            {"id": str(self.encender.pk), "nombre": "Encender", "comando": "ENCENDER"},
            {"id": str(self.fijar.pk), "nombre": "Fijar velocidad", "comando": "FIJAR_NIVEL", "minimo": "0", "maximo": "100", "unidad": "%"},
        ]
        datos = self.post_del_tipo(filas=filas)
        datos.update(cambios)
        return datos


class AccesoATiposVistaTests(TiposVistasBase):
    """SEG-13 y D-30: quién llega a cada pantalla del módulo."""

    def rutas(self):
        return [
            reverse("iot:inicio"),
            self.lista,
            self.url_nuevo,
            self.url("tipo_modificar"),
            self.url("tipo_baja"),
            self.url("tipo_reactivar"),
        ]

    def test_pre_a_los_demas_roles_reciben_403_en_todo_el_modulo(self):
        """IOT-CNS-TAC precondición a: Capataz, Vendedor, Técnico y Administrador, 403 en cada ruta, con GET y con POST."""
        for cuenta in (crear_capataz(), crear_vendedor(), crear_tecnico(), crear_administrador()):
            self.client.force_login(cuenta)
            for ruta in self.rutas():
                for metodo in (self.client.get, self.client.post):
                    with self.subTest(cuenta=cuenta.email, ruta=ruta, metodo=metodo.__name__):
                        self.assertEqual(metodo(ruta).status_code, 403)

    def test_pre_a_sin_sesion_se_va_al_inicio_de_sesion(self):
        """Toda pantalla exige sesión (D-25)."""
        self.client.logout()
        for ruta in self.rutas():
            with self.subTest(ruta=ruta):
                self.assertRedirects(self.client.get(ruta), f"{reverse('core:iniciar_sesion')}?next={ruta}", fetch_redirect_response=False)

    def test_regla_1_el_agronomo_ve_la_lista_y_recibe_403_en_las_urls_de_escritura(self):
        """IOT-CNS-TAC regla 3 e IOT-ALT/MOD/BAJ-TAC regla 1: el Agrónomo solo consulta."""
        self.client.force_login(self.agronomo)
        self.assertEqual(self.client.get(self.lista).status_code, 200)
        self.assertRedirects(self.client.get(reverse("iot:inicio")), self.lista, fetch_redirect_response=False)
        for ruta in (self.url_nuevo, self.url("tipo_modificar"), self.url("tipo_baja"), self.url("tipo_reactivar")):
            for metodo in (self.client.get, self.client.post):
                with self.subTest(ruta=ruta, metodo=metodo.__name__):
                    self.assertEqual(metodo(ruta).status_code, 403)
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.estado, "activo")

    def test_regla_3_la_lista_solo_acepta_get(self):
        """La consulta no escribe: un POST a la lista es 405."""
        self.assertEqual(self.client.post(self.lista).status_code, 405)

    def test_pre_a_un_tipo_que_no_existe_da_404(self):
        """docs/patrones/abm.md, sección 6."""
        for nombre in ("tipo_modificar", "tipo_baja"):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.get(reverse(f"iot:{nombre}", args=[999999])).status_code, 404)
        self.assertEqual(self.client.post(reverse("iot:tipo_reactivar", args=[999999])).status_code, 404)


class MenuIotVistaTests(TiposVistasBase):
    """La entrada «IoT» del menú (paso 4; ``IotConfig.ready()``)."""

    def test_el_gerente_y_el_agronomo_ven_iot_justo_despues_de_produccion(self):
        """«IoT» va inmediatamente después de «Producción» (como en ``MODS`` del prototipo) para el Gerente y el Agrónomo."""
        for rol in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO):
            with self.subTest(rol=rol):
                textos = [texto for texto, _, _ in menu_de(rol)]
                self.assertEqual(textos.index("IoT"), textos.index("Producción") + 1)
        self.assertIn(("IoT", "iot:inicio", "activity"), menu_de(Usuario.Rol.GERENTE))

    def test_los_demas_roles_no_ven_la_entrada(self):
        """El menú muestra solo lo que la cuenta puede abrir (D-25 y D-30)."""
        for rol in (Usuario.Rol.VENDEDOR, Usuario.Rol.CAPATAZ, Usuario.Rol.TECNICO, Usuario.Rol.TRANSPORTISTA):
            with self.subTest(rol=rol):
                self.assertNotIn("IoT", [texto for texto, _, _ in menu_de(rol)])

    def test_registrar_dos_veces_no_la_duplica(self):
        """``ready()`` puede correr más de una vez: la entrada «IoT» no se repite en el menú de ningún rol."""
        apps.get_app_config("iot").ready()
        for rol in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO):
            with self.subTest(rol=rol):
                self.assertEqual([texto for texto, _, _ in menu_de(rol)].count("IoT"), 1)

    def test_la_pagina_muestra_la_entrada_activa_en_el_menu(self):
        """La entrada «IoT» del menú lateral se marca activa dentro de las pantallas del módulo."""
        for cuenta in (self.gerente, self.agronomo):
            self.client.force_login(cuenta)
            with self.subTest(cuenta=cuenta.email):
                html = self.client.get(self.lista).content.decode()
                self.assertRegex(html, r'<a class="nav-item active" href="/iot/" aria-current="page">')


class IotCnsTacVistaTests(TiposVistasBase):
    """IOT-CNS-TAC: la lista de tipos y el catálogo."""

    def test_flujo_principal_el_gerente_ve_los_tipos_con_sus_acciones_y_botones(self):
        """IOT-CNS-TAC reglas 2 y 3: código, nombre, acciones con comando, rango y unidad, tiempo, equipos y estado; y los botones."""
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, "Nuevo tipo")
        self.assertContains(respuesta, "Ventilador")
        self.assertContains(respuesta, f"TAC-{self.tipo.pk:02d}")
        self.assertContains(respuesta, "Fijar velocidad")
        self.assertContains(respuesta, "0 a 100 %")
        self.assertContains(respuesta, "FIJAR_NIVEL")
        self.assertContains(respuesta, "30 s")
        self.assertContains(respuesta, self.url("tipo_modificar"))
        self.assertContains(respuesta, self.url("tipo_baja"))
        self.assertContains(respuesta, "Definen qué acciones admite cada clase de equipo")

    def test_regla_7_de_iot_alt_tac_el_catalogo_se_ve_debajo_en_solo_lectura(self):
        """IOT-ALT-TAC regla 7: capacidades con sus comandos y la leyenda de que no se edita."""
        respuesta = self.client.get(self.lista)
        for texto in ("Catálogo de capacidades", "no se edita", "Encendido", "Posición", "FIJAR_POSICION", "con valor"):
            self.assertContains(respuesta, texto)

    def test_regla_3_el_agronomo_ve_lista_y_catalogo_sin_botones_y_con_el_aviso(self):
        """IOT-CNS-TAC regla 3 y D-30: sin botones de escritura y con el aviso de que los administra el Gerente."""
        self.client.force_login(self.agronomo)
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, "Extractor")
        self.assertContains(respuesta, "Catálogo de capacidades")
        self.assertContains(respuesta, "los administra el Gerente")
        for texto in ("Nuevo tipo", self.url_nuevo, self.url("tipo_modificar"), self.url("tipo_baja"), self.url("tipo_reactivar"), "Dar de baja", "Reactivar"):
            self.assertNotContains(respuesta, texto)

    def test_regla_3_ningun_enlace_de_la_lista_lleva_a_un_403(self):
        """D-30: todo enlace del módulo que ve cada rol se abre (el POST de reactivar da 405 con GET, no 403)."""
        TipoActuador.objects.create(nombre_actuador="Inactivo propio", estado="inactivo")
        for cuenta in (self.gerente, self.agronomo):
            self.client.force_login(cuenta)
            html = self.client.get(self.lista).content.decode()
            for ruta in sorted(set(re.findall(r'(?:href|action)="(/iot/[^"]*)"', html))):
                with self.subTest(cuenta=cuenta.email, ruta=ruta):
                    self.assertNotEqual(self.client.get(ruta).status_code, 403)

    def test_regla_1_los_tipos_inactivos_se_ven_con_su_marca_y_solo_con_reactivar(self):
        """IOT-CNS-TAC regla 1 y 3: el inactivo está en la lista, «Inactivo», y su único botón es «Reactivar»."""
        inactivo = fabricas.tipo_actuador("Dado de baja", activo=False)
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, "Dado de baja")
        self.assertContains(respuesta, self.url("tipo_reactivar", inactivo))
        self.assertNotContains(respuesta, self.url("tipo_modificar", inactivo))
        self.assertNotContains(respuesta, self.url("tipo_baja", inactivo))

    def test_regla_2_la_marca_en_uso_se_ve_en_la_accion_usada(self):
        """IOT-CNS-TAC regla 2: «En uso» junto a la acción usada por una regla activa o un comando pendiente."""
        self.assertNotContains(self.client.get(self.lista), "En uso")
        with mock.patch(EN_USO, return_value={self.encender.pk: [UsoDeAccion("RGL-3", None)]}):
            self.assertContains(self.client.get(self.lista), "En uso")

    def test_regla_2_la_cantidad_de_equipos_no_cuenta_los_dados_de_baja(self):
        """IOT-CNS-TAC regla 2: la columna «Equipos»."""
        sistema = fabricas.sistema(crear_invernadero("Norte"))
        fabricas.actuador(sistema, self.tipo)
        fabricas.actuador(sistema, self.tipo, estado="inactivo")
        fila = re.search(rf"TAC-{self.tipo.pk:02d}.*?</tr>", self.client.get(self.lista).content.decode(), re.S).group(0)
        self.assertRegex(fila, r"<td>1</td>")

    def test_regla_4_ver_la_lista_no_audita(self):
        """IOT-CNS-TAC regla 4 y SEG-14."""
        antes = RegistroAuditoria.objects.count()
        self.client.get(self.lista)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_la_barra_de_contexto_esta_deshabilitada_con_todos_los_invernaderos(self):
        """Pantallas, «tipos»: la barra de contexto (ctxBar) deshabilitada en esta pestaña y la pestaña del módulo."""
        html = self.client.get(self.lista).content.decode()
        self.assertRegex(html, r'<select id="invernadero-del-contexto"[^>]*disabled')
        self.assertIn("Todos los invernaderos", html)
        self.assertIn("Los tipos de actuador son comunes a todos los invernaderos.", html)
        self.assertRegex(html, r'role="tab"[^>]*aria-selected="true">Tipos de actuador')


class IotAltTacVistaTests(TiposVistasBase):
    """IOT-ALT-TAC: el formulario de alta, con y sin HTMX."""

    def alta(self, **cambios):
        """Un POST de alta válido de «Aspersor» con dos acciones, con ``cambios`` encima."""
        datos = self.post_del_tipo(
            "Aspersor",
            "60",
            [{"nombre": "Encender", "comando": "ENCENDER"}, {"nombre": "Fijar caudal", "comando": "FIJAR_NIVEL", "minimo": "0", "maximo": "50", "unidad": "L/min"}],
        )
        datos.update(cambios)
        return self.client.post(self.url_nuevo, datos, follow=True)

    def test_la_pagina_propone_60_segundos_y_una_fila_de_accion(self):
        """«Cómo se aplica», «Tiempo mínimo»: el formulario propone 60; empieza con una acción para completar."""
        respuesta = self.client.get(self.url_nuevo)
        self.assertContains(respuesta, 'name="tiempo_minimo"')
        self.assertContains(respuesta, 'value="60"')
        self.assertContains(respuesta, 'name="accion_0_nombre"')
        self.assertNotContains(respuesta, 'name="accion_1_nombre"')
        self.assertContains(respuesta, "Protege el equipo de cambios demasiado seguidos")
        self.assertContains(respuesta, "Crear tipo")

    def test_flujo_principal_crea_el_tipo_y_avisa(self):
        """IOT-ALT-TAC postcondición a: el tipo queda creado, con sus acciones; vuelve a la lista con un aviso breve (D-29)."""
        respuesta = self.alta()
        self.assertContains(respuesta, "Tipo de actuador creado: Aspersor.")
        tipo = TipoActuador.objects.get(nombre_actuador="Aspersor")
        self.assertEqual([(a.nombre_accion, a.comando.codigo, a.unidad_valor) for a in tipo.acciones.order_by("id")], [("Encender", "ENCENDER", None), ("Fijar caudal", "FIJAR_NIVEL", "L/min")])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_tipo_actuador").count(), 1)

    def test_regla_2_un_nombre_repetido_da_el_error_del_campo_y_conserva_lo_escrito(self):
        """IOT-ALT-TAC regla 2: el error va junto al campo, con el texto del extracto, y el formulario conserva lo escrito."""
        respuesta = self.alta(nombre="ventilador")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ya existe un tipo de actuador con ese nombre.")
        self.assertContains(respuesta, 'value="ventilador"')
        self.assertContains(respuesta, 'value="Fijar caudal"')
        self.assertContains(respuesta, 'value="50"')
        self.assertEqual(TipoActuador.objects.filter(nombre_actuador__iexact="aspersor").count(), 0)

    def test_regla_9_el_tiempo_invalido_marca_su_campo(self):
        """IOT-ALT-TAC regla 9: mensaje del extracto junto al campo."""
        self.assertContains(self.alta(tiempo_minimo="-4"), "Ingresá un número entero de segundos (0 o más).")

    def test_regla_3_los_errores_de_las_acciones_se_ven_sobre_las_filas(self):
        """IOT-ALT-TAC reglas 3 y 4: los mensajes del prototipo, sin perder lo escrito."""
        respuesta = self.alta(accion_1_unidad="")
        self.assertContains(respuesta, "“Fijar caudal” necesita una unidad.")
        respuesta = self.alta(accion_1_comando="ENCENDER")
        self.assertContains(respuesta, "Dos acciones usan el comando ENCENDER.")

    def test_regla_2_todos_los_errores_se_ven_a_la_vez(self):
        """docs/patrones/abm.md, sección 2: el nombre, el tiempo y las acciones, juntos."""
        respuesta = self.alta(nombre="", tiempo_minimo="x", accion_0_nombre="")
        for texto in ("Ingresá el nombre del tipo.", "Ingresá un número entero de segundos (0 o más).", "Cada acción necesita un nombre."):
            self.assertContains(respuesta, texto)

    def test_agregar_accion_sin_javascript_vuelve_a_dibujar_la_pagina_con_una_fila_mas(self):
        """Respaldo sin JavaScript: «Agregar acción» es un botón del formulario; no guarda nada y conserva lo escrito."""
        datos = self.post_del_tipo("Aspersor", "45", [{"nombre": "Encender", "comando": "ENCENDER"}])
        respuesta = self.client.post(self.url_nuevo, datos | {"agregar": "1"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "<html")
        self.assertContains(respuesta, 'name="accion_1_nombre"')
        self.assertContains(respuesta, 'value="Aspersor"')
        self.assertContains(respuesta, 'value="45"')
        self.assertContains(respuesta, 'name="acciones_total" value="2"')
        self.assertFalse(TipoActuador.objects.filter(nombre_actuador="Aspersor").exists())

    def test_agregar_accion_con_htmx_devuelve_solo_el_fragmento_de_las_acciones(self):
        """HTMX: la respuesta es solo el bloque «#acciones» (sin la página) y los pedidos se distinguen por ``HX-Request``."""
        datos = self.post_del_tipo("Aspersor", "45", [{"nombre": "Encender", "comando": "ENCENDER"}])
        respuesta = self.client.post(self.url_nuevo, datos | {"agregar": "1"}, **HX)
        self.assertNotContains(respuesta, "<html")
        self.assertContains(respuesta, 'name="accion_1_nombre"')
        self.assertContains(respuesta, 'name="acciones_total" value="2"')
        self.assertIn("HX-Request", respuesta["Vary"])

    def test_quitar_una_fila_la_saca_y_renumera_las_demas(self):
        """«Quitar» (con y sin HTMX) saca esa fila del formulario y no guarda nada."""
        datos = self.post_del_tipo("A", "60", [{"nombre": "Uno", "comando": "ENCENDER"}, {"nombre": "Dos", "comando": "APAGAR"}])
        for extra in ({}, HX):
            with self.subTest(htmx=bool(extra)):
                respuesta = self.client.post(self.url_nuevo, datos | {"quitar": "0"}, **extra)
                self.assertContains(respuesta, 'name="acciones_total" value="1"')
                self.assertContains(respuesta, 'name="accion_0_nombre" value="Dos"')
                self.assertNotContains(respuesta, 'value="Uno"')

    def test_un_quitar_con_un_indice_raro_no_rompe(self):
        """Un formulario armado a mano con un índice que no existe se ignora."""
        datos = self.post_del_tipo("A", "60", [{"nombre": "Uno", "comando": "ENCENDER"}])
        for indice in ("7", "x", "-9"):
            self.assertEqual(self.client.post(self.url_nuevo, datos | {"quitar": indice}).status_code, 200)

    def test_el_cambio_de_comando_a_uno_con_valor_muestra_rango_y_propone_la_unidad(self):
        """«Cómo se aplica», «Acciones»: al elegir un comando con valor aparecen mínimo, máximo y unidad, y el formulario propone «%»."""
        datos = self.post_del_tipo("A", "60", [{"nombre": "Nivel", "comando": "FIJAR_NIVEL"}])
        respuesta = self.client.post(self.url_nuevo, datos | {"refrescar": "1"}, **HX)
        self.assertContains(respuesta, 'name="accion_0_minimo"')
        self.assertContains(respuesta, 'name="accion_0_maximo"')
        self.assertContains(respuesta, 'name="accion_0_unidad"')
        self.assertRegex(respuesta.content.decode(), r'<option value="%" selected>')
        self.assertContains(respuesta, "rpm (vueltas por minuto)")

    def test_el_cambio_a_un_comando_sin_valor_vacia_unidad_y_rango(self):
        """«Cómo se aplica», «Acciones»: al cambiar a un comando sin valor se vacían la unidad y el rango."""
        datos = self.post_del_tipo("A", "60", [{"nombre": "Encender", "comando": "ENCENDER", "minimo": "0", "maximo": "9", "unidad": "rpm"}])
        respuesta = self.client.post(self.url_nuevo, datos | {"refrescar": "1"}, **HX)
        for campo in ("minimo", "maximo", "unidad"):
            self.assertNotContains(respuesta, f'name="accion_0_{campo}"')

    def test_las_filas_ofrecen_los_comandos_agrupados_por_capacidad(self):
        """«Cómo se aplica», «Acciones»: «lista agrupada por capacidad»."""
        respuesta = self.client.get(self.url_nuevo)
        for texto in ('<optgroup label="Encendido">', '<optgroup label="Nivel">', '<optgroup label="Posición">', "FIJAR_NIVEL (con valor)"):
            self.assertContains(respuesta, texto)

    def test_el_formulario_usa_desplegables_propios_con_respaldo_nativo(self):
        """.claude/rules/interfaz.md: los desplegables llevan ``data-desplegable`` (sin JavaScript queda el ``select`` nativo)."""
        self.assertContains(self.client.get(self.url_nuevo), "data-desplegable")


class IotModTacVistaTests(TiposVistasBase):
    """IOT-MOD-TAC: el formulario de modificación y la reactivación."""

    def test_la_pagina_trae_el_tipo_con_sus_acciones_y_sus_ids(self):
        """IOT-MOD-TAC: el formulario parte de lo guardado, con el id de cada acción original."""
        respuesta = self.client.get(self.url("tipo_modificar"))
        self.assertContains(respuesta, 'value="Extractor"')
        self.assertContains(respuesta, 'name="tiempo_minimo" inputmode="numeric" value="30"')
        self.assertContains(respuesta, f'name="accion_0_id" value="{self.encender.pk}"')
        self.assertContains(respuesta, f'name="accion_1_id" value="{self.fijar.pk}"')
        self.assertContains(respuesta, 'name="accion_1_maximo"')
        self.assertContains(respuesta, "Guardar cambios")

    def test_flujo_principal_guarda_los_cambios_y_avisa(self):
        """IOT-MOD-TAC postcondición a: nombre, tiempo y acciones actualizados; la acción quitada sin historial se borra; aviso breve."""
        datos = self.post_actual(nombre="Extractor 2", tiempo_minimo="90")
        for clave in ("accion_1_id", "accion_1_nombre", "accion_1_comando", "accion_1_minimo", "accion_1_maximo", "accion_1_unidad"):
            datos.pop(clave)
        datos["acciones_total"] = "1"
        respuesta = self.client.post(self.url("tipo_modificar"), datos, follow=True)
        self.assertContains(respuesta, "Se guardó el tipo de actuador Extractor 2.")
        self.tipo.refresh_from_db()
        self.assertEqual((self.tipo.nombre_actuador, self.tipo.tiempo_minimo_entre_comandos), ("Extractor 2", 90))
        self.assertFalse(Accion.objects.filter(pk=self.fijar.pk).exists())

    def test_d28_guardar_sin_cambios_no_audita(self):
        """D-28."""
        self.client.post(self.url("tipo_modificar"), self.post_actual())
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_tipo_actuador").exists())

    def test_regla_2_un_nombre_de_otro_tipo_da_el_error_del_campo(self):
        """IOT-MOD-TAC regla 2."""
        respuesta = self.client.post(self.url("tipo_modificar"), self.post_actual(nombre="Bomba"))
        self.assertContains(respuesta, "Ya existe un tipo de actuador con ese nombre.")

    def test_regla_5_sin_acciones_se_rechaza_con_el_mensaje(self):
        """IOT-MOD-TAC regla 5."""
        respuesta = self.client.post(self.url("tipo_modificar"), self.post_del_tipo(filas=[]))
        self.assertContains(respuesta, "El tipo necesita al menos una acción activa.")

    def test_regla_4_una_accion_en_uso_se_muestra_bloqueada_con_su_motivo(self):
        """IOT-MOD-TAC regla 4: el nombre, el comando y la unidad de una acción en uso no se editan; el valor viaja en campos ocultos."""
        with mock.patch(EN_USO, return_value={self.fijar.pk: [UsoDeAccion("RGL-3", 40)]}):
            html = self.client.get(self.url("tipo_modificar")).content.decode()
        self.assertContains(self.client.get(self.url("tipo_modificar")), "Encender")  # la sin uso sigue editable
        self.assertRegex(html, r'id="an1"[^>]*readonly')
        self.assertRegex(html, r'<select class="field-input" id="ac1" data-desplegable disabled>')
        self.assertIn('<input type="hidden" name="accion_1_comando" value="FIJAR_NIVEL">', html)
        self.assertIn('<input type="hidden" name="accion_1_unidad" value="%">', html)
        self.assertIn("La acción está en uso", html)

    def test_regla_4_el_servicio_informa_que_regla_lo_impide(self):
        """IOT-MOD-TAC regla 4: quitar una acción en uso se rechaza con «la usan RGL-3» sobre las filas."""
        datos = self.post_actual()
        for clave in ("accion_1_id", "accion_1_nombre", "accion_1_comando", "accion_1_minimo", "accion_1_maximo", "accion_1_unidad"):
            datos.pop(clave)
        datos["acciones_total"] = "1"
        with mock.patch(EN_USO, return_value={self.fijar.pk: [UsoDeAccion("RGL-3", 40)]}):
            respuesta = self.client.post(self.url("tipo_modificar"), datos)
        self.assertContains(respuesta, "No se puede quitar «Fijar velocidad»: la usan RGL-3.")
        self.assertTrue(Accion.objects.filter(pk=self.fijar.pk).exists())

    def test_regla_6_informa_cuantos_equipos_usan_el_tipo_y_de_que_invernaderos(self):
        """IOT-MOD-TAC regla 6: «Los cambios afectan a N equipo(s) de este tipo: Invernadero Norte (3), Invernadero Sur (1).»"""
        norte, sur = crear_invernadero("Invernadero Norte"), crear_invernadero("Invernadero Sur")
        for invernadero, cantidad in ((norte, 3), (sur, 1)):
            sistema = fabricas.sistema(invernadero)
            for _ in range(cantidad):
                fabricas.actuador(sistema, self.tipo)
        self.assertContains(
            self.client.get(self.url("tipo_modificar")),
            "Los cambios afectan a 4 equipos de este tipo: Invernadero Norte (3), Invernadero Sur (1).",
        )

    def test_regla_6_sin_equipos_no_se_muestra_el_aviso(self):
        """«Cómo se aplica», «Aviso»: en IOT-01 todavía no hay actuadores y el aviso no se muestra."""
        self.assertNotContains(self.client.get(self.url("tipo_modificar")), "Los cambios afectan a")

    def test_regla_7_un_tipo_inactivo_no_se_modifica_solo_se_reactiva(self):
        """IOT-MOD-TAC regla 7: la página de modificar de un tipo inactivo vuelve a la lista con un aviso de error."""
        TipoActuador.objects.filter(pk=self.tipo.pk).update(estado="inactivo")
        respuesta = self.client.get(self.url("tipo_modificar"), follow=True)
        self.assertRedirects(respuesta, self.lista)
        self.assertContains(respuesta, "solo se puede reactivar")

    def test_post_b_reactivar_con_post_vuelve_a_activar_el_tipo(self):
        """IOT-MOD-TAC postcondición b: «Reactivar» es un POST sin ventana, con aviso breve."""
        TipoActuador.objects.filter(pk=self.tipo.pk).update(estado="inactivo")
        respuesta = self.client.post(self.url("tipo_reactivar"), follow=True)
        self.assertContains(respuesta, "El tipo de actuador Extractor está activo de nuevo.")
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.estado, "activo")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="reactivacion_tipo_actuador").count(), 1)

    def test_post_b_reactivar_con_get_no_cambia_nada(self):
        """Abrir la URL (GET) no cambia nada: 405."""
        TipoActuador.objects.filter(pk=self.tipo.pk).update(estado="inactivo")
        self.assertEqual(self.client.get(self.url("tipo_reactivar")).status_code, 405)
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.estado, "inactivo")

    def test_post_b_reactivar_un_tipo_activo_avisa_el_error(self):
        """El servicio rechaza reactivar uno que no está dado de baja; la pantalla lo muestra como aviso."""
        respuesta = self.client.post(self.url("tipo_reactivar"), follow=True)
        self.assertContains(respuesta, "El tipo de actuador no está dado de baja.")


class IotBajTacVistaTests(TiposVistasBase):
    """IOT-BAJ-TAC: la ventana de la baja."""

    def test_la_ventana_con_htmx_es_un_fragmento_y_abrirla_no_cambia_nada(self):
        """Abrir la ventana (GET) pide confirmar y no da de baja."""
        respuesta = self.client.get(self.url("tipo_baja"), **HX)
        self.assertNotContains(respuesta, "<html")
        self.assertContains(respuesta, "¿Dar de baja Extractor?")
        self.assertContains(respuesta, "Conserva sus acciones")
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.estado, "activo")

    def test_sin_javascript_la_ventana_es_la_lista_con_la_ventana_abierta(self):
        """Respaldo sin JavaScript: cada ventana es también una página."""
        respuesta = self.client.get(self.url("tipo_baja"))
        self.assertContains(respuesta, "<html")
        self.assertContains(respuesta, "¿Dar de baja Extractor?")
        self.assertContains(respuesta, "Catálogo de capacidades")

    def test_flujo_principal_confirmar_da_de_baja_y_avisa(self):
        """IOT-BAJ-TAC postcondición a: el tipo queda inactivo; aviso breve; sigue en la lista con «Reactivar»."""
        respuesta = self.client.post(self.url("tipo_baja"), follow=True)
        self.assertContains(respuesta, "El tipo de actuador Extractor quedó inactivo.")
        self.assertContains(respuesta, self.url("tipo_reactivar"))
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.estado, "inactivo")

    def test_pre_c_con_equipos_la_ventana_dice_cuantos_y_no_ofrece_confirmar(self):
        """IOT-BAJ-TAC regla 2: el texto del extracto, con el invernadero, y sin botón de confirmar."""
        fabricas.actuador(fabricas.sistema(crear_invernadero("Invernadero Norte")), self.tipo)
        respuesta = self.client.get(self.url("tipo_baja"), **HX)
        self.assertContains(respuesta, "Hay 1 equipo de este tipo en Invernadero Norte. Dalos de baja antes de dar de baja el tipo.")
        self.assertNotContains(respuesta, "Dando de baja")
        self.assertNotContains(respuesta, 'method="post"')

    def test_pre_c_un_post_con_equipos_se_rechaza_y_muestra_el_motivo(self):
        """Un envío armado a mano también lo rechaza el servicio."""
        fabricas.actuador(fabricas.sistema(crear_invernadero("Invernadero Norte")), self.tipo)
        respuesta = self.client.post(self.url("tipo_baja"), **HX)
        self.assertContains(respuesta, "Hay 1 equipo de este tipo")
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.estado, "activo")

    def test_pre_b_un_tipo_ya_dado_de_baja_vuelve_a_la_lista_con_un_aviso(self):
        """IOT-BAJ-TAC precondición b."""
        TipoActuador.objects.filter(pk=self.tipo.pk).update(estado="inactivo")
        respuesta = self.client.get(self.url("tipo_baja"), follow=True)
        self.assertRedirects(respuesta, self.lista)
        self.assertContains(respuesta, "ya está dado de baja")
