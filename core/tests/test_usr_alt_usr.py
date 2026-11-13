# Pruebas de USR-ALT-USR (Alta Usuario) y de lo que cita: precondiciones, reglas 1 a 9, postcondiciones
# a y e (SEG-01, SEG-04, SEG-14), D-21 (formato del teléfono), D-22 (auditoría en la misma transacción) y
# D-28 (teléfono de hasta 25 caracteres). Las de servicio llaman a core.servicios.alta_usuario; las de
# vista (integración) usan el cliente de prueba contra las pantallas. Cada prueba arma sus propios datos.
# El servicio se llama a través del módulo (servicios.x) para que, mientras no exista, cada prueba falle
# por separado en vez de romper la importación del archivo.

import json
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from core import servicios
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.models import (
    ADMINISTRADOR,
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


def crear_administrador(email="admin@infoponia.com"):
    """Crea un Administrador técnico: superusuario sin rol (D-10)."""
    return Usuario.objects.create_superuser(
        email=email, password=CLAVE, first_name="Adrián", last_name="Mena"
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
        """USR-ALT-USR precondición a: da de alta una cuenta activa de Gerente o de Administrador (las
        del Administrador están más abajo). Un Capataz o un Gerente dado de baja no pueden."""
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

    # ---- El Administrador (tarea 05a, D-16) ----

    def test_pre_a_rechaza_administrador_inactivo(self):
        """USR-ALT-USR precondición a: un Administrador dado de baja no da de alta un Gerente; no se crea
        nada ni se audita."""
        crear_administrador()
        inactivo = crear_administrador(email="admin.anterior@infoponia.com")
        inactivo.is_active = False
        inactivo.save()

        with self.assertRaises(PermissionDenied):
            self.alta(inactivo, rol=Usuario.Rol.GERENTE)

        self.assertFalse(Gerente.objects.exists())
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_1_administrador_da_de_alta_un_gerente(self):
        """USR-ALT-USR regla 1, postcondiciones a y c, y D-16: el Administrador da de alta la cuenta del
        Gerente, activa y con contraseña temporal, que el servicio devuelve para mostrarla una vez."""
        administrador = crear_administrador()

        cuenta, temporal = self.alta(administrador, rol=Usuario.Rol.GERENTE)

        guardada = Usuario.objects.get(pk=cuenta.pk)
        self.assertIsInstance(cuenta, Gerente)
        self.assertEqual(guardada.rol, Usuario.Rol.GERENTE)
        self.assertTrue(guardada.is_active)
        self.assertFalse(guardada.is_superuser)
        self.assertTrue(guardada.check_password(temporal))
        self.assertTrue(guardada.tiene_contrasena_temporal)

    def test_regla_1_administrador_no_da_de_alta_otros_roles(self):
        """USR-ALT-USR regla 1, D-16 y SEG-17: el Administrador da de alta solo al Gerente; ni los cinco
        roles del Gerente ni otros Administradores."""
        administrador = crear_administrador()
        roles = [rol.value for rol in Usuario.Rol if rol != Usuario.Rol.GERENTE] + [ADMINISTRADOR]

        for rol in roles:
            with self.subTest(rol=rol):
                with self.assertRaises(ValidationError) as contexto:
                    self.alta(administrador, rol=rol)
                self.assertIn("rol", contexto.exception.message_dict)
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())
        self.assertEqual(Usuario.objects.filter(is_superuser=True).count(), 1)

    def test_regla_2_rechaza_alta_de_gerente_con_uno_activo(self):
        """USR-ALT-USR regla 2, precondición c y D-09: con un Gerente activo no se da de alta otro; el
        error es general (código «gerente_activo») y no se crea nada ni se audita."""
        administrador = crear_administrador()
        crear_gerente()

        with self.assertRaises(ValidationError) as contexto:
            self.alta(administrador, rol=Usuario.Rol.GERENTE)

        self.assertEqual(codigos_de(contexto, NON_FIELD_ERRORS), ["gerente_activo"])
        self.assertEqual(Gerente.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_2_permite_alta_de_gerente_con_el_anterior_inactivo(self):
        """USR-ALT-USR regla 2 y D-13: si el Gerente anterior está dado de baja, se da de alta otro."""
        administrador = crear_administrador()
        crear_gerente(email="gerente.anterior@infoponia.com", activo=False)

        cuenta, _ = self.alta(administrador, rol=Usuario.Rol.GERENTE)

        self.assertEqual(
            list(Gerente.objects.filter(is_active=True).values_list("pk", flat=True)), [cuenta.pk]
        )

    def test_regla_3_integrity_error_sin_nombre_de_restriccion_da_email_repetido(self):
        """USR-ALT-USR regla 3 y SEG-15 (D-30): si la base rechaza el alta y no se puede leer qué
        restricción falló (sin causa, sin ``diag`` o sin nombre), se informa como email repetido; nunca
        llega un ``IntegrityError`` a la pantalla (sería un error 500)."""
        administrador = crear_administrador()
        # Django envuelve el error del driver: el de psycopg queda en ``__cause__`` (tiene que ser una
        # excepción) y trae ``diag.constraint_name``. Acá se simulan los tres casos en que falta.
        sin_causa = IntegrityError("falla simulada")
        sin_diag = IntegrityError("falla simulada")
        sin_diag.__cause__ = Exception("error del driver sin diag")
        sin_nombre = IntegrityError("falla simulada")
        sin_nombre.__cause__ = Exception("error del driver sin nombre de restricción")
        sin_nombre.__cause__.diag = SimpleNamespace(constraint_name=None)

        casos = (("sin causa", sin_causa), ("sin diag", sin_diag), ("sin nombre", sin_nombre))
        for nombre, error in casos:
            with self.subTest(caso=nombre):
                with mock.patch.object(Usuario, "save", side_effect=error):
                    with self.assertRaises(ValidationError) as contexto:
                        self.alta(administrador, rol=Usuario.Rol.GERENTE)
                self.assertEqual(errores_de(contexto, "email"), [MENSAJE_EMAIL_REPETIDO])
        self.assertFalse(Gerente.objects.exists())

    def test_regla_8_administrador_recibe_oferta_de_reactivar_gerente_inactivo(self):
        """USR-ALT-USR regla 8 y D-28: si el email es de un Gerente dado de baja (dentro del alcance del
        Administrador), no se da de alta otro: el error ofrece reactivarlo."""
        administrador = crear_administrador()
        inactivo = crear_gerente(email="laura@infoponia.com", activo=False)

        with self.assertRaises(ValidationError) as contexto:
            self.alta(administrador, rol=Usuario.Rol.GERENTE)

        self.assertEqual(codigos_de(contexto, "email"), ["email_de_cuenta_inactiva"])
        self.assertEqual(contexto.exception.error_dict["email"][0].params["cuenta"].pk, inactivo.pk)
        self.assertEqual(Usuario.objects.filter(email="laura@infoponia.com").count(), 1)

    def test_regla_8_email_de_capataz_inactivo_da_mensaje_generico_al_administrador(self):
        """USR-ALT-USR regla 8 y D-28: si la cuenta inactiva no es una que el Administrador gestione (un
        Capataz dado de baja), el mensaje es el genérico y no se ofrece reactivarla."""
        administrador = crear_administrador()
        crear_cuenta(Capataz, "laura@infoponia.com", activo=False)

        with self.assertRaises(ValidationError) as contexto:
            self.alta(administrador, rol=Usuario.Rol.GERENTE)

        self.assertEqual(errores_de(contexto, "email"), [MENSAJE_EMAIL_REPETIDO])
        self.assertNotIn("email_de_cuenta_inactiva", codigos_de(contexto, "email"))

    def test_post_e_audita_alta_de_gerente_con_rol_administrador(self):
        """USR-ALT-USR postcondición e, SEG-14 y D-22: el alta del Gerente queda auditada con el
        Administrador como quien actuó y su rol en ese momento («administrador»), sin contraseñas."""
        administrador = crear_administrador()

        cuenta, temporal = self.alta(administrador, rol=Usuario.Rol.GERENTE)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.ALTA)
        self.assertEqual(registro.usuario_id, administrador.pk)
        self.assertEqual(registro.rol, ADMINISTRADOR)
        self.assertEqual(registro.afectados, [{"modelo": "core.usuario", "id": cuenta.pk}])
        self.assertEqual(registro.detalle["rol"], Usuario.Rol.GERENTE)
        contenido = json.dumps([registro.afectados, registro.detalle])
        self.assertNotIn(temporal, contenido)
        self.assertNotIn(cuenta.password, contenido)


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
        pantalla ofrece «Reactivar cuenta» (que lleva a la confirmación de USR-MOD-USR) y ver esa cuenta.
        Desde la tarea 04b la oferta es el botón de reactivar; antes era un enlace a la ficha."""
        self.entrar_como_gerente()
        inactiva = crear_cuenta(Capataz, "laura@infoponia.com", activo=False)

        respuesta = self.enviar_alta(rol=Usuario.Rol.TECNICO)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "inactiva")
        self.assertContains(
            respuesta,
            f'<a class="btn btn-primary btn-sm" href="{reverse("core:usuario_reactivar", args=[inactiva.pk])}">'
            "Reactivar cuenta</a>",
            html=True,
        )
        self.assertContains(respuesta, f'href="{reverse("core:usuario", args=[inactiva.pk])}"')
        self.assertEqual(Usuario.objects.filter(email="laura@infoponia.com").count(), 1)

    def test_regla_8_reactivar_desde_el_aviso_reactiva_la_cuenta(self):
        """USR-ALT-USR regla 8 y USR-MOD-USR regla 6: el botón del aviso lleva a la confirmación y, al
        confirmarla, la cuenta inactiva queda activa y con una contraseña temporal; no se crea otra."""
        self.entrar_como_gerente()
        inactiva = crear_cuenta(Capataz, "laura@infoponia.com", activo=False)
        aviso = self.enviar_alta(rol=Usuario.Rol.TECNICO)
        self.assertEqual(aviso.status_code, 200)
        url = reverse("core:usuario_reactivar", args=[inactiva.pk])

        confirmacion = self.client.get(url)
        self.assertContains(confirmacion, "¿Reactivar la cuenta?")
        self.assertFalse(Usuario.objects.get(pk=inactiva.pk).is_active)  # abrir la ventana no cambia nada
        resultado = self.client.post(url)

        self.assertContains(resultado, "Cuenta reactivada")
        inactiva.refresh_from_db()
        self.assertTrue(inactiva.is_active)
        self.assertTrue(inactiva.check_password(resultado.context["contrasena_temporal"]))
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

    # ---- El Administrador (tarea 05a, D-16) ----

    def entrar_como_administrador(self):
        """Crea un Administrador, abre su sesión y lo devuelve."""
        administrador = crear_administrador()
        self.client.force_login(administrador)
        return administrador

    def test_flujo_principal_administrador_da_de_alta_un_gerente(self):
        """USR-ALT-USR flujo principal, regla 1, postcondiciones a y c, D-16 y prototipo (vAlta): el
        Administrador ve «Alta de Gerente» con el rol fijo en «Gerente» (deshabilitado); un rol enviado
        a mano se ignora; el alta crea un Gerente y muestra su contraseña temporal."""
        self.entrar_como_administrador()

        pantalla = self.client.get(reverse("core:usuario_nuevo"))
        self.assertContains(pantalla, "<h1>Alta de Gerente</h1>", html=True)
        lector = _LectorDeSelect("rol")
        lector.feed(pantalla.content.decode())
        self.assertEqual(lector.valores, [Usuario.Rol.GERENTE])
        self.assertContains(pantalla, 'name="rol" class="field-input" disabled')

        respuesta = self.enviar_alta(rol=Usuario.Rol.CAPATAZ)

        cuenta = Usuario.objects.get(email="laura@infoponia.com")
        self.assertEqual(cuenta.rol, Usuario.Rol.GERENTE)
        temporal = respuesta.context["contrasena_temporal"]
        self.assertTrue(cuenta.check_password(temporal))
        self.assertContains(respuesta, "Cuenta creada")
        self.assertContains(respuesta, temporal)

    def test_regla_2_con_gerente_activo_no_muestra_el_formulario(self):
        """USR-ALT-USR regla 2, precondición c, D-09 y D-30: con un Gerente activo, la pantalla no muestra
        el formulario (no se completan datos que no se pueden guardar): solo el aviso con el nombre del
        Gerente y dos botones, «Ver a <nombre>» (a su ficha) y «Volver a Cuentas». Un envío manual lo
        rechaza el servicio, vuelve a mostrar lo mismo y no se crea nada."""
        self.entrar_como_administrador()
        gerente = crear_gerente()

        pantalla = self.client.get(reverse("core:usuario_nuevo"))
        envio = self.enviar_alta()

        for respuesta in (pantalla, envio):
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, "Ya hay un Gerente activo: <b>Gabriela Sosa</b>.")
            for campo in ("nombre", "apellido", "email", "telefono", "rol"):
                self.assertNotContains(respuesta, f'name="{campo}"')
            self.assertNotContains(respuesta, "Dar de alta")
            self.assertContains(
                respuesta,
                f'<a class="btn btn-primary" href="{reverse("core:usuario", args=[gerente.pk])}">'
                "Ver a Gabriela Sosa</a>",
                html=True,
            )
            self.assertContains(
                respuesta,
                f'<a class="btn btn-ghost" href="{reverse("core:usuarios")}">Volver a Cuentas</a>',
                html=True,
            )
        self.assertEqual(Gerente.objects.count(), 1)
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_8_administrador_ve_reactivar_y_ver_cuenta_en_el_aviso(self):
        """USR-ALT-USR regla 8 y D-30 (tarea 05b): si el email es de un Gerente dado de baja (y no hay otro
        activo, así que se ve el formulario), el aviso ofrece al Administrador «Reactivar cuenta», porque
        ahora puede hacerlo, y «Ver cuenta»."""
        self.entrar_como_administrador()
        inactivo = crear_gerente(email="laura@infoponia.com", activo=False)

        respuesta = self.enviar_alta()

        self.assertContains(respuesta, "Ese email pertenece a una cuenta <b>inactiva</b>")
        self.assertContains(respuesta, "Gabriela Sosa, Gerente")
        self.assertContains(respuesta, "Reactivar cuenta")
        self.assertContains(respuesta, reverse("core:usuario_reactivar", args=[inactivo.pk]))
        self.assertContains(respuesta, "Ver cuenta")
        self.assertContains(respuesta, reverse("core:usuario", args=[inactivo.pk]))


class UsrAltUsrConcurrenciaTests(TransactionTestCase):
    """SEG-15 en ``alta_usuario``: dos altas de Gerente simultáneas dejan un solo Gerente activo y la
    segunda recibe un rechazo con mensaje, no un error 500. Son ``TransactionTestCase`` porque cada
    operación corre en su propio hilo, con su propia conexión y transacción (ver
    ``core/tests/concurrencia.py``)."""

    def assertQuedaUnSoloGerenteYLaOtraEsRechazada(self, resultados):
        """Una alta sale bien, la otra se rechaza con «gerente_activo» y queda un solo Gerente activo,
        con un solo registro de auditoría de alta."""
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], "ninguna operación puede terminar con un error sin traducir")
        self.assertEqual(len(exitos), 1)
        self.assertEqual(len(rechazos), 1)
        self.assertIn("gerente_activo", codigos(rechazos[0]))
        self.assertEqual(Gerente.objects.filter(is_active=True).count(), 1)
        self.assertEqual(
            RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA).count(), 1
        )

    def altas_simultaneas(self):
        """Dos Administradores dan de alta, a la vez, un Gerente cada uno (con emails distintos)."""
        primero = crear_administrador()
        segundo = crear_administrador(email="admin2@infoponia.com")
        return correr_a_la_vez(
            lambda: servicios.alta_usuario(
                primero, **datos_validos(rol=Usuario.Rol.GERENTE, email="g1@infoponia.com")
            ),
            lambda: servicios.alta_usuario(
                segundo, **datos_validos(rol=Usuario.Rol.GERENTE, email="g2@infoponia.com")
            ),
        )

    def test_seg15_altas_simultaneas_dejan_un_solo_gerente_activo(self):
        """SEG-15, regla 2 de USR-ALT-USR y D-09 (camino del bloqueo): con un Gerente anterior dado de
        baja, la segunda alta espera el bloqueo de las filas de Gerente; cuando la primera confirma, ve
        al Gerente nuevo y se rechaza con el mensaje."""
        crear_gerente(email="gerente.anterior@infoponia.com", activo=False)

        resultados = self.altas_simultaneas()

        self.assertQuedaUnSoloGerenteYLaOtraEsRechazada(resultados)
        # Camino del bloqueo: el rechazo sale de la verificación posterior al bloqueo, no de traducir
        # un error de la base.
        _, rechazos, _ = separar(resultados)
        self.assertIsNone(rechazos[0].__cause__)

    def test_seg15_altas_simultaneas_sin_gerentes_previos_informan_gerente_activo(self):
        """SEG-15, regla 2 de USR-ALT-USR y D-09 (camino de la restricción): sin ningún Gerente previo no
        hay filas que bloquear; la restricción ``un_solo_gerente_activo`` de la base rechaza la segunda
        alta y el servicio lo informa como «gerente_activo» (no como email repetido ni como error 500)."""
        resultados = self.altas_simultaneas()

        self.assertQuedaUnSoloGerenteYLaOtraEsRechazada(resultados)
        # Camino de la restricción: el servicio traduce el IntegrityError con «raise ... from error».
        _, rechazos, _ = separar(resultados)
        self.assertIsInstance(rechazos[0].__cause__, IntegrityError)
