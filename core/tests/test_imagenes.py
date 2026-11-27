# Pruebas del módulo de imágenes (USR-07, D-106 puntos 5 a 8) y del almacenamiento (D-106 puntos 1 a 4): validar, corregir la
# orientación, recortar o achicar, volver a codificar en WebP sin metadatos, nombrar con uuid4 y borrar al confirmar. Las imágenes se
# arman en memoria (``core/tests/fabricas.py``); ninguna prueba llama a R2: en las pruebas ``STORAGES["default"]`` es InMemoryStorage.
# Las del almacenamiento cargan ``config/settings.py`` en un módulo aparte, como ``test_admin_django.py``.

import importlib.util
import os
import sys
import uuid
import warnings
from io import BytesIO
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import SimpleTestCase, TestCase
from PIL import Image, ImageFile

from core import imagenes
from core.tests.fabricas import CUADRANTES, archivo_de_imagen, imagen_en_bytes


def abrir(contenido):
    """La imagen de unos bytes, ya cargada."""
    imagen = Image.open(BytesIO(contenido))
    imagen.load()
    return imagen


class ProcesarImagenTests(SimpleTestCase):
    """D-106 puntos 5 y 6: validar, corregir la orientación y volver a codificar."""

    def test_d106_archivo_de_mas_de_5_mb_se_rechaza_sin_abrirlo(self):
        """D-106 punto 5 y SEG-19: el tope de 5 MB se verifica antes de abrir la imagen con Pillow."""
        archivo = SimpleUploadedFile("grande.jpg", b"0" * (5 * 1024 * 1024 + 1))
        with mock.patch.object(imagenes.Image, "open") as abrir_con_pillow:
            with self.assertRaises(ValidationError) as contexto:
                imagenes.procesar(archivo, 256, recortar_en_cuadrado=True)
        self.assertEqual(contexto.exception.code, "imagen_pesada")
        abrir_con_pillow.assert_not_called()

    def test_d106_un_archivo_que_no_es_imagen_se_rechaza_aunque_diga_jpg(self):
        """D-106 punto 5 y D-20: el servidor verifica que sea una imagen real; la extensión no cuenta."""
        archivo = SimpleUploadedFile("foto.jpg", b"esto no es una imagen, es texto")
        with self.assertRaises(ValidationError) as contexto:
            imagenes.procesar(archivo, 256, recortar_en_cuadrado=True)
        self.assertEqual(contexto.exception.code, "imagen_no_valida")

    def test_d106_una_imagen_truncada_se_rechaza(self):
        """D-106 punto 5: una imagen con cabecera válida pero cuerpo cortado no se acepta."""
        contenido = imagen_en_bytes("PNG", (200, 200))
        archivo = SimpleUploadedFile("foto.png", contenido[: len(contenido) // 2])
        with self.assertRaises(ValidationError) as contexto:
            imagenes.procesar(archivo, 256, recortar_en_cuadrado=True)
        self.assertEqual(contexto.exception.code, "imagen_no_valida")

    def test_d106_un_gif_se_rechaza(self):
        """D-106 punto 5: solo JPG, PNG o WebP; un GIF real, aunque se llame .png, no."""
        for nombre in ("animacion.gif", "animacion.png"):
            with self.subTest(nombre=nombre):
                archivo = SimpleUploadedFile(nombre, imagen_en_bytes("GIF", (50, 50), modo="P", color=1))
                with self.assertRaises(ValidationError) as contexto:
                    imagenes.procesar(archivo, 256, recortar_en_cuadrado=True)
                self.assertEqual(contexto.exception.code, "imagen_formato")

    def test_d106_un_svg_se_rechaza(self):
        """D-106 punto 5: no se acepta SVG, que puede llevar código; tampoco con extensión de imagen."""
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><script>alert(1)</script></svg>'
        for nombre in ("logo.svg", "logo.png", "logo.webp"):
            with self.subTest(nombre=nombre):
                with self.assertRaises(ValidationError):
                    imagenes.procesar(SimpleUploadedFile(nombre, svg), 512)

    def test_d106_jpg_png_y_webp_se_aceptan(self):
        """D-106 punto 5: los tres formatos admitidos salen siempre en WebP."""
        for formato in ("JPEG", "PNG", "WEBP"):
            with self.subTest(formato=formato):
                salida = imagenes.procesar(SimpleUploadedFile("x", imagen_en_bytes(formato, (120, 80))), 512)
                self.assertEqual(abrir(salida).format, "WEBP")

    def test_d106_demasiados_pixeles_se_rechaza(self):
        """D-106 punto 5: se mantiene la protección de Pillow contra imágenes con demasiados píxeles, tanto el error
        como el aviso (una imagen entre el límite y el doble del límite solo avisa)."""
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 1000):
            for lado in (40, 100):  # 1.600 píxeles (aviso) y 10.000 (error)
                with self.subTest(lado=lado):
                    archivo = SimpleUploadedFile("x.png", imagen_en_bytes("PNG", (lado, lado)))
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        with self.assertRaises(ValidationError) as contexto:
                            imagenes.procesar(archivo, 256, recortar_en_cuadrado=True)
                    self.assertEqual(contexto.exception.code, "imagen_enorme")

    def test_d106_la_orientacion_exif_queda_derecha(self):
        """D-106 punto 6: antes de achicar se corrige la orientación; una foto de celular girada sale derecha."""
        # 40 × 20, mitad izquierda roja y derecha azul, con orientación 6 (hay que girarla 90° a la derecha).
        contenido = imagen_en_bytes("PNG", (40, 20), orientacion=6, mitades=((255, 0, 0), (0, 0, 255)))
        imagen = abrir(imagenes.procesar(SimpleUploadedFile("x.png", contenido), 512))
        self.assertEqual(imagen.size, (20, 40))  # girada: ahora es más alta que ancha
        arriba, abajo = imagen.convert("RGB").getpixel((10, 5)), imagen.convert("RGB").getpixel((10, 35))
        self.assertGreater(arriba[0], 200)  # lo que era la izquierda (rojo) queda arriba
        self.assertGreater(abajo[2], 200)  # lo que era la derecha (azul) queda abajo

    def test_d106_la_salida_es_webp_sin_metadatos(self):
        """D-106 punto 6: se descarta todo metadato (ubicación, modelo del teléfono, perfil de color)."""
        contenido = imagen_en_bytes("JPEG", (80, 60), orientacion=3)
        self.assertEqual(len(Image.open(BytesIO(contenido)).getexif()), 2)  # la entrada sí los trae
        imagen = abrir(imagenes.procesar(SimpleUploadedFile("x.jpg", contenido), 256, recortar_en_cuadrado=True))
        self.assertEqual(imagen.format, "WEBP")
        self.assertEqual(len(imagen.getexif()), 0)
        self.assertNotIn("exif", imagen.info)
        self.assertNotIn("icc_profile", imagen.info)

    def test_d106_el_recorte_en_cuadrado_se_achica_hasta_256_y_nunca_se_agranda(self):
        """D-20 («la achica») y precisión de D-106: se recorta en cuadrado y se achica hasta 256 × 256; una foto más chica
        queda con el lado de su recorte (100 × 80 sale de 80 × 80)."""
        casos = {(300, 100): (100, 100), (100, 300): (100, 100), (256, 256): (256, 256), (100, 80): (80, 80),
                 (64, 48): (48, 48), (1200, 900): (256, 256)}
        for tamano, esperado in casos.items():
            with self.subTest(tamano=tamano):
                imagen = abrir(imagenes.procesar(archivo_de_imagen("f.png", tamano=tamano), 256, recortar_en_cuadrado=True))
                self.assertEqual(imagen.size, esperado)

    def test_d106_el_limite_propio_de_40_millones_de_pixeles(self):
        """D-106 punto 5 (límite propio, más estricto que el de Pillow): una imagen que pesa menos de 5 MB pero tiene más de
        40 millones de píxeles se rechaza, y una de 40 millones o menos se acepta. Se decide con la cabecera, sin decodificarla."""
        contenido = imagen_en_bytes("PNG", (8000, 5200), modo="L", color=7)  # 41,6 millones de píxeles, casi todo igual
        self.assertLess(len(contenido), 5 * 1024 * 1024)
        with mock.patch.object(ImageFile.ImageFile, "load", side_effect=AssertionError("no se decodifica")):
            with self.assertRaises(ValidationError) as contexto:
                imagenes.procesar(SimpleUploadedFile("x.png", contenido), 256, recortar_en_cuadrado=True)
        self.assertEqual(contexto.exception.code, "imagen_enorme")
        self.assertEqual(imagenes.LIMITE_DE_PIXELES, 40_000_000)
        justo = imagen_en_bytes("PNG", (8000, 5000), modo="L", color=7)  # exactamente 40 millones
        self.assertEqual(abrir(imagenes.procesar(SimpleUploadedFile("x.png", justo), 512)).size, (512, 320))

    def test_d106_un_jpeg_se_decodifica_reducido_con_draft(self):
        """D-106 punto 5: en un JPEG grande se usa ``Image.draft()``, que decodifica a escala reducida y ahorra memoria; el
        resultado sigue teniendo el tamaño pedido."""
        from PIL import JpegImagePlugin

        original = JpegImagePlugin.JpegImageFile.draft
        archivo = SimpleUploadedFile("x.jpg", imagen_en_bytes("JPEG", (2400, 1800)))
        with mock.patch.object(JpegImagePlugin.JpegImageFile, "draft", autospec=True, side_effect=original) as draft:
            salida = imagenes.procesar(archivo, 256, recortar_en_cuadrado=True)
        draft.assert_called_once()
        self.assertEqual(abrir(salida).size, (256, 256))

    def test_d106_un_png_no_usa_draft(self):
        """``draft`` es solo de los JPEG: con otros formatos no se llama (``Image.draft`` no hace nada ahí)."""
        from PIL import JpegImagePlugin

        archivo = SimpleUploadedFile("x.png", imagen_en_bytes("PNG", (300, 300)))
        with mock.patch.object(JpegImagePlugin.JpegImageFile, "draft", autospec=True) as draft:
            imagenes.procesar(archivo, 256, recortar_en_cuadrado=True)
        draft.assert_not_called()

    def test_d106_sin_recorte_se_conserva_la_proporcion_y_no_se_agranda(self):
        """D-106 punto 11 (logo): el lado mayor mide 512 como máximo, sin recortar y sin agrandar."""
        grande = abrir(imagenes.procesar(archivo_de_imagen("l.png", tamano=(1000, 400)), 512))
        self.assertEqual(grande.size, (512, 205))
        chico = abrir(imagenes.procesar(archivo_de_imagen("l.png", tamano=(300, 100)), 512))
        self.assertEqual(chico.size, (300, 100))

    def test_d106_la_transparencia_se_conserva(self):
        """D-106 punto 11: el WebP del logo conserva la transparencia."""
        contenido = imagen_en_bytes("PNG", (60, 60), modo="RGBA", color=(0, 128, 0, 0))
        imagen = abrir(imagenes.procesar(SimpleUploadedFile("l.png", contenido), 512)).convert("RGBA")
        self.assertEqual(imagen.getpixel((30, 30))[3], 0)
        opaco = abrir(imagenes.procesar(archivo_de_imagen("o.png", tamano=(60, 60)), 512))
        self.assertEqual(opaco.mode, "RGB")


class GuardarYBorrarTests(TestCase):
    """D-106 punto 7: nombre aleatorio en una carpeta por uso; el borrado ocurre solo si la transacción se confirma."""

    def guardar(self, carpeta="fotos_perfil"):
        nombre = imagenes.guardar(imagenes.procesar(archivo_de_imagen(), 256, recortar_en_cuadrado=True), carpeta)
        self.addCleanup(lambda: default_storage.exists(nombre) and default_storage.delete(nombre))
        return nombre

    def test_d106_el_nombre_es_carpeta_uuid4_webp(self):
        """D-106 puntos 7 y 10: ``fotos_perfil/<uuid4>.webp`` y ``logos/<uuid4>.webp``."""
        for carpeta in ("fotos_perfil", "logos"):
            with self.subTest(carpeta=carpeta):
                nombre = self.guardar(carpeta)
                self.assertRegex(nombre, rf"^{carpeta}/[0-9a-f-]{{36}}\.webp$")
                self.assertEqual(uuid.UUID(nombre.split("/")[1][:-5]).version, 4)
                self.assertTrue(default_storage.exists(nombre))

    def test_d106_dos_archivos_no_comparten_nombre(self):
        """D-106 punto 7: el nombre es aleatorio (nunca el del archivo subido)."""
        self.assertNotEqual(self.guardar(), self.guardar())

    def test_d106_borrar_al_confirmar_borra_solo_si_se_confirma(self):
        """D-106 punto 7: el archivo anterior se borra después de confirmada la transacción."""
        nombre = self.guardar()
        with self.captureOnCommitCallbacks(execute=False) as pendientes:
            with transaction.atomic():
                imagenes.borrar_al_confirmar(nombre)
            self.assertTrue(default_storage.exists(nombre))  # todavía no
        for pendiente in pendientes:
            pendiente()
        self.assertFalse(default_storage.exists(nombre))

    def test_d106_si_la_transaccion_se_deshace_no_se_borra(self):
        """D-106 punto 7: si la transacción no se confirma, el archivo anterior queda."""
        nombre = self.guardar()
        with self.captureOnCommitCallbacks(execute=True) as pendientes:
            try:
                with transaction.atomic():
                    imagenes.borrar_al_confirmar(nombre)
                    raise RuntimeError("se deshace")
            except RuntimeError:
                pass
        self.assertEqual(pendientes, [])
        self.assertTrue(default_storage.exists(nombre))

    def test_d106_borrar_un_archivo_que_no_existe_no_falla(self):
        """Quitar una imagen ya borrada (o un nombre vacío) no tira el pedido."""
        imagenes.borrar("fotos_perfil/no-existe.webp")
        imagenes.borrar("")

    def test_d106_borrar_no_tira_el_pedido_si_el_almacenamiento_falla(self):
        """Un fallo al borrar el archivo viejo no deshace una operación ya confirmada: se registra y sigue."""
        with mock.patch("core.imagenes.default_storage") as almacenamiento:
            almacenamiento.delete.side_effect = OSError("sin conexión")
            with self.assertLogs("core.imagenes", level="ERROR"):
                imagenes.borrar("fotos_perfil/x.webp")


# ---- Almacenamiento (D-106 puntos 1 a 4): config/settings.py ----

VARIABLES_R2 = {
    "R2_ACCOUNT_ID": "cuenta123",
    "R2_ACCESS_KEY_ID": "clave-de-acceso",
    "R2_SECRET_ACCESS_KEY": "clave-secreta",
    "R2_BUCKET": "infoponia-imagenes",
}


def cargar_settings(entorno, comando="runserver"):
    """Carga ``config/settings.py`` en un módulo aparte con SOLO ``entorno`` como variables de entorno y ``comando`` como
    ``sys.argv[1]`` (sin leer el ``.env`` de quien corre las pruebas). No toca la configuración en uso."""
    especificacion = importlib.util.spec_from_file_location("config_settings_de_prueba", settings.BASE_DIR / "config" / "settings.py")
    modulo = importlib.util.module_from_spec(especificacion)
    with (
        mock.patch.dict(os.environ, entorno, clear=True),
        mock.patch.object(sys, "argv", ["manage.py", comando]),
        mock.patch("dotenv.load_dotenv"),
    ):
        especificacion.loader.exec_module(modulo)
    return modulo


class AlmacenamientoTests(SimpleTestCase):
    """D-106 punto 4: ``STORAGES["default"]`` según el entorno, y ``ImproperlyConfigured`` en producción sin R2."""

    DESARROLLO = {"DJANGO_DEBUG": "1"}
    PRODUCCION = {"DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "clave-falsa"}

    def backend_de(self, modulo):
        return modulo.STORAGES["default"]["BACKEND"]

    def test_d106_en_las_pruebas_usa_memoria(self):
        """D-106 punto 4: con ``manage.py test`` se usa InMemoryStorage, aunque haya variables de R2 o DEBUG apagado."""
        for entorno in (self.DESARROLLO, self.PRODUCCION, {**self.PRODUCCION, **VARIABLES_R2}):
            with self.subTest(entorno=sorted(entorno)):
                modulo = cargar_settings(entorno, comando="test")
                self.assertEqual(self.backend_de(modulo), "django.core.files.storage.InMemoryStorage")

    def test_d106_en_desarrollo_sin_r2_usa_el_disco_local(self):
        """D-106 punto 4: sin ``R2_BUCKET`` y con DEBUG, el disco local (solo en desarrollo)."""
        modulo = cargar_settings(self.DESARROLLO)
        self.assertEqual(self.backend_de(modulo), "django.core.files.storage.FileSystemStorage")
        self.assertEqual(modulo.MEDIA_URL, "media/")
        self.assertEqual(modulo.MEDIA_ROOT, settings.BASE_DIR / "media")

    def test_d106_con_r2_bucket_usa_r2_con_url_firmada_de_una_hora(self):
        """D-106 puntos 1 a 4: S3Storage apuntado al endpoint de R2, región ``auto``, firma ``s3v4``, URL firmada que vence a la hora."""
        for entorno in ({**self.DESARROLLO, **VARIABLES_R2}, {**self.PRODUCCION, **VARIABLES_R2}):
            with self.subTest(debug=entorno["DJANGO_DEBUG"]):
                modulo = cargar_settings(entorno)
                configuracion = modulo.STORAGES["default"]
                self.assertEqual(configuracion["BACKEND"], "storages.backends.s3.S3Storage")
                opciones = configuracion["OPTIONS"]
                self.assertEqual(opciones["endpoint_url"], "https://cuenta123.r2.cloudflarestorage.com")
                self.assertEqual(opciones["bucket_name"], "infoponia-imagenes")
                self.assertEqual(opciones["region_name"], "auto")
                self.assertEqual(opciones["signature_version"], "s3v4")
                self.assertIs(opciones["querystring_auth"], True)
                self.assertEqual(opciones["querystring_expire"], 3600)

    def test_d106_la_url_de_r2_sale_firmada_y_sin_llamar_a_r2(self):
        """D-106 punto 2: la firma se calcula en el servidor de InfoPonia; la URL lleva firma y vencimiento de 3600 s."""
        from storages.backends.s3 import S3Storage

        opciones = cargar_settings({**self.PRODUCCION, **VARIABLES_R2}).STORAGES["default"]["OPTIONS"]
        url = S3Storage(**opciones).url("fotos_perfil/prueba.webp")
        self.assertTrue(url.startswith("https://"))
        self.assertIn("cuenta123.r2.cloudflarestorage.com", url)
        self.assertIn("X-Amz-Expires=3600", url)
        self.assertIn("X-Amz-Signature=", url)
        self.assertNotIn("clave-secreta", url)

    def test_d106_en_produccion_sin_alguna_variable_de_r2_no_arranca(self):
        """D-106 punto 4: con DEBUG apagado y alguna de las cuatro variables faltante (o vacía), ``ImproperlyConfigured`` que
        nombra la variable."""
        for faltante in VARIABLES_R2:
            for vacia in (False, True):
                with self.subTest(faltante=faltante, vacia=vacia):
                    entorno = {**self.PRODUCCION, **VARIABLES_R2}
                    if vacia:
                        entorno[faltante] = "  "
                    else:
                        del entorno[faltante]
                    with self.assertRaises(ImproperlyConfigured) as contexto:
                        cargar_settings(entorno)
                    self.assertIn(faltante, str(contexto.exception))

    def test_d106_en_produccion_sin_ninguna_variable_nombra_las_cuatro(self):
        """D-106 punto 4: el mensaje nombra todas las variables que faltan."""
        with self.assertRaises(ImproperlyConfigured) as contexto:
            cargar_settings(self.PRODUCCION)
        for variable in VARIABLES_R2:
            self.assertIn(variable, str(contexto.exception))

    def test_d106_sin_django_debug_cuenta_como_produccion(self):
        """D-106 punto 4 y USR-09a: sin ``DJANGO_DEBUG`` el sistema corre como producción: sin R2, no arranca."""
        with self.assertRaises(ImproperlyConfigured):
            cargar_settings({"DJANGO_SECRET_KEY": "clave-falsa"})

    def test_d106_en_desarrollo_con_r2_incompleto_avisa(self):
        """Con ``R2_BUCKET`` y DEBUG, si falta otra variable de R2 también se avisa: sin ella, la librería buscaría credenciales
        por su cuenta y el error sería otro, más difícil de entender."""
        entorno = {**self.DESARROLLO, "R2_BUCKET": "infoponia-imagenes"}
        with self.assertRaises(ImproperlyConfigured) as contexto:
            cargar_settings(entorno)
        self.assertIn("R2_ACCOUNT_ID", str(contexto.exception))

    def test_d106_los_estaticos_no_cambian(self):
        """D-29 y D-106 punto 4: ``STORAGES["staticfiles"]`` queda con el almacenamiento de estáticos de hoy, en todos los entornos."""
        for entorno, comando in ((self.DESARROLLO, "runserver"), ({**self.PRODUCCION, **VARIABLES_R2}, "runserver"), (self.DESARROLLO, "test")):
            with self.subTest(entorno=sorted(entorno), comando=comando):
                modulo = cargar_settings(entorno, comando=comando)
                self.assertEqual(modulo.STORAGES["staticfiles"]["BACKEND"], "django.contrib.staticfiles.storage.StaticFilesStorage")

    def test_d106_la_configuracion_en_uso_en_las_pruebas_es_memoria(self):
        """La configuración con la que corren estas pruebas es InMemoryStorage: ninguna prueba llama a R2."""
        self.assertEqual(settings.STORAGES["default"]["BACKEND"], "django.core.files.storage.InMemoryStorage")
        nombre = default_storage.save("x/prueba.txt", ContentFile(b"x"))
        self.addCleanup(default_storage.delete, nombre)
        self.assertTrue(default_storage.exists(nombre))


# ---- Recorte elegido por la persona (USR-07, editor de encuadre; precisión de D-106) ----

ROJO, VERDE, AZUL, AMARILLO = CUADRANTES


def color_en(contenido, x, y):
    """El color (RGB) del píxel ``(x, y)`` de una imagen ya procesada."""
    return abrir(contenido).convert("RGB").getpixel((x, y))


def parecido(color, esperado, tolerancia=60):
    """True si ``color`` es casi ``esperado`` (el WebP con pérdida mueve un poco los colores)."""
    return all(abs(a - b) <= tolerancia for a, b in zip(color, esperado))


class RecorteElegidoTests(SimpleTestCase):
    """Precisión de D-106 (editor de encuadre): la persona elige el recorte cuadrado ``(x, y, lado)`` en píxeles de la imagen ya
    con la orientación EXIF aplicada; el servidor la corrige primero, recorta con esas coordenadas, achica sin agrandar y vuelve a
    codificar. Sin coordenadas, recorte central. Imagen de prueba: 400 × 300 con cuatro cuadrantes de colores de 200 × 150."""

    def imagen(self, nombre="f.png", tamano=(400, 300), **datos):
        return archivo_de_imagen(nombre, tamano=tamano, cuadrantes=CUADRANTES, **datos)

    def foto(self, archivo, recorte=None, minimo=64):
        """``procesar`` como lo llama la foto de perfil: 256 px, cuadrada, con el lado mínimo de 64."""
        return imagenes.procesar(archivo, 256, recortar_en_cuadrado=True, recorte=recorte, lado_minimo=minimo)

    # ---- la zona recortada es la pedida ----

    def test_recorte_cada_cuadrante_sale_con_su_color(self):
        """El recorte corresponde a la zona pedida, no solo al tamaño: un recorte de 150 px en cada cuadrante da su color en el centro
        y en las esquinas de la salida, que mide 150 × 150 (no se agranda)."""
        zonas = {(0, 0): ROJO, (200, 0): VERDE, (0, 150): AZUL, (200, 150): AMARILLO}
        for (x, y), esperado in zonas.items():
            with self.subTest(x=x, y=y):
                salida = self.foto(self.imagen(), recorte=(x, y, 150))
                self.assertEqual(abrir(salida).size, (150, 150))
                for punto in ((75, 75), (10, 10), (140, 140), (10, 140), (140, 10)):
                    self.assertTrue(parecido(color_en(salida, *punto), esperado), (punto, color_en(salida, *punto)))

    def test_recorte_un_recorte_que_cruza_cuadrantes_muestra_cada_color_en_su_lugar(self):
        """Un recorte de 200 px en el centro (100, 50) reúne los cuatro colores y se achica a 200 × 200 en su proporción."""
        salida = self.foto(self.imagen(), recorte=(100, 50, 200))
        self.assertEqual(abrir(salida).size, (200, 200))
        for punto, esperado in (((20, 20), ROJO), ((180, 20), VERDE), ((20, 180), AZUL), ((180, 180), AMARILLO)):
            self.assertTrue(parecido(color_en(salida, *punto), esperado), punto)

    def test_recorte_un_recorte_grande_se_achica_a_256(self):
        """Un recorte de 300 px (el lado corto) sale de 256 × 256 y conserva cada color en su esquina."""
        salida = self.foto(self.imagen(), recorte=(50, 0, 300))
        self.assertEqual(abrir(salida).size, (256, 256))
        for punto, esperado in (((10, 10), ROJO), ((245, 10), VERDE), ((10, 245), AZUL), ((245, 245), AMARILLO)):
            self.assertTrue(parecido(color_en(salida, *punto), esperado), punto)

    def test_recorte_sin_coordenadas_es_central(self):
        """Sin coordenadas (el camino sin JavaScript), recorte central como hoy: de 400 × 300 sale el cuadrado de 300 desde x = 50."""
        for recorte in (None, (None, None, None), ("", "", "")):
            with self.subTest(recorte=recorte):
                salida = self.foto(self.imagen(), recorte=recorte)
                self.assertEqual(abrir(salida).size, (256, 256))
                for punto, esperado in (((10, 10), ROJO), ((245, 10), VERDE), ((10, 245), AZUL), ((245, 245), AMARILLO)):
                    self.assertTrue(parecido(color_en(salida, *punto), esperado), punto)

    def test_recorte_los_valores_pueden_llegar_como_texto(self):
        """Del POST los valores llegan como texto: ``("200", "150", "150")`` es lo mismo que enteros."""
        salida = self.foto(self.imagen(), recorte=("200", "150", "150"))
        self.assertTrue(parecido(color_en(salida, 75, 75), AMARILLO))

    def test_recorte_los_bordes_validos_se_aceptan(self):
        """El recorte que toca el borde derecho o el inferior, y el que mide el lado corto entero, son válidos."""
        for recorte in ((300, 0, 100), (0, 200, 100), (300, 200, 100), (100, 0, 300), (0, 0, 64)):
            with self.subTest(recorte=recorte):
                self.assertEqual(abrir(self.foto(self.imagen(), recorte=recorte)).format, "WEBP")

    # ---- recortes inválidos: cada uno con su código ----

    def test_recorte_invalido_da_su_codigo(self):
        """Cada recorte inválido lanza ``ValidationError`` con su código; nada se guarda (el servicio no llega a guardar)."""
        casos = {
            "recorte_incompleto": [(10, 20, None), (None, 20, 100), (10, "", 100), (10, None, None)],
            "recorte_no_numerico": [("a", 0, 100), (0, "b", 100), (0, 0, "cien"), ("1.5", 0, 100), (1.5, 0, 100), (0, 0, "10 0")],
            "recorte_negativo": [(-1, 0, 100), (0, -5, 100), (-1, -1, 100), ("-3", 0, 100)],
            "recorte_chico": [(0, 0, 63), (0, 0, 0), (0, 0, -10), (0, 0, "10")],
            "recorte_mayor_que_la_imagen": [(0, 0, 301), (0, 0, 400), (0, 0, 10**20)],
            "recorte_fuera_de_la_imagen": [(301, 0, 100), (0, 201, 100), (350, 250, 100), (10**20, 0, 100)],
        }
        for codigo, recortes in casos.items():
            for recorte in recortes:
                with self.subTest(codigo=codigo, recorte=recorte):
                    with self.assertRaises(ValidationError) as contexto:
                        self.foto(self.imagen(), recorte=recorte)
                    self.assertEqual(contexto.exception.code, codigo)

    def test_recorte_el_lado_minimo_de_64_vale_para_toda_foto(self):
        """Una foto de menos de 64 px en su lado corto se rechaza (``imagen_chica``) con o sin coordenadas; una de 64 px entra y sale de 64 × 64."""
        for tamano in ((60, 60), (100, 63), (63, 500)):
            for recorte in (None, (0, 0, 60)):
                with self.subTest(tamano=tamano, recorte=recorte):
                    with self.assertRaises(ValidationError) as contexto:
                        self.foto(archivo_de_imagen("f.png", tamano=tamano), recorte=recorte)
                    self.assertEqual(contexto.exception.code, "imagen_chica")
        self.assertEqual(abrir(self.foto(archivo_de_imagen("f.png", tamano=(64, 64)))).size, (64, 64))
        self.assertEqual(abrir(self.foto(archivo_de_imagen("f.png", tamano=(64, 90)))).size, (64, 64))

    def test_recorte_sin_lado_minimo_el_logo_acepta_imagenes_chicas(self):
        """El logo no usa el mínimo: ``procesar`` sin ``lado_minimo`` acepta una imagen de 10 × 10."""
        self.assertEqual(abrir(imagenes.procesar(archivo_de_imagen("l.png", tamano=(10, 10)), 512)).size, (10, 10))

    def test_recorte_sin_recortar_en_cuadrado_es_un_error_de_programacion(self):
        """Un recorte solo tiene sentido para la foto cuadrada: pasarlo al logo es un error de programación (``ValueError``)."""
        with self.assertRaises(ValueError):
            imagenes.procesar(self.imagen(), 512, recorte=(0, 0, 100))

    # ---- recorte sobre una imagen chica: nunca se agranda ----

    def test_recorte_valido_sobre_una_imagen_chica_no_se_agranda(self):
        """Una imagen de 100 × 80 con un recorte de 70 sale de 70 × 70 (no de 256) y con la zona pedida."""
        salida = self.foto(archivo_de_imagen("f.png", tamano=(100, 80), cuadrantes=CUADRANTES), recorte=(30, 5, 70))
        self.assertEqual(abrir(salida).size, (70, 70))
        for punto, esperado in (((5, 5), ROJO), ((65, 5), VERDE), ((5, 65), AZUL), ((65, 65), AMARILLO)):
            self.assertTrue(parecido(color_en(salida, *punto), esperado), punto)

    # ---- orientación EXIF: las coordenadas son las de la imagen que ve la persona ----

    def test_recorte_con_exif_rotado_usa_las_coordenadas_de_la_imagen_girada(self):
        """Una foto de 300 × 200 con orientación 6 se ve de 200 × 300 (girada a la derecha): lo que era arriba a la izquierda queda
        arriba a la derecha. Las coordenadas son las de lo que ve la persona; el recorte sale de esa zona."""
        for formato, nombre in (("JPEG", "f.jpg"), ("PNG", "f.png")):
            visto = {(0, 0): AZUL, (100, 0): ROJO, (0, 150): AMARILLO, (100, 150): VERDE}  # cuadrantes de la imagen ya girada
            for (x, y), esperado in visto.items():
                with self.subTest(formato=formato, x=x, y=y):
                    archivo = archivo_de_imagen(nombre, tamano=(300, 200), cuadrantes=CUADRANTES, orientacion=6)
                    salida = self.foto(archivo, recorte=(x, y, 100))
                    self.assertEqual(abrir(salida).size, (100, 100))
                    self.assertTrue(parecido(color_en(salida, 50, 50), esperado, 80), (formato, x, y, color_en(salida, 50, 50)))

    def test_recorte_con_exif_rotado_se_valida_contra_el_tamano_girado(self):
        """El recorte (100, 200, 100) entra en la imagen girada (200 × 300) y quedaría afuera en la original (300 × 200)."""
        for nombre in ("f.jpg", "f.png"):
            with self.subTest(nombre=nombre):
                archivo = archivo_de_imagen(nombre, tamano=(300, 200), cuadrantes=CUADRANTES, orientacion=6)
                self.assertTrue(parecido(color_en(self.foto(archivo, recorte=(100, 200, 100)), 50, 50), VERDE, 80))
                archivo = archivo_de_imagen(nombre, tamano=(300, 200), cuadrantes=CUADRANTES, orientacion=6)
                with self.assertRaises(ValidationError) as contexto:  # 250 + 100 = 350 > 300 de alto girado
                    self.foto(archivo, recorte=(0, 250, 100))
                self.assertEqual(contexto.exception.code, "recorte_fuera_de_la_imagen")

    # ---- Image.draft() con coordenadas: se escalan explícitamente ----

    def test_recorte_en_un_jpeg_grande_usa_draft_y_la_zona_sigue_siendo_la_pedida(self):
        """El JPEG grande se decodifica reducido con ``draft`` y las coordenadas se escalan: la zona recortada es la misma que sin
        reducir. 2400 × 1800 con cuadrantes de 1200 × 900."""
        from PIL import JpegImagePlugin

        original = JpegImagePlugin.JpegImageFile.draft
        zonas = {(0, 0, 600): ROJO, (1200, 0, 600): VERDE, (0, 900, 600): AZUL, (1200, 900, 600): AMARILLO}
        for (x, y, lado), esperado in zonas.items():
            with self.subTest(x=x, y=y):
                archivo = archivo_de_imagen("g.jpg", tamano=(2400, 1800), cuadrantes=CUADRANTES)
                with mock.patch.object(JpegImagePlugin.JpegImageFile, "draft", autospec=True, side_effect=original) as draft:
                    salida = self.foto(archivo, recorte=(x, y, lado))
                draft.assert_called_once()
                self.assertEqual(abrir(salida).size, (256, 256))
                for punto in ((30, 30), (225, 225), (128, 128)):
                    self.assertTrue(parecido(color_en(salida, *punto), esperado), (x, y, punto))

    def test_recorte_en_un_jpeg_grande_que_cruza_cuadrantes_y_con_coordenadas_impares(self):
        """El escalado explícito no corre la zona ni se sale de la imagen con coordenadas que no son múltiplo de la reducción."""
        salida = self.foto(archivo_de_imagen("g.jpg", tamano=(2400, 1800), cuadrantes=CUADRANTES), recorte=(603, 1, 1797))
        self.assertEqual(abrir(salida).size, (256, 256))
        for punto, esperado in (((20, 20), ROJO), ((235, 20), VERDE), ((20, 235), AZUL), ((235, 235), AMARILLO)):
            self.assertTrue(parecido(color_en(salida, *punto), esperado), punto)
        extremo = self.foto(archivo_de_imagen("g.jpg", tamano=(2401, 1799), cuadrantes=CUADRANTES), recorte=(1033, 431, 1368))
        self.assertEqual(abrir(extremo).size, (256, 256))

    def test_recorte_en_un_jpeg_pequeno_no_se_reduce(self):
        """Sin necesidad de reducir (el recorte ya es chico), la decodificación es la completa y el recorte exacto."""
        salida = self.foto(archivo_de_imagen("g.jpg", tamano=(400, 300), cuadrantes=CUADRANTES), recorte=(200, 150, 150))
        self.assertEqual(abrir(salida).size, (150, 150))
        self.assertTrue(parecido(color_en(salida, 75, 75), AMARILLO))

    def test_recorte_la_salida_no_trae_metadatos(self):
        """Todo lo de D-106 sigue igual con coordenadas: WebP sin EXIF ni perfil de color."""
        salida = self.foto(archivo_de_imagen("f.jpg", tamano=(400, 300), cuadrantes=CUADRANTES, orientacion=3), recorte=(100, 50, 200))
        imagen = abrir(salida)
        self.assertEqual((imagen.format, len(imagen.getexif())), ("WEBP", 0))
        self.assertNotIn("icc_profile", imagen.info)

    def test_recorte_el_limite_de_pixeles_se_decide_antes_de_mirar_las_coordenadas(self):
        """El límite de 40 millones de píxeles se sigue decidiendo desde la cabecera, sin decodificar, también con coordenadas."""
        contenido = imagen_en_bytes("PNG", (8000, 5200), modo="L", color=7)
        with mock.patch.object(ImageFile.ImageFile, "load", side_effect=AssertionError("no se decodifica")):
            with self.assertRaises(ValidationError) as contexto:
                self.foto(SimpleUploadedFile("x.png", contenido), recorte=(0, 0, 100))
        self.assertEqual(contexto.exception.code, "imagen_enorme")
