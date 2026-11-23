# Pruebas de CMP-CNS-PRV · Consultar Proveedor (docs/casos_de_uso/compras/proveedores.md). Cita D-28, D-30 y SEG-14.
#
# Servicios que se prueban (compras/servicios/proveedores.py), tomados del módulo dentro de cada prueba:
#   listar_proveedores(actor, filtros=None) -> queryset de Proveedor
#     - Precondición a: Agrónomo o Gerente activos (PermissionDenied si no). Regla 1: ven todos, activos e inactivos.
#     - Regla 2: filtros ``estado`` («activo», «inactivo» o vacío para todos), ``texto`` (razón social, nombre, apellido o CUIT, sin
#       distinguir mayúsculas; varias palabras: todas) y ``tipo_de_insumo`` (id de una categoría de las que se especializa).
#     - Regla 3: del listado se leen razón social o nombre, CUIT, correo, teléfono, categorías activas y estado.
#   ficha_de_proveedor(actor, proveedor_id) -> Proveedor  (404 si no existe)
#     - Regla 4: los datos del proveedor; sus pedidos, órdenes, pagos y reclamos se completan de CMP-02a a CMP-06.
#   acciones_permitidas(actor, proveedor) -> frozenset  (regla 5 y D-30: ningún botón lleva a un 403)
#     - Regla 6 y SEG-14: la consulta no se audita.

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase

from compras.tests.fabricas import GERENTE, cuit_valido, proveedor, tipo_de_insumo
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from maestros.tests.fabricas import crear_agronomo, crear_vendedor

proveedores = perezoso("compras.servicios.proveedores")


class CmpCnsPrvServicioTests(TestCase):
    """Precondición, reglas y postcondición de CMP-CNS-PRV."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.limpieza = tipo_de_insumo("Limpieza")
        self.nutrientes = tipo_de_insumo("Nutrientes")
        self.sur = proveedor("Semillas del Sur S. A.", n=1, especialidades=[self.limpieza, self.nutrientes])
        self.norte = proveedor("Agro Norte S. R. L.", n=2, especialidades=[self.nutrientes], activo=False)
        self.ana = proveedor(n=3, tipo="fisica", nombre="Ana", apellido="Gómez", email="ana@mail.com")

    def listar(self, actor=GERENTE, **filtros):
        return list(proveedores.listar_proveedores(self.gerente if actor is GERENTE else actor, filtros))

    # ---- precondición a y regla 1 ----

    def test_pre_a_el_gerente_y_el_agronomo_activos_consultan(self):
        """CMP-CNS-PRV precondición a y regla 1: ambos ven todos los proveedores, activos e inactivos."""
        for actor in (self.gerente, self.agronomo):
            with self.subTest(rol=actor.rol):
                self.assertEqual(set(self.listar(actor)), {self.sur, self.norte, self.ana})

    def test_pre_a_los_demas_roles_y_las_cuentas_inactivas_no_consultan(self):
        """CMP-CNS-PRV precondición a y SEG-13: ningún otro rol, ni una cuenta dada de baja."""
        for actor in (crear_capataz(), crear_vendedor(), crear_administrador(), crear_agronomo(email="b@infoponia.com", activo=False), None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    self.listar(actor)
                with self.assertRaises(PermissionDenied):
                    proveedores.ficha_de_proveedor(actor, self.sur.pk)

    def test_regla_1_el_listado_va_por_nombre_con_los_activos_primero(self):
        """CMP-CNS-PRV regla 1 y docs/patrones/abm.md, sección 7: los activos primero y por nombre (sin distinguir mayúsculas)."""
        self.assertEqual(self.listar(), [self.ana, self.sur, self.norte])

    # ---- regla 2: filtros ----

    def test_regla_2_filtra_por_estado(self):
        """CMP-CNS-PRV regla 2: estado activo, inactivo o todos."""
        self.assertEqual(set(self.listar(estado="activo")), {self.sur, self.ana})
        self.assertEqual(self.listar(estado="inactivo"), [self.norte])
        self.assertEqual(set(self.listar(estado="")), {self.sur, self.norte, self.ana})

    def test_regla_2_filtra_por_texto_en_razon_social_nombre_apellido_y_cuit(self):
        """CMP-CNS-PRV regla 2: texto en razón social, nombre, apellido o CUIT, sin distinguir mayúsculas ni tildes de mayúscula."""
        self.assertEqual(self.listar(texto="semillas"), [self.sur])
        self.assertEqual(self.listar(texto="ANA"), [self.ana])
        self.assertEqual(self.listar(texto="gómez"), [self.ana])
        self.assertEqual(self.listar(texto="ana gómez"), [self.ana])
        self.assertEqual(self.listar(texto="xyz"), [])

    def test_regla_2_el_texto_busca_el_cuit_con_o_sin_guiones(self):
        """CMP-CNS-PRV regla 2: el CUIT se encuentra escribiéndolo completo, con guiones, o solo una parte de sus dígitos (como el prototipo)."""
        cuit = cuit_valido(1)
        con_guiones = f"{cuit[:2]}-{cuit[2:10]}-{cuit[10:]}"
        self.assertEqual(self.listar(texto=cuit), [self.sur])
        self.assertEqual(self.listar(texto=con_guiones), [self.sur])
        self.assertEqual(self.listar(texto=cuit[6:10]), [self.sur])

    def test_regla_2_filtra_por_tipo_de_insumo(self):
        """CMP-CNS-PRV regla 2: tipo de insumo en que se especializa."""
        self.assertEqual(set(self.listar(tipo_de_insumo=self.nutrientes.pk)), {self.sur, self.norte})
        self.assertEqual(self.listar(tipo_de_insumo=self.limpieza.pk), [self.sur])

    def test_regla_2_los_filtros_se_combinan(self):
        """CMP-CNS-PRV regla 2: estado, texto y tipo de insumo se combinan (todos tienen que cumplirse)."""
        self.assertEqual(self.listar(estado="activo", tipo_de_insumo=self.nutrientes.pk), [self.sur])
        self.assertEqual(self.listar(estado="inactivo", texto="semillas"), [])

    def test_regla_2_un_proveedor_con_dos_categorias_no_se_repite(self):
        """CMP-CNS-PRV regla 2: un proveedor aparece una sola vez aunque coincida con varias categorías."""
        otra = tipo_de_insumo("Herramientas")
        self.sur.especialidades.add(otra)
        self.assertEqual(self.listar(texto="semillas", tipo_de_insumo=self.limpieza.pk).count(self.sur), 1)

    # ---- regla 3: listado ----

    def test_regla_3_el_listado_trae_solo_las_categorias_activas(self):
        """CMP-CNS-PRV regla 3: los tipos de insumo en que se especializa, solo categorías activas (el vínculo con la dada de baja se conserva)."""
        self.nutrientes.estado_tipo_insumo = "inactivo"
        self.nutrientes.save()
        sur = next(p for p in proveedores.listar_proveedores(self.gerente, {}) if p.pk == self.sur.pk)
        self.assertEqual([c.pk for c in sur.categorias_activas], [self.limpieza.pk])
        self.assertEqual(self.sur.especialidades.count(), 2)

    def test_regla_3_el_listado_no_hace_una_consulta_por_proveedor(self):
        """Eficiencia: las categorías activas se traen con una consulta aparte para todos, no una por proveedor."""
        with self.assertNumQueries(2):
            lista = list(proveedores.listar_proveedores(self.gerente, {}))
            [list(p.categorias_activas) for p in lista]

    # ---- regla 4: ficha ----

    def test_regla_4_la_ficha_trae_el_proveedor_con_sus_categorias_activas(self):
        """CMP-CNS-PRV regla 4: los datos del proveedor y sus categorías activas. Pedidos, órdenes, pagos y reclamos se completan en CMP-02a a CMP-06."""
        self.limpieza.estado_tipo_insumo = "inactivo"
        self.limpieza.save()
        ficha = proveedores.ficha_de_proveedor(self.agronomo, self.sur.pk)
        self.assertEqual(ficha.pk, self.sur.pk)
        self.assertEqual([c.pk for c in ficha.categorias_activas], [self.nutrientes.pk])

    def test_regla_4_la_ficha_de_un_inactivo_tambien_se_ve(self):
        """CMP-CNS-PRV regla 1: ven también los inactivos."""
        self.assertEqual(proveedores.ficha_de_proveedor(self.gerente, self.norte.pk).pk, self.norte.pk)

    def test_regla_4_un_proveedor_que_no_existe_da_404(self):
        """docs/patrones/abm.md, sección 6: un id inexistente da 404."""
        with self.assertRaises(Http404):
            proveedores.ficha_de_proveedor(self.gerente, 999999)

    # ---- regla 5: botones ----

    def test_regla_5_el_gerente_modifica_y_da_de_baja_a_un_activo(self):
        """CMP-CNS-PRV regla 5 y D-30: sobre un proveedor activo, el Gerente puede modificar y dar de baja."""
        self.assertEqual(proveedores.acciones_permitidas(self.gerente, self.sur), frozenset({"modificar", "baja"}))

    def test_regla_5_el_gerente_solo_reactiva_a_un_inactivo(self):
        """CMP-CNS-PRV regla 5: un inactivo se reactiva desde el alta; no se modifica ni se da de baja."""
        self.assertEqual(proveedores.acciones_permitidas(self.gerente, self.norte), frozenset({"reactivar"}))

    def test_regla_5_el_agronomo_solo_consulta(self):
        """CMP-CNS-PRV regla 5: el Agrónomo no tiene ninguna acción; ningún botón lleva a un 403 (D-30)."""
        for p in (self.sur, self.norte):
            self.assertEqual(proveedores.acciones_permitidas(self.agronomo, p), frozenset())

    def test_regla_5_sin_permiso_no_hay_acciones(self):
        """D-30: ni un Gerente inactivo ni otro rol ni sin cuenta tienen acciones."""
        for actor in (crear_capataz(), crear_gerente(email="b@infoponia.com", activo=False), None):
            self.assertEqual(proveedores.acciones_permitidas(actor, self.sur), frozenset())

    # ---- postcondición a y regla 6 ----

    def test_post_a_y_regla_6_la_consulta_no_audita_ni_cambia_datos(self):
        """CMP-CNS-PRV postcondición a y regla 6 (SEG-14): listar y ver la ficha no escriben nada ni dejan registro."""
        registros = RegistroAuditoria.objects.count()
        self.listar()
        self.listar(texto="semillas", estado="activo")
        proveedores.ficha_de_proveedor(self.gerente, self.sur.pk)
        self.assertEqual(RegistroAuditoria.objects.count(), registros)
        self.sur.refresh_from_db()
        self.assertEqual(self.sur.estado_proveedor, "activo")
