# Pruebas de la lectura de variedades (INV-03, paso 3): `inventario/servicios/variedades.py` (docs/api/variedades.md, «Lectura
# (variedades.py)» y «Bloqueo»). Quién usa una variedad, quién puede gestionarla (regla 1 de PROD-MOD-VAR), qué acciones ofrece la consulta
# (regla 4 de PROD-CNS-VAR) y el bloqueo que usan PRD-01 y PRD-02. Lotes y órdenes se simulan con registrantes falsos
# (`usos_de_variedad_de_prueba`): `produccion` todavía no existe.

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from inventario.extensiones import UsoDeVariedad
from inventario.models import Semilla
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    perezoso,
    usos_de_variedad_de_prueba,
    variedad_con_semilla,
    variedades_presentes_de_prueba,
)
from maestros.extensiones import Impedimento
from maestros.tests.fabricas import crear_agronomo, crear_cultivo, crear_invernadero

variedades = perezoso("inventario.servicios.variedades")


def con_lotes_en(*invernaderos):
    """El uso de una variedad con lotes activos en esos invernaderos (lo que informaría `produccion`)."""
    return UsoDeVariedad(True, len(invernaderos), 0, frozenset(g.pk for g in invernaderos))


class ObtenerVariedadTests(ConDatosDeInventario, TestCase):
    """``obtener_variedad(variedad_id)``."""

    def test_api_trae_la_variedad_con_su_cultivo_en_una_consulta(self):
        """docs/api/variedades.md: la variedad con su cultivo (``select_related``)."""
        variedad = variedad_con_semilla(nombre="Butterhead")
        with self.assertNumQueries(1):
            leida = variedades.obtener_variedad(variedad.pk)
            self.assertEqual(leida.cultivo.nombre_cultivo, "Lechuga")
        self.assertEqual(leida.pk, variedad.pk)

    def test_api_un_id_inexistente_da_404(self):
        """docs/api/variedades.md: ``Http404`` si no existe."""
        with self.assertRaises(Http404):
            variedades.obtener_variedad(999999)


class SemillaDeYRangosDeTests(ConDatosDeInventario, TestCase):
    """``semilla_de(variedad_ids)`` y ``rangos_de(variedad_ids)``."""

    def test_api_semilla_de_da_la_semilla_de_cada_variedad_en_una_consulta(self):
        """docs/api/variedades.md: la semilla de cada variedad (siempre existe: se crea con ella), una consulta."""
        a, b = variedad_con_semilla(nombre="A"), variedad_con_semilla(nombre="B")
        with self.assertNumQueries(1):
            resultado = variedades.semilla_de([a.pk, b.pk])
        self.assertEqual({i: s.nombre_insumo for i, s in resultado.items()}, {a.pk: "Semilla Lechuga A", b.pk: "Semilla Lechuga B"})
        self.assertIsInstance(resultado[a.pk], Semilla)

    def test_api_rangos_de_devuelve_los_cuatro_rangos_como_decimal_en_una_consulta(self):
        """docs/api/variedades.md: ``Rangos(temp_ambiente, humedad, intensidad_luz, fotoperiodo)``, cada uno ``RangoAmbiental(minimo, maximo)``
        con ``Decimal``; una consulta para toda la lista."""
        a = variedad_con_semilla(nombre="A", temp_ambiente_min="18.5", temp_ambiente_max="24", fotoperiodo_min="10", fotoperiodo_max="16.25")
        b = variedad_con_semilla(nombre="B")
        with self.assertNumQueries(1):
            rangos = variedades.rangos_de([a.pk, b.pk])
        self.assertEqual(rangos[a.pk].temp_ambiente, variedades.RangoAmbiental(Decimal("18.50"), Decimal("24.00")))
        self.assertEqual(rangos[a.pk].fotoperiodo, variedades.RangoAmbiental(Decimal("10.00"), Decimal("16.25")))
        self.assertEqual(rangos[a.pk].humedad, variedades.RangoAmbiental(Decimal("60.00"), Decimal("80.00")))
        self.assertEqual(rangos[a.pk].intensidad_luz, variedades.RangoAmbiental(Decimal("200.00"), Decimal("400.00")))
        self.assertIsInstance(rangos[b.pk].temp_ambiente.minimo, Decimal)


class UsoYInvernaderosQueUsanTests(ConDatosDeInventario, TestCase):
    """``uso_de_variedades`` e ``invernaderos_que_usan``: un invernadero ACTIVO usa la variedad si tiene su semilla habilitada
    (``InsumoInvernadero`` activo) o lotes activos de ella (regla 1 de PROD-MOD-VAR)."""

    def setUp(self):
        self.variedad = variedad_con_semilla()
        self.norte = crear_invernadero("Invernadero Norte")
        self.sur = crear_invernadero("Invernadero Sur")

    def usan(self, *ids):
        return variedades.invernaderos_que_usan(list(ids or [self.variedad.pk]))

    def test_api_uso_de_variedades_sin_registrantes_es_el_neutro(self):
        """docs/api/extensiones_de_inventario.md: sin registrantes, ``UsoDeVariedad(False, 0, 0, frozenset())``."""
        self.assertEqual(variedades.uso_de_variedades([self.variedad.pk]), {self.variedad.pk: UsoDeVariedad(False, 0, 0, frozenset())})

    def test_api_uso_de_variedades_trae_lo_que_informa_produccion(self):
        """docs/api/variedades.md: ``uso_de_variedades`` devuelve lo que informan los registrantes."""
        uso = UsoDeVariedad(True, 2, 1, frozenset({self.norte.pk}))
        with usos_de_variedad_de_prueba({self.variedad.pk: uso}):
            self.assertEqual(variedades.uso_de_variedades([self.variedad.pk])[self.variedad.pk], uso)

    def test_regla_mod_var_1_una_variedad_sin_semilla_habilitada_ni_lotes_no_la_usa_nadie(self):
        """PROD-MOD-VAR regla 1: sin semilla habilitada ni lotes activos, ningún invernadero la usa."""
        self.assertEqual(self.usan(), {self.variedad.pk: set()})

    def test_regla_mod_var_1_la_semilla_habilitada_cuenta_como_uso(self):
        """PROD-MOD-VAR regla 1: un invernadero activo con la semilla habilitada usa la variedad."""
        existencia(self.variedad.semilla, self.norte)
        self.assertEqual(self.usan(), {self.variedad.pk: {self.norte.pk}})

    def test_regla_mod_var_1_la_semilla_deshabilitada_no_cuenta(self):
        """PROD-MOD-VAR regla 1: la existencia inactiva (deshabilitada) no es un uso."""
        existencia(self.variedad.semilla, self.norte, activo=False)
        self.assertEqual(self.usan(), {self.variedad.pk: set()})

    def test_regla_mod_var_1_los_lotes_activos_cuentan_como_uso(self):
        """PROD-MOD-VAR regla 1: un invernadero activo con lotes activos de la variedad la usa."""
        with usos_de_variedad_de_prueba({self.variedad.pk: con_lotes_en(self.sur)}):
            self.assertEqual(self.usan(), {self.variedad.pk: {self.sur.pk}})

    def test_regla_mod_var_1_semilla_habilitada_y_lotes_se_unen(self):
        """PROD-MOD-VAR regla 1: los invernaderos de la semilla habilitada y los de lotes activos se juntan."""
        existencia(self.variedad.semilla, self.norte)
        with usos_de_variedad_de_prueba({self.variedad.pk: con_lotes_en(self.sur)}):
            self.assertEqual(self.usan(), {self.variedad.pk: {self.norte.pk, self.sur.pk}})

    def test_regla_mod_var_1_un_invernadero_inactivo_no_cuenta_como_usuario(self):
        """PROD-MOD-VAR regla 1: solo cuentan los invernaderos ACTIVOS, por semilla habilitada o por lotes."""
        inactivo = crear_invernadero("Invernadero Viejo", activo=False)
        existencia(self.variedad.semilla, inactivo)
        with usos_de_variedad_de_prueba({self.variedad.pk: con_lotes_en(inactivo)}):
            self.assertEqual(self.usan(), {self.variedad.pk: set()})

    def test_api_cada_id_pedido_figura_aunque_nadie_lo_use(self):
        """docs/api/variedades.md: ``dict[int, set[int]]``; todo id pedido figura."""
        otra = variedad_con_semilla(nombre="Otra")
        existencia(self.variedad.semilla, self.norte)
        self.assertEqual(self.usan(self.variedad.pk, otra.pk), {self.variedad.pk: {self.norte.pk}, otra.pk: set()})

    def test_api_las_consultas_no_crecen_con_la_cantidad_de_variedades(self):
        """docs/api/variedades.md: una consulta por tabla para toda la lista de ids, nunca una por variedad."""
        mas = [variedad_con_semilla(nombre=f"V{n}") for n in range(4)]
        for variedad in mas:
            existencia(variedad.semilla, self.norte)
        with CaptureQueriesContext(connection) as una:
            self.usan(mas[0].pk)
        with CaptureQueriesContext(connection) as varias:
            self.usan(*[v.pk for v in mas])
        self.assertEqual(len(varias), len(una))


class PuedeGestionarTests(ConDatosDeInventario, TestCase):
    """``puede_gestionar(actor, variedad)`` (regla 1 de PROD-MOD-VAR) con sus tres casos."""

    def setUp(self):
        self.ana = crear_agronomo("ana@infoponia.com", nombre="Ana", apellido="Pérez")
        self.beto = crear_agronomo("beto@infoponia.com", nombre="Beto", apellido="Gómez")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.beto)
        self.variedad = variedad_con_semilla()

    def test_regla_mod_var_1_si_ningun_invernadero_la_usa_cualquier_agronomo_activo_puede(self):
        """PROD-MOD-VAR regla 1: si ningún invernadero la usa, cualquier Agrónomo activo la gestiona."""
        for actor in (self.ana, self.beto, crear_agronomo("sin.invernadero@infoponia.com")):
            with self.subTest(actor=actor.email):
                resultado = variedades.puede_gestionar(actor, self.variedad)
                self.assertTrue(resultado.puede)
                self.assertEqual(resultado.quienes, [])

    def test_regla_mod_var_1_la_gestiona_el_agronomo_de_un_invernadero_que_la_usa(self):
        """PROD-MOD-VAR regla 1: la gestiona el Agrónomo de algún invernadero que la use (semilla habilitada o lotes)."""
        existencia(self.variedad.semilla, self.norte)
        with usos_de_variedad_de_prueba({self.variedad.pk: con_lotes_en(self.sur)}):
            self.assertTrue(variedades.puede_gestionar(self.ana, self.variedad).puede)
            self.assertTrue(variedades.puede_gestionar(self.beto, self.variedad).puede)

    def test_regla_mod_var_1_el_que_no_tiene_invernadero_que_la_use_no_puede_y_se_le_dice_quienes(self):
        """PROD-MOD-VAR regla 1: si no puede gestionarla, el Sistema informa qué invernaderos la usan y quiénes son sus Agrónomos."""
        existencia(self.variedad.semilla, self.norte)
        resultado = variedades.puede_gestionar(self.beto, self.variedad)
        self.assertFalse(resultado.puede)
        self.assertEqual(resultado.quienes, ["Invernadero Norte (Ana Pérez)"])

    def test_regla_mod_var_1_un_invernadero_sin_agronomo_se_nombra_como_tal(self):
        """docs/api/variedades.md: «Invernadero Sur (sin Agrónomo)»; mientras algún invernadero la use con Agrónomo, ese la gestiona."""
        huerfano = crear_invernadero("Invernadero Oeste")
        existencia(self.variedad.semilla, huerfano)
        existencia(self.variedad.semilla, self.norte)
        resultado = variedades.puede_gestionar(self.beto, self.variedad)
        self.assertFalse(resultado.puede)
        self.assertEqual(resultado.quienes, ["Invernadero Norte (Ana Pérez)", "Invernadero Oeste (sin Agrónomo)"])

    def test_regla_mod_var_1_si_todos_los_que_la_usan_estan_sin_agronomo_nadie_la_gestiona(self):
        """docs/casos_de_uso/inventario/variedades.md, «Quién puede gestionar»: nadie hasta que el Gerente asigne un Agrónomo."""
        huerfano = crear_invernadero("Invernadero Oeste")
        existencia(self.variedad.semilla, huerfano)
        for actor in (self.ana, self.beto):
            resultado = variedades.puede_gestionar(actor, self.variedad)
            self.assertFalse(resultado.puede)
            self.assertEqual(resultado.quienes, ["Invernadero Oeste (sin Agrónomo)"])

    def test_regla_mod_var_1_un_invernadero_inactivo_no_impide_gestionar(self):
        """PROD-MOD-VAR regla 1: un invernadero inactivo no es «usuario» de la variedad: no limita quién la gestiona."""
        viejo = crear_invernadero("Invernadero Viejo", activo=False, agronomo=self.ana)
        existencia(self.variedad.semilla, viejo)
        resultado = variedades.puede_gestionar(self.beto, self.variedad)
        self.assertTrue(resultado.puede)
        self.assertEqual(resultado.quienes, [])

    def test_pre_a_quien_no_es_agronomo_activo_no_puede(self):
        """PROD-MOD-VAR precondición a: solo un Agrónomo activo gestiona variedades."""
        inactivo = crear_agronomo("inactivo@infoponia.com", activo=False)
        self.assertFalse(variedades.puede_gestionar(inactivo, self.variedad).puede)
        self.assertFalse(variedades.puede_gestionar(None, self.variedad).puede)


class AccionesPermitidasTests(ConDatosDeInventario, TestCase):
    """``acciones_permitidas(actor, variedad)`` (regla 4 de PROD-CNS-VAR): las mismas reglas de ``puede_gestionar``."""

    def setUp(self):
        self.ana = crear_agronomo("ana@infoponia.com", nombre="Ana", apellido="Pérez")
        self.beto = crear_agronomo("beto@infoponia.com", nombre="Beto", apellido="Gómez")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)

    def test_regla_cns_var_4_variedad_activa_y_gestora_ofrece_modificar_y_dar_de_baja(self):
        """PROD-CNS-VAR regla 4: de una variedad activa, el Agrónomo que puede gestionarla inicia modificar o dar de baja."""
        acciones = variedades.acciones_permitidas(self.ana, variedad_con_semilla())
        self.assertEqual((acciones.modificar, acciones.dar_de_baja, acciones.reactivar), (True, True, False))
        self.assertEqual(acciones.motivo, "")

    def test_regla_cns_var_4_variedad_inactiva_ofrece_solo_reactivar(self):
        """PROD-CNS-VAR regla 4: de una variedad inactiva, solo reactivarla (con el cultivo activo)."""
        acciones = variedades.acciones_permitidas(self.ana, variedad_con_semilla(activa=False))
        self.assertEqual((acciones.modificar, acciones.dar_de_baja, acciones.reactivar), (False, False, True))

    def test_regla_cns_var_4_inactiva_con_cultivo_inactivo_no_se_puede_reactivar_y_dice_por_que(self):
        """PROD-CNS-VAR regla 4 y PROD-MOD-VAR regla 9: solo se reactiva si su cultivo está activo: «Primero reactivá el cultivo X»."""
        cultivo = crear_cultivo("Rúcula", activo=False)
        acciones = variedades.acciones_permitidas(self.ana, variedad_con_semilla(cultivo, activa=False))
        self.assertEqual((acciones.modificar, acciones.dar_de_baja, acciones.reactivar), (False, False, False))
        self.assertEqual(acciones.motivo, "Primero reactivá el cultivo Rúcula.")

    def test_regla_cns_var_4_sin_permiso_las_acciones_quedan_deshabilitadas_con_el_nombre_de_quien_la_usa(self):
        """PROD-CNS-VAR regla 4: si no puede gestionarla, las acciones aparecen deshabilitadas con el nombre de quién la usa."""
        variedad = variedad_con_semilla()
        existencia(variedad.semilla, self.norte)
        acciones = variedades.acciones_permitidas(self.beto, variedad)
        self.assertEqual((acciones.modificar, acciones.dar_de_baja, acciones.reactivar), (False, False, False))
        self.assertEqual(acciones.motivo, "Solo la usa Invernadero Norte (Ana Pérez).")

    def test_regla_cns_var_4_inactiva_sin_permiso_tampoco_se_reactiva(self):
        """PROD-MOD-VAR regla 1: reactivar también exige poder gestionarla (su semilla puede seguir habilitada tras la baja)."""
        variedad = variedad_con_semilla(activa=False)
        existencia(variedad.semilla, self.norte)
        acciones = variedades.acciones_permitidas(self.beto, variedad)
        self.assertFalse(acciones.reactivar)
        self.assertEqual(acciones.motivo, "Solo la usa Invernadero Norte (Ana Pérez).")


class VariedadesActivasTests(ConDatosDeInventario, TestCase):
    """``variedades_activas(cultivo_id=None)``: lo que PRD-01 ofrece para sembrar."""

    def setUp(self):
        self.lechuga, self.rucula = crear_cultivo("Lechuga"), crear_cultivo("Rúcula")
        self.crespa = variedad_con_semilla(self.lechuga, "Crespa")
        self.butter = variedad_con_semilla(self.lechuga, "Butterhead")
        self.baja = variedad_con_semilla(self.lechuga, "Roja", activa=False)
        self.salvaje = variedad_con_semilla(self.rucula, "Salvaje")

    def test_api_solo_variedades_activas(self):
        """docs/api/variedades.md: las variedades activas; una dada de baja no se ofrece para sembrar (PROD-BAJ-VAR postcondición a)."""
        self.assertEqual({v.pk for v in variedades.variedades_activas()}, {self.crespa.pk, self.butter.pk, self.salvaje.pk})

    def test_api_solo_de_cultivos_activos(self):
        """docs/api/variedades.md: de cultivos activos."""
        self.rucula.estado_cultivo = "inactivo"
        self.rucula.save()
        self.assertEqual({v.pk for v in variedades.variedades_activas()}, {self.crespa.pk, self.butter.pk})

    def test_api_filtra_por_cultivo(self):
        """docs/api/variedades.md: ``variedades_activas(cultivo_id=None)`` filtra por cultivo."""
        self.assertEqual({v.pk for v in variedades.variedades_activas(self.rucula.pk)}, {self.salvaje.pk})

    def test_api_trae_el_ciclo_y_el_cultivo_sin_consultas_por_fila(self):
        """docs/api/variedades.md: con su ciclo; una sola consulta aunque se lean el ciclo y el cultivo de cada variedad."""
        with self.assertNumQueries(1):
            filas = list(variedades.variedades_activas())
            for variedad in filas:
                self.assertTrue(variedad.ciclo.pk and variedad.cultivo.nombre_cultivo)


class BloquearVariedadTests(ConDatosDeInventario, TestCase):
    """``bloquear_variedad(variedad_id)``: la usa quien crea un lote o una orden (reglas 3 y 4 de PROD-MOD-VAR, d y e de PROD-BAJ-VAR)."""

    def test_api_devuelve_la_variedad_releida_si_esta_activa(self):
        """docs/api/variedades.md: ``FOR NO KEY UPDATE``, ya releída, solo si está activa."""
        variedad = variedad_con_semilla()
        with transaction.atomic():
            self.assertEqual(variedades.bloquear_variedad(variedad.pk).pk, variedad.pk)

    def test_api_una_variedad_inactiva_da_variedad_inactiva(self):
        """docs/api/variedades.md: si no está activa, ``ValidationError`` de código ``variedad_inactiva``."""
        variedad = variedad_con_semilla(activa=False)
        with transaction.atomic(), self.assertRaises(ValidationError) as contexto:
            variedades.bloquear_variedad(variedad.pk)
        self.assertEqual(contexto.exception.code, "variedad_inactiva")

    def test_api_un_id_inexistente_da_404(self):
        """docs/api/variedades.md: una variedad que no existe es 404."""
        with transaction.atomic(), self.assertRaises(Http404):
            variedades.bloquear_variedad(999999)


class DelegadasDeLasExtensionesTests(ConDatosDeInventario, TestCase):
    """``impedimentos_de_baja_de_variedad`` y ``variedades_presentes`` de ``variedades.py`` entregan lo de los registrantes."""

    def test_regla_baj_var_2_los_impedimentos_salen_juntos(self):
        """PROD-BAJ-VAR regla 2: los impedimentos de todos los registrantes, juntos."""
        variedad = variedad_con_semilla()
        lotes = Impedimento("lotes_activos", "Tiene 2 lotes activos.", "Terminalos con su cosecha o su merma.")
        with usos_de_variedad_de_prueba(impedimentos={variedad.pk: [lotes]}):
            self.assertEqual(variedades.impedimentos_de_baja_de_variedad(variedad), [lotes])

    def test_regla_baj_var_2_sin_registrantes_no_hay_impedimentos(self):
        """PROD-BAJ-VAR: sin `produccion` ni `comercial`, nada impide la baja."""
        self.assertEqual(variedades.impedimentos_de_baja_de_variedad(variedad_con_semilla()), [])

    def test_api_variedades_presentes_trae_lo_de_los_registrantes(self):
        """docs/api/extensiones_de_inventario.md: variedades con lotes activos u órdenes de siembra a realizar, por invernadero."""
        norte = crear_invernadero("Invernadero Norte")
        with variedades_presentes_de_prueba({norte.pk: {7, 8}}):
            self.assertEqual(variedades.variedades_presentes([norte.pk, 99]), {norte.pk: {7, 8}, 99: set()})
