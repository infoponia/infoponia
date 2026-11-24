# Pruebas de `bitacora.registrar_evento_de_contrato` (COM-04a, paso 1; sección 11 de docs/api/produccion.md, D-69 punto 3): lo que usará
# COM-07a para dejar constancia de un incumplimiento de cláusula o de la anulación de una resolución. Núcleo: sin auditoría ni avisos.
# Fuente: docs/api/produccion.md (sección 11) y PROD-CNS-BIT (filtro «Tipo»).

from unittest import mock

from django.db import connections
from django.test import TestCase
from django.utils import timezone

from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora
from produccion.servicios import bitacora
from produccion.tests.fabricas import invernadero_con_produccion, lote_maduro

INCUMPLIMIENTO, ANULACION = "incumplimiento_de_clausula", "anulacion_de_resolucion"


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def registrar(self, tipo=INCUMPLIMIENTO, descripcion="No se entregó lo pactado", responsable=None):
        """Llama a `registrar_evento_de_contrato` para el invernadero del escenario."""
        return bitacora.registrar_evento_de_contrato(self.e.invernadero, tipo, descripcion, responsable or self.e.agronomo)


class RegistrarEventoDeContratoTests(Base):
    def test_post_los_dos_tipos_crean_el_registro_sin_lote_etapa_sectores_ni_cosecha(self):
        """Sección 11: `Bitacora` del invernadero con el tipo, la descripción, fecha y hora actuales y el responsable; sin lote, etapa,
        sectores ni cosecha."""
        for tipo in (INCUMPLIMIENTO, ANULACION):
            registro = Bitacora.objects.get(pk=self.registrar(tipo, "Detalle del hecho").pk)
            self.assertEqual(
                (registro.tipo_evento, registro.invernadero_id, registro.responsable_id, registro.fecha_bitacora, registro.descripcion_evento),
                (tipo, self.e.invernadero.pk, self.e.agronomo.pk, timezone.localdate(), "Detalle del hecho"),
            )
            self.assertEqual((registro.lote_id, registro.etapa_id, registro.cosecha_id, registro.sectores.count()), (None, None, None, 0))

    def test_regla_otro_tipo_lanza_value_error_sin_escribir(self):
        """Solo los dos tipos de la sección 11: con otro, `ValueError`."""
        for tipo in ("otro_evento", "merma", "cosecha", "inventado"):
            with self.subTest(tipo=tipo), self.assertRaises(ValueError):
                self.registrar(tipo)
        self.assertFalse(Bitacora.objects.exists())

    def test_regla_la_descripcion_va_de_1_a_500_y_se_recorta_sin_espacios_al_borde(self):
        """De 1 a 500 caracteres, recortada de espacios: vacía o de más de 500, `descripcion_invalida`; de justo 500, se acepta."""
        self.assertEqual(self.registrar(descripcion="  con espacios  ").descripcion_evento, "con espacios")
        self.assertEqual(len(self.registrar(descripcion="x" * 500).descripcion_evento), 500)
        for texto in ("", "   ", "x" * 501):
            with self.subTest(largo=len(texto)), self.assertRaises(ErrorDeProduccion) as rechazo:
                self.registrar(descripcion=texto)
            self.assertEqual(rechazo.exception.codigo, "descripcion_invalida")

    def test_regla_no_exige_que_el_invernadero_este_activo(self):
        """«Un contrato puede tener entregas de un invernadero dado de baja»: no verifica el estado del invernadero."""
        from maestros.models import Invernadero

        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero=Invernadero.Estado.INACTIVO)
        self.e.invernadero.refresh_from_db()
        self.assertEqual(self.registrar().tipo_evento, INCUMPLIMIENTO)

    def test_regla_sin_transaccion_lanza_runtime_error_y_no_audita_ni_notifica(self):
        """Contrato de núcleo (D-36, D-42)."""
        with mock.patch.object(connections["default"], "in_atomic_block", False), self.assertRaises(RuntimeError):
            self.registrar()
        self.assertFalse(Bitacora.objects.exists())
        auditoria, avisos = RegistroAuditoria.objects.count(), Notificacion.objects.count()
        self.registrar()
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), (auditoria, avisos))


class ConsultaDeBitacoraTests(Base):
    """PROD-CNS-BIT: los dos tipos se listan y se ofrecen en el filtro «Tipo» (disparador «Cuando exista `produccion` completa», punto 3)."""

    def test_regla_el_filtro_ofrece_los_dos_tipos_y_el_de_cosecha(self):
        """`TIPOS_DE_FILTRO` suma `cosecha`, `incumplimiento_de_clausula` y `anulacion_de_resolucion`."""
        valores = [v for v, _ in bitacora.TIPOS_DE_FILTRO]
        for tipo in ("cosecha", INCUMPLIMIENTO, ANULACION):
            self.assertIn(tipo, valores)

    def test_regla_la_consulta_lista_un_registro_de_cada_tipo_y_el_filtro_los_separa(self):
        """La consulta (sin lote: la columna muestra «—») lista los registros y el filtro por tipo trae solo el pedido."""
        self.registrar(INCUMPLIMIENTO, "Uno")
        self.registrar(ANULACION, "Otro")
        lote_maduro(self.e, 10)
        def tipos(filtros):
            pagina = bitacora.consultar_bitacora(self.e.agronomo, self.e.invernadero.pk, filtros, 1)
            return {r.tipo for dia in pagina.dias for r in dia.registros}

        self.assertTrue({INCUMPLIMIENTO, ANULACION} <= tipos(bitacora.FiltrosDeBitacora()))
        self.assertEqual(tipos(bitacora.FiltrosDeBitacora(tipo=ANULACION)), {ANULACION})
