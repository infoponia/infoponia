# Pruebas de lo que COM-05a1 completa en otras tareas (paso 6; docs/casos_de_uso/comercial/entregas.md, «Lo que completa a otras tareas»): la «Logística» de la ficha del invernadero
# (`entregas_a_realizar` y `url_entregas`), el impedimento `transportista_con_entregas`, «Entregas a realizar: N» y el efecto de la baja de la cuenta de un Transportista, las reglas de los
# vehículos que usan las entregas con datos reales (reglas 2 y 3 de COM-MOD-VEH, precondición c y regla 1 de COM-BAJ-VEH) y el enlace de la alerta «entrega sin transportista».
# Las tres pruebas mínimas de cada registrante: con datos, neutro sin datos, sin consultas por fila. Las pruebas de `test_com_mod_veh.py` y `test_com_baj_veh.py` que usan `mock.patch`
# siguen en pie (prueban el cableado); acá se suman las de datos reales.

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega, Vehiculo
from comercial.servicios import entregas, rutas, vehiculos
from comercial.tests.fabricas import (
    compra_venta,
    datos_de_vehiculo_de,
    detalle,
    entrega,
    escenario_comercial,
    iniciar_ruta_de,
    reserva_lista,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
)
from core import extensiones as extensiones_de_core
from core.models import Notificacion, RegistroAuditoria
from core.servicios import baja_usuario
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros import extensiones as extensiones_de_maestros
from maestros.models import TransportistaInvernadero
from maestros.servicios import transportistas as servicio_de_transportistas
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.gerente = crear_gerente()
        cls.t = transportista_con_vehiculo(cls.e.invernadero, "800")

    def entrega_de(self, cantidad=100, transportista=None, dias=3, **opciones):
        venta = compra_venta(self.e, dias=dias)
        det = detalle(venta, self.e.variedad, cantidad)
        return venta, entrega(venta, [reserva_lista(det, self.lote, cantidad)], transportista=transportista, **opciones)

    def titulos(self, cuenta):
        return [n.titulo for n in Notificacion.objects.filter(destinatario=cuenta).order_by("pk")]


class LogisticaTests(Base):
    def test_ext_con_datos_las_entregas_a_realizar_y_la_url_de_la_lista_filtrada(self):
        """MAE-05, punto 3 de «Cuando exista Entrega»: `entregas_a_realizar` cuenta las «a realizar» del transportista (no las concretadas ni las canceladas) y `url_entregas` es la lista con `?transportista=<id>`."""
        self.entrega_de(transportista=self.t)
        self.entrega_de(transportista=self.t)
        self.entrega_de(transportista=self.t, estado="concretada")
        self.entrega_de(transportista=self.t, estado="cancelada")
        logistica = vehiculos.logistica_de_transportistas([self.t])[self.t.pk]
        self.assertEqual((logistica.entregas_a_realizar, logistica.url_entregas), (2, reverse("comercial:entregas") + f"?transportista={self.t.pk}"))

    def test_ext_neutro_sin_entregas_son_cero_y_sin_url(self):
        """Neutro sin datos: 0 entregas y `url_entregas=None` (nada que ver)."""
        logistica = vehiculos.logistica_de_transportistas([self.t])[self.t.pk]
        self.assertEqual((logistica.entregas_a_realizar, logistica.url_entregas), (0, None))

    def test_ext_sin_consultas_por_fila(self):
        """Interfaz: las mismas consultas con un transportista que con varios."""
        with CaptureQueriesContext(connection) as pocas:
            vehiculos.logistica_de_transportistas([self.t])
        otros = [transportista_con_vehiculo(self.e.invernadero) for _ in range(3)]
        for otro in otros:
            self.entrega_de(transportista=otro)
        with CaptureQueriesContext(connection) as muchas:
            vehiculos.logistica_de_transportistas([self.t, *otros])
        self.assertEqual(len(pocas), len(muchas))


class ImpedimentoDeTransportistaTests(Base):
    def test_ext_con_datos_dice_cuantas_entregas_y_la_proxima(self):
        """Punto 2: «Tiene N entregas a realizar (la próxima, OT-0231 del 26/11).», cómo resolverlo y a dónde ir (la lista filtrada)."""
        _, lejana = self.entrega_de(transportista=self.t, dias=6)
        _, proxima = self.entrega_de(transportista=self.t, dias=2)
        (impedimento,) = entregas.impedimentos_de_transportista(self.t)
        self.assertEqual(impedimento.codigo, "transportista_con_entregas")
        self.assertEqual(impedimento.texto, f"Tiene 2 entregas a realizar (la próxima, {proxima.codigo} del {proxima.fecha_programada_orden:%d/%m}).")
        self.assertIn("Asignar transportista", impedimento.como_resolver)
        self.assertEqual(impedimento.url, reverse("comercial:entregas") + f"?transportista={self.t.pk}")

    def test_ext_con_una_sola_entrega_el_texto_va_en_singular(self):
        """«Tiene 1 entrega a realizar»."""
        self.entrega_de(transportista=self.t)
        self.assertTrue(entregas.impedimentos_de_transportista(self.t)[0].texto.startswith("Tiene 1 entrega a realizar "))

    def test_ext_neutro_sin_entregas_a_realizar_no_hay_impedimento(self):
        """Neutro: sin entregas «a realizar» (una concretada no cuenta) no se impide nada."""
        self.entrega_de(transportista=self.t, estado="concretada")
        self.assertEqual(entregas.impedimentos_de_transportista(self.t), [])

    def test_ext_esta_registrado_y_quitar_al_transportista_se_rechaza(self):
        """Está registrado en `registrar_impedimento_de_transportista` y quitar al transportista del invernadero se rechaza mientras tenga entregas (regla 9 de PROD-MOD-INV)."""
        self.assertIn(entregas.impedimentos_de_transportista, extensiones_de_maestros._IMPEDIMENTOS_DE_TRANSPORTISTA)
        self.entrega_de(transportista=self.t)
        with self.assertRaises(ValidationError):
            servicio_de_transportistas.quitar_transportista(self.gerente, self.e.invernadero.pk, self.t.pk)
        self.assertTrue(TransportistaInvernadero.objects.filter(transportista=self.t).exists())


class BajaDeCuentaTests(Base):
    def test_ext_asignaciones_con_datos_informa_las_entregas_a_realizar(self):
        """Regla 4 de USR-BAJ-USR: «Entregas a realizar: N»."""
        self.entrega_de(transportista=self.t)
        (asignacion,) = entregas.asignaciones_de_cuenta(self.t)
        self.assertEqual((asignacion.texto, asignacion.cantidad), ("Entregas a realizar", 1))

    def test_ext_asignaciones_neutro_sin_entregas_o_con_otro_rol(self):
        """Neutro: sin entregas, o una cuenta que no es Transportista, nada."""
        self.assertEqual(entregas.asignaciones_de_cuenta(self.t), [])
        self.assertEqual(entregas.asignaciones_de_cuenta(self.e.vendedor), [])

    def test_ext_asignaciones_esta_registrado_en_core(self):
        """Está registrado en `registrar_asignaciones_de_cuenta` y la ventana de baja lo junta."""
        self.entrega_de(transportista=self.t)
        self.assertIn(("Entregas a realizar", 1), [(a.texto, a.cantidad) for a in extensiones_de_core.asignaciones_de_cuenta(self.t)])

    def test_post_g_la_baja_deja_sus_entregas_sin_transportista_con_alerta_y_aviso_al_vendedor(self):
        """Postcondición g de USR-BAJ-USR: las entregas «a realizar» quedan sin transportista, con la alerta (motivo «el transportista fue dado de baja») y la notificación al Vendedor; auditadas en el registro de la baja."""
        venta, e = self.entrega_de(transportista=self.t)
        _, concretada = self.entrega_de(transportista=self.t, estado="concretada")
        baja_usuario(self.gerente, self.t.pk)
        e.refresh_from_db()
        concretada.refresh_from_db()
        self.assertEqual((e.transportista_id, concretada.transportista_id), (None, self.t.pk))
        alerta = AlertaComercial.objects.get(entrega=e).alerta
        self.assertEqual((alerta.estado_alerta, alerta.para_gerente), ("activa", True))
        self.assertIn("el transportista fue dado de baja", alerta.descripcion_alerta)
        self.assertIn(f"Entrega sin transportista: {e.codigo}", self.titulos(self.e.vendedor))
        registro = RegistroAuditoria.objects.filter(accion="baja").latest("pk")
        self.assertEqual(len(registro.detalle["datos"]["entregas_sin_transportista"]), 1)
        self.assertEqual(len(registro.detalle["datos"]["alertas_creadas"]), 1)
        verificar_invariantes_de_entregas()

    def test_post_g_el_paso_50_les_busca_otro_despues_de_la_baja(self):
        """«El paso 50 les busca otro»: con otro transportista en el invernadero, la entrega huérfana lo recibe en la corrida siguiente."""
        venta, e = self.entrega_de(transportista=self.t)
        Entrega.objects.filter(pk=e.pk).update(fecha_creacion_orden=HOY - timedelta(days=1))
        nuevo = transportista_con_vehiculo(self.e.invernadero, "800")
        baja_usuario(self.gerente, self.t.pk)
        entregas.planificar_entregas(HOY)
        e.refresh_from_db()
        self.assertEqual(e.transportista_id, nuevo.pk)
        self.assertEqual(AlertaComercial.objects.get(entrega=e).alerta.estado_alerta, "resuelta")

    def test_ext_efecto_neutro_con_otro_rol_o_sin_entregas(self):
        """Neutro: una cuenta que no es Transportista, o sin entregas, no deja afectados ni datos."""
        self.assertEqual(tuple(entregas.efecto_de_baja_de_cuenta(self.gerente, self.e.vendedor)), ([], {}))
        self.assertEqual(tuple(entregas.efecto_de_baja_de_cuenta(self.gerente, self.t)), ([], {}))

    def test_ext_asignaciones_y_impedimento_sin_consultas_por_fila(self):
        """Interfaz: las dos lecturas (`asignaciones_de_cuenta` e `impedimentos_de_transportista`) hacen las mismas consultas con una entrega que con varias."""
        self.entrega_de(transportista=self.t)
        with CaptureQueriesContext(connection) as pocas:
            entregas.asignaciones_de_cuenta(self.t)
            entregas.impedimentos_de_transportista(self.t)
        for _ in range(3):
            self.entrega_de(transportista=self.t)
        with CaptureQueriesContext(connection) as muchas:
            entregas.asignaciones_de_cuenta(self.t)
            entregas.impedimentos_de_transportista(self.t)
        self.assertEqual(len(pocas), len(muchas))


class VehiculosConEntregasTests(Base):
    """Reglas 2 y 3 de COM-MOD-VEH, precondición c y regla 1 de COM-BAJ-VEH con entregas reales (las pruebas con `mock.patch` siguen en sus archivos)."""

    def modificar(self, **extra):
        return vehiculos.modificar_vehiculo(self.gerente, self.t.vehiculo.pk, datos_de_vehiculo_de(self.t.vehiculo, **extra))

    def test_regla_2_no_se_baja_la_capacidad_por_debajo_de_la_carga_asignada_real(self):
        """Regla 2: 100 plantas × 150 g = 15 kg asignados en un día: bajar la capacidad a 10 kg se rechaza con la fecha y el peso; bajarla a 15 kg se puede."""
        _, e = self.entrega_de(100, transportista=self.t, dias=4)
        with self.assertRaises(ValidationError) as contexto:
            self.modificar(capacidad_carga="10")
        mensaje = contexto.exception.error_dict["capacidad_carga"][0]
        self.assertEqual(mensaje.code, "capacidad_menor_que_la_carga")
        self.assertIn(f"{e.fecha_programada_orden:%d/%m/%Y}", mensaje.messages[0])
        self.assertIn("15", mensaje.messages[0])
        self.assertEqual(self.modificar(capacidad_carga="15").capacidad_carga, Decimal("15.00"))

    def test_regla_2_carga_maxima_asignada_es_el_mayor_peso_de_un_dia_desde_hoy(self):
        """`carga_maxima_asignada(vehiculo, desde)`: la mayor suma del peso de las entregas no canceladas en un día desde `desde`; las canceladas y las anteriores no cuentan."""
        self.entrega_de(100, transportista=self.t, dias=4)  # 15 kg
        self.entrega_de(200, transportista=self.t, dias=4)  # +30 = 45 kg ese día
        self.entrega_de(400, transportista=self.t, dias=6, estado="cancelada")
        self.entrega_de(100, transportista=self.t, dias=2)  # 15 kg otro día
        peso, fecha = vehiculos.carga_maxima_asignada(self.t.vehiculo, HOY)
        self.assertEqual((peso, fecha), (Decimal("45.00"), HOY + timedelta(days=4)))
        self.assertEqual(vehiculos.carga_maxima_asignada(self.t.vehiculo, HOY + timedelta(days=5)), (Decimal("0"), None))

    def test_regla_3_no_se_quita_ni_se_cambia_el_transportista_con_entregas_a_realizar_reales(self):
        """Regla 3: con una entrega «a realizar» real, quitar el transportista del vehículo se rechaza con `transportista_con_entregas`; con una concretada, no."""
        self.entrega_de(transportista=self.t, estado="concretada")
        self.assertIsNone(self.modificar(transportista_id=None).transportista_id)
        self.t.vehiculo.__class__.objects.filter(pk=self.t.vehiculo.pk).update(transportista=self.t)
        self.entrega_de(transportista=self.t)
        with self.assertRaises(ValidationError) as contexto:
            self.modificar(transportista_id=None)
        self.assertEqual(contexto.exception.error_dict["transportista"][0].code, "transportista_con_entregas")

    def test_pre_c_regla_1_no_se_da_de_baja_un_vehiculo_cuyo_transportista_tiene_entregas_reales(self):
        """Precondición c y regla 1 de COM-BAJ-VEH: con entregas «a realizar» del transportista, la baja se rechaza con `transportista_con_entregas`."""
        self.entrega_de(transportista=self.t)
        with self.assertRaises(ValidationError) as contexto:
            vehiculos.baja_vehiculo(self.gerente, self.t.vehiculo.pk)
        self.assertEqual(contexto.exception.error_list[0].code, "transportista_con_entregas")

    def test_regla_1_con_entregas_a_realizar_devuelve_las_del_transportista_ordenadas(self):
        """`entregas_a_realizar_del_transportista`: las «a realizar» por fecha programada e id."""
        _, tarde = self.entrega_de(transportista=self.t, dias=6)
        _, pronto = self.entrega_de(transportista=self.t, dias=2)
        self.entrega_de(transportista=self.t, estado="cancelada")
        self.assertEqual([e.pk for e in vehiculos.entregas_a_realizar_del_transportista(self.t)], [pronto.pk, tarde.pk])


class EnlaceDeLaAlertaTests(Base):
    def alerta_de(self, e, venta):
        return entregas._alerta_sin_transportista(e, venta, "capacidad de carga insuficiente")

    def test_ext_d62_el_gerente_va_a_la_asignacion_de_esa_entrega(self):
        """D-62, 6a y extensión 1b de COM-ASG-TRP (COM-05b): el enlace del Gerente es la pantalla de asignación de esa entrega y el texto «OT-0231 · 26/11 · Pérez SA»; otro rol no recibe enlace."""
        venta, e = self.entrega_de()
        alerta = self.alerta_de(e, venta)
        enlaces = entregas.enlaces_de_alertas(self.gerente, [alerta])
        self.assertEqual(enlaces[alerta.pk].url, reverse("comercial:entrega_asignar", args=[e.pk]))
        self.assertEqual(enlaces[alerta.pk].detalle, f"{e.codigo} · {e.fecha_programada_orden:%d/%m} · {venta.cliente.nombre_visible}")
        self.assertEqual(entregas.enlaces_de_alertas(self.e.vendedor, [alerta]), {})
        self.assertEqual(entregas.enlaces_de_alertas(self.gerente, []), {})

    def test_ext_d62_esta_registrado_para_el_codigo_de_la_alerta(self):
        """Registrado con `registrar_enlace_de_alerta` para `comercial_entrega_sin_transportista` (un solo registrante por código)."""
        codigos = {c for codigos_, _ in extensiones_de_maestros.enlaces_registrados() for c in codigos_}
        self.assertIn(entregas.TIPO_SIN_TRANSPORTISTA, codigos)

class TransportistaEnRutaTests(Base):
    """COM-06a: `transportista_en_ruta` en los dos registrantes (el de `maestros` y el de la baja de cuenta de `core`). Las tres mínimas de cada uno: con datos, neutro, sin consultas por fila."""

    def en_ruta(self, cantidad=1):
        """Un transportista con `cantidad` entregas de hoy y la ruta iniciada de verdad."""
        for _ in range(cantidad):
            self.entrega_de(transportista=self.t, dias=0, fecha=HOY)
        iniciar_ruta_de(self.t)

    def test_ext_en_ruta_con_datos_dice_desde_hoy_con_cuantas_entregas_y_como_resolverlo(self):
        """Reglas 9 y 10 de PROD-MOD-INV: «Está en ruta desde hoy con N entregas.» y «Esperá a que finalice la ruta.» (primero, antes del de las entregas a realizar)."""
        self.en_ruta(2)
        impedimentos = entregas.impedimentos_de_transportista(self.t)
        self.assertEqual([i.codigo for i in impedimentos], ["transportista_en_ruta", "transportista_con_entregas"])
        self.assertEqual((impedimentos[0].texto, impedimentos[0].como_resolver), ("Está en ruta desde hoy con 2 entregas.", "Esperá a que finalice la ruta."))

    def test_ext_en_ruta_con_una_sola_entrega_va_en_singular(self):
        """«Está en ruta desde hoy con 1 entrega.»"""
        self.en_ruta(1)
        self.assertEqual(entregas.impedimentos_de_transportista(self.t)[0].texto, "Está en ruta desde hoy con 1 entrega.")

    def test_ext_en_ruta_neutro_sin_ruta_iniciada_o_con_una_ruta_de_ayer_no_hay_impedimento_de_ruta(self):
        """Neutro: sin ruta, o con una ruta que no se finalizó ayer (vencida, MD-118), no hay `transportista_en_ruta`; finalizar la ruta lo levanta."""
        self.entrega_de(transportista=self.t, dias=0, fecha=HOY)
        self.assertNotIn("transportista_en_ruta", [i.codigo for i in entregas.impedimentos_de_transportista(self.t)])
        Vehiculo.objects.filter(transportista=self.t).update(en_ruta=True, fecha_inicio_ruta=HOY - timedelta(days=1))
        self.assertNotIn("transportista_en_ruta", [i.codigo for i in entregas.impedimentos_de_transportista(self.t)])

    def test_ext_en_ruta_esta_registrado_y_quitar_o_trasladar_al_transportista_se_rechaza_con_su_codigo(self):
        """Está registrado en `registrar_impedimento_de_transportista` y quitar al transportista en ruta se rechaza con `transportista_en_ruta`."""
        self.en_ruta(1)
        with self.assertRaises(ValidationError) as c:
            servicio_de_transportistas.quitar_transportista(self.gerente, self.e.invernadero.pk, self.t.pk)
        self.assertTrue(any("Está en ruta desde hoy" in m for m in c.exception.messages))
        self.assertTrue(TransportistaInvernadero.objects.filter(transportista=self.t).exists())

    def test_ext_en_ruta_sin_consultas_por_fila(self):
        """Las mismas consultas con una entrega que con varias."""
        self.en_ruta(1)
        with CaptureQueriesContext(connection) as pocas:
            entregas.impedimentos_de_transportista(self.t)
        for _ in range(3):
            self.entrega_de(transportista=self.t, dias=0, fecha=HOY)
        with CaptureQueriesContext(connection) as muchas:
            entregas.impedimentos_de_transportista(self.t)
        self.assertEqual(len(pocas), len(muchas))

    def test_ext_baja_con_datos_el_transportista_en_ruta_no_se_da_de_baja(self):
        """Precondición d de USR-BAJ-USR: la baja de la cuenta de un Transportista en ruta se rechaza con `transportista_en_ruta` y no cambia nada."""
        self.en_ruta(1)
        (impedimento,) = entregas.impedimentos_de_baja_de_cuenta(self.t)
        self.assertEqual((impedimento.codigo, impedimento.texto, impedimento.como_resolver), ("transportista_en_ruta", "Está en ruta desde hoy con 1 entrega.", "Esperá a que finalice la ruta."))
        with self.assertRaises(ValidationError) as c:
            baja_usuario(self.gerente, self.t.pk)
        self.assertEqual([e.code for e in c.exception.error_list], ["transportista_en_ruta"])
        self.t.refresh_from_db()
        self.assertTrue(self.t.is_active)

    def test_ext_baja_neutro_con_otro_rol_o_sin_ruta_no_impide(self):
        """Neutro: un Vendedor, o un Transportista sin ruta iniciada, no tiene impedimento."""
        self.entrega_de(transportista=self.t, dias=0, fecha=HOY)
        self.assertEqual(entregas.impedimentos_de_baja_de_cuenta(self.t), [])
        self.assertEqual(entregas.impedimentos_de_baja_de_cuenta(self.e.vendedor), [])

    def test_ext_baja_esta_registrado_en_core_y_se_levanta_al_finalizar_la_ruta(self):
        """Está registrado en `registrar_impedimento_de_baja_de_cuenta`; con la ruta finalizada, la baja se hace (y sus entregas «a realizar» quedan sin transportista)."""
        self.en_ruta(1)
        self.assertEqual([i.codigo for i in extensiones_de_core.impedimentos_de_baja_de_cuenta(self.t)], ["transportista_en_ruta"])
        (e,) = Entrega.objects.filter(transportista=self.t)
        rutas.registrar_intento_fallido(self.t, e.pk, "cliente_ausente", "")
        rutas.finalizar_ruta(self.t)
        self.assertEqual(extensiones_de_core.impedimentos_de_baja_de_cuenta(self.t), [])

    def test_ext_baja_sin_consultas_por_fila(self):
        """Las mismas consultas con una entrega que con varias."""
        self.en_ruta(1)
        with CaptureQueriesContext(connection) as pocas:
            entregas.impedimentos_de_baja_de_cuenta(self.t)
        for _ in range(3):
            self.entrega_de(transportista=self.t, dias=0, fecha=HOY)
        with CaptureQueriesContext(connection) as muchas:
            entregas.impedimentos_de_baja_de_cuenta(self.t)
        self.assertEqual(len(pocas), len(muchas))


class MontoYEstadoDePagoTests(Base):
    """D-68 punto 7: `monto_a_cobrar` y `estado_de_pago` son derivados (no se guardan); «pagada» llega con COM-08a."""

    def test_regla_el_monto_a_cobrar_es_el_total_de_la_entrega_concretada_y_nulo_si_no_lo_esta(self):
        """Hasta COM-07a no hay nada que descontar: el monto a cobrar es el total; una entrega «a realizar» no tiene monto."""
        _, pendiente = self.entrega_de()
        _, concretada = self.entrega_de(estado="concretada", precio="10.00")
        self.assertEqual(entregas.monto_a_cobrar([pendiente.pk, concretada.pk]), {pendiente.pk: None, concretada.pk: Decimal("1000.00")})

    def test_regla_el_estado_de_pago_de_un_suministro_es_pendiente_o_en_mora_segun_el_vencimiento(self):
        """MD-136 y MD-139: «pendiente» hasta el vencimiento y «en mora» después; una compra-venta no tiene estado de pago de entrega."""
        from comercial.tests.fabricas import detalle_suministro, marcar_concretada, suministro

        s = suministro(self.e, plazo_pago=10)
        d = detalle_suministro(s, self.e.variedad, cantidad=10, primera_en_dias=0)
        r = reserva_lista(None, self.lote, 10, fecha_entrega=d.fecha_primer_entrega, detalle_suministro=d)
        e = marcar_concretada(entrega(s, [r], fecha=HOY))
        _, de_venta = self.entrega_de(estado="concretada")
        self.assertEqual(entregas.estado_de_pago([e.pk, de_venta.pk], HOY), {e.pk: "pendiente", de_venta.pk: None})
        self.assertEqual(entregas.estado_de_pago([e.pk], HOY + timedelta(days=10))[e.pk], "pendiente")
        self.assertEqual(entregas.estado_de_pago([e.pk], HOY + timedelta(days=11))[e.pk], "en_mora")
