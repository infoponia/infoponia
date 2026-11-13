# Pruebas de USR-GST-PRF (Gestionar Mi Perfil), tarea 06a: la pantalla Mi perfil (vPerfil) con el cliente de
# prueba. No hay servicio: la consulta no modifica nada (D-25). La foto de perfil (reglas 1 y 5, SEG-19) es de
# la tarea 07 y las cuentas vinculadas (regla 3, USR-VNC-CTA) de la 06b. El cambio de contraseña desde el perfil
# se prueba en test_usr_cmb_ctr.py. Cada prueba arma sus propios datos.

from django.test import TestCase
from django.urls import reverse

from core.models import Agronomo, RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_cuenta, crear_gerente


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
