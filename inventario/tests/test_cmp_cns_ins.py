# Pruebas de CMP-CNS-INS · Consultar Insumo (docs/casos_de_uso/inventario/insumos.md). Cita D-28, D-30 y SEG-14.
#
# Servicios que se prueban (inventario/servicios/insumos.py), tomados del módulo dentro de cada prueba:
#   consultar_insumos(actor) -> list[Insumo], cada uno con ``habilitado_en`` (invernaderos que lo usan, por nombre) y ``es_semilla``
#     - Precondición a y regla 4: Agrónomo activo; el Gerente (y el resto) no consulta (PermissionDenied).
#     - Regla 1: todo el catálogo, activos e inactivos, incluidas las semillas; los activos primero y por nombre (sin distinguir mayúsculas).
#     - Regla 2: nombre y descripción, categoría (con la marca «del sistema»), unidad, si controla vencimiento, los invernaderos donde está
#       habilitado y estado; las semillas indican que vienen del alta de su variedad (``es_semilla``).
#     - Regla 5 y postcondición a: no cambia nada y no audita.
#   invernaderos_que_usan(insumo_id) -> list[Invernadero]: «un invernadero usa el insumo si está activo y lo tiene habilitado» (por nombre).
#   puede_gestionar(actor, insumo) -> bool: regla 1 de CMP-MOD-INS. quienes_lo_usan(insumo_id) -> list[str] («<invernadero> (<Agrónomo>)»
#   o «<invernadero> (sin Agrónomo)»): el texto de las acciones deshabilitadas (regla 3).
#   acciones_permitidas(actor, insumo) -> frozenset de ``{"modificar", "baja", "reactivar"}`` según el estado (regla 3; «habilitar» es de
#   INV-02); una semilla no tiene estas acciones. La pantalla las muestra deshabilitadas si ``puede_gestionar`` es falso.

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    categoria_del_sistema,
    existencia,
    insumo,
    perezoso,
    tipo_de_insumo,
)
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

insumos = perezoso("inventario.servicios.insumos")


class CmpCnsInsServicioTests(ConDatosDeInventario, TestCase):
    """Precondición, reglas y postcondición de CMP-CNS-INS."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Gómez")
        self.tipo = tipo_de_insumo("Limpieza")

    def consultar(self, actor=None):
        return list(insumos.consultar_insumos(actor or self.agronomo))

    # ---- precondición a y regla 4 ----

    def test_pre_a_el_gerente_no_consulta_el_catalogo(self):
        """CMP-CNS-INS regla 4: «El Gerente no consulta el catálogo»."""
        with self.assertRaises(PermissionDenied):
            insumos.consultar_insumos(crear_gerente())

    def test_pre_a_capataz_administrador_y_un_agronomo_inactivo_no_consultan(self):
        """CMP-CNS-INS precondición a: Agrónomo con la cuenta activa."""
        inactivo = crear_agronomo(email="inactivo@infoponia.com", activo=False)
        for cuenta in (crear_capataz(), crear_administrador(), inactivo):
            with self.subTest(cuenta=type(cuenta).__name__):
                with self.assertRaises(PermissionDenied):
                    insumos.consultar_insumos(cuenta)

    # ---- reglas 1 y 2 ----

    def test_regla_1_consulta_todo_el_catalogo_activos_inactivos_y_semillas(self):
        """CMP-CNS-INS regla 1: «con los insumos activos e inactivos»; las semillas también se ven."""
        insumo("Detergente", tipo=self.tipo)
        insumo("Viejo", tipo=self.tipo, activo=False)
        insumo("Semilla Lechuga Crespa", tipo=categoria_del_sistema("semillas"), unidad="unidad")
        self.assertEqual(
            sorted(i.nombre_insumo for i in self.consultar()), ["Detergente", "Semilla Lechuga Crespa", "Viejo"]
        )

    def test_regla_1_sin_insumos_la_lista_viene_vacia(self):
        """CMP-CNS-INS regla 1: catálogo vacío."""
        self.assertEqual(self.consultar(), [])

    def test_regla_1_los_activos_van_primero_y_cada_grupo_por_nombre_sin_distinguir_mayusculas(self):
        """CMP-CNS-INS regla 1: orden estable para la pantalla."""
        insumo("zeta", tipo=self.tipo)
        insumo("Alfa", tipo=self.tipo)
        insumo("beta", tipo=self.tipo, activo=False)
        insumo("Anfora", tipo=self.tipo, activo=False)
        self.assertEqual([i.nombre_insumo for i in self.consultar()], ["Alfa", "zeta", "Anfora", "beta"])

    def test_regla_2_cada_insumo_trae_sus_datos_la_categoria_y_la_marca_del_sistema(self):
        """CMP-CNS-INS regla 2: nombre, descripción, categoría (con la marca «del sistema»), unidad, vencimiento y estado."""
        insumo("Detergente", tipo=self.tipo, unidad="l", controla_vencimiento=True, descripcion="5 L")
        insumo("Sobres", tipo=categoria_del_sistema("envases"), unidad="unidad")
        por_nombre = {i.nombre_insumo: i for i in self.consultar()}
        detergente, sobres = por_nombre["Detergente"], por_nombre["Sobres"]
        self.assertEqual(
            (detergente.descripcion_insumo, detergente.tipo_insumo.nombre_tipo_insumo, detergente.tipo_insumo.es_del_sistema),
            ("5 L", "Limpieza", False),
        )
        self.assertEqual((detergente.unidad_medida_insumo, detergente.controla_vencimiento, detergente.estado_insumo), ("l", True, "activo"))
        self.assertEqual((sobres.tipo_insumo.nombre_tipo_insumo, sobres.tipo_insumo.es_del_sistema), ("Envases", True))

    def test_regla_2_habilitado_en_lista_los_invernaderos_que_lo_usan_o_ninguno(self):
        """CMP-CNS-INS regla 2 y verificación a mano 5: los invernaderos donde está habilitado, o «ninguno» (lista vacía)."""
        con_uso = insumo("Detergente", tipo=self.tipo)
        insumo("Lavandina", tipo=self.tipo)
        existencia(con_uso, crear_invernadero("Invernadero Sur"))
        existencia(con_uso, crear_invernadero("Invernadero Norte"))
        existencia(con_uso, crear_invernadero("Invernadero Este"), activo=False)  # habilitación inactiva: no cuenta
        existencia(con_uso, crear_invernadero("Invernadero Cerrado", activo=False))  # invernadero inactivo: no cuenta
        por_nombre = {i.nombre_insumo: i for i in self.consultar()}
        self.assertEqual([g.nombre_invernadero for g in por_nombre["Detergente"].habilitado_en], ["Invernadero Norte", "Invernadero Sur"])
        self.assertEqual(por_nombre["Lavandina"].habilitado_en, [])

    def test_regla_2_las_semillas_indican_que_vienen_del_alta_de_su_variedad(self):
        """CMP-CNS-INS regla 2: ``es_semilla`` (categoría ``semillas`` por código) para el texto «Viene del alta de la variedad»."""
        insumo("Semilla Lechuga Crespa", tipo=categoria_del_sistema("semillas"), unidad="unidad")
        insumo("Detergente", tipo=self.tipo)
        por_nombre = {i.nombre_insumo: i for i in self.consultar()}
        self.assertTrue(por_nombre["Semilla Lechuga Crespa"].es_semilla)
        self.assertFalse(por_nombre["Detergente"].es_semilla)

    def test_regla_2_la_consulta_no_hace_una_consulta_por_insumo(self):
        """docs/patrones/abm.md: lo que se muestra de cada insumo (categoría y dónde está habilitado) sale en un número fijo de consultas."""
        for n in range(6):
            existencia(insumo(f"I{n}", tipo=self.tipo), crear_invernadero(f"Invernadero {n}"))
        with self.assertNumQueries(2):  # los insumos con su categoría (1) y sus invernaderos (1)
            self.consultar()

    # ---- regla 3: quién usa, quién gestiona y las acciones ----

    def test_regla_3_invernaderos_que_usan_el_insumo_son_los_activos_con_habilitacion_activa_por_nombre(self):
        """CMP-CNS-INS regla 3 y regla 1 de CMP-MOD-INS: un invernadero usa el insumo si está activo y lo tiene habilitado."""
        el_insumo = insumo("Detergente", tipo=self.tipo)
        existencia(el_insumo, crear_invernadero("Invernadero Sur"))
        existencia(el_insumo, crear_invernadero("Invernadero Norte"))
        existencia(el_insumo, crear_invernadero("Invernadero Este"), activo=False)
        existencia(el_insumo, crear_invernadero("Invernadero Cerrado", activo=False))
        self.assertEqual(
            [g.nombre_invernadero for g in insumos.invernaderos_que_usan(el_insumo.pk)], ["Invernadero Norte", "Invernadero Sur"]
        )

    def test_regla_3_quienes_lo_usan_nombra_el_invernadero_y_su_agronomo(self):
        """CMP-CNS-INS regla 3: «con el nombre de quién lo usa» (o «sin Agrónomo»)."""
        el_insumo = insumo("Detergente", tipo=self.tipo)
        luis = crear_agronomo(email="luis@infoponia.com", nombre="Luis", apellido="Paz")
        existencia(el_insumo, crear_invernadero("Invernadero Norte", agronomo=luis))
        existencia(el_insumo, crear_invernadero("Invernadero Sur"))
        self.assertEqual(
            insumos.quienes_lo_usan(el_insumo.pk), ["Invernadero Norte (Luis Paz)", "Invernadero Sur (sin Agrónomo)"]
        )

    def test_regla_3_puede_gestionar_si_nadie_lo_usa_o_si_es_el_agronomo_de_un_invernadero_que_lo_usa(self):
        """CMP-CNS-INS regla 3 y regla 1 de CMP-MOD-INS: cualquiera si nadie lo usa; si no, el Agrónomo de alguno que lo usa."""
        el_insumo = insumo("Detergente", tipo=self.tipo)
        ajeno = crear_agronomo(email="ajeno@infoponia.com")
        self.assertTrue(insumos.puede_gestionar(self.agronomo, el_insumo))
        existencia(el_insumo, crear_invernadero("Invernadero Norte", agronomo=ajeno))
        self.assertFalse(insumos.puede_gestionar(self.agronomo, el_insumo))
        self.assertTrue(insumos.puede_gestionar(ajeno, el_insumo))
        existencia(el_insumo, crear_invernadero("Invernadero Sur", agronomo=self.agronomo))
        self.assertTrue(insumos.puede_gestionar(self.agronomo, el_insumo))

    def test_regla_3_quien_no_es_agronomo_activo_no_puede_gestionar(self):
        """D-30: ni el Gerente ni una cuenta inactiva ni ``None`` gestionan."""
        el_insumo = insumo("Detergente", tipo=self.tipo)
        inactivo = crear_agronomo(email="inactivo@infoponia.com", activo=False)
        for cuenta in (crear_gerente(), inactivo, None):
            with self.subTest(cuenta=cuenta):
                self.assertFalse(insumos.puede_gestionar(cuenta, el_insumo))

    def test_regla_3_un_insumo_activo_ofrece_modificar_y_dar_de_baja(self):
        """CMP-CNS-INS regla 3: según su estado, inicia CMP-MOD-INS o CMP-BAJ-INS."""
        self.assertEqual(insumos.acciones_permitidas(self.agronomo, insumo("Detergente", tipo=self.tipo)), {"modificar", "baja"})

    def test_regla_3_un_insumo_inactivo_solo_ofrece_reactivar(self):
        """CMP-CNS-INS regla 3: «o lo reactiva»."""
        self.assertEqual(insumos.acciones_permitidas(self.agronomo, insumo("Viejo", tipo=self.tipo, activo=False)), {"reactivar"})

    def test_regla_3_las_semillas_no_tienen_estas_acciones(self):
        """CMP-CNS-INS regla 3: «las semillas no tienen estas acciones»."""
        for activo in (True, False):
            semilla = insumo(f"Semilla {activo}", tipo=categoria_del_sistema("semillas"), unidad="unidad", activo=activo)
            with self.subTest(activo=activo):
                self.assertEqual(insumos.acciones_permitidas(self.agronomo, semilla), frozenset())

    def test_regla_3_quien_no_es_agronomo_activo_no_tiene_acciones(self):
        """D-30: ningún botón lleva a un 403; para quien no puede, ninguna acción (sin error)."""
        el_insumo = insumo("Detergente", tipo=self.tipo)
        inactivo = crear_agronomo(email="inactivo@infoponia.com", activo=False)
        for cuenta in (crear_gerente(), crear_capataz(), inactivo, None):
            with self.subTest(cuenta=cuenta):
                self.assertEqual(insumos.acciones_permitidas(cuenta, el_insumo), frozenset())

    # ---- regla 5 y postcondición a ----

    def test_regla_5_y_post_a_la_consulta_no_cambia_nada_ni_audita(self):
        """CMP-CNS-INS regla 5 y postcondición a (SEG-14): ni cambia datos ni deja registro de auditoría."""
        insumo("Detergente", tipo=self.tipo)
        antes = RegistroAuditoria.objects.count()
        self.consultar()
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
