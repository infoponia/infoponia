# Pruebas de la cancelación de una orden de mantenimiento desde la ficha del equipo (IOT-07, paso 4; PROD-CNL-ORD para un mantenimiento: 4d, 6a, 8a, 8e, 9a y las postcondiciones j, k y m;
# docs/casos_de_uso/iot/mantenimiento_automatico.md, «Cancelar la orden desde la ficha»; D-73 puntos 2 a 4, D-79 puntos 1, 2 y 7). Se escribieron ANTES que el servicio
# (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban (iot/servicios/mantenimiento.py), tomados del módulo dentro de cada prueba:
#   resumen_de_cancelacion_de_mantenimiento(actor, orden_id) -> ResumenDeCancelacionDeMantenimiento(orden, equipos, tipo_texto, tecnico, repuestos, aviso)       (paso 4d; no escribe)
#       ``tipo_texto`` «Revisión»; ``repuestos`` es la lista de repuestos reservados (vacía en esta ronda: la pantalla dice «Sin repuestos reservados»); ``aviso`` es el texto fijo de que la alerta sigue activa.
#   cancelar_mantenimiento(actor, orden_id, motivo) -> MantenimientoTecnico                                                                                   (la orden ya cancelada)
# Errores: ``PermissionDenied`` (otros roles, cuenta inactiva y, en el resumen, quien solo consulta), ``Http404`` (la orden no existe, no es un mantenimiento o su invernadero está fuera del alcance de consulta, D-28),
# ``ValidationError``: del campo ``motivo`` (``motivo_obligatorio``, ``motivo_largo``) y generales ``fuera_de_alcance`` (regla 1, vuelto a verificar DESPUÉS de bloquear) y ``orden_no_pendiente`` (8a).
# Quién (D-79, punto 2): el Agrónomo a cargo o, sin Agrónomo activo, el Gerente (alcance del IoT).

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_capataz
from inventario.tests.fabricas import perezoso
from iot.models import Actuador, AlertaIot, MantenimientoTecnico
from iot.servicios import alertas_iot
from iot.tests import fabricas
from iot.tests.test_iot_rsv_cmd_mantenimiento import Escena
from maestros.models import Alerta
from maestros.tests.fabricas import codigos_de, crear_agronomo, error_de
from produccion.tests.fabricas import orden_suelta

mantenimiento = perezoso("iot.servicios.mantenimiento")
MOTIVO = "El extractor ya se revisó en el invernadero"


class CancelarMantenimientoBase(Escena, TestCase):
    """La escena de la orden automática (Norte con su Agrónomo, su Técnico y un actuador fuera de servicio) con una orden «a realizar» y su alerta «comando fallido»."""

    def setUp(self):
        super().setUp()
        Actuador.objects.filter(pk=self.actuador.pk).update(estado_hardware="fuera_de_servicio")
        self.alerta_fallida = alertas_iot.asegurar_alerta_iot(
            self.norte.pk, self.sistema, "iot_comando_fallido", f"hw:{self.actuador.pk}", "norte/extractor · Encender no se ejecutó", hardware=self.actuador
        ).alerta
        self.orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador], alerta=self.alerta_fallida, descripcion_orden="CMD-1 · Encender")

    def cancelar(self, actor=None, motivo=MOTIVO, orden=None):
        return mantenimiento.cancelar_mantenimiento(actor or self.laura, (orden or self.orden).pk, motivo)

    def sin_agronomo_activo(self):
        """Norte queda sin Agrónomo activo: lo opera el Gerente (D-79, punto 2)."""
        type(self.laura).objects.filter(pk=self.laura.pk).update(is_active=False)

    def recargar(self):
        self.orden.refresh_from_db()


class PermisosTests(CancelarMantenimientoBase):
    """D-79, punto 2: el alcance del IoT."""

    def test_regla_alcance_el_agronomo_a_cargo_cancela(self):
        self.cancelar()
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "cancelada")

    def test_regla_alcance_el_gerente_sin_agronomo_activo_cancela(self):
        """Excepción a «el Gerente no cancela» de PROD-CNL-ORD (D-79, punto 2): con el Agrónomo inactivo la orden no se quedaría sin quien la cierre."""
        self.sin_agronomo_activo()
        self.cancelar(actor=self.gerente)
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "cancelada")

    def test_regla_alcance_el_gerente_sin_agronomo_asignado_cancela(self):
        type(self.norte).objects.filter(pk=self.norte.pk).update(agronomo=None)
        self.cancelar(actor=self.gerente)
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "cancelada")

    def test_regla_alcance_el_gerente_con_agronomo_activo_no_cancela(self):
        """El Gerente con un Agrónomo activo ve la orden en solo lectura: ``fuera_de_alcance`` y la orden no cambia."""
        error = error_de(lambda: self.cancelar(actor=self.gerente))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["fuera_de_alcance"])
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "a_realizar")

    def test_regla_alcance_otro_agronomo_no_ve_la_orden(self):
        """Un Agrónomo de otro invernadero está fuera del alcance de consulta: 404 (D-28)."""
        otro = crear_agronomo("otro@infoponia.com")
        with self.assertRaises(Http404):
            self.cancelar(actor=otro)
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "a_realizar")

    def test_regla_alcance_el_tecnico_y_otros_roles_no_operan_el_iot(self):
        """Solo el Agrónomo y el Gerente operan el IoT: el Técnico (dueño de la orden) y el Capataz reciben ``PermissionDenied``."""
        for cuenta in (self.tecnico, crear_capataz()):
            with self.subTest(rol=type(cuenta).__name__), self.assertRaises(PermissionDenied):
                self.cancelar(actor=cuenta)
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "a_realizar")

    def test_regla_alcance_una_cuenta_inactiva_no_cancela(self):
        type(self.laura).objects.filter(pk=self.laura.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.cancelar()

    def test_regla_alcance_una_orden_que_no_es_un_mantenimiento_da_404(self):
        """Esta cancelación es solo del mantenimiento del IoT: una entrega (o cualquier otra orden) no se cancela por acá."""
        entrega = orden_suelta(self.norte, "entrega")
        with self.assertRaises(Http404):
            mantenimiento.cancelar_mantenimiento(self.laura, entrega.pk, MOTIVO)
        with self.assertRaises(Http404):
            mantenimiento.cancelar_mantenimiento(self.laura, 99999, MOTIVO)


class MotivoTests(CancelarMantenimientoBase):
    """Extensión 6a y D-79 punto 2: el motivo es obligatorio, de 1 a 300 caracteres y sin espacios al borde; se valida ANTES de cancelar."""

    def test_ext_6a_el_motivo_vacio_o_solo_espacios_se_rechaza(self):
        for motivo in ("", "   ", None):
            with self.subTest(motivo=motivo):
                error = error_de(lambda: self.cancelar(motivo=motivo))
                self.assertEqual(codigos_de(error, "motivo"), ["motivo_obligatorio"])
                self.assertEqual(error.error_dict["motivo"][0].message, "Indicá el motivo de la cancelación.")
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "a_realizar")

    def test_ext_6a_un_motivo_de_301_caracteres_se_rechaza_y_uno_de_300_se_acepta(self):
        error = error_de(lambda: self.cancelar(motivo="x" * 301))
        self.assertEqual(codigos_de(error, "motivo"), ["motivo_largo"])
        self.assertEqual(error.error_dict["motivo"][0].message, "El motivo no puede pasar de 300 caracteres.")
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "a_realizar")
        self.cancelar(motivo="x" * 300)
        self.recargar()
        self.assertEqual(self.orden.motivo_cancelacion, "x" * 300)

    def test_ext_6a_los_espacios_al_borde_no_cuentan_y_no_se_guardan(self):
        """Un motivo de 300 caracteres con espacios alrededor es válido y se guarda sin ellos (no se recorta con «…» sin avisar)."""
        self.cancelar(motivo="  " + "x" * 300 + "  ")
        self.recargar()
        self.assertEqual(self.orden.motivo_cancelacion, "x" * 300)


class EstadoDeLaOrdenTests(CancelarMantenimientoBase):
    def test_ext_8a_una_orden_ya_cancelada_no_se_cancela_de_nuevo(self):
        """Extensión 8a: «La orden ya no está a realizar: otra operación la canceló.», sin cambios ni aviso."""
        self.cancelar()
        avisos = Notificacion.objects.count()
        auditorias = RegistroAuditoria.objects.filter(accion="cancelacion_orden").count()
        error = error_de(lambda: self.cancelar(motivo="otra vez"))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["orden_no_pendiente"])
        self.assertEqual(error.messages, ["La orden ya no está a realizar: otra operación la canceló."])
        self.recargar()
        self.assertEqual(self.orden.motivo_cancelacion, MOTIVO)
        self.assertEqual((Notificacion.objects.count(), RegistroAuditoria.objects.filter(accion="cancelacion_orden").count()), (avisos, auditorias))

    def test_ext_8a_una_orden_concretada_tampoco(self):
        concretada = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador], estado="concretada")
        error = error_de(lambda: self.cancelar(orden=concretada))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["orden_no_pendiente"])


class EfectosTests(CancelarMantenimientoBase):
    """Postcondiciones a, j, k y m."""

    def test_post_a_la_orden_queda_cancelada_con_la_fecha_de_hoy_y_el_motivo(self):
        devuelta = self.cancelar()
        self.recargar()
        self.assertEqual(devuelta.pk, self.orden.pk)
        self.assertEqual((self.orden.estado_orden, self.orden.fecha_resolucion_orden, self.orden.motivo_cancelacion), ("cancelada", timezone.localdate(), MOTIVO))

    def test_post_j_el_equipo_conserva_su_estado_y_la_alerta_sigue_activa(self):
        """Postcondición j y D-73 punto 4: cancelar no cambia el hardware ni resuelve la alerta «comando fallido»: se resuelve cuando el actuador vuelve a «activo»."""
        self.cancelar()
        self.actuador.refresh_from_db()
        self.alerta_fallida.refresh_from_db()
        self.assertEqual(self.actuador.estado_hardware, "fuera_de_servicio")
        self.assertEqual(self.alerta_fallida.estado_alerta, "activa")
        self.recargar()
        self.assertEqual(self.orden.alerta_id, self.alerta_fallida.pk)

    def test_post_k_avisa_al_tecnico_activo_con_el_motivo(self):
        """Postcondición k, 9a y D-79 punto 7: título «Orden OT-0231 cancelada»; detalle «Motivo: …. Mantenimiento técnico del dd/mm/aaaa en {invernadero}, cancelada por {nombre y apellido}.»"""
        self.cancelar()
        (aviso,) = Notificacion.objects.filter(destinatario=self.tecnico)
        self.assertEqual(aviso.titulo, f"Orden {self.orden.codigo} cancelada")
        self.assertEqual(
            aviso.detalle,
            f"Motivo: {MOTIVO}. Mantenimiento técnico del {self.orden.fecha_programada_orden:%d/%m/%Y} en Norte, cancelada por Nombre Apellido.",
        )

    def test_post_k_el_aviso_lleva_el_motivo_entero_aun_con_300_caracteres(self):
        """La regla del largo es la de PROD-CNL-ORD: el motivo va completo y se acorta primero el nombre y después el invernadero; nunca pasa de 500."""
        self.cancelar(motivo="m" * 300)
        (aviso,) = Notificacion.objects.filter(destinatario=self.tecnico)
        self.assertLessEqual(len(aviso.detalle), 500)
        self.assertIn("m" * 300, aviso.detalle)

    def test_ext_9a_con_el_tecnico_inactivo_se_cancela_pero_no_se_avisa(self):
        """Extensión 9a: si el Técnico de la orden no está activo, no se envía el aviso; la cancelación queda registrada igual."""
        type(self.tecnico).objects.filter(pk=self.tecnico.pk).update(is_active=False)
        self.cancelar()
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "cancelada")
        self.assertFalse(Notificacion.objects.filter(destinatario=self.tecnico).exists())

    def test_post_k_cancelar_no_avisa_a_otras_cuentas_ni_al_actor(self):
        self.cancelar()
        self.assertEqual(Notificacion.objects.filter(titulo__startswith="Orden").exclude(destinatario=self.tecnico).count(), 0)

    def test_post_m_un_solo_registro_cancelacion_orden_con_la_orden_y_los_equipos(self):
        """Postcondición m y D-36: un registro ``cancelacion_orden`` del actor, con la orden entre los afectados y, en ``datos``, ``cancelada_desde = iot`` y los equipos de la orden."""
        self.cancelar()
        (registro,) = RegistroAuditoria.objects.filter(accion="cancelacion_orden")
        self.assertEqual(registro.usuario_id, self.laura.pk)
        self.assertIn(("iot.mantenimientotecnico", self.orden.pk), [(a["modelo"], a["id"]) for a in registro.afectados])
        self.assertEqual(registro.detalle["datos"]["cancelada_desde"], "iot")
        self.assertEqual([e["id"] for e in registro.detalle["datos"]["equipos_de_la_orden"]], [self.actuador.pk])
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "a_realizar", "despues": "cancelada"})
        self.assertEqual(registro.detalle["cambios"]["motivo_cancelacion"], {"antes": None, "despues": MOTIVO})

    def test_post_m_los_equipos_de_una_orden_con_varios_equipos_van_todos_en_datos(self):
        otro = fabricas.actuador(self.sistema, self.tipo, "norte/otro")
        varias = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador, otro])
        self.cancelar(orden=varias)
        registro = RegistroAuditoria.objects.filter(accion="cancelacion_orden").latest("pk")
        self.assertEqual(sorted(e["id"] for e in registro.detalle["datos"]["equipos_de_la_orden"]), sorted([self.actuador.pk, otro.pk]))

    def test_post_m_un_fallo_al_avisar_deshace_todo(self):
        """Todo o nada (D-22): si el aviso falla, la orden sigue «a realizar» y no queda registro de auditoría."""
        from unittest import mock

        with mock.patch("core.notificaciones.notificar_a_varios", side_effect=RuntimeError("falla")), self.assertRaises(RuntimeError):
            self.cancelar()
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "a_realizar")
        self.assertFalse(RegistroAuditoria.objects.filter(accion="cancelacion_orden").exists())

    def test_cancelar_no_toca_las_otras_ordenes_del_equipo(self):
        otra = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        self.cancelar()
        otra.refresh_from_db()
        self.assertEqual(otra.estado_orden, "a_realizar")
        self.assertEqual(AlertaIot.objects.filter(alerta__estado_alerta="activa").count(), 1)


class ResumenTests(CancelarMantenimientoBase):
    """Paso 4d y paso 6: lo que muestra la ventana «Cancelar orden», sin escribir."""

    def test_ext_4d_el_resumen_trae_los_equipos_el_tipo_el_tecnico_y_sin_repuestos(self):
        resumen = mantenimiento.resumen_de_cancelacion_de_mantenimiento(self.laura, self.orden.pk)
        self.assertEqual(resumen.orden.pk, self.orden.pk)
        self.assertEqual([e.pk for e in resumen.equipos], [self.actuador.pk])
        self.assertEqual(resumen.tipo_texto, "Revisión")
        self.assertEqual(resumen.tecnico.pk, self.tecnico.pk)
        self.assertEqual(list(resumen.repuestos), [])  # en esta ronda ningún mantenimiento reserva repuestos

    def test_ext_4d_el_resumen_avisa_que_la_alerta_sigue_activa(self):
        """D-73 punto 4: «La alerta «comando fallido» sigue activa: se resuelve cuando el equipo vuelva a estar activo.»"""
        resumen = mantenimiento.resumen_de_cancelacion_de_mantenimiento(self.laura, self.orden.pk)
        self.assertEqual(resumen.aviso, "La alerta «comando fallido» sigue activa: se resuelve cuando el equipo vuelva a estar activo.")

    def test_ext_4d_el_resumen_no_escribe_ni_audita(self):
        mantenimiento.resumen_de_cancelacion_de_mantenimiento(self.laura, self.orden.pk)
        self.recargar()
        self.assertEqual(self.orden.estado_orden, "a_realizar")
        self.assertFalse(RegistroAuditoria.objects.filter(accion="cancelacion_orden").exists())

    def test_ext_4d_el_resumen_respeta_el_alcance(self):
        """Quien solo consulta (el Gerente con Agrónomo activo) no abre la ventana: ``PermissionDenied``; fuera del alcance de consulta, 404; una orden ya cancelada, ``orden_no_pendiente``."""
        with self.assertRaises(PermissionDenied):
            mantenimiento.resumen_de_cancelacion_de_mantenimiento(self.gerente, self.orden.pk)
        with self.assertRaises(Http404):
            mantenimiento.resumen_de_cancelacion_de_mantenimiento(crear_agronomo("otro@infoponia.com"), self.orden.pk)
        self.cancelar()
        error = error_de(lambda: mantenimiento.resumen_de_cancelacion_de_mantenimiento(self.laura, self.orden.pk))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["orden_no_pendiente"])


class EtiquetasDeAuditoriaTests(TestCase):
    """La pantalla «Auditoría» muestra los datos de IOT-07 con su nombre y no con la clave cruda (se tocan solo ``ETIQUETAS`` y ``VALORES_VISIBLES`` de ``core``; sin acciones ni migración)."""

    def test_d36_las_claves_de_datos_de_iot_07_tienen_etiqueta(self):
        for clave in ("cancelada_desde", "equipos_de_la_orden", "orden_mantenimiento", "sin_orden", "ordenes_canceladas", "ordenes_mantenidas"):
            with self.subTest(clave=clave):
                self.assertIn(clave, RegistroAuditoria.ETIQUETAS)
                self.assertNotEqual(RegistroAuditoria.ETIQUETAS[clave], clave)

    def test_d36_los_valores_de_sin_orden_y_de_cancelada_desde_tienen_nombre(self):
        self.assertEqual(set(RegistroAuditoria.VALORES_VISIBLES["sin_orden"]), {"sin_tecnico", "orden_existente"})
        self.assertIn("iot", RegistroAuditoria.VALORES_VISIBLES["cancelada_desde"])

    def test_d36_las_claves_que_ya_existian_no_cambiaron(self):
        """«desde» (Estaba) y «equipos» (Equipos dados de baja) son de otras tareas: no se pisan."""
        self.assertEqual(RegistroAuditoria.ETIQUETAS["desde"], "Estaba")
        self.assertEqual(RegistroAuditoria.ETIQUETAS["equipos"], "Equipos dados de baja")
