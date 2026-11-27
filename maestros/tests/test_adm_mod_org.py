# Pruebas de ADM-MOD-ORG (Modificar Perfil de la Organización, MAE-04): precondición, reglas 1 a 7, postcondiciones a y b,
# D-28, el logo (D-106 puntos 10 a 15; reemplaza a D-45), la identidad de D-48 y la concurrencia. Fuente: docs/casos_de_uso/maestros/configuracion.md.
# Servicio: ``maestros/servicios/perfil.py``. CUIT válido de prueba: 30-71234567-1 (el del prototipo).

from io import BytesIO
from unittest import mock

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, tag
from PIL import Image

from core.extensiones import Identidad
from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from core.tests.fabricas import (
    VaciaImagenesMixin,
    archivo_de_imagen,
    archivos_guardados,
    crear_administrador,
    crear_capataz,
    crear_gerente,
    imagen_en_bytes,
)
from maestros.models import PerfilOrganizacion
from maestros.servicios import perfil
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    asegurar_datos_de_maestros,
    codigos_de,
    crear_agronomo,
    error_de,
)

CUIT_VALIDO = "30712345671"
CAMPOS_COLOR = ["color_primario", "color_secundario", "color_terciario", "color_cuaternario"]


def guardado():
    """El perfil guardado."""
    return PerfilOrganizacion.objects.get()


def auditorias():
    """Los registros de ``modificacion_perfil``, del más viejo al más nuevo."""
    return list(RegistroAuditoria.objects.filter(accion="modificacion_perfil").order_by("id"))


class AdmModOrgServicioTests(ConDatosDeMaestros, TestCase):
    """ADM-MOD-ORG: las reglas del servicio."""

    def setUp(self):
        self.gerente = crear_gerente()

    def modificar(self, **datos):
        """Modifica el perfil como el Gerente."""
        return perfil.modificar_perfil(self.gerente, **datos)

    def errores(self, **datos):
        """La ``ValidationError`` que lanza modificar con ``datos``."""
        return error_de(lambda: self.modificar(**datos))

    # ---- precondición a y regla 1 ----

    def test_pre_a_solo_un_gerente_activo_modifica(self):
        """ADM-MOD-ORG precondición a y regla 1: cualquier otra cuenta, o ninguna, recibe ``PermissionDenied``."""
        gerente_inactivo = crear_gerente(email="baja@infoponia.com", activo=False)
        for actor in (crear_agronomo(), crear_capataz(), crear_administrador(), gerente_inactivo, None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    perfil.modificar_perfil(actor, nombre_organizacion="Otro")
        self.assertEqual(guardado().nombre_organizacion, settings.NOMBRE_ORGANIZACION)
        self.assertEqual(auditorias(), [])

    def test_regla_1_obtener_crea_la_fila_si_faltara(self):
        """Regla 1 y patrón de singletons: sin fila, ``obtener`` la crea con el nombre de NOMBRE_ORGANIZACION."""
        PerfilOrganizacion.objects.all().delete()
        fila = perfil.obtener()
        self.assertEqual(PerfilOrganizacion.objects.count(), 1)
        self.assertEqual(fila.nombre_organizacion, settings.NOMBRE_ORGANIZACION)

    def test_regla_2_el_perfil_tiene_un_logo_opcional(self):
        """Regla 2 y D-106 punto 10 (reemplaza a D-45): el perfil tiene el campo ``logo``, opcional, en ``logos/``."""
        campo = PerfilOrganizacion._meta.get_field("logo")
        self.assertTrue(campo.blank)
        self.assertEqual(campo.upload_to, "logos/")
        self.assertEqual(guardado().logo.name, "")

    # ---- regla 2: nombre y opcionales ----

    def test_regla_2_el_nombre_es_obligatorio(self):
        """Regla 2: el nombre vacío (o de espacios) da error en su campo."""
        for nombre in ("", "   ", None):
            with self.subTest(nombre=nombre):
                error = self.errores(nombre_organizacion=nombre)
                self.assertEqual(codigos_de(error, "nombre_organizacion"), ["obligatorio"])

    def test_regla_2_el_nombre_se_recorta_y_tiene_un_maximo(self):
        """Regla 2 y ficha del modelo: el nombre se recorta y admite hasta 120 caracteres."""
        self.modificar(nombre_organizacion="  Vivero Los Álamos  ")
        self.assertEqual(guardado().nombre_organizacion, "Vivero Los Álamos")
        self.modificar(nombre_organizacion="x" * 120)
        error = self.errores(nombre_organizacion="x" * 121)
        self.assertEqual(codigos_de(error, "nombre_organizacion"), ["demasiado_largo"])

    def test_regla_2_los_demas_datos_son_opcionales(self):
        """Regla 2: solo el nombre es obligatorio; con todo lo demás vacío se guarda."""
        self.modificar(nombre_organizacion="Vivero", cuit_organizacion="", telefono_organizacion="",
                       email_organizacion="", direccion_organizacion="")
        self.assertEqual(guardado().cuit_organizacion, "")

    def test_regla_2_la_direccion_tiene_un_maximo_de_200(self):
        """Ficha del modelo: dirección de hasta 200 caracteres."""
        self.modificar(direccion_organizacion="d" * 200)
        error = self.errores(direccion_organizacion="d" * 201)
        self.assertEqual(codigos_de(error, "direccion_organizacion"), ["demasiado_largo"])

    def test_regla_2_telefono_con_el_formato_de_d21(self):
        """Ficha del modelo y D-21: 8 a 15 dígitos, espacios y ``+ - ( )``; lo demás da error en el campo del teléfono."""
        self.modificar(telefono_organizacion="+54 376 400-1000")
        self.assertEqual(guardado().telefono_organizacion, "+54 376 400-1000")
        for telefono in ("abc", "123", "1" * 16):
            with self.subTest(telefono=telefono):
                error = self.errores(telefono_organizacion=telefono)
                self.assertEqual(len(codigos_de(error, "telefono_organizacion")), 1)

    # ---- regla 3: email y CUIT ----

    def test_regla_3_email_por_formato(self):
        """Regla 3: el email se valida por formato."""
        self.modificar(email_organizacion="contacto@vivero.com.ar")
        for email in ("sin-arroba", "a@b", "a b@c.com", "@x.com"):
            with self.subTest(email=email):
                error = self.errores(email_organizacion=email)
                self.assertEqual(codigos_de(error, "email_organizacion"), ["email_invalido"])

    def test_regla_3_cuit_con_o_sin_guiones_se_guarda_sin_guiones(self):
        """Regla 3 y ficha: el CUIT se acepta con o sin guiones y se guarda con los 11 dígitos."""
        for escrito in ("30-71234567-1", "30712345671", " 30 71234567 1 "):
            with self.subTest(escrito=escrito):
                self.modificar(cuit_organizacion=escrito)
                self.assertEqual(guardado().cuit_organizacion, CUIT_VALIDO)

    def test_regla_3_cuit_con_digito_verificador_incorrecto_se_rechaza(self):
        """Regla 3: el dígito verificador se controla (módulo 11, pesos 5,4,3,2,7,6,5,4,3,2)."""
        for cuit in ("30-71234567-2", "30712345670", "11111111111"):
            with self.subTest(cuit=cuit):
                error = self.errores(cuit_organizacion=cuit)
                self.assertEqual(codigos_de(error, "cuit_organizacion"), ["cuit_invalido"])

    def test_regla_3_cuit_con_formato_incorrecto_se_rechaza(self):
        """Regla 3: el CUIT son 11 dígitos; menos, más o letras dan error."""
        for cuit in ("3071234567", "307123456712", "30-7123456A-1"):
            with self.subTest(cuit=cuit):
                error = self.errores(cuit_organizacion=cuit)
                self.assertEqual(codigos_de(error, "cuit_organizacion"), ["cuit_invalido"])

    def test_regla_3_cuit_cuyo_digito_calculado_es_10_se_rechaza_y_11_vale_0(self):
        """Regla 3 (``cuitOk``): si el cálculo da 10 el CUIT no es válido; si da 11 se toma como 0."""
        pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
        base_diez = next(
            f"{n:010d}" for n in range(10**6) if (11 - sum(p * int(d) for p, d in zip(pesos, f"{n:010d}")) % 11) == 10
        )
        base_once = next(
            f"{n:010d}" for n in range(10**6) if (11 - sum(p * int(d) for p, d in zip(pesos, f"{n:010d}")) % 11) == 11
        )
        for verificador in range(10):
            error = self.errores(cuit_organizacion=base_diez + str(verificador))
            self.assertEqual(codigos_de(error, "cuit_organizacion"), ["cuit_invalido"])
        self.modificar(cuit_organizacion=base_once + "0")
        self.assertEqual(guardado().cuit_organizacion, base_once + "0")

    # ---- regla 5: colores ----

    def test_regla_5_colores_con_formato_rrggbb(self):
        """Regla 5 y D-48: cada color es ``#RRGGBB``; otra cosa da error en el campo del color."""
        for color in ("rojo", "#12345", "#1234567", "123456", "#GGGGGG", "javascript:alert(1)"):
            with self.subTest(color=color):
                error = self.errores(color_primario=color)
                self.assertEqual(codigos_de(error, "color_primario"), ["color_formato"])

    def test_regla_5_los_colores_se_cargan_en_orden(self):
        """Regla 5: no se carga el 2.º sin el 1.º, ni el 3.º sin el 2.º, ni el 4.º sin el 3.º; el error va en el color
        cargado fuera de orden."""
        error = self.errores(color_secundario="#112233")
        self.assertEqual(codigos_de(error, "color_secundario"), ["color_fuera_de_orden"])
        error = self.errores(color_primario="#112233", color_terciario="#445566")
        self.assertEqual(codigos_de(error, "color_terciario"), ["color_fuera_de_orden"])
        error = self.errores(color_primario="#112233", color_secundario="#445566", color_cuaternario="#778899")
        self.assertEqual(codigos_de(error, "color_cuaternario"), ["color_fuera_de_orden"])

    def test_regla_5_cuatro_colores_en_orden_se_guardan_en_mayusculas(self):
        """Regla 5 y decisión de la tarea: hasta cuatro colores, guardados en mayúsculas de modo uniforme."""
        self.modificar(color_primario="#2e7d32", color_secundario="#aabbcc", color_terciario="#112233",
                       color_cuaternario="#FFeeDD")
        fila = guardado()
        self.assertEqual([getattr(fila, c) for c in CAMPOS_COLOR], ["#2E7D32", "#AABBCC", "#112233", "#FFEEDD"])

    def test_regla_5_sin_ningun_color_se_usa_la_paleta_del_sistema(self):
        """Regla 5: sin colores el perfil guarda vacío y ``identidad`` no trae color principal."""
        self.modificar(color_primario="#2E7D32")
        self.modificar(color_primario="")
        self.assertEqual(guardado().color_primario, "")
        self.assertEqual(perfil.identidad().color_principal, "")

    # ---- regla 7: todo o nada ----

    def test_regla_7_un_dato_invalido_no_guarda_ninguno_y_marca_todos_los_campos_con_error(self):
        """Regla 7: con tres campos inválidos y uno válido, se devuelven los tres errores juntos y no se guarda ni el válido."""
        antes = PerfilOrganizacion.objects.values().get()
        error = self.errores(nombre_organizacion="", cuit_organizacion="123", email_organizacion="x",
                             direccion_organizacion="Av. Uruguay 2450")
        self.assertEqual(set(error.error_dict), {"nombre_organizacion", "cuit_organizacion", "email_organizacion"})
        self.assertEqual(PerfilOrganizacion.objects.values().get(), antes)
        self.assertEqual(auditorias(), [])

    def test_regla_7_un_campo_desconocido_se_rechaza(self):
        """Un dato que no existe (por ejemplo, ``sitio_web``) es un error de programación: ``TypeError``."""
        with self.assertRaises(TypeError):
            self.modificar(sitio_web="x.com")

    # ---- postcondiciones ----

    def test_post_a_actualiza_solo_los_datos_indicados(self):
        """Postcondición a: se actualizan los datos indicados y lo demás queda igual."""
        self.modificar(email_organizacion="a@b.com")
        self.modificar(nombre_organizacion="Vivero Los Álamos")
        fila = guardado()
        self.assertEqual((fila.nombre_organizacion, fila.email_organizacion), ("Vivero Los Álamos", "a@b.com"))

    def test_post_b_audita_con_el_antes_y_el_despues_de_cada_dato(self):
        """Postcondición b y D-36: un registro con usuario, el perfil como afectado y, de cada dato modificado, su valor
        anterior y su valor nuevo; un opcional vacío va como nulo y no figuran los que no cambiaron."""
        self.modificar(nombre_organizacion="Vivero Los Álamos", cuit_organizacion="30-71234567-1",
                       color_primario="#2e7d32")
        (registro,) = auditorias()
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.detalle, {"cambios": {
            "nombre_organizacion": {"antes": settings.NOMBRE_ORGANIZACION, "despues": "Vivero Los Álamos"},
            "cuit_organizacion": {"antes": None, "despues": CUIT_VALIDO},
            "color_primario": {"antes": None, "despues": "#2E7D32"},
        }})
        self.assertEqual([(a["modelo"], a["id"]) for a in registro.afectados],
                         [("maestros.perfilorganizacion", guardado().pk)])

    def test_post_b_vaciar_un_dato_se_audita_con_despues_nulo(self):
        """Postcondición b: al vaciar un opcional, el «después» es nulo."""
        self.modificar(email_organizacion="a@b.com")
        self.modificar(email_organizacion="")
        self.assertEqual(
            auditorias()[-1].detalle["cambios"], {"email_organizacion": {"antes": "a@b.com", "despues": None}}
        )

    def test_d28_sin_cambios_no_escribe_ni_audita(self):
        """D-28: guardar los mismos datos (con el CUIT con guiones, que se normaliza igual) no audita."""
        self.modificar(cuit_organizacion="30-71234567-1")
        antes = len(auditorias())
        self.modificar(nombre_organizacion=guardado().nombre_organizacion, cuit_organizacion="30-71234567-1")
        self.assertEqual(len(auditorias()), antes)

    # ---- identidad (D-48) ----

    def test_d48_identidad_devuelve_el_nombre_y_el_color_principal(self):
        """D-48: ``identidad`` devuelve ``Identidad(nombre, color_principal)`` del perfil guardado."""
        self.modificar(nombre_organizacion="Vivero Los Álamos", color_primario="#2E7D32")
        self.assertEqual(perfil.identidad(), Identidad("Vivero Los Álamos", "#2E7D32"))

    def test_d48_identidad_sin_fila_o_con_nombre_vacio_es_none_y_no_crea_la_fila(self):
        """D-48: sin fila, o con el nombre vacío, devuelve ``None`` (core usa NOMBRE_ORGANIZACION); no crea la fila."""
        PerfilOrganizacion.objects.update(nombre_organizacion="")
        self.assertIsNone(perfil.identidad())
        PerfilOrganizacion.objects.all().delete()
        self.assertIsNone(perfil.identidad())
        self.assertEqual(PerfilOrganizacion.objects.count(), 0)


@tag("concurrencia")
class AdmModOrgConcurrenciaTests(ConDatosDeMaestros, TransactionTestCase):
    """Bloqueo de la fila única: gana el último y el segundo audita contra lo ya modificado."""

    def setUp(self):
        asegurar_datos_de_maestros()
        self.gerente = crear_gerente()

    def test_regla_7_dos_modificaciones_a_la_vez_gana_la_ultima_y_audita_contra_lo_releido(self):
        """El segundo pedido espera el bloqueo, relee y su «antes» es el «después» del primero; nunca un error 500."""
        resultados = correr_a_la_vez(
            lambda: perfil.modificar_perfil(self.gerente, nombre_organizacion="Vivero A"),
            lambda: perfil.modificar_perfil(self.gerente, nombre_organizacion="Vivero B"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(guardado().nombre_organizacion, "Vivero B")
        self.assertEqual(
            [r.detalle["cambios"]["nombre_organizacion"] for r in auditorias()],
            [{"antes": settings.NOMBRE_ORGANIZACION, "despues": "Vivero A"}, {"antes": "Vivero A", "despues": "Vivero B"}],
        )

    def test_d28_el_segundo_pedido_con_el_mismo_valor_ya_guardado_no_audita(self):
        """D-28 con bloqueo: si el primero ya dejó el valor que pide el segundo, no se audita dos veces."""
        resultados = correr_a_la_vez(
            lambda: perfil.modificar_perfil(self.gerente, nombre_organizacion="Vivero A"),
            lambda: perfil.modificar_perfil(self.gerente, nombre_organizacion="Vivero A"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(len(auditorias()), 1)


class AdmModOrgLogoServicioTests(VaciaImagenesMixin, ConDatosDeMaestros, TestCase):
    """ADM-MOD-ORG regla 4 y D-106 puntos 10 a 13: el logo (cargar, cambiar y quitar) con ``modificar_perfil(actor, logo=...,
    quitar_logo=...)``. Imágenes en memoria; el almacenamiento de las pruebas es InMemoryStorage."""

    def setUp(self):
        super().setUp()
        self.gerente = crear_gerente()

    def modificar(self, **datos):
        """Modifica el perfil como el Gerente y ejecuta los borrados programados para después de confirmar."""
        with self.captureOnCommitCallbacks(execute=True):
            return perfil.modificar_perfil(self.gerente, **datos)

    def errores(self, **datos):
        """La ``ValidationError`` que lanza modificar con ``datos``."""
        return error_de(lambda: self.modificar(**datos))

    def cargar(self, nombre="logo.png", **datos):
        """Carga un logo (por defecto un PNG de 100 × 100) y devuelve el nombre con el que quedó guardado."""
        self.modificar(logo=archivo_de_imagen(nombre, **datos))
        return guardado().logo.name

    def abrir(self, nombre):
        with default_storage.open(nombre) as archivo:
            imagen = Image.open(BytesIO(archivo.read()))
            imagen.load()
        return imagen

    # ---- regla 4: tipo, tamaño y proceso ----

    def test_regla_4_un_logo_apaisado_se_achica_a_512_de_lado_mayor_sin_recortar(self):
        """Regla 4 y D-106 punto 11: 1000 × 400 queda de 512 × 205, en WebP y sin recorte."""
        imagen = self.abrir(self.cargar(tamano=(1000, 400)))
        self.assertEqual((imagen.format, imagen.size), ("WEBP", (512, 205)))

    def test_regla_4_un_logo_chico_no_se_agranda(self):
        """Regla 4 y D-106 punto 11: 300 × 100 queda de 300 × 100."""
        self.assertEqual(self.abrir(self.cargar(tamano=(300, 100))).size, (300, 100))

    def test_regla_4_un_logo_alto_tambien_respeta_el_lado_mayor(self):
        """D-106 punto 11: el lado mayor mide 512 como máximo, sea el ancho o el alto."""
        self.assertEqual(self.abrir(self.cargar(tamano=(400, 1000))).size, (205, 512))

    def test_regla_4_la_transparencia_se_conserva(self):
        """Regla 4 y D-106 punto 11: un PNG con fondo transparente sigue transparente."""
        contenido = imagen_en_bytes("PNG", (80, 40), modo="RGBA", color=(0, 128, 0, 0))
        self.modificar(logo=SimpleUploadedFile("logo.png", contenido))
        imagen = self.abrir(guardado().logo.name).convert("RGBA")
        self.assertEqual(imagen.getpixel((40, 20))[3], 0)

    def test_regla_4_el_nombre_es_logos_uuid4_webp_y_no_el_del_archivo(self):
        """D-106 puntos 7 y 11: ``logos/<uuid4>.webp``; el nombre original no se conserva."""
        nombre = self.cargar(nombre="logo-de-mi-empresa.png")
        self.assertRegex(nombre, r"^logos/[0-9a-f-]{36}\.webp$")
        self.assertNotIn("empresa", nombre)

    def test_regla_4_jpg_png_y_webp_se_aceptan(self):
        """Regla 4: JPG, PNG o WebP."""
        for nombre in ("a.jpg", "b.png", "c.webp"):
            with self.subTest(nombre=nombre):
                self.assertTrue(self.cargar(nombre=nombre).startswith("logos/"))

    def test_regla_4_se_rechaza_lo_que_no_es_jpg_png_o_webp_de_hasta_5_mb(self):
        """Regla 4 y D-106 punto 5: más de 5 MB, un texto con extensión .png, un GIF y un SVG dan error en el campo del logo."""
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        casos = {
            "pesado": (SimpleUploadedFile("l.png", b"0" * (5 * 1024 * 1024 + 1)), "imagen_pesada"),
            "texto": (SimpleUploadedFile("l.png", b"no soy una imagen"), "imagen_no_valida"),
            "gif": (archivo_de_imagen("l.gif", modo="P", color=1), "imagen_formato"),
            "svg": (SimpleUploadedFile("l.svg", svg), "imagen_no_valida"),
        }
        for nombre, (archivo, codigo) in casos.items():
            with self.subTest(caso=nombre):
                error = self.errores(logo=archivo)
                self.assertEqual(set(error.error_dict), {"logo"})
                self.assertEqual(codigos_de(error, "logo"), [codigo])
        self.assertEqual(guardado().logo.name, "")
        self.assertEqual(archivos_guardados("logos"), set())

    # ---- regla 7: todo o nada ----

    def test_regla_7_un_logo_invalido_junto_con_un_nombre_valido_no_guarda_nada(self):
        """Regla 7 y D-106 punto 12: si el logo no es válido, no se guarda ningún dato (tampoco el nombre)."""
        antes = PerfilOrganizacion.objects.values().get()
        error = self.errores(nombre_organizacion="Vivero Nuevo", logo=SimpleUploadedFile("l.png", b"no soy una imagen"))
        self.assertEqual(set(error.error_dict), {"logo"})
        self.assertEqual(PerfilOrganizacion.objects.values().get(), antes)
        self.assertEqual(auditorias(), [])
        self.assertEqual(archivos_guardados("logos"), set())

    def test_regla_7_un_dato_invalido_junto_con_un_logo_valido_no_guarda_ni_el_archivo(self):
        """Regla 7: el archivo se guarda solo si todo es válido; con el nombre vacío no queda ningún archivo."""
        error = self.errores(nombre_organizacion="", logo=archivo_de_imagen("l.png"))
        self.assertEqual(set(error.error_dict), {"nombre_organizacion"})
        self.assertEqual(guardado().logo.name, "")
        self.assertEqual(archivos_guardados("logos"), set())

    def test_regla_7_los_errores_del_logo_y_de_otros_campos_vienen_juntos(self):
        """Regla 7: el error del logo se suma a los de los demás campos, cada uno en el suyo."""
        error = self.errores(nombre_organizacion="", cuit_organizacion="123", logo=SimpleUploadedFile("l.png", b"x"))
        self.assertEqual(set(error.error_dict), {"nombre_organizacion", "cuit_organizacion", "logo"})

    def test_regla_7_nombre_y_logo_validos_se_guardan_juntos(self):
        """Regla 7: los datos y el logo se guardan en una sola operación, con un solo registro de auditoría."""
        self.modificar(nombre_organizacion="Vivero Nuevo", logo=archivo_de_imagen("l.png"))
        self.assertEqual(guardado().nombre_organizacion, "Vivero Nuevo")
        self.assertTrue(guardado().logo.name.startswith("logos/"))
        self.assertEqual(len(auditorias()), 1)

    def test_regla_7_elegir_un_logo_y_quitar_el_logo_a_la_vez_es_un_error(self):
        """Precisión de D-106 (punto 12): no se sabe cuál de las dos cosas se quiso; error en el logo y no se guarda nada."""
        error = self.errores(logo=archivo_de_imagen("l.png"), quitar_logo=True)
        self.assertEqual(codigos_de(error, "logo"), ["logo_y_quitar"])
        self.assertEqual(archivos_guardados("logos"), set())

    # ---- postcondición b: auditoría ----

    def test_post_b_sin_logo_a_con_logo(self):
        """D-106 punto 13: «sin logo» → «con logo»."""
        self.cargar()
        self.assertEqual(auditorias()[-1].detalle["cambios"], {"logo": {"antes": "sin logo", "despues": "con logo"}})

    def test_post_b_con_logo_a_logo_nuevo(self):
        """D-106 punto 13: al reemplazarlo, «con logo» → «logo nuevo»."""
        self.cargar()
        self.cargar()
        self.assertEqual(auditorias()[-1].detalle["cambios"], {"logo": {"antes": "con logo", "despues": "logo nuevo"}})

    def test_post_b_con_logo_a_sin_logo(self):
        """D-106 punto 13: al quitarlo, «con logo» → «sin logo»."""
        self.cargar()
        self.modificar(quitar_logo=True)
        self.assertEqual(auditorias()[-1].detalle["cambios"], {"logo": {"antes": "con logo", "despues": "sin logo"}})
        self.assertEqual(guardado().logo.name, "")

    def test_post_b_no_se_registra_la_imagen_ni_su_nombre(self):
        """Postcondición b y D-106 punto 13: del logo se registra que cambió, no la imagen."""
        self.cargar()
        contenido = str(auditorias()[-1].detalle)
        self.assertNotIn("logos/", contenido)
        self.assertNotIn(".webp", contenido)

    def test_d28_sin_cambios_en_el_logo_no_figura_en_el_registro(self):
        """D-28 y D-106 punto 13: si se modifica otro dato y el logo no cambió, el logo no se menciona."""
        self.cargar()
        self.modificar(nombre_organizacion="Vivero Nuevo")
        self.assertEqual(set(auditorias()[-1].detalle["cambios"]), {"nombre_organizacion"})

    def test_d28_quitar_el_logo_cuando_no_hay_no_audita_ni_cambia(self):
        """D-28: sin logo, «Quitar el logo» no cambia nada y no deja registro."""
        self.modificar(quitar_logo=True)
        self.assertEqual(auditorias(), [])

    def test_d28_guardar_sin_logo_nuevo_conserva_el_que_hay(self):
        """Regla 1 y D-28: guardar los demás datos sin elegir un logo no lo toca."""
        nombre = self.cargar()
        self.modificar(email_organizacion="a@b.com")
        self.assertEqual(guardado().logo.name, nombre)
        self.assertTrue(default_storage.exists(nombre))

    # ---- D-106 punto 7: los archivos ----

    def test_d106_al_cambiar_o_quitar_se_borra_el_anterior_despues_de_confirmar(self):
        """D-106 punto 7: el archivo anterior se borra con la transacción confirmada (no antes); sin huérfanos."""
        anterior = self.cargar()
        with self.captureOnCommitCallbacks(execute=False) as pendientes:
            perfil.modificar_perfil(self.gerente, logo=archivo_de_imagen("otro.png"))
            self.assertTrue(default_storage.exists(anterior))
        for pendiente in pendientes:
            pendiente()
        nuevo = guardado().logo.name
        self.assertFalse(default_storage.exists(anterior))
        self.assertEqual(archivos_guardados("logos"), {nuevo})
        self.modificar(quitar_logo=True)
        self.assertEqual(archivos_guardados("logos"), set())

    def test_d106_si_la_transaccion_se_deshace_el_nuevo_se_borra_y_el_anterior_queda(self):
        """D-106 punto 7: si no se confirma, el archivo nuevo (ya guardado) se borra y el anterior no se toca."""
        anterior = self.cargar()
        with mock.patch.object(PerfilOrganizacion, "save", side_effect=RuntimeError("falla la base")):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError):
                    perfil.modificar_perfil(self.gerente, logo=archivo_de_imagen("otro.png"))
        self.assertEqual(guardado().logo.name, anterior)
        self.assertEqual(archivos_guardados("logos"), {anterior})

    def test_d106_si_la_auditoria_falla_tampoco_queda_el_archivo_nuevo(self):
        """D-22 y D-106 punto 7: auditoría y datos van en la misma transacción; si la auditoría falla, no queda ni el archivo."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError):
                    perfil.modificar_perfil(self.gerente, logo=archivo_de_imagen("otro.png"))
        self.assertEqual(archivos_guardados("logos"), set())

    def test_pre_a_solo_el_gerente_modifica_el_logo_y_no_se_guarda_nada(self):
        """Precondición a y regla 1: cualquier otra cuenta recibe ``PermissionDenied`` y no queda ningún archivo."""
        for actor in (crear_agronomo(), crear_capataz(), crear_administrador(), None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    perfil.modificar_perfil(actor, logo=archivo_de_imagen("l.png"))
        self.assertEqual(archivos_guardados("logos"), set())
        self.assertEqual(guardado().logo.name, "")

    # ---- D-106 punto 15: la identidad ----

    def test_d106_la_identidad_trae_la_url_del_logo_o_none(self):
        """D-106 punto 15: ``identidad()`` devuelve ``logo_url`` (la URL que da el almacenamiento) o ``None`` sin logo."""
        self.assertIsNone(perfil.identidad().logo_url)
        self.cargar()
        identidad = perfil.identidad()
        self.assertEqual(identidad.logo_url, guardado().logo.url)
        self.assertIn("logos/", identidad.logo_url)
        self.assertEqual((identidad.nombre, identidad.color_principal), (guardado().nombre_organizacion, ""))

    def test_d28_quitar_el_logo_sin_logo_no_falla_no_audita_y_no_toca_el_almacenamiento(self):
        """D-28 y D-106 puntos 12 y 13: «Quitar el logo» marcado cuando no hay logo no falla, no registra «sin logo» en la
        auditoría y no llama al almacenamiento (ni para guardar ni para borrar)."""
        with mock.patch("core.imagenes.default_storage") as almacenamiento:
            with self.captureOnCommitCallbacks(execute=True):
                fila = perfil.modificar_perfil(self.gerente, quitar_logo=True)
        self.assertEqual(almacenamiento.mock_calls, [])
        self.assertEqual(fila.logo.name, "")
        self.assertEqual(auditorias(), [])
        self.assertEqual(archivos_guardados("logos"), set())

    def test_d28_quitar_el_logo_sin_logo_junto_con_otro_cambio_audita_solo_el_otro(self):
        """D-106 punto 13: con «Quitar el logo» marcado y sin logo, el registro menciona solo lo que sí cambió."""
        self.modificar(nombre_organizacion="Vivero Nuevo", quitar_logo=True)
        self.assertEqual(set(auditorias()[-1].detalle["cambios"]), {"nombre_organizacion"})

    def test_regla_1_sin_enviar_logo_y_cambiando_otro_campo_el_logo_y_su_archivo_quedan_intactos(self):
        """Regla 1 y D-106 puntos 7 y 12: con ``logo=None`` y otro campo modificado, el logo guardado y su archivo no se tocan:
        no se borra nada, no se guarda nada nuevo y el registro no menciona el logo."""
        nombre = self.cargar()
        with mock.patch("core.imagenes.default_storage", wraps=default_storage) as almacenamiento:
            with self.captureOnCommitCallbacks(execute=True):
                fila = perfil.modificar_perfil(self.gerente, logo=None, email_organizacion="a@b.com")
        self.assertEqual(almacenamiento.method_calls, [])
        self.assertEqual(fila.logo.name, nombre)
        self.assertEqual(guardado().logo.name, nombre)
        self.assertTrue(default_storage.exists(nombre))
        self.assertEqual(archivos_guardados("logos"), {nombre})
        self.assertEqual(auditorias()[-1].detalle["cambios"], {"email_organizacion": {"antes": None, "despues": "a@b.com"}})

    def test_regla_4_el_lado_menor_se_redondea_al_entero_mas_cercano(self):
        """Regla de redondeo (D-106 punto 11): al achicar, el lado mayor pasa a 512 y el menor se proporciona y se redondea al
        entero más cercano. Caso fijo: 1000 × 400 → 512 × 204,8 → 512 × 205."""
        self.assertEqual(self.abrir(self.cargar(tamano=(1000, 400))).size, (512, 205))
