# Pruebas de concurrencia de PROD-REG-LTE · Registrar Lote Existente (PRD-05, paso 3; docs/patrones/bloqueos.md, «`produccion`» y «Contabilidad»).
# Orden de bloqueo de `registrar_lote_existente`: cuenta del Agrónomo → invernadero → variedad → sectores (id) → filas nuevas → ejercicio (al final).
#
# Dos hilos y dos conexiones (`correr_a_la_vez`, core/tests/concurrencia.py): `primera` se detiene en su punto de parada (por defecto, al registrar su
# primera auditoría: ya tomó sus bloqueos y escribió, pero no confirmó) y recién entonces arranca la otra.
#
# QUÉ FILA COMPARTE CADA PRUEBA (lo que hace que una pueda fallar al quitar un bloqueo):
# - «contra concretar una siembra normal»: la carga toma la cuenta del Agrónomo, el invernadero, la variedad del lote y los sectores de Maduración. La
#   concreción (de una orden planificada por InfoPonia, sin Agrónomo, de OTRA variedad y en Germinación) toma la cuenta del Capataz, el invernadero, esa
#   otra variedad y su sector. La ÚNICA fila compartida es el invernadero: por eso quitar `bloquear_invernadero_activo` de la carga hace fallar la prueba
#   en la que concretar va primero (la carga no ve la siembra aún sin confirmar y se registra: tiene que rechazarla con `invernadero_con_siembras`).
# - «dos cargas sobre el mismo sector»: las hace el mismo Agrónomo en el mismo invernadero, así que comparten la cuenta, el invernadero y el sector. Acá
#   el invernadero ya serializa y el bloqueo de los sectores es redundante; se mantiene por el orden global de bloqueos (sectores antes que insumos,
#   D-50 punto 10). Lo que hace fallar a esta prueba es quitar la relectura posterior al bloqueo (extensión 10a), no quitar un bloqueo.
#
# Son `TransactionTestCase`: su `flush` vacía todas las tablas al terminar (Georef, tipos de etapa, categorías y plan de cuentas), así que cada prueba
# arma su invernadero con geografía propia y vuelve a asegurar los datos (docs/patrones/datos_de_migracion.md).

from datetime import timedelta
from decimal import Decimal

from django.test import TransactionTestCase, tag
from django.utils import timezone

from contabilidad.models import AsientoContable
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, verificar_invariantes_contables
from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, perezoso
from maestros.models import EtapaProductiva
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import asegurar_datos_de_maestros, crear_sector
from produccion.models import Lote, OcupacionSector, Siembra
from produccion.tests.fabricas import codigos_del_rechazo, invernadero_con_produccion, orden_de_siembra, separar, variedad_con_stock
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

registros = perezoso("produccion.servicios.lotes_existentes")
siembras = perezoso("produccion.servicios.siembras")
D = Decimal


def hoy():
    return timezone.localdate()


@tag("concurrencia")
class LoteExistenteConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # el flush de la prueba anterior lo vació
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento; el flush de esta TransactionTestCase lo vacía en cada prueba
        self.e = invernadero_con_produccion(geografia_propia=True)
        self.e.sectores["maduracion_2"] = crear_sector(self.e.invernadero, nombre="Sector maduracion 2", tipo="maduracion", agujeros=100)
        self.etapa = EtapaProductiva.objects.get(ciclo__variedad=self.e.variedad, tipo_etapa__codigo="maduracion").pk

    def datos(self, plantas=60, sector="maduracion", **cambios):
        base = dict(
            invernadero_id=self.e.invernadero.pk,
            variedad_id=self.e.variedad.pk,
            etapa_id=self.etapa,
            fecha_siembra=hoy() - timedelta(days=40),
            fecha_ingreso_etapa=hoy() - timedelta(days=10),
            cantidad=plantas,
            costo_estimado=D("1000.00"),
            distribucion={self.e.sectores[sector].pk: plantas},
        )
        base.update(cambios)
        return registros.DatosDeLoteExistente(**base)

    def cargar(self, **cambios):
        return lambda: registros.registrar_lote_existente(self.e.agronomo, self.datos(**cambios))

    def siembra_normal_para_concretar(self):
        """Una orden «a realizar» planificada por InfoPonia (sin Agrónomo), de otra variedad y en Germinación, y la llamada que la concreta."""
        otra, existencia_otra = variedad_con_stock(self.e, nombre="Otra", stock=500)
        orden = orden_de_siembra(self.e, plantines=20, sector="germinacion", agronomo=False, variedad=otra, existencia=existencia_otra)
        return lambda: siembras.concretar_siembra(self.e.capataz, orden.pk, siembras.DatosDeConcrecion())

    # ---- Contra concretar una siembra normal en el mismo invernadero ----

    def test_regla_concretar_una_siembra_normal_primero_la_carga_espera_y_se_rechaza_porque_ve_la_siembra(self):
        """Extensión 10a y requisito especial: «no se registra un lote existente mientras se concreta una siembra normal en el mismo invernadero». La
        concreción toma el invernadero primero y se detiene sin confirmar; la carga espera ese bloqueo, relee, ve la siembra normal concretada y se rechaza
        con `invernadero_con_siembras`. Sin el bloqueo del invernadero en la carga, no vería nada (la concreción no confirmó) y se registraría."""
        self.armar()
        concretar = self.siembra_normal_para_concretar()
        resultados = correr_a_la_vez(concretar, self.cargar(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["invernadero_con_siembras"])
        self.assertEqual(Siembra.objects.filter(tipo_siembra="carga_inicial").count(), 0)
        self.assertEqual(Lote.objects.count(), 1)  # solo el de la siembra normal
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_lote_existente").count(), 0)
        self.assertEqual(AsientoContable.objects.count(), 1)  # CON-04a: solo el de la siembra normal (su consumo de semilla); la carga no asentó

    def test_regla_la_carga_primero_concretar_espera_y_las_dos_terminan_bien(self):
        """Al revés: la carga toma el invernadero primero; la concreción de una siembra normal espera y se concreta después (concretar una normal no
        está impedido por una carga previa). Dos lotes, dos asientos (el de la carga y el consumo de la siembra normal, CON-04a). OJO: esta prueba NO falla si se quita un bloqueo (las dos terminan bien con o sin él);
        solo comprueba que el orden de bloqueos no se traba."""
        self.armar()
        concretar = self.siembra_normal_para_concretar()
        resultados = correr_a_la_vez(self.cargar(), concretar, primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Lote.objects.count(), 2)
        self.assertEqual(AsientoContable.objects.count(), 2)
        verificar_invariantes_contables()

    # ---- Dos cargas sobre el mismo sector ----

    def test_regla_dos_cargas_sobre_el_mismo_sector_una_gana_y_la_otra_se_rechaza_con_los_libres_que_ve(self):
        """Requisito especial: «el control de concurrencia impide que dos usuarios ocupen los mismos agujeros». Dos cargas de 60 plantas sobre un sector de
        100 (dos pestañas del mismo Agrónomo): la segunda espera, relee los agujeros que dejó la primera (40 libres) y se rechaza con `supera_agujeros`
        (extensión 7a/10a). Sin releer bajo bloqueo se registraría y el sector quedaría ocupado en 120 de 100."""
        self.armar()
        resultados = correr_a_la_vez(self.cargar(plantas=60), self.cargar(plantas=60), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["supera_agujeros"])
        self.assertEqual(Lote.objects.count(), 1)
        self.assertEqual(OcupacionSector.objects.count(), 1)
        sector = self.e.sectores["maduracion"]
        self.assertEqual(api_sectores.agujeros_de([sector])[sector.pk].libres, 40)
        self.assertEqual(AsientoContable.objects.count(), 1)
        verificar_invariantes_contables()

    def test_regla_dos_cargas_que_no_compiten_se_hacen_las_dos(self):
        """Dos cargas en sectores distintos (mismo Agrónomo, así que se serializan por su cuenta): las dos se registran, con un asiento cada una."""
        self.armar()
        resultados = correr_a_la_vez(
            self.cargar(plantas=60, sector="maduracion"), self.cargar(plantas=60, sector="maduracion_2"), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Lote.objects.count(), 2)
        self.assertEqual(AsientoContable.objects.count(), 2)
        verificar_invariantes_contables()
