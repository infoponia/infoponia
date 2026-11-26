# Pruebas de COM-ANL-SRV · Anular Resolución de Solicitud (COM-07a, paso 6): `solicitudes.datos_de_anulacion` y `anular_resolucion`. Una por postcondición (a a f; el contraasiento, c, es «Fuera de la ronda»: no se crea) y
# extensión (2a con `resolucion_del_suministro`, 2b con `mock.patch` de `estado_de_pago`, 2c con reintegro total y parcial, 2d, 3a, 5a); el contador no baja de 0; la copia de la resolución en la `Anulacion`; volver a
# resolver después de anular (la alerta no cambia) y dos anulaciones seguidas. COM-ANL-SRV no numera sus reglas (`test_regla_<nombre>_…`).
# Fuente: docs/casos_de_uso/comercial/solicitudes.md («COM-ANL-SRV», «Anular una resolución»), D-57, D-69 puntos 4, 5, 6, 10 y 11, MD-135.
#
# Contrato de código que fijan estas pruebas: `datos_de_anulacion(actor, solicitud_id) -> DatosDeAnulacion` (`aceptada`, `contador_antes/despues`, `monto_a_cobrar_antes/despues`, `bloqueo` = `(código, mensaje)` o `None`,
# `huella`); `anular_resolucion(actor, solicitud_id, motivo, huella) -> Anulacion`; códigos `motivo_obligatorio`, `motivo_largo` (en `motivo`), `solicitud_no_resuelta`, `resolucion_del_contrato`, `entrega_cobrada`,
# `indemnizacion_reintegrada` y `solicitud_cambio`.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import Http404

from comercial.models import AlertaComercial, Anulacion, LineaDiscrepancia, SolicitudRevision, Suministro
from comercial.servicios import solicitudes
from comercial.tests.fabricas import cobro
from comercial.tests.base_solicitudes import BaseDeSolicitudes, HOY, codigos, poner_estado
from comercial.tests.fabricas import queja_aceptada, resolucion_del_suministro
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador, RegistroAuditoria, Usuario
from core.tests.fabricas import crear_cuenta
from maestros.models import Alerta
from produccion.models import Bitacora

D = Decimal
MOTIVO = "Me equivoqué al decidir."


class ComAnlSrvServicioTests(BaseDeSolicitudes):
    def solicitud(self, x):
        return SolicitudRevision.objects.get(pk=x.solicitud.pk)

    def contrato(self, x):
        return Suministro.objects.get(pk=x.contrato.pk)

    def aceptada(self, **kw):
        """Una discrepancia aceptada (por el servicio): $15,00 descontados; el monto a cobrar de la entrega queda en $485,00."""
        x = self.armar(**kw)
        self.resolver(x.solicitud)
        return x

    def datos_anul(self, x):
        return solicitudes.datos_de_anulacion(self.gerente, x.solicitud.pk)

    def anular(self, x, motivo=MOTIVO, huella=None, actor=None):
        datos = self.datos_anul(x)
        return solicitudes.anular_resolucion(actor or self.gerente, x.solicitud.pk, motivo, datos.huella if huella is None else huella)

    # ---- el flujo y las postcondiciones ----

    def test_flujo_principal_anula_una_discrepancia_aceptada_que_conto_como_incumplimiento(self):
        """Pasos 2 a 7: el paso 2 dice el contador 1 → 0 y el monto a cobrar $485,00 → $500,00; al confirmar, la solicitud vuelve a pendiente y se puede volver a resolver."""
        x = self.aceptada()
        datos = self.datos_anul(x)
        self.assertEqual((datos.aceptada, datos.contador_antes, datos.contador_despues, datos.monto_a_cobrar_antes, datos.monto_a_cobrar_despues, datos.bloqueo), (True, 1, 0, D("485.00"), D("500.00"), None))
        self.assertEqual(datos.estado_nuevo, "Pendiente de revisión")
        anulacion = self.anular(x)
        self.assertIsInstance(anulacion, Anulacion)
        self.assertEqual(self.solicitud(x).estado_solicitud, "pendiente")
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([x.entrega.pk])[x.entrega.pk], D("500.00"))

    def test_post_a_la_solicitud_vuelve_a_pendiente_con_sus_campos_de_resolucion_vacios(self):
        """Postcondición a: vuelve a «pendiente»; la fecha, el Gerente, las observaciones, los montos, el medio y el aviso quedan vacíos (la restricción de la base lo exige) y los montos de las líneas, en nulo."""
        x = self.aceptada()
        self.anular(x)
        s = self.solicitud(x)
        self.assertEqual((s.estado_solicitud, s.fecha_resolucion, s.gerente_id, s.observaciones_resolucion, s.monto_indemnizacion, s.monto_descontado, s.monto_reintegrado, s.medio_reintegro, s.estado_aviso_cliente),
                         ("pendiente", None, None, "", None, None, None, None, None))
        self.assertEqual(list(LineaDiscrepancia.objects.filter(discrepancia_id=s.pk).values_list("monto_indemnizacion_linea", flat=True)), [None])

    def test_post_b_se_crea_la_anulacion_con_fecha_motivo_usuario_y_solicitud(self):
        """Postcondición b (MD-135): una `Anulacion` con la fecha de hoy, el motivo, el usuario y la solicitud anulada; es un `OrigenDocumento` de tipo «anulacion»."""
        x = self.aceptada()
        a = self.anular(x, "  " + MOTIVO + "  ")
        self.assertEqual((a.fecha_anulacion, a.motivo_anulacion, a.usuario_id, a.solicitud_id, a.tipo), (HOY, MOTIVO, self.gerente.pk, x.solicitud.pk, "anulacion"))

    def test_post_b_la_anulacion_guarda_una_copia_de_la_resolucion_anulada(self):
        """D-69 punto 10: estado, fecha, Gerente, observaciones, monto, descontado, reintegrado y medio de lo que se anuló (para el historial de la ficha)."""
        x = self.armar(por_planta="200.00")
        self.resolver(x.solicitud, observaciones="Procede.", medio="efectivo")
        a_datos = self.datos_anul(x)
        self.assertEqual(a_datos.bloqueo[0], "indemnizacion_reintegrada")  # con reintegro no se anula: la copia se prueba con el descuento total
        y = self.armar()
        self.resolver(y.solicitud, observaciones="Procede.")
        a = self.anular(y)
        self.assertEqual(
            (a.estado_anulado, a.fecha_resolucion_anulada, a.gerente_anulado_id, a.observaciones_anuladas, a.monto_indemnizacion_anulado, a.monto_descontado_anulado, a.monto_reintegrado_anulado, a.medio_reintegro_anulado),
            ("aceptada", HOY, self.gerente.pk, "Procede.", D("15.00"), D("15.00"), D("0.00"), None),
        )

    def test_post_c_el_contador_baja_en_uno_y_el_monto_a_cobrar_vuelve(self):
        """Postcondición c: el contador de incumplimientos baja en 1 y el monto a cobrar vuelve a su valor sin la indemnización. El contraasiento (antes «Fuera de esta ronda», D-57) lo prueba `ComAnlSrvAsientoTests` (CON-04d)."""
        x = self.aceptada(incumplimientos=1)
        self.assertEqual(self.contrato(x).cantidad_incumplimientos, 2)
        self.anular(x)
        self.assertEqual(self.contrato(x).cantidad_incumplimientos, 1)

    def test_post_d_el_evento_de_bitacora_va_en_el_invernadero_de_origen_solo_si_estaba_aceptada(self):
        """Postcondición d y D-69 punto 6: un evento `anulacion_de_resolucion` en el invernadero de origen de la entrega, con el motivo; una rechazada no deja bitácora."""
        x = self.aceptada()
        self.anular(x)
        evento = Bitacora.objects.get(tipo_evento="anulacion_de_resolucion")
        self.assertEqual((evento.invernadero_id, evento.lote_id, evento.responsable_id), (x.entrega.invernadero_id, None, self.gerente.pk))
        for texto in (x.solicitud.codigo, x.entrega.codigo, x.contrato.codigo, "vuelve a pendiente", MOTIVO):
            self.assertIn(texto, evento.descripcion_evento)
        y = self.armar()
        self.resolver(y.solicitud, "rechazar", "No.")
        self.anular(y)
        self.assertEqual(Bitacora.objects.filter(tipo_evento="anulacion_de_resolucion").count(), 1)

    def test_post_d_el_motivo_largo_se_recorta_en_el_evento_de_bitacora(self):
        """El evento de bitácora admite hasta 500: con un motivo de 500 caracteres la descripción se recorta y la anulación se registra igual."""
        x = self.aceptada()
        self.anular(x, "m" * 500)
        self.assertLessEqual(len(Bitacora.objects.get(tipo_evento="anulacion_de_resolucion").descripcion_evento), 500)

    def test_post_e_se_notifica_al_vendedor_con_el_monto_a_cobrar_y_los_incumplimientos(self):
        """Postcondición e: «Monto a cobrar: $ 485,00 → $ 500,00. Incumplimientos: 1 → 0. Motivo: …»."""
        x = self.aceptada()
        self.anular(x)
        (aviso,) = self.avisos(self.e.vendedor, f"Se anuló la resolución de {x.solicitud.codigo}")
        for texto in ("$ 485,00 → $ 500,00", "Incumplimientos: 1 → 0", MOTIVO, x.entrega.codigo):
            self.assertIn(texto, aviso.detalle)

    def test_post_f_un_registro_de_auditoria_con_la_solicitud_la_anulacion_el_suministro_y_la_bitacora(self):
        """Postcondición f: `anulacion_resolucion_solicitud` con el Gerente; afectados: la solicitud (principal, con los valores anteriores y nuevos), la anulación, el suministro y el evento; el motivo en `datos`."""
        x = self.aceptada()
        a = self.anular(x)
        (registro,) = RegistroAuditoria.objects.filter(accion="anulacion_resolucion_solicitud")
        self.assertEqual([m["modelo"] for m in registro.afectados], ["comercial.discrepanciaentrega", "comercial.anulacion", "comercial.suministro", "produccion.bitacora", "contabilidad.asientocontable"])  # CON-04d: el contraasiento entra en los afectados
        self.assertEqual(registro.afectados[1]["id"], a.pk)
        self.assertEqual(registro.detalle["cambios"]["estado_solicitud"], {"antes": "aceptada", "despues": "pendiente"})
        self.assertEqual(registro.detalle["cambios"]["monto_descontado"], {"antes": "15.00", "despues": None})
        self.assertEqual(registro.detalle["datos"]["motivo"], MOTIVO)

    def test_regla_la_alerta_no_se_toca_y_no_se_crea_otra(self):
        """D-69 punto 4: la `AlertaComercial` sigue siendo una sola y queda resuelta; la solicitud pendiente se ve en la pestaña."""
        x = self.aceptada()
        self.anular(x)
        self.assertEqual(AlertaComercial.objects.filter(solicitud_id=x.solicitud.pk).count(), 1)
        self.assertEqual(Alerta.objects.get(vinculo_comercial__solicitud=x.solicitud.pk).estado_alerta, "resuelta")

    # ---- bloqueos (2a a 2c) y la solicitud rechazada (2d) ----

    def test_ext_2a_si_la_aceptacion_resolvio_el_contrato_no_se_puede_anular(self):
        """Extensión 2a (D-69 punto 5): `Suministro.solicitud_resolucion` apunta a esta solicitud: `resolucion_del_contrato`, el caso de uso termina y no cambia nada. Se prueba con la fábrica que carga el campo."""
        x = self.aceptada()
        resolucion_del_suministro(x.contrato, self.solicitud(x))
        datos = self.datos_anul(x)
        self.assertEqual(datos.bloqueo[0], "resolucion_del_contrato")
        self.assertIn(x.contrato.codigo, datos.texto_del_bloqueo)
        error = self.rechazo(solicitudes.anular_resolucion, self.gerente, x.solicitud.pk, MOTIVO, datos.huella)
        self.assertEqual(codigos(error), ["resolucion_del_contrato"])
        self.assertEqual((self.solicitud(x).estado_solicitud, Anulacion.objects.count(), self.contrato(x).cantidad_incumplimientos), ("aceptada", 0, 1))

    def test_ext_2a_otra_solicitud_aceptada_del_contrato_si_se_puede_anular(self):
        """2a es de la solicitud que llevó el contador por encima de los tolerados: otra aceptada del mismo contrato se anula."""
        x = self.aceptada()
        y = self.otra(x)
        self.resolver(y.solicitud)
        resolucion_del_suministro(x.contrato, self.solicitud(y))
        self.assertIsNone(self.datos_anul(x).bloqueo)
        self.assertEqual(self.datos_anul(y).bloqueo[0], "resolucion_del_contrato")

    def test_ext_2b_si_la_entrega_ya_se_cobro_con_el_descuento_hay_que_anular_primero_el_cobro(self):
        """Extensión 2b (D-69 punto 8; con un cobro REAL desde COM-08a, reemplaza a la prueba con `mock.patch` de `estado_de_pago`): aceptada con descuento y la entrega cobrada ⇒ `entrega_cobrada`: «Primero anulá el cobro de OT-…»."""
        x = self.aceptada()
        cobro([x.entrega])
        datos = self.datos_anul(x)
        self.assertEqual(datos.bloqueo[0], "entrega_cobrada")
        self.assertIn(f"Primero anulá el cobro de {x.entrega.codigo}", datos.texto_del_bloqueo)
        error = self.rechazo(solicitudes.anular_resolucion, self.gerente, x.solicitud.pk, MOTIVO, datos.huella)
        self.assertEqual((codigos(error), self.solicitud(x).estado_solicitud), (["entrega_cobrada"], "aceptada"))

    def test_ext_2c_si_la_indemnizacion_ya_se_reintegro_no_se_puede_anular_parcial_ni_total(self):
        """Extensión 2c (D-69 punto 5; el reintegro total con un cobro REAL desde COM-08a, reemplaza a la prueba con `mock.patch`): `monto_reintegrado > 0` ⇒ `indemnizacion_reintegrada` («ya se le reintegró al cliente»): con reintegro parcial (6d) y total (6a, entrega cobrada)."""
        parcial = self.armar(por_planta="200.00")
        self.resolver(parcial.solicitud, medio="efectivo")
        datos = self.datos_anul(parcial)
        self.assertEqual(datos.bloqueo[0], "indemnizacion_reintegrada")
        self.assertIn("$ 100,00 por efectivo", datos.texto_del_bloqueo)
        total = self.armar()
        cobro([total.entrega])
        self.resolver(total.solicitud, medio="transferencia")
        self.assertEqual(self.datos_anul(total).bloqueo[0], "indemnizacion_reintegrada")  # descontado 0: no es 2b
        error = self.rechazo(solicitudes.anular_resolucion, self.gerente, total.solicitud.pk, MOTIVO, self.datos_anul(total).huella)
        self.assertEqual(codigos(error), ["indemnizacion_reintegrada"])
        self.assertEqual((self.solicitud(total).estado_solicitud, Anulacion.objects.count()), ("aceptada", 0))

    def test_ext_2d_una_rechazada_vuelve_a_pendiente_sin_tocar_el_contador_ni_el_monto_a_cobrar(self):
        """Extensión 2d y regla «Solicitud rechazada»: vuelve a «pendiente» sin contraasiento, sin tocar el contador ni el monto a cobrar y sin evento de bitácora; la copia lleva el estado «rechazada»."""
        x = self.armar()
        self.resolver(x.solicitud, "rechazar", "No corresponde.")
        datos = self.datos_anul(x)
        self.assertEqual((datos.aceptada, datos.contador_antes, datos.contador_despues, datos.monto_a_cobrar_antes, datos.monto_a_cobrar_despues, datos.bloqueo), (False, 0, 0, D("500.00"), D("500.00"), None))
        a = self.anular(x)
        self.assertEqual((a.estado_anulado, a.observaciones_anuladas, a.monto_indemnizacion_anulado, a.medio_reintegro_anulado), ("rechazada", "No corresponde.", None, None))
        self.assertEqual((self.solicitud(x).estado_solicitud, self.contrato(x).cantidad_incumplimientos), ("pendiente", 0))
        self.assertEqual(Bitacora.objects.filter(tipo_evento="anulacion_de_resolucion").count(), 0)

    # ---- motivo, concurrencia lógica y reglas ----

    def test_ext_3a_el_motivo_es_obligatorio_y_de_hasta_500(self):
        """Extensión 3a: motivo vacío (o solo espacios) ⇒ `motivo_obligatorio`; más de 500 ⇒ `motivo_largo`; en el campo `motivo` y sin registrar nada."""
        x = self.aceptada()
        huella = self.datos_anul(x).huella
        for motivo, codigo in (("", "motivo_obligatorio"), ("   ", "motivo_obligatorio"), ("x" * 501, "motivo_largo")):
            with self.subTest(codigo=codigo):
                error = self.rechazo(solicitudes.anular_resolucion, self.gerente, x.solicitud.pk, motivo, huella)
                self.assertEqual((codigos(error), list(error.error_dict)), ([codigo], ["motivo"]))
        self.assertEqual((self.solicitud(x).estado_solicitud, Anulacion.objects.count()), ("aceptada", 0))

    def test_ext_5a_si_otra_operacion_cambio_la_solicitud_no_registra_y_dice_la_situacion_actual(self):
        """Extensión 5a: otra sesión ya la anuló (`solicitud_no_resuelta`) o cambió un dato desde el paso 2 (`solicitud_cambio`): no se registra nada."""
        x = self.aceptada()
        huella = self.datos_anul(x).huella
        poner_estado(x.contrato, "finalizado")
        error = self.rechazo(solicitudes.anular_resolucion, self.gerente, x.solicitud.pk, MOTIVO, huella)
        self.assertEqual(codigos(error), ["solicitud_cambio"])
        self.assertIn("el estado del contrato", error.error_dict["__all__"][0].params["cambios"])
        poner_estado(x.contrato, "vigente")
        self.anular(x)
        error = self.rechazo(solicitudes.anular_resolucion, self.gerente, x.solicitud.pk, MOTIVO, huella)
        self.assertEqual(codigos(error), ["solicitud_no_resuelta"])
        self.assertEqual(Anulacion.objects.count(), 1)

    def test_regla_una_pendiente_no_se_anula(self):
        """Precondición b: hay una solicitud resuelta; una pendiente da `solicitud_no_resuelta` (en el paso 2 y al registrar)."""
        x = self.armar()
        self.assertEqual(codigos(self.rechazo(solicitudes.datos_de_anulacion, self.gerente, x.solicitud.pk)), ["solicitud_no_resuelta"])
        self.assertEqual(codigos(self.rechazo(solicitudes.anular_resolucion, self.gerente, x.solicitud.pk, MOTIVO, "")), ["solicitud_no_resuelta"])

    def test_regla_el_contador_no_baja_de_cero(self):
        """Contador: baja en 1 solo si contó; nunca menos de 0 (restricción de la base): una aceptada que no sumó (datos viejos) se anula con el contador en 0."""
        x = self.armar(tipo="queja")
        q = queja_aceptada(x.entrega, "otro", monto="15.00", contar=False)  # aceptada directo, con el contador en 0
        self.assertEqual(self.contrato(x).cantidad_incumplimientos, 0)
        datos = solicitudes.datos_de_anulacion(self.gerente, q.pk)
        self.assertEqual((datos.contador_antes, datos.contador_despues), (0, 0))
        solicitudes.anular_resolucion(self.gerente, q.pk, MOTIVO, datos.huella)
        self.assertEqual((self.contrato(x).cantidad_incumplimientos, SolicitudRevision.objects.get(pk=q.pk).estado_solicitud), (0, "pendiente"))

    def test_regla_la_solicitud_se_vuelve_a_resolver_con_todas_sus_reglas(self):
        """Regla «Después»: tras anular se vuelve a resolver: el contador vuelve a subir, el monto a cobrar vuelve a bajar y la alerta (ya resuelta) no cambia ni se crea otra."""
        x = self.aceptada()
        self.anular(x)
        self.assertEqual(self.contrato(x).cantidad_incumplimientos, 0)
        resumen = self.resumen(x.solicitud)
        self.assertEqual((resumen.monto_a_cobrar_antes, resumen.monto_a_cobrar_despues), (D("500.00"), D("485.00")))
        self.resolver(x.solicitud, "aceptar", "Ahora sí.")
        self.assertEqual((self.solicitud(x).estado_solicitud, self.contrato(x).cantidad_incumplimientos), ("aceptada", 1))
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([x.entrega.pk])[x.entrega.pk], D("485.00"))
        self.assertEqual(AlertaComercial.objects.filter(solicitud_id=x.solicitud.pk).count(), 1)
        (registro,) = RegistroAuditoria.objects.filter(accion="evaluacion_discrepancia").order_by("-pk")[:1]
        self.assertNotIn("maestros.alerta", [m["modelo"] for m in registro.afectados])

    def test_regla_dos_anulaciones_sucesivas_de_la_misma_solicitud_quedan_las_dos(self):
        """Una solicitud puede anularse más de una vez (una por cada resolución): dos `Anulacion` y la ficha muestra las dos, la más reciente primero."""
        x = self.aceptada()
        self.anular(x, "Primera.")
        self.resolver(x.solicitud, "rechazar", "Segunda decisión.")
        self.anular(x, "Segunda.")
        self.assertEqual(list(Anulacion.objects.filter(solicitud_id=x.solicitud.pk).order_by("pk").values_list("motivo_anulacion", "estado_anulado")), [("Primera.", "aceptada"), ("Segunda.", "rechazada")])
        ficha = solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk)
        self.assertEqual([a.motivo_anulacion for a in ficha.historial], ["Segunda.", "Primera."])

    def test_regla_se_anula_una_queja_aceptada_con_su_monto_manual(self):
        """COM-ANL-SRV vale para quejas: una queja con $120,00 descontados vuelve a pendiente y el monto a cobrar vuelve a su valor."""
        x = self.armar(tipo="queja")
        self.resolver(x.solicitud, monto="120")
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([x.entrega.pk])[x.entrega.pk], D("380.00"))
        self.anular(x)
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([x.entrega.pk])[x.entrega.pk], D("500.00"))
        self.assertEqual((self.solicitud(x).estado_solicitud, self.contrato(x).cantidad_incumplimientos), ("pendiente", 0))

    def test_regla_solo_el_gerente_activo_anula(self):
        """Quién anula: solo el Gerente (`PermissionDenied`), también cuando la cuenta se dio de baja."""
        x = self.aceptada()
        huella = self.datos_anul(x).huella
        for actor in (self.e.vendedor, self.e.agronomo):
            with self.assertRaises(PermissionDenied):
                solicitudes.datos_de_anulacion(actor, x.solicitud.pk)
            with self.assertRaises(PermissionDenied):
                solicitudes.anular_resolucion(actor, x.solicitud.pk, MOTIVO, huella)
        with self.assertRaises(Http404):
            solicitudes.datos_de_anulacion(self.gerente, 99999999)
        Usuario.objects.filter(pk=self.gerente.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            solicitudes.anular_resolucion(self.gerente, x.solicitud.pk, MOTIVO, huella)

    def test_garantia_la_anulacion_es_atomica(self):
        """Garantías mínimas: si falla a mitad (acá, el evento de bitácora), la solicitud, el contador y el monto a cobrar quedan como estaban y no hay `Anulacion` ni auditoría."""
        x = self.aceptada()
        huella = self.datos_anul(x).huella
        with mock.patch("comercial.servicios.solicitudes.bitacora.registrar_evento_de_contrato", side_effect=RuntimeError("falló")):
            with self.assertRaises(RuntimeError):
                solicitudes.anular_resolucion(self.gerente, x.solicitud.pk, MOTIVO, huella)
        self.assertEqual((self.solicitud(x).estado_solicitud, self.contrato(x).cantidad_incumplimientos, Anulacion.objects.count()), ("aceptada", 1, 0))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="anulacion_resolucion_solicitud").count(), 0)
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([x.entrega.pk])[x.entrega.pk], D("485.00"))


class ComAnlSrvAsientoTests(BaseDeSolicitudes):
    """CON-04d · paso 3: el contraasiento de la anulación de una resolución (COM-ANL-SRV postcondición c; D-92 puntos 6 y 8; D-86; regla «Contraasiento»). Lo origina la `Anulacion` (no `contraasentar`): los movimientos del
    asiento de la indemnización con el Debe y el Haber invertidos, con la fecha de hoy (si el ejercicio del original está cerrado, va al abierto: D-102). Una rechazada no tiene asiento ni contraasiento. Solo se pueden anular las
    resoluciones cuya indemnización no se reintegró (2c), así que el original siempre es contra Deudores por Ventas."""

    def lineas(self, asiento):
        return sorted((m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.select_related("cuenta"))

    def aceptada(self, **kw):
        x = self.armar(**kw)
        self.resolver(x.solicitud)
        return x

    def anular(self, x, motivo=MOTIVO):
        datos = solicitudes.datos_de_anulacion(self.gerente, x.solicitud.pk)
        return solicitudes.anular_resolucion(self.gerente, x.solicitud.pk, motivo, datos.huella)

    def test_post_c_la_anulacion_origina_el_contraasiento_de_la_indemnizacion_con_los_movimientos_invertidos(self):
        """Postcondición c: la indemnización de $ 15,00 (Debe Indemnizaciones por Incumplimiento / Haber Deudores) se contraasienta con el Debe y el Haber invertidos, originado en la `Anulacion`, con la fecha de hoy; el original no cambia."""
        x = self.aceptada()
        original = AsientoContable.objects.get(origen_id=x.solicitud.pk)
        lineas_del_original = self.lineas(original)
        anulacion_ = self.anular(x)
        contra = AsientoContable.objects.get(origen_id=anulacion_.pk)
        self.assertEqual(self.lineas(contra), sorted([(cuentas.INDEMNIZACIONES_POR_INCUMPLIMIENTO, HABER, D("15.00")), (cuentas.DEUDORES_POR_VENTAS, DEBE, D("15.00"))]))
        self.assertEqual((contra.fecha_asiento, AsientoContable.objects.count()), (HOY, 2))
        self.assertEqual(self.lineas(AsientoContable.objects.get(pk=original.pk)), lineas_del_original)
        verificar_invariantes_contables()

    def test_regla_si_el_ejercicio_del_original_esta_cerrado_el_contraasiento_va_al_abierto_con_la_fecha_de_hoy(self):
        """Regla «Contraasiento» y D-102: el original quedó en un ejercicio que después se cerró; el contraasiento no falla y va al ejercicio abierto con la fecha de hoy. El original sigue donde estaba."""
        viejo = ejercicio_abierto(HOY - timedelta(days=60))
        x = self.aceptada()
        original = AsientoContable.objects.get(origen_id=x.solicitud.pk)
        EjercicioContable.objects.filter(pk=viejo.pk).update(estado_ejercicio=EjercicioContable.Estado.CERRADO, fecha_cierre_ejercicio=HOY - timedelta(days=3))
        abierto = ejercicio_abierto(HOY - timedelta(days=2))
        contra = AsientoContable.objects.get(origen_id=self.anular(x).pk)
        self.assertEqual((contra.ejercicio_id, contra.fecha_asiento, AsientoContable.objects.get(pk=original.pk).ejercicio_id), (abierto.pk, HOY, viejo.pk))
        verificar_invariantes_contables()

    def test_regla_solicitud_rechazada_vuelve_a_pendiente_sin_contraasiento(self):
        """Extensión 2d y regla «Solicitud rechazada»: una rechazada nunca tuvo asiento; al anularla no se crea ninguno."""
        x = self.armar()
        self.resolver(x.solicitud, decision="rechazar", observaciones="No procede.")
        self.anular(x)
        self.assertEqual((SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, AsientoContable.objects.count()), ("pendiente", 0))

    def test_regla_una_aceptada_sin_indemnizacion_se_anula_sin_contraasiento_y_sin_fallar(self):
        """H11: una queja aceptada con monto 0 no tuvo asiento; al anularla no hay nada que revertir y no falla."""
        x = self.armar(tipo="queja")
        self.resolver(x.solicitud, monto="0")
        self.assertEqual(AsientoContable.objects.count(), 0)
        self.anular(x)
        self.assertEqual((SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, AsientoContable.objects.count()), ("pendiente", 0))

    def test_regla_una_aceptada_anterior_a_con04d_sin_asiento_se_anula_sin_contraasiento(self):
        """D-92 punto 1 (sin asientos hacia atrás): una aceptación que quedó sin asiento (anterior a esta tarea) se anula igual; no hay contraasiento porque no hay original."""
        x = self.armar()
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", return_value=None):
            self.resolver(x.solicitud)
        self.anular(x)
        self.assertEqual((SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, AsientoContable.objects.count()), ("pendiente", 0))

    def test_post_f_el_registro_de_auditoria_nombra_el_contraasiento_y_no_se_audita_aparte(self):
        """Postcondición f y D-86 punto 4: el único registro `anulacion_resolucion_solicitud` nombra el contraasiento entre sus afectados y en `datos["asientos"]`."""
        x = self.aceptada()
        anulacion_ = self.anular(x)
        registro = RegistroAuditoria.objects.filter(accion="anulacion_resolucion_solicitud").get()
        contra = AsientoContable.objects.get(origen_id=anulacion_.pk)
        self.assertTrue(any(a["id"] == contra.pk and a["texto"].startswith("Asiento") for a in registro.afectados))
        self.assertEqual(len(registro.detalle["datos"]["asientos"]), 1)

    def test_garantia_si_falla_el_contraasiento_la_resolucion_sigue_aceptada(self):
        """Garantía mínima: si el contraasiento falla, la solicitud sigue «aceptada» con su contador, sin `Anulacion`, sin otro asiento y sin el registro de auditoría de la anulación."""
        x = self.aceptada()
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=RuntimeError("falla del asiento")):
            with self.assertRaises(RuntimeError):
                self.anular(x)
        self.assertEqual((SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, Suministro.objects.get(pk=x.contrato.pk).cantidad_incumplimientos), ("aceptada", 1))
        self.assertEqual((Anulacion.objects.count(), AsientoContable.objects.count(), RegistroAuditoria.objects.filter(accion="anulacion_resolucion_solicitud").count()), (0, 1, 0))

    # ---- decisión (4) del estudiante del 26/11/2026: anular una re-aceptación (el original ya se revirtió) ----

    def test_tarea_con04d_anular_reaceptacion_no_contraasienta_de_nuevo(self):
        """Decisión (4) del 26/11/2026: aceptada (asiento 1) → anulada (contraasiento 2) → vuelta a aceptar (sin asiento, aviso) → anulada otra vez. La segunda anulación NO revierte dos veces el mismo asiento: no crea otro contraasiento
        y avisa al responsable contable (el Contador) por si registró a mano la indemnización de la re-aceptación («Revertir a mano…»). La anulación en sí se hace y no falla."""
        cache.clear()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        x = self.aceptada()
        self.anular(x)
        self.resolver(x.solicitud)  # re-aceptación: sin asiento nuevo
        self.assertEqual(AsientoContable.objects.count(), 2)
        antes = len(self.avisos(contador))
        segunda = self.anular(x)
        self.assertEqual(SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, "pendiente")
        self.assertEqual((AsientoContable.objects.count(), AsientoContable.objects.filter(origen_id=segunda.pk).count()), (2, 0))
        nuevos = self.avisos(contador)[antes:]
        self.assertEqual(len(nuevos), 1)
        self.assertTrue(nuevos[0].titulo.startswith(f"Revertir a mano el asiento de {x.solicitud.codigo}"))
        self.assertEqual(self.avisos(self.gerente, "Revertir a mano"), [])
        registro = RegistroAuditoria.objects.filter(accion="anulacion_resolucion_solicitud").latest("pk")
        self.assertIn("asiento_manual_pendiente", registro.detalle["datos"])
        verificar_invariantes_contables()
