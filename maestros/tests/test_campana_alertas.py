# Pruebas de NOT-01, paso 6: lo que `maestros` le da a la campana de `core` (D-42; regla A4 de D-37). La fuente de alertas
# (``items_de_campana``) y el contador de pendientes del Gerente (``pendientes_de_alertas``) se registran en
# ``MaestrosConfig.ready()`` y se prueban solos y de punta a punta (con la campana, el alta de un Gerente y la ventana de
# baja). Fuentes: D-42, D-14, D-41; regla 7 de 8.18 (lectura); modelo de dominio, ficha ``Alerta``.

import re
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from core import extensiones, notificaciones, servicios
from core.extensiones import ItemDeAlerta
from core.models import Notificacion, Usuario
from core.tests.fabricas import CLAVE, crear_administrador, crear_capataz, crear_gerente
from maestros import extensiones as extensiones_de_maestros
from maestros.extensiones import Enlace
from maestros.models import Alerta
from maestros.servicios import invernaderos
from maestros.tests.fabricas import (
    ConGeoref,
    crear_agronomo,
    crear_alerta,
    crear_invernadero,
    tipo_de_alerta_de_prueba,
    tipo_falso,
)

HTMX = {"HTTP_HX_REQUEST": "true"}
DESCRIPCION = "Alertas activas para el Gerente"


class CampanaAlertasFuenteTests(ConGeoref, TestCase):
    """``items_de_campana(usuario)``: las alertas activas de ``usuario`` como ``ItemDeAlerta`` (D-42)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Invernadero Norte", agronomo=self.agronomo)

    def test_d42_maestros_registra_su_fuente_y_su_contador_en_ready(self):
        """D-42 y A4 de D-37: ``MaestrosConfig.ready`` registra la fuente de alertas y el contador de pendientes."""
        self.assertIn(invernaderos.items_de_campana, extensiones._FUENTES_DE_ALERTAS)
        self.assertIn(invernaderos.pendientes_de_alertas, extensiones._CONTADORES_DE_PENDIENTES)

    def test_d42_devuelve_las_activas_con_titulo_detalle_url_y_severidad(self):
        """D-42: título = la descripción de la alerta, detalle = el invernadero, url = el detalle de la alerta (MAE-02c, paso 4;
        antes era la ficha del invernadero), severidad = la del tipo."""
        alerta = crear_alerta(self.invernadero, "sin_capataz", descripcion_alerta="Invernadero sin Capataz activo")

        (item,) = invernaderos.items_de_campana(self.gerente)

        self.assertIsInstance(item, ItemDeAlerta)
        self.assertEqual(item.titulo, "Invernadero sin Capataz activo")
        self.assertEqual(item.detalle, "Invernadero Norte")
        self.assertEqual(item.url, reverse("alertas:detalle", args=[alerta.pk]))
        self.assertEqual(item.severidad, "advertencia")

    def test_d42_leida_sale_de_estado_lectura_alerta_no_leida(self):
        """Regla 7 de 8.18: una alerta recién creada es «no leída»: ``leida`` es falso."""
        crear_alerta(self.invernadero, "sin_capataz")

        (item,) = invernaderos.items_de_campana(self.gerente)

        self.assertFalse(item.leida)

    def test_d42_leida_sale_de_estado_lectura_alerta_leida(self):
        """Regla 7 de 8.18: una alerta «leída» sigue activa y figura en la lista, con ``leida`` verdadero."""
        crear_alerta(self.invernadero, "sin_capataz", estado_lectura_alerta=Alerta.Lectura.LEIDA)

        (item,) = invernaderos.items_de_campana(self.gerente)

        self.assertTrue(item.leida)

    def test_d42_lista_juntas_las_leidas_y_las_no_leidas(self):
        """D-42: la pestaña lista todas las activas; cada una con su propia lectura (los dos estados son independientes)."""
        crear_alerta(self.invernadero, "sin_capataz", estado_lectura_alerta=Alerta.Lectura.LEIDA)
        crear_alerta(self.invernadero, "sin_vendedor")

        items = invernaderos.items_de_campana(self.gerente)

        self.assertEqual(sorted(item.leida for item in items), [False, True])

    def test_d42_no_incluye_las_resueltas(self):
        """D-42: solo las alertas activas; una resuelta (aunque no esté leída) no figura."""
        crear_alerta(self.invernadero, "sin_capataz", resuelta=True)

        self.assertEqual(invernaderos.items_de_campana(self.gerente), [])

    def test_d42_la_severidad_sale_del_tipo_registrado_y_no_de_la_alerta(self):
        """D-42, paso 6: «severidad desde el tipo registrado»: manda el tipo aunque la alerta guardara otra."""
        tipo = tipo_falso("prueba_critica", severidad=Alerta.Severidad.CRITICA)
        with tipo_de_alerta_de_prueba(tipo):
            crear_alerta(self.invernadero, "prueba_critica", nivel_severidad=Alerta.Severidad.INFORMATIVA)
            (item,) = invernaderos.items_de_campana(self.gerente)

        self.assertEqual(item.severidad, "critica")

    def test_d42_un_codigo_ya_no_registrado_usa_la_severidad_guardada_y_no_rompe(self):
        """Una alerta de un tipo que ya no está registrado no rompe la campana de toda la pantalla: usa la que se guardó
        con la alerta (MD-109)."""
        crear_alerta(self.invernadero, "tipo_que_ya_no_existe", nivel_severidad=Alerta.Severidad.CRITICA)

        (item,) = invernaderos.items_de_campana(self.gerente)

        self.assertEqual(item.severidad, "critica")

    def test_d42_el_gerente_ve_solo_las_suyas_el_agronomo_las_de_sus_invernaderos(self):
        """Regla 1 de 8.9 y D-28 (``Alerta.objects.para``): el Gerente, las ``para_gerente``; el Agrónomo, las suyas."""
        del_gerente = crear_alerta(self.invernadero, "sin_capataz", para_gerente=True)
        del_agronomo = crear_alerta(self.invernadero, "prueba_agr", para_gerente=False, agronomo=self.agronomo,
                                    descripcion_alerta="Para el Agrónomo")
        otro = crear_agronomo("otro.agronomo@infoponia.com")
        crear_alerta(self.invernadero, "prueba_otro", para_gerente=False, agronomo=otro, descripcion_alerta="De otro")

        titulos_del_gerente = [item.titulo for item in invernaderos.items_de_campana(self.gerente)]
        titulos_del_agronomo = [item.titulo for item in invernaderos.items_de_campana(self.agronomo)]

        self.assertEqual(titulos_del_gerente, [del_gerente.descripcion_alerta])
        self.assertEqual(titulos_del_agronomo, [del_agronomo.descripcion_alerta])

    def test_d42_un_rol_sin_alertas_o_una_cuenta_inactiva_no_ve_ninguna(self):
        """D-42 y regla 1 de 8.9: el Capataz (hoy) no recibe alertas; una cuenta inactiva o ``None``, tampoco."""
        crear_alerta(self.invernadero, "sin_capataz")
        inactiva = crear_agronomo("inactivo@infoponia.com", activo=False)

        for usuario in (crear_capataz(), inactiva, None):
            with self.subTest(usuario=usuario):
                self.assertEqual(invernaderos.items_de_campana(usuario), [])

    def test_d42_arma_la_lista_con_una_sola_consulta(self):
        """Eficiencia: se pide el invernadero junto con las alertas (``select_related``); no hay una consulta por alerta."""
        for tipo in ("sin_capataz", "sin_vendedor", "sin_tecnico"):
            crear_alerta(self.invernadero, tipo)

        with self.assertNumQueries(1):
            self.assertEqual(len(invernaderos.items_de_campana(self.gerente)), 3)

    def test_d42_la_fuente_no_cambia_nada_ni_marca_leidas(self):
        """D-42 y SEG-14: es solo lectura; armar la campana no marca la alerta como leída (eso es ``abrir_alerta``, MAE-02b)."""
        alerta = crear_alerta(self.invernadero, "sin_capataz")

        invernaderos.items_de_campana(self.gerente)

        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.NO_LEIDA)

    def test_d42_core_ordena_por_severidad_las_alertas_de_maestros_y_conserva_el_orden_dentro_de_cada_nivel(self):
        """D-42: ``core.alertas_para`` junta esta fuente (la real, registrada en ``ready``) y ordena crítica, advertencia,
        informativa."""
        tipos = [
            tipo_falso("prueba_info", severidad=Alerta.Severidad.INFORMATIVA),
            tipo_falso("prueba_critica", severidad=Alerta.Severidad.CRITICA),
        ]
        with tipo_de_alerta_de_prueba(*tipos):
            crear_alerta(self.invernadero, "prueba_info", descripcion_alerta="III")
            crear_alerta(self.invernadero, "sin_capataz", descripcion_alerta="AAA1")
            crear_alerta(self.invernadero, "prueba_critica", descripcion_alerta="CCC")
            crear_alerta(self.invernadero, "sin_vendedor", descripcion_alerta="AAA2")
            titulos = [item.titulo for item in extensiones.alertas_para(self.gerente)]

        # Dentro de «advertencia», la más reciente primero (el orden de ``Alerta``): AAA2 se creó después que AAA1.
        self.assertEqual(titulos, ["CCC", "AAA2", "AAA1", "III"])

    # ---- R10 (MAE-02d, paso 5): el enlace de una app y ``alertas:ir`` ----

    def con_registrante(self, funcion, codigos=("com_falso",)):
        """Reemplaza los registrantes de enlaces por uno falso mientras dura la prueba."""
        parche = mock.patch.object(extensiones_de_maestros, "_ENLACES", [])
        parche.start()
        self.addCleanup(parche.stop)
        extensiones_de_maestros.registrar_enlace_de_alerta(codigos, funcion)

    def test_r10_con_registrante_la_url_es_alertas_ir_y_el_detalle_es_el_del_registrante(self):
        """R10 y D-62 (tercera enmienda, punto 3): el enlace de una app lleva a ``alertas:ir`` y su texto va debajo del título;
        la alerta que el registrante no devuelve y la de otro tipo quedan como antes (el detalle y el nombre del invernadero)."""
        de_app = crear_alerta(self.invernadero, "com_falso", descripcion_alerta="De la app")
        sin_enlace = crear_alerta(self.invernadero, "com_falso", descripcion_alerta="Sin enlace")
        otra = crear_alerta(self.invernadero, "sin_capataz", descripcion_alerta="De maestros")
        self.con_registrante(lambda usuario, alertas: {de_app.pk: Enlace("/alertas/", "Faltan 120 plantas")})

        items = {item.titulo: item for item in invernaderos.items_de_campana(self.gerente)}

        self.assertEqual(items["De la app"].url, reverse("alertas:ir", args=[de_app.pk]))
        self.assertEqual(items["De la app"].detalle, "Faltan 120 plantas")
        for titulo, alerta in (("Sin enlace", sin_enlace), ("De maestros", otra)):
            with self.subTest(titulo=titulo):
                self.assertEqual(items[titulo].url, reverse("alertas:detalle", args=[alerta.pk]))
                self.assertEqual(items[titulo].detalle, "Invernadero Norte")

    def test_r10_un_registrante_que_devuelve_el_detalle_no_pasa_por_alertas_ir(self):
        """R10: si el enlace del registrante es el propio detalle, la campana lleva al detalle (no es un enlace de una app) y usa
        el texto del registrante."""
        alerta = crear_alerta(self.invernadero, "com_falso")
        detalle = reverse("alertas:detalle", args=[alerta.pk])
        self.con_registrante(lambda usuario, alertas: {alerta.pk: Enlace(detalle, "Otro texto")})

        (item,) = invernaderos.items_de_campana(self.gerente)

        self.assertEqual((item.url, item.detalle), (detalle, "Otro texto"))

    def test_r10_las_consultas_son_las_mismas_con_una_que_con_tres_alertas_de_un_tipo_con_registrante(self):
        """R10 y D-62, punto 2: una llamada a ``enlaces_de_alertas`` para toda la lista; sin consultas por alerta."""
        self.con_registrante(lambda usuario, alertas: {a.pk: Enlace("/alertas/", "Texto") for a in alertas})
        crear_alerta(self.invernadero, "com_falso")
        with self.assertNumQueries(1):
            self.assertEqual(len(invernaderos.items_de_campana(self.gerente)), 1)

        crear_alerta(self.invernadero, "com_falso")
        crear_alerta(self.invernadero, "com_falso")
        with self.assertNumQueries(1):
            self.assertEqual(len(invernaderos.items_de_campana(self.gerente)), 3)

    def test_r10_el_registrante_se_llama_una_vez_con_el_usuario_y_todas_sus_alertas(self):
        """D-62, punto 2: ``items_de_campana`` hace una sola llamada por registrante, con ``usuario`` y la lista entera."""
        registrante = mock.Mock(return_value={})
        self.con_registrante(registrante)
        alertas = [crear_alerta(self.invernadero, "com_falso") for _ in range(3)]

        invernaderos.items_de_campana(self.gerente)

        self.assertEqual(registrante.call_count, 1)
        usuario, recibidas = registrante.call_args.args
        self.assertEqual(usuario, self.gerente)
        self.assertCountEqual([a.pk for a in recibidas], [a.pk for a in alertas])


class PendientesDeAlertasTests(ConGeoref, TestCase):
    """``pendientes_de_alertas()``: el contador de pendientes del Gerente de `maestros` (D-14, D-42)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Invernadero Norte", agronomo=self.agronomo)

    def test_d42_sin_alertas_activas_devuelve_lista_vacia(self):
        """Contrato: sin nada pendiente, ``[]`` (no ``[(descripción, 0)]``)."""
        self.assertEqual(invernaderos.pendientes_de_alertas(), [])

    def test_d42_cuenta_las_activas_para_el_gerente(self):
        """D-42: «alertas activas para el Gerente» (``para_gerente=True``), con ese texto."""
        crear_alerta(self.invernadero, "sin_capataz")
        crear_alerta(self.invernadero, "sin_vendedor")

        self.assertEqual(invernaderos.pendientes_de_alertas(), [(DESCRIPCION, 2)])

    def test_d42_cuenta_tambien_las_ya_leidas(self):
        """Regla 7 de 8.18: leída no es resuelta; la alerta sigue esperando una resolución, así que sigue pendiente."""
        crear_alerta(self.invernadero, "sin_capataz", estado_lectura_alerta=Alerta.Lectura.LEIDA)

        self.assertEqual(invernaderos.pendientes_de_alertas(), [(DESCRIPCION, 1)])

    def test_d42_no_cuenta_las_resueltas(self):
        """Solo las activas: una resuelta ya no espera nada. Si es la única, vuelve la lista vacía."""
        crear_alerta(self.invernadero, "sin_capataz", resuelta=True)

        self.assertEqual(invernaderos.pendientes_de_alertas(), [])

    def test_d42_no_cuenta_las_que_son_solo_del_agronomo(self):
        """D-42: solo ``para_gerente=True``; una alerta que es solo de un Agrónomo no es un pendiente del Gerente."""
        crear_alerta(self.invernadero, "prueba_agr", para_gerente=False, agronomo=self.agronomo)

        self.assertEqual(invernaderos.pendientes_de_alertas(), [])

    def test_d42_cuenta_la_que_es_del_agronomo_y_del_gerente(self):
        """Regla 2 de 8.9 (umbral de merma): una alerta para el Agrónomo y el Gerente a la vez cuenta una vez."""
        crear_alerta(self.invernadero, "prueba_ambos", para_gerente=True, agronomo=self.agronomo)

        self.assertEqual(invernaderos.pendientes_de_alertas(), [(DESCRIPCION, 1)])

    def test_d14_sin_gerente_activo_las_alertas_siguen_esperando(self):
        """D-14: lo pendiente se calcula por estado y no por persona: sin Gerente activo el contador no cambia."""
        crear_alerta(self.invernadero, "sin_capataz")
        self.gerente.is_active = False
        self.gerente.save(update_fields=["is_active"])

        self.assertEqual(invernaderos.pendientes_de_alertas(), [(DESCRIPCION, 1)])

    def test_d42_core_suma_el_contador_real_de_maestros(self):
        """D-42: ``pendientes_del_gerente`` junta el contador registrado en ``ready`` (sin parches)."""
        self.assertEqual(notificaciones.pendientes_del_gerente(), (0, []))
        crear_alerta(self.invernadero, "sin_capataz")
        crear_alerta(self.invernadero, "sin_vendedor")

        self.assertEqual(notificaciones.pendientes_del_gerente(), (2, [(DESCRIPCION, 2)]))

    def test_post_d_el_alta_del_gerente_avisa_las_alertas_activas_de_maestros(self):
        """USR-ALT-USR postcondición d: el Gerente nuevo recibe el total con las alertas activas para el Gerente (D-14)."""
        self.gerente.is_active = False
        self.gerente.save(update_fields=["is_active"])
        crear_alerta(self.invernadero, "sin_capataz")
        crear_alerta(self.invernadero, "sin_vendedor")

        cuenta, _ = servicios.alta_usuario(
            crear_administrador(),
            rol=Usuario.Rol.GERENTE,
            nombre="Nuevo",
            apellido="Gerente",
            email="nuevo.gerente@infoponia.com",
        )

        aviso = Notificacion.objects.get(destinatario=cuenta)
        self.assertEqual(aviso.detalle, "Tiene 2 pendientes. Alertas activas para el Gerente: 2.")

    def test_post_c_la_ventana_de_baja_del_gerente_muestra_las_alertas_activas_de_maestros(self):
        """USR-BAJ-USR postcondición c: el Administrador ve cuántos pendientes quedan (las alertas activas para el Gerente)."""
        crear_alerta(self.invernadero, "sin_capataz")
        cliente = Client()
        cliente.force_login(crear_administrador())

        respuesta = cliente.get(reverse("core:usuario_baja", args=[self.gerente.pk]), headers={"HX-Request": "true"})

        self.assertContains(respuesta, "Pendientes del Gerente: 1 (Alertas activas para el Gerente: 1).")


class CampanaConAlertasDeMaestrosTests(ConGeoref, TestCase):
    """La campana de punta a punta con la fuente real de `maestros` (verificación a mano, paso 4 de NOT-01)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Invernadero Norte", agronomo=self.agronomo)
        self.cliente = Client()
        self.cliente.login(email=self.gerente.email, password=CLAVE)
        self.url = reverse("core:campana")

    def test_d42_el_gerente_ve_en_alertas_la_de_sin_capataz_con_su_severidad_y_el_enlace_al_detalle(self):
        """Verificación a mano 4 de NOT-01: «Alertas» del Gerente con la de «sin Capataz», su severidad y el enlace al detalle
        de la alerta (MAE-02c, paso 4; antes era la ficha del invernadero)."""
        alerta = crear_alerta(self.invernadero, "sin_capataz", descripcion_alerta="Invernadero sin Capataz activo")

        contenido = self.cliente.get(self.url, **HTMX).content.decode()

        self.assertIn("Alertas (1)", contenido)
        self.assertIn("Invernadero sin Capataz activo", contenido)
        self.assertIn("Invernadero Norte", contenido)
        self.assertIn("sev-advertencia", contenido)
        self.assertIn(f'href="{reverse("alertas:detalle", args=[alerta.pk])}"', contenido)

    def test_d42_el_punto_sigue_a_la_lectura_de_la_alerta(self):
        """D-42: con una alerta no leída hay punto; ya leída (``estado_lectura_alerta``) sigue en la lista pero sin punto."""
        alerta = crear_alerta(self.invernadero, "sin_capataz")
        inicio = reverse("core:inicio")

        self.assertIn("dotn", self.cliente.get(inicio).content.decode())

        Alerta.objects.filter(pk=alerta.pk).update(estado_lectura_alerta=Alerta.Lectura.LEIDA)

        self.assertNotIn("dotn", self.cliente.get(inicio).content.decode())
        self.assertIn("Alertas (1)", self.cliente.get(self.url, **HTMX).content.decode())

    def test_regla_r7_abrir_una_alerta_desde_la_campana_la_marca_leida_y_apaga_el_punto_rojo(self):
        """MAE-02c, paso 4 (cierra el punto 4 de «Cuando exista la primera notificación o alerta»): de punta a punta, el enlace de
        la campana lleva al detalle, que llama a ``abrir_alerta``; las no leídas bajan en uno y el punto rojo se apaga."""
        alerta = crear_alerta(self.invernadero, "sin_capataz", descripcion_alerta="Invernadero sin Capataz activo")
        no_leidas = lambda: Alerta.objects.para(self.gerente).activas().no_leidas().count()
        self.assertEqual(no_leidas(), 1)
        self.assertIn("dotn", self.cliente.get(reverse("core:inicio")).content.decode())

        enlace = re.search(r'href="(/alertas/\d+/)"', self.cliente.get(self.url, **HTMX).content.decode()).group(1)
        respuesta = self.cliente.get(enlace)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(enlace, reverse("alertas:detalle", args=[alerta.pk]))
        self.assertEqual(no_leidas(), 0)
        self.assertNotIn("dotn", self.cliente.get(reverse("core:inicio")).content.decode())
        self.assertIn("Alertas (1)", self.cliente.get(self.url, **HTMX).content.decode())  # sigue activa

    def test_d42_el_agronomo_ve_las_suyas_y_el_capataz_alertas_cero(self):
        """D-42, «Quién ve la campana»: el Agrónomo las de su invernadero; el Capataz «Alertas (0)»."""
        crear_alerta(self.invernadero, "prueba_agr", para_gerente=False, agronomo=self.agronomo,
                     descripcion_alerta="Para el Agrónomo")
        capataz = crear_capataz()

        del_agronomo = Client()
        del_agronomo.login(email=self.agronomo.email, password=CLAVE)
        del_capataz = Client()
        del_capataz.login(email=capataz.email, password=CLAVE)

        self.assertIn("Alertas (1)", del_agronomo.get(self.url, **HTMX).content.decode())
        self.assertIn("Alertas (0)", del_capataz.get(self.url, **HTMX).content.decode())

    def test_r10_de_punta_a_punta_la_campana_pasa_por_alertas_ir_marca_leida_y_llega_a_la_pantalla_del_registrante(self):
        """R10 y D-62 (tercera enmienda, punto 3): con el enlace de una app, el enlace de la campana es ``alertas:ir``; al abrirlo,
        las no leídas bajan en uno, el punto rojo se apaga y la respuesta final es la pantalla del registrante."""
        alerta = crear_alerta(self.invernadero, "com_falso", descripcion_alerta="De la app")
        no_leidas = lambda: Alerta.objects.para(self.gerente).activas().no_leidas().count()
        with mock.patch.object(extensiones_de_maestros, "_ENLACES", []):
            extensiones_de_maestros.registrar_enlace_de_alerta(
                ("com_falso",), lambda usuario, alertas: {a.pk: Enlace(reverse("alertas:lista"), "Faltan 120 plantas") for a in alertas}
            )
            self.assertEqual(no_leidas(), 1)
            self.assertIn("dotn", self.cliente.get(reverse("core:inicio")).content.decode())

            contenido = self.cliente.get(self.url, **HTMX).content.decode()
            enlace = re.search(r'href="(/alertas/\d+/ir/)"', contenido).group(1)
            respuesta = self.cliente.get(enlace, follow=True)

        self.assertEqual(enlace, reverse("alertas:ir", args=[alerta.pk]))
        self.assertIn("Faltan 120 plantas", contenido)
        self.assertEqual(respuesta.redirect_chain, [(reverse("alertas:lista"), 302)])
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "maestros/alertas/lista.html")
        self.assertEqual(no_leidas(), 0)
        self.assertNotIn("dotn", self.cliente.get(reverse("core:inicio")).content.decode())
