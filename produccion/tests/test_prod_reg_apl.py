# Pruebas de PROD-REG-APL · Registrar Aplicación de Insumos (PRD-03, paso 4; docs/casos_de_uso/produccion/aplicacion_de_insumos.md, «Cómo se aplica en
# la ronda «Producción 1»»). Se escriben ANTES que el servicio y deben fallar; el estudiante las revisa antes de implementar.
#
# CONTRATO que fijan estas pruebas (produccion/servicios/aplicaciones.py, nuevo; usa `alcance.py`):
# - sectores_de_aplicacion(actor, invernadero_id) -> [FilaDeSectorAplicable(sector_id, nombre, tipo_etapa)]: los sectores ACTIVOS del invernadero,
#   por tipo de etapa y nombre (paso 4). Los fuera de servicio o inactivos no se ofrecen.
# - insumos_aplicables(actor, invernadero_id) -> [FilaDeInsumoAplicable(existencia_id, insumo_id, nombre, unidad, controla_vencimiento, stock_libre,
#   lotes, precio, destino)]: los habilitados y activos del invernadero con consumo directo (paso 6), por nombre. `stock_libre` es sin lotes vencidos;
#   `lotes` es `[(lote_id, disponible, vencimiento)]` de los vigentes con stock (FEFO). `precio` y `destino` («costo_de_los_lotes» o «gasto») son
#   `None` para el Capataz: el servicio no los devuelve (regla «Qué ve cada rol»). `[]` si no hay ninguno (extensión 6b).
# - DatosDeAplicacion(invernadero_id, alcance="todo" | "sectores", sector_ids=(), lineas=(), descripcion="", plantas_vistas=None) y
#   LineaDeAplicacion(existencia_id, cantidad, reparto=None, lotes_vistos=None). `reparto` es `((lote_insumo_id, cantidad), ...)` y solo vale en un
#   insumo que controla vencimiento (en los demás se ignora y sale FEFO). `lotes_vistos` es `((lote_insumo_id, disponible), ...)` y `plantas_vistas`,
#   `((lote_id, plantas), ...)`: lo que la persona vio, para la extensión 12a (`None` no lo verifica). Una línea con `lotes_vistos` que ya no es
#   aplicable es `cambio_simultaneo` (cambió la habilitación o el estado); sin él, `insumo_no_aplicable`.
# - resumen_de_aplicacion(actor, datos) -> ResumenDeAplicacion(invernadero, sectores, descripcion, lineas, total_a_gasto) (paso 10): valida TODO y no escribe
#   ni bloquea. `lineas` son LineaDeResumen(existencia_id, insumo_id, nombre, unidad, cantidad, partes, faltante, valor, destino, reparto, aviso): `partes`
#   `[(lote_insumo_id, cantidad)]` lo ve todo el mundo; `faltante`, `valor`, `destino`, `reparto` (`[FilaDeReparto(lote_id, codigo, plantas, porcentaje, monto,
#   costo_por_planta_antes, costo_por_planta_despues)]`), `aviso` (extensión 10c) y `total_a_gasto` son `None` si actúa un Capataz.
# - registrar_aplicacion(actor, datos) -> ResultadoDeAplicacion(aplicacion, lineas): lo mismo bajo bloqueos y repitiendo las verificaciones (12a); `lineas`
#   con la misma regla de roles. Escribe todo o nada. UN registro `registro_aplicacion`. (La API decía `-> AplicacionInsumos`: se devuelve más para que el
#   Agrónomo vea montos y reparto en el paso 13.)
#
# Códigos y campos de `ErrorDeProduccion`: sin_permiso; invernadero_inactivo; sin_sectores (6a, campo sector_ids); sector_no_elegible (sector_ids);
# sin_insumos_aplicables (6b); sin_insumos (10a); insumo_no_aplicable y insumo_repetido (campo `insumo_<existencia_id>`); cantidad_invalida (8a, campo
# `cantidad_<existencia_id>`, con los decimales de la unidad); reparto_supera_lote (8c.2a, campo `reparto_<existencia_id>`); distribucion_incompleta (10b,
# mismo campo, con `datos={"debe_sumar": ...}`); descripcion_larga (500); cambio_simultaneo (12a, con `datos={"cambios": [...]}`).
#
# Una prueba por regla y por postcondición a a e y g a i. CON-04a: la postcondición f (un asiento por consumo) se prueba en `RegistrarAsientoTests`;
# las precondiciones c y d (ejercicio y cuentas) no se prueban: se cumplen solas (D-92 punto 2).

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
from contabilidad.tests.fabricas import PlanDeCuentasMixin, verificar_invariantes_contables
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo, TipoInsumo
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote as lote_de_insumo, perezoso, tipo_de_insumo
from maestros.models import Alerta, Invernadero, SectorProduccion
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_invernadero, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.models import AplicacionInsumos, Bitacora, Consumo, ImputacionCosto, Lote, OcupacionSector
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo

alcance = perezoso("produccion.servicios.alcance")
aplicaciones = perezoso("produccion.servicios.aplicaciones")

D = Decimal
HOY = timezone.localdate()
INCONSISTENTE = "inv_stock_inconsistente"


def rechazo(llamada):
    """Ejecuta `llamada()` y devuelve el `ErrorDeProduccion` que lanza; si no lanza ninguno, la prueba falla."""
    try:
        llamada()
    except ErrorDeProduccion as error:
        return error
    raise AssertionError("Se esperaba un ErrorDeProduccion y no se lanzó ninguno.")


def tipo(consumo):
    """La categoría de pruebas de ese consumo directo (se reutiliza)."""
    return TipoInsumo.objects.filter(nombre_tipo_insumo=f"Cat {consumo}").first() or tipo_de_insumo(f"Cat {consumo}", consumo=consumo)


class Base(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        # Dos lotes de plantas: 60 en germinación (costo 100,00) y 40 en crecimiento (costo 50,00).
        cls.a = lote_activo(cls.e, cantidad=60, sector="germinacion", costo="100.00")
        cls.b = lote_activo(cls.e, cantidad=40, sector="crecimiento", costo="50.00")
        # Insumos: limpiador (gasto, 20 L a 5,00), abono (costo de los lotes, 30 kg a 4,00), guantes (gasto, unidades enteras), nutriente (costo de los
        # lotes, con vencimiento y dos lotes: 4 que vencen en 10 días y 10 en 40) y un insumo que no admite consumo directo.
        cls.limpiador = cls.stock("Limpiador", "como_gasto", 20, "l", "5.00")
        cls.abono = cls.stock("Abono", "como_costo_de_los_lotes", 30, "kg", "4.00")
        cls.guantes = cls.stock("Guantes", "como_gasto", 10, "unidad", "2.00")
        cls.nutriente = cls.stock("Nutriente", "como_costo_de_los_lotes", 0, "l", "6.00", controla=True)
        cls.lote_corto = lote_de_insumo(cls.nutriente, 4, vence=HOY + timedelta(days=10))
        cls.lote_largo = lote_de_insumo(cls.nutriente, 10, vence=HOY + timedelta(days=40))
        cls.no_admite = cls.stock("Repuesto", "no_admite", 5, "unidad", "9.00")

    @classmethod
    def stock(cls, nombre, consumo, cantidad, unidad, precio, controla=False):
        habilitado = existencia(insumo(nombre, tipo=tipo(consumo), unidad=unidad, controla_vencimiento=controla), cls.e.invernadero, precio=precio)
        if cantidad:
            lote_de_insumo(habilitado, cantidad, vence=HOY + timedelta(days=365) if controla else None)
        return habilitado

    def linea(self, habilitado, cantidad, **extra):
        return aplicaciones.LineaDeAplicacion(habilitado.pk, cantidad, **extra)

    def datos(self, *lineas, **cambios):
        base = dict(invernadero_id=self.e.invernadero.pk, lineas=tuple(lineas))
        base.update(cambios)
        return aplicaciones.DatosDeAplicacion(**base)

    def resumen(self, *lineas, actor=None, **cambios):
        return aplicaciones.resumen_de_aplicacion(actor or self.e.agronomo, self.datos(*lineas, **cambios))

    def registrar(self, *lineas, actor=None, **cambios):
        return aplicaciones.registrar_aplicacion(actor or self.e.capataz, self.datos(*lineas, **cambios))

    def stock_lote(self, habilitado):
        return LoteInsumo.objects.get(insumo_invernadero=habilitado, es_faltante_sin_lote=False)

    def disponible(self, un_lote):
        return LoteInsumo.objects.get(pk=un_lote.pk).cantidad_disponible

    def nada_se_escribio(self):
        """Todo o nada: ninguna aplicación, consumo, movimiento, imputación ni auditoría, y los lotes de plantas igual."""
        self.assertFalse(AplicacionInsumos.objects.exists())
        self.assertFalse(Consumo.objects.exists())
        self.assertFalse(ImputacionCosto.objects.exists())
        self.assertFalse(MovimientoInsumo.objects.filter(tipo_movimiento="salida_por_consumo", origen__bitacora__isnull=False).exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion="registro_aplicacion").exists())
        self.assertEqual(AsientoContable.objects.count(), 0)  # CON-04a
        self.assertEqual(Lote.objects.get(pk=self.a.pk).costo_acumulado, D("100.00"))
        self.assertEqual(Lote.objects.get(pk=self.b.pk).costo_acumulado, D("50.00"))


class LecturaTests(Base):
    def test_ext_4a_y_paso_4_ofrece_solo_los_sectores_activos_agrupados_por_tipo_de_etapa(self):
        """Paso 4 y regla «Alcance»: los sectores activos del invernadero con su tipo de etapa; un sector fuera de servicio o inactivo no se ofrece."""
        fuera = self.e.sectores["maduracion"]
        SectorProduccion.objects.filter(pk=fuera.pk).update(estado_sector="fuera_de_servicio")
        filas = aplicaciones.sectores_de_aplicacion(self.e.capataz, self.e.invernadero.pk)
        self.assertNotIn(fuera.pk, [f.sector_id for f in filas])
        self.assertIn(self.e.sectores["germinacion"].pk, [f.sector_id for f in filas])
        self.assertTrue(all(f.tipo_etapa and f.nombre for f in filas))

    def test_paso_6_ofrece_los_insumos_habilitados_con_consumo_directo_y_su_stock_libre(self):
        """Paso 6 y regla «Insumos que se ofrecen»: solo los de categorías «como gasto» o «como costo de los lotes», activos y habilitados, con el
        stock libre sin los lotes vencidos. Un insumo que no admite consumo directo no se ofrece."""
        vencido = lote_de_insumo(self.limpiador, 7, vence=HOY - timedelta(days=1))
        filas = {f.nombre: f for f in aplicaciones.insumos_aplicables(self.e.agronomo, self.e.invernadero.pk)}
        self.assertEqual(set(filas), {"Limpiador", "Abono", "Guantes", "Nutriente"})
        self.assertEqual(filas["Limpiador"].stock_libre, D("20"))  # los 7 vencidos no cuentan
        self.assertEqual(filas["Nutriente"].stock_libre, D("14"))
        self.assertEqual([(l[0], l[1]) for l in filas["Nutriente"].lotes], [(self.lote_corto.pk, D("4")), (self.lote_largo.pk, D("10"))])
        self.assertNotIn(vencido.pk, [l[0] for f in filas.values() for l in f.lotes])
        self.assertEqual((filas["Limpiador"].unidad, filas["Nutriente"].controla_vencimiento), ("l", True))

    def test_paso_6_no_ofrece_un_insumo_deshabilitado_ni_el_de_otro_invernadero(self):
        """Regla «Insumos que se ofrecen»: solo activos y habilitados en ESTE invernadero."""
        InsumoInvernadero.objects.filter(pk=self.guantes.pk).update(estado_insumo_invernadero="inactivo")
        otro = crear_invernadero("Otro", agronomo=self.e.agronomo)
        existencia(insumo("Ajeno", tipo=tipo("como_gasto")), otro)
        nombres = {f.nombre for f in aplicaciones.insumos_aplicables(self.e.agronomo, self.e.invernadero.pk)}
        self.assertNotIn("Guantes", nombres)
        self.assertNotIn("Ajeno", nombres)

    def test_regla_que_ve_cada_rol_el_agronomo_ve_precio_y_destino_y_el_capataz_no(self):
        """Regla «Qué ve cada rol»: el Agrónomo ve el destino del costo de cada insumo (y su precio); el Capataz no los recibe: el servicio los
        devuelve vacíos, no solo la plantilla."""
        agro = {f.nombre: f for f in aplicaciones.insumos_aplicables(self.e.agronomo, self.e.invernadero.pk)}
        cap = {f.nombre: f for f in aplicaciones.insumos_aplicables(self.e.capataz, self.e.invernadero.pk)}
        self.assertEqual((agro["Abono"].destino, agro["Limpiador"].destino), ("costo_de_los_lotes", "gasto"))
        self.assertEqual(agro["Limpiador"].precio, D("5.00"))
        self.assertTrue(all(f.precio is None and f.destino is None for f in cap.values()))
        self.assertEqual(cap["Limpiador"].stock_libre, D("20"))  # las cantidades y los lotes sí

    def test_ext_6b_sin_insumos_que_admitan_consumo_directo_devuelve_la_lista_vacia(self):
        """Extensión 6b: el invernadero sin insumos aplicables no es un error: la lista vacía y la pantalla lo informa."""
        otro = crear_invernadero("Vacio", agronomo=self.e.agronomo)
        self.assertEqual(aplicaciones.insumos_aplicables(self.e.agronomo, otro.pk), [])

    def test_regla_quien_registra_un_invernadero_ajeno_o_un_gerente_se_rechaza(self):
        """Regla «Quién lo registra»: el Agrónomo en los invernaderos a su cargo y el Capataz en los asignados; el Gerente no registra."""
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com"))
        self.assertEqual(rechazo(lambda: aplicaciones.insumos_aplicables(self.e.capataz, ajeno.pk)).codigo, "sin_permiso")
        gerente = crear_gerente()
        self.assertEqual(rechazo(lambda: aplicaciones.insumos_aplicables(gerente, self.e.invernadero.pk)).codigo, "sin_permiso")
        self.assertEqual(rechazo(lambda: aplicaciones.sectores_de_aplicacion(gerente, self.e.invernadero.pk)).codigo, "sin_permiso")
        with self.assertRaises(Http404):
            aplicaciones.insumos_aplicables(self.e.capataz, 999999)


class ResumenTests(Base):
    def test_paso_10_agronomo_ve_valor_destino_y_reparto_entre_los_lotes_de_plantas(self):
        """Paso 10.3 y reglas «Valor del consumo» y «Reparto del costo»: el Agrónomo ve el valor (7 kg × 4,00 = 28,00), su destino y el reparto entre los
        lotes con plantas en el alcance (60 y 40 plantas → 16,80 y 11,20) con su costo por planta antes y después."""
        resumen = self.resumen(self.linea(self.abono, "7"))
        linea = resumen.lineas[0]
        self.assertEqual((linea.valor, linea.destino, linea.faltante), (D("28.00"), "costo_de_los_lotes", D("0")))
        filas = {f.lote_id: f for f in linea.reparto}
        self.assertEqual((filas[self.a.pk].plantas, filas[self.a.pk].monto), (60, D("16.80")))
        self.assertEqual((filas[self.b.pk].plantas, filas[self.b.pk].monto), (40, D("11.20")))
        self.assertEqual((filas[self.a.pk].costo_por_planta_antes, filas[self.a.pk].costo_por_planta_despues), (D("1.67"), D("1.95")))
        self.assertEqual(resumen.total_a_gasto, D("0.00"))

    def test_paso_10_un_insumo_como_gasto_no_se_reparte_y_suma_al_total_a_gasto(self):
        """Regla «Destino del costo»: «como gasto» va a «Gastos de Producción»: sin reparto; el resumen informa el monto que va a gasto."""
        resumen = self.resumen(self.linea(self.limpiador, "5"))
        linea = resumen.lineas[0]
        self.assertEqual((linea.valor, linea.destino, linea.reparto), (D("25.00"), "gasto", []))
        self.assertEqual(resumen.total_a_gasto, D("25.00"))

    def test_regla_el_capataz_no_recibe_valores_destinos_reparto_ni_avisos_de_stock(self):
        """Regla «Qué ve cada rol» y requisito del paso 4: con un Capataz, el resumen trae las cantidades y los lotes de insumo, pero `valor`, `destino`,
        `reparto`, `faltante`, `aviso` y `total_a_gasto` vienen en `None`, aunque haya faltante."""
        resumen = self.resumen(self.linea(self.limpiador, "25"), self.linea(self.abono, "2"), actor=self.e.capataz)
        self.assertIsNone(resumen.total_a_gasto)
        for linea in resumen.lineas:
            self.assertEqual((linea.valor, linea.destino, linea.reparto, linea.faltante, linea.aviso), (None, None, None, None, None))
            self.assertTrue(linea.partes)

    def test_ext_8b_agronomo_ve_la_cantidad_sin_lote_y_se_registra_igual(self):
        """Extensión 8b: una cantidad que supera lo disponible no se bloquea (el hecho ya ocurrió); al Agrónomo el resumen le informa lo que queda sin lote."""
        resumen = self.resumen(self.linea(self.limpiador, "25"))
        self.assertEqual(resumen.lineas[0].faltante, D("5"))
        self.assertEqual(resumen.lineas[0].partes, [(self.stock_lote(self.limpiador).pk, D("20"))])

    def test_regla_reparto_fefo_propone_primero_el_lote_que_vence_antes(self):
        """Regla «Reparto entre los lotes de insumo»: FEFO; 6 L de Nutriente salen 4 del lote que vence antes y 2 del otro."""
        partes = self.resumen(self.linea(self.nutriente, "6")).lineas[0].partes
        self.assertEqual(partes, [(self.lote_corto.pk, D("4")), (self.lote_largo.pk, D("2"))])

    def test_ext_8c_el_reparto_corregido_de_un_insumo_con_vencimiento_se_respeta(self):
        """Extensión 8c: en un insumo que controla vencimiento, la persona corrige el reparto propuesto: 3 del corto y 3 del largo."""
        reparto = ((self.lote_corto.pk, "3"), (self.lote_largo.pk, "3"))
        partes = self.resumen(self.linea(self.nutriente, "6", reparto=reparto)).lineas[0].partes
        self.assertEqual(partes, [(self.lote_corto.pk, D("3")), (self.lote_largo.pk, D("3"))])

    def test_ext_8c_2a_un_lote_con_mas_de_lo_disponible_se_rechaza_con_la_cantidad_disponible(self):
        """Extensión 8c.2a: la cantidad de un lote supera lo disponible: error en el reparto del insumo, con lo disponible."""
        error = rechazo(lambda: self.resumen(self.linea(self.nutriente, "6", reparto=((self.lote_corto.pk, "5"), (self.lote_largo.pk, "1")))))
        self.assertEqual((error.codigo, error.campo), ("reparto_supera_lote", f"reparto_{self.nutriente.pk}"))
        self.assertEqual(error.datos["disponible"], D("4"))

    def test_ext_10b_un_reparto_que_no_suma_la_cantidad_usada_se_rechaza_con_cuanto_debe_sumar(self):
        """Extensión 10b: el reparto debe sumar la cantidad usada (o lo disponible en los lotes, si es menor); informa cuánto."""
        error = rechazo(lambda: self.resumen(self.linea(self.nutriente, "6", reparto=((self.lote_corto.pk, "2"), (self.lote_largo.pk, "2")))))
        self.assertEqual((error.codigo, error.campo), ("distribucion_incompleta", f"reparto_{self.nutriente.pk}"))
        self.assertEqual(error.datos["debe_sumar"], D("6"))

    def test_ext_10b_con_mas_de_lo_disponible_el_reparto_debe_sumar_lo_disponible(self):
        """Extensión 10b: con 20 L pedidos y 14 disponibles en los lotes, el reparto suma 14 y lo demás es faltante sin lote."""
        reparto = ((self.lote_corto.pk, "4"), (self.lote_largo.pk, "10"))
        linea = self.resumen(self.linea(self.nutriente, "20", reparto=reparto)).lineas[0]
        self.assertEqual((linea.faltante, sum(c for _, c in linea.partes)), (D("6"), D("14")))

    def test_regla_en_un_insumo_sin_vencimiento_el_reparto_enviado_se_ignora_y_sale_fefo(self):
        """Regla «Reparto entre los lotes de insumo»: la propuesta se corrige solo en los insumos que controlan vencimiento; en los demás se aplica tal cual."""
        lote = self.stock_lote(self.limpiador)
        partes = self.resumen(self.linea(self.limpiador, "5", reparto=((lote.pk, "1"),))).lineas[0].partes
        self.assertEqual(partes, [(lote.pk, D("5"))])

    def test_ext_10c_con_costo_de_los_lotes_pero_sin_lotes_de_plantas_va_a_gasto_y_avisa_al_agronomo(self):
        """Extensión 10c: «como costo de los lotes» sin lotes de plantas en el alcance va a gasto; solo el Agrónomo recibe el aviso. Alcance: el sector de
        maduración, donde no hay plantas."""
        sector = self.e.sectores["maduracion"]
        resumen = self.resumen(self.linea(self.abono, "2"), alcance="sectores", sector_ids=(sector.pk,))
        linea = resumen.lineas[0]
        self.assertEqual((linea.destino, linea.reparto), ("gasto", []))
        self.assertEqual(resumen.total_a_gasto, D("8.00"))
        self.assertIn("gasto", linea.aviso)
        capataz = self.resumen(self.linea(self.abono, "2"), alcance="sectores", sector_ids=(sector.pk,), actor=self.e.capataz)
        self.assertIsNone(capataz.lineas[0].aviso)

    def test_regla_alcance_solo_reparte_entre_los_lotes_con_plantas_en_los_sectores_elegidos(self):
        """Regla «Lotes de plantas del alcance»: con el alcance en el sector de germinación, solo el lote A (60 plantas) recibe el costo."""
        linea = self.resumen(self.linea(self.abono, "5"), alcance="sectores", sector_ids=(self.e.sectores["germinacion"].pk,)).lineas[0]
        self.assertEqual([(f.lote_id, f.plantas, f.monto) for f in linea.reparto], [(self.a.pk, 60, D("20.00"))])

    def test_ext_6a_algunos_sectores_sin_marcar_ninguno_se_rechaza(self):
        """Extensión 6a: el actor indicó algunos sectores pero no marcó ninguno: debe marcar al menos uno."""
        error = rechazo(lambda: self.resumen(self.linea(self.abono, "1"), alcance="sectores", sector_ids=()))
        self.assertEqual((error.codigo, error.campo), ("sin_sectores", "sector_ids"))

    def test_regla_alcance_un_sector_fuera_de_servicio_o_ajeno_no_se_puede_elegir(self):
        """Regla «Alcance»: un sector fuera de servicio (o de otro invernadero) no se puede elegir."""
        fuera = self.e.sectores["maduracion"]
        SectorProduccion.objects.filter(pk=fuera.pk).update(estado_sector="fuera_de_servicio")
        ajeno = crear_sector(crear_invernadero("Otro", agronomo=self.e.agronomo), nombre="Ajeno", tipo="germinacion")
        for sector in (fuera, ajeno):
            error = rechazo(lambda: self.resumen(self.linea(self.abono, "1"), alcance="sectores", sector_ids=(sector.pk,)))
            self.assertEqual((error.codigo, error.campo), ("sector_no_elegible", "sector_ids"))

    def test_ext_4a_un_invernadero_sin_sectores_activos_solo_admite_todo_el_invernadero(self):
        """Extensión 4a: sin sectores activos solo puede indicarse todo el invernadero; el reparto no tiene lotes y el costo va a gasto."""
        vacio = crear_invernadero("Vacio", agronomo=self.e.agronomo)
        habilitado = existencia(insumo("Abono vacio", tipo=tipo("como_costo_de_los_lotes"), unidad="kg"), vacio, precio="4.00")
        lote_de_insumo(habilitado, 10)
        datos = aplicaciones.DatosDeAplicacion(invernadero_id=vacio.pk, lineas=(aplicaciones.LineaDeAplicacion(habilitado.pk, "2"),))
        resumen = aplicaciones.resumen_de_aplicacion(self.e.agronomo, datos)
        self.assertEqual(resumen.lineas[0].destino, "gasto")
        self.assertEqual(aplicaciones.sectores_de_aplicacion(self.e.agronomo, vacio.pk), [])

    def test_ext_10a_sin_ningun_insumo_se_rechaza(self):
        """Extensión 10a: debe indicar al menos un insumo."""
        self.assertEqual(rechazo(lambda: self.resumen()).codigo, "sin_insumos")

    def test_regla_insumos_que_se_ofrecen_un_insumo_no_aplicable_o_repetido_se_rechaza(self):
        """Regla «Insumos que se ofrecen»: solo los aplicables, y cada insumo una sola vez por aplicación."""
        error = rechazo(lambda: self.resumen(self.linea(self.no_admite, "1")))
        self.assertEqual((error.codigo, error.campo), ("insumo_no_aplicable", f"insumo_{self.no_admite.pk}"))
        error = rechazo(lambda: self.resumen(self.linea(self.limpiador, "1"), self.linea(self.limpiador, "2")))
        self.assertEqual((error.codigo, error.campo), ("insumo_repetido", f"insumo_{self.limpiador.pk}"))

    def test_ext_8a_la_cantidad_debe_ser_mayor_que_cero_y_con_los_decimales_de_la_unidad(self):
        """Extensión 8a y regla «Cantidad válida»: mayor que cero; en «unidad» solo enteros; el error informa cuántos decimales admite."""
        for valor in ("0", "-1", "abc", ""):
            error = rechazo(lambda: self.resumen(self.linea(self.limpiador, valor)))
            self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", f"cantidad_{self.limpiador.pk}"))
        error = rechazo(lambda: self.resumen(self.linea(self.guantes, "1.5")))
        self.assertEqual(error.codigo, "cantidad_invalida")
        self.assertIn("entera", error.mensaje)
        self.assertEqual(self.resumen(self.linea(self.limpiador, "1.234")).lineas[0].cantidad, D("1.234"))

    def test_regla_la_descripcion_admite_hasta_500_caracteres(self):
        """Postcondición a: la descripción es opcional y de hasta 500 caracteres."""
        self.resumen(self.linea(self.limpiador, "1"), descripcion="a" * 500)
        error = rechazo(lambda: self.resumen(self.linea(self.limpiador, "1"), descripcion="a" * 501))
        self.assertEqual((error.codigo, error.campo), ("descripcion_larga", "descripcion"))

    def test_paso_10_el_resumen_no_escribe_nada(self):
        """El resumen no registra ningún cambio: ni stock, ni costos, ni auditoría."""
        antes = (self.disponible(self.stock_lote(self.limpiador)), Lote.objects.get(pk=self.a.pk).costo_acumulado)
        self.resumen(self.linea(self.limpiador, "5"), self.linea(self.abono, "3"))
        self.nada_se_escribio()
        self.assertEqual((self.disponible(self.stock_lote(self.limpiador)), Lote.objects.get(pk=self.a.pk).costo_acumulado), antes)


class RegistrarTests(Base):
    def test_flujo_principal_el_capataz_registra_una_aplicacion_de_un_insumo_como_gasto(self):
        """Flujo principal (pasos 1 a 13): devuelve la aplicación y sus líneas."""
        resultado = self.registrar(self.linea(self.limpiador, "5"), descripcion="Limpieza de pasillos")
        self.assertIsInstance(resultado.aplicacion, AplicacionInsumos)
        self.assertEqual(AplicacionInsumos.objects.get().pk, resultado.aplicacion.pk)
        self.assertEqual(len(resultado.lineas), 1)

    def test_post_a_la_aplicacion_queda_en_la_bitacora_con_fecha_hora_descripcion_responsable_e_invernadero(self):
        """Postcondición a: registro de bitácora tipo «aplicación» con la fecha y hora actuales, la descripción, el actor como responsable, asociada al invernadero
        y, si se indicaron, a los sectores; sin lote ni etapa."""
        sector = self.e.sectores["germinacion"]
        antes = timezone.localtime().time()
        resultado = self.registrar(self.linea(self.limpiador, "5"), descripcion="Limpieza", alcance="sectores", sector_ids=(sector.pk,))
        despues = timezone.localtime().time()
        guardada = Bitacora.objects.get(pk=resultado.aplicacion.pk)
        self.assertEqual((guardada.tipo_evento, guardada.descripcion_evento), ("aplicacion", "Limpieza"))
        self.assertEqual((guardada.responsable_id, guardada.fecha_bitacora, guardada.invernadero_id), (self.e.capataz.pk, HOY, self.e.invernadero.pk))
        self.assertTrue(antes <= guardada.hora_bitacora <= despues)
        self.assertEqual((guardada.lote_id, guardada.etapa_id), (None, None))
        self.assertEqual([s.pk for s in guardada.sectores.all()], [sector.pk])

    def test_post_a_todo_el_invernadero_deja_los_sectores_vacios_y_sin_descripcion_arma_una_legible(self):
        """Regla «Alcance» y D-51 punto 8: «todo el invernadero» es sin sectores; sin descripción del actor, «Aplicación de insumos: …» con la lista."""
        resultado = self.registrar(self.linea(self.limpiador, "5"), self.linea(self.guantes, "2"))
        guardada = Bitacora.objects.get(pk=resultado.aplicacion.pk)
        self.assertEqual(guardada.sectores.count(), 0)
        self.assertTrue(guardada.descripcion_evento.startswith("Aplicación de insumos: "))
        self.assertIn("Limpiador", guardada.descripcion_evento)
        self.assertIn("Guantes", guardada.descripcion_evento)
        self.assertLessEqual(len(guardada.descripcion_evento), 500)

    def test_post_b_un_consumo_por_insumo_originado_en_la_aplicacion_con_su_cantidad_monto_y_fecha(self):
        """Postcondición b: por cada insumo, un consumo (fila de bitácora interna de tipo «consumo») asociado a la aplicación y al insumo del invernadero, con
        la cantidad, el monto (cantidad × precio de referencia, 2 decimales) y la fecha actual; sin siembra."""
        resultado = self.registrar(self.linea(self.limpiador, "5"), self.linea(self.abono, "7"))
        consumos = {c.insumo_invernadero_id: c for c in Consumo.objects.filter(aplicacion=resultado.aplicacion)}
        self.assertEqual(len(consumos), 2)
        limpiador, abono = consumos[self.limpiador.pk], consumos[self.abono.pk]
        self.assertEqual((limpiador.cant_consumo, limpiador.monto_consumo, limpiador.fecha_consumo), (D("5"), D("25.00"), HOY))
        self.assertEqual((abono.cant_consumo, abono.monto_consumo), (D("7"), D("28.00")))
        self.assertEqual((limpiador.tipo_evento, limpiador.siembra_id, limpiador.invernadero_id), ("consumo", None, self.e.invernadero.pk))
        self.assertEqual(limpiador.responsable_id, self.e.capataz.pk)

    def test_post_c_y_d_baja_el_lote_de_insumo_y_un_movimiento_de_salida_por_consumo_originado_en_el_consumo(self):
        """Postcondiciones c y d: la cantidad disponible del lote de insumo baja y se registra un movimiento «salida por consumo» por lote, asociado al
        insumo y al lote y originado en el consumo (D-52); el consumo se creó antes que su movimiento."""
        lote = self.stock_lote(self.limpiador)
        resultado = self.registrar(self.linea(self.limpiador, "5"))
        self.assertEqual(self.disponible(lote), D("15"))
        consumo = Consumo.objects.get(aplicacion=resultado.aplicacion)
        movimientos = list(consumo.movimientos_de_insumo.all())
        self.assertEqual([(m.lote_insumo_id, m.cantidad, m.tipo_movimiento) for m in movimientos], [(lote.pk, D("5"), "salida_por_consumo")])
        self.assertEqual(timezone.localtime(movimientos[0].fecha).date(), HOY)  # la fecha se guarda en UTC: se compara en hora local (entre las 21 y las 24 h locales difieren)

    def test_post_c_con_vencimiento_el_reparto_fefo_o_el_corregido_se_aplica_por_lote(self):
        """Postcondición c y regla «Reparto»: sin corregir, FEFO (4 del corto y 2 del largo); un movimiento por lote."""
        resultado = self.registrar(self.linea(self.nutriente, "6"))
        self.assertEqual((self.disponible(self.lote_corto), self.disponible(self.lote_largo)), (D("0"), D("8")))
        self.assertEqual(Consumo.objects.get(aplicacion=resultado.aplicacion).movimientos_de_insumo.count(), 2)

    def test_post_c_el_reparto_corregido_por_la_persona_se_aplica(self):
        """Extensión 8c: el reparto corregido (3 y 3) es el que se descuenta."""
        self.registrar(self.linea(self.nutriente, "6", reparto=((self.lote_corto.pk, "3"), (self.lote_largo.pk, "3"))))
        self.assertEqual((self.disponible(self.lote_corto), self.disponible(self.lote_largo)), (D("1"), D("7")))

    def test_ext_8b_lo_que_supera_los_lotes_sale_del_faltante_sin_lote_y_alerta_solo_al_agronomo(self):
        """Extensión 8b y postcondiciones c, d y g: 25 L con 20 disponibles → el lote queda en 0, el faltante sin lote en −5 (con su movimiento) y existe para
        el Agrónomo una alerta «stock inconsistente» activa. Al Capataz no se le informa: ni resultado ni notificación."""
        resultado = self.registrar(self.linea(self.limpiador, "25"))
        self.assertEqual(self.disponible(self.stock_lote(self.limpiador)), D("0"))
        faltante = LoteInsumo.objects.get(insumo_invernadero=self.limpiador, es_faltante_sin_lote=True)
        self.assertEqual(faltante.cantidad_disponible, D("-5"))
        self.assertEqual(Consumo.objects.get(aplicacion=resultado.aplicacion).movimientos_de_insumo.count(), 2)
        alerta = Alerta.objects.get(tipo_alerta=INCONSISTENTE)
        self.assertEqual((alerta.agronomo_id, alerta.estado_alerta), (self.e.agronomo.pk, "activa"))
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual((resultado.lineas[0].faltante, resultado.lineas[0].valor), (None, None))

    def test_post_g_se_reevalua_la_alerta_de_stock_bajo_el_minimo(self):
        """Postcondición g: «se reevaluó la alerta de stock bajo el mínimo de cada insumo»: con mínimo 18 y 20 en stock, usar 5 deja 15 < 18 y crea la alerta."""
        InsumoInvernadero.objects.filter(pk=self.limpiador.pk).update(cant_min_insumo=D("18"))
        self.registrar(self.linea(self.limpiador, "5"))
        self.assertTrue(Alerta.objects.filter(tipo_alerta="inv_insumo_bajo_minimo", estado_alerta="activa").exists())

    def test_post_e_como_costo_de_los_lotes_imputa_a_cada_lote_con_plantas_y_sube_su_costo_acumulado(self):
        """Postcondición e: 7 kg × 4,00 = 28,00 se reparte entre los lotes con plantas en el alcance (60 y 40) → 16,80 y 11,20; una imputación por lote, asociada
        al consumo, y el costo acumulado de cada lote sube en su parte. La cantidad, la etapa y las ocupaciones no cambian (garantía mínima)."""
        ocupaciones = list(OcupacionSector.objects.values_list("pk", "cant_agujeros_ocupados").order_by("pk"))
        resultado = self.registrar(self.linea(self.abono, "7"))
        consumo = Consumo.objects.get(aplicacion=resultado.aplicacion)
        partes = {i.lote_id: i.monto_imputado for i in consumo.imputaciones.all()}
        self.assertEqual(partes, {self.a.pk: D("16.80"), self.b.pk: D("11.20")})
        a, b = Lote.objects.get(pk=self.a.pk), Lote.objects.get(pk=self.b.pk)
        self.assertEqual((a.costo_acumulado, b.costo_acumulado), (D("116.80"), D("61.20")))
        self.assertEqual((a.cantidad_actual, b.cantidad_actual, a.etapa_id), (60, 40, self.a.etapa_id))
        self.assertEqual(list(OcupacionSector.objects.values_list("pk", "cant_agujeros_ocupados").order_by("pk")), ocupaciones)

    def test_post_e_la_suma_de_las_imputaciones_es_exactamente_el_monto_del_consumo(self):
        """Garantía mínima: la suma de las imputaciones de un consumo es exactamente su monto (3 × 3,33 = 9,99 → 5,99 y 4,00: el centavo, al mayor resto)."""
        raro = self.stock("Raro", "como_costo_de_los_lotes", 10, "kg", "3.33")
        resultado = self.registrar(self.linea(raro, "3"))
        consumo = Consumo.objects.get(aplicacion=resultado.aplicacion)
        partes = {i.lote_id: i.monto_imputado for i in consumo.imputaciones.all()}
        self.assertEqual(partes, {self.a.pk: D("5.99"), self.b.pk: D("4.00")})
        self.assertEqual(sum(partes.values()), consumo.monto_consumo)

    def test_post_e_como_gasto_no_imputa_ni_cambia_el_costo_de_los_lotes(self):
        """Regla «Destino del costo»: «como gasto» no imputa: ninguna imputación y los lotes de plantas no cambian."""
        self.registrar(self.linea(self.limpiador, "5"))
        self.assertFalse(ImputacionCosto.objects.exists())
        self.assertEqual(Lote.objects.get(pk=self.a.pk).costo_acumulado, D("100.00"))

    def test_post_e_sin_lotes_de_plantas_en_el_alcance_el_costo_va_a_gasto_sin_imputaciones(self):
        """Extensión 10c: sin lotes de plantas en el alcance, no hay imputaciones aunque la categoría sea «como costo de los lotes»."""
        self.registrar(self.linea(self.abono, "2"), alcance="sectores", sector_ids=(self.e.sectores["maduracion"].pk,))
        self.assertFalse(ImputacionCosto.objects.exists())
        self.assertEqual(Lote.objects.get(pk=self.b.pk).costo_acumulado, D("50.00"))

    def test_post_e_un_lote_que_recibe_cero_centavos_no_tiene_imputacion(self):
        """Patrón del costo, ejemplo 4: 0,01 entre 60 y 40 plantas: el lote de más plantas recibe 0,01 y el otro 0,00, que no se imputa."""
        centavo = self.stock("Centavo", "como_costo_de_los_lotes", 10, "unidad", "0.01")
        resultado = self.registrar(self.linea(centavo, "1"))
        partes = {i.lote_id: i.monto_imputado for i in Consumo.objects.get(aplicacion=resultado.aplicacion).imputaciones.all()}
        self.assertEqual(partes, {self.a.pk: D("0.01")})

    def test_post_e_las_plantas_del_alcance_son_las_de_los_sectores_elegidos(self):
        """Regla «Lotes de plantas del alcance»: con el alcance en un sector, solo recibe el costo el lote con plantas ahí (todo el consumo)."""
        resultado = self.registrar(self.linea(self.abono, "5"), alcance="sectores", sector_ids=(self.e.sectores["crecimiento"].pk,))
        partes = {i.lote_id: i.monto_imputado for i in Consumo.objects.get(aplicacion=resultado.aplicacion).imputaciones.all()}
        self.assertEqual(partes, {self.b.pk: D("20.00")})

    def test_regla_que_ve_cada_rol_el_agronomo_recibe_valores_reparto_y_faltante_y_el_capataz_nada(self):
        """Regla «Qué ve cada rol» (paso 13): el resultado para el Agrónomo trae montos, reparto y faltante; para el Capataz, `None`."""
        agro = self.registrar(self.linea(self.abono, "7"), self.linea(self.limpiador, "25"), actor=self.e.agronomo)
        valores = {l.nombre: l for l in agro.lineas}
        self.assertEqual((valores["Abono"].valor, valores["Abono"].destino), (D("28.00"), "costo_de_los_lotes"))
        self.assertEqual({f.lote_id: f.monto for f in valores["Abono"].reparto}, {self.a.pk: D("16.80"), self.b.pk: D("11.20")})
        self.assertEqual(valores["Limpiador"].faltante, D("5"))
        cap = self.registrar(self.linea(self.guantes, "1"))
        self.assertEqual((cap.lineas[0].valor, cap.lineas[0].destino, cap.lineas[0].reparto, cap.lineas[0].faltante), (None, None, None, None))

    def test_regla_sin_notificacion_al_registrar_el_capataz_no_se_avisa_al_agronomo(self):
        """Regla «Sin notificación»: la aplicación queda en la bitácora; no se notifica al Agrónomo cuando la registra el Capataz."""
        self.registrar(self.linea(self.limpiador, "5"))
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_post_h_un_solo_registro_de_auditoria_con_la_aplicacion_los_consumos_movimientos_imputaciones_lotes_y_alertas(self):
        """Postcondiciones h e i y D-36: UN registro `registro_aplicacion` con quien actuó, la aplicación, los consumos, los movimientos de insumo, las
        imputaciones, los lotes de insumo y de plantas modificados (con su cambio de valor) y las alertas creadas."""
        resultado = self.registrar(self.linea(self.abono, "7"), self.linea(self.limpiador, "25"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_aplicacion").count(), 1)
        registro = RegistroAuditoria.objects.get(accion="registro_aplicacion")
        self.assertEqual(registro.usuario_id, self.e.capataz.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        consumos = list(Consumo.objects.filter(aplicacion=resultado.aplicacion))
        esperados = {("produccion.aplicacioninsumos", resultado.aplicacion.pk), ("produccion.lote", self.a.pk), ("produccion.lote", self.b.pk)}
        esperados |= {("produccion.consumo", c.pk) for c in consumos}
        esperados |= {("produccion.imputacioncosto", i.pk) for i in ImputacionCosto.objects.all()}
        esperados |= {("inventario.movimientoinsumo", m.pk) for c in consumos for m in c.movimientos_de_insumo.all()}
        esperados |= {("inventario.loteinsumo", l.pk) for l in LoteInsumo.objects.filter(insumo_invernadero__in=[self.abono, self.limpiador])}
        esperados.add(("maestros.alerta", Alerta.objects.get(tipo_alerta=INCONSISTENTE).pk))
        self.assertTrue(esperados <= afectados, esperados - afectados)
        self.assertIn("costo_acumulado", registro.detalle["cambios"])
        self.assertIn("lotes_de_insumo", registro.detalle["cambios"])

    def test_regla_los_datos_y_el_resumen_no_auditan(self):
        """D-36: un registro por caso de uso: la lectura y el resumen no escriben auditoría."""
        aplicaciones.insumos_aplicables(self.e.capataz, self.e.invernadero.pk)
        aplicaciones.sectores_de_aplicacion(self.e.capataz, self.e.invernadero.pk)
        self.resumen(self.linea(self.limpiador, "5"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_aplicacion").count(), 0)

    def test_regla_quien_registra_un_capataz_ajeno_un_gerente_una_cuenta_inactiva_o_un_invernadero_inactivo_se_rechazan(self):
        """Regla «Quién lo registra»: solo el Agrónomo a cargo y el Capataz asignado, con la cuenta activa, en un invernadero activo."""
        ajeno = crear_capataz_activo(email="ajeno@infoponia.com")
        self.assertEqual(rechazo(lambda: self.registrar(self.linea(self.limpiador, "1"), actor=ajeno)).codigo, "sin_permiso")
        self.assertEqual(rechazo(lambda: self.registrar(self.linea(self.limpiador, "1"), actor=crear_gerente())).codigo, "sin_permiso")
        capataz = self.e.capataz
        capataz.is_active = False
        capataz.save()
        self.assertEqual(rechazo(lambda: self.registrar(self.linea(self.limpiador, "1"), actor=capataz)).codigo, "sin_permiso")
        capataz.is_active = True
        capataz.save()
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(rechazo(lambda: self.registrar(self.linea(self.limpiador, "1"))).codigo, "invernadero_inactivo")
        self.nada_se_escribio()

    def test_regla_todo_o_nada_un_error_en_la_segunda_linea_no_deja_nada_a_medias(self):
        """Garantías mínimas: si una línea es inválida no se registra ninguna bitácora, consumo, movimiento, imputación ni auditoría, y no cambia ningún lote."""
        antes = self.disponible(self.stock_lote(self.limpiador))
        rechazo(lambda: self.registrar(self.linea(self.limpiador, "5"), self.linea(self.guantes, "1.5")))
        self.nada_se_escribio()
        self.assertEqual(self.disponible(self.stock_lote(self.limpiador)), antes)

    def test_ext_12a_un_lote_de_insumo_que_cambio_desde_que_la_persona_lo_vio_pide_volver_al_paso_6(self):
        """Extensión 12a: otra operación cambió la cantidad disponible de un lote de insumo indicado: no se registra nada y `cambio_simultaneo` informa qué cambió."""
        lote = self.stock_lote(self.limpiador)
        vistos = ((lote.pk, D("20")),)
        LoteInsumo.objects.filter(pk=lote.pk).update(cantidad_disponible=D("12"))
        error = rechazo(lambda: self.registrar(self.linea(self.limpiador, "5", lotes_vistos=vistos)))
        self.assertEqual(error.codigo, "cambio_simultaneo")
        self.assertTrue(error.datos["cambios"])
        self.nada_se_escribio()

    def test_ext_12a_las_plantas_de_los_lotes_del_alcance_que_cambiaron_piden_volver_al_paso_6(self):
        """Extensión 12a: cambiaron las plantas de los lotes del alcance (otra merma): `cambio_simultaneo`, sin registrar nada."""
        vistas = ((self.a.pk, 60), (self.b.pk, 40))
        OcupacionSector.objects.filter(lote=self.a, cant_agujeros_ocupados__gt=0).update(cant_agujeros_ocupados=55)
        error = rechazo(lambda: self.registrar(self.linea(self.abono, "7"), plantas_vistas=vistas))
        self.assertEqual(error.codigo, "cambio_simultaneo")
        self.nada_se_escribio()

    def test_ext_12a_un_insumo_que_se_deshabilito_despues_de_verlo_es_un_cambio_simultaneo(self):
        """Extensión 12a: cambió la habilitación o el estado de un insumo que la persona había visto (traía `lotes_vistos`): `cambio_simultaneo`."""
        lote = self.stock_lote(self.guantes)
        InsumoInvernadero.objects.filter(pk=self.guantes.pk).update(estado_insumo_invernadero="inactivo")
        error = rechazo(lambda: self.registrar(self.linea(self.guantes, "1", lotes_vistos=((lote.pk, D("10")),))))
        self.assertEqual(error.codigo, "cambio_simultaneo")
        error = rechazo(lambda: self.registrar(self.linea(self.guantes, "1")))
        self.assertEqual(error.codigo, "insumo_no_aplicable")

    def test_ext_12a_con_lo_visto_vigente_registra_normalmente(self):
        """Extensión 12a: si lo que la persona vio sigue vigente no hay conflicto."""
        lote = self.stock_lote(self.limpiador)
        self.registrar(self.linea(self.limpiador, "5", lotes_vistos=((lote.pk, D("20")),)), plantas_vistas=((self.a.pk, 60), (self.b.pk, 40)))
        self.assertEqual(AplicacionInsumos.objects.count(), 1)

    def test_regla_el_valor_se_fija_al_registrar_con_el_precio_de_referencia_de_ese_momento(self):
        """Regla «Valor del consumo»: cantidad × precio de referencia del insumo en el invernadero, en el momento del registro; queda fijo aunque el precio cambie."""
        resultado = self.registrar(self.linea(self.limpiador, "5"))
        InsumoInvernadero.objects.filter(pk=self.limpiador.pk).update(referencia_precio=D("99.00"))
        self.assertEqual(Consumo.objects.get(aplicacion=resultado.aplicacion).monto_consumo, D("25.00"))


class PlantasDelAlcanceTests(Base):
    """`plantas_del_alcance` (agregado en PRD-03, paso 7): lo que la pantalla guarda como `plantas_vistas` para la extensión 12a."""

    def test_ext_12a_devuelve_las_plantas_de_cada_lote_en_los_sectores_del_alcance(self):
        """Todo el invernadero: las plantas de cada lote; con sectores, solo las de esos sectores. Sin valores en dinero (el Capataz también la usa)."""
        todo = aplicaciones.plantas_del_alcance(self.e.capataz, self.datos(self.linea(self.limpiador, "1")))
        self.assertEqual(todo, ((self.a.pk, 60), (self.b.pk, 40)))
        uno = aplicaciones.plantas_del_alcance(
            self.e.capataz, self.datos(self.linea(self.limpiador, "1"), alcance="sectores", sector_ids=(self.e.sectores["crecimiento"].pk,))
        )
        self.assertEqual(uno, ((self.b.pk, 40),))
        self.assertEqual(rechazo(lambda: aplicaciones.plantas_del_alcance(crear_gerente(), self.datos())).codigo, "sin_permiso")


class RegistrarAsientoTests(Base):
    """CON-04a · PROD-REG-APL postcondición f (D-92 puntos 2 a 6 y 9, D-86): un asiento por consumo, originado en el consumo, por su monto y con la fecha
    de la aplicación (hoy): Debe «Productos en Proceso» si el costo se imputó a lotes o «Gastos de Producción» si va a gasto / Haber «Insumos en Stock»."""

    def lineas(self, asiento):
        return sorted(
            (m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento)
            for m in MovimientoContable.objects.filter(asiento=asiento).select_related("cuenta")
        )

    def asiento_de(self, resultado, habilitado):
        consumo = Consumo.objects.get(aplicacion=resultado.aplicacion, insumo_invernadero=habilitado)
        return consumo, AsientoContable.objects.get(origen_id=consumo.pk)

    def test_post_f_un_insumo_como_gasto_asienta_gastos_de_produccion_contra_insumos_en_stock(self):
        """Postcondición f, rama «va a gasto»: 5 L de limpiador a $5,00 = $25,00 → Debe Gastos de Producción / Haber Insumos en Stock, origen el consumo,
        fecha de hoy y la descripción legible del consumo. No había ejercicio: lo abre la autorrecuperación (H9)."""
        resultado = self.registrar(self.linea(self.limpiador, "5"))
        consumo, asiento = self.asiento_de(resultado, self.limpiador)
        self.assertEqual(asiento.fecha_asiento, HOY)
        self.assertEqual(asiento.descripcion_asiento, consumo.descripcion_evento)
        esperado = [(cuentas.GASTOS_DE_PRODUCCION, DEBE, D("25.00")), (cuentas.INSUMOS_EN_STOCK, HABER, D("25.00"))]
        self.assertEqual(self.lineas(asiento), sorted(esperado))
        self.assertEqual(EjercicioContable.objects.get().ultimo_numero_asiento, 1)
        verificar_invariantes_contables()

    def test_post_f_un_insumo_imputado_a_lotes_asienta_productos_en_proceso_contra_insumos_en_stock(self):
        """Postcondición f, rama «imputado a lotes»: 7 kg de abono a $4,00 = $28,00 (repartido en dos lotes de plantas) → un solo asiento por el consumo."""
        resultado = self.registrar(self.linea(self.abono, "7"))
        consumo, asiento = self.asiento_de(resultado, self.abono)
        self.assertEqual(consumo.imputaciones.count(), 2)
        esperado = [(cuentas.PRODUCTOS_EN_PROCESO, DEBE, D("28.00")), (cuentas.INSUMOS_EN_STOCK, HABER, D("28.00"))]
        self.assertEqual(self.lineas(asiento), sorted(esperado))
        self.assertEqual(AsientoContable.objects.count(), 1)  # uno por consumo, no uno por imputación (D-92, «alternativas»)
        verificar_invariantes_contables()

    def test_post_f_sin_lotes_de_plantas_en_el_alcance_un_insumo_de_costo_de_lotes_asienta_a_gasto(self):
        """Extensión 10c y D-92: el consumo sin imputaciones va a gasto aunque la categoría sea «como costo de los lotes»: Debe Gastos de Producción."""
        resultado = self.registrar(self.linea(self.abono, "2"), alcance="sectores", sector_ids=(self.e.sectores["maduracion"].pk,))
        consumo, asiento = self.asiento_de(resultado, self.abono)
        self.assertFalse(consumo.imputaciones.exists())
        self.assertIn((cuentas.GASTOS_DE_PRODUCCION, DEBE, D("8.00")), self.lineas(asiento))
        self.assertNotIn(cuentas.PRODUCTOS_EN_PROCESO, [c for c, _, _ in self.lineas(asiento)])

    def test_post_f_un_asiento_por_consumo_con_importes_distintos(self):
        """D-92 punto 6: dos insumos (uno a gasto, uno a lotes) tienen cada uno su asiento, con su cuenta y su monto; los números son 1 y 2."""
        resultado = self.registrar(self.linea(self.limpiador, "5"), self.linea(self.abono, "7"))
        self.assertEqual(AsientoContable.objects.count(), 2)
        self.assertIn((cuentas.GASTOS_DE_PRODUCCION, DEBE, D("25.00")), self.lineas(self.asiento_de(resultado, self.limpiador)[1]))
        self.assertIn((cuentas.PRODUCTOS_EN_PROCESO, DEBE, D("28.00")), self.lineas(self.asiento_de(resultado, self.abono)[1]))
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2])
        verificar_invariantes_contables()

    def test_post_f_un_consumo_de_cero_pesos_no_asienta_y_no_falla(self):
        """D-92 punto 5 y H11: 0,4 kg a $0,01 redondea a $0,00: el consumo se registra y no genera asiento; el otro insumo sí."""
        barato = self.stock("Barato", "como_gasto", 10, "kg", "0.01")
        resultado = self.registrar(self.linea(barato, "0.4"), self.linea(self.limpiador, "5"))
        consumo = Consumo.objects.get(aplicacion=resultado.aplicacion, insumo_invernadero=barato)
        self.assertEqual(consumo.monto_consumo, D("0.00"))
        self.assertFalse(AsientoContable.objects.filter(origen_id=consumo.pk).exists())
        self.assertEqual(AsientoContable.objects.count(), 1)

    def test_post_f_la_ficha_del_asiento_muestra_el_consumo_de_la_aplicacion_con_su_fecha_sin_enlace(self):
        """CON-04a, «enlace al origen»: la ficha del libro nombra el consumo de la aplicación y su fecha, sin dirección."""
        from contabilidad import extensiones as extensiones_de_contabilidad

        resultado = self.registrar(self.linea(self.limpiador, "5"))
        consumo = Consumo.objects.get(aplicacion=resultado.aplicacion)
        texto, url = extensiones_de_contabilidad.enlace_de_origen(AsientoContable.objects.get().origen)
        self.assertEqual(texto, f"Consumo · {consumo.descripcion_evento} ({HOY:%d/%m/%Y})")
        self.assertIsNone(url)

    def test_post_h_los_asientos_van_entre_los_afectados_del_registro_de_auditoria_y_en_sus_datos(self):
        """Postcondición h y D-92 punto 3: `registro_aplicacion` nombra cada asiento entre sus afectados y en `datos`; el asiento y sus movimientos los
        audita `contabilidad`."""
        self.registrar(self.linea(self.limpiador, "5"), self.linea(self.abono, "7"))
        registro = RegistroAuditoria.objects.get(accion="registro_aplicacion")
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        for asiento in AsientoContable.objects.all():
            self.assertIn(("contabilidad.asientocontable", asiento.pk), afectados)
        self.assertEqual(len(registro.detalle["datos"]["asientos"]), 2)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_asiento_contable").count(), 2)

    def test_regla_que_ve_cada_rol_el_capataz_registra_con_asiento_y_no_recibe_valores(self):
        """«Qué ve cada rol»: el asiento se crea igual cuando registra el Capataz, pero lo que se le devuelve sigue sin valores ni destino."""
        resultado = self.registrar(self.linea(self.limpiador, "5"))
        self.assertEqual(AsientoContable.objects.count(), 1)
        self.assertEqual((resultado.lineas[0].valor, resultado.lineas[0].destino), (None, None))

    def test_garantia_si_falla_el_segundo_asiento_no_queda_nada_de_la_aplicacion(self):
        """D-22 y `docs/patrones/asientos.md` §4: si el asiento del segundo consumo falla, se revierte todo (ni el primer asiento, ni consumos, ni
        imputaciones, ni descuento de stock)."""
        real = servicio_de_asientos.registrar_asiento_automatico
        llamadas = []

        def falla_en_la_segunda(*args, **kwargs):
            llamadas.append(1)
            if len(llamadas) == 2:
                raise RuntimeError("falla del asiento")
            return real(*args, **kwargs)

        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=falla_en_la_segunda):
            with self.assertRaises(RuntimeError):
                self.registrar(self.linea(self.limpiador, "5"), self.linea(self.abono, "7"))
        self.assertEqual(len(llamadas), 2)
        self.nada_se_escribio()
        self.assertEqual(self.disponible(self.stock_lote(self.limpiador)), D("20"))

    def test_garantia_un_rechazo_no_crea_asientos_ni_abre_el_ejercicio(self):
        """Un rechazo (cantidad inválida) no deja asientos ni abre un ejercicio."""
        rechazo(lambda: self.registrar(self.linea(self.limpiador, "-1")))
        self.assertEqual((AsientoContable.objects.count(), EjercicioContable.objects.count()), (0, 0))
