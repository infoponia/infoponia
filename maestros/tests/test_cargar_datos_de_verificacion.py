# Pruebas del cargador de ``maestros`` (``maestros/verificacion.py``) en el comando ÚNICO ``cargar_datos_de_verificacion`` de ``core`` (CLAUDE.md, «Datos para la verificación a mano»; creado en MAE-02d, unificado en IOT-03):
# se niega a correr con DEBUG apagado, con una base que no es localhost o con variables de Render; no toca al Administrador ni
# crea un Gerente (D-09); es idempotente y deja la alerta «sin Capataz» activa y no leída.

import os
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings

from core.models import Gerente, Usuario
from core.tests.fabricas import crear_administrador, crear_gerente
from core.verificacion import ErrorDeCarga
from maestros import verificacion as verificacion_de_maestros
from maestros.models import Alerta, Invernadero
from maestros.tests.fabricas import ConGeoref, crear_capataz_activo

CLAVE_DE_LA_PRUEBA = "clave-solo-de-esta-prueba"


def cargar(**opciones):
    """Corre el comando como en una base local de desarrollo: DEBUG encendido y host ``localhost`` (el ejecutor de pruebas
    apaga DEBUG por su cuenta). Devuelve lo que imprimió."""
    salida = StringIO()
    with override_settings(DEBUG=True), mock.patch.dict(connection.settings_dict, {"HOST": "localhost"}):
        call_command("cargar_datos_de_verificacion", contrasena=CLAVE_DE_LA_PRUEBA, solo="maestros", stdout=salida, **opciones)
    return salida.getvalue()


class CargarDatosDeVerificacionTests(ConGeoref, TestCase):
    """Sin caso de uso ni regla del modelo: las reglas son las de la sección «Datos para la verificación a mano» de CLAUDE.md."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.administrador = crear_administrador()

    # ---- Se niega a correr ----

    def test_claude_md_se_niega_con_debug_apagado(self):
        """CLAUDE.md: «se niega a correr si DEBUG está apagado» (sin crear nada)."""
        with override_settings(DEBUG=False), mock.patch.dict(connection.settings_dict, {"HOST": "localhost"}):
            with self.assertRaisesMessage(CommandError, "DEBUG"):
                call_command("cargar_datos_de_verificacion", contrasena=CLAVE_DE_LA_PRUEBA, solo="maestros")
        self.assertFalse(Invernadero.objects.exists())
        self.assertEqual(Usuario.objects.count(), 2)

    def test_claude_md_se_niega_si_la_base_no_es_localhost(self):
        """CLAUDE.md: «si la base no es localhost»."""
        with override_settings(DEBUG=True), mock.patch.dict(connection.settings_dict, {"HOST": "ep-algo.neon.tech"}):
            with self.assertRaisesMessage(CommandError, "no es local"):
                call_command("cargar_datos_de_verificacion", contrasena=CLAVE_DE_LA_PRUEBA, solo="maestros")
        self.assertFalse(Invernadero.objects.exists())

    def test_claude_md_se_niega_con_variables_de_render(self):
        """CLAUDE.md: «si hay variables de Render»."""
        with override_settings(DEBUG=True), mock.patch.dict(connection.settings_dict, {"HOST": "localhost"}):
            with mock.patch.dict(os.environ, {"RENDER_SERVICE_ID": "srv-123"}):
                with self.assertRaisesMessage(CommandError, "Render"):
                    call_command("cargar_datos_de_verificacion", contrasena=CLAVE_DE_LA_PRUEBA, solo="maestros")
        self.assertFalse(Invernadero.objects.exists())

    def test_la_clave_es_obligatoria(self):
        """La contraseña nunca está en el repo: entra por ``--contrasena``."""
        with override_settings(DEBUG=True), mock.patch.dict(connection.settings_dict, {"HOST": "localhost"}):
            with self.assertRaises(CommandError):
                call_command("cargar_datos_de_verificacion")

    def test_sin_gerente_activo_frena_con_un_mensaje_y_no_crea_nada(self):
        """No crea un Gerente (D-09): sin uno activo no puede dar de alta los invernaderos y lo dice."""
        Gerente.objects.update(is_active=False)

        with self.assertRaisesMessage(ErrorDeCarga, "Gerente activo"):
            verificacion_de_maestros.cargar(CLAVE_DE_LA_PRUEBA)
        self.assertFalse(Invernadero.objects.exists())

    # ---- Lo que carga ----

    def test_carga_las_cuentas_los_invernaderos_y_la_alerta_sin_capataz_no_leida(self):
        """Deja los dos Agrónomos y el Capataz de prueba (con la clave dada), los dos invernaderos y la alerta no leída."""
        salida = cargar()

        for correo in ("agronomo@prueba1.local", "agronomo@prueba2.local", "capataz@prueba1.local"):
            with self.subTest(correo=correo):
                cuenta = Usuario.objects.get(email=correo)
                self.assertTrue(cuenta.is_active)
                self.assertTrue(cuenta.check_password(CLAVE_DE_LA_PRUEBA))
        uno = Invernadero.objects.get(nombre_invernadero="Invernadero Verificación 1")
        dos = Invernadero.objects.get(nombre_invernadero="Invernadero Verificación 2")
        self.assertEqual(uno.agronomo.email, "agronomo@prueba1.local")
        self.assertEqual(dos.agronomo.email, "agronomo@prueba2.local")
        self.assertIsNone(uno.capataz_id)
        alerta = Alerta.objects.activas().get(invernadero=uno, tipo_alerta="sin_capataz")
        self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.NO_LEIDA)
        self.assertTrue(alerta.para_gerente)
        self.assertIn("agronomo@prueba1.local", salida)
        self.assertIn(str(alerta.pk), salida)
        self.assertNotIn(CLAVE_DE_LA_PRUEBA, salida)

    def test_no_crea_un_gerente_ni_toca_al_administrador(self):
        """D-09 y CLAUDE.md: ni crea un Gerente ni modifica al Administrador (su usuario y su contraseña)."""
        antes = Usuario.objects.filter(pk=self.administrador.pk).values().get()

        cargar()

        self.assertEqual(Gerente.objects.count(), 1)
        self.assertEqual(Usuario.objects.filter(pk=self.administrador.pk).values().get(), antes)

    def test_es_idempotente_y_vuelve_a_dejar_la_alerta_no_leida(self):
        """Una segunda corrida no duplica cuentas, invernaderos ni alertas, y repone «no leída» para repetir la verificación."""
        cargar()
        alerta = Alerta.objects.activas().get(tipo_alerta="sin_capataz", invernadero__nombre_invernadero="Invernadero Verificación 1")
        Alerta.objects.filter(pk=alerta.pk).update(estado_lectura_alerta=Alerta.Lectura.LEIDA)
        cuentas, invernaderos, alertas = Usuario.objects.count(), Invernadero.objects.count(), Alerta.objects.count()

        cargar()

        self.assertEqual((Usuario.objects.count(), Invernadero.objects.count(), Alerta.objects.count()), (cuentas, invernaderos, alertas))
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.NO_LEIDA)

    def test_no_pisa_la_contrasena_de_una_cuenta_que_ya_existe(self):
        """Idempotente y sin tocar lo ajeno: una cuenta de prueba que ya existe queda como está."""
        cargar()
        cuenta = Usuario.objects.get(email="agronomo@prueba1.local")
        cuenta.set_password("otra-clave")
        cuenta.save()

        cargar()

        cuenta.refresh_from_db()
        self.assertTrue(cuenta.check_password("otra-clave"))

    def test_si_el_invernadero_1_ya_tiene_capataz_frena_y_lo_explica(self):
        """No inventa una alerta falsa: si el invernadero 1 tiene Capataz, avisa cómo repetir la verificación."""
        cargar()
        capataz = crear_capataz_activo()
        Invernadero.objects.filter(nombre_invernadero="Invernadero Verificación 1").update(capataz=capataz)

        with self.assertRaisesMessage(ErrorDeCarga, "ya tiene un Capataz"):
            verificacion_de_maestros.cargar(CLAVE_DE_LA_PRUEBA)
