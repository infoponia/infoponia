# Pruebas de COM-ASG-TRP · Asignar Transportista a Entrega (COM-05b): `ComAsgTrpServicioTests` (las reglas, las postcondiciones a a f y las extensiones 1a, 1b, 3a, 4a, 4b, 5a, 8a, 8b y 9a de
# `datos_de_asignacion`, `resumen_de_asignacion` y `asignar_transportista`) y, abajo, `ComAsgTrpVistaTests` (las pantallas). Cada prueba verifica al final los invariantes de las
# reservas y de las entregas. Fuente: docs/casos_de_uso/comercial/entregas.md («COM-ASG-TRP», «Cómo se aplica en la ronda «Comercial 1»: COM-ASG-TRP»), D-66 y D-67 punto 3.

import re
from datetime import timedelta
from decimal import Decimal
from html import unescape
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega
from comercial.servicios import entregas
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    entrega,
    escenario_comercial,
    reserva_lista,
    segundo_invernadero,
    transportista_con_vehiculo,
    vehiculo_en_ruta,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from core import correo
from core.models import Notificacion, RegistroAuditoria, Usuario
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import ConfiguracionOperativa, TransportistaInvernadero
from maestros.tests.fabricas import crear_agronomo, crear_vendedor
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
TIPO = entregas.TIPO_SIN_TRANSPORTISTA


def codigos(error):
    """Los códigos de un `ValidationError` con o sin `error_dict`."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, su Gerente, un lote de 5000 y dos transportistas con vehículo de 800 kg."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.gerente = crear_gerente()
        cls.t1 = transportista_con_vehiculo(cls.e.invernadero, "800")
        cls.t2 = transportista_con_vehiculo(cls.e.invernadero, "800")

    def setUp(self):
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)

    def nueva(self, *, transportista=None, dias=3, cantidad=100, fecha=None, **opciones):
        """Una entrega «a realizar» de una venta con envío (sin avisos ni alerta). Devuelve `(venta, reserva, entrega)`."""
        venta = compra_venta(self.e, dias=dias, **opciones)
        det = detalle(venta, self.e.variedad, cantidad)
        r = reserva_lista(det, self.lote, cantidad)
        return venta, r, entrega(venta, [r], transportista=transportista, fecha=fecha)

    def sin_transportista_con_alerta(self, **opciones):
        """Una entrega sin transportista con su alerta «entrega sin transportista» activa (como la deja COM-PNF-ENT)."""
        venta, r, e = self.nueva(**opciones)
        alerta = entregas._alerta_sin_transportista(e, venta, "capacidad de carga insuficiente")
        return venta, r, e, alerta

    def avisos(self, cuenta):
        return list(Notificacion.objects.filter(destinatario=cuenta).order_by("pk"))

    def titulos(self, cuenta):
        return [a.titulo for a in self.avisos(cuenta)]

    def asignar(self, actor, e, transportista, *, huella=None):
        """Abre la asignación y confirma (los dos pasos, como la pantalla)."""
        datos = entregas.datos_de_asignacion(actor, e.pk)
        return entregas.asignar_transportista(actor, e.pk, getattr(transportista, "pk", transportista), huella or datos.huella)


class ComAsgTrpServicioTests(Base):
    # ---- flujo principal y postcondiciones ----

    def test_flujo_principal_asigna_el_transportista_elegido_a_una_entrega_sin_transportista(self):
        """Pasos 1 a 10: el Vendedor abre la entrega sin transportista, elige un candidato y confirma; la entrega queda con ese transportista y la misma fecha."""
        _, _, e = self.nueva()
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        self.assertEqual({c.transportista.pk for c in datos.candidatos if c.motivo is None}, {self.t1.pk, self.t2.pk})
        resultado = self.asignar(self.e.vendedor, e, self.t1)
        actual = Entrega.objects.get(pk=e.pk)
        self.assertEqual((resultado.pk, actual.transportista_id, actual.fecha_programada_orden), (e.pk, self.t1.pk, e.fecha_programada_orden))

    def test_post_a_la_entrega_queda_asignada_al_transportista_elegido(self):
        """Postcondición a."""
        _, _, e = self.nueva()
        self.asignar(self.e.vendedor, e, self.t2)
        self.assertEqual(Entrega.objects.get(pk=e.pk).transportista_id, self.t2.pk)

    def test_post_b_con_la_fecha_vencida_pasa_a_hoy_con_el_aviso_de_retraso_y_el_correo_al_cliente(self):
        """Postcondición b: la fecha programada que ya pasó pasa a la actual; el Vendedor recibe «Entrega con retraso» y el cliente el correo con la nueva fecha (`pendiente_envio` hasta que sale)."""
        _, _, e = self.nueva(fecha=HOY - timedelta(days=2))
        with self.captureOnCommitCallbacks(execute=False) as retrasados:
            self.asignar(self.e.vendedor, e, self.t1)
        actual = Entrega.objects.get(pk=e.pk)
        self.assertEqual((actual.fecha_programada_orden, actual.estado_aviso_cliente), (HOY, "pendiente_envio"))
        self.assertEqual(len(retrasados), 1)
        self.assertIn(f"Entrega con retraso: {e.codigo}", self.titulos(self.e.vendedor))
        self.assertIn(f"La fecha prometida era el {HOY - timedelta(days=2):%d/%m} y sale el {HOY:%d/%m}.", [a.detalle for a in self.avisos(self.e.vendedor)])

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_9a_el_correo_sale_despues_de_confirmar_y_si_falla_queda_pendiente_de_envio(self):
        """Extensión 9a y D-66 punto 12: el correo del cambio de fecha va en un `on_commit`; enviado, el aviso queda «enviado»; si falla, «pendiente de envío» (lo reintenta el paso 50)."""
        _, _, e = self.nueva(fecha=HOY - timedelta(days=1))
        with self.captureOnCommitCallbacks(execute=True):
            self.asignar(self.e.vendedor, e, self.t1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, f"Cambió la fecha de tu entrega {e.codigo}: ahora es el {HOY:%d/%m}")
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_aviso_cliente, "enviado")
        _, _, otra = self.nueva(fecha=HOY - timedelta(days=1))
        with mock.patch.object(correo, "enviar_correo", return_value=False), self.captureOnCommitCallbacks(execute=True):
            self.asignar(self.e.vendedor, otra, self.t2)
        actual = Entrega.objects.get(pk=otra.pk)
        self.assertEqual((actual.transportista_id, actual.estado_aviso_cliente), (self.t2.pk, "pendiente_envio"))

    def test_post_c_la_alerta_de_entrega_sin_transportista_queda_resuelta(self):
        """Postcondición c: se resuelve (queda en el historial) con la fecha actual como fecha de resolución."""
        _, _, e, alerta = self.sin_transportista_con_alerta()
        self.asignar(self.e.vendedor, e, self.t1)
        alerta.refresh_from_db()
        self.assertEqual((alerta.estado_alerta, timezone.localtime(alerta.fecha_resolucion).date()), ("resuelta", HOY))
        self.assertTrue(AlertaComercial.objects.filter(alerta=alerta, entrega=e).exists())

    def test_post_d_avisa_al_transportista_nuevo_y_al_anterior(self):
        """Postcondición d y extensión 5a: el nuevo recibe «Nueva entrega para el dd/mm»; el anterior, «Ya no tenés la entrega OT-…» con quién se la asignó y a qué cliente."""
        venta, _, e = self.nueva(transportista=self.t1)
        self.asignar(self.e.vendedor, e, self.t2)
        self.assertEqual(self.titulos(self.t2), [f"Nueva entrega para el {e.fecha_programada_orden:%d/%m}"])
        anterior = self.avisos(self.t1)
        self.assertEqual([a.titulo for a in anterior], [f"Ya no tenés la entrega {e.codigo}"])
        self.assertEqual(anterior[0].detalle, f"{self.e.vendedor.get_full_name()} se la asignó a otro transportista. Era para el {e.fecha_programada_orden:%d/%m} a {venta.cliente.nombre_visible}.")

    def test_ext_5a_el_transportista_anterior_inactivo_no_recibe_aviso(self):
        """Extensión 5a: el aviso al anterior solo si su cuenta está activa."""
        _, _, e = self.nueva(transportista=self.t1)
        Usuario.objects.filter(pk=self.t1.pk).update(is_active=False)
        self.asignar(self.e.vendedor, e, self.t2)
        self.assertEqual(self.avisos(self.t1), [])
        self.assertEqual(Entrega.objects.get(pk=e.pk).transportista_id, self.t2.pk)

    def test_post_e_y_ext_1a_si_asigna_el_gerente_se_avisa_al_vendedor_y_si_asigna_el_vendedor_no(self):
        """Postcondición e y extensión 1a: el Gerente asigna y el Vendedor del contrato recibe «OT-… ya tiene transportista»; si asigna el propio Vendedor, no se avisa a sí mismo."""
        _, _, e = self.nueva()
        self.asignar(self.gerente, e, self.t1)
        avisos = self.avisos(self.e.vendedor)
        self.assertEqual([a.titulo for a in avisos], [f"{e.codigo} ya tiene transportista"])
        self.assertEqual(avisos[0].detalle, f"El Gerente se la asignó a {self.t1.get_full_name()} para el {e.fecha_programada_orden:%d/%m}.")
        _, _, otra = self.nueva()
        self.asignar(self.e.vendedor, otra, self.t2)
        self.assertEqual(self.titulos(self.e.vendedor), [f"{e.codigo} ya tiene transportista"])

    def test_ext_1a_el_vendedor_inactivo_no_recibe_aviso_y_la_asignacion_es_del_gerente(self):
        """Extensión 1a y regla «Quién asigna»: las entregas de un contrato cuyo Vendedor está inactivo las asigna el Gerente, y el inactivo no recibe nada."""
        _, _, e = self.nueva()
        Usuario.objects.filter(pk=self.e.vendedor.pk).update(is_active=False)
        self.asignar(self.gerente, e, self.t1)
        self.assertEqual(self.avisos(self.e.vendedor), [])
        with self.assertRaises(PermissionDenied):
            entregas.datos_de_asignacion(self.e.vendedor, e.pk)

    def test_post_f_registra_la_auditoria_con_el_actor_el_anterior_el_nuevo_y_el_cambio_de_fecha(self):
        """Postcondición f y D-36: un registro `asignacion_transportista` con el usuario y su rol como origen; cambios: transportista antes → después y, si cambió, la fecha; datos: alertas resueltas."""
        _, _, e, alerta = self.sin_transportista_con_alerta(fecha=HOY - timedelta(days=1))
        antes = RegistroAuditoria.objects.filter(accion="asignacion_transportista").count()
        self.asignar(self.e.vendedor, e, self.t1)
        registros = RegistroAuditoria.objects.filter(accion="asignacion_transportista")
        self.assertEqual(registros.count(), antes + 1)
        registro = registros.latest("pk")
        self.assertEqual(registro.usuario_id, self.e.vendedor.pk)
        cambios = registro.detalle["cambios"]
        self.assertIsNone(cambios["transportista"]["antes"])
        self.assertEqual(cambios["transportista"]["despues"]["id"], self.t1.pk)
        self.assertEqual(cambios["fecha_programada_orden"], {"antes": f"{HOY - timedelta(days=1):%d/%m/%Y}", "despues": f"{HOY:%d/%m/%Y}"})
        self.assertEqual([a["id"] for a in registro.detalle["datos"]["alertas_resueltas"]], [alerta.pk])

    # ---- reglas ----

    def test_regla_quien_asigna_el_vendedor_del_contrato_o_el_gerente(self):
        """Paso 1 y extensión 1a (regla 12 de 8.12): el Vendedor de otro contrato, el Agrónomo y una cuenta inactiva reciben `PermissionDenied`; el Gerente puede."""
        _, _, e = self.nueva()
        ajeno = crear_vendedor(email="ajeno@infoponia.com")
        agronomo = crear_agronomo(email="otro.agronomo@infoponia.com")
        for actor in (ajeno, agronomo, self.t1):
            with self.assertRaises(PermissionDenied):
                entregas.datos_de_asignacion(actor, e.pk)
            with self.assertRaises(PermissionDenied):
                entregas.asignar_transportista(actor, e.pk, self.t1.pk, "x")
        datos = entregas.datos_de_asignacion(self.gerente, e.pk)
        self.assertIsNone(datos.bloqueo)

    def test_regla_una_entrega_inexistente_es_un_404(self):
        """Un id que no existe: `Http404` (no `PermissionDenied`)."""
        from django.http import Http404

        with self.assertRaises(Http404):
            entregas.datos_de_asignacion(self.gerente, 999999)

    def test_regla_un_retiro_no_se_asigna(self):
        """Regla «Entrega asignable»: los retiros no tienen transportista; el servicio rechaza con `entrega_sin_envio`."""
        venta = compra_venta(self.e, dias=3, modalidad="retiro")
        det = detalle(venta, self.e.variedad, 50)
        e = entrega(venta, [reserva_lista(det, self.lote, 50)])
        with self.assertRaises(ValidationError) as c:
            entregas.asignar_transportista(self.gerente, e.pk, self.t1.pk, "x")
        self.assertEqual(codigos(c.exception), ["entrega_sin_envio"])
        self.assertIsNotNone(entregas.datos_de_asignacion(self.gerente, e.pk).bloqueo)

    def test_regla_una_entrega_concretada_o_cancelada_no_se_asigna(self):
        """Regla «Entrega asignable»: solo «a realizar»; una concretada o cancelada, `entrega_no_a_realizar`."""
        for estado in ("concretada", "cancelada"):
            venta = compra_venta(self.e, dias=3)
            det = detalle(venta, self.e.variedad, 10)
            e = entrega(venta, [reserva_lista(det, self.lote, 10)], estado=estado)
            with self.assertRaises(ValidationError) as c:
                entregas.asignar_transportista(self.gerente, e.pk, self.t1.pk, "x")
            self.assertEqual(codigos(c.exception), ["entrega_no_a_realizar"], estado)
            self.assertIsNotNone(entregas.datos_de_asignacion(self.gerente, e.pk).bloqueo, estado)

    def test_ext_3a_una_entrega_en_curso_no_se_reasigna(self):
        """Extensión 3a: con el vehículo de su transportista en ruta y fecha de hoy o anterior, la pantalla no ofrece candidatos y el servicio rechaza con `entrega_en_curso`."""
        _, _, e = self.nueva(transportista=self.t1, dias=0)
        vehiculo_en_ruta(self.t1)
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        self.assertTrue(datos.en_curso)
        self.assertIn(f"{self.t1.get_full_name()} ya inició la ruta", datos.bloqueo)
        self.assertEqual(datos.candidatos, [])
        with self.assertRaises(ValidationError) as c:
            entregas.asignar_transportista(self.e.vendedor, e.pk, self.t2.pk, datos.huella)
        self.assertEqual(codigos(c.exception), ["entrega_en_curso"])
        self.assertEqual(Entrega.objects.get(pk=e.pk).transportista_id, self.t1.pk)

    def test_regla_los_candidatos_no_incluyen_al_transportista_actual_y_cada_uno_trae_su_motivo(self):
        """Regla «Candidatos»: los de `candidatos_para` para la fecha sin el actual, todos los del invernadero con su motivo; solo cumplen los de `motivo=None`."""
        chico = transportista_con_vehiculo(self.e.invernadero, "1")
        _, _, e = self.nueva(transportista=self.t1)
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        por_id = {c.transportista.pk: c.motivo for c in datos.candidatos}
        self.assertEqual(por_id, {self.t2.pk: None, chico.pk: "Capacidad de carga insuficiente"})
        self.assertEqual(datos.transportista_actual.pk, self.t1.pk)

    def test_ext_4b_ningun_candidato_cumple_dice_el_motivo_de_cada_uno_y_a_quien_acudir(self):
        """Extensión 4b: sin candidatos que cumplan, el aviso lista el motivo de cada transportista y, para el Gerente, que puede dar de alta una flota o ajustar la configuración; para el Vendedor, que avise al Gerente."""
        TransportistaInvernadero.objects.filter(transportista=self.t2).delete()
        _, _, e = self.nueva()
        Usuario.objects.filter(pk=self.t1.pk).update(is_active=False)
        for actor, frase in ((self.gerente, "Podés dar de alta un transportista en la ficha del invernadero («Logística»)"), (self.e.vendedor, "Avisale al Gerente")):
            datos = entregas.datos_de_asignacion(actor, e.pk)
            self.assertEqual([c.motivo for c in datos.candidatos], ["Inactivo"])
            self.assertIn(frase, datos.aviso_sin_candidatos)
            with self.assertRaises(ValidationError) as c:
                entregas.asignar_transportista(actor, e.pk, self.t1.pk, datos.huella)
            self.assertEqual(codigos(c.exception), ["transportista_no_cumple"])
        self.assertIsNone(Entrega.objects.get(pk=e.pk).transportista_id)

    def test_ext_4b_un_invernadero_sin_transportistas_lo_dice(self):
        """Extensión 4b: «El invernadero de origen no tiene transportistas.»"""
        TransportistaInvernadero.objects.all().delete()
        _, _, e = self.nueva()
        datos = entregas.datos_de_asignacion(self.gerente, e.pk)
        self.assertEqual((datos.candidatos, datos.aviso_sin_candidatos), ([], "El invernadero de origen no tiene transportistas."))

    def test_ext_4a_con_la_fecha_vencida_los_candidatos_son_para_hoy_y_avisa_la_reprogramacion(self):
        """Extensión 4a: la fecha de búsqueda es hoy y `reprograma` es verdadero; la pantalla dice que se reprogramará para hoy y se avisará el retraso."""
        _, _, e = self.nueva(fecha=HOY - timedelta(days=3))
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        self.assertEqual((datos.reprograma, datos.fecha_de_busqueda), (True, HOY))
        _, _, futura = self.nueva(dias=5)
        datos = entregas.datos_de_asignacion(self.e.vendedor, futura.pk)
        self.assertEqual((datos.reprograma, datos.fecha_de_busqueda), (False, futura.fecha_programada_orden))

    def test_regla_los_candidatos_se_evaluan_para_la_fecha_de_busqueda_con_la_carga_del_dia(self):
        """Regla «Candidatos»: la capacidad cuenta las entregas no canceladas del transportista ese día más la nueva (reglas 5 a 7 de 8.12)."""
        _, _, e = self.nueva()
        peso = entregas.peso_de_entregas([e.pk])[e.pk]
        justo = transportista_con_vehiculo(self.e.invernadero, str(peso * 2))
        self.nueva(transportista=justo, fecha=e.fecha_programada_orden)  # el vehículo ya lleva una entrega igual: entra justo la segunda
        self.nueva(transportista=justo, fecha=e.fecha_programada_orden)
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        self.assertEqual({c.transportista.pk: c.motivo for c in datos.candidatos}[justo.pk], "Capacidad de carga insuficiente")

    def test_regla_el_contenido_de_la_entrega_no_cambia(self):
        """Regla «Contenido sin cambios»: las líneas, las reservas y los envases quedan iguales."""
        _, r, e = self.nueva()
        antes = (list(e.lineas.values_list("pk", "precio_unitario")), list(r.lineas.values_list("cantidad_reservada", flat=True)), r.estado_reserva)
        self.asignar(self.e.vendedor, e, self.t1)
        r.refresh_from_db()
        self.assertEqual((list(e.lineas.values_list("pk", "precio_unitario")), list(r.lineas.values_list("cantidad_reservada", flat=True)), r.estado_reserva), antes)

    def test_regla_sin_quitar_el_transportista_es_obligatorio_y_tiene_que_ser_un_candidato(self):
        """Regla «Sin quitar el transportista» y decisión D: sin transportista, `transportista_obligatorio`; el actual o uno de otro invernadero, `transportista_no_cumple`."""
        _, _, e = self.nueva(transportista=self.t1)
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        for valor in (None, ""):
            with self.assertRaises(ValidationError) as c:
                entregas.asignar_transportista(self.e.vendedor, e.pk, valor, datos.huella)
            self.assertEqual(codigos(c.exception), ["transportista_obligatorio"])
        otro = segundo_invernadero(self.e)
        ajeno = transportista_con_vehiculo(otro.invernadero, "800")
        for elegido in (self.t1.pk, ajeno.pk):
            with self.assertRaises(ValidationError) as c:
                entregas.asignar_transportista(self.e.vendedor, e.pk, elegido, datos.huella)
            self.assertEqual(codigos(c.exception), ["transportista_no_cumple"])
        self.assertEqual(Entrega.objects.get(pk=e.pk).transportista_id, self.t1.pk)

    # ---- cómo queda (paso 6) ----

    def test_post_resumen_dice_como_queda_la_carga_las_entregas_las_localidades_y_el_que_la_deja(self):
        """Paso 6 y extensión 5a: la carga del día con la entrega («12,40 + 15,20 = 27,60 de 400,00 kg»), las entregas «N + 1 de M», las localidades y el transportista que la deja."""
        _, _, e = self.nueva(transportista=self.t1)
        _, _, previa = self.nueva(transportista=self.t2, fecha=e.fecha_programada_orden)
        pesos = entregas.peso_de_entregas([e.pk, previa.pk])
        como = entregas.resumen_de_asignacion(self.e.vendedor, e.pk, self.t2.pk)
        maximos = ConfiguracionOperativa.objects.get()
        self.assertEqual((como.peso_del_dia, como.peso_entrega, como.peso_total, como.capacidad), (pesos[previa.pk], pesos[e.pk], pesos[previa.pk] + pesos[e.pk], Decimal("800")))
        self.assertEqual((como.entregas, como.maximo_entregas, como.maximo_localidades), (2, maximos.cant_maxima_entregas_diarias, maximos.cant_max_ciudades_distintas_diarias))
        self.assertEqual((como.fecha, como.deja.pk), (e.fecha_programada_orden, self.t1.pk))

    def test_regla_el_resumen_rechaza_a_quien_no_cumple_y_no_escribe(self):
        """El resumen valida igual que la confirmación y no escribe nada (ni auditoría ni avisos)."""
        _, _, e = self.nueva(transportista=self.t1)
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        with self.assertRaises(ValidationError) as c:
            entregas.resumen_de_asignacion(self.e.vendedor, e.pk, self.t1.pk)
        self.assertEqual(codigos(c.exception), ["transportista_no_cumple"])
        entregas.resumen_de_asignacion(self.e.vendedor, e.pk, self.t2.pk)
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)
        self.assertEqual(Entrega.objects.get(pk=e.pk).transportista_id, self.t1.pk)

    # ---- relectura bajo bloqueo (8a y 8b) ----

    def test_ext_8a_si_otra_operacion_la_asigno_la_huella_no_coincide_y_no_se_registra_nada(self):
        """Extensión 8a: la entrega cambió mientras se miraba (le asignaron otro transportista): `entrega_cambio`, sin registros ni avisos."""
        _, _, e = self.nueva()
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        Entrega.objects.filter(pk=e.pk).update(transportista=self.t2)
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        with self.assertRaises(ValidationError) as c:
            entregas.asignar_transportista(self.e.vendedor, e.pk, self.t1.pk, datos.huella)
        self.assertEqual(codigos(c.exception), ["entrega_cambio"])
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)

    def test_ext_8a_cada_causa_la_entrega_cambio_de_fecha_se_cancelo_o_salio_en_ruta(self):
        """Extensión 8a: cambió la fecha programada, se canceló o ya está en curso: nada se registra."""
        for cambio in ("fecha", "cancelada", "en_curso"):
            _, _, e = self.nueva(transportista=self.t1, dias=0)
            datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
            if cambio == "fecha":
                Entrega.objects.filter(pk=e.pk).update(fecha_programada_orden=HOY + timedelta(days=1))
            elif cambio == "cancelada":
                Entrega.objects.filter(pk=e.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")
            else:
                vehiculo_en_ruta(self.t1)
            with self.assertRaises(ValidationError) as c:
                entregas.asignar_transportista(self.e.vendedor, e.pk, self.t2.pk, datos.huella)
            self.assertIn(codigos(c.exception)[0], ("entrega_cambio", "entrega_no_a_realizar", "entrega_en_curso"), cambio)
            self.assertEqual(Entrega.objects.get(pk=e.pk).transportista_id, self.t1.pk, cambio)
            Entrega.objects.filter(pk=e.pk).update(transportista=None)
            if cambio == "en_curso":
                from comercial.models import Vehiculo

                Vehiculo.objects.filter(transportista=self.t1).update(en_ruta=False, fecha_inicio_ruta=None)

    def test_ext_8b_si_el_transportista_se_lleno_mientras_tanto_vuelve_a_los_candidatos(self):
        """Extensión 8b: otra planificación le asignó entregas y ya no cumple: `transportista_no_cumple` con el motivo y no se registra nada."""
        _, _, e = self.nueva()
        peso = entregas.peso_de_entregas([e.pk])[e.pk]
        chico = transportista_con_vehiculo(self.e.invernadero, str(peso))
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        self.assertIsNone({c.transportista.pk: c.motivo for c in datos.candidatos}[chico.pk])
        self.nueva(transportista=chico, fecha=e.fecha_programada_orden)
        with self.assertRaises(ValidationError) as c:
            entregas.asignar_transportista(self.e.vendedor, e.pk, chico.pk, datos.huella)
        self.assertEqual(codigos(c.exception), ["transportista_no_cumple"])
        self.assertEqual(c.exception.error_dict["transportista"][0].params["motivo"], "Capacidad de carga insuficiente")
        self.assertIsNone(Entrega.objects.get(pk=e.pk).transportista_id)

    def test_ext_8b_cada_causa_se_dio_de_baja_se_traslado_o_inicio_su_ruta(self):
        """Extensión 8b: el transportista elegido se dio de baja, lo trasladaron a otro invernadero (MAE-05) o inició su ruta para hoy."""
        otro = segundo_invernadero(self.e)
        for causa in ("baja", "traslado", "ruta"):
            tr = transportista_con_vehiculo(self.e.invernadero, "800")
            _, _, e = self.nueva(dias=0)
            datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
            if causa == "baja":
                Usuario.objects.filter(pk=tr.pk).update(is_active=False)
            elif causa == "traslado":
                TransportistaInvernadero.objects.filter(transportista=tr).update(invernadero=otro.invernadero)
            else:
                vehiculo_en_ruta(tr)
            with self.assertRaises(ValidationError) as c:
                entregas.asignar_transportista(self.e.vendedor, e.pk, tr.pk, datos.huella)
            self.assertEqual(codigos(c.exception), ["transportista_no_cumple"], causa)
            self.assertIsNone(Entrega.objects.get(pk=e.pk).transportista_id, causa)

    def test_ext_8b_si_hoy_cambia_entre_la_lectura_y_la_confirmacion_se_recalcula_la_fecha_de_busqueda(self):
        """Extensión 4a tardía: la entrega vence entre la lectura y la confirmación; la fecha pasa a la nueva «hoy» si el transportista cumple, y si ya no cumple para esa fecha es 8b."""
        _, _, e = self.nueva(dias=1)
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        manana = HOY + timedelta(days=2)
        with mock.patch.object(entregas.stock, "hoy", return_value=manana):
            self.assertEqual(entregas.asignar_transportista(self.e.vendedor, e.pk, self.t1.pk, datos.huella).fecha_programada_orden, manana)
        _, _, f = self.nueva(dias=1)
        datos = entregas.datos_de_asignacion(self.e.vendedor, f.pk)
        peso = entregas.peso_de_entregas([f.pk])[f.pk]
        justo = transportista_con_vehiculo(self.e.invernadero, str(peso))
        self.nueva(transportista=justo, fecha=manana)
        with mock.patch.object(entregas.stock, "hoy", return_value=manana), self.assertRaises(ValidationError) as c:
            entregas.asignar_transportista(self.e.vendedor, f.pk, justo.pk, datos.huella)
        self.assertEqual(codigos(c.exception), ["transportista_no_cumple"])
        self.assertIsNone(Entrega.objects.get(pk=f.pk).transportista_id)

    def test_ext_8b_un_invernadero_dado_de_baja_rechaza_la_asignacion(self):
        """El invernadero de origen se bloquea activo (`bloquear_invernadero_activo`): si se dio de baja, no se asigna nada."""
        from maestros.models import Invernadero

        _, _, e = self.nueva()
        datos = entregas.datos_de_asignacion(self.e.vendedor, e.pk)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        with self.assertRaises(ValidationError):
            entregas.asignar_transportista(self.gerente, e.pk, self.t1.pk, datos.huella)
        self.assertIsNone(Entrega.objects.get(pk=e.pk).transportista_id)

    # ---- rendimiento ----

    def test_regla_los_datos_de_asignacion_no_hacen_consultas_por_transportista(self):
        """Requisito «no más de 2 segundos»: las consultas de `datos_de_asignacion` son las mismas con 1 que con 5 transportistas."""
        _, _, e = self.nueva()
        TransportistaInvernadero.objects.filter(transportista=self.t2).delete()
        entregas.datos_de_asignacion(self.gerente, e.pk)  # calienta cachés (configuración, etc.)
        with CaptureQueriesContext(connection) as con_uno:
            entregas.datos_de_asignacion(self.gerente, e.pk)
        for _ in range(4):
            transportista_con_vehiculo(self.e.invernadero, "800")
        with CaptureQueriesContext(connection) as con_cinco:
            entregas.datos_de_asignacion(self.gerente, e.pk)
        self.assertEqual(len(con_cinco), len(con_uno))


# ---- las pantallas (COM-ASG-TRP, «Pantallas» y «Pruebas»: `ComAsgTrpVistaTests`) ----

HTMX = {"HTTP_HX_REQUEST": "true"}


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class ComAsgTrpVistaTests(Base):
    def ir(self, usuario, e, metodo="get", datos=None, **extra):
        self.client.force_login(usuario)
        url = reverse("comercial:entrega_asignar", args=[e.pk])
        return getattr(self.client, metodo)(url, datos or {}, **extra)

    def calcular(self, usuario, e, datos, **extra):
        self.client.force_login(usuario)
        return self.client.post(reverse("comercial:entrega_asignar_calcular", args=[e.pk]), datos, **extra)

    def mensajes(self, respuesta):
        return [m.message for m in respuesta.context["messages"]] if respuesta.context else []

    # ---- permisos ----

    def test_regla_permisos_el_gerente_y_el_vendedor_del_contrato_entran_y_los_demas_reciben_403(self):
        """SEG-13 y D-28: el Vendedor ve las entregas de sus contratos y el Gerente todas; el Vendedor de otro contrato, el Agrónomo y el Capataz reciben 403 con mensaje; un id inexistente, 404."""
        _, _, e = self.nueva()
        self.assertEqual(self.ir(self.gerente, e).status_code, 200)
        self.assertEqual(self.ir(self.e.vendedor, e).status_code, 200)
        for ajeno in (crear_vendedor(email="ajeno@infoponia.com"), self.e.agronomo, self.e.capataz):
            self.assertEqual(self.ir(ajeno, e).status_code, 403, ajeno.rol)
            self.assertEqual(self.ir(ajeno, e, "post", {"transportista": self.t1.pk, "huella": "x"}).status_code, 403, ajeno.rol)
            self.assertEqual(self.calcular(ajeno, e, {"transportista": self.t1.pk}).status_code, 403, ajeno.rol)
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("comercial:entrega_asignar", args=[999999])).status_code, 404)

    # ---- la pantalla ----

    def test_flujo_principal_la_pantalla_muestra_la_entrega_los_candidatos_y_el_texto_explicativo(self):
        """Pasos 2 a 4: el texto explicativo, el punto de partida, el destino, la fecha, el peso y los candidatos (los que no cumplen, deshabilitados con su motivo)."""
        chico = transportista_con_vehiculo(self.e.invernadero, "1")
        venta, _, e = self.nueva()
        html = texto(self.ir(self.e.vendedor, e))
        for esperado in (
            f"Asignar transportista · {e.codigo}",
            "Elegí quién lleva la entrega. Solo se pueden elegir los transportistas del invernadero de origen que pueden llevarla ese día: el resto muestra por qué no.",
            str(self.e.invernadero), "Sin asignar", self.t1.get_full_name(), self.t2.get_full_name(), "Disponible", "Capacidad de carga insuficiente", "Asignar transportista",
        ):
            self.assertIn(esperado, html)
        self.assertRegex(html, rf'<input type="radio" name="transportista" id="t-{chico.pk}" value="{chico.pk}" disabled')
        self.assertNotRegex(html, rf'id="t-{self.t1.pk}" value="{self.t1.pk}" disabled')

    def test_ext_5a_con_transportista_el_titulo_es_cambiar_y_no_ofrece_al_actual(self):
        """Extensión 5a: «Cambiar transportista · OT-…» y el actual no figura entre los candidatos."""
        _, _, e = self.nueva(transportista=self.t1)
        html = texto(self.ir(self.e.vendedor, e))
        self.assertIn(f"Cambiar transportista · {e.codigo}", html)
        self.assertNotIn(f'value="{self.t1.pk}"', html)
        self.assertIn(f'value="{self.t2.pk}"', html)

    def test_ext_3a_una_entrega_en_curso_dice_que_no_se_reasigna_y_no_ofrece_el_formulario(self):
        """Extensión 3a: el aviso del prototipo, sin candidatos ni botón de asignar y con «Ver la lista de entregas»."""
        _, _, e = self.nueva(transportista=self.t1, dias=0)
        vehiculo_en_ruta(self.t1)
        html = texto(self.ir(self.e.vendedor, e))
        self.assertIn(f"{self.t1.get_full_name()} ya inició la ruta: el producto está cargado en su vehículo y la entrega no se puede reasignar.", html)
        self.assertIn("Ver la lista de entregas", html)
        self.assertNotIn('name="transportista"', html)
        self.assertNotIn("Asignar transportista</button>", html)

    def test_ext_4a_con_la_fecha_vencida_avisa_que_se_reprograma_para_hoy(self):
        """Extensión 4a: «La fecha ya pasó: la entrega se reprogramará para hoy, dd/mm. Se avisará el retraso al cliente y al Vendedor.» y los candidatos para hoy."""
        _, _, e = self.nueva(fecha=HOY - timedelta(days=2))
        html = texto(self.ir(self.e.vendedor, e))
        self.assertIn(f"La fecha ya pasó: la entrega se reprogramará para hoy, {HOY:%d/%m}. Se avisará el retraso al cliente y al Vendedor.", html)
        self.assertIn(f"Transportistas candidatos para el {HOY:%d/%m/%Y}", html)

    def test_ext_4b_sin_candidatos_el_boton_queda_deshabilitado_y_el_aviso_depende_del_rol(self):
        """Extensión 4b: el motivo de cada uno; el Gerente, que puede dar de alta una flota o ajustar la configuración; el Vendedor, que avise al Gerente. «Asignar transportista» deshabilitado."""
        Usuario.objects.filter(pk__in=[self.t1.pk, self.t2.pk]).update(is_active=False)
        _, _, e = self.nueva()
        gerente = texto(self.ir(self.gerente, e))
        self.assertIn("Podés dar de alta un transportista en la ficha del invernadero («Logística»), un vehículo, o ajustar los límites en «Configuración».", gerente)
        self.assertRegex(gerente, r'<button class="btn btn-primary" type="submit"[^>]*disabled')
        self.assertIn("Avisale al Gerente: puede sumar un transportista o un vehículo, o ajustar los límites.", texto(self.ir(self.e.vendedor, e)))

    # ---- «Cómo queda» ----

    def test_regla_calcular_con_htmx_devuelve_solo_la_tarjeta_y_no_escribe_nada(self):
        """Paso 6: al elegir, `calcular/` devuelve el fragmento «Cómo queda» (la carga, las entregas, las localidades y la fecha) sin escribir nada."""
        _, _, e = self.nueva(transportista=self.t1)
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        respuesta = self.calcular(self.e.vendedor, e, {"transportista": self.t2.pk}, **HTMX)
        html = texto(respuesta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("<html", html)
        for esperado in ("Cómo queda", self.t2.get_full_name(), "Carga del día", "Entregas del día", "Localidades del día", "Deja la entrega", self.t1.get_full_name(), "recibirá un aviso"):
            self.assertIn(esperado, html)
        self.assertEqual(((RegistroAuditoria.objects.count(), Notificacion.objects.count()), Entrega.objects.get(pk=e.pk).transportista_id), (antes, self.t1.pk))

    def test_regla_sin_javascript_ver_como_queda_devuelve_la_pagina_completa_con_la_tarjeta(self):
        """Respaldo sin JavaScript: «Ver cómo queda» manda el formulario a `calcular/` y vuelve la misma página con la tarjeta y el transportista marcado; no escribe."""
        _, _, e = self.nueva()
        html = texto(self.calcular(self.e.vendedor, e, {"transportista": self.t2.pk, "huella": "x"}))
        self.assertIn("<html", html)
        self.assertIn("Cómo queda", html)
        self.assertRegex(html, rf'id="t-{self.t2.pk}" value="{self.t2.pk}" checked')
        self.assertIsNone(Entrega.objects.get(pk=e.pk).transportista_id)

    def test_regla_calcular_con_uno_que_no_cumple_dice_el_motivo(self):
        """El que no cumple no se puede ver «cómo queda»: el error del campo con el motivo."""
        chico = transportista_con_vehiculo(self.e.invernadero, "1")
        _, _, e = self.nueva()
        html = texto(self.calcular(self.e.vendedor, e, {"transportista": chico.pk}, **HTMX))
        self.assertIn("capacidad de carga insuficiente", html)
        self.assertNotIn("Carga del día", html)

    # ---- confirmar ----

    def test_flujo_principal_confirmar_asigna_y_avisa_en_la_lista(self):
        """Pasos 7 a 10: «Asignar transportista» registra y vuelve a la lista con «OT-… asignada a Ana Pérez.»."""
        _, _, e = self.nueva()
        huella = entregas.datos_de_asignacion(self.e.vendedor, e.pk).huella
        respuesta = self.ir(self.e.vendedor, e, "post", {"transportista": self.t1.pk, "huella": huella}, follow=True)
        self.assertRedirects(respuesta, reverse("comercial:entregas"))
        self.assertIn(f"{e.codigo} asignada a {self.t1.get_full_name()}.", self.mensajes(respuesta))
        self.assertEqual(Entrega.objects.get(pk=e.pk).transportista_id, self.t1.pk)

    def test_ext_4a_confirmar_con_la_fecha_vencida_avisa_que_se_reprogramo(self):
        """El aviso breve de 4a: «… Se reprogramó para hoy y se avisó el retraso.»"""
        _, _, e = self.nueva(fecha=HOY - timedelta(days=2))
        huella = entregas.datos_de_asignacion(self.e.vendedor, e.pk).huella
        respuesta = self.ir(self.e.vendedor, e, "post", {"transportista": self.t1.pk, "huella": huella}, follow=True)
        self.assertIn(f"{e.codigo} asignada a {self.t1.get_full_name()}. Se reprogramó para hoy y se avisó el retraso.", self.mensajes(respuesta))

    def test_regla_confirmar_sin_elegir_vuelve_con_el_error_del_campo(self):
        """Sin transportista: el error bajo la tabla («Elegí el transportista…») y la entrega sin cambios."""
        _, _, e = self.nueva()
        huella = entregas.datos_de_asignacion(self.e.vendedor, e.pk).huella
        respuesta = self.ir(self.e.vendedor, e, "post", {"huella": huella})
        self.assertContains(respuesta, "Elegí el transportista que lleva la entrega.")
        self.assertIsNone(Entrega.objects.get(pk=e.pk).transportista_id)

    def test_ext_8a_confirmar_una_entrega_que_cambio_vuelve_a_la_lista_con_el_mensaje(self):
        """Extensión 8a: «La entrega cambió mientras la mirabas…»: se vuelve a la lista (paso 2) sin registrar nada."""
        _, _, e = self.nueva()
        huella = entregas.datos_de_asignacion(self.e.vendedor, e.pk).huella
        Entrega.objects.filter(pk=e.pk).update(transportista=self.t2)
        respuesta = self.ir(self.e.vendedor, e, "post", {"transportista": self.t1.pk, "huella": huella}, follow=True)
        self.assertRedirects(respuesta, reverse("comercial:entregas"))
        self.assertIn("La entrega cambió mientras la mirabas (se asignó, se canceló o salió en ruta). Volvé a la lista.", self.mensajes(respuesta))
        self.assertEqual(Entrega.objects.get(pk=e.pk).transportista_id, self.t2.pk)

    def test_ext_8b_confirmar_con_uno_que_ya_no_cumple_vuelve_al_paso_4_con_el_motivo(self):
        """Extensión 8b: la pantalla vuelve con los candidatos actualizados y el motivo del que ya no cumple."""
        _, _, e = self.nueva(dias=0)
        huella = entregas.datos_de_asignacion(self.e.vendedor, e.pk).huella
        vehiculo_en_ruta(self.t1)
        respuesta = self.ir(self.e.vendedor, e, "post", {"transportista": self.t1.pk, "huella": huella})
        html = texto(respuesta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("en ruta", html)
        self.assertRegex(html, rf'id="t-{self.t1.pk}" value="{self.t1.pk}" disabled')
        self.assertIsNone(Entrega.objects.get(pk=e.pk).transportista_id)

    def test_regla_la_campana_del_gerente_lleva_a_la_asignacion_de_esa_entrega(self):
        """Extensión 1b: la alerta «Entrega sin transportista» abre la pantalla de asignación de esa entrega, sin pasar por la lista."""
        _, _, e, alerta = self.sin_transportista_con_alerta()
        enlace = entregas.enlaces_de_alertas(self.gerente, [alerta])[alerta.pk]
        self.assertEqual(enlace.url, reverse("comercial:entrega_asignar", args=[e.pk]))
        self.assertEqual(enlace.detalle, f"{e.codigo} · {e.fecha_programada_orden:%d/%m} · {e.contrato_entrega.cliente.nombre_visible}")
        self.assertEqual(entregas.enlaces_de_alertas(self.e.vendedor, [alerta]), {})
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(enlace.url), f"Asignar transportista · {e.codigo}")

    def test_regla_ningun_boton_de_la_lista_lleva_a_un_403(self):
        """D-30: los enlaces de la lista de entregas que el Vendedor ve (Ver contrato, Asignar, Cambiar) abren, no dan 403."""
        self.nueva()
        self.nueva(transportista=self.t1)
        self.client.force_login(self.e.vendedor)
        pagina = self.client.get(reverse("comercial:entregas"))
        enlaces = re.findall(r'href="(/comercial/[^"]*)"', pagina.content.decode())
        self.assertTrue(any("/asignar/" in u for u in enlaces))
        for url in enlaces:
            self.assertNotEqual(self.client.get(url).status_code, 403, url)


class AccionesDeLaListaTests(Base):
    """La lista de entregas (paso 2 de COM-ASG-TRP): «Asignar transportista» (sin transportista), «Cambiar transportista» (con transportista y no en curso) y «En curso» sin acción."""

    def fila(self, e):
        self.client.force_login(self.gerente)
        html = texto(self.client.get(reverse("comercial:entregas"), {"estado": ""}))
        return next(f for f in re.findall(r"<tr[^>]*>.*?</tr>", html, re.S) if e.codigo in f)

    def test_regla_cada_fila_ofrece_la_accion_que_le_corresponde(self):
        """Sin transportista, «Asignar transportista»; con transportista, «Cambiar transportista»; en curso, «En curso» y ninguna acción; un retiro y una concretada, ninguna."""
        _, _, sin = self.nueva()
        _, _, con = self.nueva(transportista=self.t1)
        _, _, curso = self.nueva(transportista=self.t2, dias=0)
        vehiculo_en_ruta(self.t2)
        retiro = compra_venta(self.e, modalidad="retiro")
        det = detalle(retiro, self.e.variedad, 10)
        r = entrega(retiro, [reserva_lista(det, self.lote, 10)])
        cerrada = compra_venta(self.e)
        concretada = entrega(cerrada, [reserva_lista(detalle(cerrada, self.e.variedad, 10), self.lote, 10)], estado="concretada")
        url = lambda e: reverse("comercial:entrega_asignar", args=[e.pk])
        self.assertIn("Asignar transportista", self.fila(sin))
        self.assertIn(url(sin), self.fila(sin))
        self.assertIn("Cambiar transportista", self.fila(con))
        self.assertIn("En curso", self.fila(curso))
        for e in (curso, r):
            self.assertNotIn(url(e), self.fila(e))
        self.assertNotIn("Asignar transportista", self.fila(r))
        self.assertNotIn("Cambiar transportista", self.fila(curso))
        for ausente in ("Asignar transportista", "Cambiar transportista", "En curso"):
            self.assertNotIn(ausente, self.fila(concretada))
