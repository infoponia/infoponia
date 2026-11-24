# Pruebas de PROD-PNF-CSC, Planificar Cosecha (COM-04a, paso 4; docs/casos_de_uso/produccion/cosecha.md, «Cómo se aplica en la ronda «Comercial 1»»):
# `comercial/servicios/cosechas.py`. Una prueba por regla, postcondición y extensión (3a, 3b, 4a, 4b, 6a, 8a, 8b, 8c, 10-11a, 11a a 11c, 12a, 12b,
# 14a, 15a, 15b). Las que escriben verifican al final los invariantes de reservas. La concurrencia está en `test_cosechas_concurrencia.py`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), en `comercial/servicios/cosechas.py`:
#   - Datos: `DatosDeCosecha(invernadero_id, clave_de_detalle="", variedad_id=None, fecha_programada=None, prioridad="media", descripcion="",
#     lotes=((lote_id, cantidad), ...))`. `clave_de_detalle` es `""` (sin contrato, 4a) o la que da `clave_de_detalle(detalle_o_periodo)`:
#     «cv:<id del detalle>» o «sum:<id del detalle>:<aaaa-mm-dd>». Sin contrato, `variedad_id` es obligatoria.
#   - Lectura (no escribe ni bloquea): `invernaderos_para_cosechar(actor) -> [InvernaderoParaCosechar(invernadero, capataz, motivo)]` (motivo `None`,
#     `"sin_capataz"` o `"sin_stock_maduro"`); `detalles_cubribles(actor, invernadero_id, busqueda="") -> [DetalleCubrible(clave, tipo, contrato,
#     cliente, variedad, variedad_id, sin_cubrir, fecha_entrega)]` (tipo `"compra_venta"` o `"suministro"`); `variedades_sin_contrato(actor,
#     invernadero_id) -> [(variedad_id, nombre)]`; `lotes_cosechables(invernadero_id, variedad_id, fecha_programada) -> [LoteCosechable(lote_id,
#     codigo, libre, fecha_maxima, dias_de_exceso)]` (`dias_de_exceso` es 0 si la fecha programada no supera la máxima);
#     `verificar_cosecha(actor, datos) -> VerificacionDeCosecha(errores, advertencias, total_asignado, sin_cubrir)` con `errores = {campo:
#     [(codigo, mensaje)]}` y `advertencias = [(codigo, mensaje)]` (códigos `retraso`, `fecha_maxima` y `queda_sin_cubrir`).
#   - `planificar_cosecha(actor, datos) -> Cosecha`: `PermissionDenied` si `actor` no es un Agrónomo activo con el invernadero a su cargo; `ValidationError`
#     con un error por campo y su código (`sin_capataz`, `sin_stock_maduro`, `detalle_no_cubrible`, `fecha_pasada`, `vence_antes_de_la_entrega`,
#     `lote_no_cosechable`, `supera_stock_libre`, `supera_sin_cubrir`, `sin_lotes`, `cantidad_invalida`, `prioridad_invalida`, `descripcion_larga`,
#     `cosecha_duplicada`), todos releídos DESPUÉS de bloquear (15b). Un error de lote va en el campo `lote_<id>`; el de la fecha, en `fecha_programada`.
#   - Escribe UN registro de auditoría `planificacion_cosecha` y avisa dentro de la transacción (D-42): al Capataz «Nueva cosecha OT-…» y, con
#     contrato, al Vendedor «Cosecha planificada para CV-…» con lo que el detalle queda sin cubrir.
# Fuente: PROD-PNF-CSC v0.4, D-64 puntos 5 y 6, D-59 y D-36.

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva, DetalleVenta, ReservaStock
from comercial.servicios import cosechas
from comercial.servicios.cosechas import DatosDeCosecha
from comercial.tests.fabricas import (
    compra_venta,
    cosecha_manual,
    detalle,
    detalle_suministro,
    escenario_comercial,
    periodo,
    reserva,
    segundo_invernadero,
    suministro,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_vendedor
from produccion.models import Cosecha, Lote, OrdenTrabajo
from produccion.servicios import lotes as api_lotes
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def en(dias):
    """La fecha de dentro de ``dias`` días."""
    return HOY + timedelta(days=dias)


def codigos(prueba, llamada, campo=None):
    """Los códigos de los errores de un `ValidationError` que lanza `llamada()` (los de `campo`, o todos)."""
    with prueba.assertRaises(ValidationError) as rechazo:
        llamada()
    errores = rechazo.exception.error_dict
    return sorted(e.code for clave, lista in errores.items() if campo in (None, clave) for e in lista)


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con Agrónomo, Capataz y Vendedor, un lote en Maduración de 100 plantas (entró hoy: fecha máxima de cosecha dentro de 10 días,
    la duración de la etapa) y una compra-venta con envío de 50 plantas para dentro de 10 días. La postcosecha de la variedad es de 7 días: la
    primera fecha programada admitida para esa entrega es la de dentro de 3 días."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.venta = compra_venta(self.e, dias=10)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.postcosecha = self.e.variedad.duracion_post_cosecha
        self.addCleanup(verificar_invariantes_de_reservas)

    def datos(self, lotes=None, *, contrato=True, fecha=None, **extra):
        """`DatosDeCosecha` válidos: 30 plantas del lote para la fecha de dentro de 5 días, con el detalle de la venta (o sin contrato)."""
        valores = dict(
            invernadero_id=self.e.invernadero.pk,
            clave_de_detalle=cosechas.clave_de_detalle(self.detalle) if contrato else "",
            variedad_id=None if contrato else self.e.variedad.pk,
            fecha_programada=fecha or en(5),
            prioridad="media",
            lotes=tuple(lotes if lotes is not None else [(self.lote.pk, 30)]),
        )
        valores.update(extra)
        return DatosDeCosecha(**valores)

    def planificar(self, datos=None, actor=None):
        return cosechas.planificar_cosecha(actor or self.e.agronomo, datos or self.datos())


class ProdPnfCscServicioTests(Base):
    # ---- permisos y precondiciones ----

    def test_regla_solo_el_agronomo_a_cargo_planifica(self):
        """Regla «Quién»: el Gerente (solo lectura en Producción), el Vendedor, el Capataz y un Agrónomo que no tiene el invernadero a cargo reciben
        `PermissionDenied`; no se escribe nada."""
        otros = [crear_gerente(), self.e.vendedor, self.e.capataz, crear_agronomo(email="otro@infoponia.com")]
        for actor in otros:
            with self.subTest(actor=actor.email), self.assertRaises(PermissionDenied):
                self.planificar(actor=actor)
        self.assertFalse(Cosecha.objects.exists())

    def test_regla_invernaderos_para_cosechar_muestra_deshabilitados_los_que_no_pueden(self):
        """3a y 3b: un invernadero sin Capataz activo o sin lotes cosechables se muestra con su motivo (`sin_capataz`, `sin_stock_maduro`); el que
        puede, sin motivo. Solo los activos a cargo del Agrónomo."""
        sin_capataz = segundo_invernadero(self.e, "Sin Capataz", con_capataz=False)
        lote_maduro(sin_capataz, 10)
        sin_lotes = segundo_invernadero(self.e, "Sin Lotes")
        filas = {f.invernadero.pk: f for f in cosechas.invernaderos_para_cosechar(self.e.agronomo)}
        self.assertEqual(filas[self.e.invernadero.pk].motivo, None)
        self.assertEqual(filas[self.e.invernadero.pk].capataz.pk, self.e.capataz.pk)
        self.assertEqual(filas[sin_capataz.invernadero.pk].motivo, "sin_capataz")
        self.assertEqual(filas[sin_lotes.invernadero.pk].motivo, "sin_stock_maduro")
        Invernadero.objects.filter(pk=sin_lotes.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertNotIn(sin_lotes.invernadero.pk, [f.invernadero.pk for f in cosechas.invernaderos_para_cosechar(self.e.agronomo)])

    def test_ext_3a_un_invernadero_sin_capataz_activo_no_planifica(self):
        """3a: sin Capataz activo asignado, `sin_capataz` en el campo `invernadero`; nada registrado."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(capataz=None)
        self.assertEqual(codigos(self, self.planificar, "invernadero"), ["sin_capataz"])
        self.assertFalse(Cosecha.objects.exists())

    def test_ext_3b_un_invernadero_sin_lotes_maduros_con_stock_libre_no_planifica(self):
        """3b: sin lotes activos en Maduración con stock libre, `sin_stock_maduro`."""
        Lote.objects.filter(pk=self.lote.pk).update(cantidad_actual=0, costo_acumulado=0, estado_lote="finalizado")
        self.assertEqual(codigos(self, self.planificar, "invernadero"), ["sin_stock_maduro"])

    # ---- detalles cubribles (paso 4, regla «Detalle cubrible») ----

    def test_regla_detalle_cubrible_una_compra_venta_abierta_con_cantidad_sin_cubrir(self):
        """Paso 4: compra-venta «abierta» con detalle «abierto» y cantidad sin cubrir > 0: indica contrato, cliente, variedad, cantidad sin cubrir y
        fecha pactada."""
        filas = cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk)
        self.assertEqual(len(filas), 1)
        f = filas[0]
        self.assertEqual(
            (f.clave, f.tipo, f.contrato, f.variedad_id, f.sin_cubrir, f.fecha_entrega),
            (cosechas.clave_de_detalle(self.detalle), "compra_venta", self.venta.codigo, self.e.variedad.pk, 50, self.venta.fecha_pactada_venta),
        )
        self.assertIn(str(self.e.cliente), f.cliente)

    def test_regla_detalle_cubrible_lo_ya_cubierto_se_descuenta_y_lo_totalmente_cubierto_no_aparece(self):
        """Cantidad sin cubrir: 50 − 20 de una reserva = 30; con 50 cubiertos el detalle no aparece."""
        reserva(self.detalle, [(self.lote, 20)])
        self.assertEqual(cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk)[0].sin_cubrir, 30)
        reserva(self.detalle, [(self.lote, 30)])
        self.assertEqual(cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk), [])

    def test_regla_detalle_cubrible_una_venta_que_no_esta_abierta_no_aparece(self):
        """Solo detalles «abiertos» de ventas «abiertas»: una venta pendiente de decisión, cancelada o concretada no."""
        for estado in ("pendiente_decision", "cancelada", "concretada"):
            CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta=estado)
            self.assertEqual(cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk), [], estado)

    def test_regla_detalle_cubrible_con_retiro_solo_desde_el_invernadero_de_retiro(self):
        """Venta con retiro: solo puede cubrirse desde el invernadero de retiro (retiro desde otro invernadero)."""
        sur = segundo_invernadero(self.e, "Sur")
        lote_maduro(sur, 50)
        venta = compra_venta(self.e, dias=10, modalidad="retiro", retiro=sur.invernadero)
        detalle(venta, self.e.variedad, 20)
        self.assertEqual(len(cosechas.detalles_cubribles(self.e.agronomo, sur.invernadero.pk)), 2)  # la de envío (mismo Vendedor) y la de retiro
        propios = [f.contrato for f in cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk)]
        self.assertEqual(propios, [self.venta.codigo])

    def test_regla_detalle_cubrible_con_envio_solo_si_el_vendedor_es_el_del_invernadero(self):
        """Compra-venta con envío (y suministro): solo si el Vendedor del contrato es el Vendedor del invernadero (Vendedor distinto)."""
        otro = crear_vendedor(email="otrovendedor@infoponia.com")
        ajena = compra_venta(self.e, dias=10, vendedor=otro)
        detalle(ajena, self.e.variedad, 10)
        self.assertEqual([f.contrato for f in cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk)], [self.venta.codigo])

    def test_regla_detalle_cubrible_un_periodo_dentro_del_horizonte_de_planificacion(self):
        """Suministro: solo los períodos con fecha entre hoy y hoy + el horizonte (30 días); uno anterior o posterior no. Cada período es una fila."""
        sum_ = suministro(self.e)
        det = detalle_suministro(sum_, self.e.variedad, cantidad=20, periodo=20, primera_en_dias=3)  # períodos: +3, +23, +43
        filas = [f for f in cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk) if f.tipo == "suministro"]
        self.assertEqual([f.fecha_entrega for f in filas], [en(3), en(23)])
        self.assertEqual(filas[0].clave, cosechas.clave_de_detalle(periodo(det, en(3))))
        self.assertEqual((filas[0].contrato, filas[0].sin_cubrir), (sum_.codigo, 20))

    def test_regla_detalle_cubrible_un_periodo_de_un_detalle_finalizado_hasta_su_fecha_de_fin(self):
        """D-64 punto 8: un período de un detalle «finalizado» con fecha ≤ `fecha_fin_detalle` todavía se debe, así que se puede cubrir."""
        sum_ = suministro(self.e)
        det = detalle_suministro(sum_, self.e.variedad, cantidad=20, periodo=7, primera_en_dias=3, estado="finalizado", fecha_fin_detalle=en(10))
        fechas = [f.fecha_entrega for f in cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk) if f.tipo == "suministro"]
        self.assertEqual(fechas, [en(3), en(10)])

    def test_regla_los_detalles_se_ordenan_por_fecha_de_entrega_y_se_buscan_por_cliente_o_variedad(self):
        """Orden de la pantalla: fecha de entrega, después compra-ventas antes que períodos con la misma fecha, después el código. 5a: búsqueda
        por cliente o por variedad (sin distinguir mayúsculas)."""
        anterior = compra_venta(self.e, dias=4)
        detalle(anterior, self.e.variedad, 10)
        sum_ = suministro(self.e)
        detalle_suministro(sum_, self.e.variedad, cantidad=10, periodo=60, primera_en_dias=10)
        filas = cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk)
        self.assertEqual([(f.fecha_entrega, f.tipo) for f in filas], [(en(4), "compra_venta"), (en(10), "compra_venta"), (en(10), "suministro")])
        self.assertEqual(len(cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk, str(self.e.variedad).upper())), 3)
        self.assertEqual(cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk, "inexistente"), [])

    def test_ext_4b_sin_detalles_que_cubrir_la_lista_es_vacia(self):
        """4b: sin contratos con cantidad sin cubrir, no hay filas (la pantalla ofrece planificar sin contrato)."""
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="cancelado")
        self.assertEqual(cosechas.detalles_cubribles(self.e.agronomo, self.e.invernadero.pk), [])

    def test_ext_4a_las_variedades_sin_contrato_son_las_que_tienen_lotes_maduros_con_stock_libre(self):
        """4a: las variedades con lotes activos en Maduración con stock libre en el invernadero."""
        self.assertEqual(cosechas.variedades_sin_contrato(self.e.agronomo, self.e.invernadero.pk), [(self.e.variedad.pk, str(self.e.variedad))])
        cosecha_manual(self.e, [(self.lote, 100)], dias=1)
        self.assertEqual(cosechas.variedades_sin_contrato(self.e.agronomo, self.e.invernadero.pk), [])

    # ---- lotes (pasos 9 a 11) ----

    def test_regla_lotes_cosechables_con_su_stock_libre_y_su_fecha_maxima(self):
        """Paso 9 y regla «Lote cosechable»: activo, del invernadero y de la variedad, en Maduración y con stock libre > 0; stock libre = actual −
        reservado en reservas activas; fecha máxima de cosecha y días de exceso respecto de la fecha programada (11c)."""
        reserva(self.detalle, [(self.lote, 40)])
        maxima = api_lotes.fecha_maxima_de_cosecha(self.lote)
        a_tiempo = cosechas.lotes_cosechables(self.e.invernadero.pk, self.e.variedad.pk, en(5))
        self.assertEqual([(l.lote_id, l.codigo, l.libre, l.fecha_maxima, l.dias_de_exceso) for l in a_tiempo], [(self.lote.pk, self.lote.codigo, 60, maxima, 0)])
        tarde = cosechas.lotes_cosechables(self.e.invernadero.pk, self.e.variedad.pk, maxima + timedelta(days=3))
        self.assertEqual(tarde[0].dias_de_exceso, 3)

    def test_regla_un_lote_sin_stock_libre_no_es_cosechable(self):
        """Lote cosechable: con todo reservado, no aparece."""
        cosecha_manual(self.e, [(self.lote, 100)], dias=1)
        self.assertEqual(cosechas.lotes_cosechables(self.e.invernadero.pk, self.e.variedad.pk, en(5)), [])

    # ---- fechas (pasos 7 y 8) ----

    def test_ext_8a_la_fecha_pasada_se_rechaza(self):
        """8a: la fecha programada anterior a hoy es `fecha_pasada`; hoy vale."""
        self.assertEqual(codigos(self, lambda: self.planificar(self.datos(fecha=en(-1))), "fecha_programada"), ["fecha_pasada"])
        self.assertEqual(self.planificar(self.datos(contrato=False, fecha=en(0))).fecha_programada_orden, HOY)

    def test_ext_8b_la_fecha_que_vence_antes_de_la_entrega_se_rechaza_con_la_primera_admitida(self):
        """8b: fecha programada + postcosecha anterior a la entrega: `vence_antes_de_la_entrega`, y el mensaje trae la primera fecha admitida
        (entrega − postcosecha); esa fecha se acepta."""
        primera = self.venta.fecha_pactada_venta - timedelta(days=self.postcosecha)
        with self.assertRaises(ValidationError) as rechazo:
            self.planificar(self.datos(fecha=primera - timedelta(days=1)))
        error = rechazo.exception.error_dict["fecha_programada"][0]
        self.assertEqual(error.code, "vence_antes_de_la_entrega")
        self.assertIn(f"{primera:%d/%m/%Y}", error.message)
        self.assertEqual(self.planificar(self.datos(fecha=primera)).fecha_programada_orden, primera)

    def test_ext_4a_sin_contrato_la_fecha_solo_verifica_que_no_sea_pasada(self):
        """4a: sin contrato, en el paso 8 solo se verifica la fecha pasada (no hay entrega que vencer)."""
        self.assertEqual(self.planificar(self.datos(contrato=False, fecha=en(0))).fecha_programada_orden, HOY)

    def test_ext_8c_una_fecha_posterior_a_la_entrega_es_una_advertencia_y_deja_planificar(self):
        """8c: la fecha programada posterior a la entrega advierte `retraso` (con el texto de suministro si corresponde) pero no impide seguir; la
        fecha de entrega de la reserva conserva la prometida."""
        fecha = self.venta.fecha_pactada_venta + timedelta(days=2)
        verificacion = cosechas.verificar_cosecha(self.e.agronomo, self.datos(fecha=fecha))
        self.assertEqual([c for c, _ in verificacion.advertencias if c == "retraso"], ["retraso"])
        self.assertEqual(verificacion.errores, {})
        orden = self.planificar(self.datos(fecha=fecha))
        self.assertEqual(orden.reserva.fecha_entrega_reserva, self.venta.fecha_pactada_venta)

    def test_ext_8c_el_retraso_de_un_suministro_advierte_ademas_la_posible_indemnizacion(self):
        """8c: si el detalle es de un suministro, advierte además que el retraso puede originar una queja o una indemnización."""
        det = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=20, primera_en_dias=3)
        datos = self.datos(clave_de_detalle=cosechas.clave_de_detalle(periodo(det, en(3))), fecha=en(5), lotes=[(self.lote.pk, 10)])
        mensajes = [m for c, m in cosechas.verificar_cosecha(self.e.agronomo, datos).advertencias if c == "retraso"]
        self.assertEqual(len(mensajes), 1)
        self.assertIn("indemnización", mensajes[0])

    # ---- lotes y cantidades (pasos 10 a 12) ----

    def test_ext_11a_la_cantidad_que_supera_el_stock_libre_del_lote_se_rechaza(self):
        """11a: `supera_stock_libre` en el campo del lote, con el stock libre en el mensaje."""
        cosecha_manual(self.e, [(self.lote, 80)], dias=1)
        datos = self.datos([(self.lote.pk, 30)], contrato=False)  # sin contrato: solo cuenta el stock libre (20)
        with self.assertRaises(ValidationError) as rechazo:
            self.planificar(datos)
        error = rechazo.exception.error_dict[f"lote_{self.lote.pk}"][0]
        self.assertEqual(error.code, "supera_stock_libre")
        self.assertIn("20", error.message)

    def test_ext_11b_la_cantidad_que_supera_lo_que_el_detalle_tiene_sin_cubrir_se_rechaza(self):
        """11b: con contrato, el total no puede superar la cantidad sin cubrir (50): `supera_sin_cubrir` en `lotes`, con la cantidad sin cubrir."""
        with self.assertRaises(ValidationError) as rechazo:
            self.planificar(self.datos([(self.lote.pk, 51)]))
        error = rechazo.exception.error_dict["lotes"][0]
        self.assertEqual(error.code, "supera_sin_cubrir")
        self.assertIn("50", error.message)
        self.assertEqual(self.planificar(self.datos([(self.lote.pk, 50)])).reserva.lineas.get().cantidad_reservada, 50)

    def test_ext_4a_sin_contrato_el_total_solo_se_verifica_contra_el_stock_libre(self):
        """4a: sin contrato no hay «cantidad sin cubrir»: se pueden planificar 100 plantas aunque la venta pida 50."""
        self.assertEqual(self.planificar(self.datos([(self.lote.pk, 100)], contrato=False)).reserva.lineas.get().cantidad_reservada, 100)

    def test_ext_11c_un_lote_que_supera_su_fecha_maxima_advierte_con_los_dias_de_exceso_y_no_bloquea(self):
        """11c: advertencia `fecha_maxima` con la fecha máxima y los días de exceso (corridos); el Agrónomo decide (no bloquea). Vale sin contrato."""
        maxima = api_lotes.fecha_maxima_de_cosecha(self.lote)
        datos = self.datos(contrato=False, fecha=maxima + timedelta(days=4))
        advertencias = [m for c, m in cosechas.verificar_cosecha(self.e.agronomo, datos).advertencias if c == "fecha_maxima"]
        self.assertEqual(len(advertencias), 1)
        self.assertIn("4 días", advertencias[0])
        self.assertIn(f"{maxima:%d/%m/%Y}", advertencias[0])
        self.assertTrue(self.planificar(datos))

    def test_ext_12a_terminar_sin_cubrir_todo_el_detalle_advierte_y_sigue(self):
        """12a: asignar menos que lo sin cubrir deja `queda_sin_cubrir` como advertencia y el detalle queda con lo que falta (20)."""
        verificacion = cosechas.verificar_cosecha(self.e.agronomo, self.datos([(self.lote.pk, 30)]))
        self.assertEqual((verificacion.total_asignado, verificacion.sin_cubrir), (30, 20))
        self.assertIn("queda_sin_cubrir", [c for c, _ in verificacion.advertencias])

    def test_ext_12b_sin_lotes_o_con_cantidad_cero_no_se_planifica(self):
        """12b: la orden debe incluir al menos un lote con al menos una planta: `sin_lotes`; una cantidad que no es un entero mayor que 0,
        `cantidad_invalida` en el campo del lote."""
        self.assertEqual(codigos(self, lambda: self.planificar(self.datos([]))), ["sin_lotes"])
        self.assertEqual(codigos(self, lambda: self.planificar(self.datos([(self.lote.pk, 0)])), f"lote_{self.lote.pk}"), ["cantidad_invalida"])

    def test_regla_un_lote_que_no_es_cosechable_se_rechaza(self):
        """Regla «Lote cosechable»: de otra variedad, de otro invernadero, finalizado o fuera de Maduración: `lote_no_cosechable`."""
        sur = segundo_invernadero(self.e, "Sur")
        ajeno = lote_maduro(sur, 50)
        finalizado = lote_maduro(self.e, 10)
        Lote.objects.filter(pk=finalizado.pk).update(cantidad_actual=0, costo_acumulado=0, estado_lote="finalizado")
        for lote in (ajeno, finalizado):
            self.assertEqual(codigos(self, lambda: self.planificar(self.datos([(lote.pk, 5)])), f"lote_{lote.pk}"), ["lote_no_cosechable"])

    def test_regla_los_datos_de_la_orden_se_validan(self):
        """Prioridad alta, media o baja (`prioridad_invalida`) y descripción de hasta 500 (`descripcion_larga`)."""
        self.assertEqual(codigos(self, lambda: self.planificar(self.datos(prioridad="urgente")), "prioridad"), ["prioridad_invalida"])
        self.assertEqual(codigos(self, lambda: self.planificar(self.datos(descripcion="x" * 501)), "descripcion"), ["descripcion_larga"])

    def test_ext_6a_un_detalle_sin_lotes_de_su_variedad_no_puede_cubrirse_desde_el_invernadero(self):
        """6a: sin lotes activos de la variedad del detalle en Maduración con stock libre, `sin_stock_maduro` en el campo `detalle`."""
        cosecha_manual(self.e, [(self.lote, 100)], dias=1)
        otra = detalle(compra_venta(self.e, dias=10), self.e.variedad, 10)  # misma variedad: sigue sin stock libre
        datos = self.datos(clave_de_detalle=cosechas.clave_de_detalle(otra), lotes=[(self.lote.pk, 1)])
        self.assertEqual(codigos(self, lambda: self.planificar(datos), "detalle"), ["sin_stock_maduro"])

    def test_regla_un_detalle_que_no_se_puede_cubrir_se_rechaza(self):
        """Regla «Detalle cubrible»: un detalle de otro Vendedor, de una venta cancelada, un período fuera del horizonte o una clave inventada:
        `detalle_no_cubrible` en el campo `detalle`."""
        ajena = compra_venta(self.e, dias=10, vendedor=crear_vendedor(email="v2@infoponia.com"))
        de_otro = detalle(ajena, self.e.variedad, 10)
        sum_ = suministro(self.e)
        lejano = detalle_suministro(sum_, self.e.variedad, cantidad=10, primera_en_dias=45)
        for clave in (cosechas.clave_de_detalle(de_otro), cosechas.clave_de_detalle(periodo(lejano, en(45))), "cv:999999", "xx"):
            datos = self.datos(clave_de_detalle=clave, lotes=[(self.lote.pk, 5)])
            self.assertEqual(codigos(self, lambda: self.planificar(datos), "detalle"), ["detalle_no_cubrible"], clave)

    # ---- 15a y 15b ----

    def test_ext_15a_una_orden_igual_a_otra_a_realizar_se_rechaza_con_su_codigo(self):
        """15a: misma cosecha (invernadero, variedad, fecha programada, prioridad, descripción, Agrónomo, detalle y líneas) «a realizar»: se
        rechaza con `cosecha_duplicada` y el código de la existente."""
        primera = self.planificar()
        with self.assertRaises(ValidationError) as rechazo:
            self.planificar()
        error = next(e for lista in rechazo.exception.error_dict.values() for e in lista)
        self.assertEqual(error.code, "cosecha_duplicada")
        self.assertIn(primera.codigo, error.message)
        self.assertEqual(Cosecha.objects.count(), 1)

    def test_ext_15a_con_otra_cantidad_otra_fecha_o_ya_concretada_no_es_duplicada(self):
        """Solo cuenta si todo es igual y la otra está «a realizar»: con otra cantidad, otra fecha o la existente ya cancelada se planifica."""
        primera = self.planificar(self.datos([(self.lote.pk, 10)]))
        self.planificar(self.datos([(self.lote.pk, 5)]))
        self.planificar(self.datos([(self.lote.pk, 10)], fecha=en(6)))
        OrdenTrabajo.objects.filter(pk=primera.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")
        ReservaStock.objects.filter(cosecha=primera).update(estado_reserva="liberada")
        self.planificar(self.datos([(self.lote.pk, 10)]))
        self.assertEqual(Cosecha.objects.count(), 4)

    def test_ext_15b_el_stock_libre_o_lo_sin_cubrir_cambian_antes_de_registrar(self):
        """15b: se verifica de nuevo al registrar: si otra operación reservó el stock del lote (11a) o cubrió lo que el detalle pedía (11b), no se
        registra nada y el error dice qué cambió."""
        datos = self.datos([(self.lote.pk, 60)], contrato=False)
        reserva(self.detalle, [(self.lote, 50)])
        self.assertEqual(codigos(self, lambda: self.planificar(datos), f"lote_{self.lote.pk}"), ["supera_stock_libre"])
        self.assertEqual(Cosecha.objects.filter(origen_cosecha="manual").count(), 0)

    def test_ext_15b_el_detalle_deja_de_poder_cubrirse(self):
        """15b: la venta se canceló o el detalle quedó pendiente de decisión: `detalle_no_cubrible` y nada registrado."""
        datos = self.datos()
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="pendiente_decision")
        self.assertEqual(codigos(self, lambda: self.planificar(datos), "detalle"), ["detalle_no_cubrible"])
        self.assertEqual(Cosecha.objects.count(), 0)

    def test_ext_15b_un_lote_que_deja_de_estar_activo_se_rechaza(self):
        """15b: un lote que se finalizó entre la verificación y el registro: `lote_no_cosechable`."""
        datos = self.datos()
        Lote.objects.filter(pk=self.lote.pk).update(cantidad_actual=0, costo_acumulado=0, estado_lote="finalizado")
        self.assertEqual(sorted(set(codigos(self, lambda: self.planificar(datos)))), ["lote_no_cosechable", "sin_stock_maduro"])

    # ---- postcondiciones ----

    def test_post_a_la_orden_nace_a_realizar_manual_con_el_agronomo_y_el_capataz_del_invernadero(self):
        """a: orden «a realizar» con fecha de creación hoy, fecha programada, prioridad y descripción; `origen_cosecha = manual`, `agronomo` el que
        planificó, el Capataz del invernadero y el número de la secuencia (`OT-…`)."""
        orden = self.planificar(self.datos(prioridad="alta", descripcion="Para el viernes"))
        orden = Cosecha.objects.get(pk=orden.pk)
        self.assertEqual(
            (orden.estado_orden, orden.fecha_creacion_orden, orden.fecha_programada_orden, orden.prioridad_orden, orden.descripcion_orden),
            ("a_realizar", HOY, en(5), "alta", "Para el viernes"),
        )
        self.assertEqual(
            (orden.origen_cosecha, orden.agronomo_id, orden.capataz_id, orden.variedad_id, orden.invernadero_id, orden.tipo_orden),
            ("manual", self.e.agronomo.pk, self.e.capataz.pk, self.e.variedad.pk, self.e.invernadero.pk, "cosecha"),
        )
        self.assertTrue(orden.codigo.startswith("OT-"))

    def test_post_b_y_c_una_reserva_activa_con_una_linea_por_lote_sin_cantidad_cosechada(self):
        """b y c: una reserva «activa» con `fecha_reserva` de hoy, asociada a la orden, y una línea por lote seleccionado con su cantidad y sin
        cantidad cosechada; los lotes no cambian su cantidad actual."""
        otro = lote_maduro(self.e, 40)
        orden = self.planificar(self.datos([(self.lote.pk, 30), (otro.pk, 15)]))
        reserva_ = ReservaStock.objects.get(cosecha=orden)
        self.assertEqual((reserva_.estado_reserva, reserva_.fecha_reserva, reserva_.invernadero_id), ("activa", HOY, self.e.invernadero.pk))
        lineas = list(DetalleReserva.objects.filter(reserva=reserva_).order_by("lote_id").values_list("lote_id", "cantidad_reservada", "cantidad_cosechada"))
        self.assertEqual(lineas, [(self.lote.pk, 30, None), (otro.pk, 15, None)])
        self.assertEqual((Lote.objects.get(pk=self.lote.pk).cantidad_actual, Lote.objects.get(pk=otro.pk).cantidad_actual), (100, 40))

    def test_post_d_con_un_detalle_de_compra_venta_la_reserva_lleva_la_fecha_pactada(self):
        """d: la reserva queda asociada al detalle de la venta y su fecha de entrega es la pactada; el estado del detalle y de la venta no cambian."""
        orden = self.planificar(self.datos(fecha=self.venta.fecha_pactada_venta + timedelta(days=1)))
        reserva_ = ReservaStock.objects.get(cosecha=orden)
        self.assertEqual((reserva_.detalle_venta_id, reserva_.detalle_suministro_id, reserva_.fecha_entrega_reserva), (self.detalle.pk, None, self.venta.fecha_pactada_venta))
        self.detalle.refresh_from_db()
        self.venta.refresh_from_db()
        self.assertEqual((self.detalle.estado_detalle_venta, self.venta.estado_venta), ("abierto", "abierta"))

    def test_post_e_con_un_periodo_la_reserva_lleva_el_detalle_de_suministro_y_la_fecha_del_periodo(self):
        """e: la reserva queda asociada al detalle de suministro, con `fecha_entrega_reserva` = la fecha del período."""
        det = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=20, primera_en_dias=8)
        datos = self.datos(clave_de_detalle=cosechas.clave_de_detalle(periodo(det, en(8))), lotes=[(self.lote.pk, 10)], fecha=en(5))
        reserva_ = ReservaStock.objects.get(cosecha=self.planificar(datos))
        self.assertEqual((reserva_.detalle_suministro_id, reserva_.detalle_venta_id, reserva_.fecha_entrega_reserva), (det.pk, None, en(8)))

    def test_post_f_sin_contrato_la_reserva_no_tiene_detalle_ni_fecha_de_entrega(self):
        """f y D-64 punto 6: sin contrato, la reserva no queda asociada a ningún detalle y no tiene fecha de entrega."""
        reserva_ = ReservaStock.objects.get(cosecha=self.planificar(self.datos(contrato=False)))
        self.assertEqual((reserva_.detalle_venta_id, reserva_.detalle_suministro_id, reserva_.fecha_entrega_reserva), (None, None, None))

    def test_post_g_se_avisa_al_capataz(self):
        """g (paso 16): «Nueva cosecha OT-…» con la variedad, las plantas, la fecha y quién planificó, dentro de la transacción."""
        orden = self.planificar()
        aviso = Notificacion.objects.get(destinatario=self.e.capataz, titulo=f"Nueva cosecha {orden.codigo}")
        self.assertIn(str(self.e.variedad), aviso.detalle)
        self.assertIn("30 plantas", aviso.detalle)
        self.assertIn(f"{en(5):%d/%m/%Y}", aviso.detalle)

    def test_post_h_con_contrato_se_avisa_al_vendedor_con_lo_que_queda_sin_cubrir(self):
        """h: al Vendedor del contrato, «Cosecha planificada para CV-…», con la cantidad que el detalle queda sin cubrir (50 − 30 = 20). Sin contrato,
        el Vendedor no recibe nada."""
        self.planificar()
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor)
        self.assertEqual(aviso.titulo, f"Cosecha planificada para {self.venta.codigo}")
        self.assertIn("20 plantas sin cubrir", aviso.detalle)
        self.planificar(self.datos(contrato=False, fecha=en(6)))
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.vendedor).count(), 1)

    def test_post_i_y_j_un_solo_registro_de_auditoria_con_la_orden_la_reserva_y_las_lineas(self):
        """i, j y D-36: UN registro `planificacion_cosecha` del Agrónomo con la cosecha, la reserva y cada línea como afectados."""
        antes = RegistroAuditoria.objects.count()
        orden = self.planificar()
        self.assertEqual(RegistroAuditoria.objects.count(), antes + 1)
        registro = RegistroAuditoria.objects.latest("pk")
        self.assertEqual((registro.accion, registro.usuario_id), ("planificacion_cosecha", self.e.agronomo.pk))
        textos = [a["texto"] for a in registro.afectados]
        self.assertIn(orden.codigo, textos)
        self.assertTrue(any(t.startswith("Reserva #") for t in textos))
        self.assertTrue(any(t.startswith("Línea #") for t in textos))

    def test_regla_garantia_minima_si_falla_no_queda_nada(self):
        """Garantías mínimas: un rechazo no deja orden, reserva, líneas ni auditoría parcial."""
        antes = RegistroAuditoria.objects.count()
        with self.assertRaises(ValidationError):
            self.planificar(self.datos([(self.lote.pk, 999)]))
        self.assertEqual((Cosecha.objects.count(), ReservaStock.objects.count(), DetalleReserva.objects.count()), (0, 0, 0))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_regla_la_verificacion_no_escribe_nada(self):
        """`verificar_cosecha` (el recálculo de la pantalla y el resumen) no escribe ni audita ni avisa."""
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        cosechas.verificar_cosecha(self.e.agronomo, self.datos())
        self.assertEqual((Cosecha.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count()), (0, *antes))

    def test_regla_la_reserva_de_una_cosecha_manual_descuenta_el_stock_libre_de_otra_planificacion(self):
        """Regla «Stock libre»: lo reservado por una cosecha manual deja menos libre al siguiente: con 100 plantas y 70 ya planificadas, solo 30."""
        self.planificar(self.datos([(self.lote.pk, 50)], fecha=en(4)))
        self.planificar(self.datos([(self.lote.pk, 20)], contrato=False))
        libres = cosechas.lotes_cosechables(self.e.invernadero.pk, self.e.variedad.pk, en(5))
        self.assertEqual(libres[0].libre, 30)
