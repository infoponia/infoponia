# Pruebas de USR-CNS-USR (Consultar Usuario) y de lo que cita: alcance del Gerente (regla 1), filtros y
# búsqueda (regla 2), datos visibles (regla 3), sin auditoría (regla 4, SEG-14) y acceso según el rol
# (SEG-13), más D-28. Las de servicio llaman a core.servicios.consultar_usuarios y obtener_cuenta; las
# de vista (integración) usan el cliente de prueba contra las pantallas. Cada prueba arma sus propios
# datos. Los servicios se llaman a través del módulo (servicios.x) para que, mientras no existan, cada
# prueba falle por separado en vez de romper la importación del archivo.

from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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


def crear_cuenta(clase, email, nombre="Nombre", apellido="Apellido", activo=True):
    """Crea una cuenta del rol de ``clase`` con la contraseña de prueba."""
    return clase.objects.create_user(
        email=email, password=CLAVE, first_name=nombre, last_name=apellido, is_active=activo
    )


def ids(cuentas):
    """Conjunto de ids de un QuerySet o lista de cuentas."""
    return {cuenta.pk for cuenta in cuentas}


class UsrCnsUsrServicioTests(TestCase):
    """Reglas de USR-CNS-USR en los servicios ``consultar_usuarios`` y ``obtener_cuenta``."""

    # ---- Precondición ----

    def test_pre_a_rechaza_actor_sin_cuenta_activa_de_gerente(self):
        """USR-CNS-USR precondición a: solo consulta una cuenta activa de Gerente (el Administrador
        llega en la tarea 05). Un Capataz o un Gerente dado de baja no consultan."""
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")
        gerente_inactivo = crear_gerente(activo=False)

        for actor in (capataz, gerente_inactivo):
            with self.subTest(actor=actor.email):
                with self.assertRaises(PermissionDenied):
                    list(servicios.consultar_usuarios(actor))

    # ---- Reglas del caso de uso ----

    def test_regla_1_gerente_ve_solo_los_cinco_roles(self):
        """USR-CNS-USR regla 1: el Gerente consulta las cuentas de Agrónomo, Capataz, Vendedor,
        Transportista y Técnico; no ve la suya, ni otros Gerentes, ni Administradores (D-16)."""
        gerente = crear_gerente()
        crear_gerente(email="gerente.anterior@infoponia.com", activo=False)
        crear_administrador()
        del_alcance = [
            crear_cuenta(Agronomo, "agronomo@infoponia.com"),
            crear_cuenta(Capataz, "capataz@infoponia.com"),
            crear_cuenta(Vendedor, "vendedor@infoponia.com"),
            crear_cuenta(Transportista, "transportista@infoponia.com"),
            crear_cuenta(Tecnico, "tecnico@infoponia.com"),
        ]

        resultado = servicios.consultar_usuarios(gerente)

        self.assertEqual(ids(resultado), ids(del_alcance))

    def test_regla_1_cuenta_fuera_de_alcance_rechaza_acceso(self):
        """USR-CNS-USR regla 1, SEG-13 y D-28: la ficha de una cuenta que existe pero está fuera del
        alcance (la propia, otro Gerente, un Administrador) se rechaza; una del alcance se obtiene."""
        gerente = crear_gerente()
        otro_gerente = crear_gerente(email="gerente.anterior@infoponia.com", activo=False)
        administrador = crear_administrador()
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")

        for cuenta in (gerente, otro_gerente, administrador):
            with self.subTest(cuenta=cuenta.email):
                with self.assertRaises(PermissionDenied):
                    servicios.obtener_cuenta(gerente, cuenta.pk)

        self.assertEqual(servicios.obtener_cuenta(gerente, capataz.pk).pk, capataz.pk)

    def test_regla_1_id_inexistente_da_404(self):
        """USR-CNS-USR regla 1 y D-28: un id que no corresponde a ninguna cuenta da 404."""
        gerente = crear_gerente()

        with self.assertRaises(Http404):
            servicios.obtener_cuenta(gerente, 999999)

    def test_regla_2_filtra_por_rol(self):
        """USR-CNS-USR regla 2: se filtra por rol."""
        gerente = crear_gerente()
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")
        crear_cuenta(Vendedor, "vendedor@infoponia.com")

        resultado = servicios.consultar_usuarios(gerente, rol=Usuario.Rol.CAPATAZ)

        self.assertEqual(ids(resultado), {capataz.pk})

    def test_regla_2_filtra_por_estado(self):
        """USR-CNS-USR regla 2: se filtra por estado (activo o inactivo)."""
        gerente = crear_gerente()
        activo = crear_cuenta(Capataz, "activo@infoponia.com")
        inactivo = crear_cuenta(Capataz, "inactivo@infoponia.com", activo=False)

        self.assertEqual(ids(servicios.consultar_usuarios(gerente, estado="activo")), {activo.pk})
        self.assertEqual(
            ids(servicios.consultar_usuarios(gerente, estado="inactivo")), {inactivo.pk}
        )

    def test_regla_2_busca_por_nombre_apellido_o_email(self):
        """USR-CNS-USR regla 2: se busca por nombre, apellido o email."""
        gerente = crear_gerente()
        ana = crear_cuenta(Capataz, "a.perez@infoponia.com", nombre="Ana", apellido="Pérez")
        bruno = crear_cuenta(Vendedor, "b.gomez@infoponia.com", nombre="Bruno", apellido="Gómez")
        carla = crear_cuenta(Tecnico, "carla@huerta.com", nombre="Carla", apellido="Ruiz")

        casos = {"Ana": {ana.pk}, "Gómez": {bruno.pk}, "huerta": {carla.pk}}
        for busqueda, esperado in casos.items():
            with self.subTest(busqueda=busqueda):
                resultado = servicios.consultar_usuarios(gerente, busqueda=busqueda)
                self.assertEqual(ids(resultado), esperado)

    def test_regla_2_busqueda_no_distingue_mayusculas(self):
        """USR-CNS-USR regla 2: la búsqueda no distingue mayúsculas."""
        gerente = crear_gerente()
        ana = crear_cuenta(Capataz, "a.perez@infoponia.com", nombre="Ana", apellido="Pérez")

        for busqueda in ("ANA", "ana", "A.PEREZ@INFOPONIA"):
            with self.subTest(busqueda=busqueda):
                resultado = servicios.consultar_usuarios(gerente, busqueda=busqueda)
                self.assertEqual(ids(resultado), {ana.pk})

    def test_regla_2_busqueda_exige_todas_las_palabras(self):
        """USR-CNS-USR regla 2 y D-28: con varias palabras, la cuenta tiene que coincidir con todas,
        cada una en el nombre, el apellido o el email."""
        gerente = crear_gerente()
        ana = crear_cuenta(Capataz, "a.perez@infoponia.com", nombre="Ana", apellido="Pérez")
        crear_cuenta(Vendedor, "b.gomez@infoponia.com", nombre="Bruno", apellido="Gómez")

        self.assertEqual(ids(servicios.consultar_usuarios(gerente, busqueda="Ana Pérez")), {ana.pk})
        self.assertEqual(ids(servicios.consultar_usuarios(gerente, busqueda="Ana infoponia")), {ana.pk})
        self.assertEqual(ids(servicios.consultar_usuarios(gerente, busqueda="Ana Gómez")), set())

    def test_regla_4_consulta_no_crea_registro_de_auditoria(self):
        """USR-CNS-USR regla 4, postcondición a y SEG-14: consultar no audita ni cambia nada."""
        gerente = crear_gerente()
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")

        list(servicios.consultar_usuarios(gerente, busqueda="capataz"))
        servicios.obtener_cuenta(gerente, capataz.pk)

        self.assertEqual(RegistroAuditoria.objects.count(), 0)


def dar_temporal_vencida(cuenta):
    """Le da a la cuenta una contraseña temporal generada hace 8 días (ya venció, SEG-04)."""
    cuenta.asignar_contrasena_temporal()
    cuenta.fecha_contrasena_temporal = timezone.now() - timedelta(days=8)
    cuenta.save()


class UsrCnsUsrVistaTests(TestCase):
    """Flujo principal de USR-CNS-USR en las pantallas (vUsuarios y vUsuario), con el cliente de Django."""

    def entrar_como_gerente(self):
        """Crea un Gerente, abre su sesión y lo devuelve."""
        gerente = crear_gerente()
        self.client.force_login(gerente)
        return gerente

    def test_flujo_principal_lista_las_cuentas_del_alcance(self):
        """USR-CNS-USR flujo principal y regla 1: la lista muestra las cuentas del alcance y no la del
        Gerente ni las de Administradores."""
        gerente = self.entrar_como_gerente()
        crear_administrador()
        crear_cuenta(Capataz, "capataz@infoponia.com", nombre="Carlos", apellido="Peña")
        crear_cuenta(Vendedor, "vendedor@infoponia.com", nombre="Viviana", apellido="Rey")

        respuesta = self.client.get(reverse("core:usuarios"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "capataz@infoponia.com")
        self.assertContains(respuesta, "vendedor@infoponia.com")
        self.assertContains(respuesta, "Carlos Peña")
        self.assertNotContains(respuesta, "admin@infoponia.com")
        # El email del Gerente sí aparece en su propio menú de cuenta: se comprueba la tabla.
        emails_en_la_tabla = {cuenta.email for cuenta in respuesta.context["cuentas"]}
        self.assertEqual(emails_en_la_tabla, {"capataz@infoponia.com", "vendedor@infoponia.com"})
        self.assertNotIn(gerente.email, emails_en_la_tabla)

    def test_flujo_principal_muestra_la_ficha(self):
        """USR-CNS-USR flujo principal y regla 3: la ficha muestra nombre, apellido, email, teléfono,
        rol y estado."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Tecnico, "tecnico@infoponia.com", nombre="Teresa", apellido="Lugo")
        cuenta.telefono = "+54 376 400-1001"
        cuenta.save()

        respuesta = self.client.get(reverse("core:usuario", args=[cuenta.pk]))

        self.assertEqual(respuesta.status_code, 200)
        for texto in ("Teresa", "Lugo", "tecnico@infoponia.com", "+54 376 400-1001", "Técnico", "Activo"):
            self.assertContains(respuesta, texto)

    def test_regla_2_filtro_con_htmx_devuelve_solo_la_tabla(self):
        """USR-CNS-USR regla 2: un pedido de HTMX con filtros devuelve solo la tabla (sin la pantalla
        entera), ya filtrada; el mismo pedido sin HTMX devuelve la pantalla entera."""
        self.entrar_como_gerente()
        crear_cuenta(Capataz, "capataz@infoponia.com")
        crear_cuenta(Vendedor, "vendedor@infoponia.com")
        url = reverse("core:usuarios")

        parcial = self.client.get(url, {"rol": "capataz"}, headers={"HX-Request": "true"})
        entera = self.client.get(url, {"rol": "capataz"})

        self.assertContains(parcial, "capataz@infoponia.com")
        self.assertNotContains(parcial, "vendedor@infoponia.com")
        self.assertNotContains(parcial, "<html")
        self.assertContains(entera, "<html")
        self.assertContains(entera, "capataz@infoponia.com")
        self.assertNotContains(entera, "vendedor@infoponia.com")

    def test_regla_3_ficha_indica_temporal_vencida(self):
        """USR-CNS-USR regla 3: la ficha y la lista indican si la contraseña temporal sigue sin cambiar
        y si venció; una vigente se distingue de una vencida."""
        self.entrar_como_gerente()
        vencida = crear_cuenta(Capataz, "vencida@infoponia.com")
        dar_temporal_vencida(vencida)
        vigente = crear_cuenta(Vendedor, "vigente@infoponia.com")
        vigente.asignar_contrasena_temporal()
        vigente.save()

        ficha_vencida = self.client.get(reverse("core:usuario", args=[vencida.pk]))
        ficha_vigente = self.client.get(reverse("core:usuario", args=[vigente.pk]))
        lista = self.client.get(reverse("core:usuarios"))

        self.assertContains(ficha_vencida, "Temporal vencida")
        self.assertNotContains(ficha_vigente, "Temporal vencida")
        self.assertContains(ficha_vigente, "Contraseña temporal")
        self.assertContains(lista, "Temporal vencida")

    def test_regla_3_ficha_no_muestra_la_contrasena(self):
        """USR-CNS-USR regla 3 y SEG-02: nunca se muestra una contraseña, ni su resumen."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz, "capataz@infoponia.com")
        temporal = cuenta.asignar_contrasena_temporal()
        cuenta.save()

        ficha = self.client.get(reverse("core:usuario", args=[cuenta.pk]))
        lista = self.client.get(reverse("core:usuarios"))

        for respuesta in (ficha, lista):
            self.assertNotContains(respuesta, temporal)
            self.assertNotContains(respuesta, cuenta.password)
            self.assertNotContains(respuesta, "pbkdf2")

    def test_seg13_capataz_recibe_403_en_usuarios(self):
        """SEG-13: un Capataz no accede a la lista ni a la ficha; recibe 403 con mensaje que nombra su rol."""
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")
        otro = crear_cuenta(Vendedor, "vendedor@infoponia.com")
        self.client.force_login(capataz)

        for url in (reverse("core:usuarios"), reverse("core:usuario", args=[otro.pk])):
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertContains(respuesta, "Tu cuenta de Capataz no tiene acceso", status_code=403)

    def test_seg13_ficha_fuera_de_alcance_recibe_403(self):
        """SEG-13, USR-CNS-USR regla 1 y D-28: la ficha de una cuenta fuera del alcance (un Administrador,
        otro Gerente) da 403 con el mensaje en la plantilla 403 del sistema; un id inexistente, 404."""
        self.entrar_como_gerente()
        administrador = crear_administrador()
        anterior = crear_gerente(email="anterior@infoponia.com", activo=False)

        for cuenta in (administrador, anterior):
            with self.subTest(cuenta=cuenta.email):
                respuesta = self.client.get(reverse("core:usuario", args=[cuenta.pk]))
                self.assertContains(
                    respuesta, "Esa cuenta no está dentro de las que gestionás.", status_code=403
                )
                self.assertContains(respuesta, "Sin acceso", status_code=403)
        self.assertEqual(self.client.get(reverse("core:usuario", args=[999999])).status_code, 404)

    def test_d25_menu_del_gerente_muestra_usuarios_y_seguridad(self):
        """D-25 (el menú muestra solo lo que existe): el Gerente ve «Usuarios y seguridad», activo en la
        lista; un Capataz (sin menú lateral) no."""
        self.entrar_como_gerente()

        respuesta = self.client.get(reverse("core:usuarios"))

        self.assertContains(respuesta, "Usuarios y seguridad")
        self.assertContains(respuesta, f'href="{reverse("core:usuarios")}"')
        self.assertContains(respuesta, 'aria-current="page"')
        self.client.logout()
        self.client.force_login(crear_cuenta(Capataz, "capataz@infoponia.com"))
        self.assertNotContains(self.client.get(reverse("core:inicio")), "Usuarios y seguridad")
