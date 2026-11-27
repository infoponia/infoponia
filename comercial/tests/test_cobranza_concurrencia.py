# Pruebas de concurrencia de COM-08a (docs/casos_de_uso/comercial/cobranza.md, «Requisitos especiales» y «Pruebas»; docs/patrones/bloqueos.md, «Cobranza»): dos cobros de la misma entrega (uno gana; el otro recibe
# `entrega_ya_pagada`), un cobro contra la aceptación de una solicitud de la misma entrega (en los dos órdenes: el segundo ve la huella cambiada, `cobro_cambio` o `solicitud_cambio`), un cobro contra el paso 30
# sobre la misma entrega (en los dos órdenes) y el orden de los bloqueos (cuentas → invernaderos de origen → entregas): el cobro se detiene justo antes de tomar las entregas, ya con el invernadero, y la
# aceptación (invernadero → suministro → entrega) tiene que esperarlo sin cruzarse; con el orden invertido hay un deadlock y la prueba falla.
# Dos hilos, dos conexiones, el orden fijado con ``primera``. Son `TransactionTestCase`: sin Georef de la migración (el cliente tiene una dirección en la localidad propia que arma `geografia_propia`). Todas
# terminan verificando los invariantes. Nunca un error 500: la que llega segunda espera, relee con todo bloqueado y recibe un código de negocio o no hace nada.
#
# Contrato de código que fijan estas pruebas: `cobranza._bloquear_entregas(...)` es el único lugar donde el cobro toma las filas de las entregas (después de las cuentas y los invernaderos).

from datetime import timedelta

from django.core.cache import cache
from django.test import TransactionTestCase, override_settings, tag
from django.utils import timezone

from comercial.models import Entrega, LineaPago, PagoCliente
from comercial.servicios import cobranza, solicitudes
from comercial.servicios.solicitudes import DatosDeResolucion
from comercial.tests.fabricas import (
    direccion_de_cliente,
    discrepancia,
    entrega_de_suministro,
    entrega_en_mora,
    escenario_comercial,
    verificar_invariantes_de_cobros,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_solicitudes,
)
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador
from core.tests.concurrencia import codigos, correr_a_la_vez
from core.tests.fabricas import crear_cuenta, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Localidad
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.tests.fabricas import lote_maduro, separar
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HOY = timezone.localdate()


@tag("concurrencia")
class CobranzaConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self):
        """Un invernadero con su Vendedor, un lote de 500 y un Gerente; el cliente con una dirección en la localidad propia. Cada prueba arma sus entregas."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # CON-04d: cobrar asienta; el flush de la prueba anterior vació el plan
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento; el flush de esta TransactionTestCase lo vacía en cada prueba
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 500)
        self.gerente = crear_gerente()
        direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk)
        for verificar in (verificar_invariantes_de_entregas, verificar_invariantes_de_solicitudes, verificar_invariantes_de_cobros):
            self.addCleanup(verificar)

    def datos(self, entregas_):
        return cobranza.DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[e.pk for e in entregas_], medio_pago="efectivo")

    def cobrar(self, actor, entregas_, hoy=HOY):
        """El cobro como lo hace la pantalla: el resumen (sin bloquear) y el registro."""

        def operacion():
            with override_settings(CORREO_CONFIGURADO=False):
                datos = self.datos(entregas_)
                return cobranza.registrar_cobro(actor, datos, cobranza.resumen_de_cobro(actor, datos, hoy).huella, hoy)

        return operacion

    def aceptar(self, solicitud):
        """La aceptación de una discrepancia, como la pantalla (resumen y registro)."""

        def operacion():
            datos = DatosDeResolucion("aceptar", "", "", "efectivo")
            return solicitudes.resolver_solicitud(self.gerente, solicitud.pk, datos, solicitudes.resumen_de_resolucion(self.gerente, solicitud.pk, datos).huella)

        return operacion

    def cobros(self):
        return PagoCliente.objects.filter(tipo_pago="suministro").count()

    # ---- dos cobros de la misma entrega ----

    def test_regla_dos_cobros_de_la_misma_entrega_uno_gana_y_el_otro_recibe_entrega_ya_pagada(self):
        """Garantía mínima 2 y requisito especial: impide que una entrega se cobre dos veces. El primero confirma; el segundo espera el invernadero y la entrega, relee y recibe `entrega_ya_pagada`."""
        self.armar()
        e = entrega_de_suministro(self.e, self.lote)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cobrar(self.gerente, [e]), self.cobrar(self.e.vendedor, [e]), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("entrega_ya_pagada", codigos(rechazos[0]))
        self.assertEqual((self.cobros(), LineaPago.objects.filter(entrega=e, vigente=True).count()), (1, 1))

    def test_regla_dos_cobros_de_entregas_distintas_del_mismo_cliente_pasan_los_dos(self):
        """Lo que no se pisa no se bloquea entre sí: dos cobros de entregas distintas confirman los dos (sin deadlock aunque compartan invernadero)."""
        self.armar()
        a, b = entrega_de_suministro(self.e, self.lote), entrega_de_suministro(self.e, self.lote)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cobrar(self.gerente, [a]), self.cobrar(self.e.vendedor, [b]), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(self.cobros(), 2)

    # ---- un cobro contra la aceptación de una solicitud ----

    def test_regla_la_aceptacion_primero_y_el_cobro_ve_la_huella_cambiada(self):
        """Contraparte de 8b de COM-EVL-DSC: la aceptación baja el monto a cobrar; el cobro, que esperaba, relee y recibe `cobro_cambio`: no cobra el monto viejo."""
        self.armar()
        e = entrega_de_suministro(self.e, self.lote)
        solicitud = discrepancia(e, minima=12)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.aceptar(solicitud), self.cobrar(self.gerente, [e]), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("cobro_cambio", codigos(rechazos[0]))
        self.assertEqual(self.cobros(), 0)

    def test_regla_el_cobro_primero_y_la_aceptacion_ve_la_huella_cambiada(self):
        """Requisito especial: impide que una entrega se cobre mientras se registra la aceptación (y al revés): con el cobro primero, la aceptación recibe `solicitud_cambio` (el estado de pago cambió)."""
        self.armar()
        e = entrega_de_suministro(self.e, self.lote)
        solicitud = discrepancia(e, minima=12)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cobrar(self.gerente, [e]), self.aceptar(solicitud), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("solicitud_cambio", codigos(rechazos[0]))
        self.assertEqual(self.cobros(), 1)

    # ---- un cobro contra el paso 30 ----

    def test_regla_el_cobro_primero_y_el_paso_30_ya_no_alerta_esa_entrega(self):
        """El cobro confirma; el paso 30, que espera el invernadero, relee: la entrega está pagada y no la avisa (sin alerta, sin fecha de aviso)."""
        self.armar()
        e = entrega_en_mora(self.e, self.lote)
        resultados = correr_a_la_vez(self.cobrar(self.gerente, [e]), lambda: cobranza.vencer_pagos(HOY), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual((self.cobros(), Entrega.objects.get(pk=e.pk).fecha_aviso_mora), (1, None))

    def test_regla_el_paso_30_primero_y_el_cobro_resuelve_la_alerta_que_acaba_de_nacer(self):
        """El paso 30 crea la alerta y confirma; el cobro, que esperaba, relee (la huella no cambió: sigue en mora con el mismo monto) y cobra, y su `reevaluar_mora` resuelve la alerta."""
        from comercial.models import AlertaComercial

        self.armar()
        e = entrega_en_mora(self.e, self.lote)
        resultados = correr_a_la_vez(lambda: cobranza.vencer_pagos(HOY), self.cobrar(self.gerente, [e]), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual(self.cobros(), 1)
        (vinculo,) = AlertaComercial.objects.filter(entrega_id=e.pk).select_related("alerta")
        self.assertEqual(vinculo.alerta.estado_alerta, "resuelta")

    # ---- el orden de los bloqueos ----

    def test_regla_el_cobro_toma_el_invernadero_antes_que_las_entregas_y_no_se_cruza_con_la_aceptacion(self):
        """`bloqueos.md`, «Cobranza»: cuentas → invernaderos de origen → entregas. El cobro se detiene justo ANTES de tomar las entregas, ya con las cuentas y el invernadero; la aceptación (cuentas → invernadero →
        suministro → entrega) arranca y espera, y no se cruzan. OJO: cobro y aceptación comparten la cuenta del Vendedor del contrato, así que ya quedan en fila ahí; esta prueba NO detecta un orden invertido de
        invernaderos y entregas (lo detectan las dos con el paso 30, que no toma cuentas)."""
        self.armar()
        e = entrega_de_suministro(self.e, self.lote)
        solicitud = discrepancia(e, minima=12)
        resultados = correr_a_la_vez(self.cobrar(self.gerente, [e]), self.aceptar(solicitud), primera="a", detener_antes_de=(cobranza, "_bloquear_entregas"))
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("solicitud_cambio", codigos(rechazos[0]))
        self.assertEqual(self.cobros(), 1)

    def test_regla_el_cobro_no_tiene_las_entregas_tomadas_cuando_todavia_le_faltan_los_invernaderos(self):
        """El otro extremo del orden: el cobro se detiene justo ANTES de tomar los invernaderos. Con el orden correcto solo tiene las cuentas, así que el paso 30 (invernadero → entrega, sin cuentas) corre y confirma
        sin esperarlo; el cobro sigue, relee (la huella no cambió: solo nació la alerta) y cobra, y resuelve la alerta. Si el cobro tomara las entregas ANTES que los invernaderos, tendría la entrega en este punto, el paso 30
        tomaría el invernadero y esperaría la entrega mientras el cobro pide ese invernadero: un deadlock que la base resuelve abortando a uno con un error que no es de negocio, y esta prueba falla."""
        from comercial.models import AlertaComercial

        self.armar()
        e = entrega_en_mora(self.e, self.lote)
        resultados = correr_a_la_vez(self.cobrar(self.gerente, [e]), lambda: cobranza.vencer_pagos(HOY), primera="a", detener_antes_de=(cobranza, "_bloquear_invernaderos"))
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual(self.cobros(), 1)
        (vinculo,) = AlertaComercial.objects.filter(entrega_id=e.pk).select_related("alerta")
        self.assertEqual(vinculo.alerta.estado_alerta, "resuelta")

    def test_regla_el_paso_30_toma_el_invernadero_antes_que_la_entrega_y_no_se_cruza_con_el_cobro(self):
        """El paso 30 toma, por entrega, su invernadero y después la entrega: el mismo orden que el cobro. Detenido antes de tomar la entrega, el cobro espera el invernadero y no se cruzan."""
        self.armar()
        e = entrega_en_mora(self.e, self.lote)
        resultados = correr_a_la_vez(lambda: cobranza.vencer_pagos(HOY), self.cobrar(self.gerente, [e]), primera="a", detener_antes_de=(cobranza, "_bloquear_entrega_del_paso"))
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual(self.cobros(), 1)


@tag("concurrencia")
class CobroAsientoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """CON-04d · paso 1: el asiento del cobro bloquea el ejercicio AL FINAL (D-86 punto 2; `docs/patrones/asientos.md`), numera sin huecos (H8) y nunca rechaza por la fecha (D-102), también contra el cierre del
    ejercicio en los dos órdenes (el patrón de CON-04c)."""

    def armar(self):
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase vacía el plan en cada prueba
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 500)
        self.gerente = crear_gerente()
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk)
        for verificar in (verificar_invariantes_de_entregas, verificar_invariantes_de_cobros, verificar_invariantes_contables):
            self.addCleanup(verificar)

    def cobro_de(self, e, entregas_=None, actor=None):
        """La operación de cobrar ``entregas_`` (una entrega de suministro nueva por omisión) de ``e``, con la huella del resumen."""
        entregas_ = entregas_ or [entrega_de_suministro(e, lote_maduro(e, 500))]
        actor = actor or e.vendedor
        datos = cobranza.DatosDeCobro(cliente_id=e.cliente.pk, entrega_ids=[x.pk for x in entregas_], medio_pago="efectivo")
        huella = cobranza.resumen_de_cobro(actor, datos, HOY).huella

        def operacion():
            with override_settings(CORREO_CONFIGURADO=False):
                return cobranza.registrar_cobro(actor, datos, huella, HOY)

        return operacion

    def sin_errores(self, resultados):
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])

    def con_ejercicios(self):
        """El ejercicio en cierre cubre desde hace 400 días hasta hace unos 36; el abierto empieza hace 20 días y contiene a hoy."""
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, HOY - timedelta(days=400))
        self.abierto = ejercicio_abierto(HOY - timedelta(days=20))

    def _cierre_y_cobro(self, primero_el_cobro):
        self.armar()
        self.con_ejercicios()
        cobro, cierre = self.cobro_de(self.e), lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)
        self.sin_errores(correr_a_la_vez(*((cobro, cierre) if primero_el_cobro else (cierre, cobro)), primera="a"))
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento, asiento.fecha_asiento), (self.abierto.pk, 1, HOY))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)

    def test_d102_el_cierre_primero_y_el_cobro_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """El cierre tiene su fila tomada; el cobro de hoy no la necesita."""
        self._cierre_y_cobro(primero_el_cobro=False)

    def test_d102_el_cobro_primero_y_el_cierre_a_la_vez_los_dos_terminan_y_el_asiento_va_al_abierto(self):
        """El cobro ya asentó y tiene el ejercicio abierto bloqueado; el cierre toca solo su fila."""
        self._cierre_y_cobro(primero_el_cobro=True)

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_el_cobro_bloquea(self):
        """El cobro A se detiene justo ANTES de bloquear el ejercicio (con sus cuentas, invernadero y entrega ya tomados); el cobro B (otro invernadero, sin filas en común) asienta completo y toma el N.º 1."""
        self.armar()
        ejercicio_abierto(HOY - timedelta(days=20))
        otro = escenario_comercial(nombre="Invernadero Sur", sufijo="b", email_del_cliente="clienteb@ejemplo.com", geografia_propia=True)
        direccion_de_cliente(otro.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk)
        a, b = self.cobro_de(self.e), self.cobro_de(otro)
        resultados = correr_a_la_vez(a, b, primera="a", detener_antes_de=(servicio_de_asientos, "_bloquear_ejercicio"))
        self.sin_errores(resultados)
        numero = lambda pago: AsientoContable.objects.get(origen_id=pago.pk).numero_asiento  # noqa: E731
        self.assertEqual((numero(resultados["b"]), numero(resultados["a"])), (1, 2))

    def test_regla_h8_dos_cobros_de_entregas_distintas_toman_numeros_consecutivos_sin_hueco(self):
        """H8: dos cobros a la vez (de entregas distintas del mismo cliente), cada uno con su asiento compuesto, toman los números 1 y 2."""
        self.armar()
        ejercicio_abierto(HOY - timedelta(days=20))
        self.sin_errores(correr_a_la_vez(self.cobro_de(self.e), self.cobro_de(self.e), primera="a"))
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2])
