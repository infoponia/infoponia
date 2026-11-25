# Pruebas de COM-PNF-ENT · Planificar Entrega (COM-05a1): `ComPnfEntServicioTests` (la planificación inmediata: reglas, postcondiciones a a g, i y m, y las extensiones 1a, 2a, 3a, 4a,
# 6a, 7a, 8b y \*a; el aviso de envasado, postcondición h, es de COM-05a2) y `ComPnfEntDiariaTests` (el paso diario 50: las cuatro partes, j, k, l y n, y el reintento de los correos).
# Fuente: docs/casos_de_uso/comercial/entregas.md («COM-PNF-ENT», «Cómo se aplica en la ronda «Comercial 1»»), D-66 y D-42.

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega, ReservaStock
from comercial.servicios import entregas
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    detalle_suministro,
    entrega,
    escenario_comercial,
    reserva_lista,
    segundo_invernadero,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
)
from core import correo
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import ConfiguracionOperativa, Invernadero
from produccion.tests.fabricas import lote_maduro, variedad_con_stock

HOY = timezone.localdate()
TIPO = entregas.TIPO_SIN_TRANSPORTISTA


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.gerente = crear_gerente()
        cls.t = transportista_con_vehiculo(cls.e.invernadero, "800")

    def venta_lista(self, cantidad=100, dias=3, **opciones):
        venta = compra_venta(self.e, dias=dias, **opciones)
        det = detalle(venta, self.e.variedad, cantidad)
        return venta, det, reserva_lista(det, self.lote, cantidad)

    def periodo_listo(self, cantidad=100, primera_en_dias=3, **opciones):
        s = suministro(self.e)
        det = detalle_suministro(s, self.e.variedad, cantidad=cantidad, primera_en_dias=primera_en_dias, **opciones)
        fecha = det.fecha_primer_entrega
        return s, det, fecha, reserva_lista(None, self.lote, cantidad, fecha_entrega=fecha, detalle_suministro=det)

    def otra_variedad(self, nombre="Otra"):
        """Una segunda variedad con su ciclo (la fábrica devuelve `(variedad, existencia)`)."""
        return variedad_con_stock(self.e, nombre)[0]

    def sin_flota(self):
        """Saca al único transportista del invernadero: el invernadero queda sin flota."""
        self.t.invernadero_asignado.delete()

    def avisos(self, cuenta):
        return list(Notificacion.objects.filter(destinatario=cuenta).order_by("pk"))

    def titulos(self, cuenta):
        return [a.titulo for a in self.avisos(cuenta)]

    def una(self, resultados):
        self.assertEqual(len(resultados), 1)
        return resultados[0]


class ComPnfEntServicioTests(Base):
    # ---- reglas ----

    def test_flujo_principal_planifica_la_entrega_de_una_venta_lista_con_envio(self):
        """Pasos 1 a 8: una venta «abierta» con todo «lista para entrega» y envío arma una entrega «a realizar» en la fecha pactada, con el transportista elegido, su línea y sus reservas."""
        venta, det, r = self.venta_lista()
        resultado = self.una(entregas.planificar_venta(venta.pk, HOY))
        e = resultado.entrega
        self.assertTrue(resultado.creada)
        self.assertEqual((e.estado_orden, e.tipo_orden, e.fecha_programada_orden), ("a_realizar", "entrega", venta.fecha_pactada_venta))
        self.assertEqual((e.contrato_entrega_id, e.modalidad_entrega, e.direccion_destino_id), (venta.pk, "envio", venta.direccion_envio_id))
        self.assertEqual(e.transportista_id, self.t.pk)
        self.assertEqual(list(e.lineas.get().reservas.all()), [r])
        verificar_invariantes_de_entregas()

    def test_regla_venta_lista_exige_la_venta_abierta(self):
        """Regla «Venta lista para entrega»: una venta «pendiente de decisión», cancelada o concretada no se planifica."""
        for estado in ("pendiente_decision", "cancelada", "concretada"):
            venta, det, r = self.venta_lista(estado=estado)
            self.assertEqual(entregas.planificar_venta(venta.pk, HOY), [], estado)
        self.assertEqual(Entrega.objects.count(), 0)

    def test_regla_venta_lista_ningun_detalle_pendiente_de_decision(self):
        """Regla «Venta lista»: con algún detalle «pendiente de decisión del cliente» no se planifica nada, aunque otro esté listo."""
        venta, det, r = self.venta_lista()
        detalle(venta, self.otra_variedad("Pendiente"), 5, estado="pendiente_decision")
        self.assertEqual(entregas.planificar_venta(venta.pk, HOY), [])

    def test_regla_venta_lista_ninguna_reserva_activa(self):
        """Regla «Venta lista»: con una reserva «activa» (una cosecha sin concretar) la venta todavía no está lista."""
        venta, det, r = self.venta_lista()
        ReservaStock.objects.filter(pk=reserva_lista(det, self.lote, 5).pk).update(estado_reserva="activa")
        self.assertEqual(entregas.planificar_venta(venta.pk, HOY), [])

    def test_regla_venta_lista_las_reservas_liberadas_no_cuentan(self):
        """Regla «Venta lista»: las reservas «liberadas» no cuentan; se planifican las demás."""
        venta, det, r = self.venta_lista()
        liberada = reserva_lista(det, self.lote, 5)
        ReservaStock.objects.filter(pk=liberada.pk).update(estado_reserva="liberada")
        e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        self.assertEqual(list(e.lineas.get().reservas.all()), [r])

    def test_regla_los_detalles_rechazados_no_cuentan(self):
        """Regla «Venta lista»: los detalles rechazados quedan afuera (ni sus reservas activas la frenan)."""
        venta, det, r = self.venta_lista()
        rechazado = detalle(venta, self.otra_variedad("Rechazada"), 5, estado="rechazado")
        ReservaStock.objects.create(detalle_venta=rechazado, invernadero=self.e.invernadero, fecha_entrega_reserva=HOY, estado_reserva="activa")
        self.assertEqual(len(entregas.planificar_venta(venta.pk, HOY)), 1)

    def test_regla_alcance_una_venta_de_dos_invernaderos_arma_dos_entregas(self):
        """Regla «Alcance de una entrega» y paso 2: una entrega por cada invernadero de origen de la venta con envío."""
        sur = segundo_invernadero(self.e)
        transportista_con_vehiculo(sur.invernadero, "800")
        venta, det, _ = self.venta_lista(40)
        reserva_lista(det, lote_maduro(sur, 500), 30)
        resultados = entregas.planificar_venta(venta.pk, HOY)
        self.assertEqual(len(resultados), 2)
        self.assertEqual({r.entrega.invernadero_id for r in resultados}, {self.e.invernadero.pk, sur.invernadero.pk})
        verificar_invariantes_de_entregas()

    def test_regla_destino_la_venta_con_envio_usa_su_direccion_y_el_suministro_la_de_su_detalle(self):
        """Regla «Destino»: la dirección de envío de la venta; en un suministro, la del detalle."""
        venta, det, r = self.venta_lista()
        self.assertEqual(self.una(entregas.planificar_venta(venta.pk, HOY)).entrega.direccion_destino_id, venta.direccion_envio_id)
        s, d, fecha, rs = self.periodo_listo()
        self.assertEqual(self.una(entregas.planificar_periodo(d.pk, fecha, HOY)).entrega.direccion_destino_id, d.direccion_id)

    def test_regla_precio_el_de_la_venta_y_el_del_periodo_con_la_fecha_programada(self):
        """Regla «Datos económicos de una línea»: el precio unitario del detalle de venta; en un suministro, el del período según la regla 7 de 8.11 calculado con la fecha programada."""
        venta, det, r = self.venta_lista()
        linea = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega.lineas.get()
        self.assertEqual((linea.precio_unitario, linea.cant_entregada, linea.monto_pagar), (Decimal("100.00"), None, None))
        s, d, fecha, rs = self.periodo_listo(mecanismo="ajuste_periodico", porcentaje="10", meses=1, primera_en_dias=70, precio="100.00")
        linea = self.una(entregas.planificar_periodo(d.pk, fecha, HOY)).entrega.lineas.get()
        from comercial.servicios import calendario

        self.assertEqual(linea.precio_unitario, calendario.precio_en(d, fecha))
        self.assertGreater(linea.precio_unitario, Decimal("100.00"))

    def test_regla_estado_inicial_la_entrega_nace_a_realizar_y_la_de_suministro_no_confirmada(self):
        """Regla «Estado inicial»: «a realizar»; en una entrega de suministro, `no_confirmado`; en una de compra-venta, no aplica."""
        venta, det, r = self.venta_lista()
        self.assertIsNone(self.una(entregas.planificar_venta(venta.pk, HOY)).entrega.estado_confirmacion_cliente)
        s, d, fecha, rs = self.periodo_listo()
        self.assertEqual(self.una(entregas.planificar_periodo(d.pk, fecha, HOY)).entrega.estado_confirmacion_cliente, "no_confirmado")

    def test_regla_seleccion_gana_el_transportista_con_menos_entregas_ese_dia(self):
        """Regla «Selección del transportista»: entre los candidatos, el que menos entregas tiene en esa fecha."""
        otro = transportista_con_vehiculo(self.e.invernadero, "800")
        v1, d1, r1 = self.venta_lista(10)
        entrega(v1, [r1], transportista=self.t)
        v2, d2, r2 = self.venta_lista(10)
        self.assertEqual(self.una(entregas.planificar_venta(v2.pk, HOY)).transportista.pk, otro.pk)

    def test_regla_invernadero_inactivo_no_se_planifica_nada(self):
        """Disparador «Cuando exista un caso de uso que planifique…» (regla 4 de PROD-BAJ-INV): nada con origen en un invernadero inactivo."""
        venta, det, r = self.venta_lista()
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(entregas.planificar_venta(venta.pk, HOY), [])
        self.assertEqual(Entrega.objects.count(), 0)

    # ---- postcondiciones ----

    def test_post_a_la_entrega_nace_sin_agronomo_con_fecha_de_creacion_de_hoy(self):
        """Postcondición a: «a realizar», fecha de creación igual a hoy y sin Agrónomo planificador (la planificó InfoPonia)."""
        venta, det, r = self.venta_lista()
        e = Entrega.objects.get(pk=self.una(entregas.planificar_venta(venta.pk, HOY)).entrega.pk)
        self.assertEqual((e.fecha_creacion_orden, e.agronomo_id, e.numero > 0), (HOY, None, True))

    def test_post_b_la_linea_satisface_su_detalle_y_deja_vacios_los_datos_de_la_concrecion(self):
        """Postcondición b: un detalle de entrega por detalle de venta, con sus reservas y su precio; la cantidad entregada y los montos, vacíos."""
        venta, det, r = self.venta_lista()
        otra = self.otra_variedad("Rúcula")
        det2 = detalle(venta, otra, 40)
        reserva_lista(det2, lote_maduro(self.e, 100, variedad=otra), 40)
        e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        self.assertEqual(e.lineas.count(), 2)
        self.assertEqual({l.detalle_venta_id for l in e.lineas.all()}, {det.pk, det2.pk})
        self.assertTrue(all(l.cant_entregada is None and l.monto_pagar is None for l in e.lineas.all()))

    def test_post_c_se_asigna_el_transportista_y_se_le_avisa(self):
        """Postcondición c y paso 9: «Nueva entrega para el 26/11» con el código, el cliente, el destino, el peso y el contenido."""
        venta, det, r = self.venta_lista()
        e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        aviso = self.avisos(self.t)[0]
        self.assertEqual(aviso.titulo, f"Nueva entrega para el {e.fecha_programada_orden:%d/%m}")
        self.assertIn(e.codigo, aviso.detalle)
        self.assertIn("15,00 kg: 100 ", aviso.detalle)
        self.assertIn(venta.cliente.nombre_visible, aviso.detalle)

    def test_post_d_sin_transportista_hay_alerta_para_el_gerente_y_aviso_al_vendedor(self):
        """Postcondición d y extensión 6a: la entrega queda sin transportista, con la alerta «entrega sin transportista» (con el motivo) y la notificación al Vendedor."""
        self.sin_flota()
        venta, det, r = self.venta_lista()
        resultado = self.una(entregas.planificar_venta(venta.pk, HOY))
        e = resultado.entrega
        self.assertIsNone(e.transportista_id)
        self.assertEqual(resultado.motivo, "sin transportistas activos con vehículo activo")
        vinculo = AlertaComercial.objects.get(entrega=e)
        self.assertEqual(
            (vinculo.alerta.tipo_alerta, vinculo.alerta.estado_alerta, vinculo.alerta.para_gerente, vinculo.alerta.clave_estado),
            (TIPO, "activa", True, f"entrega:{e.pk}"),
        )
        self.assertEqual(
            vinculo.alerta.descripcion_alerta,
            f"{e.codigo} del {e.fecha_programada_orden:%d/%m} ({venta.cliente.nombre_visible}) sin transportista: sin transportistas activos con vehículo activo",
        )
        aviso = self.avisos(self.e.vendedor)[0]
        self.assertEqual(aviso.titulo, f"Entrega sin transportista: {e.codigo}")
        self.assertIn("Motivo: sin transportistas activos con vehículo activo", aviso.detalle)

    def test_ext_6a_cada_motivo_queda_en_la_alerta(self):
        """Extensión 6a.2: capacidad de carga insuficiente, en ruta, máximo de entregas y de localidades, cada uno en el motivo de la alerta."""
        chico = transportista_con_vehiculo(self.e.invernadero, "5")
        self.t.invernadero_asignado.delete()
        venta, det, r = self.venta_lista(100)  # 15 kg > 5 kg
        self.assertEqual(self.una(entregas.planificar_venta(venta.pk, HOY)).motivo, "capacidad de carga insuficiente")
        chico.invernadero_asignado.delete()
        en_ruta = transportista_con_vehiculo(self.e.invernadero, "800", en_ruta=True)
        venta, det, r = self.venta_lista(10, dias=0)
        self.assertEqual(self.una(entregas.planificar_venta(venta.pk, HOY)).motivo, "en ruta")
        en_ruta.invernadero_asignado.delete()
        ConfiguracionOperativa.objects.update(cant_maxima_entregas_diarias=1)
        lleno = transportista_con_vehiculo(self.e.invernadero, "800")
        v1, d1, r1 = self.venta_lista(10, dias=5)
        entrega(v1, [r1], transportista=lleno)
        v2, d2, r2 = self.venta_lista(10, dias=5)
        self.assertEqual(self.una(entregas.planificar_venta(v2.pk, HOY)).motivo, "máximo de entregas diarias")

    def test_post_e_ext_2a_un_retiro_se_planifica_sin_transportista_y_avisa_al_vendedor(self):
        """Postcondición e y extensión 2a: una sola entrega con origen y destino en el invernadero de retiro, sin transportista y sin alerta; «Retiro planificado» al Vendedor."""
        venta, det, r = self.venta_lista(modalidad="retiro")
        e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        self.assertEqual((e.modalidad_entrega, e.direccion_destino_id, e.transportista_id, e.invernadero_id), ("retiro", None, None, self.e.invernadero.pk))
        self.assertFalse(AlertaComercial.objects.filter(entrega=e).exists())
        self.assertEqual(self.avisos(self.t), [])
        aviso = self.avisos(self.e.vendedor)[0]
        self.assertEqual(aviso.titulo, f"Retiro planificado: {e.codigo}")
        self.assertIn("Lo concretás vos cuando el cliente venga.", aviso.detalle)

    def test_ext_3a_post_g_con_la_fecha_prometida_pasada_sale_hoy_y_avisa_el_retraso(self):
        """Extensión 3a y postcondición g: la fecha programada es hoy y el Vendedor recibe «Entrega con retraso» con la fecha prometida."""
        venta, det, r = self.venta_lista(dias=-2)
        e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        self.assertEqual(e.fecha_programada_orden, HOY)
        aviso = next(a for a in self.avisos(self.e.vendedor) if a.titulo.startswith("Entrega con retraso"))
        self.assertEqual(aviso.detalle, f"La fecha prometida era el {HOY - timedelta(days=2):%d/%m} y sale el {HOY:%d/%m}.")

    def test_ext_3a_en_un_suministro_el_retraso_advierte_de_la_queja_o_la_indemnizacion(self):
        """Postcondición g: en un suministro, la notificación advierte que puede haber una queja o una indemnización."""
        s, d, fecha, rs = self.periodo_listo(primera_en_dias=-3)
        self.una(entregas.planificar_periodo(d.pk, fecha, HOY))
        aviso = next(a for a in self.avisos(self.e.vendedor) if a.titulo.startswith("Entrega con retraso"))
        self.assertIn("Puede haber una queja o una indemnización según la cláusula del suministrante.", aviso.detalle)

    def test_ext_1a_un_periodo_de_un_detalle_finalizado_con_fecha_dentro_del_fin_se_planifica(self):
        """Extensión 1a y D-64 punto 8: el período de un detalle «finalizado» con fecha hasta su `fecha_fin_detalle` se debe y se planifica; uno posterior, no."""
        s, d, fecha, rs = self.periodo_listo()
        d.estado_detalle_suministro, d.fecha_fin_detalle = "finalizado", fecha
        d.save()
        self.assertEqual(len(entregas.planificar_periodo(d.pk, fecha, HOY)), 1)
        s2, d2, fecha2, rs2 = self.periodo_listo()
        d2.estado_detalle_suministro, d2.fecha_fin_detalle = "finalizado", fecha2 - timedelta(days=1)
        d2.save()
        self.assertEqual(entregas.planificar_periodo(d2.pk, fecha2, HOY), [])

    def test_ext_1a_un_suministro_no_vigente_no_se_planifica(self):
        """Precondición c: el contrato y el detalle tienen que estar «vigentes»."""
        s, d, fecha, rs = self.periodo_listo()
        s.estado_suministro = "finalizado"
        s.save()
        self.assertEqual(entregas.planificar_periodo(d.pk, fecha, HOY), [])

    def test_ext_4a_las_lineas_de_otro_detalle_se_agregan_a_la_entrega_existente_y_se_avisa(self):
        """Extensión 4a y postcondición f: con el mismo contrato, invernadero, destino y fecha, las líneas nuevas se agregan a la entrega «a realizar», se avisa al transportista y no se crea otra."""
        otra = self.otra_variedad("Rúcula")
        s = suministro(self.e)
        d1 = detalle_suministro(s, self.e.variedad, cantidad=100, primera_en_dias=3)
        d2 = detalle_suministro(s, otra, cantidad=40, primera_en_dias=3)
        fecha = d1.fecha_primer_entrega
        reserva_lista(None, self.lote, 100, fecha_entrega=fecha, detalle_suministro=d1)
        primera = self.una(entregas.planificar_periodo(d1.pk, fecha, HOY))
        reserva_lista(None, lote_maduro(self.e, 100, variedad=otra), 40, fecha_entrega=fecha, detalle_suministro=d2)
        segunda = self.una(entregas.planificar_periodo(d2.pk, fecha, HOY))
        self.assertEqual((segunda.creada, segunda.agrupada, segunda.entrega.pk), (False, True, primera.entrega.pk))
        self.assertEqual(Entrega.objects.count(), 1)
        self.assertEqual(primera.entrega.lineas.count(), 2)
        aviso = [a for a in self.avisos(self.t) if a.titulo.startswith("Cambió la entrega")]
        self.assertEqual(len(aviso), 1)
        self.assertIn(f"Se agregaron 40 {otra} de ", aviso[0].detalle)
        self.assertTrue(RegistroAuditoria.objects.filter(accion="modificacion_entrega").exists())
        verificar_invariantes_de_entregas()

    def test_d66_7_las_reservas_nuevas_de_una_venta_se_suman_a_la_linea_de_su_entrega(self):
        """D-66 punto 7: tras un recorte y una nueva cobertura, las reservas listas sin línea de una venta se agregan a la línea de su detalle en la entrega «a realizar» (no hay una segunda entrega)."""
        venta, det, r = self.venta_lista(60)
        primera = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        nueva = reserva_lista(det, self.lote, 30)
        resultado = self.una(entregas.planificar_venta(venta.pk, HOY))
        self.assertEqual((resultado.agrupada, resultado.entrega.pk), (True, primera.pk))
        linea = primera.lineas.get()
        self.assertEqual(sorted(linea.reservas.values_list("pk", flat=True)), sorted([r.pk, nueva.pk]))
        self.assertEqual(entregas.cantidades_planificadas([linea.pk])[linea.pk], 90)
        verificar_invariantes_de_entregas()

    def test_ext_4a_si_la_entrega_tiene_envasado_se_arma_una_nueva(self):
        """Condición de agrupamiento: con envasado planificado (reserva de insumo activa) no se agrega: se arma una entrega nueva."""
        from produccion.tests.fabricas import reservar

        venta, det, r = self.venta_lista(60)
        primera = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        reservar(primera, self.e.existencia_semilla, 1)
        reserva_lista(det, self.lote, 30)
        segunda = self.una(entregas.planificar_venta(venta.pk, HOY))
        self.assertTrue(segunda.creada)
        self.assertNotEqual(segunda.entrega.pk, primera.pk)

    def test_ext_8b_una_reserva_ya_planificada_no_se_planifica_dos_veces(self):
        """Extensión 8b: planificar dos veces la misma venta deja una sola entrega (la segunda no encuentra nada sin línea)."""
        venta, det, r = self.venta_lista()
        self.una(entregas.planificar_venta(venta.pk, HOY))
        self.assertEqual(entregas.planificar_venta(venta.pk, HOY), [])
        self.assertEqual(Entrega.objects.count(), 1)

    def test_ext_8b_una_reserva_que_dejo_de_estar_lista_mientras_se_bloqueaba_no_se_registra(self):
        """Extensión 8b: si al registrar la reserva ya no está «lista para entrega» (otra operación la liberó mientras esperaba el bloqueo), la entrega no se registra."""
        venta, det, r = self.venta_lista()
        original = entregas.bloquear_invernadero_activo

        def liberar_y_bloquear(invernadero_id):
            ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="liberada")
            return original(invernadero_id)

        with mock.patch.object(entregas, "bloquear_invernadero_activo", side_effect=liberar_y_bloquear):
            self.assertEqual(entregas.planificar_venta(venta.pk, HOY), [])
        self.assertEqual(Entrega.objects.count(), 0)

    def test_ext_a_un_invernadero_que_falla_no_corta_a_los_demas(self):
        """Extensión \\*a: si un invernadero falla, su entrega se revierte y se registra con `logger.exception`; la del otro invernadero queda registrada."""
        sur = segundo_invernadero(self.e)
        transportista_con_vehiculo(sur.invernadero, "800")
        venta, det, _ = self.venta_lista(40)
        reserva_lista(det, lote_maduro(sur, 500), 30)
        original, llamadas = entregas.seleccionar, []

        def falla_la_primera(candidatos):
            llamadas.append(1)
            if len(llamadas) == 1:
                raise RuntimeError("falla de prueba")
            return original(candidatos)

        with mock.patch.object(entregas, "seleccionar", side_effect=falla_la_primera), self.assertLogs("infoponia.entregas", "ERROR"):
            resultados = entregas.planificar_venta(venta.pk, HOY)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(Entrega.objects.count(), 1)

    def test_post_m_la_auditoria_la_escribe_infoponia_con_la_entrega_y_sus_reservas(self):
        """Postcondición m y D-27: UN registro `planificacion_entrega` por entrega creada, sin usuario (proceso automático), con la entrega, sus líneas y sus reservas."""
        venta, det, r = self.venta_lista()
        e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        registro = RegistroAuditoria.objects.get(accion="planificacion_entrega")
        self.assertIsNone(registro.usuario_id)
        self.assertTrue(any(a["id"] == e.pk and a["texto"] == e.codigo for a in registro.afectados))
        self.assertTrue(any(a["id"] == r.pk and a["texto"] == str(r) for a in registro.afectados))
        self.assertEqual(registro.detalle["datos"]["peso"], "15.00")

    # ---- postcondición i: el correo al cliente ----

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_i_el_correo_sale_despues_de_confirmar_con_la_fecha_el_destino_y_las_variedades(self):
        """Postcondición i y paso 11: después de confirmar (`on_commit`) el cliente recibe la fecha, el destino y las variedades y cantidades; la entrega queda «enviado»."""
        venta, det, r = self.venta_lista()
        with self.captureOnCommitCallbacks(execute=True):
            e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [venta.cliente.email_cliente])
        self.assertEqual(mail.outbox[0].subject, f"Tu entrega del {e.fecha_programada_orden:%d/%m} ({e.codigo})")
        self.assertIn("100 ", mail.outbox[0].body)
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_aviso_cliente, "enviado")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_9_11a_si_el_correo_falla_la_entrega_queda_pendiente_de_envio(self):
        """Extensión 9-11a: la entrega permanece registrada y el aviso queda «pendiente de envío» (lo reintenta el paso 50)."""
        venta, det, r = self.venta_lista()
        with mock.patch.object(correo, "enviar_correo", return_value=False), self.captureOnCommitCallbacks(execute=True):
            e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_aviso_cliente, "pendiente_envio")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_9_11a_un_cliente_sin_correo_no_recibe_nada(self):
        """D-66 punto 12: un cliente de compra-venta sin correo queda `sin_correo` y no se intenta nada."""
        self.e.cliente.email_cliente = ""
        self.e.cliente.save()
        venta, det, r = self.venta_lista()
        with self.captureOnCommitCallbacks(execute=True):
            e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        self.assertEqual(mail.outbox, [])
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_aviso_cliente, "sin_correo")

    def test_post_i_sin_el_correo_del_sistema_configurado_queda_pendiente_de_envio(self):
        """Sin el correo del sistema configurado no se envía: el aviso queda «pendiente de envío» y no se pierde."""
        venta, det, r = self.venta_lista()
        with self.captureOnCommitCallbacks(execute=True):
            e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        self.assertEqual((mail.outbox, Entrega.objects.get(pk=e.pk).estado_aviso_cliente), ([], "pendiente_envio"))

    # ---- los disparadores ----

    def test_d66_5_los_disparadores_no_planifican_dentro_de_la_transaccion_de_quien_llama(self):
        """D-66 punto 5: `programar_planificacion_de_venta` solo registra un `on_commit`; la entrega nace cuando se confirma, sin demorar a quien dispara."""
        venta, det, r = self.venta_lista()
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            entregas.programar_planificacion_de_venta(venta.pk)
            self.assertEqual(Entrega.objects.count(), 0)
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        self.assertEqual(Entrega.objects.count(), 1)

    def test_d66_5_el_disparador_de_un_periodo_hace_lo_mismo(self):
        """Lo mismo para `programar_planificacion_de_periodo`."""
        s, d, fecha, rs = self.periodo_listo()
        with self.captureOnCommitCallbacks(execute=True):
            entregas.programar_planificacion_de_periodo(d.pk, fecha)
        self.assertEqual(Entrega.objects.count(), 1)

    def test_d66_5_una_falla_del_disparador_no_vuelve_a_quien_disparo(self):
        """D-66 punto 5: una excepción al planificar se registra y no llega a quien disparó (su operación ya quedó registrada)."""
        venta, det, r = self.venta_lista()
        with mock.patch.object(entregas, "_planificar", side_effect=RuntimeError("falla")), self.assertLogs("infoponia.entregas", "ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                entregas.programar_planificacion_de_venta(venta.pk)

    def test_d66_5_programar_para_reservas_solo_programa_lo_que_quedo_listo(self):
        """`programar_para_reservas` registra un `on_commit` por venta o período con reservas «lista para entrega»; una reserva sin contrato o «activa» no programa nada."""
        venta, det, r = self.venta_lista()
        activa = reserva_lista(det, self.lote, 1)
        ReservaStock.objects.filter(pk=activa.pk).update(estado_reserva="activa")
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            entregas.programar_para_reservas([r.pk, activa.pk, None])
            entregas.programar_para_reservas([activa.pk])
        self.assertEqual(len(callbacks), 1)


class ComPnfEntDiariaTests(Base):
    def entrega_vieja(self, venta, reserva, *, dias_de_creada=1, **opciones):
        """Una entrega creada antes de hoy (la búsqueda diaria las toma; las de hoy ya se buscaron al crearlas)."""
        e = entrega(venta, [reserva], **opciones)
        Entrega.objects.filter(pk=e.pk).update(fecha_creacion_orden=min(HOY, e.fecha_programada_orden) - timedelta(days=dias_de_creada))
        return Entrega.objects.get(pk=e.pk)

    def con_flota(self):
        return transportista_con_vehiculo(self.e.invernadero, "800")

    # ---- parte 1: recuperación (l) ----

    def test_post_l_la_recuperacion_planifica_lo_listo_que_no_tiene_entrega(self):
        """Postcondición l y parte 1: una venta y un período listos sin entrega se planifican; el resumen cuenta lo creado."""
        venta, det, r = self.venta_lista()
        s, d, fecha, rs = self.periodo_listo()
        resumen = entregas.planificar_entregas(HOY)
        self.assertEqual(Entrega.objects.count(), 2)
        self.assertEqual(resumen.creados, 2)
        verificar_invariantes_de_entregas()

    def test_regla_recuperacion_dos_corridas_el_mismo_dia_no_crean_ni_avisan_nada_nuevo(self):
        """Idempotencia: la segunda corrida del día no crea entregas ni avisos nuevos."""
        venta, det, r = self.venta_lista()
        entregas.planificar_entregas(HOY)
        avisos = Notificacion.objects.count()
        segunda = entregas.planificar_entregas(HOY)
        self.assertEqual((segunda.creados, segunda.resueltos, Notificacion.objects.count(), Entrega.objects.count()), (0, 0, avisos, 1))

    def test_regla_recuperacion_no_toma_una_venta_cancelada_ni_con_entrega(self):
        """La recuperación no planifica una venta que ya tiene entrega ni una cancelada."""
        venta, det, r = self.venta_lista()
        entrega(venta, [r])
        cancelada, d2, r2 = self.venta_lista(estado="cancelada")
        self.assertEqual(entregas.planificar_entregas(HOY).creados, 0)

    # ---- parte 2: búsqueda de transportista (j y k) ----

    def test_post_j_se_asigna_el_transportista_la_alerta_se_resuelve_y_se_avisa(self):
        """Postcondición j y extensión 1b.4: la entrega sin transportista recibe uno; se avisa a él y al Vendedor; la alerta del Gerente queda resuelta; auditoría `asignacion_transportista`."""
        self.sin_flota()
        venta, det, r = self.venta_lista()
        e = self.una(entregas.planificar_venta(venta.pk, HOY)).entrega
        Entrega.objects.filter(pk=e.pk).update(fecha_creacion_orden=HOY - timedelta(days=1))
        nuevo = self.con_flota()
        resumen = entregas.planificar_entregas(HOY)
        e.refresh_from_db()
        self.assertEqual(e.transportista_id, nuevo.pk)
        alerta = AlertaComercial.objects.get(entrega=e).alerta
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertEqual(resumen.resueltos, 1)
        self.assertIn(f"Nueva entrega para el {e.fecha_programada_orden:%d/%m}", self.titulos(nuevo))
        self.assertIn(f"{e.codigo} ya tiene transportista", self.titulos(self.e.vendedor))
        registro = RegistroAuditoria.objects.get(accion="asignacion_transportista")
        self.assertIsNone(registro.usuario_id)
        self.assertEqual(entregas.planificar_entregas(HOY).resueltos, 0)  # una segunda corrida no hace nada nuevo
        verificar_invariantes_de_entregas()

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_j_con_la_fecha_pasada_pasa_a_hoy_avisa_el_retraso_y_manda_el_correo_con_la_nueva_fecha(self):
        """Postcondición j: si la fecha programada había pasado, pasa a hoy, el Vendedor recibe el aviso de retraso y el cliente, el correo «Cambió la fecha de tu entrega»."""
        venta, det, r = self.venta_lista(dias=0)
        e = self.entrega_vieja(venta, r, fecha=HOY - timedelta(days=3), aviso="enviado")
        with self.captureOnCommitCallbacks(execute=True):
            entregas.planificar_entregas(HOY)
        e.refresh_from_db()
        self.assertEqual((e.fecha_programada_orden, e.transportista_id), (HOY, self.t.pk))
        self.assertTrue(any(t.startswith("Entrega con retraso") for t in self.titulos(self.e.vendedor)))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, f"Cambió la fecha de tu entrega {e.codigo}: ahora es el {HOY:%d/%m}")
        self.assertEqual(e.estado_aviso_cliente, "enviado")

    def test_post_k_sin_transportista_y_para_manana_sale_un_unico_recordatorio(self):
        """Postcondición k: si no hay transportista y la fecha programada es mañana, un único recordatorio al Gerente y al Vendedor; una segunda corrida no manda otro."""
        self.sin_flota()
        venta, det, r = self.venta_lista(dias=1)
        e = self.entrega_vieja(venta, r)
        entregas.planificar_entregas(HOY)
        titulo = f"Mañana sale {e.codigo} sin transportista"
        self.assertEqual(self.titulos(self.gerente).count(titulo), 1)
        self.assertEqual(self.titulos(self.e.vendedor).count(titulo), 1)
        e.refresh_from_db()
        self.assertEqual(e.recordatorio_para, e.fecha_programada_orden)
        entregas.planificar_entregas(HOY)
        self.assertEqual(self.titulos(self.gerente).count(titulo), 1)

    def test_post_k_si_la_fecha_cambia_el_recordatorio_puede_volver_a_salir(self):
        """D-66 punto 6: «único» se guarda como la fecha programada avisada; con una fecha nueva, el aviso puede salir otra vez."""
        self.sin_flota()
        venta, det, r = self.venta_lista(dias=1)
        e = self.entrega_vieja(venta, r)
        Entrega.objects.filter(pk=e.pk).update(recordatorio_para=HOY - timedelta(days=5))
        entregas.planificar_entregas(HOY)
        self.assertEqual(self.titulos(self.gerente).count(f"Mañana sale {e.codigo} sin transportista"), 1)

    def test_post_k_en_cualquier_otro_caso_la_entrega_queda_sin_cambios_y_sin_avisos(self):
        """Postcondición k y extensión 1b.6: si no hay transportista y la fecha programada no es mañana, no se avisa nada."""
        self.sin_flota()
        venta, det, r = self.venta_lista(dias=5)
        e = self.entrega_vieja(venta, r)
        resumen = entregas.planificar_entregas(HOY)
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertIn("1 entregas siguen sin transportista", resumen.detalle)
        e.refresh_from_db()
        self.assertIsNone(e.recordatorio_para)

    def test_regla_las_entregas_creadas_hoy_no_se_buscan_ni_reciben_recordatorio(self):
        """Parte 2: las creadas hoy ya se buscaron al crearlas; así no salen dos avisos el mismo día."""
        self.sin_flota()
        venta, det, r = self.venta_lista(dias=1)
        entrega(venta, [r])  # creada hoy
        entregas.planificar_entregas(HOY)
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_regla_los_retiros_no_entran_en_la_busqueda_de_transportista(self):
        """Regla «Entrega sin transportista»: los retiros no entran en la búsqueda diaria, pero sí en la recuperación."""
        venta, det, r = self.venta_lista(modalidad="retiro", dias=1)
        e = self.entrega_vieja(venta, r)
        entregas.planificar_entregas(HOY)
        e.refresh_from_db()
        self.assertIsNone(e.transportista_id)

    def test_regla_un_invernadero_inactivo_no_se_reintenta(self):
        """Disparador «Cuando exista un caso de uso que… reintente entregas»: el paso 50 no toca un invernadero inactivo."""
        venta, det, r = self.venta_lista()
        e = self.entrega_vieja(venta, r)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        entregas.planificar_entregas(HOY)
        e.refresh_from_db()
        self.assertIsNone(e.transportista_id)

    # ---- parte 3: atrasadas con transportista (n) ----

    def test_post_n_la_atrasada_con_transportista_se_avisa_una_vez(self):
        """Postcondición n (PCU 8): un aviso al Vendedor y al Gerente por la entrega atrasada con transportista; no cambia nada más; una segunda corrida no vuelve a avisar."""
        venta, det, r = self.venta_lista()
        e = entrega(venta, [r], fecha=HOY - timedelta(days=2), transportista=self.t)
        entregas.planificar_entregas(HOY)
        titulo = f"Entrega atrasada: {e.codigo}"
        self.assertEqual(self.titulos(self.gerente).count(titulo), 1)
        self.assertEqual(self.titulos(self.e.vendedor).count(titulo), 1)
        e.refresh_from_db()
        self.assertEqual((e.aviso_atrasada_para, e.transportista_id, e.fecha_programada_orden), (HOY - timedelta(days=2), self.t.pk, HOY - timedelta(days=2)))
        entregas.planificar_entregas(HOY)
        self.assertEqual(self.titulos(self.gerente).count(titulo), 1)

    def test_post_n_si_cambia_la_fecha_programada_el_aviso_vuelve_a_salir(self):
        """D-66 punto 6: «único» es por fecha programada: con otra fecha atrasada, el aviso sale de nuevo."""
        venta, det, r = self.venta_lista()
        e = entrega(venta, [r], fecha=HOY - timedelta(days=2), transportista=self.t)
        entregas.planificar_entregas(HOY)
        Entrega.objects.filter(pk=e.pk).update(fecha_programada_orden=HOY - timedelta(days=1))
        entregas.planificar_entregas(HOY)
        self.assertEqual(self.titulos(self.gerente).count(f"Entrega atrasada: {e.codigo}"), 2)

    def test_post_n_una_entrega_de_hoy_o_sin_transportista_no_se_avisa_como_atrasada(self):
        """Solo las atrasadas (fecha anterior a hoy) y con transportista."""
        v1, d1, r1 = self.venta_lista()
        entrega(v1, [r1], fecha=HOY, transportista=self.t)
        entregas.planificar_entregas(HOY)
        self.assertFalse(any(t.startswith("Entrega atrasada") for t in self.titulos(self.gerente)))

    # ---- parte 4: reintento de los correos ----

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_9_11a_el_paso_50_reintenta_los_correos_pendientes(self):
        """Extensión 9-11a (D-66 punto 12): las entregas «a realizar» con el aviso «pendiente de envío» reciben el correo en el paso 50; una vez enviado, no se repite."""
        venta, det, r = self.venta_lista()
        e = entrega(venta, [r], transportista=self.t, aviso="pendiente_envio")
        entregas.planificar_entregas(HOY)
        e.refresh_from_db()
        self.assertEqual((e.estado_aviso_cliente, len(mail.outbox)), ("enviado", 1))
        entregas.planificar_entregas(HOY)
        self.assertEqual(len(mail.outbox), 1)

    # ---- fallas y registro ----

    def test_ext_a_un_elemento_que_falla_no_corta_a_los_demas(self):
        """D-56 punto 5: una entrega que falla se registra con `logger.exception` y las demás se buscan igual."""
        self.sin_flota()
        v1, d1, r1 = self.venta_lista(dias=5)
        v2, d2, r2 = self.venta_lista(dias=5)
        primera = self.entrega_vieja(v1, r1)
        segunda = self.entrega_vieja(v2, r2)
        self.con_flota()
        original, llamadas = entregas._buscar_transportista, []

        def falla_la_primera(entrega_id, hoy):
            llamadas.append(entrega_id)
            if len(llamadas) == 1:
                raise RuntimeError("falla de prueba")
            return original(entrega_id, hoy)

        with mock.patch.object(entregas, "_buscar_transportista", side_effect=falla_la_primera), self.assertLogs("infoponia.entregas", "ERROR"):
            entregas.planificar_entregas(HOY)
        primera.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual((primera.transportista_id, segunda.transportista_id is not None), (None, True))

    def test_regla_el_paso_50_esta_registrado_y_proceso_diario_lo_lista(self):
        """El paso 50 se registra en `ComercialConfig.ready()` con `planificar_entregas` y `proceso_diario --listar` lo muestra."""
        salida = StringIO()
        call_command("proceso_diario", "--listar", stdout=salida)
        self.assertIn("planificar_entregas", salida.getvalue())
        self.assertIn("50", salida.getvalue())

    def test_regla_el_resumen_cuenta_lo_revisado_creado_y_resuelto(self):
        """`ResumenDePaso(procesados, creados, resueltos, detalle)` con «N entregas siguen sin transportista»."""
        self.sin_flota()
        venta, det, r = self.venta_lista(dias=9)
        resumen = entregas.planificar_entregas(HOY)
        self.assertEqual((resumen.creados, resumen.resueltos), (1, 0))
        self.assertGreaterEqual(resumen.procesados, 1)
        self.assertEqual(resumen.detalle, "1 entregas siguen sin transportista")
