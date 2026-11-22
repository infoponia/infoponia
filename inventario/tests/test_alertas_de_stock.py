# Pruebas de `reevaluar_alertas_del_insumo` (INV-02, paso 1; docs/patrones/stock.md, sección 4; docs/api/alertas.md; D-41).
#
# Se prueba (inventario/servicios/alertas_de_stock.py), tomado del módulo dentro de cada prueba:
#   reevaluar_alertas_del_insumo(iin_id, hoy=None) -> Reevaluacion(creadas, resueltas)   (listas de Alerta)
# Hace tres cosas idempotentes: asegura o resuelve «stock inconsistente» y «bajo el mínimo» (clave ``insumo:<id>``) y resuelve las de
# vencimiento (clave ``lote:<id>``) de los lotes agotados. Las de vencimiento las CREA solo CMP-REV-VNC.

from datetime import date, timedelta

from django.db import transaction
from django.test import TestCase

from inventario.extensiones import OrdenQueReserva
from inventario.models import InsumoInvernadero, LoteInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    faltante,
    insumo,
    lote,
    perezoso,
    reservas_de_prueba,
)
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_alerta, crear_invernadero

alertas_de_stock = perezoso("inventario.servicios.alertas_de_stock")
HOY = date(2026, 12, 10)
INCONSISTENTE = "inv_stock_inconsistente"
BAJO_MINIMO = "inv_insumo_bajo_minimo"
POR_VENCER = "inv_insumo_por_vencer"
VENCIDO = "inv_insumo_vencido"


class AlertasDeStockTests(ConDatosDeInventario, TestCase):
    """Un solo punto de reevaluación (sección 4 de docs/patrones/stock.md)."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Norte", agronomo=self.agronomo)
        self.insumo = insumo("Nutriente A", unidad="l", controla_vencimiento=True)
        self.iin = existencia(self.insumo, self.invernadero, minimo=20)

    def reevaluar(self, iin=None):
        with transaction.atomic():
            return alertas_de_stock.reevaluar_alertas_del_insumo((iin or self.iin).pk, HOY)

    def activas(self, tipo, clave):
        return Alerta.objects.filter(
            invernadero=self.invernadero, tipo_alerta=tipo, clave_estado=clave, estado_alerta="activa"
        )

    # ---- bajo el mínimo ----

    def test_regla_bajo_minimo_crea_la_alerta_si_esta_bajo_el_minimo(self):
        """Sección 4: la asegura si libre + tránsito < mínimo y el estado es activo."""
        lote(self.iin, 5, vence=HOY + timedelta(days=30))
        r = self.reevaluar()
        self.assertEqual([a.tipo_alerta for a in r.creadas], [BAJO_MINIMO])
        self.assertEqual(self.activas(BAJO_MINIMO, f"insumo:{self.iin.pk}").count(), 1)

    def test_regla_bajo_minimo_no_duplica_la_alerta_al_reevaluar_dos_veces(self):
        """Idempotente: la segunda vez no crea ni resuelve nada."""
        lote(self.iin, 5, vence=HOY + timedelta(days=30))
        self.reevaluar()
        r = self.reevaluar()
        self.assertEqual((r.creadas, r.resueltas), ([], []))
        self.assertEqual(self.activas(BAJO_MINIMO, f"insumo:{self.iin.pk}").count(), 1)

    def test_regla_bajo_minimo_resuelve_la_alerta_cuando_deja_de_estar_bajo_el_minimo(self):
        """Sección 4: la resuelve si no está bajo el mínimo."""
        lote(self.iin, 5, vence=HOY + timedelta(days=30))
        self.reevaluar()
        lote(self.iin, 30, vence=HOY + timedelta(days=30))
        r = self.reevaluar()
        self.assertEqual([a.tipo_alerta for a in r.resueltas], [BAJO_MINIMO])
        self.assertEqual(self.activas(BAJO_MINIMO, f"insumo:{self.iin.pk}").count(), 0)

    def test_regla_bajo_minimo_con_minimo_cero_no_alerta(self):
        """Mínimo 0 no alerta."""
        iin = existencia(insumo("Sin min", unidad="l"), self.invernadero, minimo=0)
        self.assertEqual(self.reevaluar(iin).creadas, [])

    def test_regla_bajo_minimo_un_insumo_invernadero_inactivo_resuelve_la_alerta(self):
        """Sección 4: si el `InsumoInvernadero` pasó a inactivo, la resuelve y no la crea."""
        lote(self.iin, 5, vence=HOY + timedelta(days=30))
        self.reevaluar()
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(estado_insumo_invernadero="inactivo")
        r = self.reevaluar()
        self.assertEqual([a.tipo_alerta for a in r.resueltas], [BAJO_MINIMO])
        self.assertEqual(r.creadas, [])

    def test_regla_bajo_minimo_un_insumo_del_catalogo_inactivo_resuelve_la_alerta(self):
        """Sección 4: caso de la semilla dada de baja con su variedad, que conserva la existencia activa."""
        lote(self.iin, 5, vence=HOY + timedelta(days=30))
        self.reevaluar()
        self.insumo.estado_insumo = "inactivo"
        self.insumo.save(update_fields=["estado_insumo"])
        r = self.reevaluar()
        self.assertEqual([a.tipo_alerta for a in r.resueltas], [BAJO_MINIMO])
        self.assertEqual(r.creadas, [])

    def test_regla_bajo_minimo_un_invernadero_inactivo_no_crea_alertas(self):
        """Post e de PROD-BAJ-INV: el invernadero inactivo deja de generar alertas."""
        lote(self.iin, 5, vence=HOY + timedelta(days=30))
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save(update_fields=["estado_invernadero"])
        self.assertEqual(self.reevaluar().creadas, [])
        self.assertEqual(Alerta.objects.filter(tipo_alerta=BAJO_MINIMO).count(), 0)

    def test_regla_bajo_minimo_va_al_agronomo_del_invernadero(self):
        """D-41: destinatario `AGRONOMO_O_GERENTE`, con Agrónomo activo va a él."""
        lote(self.iin, 5, vence=HOY + timedelta(days=30))
        alerta = self.reevaluar().creadas[0]
        self.assertEqual(alerta.agronomo_id, self.agronomo.pk)
        self.assertFalse(alerta.para_gerente)

    def test_regla_bajo_minimo_sin_agronomo_va_al_gerente(self):
        """D-41 / MD-61: sin Agrónomo activo, la alerta va al Gerente."""
        sin = crear_invernadero("Sin agronomo")
        iin = existencia(insumo("Otro", unidad="l"), sin, minimo=20)
        alerta = self.reevaluar(iin).creadas[0]
        self.assertTrue(alerta.para_gerente)
        self.assertIsNone(alerta.agronomo)

    # ---- stock inconsistente ----

    def test_regla_inconsistente_crea_la_alerta_si_el_stock_vigente_no_cubre_las_reservas(self):
        """Sección 4: la asegura si vigente < reservado."""
        lote(self.iin, 31, vence=HOY + timedelta(days=30))
        with reservas_de_prueba(reservado={self.iin.pk: "40"}):
            r = self.reevaluar()
        self.assertIn(INCONSISTENTE, [a.tipo_alerta for a in r.creadas])
        self.assertEqual(self.activas(INCONSISTENTE, f"insumo:{self.iin.pk}").count(), 1)

    def test_regla_inconsistente_la_descripcion_nombra_el_insumo_y_las_ordenes_sin_cobertura(self):
        """Sección 4: la descripción identifica el insumo, el stock y las órdenes sin cobertura."""
        lote(self.iin, 1, vence=HOY + timedelta(days=30))
        orden = OrdenQueReserva(7, "Siembra de lechuga", 5, HOY, "/o/7")
        with reservas_de_prueba(reservado={self.iin.pk: "5"}, ordenes={self.iin.pk: [orden]}):
            alerta = [a for a in self.reevaluar().creadas if a.tipo_alerta == INCONSISTENTE][0]
        self.assertIn("Nutriente A", alerta.descripcion_alerta)
        self.assertIn("Siembra de lechuga", alerta.descripcion_alerta)

    def test_regla_inconsistente_con_faltante_sin_lote_crea_la_alerta(self):
        """Un faltante deja el stock vigente negativo."""
        faltante(self.iin, 2)
        self.assertIn(INCONSISTENTE, [a.tipo_alerta for a in self.reevaluar().creadas])

    def test_regla_inconsistente_la_resuelve_cuando_el_stock_vuelve_a_cubrir(self):
        """Postcondición h de CMP-AJT-STK: se resuelve con su fecha cuando vigente >= 0 y >= reservado."""
        falta = faltante(self.iin, 2)
        self.reevaluar()
        LoteInsumo.objects.filter(pk=falta.pk).update(cantidad_disponible=0)
        r = self.reevaluar()
        self.assertIn(INCONSISTENTE, [a.tipo_alerta for a in r.resueltas])
        self.assertIsNotNone(r.resueltas[0].fecha_resolucion)

    def test_regla_inconsistente_no_duplica_la_alerta(self):
        """Idempotente."""
        faltante(self.iin, 2)
        self.reevaluar()
        self.reevaluar()
        self.assertEqual(self.activas(INCONSISTENTE, f"insumo:{self.iin.pk}").count(), 1)

    # ---- vencimiento ----

    def test_regla_vencimiento_resuelve_las_alertas_de_un_lote_agotado(self):
        """Tercera cosa de la sección 4: las de por vencer y vencido de los lotes en 0 pasan a resueltas."""
        agotado = lote(self.iin, 0, vence=HOY - timedelta(days=1), ingresada=5)
        clave = f"lote:{agotado.pk}"
        por = crear_alerta(self.invernadero, POR_VENCER, para_gerente=False, agronomo=self.agronomo, clave_estado=clave)
        venc = crear_alerta(self.invernadero, VENCIDO, para_gerente=False, agronomo=self.agronomo, clave_estado=clave)
        r = self.reevaluar()
        self.assertEqual({a.pk for a in r.resueltas if a.tipo_alerta in (POR_VENCER, VENCIDO)}, {por.pk, venc.pk})

    def test_regla_vencimiento_no_resuelve_las_de_un_lote_con_stock(self):
        """Un lote con cantidad disponible mayor que cero conserva su alerta."""
        vivo = lote(self.iin, 3, vence=HOY - timedelta(days=1))
        crear_alerta(
            self.invernadero, VENCIDO, para_gerente=False, agronomo=self.agronomo, clave_estado=f"lote:{vivo.pk}"
        )
        r = self.reevaluar()
        self.assertNotIn(VENCIDO, [a.tipo_alerta for a in r.resueltas])
        self.assertEqual(self.activas(VENCIDO, f"lote:{vivo.pk}").count(), 1)

    def test_regla_vencimiento_la_reevaluacion_nunca_crea_alertas_de_vencimiento(self):
        """Sección 4: las alertas de vencimiento las crea solo CMP-REV-VNC."""
        lote(self.iin, 50, vence=HOY - timedelta(days=3))
        lote(self.iin, 50, vence=HOY + timedelta(days=3))
        tipos = [a.tipo_alerta for a in self.reevaluar().creadas]
        self.assertNotIn(VENCIDO, tipos)
        self.assertNotIn(POR_VENCER, tipos)

    def test_regla_vencimiento_la_reevaluacion_no_toca_las_de_otro_insumo(self):
        """El alcance es el `InsumoInvernadero` indicado."""
        otro = existencia(insumo("Otro", unidad="l", controla_vencimiento=True), self.invernadero)
        agotado = lote(otro, 0, vence=HOY - timedelta(days=1), ingresada=5)
        crear_alerta(
            self.invernadero, VENCIDO, para_gerente=False, agronomo=self.agronomo, clave_estado=f"lote:{agotado.pk}"
        )
        self.assertEqual([a for a in self.reevaluar().resueltas if a.tipo_alerta == VENCIDO], [])
