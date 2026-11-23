# Pruebas de PROD-PNF-TRN · Planificar Transición (PRD-02, paso 4; docs/casos_de_uso/produccion/transicion.md, «Cómo se aplica en la ronda»).
#
# Servicios que se prueban (produccion/servicios/transiciones.py):
# - datos_de_planificacion(actor, lote_id=None, fecha=None): lo que presentan los pasos 2 a 7 (los lotes con su motivo si no se pueden
#   elegir; con `lote_id`, la etapa destino, la cantidad, el Capataz, la fecha propuesta, los sectores elegibles y los que no, con su
#   motivo; con `fecha`, la diferencia con el fin estimado y la fecha máxima de cosecha). No escribe ni bloquea.
# - resumen_de_planificacion(actor, datos): valida TODO y devuelve el resumen del paso 11 SIN escribir ni bloquear.
# - planificar_transicion(actor, datos) -> TransicionEtapa: lo mismo, y repite TODAS las verificaciones bajo bloqueo (extensión 13) antes
#   de escribir (todo o nada, D-22). Los rechazos son `ErrorDeProduccion(codigo, mensaje, campo, datos)`.
# - asignar_sector(distribucion, sector_id, plantas) y por_distribuir(cantidad, distribucion): los pasos 8 y 9 (y 8-9a y 8-9b) que usa
#   la pantalla; son funciones puras.
# - DatosDeTransicion(lote_id, fecha_programada, distribucion=((sector_id, plantas), ...), prioridad=None, descripcion="", cantidad=None,
#   etapa_actual_id=None). `cantidad` y `etapa_actual_id` son lo que la persona vio (la cantidad actual del lote y su etapa): si cambiaron
#   al confirmar, `cambio_simultaneo` con el dato nuevo (extensiones 13a y 13b); `None` no lo verifica.
#
# Códigos y campos: sin_permiso; invernadero_inactivo; lote_no_trasladable (última etapa, lote finalizado o con otra etapa); lote_con_transicion
# (3a y 13a; `datos` con el código y la fecha de la orden); sin_capataz_activo (3b y 13d); capacidad_insuficiente (3c, 9a y 13c);
# sector_no_elegible (distribucion); fecha_invalida (fecha_programada; 6a); cantidad_invalida (distribucion); distribucion_incompleta
# (distribucion; 9b y 10a); cambio_simultaneo (13a y 13b; `datos` con `cantidad_actual` o `etapa_actual`); prioridad_invalida;
# descripcion_larga.
#
# Una prueba por regla y por postcondición a a g. Cada prueba arma sus propios datos y viola UNA sola regla.

from datetime import timedelta
from unittest import mock

from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from core.models import Capataz, Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, variedad_con_semilla
from maestros.models import Invernadero, SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import crear_agronomo, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.models import Lote, OcupacionSector, OrdenTrabajo, ReservaInsumo, TransicionEtapa
from produccion.servicios import transiciones
from produccion.tests.fabricas import (
    CODIGOS_DE_ETAPA,
    invernadero_con_produccion,
    lote_con_ciclo,
    orden_de_transicion,
)


def hoy():
    return timezone.localdate()


def datos(e, lote, **cambios):
    """`DatosDeTransicion` válidos: el lote entero (50 plantas, en Crecimiento desde hoy) al sector de Floración, para el fin estimado de
    su etapa (dentro de 10 días), con lo que la persona vio (cantidad y etapa actual)."""
    base = dict(
        lote_id=lote.pk,
        fecha_programada=hoy() + timedelta(days=10),
        distribucion=((e.sectores["floracion"].pk, lote.cantidad_actual),),
        prioridad=None,
        descripcion="",
        cantidad=lote.cantidad_actual,
        etapa_actual_id=lote.etapa_id,
    )
    base.update(cambios)
    return transiciones.DatosDeTransicion(**base)


def rechazo(llamada):
    """Ejecuta `llamada()` y devuelve el `ErrorDeProduccion` que lanza; si no lanza ninguno, la prueba falla."""
    try:
        llamada()
    except ErrorDeProduccion as error:
        return error
    raise AssertionError("Se esperaba un ErrorDeProduccion y no se lanzó ninguno.")


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero completo (sectores de 100 agujeros) con un lote de 50 plantas en Crecimiento desde hoy, por prueba."""

    def setUp(self):
        self.e = invernadero_con_produccion()
        self.lote = lote_con_ciclo(self.e, cantidad=50)

    def datos(self, **cambios):
        return datos(self.e, self.lote, **cambios)

    def planificar(self, **cambios):
        return transiciones.planificar_transicion(self.e.agronomo, self.datos(**cambios))

    def rechazo(self, **cambios):
        return rechazo(lambda: self.planificar(**cambios))

    def nada_creado(self):
        """Verifica que no quedó ninguna orden de transición «a realizar», ni ocupación, notificación o registro de la planificación."""
        self.assertFalse(TransicionEtapa.objects.filter(estado_orden="a_realizar").exists())
        self.assertFalse(OcupacionSector.objects.filter(orden__estado_orden="a_realizar").exists())
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="planificacion_transicion").exists())

    def otro_sector(self, codigo="floracion", nombre="Sector extra", agujeros=100):
        """Un segundo sector activo del mismo tipo de etapa."""
        return crear_sector(self.e.invernadero, nombre=nombre, tipo=codigo, agujeros=agujeros)


class DatosDePlanificacionTests(Base):
    """Pasos 2 a 7: lo que ofrece la pantalla, con el motivo de lo que no se puede elegir."""

    def test_paso_2_ofrece_los_lotes_del_agronomo_con_su_motivo_si_no_se_pueden_elegir(self):
        """Paso 2 y extensiones 3a y 3b: los lotes de los invernaderos activos a cargo, con `motivo` si no se pueden trasladar."""
        otro = lote_con_ciclo(self.e, cantidad=5, etapa="maduracion")
        lotes = {f.lote_id: f for f in transiciones.datos_de_planificacion(self.e.agronomo).lotes}
        self.assertEqual(lotes[self.lote.pk].motivo, None)
        self.assertEqual(lotes[otro.pk].motivo, "ultima_etapa")

    def test_paso_4_trae_la_etapa_destino_la_cantidad_el_capataz_y_la_fecha_propuesta(self):
        """Paso 4: la etapa destino (con su duración), la cantidad del lote (igual a su cantidad actual), el Capataz del invernadero y
        la fecha propuesta, igual a la fecha estimada de fin de la etapa actual."""
        presentado = transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk)
        self.assertEqual(presentado.lote.lote_id, self.lote.pk)
        self.assertEqual((presentado.etapa_destino.codigo, presentado.etapa_destino.duracion_dias), ("floracion", 10))
        self.assertEqual(presentado.cantidad, 50)
        self.assertEqual(presentado.capataz, self.e.capataz)
        self.assertEqual(presentado.fecha_propuesta, hoy() + timedelta(days=10))
        self.assertEqual((presentado.fecha_estimada_de_fin, presentado.dias_de_atraso), (hoy() + timedelta(days=10), None))

    def test_ext_4a_con_la_fecha_estimada_vencida_propone_hoy_e_informa_los_dias_de_atraso(self):
        """Extensión 4a: si el fin estimado de la etapa es anterior a hoy, propone hoy e informa los días de atraso."""
        atrasado = lote_con_ciclo(self.e, cantidad=5, dias_en_etapa=14)  # fin estimado: hace 4 días
        presentado = transiciones.datos_de_planificacion(self.e.agronomo, lote_id=atrasado.pk)
        self.assertEqual((presentado.fecha_propuesta, presentado.dias_de_atraso), (hoy(), 4))
        self.assertEqual(presentado.fecha_estimada_de_fin, hoy() - timedelta(days=4))

    def test_paso_7_ofrece_los_sectores_elegibles_con_su_capacidad_libre(self):
        """Paso 7: los sectores activos del invernadero, del tipo de la etapa destino, compatibles y con capacidad libre, con ella."""
        extra = self.otro_sector(agujeros=30)
        lote_con_ciclo(self.e, cantidad=40, etapa="floracion")  # ocupa 40 de los 100 del sector de Floración
        sectores = {s.sector_id: s for s in transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk).sectores}
        self.assertEqual(sectores[self.e.sectores["floracion"].pk].libres, 60)
        self.assertEqual(sectores[extra.pk].libres, 30)

    def test_regla_sector_elegible_un_sector_fuera_de_servicio_no_se_ofrece_y_dice_por_que(self):
        """«Sector elegible»: un sector «fuera de servicio» no se ofrece; figura entre los no elegibles con su motivo."""
        extra = self.otro_sector()
        SectorProduccion.objects.filter(pk=self.e.sectores["floracion"].pk).update(estado_sector="fuera_de_servicio")
        presentado = transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk)
        self.assertEqual([s.sector_id for s in presentado.sectores], [extra.pk])
        self.assertEqual({n.sector_id: n.motivo for n in presentado.no_elegibles}, {self.e.sectores["floracion"].pk: "fuera_de_servicio"})

    def test_regla_perfil_familiar_un_sector_con_plantas_de_otro_perfil_no_se_ofrece_y_dice_con_que_lote(self):
        """«Compatibilidad por perfil familiar»: un sector con lotes de otro perfil no se ofrece; el motivo nombra el lote."""
        extra = self.otro_sector()
        flor = variedad_con_semilla(nombre="Petunia", perfil="flores", etapas=CODIGOS_DE_ETAPA)
        ajeno = lote_con_ciclo(self.e, cantidad=5, etapa="floracion", variedad=flor)
        presentado = transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk)
        self.assertEqual([s.sector_id for s in presentado.sectores], [extra.pk])
        incompatible = next(n for n in presentado.no_elegibles if n.sector_id == self.e.sectores["floracion"].pk)
        self.assertEqual(incompatible.motivo, "perfil_incompatible")
        self.assertIn(ajeno.codigo, incompatible.texto)

    def test_regla_perfil_familiar_un_sector_con_el_mismo_perfil_o_con_una_transicion_del_mismo_perfil_es_compatible(self):
        """«Compatibilidad por perfil familiar»: con plantas del mismo perfil, o vacío, el sector es compatible."""
        otra = variedad_con_semilla(nombre="Mantecosa", perfil="hoja_verde", etapas=CODIGOS_DE_ETAPA)
        lote_con_ciclo(self.e, cantidad=5, etapa="floracion", variedad=otra)
        sectores = transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk).sectores
        self.assertEqual([s.sector_id for s in sectores], [self.e.sectores["floracion"].pk])

    def test_regla_perfil_familiar_la_transicion_a_realizar_hacia_el_sector_cuenta_para_su_perfil(self):
        """«Compatibilidad por perfil familiar»: ampliada a las transiciones «a realizar» hacia ese sector: otra variedad de otro perfil
        no puede planificar hacia un sector donde ya hay una transición pendiente."""
        flor = variedad_con_semilla(nombre="Petunia", perfil="flores", etapas=CODIGOS_DE_ETAPA)
        ajeno = lote_con_ciclo(self.e, cantidad=5, variedad=flor)
        orden_de_transicion(self.e, ajeno)
        self.assertEqual(rechazo(lambda: transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk)).codigo, "capacidad_insuficiente")

    def test_regla_umbral_ambiental_no_se_valida(self):
        """«Umbral ambiental»: no se valida (el lote ya está en el invernadero): un sector con otra variedad de rangos incompatibles
        pero del mismo perfil se ofrece y se puede planificar."""
        calida = variedad_con_semilla(
            nombre="Calida", perfil="hoja_verde", etapas=CODIGOS_DE_ETAPA, temp_ambiente_min="30", temp_ambiente_max="35"
        )
        lote_con_ciclo(self.e, cantidad=5, etapa="floracion", variedad=calida)
        self.assertEqual(self.planificar().estado_orden, "a_realizar")

    def test_paso_7_si_la_etapa_destino_es_maduracion_trae_la_fecha_maxima_de_cosecha(self):
        """Paso 7: solo si el destino es Maduración, la fecha máxima de cosecha estimada: la programada más la duración de Maduración
        (10 días). Con otro destino, `None`."""
        e = invernadero_con_produccion(nombre="Corto", sufijo="c", etapas=("germinacion", "crecimiento", "maduracion"))
        lote = lote_con_ciclo(e, cantidad=5)
        fecha = hoy() + timedelta(days=12)
        presentado = transiciones.datos_de_planificacion(e.agronomo, lote_id=lote.pk, fecha=fecha)
        self.assertEqual(presentado.fecha_maxima_de_cosecha, fecha + timedelta(days=10))
        self.assertIsNone(
            transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk, fecha=fecha).fecha_maxima_de_cosecha
        )

    def test_ext_6b_una_fecha_distinta_de_la_estimada_informa_la_diferencia_en_dias_sin_bloquear(self):
        """Extensión 6b: «2 días después del fin estimado»: la diferencia es positiva si es posterior y negativa si es anterior;
        `0` si coincide; no bloquea."""
        fin = hoy() + timedelta(days=10)
        diferencia = lambda f: transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk, fecha=f).diferencia_en_dias
        self.assertEqual((diferencia(fin + timedelta(days=2)), diferencia(fin - timedelta(days=3)), diferencia(fin)), (2, -3, 0))

    def test_ext_3a_el_lote_con_otra_transicion_a_realizar_no_se_elige_e_informa_cual(self):
        """Extensión 3a: `lote_con_transicion`, con el identificador y la fecha programada de la orden existente."""
        orden = orden_de_transicion(self.e, self.lote, dias=4)
        error = rechazo(lambda: transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk))
        self.assertEqual(error.codigo, "lote_con_transicion")
        self.assertEqual(error.datos, {"codigo": orden.codigo, "fecha": hoy() + timedelta(days=4)})
        self.assertIn(orden.codigo, error.mensaje)

    def test_ext_3b_el_invernadero_sin_capataz_activo_no_se_elige(self):
        """Extensión 3b: `sin_capataz_activo`."""
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.assertEqual(
            rechazo(lambda: transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk)).codigo, "sin_capataz_activo"
        )

    def test_ext_3c_sin_capacidad_libre_suficiente_informa_la_capacidad_frente_a_la_cantidad(self):
        """Extensión 3c: si la capacidad libre total de los sectores elegibles es menor que la cantidad, no se puede continuar con ese
        lote: `capacidad_insuficiente` con la capacidad libre y la cantidad en `datos`."""
        lote_con_ciclo(self.e, cantidad=60, etapa="floracion")  # quedan 40 libres en Floración
        error = rechazo(lambda: transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk))
        self.assertEqual(error.codigo, "capacidad_insuficiente")
        self.assertEqual((error.datos["capacidad_libre"], error.datos["cantidad"]), (40, 50))

    def test_ext_3c_sin_sectores_elegibles_nombra_los_incompatibles_con_sus_lotes(self):
        """Extensión 3c: informa también qué sectores del tipo destino no son compatibles por perfil familiar y con qué lotes."""
        flor = variedad_con_semilla(nombre="Petunia", perfil="flores", etapas=CODIGOS_DE_ETAPA)
        ajeno = lote_con_ciclo(self.e, cantidad=5, etapa="floracion", variedad=flor)
        error = rechazo(lambda: transiciones.datos_de_planificacion(self.e.agronomo, lote_id=self.lote.pk))
        self.assertEqual((error.codigo, error.datos["capacidad_libre"]), ("capacidad_insuficiente", 0))
        self.assertIn(ajeno.codigo, error.mensaje)

    def test_pre_a_solo_el_agronomo_a_cargo_ve_los_datos(self):
        """Precondición a: otro rol, otro Agrónomo o un lote inexistente no ven nada."""
        ajeno = crear_agronomo(email="ajeno@infoponia.com")
        for actor in (crear_gerente(), self.e.capataz):
            with self.subTest(actor=actor):
                self.assertEqual(rechazo(lambda: transiciones.datos_de_planificacion(actor)).codigo, "sin_permiso")
        # Otro Agrónomo puede abrir la pantalla (no ve lotes), pero no un lote ajeno.
        self.assertEqual(transiciones.datos_de_planificacion(ajeno).lotes, [])
        self.assertEqual(rechazo(lambda: transiciones.datos_de_planificacion(ajeno, lote_id=self.lote.pk)).codigo, "sin_permiso")
        with self.assertRaises(Http404):
            transiciones.datos_de_planificacion(self.e.agronomo, lote_id=999999)


class AsignacionDeSectoresTests(Base):
    """Pasos 8 y 9 y extensiones 8-9a y 8-9b: la distribución se arma de a un sector por vez (funciones puras)."""

    def test_paso_9_la_cantidad_por_distribuir_es_la_del_lote_menos_lo_asignado(self):
        """Paso 9: «presenta la cantidad por distribuir»: al inicio, igual a la cantidad del lote."""
        a, b = 11, 22
        self.assertEqual(transiciones.por_distribuir(50, ()), 50)
        self.assertEqual(transiciones.por_distribuir(50, ((a, 30), (b, 20))), 0)
        self.assertEqual(transiciones.por_distribuir(50, ((a, 60),)), -10)

    def test_ext_8_9a_quitar_un_sector_ya_asignado_actualiza_lo_que_falta_distribuir(self):
        """Extensión 8-9a: quitar un sector (cantidad 0) elimina esa asignación."""
        distribucion = transiciones.asignar_sector(transiciones.asignar_sector((), 11, 30), 22, 20)
        self.assertEqual(distribucion, ((11, 30), (22, 20)))
        quitada = transiciones.asignar_sector(distribucion, 22, 0)
        self.assertEqual(quitada, ((11, 30),))
        self.assertEqual(transiciones.por_distribuir(50, quitada), 20)

    def test_ext_8_9b_volver_a_indicar_un_sector_reemplaza_su_cantidad_anterior(self):
        """Extensión 8-9b: la nueva cantidad reemplaza a la anterior y el sector conserva su lugar en la lista."""
        distribucion = ((11, 30), (22, 20))
        self.assertEqual(transiciones.asignar_sector(distribucion, 11, 10), ((11, 10), (22, 20)))
        self.assertEqual(distribucion, ((11, 30), (22, 20)))  # no modifica lo que recibe


class PlanificarTransicionTests(Base):
    # ---- Precondiciones ----

    def test_pre_a_solo_el_agronomo_a_cargo_activo_planifica(self):
        """Precondición a y requisito especial: solo el rol Agrónomo y solo sobre los invernaderos que tiene a cargo."""
        ajeno = crear_agronomo(email="ajeno@infoponia.com")
        inactivo = crear_agronomo(email="inactivo@infoponia.com")
        for actor in (crear_gerente(), self.e.capataz, ajeno):
            with self.subTest(actor=actor):
                self.assertEqual(rechazo(lambda: transiciones.planificar_transicion(actor, self.datos())).codigo, "sin_permiso")
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(agronomo=inactivo)
        type(inactivo).objects.filter(pk=inactivo.pk).update(is_active=False)
        self.assertEqual(rechazo(lambda: transiciones.planificar_transicion(inactivo, self.datos())).codigo, "sin_permiso")
        self.nada_creado()

    def test_pre_b_un_invernadero_inactivo_no_se_planifica(self):
        """Precondición b: el invernadero tiene que estar activo (`invernadero_inactivo`)."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(self.rechazo().codigo, "invernadero_inactivo")
        self.nada_creado()

    def test_pre_c_el_lote_tiene_que_estar_activo_con_plantas_y_no_en_la_ultima_etapa(self):
        """Precondición c y «Lote trasladable»: un lote en la última etapa, o finalizado, no se traslada (`lote_no_trasladable`)."""
        ultima = lote_con_ciclo(self.e, cantidad=5, etapa="maduracion")
        self.assertEqual(rechazo(lambda: transiciones.planificar_transicion(self.e.agronomo, datos(self.e, ultima))).codigo, "lote_no_trasladable")
        Lote.objects.filter(pk=self.lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        self.assertEqual(self.rechazo(cantidad=None, etapa_actual_id=None).codigo, "lote_no_trasladable")
        self.nada_creado()

    def test_ext_3a_un_lote_con_otra_transicion_a_realizar_no_se_planifica(self):
        """Extensión 3a y garantía «un lote tiene como máximo una orden de transición a realizar»: `lote_con_transicion`."""
        orden = orden_de_transicion(self.e, self.lote)
        error = self.rechazo()
        self.assertEqual((error.codigo, error.datos["codigo"]), ("lote_con_transicion", orden.codigo))
        self.assertEqual(TransicionEtapa.objects.filter(lote=self.lote, estado_orden="a_realizar").count(), 1)

    def test_ext_3a_una_transicion_cancelada_o_concretada_no_impide_planificar_otra(self):
        """Regla 4 de 8.21: solo cuenta la transición «a realizar»."""
        orden_de_transicion(self.e, self.lote, estado="cancelada")
        self.assertEqual(self.planificar().estado_orden, "a_realizar")

    def test_ext_3b_sin_capataz_activo_no_se_planifica(self):
        """Extensión 3b: `sin_capataz_activo`."""
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.assertEqual(self.rechazo().codigo, "sin_capataz_activo")
        self.nada_creado()

    def test_ext_3c_sin_capacidad_libre_suficiente_no_se_planifica(self):
        """Extensión 3c: la capacidad libre total de los sectores elegibles es menor que la cantidad: `capacidad_insuficiente`."""
        lote_con_ciclo(self.e, cantidad=60, etapa="floracion")
        self.assertEqual(self.rechazo().codigo, "capacidad_insuficiente")
        self.nada_creado()

    # ---- La etapa destino y las fechas ----

    def test_regla_etapa_destino_la_fija_el_sistema_con_la_etapa_siguiente_del_ciclo(self):
        """Regla 1 de 8.20 y «Etapa destino»: la siguiente en el ciclo de la variedad (Crecimiento → Floración), y en un ciclo corto,
        Maduración; el Agrónomo no la elige."""
        self.assertEqual(self.planificar().etapa_destino.tipo_etapa.codigo, "floracion")
        e = invernadero_con_produccion(nombre="Corto", sufijo="c", etapas=("germinacion", "crecimiento", "maduracion"))
        lote = lote_con_ciclo(e, cantidad=5)
        orden = transiciones.planificar_transicion(e.agronomo, datos(e, lote, distribucion=((e.sectores["maduracion"].pk, 5),)))
        self.assertEqual(orden.etapa_destino.tipo_etapa.codigo, "maduracion")

    def test_ext_6a_la_fecha_anterior_a_hoy_se_rechaza_y_hoy_se_acepta(self):
        """Extensión 6a: `fecha_invalida` (campo `fecha_programada`); hoy se acepta."""
        error = self.rechazo(fecha_programada=hoy() - timedelta(days=1))
        self.assertEqual((error.codigo, error.campo), ("fecha_invalida", "fecha_programada"))
        self.assertEqual(self.rechazo(fecha_programada=None).codigo, "fecha_invalida")
        self.nada_creado()
        self.assertEqual(self.planificar(fecha_programada=hoy()).fecha_programada_orden, hoy())

    def test_ext_6b_una_fecha_distinta_de_la_estimada_no_bloquea_e_informa_la_diferencia_en_el_resumen(self):
        """Extensión 6b: la orden se planifica igual; el resumen trae la diferencia en días con el fin estimado (2 días después)."""
        fecha = hoy() + timedelta(days=12)
        resumen = transiciones.resumen_de_planificacion(self.e.agronomo, self.datos(fecha_programada=fecha))
        self.assertEqual((resumen.diferencia_en_dias, resumen.fecha_estimada_de_fin), (2, hoy() + timedelta(days=10)))
        self.assertEqual(self.planificar(fecha_programada=fecha).fecha_programada_orden, fecha)

    def test_regla_fecha_maxima_de_cosecha_solo_si_el_destino_es_maduracion(self):
        """«Fecha máxima de cosecha estimada» (pasos 7 y 11): la programada más la duración de Maduración, solo si el destino es
        Maduración; si no, `None`."""
        self.assertIsNone(transiciones.resumen_de_planificacion(self.e.agronomo, self.datos()).fecha_maxima_de_cosecha)
        e = invernadero_con_produccion(nombre="Corto", sufijo="c", etapas=("germinacion", "crecimiento", "maduracion"))
        lote = lote_con_ciclo(e, cantidad=5)
        fecha = hoy() + timedelta(days=12)
        resumen = transiciones.resumen_de_planificacion(
            e.agronomo, datos(e, lote, fecha_programada=fecha, distribucion=((e.sectores["maduracion"].pk, 5),))
        )
        self.assertEqual(resumen.fecha_maxima_de_cosecha, fecha + timedelta(days=10))

    # ---- La distribución ----

    def test_ext_9a_la_cantidad_de_un_sector_supera_su_capacidad_libre(self):
        """Extensión 9a: `capacidad_insuficiente` (campo `distribucion`), informando la capacidad libre del sector."""
        lote_con_ciclo(self.e, cantidad=60, etapa="floracion")  # el sector de Floración queda con 40 libres
        extra = self.otro_sector(agujeros=100)
        error = self.rechazo(distribucion=((self.e.sectores["floracion"].pk, 45), (extra.pk, 5)))
        self.assertEqual((error.codigo, error.campo), ("capacidad_insuficiente", "distribucion"))
        self.assertIn("40", error.mensaje)

    def test_ext_9b_la_cantidad_indicada_supera_lo_que_resta_por_distribuir(self):
        """Extensión 9b: distribuir más que la cantidad del lote: `distribucion_incompleta`, que informa la diferencia."""
        extra = self.otro_sector()
        error = self.rechazo(distribucion=((self.e.sectores["floracion"].pk, 40), (extra.pk, 20)))
        self.assertEqual((error.codigo, error.campo), ("distribucion_incompleta", "distribucion"))
        self.assertIn("10", error.mensaje)

    def test_ext_10a_terminar_con_cantidad_por_distribuir_mayor_que_cero_se_rechaza(self):
        """Extensión 10a: la distribución tiene que sumar exactamente la cantidad del lote; faltan 5."""
        error = self.rechazo(distribucion=((self.e.sectores["floracion"].pk, 45),))
        self.assertEqual((error.codigo, error.campo), ("distribucion_incompleta", "distribucion"))
        self.assertEqual(self.rechazo(distribucion=()).codigo, "distribucion_incompleta")

    def test_regla_distribucion_cada_sector_se_usa_una_vez_con_una_cantidad_entera_positiva(self):
        """Paso 8 y «Cantidades» (8a): números enteros positivos; un sector repetido, cero o no entero: `cantidad_invalida`."""
        sector = self.e.sectores["floracion"].pk
        for distribucion in (((sector, 25), (sector, 25)), ((sector, 0),), ((sector, -5),), ((sector, 2.5),)):
            with self.subTest(distribucion=distribucion):
                self.assertEqual(self.rechazo(distribucion=distribucion).codigo, "cantidad_invalida")

    def test_regla_sector_elegible_solo_los_de_la_etapa_destino_activos_y_del_invernadero(self):
        """«Sector elegible»: un sector de otro tipo de etapa, ajeno o fuera de servicio no se puede elegir (`sector_no_elegible`)."""
        otro_tipo = self.e.sectores["fructificacion"].pk
        self.assertEqual(self.rechazo(distribucion=((otro_tipo, 50),)).codigo, "sector_no_elegible")
        ajeno = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2")
        self.assertEqual(self.rechazo(distribucion=((ajeno.sectores["floracion"].pk, 50),)).codigo, "sector_no_elegible")
        self.assertEqual(self.rechazo(distribucion=((999999, 50),)).codigo, "sector_no_elegible")
        extra = self.otro_sector()
        SectorProduccion.objects.filter(pk=extra.pk).update(estado_sector="fuera_de_servicio")
        self.assertEqual(self.rechazo(distribucion=((extra.pk, 50),)).codigo, "sector_no_elegible")
        self.nada_creado()

    def test_regla_perfil_familiar_no_se_planifica_hacia_un_sector_con_plantas_de_otro_perfil(self):
        """«Compatibilidad por perfil familiar»: el sector elegido tiene un lote de otro perfil: `sector_no_elegible`."""
        extra = self.otro_sector()
        flor = variedad_con_semilla(nombre="Petunia", perfil="flores", etapas=CODIGOS_DE_ETAPA)
        lote_con_ciclo(self.e, cantidad=5, etapa="floracion", variedad=flor)
        self.assertEqual(self.rechazo().codigo, "sector_no_elegible")
        self.assertEqual(self.planificar(distribucion=((extra.pk, 50),)).estado_orden, "a_realizar")

    def test_regla_el_lote_va_entero_repartido_en_varios_sectores(self):
        """«Lote completo» y «Distribución»: la suma de lo planificado es la cantidad actual (30 + 20 de 50)."""
        extra = self.otro_sector()
        orden = self.planificar(distribucion=((self.e.sectores["floracion"].pk, 30), (extra.pk, 20)))
        self.assertEqual(sorted(o.cant_agujeros_planificados for o in orden.ocupaciones.all()), [20, 30])

    def test_regla_prioridad_y_descripcion_se_validan(self):
        """Paso 10 y MD-73: la prioridad es opcional (alta, media o baja) y la descripción, de hasta 500 caracteres."""
        self.assertEqual(self.rechazo(prioridad="urgente").codigo, "prioridad_invalida")
        self.assertEqual(self.rechazo(descripcion="x" * 501).codigo, "descripcion_larga")
        self.assertIsNone(self.planificar().prioridad_orden)

    # ---- Extensión 13: se repite todo bajo bloqueo ----

    def test_ext_13a_otra_transicion_a_realizar_apareció_entre_el_resumen_y_la_confirmacion(self):
        """Extensión 13a: el lote ya no puede trasladarse porque tiene otra transición «a realizar»: se rechaza sin crear nada."""
        transiciones.resumen_de_planificacion(self.e.agronomo, self.datos())
        orden_de_transicion(self.e, self.lote)
        self.assertEqual(self.rechazo().codigo, "lote_con_transicion")
        self.assertEqual(TransicionEtapa.objects.filter(estado_orden="a_realizar").count(), 1)

    def test_ext_13a_el_lote_cambio_de_etapa_o_dejo_de_estar_activo(self):
        """Extensión 13a: si la etapa actual ya no es la que la persona vio: `cambio_simultaneo` con la etapa actual; si el lote
        terminó, `lote_no_trasladable`."""
        lo_que_vio = self.datos()
        transiciones.resumen_de_planificacion(self.e.agronomo, lo_que_vio)
        etapa_nueva = orden_de_transicion(self.e, self.lote, estado="concretada")  # el lote pasó a Floración
        self.lote.refresh_from_db()
        error = rechazo(lambda: transiciones.planificar_transicion(self.e.agronomo, lo_que_vio))
        self.assertEqual(error.codigo, "cambio_simultaneo")
        self.assertIn("etapa_actual", error.datos)
        self.assertEqual(etapa_nueva.etapa_destino_id, self.lote.etapa_id)

    def test_ext_13b_cambio_la_cantidad_actual_del_lote(self):
        """Extensión 13b: una merma bajó la cantidad mientras tanto: `cambio_simultaneo` con la nueva cantidad actual; no registra nada."""
        transiciones.resumen_de_planificacion(self.e.agronomo, self.datos())
        Lote.objects.filter(pk=self.lote.pk).update(cantidad_actual=45)
        OcupacionSector.objects.filter(lote=self.lote, cant_agujeros_ocupados__gt=0).update(cant_agujeros_ocupados=45)
        error = self.rechazo()
        self.assertEqual((error.codigo, error.datos["cantidad_actual"]), ("cambio_simultaneo", 45))
        self.nada_creado()

    def test_ext_13c_el_espacio_o_la_compatibilidad_de_un_sector_destino_cambiaron(self):
        """Extensión 13c: se vuelve a verificar la capacidad libre y la compatibilidad de cada sector destino al registrar: sin lugar,
        `capacidad_insuficiente`; fuera de servicio, `sector_no_elegible`."""
        transiciones.resumen_de_planificacion(self.e.agronomo, self.datos())
        lote_con_ciclo(self.e, cantidad=60, etapa="floracion")
        self.assertEqual(self.rechazo().codigo, "capacidad_insuficiente")
        SectorProduccion.objects.filter(pk=self.e.sectores["floracion"].pk).update(estado_sector="fuera_de_servicio")
        self.assertEqual(self.rechazo().codigo, "sector_no_elegible")
        self.nada_creado()

    def test_ext_13d_el_capataz_dejo_de_estar_activo_al_registrar(self):
        """Extensión 13d: `sin_capataz_activo`, sin cambios."""
        transiciones.resumen_de_planificacion(self.e.agronomo, self.datos())
        Capataz.objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.assertEqual(self.rechazo().codigo, "sin_capataz_activo")
        self.nada_creado()

    # ---- Postcondiciones a, b, c, d, e, f y g ----

    def test_post_a_la_orden_nace_a_realizar_con_todos_sus_datos(self):
        """Postcondición a: orden de transición «a realizar» con fecha de creación (hoy), programada, descripción, prioridad, sin fecha de
        resolución ni cantidad transferida; asociada al lote, a la etapa destino, al Agrónomo, al Capataz y al invernadero del lote."""
        orden = TransicionEtapa.objects.get(pk=self.planificar(prioridad="alta", descripcion="Pasa a flor", fecha_programada=hoy() + timedelta(days=5)).pk)
        self.assertEqual(
            (orden.tipo_orden, orden.estado_orden, orden.fecha_creacion_orden, orden.fecha_programada_orden),
            ("transicion", "a_realizar", hoy(), hoy() + timedelta(days=5)),
        )
        self.assertEqual((orden.prioridad_orden, orden.descripcion_orden), ("alta", "Pasa a flor"))
        self.assertEqual(
            (orden.lote_id, orden.agronomo_id, orden.capataz_id, orden.invernadero_id),
            (self.lote.pk, self.e.agronomo.pk, self.e.capataz.pk, self.e.invernadero.pk),
        )
        self.assertEqual(orden.etapa_destino.tipo_etapa.codigo, "floracion")
        self.assertEqual((orden.fecha_resolucion_orden, orden.cant_transferido, orden.fecha_transicion), (None, None, None))
        self.assertIsNone(orden.bitacora_de_transicion)
        self.assertEqual(orden.codigo, f"OT-{orden.numero:04d}")

    def test_post_b_una_ocupacion_por_sector_destino_con_los_agujeros_planificados_y_ocupados_en_cero(self):
        """Postcondición b: una ocupación por sector destino con los planificados, ocupados en cero y sin lote; la suma es la cantidad
        actual del lote al planificar."""
        extra = self.otro_sector()
        orden = self.planificar(distribucion=((self.e.sectores["floracion"].pk, 30), (extra.pk, 20)))
        ocupaciones = list(orden.ocupaciones.order_by("pk"))
        self.assertEqual([(o.sector_id, o.cant_agujeros_planificados) for o in ocupaciones], [(self.e.sectores["floracion"].pk, 30), (extra.pk, 20)])
        self.assertEqual({(o.cant_agujeros_ocupados, o.lote_id) for o in ocupaciones}, {(0, None)})
        self.assertEqual(sum(o.cant_agujeros_planificados for o in ocupaciones), self.lote.cantidad_actual)

    def test_post_c_los_agujeros_comprometidos_del_sector_destino_aumentan_y_los_ocupados_no(self):
        """Postcondición c: los comprometidos de cada sector destino suben en lo planificado; los ocupados y el sector de origen no cambian."""
        destino, origen = self.e.sectores["floracion"], self.e.sectores["crecimiento"]
        antes = api_sectores.agujeros_de([destino, origen])
        self.planificar()
        despues = api_sectores.agujeros_de([destino, origen])
        self.assertEqual((despues[destino.pk].comprometidos - antes[destino.pk].comprometidos, despues[destino.pk].ocupados), (50, antes[destino.pk].ocupados))
        self.assertEqual(despues[origen.pk], antes[origen.pk])

    def test_post_d_se_notifica_al_capataz_con_el_codigo_de_la_orden(self):
        """Postcondición d: el Capataz recibe una notificación de la nueva orden (dentro de la transacción, D-42), con el lote, la etapa
        destino, la cantidad, la fecha y el invernadero; solo ella."""
        orden = self.planificar()
        notificacion = Notificacion.objects.get(destinatario=self.e.capataz)
        self.assertIn(orden.codigo, notificacion.titulo)
        for texto in (self.lote.codigo, "Floración", "50", self.e.invernadero.nombre_invernadero, f"{orden.fecha_programada_orden:%d/%m/%Y}"):
            self.assertIn(texto, notificacion.detalle)
        self.assertLessEqual(len(notificacion.detalle), 500)
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_post_e_f_g_un_solo_registro_de_auditoria_con_la_orden_las_ocupaciones_y_los_sectores(self):
        """Postcondiciones e, f y g (D-36, un registro por caso de uso): `planificacion_transicion` con la orden, cada ocupación y cada
        sector como afectados y el cambio de «agujeros comprometidos» de cada sector (antes → después, como texto)."""
        extra = self.otro_sector(nombre="Sector extra")
        orden = self.planificar(distribucion=((self.e.sectores["floracion"].pk, 30), (extra.pk, 20)))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="planificacion_transicion").count(), 1)
        registro = RegistroAuditoria.objects.get(accion="planificacion_transicion")
        self.assertEqual(registro.usuario_id, self.e.agronomo.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        esperados = {("produccion.transicionetapa", orden.pk)}
        esperados |= {("produccion.ocupacionsector", o.pk) for o in orden.ocupaciones.all()}
        esperados |= {("maestros.sectorproduccion", self.e.sectores["floracion"].pk), ("maestros.sectorproduccion", extra.pk)}
        self.assertLessEqual(esperados, afectados)
        cambio = registro.detalle["cambios"]["agujeros_comprometidos"]
        self.assertEqual(cambio["antes"], [f"{self.e.sectores['floracion'].nombre_sector}: 0", "Sector extra: 0"])
        self.assertEqual(cambio["despues"], [f"{self.e.sectores['floracion'].nombre_sector}: 30", "Sector extra: 20"])
        self.assertEqual(registro.detalle["datos"]["cantidad_actual"], "50")

    # ---- Garantías mínimas ----

    def test_garantia_la_transicion_no_reserva_insumos(self):
        """Garantía: «la transición no reserva insumos»."""
        self.planificar()
        self.assertEqual(ReservaInsumo.objects.count(), 0)

    def test_garantia_no_cambia_la_etapa_ni_la_cantidad_ni_las_ocupaciones_vigentes_ni_los_agujeros_disponibles(self):
        """Garantías mínimas: cualquiera sea el final, no se modifican la etapa, la cantidad actual ni las ocupaciones vigentes del lote,
        ni los agujeros ocupados de los sectores (los de origen se liberan recién al concretar)."""
        antes = (Lote.objects.values_list("etapa_id", "cantidad_actual", "costo_acumulado").get(pk=self.lote.pk),
                 list(OcupacionSector.objects.filter(lote=self.lote).order_by("pk").values_list("pk", "cant_agujeros_ocupados")))
        sectores = list(SectorProduccion.objects.filter(invernadero=self.e.invernadero))
        ocupados = {k: v.ocupados for k, v in api_sectores.agujeros_de(sectores).items()}
        self.rechazo(distribucion=())
        self.planificar()
        despues = (Lote.objects.values_list("etapa_id", "cantidad_actual", "costo_acumulado").get(pk=self.lote.pk),
                   list(OcupacionSector.objects.filter(lote=self.lote).order_by("pk").values_list("pk", "cant_agujeros_ocupados")))
        self.assertEqual(antes, despues)
        self.assertEqual(ocupados, {k: v.ocupados for k, v in api_sectores.agujeros_de(sectores).items()})

    def test_garantia_un_error_en_el_medio_no_deja_nada_creado(self):
        """Garantías mínimas y D-22: si algo falla después de escribir (acá, el aviso al Capataz), no queda ninguna orden, ocupación,
        notificación ni registro de auditoría."""
        with mock.patch("core.notificaciones.notificar", side_effect=RuntimeError("falla del aviso")):
            with self.assertRaises(RuntimeError):
                self.planificar()
        self.nada_creado()
        self.assertEqual(OrdenTrabajo.objects.filter(tipo_orden="transicion", estado_orden="a_realizar").count(), 0)


class ResumenDePlanificacionTests(Base):
    """Paso 11: el resumen valida igual que la planificación y no escribe nada."""

    def test_paso_11_el_resumen_trae_el_lote_las_etapas_el_origen_la_distribucion_la_fecha_y_el_capataz(self):
        """Paso 11: invernadero, lote, variedad, etapa actual y destino, cantidad, sectores de origen con sus agujeros, distribución,
        fecha programada, prioridad y Capataz."""
        extra = self.otro_sector()
        resumen = transiciones.resumen_de_planificacion(
            self.e.agronomo,
            self.datos(distribucion=((self.e.sectores["floracion"].pk, 30), (extra.pk, 20)), prioridad="media", descripcion="Ojo"),
        )
        self.assertEqual((resumen.invernadero, resumen.lote.pk, resumen.variedad), (self.e.invernadero, self.lote.pk, self.e.variedad))
        self.assertEqual((resumen.etapa_origen.codigo, resumen.etapa_destino.codigo), ("crecimiento", "floracion"))
        self.assertEqual(resumen.cantidad, 50)
        self.assertEqual([(s.nombre_sector, n) for s, n in resumen.sectores_de_origen], [(self.e.sectores["crecimiento"].nombre_sector, 50)])
        self.assertEqual([(s.pk, n) for s, n in resumen.distribucion], [(self.e.sectores["floracion"].pk, 30), (extra.pk, 20)])
        self.assertEqual((resumen.fecha_programada, resumen.prioridad, resumen.descripcion), (hoy() + timedelta(days=10), "media", "Ojo"))
        self.assertEqual(resumen.capataz, self.e.capataz)

    def test_paso_11_el_resumen_no_escribe_nada(self):
        """El resumen no crea órdenes, ocupaciones, notificaciones ni auditoría, ni numera la orden."""
        antes = (TransicionEtapa.objects.count(), OcupacionSector.objects.count())
        transiciones.resumen_de_planificacion(self.e.agronomo, self.datos())
        self.assertEqual((TransicionEtapa.objects.count(), OcupacionSector.objects.count()), antes)
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="planificacion_transicion").count(), 0)

    def test_paso_11_el_resumen_rechaza_lo_mismo_que_la_planificacion(self):
        """Mismo rechazo en el resumen y al confirmar: fecha pasada, distribución incompleta, lote con otra transición."""
        for cambios, codigo in (
            ({"fecha_programada": hoy() - timedelta(days=1)}, "fecha_invalida"),
            ({"distribucion": ((self.e.sectores["floracion"].pk, 10),)}, "distribucion_incompleta"),
        ):
            with self.subTest(codigo=codigo):
                self.assertEqual(rechazo(lambda: transiciones.resumen_de_planificacion(self.e.agronomo, self.datos(**cambios))).codigo, codigo)
        orden_de_transicion(self.e, self.lote)
        self.assertEqual(rechazo(lambda: transiciones.resumen_de_planificacion(self.e.agronomo, self.datos())).codigo, "lote_con_transicion")
