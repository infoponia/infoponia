# Pruebas de concurrencia de la confirmación de una entrega (COM-06b, paso 3; docs/casos_de_uso/comercial/confirmacion.md, «Pruebas»; docs/patrones/bloqueos.md, «Confirmar una entrega»): dos
# respuestas del mismo enlace a la vez (se registra una sola; la otra se rechaza con `enlace_no_sirve`) y la respuesta contra atender la entrega no reconocida de la misma entrega (las dos terminan, en
# fila en la entrega, sin interbloqueo: las dos toman las cuentas, el invernadero y la entrega en el mismo orden). Dos hilos, dos conexiones, el orden fijado con ``primera``.
# Son ``TransactionTestCase``: sin Georef de la migración (el cliente tiene una dirección en la localidad propia que arma `geografia_propia`). Terminan verificando los invariantes.
# Nunca un error 500: el que pierde espera, relee con todo bloqueado y se rechaza con un código.

from types import SimpleNamespace

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import EnlaceCliente, Queja
from comercial.servicios import atencion, confirmacion
from comercial.servicios.confirmacion import CON_QUEJAS, CONFORME, DatosDeRespuesta, QuejaPedida
from comercial.tests.fabricas import (
    alerta_no_reconocida,
    detalle_suministro,
    direccion_de_cliente,
    enlace_de_confirmacion,
    entrega,
    escenario_comercial,
    marcar_concretada,
    reserva_lista,
    suministro,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_solicitudes,
)
from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Alerta, Localidad
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.tests.fabricas import lote_maduro, separar

HOY = timezone.localdate()


@tag("concurrencia")
class ConfirmacionConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self):
        """Un invernadero con su Vendedor, un lote de 500, un Gerente y un cliente con una dirección en la localidad propia."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 500)
        self.gerente = crear_gerente()
        self.direccion = direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk).direccion
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)

    def entrega_confirmable(self):
        """Una entrega de suministro concretada con su enlace de confirmación vigente. Devuelve `SimpleNamespace(entrega, enlace, linea)`."""
        contrato = suministro(self.e)
        detalle = detalle_suministro(contrato, self.e.variedad, direccion=self.direccion, cantidad=10, minima=8)
        reserva = reserva_lista(None, self.lote, 10, fecha_entrega=detalle.fecha_primer_entrega, detalle_suministro=detalle)
        concretada = marcar_concretada(entrega(contrato, [reserva]))
        creado, _ = enlace_de_confirmacion(concretada)
        return SimpleNamespace(entrega=concretada, enlace=creado, linea=concretada.lineas.get())

    def test_regla_dos_respuestas_del_mismo_enlace_una_se_registra_y_la_otra_se_rechaza(self):
        """Requisito especial de COM-CNF-ENT: el control de concurrencia impide que un mismo enlace registre dos respuestas. La segunda espera, ve el enlace `usado` (6a) y se rechaza con `enlace_no_sirve`:
        una sola queja, un solo registro de auditoría."""
        self.armar()
        x = self.entrega_confirmable()
        respuesta = DatosDeRespuesta(CON_QUEJAS, [QuejaPedida("otro", [x.linea.pk], "Falta algo.")])
        operacion = lambda: confirmacion.registrar_respuesta(x.enlace.pk, respuesta)
        resultados = correr_a_la_vez(operacion, operacion, primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((len(buenos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["enlace_no_sirve"])
        self.assertEqual(Queja.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="respuesta_cliente_entrega").count(), 1)
        self.assertEqual(EnlaceCliente.objects.get(pk=x.enlace.pk).estado, "usado")

    def test_regla_la_respuesta_contra_atender_la_no_reconocida_de_la_misma_entrega_terminan_las_dos(self):
        """Bloqueos de «Confirmar una entrega»: la respuesta del cliente y la atención del Gerente toman las cuentas, el invernadero y la entrega en el mismo orden, así que se ponen en fila y terminan las dos
        (en cualquiera de los dos órdenes): la alerta queda resuelta con su resultado y el enlace, usado."""
        self.armar()
        for primera in ("a", "b"):
            x = self.entrega_confirmable()
            alerta = alerta_no_reconocida(x.entrega)
            responder = lambda x=x: confirmacion.registrar_respuesta(x.enlace.pk, DatosDeRespuesta(CONFORME))
            atender = lambda alerta=alerta: atencion.atender_entrega_no_reconocida(self.gerente, alerta.pk, "llego", "El cliente se equivocó.")
            resultados = correr_a_la_vez(responder, atender, primera=primera)
            buenos, rechazos, otros = separar(resultados)
            self.assertEqual((len(buenos), rechazos, otros), (2, [], []), (primera, resultados))
            self.assertEqual(Alerta.objects.get(pk=alerta.pk).estado_alerta, "resuelta")
            self.assertEqual(EnlaceCliente.objects.get(pk=x.enlace.pk).estado, "usado")
