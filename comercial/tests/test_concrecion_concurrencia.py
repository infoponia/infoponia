# Pruebas de concurrencia de la ruta y la concreción (COM-06a, paso 4; docs/casos_de_uso/comercial/rutas.md, «Pruebas»; docs/patrones/bloqueos.md, «Iniciar y finalizar la ruta» y «Concretar una
# entrega»): dos concreciones de la misma entrega (una gana; la otra, `entrega_no_concretable`), concretar contra reasignar (COM-ASG-TRP), concretar un retiro contra cambiar su envasado (la
# huella), iniciar la ruta contra planificar una entrega para el mismo transportista (5c) y el intento fallido contra concretar. Dos hilos, dos conexiones, el orden fijado con ``primera``.
# Son ``TransactionTestCase``: sin Georef de la migración (el cliente tiene una dirección en la localidad propia que arma `geografia_propia`). Todas terminan verificando los invariantes. Nunca
# un error 500: el que pierde espera el invernadero, relee con todo bloqueado y se rechaza con un código.

from datetime import timedelta
from types import SimpleNamespace

from django.core.cache import cache
from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import Entrega, PagoCliente, Vehiculo
from comercial.servicios import concrecion, entregas, envasado, rutas
from comercial.servicios.concrecion import DatosDeConcrecion
from comercial.servicios.envasado import CargaDeEnvasado
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    direccion_de_cliente,
    entrega,
    envase,
    escenario_comercial,
    reserva_lista,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador
from core.tests.concurrencia import codigos, correr_a_la_vez
from core.tests.fabricas import crear_cuenta, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Localidad
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.tests.fabricas import lote_maduro, reservar, separar

HOY = timezone.localdate()


@tag("concurrencia")
class ConcrecionConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self):
        """Un invernadero con un transportista de 800 kg, un lote de 500 y un cliente con una dirección en la localidad propia."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # CON-04c: concretar una entrega asienta; el flush de la prueba anterior vació el plan
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 500)
        self.gerente = crear_gerente()
        self.direccion = direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk).direccion
        self.t = transportista_con_vehiculo(self.e.invernadero, "800")
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)

    def entrega_lista(self, *, retiro=False, con_envasado=False, iniciar=True, cantidad=50):
        """Una entrega de hoy para concretar (con envío, del transportista, con la ruta iniciada; o un retiro). Devuelve `SimpleNamespace(entrega, venta, envases)`."""
        venta = compra_venta(self.e, dias=0, modalidad="retiro" if retiro else "envio", direccion=None if retiro else self.direccion)
        det = detalle(venta, self.e.variedad, cantidad)
        e = entrega(venta, [reserva_lista(det, self.lote, cantidad)], transportista=None if retiro else self.t, fecha=HOY)
        envases = None
        if con_envasado:
            envases = envase(self.e.invernadero, stock=30)
            reservar(e, envases, 10)
        if iniciar and not retiro:
            rutas.iniciar_ruta(self.t, rutas.ruta_del_dia(self.t).huella)
        return SimpleNamespace(entrega=e, venta=venta, envases=envases)

    def datos(self, x):
        return DatosDeConcrecion(medio_pago="efectivo", sin_envases=x.envases is None, utilizada={x.envases.pk: "10"} if x.envases else {})

    def concretar(self, x, actor, huella):
        return lambda: concrecion.concretar_entrega(actor, x.entrega.pk, self.datos(x), huella)

    def huella(self, x, actor):
        return concrecion.resumen_de_concrecion(actor, x.entrega.pk, self.datos(x)).huella

    def test_regla_dos_concreciones_de_la_misma_entrega_una_gana_y_la_otra_se_rechaza(self):
        """Requisito especial de COM-CNC-ENT: una entrega no se concreta dos veces. La segunda espera el invernadero, relee con todo bloqueado (14a) y se rechaza con `entrega_no_concretable`: un solo pago, un solo egreso."""
        self.armar()
        x = self.entrega_lista()
        huella = self.huella(x, self.t)
        resultados = correr_a_la_vez(self.concretar(x, self.t, huella), self.concretar(x, self.t, huella), primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["entrega_no_concretable"])
        self.assertEqual(PagoCliente.objects.count(), 1)
        self.assertEqual(Entrega.objects.get(pk=x.entrega.pk).estado_orden, "concretada")

    def test_regla_concretar_contra_reasignar_el_transportista_la_segunda_ve_el_resultado_de_la_primera(self):
        """Concretar contra COM-ASG-TRP (primera la concreción): la asignación espera el invernadero, relee y se rechaza (la entrega ya no está a realizar); el transportista de la entrega concretada no cambia."""
        self.armar()
        x = self.entrega_lista()
        otro = transportista_con_vehiculo(self.e.invernadero, "800")
        huella_de_asignacion = entregas.datos_de_asignacion(self.e.vendedor, x.entrega.pk).huella
        asignar = lambda: entregas.asignar_transportista(self.e.vendedor, x.entrega.pk, otro.pk, huella_de_asignacion)
        resultados = correr_a_la_vez(self.concretar(x, self.t, self.huella(x, self.t)), asignar, primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertIn(codigos(rechazos[0])[0], ("entrega_no_a_realizar", "entrega_en_curso", "entrega_cambio"))
        e = Entrega.objects.get(pk=x.entrega.pk)
        self.assertEqual((e.estado_orden, e.transportista_id), ("concretada", self.t.pk))

    def test_regla_concretar_un_retiro_contra_cambiar_su_envasado_la_huella_lo_detecta(self):
        """«Retiro en concreción»: el Agrónomo cambia el envasado de un retiro (no está «en curso») mientras el Vendedor carga los datos. Con el cambio primero, la concreción ve otra huella: `cambio_simultaneo` y no se registra nada."""
        self.armar()
        x = self.entrega_lista(retiro=True, con_envasado=True)
        huella = self.huella(x, self.e.vendedor)
        carga = CargaDeEnvasado(x.entrega.pk, ((x.envases.pk, "8"),), envasado.huella_de(x.entrega.pk))
        cambiar = lambda: envasado.planificar_envasado(self.e.agronomo, carga)
        resultados = correr_a_la_vez(cambiar, self.concretar(x, self.e.vendedor, huella), primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(Entrega.objects.get(pk=x.entrega.pk).estado_orden, "a_realizar")
        self.assertEqual(PagoCliente.objects.count(), 0)

    def test_ext_5c_iniciar_la_ruta_contra_planificar_una_entrega_del_mismo_transportista(self):
        """Iniciar la ruta contra COM-PNF-ENT (primera la planificación): el inicio espera el invernadero (el semáforo de las entregas del transportista), relee y ve una entrega nueva: `ruta_cambio` con lo agregado; el vehículo no sale."""
        self.armar()
        x = self.entrega_lista(iniciar=False)
        huella = rutas.ruta_del_dia(self.t).huella
        venta2 = compra_venta(self.e, dias=0, direccion=self.direccion)
        reserva_lista(detalle(venta2, self.e.variedad, 20), self.lote, 20)
        planificar = lambda: entregas.planificar_venta(venta2.pk, HOY)
        iniciar = lambda: rutas.iniciar_ruta(self.t, huella)
        resultados = correr_a_la_vez(planificar, iniciar, primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["ruta_cambio"])
        self.assertFalse(Vehiculo.objects.get(transportista=self.t).en_ruta)
        self.assertEqual(Entrega.objects.filter(transportista=self.t).count(), 2)
        self.assertEqual(Entrega.objects.filter(pk=x.entrega.pk).count(), 1)

    def test_regla_el_intento_fallido_contra_concretar_la_segunda_ve_el_resultado_de_la_primera(self):
        """Intento fallido contra concretar (primera el intento): la entrega pasó a mañana sin transportista, así que la concreción se rechaza con `entrega_no_concretable` y no registra pago ni egreso."""
        self.armar()
        x = self.entrega_lista()
        huella = self.huella(x, self.t)
        intento = lambda: rutas.registrar_intento_fallido(self.t, x.entrega.pk, "cliente_ausente", "")
        resultados = correr_a_la_vez(intento, self.concretar(x, self.t, huella), primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["entrega_no_concretable"])
        e = Entrega.objects.get(pk=x.entrega.pk)
        self.assertEqual((e.estado_orden, e.transportista_id), ("a_realizar", None))
        self.assertEqual(PagoCliente.objects.count(), 0)

    def test_regla_concretar_primero_y_despues_el_intento_fallido_se_rechaza(self):
        """El mismo cruce en el otro orden (primera la concreción): el intento fallido relee y ve la entrega ya concretada: `entrega_no_concretable`."""
        self.armar()
        x = self.entrega_lista()
        huella = self.huella(x, self.t)
        intento = lambda: rutas.registrar_intento_fallido(self.t, x.entrega.pk, "cliente_ausente", "")
        resultados = correr_a_la_vez(self.concretar(x, self.t, huella), intento, primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["entrega_no_concretable"])
        self.assertEqual(Entrega.objects.get(pk=x.entrega.pk).estado_orden, "concretada")


@tag("concurrencia")
class ConcrecionAsientoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """CON-04c · paso 3: los asientos de la concreción (mermas, consumos y el compuesto de la entrega) bloquean el ejercicio AL FINAL (D-86 punto 2) y nunca rechazan por la fecha
    (D-102). Se usan retiros (concreta el Vendedor, sin ruta) para no armar transportistas."""

    def armar(self):
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase vacía el plan en cada prueba
        self.e = escenario_comercial(geografia_propia=True)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_contables)

    def retiro_de(self, e, cantidad=50):
        """Una entrega de retiro de hoy lista para concretar por el Vendedor de `e`: devuelve la operación."""
        lote = lote_maduro(e, 500)
        venta = compra_venta(e, dias=0, modalidad="retiro")
        det = detalle(venta, e.variedad, cantidad)
        entrega_ = entrega(venta, [reserva_lista(det, lote, cantidad)], transportista=None, fecha=HOY)
        datos = DatosDeConcrecion(medio_pago="efectivo", sin_envases=True)
        huella = concrecion.resumen_de_concrecion(e.vendedor, entrega_.pk, datos).huella
        return lambda: concrecion.concretar_entrega(e.vendedor, entrega_.pk, datos, huella)

    def con_ejercicios(self):
        """El ejercicio en cierre cubre desde hace 400 días hasta hace unos 36; el abierto empieza hace 20 días y contiene a hoy."""
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, HOY - timedelta(days=400))
        self.abierto = ejercicio_abierto(HOY - timedelta(days=20))

    def cierre(self):
        return lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

    def sin_errores(self, resultados):
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])

    def _cierre_y_entrega(self, primera_la_entrega):
        self.armar()
        self.con_ejercicios()
        entrega_, cierre = self.retiro_de(self.e), self.cierre()
        self.sin_errores(correr_a_la_vez(*((entrega_, cierre) if primera_la_entrega else (cierre, entrega_)), primera="a"))
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento, asiento.fecha_asiento), (self.abierto.pk, 1, HOY))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)

    def test_d102_el_cierre_primero_y_la_concrecion_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """El cierre tiene su fila tomada; la concreción de hoy no la necesita."""
        self._cierre_y_entrega(primera_la_entrega=False)

    def test_d102_la_concrecion_primero_y_el_cierre_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """La concreción ya asentó y tiene el ejercicio abierto bloqueado; el cierre toca solo su fila."""
        self._cierre_y_entrega(primera_la_entrega=True)

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_la_concrecion_bloquea(self):
        """La concreción A se detiene justo ANTES de bloquear el ejercicio (con su invernadero, lotes, contrato y entrega ya tomados); la B (otro invernadero, sin filas en común)
        asienta completa y toma el N.º 1."""
        self.armar()
        ejercicio_abierto(HOY - timedelta(days=20))
        otro = escenario_comercial(nombre="Invernadero Sur", sufijo="b", email_del_cliente="clienteb@ejemplo.com", geografia_propia=True)
        a, b = self.retiro_de(self.e), self.retiro_de(otro)
        resultados = correr_a_la_vez(a, b, primera="a", detener_antes_de=(asientos, "_bloquear_ejercicio"))
        self.sin_errores(resultados)
        numero = lambda entrega_: AsientoContable.objects.get(origen_id=entrega_.pk).numero_asiento  # noqa: E731
        self.assertEqual((numero(resultados["b"]), numero(resultados["a"])), (1, 2))

    def test_regla_h8_dos_concreciones_de_entregas_distintas_toman_numeros_consecutivos_sin_hueco(self):
        """H8: dos entregas distintas a la vez (cada una con su asiento compuesto) toman los números 1 y 2."""
        self.armar()
        ejercicio_abierto(HOY - timedelta(days=20))
        resultados = correr_a_la_vez(self.retiro_de(self.e), self.retiro_de(self.e), primera="a")
        self.sin_errores(resultados)
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2])
