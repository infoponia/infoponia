# Pruebas del paso diario ``revisar_vencimientos`` (CMP-REV-VNC, INV-02, paso 7; D-56, punto 6 y consecuencias; core/procesos.py de DIA-01).
#
# ``InventarioConfig.ready()`` registra ``registrar_paso_diario("revisar_vencimientos", "Revisar vencimientos de insumos", 10, paso)``: el paso 10 del proceso
# diario. ``paso(hoy)`` llama a la misma función que el comando propio (``revisar_vencimientos(hoy)``) y devuelve un ``ResumenDePaso`` (procesados: invernaderos
# revisados; creados y resueltos: alertas). Si la corrida tuvo fallas, el paso lanza un error AL TERMINAR (después de revisar todos los invernaderos), así
# ``proceso_diario`` lo informa como fallido y termina con código distinto de cero (D-56, punto 5). Estas pruebas usan el registro real (no un paso falso).

from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core import procesos
from core.procesos import ResumenDePaso
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote, tipo_de_insumo
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

HOY = date(2026, 12, 10)
CODIGO = "revisar_vencimientos"


def proceso_diario(*args):
    """Corre ``proceso_diario`` y devuelve lo que imprimió."""
    salida = StringIO()
    call_command("proceso_diario", *args, stdout=salida)
    return salida.getvalue()


def el_paso():
    """El paso real registrado por `inventario`."""
    return next(p for p in procesos.pasos_diarios() if p.codigo == CODIGO)


class PasoDiarioVencimientosTests(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Norte", agronomo=self.agronomo)
        self.iin = existencia(insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l", controla_vencimiento=True), self.invernadero)

    # ---- el registro ----

    def test_d56_el_paso_esta_registrado_con_el_codigo_el_nombre_y_el_orden_10(self):
        """D-56, punto 6: orden 10, «Revisar vencimientos de insumos», `inventario`."""
        paso = el_paso()
        self.assertEqual((paso.codigo, paso.nombre, paso.orden), ("revisar_vencimientos", "Revisar vencimientos de insumos", 10))

    def test_d56_el_paso_es_el_primero_del_proceso_diario(self):
        """Orden 10 es el primero reservado (T-04): ningún otro paso registrado lo antecede."""
        self.assertEqual(procesos.pasos_diarios()[0].codigo, CODIGO)

    def test_d56_registrarlo_otra_vez_no_falla_ni_duplica(self):
        """``ready()`` puede correr más de una vez: un registro idéntico es idempotente."""
        paso = el_paso()
        procesos.registrar_paso_diario(paso.codigo, paso.nombre, paso.orden, paso.funcion)
        self.assertEqual([p.codigo for p in procesos.pasos_diarios()].count(CODIGO), 1)

    def test_d56_listar_muestra_el_paso_10(self):
        """Verificación a mano 12: ``proceso_diario --listar`` muestra el paso 10."""
        self.assertIn("10 · revisar_vencimientos · Revisar vencimientos de insumos", proceso_diario("--listar"))

    # ---- la función del paso ----

    def test_el_paso_devuelve_un_resumen_con_invernaderos_revisados_y_alertas(self):
        """``ResumenDePaso(procesados=invernaderos revisados, creados=alertas creadas, resueltos=alertas resueltas)``."""
        lote(self.iin, 5, vence=HOY - timedelta(days=1))
        resumen = el_paso().funcion(HOY)
        self.assertIsInstance(resumen, ResumenDePaso)
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 1, 0))

    def test_el_paso_usa_la_misma_funcion_que_el_comando_propio(self):
        """«El comando propio y el paso usan la misma función»: ``revisar_vencimientos(hoy)``."""
        with mock.patch("inventario.servicios.vencimientos.revisar_vencimientos") as servicio:
            servicio.return_value = mock.Mock(revisados=4, creadas=[1, 2], resueltas=[3], fallas=[])
            resumen = el_paso().funcion(HOY)
        servicio.assert_called_once_with(HOY)
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (4, 2, 1))

    def test_el_paso_no_lee_la_fecha_por_su_cuenta(self):
        """D-56, punto 4: recibe ``hoy`` y nunca lee la fecha: con otro día, otro resultado."""
        lote(self.iin, 5, vence=HOY + timedelta(days=3))
        antes = el_paso().funcion(HOY - timedelta(days=40))  # todavía lejos
        despues = el_paso().funcion(HOY)  # por vencer
        self.assertEqual((antes.creados, despues.creados), (0, 1))

    def test_el_paso_con_una_falla_lanza_un_error_despues_de_revisar_todos(self):
        """D-56, punto 5: si falla un invernadero, el paso termina de revisar los demás y recién entonces lanza el error."""
        sur = crear_invernadero("Sur", agronomo=self.agronomo)
        iin_sur = existencia(insumo("Otro", tipo=self.iin.insumo.tipo_insumo, unidad="l", controla_vencimiento=True), sur)
        lote(self.iin, 5, vence=HOY - timedelta(days=1))
        lote(iin_sur, 5, vence=HOY - timedelta(days=1))
        real = api_alertas.asegurar_alerta_de_estado

        def falla_en_el_norte(invernadero_id, *args, **kwargs):
            if invernadero_id == self.invernadero.pk:
                raise RuntimeError("falla simulada")
            return real(invernadero_id, *args, **kwargs)

        with mock.patch.object(api_alertas, "asegurar_alerta_de_estado", side_effect=falla_en_el_norte):
            with self.assertRaises(Exception) as contexto:
                el_paso().funcion(HOY)
        self.assertIn("falla simulada", str(contexto.exception))
        self.assertEqual(Alerta.objects.filter(invernadero=sur).count(), 1)

    # ---- proceso_diario ----

    def test_d56_proceso_diario_solo_revisar_vencimientos_lo_corre(self):
        """Verificación a mano 12: ``proceso_diario --solo revisar_vencimientos`` corre el paso con la fecha simulada."""
        lote(self.iin, 5, vence=HOY + timedelta(days=4))
        salida = proceso_diario("--solo", CODIGO, "--fecha", HOY.isoformat())
        self.assertIn("Revisar vencimientos de insumos: procesados 1 · creados 1 · resueltos 0", salida)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_insumo_por_vencer").count(), 1)

    def test_d56_proceso_diario_sin_opciones_incluye_el_paso_y_correrlo_dos_veces_no_duplica(self):
        """El proceso completo corre el paso; idempotente."""
        lote(self.iin, 5, vence=HOY - timedelta(days=1))
        proceso_diario("--fecha", HOY.isoformat())
        proceso_diario("--fecha", HOY.isoformat())
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_insumo_vencido").count(), 1)

    def test_d56_una_falla_del_paso_hace_que_proceso_diario_termine_con_codigo_distinto_de_cero(self):
        """D-56, punto 5: ``proceso_diario`` informa cuál falló y termina con error (``CommandError`` = código de salida 1)."""
        lote(self.iin, 5, vence=HOY - timedelta(days=1))
        with mock.patch.object(api_alertas, "asegurar_alerta_de_estado", side_effect=RuntimeError("falla simulada")):
            with self.assertRaises(CommandError) as contexto:
                proceso_diario("--solo", CODIGO, "--fecha", HOY.isoformat())
        self.assertIn(CODIGO, str(contexto.exception))
