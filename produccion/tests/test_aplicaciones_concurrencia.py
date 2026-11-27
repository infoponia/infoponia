# Pruebas de concurrencia de Registrar Aplicación de Insumos (PRD-03, paso 4; docs/patrones/bloqueos.md, sección `produccion`, «Lote 5»;
# docs/casos_de_uso/produccion/aplicacion_de_insumos.md, «Requisitos especiales»: «el control de concurrencia impide que dos consumos simultáneos descuenten
# dos veces lo mismo de un lote de insumo, o que un consumo y un ajuste dejen un lote con cantidad negativa»).
# Orden de bloqueos de la aplicación: cuentas → invernadero → sectores del alcance → TipoInsumo → Insumo → InsumoInvernadero → LoteInsumo → lotes de plantas.
#
# Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Son ``TransactionTestCase``: su ``flush`` vacía todas las tablas al
# terminar, así que cada prueba arma sus datos con geografía propia y vuelve a asegurar los datos (docs/patrones/datos_de_migracion.md). Un rechazo es un
# ``ErrorDeProduccion`` o un error de negocio de otra app: nunca un 500.

from datetime import timedelta
from decimal import Decimal

from django.test import TransactionTestCase, tag
from django.utils import timezone

from core.models import RegistroAuditoria
from django.core.cache import cache

from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador
from core.tests.fabricas import crear_cuenta
from core.tests.concurrencia import correr_a_la_vez
from inventario.models import LoteInsumo, TipoInsumo
from inventario.servicios import ajustes
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, existencia, insumo, lote as lote_de_insumo, perezoso, tipo_de_insumo
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import AplicacionInsumos, Consumo, Lote
from produccion.servicios import siembras
from produccion.tests.fabricas import (
    codigos_del_rechazo,
    insumo_adicional,
    invernadero_con_produccion,
    lote_activo,
    orden_de_siembra,
    reservar,
    separar,
)
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

aplicaciones = perezoso("produccion.servicios.aplicaciones")
mermas = perezoso("produccion.servicios.mermas")

D = Decimal
HOY = timezone.localdate()


@tag("concurrencia")
class AplicarConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self, stock="10"):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()  # el flush de la prueba anterior vació los tipos de etapa y las categorías
        asegurar_plan_de_cuentas()  # CON-04a: concretar una siembra asienta (y, desde el paso 3, también la aplicación)
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento; el flush de esta TransactionTestCase lo vacía en cada prueba
        self.e = invernadero_con_produccion(geografia_propia=True)
        self.lote_de_plantas = lote_activo(self.e, cantidad=50, sector="germinacion", costo="100.00")
        tipo = TipoInsumo.objects.filter(nombre_tipo_insumo="Cat costo").first() or tipo_de_insumo("Cat costo", consumo="como_costo_de_los_lotes")
        self.abono = existencia(insumo("Abono", tipo=tipo, unidad="kg"), self.e.invernadero, precio="4.00")
        self.lote_de_abono = lote_de_insumo(self.abono, stock, vence=HOY + timedelta(days=100))

    def aplicar(self, cantidad, actor=None, **cambios):
        datos = aplicaciones.DatosDeAplicacion(
            invernadero_id=self.e.invernadero.pk, lineas=(aplicaciones.LineaDeAplicacion(self.abono.pk, str(cantidad)),), **cambios
        )
        return lambda: aplicaciones.registrar_aplicacion(actor or self.e.capataz, datos)

    def test_regla_dos_aplicaciones_sobre_el_mismo_lote_de_insumo_no_descuentan_dos_veces_lo_mismo(self):
        """Requisito especial: un lote de 10 kg y dos aplicaciones de 8 kg a la vez. No se limita al stock (el hecho ya ocurrió): las dos pasan, la segunda espera
        el bloqueo del lote, lo relee en 2 y manda los 6 que faltan al faltante sin lote. Nunca un lote común negativo y el total descontado es 16."""
        self.armar("10")
        exitos, rechazos, otros = separar(correr_a_la_vez(self.aplicar(8), self.aplicar(8), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(LoteInsumo.objects.get(pk=self.lote_de_abono.pk).cantidad_disponible, D("0"))
        faltante = LoteInsumo.objects.get(insumo_invernadero=self.abono, es_faltante_sin_lote=True)
        self.assertEqual(faltante.cantidad_disponible, D("-6"))
        self.assertEqual(AplicacionInsumos.objects.count(), 2)
        self.assertEqual(Consumo.objects.count(), 2)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_aplicacion").count(), 2)
        # El costo de los 2 consumos (32,00 cada uno) llegó al único lote de plantas, exacto.
        self.assertEqual(Lote.objects.get(pk=self.lote_de_plantas.pk).costo_acumulado, D("164.00"))

    def test_regla_una_aplicacion_contra_un_ajuste_de_stock_el_ajuste_desactualizado_no_deja_el_lote_negativo(self):
        """Requisito especial: «un consumo y un ajuste dejan un lote con cantidad negativa» no pasa. El Agrónomo calcula una rotura de 6 kg sobre el lote (huella
        con 10 disponibles); la aplicación de 8 kg confirma primero; el ajuste espera, relee y se rechaza como desactualizado (extensión 14a): el lote queda en 2."""
        self.armar("10")
        entrada = {"lote_id": self.lote_de_abono.pk, "cantidad": "6"}
        huella = ajustes.calcular_ajuste(self.e.agronomo, self.e.invernadero.pk, self.abono.insumo_id, "rotura_o_perdida", entrada).huella
        ajustar = lambda: ajustes.confirmar_ajuste(
            self.e.agronomo, self.e.invernadero.pk, self.abono.insumo_id, "rotura_o_perdida", entrada, huella
        )
        resultados = correr_a_la_vez(self.aplicar(8), ajustar, primera="a")
        self.assertNotIsInstance(resultados["a"], Exception)
        self.assertIsInstance(resultados["b"], ajustes.AjusteDesactualizado)
        self.assertEqual(LoteInsumo.objects.get(pk=self.lote_de_abono.pk).cantidad_disponible, D("2"))

    def test_regla_una_aplicacion_contra_una_merma_que_cambia_las_plantas_del_alcance_pide_volver_a_cargar(self):
        """Extensión 12a: la persona vio 50 plantas en el lote del alcance; una merma de 5 confirma primero; la aplicación espera, relee 45 y se rechaza con
        `cambio_simultaneo`, sin registrar nada. (Una merma toma el invernadero y el lote; la aplicación, sectores, insumos y lotes: orden consistente.)"""
        self.armar("10")
        merma = mermas.DatosDeMerma(
            lote_id=self.lote_de_plantas.pk, cantidades=((self.e.sectores["germinacion"].pk, 5),), causa="plaga"
        )
        merma_primero = lambda: mermas.registrar_merma(self.e.capataz, merma)
        aplicar = self.aplicar(2, plantas_vistas=((self.lote_de_plantas.pk, 50),))
        exitos, rechazos, otros = separar(correr_a_la_vez(merma_primero, aplicar, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(AplicacionInsumos.objects.count(), 0)
        self.assertEqual(LoteInsumo.objects.get(pk=self.lote_de_abono.pk).cantidad_disponible, D("10"))

    def test_regla_una_aplicacion_contra_concretar_una_siembra_del_mismo_insumo_pasan_las_dos_sin_trabarse(self):
        """Orden de bloqueos (stock.md, sección 5; corrección de PRD-03 en `siembras.py`): una aplicación y la concreción de una siembra que consume el mismo
        insumo toman TipoInsumo → Insumo → InsumoInvernadero → lotes en el mismo orden: las dos pasan, sin deadlock ni 500."""
        self.armar("30")
        siembra = orden_de_siembra(self.e, plantines=20, sector="crecimiento")
        reservar(siembra, self.abono, "5")
        concretar = lambda: siembras.concretar_siembra(self.e.capataz, siembra.pk, siembras.DatosDeConcrecion())
        exitos, rechazos, otros = separar(correr_a_la_vez(self.aplicar(8), concretar, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(LoteInsumo.objects.get(pk=self.lote_de_abono.pk).cantidad_disponible, D("17"))


@tag("concurrencia")
class AplicarAsientoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """CON-04a · el asiento de cada consumo bloquea el ejercicio AL FINAL (D-86 punto 2) y NUNCA rechaza por la fecha (D-102). La aplicación siempre
    lleva la fecha de hoy. Las fechas del escenario son relativas a hoy porque el servicio toma «hoy» del reloj."""

    def armar(self):
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase vacía el plan en cada prueba
        self.e = invernadero_con_produccion(geografia_propia=True)
        lote_activo(self.e, cantidad=50, sector="germinacion", costo="100.00")
        self.abono = insumo_adicional(self.e, nombre="Abono", stock=100)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")

    def con_ejercicios(self):
        """El ejercicio en cierre cubre desde hace 400 días hasta hace unos 36; el abierto empieza hace 20 días y contiene a hoy."""
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, timezone.localdate() - timedelta(days=400))
        self.abierto = ejercicio_abierto(timezone.localdate() - timedelta(days=20))

    def aplicar_en(self, escenario, habilitado, cantidad=5):
        datos = aplicaciones.DatosDeAplicacion(
            invernadero_id=escenario.invernadero.pk, lineas=(aplicaciones.LineaDeAplicacion(habilitado.pk, str(cantidad)),)
        )
        return lambda: aplicaciones.registrar_aplicacion(escenario.capataz, datos)

    def cierre(self):
        return lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

    def sin_errores(self, resultados):
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])

    def asiento_de(self, resultado):
        return AsientoContable.objects.get(origen__bitacora__consumo__aplicacion=resultado.aplicacion)

    def test_d102_el_cierre_primero_y_la_aplicacion_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """El cierre tiene su fila tomada (sin confirmar); la aplicación de hoy no la necesita: termina bien con el asiento N.º 1 del ejercicio abierto."""
        self.armar()
        self.con_ejercicios()
        resultados = correr_a_la_vez(self.cierre(), self.aplicar_en(self.e, self.abono), primera="a")
        self.sin_errores(resultados)
        asiento = self.asiento_de(resultados["b"])
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento, asiento.fecha_asiento), (self.abierto.pk, 1, timezone.localdate()))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        verificar_invariantes_contables()

    def test_d102_la_aplicacion_primero_y_el_cierre_a_la_vez_los_dos_terminan_y_el_asiento_queda_en_el_abierto(self):
        """La aplicación ya creó su asiento y tiene el ejercicio abierto bloqueado (sin confirmar); el cierre toca solo su fila y termina."""
        self.armar()
        self.con_ejercicios()
        resultados = correr_a_la_vez(self.aplicar_en(self.e, self.abono), self.cierre(), primera="a")
        self.sin_errores(resultados)
        self.assertEqual(self.asiento_de(resultados["a"]).ejercicio_id, self.abierto.pk)
        verificar_invariantes_contables()

    def test_regla_h8_dos_aplicaciones_a_la_vez_toman_numeros_consecutivos_sin_hueco(self):
        """H8: dos aplicaciones a la vez (se serializan por el invernadero) asientan con los números 1 y 2."""
        self.armar()
        ejercicio_abierto(timezone.localdate() - timedelta(days=20))
        resultados = correr_a_la_vez(self.aplicar_en(self.e, self.abono), self.aplicar_en(self.e, self.abono), primera="a")
        self.sin_errores(resultados)
        self.assertEqual(self.asiento_de(resultados["a"]).numero_asiento, 1)  # la primera tomó el ejercicio antes
        self.assertEqual(self.asiento_de(resultados["b"]).numero_asiento, 2)
        verificar_invariantes_contables()

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_la_aplicacion_bloquea(self):
        """D-86 punto 2: la aplicación A (invernadero Norte) se detiene justo ANTES de bloquear el ejercicio, con todos sus bloqueos de producción y de
        inventario tomados; la B (otro invernadero, sin filas en común) asienta completa y toma el N.º 1. Si A hubiera bloqueado el ejercicio antes, B
        esperaría y el orden sería el inverso."""
        self.armar()
        ejercicio_abierto(timezone.localdate() - timedelta(days=20))
        otro = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="b", geografia_propia=True)
        lote_activo(otro, cantidad=50, sector="germinacion", costo="100.00")
        # Un tipo de insumo propio: la aplicación bloquea el `TipoInsumo`, y compartirlo con el otro invernadero las serializaría por esa fila.
        tipo_b = tipo_de_insumo("Cat costo B", consumo="como_costo_de_los_lotes")
        abono_b = existencia(insumo("Abono B", tipo=tipo_b, unidad="kg"), otro.invernadero, precio="4.00")
        lote_de_insumo(abono_b, 100, vence=HOY + timedelta(days=100))
        resultados = correr_a_la_vez(
            self.aplicar_en(self.e, self.abono), self.aplicar_en(otro, abono_b), primera="a", detener_antes_de=(asientos, "_bloquear_ejercicio")
        )
        self.sin_errores(resultados)
        self.assertEqual((self.asiento_de(resultados["b"]).numero_asiento, self.asiento_de(resultados["a"]).numero_asiento), (1, 2))
        verificar_invariantes_contables()
