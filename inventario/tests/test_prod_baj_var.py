# Pruebas de PROD-BAJ-VAR · Baja Variedad (INV-03, paso 6): `baja_variedad(actor, variedad_id)` e `informe_de_baja(variedad)`.
# Fuente: docs/casos_de_uso/inventario/variedades.md (precondiciones a a f, postcondiciones a a c, reglas 1 a 4 y «Decisiones de aplicación»,
# «Baja» y «Bloqueos»), docs/patrones/stock.md (secciones 4 y 5), docs/modelo/inventario.md («Semilla», «Diferencias» n.º 6) y D-36.
# Lotes, órdenes y contratos se simulan con registrantes falsos (`usos_de_variedad_de_prueba`): `produccion` y `comercial` no existen. La
# precondición f (contratos) NO se verifica con registrantes reales hasta que `comercial` registre `contratos_abiertos` (temas_abiertos.md).
#
# Contrato que fijan estas pruebas:
#   - ``baja_variedad`` devuelve la variedad. Las precondiciones b a f se evalúan DESPUÉS de bloquear y se informan TODAS juntas (regla 2):
#     un solo ``ValidationError`` general con un error por impedimento. Códigos: ``variedad_en_uso_por_otros`` (b), ``variedad_inactiva``
#     (c) y los de los registrantes (``lotes_activos``, ``ordenes_a_realizar``, ``contratos_abiertos``), cada uno con su texto y cómo resolverlo.
#   - Deja inactivas la variedad y su semilla SIN tocar las existencias (ni sus lotes ni sus movimientos) y reevalúa las alertas de CADA
#     existencia activa de la semilla llamando a ``alertas_de_stock.reevaluar_alertas_del_insumo``.
#   - Orden de bloqueo: invernaderos donde la semilla está habilitada (leídos sin bloquear, bloqueados con ``ORDER BY id`` y vueltos a leer)
#     -> cultivo -> variedad -> insumo. Si al releer aparece un invernadero que no se bloqueó, ``cambio_simultaneo`` (nunca se reintenta).
#   - ``informe_de_baja(variedad)`` (solo lectura, no bloquea) devuelve ``InformeDeBaja(impedimentos, habilitada_en, stock)``: los impedimentos
#     de los registrantes, los nombres de los invernaderos donde la semilla está habilitada y ``StockDeSemilla(invernadero, cantidad)``
#     por cada invernadero con stock.

import re
from decimal import Decimal
from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.models import Insumo, LoteInsumo, MovimientoInsumo
from inventario.servicios import alertas_de_stock
from inventario.tests.ajustes_comunes import ROTURA, BaseDeAjustes
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    lote,
    perezoso,
    usos_de_variedad_de_prueba,
    variedad_con_semilla,
)
from maestros.extensiones import Impedimento
from maestros.models import Alerta, Ciclo, EtapaProductiva, Variedad
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_cultivo, crear_invernadero, error_de
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

variedades = perezoso("inventario.servicios.variedades")
iin_servicio = perezoso("inventario.servicios.insumos_invernadero")
ajustes = perezoso("inventario.servicios.ajustes")
D = Decimal
BAJO_MINIMO = "inv_insumo_bajo_minimo"

LOTES = Impedimento("lotes_activos", "Tiene 2 lotes activos.", "Terminalos con su cosecha o su merma.")
ORDENES = Impedimento("ordenes_a_realizar", "Tiene 1 orden a realizar.", "Concretala o cancelala.")
CONTRATOS = Impedimento("contratos_abiertos", "Tiene 1 contrato abierto.", "Cumplilo o cerralo.")


class BajVarBase(ConDatosDeInventario, TestCase):
    """«Lechuga Crespa» y dos Agrónomos: Ana con Norte y Este, Beto con Sur."""

    def setUp(self):
        self.ana = crear_agronomo("ana@infoponia.com", nombre="Ana", apellido="Pérez")
        self.beto = crear_agronomo("beto@infoponia.com", nombre="Beto", apellido="Gómez")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        self.este = crear_invernadero("Invernadero Este", agronomo=self.ana)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.beto)
        self.cultivo = crear_cultivo("Lechuga")
        self.variedad = variedad_con_semilla(self.cultivo, "Crespa")

    def baja(self, actor=None, variedad=None):
        return variedades.baja_variedad(actor or self.ana, (variedad or self.variedad).pk)

    def variedad_hoy(self):
        return Variedad.objects.get(pk=self.variedad.pk)

    def semilla_hoy(self):
        return Insumo.objects.get(pk=self.variedad.semilla.pk)

    def registros(self):
        return RegistroAuditoria.objects.filter(accion="baja_variedad")


class PreCondicionesTests(BajVarBase):
    """Precondiciones a a f y regla 2 (todo lo que lo impide, junto)."""

    def test_pre_a_solo_un_agronomo_activo_da_de_baja(self):
        """PROD-BAJ-VAR precondición a."""
        with self.assertRaises(PermissionDenied):
            self.baja(crear_gerente())
        with self.assertRaises(PermissionDenied):
            self.baja(crear_agronomo("inactivo@infoponia.com", activo=False))

    def test_pre_a_una_variedad_inexistente_da_404(self):
        """Una variedad que no existe es 404."""
        with self.assertRaises(Http404):
            variedades.baja_variedad(self.ana, 999999)

    def test_pre_b_sin_gestora_no_se_da_de_baja_y_dice_quienes_la_usan(self):
        """PROD-BAJ-VAR precondición b y regla 1 de PROD-MOD-VAR: solo la usa Norte (Ana); Beto no puede, y se le dice quiénes la usan."""
        existencia(self.variedad.semilla, self.norte)
        error = error_de(lambda: self.baja(self.beto))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["variedad_en_uso_por_otros"])
        self.assertIn("Invernadero Norte (Ana Pérez)", error.error_dict[NON_FIELD_ERRORS][0].message)
        self.assertEqual(self.variedad_hoy().estado_variedad, "activo")
        self.assertFalse(self.registros().exists())

    def test_pre_b_el_agronomo_de_un_invernadero_que_la_usa_si_puede(self):
        """PROD-MOD-VAR regla 1: el Agrónomo de un invernadero que la use la da de baja (y también si nadie la usa)."""
        existencia(self.variedad.semilla, self.norte)
        self.assertEqual(self.baja(self.ana).estado_variedad, "inactivo")
        self.assertEqual(self.baja(self.beto, variedad_con_semilla(self.cultivo, "Lisa")).estado_variedad, "inactivo")

    def test_pre_c_una_variedad_inactiva_no_se_da_de_baja_de_nuevo(self):
        """PROD-BAJ-VAR precondición c: la variedad está activa."""
        inactiva = variedad_con_semilla(self.cultivo, "Vieja", activa=False)
        error = error_de(lambda: self.baja(variedad=inactiva))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["variedad_inactiva"])
        self.assertFalse(self.registros().exists())

    def test_pre_d_lotes_activos_impiden_la_baja(self):
        """PROD-BAJ-VAR precondición d: sin lotes activos (los informa `produccion`, ``lotes_activos``)."""
        with usos_de_variedad_de_prueba(impedimentos={self.variedad.pk: [LOTES]}):
            error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["lotes_activos"])
        self.assertEqual(self.variedad_hoy().estado_variedad, "activo")
        self.assertEqual(self.semilla_hoy().estado_insumo, "activo")

    def test_pre_e_ordenes_a_realizar_impiden_la_baja(self):
        """PROD-BAJ-VAR precondición e: sin órdenes de trabajo a realizar (``ordenes_a_realizar``)."""
        with usos_de_variedad_de_prueba(impedimentos={self.variedad.pk: [ORDENES]}):
            self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["ordenes_a_realizar"])

    def test_pre_f_contratos_abiertos_impiden_la_baja(self):
        """PROD-BAJ-VAR precondición f: ningún contrato vigente o abierto con un detalle de la variedad (``contratos_abiertos``; lo
        registra `comercial`: hasta entonces no se verifica)."""
        with usos_de_variedad_de_prueba(impedimentos={self.variedad.pk: [CONTRATOS]}):
            self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["contratos_abiertos"])

    def test_pre_f_sin_registrantes_nada_impide_la_baja(self):
        """docs/casos_de_uso/inventario/variedades.md, «Cómo se aplica»: sin `produccion` ni `comercial` no hay impedimentos."""
        self.assertEqual(self.baja().estado_variedad, "inactivo")

    def test_regla_2_los_impedimentos_salen_todos_juntos_con_su_texto_y_como_resolverlos(self):
        """PROD-BAJ-VAR regla 2: «informa todo lo que lo impide, cada cosa con cómo resolverla»; no se queda con el primero."""
        with usos_de_variedad_de_prueba(impedimentos={self.variedad.pk: [LOTES, ORDENES, CONTRATOS]}):
            error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["lotes_activos", "ordenes_a_realizar", "contratos_abiertos"])
        mensajes = [e.message for e in error.error_dict[NON_FIELD_ERRORS]]
        for impedimento, mensaje in zip((LOTES, ORDENES, CONTRATOS), mensajes):
            self.assertIn(impedimento.texto, mensaje)
            self.assertIn(impedimento.como_resolver, mensaje)

    def test_regla_2_sin_gestora_ya_inactiva_y_con_lotes_salen_las_tres_cosas(self):
        """PROD-BAJ-VAR regla 2: las precondiciones b, c y d se evalúan juntas, en ese orden."""
        inactiva = variedad_con_semilla(self.cultivo, "Vieja", activa=False)
        existencia(inactiva.semilla, self.norte)  # la semilla inactiva conserva su existencia activa: Norte la usa
        with usos_de_variedad_de_prueba(impedimentos={inactiva.pk: [LOTES]}):
            error = error_de(lambda: self.baja(self.beto, inactiva))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["variedad_en_uso_por_otros", "variedad_inactiva", "lotes_activos"])


class PostcondicionesTests(BajVarBase):
    """Postcondiciones a, b y c y regla 1 (baja lógica) y 3 (el stock queda)."""

    def test_post_a_la_variedad_queda_inactiva_y_conserva_su_ciclo_y_etapas(self):
        """PROD-BAJ-VAR postcondición a y regla 1: baja lógica; conserva su ciclo, sus etapas y todo su historial."""
        devuelta = self.baja()
        self.assertEqual((devuelta.pk, self.variedad_hoy().estado_variedad), (self.variedad.pk, "inactivo"))
        self.assertEqual((Ciclo.objects.filter(variedad=self.variedad).count(), EtapaProductiva.objects.filter(ciclo__variedad=self.variedad).count()), (1, 2))

    def test_post_b_la_semilla_queda_inactiva(self):
        """PROD-BAJ-VAR postcondición b: su semilla quedó inactiva y dejó de ofrecerse para pedirse."""
        self.baja()
        self.assertEqual(self.semilla_hoy().estado_insumo, "inactivo")

    def test_regla_3_las_existencias_siguen_activas_con_su_stock_y_sin_movimientos_nuevos(self):
        """PROD-BAJ-VAR regla 3 y docs/modelo/inventario.md, «Diferencias» n.º 6: la semilla no deshabilita sus existencias; el stock queda
        registrado, sin lotes ni movimientos nuevos; una existencia ya deshabilitada sigue deshabilitada."""
        con_stock = existencia(self.variedad.semilla, self.norte)
        un_lote = lote(con_stock, 12)
        deshabilitada = existencia(self.variedad.semilla, self.sur, activo=False)
        antes = (LoteInsumo.objects.count(), MovimientoInsumo.objects.count())
        self.baja()
        con_stock.refresh_from_db()
        deshabilitada.refresh_from_db()
        self.assertEqual((con_stock.estado_insumo_invernadero, deshabilitada.estado_insumo_invernadero), ("activo", "inactivo"))
        self.assertEqual((LoteInsumo.objects.count(), MovimientoInsumo.objects.count()), antes)
        un_lote.refresh_from_db()
        self.assertEqual(un_lote.cantidad_disponible, D("12"))

    def test_regla_3_una_semilla_habilitada_en_otros_invernaderos_y_con_stock_no_bloquea_la_baja(self):
        """PROD-BAJ-VAR regla 3: lo informa pero NO bloquea (ni la habilitación en otros invernaderos ni el stock que queda)."""
        lote(existencia(self.variedad.semilla, self.norte), 5)
        existencia(self.variedad.semilla, self.este)
        self.assertEqual(self.baja().estado_variedad, "inactivo")

    def test_post_c_un_solo_registro_baja_variedad_con_variedad_y_semilla_y_el_cambio_de_estado(self):
        """PROD-BAJ-VAR postcondición c y D-36: usuario, la variedad y su semilla como afectados y el estado de activo a inactivo."""
        self.baja()
        registro = self.registros().get()
        self.assertEqual(registro.usuario_id, self.ana.pk)
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "activo", "despues": "inactivo"}})
        self.assertEqual(
            {(a["modelo"], a["id"]) for a in registro.afectados},
            {("maestros.variedad", self.variedad.pk), ("inventario.semilla", self.variedad.semilla.pk)},
        )

    def test_post_c_un_error_no_deja_registro_ni_cambia_nada(self):
        """D-22: no queda un registro de una baja que no se hizo."""
        with usos_de_variedad_de_prueba(impedimentos={self.variedad.pk: [LOTES]}):
            error_de(self.baja)
        self.assertFalse(self.registros().exists())

    def test_post_c_si_falla_la_auditoria_no_queda_inactiva_ni_la_variedad_ni_la_semilla(self):
        """D-22: todo en una transacción."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla simulada")):
            with self.assertRaises(RuntimeError):
                self.baja()
        self.assertEqual((self.variedad_hoy().estado_variedad, self.semilla_hoy().estado_insumo), ("activo", "activo"))


class AlertasTests(BajVarBase):
    """La baja reevalúa las alertas de cada existencia de la semilla (docs/patrones/stock.md, sección 4)."""

    def existencia_bajo_el_minimo(self, invernadero):
        iin = existencia(self.variedad.semilla, invernadero, minimo=10)
        lote(iin, 2)
        alertas_de_stock.reevaluar_alertas_del_insumo(iin.pk)
        return iin

    def activas(self, iin):
        return Alerta.objects.filter(tipo_alerta=BAJO_MINIMO, clave_estado=f"insumo:{iin.pk}", estado_alerta=Alerta.Estado.ACTIVA)

    def test_post_b_la_alerta_bajo_el_minimo_se_resuelve_porque_el_insumo_queda_inactivo(self):
        """docs/patrones/stock.md, sección 4: «bajo el mínimo» se resuelve si el insumo del catálogo está inactivo (la semilla dada de baja)."""
        iin = self.existencia_bajo_el_minimo(self.norte)
        self.assertEqual(self.activas(iin).count(), 1)
        self.baja()
        self.assertEqual(self.activas(iin).count(), 0)
        self.assertEqual(Alerta.objects.filter(tipo_alerta=BAJO_MINIMO, estado_alerta=Alerta.Estado.RESUELTA).count(), 1)

    def test_post_c_las_alertas_resueltas_van_en_los_datos_de_la_auditoria(self):
        """docs/api/alertas.md, «Auditoría»: ``alertas_resueltas`` en los ``datos`` del registro, como referencias."""
        self.existencia_bajo_el_minimo(self.norte)
        self.baja()
        resueltas = self.registros().get().detalle["datos"]["alertas_resueltas"]
        self.assertEqual(len(resueltas), 1)

    def test_post_c_sin_alertas_no_hay_datos(self):
        """D-36: ``datos`` solo si hay algo que contar."""
        existencia(self.variedad.semilla, self.norte)
        self.baja()
        self.assertNotIn("datos", self.registros().get().detalle)

    def test_regla_3_se_reevalua_cada_existencia_activa_y_solo_esas(self):
        """Paso 6: ``reevaluar_alertas_del_insumo`` por cada existencia ACTIVA de la semilla (una llamada cada una); la deshabilitada no."""
        a, b = existencia(self.variedad.semilla, self.norte), existencia(self.variedad.semilla, self.sur)
        existencia(self.variedad.semilla, self.este, activo=False)
        with mock.patch.object(alertas_de_stock, "reevaluar_alertas_del_insumo", wraps=alertas_de_stock.reevaluar_alertas_del_insumo) as llamada:
            self.baja(self.ana)  # Ana: Norte la usa; Sur también
        self.assertEqual(sorted(c.args[0] for c in llamada.call_args_list), sorted([a.pk, b.pk]))


class InformeDeBajaTests(BajVarBase):
    """``informe_de_baja(variedad)``: qué impide la baja, dónde está habilitada la semilla y cuánto stock queda (regla 3), sin bloquear."""

    def test_regla_2_trae_los_impedimentos_de_los_registrantes(self):
        """PROD-BAJ-VAR regla 2: lo que impide la baja, con cómo resolverlo."""
        with usos_de_variedad_de_prueba(impedimentos={self.variedad.pk: [LOTES, CONTRATOS]}):
            self.assertEqual(variedades.informe_de_baja(self.variedad).impedimentos, [LOTES, CONTRATOS])

    def test_regla_3_dice_donde_esta_habilitada_la_semilla_y_cuanto_stock_queda_por_invernadero(self):
        """PROD-BAJ-VAR regla 3: «si la semilla está habilitada en otros invernaderos, lo informa; si queda stock, cuánto y en qué invernaderos»."""
        lote(existencia(self.variedad.semilla, self.norte), 12)
        existencia(self.variedad.semilla, self.sur)  # habilitada, sin stock
        existencia(self.variedad.semilla, self.este, activo=False)  # deshabilitada: no cuenta
        informe = variedades.informe_de_baja(self.variedad)
        self.assertEqual(informe.habilitada_en, ["Invernadero Norte", "Invernadero Sur"])
        self.assertEqual(informe.stock, [variedades.StockDeSemilla("Invernadero Norte", D("12"))])

    def test_regla_3_sin_existencias_no_hay_nada_que_informar(self):
        """La semilla sin habilitar en ningún invernadero: sin habilitaciones ni stock ni impedimentos."""
        informe = variedades.informe_de_baja(self.variedad)
        self.assertEqual((informe.impedimentos, informe.habilitada_en, informe.stock), ([], [], []))

    def test_regla_3_el_informe_no_bloquea_ni_escribe(self):
        """Paso 6: ``informe_de_baja`` no bloquea (ningún ``FOR NO KEY UPDATE``) ni cambia nada."""
        lote(existencia(self.variedad.semilla, self.norte), 3)
        with CaptureQueriesContext(connection) as consultas:
            variedades.informe_de_baja(self.variedad)
        self.assertFalse([q for q in consultas if "FOR NO KEY UPDATE" in q["sql"] or "FOR UPDATE" in q["sql"]])
        self.assertEqual(self.variedad_hoy().estado_variedad, "activo")


class OrdenDeBloqueoTests(BajVarBase):
    """Orden de bloqueo (docs/patrones/stock.md, sección 5): invernaderos (por id, leídos antes sin bloquear y releídos) -> cultivo ->
    variedad -> insumo. Se verifica sobre las sentencias SQL de la baja."""

    def tabla(self, sql):
        return re.search(r'FROM "(\w+)"', sql).group(1)

    def baja_con_consultas(self):
        existencia(self.variedad.semilla, self.este)
        existencia(self.variedad.semilla, self.norte)
        with CaptureQueriesContext(connection) as consultas:
            self.baja()
        return [q["sql"] for q in consultas]

    def test_orden_invernaderos_cultivo_variedad_insumo(self):
        """El primer bloqueo de cada tabla va en el orden invernadero -> cultivo -> variedad -> insumo."""
        bloqueos = [self.tabla(sql) for sql in self.baja_con_consultas() if "FOR NO KEY UPDATE" in sql]
        orden = ["maestros_invernadero", "maestros_cultivo", "maestros_variedad", "inventario_insumo"]
        primeras = [bloqueos.index(tabla) for tabla in orden]
        self.assertEqual(primeras, sorted(primeras))
        self.assertEqual(len(set(primeras)), 4)

    def test_los_invernaderos_se_bloquean_juntos_y_en_orden_de_id(self):
        """Los invernaderos de la semilla se bloquean en una sola sentencia, con ``ORDER BY id`` (dos bajas a la vez no se cruzan)."""
        sentencias = [s for s in self.baja_con_consultas() if "FOR NO KEY UPDATE" in s and self.tabla(s) == "maestros_invernadero"]
        self.assertRegex(sentencias[0], r'ORDER BY "maestros_invernadero"\."id"')

    def test_las_existencias_se_leen_sin_bloquear_antes_y_se_vuelven_a_leer_despues_de_bloquear(self):
        """«Se leen sin bloquear, se bloquean en orden de id y se vuelve a leer»: al menos dos lecturas de las existencias, ninguna bloqueada
        (la baja no las cambia), la segunda después del bloqueo del insumo."""
        sentencias = self.baja_con_consultas()
        lecturas = [i for i, s in enumerate(sentencias) if s.startswith("SELECT") and self.tabla(s) == "inventario_insumoinvernadero"]
        self.assertGreaterEqual(len(lecturas), 2)
        self.assertFalse([s for s in sentencias if "FOR NO KEY UPDATE" in s and self.tabla(s) == "inventario_insumoinvernadero"])
        bloqueo_del_insumo = next(i for i, s in enumerate(sentencias) if "FOR NO KEY UPDATE" in s and self.tabla(s) == "inventario_insumo")
        self.assertTrue(lecturas[0] < bloqueo_del_insumo < lecturas[-1])


class SemillaAjustableTrasLaBajaTests(BaseDeAjustes, TestCase):
    """CMP-AJT-STK con la semilla de una variedad dada de baja (ajuste_de_stock.md, «Semilla de una variedad dada de baja»; docs/modelo/
    inventario.md, «Diferencias» n.º 6): el stock que queda se descarta con un ajuste porque la existencia sigue activa."""

    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        self.preparar()
        self.variedad = variedad_con_semilla(crear_cultivo("Lechuga"), "Crespa")
        self.iin_semilla = existencia(self.variedad.semilla, self.invernadero, minimo=5, precio="3")
        self.stock = lote(self.iin_semilla, 20, vence=self.vence)
        variedades.baja_variedad(self.agronomo, self.variedad.pk)

    def test_la_semilla_dada_de_baja_conserva_su_existencia_activa_y_se_ofrece_para_ajustar(self):
        """Paso 4 de CMP-AJT-STK: se ofrecen las existencias activas aunque el insumo del catálogo esté inactivo."""
        self.assertEqual(Insumo.objects.get(pk=self.variedad.semilla.pk).estado_insumo, "inactivo")
        self.assertIn(self.iin_semilla.pk, [i.pk for i in iin_servicio.habilitados(self.invernadero.pk)])
        situacion = ajustes.situacion_del_insumo(self.agronomo, self.invernadero.pk, self.variedad.semilla.pk)
        self.assertEqual((situacion.stock_actual, situacion.iin.pk), (D("20"), self.iin_semilla.pk))

    def test_regla_3_el_stock_que_queda_se_descarta_con_un_ajuste_de_rotura(self):
        """PROD-BAJ-VAR regla 3: «si se descarta, se registra con un ajuste de stock»: lo lleva a cero con sus invariantes."""
        resultado = self.confirmar(ROTURA, {"lote_id": self.stock.pk, "cantidad": "20", "descripcion": "Descarte por baja"}, iin=self.iin_semilla)
        self.assertEqual((resultado.stock_actual, self.disponible(self.stock)), (D("0"), D("0")))
        self.invariantes(self.iin_semilla)
        self.iin_semilla.refresh_from_db()
        self.assertEqual(self.iin_semilla.estado_insumo_invernadero, "activo")
