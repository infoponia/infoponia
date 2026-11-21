# Pruebas de CMP-CNS-TIN · Consultar Tipo de Insumo (docs/casos_de_uso/inventario/tipos_de_insumo.md). Cita D-28, D-30 y SEG-14.
#
# Servicios que se prueban (inventario/servicios/tipos_de_insumo.py), tomados del módulo dentro de cada prueba:
#   consultar_tipos_de_insumo(actor) -> QuerySet de TipoInsumo con ``cantidad_de_insumos`` (todos, activos e inactivos)
#     - Precondición a y regla 5: Agrónomo activo; el Gerente (y el resto) no consulta (PermissionDenied).
#     - Regla 1: todas, activas e inactivas, las activas primero y por nombre (sin distinguir mayúsculas).
#     - Regla 2: nombre, marca «del sistema», consumo directo, cantidad de insumos del catálogo y estado.
#     - Regla 6 y postcondición a: no cambia nada y no audita.
#   obtener_tipo_de_insumo(actor, tipo_id) -> TipoInsumo con ``cantidad_de_insumos`` (404 si no existe)
#   acciones_permitidas(actor, tipo) -> frozenset de ``{"modificar", "baja", "reactivar"}`` (regla 4; D-30: ningún botón lleva a un 403)
#     - Una del sistema no tiene acciones.

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, categoria_del_sistema, insumo, perezoso, tipo_de_insumo
from maestros.tests.fabricas import crear_agronomo

tipos = perezoso("inventario.servicios.tipos_de_insumo")


class CmpCnsTinServicioTests(ConDatosDeInventario, TestCase):
    """Precondición, reglas y postcondición de CMP-CNS-TIN."""

    def setUp(self):
        self.agronomo = crear_agronomo()

    def consultar(self, actor=None):
        return list(tipos.consultar_tipos_de_insumo(actor or self.agronomo))

    # ---- precondición a y regla 5 ----

    def test_pre_a_el_gerente_no_consulta_categorias(self):
        """CMP-CNS-TIN regla 5: «El Gerente no consulta categorías»."""
        with self.assertRaises(PermissionDenied):
            tipos.consultar_tipos_de_insumo(crear_gerente())

    def test_pre_a_capataz_administrador_y_un_agronomo_inactivo_no_consultan(self):
        """CMP-CNS-TIN precondición a: Agrónomo con la cuenta activa."""
        inactivo = crear_agronomo(email="inactivo@infoponia.com", activo=False)
        for cuenta in (crear_capataz(), crear_administrador(), inactivo):
            with self.subTest(cuenta=type(cuenta).__name__):
                with self.assertRaises(PermissionDenied):
                    tipos.consultar_tipos_de_insumo(cuenta)

    def test_pre_a_obtener_una_categoria_tambien_es_solo_del_agronomo_y_da_404_si_no_existe(self):
        """CMP-CNS-TIN precondición a y D-28."""
        tipo = tipo_de_insumo("Limpieza")
        with self.assertRaises(PermissionDenied):
            tipos.obtener_tipo_de_insumo(crear_gerente(), tipo.pk)
        with self.assertRaises(Http404):
            tipos.obtener_tipo_de_insumo(self.agronomo, 999999)
        self.assertEqual(tipos.obtener_tipo_de_insumo(self.agronomo, tipo.pk).pk, tipo.pk)

    # ---- reglas 1 y 2 ----

    def test_regla_1_consulta_todas_activas_e_inactivas_con_las_cuatro_del_sistema(self):
        """CMP-CNS-TIN regla 1 y verificación a mano 1: las cuatro del sistema, las activas y las inactivas."""
        tipo_de_insumo("Limpieza")
        tipo_de_insumo("Vieja", activo=False)
        nombres = [t.nombre_tipo_insumo for t in self.consultar()]
        self.assertEqual(len(nombres), 6)
        for esperado in ("Semillas", "Envases", "Repuestos de hardware", "Infraestructura", "Limpieza", "Vieja"):
            self.assertIn(esperado, nombres)

    def test_regla_1_las_activas_van_primero_y_cada_grupo_por_nombre_sin_distinguir_mayusculas(self):
        """CMP-CNS-TIN regla 1: orden estable para la pantalla (activas primero; después, por nombre)."""
        tipo_de_insumo("zeta")
        tipo_de_insumo("Alfa")
        tipo_de_insumo("beta", activo=False)
        tipo_de_insumo("Anfora", activo=False)
        nombres = [t.nombre_tipo_insumo for t in self.consultar()]
        self.assertEqual(
            nombres,
            ["Alfa", "Envases", "Infraestructura", "Repuestos de hardware", "Semillas", "zeta", "Anfora", "beta"],
        )

    def test_regla_2_cada_categoria_trae_su_nombre_marca_consumo_cantidad_de_insumos_y_estado(self):
        """CMP-CNS-TIN regla 2: lo que se ve de cada categoría."""
        limpieza = tipo_de_insumo("Limpieza", "como_gasto")
        por_nombre = {t.nombre_tipo_insumo: t for t in self.consultar()}
        self.assertEqual(
            (
                por_nombre["Limpieza"].es_del_sistema,
                por_nombre["Limpieza"].consumo_directo,
                por_nombre["Limpieza"].estado_tipo_insumo,
                por_nombre["Limpieza"].cantidad_de_insumos,
            ),
            (False, "como_gasto", "activo", 0),
        )
        self.assertEqual(
            (por_nombre["Envases"].es_del_sistema, por_nombre["Envases"].consumo_directo, limpieza.pk is not None),
            (True, "no_admite", True),
        )

    def test_regla_2_la_cantidad_de_insumos_cuenta_activos_e_inactivos_del_catalogo(self):
        """CMP-CNS-TIN regla 2: «la cantidad de insumos del catálogo que tiene» incluye los inactivos (la baja cuenta solo los activos)."""
        tipo = tipo_de_insumo("Limpieza")
        insumo("Detergente", tipo=tipo)
        insumo("Lavandina", tipo=tipo)
        insumo("Viejo", tipo=tipo, activo=False)
        insumo("Sobres", tipo=categoria_del_sistema("envases"), unidad="unidad")
        cantidades = {t.nombre_tipo_insumo: t.cantidad_de_insumos for t in self.consultar()}
        self.assertEqual((cantidades["Limpieza"], cantidades["Envases"], cantidades["Semillas"]), (3, 1, 0))

    def test_regla_2_la_consulta_no_hace_una_consulta_por_categoria(self):
        """docs/patrones/abm.md: la cantidad de insumos sale en la misma consulta (sin N+1)."""
        for n in range(5):
            insumo(f"I{n}", tipo=tipo_de_insumo(f"T{n}"))
        with self.assertNumQueries(1):  # la lista con la cantidad de insumos, sin consultas por categoría
            self.consultar()

    # ---- regla 4: las acciones ----

    def test_regla_4_una_categoria_comun_activa_ofrece_modificar_y_dar_de_baja(self):
        """CMP-CNS-TIN regla 4: desde una categoría que no es del sistema se inicia CMP-MOD-TIN o CMP-BAJ-TIN."""
        self.assertEqual(tipos.acciones_permitidas(self.agronomo, tipo_de_insumo("Limpieza")), {"modificar", "baja"})

    def test_regla_4_una_categoria_inactiva_solo_ofrece_reactivar(self):
        """CMP-CNS-TIN regla 4: «o la reactiva si está inactiva»."""
        self.assertEqual(tipos.acciones_permitidas(self.agronomo, tipo_de_insumo("Vieja", activo=False)), {"reactivar"})

    def test_regla_4_las_del_sistema_no_tienen_acciones(self):
        """CMP-CNS-TIN regla 4 y verificación a mano 1: el candado y ninguna acción."""
        for codigo in ("semillas", "envases", "repuestos_de_hardware", "infraestructura"):
            with self.subTest(codigo=codigo):
                self.assertEqual(tipos.acciones_permitidas(self.agronomo, categoria_del_sistema(codigo)), frozenset())

    def test_regla_5_quien_no_es_agronomo_activo_no_tiene_acciones(self):
        """D-30: ningún botón lleva a un 403; para quien no puede, ninguna acción (devuelve un frozenset vacío, sin error)."""
        tipo = tipo_de_insumo("Limpieza")
        inactivo = crear_agronomo(email="inactivo@infoponia.com", activo=False)
        for cuenta in (crear_gerente(), crear_capataz(), inactivo, None):
            with self.subTest(cuenta=cuenta):
                self.assertEqual(tipos.acciones_permitidas(cuenta, tipo), frozenset())

    # ---- regla 6 y postcondición a ----

    def test_regla_6_y_post_a_la_consulta_no_cambia_nada_ni_audita(self):
        """CMP-CNS-TIN regla 6 y postcondición a (SEG-14): ni cambia datos ni deja registro de auditoría."""
        tipo_de_insumo("Limpieza")
        antes = RegistroAuditoria.objects.count()
        self.consultar()
        tipos.obtener_tipo_de_insumo(self.agronomo, tipo_de_insumo("Otra").pk)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
