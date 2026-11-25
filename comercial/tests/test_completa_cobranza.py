# Pruebas de lo que COM-08a completa de otras tareas (paso 7; `docs/casos_de_uso/comercial/cobranza.md`, «Lo que completa a otras tareas»), con datos reales: el pago de compra-venta de la concreción (con `tipo_pago` y
# `usuario`) y la copia de `indemnizacion_retraso_dia` (D-94 puntos 3 y 12), `modificar_suministro` (solo actualiza las entregas que todavía no vencieron), las solicitudes con un cobro real (2b solo con un cobro de
# verdad, no con una entrega saldada; `resolver_solicitud` y `anular_resolucion` llaman a `reevaluar_mora`, MD-125; la ficha muestra el cobro), COM-ATN-ENR (el cobro de la ficha y la regla 5 con un cobro vigente, no con
# uno anulado), la ficha del suministro (regla 7 de COM-CNS-SUM) y la ficha y la baja del cliente. Las pruebas de COM-06a, COM-06b y COM-07a que ya había no se tocan (salvo las seis que usaban `mock.patch` de
# `estado_de_pago`, que se reemplazaron en sus archivos y se anotan en el PR).
# Fuente: docs/casos_de_uso/comercial/cobranza.md («Lo que completa a otras tareas», «Estado de pago y monto a cobrar», «La mora»), solicitudes.md («Anular una resolución», 2b), confirmacion.md («Atender una entrega no
# reconocida»), suministro.md («COM-CNS-SUM», reglas 7 y 10), clientes.md («Consulta (CNS)» y «Baja (BAJ)»), D-94 puntos 3, 4, 5 y 12, MD-125.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa): `Lectura.cobro` (el `CobroDeEntrega` de la entrega o `None`); `FilaDeEntregaDeContrato.estado_pago_texto` dice «Pagada · COB-0001», «Saldada»,
# «En mora · 5 días» o «Pendiente»; `ficha_de_suministro(...).acciones` suma `registrar_cobro`; las filas de `clientes.entregas_sin_cobrar` traen `dias_de_mora` y su `texto_del_estado` («En mora · 5 días»), y
# no incluyen las pagadas ni las saldadas; `pendientes_del_cliente` suma «… N en mora».

from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone

from comercial.models import ClausulaSuministrado, Entrega, PagoCliente, Suministro
from comercial.servicios import atencion, clientes, cobranza, concrecion, entregas, solicitudes, suministros
from comercial.servicios.concrecion import DatosDeConcrecion
from comercial.servicios.solicitudes import DatosDeResolucion
from comercial.tests.base_cobranza import HOY, BaseDeCobranza, codigos
from comercial.tests.fabricas import (
    alerta_no_reconocida,
    cobro,
    discrepancia,
    discrepancia_aceptada,
    entrega_concretable,
    entrega_de_suministro,
)
from core.models import RegistroAuditoria
from maestros.models import Alerta

D = Decimal


class ConcrecionYModificacionTests(BaseDeCobranza):
    """El pago de compra-venta de la concreción y la indemnización por día de la entrega."""

    def concretar(self, x, actor=None):
        actor = actor or x.transportista or self.e.vendedor
        datos = DatosDeConcrecion(medio_pago="efectivo", sin_envases=x.envases is None)
        resumen = concrecion.resumen_de_concrecion(actor, x.entrega.pk, datos)
        return concrecion.concretar_entrega(actor, x.entrega.pk, datos, resumen.huella)

    def test_regla_concretar_un_suministro_copia_la_indemnizacion_por_dia_de_la_clausula(self):
        """D-94 punto 12: `concretar_entrega` copia en la entrega `indemnizacion_retraso_dia` de la cláusula del suministrado (junto con el vencimiento, MD-132)."""
        x = entrega_concretable(self.e, self.lote, tipo="suministro", cantidad=100, plazo_pago=10)
        ClausulaSuministrado.objects.filter(suministro_id=x.contrato.pk).update(indemnizacion_retraso_pago=D("120.00"))
        self.concretar(x)
        e = Entrega.objects.get(pk=x.entrega.pk)
        self.assertEqual((e.indemnizacion_retraso_dia, e.fecha_vencimiento_pago), (D("120.00"), HOY + timedelta(days=10)))

    def test_regla_concretar_una_compra_venta_no_lleva_indemnizacion_por_dia(self):
        """Solo un suministro la tiene: en una compra-venta queda nula."""
        x = entrega_concretable(self.e, self.lote, tipo="venta", cantidad=50, retiro=True)
        self.concretar(x, actor=self.e.vendedor)
        self.assertIsNone(Entrega.objects.get(pk=x.entrega.pk).indemnizacion_retraso_dia)

    def test_regla_el_pago_de_compra_venta_lleva_tipo_pago_y_usuario(self):
        """D-94 punto 3: el pago de la concreción de una compra-venta carga `tipo_pago = compra_venta` y `usuario` (quien concretó); sin número ni aviso de comprobante."""
        x = entrega_concretable(self.e, self.lote, tipo="venta", cantidad=50, retiro=True)
        self.concretar(x, actor=self.e.vendedor)
        pago = PagoCliente.objects.get(compra_venta_id=x.contrato.pk)
        self.assertEqual((pago.tipo_pago, pago.usuario_id, pago.numero, pago.estado_aviso_cliente), ("compra_venta", self.e.vendedor.pk, None, None))

    def test_regla_modificar_la_clausula_actualiza_solo_las_entregas_que_no_vencieron(self):
        """D-94 punto 12 y COM-MOD-SUM: el cambio de `indemnizacion_retraso_pago` actualiza `indemnizacion_retraso_dia` solo en las entregas concretadas con `fecha_vencimiento_pago >= hoy`: la que vence hoy y la que
        vence mañana cambian; una vencida conserva la suya."""
        vencida = self.en_mora()
        contrato = Suministro.objects.get(pk=vencida.contrato_entrega_id)
        vence_hoy = entrega_de_suministro(self.e, self.lote, contrato=contrato, plazo_pago=10, hace_dias=10)
        vence_manana = entrega_de_suministro(self.e, self.lote, contrato=contrato, plazo_pago=10, hace_dias=9)
        self.assertEqual((vence_hoy.fecha_vencimiento_pago, vence_manana.fecha_vencimiento_pago), (HOY, HOY + timedelta(days=1)))
        cambios = suministros.CambiosDeSuministro(detalles=[], nuevos=[], indemnizacion_pago="250")
        suministros.modificar_suministro(self.e.vendedor, contrato.pk, cambios, suministros.huella_de(Suministro.objects.get(pk=contrato.pk)))
        por_dia = {e.pk: Entrega.objects.get(pk=e.pk).indemnizacion_retraso_dia for e in (vencida, vence_hoy, vence_manana)}
        self.assertEqual(por_dia, {vencida.pk: D("300.00"), vence_hoy.pk: D("250.00"), vence_manana.pk: D("250.00")})

    def test_regla_modificar_otra_cosa_no_toca_la_indemnizacion_de_las_entregas(self):
        """Sin cambio de la indemnización por día (aquí, la multa), las entregas quedan como estaban."""
        e = self.concretada()
        contrato = Suministro.objects.get(pk=e.contrato_entrega_id)
        cambios = suministros.CambiosDeSuministro(detalles=[], nuevos=[], multa="12345")
        suministros.modificar_suministro(self.e.vendedor, contrato.pk, cambios, suministros.huella_de(contrato))
        self.assertEqual(Entrega.objects.get(pk=e.pk).indemnizacion_retraso_dia, D("300.00"))


class SolicitudesConUnCobroRealTests(BaseDeCobranza):
    """COM-07a con datos reales: 2b, la mora y la ficha."""

    def resolver(self, solicitud, medio="efectivo"):
        datos = DatosDeResolucion("aceptar", "", "", medio)
        resumen = solicitudes.resumen_de_resolucion(self.gerente, solicitud.pk, datos)
        return solicitudes.resolver_solicitud(self.gerente, solicitud.pk, datos, resumen.huella)

    def anular(self, solicitud):
        datos = solicitudes.datos_de_anulacion(self.gerente, solicitud.pk)
        return solicitudes.anular_resolucion(self.gerente, solicitud.pk, "Error de carga.", datos.huella)

    def test_regla_2b_una_entrega_saldada_no_es_una_entrega_cobrada(self):
        """MD-125 y 2b: una entrega saldada (monto a cobrar 0) cuenta como «pagada» pero no tiene un cobro que anular: la anulación no se bloquea con «Primero anulá el cobro»."""
        e = self.concretada()
        s = discrepancia_aceptada(e, monto="1000.00", descontado="1000.00")
        datos = solicitudes.datos_de_anulacion(self.gerente, s.pk)
        self.assertNotEqual((datos.bloqueo or ("",))[0], "entrega_cobrada")

    def test_regla_2b_con_un_cobro_anulado_la_entrega_vuelve_a_poder_anularse(self):
        """Lo que COM-08b libera: con el cobro anulado (sin cobro vigente) la entrega ya no está cobrada y 2b deja de rechazar."""
        e = self.concretada()
        s = discrepancia_aceptada(e, monto="200.00", descontado="200.00")
        cobro([e], estado="anulado")
        datos = solicitudes.datos_de_anulacion(self.gerente, s.pk)
        self.assertNotEqual((datos.bloqueo or ("",))[0], "entrega_cobrada")

    def test_regla_la_ficha_muestra_el_cobro_de_la_entrega(self):
        """La ficha de la solicitud (`Lectura.cobro`): el código, la fecha y quién cobró; `None` sin cobro."""
        e = self.concretada()
        s = discrepancia(e, minima=12)
        self.assertIsNone(solicitudes.ficha_de_solicitud(self.gerente, s.pk).lectura.cobro)
        pago = cobro([e], usuario=self.gerente)
        lectura = solicitudes.ficha_de_solicitud(self.gerente, s.pk).lectura
        self.assertEqual((lectura.cobro.codigo, lectura.cobro.fecha, lectura.estado_de_pago), (pago.codigo, HOY, "pagada"))

    def test_regla_aceptar_una_solicitud_que_salda_una_entrega_en_mora_resuelve_su_alerta(self):
        """MD-125 y «Quién la llama»: `resolver_solicitud` llama a `reevaluar_mora`: si la aceptación deja la entrega saldada, su alerta «pago en mora» se resuelve."""
        e = self.en_mora()
        with override_settings(CORREO_CONFIGURADO=False):
            cobranza.reevaluar_mora(Entrega.objects.get(pk=e.pk), HOY, False)
        self.assertEqual(len(self.alertas_de(e, activas=True)), 1)
        # una indemnización que cubre todo el monto a cobrar: una queja con monto manual igual al total
        from comercial.tests.fabricas import queja

        grande = queja(e, "otro")
        datos = DatosDeResolucion("aceptar", "", "1000", "")
        resumen = solicitudes.resumen_de_resolucion(self.gerente, grande.pk, datos)
        solicitudes.resolver_solicitud(self.gerente, grande.pk, datos, resumen.huella)
        self.assertEqual(entregas.monto_a_cobrar([e.pk])[e.pk], D("0.00"))
        self.assertEqual((len(self.alertas_de(e, activas=True)), len(self.alertas_de(e, activas=False))), (0, 1))

    def test_regla_aceptar_sin_saldar_la_entrega_no_toca_la_alerta(self):
        """Una aceptación que deja monto a cobrar > 0 no resuelve la alerta de una entrega en mora."""
        e = self.en_mora()
        s = discrepancia(e, minima=110)
        with override_settings(CORREO_CONFIGURADO=False):
            cobranza.reevaluar_mora(Entrega.objects.get(pk=e.pk), HOY, False)
        self.resolver(s)
        self.assertEqual(len(self.alertas_de(e, activas=True)), 1)

    def test_regla_anular_la_resolucion_de_una_entrega_vencida_que_estaba_saldada_asegura_la_alerta_sin_correo_ni_aviso(self):
        """«Quién la llama»: `anular_resolucion` llama a `reevaluar_mora`: si la entrega deja de estar saldada y ya venció, asegura una alerta nueva, sin correo al cliente ni aviso al Vendedor (su aviso ya lo dice)."""
        e = self.en_mora()
        s = discrepancia_aceptada(e, monto="1000.00", descontado="1000.00")
        self.assertEqual(self.alertas_de(e), [])
        self.anular(s)
        self.assertEqual(len(self.alertas_de(e, activas=True)), 1)
        self.assertEqual((len(mail.outbox), self.avisos(self.e.vendedor, f"{e.codigo} en mora")), (0, []))


class AtencionDeEntregaNoReconocidaTests(BaseDeCobranza):
    """COM-ATN-ENR con datos reales: el cobro en la ficha y la regla 5."""

    def test_regla_1_la_ficha_muestra_el_cobro_con_codigo_fecha_medio_y_monto(self):
        """Regla 1: «COB-… · dd/mm/aaaa · Efectivo · $ 1.000,00»; sin cobro, «Sin cobro registrado»."""
        e = self.concretada()
        alerta = alerta_no_reconocida(e)
        self.assertEqual(atencion.ficha_de_no_reconocida(self.gerente, alerta.pk).cobro, "Sin cobro registrado")
        pago = cobro([e], medio="efectivo", usuario=self.gerente)
        ficha = atencion.ficha_de_no_reconocida(self.gerente, alerta.pk)
        self.assertEqual(ficha.cobro, f"{pago.codigo} · {HOY:%d/%m/%Y} · Efectivo · $ 1.000,00")

    def test_regla_5_un_cobro_anulado_no_impide_atender(self):
        """Regla 5: solo un cobro vigente exige anular primero; con el cobro anulado (COM-08b) «no llegó» se atiende."""
        e = self.concretada()
        alerta = alerta_no_reconocida(e)
        cobro([e], estado="anulado")
        atencion.atender_entrega_no_reconocida(self.gerente, alerta.pk, "no_llego_perdido", "Hablé con el cliente: no llegó.")
        self.assertEqual(Alerta.objects.get(pk=alerta.pk).estado_alerta, "resuelta")

    def test_regla_5_un_cobro_vigente_rechaza_no_llego(self):
        """Regla 5 (la de ATN-ENR con el cobro real está en `test_com_atn_enr`; esta usa la fábrica directa): `entrega_cobrada`."""
        e = self.concretada()
        alerta = alerta_no_reconocida(e)
        cobro([e])
        with self.assertRaises(ValidationError) as c:
            atencion.atender_entrega_no_reconocida(self.gerente, alerta.pk, "no_llego_devuelto", "Volvió.")
        self.assertEqual(codigos(c.exception), ["entrega_cobrada"])


class FichasTests(BaseDeCobranza):
    """La ficha del suministro (regla 7 de COM-CNS-SUM) y la ficha y la baja del cliente."""

    def filas(self, contrato):
        return {f.codigo: f for f in suministros.ficha_de_suministro(self.gerente, contrato.pk).entregas}

    def test_regla_7_la_ficha_del_suministro_dice_pagada_con_el_cobro_saldada_en_mora_con_los_dias_o_pendiente(self):
        """Regla 7 de COM-CNS-SUM: el estado de pago de cada entrega: «Pagada · COB-0001», «Saldada», «En mora · 5 días» y «Pendiente»."""
        mora = self.en_mora(dias_de_mora=5)
        contrato = Suministro.objects.get(pk=mora.contrato_entrega_id)
        pagada = entrega_de_suministro(self.e, self.lote, contrato=contrato)
        saldada = entrega_de_suministro(self.e, self.lote, contrato=contrato)
        pendiente = entrega_de_suministro(self.e, self.lote, contrato=contrato)
        pago = cobro([pagada], usuario=self.gerente)
        discrepancia_aceptada(saldada, monto="1000.00", descontado="1000.00")
        filas = self.filas(contrato)
        self.assertEqual(filas[mora.codigo].estado_pago_texto, "En mora · 5 días")
        self.assertEqual(filas[pagada.codigo].estado_pago_texto, f"Pagada · {pago.codigo}")
        self.assertEqual(filas[saldada.codigo].estado_pago_texto, "Saldada")
        self.assertEqual(filas[pendiente.codigo].estado_pago_texto, "Pendiente")
        self.assertEqual((filas[pagada.codigo].estado_pago, filas[mora.codigo].estado_pago), ("pagada", "en_mora"))

    def test_regla_10_la_ficha_ofrece_registrar_cobro_si_hay_entregas_cobrables_y_el_actor_es_su_vendedor_o_el_gerente(self):
        """Regla 10 de COM-CNS-SUM: «Registrar cobro» con entregas sin pagar; sin ellas (todas pagadas) no se ofrece."""
        e = self.concretada()
        contrato = Suministro.objects.get(pk=e.contrato_entrega_id)
        self.assertIn("registrar_cobro", suministros.ficha_de_suministro(self.gerente, contrato.pk).acciones)
        self.assertIn("registrar_cobro", suministros.ficha_de_suministro(self.e.vendedor, contrato.pk).acciones)
        cobro([e])
        self.assertNotIn("registrar_cobro", suministros.ficha_de_suministro(self.gerente, contrato.pk).acciones)

    def test_regla_la_tarjeta_de_la_ficha_del_cliente_suma_el_estado_de_pago_y_deja_afuera_lo_cobrado(self):
        """«Completan el ABM de cliente», punto 4: pendiente o en mora (con los días) y sin las pagadas ni las saldadas."""
        mora, pendiente, pagada, saldada = self.en_mora(dias_de_mora=4), self.concretada(), self.concretada(), self.concretada()
        cobro([pagada])
        discrepancia_aceptada(saldada, monto="1000.00", descontado="1000.00")
        filas = {f["codigo"]: f for f in clientes.entregas_sin_cobrar(self.gerente, self.e.cliente)}
        self.assertEqual(sorted(filas), sorted([mora.codigo, pendiente.codigo]))
        self.assertEqual((filas[mora.codigo]["estado_pago"], filas[mora.codigo]["dias_de_mora"], filas[mora.codigo]["texto_del_estado"]), ("en_mora", 4, "En mora · 4 días"))
        self.assertEqual((filas[pendiente.codigo]["estado_pago"], filas[pendiente.codigo]["texto_del_estado"]), ("pendiente", "Pendiente"))

    def test_regla_la_baja_del_cliente_informa_cuantas_entregas_estan_en_mora(self):
        """Regla 1 de COM-BAJ-CLT y «Completan el ABM de cliente», punto 4: «Entregas sin cobrar: 2 (…; 1 en mora)»; no bloquea."""
        self.en_mora()
        self.concretada()
        texto = " ".join(clientes.pendientes_del_cliente(self.e.cliente, self.gerente))
        self.assertIn("Entregas sin cobrar: 2", texto)
        self.assertIn("1 en mora", texto)
        self.concretada()
        self.assertIn("Entregas sin cobrar: 3", " ".join(clientes.pendientes_del_cliente(self.e.cliente, self.gerente)))
