# Pruebas de las acciones de auditoría que suma PRD-01 (D-36, docs/patrones/auditoria.md): `planificacion_siembra`,
# `concrecion_siembra` y `cancelacion_orden` están clasificadas como de negocio (las ve el Gerente, no el Administrador) y sus
# datos tienen nombre visible. La prueba general de que toda acción está clasificada es `test_d36_cada_accion_esta_clasificada…`
# de test_aud_cns_reg.py; acá se cubre lo propio de estas tres.

from django.test import TestCase

import core.models as modelos
from core import servicios
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_gerente
from core.tests.test_aud_cns_reg import anotar

Accion = RegistroAuditoria.Accion
ACCIONES_DE_SIEMBRA = (Accion.PLANIFICACION_SIEMBRA, Accion.CONCRECION_SIEMBRA, Accion.CANCELACION_ORDEN)


class AuditoriaDeProduccionTests(TestCase):
    def test_d36_las_tres_acciones_son_de_negocio_y_no_de_cuentas(self):
        """D-36: las acciones de PRD-01 están en ``ACCIONES_DE_NEGOCIO`` y en ninguna otra clasificación."""
        for accion in ACCIONES_DE_SIEMBRA:
            with self.subTest(accion=accion):
                self.assertIn(accion, modelos.ACCIONES_DE_NEGOCIO)
                self.assertNotIn(accion, modelos.ACCIONES_DE_CUENTAS)

    def test_d36_el_gerente_las_ve_en_auditoria_aunque_solo_afecten_su_cuenta(self):
        """AUD-CNS-REG regla 1 y D-36: una acción de negocio es visible para el Gerente aunque el único afectado sea su propia
        cuenta (un registro es «de cuentas» por su acción, no por sus afectados); el Administrador ve todo."""
        gerente = crear_gerente()
        registros = [anotar(gerente, accion, [gerente]) for accion in ACCIONES_DE_SIEMBRA]
        vistos_por_el_gerente = set(servicios.consultar_auditoria(gerente).values_list("pk", flat=True))
        vistos_por_el_administrador = set(servicios.consultar_auditoria(crear_administrador()).values_list("pk", flat=True))
        for registro in registros:
            self.assertIn(registro.pk, vistos_por_el_gerente)
            self.assertIn(registro.pk, vistos_por_el_administrador)

    def test_d36_las_acciones_tienen_etiqueta_legible(self):
        """D-36: cada acción se muestra con su texto, no con su clave."""
        self.assertEqual(Accion.PLANIFICACION_SIEMBRA.label, "Planificación de siembra")
        self.assertEqual(Accion.CONCRECION_SIEMBRA.label, "Concreción de siembra")
        self.assertEqual(Accion.CANCELACION_ORDEN.label, "Cancelación de orden de trabajo")

    def test_d50_los_agujeros_comprometidos_y_ocupados_tienen_nombre_visible(self):
        """D-50 punto 4: los cambios de agujeros de cada sector se muestran con nombre visible, y la prioridad con su texto."""
        self.assertEqual(RegistroAuditoria.ETIQUETAS["agujeros_comprometidos"], "Agujeros comprometidos")
        self.assertEqual(RegistroAuditoria.ETIQUETAS["agujeros_ocupados"], "Agujeros ocupados")
        self.assertEqual(RegistroAuditoria.VALORES_VISIBLES["prioridad_orden"]["media"], "Media")


class AuditoriaDeTransicionTests(TestCase):
    """Acciones que suma PRD-02 (D-36): `planificacion_transicion`, `concrecion_transicion` y `registro_merma`."""

    ACCIONES = (Accion.PLANIFICACION_TRANSICION, Accion.CONCRECION_TRANSICION, Accion.REGISTRO_MERMA)

    def test_d36_las_tres_acciones_son_de_negocio_y_no_de_cuentas(self):
        """D-36: están en ``ACCIONES_DE_NEGOCIO`` y en ninguna otra clasificación (la ve el Gerente)."""
        for accion in self.ACCIONES:
            with self.subTest(accion=accion):
                self.assertIn(accion, modelos.ACCIONES_DE_NEGOCIO)
                self.assertNotIn(accion, modelos.ACCIONES_DE_CUENTAS)

    def test_d36_las_acciones_y_los_datos_tienen_nombre_visible(self):
        """D-36: cada acción y cada dato nuevo se muestra con su texto, no con su clave."""
        self.assertEqual(Accion.PLANIFICACION_TRANSICION.label, "Planificación de transición")
        self.assertEqual(Accion.CONCRECION_TRANSICION.label, "Concreción de transición")
        self.assertEqual(Accion.REGISTRO_MERMA.label, "Registro de merma")
        for clave in ("etapa_destino", "cantidad_transferida", "fecha_transicion", "cantidad_actual", "costo_acumulado", "merma"):
            self.assertIn(clave, RegistroAuditoria.ETIQUETAS)
