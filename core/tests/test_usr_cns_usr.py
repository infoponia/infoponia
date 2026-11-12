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
        """USR-CNS-USR precondición a: consulta una cuenta activa de Gerente o de Administrador (las del
        Administrador están más abajo). Un Capataz o un Gerente dado de baja no consultan."""
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

    def test_d30_acciones_permitidas_segun_actor_y_estado(self):
        """D-30, USR-MOD-USR y USR-BAJ-USR (regla 1) y D-28: el Gerente modifica, restablece y da de baja
        una cuenta activa de su alcance, y modifica y reactiva una inactiva; sobre una cuenta fuera de su
        alcance no tiene acciones. Tarea 05a: el Administrador todavía no tiene ninguna (llegan en la 05b)."""
        gerente = crear_gerente()
        activa = crear_cuenta(Capataz, "activa@infoponia.com")
        inactiva = crear_cuenta(Capataz, "inactiva@infoponia.com", activo=False)
        administrador = crear_administrador()

        self.assertEqual(
            servicios.acciones_permitidas(gerente, activa), {"modificar", "restablecer", "baja"}
        )
        self.assertEqual(servicios.acciones_permitidas(gerente, inactiva), {"modificar", "reactivar"})
        self.assertEqual(servicios.acciones_permitidas(gerente, administrador), set())
        for cuenta in (gerente, administrador):
            with self.subTest(cuenta=cuenta.email):
                self.assertEqual(servicios.acciones_permitidas(administrador, cuenta), set())

    # ---- El Administrador (tarea 05a, D-16) ----

    def test_pre_a_rechaza_administrador_inactivo(self):
        """USR-CNS-USR precondición a: el Administrador consulta solo con una cuenta activa; uno dado
        de baja no consulta."""
        crear_administrador()
        inactivo = crear_administrador(email="admin.anterior@infoponia.com")
        inactivo.is_active = False
        inactivo.save()

        with self.assertRaises(PermissionDenied):
            list(servicios.consultar_usuarios(inactivo))

    def test_regla_1_administrador_ve_gerentes_y_administradores_incluida_la_suya(self):
        """USR-CNS-USR regla 1 y D-16: el Administrador consulta la cuenta del Gerente (también las de
        Gerentes anteriores, inactivos) y las de los Administradores, incluida la suya."""
        administrador = crear_administrador()
        otro_administrador = crear_administrador(email="admin2@infoponia.com")
        gerente = crear_gerente()
        gerente_anterior = crear_gerente(email="gerente.anterior@infoponia.com", activo=False)
        crear_cuenta(Capataz, "capataz@infoponia.com")

        resultado = servicios.consultar_usuarios(administrador)

        self.assertEqual(
            ids(resultado),
            {administrador.pk, otro_administrador.pk, gerente.pk, gerente_anterior.pk},
        )

    def test_regla_1_administrador_no_ve_cuentas_de_los_otros_roles(self):
        """USR-CNS-USR regla 1 y D-16: el Administrador no consulta las cuentas de Agrónomo, Capataz,
        Vendedor, Transportista ni Técnico (las gestiona el Gerente)."""
        administrador = crear_administrador()
        for clase in (Agronomo, Capataz, Vendedor, Transportista, Tecnico):
            crear_cuenta(clase, f"{clase.ROL.value}@infoponia.com")

        resultado = servicios.consultar_usuarios(administrador)

        self.assertEqual(ids(resultado), {administrador.pk})

    def test_regla_2_administrador_filtra_por_rol_administrador(self):
        """USR-CNS-USR regla 2 y D-10: el Administrador filtra por «Administrador» (que no es un valor de
        ``rol``: es un superusuario sin rol) y por «Gerente»."""
        administrador = crear_administrador()
        otro_administrador = crear_administrador(email="admin2@infoponia.com")
        gerente = crear_gerente()

        self.assertEqual(
            ids(servicios.consultar_usuarios(administrador, rol=ADMINISTRADOR)),
            {administrador.pk, otro_administrador.pk},
        )
        self.assertEqual(
            ids(servicios.consultar_usuarios(administrador, rol=Usuario.Rol.GERENTE)), {gerente.pk}
        )

    def test_regla_1_administrador_obtiene_ficha_de_gerente_y_no_de_capataz(self):
        """USR-CNS-USR regla 1, SEG-13 y D-28: el Administrador obtiene la ficha del Gerente, de otro
        Administrador y la suya; la de un Capataz existe pero está fuera de su alcance."""
        administrador = crear_administrador()
        otro_administrador = crear_administrador(email="admin2@infoponia.com")
        gerente = crear_gerente()
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")

        for cuenta in (gerente, otro_administrador, administrador):
            with self.subTest(cuenta=cuenta.email):
                self.assertEqual(servicios.obtener_cuenta(administrador, cuenta.pk).pk, cuenta.pk)
        with self.assertRaises(PermissionDenied):
            servicios.obtener_cuenta(administrador, capataz.pk)


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

    # ---- El Administrador (tarea 05a, D-16) ----

    def test_flujo_principal_administrador_ve_la_lista_de_cuentas(self):
        """USR-CNS-USR flujo principal, reglas 1 y 2, D-16 y prototipo (vUsuarios): el Administrador ve
        «Cuentas» con «Alta de Gerente», el texto de su alcance, el Gerente y los Administradores (la suya
        marcada «(vos)», con el rol «Administrador») y el filtro de rol con «Gerente» y «Administrador»;
        no ve las cuentas de los otros roles."""
        administrador = crear_administrador()
        crear_administrador(email="admin2@infoponia.com")
        crear_gerente()
        crear_cuenta(Capataz, "capataz@infoponia.com")
        self.client.force_login(administrador)

        respuesta = self.client.get(reverse("core:usuarios"))

        self.assertContains(respuesta, "<h1>Cuentas</h1>", html=True)
        self.assertContains(respuesta, "Alta de Gerente")
        self.assertContains(respuesta, "Gestionás la cuenta del Gerente y las de los Administradores.")
        self.assertNotContains(respuesta, "Nuevo usuario")
        self.assertContains(respuesta, "gerente@infoponia.com")
        self.assertContains(respuesta, "admin2@infoponia.com")
        self.assertContains(respuesta, "(vos)", count=1)
        self.assertContains(respuesta, "<td>Administrador</td>", count=2, html=True)
        self.assertNotContains(respuesta, "capataz@infoponia.com")
        self.assertContains(respuesta, '<option value="gerente">Gerente</option>', html=True)
        self.assertContains(respuesta, '<option value="administrador">Administrador</option>', html=True)
        self.assertNotContains(respuesta, 'value="capataz"')

    def test_seg13_administrador_recibe_403_en_ficha_de_capataz(self):
        """SEG-13, USR-CNS-USR regla 1 y D-28: la ficha de un Capataz existe pero está fuera del alcance
        del Administrador: 403 con el mensaje."""
        self.client.force_login(crear_administrador())
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")

        respuesta = self.client.get(reverse("core:usuario", args=[capataz.pk]))

        self.assertContains(
            respuesta, "Esa cuenta no está dentro de las que gestionás.", status_code=403
        )

    def test_d30_ficha_del_administrador_no_ofrece_acciones_de_la_05b(self):
        """D-30 (tarea 05a): mientras modificar, restablecer, reactivar y dar de baja sean solo del
        Gerente, la ficha no le muestra al Administrador botones que lo lleven a un 403. Vale para el
        Gerente activo, uno inactivo, otro Administrador y la propia cuenta («(vos)»)."""
        administrador = crear_administrador()
        cuentas = [
            crear_gerente(),
            crear_gerente(email="gerente.anterior@infoponia.com", activo=False),
            crear_administrador(email="admin2@infoponia.com"),
            administrador,
        ]
        self.client.force_login(administrador)

        for cuenta in cuentas:
            with self.subTest(cuenta=cuenta.email):
                respuesta = self.client.get(reverse("core:usuario", args=[cuenta.pk]))
                self.assertEqual(respuesta.status_code, 200)
                for texto in ("Modificar datos", "Restablecer contraseña", "Reactivar cuenta", "Dar de baja"):
                    self.assertNotContains(respuesta, texto)
                for nombre in ("usuario_modificar", "usuario_restablecer", "usuario_reactivar", "usuario_baja"):
                    self.assertNotContains(respuesta, reverse(f"core:{nombre}", args=[cuenta.pk]))
        propia = self.client.get(reverse("core:usuario", args=[administrador.pk]))
        self.assertContains(propia, "(vos)")
        self.assertContains(propia, "<dd>Administrador</dd>", html=True)
