# Pruebas del admin de Alerta (MAE-02a, D-41): de solo lectura y disponible solo en desarrollo. Fuentes: D-30 (el admin de
# Django existe solo con DEBUG: ``ADMIN_DJANGO_HABILITADO = DEBUG`` y, apagado, no se registra ninguna ruta de /admin/) y
# la verificación a mano de docs/tareas/maestros/MAE-02a-alerta.md. D-30 no condiciona el registro del modelo, sino las
# rutas: por eso la prueba «sin DEBUG» mira la ruta (404), igual que las de core (core/tests/test_admin_django.py).
# Las pruebas de ruta fijan ``ADMIN_DJANGO_HABILITADO`` y vuelven a armar las rutas, para dar lo mismo en el CI (DEBUG apagado).

from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import reverse

from core.tests.fabricas import crear_administrador
from core.tests.test_admin_django import recargar_urls
from maestros.models import Alerta
from maestros.tests.fabricas import ConGeoref, crear_alerta, crear_invernadero


class AdminAlertaRegistroTests(TestCase):
    """D-30 y verificación a mano de MAE-02a: Alerta está registrada en el admin, de solo lectura."""

    def test_d30_alerta_esta_registrada_en_el_admin(self):
        """D-30 y MAE-02a (verificación a mano): ``Alerta`` aparece en el admin de Django."""
        self.assertTrue(admin.site.is_registered(Alerta))

    def test_d30_alerta_es_de_solo_lectura_incluso_para_un_superusuario(self):
        """MAE-02a (plan: «admin de Alerta de solo lectura»): ni agregar, ni modificar, ni borrar; sí ver. Las
        alertas las crean y resuelven los servicios de maestros, no una persona desde el admin."""
        modelo_admin = admin.site._registry[Alerta]
        pedido = self.client.request().wsgi_request
        pedido.user = crear_administrador()

        self.assertFalse(modelo_admin.has_add_permission(pedido))
        self.assertFalse(modelo_admin.has_change_permission(pedido))
        self.assertFalse(modelo_admin.has_delete_permission(pedido))
        self.assertTrue(modelo_admin.has_view_permission(pedido))

    def test_d30_lista_muestra_las_columnas_y_los_filtros_pedidos(self):
        """MAE-02a (verificación a mano, pasos 4 a 9): la lista muestra a qué invernadero, qué tipo y cómo está cada
        alerta; se filtra por estado y por invernadero."""
        modelo_admin = admin.site._registry[Alerta]

        self.assertEqual(
            list(modelo_admin.list_display),
            [
                "invernadero",
                "tipo_alerta",
                "descripcion_alerta",
                "estado_alerta",
                "estado_lectura_alerta",
                "fecha_hora_alerta",
                "fecha_resolucion",
                "para_gerente",
                "agronomo",
            ],
        )
        self.assertEqual(list(modelo_admin.list_filter), ["estado_alerta", "invernadero"])


class AdminAlertaPantallasTests(ConGeoref, TestCase):
    """D-30: con el admin encendido, las pantallas de Alerta solo dejan mirar; apagado, no existen."""

    def fijar_admin(self, habilitado):
        """Fija ``ADMIN_DJANGO_HABILITADO`` y vuelve a armar las rutas; todo se deshace al terminar."""
        # Los cleanups corren al revés: primero se deshace el ajuste y recién después se recargan las rutas.
        self.addCleanup(recargar_urls)
        ajuste = override_settings(ADMIN_DJANGO_HABILITADO=habilitado)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        recargar_urls()

    def test_d30_con_admin_encendido_se_ve_la_lista_y_la_ficha_pero_no_se_agrega_ni_borra(self):
        """D-30 y MAE-02a: lista y ficha responden 200 y cualquier alta, edición o baja da 403."""
        self.fijar_admin(True)
        alerta = crear_alerta(crear_invernadero())
        self.client.force_login(crear_administrador())

        lista = self.client.get(reverse("admin:maestros_alerta_changelist"))
        ficha = self.client.get(reverse("admin:maestros_alerta_change", args=[alerta.pk]))
        alta = self.client.get(reverse("admin:maestros_alerta_add"))
        edicion = self.client.post(reverse("admin:maestros_alerta_change", args=[alerta.pk]), {"estado_alerta": "resuelta"})
        baja = self.client.post(reverse("admin:maestros_alerta_delete", args=[alerta.pk]), {"post": "yes"})

        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, alerta.descripcion_alerta)
        self.assertEqual(ficha.status_code, 200)
        self.assertEqual(alta.status_code, 403)
        self.assertEqual(edicion.status_code, 403)
        self.assertEqual(baja.status_code, 403)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.ACTIVA)

    def test_d30_con_admin_apagado_la_ruta_de_alertas_no_existe(self):
        """D-30 y SEG-18: sin DEBUG no se registra ninguna ruta de /admin/, ni la de Alerta: responde 404."""
        self.fijar_admin(False)
        self.client.force_login(crear_administrador())

        respuesta = self.client.get("/admin/maestros/alerta/")

        self.assertEqual(respuesta.status_code, 404)
