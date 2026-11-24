# Pruebas de COM-MOD-SUM, Modificar Suministro (COM-03b, paso 3; docs/casos_de_uso/comercial/suministro.md, «COM-MOD-SUM»): `huella_de`,
# `datos_de_modificacion`, `resumen_de_modificacion` y `modificar_suministro`. Una prueba por postcondición (a a j), extensión, regla y decisión
# de aplicación. Las que escriben verifican al final los invariantes de reservas y de suministros. La concurrencia está en
# `test_suministros_concurrencia.py`. Ninguna regla se prueba sin mirar la base: lo que «no cambia» se compara contra lo que había.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), todo en `comercial/servicios/suministros.py`:
#   - `CambioDeDetalle(detalle_id, accion, rige_desde, rige_visto, cantidad, periodo, precio, mecanismo, porcentaje, meses, plazo_entrega,
#     indemnizacion_retraso, cantidad_minima, indemnizacion_faltante)`: un detalle VIGENTE del contrato. `accion` es `sin_cambios` (por
#     omisión), `modificar` o `terminar`. Todo texto (como llegó). **Un campo vacío = «sin cambio»** (el formulario viene cargado con los valores
#     actuales: lo igual al actual tampoco es un cambio). `rige_desde` (fecha elegida, 5a; vacía = la propuesta) y `rige_visto` (la propuesta
#     que vio la persona al abrir la pantalla, oculta en el formulario; vacía = no se compara).
#   - `CambiosDeSuministro(vendedor_id, duracion, tolerados, multa, plazo_pago, indemnizacion_pago, detalles, nuevos)`: los datos del contrato
#     (vacío = sin cambio), una lista de `CambioDeDetalle` y los detalles nuevos (`RenglonDeSuministro`, los de COM-PCT-SUM). Con
#     `CambiosDeSuministro.desde_post(datos)`; el cliente y la fecha de realización no se leen (extensión 5g).
#   - `huella_de(suministro) -> str` (10b). `datos_de_modificacion(actor, suministro_id, cambios) -> DatosDeModificacion` (solo lectura: no escribe
#     ni bloquea) con `suministro`, `hoy`, `ventana`, `huella`, `filas` (una por detalle vigente: `detalle`, `rige_desde` —la propuesta, o `None` si no
#     le quedan períodos fuera de la ventana—, `opciones` —los períodos posteriores a la ventana—, `precio_propuesto`), `errores` y `codigos`
#     (`{campo: [..]}`), `equivale_a_terminar_el_contrato`, `duracion_sugerida` y `fecha_sugerida` (5c.1a).
#     `resumen_de_modificacion(actor, suministro_id, cambios, huella) -> ResumenDeModificacion` con `cambios` (lista de `CambioResumido(texto,
#     rige_desde)`) y `ValidationError` si algo no vale. `modificar_suministro(actor, suministro_id, cambios, huella) -> Suministro`, con
#     `detalles_finalizados` y `detalles_creados` (listas) como atributos.
#   - Errores: `ValidationError` por campo. Campos: `vendedor`, `duracion`, `tolerados`, `multa`, `plazo_pago`, `indemnizacion_pago`,
#     `modificar-<id del detalle>-<campo>` (`accion`, `rige_desde`, `cantidad`, `periodo`, `precio`, `mecanismo`, `porcentaje`, `meses`, `plazo_entrega`,
#     `indemnizacion_retraso`, `cantidad_minima`, `indemnizacion_faltante`), `detalle-<i>-<campo>` (los detalles nuevos, como en COM-PCT-SUM) y `__all__`.
#   - Códigos: `contrato_cambio` (10b, `__all__`), `rescision_acordada` (`__all__`), `ventana_cambio` (10a, `__all__`), `sin_cambios` (7a, `__all__`),
#     `detalle_sin_cambios` (7a por detalle), `detalle_sin_periodos_posteriores`, `rige_desde_invalido`, `tolerados_invalidos`,
#     `tolerados_menores_que_acumulados`, `duracion_invalida`, `fin_anterior_a_la_ventana`, `par_vigente` (5b.2), `superposicion_sin_confirmar` (9d),
#     `supera_disponible` (9e, al revisar), `stock_insuficiente` (10, al confirmar), `vendedor_invalido`, y los de COM-PCT-SUM para cada dato. `PermissionDenied`
#     para quien no es Vendedor o Gerente, para un Vendedor ante un contrato ajeno y para un Vendedor que manda `vendedor_id` (solo el Gerente lo cambia);
#     `Http404` si el suministro no existe.
#   - Comprobante: `comprobantes.enviar_comprobante(contrato, tipo=None, cambios=None)`; con `tipo="modificacion"` el asunto es «Modificación de tu
#     suministro SUM-…» y el contexto lleva `tipo` y `cambios`.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase, override_settings
from django.utils import timezone

from comercial.models import ClausulaSuministrado, ClausulaSuministrante, DetalleSuministro, ReservaStock, Suministro
from comercial.servicios import calendario, suministros
from comercial.servicios.suministros import RenglonDeSuministro
from comercial.tests.fabricas import (
    detalle_suministro,
    direccion_de_cliente,
    escenario_comercial,
    reserva_de_periodo,
    segundo_invernadero,
    suministro,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_suministros,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_vendedor
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
CORREO = "comercial.servicios.comprobantes.correo.enviar_correo"


def en(dias):
    """La fecha de dentro de ``dias`` días."""
    return HOY + timedelta(days=dias)


def iso(dias):
    """La fecha de dentro de ``dias`` días, como la manda el formulario."""
    return str(en(dias))


def codigos_de(error, campo):
    """Los códigos de los errores de un campo."""
    return [e.code for e in error.error_dict.get(campo, [])]


def todos_los_codigos(error):
    """Todos los códigos de una ``ValidationError``, con campos o sin ellos."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


class BaseDeModificacion(ConDatosDeInventario, TestCase):
    """Un contrato de 6 meses con un detalle de 10 plantas cada 7 días (períodos a los 3, 10, 17, 24… días; la ventana de 14 días cubre los dos
    primeros, que están reservados) y otra dirección del cliente. Lo primero que cae fuera de la ventana es el período del día 17."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 200)
        self.gerente = crear_gerente()
        self.s = suministro(self.e, duracion=6, tolerados=3, incumplimientos=0)
        self.d = detalle_suministro(self.s, self.e.variedad, cantidad=10, periodo=7, primera_en_dias=3, minima=1)
        reserva_de_periodo(self.d, en(3), [(self.lote, 10)])
        reserva_de_periodo(self.d, en(10), [(self.lote, 10)])
        self.dir2 = direccion_de_cliente(self.e.cliente).direccion
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_suministros)

    # ---- armado de pedidos ----

    def mod(self, detalle=None, accion="modificar", **extra):
        """Un `CambioDeDetalle` del detalle pedido (por defecto, el del contrato)."""
        return suministros.CambioDeDetalle(detalle_id=(detalle or self.d).pk, accion=accion, **extra)

    def cambios(self, *detalles, nuevos=(), **extra):
        """Un `CambiosDeSuministro` con esos detalles y esos detalles nuevos; ``extra`` son los datos del contrato."""
        return suministros.CambiosDeSuministro(detalles=list(detalles), nuevos=list(nuevos), **extra)

    def nuevo(self, indice=0, **extra):
        """Un detalle nuevo de 20 plantas cada 7 días en la otra dirección, con la primera entrega a los 5 días (dentro de la ventana)."""
        valores = dict(
            indice=indice, variedad_id=str(self.e.variedad.pk), direccion_id=str(self.dir2.pk), cantidad="20", periodo="7",
            primera_entrega=iso(5), mecanismo="fijo", precio="1500,50", porcentaje="", meses="", plazo_entrega="1",
            indemnizacion_retraso="100", cantidad_minima="10", indemnizacion_faltante="50", continuar_superpuesto="",
        )
        valores.update(extra)
        return RenglonDeSuministro(**valores)

    def huella(self):
        """La huella del contrato como está ahora (lo que lleva el formulario oculto al abrir la pantalla)."""
        return suministros.huella_de(Suministro.objects.get(pk=self.s.pk))

    def modificar(self, cambios, actor=None, huella=None):
        """Modifica el contrato como ``actor`` (por defecto, su Vendedor) con la huella de ahora."""
        return suministros.modificar_suministro(actor or self.e.vendedor, self.s.pk, cambios, self.huella() if huella is None else huella)

    def rechazo(self, cambios, actor=None, huella=None):
        """Modifica esperando una ``ValidationError`` y la devuelve."""
        with self.assertRaises(ValidationError) as contexto:
            self.modificar(cambios, actor, huella)
        return contexto.exception

    def hoy_mas(self, dias):
        """Mueve «hoy» ``dias`` días hacia adelante (la fecha que lee el servicio)."""
        return mock.patch("inventario.servicios.stock.hoy", return_value=HOY + timedelta(days=dias))

    def con_otro_detalle(self, primera_en_dias=3, periodo=7, cantidad=10, **extra):
        """Un segundo detalle vigente del contrato (en la otra dirección)."""
        return detalle_suministro(
            self.s, self.e.variedad, direccion=self.dir2, cantidad=cantidad, periodo=periodo, primera_en_dias=primera_en_dias, **extra
        )

    def recargado(self, objeto):
        """El objeto de la base, como está ahora."""
        return type(objeto).objects.get(pk=objeto.pk)


class HuellaTests(BaseDeModificacion):
    """`huella_de` (10b): resume el estado del contrato al abrir la pantalla."""

    def test_regla_huella_es_estable_para_el_mismo_estado(self):
        """10b: dos lecturas sin cambios dan la misma huella (un texto)."""
        self.assertEqual(self.huella(), self.huella())
        self.assertIsInstance(self.huella(), str)

    def test_regla_huella_cambia_con_cada_dato_que_resume(self):
        """10b: estado, duración, tolerados, acumulados, multa, cláusula del suministrado, Vendedor, id de los detalles vigentes y datos de la
        rescisión: cualquier cambio cambia la huella."""
        base = self.huella()
        cambios = [
            (Suministro, self.s.pk, dict(estado_suministro="finalizado")),
            (Suministro, self.s.pk, dict(duracion_meses=7)),
            (Suministro, self.s.pk, dict(incumplimientos_tolerados=4)),
            (Suministro, self.s.pk, dict(cantidad_incumplimientos=1)),
            (Suministro, self.s.pk, dict(multa_resolucion=Decimal("1.00"))),
            (Suministro, self.s.pk, dict(vendedor_id=crear_vendedor(email="otro@infoponia.com").pk)),
            (ClausulaSuministrado, self.s.clausula_suministrado.pk, dict(plazo_pago_dias=99)),
            (ClausulaSuministrado, self.s.clausula_suministrado.pk, dict(indemnizacion_retraso_pago=Decimal("77.00"))),
            (DetalleSuministro, self.d.pk, dict(estado_detalle_suministro="finalizado")),
        ]
        for modelo, pk, valores in cambios:
            with self.subTest(valores=valores):
                original = {c: getattr(modelo.objects.get(pk=pk), c) for c in valores}
                modelo.objects.filter(pk=pk).update(**valores)
                self.assertNotEqual(self.huella(), base)
                modelo.objects.filter(pk=pk).update(**original)
                self.assertEqual(self.huella(), base)

    def test_regla_huella_cambia_si_aparece_un_detalle_vigente_o_una_rescision(self):
        """10b: un detalle vigente nuevo o los datos de una rescisión acordada cambian la huella."""
        base = self.huella()
        self.con_otro_detalle(primera_en_dias=30)
        self.assertNotEqual(self.huella(), base)
        con_detalle = self.huella()
        Suministro.objects.filter(pk=self.s.pk).update(
            motivo_rescision="otro", fecha_acuerdo_rescision=HOY, fecha_registro_rescision=HOY, fecha_ultima_entrega_rescision=en(10)
        )
        self.assertNotEqual(self.huella(), con_detalle)


class LecturaTests(BaseDeModificacion):
    """`datos_de_modificacion` y `resumen_de_modificacion`: pasos 2 a 8, sin escribir."""

    def test_regla_desde_cuando_rige_es_el_primer_periodo_posterior_a_la_ventana(self):
        """Paso 4 y regla «Desde cuándo rige un cambio»: con 14 días de ventana y períodos a los 3, 10, 17 y 24 días, el cambio rige desde el
        día 17; las opciones de 5a son todos los períodos posteriores a la ventana."""
        datos = suministros.datos_de_modificacion(self.e.vendedor, self.s.pk, self.cambios())
        (fila,) = datos.filas
        self.assertEqual(fila.detalle.pk, self.d.pk)
        self.assertEqual(fila.rige_desde, en(17))
        self.assertEqual(fila.opciones[:3], [en(17), en(24), en(31)])
        self.assertEqual(datos.ventana, en(14))
        self.assertEqual(datos.huella, self.huella())

    def test_regla_un_detalle_sin_periodos_fuera_de_la_ventana_no_se_puede_cambiar(self):
        """Paso 4: si el detalle termina dentro de la ventana, `rige_desde` es `None` («Todos sus períodos ya están dentro de la ventana de
        pre-reserva.») y modificarlo o terminarlo se rechaza con `detalle_sin_periodos_posteriores`."""
        corto = suministro(self.e, fecha_realizacion=HOY - timedelta(days=170), duracion=6)  # su fecha de fin cae a ~10 días
        d = detalle_suministro(corto, self.e.variedad, direccion=self.dir2, primera_en_dias=3)
        datos = suministros.datos_de_modificacion(self.e.vendedor, corto.pk, self.cambios())
        self.assertIsNone(datos.filas[0].rige_desde)
        for accion in ("modificar", "terminar"):
            with self.subTest(accion=accion), self.assertRaises(ValidationError) as contexto:
                suministros.modificar_suministro(
                    self.e.vendedor, corto.pk, self.cambios(self.mod(d, accion, cantidad="20")), suministros.huella_de(corto)
                )
            self.assertEqual(codigos_de(contexto.exception, f"modificar-{d.pk}-accion"), ["detalle_sin_periodos_posteriores"])

    def test_regla_el_precio_propuesto_del_sucesor_es_el_que_tendria_el_detalle_actual(self):
        """Paso 6 (decisión de aplicación): el precio inicial del sucesor viene propuesto con el precio del detalle actual en la fecha desde la que
        rige (con ajuste, el ajustado), para no bajarlo sin querer."""
        ajustado = suministro(self.e, fecha_realizacion=HOY - timedelta(days=200), duracion=12)
        d = detalle_suministro(
            ajustado, self.e.variedad, direccion=self.dir2, primera_en_dias=3, mecanismo="ajuste_periodico", precio="1000.00",
            porcentaje="10", meses=2, fecha_base_ajuste=HOY - timedelta(days=200),
        )
        datos = suministros.datos_de_modificacion(self.e.vendedor, ajustado.pk, self.cambios())
        (fila,) = datos.filas
        self.assertEqual(fila.precio_propuesto, calendario.precio_en(d, fila.rige_desde))
        self.assertGreater(fila.precio_propuesto, Decimal("1000.00"))

    def test_ext_5c_1a_terminar_el_unico_detalle_equivale_a_terminar_el_contrato(self):
        """5c.1a: sin otro detalle vigente (ni nuevo), se avisa que equivale a terminar el contrato y se propone acortar la duración hasta el
        mes que todavía incluye el último período (el del día 10: 1 mes)."""
        datos = suministros.datos_de_modificacion(self.e.vendedor, self.s.pk, self.cambios(self.mod(accion="terminar")))
        self.assertTrue(datos.equivale_a_terminar_el_contrato)
        self.assertEqual(datos.duracion_sugerida, 1)
        self.assertEqual(datos.fecha_sugerida, calendario.sumar_meses(self.s.fecha_realizacion, 1))

    def test_ext_5c_1a_con_otro_detalle_o_un_detalle_nuevo_no_equivale_a_terminar(self):
        """5c.1a: con otro detalle vigente, o agregando uno, terminar uno no equivale a terminar el contrato."""
        datos = suministros.datos_de_modificacion(self.e.vendedor, self.s.pk, self.cambios(self.mod(accion="terminar"), nuevos=[self.nuevo()]))
        self.assertFalse(datos.equivale_a_terminar_el_contrato)
        otro = self.con_otro_detalle()
        datos = suministros.datos_de_modificacion(self.e.vendedor, self.s.pk, self.cambios(self.mod(accion="terminar")))
        self.assertFalse(datos.equivale_a_terminar_el_contrato)
        self.assertEqual(len(datos.filas), 2)
        self.assertIn(otro.pk, [f.detalle.pk for f in datos.filas])

    def test_ext_6a_la_lectura_informa_los_errores_por_campo_sin_lanzarlos(self):
        """6a: `datos_de_modificacion` devuelve los errores por campo y sus códigos (no lanza); la pantalla los muestra."""
        datos = suministros.datos_de_modificacion(self.e.vendedor, self.s.pk, self.cambios(self.mod(cantidad="0"), tolerados="100"))
        self.assertEqual(datos.codigos[f"modificar-{self.d.pk}-cantidad"], ["cantidad_invalida"])
        self.assertEqual(datos.codigos["tolerados"], ["tolerados_invalidos"])

    def test_regla_la_lectura_no_escribe_nada(self):
        """Paso 6: el cálculo de la pantalla no crea ni cambia nada (ni auditoría, ni notificaciones, ni detalles)."""
        antes = (DetalleSuministro.objects.count(), ReservaStock.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count())
        suministros.datos_de_modificacion(self.e.vendedor, self.s.pk, self.cambios(self.mod(cantidad="30"), nuevos=[self.nuevo()], duracion="8"))
        despues = (DetalleSuministro.objects.count(), ReservaStock.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count())
        self.assertEqual(antes, despues)
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")

    def test_regla_el_resumen_lista_cada_cambio_con_la_fecha_desde_la_que_rige(self):
        """Paso 8: el resumen trae un cambio por cada modificación, terminación o detalle nuevo, con su fecha (`rige_desde`) y su texto; no escribe."""
        resumen = suministros.resumen_de_modificacion(
            self.e.vendedor, self.s.pk, self.cambios(self.mod(cantidad="30"), nuevos=[self.nuevo()], tolerados="5"), self.huella()
        )
        self.assertGreaterEqual(len(resumen.cambios), 3)
        self.assertIn(en(17), [c.rige_desde for c in resumen.cambios])
        self.assertTrue(all(c.texto for c in resumen.cambios))
        self.assertEqual(DetalleSuministro.objects.count(), 1)

    def test_regla_el_resumen_rechaza_lo_que_no_vale(self):
        """Paso 8: el resumen valida todo como al registrar (`ValidationError` por campo)."""
        with self.assertRaises(ValidationError) as contexto:
            suministros.resumen_de_modificacion(self.e.vendedor, self.s.pk, self.cambios(self.mod(cantidad="0")), self.huella())
        self.assertEqual(codigos_de(contexto.exception, f"modificar-{self.d.pk}-cantidad"), ["cantidad_invalida"])

    def test_ext_5g_el_cliente_y_la_fecha_de_realizacion_no_se_pueden_cambiar(self):
        """5g: `desde_post` no lee `cliente` ni `fecha_realizacion`: mandarlos no es un cambio (queda `sin_cambios`) y el contrato no cambia."""
        cambios = suministros.CambiosDeSuministro.desde_post({"cliente": "999", "fecha_realizacion": iso(-5)})
        self.assertEqual(todos_los_codigos(self.rechazo(cambios)), ["sin_cambios"])
        self.assertEqual(self.recargado(self.s).cliente_id, self.e.cliente.pk)
        self.assertEqual(self.recargado(self.s).fecha_realizacion, HOY)

    def test_regla_desde_post_arma_los_cambios_del_formulario(self):
        """`desde_post` lee los datos del contrato, `modificar-<id>-<campo>` de cada detalle (con `accion`, `rige_desde` y `rige_visto`) y los
        `detalle-<i>-<campo>` de los detalles nuevos."""
        cambios = suministros.CambiosDeSuministro.desde_post(
            {
                "tolerados": "5", "duracion": "8", "vendedor": "7",
                f"modificar-{self.d.pk}-accion": "modificar", f"modificar-{self.d.pk}-cantidad": "30",
                f"modificar-{self.d.pk}-rige_desde": iso(24), f"modificar-{self.d.pk}-rige_visto": iso(17),
                "detalle-0-variedad": str(self.e.variedad.pk), "detalle-0-cantidad": "20",
            }
        )
        self.assertEqual((cambios.tolerados, cambios.duracion, cambios.vendedor_id), ("5", "8", "7"))
        (cambio,) = cambios.detalles
        self.assertEqual((cambio.detalle_id, cambio.accion, cambio.cantidad, cambio.rige_desde, cambio.rige_visto), (self.d.pk, "modificar", "30", iso(24), iso(17)))
        (nuevo,) = cambios.nuevos
        self.assertEqual((nuevo.indice, nuevo.variedad_id, nuevo.cantidad), (0, str(self.e.variedad.pk), "20"))


class ModificarDetalleTests(BaseDeModificacion):
    """Postcondición a: modificar un detalle lo finaliza y crea su sucesor (MD-131)."""

    def test_post_a_modificar_la_cantidad_finaliza_el_detalle_y_crea_el_sucesor(self):
        """Postcondición a y regla «Detalle sucesor»: el detalle queda «finalizado» con `fecha_fin_detalle` = su último período anterior a la
        fecha desde la que rige (el del día 10); se crea un detalle «vigente» con la cantidad nueva, la misma variedad y dirección, el mismo
        período, `reemplaza_a` = el anterior, `fecha_primer_entrega` y `fecha_base_ajuste` = el día 17."""
        s = self.modificar(self.cambios(self.mod(cantidad="25")))
        anterior = self.recargado(self.d)
        self.assertEqual((anterior.estado_detalle_suministro, anterior.fecha_fin_detalle), ("finalizado", en(10)))
        (sucesor,) = DetalleSuministro.objects.filter(reemplaza_a=anterior)
        self.assertEqual(
            (sucesor.estado_detalle_suministro, sucesor.suministro_id, sucesor.variedad_id, sucesor.direccion_id, sucesor.cantidad_por_periodo,
             sucesor.periodo_entrega_dias, sucesor.fecha_primer_entrega, sucesor.fecha_base_ajuste, sucesor.fecha_fin_detalle,
             sucesor.precio_unitario_suministro, sucesor.mecanismo_precio),
            ("vigente", self.s.pk, self.e.variedad.pk, self.d.direccion_id, 25, 7, en(17), en(17), None, Decimal("100.00"), "fijo"),
        )
        self.assertEqual([x.pk for x in s.detalles_finalizados], [anterior.pk])
        self.assertEqual([x.pk for x in s.detalles_creados], [sucesor.pk])
        self.assertEqual(self.recargado(self.s).estado_suministro, "vigente")

    def test_post_a_el_sucesor_copia_la_clausula_y_lo_que_no_cambio(self):
        """Postcondición a: el sucesor lleva su propia cláusula del suministrante, igual a la del anterior si no se cambió."""
        antes = ClausulaSuministrante.objects.get(detalle=self.d)
        self.modificar(self.cambios(self.mod(cantidad="25")))
        (sucesor,) = DetalleSuministro.objects.filter(reemplaza_a=self.d)
        c = ClausulaSuministrante.objects.get(detalle=sucesor)
        self.assertNotEqual(c.pk, antes.pk)
        self.assertEqual(
            (c.plazo_entrega_dias, c.indemnizacion_retraso_entrega, c.cantidad_minima, c.indemnizacion_faltante),
            (antes.plazo_entrega_dias, antes.indemnizacion_retraso_entrega, antes.cantidad_minima, antes.indemnizacion_faltante),
        )
        self.assertEqual(ClausulaSuministrante.objects.get(detalle=self.d).pk, antes.pk)

    def test_post_a_se_pueden_cambiar_periodo_precio_mecanismo_y_clausula_del_suministrante(self):
        """Decisión I y postcondición a: período, precio inicial, mecanismo con su porcentaje y sus meses, y los cuatro datos de la cláusula del
        suministrante (el prototipo no dejaba cambiar el mecanismo ni la tolerancia)."""
        self.modificar(
            self.cambios(
                self.mod(
                    periodo="14", precio="200,50", mecanismo="ajuste_periodico", porcentaje="5", meses="3", plazo_entrega="4",
                    indemnizacion_retraso="7", cantidad_minima="5", indemnizacion_faltante="9",
                )
            )
        )
        (s,) = DetalleSuministro.objects.filter(reemplaza_a=self.d)
        self.assertEqual(
            (s.periodo_entrega_dias, s.precio_unitario_suministro, s.mecanismo_precio, s.porcentaje_ajuste, s.meses_ajuste, s.fecha_base_ajuste),
            (14, Decimal("200.50"), "ajuste_periodico", Decimal("5.00"), 3, en(17)),
        )
        c = ClausulaSuministrante.objects.get(detalle=s)
        self.assertEqual(
            (c.plazo_entrega_dias, c.indemnizacion_retraso_entrega, c.cantidad_minima, c.indemnizacion_faltante),
            (4, Decimal("7.00"), 5, Decimal("9.00")),
        )

    def test_regla_precio_con_ajuste_el_sucesor_cuenta_los_meses_desde_su_primera_entrega(self):
        """Regla «Precio con ajuste periódico en el detalle nuevo»: sin indicar precio, el inicial del sucesor es el que tendría el actual ese día
        (ya ajustado) y los meses de ajuste se cuentan desde su primera entrega."""
        ajustado = suministro(self.e, fecha_realizacion=HOY - timedelta(days=200), duracion=12)
        d = detalle_suministro(
            ajustado, self.e.variedad, direccion=self.dir2, primera_en_dias=3, mecanismo="ajuste_periodico", precio="1000.00",
            porcentaje="10", meses=2, fecha_base_ajuste=HOY - timedelta(days=200),
        )
        esperado = calendario.precio_en(d, en(17))
        suministros.modificar_suministro(
            self.e.vendedor, ajustado.pk, self.cambios(self.mod(d, cantidad="30")), suministros.huella_de(ajustado)
        )
        (s,) = DetalleSuministro.objects.filter(reemplaza_a=d)
        self.assertEqual((s.precio_unitario_suministro, s.fecha_base_ajuste, s.meses_ajuste, s.porcentaje_ajuste), (esperado, en(17), 2, Decimal("10.00")))

    def test_regla_el_precio_indicado_gana_sobre_el_propuesto(self):
        """Paso 5: si la persona indica un precio inicial, el sucesor lo usa tal cual."""
        ajustado = suministro(self.e, fecha_realizacion=HOY - timedelta(days=200), duracion=12)
        d = detalle_suministro(
            ajustado, self.e.variedad, direccion=self.dir2, primera_en_dias=3, mecanismo="ajuste_periodico", precio="1000.00",
            porcentaje="10", meses=2, fecha_base_ajuste=HOY - timedelta(days=200),
        )
        suministros.modificar_suministro(
            self.e.vendedor, ajustado.pk, self.cambios(self.mod(d, precio="900")), suministros.huella_de(ajustado)
        )
        (s,) = DetalleSuministro.objects.filter(reemplaza_a=d)
        self.assertEqual(s.precio_unitario_suministro, Decimal("900.00"))

    def test_garantia_lo_ya_reservado_no_cambia_y_las_reservas_siguen_con_el_detalle_anterior(self):
        """Garantía mínima 2 y regla «Detalle sucesor»: las reservas y sus líneas de los períodos de la ventana siguen asociadas al detalle
        anterior; el sucesor no tiene ninguna (rige desde el día 17, fuera de la ventana); la cantidad de cada reserva no cambió."""
        antes = sorted(ReservaStock.objects.filter(detalle_suministro=self.d).values_list("pk", "fecha_entrega_reserva", "lineas__cantidad_reservada"))
        self.modificar(self.cambios(self.mod(cantidad="25")))
        (sucesor,) = DetalleSuministro.objects.filter(reemplaza_a=self.d)
        despues = sorted(ReservaStock.objects.filter(detalle_suministro=self.d).values_list("pk", "fecha_entrega_reserva", "lineas__cantidad_reservada"))
        self.assertEqual(antes, despues)
        self.assertEqual(len(antes), 2)
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=sucesor).count(), 0)

    def test_ext_5a_una_fecha_posterior_deja_los_periodos_intermedios_con_las_condiciones_actuales(self):
        """5a: eligiendo el día 31, los períodos de los días 17 y 24 siguen con el detalle actual (`fecha_fin_detalle` = día 24) y el sucesor
        arranca el día 31."""
        self.modificar(self.cambios(self.mod(cantidad="25", rige_desde=iso(31))))
        self.assertEqual(self.recargado(self.d).fecha_fin_detalle, en(24))
        (s,) = DetalleSuministro.objects.filter(reemplaza_a=self.d)
        self.assertEqual((s.fecha_primer_entrega, s.fecha_base_ajuste), (en(31), en(31)))
        self.assertEqual(calendario.calendario(self.recargado(self.d))[-2:], [en(17), en(24)])

    def test_ext_5a_la_fecha_tiene_que_ser_un_periodo_posterior_a_la_ventana(self):
        """5a: una fecha dentro de la ventana, anterior a ella, que no es un período del calendario o inexistente se rechaza con
        `rige_desde_invalido` en el campo de `rige_desde` del detalle."""
        for valor in (iso(10), iso(14), iso(18), iso(-3), "no es una fecha"):
            with self.subTest(valor=valor):
                error = self.rechazo(self.cambios(self.mod(cantidad="25", rige_desde=valor)))
                self.assertEqual(codigos_de(error, f"modificar-{self.d.pk}-rige_desde"), ["rige_desde_invalido"])
        self.assertEqual(DetalleSuministro.objects.count(), 1)

    def test_regla_un_detalle_marcado_modificar_sin_ningun_dato_distinto_se_rechaza(self):
        """7a para ese detalle: «Cambiá al menos un dato o elegí "Sin cambios".» (`detalle_sin_cambios`). Mandar los valores actuales tampoco
        es un cambio."""
        for extra in ({}, {"cantidad": "10", "periodo": "7", "precio": "100"}):
            with self.subTest(extra=extra):
                error = self.rechazo(self.cambios(self.mod(**extra)))
                self.assertEqual(codigos_de(error, f"modificar-{self.d.pk}-accion"), ["detalle_sin_cambios"])

    def test_regla_un_detalle_sin_cambios_se_ignora_aunque_traiga_datos(self):
        """Un detalle con `accion = sin_cambios` no se toca aunque el formulario traiga otros valores; el otro cambio sí se aplica."""
        otro = self.con_otro_detalle(primera_en_dias=4)
        self.modificar(self.cambios(self.mod(accion="sin_cambios", cantidad="99"), self.mod(otro, cantidad="30")))
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")
        self.assertEqual(self.recargado(otro).estado_detalle_suministro, "finalizado")

    def test_ext_6a_los_datos_invalidos_se_rechazan_por_campo_con_los_limites_de_pactar(self):
        """6a: mismos límites que COM-PCT-SUM, en el campo `modificar-<id>-<campo>`."""
        casos = [
            ("cantidad", "0", "cantidad_invalida"), ("cantidad", "500001", "cantidad_invalida"), ("periodo", "0", "periodo_invalido"),
            ("periodo", "366", "periodo_invalido"), ("precio", "0", "precio_invalido"), ("precio", "10.000.000", "precio_invalido"),
            ("mecanismo", "raro", "mecanismo_invalido"), ("plazo_entrega", "366", "plazo_entrega_invalido"),
            ("indemnizacion_retraso", "-1", "indemnizacion_retraso_invalida"), ("indemnizacion_faltante", "abc", "indemnizacion_faltante_invalida"),
            ("cantidad_minima", "11", "cantidad_minima_invalida"),  # supera la cantidad por período (10)
        ]
        for campo, valor, codigo in casos:
            with self.subTest(campo=campo, valor=valor):
                error = self.rechazo(self.cambios(self.mod(**{campo: valor})))
                self.assertIn(codigo, codigos_de(error, f"modificar-{self.d.pk}-{campo}"))
        self.assertEqual(DetalleSuministro.objects.count(), 1)

    def test_ext_6a_el_ajuste_periodico_exige_porcentaje_y_meses(self):
        """6a: pasar a ajuste periódico sin porcentaje o sin meses válidos se rechaza (`porcentaje_invalido`, `meses_invalidos`)."""
        error = self.rechazo(self.cambios(self.mod(mecanismo="ajuste_periodico")))
        self.assertEqual(codigos_de(error, f"modificar-{self.d.pk}-porcentaje"), ["porcentaje_invalido"])
        self.assertEqual(codigos_de(error, f"modificar-{self.d.pk}-meses"), ["meses_invalidos"])

    def test_regla_bajar_la_cantidad_por_debajo_de_la_minima_de_la_clausula_se_rechaza(self):
        """Ficha de ClausulaSuministrante: la cantidad mínima no puede superar la cantidad por período; con minima 8, bajar a 5 es
        `cantidad_minima_invalida` (se mira la mínima que quedaría)."""
        ClausulaSuministrante.objects.filter(detalle=self.d).update(cantidad_minima=8)
        error = self.rechazo(self.cambios(self.mod(cantidad="5")))
        self.assertEqual(codigos_de(error, f"modificar-{self.d.pk}-cantidad_minima"), ["cantidad_minima_invalida"])


class TerminarDetalleTests(BaseDeModificacion):
    """Postcondición c y extensión 5c: terminar un detalle."""

    def test_post_c_terminar_un_detalle_lo_finaliza_en_su_ultimo_periodo_de_la_ventana_sin_multa(self):
        """Postcondición c: «finalizado» con `fecha_fin_detalle` = su último período dentro de la ventana (día 10), sin sucesor; sin multa ni
        incumplimiento. El contrato sigue «vigente» (le quedan períodos por entregar)."""
        self.modificar(self.cambios(self.mod(accion="terminar")))
        d = self.recargado(self.d)
        self.assertEqual((d.estado_detalle_suministro, d.fecha_fin_detalle), ("finalizado", en(10)))
        self.assertFalse(DetalleSuministro.objects.filter(reemplaza_a=d).exists())
        s = self.recargado(self.s)
        self.assertEqual((s.estado_suministro, s.cantidad_incumplimientos, s.multa_resolucion), ("vigente", 0, Decimal("50000.00")))

    def test_post_c_sin_periodos_en_la_ventana_la_fecha_de_fin_es_la_de_la_ventana(self):
        """Regla «Fecha de fin»: un detalle que empieza fuera de la ventana y se termina queda «finalizado» con `fecha_fin_detalle` = hoy + 14."""
        otro = self.con_otro_detalle(primera_en_dias=30)
        self.modificar(self.cambios(self.mod(otro, "terminar")))
        o = self.recargado(otro)
        self.assertEqual((o.estado_detalle_suministro, o.fecha_fin_detalle), ("finalizado", en(14)))
        self.assertEqual(calendario.calendario(o), [])

    def test_post_c_terminar_los_detalles_sin_periodos_pendientes_finaliza_el_contrato(self):
        """Estado del contrato al terminar todo: si ningún detalle queda vigente y ninguno tiene períodos desde hoy, el contrato pasa a
        «finalizado» en la misma transacción (regla 5 de 8.11)."""
        solo = suministro(self.e)
        d = detalle_suministro(solo, self.e.variedad, direccion=self.dir2, primera_en_dias=30)
        suministros.modificar_suministro(self.e.vendedor, solo.pk, self.cambios(self.mod(d, "terminar")), suministros.huella_de(solo))
        self.assertEqual(self.recargado(solo).estado_suministro, "finalizado")

    def test_post_c_con_periodos_por_entregar_el_contrato_sigue_vigente(self):
        """Estado del contrato: si todavía tiene períodos por entregar (los de la ventana), sigue «vigente» (lo finaliza COM-06 al concretar el
        último, disparador «Cuando exista Entrega»)."""
        self.modificar(self.cambios(self.mod(accion="terminar")))
        self.assertEqual(self.recargado(self.s).estado_suministro, "vigente")

    def test_regla_terminar_y_acortar_no_aplican_multa_ni_incumplimiento(self):
        """Terminación por mutuo acuerdo: ni terminar un detalle ni acortar la duración tocan la multa ni los incumplimientos."""
        self.con_otro_detalle(primera_en_dias=4)
        self.modificar(self.cambios(self.mod(accion="terminar"), duracion="2"))
        s = self.recargado(self.s)
        self.assertEqual((s.cantidad_incumplimientos, s.multa_resolucion, s.estado_suministro), (0, Decimal("50000.00"), "vigente"))

    def test_regla_un_par_terminado_se_puede_volver_a_agregar_despues(self):
        """Par (variedad, dirección): los finalizados no cuentan. Terminado el detalle, otra modificación puede agregar un detalle con el mismo par."""
        self.modificar(self.cambios(self.mod(accion="terminar")))
        self.modificar(self.cambios(nuevos=[self.nuevo(direccion_id=str(self.d.direccion_id), primera_entrega=iso(20))]))
        self.assertEqual(DetalleSuministro.objects.filter(suministro=self.s, estado_detalle_suministro="vigente").count(), 1)


class ContratoTests(BaseDeModificacion):
    """Postcondiciones d, e, f y g y sus extensiones."""

    def test_post_d_extender_la_duracion_actualiza_la_fecha_de_fin(self):
        """Postcondición d: la duración y la fecha de fin del contrato se actualizan (`sumar_meses` desde la fecha de realización)."""
        self.modificar(self.cambios(duracion="8"))
        s = self.recargado(self.s)
        self.assertEqual((s.duracion_meses, s.fecha_fin), (8, calendario.sumar_meses(self.s.fecha_realizacion, 8)))
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")

    def test_ext_5d_acortar_la_duracion_actualiza_la_fecha_de_fin_si_no_toca_la_ventana(self):
        """5d.2: acortar a 3 meses (fin ~día 90) conserva los períodos de la ventana; el detalle sigue vigente con períodos después de la ventana."""
        self.modificar(self.cambios(duracion="3"))
        s = self.recargado(self.s)
        self.assertEqual((s.duracion_meses, s.fecha_fin), (3, calendario.sumar_meses(HOY, 3)))
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")

    def test_ext_5d_la_nueva_fecha_de_fin_no_puede_ser_anterior_al_ultimo_periodo_de_la_ventana(self):
        """5d.2: con un contrato pactado hace 100 días, acortarlo a 3 meses deja el fin hace 10 días, antes del período del día 10 (reservado):
        `fin_anterior_a_la_ventana` con la fecha más cercana posible en el mensaje; no cambia nada."""
        viejo = suministro(self.e, fecha_realizacion=HOY - timedelta(days=100), duracion=6)
        d = detalle_suministro(viejo, self.e.variedad, direccion=self.dir2, primera_en_dias=3)
        with self.assertRaises(ValidationError) as contexto:
            suministros.modificar_suministro(self.e.vendedor, viejo.pk, self.cambios(duracion="3"), suministros.huella_de(viejo))
        error = contexto.exception
        self.assertEqual(codigos_de(error, "duracion"), ["fin_anterior_a_la_ventana"])
        self.assertIn(f"{en(10):%d/%m/%Y}", error.error_dict["duracion"][0].message)
        self.assertEqual(self.recargado(viejo).duracion_meses, 6)
        self.assertEqual(self.recargado(d).estado_detalle_suministro, "vigente")

    def test_ext_5d_acortar_la_duracion_finaliza_el_detalle_que_se_queda_sin_periodos(self):
        """Decisión de aplicación del lote C3 (validada el 21/11/2026): un detalle vigente que con la nueva fecha de fin se queda sin períodos
        posteriores a la ventana pasa a «finalizado» con `fecha_fin_detalle` = su último período (y el resumen lo muestra); el otro, que sí
        tiene, sigue vigente."""
        largo = self.con_otro_detalle(primera_en_dias=5, periodo=60)  # períodos a los 5 y a los 65 días
        s = self.modificar(self.cambios(duracion="1"))  # fin a ~30 días: al de 60 días no le queda ninguno posterior a la ventana
        self.assertEqual(self.recargado(self.s).duracion_meses, 1)
        l = self.recargado(largo)
        self.assertEqual((l.estado_detalle_suministro, l.fecha_fin_detalle), ("finalizado", en(5)))
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")
        self.assertEqual([x.pk for x in s.detalles_finalizados], [largo.pk])

    def test_ext_5d_el_detalle_sin_ningun_periodo_hasta_la_nueva_fecha_de_fin_se_finaliza_con_ella(self):
        """Decisión de aplicación (criterio 5 aprobado el 24/11/2026): un detalle vigente que con la nueva fecha de fin no tiene ningún período
        (ni dentro de la ventana: su primera entrega cae después del nuevo fin) pasa a «finalizado» con `fecha_fin_detalle` = la nueva fecha de
        fin del contrato; su calendario queda vacío. El otro detalle sigue vigente."""
        lejano = self.con_otro_detalle(primera_en_dias=60, periodo=30)
        self.modificar(self.cambios(duracion="1"))
        l = self.recargado(lejano)
        self.assertEqual((l.estado_detalle_suministro, l.fecha_fin_detalle), ("finalizado", calendario.sumar_meses(HOY, 1)))
        self.assertEqual(calendario.calendario(l), [])
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")

    def test_ext_5d_el_resumen_muestra_el_detalle_que_se_queda_sin_periodos(self):
        """El resumen (paso 8) lista el detalle que pasa a «finalizado» por acortar la duración."""
        self.con_otro_detalle(primera_en_dias=5, periodo=60)
        resumen = suministros.resumen_de_modificacion(self.e.vendedor, self.s.pk, self.cambios(duracion="1"), self.huella())
        self.assertTrue(any("finaliz" in c.texto.lower() for c in resumen.cambios))

    def test_ext_5d_la_duracion_va_de_1_a_120_meses(self):
        """6a y regla «Datos del contrato»: de 1 a 120; `duracion_invalida` en otro caso."""
        for valor in ("0", "121", "x"):
            with self.subTest(valor=valor):
                self.assertEqual(codigos_de(self.rechazo(self.cambios(duracion=valor)), "duracion"), ["duracion_invalida"])

    def test_post_e_cambia_los_tolerados_y_la_multa(self):
        """Postcondición e: se actualizan los incumplimientos tolerados y la multa por resolución."""
        self.modificar(self.cambios(tolerados="5", multa="1.500,50"))
        s = self.recargado(self.s)
        self.assertEqual((s.incumplimientos_tolerados, s.multa_resolucion), (5, Decimal("1500.50")))

    def test_ext_5e_los_tolerados_iguales_a_los_acumulados_se_aceptan(self):
        """PCU 16 y 5e: con 2 incumplimientos acumulados, 2 tolerados se acepta (el contrato se resuelve cuando los acumulados **superan** los
        tolerados). Con 0 tolerados y 0 acumulados también."""
        Suministro.objects.filter(pk=self.s.pk).update(cantidad_incumplimientos=2)
        self.modificar(self.cambios(tolerados="2"))
        self.assertEqual(self.recargado(self.s).incumplimientos_tolerados, 2)
        Suministro.objects.filter(pk=self.s.pk).update(cantidad_incumplimientos=0)
        self.modificar(self.cambios(tolerados="0"))
        self.assertEqual(self.recargado(self.s).incumplimientos_tolerados, 0)

    def test_ext_5e_los_tolerados_menores_a_los_acumulados_se_rechazan(self):
        """5e: con 2 acumulados, 1 tolerado es `tolerados_menores_que_acumulados` («No puede ser menor que los 2 incumplimientos ya
        acumulados.»); fuera de 0 a 99, `tolerados_invalidos`."""
        Suministro.objects.filter(pk=self.s.pk).update(cantidad_incumplimientos=2)
        error = self.rechazo(self.cambios(tolerados="1"))
        self.assertEqual(codigos_de(error, "tolerados"), ["tolerados_menores_que_acumulados"])
        self.assertIn("2 incumplimientos", error.error_dict["tolerados"][0].message)
        for valor in ("100", "-1", "x"):
            with self.subTest(valor=valor):
                self.assertEqual(codigos_de(self.rechazo(self.cambios(tolerados=valor)), "tolerados"), ["tolerados_invalidos"])
        self.assertEqual(self.recargado(self.s).incumplimientos_tolerados, 3)

    def test_post_f_cambia_la_clausula_del_suministrado_sin_tocar_lo_demas(self):
        """Postcondición f y 5f: se actualiza la cláusula del suministrado (la fila, no una nueva); rige para las entregas que se concreten desde
        la confirmación."""
        antes = ClausulaSuministrado.objects.get(suministro=self.s).pk
        self.modificar(self.cambios(plazo_pago="30", indemnizacion_pago="250"))
        c = ClausulaSuministrado.objects.get(suministro=self.s)
        self.assertEqual((c.pk, c.plazo_pago_dias, c.indemnizacion_retraso_pago), (antes, 30, Decimal("250.00")))
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")

    def test_ext_6a_la_clausula_del_suministrado_y_la_multa_se_validan(self):
        """6a: plazo de pago de 0 a 365, indemnización y multa con sus topes."""
        casos = [("plazo_pago", "366", "plazo_pago_invalido"), ("indemnizacion_pago", "10.000.000", "indemnizacion_pago_invalida"), ("multa", "x", "multa_invalida")]
        for campo, valor, codigo in casos:
            with self.subTest(campo=campo):
                self.assertEqual(codigos_de(self.rechazo(self.cambios(**{campo: valor})), campo), [codigo])

    def test_post_g_el_gerente_cambia_el_vendedor_responsable(self):
        """Postcondición g y 1a.2: el contrato pasa al Vendedor nuevo (activo, con un invernadero activo). Lo ya reservado no se mueve (D-60)."""
        nuevo = crear_vendedor(email="nuevo@infoponia.com")
        segundo = segundo_invernadero(self.e, "Invernadero Nuevo")
        Invernadero.objects.filter(pk=segundo.invernadero.pk).update(vendedor=nuevo)
        reservas = sorted(ReservaStock.objects.values_list("pk", "invernadero_id"))
        self.modificar(self.cambios(vendedor_id=str(nuevo.pk)), actor=self.gerente)
        self.assertEqual(self.recargado(self.s).vendedor_id, nuevo.pk)
        self.assertEqual(sorted(ReservaStock.objects.values_list("pk", "invernadero_id")), reservas)

    def test_ext_1a_el_vendedor_nuevo_tiene_que_estar_activo_y_con_invernadero_activo(self):
        """1a.2: un Vendedor inexistente, de otro rol, sin invernaderos activos o dado de baja es `vendedor_invalido`."""
        sin_invernaderos = crear_vendedor(email="sin@infoponia.com")
        for valor in ("999999", "abc", str(self.e.agronomo.pk), str(sin_invernaderos.pk)):
            with self.subTest(valor=valor):
                error = self.rechazo(self.cambios(vendedor_id=valor), actor=self.gerente)
                self.assertEqual(codigos_de(error, "vendedor"), ["vendedor_invalido"])
        self.assertEqual(self.recargado(self.s).vendedor_id, self.e.vendedor.pk)

    def test_ext_1a_solo_el_gerente_cambia_el_vendedor(self):
        """Regla «Quién modifica»: el Vendedor responsable lo cambia solo el Gerente; un Vendedor que lo manda recibe `PermissionDenied` y no
        cambia nada. Mandar el Vendedor actual no es un cambio."""
        nuevo = crear_vendedor(email="nuevo@infoponia.com")
        with self.assertRaises(PermissionDenied):
            self.modificar(self.cambios(vendedor_id=str(nuevo.pk)))
        self.assertEqual(self.recargado(self.s).vendedor_id, self.e.vendedor.pk)
        error = self.rechazo(self.cambios(vendedor_id=str(self.e.vendedor.pk)))
        self.assertEqual(todos_los_codigos(error), ["sin_cambios"])


class DetalleNuevoTests(BaseDeModificacion):
    """Extensión 5b: agregar un detalle."""

    def test_post_b_agrega_un_detalle_vigente_con_su_clausula_y_reserva_los_periodos_de_la_ventana(self):
        """Postcondición b: detalle «vigente» con su cláusula del suministrante, `fecha_base_ajuste` = su primera entrega (decisión validada del lote C3),
        sin `reemplaza_a`; sus períodos dentro de la ventana (los días 5 y 12) quedan reservados con PROD-ASG-STK (con su cosecha)."""
        s = self.modificar(self.cambios(nuevos=[self.nuevo()]))
        (n,) = [d for d in DetalleSuministro.objects.filter(suministro=self.s) if d.pk != self.d.pk]
        self.assertEqual(
            (n.estado_detalle_suministro, n.reemplaza_a_id, n.direccion_id, n.cantidad_por_periodo, n.fecha_primer_entrega, n.fecha_base_ajuste),
            ("vigente", None, self.dir2.pk, 20, en(5), en(5)),
        )
        self.assertTrue(ClausulaSuministrante.objects.filter(detalle=n).exists())
        reservas = ReservaStock.objects.filter(detalle_suministro=n)
        self.assertEqual(sorted(r.fecha_entrega_reserva for r in reservas), [en(5), en(12)])
        self.assertTrue(all(r.cosecha_id is not None for r in reservas))
        self.assertEqual([x.pk for x in s.detalles_creados], [n.pk])
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")

    def test_post_b_sin_periodos_en_la_ventana_no_reserva_nada(self):
        """Postcondición b: si la primera entrega cae fuera de la ventana, se crea el detalle y no se reserva nada (lo hace la pre-reserva)."""
        self.modificar(self.cambios(nuevos=[self.nuevo(primera_entrega=iso(30))]))
        self.assertEqual(ReservaStock.objects.exclude(detalle_suministro=self.d).count(), 0)

    def test_ext_5b_2_el_par_de_un_detalle_vigente_se_rechaza_y_propone_modificarlo(self):
        """5b.2: la misma variedad y dirección de un detalle vigente del contrato es `par_vigente` en el campo `detalle-<i>-variedad`; el mensaje
        propone modificar ese detalle."""
        error = self.rechazo(self.cambios(nuevos=[self.nuevo(direccion_id=str(self.d.direccion_id))]))
        self.assertEqual(codigos_de(error, "detalle-0-variedad"), ["par_vigente"])
        self.assertIn("modific", error.error_dict["detalle-0-variedad"][0].message.lower())
        self.assertEqual(DetalleSuministro.objects.count(), 1)

    def test_ext_5b_2_dos_detalles_nuevos_con_el_mismo_par_se_rechazan(self):
        """9c aplicado a los nuevos: dos renglones nuevos con el mismo par son `par_repetido`."""
        error = self.rechazo(self.cambios(nuevos=[self.nuevo(0), self.nuevo(1)]))
        self.assertEqual(codigos_de(error, "detalle-1-variedad"), ["par_repetido"])

    def test_ext_5b_2_la_superposicion_con_otro_contrato_advierte_y_pide_continuar(self):
        """5b.2 y 9d: si el par coincide con un detalle vigente de OTRO contrato del cliente, advierte sin bloquear; sin la casilla «Continuar
        igual», es `superposicion_sin_confirmar` en `detalle-<i>-continuar`; con ella, se agrega."""
        otro = suministro(self.e)
        detalle_suministro(otro, self.e.variedad, direccion=self.dir2, primera_en_dias=30)
        error = self.rechazo(self.cambios(nuevos=[self.nuevo()]))
        self.assertEqual(codigos_de(error, "detalle-0-continuar"), ["superposicion_sin_confirmar"])
        self.modificar(self.cambios(nuevos=[self.nuevo(continuar_superpuesto="1")]))
        self.assertEqual(DetalleSuministro.objects.filter(suministro=self.s).count(), 2)

    def test_ext_5b_3_si_no_alcanza_el_stock_de_la_ventana_se_informa_y_no_se_registra_nada(self):
        """5b.3 y 9e: con 200 plantas libres menos las 20 reservadas, un detalle nuevo de 500 por período es `supera_disponible` en
        `detalle-<i>-cantidad`; no se crea nada."""
        error = self.rechazo(self.cambios(nuevos=[self.nuevo(cantidad="500", cantidad_minima="1")]))
        self.assertEqual(codigos_de(error, "detalle-0-cantidad"), ["supera_disponible"])
        self.assertEqual((DetalleSuministro.objects.count(), RegistroAuditoria.objects.filter(accion="modificacion_suministro").count()), (1, 0))

    def test_ext_5b_3_los_periodos_se_verifican_acumulados_con_el_resto_de_los_detalles_nuevos(self):
        """9e: dos detalles nuevos de la misma variedad se verifican uno contra lo que deja el otro (cada período contra el acumulado)."""
        dir3 = direccion_de_cliente(self.e.cliente).direccion
        error = self.rechazo(
            self.cambios(
                nuevos=[
                    self.nuevo(0, cantidad="100", cantidad_minima="1"),
                    self.nuevo(1, direccion_id=str(dir3.pk), cantidad="100", cantidad_minima="1"),
                ]
            )
        )
        self.assertTrue(
            codigos_de(error, "detalle-0-cantidad") == ["supera_disponible"] or codigos_de(error, "detalle-1-cantidad") == ["supera_disponible"]
        )

    def test_ext_5b_1_los_datos_del_detalle_nuevo_siguen_las_reglas_de_pactar(self):
        """5b.1 y 6a: variedad, dirección (activa del cliente), cantidad, período, primera entrega (entre hoy y la fecha de fin) y cláusula,
        con los códigos de COM-PCT-SUM."""
        casos = [
            ("cantidad", "0", "cantidad_invalida"), ("periodo", "0", "periodo_invalido"), ("precio", "0", "precio_invalido"),
            ("primera_entrega", iso(-1), "fecha_fuera_de_rango"), ("primera_entrega", iso(400), "fecha_fuera_de_rango"),
            ("direccion_id", "999999", "direccion_no_valida"), ("variedad_id", "", "variedad_obligatoria"),
        ]
        for campo, valor, codigo in casos:
            with self.subTest(campo=campo):
                error = self.rechazo(self.cambios(nuevos=[self.nuevo(**{campo: valor})]))
                self.assertIn(codigo, todos_los_codigos(error))

    def test_post_b_el_precio_con_ajuste_del_detalle_nuevo_cuenta_desde_su_primera_entrega(self):
        """Regla «Precio con ajuste periódico en el detalle nuevo»: los meses de ajuste se cuentan desde la primera entrega del detalle nuevo."""
        self.modificar(self.cambios(nuevos=[self.nuevo(mecanismo="ajuste_periodico", porcentaje="4", meses="2", primera_entrega=iso(30))]))
        n = DetalleSuministro.objects.exclude(pk=self.d.pk).get(suministro=self.s)
        self.assertEqual((n.fecha_base_ajuste, n.porcentaje_ajuste, n.meses_ajuste), (en(30), Decimal("4.00"), 2))


class ConfirmacionTests(BaseDeModificacion):
    """Pasos 10 a 12 y sus extensiones."""

    def test_ext_7a_sin_ningun_cambio_se_informa_y_no_se_registra_nada(self):
        """7a: sin ningún cambio, `sin_cambios` (`__all__`) y nada se escribe. Los valores iguales a los actuales tampoco son un cambio."""
        for cambios in (self.cambios(), self.cambios(tolerados="3", multa="50000", duracion="6", plazo_pago="15", indemnizacion_pago="100")):
            with self.subTest():
                self.assertEqual(codigos_de(self.rechazo(cambios), "__all__"), ["sin_cambios"])
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_suministro").exists())

    def test_ext_10a_si_un_periodo_entro_en_la_ventana_no_se_registra_nada(self):
        """10a: entre la lectura (la propuesta era el día 17) y la confirmación pasaron 3 días: la ventana llega al día 17 y la propuesta pasa a
        ser el día 24. `ventana_cambio` (`__all__`), no se registra ningún cambio ni aviso ni auditoría; el detalle sigue vigente."""
        huella = self.huella()
        cambios = self.cambios(self.mod(cantidad="25", rige_visto=iso(17)))
        with self.hoy_mas(3):
            error = self.rechazo(cambios, huella=huella)
        self.assertEqual(codigos_de(error, "__all__"), ["ventana_cambio"])
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")
        self.assertEqual(DetalleSuministro.objects.count(), 1)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_suministro").exists())
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_ext_10a_con_la_misma_propuesta_la_modificacion_se_registra(self):
        """10a (contraprueba): si la propuesta que vio la persona sigue siendo la de hoy, no hay `ventana_cambio`."""
        self.modificar(self.cambios(self.mod(cantidad="25", rige_visto=iso(17))))
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "finalizado")

    def test_ext_10b_si_la_huella_cambio_no_se_registra_nada(self):
        """10b: otra operación cambió el contrato después de abrir la pantalla: `contrato_cambio` («El contrato cambió mientras lo modificabas
        (por ejemplo, se resolvió o lo modificó otra persona). Volvé a abrirlo.») y no se registra nada."""
        huella = self.huella()
        Suministro.objects.filter(pk=self.s.pk).update(incumplimientos_tolerados=9)
        error = self.rechazo(self.cambios(self.mod(cantidad="25")), huella=huella)
        self.assertEqual(codigos_de(error, "__all__"), ["contrato_cambio"])
        self.assertIn("El contrato cambió mientras lo modificabas", error.error_dict["__all__"][0].message)
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_suministro").exists())

    def test_ext_10b_un_contrato_que_ya_no_esta_vigente_no_se_modifica(self):
        """10b: un contrato resuelto, finalizado o rescindido entre la lectura y la confirmación es `contrato_cambio`, aunque la huella se haya
        leído después."""
        for estado in ("finalizado",):
            with self.subTest(estado=estado):
                Suministro.objects.filter(pk=self.s.pk).update(estado_suministro=estado)
                error = self.rechazo(self.cambios(self.mod(cantidad="25")))
                self.assertEqual(codigos_de(error, "__all__"), ["contrato_cambio"])
                Suministro.objects.filter(pk=self.s.pk).update(estado_suministro="vigente")

    def test_ext_10b_con_otra_modificacion_anterior_la_huella_vieja_se_rechaza(self):
        """10b: dos modificaciones con la misma huella: la primera se registra y la segunda recibe `contrato_cambio` (cambiaron los detalles
        vigentes)."""
        huella = self.huella()
        self.modificar(self.cambios(self.mod(cantidad="25")), huella=huella)
        error = self.rechazo(self.cambios(tolerados="5"), huella=huella)
        self.assertEqual(codigos_de(error, "__all__"), ["contrato_cambio"])
        self.assertEqual(self.recargado(self.s).incumplimientos_tolerados, 3)

    def test_regla_un_contrato_con_rescision_acordada_no_se_modifica(self):
        """Precondición nueva (COM-RSC-SUM): con una rescisión acordada, `rescision_acordada` («Tiene una rescisión acordada: dejala sin efecto
        para modificarlo.»); no se registra nada."""
        Suministro.objects.filter(pk=self.s.pk).update(
            motivo_rescision="otro", descripcion_rescision="x", fecha_acuerdo_rescision=HOY, fecha_registro_rescision=HOY,
            fecha_ultima_entrega_rescision=en(10),
        )
        error = self.rechazo(self.cambios(tolerados="5"))
        self.assertEqual(codigos_de(error, "__all__"), ["rescision_acordada"])
        self.assertIn("dejala sin efecto", error.error_dict["__all__"][0].message)

    def test_ext_10_si_el_stock_ya_no_alcanza_al_confirmar_se_revierte_todo(self):
        """Paso 10: lo que se veía ya no alcanza al confirmar (otro consumió el stock): `stock_insuficiente` y se revierte todo (detalles,
        reservas, cosechas, notificaciones y auditoría); el detalle que se iba a modificar sigue vigente."""
        falso = {self.e.variedad.pk: [suministros.stock_maduro.Cobertura(en(5), 500, 1000), suministros.stock_maduro.Cobertura(en(12), 500, 1000)]}
        with mock.patch.object(suministros.stock_maduro, "simular_varias", return_value=falso):
            error = self.rechazo(self.cambios(self.mod(cantidad="25"), nuevos=[self.nuevo(cantidad="500", cantidad_minima="1")]))
        self.assertIn("stock_insuficiente", todos_los_codigos(error))
        self.assertEqual((DetalleSuministro.objects.count(), ReservaStock.objects.count()), (1, 2))
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")
        self.assertEqual((RegistroAuditoria.objects.filter(accion="modificacion_suministro").count(), Notificacion.objects.count()), (0, 0))

    def test_regla_todos_los_cambios_o_ninguno_con_un_detalle_que_falla(self):
        """Garantía mínima 1: si un cambio es válido y otro no, no se registra ninguno."""
        error = self.rechazo(self.cambios(self.mod(cantidad="25"), tolerados="100"))
        self.assertEqual(codigos_de(error, "tolerados"), ["tolerados_invalidos"])
        self.assertEqual((self.recargado(self.d).estado_detalle_suministro, DetalleSuministro.objects.count()), ("vigente", 1))

    def test_regla_un_solo_modificar_aplica_varios_cambios_a_la_vez(self):
        """Pasos 5 a 9: varios cambios (un detalle modificado, otro terminado, uno agregado y datos del contrato) se aplican en una sola
        confirmación y un único registro de auditoría."""
        otro = self.con_otro_detalle(primera_en_dias=4)
        dir3 = direccion_de_cliente(self.e.cliente).direccion
        s = self.modificar(
            self.cambios(self.mod(cantidad="25"), self.mod(otro, "terminar"), nuevos=[self.nuevo(direccion_id=str(dir3.pk))], tolerados="4")
        )
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "finalizado")
        self.assertEqual(self.recargado(otro).estado_detalle_suministro, "finalizado")
        self.assertEqual(sorted(x.pk for x in s.detalles_finalizados), sorted([self.d.pk, otro.pk]))
        self.assertEqual(len(s.detalles_creados), 2)
        self.assertEqual(self.recargado(self.s).incumplimientos_tolerados, 4)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_suministro").count(), 1)


class PermisosTests(BaseDeModificacion):
    """Precondición a y regla «Quién modifica»."""

    def test_regla_quien_modifica_el_vendedor_del_contrato_y_el_gerente(self):
        """Regla «Quién modifica» y 1a: el Vendedor del contrato y el Gerente."""
        self.modificar(self.cambios(tolerados="4"), actor=self.e.vendedor)
        self.modificar(self.cambios(tolerados="5"), actor=self.gerente)
        self.assertEqual(self.recargado(self.s).incumplimientos_tolerados, 5)

    def test_regla_un_vendedor_no_modifica_un_contrato_ajeno(self):
        """Alcance por usuario (D-28): otro Vendedor recibe `PermissionDenied` en las tres funciones; no cambia nada."""
        ajeno = crear_vendedor(email="ajeno@infoponia.com")
        for llamada in (
            lambda: suministros.datos_de_modificacion(ajeno, self.s.pk, self.cambios()),
            lambda: suministros.resumen_de_modificacion(ajeno, self.s.pk, self.cambios(tolerados="5"), self.huella()),
            lambda: suministros.modificar_suministro(ajeno, self.s.pk, self.cambios(tolerados="5"), self.huella()),
        ):
            with self.subTest(), self.assertRaises(PermissionDenied):
                llamada()
        self.assertEqual(self.recargado(self.s).incumplimientos_tolerados, 3)

    def test_regla_otros_roles_y_cuentas_inactivas_reciben_permission_denied(self):
        """Precondición a: un Agrónomo, o un Vendedor dado de baja, no modifica."""
        with self.assertRaises(PermissionDenied):
            self.modificar(self.cambios(tolerados="5"), actor=self.e.agronomo)
        baja = crear_vendedor(email="baja@infoponia.com")
        baja.is_active = False
        baja.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            self.modificar(self.cambios(tolerados="5"), actor=baja)

    def test_regla_un_suministro_inexistente_es_404(self):
        """Un id que no existe es `Http404`."""
        with self.assertRaises(Http404):
            suministros.modificar_suministro(self.e.vendedor, 999999, self.cambios(tolerados="5"), "x")


class EfectosTests(BaseDeModificacion):
    """Postcondiciones h, i y j: comprobante, avisos y auditoría."""

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_h_el_comprobante_modificado_sale_al_cliente_con_cada_cambio(self):
        """Postcondición h y paso 11: se envía el comprobante del contrato modificado (asunto «Modificación de tu suministro SUM-…», con la lista de
        cambios y la fecha desde la que rige cada uno); `estado_comprobante = enviado`."""
        with mock.patch(CORREO, return_value=True) as enviar:
            s = self.modificar(self.cambios(self.mod(cantidad="25")))
        cuenta, asunto, plantilla, contexto = enviar.call_args.args
        self.assertEqual((cuenta.email, asunto), (self.e.cliente.email_cliente, f"Modificación de tu suministro {s.codigo}"))
        self.assertEqual(plantilla, "comercial/correos/comprobante_suministro.txt")
        self.assertEqual(contexto["tipo"], "modificacion")
        self.assertIn(en(17), [c.rige_desde for c in contexto["cambios"]])
        self.assertEqual(self.recargado(self.s).estado_comprobante, "enviado")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_requisito_el_correo_sale_fuera_de_la_transaccion(self):
        """D-14 y criterio de COM-02: el correo se manda después de confirmar, nunca con los bloqueos tomados."""
        from django.db import connection

        base = len(connection.savepoint_ids)

        def enviar(*args):
            self.assertEqual(len(connection.savepoint_ids), base)
            return True

        with mock.patch(CORREO, side_effect=enviar) as simulado:
            self.modificar(self.cambios(self.mod(cantidad="25")))
        simulado.assert_called_once()

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_11a_si_el_correo_falla_la_modificacion_queda_registrada_con_el_comprobante_pendiente(self):
        """11a: la modificación permanece registrada; `pendiente_envio` (el reintento es manual, «Reenviar comprobante»). Si modificó el Gerente,
        el Vendedor recibe además «El comprobante de SUM-… quedó pendiente de envío.»."""
        with mock.patch(CORREO, return_value=False):
            s = self.modificar(self.cambios(self.mod(cantidad="25")), actor=self.gerente)
        self.assertEqual(self.recargado(self.s).estado_comprobante, "pendiente_envio")
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "finalizado")
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor, titulo="Comprobante pendiente de envío")
        self.assertEqual(aviso.detalle, f"El comprobante de {s.codigo} quedó pendiente de envío.")

    def test_regla_un_cliente_sin_correo_deja_el_comprobante_para_imprimir(self):
        """Variación 16b aplicada: sin correo del cliente, `para_imprimir`; la modificación se registra igual."""
        from comercial.models import Cliente

        Cliente.objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        self.modificar(self.cambios(tolerados="5"))
        self.assertEqual(self.recargado(self.s).estado_comprobante, "para_imprimir")

    def test_regla_una_modificacion_rechazada_no_manda_ningun_correo(self):
        """Garantía mínima: rechazada, no sale el comprobante."""
        with override_settings(CORREO_CONFIGURADO=True), mock.patch(CORREO) as enviar:
            self.rechazo(self.cambios(tolerados="100"))
        enviar.assert_not_called()

    def test_post_i_si_modifico_el_gerente_el_vendedor_recibe_el_aviso(self):
        """Postcondición i: si actuó el Gerente, se notifica al Vendedor («El Gerente modificó SUM-…: …»)."""
        s = self.modificar(self.cambios(tolerados="5"), actor=self.gerente)
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor, detalle__startswith="El Gerente modificó")
        self.assertIn(s.codigo, aviso.detalle)

    def test_post_i_si_modifico_el_vendedor_nadie_recibe_el_aviso_del_gerente(self):
        """Postcondición i: el aviso es solo cuando actuó el Gerente (el Vendedor sabe lo que hizo)."""
        self.modificar(self.cambios(tolerados="5"))
        self.assertFalse(Notificacion.objects.filter(detalle__startswith="El Gerente modificó").exists())

    def test_post_i_si_cambio_el_vendedor_se_avisa_al_anterior_y_al_nuevo(self):
        """Postcondición i: al anterior «SUM-… pasó a {nuevo}.» y al nuevo «Quedó a cargo de SUM-…, de {cliente}.»; dentro de la transacción
        (D-42)."""
        nuevo = crear_vendedor(email="nuevo@infoponia.com")
        segundo = segundo_invernadero(self.e, "Invernadero Nuevo")
        Invernadero.objects.filter(pk=segundo.invernadero.pk).update(vendedor=nuevo)
        s = self.modificar(self.cambios(vendedor_id=str(nuevo.pk)), actor=self.gerente)
        anterior = Notificacion.objects.filter(destinatario=self.e.vendedor, detalle__contains="pasó a")
        entrante = Notificacion.objects.filter(destinatario=nuevo, detalle__contains="Quedó a cargo de")
        self.assertEqual((anterior.count(), entrante.count()), (1, 1))
        self.assertIn(s.codigo, anterior.get().detalle)
        self.assertIn(s.codigo, entrante.get().detalle)
        self.assertIn(str(self.e.cliente), entrante.get().detalle)

    def test_post_j_un_registro_de_auditoria_con_los_cambios_y_los_detalles(self):
        """Postcondición j y D-36: UN registro `modificacion_suministro` con el usuario y los afectados: el suministro (primero), el detalle
        finalizado y el creado con sus cláusulas; los cambios del contrato con su antes y su después."""
        s = self.modificar(self.cambios(self.mod(cantidad="25"), tolerados="5"), actor=self.gerente)
        (registro,) = RegistroAuditoria.objects.filter(accion="modificacion_suministro")
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.afectados[0]["texto"], s.codigo)
        ids = {(a["modelo"], a["id"]) for a in registro.afectados}
        (sucesor,) = DetalleSuministro.objects.filter(reemplaza_a=self.d)
        self.assertIn(("comercial.detallesuministro", self.d.pk), ids)
        self.assertIn(("comercial.detallesuministro", sucesor.pk), ids)
        self.assertIn(("comercial.clausulasuministrante", ClausulaSuministrante.objects.get(detalle=sucesor).pk), ids)
        self.assertEqual(registro.detalle["cambios"]["incumplimientos_tolerados"], {"antes": "3", "despues": "5"})

    def test_post_j_los_detalles_nuevos_con_reservas_van_entre_los_afectados(self):
        """Postcondición j: lo que reservó `asignar` para un detalle agregado (reservas, líneas y cosechas) va entre los afectados."""
        self.modificar(self.cambios(nuevos=[self.nuevo()]))
        (registro,) = RegistroAuditoria.objects.filter(accion="modificacion_suministro")
        modelos = {a["modelo"] for a in registro.afectados}
        self.assertTrue({"comercial.reservastock", "comercial.detallereserva", "produccion.cosecha"} <= modelos)

    def test_regla_una_modificacion_rechazada_no_deja_auditoria_ni_avisos(self):
        """Garantía mínima 1: rechazada, no queda registro ni notificación."""
        self.rechazo(self.cambios(tolerados="100"), actor=self.gerente)
        self.assertEqual((RegistroAuditoria.objects.filter(accion="modificacion_suministro").count(), Notificacion.objects.count()), (0, 0))
