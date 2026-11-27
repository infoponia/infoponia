# Pruebas de concurrencia de la cámara (COM-04b; docs/patrones/bloqueos.md, «Cosecha y cámara»; docs/patrones/stock_maduro.md, secciones 3 y 8): PROD-ASG-CAM contra una compra-venta que
# toma la misma partida, PROD-VNC-CAM contra una merma en cámara, la merma en cámara contra PROD-ASG-CAM y dos mermas de la misma partida. Todas bloquean en el mismo orden (cuentas →
# invernaderos → variedad → lotes y partidas → contratos → reservas), así que la segunda espera a la primera y ve lo que confirmó. Las operaciones usan retiro (sin Georef: el
# `flush` de estas pruebas vacía las tablas). Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Todas terminan verificando los invariantes de
# reservas. «Merma en cámara contra la decisión del cliente que usa esas reservas» (COM-04c): `test_com_dcd_flt.py`, `ComDcdFltConcurrenciaTests` (comparte el escenario de la decisión).

from datetime import timedelta

from django.core.cache import cache
from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva, ReservaStock
from comercial.servicios import camara, compra_ventas, merma_camara
from comercial.servicios.merma_camara import DatosDeMermaEnCamara
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    escenario_comercial,
    partida,
    reserva,
    verificar_invariantes_de_reservas,
)
from comercial.tests.test_stock_maduro_concurrencia import datos_de_retiro
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_cuenta
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Lote, Merma, StockCosechado
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HOY = timezone.localdate()


@tag("concurrencia")
class CamaraConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Cuatro choques sobre una misma partida."""

    def armar(self, disponible=40, fecha_limite=None):
        """Un invernadero sin stock en pie (su único lote queda finalizado) con una partida de `disponible` plantas."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # CON-04c: la merma en cámara y el vencimiento asientan; el flush vació el plan
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento; el flush de esta TransactionTestCase lo vacía en cada prueba
        self.e = escenario_comercial(geografia_propia=True)
        lote = lote_maduro(self.e, 10)
        self.partida = partida(lote, disponible, fecha_limite=fecha_limite)
        Lote.objects.filter(pk=lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        self.addCleanup(verificar_invariantes_de_reservas)

    def espera(self, cantidad, dias=3):
        """Un detalle de una compra-venta con retiro, «abierto», sin reservas: lo que espera stock de la cámara."""
        return detalle(compra_venta(self.e, dias=dias, modalidad="retiro", retiro=self.e.invernadero), self.e.variedad, cantidad)

    def vender(self, cantidad):
        """Una operación que registra una venta con retiro de `cantidad` plantas."""
        datos = datos_de_retiro(self.e, self.e.invernadero, cantidad)
        return lambda: compra_ventas.registrar_compra_venta(self.e.vendedor, datos)

    def asignar(self):
        """Una operación que corre PROD-ASG-CAM sobre la partida."""
        return lambda: camara.asignar_camara([self.partida.pk], HOY)

    def mermar(self, cantidad, actor=None):
        """Una operación que registra una merma en cámara de `cantidad` plantas de la partida."""
        datos = DatosDeMermaEnCamara(self.partida.pk, cantidad, "dano_en_camara")
        return lambda: merma_camara.registrar_merma_en_camara(actor or self.e.agronomo, datos)

    def reservado(self):
        """Lo reservado de la partida en reservas que la ocupan."""
        return sum(
            DetalleReserva.objects.filter(partida=self.partida, reserva__estado_reserva__in=("activa", "lista_para_entrega")).values_list("cantidad_reservada", flat=True)
        )

    def test_regla_asignar_camara_primero_y_la_venta_ve_la_partida_ya_reservada(self):
        """Requisito especial de PROD-ASG-CAM y sección 3 del patrón: con la asignación primero, la venta de 40 espera, relee la partida con 0 libres y recibe `stock_insuficiente`;
        la partida nunca queda reservada por encima de su disponible."""
        self.armar(40)
        espera = self.espera(40)
        resultados = correr_a_la_vez(self.asignar(), self.vender(40), primera="a")
        asignacion, venta = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(asignacion[0]), asignacion[2], venta[2]), (1, [], []))
        self.assertIn("stock_insuficiente", codigos_del_rechazo(venta[1][0]))
        self.assertEqual(self.reservado(), 40)
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=espera).count(), 1)
        self.assertEqual(CompraVenta.objects.filter(detalles__isnull=False).distinct().count(), 1)  # solo la que esperaba

    def test_regla_la_venta_primero_y_la_asignacion_no_encuentra_stock_libre(self):
        """Con la venta primero toma la partida; la asignación, que esperaba, relee y no tiene stock libre (extensión 2a): no reserva nada de más."""
        self.armar(40)
        espera = self.espera(40)
        resultados = correr_a_la_vez(self.vender(40), self.asignar(), primera="a")
        venta, asignacion = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(venta[0]), venta[2], asignacion[2]), (1, [], []))
        self.assertEqual(asignacion[0], [[]])
        self.assertEqual(self.reservado(), 40)
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=espera).count(), 0)

    def test_regla_la_merma_primero_y_el_vencimiento_no_la_cuenta_dos_veces(self):
        """PROD-VNC-CAM contra una merma en cámara de la misma partida: con la merma primero (agota la partida), el vencimiento espera, relee y la saltea (ya no está «disponible»):
        una sola `Merma` y sin disponible negativa."""
        self.armar(40, fecha_limite=HOY - timedelta(days=1))
        resultados = correr_a_la_vez(self.mermar(40), lambda: camara.vencer_partidas_en_camara(HOY), primera="a")
        merma, vencimiento = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(merma[0]), merma[2], vencimiento[2]), (1, [], []))
        self.assertEqual(vencimiento[0][0].procesados, 0)
        self.assertEqual(Merma.objects.count(), 1)
        self.assertEqual(StockCosechado.objects.get(pk=self.partida.pk).cantidad_disponible_cosechado, 0)

    def test_regla_el_vencimiento_primero_y_la_merma_se_rechaza_porque_la_partida_ya_no_esta_disponible(self):
        """Con el vencimiento primero, la merma espera, relee y recibe `partida_no_disponible`: ni una merma de más ni una disponible negativa."""
        self.armar(40, fecha_limite=HOY - timedelta(days=1))
        resultados = correr_a_la_vez(lambda: camara.vencer_partidas_en_camara(HOY), self.mermar(10), primera="a")
        vencimiento, merma = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(vencimiento[0]), vencimiento[2], merma[2]), (1, [], []))
        self.assertEqual([e.error_dict["partida"][0].code for e in merma[1]], ["partida_no_disponible"])
        self.assertEqual(Merma.objects.count(), 1)
        self.assertEqual(StockCosechado.objects.get(pk=self.partida.pk).estado_stock_cosechado, "vencido")

    def test_regla_la_merma_primero_y_la_asignacion_toma_solo_lo_que_queda(self):
        """Merma en cámara contra PROD-ASG-CAM: con la merma primero (30 de 40), la asignación espera, relee y reserva solo los 10 que quedan; lo reservado nunca supera la disponible."""
        self.armar(40)
        espera = self.espera(40)
        resultados = correr_a_la_vez(self.mermar(30), self.asignar(), primera="a")
        merma, asignacion = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(merma[0]), merma[2], asignacion[2]), (1, [], []))
        self.assertEqual(self.reservado(), 10)
        self.assertEqual(DetalleReserva.objects.get(reserva__detalle_venta=espera).cantidad_reservada, 10)

    def test_regla_la_asignacion_primero_y_la_merma_recorta_lo_recien_reservado(self):
        """Con la asignación primero (40 reservados de 40), la merma de 15 espera, ve la reserva nueva y la recorta (10c): queda reservado lo que cabe en los 25 que quedan."""
        self.armar(40)
        espera = self.espera(40)
        resultados = correr_a_la_vez(self.asignar(), self.mermar(15), primera="a")
        asignacion, merma = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(asignacion[0]), asignacion[2], merma[2]), (1, [], []))
        self.assertEqual(merma[0][0].recortes, [(espera.compra_venta.codigo, 15)])
        self.assertEqual(self.reservado(), 25)

    def test_regla_dos_mermas_de_la_misma_partida_nunca_la_dejan_negativa(self):
        """Dos mermas de 20 sobre una partida de 30: la segunda espera, relee la disponible (10) y recibe `cantidad_invalida`; la partida no queda negativa y hay una sola merma."""
        self.armar(30)
        resultados = correr_a_la_vez(self.mermar(20), self.mermar(20, actor=self.e.capataz), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(rechazos[0].error_dict["cantidad"][0].code, "cantidad_invalida")
        self.assertEqual(StockCosechado.objects.get(pk=self.partida.pk).cantidad_disponible_cosechado, 10)
        self.assertEqual(Merma.objects.count(), 1)


@tag("concurrencia")
class CamaraAsientoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """CON-04c · paso 2: el asiento de la merma en cámara y del vencimiento bloquea el ejercicio AL FINAL (D-86 punto 2) y nunca rechaza por la fecha (D-102)."""

    def armar(self):
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase vacía el plan en cada prueba
        self.e = escenario_comercial(geografia_propia=True)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_contables)

    def una_partida(self, e, disponible=40, fecha_limite=None):
        lote = lote_maduro(e, 10)
        p = partida(lote, disponible, fecha_limite=fecha_limite)
        Lote.objects.filter(pk=lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        return p

    def con_ejercicios(self):
        """El ejercicio en cierre cubre desde hace 400 días hasta hace unos 36; el abierto empieza hace 20 días y contiene a hoy."""
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, HOY - timedelta(days=400))
        self.abierto = ejercicio_abierto(HOY - timedelta(days=20))

    def cierre(self):
        return lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

    def mermar(self, e, p, cantidad=5):
        datos = DatosDeMermaEnCamara(p.pk, cantidad, "dano_en_camara")
        return lambda: merma_camara.registrar_merma_en_camara(e.agronomo, datos)

    def sin_errores(self, resultados):
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])

    def _cierre_y_merma(self, primera_la_merma):
        """El cierre del ejercicio en cierre y una merma de hoy a la vez: los dos terminan y el asiento N.º 1 va al ejercicio abierto."""
        self.armar()
        self.con_ejercicios()
        merma, cierre = self.mermar(self.e, self.una_partida(self.e)), self.cierre()
        self.sin_errores(correr_a_la_vez(*((merma, cierre) if primera_la_merma else (cierre, merma)), primera="a"))
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento), (self.abierto.pk, 1))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)

    def test_d102_el_cierre_primero_y_la_merma_en_camara_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """El cierre tiene su fila tomada; la merma de hoy no la necesita."""
        self._cierre_y_merma(primera_la_merma=False)

    def test_d102_la_merma_en_camara_primero_y_el_cierre_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """La merma ya asentó y tiene el ejercicio abierto bloqueado; el cierre toca solo su fila."""
        self._cierre_y_merma(primera_la_merma=True)

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_la_merma_en_camara_bloquea(self):
        """La merma A (invernadero Norte) se detiene justo ANTES de bloquear el ejercicio; la B (otro invernadero, sin filas en común) asienta completa y toma el N.º 1."""
        self.armar()
        ejercicio_abierto(HOY - timedelta(days=20))
        otro = escenario_comercial(nombre="Invernadero Sur", sufijo="b", email_del_cliente="clienteb@ejemplo.com", geografia_propia=True)
        pa, pb = self.una_partida(self.e), self.una_partida(otro)
        resultados = correr_a_la_vez(self.mermar(self.e, pa), self.mermar(otro, pb), primera="a", detener_antes_de=(asientos, "_bloquear_ejercicio"))
        self.sin_errores(resultados)
        numero = lambda r: AsientoContable.objects.get(origen_id=r.merma.pk).numero_asiento  # noqa: E731
        self.assertEqual((numero(resultados["b"]), numero(resultados["a"])), (1, 2))

    def test_regla_h8_dos_mermas_de_la_misma_partida_toman_numeros_consecutivos_sin_hueco(self):
        """H8: dos mermas de una misma partida a la vez se serializan y asientan con los números 1 y 2."""
        self.armar()
        ejercicio_abierto(HOY - timedelta(days=20))
        p = self.una_partida(self.e)
        resultados = correr_a_la_vez(self.mermar(self.e, p, 5), self.mermar(self.e, p, 5), primera="a")
        self.sin_errores(resultados)
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2])
