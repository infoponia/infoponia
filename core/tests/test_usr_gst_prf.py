# Pruebas de USR-GST-PRF (Gestionar Mi Perfil), tarea 06a: la pantalla Mi perfil (vPerfil) con el cliente de
# prueba. No hay servicio: la consulta no modifica nada (D-25). La foto de perfil (reglas 1 y 5, SEG-19) es de
# la tarea 07 y las cuentas vinculadas (regla 3, USR-VNC-CTA) de la 06b. El cambio de contraseña desde el perfil
# se prueba en test_usr_cmb_ctr.py. Cada prueba arma sus propios datos.

from io import BytesIO
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from core import extensiones, servicios
from core.extensiones import DatoDeCuenta
from core.models import Agronomo, RegistroAuditoria, Transportista, Usuario
from core.tests.fabricas import (
    CUADRANTES,
    VaciaImagenesMixin,
    agrupar,
    archivo_de_imagen,
    archivos_guardados,
    crear_administrador,
    crear_capataz,
    crear_cuenta,
    crear_gerente,
)


class UsrGstPrfVistaTests(TestCase):
    """Reglas de USR-GST-PRF en la pantalla Mi perfil."""

    def abrir_perfil(self, cuenta):
        """Abre una sesión con ``cuenta`` y devuelve la respuesta de Mi perfil."""
        self.client.force_login(cuenta)
        return self.client.get(reverse("core:mi_perfil"))

    def test_flujo_principal_muestra_los_datos_de_la_cuenta_con_la_que_opera(self):
        """USR-GST-PRF regla 1: nombre, apellido, email, teléfono, rol y estado de la cuenta con la que se opera."""
        agronomo = crear_cuenta(
            Agronomo,
            email="laura@infoponia.com",
            nombre="Laura",
            apellido="Ibáñez",
            telefono="+54 376 400-1001",
        )

        respuesta = self.abrir_perfil(agronomo)

        self.assertEqual(respuesta.status_code, 200)
        for dato in ("Mi perfil", "Laura", "Ibáñez", "laura@infoponia.com", "+54 376 400-1001",
                     "Agrónomo", "Activo"):
            self.assertContains(respuesta, dato)

    def test_regla_1_no_muestra_la_contrasena_ni_su_resumen(self):
        """USR-GST-PRF regla 1 y SEG-02: nunca se muestra la contraseña ni su resumen."""
        capataz = crear_capataz()

        respuesta = self.abrir_perfil(capataz)

        self.assertNotContains(respuesta, capataz.password)
        self.assertNotContains(respuesta, capataz.password.split("$")[0] + "$")

    def test_regla_1_el_administrador_figura_sin_rol_operativo(self):
        """USR-GST-PRF regla 1 y D-10: el Administrador no tiene rol del dominio; se lo indica así."""
        respuesta = self.abrir_perfil(crear_administrador())

        self.assertContains(respuesta, "Administrador (sin rol operativo)")

    def test_regla_2_un_rol_no_ve_modificar_y_sabe_a_quien_pedirselo(self):
        """USR-GST-PRF regla 2: la persona no modifica sus datos desde el perfil; se le dice que se lo pida al
        Gerente que gestiona su cuenta, con su nombre (vPerfil)."""
        crear_gerente(nombre="Gabriela", apellido="Sosa")
        capataz = crear_capataz()

        respuesta = self.abrir_perfil(capataz)

        self.assertContains(respuesta, "Para corregir estos datos, pedíselo al Gerente (Gabriela Sosa).")
        self.assertNotContains(respuesta, "Modificar mis datos")
        self.assertNotContains(respuesta, reverse("core:usuario_modificar", args=[capataz.pk]))

    def test_regla_2_sin_gerente_activo_dice_el_gerente_sin_nombre(self):
        """USR-GST-PRF regla 2 y D-13: entre la baja de un Gerente y el alta del siguiente no hay Gerente
        activo; el perfil igual dice a quién pedírselo, sin nombre."""
        crear_gerente(activo=False)
        capataz = crear_capataz()

        respuesta = self.abrir_perfil(capataz)

        self.assertContains(respuesta, "Para corregir estos datos, pedíselo al Gerente.")

    def test_regla_2_el_gerente_se_lo_pide_al_administrador(self):
        """USR-GST-PRF regla 2 y D-16: los datos del Gerente los corrige el Administrador."""
        respuesta = self.abrir_perfil(crear_gerente())

        self.assertContains(respuesta, "Para corregir estos datos, pedíselo al Administrador.")
        self.assertNotContains(respuesta, "Modificar mis datos")

    def test_regla_2_el_administrador_ve_modificar_mis_datos(self):
        """USR-GST-PRF regla 2 y D-16: el Administrador gestiona su propia cuenta, así que el perfil le ofrece
        modificar sus datos (la pantalla de modificar de «Cuentas»)."""
        administrador = crear_administrador()

        respuesta = self.abrir_perfil(administrador)

        self.assertContains(respuesta, "Modificar mis datos")
        self.assertContains(respuesta, reverse("core:usuario_modificar", args=[administrador.pk]))
        self.assertNotContains(respuesta, "Para corregir estos datos")

    def test_regla_4_la_consulta_no_se_audita(self):
        """USR-GST-PRF regla 4 y SEG-14: consultar el perfil no deja registro de auditoría."""
        self.abrir_perfil(crear_capataz())

        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_seg04_con_temporal_redirige_a_elegir_contrasena(self):
        """SEG-04 y regla 4 de USR-INI-SES: con contraseña temporal no se ve el perfil; se elige primero una
        contraseña propia."""
        capataz = crear_capataz()
        capataz.asignar_contrasena_temporal()
        capataz.save()

        respuesta = self.abrir_perfil(capataz)

        self.assertRedirects(
            respuesta, reverse("core:elegir_contrasena"), fetch_redirect_response=False
        )

    def test_seg13_sin_sesion_redirige_al_inicio_de_sesion(self):
        """Precondición a de USR-GST-PRF y SEG-13: sin sesión no hay perfil; se pide identificarse."""
        respuesta = self.client.get(reverse("core:mi_perfil"))

        self.assertRedirects(
            respuesta,
            f"{reverse('core:iniciar_sesion')}?next={reverse('core:mi_perfil')}",
            fetch_redirect_response=False,
        )

    def test_flujo_principal_en_celular_muestra_volver(self):
        """vPerfil del prototipo («Pantallas»): en celular, Mi perfil tiene un botón «Volver» en la cabecera,
        que lleva al inicio. El inicio no lo tiene."""
        capataz = crear_capataz()

        respuesta = self.abrir_perfil(capataz)

        self.assertContains(respuesta, 'aria-label="Volver al inicio"')
        self.assertNotContains(self.client.get(reverse("core:inicio")), 'aria-label="Volver al inicio"')

    def test_d31_el_menu_de_cuenta_ofrece_mi_perfil_a_todas_las_cuentas(self):
        """D-25 y D-31: el menú de cuenta ofrece «Mi perfil» (tarea 06) y se llama igual para todas las
        cuentas, también para el Administrador: la contraseña está dentro de Mi perfil. El prototipo
        (accountPop) dice «Mi perfil y contraseña» para el Administrador; D-31 se aparta de eso."""
        casos = (
            (crear_capataz(), reverse("core:inicio")),
            (crear_administrador(), reverse("core:usuarios")),
        )
        for cuenta, pantalla in casos:
            with self.subTest(rol=cuenta.rol or "administrador"):
                self.client.force_login(cuenta)
                respuesta = self.client.get(pantalla)
                self.assertContains(respuesta, f'href="{reverse("core:mi_perfil")}"')
                self.assertContains(respuesta, "Mi perfil</a>")
                self.assertNotContains(respuesta, "Mi perfil y contraseña")


class UsrGstPrfDatosDeCuentaTests(TestCase):
    """Regla 1 de USR-GST-PRF (MAE-05, D-55): Mi perfil muestra los datos de solo lectura que registran las apps por
    ``core.extensiones.registrar_datos_de_cuenta`` (el «Invernadero» del Transportista), SIN la nota."""

    def con(self, *funciones):
        """Reemplaza los registrantes de datos de cuenta por ``funciones``."""
        return mock.patch.object(extensiones, "_DATOS_DE_CUENTA", list(funciones))

    def test_regla_1_mi_perfil_muestra_el_dato_sin_la_nota(self):
        """USR-GST-PRF regla 1 y ``fichaDeCuenta``: «Igual en Mi perfil del Transportista, sin la nota»."""
        cuenta = crear_cuenta(Transportista, "transportista@infoponia.com", nombre="Marcos", apellido="Vera")
        dato = DatoDeCuenta("Invernadero", "Norte", "Se asigna desde la ficha del invernadero, en “Logística”.")
        self.client.force_login(cuenta)

        with self.con(lambda c: [dato]):
            respuesta = self.client.get(reverse("core:mi_perfil"))

        self.assertContains(respuesta, "Invernadero")
        self.assertContains(respuesta, "Norte")
        self.assertNotContains(respuesta, "Se asigna desde la ficha del invernadero")

    def test_regla_1_los_registrantes_reciben_la_cuenta_con_la_que_se_opera(self):
        """Contrato: ``funcion(cuenta)`` con la cuenta de la sesión."""
        cuenta = crear_cuenta(Transportista, "transportista@infoponia.com", nombre="Marcos", apellido="Vera")
        self.client.force_login(cuenta)
        recibidas = []

        with self.con(lambda c: recibidas.append(c.pk) or []):
            self.client.get(reverse("core:mi_perfil"))

        self.assertEqual(recibidas, [cuenta.pk])

    def test_regla_1_sin_registrantes_mi_perfil_no_muestra_el_dato(self):
        """Sin registrantes, Mi perfil queda como antes."""
        cuenta = crear_cuenta(Transportista, "transportista@infoponia.com", nombre="Marcos", apellido="Vera")
        self.client.force_login(cuenta)

        with self.con():
            respuesta = self.client.get(reverse("core:mi_perfil"))

        self.assertNotContains(respuesta, "Sin invernadero")

    def test_regla_1_el_dato_se_muestra_tambien_en_el_marco_angosto_del_transportista(self):
        """Interfaz (D-25): el Transportista usa el marco angosto; Mi perfil sigue mostrando el dato."""
        cuenta = crear_cuenta(Transportista, "transportista@infoponia.com", nombre="Marcos", apellido="Vera")
        self.client.force_login(cuenta)
        with self.con(lambda c: [DatoDeCuenta("Invernadero", "Sin invernadero", "")]):
            respuesta = self.client.get(reverse("core:mi_perfil"))
        self.assertContains(respuesta, "Sin invernadero")


class UsrGstPrfFotoServicioTests(VaciaImagenesMixin, TestCase):
    """Foto de perfil (USR-GST-PRF regla 5, SEG-19, D-20 y D-106): cargar, cambiar y quitar la propia con
    ``cambiar_foto_perfil`` y ``quitar_foto_perfil``. Sin auditoría (regla 4, SEG-14)."""

    def setUp(self):
        super().setUp()
        self.cuenta = crear_capataz()

    def foto_de(self, cuenta):
        """El nombre guardado de la foto de ``cuenta``, leído de la base."""
        return Usuario.objects.get(pk=cuenta.pk).foto_perfil.name

    def cargar(self, cuenta=None, **datos):
        """Carga una foto a ``cuenta`` (por defecto, la de la prueba) y devuelve su nombre."""
        cuenta = cuenta or self.cuenta
        with self.captureOnCommitCallbacks(execute=True):
            servicios.cambiar_foto_perfil(cuenta, archivo_de_imagen("f.jpg", **datos))
        return self.foto_de(cuenta)

    def test_regla_5_carga_una_foto_de_256_por_256_en_webp(self):
        """USR-GST-PRF regla 5, SEG-19 y D-106: la foto queda recortada en cuadrado y achicada a 256 × 256, en WebP."""
        nombre = self.cargar(tamano=(800, 600))
        self.assertRegex(nombre, r"^fotos_perfil/[0-9a-f-]{36}\.webp$")
        with default_storage.open(nombre) as archivo:
            imagen = Image.open(BytesIO(archivo.read()))
        self.assertEqual((imagen.format, imagen.size), ("WEBP", (256, 256)))

    def test_d106_una_foto_chica_no_se_agranda(self):
        """D-20 («la achica») y precisión de D-106: una foto de 100 × 80 se recorta en cuadrado y sale de 80 × 80."""
        nombre = self.cargar(tamano=(100, 80))
        with default_storage.open(nombre) as archivo:
            self.assertEqual(Image.open(BytesIO(archivo.read())).size, (80, 80))

    def test_post_a_la_instancia_queda_con_la_foto_nueva(self):
        """USR-GST-PRF postcondición a: la cuenta quedó con la foto nueva (también el objeto que se pasó)."""
        servicios.cambiar_foto_perfil(self.cuenta, archivo_de_imagen("f.png"))
        self.assertTrue(self.cuenta.foto_perfil.name.startswith("fotos_perfil/"))
        self.assertEqual(self.cuenta.foto_perfil.name, self.foto_de(self.cuenta))

    def test_d106_al_cambiar_se_borra_la_anterior_despues_de_confirmar(self):
        """D-106 punto 7: el archivo anterior se borra con la transacción confirmada, no antes."""
        anterior = self.cargar()
        with self.captureOnCommitCallbacks(execute=False) as pendientes:
            servicios.cambiar_foto_perfil(self.cuenta, archivo_de_imagen("g.png"))
            self.assertTrue(default_storage.exists(anterior))  # todavía no
        for pendiente in pendientes:
            pendiente()
        nueva = self.foto_de(self.cuenta)
        self.assertNotEqual(nueva, anterior)
        self.assertFalse(default_storage.exists(anterior))
        self.assertTrue(default_storage.exists(nueva))
        self.assertEqual(archivos_guardados(), {nueva})

    def test_d106_si_la_transaccion_se_deshace_la_anterior_queda_y_la_nueva_se_borra(self):
        """D-106 punto 7: si no se confirma, el archivo anterior no se borra y el nuevo (ya guardado) no queda huérfano."""
        anterior = self.cargar()
        with mock.patch.object(Usuario, "save", side_effect=RuntimeError("falla la base")):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError):
                    servicios.cambiar_foto_perfil(self.cuenta, archivo_de_imagen("g.png"))
        self.assertEqual(self.foto_de(self.cuenta), anterior)
        self.assertEqual(archivos_guardados(), {anterior})

    def test_regla_5_una_imagen_no_valida_no_cambia_nada(self):
        """SEG-19 y D-106 punto 5: un archivo que no es imagen se rechaza (``ValidationError``) y la foto anterior sigue."""
        anterior = self.cargar()
        falso = SimpleUploadedFile("f.jpg", b"no soy una imagen")
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValidationError) as contexto:
                servicios.cambiar_foto_perfil(self.cuenta, falso)
        self.assertEqual(contexto.exception.code, "imagen_no_valida")
        self.assertEqual(self.foto_de(self.cuenta), anterior)
        self.assertEqual(archivos_guardados(), {anterior})

    def test_regla_5_quitar_deja_la_cuenta_sin_foto_y_borra_el_archivo(self):
        """USR-GST-PRF postcondición a y D-106 punto 7: quitar deja la cuenta sin foto y borra el archivo (al confirmar)."""
        self.cargar()
        with self.captureOnCommitCallbacks(execute=True):
            servicios.quitar_foto_perfil(self.cuenta)
        self.assertEqual(self.foto_de(self.cuenta), "")
        self.assertEqual(archivos_guardados(), set())

    def test_regla_5_quitar_sin_foto_no_hace_nada(self):
        """Quitar una foto que no hay no falla ni cambia nada."""
        with self.captureOnCommitCallbacks(execute=True):
            servicios.quitar_foto_perfil(self.cuenta)
        self.assertEqual(self.foto_de(self.cuenta), "")

    def test_d106_si_quitar_se_deshace_el_archivo_queda(self):
        """D-106 punto 7: quitar dentro de una transacción que se deshace no borra el archivo."""
        nombre = self.cargar()
        with mock.patch.object(Usuario, "save", side_effect=RuntimeError("falla la base")):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError):
                    servicios.quitar_foto_perfil(self.cuenta)
        self.assertEqual(self.foto_de(self.cuenta), nombre)
        self.assertTrue(default_storage.exists(nombre))

    def test_regla_4_ni_la_carga_ni_la_quita_se_auditan(self):
        """USR-GST-PRF regla 4, SEG-14 y D-20: el cambio de foto no genera registro de auditoría."""
        antes = RegistroAuditoria.objects.count()
        self.cargar()
        self.cargar()
        with self.captureOnCommitCallbacks(execute=True):
            servicios.quitar_foto_perfil(self.cuenta)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_regla_5_la_foto_es_por_cuenta_y_no_se_comparte_con_las_vinculadas(self):
        """USR-GST-PRF regla 5 y D-20: la foto de una cuenta no pasa a sus cuentas vinculadas."""
        otra = crear_cuenta(Agronomo, email="otra@infoponia.com")
        agrupar(self.cuenta, otra)
        self.cargar()
        self.assertEqual(self.foto_de(otra), "")

    def test_pre_a_una_cuenta_inactiva_no_cambia_su_foto(self):
        """USR-GST-PRF precondición a: solo con una cuenta identificada y activa (SEG-13)."""
        inactiva = crear_cuenta(Agronomo, email="baja@infoponia.com", activo=False)
        with self.assertRaises(PermissionDenied):
            servicios.cambiar_foto_perfil(inactiva, archivo_de_imagen("f.png"))
        with self.assertRaises(PermissionDenied):
            servicios.quitar_foto_perfil(inactiva)
        self.assertEqual(archivos_guardados(), set())

    def test_regla_5_el_administrador_tambien_tiene_foto(self):
        """USR-GST-PRF regla 5: cada cuenta, también la del Administrador, puede cargar su foto."""
        admin = crear_administrador()
        servicios.cambiar_foto_perfil(admin, archivo_de_imagen("f.png"))
        self.assertTrue(self.foto_de(admin).startswith("fotos_perfil/"))

    def test_regla_5_el_gerente_carga_su_foto(self):
        """USR-GST-PRF regla 5: la carga vale para cualquier rol del dominio."""
        gerente = crear_gerente()
        servicios.cambiar_foto_perfil(gerente, archivo_de_imagen("f.png"))
        self.assertTrue(self.foto_de(gerente).startswith("fotos_perfil/"))


class UsrGstPrfFotoVistaTests(VaciaImagenesMixin, TestCase):
    """Mi perfil con la foto (USR-GST-PRF reglas 1 y 5, SEG-19): cargar, cambiar y quitar con el cliente de prueba."""

    def setUp(self):
        super().setUp()
        self.cuenta = crear_capataz()
        self.client.force_login(self.cuenta)

    def subir(self, campo="foto", **datos):
        """POST a ``mi-perfil/foto/`` con una imagen en ``campo``, siguiendo la redirección."""
        return self.client.post(
            reverse("core:cambiar_mi_foto"), {campo: archivo_de_imagen("f.jpg", **datos)}, follow=True
        )

    def foto(self):
        return Usuario.objects.get(pk=self.cuenta.pk).foto_perfil.name

    def test_flujo_principal_sin_foto_ofrece_elegirla_y_muestra_la_sigla(self):
        """USR-GST-PRF regla 5: sin foto, el avatar lleva la sigla del rol y se ofrece «Elegir foto» (no «Quitar»)."""
        respuesta = self.client.get(reverse("core:mi_perfil"))
        self.assertContains(respuesta, "Elegir foto")
        self.assertContains(respuesta, "Tomar foto")
        self.assertContains(respuesta, 'enctype="multipart/form-data"')
        self.assertContains(respuesta, 'name="foto"')
        self.assertContains(respuesta, 'capture="user"')
        self.assertContains(respuesta, "JPG, PNG o WebP, de hasta 5 MB")
        self.assertNotContains(respuesta, 'class="avatar photo"')
        self.assertNotContains(respuesta, "form-quitar-foto")

    def test_flujo_principal_carga_la_foto_y_se_ve_en_el_perfil_y_en_el_encabezado(self):
        """USR-GST-PRF reglas 1 y 5: se carga, se avisa, y el avatar de Mi perfil y el del encabezado muestran la foto."""
        respuesta = self.subir(tamano=(600, 400))
        self.assertRedirects(respuesta, reverse("core:mi_perfil"))
        self.assertContains(respuesta, "Foto de perfil actualizada.")
        nombre = self.foto()
        self.assertRegex(nombre, r"^fotos_perfil/[0-9a-f-]{36}\.webp$")
        html = respuesta.content.decode()
        self.assertEqual(html.count('class="avatar photo"'), 2)  # Mi perfil y el encabezado
        self.assertContains(respuesta, "Cambiar foto")
        self.assertContains(respuesta, 'id="form-quitar-foto"')
        self.assertIn(nombre.split("/")[1], html)

    def test_flujo_principal_la_camara_del_celular_envia_por_su_propio_campo(self):
        """USR-GST-PRF regla 5: la foto se carga desde un archivo o desde la cámara (``foto_camara``)."""
        respuesta = self.subir(campo="foto_camara")
        self.assertContains(respuesta, "Foto de perfil actualizada.")
        self.assertTrue(self.foto().startswith("fotos_perfil/"))

    def test_flujo_principal_cambiar_reemplaza_la_foto(self):
        """USR-GST-PRF regla 5: cambiar deja una sola foto, la nueva; el archivo anterior ya no está."""
        self.subir()
        anterior = self.foto()
        with self.captureOnCommitCallbacks(execute=True):
            self.subir()
        self.assertNotEqual(self.foto(), anterior)
        self.assertEqual(archivos_guardados(), {self.foto()})

    def test_flujo_principal_quitar_deja_la_cuenta_sin_foto(self):
        """USR-GST-PRF regla 5: «Quitar» vuelve a la sigla y borra el archivo."""
        self.subir()
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(reverse("core:quitar_mi_foto"), follow=True)
        self.assertRedirects(respuesta, reverse("core:mi_perfil"))
        self.assertContains(respuesta, "Se quitó la foto de perfil.")
        self.assertNotContains(respuesta, 'class="avatar photo"')
        self.assertEqual(self.foto(), "")
        self.assertEqual(archivos_guardados(), set())

    def test_ext_archivos_no_validos_avisan_el_motivo_y_no_cambian_la_foto(self):
        """SEG-19 y D-106 punto 5: más de 5 MB, un texto con extensión .jpg y un GIF se rechazan con su motivo."""
        casos = {
            "pesado": (SimpleUploadedFile("g.jpg", b"0" * (5 * 1024 * 1024 + 1)), "La imagen pesa más de 5 MB"),
            "texto": (SimpleUploadedFile("g.jpg", b"no soy una imagen"), "No se pudo abrir ese archivo como imagen"),
            "gif": (archivo_de_imagen("g.gif", modo="P", color=1), "Solo se aceptan imágenes JPG, PNG o WebP"),
        }
        for nombre, (archivo, mensaje) in casos.items():
            with self.subTest(caso=nombre):
                respuesta = self.client.post(reverse("core:cambiar_mi_foto"), {"foto": archivo}, follow=True)
                self.assertRedirects(respuesta, reverse("core:mi_perfil"))
                self.assertContains(respuesta, mensaje)
                self.assertEqual(self.foto(), "")

    def test_ext_sin_archivo_pide_elegir_una_imagen(self):
        """Un envío sin archivo no cambia nada y avisa."""
        respuesta = self.client.post(reverse("core:cambiar_mi_foto"), {}, follow=True)
        self.assertContains(respuesta, "Elegí una imagen para tu foto de perfil.")
        self.assertEqual(self.foto(), "")

    def test_ext_un_get_vuelve_a_mi_perfil_y_no_cambia_nada(self):
        """Como el cambio de contraseña: abrir la dirección con un GET no hace nada y vuelve a Mi perfil."""
        for nombre in ("core:cambiar_mi_foto", "core:quitar_mi_foto"):
            with self.subTest(nombre=nombre):
                self.assertRedirects(self.client.get(reverse(nombre)), reverse("core:mi_perfil"))

    def test_regla_5_la_foto_es_siempre_la_de_la_cuenta_con_la_que_se_opera(self):
        """USR-GST-PRF regla 5: un ``cuenta_id`` o ``id`` enviado a mano no cambia la foto de otra cuenta."""
        otra = crear_cuenta(Agronomo, email="otra@infoponia.com")
        self.client.post(
            reverse("core:cambiar_mi_foto"), {"foto": archivo_de_imagen("f.png"), "cuenta_id": otra.pk, "id": otra.pk}
        )
        self.assertEqual(Usuario.objects.get(pk=otra.pk).foto_perfil.name, "")
        self.assertTrue(self.foto().startswith("fotos_perfil/"))

    def test_regla_5_la_foto_no_pasa_a_las_cuentas_vinculadas(self):
        """USR-GST-PRF regla 5 y D-20: la cuenta vinculada sigue con su sigla; la foto no se comparte."""
        otra = crear_cuenta(Agronomo, email="otra@infoponia.com")
        agrupar(self.cuenta, otra)
        self.subir()
        self.assertEqual(Usuario.objects.get(pk=otra.pk).foto_perfil.name, "")
        self.client.force_login(otra)
        self.assertNotContains(self.client.get(reverse("core:mi_perfil")), 'class="avatar photo"')

    def test_seg13_sin_sesion_va_al_inicio_de_sesion(self):
        """SEG-13: sin sesión no se llega a la foto."""
        self.client.logout()
        for nombre in ("core:cambiar_mi_foto", "core:quitar_mi_foto"):
            with self.subTest(nombre=nombre):
                respuesta = self.client.post(reverse(nombre), {"foto": archivo_de_imagen("f.png")})
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn(reverse("core:iniciar_sesion"), respuesta["Location"])
        self.assertEqual(self.foto(), "")

    def test_seg04_con_contrasena_temporal_se_pide_elegir_la_contrasena_primero(self):
        """SEG-04: con una contraseña temporal solo se puede elegir una propia; la foto espera."""
        self.cuenta.asignar_contrasena_temporal()
        self.cuenta.save()
        self.client.force_login(self.cuenta)  # cambió el resumen de la contraseña: se vuelve a abrir la sesión
        respuesta = self.client.post(reverse("core:cambiar_mi_foto"), {"foto": archivo_de_imagen("f.png")})
        self.assertRedirects(respuesta, reverse("core:elegir_contrasena"), fetch_redirect_response=False)
        self.assertEqual(self.foto(), "")

    def test_regla_5_el_administrador_carga_su_foto_y_se_ve_en_su_encabezado(self):
        """USR-GST-PRF regla 5: el Administrador, que no tiene menú de módulos, también ve su foto."""
        admin = crear_administrador()
        self.client.force_login(admin)
        respuesta = self.client.post(reverse("core:cambiar_mi_foto"), {"foto": archivo_de_imagen("f.png")}, follow=True)
        self.assertContains(respuesta, "Foto de perfil actualizada.")
        self.assertContains(respuesta, 'class="avatar photo"')

    def test_regla_5_el_nombre_de_la_foto_no_revela_nada_de_la_persona(self):
        """D-106 punto 7: el archivo se llama como un uuid4 y el aviso y la página no muestran el nombre original."""
        archivo = archivo_de_imagen("mi-foto-de-vacaciones-con-mi-nombre.jpg")
        respuesta = self.client.post(reverse("core:cambiar_mi_foto"), {"foto": archivo}, follow=True)
        self.assertNotContains(respuesta, "vacaciones")
        self.assertNotIn("vacaciones", self.foto())


class UsrGstPrfFotoRecorteServicioTests(VaciaImagenesMixin, TestCase):
    """Editor de encuadre (precisión de D-106): ``cambiar_foto_perfil(usuario, archivo, recorte=(x, y, lado))`` guarda la zona
    pedida; un recorte inválido o una foto de menos de 64 px no guarda nada y la foto anterior sigue."""

    def setUp(self):
        super().setUp()
        self.cuenta = crear_capataz()

    def foto_de(self):
        return Usuario.objects.get(pk=self.cuenta.pk).foto_perfil.name

    def imagen(self, **datos):
        return archivo_de_imagen("f.png", tamano=(400, 300), cuadrantes=CUADRANTES, **datos)

    def color_guardado(self, x, y):
        with default_storage.open(self.foto_de()) as archivo:
            return Image.open(BytesIO(archivo.read())).convert("RGB").getpixel((x, y))

    def test_regla_5_con_recorte_guarda_la_zona_pedida(self):
        """USR-GST-PRF regla 5 y precisión de D-106: la foto guardada es la zona elegida (no solo del tamaño correcto)."""
        for recorte, esperado in (((0, 0, 150), CUADRANTES[0]), ((200, 150, 150), CUADRANTES[3])):
            with self.subTest(recorte=recorte):
                with self.captureOnCommitCallbacks(execute=True):
                    servicios.cambiar_foto_perfil(self.cuenta, self.imagen(), recorte=recorte)
                self.assertTrue(all(abs(a - b) <= 60 for a, b in zip(self.color_guardado(75, 75), esperado)))
        self.assertEqual(len(archivos_guardados()), 1)

    def test_regla_5_sin_recorte_es_central_como_hoy(self):
        """Sin coordenadas (el camino sin JavaScript), recorte central y 256 × 256."""
        with self.captureOnCommitCallbacks(execute=True):
            servicios.cambiar_foto_perfil(self.cuenta, self.imagen())
        with default_storage.open(self.foto_de()) as archivo:
            self.assertEqual(Image.open(BytesIO(archivo.read())).size, (256, 256))

    def test_regla_5_un_recorte_invalido_no_cambia_nada_y_no_deja_archivos(self):
        """Todo o nada: con cada recorte inválido, ``ValidationError`` con su código, la foto anterior sigue y no queda ningún archivo nuevo."""
        with self.captureOnCommitCallbacks(execute=True):
            servicios.cambiar_foto_perfil(self.cuenta, self.imagen())
        anterior = self.foto_de()
        casos = {
            "recorte_incompleto": (10, None, 100),
            "recorte_no_numerico": ("a", 0, 100),
            "recorte_negativo": (-1, 0, 100),
            "recorte_chico": (0, 0, 63),
            "recorte_mayor_que_la_imagen": (0, 0, 301),
            "recorte_fuera_de_la_imagen": (301, 0, 100),
        }
        for codigo, recorte in casos.items():
            with self.subTest(codigo=codigo):
                with self.captureOnCommitCallbacks(execute=True):
                    with self.assertRaises(ValidationError) as contexto:
                        servicios.cambiar_foto_perfil(self.cuenta, self.imagen(), recorte=recorte)
                self.assertEqual(contexto.exception.code, codigo)
                self.assertEqual(self.foto_de(), anterior)
                self.assertEqual(archivos_guardados(), {anterior})

    def test_regla_5_una_foto_de_menos_de_64_px_se_rechaza_con_y_sin_recorte(self):
        """Mínimo general de 64 px (precisión de D-106): ``imagen_chica`` con y sin coordenadas; no se guarda nada."""
        for recorte in (None, (0, 0, 60)):
            with self.subTest(recorte=recorte):
                with self.assertRaises(ValidationError) as contexto:
                    servicios.cambiar_foto_perfil(self.cuenta, archivo_de_imagen("f.png", tamano=(50, 50)), recorte=recorte)
                self.assertEqual(contexto.exception.code, "imagen_chica")
        self.assertEqual(self.foto_de(), "")
        self.assertEqual(archivos_guardados(), set())


class UsrGstPrfFotoRecorteVistaTests(VaciaImagenesMixin, TestCase):
    """Editor de encuadre en Mi perfil (precisión de D-106): la vista lee ``recorte_x``, ``recorte_y`` y ``recorte_lado`` del POST."""

    def setUp(self):
        super().setUp()
        self.cuenta = crear_capataz()
        self.client.force_login(self.cuenta)

    def foto(self):
        return Usuario.objects.get(pk=self.cuenta.pk).foto_perfil.name

    def enviar(self, recorte=None, **datos):
        cuerpo = {"foto": archivo_de_imagen("f.png", tamano=(400, 300), cuadrantes=CUADRANTES, **datos)}
        if recorte is not None:
            cuerpo |= dict(zip(("recorte_x", "recorte_y", "recorte_lado"), recorte))
        return self.client.post(reverse("core:cambiar_mi_foto"), cuerpo, follow=True)

    def color(self, x, y):
        with default_storage.open(self.foto()) as archivo:
            return Image.open(BytesIO(archivo.read())).convert("RGB").getpixel((x, y))

    def test_flujo_principal_con_coordenadas_guarda_la_zona_elegida(self):
        """Con los tres valores en el POST (lo que arma el editor), la foto es esa zona: el cuadrante azul (0, 150, 150)."""
        respuesta = self.enviar(recorte=("0", "150", "150"))
        self.assertContains(respuesta, "Foto de perfil actualizada.")
        self.assertTrue(all(abs(a - b) <= 60 for a, b in zip(self.color(75, 75), CUADRANTES[2])))

    def test_flujo_principal_sin_coordenadas_es_el_recorte_central(self):
        """El camino sin JavaScript: sin los ocultos, recorte central; también con los ocultos vacíos."""
        for recorte in (None, ("", "", "")):
            with self.subTest(recorte=recorte):
                respuesta = self.enviar(recorte=recorte)
                self.assertContains(respuesta, "Foto de perfil actualizada.")
        with default_storage.open(self.foto()) as archivo:
            self.assertEqual(Image.open(BytesIO(archivo.read())).size, (256, 256))

    def test_ext_coordenadas_invalidas_o_incompletas_avisan_y_no_cambian_la_foto(self):
        """Recortes inválidos: aviso con el motivo, la foto actual no cambia y no queda ningún archivo nuevo."""
        self.enviar()
        anterior = self.foto()
        casos = {
            "incompleto": (("10", "", "100"), "Faltan datos del encuadre"),
            "no numérico": (("a", "0", "100"), "no son números"),
            "negativo": (("-1", "0", "100"), "adentro de la imagen"),
            "chico": (("0", "0", "63"), "demasiado chico"),
            "mayor": (("0", "0", "301"), "más grande que la imagen"),
            "afuera": (("301", "0", "100"), "adentro de la imagen"),
        }
        for nombre, (recorte, mensaje) in casos.items():
            with self.subTest(caso=nombre):
                with self.captureOnCommitCallbacks(execute=True):
                    respuesta = self.enviar(recorte=recorte)
                self.assertRedirects(respuesta, reverse("core:mi_perfil"))
                self.assertContains(respuesta, mensaje)
                self.assertEqual(self.foto(), anterior)
                self.assertEqual(archivos_guardados(), {anterior})

    def test_ext_una_foto_de_menos_de_64_px_avisa_el_motivo(self):
        """Mínimo de 64 px: aviso «La foto es demasiado chica…» con y sin coordenadas; no cambia nada."""
        for recorte in (None, ("0", "0", "40")):
            with self.subTest(recorte=recorte):
                respuesta = self.client.post(
                    reverse("core:cambiar_mi_foto"),
                    {"foto": archivo_de_imagen("f.png", tamano=(50, 50))} | (dict(zip(("recorte_x", "recorte_y", "recorte_lado"), recorte)) if recorte else {}),
                    follow=True,
                )
                self.assertContains(respuesta, "demasiado chica")
        self.assertEqual(self.foto(), "")

    def test_flujo_principal_la_pantalla_trae_el_editor_y_el_respaldo_sin_javascript(self):
        """Mi perfil trae los tres ocultos, la ventana del editor (en un ``<template>``), los botones de zoom y «Guardar foto»,
        el texto nuevo y el ``<noscript>`` del camino sin JavaScript."""
        html = self.client.get(reverse("core:mi_perfil")).content.decode()
        for nombre in ("recorte_x", "recorte_y", "recorte_lado"):
            self.assertIn(f'<input type="hidden" name="{nombre}"', html)
        self.assertIn("<template", html)
        self.assertIn("data-encuadre", html)
        for texto in ("Encuadrá tu foto", "Guardar foto", "Cancelar", 'aria-label="Alejar"', 'aria-label="Acercar"',
                      "Arrastrá la foto o usá las flechas", "Al elegirla, la encuadrás en el círculo."):
            self.assertIn(texto, html)
        self.assertRegex(html, r"<noscript>\s*<button[^>]*>Guardar foto</button>\s*</noscript>")
        self.assertIn("encuadre_foto.js", html)
