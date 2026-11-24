# Pruebas de PROD-CNL-ORD · la «Cancelación de una entrega» (COM-05a1; `cancelar_entrega_incluida` y `quitar_lineas_liberadas` de `comercial/servicios/entregas.py`), solo desde otro caso
# de uso (sin pantalla). Los llamadores reales (PROD-VNC-CAM 3a y la merma en cámara 10c) se prueban en `test_prod_vnc_cam.py` y `test_prod_reg_mrm_camara.py`.
# Fuente: docs/casos_de_uso/produccion/cancelar_orden.md («Cancelación de una entrega» y «Comercial 1: entregas y envasado»; situaciones 10 a 12), D-66 puntos 4 y 9.

from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega
from comercial.servicios import entregas
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    entrega,
    escenario_comercial,
    reserva_lista,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Invernadero
from produccion.models import ReservaInsumo
from produccion.tests.fabricas import lote_maduro, reservar, variedad_con_stock

HOY = timezone.localdate()
TIPO = entregas.TIPO_SIN_TRANSPORTISTA


def codigo_de(error):
    """El código del primer error de un `ValidationError` de campo."""
    return next(iter(error.error_dict.values()))[0].code


class ProdCnlOrdEntregasServicioTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.gerente = crear_gerente()
        cls.t = transportista_con_vehiculo(cls.e.invernadero, "800")

    def entrega_de(self, cantidad=100, *, transportista=None, **opciones):
        venta = compra_venta(self.e, dias=opciones.pop("dias", 3))
        det = detalle(venta, self.e.variedad, cantidad)
        r = reserva_lista(det, self.lote, cantidad)
        return venta, r, entrega(venta, [r], transportista=transportista, **opciones)

    def avisos(self, cuenta):
        return list(Notificacion.objects.filter(destinatario=cuenta).order_by("pk"))

    # ---- la orden ----

    def test_post_la_entrega_pasa_a_cancelada_con_la_fecha_de_hoy_y_el_motivo_y_conserva_sus_lineas(self):
        """La entrega pasa a «cancelada» con la fecha actual como fecha de resolución y el motivo del caso de uso base; conserva sus detalles como historial (R150 en 0..\\*)."""
        venta, r, e = self.entrega_de()
        resultado = entregas.cancelar_entrega_incluida(None, e, "Se canceló la venta.")
        actual = Entrega.objects.get(pk=e.pk)
        self.assertEqual((actual.estado_orden, actual.fecha_resolucion_orden, actual.motivo_cancelacion), ("cancelada", HOY, "Se canceló la venta."))
        self.assertEqual(actual.lineas.count(), 1)
        self.assertEqual(list(actual.lineas.get().reservas.all()), [r])
        self.assertEqual(resultado.entrega.pk, e.pk)

    def test_regla_no_toca_las_reservas_de_stock_ni_sus_lineas(self):
        """Situación 12 y precondición: este caso de uso no cambia las reservas de stock; el destino del producto lo decide el caso de uso base."""
        venta, r, e = self.entrega_de()
        antes = (r.estado_reserva, list(r.lineas.values_list("cantidad_reservada", flat=True)))
        entregas.cancelar_entrega_incluida(None, e, "x")
        r.refresh_from_db()
        self.assertEqual((r.estado_reserva, list(r.lineas.values_list("cantidad_reservada", flat=True))), antes)

    def test_regla_la_entrega_cancelada_deja_de_contar_para_el_transportista(self):
        """La entrega deja de contar para la capacidad de carga y los límites diarios, que solo cuentan las no canceladas."""
        venta, r, e = self.entrega_de(transportista=self.t)
        fecha = e.fecha_programada_orden
        entregas.cancelar_entrega_incluida(None, e, "x")
        candidato = next(c for c in entregas.candidatos_para(self.e.invernadero, fecha, 1, None, hoy=HOY) if c.transportista.pk == self.t.pk)
        self.assertEqual((candidato.entregas_del_dia, candidato.motivo), (0, None))

    def test_regla_el_motivo_largo_se_recorta_a_300_y_el_vacio_se_rechaza(self):
        """El motivo ya viene armado: si pasa de 300 se recorta con «…» (como `cancelar_orden_incluida`); vacío, `motivo_obligatorio`."""
        venta, r, e = self.entrega_de()
        with self.assertRaises(ValidationError) as contexto:
            entregas.cancelar_entrega_incluida(None, e, "   ")
        self.assertEqual(codigo_de(contexto.exception), "motivo_obligatorio")
        entregas.cancelar_entrega_incluida(None, e, "a" * 400)
        guardado = Entrega.objects.get(pk=e.pk).motivo_cancelacion
        self.assertEqual((len(guardado), guardado[-1]), (300, "…"))

    # ---- el envasado (situación 10) ----

    def test_regla_las_reservas_de_insumo_pasan_a_canceladas_sin_consumo(self):
        """Situación 10: las reservas de insumo (envases) «activas» pasan a «cancelada», sin registrar consumo."""
        venta, r, e = self.entrega_de()
        reservar(e, self.e.existencia_semilla, 20)
        resultado = entregas.cancelar_entrega_incluida(None, e, "x")
        reserva = ReservaInsumo.objects.get(orden_id=e.pk)
        self.assertEqual((reserva.estado, reserva.cantidad_utilizada, reserva.cantidad_devuelta), ("cancelada", None, None))
        self.assertEqual([x.pk for x in resultado.reservas_de_insumo], [reserva.pk])

    def test_post_con_envasado_se_avisa_al_agronomo_de_los_envases_reservados(self):
        """Situación 10: si el envasado ya estaba planificado, el Agrónomo del invernadero recibe los envases que estaban reservados para que los regularice con un ajuste de stock."""
        venta, r, e = self.entrega_de()
        reservar(e, self.e.existencia_semilla, 20)
        entregas.cancelar_entrega_incluida(None, e, "x")
        aviso = self.avisos(self.e.agronomo)[0]
        self.assertEqual(aviso.titulo, f"Se canceló {e.codigo}, que tenía envases reservados")
        self.assertIn(f"Reservados: 20 {self.e.existencia_semilla.insumo.nombre_insumo}.", aviso.detalle)
        self.assertIn("ajustá el stock", aviso.detalle)

    def test_regla_sin_envasado_no_se_avisa_al_agronomo(self):
        """Sin reservas de insumo activas no hay envases que regularizar: el Agrónomo no recibe nada."""
        venta, r, e = self.entrega_de()
        entregas.cancelar_entrega_incluida(None, e, "x")
        self.assertEqual(self.avisos(self.e.agronomo), [])

    def test_regla_sin_agronomo_activo_no_se_avisa_de_los_envases(self):
        """Sin Agrónomo activo en el invernadero, el aviso no se envía (y la cancelación sigue)."""
        venta, r, e = self.entrega_de()
        reservar(e, self.e.existencia_semilla, 20)
        self.e.agronomo.is_active = False
        self.e.agronomo.save()
        resultado = entregas.cancelar_entrega_incluida(None, e, "x")
        self.assertEqual(self.avisos(self.e.agronomo), [])
        self.assertEqual(resultado.avisados, [])

    # ---- el transportista (situación 11) ----

    def test_post_se_avisa_al_transportista_la_cancelacion(self):
        """Si la entrega tiene transportista, se le notifica la cancelación con el motivo."""
        venta, r, e = self.entrega_de(transportista=self.t)
        entregas.cancelar_entrega_incluida(None, e, "Se venció en cámara el producto reservado.")
        aviso = self.avisos(self.t)[0]
        self.assertEqual((aviso.titulo, aviso.detalle), (f"Se canceló la entrega {e.codigo}", "Se venció en cámara el producto reservado."))

    def test_ext_11_una_entrega_en_curso_se_cancela_igual_y_se_le_dice_que_no_la_entregue(self):
        """Situación 11: si el vehículo está en ruta y la fecha programada es hoy o anterior, se cancela igual y el aviso, inmediato, indica que no la entregue y devuelva el producto y los envases al invernadero."""
        en_ruta = transportista_con_vehiculo(self.e.invernadero, "800", en_ruta=True)
        venta, r, e = self.entrega_de(transportista=en_ruta, dias=0)
        entregas.cancelar_entrega_incluida(None, e, "Se canceló la venta.")
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_orden, "cancelada")
        aviso = self.avisos(en_ruta)[0]
        self.assertIn(f"No la entregues: devolvé el producto y los envases a {self.e.invernadero}.", aviso.detalle)

    def test_ext_11_una_entrega_futura_no_se_considera_en_curso_aunque_el_vehiculo_este_en_ruta(self):
        """El texto de «en curso» solo va si la fecha programada es hoy o anterior."""
        en_ruta = transportista_con_vehiculo(self.e.invernadero, "800", en_ruta=True)
        venta, r, e = self.entrega_de(transportista=en_ruta, dias=4)
        entregas.cancelar_entrega_incluida(None, e, "x")
        self.assertNotIn("No la entregues", self.avisos(en_ruta)[0].detalle)

    # ---- la alerta (PCU, sección 7) ----

    def test_post_la_alerta_entrega_sin_transportista_queda_resuelta(self):
        """PCU 7: la cancelación de una entrega resuelve su alerta «entrega sin transportista»."""
        venta, r, e = self.entrega_de()
        alerta = entregas._alerta_sin_transportista(e, venta, "capacidad de carga insuficiente")
        resultado = entregas.cancelar_entrega_incluida(None, e, "x")
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertEqual(resultado.alerta_resuelta.pk, alerta.pk)
        self.assertEqual(AlertaComercial.objects.get(entrega=e).alerta_id, alerta.pk)

    # ---- las reglas del caso de uso incluido ----

    def test_regla_no_audita_y_devuelve_lo_afectado_para_el_registro_del_llamador(self):
        """Como `cancelar_cosecha_incluida`: no audita (lo hace el caso de uso base, D-36); devuelve la entrega y a quién avisó."""
        venta, r, e = self.entrega_de(transportista=self.t)
        antes = RegistroAuditoria.objects.count()
        resultado = entregas.cancelar_entrega_incluida(None, e, "x")
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        self.assertEqual([c.pk for c in resultado.avisados], [self.t.pk])

    def test_ext_8a_una_entrega_que_ya_no_esta_a_realizar_se_rechaza(self):
        """Extensión 8a: si la entrega ya no está «a realizar» (la concretó o la canceló otro), `entrega_no_a_realizar` y el caso de uso base decide cómo sigue."""
        for estado in ("concretada", "cancelada"):
            venta, r, e = self.entrega_de(estado=estado)
            with self.assertRaises(ValidationError) as contexto:
                entregas.cancelar_entrega_incluida(None, e, "x")
            self.assertEqual(codigo_de(contexto.exception), "entrega_no_a_realizar")

    def test_regla_sin_transaccion_lanza_runtime_error(self):
        """Corre en la transacción del llamador: sin ella, `RuntimeError`."""
        venta, r, e = self.entrega_de()
        with mock.patch.object(entregas.transaction, "get_autocommit", return_value=True), self.assertRaises(RuntimeError):
            entregas.cancelar_entrega_incluida(None, e, "x")
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_orden, "a_realizar")

    def test_regla_con_actor_no_cambia_lo_que_hace(self):
        """`actor` puede ser `None` (InfoPonia) o quien actúa: no cambia lo que hace la función."""
        venta, r, e = self.entrega_de()
        entregas.cancelar_entrega_incluida(self.gerente, e, "x")
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_orden, "cancelada")

    def test_regla_cancela_aunque_el_invernadero_este_inactivo(self):
        """Cancelar siempre se puede: resolver la alerta no exige un invernadero activo."""
        venta, r, e = self.entrega_de()
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        entregas.cancelar_entrega_incluida(None, e, "x")
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_orden, "cancelada")


class QuitarLineasLiberadasTests(ConDatosDeInventario, TestCase):
    """D-66 puntos 4 y 9: después de un recorte, las líneas sin reservas vivas valen 0 y la entrega vacía se cancela."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.t = transportista_con_vehiculo(cls.e.invernadero, "800")

    def liberar(self, *reservas):
        for r in reservas:
            r.estado_reserva = "liberada"
            r.save()

    def test_d66_4_la_entrega_con_todas_sus_lineas_en_cero_esta_vacia_y_se_cancela(self):
        """Una entrega «a realizar» con todas sus líneas quitadas se cancela con `cancelar_entrega_incluida`, con el motivo pedido."""
        venta = compra_venta(self.e)
        det = detalle(venta, self.e.variedad, 50)
        r = reserva_lista(det, self.lote, 50)
        e = entrega(venta, [r], transportista=self.t)
        self.liberar(r)
        quita = entregas.quitar_lineas_liberadas(None, entregas.entregas_de_reservas([r.pk]), "Se venció en cámara el producto reservado.")
        self.assertEqual([c.entrega.pk for c in quita.cancelaciones], [e.pk])
        self.assertEqual(len(quita.lineas_quitadas), 1)
        actual = Entrega.objects.get(pk=e.pk)
        self.assertEqual((actual.estado_orden, actual.motivo_cancelacion), ("cancelada", "Se venció en cámara el producto reservado."))
        self.assertEqual(actual.lineas.count(), 1)  # la línea no se borra: queda como historial
        verificar_invariantes_de_entregas()

    def test_d66_4_la_entrega_que_conserva_una_linea_no_se_cancela(self):
        """La entrega que conserva otra línea con producto sigue «a realizar»; solo la línea recortada se da por quitada."""
        venta = compra_venta(self.e)
        det = detalle(venta, self.e.variedad, 50)
        de_otra_variedad = detalle(venta, variedad_con_stock(self.e, "Rúcula")[0], 20)
        r1 = reserva_lista(det, self.lote, 50)
        r2 = reserva_lista(de_otra_variedad, lote_maduro(self.e, 100, variedad=de_otra_variedad.variedad), 20)
        e = entrega(venta, [r1, r2])
        self.liberar(r1)
        quita = entregas.quitar_lineas_liberadas(None, entregas.entregas_de_reservas([r1.pk]), "x")
        self.assertEqual(quita.cancelaciones, [])
        self.assertEqual(len(quita.lineas_quitadas), 1)
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_orden, "a_realizar")
        self.assertEqual(entregas.peso_de_entregas([e.pk])[e.pk], Decimal("3.00"))

    def test_d66_4_una_reserva_recortada_pero_no_liberada_deja_la_entrega_a_realizar(self):
        """Un recorte parcial deja la reserva «lista para entrega» con menos cantidad: la línea sigue con producto y la entrega no se cancela."""
        venta = compra_venta(self.e)
        det = detalle(venta, self.e.variedad, 50)
        r = reserva_lista(det, self.lote, 50)
        e = entrega(venta, [r])
        r.lineas.update(cantidad_reservada=20)
        quita = entregas.quitar_lineas_liberadas(None, entregas.entregas_de_reservas([r.pk]), "x")
        self.assertEqual((quita.cancelaciones, quita.lineas_quitadas), ([], []))
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_orden, "a_realizar")
        self.assertEqual(entregas.peso_de_entregas([e.pk])[e.pk], Decimal("3.00"))

    def test_regla_una_entrega_que_ya_no_esta_a_realizar_no_se_toca(self):
        """Solo las entregas «a realizar» entran: una concretada (PROD-VNC-CAM 3b, COM-06) no se cancela acá."""
        venta = compra_venta(self.e)
        det = detalle(venta, self.e.variedad, 50)
        r = reserva_lista(det, self.lote, 50)
        e = entrega(venta, [r], estado="concretada")
        self.liberar(r)
        quita = entregas.quitar_lineas_liberadas(None, [e.pk], "x")
        self.assertEqual((quita.cancelaciones, quita.lineas_quitadas), ([], []))

    def test_regla_sin_entregas_afectadas_no_hace_nada(self):
        """Sin ids no consulta ni bloquea nada."""
        quita = entregas.quitar_lineas_liberadas(None, [], "x")
        self.assertEqual((quita.cancelaciones, quita.lineas_quitadas), ([], []))

    def test_regla_entregas_de_reservas_encuentra_solo_las_a_realizar(self):
        """`entregas_de_reservas`: los ids de las entregas «a realizar» con una línea de esas reservas."""
        venta = compra_venta(self.e)
        det = detalle(venta, self.e.variedad, 50)
        r = reserva_lista(det, self.lote, 50)
        a_realizar = entrega(venta, [r])
        entrega(venta, [r], estado="cancelada")
        self.assertEqual(entregas.entregas_de_reservas([r.pk]), [a_realizar.pk])
        self.assertEqual(entregas.entregas_de_reservas([]), [])
