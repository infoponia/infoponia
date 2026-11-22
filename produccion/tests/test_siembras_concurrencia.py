# Pruebas de concurrencia de las siembras (PRD-01; docs/patrones/bloqueos.md, sección `produccion`; docs/patrones/stock.md, sección 5).
# Paso 5: PLANIFICAR. Dos planificaciones sobre la última semilla y sobre el último agujero; planificar contra la baja del sector y contra
# la baja de la variedad, en los dos órdenes. El paso 6 suma las de concretar en este mismo archivo.
#
# Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py): ``primera`` se detiene en su punto de parada
# (por defecto, ``RegistroAuditoria.objects.registrar``: ya tomó sus bloqueos y escribió, pero no confirmó) y recién entonces arranca la
# otra. Son ``TransactionTestCase``: su ``flush`` vacía todas las tablas al terminar (Georef, los tipos de etapa y las categorías
# también), así que cada prueba arma su invernadero con geografía propia y vuelve a asegurar los datos en ``setUp``
# (docs/patrones/datos_de_migracion.md). Un rechazo es un ``ErrorDeProduccion`` o una ``ValidationError`` de las bajas: nunca un 500.

from datetime import timedelta
from decimal import Decimal

from django.test import TransactionTestCase, tag
from django.utils import timezone

from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from inventario.servicios import variedades
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, perezoso
from maestros.models import SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import asegurar_datos_de_maestros
from inventario.models import LoteInsumo
from produccion.models import Lote, OcupacionSector, ReservaInsumo, Siembra
from produccion.tests.fabricas import codigos_del_rechazo, invernadero_con_produccion, orden_de_siembra, separar
from produccion.tests.test_prod_pnf_smb import datos

siembras = perezoso("produccion.servicios.siembras")


@tag("concurrencia")
class PlanificarConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de `planificar_siembra`: cuentas → invernadero → variedad → sectores → insumos → filas propias."""

    def armar(self, **opciones):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()  # el flush de la prueba anterior vació los tipos de etapa y las categorías
        self.e = invernadero_con_produccion(geografia_propia=True, **opciones)
        self.agronomo = self.e.agronomo

    def planificar(self, **cambios):
        return lambda: siembras.planificar_siembra(self.agronomo, datos(self.e, **cambios))

    def test_regla_stock_libre_dos_planificaciones_sobre_la_ultima_semilla_una_gana_y_la_otra_se_rechaza(self):
        """«El control de concurrencia sobre el stock libre impide la sobreasignación» (requisitos especiales): con 10 semillas libres,
        dos planificaciones de 10 plantines (en dos pestañas del mismo Agrónomo) no pasan las dos. La segunda espera el bloqueo del
        insumo del invernadero, ve la reserva de la primera y se rechaza con `stock_insuficiente`. Sin bloqueo, las dos verían 10 libres."""
        self.armar(stock_de_semillas=10)
        resultados = correr_a_la_vez(
            self.planificar(cantidad=10, prioridad="alta"), self.planificar(cantidad=10, prioridad="baja"), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["stock_insuficiente"])
        self.assertEqual(Siembra.objects.count(), 1)
        self.assertEqual(ReservaInsumo.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="planificacion_siembra").count(), 1)

    def test_regla_capacidad_libre_dos_planificaciones_sobre_el_ultimo_agujero_una_gana_y_la_otra_se_rechaza(self):
        """Garantías mínimas: «ningún espacio de sector queda comprometido por encima de lo realmente libre». Con un sector de 10
        agujeros, dos planificaciones de 10 plantines: la segunda espera el bloqueo del sector, ve los 10 comprometidos y se rechaza
        con `capacidad_insuficiente`."""
        self.armar(agujeros=10)
        resultados = correr_a_la_vez(
            self.planificar(cantidad=10, prioridad="alta"), self.planificar(cantidad=10, prioridad="baja"), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["capacidad_insuficiente"])
        self.assertEqual(sum(o.cant_agujeros_planificados for o in OcupacionSector.objects.all()), 10)

    def test_regla_dos_planificaciones_que_no_compiten_se_hacen_las_dos(self):
        """El bloqueo serializa pero no rechaza de más: con stock y espacio para las dos, se planifican las dos."""
        self.armar()
        resultados = correr_a_la_vez(
            self.planificar(cantidad=10, prioridad="alta"), self.planificar(cantidad=10, prioridad="baja"), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Siembra.objects.count(), 2)
        self.assertNotEqual(exitos[0].numero, exitos[1].numero)

    def test_pre_d_planificar_contra_la_baja_del_sector_la_baja_espera_y_se_rechaza_porque_ve_lo_comprometido(self):
        """PROD-BAJ-SCT reglas 2 y 3: quien compromete agujeros bloquea antes el sector; la baja espera a que confirme, cuenta lo
        comprometido después de bloquear y se rechaza con `agujeros_comprometidos`. El sector sigue activo."""
        self.armar()
        sector = self.e.sectores["germinacion"]
        resultados = correr_a_la_vez(
            self.planificar(), lambda: api_sectores.baja_sector(self.agronomo, sector.pk), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("agujeros_comprometidos", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(SectorProduccion.objects.get(pk=sector.pk).estado_sector, "activo")

    def test_pre_d_la_baja_del_sector_primero_planificar_espera_y_se_rechaza_porque_lo_ve_inactivo(self):
        """Contrato de D-40: si la baja confirma primero, la planificación espera el sector, lo relee, lo ve dado de baja y se rechaza
        con `sector_no_elegible` sin crear nada."""
        self.armar()
        sector = self.e.sectores["germinacion"]
        resultados = correr_a_la_vez(
            lambda: api_sectores.baja_sector(self.agronomo, sector.pk, advertencia_confirmada=True), self.planificar(), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["sector_no_elegible"])
        self.assertEqual(Siembra.objects.count(), 0)

    def test_pre_e_planificar_contra_la_baja_de_la_variedad_la_baja_espera_y_se_rechaza_porque_ve_la_orden(self):
        """PROD-BAJ-VAR precondición e: quien crea una orden de siembra bloquea antes la variedad; la baja espera, cuenta las órdenes
        «a realizar» después de bloquear y se rechaza con `ordenes_a_realizar`. La variedad sigue activa."""
        self.armar()
        resultados = correr_a_la_vez(
            self.planificar(), lambda: variedades.baja_variedad(self.agronomo, self.e.variedad.pk), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("ordenes_a_realizar", codigos_del_rechazo(rechazos[0]))
        self.e.variedad.refresh_from_db()
        self.assertEqual(self.e.variedad.estado_variedad, "activo")

    def test_pre_e_la_baja_de_la_variedad_primero_planificar_espera_y_se_rechaza_porque_la_ve_inactiva(self):
        """Si la baja de la variedad confirma primero, la planificación la relee después de bloquearla y se rechaza con
        `variedad_inactiva`, sin crear nada."""
        self.armar()
        resultados = correr_a_la_vez(
            lambda: variedades.baja_variedad(self.agronomo, self.e.variedad.pk), self.planificar(), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["variedad_inactiva"])
        self.assertEqual(Siembra.objects.count(), 0)


@tag("concurrencia")
class ConcretarConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de `concretar_siembra`: cuentas → invernadero → variedad → sectores de la orden → insumos y existencias → lotes de insumo
    (los toma `registrar_salida_por_consumo`) → la orden y sus filas. «Concretar contra cancelar» está en `test_cancelar_concurrencia.py`."""

    def armar(self, **opciones):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = invernadero_con_produccion(geografia_propia=True, **opciones)

    def concretar(self, orden):
        return lambda: siembras.concretar_siembra(self.e.capataz, orden.pk, siembras.DatosDeConcrecion())

    def test_garantia_una_orden_se_concreta_una_unica_vez_la_segunda_ve_el_nuevo_estado(self):
        """Garantías mínimas y requisito especial: dos concreciones simultáneas de la misma orden (dos pantallas del mismo Capataz): la
        segunda espera, relee la orden ya «concretada» y se rechaza con `orden_no_pendiente` (extensión 19a). Un solo lote, un solo
        descuento de stock y un solo registro de auditoría."""
        self.armar()
        orden = orden_de_siembra(self.e, plantines=50)
        resultados = correr_a_la_vez(self.concretar(orden), self.concretar(orden), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["orden_no_pendiente"])
        self.assertEqual(Lote.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="concrecion_siembra").count(), 1)
        self.assertEqual(LoteInsumo.objects.get(pk=self.e.lote_de_semillas.pk).cantidad_disponible, Decimal("950"))

    def test_regla_dos_ordenes_distintas_sobre_la_misma_semilla_no_descuentan_dos_veces_lo_mismo(self):
        """Dos concreciones de órdenes distintas sobre la misma semilla: se serializan por la existencia y el lote de insumo; el stock
        queda en 1.000 − 50 − 30 sin lote negativo ni doble descuento."""
        self.armar()
        una = orden_de_siembra(self.e, plantines=50)
        otra = orden_de_siembra(self.e, plantines=30, sector="crecimiento")
        resultados = correr_a_la_vez(self.concretar(una), self.concretar(otra), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(LoteInsumo.objects.get(pk=self.e.lote_de_semillas.pk).cantidad_disponible, Decimal("920"))
        self.assertFalse(LoteInsumo.objects.filter(es_faltante_sin_lote=True).exists())

    def test_pre_e_concretar_contra_la_baja_de_la_variedad_la_baja_espera_y_se_rechaza_porque_ve_el_lote(self):
        """PROD-BAJ-VAR precondiciones d y e: quien concreta bloquea la variedad (también al concretar). La baja espera, ya no ve la
        orden «a realizar» pero sí el lote activo, y se rechaza con `lotes_activos`: la variedad no se da de baja a mitad de camino."""
        self.armar()
        orden = orden_de_siembra(self.e, plantines=50)
        resultados = correr_a_la_vez(
            self.concretar(orden), lambda: variedades.baja_variedad(self.e.agronomo, self.e.variedad.pk), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["lotes_activos"])
        self.e.variedad.refresh_from_db()
        self.assertEqual(self.e.variedad.estado_variedad, "activo")
