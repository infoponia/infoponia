# Pruebas de IOT-MOD-HDW · Modificar Hardware, la parte de las órdenes de mantenimiento al volver a activar un equipo (IOT-07, paso 5): regla 8 y postcondiciones b y e (docs/casos_de_uso/iot/hardware.md);
# docs/casos_de_uso/iot/mantenimiento_automatico.md, «Volver a activar un equipo con órdenes»; D-73 (punto 2), D-79 (punto 8). Se escribieron ANTES que el servicio
# (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban (iot/servicios/hardware.py), tomados del módulo dentro de cada prueba:
#   ordenes_al_volver_a_activar(equipo) -> list[OrdenAlVolver(orden, cancelable, otros_fuera_de_servicio)]
#       las órdenes «a realizar» del equipo (por id); ``otros_fuera_de_servicio`` son los DEMÁS equipos de la orden que siguen «fuera de servicio»; si hay alguno, no es cancelable. Sin consultas por fila.
#   volver_a_activar(actor, equipo_id, decisiones=None) -> equipo
#       ``decisiones`` es ``{orden_id: "cancelar" | "mantener"}`` (las claves pueden venir como texto: vienen de un formulario). Errores generales (``ValidationError``):
#       ``decisiones_incompletas`` («Elegí qué hacer con cada orden de mantenimiento.»: con órdenes y sin decisión para alguna, o con un valor que no es «cancelar» ni «mantener»),
#       ``orden_no_cancelable`` («La orden OT-0231 incluye otros equipos fuera de servicio: no se puede cancelar.») y
#       ``ordenes_cambiaron`` («Las órdenes del equipo cambiaron mientras confirmabas: revisalas de nuevo.»: después de bloquear, una orden decidida ya no está «a realizar»).
#       Cada orden a cancelar: ``cancelar_orden_incluida`` con el motivo «Se volvió a activar el equipo {identificador}.» y aviso al Técnico (solo con la cuenta activa).
#       Auditoría: ``reactivacion_hardware`` con las órdenes canceladas como afectados y, en ``datos``, ``ordenes_canceladas`` y ``ordenes_mantenidas`` (códigos), solo si el equipo tenía órdenes.
# Sin órdenes, todo igual que en IOT-02.

from django.core.exceptions import NON_FIELD_ERRORS
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import perezoso
from iot.models import Actuador, Comando
from iot.servicios import alertas_iot
from iot.tests import fabricas
from iot.tests.test_iot_rsv_cmd_mantenimiento import AHORA, Escena
from maestros.tests.fabricas import codigos_de, error_de

hardware = perezoso("iot.servicios.hardware")
ELIGE = "Elegí qué hacer con cada orden de mantenimiento."
CAMBIARON = "Las órdenes del equipo cambiaron mientras confirmabas: revisalas de nuevo."


class ConEquipoFueraDeServicio(Escena, TestCase):
    """Norte con su Técnico y un actuador «fuera de servicio» con su alerta «comando fallido»."""

    def setUp(self):
        super().setUp()
        Actuador.objects.filter(pk=self.actuador.pk).update(estado_hardware="fuera_de_servicio")
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="fallido", resuelto_en=AHORA)  # el equipo está fuera de servicio porque su comando falló: no queda pendiente
        self.alerta_fallida = alertas_iot.asegurar_alerta_iot(
            self.norte.pk, self.sistema, "iot_comando_fallido", f"hw:{self.actuador.pk}", "norte/extractor · Encender no se ejecutó", hardware=self.actuador
        ).alerta

    def orden(self, equipos=None, **extra):
        return fabricas.mantenimiento_tecnico(self.norte, self.tecnico, equipos or [self.actuador], **extra)

    def activar(self, decisiones=None, actor=None):
        return hardware.volver_a_activar(actor or self.laura, self.actuador.pk, decisiones)

    def estado(self):
        self.actuador.refresh_from_db()
        return self.actuador.estado_hardware

    def otro_equipo_fuera_de_servicio(self, estado="fuera_de_servicio"):
        return fabricas.actuador(self.sistema, self.tipo, "norte/otro", estado=estado)


class OrdenesAlVolverAActivarTests(ConEquipoFueraDeServicio):
    """La ventana: las órdenes del equipo, cada una con «Cancelarla» o solo «Mantenerla» (D-79, punto 8)."""

    def test_regla_8_sin_ordenes_devuelve_una_lista_vacia(self):
        self.assertEqual(hardware.ordenes_al_volver_a_activar(self.actuador), [])

    def test_regla_8_cada_orden_a_realizar_del_equipo_es_cancelable_si_no_hay_otros_fuera_de_servicio(self):
        primera, segunda = self.orden(), self.orden()
        filas = hardware.ordenes_al_volver_a_activar(self.actuador)
        self.assertEqual([f.orden for f in filas], [primera, segunda])
        self.assertEqual([(f.cancelable, f.otros_fuera_de_servicio) for f in filas], [(True, []), (True, [])])

    def test_regla_8_una_orden_con_otro_equipo_fuera_de_servicio_no_es_cancelable_y_lo_nombra(self):
        """Regla 8 de IOT-MOD-HDW: «Si la orden incluye otros equipos que siguen fuera de servicio, no se ofrece cancelarla»."""
        otro = self.otro_equipo_fuera_de_servicio()
        orden = self.orden([self.actuador, otro])
        (fila,) = hardware.ordenes_al_volver_a_activar(self.actuador)
        self.assertEqual(fila.orden, orden)
        self.assertFalse(fila.cancelable)
        self.assertEqual([e.pk for e in fila.otros_fuera_de_servicio], [otro.pk])

    def test_regla_8_un_otro_equipo_activo_no_impide_cancelarla(self):
        otro = self.otro_equipo_fuera_de_servicio(estado="activo")
        self.orden([self.actuador, otro])
        (fila,) = hardware.ordenes_al_volver_a_activar(self.actuador)
        self.assertEqual((fila.cancelable, fila.otros_fuera_de_servicio), (True, []))

    def test_regla_8_las_canceladas_y_las_de_otro_equipo_no_se_muestran(self):
        self.orden(estado="cancelada")
        self.orden([self.otro_equipo_fuera_de_servicio()])
        self.assertEqual(hardware.ordenes_al_volver_a_activar(self.actuador), [])

    def test_regla_8_sin_consultas_por_fila(self):
        """Una cantidad fija de consultas con 1 y con 5 órdenes (algunas con otros equipos), leyendo lo que dibuja la ventana."""
        otro = self.otro_equipo_fuera_de_servicio()

        def leer():
            return [(f.orden.codigo, f.orden.tecnico.email, f.cancelable, [e.identificador_equipo for e in f.otros_fuera_de_servicio]) for f in hardware.ordenes_al_volver_a_activar(self.actuador)]

        self.orden()
        with CaptureQueriesContext(connection) as con_una:
            leer()
        for _ in range(4):
            self.orden([self.actuador, otro])
        with CaptureQueriesContext(connection) as con_cinco:
            filas = leer()
        self.assertEqual(len(filas), 5)
        self.assertEqual(len(con_una), len(con_cinco))


class DecisionesTests(ConEquipoFueraDeServicio):
    """Regla 8 y postcondiciones b y e: cancelar una y mantener otra, y lo que se rechaza."""

    def test_post_b_cancelar_una_y_mantener_otra(self):
        """Postcondición b: el equipo vuelve a «activo»; la orden elegida se cancela con el motivo armado por InfoPonia y la otra no cambia."""
        a_cancelar, a_mantener = self.orden(), self.orden()
        self.activar({a_cancelar.pk: "cancelar", a_mantener.pk: "mantener"})
        a_cancelar.refresh_from_db()
        a_mantener.refresh_from_db()
        self.assertEqual(self.estado(), "activo")
        self.assertEqual((a_cancelar.estado_orden, a_cancelar.motivo_cancelacion), ("cancelada", "Se volvió a activar el equipo norte/extractor."))
        self.assertEqual((a_mantener.estado_orden, a_mantener.motivo_cancelacion), ("a_realizar", None))

    def test_post_b_la_alerta_comando_fallido_se_resuelve_al_volver_a_activar(self):
        orden = self.orden()
        self.activar({orden.pk: "mantener"})
        self.alerta_fallida.refresh_from_db()
        self.assertEqual(self.alerta_fallida.estado_alerta, "resuelta")

    def test_post_b_mantener_deja_la_orden_intacta(self):
        orden = self.orden(alerta=self.alerta_fallida)
        self.activar({orden.pk: "mantener"})
        orden.refresh_from_db()
        self.assertEqual((orden.estado_orden, orden.alerta_id), ("a_realizar", self.alerta_fallida.pk))
        self.assertEqual(self.estado(), "activo")

    def test_regla_8_las_claves_pueden_venir_como_texto(self):
        """Las decisiones llegan de un formulario: sus claves son texto."""
        orden = self.orden()
        self.activar({str(orden.pk): "cancelar"})
        orden.refresh_from_db()
        self.assertEqual(orden.estado_orden, "cancelada")

    def test_regla_8_con_ordenes_y_sin_decisiones_se_rechaza_y_no_cambia_nada(self):
        orden = self.orden()
        for decisiones in (None, {}):
            with self.subTest(decisiones=decisiones):
                error = error_de(lambda: self.activar(decisiones))
                self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["decisiones_incompletas"])
                self.assertEqual(error.messages, [ELIGE])
        orden.refresh_from_db()
        self.assertEqual((self.estado(), orden.estado_orden), ("fuera_de_servicio", "a_realizar"))
        self.alerta_fallida.refresh_from_db()
        self.assertEqual(self.alerta_fallida.estado_alerta, "activa")

    def test_regla_8_sin_decision_para_una_de_las_ordenes_se_rechaza(self):
        decidida, sin_decidir = self.orden(), self.orden()
        error = error_de(lambda: self.activar({decidida.pk: "cancelar"}))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["decisiones_incompletas"])
        decidida.refresh_from_db()
        self.assertEqual((self.estado(), decidida.estado_orden, sin_decidir.estado_orden), ("fuera_de_servicio", "a_realizar", "a_realizar"))

    def test_regla_8_una_decision_que_no_es_cancelar_ni_mantener_se_rechaza(self):
        orden = self.orden()
        error = error_de(lambda: self.activar({orden.pk: "borrar"}))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["decisiones_incompletas"])
        self.assertEqual(self.estado(), "fuera_de_servicio")

    def test_regla_8_una_orden_con_otro_equipo_fuera_de_servicio_solo_se_mantiene(self):
        """Pedir cancelar una no cancelable: «La orden OT-0231 incluye otros equipos fuera de servicio: no se puede cancelar.» y no cambia nada; mantenerla sí se puede."""
        otro = self.otro_equipo_fuera_de_servicio()
        orden = self.orden([self.actuador, otro])
        error = error_de(lambda: self.activar({orden.pk: "cancelar"}))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["orden_no_cancelable"])
        self.assertEqual(error.messages, [f"La orden {orden.codigo} incluye otros equipos fuera de servicio: no se puede cancelar."])
        orden.refresh_from_db()
        self.assertEqual((self.estado(), orden.estado_orden), ("fuera_de_servicio", "a_realizar"))
        self.activar({orden.pk: "mantener"})
        orden.refresh_from_db()
        self.assertEqual((self.estado(), orden.estado_orden), ("activo", "a_realizar"))

    def test_regla_8_las_ordenes_cambiaron_mientras_tanto(self):
        """Después de bloquear, una orden decidida que ya no está «a realizar» (la canceló otra operación): «Las órdenes del equipo cambiaron mientras confirmabas: revisalas de nuevo.»"""
        orden = self.orden()
        type(orden).objects.filter(pk=orden.pk).update(estado_orden="cancelada", fecha_resolucion_orden=orden.fecha_programada_orden, motivo_cancelacion="x")
        error = error_de(lambda: self.activar({orden.pk: "cancelar"}))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["ordenes_cambiaron"])
        self.assertEqual(error.messages, [CAMBIARON])
        self.assertEqual(self.estado(), "fuera_de_servicio")

    def test_regla_8_una_orden_de_otro_equipo_no_se_toca(self):
        propia = self.orden()
        ajena = self.orden([self.otro_equipo_fuera_de_servicio()])
        self.activar({propia.pk: "cancelar"})
        ajena.refresh_from_db()
        self.assertEqual(ajena.estado_orden, "a_realizar")

    def test_regla_8_no_se_puede_decidir_sobre_una_orden_ajena_al_equipo(self):
        """Una decisión sobre una orden que no es de este equipo cuenta como «las órdenes cambiaron»: no se cancela nada ajeno."""
        ajena = self.orden([self.otro_equipo_fuera_de_servicio()])
        propia = self.orden()
        error = error_de(lambda: self.activar({propia.pk: "mantener", ajena.pk: "cancelar"}))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["ordenes_cambiaron"])
        ajena.refresh_from_db()
        self.assertEqual(ajena.estado_orden, "a_realizar")


class AvisosYAuditoriaTests(ConEquipoFueraDeServicio):
    """Postcondición e: el aviso de cada orden cancelada y el registro `reactivacion_hardware`."""

    def avisos(self):
        return list(Notificacion.objects.filter(destinatario=self.tecnico).order_by("pk"))

    def test_post_b_el_tecnico_recibe_un_aviso_por_cada_orden_cancelada_y_ninguno_por_las_mantenidas(self):
        c1, c2, m = self.orden(), self.orden(), self.orden()
        self.activar({c1.pk: "cancelar", c2.pk: "cancelar", m.pk: "mantener"})
        avisos = self.avisos()
        self.assertEqual(sorted(a.titulo for a in avisos), sorted([f"Orden {c1.codigo} cancelada", f"Orden {c2.codigo} cancelada"]))
        self.assertIn("Motivo: Se volvió a activar el equipo norte/extractor.", avisos[0].detalle)
        self.assertIn("Mantenimiento técnico del", avisos[0].detalle)

    def test_ext_9a_con_el_tecnico_inactivo_se_cancela_sin_avisar(self):
        type(self.tecnico).objects.filter(pk=self.tecnico.pk).update(is_active=False)
        orden = self.orden()
        self.activar({orden.pk: "cancelar"})
        orden.refresh_from_db()
        self.assertEqual(orden.estado_orden, "cancelada")
        self.assertEqual(self.avisos(), [])

    def test_post_e_la_auditoria_lista_las_canceladas_y_las_mantenidas(self):
        """Postcondición e: UN registro `reactivacion_hardware`; las órdenes canceladas son afectados; en `datos`, `ordenes_canceladas` y `ordenes_mantenidas` (códigos); `desde` se conserva."""
        c, m = self.orden(), self.orden()
        self.activar({c.pk: "cancelar", m.pk: "mantener"})
        (registro,) = RegistroAuditoria.objects.filter(accion="reactivacion_hardware")
        afectados = [(a["modelo"], a["id"]) for a in registro.afectados]
        self.assertIn(("iot.mantenimientotecnico", c.pk), afectados)
        self.assertNotIn(("iot.mantenimientotecnico", m.pk), afectados)
        self.assertEqual(registro.detalle["datos"], {"desde": "fuera_de_servicio", "ordenes_canceladas": [c.codigo], "ordenes_mantenidas": [m.codigo]})

    def test_post_e_sin_ordenes_la_auditoria_es_la_de_iot_02(self):
        """Sin órdenes, todo igual que en IOT-02: ni `ordenes_canceladas` ni `ordenes_mantenidas` en `datos`, con o sin `decisiones`."""
        for decisiones in (None, {}):
            with self.subTest(decisiones=decisiones):
                Actuador.objects.filter(pk=self.actuador.pk).update(estado_hardware="fuera_de_servicio")
                self.activar(decisiones)
                registro = RegistroAuditoria.objects.filter(accion="reactivacion_hardware").latest("pk")
                self.assertEqual(registro.detalle["datos"], {"desde": "fuera_de_servicio"})

    def test_post_b_un_fallo_al_avisar_deshace_todo(self):
        """Todo o nada (D-22): si el aviso falla, el equipo sigue fuera de servicio, la orden «a realizar» y sin registro."""
        from unittest import mock

        orden = self.orden()
        with mock.patch("core.notificaciones.notificar_a_varios", side_effect=RuntimeError("falla")), self.assertRaises(RuntimeError):
            self.activar({orden.pk: "cancelar"})
        orden.refresh_from_db()
        self.assertEqual((self.estado(), orden.estado_orden), ("fuera_de_servicio", "a_realizar"))
        self.assertFalse(RegistroAuditoria.objects.filter(accion="reactivacion_hardware").exists())
        self.alerta_fallida.refresh_from_db()
        self.assertEqual(self.alerta_fallida.estado_alerta, "activa")
