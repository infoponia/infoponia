# Pruebas de NOT-01, paso 6: lo que `maestros` le da a la campana de `core` (D-42; regla A4 de D-37). La fuente de alertas
# (``items_de_campana``) y el contador de pendientes del Gerente (``pendientes_de_alertas``) se registran en
# ``MaestrosConfig.ready()`` y se prueban solos y de punta a punta (con la campana, el alta de un Gerente y la ventana de
# baja). Fuentes: D-42, D-14, D-41; regla 7 de 8.18 (lectura); modelo de dominio, ficha ``Alerta``.

from django.test import Client, TestCase
from django.urls import reverse

from core import extensiones, notificaciones, servicios
from core.extensiones import ItemDeAlerta
from core.models import Notificacion, Usuario
from core.tests.fabricas import CLAVE, crear_administrador, crear_capataz, crear_gerente
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
        """D-42: título = la descripción de la alerta, detalle = el invernadero, url = su ficha, severidad = la del tipo."""
        crear_alerta(self.invernadero, "sin_capataz", descripcion_alerta="Invernadero sin Capataz activo")

        (item,) = invernaderos.items_de_campana(self.gerente)

        self.assertIsInstance(item, ItemDeAlerta)
        self.assertEqual(item.titulo, "Invernadero sin Capataz activo")
        self.assertEqual(item.detalle, "Invernadero Norte")
        self.assertEqual(item.url, reverse("maestros:invernadero", args=[self.invernadero.pk]))
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

    def test_d42_el_gerente_ve_en_alertas_la_de_sin_capataz_con_su_severidad_y_el_enlace_a_la_ficha(self):
        """Verificación a mano 4 de NOT-01: «Alertas» del Gerente con la de «sin Capataz», su severidad y el enlace a la ficha."""
        crear_alerta(self.invernadero, "sin_capataz", descripcion_alerta="Invernadero sin Capataz activo")

        contenido = self.cliente.get(self.url, **HTMX).content.decode()

        self.assertIn("Alertas (1)", contenido)
        self.assertIn("Invernadero sin Capataz activo", contenido)
        self.assertIn("Invernadero Norte", contenido)
        self.assertIn("sev-advertencia", contenido)
        self.assertIn(f'href="{reverse("maestros:invernadero", args=[self.invernadero.pk])}"', contenido)

    def test_d42_el_punto_sigue_a_la_lectura_de_la_alerta(self):
        """D-42: con una alerta no leída hay punto; ya leída (``estado_lectura_alerta``) sigue en la lista pero sin punto."""
        alerta = crear_alerta(self.invernadero, "sin_capataz")
        inicio = reverse("core:inicio")

        self.assertIn("dotn", self.cliente.get(inicio).content.decode())

        Alerta.objects.filter(pk=alerta.pk).update(estado_lectura_alerta=Alerta.Lectura.LEIDA)

        self.assertNotIn("dotn", self.cliente.get(inicio).content.decode())
        self.assertIn("Alertas (1)", self.cliente.get(self.url, **HTMX).content.decode())

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
