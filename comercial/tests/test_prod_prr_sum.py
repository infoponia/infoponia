# Pruebas de PROD-PRR-SUM, Pre-reservar Período de Suministro (COM-03b, paso 4; docs/casos_de_uso/produccion/pre_reserva.md): el paso diario 40
# (`pre_reservar_suministros(hoy)`), la alerta «período sin cobertura completa» (MD-133, D-63) y su enlace en la campana (D-62). Una prueba por
# regla, postcondición y extensión; las que escriben verifican al final los invariantes de reservas y de suministros. La concurrencia está en
# `test_pre_reserva_concurrencia.py`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), en `comercial/servicios/pre_reserva.py`:
#   - `pre_reservar_suministros(hoy) -> ResumenDePaso(procesados, creados, resueltos, detalle)` (D-56): ``procesados`` = períodos intentados,
#     ``creados`` = reservas creadas, ``resueltos`` = alertas resueltas (las que cubre y las que pasaron su fecha) y ``detalle`` =
#     «N períodos siguen sin cobertura completa». Nunca lee la fecha por su cuenta. Un período, una transacción.
#   - `enlaces_de_alertas_de_periodo(usuario, alertas) -> dict[int, Enlace]` (D-62): para el Gerente, la ficha del suministro con ``#calendario``;
#     para el Agrónomo, la ficha del invernadero de la alerta; para otros roles, nada. El texto: «Faltan N plantas para el dd/mm»
#     («Falta 1 planta…» con una). Una consulta para toda la lista.
#   - La alerta: tipo `comercial_periodo_sin_cobertura` (`AGRONOMO_O_GERENTE`, `ADVERTENCIA`, `ESTADO`, origen `DETALLE_SUMINISTRO`), clave
#     ``periodo:{id del detalle}:{aaaa-mm-dd}``, descripción «Período sin cobertura completa · {variedad} · {cliente} · dd/mm» y su
#     `AlertaComercial` (detalle, fecha del período, cantidad sin cubrir). Invernadero (D-63, punto 3): el de la primera reserva del período
#     (la de menor id) o, sin reservas, el activo de menor id del Vendedor. Notificación al Vendedor («Período sin cobertura completa») solo la
#     primera vez. Sin invernadero activo del Vendedor (D-63, punto 4): sin alerta; se notifica al Vendedor y al Gerente, una sola vez.
#   - Auditoría: acción `pre_reserva_periodo`, sin usuario (origen InfoPonia, D-27), un registro por período en el que CAMBIÓ algo (reservas
#     creadas, alerta creada o resuelta); afectados: el detalle primero; `datos`: ``fecha_periodo`` (dd/mm/aaaa), ``cantidad_sin_cubrir``,
#     ``alertas_creadas`` y ``alertas_resueltas`` (textos con el número).
#   - Registro en `ComercialConfig.ready()`: el tipo, el enlace (`registrar_enlace_de_alerta`) y el paso diario `pre_reservar_suministros`
#     (orden 40, «Pre-reservar suministros»).
#   - D-64 punto 8 (COM-04a, decisión del estudiante del 24/11/2026): la pre-reserva también retoma los períodos de un detalle «finalizado»
#     cuya fecha no supera `fecha_fin_detalle` (todavía se deben); los posteriores no.

from datetime import timedelta
from unittest import mock

from django.apps import apps
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from comercial.models import AlertaComercial, Cliente, DetalleReserva, DetalleSuministro, ReservaStock, Suministro
from comercial.tests.fabricas import (
    alerta_de_periodo,
    compra_venta,
    detalle,
    detalle_suministro,
    direccion_de_cliente,
    escenario_comercial,
    partida,
    reserva,
    segundo_invernadero,
    suministro,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_suministros,
)
from core.models import ROL_INFOPONIA, Notificacion, RegistroAuditoria
from core.procesos import ResumenDePaso, pasos_diarios
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.alertas import Clase, Destinatario, Origen, tipo_de_alerta
from maestros.extensiones import Enlace, enlaces_registrados
from maestros.models import Alerta, Invernadero
from maestros.servicios.invernaderos import items_de_campana
from produccion.models import Cosecha
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
TIPO = "comercial_periodo_sin_cobertura"


def en(dias):
    """La fecha de dentro de ``dias`` días."""
    return HOY + timedelta(days=dias)


class BaseDePrereserva(ConDatosDeInventario, TestCase):
    """Un contrato de 6 meses con un detalle de 30 plantas cada 7 días (períodos a los 3, 10, 17… días; la ventana de 14 días cubre los dos
    primeros), sin reservas, y un lote en Maduración de ``STOCK`` plantas (con 0, ninguno)."""

    STOCK = 100

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, self.STOCK) if self.STOCK else None
        self.gerente = crear_gerente()
        self.s = suministro(self.e, duracion=6)
        self.d = detalle_suministro(self.s, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=3)
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_suministros)

    def correr(self, hoy=None):
        """Corre el paso diario 40 para ``hoy`` (por defecto, el de hoy)."""
        from comercial.servicios import pre_reserva

        return pre_reserva.pre_reservar_suministros(hoy or HOY)

    def reservas(self, detalle=None):
        """Las reservas del detalle (por defecto el del contrato), de la más vieja a la más nueva."""
        return list(ReservaStock.objects.filter(detalle_suministro=detalle or self.d).order_by("pk"))

    def fechas_reservadas(self, detalle=None):
        """Las fechas de entrega de las reservas del detalle, ordenadas y sin repetir."""
        return sorted({r.fecha_entrega_reserva for r in self.reservas(detalle)})

    def alertas(self):
        """Las alertas de período del contrato, por fecha del período."""
        return list(
            Alerta.objects.filter(tipo_alerta=TIPO, vinculo_comercial__detalle_suministro__suministro=self.s)
            .select_related("vinculo_comercial", "invernadero")
            .order_by("vinculo_comercial__fecha_periodo")
        )

    def otra_direccion(self):
        """Otra dirección activa del cliente."""
        return direccion_de_cliente(self.e.cliente).direccion

    def retener(self, cantidad):
        """Una compra-venta ajena que reserva ``cantidad`` plantas del lote (le saca stock libre) y la reserva que lo hace. El detalle pide 100: la
        reserva puede crecer hasta 100 sin romper el invariante."""
        venta = compra_venta(self.e)
        return reserva(detalle(venta, self.e.variedad, cantidad=100), [(self.lote, cantidad)])

    def reservar_en_total(self, reserva_ajena, cantidad):
        """Cambia lo que retiene la reserva ajena (sube o baja el stock libre del lote)."""
        DetalleReserva.objects.filter(reserva=reserva_ajena).update(cantidad_reservada=cantidad)


class FlujoPrincipalTests(BaseDePrereserva):
    """Postcondiciones a, b, e y f y el escenario principal."""

    def test_flujo_principal_reserva_los_periodos_de_la_ventana_y_solo_esos(self):
        """Pasos 2 a 4 y regla «Período a pre-reservar»: con la ventana a 14 días y períodos a los 3, 10 y 17, se reservan los dos primeros (30
        plantas cada uno) y el del día 17 queda para cuando entre en la ventana. El resumen del paso cuenta períodos y reservas."""
        resumen = self.correr()
        self.assertEqual(self.fechas_reservadas(), [en(3), en(10)])
        self.assertEqual(
            resumen, ResumenDePaso(procesados=2, creados=2, resueltos=0, detalle="0 períodos siguen sin cobertura completa")
        )

    def test_post_a_la_reserva_lleva_la_fecha_del_periodo_su_detalle_y_su_linea(self):
        """Postcondición a: cada reserva es del detalle, con `fecha_entrega_reserva` = la fecha del período, en el invernadero del lote, y una línea
        de lote por la cantidad del período."""
        self.correr()
        for reserva in self.reservas():
            self.assertEqual((reserva.detalle_suministro_id, reserva.detalle_venta_id, reserva.invernadero_id), (self.d.pk, None, self.e.invernadero.pk))
            (linea,) = reserva.lineas.all()
            self.assertEqual((linea.lote_id, linea.partida_id, linea.cantidad_reservada), (self.lote.pk, None, 30))

    def test_post_b_con_lineas_de_lote_se_crea_la_cosecha_con_prioridad_media(self):
        """Postcondición b y regla «Cosecha»: la reserva con líneas de lote queda «activa» con su cosecha «a realizar», prioridad «media», en el
        invernadero, con su Capataz."""
        self.correr()
        reservas = self.reservas()
        self.assertEqual({r.estado_reserva for r in reservas}, {"activa"})
        self.assertEqual(Cosecha.objects.count(), 2)
        for reserva in reservas:
            cosecha = Cosecha.objects.get(pk=reserva.cosecha_id)
            self.assertEqual((cosecha.estado_orden, cosecha.prioridad_orden, cosecha.invernadero_id), ("a_realizar", "media", self.e.invernadero.pk))

    def test_post_b_si_todo_sale_de_camara_la_reserva_queda_lista_para_entrega_sin_cosecha(self):
        """Postcondición b y regla 7 de 8.6: con una partida de cámara que cubre los dos períodos, las reservas quedan «lista para entrega», con
        su línea de partida y sin cosecha."""
        partida(self.lote, disponible=60)
        self.correr()
        reservas = self.reservas()
        self.assertEqual({r.estado_reserva for r in reservas}, {"lista_para_entrega"})
        self.assertTrue(all(r.lineas.get().partida_id is not None and r.cosecha_id is None for r in reservas))
        self.assertEqual(Cosecha.objects.count(), 0)

    def test_post_e_se_notifica_cada_cosecha_al_capataz_y_al_agronomo(self):
        """Postcondición e y paso 5: cada cosecha creada se notifica al Capataz del invernadero y al Agrónomo (dos cosechas, cuatro avisos)."""
        self.correr()
        avisos = Notificacion.objects.filter(destinatario__in=[self.e.capataz, self.e.agronomo])
        self.assertEqual(avisos.count(), 4)
        self.assertEqual(sorted({a.destinatario_id for a in avisos}), sorted([self.e.capataz.pk, self.e.agronomo.pk]))

    def test_post_f_un_registro_de_auditoria_por_periodo_con_origen_infoponia(self):
        """Postcondición f y D-27: un registro `pre_reserva_periodo` por período, sin usuario (rol «infoponia»), con el detalle entre los
        afectados (primero) y la fecha del período, la cantidad sin cubrir y las alertas en `datos`."""
        self.correr()
        registros = list(RegistroAuditoria.objects.filter(accion="pre_reserva_periodo").order_by("pk"))
        self.assertEqual(len(registros), 2)
        for registro, fecha in zip(registros, (en(3), en(10))):
            self.assertEqual((registro.usuario_id, registro.rol), (None, ROL_INFOPONIA))
            self.assertEqual(registro.afectados[0]["modelo"], "comercial.detallesuministro")
            self.assertEqual(registro.afectados[0]["id"], self.d.pk)
            self.assertEqual(
                (registro.detalle["datos"]["fecha_periodo"], registro.detalle["datos"]["cantidad_sin_cubrir"], registro.detalle["datos"]["alertas_creadas"]),
                (f"{fecha:%d/%m/%Y}", "0", "0"),
            )
            modelos = {a["modelo"] for a in registro.afectados}
            self.assertTrue({"comercial.reservastock", "comercial.detallereserva", "produccion.cosecha"} <= modelos)

    def test_ext_2a_sin_periodos_a_pre_reservar_no_cambia_nada(self):
        """Extensión 2a: el paso termina sin cambios (ni reservas, ni alertas, ni auditoría) y el resumen es cero."""
        DetalleSuministro.objects.filter(pk=self.d.pk).update(fecha_primer_entrega=en(100))
        resumen = self.correr()
        self.assertEqual(resumen, ResumenDePaso(0, 0, 0, "0 períodos siguen sin cobertura completa"))
        self.assertEqual((ReservaStock.objects.count(), Alerta.objects.count(), RegistroAuditoria.objects.filter(accion="pre_reserva_periodo").count()), (0, 0, 0))


class ReglaDelPeriodoTests(BaseDePrereserva):
    """Regla «Período a pre-reservar» y su orden."""

    def test_regla_no_toma_periodos_anteriores_a_hoy(self):
        """Regla «Período a pre-reservar»: con la primera entrega hace 5 días (períodos a los -5, 2, 9 y 16), el de hace 5 días no se toma; sí los
        de los días 2 y 9."""
        DetalleSuministro.objects.filter(pk=self.d.pk).update(fecha_primer_entrega=en(-5))
        self.correr()
        self.assertEqual(self.fechas_reservadas(), [en(2), en(9)])

    def test_regla_no_pasa_de_la_fecha_de_fin_del_contrato(self):
        """Regla «Período a pre-reservar»: un contrato que termina dentro de la ventana (un mes que empezó hace 24 días) solo pre-reserva el
        período que cae hasta su fecha de fin (día 3), no el del día 10."""
        corto = suministro(self.e, fecha_realizacion=HOY - timedelta(days=24), duracion=1)
        detalle = detalle_suministro(corto, self.e.variedad, direccion=self.otra_direccion(), cantidad=10, periodo=7, primera_en_dias=3)
        self.correr()
        self.assertEqual(self.fechas_reservadas(detalle), [en(3)])

    def test_regla_la_fecha_de_fin_del_detalle_corta_el_calendario(self):
        """Regla «Período a pre-reservar» (MD-131) y COM-RSC-SUM: un detalle vigente de un contrato con rescisión acordada, con
        `fecha_fin_detalle` = el día 3, no aporta períodos posteriores."""
        Suministro.objects.filter(pk=self.s.pk).update(
            motivo_rescision="otro", descripcion_rescision="x", fecha_acuerdo_rescision=HOY, fecha_registro_rescision=HOY,
            fecha_ultima_entrega_rescision=en(3),
        )
        DetalleSuministro.objects.filter(pk=self.d.pk).update(fecha_fin_detalle=en(3))
        self.correr()
        self.assertEqual(self.fechas_reservadas(), [en(3)])

    def test_regla_d64_8_un_detalle_finalizado_se_pre_reserva_hasta_su_fecha_de_fin(self):
        """D-64, punto 8 (COM-04a): el período con fecha ≤ `fecha_fin_detalle` de un detalle «finalizado» todavía se debe, así que la pre-reserva lo toma
        (los días 3 y 10); uno posterior (el día 17, fuera de la ventana de 14 días, o cualquiera después de la fecha de fin) no."""
        DetalleSuministro.objects.filter(pk=self.d.pk).update(estado_detalle_suministro="finalizado", fecha_fin_detalle=en(10))
        resumen = self.correr()
        self.assertEqual(resumen.procesados, 2)
        self.assertEqual(self.fechas_reservadas(), [en(3), en(10)])

    def test_regla_d64_8_un_periodo_posterior_a_la_fecha_de_fin_de_un_detalle_finalizado_no_se_toma(self):
        """Con `fecha_fin_detalle` en el día 3, el período del día 10 ya no se debe: no se pre-reserva."""
        DetalleSuministro.objects.filter(pk=self.d.pk).update(estado_detalle_suministro="finalizado", fecha_fin_detalle=en(3))
        self.correr()
        self.assertEqual(self.fechas_reservadas(), [en(3)])

    def test_regla_d64_8_el_periodo_de_un_detalle_terminado_que_pierde_su_reserva_se_vuelve_a_tomar(self):
        """D-64 punto 8: si la reserva de un período de un detalle terminado se libera (cosecha cancelada), el período vuelve a tener cantidad sin
        cubrir y la pre-reserva del día siguiente lo cubre de nuevo."""
        DetalleSuministro.objects.filter(pk=self.d.pk).update(estado_detalle_suministro="finalizado", fecha_fin_detalle=en(10))
        self.correr()
        ReservaStock.objects.filter(detalle_suministro=self.d, fecha_entrega_reserva=en(3)).update(estado_reserva="liberada")
        resumen = self.correr()
        self.assertEqual(resumen.procesados, 1)
        self.assertEqual(
            ReservaStock.objects.filter(detalle_suministro=self.d, fecha_entrega_reserva=en(3)).exclude(estado_reserva="liberada").count(), 1
        )

    def test_regla_un_suministro_que_no_esta_vigente_no_se_pre_reserva(self):
        """Regla «Período a pre-reservar»: de un suministro «vigente»; uno «finalizado» no aporta períodos."""
        Suministro.objects.filter(pk=self.s.pk).update(estado_suministro="finalizado")
        self.correr()
        self.assertEqual(ReservaStock.objects.count(), 0)

    def test_regla_cliente_inactivo_su_contrato_vigente_se_sigue_pre_reservando(self):
        """Regla «Cliente inactivo» (regla 2 de 8.18): no se mira el estado del cliente."""
        Cliente.objects.filter(pk=self.e.cliente.pk).update(estado_cliente="inactivo")
        self.correr()
        self.assertEqual(self.fechas_reservadas(), [en(3), en(10)])

    def test_regla_el_orden_es_por_fecha_y_con_la_misma_fecha_por_id_del_detalle(self):
        """Paso 2: los períodos se recorren por fecha de entrega y, con la misma fecha, en el orden de registro de sus detalles. Con dos detalles
        que coinciden en fecha, las reservas salen por fecha y, con la misma, por id de detalle."""
        otro = detalle_suministro(self.s, self.e.variedad, direccion=self.otra_direccion(), cantidad=10, periodo=7, primera_en_dias=3)
        self.correr()
        orden = [(r.fecha_entrega_reserva, r.detalle_suministro_id) for r in ReservaStock.objects.filter(detalle_suministro__isnull=False).order_by("pk")]
        self.assertEqual(orden, sorted(orden))
        self.assertEqual(orden[:2], [(en(3), self.d.pk), (en(3), otro.pk)])

    def test_regla_un_dia_sin_ejecucion_se_recupera_al_siguiente(self):
        """Regla «Período a pre-reservar»: «un día sin ejecución se recupera al siguiente». Un período a los 15 días entra en la ventana mañana;
        si nadie corre mañana, la ejecución de pasado mañana (hoy + 2) lo toma igual."""
        DetalleSuministro.objects.filter(pk=self.d.pk).update(fecha_primer_entrega=en(15), periodo_entrega_dias=30)
        partida(self.lote, disponible=60, fecha_limite=en(40))  # de cámara: el lote todavía no llega a cosechar para el día 15
        self.assertEqual(self.correr().procesados, 0)
        self.correr(HOY + timedelta(days=2))
        self.assertEqual(self.fechas_reservadas(), [en(15)])


class IdempotenciaTests(BaseDePrereserva):
    """Garantía mínima 2: aunque el proceso se repita, no hay más reservas que las necesarias."""

    def test_regla_dos_corridas_el_mismo_dia_no_hacen_nada_la_segunda(self):
        """Idempotencia (D-56, punto 4): la segunda corrida del día no crea reservas, no audita y su resumen es cero."""
        self.correr()
        reservas, auditoria = ReservaStock.objects.count(), RegistroAuditoria.objects.filter(accion="pre_reserva_periodo").count()
        resumen = self.correr()
        self.assertEqual(resumen, ResumenDePaso(0, 0, 0, "0 períodos siguen sin cobertura completa"))
        self.assertEqual(ReservaStock.objects.count(), reservas)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="pre_reserva_periodo").count(), auditoria)

    def test_regla_un_periodo_reintentado_sin_ningun_cambio_no_audita(self):
        """Auditoría: un período que se vuelve a intentar sin cambiar nada (sigue sin stock, con su alerta ya creada y la misma cantidad) no deja
        registro: si no, cada día dejaría uno igual. Tampoco avisa de nuevo."""
        self.retener(100)
        self.correr()
        auditoria, avisos = RegistroAuditoria.objects.filter(accion="pre_reserva_periodo").count(), Notificacion.objects.count()
        self.correr()
        self.assertEqual(RegistroAuditoria.objects.filter(accion="pre_reserva_periodo").count(), auditoria)
        self.assertEqual(Notificacion.objects.count(), avisos)


class SinStockTests(BaseDePrereserva):
    """Extensiones 3a y 3b y la alerta (postcondiciones c y d). El lote tiene 100 plantas y una venta ajena retiene 80: quedan 20 libres."""

    def setUp(self):
        super().setUp()
        self.ajena = self.retener(80)

    def test_ext_3a_reserva_lo_disponible_y_genera_la_alerta_con_lo_que_falta(self):
        """Extensión 3a y postcondición c: con 20 plantas libres y 30 por período, el primero se reserva con 20 y queda con 10 sin cubrir; el
        segundo no tiene nada disponible (no crea reserva). Cada uno tiene su alerta con la clave del período, su descripción y su
        `AlertaComercial` (fecha y cantidad sin cubrir)."""
        resumen = self.correr()
        self.assertEqual(self.fechas_reservadas(), [en(3)])
        self.assertEqual(self.reservas()[0].lineas.get().cantidad_reservada, 20)
        primera, segunda = self.alertas()
        self.assertEqual((primera.clave_estado, segunda.clave_estado), (f"periodo:{self.d.pk}:{en(3)}", f"periodo:{self.d.pk}:{en(10)}"))
        self.assertEqual(
            primera.descripcion_alerta, f"Período sin cobertura completa · {self.e.variedad} · {self.e.cliente} · {en(3):%d/%m}"
        )
        self.assertEqual(
            [(a.vinculo_comercial.fecha_periodo, a.vinculo_comercial.cantidad_sin_cubrir) for a in (primera, segunda)], [(en(3), 10), (en(10), 30)]
        )
        self.assertEqual(
            resumen, ResumenDePaso(procesados=2, creados=1, resueltos=0, detalle="2 períodos siguen sin cobertura completa")
        )

    def test_ext_3a_la_alerta_es_del_tipo_registrado_para_el_agronomo_activo(self):
        """Postcondición c y regla «Alerta»: tipo `comercial_periodo_sin_cobertura`, activa, para el Agrónomo del invernadero (regla 1 de 8.9);
        el Gerente no la recibe mientras haya Agrónomo activo."""
        self.correr()
        for alerta in self.alertas():
            self.assertEqual((alerta.tipo_alerta, alerta.estado_alerta, alerta.agronomo_id, alerta.para_gerente), (TIPO, "activa", self.e.agronomo.pk, False))

    def test_post_c_se_notifica_al_vendedor_del_contrato_con_lo_que_falta(self):
        """Postcondición c: «SUM-…: el período del dd/mm de {variedad} quedó sin cobertura completa. Faltan N plantas. InfoPonia vuelve a intentar
        cada día.» (una por período, al Vendedor del contrato)."""
        self.correr()
        avisos = list(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo="Período sin cobertura completa").order_by("pk"))
        self.assertEqual(len(avisos), 2)
        self.assertEqual(
            avisos[0].detalle,
            f"{self.s.codigo}: el período del {en(3):%d/%m} de {self.e.variedad} quedó sin cobertura completa. Faltan 10 plantas. "
            "InfoPonia vuelve a intentar cada día.",
        )
        self.assertIn("Faltan 30 plantas", avisos[1].detalle)

    def test_regla_la_alerta_no_se_duplica_ni_se_vuelve_a_notificar(self):
        """Postcondición c («si ya tenía la alerta, no se generó otra») y regla «Alerta»: otra corrida sin stock nuevo deja una alerta por período y
        no avisa al Vendedor de nuevo."""
        self.correr()
        avisos = Notificacion.objects.filter(destinatario=self.e.vendedor, titulo="Período sin cobertura completa").count()
        self.correr()
        self.assertEqual((len(self.alertas()), AlertaComercial.objects.count()), (2, 2))
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo="Período sin cobertura completa").count(), avisos)

    def test_ext_3b_con_stock_nuevo_se_reserva_la_cantidad_sin_cubrir_en_una_reserva_adicional_y_se_resuelve_la_alerta(self):
        """Extensiones 3b y postcondición d: cuando hay stock nuevo, el período con reserva parcial recibe «una reserva adicional» por lo que le
        falta, queda cubierto y su alerta se resuelve (con su fecha); el resumen cuenta las alertas resueltas."""
        self.correr()
        ReservaStock.objects.filter(pk=self.ajena.pk).update(estado_reserva="liberada")  # la venta ajena libera sus 80 plantas
        resumen = self.correr()
        reservas_del_primero = [r for r in self.reservas() if r.fecha_entrega_reserva == en(3)]
        self.assertEqual(sorted(r.lineas.get().cantidad_reservada for r in reservas_del_primero), [10, 20])
        self.assertEqual({a.estado_alerta for a in self.alertas()}, {"resuelta"})
        self.assertIsNotNone(self.alertas()[0].fecha_resolucion)
        self.assertEqual((resumen.creados, resumen.resueltos), (2, 2))

    def test_ext_3b_si_sigue_sin_alcanzar_la_alerta_sigue_activa_con_la_cantidad_actualizada(self):
        """Extensión 3b.2: con 50 plantas libres (30 después de las 20 ya reservadas), el primer período se cubre (10) y el segundo queda con 10 sin
        cubrir: su alerta sigue activa con la cantidad actualizada (de 30 a 10), sin otra alerta."""
        self.correr()
        self.reservar_en_total(self.ajena, 50)
        self.correr()
        primera, segunda = self.alertas()
        self.assertEqual((primera.estado_alerta, segunda.estado_alerta), ("resuelta", "activa"))
        self.assertEqual(segunda.vinculo_comercial.cantidad_sin_cubrir, 10)
        self.assertEqual(Alerta.objects.filter(tipo_alerta=TIPO).count(), 2)

    def test_post_d_la_alerta_se_resuelve_sola_al_pasar_la_fecha_del_periodo(self):
        """Regla «Alerta» («se resuelve al cubrirse el período o al llegar su fecha», decisión de aplicación): el período del día se intenta por
        última vez ese día y su alerta sigue activa; al empezar la corrida del día siguiente, una consulta resuelve las de fecha anterior, con su
        auditoría."""
        self.correr()
        self.correr(en(3))  # el día del período: sigue activa
        self.assertEqual(self.alertas()[0].estado_alerta, "activa")
        resumen = self.correr(en(4))
        primera = self.alertas()[0]
        self.assertEqual((primera.vinculo_comercial.fecha_periodo, primera.estado_alerta), (en(3), "resuelta"))
        self.assertGreaterEqual(resumen.resueltos, 1)
        self.assertTrue(
            RegistroAuditoria.objects.filter(accion="pre_reserva_periodo", detalle__datos__alertas_resueltas="1").exists()
        )

    def test_regla_el_invernadero_de_la_alerta_es_el_activo_de_menor_id_del_vendedor_si_no_hay_reserva(self):
        """D-63, punto 3: un período sin ninguna reserva lleva su alerta en el invernadero activo de menor id del Vendedor (aunque haya otro más
        nuevo)."""
        segundo_invernadero(self.e, "Invernadero Sur")
        self.reservar_en_total(self.ajena, 100)
        self.correr()
        self.assertEqual({a.invernadero_id for a in self.alertas()}, {self.e.invernadero.pk})

    def test_regla_el_invernadero_de_la_alerta_es_el_de_la_primera_reserva_del_periodo(self):
        """D-63, punto 3: si el período tiene reserva, la alerta va en el invernadero de la primera (la de menor id): acá el stock está solo en el
        segundo invernadero del Vendedor."""
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        self.reservar_en_total(self.ajena, 100)
        lote_maduro(sur, 20)
        self.correr()
        self.assertEqual(self.alertas()[0].invernadero_id, sur.invernadero.pk)
        self.assertEqual(self.reservas()[0].invernadero_id, sur.invernadero.pk)

    def test_ext_3a_sin_ninguna_planta_disponible_no_crea_reserva_y_genera_la_misma_alerta(self):
        """Extensión 3a.2: sin nada disponible, no crea reserva y genera la misma alerta, con todo lo del período por cubrir."""
        self.reservar_en_total(self.ajena, 100)
        self.correr()
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro__isnull=False).count(), 0)
        self.assertEqual([a.vinculo_comercial.cantidad_sin_cubrir for a in self.alertas()], [30, 30])

    def test_regla_sin_invernadero_activo_del_vendedor_no_hay_alerta_y_se_avisa_al_vendedor_y_al_gerente(self):
        """D-63, punto 4: si el Vendedor se quedó sin invernaderos activos no se crea la alerta (le falta el invernadero): se notifica al Vendedor
        y al Gerente con el mismo texto, una sola vez (una segunda corrida no repite el aviso)."""
        Invernadero.objects.filter(vendedor_id=self.e.vendedor.pk).update(estado_invernadero="inactivo")
        self.correr()
        self.assertEqual(Alerta.objects.filter(tipo_alerta=TIPO).count(), 0)
        al_vendedor = list(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo="Período sin cobertura completa"))
        al_gerente = list(Notificacion.objects.filter(destinatario=self.gerente, titulo="Período sin cobertura completa"))
        self.assertEqual((len(al_vendedor), len(al_gerente)), (2, 2))
        self.assertEqual(sorted(a.detalle for a in al_vendedor), sorted(a.detalle for a in al_gerente))
        self.correr()
        self.assertEqual(Notificacion.objects.filter(titulo="Período sin cobertura completa").count(), 4)


class FallaDeUnPeriodoTests(BaseDePrereserva):
    """Extensión *a: un período que falla no corta el paso."""

    def test_ext_asterisco_a_un_periodo_que_falla_no_deja_nada_y_los_demas_siguen(self):
        """Extensión *a y garantía mínima 1: si el primer período falla, no queda nada parcial de él (ni reserva, ni alerta, ni auditoría), el
        segundo se pre-reserva igual, el paso no lanza y la falla queda en el log. Al día siguiente el primero se vuelve a tomar."""
        from comercial.servicios import stock_maduro

        real = stock_maduro.asignar

        def falla_en_el_primero(origen, periodo, *args, **kwargs):
            if periodo.fecha == en(3):
                raise RuntimeError("falla de prueba")
            return real(origen, periodo, *args, **kwargs)

        with mock.patch.object(stock_maduro, "asignar", side_effect=falla_en_el_primero), self.assertLogs(level="ERROR"):
            self.correr()
        self.assertEqual(self.fechas_reservadas(), [en(10)])
        self.assertEqual(Alerta.objects.count(), 0)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="pre_reserva_periodo").count(), 1)
        self.correr()
        self.assertEqual(self.fechas_reservadas(), [en(3), en(10)])


class RegistroTests(BaseDePrereserva):
    """Lo que `ComercialConfig.ready()` deja registrado (regla A4 de D-37)."""

    def test_regla_el_tipo_de_alerta_esta_registrado_con_su_definicion(self):
        """D-62 y D-63, punto 3: `AGRONOMO_O_GERENTE`, `ADVERTENCIA`, de estado y con origen `DETALLE_SUMINISTRO`."""
        tipo = tipo_de_alerta(TIPO)
        self.assertEqual(
            (tipo.nombre, tipo.destinatario, tipo.severidad, tipo.clase, tipo.origen),
            ("Período sin cobertura completa", Destinatario.AGRONOMO_O_GERENTE, Alerta.Severidad.ADVERTENCIA, Clase.ESTADO, Origen.DETALLE_SUMINISTRO),
        )

    def test_regla_el_paso_40_esta_registrado_en_el_proceso_diario(self):
        """D-56, punto 6: «pre_reservar_suministros», «Pre-reservar suministros», orden 40."""
        from comercial.servicios import pre_reserva

        (paso,) = [p for p in pasos_diarios() if p.codigo == "pre_reservar_suministros"]
        self.assertEqual((paso.nombre, paso.orden, paso.funcion), ("Pre-reservar suministros", 40, pre_reserva.pre_reservar_suministros))

    def test_regla_el_enlace_esta_registrado_para_el_tipo(self):
        """D-62: `comercial` registra su función de enlaces para `comercial_periodo_sin_cobertura`."""
        from comercial.servicios import pre_reserva

        self.assertIn(((TIPO,), pre_reserva.enlaces_de_alertas_de_periodo), enlaces_registrados())

    def test_regla_ready_dos_veces_no_duplica_nada(self):
        """`ready()` puede correr más de una vez: el paso, el tipo y el enlace siguen una sola vez."""
        apps.get_app_config("comercial").ready()
        self.assertEqual(len([p for p in pasos_diarios() if p.codigo == "pre_reservar_suministros"]), 1)
        self.assertEqual(len([c for c, _ in enlaces_registrados() if TIPO in c]), 1)


class EnlaceDeAlertaTests(BaseDePrereserva):
    """D-62: adónde lleva la alerta desde la campana, según quién la ve."""

    def setUp(self):
        super().setUp()
        self.alerta = alerta_de_periodo(self.d, en(3), cantidad_sin_cubrir=10, invernadero=self.e.invernadero, para_gerente=True, agronomo=self.e.agronomo)

    def con_invernadero(self, alertas):
        return list(Alerta.objects.filter(pk__in=[a.pk for a in alertas]).select_related("invernadero"))

    def enlaces(self, usuario, alertas=None):
        from comercial.servicios import pre_reserva

        return pre_reserva.enlaces_de_alertas_de_periodo(usuario, self.con_invernadero(alertas or [self.alerta]))

    def test_regla_el_gerente_va_a_la_ficha_del_suministro_en_su_calendario(self):
        """D-62: para el Gerente, la ficha del suministro con ``#calendario`` y el detalle «Faltan N plantas para el dd/mm»."""
        enlace = self.enlaces(self.gerente)[self.alerta.pk]
        self.assertEqual(enlace, Enlace(reverse("comercial:suministro", args=[self.s.pk]) + "#calendario", f"Faltan 10 plantas para el {en(3):%d/%m}"))

    def test_regla_el_agronomo_va_a_la_ficha_del_invernadero(self):
        """D-62, punto 4: el Agrónomo no abre contratos; va a la ficha del invernadero de la alerta, con el mismo texto."""
        enlace = self.enlaces(self.e.agronomo)[self.alerta.pk]
        self.assertEqual(enlace, Enlace(reverse("maestros:invernadero", args=[self.e.invernadero.pk]), f"Faltan 10 plantas para el {en(3):%d/%m}"))

    def test_regla_con_una_sola_planta_el_texto_va_en_singular(self):
        """El texto concuerda: «Falta 1 planta para el dd/mm»."""
        AlertaComercial.objects.filter(alerta=self.alerta).update(cantidad_sin_cubrir=1)
        self.assertEqual(self.enlaces(self.gerente)[self.alerta.pk].detalle, f"Falta 1 planta para el {en(3):%d/%m}")

    def test_regla_otros_roles_no_reciben_enlace_y_queda_el_de_omision(self):
        """D-62, punto 4: «Ninguna alerta de la campana puede llevar a un 403»: para un rol que no abre ninguna de las dos pantallas, el
        registrante no devuelve nada."""
        self.assertEqual(self.enlaces(self.e.capataz), {})
        self.assertEqual(self.enlaces(self.e.vendedor), {})

    def test_regla_sin_alertas_devuelve_vacio_sin_consultar_la_base(self):
        """Prueba mínima de cada registrante: lista vacía, `{}` sin consultas."""
        from comercial.servicios import pre_reserva

        with self.assertNumQueries(0):
            self.assertEqual(pre_reserva.enlaces_de_alertas_de_periodo(self.gerente, []), {})

    def test_regla_una_sola_consulta_para_toda_la_lista(self):
        """Prueba mínima de cada registrante: sin consultas por alerta (igual número de consultas con una que con tres alertas)."""
        from comercial.servicios import pre_reserva

        mas = [alerta_de_periodo(self.d, en(d), invernadero=self.e.invernadero, para_gerente=True) for d in (10, 17)]
        una = self.con_invernadero([self.alerta])
        tres = self.con_invernadero([self.alerta, *mas])
        with CaptureQueriesContext(connection) as con_una:
            pre_reserva.enlaces_de_alertas_de_periodo(self.gerente, una)
        with CaptureQueriesContext(connection) as con_tres:
            pre_reserva.enlaces_de_alertas_de_periodo(self.gerente, tres)
        self.assertEqual(len(con_una), len(con_tres))

    def test_regla_la_campana_del_gerente_pasa_por_alertas_ir_con_el_texto_del_enlace(self):
        """D-62 (tercera enmienda): el item de la campana lleva a `alertas:ir` y su detalle sale del enlace."""
        (item,) = [i for i in items_de_campana(self.gerente) if i.titulo == self.alerta.descripcion_alerta]
        self.assertEqual(item.url, reverse("alertas:ir", args=[self.alerta.pk]))
        self.assertEqual(item.detalle, f"Faltan 10 plantas para el {en(3):%d/%m}")

    def test_regla_alertas_ir_lleva_al_gerente_a_la_ficha_del_suministro_y_marca_leida_la_alerta(self):
        """D-62: `alertas:ir` abre la alerta (la marca «leída») y redirige a la ficha del suministro con su calendario."""
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("alertas:ir", args=[self.alerta.pk]))
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.s.pk]) + "#calendario", fetch_redirect_response=False)
        self.assertEqual(Alerta.objects.get(pk=self.alerta.pk).estado_lectura_alerta, Alerta.Lectura.LEIDA)

    def test_regla_alertas_ir_lleva_al_agronomo_a_una_pantalla_que_puede_abrir(self):
        """D-62, punto 4: para el Agrónomo la ficha del invernadero, que abre sin 403."""
        self.client.force_login(self.e.agronomo)
        respuesta = self.client.get(reverse("alertas:ir", args=[self.alerta.pk]))
        self.assertRedirects(respuesta, reverse("maestros:invernadero", args=[self.e.invernadero.pk]))
