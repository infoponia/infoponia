# Pruebas de PROD-MOD-CSC, Modificar Cosecha (COM-04a, paso 4; docs/casos_de_uso/produccion/cosecha.md, «Cómo se aplica en la ronda «Comercial 1»»):
# `comercial/servicios/cosechas.py`. Una prueba por postcondición (a a f) y extensión (2a, 5a, 5b.4a a 5b.4c, 5c, 6a a 6d, 7a, 10a, 10b); el stock libre
# que suma lo propio; la fecha de entrega que no cambia. La concurrencia (modificar contra concretar, contra planificar) está en
# `test_cosechas_concurrencia.py`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), en `comercial/servicios/cosechas.py`:
#   - `cosechas_modificables(actor) -> [FilaDeCosecha(cosecha_id, codigo, variedad, invernadero, fecha_programada, prioridad, cantidad_reservada,
#     origen, contrato, fecha_entrega)]`: las «a realizar» de los invernaderos del Agrónomo, de cualquier origen, por fecha programada (paso 2);
#     `origen` es el texto («Automática», «Manual», «Encadenada»), `contrato` el código o `None`.
#   - `datos_de_modificacion(actor, cosecha_id) -> FichaDeModificacion(cosecha, lineas, lotes, contrato, fecha_entrega, primera_fecha, ultima_fecha,
#     huella)`: `lineas = [LineaDeLote(lote_id, codigo, reservada, libre, fecha_maxima)]` (con `libre` incluyendo lo que ya reserva esta cosecha) y `lotes`
#     los lotes cosechables de la variedad y el invernadero (los de 5b.1, mismo tipo de fila); `primera_fecha = max(hoy, entrega − postcosecha)` y
#     `ultima_fecha = entrega` (la última sin retraso), ambas `None` sin contrato; `huella = huella_de(cosecha)` leída al abrir.
#   - `huella_de(cosecha)`: un texto estable con estado, fecha programada, prioridad, descripción y las líneas (lote y cantidad): cambia si cambia
#     cualquiera de esos datos.
#   - Datos: `DatosDeModificacion(fecha_programada, prioridad, descripcion, lotes=((lote_id, cantidad), ...), variedad_id=None, invernadero_id=None,
#     clave_de_detalle=None, cantidad_total=None)`: los cuatro últimos son lo que la pantalla NO ofrece (5c); si llegan y difieren de lo guardado,
#     `no_modificable`.
#   - `verificar_modificacion(actor, cosecha_id, datos) -> VerificacionDeModificacion(errores, advertencias, cambios, total_asignado,
#     total_reservado)`: `errores = {campo: [(codigo, mensaje)]}`, `advertencias = [(codigo, mensaje)]` (`retraso`, `fecha_maxima`, `lotes_no_alcanzan`) y
#     `cambios = [(campo, antes, despues)]` con los campos `fecha_programada`, `prioridad`, `descripcion` y `lotes` (paso 8: valor anterior y nuevo).
#   - `modificar_cosecha(actor, cosecha_id, datos, huella) -> Cosecha`: `PermissionDenied` si no es el Agrónomo a cargo; `ValidationError` por campo con
#     `sin_cambios`, `fecha_pasada`, `vence_antes_de_la_entrega`, `total_distinto`, `supera_stock_libre` (campo `lote_<id>`), `no_modificable`,
#     `cosecha_resuelta` (10a) y `cosecha_cambio` (la huella cambió). Todo releído DESPUÉS de bloquear. Un registro `modificacion_cosecha`; avisa al Capataz
#     «Cosecha OT-… modificada» y, si la fecha nueva atrasa la entrega de un contrato, al Vendedor «Cosecha de CV-… con retraso».
# Fuente: PROD-MOD-CSC v0.1, D-64 punto 5 y D-36.

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from comercial.models import DetalleReserva, ReservaStock
from comercial.servicios import cosechas
from comercial.servicios.cosechas import DatosDeModificacion
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
from maestros.tests.fabricas import crear_agronomo
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
    return sorted(e.code for clave, lista in rechazo.exception.error_dict.items() if campo in (None, clave) for e in lista)


class Base(ConDatosDeInventario, TestCase):
    """Una cosecha automática con contrato (compra-venta con envío de 50 plantas para dentro de 10 días) que reserva 30 plantas de un lote de 100
    en Maduración y está programada para dentro de 5 días. La postcosecha es de 7 días (primera fecha admitida: dentro de 3 días)."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.venta = compra_venta(self.e, dias=10)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.cosecha = cosecha_manual(self.e, [(self.lote, 30)], detalle_=self.detalle, dias=5, origen="automatica")
        self.postcosecha = self.e.variedad.duracion_post_cosecha
        self.addCleanup(verificar_invariantes_de_reservas)

    def datos(self, **cambios):
        """`DatosDeModificacion` que repiten lo guardado, con los `cambios` pedidos."""
        valores = dict(fecha_programada=en(5), prioridad="media", descripcion="", lotes=((self.lote.pk, 30),))
        valores.update(cambios)
        return DatosDeModificacion(**valores)

    def huella(self, cosecha=None):
        return cosechas.huella_de(Cosecha.objects.get(pk=(cosecha or self.cosecha).pk))

    def modificar(self, actor=None, huella=None, cosecha=None, **cambios):
        cosecha = cosecha or self.cosecha
        return cosechas.modificar_cosecha(actor or self.e.agronomo, cosecha.pk, self.datos(**cambios), huella or self.huella(cosecha))

    def releer(self):
        return Cosecha.objects.get(pk=self.cosecha.pk)

    def lineas(self):
        return sorted(DetalleReserva.objects.filter(reserva__cosecha=self.cosecha).values_list("lote_id", "cantidad_reservada"))


class ProdModCscServicioTests(Base):
    # ---- lectura (pasos 2 a 4) ----

    def test_regla_cosechas_modificables_son_las_a_realizar_de_cualquier_origen_por_fecha(self):
        """Paso 2 y regla «Cosecha modificable»: las pendientes (automática, manual, encadenada) de los invernaderos del Agrónomo, por fecha
        programada, con origen, cantidad reservada, contrato y fecha de entrega; las concretadas y canceladas no."""
        manual = cosecha_manual(self.e, [(self.lote, 10)], dias=2)
        encadenada = cosecha_manual(self.e, [(self.lote, 5)], detalle_=self.detalle, dias=8, origen="encadenada")
        hecha = cosecha_manual(self.e, [(self.lote, 5)], dias=1)
        OrdenTrabajo.objects.filter(pk=hecha.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")
        ReservaStock.objects.filter(cosecha=hecha).update(estado_reserva="liberada")
        filas = cosechas.cosechas_modificables(self.e.agronomo)
        self.assertEqual([f.cosecha_id for f in filas], [manual.pk, self.cosecha.pk, encadenada.pk])
        f = filas[1]
        self.assertEqual(
            (f.origen, f.cantidad_reservada, f.contrato, f.fecha_entrega, f.prioridad, f.fecha_programada),
            ("Automática", 30, self.venta.codigo, self.venta.fecha_pactada_venta, "media", en(5)),
        )
        self.assertEqual((filas[0].origen, filas[0].contrato, filas[2].origen), ("Manual", None, "Encadenada"))

    def test_regla_solo_el_agronomo_a_cargo_modifica_y_ve_las_cosechas(self):
        """Precondición a y regla «Quién modifica»: el Gerente, el Vendedor, el Capataz y un Agrónomo ajeno reciben `PermissionDenied`."""
        for actor in (crear_gerente(), self.e.vendedor, self.e.capataz, crear_agronomo(email="otro@infoponia.com")):
            with self.subTest(actor=actor.email):
                with self.assertRaises(PermissionDenied):
                    self.modificar(actor=actor, descripcion="x")
                with self.assertRaises(PermissionDenied):
                    cosechas.datos_de_modificacion(actor, self.cosecha.pk)
        self.assertEqual(self.releer().descripcion_orden, "")

    def test_regla_la_ficha_trae_las_lineas_el_stock_libre_que_suma_lo_propio_y_las_fechas_admitidas(self):
        """Paso 4 y 5b.1: cada línea con su cantidad reservada, el stock libre del lote **incluyendo lo que ya reserva esta cosecha** (100 −
        otras reservas) y su fecha máxima; con contrato, la fecha de entrega y la primera y la última fecha admitidas."""
        cosecha_manual(self.e, [(self.lote, 20)], dias=1)  # otra cosecha: 20 reservadas de otra orden
        ficha = cosechas.datos_de_modificacion(self.e.agronomo, self.cosecha.pk)
        self.assertEqual(
            [(l.lote_id, l.reservada, l.libre, l.fecha_maxima) for l in ficha.lineas],
            [(self.lote.pk, 30, 80, api_lotes.fecha_maxima_de_cosecha(self.lote))],
        )
        self.assertEqual([l.lote_id for l in ficha.lotes], [self.lote.pk])
        self.assertEqual(
            (ficha.contrato, ficha.fecha_entrega, ficha.primera_fecha, ficha.ultima_fecha),
            (self.venta.codigo, self.venta.fecha_pactada_venta, self.venta.fecha_pactada_venta - timedelta(days=self.postcosecha), self.venta.fecha_pactada_venta),
        )
        self.assertEqual(ficha.huella, self.huella())

    def test_regla_la_huella_cambia_con_cualquiera_de_los_datos_que_protege(self):
        """`huella_de`: estado, fecha programada, prioridad, descripción y líneas; si nada cambió, es la misma."""
        base = self.huella()
        self.assertEqual(base, self.huella())
        self.modificar(prioridad="alta")
        self.assertNotEqual(self.huella(), base)

    # ---- postcondiciones ----

    def test_post_a_la_fecha_la_prioridad_y_la_descripcion_cambian(self):
        """a: la cosecha queda con la fecha programada, la prioridad y la descripción nuevas (los pasos 5 y 6, extensión 5a)."""
        self.modificar(fecha_programada=en(6), prioridad="alta", descripcion="Primero la lechuga")
        c = self.releer()
        self.assertEqual((c.fecha_programada_orden, c.prioridad_orden, c.descripcion_orden), (en(6), "alta", "Primero la lechuga"))

    def test_post_b_las_lineas_cambian_se_borran_las_quitadas_y_se_crean_las_agregadas(self):
        """b: cada línea de lote queda con su cantidad nueva, las de los lotes quitados se eliminan y se crean las de los agregados; el total
        reservado no cambia y el stock libre de cada lote baja o sube en la diferencia."""
        otro = lote_maduro(self.e, 40)
        self.modificar(lotes=((self.lote.pk, 10), (otro.pk, 20)))
        self.assertEqual(self.lineas(), sorted([(self.lote.pk, 10), (otro.pk, 20)]))
        self.modificar(lotes=((otro.pk, 30),), huella=self.huella())
        self.assertEqual(self.lineas(), [(otro.pk, 30)])
        libres = {l.lote_id: l.libre for l in cosechas.lotes_cosechables(self.e.invernadero.pk, self.e.variedad.pk, en(5))}
        self.assertEqual((libres[self.lote.pk], libres[otro.pk]), (100, 10))

    def test_post_c_la_fecha_de_entrega_de_la_reserva_no_cambia_aunque_se_atrase_la_cosecha(self):
        """c y regla 12 de 8.8: la fecha prometida se conserva; también si la nueva fecha programada es posterior."""
        self.modificar(fecha_programada=self.venta.fecha_pactada_venta + timedelta(days=3))
        self.assertEqual(ReservaStock.objects.get(cosecha=self.cosecha).fecha_entrega_reserva, self.venta.fecha_pactada_venta)

    def test_regla_no_cambian_la_variedad_el_invernadero_el_contrato_ni_la_cantidad_total(self):
        """Garantías mínimas: tras modificar, la variedad, el invernadero, el detalle de la reserva y el total reservado son los mismos."""
        otro = lote_maduro(self.e, 40)
        self.modificar(lotes=((otro.pk, 30),))
        c, r = self.releer(), ReservaStock.objects.get(cosecha=self.cosecha)
        self.assertEqual((c.variedad_id, c.invernadero_id, r.detalle_venta_id, sum(n for _, n in self.lineas())), (self.e.variedad.pk, self.e.invernadero.pk, self.detalle.pk, 30))

    def test_post_d_se_avisa_al_capataz(self):
        """d (paso 11): «Cosecha OT-… modificada» con lo que cambió, siempre."""
        self.modificar(prioridad="alta")
        aviso = Notificacion.objects.get(destinatario=self.e.capataz)
        self.assertEqual(aviso.titulo, f"Cosecha {self.cosecha.codigo} modificada")
        self.assertIn("prioridad", aviso.detalle.lower())

    def test_post_e_si_la_fecha_atrasa_la_entrega_se_avisa_al_vendedor(self):
        """e y 6c: con contrato y fecha programada posterior a la de entrega, al Vendedor «Cosecha de CV-… con retraso»; sin retraso, no."""
        self.modificar(prioridad="alta")
        self.assertFalse(Notificacion.objects.filter(destinatario=self.e.vendedor).exists())
        self.modificar(fecha_programada=self.venta.fecha_pactada_venta + timedelta(days=2), huella=self.huella())
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor)
        self.assertEqual(aviso.titulo, f"Cosecha de {self.venta.codigo} con retraso")

    def test_post_e_en_un_suministro_el_aviso_nombra_la_posible_indemnizacion(self):
        """e: en un suministro, el aviso al Vendedor lleva la advertencia de posible queja o indemnización según la cláusula."""
        det = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=20, primera_en_dias=8)
        c = cosecha_manual(self.e, [(self.lote, 10)], periodo_=periodo(det, en(8)), dias=2)
        cosechas.modificar_cosecha(self.e.agronomo, c.pk, self.datos(fecha_programada=en(9), lotes=((self.lote.pk, 10),)), self.huella(c))
        self.assertIn("indemnización", Notificacion.objects.get(destinatario=self.e.vendedor).detalle)

    def test_post_f_un_registro_de_auditoria_con_cada_cambio_antes_y_despues(self):
        """f y D-36: UN registro `modificacion_cosecha` con cada cambio (valor anterior y nuevo)."""
        antes = RegistroAuditoria.objects.count()
        self.modificar(fecha_programada=en(6), prioridad="baja")
        self.assertEqual(RegistroAuditoria.objects.count(), antes + 1)
        registro = RegistroAuditoria.objects.latest("pk")
        self.assertEqual((registro.accion, registro.usuario_id), ("modificacion_cosecha", self.e.agronomo.pk))
        cambios = registro.detalle["cambios"]
        self.assertEqual((cambios["prioridad_orden"]["antes"], cambios["prioridad_orden"]["despues"]), ("media", "baja"))
        self.assertIn("fecha_programada_orden", cambios)
        self.assertIn(self.cosecha.codigo, [a["texto"] for a in registro.afectados])

    # ---- extensiones ----

    def test_ext_5b_4a_el_total_asignado_debe_coincidir_con_el_reservado(self):
        """5b.4a: `total_distinto` en `lotes`; hasta que coincidan no se puede terminar, y no se registra nada."""
        self.assertEqual(codigos(self, lambda: self.modificar(lotes=((self.lote.pk, 20),)), "lotes"), ["total_distinto"])
        self.assertEqual(self.lineas(), [(self.lote.pk, 30)])
        verificacion = cosechas.verificar_modificacion(self.e.agronomo, self.cosecha.pk, self.datos(lotes=((self.lote.pk, 20),)))
        self.assertEqual((verificacion.total_asignado, verificacion.total_reservado), (20, 30))
        self.assertEqual([c for c, _ in verificacion.errores["lotes"]], ["total_distinto"])

    def test_ext_5b_4b_la_cantidad_que_supera_el_stock_libre_del_lote_se_rechaza(self):
        """5b.4b: sobre el stock libre que suma lo propio (otras reservas 70 → libre 30 incluyendo las 30 de esta): 31 supera; el mensaje trae el máximo."""
        cosecha_manual(self.e, [(self.lote, 70)], dias=1)
        with self.assertRaises(ValidationError) as rechazo:
            self.modificar(lotes=((self.lote.pk, 31),))
        error = rechazo.exception.error_dict[f"lote_{self.lote.pk}"][0]
        self.assertEqual(error.code, "supera_stock_libre")
        self.assertIn("30", error.message)
        self.modificar(lotes=((self.lote.pk, 30),), prioridad="alta")  # lo propio sí se puede conservar entero
        self.assertEqual(self.lineas(), [(self.lote.pk, 30)])

    def test_ext_5b_4c_si_los_lotes_no_alcanzan_se_avisa_que_hay_que_cancelar_la_orden(self):
        """5b.4c: si los lotes de la variedad ya no alcanzan para lo reservado (una merma bajó el lote), advertencia `lotes_no_alcanzan` que manda
        a cancelar la orden (PROD-CNL-ORD)."""
        Lote.objects.filter(pk=self.lote.pk).update(cantidad_actual=20, costo_acumulado=20)
        self.addCleanup(lambda: Lote.objects.filter(pk=self.lote.pk).update(cantidad_actual=100, costo_acumulado=100))  # antes de los invariantes
        verificacion = cosechas.verificar_modificacion(self.e.agronomo, self.cosecha.pk, self.datos(prioridad="alta"))
        mensajes = [m for c, m in verificacion.advertencias if c == "lotes_no_alcanzan"]
        self.assertEqual(len(mensajes), 1)
        self.assertIn("cancelar", mensajes[0].lower())

    def test_ext_5c_variedad_invernadero_contrato_o_cantidad_total_no_se_modifican(self):
        """5c: si llegan en el POST y difieren de lo guardado, `no_modificable` (la pantalla no los ofrece); si repiten lo guardado, no molestan."""
        for campo, valor in (("variedad_id", 999999), ("invernadero_id", 999999), ("clave_de_detalle", "cv:999999"), ("cantidad_total", 99)):
            with self.subTest(campo=campo):
                self.assertEqual(codigos(self, lambda: self.modificar(prioridad="alta", **{campo: valor}), campo), ["no_modificable"])
        self.modificar(prioridad="alta", variedad_id=self.e.variedad.pk, invernadero_id=self.e.invernadero.pk, cantidad_total=30)

    def test_ext_6a_la_fecha_pasada_se_rechaza(self):
        """6a: `fecha_pasada` en `fecha_programada`."""
        self.assertEqual(codigos(self, lambda: self.modificar(fecha_programada=en(-1)), "fecha_programada"), ["fecha_pasada"])

    def test_ext_6b_con_contrato_el_producto_no_puede_vencer_antes_de_la_entrega(self):
        """6b: fecha + postcosecha anterior a la entrega: `vence_antes_de_la_entrega` con la primera fecha admitida en el mensaje (regla 11 de 8.8)."""
        primera = self.venta.fecha_pactada_venta - timedelta(days=self.postcosecha)
        with self.assertRaises(ValidationError) as rechazo:
            self.modificar(fecha_programada=primera - timedelta(days=1))
        error = rechazo.exception.error_dict["fecha_programada"][0]
        self.assertEqual(error.code, "vence_antes_de_la_entrega")
        self.assertIn(f"{primera:%d/%m/%Y}", error.message)
        self.modificar(fecha_programada=primera)
        self.assertEqual(self.releer().fecha_programada_orden, primera)

    def test_ext_6b_sin_contrato_no_hay_validacion_de_vencimiento(self):
        """6b solo con contrato: una cosecha sin contrato acepta cualquier fecha desde hoy."""
        sin = cosecha_manual(self.e, [(self.lote, 5)], dias=3)
        cosechas.modificar_cosecha(self.e.agronomo, sin.pk, self.datos(fecha_programada=en(0), lotes=((self.lote.pk, 5),)), self.huella(sin))
        self.assertEqual(Cosecha.objects.get(pk=sin.pk).fecha_programada_orden, HOY)

    def test_ext_6c_la_fecha_posterior_a_la_entrega_advierte_retraso_y_deja_modificar(self):
        """6c: advertencia `retraso`; si se mantiene, se registra (y se avisa al Vendedor: ver postcondición e)."""
        fecha = self.venta.fecha_pactada_venta + timedelta(days=2)
        verificacion = cosechas.verificar_modificacion(self.e.agronomo, self.cosecha.pk, self.datos(fecha_programada=fecha))
        self.assertIn("retraso", [c for c, _ in verificacion.advertencias])
        self.assertEqual(verificacion.errores, {})

    def test_ext_6d_un_lote_que_supera_su_fecha_maxima_advierte_con_los_dias_de_exceso(self):
        """6d: advertencia `fecha_maxima` (días corridos entre la máxima y la programada); no bloquea."""
        maxima = api_lotes.fecha_maxima_de_cosecha(self.lote)
        datos = self.datos(fecha_programada=maxima + timedelta(days=2))
        mensajes = [m for c, m in cosechas.verificar_modificacion(self.e.agronomo, self.cosecha.pk, datos).advertencias if c == "fecha_maxima"]
        self.assertEqual(len(mensajes), 1)
        self.assertIn("2 días", mensajes[0])

    def test_ext_7a_sin_cambios_no_se_registra_nada(self):
        """7a: `sin_cambios`; ni auditoría ni avisos."""
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        self.assertEqual(codigos(self, self.modificar), ["sin_cambios"])
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)

    def test_regla_paso_8_el_resumen_muestra_cada_cambio_con_su_valor_anterior_y_el_nuevo(self):
        """Paso 8: `cambios` lista `(campo, antes, despues)` de la fecha, la prioridad, la descripción y los lotes."""
        otro = lote_maduro(self.e, 40)
        verificacion = cosechas.verificar_modificacion(
            self.e.agronomo, self.cosecha.pk, self.datos(prioridad="alta", lotes=((self.lote.pk, 10), (otro.pk, 20)))
        )
        por_campo = {campo: (antes, despues) for campo, antes, despues in verificacion.cambios}
        self.assertEqual(por_campo["prioridad"], ("media", "alta"))
        self.assertEqual(set(por_campo), {"prioridad", "lotes"})

    def test_ext_10a_si_la_cosecha_ya_se_concreto_o_cancelo_no_se_registra_nada(self):
        """10a: `cosecha_resuelta` con el estado actual; nada registrado."""
        huella = self.huella()
        for estado in ("concretada", "cancelada"):
            OrdenTrabajo.objects.filter(pk=self.cosecha.pk).update(
                estado_orden=estado, fecha_resolucion_orden=HOY, motivo_cancelacion="x" if estado == "cancelada" else None
            )
            with self.subTest(estado=estado):
                with self.assertRaises(ValidationError) as rechazo:
                    self.modificar(prioridad="alta", huella=huella)
                error = next(e for lista in rechazo.exception.error_dict.values() for e in lista)
                self.assertEqual(error.code, "cosecha_resuelta")
                self.assertIn(estado, error.message)
        self.assertEqual(self.releer().prioridad_orden, "media")

    def test_ext_10a_la_huella_cambiada_se_rechaza_con_cosecha_cambio(self):
        """Paso 10: si alguien modificó la cosecha mientras se editaba (la huella leída al abrir ya no coincide), `cosecha_cambio`."""
        huella = self.huella()
        self.modificar(descripcion="otro cambio", huella=huella)
        self.assertEqual(codigos(self, lambda: self.modificar(prioridad="alta", huella=huella)), ["cosecha_cambio"])
        self.assertEqual(self.releer().prioridad_orden, "media")

    def test_ext_10b_si_otra_operacion_reservo_el_stock_del_lote_no_se_registra_nada(self):
        """10b: al registrar, el stock libre de un lote ya no alcanza (otra operación lo reservó): `supera_stock_libre` y nada cambia."""
        otro = lote_maduro(self.e, 25)
        huella = self.huella()
        cosecha_manual(self.e, [(otro, 20)], dias=1)  # otra operación reserva casi todo el lote nuevo
        self.assertEqual(
            codigos(self, lambda: self.modificar(lotes=((otro.pk, 30),), huella=huella), f"lote_{otro.pk}"), ["supera_stock_libre"]
        )
        self.assertEqual(self.lineas(), [(self.lote.pk, 30)])

    def test_regla_garantia_minima_si_falla_la_cosecha_y_su_reserva_quedan_como_estaban(self):
        """Garantías mínimas: un rechazo no cambia la cosecha ni sus líneas ni deja auditoría ni avisos."""
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        with self.assertRaises(ValidationError):
            self.modificar(fecha_programada=en(-1), prioridad="alta")
        c = self.releer()
        self.assertEqual((c.prioridad_orden, c.fecha_programada_orden, self.lineas()), ("media", en(5), [(self.lote.pk, 30)]))
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)
