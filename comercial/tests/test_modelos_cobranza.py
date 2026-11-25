# Pruebas de los modelos de COM-08a (paso 1): `LineaPago` (R154, D-94 punto 2), lo nuevo de `PagoCliente` (`tipo_pago`, `numero`, `usuario`, `estado_aviso_cliente` y C7 como {xor}; D-94 punto 3), lo nuevo de
# `Entrega` (la mora y la indemnización por día; D-94 puntos 5 y 12), la secuencia del número de cobro, las acciones y etiquetas de auditoría de `core`, las fábricas nuevas y
# `verificar_invariantes_de_cobros`. Una prueba por restricción de la base (la viola y no la viola).
# Fuente: docs/modelo/comercial.md («PagoCliente», «LineaPago», «Entrega»), D-94 puntos 2, 3, 5 y 12, D-36 (auditoría) y docs/casos_de_uso/comercial/cobranza.md («Pruebas»).

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega, LineaPago, PagoCliente
from comercial.tests.fabricas import (
    cobro,
    entrega_de_suministro,
    entrega_en_mora,
    escenario_comercial,
    pago_de_compra_venta,
    compra_venta,
    verificar_invariantes_de_cobros,
)
from core.models import ACCIONES_DE_NEGOCIO, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


class Base(ConDatosDeInventario, TestCase):
    """Un escenario con un lote de 500 plantas y su Gerente; cada prueba arma sus entregas y sus cobros."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.gerente = crear_gerente()
        cls.lote = lote_maduro(cls.e, 500)

    def concretada(self, **extra):
        """Una entrega de suministro concretada hoy (10 plantas a $100 = $1.000,00, plazo de 10 días, $300,00 por día de atraso)."""
        return entrega_de_suministro(self.e, self.lote, **extra)

    def rompe(self, texto):
        with self.assertRaises(AssertionError) as c:
            verificar_invariantes_de_cobros()
        self.assertIn(texto, str(c.exception))


class LineaPagoRestriccionesTests(Base):
    """D-94 punto 2 y `docs/modelo/comercial.md`, «LineaPago», restricciones de la base."""

    def test_regla_una_linea_por_pago_y_entrega(self):
        """Único `(pago, entrega)`: la misma entrega no puede estar dos veces en un pago."""
        e = self.concretada()
        pago = cobro([e])
        viola(self, lambda: LineaPago.objects.create(pago=pago, entrega=e, monto_cobrado=Decimal("1.00"), vigente=False))

    def test_regla_a_lo_sumo_una_linea_vigente_por_entrega(self):
        """Garantía mínima 2 de COM-REG-CBR: el índice único parcial. Una entrega con su cobro vigente no admite otro vigente."""
        e = self.concretada()
        cobro([e])
        viola(self, lambda: cobro([e]))

    def test_regla_una_entrega_conserva_el_cobro_anulado_y_recibe_el_correcto(self):
        """MD-136: una línea no vigente no cuenta para el índice parcial: la entrega puede tener un pago anulado y uno vigente."""
        e = self.concretada()
        anulado = cobro([e], estado="anulado")
        vigente = cobro([e])
        self.assertEqual(sorted(LineaPago.objects.filter(entrega=e).values_list("pago_id", "vigente")), sorted([(anulado.pk, False), (vigente.pk, True)]))
        verificar_invariantes_de_cobros()

    def test_regla_lo_cobrado_es_mayor_que_cero(self):
        """`monto_cobrado > 0`: una entrega saldada no se cobra."""
        e = self.concretada()
        pago = cobro([e])
        otra = self.concretada()
        viola(self, lambda: LineaPago.objects.create(pago=pago, entrega=otra, monto_cobrado=Decimal("0.00"), vigente=False))

    def test_regla_los_dias_de_atraso_no_son_negativos(self):
        """`dias_atraso >= 0`."""
        e = self.concretada()
        pago = cobro([e])
        otra = self.concretada()
        viola(self, lambda: LineaPago.objects.create(pago=pago, entrega=otra, monto_cobrado=Decimal("1.00"), dias_atraso=-1, vigente=False))

    def test_regla_la_indemnizacion_no_es_negativa(self):
        """`indemnizacion_atraso >= 0`."""
        e = self.concretada()
        pago = cobro([e])
        otra = self.concretada()
        viola(self, lambda: LineaPago.objects.create(pago=pago, entrega=otra, monto_cobrado=Decimal("1.00"), dias_atraso=1, indemnizacion_atraso=Decimal("-1.00"), vigente=False))

    def test_regla_sin_atraso_no_hay_indemnizacion(self):
        """`dias_atraso = 0 ⇒ indemnizacion_atraso = 0`; con atraso, puede ser cualquier monto no negativo."""
        e = self.concretada()
        pago = cobro([e])
        otra = self.concretada()
        viola(self, lambda: LineaPago.objects.create(pago=pago, entrega=otra, monto_cobrado=Decimal("1.00"), dias_atraso=0, indemnizacion_atraso=Decimal("5.00"), vigente=False))
        LineaPago.objects.create(pago=pago, entrega=otra, monto_cobrado=Decimal("1.00"), dias_atraso=2, indemnizacion_atraso=Decimal("5.00"), vigente=False)

    def test_regla_el_codigo_de_una_linea_es_legible_en_la_auditoria(self):
        """`__str__` de la línea (texto de `referencia()`, D-36)."""
        e = self.concretada()
        linea = cobro([e]).lineas.get()
        self.assertEqual(str(linea), f"Línea de pago #{linea.pk}")


class PagoClienteRestriccionesTests(Base):
    """D-94 punto 3: C7 como {xor} y los campos nuevos de `PagoCliente`."""

    def datos(self, **extra):
        base = dict(cliente=self.e.cliente, medio_pago="efectivo", fecha_pago=HOY, monto_pagado=Decimal("100.00"))
        base.update(extra)
        return base

    def siguiente_numero(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval('comercial_cobro_numero_seq')")
            return cursor.fetchone()[0]

    def test_regla_c7_un_pago_de_compra_venta_exige_compra_venta(self):
        """C7 {xor}: `tipo_pago = compra_venta` sin `compra_venta` se rechaza (y sin número)."""
        viola(self, lambda: PagoCliente.objects.create(**self.datos(tipo_pago="compra_venta")))

    def test_regla_c7_un_pago_de_suministro_no_tiene_compra_venta(self):
        """C7 {xor}: `tipo_pago = suministro` con `compra_venta` se rechaza."""
        venta = compra_venta(self.e)
        viola(self, lambda: PagoCliente.objects.create(**self.datos(tipo_pago="suministro", compra_venta=venta, numero=self.siguiente_numero())))

    def test_regla_solo_un_pago_de_suministro_tiene_numero(self):
        """`tipo_pago = suministro ⇔ numero no nulo`: sin número se rechaza; con número en una compra-venta, también."""
        venta = compra_venta(self.e)
        viola(self, lambda: PagoCliente.objects.create(**self.datos(tipo_pago="suministro")))
        viola(self, lambda: PagoCliente.objects.create(**self.datos(tipo_pago="compra_venta", compra_venta=venta, numero=self.siguiente_numero())))

    def test_regla_el_numero_del_cobro_es_unico(self):
        """`UniqueConstraint(numero)`."""
        numero = self.siguiente_numero()
        PagoCliente.objects.create(**self.datos(tipo_pago="suministro", numero=numero))
        viola(self, lambda: PagoCliente.objects.create(**self.datos(tipo_pago="suministro", numero=numero)))

    def test_regla_el_tipo_de_pago_es_de_su_lista(self):
        """`tipo_pago` solo admite «compra_venta» o «suministro»."""
        viola(self, lambda: PagoCliente.objects.create(**self.datos(tipo_pago="otro", numero=self.siguiente_numero())))

    def test_regla_el_aviso_al_cliente_es_de_su_lista(self):
        """`estado_aviso_cliente` nulo o `enviado` / `pendiente_envio` / `sin_correo`."""
        for valor in ("enviado", "pendiente_envio", "sin_correo", None):
            PagoCliente.objects.create(**self.datos(tipo_pago="suministro", numero=self.siguiente_numero(), estado_aviso_cliente=valor))
        viola(self, lambda: PagoCliente.objects.create(**self.datos(tipo_pago="suministro", numero=self.siguiente_numero(), estado_aviso_cliente="roto")))

    def test_regla_un_pago_de_compra_venta_no_tiene_aviso_de_comprobante(self):
        """`tipo_pago = compra_venta ⇒ estado_aviso_cliente` nulo: su comprobante es el de la venta (`Contrato.estado_comprobante`)."""
        venta = compra_venta(self.e)
        viola(self, lambda: PagoCliente.objects.create(**self.datos(tipo_pago="compra_venta", compra_venta=venta, estado_aviso_cliente="enviado")))

    def test_regla_el_pago_de_compra_venta_de_comercial_06a_sigue_siendo_valido(self):
        """La migración deja el valor por omisión `compra_venta`: el pago que ya creaba COM-06a (sin número, sin usuario, sin aviso) cumple la C7 nueva."""
        pago = pago_de_compra_venta(compra_venta(self.e))
        pago.refresh_from_db()
        self.assertEqual((pago.tipo_pago, pago.numero, pago.usuario_id, pago.estado_aviso_cliente), ("compra_venta", None, None, None))
        self.assertEqual(str(pago), f"Pago #{pago.pk}")

    def test_regla_el_codigo_del_cobro_es_cob_con_cuatro_cifras(self):
        """D-94 punto 3: `COB-0032`; el `__str__` es el código (texto de la auditoría)."""
        pago = cobro([self.concretada()])
        self.assertEqual(pago.codigo, f"COB-{pago.numero:04d}")
        self.assertEqual(str(pago), pago.codigo)
        self.assertRegex(pago.codigo, r"^COB-\d{4}$")

    def test_regla_la_secuencia_del_cobro_avanza_sin_repetir(self):
        """`comercial_cobro_numero_seq` (creada por la migración con `RunSQL`): dos números seguidos son distintos y crecientes."""
        a, b = self.siguiente_numero(), self.siguiente_numero()
        self.assertGreater(b, a)


class EntregaMoraRestriccionesTests(Base):
    """D-94 puntos 5 y 12: los campos nuevos de `Entrega`."""

    def test_regla_el_aviso_de_mora_es_de_su_lista(self):
        """`estado_aviso_mora` nulo o `enviado` / `pendiente_envio` / `sin_correo`."""
        e = self.concretada()
        for valor in ("enviado", "pendiente_envio", "sin_correo"):
            Entrega.objects.filter(pk=e.pk).update(fecha_aviso_mora=HOY, estado_aviso_mora=valor)
        viola(self, lambda: Entrega.objects.filter(pk=e.pk).update(fecha_aviso_mora=HOY, estado_aviso_mora="roto"))

    def test_regla_el_resultado_del_correo_de_mora_exige_la_fecha_del_aviso(self):
        """`estado_aviso_mora` no nulo ⇒ `fecha_aviso_mora` no nula."""
        e = self.concretada()
        viola(self, lambda: Entrega.objects.filter(pk=e.pk).update(estado_aviso_mora="enviado", fecha_aviso_mora=None))
        Entrega.objects.filter(pk=e.pk).update(fecha_aviso_mora=HOY)  # la fecha sola sí se admite (el correo aún no se intentó)

    def test_regla_la_indemnizacion_por_dia_no_es_negativa(self):
        """`indemnizacion_retraso_dia` nula o `>= 0`; la copia `concretar_entrega` (aquí, `marcar_concretada`) de la cláusula."""
        e = self.concretada(indemnizacion_pago="300.00")
        self.assertEqual(e.indemnizacion_retraso_dia, Decimal("300.00"))
        viola(self, lambda: Entrega.objects.filter(pk=e.pk).update(indemnizacion_retraso_dia=Decimal("-0.01")))

    def test_regla_una_entrega_nace_sin_aviso_de_mora(self):
        """Las entregas ya existentes (y las nuevas) quedan sin fecha ni resultado de aviso de mora."""
        e = self.concretada()
        self.assertEqual((e.fecha_aviso_mora, e.estado_aviso_mora), (None, None))


class FabricasDeCobranzaTests(Base):
    """Las fábricas nuevas arman datos que cumplen los invariantes."""

    def test_entrega_en_mora_vencio_hace_los_dias_pedidos(self):
        """`entrega_en_mora(dias_de_mora=3, plazo_pago=10)`: concretada hace 13 días, vencimiento hace 3."""
        e = entrega_en_mora(self.e, self.lote, dias_de_mora=3, plazo_pago=10)
        self.assertEqual(e.fecha_resolucion_orden, HOY - timedelta(days=13))
        self.assertEqual(e.fecha_vencimiento_pago, HOY - timedelta(days=3))

    def test_cobro_calcula_el_atraso_con_la_indemnizacion_de_la_entrega(self):
        """5 días de mora × $300,00 = $1.500,00; el pago suma lo cobrado más el atraso (D-94 punto 12)."""
        e = entrega_en_mora(self.e, self.lote, dias_de_mora=5, plazo_pago=10)
        pago = cobro([e])
        linea = pago.lineas.get()
        self.assertEqual((linea.monto_cobrado, linea.dias_atraso, linea.indemnizacion_atraso), (Decimal("1000.00"), 5, Decimal("1500.00")))
        self.assertEqual(pago.monto_pagado, Decimal("2500.00"))
        verificar_invariantes_de_cobros()

    def test_marcar_concretada_sin_hace_dias_conserva_lo_de_comercial_06a(self):
        """Compatibilidad: sin `hace_dias`, la entrega se concreta hoy y vence `plazo_pago` días después."""
        e = self.concretada(plazo_pago=15)
        self.assertEqual((e.fecha_resolucion_orden, e.fecha_vencimiento_pago), (HOY, HOY + timedelta(days=15)))


class InvariantesDeCobrosTests(Base):
    """`verificar_invariantes_de_cobros`: pasa con datos sanos y se rompe, con su mensaje, cuando falta algo."""

    def test_sin_cobros_ni_mora_pasa(self):
        """Sin datos de cobranza, no hay nada que romper."""
        self.concretada()
        verificar_invariantes_de_cobros()

    def test_un_pago_de_suministro_sin_lineas_rompe(self):
        """Invariante 1: un pago de suministro tiene al menos una línea."""
        pago = cobro([self.concretada()])
        pago.lineas.all().delete()
        self.rompe("un pago de suministro sin líneas")

    def test_un_pago_de_compra_venta_con_lineas_rompe(self):
        """Invariante 1: un pago de compra-venta no tiene líneas."""
        e = self.concretada()
        pago = pago_de_compra_venta(compra_venta(self.e))
        LineaPago.objects.create(pago=pago, entrega=e, monto_cobrado=Decimal("1.00"), vigente=True)
        self.rompe("un pago de compra-venta con 1 líneas de pago")

    def test_el_monto_pagado_debe_ser_la_suma_de_las_lineas(self):
        """Invariante 2."""
        pago = cobro([self.concretada()])
        PagoCliente.objects.filter(pk=pago.pk).update(monto_pagado=Decimal("1.00"))
        self.rompe("distinto de la suma de sus líneas")

    def test_la_linea_debe_seguir_el_estado_de_su_pago(self):
        """Invariante 3: `vigente` copia `estado_pago = vigente`."""
        pago = cobro([self.concretada()])
        LineaPago.objects.filter(pago=pago).update(vigente=False)
        self.rompe("con vigente=False y el pago vigente")

    def test_las_entregas_de_un_pago_son_del_cliente_del_pago(self):
        """Invariante 4: todas las entregas de un pago son del cliente del pago."""
        pago = cobro([self.concretada()])
        otro = escenario_comercial("2").cliente
        PagoCliente.objects.filter(pk=pago.pk).update(cliente=otro)
        self.rompe("de otro cliente")

    def test_lo_cobrado_debe_ser_el_monto_a_cobrar_mientras_la_linea_este_vigente(self):
        """Invariante 5."""
        pago = cobro([self.concretada()])
        LineaPago.objects.filter(pago=pago).update(monto_cobrado=Decimal("999.00"))
        PagoCliente.objects.filter(pk=pago.pk).update(monto_pagado=Decimal("999.00"))
        self.rompe("no es su monto a cobrar")

    def test_solo_una_entrega_concretada_de_suministro_tiene_fecha_de_aviso_de_mora(self):
        """Invariante 6: una entrega «a realizar» con `fecha_aviso_mora` rompe."""
        e = self.concretada()
        Entrega.objects.filter(pk=e.pk).update(estado_orden="a_realizar", fecha_resolucion_orden=None, fecha_aviso_mora=HOY)
        self.rompe("no es una entrega de suministro concretada")

    def test_una_entrega_en_mora_avisada_necesita_su_alerta_activa(self):
        """Invariante 7: con `fecha_aviso_mora` y en mora, sin alerta «pago en mora» activa, rompe; con ella, pasa."""
        from maestros.models import Alerta

        e = entrega_en_mora(self.e, self.lote)
        Entrega.objects.filter(pk=e.pk).update(fecha_aviso_mora=HOY)
        self.rompe("sin su alerta «pago en mora» activa")
        alerta = Alerta.objects.create(
            invernadero=e.invernadero, tipo_alerta="comercial_pago_en_mora", descripcion_alerta="x", nivel_severidad="critica", para_gerente=True, clave_estado=f"entrega:{e.pk}"
        )
        AlertaComercial.objects.create(alerta=alerta, entrega_id=e.pk)
        verificar_invariantes_de_cobros()


class AuditoriaDeCobranzaTests(TestCase):
    """Las acciones de auditoría nuevas están clasificadas, con su etiqueta (D-36)."""

    def test_las_acciones_nuevas_son_de_negocio(self):
        """D-36: cada acción nueva se clasifica en `ACCIONES_DE_NEGOCIO` (el Gerente la ve en «Auditoría»)."""
        self.assertIn(RegistroAuditoria.Accion.REGISTRO_COBRO, ACCIONES_DE_NEGOCIO)
        self.assertIn(RegistroAuditoria.Accion.VENCIMIENTO_PAGO, ACCIONES_DE_NEGOCIO)
        self.assertEqual(RegistroAuditoria.Accion.REGISTRO_COBRO.value, "registro_cobro")
        self.assertEqual(RegistroAuditoria.Accion.VENCIMIENTO_PAGO.value, "vencimiento_pago")

    def test_las_etiquetas_nuevas_estan_en_el_diccionario(self):
        """D-36: el nombre visible de lo que auditan el cobro y el vencimiento."""
        for clave in ("monto_pagado", "numero_cobro", "indemnizacion_atraso_total", "fecha_aviso_mora", "detalle_de_entregas", "medio_pago", "fecha_pago"):
            self.assertIn(clave, RegistroAuditoria.ETIQUETAS)
