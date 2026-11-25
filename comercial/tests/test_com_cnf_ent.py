# Pruebas de COM-CNF-ENT · Confirmar Entrega (COM-06b, paso 3): `confirmacion.datos_para_el_cliente`, `tipos_de_queja_disponibles`, `datos_de_respuesta`, `resumen_de_respuesta`,
# `registrar_respuesta` y `reenviar_acuse`. Una por postcondición (a a k) y extensión (2a con sus tres motivos, 2b, 3a con 3a.4a, 3a.4b, 3a.5a y 3a.6a, 3b con 3b.1a, 4a, 6a, 7a, 8a); cada regla
# (los tipos disponibles con y sin retraso, una por tipo, el retraso solo con sus líneas, el contrato finalizado, la vigencia calculada); que el cliente no ve perdidas ni costos; que todo es atómico.
# Fuente: docs/casos_de_uso/comercial/confirmacion.md («COM-CNF-ENT» y «Cómo se aplica», «Servicios» y «Registrar la respuesta»), D-65 y D-68. Después de cada prueba se verifican los invariantes.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa): ver el docstring de cada función de `comercial/servicios/confirmacion.py`. Códigos de error: `respuesta_obligatoria`,
# `quejas_vacias`, `tipo_no_disponible`, `queja_repetida`, `queja_sin_detalles`, `linea_no_valida`, `motivo_obligatorio`, `motivo_largo`, `enlace_no_sirve` (con `params["motivo"]`) y `acuse_no_disponible`.

from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from comercial.models import AlertaComercial, DetalleEntrega, EnlaceCliente, Entrega, Queja, Suministro
from comercial.servicios import confirmacion
from comercial.servicios.confirmacion import CON_QUEJAS, CONFORME, NO_RECIBI, DatosDeRespuesta, QuejaPedida
from comercial.tests.fabricas import (
    detalle_suministro,
    discrepancia,
    enlace as un_enlace,
    enlace_de_confirmacion,
    entrega,
    escenario_comercial,
    marcar_concretada,
    reserva_lista,
    suministro,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_solicitudes,
    compra_venta,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta, ConfiguracionOperativa
from produccion.models import MovimientoStock
from produccion.tests.fabricas import lote_maduro, variedad_con_stock

HOY = timezone.localdate()
ESTADO, RETRASO, OTRO = "estado_mercaderia", "retraso", "otro"


def codigos(error):
    """Los códigos de un `ValidationError` con o sin `error_dict`."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


def campos(error):
    """Los campos con error de un `ValidationError`."""
    return sorted(error.error_dict) if hasattr(error, "error_dict") else []


def motivo_de(error):
    """El `params["motivo"]` de un `enlace_no_sirve`."""
    return error.error_dict["__all__"][0].params["motivo"]


class Base(ConDatosDeInventario, TestCase):
    """Un suministro con dos detalles (dos variedades, 100 y 60 plantas) y su Vendedor y su Gerente. Cada `nueva()` arma una entrega concretada con su enlace de confirmación."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.gerente = crear_gerente()
        cls.otra_variedad, _ = variedad_con_stock(cls.e, "Rúcula 06b")
        cls.lote = lote_maduro(cls.e, 500)
        cls.lote_otra = lote_maduro(cls.e, 500, variedad=cls.otra_variedad)
        cls.contrato = suministro(cls.e)
        # El primero tiene un plazo de entrega de 1 día; el segundo, de 30: el retraso de una entrega es solo el del primero.
        cls.d1 = detalle_suministro(cls.contrato, cls.e.variedad, cantidad=100, minima=50, plazo_entrega=1)
        cls.d2 = detalle_suministro(cls.contrato, cls.otra_variedad, cantidad=60, minima=30, plazo_entrega=30)

    def setUp(self):
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)

    def nueva(self, *, cantidades=None, retraso=0, con_enlace=True):
        """Una entrega de suministro concretada (directo en la base) con sus dos líneas y su enlace de confirmación vigente. `retraso` días de retraso en la primera línea (se fija la fecha de
        resolución; el período es dentro de 3 días y el plazo, de 1). Devuelve `SimpleNamespace(entrega, enlace, token, lineas)`."""
        # Reservas nuevas en cada entrega: una reserva tiene a lo sumo una línea en una entrega no cancelada (regla 4 de 8.8; invariante de entregas).
        r1 = reserva_lista(None, self.lote, 100, fecha_entrega=self.d1.fecha_primer_entrega, detalle_suministro=self.d1)
        r2 = reserva_lista(None, self.lote_otra, 60, fecha_entrega=self.d2.fecha_primer_entrega, detalle_suministro=self.d2)
        e = marcar_concretada(entrega(self.contrato, [r1, r2]), cantidades=cantidades)
        if retraso:
            Entrega.objects.filter(pk=e.pk).update(fecha_resolucion_orden=HOY + timedelta(days=3 + 1 + retraso))
            e.refresh_from_db()
        creado, token = enlace_de_confirmacion(e) if con_enlace else (None, None)
        return SimpleNamespace(entrega=e, enlace=creado, token=token, lineas=list(e.lineas.order_by("pk")))

    def registrar(self, x, respuesta, **extra):
        return confirmacion.registrar_respuesta(x.enlace.pk, respuesta, **extra)

    def conforme(self):
        return DatosDeRespuesta(CONFORME)

    def con_quejas(self, *quejas):
        return DatosDeRespuesta(CON_QUEJAS, list(quejas))

    def no_recibi(self, motivo="No llegó nada."):
        return DatosDeRespuesta(NO_RECIBI, motivo_no_recibi=motivo)

    def refrescar(self, x):
        return Entrega.objects.get(pk=x.entrega.pk)

    @staticmethod
    def alertas_comerciales():
        """Cuántas alertas de `comercial` hay (la base de la prueba puede tener otras, de personal del invernadero)."""
        return Alerta.objects.filter(tipo_alerta__startswith="comercial_").count()

    def avisos(self, cuenta):
        return list(Notificacion.objects.filter(destinatario=cuenta).order_by("pk"))


class DatosParaElClienteTests(Base):
    def test_post_paso_2_el_cliente_ve_la_entrega_con_precio_monto_total_y_vencimiento(self):
        """Paso 2: el contrato, la fecha real, por línea la variedad, la fecha prometida, las cantidades planificada, entregada y devuelta, el precio y el monto; el total y el vencimiento del pago."""
        x = self.nueva(cantidades=[(80, 15, 5), (60, 0, 0)])
        datos = confirmacion.datos_para_el_cliente(x.enlace)
        l1, l2 = datos.lineas
        self.assertEqual((datos.contrato.pk, datos.fecha_real, datos.vencimiento_del_pago), (self.contrato.pk, HOY, x.entrega.fecha_vencimiento_pago))
        self.assertEqual((l1.variedad, l1.fecha_prometida, l1.planificada, l1.entregada, l1.devuelta), (str(self.e.variedad), self.d1.fecha_primer_entrega, 100, 80, 5))
        self.assertEqual((l1.precio, l1.monto), (x.lineas[0].precio_unitario, x.lineas[0].monto_pagar))
        self.assertEqual((l2.planificada, l2.entregada, l2.devuelta), (60, 60, 0))
        self.assertEqual((datos.total, datos.a_pagar, datos.hay_descuento), (x.entrega.monto_total_entrega, x.entrega.monto_total_entrega, False))
        self.assertEqual(datos.vence_el_enlace, HOY + timedelta(days=3))

    def test_regla_el_cliente_no_ve_las_plantas_perdidas_ni_los_costos(self):
        """Garantía mínima: ni la línea ni los datos tienen un campo de plantas perdidas o de costo; la planificada (80 + 15 perdidas + 5 devueltas) las incluye sin mostrarlas."""
        x = self.nueva(cantidades=[(80, 15, 5), (60, 0, 0)])
        datos = confirmacion.datos_para_el_cliente(x.enlace)
        for objeto in (datos, datos.lineas[0]):
            nombres = " ".join(vars(objeto)).lower()
            self.assertNotIn("perd", nombres)
            self.assertNotIn("costo", nombres)
        self.assertEqual(datos.lineas[0].planificada, 100)

    def test_ext_2a_cada_motivo_por_el_que_el_enlace_no_sirve(self):
        """Extensión 2a: usado, vencido y anulado dan `enlace_no_sirve` con su motivo; un enlace de faltante (otro tipo) da `no_valido`."""
        for estado, motivo in (("usado", "usado"), ("vencido", "vencido"), ("anulado", "anulado")):
            x = self.nueva(con_enlace=False)
            creado, _ = enlace_de_confirmacion(x.entrega, estado=estado)
            with self.assertRaises(ValidationError) as c:
                confirmacion.datos_para_el_cliente(creado)
            self.assertEqual((codigos(c.exception), motivo_de(c.exception)), (["enlace_no_sirve"], motivo))
        venta = compra_venta(self.e, estado="pendiente_decision")
        faltante, _ = un_enlace(venta)
        with self.assertRaises(ValidationError) as c:
            confirmacion.registrar_respuesta(faltante.pk, self.conforme())
        self.assertEqual(motivo_de(c.exception), "no_valido")

    def test_regla_el_ultimo_dia_de_la_vigencia_sirve_y_el_siguiente_no(self):
        """Regla «Enlace de confirmación»: la vigencia es la fecha de resolución más los días del parámetro (3), calculada; el último día sirve y el siguiente no (`vencido`)."""
        x = self.nueva()
        self.assertEqual(confirmacion.datos_para_el_cliente(x.enlace, hoy=HOY + timedelta(days=3)).vence_el_enlace, HOY + timedelta(days=3))
        with self.assertRaises(ValidationError) as c:
            confirmacion.datos_para_el_cliente(x.enlace, hoy=HOY + timedelta(days=4))
        self.assertEqual(motivo_de(c.exception), "vencido")

    def test_regla_cambiar_el_parametro_cambia_la_vigencia_de_un_enlace_ya_enviado(self):
        """D-68 punto 8: con `dias_vigencia_enlace_confirmacion = 1`, el enlace ya creado vence a los 2 días."""
        x = self.nueva()
        configuracion = ConfiguracionOperativa.objects.get_or_create(singleton=1)[0]
        configuracion.dias_vigencia_enlace_confirmacion = 1
        configuracion.save()
        with self.assertRaises(ValidationError):
            confirmacion.datos_para_el_cliente(x.enlace, hoy=HOY + timedelta(days=2))
        self.assertEqual(confirmacion.datos_para_el_cliente(x.enlace, hoy=HOY + timedelta(days=1)).vence_el_enlace, HOY + timedelta(days=1))

    def test_ext_2b_el_detalle_con_discrepancia_pendiente_se_marca_en_revision(self):
        """Extensión 2b: cada detalle de la discrepancia «pendiente de revisión» trae `en_revision`; los demás, no."""
        x = self.nueva(cantidades=[(10, 0, 90), (10, 0, 50)])
        d = discrepancia(x.entrega, minima=50)  # una línea por cada línea de suministro de la entrega
        from comercial.models import LineaDiscrepancia

        LineaDiscrepancia.objects.filter(discrepancia=d, detalle_entrega=x.lineas[1]).delete()
        datos = confirmacion.datos_para_el_cliente(x.enlace)
        self.assertEqual([l.en_revision for l in datos.lineas], [True, False])

    def test_regla_la_entrega_a_pagar_resta_lo_descontado_hasta_que_exista_una_indemnizacion(self):
        """PCU 16: «lo que queda a pagar» es el monto a cobrar de la entrega (`entregas.monto_a_cobrar`); sin indemnizaciones aceptadas (COM-07) es el total y no se muestra la diferencia."""
        x = self.nueva()
        datos = confirmacion.datos_para_el_cliente(x.enlace)
        self.assertEqual(datos.a_pagar, x.entrega.monto_total_entrega)
        self.assertFalse(datos.hay_descuento)


class TiposDeQuejaTests(Base):
    def test_regla_tipos_de_queja_sin_retraso_son_estado_de_la_mercaderia_y_otro(self):
        """Regla «Tipos de queja»: sin ningún detalle con días de retraso, no se ofrece «retraso»."""
        datos = confirmacion.datos_para_el_cliente(self.nueva().enlace)
        self.assertEqual([v for v, _ in confirmacion.tipos_de_queja_disponibles(datos)], [ESTADO, OTRO])

    def test_regla_tipos_de_queja_con_retraso_se_ofrece_retraso(self):
        """Regla «Queja por retraso»: con algún detalle con días de retraso mayores que cero, «retraso» aparece (entre los otros dos)."""
        datos = confirmacion.datos_para_el_cliente(self.nueva(retraso=2).enlace)
        self.assertEqual([v for v, _ in confirmacion.tipos_de_queja_disponibles(datos)], [ESTADO, RETRASO, OTRO])
        self.assertEqual([l.dias_de_retraso for l in datos.lineas], [2, 0])

    def test_regla_los_dias_de_retraso_son_fecha_de_resolucion_menos_periodo_mas_plazo(self):
        """Regla «Queja por retraso»: días = fecha de resolución − (fecha del período + plazo de entrega de la cláusula); nunca negativos."""
        datos = confirmacion.datos_para_el_cliente(self.nueva(retraso=5).enlace)
        self.assertEqual([l.dias_de_retraso for l in datos.lineas], [5, 0])
        self.assertEqual(confirmacion.datos_para_el_cliente(self.nueva().enlace).lineas[0].dias_de_retraso, 0)  # llegó antes del límite

    def test_ext_4a_cambiar_de_respuesta_descarta_las_quejas_y_el_motivo(self):
        """Extensión 4a: si el cliente pasa a «conforme» o a «no recibí», las quejas agregadas se descartan; el motivo de «no recibí» solo cuenta con esa respuesta."""
        post = {"respuesta": CONFORME, f"queja_{ESTADO}": "1", f"lineas_{ESTADO}": ["1"], f"motivo_{ESTADO}": "Mal estado.", "motivo_no_recibi": "No llegó."}
        datos = confirmacion.datos_de_respuesta(post)
        self.assertEqual((datos.respuesta, datos.quejas, datos.motivo_no_recibi), (CONFORME, [], ""))
        datos = confirmacion.datos_de_respuesta({**post, "respuesta": NO_RECIBI})
        self.assertEqual((datos.quejas, datos.motivo_no_recibi), ([], "No llegó."))
        datos = confirmacion.datos_de_respuesta({**post, "respuesta": CON_QUEJAS})
        self.assertEqual((len(datos.quejas), datos.motivo_no_recibi), (1, ""))
        self.assertEqual((datos.quejas[0].tipo, datos.quejas[0].lineas, datos.quejas[0].motivo), (ESTADO, [1], "Mal estado."))

    def test_regla_los_datos_de_respuesta_llegan_en_el_orden_de_los_tipos(self):
        """Las quejas se arman en el orden estado, retraso y otro, sin importar el orden del formulario; lo que no es un número en `lineas_<tipo>` se descarta."""
        post = {"respuesta": CON_QUEJAS, f"queja_{OTRO}": "1", f"lineas_{OTRO}": ["3", "x"], f"queja_{ESTADO}": "1", f"lineas_{ESTADO}": ["1", "2"]}
        datos = confirmacion.datos_de_respuesta(post)
        self.assertEqual([(q.tipo, q.lineas) for q in datos.quejas], [(ESTADO, [1, 2]), (OTRO, [3])])


class ResumenYValidacionTests(Base):
    def datos(self, **opciones):
        x = self.nueva(**opciones)
        return x, confirmacion.datos_para_el_cliente(x.enlace)

    def error(self, datos, respuesta):
        with self.assertRaises(ValidationError) as c:
            confirmacion.resumen_de_respuesta(datos, respuesta)
        return c.exception

    def test_regla_sin_elegir_la_respuesta_se_pide(self):
        """Paso 3: hay que indicar si recibió la entrega (`respuesta_obligatoria`)."""
        _, datos = self.datos()
        error = self.error(datos, DatosDeRespuesta(""))
        self.assertEqual((codigos(error), campos(error)), (["respuesta_obligatoria"], ["respuesta"]))

    def test_ext_3a_6a_con_quejas_pero_sin_agregar_ninguna_se_pide_una_o_estar_conforme(self):
        """Extensión 3a.6a: «con quejas» sin ninguna queja da `quejas_vacias`."""
        _, datos = self.datos()
        self.assertEqual(codigos(self.error(datos, self.con_quejas())), ["quejas_vacias"])

    def test_ext_3a_4a_una_queja_sin_detalles_se_rechaza(self):
        """Extensión 3a.4a: cada queja necesita al menos un detalle (`queja_sin_detalles`, campo `lineas_<tipo>`)."""
        _, datos = self.datos()
        error = self.error(datos, self.con_quejas(QuejaPedida(ESTADO, [], "Mal estado.")))
        self.assertEqual((codigos(error), campos(error)), (["queja_sin_detalles"], [f"lineas_{ESTADO}"]))

    def test_ext_3a_4b_el_motivo_es_obligatorio_en_estado_y_otro_pero_no_en_retraso(self):
        """Extensión 3a.4b y regla «Motivo de la queja»: obligatorio en «estado de la mercadería» y «otro» (`motivo_obligatorio`); opcional en «retraso»."""
        x, datos = self.datos(retraso=3)
        l1 = x.lineas[0].pk
        for tipo in (ESTADO, OTRO):
            error = self.error(datos, self.con_quejas(QuejaPedida(tipo, [l1], "   ")))
            self.assertEqual((codigos(error), campos(error)), (["motivo_obligatorio"], [f"motivo_{tipo}"]))
        resumen = confirmacion.resumen_de_respuesta(datos, self.con_quejas(QuejaPedida(RETRASO, [l1], "")))
        self.assertEqual([q.tipo for q in resumen.quejas], [RETRASO])

    def test_regla_el_motivo_pasa_de_500_caracteres_se_rechaza(self):
        """Regla del motivo: hasta 500 caracteres (`motivo_largo`), en una queja y en «no recibí»."""
        x, datos = self.datos()
        error = self.error(datos, self.con_quejas(QuejaPedida(OTRO, [x.lineas[0].pk], "x" * 501)))
        self.assertEqual(codigos(error), ["motivo_largo"])
        self.assertEqual(codigos(self.error(datos, self.no_recibi("x" * 501))), ["motivo_largo"])
        confirmacion.resumen_de_respuesta(datos, self.con_quejas(QuejaPedida(OTRO, [x.lineas[0].pk], "x" * 500)))

    def test_regla_retraso_solo_con_sus_lineas_y_solo_si_hay_retraso(self):
        """Regla «Queja por retraso»: sin retraso en la entrega «retraso» no está disponible (`tipo_no_disponible`); con retraso solo admite las líneas demoradas (`linea_no_valida`)."""
        x, datos = self.datos()
        error = self.error(datos, self.con_quejas(QuejaPedida(RETRASO, [x.lineas[0].pk])))
        self.assertEqual(codigos(error), ["tipo_no_disponible"])
        x, datos = self.datos(retraso=2)
        error = self.error(datos, self.con_quejas(QuejaPedida(RETRASO, [x.lineas[1].pk])))  # la segunda no llegó con retraso
        self.assertEqual((codigos(error), campos(error)), (["linea_no_valida"], [f"lineas_{RETRASO}"]))
        confirmacion.resumen_de_respuesta(datos, self.con_quejas(QuejaPedida(RETRASO, [x.lineas[0].pk])))

    def test_regla_una_linea_de_otra_entrega_no_vale(self):
        """Garantía mínima: el cliente solo responde sobre la entrega de su enlace: un detalle de otra entrega da `linea_no_valida`."""
        x, datos = self.datos()
        otra = self.nueva()
        error = self.error(datos, self.con_quejas(QuejaPedida(ESTADO, [otra.lineas[0].pk], "Mal estado.")))
        self.assertEqual(codigos(error), ["linea_no_valida"])

    def test_regla_como_maximo_una_queja_por_tipo(self):
        """Regla «Tipos de queja»: dos quejas del mismo tipo en una respuesta dan `queja_repetida`."""
        x, datos = self.datos()
        pedida = QuejaPedida(OTRO, [x.lineas[0].pk], "Otra cosa.")
        self.assertEqual(codigos(self.error(datos, self.con_quejas(pedida, pedida))), ["queja_repetida"])

    def test_ext_3b_1a_no_recibi_exige_el_motivo(self):
        """Extensión 3b.1a: el motivo de «no recibí» es obligatorio (`motivo_obligatorio`, campo `motivo_no_recibi`)."""
        _, datos = self.datos()
        error = self.error(datos, self.no_recibi("  "))
        self.assertEqual((codigos(error), campos(error)), (["motivo_obligatorio"], ["motivo_no_recibi"]))

    def test_ext_3a_5a_quitar_una_queja_la_saca_del_resumen_y_el_resumen_no_escribe(self):
        """Extensión 3a.5a y paso 4: el resumen solo trae las quejas que quedan, con sus productos y su motivo, y la advertencia de que el enlace no podrá volver a usarse; no registra nada."""
        x, datos = self.datos(retraso=2)
        l1, l2 = x.lineas[0].pk, x.lineas[1].pk
        completo = confirmacion.resumen_de_respuesta(datos, self.con_quejas(QuejaPedida(OTRO, [l2], "Otra cosa."), QuejaPedida(RETRASO, [l1])))
        self.assertEqual([(q.tipo, q.productos) for q in completo.quejas], [(RETRASO, [str(self.e.variedad)]), (OTRO, [str(self.otra_variedad)])])
        sin_retraso = confirmacion.resumen_de_respuesta(datos, self.con_quejas(QuejaPedida(OTRO, [l2], "Otra cosa.")))
        self.assertEqual([q.tipo for q in sin_retraso.quejas], [OTRO])
        self.assertIn("no podrá volver a usarse", sin_retraso.advertencia)
        self.assertEqual((Queja.objects.count(), self.alertas_comerciales(), RegistroAuditoria.objects.filter(accion="respuesta_cliente_entrega").count()), (0, 0, 0))
        self.assertEqual(EnlaceCliente.objects.get(pk=x.enlace.pk).estado, "vigente")

    def test_ext_3b_2_el_resumen_de_no_recibi_trae_el_motivo(self):
        """Extensión 3b.2: el resumen de «no recibí» trae el motivo y ninguna queja."""
        _, datos = self.datos()
        resumen = confirmacion.resumen_de_respuesta(datos, self.no_recibi("  No llegó nada.  "))
        self.assertEqual((resumen.respuesta, resumen.quejas, resumen.motivo_no_recibi), (NO_RECIBI, [], "No llegó nada."))


class RegistrarRespuestaTests(Base):
    def test_post_a_d_confirmar_sin_quejas_confirma_y_deja_el_enlace_usado(self):
        """Postcondiciones a y d: el enlace queda `usado` con su fecha de uso y la confirmación pasa de «no confirmado» a «confirmado»; ni quejas ni alertas ni avisos."""
        x = self.nueva()
        respuesta = self.registrar(x, self.conforme())
        enlace = EnlaceCliente.objects.get(pk=x.enlace.pk)
        self.assertEqual((enlace.estado, enlace.fecha_uso is not None), ("usado", True))
        self.assertEqual(self.refrescar(x).estado_confirmacion_cliente, "confirmado")
        self.assertEqual((respuesta.quejas, respuesta.alertas, Queja.objects.count(), self.alertas_comerciales(), Notificacion.objects.count()), ([], [], 0, 0, 0))

    def test_post_e_cada_queja_nace_pendiente_con_su_tipo_su_motivo_el_cliente_y_los_detalles(self):
        """Postcondición e: estado «pendiente de revisión», `fecha_solicitud` = hoy, su tipo y su motivo (recortado), asociada al cliente y a los detalles que eligió, sin Gerente ni monto."""
        x = self.nueva(retraso=2)
        self.registrar(x, self.con_quejas(QuejaPedida(ESTADO, [x.lineas[0].pk, x.lineas[1].pk], "  Llegó golpeado.  "), QuejaPedida(RETRASO, [x.lineas[0].pk])))
        estado, retraso = Queja.objects.order_by("numero")
        self.assertEqual((estado.tipo_queja, estado.motivo_queja, retraso.tipo_queja, retraso.motivo_queja), (ESTADO, "Llegó golpeado.", RETRASO, ""))
        for q in (estado, retraso):
            self.assertEqual((q.estado_solicitud, q.fecha_solicitud, q.gerente_id, q.monto_indemnizacion, q.cliente_id, q.entrega_id), ("pendiente", HOY, None, None, self.e.cliente.pk, x.entrega.pk))
        self.assertEqual(sorted(estado.detalles.values_list("pk", flat=True)), sorted(l.pk for l in x.lineas))
        self.assertEqual(list(retraso.detalles.values_list("pk", flat=True)), [x.lineas[0].pk])
        self.assertEqual(self.refrescar(x).estado_confirmacion_cliente, "confirmado")  # confirmar es reconocer que se recibió, aunque haya quejas

    def test_post_f_g_cada_queja_genera_su_alerta_para_el_gerente_y_el_aviso_al_vendedor(self):
        """Postcondiciones f y g: una alerta de evento `comercial_queja` para el Gerente (advertencia) con su `AlertaComercial(solicitud=…)` y un aviso al Vendedor con el número y el tipo."""
        x = self.nueva(retraso=2)
        self.registrar(x, self.con_quejas(QuejaPedida(RETRASO, [x.lineas[0].pk]), QuejaPedida(OTRO, [x.lineas[1].pk], "Falta algo.")))
        quejas = list(Queja.objects.order_by("numero"))
        alertas = [AlertaComercial.objects.get(solicitud=q).alerta for q in quejas]
        for q, a in zip(quejas, alertas):
            self.assertEqual((a.tipo_alerta, a.para_gerente, a.nivel_severidad, a.estado_alerta, a.invernadero_id), ("comercial_queja", True, "advertencia", "activa", self.e.invernadero.pk))
            self.assertIn(q.codigo, a.descripcion_alerta)
            self.assertIn(x.entrega.codigo, a.descripcion_alerta)
        self.assertIn("Retraso · 1 producto", alertas[0].descripcion_alerta)
        avisos = self.avisos(self.e.vendedor)
        self.assertEqual(len(avisos), 2)
        self.assertIn(f"{quejas[0].codigo}: queja por retraso del cliente {self.e.cliente.nombre_visible}", avisos[0].detalle)
        self.assertIn(quejas[1].codigo, avisos[1].detalle)
        self.assertEqual(self.avisos(self.gerente), [])  # el Gerente las ve como alertas, no como avisos

    def test_post_i_j_k_no_recibi_deja_no_confirmado_crea_la_alerta_critica_y_avisa_sin_quejas(self):
        """Postcondiciones i, j y k: la confirmación sigue «no confirmado», una alerta crítica «entrega no reconocida» con la entrega y el motivo, el aviso al Vendedor con el motivo y ninguna queja."""
        x = self.nueva()
        r = self.registrar(x, self.no_recibi("No llegó nada a la sucursal."))
        self.assertEqual(self.refrescar(x).estado_confirmacion_cliente, "no_confirmado")
        self.assertEqual(Queja.objects.count(), 0)
        (alerta,) = r.alertas
        vinculo = AlertaComercial.objects.get(alerta=alerta)
        self.assertEqual((alerta.tipo_alerta, alerta.nivel_severidad, alerta.para_gerente, vinculo.entrega_id, vinculo.solicitud_id), ("comercial_entrega_no_reconocida", "critica", True, x.entrega.pk, None))
        self.assertIn("No llegó nada a la sucursal.", alerta.descripcion_alerta)
        self.assertIn(x.entrega.codigo, alerta.descripcion_alerta)
        (aviso,) = self.avisos(self.e.vendedor)
        self.assertIn("No llegó nada a la sucursal.", aviso.detalle)
        self.assertEqual(EnlaceCliente.objects.get(pk=x.enlace.pk).estado, "usado")

    def test_post_c_un_registro_de_auditoria_con_origen_cliente_mediante_enlace(self):
        """Postcondición c: un solo registro `respuesta_cliente_entrega`, sin cuenta y con rol «cliente_enlace»; el cliente, la entrega, el enlace y las quejas afectados; el cambio de la confirmación y, en `datos`, las quejas y las alertas creadas."""
        x = self.nueva()
        self.registrar(x, self.con_quejas(QuejaPedida(OTRO, [x.lineas[0].pk], "Falta algo.")))
        registro = RegistroAuditoria.objects.get(accion="respuesta_cliente_entrega")
        self.assertEqual((registro.usuario_id, registro.rol), (None, "cliente_enlace"))
        self.assertEqual({a["modelo"] for a in registro.afectados}, {"comercial.entrega", "comercial.cliente", "comercial.enlacecliente", "comercial.queja"})
        self.assertEqual(registro.detalle["cambios"], {"estado_confirmacion_cliente": {"antes": "no_confirmado", "despues": "confirmado"}})
        datos = registro.detalle["datos"]
        self.assertEqual((datos["respuesta_cliente"], datos["entrega"]["id"], datos["cliente"]["id"]), (CON_QUEJAS, x.entrega.pk, self.e.cliente.pk))
        self.assertEqual((len(datos["quejas_creadas"]), len(datos["alertas_creadas"])), (1, 1))

    def test_post_c_no_recibi_audita_el_motivo_y_ningun_cambio_de_valores(self):
        """Postcondición c en 3b.4: el motivo en `datos` y ningún cambio (la confirmación no cambia)."""
        x = self.nueva()
        self.registrar(x, self.no_recibi("No llegó."))
        registro = RegistroAuditoria.objects.get(accion="respuesta_cliente_entrega")
        self.assertEqual(registro.detalle["datos"]["motivo_no_reconocida"], "No llegó.")
        self.assertNotIn("cambios", registro.detalle)

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_b_h_el_acuse_lleva_el_numero_y_el_tipo_de_cada_queja(self):
        """Postcondiciones b y h: después de confirmar sale el acuse al correo del cliente con la entrega, la confirmación y el número y el tipo de cada queja."""
        x = self.nueva()
        with self.captureOnCommitCallbacks(execute=True):
            r = self.registrar(x, self.con_quejas(QuejaPedida(ESTADO, [x.lineas[0].pk], "Mal estado."), QuejaPedida(OTRO, [x.lineas[1].pk], "Otra cosa.")))
        (correo,) = mail.outbox
        self.assertEqual(correo.to, [self.e.cliente.email_cliente])
        self.assertIn(x.entrega.codigo, correo.body)
        self.assertIn("Confirmaste que recibiste la entrega", correo.body)
        for q in Queja.objects.all():
            self.assertIn(f"{q.codigo}: {q.get_tipo_queja_display()}", correo.body)
        self.assertTrue(r.acuse_enviado)

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_b_el_acuse_de_no_recibi_deja_constancia_de_que_no_reconocio_la_entrega(self):
        """Postcondición b / 7a: el acuse de «no recibí» es la constancia de que no reconoció la entrega."""
        x = self.nueva()
        with self.captureOnCommitCallbacks(execute=True):
            self.registrar(x, self.no_recibi())
        (correo,) = mail.outbox
        self.assertIn("no reconocés la entrega", correo.body)

    def test_ext_6a_un_segundo_envio_del_mismo_enlace_no_registra_nada(self):
        """Extensión 6a: el enlace ya usado (por ejemplo, la respuesta enviada desde otra pestaña) da `enlace_no_sirve` (usado), sin registrar nada más."""
        x = self.nueva()
        self.registrar(x, self.con_quejas(QuejaPedida(OTRO, [x.lineas[0].pk], "Falta algo.")))
        with self.assertRaises(ValidationError) as c:
            self.registrar(x, self.con_quejas(QuejaPedida(ESTADO, [x.lineas[0].pk], "Mal estado.")))
        self.assertEqual((codigos(c.exception), motivo_de(c.exception)), (["enlace_no_sirve"], "usado"))
        self.assertEqual((Queja.objects.count(), RegistroAuditoria.objects.filter(accion="respuesta_cliente_entrega").count()), (1, 1))

    def test_ext_6a_el_enlace_que_vencio_mientras_completaba_la_respuesta_no_registra_nada(self):
        """Extensión 6a: si la vigencia calculada terminó mientras completaba la respuesta, `enlace_no_sirve` (vencido) y ni cambio de la confirmación, ni quejas, ni alertas, ni aviso."""
        x = self.nueva()
        with self.assertRaises(ValidationError) as c:
            self.registrar(x, self.conforme(), hoy=HOY + timedelta(days=4))
        self.assertEqual(motivo_de(c.exception), "vencido")
        self.assertEqual((self.refrescar(x).estado_confirmacion_cliente, EnlaceCliente.objects.get(pk=x.enlace.pk).estado, Notificacion.objects.count(), RegistroAuditoria.objects.filter(accion="respuesta_cliente_entrega").count()), ("no_confirmado", "vigente", 0, 0))

    def test_regla_la_respuesta_invalida_no_registra_nada(self):
        """Los errores del servicio (por ejemplo, una queja sin motivo) levantan antes de escribir: el enlace sigue vigente y la entrega, «no confirmado»."""
        x = self.nueva()
        with self.assertRaises(ValidationError) as c:
            self.registrar(x, self.con_quejas(QuejaPedida(OTRO, [x.lineas[0].pk], "")))
        self.assertEqual(codigos(c.exception), ["motivo_obligatorio"])
        self.assertEqual((self.refrescar(x).estado_confirmacion_cliente, EnlaceCliente.objects.get(pk=x.enlace.pk).estado, Queja.objects.count()), ("no_confirmado", "vigente", 0))

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_7a_si_el_acuse_no_sale_la_respuesta_queda_registrada_y_se_informa(self):
        """Extensión 7a: el acuse que falla no deshace nada; `acuse_enviado` queda `False` para que la pantalla final ofrezca «Reenviar acuse»."""
        x = self.nueva()
        with mock.patch("core.correo.enviar_correo", return_value=False), self.captureOnCommitCallbacks(execute=True):
            r = self.registrar(x, self.conforme())
        self.assertFalse(r.acuse_enviado)
        self.assertEqual((self.refrescar(x).estado_confirmacion_cliente, EnlaceCliente.objects.get(pk=x.enlace.pk).estado), ("confirmado", "usado"))

    def test_ext_7a_sin_el_correo_del_sistema_el_acuse_no_sale_y_la_respuesta_queda(self):
        """Extensión 7a: sin el correo del sistema configurado el acuse no sale (`acuse_enviado = False`) y la respuesta sigue registrada."""
        x = self.nueva()
        with self.captureOnCommitCallbacks(execute=True):
            r = self.registrar(x, self.conforme())
        self.assertEqual((r.acuse_enviado, mail.outbox), (False, []))

    def test_regla_el_contrato_finalizado_confirma_y_se_queja_igual_sin_tocar_nada_mas(self):
        """Regla «Contrato finalizado o resuelto»: el cliente confirma y se queja igual; no cambia el estado de la orden, los montos, el stock ni la cantidad de incumplimientos del contrato."""
        x = self.nueva()
        Suministro.objects.filter(pk=self.contrato.pk).update(estado_suministro="finalizado")
        antes = Entrega.objects.values("estado_orden", "monto_total_entrega", "fecha_vencimiento_pago", "fecha_resolucion_orden").get(pk=x.entrega.pk)
        lineas_antes = list(DetalleEntrega.objects.filter(entrega=x.entrega).values("cant_entregada", "cant_perdida", "cant_devuelta", "monto_pagar").order_by("pk"))
        movimientos = MovimientoStock.objects.count()
        self.registrar(x, self.con_quejas(QuejaPedida(OTRO, [x.lineas[0].pk], "Falta algo.")))
        self.assertEqual(Entrega.objects.values("estado_orden", "monto_total_entrega", "fecha_vencimiento_pago", "fecha_resolucion_orden").get(pk=x.entrega.pk), antes)
        self.assertEqual(list(DetalleEntrega.objects.filter(entrega=x.entrega).values("cant_entregada", "cant_perdida", "cant_devuelta", "monto_pagar").order_by("pk")), lineas_antes)
        self.assertEqual((MovimientoStock.objects.count(), Suministro.objects.get(pk=self.contrato.pk).cantidad_incumplimientos), (movimientos, 0))
        self.assertEqual(self.refrescar(x).estado_confirmacion_cliente, "confirmado")

    def test_regla_cliente_dado_de_baja_responde_igual(self):
        """Regla 2 de 8.18 aplicada al enlace: un cliente dado de baja con una entrega sin responder sigue pudiendo confirmar."""
        from comercial.models import Cliente

        x = self.nueva()
        Cliente.objects.filter(pk=self.e.cliente.pk).update(estado_cliente=Cliente.Estado.INACTIVO)
        self.registrar(x, self.conforme())
        self.assertEqual(self.refrescar(x).estado_confirmacion_cliente, "confirmado")

    def test_regla_sin_el_vendedor_activo_igual_se_registra_sin_aviso(self):
        """La cuenta del Vendedor dada de baja no impide la respuesta: se registra la queja y su alerta, y no hay a quién avisar."""
        from core.models import Usuario

        x = self.nueva()
        Usuario.objects.filter(pk=self.e.vendedor.pk).update(is_active=False)
        self.registrar(x, self.con_quejas(QuejaPedida(OTRO, [x.lineas[0].pk], "Falta algo.")))
        self.assertEqual((Queja.objects.count(), Notificacion.objects.count()), (1, 0))

    def test_regla_el_registro_es_atomico_si_falla_no_queda_nada(self):
        """Requisito especial: la confirmación, las quejas, las alertas, el uso del enlace y los logs se registran juntos o no se registra ninguno."""
        x = self.nueva()
        with mock.patch("comercial.servicios.confirmacion.RegistroAuditoria.objects.registrar", side_effect=RuntimeError("falla")), self.assertRaises(RuntimeError):
            self.registrar(x, self.con_quejas(QuejaPedida(OTRO, [x.lineas[0].pk], "Falta algo.")))
        self.assertEqual((self.refrescar(x).estado_confirmacion_cliente, EnlaceCliente.objects.get(pk=x.enlace.pk).estado), ("no_confirmado", "vigente"))
        self.assertEqual((Queja.objects.count(), self.alertas_comerciales(), AlertaComercial.objects.count(), Notificacion.objects.count()), (0, 0, 0, 0))

    def test_regla_registrar_sin_el_enlace_de_confirmacion_da_no_valido(self):
        """Un id que no es de un enlace de confirmación (inexistente o de faltante) da `enlace_no_sirve` con `no_valido`."""
        with self.assertRaises(ValidationError) as c:
            confirmacion.registrar_respuesta(999999, self.conforme())
        self.assertEqual(motivo_de(c.exception), "no_valido")


@override_settings(CORREO_CONFIGURADO=True)
class ReenviarAcuseTests(Base):
    def test_ext_8a_reenvia_el_acuse_al_correo_registrado_las_veces_que_haga_falta(self):
        """Extensión 8a: `reenviar_acuse` manda otra vez el acuse al correo del cliente (con el número y el tipo de cada queja) y devuelve `True`; se puede pedir de nuevo."""
        x = self.nueva()
        with self.captureOnCommitCallbacks(execute=True):
            self.registrar(x, self.con_quejas(QuejaPedida(OTRO, [x.lineas[0].pk], "Falta algo.")))
        mail.outbox.clear()
        self.assertTrue(confirmacion.reenviar_acuse(x.enlace.pk))
        self.assertTrue(confirmacion.reenviar_acuse(x.enlace.pk))
        self.assertEqual(len(mail.outbox), 2)
        for correo in mail.outbox:
            self.assertEqual(correo.to, [self.e.cliente.email_cliente])
            self.assertIn(Queja.objects.get().codigo, correo.body)

    def test_ext_8a_si_el_envio_falla_informa_y_se_puede_volver_a_pedir(self):
        """Extensión 8a.2: si el envío falla devuelve `False`; el cliente puede volver a pedirlo."""
        x = self.nueva()
        self.registrar(x, self.conforme())
        with mock.patch("core.correo.enviar_correo", return_value=False):
            self.assertFalse(confirmacion.reenviar_acuse(x.enlace.pk))
        self.assertTrue(confirmacion.reenviar_acuse(x.enlace.pk))

    def test_ext_8a_el_acuse_de_no_recibi_se_reenvia_como_constancia(self):
        """El reenvío rearma lo que dijo el acuse: «no recibí» sale como constancia."""
        x = self.nueva()
        self.registrar(x, self.no_recibi())
        self.assertTrue(confirmacion.reenviar_acuse(x.enlace.pk))
        self.assertIn("no reconocés la entrega", mail.outbox[-1].body)

    def test_ext_8a_sin_respuesta_registrada_no_hay_acuse_que_reenviar(self):
        """Solo desde la pantalla final: con el enlace todavía vigente, `acuse_no_disponible`."""
        x = self.nueva()
        with self.assertRaises(ValidationError) as c:
            confirmacion.reenviar_acuse(x.enlace.pk)
        self.assertEqual(codigos(c.exception), ["acuse_no_disponible"])
