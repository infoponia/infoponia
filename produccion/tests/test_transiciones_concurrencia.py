# Pruebas de concurrencia de las transiciones (PRD-02; docs/patrones/bloqueos.md, sección `produccion`; docs/casos_de_uso/produccion/transicion.md,
# «Requisitos especiales»). Paso 4: PLANIFICAR. Dos planificaciones sobre el mismo lote, dos sobre el último agujero y planificar contra la
# baja del sector, en los dos órdenes. El paso 5 suma las de concretar en este mismo archivo.
#
# Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py): ``primera`` se detiene en su punto de parada
# (por defecto, ``RegistroAuditoria.objects.registrar``: ya tomó sus bloqueos y escribió, pero no confirmó) y recién entonces arranca la
# otra. Son ``TransactionTestCase``: su ``flush`` vacía todas las tablas al terminar (Georef, los tipos de etapa y las categorías
# también), así que cada prueba arma su invernadero con geografía propia y vuelve a asegurar los datos en ``setUp``
# (docs/patrones/datos_de_migracion.md). Un rechazo es un ``ErrorDeProduccion`` o una ``ValidationError`` de las bajas: nunca un 500.

from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.test import TransactionTestCase, tag
from django.utils import timezone

from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.tests.fabricas import crear_cuenta
from core.models import Contador, RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Lote, Merma, OcupacionSector, TransicionEtapa
from produccion.servicios import mermas, ordenes, transiciones
from produccion.tests.fabricas import (
    codigos_del_rechazo,
    invernadero_con_produccion,
    lote_con_ciclo,
    orden_de_transicion,
    separar,
)
from produccion.tests.test_prod_cnc_trn import datos as datos_de_concrecion
from produccion.tests.test_prod_pnf_trn import datos


@tag("concurrencia")
class PlanificarTransicionConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de `planificar_transicion`: cuentas → invernadero → variedad → sectores destino → lote → filas propias."""

    def armar(self, **opciones):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()  # el flush de la prueba anterior vació los tipos de etapa y las categorías
        self.e = invernadero_con_produccion(geografia_propia=True, **opciones)
        self.agronomo = self.e.agronomo

    def planificar(self, lote, **cambios):
        return lambda: transiciones.planificar_transicion(self.agronomo, datos(self.e, lote, **cambios))

    def test_regla_dos_planificaciones_sobre_el_mismo_lote_una_gana_y_la_otra_se_rechaza(self):
        """Garantía «un lote tiene como máximo una orden de transición a realizar» (regla 4 de 8.21; sin restricción de base): dos
        planificaciones del mismo lote (dos pestañas del mismo Agrónomo) no pasan las dos. La segunda espera el bloqueo del lote, ve la
        orden de la primera y se rechaza con `lote_con_transicion`. Sin ese bloqueo, las dos verían el lote sin transición."""
        self.armar()
        lote = lote_con_ciclo(self.e, cantidad=10)
        resultados = correr_a_la_vez(
            self.planificar(lote, prioridad="alta"), self.planificar(lote, prioridad="baja"), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["lote_con_transicion"])
        self.assertEqual(TransicionEtapa.objects.filter(lote=lote, estado_orden="a_realizar").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="planificacion_transicion").count(), 1)

    def test_regla_capacidad_libre_dos_planificaciones_sobre_el_ultimo_agujero_una_gana_y_la_otra_se_rechaza(self):
        """Garantías mínimas: «ningún sector queda comprometido por encima de su capacidad libre aun cuando dos Agrónomos planifiquen al
        mismo tiempo». El sector de Floración tiene 20 agujeros y un lote ya ocupa 10: dos lotes de 10 compiten por los 10 últimos;
        el segundo espera el bloqueo del sector, ve lo comprometido y se rechaza con `capacidad_insuficiente`."""
        self.armar(agujeros=20)
        lote_con_ciclo(self.e, cantidad=10, etapa="floracion")
        uno, otro = lote_con_ciclo(self.e, cantidad=10), lote_con_ciclo(self.e, cantidad=10)
        resultados = correr_a_la_vez(self.planificar(uno), self.planificar(otro), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["capacidad_insuficiente"])
        sector = self.e.sectores["floracion"]
        self.assertEqual(api_sectores.agujeros_de([sector])[sector.pk].comprometidos, 10)
        self.assertEqual(
            sum(o.cant_agujeros_planificados for o in OcupacionSector.objects.filter(orden__estado_orden="a_realizar")), 10
        )

    def test_regla_dos_planificaciones_de_lotes_distintos_que_no_compiten_se_hacen_las_dos(self):
        """El bloqueo serializa pero no rechaza de más: con lugar para los dos lotes, se planifican las dos transiciones."""
        self.armar()
        uno, otro = lote_con_ciclo(self.e, cantidad=10), lote_con_ciclo(self.e, cantidad=10)
        resultados = correr_a_la_vez(self.planificar(uno), self.planificar(otro), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertNotEqual(exitos[0].numero, exitos[1].numero)
        self.assertEqual(Lote.objects.filter(estado_lote="activo").count(), 2)

    def test_pre_d_planificar_contra_la_baja_del_sector_destino_la_baja_espera_y_se_rechaza_porque_ve_lo_comprometido(self):
        """PROD-BAJ-SCT reglas 2 y 3: quien compromete agujeros bloquea antes el sector; la baja espera a que confirme, cuenta lo
        comprometido después de bloquear y se rechaza con `agujeros_comprometidos`. El sector sigue activo."""
        self.armar()
        lote = lote_con_ciclo(self.e, cantidad=10)
        sector = self.e.sectores["floracion"]
        resultados = correr_a_la_vez(
            self.planificar(lote), lambda: api_sectores.baja_sector(self.agronomo, sector.pk), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("agujeros_comprometidos", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(SectorProduccion.objects.get(pk=sector.pk).estado_sector, "activo")

    def test_pre_d_la_baja_del_sector_destino_primero_planificar_espera_y_se_rechaza_porque_lo_ve_inactivo(self):
        """Contrato de D-40 y extensión 13c: si la baja confirma primero, la planificación espera el sector, lo relee, lo ve dado de
        baja y se rechaza con `sector_no_elegible` sin crear nada."""
        self.armar()
        lote = lote_con_ciclo(self.e, cantidad=10)
        sector = self.e.sectores["floracion"]
        resultados = correr_a_la_vez(
            lambda: api_sectores.baja_sector(self.agronomo, sector.pk, advertencia_confirmada=True), self.planificar(lote), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["sector_no_elegible"])
        self.assertEqual(TransicionEtapa.objects.filter(estado_orden="a_realizar").count(), 0)


@tag("concurrencia")
class ConcretarTransicionConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de `concretar_transicion`: cuentas (Capataz y Agrónomo) → invernadero → variedad → sectores (destino y de origen, por id) →
    lote → la orden y sus ocupaciones. Las pruebas de planificar están en `PlanificarTransicionConcurrenciaTests`."""

    def armar(self, cantidad=50):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = invernadero_con_produccion(geografia_propia=True)
        self.lote = lote_con_ciclo(self.e, cantidad=cantidad)
        self.orden = orden_de_transicion(self.e, self.lote)

    def concretar(self, **cambios):
        return lambda: transiciones.concretar_transicion(
            self.e.capataz, self.orden.pk, datos_de_concrecion(cantidad=self.lote.cantidad_actual, **cambios)
        )

    def merma(self, cantidad):
        """Una merma de `cantidad` plantas, como la hará Registrar Merma (PRD-03): invernadero → lote → `aplicar_merma` → un registro."""

        def operacion():
            with transaction.atomic():
                bloquear_invernadero_activo(self.lote.invernadero_id)
                fila = Lote.objects.select_for_update(no_key=True).get(pk=self.lote.pk)
                resultado = mermas.aplicar_merma(fila, cantidad, "plaga", "", timezone.localdate(), self.e.capataz)
                RegistroAuditoria.objects.registrar(
                    usuario=self.e.agronomo, accion=RegistroAuditoria.Accion.REGISTRO_MERMA, afectados=[fila], detalle={}
                )
                return resultado

        return operacion

    def test_regla_concretar_dos_veces_la_orden_una_gana_y_la_otra_se_rechaza(self):
        """Garantía «una orden de transición se concreta una única vez» (sin restricción de base): dos concreciones de la misma orden
        (dos pestañas del Capataz) no pasan las dos. La segunda espera, relee la orden ya «concretada» y se rechaza con
        `orden_no_pendiente`, sin tocar el lote por segunda vez."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(), self.concretar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["orden_no_pendiente"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="concrecion_transicion").count(), 1)
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 50)

    def test_regla_concretar_contra_cancelar_gana_la_primera_y_la_otra_ve_el_estado_actual(self):
        """Requisito especial: «que una orden se concrete y se cancele al mismo tiempo» no pasa. Con la concreción primero, la
        cancelación espera, relee y se rechaza (`orden_no_pendiente`); con la cancelación primero, la concreción se rechaza igual
        (extensión 13b) y el lote conserva su etapa."""
        self.armar()
        cancelar = lambda: ordenes.cancelar_orden(self.e.agronomo, self.orden.pk, "Ya no hace falta")
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(), cancelar, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["orden_no_pendiente"])
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "concretada")

    def test_regla_cancelar_primero_la_concrecion_se_rechaza_y_el_lote_conserva_su_etapa(self):
        """Extensión 13b: si el Agrónomo cancela mientras el Capataz carga los datos, la concreción no registra nada e informa el
        estado actual de la orden."""
        self.armar()
        cancelar = lambda: ordenes.cancelar_orden(self.e.agronomo, self.orden.pk, "Ya no hace falta")
        exitos, rechazos, otros = separar(correr_a_la_vez(cancelar, self.concretar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["orden_no_pendiente"])
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "cancelada")
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).etapa_id, self.lote.etapa_id)

    def test_ext_13c_concretar_contra_una_merma_que_cambia_la_cantidad_la_concrecion_pide_volver_a_cargar(self):
        """Extensión 13c y «el control de concurrencia impide que se concrete sobre una cantidad del lote que cambió mientras tanto»:
        con la merma primera (el Capataz había visto 50 plantas), la concreción espera el invernadero, relee el lote con 45 y se rechaza
        con `cambio_simultaneo` (nueva cantidad y propuesta); no registra nada."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.merma(5), self.concretar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(rechazos[0].datos["cantidad_actual"], 45)
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "a_realizar")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="concrecion_transicion").count(), 0)

    def test_ext_13c_con_la_concrecion_primera_la_merma_espera_y_se_aplica_al_lote_ya_trasladado(self):
        """Con la concreción primera, la merma espera el invernadero y se aplica después, sobre el lote ya en su etapa nueva: las dos
        pasan y la merma queda en la etapa destino."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(), self.merma(5), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        lote = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual((lote.cantidad_actual, lote.etapa_id), (45, self.orden.etapa_destino_id))
        self.assertEqual(Merma.objects.get().etapa_id, self.orden.etapa_destino_id)

    def test_pre_d_concretar_contra_la_baja_del_sector_destino_la_baja_espera_y_se_rechaza_porque_ve_las_plantas(self):
        """PROD-BAJ-SCT regla 2: quien carga agujeros bloquea antes el sector; la baja espera a que confirme, cuenta los ocupados
        después de bloquear y se rechaza con `agujeros_ocupados`. El sector sigue activo. (Con la baja primera no hay prueba: mientras
        la orden está «a realizar», la baja ya se rechaza por `agujeros_comprometidos` sin esperar.)"""
        self.armar()
        sector = self.e.sectores["floracion"]
        baja = lambda: api_sectores.baja_sector(self.e.agronomo, sector.pk)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(), baja, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("agujeros_ocupados", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(SectorProduccion.objects.get(pk=sector.pk).estado_sector, "activo")


@tag("concurrencia")
class ConcretarTransicionAsientoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """CON-04a · el asiento de la merma de una transición bloquea el ejercicio AL FINAL (D-86 punto 2) y NUNCA rechaza por la fecha (D-102). La
    merma lleva la fecha EFECTIVA de la transición, que puede caer en el ejercicio que se está cerrando."""

    def armar(self):
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase vacía el plan en cada prueba
        self.e = invernadero_con_produccion(geografia_propia=True)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")

    def con_ejercicios(self):
        """El ejercicio en cierre cubre desde hace 400 días hasta hace unos 36; el abierto empieza hace 20 días y contiene a hoy."""
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, timezone.localdate() - timedelta(days=400))
        self.abierto = ejercicio_abierto(timezone.localdate() - timedelta(days=20))

    def cierre(self):
        return lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

    def sin_errores(self, resultados):
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])

    def lote_y_orden(self, escenario=None, dias_en_etapa=45):
        e = escenario or self.e
        lote = lote_con_ciclo(e, cantidad=50, dias_en_etapa=dias_en_etapa)
        return lote, orden_de_transicion(e, lote)

    def concretar(self, orden, lote, escenario=None, dias_atras=38):
        """Concreta con una merma de 10 plantas (40 ubicadas) y fecha efectiva de hace `dias_atras` días."""
        e = escenario or self.e
        destino = e.sectores["floracion"]
        datos = datos_de_concrecion(
            fecha_efectiva=timezone.localdate() - timedelta(days=dias_atras), cantidades=((destino.pk, 40),), causa="plaga", cantidad=lote.cantidad_actual
        )
        return lambda: transiciones.concretar_transicion(e.capataz, orden.pk, datos)

    def test_d102_el_cierre_primero_y_concretar_con_fecha_en_el_ejercicio_en_cierre_espera_y_el_asiento_va_al_abierto_con_la_aclaracion(self):
        """La transición tiene fecha efectiva dentro del ejercicio en cierre. El cierre tiene esa fila tomada; la concreción espera, la relee ya
        «cerrada», elige de nuevo y el asiento de la merma va al abierto, con la fecha de hoy y la aclaración de la fecha real. Ninguno falla."""
        self.armar()
        self.con_ejercicios()
        lote, orden = self.lote_y_orden()
        resultados = correr_a_la_vez(self.cierre(), self.concretar(orden, lote), primera="a")
        self.sin_errores(resultados)
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento), (self.abierto.pk, timezone.localdate()))
        self.assertIn("Fecha del hecho", asiento.descripcion_asiento)
        self.assertEqual(TransicionEtapa.objects.get(pk=orden.pk).estado_orden, "concretada")
        verificar_invariantes_contables()

    def test_d102_concretar_primero_con_fecha_en_el_ejercicio_en_cierre_y_el_cierre_a_la_vez_el_asiento_queda_en_el_ejercicio_en_cierre(self):
        """La concreción ya creó el asiento en el ejercicio en cierre (tiene su fila tomada); el cierre espera y cierra el ejercicio con ese asiento
        adentro. Los dos terminan bien."""
        self.armar()
        self.con_ejercicios()
        lote, orden = self.lote_y_orden()
        resultados = correr_a_la_vez(self.concretar(orden, lote), self.cierre(), primera="a")
        self.sin_errores(resultados)
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento), (self.en_cierre.pk, 1))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        verificar_invariantes_contables()

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_la_concrecion_con_merma_bloquea(self):
        """D-86 punto 2: la concreción A (invernadero Norte) se detiene justo ANTES de bloquear el ejercicio; la B (otro invernadero) asienta completa
        y toma el N.º 1. Si A hubiera bloqueado el ejercicio antes que sus filas, B esperaría y el orden sería el inverso."""
        self.armar()
        ejercicio_abierto(timezone.localdate() - timedelta(days=60))
        otro = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="b", geografia_propia=True)
        lote_a, orden_a = self.lote_y_orden(dias_en_etapa=5)
        lote_b, orden_b = self.lote_y_orden(otro, dias_en_etapa=5)
        resultados = correr_a_la_vez(
            self.concretar(orden_a, lote_a, dias_atras=0),
            self.concretar(orden_b, lote_b, otro, dias_atras=0),
            primera="a",
            detener_antes_de=(asientos, "_bloquear_ejercicio"),
        )
        self.sin_errores(resultados)
        numero = lambda orden: AsientoContable.objects.get(origen__bitacora__merma__lote=orden.lote_id).numero_asiento
        self.assertEqual((numero(orden_b), numero(orden_a)), (1, 2))
        verificar_invariantes_contables()
