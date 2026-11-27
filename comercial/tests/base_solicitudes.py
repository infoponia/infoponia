# Base compartida de las pruebas de servicios de COM-07a (test_com_evl_dsc, test_com_rsv_qja, test_com_anl_srv, test_com_cns_srv): arma, directo en la base y con las fábricas, un suministro con una entrega
# concretada (cantidad, mínima, entregada, precio y cláusula a gusto) y su solicitud pendiente (una discrepancia o una queja), con la alerta y el Gerente. Cada prueba arma sus propios datos.
# Fuente: docs/casos_de_uso/comercial/solicitudes.md («Pruebas»).

from datetime import timedelta
from types import SimpleNamespace

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from comercial.models import Suministro
from comercial.servicios import solicitudes
from comercial.servicios.solicitudes import DatosDeResolucion
from comercial.tests.fabricas import (
    detalle_suministro,
    discrepancia,
    entrega,
    escenario_comercial,
    marcar_concretada,
    queja,
    queja_aceptada,
    reserva_lista,
    suministro,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_solicitudes,
)
from contabilidad.tests.fabricas import PlanDeCuentasMixin, verificar_invariantes_contables
from core.models import Notificacion
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.tests.fabricas import lote_maduro, variedad_con_stock
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HOY = timezone.localdate()


def codigos(error):
    """Los códigos de un `ValidationError` con o sin `error_dict`."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


def campos(error):
    return sorted(error.error_dict) if hasattr(error, "error_dict") else []


def poner_estado(contrato, estado):
    """Lleva un suministro al `estado` pedido con los datos que exige la base (`resuelto` y `rescindido` traen sus fechas)."""
    if estado == "resuelto":
        Suministro.objects.filter(pk=contrato.pk).update(estado_suministro="resuelto", fecha_resolucion_suministro=HOY)
    elif estado == "rescindido":
        Suministro.objects.filter(pk=contrato.pk).update(
            estado_suministro="rescindido", fecha_rescision=HOY, motivo_rescision="a_pedido_del_cliente", fecha_acuerdo_rescision=HOY, fecha_registro_rescision=HOY, fecha_ultima_entrega_rescision=HOY
        )
    else:
        Suministro.objects.filter(pk=contrato.pk).update(estado_suministro=estado)


class BaseDeSolicitudes(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, un lote y un Gerente. `armar()` deja un suministro con una entrega concretada y su solicitud pendiente."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.gerente = crear_gerente()

    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)
        self.addCleanup(verificar_invariantes_contables)  # CON-04d: aceptar y anular una resolución asientan
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba

    def armar(
        self, *, tipo="discrepancia", cantidad=10, minima=8, entregada=5, precio="100.00", tolerados=3, incumplimientos=0, plazo_entrega=0, retraso=0, por_dia="10.00", por_planta="5.00",
        queja_tipo="estado_mercaderia", estado_contrato="vigente", dos_lineas=False, con_alerta=True,
    ):
        """Un suministro de `cantidad` plantas por período a `precio` (mínimo `minima`), con la entrega concretada con `entregada` plantas (el resto perdido) y su solicitud pendiente: una discrepancia
        (`tipo="discrepancia"`) o una queja de `queja_tipo`. ``retraso`` son los días de retraso de la entrega (la fecha del período queda en el pasado). ``dos_lineas`` suma un segundo detalle
        (otra dirección del cliente) con las mismas cantidades. Devuelve `SimpleNamespace(contrato, detalle, detalles, entrega, solicitud)`."""
        contrato = suministro(self.e, tolerados=tolerados, plazo_pago=15)
        detalles = [
            detalle_suministro(
                contrato, self.e.variedad, cantidad=cantidad, minima=minima, precio=precio, primera_en_dias=-(retraso + plazo_entrega), plazo_entrega=plazo_entrega,
                indemnizacion_retraso=por_dia, indemnizacion_faltante=por_planta,
            )
        ]
        if dos_lineas:
            # Una entrega tiene un solo destino: el segundo detalle es de OTRA variedad en la misma dirección (el par variedad-dirección vigente es único).
            otra_variedad = variedad_con_stock(self.e, nombre="Otra")[0]
            detalles.append(
                detalle_suministro(
                    contrato, otra_variedad, cantidad=cantidad, minima=minima, precio=precio, primera_en_dias=-(retraso + plazo_entrega), plazo_entrega=plazo_entrega,
                    indemnizacion_retraso=por_dia, indemnizacion_faltante=por_planta,
                )
            )
        reservas = [reserva_lista(None, self.lote, cantidad, fecha_entrega=d.fecha_primer_entrega, detalle_suministro=d) for d in detalles]
        concretada = marcar_concretada(entrega(contrato, reservas), cantidades=[(entregada, cantidad - entregada, 0)] * len(detalles))
        if estado_contrato != "vigente":
            poner_estado(contrato, estado_contrato)
        x = SimpleNamespace(contrato=contrato, detalle=detalles[0], detalles=detalles, entrega=concretada)
        x.solicitud = discrepancia(concretada, minima=minima, con_alerta=con_alerta) if tipo == "discrepancia" else queja(concretada, queja_tipo, con_alerta=con_alerta)
        # Los incumplimientos previos salen de solicitudes aceptadas de otras entregas del mismo contrato (el invariante: contador = aceptadas), sin monto: no tocan el monto a cobrar de `x`.
        for i in range(incumplimientos):
            queja_aceptada(self._entrega_extra(x, dias=7 * (i + 20)), "otro", monto="0.00")
        return x

    def _entrega_extra(self, x, *, dias, entregada=5):
        """Una entrega concretada más del primer detalle de `x`, `dias` después de su primer período."""
        detalle = x.detalle
        cantidad = detalle.cantidad_por_periodo
        reserva = reserva_lista(None, self.lote, cantidad, fecha_entrega=detalle.fecha_primer_entrega + timedelta(days=dias), detalle_suministro=detalle)
        return marcar_concretada(entrega(x.contrato, [reserva]), cantidades=[(entregada, cantidad - entregada, 0)])

    def otra(self, x, *, tipo="discrepancia", entregada=5, queja_tipo="estado_mercaderia", dias=7):
        """Otra entrega concretada del MISMO suministro (el período siguiente de su primer detalle) con su solicitud pendiente."""
        detalle = x.detalle
        concretada = self._entrega_extra(x, dias=dias, entregada=entregada)
        y = SimpleNamespace(contrato=x.contrato, detalle=detalle, detalles=[detalle], entrega=concretada)
        y.solicitud = discrepancia(concretada, minima=detalle.clausula_suministrante.cantidad_minima) if tipo == "discrepancia" else queja(concretada, queja_tipo)
        return y

    def datos(self, decision="aceptar", observaciones="", monto="", medio=""):
        return DatosDeResolucion(decision, observaciones, monto, medio)

    def resumen(self, solicitud, decision="aceptar", observaciones="", monto="", medio="", actor=None):
        return solicitudes.resumen_de_resolucion(actor or self.gerente, solicitud.pk, self.datos(decision, observaciones, monto, medio))

    def resolver(self, solicitud, decision="aceptar", observaciones="", monto="", medio="", actor=None, huella=None):
        """Resumen y registro, como la pantalla: la huella es la del resumen (o la pasada)."""
        datos = self.datos(decision, observaciones, monto, medio)
        resumen = solicitudes.resumen_de_resolucion(actor or self.gerente, solicitud.pk, datos)
        return solicitudes.resolver_solicitud(actor or self.gerente, solicitud.pk, datos, resumen.huella if huella is None else huella)

    def rechazo(self, funcion, *args, **kwargs):
        """El `ValidationError` que lanza `funcion` (la prueba falla si no lanza)."""
        with self.assertRaises(ValidationError) as c:
            funcion(*args, **kwargs)
        return c.exception

    def avisos(self, cuenta, titulo=""):
        return list(Notificacion.objects.filter(destinatario=cuenta, titulo__startswith=titulo).order_by("pk"))
