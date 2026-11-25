# Pruebas de los registrantes de PRD-04 (paso 5; docs/api/produccion.md, sección 3; docs/api/extensiones_de_maestros.md, «Sectores» y «Lote 5»;
# docs/casos_de_uso/produccion/sector_fuera_de_servicio.md, «Vuelta a servicio y baja (MAE-03)»): lo que `produccion` registra en `maestros` para
# cerrar el registro «Fuera de servicio» al volver el sector a servicio (`registrar_efecto_de_vuelta_a_servicio`), al darlo de baja
# (`registrar_efecto_de_baja_de_sector`) y al dar de baja el invernadero (`registrar_efecto_de_baja`).
#
# CONTRATO que fijan estas pruebas (se anota en el Cierre): en `produccion/servicios/registrantes.py`, `efecto_de_vuelta_a_servicio(actor, sector)`,
# `efecto_de_baja_de_sector(actor, sector)` y `efecto_de_baja_del_invernadero(actor, invernadero)`. Cada uno cierra con `fecha_fin = hoy` el registro
# abierto (no toca los cerrados, ni crea otro: es la MISMA fila antes y después) y, sin registro abierto, no hace nada. Solo la vuelta a servicio escribe
# además un registro de bitácora `otro_evento` con el sector y los días que estuvo fuera. Se prueba punta a punta con las funciones públicas de `maestros`
# y el registrante REAL, no con uno falso.

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from datetime import timedelta

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from inventario.models import LoteInsumo
from maestros import extensiones
from maestros.models import SectorProduccion
from maestros.servicios import invernaderos, sectores
from maestros.tests.fabricas import codigos_de, crear_sector, error_de
from produccion.models import Bitacora, FueraDeServicio
from produccion.servicios import registrantes
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo, orden_de_siembra
from produccion.tests.test_modelos_fds import fuera_de_servicio_de


class BaseDeRegistrantesDeFds(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):  # CON-04a: estos servicios asientan
    """Un invernadero con un sector por etapa; los sectores fuera de servicio de las pruebas se arman con `fuera_de_servicio_de`."""

    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.hoy = timezone.localdate()

    def sector_fuera_de_servicio(self, nombre="Fuera 1", tipo="crecimiento", dias=3, con_registro=True):
        """Un sector «fuera de servicio» y, si `con_registro`, su registro abierto desde hace `dias` días."""
        sector = crear_sector(self.e.invernadero, nombre, tipo, 50, "fuera_de_servicio")
        registro = None
        if con_registro:
            registro = fuera_de_servicio_de(self.e, sector, fecha_bitacora=self.hoy - timedelta(days=dias))
        return sector, registro


class VueltaAServicioTests(BaseDeRegistrantesDeFds):
    """`registrar_efecto_de_vuelta_a_servicio` (postcondición b de PROD-MOD-SCT)."""

    def test_ext_con_registro_abierto_lo_cierra_con_la_fecha_de_hoy_y_es_la_misma_fila(self):
        """Postcondición b de PROD-MOD-SCT: el registro abierto se cierra con `fecha_fin = hoy`; no se crea otro."""
        sector, registro = self.sector_fuera_de_servicio()
        sectores.volver_a_servicio_sector(self.e.agronomo, sector.pk)
        self.assertEqual(FueraDeServicio.objects.count(), 1)
        cerrado = FueraDeServicio.objects.get()
        self.assertEqual((cerrado.pk, cerrado.fecha_fin, cerrado.fecha_efectiva), (registro.pk, self.hoy, self.hoy - timedelta(days=3)))
        self.assertEqual(SectorProduccion.objects.get(pk=sector.pk).estado_sector, "activo")

    def test_ext_escribe_en_la_bitacora_que_el_sector_vuelve_con_los_dias_que_estuvo_fuera(self):
        """«Vuelta a servicio y baja (MAE-03)»: bitácora `otro_evento` con el sector, el actor y «desde … hasta …, N días»."""
        sector, _ = self.sector_fuera_de_servicio(dias=3)
        sectores.volver_a_servicio_sector(self.e.agronomo, sector.pk)
        evento = Bitacora.objects.get(tipo_evento="otro_evento")
        self.assertEqual((evento.responsable_id, evento.fecha_bitacora, evento.invernadero_id, evento.lote_id), (self.e.agronomo.pk, self.hoy, self.e.invernadero.pk, None))
        self.assertEqual([s.pk for s in evento.sectores.all()], [sector.pk])
        for texto in (
            f"El sector {sector.nombre_sector} vuelve a estar activo.",
            (self.hoy - timedelta(days=3)).strftime("%d/%m/%Y"),
            self.hoy.strftime("%d/%m/%Y"),
            "3 días",
        ):
            self.assertIn(texto, evento.descripcion_evento)

    def test_ext_un_dia_va_en_singular_y_el_mismo_dia_es_cero_dias(self):
        """El texto concuerda en número: «1 día» y «0 días»."""
        uno, _ = self.sector_fuera_de_servicio("Uno", dias=1)
        cero, _ = self.sector_fuera_de_servicio("Cero", "floracion", dias=0)
        sectores.volver_a_servicio_sector(self.e.agronomo, uno.pk)
        sectores.volver_a_servicio_sector(self.e.agronomo, cero.pk)
        textos = " ".join(Bitacora.objects.filter(tipo_evento="otro_evento").values_list("descripcion_evento", flat=True))
        self.assertIn("1 día.", textos)
        self.assertIn("0 días", textos)

    def test_ext_solo_cierra_el_abierto_y_no_toca_los_registros_ya_cerrados(self):
        """Un sector que ya salió y volvió antes conserva su historial: solo se cierra el registro abierto."""
        sector, abierto = self.sector_fuera_de_servicio(dias=2)
        viejo = fuera_de_servicio_de(self.e, sector, fecha_bitacora=self.hoy - timedelta(days=20), fecha_fin=self.hoy - timedelta(days=10))
        sectores.volver_a_servicio_sector(self.e.agronomo, sector.pk)
        self.assertEqual(FueraDeServicio.objects.get(pk=viejo.pk).fecha_fin, self.hoy - timedelta(days=10))
        self.assertEqual(FueraDeServicio.objects.get(pk=abierto.pk).fecha_fin, self.hoy)

    def test_ext_sin_registro_abierto_no_hace_nada_y_el_sector_vuelve_igual(self):
        """Neutro sin datos: un sector fuera de servicio sin registro (cargado por otra vía) vuelve a activo sin error ni bitácora."""
        sector, _ = self.sector_fuera_de_servicio(con_registro=False)
        sectores.volver_a_servicio_sector(self.e.agronomo, sector.pk)
        self.assertFalse(FueraDeServicio.objects.exists() or Bitacora.objects.exists())
        self.assertEqual(SectorProduccion.objects.get(pk=sector.pk).estado_sector, "activo")

    def test_ext_el_registro_queda_asociado_al_mismo_sector_antes_y_despues(self):
        """«Que el registro del sector es el mismo antes y después»: sector, invernadero y motivo no cambian al cerrarlo."""
        sector, registro = self.sector_fuera_de_servicio()
        sectores.volver_a_servicio_sector(self.e.agronomo, sector.pk)
        cerrado = FueraDeServicio.objects.get(pk=registro.pk)
        self.assertEqual(
            (cerrado.sector_id, cerrado.invernadero_id, cerrado.motivo_fuera_de_servicio), (sector.pk, registro.invernadero_id, registro.motivo_fuera_de_servicio)
        )

    def test_ext_la_vuelta_a_servicio_pasa_de_punta_a_punta_con_el_servicio_real_de_poner_fuera_de_servicio(self):
        """De punta a punta: se pone fuera de servicio con el caso de uso real y se vuelve a activar; el registro queda cerrado y el sector se
        puede volver a poner fuera de servicio (un solo registro abierto por sector)."""
        from produccion.servicios import sectores_fuera_de_servicio as fds

        datos = fds.DatosDeFueraDeServicio(sector_id=self.e.sectores["crecimiento"].pk, motivo="Rotura", fecha=self.hoy)
        fds.poner_fuera_de_servicio(self.e.agronomo, datos)
        sectores.volver_a_servicio_sector(self.e.agronomo, self.e.sectores["crecimiento"].pk)
        fds.poner_fuera_de_servicio(self.e.agronomo, datos)
        self.assertEqual(sorted(FueraDeServicio.objects.values_list("fecha_fin", flat=True), key=lambda f: (f is None, f)), [self.hoy, None])


class BajaDeSectorTests(BaseDeRegistrantesDeFds):
    """`registrar_efecto_de_baja_de_sector` (postcondición b de PROD-BAJ-SCT)."""

    def test_ext_con_registro_abierto_lo_cierra_con_la_fecha_de_hoy_sin_escribir_bitacora(self):
        """Postcondición b de PROD-BAJ-SCT: se cierra el registro abierto; no hay evento de «vuelta» (el sector no vuelve a servicio)."""
        sector, registro = self.sector_fuera_de_servicio()
        sectores.baja_sector(self.e.agronomo, sector.pk)
        self.assertEqual(FueraDeServicio.objects.get(pk=registro.pk).fecha_fin, self.hoy)
        self.assertEqual(SectorProduccion.objects.get(pk=sector.pk).estado_sector, "inactivo")
        self.assertFalse(Bitacora.objects.filter(tipo_evento="otro_evento").exists())

    def test_ext_sin_registro_abierto_la_baja_funciona_igual(self):
        """Neutro: un sector activo (sin registro) o fuera de servicio sin registro se da de baja sin error."""
        sector, _ = self.sector_fuera_de_servicio(con_registro=False)
        activo = self.e.sectores["floracion"]
        crear_sector(self.e.invernadero, "Otro de floración", "floracion")  # evita la advertencia del último sector activo del tipo
        sectores.baja_sector(self.e.agronomo, sector.pk)
        sectores.baja_sector(self.e.agronomo, activo.pk)
        self.assertFalse(FueraDeServicio.objects.exists())

    def test_ext_no_toca_los_registros_de_otros_sectores(self):
        """Solo el del sector que se da de baja."""
        sector, registro = self.sector_fuera_de_servicio("Uno")
        _, otro = self.sector_fuera_de_servicio("Otro", "floracion")
        sectores.baja_sector(self.e.agronomo, sector.pk)
        self.assertEqual(FueraDeServicio.objects.get(pk=registro.pk).fecha_fin, self.hoy)
        self.assertIsNone(FueraDeServicio.objects.get(pk=otro.pk).fecha_fin)


class BajaDeInvernaderoTests(BaseDeRegistrantesDeFds):
    """`registrar_efecto_de_baja` (baja del invernadero): cierra los registros abiertos de todos sus sectores."""

    @classmethod
    def setUpTestData(cls):
        """Con el lote de semillas en cero: con stock la baja del invernadero se rechaza por otra regla (precondición e de PROD-BAJ-INV)."""
        cls.e = invernadero_con_produccion()
        LoteInsumo.objects.update(cantidad_disponible=0)
        cls.hoy = timezone.localdate()

    def test_ext_cierra_los_registros_abiertos_de_los_sectores_del_invernadero_y_no_los_cerrados_ni_los_de_otro_invernadero(self):
        """Postcondición b de PROD-BAJ-INV y D-51 punto 7: los abiertos se cierran con la fecha de hoy; los ya cerrados y los de otro
        invernadero quedan como estaban."""
        uno, abierto_uno = self.sector_fuera_de_servicio("Uno")
        dos, abierto_dos = self.sector_fuera_de_servicio("Dos", "floracion", dias=7)
        cerrado = fuera_de_servicio_de(self.e, uno, fecha_bitacora=self.hoy - timedelta(days=30), fecha_fin=self.hoy - timedelta(days=20))
        ajeno = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2")
        sector_ajeno = crear_sector(ajeno.invernadero, "Ajeno", "crecimiento", 50, "fuera_de_servicio")
        registro_ajeno = fuera_de_servicio_de(ajeno, sector_ajeno)
        invernaderos.baja_invernadero(crear_gerente(), self.e.invernadero.pk)
        self.assertEqual(FueraDeServicio.objects.get(pk=abierto_uno.pk).fecha_fin, self.hoy)
        self.assertEqual(FueraDeServicio.objects.get(pk=abierto_dos.pk).fecha_fin, self.hoy)
        self.assertEqual(FueraDeServicio.objects.get(pk=cerrado.pk).fecha_fin, self.hoy - timedelta(days=20))
        self.assertIsNone(FueraDeServicio.objects.get(pk=registro_ajeno.pk).fecha_fin)
        self.assertFalse(Bitacora.objects.filter(tipo_evento="otro_evento").exists())

    def test_ext_sin_registros_abiertos_la_baja_del_invernadero_funciona_igual(self):
        """Neutro sin datos."""
        invernaderos.baja_invernadero(crear_gerente(), self.e.invernadero.pk)
        self.assertFalse(FueraDeServicio.objects.exists())

    def test_pre_la_baja_del_invernadero_sigue_sin_lotes_ni_ordenes_como_pide_prd_01(self):
        """PRD-01 sigue vigente: con un lote activo y una orden «a realizar» la baja se rechaza con `lotes_activos` y `ordenes_a_realizar`, y
        el registro «Fuera de servicio» sigue abierto (el efecto solo corre si la baja se hace)."""
        _, registro = self.sector_fuera_de_servicio()
        lote_activo(self.e, cantidad=10)
        orden_de_siembra(self.e, plantines=5, sector="germinacion", con_reserva=False)
        error = error_de(lambda: invernaderos.baja_invernadero(crear_gerente(), self.e.invernadero.pk))
        self.assertTrue({"lotes_activos", "ordenes_a_realizar"} <= set(codigos_de(error, "__all__")))
        self.assertIsNone(FueraDeServicio.objects.get(pk=registro.pk).fecha_fin)

    def test_la_cantidad_de_consultas_no_depende_de_los_sectores_fuera_de_servicio(self):
        """Una consulta por tabla, no por sector: el efecto es el mismo con uno que con varios registros abiertos."""
        self.sector_fuera_de_servicio("Fuera base", "crecimiento")
        with CaptureQueriesContext(connection) as pocas:
            registrantes.efecto_de_baja_del_invernadero(self.e.agronomo, self.e.invernadero)
        for numero, tipo in enumerate(("crecimiento", "floracion", "fructificacion", "maduracion")):
            self.sector_fuera_de_servicio(f"Fuera {numero}", tipo)
        with CaptureQueriesContext(connection) as muchas:
            registrantes.efecto_de_baja_del_invernadero(self.e.agronomo, self.e.invernadero)
        self.assertEqual(len(pocas), len(muchas))


class RegistroDeLosPuntosTests(TestCase):
    """`ProduccionConfig.ready()` registra los tres efectos, una sola vez aunque `ready()` corra más de una vez."""

    def test_ext_los_tres_efectos_estan_registrados_una_sola_vez(self):
        """Los `registrar_*` de `maestros` no son idempotentes: `ready()` lleva la guarda de siempre."""
        apps.get_app_config("produccion").ready()
        for lista, funcion in (
            (extensiones._VUELTAS_A_SERVICIO, registrantes.efecto_de_vuelta_a_servicio),
            (extensiones._EFECTOS_DE_BAJA_DE_SECTOR, registrantes.efecto_de_baja_de_sector),
            (extensiones._EFECTOS_DE_BAJA, registrantes.efecto_de_baja_del_invernadero),
        ):
            self.assertEqual(lista.count(funcion), 1, funcion.__name__)
