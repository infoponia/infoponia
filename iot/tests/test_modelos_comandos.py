# Pruebas del modelo `RegistroComando` (IOT-05, paso 1; docs/modelo/iot.md, «RegistroComando»; MD-110) y de lo que la tarea suma fuera de la app: el valor `comando`
# de `Bitacora.TipoEvento` y las tres acciones de auditoría. Las restricciones de `Comando` que ya existían (un pendiente por actuador) siguen: se prueban acá en
# presencia del registro, saltándose los servicios.

from datetime import date, time

from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import ACCIONES_DE_NEGOCIO, RegistroAuditoria
from iot.models import Comando, RegistroComando
from iot.tests import fabricas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero
from produccion.models import Bitacora


class RegistroComandoModeloTests(fabricas.ConCatalogoIot, TestCase):
    """MD-110: el registro de bitácora de un comando."""

    def setUp(self):
        self.agronomo = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.agronomo)
        self.sistema = fabricas.sistema(self.norte)
        self.actuador = fabricas.actuador(self.sistema, fabricas.tipo_actuador())
        self.encender = self.actuador.tipo_actuador.acciones.order_by("id").first()
        self.comando = fabricas.comando(self.actuador, self.encender)

    def registro(self, **extra):
        """Un registro de la prueba; ``extra`` pisa campos."""
        datos = {"comando": self.comando, "resultado": "emitido"}
        return RegistroComando.objects.create(**(datos | extra))

    def test_md110_crear_un_registro_le_pone_el_tipo_comando(self):
        """MD-110: ``tipo_evento = comando`` aunque quien lo crea no lo diga, y aunque diga otro."""
        self.assertEqual(self.registro().tipo_evento, Bitacora.TipoEvento.COMANDO)
        self.assertEqual(self.registro(tipo_evento="merma").tipo_evento, "comando")

    def test_md110_el_invernadero_es_el_del_sistema_del_actuador(self):
        """MD-110: el invernadero del registro es el del sistema IoT del actuador del comando."""
        self.assertEqual(self.registro().invernadero_id, self.norte.pk)

    def test_md110_el_registro_no_tiene_lote_ni_etapa(self):
        """MD-110: sin lote (y, por ser del IoT, sin etapa)."""
        registro = self.registro()
        self.assertIsNone(registro.lote_id)
        self.assertIsNone(registro.etapa_id)

    def test_md110_el_registro_es_una_fila_de_la_bitacora_del_invernadero(self):
        """MD-110: aparece en ``Bitacora`` y en el documento de origen de tipo «bitácora» (D-52)."""
        registro = self.registro()
        padre = Bitacora.objects.get(pk=registro.pk)
        self.assertEqual((padre.tipo_evento, padre.invernadero_id, padre.tipo), ("comando", self.norte.pk, "bitacora"))

    def test_md110_sin_fecha_usa_la_actual_y_con_fecha_respeta_la_dada(self):
        """MD-110: los servicios pasan la fecha y la hora de su ``ahora``; si no, se usan las actuales."""
        self.assertIsNotNone(self.registro().fecha_bitacora)
        dado = self.registro(fecha_bitacora=date(2026, 11, 20), hora_bitacora=time(14, 5))
        self.assertEqual((dado.fecha_bitacora, dado.hora_bitacora), (date(2026, 11, 20), time(14, 5)))

    def test_md110_el_numero_de_intento_y_el_responsable_son_optativos(self):
        """MD-110: ``numero_intento`` nulo salvo en un intento fallido; ``responsable`` nulo si lo hizo InfoPonia o el nodo."""
        sin = self.registro()
        self.assertEqual((sin.numero_intento, sin.responsable_id), (None, None))
        con = self.registro(resultado="intento_fallido", numero_intento=2, responsable=self.agronomo)
        self.assertEqual((con.numero_intento, con.responsable_id), (2, self.agronomo.pk))

    def test_md110_el_resultado_es_uno_de_los_seis(self):
        """MD-110: la base rechaza un resultado fuera de la lista."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.registro(resultado="inventado")
        for valor in ("emitido", "intento_fallido", "ejecutado", "fallido", "rechazado", "cancelado"):
            self.registro(resultado=valor)

    def test_md105_los_registros_no_cambian_el_pendiente_unico_por_actuador(self):
        """MD-105 sigue: con registros de por medio, un segundo pendiente sobre el mismo actuador choca; un comando resuelto, no."""
        self.registro()
        apagar = self.actuador.tipo_actuador.acciones.order_by("id").last()
        with self.assertRaises(IntegrityError), transaction.atomic():
            fabricas.comando(self.actuador, apagar)
        fabricas.comando(self.actuador, apagar, estado="ejecutado")
        self.assertEqual(Comando.objects.filter(actuador=self.actuador, estado_comando="pendiente").count(), 1)

    def test_md110_el_comando_con_registros_no_se_borra(self):
        """Las FK son ``PROTECT`` (convención de la ficha): un comando con registros no se borra."""
        from django.db.models.deletion import ProtectedError

        self.registro()
        with self.assertRaises(ProtectedError):
            self.comando.delete()


class AccionesDeAuditoriaDeComandosTests(TestCase):
    """Las tres acciones que suma IOT-05 (D-36): están en los choices y clasificadas como de negocio."""

    def test_d36_las_tres_acciones_existen_y_son_de_negocio(self):
        """IOT-05, «Límites»: ``emision_comando``, ``cancelacion_comando`` y ``resolucion_comando_iot``."""
        for codigo in ("emision_comando", "cancelacion_comando", "resolucion_comando_iot"):
            self.assertIn(codigo, RegistroAuditoria.Accion.values)
            self.assertIn(RegistroAuditoria.Accion(codigo), ACCIONES_DE_NEGOCIO)

    def test_bitacora_acepta_el_tipo_comando_en_sus_opciones(self):
        """IOT-05, «Límites»: ``Bitacora.TipoEvento`` suma «Comando»."""
        self.assertEqual(Bitacora.TipoEvento("comando").label, "Comando")
