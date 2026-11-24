# Pruebas de COM-RSC-SUM, Rescindir Suministro (COM-03b, paso 5; docs/casos_de_uso/comercial/suministro.md, «COM-RSC-SUM» y «COM-RSC-SUM y COM-ANL-RSC»): `datos_de_rescision`,
# `rescindir_suministro` y el cierre diario `cerrar_rescisiones` (paso 35). Una prueba por regla, postcondición y extensión (2a, 4a, 6a, 6b, 7a y 7b). Las que
# escriben verifican al final los invariantes de reservas y de suministros. La concurrencia está en `test_suministros_concurrencia.py` y COM-ANL-RSC en
# `test_com_anl_rsc.py`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), todo en `comercial/servicios/suministros.py`:
#   - `PedidoDeRescision(motivo, descripcion, fecha_acuerdo, acuerdo)`: lo que carga la ventana, todo texto. `motivo` es `a_pedido_del_cliente`,
#     `a_pedido_de_la_empresa` u `otro`; `fecha_acuerdo`, `aaaa-mm-dd` o `dd/mm/aaaa`; `acuerdo`, «1» si el Gerente marcó «Confirmo que la rescisión se acordó con
#     el cliente». Con `PedidoDeRescision.desde_post(datos)` (claves `motivo`, `descripcion`, `fecha_acuerdo`, `acuerdo`).
#   - `periodos_conservados(suministro, hoy) -> list[(id del detalle, fecha)]`: los períodos de los detalles vigentes con fecha entre hoy y hoy + días de
#     pre-reserva, por fecha y, con la misma fecha, por id del detalle.
#   - `datos_de_rescision(actor, suministro_id) -> DatosDeRescision` (solo lectura: no escribe ni bloquea) con `suministro`, `hoy`, `ventana`, `huella` (la de
#     COM-MOD-SUM), `conservados` (lo de arriba), `fecha_ultima_entrega` (la mayor, o `None`) y `rescinde_en_el_acto` (2a: no hay períodos conservados). Solo el
#     Gerente (`PermissionDenied`); un contrato que no está vigente es `contrato_cambio` y uno con rescisión acordada, `rescision_acordada` (`ValidationError`).
#   - `rescindir_suministro(actor, suministro_id, pedido, huella, conservados) -> Suministro`: ``conservados`` son los de `datos_de_rescision` (6a); ``None``
#     no los compara.
#   - Errores: `ValidationError` por campo. Campos: `motivo`, `descripcion`, `fecha_acuerdo`, `acuerdo` y `__all__`. Códigos: `motivo_obligatorio`, `motivo_invalido`,
#     `descripcion_obligatoria` (con «otro»), `descripcion_larga` (más de 500), `fecha_obligatoria`, `fecha_invalida`, `fecha_futura`, `acuerdo_sin_confirmar`,
#     `ventana_cambio` (6a), `contrato_cambio` (6b: no vigente o huella distinta), `rescision_acordada` (6b: ya tiene una).
#   - Cuando no hay períodos conservados (2a) el contrato queda «rescindido» en el acto con `fecha_ultima_entrega_rescision` = `fecha_rescision` = hoy (la
#     restricción de la base exige la fecha: decisión de aplicación del 24/11/2026).
#   - `cerrar_rescisiones(hoy) -> ResumenDePaso(procesados=N, creados=0, resueltos=N, detalle="N suministros rescindidos")` (paso diario 35, «Cerrar rescisiones de
#     suministros»), un contrato por transacción, idempotente.
#   - Comprobante: `enviar_comprobante(contrato, tipo="rescision")` (asunto «Rescisión de tu suministro SUM-…»); «Reenviar» deduce el tipo del estado (con una
#     rescisión acordada o rescindido, la constancia de la rescisión).

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from io import StringIO

from comercial.models import Cliente, DetalleSuministro, ReservaStock, Suministro
from comercial.servicios import calendario, comprobantes, suministros
from comercial.tests.fabricas import (
    detalle_suministro,
    direccion_de_cliente,
    escenario_comercial,
    partida,
    reserva_de_periodo,
    suministro,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_suministros,
)
from core.models import ROL_INFOPONIA, Notificacion, RegistroAuditoria
from core.procesos import ResumenDePaso, pasos_diarios
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
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


class BaseDeRescision(ConDatosDeInventario, TestCase):
    """Un contrato de 6 meses con un detalle de 10 plantas cada 7 días (períodos a los 3, 10, 17… días; la ventana de 14 días cubre los dos primeros, que están
    reservados) y otra dirección del cliente."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 200)
        self.gerente = crear_gerente()
        self.s = suministro(self.e, duracion=6, tolerados=3, incumplimientos=1)
        self.d = detalle_suministro(self.s, self.e.variedad, cantidad=10, periodo=7, primera_en_dias=3)
        reserva_de_periodo(self.d, en(3), [(self.lote, 10)])
        reserva_de_periodo(self.d, en(10), [(self.lote, 10)])
        self.dir2 = direccion_de_cliente(self.e.cliente).direccion
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_suministros)

    def pedido(self, **extra):
        """Un pedido válido: a pedido del cliente, acordado ayer, con la casilla marcada."""
        valores = dict(motivo="a_pedido_del_cliente", descripcion="", fecha_acuerdo=iso(-1), acuerdo="1")
        valores.update(extra)
        return suministros.PedidoDeRescision(**valores)

    def lectura(self, s=None):
        """Lo que ve el Gerente al abrir la ventana."""
        return suministros.datos_de_rescision(self.gerente, (s or self.s).pk)

    def rescindir(self, pedido=None, actor=None, s=None, **forzar):
        """Rescinde ``s`` (por defecto, el contrato) como ``actor`` (por defecto, el Gerente) con lo que leyó la ventana; ``forzar`` pisa la huella o los
        conservados."""
        if "huella" in forzar and "conservados" in forzar:  # lo que vio la ventana antes: no se vuelve a leer (el contrato pudo cambiar)
            huella, conservados = forzar["huella"], forzar["conservados"]
        else:
            lectura = self.lectura(s)
            huella, conservados = forzar.get("huella", lectura.huella), forzar.get("conservados", lectura.conservados)
        return suministros.rescindir_suministro(actor or self.gerente, (s or self.s).pk, pedido or self.pedido(), huella, conservados)

    def rechazo(self, pedido=None, actor=None, **forzar):
        """Rescinde esperando una ``ValidationError`` y la devuelve."""
        with self.assertRaises(ValidationError) as contexto:
            self.rescindir(pedido, actor, **forzar)
        return contexto.exception

    def hoy_mas(self, dias):
        """Mueve «hoy» ``dias`` días hacia adelante (la fecha que lee el servicio)."""
        return mock.patch("inventario.servicios.stock.hoy", return_value=HOY + timedelta(days=dias))

    def otro_detalle(self, **extra):
        """Un segundo detalle vigente del contrato (en la otra dirección)."""
        return detalle_suministro(self.s, self.e.variedad, direccion=self.dir2, **extra)

    def recargado(self, objeto):
        return type(objeto).objects.get(pk=objeto.pk)


class LecturaTests(BaseDeRescision):
    """Pasos 1 y 2: lo que presenta la ventana, sin escribir."""

    def test_regla_periodos_que_se_conservan_son_los_de_la_ventana_con_detalles_de_distinto_periodo(self):
        """Regla «Períodos que se conservan»: los de los detalles vigentes con fecha entre hoy y hoy + 14. Con un segundo detalle cada 20 días desde el día 5,
        son (por fecha y, con la misma, por detalle): el día 3 y el 10 del primero y el 5 del segundo; la última entrega es la del día 10."""
        otro = self.otro_detalle(periodo=20, primera_en_dias=5)
        lectura = self.lectura()
        self.assertEqual(lectura.conservados, [(self.d.pk, en(3)), (otro.pk, en(5)), (self.d.pk, en(10))])
        self.assertEqual((lectura.fecha_ultima_entrega, lectura.rescinde_en_el_acto, lectura.ventana), (en(10), False, en(14)))
        self.assertEqual(lectura.huella, suministros.huella_de(self.recargado(self.s)))

    def test_regla_no_cuenta_periodos_pasados_ni_detalles_finalizados(self):
        """Los períodos anteriores a hoy no se conservan (no hay nada que entregar) y un detalle finalizado no aporta."""
        propio = suministro(self.e)
        d = detalle_suministro(propio, self.e.variedad, direccion=self.dir2, primera_en_dias=-5)  # períodos a los -5, 2, 9 y 16 días
        finalizado = detalle_suministro(propio, self.e.variedad, primera_en_dias=4, estado="finalizado", fecha_fin_detalle=en(11))
        self.assertEqual(self.lectura(propio).conservados, [(d.pk, en(2)), (d.pk, en(9))])
        self.assertNotIn(finalizado.pk, [x for x, _ in self.lectura(propio).conservados])

    def test_ext_2a_sin_periodos_dentro_de_la_ventana_se_rescinde_en_el_acto(self):
        """Extensión 2a: sin períodos conservados, `rescinde_en_el_acto` (el contrato queda rescindido al confirmar) y no hay última entrega."""
        solo = suministro(self.e)
        detalle_suministro(solo, self.e.variedad, direccion=self.dir2, primera_en_dias=30)
        lectura = self.lectura(solo)
        self.assertEqual((lectura.conservados, lectura.fecha_ultima_entrega, lectura.rescinde_en_el_acto), ([], None, True))

    def test_regla_la_lectura_no_escribe_nada(self):
        """Paso 2: abrir la ventana no cambia nada (ni el contrato, ni los detalles, ni auditoría ni avisos)."""
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        self.lectura()
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)
        self.assertIsNone(self.recargado(self.s).motivo_rescision)

    def test_regla_solo_el_gerente_abre_la_ventana(self):
        """Regla «Quién rescinde»: el Vendedor del contrato y los demás roles reciben `PermissionDenied`."""
        for actor in (self.e.vendedor, self.e.agronomo):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                suministros.datos_de_rescision(actor, self.s.pk)

    def test_ext_6b_un_contrato_que_no_esta_vigente_o_ya_rescindido_no_se_abre(self):
        """6b: un contrato no vigente es `contrato_cambio`; uno que ya tiene una rescisión acordada, `rescision_acordada`."""
        Suministro.objects.filter(pk=self.s.pk).update(estado_suministro="finalizado")
        with self.assertRaises(ValidationError) as contexto:
            self.lectura()
        self.assertEqual(codigos_de(contexto.exception, "__all__"), ["contrato_cambio"])
        Suministro.objects.filter(pk=self.s.pk).update(
            estado_suministro="vigente", motivo_rescision="otro", descripcion_rescision="x", fecha_acuerdo_rescision=HOY,
            fecha_registro_rescision=HOY, fecha_ultima_entrega_rescision=en(10),
        )
        with self.assertRaises(ValidationError) as contexto:
            self.lectura()
        self.assertEqual(codigos_de(contexto.exception, "__all__"), ["rescision_acordada"])

    def test_regla_desde_post_arma_el_pedido(self):
        """`PedidoDeRescision.desde_post` lee `motivo`, `descripcion`, `fecha_acuerdo` y `acuerdo`."""
        pedido = suministros.PedidoDeRescision.desde_post(
            {"motivo": "otro", "descripcion": "Se mudó", "fecha_acuerdo": iso(-2), "acuerdo": "1", "cliente": "9"}
        )
        self.assertEqual((pedido.motivo, pedido.descripcion, pedido.fecha_acuerdo, pedido.acuerdo), ("otro", "Se mudó", iso(-2), "1"))


class FlujoPrincipalTests(BaseDeRescision):
    """Postcondiciones a a d y g del flujo principal."""

    def test_post_a_el_suministro_queda_con_la_rescision_acordada_y_sigue_vigente(self):
        """Postcondición a: motivo, descripción, fecha del acuerdo, fecha del registro (hoy) y fecha de la última entrega conservada (día 10); sigue «vigente»
        y todavía no tiene fecha de rescisión."""
        s = self.rescindir(self.pedido(motivo="otro", descripcion="Cierra el vivero", fecha_acuerdo=iso(-3)))
        r = self.recargado(self.s)
        self.assertEqual(
            (r.estado_suministro, r.motivo_rescision, r.descripcion_rescision, r.fecha_acuerdo_rescision, r.fecha_registro_rescision,
             r.fecha_ultima_entrega_rescision, r.fecha_rescision),
            ("vigente", "otro", "Cierra el vivero", en(-3), HOY, en(10), None),
        )
        self.assertTrue(r.tiene_rescision_acordada)
        self.assertEqual(s.pk, self.s.pk)

    def test_post_b_cada_detalle_vigente_queda_con_su_fecha_de_fin_en_su_ultimo_periodo_de_la_ventana(self):
        """Postcondición b: el primer detalle termina el día 10 y el segundo (cada 20 días desde el día 5) el día 5; los períodos posteriores no se
        entregan: el calendario de cada uno corta ahí. Los dos siguen «vigentes»."""
        otro = self.otro_detalle(periodo=20, primera_en_dias=5)
        self.rescindir()
        d, o = self.recargado(self.d), self.recargado(otro)
        self.assertEqual((d.fecha_fin_detalle, o.fecha_fin_detalle), (en(10), en(5)))
        self.assertEqual((d.estado_detalle_suministro, o.estado_detalle_suministro), ("vigente", "vigente"))
        self.assertEqual(calendario.calendario(d)[-1], en(10))
        self.assertEqual(calendario.calendario(o), [en(5)])

    def test_post_b_un_detalle_sin_periodos_en_la_ventana_termina_en_el_ultimo_dia_de_la_ventana(self):
        """Regla «Fecha de fin de cada detalle»: sin ningún período dentro de la ventana, su fecha de fin es la de la ventana (hoy + 14) y queda sin períodos."""
        lejano = self.otro_detalle(primera_en_dias=30)
        self.rescindir()
        l = self.recargado(lejano)
        self.assertEqual(l.fecha_fin_detalle, en(14))
        self.assertEqual(calendario.calendario(l), [])

    def test_post_b_un_detalle_finalizado_antes_no_se_toca(self):
        """Postcondición b: solo los detalles «vigentes»; uno ya finalizado (por una modificación) conserva su fecha de fin."""
        finalizado = self.otro_detalle(primera_en_dias=4, estado="finalizado", fecha_fin_detalle=en(11))
        self.rescindir()
        self.assertEqual(self.recargado(finalizado).fecha_fin_detalle, en(11))

    def test_post_d_sin_multa_ni_incumplimiento(self):
        """Postcondición d y regla «Sin multa ni incumplimiento»: no cambia la multa, ni la cantidad de incumplimientos, ni los tolerados."""
        self.rescindir()
        r = self.recargado(self.s)
        self.assertEqual((r.multa_resolucion, r.cantidad_incumplimientos, r.incumplimientos_tolerados), (Decimal("50000.00"), 1, 3))

    def test_garantia_lo_ya_reservado_no_cambia(self):
        """Garantía mínima 2: las reservas de los períodos de la ventana siguen igual."""
        antes = sorted(ReservaStock.objects.filter(detalle_suministro=self.d).values_list("pk", "fecha_entrega_reserva", "estado_reserva", "lineas__cantidad_reservada"))
        self.rescindir()
        despues = sorted(ReservaStock.objects.filter(detalle_suministro=self.d).values_list("pk", "fecha_entrega_reserva", "estado_reserva", "lineas__cantidad_reservada"))
        self.assertEqual(antes, despues)

    def test_ext_2a_sin_periodos_conservados_el_contrato_queda_rescindido_en_el_acto(self):
        """Postcondición c y extensión 2a: sin períodos por entregar, el suministro pasa a «rescindido» con `fecha_rescision` = hoy (y la última entrega, hoy)
        y sus detalles vigentes a «finalizado», en la misma operación."""
        solo = suministro(self.e)
        d = detalle_suministro(solo, self.e.variedad, direccion=self.dir2, primera_en_dias=30)
        self.rescindir(s=solo)
        r = self.recargado(solo)
        self.assertEqual((r.estado_suministro, r.fecha_rescision, r.fecha_ultima_entrega_rescision, r.fecha_registro_rescision), ("rescindido", HOY, HOY, HOY))
        self.assertEqual(
            (self.recargado(d).estado_detalle_suministro, self.recargado(d).fecha_fin_detalle), ("finalizado", en(14))
        )
        self.assertFalse(r.tiene_rescision_acordada)  # ya no es una rescisión «acordada vigente»: está cerrada

    def test_regla_con_periodos_conservados_el_contrato_sigue_vigente_hasta_la_ultima_entrega(self):
        """Regla «Mientras se entregan los períodos conservados»: sigue «vigente»; el cierre lo hace el paso diario 35."""
        self.rescindir()
        self.assertEqual(self.recargado(self.s).estado_suministro, "vigente")
        self.assertIsNone(self.recargado(self.s).fecha_rescision)

    def test_regla_no_se_puede_volver_a_rescindir_ni_modificar_mientras_dura(self):
        """Regla «Mientras se entregan…»: no se puede volver a rescindir (`rescision_acordada`) ni modificar (`rescision_acordada`, COM-MOD-SUM)."""
        self.rescindir()
        self.assertEqual(codigos_de(self.rechazo(huella=suministros.huella_de(self.recargado(self.s)), conservados=None), "__all__"), ["rescision_acordada"])
        with self.assertRaises(ValidationError) as contexto:
            suministros.modificar_suministro(
                self.e.vendedor, self.s.pk, suministros.CambiosDeSuministro(tolerados="5"), suministros.huella_de(self.recargado(self.s))
            )
        self.assertEqual(codigos_de(contexto.exception, "__all__"), ["rescision_acordada"])

    def test_regla_la_pre_reserva_no_toma_periodos_posteriores_a_la_rescision(self):
        """Regla «Fecha de fin de cada detalle»: con la rescisión registrada, la pre-reserva de dentro de 7 días (ventana hasta el día 21) no reserva el
        período del día 17: el calendario del detalle corta en el día 10."""
        from comercial.servicios import pre_reserva

        partida(self.lote, disponible=100, fecha_limite=en(60))
        self.rescindir()
        pre_reserva.pre_reservar_suministros(en(7))
        self.assertEqual(sorted({r.fecha_entrega_reserva for r in ReservaStock.objects.filter(detalle_suministro=self.d)}), [en(3), en(10)])

    def test_regla_cliente_inactivo_no_impide_rescindir(self):
        """Un contrato vigente de un cliente dado de baja se puede rescindir igual (regla 2 de 8.18: no se mira el estado del cliente)."""
        Cliente.objects.filter(pk=self.e.cliente.pk).update(estado_cliente="inactivo")
        self.rescindir()
        self.assertIsNotNone(self.recargado(self.s).motivo_rescision)


class ValidacionesTests(BaseDeRescision):
    """Paso 3 y extensión 4a, y quién rescinde."""

    def test_regla_solo_el_gerente_rescinde(self):
        """Regla «Quién rescinde»: el Vendedor del contrato y otros roles reciben `PermissionDenied`; no se registra nada."""
        lectura = self.lectura()
        for actor in (self.e.vendedor, self.e.agronomo, crear_vendedor(email="otro@infoponia.com")):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                suministros.rescindir_suministro(actor, self.s.pk, self.pedido(), lectura.huella, lectura.conservados)
        self.assertIsNone(self.recargado(self.s).motivo_rescision)

    def test_ext_4a_falta_el_motivo_o_no_es_de_la_lista(self):
        """4a: sin motivo, `motivo_obligatorio`; uno que no está en la lista cerrada, `motivo_invalido`."""
        self.assertEqual(codigos_de(self.rechazo(self.pedido(motivo="")), "motivo"), ["motivo_obligatorio"])
        self.assertEqual(codigos_de(self.rechazo(self.pedido(motivo="porque si")), "motivo"), ["motivo_invalido"])

    def test_ext_4a_el_motivo_otro_exige_descripcion_y_las_demas_no(self):
        """4a y regla «Motivo»: con «otro» la descripción es obligatoria (`descripcion_obligatoria`; en blanco no vale); con los otros dos es opcional.
        No pasa de 500 caracteres (`descripcion_larga`)."""
        self.assertEqual(codigos_de(self.rechazo(self.pedido(motivo="otro", descripcion="   ")), "descripcion"), ["descripcion_obligatoria"])
        self.assertEqual(codigos_de(self.rechazo(self.pedido(descripcion="x" * 501)), "descripcion"), ["descripcion_larga"])
        self.rescindir(self.pedido(motivo="a_pedido_de_la_empresa", descripcion=""))
        self.assertEqual(self.recargado(self.s).motivo_rescision, "a_pedido_de_la_empresa")

    def test_ext_4a_la_fecha_del_acuerdo_no_puede_ser_posterior_a_hoy(self):
        """4a y regla «Fecha del acuerdo»: igual o anterior a hoy; una futura es `fecha_futura`; sin fecha, `fecha_obligatoria`; ilegible, `fecha_invalida`.
        Hoy mismo se acepta."""
        self.assertEqual(codigos_de(self.rechazo(self.pedido(fecha_acuerdo=iso(1))), "fecha_acuerdo"), ["fecha_futura"])
        self.assertEqual(codigos_de(self.rechazo(self.pedido(fecha_acuerdo="")), "fecha_acuerdo"), ["fecha_obligatoria"])
        self.assertEqual(codigos_de(self.rechazo(self.pedido(fecha_acuerdo="ayer")), "fecha_acuerdo"), ["fecha_invalida"])
        self.rescindir(self.pedido(fecha_acuerdo=f"{HOY:%d/%m/%Y}"))
        self.assertEqual(self.recargado(self.s).fecha_acuerdo_rescision, HOY)

    def test_ext_4a_sin_confirmar_el_acuerdo_con_el_cliente_no_se_rescinde(self):
        """4a y regla «Rescisión por mutuo acuerdo»: sin la casilla, `acuerdo_sin_confirmar`; el sistema no deja registrar una rescisión unilateral."""
        for valor in ("", "0", "no"):
            with self.subTest(valor=valor):
                self.assertEqual(codigos_de(self.rechazo(self.pedido(acuerdo=valor)), "acuerdo"), ["acuerdo_sin_confirmar"])
        self.assertIsNone(self.recargado(self.s).motivo_rescision)

    def test_ext_4a_con_varios_errores_los_informa_todos_y_no_registra_nada(self):
        """4a: todos los errores del pedido juntos, por campo; nada se escribe (ni auditoría, ni avisos)."""
        error = self.rechazo(self.pedido(motivo="otro", descripcion="", fecha_acuerdo=iso(2), acuerdo=""))
        self.assertEqual(sorted(error.error_dict), ["acuerdo", "descripcion", "fecha_acuerdo"])
        self.assertEqual((RegistroAuditoria.objects.filter(accion="rescision_suministro").count(), Notificacion.objects.count()), (0, 0))


class ConcurrenciaEnLecturaTests(BaseDeRescision):
    """Extensiones 6a y 6b: lo que cambió entre la ventana y la confirmación."""

    def test_ext_6a_si_un_periodo_entro_en_la_ventana_no_se_registra_nada(self):
        """6a: la ventana mostró los períodos de los días 3 y 10; pasaron 3 días y ahora son los del 10 y el 17: `ventana_cambio`, no se registra nada y
        se vuelve a presentar lo que se conserva."""
        lectura = self.lectura()
        with self.hoy_mas(3):
            error = self.rechazo(huella=lectura.huella, conservados=lectura.conservados)
        self.assertEqual(codigos_de(error, "__all__"), ["ventana_cambio"])
        self.assertIsNone(self.recargado(self.s).motivo_rescision)
        self.assertEqual(self.recargado(self.d).fecha_fin_detalle, None)
        self.assertEqual((RegistroAuditoria.objects.filter(accion="rescision_suministro").count(), Notificacion.objects.count()), (0, 0))

    def test_ext_6a_sin_conservados_no_se_compara(self):
        """Si quien llama no manda lo que vio (`None`), no hay 6a: se rescinde con lo de ahora."""
        lectura = self.lectura()
        with self.hoy_mas(3):
            self.rescindir(huella=lectura.huella, conservados=None)
        self.assertEqual(self.recargado(self.s).fecha_ultima_entrega_rescision, en(17))

    def test_ext_6b_si_otra_operacion_cambio_el_contrato_no_se_registra_nada(self):
        """6b: la huella cambió (otra operación lo modificó): `contrato_cambio`, no se registra nada."""
        lectura = self.lectura()
        Suministro.objects.filter(pk=self.s.pk).update(incumplimientos_tolerados=9)
        error = self.rechazo(huella=lectura.huella, conservados=lectura.conservados)
        self.assertEqual(codigos_de(error, "__all__"), ["contrato_cambio"])
        self.assertIsNone(self.recargado(self.s).motivo_rescision)

    def test_ext_6b_si_ya_no_esta_vigente_no_se_registra_nada(self):
        """6b: un contrato resuelto, finalizado o rescindido mientras tanto es `contrato_cambio`."""
        lectura = self.lectura()
        Suministro.objects.filter(pk=self.s.pk).update(estado_suministro="finalizado")
        error = self.rechazo(huella=lectura.huella, conservados=lectura.conservados)
        self.assertEqual(codigos_de(error, "__all__"), ["contrato_cambio"])

    def test_ext_6b_si_otro_ya_registro_la_rescision_es_rescision_acordada(self):
        """6b: dos Gerentes (o dos pestañas) con la misma huella; la segunda recibe `rescision_acordada` y no cambia la primera."""
        lectura = self.lectura()
        self.rescindir(self.pedido(descripcion="primera"))
        error = self.rechazo(self.pedido(motivo="otro", descripcion="segunda"), huella=lectura.huella, conservados=lectura.conservados)
        self.assertEqual(codigos_de(error, "__all__"), ["rescision_acordada"])
        self.assertEqual(self.recargado(self.s).descripcion_rescision, "primera")

    def test_regla_si_el_stock_o_algo_falla_antes_de_confirmar_el_contrato_queda_como_estaba(self):
        """Garantía mínima 1: si la auditoría falla, no queda la rescisión (todo en una transacción)."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla de prueba")), self.assertRaises(RuntimeError):
            self.rescindir()
        self.assertIsNone(self.recargado(self.s).motivo_rescision)
        self.assertIsNone(self.recargado(self.d).fecha_fin_detalle)


class EfectosTests(BaseDeRescision):
    """Postcondiciones e, f y g: constancia, aviso y auditoría."""

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_e_la_constancia_sale_al_cliente(self):
        """Postcondición e y paso 7: se envía al cliente la constancia (asunto «Rescisión de tu suministro SUM-…»); `estado_comprobante = enviado`. Sale fuera
        de la transacción (D-14, D-54)."""
        base = len(connection.savepoint_ids)

        def enviar(*args):
            self.assertEqual(len(connection.savepoint_ids), base)
            return True

        with mock.patch(CORREO, side_effect=enviar) as simulado:
            s = self.rescindir()
        cuenta, asunto, plantilla, contexto = simulado.call_args.args
        self.assertEqual((cuenta.email, asunto), (self.e.cliente.email_cliente, f"Rescisión de tu suministro {s.codigo}"))
        self.assertEqual((plantilla, contexto["tipo"]), ("comercial/correos/comprobante_suministro.txt", "rescision"))
        self.assertEqual(self.recargado(self.s).estado_comprobante, "enviado")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_7a_si_el_correo_falla_la_rescision_queda_y_la_constancia_pendiente(self):
        """7a: la rescisión permanece registrada y la constancia queda «pendiente de envío», para reenviarla desde la ficha; el Vendedor recibe además
        «El comprobante de SUM-… quedó pendiente de envío.»."""
        with mock.patch(CORREO, return_value=False):
            s = self.rescindir()
        r = self.recargado(self.s)
        self.assertEqual((r.estado_comprobante, r.motivo_rescision is not None), ("pendiente_envio", True))
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor, titulo="Comprobante pendiente de envío")
        self.assertEqual(aviso.detalle, f"El comprobante de {s.codigo} quedó pendiente de envío.")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_7a_reenviar_manda_la_constancia_de_la_rescision(self):
        """7a: «Reenviar comprobante» de un contrato con rescisión acordada manda la constancia de la rescisión (no el comprobante de siempre)."""
        with mock.patch(CORREO, return_value=False):
            s = self.rescindir()
        with mock.patch(CORREO, return_value=True) as simulado:
            self.assertEqual(comprobantes.reenviar_comprobante(self.gerente, s.pk), "enviado")
        _, asunto, _, contexto = simulado.call_args.args
        self.assertEqual((asunto, contexto["tipo"]), (f"Rescisión de tu suministro {s.codigo}", "rescision"))

    def test_ext_7b_un_cliente_sin_correo_deja_la_constancia_para_imprimir(self):
        """7b: sin correo del cliente, la rescisión permanece registrada y la constancia queda «para imprimir»."""
        Cliente.objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        self.rescindir()
        r = self.recargado(self.s)
        self.assertEqual((r.estado_comprobante, r.motivo_rescision is not None), ("para_imprimir", True))

    def test_post_f_se_notifica_al_vendedor_con_la_fecha_de_la_ultima_entrega(self):
        """Postcondición f: «El Gerente registró la rescisión de SUM-… ({cliente}) por mutuo acuerdo. Se entrega hasta el dd/mm/aaaa.»"""
        s = self.rescindir()
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor, titulo="Rescisión de suministro")
        self.assertEqual(
            aviso.detalle,
            f"El Gerente registró la rescisión de {s.codigo} ({self.e.cliente}) por mutuo acuerdo. Se entrega hasta el {en(10):%d/%m/%Y}.",
        )

    def test_post_f_con_rescision_en_el_acto_el_aviso_dice_que_quedo_rescindido(self):
        """Postcondición f con 2a: sin entregas por delante, el aviso dice que el contrato quedó rescindido."""
        solo = suministro(self.e)
        detalle_suministro(solo, self.e.variedad, direccion=self.dir2, primera_en_dias=30)
        self.rescindir(s=solo)
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor, titulo="Rescisión de suministro")
        self.assertIn("quedó rescindido", aviso.detalle)

    def test_post_g_un_registro_de_auditoria_con_los_datos_de_la_rescision_y_las_fechas_de_cada_detalle(self):
        """Postcondición g y D-36: UN registro `rescision_suministro` del Gerente con el suministro (primero) y sus detalles entre los afectados; en `datos`, el
        motivo, la fecha del acuerdo, la última entrega y la fecha de fin de cada detalle."""
        s = self.rescindir(self.pedido(motivo="otro", descripcion="Cierra"))
        (registro,) = RegistroAuditoria.objects.filter(accion="rescision_suministro")
        self.assertEqual((registro.usuario_id, registro.afectados[0]["texto"]), (self.gerente.pk, s.codigo))
        self.assertIn(("comercial.detallesuministro", self.d.pk), {(a["modelo"], a["id"]) for a in registro.afectados})
        datos = registro.detalle["datos"]
        self.assertEqual((datos["motivo_rescision"], datos["descripcion_rescision"]), ("otro", "Cierra"))
        self.assertEqual((datos["fecha_acuerdo_rescision"], datos["fecha_ultima_entrega_rescision"]), (f"{en(-1):%d/%m/%Y}", f"{en(10):%d/%m/%Y}"))
        self.assertTrue(any(f"{en(10):%d/%m/%Y}" in linea for linea in datos["detalles"]))

    def test_regla_una_rescision_rechazada_no_deja_auditoria_ni_avisos_ni_correo(self):
        """Garantía mínima 1: rechazada, no queda registro, notificación ni correo."""
        with override_settings(CORREO_CONFIGURADO=True), mock.patch(CORREO) as enviar:
            self.rechazo(self.pedido(acuerdo=""))
        enviar.assert_not_called()
        self.assertEqual((RegistroAuditoria.objects.filter(accion="rescision_suministro").count(), Notificacion.objects.count()), (0, 0))


class CierreDiarioTests(BaseDeRescision):
    """Paso diario 35, `cerrar_rescisiones(hoy)` (regla «Cierre»)."""

    def cerrar(self, hoy):
        return suministros.cerrar_rescisiones(hoy)

    def test_regla_el_cierre_pasa_a_rescindido_el_dia_siguiente_a_la_ultima_entrega(self):
        """Regla «Cierre»: el día de la última entrega (10) el contrato sigue vigente; el día siguiente pasa a «rescindido» con `fecha_rescision` = la última
        entrega conservada, y sus detalles vigentes a «finalizado» (con la fecha de fin que ya tenían)."""
        self.rescindir()
        self.assertEqual(self.cerrar(en(10)), ResumenDePaso(0, 0, 0, "0 suministros rescindidos"))
        self.assertEqual(self.recargado(self.s).estado_suministro, "vigente")
        resumen = self.cerrar(en(11))
        r, d = self.recargado(self.s), self.recargado(self.d)
        self.assertEqual((r.estado_suministro, r.fecha_rescision), ("rescindido", en(10)))
        self.assertEqual((d.estado_detalle_suministro, d.fecha_fin_detalle), ("finalizado", en(10)))
        self.assertEqual(resumen, ResumenDePaso(procesados=1, creados=0, resueltos=1, detalle="1 suministros rescindidos"))

    def test_regla_el_cierre_es_idempotente(self):
        """D-56, punto 4: una segunda corrida no hace nada (ni auditoría nueva) y el contrato rescindido no vuelve a tocarse."""
        self.rescindir()
        self.cerrar(en(11))
        auditoria = RegistroAuditoria.objects.filter(accion="cierre_rescision").count()
        self.assertEqual(self.cerrar(en(11)).procesados, 0)
        self.assertEqual(self.cerrar(en(30)).procesados, 0)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cierre_rescision").count(), auditoria)

    def test_regla_el_cierre_audita_sin_usuario_con_origen_infoponia(self):
        """Auditoría: acción `cierre_rescision`, sin usuario (InfoPonia, D-27), con el suministro y sus detalles entre los afectados."""
        self.rescindir()
        self.cerrar(en(11))
        (registro,) = RegistroAuditoria.objects.filter(accion="cierre_rescision")
        self.assertEqual((registro.usuario_id, registro.rol, registro.afectados[0]["id"]), (None, ROL_INFOPONIA, self.s.pk))
        self.assertIn(("comercial.detallesuministro", self.d.pk), {(a["modelo"], a["id"]) for a in registro.afectados})

    def test_regla_solo_cierra_contratos_vigentes_con_rescision_acordada(self):
        """Un contrato vigente sin rescisión, uno ya finalizado y uno con la rescisión dejada sin efecto no se cierran."""
        sin_rescision = suministro(self.e)
        detalle_suministro(sin_rescision, self.e.variedad, direccion=self.dir2, primera_en_dias=3)
        self.assertEqual(self.cerrar(en(200)).procesados, 0)
        self.assertEqual(self.recargado(sin_rescision).estado_suministro, "vigente")

    def test_regla_cada_contrato_en_su_transaccion_y_uno_que_falla_no_corta_el_paso(self):
        """Contrato del paso (D-56, punto 5): si el cierre de un contrato falla, queda en el log y los demás se cierran."""
        otro = suministro(self.e)
        d = detalle_suministro(otro, self.e.variedad, direccion=self.dir2, primera_en_dias=3)
        reserva_de_periodo(d, en(3), [(self.lote, 10)])
        self.rescindir()
        self.rescindir(s=otro)
        real = RegistroAuditoria.objects.registrar

        def falla_en_el_primero(*args, **kwargs):
            if kwargs.get("accion") == "cierre_rescision" and kwargs["afectados"][0].pk == self.s.pk:
                raise RuntimeError("falla de prueba")
            return real(*args, **kwargs)

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=falla_en_el_primero), self.assertLogs(level="ERROR"):
            resumen = self.cerrar(en(11))
        self.assertEqual((self.recargado(self.s).estado_suministro, self.recargado(otro).estado_suministro), ("vigente", "rescindido"))
        self.assertEqual(resumen.procesados, 1)

    def test_regla_con_la_ultima_entrega_ya_pasada_en_el_registro_en_el_acto_no_hay_cierre_pendiente(self):
        """Con 2a el contrato ya quedó rescindido al registrar: el paso 35 no lo vuelve a procesar."""
        solo = suministro(self.e)
        detalle_suministro(solo, self.e.variedad, direccion=self.dir2, primera_en_dias=30)
        self.rescindir(s=solo)
        self.assertEqual(self.cerrar(en(60)).procesados, 0)


class RegistroDelPasoTests(BaseDeRescision):
    """Lo que `ComercialConfig.ready()` deja registrado (regla A4 de D-37)."""

    def test_regla_el_paso_35_esta_registrado_en_el_proceso_diario(self):
        """D-56, punto 6: «cerrar_rescisiones», «Cerrar rescisiones de suministros», orden 35, entre el 30 y el 40."""
        (paso,) = [p for p in pasos_diarios() if p.codigo == "cerrar_rescisiones"]
        self.assertEqual((paso.nombre, paso.orden, paso.funcion), ("Cerrar rescisiones de suministros", 35, suministros.cerrar_rescisiones))
        ordenes = [p.orden for p in pasos_diarios()]
        self.assertEqual(ordenes, sorted(ordenes))

    def test_regla_proceso_diario_listar_muestra_el_paso_35_y_el_40(self):
        """Criterio de la tarea: `proceso_diario --listar` muestra «35 · cerrar_rescisiones» y «40 · pre_reservar_suministros»."""
        salida = StringIO()
        call_command("proceso_diario", "--listar", stdout=salida)
        texto = salida.getvalue()
        self.assertIn("35 · cerrar_rescisiones · Cerrar rescisiones de suministros", texto)
        self.assertIn("40 · pre_reservar_suministros · Pre-reservar suministros", texto)
        self.assertLess(texto.index("35 · cerrar_rescisiones"), texto.index("40 · pre_reservar_suministros"))

    def test_regla_ready_dos_veces_no_duplica_el_paso(self):
        """`ready()` puede correr más de una vez."""
        apps.get_app_config("comercial").ready()
        self.assertEqual(len([p for p in pasos_diarios() if p.codigo == "cerrar_rescisiones"]), 1)

    def test_regla_correr_el_proceso_diario_cierra_la_rescision(self):
        """De punta a punta: `proceso_diario --fecha` el día siguiente a la última entrega cierra el contrato."""
        self.rescindir()
        salida = StringIO()
        call_command("proceso_diario", "--fecha", iso(11), "--solo", "cerrar_rescisiones", stdout=salida)
        self.assertEqual(self.recargado(self.s).estado_suministro, "rescindido")
