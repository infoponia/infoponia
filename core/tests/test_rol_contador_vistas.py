# Pruebas de las pantallas con el rol Contador (USR-11, D-85): el alta, los filtros, la lista, la ficha, la ventana de
# reactivación, el avatar «CON», el menú y el control de acceso del Contador (SEG-13), y la auditoría de sus altas y bajas.
# Usan el cliente de prueba de Django. Cada prueba arma sus propios datos.

from django.test import TestCase
from django.urls import reverse

from core import menu
from core.models import Contador, RegistroAuditoria, Usuario
from core.templatetags.cuentas import sigla
from core.tests.fabricas import crear_administrador, crear_cuenta, crear_gerente

# Pantallas de otros módulos y de cuentas que el Contador NO tiene que poder abrir (D-85 punto 6, SEG-13).
PANTALLAS_VEDADAS = (
    "core:usuarios",
    "core:usuario_nuevo",
    "core:auditoria",
    "maestros:invernaderos",
    "alertas:lista",
    "inventario:existencias",
    "comercial:inicio",
    "compras:pedidos",
    "iot:inicio",
    "produccion:bitacora",
    "configuracion:pantalla",
)


class RolContadorVistasTests(TestCase):
    """D-85 punto 6: lo que ven el Gerente y el Administrador del rol nuevo, y lo que puede abrir el Contador."""

    def entrar_como_gerente(self):
        """Crea un Gerente, abre su sesión y lo devuelve."""
        gerente = crear_gerente()
        self.client.force_login(gerente)
        return gerente

    def test_regla_1_el_alta_y_el_filtro_ofrecen_el_contador(self):
        """USR-ALT-USR regla 1 y USR-CNS-USR regla 2 (D-85 punto 3): «Contador» está en el rol del alta y en el filtro."""
        self.entrar_como_gerente()

        alta = self.client.get(reverse("core:usuario_nuevo"))
        lista = self.client.get(reverse("core:usuarios"))

        self.assertContains(alta, 'value="contador"')
        self.assertContains(lista, 'value="contador"')

    def test_flujo_principal_alta_de_contador_muestra_la_cuenta_creada(self):
        """USR-ALT-USR flujo principal con el rol nuevo: el POST crea el Contador y muestra «Cuenta creada»."""
        self.entrar_como_gerente()

        respuesta = self.client.post(
            reverse("core:usuario_nuevo"),
            {"rol": "contador", "nombre": "Carolina", "apellido": "Vega", "email": "carolina@infoponia.com", "telefono": ""},
        )

        self.assertContains(respuesta, "Cuenta creada")
        self.assertTrue(Contador.objects.filter(email="carolina@infoponia.com", is_active=True).exists())

    def test_regla_2_el_segundo_alta_muestra_el_error_y_conserva_lo_escrito(self):
        """SEG-15 y D-85 punto 2: con un Contador activo, el alta de otro vuelve al formulario con el error general arriba
        y con lo escrito; no crea nada."""
        self.entrar_como_gerente()
        crear_cuenta(Contador, email="activo@infoponia.com", nombre="Mario", apellido="Rey")

        respuesta = self.client.post(
            reverse("core:usuario_nuevo"),
            {"rol": "contador", "nombre": "Carolina", "apellido": "Vega", "email": "carolina@infoponia.com", "telefono": ""},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ya hay un Contador activo: Mario Rey")
        self.assertContains(respuesta, "carolina@infoponia.com")
        self.assertFalse(Usuario.objects.filter(email="carolina@infoponia.com").exists())

    def test_regla_1_la_lista_y_la_ficha_muestran_el_rol(self):
        """USR-CNS-USR: la lista y la ficha muestran el nombre y el rol «Contador» (D-85 punto 6). La sigla «CON» del avatar
        sale de ``SIGLAS`` y la ve la propia cuenta en su encabezado (otra prueba) y en las cuentas vinculadas."""
        self.entrar_como_gerente()
        contador = crear_cuenta(Contador, email="contador@infoponia.com", nombre="Carolina", apellido="Vega")

        lista = self.client.get(reverse("core:usuarios"))
        ficha = self.client.get(reverse("core:usuario", args=[contador.pk]))

        for respuesta in (lista, ficha):
            self.assertContains(respuesta, "Carolina Vega")
            self.assertContains(respuesta, "Contador")
        self.assertEqual(sigla(contador), "CON")

    def test_regla_5_la_ventana_de_reactivacion_no_ofrece_confirmar_con_otro_activo(self):
        """USR-MOD-USR regla 5 y D-30: reactivar un Contador con otro activo muestra el motivo, sin botón de confirmar."""
        self.entrar_como_gerente()
        crear_cuenta(Contador, email="activo@infoponia.com", nombre="Mario", apellido="Rey")
        inactivo = crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        respuesta = self.client.get(reverse("core:usuario_reactivar", args=[inactivo.pk]))

        self.assertContains(respuesta, "ya hay un Contador activo")
        self.assertContains(respuesta, "Mario Rey")
        self.assertNotContains(respuesta, 'data-enviando="Reactivando…"')

    def test_regla_5_la_ventana_de_reactivacion_ofrece_confirmar_sin_otro_activo(self):
        """USR-MOD-USR regla 5: sin otro Contador activo, la ventana ofrece el botón de confirmar."""
        self.entrar_como_gerente()
        inactivo = crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        respuesta = self.client.get(reverse("core:usuario_reactivar", args=[inactivo.pk]))

        self.assertContains(respuesta, 'data-enviando="Reactivando…"')
        self.assertNotContains(respuesta, "ya hay un Contador activo")

    def test_regla_1_el_administrador_no_ve_al_contador(self):
        """USR-CNS-USR regla 1 y D-85 punto 3: el Administrador no lo ve en la lista y su ficha da 403."""
        contador = crear_cuenta(Contador, email="contador@infoponia.com", nombre="Carolina", apellido="Vega")
        self.client.force_login(crear_administrador())

        lista = self.client.get(reverse("core:usuarios"))
        ficha = self.client.get(reverse("core:usuario", args=[contador.pk]))

        self.assertNotContains(lista, "Carolina Vega")
        self.assertNotContains(lista, 'value="contador"')
        self.assertEqual(ficha.status_code, 403)

    def test_regla_8_el_gerente_ve_la_auditoria_del_alta_y_de_la_baja(self):
        """SEG-14 y D-36: el alta y la baja del Contador quedan en «Auditoría» y el Gerente las ve (el rol es operativo)."""
        gerente = self.entrar_como_gerente()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.client.post(reverse("core:usuario_baja", args=[contador.pk]))

        registros = RegistroAuditoria.objects.visibles_para(gerente)
        respuesta = self.client.get(reverse("core:auditoria"))

        self.assertEqual(
            list(registros.filter(accion=RegistroAuditoria.Accion.BAJA).values_list("rol", flat=True)), ["gerente"]
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Contador")

    def test_d85_el_contador_entra_a_su_inicio_y_su_menu_es_panel_contabilidad_y_compras(self):
        """SEG-13 y D-85 punto 6: el Contador entra al inicio (con su rol y la sigla), el menú es «Panel de control» y no hay
        «Estadísticas». La entrada «Contabilidad» la suma CON-03a."""
        self.client.force_login(crear_cuenta(Contador, email="contador@infoponia.com"))

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["sigla"], "CON")
        self.assertEqual(respuesta.context["rol_visible"], "Contador")
        self.assertFalse(respuesta.context["modo_campo"])
        self.assertEqual([entrada["texto"] for entrada in respuesta.context["menu"]], ["Panel de control", "Contabilidad", "Pagos a proveedores", "Compras"])  # «Contabilidad» la registra CON-03a; «Pagos a proveedores», CMP-05 (D-87 punto 6); «Compras», CMP-03
        self.assertNotContains(respuesta, "Estadísticas")
        self.assertEqual([texto for texto, _, _ in menu.menu_de(Usuario.Rol.CONTADOR)], ["Panel de control", "Contabilidad", "Pagos a proveedores", "Compras"])

    def test_d85_el_contador_no_abre_los_otros_modulos(self):
        """SEG-13 y D-85 punto 6: cuentas, auditoría, producción, alertas, inventario, comercial, compras, IoT, bitácora y
        configuración le dan 403."""
        self.client.force_login(crear_cuenta(Contador, email="contador@infoponia.com"))

        for nombre in PANTALLAS_VEDADAS:
            with self.subTest(pantalla=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)

    def test_d85_el_contador_opera_su_propio_perfil_y_la_campana(self):
        """D-85 puntos 6 y 7: el Contador usa Mi perfil y la campana como todo rol (no son un módulo)."""
        self.client.force_login(crear_cuenta(Contador, email="contador@infoponia.com"))

        self.assertEqual(self.client.get(reverse("core:mi_perfil")).status_code, 200)
        self.assertIsNotNone(self.client.get(reverse("core:inicio")).context["campana"])
