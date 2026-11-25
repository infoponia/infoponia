# Pruebas de COM-INI-RUT · Iniciar Ruta (COM-06a, paso 2): `rutas.ruta_del_dia` e `rutas.iniciar_ruta`. Una por postcondición (a a c), extensión (1a, 1b, 1c, 2a, 2b, 2c, 5a, 5b, 5c, 5d) y regla
# (las entregas de la ruta, el peso, el orden, más de una ruta en el día, quién lo ejecuta); que iniciar no toca entregas ni reservas; y que con la ruta iniciada de verdad las demás operaciones
# ven la entrega «en curso». Fuente: docs/casos_de_uso/comercial/rutas.md («COM-INI-RUT» y «Cómo se aplica», «Iniciar la ruta»), D-66 punto 11 y MD-118.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from comercial.models import Entrega, ReservaStock, Vehiculo
from comercial.servicios import entregas, rutas
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    entrega,
    envase,
    escenario_comercial,
    reserva_lista,
    segundo_invernadero,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_transportista
from produccion.models import ReservaInsumo
from produccion.tests.fabricas import lote_maduro, reservar

HOY = timezone.localdate()


def codigos(error):
    """Los códigos de un `ValidationError` con o sin `error_dict`."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


def parametros(error):
    """Los `params` del primer error (lo que trae `ruta_cambio` y `ruta_con_entregas_pendientes`)."""
    return next(iter(error.error_dict.values()))[0].params


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, un lote de 5000 y un Transportista con vehículo de 800 kg."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.t = transportista_con_vehiculo(cls.e.invernadero, "800")

    def setUp(self):
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)

    def nueva(self, *, transportista=None, cantidad=10, fecha=None, estado="a_realizar", modalidad="envio", dias=0):
        """Una entrega de una venta nueva (por omisión, de `self.t`, para hoy)."""
        retiro = modalidad == "retiro"
        venta = compra_venta(self.e, dias=dias, modalidad=modalidad)
        det = detalle(venta, self.e.variedad, cantidad)
        r = reserva_lista(det, self.lote, cantidad)
        return entrega(venta, [r], transportista=None if retiro else (transportista or self.t), fecha=fecha, estado=estado)

    def ruta(self, cuenta=None):
        return rutas.ruta_del_dia(cuenta or self.t)

    def iniciar(self, cuenta=None):
        cuenta = cuenta or self.t
        return rutas.iniciar_ruta(cuenta, rutas.ruta_del_dia(cuenta).huella)

    def vehiculo(self):
        return Vehiculo.objects.get(transportista=self.t)


class ComIniRutServicioTests(Base):
    # ---- postcondiciones ----

    def test_post_a_el_vehiculo_queda_en_ruta_con_la_fecha_de_hoy(self):
        """Postcondición a: `en_ruta` pasó a verdadero y `fecha_inicio_ruta` es la fecha actual."""
        self.nueva()
        devuelto = self.iniciar()
        v = self.vehiculo()
        self.assertEqual((v.en_ruta, v.fecha_inicio_ruta, devuelto.pk), (True, HOY, v.pk))
        self.assertTrue(v.esta_en_ruta(HOY))

    def test_post_b_las_entregas_y_sus_reservas_no_cambian(self):
        """Postcondición b y garantía mínima: iniciar no modifica ninguna entrega (estado, fecha, transportista, líneas), ni reserva de stock o de insumo, ni crea consumos."""
        e = self.nueva()
        b = envase(self.e.invernadero)
        reservar(e, b, 5)
        antes = (
            list(Entrega.objects.values()),
            list(ReservaStock.objects.values()),
            list(ReservaInsumo.objects.values()),
            list(e.lineas.values()),
        )
        self.iniciar()
        despues = (
            list(Entrega.objects.values()),
            list(ReservaStock.objects.values()),
            list(ReservaInsumo.objects.values()),
            list(e.lineas.values()),
        )
        self.assertEqual(antes, despues)

    def test_post_c_se_audita_con_el_vehiculo_y_los_cambios(self):
        """Postcondición c: un registro `inicio_ruta` del Transportista, con el vehículo, el cambio de `en_ruta` y de `fecha_inicio_ruta` y los códigos de las entregas de la ruta."""
        e = self.nueva()
        self.iniciar()
        r = RegistroAuditoria.objects.get(accion="inicio_ruta")
        self.assertEqual(r.usuario_id, self.t.pk)
        self.assertEqual([a["id"] for a in r.afectados], [self.vehiculo().pk])
        self.assertEqual(r.detalle["cambios"]["en_ruta"], {"antes": False, "despues": True})
        self.assertEqual(r.detalle["cambios"]["fecha_inicio_ruta"]["despues"], f"{HOY:%d/%m/%Y}")
        self.assertEqual(r.detalle["datos"]["entregas_de_la_ruta"], [e.codigo])

    def test_regla_iniciar_no_avisa_a_nadie(self):
        """El inicio de la ruta no es un hito de salida: no crea notificaciones."""
        self.nueva()
        antes = Notificacion.objects.count()
        self.iniciar()
        self.assertEqual(Notificacion.objects.count(), antes)

    # ---- pasos 1 a 3 ----

    def test_flujo_principal_la_ruta_trae_el_vehiculo_las_entregas_el_peso_y_la_capacidad(self):
        """Pasos 2 y 3: el vehículo, las entregas con cliente, destino y contenido, la cantidad, las localidades, el peso (10 × 150 g = 1,50 kg) y la capacidad de carga."""
        e = self.nueva()
        datos = self.ruta()
        self.assertEqual((datos.situacion, datos.cantidad, datos.peso, datos.capacidad), ("lista", 1, Decimal("1.50"), Decimal("800.00")))
        (fila,) = datos.entregas
        self.assertEqual((fila.codigo, fila.cliente, fila.dias_de_retraso, fila.con_envasado), (e.codigo, self.e.cliente.nombre_visible, 0, False))
        self.assertIn("10", fila.contenido)
        self.assertEqual(datos.localidades, 1)
        self.assertEqual(datos.vehiculo.pk, self.vehiculo().pk)

    def test_regla_entregas_de_la_ruta_solo_las_con_envio_a_realizar_propias_y_de_hoy_o_antes(self):
        """Regla «Entregas de la ruta»: un retiro, la de otro transportista, la cancelada, la concretada y la de fecha futura no entran."""
        propia = self.nueva()
        self.nueva(modalidad="retiro")
        self.nueva(transportista=transportista_con_vehiculo(self.e.invernadero))
        self.nueva(estado="cancelada")
        self.nueva(fecha=HOY + timedelta(days=2), dias=2)
        datos = self.ruta()
        self.assertEqual([f.entrega.pk for f in datos.entregas], [propia.pk])
        self.assertEqual(len(datos.proximas), 1)

    def test_ext_2b_las_demoradas_van_primero_con_sus_dias_de_retraso(self):
        """Extensión 2b y regla «Orden de presentación»: primero las demoradas (las más atrasadas antes), después las de hoy."""
        de_hoy = self.nueva()
        un_dia = self.nueva(fecha=HOY - timedelta(days=1))
        tres = self.nueva(fecha=HOY - timedelta(days=3))
        datos = self.ruta()
        self.assertEqual([f.entrega.pk for f in datos.entregas], [tres.pk, un_dia.pk, de_hoy.pk])
        self.assertEqual([f.dias_de_retraso for f in datos.entregas], [3, 1, 0])

    def test_ext_2c_las_entregas_sin_envasado_se_senalan(self):
        """Extensión 2c: se marca la que no tiene envasado planificado; el inicio no se bloquea."""
        con = self.nueva()
        reservar(con, envase(self.e.invernadero), 5)
        sin = self.nueva()
        datos = {f.entrega.pk: f.con_envasado for f in self.ruta().entregas}
        self.assertEqual(datos, {con.pk: True, sin.pk: False})
        self.iniciar()
        self.assertTrue(self.vehiculo().esta_en_ruta(HOY))

    def test_regla_el_peso_de_la_ruta_suma_el_de_todas_sus_entregas(self):
        """Regla «Peso de la ruta»: Σ del peso de las entregas de la ruta (informativo)."""
        self.nueva(cantidad=10)
        self.nueva(cantidad=20)
        self.assertEqual(self.ruta().peso, Decimal("4.50"))

    def test_ext_1a_sin_vehiculo_o_con_el_vehiculo_inactivo_no_hay_ruta(self):
        """Extensión 1a: sin vehículo (o con el vehículo dado de baja, que queda sin transportista) la situación es `sin_vehiculo` y iniciar se rechaza con `sin_vehiculo`."""
        sin = transportista_con_vehiculo(self.e.invernadero, con_vehiculo=False)
        self.assertEqual(rutas.ruta_del_dia(sin).situacion, "sin_vehiculo")
        with self.assertRaises(ValidationError) as c:
            rutas.iniciar_ruta(sin, "[]")
        self.assertEqual(codigos(c.exception), ["sin_vehiculo"])

    def test_ext_1b_con_la_ruta_de_hoy_iniciada_se_ofrece_concretar_y_no_se_vuelve_a_iniciar(self):
        """Extensión 1b: la situación es `en_ruta`; iniciar de nuevo (5a) no cambia nada y se rechaza con `ruta_ya_iniciada`."""
        self.nueva()
        self.iniciar()
        self.assertEqual(self.ruta().situacion, "en_ruta")
        antes = RegistroAuditoria.objects.count()
        with self.assertRaises(ValidationError) as c:
            rutas.iniciar_ruta(self.t, self.ruta().huella)
        self.assertEqual(codigos(c.exception), ["ruta_ya_iniciada"])
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_ext_1c_una_ruta_de_un_dia_anterior_ya_no_esta_vigente_y_se_reemplaza(self):
        """Extensión 1c: la situación es `ruta_vencida` con la fecha de esa ruta; al iniciar, `fecha_inicio_ruta` pasa a hoy."""
        self.nueva()
        Vehiculo.objects.filter(transportista=self.t).update(en_ruta=True, fecha_inicio_ruta=HOY - timedelta(days=1))
        datos = self.ruta()
        self.assertEqual((datos.situacion, datos.fecha_ruta_vencida), ("ruta_vencida", HOY - timedelta(days=1)))
        self.iniciar()
        self.assertEqual(self.vehiculo().fecha_inicio_ruta, HOY)
        cambios = RegistroAuditoria.objects.get(accion="inicio_ruta").detalle["cambios"]
        self.assertEqual(cambios["fecha_inicio_ruta"]["antes"], f"{HOY - timedelta(days=1):%d/%m/%Y}")

    def test_ext_2a_sin_entregas_se_informa_la_proxima_fecha_y_no_se_inicia(self):
        """Extensión 2a: sin entregas de la ruta, `cantidad` es 0 y trae la próxima fecha de sus entregas; iniciar se rechaza con `sin_entregas_de_ruta`."""
        datos = self.ruta()
        self.assertEqual((datos.cantidad, datos.proxima_fecha), (0, None))
        self.nueva(fecha=HOY + timedelta(days=4), dias=4)
        datos = self.ruta()
        self.assertEqual((datos.cantidad, datos.proxima_fecha), (0, HOY + timedelta(days=4)))
        with self.assertRaises(ValidationError) as c:
            rutas.iniciar_ruta(self.t, datos.huella)
        self.assertEqual(codigos(c.exception), ["sin_entregas_de_ruta"])
        self.assertFalse(self.vehiculo().en_ruta)

    def test_ext_5a_si_la_inicio_otro_dispositivo_no_se_registra_nada(self):
        """Extensión 5a: entre la pantalla y la confirmación la ruta ya se inició: `ruta_ya_iniciada`, sin cambios ni auditoría nueva."""
        self.nueva()
        huella = self.ruta().huella
        self.iniciar()
        antes = RegistroAuditoria.objects.count()
        with self.assertRaises(ValidationError) as c:
            rutas.iniciar_ruta(self.t, huella)
        self.assertEqual(codigos(c.exception), ["ruta_ya_iniciada"])
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_ext_5b_si_el_vehiculo_dejo_de_ser_suyo_no_se_registra_nada(self):
        """Extensión 5b: el Gerente dio de baja el vehículo mientras tanto (queda inactivo y sin transportista): `vehiculo_inactivo`, sin cambios."""
        self.nueva()
        huella = self.ruta().huella

        def dar_de_baja(invernadero_id):
            Vehiculo.objects.filter(transportista=self.t).update(estado_vehiculo="inactivo", transportista=None)

        with mock.patch("comercial.servicios.rutas.bloquear_invernadero_activo", side_effect=dar_de_baja):
            with self.assertRaises(ValidationError) as c:
                rutas.iniciar_ruta(self.t, huella)
        self.assertEqual(codigos(c.exception), ["vehiculo_inactivo"])
        self.assertFalse(Vehiculo.objects.filter(en_ruta=True).exists())

    def test_ext_5c_si_las_entregas_cambiaron_se_informa_lo_agregado_y_lo_quitado(self):
        """Extensión 5c: otra operación le asignó una entrega y le quitó otra: `ruta_cambio` con `agregadas` y `quitadas`, sin cambiar el vehículo."""
        quitada = self.nueva()
        huella = self.ruta().huella
        Entrega.objects.filter(pk=quitada.pk).update(transportista=None)
        agregada = self.nueva()
        otra = self.nueva()
        with self.assertRaises(ValidationError) as c:
            rutas.iniciar_ruta(self.t, huella)
        self.assertEqual(codigos(c.exception), ["ruta_cambio"])
        self.assertEqual(parametros(c.exception), {"agregadas": [agregada.codigo, otra.codigo], "quitadas": [quitada.codigo]})
        self.assertFalse(self.vehiculo().en_ruta)
        self.iniciar()  # con la huella nueva, sí

    def test_ext_5d_si_ya_no_le_queda_ninguna_entrega_no_se_inicia(self):
        """Extensión 5d: se canceló la única entrega mientras tanto: `sin_entregas_de_ruta`."""
        e = self.nueva()
        huella = self.ruta().huella
        Entrega.objects.filter(pk=e.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")
        with self.assertRaises(ValidationError) as c:
            rutas.iniciar_ruta(self.t, huella)
        self.assertEqual(codigos(c.exception), ["sin_entregas_de_ruta"])

    def test_regla_mas_de_una_ruta_en_el_dia_despues_de_finalizar(self):
        """Regla «Más de una ruta en el día»: tras finalizar, si recibe otra entrega para hoy puede iniciar otra ruta."""
        e = self.nueva()
        self.iniciar()
        # Solo para vaciar la ruta: la concreción real se prueba en `test_com_cnc_ent`.
        Entrega.objects.filter(pk=e.pk).update(estado_orden="concretada", fecha_resolucion_orden=HOY, monto_total_entrega=Decimal("0.00"))
        e.lineas.update(cant_entregada=0, cant_perdida=0, cant_devuelta=0, monto_pagar=Decimal("0.00"))
        rutas.finalizar_ruta(self.t)
        self.nueva()
        self.assertEqual(self.ruta().situacion, "lista")
        self.iniciar()
        self.assertTrue(self.vehiculo().esta_en_ruta(HOY))

    def test_regla_solo_el_transportista_inicia_su_ruta(self):
        """Regla «Quién lo ejecuta»: el Gerente, el Vendedor y un Transportista inactivo no la inician (`PermissionDenied`)."""
        self.nueva()
        gerente = crear_gerente()
        for cuenta in (gerente, self.e.vendedor):
            with self.assertRaises(PermissionDenied):
                rutas.ruta_del_dia(cuenta)
            with self.assertRaises(PermissionDenied):
                rutas.iniciar_ruta(cuenta, "[]")
        self.t.is_active = False
        self.t.save()
        with self.assertRaises(PermissionDenied):
            rutas.iniciar_ruta(self.t, "[]")

    def test_regla_cada_transportista_solo_ve_sus_entregas(self):
        """Regla «Solo le presenta sus entregas»: la ruta de otro transportista no incluye las mías."""
        mia = self.nueva()
        otro = transportista_con_vehiculo(self.e.invernadero)
        self.assertEqual(self.ruta(otro).cantidad, 0)
        self.assertEqual([f.entrega.pk for f in self.ruta().entregas], [mia.pk])

    def test_regla_un_transportista_sin_invernadero_no_tiene_entregas(self):
        """Un transportista sin invernadero asignado (MD-138) no tiene entregas: 2a."""
        solo = crear_transportista(email="solo@infoponia.com")
        from comercial.tests.fabricas import vehiculo

        vehiculo(transportista=solo)
        self.assertEqual(rutas.ruta_del_dia(solo).cantidad, 0)
        with self.assertRaises(ValidationError) as c:
            rutas.iniciar_ruta(solo, "[]")
        self.assertEqual(codigos(c.exception), ["sin_entregas_de_ruta"])

    def test_regla_la_ruta_se_arma_sin_consultas_por_entrega(self):
        """Una consulta por tabla: la cantidad de consultas es la misma con 1 que con 4 entregas."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.nueva()
        with CaptureQueriesContext(connection) as una:
            self.ruta()
        for _ in range(3):
            self.nueva()
        with CaptureQueriesContext(connection) as varias:
            self.ruta()
        self.assertEqual(len(una), len(varias))

    # ---- lo que ven las demás operaciones con la ruta iniciada de verdad ----

    def test_d66_11_con_la_ruta_iniciada_la_entrega_esta_en_curso_para_las_demas_operaciones(self):
        """Regla «Entregas en curso»: desde el inicio, la entrega está en curso (`entregas.en_curso`), COM-ASG-TRP no la reasigna y el envasado no cambia."""
        e = self.nueva()
        self.assertFalse(entregas.en_curso(e, HOY))
        otro = transportista_con_vehiculo(self.e.invernadero)
        self.iniciar()
        self.assertTrue(entregas.en_curso(Entrega.objects.get(pk=e.pk), HOY))
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        self.assertTrue(datos.en_curso)
        with self.assertRaises(ValidationError) as c:
            entregas.asignar_transportista(self.e.vendedor, e.pk, otro.pk, datos.huella)
        self.assertEqual(codigos(c.exception), ["entrega_en_curso"])

    def test_d66_11_iniciar_toma_el_invernadero_de_origen_antes_de_cambiar_el_vehiculo(self):
        """D-66 punto 11: el semáforo es el invernadero de origen; se toma antes de cambiar el vehículo."""
        self.nueva()
        orden = []
        real = rutas.bloquear_invernadero_activo

        def registrar(invernadero_id):
            orden.append(("invernadero", Vehiculo.objects.get(transportista=self.t).en_ruta))
            return real(invernadero_id)

        with mock.patch("comercial.servicios.rutas.bloquear_invernadero_activo", side_effect=registrar):
            self.iniciar()
        self.assertEqual(orden, [("invernadero", False)])

    def test_regla_un_invernadero_ajeno_no_mezcla_las_rutas(self):
        """Las entregas de otro invernadero (de otro transportista) no aparecen en mi ruta."""
        otro = segundo_invernadero(self.e)
        t2 = transportista_con_vehiculo(otro.invernadero)
        self.assertEqual(rutas.ruta_del_dia(t2).cantidad, 0)
