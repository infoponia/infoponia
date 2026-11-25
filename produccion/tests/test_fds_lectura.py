# Pruebas de la LECTURA de PROD-PNR-FDS (PRD-04, paso 3): `sectores_para_fuera_de_servicio`, `detalle_de_sector`,
# `fecha_minima_fuera_de_servicio` y `destinos_elegibles` (produccion/servicios/sectores_fuera_de_servicio.py).
# Fuente: docs/casos_de_uso/produccion/sector_fuera_de_servicio.md (reglas «Quién lo ejecuta», «Fecha mínima», «Sector de destino
# elegible», «Órdenes afectadas», extensiones 4a, 6c, 6d y 6e) y «Decisiones de aplicación». Ninguna de estas funciones escribe.

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from datetime import timedelta

from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Invernadero
from maestros.tests.fabricas import asegurar_datos_de_maestros, crear_agronomo, crear_invernadero, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, FueraDeServicio, OcupacionSector, Reubicacion
from produccion.servicios import sectores_fuera_de_servicio as fds
from produccion.tests.fabricas import (
    invernadero_con_produccion,
    lote_activo,
    orden_de_siembra,
    orden_de_transicion,
    variedad_con_stock,
)


def codigo_del_error(prueba, funcion, *argumentos):
    """El código del `ErrorDeProduccion` que lanza `funcion`."""
    with prueba.assertRaises(ErrorDeProduccion) as contexto:
        funcion(*argumentos)
    return contexto.exception.codigo


def registrar_alta(sector, actor, dias_atras, accion=RegistroAuditoria.Accion.ALTA_SECTOR):
    """Un registro de auditoría de `accion` sobre el sector, con la fecha de hace `dias_atras` días."""
    return RegistroAuditoria.objects.create(
        usuario=actor,
        rol="agronomo",
        accion=accion,
        fecha_hora=timezone.now() - timedelta(days=dias_atras),
        afectados=[{"modelo": "maestros.sectorproduccion", "id": sector.pk, "texto": sector.nombre_sector}],
        detalle={},
    )


def registro_de_bitacora(escenario, lote, dias_atras):
    """Un registro de bitácora del lote (un «otro evento») de hace `dias_atras` días."""
    return Bitacora.objects.create(
        invernadero=escenario.invernadero,
        lote=lote,
        tipo_evento="otro_evento",
        fecha_bitacora=timezone.localdate() - timedelta(days=dias_atras),
        hora_bitacora=timezone.localtime().time(),
        responsable=escenario.agronomo,
    )


class PruebaConEscenario(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):  # CON-04a: estos servicios asientan
    """Un invernadero con un sector por etapa. `self.germ` es el sector de Germinación; `otro_germ` es un segundo sector de Germinación."""

    @classmethod
    def setUpTestData(cls):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        cls.e = invernadero_con_produccion()
        cls.germ = cls.e.sectores["germinacion"]
        cls.hoy = timezone.localdate()

    def otro_germ(self, nombre="Germinación 2", agujeros=100, estado="activo"):
        """Un segundo sector de Germinación del invernadero, registrado en el escenario como `germ2` (o el nombre en minúsculas)."""
        sector = crear_sector(self.e.invernadero, nombre, "germinacion", agujeros, estado)
        self.e.sectores[nombre.lower().replace(" ", "_")] = sector
        return sector


class SectoresParaFueraDeServicioTests(PruebaConEscenario):
    """Paso 2 del caso de uso y precondición b: qué sectores se ofrecen."""

    def test_regla_quien_lo_ejecuta_ofrece_los_sectores_activos_agrupados_por_tipo_de_etapa(self):
        """Regla «Quién lo ejecuta» y paso 2: invernaderos activos del Agrónomo con sus sectores activos, por tipo de etapa."""
        self.otro_germ("Germinación 0")
        resultado = fds.sectores_para_fuera_de_servicio(self.e.agronomo)
        self.assertEqual([r.invernadero for r in resultado], [self.e.invernadero])
        grupos = resultado[0].grupos
        self.assertEqual([g.tipo_etapa.codigo for g in grupos], ["germinacion", "crecimiento", "floracion", "fructificacion", "maduracion"])
        self.assertEqual([s.nombre_sector for s in grupos[0].sectores], ["Germinación 0", "Sector germinacion"])

    def test_regla_sector_que_se_puede_poner_fuera_de_servicio_solo_los_activos(self):
        """Regla «Sector que se puede poner fuera de servicio»: uno fuera de servicio o dado de baja no se ofrece."""
        self.otro_germ("Fuera", estado="fuera_de_servicio")
        self.otro_germ("De baja", estado="inactivo")
        nombres = [s.nombre_sector for g in fds.sectores_para_fuera_de_servicio(self.e.agronomo)[0].grupos for s in g.sectores]
        self.assertNotIn("Fuera", nombres)
        self.assertNotIn("De baja", nombres)

    def test_regla_quien_lo_ejecuta_no_ofrece_invernaderos_de_otro_agronomo_ni_inactivos(self):
        """Regla «Quién lo ejecuta»: solo los invernaderos activos a cargo del actor."""
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com"))
        crear_sector(ajeno, "Ajeno-1", "germinacion")
        propio_inactivo = crear_invernadero("Inactivo", agronomo=self.e.agronomo, activo=False)
        crear_sector(propio_inactivo, "Inactivo-1", "germinacion")
        self.assertEqual([r.invernadero for r in fds.sectores_para_fuera_de_servicio(self.e.agronomo)], [self.e.invernadero])

    def test_pre_b_sin_sectores_activos_la_lista_queda_vacia(self):
        """Precondición b: sin ningún sector activo no hay nada que ofrecer (la pantalla queda deshabilitada con su motivo)."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(fds.sectores_para_fuera_de_servicio(self.e.agronomo), [])

    def test_regla_quien_lo_ejecuta_rechaza_al_capataz_y_a_nadie(self):
        """Regla «Quién lo ejecuta»: el Capataz no puede (`sin_permiso`)."""
        self.assertEqual(codigo_del_error(self, fds.sectores_para_fuera_de_servicio, self.e.capataz), "sin_permiso")
        self.assertEqual(codigo_del_error(self, fds.sectores_para_fuera_de_servicio, None), "sin_permiso")

    def test_la_cantidad_de_consultas_no_depende_de_los_sectores(self):
        """Una consulta por tabla, no por sector."""
        with CaptureQueriesContext(connection) as pocos:
            fds.sectores_para_fuera_de_servicio(self.e.agronomo)
        for numero in range(4):
            self.otro_germ(f"Extra {numero}")
        with CaptureQueriesContext(connection) as muchos:
            fds.sectores_para_fuera_de_servicio(self.e.agronomo)
        self.assertEqual(len(pocos), len(muchos))


class DetalleDeSectorTests(PruebaConEscenario):
    """Paso 4 del caso de uso: el detalle del sector elegido."""

    def test_paso_4_muestra_el_invernadero_los_lotes_con_sus_plantas_y_la_fecha_propuesta(self):
        """Paso 4, puntos 1, 2 y 4: invernadero, lotes con plantas en el sector y la fecha actual como fecha efectiva propuesta."""
        lote = lote_activo(self.e, cantidad=40)
        detalle = fds.detalle_de_sector(self.e.agronomo, self.germ.pk)
        self.assertEqual(detalle.invernadero, self.e.invernadero)
        self.assertEqual([(l.lote.pk, l.plantas, str(l.variedad)) for l in detalle.lotes], [(lote.pk, 40, str(self.e.variedad))])
        self.assertEqual(detalle.fecha_propuesta, self.hoy)
        self.assertFalse(detalle.sin_plantas)

    def test_paso_4_las_plantas_son_las_que_el_lote_tiene_en_el_sector_no_las_del_lote(self):
        """Paso 4, punto 2: «las plantas de cada uno en el sector». Un lote repartido en dos sectores cuenta solo las de este."""
        otro = self.otro_germ()
        lote = lote_activo(self.e, cantidad=30)
        orden = lote.siembra
        OcupacionSector.objects.create(orden=orden, sector=otro, lote=lote, cant_agujeros_planificados=20, cant_agujeros_ocupados=20)
        detalle = fds.detalle_de_sector(self.e.agronomo, self.germ.pk)
        self.assertEqual([l.plantas for l in detalle.lotes], [30])
        self.assertEqual([l.plantas for l in fds.detalle_de_sector(self.e.agronomo, otro.pk).lotes], [20])

    def test_paso_4_las_ordenes_son_las_a_realizar_con_agujeros_comprometidos_en_el_sector(self):
        """Paso 4, punto 3 y regla «Órdenes afectadas»: siembra (variedad) y transición (lote), con agujeros y fecha; no las concretadas
        ni las canceladas."""
        lote = lote_activo(self.e, cantidad=25, sector="germinacion")
        siembra = orden_de_siembra(self.e, plantines=15, sector="germinacion", dias=3)
        orden_de_siembra(self.e, plantines=10, sector="germinacion", estado="cancelada")
        transicion = orden_de_transicion(self.e, lote, distribucion={"germinacion": 25}, dias=1)
        detalle = fds.detalle_de_sector(self.e.agronomo, self.germ.pk)
        self.assertEqual([o.orden.pk for o in detalle.ordenes], [transicion.pk, siembra.pk])
        por_orden = {o.orden.pk: o for o in detalle.ordenes}
        self.assertEqual(por_orden[siembra.pk].agujeros, 15)
        self.assertEqual(por_orden[siembra.pk].detalle, str(self.e.variedad))
        self.assertEqual(por_orden[transicion.pk].detalle, f"lote {lote.codigo}")
        self.assertEqual(por_orden[siembra.pk].fecha_programada, self.hoy + timedelta(days=3))

    def test_ext_6d_sector_sin_plantas_ni_ordenes(self):
        """Extensión 6d: un sector vacío solo cambiará de estado: sin lotes ni órdenes."""
        detalle = fds.detalle_de_sector(self.e.agronomo, self.germ.pk)
        self.assertTrue(detalle.sin_plantas)
        self.assertTrue(detalle.sin_ordenes)
        self.assertEqual(detalle.lotes, [])
        self.assertEqual(detalle.ordenes, [])

    def test_ext_4a_el_ultimo_sector_activo_de_su_tipo_advierte_sin_bloquear(self):
        """Extensión 4a: es el último sector activo de su etapa: advierte que se queda sin sectores de esa etapa y recomienda."""
        detalle = fds.detalle_de_sector(self.e.agronomo, self.germ.pk)
        self.assertTrue(detalle.avisos)
        self.assertIn("se queda sin sectores activos de Germinación", detalle.avisos[0].texto)
        self.assertIn("Se recomienda registrar otro sector", detalle.avisos[0].texto)

    def test_ext_4a_incluye_las_siembras_a_realizar_que_dejan_de_poder_hacerse(self):
        """Extensión 4a, punto 3: reutiliza el cálculo de PROD-MOD-SCT (siembras a realizar de variedades que usan la etapa)."""
        orden_de_siembra(self.e, plantines=15, sector="germinacion")
        textos = " ".join(a.texto for a in fds.detalle_de_sector(self.e.agronomo, self.germ.pk).avisos)
        self.assertIn("siembra", textos.lower())

    def test_ext_4a_con_otro_sector_activo_del_tipo_no_hay_avisos(self):
        """Extensión 4a: si queda otro sector activo del tipo, no hay advertencia (uno fuera de servicio no cuenta como activo)."""
        self.otro_germ(estado="fuera_de_servicio")
        self.assertTrue(fds.detalle_de_sector(self.e.agronomo, self.germ.pk).avisos)
        self.otro_germ("Germinación 3")
        self.assertEqual(fds.detalle_de_sector(self.e.agronomo, self.germ.pk).avisos, [])

    def test_regla_quien_lo_ejecuta_solo_el_agronomo_a_cargo_ve_el_detalle(self):
        """Regla «Quién lo ejecuta»: el Capataz y un Agrónomo ajeno no (`sin_permiso`); un sector inexistente es 404."""
        self.assertEqual(codigo_del_error(self, fds.detalle_de_sector, self.e.capataz, self.germ.pk), "sin_permiso")
        ajeno = crear_agronomo(email="ajeno@infoponia.com")
        self.assertEqual(codigo_del_error(self, fds.detalle_de_sector, ajeno, self.germ.pk), "sin_permiso")
        with self.assertRaises(Http404):
            fds.detalle_de_sector(self.e.agronomo, 0)

    def test_regla_sector_que_se_puede_poner_fuera_de_servicio_rechaza_el_que_no_esta_activo(self):
        """Regla «Sector que se puede poner fuera de servicio»: un sector fuera de servicio o dado de baja se rechaza con `sector_no_activo`."""
        for estado in ("fuera_de_servicio", "inactivo"):
            sector = self.otro_germ(f"Estado {estado}", estado=estado)
            self.assertEqual(codigo_del_error(self, fds.detalle_de_sector, self.e.agronomo, sector.pk), "sector_no_activo")

    def test_regla_un_invernadero_inactivo_no_admite_operaciones_nuevas(self):
        """Regla 4 de PROD-BAJ-INV: con el invernadero dado de baja, `invernadero_inactivo`."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(codigo_del_error(self, fds.detalle_de_sector, self.e.agronomo, self.germ.pk), "invernadero_inactivo")

    def test_la_cantidad_de_consultas_no_depende_de_los_lotes_ni_de_las_ordenes(self):
        """Una consulta por tabla, no por fila."""
        lote_activo(self.e, cantidad=10)
        orden_de_siembra(self.e, plantines=5, sector="germinacion")
        with CaptureQueriesContext(connection) as pocas:
            fds.detalle_de_sector(self.e.agronomo, self.germ.pk)
        for _ in range(3):
            lote_activo(self.e, cantidad=10)
            orden_de_siembra(self.e, plantines=5, sector="germinacion", con_reserva=False)
        with CaptureQueriesContext(connection) as muchas:
            fds.detalle_de_sector(self.e.agronomo, self.germ.pk)
        self.assertEqual(len(pocas), len(muchas))


class FechaMinimaTests(PruebaConEscenario):
    """Regla «Fecha mínima» y extensión 6c."""

    def test_regla_fecha_minima_sin_nada_que_la_determine_no_hay_minima(self):
        """Un sector vacío y sin registros de auditoría no tiene fecha mínima."""
        resultado = fds.fecha_minima_fuera_de_servicio(self.germ)
        self.assertIsNone(resultado.fecha)
        self.assertEqual(resultado.origen, "")

    def test_regla_fecha_minima_es_la_ultima_activacion_derivada_de_la_auditoria(self):
        """Regla «Fecha mínima», punto 1 (D-51 punto 6): la fecha del último `alta_sector` o `reactivacion_sector` del sector."""
        registrar_alta(self.germ, self.e.agronomo, 30)
        registrar_alta(self.germ, self.e.agronomo, 10, accion=RegistroAuditoria.Accion.REACTIVACION_SECTOR)
        otro = self.otro_germ()
        registrar_alta(otro, self.e.agronomo, 1)  # el de otro sector no cuenta
        resultado = fds.fecha_minima_fuera_de_servicio(self.germ)
        self.assertEqual(resultado.fecha, self.hoy - timedelta(days=10))
        self.assertIn("última activación del sector", resultado.origen)
        self.assertIn((self.hoy - timedelta(days=10)).strftime("%d/%m/%Y"), resultado.origen)

    def test_regla_fecha_minima_incluye_el_fecha_fin_del_ultimo_registro_fuera_de_servicio(self):
        """Regla «Fecha mínima», punto 1: si volvió a servicio después de su alta, cuenta el `fecha_fin` más reciente."""
        registrar_alta(self.germ, self.e.agronomo, 30)
        FueraDeServicio.objects.create(
            invernadero=self.e.invernadero, tipo_evento="fuera_de_servicio", fecha_bitacora=self.hoy - timedelta(days=20),
            hora_bitacora=timezone.localtime().time(), motivo_fuera_de_servicio="Rotura", sector=self.germ,
            fecha_fin=self.hoy - timedelta(days=5),
        )
        resultado = fds.fecha_minima_fuera_de_servicio(self.germ)
        self.assertEqual(resultado.fecha, self.hoy - timedelta(days=5))
        self.assertIn("volvió a servicio", resultado.origen)

    def test_regla_fecha_minima_incluye_la_llegada_de_un_lote_por_su_siembra(self):
        """Regla «Fecha mínima», punto 2: la llegada de un lote sembrado en el sector es `siembra.fecha_siembra`."""
        registrar_alta(self.germ, self.e.agronomo, 30)
        lote = lote_activo(self.e)
        lote.siembra.fecha_siembra = self.hoy - timedelta(days=7)
        lote.siembra.save(update_fields=["fecha_siembra"])
        resultado = fds.fecha_minima_fuera_de_servicio(self.germ)
        self.assertEqual(resultado.fecha, self.hoy - timedelta(days=7))
        self.assertIn(f"llegada del lote {lote.codigo}", resultado.origen)

    def test_regla_fecha_minima_incluye_la_llegada_de_un_lote_por_su_transicion(self):
        """Regla «Fecha mínima», punto 2: la llegada por una transición es su `fecha_transicion`."""
        lote = lote_activo(self.e, cantidad=20)
        orden_de_transicion(self.e, lote, estado="concretada", fecha_efectiva=self.hoy - timedelta(days=4))
        resultado = fds.fecha_minima_fuera_de_servicio(self.e.sectores["crecimiento"])
        self.assertEqual(resultado.fecha, self.hoy - timedelta(days=4))
        self.assertIn("llegada del lote", resultado.origen)

    def test_regla_fecha_minima_incluye_la_llegada_de_un_lote_por_su_reubicacion(self):
        """Regla «Fecha mínima», punto 2: la llegada por una reubicación es su `fecha_bitacora`."""
        destino = self.otro_germ()
        lote = lote_activo(self.e, cantidad=20)
        reubicacion = Reubicacion.objects.create(
            invernadero=self.e.invernadero, lote=lote, tipo_evento="reubicacion", fecha_bitacora=self.hoy - timedelta(days=2),
            hora_bitacora=timezone.localtime().time(),
        )
        OcupacionSector.objects.create(
            reubicacion=reubicacion, sector=destino, lote=lote, cant_agujeros_planificados=20, cant_agujeros_ocupados=20
        )
        resultado = fds.fecha_minima_fuera_de_servicio(destino)
        self.assertEqual(resultado.fecha, self.hoy - timedelta(days=2))

    def test_regla_fecha_minima_incluye_el_ultimo_registro_de_bitacora_del_lote(self):
        """Regla «Fecha mínima», punto 3: el último registro de bitácora de los lotes del sector, aunque sea posterior a su llegada."""
        lote = lote_activo(self.e)
        lote.siembra.fecha_siembra = self.hoy - timedelta(days=9)
        lote.siembra.save(update_fields=["fecha_siembra"])
        registro_de_bitacora(self.e, lote, 3)
        registro_de_bitacora(self.e, lote, 6)
        resultado = fds.fecha_minima_fuera_de_servicio(self.germ)
        self.assertEqual(resultado.fecha, self.hoy - timedelta(days=3))
        self.assertIn(f"último registro de bitácora del lote {lote.codigo}", resultado.origen)

    def test_regla_fecha_minima_no_cuenta_la_bitacora_de_lotes_que_no_estan_en_el_sector(self):
        """Solo los lotes que ocupan el sector: la bitácora de otro lote no mueve la mínima."""
        propio = lote_activo(self.e, cantidad=10)
        propio.siembra.fecha_siembra = self.hoy - timedelta(days=8)
        propio.siembra.save(update_fields=["fecha_siembra"])
        ajeno = lote_activo(self.e, cantidad=10, sector="crecimiento", etapa="crecimiento")
        registro_de_bitacora(self.e, ajeno, 0)
        self.assertEqual(fds.fecha_minima_fuera_de_servicio(self.germ).fecha, self.hoy - timedelta(days=8))

    def test_la_cantidad_de_consultas_no_depende_de_los_lotes(self):
        """Cuatro consultas fijas, no una por lote."""
        lote_activo(self.e, cantidad=10)
        with CaptureQueriesContext(connection) as pocas:
            fds.fecha_minima_fuera_de_servicio(self.germ)
        for _ in range(3):
            lote_activo(self.e, cantidad=10)
        with CaptureQueriesContext(connection) as muchas:
            fds.fecha_minima_fuera_de_servicio(self.germ)
        self.assertEqual(len(pocas), len(muchas))


class DestinosElegiblesTests(PruebaConEscenario):
    """Regla «Sector de destino elegible» y extensiones 6e y 8b (la parte de lectura)."""

    def destinos(self, lotes):
        """`destinos_elegibles` del sector de Germinación para esos lotes, como `{lote_id: [nombres de sector]}`."""
        resultado = fds.destinos_elegibles(self.germ, lotes)
        return {lote_id: [d.sector.nombre_sector for d in lista] for lote_id, lista in resultado.items()}

    def test_regla_destino_elegible_mismo_invernadero_tipo_de_etapa_y_activo_distinto_del_origen(self):
        """Regla «Sector de destino elegible»: solo sectores activos del mismo invernadero y tipo de etapa, sin el de origen."""
        lote = lote_activo(self.e, cantidad=10)
        self.otro_germ("Destino bueno")
        self.otro_germ("Destino fuera", estado="fuera_de_servicio")
        self.otro_germ("Destino de baja", estado="inactivo")
        ajeno = crear_invernadero("Otro invernadero", agronomo=crear_agronomo(email="otro@infoponia.com"))
        crear_sector(ajeno, "Ajeno", "germinacion")
        self.assertEqual(self.destinos([lote]), {lote.pk: ["Destino bueno"]})  # no están Crecimiento ni el de origen

    def test_regla_destino_elegible_exige_agujeros_libres(self):
        """Regla «Sector de destino elegible»: con agujeros libres (total − ocupados − comprometidos). Uno lleno no se ofrece."""
        lote = lote_activo(self.e, cantidad=10)
        lleno = self.otro_germ("Lleno", agujeros=20)
        reservado = self.otro_germ("Reservado", agujeros=20)
        con_lugar = self.otro_germ("Con lugar", agujeros=20)
        e = self.e
        OcupacionSector.objects.create(
            orden=orden_de_siembra(e, plantines=20, sector="germinacion", con_reserva=False), sector=lleno, cant_agujeros_planificados=20
        )
        OcupacionSector.objects.create(
            orden=orden_de_siembra(e, plantines=5, sector="germinacion", con_reserva=False), sector=reservado, cant_agujeros_planificados=5
        )
        resultado = {d.sector.nombre_sector: d.libres for d in fds.destinos_elegibles(self.germ, [lote])[lote.pk]}
        self.assertEqual(resultado, {"Reservado": 15, "Con lugar": 20})
        self.assertNotIn("Lleno", resultado)
        self.assertIsNotNone(con_lugar)

    def test_regla_destino_elegible_no_cuenta_como_libres_los_comprometidos_por_las_ordenes_que_se_cancelan(self):
        """Decisión de aplicación: los comprometidos por las órdenes que esta misma operación cancela (aquí, una siembra con agujeros
        también en el destino) NO se cuentan como libres: así el resultado no depende del orden en que se apliquen."""
        lote = lote_activo(self.e, cantidad=10)
        destino = self.otro_germ("Destino", agujeros=30)
        siembra = orden_de_siembra(self.e, plantines=12, sector="germinacion", con_reserva=False)
        OcupacionSector.objects.create(orden=siembra, sector=destino, cant_agujeros_planificados=12)
        libres = {d.sector.nombre_sector: d.libres for d in fds.destinos_elegibles(self.germ, [lote])[lote.pk]}
        self.assertEqual(libres, {"Destino": 18})

    def test_regla_destino_elegible_exige_perfil_familiar_compatible(self):
        """Regla «Sector de destino elegible»: perfil compatible. Uno con plantas de otro perfil no se ofrece; uno vacío o del mismo, sí."""
        lote = lote_activo(self.e, cantidad=10)
        vacio = self.otro_germ("Vacío")
        mismo = self.otro_germ("Mismo perfil")
        distinto = self.otro_germ("Otro perfil")
        lote_activo(self.e, cantidad=5, sector="germinacion")  # variedad del escenario (hoja verde)
        OcupacionSector.objects.filter(sector=self.germ).exclude(lote=lote).update(sector=mismo)
        otra_variedad, _ = variedad_con_stock(self.e, nombre="De fruto", perfil="frutos_grandes")
        otro_lote = lote_activo(self.e, cantidad=4, variedad=otra_variedad)
        OcupacionSector.objects.filter(lote=otro_lote).update(sector=distinto)
        nombres = self.destinos([lote])[lote.pk]
        self.assertEqual(sorted(nombres), sorted(["Vacío", "Mismo perfil"]))
        self.assertIsNotNone(vacio)

    def test_ext_6e_un_lote_sin_destinos_elegibles_devuelve_lista_vacia(self):
        """Extensión 6e: sin destinos elegibles, la lista del lote está vacía (sus plantas se registrarán como merma)."""
        lote = lote_activo(self.e, cantidad=10)
        self.assertEqual(self.destinos([lote]), {lote.pk: []})

    def test_regla_destino_elegible_cada_lote_tiene_su_lista_segun_su_perfil(self):
        """Un lote por destino y varios al mismo destino: cada lote recibe su propia lista según el perfil de su variedad."""
        destino = self.otro_germ("Compartido")
        uno = lote_activo(self.e, cantidad=10)
        otro = lote_activo(self.e, cantidad=5)
        resultado = fds.destinos_elegibles(self.germ, [uno, otro])
        self.assertEqual([d.sector.pk for d in resultado[uno.pk]], [destino.pk])
        self.assertEqual([d.sector.pk for d in resultado[otro.pk]], [destino.pk])

    def test_destino_incluye_agujeros_libres_y_perfil(self):
        """El destino informa lo que muestra la pantalla: sus agujeros libres y su perfil familiar (`None` si está vacío)."""
        lote = lote_activo(self.e, cantidad=10)
        self.otro_germ("Destino", agujeros=40)
        destino = fds.destinos_elegibles(self.germ, [lote])[lote.pk][0]
        self.assertEqual((destino.libres, destino.perfil), (40, None))

    def test_la_cantidad_de_consultas_no_depende_de_los_lotes_ni_de_los_destinos(self):
        """Tres consultas fijas para toda la lista."""
        uno = lote_activo(self.e, cantidad=10)
        self.otro_germ("Destino 1")
        with CaptureQueriesContext(connection) as pocas:
            fds.destinos_elegibles(self.germ, [uno])
        otros = [lote_activo(self.e, cantidad=3) for _ in range(3)]
        for numero in range(3):
            self.otro_germ(f"Destino extra {numero}")
        with CaptureQueriesContext(connection) as muchas:
            fds.destinos_elegibles(self.germ, [uno, *otros])
        self.assertEqual(len(pocas), len(muchas))
