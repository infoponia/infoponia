# Pruebas del enlace del cliente (COM-04c, paso 2; docs/patrones/enlace_del_cliente.md, sección 8; D-65): `comercial/servicios/enlaces.py`. Crear, reemplazar, anular, encontrar por su
# token, decir si sirve, enviar el correo y vencer (paso diario 27). Las de la entrada pública (`/cliente/<token>/`, los encabezados y la sesión) están en `test_faltantes_vistas.py`;
# la concurrencia (dos envíos del mismo enlace), en `test_com_dcd_flt.py`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa):
#   - `crear_enlace(tipo, cliente, *, compra_venta, vence) -> (EnlaceCliente, token)`: dentro de la transacción (si no, `RuntimeError`); cliente sin correo, `ValueError`; reemplaza el
#     vigente de la venta; guarda solo el resumen SHA-256; el correo sale con `on_commit` (`enviar_enlace`), nunca si se revierte.
#   - `enviar_enlace(enlace_id, token)`: `estado_envio` = `enviado` o `pendiente_envio` (más el aviso al Vendedor); no envía si el enlace ya no está vigente.
#   - `anular_enlaces_de(venta)`: los vigentes a `anulado`; el `usado` no se toca. `reemplazar_enlaces_de(venta)`: los vigentes a `reemplazado`.
#   - `situacion_del_enlace(enlace, hoy=None)`: `sirve` o el motivo (`vencido`, `usado`, `reemplazado`, `anulado`, `venta_cancelada`, `sin_pendientes`); sirve todo el día del vencimiento.
#   - `avisar_enlaces_vencidos(hoy) -> ResumenDePaso` (paso 27): `vencido` + aviso al Vendedor + registro `vencimiento_enlace`; idempotente.

from datetime import timedelta
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from comercial.models import CompraVenta, DetalleVenta, EnlaceCliente
from comercial.servicios import enlaces
from comercial.tests.fabricas import (
    cliente,
    compra_venta,
    detalle,
    detalle_suministro,
    enlace as un_enlace,
    enlace_de_confirmacion,
    entrega,
    escenario_comercial,
    marcar_concretada,
    reserva_lista,
    suministro,
)
from core.models import Notificacion, RegistroAuditoria
from core.procesos import ResumenDePaso, pasos_diarios
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import ConfiguracionOperativa
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
Tipo = EnlaceCliente.Tipo


class Base(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.venta = compra_venta(self.e, estado="pendiente_decision")
        self.detalle = detalle(self.venta, self.e.variedad, 50, estado="pendiente_decision")
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(fecha_pendiente_decision=HOY)

    def crear(self, venta=None, vence=None):
        venta = venta or self.venta
        return enlaces.crear_enlace(Tipo.DECISION_FALTANTE, venta.cliente, compra_venta=venta, vence=vence or HOY + timedelta(days=2))


class CrearEnlaceTests(Base):
    def test_regla_el_token_no_esta_en_la_base_y_dos_tokens_seguidos_son_distintos(self):
        """D-65 punto 2 (patrón, sección 8): la base guarda solo el SHA-256 de 64 caracteres; el token no aparece en ninguna columna y dos enlaces seguidos tienen tokens distintos."""
        primero, token1 = self.crear()
        segundo, token2 = self.crear()
        self.assertNotEqual(token1, token2)
        for creado, token in ((primero, token1), (segundo, token2)):
            fila = EnlaceCliente.objects.filter(pk=creado.pk).values().get()
            self.assertEqual(len(fila["token_resumen"]), 64)
            self.assertNotIn(token, " ".join(str(v) for v in fila.values()))

    def test_regla_crear_reemplaza_al_enlace_vigente_de_la_venta(self):
        """Regla «Enlace de decisión» y D-65 punto 5: uno solo vigente por venta; el anterior pasa a `reemplazado`."""
        viejo, _ = un_enlace(self.venta)
        nuevo, _ = self.crear()
        viejo.refresh_from_db()
        self.assertEqual((viejo.estado, nuevo.estado), ("reemplazado", "vigente"))
        self.assertEqual(EnlaceCliente.objects.filter(compra_venta=self.venta, estado="vigente").count(), 1)

    def test_regla_un_cliente_sin_correo_no_tiene_enlace(self):
        """D-65 punto 1: sin correo no se crea enlace (lo decide el Vendedor, extensión 1a): `ValueError`."""
        sin_correo = cliente(email="")
        venta = compra_venta(self.e, cliente_=sin_correo, estado="pendiente_decision")
        with self.assertRaises(ValueError):
            enlaces.crear_enlace(Tipo.DECISION_FALTANTE, sin_correo, compra_venta=venta, vence=HOY)
        self.assertFalse(EnlaceCliente.objects.filter(compra_venta=venta).exists())

    def test_regla_sin_transaccion_lanza_runtime_error(self):
        """Corre en la transacción del caso de uso que la llama."""
        with mock.patch.object(transaction, "get_autocommit", return_value=True), self.assertRaises(RuntimeError):
            self.crear()

    def test_regla_un_rollback_del_caso_de_uso_no_envia_el_correo(self):
        """D-65 punto 6 (patrón, sección 8): si la transacción se revierte, el `on_commit` del correo se descarta."""
        with mock.patch("comercial.servicios.enlaces.enviar_enlace") as envio, self.captureOnCommitCallbacks(execute=True) as callbacks:
            try:
                with transaction.atomic():
                    self.crear()
                    raise RuntimeError("el caso de uso falla")
            except RuntimeError:
                pass
        self.assertEqual((callbacks, envio.call_count), ([], 0))
        self.assertFalse(EnlaceCliente.objects.exists())

    def test_regla_al_confirmar_se_registra_el_envio_del_correo(self):
        """D-65 punto 6: `crear_enlace` deja un solo `on_commit` que llama a `enviar_enlace` con el id y el token."""
        with mock.patch("comercial.servicios.enlaces.enviar_enlace") as envio, self.captureOnCommitCallbacks(execute=True) as callbacks:
            creado, token = self.crear()
        self.assertEqual(len(callbacks), 1)
        envio.assert_called_once_with(creado.pk, token)


@override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test")
class EnviarEnlaceTests(Base):
    def test_regla_con_el_correo_enviado_queda_enviado_con_la_url_con_el_token(self):
        """Patrón, sección 3: `enviar_correo` recibe la URL absoluta `https://<sitio>/cliente/<token>/`, las cantidades solicitada y disponible y el vencimiento; queda `enviado`."""
        creado, token = self.crear()
        with mock.patch("core.correo.enviar_correo", return_value=True) as envio:
            enlaces.enviar_enlace(creado.pk, token)
        creado.refresh_from_db()
        self.assertEqual(creado.estado_envio, "enviado")
        destinatario, asunto, plantilla, contexto = envio.call_args.args
        self.assertEqual((destinatario.email, plantilla), (self.venta.cliente.email_cliente, "comercial/correos/enlace_faltante.txt"))
        self.assertEqual(contexto["url"], f"https://sitio.test/cliente/{token}/")
        self.assertEqual(contexto["lineas"], [{"variedad": str(self.e.variedad), "solicitada": 50, "disponible": 0}])
        self.assertEqual(contexto["vence"], creado.fecha_vencimiento)
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_ext_un_correo_que_falla_deja_pendiente_de_envio_y_avisa_al_vendedor(self):
        """D-65 punto 6: `enviar_correo` devuelve `False` → `pendiente_envio` y una notificación al Vendedor para que registre él la decisión (extensión 1a)."""
        creado, token = self.crear()
        with mock.patch("core.correo.enviar_correo", return_value=False):
            enlaces.enviar_enlace(creado.pk, token)
        creado.refresh_from_db()
        self.assertEqual(creado.estado_envio, "pendiente_envio")
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor)
        self.assertIn(self.venta.codigo, aviso.titulo)
        self.assertIn("registrá vos la decisión", aviso.detalle)

    @override_settings(URL_DEL_SITIO="")
    def test_ext_sin_la_url_del_sitio_no_se_envia_y_queda_pendiente(self):
        """Sin `URL_DEL_SITIO` no se puede armar el enlace del correo: no se envía nada, `pendiente_envio` y aviso al Vendedor."""
        creado, token = self.crear()
        with mock.patch("core.correo.enviar_correo") as envio:
            enlaces.enviar_enlace(creado.pk, token)
        creado.refresh_from_db()
        self.assertEqual((creado.estado_envio, envio.call_count), ("pendiente_envio", 0))
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.vendedor).count(), 1)

    def test_ext_si_el_enlace_ya_no_esta_vigente_no_envia_nada(self):
        """Patrón, sección 3, punto 1: otra operación lo anuló entre el commit y el envío: no sale correo y el resultado queda sin cargar."""
        creado, token = self.crear()
        enlaces.anular_enlaces_de(self.venta)
        with mock.patch("core.correo.enviar_correo") as envio:
            enlaces.enviar_enlace(creado.pk, token)
        creado.refresh_from_db()
        self.assertEqual((creado.estado, creado.estado_envio, envio.call_count), ("anulado", None, 0))

    @override_settings(CORREO_CONFIGURADO=False)
    def test_ext_sin_el_correo_del_sistema_configurado_queda_pendiente(self):
        """Sin correo configurado (D-33) tampoco se envía: `pendiente_envio` y aviso al Vendedor."""
        creado, token = self.crear()
        with mock.patch("core.correo.enviar_correo") as envio:
            enlaces.enviar_enlace(creado.pk, token)
        creado.refresh_from_db()
        self.assertEqual((creado.estado_envio, envio.call_count), ("pendiente_envio", 0))


class AnularYReemplazarTests(Base):
    def test_regla_anular_pasa_a_anulado_los_vigentes_y_no_toca_al_usado(self):
        """Patrón, sección 6: `anular_enlaces_de` pasa a `anulado` los `vigente`; el `usado` es de quien ya decidió y no se toca."""
        usado, _ = un_enlace(self.venta, estado="usado")
        vigente, _ = un_enlace(self.venta)
        anulados = enlaces.anular_enlaces_de(self.venta)
        usado.refresh_from_db()
        vigente.refresh_from_db()
        self.assertEqual(([e.pk for e in anulados], usado.estado, vigente.estado), ([vigente.pk], "usado", "anulado"))

    def test_regla_reemplazar_pasa_a_reemplazado_el_vigente(self):
        """El camino sin correo (D-65 punto 1): el vigente, si lo había, queda `reemplazado` y no se crea otro."""
        vigente, _ = un_enlace(self.venta)
        enlaces.reemplazar_enlaces_de(self.venta)
        vigente.refresh_from_db()
        self.assertEqual(vigente.estado, "reemplazado")


class SituacionTests(Base):
    def test_regla_enlace_por_token_busca_por_el_resumen(self):
        """D-65 punto 4: se busca por el resumen del token; un token que no existe da `None`."""
        creado, token = un_enlace(self.venta)
        self.assertEqual(enlaces.enlace_por_token(token).pk, creado.pk)
        self.assertIsNone(enlaces.enlace_por_token("no-existe"))
        self.assertIsNone(enlaces.enlace_por_id(None))

    def test_regla_el_dia_del_vencimiento_sirve_y_el_siguiente_no(self):
        """D-65 punto 4 (patrón, sección 8): sirve hasta el final del día de `fecha_vencimiento`."""
        creado, _ = un_enlace(self.venta, vence=HOY + timedelta(days=2))
        self.assertEqual(enlaces.situacion_del_enlace(creado, HOY + timedelta(days=2)), enlaces.SIRVE)
        self.assertEqual(enlaces.situacion_del_enlace(creado, HOY + timedelta(days=3)), enlaces.VENCIDO)

    def test_ext_2a_cada_motivo_por_el_que_el_enlace_no_sirve(self):
        """Extensión 2a de COM-DCD-FLT: usado, reemplazado, anulado, vencido (por estado), venta cancelada y venta sin detalles pendientes."""
        for estado, esperado in (("usado", enlaces.USADO), ("reemplazado", enlaces.REEMPLAZADO), ("anulado", enlaces.ANULADO), ("vencido", enlaces.VENCIDO)):
            with self.subTest(estado=estado):
                creado, _ = un_enlace(self.venta, estado=estado)
                self.assertEqual(enlaces.situacion_del_enlace(creado, HOY), esperado)
        vigente, _ = un_enlace(self.venta)
        self.assertEqual(enlaces.situacion_del_enlace(vigente, HOY), enlaces.SIRVE)
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="abierto")
        self.assertEqual(enlaces.situacion_del_enlace(vigente, HOY), enlaces.SIN_PENDIENTES)
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="cancelada")
        self.assertEqual(enlaces.situacion_del_enlace(vigente, HOY), enlaces.VENTA_CANCELADA)


class VencerEnlacesTests(Base):
    def vencido(self, dias_atras=1):
        creado, _ = un_enlace(self.venta, vence=HOY - timedelta(days=dias_atras))
        return creado

    def test_regla_el_paso_27_esta_registrado_en_su_orden(self):
        """D-56 y D-65 punto 7: el paso «Avisar enlaces vencidos» corre con el orden 27 (entre el 25 y el 30)."""
        pasos = {p.codigo: p.orden for p in pasos_diarios()}
        self.assertEqual(pasos["avisar_enlaces_vencidos"], 27)

    def test_regla_vence_el_enlace_avisa_una_sola_vez_al_vendedor_y_audita(self):
        """Regla «Vencimiento sin respuesta»: `vencido`, UNA notificación al Vendedor y un registro `vencimiento_enlace` hecho por InfoPonia; los detalles siguen pendientes."""
        creado = self.vencido()
        resumen = enlaces.avisar_enlaces_vencidos(HOY)
        creado.refresh_from_db()
        self.detalle.refresh_from_db()
        self.assertIsInstance(resumen, ResumenDePaso)
        self.assertEqual((resumen.procesados, resumen.creados), (1, 1))
        self.assertEqual((creado.estado, self.detalle.estado_detalle_venta), ("vencido", "pendiente_decision"))
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor)
        self.assertIn("Venció el plazo del cliente", aviso.detalle)
        registro = RegistroAuditoria.objects.get(accion="vencimiento_enlace")
        self.assertEqual((registro.usuario, registro.rol), (None, "infoponia"))

    def test_regla_es_idempotente(self):
        """D-56 punto 4: un enlace `vencido` no se vuelve a tomar; el segundo corrido no avisa ni audita otra vez."""
        self.vencido()
        enlaces.avisar_enlaces_vencidos(HOY)
        segundo = enlaces.avisar_enlaces_vencidos(HOY)
        self.assertEqual((segundo.procesados, segundo.creados), (0, 0))
        self.assertEqual((Notificacion.objects.count(), RegistroAuditoria.objects.filter(accion="vencimiento_enlace").count()), (1, 1))

    def test_regla_el_dia_del_vencimiento_todavia_no_vence(self):
        """Sirve todo el día de `fecha_vencimiento`: el paso lo toma recién al día siguiente."""
        creado, _ = un_enlace(self.venta, vence=HOY)
        self.assertEqual(enlaces.avisar_enlaces_vencidos(HOY).procesados, 0)
        self.assertEqual(enlaces.avisar_enlaces_vencidos(HOY + timedelta(days=1)).procesados, 1)
        creado.refresh_from_db()
        self.assertEqual(creado.estado, "vencido")

    def test_regla_nunca_lee_la_fecha_por_su_cuenta(self):
        """D-56: con `--fecha` simula el paso del tiempo; un enlace que vence dentro de 2 días se toma con `hoy` de dentro de 3."""
        un_enlace(self.venta, vence=HOY + timedelta(days=2))
        self.assertEqual(enlaces.avisar_enlaces_vencidos(HOY).procesados, 0)
        self.assertEqual(enlaces.avisar_enlaces_vencidos(HOY + timedelta(days=3)).procesados, 1)

    def test_regla_un_enlace_usado_o_anulado_no_se_toma(self):
        """Solo los `vigente` vencen."""
        un_enlace(self.venta, estado="usado", vence=HOY - timedelta(days=3))
        un_enlace(self.venta, estado="anulado", vence=HOY - timedelta(days=3))
        self.assertEqual(enlaces.avisar_enlaces_vencidos(HOY).procesados, 0)


# ---- COM-06b: el enlace de confirmación de una entrega (patrón, sección 9; D-68 puntos 1 y 8) ----


def fijar_vigencia(dias):
    """Cambia el parámetro `dias_vigencia_enlace_confirmacion` de la configuración operativa (la fila única)."""
    configuracion = ConfiguracionOperativa.objects.get_or_create(singleton=1)[0]
    configuracion.dias_vigencia_enlace_confirmacion = dias
    configuracion.save()


class ConfirmacionDeEntregaBase(ConDatosDeInventario, TestCase):
    """Un suministro con una entrega concretada de hoy (directo en la base)."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 500)
        self.contrato = suministro(self.e)
        self.detalle_sum = detalle_suministro(self.contrato, self.e.variedad, cantidad=10, minima=8)
        reserva = reserva_lista(None, self.lote, 10, fecha_entrega=self.detalle_sum.fecha_primer_entrega, detalle_suministro=self.detalle_sum)
        self.entrega = marcar_concretada(entrega(self.contrato, [reserva]))

    def crear(self, entrega_=None):
        return enlaces.crear_enlace(Tipo.CONFIRMACION_ENTREGA, self.contrato.cliente, entrega=entrega_ or self.entrega)


class CrearEnlaceDeConfirmacionTests(ConfirmacionDeEntregaBase):
    def test_regla_el_enlace_de_confirmacion_lleva_la_entrega_sin_venta_ni_vencimiento_y_no_guarda_el_token(self):
        """Patrón, secciones 8 y 9: `crear_enlace(confirmacion_entrega, cliente, entrega=…)`; `fecha_vencimiento` nula; la base guarda solo el SHA-256 y el correo sale con `on_commit`."""
        with mock.patch("comercial.servicios.enlaces.enviar_enlace") as envio, self.captureOnCommitCallbacks(execute=True) as callbacks:
            creado, token = self.crear()
        fila = EnlaceCliente.objects.filter(pk=creado.pk).values().get()
        self.assertEqual((creado.tipo, creado.entrega_id, creado.compra_venta_id, creado.fecha_vencimiento, creado.estado), ("confirmacion_entrega", self.entrega.pk, None, None, "vigente"))
        self.assertEqual(len(fila["token_resumen"]), 64)
        self.assertNotIn(token, " ".join(str(v) for v in fila.values()))
        self.assertEqual(len(callbacks), 1)
        envio.assert_called_once_with(creado.pk, token)

    def test_regla_uno_por_entrega_y_sin_reemplazo(self):
        """Regla «Enlace de confirmación»: uno por entrega; un segundo no reemplaza al primero (la base lo impide) y el primero queda vigente."""
        primero, _ = self.crear()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear()
        primero.refresh_from_db()
        self.assertEqual((primero.estado, EnlaceCliente.objects.filter(entrega=self.entrega).count()), ("vigente", 1))

    def test_regla_los_argumentos_tienen_que_cuadrar_con_el_tipo(self):
        """Cambio del parámetro de `crear_enlace` (COM-06b): la confirmación exige la entrega y no admite venta ni vencimiento; el faltante exige venta y vencimiento y no admite entrega."""
        cli = self.contrato.cliente
        for argumentos in ({}, {"entrega": self.entrega, "vence": HOY}, {"entrega": self.entrega, "compra_venta": compra_venta(self.e)}):
            with self.assertRaises(ValueError):
                enlaces.crear_enlace(Tipo.CONFIRMACION_ENTREGA, cli, **argumentos)
        venta = compra_venta(self.e, estado="pendiente_decision")
        for argumentos in ({"compra_venta": venta}, {"compra_venta": venta, "vence": HOY, "entrega": self.entrega}, {"vence": HOY}):
            with self.assertRaises(ValueError):
                enlaces.crear_enlace(Tipo.DECISION_FALTANTE, cli, **argumentos)

    def test_regla_un_cliente_sin_correo_no_tiene_enlace_de_confirmacion(self):
        """Regla «Enlace de confirmación»: sin correo no hay enlace (`ValueError`; el llamador lo sabe antes)."""
        sin_correo = cliente(email="")
        with self.assertRaises(ValueError):
            enlaces.crear_enlace(Tipo.CONFIRMACION_ENTREGA, sin_correo, entrega=self.entrega)

    def test_regla_crear_el_de_confirmacion_no_reemplaza_los_de_faltante(self):
        """El enlace de decisión de faltante de una venta del mismo cliente sigue vigente (no se reemplaza por tipo distinto ni por otro contrato)."""
        venta = compra_venta(self.e, estado="pendiente_decision")
        faltante, _ = un_enlace(venta)
        self.crear()
        faltante.refresh_from_db()
        self.assertEqual(faltante.estado, "vigente")


class VigenciaDeLaConfirmacionTests(ConfirmacionDeEntregaBase):
    def test_regla_vigencia_calculada_con_el_parametro_el_ultimo_dia_sirve_y_el_siguiente_no(self):
        """D-68 punto 8: `fecha_resolucion_orden + dias_vigencia_enlace_confirmacion` (3 por omisión): hasta el final de ese día sirve; al siguiente, `vencido`."""
        creado, _ = enlace_de_confirmacion(self.entrega)
        self.assertEqual(enlaces.vencimiento_de(creado), HOY + timedelta(days=3))
        self.assertEqual(enlaces.situacion_del_enlace(creado, HOY + timedelta(days=3)), enlaces.SIRVE)
        self.assertEqual(enlaces.situacion_del_enlace(creado, HOY + timedelta(days=4)), enlaces.VENCIDO)

    def test_regla_cambiar_el_parametro_cambia_la_vigencia_de_un_enlace_ya_creado(self):
        """Regla «Enlace de confirmación»: si cambia `dias_vigencia_enlace_confirmacion`, cambia también la vigencia de los enlaces ya enviados."""
        creado, _ = enlace_de_confirmacion(self.entrega)
        fijar_vigencia(1)
        self.assertEqual(enlaces.situacion_del_enlace(creado, HOY + timedelta(days=2)), enlaces.VENCIDO)
        fijar_vigencia(10)
        self.assertEqual(enlaces.situacion_del_enlace(creado, HOY + timedelta(days=10)), enlaces.SIRVE)

    def test_ext_2a_cada_motivo_por_el_que_la_confirmacion_no_sirve(self):
        """Extensión 2a de COM-CNF-ENT: usado, anulado y vencido (por estado) no sirven, cada uno con su motivo y su texto."""
        for estado, motivo in (("usado", enlaces.USADO), ("anulado", enlaces.ANULADO), ("vencido", enlaces.VENCIDO)):
            EnlaceCliente.objects.filter(entrega=self.entrega).delete()
            creado, _ = enlace_de_confirmacion(self.entrega, estado=estado)
            self.assertEqual(enlaces.situacion_del_enlace(creado, HOY), motivo)
            self.assertEqual(enlaces.texto_del_motivo(motivo, Tipo.CONFIRMACION_ENTREGA), enlaces.MOTIVOS_DE_CONFIRMACION[motivo])

    def test_regla_el_paso_27_no_toma_el_enlace_de_confirmacion(self):
        """Patrón, sección 9: un enlace de confirmación no usado no avisa nada («sin confirmación tácita»): el paso 27 solo toma el faltante."""
        creado, _ = enlace_de_confirmacion(self.entrega)
        enlaces.avisar_enlaces_vencidos(HOY + timedelta(days=30))
        creado.refresh_from_db()
        self.assertEqual((creado.estado, Notificacion.objects.count()), ("vigente", 0))


@override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test")
class EnviarYReemitirConfirmacionTests(ConfirmacionDeEntregaBase):
    def test_regla_el_correo_lleva_el_comprobante_y_el_enlace_y_el_resultado_va_al_enlace_y_a_la_entrega(self):
        """Postcondición l: `enviar_correo` recibe el comprobante (variedad, monto, vencimiento), la URL con el token y hasta cuándo sirve; `estado_envio` y `estado_aviso_cliente` quedan «enviado»."""
        creado, token = self.crear()
        with mock.patch("core.correo.enviar_correo", return_value=True) as envio:
            enlaces.enviar_enlace(creado.pk, token)
        destinatario, asunto, plantilla, contexto = envio.call_args.args
        self.assertEqual((destinatario.email, plantilla), (self.contrato.cliente.email_cliente, "comercial/correos/confirmacion_entrega.txt"))
        self.assertEqual((contexto["url"], contexto["vence"], contexto["codigo"]), (f"https://sitio.test/cliente/{token}/", HOY + timedelta(days=3), self.entrega.codigo))
        self.assertEqual(contexto["lineas"][0]["variedad"], str(self.e.variedad))
        creado.refresh_from_db()
        self.entrega.refresh_from_db()
        self.assertEqual((creado.estado_envio, self.entrega.estado_aviso_cliente, Notificacion.objects.count()), ("enviado", "enviado", 0))

    def test_ext_un_correo_que_falla_deja_pendiente_de_envio_sin_avisar_al_vendedor(self):
        """15a: si el correo no sale queda «pendiente de envío» en el enlace y en la entrega, y no se avisa al Vendedor (lo reintenta el paso 50)."""
        creado, token = self.crear()
        with mock.patch("core.correo.enviar_correo", return_value=False):
            enlaces.enviar_enlace(creado.pk, token)
        creado.refresh_from_db()
        self.entrega.refresh_from_db()
        self.assertEqual((creado.estado_envio, self.entrega.estado_aviso_cliente, Notificacion.objects.count()), ("pendiente_envio", "pendiente_envio", 0))

    def test_ext_sin_la_url_del_sitio_queda_pendiente(self):
        """Sin `URL_DEL_SITIO` el enlace no se puede armar: «pendiente de envío», sin correo."""
        creado, token = self.crear()
        with override_settings(URL_DEL_SITIO=""), mock.patch("core.correo.enviar_correo") as envio:
            enlaces.enviar_enlace(creado.pk, token)
        creado.refresh_from_db()
        self.assertEqual((creado.estado_envio, envio.call_count), ("pendiente_envio", 0))

    def test_regla_reemitir_da_un_token_nuevo_a_la_misma_fila_y_el_viejo_deja_de_servir(self):
        """Extensión 15a: `reemitir_enlace` pone un token nuevo en la misma fila (`token_resumen` nuevo), lo manda con `on_commit` y el token viejo ya no se encuentra."""
        creado, viejo = self.crear()
        with mock.patch("comercial.servicios.enlaces.enviar_enlace") as envio, self.captureOnCommitCallbacks(execute=True):
            nuevo = enlaces.reemitir_enlace(creado)
        self.assertIsNotNone(nuevo)
        self.assertNotEqual(nuevo, viejo)
        envio.assert_called_once_with(creado.pk, nuevo)
        self.assertIsNone(enlaces.enlace_por_token(viejo))
        self.assertEqual(enlaces.enlace_por_token(nuevo).pk, creado.pk)
        self.assertEqual(EnlaceCliente.objects.filter(entrega=self.entrega).count(), 1)

    def test_regla_un_enlace_usado_o_vencido_no_se_reemite(self):
        """15a: «Vencido o usado, no se reintenta»: `reemitir_enlace` no hace nada y no cambia el token."""
        for estado in ("usado", "vencido", "anulado"):
            EnlaceCliente.objects.filter(entrega=self.entrega).delete()
            creado, _ = enlace_de_confirmacion(self.entrega, estado=estado)
            antes = creado.token_resumen
            self.assertIsNone(enlaces.reemitir_enlace(creado))
            creado.refresh_from_db()
            self.assertEqual(creado.token_resumen, antes)
        EnlaceCliente.objects.filter(entrega=self.entrega).delete()
        creado, _ = enlace_de_confirmacion(self.entrega)
        with mock.patch("comercial.servicios.enlaces.vencimiento_de", return_value=HOY - timedelta(days=1)):  # vigente por estado pero ya pasó su vigencia calculada
            self.assertIsNone(enlaces.reemitir_enlace(creado))

    def test_regla_reemitir_no_toca_los_enlaces_de_faltante(self):
        """El faltante no reintenta (sección 3 del patrón): `reemitir_enlace` de un enlace de decisión no hace nada."""
        venta = compra_venta(self.e, estado="pendiente_decision")
        faltante, _ = un_enlace(venta)
        self.assertIsNone(enlaces.reemitir_enlace(faltante))
