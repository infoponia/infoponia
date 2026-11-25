# Pruebas de concurrencia del pago a proveedores (CMP-05, paso 3). Fuente: docs/casos_de_uso/compras/pagos.md («Requisitos especiales»: «el control de concurrencia impide dos pagos al mismo proveedor en
# la misma orden y respeta el orden de bloqueos: la orden antes que el ejercicio, que se bloquea al final»), D-91 (punto 1: la única ``(orden, proveedor)``; punto 4: la fecha), D-86 (el ejercicio va
# último), D-102 (el asiento automático nunca se rechaza por la fecha), docs/patrones/bloqueos.md («Contabilidad: el ejercicio se bloquea último» y «compras»: el pago es cuentas → ``OrdenCompra`` →
# ``Pago`` → ejercicio) y docs/patrones/asientos.md, secciones 2 y 4.
#
# Dos hilos con ``correr_a_la_vez`` (``TransactionTestCase``: su ``flush`` vacía los datos de las migraciones, así que se aseguran de nuevo en cada prueba, ``docs/patrones/datos_de_migracion.md``).
#
#   - 1: dos pagos a la vez del mismo proveedor y la misma orden: se registra uno solo; el otro espera, relee y recibe ``pago_ya_registrado``. Un solo asiento.
#   - 2: dos pagos a proveedores distintos de la misma orden: los dos se registran, con números de asiento correlativos y sin hueco.
#   - 3: pago contra la recepción del otro proveedor de la misma orden (en la misma fila de la orden): los dos se registran.
#   - 4: el ejercicio va último: un rival que lo bloquea ANTES de la orden forma un *deadlock* con el pago. Si el pago bloqueara el ejercicio primero, esta prueba fallaría por no haber deadlock.
#   - 5: «pago contra cierre del ejercicio» (D-102): con la fecha del pago en el ejercicio «en cierre»,
#       5a: el cierre se confirma antes de que el pago pida su asiento: el pago queda con su fecha y el asiento va al ejercicio abierto, con la fecha de hoy y la aclaración de H10 (el pago no se rechaza);
#       5b: el pago ya tiene el ejercicio tomado: el cierre espera, cierra después, y el asiento queda dentro del ejercicio cerrado con la fecha elegida.

from datetime import timedelta

from django.db import OperationalError, transaction
from django.test import TransactionTestCase, override_settings, tag

from compras.errores import ErrorDeCompras
from compras.models import DetalleOrdenCompra, Pago, Recepcion
from compras.servicios import pagos
from compras.servicios import recepciones as servicio_de_recepciones
from compras.tests.base_recepciones import D
from compras.tests.fabricas import EscenarioDeRecepcion
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import PlanDeCuentasMixin, asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_cuenta
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.tests.fabricas import asegurar_datos_de_maestros, asegurar_georef

PARADA_ANTES_DEL_ASIENTO = (servicio_de_asientos, "registrar_asiento_automatico")
Estado = EjercicioContable.Estado


@tag("concurrencia")
@override_settings(CORREO_CONFIGURADO=False)
class PagosConcurrenciaTests(PlanDeCuentasMixin, ConDatosDeInventario, EscenarioDeRecepcion, TransactionTestCase):
    """El escenario de ``EscenarioDeRecepcion`` (Ana, la orden de A en Norte y B en Norte 2) con un Contador y un ejercicio abierto. Cada prueba recibe lo que necesita."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        asegurar_georef()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase lo vacía en cada prueba
        self.armar()
        self.abierto = ejercicio_abierto()
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")

    # --- auxiliares ---

    def recibir(self, lineas, proveedor=None, invernadero=None):
        """Recepción de Ana de ``lineas`` ``[(detalle, cantidad, vence)]`` del proveedor y el invernadero indicados (por defecto A en Norte)."""
        datos = servicio_de_recepciones.DatosDeRecepcion(
            self.orden.pk,
            (proveedor or self.proveedor).pk,
            (invernadero or self.norte).pk,
            [servicio_de_recepciones.LineaRecibida(d.pk, [(D(str(c)), v)], []) for d, c, v in lineas],
        )
        return servicio_de_recepciones.registrar_recepcion(self.ana, datos)

    def recibir_a(self):
        return self.recibir([(self.l_fert, 10, self.vence), (self.l_maceta, 20, None)])

    def recibir_b(self):
        return self.recibir([(self.l_tomate, 8, None)], proveedor=self.proveedor_b, invernadero=self.norte2)

    def pagar(self, proveedor=None, medio="transferencia", fecha=None, actor=None):
        return lambda: pagos.registrar_pago(actor or self.contador, self.orden.pk, (proveedor or self.proveedor).pk, medio, fecha or self.hoy)

    def exitos_y_errores(self, resultados):
        return [r for r in resultados.values() if not isinstance(r, Exception)], [r for r in resultados.values() if isinstance(r, Exception)]

    def asientos_de_pagos(self):
        return AsientoContable.objects.filter(origen__tipo="pago")

    # --- 1. dos pagos del mismo par ---

    def test_requisito_dos_pagos_del_mismo_proveedor_y_orden_registran_uno_solo(self):
        """Requisitos especiales y R158: dos sesiones pagan a A a la vez; la segunda espera la orden, relee y recibe ``pago_ya_registrado``. Un solo pago, un solo asiento de pago y Proveedores en cero."""
        self.recibir_a()
        resultados = correr_a_la_vez(self.pagar(), self.pagar(medio="efectivo"), primera="a")
        exitos, errores = self.exitos_y_errores(resultados)
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertIsInstance(errores[0], ErrorDeCompras)
        self.assertEqual((errores[0].codigo, errores[0].datos["pago_id"]), ("pago_ya_registrado", exitos[0].pk))
        self.assertEqual((Pago.objects.count(), self.asientos_de_pagos().count()), (1, 1))
        verificar_invariantes_contables()

    # --- 2 y 3. pagos y recepciones de la misma orden ---

    def test_requisito_dos_pagos_de_proveedores_distintos_de_la_misma_orden_toman_numeros_correlativos(self):
        """Los dos pares de la misma orden se pagan a la vez: los dos se registran (se ponen en fila en la orden) con números de asiento correlativos y sin hueco."""
        self.recibir_a()
        self.recibir_b()
        resultados = correr_a_la_vez(self.pagar(), self.pagar(proveedor=self.proveedor_b, medio="efectivo"), primera="a", detener_antes_de=PARADA_ANTES_DEL_ASIENTO)
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual(Pago.objects.count(), 2)
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2, 3, 4])
        verificar_invariantes_contables()

    def test_requisito_pagar_a_un_proveedor_mientras_se_recibe_lo_del_otro_se_registran_los_dos(self):
        """Regla «Pago diferido»: A está listo y B todavía recibe lo suyo. El pago de A (con la orden tomada) y la recepción de B se ponen en fila en la orden: ninguna se pierde ni se cruza."""
        self.recibir_a()
        resultados = correr_a_la_vez(self.pagar(), lambda: self.recibir_b(), primera="a", detener_antes_de=PARADA_ANTES_DEL_ASIENTO)
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual((Pago.objects.get().proveedor_id, Recepcion.objects.filter(proveedor=self.proveedor_b).count()), (self.proveedor.pk, 1))
        self.assertEqual(DetalleOrdenCompra.objects.get(pk=self.l_tomate.pk).estado_detalle_orden, "completo")
        verificar_invariantes_contables()

    # --- 4. el ejercicio va último ---

    def test_regla_el_ejercicio_va_ultimo_un_rival_que_lo_bloquea_antes_de_la_orden_forma_un_deadlock_con_el_pago(self):
        """docs/patrones/asientos.md, secciones 2 y 4, y D-86: el pago toma la orden y **recién al final** el ejercicio. Un rival que bloquea el ejercicio ANTES de la orden (el orden prohibido) se cruza con él:
        el pago detenido antes del asiento tiene la orden; el rival toma el ejercicio y espera la orden; al seguir, el pago pide el ejercicio: *deadlock*, y la base aborta a uno. Si el pago bloqueara el
        ejercicio primero, no habría cruce y esta prueba fallaría."""
        self.recibir_a()

        def rival_con_el_orden_prohibido():
            with transaction.atomic():
                EjercicioContable.objects.select_for_update(no_key=True).get(pk=self.abierto.pk)  # el ejercicio primero...
                from compras.models import OrdenCompra

                OrdenCompra.objects.select_for_update(no_key=True).get(pk=self.orden.pk)  # ...y después la orden

        resultados = correr_a_la_vez(self.pagar(), rival_con_el_orden_prohibido, primera="a", detener_antes_de=PARADA_ANTES_DEL_ASIENTO)
        deadlocks = [r for r in resultados.values() if isinstance(r, OperationalError) and "deadlock" in str(r).lower()]
        self.assertEqual(len(deadlocks), 1, resultados)

    # --- 5. pago contra el cierre del ejercicio ---

    def con_un_ejercicio_en_cierre(self):
        """Un ejercicio «en cierre» que terminó ayer (y el abierto desde hoy): devuelve el «en cierre»."""
        return ejercicio(Estado.EN_CIERRE, self.hoy - timedelta(days=365), self.hoy - timedelta(days=1))

    def test_d102_si_el_ejercicio_se_cierra_antes_del_asiento_el_pago_no_se_rechaza_y_el_asiento_va_al_abierto_con_la_aclaracion(self):
        """D-102 puntos 1 y 2: el pago con fecha en el ejercicio «en cierre» pasó la validación y se detuvo antes de pedir el asiento; el cierre termina sin esperarlo (el pago todavía no tiene el ejercicio).
        Al seguir, el pago **no falla**: queda con su fecha, y el asiento va al ejercicio abierto con la fecha de hoy y «Fecha del hecho: dd/mm/aaaa (el ejercicio de esa fecha ya está cerrado)…»."""
        en_cierre = self.con_un_ejercicio_en_cierre()
        self.recibir_a()
        fecha = self.hoy - timedelta(days=3)
        resultados = correr_a_la_vez(
            self.pagar(fecha=fecha), lambda: ejercicios.cerrar_ejercicio(self.contador, en_cierre.pk), primera="a", detener_antes_de=PARADA_ANTES_DEL_ASIENTO
        )
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual(EjercicioContable.objects.get(pk=en_cierre.pk).estado_ejercicio, Estado.CERRADO)
        pago = Pago.objects.get()
        self.assertEqual(pago.fecha_pago, fecha)
        asiento = AsientoContable.objects.get(origen_id=pago.pk)
        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento), (self.abierto.pk, self.hoy))
        self.assertIn(f"Fecha del hecho: {fecha:%d/%m/%Y}", asiento.descripcion_asiento)
        self.assertIn("el ejercicio de esa fecha ya está cerrado", asiento.descripcion_asiento)
        verificar_invariantes_contables()

    def test_d102_si_el_pago_ya_tiene_el_ejercicio_el_cierre_espera_y_el_asiento_queda_dentro_del_ejercicio_cerrado(self):
        """El pago llega primero (detenido después de crear su asiento, con el ejercicio «en cierre» bloqueado): el cierre espera, cierra cuando el pago confirma, y el asiento queda en ese ejercicio con la
        fecha elegida: el ejercicio cerrado incluye al pago."""
        en_cierre = self.con_un_ejercicio_en_cierre()
        self.recibir_a()
        fecha = self.hoy - timedelta(days=3)
        resultados = correr_a_la_vez(self.pagar(fecha=fecha), lambda: ejercicios.cerrar_ejercicio(self.contador, en_cierre.pk), primera="a")
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual(EjercicioContable.objects.get(pk=en_cierre.pk).estado_ejercicio, Estado.CERRADO)
        asiento = AsientoContable.objects.get(origen_id=Pago.objects.get().pk)
        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento, asiento.numero_asiento), (en_cierre.pk, fecha, 1))
        self.assertNotIn("Fecha del hecho", asiento.descripcion_asiento)
        verificar_invariantes_contables()
