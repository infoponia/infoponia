# Pruebas de COM-CNS-SRV · Consultar Solicitudes de Revisión (COM-07a, paso 4): `solicitudes.lista_de_solicitudes`, `ficha_de_solicitud`, `pendientes_para`, `solicitudes_del_suministro` y `reenviar_aviso`. Una por regla
# (1 a 7; la 6 como D-69 punto 16: la pestaña busca por número), el orden, los filtros, el alcance del Vendedor y que no haya consultas por fila. COM-CNS-SRV numera sus reglas (`test_regla_3_…`).
# Fuente: docs/casos_de_uso/comercial/solicitudes.md («COM-CNS-SRV», «La lista», «La ficha»), D-28 (alcance), D-69 punto 16 y 17.
#
# Contrato de código que fijan estas pruebas: `FiltrosDeSolicitudes.desde_get(get)`; `lista_de_solicitudes(actor, filtros, pagina) -> PaginaDeSolicitudes(pagina, filas, filtros, pendientes)` con filas
# `FilaDeSolicitud`; `ficha_de_solicitud(actor, solicitud_id) -> FichaDeSolicitud` (`puede_evaluar`, `puede_anular`, `puede_reenviar`, `puede_imprimir`, `vista_previa`, `historial`, `intentos`).

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from comercial.models import SolicitudRevision, Suministro
from comercial.servicios import solicitudes
from comercial.servicios.solicitudes import FiltrosDeSolicitudes
from comercial.tests.base_solicitudes import BaseDeSolicitudes, HOY, codigos
from core.models import Usuario
from maestros.tests.fabricas import crear_vendedor

D = Decimal


class ComCnsSrvServicioTests(BaseDeSolicitudes):
    def lista(self, actor=None, **filtros):
        return solicitudes.lista_de_solicitudes(actor or self.gerente, FiltrosDeSolicitudes(**filtros))

    def codigos_de(self, pagina):
        return [f.codigo for f in pagina.filas]

    def fecha(self, x, dias_atras):
        SolicitudRevision.objects.filter(pk=x.solicitud.pk).update(fecha_solicitud=HOY - timedelta(days=dias_atras))

    # ---- regla 1: el alcance ----

    def test_regla_1_el_gerente_ve_todas_y_el_vendedor_solo_las_de_sus_contratos(self):
        """Regla 1: el Gerente ve todas las solicitudes, pendientes y resueltas; el Vendedor, las de los contratos de los que es Vendedor (D-28), en modo lectura."""
        mia, ajena = self.armar(), self.armar(tipo="queja")
        otro = crear_vendedor(email="otro@infoponia.com")
        Suministro.objects.filter(pk=ajena.contrato.pk).update(vendedor=otro)
        self.resolver(mia.solicitud, "rechazar", "No.")
        self.assertEqual(sorted(self.codigos_de(self.lista())), sorted([mia.solicitud.codigo, ajena.solicitud.codigo]))
        self.assertEqual(self.codigos_de(self.lista(self.e.vendedor)), [mia.solicitud.codigo])
        self.assertEqual(self.codigos_de(self.lista(otro)), [ajena.solicitud.codigo])

    def test_regla_1_los_demas_roles_y_las_cuentas_inactivas_no_consultan(self):
        """Precondición a: solo un Gerente o un Vendedor con la cuenta activa; el Agrónomo, el Capataz y un Vendedor dado de baja reciben `PermissionDenied`."""
        x = self.armar()
        for actor in (self.e.agronomo, self.e.capataz):
            with self.assertRaises(PermissionDenied):
                self.lista(actor)
            with self.assertRaises(PermissionDenied):
                solicitudes.ficha_de_solicitud(actor, x.solicitud.pk)
        Usuario.objects.filter(pk=self.e.vendedor.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.lista(self.e.vendedor)

    def test_regla_1_el_vendedor_no_abre_la_ficha_de_una_solicitud_ajena(self):
        """Regla 1: la ficha de una solicitud de un contrato que no es suyo es `PermissionDenied` (y una que no existe, `Http404`)."""
        x = self.armar()
        otro = crear_vendedor(email="otro@infoponia.com")
        with self.assertRaises(PermissionDenied):
            solicitudes.ficha_de_solicitud(otro, x.solicitud.pk)
        with self.assertRaises(Http404):
            solicitudes.ficha_de_solicitud(self.gerente, 99999999)

    # ---- el orden y las columnas ----

    def test_paso_2_primero_las_pendientes_de_la_mas_antigua_a_la_mas_reciente_y_despues_las_resueltas(self):
        """Paso 2 de COM-EVL-DSC y COM-RSV-QJA («tablas siempre ordenadas»): pendientes de la más antigua a la más reciente; después las resueltas, de la resolución más reciente a la más antigua."""
        vieja, nueva, r1, r2 = self.armar(), self.armar(tipo="queja"), self.armar(), self.armar(tipo="queja")
        self.fecha(vieja, 10)
        self.fecha(nueva, 2)
        self.resolver(r1.solicitud)
        self.resolver(r2.solicitud, "rechazar", "No.")
        SolicitudRevision.objects.filter(pk=r1.solicitud.pk).update(fecha_resolucion=HOY - timedelta(days=3))
        self.assertEqual(
            self.codigos_de(self.lista()), [vieja.solicitud.codigo, nueva.solicitud.codigo, r2.solicitud.codigo, r1.solicitud.codigo]
        )

    def test_regla_3_la_fila_trae_tipo_entrega_contrato_cliente_fechas_cantidad_e_indemnizacion(self):
        """Columnas del prototipo (`tabSolicitudes`) y del paso 2: solicitud, tipo, entrega y contrato con el cliente, fechas, cantidad de líneas o detalles, indemnización (solo si está aceptada) y estado."""
        d, q = self.armar(dos_lineas=True), self.armar(tipo="queja", queja_tipo="retraso", entregada=10, retraso=2)
        self.resolver(d.solicitud)
        por_codigo = {f.codigo: f for f in self.lista().filas}
        fila = por_codigo[d.solicitud.codigo]
        self.assertEqual(
            (fila.tipo_texto, fila.entrega_codigo, fila.contrato_codigo, fila.cliente, fila.fecha_solicitud, fila.fecha_entrega, fila.cantidad, fila.indemnizacion, fila.estado, fila.estado_texto, fila.pendiente),
            ("Discrepancia de cantidad", d.entrega.codigo, d.contrato.codigo, self.e.cliente.nombre_visible, HOY, HOY, 2, D("30.00"), "aceptada", "Aceptada", False),
        )
        pendiente = por_codigo[q.solicitud.codigo]
        self.assertEqual((pendiente.tipo_texto, pendiente.cantidad, pendiente.indemnizacion, pendiente.pendiente), ("Queja · retraso", 1, None, True))

    # ---- regla 2: los filtros ----

    def test_regla_2_filtra_por_tipo_y_por_estado(self):
        """Regla 2: tipo (queja o discrepancia) y estado (pendiente, resueltas, aceptadas o rechazadas; las dos últimas son «resuelta» separada)."""
        d, q, r = self.armar(), self.armar(tipo="queja"), self.armar(tipo="queja")
        self.resolver(q.solicitud)
        self.resolver(r.solicitud, "rechazar", "No.")
        self.assertEqual(self.codigos_de(self.lista(tipo="discrepancia")), [d.solicitud.codigo])
        self.assertEqual(sorted(self.codigos_de(self.lista(tipo="queja"))), sorted([q.solicitud.codigo, r.solicitud.codigo]))
        self.assertEqual(self.codigos_de(self.lista(estado="pendiente")), [d.solicitud.codigo])
        self.assertEqual(sorted(self.codigos_de(self.lista(estado="resueltas"))), sorted([q.solicitud.codigo, r.solicitud.codigo]))
        self.assertEqual(self.codigos_de(self.lista(estado="aceptada")), [q.solicitud.codigo])
        self.assertEqual(self.codigos_de(self.lista(estado="rechazada")), [r.solicitud.codigo])

    def test_regla_2_filtra_por_cliente_contrato_fechas_y_vendedor(self):
        """Regla 2: cliente (texto), contrato (número, con o sin el prefijo), rango de fechas de la solicitud y, solo para el Gerente, Vendedor."""
        a, b = self.armar(), self.armar()
        otro = crear_vendedor(email="otro@infoponia.com")
        Suministro.objects.filter(pk=b.contrato.pk).update(vendedor=otro)
        self.fecha(b, 20)
        self.assertEqual(len(self.lista(cliente=self.e.cliente.nombre_visible[:4]).filas), 2)
        self.assertEqual(self.lista(cliente="zzzz-no-existe").filas, [])
        self.assertEqual(self.codigos_de(self.lista(contrato=a.contrato.codigo)), [a.solicitud.codigo])
        self.assertEqual(self.codigos_de(self.lista(contrato=str(b.contrato.numero))), [b.solicitud.codigo])
        self.assertEqual(self.codigos_de(self.lista(desde=HOY - timedelta(days=5))), [a.solicitud.codigo])
        self.assertEqual(self.codigos_de(self.lista(hasta=HOY - timedelta(days=5))), [b.solicitud.codigo])
        self.assertEqual(self.codigos_de(self.lista(vendedor=str(otro.pk))), [b.solicitud.codigo])
        self.assertEqual(len(self.lista(self.e.vendedor, vendedor=str(otro.pk)).filas), 1)  # el Vendedor no filtra por Vendedor: ve solo lo suyo

    def test_regla_6_la_pestana_busca_por_el_numero_de_la_solicitud(self):
        """Regla 6 con D-69 punto 16: las notificaciones nombran la solicitud (`SR-0012`) y la pestaña la busca por número, con el prefijo o sin él."""
        a, b = self.armar(), self.armar()
        self.assertEqual(self.codigos_de(self.lista(numero=a.solicitud.codigo)), [a.solicitud.codigo])
        self.assertEqual(self.codigos_de(self.lista(numero=str(b.solicitud.numero))), [b.solicitud.codigo])
        self.assertEqual(self.codigos_de(self.lista(numero=a.solicitud.codigo.lower())), [a.solicitud.codigo])
        self.assertEqual(len(self.lista(numero="sin-numero").filas), 2)  # sin dígitos no filtra

    def test_regla_2_los_filtros_se_leen_de_la_url(self):
        """`FiltrosDeSolicitudes.desde_get`: los parámetros de la URL, con fechas ISO inválidas ignoradas; `hay_filtros` dice si hay alguno."""
        f = FiltrosDeSolicitudes.desde_get({"tipo": "queja", "estado": "pendiente", "desde": "2026-11-01", "hasta": "no-es-fecha", "numero": "SR-0012"})
        self.assertEqual((f.tipo, f.estado, f.desde.isoformat(), f.hasta, f.numero), ("queja", "pendiente", "2026-11-01", None, "SR-0012"))
        self.assertTrue(f.hay_filtros)
        self.assertFalse(FiltrosDeSolicitudes.desde_get({}).hay_filtros)

    def test_regla_la_lista_no_hace_consultas_por_fila(self):
        """Una consulta por tabla para toda la página: con una fila y con ocho filas las consultas son las mismas."""
        self.armar()
        with CaptureQueriesContext(connection) as una:
            solicitudes.lista_de_solicitudes(self.gerente, FiltrosDeSolicitudes())
        for i in range(7):
            self.armar(tipo="queja" if i % 2 else "discrepancia")
        with CaptureQueriesContext(connection) as ocho:
            pagina = solicitudes.lista_de_solicitudes(self.gerente, FiltrosDeSolicitudes())
        self.assertEqual((len(pagina.filas), len(una), len(ocho)), (8, len(una), len(una)))

    def test_regla_el_contador_de_la_pestana_es_solo_del_gerente(self):
        """«Contador de la pestaña»: las pendientes, solo para el Gerente activo (`None` para el Vendedor y para una cuenta inactiva)."""
        a, b = self.armar(), self.armar()
        self.assertEqual((solicitudes.pendientes_para(self.gerente), solicitudes.pendientes_para(self.e.vendedor)), (2, None))
        self.resolver(a.solicitud)
        self.assertEqual(solicitudes.pendientes_para(self.gerente), 1)
        self.assertEqual(self.lista().pendientes, 1)
        Usuario.objects.filter(pk=self.gerente.pk).update(is_active=False)
        self.gerente.refresh_from_db()
        self.assertIsNone(solicitudes.pendientes_para(self.gerente))

    # ---- la ficha: reglas 3 a 5 y 7 ----

    def test_regla_3_la_ficha_trae_la_entrega_las_cantidades_el_monto_y_el_estado_de_pago(self):
        """Regla 3: la entrega y el detalle afectados; las cantidades pactada (mínimo), planificada, entregada, perdida y devuelta; el monto de la indemnización; el estado de pago y el monto a cobrar de la entrega."""
        x = self.armar()
        ficha = solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk)
        l = ficha.lectura
        self.assertEqual((ficha.codigo, ficha.tipo_texto), (x.solicitud.codigo, "Discrepancia de cantidad"))
        (linea,) = l.lineas
        self.assertEqual((linea.minima, linea.planificada, linea.entregada, linea.perdida, linea.devuelta, linea.por_planta, linea.monto), (8, 10, 5, 5, 0, D("5.00"), D("15.00")))
        self.assertEqual((l.calculado, l.monto_a_cobrar, l.estado_de_pago, l.entrega.pk, l.suministro.pk), (D("15.00"), D("500.00"), "pendiente", x.entrega.pk, x.contrato.pk))

    def test_regla_3_una_queja_por_estado_trae_su_tope_y_una_por_retraso_los_dias(self):
        """Regla 3 y 4a: la queja sin cláusula muestra el tope (lo que el cliente paga por sus detalles); la de retraso, los días, el plazo y la indemnización por día."""
        e = self.armar(tipo="queja")
        self.assertEqual((solicitudes.ficha_de_solicitud(self.gerente, e.solicitud.pk).lectura.tope, solicitudes.ficha_de_solicitud(self.gerente, e.solicitud.pk).lectura.es_manual), (D("500.00"), True))
        r = self.armar(tipo="queja", queja_tipo="retraso", entregada=10, retraso=4, plazo_entrega=1, por_dia="12.50")
        lectura = solicitudes.ficha_de_solicitud(self.gerente, r.solicitud.pk).lectura
        (linea,) = lectura.lineas
        self.assertEqual((linea.dias, linea.plazo, linea.por_dia, linea.monto, lectura.calculado, lectura.tope), (4, 1, D("12.50"), D("50.00"), D("50.00"), None))

    def test_regla_4_una_pendiente_le_dice_al_vendedor_que_la_evalua_el_gerente(self):
        """Regla 4: el Vendedor ve las pendientes en solo lectura (`puede_evaluar` falso, sin vista previa del panel); el Gerente puede evaluarla (regla 7) y no anularla."""
        x = self.armar()
        v = solicitudes.ficha_de_solicitud(self.e.vendedor, x.solicitud.pk)
        self.assertEqual((v.puede_evaluar, v.puede_anular, v.vista_previa, v.es_gerente), (False, False, None, False))
        g = solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk)
        self.assertEqual((g.puede_evaluar, g.puede_anular, g.es_gerente), (True, False, True))
        self.assertEqual((g.vista_previa.monto, g.vista_previa.incumplimientos_antes, g.vista_previa.incumplimientos_despues, g.vista_previa.resolveria), (D("15.00"), 0, 1, False))

    def test_regla_5_una_resuelta_trae_la_decision_el_gerente_la_fecha_las_observaciones_y_el_descuento(self):
        """Regla 5: además, la decisión, el Gerente que la tomó, la fecha de resolución, las observaciones y cómo quedó el monto a cobrar (MD-115); «Cuenta como incumplimiento» si está aceptada."""
        x = self.armar(por_planta="200.00")
        self.resolver(x.solicitud, observaciones="Procede.", medio="efectivo")
        ficha = solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk)
        s = ficha.solicitud
        self.assertEqual((s.estado_solicitud, s.fecha_resolucion, ficha.gerente_que_resolvio, s.observaciones_resolucion), ("aceptada", HOY, "Gabriela Sosa", "Procede."))
        self.assertEqual((s.monto_indemnizacion, s.monto_descontado, s.monto_reintegrado, s.medio_reintegro, ficha.lectura.monto_a_cobrar), (D("600.00"), D("500.00"), D("100.00"), "efectivo", D("0.00")))
        self.assertEqual((ficha.cuenta_como_incumplimiento, ficha.puede_anular, ficha.puede_evaluar, ficha.vista_previa), (True, True, False, None))
        v = solicitudes.ficha_de_solicitud(self.e.vendedor, x.solicitud.pk)
        self.assertEqual((v.puede_anular, v.puede_evaluar), (False, False))

    def test_regla_5_una_rechazada_no_cuenta_como_incumplimiento(self):
        """Una rechazada muestra la decisión y las observaciones y no cuenta como incumplimiento."""
        x = self.armar()
        self.resolver(x.solicitud, "rechazar", "No corresponde.")
        ficha = solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk)
        self.assertEqual((ficha.solicitud.estado_solicitud, ficha.cuenta_como_incumplimiento, ficha.puede_anular), ("rechazada", False, True))

    def test_regla_7_con_el_contrato_vencido_o_resuelto_la_vista_previa_dice_historial(self):
        """Regla 7 y 6c: la vista previa del panel dice si la aceptación resolvería el contrato (6b) o si queda como historial (6c)."""
        x = self.armar(tolerados=0)
        self.assertTrue(solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk).vista_previa.resolveria)
        y = self.armar(tolerados=0, estado_contrato="finalizado")
        previa = solicitudes.ficha_de_solicitud(self.gerente, y.solicitud.pk).vista_previa
        self.assertEqual((previa.resolveria, previa.historial), (False, True))

    @override_settings(CORREO_CONFIGURADO=True)
    def test_regla_9a_la_ficha_ofrece_reenviar_el_aviso_pendiente_y_imprimir_si_no_hay_correo(self):
        """D-69 punto 17: con el aviso «pendiente de envío» la ficha ofrece «Reenviar aviso»; con «sin correo», «Imprimir comprobante»; con «enviado» ninguno."""
        x = self.armar()
        with self.captureOnCommitCallbacks(execute=False):
            self.resolver(x.solicitud)
        ficha = solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk)
        self.assertEqual((ficha.solicitud.estado_aviso_cliente, ficha.puede_reenviar, ficha.puede_imprimir), ("pendiente_envio", True, False))
        SolicitudRevision.objects.filter(pk=x.solicitud.pk).update(estado_aviso_cliente="enviado")
        ficha = solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk)
        self.assertEqual((ficha.puede_reenviar, ficha.puede_imprimir), (False, False))
        SolicitudRevision.objects.filter(pk=x.solicitud.pk).update(estado_aviso_cliente="sin_correo")
        self.assertTrue(solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk).puede_imprimir)

    def test_regla_9a_reenviar_el_aviso_lo_pueden_el_gerente_y_el_vendedor_del_contrato(self):
        """«Reenviar aviso»: el Gerente y el Vendedor del contrato sí; otro Vendedor, no; si el aviso no está pendiente, `aviso_no_pendiente`."""
        x = self.armar()
        with self.captureOnCommitCallbacks(execute=False):
            self.resolver(x.solicitud)
        otro = crear_vendedor(email="otro@infoponia.com")
        with self.assertRaises(PermissionDenied):
            solicitudes.reenviar_aviso(otro, x.solicitud.pk)
        with override_settings(CORREO_CONFIGURADO=True):
            self.assertTrue(solicitudes.reenviar_aviso(self.e.vendedor, x.solicitud.pk))
        self.assertEqual(codigos(self.rechazo(solicitudes.reenviar_aviso, self.gerente, x.solicitud.pk)), ["aviso_no_pendiente"])

    def test_regla_8_de_cns_sum_la_ficha_del_suministro_lista_sus_solicitudes_de_la_mas_reciente_a_la_mas_antigua(self):
        """Lo que completa a COM-03a (regla 8 de COM-CNS-SUM): número, fecha y entrega, tipo, estado y «cuenta como incumplimiento», de la más reciente a la más antigua."""
        x = self.armar()
        y = self.otra(x, tipo="queja")
        self.fecha(x, 5)
        self.resolver(x.solicitud)
        filas = solicitudes.solicitudes_del_suministro(x.contrato.pk)
        self.assertEqual([f.codigo for f in filas], [y.solicitud.codigo, x.solicitud.codigo])
        self.assertEqual(
            (filas[0].tipo_texto, filas[0].estado_texto, filas[0].cuenta_como_incumplimiento, filas[0].entrega_codigo), ("Queja · estado de la mercadería", "Pendiente de revisión", False, y.entrega.codigo)
        )
        self.assertEqual((filas[1].estado, filas[1].cuenta_como_incumplimiento), ("aceptada", True))
