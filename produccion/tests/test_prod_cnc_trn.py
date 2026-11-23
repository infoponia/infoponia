# Pruebas de PROD-CNC-TRN · Concretar Transición (PRD-02, paso 5; docs/casos_de_uso/produccion/transicion.md, «Cómo se aplica en la ronda»).
#
# Servicios que se prueban (produccion/servicios/transiciones.py):
# - datos_de_concrecion(actor, orden_id): lo que propone el paso 4 (fecha de hoy, cantidad por sector destino, con el reparto proporcional si
#   el lote perdió plantas; fecha mínima y de dónde sale). No escribe ni bloquea.
# - resumen_de_concrecion(actor, orden_id, datos): valida TODO y devuelve el resumen del paso 11 SIN escribir ni bloquear.
# - concretar_transicion(actor, orden_id, datos) -> TransicionEtapa: lo mismo, y repite TODAS las verificaciones bajo bloqueo (extensiones 13a
#   a 13c) antes de escribir (todo o nada, D-22), con la merma de las plantas que no se trasladaron (aplicar_merma) dentro de la misma
#   transacción. Los rechazos son `ErrorDeProduccion(codigo, mensaje, campo, datos)`.
# - DatosDeConcrecionDeTransicion(fecha_efectiva, cantidades=((sector_id, plantas), ...), causa="", descripcion="", cantidad=None).
#   `cantidades` solo lleva los sectores que difieren de lo propuesto (los demás toman la propuesta, paso 8); `cantidad` es la cantidad
#   actual del lote que la persona vio: si cambió al confirmar, `cambio_simultaneo` con la nueva cantidad y la propuesta (extensión 13c).
#
# Códigos y campos: sin_permiso; orden_no_pendiente (13b); invernadero_inactivo; lote_sin_plantas (4a); cambio_simultaneo (13a: `datos`
# con `etapa_actual`; 13c: con `cantidad_actual` y `propuesta`); fecha_invalida (fecha_efectiva; 6a y 6b, esta con `fecha_minima` y
# `origen` en `datos`); sector_no_elegible (cantidades); cantidad_invalida (cantidades; 8a, 10b y 10c); causa_obligatoria (causa; 10a.3a);
# causa_invalida; descripcion_larga.
#
# Una prueba por regla y por postcondición a a m, menos las contables (D-45: sin ejercicio, cuentas ni asientos). Cada prueba arma sus
# propios datos y viola UNA sola regla.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from core.models import Capataz, Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.models import MovimientoInsumo
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta, Invernadero
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import crear_capataz_activo, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.models import AlertaDeMerma, Bitacora, Consumo, Lote, Merma, OcupacionSector, OrdenTrabajo, TransicionEtapa
from produccion.servicios import costos, lotes as api_lotes, transiciones
from produccion.tests.fabricas import (
    invernadero_con_produccion,
    lote_con_ciclo,
    orden_de_siembra,
    orden_de_transicion,
)


def hoy():
    return timezone.localdate()


def datos(**cambios):
    """`DatosDeConcrecionDeTransicion` válidos: hoy, sin cambios sobre lo propuesto, y la cantidad actual que la persona vio (50)."""
    base = dict(fecha_efectiva=hoy(), cantidades=(), causa="", descripcion="", cantidad=50)
    base.update(cambios)
    return transiciones.DatosDeConcrecionDeTransicion(**base)


def rechazo(llamada):
    """Ejecuta `llamada()` y devuelve el `ErrorDeProduccion` que lanza; si no lanza ninguno, la prueba falla."""
    try:
        llamada()
    except ErrorDeProduccion as error:
        return error
    raise AssertionError("Se esperaba un ErrorDeProduccion y no se lanzó ninguno.")


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero completo (sectores de 100 agujeros) con un lote de 50 plantas en Crecimiento (costo 100,00) desde hoy y su transición
    «a realizar» a Floración, planificada por el Agrónomo para el sector de Floración."""

    def setUp(self):
        self.e = invernadero_con_produccion()
        self.lote = lote_con_ciclo(self.e, cantidad=50, costo="100.00")
        self.orden = orden_de_transicion(self.e, self.lote)
        self.destino = self.e.sectores["floracion"]
        self.origen = self.e.sectores["crecimiento"]

    def concretar(self, actor=None, **cambios):
        return transiciones.concretar_transicion(actor or self.e.capataz, self.orden.pk, datos(**cambios))

    def rechazo(self, **cambios):
        return rechazo(lambda: self.concretar(**cambios))

    def dos_destinos(self):
        """Reparte la orden en dos sectores de Floración (30 y 20 planificados). Devuelve el sector extra."""
        extra = crear_sector(self.e.invernadero, nombre="Sector extra", tipo="floracion", agujeros=100)
        OcupacionSector.objects.filter(orden=self.orden).update(cant_agujeros_planificados=30)
        OcupacionSector.objects.create(orden=self.orden, sector=extra, cant_agujeros_planificados=20)
        return extra

    def bajar_el_lote(self, cantidad):
        """Como si una merma hubiera bajado la cantidad actual del lote mientras la orden esperaba (extensión 13c)."""
        Lote.objects.filter(pk=self.lote.pk).update(cantidad_actual=cantidad, costo_acumulado=Decimal("2.00") * cantidad)
        OcupacionSector.objects.filter(lote=self.lote, cant_agujeros_ocupados__gt=0).update(cant_agujeros_ocupados=cantidad)

    def nada_cambio(self):
        """La orden sigue «a realizar» y no hay bitácora de transición, merma, notificación ni registro de la concreción."""
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "a_realizar")
        self.assertFalse(Merma.objects.exists())
        self.assertFalse(Bitacora.objects.filter(tipo_evento="transicion").exists())
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="concrecion_transicion").exists())
        self.assertEqual(Lote.objects.values_list("etapa_id", "cantidad_actual").get(pk=self.lote.pk), (self.lote.etapa_id, self.lote.cantidad_actual))


class DatosDeConcrecionTests(Base):
    """Paso 4: lo que propone la pantalla."""

    def test_paso_4_propone_la_fecha_de_hoy_las_cantidades_planificadas_y_la_fecha_minima(self):
        """Paso 4: la fecha de hoy como fecha efectiva, la cantidad planificada por sector como cantidad ubicada, la etapa actual y la
        destino, los sectores de origen con sus agujeros y la fecha mínima admitida."""
        propuesta = transiciones.datos_de_concrecion(self.e.capataz, self.orden.pk)
        self.assertEqual(propuesta.fecha_propuesta, hoy())
        self.assertEqual([(f.sector_id, f.planificados, f.propuesto) for f in propuesta.distribucion], [(self.destino.pk, 50, 50)])
        self.assertEqual((propuesta.etapa_origen.codigo, propuesta.etapa_destino.codigo), ("crecimiento", "floracion"))
        self.assertEqual(propuesta.cantidad_actual, 50)
        self.assertEqual([(s.pk, n) for s, n in propuesta.sectores_de_origen], [(self.origen.pk, 50)])
        self.assertEqual((propuesta.fecha_minima, propuesta.origen_de_la_fecha_minima), (hoy(), "entrada"))

    def test_regla_reparto_proporcional_si_el_lote_perdio_plantas_la_propuesta_se_reparte(self):
        """«Reparto proporcional»: si la cantidad actual es menor que la suma de lo planificado, propone la cantidad actual repartida en
        proporción (45 de 30 y 20: 27 y 18)."""
        extra = self.dos_destinos()
        self.bajar_el_lote(45)
        propuesta = transiciones.datos_de_concrecion(self.e.capataz, self.orden.pk)
        self.assertEqual({f.sector_id: f.propuesto for f in propuesta.distribucion}, {self.destino.pk: 27, extra.pk: 18})
        self.assertEqual(propuesta.cantidad_actual, 45)

    def test_regla_fecha_minima_la_mayor_entre_la_entrada_y_el_ultimo_registro_de_bitacora(self):
        """«Fecha mínima»: con un registro de bitácora del lote en la etapa, posterior a la entrada, la mínima es esa fecha y se dice
        que viene de la bitácora."""
        lote = lote_con_ciclo(self.e, cantidad=10, dias_en_etapa=5)
        orden = orden_de_transicion(self.e, lote, distribucion={"floracion": 10})
        propuesta = transiciones.datos_de_concrecion(self.e.capataz, orden.pk)
        self.assertEqual((propuesta.fecha_minima, propuesta.origen_de_la_fecha_minima), (hoy() - timedelta(days=5), "entrada"))
        Bitacora.objects.create(
            invernadero=lote.invernadero, lote=lote, etapa=lote.etapa, tipo_evento="merma", fecha_bitacora=hoy() - timedelta(days=1),
            hora_bitacora=timezone.localtime().time(),
        )
        propuesta = transiciones.datos_de_concrecion(self.e.capataz, orden.pk)
        self.assertEqual((propuesta.fecha_minima, propuesta.origen_de_la_fecha_minima), (hoy() - timedelta(days=1), "bitacora"))

    def test_ext_4a_un_lote_sin_plantas_no_se_puede_concretar(self):
        """Extensión 4a: la cantidad actual es cero (una merma lo dejó sin plantas): `lote_sin_plantas`; la orden sigue «a realizar» para
        que el Agrónomo la cancele."""
        Lote.objects.filter(pk=self.lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        OcupacionSector.objects.filter(lote=self.lote).update(cant_agujeros_ocupados=0)
        self.assertEqual(rechazo(lambda: transiciones.datos_de_concrecion(self.e.capataz, self.orden.pk)).codigo, "lote_sin_plantas")
        self.assertEqual(self.rechazo().codigo, "lote_sin_plantas")
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "a_realizar")

    def test_pre_b_solo_el_capataz_asignado_a_la_orden_ve_la_propuesta(self):
        """Requisito especial: «solo el Capataz asignado a la orden puede concretarla»: otro rol u otro Capataz, `sin_permiso`; una
        orden inexistente o que no es de transición, `Http404`."""
        otro = crear_capataz_activo("otro.capataz@infoponia.com")
        for actor in (self.e.agronomo, crear_gerente(), otro):
            with self.subTest(actor=actor):
                self.assertEqual(rechazo(lambda: transiciones.datos_de_concrecion(actor, self.orden.pk)).codigo, "sin_permiso")
        siembra = orden_de_siembra(self.e, plantines=1)
        for orden_id in (999999, siembra.pk):
            with self.subTest(orden_id=orden_id), self.assertRaises(Http404):
                transiciones.datos_de_concrecion(self.e.capataz, orden_id)


class ConcretarTransicionTests(Base):
    # ---- Precondiciones ----

    def test_pre_a_solo_el_capataz_asignado_activo_concreta(self):
        """Precondición a y requisito especial: otro rol, otro Capataz o el Capataz dado de baja, `sin_permiso`; no cambia nada."""
        otro = crear_capataz_activo("otro.capataz@infoponia.com")
        for actor in (self.e.agronomo, crear_gerente(), otro):
            with self.subTest(actor=actor):
                self.assertEqual(rechazo(lambda: self.concretar(actor)).codigo, "sin_permiso")
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.assertEqual(self.rechazo().codigo, "sin_permiso")
        self.nada_cambio()

    def test_pre_b_la_orden_tiene_que_estar_a_realizar_y_el_invernadero_activo(self):
        """Extensión 13b: una orden cancelada o ya concretada, `orden_no_pendiente`, con su estado actual en el mensaje; un invernadero
        inactivo, `invernadero_inactivo`."""
        OrdenTrabajo.objects.filter(pk=self.orden.pk).update(
            estado_orden="cancelada", fecha_resolucion_orden=hoy(), motivo_cancelacion="Ya no hace falta"
        )
        error = self.rechazo()
        self.assertEqual(error.codigo, "orden_no_pendiente")
        self.assertIn("cancelada", error.mensaje)
        OrdenTrabajo.objects.filter(pk=self.orden.pk).update(estado_orden="a_realizar", fecha_resolucion_orden=None, motivo_cancelacion=None)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(self.rechazo().codigo, "invernadero_inactivo")

    def test_regla_una_orden_se_concreta_una_unica_vez(self):
        """Garantía «una orden de transición se concreta una única vez»: la segunda vez, `orden_no_pendiente`."""
        self.concretar()
        self.assertEqual(self.rechazo().codigo, "orden_no_pendiente")

    # ---- La fecha efectiva ----

    def test_ext_6a_la_fecha_efectiva_posterior_a_hoy_se_rechaza(self):
        """Extensión 6a: `fecha_invalida` (campo `fecha_efectiva`); sin fecha tampoco."""
        error = self.rechazo(fecha_efectiva=hoy() + timedelta(days=1))
        self.assertEqual((error.codigo, error.campo), ("fecha_invalida", "fecha_efectiva"))
        self.assertEqual(self.rechazo(fecha_efectiva=None).codigo, "fecha_invalida")
        self.nada_cambio()

    def test_ext_6b_la_fecha_anterior_a_la_minima_se_rechaza_e_informa_de_donde_viene(self):
        """Extensión 6b: `fecha_invalida` con la fecha mínima y su origen (la entrada del lote a su etapa actual o su último registro de
        bitácora en ella); en la fecha mínima misma, se acepta."""
        lote = lote_con_ciclo(self.e, cantidad=10, dias_en_etapa=5)
        orden = orden_de_transicion(self.e, lote, distribucion={"floracion": 10})
        antes = hoy() - timedelta(days=6)
        error = rechazo(lambda: transiciones.concretar_transicion(self.e.capataz, orden.pk, datos(fecha_efectiva=antes, cantidad=10)))
        self.assertEqual((error.codigo, error.campo), ("fecha_invalida", "fecha_efectiva"))
        self.assertEqual((error.datos["fecha_minima"], error.datos["origen"]), (hoy() - timedelta(days=5), "entrada"))
        Bitacora.objects.create(
            invernadero=lote.invernadero, lote=lote, etapa=lote.etapa, tipo_evento="merma", fecha_bitacora=hoy() - timedelta(days=2),
            hora_bitacora=timezone.localtime().time(),
        )
        error = rechazo(
            lambda: transiciones.concretar_transicion(
                self.e.capataz, orden.pk, datos(fecha_efectiva=hoy() - timedelta(days=3), cantidad=10)
            )
        )
        self.assertEqual((error.datos["fecha_minima"], error.datos["origen"]), (hoy() - timedelta(days=2), "bitacora"))
        concretada = transiciones.concretar_transicion(self.e.capataz, orden.pk, datos(fecha_efectiva=hoy() - timedelta(days=2), cantidad=10))
        self.assertEqual(TransicionEtapa.objects.get(pk=concretada.pk).fecha_transicion, hoy() - timedelta(days=2))

    def test_regla_fecha_efectiva_puede_ser_anterior_a_la_creacion_y_a_la_programada(self):
        """«Fecha efectiva válida»: entre la mínima y hoy, ambas inclusive; puede ser anterior a la fecha de creación de la orden y a la
        programada (el traslado físico pudo hacerse antes de registrarlo)."""
        lote = lote_con_ciclo(self.e, cantidad=10, dias_en_etapa=5)
        orden = orden_de_transicion(self.e, lote, distribucion={"floracion": 10}, dias=3)
        concretada = transiciones.concretar_transicion(
            self.e.capataz, orden.pk, datos(fecha_efectiva=hoy() - timedelta(days=2), cantidad=10)
        )
        orden = TransicionEtapa.objects.get(pk=concretada.pk)
        self.assertLess(orden.fecha_transicion, orden.fecha_creacion_orden)
        self.assertLess(orden.fecha_transicion, orden.fecha_programada_orden)

    # ---- Las cantidades ----

    def test_ext_8a_una_cantidad_mayor_que_la_planificada_para_el_sector_se_rechaza(self):
        """Extensión 8a: `cantidad_invalida` (campo `cantidades`), informando lo planificado para ese sector."""
        error = self.rechazo(cantidades=((self.destino.pk, 51),))
        self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", "cantidades"))
        self.assertEqual(error.datos["planificado"], 50)

    def test_regla_cantidad_ubicada_es_un_entero_entre_cero_y_lo_planificado_y_solo_de_sectores_de_la_orden(self):
        """«Cantidad ubicada válida»: entera, de 0 a lo planificado; no se admiten sectores fuera de la distribución planificada
        (`sector_no_elegible`) ni un sector repetido."""
        for cantidades in (((self.destino.pk, -1),), ((self.destino.pk, 2.5),), ((self.destino.pk, 10), (self.destino.pk, 10))):
            with self.subTest(cantidades=cantidades):
                self.assertEqual(self.rechazo(cantidades=cantidades).codigo, "cantidad_invalida")
        self.assertEqual(self.rechazo(cantidades=((self.e.sectores["fructificacion"].pk, 5),)).codigo, "sector_no_elegible")
        self.nada_cambio()

    def test_regla_valores_propuestos_los_sectores_que_no_se_indican_toman_la_cantidad_propuesta(self):
        """«Valores propuestos»: el Capataz solo indica lo que difiere; en los demás sectores se toma la propuesta (30 en el sector
        que no se indicó)."""
        extra = self.dos_destinos()
        self.concretar(cantidades=((extra.pk, 20),), causa="")
        por_sector = dict(OcupacionSector.objects.filter(orden=self.orden).values_list("sector_id", "cant_agujeros_ocupados"))
        self.assertEqual(por_sector, {self.destino.pk: 30, extra.pk: 20})

    def test_ext_10b_el_total_ubicado_en_cero_se_rechaza(self):
        """Extensión 10b: «no es posible concretar una transición sin plantas trasladadas»: `cantidad_invalida`; la orden sigue «a
        realizar» hasta que el Agrónomo la cancele."""
        error = self.rechazo(cantidades=((self.destino.pk, 0),), causa="plaga")
        self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", "cantidades"))
        self.assertIn("sin plantas", error.mensaje)
        self.nada_cambio()

    def test_ext_10c_el_total_ubicado_no_puede_superar_la_cantidad_actual_del_lote(self):
        """Extensión 10c: con 45 plantas en el lote y 50 planificadas, ubicar 50 se rechaza e informa la cantidad actual."""
        self.bajar_el_lote(45)
        error = self.rechazo(cantidades=((self.destino.pk, 50),), cantidad=45)
        self.assertEqual((error.codigo, error.datos["cantidad_actual"]), ("cantidad_invalida", 45))

    def test_ext_10a_si_faltan_plantas_la_causa_es_obligatoria(self):
        """Extensión 10a.3a: con el total ubicado menor que la cantidad actual hay que indicar la causa (`causa_obligatoria`, campo
        `causa`); una causa que no es de un lote en pie, `causa_invalida`; la descripción, hasta 300 (`descripcion_larga`). El Sistema
        calcula la cantidad perdida; no se escribe."""
        error = self.rechazo(cantidades=((self.destino.pk, 40),))
        self.assertEqual((error.codigo, error.campo), ("causa_obligatoria", "causa"))
        self.assertEqual(self.rechazo(cantidades=((self.destino.pk, 40),), causa="vencimiento_en_camara").codigo, "causa_invalida")
        self.assertEqual(self.rechazo(cantidades=((self.destino.pk, 40),), causa="plaga", descripcion="x" * 301).codigo, "descripcion_larga")
        self.nada_cambio()

    def test_ext_10a_con_el_total_completo_no_hay_merma_y_la_causa_se_ignora(self):
        """«Total completo sin merma»: si se ubican todas las plantas no se registra merma aunque venga una causa."""
        self.concretar(causa="plaga")
        self.assertFalse(Merma.objects.exists())

    # ---- Extensiones 13a y 13c ----

    def test_ext_13a_el_lote_cambio_de_etapa_mientras_el_capataz_cargaba_los_datos(self):
        """Extensión 13a: el lote ya no está en la etapa de la orden: no registra nada e informa qué cambió (`cambio_simultaneo`)."""
        Lote.objects.filter(pk=self.lote.pk).update(etapa_id=self.orden.etapa_destino_id)
        error = self.rechazo()
        self.assertEqual(error.codigo, "cambio_simultaneo")
        self.assertIn("etapa_actual", error.datos)

    def test_ext_13c_cambio_la_cantidad_actual_y_se_vuelve_a_proponer_el_reparto(self):
        """Extensión 13c: el lote perdió plantas mientras tanto: no registra nada, informa la nueva cantidad actual y trae la
        distribución propuesta con esa cantidad (45 de 30 y 20: 27 y 18)."""
        extra = self.dos_destinos()
        self.bajar_el_lote(45)
        error = self.rechazo(cantidad=50)
        self.assertEqual(error.codigo, "cambio_simultaneo")
        self.assertEqual(error.datos["cantidad_actual"], 45)
        self.assertEqual(dict(error.datos["propuesta"]), {self.destino.pk: 27, extra.pk: 18})
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "a_realizar")

    def test_ext_13c_sin_dato_visto_no_compara_y_usa_la_cantidad_actual(self):
        """Con `cantidad=None` la comparación no corre; la propuesta sale de la cantidad actual."""
        self.dos_destinos()
        self.bajar_el_lote(45)
        self.concretar(cantidad=None, cantidades=())
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 45)

    # ---- Postcondiciones ----

    def test_post_a_la_orden_pasa_a_concretada_con_su_fecha_efectiva_y_su_cantidad_transferida(self):
        """Postcondición a: «concretada» con fecha de resolución = hoy, fecha efectiva = la indicada y cantidad transferida = el total
        ubicado (suma de los agujeros ocupados)."""
        extra = self.dos_destinos()
        fecha = hoy()
        self.concretar(fecha_efectiva=fecha, cantidades=((self.destino.pk, 30), (extra.pk, 15)), causa="plaga", cantidad=50)
        orden = TransicionEtapa.objects.get(pk=self.orden.pk)
        self.assertEqual((orden.estado_orden, orden.fecha_resolucion_orden, orden.fecha_transicion, orden.cant_transferido), ("concretada", hoy(), fecha, 45))

    def test_post_b_el_lote_pasa_a_la_etapa_destino_y_sigue_activo_con_la_cantidad_ubicada(self):
        """Postcondición b: la etapa del lote es la destino y sigue «activo»; si hubo plantas perdidas su cantidad actual es el total
        ubicado."""
        self.concretar(cantidades=((self.destino.pk, 40),), causa="plaga")
        lote = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual((lote.etapa_id, lote.estado_lote, lote.cantidad_actual), (self.orden.etapa_destino_id, "activo", 40))

    def test_post_c_las_ocupaciones_destino_cargan_los_ocupados_y_se_asocian_al_lote_las_que_tienen_plantas(self):
        """Postcondición c: cada ocupación destino queda con los agujeros ocupados = plantas ubicadas; los planificados no cambian; las
        que tienen al menos una planta se asocian al lote y las que quedaron en cero se conservan con cero ocupados y sin lote."""
        extra = self.dos_destinos()
        self.concretar(cantidades=((self.destino.pk, 30), (extra.pk, 0)), causa="plaga", cantidad=50)
        principal = OcupacionSector.objects.get(orden=self.orden, sector=self.destino)
        vacia = OcupacionSector.objects.get(orden=self.orden, sector=extra)
        self.assertEqual((principal.cant_agujeros_planificados, principal.cant_agujeros_ocupados, principal.lote_id), (30, 30, self.lote.pk))
        self.assertEqual((vacia.cant_agujeros_planificados, vacia.cant_agujeros_ocupados, vacia.lote_id), (20, 0, None))

    def test_post_d_las_ocupaciones_de_origen_quedan_en_cero_y_conservan_su_lote(self):
        """Postcondición d: las ocupaciones que el lote tenía en sus sectores de origen quedan con cero ocupados y siguen asociadas al
        lote (también los agujeros de las plantas perdidas)."""
        self.concretar(cantidades=((self.destino.pk, 40),), causa="plaga")
        origen = OcupacionSector.objects.filter(lote=self.lote, sector=self.origen)
        self.assertTrue(origen.exists())
        self.assertEqual({(o.cant_agujeros_ocupados, o.lote_id) for o in origen}, {(0, self.lote.pk)})

    def test_post_e_f_los_agujeros_de_cada_sector_se_actualizan(self):
        """Postcondiciones e y f: en el sector destino los comprometidos bajan en lo planificado y los ocupados suben en lo ubicado (lo
        planificado que no se ubicó vuelve a estar libre); en el de origen los disponibles suben en lo que el lote ocupaba, incluido lo
        perdido."""
        antes = api_sectores.agujeros_de([self.destino, self.origen])
        self.concretar(cantidades=((self.destino.pk, 40),), causa="plaga")
        despues = api_sectores.agujeros_de([self.destino, self.origen])
        self.assertEqual((antes[self.destino.pk].comprometidos, despues[self.destino.pk].comprometidos), (50, 0))
        self.assertEqual((antes[self.destino.pk].ocupados, despues[self.destino.pk].ocupados), (0, 40))
        self.assertEqual((antes[self.origen.pk].ocupados, despues[self.origen.pk].ocupados), (50, 0))
        self.assertEqual((antes[self.origen.pk].libres, despues[self.origen.pk].libres), (50, 100))
        self.assertEqual((antes[self.destino.pk].libres, despues[self.destino.pk].libres), (50, 60))

    def test_post_g_registra_en_la_bitacora_un_evento_de_transicion_enlazado_a_la_orden(self):
        """Postcondición g: evento de bitácora «transición» con la fecha efectiva, la hora actual, el Capataz como responsable, el lote,
        la etapa DESTINO y el invernadero; descripción legible; los sectores son los destino con al menos una planta; la orden lo enlaza."""
        extra = self.dos_destinos()
        fecha = hoy()
        antes = timezone.localtime().time()
        self.concretar(fecha_efectiva=fecha, cantidades=((extra.pk, 0),), causa="plaga", cantidad=50)
        orden = TransicionEtapa.objects.get(pk=self.orden.pk)
        registro = Bitacora.objects.get(pk=orden.bitacora_de_transicion_id)
        self.assertEqual(registro.tipo_evento, "transicion")
        self.assertEqual((registro.fecha_bitacora, registro.responsable_id, registro.lote_id), (fecha, self.e.capataz.pk, self.lote.pk))
        self.assertEqual((registro.etapa_id, registro.invernadero_id), (orden.etapa_destino_id, self.e.invernadero.pk))
        self.assertGreaterEqual(registro.hora_bitacora, antes)
        self.assertEqual(registro.descripcion_evento, f"Transición del lote {self.lote.codigo} a Floración: 30 plantas.")
        self.assertEqual(list(registro.sectores.values_list("pk", flat=True)), [self.destino.pk])

    def test_post_h_las_plantas_sin_trasladar_se_registran_como_merma_en_la_etapa_de_origen_con_la_fecha_efectiva(self):
        """Postcondición h y «Merma de la transición»: una sola merma con la cantidad que el Sistema calcula (cantidad actual menos el
        total ubicado), la causa y la descripción indicadas, en la etapa de ORIGEN y con la fecha efectiva; el Capataz es el responsable;
        no libera agujeros por su cuenta."""
        lote_etapa = self.lote.etapa_id
        self.concretar(cantidades=((self.destino.pk, 40),), causa="enfermedad", descripcion="Hongo en la bandeja")
        merma = Merma.objects.get()
        self.assertEqual((merma.cant_merma, merma.causa, merma.etapa_id, merma.lote_id), (10, "enfermedad", lote_etapa, self.lote.pk))
        self.assertEqual((merma.fecha_bitacora, merma.responsable_id), (hoy(), self.e.capataz.pk))
        self.assertIn("Hongo en la bandeja", merma.descripcion_evento)
        self.assertEqual(list(merma.sectores.all()), [])

    def test_post_h_la_merma_baja_el_costo_del_lote_como_el_patron_y_el_costo_por_planta_no_cambia(self):
        """`costo_del_lote.md`: 50 plantas a 100,00 (2,00 cada una); perder 10 cuesta 20,00: el lote queda con 80,00 y el costo por
        planta sigue en 2,00 (cambió el costo total, no el unitario)."""
        self.concretar(cantidades=((self.destino.pk, 40),), causa="plaga")
        lote = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado), (40, Decimal("80.00")))
        self.assertEqual(costos.costo_por_planta(lote), Decimal("2.00"))

    def test_post_h_la_transicion_no_puede_dejar_el_lote_en_cero(self):
        """«En una transición no puede llegar a cero»: el total ubicado es de al menos una planta; el lote sigue activo."""
        self.rechazo(cantidades=((self.destino.pk, 0),), causa="plaga")
        self.concretar(cantidades=((self.destino.pk, 1),), causa="plaga")
        lote = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual((lote.cantidad_actual, lote.estado_lote), (1, "activo"))

    def test_post_i_la_merma_que_cruza_el_umbral_crea_la_alerta_para_el_agronomo_y_el_gerente(self):
        """Postcondición i: perder 10 de 50 (20 %, más del 15 %) genera la alerta de umbral (Agrónomo y Gerente) enlazada con la merma;
        con «descarte por selección» no suma y no hay alerta."""
        self.concretar(cantidades=((self.destino.pk, 40),), causa="plaga")
        alerta = Alerta.objects.get(tipo_alerta="produccion_merma_umbral")
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (self.e.agronomo.pk, True))
        self.assertEqual(AlertaDeMerma.objects.get(alerta=alerta).merma_id, Merma.objects.get().pk)

    def test_post_i_el_descarte_por_seleccion_no_crea_la_alerta_de_umbral(self):
        """Regla «Merma acumulada»: «descarte por selección» baja plantas y costo pero no cuenta para el umbral."""
        self.concretar(cantidades=((self.destino.pk, 25),), causa="descarte_por_seleccion")
        self.assertFalse(Alerta.objects.exists())
        self.assertEqual(Merma.objects.get().causa, "descarte_por_seleccion")

    def test_post_i_desde_la_transicion_no_se_dispara_la_condicion_2_de_plantas_comprometidas(self):
        """Extensión 10a de PROD-REG-MRM: la alerta de plantas comprometidas se evalúa SIN contar la orden que se concreta: desde esta
        transición no puede dispararse (la condición 2 está probada llamando a `aplicar_merma`, en `test_mermas_nucleo.py`)."""
        self.concretar(cantidades=((self.destino.pk, 40),), causa="plaga")
        self.assertFalse(Alerta.objects.filter(tipo_alerta="produccion_plantas_comprometidas").exists())

    def test_post_j_se_notifica_al_agronomo_con_lo_planificado_lo_realizado_la_merma_y_las_fechas(self):
        """Postcondición j: el Agrónomo a cargo recibe un aviso con lo planificado y lo realizado por sector, las plantas perdidas y su
        causa y la fecha efectiva frente a la programada (hasta 500 caracteres); solo él."""
        self.concretar(cantidades=((self.destino.pk, 40),), causa="plaga")
        notificacion = Notificacion.objects.get(destinatario=self.e.agronomo)
        self.assertEqual(Notificacion.objects.count(), 1)
        self.assertIn(self.orden.codigo, notificacion.titulo)
        for texto in (self.lote.codigo, "Floración", self.destino.nombre_sector, "50", "40", "10", "plaga", f"{hoy():%d/%m/%Y}"):
            self.assertIn(texto, notificacion.detalle)
        self.assertLessEqual(len(notificacion.detalle), 500)

    def test_post_j_avisa_si_la_fecha_efectiva_es_anterior_a_la_creacion_de_la_orden(self):
        """Postcondición j: la notificación avisa además si la fecha efectiva es anterior a la fecha de creación de la orden."""
        lote = lote_con_ciclo(self.e, cantidad=10, dias_en_etapa=5)
        orden = orden_de_transicion(self.e, lote, distribucion={"floracion": 10})
        transiciones.concretar_transicion(self.e.capataz, orden.pk, datos(fecha_efectiva=hoy() - timedelta(days=2), cantidad=10))
        detalle = Notificacion.objects.get(destinatario=self.e.agronomo).detalle
        self.assertIn("anterior a la creación de la orden", detalle)
        self.assertIn(f"{orden.fecha_creacion_orden:%d/%m/%Y}", detalle)

    def test_post_j_sin_la_diferencia_no_hay_aviso_de_fecha_anterior(self):
        """Con la fecha efectiva de hoy (no anterior a la creación), el aviso no menciona la fecha de creación."""
        self.concretar()
        self.assertNotIn("anterior a la creación", Notificacion.objects.get().detalle)

    def test_post_k_l_m_un_solo_registro_de_auditoria_con_todo_lo_modificado_y_creado(self):
        """Postcondiciones k, l y m (D-36, un registro por caso de uso): `concrecion_transicion` con la orden, el lote, las ocupaciones,
        los sectores, el registro de bitácora y, si hubo, la merma y la alerta; los cambios de estado, fecha de resolución, fecha efectiva,
        cantidad transferida, etapa y cantidad del lote y los agujeros ocupados de cada sector."""
        self.concretar(cantidades=((self.destino.pk, 40),), causa="plaga")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="concrecion_transicion").count(), 1)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="registro_merma").exists())  # la merma va DENTRO del único registro
        registro = RegistroAuditoria.objects.get(accion="concrecion_transicion")
        self.assertEqual(registro.usuario_id, self.e.capataz.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        orden = TransicionEtapa.objects.get(pk=self.orden.pk)
        esperados = {
            ("produccion.transicionetapa", orden.pk),
            ("produccion.lote", self.lote.pk),
            ("produccion.bitacora", orden.bitacora_de_transicion_id),
            ("produccion.merma", Merma.objects.get().pk),
            ("maestros.sectorproduccion", self.destino.pk),
            ("maestros.sectorproduccion", self.origen.pk),
        }
        esperados |= {("produccion.ocupacionsector", o.pk) for o in OcupacionSector.objects.filter(orden=orden)}
        # Las ocupaciones de origen (la vigente del lote en Crecimiento); las históricas ya en cero no se modifican.
        esperados |= {("produccion.ocupacionsector", o.pk) for o in OcupacionSector.objects.filter(lote=self.lote, sector=self.origen)}
        esperados |= {("maestros.alerta", a.pk) for a in Alerta.objects.all()}
        self.assertLessEqual(esperados, afectados)
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["estado"], {"antes": "a_realizar", "despues": "concretada"})
        self.assertEqual(cambios["cantidad_transferida"]["despues"], "40")
        self.assertEqual((cambios["cantidad_actual"]["antes"], cambios["cantidad_actual"]["despues"]), ("50", "40"))
        self.assertEqual(cambios["costo_acumulado"], {"antes": "100.00", "despues": "80.00"})
        self.assertEqual(cambios["etapa"], {"antes": "Crecimiento", "despues": "Floración"})
        self.assertIn(f"{self.origen.nombre_sector}: 0", cambios["agujeros_ocupados"]["despues"])
        self.assertIn(f"{self.destino.nombre_sector}: 40", cambios["agujeros_ocupados"]["despues"])

    # ---- Garantías mínimas ----

    def test_garantia_un_error_en_el_medio_no_deja_nada_cambiado(self):
        """Garantías mínimas y D-22 (incluido el caso de uso que lo extiende): si algo falla después de escribir (acá, el aviso al
        Agrónomo), la orden sigue «a realizar» y no queda merma, bitácora, ocupación cargada, cambio en el lote, notificación ni registro."""
        antes = list(OcupacionSector.objects.order_by("pk").values_list("pk", "cant_agujeros_ocupados", "lote_id"))
        with mock.patch("core.notificaciones.notificar", side_effect=RuntimeError("falla del aviso")):
            with self.assertRaises(RuntimeError):
                self.concretar(cantidades=((self.destino.pk, 40),), causa="plaga")
        self.nada_cambio()
        self.assertEqual(list(OcupacionSector.objects.order_by("pk").values_list("pk", "cant_agujeros_ocupados", "lote_id")), antes)
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).costo_acumulado, Decimal("100.00"))
        self.assertFalse(Alerta.objects.exists())

    def test_garantia_la_transicion_no_consume_insumos_ni_genera_asientos(self):
        """Garantía: «la transición no consume insumos ni genera asientos por sí misma» (D-45: sin ejercicio, cuentas ni asientos): no
        hay movimientos de insumo ni consumos, y la concreción no pide ejercicio contable."""
        antes = (MovimientoInsumo.objects.count(), Consumo.objects.count())
        self.concretar()
        self.assertEqual((MovimientoInsumo.objects.count(), Consumo.objects.count()), antes)


class ResumenDeConcrecionTests(Base):
    """Paso 11: el resumen valida igual que la concreción y no escribe nada."""

    def resumen(self, **cambios):
        return transiciones.resumen_de_concrecion(self.e.capataz, self.orden.pk, datos(**cambios))

    def test_paso_11_el_resumen_trae_la_fecha_las_etapas_las_cantidades_la_liberacion_y_la_distribucion(self):
        """Paso 11: fecha efectiva y su diferencia en días con la programada, lote y variedad, etapas de origen y destino, cantidad
        actual y total ubicado, plantas sin trasladar con su causa, sectores de origen que se liberan y la distribución real frente a la
        planificada."""
        extra = self.dos_destinos()
        resumen = self.resumen(cantidades=((self.destino.pk, 25), (extra.pk, 20)), causa="plaga", descripcion="Hongo")
        self.assertEqual((resumen.fecha_efectiva, resumen.diferencia_con_la_programada), (hoy(), 0))
        self.assertEqual((resumen.lote.pk, resumen.variedad), (self.lote.pk, self.e.variedad))
        self.assertEqual((resumen.etapa_origen.codigo, resumen.etapa_destino.codigo), ("crecimiento", "floracion"))
        self.assertEqual((resumen.cantidad_actual, resumen.total_ubicado, resumen.plantas_sin_trasladar), (50, 45, 5))
        self.assertEqual((resumen.causa, resumen.descripcion), ("plaga", "Hongo"))
        self.assertEqual([(s.pk, n) for s, n in resumen.sectores_que_se_liberan], [(self.origen.pk, 50)])
        self.assertEqual([(s.pk, plan, real) for s, plan, real in resumen.distribucion], [(self.destino.pk, 30, 25), (extra.pk, 20, 20)])

    def test_paso_11_sin_plantas_perdidas_no_hay_causa_ni_plantas_sin_trasladar(self):
        """Con el total completo, `plantas_sin_trasladar` es cero y la causa queda vacía aunque se haya cargado una."""
        resumen = self.resumen(causa="plaga")
        self.assertEqual((resumen.plantas_sin_trasladar, resumen.causa), (0, ""))

    def test_ext_11a_con_maduracion_vencida_advierte_que_no_contara_como_stock_maduro_libre(self):
        """Extensión 11a: si el destino es Maduración y la fecha máxima de cosecha (efectiva + duración de Maduración) es anterior a hoy,
        el resumen advierte y no bloquea. Con la fecha de hoy no hay advertencia."""
        e = invernadero_con_produccion(nombre="Corto", sufijo="c", etapas=("germinacion", "crecimiento", "maduracion"))
        lote = lote_con_ciclo(e, cantidad=10, dias_en_etapa=30)
        orden = orden_de_transicion(e, lote, distribucion={"maduracion": 10})
        vencida = transiciones.resumen_de_concrecion(e.capataz, orden.pk, datos(fecha_efectiva=hoy() - timedelta(days=25), cantidad=10))
        self.assertEqual(vencida.fecha_maxima_de_cosecha, hoy() - timedelta(days=15))
        self.assertTrue(vencida.maduracion_vencida)
        actual = transiciones.resumen_de_concrecion(e.capataz, orden.pk, datos(cantidad=10))
        self.assertEqual((actual.fecha_maxima_de_cosecha, actual.maduracion_vencida), (hoy() + timedelta(days=10), False))
        self.assertIsNone(self.resumen().fecha_maxima_de_cosecha)

    def test_paso_11_el_resumen_no_escribe_nada(self):
        """El resumen no cambia la orden, el lote ni las ocupaciones, y no crea merma, bitácora, notificación ni auditoría."""
        self.resumen(cantidades=((self.destino.pk, 40),), causa="plaga")
        self.nada_cambio()
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).costo_acumulado, Decimal("100.00"))

    def test_paso_11_el_resumen_rechaza_lo_mismo_que_la_concrecion(self):
        """Mismo rechazo en el resumen y al confirmar: fecha futura, total en cero, causa obligatoria, cantidad que cambió."""
        casos = (
            ({"fecha_efectiva": hoy() + timedelta(days=1)}, "fecha_invalida"),
            ({"cantidades": ((self.destino.pk, 0),), "causa": "plaga"}, "cantidad_invalida"),
            ({"cantidades": ((self.destino.pk, 40),)}, "causa_obligatoria"),
            ({"cantidad": 49}, "cambio_simultaneo"),
        )
        for cambios, codigo in casos:
            with self.subTest(codigo=codigo):
                self.assertEqual(rechazo(lambda: self.resumen(**cambios)).codigo, codigo)

    def test_ext_12a_el_resumen_se_puede_volver_a_pedir_con_las_cantidades_corregidas(self):
        """Extensión 12a: corregir una cantidad y volver a pedir el resumen repite las verificaciones (pasa de 40 a 50 y la causa deja
        de hacer falta)."""
        con_merma = self.resumen(cantidades=((self.destino.pk, 40),), causa="plaga")
        corregido = self.resumen(cantidades=((self.destino.pk, 50),))
        self.assertEqual((con_merma.plantas_sin_trasladar, corregido.plantas_sin_trasladar), (10, 0))


class FechaMinimaEnLaConcrecionTests(Base):
    def test_regla_la_fecha_minima_usa_la_misma_funcion_de_lectura(self):
        """La fecha mínima de la concreción es la de `fecha_minima_de_transicion` (paso 2): no hay dos definiciones."""
        propuesta = transiciones.datos_de_concrecion(self.e.capataz, self.orden.pk)
        self.assertEqual(propuesta.fecha_minima, transiciones.fecha_minima_de_transicion(Lote.objects.get(pk=self.lote.pk)))
        self.assertEqual(api_lotes.fecha_de_entrada_a_la_etapa(Lote.objects.get(pk=self.lote.pk)), hoy())
