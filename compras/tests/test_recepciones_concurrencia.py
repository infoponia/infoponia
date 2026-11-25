# Pruebas de concurrencia de la recepción y del cierre con faltante (CMP-04, paso 5). Fuente: docs/casos_de_uso/compras/recepcion.md («Requisitos especiales» de CMP-REG-RCP: «el
# control de concurrencia cumple tres funciones» y el de CMP-CRR-FLT), D-86 (el ejercicio se bloquea último), D-90 punto 5 (orden de bloqueo de compras), docs/patrones/bloqueos.md
# («Contabilidad: el ejercicio se bloquea último» y «compras») y docs/patrones/asientos.md, secciones 2 y 4.
#
# Dos hilos con ``correr_a_la_vez`` (``TransactionTestCase``: su ``flush`` vacía los datos de las migraciones, así que se aseguran de nuevo en cada prueba). Por defecto, la primera
# operación se detiene después de su primer registro de auditoría (con todos sus bloqueos de ``compras`` tomados y sin confirmar) y entonces arranca la otra. Las pruebas del ejercicio
# detienen a la recepción **justo antes de pedir el asiento** (``detener_antes_de=(asientos, "registrar_asiento_automatico")``): con lo suyo bloqueado y el ejercicio todavía sin tocar.
#
#   - 1 y 1b: dos recepciones de la misma línea no superan lo pendiente; las que caben juntas, sí, con números de asiento correlativos.
#   - 2: recibir contra cerrar con faltante de la misma línea (en los dos órdenes): el tránsito no se resta dos veces ni queda negativo.
#   - 3: recepción contra ``cerrar_ejercicio``: NO interfieren. ``cerrar_ejercicio`` bloquea solo el ejercicio «en cierre» y la recepción asienta siempre en el abierto (la fecha de la
#     recepción es hoy), así que no comparten ninguna fila: el cierre termina sin esperar y la recepción asienta después sin error. No es una prueba del orden de bloqueos.
#   - 4: recepción contra ``abrir_ejercicio_si_corresponde``: la apertura termina sin esperar a la recepción detenida; la recepción asienta en el ejercicio nuevo.
#   - 5: recepción contra una salida por consumo del mismo ``InsumoInvernadero`` (en los dos órdenes): el stock y el tránsito no pierden cambios.
#   - 6: dos recepciones de órdenes distintas: la segunda no espera a la primera hasta el asiento, y los números de asiento son correlativos y sin hueco.
#   - 7: el ejercicio va último: un rival que bloquea el ejercicio ANTES de las filas de la recepción forma un *deadlock* con ella. Si la recepción bloqueara el ejercicio primero, esa
#     prueba fallaría por no haber deadlock (docs/patrones/asientos.md, sección 4).

import threading
from datetime import timedelta
from unittest import mock

from django.db import OperationalError, transaction
from django.test import TransactionTestCase, override_settings, tag

from compras.errores import ErrorDeCompras
from compras.models import DetalleOrdenCompra, DetalleRecepcion, Recepcion
from compras.tests.base_recepciones import D, RecepcionBase, recepciones
from compras.tests.fabricas import EscenarioDeRecepcion
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import (
    PlanDeCuentasMixin,
    asegurar_plan_de_cuentas,
    ejercicio,
    ejercicio_abierto,
    verificar_invariantes_contables,
)
from core.tests.concurrencia import correr_a_la_vez
from inventario.models import InsumoInvernadero
from inventario.servicios import alertas_de_stock, stock
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    asegurar_datos_de_inventario,
    lote,
    origen_falso,
    verificar_invariantes,
)
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from maestros.tests.fabricas import asegurar_datos_de_maestros, asegurar_georef

PARADA_ANTES_DEL_ASIENTO = (servicio_de_asientos, "registrar_asiento_automatico")
Estado = EjercicioContable.Estado


@tag("concurrencia")
@override_settings(CORREO_CONFIGURADO=False)
class RecepcionesConcurrenciaTests(PlanDeCuentasMixin, ConDatosDeInventario, EscenarioDeRecepcion, TransactionTestCase):
    """El escenario de ``EscenarioDeRecepcion`` (Ana, Beto, el Gerente y la orden aprobada de A en Norte, B en Norte 2) con un ejercicio abierto ya puesto en marcha."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        asegurar_georef()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase lo vacía en cada prueba (docs/patrones/datos_de_migracion.md)
        self.armar()
        self.abierto = ejercicio_abierto()

    # --- auxiliares ---

    def linea(self, detalle, cantidad, vence=None):
        return recepciones.LineaRecibida(detalle.pk, [(D(str(cantidad)), vence)], [])

    def datos(self, lineas, orden=None, proveedor=None, invernadero=None):
        return recepciones.DatosDeRecepcion((orden or self.orden).pk, (proveedor or self.proveedor).pk, (invernadero or self.norte).pk, list(lineas))

    def recibir(self, actor, lineas, **kwargs):
        return lambda: recepciones.registrar_recepcion(actor, self.datos(lineas, **kwargs))

    def cerrar(self, actor, *detalles):
        return lambda: recepciones.cerrar_con_faltante(actor, [(d.pk, "El proveedor no repone.") for d in detalles])

    def transito(self, iin):
        return InsumoInvernadero.objects.get(pk=iin.pk).cant_transito_insumo

    def stock_de(self, iin):
        return stock.stock_actual_de([iin.pk])[iin.pk]

    def exitos_y_errores(self, resultados):
        exitos = [r for r in resultados.values() if not isinstance(r, Exception)]
        errores = [r for r in resultados.values() if isinstance(r, Exception)]
        return exitos, errores

    def correr_con_eventos(self, operacion_a, operacion_b):
        """``correr_a_la_vez`` con ``a`` detenida justo antes de pedir el asiento y con el orden de lo que pasó: ``(resultados, eventos)``. ``eventos`` anota ``"b_termino"`` cuando
        termina ``b`` y ``"a_reanuda"`` cuando ``a`` sigue después de la parada: si ``b`` terminó antes de que ``a`` siguiera, ``b`` no esperó a ``a`` (y ``a`` seguía sin confirmar)."""
        eventos = []
        original = servicio_de_asientos.registrar_asiento_automatico

        def anotar_reanudacion(*args, **kwargs):
            if threading.current_thread().name == "a":
                eventos.append("a_reanuda")
            return original(*args, **kwargs)

        def terminando(operacion, nombre):
            def corrida():
                try:
                    return operacion()
                finally:
                    eventos.append(f"{nombre}_termino")

            return corrida

        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=anotar_reanudacion):
            resultados = correr_a_la_vez(terminando(operacion_a, "a"), terminando(operacion_b, "b"), primera="a", detener_antes_de=PARADA_ANTES_DEL_ASIENTO)
        return resultados, eventos

    # --- 1. dos recepciones de la misma línea ---

    def test_requisito_dos_recepciones_de_la_misma_linea_no_superan_lo_que_falta_recibir(self):
        """CMP-REG-RCP «Requisitos especiales» (1.ª función): dos sesiones reciben 8 de una línea que pide 10; la segunda espera, relee y recibe ``supera_lo_pendiente`` con lo que falta ahora (2).
        Nunca se ingresa más de lo pedido: 8 recibidos, tránsito 2, un solo asiento."""
        resultados = correr_a_la_vez(self.recibir(self.ana, [self.linea(self.l_fert, 8, self.vence)]), self.recibir(self.ana, [self.linea(self.l_fert, 8, self.vence)]), primera="a")
        exitos, errores = self.exitos_y_errores(resultados)
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertIsInstance(errores[0], ErrorDeCompras)
        self.assertEqual((errores[0].codigo, errores[0].datos["pendiente"]), ("supera_lo_pendiente", D("2")))
        self.assertEqual(sum(d.cantidad_recibida_detalle for d in DetalleRecepcion.objects.filter(detalle_orden=self.l_fert)), D("8"))
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("8"), D("2")))
        self.assertEqual((Recepcion.objects.count(), AsientoContable.objects.count()), (1, 1))
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()

    def test_requisito_dos_recepciones_que_caben_juntas_se_registran_las_dos_con_asientos_correlativos(self):
        """Requisitos especiales: dos sesiones reciben 5 y 5 de una línea de 10: las dos se registran, la línea queda completa, el tránsito en 0 y los asientos con los números 1 y 2 sin hueco."""
        resultados = correr_a_la_vez(self.recibir(self.ana, [self.linea(self.l_fert, 5, self.vence)]), self.recibir(self.gerente, [self.linea(self.l_fert, 5, self.vence)]), primera="a")
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual(DetalleOrdenCompra.objects.get(pk=self.l_fert.pk).estado_detalle_orden, "completo")
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("10"), D("0")))
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2])
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()

    # --- 2. recibir contra cerrar con faltante ---

    def test_requisito_recibir_mientras_se_cierra_con_faltante_gana_la_recepcion_y_el_cierre_resta_lo_que_falta_despues(self):
        """CMP-REG-RCP y CMP-CRR-FLT «Requisitos especiales» (3.ª función): la recepción de 4 llega primero; el cierre espera, relee y cierra la línea por lo que falta ahora (6): el tránsito queda en
        0 (ni se resta de más ni queda negativo) y el stock en 4."""
        resultados = correr_a_la_vez(self.recibir(self.ana, [self.linea(self.l_fert, 4, self.vence)]), self.cerrar(self.ana, self.l_fert), primera="a")
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("4"), D("0")))
        self.assertEqual(DetalleOrdenCompra.objects.get(pk=self.l_fert.pk).estado_detalle_orden, "cerrado_con_faltante")
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()

    def test_requisito_cerrar_con_faltante_mientras_se_recibe_gana_el_cierre_y_la_recepcion_no_ingresa_nada(self):
        """CMP-CRR-FLT «Requisitos especiales»: el cierre llega primero; la recepción espera, ve la línea «cerrada con faltante» y recibe ``linea_no_pendiente``: no entra mercadería a una línea cerrada,
        el tránsito baja una sola vez (10 → 0) y no hay asiento."""
        resultados = correr_a_la_vez(self.cerrar(self.ana, self.l_fert), self.recibir(self.ana, [self.linea(self.l_fert, 4, self.vence)]), primera="a")
        self.assertIsInstance(resultados["b"], ErrorDeCompras)
        self.assertEqual(resultados["b"].codigo, "linea_no_pendiente")
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("0"), D("0")))
        self.assertEqual((Recepcion.objects.count(), AsientoContable.objects.count()), (0, 0))
        verificar_invariantes(self.fertilizante)

    def test_requisito_dos_cierres_de_la_misma_linea_restan_el_transito_una_sola_vez(self):
        """CMP-CRR-FLT «Requisitos especiales»: dos cierres simultáneos de la misma línea no restan dos veces el tránsito: el segundo espera, ve la línea cerrada y recibe ``linea_no_pendiente``."""
        resultados = correr_a_la_vez(self.cerrar(self.ana, self.l_fert), self.cerrar(self.gerente, self.l_fert), primera="a")
        exitos, errores = self.exitos_y_errores(resultados)
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertEqual(errores[0].codigo, "linea_no_pendiente")
        self.assertEqual(self.transito(self.fertilizante), D("0"))

    # --- 3. recepción contra cerrar_ejercicio: no interfieren ---

    def test_requisito_el_cierre_del_ejercicio_no_espera_a_la_recepcion_ni_la_afecta(self):
        """D-86 y ``cerrar_ejercicio`` (bloquea solo el ejercicio «en cierre»): con la recepción detenida antes del asiento, y con sus filas de ``compras`` tomadas y sin confirmar, el cierre del
        ejercicio en cierre **termina sin esperarla** (se comprueba que la recepción seguía sin confirmar cuando el cierre terminó); después la recepción asienta en el ejercicio abierto sin error. Y
        con el cierre ya hecho, otra recepción asienta igual en el abierto."""
        EjercicioContable.objects.filter(pk=self.abierto.pk).delete()  # el abierto lo recrea el escenario de esta prueba, después del «en cierre»
        hoy = self.hoy
        en_cierre = ejercicio(Estado.EN_CIERRE, hoy - timedelta(days=400))  # terminó hace más de un mes; el siguiente (abierto) arranca al día siguiente y cubre hoy
        abierto = ejercicio(Estado.ABIERTO, en_cierre.fecha_cierre_ejercicio + timedelta(days=1))
        visto = {}

        def cerrar_el_ejercicio():
            cerrado = ejercicios.cerrar_ejercicio(self.gerente, en_cierre.pk)
            visto["recepciones_confirmadas_al_cerrar"] = Recepcion.objects.count()
            return cerrado

        resultados, eventos = self.correr_con_eventos(self.recibir(self.ana, [self.linea(self.l_fert, 4, self.vence)]), cerrar_el_ejercicio)
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual(eventos, ["b_termino", "a_reanuda", "a_termino"])  # el cierre no esperó: terminó antes de que la recepción siguiera
        self.assertEqual(visto["recepciones_confirmadas_al_cerrar"], 0)  # y la recepción estaba de verdad detenida, sin confirmar
        self.assertEqual(EjercicioContable.objects.get(pk=en_cierre.pk).estado_ejercicio, Estado.CERRADO)
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento), (abierto.pk, 1))
        self.recibir(self.ana, [self.linea(self.l_fert, 6, self.vence)])()  # con el cierre ya hecho
        self.assertEqual(sorted(AsientoContable.objects.filter(ejercicio=abierto).values_list("numero_asiento", flat=True)), [1, 2])
        verificar_invariantes_contables()

    # --- 4. recepción contra abrir_ejercicio_si_corresponde ---

    def test_requisito_la_apertura_del_ejercicio_no_espera_a_la_recepcion_y_la_recepcion_asienta_en_el_nuevo(self):
        """D-84 punto 2 y docs/patrones/asientos.md, sección 2: con el ejercicio abierto vencido, la recepción detenida antes del asiento no tiene tomado el ejercicio, así que ``abrir_ejercicio_si_corresponde``
        termina sin esperarla (pasa el viejo a «en cierre» y crea el nuevo); la recepción sigue y asienta en el ejercicio nuevo con el número 1."""
        EjercicioContable.objects.filter(pk=self.abierto.pk).delete()
        viejo = ejercicio_abierto(self.hoy - timedelta(days=400))  # terminó hace más de un mes
        visto = {}

        def abrir():
            resultado = ejercicios.abrir_ejercicio_si_corresponde()
            visto["recepciones_confirmadas_al_abrir"] = Recepcion.objects.count()
            return resultado

        resultados, eventos = self.correr_con_eventos(self.recibir(self.ana, [self.linea(self.l_fert, 4, self.vence)]), abrir)
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual(eventos, ["b_termino", "a_reanuda", "a_termino"])
        self.assertEqual(visto["recepciones_confirmadas_al_abrir"], 0)
        self.assertEqual(EjercicioContable.objects.get(pk=viejo.pk).estado_ejercicio, Estado.EN_CIERRE)
        nuevo = EjercicioContable.objects.get(estado_ejercicio=Estado.ABIERTO)
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento), (nuevo.pk, 1))
        self.assertFalse(AsientoContable.objects.filter(ejercicio=viejo).exists())
        verificar_invariantes_contables()

    # --- 5. recepción contra consumo del mismo insumo ---

    def consumir(self, lote_, cantidad):
        """Una salida por consumo de ``produccion`` simulada con lo que ella hace: el invernadero bloqueado y ``registrar_salida_por_consumo`` (sin importar ``produccion``, regla A1)."""
        origen = origen_falso()

        def operacion():
            with transaction.atomic():
                bloquear_invernadero_activo(self.norte.pk)
                return stock.registrar_salida_por_consumo(self.fertilizante.pk, [(lote_.pk, D(str(cantidad)))], origen_id=origen.pk)

        return operacion

    def test_requisito_recepcion_y_consumo_del_mismo_insumo_no_pierden_cambios_si_gana_la_recepcion(self):
        """CMP-REG-RCP «Requisitos especiales» (2.ª función): la recepción de 4 llega primero con el invernadero y la existencia bloqueados; el consumo de 3 espera y después descuenta del lote: stock
        5 + 4 − 3 = 6 y tránsito 10 − 4 = 6; ninguno pisa el cambio del otro."""
        previo = lote(self.fertilizante, 5, vence=self.vence)
        resultados = correr_a_la_vez(self.recibir(self.ana, [self.linea(self.l_fert, 4, self.vence)]), self.consumir(previo, 3), primera="a")
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("6"), D("6")))
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()

    def test_requisito_recepcion_y_consumo_del_mismo_insumo_no_pierden_cambios_si_gana_el_consumo(self):
        """Lo mismo con el consumo primero (detenido antes de reevaluar las alertas, con sus lotes tomados): la recepción espera y suma encima: stock 6 y tránsito 6."""
        previo = lote(self.fertilizante, 5, vence=self.vence)
        resultados = correr_a_la_vez(
            self.consumir(previo, 3), self.recibir(self.ana, [self.linea(self.l_fert, 4, self.vence)]), primera="a", detener_antes_de=(alertas_de_stock, "reevaluar_alertas_del_insumo")
        )
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("6"), D("6")))
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()

    # --- 6. dos recepciones de órdenes distintas ---

    def test_requisito_dos_recepciones_de_ordenes_distintas_toman_numeros_de_asiento_correlativos_sin_esperarse_hasta_el_asiento(self):
        """docs/patrones/asientos.md, sección 4 («dos operaciones con asiento a la vez toman números distintos y sin hueco») y D-86: dos recepciones de órdenes distintas (de invernaderos distintos) no
        comparten ninguna fila de ``compras``: con la primera detenida antes del asiento, la segunda termina entera sin esperarla (le toca el 1) y la primera sigue (el 2). Sin hueco."""
        otra, linea_otra, _ = self.otra_orden(self.beto, self.sur, "Sustrato")
        propia = self.recibir(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        ajena = lambda: recepciones.registrar_recepcion(self.beto, recepciones.DatosDeRecepcion(otra.pk, linea_otra.proveedor.pk, self.sur.pk, [self.linea(linea_otra, 3)]))
        resultados, eventos = self.correr_con_eventos(propia, ajena)
        self.assertEqual(self.exitos_y_errores(resultados)[1], [])
        self.assertEqual(eventos, ["b_termino", "a_reanuda", "a_termino"])
        por_orden = {a.origen.recepcion.orden_id: a.numero_asiento for a in AsientoContable.objects.select_related("origen")}
        self.assertEqual(por_orden, {otra.pk: 1, self.orden.pk: 2})
        verificar_invariantes_contables()

    # --- 7. el ejercicio va último ---

    def test_regla_el_ejercicio_va_ultimo_un_rival_que_lo_bloquea_antes_forma_un_deadlock_con_la_recepcion(self):
        """docs/patrones/asientos.md, secciones 2 y 4, y D-86: la recepción toma sus filas de ``compras`` y **recién al final** el ejercicio. Un rival que bloquea el ejercicio ANTES de la línea (el orden
        prohibido) se cruza con ella: la recepción detenida antes del asiento tiene la línea; el rival toma el ejercicio y espera la línea; al seguir, la recepción pide el ejercicio: *deadlock*, y la base
        aborta a uno. Si la recepción bloqueara el ejercicio primero, no habría cruce y esta prueba fallaría."""

        def rival_con_el_orden_prohibido():
            with transaction.atomic():
                EjercicioContable.objects.select_for_update(no_key=True).get(pk=self.abierto.pk)  # el ejercicio primero...
                DetalleOrdenCompra.objects.select_for_update(no_key=True).get(pk=self.l_fert.pk)  # ...y después la fila de la recepción

        resultados = correr_a_la_vez(
            self.recibir(self.ana, [self.linea(self.l_fert, 4, self.vence)]), rival_con_el_orden_prohibido, primera="a", detener_antes_de=PARADA_ANTES_DEL_ASIENTO
        )
        deadlocks = [r for r in resultados.values() if isinstance(r, OperationalError) and "deadlock" in str(r).lower()]
        self.assertEqual(len(deadlocks), 1, resultados)
