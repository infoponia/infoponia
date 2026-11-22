# Pruebas de las acciones de auditoría de variedades en `core` (INV-03, paso 2; D-36 y docs/patrones/auditoria.md, «Lo que hay que
# tocar en `core`»): están clasificadas como de negocio, el Gerente las ve en «Auditoría» y sus campos se leen con su nombre visible.
# La prueba `test_d36_cada_accion_esta_clasificada_en_cuentas_o_en_negocio` de `core` sigue pasando (se corre `core`).

from django.test import TestCase

from core.models import ACCIONES_DE_CUENTAS, ACCIONES_DE_NEGOCIO, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, variedad_con_semilla
from maestros.tests.fabricas import crear_agronomo

Accion = RegistroAuditoria.Accion

ACCIONES_DE_VARIEDADES = [
    Accion.ALTA_VARIEDAD,
    Accion.MODIFICACION_VARIEDAD,
    Accion.BAJA_VARIEDAD,
    Accion.REACTIVACION_VARIEDAD,
    Accion.MODIFICACION_SEMILLA,
]


class AuditoriaDeVariedadesTests(ConDatosDeInventario, TestCase):
    """Las cinco acciones de INV-03 en la auditoría."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.variedad = variedad_con_semilla()

    def registrar(self, accion, detalle=None):
        return RegistroAuditoria.objects.registrar(
            usuario=self.agronomo,
            accion=accion,
            afectados=[self.variedad, self.variedad.semilla],
            detalle=detalle or {"cambios": {"estado": {"antes": "activo", "despues": "inactivo"}}},
        )

    def test_d36_las_cinco_acciones_nuevas_son_de_negocio_y_no_de_cuentas(self):
        """D-36: cada acción nueva se clasifica en `ACCIONES_DE_NEGOCIO` y solo ahí."""
        for accion in ACCIONES_DE_VARIEDADES:
            with self.subTest(accion=accion):
                self.assertIn(accion, ACCIONES_DE_NEGOCIO)
                self.assertNotIn(accion, ACCIONES_DE_CUENTAS)

    def test_d36_los_nombres_de_las_acciones_caben_en_el_campo(self):
        """D-39: `accion` admite 50 caracteres; todas entran."""
        for accion in ACCIONES_DE_VARIEDADES:
            self.assertLessEqual(len(accion.value), 50)

    def test_d36_el_gerente_ve_cada_accion_nueva_en_auditoria(self):
        """D-36 y PROD-ALT-VAR postcondición d: el Gerente ve cada acción (decide por `ACCIONES_DE_CUENTAS`)."""
        gerente = crear_gerente()
        for accion in ACCIONES_DE_VARIEDADES:
            self.registrar(accion)
        vistas = set(RegistroAuditoria.objects.visibles_para(gerente).values_list("accion", flat=True))
        self.assertEqual(vistas, {accion.value for accion in ACCIONES_DE_VARIEDADES})

    def test_d36_los_campos_nuevos_se_muestran_con_su_nombre_y_sus_valores_visibles(self):
        """D-36: `ETIQUETAS` y `VALORES_VISIBLES` dan el nombre visible de los campos de una variedad y del perfil familiar."""
        registro = self.registrar(
            Accion.MODIFICACION_VARIEDAD,
            {
                "cambios": {
                    "nombre": {"antes": "Crespa", "despues": "Butterhead"},
                    "perfil_familia": {"antes": "hoja_verde", "despues": "frutos_pequenos"},
                    "etapas": {"antes": ["Germinación: 5 días"], "despues": ["Germinación: 6 días"]},
                    "temp_ambiente_min": {"antes": "18,00", "despues": "17,00"},
                    "temp_ambiente_max": {"antes": "24,00", "despues": "25,00"},
                    "humedad_min": {"antes": "60,00", "despues": "55,00"},
                    "humedad_max": {"antes": "80,00", "despues": "85,00"},
                    "intensidad_luz_min": {"antes": "200,00", "despues": "150,00"},
                    "intensidad_luz_max": {"antes": "400,00", "despues": "450,00"},
                    "fotoperiodo_min": {"antes": "12,00", "despues": "10,00"},
                    "fotoperiodo_max": {"antes": "16,00", "despues": "18,00"},
                    "duracion_post_cosecha": {"antes": "7", "despues": "10"},
                    "peso_promedio_planta": {"antes": "150", "despues": "200"},
                    "nombre_semilla": {"antes": "Semilla Lechuga Crespa", "despues": "Semilla Lechuga Butterhead"},
                }
            },
        )
        filas = {campo: (antes, despues) for campo, antes, despues in registro.filas_de_cambios()}
        self.assertEqual(filas["Perfil familiar"], ("Hoja verde", "Frutos pequeños"))
        self.assertEqual(filas["Temperatura ambiente mínima (°C)"], ("18,00", "17,00"))
        self.assertEqual(filas["Fotoperíodo máximo (h/día)"], ("16,00", "18,00"))
        self.assertEqual(filas["Duración postcosecha (días)"], ("7", "10"))
        self.assertEqual(filas["Peso promedio por planta (g)"], ("150", "200"))
        self.assertEqual(filas["Nombre de la semilla"], ("Semilla Lechuga Crespa", "Semilla Lechuga Butterhead"))
        self.assertEqual(len(filas), 14)
        # El orden de las filas es el de `ETIQUETAS` (el de la pantalla), no el del JSON.
        self.assertEqual(
            [campo for campo, _, _ in registro.filas_de_cambios()][:3], ["Nombre", "Perfil familiar", "Etapas"]
        )

    def test_d36_las_acciones_tienen_un_nombre_legible(self):
        """D-36: las acciones ya tienen `choices` con su texto (se ven en la lista de auditoría)."""
        self.assertEqual(Accion.ALTA_VARIEDAD.label, "Alta de variedad")
        self.assertEqual(Accion.MODIFICACION_SEMILLA.label, "Modificación de semilla")
