# Pruebas de concurrencia de COM-ANL-CBR (COM-08b, paso 5; docs/casos_de_uso/comercial/cobranza.md, «Requisitos especiales» y «Pruebas»; docs/patrones/bloqueos.md, «Cobranza»): dos anulaciones del mismo cobro
# (una gana; la otra recibe `cobro_ya_anulado`), dos cobros correctos de la misma anulación (uno gana; el otro recibe `anulacion_ya_usada`), y la anulación contra el paso 30 sobre entregas del mismo
# invernadero (el paso 30 retenido con el invernadero: la anulación espera y no se cruzan) y el orden de los bloqueos (cuentas → invernaderos de origen → entregas → el pago y sus líneas).
# Dos hilos, dos conexiones, el orden fijado con ``primera``. Son `TransactionTestCase`: sin Georef de la migración (el cliente tiene una dirección en la localidad propia que arma `geografia_propia`). Todas
# terminan verificando los invariantes. Nunca un error 500: la que llega segunda espera, relee con todo bloqueado y recibe un código de negocio o no hace nada.
#
# Contrato de código que fijan estas pruebas: `cobranza._bloquear_pago_y_lineas(pago_id)` es el único lugar donde la anulación toma el pago y sus líneas (después de las cuentas, los invernaderos y las entregas,
# que toma con `_bloquear_invernaderos` y `_bloquear_entregas`, las mismas funciones del cobro). Sobre qué detecta cada prueba, ver su docstring: la anulación y el cobro (o la aceptación de una solicitud) comparten
# las cuentas (el Gerente y el Vendedor) y quedan en fila ahí, así que solo el paso 30 (que no toma cuentas) puede cruzarse con ella en los invernaderos y las entregas.

from datetime import timedelta

from django.test import TransactionTestCase, override_settings, tag
from django.utils import timezone

from comercial.models import AlertaComercial, Anulacion, Entrega, LineaPago, PagoCliente
from comercial.servicios import cobranza
from comercial.tests.fabricas import (
    direccion_de_cliente,
    entrega_de_suministro,
    entrega_en_mora,
    escenario_comercial,
    verificar_invariantes_de_cobros,
    verificar_invariantes_de_entregas,
)
from contabilidad.models import AsientoContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio_abierto, verificar_invariantes_contables
from core.tests.concurrencia import codigos, correr_a_la_vez
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Localidad
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.tests.fabricas import lote_maduro, separar
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HOY = timezone.localdate()
LUEGO = HOY + timedelta(days=4)
DatosDeCobro = cobranza.DatosDeCobro


@tag("concurrencia")
class AnulacionDeCobroConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self):
        """Un invernadero con su Vendedor, un lote de 500 y un Gerente; el cliente con una dirección en la localidad propia. Cada prueba arma sus entregas y sus cobros."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # CON-04d: cobrar y anular un cobro asientan; el flush de la prueba anterior vació el plan
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento; el flush de esta TransactionTestCase lo vacía en cada prueba
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 500)
        self.gerente = crear_gerente()
        direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk)
        for verificar in (verificar_invariantes_de_entregas, verificar_invariantes_de_cobros):
            self.addCleanup(verificar)

    def datos(self, entregas_, **extra):
        return DatosDeCobro(cliente_id=self.e.cliente.pk, entrega_ids=[e.pk for e in entregas_], medio_pago="efectivo", **extra)

    def registrar(self, entregas_, hoy=HOY, **extra):
        """El cobro como la pantalla, ya hecho (en el hilo de la prueba, sin correo)."""
        datos = self.datos(entregas_, **extra)
        with override_settings(CORREO_CONFIGURADO=False):
            return cobranza.registrar_cobro(self.gerente, datos, cobranza.resumen_de_cobro(self.gerente, datos, hoy).huella, hoy)

    def anular(self, pago, *, hoy=HOY, pago_en_fecha=False):
        """La anulación como la pantalla (los datos y la confirmación), con la huella que vio antes de que arrancara la otra operación."""
        huella = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, hoy).huella

        def operacion():
            with override_settings(CORREO_CONFIGURADO=False):
                return cobranza.anular_cobro(self.gerente, pago.pk, "Error de carga.", pago_en_fecha, huella, hoy)

        return operacion

    def cobrar_correcto(self, entregas_, anulacion):
        """El cobro correcto de 7a (con la fecha del cobro anulado), con la huella del resumen que vio la pantalla antes de que arrancara la otra operación."""
        datos = self.datos(entregas_, anulacion_id=anulacion.pk, usar_fecha_anulada=True)
        huella = cobranza.resumen_de_cobro(self.gerente, datos, LUEGO).huella

        def operacion():
            with override_settings(CORREO_CONFIGURADO=False):
                return cobranza.registrar_cobro(self.gerente, datos, huella, LUEGO)

        return operacion

    # ---- dos anulaciones del mismo cobro ----

    def test_regla_dos_anulaciones_del_mismo_cobro_una_gana_y_la_otra_recibe_cobro_ya_anulado(self):
        """5a y requisito especial («una única transacción serializada con COM-REG-CBR»): la primera confirma; la segunda espera el invernadero y las entregas, relee con el pago ya anulado y recibe
        `cobro_ya_anulado`: una sola anulación, una sola alerta nueva y un solo aviso."""
        self.armar()
        e = entrega_en_mora(self.e, self.lote)
        pago = self.registrar([e])
        exitos, rechazos, otros = separar(correr_a_la_vez(self.anular(pago), self.anular(pago), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("cobro_ya_anulado", codigos(rechazos[0]))
        self.assertEqual((Anulacion.objects.filter(pago_cliente=pago).count(), LineaPago.objects.filter(vigente=True).count()), (1, 0))
        self.assertEqual(AlertaComercial.objects.filter(entrega_id=e.pk, alerta__estado_alerta="activa").count(), 1)

    # ---- dos cobros correctos de la misma anulación ----

    def test_regla_dos_cobros_correctos_de_la_misma_anulacion_uno_gana_y_el_otro_recibe_anulacion_ya_usada(self):
        """7a («una sola vez por anulación»): dos cobros correctos de la misma anulación (de las dos entregas del cobro anulado, para que no choquen por la entrega): el primero confirma; el segundo espera, relee y
        recibe `anulacion_ya_usada`. Un solo cobro con `anulacion_corregida`."""
        self.armar()
        e1, e2 = entrega_en_mora(self.e, self.lote), entrega_en_mora(self.e, self.lote)
        original = self.registrar([e1, e2])
        datos = cobranza.datos_de_anulacion_de_cobro(self.gerente, original.pk, LUEGO)
        anulacion = cobranza.anular_cobro(self.gerente, original.pk, "El cliente pagó, se cargó mal.", True, datos.huella, LUEGO)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cobrar_correcto([e1], anulacion), self.cobrar_correcto([e2], anulacion), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("anulacion_ya_usada", codigos(rechazos[0]))
        self.assertEqual(PagoCliente.objects.filter(anulacion_corregida=anulacion).count(), 1)

    # ---- la anulación contra el paso 30 ----

    def preparar_anulable_y_candidata(self):
        """Dos entregas del mismo invernadero: una ya cobrada en mora (la anulación la deja otra vez «en mora»: alerta y primer correo) y otra en mora todavía sin cobrar ni avisar (la candidata del paso 30)."""
        self.armar()
        self.cobrada = entrega_en_mora(self.e, self.lote)
        self.candidata = entrega_en_mora(self.e, self.lote)
        self.pago = self.registrar([self.cobrada])

    def esperado_de_las_dos(self):
        """Ninguna operación pisó a la otra: la anulación creó la alerta de la cobrada y el paso 30, la de la candidata; cada una con su fecha de aviso."""
        for e in (self.cobrada, self.candidata):
            self.assertEqual(AlertaComercial.objects.filter(entrega_id=e.pk, alerta__estado_alerta="activa").count(), 1, e.codigo)
            self.assertEqual(Entrega.objects.get(pk=e.pk).fecha_aviso_mora, HOY, e.codigo)

    def test_regla_el_paso_30_retiene_el_invernadero_y_la_anulacion_espera_sin_cruzarse(self):
        """`bloqueos.md`, «Cobranza»: el paso 30 toma, por entrega, su invernadero y después la entrega. Detenido justo ANTES de tomar su entrega (ya con el invernadero), la anulación (cuentas → invernaderos) arranca,
        espera ese invernadero y, cuando el paso 30 termina, sigue: sin error ni deadlock."""
        self.preparar_anulable_y_candidata()
        resultados = correr_a_la_vez(lambda: cobranza.vencer_pagos(HOY), self.anular(self.pago), primera="a", detener_antes_de=(cobranza, "_bloquear_entrega_del_paso"))
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual(PagoCliente.objects.get(pk=self.pago.pk).estado_pago, "anulado")
        self.esperado_de_las_dos()

    def test_regla_la_anulacion_retiene_el_invernadero_y_las_entregas_y_el_paso_30_espera_sin_cruzarse(self):
        """La anulación se detiene justo ANTES de tomar el pago y sus líneas, ya con las cuentas, los invernaderos y las entregas (el orden de «Cobranza»); el paso 30 (invernadero → entrega, sin cuentas)
        arranca, espera el invernadero y sigue cuando la anulación termina. Si la anulación tomara el pago ANTES que el invernadero y las entregas, o las entregas antes que el invernadero, el orden sería otro
        que el del paso 30 y esta prueba (con la del cobro, que usa las mismas funciones) lo vería como un deadlock."""
        self.preparar_anulable_y_candidata()
        resultados = correr_a_la_vez(self.anular(self.pago), lambda: cobranza.vencer_pagos(HOY), primera="a", detener_antes_de=(cobranza, "_bloquear_pago_y_lineas"))
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual(PagoCliente.objects.get(pk=self.pago.pk).estado_pago, "anulado")
        self.esperado_de_las_dos()

    def test_regla_la_anulacion_primero_y_el_paso_30_no_repite_la_alerta_ni_el_correo(self):
        """Regla 3 de COM-VNC-PAG con la anulación: la anulación asegura la alerta de la entrega cobrada y carga su `fecha_aviso_mora`; el paso 30, que corre después, no la vuelve a tocar (una alerta, un aviso)."""
        self.preparar_anulable_y_candidata()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.anular(self.pago), lambda: cobranza.vencer_pagos(HOY), primera="a"))
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.esperado_de_las_dos()
        self.assertEqual(AlertaComercial.objects.filter(entrega_id=self.cobrada.pk).count(), 1)

    # ---- el orden de los bloqueos, sondeado fila por fila ----

    def tomada(self, modelo, pk):
        """¿Otra transacción ya tiene tomada esa fila? Se la pide con `NOWAIT` en un savepoint y con el mismo modo que usa la anulación (`FOR NO KEY UPDATE`): si no puede, está tomada."""
        from django.db import OperationalError, transaction

        try:
            with transaction.atomic():
                list(modelo.objects.select_for_update(no_key=True, nowait=True, of=("self",)).filter(pk=pk))
            return False
        except OperationalError:
            return True

    def sondear(self, entrega_, pago):
        """Qué filas tiene tomadas la operación que está detenida: `(invernadero, entrega, pago)`. Se corre como la segunda operación de `correr_a_la_vez`, con la primera detenida."""
        from comercial.models import PagoCliente
        from maestros.models import Invernadero
        from produccion.models import OrdenTrabajo

        def operacion():
            return (self.tomada(Invernadero, entrega_.invernadero_id), self.tomada(OrdenTrabajo, entrega_.pk), self.tomada(PagoCliente, pago.pk))

        return operacion

    def test_regla_la_anulacion_toma_el_invernadero_y_todavia_no_las_entregas_antes_de_tomarlas(self):
        """`bloqueos.md`, «Cobranza»: cuentas → invernaderos de origen → entregas → pago y líneas. Detenida justo ANTES de tomar las entregas, la anulación ya tiene el invernadero y todavía no tiene ni la entrega ni el pago.
        Si tomara las entregas antes que el invernadero (o el pago antes que las entregas), esta prueba falla: el orden no se puede invertir sin que la sonda lo vea."""
        self.preparar_anulable_y_candidata()
        resultados = correr_a_la_vez(self.anular(self.pago), self.sondear(self.cobrada, self.pago), primera="a", detener_antes_de=(cobranza, "_bloquear_entregas"))
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []))
        self.assertIn((True, False, False), exitos)

    def test_regla_la_anulacion_toma_el_pago_y_las_lineas_al_final_despues_de_las_entregas(self):
        """Detenida justo ANTES de tomar el pago y sus líneas, la anulación ya tiene el invernadero y la entrega y todavía no el pago."""
        self.preparar_anulable_y_candidata()
        resultados = correr_a_la_vez(self.anular(self.pago), self.sondear(self.cobrada, self.pago), primera="a", detener_antes_de=(cobranza, "_bloquear_pago_y_lineas"))
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []))
        self.assertIn((True, True, False), exitos)


@tag("concurrencia")
class AnulacionDeCobroAsientoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """CON-04d · paso 1: el contraasiento de la anulación bloquea el ejercicio AL FINAL (D-86 punto 2), después del pago y de sus líneas (el orden de la anulación), y numera sin huecos (H8)."""

    def armar(self):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase vacía el plan en cada prueba
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 500)
        self.gerente = crear_gerente()
        direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk)
        for verificar in (verificar_invariantes_de_entregas, verificar_invariantes_de_cobros, verificar_invariantes_contables):
            self.addCleanup(verificar)
        ejercicio_abierto(HOY - timedelta(days=20))

    def cobrado(self, e):
        """Un cobro ya registrado (en el hilo de la prueba) de una entrega nueva de ``e``; devuelve la operación que lo anula, con la huella que vio la pantalla."""
        entrega_ = entrega_de_suministro(e, lote_maduro(e, 500))
        datos = cobranza.DatosDeCobro(cliente_id=e.cliente.pk, entrega_ids=[entrega_.pk], medio_pago="efectivo")
        with override_settings(CORREO_CONFIGURADO=False):
            pago = cobranza.registrar_cobro(self.gerente, datos, cobranza.resumen_de_cobro(self.gerente, datos, HOY).huella, HOY)
        huella = cobranza.datos_de_anulacion_de_cobro(self.gerente, pago.pk, HOY).huella

        def operacion():
            with override_settings(CORREO_CONFIGURADO=False):
                return cobranza.anular_cobro(self.gerente, pago.pk, "Error de carga.", False, huella, HOY)

        return operacion

    def sin_errores(self, resultados):
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])

    # Sin prueba de «el ejercicio es lo último» para la anulación: solo el Gerente anula y es uno, así que dos anulaciones quedan en fila en su cuenta y nada distingue el orden (lo prueba el cobro, que sí lo hacen cuentas distintas).

    def test_regla_h8_dos_anulaciones_a_la_vez_toman_numeros_consecutivos_sin_hueco(self):
        """H8: dos anulaciones de cobros distintos a la vez toman el 3 y el 4 (los cobros tenían el 1 y el 2)."""
        self.armar()
        a, b = self.cobrado(self.e), self.cobrado(self.e)
        self.sin_errores(correr_a_la_vez(a, b, primera="a"))
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2, 3, 4])
