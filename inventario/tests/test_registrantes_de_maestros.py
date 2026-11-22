# Pruebas de lo que `inventario` registra en `maestros` (INV-03, paso 7; docs/api/extensiones_de_maestros.md, «Cultivos», y
# docs/api/extensiones_de_inventario.md, «Lo que `inventario` registra en `maestros` (INV-03)»): `registrar_semillas_de_cultivo` (contar y
# renombrar), `registrar_uso_de_cultivo` y la prueba de punta a punta con `modificar_cultivo` de MAE-03 (PROD-MOD-CLT reglas 3 y 4).
#
# Contrato que fijan estas pruebas (funciones de `inventario`; `InventarioConfig.ready()` las registra, de forma idempotente):
#   - ``semillas.contar_semillas_del_cultivo(cultivo) -> int``: las semillas de TODAS las variedades del cultivo (activas e inactivas),
#     que son las que cambian de nombre si se renombra el cultivo. Una consulta.
#   - ``semillas.renombrar_semillas_del_cultivo(actor, cultivo, nombre_anterior) -> int``: con el cultivo YA renombrado, deja cada semilla
#     como «Semilla {cultivo} {variedad}» y devuelve cuántas cambiaron. Bloquea las filas de ``Insumo`` de una vez y con ``ORDER BY id``
#     (último nivel del orden cultivo -> variedad -> insumo), escribe UN registro ``modificacion_semilla`` por semilla renombrada y es
#     todo o nada: si un nombre choca con otro insumo (o la restricción única salta a la vez en otro pedido) lanza un error del campo
#     ``nombre`` y no queda ninguna semilla renombrada.
#   - ``variedades.invernaderos_que_usan_el_cultivo(cultivo) -> set[int]``: los invernaderos ACTIVOS que usan alguna variedad del cultivo
#     (semilla habilitada o lotes activos): la unión de ``invernaderos_que_usan`` de sus variedades.

from unittest import mock

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.models import Notificacion, RegistroAuditoria
from inventario.extensiones import UsoDeVariedad
from inventario.models import Insumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    insumo,
    perezoso,
    tipo_de_insumo,
    usos_de_variedad_de_prueba,
    variedad_con_semilla,
)
from maestros import extensiones
from maestros.servicios import cultivos
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_cultivo, crear_invernadero, error_de

semillas = perezoso("inventario.servicios.semillas")
variedades = perezoso("inventario.servicios.variedades")


class BaseDeRegistrantes(ConDatosDeInventario, TestCase):
    """El cultivo «Lechuga» con tres variedades (una dada de baja) y un cultivo ajeno con una."""

    def setUp(self):
        self.ana = crear_agronomo("ana@infoponia.com", nombre="Ana", apellido="Pérez")
        self.beto = crear_agronomo("beto@infoponia.com", nombre="Beto", apellido="Gómez")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.beto)
        self.lechuga = crear_cultivo("Lechuga")
        self.crespa = variedad_con_semilla(self.lechuga, "Crespa")
        self.lisa = variedad_con_semilla(self.lechuga, "Lisa")
        self.roja = variedad_con_semilla(self.lechuga, "Roja", activa=False)
        self.acelga = crear_cultivo("Acelga")
        self.verde = variedad_con_semilla(self.acelga, "Verde")

    def nombre_de_la_semilla(self, variedad):
        return Insumo.objects.get(pk=variedad.semilla.pk).nombre_insumo

    def renombrar_cultivo_en_la_base(self, nombre="Lechuga común"):
        """Simula lo que hace ``modificar_cultivo`` antes de llamar al registrante: el cultivo ya tiene su nombre nuevo."""
        anterior = self.lechuga.nombre_cultivo
        self.lechuga.nombre_cultivo = nombre
        self.lechuga.save()
        return anterior


class ContarSemillasTests(BaseDeRegistrantes):
    """``contar_semillas_del_cultivo``: lo que el renombre informa antes de confirmar (regla 3 de PROD-MOD-CLT)."""

    def test_regla_3_cuenta_las_semillas_de_todas_las_variedades_activas_o_inactivas(self):
        """PROD-MOD-CLT regla 3: «antes de confirmar, el Sistema informa cuántas semillas cambian de nombre»: las de las tres variedades."""
        self.assertEqual(semillas.contar_semillas_del_cultivo(self.lechuga), 3)
        self.assertEqual(semillas.contar_semillas_del_cultivo(self.acelga), 1)

    def test_regla_3_un_cultivo_sin_variedades_no_cambia_ninguna(self):
        """Prueba mínima del registrante (sin datos): el neutro es 0."""
        self.assertEqual(semillas.contar_semillas_del_cultivo(crear_cultivo("Rúcula")), 0)

    def test_regla_3_no_hace_una_consulta_por_variedad(self):
        """Prueba mínima del registrante: una sola consulta."""
        with self.assertNumQueries(1):
            semillas.contar_semillas_del_cultivo(self.lechuga)

    def test_api_el_registrante_de_maestros_cuenta_lo_mismo(self):
        """docs/api/extensiones_de_maestros.md: ``contar_semillas_a_renombrar`` suma lo que informa `inventario`."""
        self.assertEqual(extensiones.contar_semillas_a_renombrar(self.lechuga), 3)


class RenombrarSemillasTests(BaseDeRegistrantes):
    """``renombrar_semillas_del_cultivo``: postcondiciones a y d de PROD-MOD-CLT."""

    def renombrar(self, nombre="Lechuga común"):
        anterior = self.renombrar_cultivo_en_la_base(nombre)
        return semillas.renombrar_semillas_del_cultivo(self.ana, self.lechuga, anterior)

    def test_post_a_renombra_la_semilla_de_cada_variedad_activa_o_inactiva_y_devuelve_cuantas(self):
        """PROD-MOD-CLT postcondición a y regla 3: «Semilla {cultivo} {variedad}» con el nombre nuevo, también la de la variedad dada de baja."""
        self.assertEqual(self.renombrar(), 3)
        self.assertEqual(
            [self.nombre_de_la_semilla(v) for v in (self.crespa, self.lisa, self.roja)],
            ["Semilla Lechuga común Crespa", "Semilla Lechuga común Lisa", "Semilla Lechuga común Roja"],
        )

    def test_post_a_no_toca_las_semillas_de_otros_cultivos(self):
        """PROD-MOD-CLT regla 3: solo las de las variedades de ese cultivo."""
        self.renombrar()
        self.assertEqual(self.nombre_de_la_semilla(self.verde), "Semilla Acelga Verde")

    def test_post_a_no_cambia_el_estado_ni_las_existencias_de_las_semillas(self):
        """docs/api/variedades.md: ninguna función de semillas toca existencias ni el estado."""
        iin = existencia(self.crespa.semilla, self.norte)
        self.renombrar()
        iin.refresh_from_db()
        self.assertEqual((iin.estado_insumo_invernadero, Insumo.objects.get(pk=self.roja.semilla.pk).estado_insumo), ("activo", "inactivo"))

    def test_post_a_el_nombre_de_la_semilla_nunca_pasa_de_100_caracteres(self):
        """D-49: cultivo de hasta 40 y variedad de hasta 50: la semilla llega a 99 y entra en los 100 del insumo."""
        largo = crear_cultivo("C" * 40)
        variedad = variedad_con_semilla(largo, "V" * 50)
        largo.nombre_cultivo = "D" * 40
        largo.save()
        semillas.renombrar_semillas_del_cultivo(self.ana, largo, "C" * 40)
        self.assertEqual(len(self.nombre_de_la_semilla(variedad)), 99)

    def test_post_d_un_registro_modificacion_semilla_por_semilla_renombrada(self):
        """PROD-MOD-CLT postcondición d y D-36: un log por cada semilla que cambió de nombre, con la semilla, su variedad y el cultivo
        como afectados y el nombre antes y después; el usuario es quien renombró."""
        self.renombrar()
        registros = RegistroAuditoria.objects.filter(accion="modificacion_semilla").order_by("id")
        self.assertEqual(registros.count(), 3)
        for variedad in (self.crespa, self.lisa, self.roja):
            registro = next(r for r in registros if any(a["modelo"] == "maestros.variedad" and a["id"] == variedad.pk for a in r.afectados))
            self.assertEqual(registro.usuario_id, self.ana.pk)
            self.assertEqual(
                {(a["modelo"], a["id"]) for a in registro.afectados},
                {("inventario.semilla", variedad.semilla.pk), ("maestros.variedad", variedad.pk), ("maestros.cultivo", self.lechuga.pk)},
            )
            self.assertEqual(
                registro.detalle["cambios"],
                {"nombre": {"antes": f"Semilla Lechuga {variedad.nombre_variedad}", "despues": f"Semilla Lechuga común {variedad.nombre_variedad}"}},
            )

    def test_post_d_una_semilla_que_ya_tiene_el_nombre_no_cuenta_ni_se_audita(self):
        """D-28: lo que no cambia no se escribe ni se audita."""
        self.assertEqual(self.renombrar("Lechuga"), 0)  # el cultivo conserva el nombre
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_semilla").exists())

    def test_un_cultivo_sin_variedades_no_renombra_nada(self):
        """Prueba mínima del registrante (sin datos): 0 y ningún registro."""
        vacio = crear_cultivo("Rúcula")
        vacio.nombre_cultivo = "Rúcula común"
        vacio.save()
        self.assertEqual(semillas.renombrar_semillas_del_cultivo(self.ana, vacio, "Rúcula"), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_semilla").exists())

    def test_bloquea_los_insumos_de_una_vez_y_en_orden_de_id_antes_de_escribir(self):
        """Orden de bloqueo (docs/patrones/stock.md, sección 5): las filas de ``Insumo`` de las semillas, en una sola sentencia con
        ``ORDER BY id``, y antes del primer ``UPDATE`` (el cultivo y las variedades ya los bloqueó ``modificar_cultivo``)."""
        anterior = self.renombrar_cultivo_en_la_base()
        with CaptureQueriesContext(connection) as consultas:
            semillas.renombrar_semillas_del_cultivo(self.ana, self.lechuga, anterior)
        sentencias = [q["sql"] for q in consultas]
        bloqueos = [s for s in sentencias if "FOR NO KEY UPDATE" in s and 'FROM "inventario_insumo"' in s]
        self.assertEqual(len(bloqueos), 1)
        self.assertRegex(bloqueos[0], r'ORDER BY "inventario_insumo"\."id"')
        primer_update = next(i for i, s in enumerate(sentencias) if s.startswith('UPDATE "inventario_insumo"'))
        self.assertLess(sentencias.index(bloqueos[0]), primer_update)

    def test_decision_un_nombre_que_ya_usa_otro_insumo_es_un_error_del_campo_nombre_y_no_renombra_ninguna(self):
        """Decisión del 22/11/2026: ``semilla_repetida`` en ``nombre``; todo o nada: tampoco las semillas anteriores al choque."""
        insumo("Semilla Lechuga común Lisa", tipo=tipo_de_insumo("Varios"))
        anterior = self.renombrar_cultivo_en_la_base()
        error = error_de(lambda: semillas.renombrar_semillas_del_cultivo(self.ana, self.lechuga, anterior))
        self.assertEqual(codigos_de(error, "nombre"), ["semilla_repetida"])
        self.assertEqual([self.nombre_de_la_semilla(v) for v in (self.crespa, self.lisa, self.roja)], [f"Semilla Lechuga {n}" for n in ("Crespa", "Lisa", "Roja")])
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_semilla").exists())

    def test_decision_si_la_restriccion_unica_salta_a_la_vez_tambien_es_un_error_del_campo_nombre(self):
        """Decisión del 22/11/2026: si otro pedido ocupa el nombre entre la verificación y el guardado, el ``IntegrityError`` de
        ``insumo_nombre_unico`` se traduce a ``semilla_repetida`` en ``nombre`` (nunca un 500) y no queda ninguna renombrada."""
        insumo("Semilla Lechuga común Lisa", tipo=tipo_de_insumo("Varios"))
        anterior = self.renombrar_cultivo_en_la_base()
        with mock.patch.object(semillas, "verificar_nombre"):  # como si la verificación hubiera pasado antes del choque
            error = error_de(lambda: semillas.renombrar_semillas_del_cultivo(self.ana, self.lechuga, anterior))
        self.assertEqual(codigos_de(error, "nombre"), ["semilla_repetida"])
        self.assertEqual(self.nombre_de_la_semilla(self.crespa), "Semilla Lechuga Crespa")
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_semilla").exists())


class UsoDeCultivoTests(BaseDeRegistrantes):
    """``invernaderos_que_usan_el_cultivo``: regla 4 de PROD-MOD-CLT."""

    def test_regla_4_sin_uso_no_hay_invernaderos(self):
        """Prueba mínima del registrante (sin datos): conjunto vacío."""
        self.assertEqual(variedades.invernaderos_que_usan_el_cultivo(self.lechuga), set())

    def test_regla_4_la_semilla_habilitada_de_cualquier_variedad_cuenta(self):
        """PROD-MOD-CLT regla 4: usa el cultivo el invernadero activo con la semilla habilitada de alguna de sus variedades."""
        existencia(self.crespa.semilla, self.norte)
        existencia(self.lisa.semilla, self.sur)
        self.assertEqual(variedades.invernaderos_que_usan_el_cultivo(self.lechuga), {self.norte.pk, self.sur.pk})
        self.assertEqual(variedades.invernaderos_que_usan_el_cultivo(self.acelga), set())

    def test_regla_4_los_lotes_activos_que_informa_produccion_tambien_cuentan(self):
        """PROD-MOD-CLT regla 4: «o lotes activos de ella» (por ``uso_de_variedades``, que registra `produccion`)."""
        uso = UsoDeVariedad(True, 1, 0, frozenset({self.sur.pk}))
        with usos_de_variedad_de_prueba({self.crespa.pk: uso}):
            self.assertEqual(variedades.invernaderos_que_usan_el_cultivo(self.lechuga), {self.sur.pk})

    def test_regla_4_la_semilla_deshabilitada_y_el_invernadero_inactivo_no_cuentan(self):
        """PROD-MOD-CLT regla 4: solo invernaderos ACTIVOS con la semilla habilitada."""
        existencia(self.crespa.semilla, self.norte, activo=False)
        existencia(self.lisa.semilla, crear_invernadero("Invernadero Viejo", activo=False))
        self.assertEqual(variedades.invernaderos_que_usan_el_cultivo(self.lechuga), set())

    def test_regla_4_una_variedad_dada_de_baja_con_su_semilla_aun_habilitada_cuenta(self):
        """docs/modelo/inventario.md, «Semilla»: la baja de la variedad no deshabilita sus existencias, así que el invernadero sigue usándola."""
        existencia(self.roja.semilla, self.norte)
        self.assertEqual(variedades.invernaderos_que_usan_el_cultivo(self.lechuga), {self.norte.pk})

    def test_regla_4_las_consultas_no_crecen_con_la_cantidad_de_variedades(self):
        """Prueba mínima del registrante: una consulta por tabla para toda la lista de variedades, nunca una por variedad."""
        existencia(self.crespa.semilla, self.norte)
        with CaptureQueriesContext(connection) as pocas:
            variedades.invernaderos_que_usan_el_cultivo(self.acelga)
        for n in range(4):
            existencia(variedad_con_semilla(self.acelga, f"V{n}").semilla, self.norte)
        with CaptureQueriesContext(connection) as muchas:
            variedades.invernaderos_que_usan_el_cultivo(self.acelga)
        self.assertEqual(len(muchas), len(pocas))

    def test_api_el_registrante_de_maestros_devuelve_lo_mismo(self):
        """docs/api/extensiones_de_maestros.md: ``invernaderos_que_usan_el_cultivo`` junta lo que informa `inventario`."""
        existencia(self.crespa.semilla, self.norte)
        self.assertEqual(extensiones.invernaderos_que_usan_el_cultivo(self.lechuga), {self.norte.pk})


class RegistroEnReadyTests(TestCase):
    """``InventarioConfig.ready()`` registra los puntos de `maestros` una sola vez, aunque ``ready()`` corra más de una vez."""

    def test_los_registrantes_estan_registrados_una_sola_vez(self):
        """docs/api/extensiones_de_inventario.md: ``registrar_semillas_de_cultivo(contar, renombrar)`` y ``registrar_uso_de_cultivo``."""
        self.assertEqual(sum(1 for contar, _ in extensiones._SEMILLAS if contar is semillas.contar_semillas_del_cultivo), 1)
        self.assertEqual(extensiones._USOS_DE_CULTIVO.count(variedades.invernaderos_que_usan_el_cultivo), 1)

    def test_ready_es_idempotente(self):
        """Paso 7: ``ready()`` puede correr más de una vez sin duplicar registrantes."""
        apps.get_app_config("inventario").ready()
        apps.get_app_config("inventario").ready()
        self.assertEqual(sum(1 for contar, _ in extensiones._SEMILLAS if contar is semillas.contar_semillas_del_cultivo), 1)
        self.assertEqual(extensiones._USOS_DE_CULTIVO.count(variedades.invernaderos_que_usan_el_cultivo), 1)


class ModificarCultivoDePuntaAPuntaTests(BaseDeRegistrantes):
    """``modificar_cultivo`` de MAE-03 con los registrantes reales de `inventario` (PROD-MOD-CLT, reglas 3 y 4 y postcondiciones a, b y d)."""

    def renombrar(self, nombre="Lechuga común", actor=None):
        return cultivos.modificar_cultivo(actor or self.ana, self.lechuga.pk, nombre=nombre)

    def test_post_a_el_renombre_del_cultivo_renombra_las_semillas_de_sus_variedades(self):
        """PROD-MOD-CLT postcondición a: el cultivo y la semilla de cada una de sus variedades quedan con el nombre nuevo."""
        self.renombrar()
        self.assertEqual(
            [self.nombre_de_la_semilla(v) for v in (self.crespa, self.lisa, self.roja, self.verde)],
            ["Semilla Lechuga común Crespa", "Semilla Lechuga común Lisa", "Semilla Lechuga común Roja", "Semilla Acelga Verde"],
        )

    def test_post_d_un_registro_del_cultivo_y_uno_por_semilla(self):
        """PROD-MOD-CLT postcondición d: un log del cultivo (con la cantidad de semillas renombradas) y otro por cada semilla."""
        self.renombrar()
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_cultivo").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_semilla").count(), 3)
        self.assertEqual(RegistroAuditoria.objects.get(accion="modificacion_cultivo").detalle["datos"], {"semillas_renombradas": 3})

    def test_regla_3_el_aviso_dice_cuantas_semillas_cambian_antes_de_confirmar(self):
        """PROD-MOD-CLT regla 3: ``aviso_de_renombre`` informa cuántas semillas cambian de nombre."""
        self.assertEqual(cultivos.aviso_de_renombre(self.ana, self.lechuga.pk).cantidad_de_semillas, 3)

    def test_post_b_avisa_al_agronomo_de_cada_invernadero_que_usa_el_cultivo_menos_al_actor(self):
        """PROD-MOD-CLT postcondición b y regla 4: Beto (Sur) la usa y recibe el aviso; Ana, que renombra, no."""
        existencia(self.crespa.semilla, self.norte)
        existencia(self.lisa.semilla, self.sur)
        self.renombrar()
        avisos = list(Notificacion.objects.all())
        self.assertEqual([(a.destinatario_id, a.titulo) for a in avisos], [(self.beto.pk, "Cambió el cultivo Lechuga")])
        self.assertEqual([i.nombre_invernadero for i in cultivos.aviso_de_renombre(self.ana, self.lechuga.pk).invernaderos], ["Invernadero Sur"])

    def test_decision_un_nombre_de_semilla_que_choca_rechaza_todo_el_renombre(self):
        """Decisión del 22/11/2026: si la semilla de una variedad chocaría con otro insumo, error en ``nombre`` y NO cambia nada: ni el
        cultivo ni las semillas, ni queda registro ni aviso (todo en la transacción de ``modificar_cultivo``)."""
        insumo("Semilla Lechuga común Lisa", tipo=tipo_de_insumo("Varios"))
        existencia(self.crespa.semilla, self.sur)
        error = error_de(lambda: self.renombrar())
        self.assertEqual(codigos_de(error, "nombre"), ["semilla_repetida"])
        self.lechuga.refresh_from_db()
        self.assertEqual(self.lechuga.nombre_cultivo, "Lechuga")
        self.assertEqual(self.nombre_de_la_semilla(self.crespa), "Semilla Lechuga Crespa")
        self.assertFalse(RegistroAuditoria.objects.filter(accion__in=["modificacion_cultivo", "modificacion_semilla"]).exists())
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_regla_3_un_cultivo_sin_variedades_se_renombra_sin_semillas(self):
        """PROD-MOD-CLT: sin variedades no hay semillas que renombrar ni logs de semilla; el log del cultivo no lleva ``datos``."""
        vacio = crear_cultivo("Rúcula")
        cultivos.modificar_cultivo(self.ana, vacio.pk, nombre="Rúcula común")
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_semilla").exists())
        self.assertNotIn("datos", RegistroAuditoria.objects.get(accion="modificacion_cultivo").detalle)
