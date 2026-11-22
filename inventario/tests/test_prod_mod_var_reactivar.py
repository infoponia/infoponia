# Pruebas de la reactivación de una variedad (PROD-MOD-VAR postcondición d y regla 9; INV-03, paso 5): `reactivar_variedad(actor,
# variedad_id)`. Fuente: docs/casos_de_uso/inventario/variedades.md («Reactivación», regla 9 de MOD y regla 4 de CNS), docs/modelo/inventario.md
# («Semilla») y D-36. Reactiva la variedad y su semilla y NO toca las existencias de la semilla: no vuelve a habilitar las que estaban
# deshabilitadas, y las que quedaron activas con la baja siguen activas. Exige el cultivo activo (lo bloquea antes de verificarlo).

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.models import Insumo, InsumoInvernadero
from inventario.tests.fabricas import ConDatosDeInventario, existencia, lote, perezoso, variedad_con_semilla
from maestros.models import Variedad
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_cultivo, crear_invernadero, error_de

variedades = perezoso("inventario.servicios.variedades")


class ReactivarVariedadTests(ConDatosDeInventario, TestCase):
    """Una variedad dada de baja (con su semilla inactiva) en el cultivo «Lechuga»."""

    def setUp(self):
        self.ana = crear_agronomo("ana@infoponia.com", nombre="Ana", apellido="Pérez")
        self.beto = crear_agronomo("beto@infoponia.com", nombre="Beto", apellido="Gómez")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.beto)
        self.cultivo = crear_cultivo("Lechuga")
        self.variedad = variedad_con_semilla(self.cultivo, "Crespa", activa=False)

    def reactivar(self, actor=None):
        return variedades.reactivar_variedad(actor or self.ana, self.variedad.pk)

    def test_post_d_reactiva_la_variedad_y_su_semilla(self):
        """PROD-MOD-VAR postcondición d: si reactivó la variedad, ella y su semilla quedaron en estado «activo»."""
        devuelta = self.reactivar()
        self.assertEqual(devuelta.pk, self.variedad.pk)
        self.assertEqual(Variedad.objects.get(pk=self.variedad.pk).estado_variedad, "activo")
        self.assertEqual(Insumo.objects.get(pk=self.variedad.semilla.pk).estado_insumo, "activo")

    def test_regla_9_no_toca_las_existencias_de_la_semilla(self):
        """PROD-MOD-VAR regla 9: no la vuelve a habilitar donde estaba deshabilitada, y deja activa la que quedó activa con la baja
        (con su stock): ni estado ni lotes cambian."""
        deshabilitada = existencia(self.variedad.semilla, self.norte, activo=False)
        con_stock = existencia(self.variedad.semilla, self.sur)
        lote(con_stock, 12)
        self.reactivar(self.beto)  # la usa Sur (de Beto) con su existencia activa; la de Norte está deshabilitada
        deshabilitada.refresh_from_db()
        con_stock.refresh_from_db()
        self.assertEqual((deshabilitada.estado_insumo_invernadero, con_stock.estado_insumo_invernadero), ("inactivo", "activo"))
        self.assertEqual(InsumoInvernadero.objects.count(), 2)
        self.assertEqual([l.cantidad_disponible for l in con_stock.lotes.all()], [12])

    def test_regla_9_exige_el_cultivo_activo(self):
        """PROD-MOD-VAR regla 9: «solo si su cultivo está activo»: error general ``cultivo_inactivo`` y nada cambia."""
        self.cultivo.estado_cultivo = "inactivo"
        self.cultivo.save()
        error = error_de(self.reactivar)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["cultivo_inactivo"])
        self.assertEqual(Variedad.objects.get(pk=self.variedad.pk).estado_variedad, "inactivo")
        self.assertEqual(Insumo.objects.get(pk=self.variedad.semilla.pk).estado_insumo, "inactivo")

    def test_regla_9_una_variedad_activa_no_se_reactiva(self):
        """PROD-MOD-VAR regla 9: solo se reactiva una variedad inactiva (``variedad_no_inactiva``)."""
        activa = variedad_con_semilla(self.cultivo, "Lisa")
        error = error_de(lambda: variedades.reactivar_variedad(self.ana, activa.pk))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["variedad_no_inactiva"])
        self.assertFalse(RegistroAuditoria.objects.filter(accion="reactivacion_variedad").exists())

    def test_pre_a_solo_un_agronomo_activo_reactiva(self):
        """PROD-MOD-VAR precondición a."""
        with self.assertRaises(PermissionDenied):
            self.reactivar(crear_gerente())
        with self.assertRaises(PermissionDenied):
            self.reactivar(crear_agronomo("inactivo@infoponia.com", activo=False))

    def test_pre_a_una_variedad_inexistente_da_404(self):
        """Una variedad que no existe es 404."""
        with self.assertRaises(Http404):
            variedades.reactivar_variedad(self.ana, 999999)

    def test_regla_1_la_reactiva_el_agronomo_de_un_invernadero_que_la_usa_y_no_otro(self):
        """PROD-MOD-VAR regla 1: la semilla habilitada (activa tras la baja) hace que la use Norte: solo Ana la reactiva; a Beto se le
        dice quiénes la usan. Se verifica DESPUÉS de bloquear."""
        existencia(self.variedad.semilla, self.norte)
        error = error_de(lambda: self.reactivar(self.beto))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["variedad_en_uso_por_otros"])
        self.assertIn("Invernadero Norte (Ana Pérez)", error.error_dict[NON_FIELD_ERRORS][0].message)
        self.assertEqual(Variedad.objects.get(pk=self.variedad.pk).estado_variedad, "inactivo")
        self.reactivar(self.ana)
        self.assertEqual(Variedad.objects.get(pk=self.variedad.pk).estado_variedad, "activo")

    def test_post_e_un_registro_reactivacion_variedad_con_el_cambio_de_estado(self):
        """PROD-MOD-VAR postcondición e y D-36: un registro ``reactivacion_variedad`` con el estado de inactivo a activo, la variedad y
        su semilla como afectados."""
        self.reactivar()
        registro = RegistroAuditoria.objects.get(accion="reactivacion_variedad")
        self.assertEqual(registro.usuario_id, self.ana.pk)
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "inactivo", "despues": "activo"}})
        self.assertEqual(
            {(a["modelo"], a["id"]) for a in registro.afectados},
            {("maestros.variedad", self.variedad.pk), ("inventario.semilla", self.variedad.semilla.pk)},
        )
        self.assertEqual(RegistroAuditoria.objects.filter(accion="reactivacion_variedad").count(), 1)

    def test_post_e_un_error_no_deja_registro(self):
        """D-22: no queda un registro de una reactivación que no se hizo."""
        self.cultivo.estado_cultivo = "inactivo"
        self.cultivo.save()
        error_de(self.reactivar)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="reactivacion_variedad").exists())
