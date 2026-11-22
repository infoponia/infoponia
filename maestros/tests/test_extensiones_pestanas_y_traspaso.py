# Pruebas de lo que PRD-01 suma a `maestros/extensiones.py` (paso 4): el punto `registrar_pestana_de_invernadero` y el contrato
# ampliado de `traspasar`, que ahora devuelve las instancias que tocó para que `modificar_invernadero` las sume a los afectados de
# su único registro (D-36; D-60 punto 4; decisión del estudiante en PRD-01). Fuente: docs/api/extensiones_de_maestros.md
# («Pestañas de la ficha del invernadero») y docs/api/produccion.md (sección 3). Con registrantes falsos (`mock.patch.object`).

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.safestring import mark_safe

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros import extensiones
from maestros.models import SectorProduccion
from maestros.servicios import invernaderos
from maestros.tests.fabricas import ConDatosDeMaestros, crear_agronomo, crear_capataz_activo, crear_invernadero, crear_sector
from maestros.tests.test_prod_mod_inv import datos_de


class PestanasDeInvernaderoTests(SimpleTestCase):
    """El punto `registrar_pestana_de_invernadero(clave, titulo, funcion)` y `pestanas_de_invernadero(actor, invernadero)`."""

    def test_ext_sin_registrantes_no_hay_pestanas(self):
        """Prueba mínima (neutro): sin registrantes, ninguna pestaña extra."""
        with mock.patch.object(extensiones, "_PESTANAS", []):
            self.assertEqual(extensiones.pestanas_de_invernadero(object(), object()), [])

    def test_ext_las_registradas_salen_en_orden_de_registro_y_sin_las_que_devuelven_none(self):
        """Prueba mínima (con datos): en orden de registro; la función que devuelve `None` (el actor no la ve) no figura."""
        with mock.patch.object(extensiones, "_PESTANAS", []):
            extensiones.registrar_pestana_de_invernadero("lotes", "Lotes activos", lambda actor, inv: mark_safe("<p>lotes</p>"))
            extensiones.registrar_pestana_de_invernadero("secreta", "Secreta", lambda actor, inv: None)
            extensiones.registrar_pestana_de_invernadero("bitacora", "Bitácora", lambda actor, inv: mark_safe("<p>bitácora</p>"))
            pestanas = extensiones.pestanas_de_invernadero(object(), object())
        self.assertEqual([(p.clave, p.titulo) for p in pestanas], [("lotes", "Lotes activos"), ("bitacora", "Bitácora")])
        self.assertEqual(pestanas[0].html, "<p>lotes</p>")

    def test_ext_repetir_la_clave_lanza_runtime_error(self):
        """API: `clave` única; repetirla lanza `RuntimeError`."""
        with mock.patch.object(extensiones, "_PESTANAS", []):
            extensiones.registrar_pestana_de_invernadero("lotes", "Lotes activos", lambda actor, inv: None)
            with self.assertRaises(RuntimeError):
                extensiones.registrar_pestana_de_invernadero("lotes", "Otra", lambda actor, inv: None)

    def test_ext_cada_funcion_se_llama_una_sola_vez(self):
        """Prueba mínima (sin consultas por fila): cada registrante se llama una vez por ficha, con el actor y el invernadero."""
        llamada = mock.Mock(return_value=mark_safe("<p>x</p>"))
        actor, invernadero = SimpleNamespace(), SimpleNamespace()
        with mock.patch.object(extensiones, "_PESTANAS", []):
            extensiones.registrar_pestana_de_invernadero("lotes", "Lotes activos", llamada)
            extensiones.pestanas_de_invernadero(actor, invernadero)
        llamada.assert_called_once_with(actor, invernadero)


class FichaConPestanasTests(ConDatosDeMaestros, TestCase):
    """La ficha del invernadero muestra las pestañas registradas después de «Sectores»."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo)
        self.url = reverse("maestros:invernadero", args=[self.invernadero.pk])
        self.client.force_login(self.agronomo)

    def con_pestana(self, html='<ul><li class="x">L-1 &amp; L-2</li></ul>'):
        return mock.patch.object(
            extensiones, "_PESTANAS", [("lotes", "Lotes activos", lambda actor, inv: mark_safe(html))]
        )

    def test_prueba_minima_sin_registrantes_la_ficha_no_tiene_pestanas_extra(self):
        """Prueba mínima: sin registrantes, la ficha solo tiene «Sectores»."""
        with mock.patch.object(extensiones, "_PESTANAS", []):
            respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Lotes activos")

    def test_prueba_minima_la_pestana_registrada_se_muestra_como_enlace_y_su_contenido_al_elegirla(self):
        """Prueba mínima: el título es un enlace (funciona sin JavaScript); su contenido aparece con `?pestana=lotes`."""
        with self.con_pestana():
            ficha = self.client.get(self.url)
            elegida = self.client.get(self.url + "?pestana=lotes")
        self.assertContains(ficha, "Lotes activos")
        self.assertContains(ficha, "?pestana=lotes")
        self.assertNotContains(ficha, 'class="x"')
        self.assertContains(elegida, 'class="x"')

    def test_prueba_minima_el_html_no_se_escapa_dos_veces(self):
        """Prueba mínima: el HTML ya armado y escapado por quien lo registra llega tal cual (`&amp;` queda `&amp;`)."""
        with self.con_pestana():
            elegida = self.client.get(self.url + "?pestana=lotes")
        self.assertContains(elegida, "L-1 &amp; L-2", html=False)
        self.assertNotContains(elegida, "&amp;amp;")
        self.assertNotContains(elegida, "&lt;ul&gt;")


class TraspasoConAfectadosTests(ConDatosDeMaestros, TestCase):
    """El contrato ampliado: `traspasar` devuelve las instancias que tocó (D-36, D-60 punto 4)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.capataz = crear_capataz_activo()
        self.nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo, capataz=self.capataz)
        self.sector = crear_sector(self.invernadero)

    def test_ext_traspasar_junta_lo_que_devuelven_los_registrantes_y_tolera_none(self):
        """`traspasar` devuelve las instancias de todos los registrantes, juntas; un registrante que no devuelve nada (el
        contrato anterior) cuenta como lista vacía."""
        otro = crear_sector(self.invernadero, nombre="Sector 2")
        registrantes = [(None, lambda *a: [self.sector]), (None, lambda *a: None), (None, lambda *a: [otro])]
        with mock.patch.object(extensiones, "_TRASPASOS", registrantes):
            afectados = extensiones.traspasar(self.gerente, self.invernadero, "capataz", self.capataz, self.nuevo)
        self.assertEqual(afectados, [self.sector, otro])

    def test_d36_modificar_invernadero_suma_lo_traspasado_a_los_afectados_de_su_unico_registro(self):
        """D-36 y D-60 punto 4: lo que traspasan los registrantes queda entre los afectados del registro
        `modificacion_invernadero`; sigue siendo un solo registro."""
        antes = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_INVERNADERO).count()
        with mock.patch.object(extensiones, "_TRASPASOS", [(lambda *a: [], lambda *a: [self.sector])]):
            invernaderos.modificar_invernadero(
                self.gerente,
                self.invernadero.pk,
                **(datos_de(self.invernadero) | {"capataz_id": self.nuevo.pk, "personal_confirmado": True}),
            )
        registros = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_INVERNADERO)
        self.assertEqual(registros.count(), antes + 1)
        modelos_afectados = [(a["modelo"], a["id"]) for a in registros.latest("id").afectados]
        self.assertIn(("maestros.sectorproduccion", self.sector.pk), modelos_afectados)
        self.assertEqual(len(modelos_afectados), len(set(modelos_afectados)), "sin afectados repetidos")

    def test_d36_un_registrante_que_devuelve_none_no_cambia_los_afectados(self):
        """Compatibilidad: con registrantes del contrato anterior (que devuelven `None`) los afectados son los de siempre."""
        with mock.patch.object(extensiones, "_TRASPASOS", [(lambda *a: [], lambda *a: None)]):
            invernaderos.modificar_invernadero(
                self.gerente,
                self.invernadero.pk,
                **(datos_de(self.invernadero) | {"capataz_id": self.nuevo.pk, "personal_confirmado": True}),
            )
        registro = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_INVERNADERO).latest("id")
        self.assertNotIn("maestros.sectorproduccion", [a["modelo"] for a in registro.afectados])
        self.assertFalse(SectorProduccion.objects.filter(pk=self.sector.pk).exclude(invernadero=self.invernadero).exists())
