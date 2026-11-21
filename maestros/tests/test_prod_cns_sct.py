# Pruebas de PROD-CNS-SCT · Consultar Sector (docs/casos_de_uso/maestros/sectores.md) y de la capacidad de la ficha del
# invernadero (regla 3 de PROD-CNS-INV). Alcance por usuario en un único lugar (D-28); la consulta no se audita (SEG-14).
#
# Servicios que se prueban (maestros/servicios/sectores.py), tomados del módulo dentro de cada prueba:
#   consultar_sectores(actor, invernadero_id) -> sectores del invernadero dentro del alcance (PermissionDenied fuera de él,
#     Http404 si no existe); agrupar_sectores(sectores) -> (grupos, dados_de_baja); capacidad_del_invernadero(sectores,
#     agujeros); obtener_sector(actor, sector_id); agujeros_de(sectores); perfiles_de_sectores(ids);
#     contenido_de_sectores(sectores); acciones_permitidas(actor, sector); puede_agregar_sectores(actor, invernadero);
#     bloquear_sectores(invernadero_id, ids) (contrato de los puntos de extensión, docs/api/extensiones_de_maestros.md).

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from maestros.extensiones import Contenido
from maestros.models import SectorProduccion
from maestros.servicios import sectores
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    codigos_de,
    con_agujeros,
    con_extension,
    crear_agronomo,
    crear_agronomo_con_invernadero,
    crear_invernadero,
    crear_sector,
    error_de,
)


class ProdCnsSctServicioTests(ConDatosDeMaestros, TestCase):
    """Reglas y precondición de PROD-CNS-SCT."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()
        self.gerente = crear_gerente()

    # ---- precondición y alcance ----

    def test_pre_a_un_capataz_no_consulta_sectores(self):
        """PROD-CNS-SCT precondición a: Agrónomo o Gerente activos."""
        with self.assertRaises(PermissionDenied):
            sectores.consultar_sectores(crear_capataz(), self.invernadero.pk)

    def test_pre_a_una_cuenta_inactiva_no_consulta(self):
        """PROD-CNS-SCT precondición a: la cuenta tiene que estar activa."""
        self.agronomo.is_active = False
        self.agronomo.save()
        with self.assertRaises(PermissionDenied):
            sectores.consultar_sectores(self.agronomo, self.invernadero.pk)

    def test_regla_1_el_agronomo_a_cargo_consulta_los_sectores_de_su_invernadero(self):
        """PROD-CNS-SCT regla 1."""
        sector = crear_sector(self.invernadero, "C-1")
        self.assertEqual(list(sectores.consultar_sectores(self.agronomo, self.invernadero.pk)), [sector])

    def test_regla_1_el_agronomo_de_otro_invernadero_recibe_403(self):
        """PROD-CNS-SCT regla 1 y D-28: solo los invernaderos activos a su cargo (se aparta del texto de la
        «Verificación a mano», que decía «los ve sin acciones»: manda el caso de uso)."""
        with self.assertRaises(PermissionDenied):
            sectores.consultar_sectores(crear_agronomo(email="otro@infoponia.com"), self.invernadero.pk)

    def test_regla_1_el_gerente_consulta_los_sectores_de_cualquier_invernadero(self):
        """PROD-CNS-SCT regla 1: en solo lectura, de cualquier invernadero (también inactivo)."""
        sector = crear_sector(self.invernadero, "C-1")
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save()
        self.assertEqual(list(sectores.consultar_sectores(self.gerente, self.invernadero.pk)), [sector])

    def test_regla_1_un_invernadero_inactivo_no_lo_consulta_el_agronomo(self):
        """D-28: el alcance del Agrónomo son los invernaderos activos a su cargo."""
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save()
        with self.assertRaises(PermissionDenied):
            sectores.consultar_sectores(self.agronomo, self.invernadero.pk)

    def test_regla_1_un_invernadero_que_no_existe_da_404(self):
        """D-28: un id inexistente da 404."""
        with self.assertRaises(Http404):
            sectores.consultar_sectores(self.gerente, 999999)

    def test_regla_1_no_trae_los_sectores_de_otro_invernadero(self):
        """Los sectores se consultan por invernadero."""
        crear_sector(crear_invernadero("Otro", agronomo=self.agronomo), "X-1")
        self.assertEqual(list(sectores.consultar_sectores(self.agronomo, self.invernadero.pk)), [])

    def test_regla_1_obtener_un_sector_respeta_el_alcance(self):
        """D-28: 403 fuera del alcance y 404 si no existe."""
        sector = crear_sector(self.invernadero, "C-1")
        self.assertEqual(sectores.obtener_sector(self.agronomo, sector.pk), sector)
        self.assertEqual(sectores.obtener_sector(self.gerente, sector.pk), sector)
        with self.assertRaises(PermissionDenied):
            sectores.obtener_sector(crear_agronomo(email="otro@infoponia.com"), sector.pk)
        with self.assertRaises(Http404):
            sectores.obtener_sector(self.gerente, 999999)

    def test_regla_1_el_alcance_vive_en_el_queryset(self):
        """D-28 / CLAUDE.md: un único queryset de alcance por modelo."""
        sector = crear_sector(self.invernadero, "C-1")
        crear_sector(crear_invernadero("Otro", agronomo=crear_agronomo(email="otro@infoponia.com")), "X-1")
        self.assertEqual(list(SectorProduccion.objects.en_alcance_de(self.agronomo)), [sector])
        self.assertEqual(SectorProduccion.objects.en_alcance_de(self.gerente).count(), 2)
        self.assertEqual(SectorProduccion.objects.en_alcance_de(crear_capataz()).count(), 0)

    # ---- regla 2: agrupación ----

    def test_regla_2_los_sectores_se_agrupan_por_tipo_de_etapa_en_el_orden_de_las_etapas(self):
        """PROD-CNS-SCT regla 2: cantidad de sectores y de agujeros de cada grupo; solo los tipos que tienen sectores."""
        crear_sector(self.invernadero, "M-1", "maduracion", 30)
        crear_sector(self.invernadero, "G-1", "germinacion", 100)
        crear_sector(self.invernadero, "G-2", "germinacion", 50)
        crear_sector(self.invernadero, "F-1", "floracion", 20, estado="fuera_de_servicio")
        grupos, dados_de_baja = sectores.agrupar_sectores(sectores.consultar_sectores(self.agronomo, self.invernadero.pk))
        self.assertEqual(
            [(g.tipo_etapa.codigo, g.cantidad_de_sectores, g.cantidad_de_agujeros) for g in grupos],
            [("germinacion", 2, 150), ("floracion", 1, 20), ("maduracion", 1, 30)],
        )
        self.assertEqual([s.nombre_sector for s in grupos[0].sectores], ["G-1", "G-2"])
        self.assertEqual(dados_de_baja, [])

    def test_regla_2_los_dados_de_baja_van_en_un_grupo_aparte(self):
        """PROD-CNS-SCT regla 2: no cuentan en los grupos de las etapas."""
        crear_sector(self.invernadero, "G-1", "germinacion", 100)
        baja = crear_sector(self.invernadero, "G-2", "germinacion", 50, estado="inactivo")
        grupos, dados_de_baja = sectores.agrupar_sectores(sectores.consultar_sectores(self.agronomo, self.invernadero.pk))
        self.assertEqual([(g.cantidad_de_sectores, g.cantidad_de_agujeros) for g in grupos], [(1, 100)])
        self.assertEqual(dados_de_baja, [baja])

    # ---- regla 3: agujeros, perfil y contenido ----

    def test_regla_3_los_agujeros_libres_son_el_total_menos_ocupados_y_comprometidos(self):
        """PROD-CNS-SCT regla 3 y regla 5 de PROD-ALT-SCT: se calculan, no se guardan."""
        a = crear_sector(self.invernadero, "A", agujeros=100)
        b = crear_sector(self.invernadero, "B", agujeros=40)
        with con_agujeros(**{f"s{a.pk}": (30, 20)}):
            agujeros = sectores.agujeros_de([a, b])
        self.assertEqual(tuple(agujeros[a.pk]), (100, 30, 20, 50))
        self.assertEqual(tuple(agujeros[b.pk]), (40, 0, 0, 40))

    def test_regla_3_sin_registrantes_todo_el_sector_esta_libre(self):
        """«Cómo se aplica»: sin registrantes, 0 ocupados y 0 comprometidos."""
        a = crear_sector(self.invernadero, "A", agujeros=70)
        self.assertEqual(tuple(sectores.agujeros_de([a])[a.pk]), (70, 0, 0, 70))

    def test_regla_3_el_perfil_de_un_sector_vacio_es_none_y_el_de_uno_con_plantas_lo_da_el_registrante(self):
        """PROD-CNS-SCT regla 3: «sin plantas: acepta cualquier perfil» o el perfil familiar."""
        a = crear_sector(self.invernadero, "A")
        self.assertEqual(sectores.perfiles_de_sectores([a.pk]), {a.pk: None})
        with con_extension("_PERFILES", lambda ids: {i: "Hoja verde" for i in ids}):
            self.assertEqual(sectores.perfiles_de_sectores([a.pk]), {a.pk: "Hoja verde"})

    def test_regla_3_el_contenido_sale_de_los_registrantes(self):
        """PROD-CNS-SCT regla 3: lotes, órdenes y hardware vienen de los puntos de extensión."""
        a = crear_sector(self.invernadero, "A")
        self.assertEqual(sectores.contenido_de_sectores([a]), {a.pk: []})
        lote = Contenido("lote", "L-1 · Crespa", 40, None, None)
        with con_extension("_CONTENIDOS", lambda ss: {s.pk: [lote] for s in ss}):
            self.assertEqual(sectores.contenido_de_sectores([a]), {a.pk: [lote]})

    # ---- regla 5: sin sectores ----

    def test_regla_5_un_invernadero_sin_sectores_devuelve_una_lista_vacia_y_la_marca(self):
        """PROD-CNS-SCT regla 5: el Sistema lo informa (la pantalla usa esta lista vacía y ``tiene_sectores``)."""
        self.assertEqual(list(sectores.consultar_sectores(self.agronomo, self.invernadero.pk)), [])
        self.assertFalse(self.invernadero.tiene_sectores())

    # ---- capacidad de la ficha ----

    def test_regla_3_de_cns_inv_la_capacidad_por_tipo_cuenta_activos_y_fuera_de_servicio(self):
        """PROD-CNS-INV regla 3: por tipo, los agujeros, los libres y la cantidad de sectores; los dados de baja no cuentan."""
        a = crear_sector(self.invernadero, "A", "germinacion", 100)
        crear_sector(self.invernadero, "B", "germinacion", 40, estado="fuera_de_servicio")
        crear_sector(self.invernadero, "C", "germinacion", 999, estado="inactivo")
        sectores_del_invernadero = list(sectores.consultar_sectores(self.agronomo, self.invernadero.pk))
        with con_agujeros(**{f"s{a.pk}": (30, 20)}):
            agujeros = sectores.agujeros_de(sectores_del_invernadero)
        capacidad = sectores.capacidad_del_invernadero(sectores_del_invernadero, agujeros)
        self.assertEqual(len(capacidad), 1)
        self.assertEqual(capacidad[0].tipo_etapa.codigo, "germinacion")
        self.assertEqual((capacidad[0].agujeros, capacidad[0].libres, capacidad[0].cantidad_de_sectores), (140, 90, 2))

    # ---- acciones (D-30) ----

    def test_regla_6_el_agronomo_a_cargo_ve_las_acciones_segun_el_estado(self):
        """PROD-CNS-SCT regla 6: modificar y baja (y sacar de servicio, de PRD-04) si está activo; modificar, volver a
        activar y baja si está fuera de servicio; solo reactivar si está dado de baja."""
        activo = crear_sector(self.invernadero, "A")
        fuera = crear_sector(self.invernadero, "B", estado="fuera_de_servicio")
        baja = crear_sector(self.invernadero, "C", estado="inactivo")
        self.assertEqual(sectores.acciones_permitidas(self.agronomo, activo), {"modificar", "baja"})
        self.assertEqual(sectores.acciones_permitidas(self.agronomo, fuera), {"modificar", "volver_a_servicio", "baja"})
        self.assertEqual(sectores.acciones_permitidas(self.agronomo, baja), {"reactivar"})

    def test_regla_1_el_gerente_y_los_demas_no_ven_acciones(self):
        """PROD-CNS-SCT regla 1 y D-30: el Gerente consulta en solo lectura; ningún botón lleva a un 403."""
        sector = crear_sector(self.invernadero, "A")
        for actor in (self.gerente, crear_agronomo(email="otro@infoponia.com"), crear_capataz()):
            with self.subTest(actor=actor):
                self.assertEqual(sectores.acciones_permitidas(actor, sector), frozenset())
                self.assertFalse(sectores.puede_agregar_sectores(actor, self.invernadero))

    def test_regla_6_con_el_invernadero_inactivo_no_hay_acciones(self):
        """D-30: el invernadero tiene que estar activo."""
        sector = crear_sector(self.invernadero, "A")
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save()
        self.assertEqual(sectores.acciones_permitidas(self.agronomo, sector), frozenset())
        self.assertFalse(sectores.puede_agregar_sectores(self.agronomo, self.invernadero))

    def test_regla_5_el_agronomo_a_cargo_puede_agregar_sectores(self):
        """PROD-CNS-SCT regla 5: al Agrónomo a cargo le ofrece registrar uno."""
        self.assertTrue(sectores.puede_agregar_sectores(self.agronomo, self.invernadero))

    # ---- regla 7 ----

    def test_regla_7_la_consulta_no_audita(self):
        """PROD-CNS-SCT regla 7 y SEG-14."""
        sector = crear_sector(self.invernadero, "A")
        sectores.consultar_sectores(self.agronomo, self.invernadero.pk)
        sectores.obtener_sector(self.agronomo, sector.pk)
        sectores.agujeros_de([sector])
        self.assertFalse(RegistroAuditoria.objects.exists())


class BloquearSectoresTests(ConDatosDeMaestros, TestCase):
    """``bloquear_sectores``: el contrato que usan PRD-01 y PRD-02 para reservar agujeros
    (docs/api/extensiones_de_maestros.md, «Sectores»)."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()

    def test_ext_devuelve_los_sectores_activos_releidos_en_orden_de_id(self):
        """API: ``FOR NO KEY UPDATE``, en orden de id, ya releídos."""
        b = crear_sector(self.invernadero, "B")
        a = crear_sector(self.invernadero, "A")
        resultado = sectores.bloquear_sectores(self.invernadero.pk, [a.pk, b.pk])
        self.assertEqual([s.pk for s in resultado], sorted([a.pk, b.pk]))

    def test_ext_rechaza_un_sector_que_no_es_del_invernadero(self):
        """API: ``sector_no_disponible``."""
        ajeno = crear_sector(crear_invernadero("Otro", agronomo=self.agronomo), "X")
        error = error_de(lambda: sectores.bloquear_sectores(self.invernadero.pk, [ajeno.pk]))
        self.assertEqual(codigos_de(error), ["sector_no_disponible"])

    def test_ext_rechaza_un_sector_inactivo_o_fuera_de_servicio(self):
        """API: un sector fuera de servicio o inactivo no recibe plantas ni órdenes."""
        for estado in ("inactivo", "fuera_de_servicio"):
            with self.subTest(estado=estado):
                sector = crear_sector(self.invernadero, f"S-{estado}", estado=estado)
                error = error_de(lambda: sectores.bloquear_sectores(self.invernadero.pk, [sector.pk]))
                self.assertEqual(codigos_de(error), ["sector_no_disponible"])

    def test_ext_rechaza_un_id_que_no_existe(self):
        """API: un id inexistente tampoco está disponible."""
        with self.assertRaises(ValidationError):
            sectores.bloquear_sectores(self.invernadero.pk, [999999])

    def test_ext_bloquea_con_el_invernadero_activo(self):
        """Contrato de D-40: con el invernadero inactivo se rechaza (``invernadero_inactivo``)."""
        sector = crear_sector(self.invernadero, "A")
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save()
        error = error_de(lambda: sectores.bloquear_sectores(self.invernadero.pk, [sector.pk]))
        self.assertIn("invernadero_inactivo", codigos_de(error, NON_FIELD_ERRORS) + codigos_de(error))
