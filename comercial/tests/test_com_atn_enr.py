# Pruebas de COM-ATN-ENR · Atender Entrega No Reconocida (COM-06b, paso 4): `atencion.ficha_de_no_reconocida`, `atender_entrega_no_reconocida`, `alerta_activa_de`. Una por regla (1 a 5) y
# postcondición (a a c); solo el Gerente; la alerta ya resuelta; que no toca la entrega, el stock, los asientos ni los incumplimientos (regla 3). La entrega y la alerta salen del recorrido real:
# se concreta un suministro con `concretar_entrega` y el cliente responde «no recibí» con `registrar_respuesta` (así la ficha encuentra los registros de auditoría que lee).
# Fuente: docs/casos_de_uso/comercial/confirmacion.md («COM-ATN-ENR» y «Atender una entrega no reconocida»), D-68 punto 9 y MD-137. Las pruebas numeran sus reglas (`test_regla_2_…`).
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa): `atender_entrega_no_reconocida(actor, alerta_id, resultado, descripcion) -> Alerta`; códigos `resultado_obligatorio`,
# `resultado_invalido`, `descripcion_obligatoria`, `descripcion_larga`, `alerta_resuelta`, `entrega_cobrada`; `PermissionDenied` y `Http404`. La notificación de «no llegó» va al Vendedor y al
# responsable contable (el Contador activo o, sin Contador, el Gerente), nunca al Gerente que atiende (decisión del estudiante del 25/11/2026; `docs/disparadores.md`, «Cuando exista el rol Contador»).

from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega, IntentoFallido, Suministro
from comercial.servicios import atencion, concrecion, confirmacion
from comercial.servicios.concrecion import DatosDeConcrecion
from comercial.servicios.confirmacion import NO_RECIBI, DatosDeRespuesta
from comercial.tests.fabricas import entrega_concretable, escenario_comercial, verificar_invariantes_de_entregas, verificar_invariantes_de_solicitudes
from contabilidad.models import AsientoContable
from core.models import Contador, Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_cuenta, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta
from maestros.tests.fabricas import crear_alerta
from produccion.models import MovimientoStock, StockCosechado
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def codigos(error):
    """Los códigos de un `ValidationError` con o sin `error_dict`."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


def campos(error):
    return sorted(error.error_dict) if hasattr(error, "error_dict") else []


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, un lote y un Gerente. `no_reconocida()` arma el recorrido real hasta la alerta crítica."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.gerente = crear_gerente()

    def setUp(self):
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)

    def no_reconocida(self, *, con_envasado=True):
        """Concreta un suministro de 100 plantas (con 10 envases reservados) y el cliente responde que no la recibió. Devuelve el `SimpleNamespace` de `entrega_concretable` con `alerta`."""
        x = entrega_concretable(self.e, self.lote, tipo="suministro", cantidad=100, minima=50, con_envasado=con_envasado)
        datos = DatosDeConcrecion(sin_envases=not con_envasado)
        resumen = concrecion.resumen_de_concrecion(x.transportista, x.entrega.pk, datos)
        concrecion.concretar_entrega(x.transportista, x.entrega.pk, datos, resumen.huella)
        enlace = x.entrega.enlaces.get()
        confirmacion.registrar_respuesta(enlace.pk, DatosDeRespuesta(NO_RECIBI, motivo_no_recibi="No llegó nada a la sucursal."))
        x.alerta = Alerta.objects.get(vinculo_comercial__entrega=x.entrega.pk, tipo_alerta="comercial_entrega_no_reconocida")
        return x

    def atender(self, x, resultado="no_llego_perdido", descripcion="Hablé con el cliente: no llegó.", actor=None):
        return atencion.atender_entrega_no_reconocida(actor or self.gerente, x.alerta.pk, resultado, descripcion)

    def avisos(self, cuenta, titulo="Corregir los asientos"):
        return list(Notificacion.objects.filter(destinatario=cuenta, titulo__startswith=titulo).order_by("pk"))


class FichaTests(Base):
    def test_regla_1_la_ficha_trae_todo_lo_que_genero_la_entrega(self):
        """Regla 1: las líneas con sus cantidades, el transportista y su vehículo, cuándo se concretó, los intentos fallidos, la confirmación con el motivo del cliente, los consumos de envases, el cobro y los
        asientos («Fuera de esta ronda · contabilidad», D-57)."""
        x = self.no_reconocida()
        IntentoFallido.objects.create(entrega=x.entrega, transportista=x.transportista, fecha_programada=HOY, motivo="cliente_ausente", descripcion="Nadie atendió.")
        ficha = atencion.ficha_de_no_reconocida(self.gerente, x.alerta.pk)
        (linea,) = ficha.lineas
        self.assertEqual((linea.planificada, linea.entregada, linea.perdida, linea.devuelta), (100, 100, 0, 0))
        self.assertEqual((ficha.entrega.pk, ficha.contrato.pk, ficha.cliente.pk, ficha.vendedor.pk, ficha.transportista.pk), (x.entrega.pk, x.contrato.pk, self.e.cliente.pk, self.e.vendedor.pk, x.transportista.pk))
        self.assertIsNotNone(ficha.vehiculo)
        self.assertIsNotNone(ficha.concretada_en)
        self.assertEqual([i.motivo for i in ficha.intentos], ["cliente_ausente"])
        self.assertEqual((ficha.confirmacion, ficha.motivo_del_cliente), ("No confirmada", "No llegó nada a la sucursal."))
        self.assertEqual(len(ficha.consumos), 1)
        self.assertIn("Bandeja", ficha.consumos[0])
        self.assertEqual((ficha.cobro, ficha.asientos), ("Sin cobro registrado", "Fuera de esta ronda · contabilidad"))
        self.assertEqual([valor for valor, _ in ficha.resultados], ["llego", "no_llego_perdido", "no_llego_devuelto"])

    def test_regla_1_sin_envasado_ni_intentos_la_ficha_los_deja_vacios(self):
        """Regla 1: una entrega sin envasado ni intentos fallidos no trae consumos ni intentos."""
        x = self.no_reconocida(con_envasado=False)
        ficha = atencion.ficha_de_no_reconocida(self.gerente, x.alerta.pk)
        self.assertEqual((ficha.consumos, ficha.intentos), ([], []))

    def test_precondicion_solo_el_gerente_activo(self):
        """Precondición a: el actor es un Gerente con la cuenta activa; el Vendedor, el Transportista y un Gerente dado de baja reciben `PermissionDenied`."""
        x = self.no_reconocida()
        for actor in (self.e.vendedor, x.transportista):
            with self.assertRaises(PermissionDenied):
                atencion.ficha_de_no_reconocida(actor, x.alerta.pk)
            with self.assertRaises(PermissionDenied):
                atencion.atender_entrega_no_reconocida(actor, x.alerta.pk, "llego", "Se equivocó.")
        from core.models import Usuario

        Usuario.objects.filter(pk=self.gerente.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            atencion.ficha_de_no_reconocida(self.gerente, x.alerta.pk)
        with self.assertRaises(PermissionDenied):
            self.atender(x, "llego", "Se equivocó.")
        self.assertEqual(Alerta.objects.get(pk=x.alerta.pk).estado_alerta, "activa")

    def test_precondicion_b_una_alerta_de_otro_tipo_o_inexistente_es_404(self):
        """Precondición b: la alerta tiene que ser una «entrega no reconocida»; cualquier otra o un id que no existe da `Http404`."""
        otra = crear_alerta(self.e.invernadero, "comercial_discrepancia_entrega")
        for alerta_id in (otra.pk, 999999):
            with self.assertRaises(Http404):
                atencion.ficha_de_no_reconocida(self.gerente, alerta_id)
            with self.assertRaises(Http404):
                atencion.atender_entrega_no_reconocida(self.gerente, alerta_id, "llego", "x")

    def test_precondicion_b_una_alerta_ya_resuelta_no_se_atiende_ni_se_muestra(self):
        """Precondición b: la alerta tiene que estar activa: la ya resuelta da `alerta_resuelta` en la ficha y al atenderla de nuevo."""
        x = self.no_reconocida()
        self.atender(x, "llego", "El cliente se equivocó.")
        with self.assertRaises(ValidationError) as c:
            atencion.ficha_de_no_reconocida(self.gerente, x.alerta.pk)
        self.assertEqual(codigos(c.exception), ["alerta_resuelta"])
        with self.assertRaises(ValidationError) as c:
            self.atender(x, "no_llego_perdido", "Otra vez.")
        self.assertEqual(codigos(c.exception), ["alerta_resuelta"])
        self.assertEqual(AlertaComercial.objects.get(alerta=x.alerta).resultado_averiguacion, "llego")  # el primero se conserva

    def test_alerta_activa_de_encuentra_la_alerta_mientras_este_activa(self):
        """`alerta_activa_de(entrega_id)` (para el enlace «Atender» de la ficha del suministro): el id de la alerta activa y, resuelta, `None`."""
        x = self.no_reconocida()
        self.assertEqual(atencion.alerta_activa_de(x.entrega.pk), x.alerta.pk)
        self.atender(x, "llego", "Se equivocó.")
        self.assertIsNone(atencion.alerta_activa_de(x.entrega.pk))


class AtenderTests(Base):
    def test_post_a_la_alerta_queda_resuelta_con_el_resultado_y_la_descripcion(self):
        """Postcondición a: la alerta pasa a «resuelta» con su fecha, y la `AlertaComercial` guarda el resultado y la descripción (obligatoria, sin espacios al borde; MD-137)."""
        x = self.no_reconocida()
        resuelta = self.atender(x, "no_llego_perdido", "  Hablé con el cliente y con el chofer.  ")
        self.assertEqual((resuelta.pk, resuelta.estado_alerta, resuelta.fecha_resolucion is not None), (x.alerta.pk, "resuelta", True))
        vinculo = AlertaComercial.objects.get(alerta=x.alerta)
        self.assertEqual((vinculo.resultado_averiguacion, vinculo.descripcion_averiguacion), ("no_llego_perdido", "Hablé con el cliente y con el chofer."))

    def test_regla_2_cada_resultado_de_la_lista_cierra_la_alerta(self):
        """Regla 2: «la entrega llegó», «no llegó, producto perdido» y «no llegó, producto devuelto» son los resultados válidos."""
        for resultado in ("llego", "no_llego_perdido", "no_llego_devuelto"):
            x = self.no_reconocida(con_envasado=False)
            self.atender(x, resultado, f"Resultado {resultado}.")
            self.assertEqual(AlertaComercial.objects.get(alerta=x.alerta).resultado_averiguacion, resultado)

    def test_regla_2_el_resultado_es_obligatorio_y_de_la_lista(self):
        """Regla 2: sin resultado, `resultado_obligatorio`; uno fuera de la lista, `resultado_invalido`; la alerta sigue activa."""
        x = self.no_reconocida()
        for valor, codigo in (("", "resultado_obligatorio"), ("perdido", "resultado_invalido")):
            with self.assertRaises(ValidationError) as c:
                self.atender(x, valor)
            self.assertEqual((codigos(c.exception), campos(c.exception)), ([codigo], ["resultado"]))
        self.assertEqual(Alerta.objects.get(pk=x.alerta.pk).estado_alerta, "activa")

    def test_post_a_la_descripcion_es_obligatoria_y_de_hasta_500_caracteres(self):
        """Postcondición a: la descripción es obligatoria (`descripcion_obligatoria`) y de hasta 500 caracteres (`descripcion_larga`)."""
        x = self.no_reconocida()
        for valor, codigo in (("   ", "descripcion_obligatoria"), ("x" * 501, "descripcion_larga")):
            with self.assertRaises(ValidationError) as c:
                self.atender(x, "llego", valor)
            self.assertEqual((codigos(c.exception), campos(c.exception)), ([codigo], ["descripcion"]))
        self.atender(x, "llego", "x" * 500)

    def test_regla_3_no_toca_la_entrega_el_stock_los_asientos_ni_los_incumplimientos(self):
        """Regla 3: sin reversión automática: la entrega sigue concretada con sus montos, no hay movimientos de stock ni partidas nuevas, no se crean asientos y los incumplimientos del contrato no cambian."""
        x = self.no_reconocida()
        entrega = lambda: Entrega.objects.values("estado_orden", "estado_confirmacion_cliente", "monto_total_entrega", "fecha_vencimiento_pago", "fecha_resolucion_orden").get(pk=x.entrega.pk)
        antes = (entrega(), MovimientoStock.objects.count(), StockCosechado.objects.count(), AsientoContable.objects.count(), Suministro.objects.get(pk=x.contrato.pk).cantidad_incumplimientos)
        self.atender(x, "no_llego_perdido", "Se perdió en el camino.")
        despues = (entrega(), MovimientoStock.objects.count(), StockCosechado.objects.count(), AsientoContable.objects.count(), Suministro.objects.get(pk=x.contrato.pk).cantidad_incumplimientos)
        self.assertEqual(despues, antes)
        self.assertEqual(despues[0]["estado_orden"], "concretada")

    def test_regla_4_el_producto_devuelto_no_reingresa_a_la_camara(self):
        """Regla 4: el reingreso del producto devuelto es una mejora futura: no se crea ninguna partida ni movimiento; la descripción lo registra."""
        x = self.no_reconocida()
        partidas, movimientos = StockCosechado.objects.count(), MovimientoStock.objects.count()
        self.atender(x, "no_llego_devuelto", "Volvió a la sucursal; se registra acá.")
        self.assertEqual((StockCosechado.objects.count(), MovimientoStock.objects.count()), (partidas, movimientos))
        self.assertEqual(AlertaComercial.objects.get(alerta=x.alerta).descripcion_averiguacion, "Volvió a la sucursal; se registra acá.")

    def test_regla_5_si_la_entrega_ya_se_cobro_y_no_llego_primero_se_anula_el_cobro(self):
        """Regla 5: con un cobro vigente (desde COM-08a) «no llegó» se rechaza con `entrega_cobrada`; «la entrega llegó» no pide anular nada. Hasta COM-08a el cobro se simula."""
        x = self.no_reconocida()
        with mock.patch("comercial.servicios.atencion._tiene_cobro_vigente", return_value=True):
            for resultado in ("no_llego_perdido", "no_llego_devuelto"):
                with self.assertRaises(ValidationError) as c:
                    self.atender(x, resultado)
                self.assertEqual(codigos(c.exception), ["entrega_cobrada"])
            self.assertEqual(Alerta.objects.get(pk=x.alerta.pk).estado_alerta, "activa")
            self.atender(x, "llego", "El cliente se equivocó.")
        self.assertEqual(Alerta.objects.get(pk=x.alerta.pk).estado_alerta, "resuelta")

    def test_post_b_no_llego_avisa_al_vendedor_y_al_responsable_contable_sin_el_gerente_que_atiende(self):
        """Postcondición b: con «no llegó» se avisa al Vendedor del contrato y al responsable contable: sin Contador es el Gerente, que es quien atiende y no se avisa a sí mismo."""
        x = self.no_reconocida()
        self.atender(x, "no_llego_perdido")
        (aviso,) = self.avisos(self.e.vendedor)
        self.assertIn(x.entrega.codigo, aviso.detalle)
        self.assertIn("no llegó al cliente (producto perdido)", aviso.detalle)
        self.assertIn("corregir los asientos a mano", aviso.detalle)
        self.assertEqual(self.avisos(self.gerente), [])

    def test_post_b_con_contador_el_aviso_va_al_contador_y_no_al_gerente(self):
        """Postcondición b (H12, disparador «Cuando exista el rol Contador»): con un Contador activo, el aviso va al Contador y al Vendedor; con «producto devuelto» el texto lo dice."""
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        x = self.no_reconocida()
        self.atender(x, "no_llego_devuelto")
        self.assertEqual(len(self.avisos(self.e.vendedor)), 1)
        (aviso,) = self.avisos(contador)
        self.assertIn("no llegó al cliente (producto devuelto)", aviso.detalle)
        self.assertEqual(self.avisos(self.gerente), [])

    def test_post_b_la_entrega_que_llego_no_avisa_a_nadie(self):
        """Postcondición b es solo de «no llegó»: con «la entrega llegó» (el cliente se equivocó) no hay nada que corregir y no se avisa."""
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        x = self.no_reconocida()
        antes = Notificacion.objects.count()
        self.atender(x, "llego", "El cliente se equivocó de pedido.")
        self.assertEqual(Notificacion.objects.count(), antes)
        self.assertEqual(self.avisos(contador), [])

    def test_post_b_sin_vendedor_activo_igual_se_atiende(self):
        """Un Vendedor del contrato dado de baja no impide atender: solo queda el responsable contable (o nadie, si es quien atiende)."""
        from core.models import Usuario

        x = self.no_reconocida()
        Usuario.objects.filter(pk=self.e.vendedor.pk).update(is_active=False)
        self.atender(x, "no_llego_perdido")
        self.assertEqual(Alerta.objects.get(pk=x.alerta.pk).estado_alerta, "resuelta")
        self.assertEqual(self.avisos(self.e.vendedor), [])

    def test_post_c_un_registro_de_auditoria_con_el_gerente_la_alerta_la_entrega_y_el_resultado(self):
        """Postcondición c: un registro `atencion_entrega_no_reconocida` con el usuario y su rol, la alerta y la entrega afectadas y, en `datos`, el resultado y la descripción."""
        x = self.no_reconocida()
        self.atender(x, "no_llego_perdido", "Se perdió.")
        registro = RegistroAuditoria.objects.get(accion="atencion_entrega_no_reconocida")
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        self.assertEqual({(a["modelo"], a["id"]) for a in registro.afectados}, {("maestros.alerta", x.alerta.pk), ("comercial.entrega", x.entrega.pk)})
        datos = registro.detalle["datos"]
        self.assertEqual((datos["resultado_averiguacion"], datos["descripcion_averiguacion"], datos["entrega"]["id"], datos["alerta"]["id"]), ("no_llego_perdido", "Se perdió.", x.entrega.pk, x.alerta.pk))

    def test_regla_el_registro_es_atomico_si_falla_no_queda_nada(self):
        """Una transacción: si la auditoría falla, la alerta sigue activa, el resultado sin cargar y no hay avisos."""
        x = self.no_reconocida()
        antes = Notificacion.objects.count()
        with mock.patch("comercial.servicios.atencion.RegistroAuditoria.objects.registrar", side_effect=RuntimeError("falla")), self.assertRaises(RuntimeError):
            self.atender(x, "no_llego_perdido")
        vinculo = AlertaComercial.objects.get(alerta=x.alerta)
        self.assertEqual((Alerta.objects.get(pk=x.alerta.pk).estado_alerta, vinculo.resultado_averiguacion, vinculo.descripcion_averiguacion, Notificacion.objects.count()), ("activa", None, "", antes))
