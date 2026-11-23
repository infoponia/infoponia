# Pruebas del comando `python manage.py revision_iot` (IOT-04, paso 4; D-71 punto 1; docs/casos_de_uso/iot/entregar_informacion.md, «La revisión periódica», «Dónde y cómo se
# corre»). Se escribieron ANTES que el comando (`.claude/rules/pruebas.md`). El comando no tiene lógica propia: valida las opciones, llama a ``revision.revisar(ahora)`` por
# el módulo, imprime y, si algún sistema falló, termina con código 1 (``CommandError``), como `proceso_diario` (D-56).
#
# Salida (decidida acá, a partir del ejemplo del extracto): una línea con la hora usada; una por sistema, «<invernadero>: N alertas generadas · N resueltas · N resúmenes ·
# N fotoperíodos · N lecturas borradas» (en singular cuando es 1: «1 alerta generada», «1 resuelta», «1 resumen», «1 fotoperíodo», «1 lectura borrada») o
# «<invernadero>: FALLÓ: <error>»; «No hay sistemas IoT activos.» si no hay; y una de correos, «Correos: N enviados · N fallidos · N pendientes sin servidor de correo»
# (también en singular). Ninguna prueba depende de la hora del día.

from datetime import datetime, timedelta
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import Hardware, NodoCentral
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

revision = perezoso("iot.servicios.revision")
alertas_iot = perezoso("iot.servicios.alertas_iot")

LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")
AHORA = datetime(2026, 11, 23, 12, 0, tzinfo=LOCAL)
AHORA_TEXTO = "2026-11-23T12:00"
RESUMEN_VACIO = "0 alertas generadas · 0 resueltas · 0 resúmenes · 0 fotoperíodos · 0 lecturas borradas"
CORREOS_VACIO = "Correos: 0 enviados · 0 fallidos · 0 pendientes sin servidor de correo"


class ComandoRevisionIotTests(fabricas.ConCatalogoIot, TestCase):
    """`revision_iot`: con y sin `--ahora`, `--cada`, la salida y el código de salida."""

    def setUp(self):
        cache.clear()
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.temp = fabricas.sensor(self.sistema, "norte/sectorA/temperatura")

    def correr(self, *argumentos):
        """Corre el comando y devuelve su salida (las líneas, sin el salto final)."""
        salida = StringIO()
        call_command("revision_iot", *argumentos, stdout=salida)
        return salida.getvalue().splitlines()

    # ---- con y sin --ahora ----

    def test_regla_comando_con_ahora_usa_esa_hora_local_e_imprime_las_lineas(self):
        """«Dónde y cómo se corre»: `--ahora AAAA-MM-DDTHH:MM` es hora local. Salida: la hora usada, una línea por sistema y la de correos."""
        lineas = self.correr("--ahora", AHORA_TEXTO)
        self.assertIn("23/11/2026 12:00", lineas[0])
        self.assertEqual(lineas[1], f"Norte: {RESUMEN_VACIO}")
        self.assertEqual(lineas[-1], CORREOS_VACIO)

    def test_regla_comando_con_ahora_la_revision_recibe_un_datetime_con_zona(self):
        """D-71 punto 2: `revisar` recibe `ahora` con zona; `--ahora` es la hora local del proyecto (12:00 locales = 15:00 UTC)."""
        with mock.patch("iot.servicios.revision.revisar", wraps=revision.revisar) as espia:
            self.correr("--ahora", AHORA_TEXTO)
        (ahora,) = espia.call_args.args
        self.assertEqual(ahora, AHORA)
        self.assertIsNotNone(ahora.utcoffset())

    def test_regla_comando_sin_ahora_corre_una_vez_con_la_hora_actual(self):
        """«Sin opciones, corre una vez» con la hora actual (con zona), leída por el comando y no por el servicio."""
        with mock.patch("iot.servicios.revision.revisar", wraps=revision.revisar) as espia:
            self.correr()
        self.assertEqual(espia.call_count, 1)
        (ahora,) = espia.call_args.args
        self.assertLess(abs(ahora - timezone.now()), timedelta(minutes=1))

    def test_regla_comando_ahora_invalido_es_un_error_y_no_corre_nada(self):
        """«Con un formato inválido, `CommandError`»: fecha imposible, formato distinto, solo la fecha o vacío. No corre ni imprime nada."""
        Hardware.objects.filter(pk=self.temp.pk).update(ultimo_mensaje_en=AHORA - timedelta(hours=1))
        for texto in ("2026-13-45T10:00", "2026-11-23 12:00", "2026-11-23", "", "mañana"):
            with self.subTest(texto=texto):
                with self.assertRaises(CommandError):
                    self.correr("--ahora", texto)
        self.assertFalse(Alerta.objects.exists())

    # ---- la salida ----

    def test_regla_comando_la_linea_de_un_sistema_cuenta_en_singular_y_en_plural(self):
        """Salida: «Norte: 1 alerta generada · 0 resueltas · …». Un sensor sin actividad genera una alerta (advertencia: no sale correo)."""
        Hardware.objects.filter(pk=self.temp.pk).update(ultimo_mensaje_en=AHORA - timedelta(minutes=30))
        lineas = self.correr("--ahora", AHORA_TEXTO)
        self.assertEqual(lineas[1], "Norte: 1 alerta generada · 0 resueltas · 0 resúmenes · 0 fotoperíodos · 0 lecturas borradas")

    def test_regla_comando_sin_sistemas_activos_lo_dice(self):
        """«Sin sistemas, "No hay sistemas IoT activos"»."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        lineas = self.correr("--ahora", AHORA_TEXTO)
        self.assertIn("No hay sistemas IoT activos.", lineas)

    def test_regla_comando_la_linea_de_correos_dice_los_pendientes_sin_servidor(self):
        """«Correos» de «La revisión periódica»: sin servidor de correo (en las pruebas arranca apagado) la salida lo informa: «1 pendiente sin servidor de correo»."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=AHORA - timedelta(minutes=10))
        lineas = self.correr("--ahora", AHORA_TEXTO)
        self.assertEqual(lineas[-1], "Correos: 0 enviados · 0 fallidos · 1 pendiente sin servidor de correo")

    def test_regla_comando_la_linea_de_correos_cuenta_los_enviados(self):
        """«Correos: 1 enviado · 0 fallidos · 0 pendientes sin servidor de correo» cuando salió el de la alerta crítica."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=AHORA - timedelta(minutes=10))
        with self.settings(CORREO_CONFIGURADO=True), mock.patch("core.correo.enviar_correo", return_value=True):
            lineas = self.correr("--ahora", AHORA_TEXTO)
        self.assertEqual(lineas[-1], "Correos: 1 enviado · 0 fallidos · 0 pendientes sin servidor de correo")

    # ---- código de salida ----

    def test_regla_comando_si_un_sistema_falla_lo_informa_y_termina_con_error(self):
        """«Código de salida: 1 si algún sistema falló; 0 si no»: `CommandError` (como `proceso_diario`); la línea del sistema dice «FALLÓ: …» y se imprimió igual."""
        Hardware.objects.filter(pk=self.temp.pk).update(ultimo_mensaje_en=AHORA - timedelta(minutes=30))
        salida = StringIO()
        with mock.patch("iot.servicios.alertas_iot.asegurar_alerta_iot", side_effect=RuntimeError("falla de prueba")):
            with self.assertLogs("iot.revision", level="ERROR"):
                with self.assertRaises(CommandError):
                    call_command("revision_iot", "--ahora", AHORA_TEXTO, stdout=salida)
        self.assertIn("Norte: FALLÓ: RuntimeError: falla de prueba", salida.getvalue())

    def test_regla_comando_sin_fallos_termina_sin_error(self):
        """Código de salida 0: no lanza `CommandError`."""
        self.correr("--ahora", AHORA_TEXTO)

    # ---- --cada ----

    def test_regla_comando_cada_repite_hasta_ctrl_c_y_corta_limpio(self):
        """«`--cada N`: repite cada N segundos hasta Ctrl+C, que corta limpio y con código 0»: con `time.sleep` reemplazado, que a la segunda vuelta lanza
        `KeyboardInterrupt`, corre dos veces, duerme 60 segundos y termina sin error."""
        with mock.patch("iot.servicios.revision.revisar", wraps=revision.revisar) as espia:
            with mock.patch("iot.management.commands.revision_iot.time.sleep", side_effect=[None, KeyboardInterrupt]) as dormir:
                self.correr("--cada", "60")
        self.assertEqual(espia.call_count, 2)
        self.assertEqual([llamada.args for llamada in dormir.call_args_list], [(60,), (60,)])

    def test_regla_comando_cada_menor_que_10_segundos_es_un_error(self):
        """«`--cada N`: N ≥ 10»: con 9 (o con algo que no es un número) es `CommandError` y no corre."""
        with mock.patch("iot.servicios.revision.revisar") as espia:
            for valor in ("9", "0", "-5", "abc"):
                with self.subTest(valor=valor):
                    with self.assertRaises(CommandError):
                        self.correr("--cada", valor)
        espia.assert_not_called()
