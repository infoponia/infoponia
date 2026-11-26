# Recorrido de CON-04d · Asientos de cobros, indemnizaciones y multas, de punta a punta con el cliente de Django, por rol y por estado (D-96; docs/patrones/verificacion_a_mano.md).
# Una prueba larga a propósito: lo que se verifica es que el flujo ENCADENA bien. El Vendedor revisa y registra el cobro de una entrega en mora (el resumen y la ficha muestran el asiento);
# el Gerente anula ese cobro (el contraasiento) y registra el correcto; el Contador y el Gerente leen los asientos en el libro y en su ficha, con el texto de su origen y sin enlace, y los
# demás roles no (403). Una segunda prueba recorre la indemnización de una discrepancia (aceptar con su asiento, anular con su contraasiento, volver a aceptar: sin asiento y con aviso al
# Contador, decisión del 26/11/2026). Las reglas sueltas están en `test_com_reg_cbr.py`, `test_com_anl_cbr.py`, `test_com_evl_dsc.py`, `test_com_anl_srv.py`, `test_com_rsv_sum.py` y
# `test_com_atn_enr.py`. Lo que solo ve un navegador (CSRF, `Origin`, JavaScript) va en la «Verificación a mano» de la tarea.

from html import unescape

from django.test import override_settings
from django.urls import reverse

from comercial.models import PagoCliente, SolicitudRevision
from comercial.servicios import cobranza, solicitudes
from comercial.tests.base_cobranza import HOY, BaseDeCobranza
from comercial.tests.base_solicitudes import BaseDeSolicitudes
from contabilidad.models import AsientoContable
from contabilidad.tests.fabricas import verificar_invariantes_contables
from core.models import Contador, Notificacion
from core.tests.fabricas import crear_cuenta
from maestros.tests.fabricas import crear_transportista, crear_vendedor


def texto(respuesta):
    return unescape(respuesta.content.decode())


class RecorridoDeAsientosDeDineroTests(BaseDeCobranza):
    def ir(self, nombre, *args, usuario=None, **extra):
        self.client.force_login(usuario or self.gerente)
        return self.client.get(reverse(f"comercial:{nombre}", args=args), **extra)

    def enviar(self, nombre, *args, datos=None, usuario=None, **extra):
        self.client.force_login(usuario or self.gerente)
        return self.client.post(reverse(f"comercial:{nombre}", args=args), datos or {}, **extra)

    def test_recorrido_del_cobro_su_anulacion_y_la_lectura_del_libro_de_punta_a_punta(self):
        vendedor, gerente = self.e.vendedor, self.gerente
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        e = self.en_mora(dias_de_mora=3)  # $ 1.000,00 + 3 × $ 300,00 de atraso = $ 1.900,00
        pedido = {"cliente": str(self.e.cliente.pk), "entrega": [str(e.pk)], "medio_pago": "transferencia", "cliente_fijo": "1"}

        # --- 1. El Vendedor revisa el cobro: el resumen muestra el asiento que se registrará; todavía no hay nada asentado ---
        resumen = texto(self.enviar("cobranza_revisar", datos=pedido, usuario=vendedor))
        for esperado in ("Asiento que se registra al confirmar", "Banco c/c", "Deudores por Ventas", "Indemnizaciones por Atraso en el Pago", "$ 1.900,00", "$ 900,00"):
            self.assertIn(esperado, resumen)
        self.assertNotIn("Fuera de esta ronda", resumen)
        self.assertEqual(AsientoContable.objects.count(), 0)

        # --- 2. Lo confirma: un solo asiento compuesto, con la fecha del cobro; la ficha lo muestra como texto ---
        datos = cobranza.DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[e.pk], medio_pago="transferencia")
        huella = cobranza.resumen_de_cobro(vendedor, datos, HOY).huella
        with override_settings(CORREO_CONFIGURADO=False), self.captureOnCommitCallbacks(execute=True):
            respuesta = self.enviar("cobranza_registrar", datos={**pedido, "accion": "confirmar", "huella": huella}, usuario=vendedor)
        self.assertEqual(respuesta.status_code, 302)
        pago = PagoCliente.objects.get(tipo_pago="suministro")
        cobro_asiento = AsientoContable.objects.get(origen_id=pago.pk)
        self.assertEqual((AsientoContable.objects.count(), cobro_asiento.numero_asiento, cobro_asiento.fecha_asiento), (1, 1, HOY))
        ficha = texto(self.ir("cobro", pago.pk, usuario=vendedor))
        self.assertIn("Asiento del cobro", ficha)
        self.assertIn("Asiento N.º 1", ficha)

        # --- 3. El Gerente anula el cobro: la pantalla muestra el contraasiento que se registrará y, al confirmar, la ficha muestra los dos asientos ---
        pantalla = texto(self.ir("cobro_anular", pago.pk, usuario=gerente))
        self.assertIn("Contraasiento que se registra", pantalla)
        huella_anulacion = cobranza.datos_de_anulacion_de_cobro(gerente, pago.pk, HOY).huella
        with override_settings(CORREO_CONFIGURADO=False), self.captureOnCommitCallbacks(execute=True):
            self.enviar("cobro_anular", pago.pk, datos={"huella": huella_anulacion, "motivo": "Se cargó con el medio equivocado."}, usuario=gerente)
        self.assertEqual(AsientoContable.objects.count(), 2)
        ficha = texto(self.ir("cobro", pago.pk, usuario=gerente))
        self.assertIn("Contraasiento de la anulación", ficha)
        self.assertIn("Asiento N.º 2", ficha)

        # --- 4. El Contador y el Gerente leen el libro y cada ficha, con el texto de su origen y sin enlace; los demás roles no entran (403) ---
        libro = reverse("contabilidad:libro")
        for rol in (self.e.agronomo, self.e.capataz, vendedor, crear_transportista(email="t2@infoponia.com")):
            self.client.force_login(rol)
            self.assertEqual(self.client.get(libro).status_code, 403, rol)
        ejercicio_id = cobro_asiento.ejercicio_id
        for lector in (contador, gerente):
            self.client.force_login(lector)
            self.assertEqual(self.client.get(libro).status_code, 200)
            primero = texto(self.client.get(reverse("contabilidad:asiento", args=[ejercicio_id, 1])))
            segundo = texto(self.client.get(reverse("contabilidad:asiento", args=[ejercicio_id, 2])))
            self.assertIn(f"Cobro {pago.codigo}", primero)
            self.assertIn(f"Anulación del cobro {pago.codigo}", segundo)
            self.assertNotRegex(primero, rf"<a [^>]*>[^<]*Cobro {pago.codigo}")
            self.assertNotRegex(segundo, rf"<a [^>]*>[^<]*Anulación del cobro {pago.codigo}")

        # --- 5. El cobro correcto se registra de nuevo: otro asiento (el N.º 3) ---
        datos = cobranza.DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[e.pk], medio_pago="efectivo")
        huella = cobranza.resumen_de_cobro(gerente, datos, HOY).huella
        with override_settings(CORREO_CONFIGURADO=False), self.captureOnCommitCallbacks(execute=True):
            self.enviar("cobranza_registrar", datos={**pedido, "medio_pago": "efectivo", "accion": "confirmar", "huella": huella}, usuario=gerente)
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2, 3])
        verificar_invariantes_contables()


class RecorridoDeIndemnizacionesTests(BaseDeSolicitudes):
    def test_recorrido_de_la_indemnizacion_aceptar_anular_y_volver_a_aceptar(self):
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        x = self.armar()
        datos_de_aceptar = solicitudes.DatosDeResolucion("aceptar", "", "", "")
        self.client.force_login(self.gerente)

        # --- 1. El Gerente revisa: el resumen muestra el asiento de la indemnización de $ 15,00 contra Deudores por Ventas ---
        resumen = texto(self.client.post(reverse("comercial:solicitud_resolver_revisar", args=[x.solicitud.pk]), {"decision": "aceptar"}))
        for esperado in ("Asiento que se registra al confirmar", "Indemnizaciones por Incumplimiento a Cliente", "Deudores por Ventas", "$ 15,00"):
            self.assertIn(esperado, resumen)
        self.assertEqual(AsientoContable.objects.count(), 0)

        # --- 2. Confirma: un asiento con la solicitud de origen; el Contador lo lee en su ficha como texto ---
        huella = solicitudes.resumen_de_resolucion(self.gerente, x.solicitud.pk, datos_de_aceptar).huella
        self.client.post(reverse("comercial:solicitud_resolver", args=[x.solicitud.pk]), {"decision": "aceptar", "huella": huella})
        asiento = AsientoContable.objects.get(origen_id=x.solicitud.pk)
        self.client.force_login(contador)
        ficha = texto(self.client.get(reverse("contabilidad:asiento", args=[asiento.ejercicio_id, asiento.numero_asiento])))
        self.assertIn(f"Indemnización de la discrepancia {x.solicitud.codigo}", ficha)

        # --- 3. El Gerente anula la resolución: la pantalla muestra el contraasiento y, al confirmar, queda registrado ---
        self.client.force_login(self.gerente)
        self.assertIn("Contraasiento que se registra", texto(self.client.get(reverse("comercial:solicitud_anular", args=[x.solicitud.pk]))))
        huella = solicitudes.datos_de_anulacion(self.gerente, x.solicitud.pk).huella
        self.client.post(reverse("comercial:solicitud_anular", args=[x.solicitud.pk]), {"huella": huella, "motivo": "Se aceptó por error."})
        self.assertEqual(AsientoContable.objects.count(), 2)
        self.assertEqual(SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, "pendiente")

        # --- 4. La vuelve a aceptar: NO asienta (un origen, un asiento) y avisa al Contador para que lo registre a mano ---
        huella = solicitudes.resumen_de_resolucion(self.gerente, x.solicitud.pk, datos_de_aceptar).huella
        self.client.post(reverse("comercial:solicitud_resolver", args=[x.solicitud.pk]), {"decision": "aceptar", "huella": huella})
        self.assertEqual(SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, "aceptada")
        self.assertEqual(AsientoContable.objects.count(), 2)
        (aviso,) = Notificacion.objects.filter(destinatario=contador, titulo__startswith=f"Registrar el asiento de {x.solicitud.codigo}")
        self.assertIn("registrá a mano", aviso.detalle)

        # --- 5. El Vendedor y el Agrónomo no ven la anulación (403) ---
        for rol in (self.e.vendedor, self.e.agronomo, crear_vendedor(email="ajeno@infoponia.com")):
            self.client.force_login(rol)
            self.assertEqual(self.client.get(reverse("comercial:solicitud_anular", args=[x.solicitud.pk])).status_code, 403, rol)
        verificar_invariantes_contables()
