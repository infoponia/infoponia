# Pruebas de USR-ALT-USR (Alta Usuario) y de lo que cita: precondiciones, reglas 1 a 9, postcondiciones
# a y e (SEG-01, SEG-04, SEG-14), D-21 (formato del teléfono), D-22 (auditoría en la misma transacción) y
# D-28 (teléfono de hasta 25 caracteres). Las de servicio llaman a core.servicios.alta_usuario; las de
# vista (integración) usan el cliente de prueba contra las pantallas. Cada prueba arma sus propios datos.
# El servicio se llama a través del módulo (servicios.x) para que, mientras no exista, cada prueba falle
# por separado en vez de romper la importación del archivo.

import json
from html.parser import HTMLParser
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from core import servicios
from core.models import (
    Agronomo,
    Capataz,
    Gerente,
    RegistroAuditoria,
    Tecnico,
    Transportista,
    Usuario,
    Vendedor,
)

CLAVE = "clave-segura-123"
MENSAJE_EMAIL_REPETIDO = "Ya existe una cuenta con ese email."


def crear_gerente(email="gerente@infoponia.com", activo=True):
    """Crea un Gerente con la contraseña de prueba. Solo puede haber uno activo (D-09)."""
    return Gerente.objects.create_user(
        email=email, password=CLAVE, first_name="Gabriela", last_name="Sosa", is_active=activo
    )


def crear_cuenta(clase, email, activo=True):
    """Crea una cuenta del rol de ``clase`` con la contraseña de prueba."""
    return clase.objects.create_user(
        email=email, password=CLAVE, first_name="Nombre", last_name="Apellido", is_active=activo
    )


def datos_validos(**cambios):
    """Datos mínimos válidos para un alta (todo lo que pide la regla 7); ``cambios`` pisa campos."""
    datos = {
        "rol": Usuario.Rol.CAPATAZ,
        "nombre": "Laura",
        "apellido": "Benítez",
        "email": "laura@infoponia.com",
        "telefono": "",
    }
    datos.update(cambios)
    return datos


def errores_de(contexto, campo):
    """Mensajes del campo en un ``ValidationError`` armado por campo."""
    return contexto.exception.message_dict.get(campo, [])


def codigos_de(contexto, campo):
    """Códigos de error del campo en un ``ValidationError`` armado por campo."""
    return [e.code for e in contexto.exception.error_dict.get(campo, [])]


class UsrAltUsrServicioTests(TestCase):
    """Reglas, precondiciones y postcondiciones de USR-ALT-USR en el servicio ``alta_usuario``."""

    def alta(self, actor, **cambios):
        """Llama al servicio con datos válidos, pisados por ``cambios``."""
        return servicios.alta_usuario(actor, **datos_validos(**cambios))

    def assertTelefonoRechazado(self, telefono):
        """El alta con ese teléfono falla en el campo ``telefono`` y no crea ninguna cuenta."""
        # Se llama una vez por teléfono dentro de un mismo test: reutiliza el Gerente si ya existe.
        gerente = Gerente.objects.filter(is_active=True).first() or crear_gerente()
        cuentas_antes = Usuario.objects.count()

        with self.assertRaises(ValidationError) as contexto:
            self.alta(gerente, telefono=telefono)

        self.assertIn("telefono", contexto.exception.message_dict)
        self.assertEqual(Usuario.objects.count(), cuentas_antes)

    # ---- Precondición ----

    def test_pre_a_rechaza_actor_sin_cuenta_activa_de_gerente(self):
        """USR-ALT-USR precondición a: solo da de alta una cuenta activa de Gerente (el Administrador
        llega en la tarea 05). Un Capataz o un Gerente dado de baja no pueden."""
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")
        gerente_inactivo = crear_gerente(activo=False)

        for actor in (capataz, gerente_inactivo):
            with self.subTest(actor=actor.email):
                with self.assertRaises(PermissionDenied):
                    self.alta(actor)
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())

    # ---- Reglas del caso de uso ----

    def test_regla_1_gerente_da_de_alta_los_cinco_roles(self):
        """USR-ALT-USR regla 1: el Gerente da de alta cuentas de Agrónomo, Capataz, Vendedor,
        Transportista y Técnico, cada una con la clase de su rol."""
        gerente = crear_gerente()
        esperado = {
            Usuario.Rol.AGRONOMO: Agronomo,
            Usuario.Rol.CAPATAZ: Capataz,
            Usuario.Rol.VENDEDOR: Vendedor,
            Usuario.Rol.TRANSPORTISTA: Transportista,
            Usuario.Rol.TECNICO: Tecnico,
        }

        for rol, clase in esperado.items():
            with self.subTest(rol=rol):
                cuenta, _ = self.alta(gerente, rol=rol, email=f"{rol}@infoponia.com")
                self.assertIsInstance(cuenta, clase)
                self.assertEqual(Usuario.objects.get(pk=cuenta.pk).rol, rol)

    def test_regla_1_gerente_no_da_de_alta_un_gerente(self):
        """USR-ALT-USR regla 1: el Gerente no da de alta Gerentes (lo hace el Administrador, D-16)."""
        gerente = crear_gerente()

        with self.assertRaises(ValidationError) as contexto:
            self.alta(gerente, rol=Usuario.Rol.GERENTE)

        self.assertIn("rol", contexto.exception.message_dict)
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())

    def test_regla_1_nadie_da_de_alta_un_administrador(self):
        """USR-ALT-USR regla 1 y SEG-17: los Administradores no se dan de alta desde el Sistema."""
        gerente = crear_gerente()

        for rol in ("administrador", "superusuario", "inexistente"):
            with self.subTest(rol=rol):
                with self.assertRaises(ValidationError) as contexto:
                    self.alta(gerente, rol=rol)
                self.assertIn("rol", contexto.exception.message_dict)
        self.assertFalse(Usuario.objects.filter(is_superuser=True).exists())
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())

    def test_regla_3_rechaza_email_repetido(self):
        """USR-ALT-USR regla 3 y precondición b: el email es único entre todas las cuentas."""
        gerente = crear_gerente()
        crear_cuenta(Capataz, "laura@infoponia.com")

        with self.assertRaises(ValidationError) as contexto:
            self.alta(gerente)

        self.assertEqual(errores_de(contexto, "email"), [MENSAJE_EMAIL_REPETIDO])
        self.assertEqual(Usuario.objects.filter(email="laura@infoponia.com").count(), 1)

    def test_regla_3_rechaza_email_repetido_con_otras_mayusculas(self):
        """USR-ALT-USR regla 3 y SEG-01: el email se compara sin distinguir mayúsculas."""
        gerente = crear_gerente()
        crear_cuenta(Capataz, "laura@infoponia.com")

        with self.assertRaises(ValidationError) as contexto:
            self.alta(gerente, email="  LAURA@Infoponia.COM ")

        self.assertEqual(errores_de(contexto, "email"), [MENSAJE_EMAIL_REPETIDO])

    def test_regla_4_genera_contrasena_temporal(self):
        """USR-ALT-USR regla 4 y SEG-04: la contraseña inicial la genera el Sistema, es temporal y
        quien da de alta no la elige: el servicio no recibe ninguna."""
        gerente = crear_gerente()

        cuenta, temporal = self.alta(gerente)

        cuenta.refresh_from_db()
        self.assertEqual(len(temporal), 12)
        self.assertTrue(cuenta.check_password(temporal))
        self.assertTrue(cuenta.tiene_contrasena_temporal)
        self.assertFalse(cuenta.contrasena_temporal_vencida())

    def test_regla_4_no_acepta_contrasena_elegida_por_quien_da_de_alta(self):
        """USR-ALT-USR regla 4: nadie elige la contraseña de otra persona; el servicio no tiene ese
        parámetro."""
        gerente = crear_gerente()

        with self.assertRaises(TypeError):
            servicios.alta_usuario(gerente, **datos_validos(), contrasena="mi-clave-elegida-1")

    def test_regla_7_exige_nombre_apellido_email_y_rol(self):
        """USR-ALT-USR regla 7: son obligatorios el nombre, el apellido, el email y el rol; un valor
        con solo espacios cuenta como vacío."""
        gerente = crear_gerente()

        for campo in ("nombre", "apellido", "email", "rol"):
            for vacio in ("", "   "):
                with self.subTest(campo=campo, valor=vacio):
                    with self.assertRaises(ValidationError) as contexto:
                        self.alta(gerente, **{campo: vacio})
                    self.assertIn(campo, contexto.exception.message_dict)
        self.assertEqual(Usuario.objects.count(), 1)  # solo el Gerente

    def test_regla_7_telefono_es_opcional(self):
        """USR-ALT-USR regla 7: el teléfono es opcional."""
        gerente = crear_gerente()

        cuenta, _ = self.alta(gerente, telefono="")

        self.assertEqual(Usuario.objects.get(pk=cuenta.pk).telefono, "")

    def test_regla_8_email_de_cuenta_inactiva_no_crea_otra(self):
        """USR-ALT-USR regla 8: si el email es de una cuenta inactiva, no se da de alta otra; el error
        lo indica con un código propio y trae la cuenta, para ofrecer reactivarla."""
        gerente = crear_gerente()
        inactiva = crear_cuenta(Capataz, "laura@infoponia.com", activo=False)

        with self.assertRaises(ValidationError) as contexto:
            self.alta(gerente, rol=Usuario.Rol.TECNICO)

        self.assertEqual(codigos_de(contexto, "email"), ["email_de_cuenta_inactiva"])
        error = contexto.exception.error_dict["email"][0]
        self.assertEqual(error.params["cuenta"].pk, inactiva.pk)
        self.assertEqual(Usuario.objects.filter(email="laura@infoponia.com").count(), 1)

    def test_regla_8_email_inactivo_fuera_de_alcance_da_mensaje_generico(self):
        """USR-ALT-USR regla 8 y D-28: si la cuenta inactiva no es una que el Gerente gestione (por
        ejemplo, un Gerente dado de baja), no se dice que está inactiva ni se ofrece reactivarla: el
        mensaje es el genérico."""
        gerente = crear_gerente()
        crear_gerente(email="laura@infoponia.com", activo=False)

        with self.assertRaises(ValidationError) as contexto:
            self.alta(gerente)

        self.assertEqual(errores_de(contexto, "email"), [MENSAJE_EMAIL_REPETIDO])
        self.assertNotIn("email_de_cuenta_inactiva", codigos_de(contexto, "email"))

    def test_regla_9_acepta_telefonos_validos(self):
        """USR-ALT-USR regla 9 y D-21: dígitos, espacios y + - ( ), con el + solo al comienzo y entre
        8 y 15 dígitos."""
        gerente = crear_gerente()
        validos = [
            "+54 376 400-1001",
            "(376) 400 1001",
            "37640010",  # 8 dígitos
            "+54 9 376 400 1001",
            "123456789012345",  # 15 dígitos
        ]

        for indice, telefono in enumerate(validos):
            with self.subTest(telefono=telefono):
                cuenta, _ = self.alta(gerente, email=f"tel{indice}@infoponia.com", telefono=telefono)
                self.assertEqual(Usuario.objects.get(pk=cuenta.pk).telefono, telefono)

    def test_regla_9_rechaza_letras_y_otros_simbolos(self):
        """USR-ALT-USR regla 9 y D-21: solo dígitos, espacios y los símbolos + - ( )."""
        for telefono in ("abc12345678", "376.400.1001", "376/4001001", "376 400 100x"):
            with self.subTest(telefono=telefono):
                self.assertTelefonoRechazado(telefono)

    def test_regla_9_rechaza_mas_que_no_esta_al_comienzo(self):
        """USR-ALT-USR regla 9 y D-21: el + va solo al comienzo."""
        for telefono in ("376+4001001", "54 +3764001001", "++543764001001"):
            with self.subTest(telefono=telefono):
                self.assertTelefonoRechazado(telefono)

    def test_regla_9_rechaza_menos_de_8_o_mas_de_15_digitos(self):
        """USR-ALT-USR regla 9 y D-21: entre 8 y 15 dígitos."""
        for telefono in ("1234567", "+54 376 40", "1234567890123456"):  # 7, 7 y 16 dígitos
            with self.subTest(telefono=telefono):
                self.assertTelefonoRechazado(telefono)

    def test_d28_rechaza_telefono_de_mas_de_25_caracteres(self):
        """D-28 (reemplaza el largo de D-15): el teléfono tiene como máximo 25 caracteres. Este tiene
        14 dígitos y solo símbolos válidos, pero 27 caracteres: el error tiene que nombrar el límite."""
        gerente = crear_gerente()
        telefono = "1 2 3 4 5 6 7 8 9 0 1 2 3 4"

        with self.assertRaises(ValidationError) as contexto:
            self.alta(gerente, telefono=telefono)

        mensajes = errores_de(contexto, "telefono")
        self.assertEqual(len(mensajes), 1)  # un solo error, no uno por validador
        self.assertIn("25", mensajes[0])

    def test_d28_acepta_telefono_de_exactamente_25_caracteres(self):
        """D-28: 25 caracteres es el máximo permitido (borde)."""
        gerente = crear_gerente()
        telefono = "+54 (376) 400-1001 -1 2 3"  # 15 dígitos: cumple también D-21
        self.assertEqual(len(telefono), 25)

        cuenta, _ = self.alta(gerente, telefono=telefono)

        self.assertEqual(Usuario.objects.get(pk=cuenta.pk).telefono, telefono)

    # ---- Postcondiciones ----

    def test_post_a_crea_cuenta_activa_con_rol_y_datos(self):
        """USR-ALT-USR postcondición a: se creó una cuenta activa, con el rol indicado, nombre,
        apellido, email (en minúsculas, SEG-01), teléfono y contraseña temporal."""
        gerente = crear_gerente()

        cuenta, _ = self.alta(
            gerente,
            rol=Usuario.Rol.VENDEDOR,
            nombre=" Laura ",
            apellido=" Benítez ",
            email=" Laura@Infoponia.com ",
            telefono="+54 376 400-1001",
        )

        guardada = Usuario.objects.get(pk=cuenta.pk)
        self.assertTrue(guardada.is_active)
        self.assertEqual(guardada.rol, Usuario.Rol.VENDEDOR)
        self.assertEqual(guardada.first_name, "Laura")
        self.assertEqual(guardada.last_name, "Benítez")
        self.assertEqual(guardada.email, "laura@infoponia.com")
        self.assertEqual(guardada.telefono, "+54 376 400-1001")
        self.assertFalse(guardada.is_superuser)
        self.assertTrue(guardada.tiene_contrasena_temporal)

    def test_post_e_audita_el_alta_sin_contrasena(self):
        """USR-ALT-USR postcondición e, SEG-14 y D-22: queda un registro de auditoría con quién actuó,
        su rol, la acción y la cuenta nueva; no contiene ninguna contraseña."""
        gerente = crear_gerente()

        cuenta, temporal = self.alta(gerente)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.ALTA)
        self.assertEqual(registro.usuario_id, gerente.pk)
        self.assertEqual(registro.rol, "gerente")
        self.assertEqual(registro.afectados, [{"modelo": "core.usuario", "id": cuenta.pk}])
        contenido = json.dumps([registro.afectados, registro.detalle])
        self.assertNotIn(temporal, contenido)
        self.assertNotIn(cuenta.password, contenido)

    def test_d22_alta_rechazada_no_deja_registro_de_auditoria(self):
        """D-22: un alta rechazada no deja registro de auditoría."""
        gerente = crear_gerente()

        with self.assertRaises(ValidationError):
            self.alta(gerente, email="")

        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_d22_si_falla_la_auditoria_no_crea_la_cuenta(self):
        """D-22: la cuenta y su registro de auditoría se guardan en la misma transacción; si falla el
        registro, no queda la cuenta."""
        gerente = crear_gerente()

        with mock.patch.object(
            RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla simulada")
        ):
            with self.assertRaises(RuntimeError):
                self.alta(gerente)

        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())


class _LectorDeSelect(HTMLParser):
    """Lee las opciones del ``<select name=...>`` de una página (valor de cada ``<option>``)."""

    def __init__(self, nombre):
        super().__init__()
        self.nombre = nombre
        self.dentro = False
        self.encontrado = False
        self.valores = []

    def handle_starttag(self, etiqueta, atributos):
        atributos = dict(atributos)
        if etiqueta == "select" and atributos.get("name") == self.nombre:
            self.dentro = self.encontrado = True
        elif etiqueta == "option" and self.dentro:
            self.valores.append(atributos.get("value", ""))

    def handle_endtag(self, etiqueta):
        if etiqueta == "select":
            self.dentro = False


class UsrAltUsrVistaTests(TestCase):
    """Flujo principal de USR-ALT-USR en las pantallas (vAlta y vAltaOk), con el cliente de Django."""

    def entrar_como_gerente(self):
        """Crea un Gerente, abre su sesión y lo devuelve."""
        gerente = crear_gerente()
        self.client.force_login(gerente)
        return gerente

    def enviar_alta(self, **cambios):
        """Envía el formulario de alta con datos válidos pisados por ``cambios``."""
        return self.client.post(reverse("core:usuario_nuevo"), datos_validos(**cambios))

    def test_flujo_principal_da_de_alta_y_muestra_la_temporal(self):
        """USR-ALT-USR flujo principal y postcondiciones a y c: el alta crea la cuenta, muestra «Cuenta
        creada» y le informa a quien la hizo la contraseña temporal, que es la de la cuenta."""
        self.entrar_como_gerente()

        respuesta = self.enviar_alta()

        self.assertEqual(respuesta.status_code, 200)
        cuenta = Usuario.objects.get(email="laura@infoponia.com")
        temporal = respuesta.context["contrasena_temporal"]
        self.assertTrue(cuenta.check_password(temporal))
        self.assertContains(respuesta, "Cuenta creada")
        self.assertContains(respuesta, temporal)
        self.assertContains(respuesta, "Laura Benítez")

    def test_post_c_la_temporal_no_se_vuelve_a_mostrar(self):
        """USR-ALT-USR postcondición c: la temporal se informa una única vez. La respuesta lleva
        «no-store» (el botón «Atrás» no la recupera) y ni la ficha ni la lista la muestran después."""
        self.entrar_como_gerente()

        respuesta = self.enviar_alta()

        temporal = respuesta.context["contrasena_temporal"]
        self.assertIn("no-store", respuesta["Cache-Control"])
        cuenta = Usuario.objects.get(email="laura@infoponia.com")
        for url in (reverse("core:usuario", args=[cuenta.pk]), reverse("core:usuarios")):
            self.assertNotContains(self.client.get(url), temporal)
        self.assertNotIn(temporal, str(self.client.session.items()))

    def test_regla_1_formulario_tiene_select_nativo_con_los_cinco_roles(self):
        """USR-ALT-USR regla 1 y D-24: el formulario tiene un ``<select>`` nativo (es lo que se ve sin
        JavaScript) con los cinco roles y la opción vacía; sin Gerente ni Administrador."""
        self.entrar_como_gerente()

        respuesta = self.client.get(reverse("core:usuario_nuevo"))

        lector = _LectorDeSelect("rol")
        lector.feed(respuesta.content.decode())
        self.assertTrue(lector.encontrado, "no hay un <select name='rol'>")
        self.assertEqual(
            lector.valores, ["", "agronomo", "capataz", "vendedor", "transportista", "tecnico"]
        )

    def test_regla_8_ofrece_reactivar_la_cuenta_inactiva(self):
        """USR-ALT-USR regla 8: si el email es de una cuenta inactiva, no se da de alta otra y la
        pantalla ofrece ir a reactivar esa cuenta."""
        self.entrar_como_gerente()
        inactiva = crear_cuenta(Capataz, "laura@infoponia.com", activo=False)

        respuesta = self.enviar_alta(rol=Usuario.Rol.TECNICO)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "inactiva")
        self.assertContains(respuesta, f'href="{reverse("core:usuario", args=[inactiva.pk])}"')
        self.assertContains(respuesta, "reactivala")
        self.assertEqual(Usuario.objects.filter(email="laura@infoponia.com").count(), 1)

    def test_regla_9_muestra_el_error_del_telefono_al_confirmar(self):
        """USR-ALT-USR regla 9 y D-21: el error del teléfono aparece al confirmar el formulario, junto
        al campo, y no se crea la cuenta. El formulario vacío no muestra errores (no valida al escribir)."""
        self.entrar_como_gerente()

        vacio = self.client.get(reverse("core:usuario_nuevo"))
        respuesta = self.enviar_alta(telefono="12ab")

        self.assertNotContains(vacio, 'class="err"')
        self.assertContains(respuesta, "El teléfono solo puede tener números")
        self.assertContains(respuesta, "Laura")  # conserva lo escrito
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())

    def test_seg13_capataz_recibe_403_en_el_alta(self):
        """SEG-13: un Capataz no abre el formulario ni envía un alta; recibe 403 y no se crea nada."""
        self.client.force_login(crear_cuenta(Capataz, "capataz@infoponia.com"))

        pantalla = self.client.get(reverse("core:usuario_nuevo"))
        envio = self.enviar_alta()

        self.assertEqual(pantalla.status_code, 403)
        self.assertEqual(envio.status_code, 403)
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())
