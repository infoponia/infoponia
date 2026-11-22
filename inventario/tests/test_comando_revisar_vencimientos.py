# Pruebas del comando ``revisar_vencimientos`` (CMP-REV-VNC, INV-02, paso 7; docs/casos_de_uso/inventario/vencimientos.md, «Cómo se aplica en la ronda»;
# D-56): ``inventario/management/commands/revisar_vencimientos.py``. El comando NO tiene lógica: valida ``--fecha``, llama a
# ``inventario.servicios.vencimientos.revisar_vencimientos(hoy=...)`` (llamado con el argumento ``hoy``; ``None`` sin ``--fecha``), imprime el resumen y,
# si hubo fallas, termina con código distinto de cero (``CommandError``: Django la convierte en ``exit(1)`` al correr ``manage.py``), para que
# Render marque la corrida como fallida. Debe terminar solo (nada interactivo).

from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from core.models import RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote, perezoso, tipo_de_insumo
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

vencimientos = perezoso("inventario.servicios.vencimientos")
HOY = date(2026, 12, 10)


def correr(*args):
    """Corre el comando y devuelve lo que imprimió."""
    salida = StringIO()
    call_command("revisar_vencimientos", *args, stdout=salida)
    return salida.getvalue()


def resultado(revisados=0, creadas=(), resueltas=(), fallas=()):
    """Un ``Resultado`` falso de ``revisar_vencimientos``."""
    return vencimientos.Resultado(revisados, list(creadas), list(resueltas), list(fallas))


class ComandoRevisarVencimientosTests(SimpleTestCase):
    """El comando solo orquesta: se prueba con el servicio simulado (sin base de datos)."""

    def test_sin_fecha_llama_al_servicio_sin_hoy_para_que_use_la_fecha_del_invernadero(self):
        """Regla 1: sin ``--fecha``, el servicio usa la fecha de ``America/Argentina/Buenos_Aires``: el comando no la calcula."""
        with mock.patch("inventario.servicios.vencimientos.revisar_vencimientos", return_value=resultado(2)) as servicio:
            correr()
        servicio.assert_called_once_with(hoy=None)

    def test_con_fecha_la_pasa_como_date_al_servicio(self):
        """``--fecha AAAA-MM-DD`` solo sirve para correrlo a mano en el servidor: simula ese día."""
        with mock.patch("inventario.servicios.vencimientos.revisar_vencimientos", return_value=resultado(1)) as servicio:
            correr("--fecha", "2026-12-15")
        servicio.assert_called_once_with(hoy=date(2026, 12, 15))

    def test_imprime_cuantos_invernaderos_reviso_y_cuantas_alertas_creo_y_resolvio(self):
        """Resumen en pantalla: invernaderos revisados, alertas creadas y resueltas."""
        with mock.patch(
            "inventario.servicios.vencimientos.revisar_vencimientos",
            return_value=resultado(3, creadas=[object(), object()], resueltas=[object()]),
        ):
            salida = correr()
        self.assertIn("Invernaderos revisados: 3", salida)
        self.assertIn("Alertas creadas: 2", salida)
        self.assertIn("Alertas resueltas: 1", salida)

    def test_una_fecha_con_formato_invalido_es_un_error_de_uso_y_no_corre_nada(self):
        """Mismo criterio que ``proceso_diario``: AAAA-MM-DD estricto; un error de uso no corre nada."""
        for mala in ("15/12/2026", "2026-13-01", "2026-1-5", "mañana"):
            with self.subTest(fecha=mala), mock.patch("inventario.servicios.vencimientos.revisar_vencimientos") as servicio:
                with self.assertRaises(CommandError) as contexto:
                    correr("--fecha", mala)
                self.assertIn("AAAA-MM-DD", str(contexto.exception))
                servicio.assert_not_called()

    def test_con_fallas_termina_con_codigo_distinto_de_cero_e_informa_cual_fallo(self):
        """Código de salida distinto de cero si hubo una falla (para que Render la marque), con el invernadero y el error; las demás se revisaron."""
        falla = (7, RuntimeError("falla simulada"))
        with mock.patch("inventario.servicios.vencimientos.revisar_vencimientos", return_value=resultado(2, fallas=[falla])):
            salida = StringIO()
            with self.assertRaises(CommandError) as contexto:
                call_command("revisar_vencimientos", stdout=salida)
        self.assertIn("falla simulada", str(contexto.exception) + salida.getvalue())
        self.assertIn("7", str(contexto.exception) + salida.getvalue())
        self.assertIn("Invernaderos revisados: 2", salida.getvalue())

    def test_sin_fallas_no_levanta_error(self):
        """Código de salida 0 cuando todo salió bien."""
        with mock.patch("inventario.servicios.vencimientos.revisar_vencimientos", return_value=resultado(1)):
            correr()


class ComandoRevisarVencimientosConBaseTests(ConDatosDeInventario, TestCase):
    """El comando de punta a punta, con el servicio real."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Norte", agronomo=self.agronomo)
        self.iin = existencia(insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l", controla_vencimiento=True), self.invernadero)

    def test_con_fecha_genera_las_alertas_que_corresponden_a_ese_dia(self):
        """``--fecha`` simula el paso del tiempo: un lote que vence dentro de 5 días genera «por vencer»; con otra fecha, «vencido»."""
        lote(self.iin, 5, vence=HOY + timedelta(days=5))
        salida = correr("--fecha", HOY.isoformat())
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_insumo_por_vencer").count(), 1)
        self.assertIn("Alertas creadas: 1", salida)
        correr("--fecha", (HOY + timedelta(days=6)).isoformat())
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_insumo_vencido", estado_alerta="activa").count(), 1)

    def test_correrlo_de_nuevo_no_duplica_nada(self):
        """Idempotente (regla 1): la segunda corrida informa 0 alertas creadas."""
        lote(self.iin, 5, vence=HOY - timedelta(days=1))
        correr("--fecha", HOY.isoformat())
        antes = (Alerta.objects.count(), RegistroAuditoria.objects.count())
        salida = correr("--fecha", HOY.isoformat())
        self.assertEqual((Alerta.objects.count(), RegistroAuditoria.objects.count()), antes)
        self.assertIn("Alertas creadas: 0", salida)

    def test_una_falla_real_en_un_invernadero_termina_con_error_pero_revisa_los_demas(self):
        """Falla simulada dentro del servicio real: el comando termina con ``CommandError`` y el otro invernadero igual se revisó."""
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
            with self.assertRaises(CommandError):
                correr("--fecha", HOY.isoformat())
        self.assertEqual(Alerta.objects.filter(invernadero=sur, tipo_alerta="inv_insumo_vencido").count(), 1)
        self.assertEqual(Alerta.objects.filter(invernadero=self.invernadero).count(), 0)
