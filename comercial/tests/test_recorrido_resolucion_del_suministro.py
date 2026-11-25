# Recorrido de COM-07b (D-96): de punta a punta con el cliente de Django, como lo hace una persona, por rol y por estado. El Gerente evalúa la discrepancia que supera los incumplimientos tolerados de un suministro
# (el resumen lo advierte) y la acepta: InfoPonia resuelve el contrato después del commit (cancela la cosecha y la entrega, libera las reservas, pasa lo cosechado a la cámara) y avisa; el Gerente ve la alerta en la
# campana, entra por su enlace a la ficha, intenta anular la aceptación (se rechaza) y da por atendida la resolución; el Vendedor ve lo mismo en lectura, sin el botón; otro rol no entra. Después, el disparo perdido: el paso
# diario 33 (`proceso_diario --solo resolver_suministros`) resuelve un contrato que quedó vigente con más incumplimientos que los tolerados, y una segunda corrida no hace nada. No reemplaza la «Verificación a mano» del
# estudiante: la complementa. Lo que solo ve un navegador (CSRF real, `Origin`, el aviso breve y el aspecto) queda para el paso de «navegador real» de esa verificación.
# Fuente: docs/casos_de_uso/comercial/resolucion.md («Pantallas», «Verificación a mano» de la tarea COM-07b), D-30, D-61, D-69 (puntos 5, 7, 13, 14 y 15), D-56.

from datetime import timedelta
from html import unescape
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from comercial.models import AlertaComercial, Entrega, ReservaStock, Suministro
from comercial.tests.base_solicitudes import HOY, BaseDeSolicitudes
from comercial.tests.fabricas import (
    _aceptar,
    entrega,
    reserva_de_periodo,
    reserva_lista,
    transportista_con_vehiculo,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_resolucion,
)
from core.models import Notificacion, RegistroAuditoria
from maestros.models import Alerta
from produccion.models import Cosecha, StockCosechado
from produccion.tests.fabricas import reservar


def texto(respuesta):
    return unescape(respuesta.content.decode())


@override_settings(CORREO_CONFIGURADO=True)
class RecorridoDeResolucionDelSuministroTests(BaseDeSolicitudes):
    def setUp(self):
        super().setUp()
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_resolucion)

    def armar_el_escenario(self):
        """Un suministro con 0 tolerados y multa de $ 50.000,00, con la discrepancia pendiente de una entrega ya concretada (su reserva «entregada»), una entrega «a realizar» con su Transportista y 5 envases
        reservados (período +7, reserva «lista para entrega») y una reserva «activa» con su cosecha «a realizar» (período +14)."""
        x = self.armar(tolerados=0)
        ReservaStock.objects.filter(detalle_suministro=x.detalle).update(estado_reserva="entregada")  # la que ya se entregó
        t = transportista_con_vehiculo(self.e.invernadero, "800")
        r = reserva_lista(None, self.lote, 10, fecha_entrega=HOY + timedelta(days=7), detalle_suministro=x.detalle)
        x.entrega_a_realizar = entrega(x.contrato, [r], transportista=t)
        x.envases = reservar(x.entrega_a_realizar, self.e.existencia_semilla, 5)
        x.reserva_activa = reserva_de_periodo(x.detalle, HOY + timedelta(days=14), [(self.lote, 20)])
        x.transportista = t
        return x

    def test_recorrido_del_gerente_el_vendedor_y_el_paso_diario(self):
        """COM-RSV-SUM de punta a punta: la aceptación que supera lo tolerado resuelve el contrato; la ficha, la lista, la campana y «Dar por atendida» por rol; el disparo perdido y el paso 33."""
        x = self.armar_el_escenario()
        g = self.client

        # 1. Con el contrato vigente, la ficha del Gerente no tiene aviso de resolución ni «Dar por atendida» (regla 4 de COM-CNS-SUM: solo lo que corresponde).
        g.force_login(self.gerente)
        ficha = texto(g.get(reverse("comercial:suministro", args=[x.contrato.pk])))
        self.assertNotIn("Resuelto por incumplimientos", ficha)
        self.assertNotIn("Dar por atendida", ficha)

        # 2. Disparador 1 y extensión 6b de COM-EVL-DSC: el resumen de la discrepancia advierte que el contrato se resuelve, con la multa.
        revisar = reverse("comercial:solicitud_resolver_revisar", args=[x.solicitud.pk])
        resumen = texto(g.post(revisar, {"decision": "aceptar", "observaciones": "Se cargó menos."}, HTTP_HX_REQUEST="true"))
        self.assertIn("se resolverá", resumen)
        self.assertIn("$ 50.000,00", resumen)

        # 3. El Gerente acepta. Después del commit, InfoPonia resuelve el contrato (postcondiciones a a g) y avisa (i a l).
        huella = self.resumen(x.solicitud, "aceptar", "Se cargó menos.").huella
        with self.captureOnCommitCallbacks(execute=True):
            confirmar = g.post(reverse("comercial:solicitud_resolver", args=[x.solicitud.pk]), {"decision": "aceptar", "observaciones": "Se cargó menos.", "huella": huella})
        self.assertEqual(confirmar.status_code, 302)
        contrato = Suministro.objects.get(pk=x.contrato.pk)
        self.assertEqual((contrato.estado_suministro, contrato.fecha_resolucion_suministro, contrato.solicitud_resolucion_id), ("resuelto", HOY, x.solicitud.pk))  # a y D-69 punto 5
        self.assertEqual(Entrega.objects.get(pk=x.entrega_a_realizar.pk).estado_orden, "cancelada")  # f
        self.assertEqual(Cosecha.objects.get(pk=x.reserva_activa.cosecha_id).estado_orden, "cancelada")  # c
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=x.detalle, estado_reserva__in=["activa", "lista_para_entrega"]).count(), 0)  # c y d
        self.assertEqual(StockCosechado.objects.filter(motivo_cosechado="resolucion_del_contrato").count(), 0)  # nada cosechado que pasar a la cámara en este escenario
        self.assertEqual(len(RegistroAuditoria.objects.filter(accion="resolucion_suministro")), 1)  # m
        self.assertTrue(any(m.subject == f"Resolución de tu suministro {x.contrato.codigo}" and "$ 50.000,00" in m.body for m in mail.outbox))  # k
        self.assertEqual(Suministro.objects.get(pk=x.contrato.pk).estado_comprobante, "enviado")

        # 4. Los avisos (l): el Vendedor, el Transportista, el Capataz y el Agrónomo (uno solo, con los envases).
        self.assertEqual(len(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo=f"{x.contrato.codigo} resuelto por incumplimientos")), 1)
        self.assertEqual(len(Notificacion.objects.filter(destinatario=x.transportista, titulo=f"Se canceló la entrega {x.entrega_a_realizar.codigo}")), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.capataz).count(), 1)
        (aviso_agronomo,) = Notificacion.objects.filter(destinatario=self.e.agronomo, titulo__startswith=f"{x.contrato.codigo} resuelto:")
        self.assertIn("Envases que estaban reservados", aviso_agronomo.detalle)

        # 5. La campana del Gerente tiene la alerta «suministro resuelto»; su enlace lleva a la ficha del suministro.
        alerta = Alerta.objects.get(tipo_alerta="comercial_suministro_resuelto")
        self.assertEqual((alerta.estado_alerta, alerta.para_gerente), ("activa", True))
        campana = texto(g.get(reverse("core:campana")))
        self.assertIn(f"{x.contrato.codigo} · resuelto · multa $ 50.000,00", campana)
        self.assertRedirects(g.get(reverse("alertas:ir", args=[alerta.pk])), reverse("comercial:suministro", args=[x.contrato.pk]), fetch_redirect_response=False)

        # 6. La ficha del Gerente: el aviso con la solicitud y la multa, «Dar por atendida» con su texto, y la lista con la marca «Resolución sin atender».
        ficha = texto(g.get(reverse("comercial:suministro", args=[x.contrato.pk])))
        for esperado in (f"Resuelto por incumplimientos el {HOY:%d/%m/%Y}", "1 de 0", x.solicitud.codigo, "$ 50.000,00", "Las entregas concretadas se siguen cobrando", "Dar por atendida",
                         "Usalo cuando hayas pagado la multa y avisado al cliente"):
            self.assertIn(esperado, ficha)
        self.assertNotIn("Modificar suministro", ficha)
        self.assertNotIn("Rescindir suministro", ficha)
        self.assertIn("Resolución sin atender", texto(g.get(reverse("comercial:contratos"), {"tipo": "suministro"})))

        # 7. Extensión 2a de COM-ANL-SRV: no se puede anular la aceptación que resolvió el contrato (la página dice por qué; un POST a mano tampoco la anula).
        anular = reverse("comercial:solicitud_anular", args=[x.solicitud.pk])
        self.assertIn("esta aceptación resolvió el contrato", texto(g.get(anular)))
        g.post(anular, {"motivo": "Me equivoqué.", "huella": ""})
        self.assertEqual(Suministro.objects.get(pk=x.contrato.pk).cantidad_incumplimientos, 1)

        # 8. El Vendedor (en lectura): ve el aviso de resolución y la lista sin la marca, pero ningún botón de escritura; un POST a mano a «Dar por atendida» es 403 (D-30).
        g.force_login(self.e.vendedor)
        ficha_del_vendedor = texto(g.get(reverse("comercial:suministro", args=[x.contrato.pk])))
        self.assertIn("Resuelto por incumplimientos el", ficha_del_vendedor)
        self.assertNotIn("Dar por atendida", ficha_del_vendedor)
        self.assertNotIn("Resolución sin atender", texto(g.get(reverse("comercial:contratos"), {"tipo": "suministro"})))
        self.assertEqual(g.post(reverse("comercial:suministro_dar_por_atendida", args=[x.contrato.pk])).status_code, 403)

        # 9. Un Transportista no entra a la ficha ni a «Dar por atendida» (sin permiso).
        g.force_login(x.transportista)
        self.assertEqual(g.get(reverse("comercial:suministro", args=[x.contrato.pk])).status_code, 403)
        self.assertEqual(g.post(reverse("comercial:suministro_dar_por_atendida", args=[x.contrato.pk])).status_code, 403)

        # 10. «Dar por atendida»: la alerta se resuelve, la marca de la lista desaparece y la ficha ya no tiene el botón; una segunda vez no es un error.
        g.force_login(self.gerente)
        atendida = g.post(reverse("comercial:suministro_dar_por_atendida", args=[x.contrato.pk]))
        self.assertRedirects(atendida, reverse("comercial:suministro", args=[x.contrato.pk]), fetch_redirect_response=False)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertNotIn("Dar por atendida", texto(g.get(atendida.url)))
        self.assertNotIn("Resolución sin atender", texto(g.get(reverse("comercial:contratos"), {"tipo": "suministro"})))
        self.assertEqual(g.post(reverse("comercial:suministro_dar_por_atendida", args=[x.contrato.pk])).status_code, 302)
        self.assertEqual(len(RegistroAuditoria.objects.filter(accion="atencion_suministro_resuelto")), 1)
        self.assertEqual(AlertaComercial.objects.filter(suministro=x.contrato).count(), 1)

        # 11. Extensión 2a de COM-RSV-SUM: el paso diario no vuelve a tocar un contrato resuelto.
        antes = RegistroAuditoria.objects.count()
        call_command("proceso_diario", solo="resolver_suministros", stdout=StringIO())
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

        # 12. El disparo perdido (disparador 2, situación 6): otro contrato quedó «vigente» con más incumplimientos que los tolerados; el paso 33 lo resuelve y, corrido otra vez, no hace nada.
        y = self.armar(tolerados=0)
        ReservaStock.objects.filter(detalle_suministro=y.detalle).update(estado_reserva="entregada")
        reserva_activa = reserva_de_periodo(y.detalle, HOY + timedelta(days=7), [(self.lote, 10)])
        Suministro.objects.filter(pk=y.contrato.pk).update(cantidad_incumplimientos=1)
        _aceptar(y.solicitud, monto="0.00", descontado=None, reintegrado="0.00", medio=None, gerente=self.gerente, observaciones="", contar=False)  # la solicitud aceptada cuyo disparo se perdió
        with self.captureOnCommitCallbacks(execute=True):
            salida = StringIO()
            call_command("proceso_diario", solo="resolver_suministros", stdout=salida)
        self.assertEqual(Suministro.objects.get(pk=y.contrato.pk).estado_suministro, "resuelto")
        self.assertEqual(Cosecha.objects.get(pk=reserva_activa.cosecha_id).estado_orden, "cancelada")
        self.assertEqual(Suministro.objects.get(pk=y.contrato.pk).solicitud_resolucion_id, y.solicitud.pk)
        antes = RegistroAuditoria.objects.count()
        call_command("proceso_diario", solo="resolver_suministros", stdout=StringIO())
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
