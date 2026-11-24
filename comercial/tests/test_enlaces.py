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

from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from comercial.models import CompraVenta, DetalleVenta, EnlaceCliente
from comercial.servicios import enlaces
from comercial.tests.fabricas import cliente, compra_venta, detalle, enlace as un_enlace, escenario_comercial
from core.models import Notificacion, RegistroAuditoria
from core.procesos import ResumenDePaso, pasos_diarios
from inventario.tests.fabricas import ConDatosDeInventario

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
