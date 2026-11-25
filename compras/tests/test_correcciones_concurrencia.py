# Pruebas de concurrencia de la corrección de recepciones y de la emisión de reclamos (CMP-06, pasos 2 y 3). Fuente: docs/casos_de_uso/compras/correccion_y_reclamos.md («Requisitos especiales» de
# CMP-COR-RCP: «el control de concurrencia impide corregir una línea mientras se la recibe, se la cierra con faltante, se la paga o se consume el lote, y respeta el orden de bloqueos de
# docs/patrones/bloqueos.md (el ejercicio al final)»; «Pruebas»: corrección contra pago, corrección contra consumo del lote, dos emisiones del mismo reclamo), D-86 (el ejercicio va último), D-90
# punto 5 (orden de bloqueo de compras: cuentas → invernadero → ``Insumo`` → ``InsumoInvernadero`` → lotes → … → orden → líneas → recepción → ``Pago`` → ``ReclamoProveedor`` → ejercicio),
# docs/patrones/bloqueos.md («Contabilidad: el ejercicio se bloquea último» y «compras») y docs/patrones/asientos.md, secciones 2 y 4.
#
# Dos hilos con ``correr_a_la_vez`` (``TransactionTestCase``: su ``flush`` vacía los datos de las migraciones, así que se aseguran de nuevo en cada prueba). Por defecto, la primera operación se
# detiene después de su primer registro de auditoría (con todos sus bloqueos tomados y sin confirmar) y entonces arranca la otra.
#
#   - 1 y 1b: corrección contra pago del mismo proveedor y orden (en los dos órdenes): se registra uno solo; el otro espera, relee y se rechaza (sin pago pendiente o con pago registrado).
#   - 2 y 2b: corrección contra una salida por consumo del mismo lote (en los dos órdenes): el lote nunca queda negativo; si el consumo gana, la corrección se rechaza con lo que queda.
#   - 3: dos correcciones de la misma línea que no caben juntas: la segunda espera, relee y recibe ``supera_lo_corregible`` con lo que queda.
#   - 4: dos correcciones de recepciones de la misma orden con asiento: las dos se registran con números de asiento correlativos y sin hueco.
#   - 5: el ejercicio va último: un rival que lo bloquea ANTES de la orden forma un *deadlock* con la corrección.
#   - 6: dos emisiones a la vez del mismo reclamo: se emite una sola vez, la otra recibe ``reclamo_ya_emitido`` y la alerta se resuelve una vez.

from django.db import OperationalError, transaction
from django.test import TransactionTestCase, override_settings, tag

from compras.errores import ErrorDeCompras
from compras.models import CorreccionRecepcion, DetalleRecepcion, OrdenCompra, Pago, ReclamoProveedor
from compras.servicios import pagos
from compras.servicios import recepciones as servicio_de_recepciones
from compras.tests.base_correcciones import correcciones, reclamos
from compras.tests.base_recepciones import D
from compras.tests.fabricas import EscenarioDeRecepcion
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import PlanDeCuentasMixin, asegurar_plan_de_cuentas, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador, RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_cuenta
from inventario.models import InsumoInvernadero, LoteInsumo
from inventario.servicios import alertas_de_stock, stock
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, origen_falso, verificar_invariantes
from maestros.models import Alerta
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from maestros.tests.fabricas import asegurar_datos_de_maestros, asegurar_georef

PARADA_ANTES_DEL_ASIENTO = (servicio_de_asientos, "registrar_asiento_automatico")
DANADA = "mercaderia_danada"


@tag("concurrencia")
@override_settings(CORREO_CONFIGURADO=False)
class CorreccionesConcurrenciaTests(PlanDeCuentasMixin, ConDatosDeInventario, EscenarioDeRecepcion, TransactionTestCase):
    """El escenario de ``EscenarioDeRecepcion`` (Ana, la orden de A en Norte y B en Norte 2) con un Contador y un ejercicio abierto. Cada prueba recibe lo que necesita."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        asegurar_georef()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase lo vacía en cada prueba (docs/patrones/datos_de_migracion.md)
        self.armar()
        self.abierto = ejercicio_abierto()
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")

    # --- auxiliares ---

    def recibir(self, lineas, proveedor=None, invernadero=None):
        """Recepción de Ana de ``lineas`` ``[(detalle, cantidad, vence)]`` del proveedor y el invernadero indicados (por defecto A en Norte); sin correos."""
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

    def recibir_con_inconveniente(self):
        datos = servicio_de_recepciones.DatosDeRecepcion(
            self.orden.pk,
            self.proveedor.pk,
            self.norte.pk,
            [servicio_de_recepciones.LineaRecibida(self.l_fert.pk, [(D("4"), self.vence)], [(DANADA, D("2"), "Cajas rotas")])],
        )
        return servicio_de_recepciones.registrar_recepcion(self.ana, datos)

    def corregir(self, actor, recepcion, detalle_orden, cantidad):
        """La operación de corregir ``cantidad`` de la línea ``detalle_orden`` de ``recepcion`` (la línea de la recepción se busca al correr)."""

        def operacion():
            linea = DetalleRecepcion.objects.get(recepcion=recepcion, detalle_orden=detalle_orden)
            return correcciones.registrar_correccion(actor, recepcion.pk, [(linea.pk, D(str(cantidad)))], "")

        return operacion

    def pagar(self, proveedor=None):
        return lambda: pagos.registrar_pago(self.contador, self.orden.pk, (proveedor or self.proveedor).pk, "transferencia", self.hoy)

    def consumir(self, lote_, cantidad):
        """Una salida por consumo de ``produccion`` simulada con lo que ella hace: el invernadero bloqueado y ``registrar_salida_por_consumo`` (sin importar ``produccion``, regla A1)."""
        origen = origen_falso()

        def operacion():
            with transaction.atomic():
                bloquear_invernadero_activo(self.norte.pk)
                return stock.registrar_salida_por_consumo(self.fertilizante.pk, [(lote_.pk, D(str(cantidad)))], origen_id=origen.pk)

        return operacion

    def exitos_y_errores(self, resultados):
        return [r for r in resultados.values() if not isinstance(r, Exception)], [r for r in resultados.values() if isinstance(r, Exception)]

    def transito(self, iin):
        return InsumoInvernadero.objects.get(pk=iin.pk).cant_transito_insumo

    def lote_de_fertilizante(self):
        return LoteInsumo.objects.get(insumo_invernadero=self.fertilizante, es_faltante_sin_lote=False)

    # --- 1. corrección contra pago ---

    def test_requisito_si_la_correccion_gana_el_pago_espera_y_se_rechaza_sin_pago_pendiente(self):
        """Requisitos especiales («impide corregir una línea mientras se la paga»): la corrección tiene la orden y las líneas; el pago espera la orden, relee y ya no hay nada para pagar (la línea volvió a
        «pendiente»): ``sin_pago_pendiente``. Queda la corrección, ningún pago y Proveedores con lo que se debe por lo que quedó recibido (8 de 10 kg)."""
        recepcion = self.recibir_a()
        resultados = correr_a_la_vez(self.corregir(self.ana, recepcion, self.l_fert, 2), self.pagar(), primera="a")
        exitos, errores = self.exitos_y_errores(resultados)
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertIsInstance(errores[0], ErrorDeCompras)
        self.assertEqual(errores[0].codigo, "sin_pago_pendiente")
        self.assertEqual((CorreccionRecepcion.objects.count(), Pago.objects.count()), (1, 0))
        self.assertEqual(self.lote_de_fertilizante().cantidad_disponible, D("8"))
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()

    def test_requisito_si_el_pago_gana_la_correccion_espera_y_se_rechaza_con_pago_registrado(self):
        """Requisitos especiales: el pago tiene la orden; la corrección espera, relee y ve el ``Pago``: ``pago_registrado``. Nada de la recepción cambia: lote en 10, un pago y un asiento de pago."""
        recepcion = self.recibir_a()
        resultados = correr_a_la_vez(self.pagar(), self.corregir(self.ana, recepcion, self.l_fert, 2), primera="a")
        exitos, errores = self.exitos_y_errores(resultados)
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertIsInstance(errores[0], ErrorDeCompras)
        self.assertEqual((errores[0].codigo, errores[0].datos["pago_id"]), ("pago_registrado", exitos[0].pk))
        self.assertEqual((CorreccionRecepcion.objects.count(), Pago.objects.count()), (0, 1))
        self.assertEqual(self.lote_de_fertilizante().cantidad_disponible, D("10"))
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()

    # --- 2. corrección contra consumo del lote ---

    def test_requisito_si_la_correccion_gana_el_consumo_espera_y_descuenta_del_lote_que_queda(self):
        """Requisitos especiales («impide corregir una línea mientras se consume el lote»): la corrección de 7 llega primero con el invernadero, la existencia y los lotes tomados; el consumo de 3 espera y
        descuenta de lo que queda (3): el lote termina en 0, sin faltante sin lote, con el tránsito en 7."""
        self.recibir_a()
        recepcion = DetalleRecepcion.objects.get(detalle_orden=self.l_fert).recepcion
        lote_ = self.lote_de_fertilizante()
        resultados = correr_a_la_vez(self.corregir(self.ana, recepcion, self.l_fert, 7), self.consumir(lote_, 3), primera="a")
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual(self.lote_de_fertilizante().cantidad_disponible, D("0"))
        self.assertEqual(self.transito(self.fertilizante), D("7"))
        self.assertFalse(LoteInsumo.objects.filter(insumo_invernadero=self.fertilizante, es_faltante_sin_lote=True).exists())
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()

    def test_requisito_si_el_consumo_gana_la_correccion_espera_relee_y_recibe_lo_que_queda_del_lote(self):
        """Requisitos especiales: el consumo de 7 llega primero (detenido antes de reevaluar las alertas, con sus lotes tomados); la corrección de 5 espera, relee el lote (3) y recibe
        ``supera_lo_corregible`` con ``maxima = 3``. El lote nunca queda negativo y no se asienta nada de más."""
        recepcion = self.recibir_a()
        lote_ = self.lote_de_fertilizante()
        asientos_antes = AsientoContable.objects.count()
        resultados = correr_a_la_vez(
            self.consumir(lote_, 7), self.corregir(self.ana, recepcion, self.l_fert, 5), primera="a", detener_antes_de=(alertas_de_stock, "reevaluar_alertas_del_insumo")
        )
        exitos, errores = self.exitos_y_errores(resultados)
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertEqual((errores[0].codigo, errores[0].datos["maxima"]), ("supera_lo_corregible", D("3")))
        self.assertEqual(self.lote_de_fertilizante().cantidad_disponible, D("3"))
        self.assertEqual((CorreccionRecepcion.objects.count(), AsientoContable.objects.count()), (0, asientos_antes))
        verificar_invariantes(self.fertilizante)

    # --- 3. dos correcciones de la misma línea ---

    def test_requisito_dos_correcciones_de_la_misma_linea_no_superan_lo_corregible(self):
        """Dos sesiones corrigen 6 de una línea con 10 recibidos: la segunda espera, relee y recibe ``supera_lo_corregible`` con ``maxima = 4``. Se registra una sola; el lote en 4, el tránsito en 6."""
        recepcion = self.recibir_a()
        resultados = correr_a_la_vez(self.corregir(self.ana, recepcion, self.l_fert, 6), self.corregir(self.gerente, recepcion, self.l_fert, 6), primera="a")
        exitos, errores = self.exitos_y_errores(resultados)
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertEqual((errores[0].codigo, errores[0].datos["maxima"]), ("supera_lo_corregible", D("4")))
        self.assertEqual(CorreccionRecepcion.objects.count(), 1)
        self.assertEqual((self.lote_de_fertilizante().cantidad_disponible, self.transito(self.fertilizante)), (D("4"), D("6")))
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()

    # --- 4. dos correcciones con asiento ---

    def test_requisito_dos_correcciones_de_recepciones_de_la_misma_orden_toman_numeros_de_asiento_correlativos(self):
        """Docs/patrones/asientos.md, sección 4: las correcciones de la recepción de A y la de B (de la misma orden) se ponen en fila en la orden: las dos se registran y sus asientos toman números
        correlativos y sin hueco (las dos recepciones tomaron el 1 y el 2)."""
        a = self.recibir_a()
        b = self.recibir_b()
        resultados = correr_a_la_vez(self.corregir(self.ana, a, self.l_fert, 2), self.corregir(self.ana, b, self.l_tomate, 1), primera="a", detener_antes_de=PARADA_ANTES_DEL_ASIENTO)
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual(CorreccionRecepcion.objects.count(), 2)
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2, 3, 4])
        verificar_invariantes_contables()

    # --- 5. el ejercicio va último ---

    def test_regla_el_ejercicio_va_ultimo_un_rival_que_lo_bloquea_antes_de_la_orden_forma_un_deadlock_con_la_correccion(self):
        """Docs/patrones/asientos.md, secciones 2 y 4, y D-86: la corrección toma sus filas de ``compras`` y **recién al final** el ejercicio. Un rival que bloquea el ejercicio ANTES de la orden (el orden
        prohibido) se cruza con ella: la corrección detenida antes del asiento tiene la orden; el rival toma el ejercicio y espera la orden; al seguir, la corrección pide el ejercicio: *deadlock*, y la
        base aborta a uno. Si la corrección bloqueara el ejercicio primero, no habría cruce y esta prueba fallaría."""
        recepcion = self.recibir_a()

        def rival_con_el_orden_prohibido():
            with transaction.atomic():
                EjercicioContable.objects.select_for_update(no_key=True).get(pk=self.abierto.pk)  # el ejercicio primero...
                OrdenCompra.objects.select_for_update(no_key=True).get(pk=self.orden.pk)  # ...y después la orden

        resultados = correr_a_la_vez(self.corregir(self.ana, recepcion, self.l_fert, 2), rival_con_el_orden_prohibido, primera="a", detener_antes_de=PARADA_ANTES_DEL_ASIENTO)
        deadlocks = [r for r in resultados.values() if isinstance(r, OperationalError) and "deadlock" in str(r).lower()]
        self.assertEqual(len(deadlocks), 1, resultados)

    # --- 6. dos emisiones del mismo reclamo ---

    def test_requisito_dos_emisiones_del_mismo_reclamo_emiten_una_sola_vez(self):
        """CMP-EMT-RCL (reclamo ya emitido): dos sesiones del Gerente emiten el mismo reclamo; la segunda espera el invernadero y el reclamo, relee y recibe ``reclamo_ya_emitido``. Un solo registro
        ``emision_reclamo``, el reclamo emitido una vez y la alerta resuelta."""
        self.recibir_con_inconveniente()
        reclamo = ReclamoProveedor.objects.get()
        emitir = lambda: reclamos.emitir_reclamo(self.gerente, reclamo.pk)
        resultados = correr_a_la_vez(emitir, emitir, primera="a")
        exitos, errores = self.exitos_y_errores(resultados)
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertIsInstance(errores[0], ErrorDeCompras)
        self.assertEqual(errores[0].codigo, "reclamo_ya_emitido")
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.EMISION_RECLAMO).count(), 1)
        reclamo.refresh_from_db()
        self.assertEqual((reclamo.gerente_id, reclamo.estado_reclamo), (self.gerente.pk, "abierto"))
        self.assertEqual(Alerta.objects.get().estado_alerta, Alerta.Estado.RESUELTA)

    def test_requisito_emitir_y_cerrar_a_la_vez_no_cierran_un_reclamo_sin_emitir(self):
        """Regla 1 de CMP-CRR-RCL: si el cierre llega a la vez que la emisión, espera y relee: o el reclamo ya está emitido y se cierra, o se rechaza con ``reclamo_sin_emitir``; nunca queda cerrado sin
        emitir (la restricción de la base lo respalda)."""
        self.recibir_con_inconveniente()
        reclamo = ReclamoProveedor.objects.get()
        resultados = correr_a_la_vez(lambda: reclamos.emitir_reclamo(self.gerente, reclamo.pk), lambda: reclamos.cerrar_reclamo(self.gerente, reclamo.pk), primera="a")
        reclamo.refresh_from_db()
        self.assertTrue(reclamo.emitido)
        errores = [r for r in resultados.values() if isinstance(r, Exception)]
        self.assertTrue(all(isinstance(e, ErrorDeCompras) for e in errores), resultados)
        self.assertIn((reclamo.estado_reclamo, len(errores)), {("cerrado", 0), ("abierto", 1)})
