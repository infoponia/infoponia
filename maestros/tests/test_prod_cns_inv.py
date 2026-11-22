# Pruebas de PROD-CNS-INV · Consultar Invernadero (docs/casos_de_uso/maestros/invernaderos.md) y de lo que cita: D-28
# (alcance en un único queryset; 403 fuera del alcance y 404 si no existe) y SEG-14 (la consulta no se audita).
#
# Servicios que se prueban (maestros/servicios/invernaderos.py), tomados del módulo dentro de cada prueba:
#   consultar_invernaderos(actor) -> queryset de los invernaderos del alcance de ``actor`` (regla 1), activos primero y
#       por nombre. Precondición a: Gerente o Agrónomo activos; cualquier otro, PermissionDenied.
#   obtener_invernadero(actor, invernadero_id) -> Invernadero. Inexistente, Http404; fuera del alcance, PermissionDenied.
# El alcance vive en ``Invernadero.objects.en_alcance_de(actor)`` (D-28). Las marcas de la lista y de la ficha (reglas
# 2 y 4) las da ``Invernadero.roles_faltantes`` y ``tiene_sectores``.
#
# Fuera de alcance de MAE-01: capacidad, sectores, lotes, cámara y bitácora de la ficha (regla 3).
# MAE-02b suma la regla 5 (el Inicio del Gerente): ``invernaderos_con_personal_por_asignar(actor)`` y
# ``seccion_de_inicio(usuario)``, que ``MaestrosConfig.ready()`` registra en ``core.extensiones`` (D-43).

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.urls import reverse

from core import extensiones
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from maestros.models import Invernadero
from maestros.servicios import invernaderos
from maestros.tests.fabricas import (
    ConGeoref,
    crear_agronomo,
    crear_capataz_activo,
    crear_invernadero,
    crear_tecnico,
    crear_vendedor,
    asignar_transportista,
    crear_transportista,
)


class ProdCnsInvServicioTests(ConGeoref, TestCase):
    """Servicios ``consultar_invernaderos`` y ``obtener_invernadero`` (PROD-CNS-INV, reglas 1, 2, 4 y 7)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.otro_agronomo = crear_agronomo("otro.agronomo@infoponia.com")

    def nombres(self, actor):
        """Nombres de los invernaderos que ve ``actor``, en el orden en que los devuelve el servicio."""
        return [i.nombre_invernadero for i in invernaderos.consultar_invernaderos(actor)]

    # ---- Precondición a ----

    def test_pre_a_otros_roles_no_consultan(self):
        """PROD-CNS-INV, precondición a y regla 1: el Capataz (y cualquier rol que no sea Gerente o Agrónomo) no
        consulta invernaderos."""
        crear_invernadero()
        for actor in (crear_capataz(), crear_vendedor(), crear_tecnico(), crear_administrador()):
            with self.subTest(actor=actor.email), self.assertRaises(PermissionDenied):
                invernaderos.consultar_invernaderos(actor)

    def test_pre_a_cuentas_inactivas_no_consultan(self):
        """PROD-CNS-INV, precondición a: «cuenta activa de Gerente o de Agrónomo»."""
        agronomo = crear_agronomo("inactivo@infoponia.com", activo=False)
        for actor in (agronomo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                invernaderos.consultar_invernaderos(actor)

    # ---- Regla 1: alcance ----

    def test_regla_1_el_gerente_ve_todos_activos_e_inactivos(self):
        """PROD-CNS-INV, regla 1: el Gerente consulta todos los invernaderos, activos e inactivos, tengan o no
        personal."""
        crear_invernadero("A", agronomo=self.agronomo)
        crear_invernadero("B", activo=False)
        crear_invernadero("C")
        self.assertCountEqual(self.nombres(self.gerente), ["A", "B", "C"])

    def test_regla_1_el_agronomo_ve_solo_los_activos_a_su_cargo(self):
        """PROD-CNS-INV, regla 1: el Agrónomo, solo los activos a su cargo."""
        crear_invernadero("Propio", agronomo=self.agronomo)
        crear_invernadero("Ajeno", agronomo=self.otro_agronomo)
        crear_invernadero("Sin agrónomo")
        crear_invernadero("Propio inactivo", activo=False, agronomo=self.agronomo)
        self.assertEqual(self.nombres(self.agronomo), ["Propio"])

    def test_d28_el_alcance_vive_en_el_queryset(self):
        """D-28: un único queryset de alcance (``en_alcance_de``), con la misma regla que el servicio."""
        crear_invernadero("Propio", agronomo=self.agronomo)
        crear_invernadero("Ajeno", activo=False)
        self.assertEqual(Invernadero.objects.en_alcance_de(self.gerente).count(), 2)
        self.assertEqual(list(Invernadero.objects.en_alcance_de(self.agronomo)), list(Invernadero.objects.filter(nombre_invernadero="Propio")))
        self.assertFalse(Invernadero.objects.en_alcance_de(crear_capataz()).exists())
        self.assertFalse(Invernadero.objects.en_alcance_de(None).exists())

    def test_regla_2_lista_activos_primero_y_por_nombre(self):
        """PROD-CNS-INV, regla 2 (la lista): los activos primero, cada grupo por nombre."""
        crear_invernadero("Zeta")
        crear_invernadero("Beta", activo=False)
        crear_invernadero("Alfa")
        self.assertEqual(self.nombres(self.gerente), ["Alfa", "Zeta", "Beta"])

    # ---- obtener_invernadero (ficha) ----

    def test_regla_1_la_ficha_dentro_del_alcance_se_abre(self):
        """PROD-CNS-INV, regla 1: el Gerente abre cualquier ficha; el Agrónomo, la de un invernadero activo a su cargo."""
        invernadero = crear_invernadero("Propio", agronomo=self.agronomo)
        self.assertEqual(invernaderos.obtener_invernadero(self.gerente, invernadero.pk), invernadero)
        self.assertEqual(invernaderos.obtener_invernadero(self.agronomo, invernadero.pk), invernadero)

    def test_d28_ficha_fuera_del_alcance_da_403(self):
        """D-28: un invernadero que existe pero está fuera del alcance (ajeno o inactivo) da PermissionDenied."""
        ajeno = crear_invernadero("Ajeno", agronomo=self.otro_agronomo)
        inactivo = crear_invernadero("Inactivo", activo=False, agronomo=self.agronomo)
        for invernadero in (ajeno, inactivo):
            with self.subTest(invernadero=invernadero.nombre_invernadero), self.assertRaises(PermissionDenied):
                invernaderos.obtener_invernadero(self.agronomo, invernadero.pk)

    def test_d28_ficha_inexistente_da_404(self):
        """D-28: un id que no existe da Http404."""
        with self.assertRaises(Http404):
            invernaderos.obtener_invernadero(self.gerente, 0)

    def test_regla_1_la_ficha_de_otro_rol_da_403(self):
        """PROD-CNS-INV, regla 1: el Capataz no consulta invernaderos, tampoco su ficha."""
        invernadero = crear_invernadero("A", capataz=crear_capataz_activo())
        with self.assertRaises(PermissionDenied):
            invernaderos.obtener_invernadero(crear_capataz(), invernadero.pk)

    # ---- Reglas 2 y 4: marcas ----

    def test_regla_2_marca_el_personal_por_asignar(self):
        """PROD-CNS-INV, reglas 2 y 4: sin agrónomo, capataz y vendedor, los tres figuran como «sin asignar»
        (``nunca_asignado``); el Técnico no figura porque no hay IoT."""
        invernadero = crear_invernadero()
        self.assertEqual(
            invernadero.roles_faltantes(),
            [("agronomo", "Agrónomo", True), ("capataz", "Capataz", True), ("vendedor", "Vendedor", True)],
        )

    def test_regla_2_marca_el_personal_inactivo(self):
        """PROD-CNS-INV, regla 2: una persona asignada pero inactiva figura como faltante, no como «sin asignar»."""
        inactiva = crear_vendedor(activo=False)
        invernadero = crear_invernadero(agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=inactiva)
        self.assertEqual(invernadero.roles_faltantes(), [("vendedor", "Vendedor", False)])

    def test_regla_2_con_todo_el_personal_activo_no_falta_nadie(self):
        """PROD-CNS-INV, regla 2: con agrónomo, capataz y vendedor activos no hay nada por asignar."""
        invernadero = crear_invernadero(
            agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=crear_vendedor()
        )
        self.assertEqual(invernadero.roles_faltantes(), [])

    def test_regla_2_marca_los_invernaderos_sin_sectores(self):
        """PROD-CNS-INV, regla 2 y regla 7 de PROD-ALT-INV: «sin sectores: todavía no se puede sembrar»."""
        self.assertFalse(crear_invernadero().tiene_sectores())

    # ---- Regla 7: no se audita ----

    def test_regla_7_la_consulta_no_audita(self):
        """PROD-CNS-INV, regla 7 y SEG-14: ni la lista ni la ficha dejan registro de auditoría."""
        invernadero = crear_invernadero("A", agronomo=self.agronomo)
        list(invernaderos.consultar_invernaderos(self.gerente))
        invernaderos.obtener_invernadero(self.agronomo, invernadero.pk)
        self.assertFalse(RegistroAuditoria.objects.exists())

    # ---- Regla 5 (MAE-02b): el Inicio del Gerente lista el personal por asignar ----

    def personal_por_asignar(self, actor=None):
        """``[(nombre, [atributos de los roles que faltan])]`` de ``invernaderos_con_personal_por_asignar``."""
        return [
            (invernadero.nombre_invernadero, [atributo for atributo, _, _ in faltantes])
            for invernadero, faltantes in invernaderos.invernaderos_con_personal_por_asignar(actor or self.gerente)
        ]

    def test_regla_5_lista_los_activos_con_personal_por_asignar_por_nombre(self):
        """PROD-CNS-INV regla 5: el Inicio del Gerente lista los invernaderos con personal por asignar, por nombre (sin
        distinguir mayúsculas), con los roles que faltan."""
        crear_invernadero("Zeta")
        crear_invernadero("alfa", capataz=crear_capataz_activo())

        self.assertEqual(
            self.personal_por_asignar(),
            [("alfa", ["agronomo", "vendedor"]), ("Zeta", ["agronomo", "capataz", "vendedor"])],
        )

    def test_regla_5_no_lista_los_inactivos_ni_los_completos(self):
        """PROD-CNS-INV regla 5 y post e de PROD-BAJ-INV: ni los inactivos ni los que tienen todo su personal activo. Control:
        un activo con personal por asignar sí figura."""
        crear_invernadero("Inactivo", activo=False)
        crear_invernadero(
            "Completo", agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=crear_vendedor()
        )
        crear_invernadero("Con faltante", agronomo=self.otro_agronomo)

        self.assertEqual(self.personal_por_asignar(), [("Con faltante", ["capataz", "vendedor"])])

    def test_regla_5_muestra_al_asignado_inactivo(self):
        """PROD-CNS-INV regla 5: una persona asignada pero dada de baja cuenta como personal por asignar; el rol viene con
        ``nunca_asignado`` en falso (el Inicio la nombra)."""
        capataz = crear_capataz_activo(activo=False)
        crear_invernadero(
            "Sur", agronomo=self.agronomo, capataz=capataz, vendedor=crear_vendedor()
        )

        (invernadero, faltantes), = invernaderos.invernaderos_con_personal_por_asignar(self.gerente)

        self.assertEqual(invernadero.nombre_invernadero, "Sur")
        self.assertEqual(faltantes, [("capataz", "Capataz", False)])

    def test_regla_5_tecnico_sin_iot_no_cuenta(self):
        """PROD-CNS-INV regla 5 y regla 5 de PROD-ALT-INV: sin sistema IoT, no falta el Técnico. Control: el invernadero al
        que le falta el Vendedor sí figura."""
        crear_invernadero(
            "Sin tecnico", agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=crear_vendedor()
        )
        crear_invernadero(
            "Sin vendedor",
            agronomo=self.otro_agronomo,
            capataz=crear_capataz_activo("otro.capataz@infoponia.com"),
        )

        self.assertEqual(self.personal_por_asignar(), [("Sin vendedor", ["vendedor"])])

    def test_regla_5_solo_el_gerente_activo_consulta(self):
        """PROD-CNS-INV regla 5 y SEG-13: el Agrónomo, el Capataz, un Gerente dado de baja y ``None`` no consultan lo que
        falta asignar. Control: el Gerente activo sí."""
        crear_invernadero("Sur")
        inactivo = crear_gerente(email="anterior@infoponia.com", activo=False)

        for actor in (self.agronomo, crear_capataz(), inactivo, None):
            with self.subTest(actor=getattr(actor, "email", None)):
                with self.assertRaises(PermissionDenied):
                    invernaderos.invernaderos_con_personal_por_asignar(actor)
        self.assertEqual(len(self.personal_por_asignar()), 1)

    def test_regla_7_la_consulta_del_inicio_no_audita(self):
        """PROD-CNS-INV regla 7 y SEG-14: consultar lo que falta asignar no audita. Control: devuelve el invernadero."""
        crear_invernadero("Sur")

        resultado = invernaderos.invernaderos_con_personal_por_asignar(self.gerente)

        self.assertEqual(len(resultado), 1)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_5_la_seccion_de_inicio_es_solo_del_gerente(self):
        """PROD-CNS-INV regla 5: ``seccion_de_inicio`` devuelve la sección «Personal por asignar» para el Gerente activo y
        ``None`` para cualquier otro."""
        seccion = invernaderos.seccion_de_inicio(self.gerente)

        self.assertEqual(seccion.plantilla, "maestros/invernaderos/_inicio_personal.html")
        for usuario in (self.agronomo, crear_capataz(), crear_gerente(email="anterior@infoponia.com", activo=False), None):
            with self.subTest(usuario=getattr(usuario, "email", None)):
                self.assertIsNone(invernaderos.seccion_de_inicio(usuario))

    def test_d43_maestros_registra_su_seccion_de_inicio(self):
        """D-43 y A4 de D-37: ``MaestrosConfig.ready()`` registra la sección del Inicio en ``core.extensiones``."""
        self.assertIn(invernaderos.seccion_de_inicio, extensiones._SECCIONES_DE_INICIO)


class ProdCnsInvVistaTests(ConGeoref, TestCase):
    """Lista y ficha de invernaderos (integración, PROD-CNS-INV): alcance por rol, marcas y avisos, y el menú."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.otro_agronomo = crear_agronomo("otro.agronomo@infoponia.com")
        self.url = reverse("maestros:invernaderos")

    def test_flujo_principal_el_gerente_ve_la_lista_completa(self):
        """PROD-CNS-INV, regla 1: el Gerente ve todos, activos e inactivos, con la dirección y su acceso a «Nuevo»."""
        crear_invernadero("Invernadero A", agronomo=self.agronomo)
        crear_invernadero("Invernadero B", activo=False)
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Invernadero A")
        self.assertContains(respuesta, "Invernadero B")
        self.assertContains(respuesta, "Calle 122 3310")
        self.assertContains(respuesta, "Garupá")
        self.assertContains(respuesta, reverse("maestros:invernadero_nuevo"))

    def test_regla_1_el_agronomo_ve_solo_sus_activos_y_no_puede_dar_de_alta(self):
        """PROD-CNS-INV, regla 1 y D-30: el Agrónomo ve los activos a su cargo y no se le ofrece «Nuevo invernadero»."""
        crear_invernadero("Propio", agronomo=self.agronomo)
        crear_invernadero("Ajeno", agronomo=self.otro_agronomo)
        crear_invernadero("Propio inactivo", activo=False, agronomo=self.agronomo)
        self.client.force_login(self.agronomo)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Propio")
        self.assertNotContains(respuesta, "Ajeno")
        self.assertNotContains(respuesta, "Propio inactivo")
        self.assertNotContains(respuesta, reverse("maestros:invernadero_nuevo"))

    def test_regla_1_el_capataz_no_consulta_invernaderos(self):
        """PROD-CNS-INV, regla 1: el Capataz recibe 403 en la lista y en la ficha."""
        invernadero = crear_invernadero("A")
        self.client.force_login(crear_capataz())
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(reverse("maestros:invernadero", args=[invernadero.pk])).status_code, 403)

    def test_regla_2_la_lista_marca_sin_sectores_y_personal_por_asignar(self):
        """PROD-CNS-INV, regla 2: marca los invernaderos sin sectores y los que tienen personal por asignar."""
        crear_invernadero("A")
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Sin sectores: todavía no se puede sembrar")
        self.assertContains(respuesta, "Personal por asignar: Agrónomo, Capataz, Vendedor")
        self.assertContains(respuesta, "Sin asignar")
        self.assertContains(respuesta, "No hace falta sin IoT")

    def test_regla_2_la_lista_marca_al_personal_inactivo(self):
        """PROD-CNS-INV, regla 2: el personal asignado pero inactivo se muestra con la marca «Inactivo»."""
        crear_invernadero(
            "A", agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=crear_vendedor(activo=False)
        )
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Inactivo")
        self.assertContains(respuesta, "Personal por asignar: Vendedor")

    def test_regla_2_sin_faltantes_no_hay_aviso_de_personal(self):
        """PROD-CNS-INV, regla 2: con todo el personal activo no aparece «Personal por asignar»."""
        crear_invernadero(
            "A", agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=crear_vendedor()
        )
        self.client.force_login(self.gerente)
        self.assertNotContains(self.client.get(self.url), "Personal por asignar")

    def test_regla_3_la_ficha_muestra_ubicacion_y_equipo(self):
        """PROD-CNS-INV, regla 3: la ficha muestra la dirección, la localidad, el departamento, la zona, el sistema
        IoT y el equipo."""
        invernadero = crear_invernadero("A", tipo="rural", agronomo=self.agronomo)
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("maestros:invernadero", args=[invernadero.pk]))
        for texto in ("Ruta Nacional 14, km 871", "Garupá, Misiones", "Capital", "Rural", "Sin registrar", "Agrónomo"):
            with self.subTest(texto=texto):
                self.assertContains(respuesta, texto)

    def test_regla_4_la_ficha_avisa_el_personal_faltante(self):
        """PROD-CNS-INV, regla 4: si falta personal, la ficha lo avisa; al Gerente le dice que lo asigna al
        modificar, y al Agrónomo, que lo asigna el Gerente."""
        invernadero = crear_invernadero("A", agronomo=self.agronomo)
        url = reverse("maestros:invernadero", args=[invernadero.pk])
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(url), "Faltan asignar: Capataz, Vendedor")
        self.assertContains(self.client.get(url), "Lo asigna el Gerente al modificar")
        self.client.force_login(self.agronomo)
        self.assertContains(self.client.get(url), "Los asigna el Gerente.")

    def test_regla_4_la_ficha_avisa_si_el_asignado_esta_inactivo(self):
        """PROD-CNS-INV, regla 4: un rol con la persona inactiva se avisa distinto de uno sin asignar."""
        invernadero = crear_invernadero(
            "A", agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=crear_vendedor(activo=False)
        )
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("maestros:invernadero", args=[invernadero.pk]))
        self.assertContains(respuesta, "Vendedor (el asignado está inactivo)")

    def test_regla_2_la_ficha_marca_sin_sectores(self):
        """PROD-CNS-INV, regla 2: la ficha de un invernadero sin sectores lo dice."""
        invernadero = crear_invernadero("A")
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("maestros:invernadero", args=[invernadero.pk]))
        self.assertContains(respuesta, "todavía no se puede sembrar")

    def test_regla_1_la_ficha_fuera_del_alcance_da_403_y_la_inexistente_404(self):
        """PROD-CNS-INV, regla 1 y D-28: la ficha de un invernadero ajeno da 403; la de uno que no existe, 404."""
        ajeno = crear_invernadero("Ajeno", agronomo=self.otro_agronomo)
        self.client.force_login(self.agronomo)
        self.assertEqual(self.client.get(reverse("maestros:invernadero", args=[ajeno.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("maestros:invernadero", args=[0])).status_code, 404)

    def test_regla_6_la_ficha_ofrece_al_gerente_modificar_y_dar_de_baja_o_reactivar(self):
        """PROD-CNS-INV, regla 6 (y D-30): «el Gerente solo modifica, da de baja o reactiva el invernadero». Sobre uno
        activo ve «Modificar» y «Dar de baja»; sobre uno inactivo, solo «Reactivar»."""
        activo = crear_invernadero("A", agronomo=self.agronomo)
        inactivo = crear_invernadero("B", activo=False)
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("maestros:invernadero", args=[activo.pk]))
        self.assertContains(respuesta, reverse("maestros:invernadero_modificar", args=[activo.pk]))
        self.assertContains(respuesta, reverse("maestros:invernadero_baja", args=[activo.pk]))
        self.assertNotContains(respuesta, reverse("maestros:invernadero_reactivar", args=[activo.pk]))
        respuesta = self.client.get(reverse("maestros:invernadero", args=[inactivo.pk]))
        self.assertContains(respuesta, reverse("maestros:invernadero_reactivar", args=[inactivo.pk]))
        self.assertNotContains(respuesta, reverse("maestros:invernadero_modificar", args=[inactivo.pk]))
        self.assertNotContains(respuesta, reverse("maestros:invernadero_baja", args=[inactivo.pk]))

    def test_regla_6_el_agronomo_no_ve_acciones_del_invernadero(self):
        """PROD-CNS-INV, regla 6 y D-30: el Agrónomo a cargo no modifica, ni da de baja, ni reactiva el invernadero:
        la ficha no le ofrece ningún botón que lo lleve a un 403."""
        invernadero = crear_invernadero("A", agronomo=self.agronomo)
        self.client.force_login(self.agronomo)
        respuesta = self.client.get(reverse("maestros:invernadero", args=[invernadero.pk]))
        for nombre in ("invernadero_modificar", "invernadero_baja", "invernadero_reactivar"):
            self.assertNotContains(respuesta, reverse(f"maestros:{nombre}", args=[invernadero.pk]))

    def test_regla_7_las_pantallas_solo_leen_y_no_auditan(self):
        """PROD-CNS-INV, regla 7 y SEG-14: la lista y la ficha solo aceptan GET (un POST da 405) y no auditan."""
        invernadero = crear_invernadero("A", agronomo=self.agronomo)
        self.client.force_login(self.gerente)
        ficha = reverse("maestros:invernadero", args=[invernadero.pk])
        self.client.get(self.url)
        self.client.get(ficha)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(self.client.post(ficha).status_code, 405)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_d25_el_menu_ofrece_produccion_al_gerente_y_al_agronomo(self):
        """D-25: el menú lateral muestra «Producción» al Gerente y al Agrónomo, y no al Vendedor."""
        for cuenta, debe in ((self.gerente, True), (self.agronomo, True), (crear_vendedor(), False)):
            self.client.force_login(cuenta)
            with self.subTest(cuenta=cuenta.email):
                respuesta = self.client.get(reverse("core:inicio"))
                self.assertEqual("Producción" in respuesta.content.decode(), debe)
                if debe:
                    self.assertContains(respuesta, f'href="{self.url}"')

    # ---- Regla 5 (MAE-02b): «Personal por asignar» en el Inicio del Gerente ----

    def test_regla_5_el_inicio_del_gerente_muestra_personal_por_asignar_y_asignar(self):
        """PROD-CNS-INV regla 5: el Inicio del Gerente lista los invernaderos con personal por asignar (con lo que falta o
        la persona inactiva) y un acceso a modificar cada uno."""
        sur = crear_invernadero("Sur")
        norte = crear_invernadero(
            "Norte",
            agronomo=self.agronomo,
            capataz=crear_capataz_activo(activo=False),
            vendedor=crear_vendedor(),
        )
        self.client.force_login(self.gerente)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(respuesta, "Personal por asignar")
        self.assertContains(respuesta, "2 pendientes")
        self.assertContains(respuesta, "Falta Agrónomo · Falta Capataz · Falta Vendedor")
        self.assertContains(respuesta, "Capataz inactivo (Nombre Apellido)")
        self.assertContains(respuesta, f'href="{reverse("maestros:invernadero_modificar", args=[sur.pk])}"')
        self.assertContains(respuesta, f'href="{reverse("maestros:invernadero_modificar", args=[norte.pk])}"')
        self.assertContains(respuesta, "Asignar")

    def test_regla_5_sin_faltantes_dice_que_esta_todo_asignado(self):
        """PROD-CNS-INV regla 5: sin personal por asignar, el Inicio lo dice. Sin ningún invernadero activo no muestra ni
        la lista ni ese aviso (no hay nada que decir)."""
        self.client.force_login(self.gerente)
        sin_invernaderos = self.client.get(reverse("core:inicio"))
        crear_invernadero(
            "Completo", agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=crear_vendedor()
        )

        con_uno_completo = self.client.get(reverse("core:inicio"))

        self.assertNotContains(sin_invernaderos, "Todos los invernaderos activos tienen su personal asignado.")
        self.assertNotContains(sin_invernaderos, "Personal por asignar")
        self.assertContains(con_uno_completo, "Todos los invernaderos activos tienen su personal asignado.")
        self.assertNotContains(con_uno_completo, "Personal por asignar")

    # ---- MAE-05 (D-55, punto 6): el transportista sin invernadero en «Personal por asignar» ----

    def test_regla_5_el_transportista_activo_sin_invernadero_aparece_como_aviso_con_asignar(self):
        """PROD-CNS-INV regla 5 *(MAE-05)*: el Inicio del Gerente lista a los transportistas activos sin invernadero, como
        aviso (no es una alerta), con un acceso para asignarlos que lleva a la lista de invernaderos."""
        crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera")
        self.client.force_login(self.gerente)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(respuesta, "Personal por asignar")
        self.assertContains(respuesta, "Marcos Vera")
        self.assertContains(respuesta, "Transportista sin invernadero: no recibe entregas.")
        self.assertContains(respuesta, f'href="{reverse("maestros:invernaderos")}"')

    def test_regla_5_el_transportista_inactivo_no_aparece(self):
        """PROD-CNS-INV regla 5 *(MAE-05)*: solo los activos."""
        crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera", activo=False)
        self.client.force_login(self.gerente)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertNotContains(respuesta, "Marcos Vera")
        self.assertNotContains(respuesta, "Transportista sin invernadero")

    def test_regla_5_el_transportista_con_invernadero_no_aparece(self):
        """PROD-CNS-INV regla 5 *(MAE-05)*: quien ya trabaja para un invernadero no es un pendiente."""
        asignar_transportista(
            crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera"),
            crear_invernadero("Norte", agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=crear_vendedor()),
        )
        self.client.force_login(self.gerente)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertNotContains(respuesta, "Marcos Vera")
        self.assertNotContains(respuesta, "Transportista sin invernadero")

    def test_regla_5_el_contador_suma_invernaderos_y_transportistas(self):
        """PROD-CNS-INV regla 5 *(MAE-05)*: la cabecera dice «N pendientes»: invernaderos más transportistas."""
        crear_invernadero("Sur")
        crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera")
        crear_transportista("carla@infoponia.com", nombre="Carla", apellido="Sosa")
        self.client.force_login(self.gerente)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(respuesta, "3 pendientes")

    def test_regla_5_los_transportistas_van_por_apellido_y_nombre(self):
        """PROD-CNS-INV regla 5 *(MAE-05)*: orden por apellido y nombre, sin distinguir mayúsculas."""
        crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="vera")
        crear_transportista("carla@infoponia.com", nombre="Carla", apellido="Sosa")
        crear_transportista("ana@infoponia.com", nombre="Ana", apellido="Álvarez")
        seccion = invernaderos.seccion_de_inicio(self.gerente)

        self.assertEqual(
            [t.get_full_name() for t in seccion.contexto["transportistas_sin_invernadero"]],
            ["Ana Álvarez", "Carla Sosa", "Marcos vera"],
        )

    def test_regla_5_un_invernadero_sin_transportistas_no_aparece(self):
        """PROD-CNS-INV regla 5 y decisión D de D-55: un invernadero con todo el personal pero sin transportistas no genera
        aviso (puede vender con retiro): el Inicio dice que todo está asignado."""
        crear_invernadero(
            "Completo", agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=crear_vendedor()
        )
        self.client.force_login(self.gerente)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(respuesta, "Todos los invernaderos activos tienen su personal asignado.")
        self.assertNotContains(respuesta, "pendiente")

    def test_regla_5_con_un_transportista_sin_invernadero_no_dice_que_esta_todo_asignado(self):
        """PROD-CNS-INV regla 5 *(MAE-05)*: el mensaje de todo asignado solo va si no hay ni invernaderos ni transportistas
        por asignar."""
        crear_invernadero(
            "Completo", agronomo=self.agronomo, capataz=crear_capataz_activo(), vendedor=crear_vendedor()
        )
        crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera")
        self.client.force_login(self.gerente)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertNotContains(respuesta, "Todos los invernaderos activos tienen su personal asignado.")
        self.assertContains(respuesta, "1 pendiente")

    def test_regla_5_sin_invernaderos_activos_el_transportista_sigue_apareciendo(self):
        """PROD-CNS-INV regla 5 *(MAE-05)*: el aviso del transportista no depende de que haya invernaderos activos."""
        crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera")
        self.client.force_login(self.gerente)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(respuesta, "Marcos Vera")

    def test_regla_5_el_inicio_del_agronomo_no_muestra_a_los_transportistas(self):
        """PROD-CNS-INV regla 5: la sección es solo del Gerente, también para los transportistas."""
        crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera")
        self.client.force_login(self.agronomo)

        self.assertNotContains(self.client.get(reverse("core:inicio")), "Marcos Vera")

    def test_regla_5_el_inicio_del_agronomo_no_muestra_la_seccion(self):
        """PROD-CNS-INV regla 5: la sección es solo del Gerente. Control: con el mismo invernadero, el Gerente la ve."""
        crear_invernadero("Sur", agronomo=self.agronomo)
        self.client.force_login(self.agronomo)
        del_agronomo = self.client.get(reverse("core:inicio"))
        self.client.force_login(self.gerente)
        del_gerente = self.client.get(reverse("core:inicio"))

        self.assertNotContains(del_agronomo, "Personal por asignar")
        self.assertContains(del_gerente, "Personal por asignar")

    def test_regla_7_el_inicio_no_audita(self):
        """PROD-CNS-INV regla 7 y SEG-14: abrir el Inicio no audita. Control: la sección se muestra."""
        crear_invernadero("Sur")
        self.client.force_login(self.gerente)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(respuesta, "Personal por asignar")
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_d30_el_inicio_no_ofrece_asignar_un_invernadero_inactivo(self):
        """D-30: ningún enlace lleva a un 403 o a una redirección. Modificar un invernadero inactivo no se puede (solo
        reactivar), así que el Inicio no lo lista. Control: el activo sí tiene su «Asignar»."""
        activo = crear_invernadero("Activo")
        inactivo = crear_invernadero("Inactivo", activo=False)
        self.client.force_login(self.gerente)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(respuesta, reverse("maestros:invernadero_modificar", args=[activo.pk]))
        self.assertNotContains(respuesta, reverse("maestros:invernadero_modificar", args=[inactivo.pk]))

    def test_d25_sin_javascript_el_inicio_ofrece_asignar_con_un_enlace(self):
        """D-25 y sin JavaScript: «Asignar» es un enlace común (``href``), sin atributos de HTMX: funciona igual con el
        JavaScript desactivado."""
        sur = crear_invernadero("Sur")
        self.client.force_login(self.gerente)
        destino = reverse("maestros:invernadero_modificar", args=[sur.pk])

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(respuesta, f'href="{destino}"')
        self.assertNotContains(respuesta, f'hx-get="{destino}"')
