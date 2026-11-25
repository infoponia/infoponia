# Pruebas de PROD-CNC-SMB · Concretar Siembra (PRD-01, paso 6; docs/casos_de_uso/produccion/siembra.md, «Decisiones de aplicación»).
#
# Servicios que se prueban (produccion/servicios/siembras.py), tomados del módulo dentro de cada prueba:
# - datos_de_concrecion(actor, orden_id): lo que propone el paso 4 (fecha de hoy, cantidades planificadas, reservas con su utilizada,
#   devuelta y consumida propuestas y los lotes de insumo que propone FEFO). No escribe.
# - resumen_de_concrecion(actor, orden_id, datos): valida todo y devuelve el resumen del paso 17. No escribe ni bloquea.
# - concretar_siembra(actor, orden_id, datos) -> Lote: lo mismo, bloquea, vuelve a verificar y escribe (todo o nada).
# - DatosDeConcrecion(fecha_efectiva=None, sembrado=None, motivo_diferencia="", ajustes=()): solo lo que difiere de lo propuesto.
#   `sembrado` es `((sector_id, plantines), ...)` (el sector que no figura toma lo planificado); `ajustes`, `AjusteDeInsumo(existencia_id,
#   utilizada=None, devuelta=None, lotes=None)` (`lotes`: `((lote_de_insumo_id, cantidad), ...)`, extensión 17b).
#
# CON-04a (D-92): la postcondición j (un asiento por consumo, Debe Productos en Proceso / Haber Insumos en Stock, con la fecha efectiva de la
# siembra) se prueba en `ConcretarSiembraAsientoTests`. Las precondiciones c y d (ejercicio y cuentas) NO se prueban: se cumplen solas (D-92 punto 2).
# Códigos y campos: sin_permiso; orden_no_pendiente (19a, con el estado actual); fecha_invalida (fecha_efectiva); cantidad_invalida
# (sembrado, utilizada, devuelta o lotes); sector_no_elegible (sembrado); motivo_largo (motivo_diferencia).
# Hecho en PRD-01: el precio de referencia es obligatorio y mayor que cero (INV-01), así que «precio de referencia vacío» no existe.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable, EjercicioContable, MovimientoContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Capataz, Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.tests.fabricas import ConDatosDeInventario, lote as lote_de_insumo, perezoso
from maestros.models import Alerta
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import crear_capataz_activo, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, Consumo, Lote, OcupacionSector, OrdenTrabajo, ReservaInsumo, Siembra
from produccion.tests.fabricas import insumo_adicional, invernadero_con_produccion, orden_de_siembra, orden_suelta, reservar

siembras = perezoso("produccion.servicios.siembras")
D = Decimal


def hoy():
    return timezone.localdate()


def rechazo(llamada):
    """Ejecuta `llamada()` y devuelve el `ErrorDeProduccion` que lanza; si no lanza ninguno, la prueba falla."""
    try:
        llamada()
    except ErrorDeProduccion as error:
        return error
    raise AssertionError("Se esperaba un ErrorDeProduccion y no se lanzó ninguno.")


class Base(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """Un invernadero completo (sectores de 100 agujeros, semilla con 1.000 unidades de precio 2,00) y una orden de 50 plantines."""

    def setUp(self):
        self.e = invernadero_con_produccion()
        self.orden = orden_de_siembra(self.e, plantines=50)

    def datos(self, **cambios):
        return siembras.DatosDeConcrecion(**cambios)

    def concretar(self, orden=None, actor=None, **cambios):
        return siembras.concretar_siembra(actor or self.e.capataz, (orden or self.orden).pk, self.datos(**cambios))

    def rechazo(self, orden=None, actor=None, **cambios):
        return rechazo(lambda: self.concretar(orden, actor, **cambios))

    def en_dos_sectores(self):
        """Una orden de 50 plantines repartida en dos sectores de germinación: 30 y 20. Devuelve `(orden, sector1, sector2)`."""
        sector2 = crear_sector(self.e.invernadero, "Germ 2", "germinacion", agujeros=100)
        orden = orden_de_siembra(self.e, plantines=50, agujeros=30, sector="germinacion")
        OcupacionSector.objects.create(orden=orden, sector=sector2, cant_agujeros_planificados=20)
        return orden, self.e.sectores["germinacion"], sector2

    def ajuste(self, existencia, **valores):
        return siembras.AjusteDeInsumo(existencia.pk, **valores)

    def adicional_reservado(self, cantidad="10", stock=50, **opciones):
        """Un insumo adicional con `stock` y `cantidad` reservada por la orden de la prueba."""
        adicional = insumo_adicional(self.e, stock=stock, **opciones)
        reservar(self.orden, adicional, cantidad)
        return adicional

    def nada_cambio(self):
        """La orden sigue «a realizar», sin lote, consumo, movimiento, notificación ni registro de auditoría de la concreción."""
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado_orden, "a_realizar")
        self.assertEqual(Lote.objects.count(), 0)
        self.assertEqual(Consumo.objects.count(), 0)
        self.assertEqual(MovimientoInsumo.objects.filter(tipo_movimiento="salida_por_consumo").count(), 0)
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="concrecion_siembra").exists())
        self.assertEqual(set(ReservaInsumo.objects.values_list("estado", flat=True)), {"activa"})
        self.assertEqual(sum(o.cant_agujeros_ocupados for o in OcupacionSector.objects.all()), 0)
        self.assertEqual(AsientoContable.objects.count(), 0)  # CON-04a: tampoco quedan asientos

    def disponible_de_la_semilla(self):
        return sum(l.cantidad_disponible for l in LoteInsumo.objects.filter(insumo_invernadero=self.e.existencia_semilla))


class PropuestaYResumenTests(Base):
    """Pasos 4 y 17: lo que propone el sistema y el resumen, sin escribir nada."""

    def test_paso_4_el_sistema_propone_hoy_las_cantidades_planificadas_y_las_cantidades_de_cada_reserva(self):
        """Regla «Valores propuestos»: fecha de hoy, cantidad planificada por sector, semilla utilizada = total, devuelta = reservada − utilizada,
        y los lotes de insumo propuestos con FEFO."""
        adicional = self.adicional_reservado("10")
        propuesta = siembras.datos_de_concrecion(self.e.capataz, self.orden.pk)
        self.assertEqual((propuesta.fecha_propuesta, propuesta.fecha_minima), (hoy(), self.orden.fecha_creacion_orden))
        self.assertEqual([(f.sector_id, f.planificados, f.propuesto) for f in propuesta.distribucion], [(self.e.sectores["germinacion"].pk, 50, 50)])
        semilla, extra = propuesta.reservas
        self.assertEqual((semilla.existencia_id, semilla.reservada, semilla.utilizada, semilla.devuelta, semilla.consumida), (self.e.existencia_semilla.pk, D("50"), D("50"), D("0"), D("50")))
        self.assertEqual((extra.existencia_id, extra.reservada, extra.utilizada, extra.devuelta, extra.consumida), (adicional.pk, D("10"), D("10"), D("0"), D("10")))
        self.assertEqual(semilla.lotes, [(self.e.lote_de_semillas.pk, D("50"))])
        self.assertEqual(semilla.resto, D("0"))

    def test_paso_17_el_resumen_trae_total_diferencia_distribucion_y_costo_y_no_escribe(self):
        """Paso 17: fecha efectiva, total sembrado frente al planificado, motivo, distribución real frente a la planificada, y
        lo utilizado, devuelto y consumido. No cambia nada."""
        orden, s1, s2 = self.en_dos_sectores()
        resumen = siembras.resumen_de_concrecion(
            self.e.capataz, orden.pk, self.datos(sembrado=((s1.pk, 30), (s2.pk, 5)), motivo_diferencia="Faltó turba")
        )
        self.assertEqual((resumen.total_sembrado, resumen.total_planificado, resumen.diferencia), (35, 50, 15))
        self.assertEqual(resumen.motivo_diferencia, "Faltó turba")
        self.assertEqual([(s.pk, plan, real) for s, plan, real in resumen.distribucion], [(s1.pk, 30, 30), (s2.pk, 20, 5)])
        semilla = resumen.reservas[0]
        self.assertEqual((semilla.utilizada, semilla.devuelta, semilla.consumida), (D("35"), D("15"), D("35")))
        self.assertEqual(resumen.costo, D("70.00"))  # 35 semillas × $2,00
        self.assertEqual(Lote.objects.count() + Consumo.objects.count() + Notificacion.objects.count(), 0)
        self.assertEqual(self.disponible_de_la_semilla(), D("1000"))

    def test_paso_17_el_resumen_rechaza_lo_mismo_que_la_concrecion(self):
        """El resumen valida todo: el mismo código y campo que `concretar_siembra`."""
        error = rechazo(lambda: siembras.resumen_de_concrecion(self.e.capataz, self.orden.pk, self.datos(fecha_efectiva=hoy() + timedelta(days=1))))
        self.assertEqual((error.codigo, error.campo), ("fecha_invalida", "fecha_efectiva"))


class ConcretarSiembraTests(Base):
    # ---- Precondiciones y 19a ----

    def test_pre_b_solo_el_capataz_asignado_a_la_orden_concreta(self):
        """Requisito especial «Solo el Capataz asignado a la orden puede concretarla»: otro Capataz, el Agrónomo, el Gerente o un
        Capataz inactivo reciben `sin_permiso`."""
        otro = crear_capataz_activo("otro.capataz@infoponia.com")
        for actor in (otro, self.e.agronomo, crear_gerente()):
            with self.subTest(actor=actor):
                self.assertEqual(self.rechazo(actor=actor).codigo, "sin_permiso")
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.assertEqual(self.rechazo().codigo, "sin_permiso")
        self.nada_cambio()

    def test_pre_b_una_orden_que_no_es_de_siembra_o_no_existe_da_404(self):
        """Solo se concretan órdenes de siembra: una entrega suelta o un id inexistente dan `Http404`."""
        entrega = orden_suelta(self.e.invernadero, "entrega")
        for orden_id in (entrega.pk, 999999):
            with self.subTest(orden=orden_id), self.assertRaises(Http404):
                siembras.concretar_siembra(self.e.capataz, orden_id, self.datos())

    def test_ext_19a_una_orden_que_ya_no_esta_a_realizar_informa_su_estado_y_no_cambia_nada(self):
        """Extensión 19a y garantía «una orden se concreta una única vez»: cancelada o ya concretada → `orden_no_pendiente`, con el
        estado actual en el mensaje."""
        cancelada = orden_de_siembra(self.e, plantines=5, sector="crecimiento", estado="cancelada")
        error = self.rechazo(orden=cancelada)
        self.assertEqual(error.codigo, "orden_no_pendiente")
        self.assertIn("cancelada", error.mensaje)
        self.concretar()
        error = self.rechazo()
        self.assertEqual(error.codigo, "orden_no_pendiente")
        self.assertIn("concretada", error.mensaje)
        self.assertEqual(Lote.objects.count(), 1)
        self.assertEqual(self.disponible_de_la_semilla(), D("950"))

    # ---- Fecha efectiva ----

    def test_ext_6a_y_6b_la_fecha_efectiva_va_de_la_creacion_de_la_orden_a_hoy_ambas_inclusive(self):
        """Extensiones 6a y 6b y regla «Fecha efectiva válida»: no posterior a hoy ni anterior a la creación de la orden; los extremos pasan."""
        OrdenTrabajo.objects.filter(pk=self.orden.pk).update(fecha_creacion_orden=hoy() - timedelta(days=5))
        for fecha in (hoy() + timedelta(days=1), hoy() - timedelta(days=6)):
            with self.subTest(fecha=fecha):
                error = self.rechazo(fecha_efectiva=fecha)
                self.assertEqual((error.codigo, error.campo), ("fecha_invalida", "fecha_efectiva"))
        self.nada_cambio()
        self.assertEqual(Siembra.objects.get(pk=self.concretar(fecha_efectiva=hoy() - timedelta(days=5)).siembra_id).fecha_siembra, hoy() - timedelta(days=5))

    def test_regla_la_fecha_efectiva_por_defecto_es_hoy(self):
        """Regla «Valores propuestos»: sin fecha, la fecha efectiva es la actual."""
        siembra = Siembra.objects.get(pk=self.concretar().siembra_id)
        self.assertEqual((siembra.fecha_siembra, siembra.fecha_resolucion_orden), (hoy(), hoy()))

    # ---- Cantidades sembradas ----

    def test_ext_8a_lo_sembrado_en_un_sector_no_supera_lo_planificado(self):
        """Extensión 8a: más de lo planificado en un sector → `cantidad_invalida` (campo sembrado), con la cantidad planificada."""
        error = self.rechazo(sembrado=((self.e.sectores["germinacion"].pk, 51),))
        self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", "sembrado"))
        self.assertIn("50", error.mensaje)

    def test_regla_no_se_admiten_sectores_fuera_de_la_distribucion_planificada(self):
        """Regla «Cantidad sembrada válida»: un sector que no es de la orden → `sector_no_elegible`."""
        self.assertEqual(self.rechazo(sembrado=((self.e.sectores["crecimiento"].pk, 5),)).codigo, "sector_no_elegible")

    def test_ext_10a_el_total_sembrado_en_cero_se_rechaza_y_la_orden_sigue_a_realizar(self):
        """Extensión 10a: sin plantines sembrados no se concreta; la orden queda «a realizar» hasta que el Agrónomo la cancele."""
        error = self.rechazo(sembrado=((self.e.sectores["germinacion"].pk, 0),))
        self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", "sembrado"))
        self.nada_cambio()

    def test_ext_9a_si_se_sembro_menos_queda_el_motivo_y_la_cantidad_planificada_no_cambia(self):
        """Extensión 9a y postcondición a: el motivo de la diferencia se guarda; `cant_plantines_siembra` (lo planificado) no cambia."""
        lote = self.concretar(sembrado=((self.e.sectores["germinacion"].pk, 40),), motivo_diferencia="Se rompió una bandeja")
        siembra = Siembra.objects.get(pk=lote.siembra_id)
        self.assertEqual((siembra.motivo_diferencia_siembra, siembra.cant_plantines_siembra, lote.cantidad_inicial), ("Se rompió una bandeja", 50, 40))

    def test_ext_9a_el_motivo_se_guarda_solo_si_hubo_diferencia_y_pasa_de_300_se_rechaza(self):
        """Regla del modelo (`motivo_diferencia_siembra`): solo si el total sembrado fue menor; hasta 300 caracteres."""
        siembra = Siembra.objects.get(pk=self.concretar(motivo_diferencia="no hay diferencia").siembra_id)
        self.assertEqual(siembra.motivo_diferencia_siembra, "")
        otra = orden_de_siembra(self.e, plantines=5, sector="crecimiento")
        error = self.rechazo(orden=otra, sembrado=((self.e.sectores["crecimiento"].pk, 1),), motivo_diferencia="x" * 301)
        self.assertEqual((error.codigo, error.campo), ("motivo_largo", "motivo_diferencia"))

    # ---- Postcondiciones a, b, c, d ----

    def test_post_a_la_orden_queda_concretada_con_su_fecha_de_resolucion_y_de_siembra(self):
        """Postcondición a: «a realizar» → «concretada», con fecha de resolución = hoy y fecha de siembra = la efectiva."""
        OrdenTrabajo.objects.filter(pk=self.orden.pk).update(fecha_creacion_orden=hoy() - timedelta(days=3))
        self.concretar(fecha_efectiva=hoy() - timedelta(days=2))
        siembra = Siembra.objects.get(pk=self.orden.pk)
        self.assertEqual(
            (siembra.estado_orden, siembra.fecha_resolucion_orden, siembra.fecha_siembra),
            ("concretada", hoy(), hoy() - timedelta(days=2)),
        )

    def test_post_b_el_lote_nace_en_germinacion_con_lo_sembrado_y_la_suma_de_los_montos_como_costo(self):
        """Postcondición b: lote «activo» con cantidad inicial = actual = total sembrado, de la siembra, del invernadero y de la etapa de
        Germinación del ciclo; costo acumulado = suma de los montos de consumo (semilla 40 × $2,00 + adicional 2 × $4,00)."""
        adicional = self.adicional_reservado("2")
        lote = self.concretar(sembrado=((self.e.sectores["germinacion"].pk, 40),))
        lote = Lote.objects.select_related("etapa__tipo_etapa").get(pk=lote.pk)
        self.assertEqual((lote.estado_lote, lote.cantidad_inicial, lote.cantidad_actual), ("activo", 40, 40))
        self.assertEqual((lote.siembra_id, lote.invernadero_id, lote.etapa.tipo_etapa.codigo), (self.orden.pk, self.e.invernadero.pk, "germinacion"))
        self.assertEqual(lote.costo_acumulado, D("88.00"))
        self.assertEqual(lote.codigo, f"L-{lote.pk}")

    def test_post_b_el_costo_es_la_suma_de_los_montos_ya_redondeados(self):
        """Regla «Costo del lote» y costo_del_lote.md: 0,5 kg × $3,33 = 1,665 → 1,67 (ROUND_HALF_UP) y la semilla 50 × $2,00; el costo
        es 101,67, la suma de lo que se ve en cada consumo."""
        self.adicional_reservado("0.5", stock=5, precio="3.33")
        lote = self.concretar()
        self.assertEqual(sorted(Consumo.objects.values_list("monto_consumo", flat=True)), [D("1.67"), D("100.00")])
        self.assertEqual(lote.costo_acumulado, D("101.67"))

    def test_post_c_las_ocupaciones_guardan_lo_sembrado_y_solo_las_que_sembraron_van_al_lote(self):
        """Postcondición c: ocupados = sembrado en cada sector; los planificados no cambian; con al menos un plantín quedan asociadas
        al lote; las de cero se conservan, con cero ocupados y sin lote."""
        orden, s1, s2 = self.en_dos_sectores()
        lote = self.concretar(orden, sembrado=((s1.pk, 25), (s2.pk, 0)))
        o1, o2 = (OcupacionSector.objects.get(orden=orden, sector=s) for s in (s1, s2))
        self.assertEqual((o1.cant_agujeros_planificados, o1.cant_agujeros_ocupados, o1.lote_id), (30, 25, lote.pk))
        self.assertEqual((o2.cant_agujeros_planificados, o2.cant_agujeros_ocupados, o2.lote_id), (20, 0, None))

    def test_post_d_los_agujeros_comprometidos_se_liberan_y_los_ocupados_son_los_sembrados(self):
        """Postcondición d y regla «Liberación de agujeros»: comprometidos − planificados; ocupados = sembrados (libres = total − ocupados)."""
        sector = self.e.sectores["germinacion"]
        antes = api_sectores.agujeros_de([sector])[sector.pk]
        self.assertEqual((antes.comprometidos, antes.ocupados), (50, 0))
        self.concretar(sembrado=((sector.pk, 40),))
        despues = api_sectores.agujeros_de([sector])[sector.pk]
        self.assertEqual((despues.comprometidos, despues.ocupados, despues.libres), (0, 40, 60))

    # ---- Postcondiciones e y f: reservas ----

    def test_post_e_la_semilla_queda_con_utilizada_igual_al_total_y_consumida(self):
        """Postcondición e: utilizada = total sembrado (40), devuelta propuesta = 10, estado «consumida». Consumido = reservada − devuelta."""
        self.concretar(sembrado=((self.e.sectores["germinacion"].pk, 40),))
        reserva = ReservaInsumo.objects.get(orden=self.orden)
        self.assertEqual((reserva.estado, reserva.cantidad_utilizada, reserva.cantidad_devuelta), ("consumida", D("40"), D("10")))
        self.assertEqual(Consumo.objects.get(siembra=self.orden).cant_consumo, D("40"))

    def test_regla_cantidad_devuelta_el_capataz_puede_reducirla_si_algo_se_daño(self):
        """Regla «Cantidad devuelta» y paso 14: con 4 devueltas de las 10 sobrantes, se consumen 46 (reservada 50 − devuelta 4)."""
        self.concretar(sembrado=((self.e.sectores["germinacion"].pk, 40),), ajustes=(self.ajuste(self.e.existencia_semilla, devuelta=D("4")),))
        reserva = ReservaInsumo.objects.get(orden=self.orden)
        self.assertEqual((reserva.cantidad_utilizada, reserva.cantidad_devuelta), (D("40"), D("4")))
        self.assertEqual(Consumo.objects.get(siembra=self.orden).cant_consumo, D("46"))
        self.assertEqual(self.disponible_de_la_semilla(), D("954"))

    def test_ext_15a_la_devuelta_no_supera_la_reservada_menos_la_utilizada(self):
        """Extensión 15a: con 40 utilizadas de 50, se devuelven como máximo 10 (`cantidad_invalida`, campo devuelta, con el máximo)."""
        error = self.rechazo(
            sembrado=((self.e.sectores["germinacion"].pk, 40),), ajustes=(self.ajuste(self.e.existencia_semilla, devuelta=D("11")),)
        )
        self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", "devuelta"))
        self.assertIn("10", error.mensaje)
        self.assertEqual(self.rechazo(ajustes=(self.ajuste(self.e.existencia_semilla, devuelta=D("-1")),)).codigo, "cantidad_invalida")
        self.nada_cambio()

    def test_post_f_un_adicional_con_utilizada_y_devuelta_propuestas_queda_consumido(self):
        """Postcondición f: un insumo adicional sin cambios usa lo reservado: utilizada = reservada, devuelta 0, «consumida»."""
        adicional = self.adicional_reservado("10")
        self.concretar()
        reserva = ReservaInsumo.objects.get(orden=self.orden, insumo_invernadero=adicional)
        self.assertEqual((reserva.estado, reserva.cantidad_utilizada, reserva.cantidad_devuelta), ("consumida", D("10"), D("0")))

    def test_post_f_un_adicional_usado_en_parte_devuelve_el_sobrante(self):
        """Pasos 12 a 15: con 4 utilizadas de 10 reservadas, la devuelta propuesta es 6 y se consumen 4."""
        adicional = self.adicional_reservado("10")
        self.concretar(ajustes=(self.ajuste(adicional, utilizada=D("4")),))
        reserva = ReservaInsumo.objects.get(orden=self.orden, insumo_invernadero=adicional)
        self.assertEqual((reserva.cantidad_utilizada, reserva.cantidad_devuelta, reserva.estado), (D("4"), D("6"), "consumida"))
        self.assertEqual(Consumo.objects.get(siembra=self.orden, insumo_invernadero=adicional).cant_consumo, D("4"))

    def test_ext_12a_un_adicional_no_utilizado_con_todo_devuelto_cancela_su_reserva_y_no_deja_consumo(self):
        """Extensión 12a y regla «Resolución de reservas»: utilizada 0 y devuelta = reservada → consumida 0 → la reserva queda
        «cancelada» (con lo cargado) y no hay consumo ni movimiento ni descuento de stock."""
        adicional = self.adicional_reservado("10")
        self.concretar(ajustes=(self.ajuste(adicional, utilizada=D("0")),))
        reserva = ReservaInsumo.objects.get(orden=self.orden, insumo_invernadero=adicional)
        self.assertEqual((reserva.estado, reserva.cantidad_utilizada, reserva.cantidad_devuelta), ("cancelada", D("0"), D("10")))
        self.assertFalse(Consumo.objects.filter(insumo_invernadero=adicional).exists())
        self.assertFalse(MovimientoInsumo.objects.filter(lote_insumo__insumo_invernadero=adicional, tipo_movimiento="salida_por_consumo").exists())
        self.assertEqual(sum(l.cantidad_disponible for l in LoteInsumo.objects.filter(insumo_invernadero=adicional)), D("50"))

    def test_ext_13a_la_utilizada_de_un_adicional_no_supera_la_reservada(self):
        """Extensión 13a: 11 utilizadas de 10 reservadas → `cantidad_invalida` (campo utilizada), con la cantidad reservada."""
        adicional = self.adicional_reservado("10")
        error = self.rechazo(ajustes=(self.ajuste(adicional, utilizada=D("11")),))
        self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", "utilizada"))
        self.assertIn("10", error.mensaje)
        self.nada_cambio()

    def test_regla_ninguna_reserva_de_una_orden_concretada_queda_activa(self):
        """Regla «Resolución de reservas»: todas pasan a «consumida» o a «cancelada»."""
        self.adicional_reservado("10")
        self.concretar()
        self.assertFalse(ReservaInsumo.objects.filter(orden=self.orden, estado="activa").exists())

    # ---- Postcondiciones g e i: lotes de insumo y movimientos ----

    def test_post_g_i_el_stock_sale_de_los_lotes_con_fefo_un_movimiento_por_lote_con_la_fecha_efectiva(self):
        """Postcondiciones g e i y regla «Lotes de salida»: FEFO (sale primero lo que vence primero); un movimiento «salida por consumo»
        por lote, originado en el consumo, con la fecha efectiva."""
        OrdenTrabajo.objects.filter(pk=self.orden.pk).update(fecha_creacion_orden=hoy() - timedelta(days=2))
        primero = lote_de_insumo(self.e.existencia_semilla, 30, vence=hoy() + timedelta(days=10))
        self.concretar(fecha_efectiva=hoy() - timedelta(days=1))
        consumo = Consumo.objects.get(siembra=self.orden, insumo_invernadero=self.e.existencia_semilla)
        movimientos = MovimientoInsumo.objects.filter(origen=consumo)
        self.assertEqual({m.lote_insumo_id: m.cantidad for m in movimientos}, {primero.pk: D("30"), self.e.lote_de_semillas.pk: D("20")})
        self.assertEqual({m.tipo_movimiento for m in movimientos}, {"salida_por_consumo"})
        self.assertEqual({timezone.localtime(m.fecha).date() for m in movimientos}, {hoy() - timedelta(days=1)})
        self.assertEqual(self.disponible_de_la_semilla(), D("980"))

    def test_ext_17b_el_capataz_puede_elegir_los_lotes_de_los_que_sale(self):
        """Extensión 17b: sale del lote elegido (no del que propone FEFO)."""
        elegido = lote_de_insumo(self.e.existencia_semilla, 200, vence=hoy() + timedelta(days=500))
        self.concretar(ajustes=(self.ajuste(self.e.existencia_semilla, lotes=((elegido.pk, D("50")),)),))
        self.assertEqual(LoteInsumo.objects.get(pk=elegido.pk).cantidad_disponible, D("150"))
        self.assertEqual(LoteInsumo.objects.get(pk=self.e.lote_de_semillas.pk).cantidad_disponible, D("1000"))

    def test_ext_17b_la_cantidad_de_un_lote_no_supera_su_disponible_ni_el_total_la_consumida(self):
        """Extensión 17b: cada lote aporta como máximo lo que tiene y el total no pasa de lo consumido; un lote de otra existencia no vale."""
        chico = lote_de_insumo(self.e.existencia_semilla, 10, vence=hoy() + timedelta(days=500))
        otro_insumo = insumo_adicional(self.e, "Otro", stock=5)
        ajeno = LoteInsumo.objects.filter(insumo_invernadero=otro_insumo).first()
        for lotes in (((chico.pk, D("11")),), ((self.e.lote_de_semillas.pk, D("45")), (chico.pk, D("10"))), ((ajeno.pk, D("5")),)):
            with self.subTest(lotes=lotes):
                error = self.rechazo(ajustes=(self.ajuste(self.e.existencia_semilla, lotes=lotes),))
                self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", "lotes"))
        self.nada_cambio()

    def test_ext_17b_lo_que_los_lotes_elegidos_no_cubren_sale_del_faltante_sin_lote(self):
        """Extensión 17b, punto 2: lo que los lotes indicados no cubren sale del lote «faltante sin lote» (el total de lo indicado no
        pasa de lo consumido)."""
        chico = lote_de_insumo(self.e.existencia_semilla, 30, vence=hoy() + timedelta(days=500))
        self.concretar(ajustes=(self.ajuste(self.e.existencia_semilla, lotes=((chico.pk, D("30")),)),))
        self.assertEqual(LoteInsumo.objects.get(insumo_invernadero=self.e.existencia_semilla, es_faltante_sin_lote=True).cantidad_disponible, D("-20"))
        self.assertEqual(LoteInsumo.objects.get(pk=chico.pk).cantidad_disponible, D("0"))

    def test_ext_19b_si_los_lotes_no_cubren_el_resto_sale_del_faltante_sin_lote_y_se_activa_la_alerta(self):
        """Extensión 19b y postcondiciones g y p: la concreción NO se rechaza; el resto sale del lote «faltante sin lote» (que queda
        negativo) y se activa la alerta «stock inconsistente» para el Agrónomo."""
        adicional = self.adicional_reservado("10", stock=50)
        LoteInsumo.objects.filter(insumo_invernadero=adicional, es_faltante_sin_lote=False).update(cantidad_disponible=4)
        self.concretar()
        faltante = LoteInsumo.objects.get(insumo_invernadero=adicional, es_faltante_sin_lote=True)
        self.assertEqual(faltante.cantidad_disponible, D("-6"))
        self.assertEqual(LoteInsumo.objects.get(insumo_invernadero=adicional, es_faltante_sin_lote=False).cantidad_disponible, D("0"))
        alerta = Alerta.objects.get(tipo_alerta="inv_stock_inconsistente", clave_estado=f"insumo:{adicional.pk}")
        self.assertEqual((alerta.estado_alerta, alerta.agronomo_id), ("activa", self.e.agronomo.pk))

    def test_ext_19b_un_faltante_sin_ningun_lote_con_stock_igual_se_concreta(self):
        """Extensión 19b: aun sin ningún lote con stock, el consumo sale entero del faltante y la concreción se registra."""
        adicional = self.adicional_reservado("10", stock=50)
        LoteInsumo.objects.filter(insumo_invernadero=adicional, es_faltante_sin_lote=False).update(cantidad_disponible=0)
        self.concretar()
        self.assertEqual(LoteInsumo.objects.get(insumo_invernadero=adicional, es_faltante_sin_lote=True).cantidad_disponible, D("-10"))
        self.assertEqual(Siembra.objects.get(pk=self.orden.pk).estado_orden, "concretada")

    # ---- Postcondición h: consumos y bitácora ----

    def test_post_h_un_consumo_por_reserva_consumida_con_su_monto_y_su_bitacora(self):
        """Postcondición h y D-51 puntos 2 y 8: un consumo (hijo de bitácora, evento «siembra») por reserva con consumido > 0, con la cantidad,
        el monto (consumido × precio de referencia), la fecha efectiva, el Capataz como responsable, el lote, la etapa, el invernadero y
        los sectores donde se sembró al menos una planta; la descripción es legible."""
        orden, s1, s2 = self.en_dos_sectores()
        self.concretar(orden, sembrado=((s1.pk, 30), (s2.pk, 0)))
        consumo = Consumo.objects.select_related("lote", "etapa__tipo_etapa").get(siembra=orden, insumo_invernadero=self.e.existencia_semilla)
        self.assertEqual((consumo.cant_consumo, consumo.monto_consumo, consumo.fecha_consumo), (D("30"), D("60.00"), hoy()))
        self.assertEqual((consumo.tipo_evento, consumo.responsable_id, consumo.fecha_bitacora), ("siembra", self.e.capataz.pk, hoy()))
        self.assertEqual((consumo.lote.siembra_id, consumo.etapa.tipo_etapa.codigo, consumo.invernadero_id), (orden.pk, "germinacion", self.e.invernadero.pk))
        self.assertEqual(list(consumo.sectores.values_list("pk", flat=True)), [s1.pk])
        self.assertIn(orden.codigo, consumo.descripcion_evento)
        self.assertIn(self.e.semilla.nombre_insumo, consumo.descripcion_evento)
        self.assertIn("30", consumo.descripcion_evento)

    def test_regla_el_consumo_se_crea_antes_que_sus_movimientos_y_todos_lo_apuntan(self):
        """D-52 punto 5: cada movimiento de stock de la concreción tiene como origen el consumo de su insumo; el consumo es un documento de origen."""
        self.adicional_reservado("10")
        self.concretar()
        for consumo in Consumo.objects.all():
            movimientos = MovimientoInsumo.objects.filter(origen=consumo)
            self.assertTrue(movimientos.exists())
            self.assertEqual({m.lote_insumo.insumo_invernadero_id for m in movimientos}, {consumo.insumo_invernadero_id})
        self.assertEqual(Bitacora.objects.filter(tipo_evento="siembra").count(), 2)

    def test_regla_14_el_monto_del_consumo_queda_fijo_aunque_el_precio_cambie(self):
        """Regla 14 de 8.9 y «Monto de consumo»: el monto se calculó con el precio al concretar y no cambia si el precio cambia después."""
        self.concretar()
        InsumoInvernadero.objects.filter(pk=self.e.existencia_semilla.pk).update(referencia_precio=D("99.00"))
        self.assertEqual(Consumo.objects.get(siembra=self.orden).monto_consumo, D("100.00"))

    # ---- Postcondición k: notificación ----

    def test_post_k_el_agronomo_que_planifico_recibe_las_diferencias_y_el_motivo(self):
        """Postcondición k: aviso al Agrónomo que planificó, con la diferencia entre lo planificado y lo sembrado y el motivo."""
        lote = self.concretar(sembrado=((self.e.sectores["germinacion"].pk, 40),), motivo_diferencia="Se rompió una bandeja")
        aviso = Notificacion.objects.get(destinatario=self.e.agronomo)
        self.assertIn(self.orden.codigo, aviso.titulo)
        for texto in (lote.codigo, "40", "50", "Se rompió una bandeja"):
            self.assertIn(texto, aviso.detalle)
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_post_k_si_planifico_infoponia_no_se_notifica_a_nadie(self):
        """Si la orden la planificó InfoPonia (sin Agrónomo), no hay a quién avisar y la concreción se registra igual."""
        orden = orden_de_siembra(self.e, plantines=5, sector="crecimiento", agronomo=False)
        self.concretar(orden)
        self.assertEqual(Notificacion.objects.count(), 0)

    # ---- Postcondiciones l, m, n y o: auditoría ----

    def test_post_l_m_n_o_un_solo_registro_con_todo_lo_tocado_y_los_cambios_de_la_orden(self):
        """Postcondiciones l a o (D-36, un registro por caso de uso): `concrecion_siembra` con la orden, el lote, las ocupaciones, los
        sectores, las reservas, los insumos del invernadero, los lotes de insumo, los consumos y los movimientos como afectados; los
        cambios de estado, fecha de resolución, fecha de siembra y motivo; y el cambio de agujeros de cada sector."""
        self.adicional_reservado("10")
        lote = self.concretar(sembrado=((self.e.sectores["germinacion"].pk, 40),), motivo_diferencia="Poca semilla")
        registro = RegistroAuditoria.objects.get(accion="concrecion_siembra")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="concrecion_siembra").count(), 1)
        self.assertEqual(registro.usuario_id, self.e.capataz.pk)
        modelos = {a["modelo"] for a in registro.afectados}
        esperados = {
            "produccion.siembra", "produccion.lote", "produccion.ocupacionsector", "maestros.sectorproduccion", "produccion.reservainsumo",
            "inventario.insumoinvernadero", "inventario.loteinsumo", "produccion.consumo", "inventario.movimientoinsumo",
        }
        self.assertLessEqual(esperados, modelos)
        self.assertIn(("produccion.lote", lote.pk), {(a["modelo"], a["id"]) for a in registro.afectados})
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["estado"], {"antes": "a_realizar", "despues": "concretada"})
        self.assertEqual(cambios["fecha_siembra"]["despues"], f"{hoy():%d/%m/%Y}")
        self.assertEqual(cambios["motivo_diferencia_siembra"]["despues"], "Poca semilla")
        sector = self.e.sectores["germinacion"].nombre_sector
        self.assertEqual(cambios["agujeros_comprometidos"], {"antes": [f"{sector}: 50"], "despues": [f"{sector}: 0"]})
        self.assertEqual(cambios["agujeros_ocupados"], {"antes": [f"{sector}: 0"], "despues": [f"{sector}: 40"]})

    # ---- Todo o nada ----

    def test_garantia_un_error_en_el_medio_no_deja_nada_cambiado(self):
        """Garantías mínimas y D-22: si algo falla después de escribir (el aviso al Agrónomo), la orden sigue «a realizar», las reservas
        «activas», el stock igual y no queda lote, consumo, movimiento ni registro de auditoría."""
        self.adicional_reservado("10")
        with mock.patch("core.notificaciones.notificar", side_effect=RuntimeError("falla del aviso")):
            with self.assertRaises(RuntimeError):
                self.concretar()
        self.nada_cambio()
        self.assertEqual(self.disponible_de_la_semilla(), D("1000"))

    def test_garantia_un_rechazo_no_cambia_el_stock_ni_los_agujeros(self):
        """Garantías mínimas: con un rechazo, los agujeros comprometidos y el stock quedan como estaban."""
        self.rechazo(sembrado=((self.e.sectores["germinacion"].pk, 51),))
        sector = self.e.sectores["germinacion"]
        self.assertEqual(api_sectores.agujeros_de([sector])[sector.pk].comprometidos, 50)
        self.assertEqual(self.disponible_de_la_semilla(), D("1000"))


class ConcretarSiembraAsientoTests(Base):
    """CON-04a · PROD-CNC-SMB postcondición j (D-92 puntos 2 a 6 y 9, D-86): un asiento por consumo, originado en el consumo, Debe Productos en
    Proceso / Haber Insumos en Stock por `monto_consumo`, con la fecha efectiva de la siembra."""

    def lineas(self, asiento):
        """Los movimientos del asiento como `[(cuenta, tipo, importe)]`, ordenados."""
        return sorted(
            (m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento)
            for m in MovimientoContable.objects.filter(asiento=asiento).select_related("cuenta")
        )

    def test_post_j_un_asiento_por_consumo_productos_en_proceso_contra_insumos_en_stock(self):
        """Postcondición j y D-92 puntos 5 y 6: la semilla (50 × $2,00) y el adicional (10 × $4,00) tienen cada uno su consumo y su asiento, con el
        consumo como origen, el monto del consumo como importe y la fecha de hoy. No hay ejercicio de antes: lo abre la autorrecuperación (H9)."""
        self.adicional_reservado("10")
        self.concretar()
        consumos = list(Consumo.objects.order_by("pk"))
        self.assertEqual({c.monto_consumo for c in consumos}, {D("100.00"), D("40.00")})
        self.assertEqual(AsientoContable.objects.count(), 2)
        for consumo in consumos:
            asiento = AsientoContable.objects.get(origen_id=consumo.pk)
            self.assertEqual(asiento.fecha_asiento, hoy())
            esperado = [(cuentas.INSUMOS_EN_STOCK, HABER, consumo.monto_consumo), (cuentas.PRODUCTOS_EN_PROCESO, DEBE, consumo.monto_consumo)]
            self.assertEqual(self.lineas(asiento), sorted(esperado))
        self.assertEqual(EjercicioContable.objects.get().ultimo_numero_asiento, 2)
        verificar_invariantes_contables()

    def test_post_j_un_consumo_de_cero_pesos_no_tiene_asiento_y_no_falla(self):
        """D-92 punto 5 y H11: un consumo cuyo monto redondea a $0,00 (0,4 kg a $0,01) se registra y no genera asiento; el de la semilla sí."""
        adicional = insumo_adicional(self.e, stock=50, unidad="kg", precio="0.01")
        reservar(self.orden, adicional, "0.4")
        self.concretar()
        consumo_cero = Consumo.objects.get(siembra=self.orden, insumo_invernadero=adicional)
        self.assertEqual(consumo_cero.monto_consumo, D("0.00"))
        self.assertFalse(AsientoContable.objects.filter(origen_id=consumo_cero.pk).exists())
        self.assertEqual(AsientoContable.objects.count(), 1)
        self.assertEqual(Siembra.objects.get(pk=self.orden.pk).estado_orden, "concretada")
        verificar_invariantes_contables()

    def test_post_j_la_fecha_del_asiento_es_la_efectiva_de_la_siembra_no_la_de_hoy(self):
        """D-92 punto 4 y H10: una siembra con fecha efectiva de hace 3 días (orden creada hace 5) asienta con esa fecha, en el ejercicio que la contiene."""
        abierto = ejercicio_abierto(hoy() - timedelta(days=30))
        orden = orden_de_siembra(self.e, plantines=10, sector="crecimiento", dias=-5)
        self.concretar(orden, fecha_efectiva=hoy() - timedelta(days=3))
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.fecha_asiento, asiento.ejercicio_id), (hoy() - timedelta(days=3), abierto.pk))
        self.assertNotIn("Fecha del hecho", asiento.descripcion_asiento)
        verificar_invariantes_contables()

    def test_d102_una_fecha_en_un_ejercicio_cerrado_no_rechaza_y_el_asiento_va_al_abierto_con_la_aclaracion(self):
        """D-102 (D-84 punto 5): si la fecha efectiva cae en un ejercicio ya cerrado, la siembra se concreta igual y el asiento va al abierto, con
        la fecha de hoy y la aclaración de la fecha real."""
        ejercicio(EjercicioContable.Estado.CERRADO, hoy() - timedelta(days=60), hoy() - timedelta(days=1))
        abierto = ejercicio_abierto(hoy())
        orden = orden_de_siembra(self.e, plantines=10, sector="crecimiento", dias=-5)
        fecha = hoy() - timedelta(days=3)
        self.concretar(orden, fecha_efectiva=fecha)
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.fecha_asiento, asiento.ejercicio_id), (hoy(), abierto.pk))
        self.assertIn(f"Fecha del hecho: {fecha:%d/%m/%Y}", asiento.descripcion_asiento)
        self.assertEqual(Siembra.objects.get(pk=orden.pk).fecha_siembra, fecha)
        verificar_invariantes_contables()

    def test_post_j_la_ficha_del_asiento_muestra_el_consumo_de_la_siembra_sin_enlace(self):
        """CON-04a, «enlace al origen»: la ficha del libro nombra el consumo de la siembra y no lleva dirección (el Contador no abre la orden)."""
        from contabilidad import extensiones as extensiones_de_contabilidad

        self.concretar()
        texto, url = extensiones_de_contabilidad.enlace_de_origen(AsientoContable.objects.get().origen)
        self.assertEqual(texto, f"Consumo · {Consumo.objects.get(siembra=self.orden).descripcion_evento}")
        self.assertIsNone(url)

    def test_post_j_la_descripcion_del_asiento_es_la_del_consumo(self):
        """El asiento lleva la descripción legible del consumo («Siembra OT-0004: Semilla…, 50 unidades»), que es lo que lee el Contador en el libro."""
        self.concretar()
        consumo = Consumo.objects.get(siembra=self.orden)
        self.assertEqual(AsientoContable.objects.get(origen_id=consumo.pk).descripcion_asiento, consumo.descripcion_evento)

    def test_post_o_los_asientos_van_entre_los_afectados_del_registro_de_auditoria_y_en_sus_datos(self):
        """Postcondición o y D-92 punto 3: el único registro `concrecion_siembra` nombra cada asiento entre sus afectados y en `datos`; el asiento y
        cada movimiento tienen su propio registro de auditoría (los hace `contabilidad`, no se repiten)."""
        self.adicional_reservado("10")
        self.concretar()
        registro = RegistroAuditoria.objects.get(accion="concrecion_siembra")
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        for asiento in AsientoContable.objects.all():
            self.assertIn(("contabilidad.asientocontable", asiento.pk), afectados)
        self.assertEqual(len(registro.detalle["datos"]["asientos"]), 2)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_asiento_contable").count(), 2)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="concrecion_siembra").count(), 1)

    def test_garantia_si_falla_el_segundo_asiento_no_queda_ni_el_primero_ni_nada_de_la_concrecion(self):
        """D-22 y `docs/patrones/asientos.md` §4: si el asiento del segundo consumo falla, se revierte todo: sin lote, consumos, movimientos de
        stock, asientos ni registro de auditoría."""
        real = servicio_de_asientos.registrar_asiento_automatico
        llamadas = []

        def falla_en_la_segunda(*args, **kwargs):
            llamadas.append(1)
            if len(llamadas) == 2:
                raise RuntimeError("falla del asiento")
            return real(*args, **kwargs)

        self.adicional_reservado("10")
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=falla_en_la_segunda):
            with self.assertRaises(RuntimeError):
                self.concretar()
        self.assertEqual(len(llamadas), 2)
        self.nada_cambio()
        self.assertEqual(self.disponible_de_la_semilla(), D("1000"))

    def test_garantia_un_rechazo_no_crea_asientos_ni_abre_el_ejercicio(self):
        """Un rechazo de la concreción (cantidad inválida) no deja asientos ni abre un ejercicio: lo verificado va antes de lo escrito."""
        self.rechazo(sembrado=((self.e.sectores["germinacion"].pk, 51),))
        self.assertEqual(AsientoContable.objects.count(), 0)
        self.assertEqual(EjercicioContable.objects.count(), 0)
