# Pruebas de COM-RSV-QJA · Resolver Queja (COM-07a, paso 5): `solicitudes.resumen_de_resolucion`, `resolver_solicitud` y `resolver_queja` con una queja por retraso (la indemnización sale de la cláusula) o por estado de la
# mercadería u otro (la carga el Gerente, de 0 al tope de MD-114). Lo que comparte con COM-EVL-DSC (la huella, los bloqueos, las extensiones 6a a 8b) se prueba a fondo en `test_com_evl_dsc.py`; acá, lo propio de la queja:
# los montos, 4a, 4a.3a, 4b, 6d con monto manual, el aviso de aceptación sin indemnización y la auditoría. Datos: `BaseDeSolicitudes.armar(tipo="queja", …)`: 10 plantas por período a $100 con 5 entregadas, o sea un
# tope de $500,00 (5 × $100) y, en la queja por retraso, $10 por día de retraso.
# Fuente: docs/casos_de_uso/comercial/solicitudes.md («COM-RSV-QJA», «Cálculos», «Registrar la resolución»), MD-114, MD-115, D-57, D-68 punto 6 y D-69. Las pruebas numeran las extensiones.
#
# Contrato de código que fijan estas pruebas: `resolver_queja(actor, solicitud_id, datos, huella)`; `DatosDeResolucion(decision, observaciones, monto, medio_reintegro)` con el `monto` como texto (coma o punto);
# códigos `monto_invalido` (con el tope en el mensaje) y `monto_no_admitido`; `FichaDeSolicitud.intento_en_plazo` (4b) y `.intentos`.

from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import override_settings

from comercial.models import IntentoFallido, Queja, SolicitudRevision, Suministro
from comercial.servicios import solicitudes
from comercial.tests.base_solicitudes import BaseDeSolicitudes, HOY, codigos
from comercial.tests.fabricas import queja_aceptada, transportista_con_vehiculo
from contabilidad.models import AsientoContable
from core.models import RegistroAuditoria
from maestros.models import Alerta
from produccion.models import Bitacora

D = Decimal


class ComRsvQjaServicioTests(BaseDeSolicitudes):
    def solicitud(self, x):
        return SolicitudRevision.objects.get(pk=x.solicitud.pk)

    def contrato(self, x):
        return Suministro.objects.get(pk=x.contrato.pk)

    def retraso(self, **kw):
        kw.setdefault("retraso", 3)
        return self.armar(tipo="queja", queja_tipo="retraso", entregada=10, **kw)

    # ---- la queja por retraso (la indemnización sale de la cláusula) ----

    def test_flujo_principal_acepta_una_queja_por_retraso_y_descuenta_la_indemnizacion(self):
        """Pasos 6 a 10: 3 días × $10 = $30,00, descontados del monto a cobrar ($1.000,00 → $970,00); la queja queda aceptada, el contrato suma un incumplimiento y la alerta se resuelve."""
        x = self.retraso()
        resumen = self.resumen(x.solicitud)
        self.assertEqual((resumen.monto, resumen.descontado, resumen.reintegrado), (D("30.00"), D("30.00"), D("0.00")))
        self.assertEqual((resumen.monto_a_cobrar_antes, resumen.monto_a_cobrar_despues), (D("1000.00"), D("970.00")))
        resuelta = self.resolver(x.solicitud, observaciones="El camión llegó tarde.")
        self.assertEqual((resuelta.estado_solicitud, resuelta.tipo_solicitud), ("aceptada", "queja"))
        s = self.solicitud(x)
        self.assertEqual((s.fecha_resolucion, s.gerente_id, s.monto_indemnizacion, s.monto_descontado), (HOY, self.gerente.pk, D("30.00"), D("30.00")))
        self.assertEqual(self.contrato(x).cantidad_incumplimientos, 1)
        self.assertEqual(Alerta.objects.get(vinculo_comercial__solicitud=x.solicitud.pk).estado_alerta, "resuelta")
        self.assertEqual(AsientoContable.objects.count(), 0)  # postcondición e: fuera de la ronda (D-57)

    def test_regla_retraso_suma_los_detalles_con_dias_de_retraso(self):
        """Regla «Retraso»: la suma de todos los detalles de la queja: dos líneas con 3 días a $10 cada una = $60,00."""
        x = self.armar(tipo="queja", queja_tipo="retraso", entregada=10, retraso=3, dos_lineas=True)
        self.assertEqual(self.resumen(x.solicitud).monto, D("60.00"))

    def test_regla_retraso_con_plazo_de_entrega_solo_cuentan_los_dias_pasados_del_plazo(self):
        """Regla «Retraso»: días = fecha real − (fecha del período + plazo de entrega): plazo 2 y 3 días pasados del plazo = 3 días, $30,00."""
        x = self.retraso(plazo_entrega=2)
        self.assertEqual(self.resumen(x.solicitud).monto, D("30.00"))
        self.assertEqual(solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk).lectura.lineas[0].dias, 3)

    def test_ext_4a_una_queja_por_retraso_no_admite_un_monto(self):
        """El monto de una queja por retraso es el de la cláusula y nadie lo modifica: cargarlo da `monto_no_admitido`."""
        x = self.retraso()
        error = self.rechazo(self.resolver, x.solicitud, monto="500")
        self.assertEqual((codigos(error), list(error.error_dict)), (["monto_no_admitido"], ["monto"]))
        self.assertEqual(self.solicitud(x).estado_solicitud, "pendiente")

    def test_ext_4b_la_ficha_destaca_un_intento_fallido_dentro_del_plazo(self):
        """Extensión 4b y D-68 punto 6: un intento fallido con fecha programada dentro del plazo de algún detalle se destaca; fuera del plazo o sin intentos, no; el Gerente decide."""
        x = self.retraso()
        self.assertEqual((solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk).intento_en_plazo, solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk).intentos), (False, []))
        transportista = transportista_con_vehiculo(self.e.invernadero)
        IntentoFallido.objects.create(entrega=x.entrega, transportista=transportista, fecha_programada=x.detalle.fecha_primer_entrega, motivo="cliente_ausente", descripcion="No había nadie.")
        ficha = solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk)
        self.assertEqual(([i.motivo for i in ficha.intentos], ficha.intento_en_plazo), (["cliente_ausente"], True))
        IntentoFallido.objects.all().delete()
        IntentoFallido.objects.create(entrega=x.entrega, transportista=transportista, fecha_programada=HOY, motivo="otro")
        self.assertFalse(solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk).intento_en_plazo)

    def test_ext_4b_el_sistema_no_descarta_la_queja_solo_decide_el_gerente(self):
        """Regla «Intento fallido»: con un intento dentro del plazo el servicio igual permite aceptar (decide el Gerente)."""
        x = self.retraso()
        IntentoFallido.objects.create(entrega=x.entrega, transportista=transportista_con_vehiculo(self.e.invernadero), fecha_programada=x.detalle.fecha_primer_entrega, motivo="cliente_ausente")
        self.assertFalse(self.resumen(x.solicitud).hay_errores)
        self.assertEqual(self.resolver(x.solicitud).estado_solicitud, "aceptada")

    def test_post_f_el_evento_de_bitacora_lleva_los_dias_de_retraso_y_el_total(self):
        """Postcondición f: «SR-… · Queja por retraso · OT-… de SUM-… · … · Lechuga…: 3 días, $ 30,00 · Total: $ 30,00»."""
        x = self.retraso()
        self.resolver(x.solicitud)
        evento = Bitacora.objects.get(tipo_evento="incumplimiento_de_clausula")
        for texto in (x.solicitud.codigo, "Queja por retraso", x.entrega.codigo, "3 días, $ 30,00", "Total: $ 30,00"):
            self.assertIn(texto, evento.descripcion_evento)
        self.assertEqual((evento.lote_id, evento.etapa_id), (None, None))

    # ---- la queja por estado de la mercadería u otro (la carga el Gerente) ----

    def test_ext_4a_sin_monto_o_con_cero_la_queja_se_acepta_sin_indemnizacion(self):
        """Extensión 4a.4: sin monto (o con 0) el resumen no tiene cambios en lo que el cliente debe, el monto queda en 0 y no hay asiento; igual suma un incumplimiento y deja el evento."""
        for monto in ("", "0", "0,00"):
            with self.subTest(monto=monto):
                x = self.armar(tipo="queja")
                resumen = self.resumen(x.solicitud, monto=monto)
                self.assertEqual((resumen.monto, resumen.descontado, resumen.reintegrado, resumen.monto_a_cobrar_despues), (D("0.00"), D("0.00"), D("0.00"), D("500.00")))
                self.resolver(x.solicitud, monto=monto)
                s = self.solicitud(x)
                self.assertEqual((s.estado_solicitud, s.monto_indemnizacion, s.monto_descontado, s.monto_reintegrado, s.medio_reintegro), ("aceptada", D("0.00"), D("0.00"), D("0.00"), None))
                self.assertEqual(self.contrato(x).cantidad_incumplimientos, 1)
        self.assertEqual(AsientoContable.objects.count(), 0)
        self.assertEqual(Bitacora.objects.filter(tipo_evento="incumplimiento_de_clausula").count(), 3)

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_g_sin_indemnizacion_el_cliente_recibe_un_aviso_de_aceptacion_sin_comprobante(self):
        """Postcondición g: sin indemnización, un aviso de que la queja fue aceptada (número, tipo, entrega y observaciones); con indemnización, el comprobante."""
        x = self.armar(tipo="queja")
        with self.captureOnCommitCallbacks(execute=True):
            self.resolver(x.solicitud, observaciones="Lo vamos a tener en cuenta.")
        (correo,) = mail.outbox
        self.assertIn("fue aceptada", correo.subject)
        self.assertNotIn("Comprobante de indemnización", correo.subject)
        for texto in (x.solicitud.codigo, "estado de la mercadería", x.entrega.codigo, "Lo vamos a tener en cuenta.", "no corresponde una indemnización"):
            self.assertIn(texto, correo.body)

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_g_con_indemnizacion_el_cliente_recibe_el_comprobante_con_las_dos_partes(self):
        """Postcondición g y 9a: el comprobante indica cuánto se descontó y cuánto se reintegró y con qué medio."""
        x = self.armar(tipo="queja")
        queja_aceptada(x.entrega, "otro", monto="400.00")  # el monto a cobrar queda en $100
        with self.captureOnCommitCallbacks(execute=True):
            self.resolver(x.solicitud, monto="300", medio="transferencia")
        (correo,) = mail.outbox
        self.assertIn("Comprobante de indemnización", correo.subject)
        for texto in ("$ 300,00", "Descontado de lo que debés por la entrega: $ 100,00", "Reintegrado a vos: $ 200,00 (transferencia)", "sin validez fiscal"):
            self.assertIn(texto, correo.body)

    def test_ext_4a_3a_el_monto_cargado_no_valido_se_rechaza_con_el_tope(self):
        """Extensión 4a.3a: negativo, con tres decimales, que no es un número o que supera el tope ($500,00 = 5 × $100): `monto_invalido`, el mensaje dice el tope y no se escribe nada."""
        x = self.armar(tipo="queja")
        for monto in ("-1", "10,123", "abc", "500,01", "1000"):
            with self.subTest(monto=monto):
                resumen = self.resumen(x.solicitud, monto=monto)
                (codigo, mensaje), = resumen.errores["monto"]
                self.assertEqual(codigo, "monto_invalido")
                self.assertIn("$ 500,00", mensaje)
                self.assertEqual(codigos(self.rechazo(self.resolver, x.solicitud, monto=monto)), ["monto_invalido"])
        self.assertEqual(self.solicitud(x).estado_solicitud, "pendiente")

    def test_regla_tope_del_monto_manual_el_tope_exacto_vale_y_es_lo_pagado_por_los_detalles_de_la_queja(self):
        """Regla «Tope del monto manual»: el tope exacto ($500,00) vale; es lo que el cliente paga por los **detalles de la queja** (corrige al prototipo, que usaba el total de la entrega)."""
        x = self.armar(tipo="queja", dos_lineas=True)  # la entrega suma $1.000, pero la queja se refiere solo a la primera línea
        from comercial.models import DetalleEntrega

        Queja.objects.get(pk=x.solicitud.pk).detalles.set(DetalleEntrega.objects.filter(entrega=x.entrega).order_by("pk")[:1])
        resumen = self.resumen(x.solicitud, monto="500")
        self.assertEqual((resumen.lectura.tope, resumen.monto), (D("500.00"), D("500.00")))
        self.assertEqual(self.resumen(x.solicitud, monto="500,01").errores["monto"][0][0], "monto_invalido")

    def test_ext_4a_el_monto_acepta_coma_o_punto_y_se_guarda_con_dos_decimales(self):
        """Lista de variaciones 4b: el monto en pesos con dos decimales, con coma o con punto."""
        for texto, esperado in (("120,5", "120.50"), ("120.55", "120.55")):
            with self.subTest(texto=texto):
                x = self.armar(tipo="queja", queja_tipo="otro")
                self.resolver(x.solicitud, monto=texto)
                self.assertEqual(self.solicitud(x).monto_indemnizacion, D(esperado))

    def test_ext_6d_con_monto_manual_mayor_que_lo_que_queda_a_cobrar_el_resto_se_reintegra(self):
        """Extensión 6d: tras otra aceptación que deja $100 por cobrar, $300 se descuentan en $100 y $200 se reintegran con el medio; el monto a cobrar queda en $0 (nunca negativo); sin medio se pide."""
        x = self.armar(tipo="queja")
        queja_aceptada(x.entrega, "otro", monto="400.00")
        resumen = self.resumen(x.solicitud, monto="300")
        self.assertEqual((resumen.descontado, resumen.reintegrado, resumen.monto_a_cobrar_antes, resumen.monto_a_cobrar_despues), (D("100.00"), D("200.00"), D("100.00"), D("0.00")))
        self.assertEqual(codigos(self.rechazo(self.resolver, x.solicitud, monto="300")), ["medio_obligatorio"])
        self.resolver(x.solicitud, monto="300", medio="efectivo")
        s = self.solicitud(x)
        self.assertEqual((s.monto_indemnizacion, s.monto_descontado, s.monto_reintegrado, s.medio_reintegro), (D("300.00"), D("100.00"), D("200.00"), "efectivo"))
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([x.entrega.pk])[x.entrega.pk], D("0.00"))

    def test_ext_6a_con_la_entrega_pagada_se_reintegra_todo(self):
        """Extensión 6a: pagada ⇒ todo se reintegra con el medio elegido (`estado_de_pago` simulado, D-69 punto 8)."""
        x = self.armar(tipo="queja")
        with mock.patch("comercial.servicios.entregas.estado_de_pago", return_value={x.entrega.pk: "pagada"}):
            self.resolver(x.solicitud, monto="80", medio="transferencia")
        s = self.solicitud(x)
        self.assertEqual((s.monto_descontado, s.monto_reintegrado, s.medio_reintegro), (D("0.00"), D("80.00"), "transferencia"))

    # ---- decisiones, extensiones comunes y reglas ----

    def test_ext_5a_rechaza_con_observaciones_y_avisa(self):
        """Extensión 5a: rechazada sin indemnización ni incumplimiento ni bitácora; observaciones obligatorias (5b); el Vendedor recibe la decisión."""
        x = self.armar(tipo="queja")
        self.assertEqual(self.resumen(x.solicitud, "rechazar").errores["observaciones"][0][0], "observaciones_obligatorias")
        self.resolver(x.solicitud, "rechazar", "No corresponde.", monto="999")  # el monto se ignora al rechazar
        s = self.solicitud(x)
        self.assertEqual((s.estado_solicitud, s.monto_indemnizacion, self.contrato(x).cantidad_incumplimientos), ("rechazada", None, 0))
        self.assertEqual(Bitacora.objects.filter(tipo_evento="incumplimiento_de_clausula").count(), 0)
        (aviso,) = self.avisos(self.e.vendedor, f"{x.solicitud.codigo} rechazada")
        self.assertIn("No corresponde.", aviso.detalle)

    def test_ext_6b_y_6c_los_tolerados_y_el_estado_del_contrato(self):
        """6b: superar los tolerados lo advierte y dispara la resolución después del commit; 6c: un contrato finalizado lo registra como historial."""
        x = self.armar(tipo="queja", tolerados=1, incumplimientos=1)
        self.assertTrue(self.resumen(x.solicitud).resolveria)
        with mock.patch("comercial.servicios.resoluciones.resolver_si_corresponde") as resolver:
            with self.captureOnCommitCallbacks(execute=True):
                self.resolver(x.solicitud)
        resolver.assert_called_once_with(x.contrato.pk)
        y = self.armar(tipo="queja", tolerados=0, estado_contrato="finalizado")
        self.assertEqual((self.resumen(y.solicitud).historial, self.resumen(y.solicitud).resolveria), (True, False))
        self.resolver(y.solicitud)
        self.assertEqual(self.contrato(y).cantidad_incumplimientos, 1)

    def test_ext_8a_y_8b_ya_resuelta_y_huella(self):
        """8a: ya no pendiente ⇒ `solicitud_no_pendiente`; 8b: si cambió un dato del resumen ⇒ `solicitud_cambio`."""
        x = self.armar(tipo="queja")
        resumen = self.resumen(x.solicitud)
        Suministro.objects.filter(pk=x.contrato.pk).update(estado_suministro="finalizado")
        error = self.rechazo(solicitudes.resolver_solicitud, self.gerente, x.solicitud.pk, self.datos(), resumen.huella)
        self.assertEqual(codigos(error), ["solicitud_cambio"])
        Suministro.objects.filter(pk=x.contrato.pk).update(estado_suministro="vigente")
        self.resolver(x.solicitud)
        self.assertEqual(codigos(self.rechazo(solicitudes.resolver_solicitud, self.gerente, x.solicitud.pk, self.datos(), resumen.huella)), ["solicitud_no_pendiente"])

    def test_post_j_y_l_un_registro_de_auditoria_de_la_resolucion_de_la_queja(self):
        """Postcondiciones k y l: un registro `resolucion_queja` con la queja como afectada principal, la alerta, el suministro y el evento de bitácora."""
        x = self.retraso()
        self.resolver(x.solicitud)
        (registro,) = RegistroAuditoria.objects.filter(accion="resolucion_queja")
        self.assertEqual([a["modelo"] for a in registro.afectados], ["comercial.queja", "maestros.alerta", "comercial.suministro", "produccion.bitacora"])
        self.assertEqual(registro.detalle["cambios"]["monto_indemnizacion"], {"antes": None, "despues": "30.00"})
        self.assertEqual(RegistroAuditoria.objects.filter(accion="evaluacion_discrepancia").count(), 0)

    def test_regla_solo_el_gerente_activo_y_el_tipo_correcto(self):
        """Solo el Gerente activo resuelve; `resolver_queja` sobre una discrepancia es `Http404`."""
        x = self.armar(tipo="queja")
        with self.assertRaises(PermissionDenied):
            solicitudes.resolver_queja(self.e.vendedor, x.solicitud.pk, self.datos(), "")
        d = self.armar()
        with self.assertRaises(Http404):
            solicitudes.resolver_queja(self.gerente, d.solicitud.pk, self.datos(), "")
        resumen = self.resumen(x.solicitud)
        self.assertEqual(solicitudes.resolver_queja(self.gerente, x.solicitud.pk, self.datos(), resumen.huella).estado_solicitud, "aceptada")

    def test_garantia_la_resolucion_es_atomica(self):
        """Garantías mínimas: si falla a mitad no queda ningún cambio (la queja sigue pendiente, con su alerta sin resolver)."""
        x = self.armar(tipo="queja")
        resumen = self.resumen(x.solicitud)
        with mock.patch("comercial.servicios.solicitudes.alertas.resolver_alerta", side_effect=RuntimeError("falló")):
            with self.assertRaises(RuntimeError):
                solicitudes.resolver_solicitud(self.gerente, x.solicitud.pk, self.datos(), resumen.huella)
        self.assertEqual((self.solicitud(x).estado_solicitud, self.contrato(x).cantidad_incumplimientos, Bitacora.objects.filter(tipo_evento="incumplimiento_de_clausula").count()), ("pendiente", 0, 0))
