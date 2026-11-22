# Pruebas del modelo `Semilla` (INV-03, paso 1): una por variedad, protegida, y el invariante «una Semilla está en la categoría
# `semillas` y ningún otro insumo lo está». Fuente: docs/modelo/inventario.md («Semilla», «Reglas que la tocan») y D-49.

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from inventario.models import Insumo, Semilla
from inventario.tests.fabricas import ConDatosDeInventario, categoria_del_sistema, insumo, variedad_con_semilla


class SemillaModeloTests(ConDatosDeInventario, TestCase):
    """Restricciones y herencia de ``Semilla``."""

    def test_r137_una_semilla_por_variedad(self):
        """R137 (único ``variedad_id``): una variedad no puede tener dos semillas."""
        variedad = variedad_con_semilla()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Semilla.objects.create(
                nombre_insumo="Otra semilla",
                tipo_insumo=categoria_del_sistema("semillas"),
                unidad_medida_insumo="unidad",
                variedad=variedad,
            )

    def test_r137_la_variedad_apunta_a_su_semilla(self):
        """R137: ``variedad.semilla`` es la semilla creada, y es un ``Insumo`` (herencia multitabla, ``insumo_ptr``)."""
        variedad = variedad_con_semilla(nombre="Butterhead")
        self.assertEqual(variedad.semilla.nombre_insumo, "Semilla Lechuga Butterhead")
        self.assertTrue(Insumo.objects.filter(pk=variedad.semilla.pk).exists())

    def test_la_fabrica_deja_la_semilla_como_pide_la_postcondicion_c(self):
        """PROD-ALT-VAR postcondición c: categoría Semillas, por unidad, con control de vencimiento y estado de su variedad."""
        activa = variedad_con_semilla(nombre="A").semilla
        inactiva = variedad_con_semilla(nombre="B", activa=False).semilla
        self.assertEqual(activa.tipo_insumo.codigo, "semillas")
        self.assertEqual(activa.unidad_medida_insumo, "unidad")
        self.assertTrue(activa.controla_vencimiento)
        self.assertEqual((activa.estado_insumo, inactiva.estado_insumo), ("activo", "inactivo"))

    def test_la_variedad_con_semilla_no_se_borra(self):
        """Modelo de inventario: la FK es PROTECT (las bajas son lógicas): no se puede borrar la variedad de una semilla."""
        variedad = variedad_con_semilla()
        with self.assertRaises(ProtectedError):
            variedad.delete()

    def test_str_es_el_nombre(self):
        """D-36: el texto de la auditoría de una semilla es su nombre."""
        self.assertEqual(str(variedad_con_semilla().semilla), "Semilla Lechuga Crespa")

    def test_invariante_semilla_si_y_solo_si_categoria_semillas(self):
        """docs/modelo/inventario.md, «La categoría la fija el servicio»: toda ``Semilla`` está en la categoría ``semillas`` y
        ningún otro insumo lo está (el alta de insumos no ofrece esa categoría, regla 4 de CMP-ALT-INS)."""
        variedad_con_semilla(nombre="A")
        variedad_con_semilla(nombre="B", activa=False)
        insumo("Detergente")
        en_semillas = set(Insumo.objects.filter(tipo_insumo__codigo="semillas").values_list("pk", flat=True))
        self.assertEqual(en_semillas, set(Semilla.objects.values_list("pk", flat=True)))
        self.assertEqual(len(en_semillas), 2)
