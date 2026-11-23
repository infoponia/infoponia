# Pruebas de las pantallas de «Compras» → «Proveedores» (CMP-01, paso 4; integración con el cliente de prueba de Django): la lista con sus filtros
# (CMP-CNS-PRV), la ficha, el formulario de alta con la oferta de reactivar (CMP-ALT-PRV), la modificación (CMP-MOD-PRV), la reactivación y la
# ventana de la baja (CMP-BAJ-PRV), con HTMX y sin JavaScript. El Gerente escribe; el Agrónomo solo consulta y no ve botones de cambio; los demás
# roles reciben 403 (SEG-13) y sin sesión van al inicio de sesión. Fuente: docs/casos_de_uso/compras/proveedores.md y D-30.

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from compras.models import Proveedor
from compras.tests.fabricas import con_guiones, cuit_valido, datos_de_alta, proveedor, tipo_de_insumo
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from maestros.extensiones import Impedimento
from maestros.tests.fabricas import crear_agronomo, crear_vendedor

HX = {"HTTP_HX_REQUEST": "true"}


def datos_de_formulario(**cambios):
    """Lo que envía el formulario de un alta (jurídica, CUIT número 1); ``cambios`` pisa lo que se indique. Las categorías van como lista."""
    datos = datos_de_alta(cuit=con_guiones(cuit_valido(1)))
    datos.update(cambios)
    return datos


class ProveedoresVistasBase(TestCase):
    """Un Gerente y un Agrónomo; las rutas de cada pantalla. La sesión arranca como Gerente."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.client.force_login(self.gerente)
        self.lista = reverse("compras:proveedores")
        self.nuevo = reverse("compras:proveedor_nuevo")

    def url(self, nombre, p):
        return reverse(f"compras:{nombre}", args=[p.pk])


class AccesoAProveedoresVistaTests(ProveedoresVistasBase):
    """Quién llega a cada pantalla (precondición a de cada caso de uso, SEG-13)."""

    def rutas_de_escritura(self):
        p = proveedor(n=1)
        i = proveedor("Agro Norte S. R. L.", n=2, activo=False)
        return [self.nuevo, self.url("proveedor_editar", p), self.url("proveedor_baja", p), self.url("proveedor_reactivar", i)]

    def rutas_de_lectura(self):
        return [self.lista, self.url("proveedor_ficha", proveedor(n=3))]

    def test_pre_a_el_gerente_y_el_agronomo_consultan(self):
        """CMP-CNS-PRV precondición a: Gerente y Agrónomo llegan a la lista y a la ficha."""
        rutas = self.rutas_de_lectura()
        for cuenta in (self.gerente, self.agronomo):
            self.client.force_login(cuenta)
            for ruta in rutas:
                with self.subTest(rol=cuenta.rol, ruta=ruta):
                    self.assertEqual(self.client.get(ruta).status_code, 200)

    def test_pre_a_los_demas_roles_no_consultan(self):
        """CMP-CNS-PRV precondición a: Capataz, Vendedor y Administrador reciben 403."""
        rutas = self.rutas_de_lectura()
        for cuenta in (crear_capataz(), crear_vendedor(), crear_administrador()):
            self.client.force_login(cuenta)
            for ruta in rutas:
                with self.subTest(cuenta=cuenta.email, ruta=ruta):
                    self.assertEqual(self.client.get(ruta).status_code, 403)

    def test_pre_a_el_agronomo_no_da_de_alta_ni_modifica_ni_da_de_baja_ni_reactiva(self):
        """CMP-ALT/MOD/BAJ-PRV precondición a: el Agrónomo recibe 403 en cada ruta de escritura, con GET y con POST, y no cambia nada."""
        rutas = self.rutas_de_escritura()
        antes = (Proveedor.objects.count(), Proveedor.objects.filter(estado_proveedor="activo").count())
        self.client.force_login(self.agronomo)
        for ruta in rutas:
            for metodo in (self.client.get, self.client.post):
                with self.subTest(ruta=ruta, metodo=metodo.__name__):
                    self.assertEqual(metodo(ruta, datos_de_formulario() if metodo == self.client.post else None).status_code, 403)
        self.assertEqual((Proveedor.objects.count(), Proveedor.objects.filter(estado_proveedor="activo").count()), antes)
        self.assertFalse(RegistroAuditoria.objects.filter(accion__endswith="_proveedor").exists())

    def test_pre_a_los_demas_roles_no_escriben(self):
        """CMP-ALT/MOD/BAJ-PRV precondición a: Capataz, Vendedor y Administrador reciben 403 en cada ruta de escritura."""
        rutas = self.rutas_de_escritura()
        for cuenta in (crear_capataz(), crear_vendedor(), crear_administrador()):
            self.client.force_login(cuenta)
            for ruta in rutas:
                with self.subTest(cuenta=cuenta.email, ruta=ruta):
                    self.assertEqual(self.client.get(ruta).status_code, 403)

    def test_sin_sesion_va_al_inicio_de_sesion(self):
        """SEG-13: toda pantalla exige sesión."""
        rutas = self.rutas_de_lectura() + self.rutas_de_escritura()
        self.client.logout()
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn("login", respuesta["Location"].lower().replace("iniciar", "login"))


class MenuDeComprasVistaTests(ProveedoresVistasBase):
    """«Compras» en el menú lateral (D-25: el menú muestra solo lo que existe)."""

    def test_el_gerente_y_el_agronomo_ven_compras_en_el_menu(self):
        """D-87 punto 6: «Compras» para Agrónomo y Gerente; abre en su primera pestaña, «Pedidos» (CMP-02a; con CMP-01 apuntaba a «Proveedores», la única que había,
        y el estudiante aprobó el cambio el 23/11/2026). «Proveedores» sigue a un clic: es la otra pestaña."""
        for cuenta in (self.gerente, self.agronomo):
            self.client.force_login(cuenta)
            respuesta = self.client.get(reverse("core:inicio"))
            self.assertContains(respuesta, reverse("compras:pedidos"))
            self.assertContains(self.client.get(reverse("compras:pedidos")), reverse("compras:proveedores"))

    def test_otros_roles_no_ven_compras_en_el_menu(self):
        """El Vendedor no tiene «Compras»."""
        self.client.force_login(crear_vendedor())
        self.assertNotContains(self.client.get(reverse("core:inicio")), reverse("compras:pedidos"))


class ListaDeProveedoresVistaTests(ProveedoresVistasBase):
    """CMP-CNS-PRV: la lista, sus filtros y los botones según el rol."""

    def setUp(self):
        super().setUp()
        self.limpieza = tipo_de_insumo("Limpieza")
        self.sur = proveedor("Semillas del Sur S. A.", n=1, telefono="376 400-1001", especialidades=[self.limpieza])
        self.norte = proveedor("Agro Norte S. R. L.", n=2, activo=False)

    def test_regla_3_la_lista_muestra_nombre_cuit_contacto_categorias_y_estado(self):
        """CMP-CNS-PRV regla 3: razón social, CUIT, correo, teléfono, categorías activas y estado. Por defecto, los activos."""
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, "Semillas del Sur S. A.")
        self.assertContains(respuesta, con_guiones(cuit_valido(1)))
        self.assertContains(respuesta, "ventas@semillasdelsur.com")
        self.assertContains(respuesta, "376 400-1001")
        self.assertContains(respuesta, "Limpieza")
        self.assertNotContains(respuesta, "Agro Norte S. R. L.")

    def test_regla_1_se_ven_tambien_los_inactivos_con_el_filtro_todos(self):
        """CMP-CNS-PRV regla 1 y 2: con el filtro de estado se ven los inactivos o todos."""
        self.assertContains(self.client.get(self.lista, {"estado": "inactivo"}), "Agro Norte S. R. L.")
        todos = self.client.get(self.lista, {"estado": ""})
        self.assertContains(todos, "Agro Norte S. R. L.")
        self.assertContains(todos, "Semillas del Sur S. A.")

    def test_regla_2_filtra_por_texto_y_por_tipo_de_insumo(self):
        """CMP-CNS-PRV regla 2: texto (nombre o CUIT) y categoría; combinados."""
        self.assertNotContains(self.client.get(self.lista, {"q": "norte", "estado": ""}), "Semillas del Sur S. A.")
        self.assertContains(self.client.get(self.lista, {"q": cuit_valido(1)}), "Semillas del Sur S. A.")
        con_categoria = self.client.get(self.lista, {"categoria": self.limpieza.pk, "estado": ""})
        self.assertContains(con_categoria, "Semillas del Sur S. A.")
        self.assertNotContains(con_categoria, "Agro Norte S. R. L.")

    def test_regla_2_un_filtro_sin_resultados_lo_dice_y_ofrece_quitarlo(self):
        """docs/patrones/abm.md, sección 7: el estado vacío con filtros."""
        respuesta = self.client.get(self.lista, {"q": "zzz"})
        self.assertContains(respuesta, "No hay proveedores con esos filtros.")
        self.assertContains(respuesta, "Quitar filtros")

    def test_la_lista_vacia_invita_al_gerente_a_registrar_el_primero(self):
        """El estado vacío: el Gerente ve cómo seguir; el Agrónomo, quién los carga."""
        Proveedor.objects.all().delete()
        self.assertContains(self.client.get(self.lista), "Registrá el primero")
        self.client.force_login(self.agronomo)
        self.assertContains(self.client.get(self.lista), "Los carga el Gerente")

    def test_regla_5_el_gerente_ve_nuevo_editar_y_reactivar(self):
        """CMP-CNS-PRV regla 5: el Gerente puede ir a alta, modificar y reactivar."""
        respuesta = self.client.get(self.lista, {"estado": ""})
        self.assertContains(respuesta, self.nuevo)
        self.assertContains(respuesta, self.url("proveedor_editar", self.sur))
        self.assertContains(respuesta, self.url("proveedor_reactivar", self.norte))

    def test_regla_5_el_agronomo_ve_la_lista_sin_botones_de_cambio(self):
        """CMP-CNS-PRV regla 5 y D-30: el Agrónomo ve la lista y la ficha, sin «Nuevo proveedor», «Editar» ni «Reactivar»."""
        self.client.force_login(self.agronomo)
        respuesta = self.client.get(self.lista, {"estado": ""})
        self.assertContains(respuesta, "Semillas del Sur S. A.")
        for ruta in (self.nuevo, self.url("proveedor_editar", self.sur), self.url("proveedor_reactivar", self.norte)):
            self.assertNotContains(respuesta, ruta)
        self.assertContains(respuesta, self.url("proveedor_ficha", self.sur))

    def test_la_lista_no_audita(self):
        """CMP-CNS-PRV regla 6 (SEG-14): consultar no deja registro."""
        antes = RegistroAuditoria.objects.count()
        self.client.get(self.lista)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_la_lista_solo_acepta_lecturas(self):
        """Una lista no se envía: POST da 405."""
        self.assertEqual(self.client.post(self.lista).status_code, 405)


class FichaDeProveedorVistaTests(ProveedoresVistasBase):
    """CMP-CNS-PRV regla 4 y 5: la ficha y sus botones."""

    def setUp(self):
        super().setUp()
        self.limpieza = tipo_de_insumo("Limpieza")
        self.vieja = tipo_de_insumo("Vieja", activo=False)
        self.sur = proveedor("Semillas del Sur S. A.", n=1, especialidades=[self.limpieza, self.vieja])
        self.norte = proveedor("Agro Norte S. R. L.", n=2, activo=False)

    def test_regla_4_la_ficha_muestra_los_datos_y_solo_las_categorias_activas(self):
        """CMP-CNS-PRV regla 4 y CMP-MOD-PRV regla 4: los datos del proveedor; las categorías dadas de baja no se muestran."""
        respuesta = self.client.get(self.url("proveedor_ficha", self.sur))
        self.assertContains(respuesta, con_guiones(cuit_valido(1)))
        self.assertContains(respuesta, "ventas@semillasdelsur.com")
        self.assertContains(respuesta, "Limpieza")
        self.assertNotContains(respuesta, "Vieja")

    def test_regla_5_el_gerente_ve_editar_y_dar_de_baja_de_un_activo(self):
        """CMP-CNS-PRV regla 5: sobre un activo, modificar y dar de baja (no reactivar)."""
        respuesta = self.client.get(self.url("proveedor_ficha", self.sur))
        self.assertContains(respuesta, self.url("proveedor_editar", self.sur))
        self.assertContains(respuesta, self.url("proveedor_baja", self.sur))
        self.assertNotContains(respuesta, self.url("proveedor_reactivar", self.sur))

    def test_regla_5_el_gerente_solo_reactiva_a_un_inactivo(self):
        """CMP-CNS-PRV regla 5: sobre un inactivo, solo reactivarlo."""
        respuesta = self.client.get(self.url("proveedor_ficha", self.norte))
        self.assertContains(respuesta, self.url("proveedor_reactivar", self.norte))
        self.assertNotContains(respuesta, self.url("proveedor_editar", self.norte))
        self.assertNotContains(respuesta, self.url("proveedor_baja", self.norte))

    def test_regla_5_el_agronomo_ve_la_ficha_sin_botones(self):
        """CMP-CNS-PRV regla 5 y D-30: el Agrónomo solo consulta."""
        self.client.force_login(self.agronomo)
        for p in (self.sur, self.norte):
            respuesta = self.client.get(self.url("proveedor_ficha", p))
            self.assertEqual(respuesta.status_code, 200)
            for nombre in ("proveedor_editar", "proveedor_baja", "proveedor_reactivar"):
                self.assertNotContains(respuesta, self.url(nombre, p))

    def test_la_ficha_de_un_proveedor_que_no_existe_da_404(self):
        """docs/patrones/abm.md, sección 6."""
        self.assertEqual(self.client.get(reverse("compras:proveedor_ficha", args=[999999])).status_code, 404)


class AltaDeProveedorVistaTests(ProveedoresVistasBase):
    """CMP-ALT-PRV: el formulario, los errores por campo y la oferta de reactivar."""

    def test_flujo_principal_el_formulario_se_muestra_y_el_alta_lleva_a_la_ficha(self):
        """CMP-ALT-PRV flujo principal: se completa el formulario, se registra, se avisa y se ve la ficha del proveedor creado."""
        limpieza = tipo_de_insumo("Limpieza")
        self.assertContains(self.client.get(self.nuevo), "Registrar proveedor")
        respuesta = self.client.post(self.nuevo, {**datos_de_formulario(), "especialidades": [limpieza.pk]}, follow=True)
        creado = Proveedor.objects.get()
        self.assertRedirects(respuesta, self.url("proveedor_ficha", creado))
        self.assertContains(respuesta, "Registramos a Semillas del Sur S. A.")
        self.assertEqual((creado.cuit_proveedor, list(creado.especialidades.all())), (cuit_valido(1), [limpieza]))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_proveedor").count(), 1)

    def test_regla_1_los_errores_se_muestran_por_campo_y_conserva_lo_escrito(self):
        """docs/patrones/abm.md, sección 7: errores junto al campo y el formulario conserva lo escrito (incluidas las categorías marcadas)."""
        limpieza = tipo_de_insumo("Limpieza")
        respuesta = self.client.post(
            self.nuevo, {**datos_de_formulario(razon_social="Semillas del Sur", email="", telefono="abc"), "especialidades": [limpieza.pk]}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ingresá el correo")
        self.assertContains(respuesta, "El teléfono solo puede tener")
        self.assertContains(respuesta, 'value="Semillas del Sur"')
        self.assertContains(respuesta, f'value="{limpieza.pk}" checked')
        self.assertEqual(Proveedor.objects.count(), 0)

    def test_regla_2_un_cuit_de_un_activo_se_rechaza_con_un_mensaje_claro(self):
        """CMP-ALT-PRV regla 2: el CUIT no se repite: «Ya está registrado como…»."""
        proveedor("Agro Norte S. R. L.", n=1)
        respuesta = self.client.post(self.nuevo, datos_de_formulario())
        self.assertContains(respuesta, "Ya está registrado como Agro Norte S. R. L.")
        self.assertNotContains(respuesta, 'name="reactivar_id"')
        self.assertEqual(Proveedor.objects.count(), 1)

    def test_regla_2_un_cuit_de_un_inactivo_ofrece_reactivarlo(self):
        """CMP-ALT-PRV regla 2: el CUIT de un proveedor dado de baja ofrece reactivarlo, con los datos escritos."""
        inactivo = proveedor("Agro Norte S. R. L.", n=1, activo=False)
        respuesta = self.client.post(self.nuevo, datos_de_formulario())
        self.assertContains(respuesta, "Reactivar con estos datos")
        self.assertContains(respuesta, f'name="reactivar_id" value="{inactivo.pk}"')
        self.assertEqual(Proveedor.objects.count(), 1)

    def test_post_c_reactivar_con_los_datos_escritos_reactiva_al_proveedor_y_no_crea_otro(self):
        """CMP-ALT-PRV postcondición c: «Reactivar con estos datos» pasa al proveedor a activo con los datos nuevos y audita la reactivación."""
        inactivo = proveedor("Agro Norte S. R. L.", n=1, activo=False, email="viejo@mail.com")
        datos = datos_de_formulario(email="nuevo@agronorte.com", razon_social="Agro Norte S. A.")
        respuesta = self.client.post(self.nuevo, {**datos, "reactivar_id": inactivo.pk}, follow=True)
        self.assertRedirects(respuesta, self.url("proveedor_ficha", inactivo))
        inactivo.refresh_from_db()
        self.assertEqual((inactivo.estado_proveedor, inactivo.email_proveedor, inactivo.razon_social_proveedor), ("activo", "nuevo@agronorte.com", "Agro Norte S. A."))
        self.assertEqual(Proveedor.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="reactivacion_proveedor").count(), 1)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="alta_proveedor").exists())

    def test_regla_1_una_persona_fisica_se_registra_con_nombre_y_apellido(self):
        """CMP-ALT-PRV regla 1: elegir «Persona física» pide nombre y apellido."""
        respuesta = self.client.post(self.nuevo, datos_de_formulario(tipo="fisica", razon_social="", nombre="", apellido=""))
        self.assertContains(respuesta, "Ingresá el nombre.")
        self.assertContains(respuesta, "Ingresá el apellido.")
        self.client.post(self.nuevo, datos_de_formulario(tipo="fisica", razon_social="", nombre="Ana", apellido="Gómez"))
        self.assertEqual(str(Proveedor.objects.get()), "Ana Gómez")


class ModificacionDeProveedorVistaTests(ProveedoresVistasBase):
    """CMP-MOD-PRV: el formulario de modificación."""

    def setUp(self):
        super().setUp()
        self.limpieza = tipo_de_insumo("Limpieza")
        self.sur = proveedor("Semillas del Sur S. A.", n=1, telefono="376 400-1001", especialidades=[self.limpieza])
        self.editar = self.url("proveedor_editar", self.sur)

    def datos(self, **cambios):
        datos = {
            "cuit": con_guiones(cuit_valido(1)),
            "razon_social": "Semillas del Sur S. A.",
            "email": "ventas@semillasdelsur.com",
            "telefono": "376 400-1001",
            "especialidades": [self.limpieza.pk],
        }
        datos.update(cambios)
        return datos

    def test_el_formulario_arranca_con_los_datos_del_proveedor_y_sin_cambiar_el_tipo(self):
        """CMP-MOD-PRV: el formulario muestra los datos actuales (CUIT con guiones, categorías marcadas); el tipo es solo informativo."""
        respuesta = self.client.get(self.editar)
        self.assertContains(respuesta, 'value="Semillas del Sur S. A."')
        self.assertContains(respuesta, f'value="{con_guiones(cuit_valido(1))}"')
        self.assertContains(respuesta, f'value="{self.limpieza.pk}" checked')
        self.assertContains(respuesta, "El tipo no se cambia")
        self.assertNotContains(respuesta, 'name="tipo"')
        self.assertContains(respuesta, "Guardar cambios")

    def test_flujo_principal_guarda_los_cambios_y_vuelve_a_la_ficha(self):
        """CMP-MOD-PRV flujo principal: se guardan los datos, se avisa y se audita la modificación."""
        respuesta = self.client.post(self.editar, self.datos(email="info@semillasdelsur.com"), follow=True)
        self.assertRedirects(respuesta, self.url("proveedor_ficha", self.sur))
        self.assertContains(respuesta, "Guardamos los cambios.")
        self.sur.refresh_from_db()
        self.assertEqual(self.sur.email_proveedor, "info@semillasdelsur.com")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_proveedor").count(), 1)

    def test_regla_1_los_errores_se_muestran_por_campo(self):
        """CMP-MOD-PRV regla 1: las mismas validaciones que el alta, por campo."""
        respuesta = self.client.post(self.editar, self.datos(email="", cuit="30712345670"))
        self.assertContains(respuesta, "Ingresá el correo")
        self.assertContains(respuesta, "El CUIT no es válido")
        self.sur.refresh_from_db()
        self.assertEqual(self.sur.cuit_proveedor, cuit_valido(1))

    def test_regla_1_un_cuit_de_otro_proveedor_se_rechaza(self):
        """CMP-MOD-PRV regla 1 (H14)."""
        proveedor("Agro Norte S. R. L.", n=2)
        self.assertContains(self.client.post(self.editar, self.datos(cuit=cuit_valido(2))), "Ya está registrado como Agro Norte S. R. L.")

    def test_regla_2_el_cuit_no_se_puede_editar_si_tiene_pedidos_u_ordenes(self):
        """CMP-MOD-PRV regla 2: con pedidos u órdenes el CUIT se muestra de solo lectura y un envío manual no lo cambia (la consulta se simula)."""
        with mock.patch("compras.servicios.proveedores.tiene_pedidos_u_ordenes", return_value=True):
            self.assertContains(self.client.get(self.editar), "El CUIT no se puede cambiar")
            respuesta = self.client.post(self.editar, {k: v for k, v in self.datos(email="otro@mail.com").items() if k != "cuit"})
        self.assertEqual(respuesta.status_code, 302)
        self.sur.refresh_from_db()
        self.assertEqual((self.sur.cuit_proveedor, self.sur.email_proveedor), (cuit_valido(1), "otro@mail.com"))

    def test_pre_b_un_proveedor_inactivo_no_se_modifica_y_se_ofrece_reactivarlo(self):
        """CMP-MOD-PRV precondición b: uno dado de baja vuelve a la ficha con un aviso (ningún botón lleva a un error)."""
        inactivo = proveedor("Agro Norte S. R. L.", n=2, activo=False)
        respuesta = self.client.get(self.url("proveedor_editar", inactivo), follow=True)
        self.assertRedirects(respuesta, self.url("proveedor_ficha", inactivo))
        self.assertContains(respuesta, "solo se puede reactivar")


class ReactivacionDeProveedorVistaTests(ProveedoresVistasBase):
    """CMP-ALT-PRV postcondición c, desde la ficha: reactivar con un formulario con sus datos."""

    def setUp(self):
        super().setUp()
        self.norte = proveedor("Agro Norte S. R. L.", n=2, activo=False, email="viejo@agronorte.com")
        self.reactivar = self.url("proveedor_reactivar", self.norte)

    def test_el_formulario_muestra_el_cuit_fijo_y_pide_confirmar(self):
        """CMP-ALT-PRV postcondición c: el CUIT identifica al proveedor y no se cambia."""
        respuesta = self.client.get(self.reactivar)
        self.assertContains(respuesta, "Reactivar proveedor")
        self.assertContains(respuesta, "no se cambia")
        self.assertNotContains(respuesta, 'name="cuit"')

    def test_reactiva_con_los_datos_corregidos_y_vuelve_a_la_ficha(self):
        """CMP-ALT-PRV postcondición c: pasa a activo con los datos indicados."""
        respuesta = self.client.post(
            self.reactivar, {"razon_social": "Agro Norte S. R. L.", "email": "ventas@agronorte.com", "telefono": "", "especialidades": []}, follow=True
        )
        self.assertRedirects(respuesta, self.url("proveedor_ficha", self.norte))
        self.assertContains(respuesta, "está activo otra vez")
        self.norte.refresh_from_db()
        self.assertEqual((self.norte.estado_proveedor, self.norte.email_proveedor), ("activo", "ventas@agronorte.com"))

    def test_un_error_de_campo_se_muestra_y_no_reactiva(self):
        """CMP-ALT-PRV regla 1: los mismos controles que el alta."""
        respuesta = self.client.post(self.reactivar, {"razon_social": "Agro Norte S. R. L.", "email": "", "telefono": ""})
        self.assertContains(respuesta, "Ingresá el correo")
        self.norte.refresh_from_db()
        self.assertEqual(self.norte.estado_proveedor, "inactivo")

    def test_un_proveedor_activo_no_se_reactiva(self):
        """El servicio rechaza reactivar a un activo; la pantalla vuelve a la ficha con un aviso."""
        activo = proveedor("Semillas del Sur S. A.", n=1)
        respuesta = self.client.get(self.url("proveedor_reactivar", activo), follow=True)
        self.assertRedirects(respuesta, self.url("proveedor_ficha", activo))
        self.assertContains(respuesta, "no está dado de baja")


class BajaDeProveedorVistaTests(ProveedoresVistasBase):
    """CMP-BAJ-PRV: la ventana de confirmación, con HTMX y sin JavaScript."""

    def setUp(self):
        super().setUp()
        self.sur = proveedor("Semillas del Sur S. A.", n=1)
        self.baja = self.url("proveedor_baja", self.sur)

    def test_con_htmx_la_ventana_es_un_fragmento_y_abrirla_no_cambia_nada(self):
        """CMP-BAJ-PRV: la ventana pide confirmar; abrirla (GET) no da de baja."""
        respuesta = self.client.get(self.baja, **HX)
        self.assertContains(respuesta, "¿Dar de baja a Semillas del Sur S. A.?")
        self.assertNotContains(respuesta, "<html")
        self.sur.refresh_from_db()
        self.assertEqual(self.sur.estado_proveedor, "activo")

    def test_sin_javascript_la_ventana_es_la_ficha_con_la_ventana_abierta(self):
        """docs/patrones/abm.md, sección 7: respaldo sin JavaScript."""
        respuesta = self.client.get(self.baja)
        self.assertContains(respuesta, "<html")
        self.assertContains(respuesta, "¿Dar de baja a Semillas del Sur S. A.?")
        self.assertContains(respuesta, "Datos")

    def test_confirmar_da_de_baja_avisa_y_vuelve_a_la_lista(self):
        """CMP-BAJ-PRV flujo principal: queda inactivo, se audita y se avisa."""
        respuesta = self.client.post(self.baja, follow=True)
        self.assertRedirects(respuesta, self.lista)
        self.assertContains(respuesta, "Semillas del Sur S. A. quedó inactivo.")
        self.sur.refresh_from_db()
        self.assertEqual(self.sur.estado_proveedor, "inactivo")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_proveedor").count(), 1)

    def test_regla_2_con_impedimentos_la_ventana_dice_que_lo_impide_y_no_ofrece_confirmar(self):
        """CMP-BAJ-PRV regla 2: si algo lo impide, la ventana lo explica con cómo resolverlo y un POST no da de baja (los impedimentos los suman CMP-03 y CMP-05)."""
        impedimento = Impedimento("orden_no_terminada", "Tiene la orden OC-3 sin terminar.", "Recibí o cerrá con faltante la mercadería.")
        with mock.patch("compras.servicios.proveedores.impedimentos_de_baja", return_value=[impedimento]):
            ventana = self.client.get(self.baja, **HX)
            self.assertContains(ventana, "No se puede dar de baja a Semillas del Sur S. A.")
            self.assertContains(ventana, "Tiene la orden OC-3 sin terminar.")
            self.assertContains(ventana, "Recibí o cerrá con faltante la mercadería.")
            self.assertNotContains(ventana, "Dando de baja")
            self.client.post(self.baja)
        self.sur.refresh_from_db()
        self.assertEqual(self.sur.estado_proveedor, "activo")

    def test_un_proveedor_inactivo_no_tiene_ventana_de_baja(self):
        """CMP-BAJ-PRV precondición b: se vuelve a la ficha con un aviso."""
        inactivo = proveedor("Agro Norte S. R. L.", n=2, activo=False)
        respuesta = self.client.get(self.url("proveedor_baja", inactivo), follow=True)
        self.assertRedirects(respuesta, self.url("proveedor_ficha", inactivo))
        self.assertContains(respuesta, "ya está dado de baja")
