# Pruebas de los modelos de COM-03a (docs/modelo/comercial.md: Suministro, DetalleSuministro, ClausulaSuministrado, ClausulaSuministrante y
# la FK nueva de ReservaStock con su restricción C3): una prueba por restricción de la base (la viola y no la viola), también las de los
# campos de la rescisión (MD-140) que escribe COM-03b, el código `SUM-0001` y la secuencia.

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import ClausulaSuministrado, ClausulaSuministrante, DetalleSuministro, ReservaStock, Suministro
from comercial.tests.fabricas import compra_venta, detalle, detalle_suministro, escenario_comercial, reserva, suministro
from contabilidad.models import OrigenDocumento
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


def no_viola(operacion):
    """Ejecuta `operacion` dentro de un savepoint: si la base la rechaza, la prueba falla con el IntegrityError."""
    with transaction.atomic():
        operacion()


class ModelosDeSuministrosTests(ConDatosDeInventario, TestCase):
    """Restricciones de la base de las cuatro clases y la C3 de `ReservaStock`."""

    def setUp(self):
        self.e = escenario_comercial()
        self.sum = suministro(self.e)
        self.det = detalle_suministro(self.sum, self.e.variedad)

    def cambiar(self, objeto, **campos):
        """Guarda `campos` en `objeto` con un UPDATE directo (sin `full_clean`): lo que se prueba es la base."""
        type(objeto).objects.filter(pk=objeto.pk).update(**campos)

    # ---- Suministro ----

    def test_regla_el_suministro_es_hijo_de_contrato_con_su_tipo_su_codigo_y_su_secuencia(self):
        """Ficha de Suministro: hija de `Contrato` (`tipo_contrato = suministro`), código `SUM-{numero:04d}` y secuencia propia."""
        self.assertEqual(OrigenDocumento.objects.get(pk=self.sum.pk).tipo, "contrato")
        self.assertEqual(self.sum.codigo, f"SUM-{self.sum.numero:04d}")
        with connection.cursor() as cursor:
            cursor.execute("ALTER SEQUENCE comercial_suministro_numero_seq RESTART WITH 1")
            cursor.execute("SELECT nextval('comercial_suministro_numero_seq')")
            self.assertEqual(cursor.fetchone()[0], 1)
        self.assertEqual(Suministro.objects.get(pk=self.sum.pk).tipo_contrato, "suministro")

    def test_regla_el_suministro_nace_vigente_sin_incumplimientos_ni_rescision(self):
        """Regla 5 y 6 de 8.11: nace «vigente» con la cantidad de incumplimientos en cero; sin fecha de resolución ni rescisión."""
        s = Suministro.objects.get(pk=self.sum.pk)
        self.assertEqual((s.estado_suministro, s.cantidad_incumplimientos), ("vigente", 0))
        self.assertIsNone(s.fecha_resolucion_suministro)
        self.assertIsNone(s.motivo_rescision)
        self.assertFalse(s.tiene_rescision_acordada)

    def test_regla_duracion_entre_1_y_120_meses(self):
        """Datos del contrato: de 1 a 120 meses."""
        for valor in (0, 121):
            with self.subTest(valor=valor):
                viola(self, lambda: self.cambiar(self.sum, duracion_meses=valor))
        for valor in (1, 120):
            with self.subTest(valor=valor):
                no_viola(lambda: self.cambiar(self.sum, duracion_meses=valor))

    def test_regla_tolerados_entre_0_y_99(self):
        """PCU 16: de 0 a 99 (con 0, el primer incumplimiento resuelve el contrato)."""
        viola(self, lambda: self.cambiar(self.sum, incumplimientos_tolerados=100))
        for valor in (0, 99):
            with self.subTest(valor=valor):
                no_viola(lambda: self.cambiar(self.sum, incumplimientos_tolerados=valor))

    def test_regla_multa_no_negativa(self):
        """Datos del contrato: la multa es de $ 0 en adelante."""
        viola(self, lambda: self.cambiar(self.sum, multa_resolucion=Decimal("-0.01")))
        no_viola(lambda: self.cambiar(self.sum, multa_resolucion=Decimal("0.00")))

    def test_regla_incumplimientos_no_negativos(self):
        """Regla 6 de 8.11: `cantidad_incumplimientos >= 0` (campo positivo: la base lo rechaza)."""
        viola(self, lambda: self.cambiar(self.sum, cantidad_incumplimientos=-1))
        no_viola(lambda: self.cambiar(self.sum, cantidad_incumplimientos=0))

    def test_regla_estado_del_suministro_dentro_de_su_lista(self):
        """Ficha de Suministro: vigente, finalizado, resuelto o rescindido."""
        viola(self, lambda: self.cambiar(self.sum, estado_suministro="cancelado"))
        no_viola(lambda: self.cambiar(self.sum, estado_suministro="finalizado"))

    def test_regla_resuelto_si_y_solo_si_tiene_fecha_de_resolucion(self):
        """MD-120: `estado = resuelto ⇔ fecha_resolucion_suministro` no nula."""
        viola(self, lambda: self.cambiar(self.sum, estado_suministro="resuelto"))
        viola(self, lambda: self.cambiar(self.sum, fecha_resolucion_suministro=HOY))
        no_viola(lambda: self.cambiar(self.sum, estado_suministro="resuelto", fecha_resolucion_suministro=HOY))

    def test_regla_rescindido_si_y_solo_si_tiene_fecha_de_rescision(self):
        """MD-140: `estado = rescindido ⇔ fecha_rescision` no nula (y rescindido exige una rescisión acordada)."""
        viola(self, lambda: self.cambiar(self.sum, fecha_rescision=HOY))
        viola(self, lambda: self.cambiar(self.sum, estado_suministro="rescindido"))
        no_viola(lambda: self.cambiar(self.sum, **self.rescision(estado_suministro="rescindido", fecha_rescision=HOY)))

    def rescision(self, **extra):
        """Los cuatro campos de una rescisión acordada (todos juntos o ninguno) más `extra`."""
        campos = {
            "motivo_rescision": "a_pedido_del_cliente",
            "fecha_acuerdo_rescision": HOY - timedelta(days=1),
            "fecha_registro_rescision": HOY,
            "fecha_ultima_entrega_rescision": HOY + timedelta(days=14),
        }
        campos.update(extra)
        return campos

    def test_regla_rescision_acordada_exige_las_tres_fechas_y_el_motivo_juntos(self):
        """MD-140: `motivo_rescision` no nulo ⇔ las fechas de acuerdo, de registro y de última entrega no nulas."""
        no_viola(lambda: self.cambiar(self.sum, **self.rescision()))
        self.assertTrue(Suministro.objects.get(pk=self.sum.pk).tiene_rescision_acordada)
        for faltante in ("fecha_acuerdo_rescision", "fecha_registro_rescision", "fecha_ultima_entrega_rescision"):
            with self.subTest(faltante=faltante):
                viola(self, lambda: self.cambiar(self.sum, **self.rescision(**{faltante: None})))
        self.cambiar(self.sum, motivo_rescision=None, fecha_acuerdo_rescision=None, fecha_registro_rescision=None, fecha_ultima_entrega_rescision=None)
        viola(self, lambda: self.cambiar(self.sum, fecha_acuerdo_rescision=HOY))  # una fecha sin motivo
        viola(self, lambda: self.cambiar(self.sum, motivo_rescision="otro"))  # motivo sin fechas

    def test_regla_el_acuerdo_no_es_posterior_al_registro_de_la_rescision(self):
        """MD-140: `fecha_acuerdo_rescision <= fecha_registro_rescision`."""
        viola(self, lambda: self.cambiar(self.sum, **self.rescision(fecha_acuerdo_rescision=HOY + timedelta(days=1))))
        no_viola(lambda: self.cambiar(self.sum, **self.rescision(fecha_acuerdo_rescision=HOY)))

    def test_regla_el_motivo_de_la_rescision_esta_en_su_lista(self):
        """MD-140: a pedido del cliente, a pedido de la empresa u otro (la lista cerrada la verifica `full_clean`; la base, que el motivo
        sea consistente con las fechas)."""
        for motivo in ("a_pedido_del_cliente", "a_pedido_de_la_empresa", "otro"):
            with self.subTest(motivo=motivo):
                no_viola(lambda: self.cambiar(self.sum, **self.rescision(motivo_rescision=motivo)))

    # ---- DetalleSuministro ----

    def test_regla_periodo_de_entrega_entre_1_y_365_dias(self):
        """Datos del detalle: de 1 a 365 días."""
        for valor in (0, 366):
            with self.subTest(valor=valor):
                viola(self, lambda: self.cambiar(self.det, periodo_entrega_dias=valor))
        for valor in (1, 365):
            with self.subTest(valor=valor):
                no_viola(lambda: self.cambiar(self.det, periodo_entrega_dias=valor))

    def test_regla_cantidad_por_periodo_entre_1_y_500000(self):
        """Datos del detalle: de 1 a 500.000 plantas."""
        for valor in (0, 500001):
            with self.subTest(valor=valor):
                viola(self, lambda: self.cambiar(self.det, cantidad_por_periodo=valor))
        for valor in (1, 500000):
            with self.subTest(valor=valor):
                no_viola(lambda: self.cambiar(self.det, cantidad_por_periodo=valor))

    def test_regla_precio_inicial_entre_0_01_y_9999999_99(self):
        """Datos del precio: de $ 0,01 a $ 9.999.999,99."""
        viola(self, lambda: self.cambiar(self.det, precio_unitario_suministro=Decimal("0.00")))
        for valor in ("0.01", "9999999.99"):
            with self.subTest(valor=valor):
                no_viola(lambda: self.cambiar(self.det, precio_unitario_suministro=Decimal(valor)))

    def test_regla_porcentaje_de_ajuste_entre_0_01_y_100(self):
        """Datos del precio: de 0,01 % a 100 %, solo con ajuste periódico."""
        ajuste = {"mecanismo_precio": "ajuste_periodico", "meses_ajuste": 2}
        for valor in ("0.00", "100.01"):
            with self.subTest(valor=valor):
                viola(self, lambda: self.cambiar(self.det, porcentaje_ajuste=Decimal(valor), **ajuste))
        for valor in ("0.01", "100.00"):
            with self.subTest(valor=valor):
                no_viola(lambda: self.cambiar(self.det, porcentaje_ajuste=Decimal(valor), **ajuste))

    def test_regla_meses_de_ajuste_entre_1_y_60(self):
        """Datos del precio: de 1 a 60 meses, solo con ajuste periódico."""
        ajuste = {"mecanismo_precio": "ajuste_periodico", "porcentaje_ajuste": Decimal("3.00")}
        for valor in (0, 61):
            with self.subTest(valor=valor):
                viola(self, lambda: self.cambiar(self.det, meses_ajuste=valor, **ajuste))
        for valor in (1, 60):
            with self.subTest(valor=valor):
                no_viola(lambda: self.cambiar(self.det, meses_ajuste=valor, **ajuste))

    def test_regla_mecanismo_fijo_no_lleva_ajuste_y_periodico_si(self):
        """Ficha de DetalleSuministro: `fijo ⇒ porcentaje y meses nulos`; `ajuste_periodico ⇒ los dos no nulos`."""
        viola(self, lambda: self.cambiar(self.det, porcentaje_ajuste=Decimal("3.00")))
        viola(self, lambda: self.cambiar(self.det, meses_ajuste=2))
        viola(self, lambda: self.cambiar(self.det, mecanismo_precio="ajuste_periodico"))
        viola(self, lambda: self.cambiar(self.det, mecanismo_precio="ajuste_periodico", porcentaje_ajuste=Decimal("3.00")))
        no_viola(lambda: self.cambiar(self.det, mecanismo_precio="ajuste_periodico", porcentaje_ajuste=Decimal("3.00"), meses_ajuste=2))

    def test_regla_mecanismo_y_estado_del_detalle_dentro_de_su_lista(self):
        """Ficha de DetalleSuministro: `fijo` o `ajuste_periodico`; `vigente`, `finalizado` o `resuelto`."""
        viola(self, lambda: self.cambiar(self.det, mecanismo_precio="variable"))
        viola(self, lambda: self.cambiar(self.det, estado_detalle_suministro="rescindido"))
        for estado in ("finalizado", "resuelto"):
            with self.subTest(estado=estado):
                no_viola(lambda: self.cambiar(self.det, estado_detalle_suministro=estado))

    def test_regla_el_par_variedad_y_direccion_vigente_no_se_repite_en_el_contrato(self):
        """«Dirección y modalidad» y MD-131: un par (variedad, dirección) vigente por contrato; los finalizados no cuentan."""
        viola(self, lambda: detalle_suministro(self.sum, self.e.variedad))
        self.cambiar(self.det, estado_detalle_suministro="finalizado", fecha_fin_detalle=HOY)
        no_viola(lambda: detalle_suministro(self.sum, self.e.variedad))

    def test_regla_el_mismo_par_en_otro_contrato_se_admite(self):
        """9d de COM-PCT-SUM: la superposición entre contratos no se bloquea en la base (solo se advierte)."""
        otro = suministro(self.e)
        no_viola(lambda: detalle_suministro(otro, self.e.variedad))

    def test_regla_reemplaza_a_es_uno_a_uno(self):
        """MD-131: un detalle tiene a lo sumo un sucesor (`OneToOneField`)."""
        self.cambiar(self.det, estado_detalle_suministro="finalizado", fecha_fin_detalle=HOY)
        sucesor = detalle_suministro(self.sum, self.e.variedad, reemplaza_a=self.det)
        self.assertEqual(self.det.sucesor, sucesor)
        viola(self, lambda: detalle_suministro(self.sum, self.e.variedad, estado="finalizado", fecha_fin_detalle=HOY, reemplaza_a=self.det))

    # ---- cláusulas ----

    def test_regla_clausula_del_suministrado_plazo_de_pago_entre_0_y_365(self):
        """Cláusula del suministrado: de 0 a 365 días."""
        clausula = ClausulaSuministrado.objects.get(suministro=self.sum)
        viola(self, lambda: self.cambiar(clausula, plazo_pago_dias=366))
        for valor in (0, 365):
            with self.subTest(valor=valor):
                no_viola(lambda: self.cambiar(clausula, plazo_pago_dias=valor))

    def test_regla_clausula_del_suministrado_indemnizacion_entre_0_y_9999999_99(self):
        """Cláusula del suministrado: de $ 0,00 a $ 9.999.999,99 por día (el tope lo da el propio campo, `DecimalField(9, 2)`)."""
        clausula = ClausulaSuministrado.objects.get(suministro=self.sum)
        for valor in ("-0.01",):
            with self.subTest(valor=valor):
                viola(self, lambda: self.cambiar(clausula, indemnizacion_retraso_pago=Decimal(valor)))
        for valor in ("0.00", "9999999.99"):
            with self.subTest(valor=valor):
                no_viola(lambda: self.cambiar(clausula, indemnizacion_retraso_pago=Decimal(valor)))

    def test_regla_el_contrato_tiene_una_sola_clausula_del_suministrado(self):
        """MD-124: la cláusula del suministrado es una por contrato (`OneToOne`)."""
        viola(self, lambda: ClausulaSuministrado.objects.create(suministro=self.sum, plazo_pago_dias=1, indemnizacion_retraso_pago=Decimal("1")))

    def test_regla_clausula_del_suministrante_plazo_entre_0_y_365(self):
        """Cláusula del suministrante: tolerancia de 0 a 365 días."""
        clausula = ClausulaSuministrante.objects.get(detalle=self.det)
        viola(self, lambda: self.cambiar(clausula, plazo_entrega_dias=366))
        for valor in (0, 365):
            with self.subTest(valor=valor):
                no_viola(lambda: self.cambiar(clausula, plazo_entrega_dias=valor))

    def test_regla_clausula_del_suministrante_indemnizaciones_entre_0_y_9999999_99(self):
        """Cláusula del suministrante: indemnización por retraso y por faltante, de $ 0,00 a $ 9.999.999,99."""
        clausula = ClausulaSuministrante.objects.get(detalle=self.det)
        for campo in ("indemnizacion_retraso_entrega", "indemnizacion_faltante"):
            for valor in ("-0.01",):
                with self.subTest(campo=campo, valor=valor):
                    viola(self, lambda: self.cambiar(clausula, **{campo: Decimal(valor)}))
            for valor in ("0.00", "9999999.99"):
                with self.subTest(campo=campo, valor=valor):
                    no_viola(lambda: self.cambiar(clausula, **{campo: Decimal(valor)}))

    def test_regla_cantidad_minima_de_al_menos_una_planta(self):
        """Cláusula del suministrante: desde 1 planta (la cota superior, la cantidad por período, la verifica el servicio: otra tabla)."""
        clausula = ClausulaSuministrante.objects.get(detalle=self.det)
        viola(self, lambda: self.cambiar(clausula, cantidad_minima=0))
        no_viola(lambda: self.cambiar(clausula, cantidad_minima=1))

    def test_regla_el_detalle_tiene_una_sola_clausula_del_suministrante(self):
        """Cláusula por detalle (`OneToOne`)."""
        viola(
            self,
            lambda: ClausulaSuministrante.objects.create(
                detalle=self.det, plazo_entrega_dias=0, indemnizacion_retraso_entrega=Decimal("1"), cantidad_minima=1,
                indemnizacion_faltante=Decimal("1"),
            ),
        )

    # ---- ReservaStock: C3 ----

    def test_regla_c3_una_reserva_no_tiene_detalle_de_venta_y_de_suministro_a_la_vez(self):
        """Ficha de ReservaStock, C3: a lo sumo uno de R123 y R124 (ninguno: la cosecha manual sin contrato)."""
        lote = lote_maduro(self.e, 50)
        venta = compra_venta(self.e)
        detalle_venta = detalle(venta, self.e.variedad, cantidad=10)
        r = reserva(detalle_venta, [(lote, 5)])
        viola(self, lambda: ReservaStock.objects.filter(pk=r.pk).update(detalle_suministro=self.det))
        ReservaStock.objects.filter(pk=r.pk).update(detalle_venta=None)
        no_viola(lambda: ReservaStock.objects.filter(pk=r.pk).update(detalle_suministro=self.det))
        self.assertEqual(list(self.det.reservas.all()), [r])
