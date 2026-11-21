# Pruebas de `contabilidad.OrigenDocumento` (D-52, CON-01): no se crea uno puro, la hija directa fija su `tipo`,
# la nieta lo hereda, el `tipo` es obligatorio y está dentro de la lista, y los `id` se comparten entre hijas.
import io

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, models
from django.test import TestCase
from django.test.utils import isolate_apps

from contabilidad.models import OrigenDocumento


def _crear_tablas(*modelos):
    """Crea las tablas de las hijas de prueba. En PostgreSQL el DDL es transaccional: el TestCase lo deshace."""
    with connection.schema_editor() as editor:
        for modelo in modelos:
            editor.create_model(modelo)


class OrigenDocumentoModeloTests(TestCase):
    """Pruebas del modelo `OrigenDocumento` (decisión D-52, sin caso de uso)."""

    def test_d52_no_se_puede_guardar_uno_puro(self):
        """D-52 punto 1 y `docs/modelo/contabilidad.md` («Restricciones y reglas»): una instancia pura no se guarda."""
        with self.assertRaises(TypeError):
            OrigenDocumento(tipo=OrigenDocumento.Tipo.BITACORA).save()
        with self.assertRaises(TypeError):
            OrigenDocumento.objects.create(tipo=OrigenDocumento.Tipo.BITACORA)
        self.assertEqual(OrigenDocumento.objects.count(), 0)

    @isolate_apps("contabilidad")
    def test_d52_hija_fija_su_tipo_y_queda_creada(self):
        """D-52 punto 2: la hija directa fija su `tipo` (`TIPO_DE_ORIGEN`) y queda creada con su `id`."""

        class HijaBitacora(OrigenDocumento):
            TIPO_DE_ORIGEN = OrigenDocumento.Tipo.BITACORA

        _crear_tablas(HijaBitacora)
        hija = HijaBitacora.objects.create()
        self.assertIsNotNone(hija.id)
        self.assertEqual(OrigenDocumento.objects.get(id=hija.id).tipo, "bitacora")

    @isolate_apps("contabilidad")
    def test_d52_hija_no_cambia_su_tipo(self):
        """Modelo de contabilidad, atributo `tipo`: «lo fija la hija directa y nunca cambia»."""

        class HijaOrden(OrigenDocumento):
            TIPO_DE_ORIGEN = OrigenDocumento.Tipo.ORDEN_DE_TRABAJO

        _crear_tablas(HijaOrden)
        hija = HijaOrden(tipo=OrigenDocumento.Tipo.BITACORA)
        hija.save()
        self.assertEqual(hija.tipo, "orden_de_trabajo")
        hija.tipo = OrigenDocumento.Tipo.BITACORA
        hija.save()
        self.assertEqual(OrigenDocumento.objects.get(id=hija.id).tipo, "orden_de_trabajo")

    @isolate_apps("contabilidad")
    def test_d52_nieta_hereda_el_tipo_de_su_hija_directa(self):
        """D-52 punto 2: las hijas de las hijas (`Siembra`, `Consumo`...) no cambian: heredan `TIPO_DE_ORIGEN`."""

        class HijaOrden(OrigenDocumento):
            TIPO_DE_ORIGEN = OrigenDocumento.Tipo.ORDEN_DE_TRABAJO

        class NietaSiembra(HijaOrden):
            pass

        _crear_tablas(HijaOrden, NietaSiembra)
        nieta = NietaSiembra.objects.create()
        self.assertEqual(NietaSiembra.TIPO_DE_ORIGEN, OrigenDocumento.Tipo.ORDEN_DE_TRABAJO)
        self.assertEqual(OrigenDocumento.objects.get(id=nieta.id).tipo, "orden_de_trabajo")
        self.assertTrue(HijaOrden.objects.filter(id=nieta.id).exists())

    def test_d52_tipo_fuera_de_la_lista_no_es_valido(self):
        """Modelo de contabilidad, «Restricciones y reglas»: `tipo` dentro de la lista."""
        documento = OrigenDocumento(tipo="cualquiera")
        with self.assertRaises(ValidationError) as contexto:
            documento.full_clean()
        self.assertIn("tipo", contexto.exception.message_dict)

    @isolate_apps("contabilidad")
    def test_d52_hija_con_tipo_fuera_de_la_lista_no_se_guarda(self):
        """Modelo de contabilidad: una hija con un `TIPO_DE_ORIGEN` inválido o ausente no puede guardarse."""

        class HijaInvalida(OrigenDocumento):
            TIPO_DE_ORIGEN = "cualquiera"

        class HijaSinTipo(OrigenDocumento):
            pass

        _crear_tablas(HijaInvalida, HijaSinTipo)
        with self.assertRaises(TypeError):
            HijaInvalida.objects.create()
        with self.assertRaises(TypeError):
            HijaSinTipo.objects.create()
        self.assertEqual(OrigenDocumento.objects.count(), 0)

    def test_d52_tipo_es_obligatorio(self):
        """Modelo de contabilidad, «Restricciones y reglas»: `tipo` obligatorio."""
        with self.assertRaises(ValidationError) as contexto:
            OrigenDocumento().full_clean()
        self.assertIn("tipo", contexto.exception.message_dict)

    @isolate_apps("contabilidad")
    def test_d52_hijas_comparten_la_secuencia_de_id(self):
        """D-52 punto 2: los `id` se comparten entre todos los tipos de documento (no son consecutivos por tipo)."""

        class HijaOrden(OrigenDocumento):
            TIPO_DE_ORIGEN = OrigenDocumento.Tipo.ORDEN_DE_TRABAJO

        class HijaMovimiento(OrigenDocumento):
            TIPO_DE_ORIGEN = OrigenDocumento.Tipo.MOVIMIENTO_DE_INSUMO

        _crear_tablas(HijaOrden, HijaMovimiento)
        creadas = [HijaOrden.objects.create(), HijaMovimiento.objects.create(), HijaOrden.objects.create()]
        ids = [hija.id for hija in creadas]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(ids, sorted(ids))
        tipos = list(OrigenDocumento.objects.order_by("id").values_list("tipo", flat=True))
        self.assertEqual(tipos, ["orden_de_trabajo", "movimiento_de_insumo", "orden_de_trabajo"])

    def test_d52_makemigrations_no_deja_cambios(self):
        """CON-01, paso 2: los modelos de `contabilidad` y su migración inicial coinciden."""
        try:
            call_command("makemigrations", "contabilidad", check=True, dry_run=True, stdout=io.StringIO())
        except SystemExit:
            self.fail("makemigrations detectó cambios sin migrar en contabilidad")
