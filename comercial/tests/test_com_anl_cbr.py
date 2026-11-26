# Pruebas de COM-ANL-CBR · Anular Cobro (COM-08b, paso 2 y paso 3 de la tarea): `datos_de_anulacion_de_cobro` (solo lectura), `anular_cobro`, `anulacion_para_registrar` y el cobro correcto con la fecha del cobro
# anulado (extensión 7a: `DatosDeCobro.anulacion_id` y `usar_fecha_anulada`). Una por regla (quién anula, alcance, cobro anulado, estado de las entregas, alerta y avisos, volver a cobrar), por postcondición
# (a, b, d, e, f; la c, el contraasiento, es «Fuera de esta ronda»: se prueba que NO se crea) y por extensión (1a, 3a, 5a, 7a con y sin `cliente_pago_en_fecha`, con la casilla desmarcada, con una entrega que
# no era del cobro y con la anulación ya usada). Además, lo que la anulación libera: 2b de COM-ANL-SRV y la regla 5 de COM-ATN-ENR. `verificar_invariantes_de_cobros()` corre al final de cada una (`BaseDeCobranza`).
# Fuente: docs/casos_de_uso/comercial/cobranza.md («COM-ANL-CBR», «Anular un cobro», «Lo que libera»), D-94 puntos 5, 10 y 11 (el campo se llama `pago_cliente`), MD-135, MD-136, D-57, D-42, D-36.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa; es lo que `cobranza.md` deja a criterio del código):
# - `datos_de_anulacion_de_cobro(actor, pago_id, hoy=None) -> DatosDeAnulacionDeCobro` con `pago`, `codigo`, `cliente` (el nombre), `fecha`, `medio` (el texto), `monto`, `indemnizacion` (el atraso total),
#   `entregas` (una `EntregaDeAnulacion` por entrega con `entrega_id`, `codigo`, `contrato_codigo`, `monto_cobrado`, `dias_atraso`, `indemnizacion`, `estado_despues` —«pendiente» o «en_mora»— y `alerta` —si se va
#   a asegurar su alerta—), `contraasiento` (el texto «Fuera de esta ronda · contabilidad») y `huella` (un texto). No escribe nada;
# - `anular_cobro(actor, pago_id, motivo, cliente_pago_en_fecha, huella, hoy=None) -> Anulacion`; errores `ValidationError` con `code`: `cobro_de_compra_venta` (1a), `cobro_ya_anulado` (5a), `motivo_obligatorio` y
#   `motivo_largo` (3a, en el campo `motivo`) y `cambio_simultaneo` (la huella cambió); `PermissionDenied` (`sin_permiso`) si no es el Gerente activo; `Http404` si el cobro no existe;
# - `DatosDeCobro(cliente_id, entrega_ids, medio_pago, anulacion_id=None, usar_fecha_anulada=False)`;
# - `anulacion_para_registrar(actor, anulacion_id) -> AnulacionParaRegistrar` con `anulacion`, `cliente_id`, `entrega_ids` (las del cobro anulado que siguen sin cobrar), `usa_fecha` (la anulación dice que el cliente
#   pagó ese día) y `fecha` (la del cobro anulado); `anulacion_ya_usada` si su cobro correcto ya se registró;
# - la auditoría `anulacion_cobro`: `cambios.estado_pago` (vigente → anulado) y `datos` con `motivo_anulacion`, `cliente_pago_en_fecha`, `cobro_anulado`, `entregas_que_vuelven` y `alertas_creadas`.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import override_settings

from comercial.models import Anulacion, Entrega, LineaPago, PagoCliente
from comercial.servicios import atencion, cobranza, entregas, solicitudes
from comercial.tests.base_cobranza import HOY, BaseDeCobranza, codigos
from comercial.tests.fabricas import (
    alerta_no_reconocida,
    anulacion,
    compra_venta,
    discrepancia_aceptada,
    pago_de_compra_venta,
)
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import asiento_de_prueba, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Notificacion, RegistroAuditoria
from maestros.models import Alerta, Invernadero
from maestros.tests.fabricas import crear_capataz_activo

D = Decimal
DatosDeCobro = cobranza.DatosDeCobro


class ComAnlCbrServicioTests(BaseDeCobranza):
    def registrar(self, entregas_, *, actor=None, medio="transferencia", hoy=HOY, **extra):
        """El cobro como la pantalla (resumen y registro); sin ejecutar los `on_commit` (el comprobante no sale)."""
        actor = actor or self.gerente
        datos = DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[e.pk for e in entregas_], medio_pago=medio, **extra)
        resumen = cobranza.resumen_de_cobro(actor, datos, hoy)
        return cobranza.registrar_cobro(actor, datos, resumen.huella, hoy)

    def anular(self, pago, *, actor=None, motivo="Se cargó con el medio equivocado.", pago_en_fecha=False, hoy=HOY, huella=None, correo=True):
        """La anulación como la pantalla (los datos y la confirmación), con el correo del sistema configurado y los `on_commit` ejecutados."""
        actor = actor or self.gerente
        with override_settings(CORREO_CONFIGURADO=correo), self.captureOnCommitCallbacks(execute=True):
            datos = cobranza.datos_de_anulacion_de_cobro(actor, pago.pk, hoy)
            return cobranza.anular_cobro(actor, pago.pk, motivo, pago_en_fecha, huella or datos.huella, hoy)

    def estado(self, entrega_, hoy=HOY):
        return entregas.estado_de_pago([entrega_.pk], hoy)[entrega_.pk]

    def un_cobro_de_dos(self):
        """Un cobro (del Gerente) de una entrega en mora (venció hace 3 días) y otra pendiente: devuelve `(pago, en_mora, pendiente)`."""
        en_mora, pendiente = self.en_mora(dias_de_mora=3), self.concretada()
        return self.registrar([en_mora, pendiente]), en_mora, pendiente

    # ---- el flujo principal y las postcondiciones ----

    def test_flujo_principal_el_gerente_anula_un_cobro_de_dos_entregas(self):
        """Pasos 1 a 7: el Gerente abre la anulación, escribe el motivo y confirma: el cobro queda «anulado», una entrega vuelve a «en mora» y la otra a «pendiente»."""
        pago, en_mora, pendiente = self.un_cobro_de_dos()
        datos = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, HOY)
        self.assertEqual((datos.codigo, datos.monto, datos.indemnizacion), (pago.codigo, pago.monto_pagado, D("900.00")))
        resultado = self.anular(pago)
        self.assertIsInstance(resultado, Anulacion)
        pago.refresh_from_db()
        self.assertEqual(pago.estado_pago, "anulado")
        self.assertEqual((self.estado(en_mora), self.estado(pendiente)), ("en_mora", "pendiente"))

    def test_post_a_el_cobro_queda_anulado_y_conserva_su_vinculo_con_las_entregas(self):
        """Postcondición a (MD-136): el pago pasa a «anulado», conserva sus datos y sus líneas (con `vigente = False`); no se borra nada."""
        pago, en_mora, pendiente = self.un_cobro_de_dos()
        antes = (pago.monto_pagado, pago.medio_pago, pago.fecha_pago, pago.numero)
        self.anular(pago)
        pago.refresh_from_db()
        self.assertEqual((pago.monto_pagado, pago.medio_pago, pago.fecha_pago, pago.numero), antes)
        self.assertEqual(sorted(pago.lineas.values_list("entrega_id", "vigente")), sorted([(en_mora.pk, False), (pendiente.pk, False)]))
        self.assertEqual(LineaPago.objects.filter(vigente=True).count(), 0)

    def test_post_b_la_anulacion_guarda_la_fecha_el_motivo_el_usuario_el_cobro_y_la_indicacion(self):
        """Postcondición b (MD-135): fecha de hoy, motivo, usuario, el cobro anulado y si el cliente sí pagó en esa fecha."""
        pago, _, _ = self.un_cobro_de_dos()
        a = self.anular(pago, motivo="No se acreditó la transferencia.", pago_en_fecha=True)
        a.refresh_from_db()
        self.assertEqual((a.fecha_anulacion, a.motivo_anulacion, a.usuario_id, a.pago_cliente_id, a.cliente_pago_en_fecha), (HOY, "No se acreditó la transferencia.", self.gerente.pk, pago.pk, True))
        self.assertEqual((a.solicitud_id, a.estado_anulado), (None, None))
        self.assertEqual(pago.anulacion_de_cobro.pk, a.pk)

    def test_post_b_cliente_pago_en_fecha_por_omision_es_falso(self):
        """Paso 3: la casilla viene desmarcada: se guarda `False`."""
        pago, _, _ = self.un_cobro_de_dos()
        self.assertIs(self.anular(pago).cliente_pago_en_fecha, False)

    # `test_post_c_no_crea_el_contraasiento_fuera_de_esta_ronda` (COM-08b, D-57) se REEMPLAZÓ por `ComAnlCbrAsientoTests` (CON-04d): el contraasiento ahora se crea (D-92 punto 6). Lo que mostraba la pantalla
    # (`datos.contraasiento`) lo cubre `test_cobranza_vistas` / `ComAnlCbrAsientoTests` en el paso de las pantallas.

    def test_post_d_cada_entrega_vuelve_a_pendiente_o_en_mora_segun_su_vencimiento_guardado(self):
        """Postcondición d y regla «Estado de las entregas»: se recalcula con `fecha_vencimiento_pago` (MD-132): el día del vencimiento todavía es «pendiente»; al día siguiente, «en mora»."""
        vence_hoy = self.concretada(hace_dias=10, plazo_pago=10)  # vence hoy
        vencio_ayer = self.concretada(hace_dias=11, plazo_pago=10)
        pago = self.registrar([vence_hoy, vencio_ayer])
        datos = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, HOY)
        self.assertEqual({e.codigo: e.estado_despues for e in datos.entregas}, {vence_hoy.codigo: "pendiente", vencio_ayer.codigo: "en_mora"})
        self.anular(pago)
        self.assertEqual((self.estado(vence_hoy), self.estado(vencio_ayer)), ("pendiente", "en_mora"))

    def test_post_e_la_entrega_en_mora_tiene_su_alerta_activa_otra_vez_y_el_vendedor_recibe_el_aviso(self):
        """Postcondición e (D-94 punto 5): una entrega que vuelve a «en mora» tiene activa su alerta «pago en mora» (se asegura una nueva, la anterior queda en el historial) y se notifica al Vendedor."""
        pago, en_mora, pendiente = self.un_cobro_de_dos()
        self.anular(pago)
        self.assertEqual(len(self.alertas_de(en_mora, activas=True)), 1)
        self.assertEqual(self.alertas_de(pendiente), [])
        avisos = self.avisos(self.e.vendedor, f"{pago.codigo} anulado")
        self.assertEqual(len(avisos), 1)
        self.assertIn(f"{en_mora.codigo} (en mora)", avisos[0].detalle)
        self.assertIn(f"{pendiente.codigo} (pendiente)", avisos[0].detalle)
        self.assertIn("Vuelven a estar sin pagar", avisos[0].detalle)
        self.assertIn("Se cargó con el medio equivocado.", avisos[0].detalle)

    def test_post_e_el_aviso_individual_de_mora_no_sale_porque_el_aviso_de_la_anulacion_ya_lo_dice(self):
        """D-94 punto 5 («`anular_cobro` → `avisar_vendedor = False`»): el Vendedor no recibe además «OT-… en mora»."""
        pago, en_mora, _ = self.un_cobro_de_dos()
        self.anular(pago)
        self.assertEqual(self.avisos(self.e.vendedor, f"{en_mora.codigo} en mora"), [])

    def test_post_e_una_entrega_que_nunca_estuvo_en_mora_y_queda_en_mora_manda_el_primer_correo(self):
        """Regla «Alerta y avisos»: si la entrega nunca había sido avisada (se cobró en mora sin que el paso 30 corriera), `reevaluar_mora` carga `fecha_aviso_mora` y sale el correo de mora, una sola vez."""
        pago, en_mora, _ = self.un_cobro_de_dos()
        self.assertIsNone(Entrega.objects.get(pk=en_mora.pk).fecha_aviso_mora)
        self.anular(pago)
        e = Entrega.objects.get(pk=en_mora.pk)
        self.assertEqual((e.fecha_aviso_mora, e.estado_aviso_mora), (HOY, "enviado"))
        self.assertEqual([m.subject for m in mail.outbox], [f"Pago en mora de la entrega {en_mora.codigo}"])

    def test_post_e_una_entrega_que_ya_estuvo_en_mora_tiene_su_alerta_sin_otro_correo(self):
        """Postcondición e y regla 3 de COM-VNC-PAG: el correo al cliente no se repite: si ya se había avisado (paso 30), solo se asegura la alerta."""
        en_mora = self.en_mora(dias_de_mora=3)
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            cobranza.vencer_pagos(HOY)
        self.assertEqual(len(mail.outbox), 1)
        mail.outbox.clear()
        pago = self.registrar([en_mora])
        self.assertEqual((len(self.alertas_de(en_mora, activas=True)), len(self.alertas_de(en_mora, activas=False))), (0, 1))
        self.anular(pago)
        self.assertEqual((len(self.alertas_de(en_mora, activas=True)), len(self.alertas_de(en_mora, activas=False))), (1, 1))
        self.assertEqual(mail.outbox, [])

    def test_regla_la_anulacion_no_le_escribe_al_cliente(self):
        """Decisión 13 de D-94: «la anulación de un cobro no le escribe al cliente»: con entregas pendientes (sin mora) no sale ningún correo."""
        pago = self.registrar([self.concretada()])
        self.anular(pago)
        self.assertEqual(mail.outbox, [])

    def test_regla_con_el_invernadero_dado_de_baja_no_hay_alerta_pero_la_anulacion_se_registra(self):
        """D-94 punto 6: la API no crea la alerta de un invernadero dado de baja (`None`); la anulación y el aviso al Vendedor salen igual."""
        pago, en_mora, _ = self.un_cobro_de_dos()
        Invernadero.objects.filter(pk=en_mora.invernadero_id).update(estado_invernadero="inactivo")
        self.anular(pago)
        pago.refresh_from_db()
        self.assertEqual((pago.estado_pago, self.alertas_de(en_mora, activas=True)), ("anulado", []))
        self.assertEqual(len(self.avisos(self.e.vendedor, f"{pago.codigo} anulado")), 1)

    def test_regla_el_vendedor_inactivo_no_recibe_aviso_y_la_anulacion_sigue(self):
        """Regla «Alerta y avisos»: solo se avisa a un Vendedor activo."""
        pago, _, _ = self.un_cobro_de_dos()
        self.e.vendedor.is_active = False
        self.e.vendedor.save(update_fields=["is_active"])
        self.anular(pago)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo__startswith=f"{pago.codigo} anulado").count(), 0)

    def test_post_f_la_auditoria_registra_la_anulacion_con_sus_afectados_y_sus_datos(self):
        """Postcondición f (D-36): un registro `anulacion_cobro` con el Gerente; afectados: el pago (principal), la anulación, las líneas y las alertas creadas; los datos: el motivo, la indicación y cada entrega con su estado nuevo."""
        pago, en_mora, pendiente = self.un_cobro_de_dos()
        a = self.anular(pago, pago_en_fecha=True)
        registro = RegistroAuditoria.objects.get(accion="anulacion_cobro")
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.afectados[0]["id"], pago.pk)
        self.assertTrue(any(x["id"] == a.pk and "Anulación" in x["texto"] for x in registro.afectados))
        self.assertEqual({x["id"] for x in registro.afectados if x["modelo"] == "comercial.lineapago"}, set(pago.lineas.values_list("pk", flat=True)))
        (alerta,) = Alerta.objects.filter(vinculo_comercial__entrega_id=en_mora.pk, estado_alerta="activa")
        self.assertTrue(any(x["id"] == alerta.pk for x in registro.afectados))
        self.assertEqual(registro.detalle["cambios"]["estado_pago"], {"antes": "vigente", "despues": "anulado"})
        datos = registro.detalle["datos"]
        self.assertEqual((datos["motivo_anulacion"], datos["cliente_pago_en_fecha"]), ("Se cargó con el medio equivocado.", True))
        self.assertTrue(any(en_mora.codigo in t and "en_mora" in t for t in datos["entregas_que_vuelven"]))
        self.assertTrue(any(pendiente.codigo in t and "pendiente" in t for t in datos["entregas_que_vuelven"]))

    def test_regla_la_anulacion_no_toca_la_entrega_el_contrato_ni_los_incumplimientos(self):
        """Lo que no hace: no cambia la entrega concretada (su monto, su vencimiento) ni los incumplimientos del contrato."""
        pago, en_mora, _ = self.un_cobro_de_dos()
        antes = Entrega.objects.filter(pk=en_mora.pk).values("estado_orden", "monto_total_entrega", "fecha_vencimiento_pago", "indemnizacion_retraso_dia").get()
        self.anular(pago)
        self.assertEqual(Entrega.objects.filter(pk=en_mora.pk).values("estado_orden", "monto_total_entrega", "fecha_vencimiento_pago", "indemnizacion_retraso_dia").get(), antes)

    # ---- quién anula y alcance ----

    def test_regla_solo_el_gerente_anula_el_vendedor_del_contrato_no(self):
        """Regla «Quién anula»: solo el Gerente. El Vendedor del contrato recibe `PermissionDenied` en la lectura y en la escritura, y no cambia nada."""
        pago, _, _ = self.un_cobro_de_dos()
        with self.assertRaises(PermissionDenied):
            cobranza.datos_de_anulacion_de_cobro(self.e.vendedor, pago.pk, HOY)
        huella = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, HOY).huella
        with self.assertRaises(PermissionDenied):
            cobranza.anular_cobro(self.e.vendedor, pago.pk, "Motivo.", False, huella, HOY)
        pago.refresh_from_db()
        self.assertEqual((pago.estado_pago, Anulacion.objects.count()), ("vigente", 0))

    def test_regla_los_demas_roles_y_el_gerente_inactivo_no_anulan(self):
        """Regla «Quién anula»: un Capataz y un Gerente con la cuenta inactiva reciben `PermissionDenied`."""
        pago, _, _ = self.un_cobro_de_dos()
        with self.assertRaises(PermissionDenied):
            cobranza.datos_de_anulacion_de_cobro(crear_capataz_activo(), pago.pk, HOY)
        huella = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, HOY).huella
        self.gerente.is_active = False
        self.gerente.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            cobranza.anular_cobro(self.gerente, pago.pk, "Motivo.", False, huella, HOY)
        self.assertEqual(PagoCliente.objects.get(pk=pago.pk).estado_pago, "vigente")

    def test_ext_1a_un_cobro_de_compra_venta_no_se_anula_desde_aca(self):
        """Extensión 1a y regla «Alcance»: «Este cobro es de una compra-venta: va dentro del asiento de la entrega y se corrige con un asiento manual.»: `cobro_de_compra_venta`, sin cambios."""
        pago = pago_de_compra_venta(compra_venta(self.e, dias=0))
        error = self.rechazo(cobranza.datos_de_anulacion_de_cobro, self.gerente, pago.pk, HOY)
        self.assertEqual(codigos(error), ["cobro_de_compra_venta"])
        self.assertIn("asiento manual", " ".join(error.messages))
        error = self.rechazo(cobranza.anular_cobro, self.gerente, pago.pk, "Motivo.", False, "", HOY)
        self.assertEqual(codigos(error), ["cobro_de_compra_venta"])
        self.assertEqual((PagoCliente.objects.get(pk=pago.pk).estado_pago, Anulacion.objects.count()), ("vigente", 0))

    def test_regla_un_cobro_que_no_existe_da_404(self):
        """Un cobro inexistente: `Http404`."""
        with self.assertRaises(Http404):
            cobranza.datos_de_anulacion_de_cobro(self.gerente, 999999, HOY)

    # ---- el motivo (3a) ----

    def test_ext_3a_el_motivo_es_obligatorio_y_de_hasta_500_sin_espacios_al_borde(self):
        """Extensión 3a: vacío (o solo espacios) → `motivo_obligatorio`; más de 500 → `motivo_largo`; 500 pasa; los espacios al borde se sacan."""
        pago, _, _ = self.un_cobro_de_dos()
        huella = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, HOY).huella
        for vacio in ("", "   "):
            self.assertEqual(codigos(self.rechazo(cobranza.anular_cobro, self.gerente, pago.pk, vacio, False, huella, HOY)), ["motivo_obligatorio"])
        self.assertEqual(codigos(self.rechazo(cobranza.anular_cobro, self.gerente, pago.pk, "x" * 501, False, huella, HOY)), ["motivo_largo"])
        self.assertEqual(PagoCliente.objects.get(pk=pago.pk).estado_pago, "vigente")
        a = self.anular(pago, motivo="  " + "x" * 500 + "  ")
        self.assertEqual(a.motivo_anulacion, "x" * 500)

    # ---- 5a y la huella ----

    def test_ext_5a_si_el_cobro_ya_se_anulo_en_otra_operacion_no_se_registra_nada(self):
        """Extensión 5a: `cobro_ya_anulado`; no se crea otra anulación ni otro registro de auditoría ni otro aviso."""
        pago, _, _ = self.un_cobro_de_dos()
        huella = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, HOY).huella
        self.anular(pago)
        antes = (Anulacion.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count())
        self.assertEqual(codigos(self.rechazo(cobranza.anular_cobro, self.gerente, pago.pk, "Otra vez.", False, huella, HOY)), ["cobro_ya_anulado"])
        self.assertEqual(codigos(self.rechazo(cobranza.datos_de_anulacion_de_cobro, self.gerente, pago.pk, HOY)), ["cobro_ya_anulado"])
        self.assertEqual((Anulacion.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)

    def test_regla_si_cambio_el_dia_o_el_estado_en_que_quedan_las_entregas_la_huella_lo_detecta(self):
        """Huella (D-94 punto 9, por analogía con 10b): lo que la pantalla mostró («vuelve a pendiente») puede dejar de valer si pasa un día: `cambio_simultaneo` y no se anula nada."""
        pago = self.registrar([self.concretada(hace_dias=10, plazo_pago=10)])  # vence hoy: hoy vuelve «pendiente»; mañana, «en mora»
        huella = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, HOY).huella
        error = self.rechazo(cobranza.anular_cobro, self.gerente, pago.pk, "Motivo.", False, huella, HOY + timedelta(days=1))
        self.assertEqual(codigos(error), ["cambio_simultaneo"])
        self.assertEqual((PagoCliente.objects.get(pk=pago.pk).estado_pago, Anulacion.objects.count()), ("vigente", 0))

    def test_regla_la_lectura_no_escribe_nada(self):
        """Pasos 1 y 2 son de solo lectura: ni anulación, ni auditoría, ni avisos, ni alertas, ni asientos."""
        pago, _, _ = self.un_cobro_de_dos()
        antes = (Anulacion.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count(), Alerta.objects.count(), LineaPago.objects.filter(vigente=True).count())
        datos = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, HOY)
        self.assertEqual(sorted(e.estado_despues for e in datos.entregas), ["en_mora", "pendiente"])
        self.assertEqual(sorted(e.alerta for e in datos.entregas), [False, True])
        self.assertEqual((Anulacion.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count(), Alerta.objects.count(), LineaPago.objects.filter(vigente=True).count()), antes)

    # ---- volver a cobrar ----

    def test_regla_la_entrega_vuelve_a_ser_cobrable_y_se_puede_registrar_otro_cobro(self):
        """Regla «Volver a cobrar» y «Lo que libera»: una entrega cuyo cobro se anuló vuelve a aparecer en «Por cobrar» y se cobra de nuevo (un cobro común con la fecha de hoy); la base conserva los dos pagos."""
        pago, en_mora, pendiente = self.un_cobro_de_dos()
        self.anular(pago)
        cobrables = {f.entrega_id for f in cobranza.entregas_cobrables(self.gerente, self.e.cliente.pk, HOY)}
        self.assertEqual(cobrables, {en_mora.pk, pendiente.pk})
        nuevo = self.registrar([en_mora, pendiente], medio="efectivo")
        self.assertEqual((nuevo.estado_pago, nuevo.anulacion_corregida_id, nuevo.fecha_pago), ("vigente", None, HOY))
        self.assertEqual(entregas.estado_de_pago([en_mora.pk], HOY)[en_mora.pk].cobro.codigo, nuevo.codigo)
        self.assertEqual(PagoCliente.objects.filter(tipo_pago="suministro").count(), 2)
        self.assertEqual(self.alertas_de(en_mora, activas=True), [])

    # ---- lo que la anulación libera: 2b de COM-ANL-SRV y la regla 5 de COM-ATN-ENR ----

    def test_regla_despues_de_anular_2b_de_com_anl_srv_deja_de_rechazar(self):
        """«Lo que libera»: con el cobro vigente, anular la resolución de la solicitud aceptada con descuento rechaza `entrega_cobrada`; con el cobro anulado, deja de rechazar."""
        e = self.concretada()
        s = discrepancia_aceptada(e, monto="200.00", descontado="200.00")
        pago = self.registrar([e])
        self.assertEqual(solicitudes.datos_de_anulacion(self.gerente, s.pk).bloqueo[0], "entrega_cobrada")
        self.anular(pago)
        datos = solicitudes.datos_de_anulacion(self.gerente, s.pk)
        self.assertIsNone(datos.bloqueo)
        solicitudes.anular_resolucion(self.gerente, s.pk, "Error de carga.", datos.huella)

    def test_regla_despues_de_anular_la_regla_5_de_com_atn_enr_deja_de_rechazar(self):
        """«Lo que libera»: con el cobro vigente, atender «no llegó» rechaza `entrega_cobrada` («Primero anulá el cobro.»); con el cobro anulado, se atiende."""
        e = self.concretada()
        alerta = alerta_no_reconocida(e)
        pago = self.registrar([e])
        self.assertEqual(codigos(self.rechazo(atencion.atender_entrega_no_reconocida, self.gerente, alerta.pk, "no_llego_perdido", "No llegó.")), ["entrega_cobrada"])
        self.anular(pago)
        atencion.atender_entrega_no_reconocida(self.gerente, alerta.pk, "no_llego_perdido", "No llegó.")
        self.assertEqual(Alerta.objects.get(pk=alerta.pk).estado_alerta, "resuelta")


class ComAnlCbrCobroCorrectoTests(BaseDeCobranza):
    """Extensión 7a: el cobro correcto con la fecha del cobro anulado (D-94 punto 10). El cobro original se registra «hoy» y se anula 4 días después (`hoy` es un parámetro del servicio)."""

    LUEGO = HOY + timedelta(days=4)

    def setUp(self):
        super().setUp()
        self.e1, self.e2 = self.en_mora(dias_de_mora=3), self.en_mora(dias_de_mora=3)  # vencidas hace 3 días: $ 900,00 de atraso por entrega al cobrarse hoy
        datos = DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[self.e1.pk, self.e2.pk], medio_pago="transferencia")
        self.original = cobranza.registrar_cobro(self.gerente, datos, cobranza.resumen_de_cobro(self.gerente, datos, HOY).huella, HOY)

    def anular(self, *, pago_en_fecha):
        datos = cobranza.datos_de_anulacion_de_cobro(self.gerente, self.original.pk, self.LUEGO)
        return cobranza.anular_cobro(self.gerente, self.original.pk, "El cliente pagó pero se cargó mal el medio.", pago_en_fecha, datos.huella, self.LUEGO)

    def datos(self, entregas_, **extra):
        return DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[e.pk for e in entregas_], medio_pago="efectivo", **extra)

    def cobrar(self, datos, actor=None):
        actor = actor or self.gerente
        return cobranza.registrar_cobro(actor, datos, cobranza.resumen_de_cobro(actor, datos, self.LUEGO).huella, self.LUEGO)

    def test_ext_7a_con_cliente_pago_en_fecha_la_pantalla_propone_la_fecha_del_cobro_anulado(self):
        """7a: `anulacion_para_registrar` devuelve el cliente, las entregas del cobro anulado y la fecha propuesta (la del cobro anulado, con `usa_fecha`)."""
        a = self.anular(pago_en_fecha=True)
        x = cobranza.anulacion_para_registrar(self.gerente, a.pk)
        self.assertEqual((x.cliente_id, sorted(x.entrega_ids), x.usa_fecha, x.fecha), (self.e.cliente.pk, sorted([self.e1.pk, self.e2.pk]), True, HOY))

    def test_ext_7a_con_la_casilla_la_fecha_del_pago_es_la_del_cobro_anulado_y_el_atraso_se_calcula_a_esa_fecha(self):
        """7a: con `usar_fecha_anulada`, el resumen y el cobro usan la fecha del cobro anulado: 3 días de atraso (no 7) → $ 900,00 por entrega; el cobro carga `anulacion_corregida`."""
        a = self.anular(pago_en_fecha=True)
        datos = self.datos([self.e1, self.e2], anulacion_id=a.pk, usar_fecha_anulada=True)
        resumen = cobranza.resumen_de_cobro(self.gerente, datos, self.LUEGO)
        self.assertEqual((resumen.fecha_pago, resumen.indemnizacion, resumen.total), (HOY, D("1800.00"), D("3800.00")))
        nuevo = self.cobrar(datos)
        self.assertEqual((nuevo.fecha_pago, nuevo.monto_pagado, nuevo.anulacion_corregida_id, nuevo.estado_pago), (HOY, D("3800.00"), a.pk, "vigente"))
        self.assertEqual({(l.dias_atraso, l.indemnizacion_atraso) for l in nuevo.lineas.all()}, {(3, D("900.00"))})
        self.assertEqual(a.cobro_correcto.pk, nuevo.pk)
        registro = RegistroAuditoria.objects.filter(accion="registro_cobro").latest("pk")  # la auditoría del cobro correcto dice a qué anulación corrige y con qué fecha
        self.assertEqual((registro.detalle["datos"]["anulacion_corregida"]["id"], registro.detalle["cambios"]["fecha_pago"]["despues"]), (a.pk, HOY.isoformat()))

    def test_ext_7a_la_misma_indemnizacion_que_el_cobro_anulado(self):
        """Postcondición de 7a («para no cobrarle un atraso que no tuvo»): la indemnización del cobro correcto es igual a la del cobro anulado."""
        a = self.anular(pago_en_fecha=True)
        nuevo = self.cobrar(self.datos([self.e1, self.e2], anulacion_id=a.pk, usar_fecha_anulada=True))
        original = sum((l.indemnizacion_atraso for l in LineaPago.objects.filter(pago=self.original)), D("0.00"))
        self.assertEqual(sum((l.indemnizacion_atraso for l in nuevo.lineas.all()), D("0.00")), original)

    def test_ext_7a_sin_marcar_la_casilla_es_un_cobro_comun_con_la_fecha_de_hoy(self):
        """7a: sin `usar_fecha_anulada` (aunque el cliente sí pagó) el cobro lleva la fecha de hoy, el atraso de hoy (7 días × $ 300,00) y no carga `anulacion_corregida`."""
        a = self.anular(pago_en_fecha=True)
        nuevo = self.cobrar(self.datos([self.e1], anulacion_id=a.pk))
        self.assertEqual((nuevo.fecha_pago, nuevo.anulacion_corregida_id), (self.LUEGO, None))
        self.assertEqual((nuevo.lineas.get().dias_atraso, nuevo.lineas.get().indemnizacion_atraso), (7, D("2100.00")))

    def test_ext_7a_si_el_cliente_no_pago_ese_dia_no_hay_fecha_propuesta(self):
        """7a solo vale con `cliente_pago_en_fecha`: `anulacion_para_registrar` no propone la fecha y usarla se rechaza con `fecha_no_admitida`."""
        a = self.anular(pago_en_fecha=False)
        x = cobranza.anulacion_para_registrar(self.gerente, a.pk)
        self.assertEqual((x.usa_fecha, sorted(x.entrega_ids)), (False, sorted([self.e1.pk, self.e2.pk])))
        error = self.rechazo(cobranza.resumen_de_cobro, self.gerente, self.datos([self.e1], anulacion_id=a.pk, usar_fecha_anulada=True), self.LUEGO)
        self.assertEqual(codigos(error), ["fecha_no_admitida"])

    def test_ext_7a_con_una_entrega_que_no_era_del_cobro_anulado_no_se_admite_la_fecha(self):
        """Límite de 7a (D-94 punto 10): solo las entregas del cobro anulado; con otra, `fecha_no_admitida` (la fecha anterior no sirve para cobrar sin atraso cualquier entrega) y no se cobra nada."""
        a = self.anular(pago_en_fecha=True)
        otra = self.en_mora(dias_de_mora=3)
        antes = PagoCliente.objects.count()
        for entregas_ in ([otra], [self.e1, otra]):
            self.assertEqual(codigos(self.rechazo(self.cobrar, self.datos(entregas_, anulacion_id=a.pk, usar_fecha_anulada=True))), ["fecha_no_admitida"])
        self.assertEqual(PagoCliente.objects.count(), antes)

    def test_ext_7a_se_puede_cobrar_solo_una_parte_de_las_entregas_del_cobro_anulado(self):
        """7a: las entregas elegidas tienen que ser **del** cobro anulado, no todas: con una sola, vale (cada entrega se paga completa, sin pagos parciales)."""
        a = self.anular(pago_en_fecha=True)
        nuevo = self.cobrar(self.datos([self.e1], anulacion_id=a.pk, usar_fecha_anulada=True))
        self.assertEqual((nuevo.anulacion_corregida_id, nuevo.fecha_pago, nuevo.monto_pagado), (a.pk, HOY, D("1900.00")))

    def test_ext_7a_la_anulacion_se_usa_una_sola_vez(self):
        """Límite de 7a: «una sola vez por anulación»: el segundo cobro con la fecha anulada recibe `anulacion_ya_usada`, aunque sea de la otra entrega; `anulacion_para_registrar` también."""
        a = self.anular(pago_en_fecha=True)
        self.cobrar(self.datos([self.e1], anulacion_id=a.pk, usar_fecha_anulada=True))
        self.assertEqual(codigos(self.rechazo(self.cobrar, self.datos([self.e2], anulacion_id=a.pk, usar_fecha_anulada=True))), ["anulacion_ya_usada"])
        self.assertEqual(codigos(self.rechazo(cobranza.anulacion_para_registrar, self.gerente, a.pk)), ["anulacion_ya_usada"])
        self.assertEqual(PagoCliente.objects.filter(anulacion_corregida=a).count(), 1)

    def test_ext_7a_solo_el_gerente_usa_la_fecha_anulada(self):
        """Límite de 7a (D-94 punto 10): «solo el Gerente (la anulación es suya)»: el Vendedor del contrato con `usar_fecha_anulada` recibe `fecha_no_admitida`."""
        a = self.anular(pago_en_fecha=True)
        error = self.rechazo(cobranza.resumen_de_cobro, self.e.vendedor, self.datos([self.e1], anulacion_id=a.pk, usar_fecha_anulada=True), self.LUEGO)
        self.assertEqual(codigos(error), ["fecha_no_admitida"])

    def test_ext_7a_una_anulacion_de_una_solicitud_no_habilita_la_fecha(self):
        """La anulación tiene que ser la de un cobro: la de la resolución de una solicitud (COM-ANL-SRV) o un id inexistente dan `fecha_no_admitida`."""
        de_solicitud = anulacion(discrepancia_aceptada(self.concretada(), monto="100.00", descontado="100.00"), usuario=self.gerente)
        for anulacion_id in (de_solicitud.pk, 999999):
            error = self.rechazo(cobranza.resumen_de_cobro, self.gerente, self.datos([self.e1], anulacion_id=anulacion_id, usar_fecha_anulada=True), self.LUEGO)
            self.assertEqual(codigos(error), ["fecha_no_admitida"])


class ComAnlCbrAsientoTests(BaseDeCobranza):
    """CON-04d · paso 1: el contraasiento de la anulación de un cobro (COM-ANL-CBR postcondición c; D-92 puntos 6 y 8; D-86). Lo origina la `Anulacion` (no `contraasentar`, que es del Contador): los movimientos del
    asiento del cobro, con el Debe y el Haber invertidos, con la fecha de hoy (regla «Contraasiento»). Si el cobro no tiene asiento (anterior a CON-04d, D-92 punto 1), no hay contraasiento y la anulación no falla."""

    def registrar(self, entregas_, *, medio="transferencia", hoy=HOY):
        datos = DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[e.pk for e in entregas_], medio_pago=medio)
        return cobranza.registrar_cobro(self.gerente, datos, cobranza.resumen_de_cobro(self.gerente, datos, hoy).huella, hoy)

    def anular(self, pago, *, hoy=HOY):
        with override_settings(CORREO_CONFIGURADO=False), self.captureOnCommitCallbacks(execute=True):
            datos = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, hoy)
            return cobranza.anular_cobro(self.gerente, pago.pk, "Se cargó con el medio equivocado.", False, datos.huella, hoy)

    def lineas(self, asiento):
        return sorted((m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.select_related("cuenta"))

    def test_post_c_la_anulacion_origina_el_contraasiento_del_cobro_completo_incluida_la_indemnizacion(self):
        """Postcondición c: el cobro de dos entregas (una en mora 3 días) tiene Debe Banco 2.900,00 / Haber Deudores 2.000,00 / Haber Atraso 900,00; el contraasiento es lo mismo invertido, originado en la `Anulacion`, con la fecha de hoy."""
        pago = self.registrar([self.en_mora(dias_de_mora=3), self.concretada()])
        original = AsientoContable.objects.get(origen_id=pago.pk)
        lineas_del_original = self.lineas(original)
        anulacion_ = self.anular(pago)
        contra = AsientoContable.objects.get(origen_id=anulacion_.pk)
        self.assertEqual(
            self.lineas(contra),
            sorted([(cuentas.BANCO, HABER, D("2900.00")), (cuentas.DEUDORES_POR_VENTAS, DEBE, D("2000.00")), (cuentas.INDEMNIZACIONES_POR_ATRASO, DEBE, D("900.00"))]),
        )
        self.assertEqual((contra.fecha_asiento, AsientoContable.objects.count()), (HOY, 2))
        self.assertEqual(self.lineas(AsientoContable.objects.get(pk=original.pk)), lineas_del_original)  # el original no se tocó
        verificar_invariantes_contables()

    def test_post_c_un_cobro_en_efectivo_sin_atraso_se_contraasienta_contra_caja(self):
        """Postcondición c: efectivo y sin atraso: Debe Deudores / Haber Caja, por el mismo importe que el original."""
        pago = self.registrar([self.concretada()], medio="efectivo")
        contra = AsientoContable.objects.get(origen_id=self.anular(pago).pk)
        self.assertEqual(self.lineas(contra), sorted([(cuentas.CAJA, HABER, D("1000.00")), (cuentas.DEUDORES_POR_VENTAS, DEBE, D("1000.00"))]))

    def test_regla_contraasiento_usa_los_movimientos_del_original_invertidos_y_la_fecha_de_hoy_aunque_el_cobro_sea_de_otra_fecha(self):
        """Regla «Contraasiento» (COM-ANL-CBR) y D-92 punto 8: se invierte lo que quedó asentado (no se recalcula) y se fecha hoy, cuatro días después del cobro."""
        ejercicio_abierto(HOY - timedelta(days=60))
        pago = self.registrar([self.concretada()], hoy=HOY - timedelta(days=4))
        original = AsientoContable.objects.get(origen_id=pago.pk)
        self.assertEqual(original.fecha_asiento, HOY - timedelta(days=4))
        contra = AsientoContable.objects.get(origen_id=self.anular(pago).pk)
        self.assertEqual(contra.fecha_asiento, HOY)
        invertidos = sorted((c, HABER if t == DEBE else DEBE, i) for c, t, i in self.lineas(original))
        self.assertEqual(self.lineas(contra), invertidos)

    def test_regla_un_cobro_anterior_a_con04d_sin_asiento_se_anula_sin_contraasiento_y_sin_fallar(self):
        """D-92 punto 1 (sin asientos hacia atrás): un cobro sin asiento (anterior a esta tarea) se anula igual; no hay contraasiento porque no hay nada que revertir."""
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", return_value=None):
            pago = self.registrar([self.concretada()])
        self.assertEqual(AsientoContable.objects.count(), 0)
        anulacion_ = self.anular(pago)
        self.assertEqual((PagoCliente.objects.get(pk=pago.pk).estado_pago, AsientoContable.objects.count()), ("anulado", 0))
        self.assertTrue(Anulacion.objects.filter(pk=anulacion_.pk).exists())

    def test_d102_si_el_asiento_del_cobro_esta_en_un_ejercicio_cerrado_el_contraasiento_va_al_abierto_con_la_fecha_de_hoy(self):
        """D-102 y regla «Contraasiento»: el original quedó en un ejercicio ya cerrado; el contraasiento no falla y va al ejercicio abierto con la fecha de hoy. El original no se modifica."""
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", return_value=None):
            pago = self.registrar([self.concretada()], medio="efectivo")
        cerrado = ejercicio(EjercicioContable.Estado.CERRADO, HOY - timedelta(days=400), HOY - timedelta(days=40))
        abierto = ejercicio_abierto(HOY - timedelta(days=39))
        original = asiento_de_prueba(cerrado, HOY - timedelta(days=45), [(cuentas.CAJA, DEBE, D("1000.00")), (cuentas.DEUDORES_POR_VENTAS, HABER, D("1000.00"))], origen=pago)
        contra = AsientoContable.objects.get(origen_id=self.anular(pago).pk)
        self.assertEqual((contra.ejercicio_id, contra.fecha_asiento), (abierto.pk, HOY))
        self.assertEqual(self.lineas(contra), sorted([(cuentas.CAJA, HABER, D("1000.00")), (cuentas.DEUDORES_POR_VENTAS, DEBE, D("1000.00"))]))
        self.assertEqual(AsientoContable.objects.get(pk=original.pk).ejercicio_id, cerrado.pk)
        verificar_invariantes_contables()

    def test_post_f_el_registro_de_auditoria_nombra_el_contraasiento(self):
        """Postcondición f y D-86 punto 4: el único registro `anulacion_cobro` nombra el contraasiento entre sus afectados y en `datos["asientos"]`; no se audita aparte."""
        pago = self.registrar([self.concretada()])
        anulacion_ = self.anular(pago)
        registro = RegistroAuditoria.objects.filter(accion="anulacion_cobro").get()
        contra = AsientoContable.objects.get(origen_id=anulacion_.pk)
        self.assertTrue(any(a["id"] == contra.pk and a["texto"].startswith("Asiento") for a in registro.afectados))
        self.assertEqual(len(registro.detalle["datos"]["asientos"]), 1)

    def test_garantia_si_falla_el_contraasiento_el_cobro_sigue_vigente_y_no_queda_la_anulacion(self):
        """Garantía mínima (atómica): si el contraasiento falla, el cobro sigue «vigente» con sus líneas vigentes, sin `Anulacion`, sin otro asiento y sin el registro de auditoría de la anulación."""
        pago = self.registrar([self.concretada()])
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=RuntimeError("falla del asiento")):
            with self.assertRaises(RuntimeError):
                self.anular(pago)
        self.assertEqual((PagoCliente.objects.get(pk=pago.pk).estado_pago, Anulacion.objects.count(), AsientoContable.objects.count()), ("vigente", 0, 1))
        self.assertEqual((LineaPago.objects.filter(pago=pago, vigente=True).count(), RegistroAuditoria.objects.filter(accion="anulacion_cobro").count()), (1, 0))
