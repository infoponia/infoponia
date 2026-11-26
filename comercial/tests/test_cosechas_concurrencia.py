# Pruebas de concurrencia de las cosechas (COM-04a, pasos 4 y 5; docs/patrones/bloqueos.md, sección `comercial`, «Cosecha y cámara», y
# docs/patrones/stock_maduro.md, sección 3): dos planificaciones por el último stock de un lote; una planificación contra una compra-venta; modificar contra
# concretar; concretar contra cancelar; dos concreciones de la misma orden; concretar contra una venta que toma el stock libre del lote. Dos hilos, dos
# conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Cada una termina verificando los invariantes de las reservas. Nunca un error 500:
# el que pierde recibe un rechazo claro (`ValidationError`). Las ventas se hacen con retiro (sin Georef: el `flush` de estas pruebas vacía las tablas).
# El bloqueo que las ordena: cuentas → invernaderos → variedades → sectores → lotes → partidas → contrato → detalles → la cosecha (`OrdenTrabajo`) →
# su reserva y sus líneas.

from datetime import timedelta

from django.core.cache import cache
from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva
from comercial.servicios import compra_ventas, cosechas
from comercial.servicios.compra_ventas import DatosDeCompraVenta, Renglon
from comercial.servicios.cosechas import DatosDeCosecha, DatosDeConcrecion, DatosDeModificacion
from comercial.tests.fabricas import compra_venta, cosecha_manual, detalle, escenario_comercial, verificar_invariantes_de_reservas
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_cuenta
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Cosecha, Lote, MovimientoStock
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar

HOY = timezone.localdate()


def en(dias):
    """La fecha de dentro de ``dias`` días."""
    return HOY + timedelta(days=dias)


@tag("concurrencia")
class CosechasConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self, plantas=100, reservadas=30):
        """El escenario sin Georef, un lote de `plantas` y una cosecha con contrato (venta con retiro de 50) que reserva `reservadas`."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # CON-04c: concretar una cosecha asienta; el flush de la prueba anterior vació el plan
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, plantas)
        self.sector = self.e.sectores["maduracion"]
        self.venta = compra_venta(self.e, dias=10, modalidad="retiro", retiro=self.e.invernadero)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.cosecha = cosecha_manual(self.e, [(self.lote, reservadas)], detalle_=self.detalle, dias=5) if reservadas else None
        self.addCleanup(verificar_invariantes_de_reservas)

    # ---- las operaciones ----

    def planificar(self, plantas, dias=5):
        """Planifica, como el Agrónomo, una cosecha SIN contrato de `plantas` del lote."""
        datos = DatosDeCosecha(
            invernadero_id=self.e.invernadero.pk, variedad_id=self.e.variedad.pk, fecha_programada=en(dias), prioridad="media", lotes=((self.lote.pk, plantas),)
        )
        return lambda: cosechas.planificar_cosecha(self.e.agronomo, datos)

    def vender(self, cantidad):
        """Registra, como el Vendedor, una compra-venta con retiro de `cantidad` plantas."""
        datos = DatosDeCompraVenta(
            cliente_id=str(self.e.cliente.pk),
            fecha_pactada=str(en(3)),
            modalidad="retiro",
            invernadero_id=str(self.e.invernadero.pk),
            renglones=[Renglon(0, str(self.e.variedad.pk), str(cantidad), "100")],
        )
        return lambda: compra_ventas.registrar_compra_venta(self.e.vendedor, datos)

    def concretar(self, plantas):
        """Concreta la cosecha, como su Capataz, cosechando `plantas` del lote."""
        datos = DatosDeConcrecion(cantidades=((self.lote.pk, self.sector.pk, plantas),))
        return lambda: cosechas.concretar_cosecha(self.e.capataz, self.cosecha.pk, datos)

    def modificar(self, huella, **cambios):
        """Modifica la cosecha, como el Agrónomo (con la huella que leyó al abrirla)."""
        valores = dict(fecha_programada=en(5), prioridad="media", descripcion="", lotes=((self.lote.pk, 30),))
        valores.update(cambios)
        datos = DatosDeModificacion(**valores)
        return lambda: cosechas.modificar_cosecha(self.e.agronomo, self.cosecha.pk, datos, huella)

    def cancelar(self, huella):
        """Cancela la cosecha, como el Agrónomo."""
        return lambda: cosechas.cancelar_cosecha(self.e.agronomo, self.cosecha.pk, "Se cancela", huella)

    def releer(self):
        return Cosecha.objects.get(pk=self.cosecha.pk)

    # ---- planificar ----

    def test_regla_dos_planificaciones_por_el_ultimo_stock_de_un_lote_una_registra_y_la_otra_no_alcanza(self):
        """PROD-PNF-CSC, concurrencia: un lote de 30 y dos planificaciones de 30 (sin contrato). La segunda espera al lote, relee el stock libre (0) y recibe
        `supera_stock_libre` (15b); el lote nunca queda reservado por encima de su stock libre."""
        self.armar(plantas=30, reservadas=0)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.planificar(30, 5), self.planificar(30, 6), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("supera_stock_libre", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Cosecha.objects.count(), 1)
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(lote=self.lote)), 30)

    def test_regla_una_planificacion_contra_una_compra_venta_por_el_mismo_stock(self):
        """Una planificación de 50 y una venta de 50 sobre un lote de 50: gana la que toma el lote primero, la otra recibe su rechazo (`supera_stock_libre` o
        `stock_insuficiente`); no queda nada reservado de más."""
        self.armar(plantas=50, reservadas=0)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.planificar(50), self.vender(50), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertTrue({"supera_stock_libre", "stock_insuficiente"} & set(codigos_del_rechazo(rechazos[0])))
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(lote=self.lote)), 50)

    # ---- modificar contra concretar ----

    def test_regla_concretar_primero_y_la_modificacion_ve_la_cosecha_resuelta(self):
        """PROD-MOD-CSC 10a: con la concreción primero, la modificación espera la fila de la cosecha, la relee «concretada» y recibe `cosecha_resuelta`: no
        cambia nada de lo concretado."""
        self.armar()
        huella = cosechas.huella_de(self.releer())
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(30), self.modificar(huella, prioridad="alta"), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("cosecha_resuelta", codigos_del_rechazo(rechazos[0]))
        self.assertEqual((self.releer().estado_orden, self.releer().prioridad_orden), ("concretada", "media"))
        self.assertEqual(MovimientoStock.objects.filter(tipo_movimiento="salida_por_cosecha").count(), 1)

    def test_regla_modificar_primero_y_la_concrecion_toma_lo_modificado(self):
        """Con la modificación primero (cambia el lote al otro de 40), la concreción espera, relee las líneas nuevas y las concreta: las dos se registran."""
        self.armar()
        otro = lote_maduro(self.e, 40)
        huella = cosechas.huella_de(self.releer())
        datos = DatosDeConcrecion(cantidades=((otro.pk, self.sector.pk, 30),))
        concretar_el_otro = lambda: cosechas.concretar_cosecha(self.e.capataz, self.cosecha.pk, datos)  # noqa: E731
        exitos, rechazos, otros = separar(correr_a_la_vez(self.modificar(huella, lotes=((otro.pk, 30),)), concretar_el_otro, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Lote.objects.get(pk=otro.pk).cantidad_actual, 10)
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 100)

    # ---- concretar contra cancelar y contra sí misma ----

    def test_regla_concretar_contra_cancelar_gana_el_primero_y_el_otro_ve_el_estado_actual(self):
        """PROD-CNC-CSC 13b y PROD-CNL-ORD 8a: con la concreción primero, la cancelación recibe `orden_no_a_realizar`; con la cancelación primero, la
        concreción. Nunca las dos."""
        self.armar()
        huella = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk).huella
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(30), self.cancelar(huella), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("orden_no_a_realizar", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(self.releer().estado_orden, "concretada")

    def test_regla_cancelar_primero_y_la_concrecion_se_rechaza(self):
        """El orden inverso: la cancelación gana y la concreción recibe `orden_no_a_realizar`; no hay movimientos de stock."""
        self.armar()
        huella = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk).huella
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(huella), self.concretar(30), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("orden_no_a_realizar", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(self.releer().estado_orden, "cancelada")
        self.assertFalse(MovimientoStock.objects.filter(tipo_movimiento="salida_por_cosecha").exists())

    def test_regla_dos_concreciones_de_la_misma_orden_una_sola_se_registra(self):
        """«Una orden de cosecha se concreta una única vez»: la segunda espera, relee y recibe `orden_no_a_realizar`; el lote baja una sola vez."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(30), self.concretar(30), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("orden_no_a_realizar", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 70)

    # ---- concretar contra una venta ----

    def test_regla_una_venta_que_toma_el_stock_libre_primero_y_la_concrecion_ve_el_nuevo_maximo(self):
        """13c: lote de 100, 30 reservados por la cosecha. Con la venta de 70 primero, el máximo de la concreción baja a 30 (+0 libre): cosechar 100 recibe
        `supera_maximo`; la venta queda registrada."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.vender(70), self.concretar(100), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("supera_maximo", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(CompraVenta.objects.exclude(pk=self.venta.pk).count(), 1)
        self.assertEqual(self.releer().estado_orden, "a_realizar")

    def test_regla_una_concrecion_primero_deja_el_excedente_en_la_camara_y_la_venta_lo_toma(self):
        """El orden inverso: con la concreción primero (cosecha 100 de 100 reservadas 30, máximo 100), lo que sobra (70) ingresa a la cámara; la venta espera,
        relee y se cubre con esa partida: las dos se registran y el lote queda sin plantas."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(100), self.vender(70), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(self.releer().estado_orden, "concretada")
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(partida__isnull=False)), 70)
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 0)


@tag("concurrencia")
class ConcretarCosechaAsientoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """CON-04c · paso 1: el asiento de la cosecha bloquea el ejercicio AL FINAL (D-86 punto 2) y NUNCA rechaza por la fecha (D-102). La fecha del asiento
    es la efectiva de la cosecha: una cosecha de hoy no necesita el ejercicio en cierre."""

    def armar(self, **kwargs):
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase vacía el plan en cada prueba
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 100)
        self.sector = self.e.sectores["maduracion"]
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.addCleanup(verificar_invariantes_de_reservas)

    def con_ejercicios(self):
        """El ejercicio en cierre cubre desde hace 400 días hasta hace unos 36; el abierto empieza hace 20 días y contiene a hoy."""
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, HOY - timedelta(days=400))
        self.abierto = ejercicio_abierto(HOY - timedelta(days=20))

    def cierre(self):
        return lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

    def cosecha_de(self, e=None, lote=None, plantas=30):
        """Una cosecha con contrato (venta con retiro de 50) que reserva `plantas` del lote, y lo que la concreta."""
        e = e or self.e
        lote = lote or self.lote
        venta = compra_venta(e, dias=10, modalidad="retiro", retiro=e.invernadero)
        cosecha = cosecha_manual(e, [(lote, plantas)], detalle_=detalle(venta, e.variedad, 50), dias=5)
        datos = DatosDeConcrecion(cantidades=((lote.pk, e.sectores["maduracion"].pk, plantas),))
        return lambda: cosechas.concretar_cosecha(e.capataz, cosecha.pk, datos)

    def sin_errores(self, resultados):
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])

    def test_d102_el_cierre_primero_y_la_cosecha_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """El cierre del ejercicio en cierre tiene su fila tomada (sin confirmar); la cosecha de hoy no la necesita: termina con el asiento N.º 1 del abierto."""
        self.armar()
        self.con_ejercicios()
        resultados = correr_a_la_vez(self.cierre(), self.cosecha_de(), primera="a")
        self.sin_errores(resultados)
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento, asiento.fecha_asiento), (self.abierto.pk, 1, HOY))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        verificar_invariantes_contables()

    def test_d102_la_cosecha_primero_y_el_cierre_a_la_vez_los_dos_terminan_y_el_asiento_queda_en_el_abierto(self):
        """La cosecha ya creó su asiento y tiene el ejercicio abierto bloqueado (sin confirmar); el cierre toca solo su fila y termina."""
        self.armar()
        self.con_ejercicios()
        resultados = correr_a_la_vez(self.cosecha_de(), self.cierre(), primera="a")
        self.sin_errores(resultados)
        self.assertEqual(AsientoContable.objects.get().ejercicio_id, self.abierto.pk)
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        verificar_invariantes_contables()

    def test_regla_h8_dos_cosechas_a_la_vez_toman_numeros_consecutivos_sin_hueco(self):
        """H8: dos cosechas distintas (cada una con su asiento) a la vez toman los números 1 y 2."""
        self.armar()
        ejercicio_abierto(HOY - timedelta(days=20))
        otro = lote_maduro(self.e, 100)
        resultados = correr_a_la_vez(self.cosecha_de(), self.cosecha_de(lote=otro), primera="a")
        self.sin_errores(resultados)
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2])
        verificar_invariantes_contables()

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_la_cosecha_bloquea(self):
        """D-86 punto 2: la cosecha A se detiene justo ANTES de bloquear el ejercicio (con su invernadero, lote y orden ya tomados); la cosecha B (otro
        invernadero, sin filas en común) asienta completa y toma el N.º 1. Si A hubiera bloqueado el ejercicio antes, el orden sería el inverso."""
        self.armar()
        ejercicio_abierto(HOY - timedelta(days=20))
        otro = escenario_comercial(nombre="Invernadero Sur", sufijo="b", email_del_cliente="clienteb@ejemplo.com", geografia_propia=True)
        lote_b = lote_maduro(otro, 100)
        resultados = correr_a_la_vez(
            self.cosecha_de(), self.cosecha_de(e=otro, lote=lote_b), primera="a", detener_antes_de=(asientos, "_bloquear_ejercicio")
        )
        self.sin_errores(resultados)
        self.assertEqual(AsientoContable.objects.count(), 2)
        primero = AsientoContable.objects.get(numero_asiento=1)
        self.assertEqual(primero.origen.movimientostock.lote_id, lote_b.pk)
        verificar_invariantes_contables()
