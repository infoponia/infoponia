# Recorrido de USR-07 (foto de perfil y logo de la organización) de punta a punta con el cliente de prueba de Django, por rol y por
# estado: lo que haría una persona. No reemplaza la «Verificación a mano» (docs/patrones/verificacion_a_mano.md, D-96): el cliente de
# Django no ve el CSRF del navegador, el JavaScript (el envío al elegir el archivo) ni la cámara del celular, ni el bucket real de R2.
# Vive en ``maestros`` y no en ``core`` porque toca las dos apps (regla A3 de D-37). Las imágenes van a InMemoryStorage.

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import RegistroAuditoria, Usuario, Vendedor
from core.tests.fabricas import (
    CLAVE,
    CUADRANTES,
    VaciaImagenesMixin,
    archivo_de_imagen,
    archivos_guardados,
    crear_administrador,
    crear_cuenta,
    crear_gerente,
)
from maestros.models import PerfilOrganizacion
from maestros.tests.fabricas import ConDatosDeMaestros, crear_agronomo

CONFIGURACION = reverse("configuracion:pantalla") + "?pestana=organizacion"
GUARDAR_ORGANIZACION = reverse("configuracion:guardar_organizacion")
HTMX = {"HTTP_HX_REQUEST": "true"}


def organizacion_enviada(**cambios):
    """El perfil guardado como lo envía el formulario de la pestaña «Organización», con ``cambios`` encima."""
    fila = PerfilOrganizacion.objects.get()
    campos = ("nombre_organizacion", "cuit_organizacion", "telefono_organizacion", "email_organizacion", "direccion_organizacion",
              "color_primario", "color_secundario", "color_terciario", "color_cuaternario")
    return {campo: getattr(fila, campo) for campo in campos} | cambios


class RecorridoDeFotoYLogoTests(VaciaImagenesMixin, ConDatosDeMaestros, TestCase):
    """Foto de perfil (USR-GST-PRF regla 5, USR-MOD-USR regla 8) y logo (ADM-MOD-ORG regla 4), por rol y por estado."""

    def setUp(self):
        super().setUp()
        self.gerente = crear_gerente()
        self.vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com", nombre="Vera", apellido="Gómez")

    def entrar(self, cuenta):
        """Abre la sesión de ``cuenta`` con su contraseña, como lo hace una persona."""
        self.client.logout()
        self.assertTrue(self.client.login(username=cuenta.email, password=CLAVE))

    def foto(self, cuenta):
        return Usuario.objects.get(pk=cuenta.pk).foto_perfil.name

    def logo(self):
        return PerfilOrganizacion.objects.get().logo.name

    def test_recorrido_la_foto_de_una_cuenta_de_punta_a_punta(self):
        """Vendedor: sin foto → carga desde archivo → cambia desde la cámara → archivo inválido → quita. Gerente: le quita la foto."""
        self.entrar(self.vendedor)
        perfil = self.client.get(reverse("core:mi_perfil"))
        self.assertContains(perfil, "Elegir foto")  # estado inicial: sin foto, con la sigla
        self.assertNotContains(perfil, 'class="avatar photo"')

        # 1. Carga desde un archivo: se avisa y la foto se ve en Mi perfil y en el encabezado.
        respuesta = self.client.post(reverse("core:cambiar_mi_foto"), {"foto": archivo_de_imagen("vacaciones.jpg", tamano=(900, 600))}, follow=True)
        self.assertContains(respuesta, "Foto de perfil actualizada.")
        self.assertEqual(respuesta.content.decode().count('class="avatar photo"'), 2)
        primera = self.foto(self.vendedor)
        self.assertRegex(primera, r"^fotos_perfil/[0-9a-f-]{36}\.webp$")

        # 2. Cambia con la cámara del celular: queda una sola foto, la nueva.
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("core:cambiar_mi_foto"), {"foto_camara": archivo_de_imagen("camara.png")})
        segunda = self.foto(self.vendedor)
        self.assertNotEqual(segunda, primera)
        self.assertEqual(archivos_guardados(), {segunda})

        # 2b. Editor de encuadre: con los tres valores del editor se guarda esa zona; con uno inválido, aviso y la foto sigue.
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(
                reverse("core:cambiar_mi_foto"),
                {"foto": archivo_de_imagen("encuadre.jpg", tamano=(400, 300), cuadrantes=CUADRANTES),
                 "recorte_x": "200", "recorte_y": "150", "recorte_lado": "150"},
                follow=True,
            )
        self.assertContains(respuesta, "Foto de perfil actualizada.")
        encuadrada = self.foto(self.vendedor)
        self.assertNotEqual(encuadrada, segunda)
        respuesta = self.client.post(
            reverse("core:cambiar_mi_foto"),
            {"foto": archivo_de_imagen("encuadre.jpg", tamano=(400, 300)), "recorte_x": "390", "recorte_y": "0", "recorte_lado": "100"},
            follow=True,
        )
        self.assertContains(respuesta, "adentro de la imagen")
        self.assertEqual(self.foto(self.vendedor), encuadrada)
        segunda = encuadrada

        # 3. Un archivo que no es imagen se rechaza con su motivo y la foto sigue.
        respuesta = self.client.post(reverse("core:cambiar_mi_foto"), {"foto": SimpleUploadedFile("x.jpg", b"texto")}, follow=True)
        self.assertContains(respuesta, "No se pudo abrir ese archivo como imagen")
        self.assertEqual(self.foto(self.vendedor), segunda)

        # 4. El Gerente ve la foto en la ficha y se la quita (no puede cambiarla).
        self.entrar(self.gerente)
        ficha = self.client.get(reverse("core:usuario", args=[self.vendedor.pk]))
        self.assertContains(ficha, "Quitar foto")
        self.assertNotContains(ficha, 'type="file"')
        ventana = self.client.get(reverse("core:usuario_quitar_foto", args=[self.vendedor.pk]), **HTMX)
        self.assertContains(ventana, "¿Quitar la foto de perfil?")
        self.assertEqual(self.foto(self.vendedor), segunda)  # abrir la ventana no cambia nada
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(reverse("core:usuario_quitar_foto", args=[self.vendedor.pk]), follow=True)
        self.assertContains(respuesta, "Se quitó la foto de perfil de Vera Gómez.")
        self.assertEqual(self.foto(self.vendedor), "")
        self.assertEqual(archivos_guardados(), set())

        # 5. La persona carga otra y después la quita ella misma.
        self.entrar(self.vendedor)
        self.client.post(reverse("core:cambiar_mi_foto"), {"foto": archivo_de_imagen("otra.webp")})
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(reverse("core:quitar_mi_foto"), follow=True)
        self.assertContains(respuesta, "Se quitó la foto de perfil.")
        self.assertEqual(archivos_guardados(), set())
        self.assertNotContains(respuesta, 'class="avatar photo"')

        # Ninguno de estos cambios se audita (USR-GST-PRF regla 4, SEG-14).
        self.assertEqual(RegistroAuditoria.objects.filter(accion__icontains="foto").count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(detalle__icontains="fotos_perfil").exists())

    def test_recorrido_alcance_por_rol_en_la_foto(self):
        """El Gerente no gestiona al Administrador (403) y el Administrador sí gestiona al Gerente y a sí mismo; un Agrónomo no gestiona a nadie."""
        admin = crear_administrador()
        agronomo = crear_agronomo()
        for cuenta in (self.gerente, admin):
            self.entrar(cuenta)
            self.client.post(reverse("core:cambiar_mi_foto"), {"foto": archivo_de_imagen("f.png")})
            self.assertTrue(self.foto(cuenta).startswith("fotos_perfil/"))

        self.entrar(self.gerente)  # fuera de su alcance
        self.assertEqual(self.client.post(reverse("core:usuario_quitar_foto", args=[admin.pk])).status_code, 403)
        self.assertTrue(self.foto(admin).startswith("fotos_perfil/"))

        self.entrar(agronomo)  # sin rol de gestión
        self.assertEqual(self.client.post(reverse("core:usuario_quitar_foto", args=[self.vendedor.pk])).status_code, 403)

        self.entrar(admin)  # el Administrador quita la del Gerente y la suya
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("core:usuario_quitar_foto", args=[self.gerente.pk]))
            self.client.post(reverse("core:usuario_quitar_foto", args=[admin.pk]))
        self.assertEqual((self.foto(self.gerente), self.foto(admin)), ("", ""))

    def test_recorrido_el_logo_de_la_organizacion_de_punta_a_punta(self):
        """Gerente: sin logo → carga (HTMX) → se ve en el encabezado y en el inicio de sesión → error por logo + quitar → cambia →
        quita → vuelve el ícono. Otro rol no llega a la pantalla."""
        self.entrar(self.gerente)
        inicio = self.client.get(reverse("core:inicio")).content.decode()
        self.assertIn('<div class="logo"><svg', inicio)  # estado inicial: el ícono
        self.assertNotContains(self.client.get(CONFIGURACION), "Quitar el logo")

        # 1. Carga con HTMX: 204 y recarga; el logo se ve con y sin sesión.
        respuesta = self.client.post(
            GUARDAR_ORGANIZACION, organizacion_enviada(nombre_organizacion="Vivero Los Álamos", logo=archivo_de_imagen("logo.png", tamano=(1000, 400))), **HTMX
        )
        self.assertEqual(respuesta.status_code, 204)
        primero = self.logo()
        self.assertRegex(primero, r"^logos/[0-9a-f-]{36}\.webp$")
        url = PerfilOrganizacion.objects.get().logo.url
        self.assertIn(f'<img src="{url}" alt="" decoding="async">', self.client.get(reverse("core:inicio")).content.decode())
        self.assertContains(self.client.get(CONFIGURACION), "Quitar el logo")
        self.client.logout()
        login = self.client.get(reverse("core:iniciar_sesion")).content.decode()
        self.assertIn('class="logo logo-imagen"', login)
        self.assertIn("Vivero Los Álamos", login)

        # 2. Logo nuevo + «Quitar el logo» a la vez: error, conserva lo escrito y no cambia nada.
        self.entrar(self.gerente)
        respuesta = self.client.post(
            GUARDAR_ORGANIZACION,
            organizacion_enviada(direccion_organizacion="Av. Uruguay 2450", logo=archivo_de_imagen("otro.png"), quitar_logo="on"),
        )
        self.assertContains(respuesta, "Elegí un logo nuevo o marcá")
        self.assertContains(respuesta, 'value="Av. Uruguay 2450"')
        self.assertEqual(self.logo(), primero)

        # 3. Un logo inválido con otros datos válidos no guarda nada.
        respuesta = self.client.post(
            GUARDAR_ORGANIZACION, organizacion_enviada(nombre_organizacion="Otro nombre", logo=SimpleUploadedFile("l.svg", b"<svg><script/></svg>"))
        )
        self.assertContains(respuesta, "No se pudo abrir ese archivo como imagen")
        self.assertNotEqual(PerfilOrganizacion.objects.get().nombre_organizacion, "Otro nombre")

        # 4. Cambia el logo: el archivo anterior se borra.
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(GUARDAR_ORGANIZACION, organizacion_enviada(logo=archivo_de_imagen("nuevo.jpg", tamano=(300, 100))))
        segundo = self.logo()
        self.assertNotEqual(segundo, primero)
        self.assertEqual(archivos_guardados("logos"), {segundo})

        # 5. Lo quita: vuelve el ícono y no queda ningún archivo.
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(GUARDAR_ORGANIZACION, organizacion_enviada(quitar_logo="on"))
        self.assertEqual(self.logo(), "")
        self.assertEqual(archivos_guardados("logos"), set())
        self.assertIn('<div class="logo"><svg', self.client.get(reverse("core:inicio")).content.decode())

        # Auditoría: del logo se registra que cambió, nunca la imagen.
        cambios = [r.detalle["cambios"].get("logo") for r in RegistroAuditoria.objects.filter(accion="modificacion_perfil").order_by("id")]
        self.assertEqual(
            cambios,
            [
                {"antes": "sin logo", "despues": "con logo"},
                {"antes": "con logo", "despues": "logo nuevo"},
                {"antes": "con logo", "despues": "sin logo"},
            ],
        )
        self.assertFalse(RegistroAuditoria.objects.filter(detalle__icontains="logos/").exists())

        # Otros roles no llegan a la pestaña ni pueden enviarla.
        for cuenta in (crear_agronomo(), self.vendedor):
            self.entrar(cuenta)
            self.assertEqual(self.client.get(CONFIGURACION).status_code, 403)
            self.assertEqual(self.client.post(GUARDAR_ORGANIZACION, organizacion_enviada(logo=archivo_de_imagen("x.png"))).status_code, 403)
        self.assertEqual(archivos_guardados("logos"), set())
