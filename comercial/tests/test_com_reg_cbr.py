# Pruebas de COM-REG-CBR · Registrar Cobro de Suministro (COM-08a, paso 5): `clientes_con_deuda`, `entregas_cobrables`, `resumen_de_cobro` (no escribe), `registrar_cobro`, `cliente_de_la_entrega` (1a y 1a1),
# `reenviar_comprobante_de_cobro`, `cobros_registrados` y `ficha_de_cobro`, y el reintento del comprobante en la parte 4 del paso 50. Una por regla (quién cobra, entrega cobrable, un cliente por cobro, sin pagos
# parciales, monto a cobrar, vencimiento, indemnización por atraso, fecha del pago, medio, el atraso no es un incumplimiento, alerta, avisos), por postcondición (a, b, c, e, f, g; la d, el asiento, es «Fuera de la
# ronda»: se prueba que NO se crea) y por extensión (1a, 1a1, 3a, 5a, 10a, 10b por monto y por fecha, 11a). `verificar_invariantes_de_cobros()` corre al final de cada una (`BaseDeCobranza`).
# Fuente: docs/casos_de_uso/comercial/cobranza.md («COM-REG-CBR», «Por cobrar», «Entregas cobrables», «Registrar el cobro»), D-94 puntos 3, 8, 9, 12 y 13, MD-115, MD-124, MD-125, MD-136, D-57.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa; es lo que `cobranza.md` deja a criterio del código):
# - `DatosDeCobro(cliente_id, entrega_ids, medio_pago)`; `resumen_de_cobro(actor, datos, hoy=None) -> ResumenDeCobro` con `cliente`, `lineas` (`EntregaCobrable`), `base`, `indemnizacion`, `total`, `medio_pago`, `fecha_pago`,
#   `errores` (`{campo: código}`: `sin_entregas_elegidas` en `entregas` y `medio_de_pago_obligatorio` en `medio_pago`), `hay_errores`, `hay_pendientes` y `huella` (un texto JSON);
# - `registrar_cobro(actor, datos, huella, hoy=None) -> PagoCliente`; errores `ValidationError` con `code`: `sin_entregas_elegidas`, `medio_de_pago_obligatorio`, `entregas_de_otro_cliente`, `entrega_no_cobrable`,
#   `entrega_ya_pagada` (con `params` `codigo_entrega`, `cobro`, `fecha` y `quien`), `cobro_cambio` (con `params["cambios"]`: una línea de texto por entrega); `PermissionDenied` (`sin_permiso`);
# - `EntregaCobrable(entrega_id, codigo, contrato_id, contrato_codigo, fecha_concrecion, invernadero, monto_total, descontado, monto_a_cobrar, vencimiento, estado, dias_de_atraso, indemnizacion, solicitudes_pendientes,
#   no_reconocida)`; `ClienteConDeuda(cliente_id, cliente, cantidad, en_mora, total, total_en_mora, entregas)`; `FiltrosDeCobranza(contrato_id, estado)`;
# - `enviar_comprobante_de_cobro(pago_id) -> bool` (fuera de una transacción; solo desde `pendiente_envio`).

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from comercial.models import ClausulaSuministrado, Entrega, LineaPago, PagoCliente, Suministro
from comercial.servicios import cobranza, entregas
from comercial.tests.base_cobranza import HOY, BaseDeCobranza, codigos
from comercial.tests.base_solicitudes import poner_estado
from comercial.tests.fabricas import (
    cliente,
    cobro,
    compra_venta,
    detalle,
    direccion_de_cliente,
    discrepancia,
    discrepancia_aceptada,
    entrega_concretada,
    queja,
    reserva_lista,
)
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import ejercicio_abierto, verificar_invariantes_contables
from core.models import RegistroAuditoria
from maestros.tests.fabricas import crear_transportista, crear_vendedor
from produccion.models import Bitacora

D = Decimal
DatosDeCobro = cobranza.DatosDeCobro


class ComRegCbrServicioTests(BaseDeCobranza):
    def datos(self, entregas_, medio="transferencia", cliente_=None):
        return DatosDeCobro(cliente_id=(cliente_ or self.e.cliente).pk, entrega_ids=[e.pk for e in entregas_], medio_pago=medio)

    def resumen(self, actor, entregas_, medio="transferencia", hoy=HOY, cliente_=None):
        return cobranza.resumen_de_cobro(actor, self.datos(entregas_, medio, cliente_), hoy)

    def cobrar(self, actor, entregas_, medio="transferencia", hoy=HOY, cliente_=None, huella=None, correo=True):
        """Resumen y registro, como la pantalla (la huella es la del resumen o la pasada), con el correo del sistema configurado y los `on_commit` ejecutados."""
        datos = self.datos(entregas_, medio, cliente_)
        with override_settings(CORREO_CONFIGURADO=correo), self.captureOnCommitCallbacks(execute=True):
            resumen = cobranza.resumen_de_cobro(actor, datos, hoy)
            return cobranza.registrar_cobro(actor, datos, resumen.huella if huella is None else huella, hoy)

    def vendedor(self):
        return self.e.vendedor

    def cuantos_cobros(self):
        return PagoCliente.objects.filter(tipo_pago="suministro").count()

    # ---- el flujo principal y las postcondiciones ----

    def test_flujo_principal_el_vendedor_cobra_una_entrega_en_mora_con_su_atraso(self):
        """Pasos 1 a 12: el Vendedor del contrato cobra una entrega que venció hace 5 días: $ 1.000,00 más 5 × $ 300,00 de atraso = $ 2.500,00; queda el cobro COB-NNNN con su línea."""
        e = self.en_mora(dias_de_mora=5)
        resumen = self.resumen(self.vendedor(), [e])
        self.assertEqual((resumen.base, resumen.indemnizacion, resumen.total), (D("1000.00"), D("1500.00"), D("2500.00")))
        self.assertFalse(resumen.hay_errores)
        pago = self.cobrar(self.vendedor(), [e])
        self.assertEqual((pago.tipo_pago, pago.cliente_id, pago.medio_pago, pago.fecha_pago, pago.monto_pagado, pago.estado_pago), ("suministro", self.e.cliente.pk, "transferencia", HOY, D("2500.00"), "vigente"))
        self.assertEqual((pago.usuario_id, pago.compra_venta_id), (self.vendedor().pk, None))
        self.assertRegex(pago.codigo, r"^COB-\d{4,5}$")  # 4 dígitos, o 5 si la numeración de una base de pruebas reutilizada (--keepdb) pasó de 9999
        (linea,) = pago.lineas.all()
        self.assertEqual((linea.entrega_id, linea.monto_cobrado, linea.dias_atraso, linea.indemnizacion_atraso, linea.vigente), (e.pk, D("1000.00"), 5, D("1500.00"), True))

    def test_post_a_el_monto_pagado_suma_lo_a_cobrar_y_el_atraso_de_entregas_de_contratos_distintos_del_mismo_cliente(self):
        """Postcondición a y regla «Un cliente por cobro»: pueden ser de contratos distintos (R116 y R154)."""
        a, b = self.en_mora(dias_de_mora=2), self.concretada()
        pago = self.cobrar(self.vendedor(), [a, b])
        self.assertNotEqual(a.contrato_entrega_id, b.contrato_entrega_id)
        self.assertEqual((pago.monto_pagado, pago.lineas.count()), (D("1000.00") + D("600.00") + D("1000.00"), 2))

    def test_post_b_cada_entrega_queda_pagada_y_su_monto_a_cobrar_no_cambia(self):
        """Postcondición b: «pagada» con el código del cobro; el monto a cobrar sigue siendo el de entonces (una indemnización aceptada después se reintegra)."""
        e = self.concretada()
        pago = self.cobrar(self.vendedor(), [e])
        estado = entregas.estado_de_pago([e.pk], HOY)[e.pk]
        self.assertEqual((estado, estado.cobro.codigo, estado.saldada), ("pagada", pago.codigo, False))
        self.assertEqual(entregas.monto_a_cobrar([e.pk])[e.pk], D("1000.00"))

    def test_post_c_la_indemnizacion_usa_la_clausula_vigente_al_vencer_y_no_la_deHOY(self):
        """Postcondición c y D-94 punto 12: la entrega guarda su indemnización por día; si después cambia la cláusula, lo cobrado no cambia."""
        e = self.en_mora(dias_de_mora=2)
        ClausulaSuministrado.objects.filter(suministro_id=e.contrato_entrega_id).update(indemnizacion_retraso_pago=D("999.00"))
        pago = self.cobrar(self.vendedor(), [e])
        self.assertEqual(pago.lineas.get().indemnizacion_atraso, D("600.00"))

    def test_regla_una_entrega_sin_indemnizacion_guardada_usa_la_clausula_deHOY(self):
        """D-94 punto 12: «si es nula (entregas concretadas antes de COM-08a, solo datos de prueba), la de la cláusula de hoy»."""
        e = self.en_mora(dias_de_mora=2)
        Entrega.objects.filter(pk=e.pk).update(indemnizacion_retraso_dia=None)
        ClausulaSuministrado.objects.filter(suministro_id=e.contrato_entrega_id).update(indemnizacion_retraso_pago=D("50.00"))
        self.assertEqual(self.cobrar(self.vendedor(), [e]).lineas.get().indemnizacion_atraso, D("100.00"))

    def test_regla_el_ejemplo_de_la_regla_vence_el_11_se_paga_el_14_son_3_dias_y_900(self):
        """Regla «Indemnización por atraso en el pago»: 3 días de atraso × $ 300,00 = $ 900,00."""
        e = self.concretada(plazo_pago=10)
        pago = self.cobrar(self.vendedor(), [e], hoy=e.fecha_vencimiento_pago + timedelta(days=3))
        self.assertEqual((pago.lineas.get().dias_atraso, pago.lineas.get().indemnizacion_atraso, pago.monto_pagado, pago.fecha_pago), (3, D("900.00"), D("1900.00"), e.fecha_vencimiento_pago + timedelta(days=3)))

    def test_regla_el_dia_del_vencimiento_se_paga_sin_atraso(self):
        """Regla «Vencimiento del pago»: el día del vencimiento todavía se paga sin atraso."""
        e = self.concretada(plazo_pago=10)
        pago = self.cobrar(self.vendedor(), [e], hoy=e.fecha_vencimiento_pago)
        self.assertEqual((pago.lineas.get().dias_atraso, pago.lineas.get().indemnizacion_atraso), (0, D("0.00")))

    def test_regla_monto_a_cobrar_con_descuento_cobra_lo_que_queda(self):
        """Regla «Monto a cobrar» (MD-115): total − Σ descontado; con $ 200,00 descontados se cobran $ 800,00."""
        e = self.concretada()
        discrepancia_aceptada(e, monto="200.00", descontado="200.00")
        pago = self.cobrar(self.vendedor(), [e])
        self.assertEqual((pago.lineas.get().monto_cobrado, pago.monto_pagado), (D("800.00"), D("800.00")))

    def test_regla_la_indemnizacion_aceptada_despues_del_cobro_se_reintegra_y_no_cambia_el_monto_a_cobrar(self):
        """Regla «Indemnización aceptada después del cobro» (6a de COM-EVL-DSC, con un cobro real): con la entrega cobrada, la aceptación no descuenta (`monto_descontado` 0) y reintegra todo."""
        from comercial.servicios import solicitudes
        from comercial.servicios.solicitudes import DatosDeResolucion

        e = self.concretada()
        solicitud = discrepancia(e, minima=12)
        self.cobrar(self.vendedor(), [e])
        datos = DatosDeResolucion("aceptar", "", "", "efectivo")
        resumen = solicitudes.resumen_de_resolucion(self.gerente, solicitud.pk, datos)
        resuelta = solicitudes.resolver_solicitud(self.gerente, solicitud.pk, datos, resumen.huella)
        self.assertEqual((resuelta.monto_descontado, resuelta.monto_reintegrado > 0), (D("0.00"), True))
        self.assertEqual(entregas.monto_a_cobrar([e.pk])[e.pk], D("1000.00"))

    def test_post_e_la_alerta_pago_en_mora_de_cada_entrega_pasa_a_resuelta(self):
        """Postcondición e: la alerta activa de las entregas elegidas se resuelve con la fecha; la de una entrega no elegida sigue activa."""
        elegida, otra = self.en_mora(), self.en_mora()
        with override_settings(CORREO_CONFIGURADO=False):
            cobranza.reevaluar_mora(Entrega.objects.get(pk=elegida.pk), HOY, False)
            cobranza.reevaluar_mora(Entrega.objects.get(pk=otra.pk), HOY, False)
        self.cobrar(self.vendedor(), [elegida])
        (alerta,) = [v.alerta for v in self.alertas_de(elegida)]
        self.assertEqual((alerta.estado_alerta, alerta.fecha_resolucion is not None), ("resuelta", True))
        self.assertEqual([v.alerta.estado_alerta for v in self.alertas_de(otra)], ["activa"])

    def test_post_f_el_cliente_recibe_el_comprobante_de_cobro(self):
        """Postcondición f y 11: el comprobante (uso interno) con el cliente, el código, la fecha, el medio, cada entrega y el total; queda «enviado»."""
        e = self.en_mora(dias_de_mora=5)
        pago = self.cobrar(self.vendedor(), [e], medio="transferencia")
        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, [self.e.cliente.email_cliente])
        self.assertIn(pago.codigo, mensaje.subject)
        for esperado in (self.e.cliente.nombre_visible, pago.codigo, f"{HOY:%d/%m/%Y}", "Transferencia", e.codigo, e.contrato_entrega.codigo, "1.000,00", "1.500,00", "2.500,00", "sin validez fiscal"):
            self.assertIn(esperado, mensaje.body)
        pago.refresh_from_db()
        self.assertEqual(pago.estado_aviso_cliente, "enviado")

    def test_post_f_si_cobra_el_gerente_se_notifica_al_vendedor_de_cada_contrato(self):
        """Postcondición f y 11: «COB-… registrado» con el cliente, las entregas, el total, el medio y el atraso; el Vendedor que cobra no se avisa a sí mismo."""
        e = self.en_mora(dias_de_mora=5)
        pago = self.cobrar(self.gerente, [e], medio="transferencia")
        (aviso,) = self.avisos(self.e.vendedor, f"{pago.codigo} registrado")
        esperado = f"El Gerente registró el cobro de {self.e.cliente.nombre_visible}: {e.codigo} ({e.contrato_entrega.codigo}), $ 2.500,00 por transferencia, con $ 1.500,00 de atraso."
        self.assertEqual(aviso.detalle, esperado)
        otra = self.concretada()
        pago2 = self.cobrar(self.vendedor(), [otra])
        self.assertEqual(self.avisos(self.e.vendedor, f"{pago2.codigo} registrado"), [])

    def test_post_g_la_auditoria_registra_el_cobro_con_el_actor_el_pago_las_lineas_y_las_alertas(self):
        """Postcondición g (D-36): UN registro `registro_cobro` con el actor y su rol, el pago (principal), sus líneas y las alertas resueltas; por entrega, el monto, los días y la indemnización (como texto)."""
        e = self.en_mora(dias_de_mora=5)
        with override_settings(CORREO_CONFIGURADO=False):
            alerta = cobranza.reevaluar_mora(Entrega.objects.get(pk=e.pk), HOY, False)
        pago = self.cobrar(self.vendedor(), [e])
        registro = RegistroAuditoria.objects.get(accion="registro_cobro")
        self.assertEqual((registro.usuario_id, registro.rol), (self.vendedor().pk, "vendedor"))
        linea = pago.lineas.get()
        self.assertEqual(registro.afectados[0]["id"], pago.pk)
        self.assertTrue(any(a["id"] == linea.pk for a in registro.afectados))
        self.assertTrue(any(a["id"] == alerta.pk for a in registro.afectados))
        self.assertEqual(registro.detalle["cambios"]["monto_pagado"]["despues"], "2500.00")
        self.assertTrue(any("1500.00" in texto and "5" in texto for texto in registro.detalle["datos"]["detalle_de_entregas"]))

    # `test_post_d_no_se_crea_ningun_asiento_en_esta_ronda` (COM-08a, D-57) se REEMPLAZÓ por `ComRegCbrAsientoTests` (CON-04d): la regla cambió, el cobro ahora asienta (D-92 punto 6).

    # ---- reglas: quién cobra y qué se cobra ----

    def test_regla_quien_cobra_el_vendedor_del_contrato_y_el_gerente(self):
        """Regla «Quién cobra»: el Vendedor del contrato o el Gerente."""
        self.assertEqual(self.cobrar(self.vendedor(), [self.concretada()]).usuario_id, self.vendedor().pk)
        self.assertEqual(self.cobrar(self.gerente, [self.concretada()]).usuario_id, self.gerente.pk)

    def test_regla_el_vendedor_de_otro_contrato_no_cobra_y_no_cambia_nada(self):
        """Alcance (D-28): otro Vendedor ve y cobra solo sus contratos; `PermissionDenied` y nada registrado."""
        e = self.concretada()
        ajeno = crear_vendedor(email="otro@infoponia.com")
        with self.assertRaises(PermissionDenied):
            self.resumen(ajeno, [e])
        with self.assertRaises(PermissionDenied):
            self.cobrar(ajeno, [e], huella="{}")
        self.assertEqual(self.cuantos_cobros(), 0)

    def test_regla_los_demas_roles_y_las_cuentas_inactivas_no_cobran(self):
        """Solo el Gerente y el Vendedor, y activos (se verifica después de bloquear)."""
        e = self.concretada()
        for actor in (crear_transportista(email="t@infoponia.com"), self.e.agronomo):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.cobrar(actor, [e], huella="{}")
        resumen = self.resumen(self.vendedor(), [e])
        type(self.vendedor()).objects.filter(pk=self.vendedor().pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            cobranza.registrar_cobro(self.vendedor(), self.datos([e]), resumen.huella, HOY)
        self.assertEqual(self.cuantos_cobros(), 0)

    def test_regla_un_contrato_finalizado_o_resuelto_se_cobra_igual(self):
        """Regla «Entrega cobrable»: cualquiera sea el estado del contrato."""
        for estado in ("finalizado", "resuelto"):
            with self.subTest(estado=estado):
                e = self.concretada()
                poner_estado(Suministro.objects.get(pk=e.contrato_entrega_id), estado)
                self.assertEqual(self.cobrar(self.vendedor(), [e]).lineas.count(), 1)

    def test_regla_un_cliente_inactivo_conserva_el_cobro_de_sus_suministros(self):
        """Regla «Entrega cobrable» (reglas 1 y 2 de 8.18): aunque el cliente esté inactivo."""
        e = self.concretada()
        type(self.e.cliente).objects.filter(pk=self.e.cliente.pk).update(estado_cliente="inactivo")
        self.assertEqual(self.cobrar(self.vendedor(), [e]).lineas.count(), 1)

    def test_regla_no_son_cobrables_una_saldada_una_sin_concretar_ni_una_de_compra_venta(self):
        """`entrega_no_cobrable`: saldada (monto 0), «a realizar» o de compra-venta."""
        from comercial.tests.fabricas import detalle_suministro, entrega, suministro

        saldada = self.concretada()
        discrepancia_aceptada(saldada, monto="1000.00", descontado="1000.00")
        contrato = suministro(self.e)
        d = detalle_suministro(contrato, self.e.variedad, cantidad=10, primera_en_dias=0)
        a_realizar = entrega(contrato, [reserva_lista(None, self.lote, 10, fecha_entrega=d.fecha_primer_entrega, detalle_suministro=d)])
        venta = compra_venta(self.e, dias=0)
        de_venta = entrega_concretada(venta, [reserva_lista(detalle(venta, self.e.variedad, 10), self.lote, 10)], con_pago=True)
        for e in (saldada, a_realizar, de_venta):
            with self.subTest(entrega=e.codigo):
                error = self.rechazo(cobranza.registrar_cobro, self.vendedor(), self.datos([e]), "{}", HOY)
                self.assertEqual(codigos(error), ["entrega_no_cobrable"])
        self.assertEqual(self.cuantos_cobros(), 0)

    def test_regla_un_cliente_por_cobro_rechaza_entregas_de_otro_cliente(self):
        """Regla «Un cliente por cobro»: `entregas_de_otro_cliente`; nada registrado."""
        otro_cliente = cliente(razon_social="Otro S.A.", email="otro@cliente.com")
        direccion_de_cliente(otro_cliente)
        mia, ajena = self.concretada(), self.concretada(cliente_=otro_cliente)
        error = self.rechazo(cobranza.registrar_cobro, self.gerente, self.datos([mia, ajena]), "{}", HOY)
        self.assertEqual(codigos(error), ["entregas_de_otro_cliente"])
        self.assertEqual(self.cuantos_cobros(), 0)

    def test_regla_sin_pagos_parciales_se_cobra_cada_entrega_completa_y_una_sola_vez(self):
        """Regla «Sin pagos parciales»: lo cobrado es el monto a cobrar entero; la misma entrega no se cobra dos veces."""
        e = self.concretada()
        self.assertEqual(self.cobrar(self.vendedor(), [e]).lineas.get().monto_cobrado, D("1000.00"))
        with self.assertRaises(Exception) as c:
            self.cobrar(self.vendedor(), [e])
        self.assertEqual(codigos(c.exception), ["entrega_ya_pagada"])

    def test_regla_el_atraso_no_es_un_incumplimiento_de_la_empresa(self):
        """Regla «El atraso no es un incumplimiento»: ni suma al contador del contrato ni escribe la bitácora; tampoco toca la entrega."""
        e = self.en_mora(dias_de_mora=4)
        antes = (Suministro.objects.get(pk=e.contrato_entrega_id).cantidad_incumplimientos, Bitacora.objects.count())
        self.cobrar(self.vendedor(), [e])
        despues = (Suministro.objects.get(pk=e.contrato_entrega_id).cantidad_incumplimientos, Bitacora.objects.count())
        self.assertEqual(antes, despues)
        nueva = Entrega.objects.get(pk=e.pk)
        self.assertEqual((nueva.estado_orden, nueva.monto_total_entrega, nueva.fecha_vencimiento_pago), (e.estado_orden, e.monto_total_entrega, e.fecha_vencimiento_pago))

    def test_regla_la_secuencia_da_numeros_consecutivos(self):
        """D-94 punto 3: `COB-0032`, de la secuencia (sin `max()+1`)."""
        a = self.cobrar(self.vendedor(), [self.concretada()])
        b = self.cobrar(self.vendedor(), [self.concretada()])
        self.assertEqual(b.numero, a.numero + 1)

    # ---- extensiones ----

    def test_ext_5a_sin_entregas_elegidas_lo_dice_y_no_registra(self):
        """5a: «hay que elegir al menos una entrega»: error del resumen y `sin_entregas_elegidas` al registrar."""
        resumen = self.resumen(self.vendedor(), [])
        self.assertEqual(resumen.errores.get("entregas"), "sin_entregas_elegidas")
        error = self.rechazo(cobranza.registrar_cobro, self.vendedor(), self.datos([]), resumen.huella, HOY)
        self.assertEqual(codigos(error), ["sin_entregas_elegidas"])

    def test_regla_el_medio_de_pago_es_obligatorio_y_de_la_lista(self):
        """Paso 7 y regla «Medio de pago»: efectivo, transferencia, tarjeta de débito o crédito; sin medio o con otro, `medio_de_pago_obligatorio`."""
        e = self.concretada()
        for medio in ("", "cheque"):
            with self.subTest(medio=medio):
                self.assertEqual(self.resumen(self.vendedor(), [e], medio=medio).errores.get("medio_pago"), "medio_de_pago_obligatorio")
                error = self.rechazo(cobranza.registrar_cobro, self.vendedor(), self.datos([e], medio), self.resumen(self.vendedor(), [e], medio=medio).huella, HOY)
                self.assertEqual(codigos(error), ["medio_de_pago_obligatorio"])
        for medio in ("efectivo", "transferencia", "tarjeta_debito", "tarjeta_credito"):
            self.assertFalse(self.resumen(self.vendedor(), [e], medio=medio).hay_errores)

    def test_ext_3a_el_resumen_advierte_la_solicitud_pendiente_y_deja_cobrar(self):
        """3a: la solicitud pendiente (tipo, número y fecha) se señala; si se cobra ahora y se acepta después, se reintegra; el actor puede elegir igual esa entrega."""
        e = self.concretada()
        solicitud = discrepancia(e, minima=12)
        resumen = self.resumen(self.vendedor(), [e])
        self.assertTrue(resumen.hay_pendientes)
        (pendiente,) = resumen.lineas[0].solicitudes_pendientes
        self.assertEqual((pendiente.codigo, pendiente.tipo, pendiente.fecha), (solicitud.codigo, "discrepancia", solicitud.fecha_solicitud))
        self.assertEqual(self.cobrar(self.vendedor(), [e]).lineas.count(), 1)

    def test_ext_10a_si_otra_sesion_ya_cobro_la_entrega_informa_el_cobro_la_fecha_y_quien(self):
        """10a: `entrega_ya_pagada` con el cobro, su fecha y quién lo registró; nada nuevo registrado."""
        e = self.concretada()
        resumen = self.resumen(self.vendedor(), [e])
        previo = self.cobrar(self.gerente, [e])
        error = self.rechazo(cobranza.registrar_cobro, self.vendedor(), self.datos([e]), resumen.huella, HOY)
        self.assertEqual(codigos(error), ["entrega_ya_pagada"])
        params = error.error_dict["__all__"][0].params
        self.assertEqual((params["cobro"], params["fecha"], self.gerente.email in params["quien"]), (previo.codigo, f"{HOY:%d/%m/%Y}", True))
        self.assertEqual(self.cuantos_cobros(), 1)

    def test_ext_10b_si_se_acepto_una_solicitud_mientras_tanto_cambia_el_monto_y_vuelve_con_los_montos_nuevos(self):
        """10b: el monto a cobrar cambió: `cobro_cambio` con el anterior y el nuevo de cada entrega; nada registrado; con un resumen nuevo se cobra el monto nuevo."""
        e = self.concretada()
        resumen = self.resumen(self.vendedor(), [e])
        discrepancia_aceptada(e, monto="200.00", descontado="200.00")
        error = self.rechazo(cobranza.registrar_cobro, self.vendedor(), self.datos([e]), resumen.huella, HOY)
        self.assertEqual(codigos(error), ["cobro_cambio"])
        (cambio,) = error.error_dict["__all__"][0].params["cambios"]
        self.assertIn(e.codigo, cambio)
        self.assertIn("1.000,00", cambio)
        self.assertIn("800,00", cambio)
        self.assertEqual(self.cuantos_cobros(), 0)
        self.assertEqual(self.cobrar(self.vendedor(), [e]).monto_pagado, D("800.00"))

    def test_ext_10b_si_cambio_la_fecha_actual_cambia_el_atraso_y_lo_dice(self):
        """10b («o cambió la fecha actual», D-94 punto 9): la huella incluye la fecha de hoy; con otro día, `cobro_cambio`."""
        e = self.concretada(plazo_pago=10)
        resumen = self.resumen(self.vendedor(), [e], hoy=e.fecha_vencimiento_pago)
        error = self.rechazo(cobranza.registrar_cobro, self.vendedor(), self.datos([e]), resumen.huella, e.fecha_vencimiento_pago + timedelta(days=1))
        self.assertEqual(codigos(error), ["cobro_cambio"])
        self.assertEqual(self.cuantos_cobros(), 0)

    def test_ext_11a_si_el_correo_falla_el_cobro_permanece_pendiente_de_envio_y_se_reenvia(self):
        """11a: el cobro queda registrado con el comprobante «pendiente de envío»; «Reenviar comprobante» lo manda y pasa a «enviado»."""
        e = self.concretada()
        with mock.patch("core.correo.enviar_correo", return_value=False):
            pago = self.cobrar(self.vendedor(), [e])
        pago.refresh_from_db()
        self.assertEqual((pago.estado_aviso_cliente, len(mail.outbox)), ("pendiente_envio", 0))
        with override_settings(CORREO_CONFIGURADO=True):
            self.assertTrue(cobranza.reenviar_comprobante_de_cobro(self.vendedor(), pago.pk))
        pago.refresh_from_db()
        self.assertEqual((pago.estado_aviso_cliente, len(mail.outbox)), ("enviado", 1))

    def test_ext_11a_sin_el_correo_del_sistema_queda_pendiente_sin_intentar(self):
        """Sin el correo del sistema (D-35): no se intenta, queda «pendiente de envío»."""
        pago = self.cobrar(self.vendedor(), [self.concretada()], correo=False)
        pago.refresh_from_db()
        self.assertEqual((pago.estado_aviso_cliente, len(mail.outbox)), ("pendiente_envio", 0))

    def test_ext_11a_un_cliente_sin_correo_queda_sin_correo_y_no_se_reenvia(self):
        """Regla 18 de 8.20: sin correo, `sin_correo` (la ficha ofrece «Imprimir»); reenviar es `cliente_sin_correo` o `comprobante_no_pendiente`."""
        e = self.concretada()
        type(self.e.cliente).objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        pago = self.cobrar(self.vendedor(), [e])
        pago.refresh_from_db()
        self.assertEqual((pago.estado_aviso_cliente, len(mail.outbox)), ("sin_correo", 0))
        error = self.rechazo(cobranza.reenviar_comprobante_de_cobro, self.vendedor(), pago.pk)
        self.assertEqual(codigos(error), ["comprobante_no_pendiente"])

    def test_ext_11a_reenviar_exige_el_alcance_y_que_este_pendiente(self):
        """«Reenviar comprobante»: el Vendedor del contrato o el Gerente; con el comprobante ya enviado, `comprobante_no_pendiente`; otro Vendedor, `PermissionDenied`."""
        pago = self.cobrar(self.vendedor(), [self.concretada()])
        error = self.rechazo(cobranza.reenviar_comprobante_de_cobro, self.vendedor(), pago.pk)
        self.assertEqual(codigos(error), ["comprobante_no_pendiente"])
        with self.assertRaises(PermissionDenied):
            cobranza.reenviar_comprobante_de_cobro(crear_vendedor(email="ajeno@infoponia.com"), pago.pk)

    def test_regla_si_falla_la_auditoria_no_queda_nada(self):
        """Garantía mínima 1: atomicidad. Sin su registro de auditoría no queda el cobro, ni las líneas, ni la alerta resuelta, ni el aviso."""
        e = self.en_mora()
        with override_settings(CORREO_CONFIGURADO=False):
            cobranza.reevaluar_mora(Entrega.objects.get(pk=e.pk), HOY, False)
        with mock.patch("comercial.servicios.cobranza.RegistroAuditoria.objects.registrar", side_effect=RuntimeError("falla")), self.assertRaises(RuntimeError):
            self.cobrar(self.gerente, [e])
        self.assertEqual((self.cuantos_cobros(), LineaPago.objects.count(), len(self.alertas_de(e, activas=True)), self.avisos(self.e.vendedor, "COB-")), (0, 0, 1, []))

    def test_regla_el_resumen_no_escribe_nada(self):
        """Paso 8 (`revisar/` no escribe): el resumen no crea cobro, línea, auditoría ni aviso, y no consume la secuencia."""
        e = self.en_mora()
        with CaptureQueriesContext(connection) as consultas:
            self.resumen(self.vendedor(), [e])
        escrituras = [q["sql"] for q in consultas.captured_queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) or "nextval" in q["sql"]]
        self.assertEqual(escrituras, [])

    # ---- 1a y 1a1: desde la alerta ----

    def test_ext_1a_desde_la_alerta_se_abre_con_el_cliente_de_esa_entrega(self):
        """1a: el cliente de la entrega de la alerta (la pantalla la deja ya elegida)."""
        e = self.en_mora()
        self.assertEqual(cobranza.cliente_de_la_entrega(self.gerente, e.pk), self.e.cliente.pk)

    def test_ext_1a1_si_la_entrega_de_la_alerta_ya_esta_pagada_informa_el_cobro_y_termina(self):
        """1a1: `entrega_ya_pagada` con el cobro, su fecha y quién lo registró."""
        e = self.en_mora()
        pago = cobro([e], usuario=self.gerente)
        error = self.rechazo(cobranza.cliente_de_la_entrega, self.gerente, e.pk)
        self.assertEqual(codigos(error), ["entrega_ya_pagada"])
        self.assertEqual(error.error_dict["__all__"][0].params["cobro"], pago.codigo)

    def test_ext_1a_el_vendedor_ajeno_no_abre_la_entrega(self):
        """Alcance: un Vendedor de otro contrato recibe `PermissionDenied`; una entrega que no existe, `Http404`."""
        e = self.en_mora()
        with self.assertRaises(PermissionDenied):
            cobranza.cliente_de_la_entrega(crear_vendedor(email="ajeno2@infoponia.com"), e.pk)
        with self.assertRaises(Http404):
            cobranza.cliente_de_la_entrega(self.gerente, 999999)


class PorCobrarTests(BaseDeCobranza):
    """Pasos 2 y 4 de COM-REG-CBR: los clientes con deuda y sus entregas cobrables."""

    def test_regla_clientes_con_deuda_agrupa_por_cliente_con_sus_totales(self):
        """Paso 2: por cliente, la cantidad de entregas sin pagar, cuántas en mora, el total a cobrar y el total en mora; de la A a la Z."""
        otro = cliente(razon_social="Aaa Verdulería", email="a@a.com")
        direccion_de_cliente(otro)
        self.en_mora(), self.concretada(), self.concretada(cliente_=otro)
        grupos = cobranza.clientes_con_deuda(self.gerente, HOY)
        self.assertEqual([g.cliente for g in grupos], sorted(g.cliente for g in grupos))
        propio = next(g for g in grupos if g.cliente_id == self.e.cliente.pk)
        self.assertEqual((propio.cantidad, propio.en_mora, propio.total, propio.total_en_mora, len(propio.entregas)), (2, 1, D("2000.00"), D("1000.00"), 2))

    def test_regla_no_entran_las_pagadas_ni_las_saldadas(self):
        """Regla «Entrega cobrable»: sin línea vigente y con monto a cobrar mayor que cero."""
        pagada, saldada, sin_pagar = self.concretada(), self.concretada(), self.concretada()
        cobro([pagada])
        discrepancia_aceptada(saldada, monto="1000.00", descontado="1000.00")
        (grupo,) = cobranza.clientes_con_deuda(self.gerente, HOY)
        self.assertEqual([e.entrega_id for e in grupo.entregas], [sin_pagar.pk])

    def test_regla_el_vendedor_ve_solo_los_clientes_de_sus_contratos(self):
        """Alcance: el Vendedor, los contratos de los que es Vendedor (D-28); los demás roles, `PermissionDenied`."""
        ajeno = crear_vendedor(email="ajeno3@infoponia.com")
        self.concretada()
        self.assertEqual(len(cobranza.clientes_con_deuda(self.vendedor_(), HOY)), 1)
        self.assertEqual(cobranza.clientes_con_deuda(ajeno, HOY), [])
        with self.assertRaises(PermissionDenied):
            cobranza.clientes_con_deuda(self.e.agronomo, HOY)

    def vendedor_(self):
        return self.e.vendedor

    def test_regla_las_entregas_van_de_la_que_vence_primero_a_la_ultima_con_todo_lo_que_pide_el_paso_4(self):
        """Paso 4: contrato, fecha de concreción, invernadero de origen, monto total, descontado, monto a cobrar, vencimiento, estado, días de atraso e indemnización a la fecha del pago."""
        tarde = self.concretada(plazo_pago=10)
        vencida = self.en_mora(dias_de_mora=5)
        discrepancia_aceptada(vencida, monto="100.00", descontado="100.00")
        filas = cobranza.entregas_cobrables(self.gerente, self.e.cliente.pk, HOY)
        self.assertEqual([f.entrega_id for f in filas], [vencida.pk, tarde.pk])
        f = filas[0]
        self.assertEqual((f.codigo, f.contrato_codigo, f.fecha_concrecion, str(f.invernadero)), (vencida.codigo, vencida.contrato_entrega.codigo, vencida.fecha_resolucion_orden, str(vencida.invernadero)))
        self.assertEqual((f.monto_total, f.descontado, f.monto_a_cobrar, f.vencimiento, f.estado, f.dias_de_atraso, f.indemnizacion), (D("1000.00"), D("100.00"), D("900.00"), vencida.fecha_vencimiento_pago, "en_mora", 5, D("1500.00")))
        self.assertEqual((filas[1].estado, filas[1].dias_de_atraso, filas[1].indemnizacion), ("pendiente", 0, D("0.00")))

    def test_regla_la_indemnizacion_se_calcula_a_la_fecha_del_pago_que_se_pide(self):
        """Paso 6 (y 7a de COM-ANL-CBR): `fecha_pago` cambia el atraso."""
        e = self.concretada(plazo_pago=10)
        (f,) = cobranza.entregas_cobrables(self.gerente, self.e.cliente.pk, HOY, fecha_pago=e.fecha_vencimiento_pago + timedelta(days=2))
        self.assertEqual((f.dias_de_atraso, f.indemnizacion), (2, D("600.00")))

    def test_regla_los_filtros_son_el_contrato_y_el_estado_de_pago(self):
        """Lista de tecnología, 4: filtrar por contrato y por estado («pendiente» o «en mora»)."""
        a, b = self.en_mora(), self.concretada()
        todos = cobranza.entregas_cobrables(self.gerente, self.e.cliente.pk, HOY)
        solo_mora = cobranza.entregas_cobrables(self.gerente, self.e.cliente.pk, HOY, cobranza.FiltrosDeCobranza(estado="en_mora"))
        solo_pendientes = cobranza.entregas_cobrables(self.gerente, self.e.cliente.pk, HOY, cobranza.FiltrosDeCobranza(estado="pendiente"))
        un_contrato = cobranza.entregas_cobrables(self.gerente, self.e.cliente.pk, HOY, cobranza.FiltrosDeCobranza(contrato_id=b.contrato_entrega_id))
        self.assertEqual(([f.entrega_id for f in todos], [f.entrega_id for f in solo_mora], [f.entrega_id for f in solo_pendientes], [f.entrega_id for f in un_contrato]), ([a.pk, b.pk], [a.pk], [b.pk], [b.pk]))

    def test_ext_3a_la_entrega_con_una_solicitud_pendiente_la_trae_y_la_no_reconocida_se_marca(self):
        """3a y paso 4: la solicitud pendiente con su tipo, número y fecha; COM-06b: la entrega no reconocida lleva su marca."""
        from comercial.tests.fabricas import alerta_no_reconocida

        e = self.concretada()
        solicitud = queja(e)
        alerta_no_reconocida(e)
        (f,) = cobranza.entregas_cobrables(self.gerente, self.e.cliente.pk, HOY)
        self.assertEqual([(p.codigo, p.tipo) for p in f.solicitudes_pendientes], [(solicitud.codigo, "queja")])
        self.assertTrue(f.no_reconocida)

    def test_regla_sin_consultas_por_fila(self):
        """Requisito especial (2 segundos): la misma cantidad de consultas con una entrega que con cinco, en los grupos y en la lista del cliente."""
        self.concretada()
        with CaptureQueriesContext(connection) as pocas_g:
            cobranza.clientes_con_deuda(self.gerente, HOY)
        with CaptureQueriesContext(connection) as pocas_e:
            cobranza.entregas_cobrables(self.gerente, self.e.cliente.pk, HOY)
        for _ in range(4):
            e = self.concretada()
            queja(e)
        with CaptureQueriesContext(connection) as muchas_g:
            cobranza.clientes_con_deuda(self.gerente, HOY)
        with CaptureQueriesContext(connection) as muchas_e:
            cobranza.entregas_cobrables(self.gerente, self.e.cliente.pk, HOY)
        self.assertEqual((len(pocas_g), len(pocas_e)), (len(muchas_g), len(muchas_e)))


class CobrosRegistradosTests(BaseDeCobranza):
    """«Cobros registrados» y la ficha del cobro (prototipo `tabCobranza`; la ficha no está en el prototipo)."""

    def test_regla_la_lista_trae_el_cobro_el_cliente_las_entregas_el_medio_el_monto_y_el_atraso(self):
        """La lista: código con su fecha, cliente, entregas, medio, monto con «incluye $ … por atraso» y estado «Vigente»."""
        e = self.en_mora(dias_de_mora=2)
        pago = cobro([e], usuario=self.gerente, medio="efectivo")
        lista = cobranza.cobros_registrados(self.gerente)
        (fila,) = lista.filas
        self.assertEqual((fila.pago_id, fila.codigo, fila.fecha, fila.cliente, fila.entregas, fila.medio, fila.monto, fila.atraso, fila.estado), (pago.pk, pago.codigo, HOY, self.e.cliente.nombre_visible, [e.codigo], "Efectivo", D("1600.00"), D("600.00"), "vigente"))

    def test_regla_el_vendedor_ve_solo_los_cobros_de_sus_contratos(self):
        """Alcance: el Vendedor ve los cobros con entregas de sus contratos; otro, ninguno; la ficha ajena es 403."""
        pago = cobro([self.concretada()])
        ajeno = crear_vendedor(email="ajeno4@infoponia.com")
        self.assertEqual(len(cobranza.cobros_registrados(self.e.vendedor).filas), 1)
        self.assertEqual(len(cobranza.cobros_registrados(ajeno).filas), 0)
        with self.assertRaises(PermissionDenied):
            cobranza.ficha_de_cobro(ajeno, pago.pk)

    def test_regla_un_pago_de_compra_venta_no_es_un_cobro_de_suministro(self):
        """El pago de una compra-venta no está en la lista y su ficha es 404 (se ve en la ficha de la venta)."""
        venta = compra_venta(self.e, dias=0)
        de_venta = entrega_concretada(venta, [reserva_lista(detalle(venta, self.e.variedad, 10), self.lote, 10)], con_pago=True)
        self.assertEqual(cobranza.cobros_registrados(self.gerente).filas, [])
        with self.assertRaises(Http404):
            cobranza.ficha_de_cobro(self.gerente, venta.pagos.get().pk)

    def test_regla_la_ficha_trae_las_entregas_con_lo_cobrado_el_atraso_y_el_estado_del_comprobante(self):
        """La ficha: el cobro, sus entregas con lo cobrado y el atraso, el estado del comprobante con «Reenviar» o «Imprimir»."""
        e = self.en_mora(dias_de_mora=2)
        pago = cobro([e], usuario=self.gerente, aviso="pendiente_envio")
        ficha = cobranza.ficha_de_cobro(self.gerente, pago.pk)
        self.assertEqual((ficha.codigo, ficha.total, ficha.indemnizacion, ficha.estado, ficha.puede_reenviar, ficha.puede_imprimir), (pago.codigo, D("1600.00"), D("600.00"), "vigente", True, False))
        (linea,) = ficha.lineas
        self.assertEqual((linea.codigo, linea.monto_cobrado, linea.dias_atraso, linea.indemnizacion), (e.codigo, D("1000.00"), 2, D("600.00")))
        sin_correo = cobranza.ficha_de_cobro(self.gerente, cobro([self.concretada()], aviso="sin_correo").pk)
        self.assertEqual((sin_correo.puede_reenviar, sin_correo.puede_imprimir), (False, True))


class Paso50ReintentaElComprobanteTests(BaseDeCobranza):
    """La parte 4 del paso 50 («Correos pendientes», `entregas.md`) suma los pagos con `estado_aviso_cliente = pendiente_envio` (D-94 punto 13)."""

    def test_regla_el_paso_50_reintenta_el_comprobante_de_cobro_pendiente(self):
        """El comprobante pendiente sale en el paso 50 y queda «enviado»; uno ya enviado no se vuelve a mandar."""
        pendiente = cobro([self.concretada()], aviso="pendiente_envio")
        enviado = cobro([self.concretada()], aviso="enviado")
        with override_settings(CORREO_CONFIGURADO=True):
            entregas.planificar_entregas(HOY)
        pendiente.refresh_from_db()
        enviado.refresh_from_db()
        self.assertEqual((pendiente.estado_aviso_cliente, enviado.estado_aviso_cliente, len(mail.outbox)), ("enviado", "enviado", 1))

    def test_regla_el_reintento_cuenta_en_los_procesados_del_paso(self):
        """El resumen del paso suma los pagos revisados."""
        cobro([self.concretada()], aviso="pendiente_envio")
        with override_settings(CORREO_CONFIGURADO=False):
            sin = entregas.planificar_entregas(HOY)
        cobro([self.concretada()], aviso="pendiente_envio")
        with override_settings(CORREO_CONFIGURADO=False):
            con = entregas.planificar_entregas(HOY)
        self.assertEqual(con.procesados, sin.procesados + 1)


class ComRegCbrFechaDelCobroAnuladoTests(BaseDeCobranza):
    """COM-08b (paso 3 de la tarea; D-94 punto 10): la regla «Fecha del pago» de COM-REG-CBR sigue siendo «hoy, nunca una fecha anterior» **salvo** en el camino de 7a de COM-ANL-CBR (`DatosDeCobro.anulacion_id` y
    `usar_fecha_anulada`). Los casos de 7a con sus límites están en `test_com_anl_cbr.py`; acá, los dos códigos de error que `cobranza.md` («Registrar el cobro») asigna a COM-REG-CBR: `fecha_no_admitida` y
    `anulacion_ya_usada`."""

    LUEGO = HOY + timedelta(days=4)

    def cobro_anulado(self, *, pago_en_fecha=True):
        """Un cobro de dos entregas en mora, registrado hoy por el Gerente y anulado 4 días después. Devuelve `(anulacion, e1, e2)`."""
        e1, e2 = self.en_mora(dias_de_mora=3), self.en_mora(dias_de_mora=3)
        datos = DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[e1.pk, e2.pk], medio_pago="efectivo")
        pago = cobranza.registrar_cobro(self.gerente, datos, cobranza.resumen_de_cobro(self.gerente, datos, HOY).huella, HOY)
        previo = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, self.LUEGO)
        return cobranza.anular_cobro(self.gerente, pago.pk, "Error de carga.", pago_en_fecha, previo.huella, self.LUEGO), e1, e2

    def datos(self, entregas_, **extra):
        return DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[e.pk for e in entregas_], medio_pago="efectivo", **extra)

    def test_regla_fecha_del_pago_sin_la_anulacion_que_la_justifica_se_rechaza_con_fecha_no_admitida(self):
        """`usar_fecha_anulada` sin `anulacion_id` (una fecha anterior sin la anulación que la justifica): `fecha_no_admitida`, en el resumen y en el registro; no se cobra nada."""
        e = self.en_mora(dias_de_mora=3)
        datos = self.datos([e], usar_fecha_anulada=True)
        self.assertEqual(codigos(self.rechazo(cobranza.resumen_de_cobro, self.gerente, datos, HOY)), ["fecha_no_admitida"])
        huella = cobranza.resumen_de_cobro(self.gerente, self.datos([e]), HOY).huella
        self.assertEqual(codigos(self.rechazo(cobranza.registrar_cobro, self.gerente, datos, huella, HOY)), ["fecha_no_admitida"])
        self.assertEqual(PagoCliente.objects.filter(tipo_pago="suministro").count(), 0)

    def test_regla_fecha_del_pago_sin_7a_es_siempre_la_de_hoy(self):
        """Sin el camino de 7a, la fecha del cobro es la de hoy aunque exista una anulación con `cliente_pago_en_fecha`: `fecha_pago = hoy`, `anulacion_corregida` nula."""
        anulacion_, e1, _ = self.cobro_anulado()
        datos = self.datos([e1], anulacion_id=anulacion_.pk)
        pago = cobranza.registrar_cobro(self.gerente, datos, cobranza.resumen_de_cobro(self.gerente, datos, self.LUEGO).huella, self.LUEGO)
        self.assertEqual((pago.fecha_pago, pago.anulacion_corregida_id), (self.LUEGO, None))

    def test_regla_fecha_del_pago_el_resumen_de_7a_muestra_la_fecha_del_cobro_anulado(self):
        """Paso 8 con 7a: el resumen muestra la fecha del cobro anulado y, en la huella, esa fecha: la pantalla vuelve al paso 6 si cambia."""
        anulacion_, e1, e2 = self.cobro_anulado()
        datos = self.datos([e1, e2], anulacion_id=anulacion_.pk, usar_fecha_anulada=True)
        resumen = cobranza.resumen_de_cobro(self.gerente, datos, self.LUEGO)
        self.assertEqual((resumen.fecha_pago, resumen.indemnizacion), (HOY, D("1800.00")))
        self.assertNotEqual(resumen.huella, cobranza.resumen_de_cobro(self.gerente, self.datos([e1, e2], anulacion_id=anulacion_.pk), self.LUEGO).huella)

    def test_regla_fecha_del_pago_con_7a_nunca_es_posterior_a_hoy(self):
        """«Nunca posterior» (`cobranza.md`, «Fecha del pago»): la fecha de 7a es la del cobro anulado, que no puede ser futura; si el reloj retrocede (`hoy` anterior a la fecha del cobro anulado), `fecha_no_admitida`."""
        anulacion_, e1, _ = self.cobro_anulado()
        datos = self.datos([e1], anulacion_id=anulacion_.pk, usar_fecha_anulada=True)
        self.assertEqual(codigos(self.rechazo(cobranza.resumen_de_cobro, self.gerente, datos, HOY - timedelta(days=1))), ["fecha_no_admitida"])

    def test_ext_anulacion_ya_usada_el_segundo_cobro_correcto_de_la_misma_anulacion_se_rechaza(self):
        """`anulacion_ya_usada` («El cobro correcto de esa anulación ya se registró»): el primer cobro correcto confirma; el segundo, aunque sea de la otra entrega del cobro anulado, no se registra."""
        anulacion_, e1, e2 = self.cobro_anulado()
        primero = self.datos([e1], anulacion_id=anulacion_.pk, usar_fecha_anulada=True)
        cobranza.registrar_cobro(self.gerente, primero, cobranza.resumen_de_cobro(self.gerente, primero, self.LUEGO).huella, self.LUEGO)
        segundo = self.datos([e2], anulacion_id=anulacion_.pk, usar_fecha_anulada=True)
        error = self.rechazo(cobranza.resumen_de_cobro, self.gerente, segundo, self.LUEGO)
        self.assertEqual(codigos(error), ["anulacion_ya_usada"])
        self.assertIn("ya se registró", " ".join(error.messages))
        huella = cobranza.resumen_de_cobro(self.gerente, self.datos([e2]), self.LUEGO).huella
        self.assertEqual(codigos(self.rechazo(cobranza.registrar_cobro, self.gerente, segundo, huella, self.LUEGO)), ["anulacion_ya_usada"])
        self.assertEqual(PagoCliente.objects.filter(tipo_pago="suministro", estado_pago="vigente").count(), 1)


class ComRegCbrAsientoTests(BaseDeCobranza):
    """CON-04d · paso 1: el asiento del cobro (COM-REG-CBR postcondición d; D-92 puntos 3 a 6 y 9; D-86). UN asiento compuesto con el `PagoCliente` como origen y la fecha del cobro (`fecha_pago`, D-92 punto 4):
    Debe Caja (efectivo) o Banco c/c (los demás medios) por `monto_pagado` / Haber Deudores por Ventas por Σ `monto_cobrado` / Haber Indemnizaciones por Atraso en el Pago por Σ `indemnizacion_atraso`, solo si es mayor que 0.
    Decisiones del estudiante del 26/11/2026: (1) el cobro que corrige uno anulado (7a) asienta con la `fecha_pago` y no con la actual; (2) sin transición para Deudores por Ventas."""

    def cobrar(self, actor, entregas_, medio="transferencia", hoy=HOY, **extra):
        """Resumen y registro, como la pantalla, con los `on_commit` ejecutados."""
        datos = DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[e.pk for e in entregas_], medio_pago=medio, **extra)
        with override_settings(CORREO_CONFIGURADO=False), self.captureOnCommitCallbacks(execute=True):
            return cobranza.registrar_cobro(actor, datos, cobranza.resumen_de_cobro(actor, datos, hoy).huella, hoy)

    def lineas(self, asiento):
        """`[(cuenta, tipo, importe)]` del asiento, ordenado (el compuesto no fija el orden de sus líneas)."""
        return sorted((m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.select_related("cuenta"))

    def asiento_de(self, pago):
        return AsientoContable.objects.get(origen_id=pago.pk)

    def test_post_d_un_asiento_compuesto_con_atraso_va_contra_banco_deudores_e_indemnizaciones_por_atraso(self):
        """Postcondición d: una entrega en mora 5 días ($ 1.000,00 + 5 × $ 300,00): Debe Banco c/c 2.500,00 / Haber Deudores por Ventas 1.000,00 / Haber Indemnizaciones por Atraso 1.500,00, originado en el pago, con la fecha de hoy."""
        e = self.en_mora(dias_de_mora=5)
        pago = self.cobrar(self.e.vendedor, [e])
        asiento = self.asiento_de(pago)
        self.assertEqual(
            self.lineas(asiento),
            sorted([(cuentas.BANCO, DEBE, D("2500.00")), (cuentas.DEUDORES_POR_VENTAS, HABER, D("1000.00")), (cuentas.INDEMNIZACIONES_POR_ATRASO, HABER, D("1500.00"))]),
        )
        self.assertEqual((asiento.fecha_asiento, asiento.origen_id, AsientoContable.objects.count()), (HOY, pago.pk, 1))
        verificar_invariantes_contables()

    def test_post_d_efectivo_sin_atraso_va_a_caja_y_no_hay_linea_de_atraso(self):
        """Postcondición d: el efectivo se imputa a Caja; sin atraso, la línea de Indemnizaciones por Atraso se omite (solo si es mayor que cero) y quedan dos movimientos."""
        pago = self.cobrar(self.e.vendedor, [self.concretada()], medio="efectivo")
        self.assertEqual(self.lineas(self.asiento_de(pago)), sorted([(cuentas.CAJA, DEBE, D("1000.00")), (cuentas.DEUDORES_POR_VENTAS, HABER, D("1000.00"))]))

    def test_regla_15_de_8_13_los_demas_medios_van_a_banco(self):
        """Regla 15 de 8.13: transferencia, tarjeta de débito y tarjeta de crédito van a Banco c/c; solo el efectivo, a Caja."""
        for medio in ("transferencia", "tarjeta_debito", "tarjeta_credito"):
            pago = self.cobrar(self.e.vendedor, [self.concretada()], medio=medio)
            self.assertIn(cuentas.BANCO, [c for c, _, _ in self.lineas(self.asiento_de(pago))], medio)

    def test_post_d_con_varias_entregas_el_asiento_suma_lo_cobrado_y_el_atraso_de_todas(self):
        """Postcondición d: un solo asiento por el cobro entero: Debe Banco por el monto pagado (1.000 + 600 + 1.000), Haber Deudores por 2.000,00 y Haber Atraso por 600,00."""
        pago = self.cobrar(self.e.vendedor, [self.en_mora(dias_de_mora=2), self.concretada()])
        self.assertEqual(
            self.lineas(self.asiento_de(pago)),
            sorted([(cuentas.BANCO, DEBE, D("2600.00")), (cuentas.DEUDORES_POR_VENTAS, HABER, D("2000.00")), (cuentas.INDEMNIZACIONES_POR_ATRASO, HABER, D("600.00"))]),
        )
        self.assertEqual(AsientoContable.objects.count(), 1)

    def test_post_g_el_registro_de_auditoria_nombra_el_asiento_y_no_se_audita_aparte(self):
        """Postcondición g y D-86 punto 4: el único registro `registro_cobro` nombra el asiento entre sus afectados y en `datos["asientos"]`."""
        pago = self.cobrar(self.e.vendedor, [self.concretada()])
        registro = RegistroAuditoria.objects.filter(accion="registro_cobro").get()
        asiento = self.asiento_de(pago)
        self.assertTrue(any(a["id"] == asiento.pk and a["texto"].startswith("Asiento") for a in registro.afectados))
        self.assertEqual(len(registro.detalle["datos"]["asientos"]), 1)

    def test_garantia_si_falla_el_asiento_no_queda_ni_el_cobro_ni_nada(self):
        """Garantía mínima 1: si el asiento falla, no queda el pago, ni las líneas, ni el asiento, ni la auditoría, y la entrega sigue sin pagar."""
        e = self.concretada()
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=RuntimeError("falla del asiento")):
            with self.assertRaises(RuntimeError):
                self.cobrar(self.e.vendedor, [e])
        self.assertEqual((PagoCliente.objects.count(), LineaPago.objects.count(), AsientoContable.objects.count(), RegistroAuditoria.objects.filter(accion="registro_cobro").count()), (0, 0, 0, 0))
        self.assertEqual(entregas.estado_de_pago([e.pk], HOY)[e.pk], "pendiente")

    def test_regla_9_el_cobro_sin_ejercicio_no_se_registra(self):
        """Regla 9 de CON-INI-EJE (CON-05; reemplaza `test_d92_el_cobro_asienta_aunque_no_haya_ejercicio_abierto_y_se_recupera_solo`, que verificaba D-92 punto 2 y H9 con el primer ejercicio
        creado solo): sin ejercicio no se verifica nada aparte, pero `registrar_asiento_automatico` rechaza con `contabilidad_no_iniciada` y el cobro no queda registrado."""
        entrega_ = self.concretada()
        EjercicioContable.objects.all().delete()  # la base de pruebas trae el ejercicio del helper
        with self.assertRaises(ErrorContable) as contexto:
            self.cobrar(self.e.vendedor, [entrega_])
        self.assertEqual(contexto.exception.codigo, "contabilidad_no_iniciada")
        self.assertEqual((PagoCliente.objects.count(), EjercicioContable.objects.count()), (0, 0))

    # ---- decisión (2) del estudiante del 26/11/2026 ----

    def test_d92_cobro_de_entrega_sin_asiento_de_concrecion_va_contra_deudores(self):
        """Decisión (2) del 26/11/2026 y D-92 punto 1: sin transición. La entrega de la fábrica no tiene asiento de concreción (como una anterior a CON-04c) y el cobro igual acredita Deudores por Ventas por
        lo cobrado: nada va a Ventas ni se corrige por la ausencia del asiento anterior."""
        e = self.concretada()
        self.assertFalse(AsientoContable.objects.filter(origen_id=e.pk).exists())
        pago = self.cobrar(self.e.vendedor, [e], medio="efectivo")
        self.assertEqual(self.lineas(self.asiento_de(pago)), sorted([(cuentas.CAJA, DEBE, D("1000.00")), (cuentas.DEUDORES_POR_VENTAS, HABER, D("1000.00"))]))
        self.assertNotIn(cuentas.VENTAS, [c for c, _, _ in self.lineas(self.asiento_de(pago))])


class ComRegCbrAsientoDe7aTests(BaseDeCobranza):
    """CON-04d · paso 1, decisión (1) del estudiante del 26/11/2026: el asiento del cobro que corrige uno anulado (7a, D-94 punto 10) lleva la `fecha_pago` (la del cobro anulado) y no la actual (D-92 punto 4).
    Si esa fecha cae en un ejercicio cerrado, lo resuelve D-102 (va al abierto con la fecha de hoy y la aclaración). El cobro original se registra en ``ANTES`` y se corrige 4 días después."""

    ANTES = HOY - timedelta(days=4)
    LUEGO = HOY

    def preparar(self):
        """Dos entregas vencidas hace 3 días al ``ANTES``, cobradas ese día por el Gerente y anuladas hoy («el cliente sí pagó»). Devuelve la anulación."""
        self.e1, self.e2 = self.en_mora(dias_de_mora=7), self.en_mora(dias_de_mora=7)  # vencidas hace 7 días hoy: hace 3 el ``ANTES``
        datos = DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[self.e1.pk, self.e2.pk], medio_pago="transferencia")
        self.original = cobranza.registrar_cobro(self.gerente, datos, cobranza.resumen_de_cobro(self.gerente, datos, self.ANTES).huella, self.ANTES)
        info = cobranza.datos_de_anulacion_de_cobro(self.gerente, self.original.pk, self.LUEGO)
        return cobranza.anular_cobro(self.gerente, self.original.pk, "Se cargó mal el medio.", True, info.huella, self.LUEGO)

    def corregir(self, anulacion_):
        datos = DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[self.e1.pk, self.e2.pk], medio_pago="efectivo", anulacion_id=anulacion_.pk, usar_fecha_anulada=True)
        return cobranza.registrar_cobro(self.gerente, datos, cobranza.resumen_de_cobro(self.gerente, datos, self.LUEGO).huella, self.LUEGO)

    def test_d92_cobro_7a_asienta_con_la_fecha_del_cobro_anulado(self):
        """Decisión (1): con `usar_fecha_anulada`, el cobro correcto tiene `fecha_pago` = la del anulado y su asiento lleva esa fecha (no la de hoy), en el ejercicio que la contiene."""
        ej = ejercicio_abierto(HOY - timedelta(days=60))
        nuevo = self.corregir(self.preparar())
        self.assertEqual(nuevo.fecha_pago, self.ANTES)
        asiento = AsientoContable.objects.get(origen_id=nuevo.pk)
        self.assertEqual((asiento.fecha_asiento, asiento.ejercicio_id), (self.ANTES, ej.pk))
        self.assertNotIn("Fecha del hecho", asiento.descripcion_asiento)
        self.assertEqual(
            sorted((m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.select_related("cuenta")),
            sorted([(cuentas.CAJA, DEBE, D("3800.00")), (cuentas.DEUDORES_POR_VENTAS, HABER, D("2000.00")), (cuentas.INDEMNIZACIONES_POR_ATRASO, HABER, D("1800.00"))]),
        )
        verificar_invariantes_contables()

    def test_d102_cobro_7a_con_el_ejercicio_de_esa_fecha_cerrado_va_al_abierto_con_la_fecha_de_hoy_y_la_aclaracion(self):
        """Decisión (1) y D-102: si el ejercicio de la fecha del cobro anulado ya está cerrado, el asiento NO falla: va al abierto con la fecha de hoy y la descripción aclara la fecha real."""
        cerrado = ejercicio_abierto(HOY - timedelta(days=60))
        anulacion_ = self.preparar()  # el cobro original y su anulación se asientan mientras el ejercicio está abierto; después se cierra (la fecha del cobro anulado queda en un ejercicio cerrado)
        EjercicioContable.objects.filter(pk=cerrado.pk).update(estado_ejercicio=EjercicioContable.Estado.CERRADO, fecha_cierre_ejercicio=HOY - timedelta(days=3))
        abierto = ejercicio_abierto(HOY - timedelta(days=2))
        nuevo = self.corregir(anulacion_)
        asiento = AsientoContable.objects.get(origen_id=nuevo.pk)
        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento), (abierto.pk, HOY))
        self.assertIn(f"Fecha del hecho: {self.ANTES:%d/%m/%Y}", asiento.descripcion_asiento)
        self.assertIn("ya está cerrado", asiento.descripcion_asiento)
        self.assertFalse(AsientoContable.objects.filter(ejercicio=cerrado, origen_id=nuevo.pk).exists())
        verificar_invariantes_contables()

    def test_regla_sin_la_casilla_el_cobro_comun_asienta_con_la_fecha_de_hoy(self):
        """Fuera de 7a rige la regla «Fecha del pago»: el cobro común lleva y asienta la fecha de hoy."""
        ejercicio_abierto(HOY - timedelta(days=60))
        self.preparar()
        datos = DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[self.e1.pk], medio_pago="efectivo")
        nuevo = cobranza.registrar_cobro(self.gerente, datos, cobranza.resumen_de_cobro(self.gerente, datos, self.LUEGO).huella, self.LUEGO)
        self.assertEqual((nuevo.fecha_pago, AsientoContable.objects.get(origen_id=nuevo.pk).fecha_asiento), (self.LUEGO, self.LUEGO))
