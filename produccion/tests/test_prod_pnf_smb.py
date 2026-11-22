# Pruebas de PROD-PNF-SMB · Planificar Siembra (PRD-01, paso 5; docs/casos_de_uso/produccion/siembra.md, «Decisiones de aplicación»).
#
# Servicios que se prueban (produccion/servicios/siembras.py), tomados del módulo dentro de cada prueba para que, mientras no existan,
# falle cada prueba por separado:
# - datos_de_planificacion(actor, invernadero_id=None, variedad_id=None, fecha=None): lo que presentan los pasos 2 a 12 (invernaderos con
#   su motivo si no se pueden elegir, variedades con su compatibilidad, sectores ofrecidos e insumos adicionales). No escribe.
# - resumen_de_planificacion(actor, datos): valida todo y devuelve el resumen del paso 16 SIN escribir ni bloquear.
# - planificar_siembra(actor, datos) -> Siembra: lo mismo, y repite TODAS las verificaciones bajo bloqueo (extensión 18b) antes de
#   escribir (todo o nada, D-22). Los rechazos son `ErrorDeProduccion(codigo, mensaje, campo)`.
# - DatosDeSiembra(invernadero_id, variedad_id, cantidad, fecha_programada, distribucion=((sector_id, plantines), ...), prioridad=None,
#   descripcion="", insumos_adicionales=((existencia_id, cantidad), ...)).
#
# Códigos y campos: sin_permiso; invernadero_inactivo; sin_capataz_activo; variedad_inactiva; variedad_incompatible (campo variedad);
# capacidad_insuficiente (campo variedad en 5b y 5c; cantidad en 8d y 8e; distribucion en 11a); semilla_no_habilitada (variedad);
# fecha_invalida (fecha_programada); cantidad_invalida (cantidad, distribucion o insumos_adicionales); stock_insuficiente (cantidad o
# insumos_adicionales); distribucion_incompleta (distribucion; 11b también); sector_no_elegible (distribucion); insumo_no_elegible
# (insumos_adicionales); prioridad_invalida; descripcion_larga; orden_duplicada (18a).
#
# Una prueba por regla y por postcondición a a i. Cada prueba arma sus propios datos y viola UNA sola regla.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from core.models import Capataz, Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.models import LoteInsumo
from inventario.servicios import insumos_invernadero
from inventario.tests.fabricas import ConDatosDeInventario, categoria_del_sistema, existencia, insumo, lote, perezoso
from maestros.models import Invernadero, SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import crear_agronomo, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.models import OcupacionSector, OrdenTrabajo, ReservaInsumo, Siembra
from produccion.tests.fabricas import (
    insumo_adicional,
    invernadero_con_produccion,
    lote_activo,
    orden_de_siembra,
    variedad_con_stock,
)

siembras = perezoso("produccion.servicios.siembras")
D = Decimal


def hoy():
    return timezone.localdate()


def datos(e, **cambios):
    """`DatosDeSiembra` válidos: 50 plantines de la variedad del escenario, en el sector de germinación, para dentro de 3 días."""
    base = dict(
        invernadero_id=e.invernadero.pk,
        variedad_id=e.variedad.pk,
        cantidad=50,
        fecha_programada=hoy() + timedelta(days=3),
        distribucion=((e.sectores["germinacion"].pk, cambios.get("cantidad", 50)),),
        prioridad=None,
        descripcion="",
        insumos_adicionales=(),
    )
    base.update(cambios)
    return siembras.DatosDeSiembra(**base)


def rechazo(llamada):
    """Ejecuta `llamada()` y devuelve el `ErrorDeProduccion` que lanza; si no lanza ninguno, la prueba falla."""
    try:
        llamada()
    except ErrorDeProduccion as error:
        return error
    raise AssertionError("Se esperaba un ErrorDeProduccion y no se lanzó ninguno.")


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero completo (sectores de 100 agujeros, variedad con semilla habilitada y 1.000 semillas) por prueba."""

    def setUp(self):
        self.e = invernadero_con_produccion()

    def planificar(self, **cambios):
        return siembras.planificar_siembra(self.e.agronomo, datos(self.e, **cambios))

    def rechazo(self, **cambios):
        return rechazo(lambda: self.planificar(**cambios))

    def nada_creado(self):
        """Verifica que no quedó ninguna orden, ocupación, reserva, notificación ni registro de auditoría de la planificación."""
        self.assertEqual(Siembra.objects.count(), 0)
        self.assertEqual(OrdenTrabajo.objects.count(), 0)
        self.assertEqual(OcupacionSector.objects.count(), 0)
        self.assertEqual(ReservaInsumo.objects.count(), 0)
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="planificacion_siembra").exists())


class DatosDePlanificacionTests(Base):
    """Pasos 2, 4, 9 y 12: lo que ofrece la pantalla, con el motivo de lo que no se puede elegir."""

    def ofrecidos(self, actor=None):
        return {i.invernadero_id: i for i in siembras.datos_de_planificacion(actor or self.e.agronomo).invernaderos}

    def test_paso_2_ofrece_los_invernaderos_activos_a_cargo_y_no_los_inactivos_ni_los_ajenos(self):
        """Paso 2: los invernaderos activos a cargo del Agrónomo; nunca los de otro ni los dados de baja."""
        inactivo = invernadero_con_produccion(nombre="Invernadero Viejo", sufijo="2")
        Invernadero.objects.filter(pk=inactivo.invernadero.pk).update(estado_invernadero="inactivo", agronomo=self.e.agronomo)
        ajeno = invernadero_con_produccion(nombre="Invernadero Ajeno", sufijo="3")
        self.assertEqual(list(self.ofrecidos()), [self.e.invernadero.pk])
        self.assertIsNone(self.ofrecidos()[self.e.invernadero.pk].motivo)
        self.assertNotIn(ajeno.invernadero.pk, self.ofrecidos())

    def test_ext_3a_un_invernadero_sin_capataz_activo_aparece_deshabilitado_con_su_motivo(self):
        """Extensión 3a: sin Capataz activo, el invernadero se ofrece deshabilitado y el motivo lo dice (voseo)."""
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        motivo = self.ofrecidos()[self.e.invernadero.pk].motivo
        self.assertIn("Capataz", motivo)

    def test_ext_3b_un_invernadero_sin_espacio_de_germinacion_aparece_deshabilitado_con_su_motivo(self):
        """Extensión 3b: sin sectores de germinación activos con capacidad libre, deshabilitado y con el motivo."""
        orden_de_siembra(self.e, plantines=100)
        motivo = self.ofrecidos()[self.e.invernadero.pk].motivo
        self.assertIn("germinación", motivo)

    def test_paso_4_cada_variedad_trae_perfil_ciclo_stock_libre_y_compatibilidad(self):
        """Paso 4: perfil familiar, duración del ciclo (5 etapas de 10 días), stock libre de la semilla y si es compatible."""
        orden_de_siembra(self.e, plantines=20)  # reserva 20 de la semilla
        fila = {v.variedad_id: v for v in siembras.datos_de_planificacion(self.e.agronomo, self.e.invernadero.pk).variedades}[self.e.variedad.pk]
        self.assertEqual((fila.perfil, fila.duracion_dias, fila.stock_libre, fila.compatible), ("hoja_verde", 50, D("980"), True))
        self.assertEqual(fila.conflictos, [])

    def test_ext_4a_sin_lotes_ni_ordenes_todas_las_variedades_son_compatibles(self):
        """Extensión 4a: un invernadero sin lotes activos ni órdenes «a realizar» ofrece todas como compatibles."""
        rara, _ = variedad_con_stock(self.e, "Calida", temp_ambiente_min="30", temp_ambiente_max="35")
        filas = siembras.datos_de_planificacion(self.e.agronomo, self.e.invernadero.pk).variedades
        self.assertTrue(all(v.compatible for v in filas))
        self.assertIn(rara.pk, [v.variedad_id for v in filas])

    def test_paso_4_y_ext_5a_una_variedad_no_compatible_dice_que_variables_y_con_que_lotes_u_ordenes(self):
        """Paso 4 y extensión 5a: la no compatible indica qué variable entra en conflicto y con qué lote activo u orden «a realizar»."""
        lote = lote_activo(self.e, cantidad=10)
        orden = orden_de_siembra(self.e, plantines=5, sector="crecimiento")
        rara, _ = variedad_con_stock(self.e, "Calida", temp_ambiente_min="30", temp_ambiente_max="35")
        fila = {v.variedad_id: v for v in siembras.datos_de_planificacion(self.e.agronomo, self.e.invernadero.pk).variedades}[rara.pk]
        self.assertFalse(fila.compatible)
        self.assertEqual([c.variable for c in fila.conflictos], ["temp_ambiente"])
        self.assertIn(lote.codigo, fila.conflictos[0].texto)
        self.assertIn(orden.codigo, fila.conflictos[0].texto)

    def test_ext_5c_una_variedad_a_la_que_le_faltan_sectores_de_una_etapa_viene_deshabilitada(self):
        """Extensión 5c: si falta un sector activo o fuera de servicio de una etapa del ciclo, la variedad no se puede sembrar."""
        SectorProduccion.objects.filter(pk=self.e.sectores["floracion"].pk).update(estado_sector="inactivo")
        fila = {v.variedad_id: v for v in siembras.datos_de_planificacion(self.e.agronomo, self.e.invernadero.pk).variedades}[self.e.variedad.pk]
        self.assertIn("Floración", fila.motivo)

    def test_paso_9_ofrece_solo_sectores_de_germinacion_activos_compatibles_y_con_lugar(self):
        """Paso 9: sectores de germinación ACTIVOS, compatibles con el perfil y con capacidad libre. Un sector fuera de servicio, uno
        lleno y uno que ocupa otro perfil familiar no se ofrecen."""
        crear_sector(self.e.invernadero, "Germ libre", "germinacion", agujeros=40)
        crear_sector(self.e.invernadero, "Germ fuera", "germinacion", agujeros=40, estado="fuera_de_servicio")
        lleno = crear_sector(self.e.invernadero, "Germ lleno", "germinacion", agujeros=10)
        tomate, _ = variedad_con_stock(self.e, "Tomate", perfil="frutos_grandes")
        lote_activo(self.e, cantidad=10, sector="germinacion", variedad=tomate)  # el sector principal ya tiene otro perfil
        orden = orden_de_siembra(self.e, plantines=10, agujeros=10, con_reserva=False)
        OcupacionSector.objects.filter(orden=orden).update(sector=lleno)  # y este queda sin agujeros libres
        ofrecidos = siembras.datos_de_planificacion(self.e.agronomo, self.e.invernadero.pk, self.e.variedad.pk).sectores
        self.assertEqual({s.nombre: s.libres for s in ofrecidos}, {"Germ libre": 40})

    def test_paso_12_ofrece_insumos_adicionales_activos_sin_categorias_del_sistema_con_su_stock_libre(self):
        """Paso 12: insumos activos del invernadero que no son de las categorías del sistema, con su stock libre."""
        fertilizante = insumo_adicional(self.e, "Fertilizante", stock=50)
        insumo_adicional(self.e, "Inactivo", stock=5, activo=False)
        envase = existencia(insumo("Bandeja", tipo=categoria_del_sistema("envases"), unidad="unidad"), self.e.invernadero)
        lote(envase, 10)
        ofrecidos = siembras.datos_de_planificacion(self.e.agronomo, self.e.invernadero.pk).insumos_adicionales
        self.assertEqual([(i.existencia_id, i.stock_libre) for i in ofrecidos], [(fertilizante.pk, D("50"))])


class PlanificarSiembraTests(Base):
    # ---- Precondiciones ----

    def test_pre_a_solo_el_agronomo_a_cargo_activo_planifica(self):
        """Precondición a y requisito especial: solo el rol Agrónomo y solo sobre los invernaderos que tiene a cargo."""
        ajeno = crear_agronomo(email="ajeno@infoponia.com")
        inactivo = crear_agronomo(email="inactivo@infoponia.com")
        for actor in (crear_gerente(), self.e.capataz, ajeno):
            with self.subTest(actor=actor):
                self.assertEqual(rechazo(lambda: siembras.planificar_siembra(actor, datos(self.e))).codigo, "sin_permiso")
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(agronomo=inactivo)
        type(inactivo).objects.filter(pk=inactivo.pk).update(is_active=False)
        self.assertEqual(rechazo(lambda: siembras.planificar_siembra(inactivo, datos(self.e))).codigo, "sin_permiso")
        self.nada_creado()

    def test_pre_b_un_invernadero_inactivo_no_se_planifica(self):
        """Precondición b: el invernadero tiene que estar activo (código `invernadero_inactivo`)."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(self.rechazo().codigo, "invernadero_inactivo")
        self.nada_creado()

    def test_pre_c_una_variedad_inactiva_no_se_siembra(self):
        """Precondición c: la variedad tiene que estar activa (código `variedad_inactiva`)."""
        type(self.e.variedad).objects.filter(pk=self.e.variedad.pk).update(estado_variedad="inactivo")
        self.assertEqual(self.rechazo().codigo, "variedad_inactiva")
        self.nada_creado()

    def test_ext_3a_sin_capataz_activo_no_se_planifica(self):
        """Extensión 3a (el CU manda sobre el prototipo, que solo avisaba): sin Capataz asignado o con el Capataz inactivo, se bloquea."""
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.assertEqual(self.rechazo().codigo, "sin_capataz_activo")
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=True)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(capataz=None)
        self.assertEqual(self.rechazo().codigo, "sin_capataz_activo")
        self.nada_creado()

    # ---- Umbral efectivo (compatibilidad de la variedad) ----

    def test_regla_umbral_efectivo_sin_lotes_ni_ordenes_cualquier_variedad_es_compatible(self):
        """Regla «Umbral efectivo» y extensión 4a: sin lotes activos ni órdenes «a realizar», el umbral es vacío y todo es compatible."""
        rara, _ = variedad_con_stock(self.e, "Calida", temp_ambiente_min="30", temp_ambiente_max="35")
        orden = self.planificar(variedad_id=rara.pk)
        self.assertEqual(orden.variedad_id, rara.pk)

    def test_regla_umbral_efectivo_con_un_lote_activo_rechaza_una_variedad_con_rangos_que_no_se_superponen(self):
        """Regla «Umbral efectivo» y extensión 5a: con un lote activo de 18-24 °C, una variedad de 30-35 °C es no compatible; el mensaje
        nombra la variable y el lote con el que choca. Se aplica aunque el invernadero no tenga IoT."""
        lote = lote_activo(self.e, cantidad=10)
        rara, _ = variedad_con_stock(self.e, "Calida", temp_ambiente_min="30", temp_ambiente_max="35")
        error = self.rechazo(variedad_id=rara.pk)
        self.assertEqual((error.codigo, error.campo), ("variedad_incompatible", "variedad"))
        self.assertIn("temperatura ambiente", error.mensaje.lower())
        self.assertIn(lote.codigo, error.mensaje)
        self.nada_creado_salvo_el_lote()

    def test_regla_umbral_efectivo_cuenta_tambien_las_ordenes_de_siembra_a_realizar(self):
        """Regla «Umbral efectivo»: el umbral sale de lotes activos Y de órdenes «a realizar»; una cancelada ya no cuenta."""
        orden = orden_de_siembra(self.e, plantines=5, sector="crecimiento")
        rara, _ = variedad_con_stock(self.e, "Calida", temp_ambiente_min="30", temp_ambiente_max="35")
        error = self.rechazo(variedad_id=rara.pk)
        self.assertEqual(error.codigo, "variedad_incompatible")
        self.assertIn(orden.codigo, error.mensaje)
        OrdenTrabajo.objects.filter(pk=orden.pk).update(
            estado_orden="cancelada", fecha_resolucion_orden=hoy(), motivo_cancelacion="x"
        )
        self.assertEqual(self.planificar(variedad_id=rara.pk).variedad_id, rara.pk)

    def test_regla_umbral_efectivo_una_variedad_con_rangos_que_se_superponen_es_compatible(self):
        """Regla «Umbral efectivo»: es compatible si, al sumarla, ninguna intersección queda vacía (20-26 °C con 18-24 °C)."""
        lote_activo(self.e, cantidad=10)
        parecida, _ = variedad_con_stock(self.e, "Parecida", temp_ambiente_min="20", temp_ambiente_max="26")
        self.assertEqual(self.planificar(variedad_id=parecida.pk).variedad_id, parecida.pk)

    def nada_creado_salvo_el_lote(self):
        """Como `nada_creado`, pero con el lote activo que armó la prueba (su siembra, su ocupación y su orden concretada)."""
        self.assertEqual(OrdenTrabajo.objects.filter(estado_orden="a_realizar").count(), 0)
        self.assertEqual(ReservaInsumo.objects.count(), 0)
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="planificacion_siembra").exists())

    # ---- Semilla y stock libre ----

    def test_ext_8b_la_semilla_sin_habilitar_se_rechaza_y_habilitada_al_vuelo_el_caso_continua(self):
        """Extensión 8b: semilla no habilitada → `semilla_no_habilitada`. Después de habilitarla con CMP-HAB-IIN, la verificación pasa
        al paso siguiente (sin stock, ahora el rechazo es `stock_insuficiente`)."""
        nueva, _ = variedad_con_stock(self.e, "Nueva", habilitar=False)
        error = self.rechazo(variedad_id=nueva.pk)
        self.assertEqual((error.codigo, error.campo), ("semilla_no_habilitada", "variedad"))
        insumos_invernadero.habilitar_insumo(self.e.agronomo, nueva.semilla.pk, self.e.invernadero.pk, "0", "2.00")
        self.assertEqual(self.rechazo(variedad_id=nueva.pk).codigo, "stock_insuficiente")

    def test_ext_8c_stock_libre_justo_pasa_y_uno_menos_se_rechaza(self):
        """Extensión 8c y regla «Stock libre»: con 50 semillas libres se planifican 50; con 49 no (`stock_insuficiente`, campo cantidad)."""
        justo = invernadero_con_produccion(nombre="Justo", sufijo="2", stock_de_semillas=50)
        self.assertEqual(siembras.planificar_siembra(justo.agronomo, datos(justo)).cant_plantines_siembra, 50)
        corto = invernadero_con_produccion(nombre="Corto", sufijo="3", stock_de_semillas=49)
        error = rechazo(lambda: siembras.planificar_siembra(corto.agronomo, datos(corto)))
        self.assertEqual((error.codigo, error.campo), ("stock_insuficiente", "cantidad"))
        self.assertIn("49", error.mensaje)

    def test_regla_stock_libre_descuenta_las_reservas_activas(self):
        """Regla «Stock libre»: cantidad actual − reservas «activas». Con 960 reservadas quedan 40 libres y 50 no alcanzan."""
        orden_de_siembra(self.e, plantines=960, agujeros=10)
        self.assertEqual(self.rechazo().codigo, "stock_insuficiente")

    def test_regla_stock_libre_no_cuenta_los_lotes_vencidos_a_la_fecha_programada(self):
        """Regla «Stock libre»: sin los lotes vencidos a la fecha programada. Un lote que vence en 2 días no cubre una siembra
        programada para dentro de 10; sí una para mañana."""
        LoteInsumo.objects.filter(pk=self.e.lote_de_semillas.pk).update(fecha_vencimiento=hoy() + timedelta(days=2))
        self.assertEqual(self.rechazo(fecha_programada=hoy() + timedelta(days=10)).codigo, "stock_insuficiente")
        self.assertEqual(self.planificar(fecha_programada=hoy() + timedelta(days=1)).cant_plantines_siembra, 50)

    # ---- Fecha y cantidad ----

    def test_ext_8a_la_fecha_pasada_se_rechaza_y_hoy_se_acepta(self):
        """Extensión 8a y regla 8 del flujo: la fecha programada es igual o posterior a hoy (`fecha_invalida`, campo fecha_programada)."""
        error = self.rechazo(fecha_programada=hoy() - timedelta(days=1))
        self.assertEqual((error.codigo, error.campo), ("fecha_invalida", "fecha_programada"))
        self.assertEqual(self.planificar(fecha_programada=hoy()).fecha_programada_orden, hoy())

    def test_regla_7a_la_cantidad_es_un_entero_positivo(self):
        """Variación 7a: la cantidad de plantines es un entero positivo (`cantidad_invalida`, campo cantidad)."""
        for cantidad in (0, -5, "abc", 2.5):
            with self.subTest(cantidad=cantidad):
                self.assertEqual(self.rechazo(cantidad=cantidad, distribucion=((self.e.sectores["germinacion"].pk, 1),)).codigo, "cantidad_invalida")
        self.nada_creado()

    def test_regla_prioridad_y_descripcion_se_validan(self):
        """Paso 7 y 15: la prioridad es alta, media o baja (o ninguna) y la descripción tiene hasta 500 caracteres."""
        self.assertEqual(self.rechazo(prioridad="urgente").codigo, "prioridad_invalida")
        self.assertEqual(self.rechazo(descripcion="x" * 501).codigo, "descripcion_larga")
        self.assertEqual(self.planificar(descripcion="x" * 500, prioridad="baja").descripcion_orden, "x" * 500)

    # ---- Capacidad ----

    def test_ext_5c_falta_un_sector_activo_o_fuera_de_servicio_de_una_etapa_del_ciclo(self):
        """Extensión 5c y regla «Capacidad por etapa»: sin sector de alguna etapa del ciclo no se planifica (`capacidad_insuficiente`,
        campo variedad); un sector inactivo no cuenta, uno fuera de servicio sí."""
        SectorProduccion.objects.filter(pk=self.e.sectores["floracion"].pk).update(estado_sector="inactivo")
        error = self.rechazo()
        self.assertEqual((error.codigo, error.campo), ("capacidad_insuficiente", "variedad"))
        self.assertIn("Floración", error.mensaje)
        SectorProduccion.objects.filter(pk=self.e.sectores["floracion"].pk).update(estado_sector="fuera_de_servicio")
        self.assertEqual(self.planificar().cant_plantines_siembra, 50)

    def test_ext_8d_la_cantidad_supera_los_agujeros_de_una_etapa_y_el_mensaje_dice_el_maximo(self):
        """Extensión 8d y regla «Capacidad por etapa»: 50 plantines no entran en Maduración (30 agujeros): el mensaje dice la etapa y el
        máximo (30). Un sector fuera de servicio cuenta para este tope, aunque no se ofrezca para ubicar plantines."""
        SectorProduccion.objects.filter(pk=self.e.sectores["maduracion"].pk).update(cant_agujeros_total=30)
        error = self.rechazo()
        self.assertEqual((error.codigo, error.campo), ("capacidad_insuficiente", "cantidad"))
        self.assertIn("Maduración", error.mensaje)
        self.assertIn("30", error.mensaje)
        crear_sector(self.e.invernadero, "Mad fuera", "maduracion", agujeros=100, estado="fuera_de_servicio")
        self.assertEqual(self.planificar().cant_plantines_siembra, 50)

    def test_ext_8e_la_cantidad_supera_la_capacidad_libre_total_de_germinacion(self):
        """Extensión 8e: con 80 agujeros comprometidos de 100, la capacidad libre es 20 y 50 plantines no entran (campo cantidad)."""
        orden_de_siembra(self.e, plantines=80)
        error = self.rechazo()
        self.assertEqual((error.codigo, error.campo), ("capacidad_insuficiente", "cantidad"))
        self.assertIn("20", error.mensaje)

    def test_ext_5b_sin_sectores_de_germinacion_con_lugar_se_rechaza_la_variedad(self):
        """Extensión 5b: si ningún sector de germinación activo tiene capacidad libre, el rechazo es de la variedad (campo variedad)."""
        orden_de_siembra(self.e, plantines=100)
        error = self.rechazo()
        self.assertEqual((error.codigo, error.campo), ("capacidad_insuficiente", "variedad"))

    def test_regla_perfil_familiar_un_sector_con_otro_perfil_no_es_compatible(self):
        """Regla «Compatibilidad por perfil familiar»: un sector con lotes de otro perfil no se elige (`sector_no_elegible`); uno vacío sí."""
        tomate, _ = variedad_con_stock(self.e, "Tomate", perfil="frutos_grandes")
        lote_activo(self.e, cantidad=10, sector="germinacion", variedad=tomate)
        vacio = crear_sector(self.e.invernadero, "Germ 2", "germinacion", agujeros=100)
        error = self.rechazo(distribucion=((self.e.sectores["germinacion"].pk, 50),))
        self.assertEqual((error.codigo, error.campo), ("sector_no_elegible", "distribucion"))
        self.assertEqual(self.planificar(distribucion=((vacio.pk, 50),)).ocupaciones.get().sector_id, vacio.pk)

    def test_regla_perfil_familiar_un_sector_con_ordenes_del_mismo_perfil_si_es_compatible(self):
        """Regla «Compatibilidad por perfil familiar»: si todo lo que hay pertenece al mismo perfil que la variedad, es compatible."""
        orden_de_siembra(self.e, plantines=10)
        self.assertEqual(self.planificar(cantidad=20, distribucion=((self.e.sectores["germinacion"].pk, 20),)).cant_plantines_siembra, 20)

    def test_ext_11_un_sector_que_no_es_de_germinacion_activo_del_invernadero_no_se_elige(self):
        """Paso 9: solo sectores de germinación ACTIVOS del invernadero. Otro tipo de etapa, fuera de servicio, de otro invernadero o
        inexistente → `sector_no_elegible`."""
        fuera = crear_sector(self.e.invernadero, "Germ fuera", "germinacion", agujeros=100, estado="fuera_de_servicio")
        ajeno = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2")
        for sector_id in (self.e.sectores["crecimiento"].pk, fuera.pk, ajeno.sectores["germinacion"].pk, 999999):
            with self.subTest(sector=sector_id):
                self.assertEqual(self.rechazo(distribucion=((sector_id, 50),)).codigo, "sector_no_elegible")
        self.nada_creado()

    def test_ext_11a_la_cantidad_de_un_sector_supera_su_capacidad_libre(self):
        """Extensión 11a: 30 plantines en un sector con 20 libres se rechazan e informan la capacidad libre (campo distribucion)."""
        otro = crear_sector(self.e.invernadero, "Germ 2", "germinacion", agujeros=100)
        orden_de_siembra(self.e, plantines=80)
        error = self.rechazo(distribucion=((self.e.sectores["germinacion"].pk, 30), (otro.pk, 20)))
        self.assertEqual((error.codigo, error.campo), ("capacidad_insuficiente", "distribucion"))
        self.assertIn("20", error.mensaje)

    def test_ext_11b_y_paso_11_la_distribucion_tiene_que_sumar_exactamente_la_cantidad(self):
        """Extensión 11b y paso 11: lo distribuido suma la cantidad de plantines; si falta o sobra, `distribucion_incompleta`."""
        otro = crear_sector(self.e.invernadero, "Germ 2", "germinacion", agujeros=100)
        g = self.e.sectores["germinacion"].pk
        for distribucion in (((g, 30),), ((g, 40), (otro.pk, 20)), ()):
            with self.subTest(distribucion=distribucion):
                self.assertEqual(self.rechazo(distribucion=distribucion).codigo, "distribucion_incompleta")
        self.nada_creado()

    def test_post_b_la_distribucion_en_varios_sectores_crea_una_ocupacion_por_sector(self):
        """Postcondición b: una ocupación por sector con los agujeros planificados y los ocupados en cero; suman la cantidad."""
        otro = crear_sector(self.e.invernadero, "Germ 2", "germinacion", agujeros=100)
        orden = self.planificar(distribucion=((self.e.sectores["germinacion"].pk, 30), (otro.pk, 20)))
        ocupaciones = {o.sector_id: o for o in orden.ocupaciones.all()}
        self.assertEqual({k: (o.cant_agujeros_planificados, o.cant_agujeros_ocupados) for k, o in ocupaciones.items()},
                         {self.e.sectores["germinacion"].pk: (30, 0), otro.pk: (20, 0)})
        self.assertEqual(sum(o.cant_agujeros_planificados for o in ocupaciones.values()), 50)

    # ---- Insumos adicionales ----

    def test_post_e_los_insumos_adicionales_se_reservan_con_la_cantidad_indicada(self):
        """Postcondición e: una reserva «activa» por cada insumo adicional, con la cantidad indicada y la fecha de hoy."""
        fertilizante = insumo_adicional(self.e, "Fertilizante", stock=50)
        orden = self.planificar(insumos_adicionales=((fertilizante.pk, D("12.5")),))
        reserva = orden.reservas.get(insumo_invernadero=fertilizante)
        self.assertEqual((reserva.cantidad_reservada, reserva.estado, reserva.fecha_reserva), (D("12.5"), "activa", hoy()))
        self.assertEqual(orden.reservas.count(), 2)

    def test_ext_13a_sin_insumos_adicionales_se_reserva_solo_la_semilla(self):
        """Extensión 13a: sin insumos adicionales, la orden reserva únicamente la semilla."""
        self.assertEqual(self.planificar().reservas.count(), 1)

    def test_ext_14a_un_insumo_adicional_que_supera_su_stock_libre_se_rechaza(self):
        """Extensión 14a y regla «Stock libre»: 60 de un insumo con 50 libres → `stock_insuficiente` (campo insumos_adicionales) con el stock libre."""
        fertilizante = insumo_adicional(self.e, "Fertilizante", stock=50)
        error = self.rechazo(insumos_adicionales=((fertilizante.pk, D("60")),))
        self.assertEqual((error.codigo, error.campo), ("stock_insuficiente", "insumos_adicionales"))
        self.assertIn("50", error.mensaje)
        self.nada_creado()

    def test_regla_insumos_adicionales_no_pueden_ser_de_las_categorias_del_sistema_ni_inactivos(self):
        """Regla «Insumos adicionales»: activos del invernadero y fuera de las categorías del sistema (`insumo_no_elegible`)."""
        envase = existencia(insumo("Bandeja", tipo=categoria_del_sistema("envases"), unidad="unidad"), self.e.invernadero)
        lote(envase, 10)
        inactivo = insumo_adicional(self.e, "Inactivo", stock=5, activo=False)
        ajeno = insumo_adicional(invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2"), "De otro", stock=5)
        for existencia_id in (envase.pk, self.e.existencia_semilla.pk, inactivo.pk, ajeno.pk):
            with self.subTest(existencia=existencia_id):
                error = self.rechazo(insumos_adicionales=((existencia_id, D("1")),))
                self.assertEqual((error.codigo, error.campo), ("insumo_no_elegible", "insumos_adicionales"))
        self.nada_creado()

    def test_regla_13a_la_cantidad_de_un_insumo_adicional_respeta_los_decimales_de_su_unidad(self):
        """Variación 13a: la cantidad se expresa en la unidad del insumo; una unidad entera no admite decimales (`cantidad_invalida`)."""
        bandejas = insumo_adicional(self.e, "Turba en bolsas", stock=50, unidad="unidad")
        for cantidad in (D("1.5"), D("0"), D("-1")):
            with self.subTest(cantidad=cantidad):
                self.assertEqual(self.rechazo(insumos_adicionales=((bandejas.pk, cantidad),)).codigo, "cantidad_invalida")

    # ---- 18a: duplicados ----

    def test_ext_18a_una_orden_identica_se_rechaza_e_informa_la_existente(self):
        """Extensión 18a: una orden con los mismos valores en todos sus atributos se rechaza con el código de la existente."""
        primera = self.planificar(prioridad="alta", descripcion="Lote de prueba")
        error = self.rechazo(prioridad="alta", descripcion="Lote de prueba")
        self.assertEqual(error.codigo, "orden_duplicada")
        self.assertIn(primera.codigo, error.mensaje)
        self.assertEqual(Siembra.objects.count(), 1)

    def test_ext_18a_con_otra_prioridad_ya_no_es_un_duplicado(self):
        """Extensión 18a: basta que un atributo cambie (la prioridad) para que sea otra orden; los números son distintos y crecientes."""
        primera = self.planificar(prioridad="alta")
        segunda = self.planificar(prioridad="baja")
        self.assertGreater(segunda.numero, primera.numero)
        self.assertEqual(segunda.codigo, f"OT-{segunda.numero:04d}")

    # ---- 18b: se repite todo bajo bloqueo ----

    def test_ext_18b_planificar_repite_las_verificaciones_aunque_el_resumen_haya_pasado(self):
        """Extensión 18b: entre el resumen y la confirmación otra operación consumió el stock; `planificar_siembra` lo vuelve a verificar
        y rechaza sin crear nada."""
        siembras.resumen_de_planificacion(self.e.agronomo, datos(self.e))
        LoteInsumo.objects.filter(pk=self.e.lote_de_semillas.pk).update(cantidad_disponible=10)
        self.assertEqual(self.rechazo().codigo, "stock_insuficiente")
        self.nada_creado()

    def test_ext_18b_planificar_vuelve_a_verificar_la_compatibilidad_y_la_capacidad(self):
        """Extensión 18b: si cambió la compatibilidad (entró un lote incompatible) o el espacio, el rechazo es el del dato que cambió."""
        rara, _ = variedad_con_stock(self.e, "Calida", temp_ambiente_min="30", temp_ambiente_max="35")
        siembras.resumen_de_planificacion(self.e.agronomo, datos(self.e, variedad_id=rara.pk))
        lote_activo(self.e, cantidad=10)
        self.assertEqual(self.rechazo(variedad_id=rara.pk).codigo, "variedad_incompatible")
        orden_de_siembra(self.e, plantines=80, sector="germinacion", variedad=self.e.variedad, con_reserva=False)
        self.assertEqual(self.rechazo().codigo, "capacidad_insuficiente")

    # ---- Postcondiciones a, c, d, f, g, h, i ----

    def test_post_a_la_orden_nace_a_realizar_con_todos_sus_datos(self):
        """Postcondición a: orden de siembra «a realizar» con fecha de creación (hoy), programada, plantines, prioridad, descripción,
        invernadero, variedad, Agrónomo que la planificó y Capataz del invernadero. `cant_plantines_siembra` y el Agrónomo quedan."""
        orden = self.planificar(prioridad="media", descripcion="Primera tanda", fecha_programada=hoy() + timedelta(days=5))
        orden = Siembra.objects.get(pk=orden.pk)
        self.assertEqual(
            (orden.tipo_orden, orden.estado_orden, orden.fecha_creacion_orden, orden.fecha_programada_orden, orden.cant_plantines_siembra),
            ("siembra", "a_realizar", hoy(), hoy() + timedelta(days=5), 50),
        )
        self.assertEqual((orden.prioridad_orden, orden.descripcion_orden), ("media", "Primera tanda"))
        self.assertEqual(
            (orden.invernadero_id, orden.variedad_id, orden.agronomo_id, orden.capataz_id),
            (self.e.invernadero.pk, self.e.variedad.pk, self.e.agronomo.pk, self.e.capataz.pk),
        )
        self.assertIsNone(orden.fecha_resolucion_orden)
        self.assertIsNone(orden.fecha_siembra)

    def test_post_c_los_agujeros_comprometidos_del_sector_aumentan_y_los_ocupados_no(self):
        """Postcondición c: en cada sector seleccionado, los agujeros comprometidos suben en lo planificado; el stock actual y los
        agujeros ocupados no cambian (garantías mínimas)."""
        sector = self.e.sectores["germinacion"]
        antes = api_sectores.agujeros_de([sector])[sector.pk]
        self.planificar()
        despues = api_sectores.agujeros_de([sector])[sector.pk]
        self.assertEqual((despues.comprometidos - antes.comprometidos, despues.ocupados), (50, antes.ocupados))
        self.assertEqual(LoteInsumo.objects.get(pk=self.e.lote_de_semillas.pk).cantidad_disponible, D("1000"))

    def test_post_d_la_semilla_se_reserva_por_la_cantidad_de_plantines(self):
        """Postcondición d: reserva «activa» de la semilla con cantidad = plantines y fecha de reserva = hoy, asociada a la orden y a su
        insumo del invernadero."""
        reserva = self.planificar().reservas.get()
        self.assertEqual(
            (reserva.insumo_invernadero_id, reserva.cantidad_reservada, reserva.estado, reserva.fecha_reserva, reserva.cantidad_utilizada),
            (self.e.existencia_semilla.pk, D("50"), "activa", hoy(), None),
        )

    def test_post_f_se_notifica_al_capataz_con_el_codigo_de_la_orden(self):
        """Postcondición f: el Capataz recibe una notificación de la nueva orden (dentro de la transacción, D-42)."""
        orden = self.planificar()
        notificacion = Notificacion.objects.get(destinatario=self.e.capataz)
        self.assertIn(orden.codigo, notificacion.titulo)
        self.assertIn(self.e.invernadero.nombre_invernadero, notificacion.detalle)
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_post_g_h_i_un_solo_registro_de_auditoria_con_todo_lo_creado_y_el_cambio_de_los_sectores(self):
        """Postcondiciones g, h e i (D-36, un registro por caso de uso): `planificacion_siembra` con la orden, cada ocupación, cada reserva
        y cada sector como afectados, y el cambio de «agujeros comprometidos» de cada sector (antes → después, como texto)."""
        fertilizante = insumo_adicional(self.e, "Fertilizante", stock=50)
        orden = self.planificar(insumos_adicionales=((fertilizante.pk, D("5")),))
        registro = RegistroAuditoria.objects.get(accion="planificacion_siembra")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="planificacion_siembra").count(), 1)
        self.assertEqual(registro.usuario_id, self.e.agronomo.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        esperados = {("produccion.siembra", orden.pk), ("maestros.sectorproduccion", self.e.sectores["germinacion"].pk)}
        esperados |= {("produccion.ocupacionsector", o.pk) for o in orden.ocupaciones.all()}
        esperados |= {("produccion.reservainsumo", r.pk) for r in orden.reservas.all()}
        self.assertLessEqual(esperados, afectados)
        cambio = registro.detalle["cambios"]["agujeros_comprometidos"]
        self.assertEqual(cambio["antes"], [f"{self.e.sectores['germinacion'].nombre_sector}: 0"])
        self.assertEqual(cambio["despues"], [f"{self.e.sectores['germinacion'].nombre_sector}: 50"])
        self.assertEqual(registro.detalle["datos"]["cant_plantines_siembra"], "50")

    # ---- Todo o nada ----

    def test_garantia_un_error_en_el_medio_no_deja_nada_creado(self):
        """Garantías mínimas y D-22: si algo falla después de escribir (acá, el aviso al Capataz), no queda ninguna orden, ocupación,
        reserva, notificación ni registro de auditoría."""
        fertilizante = insumo_adicional(self.e, "Fertilizante", stock=50)
        with mock.patch("core.notificaciones.notificar", side_effect=RuntimeError("falla del aviso")):
            with self.assertRaises(RuntimeError):
                self.planificar(insumos_adicionales=((fertilizante.pk, D("5")),))
        self.nada_creado()

    def test_garantia_el_stock_y_los_agujeros_no_cambian_cualquiera_sea_el_final(self):
        """Garantías mínimas: planificar no toca el stock actual ni los agujeros ocupados, ni con éxito ni con rechazo."""
        self.rechazo(cantidad=5000, distribucion=((self.e.sectores["germinacion"].pk, 5000),))
        self.planificar()
        self.assertEqual(LoteInsumo.objects.get(pk=self.e.lote_de_semillas.pk).cantidad_disponible, D("1000"))
        self.assertEqual(sum(o.cant_agujeros_ocupados for o in OcupacionSector.objects.all()), 0)


class ResumenDePlanificacionTests(Base):
    """Paso 16: el resumen valida igual que la planificación y no escribe nada."""

    def test_paso_16_el_resumen_trae_la_fecha_estimada_de_cosecha_la_distribucion_el_capataz_y_las_reservas(self):
        """Paso 16 y regla «Fecha estimada de cosecha»: programada + días hasta Maduración (4 etapas de 10 días = 40), la distribución,
        el Capataz y las reservas (la semilla y los insumos adicionales)."""
        fertilizante = insumo_adicional(self.e, "Fertilizante", stock=50)
        otro = crear_sector(self.e.invernadero, "Germ 2", "germinacion", agujeros=100)
        fecha = hoy() + timedelta(days=7)
        resumen = siembras.resumen_de_planificacion(
            self.e.agronomo,
            datos(self.e, fecha_programada=fecha, distribucion=((self.e.sectores["germinacion"].pk, 30), (otro.pk, 20)),
                  prioridad="alta", insumos_adicionales=((fertilizante.pk, D("5")),)),
        )
        self.assertEqual(resumen.fecha_estimada_de_cosecha, fecha + timedelta(days=40))
        self.assertEqual([(s.pk, n) for s, n in resumen.distribucion], [(self.e.sectores["germinacion"].pk, 30), (otro.pk, 20)])
        self.assertEqual(resumen.capataz.pk, self.e.capataz.pk)
        self.assertEqual((resumen.cantidad, resumen.prioridad, str(resumen.variedad)), (50, "alta", str(self.e.variedad)))
        self.assertEqual(resumen.reservas[0].cantidad, D("50"))
        self.assertEqual(len(resumen.reservas), 2)

    def test_paso_16_el_resumen_no_escribe_nada(self):
        """Paso 16: el resumen no crea órdenes, ni numera, ni audita, ni notifica."""
        siembras.resumen_de_planificacion(self.e.agronomo, datos(self.e))
        self.assertEqual(OrdenTrabajo.objects.count() + ReservaInsumo.objects.count() + Notificacion.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="planificacion_siembra").exists())

    def test_paso_16_el_resumen_rechaza_lo_mismo_que_la_planificacion(self):
        """El resumen valida todo: los mismos códigos y campos que `planificar_siembra` (semilla, stock, fecha, capacidad)."""
        error = rechazo(lambda: siembras.resumen_de_planificacion(self.e.agronomo, datos(self.e, fecha_programada=hoy() - timedelta(days=1))))
        self.assertEqual((error.codigo, error.campo), ("fecha_invalida", "fecha_programada"))
        error = rechazo(lambda: siembras.resumen_de_planificacion(
            self.e.agronomo, datos(self.e, cantidad=2000, distribucion=((self.e.sectores["germinacion"].pk, 2000),))))
        self.assertEqual(error.codigo, "stock_insuficiente")
