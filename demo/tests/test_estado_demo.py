# Pruebas del comando ``estado_demo`` (DAT-02, paso 4): solo lectura, detrás del mismo doble candado que ``cargar_demo`` (sin la condición de
# «no hay cuentas»), y sin fallar por lo que falte. Los secretos de las pruebas se inventan en cada corrida.

import os
import secrets
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from core.models import RegistroAuditoria, Usuario
from demo import candado, carga
from inventario.tests.fabricas import ConDatosDeInventario
from iot.models import SistemaIoT
from produccion.models import Lote

BASE = "ejemplo"


class _ConCandadoAbierto:
    """Mixin: deja ``INFOPONIA_DEMO=1`` y la base «infoponia_demo» (sustituida) mientras dura cada prueba."""

    def setUp(self):
        super().setUp()
        entorno = patch.dict(os.environ, {candado.VARIABLE_DEL_CANDADO: "1"})
        base = patch.object(candado, "nombre_de_la_base", return_value=candado.BASE_DE_LA_DEMO)
        for parche in (entorno, base):
            parche.start()
            self.addCleanup(parche.stop)

    def _estado(self):
        salida = StringIO()
        call_command("estado_demo", stdout=salida)
        return salida.getvalue()


class EstadoDemoConCandadoCerradoTests(TestCase):
    """DAT-02 paso 4: el comando de solo lectura también está detrás del candado."""

    def test_dat_02_sin_infoponia_demo_se_niega(self):
        with patch.dict(os.environ, {candado.VARIABLE_DEL_CANDADO: "0"}), patch.object(candado, "nombre_de_la_base", return_value=candado.BASE_DE_LA_DEMO):
            with self.assertRaises(CommandError):
                call_command("estado_demo", stdout=StringIO())

    def test_dat_02_con_otra_base_se_niega(self):
        with patch.dict(os.environ, {candado.VARIABLE_DEL_CANDADO: "1"}), patch.object(candado, "nombre_de_la_base", return_value="infoponia"):
            with self.assertRaises(CommandError):
                call_command("estado_demo", stdout=StringIO())


class EstadoDemoSinCargaTests(_ConCandadoAbierto, TestCase):
    """DAT-02 paso 4: con la base vacía, el informe no falla y dice qué falta."""

    def test_dat_02_con_la_base_vacia_informa_lo_que_falta_sin_fallar(self):
        """No exige los secretos ni que la base esté vacía de cuentas: informa que no hay nada cargado."""
        salida = self._estado()
        self.assertIn("[falta] LN-1", salida)
        self.assertIn("[falta] S-1", salida)
        self.assertIn("[falta] Sistema IoT de Norte", salida)
        self.assertIn("(ninguna: la carga todavía no se hizo)", salida)


class EstadoDemoConCargaTests(_ConCandadoAbierto, PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """DAT-02 paso 4: con la carga hecha, todas las escenas están listas y las piezas dicen «está» o «no está»."""

    @classmethod
    def setUpTestData(cls):
        cls.hoy = timezone.localdate()
        cls.contrasena = secrets.token_urlsafe(12)
        carga.cargar(carga.Contexto(hoy=cls.hoy, base=BASE, contrasena=cls.contrasena))

    def test_dat_02_las_fechas_del_guion(self):
        """HOY, HOY+1 (paso 40), HOY+3 (fungicida) y HOY+8 (primera entrega de S-2)."""
        salida = self._estado()
        for etiqueta, dias in (("HOY", 0), ("HOY+1", 1), ("HOY+3", 3), ("HOY+8", 8)):
            self.assertIn(f"{etiqueta}: {self.hoy + timedelta(days=dias):%d/%m/%Y}", salida)

    def test_dat_02_las_seis_escenas_estan_listas_despues_de_la_carga(self):
        """LN-1 con su stock libre, LN-2 en Crecimiento, S-1 con la cosecha «a realizar», S-2 sin reservas, el IoT y la Solución A bajo el mínimo."""
        salida = self._estado()
        self.assertEqual(salida.count("[lista]"), 6, salida)
        self.assertNotIn("[falta]", salida)
        self.assertIn("«a realizar»", salida)
        self.assertIn("12 contra un mínimo de 20", salida)

    def test_dat_02_ln1_muestra_su_stock_libre_descontadas_las_reservas_de_s1(self):
        """S-1 reserva 60 + 60 de LN-1: quedan 180 libres de 300."""
        salida = self._estado()
        self.assertIn("180 plantas libres de 300", salida)

    def test_dat_02_las_piezas_estan_o_no_estan(self):
        """PRD-05, CMP-07 y COM-08a están; CON-04d todavía no: «no está (la resolución sí)»."""
        salida = self._estado()
        self.assertIn("Lote existente (PRD-05): está", salida)
        self.assertIn("Pedido automático (CMP-07): está", salida)
        self.assertIn("Cobro de suministro (COM-08a): está", salida)
        self.assertIn("Asiento de la multa (CON-04d): no está (la resolución sí)", salida)

    def test_dat_02_una_pieza_ausente_se_informa_sin_fallar(self):
        """Si faltaran los pasos diarios o PRD-05, el informe lo dice y sigue."""
        with patch("demo.estado.pasos_diarios", return_value=[]), patch("demo.estado._lote_existente", return_value=False):
            salida = self._estado()
        self.assertIn("Lote existente (PRD-05): no está", salida)
        self.assertIn("Pedido automático (CMP-07): no está", salida)
        self.assertIn("Cobro de suministro (COM-08a): no está", salida)

    def test_dat_02_el_asiento_de_la_multa_se_reconoce_cuando_la_resolucion_llama_al_servicio_de_asientos(self):
        """CON-04d: cuando ``resoluciones`` use ``registrar_asiento_automatico``, el informe dice «está»."""
        with patch("demo.estado.inspect.getsource", return_value="... registrar_asiento_automatico(...) ..."):
            self.assertIn("Asiento de la multa (CON-04d): está", self._estado())

    def test_dat_02_las_cuentas_con_rol_y_correo(self):
        salida = self._estado()
        self.assertIn("Gerente: ejemplo+gerente1@gmail.com", salida)
        self.assertIn("Contador: ejemplo+contador1@gmail.com", salida)
        self.assertEqual(sum(1 for l in salida.splitlines() if "@gmail.com" in l), 10)

    def test_dat_02_nunca_imprime_la_contrasena_ni_el_token(self):
        """Decisión de la demo, punto 6: ni la contraseña ni el token (ni su resumen) aparecen; solo que el token fue generado."""
        salida = self._estado()
        sistema = SistemaIoT.objects.get(invernadero__nombre_invernadero="Norte")
        self.assertNotIn(self.contrasena, salida)
        self.assertNotIn(sistema.token_resumen, salida)
        self.assertIn("token generado el", salida)

    def test_dat_02_es_de_solo_lectura(self):
        """No crea ni cambia nada: mismas cuentas, mismos registros de auditoría y mismos lotes antes y después."""
        antes = (Usuario.objects.count(), RegistroAuditoria.objects.count(), Lote.objects.count())
        self._estado()
        self._estado()
        self.assertEqual((Usuario.objects.count(), RegistroAuditoria.objects.count(), Lote.objects.count()), antes)
