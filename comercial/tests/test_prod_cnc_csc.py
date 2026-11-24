# Pruebas de PROD-CNC-CSC, Concretar Cosecha (COM-04a, paso 5; docs/casos_de_uso/produccion/cosecha.md, «Cómo se aplica en la ronda «Comercial 1»»):
# `comercial/servicios/cosechas.py`, SIN el `on_commit` de PROD-ASG-CAM (postcondición k: COM-04b) ni el enlace de la extensión 13a (COM-04c). Una prueba
# por postcondición (a a e, g a j, l, m, o a r) y por extensión (4a, 6a, 6b, 8a, 8b, 10a con sus 3a y 3b, 10b, 12a, 13a con cobertura total, parcial y nula,
# en compra-venta y en suministro, 13b, 13c). La concurrencia está en `test_cosechas_concurrencia.py`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), en `comercial/servicios/cosechas.py`:
#   - `propuesta_por_sector(cantidad, ocupados) -> {sector_id: plantas}` (función pura): `ocupados` es `[(sector_id, agujeros ocupados)]` en el orden de los
#     sectores; resto mayor y, con empate, el sector con más agujeros ocupados y después el primero (usa `transiciones.repartir_proporcional`).
#   - `datos_de_concrecion(actor, cosecha_id) -> FichaDeConcrecion(cosecha, contrato, fecha_entrega, hoy, lotes)` con
#     `lotes = [LoteAConcretar(lote_id, codigo, reservada, sectores)]` y `sectores = [SectorAConcretar(sector_id, nombre, ocupados, propuesta)]`.
#   - Datos: `DatosDeConcrecion(fecha_efectiva=None, cantidades=(), perdidas=(), causas=())`: `fecha_efectiva` `None` es hoy; `cantidades` y `perdidas`
#     son `((lote_id, sector_id, plantas), …)` (lo que no figura toma la propuesta y 0 perdidas) y `causas` es `((lote_id, causa, descripcion), …)`.
#   - `verificar_concrecion(actor, cosecha_id, datos) -> ResumenDeConcrecion(errores, lotes, total_reservado, total_cosechado, destino)` (no escribe):
#     `errores = {campo: [(codigo, mensaje)]}` (campos `fecha_efectiva`, `cantidad_<lote>_<sector>`, `lote_<lote>`, `perdidas_<lote>_<sector>`,
#     `causa_<lote>`); `lotes = [FilaDeLoteConcretado(lote_id, codigo, reservada, cosechada, excedente, no_cosechadas, perdidas, quedan_libres)]`;
#     `destino` es una lista de textos («Todo ingresa a la cámara», «El excedente de L-1 (10) ingresa a la cámara», «Faltan 10 plantas…»).
#   - `concretar_cosecha(actor, cosecha_id, datos) -> ResultadoConcrecion(cosecha, reserva, partidas, mermas, asignacion, faltante)`: `PermissionDenied` si no
#     es el Capataz activo asignado; `ValidationError` por campo con `fecha_futura`, `fecha_antes_de_creacion`, `supera_sector`, `supera_maximo`,
#     `supera_no_cosechadas`, `causa_obligatoria` y `orden_no_a_realizar` (13b); `faltante` es lo que se intentó cubrir con `asignar` (o 0) y
#     `asignacion` el resultado de `asignar` (o `None`). Un registro `concrecion_cosecha`; avisa al Agrónomo y, con faltante o excedente, al Vendedor.
# Fuente: PROD-CNC-CSC v0.4, D-64 puntos 2 a 5, 9 y 13, D-36, D-42 y docs/patrones/costo_del_lote.md.

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva, DetalleSuministro, DetalleVenta, ReservaStock
from comercial.servicios import cosechas, stock_maduro
from comercial.servicios.cosechas import DatosDeConcrecion
from comercial.tests.fabricas import (
    compra_venta,
    cosecha_manual,
    detalle,
    detalle_suministro,
    escenario_comercial,
    periodo,
    suministro,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_sector
from produccion.models import Bitacora, Cosecha, Lote, Merma, MovimientoStock, OcupacionSector, OrdenTrabajo, StockCosechado
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def en(dias):
    """La fecha de dentro de ``dias`` días."""
    return HOY + timedelta(days=dias)


def codigos(prueba, llamada, campo=None):
    """Los códigos de los errores de un `ValidationError` que lanza `llamada()` (los de `campo`, o todos)."""
    with prueba.assertRaises(ValidationError) as rechazo:
        llamada()
    return sorted(e.code for clave, lista in rechazo.exception.error_dict.items() if campo in (None, clave) for e in lista)


class Base(ConDatosDeInventario, TestCase):
    """Un lote de 100 plantas en Maduración (costo 100,00: 1,00 por planta) ocupando 100 agujeros de un sector, y una cosecha «a realizar» con contrato
    (compra-venta con envío de 50 plantas para dentro de 10 días) que reserva 30 plantas de él. La postcosecha es de 7 días."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.sector = self.e.sectores["maduracion"]
        self.venta = compra_venta(self.e, dias=10)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.cosecha = cosecha_manual(self.e, [(self.lote, 30)], detalle_=self.detalle)
        self.addCleanup(verificar_invariantes_de_reservas)

    def datos(self, cantidades=None, **extra):
        """`DatosDeConcrecion` con `cantidades` `{(lote, sector): plantas}` (por omisión, la propuesta)."""
        if cantidades is not None:
            extra["cantidades"] = tuple((lote.pk, sector.pk, n) for (lote, sector), n in cantidades.items())
        return DatosDeConcrecion(**extra)

    def concretar(self, cantidades=None, actor=None, cosecha=None, **extra):
        return cosechas.concretar_cosecha(actor or self.e.capataz, (cosecha or self.cosecha).pk, self.datos(cantidades, **extra))

    def cosechando(self, plantas, **extra):
        """Concreta cosechando `plantas` del lote en su único sector."""
        return self.concretar({(self.lote, self.sector): plantas}, **extra)

    def lote_en_dos_sectores(self, en_uno=60, en_otro=40):
        """Un lote de `en_uno + en_otro` plantas repartido en el sector de Maduración y en otro (como `test_prod_reg_mrm`). Devuelve `(lote, otro sector)`."""
        lote = lote_maduro(self.e, en_uno + en_otro)
        propio = self.sector
        otro = crear_sector(self.e.invernadero, nombre="Maduración 2", tipo="maduracion", agujeros=100)
        ocupacion = OcupacionSector.objects.get(lote=lote, sector=propio, cant_agujeros_ocupados__gt=0)
        OcupacionSector.objects.filter(pk=ocupacion.pk).update(cant_agujeros_ocupados=en_uno)
        OcupacionSector.objects.create(orden_id=ocupacion.orden_id, sector=otro, lote=lote, cant_agujeros_planificados=en_otro, cant_agujeros_ocupados=en_otro)
        return lote, otro

    def releer(self, modelo, pk):
        return modelo.objects.get(pk=pk)


class PropuestaPorSectorTests(TestCase):
    """Lista de tecnología 7a: el reparto de la propuesta, de tabla."""

    def test_regla_7a_se_reparte_en_proporcion_a_los_agujeros_ocupados(self):
        """Cuota proporcional exacta: 30 plantas entre sectores con 60 y 40 agujeros ocupados: 18 y 12."""
        self.assertEqual(cosechas.propuesta_por_sector(30, [(1, 60), (2, 40)]), {1: 18, 2: 12})

    def test_regla_7a_las_unidades_restantes_van_al_mayor_resto(self):
        """Método del resto mayor: 10 entre 60, 30 y 10: cuotas 6, 3, 1 exactas; 2 entre 1, 1, 1: cuotas 0 y restos iguales: las restantes van de a una a los primeros."""
        self.assertEqual(cosechas.propuesta_por_sector(10, [(1, 60), (2, 30), (3, 10)]), {1: 6, 2: 3, 3: 1})
        self.assertEqual(cosechas.propuesta_por_sector(2, [(1, 1), (2, 1), (3, 1)]), {1: 1, 2: 1, 3: 0})

    def test_regla_7a_con_empate_gana_el_sector_con_mas_agujeros_y_despues_el_primero(self):
        """Empate de resto: el de más agujeros ocupados y, si sigue, el primero de la lista: 7 entre 5 y 5 da 4 y 3; 5 entre 3, 3 y 4 favorece al de 4."""
        self.assertEqual(cosechas.propuesta_por_sector(7, [(10, 5), (20, 5)]), {10: 4, 20: 3})
        self.assertEqual(cosechas.propuesta_por_sector(5, [(1, 3), (2, 3), (3, 4)]), {1: 2, 2: 1, 3: 2})

    def test_regla_7a_si_lo_reservado_alcanza_o_supera_a_los_agujeros_cada_sector_propone_los_suyos(self):
        """Con reservado ≥ ocupado total, la propuesta es lo ocupado de cada sector."""
        self.assertEqual(cosechas.propuesta_por_sector(100, [(1, 60), (2, 40)]), {1: 60, 2: 40})
        self.assertEqual(cosechas.propuesta_por_sector(0, [(1, 60)]), {1: 0})


class LecturaDeConcrecionTests(Base):
    def test_regla_la_ficha_propone_la_fecha_de_hoy_y_la_cantidad_por_sector(self):
        """Paso 4: la variedad, el contrato y la fecha de entrega, y para cada lote la cantidad reservada y sus sectores con los agujeros que ocupa
        y la cantidad propuesta (la reservada repartida)."""
        lote, otro = self.lote_en_dos_sectores()
        cosecha_manual(self.e, [(lote, 30)], dias=1)
        ficha = cosechas.datos_de_concrecion(self.e.capataz, self.cosecha.pk)
        self.assertEqual((ficha.hoy, ficha.contrato, ficha.fecha_entrega), (HOY, self.venta.codigo, self.venta.fecha_pactada_venta))
        self.assertEqual([(l.lote_id, l.reservada) for l in ficha.lotes], [(self.lote.pk, 30)])
        self.assertEqual([(s.sector_id, s.ocupados, s.propuesta) for s in ficha.lotes[0].sectores], [(self.sector.pk, 100, 30)])

    def test_regla_la_propuesta_de_un_lote_en_dos_sectores_se_reparte_por_resto_mayor(self):
        """7a con datos reales: 30 reservadas de un lote que ocupa 60 y 40 agujeros: 18 y 12."""
        lote, otro = self.lote_en_dos_sectores()
        cosecha = cosecha_manual(self.e, [(lote, 30)], dias=1)
        ficha = cosechas.datos_de_concrecion(self.e.capataz, cosecha.pk)
        self.assertEqual(sorted((s.sector_id, s.propuesta) for s in ficha.lotes[0].sectores), sorted([(self.sector.pk, 18), (otro.pk, 12)]))

    def test_regla_solo_el_capataz_asignado_concreta(self):
        """Regla «Quién»: otro Capataz, el Agrónomo, el Gerente, el Vendedor y un Capataz con la cuenta inactiva reciben `PermissionDenied` (leer y concretar)."""
        ajeno = crear_capataz_activo(email="ajeno@infoponia.com")
        for actor in (ajeno, self.e.agronomo, crear_gerente(), self.e.vendedor):
            with self.subTest(actor=actor.email):
                with self.assertRaises(PermissionDenied):
                    cosechas.datos_de_concrecion(actor, self.cosecha.pk)
                with self.assertRaises(PermissionDenied):
                    self.cosechando(10, actor=actor)
        type(self.e.capataz).objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.cosechando(10)
        self.assertEqual(self.releer(Cosecha, self.cosecha.pk).estado_orden, "a_realizar")


class PostcondicionesTests(Base):
    def test_post_a_la_orden_pasa_a_concretada_con_la_fecha_de_resolucion_y_la_de_cosecha(self):
        """a: «concretada», `fecha_resolucion_orden` = hoy y `fecha_cosecha` = la efectiva."""
        ayer = HOY - timedelta(days=1)
        Cosecha.objects.filter(pk=self.cosecha.pk).update(fecha_creacion_orden=ayer - timedelta(days=1))
        self.cosechando(30, fecha_efectiva=ayer)
        c = self.releer(Cosecha, self.cosecha.pk)
        self.assertEqual((c.estado_orden, c.fecha_resolucion_orden, c.fecha_cosecha), ("concretada", HOY, ayer))

    def test_post_b_la_linea_de_reserva_queda_con_su_cantidad_cosechada(self):
        """b: cada línea de lote queda con `cantidad_cosechada` (incluido 0)."""
        self.cosechando(25)
        self.assertEqual(list(DetalleReserva.objects.filter(reserva__cosecha=self.cosecha).values_list("cantidad_reservada", "cantidad_cosechada")), [(30, 25)])

    def test_post_c_baja_la_cantidad_y_el_costo_del_lote_con_el_costo_por_planta_de_antes(self):
        """c: el lote baja lo cosechado (30) y su costo en cantidad × costo por planta (1,00 → 30,00)."""
        self.cosechando(30)
        lote = self.releer(Lote, self.lote.pk)
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado, lote.estado_lote), (70, Decimal("70.00"), "activo"))

    def test_post_c_un_lote_que_llega_a_cero_queda_finalizado(self):
        """c: «finalizado» cuando la cantidad actual llega a 0 (y costo 0); la ocupación conserva su lote."""
        cosecha = cosecha_manual(self.e, [(self.lote, 70)], dias=1)
        self.cosechando(30)
        self.concretar({(self.lote, self.sector): 70}, cosecha=cosecha)
        lote = self.releer(Lote, self.lote.pk)
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado, lote.estado_lote), (0, Decimal("0.00"), "finalizado"))
        self.assertTrue(OcupacionSector.objects.filter(lote=lote, cant_agujeros_ocupados=0).exists())

    def test_post_d_libera_los_agujeros_de_cada_sector_cosechado(self):
        """d: cada sector libera tantos agujeros como plantas se cosecharon ahí (los agujeros disponibles suben igual)."""
        lote, otro = self.lote_en_dos_sectores()
        cosecha = cosecha_manual(self.e, [(lote, 30)], dias=1)
        self.concretar({(lote, self.sector): 10, (lote, otro): 20}, cosecha=cosecha)
        ocupados = {o.sector_id: o.cant_agujeros_ocupados for o in OcupacionSector.objects.filter(lote=lote, cant_agujeros_ocupados__gt=0)}
        self.assertEqual(ocupados, {self.sector.pk: 50, otro.pk: 20})

    def test_post_e_registra_la_salida_por_cosecha_con_la_cosecha_como_origen(self):
        """e: un movimiento `salida_por_cosecha` por lote con cantidad cosechada > 0, con la fecha efectiva y el costo de antes."""
        self.cosechando(30)
        m = MovimientoStock.objects.get(tipo_movimiento="salida_por_cosecha")
        self.assertEqual((m.cantidad, m.lote_id, m.origen_id, m.costo_unitario), (30, self.lote.pk, self.cosecha.pk, Decimal("1.0000")))

    def test_post_g_un_registro_de_bitacora_por_lote_tambien_el_que_rindio_cero(self):
        """g y R152: un registro `cosecha` por cada lote de la orden, con el Capataz como responsable, la etapa del lote y el invernadero."""
        otro = lote_maduro(self.e, 20)
        cosecha = cosecha_manual(self.e, [(self.lote, 10), (otro, 10)], dias=1)
        self.concretar({(self.lote, self.sector): 10, (otro, self.sector): 0}, cosecha=cosecha)
        registros = Bitacora.objects.filter(cosecha=cosecha, tipo_evento="cosecha")
        self.assertEqual(sorted(r.lote_id for r in registros), sorted([self.lote.pk, otro.pk]))
        self.assertEqual({r.responsable_id for r in registros}, {self.e.capataz.pk})
        self.assertEqual(MovimientoStock.objects.filter(tipo_movimiento="salida_por_cosecha").count(), 1)

    def test_post_h_con_contrato_la_reserva_pasa_a_lista_para_entrega(self):
        """h: con contrato y algo cubierto, «lista para entrega»."""
        self.cosechando(30)
        self.assertEqual(self.releer(ReservaStock, ReservaStock.objects.get(cosecha=self.cosecha).pk).estado_reserva, "lista_para_entrega")

    def test_post_h_si_no_se_cosecho_nada_la_reserva_se_libera_y_todo_es_faltante(self):
        """h: con la cantidad cubierta total en 0, «liberada»; todo lo reservado (30) es faltante y, si no hay stock para cubrirlo (las 30 plantas se perdieron y el
        resto del lote está reservado), sigue el camino: la venta queda pendiente."""
        cosecha_manual(self.e, [(self.lote, 70)], dias=1)  # y 30 se pierden: el lote queda sin stock libre
        resultado = self.concretar({(self.lote, self.sector): 0}, perdidas=((self.lote.pk, self.sector.pk, 30),), causas=((self.lote.pk, "plaga", ""),))
        self.assertEqual(resultado.reserva.estado_reserva, "liberada")
        self.assertEqual(resultado.faltante, 30)
        self.assertEqual(self.releer(CompraVenta, self.venta.pk).estado_venta, "pendiente_decision")

    def test_post_i_con_contrato_el_excedente_ingresa_a_la_camara_con_el_costo_de_antes(self):
        """i y 10b: lo que sobra de la reserva (40 − 30 = 10) es una partida `excedente_de_cosecha` «disponible», con el costo por planta de antes,
        fecha de ingreso la efectiva y fecha límite = cosecha + postcosecha; un `ingreso_a_camara` originado en la cosecha."""
        resultado = self.cosechando(40)
        partida = StockCosechado.objects.get()
        self.assertEqual(
            (partida.cantidad_ingreso_cosechado, partida.motivo_cosechado, partida.estado_stock_cosechado, partida.costo_unitario_cosechado, partida.fecha_ingreso, partida.lote_id),
            (10, "excedente_de_cosecha", "disponible", Decimal("1.0000"), HOY, self.lote.pk),
        )
        self.assertEqual(partida.fecha_limite, HOY + timedelta(days=self.e.variedad.duracion_post_cosecha))
        m = MovimientoStock.objects.get(tipo_movimiento="ingreso_a_camara")
        self.assertEqual((m.partida_id, m.cantidad, m.origen_id), (partida.pk, 10, self.cosecha.pk))
        self.assertEqual([p.pk for p in resultado.partidas], [partida.pk])

    def test_post_j_sin_contrato_todo_lo_cosechado_ingresa_a_la_camara_y_la_reserva_se_libera(self):
        """j y 4a: la reserva «liberada»; por cada lote con cantidad cosechada > 0, una partida `cosecha_del_agronomo` por lo cosechado."""
        sin = cosecha_manual(self.e, [(self.lote, 40)], dias=1)
        self.concretar({(self.lote, self.sector): 40}, cosecha=sin)
        self.assertEqual(self.releer(ReservaStock, ReservaStock.objects.get(cosecha=sin).pk).estado_reserva, "liberada")
        partida = StockCosechado.objects.get()
        self.assertEqual((partida.cantidad_ingreso_cosechado, partida.motivo_cosechado, partida.costo_unitario_cosechado), (40, "cosecha_del_agronomo", Decimal("1.0000")))

    def test_post_j_un_lote_que_rindio_cero_no_deja_partida(self):
        """j: solo los lotes con cantidad cosechada mayor que 0 crean partida."""
        sin = cosecha_manual(self.e, [(self.lote, 40)], dias=1)
        self.concretar({(self.lote, self.sector): 0}, cosecha=sin)
        self.assertFalse(StockCosechado.objects.exists())

    def test_regla_la_partida_tiene_el_costo_de_antes_de_la_cosecha_no_el_del_lote_de_despues(self):
        """Regla «Partida de cámara» y D-64 punto 3: el lote queda finalizado con costo 0, pero la partida lleva el costo por planta de antes."""
        entero = lote_maduro(self.e, 100)
        sin = cosecha_manual(self.e, [(entero, 100)], dias=1)
        self.concretar({(entero, self.sector): 100}, cosecha=sin)
        self.assertEqual(StockCosechado.objects.get().costo_unitario_cosechado, Decimal("1.0000"))
        self.assertEqual(self.releer(Lote, entero.pk).costo_acumulado, Decimal("0.00"))

    def test_post_m_las_plantas_perdidas_son_merma_del_lote_y_las_no_declaradas_quedan_libres(self):
        """m y 10a: la merma por lote (causa y descripción del Capataz, por sector), cuenta para el umbral (con etapa); las no cosechadas que no se declaran
        perdidas quedan en el lote como stock libre. 30 reservadas, 20 cosechadas, 4 perdidas: quedan 76 en el lote y 6 libres de la reserva."""
        resultado = self.concretar(
            {(self.lote, self.sector): 20}, perdidas=((self.lote.pk, self.sector.pk, 4),), causas=((self.lote.pk, "plaga", "Hongo en un borde"),)
        )
        merma = Merma.objects.get()
        self.assertEqual((merma.cant_merma, merma.causa, merma.lote_id, merma.etapa_id), (4, "plaga", self.lote.pk, self.lote.etapa_id))
        self.assertIn("Hongo en un borde", merma.descripcion_evento)
        self.assertEqual(self.releer(Lote, self.lote.pk).cantidad_actual, 76)
        self.assertEqual([m.pk for m in resultado.mermas], [merma.pk])
        self.assertTrue(MovimientoStock.objects.filter(tipo_movimiento="salida_por_merma", cantidad=4).exists())

    def test_post_o_se_avisa_al_agronomo_con_lo_reservado_lo_cosechado_y_lo_perdido(self):
        """o: «Cosecha OT-… concretada» con, por lote, lo reservado, lo cosechado y lo perdido."""
        self.concretar({(self.lote, self.sector): 20}, perdidas=((self.lote.pk, self.sector.pk, 4),), causas=((self.lote.pk, "plaga", ""),))
        aviso = Notificacion.objects.get(destinatario=self.e.agronomo, titulo=f"Cosecha {self.cosecha.codigo} concretada")
        for texto in (self.lote.codigo, "30", "20", "4"):
            self.assertIn(texto, aviso.detalle)

    def test_post_o_con_contrato_y_faltante_o_excedente_se_avisa_tambien_al_vendedor(self):
        """o: con contrato y faltante («Cosecha de CV-…: faltaron N») o excedente, también al Vendedor; sin ninguno de los dos, no."""
        self.cosechando(30)
        self.assertFalse(Notificacion.objects.filter(destinatario=self.e.vendedor).exists())
        otra = cosecha_manual(self.e, [(self.lote, 20)], detalle_=self.detalle, dias=1)
        self.concretar({(self.lote, self.sector): 15}, cosecha=otra)
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor)
        self.assertTrue(aviso.titulo.startswith(f"Cosecha de {self.venta.codigo}"))
        self.assertIn("5", aviso.detalle)

    def test_post_p_q_y_r_un_solo_registro_de_auditoria_con_todo_lo_tocado(self):
        """p, q, r y D-36: UN registro `concrecion_cosecha` del Capataz con la orden, la reserva y sus líneas, el lote, las ocupaciones, los movimientos,
        los registros de bitácora y las partidas."""
        antes = RegistroAuditoria.objects.count()
        self.cosechando(40)
        self.assertEqual(RegistroAuditoria.objects.count(), antes + 1)
        registro = RegistroAuditoria.objects.latest("pk")
        self.assertEqual((registro.accion, registro.usuario_id), ("concrecion_cosecha", self.e.capataz.pk))
        textos = [a["texto"] for a in registro.afectados]
        for esperado in (self.cosecha.codigo, self.lote.codigo, "Reserva #", "Línea #", "Ocupación #", "Movimiento de stock #", "Bitácora #", "P-"):
            self.assertTrue(any(t.startswith(esperado) or esperado in t for t in textos), esperado)


class ExtensionesTests(Base):
    def test_ext_6a_una_fecha_efectiva_posterior_a_hoy_se_rechaza(self):
        """6a: `fecha_futura`."""
        self.assertEqual(codigos(self, lambda: self.cosechando(10, fecha_efectiva=en(1)), "fecha_efectiva"), ["fecha_futura"])

    def test_ext_6b_una_fecha_anterior_a_la_creacion_de_la_orden_se_rechaza_con_esa_fecha(self):
        """6b: `fecha_antes_de_creacion` y el mensaje informa la fecha de creación; la de creación misma vale."""
        Cosecha.objects.filter(pk=self.cosecha.pk).update(fecha_creacion_orden=en(-2))
        with self.assertRaises(ValidationError) as rechazo:
            self.cosechando(10, fecha_efectiva=en(-3))
        error = rechazo.exception.error_dict["fecha_efectiva"][0]
        self.assertEqual(error.code, "fecha_antes_de_creacion")
        self.assertIn(f"{en(-2):%d/%m/%Y}", error.message)
        self.cosechando(10, fecha_efectiva=en(-2))

    def test_ext_8a_un_sector_que_supera_los_agujeros_del_lote_en_el_se_rechaza(self):
        """8a: `supera_sector` con los agujeros ocupados por el lote en ese sector (100)."""
        with self.assertRaises(ValidationError) as rechazo:
            self.cosechando(101)
        error = rechazo.exception.error_dict[f"cantidad_{self.lote.pk}_{self.sector.pk}"][0]
        self.assertEqual(error.code, "supera_sector")
        self.assertIn("100", error.message)
        self.assertEqual(self.releer(Cosecha, self.cosecha.pk).estado_orden, "a_realizar")

    def test_ext_8b_el_total_del_lote_no_puede_tomar_plantas_reservadas_por_otras_ordenes(self):
        """8b: máximo = lo reservado en esta línea (30) + el stock libre del lote (100 − 30 de esta − 40 de otra = 30) = 60, es decir la cantidad actual menos
        lo que reservan las otras órdenes: 61 supera y 60 deja justo lo reservado por la otra."""
        cosecha_manual(self.e, [(self.lote, 40)], dias=1)
        with self.assertRaises(ValidationError) as rechazo:
            self.cosechando(61)
        error = rechazo.exception.error_dict[f"lote_{self.lote.pk}"][0]
        self.assertEqual(error.code, "supera_maximo")
        self.assertIn("60", error.message)
        self.cosechando(60)

    def test_ext_10a_3a_las_plantas_perdidas_no_pueden_superar_las_no_cosechadas(self):
        """10a.3a: perdidas por lote ≤ reservada − cosechada (30 − 25 = 5): 6 es `supera_no_cosechadas`."""
        self.assertEqual(
            codigos(
                self,
                lambda: self.concretar({(self.lote, self.sector): 25}, perdidas=((self.lote.pk, self.sector.pk, 6),), causas=((self.lote.pk, "plaga", ""),)),
                f"perdidas_{self.lote.pk}",
            ),
            ["supera_no_cosechadas"],
        )

    def test_ext_10a_3a_las_perdidas_por_sector_se_validan_contra_lo_que_queda_despues_de_la_cosecha(self):
        """10a.3a: en un sector, las perdidas no superan lo que queda del lote ahí **después** de cosechar: un lote con 3 agujeros ocupados en un sector y 27 en
        otro, 30 reservadas; se cosechan 0 y 22 (8 no cosechadas): perder 4 del sector de 3 supera lo que queda ahí (`supera_sector`), aunque 4 ≤ 8."""
        lote, otro = self.lote_en_dos_sectores(en_uno=3, en_otro=27)
        cosecha = cosecha_manual(self.e, [(lote, 30)], dias=1)
        cantidades = {(lote, self.sector): 0, (lote, otro): 22}
        resultado = codigos(
            self,
            lambda: self.concretar(cantidades, cosecha=cosecha, perdidas=((lote.pk, self.sector.pk, 4),), causas=((lote.pk, "plaga", ""),)),
            f"perdidas_{lote.pk}_{self.sector.pk}",
        )
        self.assertEqual(resultado, ["supera_sector"])

    def test_ext_10a_3b_las_plantas_perdidas_sin_causa_se_rechazan(self):
        """10a.3b: `causa_obligatoria` en el campo de la causa del lote; con una causa de lote en pie se registra."""
        datos = dict(perdidas=((self.lote.pk, self.sector.pk, 2),))
        self.assertEqual(codigos(self, lambda: self.concretar({(self.lote, self.sector): 20}, **datos), f"causa_{self.lote.pk}"), ["causa_obligatoria"])
        self.assertEqual(
            codigos(self, lambda: self.concretar({(self.lote, self.sector): 20}, causas=((self.lote.pk, "dano_en_camara", ""),), **datos), f"causa_{self.lote.pk}"),
            ["causa_invalida"],
        )

    def test_ext_12a_el_resumen_permite_corregir_y_no_escribe(self):
        """12a: `verificar_concrecion` devuelve, por lote, reservado, cosechado, excedente, no cosechadas, perdidas y lo que queda libre, y el destino,
        sin escribir nada."""
        antes = (RegistroAuditoria.objects.count(), MovimientoStock.objects.count())
        datos = self.datos({(self.lote, self.sector): 25}, perdidas=((self.lote.pk, self.sector.pk, 2),), causas=((self.lote.pk, "plaga", ""),))
        resumen = cosechas.verificar_concrecion(self.e.capataz, self.cosecha.pk, datos)
        fila = resumen.lotes[0]
        self.assertEqual(
            (fila.lote_id, fila.reservada, fila.cosechada, fila.excedente, fila.no_cosechadas, fila.perdidas, fila.quedan_libres), (self.lote.pk, 30, 25, 0, 5, 2, 3)
        )
        self.assertEqual((resumen.total_reservado, resumen.total_cosechado, resumen.errores), (30, 25, {}))
        self.assertTrue(any("Faltan 5" in t for t in resumen.destino))
        self.assertEqual((RegistroAuditoria.objects.count(), MovimientoStock.objects.count()), antes)

    def test_ext_4a_sin_contrato_el_resumen_dice_que_todo_ingresa_a_la_camara(self):
        """4a: el destino de lo cosechado de una cosecha sin contrato: «todo ingresará a la cámara»."""
        sin = cosecha_manual(self.e, [(self.lote, 40)], dias=1)
        resumen = cosechas.verificar_concrecion(self.e.capataz, sin.pk, self.datos({(self.lote, self.sector): 40}))
        self.assertTrue(any("cámara" in t for t in resumen.destino))

    def test_ext_13b_una_orden_que_ya_no_esta_a_realizar_no_se_concreta(self):
        """13b: `orden_no_a_realizar` con el estado actual (concretada, o cancelada por el Agrónomo mientras se cargaba); dos veces tampoco."""
        self.cosechando(30)
        with self.assertRaises(ValidationError) as rechazo:
            self.cosechando(30)
        error = next(e for lista in rechazo.exception.error_dict.values() for e in lista)
        self.assertEqual(error.code, "orden_no_a_realizar")
        self.assertIn("concretada", error.message)
        self.assertEqual(MovimientoStock.objects.filter(tipo_movimiento="salida_por_cosecha").count(), 1)

    def test_ext_13c_si_cambio_el_stock_libre_el_nuevo_maximo_se_informa(self):
        """13c: entre las verificaciones y la confirmación otra reserva tomó stock libre: `supera_maximo` con el nuevo máximo; nada cambia."""
        datos = self.datos({(self.lote, self.sector): 90})
        cosecha_manual(self.e, [(self.lote, 70)], dias=1)  # el máximo baja a 30
        with self.assertRaises(ValidationError) as rechazo:
            cosechas.concretar_cosecha(self.e.capataz, self.cosecha.pk, datos)
        self.assertEqual(rechazo.exception.error_dict[f"lote_{self.lote.pk}"][0].code, "supera_maximo")
        self.assertEqual(self.releer(Lote, self.lote.pk).cantidad_actual, 100)


class FaltanteTests(Base):
    """Extensión 13a y postcondición l: el faltante se cubre con PROD-ASG-STK (`origen_cosecha="encadenada"`); lo que no, sigue el camino de faltante.
    Las plantas no cosechadas ni perdidas quedan en el lote como stock libre y PUEDEN volver a reservarse (regla «Plantas no cosechadas»): por eso los casos de
    cobertura parcial y nula pierden las 10 plantas faltantes y reservan el resto del lote con otra cosecha."""

    def sin_stock_en_el_lote_propio(self):
        """Otra cosecha reserva 70 del lote de 100: tras cosechar 20 y perder 10 de las 30 reservadas, el lote queda con 70, todas reservadas."""
        cosecha_manual(self.e, [(self.lote, 70)], dias=1)

    def cosechando_con_perdidas(self, cosecha=None):
        """Cosecha 20 de las 30 reservadas del lote y declara 10 perdidas por plaga (el faltante sigue siendo 10)."""
        return self.concretar(
            {(self.lote, self.sector): 20}, cosecha=cosecha, perdidas=((self.lote.pk, self.sector.pk, 10),), causas=((self.lote.pk, "plaga", ""),)
        )

    def test_ext_13a_con_cobertura_total_otro_lote_cubre_el_faltante_y_se_programa_una_cosecha_encadenada(self):
        """13a con cobertura total: se cosechan 20 de 30 (faltan 10); otro lote que entró antes a Maduración (se asigna primero) los cubre: reserva nueva y
        cosecha «Encadenada»; el detalle y la venta siguen abiertos; la reserva original queda «lista para entrega»."""
        otro = lote_maduro(self.e, 100, entrada=HOY - timedelta(days=1))
        resultado = self.cosechando(20)
        self.assertEqual((resultado.faltante, resultado.asignacion.cubierta, resultado.asignacion.sin_cubrir), (10, 10, 0))
        nueva = Cosecha.objects.exclude(pk=self.cosecha.pk).get()
        self.assertEqual((nueva.origen_cosecha, nueva.agronomo_id), ("encadenada", None))
        self.assertEqual(list(DetalleReserva.objects.filter(reserva__cosecha=nueva).values_list("lote_id", "cantidad_reservada")), [(otro.pk, 10)])
        self.assertEqual((self.releer(DetalleVenta, self.detalle.pk).estado_detalle_venta, self.releer(CompraVenta, self.venta.pk).estado_venta), ("abierto", "abierta"))
        self.assertEqual(resultado.reserva.estado_reserva, "lista_para_entrega")

    def test_ext_13a_con_cobertura_parcial_la_venta_queda_pendiente_de_decision_del_cliente(self):
        """13a con cobertura parcial: `asignar` reserva lo que hay (4 plantas de otro lote) y lo no cubierto (6) sigue el camino de faltante: el detalle y la
        venta pasan a «pendiente de decisión del cliente» con la fecha de hoy; el Vendedor recibe el faltante."""
        self.sin_stock_en_el_lote_propio()
        lote_maduro(self.e, 4)
        resultado = self.cosechando_con_perdidas()
        self.assertEqual((resultado.faltante, resultado.asignacion.cubierta, resultado.asignacion.sin_cubrir), (10, 4, 6))
        detalle_ = self.releer(DetalleVenta, self.detalle.pk)
        self.assertEqual((detalle_.estado_detalle_venta, detalle_.fecha_pendiente_decision), ("pendiente_decision", HOY))
        self.assertEqual(self.releer(CompraVenta, self.venta.pk).estado_venta, "pendiente_decision")
        self.assertTrue(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo__startswith=f"Cosecha de {self.venta.codigo}").exists())

    def test_ext_13a_con_cobertura_nula_todo_el_faltante_va_al_camino(self):
        """13a con cobertura nula: sin ningún otro stock, el detalle y la venta pasan a «pendiente de decisión del cliente»."""
        self.sin_stock_en_el_lote_propio()
        resultado = self.cosechando_con_perdidas()
        self.assertEqual((resultado.faltante, resultado.asignacion.cubierta, resultado.asignacion.sin_cubrir), (10, 0, 10))
        self.assertEqual(self.releer(DetalleVenta, self.detalle.pk).estado_detalle_venta, "pendiente_decision")

    def test_ext_13a_en_un_suministro_el_periodo_queda_con_cantidad_sin_cubrir_y_no_cambia_de_estado(self):
        """13a en un suministro: no hay pendiente de decisión; el período queda con lo que falta (la pre-reserva diaria lo vuelve a intentar) y se
        notifica el faltante al Vendedor."""
        det = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=30, primera_en_dias=8)
        p = periodo(det, en(8))
        c = cosecha_manual(self.e, [(self.lote, 30)], periodo_=p, dias=1)
        cosecha_manual(self.e, [(self.lote, 40)], dias=1)  # el lote de 100: 30 + 30 + 40
        resultado = self.cosechando_con_perdidas(cosecha=c)
        self.assertEqual((resultado.faltante, resultado.asignacion.sin_cubrir), (10, 10))
        self.assertEqual(self.releer(DetalleSuministro, det.pk).estado_detalle_suministro, "vigente")
        self.assertEqual(stock_maduro.cantidad_sin_cubrir(periodo(self.releer(DetalleSuministro, det.pk), en(8))), 10)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.e.vendedor).exists())

    def test_regla_el_excedente_de_un_lote_cubre_el_faltante_de_otro(self):
        """El excedente y el faltante en la misma cosecha: el lote A rinde 10 de 20 reservadas (faltan 10) y el B, 20 de 10 (sobran 10, a la cámara); al
        intentar cubrir el faltante, `asignar` toma antes la partida de cámara (prioridad de PROD-ASG-STK): queda cubierto, sin faltante."""
        b = lote_maduro(self.e, 50)
        contrato = detalle(compra_venta(self.e, dias=5), self.e.variedad, 50)  # entrega antes del vencimiento de la partida
        c = cosecha_manual(self.e, [(self.lote, 20), (b, 10)], detalle_=contrato, dias=1)
        resultado = self.concretar({(self.lote, self.sector): 10, (b, self.sector): 20}, cosecha=c)
        self.assertEqual((resultado.faltante, resultado.asignacion.cubierta, resultado.asignacion.sin_cubrir), (10, 10, 0))
        partida = StockCosechado.objects.get()
        self.assertEqual(partida.lote_id, b.pk)
        self.assertEqual(DetalleReserva.objects.filter(partida=partida, reserva__estado_reserva="lista_para_entrega").count(), 1)
        self.assertEqual(self.releer(DetalleVenta, contrato.pk).estado_detalle_venta, "abierto")

    def test_regla_una_cosecha_sin_contrato_no_tiene_faltante(self):
        """Sin contrato no hay faltante ni camino: lo que se cosecha de menos queda en el lote."""
        sin = cosecha_manual(self.e, [(self.lote, 40)], dias=1)
        resultado = self.concretar({(self.lote, self.sector): 10}, cosecha=sin)
        self.assertEqual((resultado.faltante, resultado.asignacion), (0, None))
        self.assertEqual(self.releer(DetalleVenta, self.detalle.pk).estado_detalle_venta, "abierto")
