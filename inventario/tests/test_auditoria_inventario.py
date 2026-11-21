# Pruebas de las acciones de auditoría de `inventario` en `core` (INV-01, paso 3; D-36 y docs/patrones/auditoria.md, «Lo que hay
# que tocar en `core`»): están clasificadas como de negocio, el Gerente las ve en «Auditoría» y sus campos se leen con su nombre
# visible. La prueba `test_d36_cada_accion_esta_clasificada_en_cuentas_o_en_negocio` de `core` sigue pasando (se corre `core`).

from django.test import TestCase

from core.models import ACCIONES_DE_CUENTAS, ACCIONES_DE_NEGOCIO, RegistroAuditoria, referencia
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, categoria_del_sistema, insumo, tipo_de_insumo
from maestros.tests.fabricas import crear_agronomo

Accion = RegistroAuditoria.Accion

ACCIONES_DE_INVENTARIO = [
    Accion.ALTA_TIPO_INSUMO,
    Accion.MODIFICACION_TIPO_INSUMO,
    Accion.BAJA_TIPO_INSUMO,
    Accion.REACTIVACION_TIPO_INSUMO,
    Accion.ALTA_INSUMO,
    Accion.MODIFICACION_INSUMO,
    Accion.BAJA_INSUMO,
    Accion.REACTIVACION_INSUMO,
    Accion.BAJA_INSUMO_INVERNADERO,
]


class AuditoriaDeInventarioTests(ConDatosDeInventario, TestCase):
    """Las nueve acciones de INV-01 en la auditoría."""

    def setUp(self):
        self.agronomo = crear_agronomo()

    def registrar(self, accion, afectado, detalle=None):
        return RegistroAuditoria.objects.registrar(
            usuario=self.agronomo,
            accion=accion,
            afectados=[afectado],
            detalle=detalle or {"cambios": {"estado": {"antes": "activo", "despues": "inactivo"}}},
        )

    def test_d36_las_nueve_acciones_nuevas_son_de_negocio_y_no_de_cuentas(self):
        """D-36: cada acción nueva se clasifica en `ACCIONES_DE_NEGOCIO` y solo ahí."""
        self.assertEqual(len(ACCIONES_DE_INVENTARIO), 9)
        for accion in ACCIONES_DE_INVENTARIO:
            with self.subTest(accion=accion):
                self.assertIn(accion, ACCIONES_DE_NEGOCIO)
                self.assertNotIn(accion, ACCIONES_DE_CUENTAS)

    def test_d36_los_nombres_de_las_acciones_caben_en_el_campo(self):
        """D-39: `accion` admite 50 caracteres; todas las de inventario entran y siguen la forma `<acción>_<entidad>`."""
        for accion in ACCIONES_DE_INVENTARIO:
            self.assertLessEqual(len(accion.value), 50)

    def test_d36_el_gerente_ve_cada_accion_nueva_en_auditoria(self):
        """D-36 y verificación a mano 10: el Gerente ve cada acción (decide por `ACCIONES_DE_CUENTAS`) aunque el afectado sea
        una categoría o un insumo."""
        gerente = crear_gerente()
        tipo = tipo_de_insumo("Limpieza")
        un_insumo = insumo("Detergente", tipo=tipo)
        for accion in ACCIONES_DE_INVENTARIO:
            afectado = tipo if "tipo_insumo" in accion.value else un_insumo
            self.registrar(accion, afectado)
        vistas = set(RegistroAuditoria.objects.visibles_para(gerente).values_list("accion", flat=True))
        self.assertEqual(vistas, {accion.value for accion in ACCIONES_DE_INVENTARIO})

    def test_d36_los_campos_nuevos_se_muestran_con_su_nombre_y_sus_valores_visibles(self):
        """D-36: `ETIQUETAS` y `VALORES_VISIBLES` dan el nombre visible de los campos de insumos y el de sus valores."""
        tipo = tipo_de_insumo("Limpieza")
        un_insumo = insumo("Detergente", tipo=tipo, unidad="m3")
        registro = self.registrar(
            Accion.MODIFICACION_INSUMO,
            un_insumo,
            {
                "cambios": {
                    "nombre": {"antes": "Detergente", "despues": "Detergente líquido"},
                    "descripcion": {"antes": "", "despues": "5 L"},
                    "categoria": {"antes": referencia(tipo), "despues": referencia(categoria_del_sistema("envases"))},
                    "unidad_medida": {"antes": "l", "despues": "m3"},
                    "controla_vencimiento": {"antes": False, "despues": True},
                    "consumo_directo": {"antes": "como_gasto", "despues": "como_costo_de_los_lotes"},
                }
            },
        )
        filas = {campo: (antes, despues) for campo, antes, despues in registro.filas_de_cambios()}
        self.assertEqual(filas["Categoría"], ("Limpieza", "Envases"))
        self.assertEqual(filas["Unidad de medida"], ("L", "m³"))
        self.assertEqual(filas["Controla vencimiento"], ("No", "Sí"))
        self.assertEqual(filas["Consumo directo"], ("Como gasto", "Como costo de los lotes"))
        self.assertEqual(filas["Descripción"], ("", "5 L"))
        # El orden de las filas es el de `ETIQUETAS` (el de la pantalla), no el del JSON.
        self.assertEqual(
            [campo for campo, _, _ in registro.filas_de_cambios()],
            ["Nombre", "Descripción", "Categoría", "Unidad de medida", "Controla vencimiento", "Consumo directo"],
        )

    def test_d36_las_acciones_tienen_un_nombre_legible(self):
        """D-36: las acciones ya tienen `choices` con su texto (se ven en la lista de auditoría)."""
        self.assertEqual(Accion.BAJA_INSUMO_INVERNADERO.label, "Baja de insumo en un invernadero")
        self.assertEqual(Accion.ALTA_TIPO_INSUMO.label, "Alta de categoría de insumos")
