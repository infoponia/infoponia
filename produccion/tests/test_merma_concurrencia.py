# Pruebas de concurrencia de Registrar Merma (PRD-03, paso 3; docs/patrones/bloqueos.md, sección `produccion`, «Lote 5»; docs/casos_de_uso/
# produccion/merma.md, «Requisitos especiales»: «el control de concurrencia impide que dos mermas, o una merma y una cosecha simultáneas,
# dejen a un lote con cantidad negativa»). Orden de bloqueos de la merma de un lote: cuentas → invernadero → variedad → sectores con pérdidas →
# lote → ocupaciones.
#
# Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Son ``TransactionTestCase``: su ``flush`` vacía todas
# las tablas al terminar, así que cada prueba arma su invernadero con geografía propia y vuelve a asegurar los datos
# (docs/patrones/datos_de_migracion.md). Un rechazo es un ``ErrorDeProduccion``: nunca un 500.
# Fuera de esta tarea: «merma contra poner el sector fuera de servicio» necesita PRD-04 (queda para esa tarea).

from django.test import TransactionTestCase, tag

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador
from core.tests.fabricas import crear_cuenta

from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, perezoso
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Lote, Merma, OcupacionSector, TransicionEtapa
from produccion.servicios import transiciones
from produccion.tests.fabricas import codigos_del_rechazo, invernadero_con_produccion, lote_con_ciclo, orden_de_transicion, separar
from produccion.tests.test_prod_cnc_trn import datos as datos_de_concrecion
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

mermas = perezoso("produccion.servicios.mermas")


@tag("concurrencia")
class RegistrarMermaConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self, cantidad=10):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # CON-04a: registrar una merma asienta; el flush de la prueba anterior vació el plan
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento; el flush de esta TransactionTestCase lo vacía en cada prueba
        self.e = invernadero_con_produccion(geografia_propia=True)
        self.lote = lote_con_ciclo(self.e, cantidad=cantidad)
        self.sector = self.e.sectores["crecimiento"]

    def merma(self, plantas, *, viendo=None, actor=None):
        """Una merma de `plantas` del sector de crecimiento. `viendo` es la cantidad actual que la persona vio (extensión 10d)."""
        datos = mermas.DatosDeMerma(
            lote_id=self.lote.pk,
            cantidades=((self.sector.pk, plantas),),
            causa="plaga",
            cantidad_actual=viendo,
            ocupados=None if viendo is None else ((self.sector.pk, viendo),),
        )
        return lambda: mermas.registrar_merma(actor or self.e.capataz, datos)

    def test_regla_dos_mermas_a_la_vez_sobre_el_mismo_lote_nunca_lo_dejan_negativo_la_segunda_pide_volver_a_cargar(self):
        """Requisito especial y extensión 10d: un lote de 10 plantas y dos mermas de 6 (las dos vieron 10). La segunda espera el
        invernadero, relee el lote con 4 y se rechaza con `cambio_simultaneo` informando la cantidad vigente; el lote queda en 4."""
        self.armar(10)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.merma(6, viendo=10), self.merma(6, viendo=10), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(rechazos[0].datos["cantidad_actual"], 4)
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 4)
        self.assertEqual(Merma.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_merma").count(), 1)

    def test_regla_dos_mermas_a_la_vez_sin_lo_visto_la_segunda_se_rechaza_por_cantidad_y_el_lote_no_queda_negativo(self):
        """Requisito especial: aunque la segunda no informe lo que vio, relee bajo el bloqueo y se rechaza con `cantidad_invalida`
        (6 supera los 4 agujeros ocupados que quedan): nunca un lote negativo ni un 500."""
        self.armar(10)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.merma(6), self.merma(6), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cantidad_invalida"])
        lote = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual(lote.cantidad_actual, 4)
        self.assertEqual(OcupacionSector.objects.get(lote=lote, cant_agujeros_ocupados__gt=0).cant_agujeros_ocupados, 4)

    def test_regla_dos_mermas_que_caben_las_dos_pasan_en_serie(self):
        """Dos mermas de 3 sobre un lote de 10 caben las dos: la segunda espera, relee y se aplica sobre 7 sin conflicto (no vieron nada)."""
        self.armar(10)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.merma(3), self.merma(3), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 4)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_merma").count(), 2)

    def test_ext_10d_una_merma_contra_concretar_la_transicion_la_merma_primera_hace_que_la_concrecion_pida_volver_a_cargar(self):
        """«Una merma y una transición» (requisito especial; extensión 13c de PROD-CNC-TRN): con la merma primera la concreción relee el
        lote con 45 plantas y se rechaza con `cambio_simultaneo`; la orden sigue «a realizar»."""
        self.armar(50)
        orden = orden_de_transicion(self.e, self.lote)
        concretar = lambda: transiciones.concretar_transicion(
            self.e.capataz, orden.pk, datos_de_concrecion(cantidad=self.lote.cantidad_actual)
        )
        exitos, rechazos, otros = separar(correr_a_la_vez(self.merma(5, viendo=50), concretar, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(rechazos[0].datos["cantidad_actual"], 45)
        self.assertEqual(TransicionEtapa.objects.get(pk=orden.pk).estado_orden, "a_realizar")

    def test_ext_10d_una_merma_contra_concretar_la_transicion_la_concrecion_primera_hace_que_la_merma_vea_los_sectores_nuevos(self):
        """Extensión 10d: con la concreción primera, los agujeros del sector de origen pasan a 0 (las plantas se mudaron al sector destino) y
        la merma, que había visto 50 ocupados ahí, se rechaza con `cambio_simultaneo` informando lo vigente; no registra nada."""
        self.armar(50)
        orden = orden_de_transicion(self.e, self.lote)
        concretar = lambda: transiciones.concretar_transicion(
            self.e.capataz, orden.pk, datos_de_concrecion(cantidad=self.lote.cantidad_actual)
        )
        exitos, rechazos, otros = separar(correr_a_la_vez(concretar, self.merma(5, viendo=50), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cambio_simultaneo"])
        destino = OcupacionSector.objects.get(orden_id=orden.pk).sector_id
        self.assertEqual(rechazos[0].datos["ocupados"], {destino: 50})
        self.assertFalse(Merma.objects.exists())
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 50)


@tag("concurrencia")
class RegistrarMermaAsientoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """CON-04a · el asiento de la merma bloquea el ejercicio AL FINAL (D-86 punto 2) y NUNCA rechaza por la fecha (D-102): una merma que se cruza con
    el cierre del ejercicio no falla y su asiento queda en el ejercicio que corresponde. La merma de un lote siempre lleva la fecha de hoy."""

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

    def merma(self, lote, escenario=None, plantas=3):
        e = escenario or self.e
        datos = mermas.DatosDeMerma(lote_id=lote.pk, cantidades=((e.sectores["crecimiento"].pk, plantas),), causa="plaga")
        return lambda: mermas.registrar_merma(e.capataz, datos)

    def test_d102_el_cierre_primero_y_la_merma_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """El cierre del ejercicio en cierre tiene su fila tomada (sin confirmar); la merma de hoy no la necesita: termina bien con el asiento N.º 1
        del ejercicio abierto. El ejercicio en cierre queda cerrado y sin asientos."""
        self.armar()
        self.con_ejercicios()
        lote = lote_con_ciclo(self.e, cantidad=10)
        resultados = correr_a_la_vez(self.cierre(), self.merma(lote), primera="a")
        self.sin_errores(resultados)
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento, asiento.fecha_asiento), (self.abierto.pk, 1, timezone.localdate()))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        verificar_invariantes_contables()

    def test_d102_la_merma_primero_y_el_cierre_a_la_vez_los_dos_terminan_y_el_asiento_queda_en_el_abierto(self):
        """La merma ya creó su asiento y tiene el ejercicio abierto bloqueado (sin confirmar); el cierre toca solo su fila y termina."""
        self.armar()
        self.con_ejercicios()
        lote = lote_con_ciclo(self.e, cantidad=10)
        resultados = correr_a_la_vez(self.merma(lote), self.cierre(), primera="a")
        self.sin_errores(resultados)
        self.assertEqual(AsientoContable.objects.get().ejercicio_id, self.abierto.pk)
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        verificar_invariantes_contables()

    def test_regla_h8_dos_mermas_a_la_vez_toman_numeros_consecutivos_sin_hueco(self):
        """H8: dos mermas de un mismo lote a la vez (se serializan por el invernadero) asientan con los números 1 y 2."""
        self.armar()
        ejercicio_abierto(timezone.localdate() - timedelta(days=20))
        lote = lote_con_ciclo(self.e, cantidad=10)
        resultados = correr_a_la_vez(self.merma(lote), self.merma(lote), primera="a")
        self.sin_errores(resultados)
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2])
        self.assertEqual(AsientoContable.objects.get(origen_id=resultados["a"].pk).numero_asiento, 1)  # la primera tomó el ejercicio antes
        verificar_invariantes_contables()

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_la_merma_bloquea(self):
        """D-86 punto 2: la merma A (invernadero Norte) se detiene justo ANTES de bloquear el ejercicio, con el invernadero, el lote y los sectores ya
        tomados; la merma B (otro invernadero, sin ninguna fila en común) asienta completa y toma el N.º 1. Si A hubiera bloqueado el ejercicio
        antes, B esperaría y el orden sería el inverso."""
        self.armar()
        ejercicio_abierto(timezone.localdate() - timedelta(days=20))
        otro = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="b", geografia_propia=True)
        lote_a, lote_b = lote_con_ciclo(self.e, cantidad=10), lote_con_ciclo(otro, cantidad=10)
        resultados = correr_a_la_vez(
            self.merma(lote_a), self.merma(lote_b, escenario=otro), primera="a", detener_antes_de=(asientos, "_bloquear_ejercicio")
        )
        self.sin_errores(resultados)
        numero = lambda merma: AsientoContable.objects.get(origen_id=merma.pk).numero_asiento
        self.assertEqual((numero(resultados["b"]), numero(resultados["a"])), (1, 2))
        verificar_invariantes_contables()
