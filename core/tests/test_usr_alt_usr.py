# Pruebas de USR-ALT-USR (Alta Usuario) y de lo que cita: precondiciones, reglas 1 a 9, postcondiciones
# a y e (SEG-01, SEG-04, SEG-14), D-21 (formato del teléfono), D-22 (auditoría en la misma transacción) y
# D-28 (teléfono de hasta 25 caracteres). Las de servicio llaman a core.servicios.alta_usuario; las de
# vista (integración) usan el cliente de prueba contra las pantallas. Cada prueba arma sus propios datos.
# El servicio se llama a través del módulo (servicios.x) para que, mientras no exista, cada prueba falle
# por separado en vez de romper la importación del archivo.
# Tarea 08b (D-35): la forma de primer acceso (invitación por correo o contraseña temporal, reglas 4, 10 y 11,
# postcondiciones a, c y e) y SEG-20 (aceptar la invitación), con sus pruebas de concurrencia y de envío.

import json
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import authenticate
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core import mail
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.core.mail.backends.base import BaseEmailBackend
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings, tag
from django.utils import timezone
from django.urls import reverse

from core import servicios
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import (
    BACKEND_QUE_FALLA,
    CLAVE,
    PATRON_INVITACION,
    construir_url,
    contenido_de_auditoria,
    crear_administrador,
    crear_cuenta,
    crear_gerente,
    dar_invitacion,
    invitacion_valida,
    sin_csrf,
    token_de_invitacion,
)
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

MENSAJE_EMAIL_REPETIDO = "Ya existe una cuenta con ese email."

# Formas de primer acceso (regla 4 de USR-ALT-USR, D-35). Texto literal: si el servicio cambiara el valor, las
# pruebas lo detectan.
INVITACION = "invitacion"
TEMPORAL = "temporal"
# Cumple SEG-03 y no se parece a los datos de las cuentas de prueba.
NUEVA = "huerta-hidro-2026"
OTRA_NUEVA = "lechuga-nft-2026"
# Mensaje de la contraseña vacía: el de FormularioContrasenaNueva y de cambiar_contrasena.
MENSAJE_CONTRASENA_VACIA = "Ingresá la contraseña nueva."


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
        cuenta, acceso = servicios.alta_usuario(actor, **datos_validos(**cambios))
        # D-35: el servicio devuelve la forma de acceso; estas pruebas son de la contraseña temporal.
        return cuenta, acceso.contrasena_temporal

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


    # ---- Forma de primer acceso: invitación o contraseña temporal (tarea 08b, D-35) ----

    def alta_con(self, actor, acceso, **cambios):
        """Alta con la forma de acceso indicada; devuelve ``(cuenta, resultado)`` del servicio."""
        return servicios.alta_usuario(
            actor, **datos_validos(**cambios), acceso=acceso, construir_url=construir_url
        )

    @override_settings(CORREO_CONFIGURADO=True)
    def test_regla_4_con_invitacion_la_cuenta_queda_sin_contrasena(self):
        """USR-ALT-USR regla 4, postcondición a, SEG-20 y D-35: con la invitación la cuenta queda activa, sin
        contraseña utilizable y con la invitación pendiente; no tiene contraseña temporal y el resultado no trae
        ninguna."""
        gerente = crear_gerente()

        cuenta, resultado = self.alta_con(gerente, INVITACION)

        cuenta = Usuario.objects.get(pk=cuenta.pk)
        self.assertTrue(cuenta.is_active)
        self.assertFalse(cuenta.has_usable_password())
        self.assertTrue(cuenta.tiene_invitacion_pendiente)
        self.assertFalse(cuenta.invitacion_vencida())
        self.assertIsNone(cuenta.fecha_contrasena_temporal)
        self.assertEqual(resultado.forma, INVITACION)
        self.assertIsNone(resultado.contrasena_temporal)
        self.assertTrue(resultado.invitacion_enviada)

    @override_settings(CORREO_CONFIGURADO=True)
    def test_regla_4_con_temporal_sigue_igual_que_antes(self):
        """USR-ALT-USR regla 4, SEG-04 y D-35: con la contraseña temporal la cuenta queda como hasta ahora (temporal
        que vence a los 7 días, sin invitación) y no se envía ningún correo."""
        gerente = crear_gerente()

        cuenta, resultado = self.alta_con(gerente, TEMPORAL)

        cuenta = Usuario.objects.get(pk=cuenta.pk)
        self.assertEqual(resultado.forma, TEMPORAL)
        self.assertTrue(cuenta.check_password(resultado.contrasena_temporal))
        self.assertTrue(cuenta.tiene_contrasena_temporal)
        self.assertIsNone(cuenta.fecha_invitacion)
        self.assertFalse(resultado.invitacion_enviada)
        self.assertEqual(mail.outbox, [])

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_c_con_invitacion_envia_el_correo_con_rol_y_enlace(self):
        """USR-ALT-USR postcondición c, SEG-20 y D-35: se envía al email de la cuenta un correo en texto plano que
        saluda con el nombre, dice que se le creó una cuenta con su rol, trae el enlace (válido para esa cuenta),
        dice que vence en 7 días y sirve una sola vez, y que si no la esperaba lo ignore."""
        gerente = crear_gerente()

        cuenta, _ = self.alta_con(gerente, INVITACION)

        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, ["laura@infoponia.com"])
        self.assertEqual(mensaje.content_subtype, "plain")
        self.assertEqual(getattr(mensaje, "alternatives", []), [])
        self.assertIn("Hola Laura", mensaje.body)
        self.assertIn("Capataz", mensaje.body)
        self.assertIn("7 días", mensaje.body)
        self.assertIn("una sola vez", mensaje.body)
        self.assertIn("ignorá", mensaje.body.lower())
        encontrado = PATRON_INVITACION.search(mensaje.body)
        self.assertIsNotNone(encontrado, mensaje.body)
        self.assertTrue(invitacion_valida(cuenta, encontrado.group(2)))

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_e_audita_la_forma_de_acceso(self):
        """USR-ALT-USR postcondición e, SEG-14 y D-35: el registro del alta guarda la forma de acceso elegida, sin
        contraseñas ni el token de la invitación."""
        gerente = crear_gerente()

        invitada, _ = self.alta_con(gerente, INVITACION)
        con_temporal, resultado = self.alta_con(gerente, TEMPORAL, email="otra@infoponia.com")

        registros = {
            r.afectados[0]["id"]: r for r in RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA)
        }
        self.assertEqual(registros[invitada.pk].detalle["acceso"], INVITACION)
        self.assertEqual(registros[con_temporal.pk].detalle["acceso"], TEMPORAL)
        token = PATRON_INVITACION.search(mail.outbox[0].body).group(2)
        for registro in registros.values():
            contenido = contenido_de_auditoria(registro)
            self.assertNotIn(token, contenido)
            self.assertNotIn(resultado.contrasena_temporal, contenido)

    @override_settings(CORREO_CONFIGURADO=False)
    def test_regla_10_sin_correo_rechaza_la_invitacion(self):
        """USR-ALT-USR regla 10, SEG-12 y D-35: sin el envío de correo configurado la invitación no está disponible:
        el servicio la rechaza en el campo ``acceso`` («correo_no_configurado») aunque llegue en el pedido, no crea
        la cuenta y no envía nada."""
        gerente = crear_gerente()

        with self.assertRaises(ValidationError) as contexto:
            self.alta_con(gerente, INVITACION)

        self.assertIn("correo_no_configurado", codigos_de(contexto, "acceso"))
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())
        self.assertEqual(mail.outbox, [])

    @override_settings(CORREO_CONFIGURADO=True)
    def test_d35_forma_de_acceso_desconocida_se_rechaza(self):
        """D-35: una forma de acceso que no es «invitacion» ni «temporal» se rechaza en el campo ``acceso``
        («acceso_invalido») y no crea la cuenta."""
        gerente = crear_gerente()

        for acceso in ("sms", ""):
            with self.subTest(acceso=acceso):
                with self.assertRaises(ValidationError) as contexto:
                    self.alta_con(gerente, acceso)
                self.assertIn("acceso_invalido", codigos_de(contexto, "acceso"))
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())

    @override_settings(CORREO_CONFIGURADO=True, EMAIL_BACKEND=BACKEND_QUE_FALLA)
    def test_regla_11_si_falla_el_envio_la_cuenta_se_crea_igual(self):
        """USR-ALT-USR regla 11, SEG-12 y D-35: si el envío de la invitación falla, la cuenta se crea igual, con la
        invitación pendiente y su auditoría; el resultado lo informa (para avisarle a quien hizo el alta) y la falla
        queda en los registros de errores, con el id de la cuenta y sin el enlace."""
        gerente = crear_gerente()

        with self.assertLogs("core.servicios", level="ERROR") as registros:
            cuenta, resultado = self.alta_con(gerente, INVITACION)

        self.assertFalse(resultado.invitacion_enviada)
        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).tiene_invitacion_pendiente)
        self.assertTrue(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA).exists())
        salida = "\n".join(registros.output)
        self.assertIn(str(cuenta.pk), salida)
        self.assertNotIn("/invitacion/", salida)

    def test_d35_una_cuenta_no_tiene_invitacion_y_temporal_a_la_vez(self):
        """D-35: una cuenta nunca tiene a la vez una invitación pendiente y una contraseña temporal. La base lo
        rechaza (restricción ``invitacion_o_temporal``), como respaldo de los servicios."""
        cuenta = crear_cuenta(Capataz)
        ahora = timezone.now()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.filter(pk=cuenta.pk).update(
                fecha_invitacion=ahora, fecha_contrasena_temporal=ahora
            )


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


@tag("concurrencia")
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
        """Dos Administradores dan de alta, a la vez, un Gerente cada uno (con emails distintos).

        La primera alta se detiene al registrar la auditoría (con su Gerente ya escrito y sin confirmar) y
        recién entonces arranca la segunda. Las dos son iguales, así que da lo mismo cuál va primera; se fija
        «a» para que el orden no dependa de la velocidad de la máquina."""
        primero = crear_administrador()
        segundo = crear_administrador(email="admin2@infoponia.com")
        return correr_a_la_vez(
            lambda: servicios.alta_usuario(
                primero, **datos_validos(rol=Usuario.Rol.GERENTE, email="g1@infoponia.com")
            ),
            lambda: servicios.alta_usuario(
                segundo, **datos_validos(rol=Usuario.Rol.GERENTE, email="g2@infoponia.com")
            ),
            primera="a",
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


def invitar(nombre_email="laura@infoponia.com", clase=Capataz, **extra):
    """Una cuenta con la invitación pendiente y el token de su invitación: ``(cuenta, token)``."""
    cuenta = dar_invitacion(crear_cuenta(clase, nombre_email, **extra))
    return cuenta, token_de_invitacion(cuenta)


class UsrAltUsrInvitacionTests(TestCase):
    """SEG-20 (invitación por correo) en ``confirmar_invitacion``: la persona elige su contraseña con el enlace de la
    invitación. Mismo patrón que la recuperación (D-34): bloquea la cuenta y revalida el token después de bloquear.
    D-35."""

    def assertEnlaceInvalido(self, cuenta_id, token, nueva=NUEVA):
        """``confirmar_invitacion`` rechaza el enlace con el código «enlace_invalido»."""
        with self.assertRaises(ValidationError) as contexto:
            servicios.confirmar_invitacion(cuenta_id, token, nueva)
        self.assertIn("enlace_invalido", codigos(contexto.exception))

    def assertSigueInvitada(self, cuenta):
        """La cuenta sigue con la invitación pendiente y sin contraseña, y no se auditó ninguna aceptación."""
        cuenta = Usuario.objects.get(pk=cuenta.pk)
        self.assertTrue(cuenta.tiene_invitacion_pendiente)
        self.assertFalse(cuenta.has_usable_password())
        self.assertFalse(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ACEPTACION_INVITACION).exists())

    def test_d35_invitacion_vencida_en_el_limite(self):
        """SEG-20 y D-35: ``Usuario.invitacion_vencida`` (la usan las insignias de la consulta, regla 3 de USR-CNS-USR)
        vence a los 7 días de la invitación, el mismo plazo que la contraseña temporal: 1 s antes no está vencida y
        1 s después sí. Una cuenta sin invitación nunca está vencida. Es el estado de la cuenta, distinto del
        vencimiento del token."""
        cuenta, _ = invitar()
        cuenta = Usuario.objects.get(pk=cuenta.pk)
        enviada = cuenta.fecha_invitacion

        self.assertFalse(cuenta.invitacion_vencida(ahora=enviada + timedelta(days=7, seconds=-1)))
        self.assertTrue(cuenta.invitacion_vencida(ahora=enviada + timedelta(days=7, seconds=1)))

        sin_invitacion = crear_cuenta(Capataz, "sin.invitacion@infoponia.com")
        self.assertFalse(sin_invitacion.tiene_invitacion_pendiente)
        self.assertFalse(sin_invitacion.invitacion_vencida(ahora=timezone.now() + timedelta(days=30)))

    def test_seg20_aceptar_pone_la_contrasena_y_no_la_deja_temporal(self):
        """SEG-20 y USR-ALT-USR postcondición a: al aceptar, la cuenta queda con la contraseña que eligió su dueño,
        sin la invitación pendiente y sin contraseña temporal."""
        cuenta, token = invitar()

        servicios.confirmar_invitacion(cuenta.pk, token, NUEVA)

        cuenta = Usuario.objects.get(pk=cuenta.pk)
        self.assertTrue(cuenta.check_password(NUEVA))
        self.assertIsNone(cuenta.fecha_invitacion)
        self.assertIsNone(cuenta.fecha_contrasena_temporal)

    def test_seg20_aceptar_audita_con_usuario_y_rol_de_la_cuenta(self):
        """SEG-14, D-22 y D-35: la aceptación se audita con la acción «aceptacion_invitacion»; el usuario y el rol
        son los de la cuenta afectada, que es la única afectada, y no queda ninguna contraseña ni el token."""
        cuenta, token = invitar()

        servicios.confirmar_invitacion(cuenta.pk, token, NUEVA)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.ACEPTACION_INVITACION)
        self.assertEqual(registro.usuario_id, cuenta.pk)
        self.assertEqual(registro.rol, "capataz")
        self.assertEqual(registro.afectados, [{"modelo": "core.usuario", "id": cuenta.pk}])
        contenido = contenido_de_auditoria(registro)
        for secreto in (NUEVA, token):
            self.assertNotIn(secreto, contenido)

    def test_seg20_el_enlace_sirve_una_sola_vez(self):
        """SEG-20: un enlace de invitación ya usado no vuelve a servir y no cambia nada."""
        cuenta, token = invitar()
        servicios.confirmar_invitacion(cuenta.pk, token, NUEVA)

        self.assertEnlaceInvalido(cuenta.pk, token, OTRA_NUEVA)

        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).check_password(NUEVA))
        self.assertEqual(RegistroAuditoria.objects.count(), 1)

    def test_seg20_el_enlace_vence_a_los_7_dias(self):
        """SEG-20 y D-35: pasados 7 días (y 1 s) el enlace venció, aunque la recuperación vence a la hora
        (``PASSWORD_RESET_TIMEOUT`` no cambia)."""
        cuenta, token = invitar()
        despues = datetime.now() + timedelta(days=7, seconds=1)

        with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=despues):
            self.assertEnlaceInvalido(cuenta.pk, token)

        self.assertSigueInvitada(cuenta)

    def test_seg20_el_enlace_sirve_antes_de_los_7_dias(self):
        """SEG-20 y D-35: un día después (más que la hora de la recuperación) y hasta 1 s antes de los 7 días, el
        enlace todavía sirve."""
        for nombre, demora in {"un día": timedelta(days=1), "casi 7 días": timedelta(days=7, seconds=-1)}.items():
            with self.subTest(nombre):
                cuenta, token = invitar(f"{demora.days}@infoponia.com")
                with mock.patch.object(
                    PasswordResetTokenGenerator, "_now", return_value=datetime.now() + demora
                ):
                    servicios.confirmar_invitacion(cuenta.pk, token, NUEVA)
                self.assertTrue(Usuario.objects.get(pk=cuenta.pk).check_password(NUEVA))

    def test_seg20_enlace_alterado_o_de_cuenta_inactiva_se_rechaza(self):
        """SEG-20 y D-35: un token alterado, uno de otra cuenta, una cuenta inexistente o una que pasó a inactiva
        dan «enlace_invalido» y no cambian nada."""
        cuenta, token = invitar()
        otra, token_de_otra = invitar("otra@infoponia.com")

        casos = {
            "token alterado": (cuenta.pk, token[:-1] + ("a" if token[-1] != "a" else "b")),
            "token de otra cuenta": (cuenta.pk, token_de_otra),
            "cuenta inexistente": (otra.pk + 1000, token),
            "sin cuenta": (None, token),
        }
        for nombre, (cuenta_id, token_del_caso) in casos.items():
            with self.subTest(nombre):
                self.assertEnlaceInvalido(cuenta_id, token_del_caso)

        Usuario.objects.filter(pk=otra.pk).update(is_active=False)
        with self.subTest("cuenta inactiva"):
            self.assertEnlaceInvalido(otra.pk, token_de_otra)

        self.assertSigueInvitada(cuenta)
        self.assertSigueInvitada(otra)

    def test_seg20_aceptar_aplica_la_politica(self):
        """SEG-20 y SEG-03: la contraseña elegida con la invitación cumple la política; si no, el error va en el
        campo ``contrasena_nueva`` (la vacía, con el mismo mensaje que el formulario), no cambia nada y el enlace
        sigue sirviendo."""
        cuenta, token = invitar(nombre="Maximiliano", apellido="Fernández")

        casos = {
            "corta": ("hid-26", "password_too_short"),
            "solo números": ("83920174", "password_entirely_numeric"),
            "común": ("password1", "password_too_common"),
            "parecida a los datos": ("maximiliano26", "password_too_similar"),
            "vacía": ("", "required"),
        }
        for nombre, (contrasena, codigo) in casos.items():
            with self.subTest(nombre):
                with self.assertRaises(ValidationError) as contexto:
                    servicios.confirmar_invitacion(cuenta.pk, token, contrasena)
                errores = contexto.exception.error_dict.get("contrasena_nueva", [])
                self.assertIn(codigo, [e.code for e in errores])
                if codigo == "required":
                    self.assertEqual([e.message for e in errores], [MENSAJE_CONTRASENA_VACIA])
                self.assertSigueInvitada(cuenta)

        servicios.confirmar_invitacion(cuenta.pk, token, NUEVA)
        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).check_password(NUEVA))

    def test_seg20_sin_aceptar_no_se_identifica(self):
        """SEG-20 y SEG-06: mientras la persona no elige su contraseña, la cuenta no puede identificarse con ninguna
        contraseña (el inicio de sesión da el mensaje genérico)."""
        cuenta, _ = invitar()

        for contrasena in ("", CLAVE, NUEVA):
            with self.subTest(contrasena=contrasena):
                self.assertIsNone(authenticate(None, email=cuenta.email, password=contrasena))

    @override_settings(CORREO_CONFIGURADO=True)
    def test_d35_token_de_recuperacion_no_sirve_como_invitacion_ni_al_reves(self):
        """D-35: el enlace de recuperación (D-34) y el de invitación usan generadores distintos: el token de uno no
        sirve para el otro."""
        cuenta, token_invitacion = invitar()
        token_recuperacion = default_token_generator.make_token(Usuario.objects.get(pk=cuenta.pk))

        self.assertEnlaceInvalido(cuenta.pk, token_recuperacion)
        with self.assertRaises(ValidationError) as contexto:
            servicios.confirmar_recuperacion(cuenta.pk, token_invitacion, NUEVA)
        self.assertIn("enlace_invalido", codigos(contexto.exception))

        self.assertSigueInvitada(cuenta)

    @override_settings(CORREO_CONFIGURADO=True)
    def test_seg20_recuperar_antes_de_aceptar_tiene_el_mismo_resultado(self):
        """SEG-20: si la persona usa «¿Olvidaste tu contraseña?» antes de aceptar la invitación, le llega el enlace
        de recuperación y, al usarlo, la cuenta queda con su contraseña y sin la invitación; el enlace de la
        invitación deja de servir."""
        cuenta, token_invitacion = invitar()

        servicios.pedir_recuperacion(cuenta.email, construir_url)
        self.assertEqual(len(mail.outbox), 1)
        token_recuperacion = default_token_generator.make_token(Usuario.objects.get(pk=cuenta.pk))
        servicios.confirmar_recuperacion(cuenta.pk, token_recuperacion, NUEVA)

        cuenta = Usuario.objects.get(pk=cuenta.pk)
        self.assertTrue(cuenta.check_password(NUEVA))
        self.assertIsNone(cuenta.fecha_invitacion)
        self.assertIsNone(cuenta.fecha_contrasena_temporal)
        self.assertEnlaceInvalido(cuenta.pk, token_invitacion, OTRA_NUEVA)

    @override_settings(CORREO_CONFIGURADO=False)
    def test_d35_aceptar_no_depende_del_correo_configurado(self):
        """D-35: aceptar una invitación no envía nada, así que funciona aunque el correo haya dejado de estar
        configurado después de enviarla (a diferencia de la recuperación, precondición a de USR-RCP-CTR)."""
        cuenta, token = invitar()

        servicios.confirmar_invitacion(cuenta.pk, token, NUEVA)

        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).check_password(NUEVA))


class BackendQueAnotaLaTransaccion(BaseEmailBackend):
    """Backend de correo de prueba: anota, en el momento de enviar, si había una transacción abierta y si la cuenta
    destinataria ya estaba guardada en la base (D-35, D-14)."""

    anotaciones = []

    def send_messages(self, email_messages):
        for mensaje in email_messages:
            BackendQueAnotaLaTransaccion.anotaciones.append(
                {
                    "transaccion_abierta": connection.in_atomic_block,
                    "cuenta_guardada": Usuario.objects.filter(email=mensaje.to[0]).exists(),
                }
            )
        return len(email_messages)


@override_settings(
    CORREO_CONFIGURADO=True, EMAIL_BACKEND="core.tests.test_usr_alt_usr.BackendQueAnotaLaTransaccion"
)
class UsrAltUsrInvitacionEnvioTests(TransactionTestCase):
    """D-35 y D-14: la invitación se envía DESPUÉS de confirmar la transacción del alta, no dentro de ella. Es
    ``TransactionTestCase`` porque ``TestCase`` envuelve cada prueba en una transacción y no deja ver la diferencia."""

    def setUp(self):
        BackendQueAnotaLaTransaccion.anotaciones = []

    def test_d35_la_invitacion_se_envia_fuera_de_la_transaccion(self):
        """D-35 (lineamiento 4) y D-14: al enviar la invitación no hay ninguna transacción abierta y la cuenta ya
        está guardada. Así un servidor SMTP lento no mantiene la transacción (ni sus bloqueos) abierta, y un correo
        nunca sale para una cuenta que después se deshizo."""
        gerente = crear_gerente()

        servicios.alta_usuario(
            gerente, **datos_validos(), acceso=INVITACION, construir_url=construir_url
        )

        self.assertEqual(
            BackendQueAnotaLaTransaccion.anotaciones,
            [{"transaccion_abierta": False, "cuenta_guardada": True}],
        )


@tag("concurrencia")
@override_settings(CORREO_CONFIGURADO=True)
class UsrAltUsrInvitacionConcurrenciaTests(TransactionTestCase):
    """SEG-20 con dos pedidos simultáneos: el enlace de la invitación es de un solo uso también cuando llegan dos
    aceptaciones a la vez, o cuando quien gestiona la cuenta restablece el acceso mientras la persona acepta. Son
    ``TransactionTestCase``: cada operación corre en su propio hilo, con su conexión y su transacción (ver
    ``core/tests/concurrencia.py``)."""

    def test_seg20_dos_aceptaciones_con_el_mismo_enlace_cambian_una_sola_vez(self):
        """SEG-20 y D-35: dos aceptaciones con el mismo enlace y contraseñas distintas. ``correr_a_la_vez`` detiene a
        la primera justo después de ``registrar`` (por defecto): ya bloqueó la cuenta, guardó la contraseña y auditó,
        pero no confirmó. Recién entonces arranca la segunda, que queda esperando el bloqueo; cuando sigue, revalida
        el token con la fila releída y se rechaza con «enlace_invalido». Si el token se validara solo antes de
        bloquear, las dos pasarían: esta prueba falla."""
        cuenta, token = invitar()

        resultados = correr_a_la_vez(
            lambda: servicios.confirmar_invitacion(cuenta.pk, token, NUEVA),
            lambda: servicios.confirmar_invitacion(cuenta.pk, token, OTRA_NUEVA),
            primera="a",
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], "ninguna operación puede terminar con un error sin traducir")
        self.assertEqual(len(exitos), 1)
        self.assertEqual(len(rechazos), 1)
        self.assertIn("enlace_invalido", codigos(rechazos[0]))
        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).check_password(NUEVA))
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ACEPTACION_INVITACION).count(), 1)

    def test_d35_restablecer_mientras_se_acepta_invalida_el_enlace(self):
        """USR-MOD-USR regla 11, SEG-20 y D-35: el Gerente restablece el acceso con una contraseña temporal mientras
        la persona acepta la invitación. El restablecimiento va primero y se detiene después de auditar, con la
        cuenta bloqueada; la aceptación espera el bloqueo y, al seguir, revalida el token: la cuenta ya no tiene la
        invitación, así que se rechaza con «enlace_invalido» y la cuenta queda con la temporal."""
        gerente = crear_gerente()
        cuenta, token = invitar()

        resultados = correr_a_la_vez(
            lambda: servicios.restablecer_contrasena(gerente, cuenta.pk, acceso=TEMPORAL),
            lambda: servicios.confirmar_invitacion(cuenta.pk, token, NUEVA),
            primera="a",
        )

        self.assertNotIsInstance(resultados["a"], Exception)
        self.assertIsInstance(resultados["b"], ValidationError)
        self.assertIn("enlace_invalido", codigos(resultados["b"]))
        cuenta = Usuario.objects.get(pk=cuenta.pk)
        self.assertTrue(cuenta.check_password(resultados["a"].contrasena_temporal))
        self.assertIsNone(cuenta.fecha_invitacion)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ACEPTACION_INVITACION).exists())


@override_settings(CORREO_CONFIGURADO=True)
class UsrAltUsrAccesoVistaTests(TestCase):
    """Integración del alta con la forma de primer acceso (regla 4, reglas 10 y 11, postcondiciones a y c, D-35): el
    radio del formulario, el resultado con la invitación, el aviso de la falla de envío y la temporal de siempre."""

    def entrar_como_gerente(self):
        """Crea un Gerente, abre su sesión y lo devuelve."""
        gerente = crear_gerente()
        self.client.force_login(gerente)
        return gerente

    def enviar_alta(self, **cambios):
        """Envía el formulario de alta con datos válidos pisados por ``cambios``."""
        return self.client.post(reverse("core:usuario_nuevo"), datos_validos(**cambios))

    def test_regla_4_con_correo_el_formulario_ofrece_la_invitacion_marcada_por_defecto(self):
        """USR-ALT-USR regla 4 y D-35: con el correo configurado el formulario ofrece las dos formas de primer
        acceso y la invitación viene marcada (es la opción por defecto)."""
        self.entrar_como_gerente()

        respuesta = self.client.get(reverse("core:usuario_nuevo"))

        self.assertContains(respuesta, 'name="acceso" value="invitacion" checked')
        self.assertContains(respuesta, 'name="acceso" value="temporal"')
        self.assertNotContains(respuesta, 'name="acceso" value="temporal" checked')
        self.assertContains(respuesta, "Invitación por correo")

    @override_settings(CORREO_CONFIGURADO=False)
    def test_regla_10_sin_correo_el_formulario_solo_ofrece_la_temporal(self):
        """USR-ALT-USR regla 10 y D-35: sin el correo configurado el formulario no ofrece la invitación: no hay
        campo de forma de acceso y se explica que se genera una contraseña temporal."""
        self.entrar_como_gerente()

        respuesta = self.client.get(reverse("core:usuario_nuevo"))

        self.assertNotContains(respuesta, 'name="acceso"')
        self.assertContains(respuesta, "no está disponible porque el envío de correo no está configurado")
        self.assertContains(respuesta, "contraseña temporal")

    def test_flujo_principal_alta_con_invitacion_muestra_el_resultado_y_envia_el_correo(self):
        """USR-ALT-USR postcondiciones a y c, y D-35: el alta con invitación muestra «Cuenta creada» con el mensaje
        pedido (a quién se le envió, que vence en 7 días y la pista de la carpeta de Spam), envía el correo, deja
        la cuenta con la invitación pendiente y NO muestra ninguna contraseña temporal."""
        self.entrar_como_gerente()

        respuesta = self.enviar_alta(acceso=INVITACION)

        self.assertEqual(respuesta.status_code, 200)
        cuenta = Usuario.objects.get(email="laura@infoponia.com")
        self.assertTrue(cuenta.tiene_invitacion_pendiente)
        self.assertContains(respuesta, "Cuenta creada")
        self.assertContains(
            respuesta,
            "Le enviamos una invitación a <b class=\"mono\">laura@infoponia.com</b>. Vence en 7 días. Si no le llega, "
            "que revise la carpeta de Spam, o restablecé el acceso con una contraseña temporal.",
        )
        self.assertIsNone(respuesta.context["contrasena_temporal"])
        self.assertNotContains(respuesta, "contrasena-temporal")
        self.assertNotContains(respuesta, "La contraseña temporal se mostró una sola vez")
        self.assertEqual([m.to for m in mail.outbox], [["laura@infoponia.com"]])

    def test_regla_4_alta_con_temporal_con_correo_muestra_la_temporal_y_no_envia_nada(self):
        """USR-ALT-USR regla 4, postcondición c y D-35: eligiendo la contraseña temporal, aunque el correo esté
        configurado, se la informa a quien hizo el alta una única vez y no se envía ningún correo."""
        self.entrar_como_gerente()

        respuesta = self.enviar_alta(acceso=TEMPORAL)

        cuenta = Usuario.objects.get(email="laura@infoponia.com")
        temporal = respuesta.context["contrasena_temporal"]
        self.assertTrue(cuenta.check_password(temporal))
        self.assertContains(respuesta, temporal)
        self.assertFalse(cuenta.tiene_invitacion_pendiente)
        self.assertEqual(mail.outbox, [])

    def test_regla_4_con_correo_hay_que_elegir_la_forma_de_acceso(self):
        """USR-ALT-USR regla 4 y D-35: con el correo configurado el campo es obligatorio: un pedido sin la forma de
        acceso vuelve al formulario con el error y no crea la cuenta."""
        self.entrar_como_gerente()

        respuesta = self.enviar_alta()

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "core/usuarios/alta.html")
        self.assertContains(respuesta, "Elegí cómo va a acceder la persona")
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())

    @override_settings(CORREO_CONFIGURADO=False)
    def test_regla_10_sin_correo_una_invitacion_enviada_a_mano_se_rechaza(self):
        """USR-ALT-USR regla 10, SEG-12 y D-35: sin el correo configurado, un pedido con ``acceso=invitacion`` (la
        pantalla no lo ofrece) vuelve al formulario con el motivo, sin crear la cuenta ni enviar nada."""
        self.entrar_como_gerente()

        respuesta = self.enviar_alta(acceso=INVITACION)

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "core/usuarios/alta.html")
        self.assertContains(respuesta, "La invitación por correo no está disponible")
        self.assertFalse(Usuario.objects.filter(email="laura@infoponia.com").exists())
        self.assertEqual(mail.outbox, [])

    @override_settings(CORREO_CONFIGURADO=False)
    def test_regla_10_sin_correo_el_alta_sin_elegir_da_la_temporal(self):
        """USR-ALT-USR regla 10 y D-35: sin el correo configurado, un pedido sin forma de acceso (como el que arma
        la pantalla) da de alta con la contraseña temporal de siempre."""
        self.entrar_como_gerente()

        respuesta = self.enviar_alta()

        cuenta = Usuario.objects.get(email="laura@infoponia.com")
        self.assertTrue(cuenta.check_password(respuesta.context["contrasena_temporal"]))
        self.assertTrue(cuenta.tiene_contrasena_temporal)

    @override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA)
    def test_regla_11_si_falla_el_envio_el_alta_avisa_y_ofrece_restablecer(self):
        """USR-ALT-USR regla 11 y D-35: si el envío de la invitación falla, la cuenta se crea igual y la pantalla se
        lo avisa a quien hizo el alta con un aviso de error (no dice que se envió) que ofrece «Restablecer acceso»."""
        self.entrar_como_gerente()

        with self.assertLogs("core.servicios", level="ERROR"):
            respuesta = self.enviar_alta(acceso=INVITACION)

        cuenta = Usuario.objects.get(email="laura@infoponia.com")
        self.assertTrue(cuenta.tiene_invitacion_pendiente)
        self.assertContains(respuesta, "Cuenta creada")
        self.assertContains(respuesta, "No pudimos enviar la invitación")
        self.assertNotContains(respuesta, "Le enviamos una invitación")
        self.assertContains(respuesta, f'href="{reverse("core:usuario_restablecer", args=[cuenta.pk])}"')
        self.assertContains(respuesta, "Restablecer acceso")

    def test_regla_4_el_administrador_da_de_alta_al_gerente_con_invitacion(self):
        """USR-ALT-USR regla 4, regla 1 y D-35: el Administrador, que da de alta al Gerente, elige la forma de
        acceso igual que el Gerente."""
        self.client.force_login(crear_administrador())

        respuesta = self.enviar_alta(rol=Usuario.Rol.GERENTE, acceso=INVITACION)

        cuenta = Usuario.objects.get(email="laura@infoponia.com")
        self.assertEqual(cuenta.rol, Usuario.Rol.GERENTE)
        self.assertTrue(cuenta.tiene_invitacion_pendiente)
        self.assertContains(respuesta, "Le enviamos una invitación a")
        self.assertIn("Gerente", mail.outbox[0].body)


@override_settings(CORREO_CONFIGURADO=True)
class UsrAltUsrInvitacionVistaTests(TestCase):
    """Pantallas del enlace de la invitación (SEG-20, D-35): la entrada del enlace, «Elegí tu contraseña para empezar
    a usar InfoPonia» y «Invitación no válida». Misma técnica que la recuperación (D-34): el token pasa a la sesión y
    la URL del formulario no lo lleva; pantallas solo para quien no tiene sesión. Cada prueba arma sus datos."""

    @staticmethod
    def ruta_del_correo(mensaje):
        """Ruta (sin dominio) del enlace de invitación del correo."""
        encontrado = re.search(r"https?://testserver(/invitacion/[\w-]+/[\w-]+/)", mensaje.body)
        assert encontrado, mensaje.body
        return encontrado.group(1)

    @staticmethod
    def enlace(cuenta, token=None, uidb64=None):
        """Ruta del enlace de invitación de ``cuenta`` con un token de invitación recién generado (o el indicado)."""
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        return reverse(
            "core:invitacion_enlace",
            kwargs={
                "uidb64": uidb64 or urlsafe_base64_encode(force_bytes(cuenta.pk)),
                "token": token or token_de_invitacion(cuenta),
            },
        )

    @staticmethod
    def pantalla_elegir(cuenta):
        """URL de «Elegí tu contraseña» de la invitación de ``cuenta`` (sin el token)."""
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        return reverse(
            "core:invitacion_elegir", kwargs={"uidb64": urlsafe_base64_encode(force_bytes(cuenta.pk))}
        )

    def elegir(self, cuenta, nueva=NUEVA, repetida=None):
        """Envía el formulario de la contraseña de la invitación de ``cuenta``."""
        return self.client.post(
            self.pantalla_elegir(cuenta),
            {"contrasena_nueva": nueva, "contrasena_repetida": nueva if repetida is None else repetida},
        )

    def assertInvitacionNoValida(self, respuesta):
        """La respuesta es la pantalla «Invitación no válida»."""
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "core/invitacion_enlace_invalido.html")
        self.assertContains(respuesta, "Invitación no válida")

    def test_flujo_principal_la_persona_abre_el_correo_y_elige_su_contraseña(self):
        """SEG-20 y D-35, flujo principal: el Gerente da de alta con invitación; la persona abre el enlace del correo,
        elige su contraseña y llega al inicio de sesión con un aviso, sin sesión iniciada; después entra con la
        contraseña que eligió. La cuenta deja de tener la invitación pendiente y se audita la aceptación."""
        gerente = crear_gerente()
        self.client.force_login(gerente)
        self.client.post(reverse("core:usuario_nuevo"), datos_validos(acceso=INVITACION))
        self.client.logout()
        cuenta = Usuario.objects.get(email="laura@infoponia.com")

        respuesta = self.client.get(self.ruta_del_correo(mail.outbox[0]))
        self.assertRedirects(respuesta, self.pantalla_elegir(cuenta), fetch_redirect_response=False)
        pantalla = self.client.get(self.pantalla_elegir(cuenta))
        self.assertTemplateUsed(pantalla, "core/invitacion_elegir.html")
        self.assertContains(pantalla, "Elegí tu contraseña para empezar a usar InfoPonia")

        respuesta = self.elegir(cuenta)

        self.assertRedirects(respuesta, reverse("core:iniciar_sesion"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(
            self.client.get(reverse("core:iniciar_sesion")), "Contraseña guardada. Ingresá con tu nueva contraseña."
        )
        cuenta.refresh_from_db()
        self.assertTrue(cuenta.check_password(NUEVA))
        self.assertFalse(cuenta.tiene_invitacion_pendiente)
        self.assertFalse(cuenta.tiene_contrasena_temporal)
        entrada = self.client.post(
            reverse("core:iniciar_sesion"), {"username": cuenta.email, "password": NUEVA}
        )
        self.assertRedirects(entrada, reverse("core:inicio"), fetch_redirect_response=False)
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                accion=RegistroAuditoria.Accion.ACEPTACION_INVITACION, usuario=cuenta
            ).exists()
        )

    def test_seg20_la_url_del_formulario_no_lleva_el_token(self):
        """SEG-20 y D-34/D-35: el enlace guarda el token en la sesión y redirige a una URL sin él; la pantalla de la
        contraseña tampoco lo repite."""
        cuenta, token = invitar()

        respuesta = self.client.get(self.enlace(cuenta, token))

        self.assertEqual(respuesta.status_code, 302)
        self.assertNotIn(token, respuesta["Location"])
        pantalla = self.client.get(respuesta["Location"])
        self.assertEqual(pantalla.status_code, 200)
        self.assertNotContains(pantalla, token)

    def test_seg20_invitacion_no_valida_es_la_misma_pantalla_para_cada_causa(self):
        """SEG-20 y D-35: una invitación usada, vencida (7 días), alterada, reemplazada por otra, de una cuenta
        inactiva o con un token de recuperación muestra la misma pantalla «Invitación no válida» y no cambia nada."""
        gerente = crear_gerente()
        pantallas = {}

        def caso(nombre, preparar):
            """Arma una cuenta nueva con invitación, prepara el caso y abre el enlace con un cliente nuevo."""
            cuenta, token = invitar(f"{len(pantallas)}@infoponia.com")
            url = preparar(cuenta, token)
            with self.subTest(nombre):
                respuesta = Client().get(url or self.enlace(cuenta, token))
                self.assertInvitacionNoValida(respuesta)
                pantallas[nombre] = sin_csrf(respuesta.content)

        caso("usada", lambda cuenta, token: servicios.confirmar_invitacion(cuenta.pk, token, NUEVA) and None)
        caso(
            "alterada",
            lambda cuenta, token: self.enlace(cuenta, token[:-1] + ("a" if token[-1] != "a" else "b")),
        )
        caso(
            "reemplazada",
            lambda cuenta, token: servicios.restablecer_contrasena(
                gerente, cuenta.pk, acceso=INVITACION, construir_url=construir_url
            )
            and None,
        )
        caso("inactiva", lambda cuenta, token: Usuario.objects.filter(pk=cuenta.pk).update(is_active=False) and None)
        caso(
            "de recuperación",
            lambda cuenta, token: self.enlace(cuenta, default_token_generator.make_token(cuenta)),
        )

        cuenta, token = invitar("vencida@infoponia.com")
        despues = datetime.now() + timedelta(days=7, seconds=1)
        with self.subTest("vencida"), mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=despues):
            respuesta = Client().get(self.enlace(cuenta, token))
            self.assertInvitacionNoValida(respuesta)
            pantallas["vencida"] = sin_csrf(respuesta.content)

        self.assertEqual(len(set(pantallas.values())), 1, list(pantallas))

    def test_seg20_invitacion_no_valida_ofrece_pedir_otro_enlace_segun_el_correo(self):
        """SEG-20 y D-35: la pantalla «Invitación no válida» ofrece «Pedir un enlace nuevo» (¿Olvidaste tu
        contraseña?: el resultado es el mismo) con el correo configurado, y sin él pide a quien gestiona la cuenta que
        restablezca el acceso."""
        cuenta, _ = invitar()
        url = self.enlace(cuenta, "invalido-0000")

        con_correo = self.client.get(url)
        with override_settings(CORREO_CONFIGURADO=False):
            sin_correo = self.client.get(url)

        self.assertContains(con_correo, f'href="{reverse("core:recuperar_contrasena")}"')
        self.assertNotContains(sin_correo, reverse("core:recuperar_contrasena"))
        self.assertContains(sin_correo, "Pedile a quien gestiona tu cuenta que te restablezca el acceso")

    def test_seg20_con_sesion_iniciada_las_pantallas_redirigen_al_inicio(self):
        """SEG-20 y D-34/D-35: las pantallas de la invitación son solo para quien no tiene sesión."""
        cuenta, token = invitar()
        self.client.force_login(crear_gerente())

        for nombre, url in {
            "enlace": self.enlace(cuenta, token),
            "elegir": self.pantalla_elegir(cuenta),
        }.items():
            with self.subTest(nombre):
                self.assertRedirects(self.client.get(url), reverse("core:inicio"), fetch_redirect_response=False)

    def test_seg20_la_pantalla_de_contrasena_sin_pasar_por_el_enlace_no_es_valida(self):
        """SEG-20: abrir directamente «Elegí tu contraseña», sin haber pasado por el enlace del correo (sin token en
        la sesión), muestra «Invitación no válida»."""
        cuenta, _ = invitar()

        self.assertInvitacionNoValida(self.client.get(self.pantalla_elegir(cuenta)))

    def test_seg20_la_invitacion_se_puede_aceptar_sin_el_correo_configurado(self):
        """SEG-20 y D-35: aceptar la invitación no envía nada, así que las pantallas funcionan aunque el correo haya
        dejado de estar configurado después de enviarla."""
        cuenta, token = invitar()

        with override_settings(CORREO_CONFIGURADO=False):
            respuesta = self.client.get(self.enlace(cuenta, token))
            self.assertRedirects(respuesta, self.pantalla_elegir(cuenta), fetch_redirect_response=False)
            self.elegir(cuenta)

        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).check_password(NUEVA))

    def test_seg20_errores_de_politica_en_el_formulario(self):
        """SEG-20 y SEG-03: una contraseña que no cumple la política, o dos que no coinciden, vuelven al formulario
        con el error en el campo y sin cambiar nada; el enlace sigue sirviendo para otro intento."""
        cuenta, token = invitar()
        self.client.get(self.enlace(cuenta, token))

        sin_politica = self.elegir(cuenta, "123")
        distintas = self.elegir(cuenta, NUEVA, repetida=OTRA_NUEVA)

        self.assertContains(sin_politica, 'id="error-contrasena_nueva"')
        self.assertContains(distintas, "Las contraseñas no coinciden.")
        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).tiene_invitacion_pendiente)
        correcto = self.elegir(cuenta)
        self.assertRedirects(correcto, reverse("core:iniciar_sesion"), fetch_redirect_response=False)

    def test_seg20_invitacion_que_deja_de_servir_mientras_se_escribe(self):
        """SEG-20 y D-35: si la invitación se usa en otra pestaña o la cuenta se da de baja mientras la persona
        escribe, al enviar se muestra «Invitación no válida» y no cambia nada."""
        casos = {
            "usada en otra pestaña": lambda cuenta, token: servicios.confirmar_invitacion(cuenta.pk, token, OTRA_NUEVA),
            "cuenta dada de baja": lambda cuenta, token: Usuario.objects.filter(pk=cuenta.pk).update(is_active=False),
        }
        for numero, (nombre, preparar) in enumerate(casos.items()):
            with self.subTest(nombre):
                self.client = Client()
                cuenta, token = invitar(f"escribe{numero}@infoponia.com")
                self.client.get(self.enlace(cuenta, token))
                preparar(cuenta, token)

                respuesta = self.elegir(cuenta)

                self.assertInvitacionNoValida(respuesta)
                self.assertFalse(Usuario.objects.get(pk=cuenta.pk).check_password(NUEVA))
