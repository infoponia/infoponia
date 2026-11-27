# Pruebas de concurrencia de COM-RSV-SUM · Resolver Suministro por Incumplimientos (COM-07b; docs/casos_de_uso/comercial/resolucion.md, «Requisitos especiales» y «Pruebas»; docs/patrones/bloqueos.md,
# «Resolver un suministro»): resolver contra concretar una cosecha del contrato, contra concretar una entrega, contra planificar una entrega, contra la pre-reserva de un período (paso 40), contra
# iniciar la ruta del transportista de una entrega del contrato, dos resoluciones del mismo contrato a la vez (una sola; la otra termina en 2a) y resolver contra anular la solicitud que lo provoca.
# Dos hilos, dos conexiones, el orden fijado con ``primera`` (la que se detiene después de registrar la auditoría y antes de confirmar). Son ``TransactionTestCase``: sin Georef de la migración (el
# cliente tiene una dirección en la localidad propia que arma `geografia_propia`). Todas terminan verificando los invariantes. Nunca un error 500: la que llega segunda espera, relee con todo
# bloqueado y recibe un código de negocio o no hace nada («si el contrato ya está “resuelto”, no actúa sobre él»).

from datetime import timedelta
from types import SimpleNamespace

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import Entrega, ReservaStock, Suministro
from comercial.servicios import concrecion, entregas, pre_reserva, resoluciones, rutas, solicitudes
from comercial.servicios.concrecion import DatosDeConcrecion
from comercial.servicios.cosechas import DatosDeConcrecion as DatosDeConcrecionDeCosecha
from comercial.tests.fabricas import (
    cosecha_manual,
    detalle_suministro,
    direccion_de_cliente,
    entrega,
    escenario_comercial,
    marcar_concretada,
    periodo,
    queja_aceptada,
    reserva_lista,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_resolucion,
    verificar_invariantes_de_solicitudes,
)
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador, Notificacion, RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez
from core.tests.fabricas import crear_cuenta, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Localidad
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Cosecha
from produccion.tests.fabricas import lote_maduro, separar
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HOY = timezone.localdate()


@tag("concurrencia")
class ResolucionConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self):
        """Un invernadero con un transportista, un lote de 500, un Gerente, y un suministro «vigente» con 3 tolerados y 4 incumplimientos (4 quejas aceptadas de entregas ya concretadas, con su reserva
        «entregada»). Sus períodos: -40, -33, -26, -19, -12, -5, +2, +9, +16… Devuelve un `SimpleNamespace(contrato, detalle, quejas)`."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # CON-04c: concretar una entrega o registrar una merma asienta; el flush vació el plan
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento; el flush de esta TransactionTestCase lo vacía en cada prueba
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 500)
        self.gerente = crear_gerente()
        self.direccion = direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk).direccion
        self.t = transportista_con_vehiculo(self.e.invernadero, "800")
        for verificar in (verificar_invariantes_de_reservas, verificar_invariantes_de_entregas, verificar_invariantes_de_solicitudes, verificar_invariantes_de_resolucion):
            self.addCleanup(verificar)
        contrato = suministro(self.e, tolerados=3, multa="50000.00", plazo_pago=15)
        d = detalle_suministro(contrato, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=-40, minima=10, direccion=self.direccion)
        quejas = []
        for i in range(4):
            fecha = HOY - timedelta(days=40 - 7 * i)
            r = reserva_lista(None, self.lote, 5, fecha_entrega=fecha, detalle_suministro=d)
            concretada = marcar_concretada(entrega(contrato, [r], fecha=fecha), cantidades=[(5, 0, 0)])
            ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="entregada")
            quejas.append(queja_aceptada(concretada, "otro", monto="0.00"))
        return SimpleNamespace(contrato=contrato, detalle=d, quejas=quejas)

    def resolver(self, x):
        return lambda: resoluciones.resolver_suministro(x.contrato.pk, HOY)

    def estado(self, x):
        return Suministro.objects.get(pk=x.contrato.pk).estado_suministro

    def pendientes(self, x):
        """Lo que no puede quedar de un contrato resuelto: reservas «activa» o «lista para entrega», cosechas y entregas «a realizar»."""
        return (
            ReservaStock.objects.filter(detalle_suministro__suministro=x.contrato, estado_reserva__in=["activa", "lista_para_entrega"]).count(),
            Cosecha.objects.filter(estado_orden="a_realizar", reserva__detalle_suministro__suministro=x.contrato).count(),
            Entrega.objects.filter(estado_orden="a_realizar", contrato_entrega_id=x.contrato.pk).count(),
        )

    # ---- contra concretar una cosecha del contrato ----

    def con_cosecha(self):
        x = self.armar()
        x.cosecha = cosecha_manual(self.e, [(self.lote, 30)], periodo_=periodo(x.detalle, HOY + timedelta(days=9)), dias=5)
        return x

    def concretar_cosecha(self, x):
        from comercial.servicios import cosechas

        datos = DatosDeConcrecionDeCosecha(cantidades=((self.lote.pk, self.e.sectores["maduracion"].pk, 30),))
        return lambda: cosechas.concretar_cosecha(self.e.capataz, x.cosecha.pk, datos)

    def test_regla_resolver_primero_y_la_concrecion_de_la_cosecha_recibe_orden_no_a_realizar(self):
        """La resolución cancela la cosecha; la concreción, que espera su fila, relee y recibe `orden_no_a_realizar`: el lote no se toca y no queda nada pendiente."""
        x = self.con_cosecha()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.resolver(x), self.concretar_cosecha(x), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("orden_no_a_realizar", codigos(rechazos[0]))
        self.assertEqual((self.estado(x), Cosecha.objects.get(pk=x.cosecha.pk).estado_orden), ("resuelto", "cancelada"))
        self.assertEqual(self.pendientes(x), (0, 0, 0))

    def test_regla_concretar_primero_y_la_resolucion_pasa_lo_cosechado_a_la_camara(self):
        """6a.2: con la concreción primero, la resolución relee, ve la cosecha «concretada» y su reserva «lista para entrega», y el producto cosechado ingresa a la cámara (30 plantas)."""
        x = self.con_cosecha()
        resultados = correr_a_la_vez(self.concretar_cosecha(x), self.resolver(x), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(rechazos), otros), (0, []), resultados)
        self.assertEqual((self.estado(x), Cosecha.objects.get(pk=x.cosecha.pk).estado_orden), ("resuelto", "concretada"))
        self.assertEqual(resultados["b"].partidas[0].cantidad_ingreso_cosechado, 30)
        self.assertEqual(self.pendientes(x), (0, 0, 0))

    # ---- contra concretar una entrega ----

    def con_entrega_en_ruta(self, x):
        """Una entrega «a realizar» de hoy (período -5, atrasado) con el transportista, y su ruta iniciada. Devuelve la entrega."""
        r = reserva_lista(None, self.lote, 30, fecha_entrega=HOY - timedelta(days=5), detalle_suministro=x.detalle)
        e = entrega(x.contrato, [r], transportista=self.t, fecha=HOY)
        rutas.iniciar_ruta(self.t, rutas.ruta_del_dia(self.t).huella)
        return e

    def concretar_entrega(self, e):
        datos = DatosDeConcrecion(sin_envases=True)
        huella = concrecion.resumen_de_concrecion(self.t, e.pk, datos).huella
        return lambda: concrecion.concretar_entrega(self.t, e.pk, datos, huella)

    def test_regla_resolver_primero_y_la_concrecion_de_la_entrega_se_rechaza(self):
        """La resolución cancela la entrega (también la que está en viaje); la concreción, que espera el invernadero, relee y se rechaza: no queda concretada ni cobrada."""
        x = self.armar()
        e = self.con_entrega_en_ruta(x)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.resolver(x), self.concretar_entrega(e), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertTrue({"entrega_no_concretable", "cambio_simultaneo", "entrega_no_a_realizar"} & set(codigos(rechazos[0])), codigos(rechazos[0]))
        self.assertEqual((self.estado(x), Entrega.objects.get(pk=e.pk).estado_orden), ("resuelto", "cancelada"))
        self.assertEqual(self.pendientes(x), (0, 0, 0))

    def test_regla_concretar_primero_y_la_resolucion_conserva_la_entrega_concretada(self):
        """Con la concreción primero, la entrega queda «concretada» (con su deuda) y la resolución, que relee, no la toca: lo ya entregado se conserva."""
        x = self.armar()
        e = self.con_entrega_en_ruta(x)
        resultados = correr_a_la_vez(self.concretar_entrega(e), self.resolver(x), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(rechazos), otros), (0, []), resultados)
        actual = Entrega.objects.get(pk=e.pk)
        self.assertEqual((actual.estado_orden, self.estado(x)), ("concretada", "resuelto"))
        self.assertIsNotNone(actual.monto_total_entrega)

    # ---- contra planificar una entrega ----

    def test_regla_resolver_primero_y_la_planificacion_no_encuentra_nada_que_hacer(self):
        """La planificación (la del `on_commit` y la del paso 50 son la misma función) espera el invernadero y relee: el suministro ya no está «vigente», así que no crea ninguna entrega."""
        x = self.armar()
        fecha = HOY + timedelta(days=2)
        reserva_lista(None, self.lote, 30, fecha_entrega=fecha, detalle_suministro=x.detalle)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.resolver(x), lambda: entregas.planificar_periodo(x.detalle.pk, fecha, HOY), primera="a"))
        self.assertEqual((rechazos, otros), ([], []), (rechazos, otros))
        self.assertEqual(self.estado(x), "resuelto")
        self.assertEqual(self.pendientes(x), (0, 0, 0))

    def test_regla_la_planificacion_primero_y_la_resolucion_cancela_tambien_la_entrega_nueva(self):
        """Con la planificación primero, la entrega nace antes de que la resolución relea: aparece algo que la lectura previa no vio (6a), se repite una vez y la entrega nueva también se cancela."""
        x = self.armar()
        fecha = HOY + timedelta(days=2)
        reserva_lista(None, self.lote, 30, fecha_entrega=fecha, detalle_suministro=x.detalle)
        resultados = correr_a_la_vez(lambda: entregas.planificar_periodo(x.detalle.pk, fecha, HOY), self.resolver(x), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        self.assertEqual(self.estado(x), "resuelto")
        self.assertEqual(self.pendientes(x), (0, 0, 0))
        self.assertEqual(Entrega.objects.filter(contrato_entrega_id=x.contrato.pk, estado_orden="cancelada").count(), 1)  # la que nació de la planificación: no pasó en vacío

    # ---- contra la pre-reserva (paso 40) de un período ----

    def test_regla_resolver_primero_y_la_pre_reserva_no_reserva_nada_para_el_contrato_resuelto(self):
        """Con la resolución primero, la pre-reserva del período espera el invernadero y relee: el detalle ya no está «vigente» y no crea reserva ni cosecha."""
        x = self.armar()
        fecha = HOY + timedelta(days=9)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.resolver(x), lambda: pre_reserva._pre_reservar_periodo(x.detalle.pk, fecha), primera="a"))
        self.assertEqual((rechazos, otros), ([], []), (rechazos, otros))
        self.assertEqual(self.estado(x), "resuelto")
        self.assertEqual(self.pendientes(x), (0, 0, 0))
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=x.detalle, fecha_entrega_reserva=fecha).count(), 0)

    def test_regla_la_pre_reserva_primero_y_la_resolucion_libera_la_reserva_nueva(self):
        """Con la pre-reserva primero, la reserva y la cosecha nuevas existen cuando la resolución relee: se repite lo que haga falta y nada queda apartado para el contrato resuelto."""
        x = self.armar()
        fecha = HOY + timedelta(days=9)
        resultados = correr_a_la_vez(lambda: pre_reserva._pre_reservar_periodo(x.detalle.pk, fecha), self.resolver(x), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        self.assertEqual(self.estado(x), "resuelto")
        self.assertEqual(self.pendientes(x), (0, 0, 0))
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=x.detalle, fecha_entrega_reserva=fecha, estado_reserva="liberada").count(), 1)  # la que nació de la pre-reserva

    # ---- contra iniciar la ruta del transportista ----

    def con_entrega_sin_ruta(self, x):
        r = reserva_lista(None, self.lote, 30, fecha_entrega=HOY - timedelta(days=5), detalle_suministro=x.detalle)
        return entrega(x.contrato, [r], transportista=self.t, fecha=HOY)

    def test_regla_resolver_primero_y_el_inicio_de_ruta_ve_que_la_entrega_ya_no_esta(self):
        """Con la resolución primero, la entrega queda cancelada y el inicio de ruta, que espera el invernadero, relee: su ruta cambió (`ruta_cambio`) o ya no tiene entregas (`sin_entregas_de_ruta`); no inicia nada."""
        x = self.armar()
        e = self.con_entrega_sin_ruta(x)
        huella = rutas.ruta_del_dia(self.t).huella
        exitos, rechazos, otros = separar(correr_a_la_vez(self.resolver(x), lambda: rutas.iniciar_ruta(self.t, huella), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertTrue({"ruta_cambio", "sin_entregas_de_ruta"} & set(codigos(rechazos[0])), codigos(rechazos[0]))
        self.assertEqual((self.estado(x), Entrega.objects.get(pk=e.pk).estado_orden), ("resuelto", "cancelada"))

    def test_regla_iniciar_la_ruta_primero_y_la_resolucion_cancela_la_entrega_en_curso_y_avisa_al_transportista(self):
        """Con el inicio de ruta primero, la entrega ya está en curso (3c): la resolución la cancela igual y el Transportista recibe «No la entregues…»."""
        x = self.armar()
        e = self.con_entrega_sin_ruta(x)
        huella = rutas.ruta_del_dia(self.t).huella
        resultados = correr_a_la_vez(lambda: rutas.iniciar_ruta(self.t, huella), self.resolver(x), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        self.assertEqual((self.estado(x), Entrega.objects.get(pk=e.pk).estado_orden), ("resuelto", "cancelada"))
        aviso = Notificacion.objects.get(destinatario=self.t, titulo=f"Se canceló la entrega {e.codigo}")
        self.assertIn("No la entregues", aviso.detalle)

    # ---- dos resoluciones a la vez ----

    def test_regla_dos_resoluciones_del_mismo_contrato_una_sola_y_la_otra_termina_en_2a(self):
        """Requisito especial: el contrato se resuelve una única vez. La segunda espera el suministro, relee y ve el contrato «resuelto» (2a): devuelve `None`, no cambia nada y no deja otro registro."""
        x = self.armar()
        r = reserva_lista(None, self.lote, 30, fecha_entrega=HOY + timedelta(days=2), detalle_suministro=x.detalle)
        e = entrega(x.contrato, [r])
        resultados = correr_a_la_vez(self.resolver(x), self.resolver(x), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        self.assertEqual(sorted(resultado is None for resultado in resultados.values()), [False, True])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="resolucion_suministro").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="resolucion_suministro_descartada").count(), 0)
        self.assertEqual((self.estado(x), Entrega.objects.get(pk=e.pk).estado_orden), ("resuelto", "cancelada"))

    # ---- contra anular la solicitud que lo provoca ----

    def anular(self, x):
        solicitud = x.quejas[-1]
        huella = solicitudes.datos_de_anulacion(self.gerente, solicitud.pk).huella
        return lambda: solicitudes.anular_resolucion(self.gerente, solicitud.pk, "Me equivoqué al decidir.", huella)

    def test_regla_anular_primero_y_la_resolucion_ve_que_ya_no_supera_los_tolerados(self):
        """Con la anulación primero, el contador baja a 3 (los tolerados): la resolución, que espera el suministro, relee (2b), no cambia nada y deja el disparo descartado. El contrato sigue «vigente»."""
        x = self.armar()
        resultados = correr_a_la_vez(self.anular(x), self.resolver(x), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        contrato = Suministro.objects.get(pk=x.contrato.pk)
        self.assertEqual((contrato.estado_suministro, contrato.cantidad_incumplimientos, contrato.solicitud_resolucion_id), ("vigente", 3, None))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="resolucion_suministro_descartada").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="resolucion_suministro").count(), 0)

    def test_regla_resolver_primero_y_la_anulacion_se_rechaza_porque_esa_aceptacion_resolvio_el_contrato(self):
        """Con la resolución primero, `solicitud_resolucion` apunta a la solicitud: la anulación, que espera el suministro, se rechaza (2a de COM-ANL-SRV: `resolucion_del_contrato`, o `solicitud_cambio` si la huella cambió antes) y el contador no baja."""
        x = self.armar()
        resultados = correr_a_la_vez(self.resolver(x), self.anular(x), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertTrue({"resolucion_del_contrato", "solicitud_cambio"} & set(codigos(rechazos[0])), codigos(rechazos[0]))
        contrato = Suministro.objects.get(pk=x.contrato.pk)
        self.assertEqual((contrato.estado_suministro, contrato.cantidad_incumplimientos, contrato.solicitud_resolucion_id), ("resuelto", 4, x.quejas[-1].pk))

    # ---- CON-04d · paso 4: el asiento de la multa y el ejercicio (D-86 punto 2; D-102) ----

    def _cierre_y_resolucion(self, primera_la_resolucion):
        self.armar_con_ejercicios()
        resolucion, cierre = self.resolver(self.x), lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)  # noqa: E731
        resultados = correr_a_la_vez(*((resolucion, cierre) if primera_la_resolucion else (cierre, resolucion)), primera="a")
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        asiento = AsientoContable.objects.get(origen_id=self.x.contrato.pk)
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento, asiento.fecha_asiento), (self.abierto.pk, 1, HOY))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        verificar_invariantes_contables()

    def armar_con_ejercicios(self):
        """El ejercicio en cierre cubre desde hace 400 días hasta hace unos 36; el abierto empieza hace 20 días y contiene a hoy."""
        self.x = self.armar()
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, HOY - timedelta(days=400))
        self.abierto = ejercicio_abierto(HOY - timedelta(days=20))

    def test_d102_el_cierre_primero_y_la_resolucion_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """El cierre tiene su fila tomada; la resolución de hoy no la necesita."""
        self._cierre_y_resolucion(primera_la_resolucion=False)

    def test_d102_la_resolucion_primero_y_el_cierre_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """La resolución ya asentó y tiene el ejercicio abierto bloqueado; el cierre toca solo su fila."""
        self._cierre_y_resolucion(primera_la_resolucion=True)

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_la_resolucion_bloquea(self):
        """La resolución se detiene justo ANTES de bloquear el ejercicio (con el invernadero, el suministro y lo que cancela ya tomados); un cierre del ejercicio en cierre, que toca solo su fila, termina sin esperarla y la
        resolución, al seguir, asienta en el abierto con el N.º 1: nadie queda esperando una fila que el otro tiene."""
        self.armar_con_ejercicios()
        resultados = correr_a_la_vez(self.resolver(self.x), lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk), primera="a", detener_antes_de=(servicio_de_asientos, "_bloquear_ejercicio"))
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual(AsientoContable.objects.get(origen_id=self.x.contrato.pk).numero_asiento, 1)
