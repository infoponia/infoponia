# Pruebas de PROD-REG-LTE · Registrar Lote Existente (PRD-05, paso 3; docs/casos_de_uso/produccion/lote_existente.md y su «Cómo se aplica»; D-92 punto 12).
#
# Servicio que se prueba (produccion/servicios/lotes_existentes.py), tomado del módulo dentro de cada prueba (`perezoso`):
# - invernaderos_disponibles(actor): los invernaderos activos a cargo del Agrónomo sin una siembra normal concretada (precondición c, paso 2).
# - datos_de_registro(actor, invernadero_id, variedad_id=None, etapa_id=None): lo que presentan los pasos 2, 4 y 6. No escribe.
# - resumen_de_registro(actor, datos): valida todo y devuelve el resumen del paso 8, con el asiento previsto. No escribe ni bloquea.
# - registrar_lote_existente(actor, datos) -> Lote: lo mismo bajo bloqueo (extensión 10a) y escribe todo o nada (D-22).
# - DatosDeLoteExistente(invernadero_id, variedad_id, etapa_id, fecha_siembra, fecha_ingreso_etapa, cantidad, costo_estimado, distribucion):
#   `etapa_id` es el id de la `EtapaProductiva` del ciclo; `distribucion` es `{sector_id: plantas}` o `((sector_id, plantas), ...)`.
#
# Códigos y campos: sin_permiso; invernadero_inactivo; invernadero_con_siembras (2a y 10a); variedad_inactiva (variedad); etapa_invalida (etapa);
# fecha_invalida (fecha_siembra o fecha_ingreso_etapa; 5a); cantidad_invalida (cantidad o distribucion; 5b); costo_invalido (costo_estimado; 5c);
# sin_sectores (etapa; 7d); sector_no_elegible (distribucion); supera_agujeros (distribucion; 7a); distribucion_incompleta (distribucion; 7b).
#
# Una prueba por postcondición y por extensión. Las que crean un asiento terminan con `verificar_invariantes_contables()`.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from contabilidad import cuentas
from contabilidad.models import AsientoContable, MovimientoContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin, verificar_invariantes_contables
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.models import MovimientoInsumo
from inventario.tests.fabricas import ConDatosDeInventario, perezoso, variedad_con_semilla
from maestros.models import EtapaProductiva, SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import crear_agronomo, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, Consumo, Lote, OcupacionSector, OrdenTrabajo, ReservaInsumo, Siembra
from produccion.servicios import ordenes
from produccion.tests.fabricas import (
    invernadero_con_produccion,
    lote_activo,
    lote_de_carga_inicial,
    orden_de_siembra,
)

registros = perezoso("produccion.servicios.lotes_existentes")
D = Decimal


def hoy():
    return timezone.localdate()


def etapa_de(variedad, codigo):
    """El id de la `EtapaProductiva` de `codigo` en el ciclo de la variedad."""
    return EtapaProductiva.objects.get(ciclo__variedad=variedad, tipo_etapa__codigo=codigo).pk


def datos(e, **cambios):
    """`DatosDeLoteExistente` válidos: 180 plantas en Maduración repartidas en dos sectores (100 y 80), con costo $12.000, sembradas
    hace 40 días y en la etapa desde hace 10."""
    segundo = cambios.pop("segundo_sector", None)
    base = dict(
        invernadero_id=e.invernadero.pk,
        variedad_id=e.variedad.pk,
        etapa_id=etapa_de(e.variedad, "maduracion"),
        fecha_siembra=hoy() - timedelta(days=40),
        fecha_ingreso_etapa=hoy() - timedelta(days=10),
        cantidad=180,
        costo_estimado=D("12000.00"),
        distribucion={e.sectores["maduracion"].pk: 100, (segundo or e.sectores["maduracion_2"]).pk: 80},
    )
    base.update(cambios)
    return registros.DatosDeLoteExistente(**base)


class ProdRegLteBase(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """Un invernadero sin siembras con dos sectores de Maduración de 100 agujeros (`maduracion` y `maduracion_2`)."""

    def setUp(self):
        self.e = invernadero_con_produccion()
        self.e.sectores["maduracion_2"] = crear_sector(self.e.invernadero, nombre="Sector maduracion 2", tipo="maduracion", agujeros=100)

    def rechazo(self, actor, d, codigo, campo=None):
        """Verifica que `registrar_lote_existente` rechace con `codigo` (y `campo`) y que no quede nada escrito. Devuelve el error."""
        antes = (Siembra.objects.count(), Lote.objects.count(), OcupacionSector.objects.count(), AsientoContable.objects.count())
        with self.assertRaises(ErrorDeProduccion) as contexto:
            registros.registrar_lote_existente(actor, d)
        self.assertEqual(contexto.exception.codigo, codigo)
        if campo is not None:
            self.assertEqual(contexto.exception.campo, campo)
        self.assertEqual(
            (Siembra.objects.count(), Lote.objects.count(), OcupacionSector.objects.count(), AsientoContable.objects.count()), antes
        )
        return contexto.exception


class ProdRegLteServicioTests(ProdRegLteBase):
    # ---- Flujo principal y postcondiciones ----

    def test_flujo_principal_registra_un_lote_en_maduracion_en_dos_sectores(self):
        """Hecho cuando de PRD-05: lote en Maduración en dos sectores con costo $12.000: lote activo, agujeros que bajan, bitácora y asiento."""
        lote = registros.registrar_lote_existente(self.e.agronomo, datos(self.e))
        lote = Lote.objects.get(pk=lote.pk)
        self.assertEqual((lote.estado_lote, lote.cantidad_inicial, lote.cantidad_actual), ("activo", 180, 180))
        self.assertEqual(lote.etapa.tipo_etapa.codigo, "maduracion")
        self.assertEqual(lote.costo_acumulado, D("12000.00"))
        agujeros = api_sectores.agujeros_de(list(SectorProduccion.objects.filter(invernadero=self.e.invernadero, tipo_etapa__codigo="maduracion")))
        self.assertEqual(sorted(a.libres for a in agujeros.values()), [0, 20])
        self.assertEqual(Bitacora.objects.filter(lote=lote, tipo_evento="carga_inicial").count(), 1)
        self.assertEqual(AsientoContable.objects.count(), 1)
        verificar_invariantes_contables()

    def test_post_a_siembra_concretada_de_carga_inicial_sin_capataz_reservas_ni_consumos(self):
        """Postcondición a y reglas «Siembra de carga inicial» y «Garantías»: siembra concretada, `carga_inicial`, con la fecha de siembra
        indicada y la cantidad, de la variedad y el invernadero; sin Capataz, reservas, consumos, otras órdenes ni movimientos de insumo."""
        d = datos(self.e)
        lote = registros.registrar_lote_existente(self.e.agronomo, d)
        siembra = Siembra.objects.get(pk=lote.siembra_id)
        self.assertEqual((siembra.tipo_orden, siembra.estado_orden, siembra.tipo_siembra), ("siembra", "concretada", "carga_inicial"))
        self.assertIsNone(siembra.capataz_id)
        self.assertEqual(siembra.fecha_siembra, d.fecha_siembra)
        self.assertEqual((siembra.cant_plantines_siembra, siembra.variedad_id, siembra.invernadero_id), (180, self.e.variedad.pk, self.e.invernadero.pk))
        self.assertEqual(siembra.agronomo_id, self.e.agronomo.pk)
        self.assertEqual(ReservaInsumo.objects.count(), 0)
        self.assertEqual(Consumo.objects.count(), 0)
        self.assertEqual(MovimientoInsumo.objects.filter(tipo_movimiento__startswith="salida").count(), 0)
        self.assertEqual(OrdenTrabajo.objects.count(), 1)  # ninguna orden para el Capataz
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_regla_fechas_de_la_orden_son_hoy_y_la_fecha_de_siembra_es_la_indicada(self):
        """Decisión del estudiante (25/11/2026, difiere de D-92 punto 12): `fecha_creacion_orden = fecha_programada_orden =
        fecha_resolucion_orden = hoy` (cumple `orden_trabajo_programada_desde_creacion`) y `fecha_siembra` es la pasada indicada."""
        d = datos(self.e)
        siembra = Siembra.objects.get(pk=registros.registrar_lote_existente(self.e.agronomo, d).siembra_id)
        self.assertEqual((siembra.fecha_creacion_orden, siembra.fecha_programada_orden, siembra.fecha_resolucion_orden), (hoy(), hoy(), hoy()))
        self.assertEqual(siembra.fecha_siembra, hoy() - timedelta(days=40))
        self.assertNotEqual(siembra.fecha_siembra, siembra.fecha_programada_orden)

    def test_regla_numero_de_la_orden_sale_de_la_secuencia(self):
        """D-92 punto 12: el número de la orden es el de la secuencia de siempre (`ordenes.siguiente_numero`)."""
        previo = ordenes.siguiente_numero()
        siembra = Siembra.objects.get(pk=registros.registrar_lote_existente(self.e.agronomo, datos(self.e)).siembra_id)
        self.assertGreater(siembra.numero, previo)

    def test_post_b_lote_con_la_cantidad_la_etapa_y_el_costo_indicados(self):
        """Postcondición b: lote «activo» de la siembra y del invernadero, `cantidad_inicial = cantidad_actual`, en la etapa indicada, con el
        costo estimado como costo acumulado (D-92 punto 12: crearlo no pasa por `costos.py`)."""
        lote = registros.registrar_lote_existente(self.e.agronomo, datos(self.e, costo_estimado=D("1234.56")))
        lote = Lote.objects.get(pk=lote.pk)
        self.assertEqual((lote.invernadero_id, lote.cantidad_inicial, lote.cantidad_actual), (self.e.invernadero.pk, 180, 180))
        self.assertEqual(lote.etapa_id, etapa_de(self.e.variedad, "maduracion"))
        self.assertEqual(lote.costo_acumulado, D("1234.56"))

    def test_post_b_entrada_de_bitacora_carga_inicial_con_etapa_y_fecha_de_ingreso(self):
        """Postcondición b y D-92 punto 12: una `Bitacora` `carga_inicial` con el lote, la etapa actual, `fecha_bitacora` = ingreso a la etapa,
        el actor como responsable, los sectores y una descripción legible (D-51 punto 8)."""
        d = datos(self.e)
        lote = registros.registrar_lote_existente(self.e.agronomo, d)
        registro = Bitacora.objects.get(lote=lote, tipo_evento="carga_inicial")
        self.assertEqual(registro.etapa_id, lote.etapa_id)
        self.assertEqual(registro.fecha_bitacora, d.fecha_ingreso_etapa)
        self.assertEqual(registro.responsable_id, self.e.agronomo.pk)
        self.assertEqual(registro.invernadero_id, self.e.invernadero.pk)
        self.assertEqual({s.pk for s in registro.sectores.all()}, set(d.distribucion))
        self.assertIn(lote.codigo, registro.descripcion_evento)
        self.assertLessEqual(len(registro.descripcion_evento), 500)

    def test_post_c_una_ocupacion_por_sector_y_los_agujeros_libres_bajan(self):
        """Postcondición c y regla «Sectores»: una ocupación por sector con planificados = ocupados, de la siembra y del lote; los libres
        bajan en esa cantidad."""
        d = datos(self.e)
        sectores = list(SectorProduccion.objects.filter(pk__in=d.distribucion))
        antes = api_sectores.agujeros_de(sectores)
        lote = registros.registrar_lote_existente(self.e.agronomo, d)
        ocupaciones = OcupacionSector.objects.filter(orden_id=lote.siembra_id)
        self.assertEqual({(o.sector_id, o.cant_agujeros_planificados, o.cant_agujeros_ocupados, o.lote_id) for o in ocupaciones},
                         {(self.e.sectores["maduracion"].pk, 100, 100, lote.pk), (self.e.sectores["maduracion_2"].pk, 80, 80, lote.pk)})
        despues = api_sectores.agujeros_de(sectores)
        for sector in sectores:
            self.assertEqual(despues[sector.pk].libres, antes[sector.pk].libres - d.distribucion[sector.pk])
            self.assertEqual(despues[sector.pk].comprometidos, 0)

    def test_post_d_asiento_productos_en_proceso_contra_capital_inicial_con_la_fecha_actual(self):
        """Postcondición d y D-92 puntos 4 y 12: asiento originado en la siembra, Debe Productos en Proceso / Haber Capital Inicial por el
        costo estimado, con la fecha ACTUAL (no la de la siembra) y sin aclaración de fecha anterior (CON-02)."""
        d = datos(self.e)
        lote = registros.registrar_lote_existente(self.e.agronomo, d)
        asiento = AsientoContable.objects.get(origen_id=lote.siembra_id)
        self.assertEqual(asiento.fecha_asiento, hoy())
        self.assertNotIn("Fecha del hecho", asiento.descripcion_asiento)
        lineas = sorted(
            (m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in MovimientoContable.objects.filter(asiento=asiento)
        )
        self.assertEqual(
            lineas, sorted([(cuentas.PRODUCTOS_EN_PROCESO, "D", D("12000.00")), (cuentas.CAPITAL_INICIAL, "H", D("12000.00"))])
        )
        verificar_invariantes_contables()

    def test_post_d_con_costo_cero_no_hay_asiento_y_no_falla(self):
        """Postcondición d y H11: con costo estimado $0 se registra todo y no hay asiento."""
        lote = registros.registrar_lote_existente(self.e.agronomo, datos(self.e, costo_estimado=D("0")))
        self.assertEqual(Lote.objects.get(pk=lote.pk).costo_acumulado, D("0.00"))
        self.assertEqual(AsientoContable.objects.count(), 0)
        self.assertEqual(Siembra.objects.filter(tipo_siembra="carga_inicial").count(), 1)
        verificar_invariantes_contables()

    def test_post_d_la_fecha_de_siembra_pasada_no_cae_en_el_caso_fecha_anterior_de_con_02(self):
        """D-92 punto 4: aunque la siembra sea de hace un año, el asiento lleva la fecha de hoy y su descripción no aclara ninguna fecha anterior."""
        d = datos(self.e, fecha_siembra=hoy() - timedelta(days=400), fecha_ingreso_etapa=hoy() - timedelta(days=5))
        lote = registros.registrar_lote_existente(self.e.agronomo, d)
        asiento = AsientoContable.objects.get(origen_id=lote.siembra_id)
        self.assertEqual(asiento.fecha_asiento, hoy())
        self.assertNotIn("Fecha del hecho", asiento.descripcion_asiento)
        verificar_invariantes_contables()

    def test_post_e_un_registro_de_auditoria_con_todo_lo_creado_entre_los_afectados(self):
        """Postcondición e y D-36: un único registro `registro_lote_existente` con la siembra, el lote, las ocupaciones, los sectores, la
        bitácora y el asiento entre los afectados."""
        lote = registros.registrar_lote_existente(self.e.agronomo, datos(self.e))
        registro = RegistroAuditoria.objects.get(accion="registro_lote_existente")
        self.assertEqual(registro.usuario_id, self.e.agronomo.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        asiento = AsientoContable.objects.get(origen_id=lote.siembra_id)
        bitacora = Bitacora.objects.get(lote=lote, tipo_evento="carga_inicial")
        modelos = {modelo.lower() for modelo, _ in afectados}
        for parte in ("siembra", "lote", "ocupacionsector", "sectorproduccion", "bitacora", "asientocontable"):
            self.assertTrue(any(parte in modelo for modelo in modelos), f"Falta {parte} entre los afectados: {modelos}")
        ids = {id_ for _, id_ in afectados}
        self.assertTrue({lote.pk, lote.siembra_id, asiento.pk, bitacora.pk} <= ids)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_lote_existente").count(), 1)

    def test_post_e_sin_asiento_el_registro_de_auditoria_no_lo_nombra(self):
        """Con costo $0 no hay asiento: el registro de auditoría existe y no lo incluye."""
        registros.registrar_lote_existente(self.e.agronomo, datos(self.e, costo_estimado=D("0")))
        registro = RegistroAuditoria.objects.get(accion="registro_lote_existente")
        self.assertFalse(any("asiento" in a["modelo"].lower() for a in registro.afectados))

    def test_d36_el_detalle_de_la_auditoria_usa_solo_valores_permitidos_y_claves_con_etiqueta(self):
        """D-36: el detalle no lleva `Decimal` ni fechas crudas (ya lo valida `registrar`) y toda clave de «cambios» y «datos» tiene nombre visible."""
        registros.registrar_lote_existente(self.e.agronomo, datos(self.e))
        detalle = RegistroAuditoria.objects.get(accion="registro_lote_existente").detalle
        for clave in [*detalle.get("cambios", {}), *detalle.get("datos", {})]:
            self.assertIn(clave, RegistroAuditoria.ETIQUETAS, clave)
        self.assertEqual(detalle["datos"]["tipo_siembra"], "carga_inicial")

    def test_regla_un_lote_en_otra_etapa_ocupa_sectores_de_ese_tipo(self):
        """Regla «Etapa actual»: cualquier etapa del ciclo, no solo Germinación; los sectores son los del tipo de esa etapa."""
        d = datos(self.e, etapa_id=etapa_de(self.e.variedad, "crecimiento"), cantidad=40, distribucion={self.e.sectores["crecimiento"].pk: 40})
        lote = registros.registrar_lote_existente(self.e.agronomo, d)
        self.assertEqual(Lote.objects.get(pk=lote.pk).etapa.tipo_etapa.codigo, "crecimiento")
        self.rechazo(self.e.agronomo, datos(self.e, etapa_id=etapa_de(self.e.variedad, "floracion"), cantidad=10,
                                            distribucion={self.e.sectores["crecimiento"].pk: 10}), "sector_no_elegible", "distribucion")

    def test_regla_dos_cargas_en_el_mismo_invernadero_son_validas(self):
        """Regla «Cuándo»: solo la siembra NORMAL concretada impide cargar; una carga inicial previa no (se cargan varios lotes)."""
        registros.registrar_lote_existente(self.e.agronomo, datos(self.e, cantidad=60, distribucion={self.e.sectores["maduracion"].pk: 60}))
        registros.registrar_lote_existente(self.e.agronomo, datos(self.e, cantidad=40, distribucion={self.e.sectores["maduracion"].pk: 40}))
        self.assertEqual(Lote.objects.count(), 2)
        verificar_invariantes_contables()

    def test_regla_el_perfil_familiar_del_sector_se_aplica_como_en_el_resto_del_sistema(self):
        """«Sobre el perfil familiar» de «Cómo se aplica»: un sector con plantas de otro perfil no es elegible (`sector_no_elegible`)."""
        otra = variedad_con_semilla(nombre="Tomate", perfil="frutos_grandes", etapas=("germinacion", "maduracion"))
        lote_de_carga_inicial(self.e, cantidad=10, etapa="maduracion", sector=self.e.sectores["maduracion"], variedad=otra)
        self.rechazo(self.e.agronomo, datos(self.e, cantidad=10, distribucion={self.e.sectores["maduracion"].pk: 10}), "sector_no_elegible", "distribucion")

    # ---- Precondiciones ----

    def test_regla_rol_solo_el_agronomo_a_cargo_registra(self):
        """Regla «Quién registra» y precondición a: el Capataz, el Gerente y un Agrónomo ajeno son `sin_permiso`; un Agrónomo inactivo, también."""
        d = datos(self.e)
        for actor in (self.e.capataz, crear_gerente(), crear_agronomo(email="ajeno@infoponia.com")):
            self.rechazo(actor, d, "sin_permiso")
        self.e.agronomo.is_active = False
        self.e.agronomo.save(update_fields=["is_active"])
        self.rechazo(self.e.agronomo, d, "sin_permiso")

    def test_regla_invernadero_inactivo_no_admite_la_carga(self):
        """Precondición b: el invernadero tiene que estar activo."""
        d = datos(self.e)
        self.e.invernadero.estado_invernadero = "inactivo"
        self.e.invernadero.save(update_fields=["estado_invernadero"])
        self.rechazo(self.e.agronomo, d, "invernadero_inactivo")

    def test_regla_invernadero_inexistente_es_404(self):
        """Un invernadero que no existe es `Http404`."""
        with self.assertRaises(Http404):
            registros.registrar_lote_existente(self.e.agronomo, datos(self.e, invernadero_id=999999))

    def test_regla_variedad_inactiva_se_rechaza(self):
        """Paso 4: la variedad tiene que estar activa (`variedad_inactiva`, campo variedad)."""
        d = datos(self.e)
        self.e.variedad.estado_variedad = "inactivo"
        self.e.variedad.save(update_fields=["estado_variedad"])
        self.rechazo(self.e.agronomo, d, "variedad_inactiva", "variedad")

    def test_regla_la_etapa_tiene_que_ser_del_ciclo_de_la_variedad(self):
        """Paso 4: una etapa de otro ciclo es `etapa_invalida` (campo etapa)."""
        otra = variedad_con_semilla(nombre="Otra", etapas=("germinacion", "maduracion"))
        self.rechazo(self.e.agronomo, datos(self.e, etapa_id=etapa_de(otra, "maduracion")), "etapa_invalida", "etapa")

    # ---- Extensión 2a / precondición c ----

    def test_ext_2a_con_una_siembra_normal_concretada_no_se_puede_cargar(self):
        """Extensión 2a y precondición c: el invernadero ya tiene una siembra normal concretada: `invernadero_con_siembras`."""
        d = datos(self.e)
        lote_activo(self.e, cantidad=10)
        self.rechazo(self.e.agronomo, d, "invernadero_con_siembras")

    def test_ext_2a_una_siembra_normal_a_realizar_o_cancelada_no_impide_cargar(self):
        """Regla «Cuándo»: solo cuentan las siembras NORMALES CONCRETADAS; una «a realizar» o «cancelada» no."""
        orden_de_siembra(self.e, plantines=10, sector="germinacion", estado="a_realizar")
        orden_de_siembra(self.e, plantines=10, sector="germinacion", estado="cancelada", agujeros=10)
        registros.registrar_lote_existente(self.e.agronomo, datos(self.e))
        self.assertEqual(Lote.objects.count(), 1)

    # ---- Extensiones 5a, 5b, 5c ----

    def test_ext_5a_fecha_de_siembra_futura_se_rechaza(self):
        """Extensión 5a: la fecha de siembra no puede ser posterior a hoy."""
        d = datos(self.e, fecha_siembra=hoy() + timedelta(days=1), fecha_ingreso_etapa=hoy())
        self.rechazo(self.e.agronomo, d, "fecha_invalida", "fecha_siembra")

    def test_ext_5a_ingreso_anterior_a_la_siembra_o_posterior_a_hoy_se_rechaza(self):
        """Extensión 5a: el ingreso a la etapa no puede ser anterior a la siembra ni posterior a hoy."""
        self.rechazo(self.e.agronomo, datos(self.e, fecha_siembra=hoy() - timedelta(days=5), fecha_ingreso_etapa=hoy() - timedelta(days=6)),
                     "fecha_invalida", "fecha_ingreso_etapa")
        self.rechazo(self.e.agronomo, datos(self.e, fecha_ingreso_etapa=hoy() + timedelta(days=1)), "fecha_invalida", "fecha_ingreso_etapa")

    def test_ext_5a_fechas_faltantes_se_rechazan(self):
        """Extensión 5a: sin fecha de siembra o sin ingreso, `fecha_invalida`."""
        self.rechazo(self.e.agronomo, datos(self.e, fecha_siembra=None), "fecha_invalida", "fecha_siembra")
        self.rechazo(self.e.agronomo, datos(self.e, fecha_ingreso_etapa=None), "fecha_invalida", "fecha_ingreso_etapa")

    def test_ext_5a_las_tres_fechas_en_hoy_son_validas(self):
        """Los límites de 5a son inclusivos: siembra = ingreso = hoy."""
        registros.registrar_lote_existente(self.e.agronomo, datos(self.e, fecha_siembra=hoy(), fecha_ingreso_etapa=hoy()))
        self.assertEqual(Lote.objects.count(), 1)

    def test_ext_5b_cantidad_cero_negativa_o_no_entera_se_rechaza(self):
        """Extensión 5b: la cantidad de plantas es un entero mayor que cero."""
        for malo in (0, -5, 2.5, "10", None, True):
            self.rechazo(self.e.agronomo, datos(self.e, cantidad=malo), "cantidad_invalida", "cantidad")

    def test_ext_5c_costo_negativo_con_tres_decimales_o_no_decimal_se_rechaza(self):
        """Extensión 5c: el costo estimado es un `Decimal` ≥ 0 con dos decimales como mucho (un `float` no vale)."""
        for malo in (D("-1"), D("10.001"), 10.5, "10", None):
            self.rechazo(self.e.agronomo, datos(self.e, costo_estimado=malo), "costo_invalido", "costo_estimado")

    def test_ext_5c_costo_mayor_que_lo_que_entra_en_el_campo_se_rechaza(self):
        """El costo del lote es `DecimalField(14, 2)`: más de 12 enteros es `costo_invalido` y no un error de base."""
        self.rechazo(self.e.agronomo, datos(self.e, costo_estimado=D("1000000000000.00")), "costo_invalido", "costo_estimado")

    def test_ext_5c_costo_con_dos_decimales_o_con_ceros_de_mas_es_valido(self):
        """`Decimal('10.50')` y `Decimal('10.5000')` valen (son 10,50); tres decimales significativos no."""
        lote = registros.registrar_lote_existente(self.e.agronomo, datos(self.e, costo_estimado=D("10.5000")))
        self.assertEqual(Lote.objects.get(pk=lote.pk).costo_acumulado, D("10.50"))

    # ---- Extensiones 7a, 7b, 7c, 7d ----

    def test_ext_7a_cantidad_en_un_sector_mayor_que_sus_agujeros_libres_informa_los_libres(self):
        """Extensión 7a: la cantidad en un sector supera sus agujeros libres: `supera_agujeros`, y el rechazo trae los libres de ese sector."""
        d = datos(self.e, cantidad=120, distribucion={self.e.sectores["maduracion"].pk: 120})
        error = self.rechazo(self.e.agronomo, d, "supera_agujeros", "distribucion")
        self.assertEqual(error.datos.get("libres"), {self.e.sectores["maduracion"].pk: 100})

    def test_ext_7a_los_agujeros_ocupados_por_otro_lote_no_estan_libres(self):
        """Extensión 7a: lo que ya ocupa otro lote cargado antes se descuenta."""
        registros.registrar_lote_existente(self.e.agronomo, datos(self.e, cantidad=90, distribucion={self.e.sectores["maduracion"].pk: 90}))
        d = datos(self.e, cantidad=20, distribucion={self.e.sectores["maduracion"].pk: 20})
        error = self.rechazo(self.e.agronomo, d, "supera_agujeros", "distribucion")
        self.assertEqual(error.datos.get("libres"), {self.e.sectores["maduracion"].pk: 10})

    def test_ext_7b_la_suma_de_la_distribucion_distinta_de_la_cantidad_senala_la_diferencia(self):
        """Extensión 7b: la suma no es igual a la cantidad: `distribucion_incompleta` (y el mensaje dice cuánto falta o sobra)."""
        falta = self.rechazo(self.e.agronomo, datos(self.e, cantidad=180, distribucion={self.e.sectores["maduracion"].pk: 100}),
                             "distribucion_incompleta", "distribucion")
        self.assertIn("80", falta.mensaje)
        sobra = self.rechazo(self.e.agronomo, datos(self.e, cantidad=50, distribucion={self.e.sectores["maduracion"].pk: 60}),
                             "distribucion_incompleta", "distribucion")
        self.assertIn("10", sobra.mensaje)

    def test_ext_7c_repartir_en_mas_de_un_sector_se_repite_por_cada_uno(self):
        """Extensión 7c: tres sectores, cada uno con su cantidad."""
        tercero = crear_sector(self.e.invernadero, nombre="Sector maduracion 3", tipo="maduracion", agujeros=50)
        d = datos(self.e, cantidad=200, distribucion={self.e.sectores["maduracion"].pk: 100, self.e.sectores["maduracion_2"].pk: 60, tercero.pk: 40})
        lote = registros.registrar_lote_existente(self.e.agronomo, d)
        self.assertEqual(OcupacionSector.objects.filter(lote=lote).count(), 3)

    def test_ext_7d_sin_sectores_compatibles_con_la_etapa_informa_que_no_hay_donde_ubicar_el_lote(self):
        """Extensión 7d: no hay sectores activos del tipo de la etapa: `sin_sectores` (campo etapa)."""
        SectorProduccion.objects.filter(invernadero=self.e.invernadero, tipo_etapa__codigo="maduracion").update(estado_sector="fuera_de_servicio")
        self.rechazo(self.e.agronomo, datos(self.e), "sin_sectores", "etapa")

    def test_ext_7d_sectores_llenos_tampoco_son_donde_ubicar_el_lote(self):
        """Extensión 7d: con todos los sectores del tipo llenos, tampoco hay dónde ubicar el lote."""
        registros.registrar_lote_existente(
            self.e.agronomo, datos(self.e, cantidad=200, distribucion={self.e.sectores["maduracion"].pk: 100, self.e.sectores["maduracion_2"].pk: 100})
        )
        self.rechazo(self.e.agronomo, datos(self.e, cantidad=5, distribucion={self.e.sectores["maduracion"].pk: 5}), "sin_sectores", "etapa")

    def test_regla_un_sector_que_no_se_ofrece_es_sector_no_elegible(self):
        """Paso 6: un sector de otro tipo, de otro invernadero, fuera de servicio o inactivo no se puede elegir (`sector_no_elegible`)."""
        otro = invernadero_con_produccion(nombre="Otro", sufijo="2", geografia_propia=False)
        fuera = crear_sector(self.e.invernadero, nombre="Fuera", tipo="maduracion", agujeros=50, estado="fuera_de_servicio")
        baja = crear_sector(self.e.invernadero, nombre="Baja", tipo="maduracion", agujeros=50, estado="inactivo")
        for sector in (self.e.sectores["germinacion"], otro.sectores["maduracion"], fuera, baja):
            self.rechazo(self.e.agronomo, datos(self.e, cantidad=10, distribucion={sector.pk: 10}), "sector_no_elegible", "distribucion")

    def test_regla_un_sector_repetido_o_con_cantidad_cero_se_rechaza(self):
        """Paso 7: cada sector se usa una vez y con una cantidad entera mayor que cero (`cantidad_invalida`, campo distribucion)."""
        sector = self.e.sectores["maduracion"].pk
        self.rechazo(self.e.agronomo, datos(self.e, cantidad=10, distribucion=((sector, 5), (sector, 5))), "cantidad_invalida", "distribucion")
        self.rechazo(self.e.agronomo, datos(self.e, cantidad=10, distribucion={sector: 10, self.e.sectores["maduracion_2"].pk: 0}),
                     "cantidad_invalida", "distribucion")

    def test_regla_distribucion_vacia_se_rechaza(self):
        """Paso 7: sin distribución, `distribucion_incompleta`."""
        self.rechazo(self.e.agronomo, datos(self.e, distribucion={}), "distribucion_incompleta", "distribucion")

    # ---- Extensión 10a y garantías ----

    def test_ext_10a_si_se_concreta_una_siembra_normal_mientras_se_bloquea_no_se_registra_nada(self):
        """Extensión 10a: después de bloquear, el invernadero ya tiene una siembra normal concretada: `invernadero_con_siembras` y nada
        queda escrito (se vuelve a verificar bajo bloqueo)."""
        real = registros.bloquear_invernadero_activo

        def bloquear_y_que_aparezca_una_siembra_normal(*argumentos):
            resultado = real(*argumentos)
            lote_activo(self.e, cantidad=10)  # otra transacción la concretó antes de que esta releyera
            return resultado

        with mock.patch("produccion.servicios.lotes_existentes.bloquear_invernadero_activo", side_effect=bloquear_y_que_aparezca_una_siembra_normal):
            antes = Siembra.objects.filter(tipo_siembra="carga_inicial").count()
            with self.assertRaises(ErrorDeProduccion) as contexto:
                registros.registrar_lote_existente(self.e.agronomo, datos(self.e))
        self.assertEqual(contexto.exception.codigo, "invernadero_con_siembras")
        self.assertEqual(Siembra.objects.filter(tipo_siembra="carga_inicial").count(), antes)
        self.assertEqual(AsientoContable.objects.count(), 0)

    def test_ext_10a_si_los_agujeros_libres_cambiaron_mientras_se_bloquea_no_se_registra_nada(self):
        """Extensión 10a: después de bloquear, otro lote ocupó los agujeros: `supera_agujeros` y nada queda escrito."""
        real = registros.bloquear_variedad

        def bloquear_y_que_otro_ocupe_el_sector(*argumentos):
            resultado = real(*argumentos)
            lote_de_carga_inicial(self.e, cantidad=95, etapa="maduracion", sector=self.e.sectores["maduracion"])
            return resultado

        with mock.patch("produccion.servicios.lotes_existentes.bloquear_variedad", side_effect=bloquear_y_que_otro_ocupe_el_sector):
            with self.assertRaises(ErrorDeProduccion) as contexto:
                registros.registrar_lote_existente(self.e.agronomo, datos(self.e))
        self.assertEqual(contexto.exception.codigo, "supera_agujeros")
        # El lote «ajeno» que simula el parche se crea DENTRO de la transacción del servicio, así que también se revierte: no queda ninguno.
        self.assertEqual(Lote.objects.count(), 0)
        self.assertEqual(AsientoContable.objects.count(), 0)

    def test_garantia_si_falla_el_asiento_no_queda_nada(self):
        """Garantías mínimas y requisito especial: todo en una transacción; si falla el asiento no queda siembra, lote, ocupación, bitácora ni log."""
        with mock.patch.object(registros.asientos, "registrar_asiento_automatico", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                registros.registrar_lote_existente(self.e.agronomo, datos(self.e))
        self.assertEqual((Siembra.objects.count(), Lote.objects.count(), OcupacionSector.objects.count(), Bitacora.objects.count()), (0, 0, 0, 0))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_lote_existente").count(), 0)
        agujeros = api_sectores.agujeros_de([self.e.sectores["maduracion"]])
        self.assertEqual(agujeros[self.e.sectores["maduracion"].pk].libres, 100)

    # ---- Lectura: pasos 2, 4, 6 y 8 ----

    def test_paso_2_invernaderos_disponibles_son_los_activos_a_cargo_sin_siembras_normales(self):
        """Paso 2 y extensión 2a: solo los invernaderos activos a cargo del Agrónomo sin siembra normal concretada."""
        con_siembra = invernadero_con_produccion(nombre="Con siembra", sufijo="2")
        lote_activo(con_siembra, cantidad=5)
        ajeno = invernadero_con_produccion(nombre="Ajeno", sufijo="3")
        self.assertEqual([i.pk for i in registros.invernaderos_disponibles(self.e.agronomo)], [self.e.invernadero.pk])
        self.assertEqual(registros.invernaderos_disponibles(con_siembra.agronomo), [])
        self.assertEqual([i.pk for i in registros.invernaderos_disponibles(ajeno.agronomo)], [ajeno.invernadero.pk])

    def test_paso_2_quien_no_es_agronomo_no_tiene_invernaderos_disponibles(self):
        """Regla «Quién registra»: para el Capataz, el Gerente o una cuenta inactiva la lista es vacía (la pantalla no muestra la acción)."""
        self.assertEqual(registros.invernaderos_disponibles(self.e.capataz), [])
        self.assertEqual(registros.invernaderos_disponibles(crear_gerente()), [])
        self.assertEqual(registros.invernaderos_disponibles(None), [])

    def test_paso_2_la_carga_inicial_previa_no_saca_al_invernadero_de_la_lista(self):
        """Regla «Cuándo»: tras una carga inicial el invernadero sigue disponible; tras concretar una siembra normal, deja de estarlo."""
        registros.registrar_lote_existente(self.e.agronomo, datos(self.e))
        self.assertEqual([i.pk for i in registros.invernaderos_disponibles(self.e.agronomo)], [self.e.invernadero.pk])
        lote_activo(self.e, cantidad=5)
        self.assertEqual(registros.invernaderos_disponibles(self.e.agronomo), [])

    def test_pasos_4_y_6_datos_de_registro_ofrece_variedades_etapas_y_sectores_elegibles_con_sus_libres(self):
        """Pasos 4 y 6: con el invernadero, la variedad y la etapa elegidos se ofrecen los sectores elegibles con sus agujeros libres."""
        sin_eleccion = registros.datos_de_registro(self.e.agronomo, self.e.invernadero.pk)
        self.assertEqual([i.pk for i in sin_eleccion.invernaderos], [self.e.invernadero.pk])
        self.assertIn(self.e.variedad.pk, [v.variedad_id for v in sin_eleccion.variedades])
        self.assertEqual(sin_eleccion.etapas, [])
        con_variedad = registros.datos_de_registro(self.e.agronomo, self.e.invernadero.pk, self.e.variedad.pk)
        self.assertEqual([e.codigo for e in con_variedad.etapas], ["germinacion", "crecimiento", "floracion", "fructificacion", "maduracion"])
        self.assertEqual(con_variedad.sectores, [])
        completo = registros.datos_de_registro(self.e.agronomo, self.e.invernadero.pk, self.e.variedad.pk, etapa_de(self.e.variedad, "maduracion"))
        self.assertEqual({(s.sector_id, s.libres) for s in completo.sectores},
                         {(self.e.sectores["maduracion"].pk, 100), (self.e.sectores["maduracion_2"].pk, 100)})

    def test_paso_6_datos_de_registro_con_una_siembra_normal_concretada_rechaza(self):
        """Extensión 2a: elegir un invernadero con siembras normales concretadas es `invernadero_con_siembras`."""
        lote_activo(self.e, cantidad=5)
        with self.assertRaises(ErrorDeProduccion) as contexto:
            registros.datos_de_registro(self.e.agronomo, self.e.invernadero.pk)
        self.assertEqual(contexto.exception.codigo, "invernadero_con_siembras")

    def test_paso_6_datos_de_registro_muestra_los_libres_descontando_lo_cargado(self):
        """Paso 6: los agujeros libres que se ofrecen descuentan lo que ya ocupan otros lotes."""
        registros.registrar_lote_existente(self.e.agronomo, datos(self.e, cantidad=30, distribucion={self.e.sectores["maduracion"].pk: 30}))
        completo = registros.datos_de_registro(self.e.agronomo, self.e.invernadero.pk, self.e.variedad.pk, etapa_de(self.e.variedad, "maduracion"))
        self.assertEqual({s.sector_id: s.libres for s in completo.sectores}[self.e.sectores["maduracion"].pk], 70)

    def test_paso_8_el_resumen_no_escribe_y_muestra_costo_por_planta_ocupacion_y_asiento(self):
        """Paso 8: el resumen trae la variedad, la etapa, las fechas, las cantidades, el costo estimado y por planta, la ocupación por sector con
        los agujeros que quedan libres y el asiento que se registrará; no escribe nada."""
        resumen = registros.resumen_de_registro(self.e.agronomo, datos(self.e))
        self.assertEqual((resumen.cantidad, resumen.costo_estimado, resumen.costo_por_planta), (180, D("12000.00"), D("66.67")))
        self.assertEqual(resumen.etapa.codigo, "maduracion")
        self.assertEqual({(s.sector_id, s.plantas, s.libres_despues) for s in resumen.distribucion},
                         {(self.e.sectores["maduracion"].pk, 100, 0), (self.e.sectores["maduracion_2"].pk, 80, 20)})
        self.assertEqual((resumen.asiento.debe[0], resumen.asiento.haber[0], resumen.asiento.importe),
                         (cuentas.PRODUCTOS_EN_PROCESO, cuentas.CAPITAL_INICIAL, D("12000.00")))
        self.assertEqual((Siembra.objects.count(), Lote.objects.count(), AsientoContable.objects.count()), (0, 0, 0))

    def test_paso_8_el_resumen_con_costo_cero_no_muestra_asiento(self):
        """Paso 8 y H11: con costo $0 no hay asiento previsto."""
        resumen = registros.resumen_de_registro(self.e.agronomo, datos(self.e, costo_estimado=D("0")))
        self.assertIsNone(resumen.asiento)
        self.assertEqual(resumen.costo_por_planta, D("0.00"))

    def test_paso_8_el_resumen_rechaza_lo_mismo_que_el_registro(self):
        """El resumen valida TODO (mismos rechazos que `registrar_lote_existente`), sin escribir."""
        for cambios, codigo in (
            ({"cantidad": 0}, "cantidad_invalida"),
            ({"costo_estimado": D("-1")}, "costo_invalido"),
            ({"fecha_siembra": hoy() + timedelta(days=1)}, "fecha_invalida"),
            ({"distribucion": {self.e.sectores["maduracion"].pk: 10}}, "distribucion_incompleta"),
        ):
            with self.assertRaises(ErrorDeProduccion) as contexto:
                registros.resumen_de_registro(self.e.agronomo, datos(self.e, **cambios))
            self.assertEqual(contexto.exception.codigo, codigo)

    # ---- Después de cargado ----

    def test_regla_despues_de_cargado_el_lote_se_puede_cancelar_nada_porque_ya_esta_concretada(self):
        """Regla «Siembra de carga inicial» y D-53: la orden de la carga ya está concretada y sin Capataz: cancelarla es `orden_no_pendiente`
        (no se lee `hija.capataz`) y el lote queda tal cual."""
        lote = registros.registrar_lote_existente(self.e.agronomo, datos(self.e))
        with self.assertRaises(ErrorDeProduccion) as contexto:
            ordenes.cancelar_orden(self.e.agronomo, lote.siembra_id, "Prueba")
        self.assertEqual(contexto.exception.codigo, "orden_no_pendiente")
        self.assertEqual(Lote.objects.get(pk=lote.pk).estado_lote, "activo")
