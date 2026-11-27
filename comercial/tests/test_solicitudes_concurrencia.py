# Pruebas de concurrencia de las solicitudes de revisión (COM-07a, paso 7; docs/casos_de_uso/comercial/solicitudes.md, «Pruebas»; docs/patrones/bloqueos.md, «Resolver o anular una solicitud»; D-69 puntos 11 y 12): dos
# aceptaciones de solicitudes distintas del mismo contrato (una gana; la otra ve la huella cambiada y, con el resumen nuevo, el contador sube 2: ninguna pierde un incumplimiento), la misma solicitud desde dos sesiones (una
# sola), aceptar contra anular, anular contra aceptar otra solicitud del contrato, aceptar contra concretar otra entrega del mismo contrato (en fila en el invernadero y el contrato, sin interbloqueo) y dos aceptaciones de
# la misma entrega (discrepancia y queja) con el monto a cobrar justo (nunca negativo). Dos hilos, dos conexiones, el orden fijado con ``primera``.
# Son ``TransactionTestCase``: sin Georef de la migración (el cliente tiene una dirección en la localidad propia que arma `geografia_propia`). Todas terminan verificando los invariantes. Nunca un error 500: el que pierde
# espera el invernadero y el contrato, relee con todo bloqueado y se rechaza con un código (`solicitud_cambio`, `solicitud_no_pendiente` o `solicitud_no_resuelta`).

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import Entrega, SolicitudRevision, Suministro
from comercial.servicios import concrecion, rutas, solicitudes
from comercial.servicios.concrecion import DatosDeConcrecion
from comercial.servicios.solicitudes import DatosDeResolucion
from comercial.tests.fabricas import (
    detalle_suministro,
    direccion_de_cliente,
    discrepancia,
    entrega,
    escenario_comercial,
    marcar_concretada,
    queja,
    reserva_lista,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_solicitudes,
)
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador, RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez
from core.tests.fabricas import crear_cuenta, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Localidad
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.tests.fabricas import lote_maduro, separar
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HOY = timezone.localdate()
MOTIVO = "Me equivoqué."
D = Decimal


@tag("concurrencia")
class SolicitudesConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self):
        """Un invernadero con su Vendedor, un lote de 500, un Gerente, un suministro de 10 plantas por período a $100 (mínimo 8) y un cliente con una dirección en la localidad propia."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # CON-04c: concretar una entrega o registrar una merma asienta; el flush vació el plan
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento; el flush de esta TransactionTestCase lo vacía en cada prueba
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 500)
        self.gerente = crear_gerente()
        self.direccion = direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk).direccion
        self.contrato = suministro(self.e, tolerados=5, plazo_pago=15)
        self.detalle = detalle_suministro(self.contrato, self.e.variedad, direccion=self.direccion, cantidad=10, minima=8, precio="100.00", primera_en_dias=0, indemnizacion_faltante="5.00")
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)
        self.addCleanup(verificar_invariantes_contables)  # CON-04d: aceptar y anular una resolución asientan

    def concretada(self, dias, tipo="discrepancia"):
        """Una entrega concretada (5 de 10 plantas) del período `dias` días después del primero, con su solicitud pendiente. Devuelve `SimpleNamespace(entrega, solicitud)`."""
        reserva = reserva_lista(None, self.lote, 10, fecha_entrega=self.detalle.fecha_primer_entrega + timedelta(days=dias), detalle_suministro=self.detalle)
        e = marcar_concretada(entrega(self.contrato, [reserva]), cantidades=[(5, 5, 0)])
        return SimpleNamespace(entrega=e, solicitud=discrepancia(e, minima=8) if tipo == "discrepancia" else queja(e, "otro"))

    def aceptar(self, x, monto="", medio="", huella=None):
        """Una operación para `correr_a_la_vez`: acepta `x.solicitud` con la huella del resumen que el Gerente tenía a la vista (se arma antes de correr)."""
        datos = DatosDeResolucion("aceptar", "", monto, medio)
        huella = solicitudes.resumen_de_resolucion(self.gerente, x.solicitud.pk, datos).huella if huella is None else huella
        return lambda: solicitudes.resolver_solicitud(self.gerente, x.solicitud.pk, datos, huella)

    def anular(self, x, huella=None):
        huella = solicitudes.datos_de_anulacion(self.gerente, x.solicitud.pk).huella if huella is None else huella
        return lambda: solicitudes.anular_resolucion(self.gerente, x.solicitud.pk, MOTIVO, huella)

    def contador(self):
        return Suministro.objects.get(pk=self.contrato.pk).cantidad_incumplimientos

    def estado(self, x):
        return SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud

    # ---- aceptaciones del mismo contrato ----

    def test_regla_dos_aceptaciones_del_mismo_contrato_ninguna_pierde_un_incumplimiento(self):
        """Requisito especial de COM-EVL-DSC: impide que dos aceptaciones simultáneas sobre el mismo contrato pierdan un incumplimiento. La segunda espera el contrato, relee con todo bloqueado, ve el contador cambiado
        (8b: `solicitud_cambio`) y no registra; con el resumen nuevo se acepta y el contador sube a 2."""
        self.armar()
        a, b = self.concretada(0), self.concretada(7)
        resultados = correr_a_la_vez(self.aceptar(a), self.aceptar(b), primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["solicitud_cambio"])
        self.assertEqual((self.contador(), self.estado(a), self.estado(b)), (1, "aceptada", "pendiente"))
        self.aceptar(b)()  # con el resumen nuevo
        self.assertEqual((self.contador(), self.estado(b)), (2, "aceptada"))

    def test_regla_la_misma_solicitud_desde_dos_sesiones_se_resuelve_una_sola_vez(self):
        """Requisito especial: impide que una solicitud se resuelva dos veces. La segunda espera, ve que ya no está pendiente (8a: `solicitud_no_pendiente`): un solo incumplimiento, un solo registro de auditoría."""
        self.armar()
        a = self.concretada(0)
        operacion = self.aceptar(a)
        resultados = correr_a_la_vez(operacion, operacion, primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["solicitud_no_pendiente"])
        self.assertEqual((self.contador(), RegistroAuditoria.objects.filter(accion="evaluacion_discrepancia").count()), (1, 1))

    def test_regla_dos_aceptaciones_de_la_misma_entrega_dejan_el_monto_a_cobrar_justo_nunca_negativo(self):
        """Requisito especial de COM-RSV-QJA: dos aceptaciones simultáneas no dejan negativo el monto a cobrar. Una discrepancia ($15) y una queja de $500 (todo lo cobrable): la segunda ve el monto a cobrar cambiado y no
        registra; con el resumen nuevo se descuentan $485 y se reintegran $15: el monto a cobrar queda en $0."""
        self.armar()
        a = self.concretada(0)
        b = SimpleNamespace(entrega=a.entrega, solicitud=queja(a.entrega, "otro"))
        resultados = correr_a_la_vez(self.aceptar(a), self.aceptar(b, monto="500"), primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["solicitud_cambio"])
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([a.entrega.pk])[a.entrega.pk], D("485.00"))
        self.aceptar(b, monto="500", medio="efectivo")()
        s = SolicitudRevision.objects.get(pk=b.solicitud.pk)
        self.assertEqual((s.monto_descontado, s.monto_reintegrado, s.medio_reintegro), (D("485.00"), D("15.00"), "efectivo"))
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([a.entrega.pk])[a.entrega.pk], D("0.00"))
        self.assertEqual(self.contador(), 2)

    # ---- aceptar contra anular ----

    def test_regla_aceptar_y_anular_la_misma_se_ponen_en_fila_y_el_segundo_ve_lo_que_hizo_el_primero(self):
        """Aceptar contra anular la misma solicitud. Si acepta primero (queda detenida con todo tomado, sin confirmar), la anulación espera, relee y ve datos distintos de los que tenía a la vista (`solicitud_cambio`):
        solo la aceptación se registra. Si la anulación llegara primero con la solicitud todavía pendiente, falla por validación (`solicitud_no_resuelta`) antes de escribir nada: no hay carrera que simular (no llega a
        auditar, y `correr_a_la_vez` exige que la primera llegue a ese punto), así que ese orden se prueba en secuencia. Nunca interbloqueo ni error 500."""
        self.armar()
        z = self.concretada(0)
        resultados = correr_a_la_vez(self.aceptar(z), self.anular(z, huella=""), primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["solicitud_cambio"])
        self.assertEqual(self.estado(z), "aceptada")
        w = self.concretada(14)
        with self.assertRaises(ValidationError) as c:
            self.anular(w, huella="")()
        self.assertEqual(codigos(c.exception), ["solicitud_no_resuelta"])
        self.aceptar(w)()
        self.assertEqual(self.estado(w), "aceptada")

    def test_regla_dos_anulaciones_de_la_misma_solicitud_solo_se_registra_una(self):
        """Dos anulaciones simultáneas de la misma resolución: la segunda ve que ya está pendiente (`solicitud_no_resuelta`): una `Anulacion`, el contador baja una sola vez."""
        self.armar()
        a = self.concretada(0)
        self.aceptar(a)()
        operacion = self.anular(a)
        resultados = correr_a_la_vez(operacion, operacion, primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["solicitud_no_resuelta"])
        self.assertEqual((self.contador(), RegistroAuditoria.objects.filter(accion="anulacion_resolucion_solicitud").count()), (0, 1))

    def test_regla_anular_una_y_aceptar_otra_del_mismo_contrato_terminan_sin_interbloqueo(self):
        """Anular la aceptación de una solicitud mientras se acepta otra del mismo contrato: las dos toman el invernadero y después el contrato en el mismo orden; la segunda ve el contador cambiado y se rechaza
        (`solicitud_cambio`); con el resumen nuevo se acepta. El contador queda igual a las aceptadas (invariante)."""
        self.armar()
        x, y = self.concretada(0), self.concretada(7)
        self.aceptar(x)()
        resultados = correr_a_la_vez(self.anular(x), self.aceptar(y), primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["solicitud_cambio"])
        self.assertEqual((self.contador(), self.estado(x), self.estado(y)), (0, "pendiente", "pendiente"))
        self.aceptar(y)()
        self.assertEqual(self.contador(), 1)

    # ---- aceptar contra concretar otra entrega del mismo contrato ----

    def test_regla_aceptar_y_concretar_otra_entrega_del_mismo_contrato_se_ponen_en_fila_sin_interbloqueo(self):
        """Aceptar una solicitud mientras el Transportista concreta otra entrega del mismo contrato (en los dos órdenes): las dos toman el invernadero de origen y después el contrato en el mismo orden (D-69 punto 11,
        como la concreción), así que se ponen en fila y terminan las dos, sin error 500."""
        self.armar()
        for primera, periodo_aceptado, periodo_a_concretar in (("a", 7, 14), ("b", 21, 28)):
            with self.subTest(primera=primera):
                transportista = transportista_con_vehiculo(self.e.invernadero, "800")
                aceptada = self.concretada(periodo_aceptado)
                reserva = reserva_lista(None, self.lote, 10, fecha_entrega=self.detalle.fecha_primer_entrega + timedelta(days=periodo_a_concretar), detalle_suministro=self.detalle)
                otra = entrega(self.contrato, [reserva], transportista=transportista, fecha=HOY)
                rutas.iniciar_ruta(transportista, rutas.ruta_del_dia(transportista).huella)
                datos = DatosDeConcrecion(sin_envases=True)
                huella = concrecion.resumen_de_concrecion(transportista, otra.pk, datos).huella
                concretar = lambda: concrecion.concretar_entrega(transportista, otra.pk, datos, huella)
                antes = self.contador()
                resultados = correr_a_la_vez(self.aceptar(aceptada), concretar, primera=primera)
                buenos, rechazos, otros = separar(resultados)
                self.assertEqual((len(buenos), rechazos, otros), (2, [], []), (primera, resultados))
                self.assertEqual((self.estado(aceptada), Entrega.objects.get(pk=otra.pk).estado_orden), ("aceptada", "concretada"))
                self.assertEqual(self.contador(), antes + 1)

    # ---- CON-04d · paso 2: el asiento de la indemnización y el ejercicio (D-86 punto 2; D-102) ----

    def _cierre_y_aceptacion(self, primera_la_aceptacion):
        """El ejercicio en cierre cubre desde hace 400 días hasta hace unos 36; el abierto empieza hace 20 días y contiene a hoy. El cierre y la aceptación corren a la vez en el orden pedido."""
        self.armar()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, HOY - timedelta(days=400))
        abierto = ejercicio_abierto(HOY - timedelta(days=20))
        x = self.concretada(0)
        aceptacion, cierre = self.aceptar(x), lambda: ejercicios.cerrar_ejercicio(contador, en_cierre.pk)
        resultados = correr_a_la_vez(*((aceptacion, cierre) if primera_la_aceptacion else (cierre, aceptacion)), primera="a")
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        asiento = AsientoContable.objects.get(origen_id=x.solicitud.pk)
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento, asiento.fecha_asiento), (abierto.pk, 1, HOY))
        self.assertEqual(EjercicioContable.objects.get(pk=en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        verificar_invariantes_contables()

    def test_d102_el_cierre_primero_y_la_aceptacion_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """El cierre tiene su fila tomada; la aceptación de hoy no la necesita."""
        self._cierre_y_aceptacion(primera_la_aceptacion=False)

    def test_d102_la_aceptacion_primero_y_el_cierre_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """La aceptación ya asentó y tiene el ejercicio abierto bloqueado; el cierre toca solo su fila."""
        self._cierre_y_aceptacion(primera_la_aceptacion=True)

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_la_aceptacion_bloquea(self):
        """La aceptación se detiene justo ANTES de bloquear el ejercicio (con su invernadero, contrato y entrega ya tomados) y otra, de un invernadero distinto, asienta completa y toma el N.º 1: el ejercicio se bloquea al final."""
        self.armar()
        ejercicio_abierto(HOY - timedelta(days=20))
        otro = escenario_comercial(nombre="Invernadero Sur", sufijo="b", email_del_cliente="clienteb@ejemplo.com", geografia_propia=True)
        lote_b = lote_maduro(otro, 500)
        direccion_b = direccion_de_cliente(otro.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk).direccion
        contrato_b = suministro(otro, tolerados=5, plazo_pago=15)
        detalle_b = detalle_suministro(contrato_b, otro.variedad, direccion=direccion_b, cantidad=10, minima=8, precio="100.00", primera_en_dias=0, indemnizacion_faltante="5.00")
        reserva = reserva_lista(None, lote_b, 10, fecha_entrega=detalle_b.fecha_primer_entrega, detalle_suministro=detalle_b)
        entrega_b = marcar_concretada(entrega(contrato_b, [reserva]), cantidades=[(5, 5, 0)])
        solicitud_b = SimpleNamespace(entrega=entrega_b, solicitud=discrepancia(entrega_b, minima=8))
        datos = DatosDeResolucion("aceptar", "", "", "")
        huella_b = solicitudes.resumen_de_resolucion(self.gerente, solicitud_b.solicitud.pk, datos).huella
        a = self.aceptar(self.concretada(0))
        b = lambda: solicitudes.resolver_solicitud(self.gerente, solicitud_b.solicitud.pk, datos, huella_b)  # noqa: E731
        resultados = correr_a_la_vez(a, b, primera="a", detener_antes_de=(servicio_de_asientos, "_bloquear_ejercicio"))
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2])

    # ---- CON-04d · paso 3: el contraasiento de la anulación y el ejercicio (D-86 punto 2; D-102) ----

    def _cierre_y_anulacion(self, primera_la_anulacion):
        self.armar()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, HOY - timedelta(days=400))
        abierto = ejercicio_abierto(HOY - timedelta(days=20))
        x = self.concretada(0)
        self.aceptar(x)()  # la aceptación ya hecha (asiento N.º 1): el contraasiento y el cierre corren a la vez
        anulacion = self.anular(x)
        cierre = lambda: ejercicios.cerrar_ejercicio(contador, en_cierre.pk)  # noqa: E731
        resultados = correr_a_la_vez(*((anulacion, cierre) if primera_la_anulacion else (cierre, anulacion)), primera="a")
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", "ejercicio_id")), [(1, abierto.pk), (2, abierto.pk)])
        self.assertEqual(EjercicioContable.objects.get(pk=en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        verificar_invariantes_contables()

    def test_d102_el_cierre_primero_y_la_anulacion_a_la_vez_los_dos_terminan_y_el_contraasiento_va_al_abierto(self):
        """El cierre tiene su fila tomada; la anulación de hoy no la necesita."""
        self._cierre_y_anulacion(primera_la_anulacion=False)

    def test_d102_la_anulacion_primero_y_el_cierre_a_la_vez_los_dos_terminan_y_el_contraasiento_va_al_abierto(self):
        """La anulación ya contraasentó y tiene el ejercicio abierto bloqueado; el cierre toca solo su fila."""
        self._cierre_y_anulacion(primera_la_anulacion=True)
