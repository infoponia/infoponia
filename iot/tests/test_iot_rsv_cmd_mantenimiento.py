# Pruebas de IOT-RSV-CMD · Resolver Comando, la parte de la orden de mantenimiento (IOT-07, paso 3): postcondiciones k y l, extensiones 4b.4, 4b.4a y 4b.4b, la regla «Orden de mantenimiento
# automática» y la asociación de la orden con la alerta (R048). Fuentes: docs/casos_de_uso/iot/resolver_comando.md, docs/casos_de_uso/iot/mantenimiento_automatico.md («La orden al escalar»), D-73,
# D-78 (puntos 10 y 11), D-79 (puntos 3, 5, 6 y 7) y D-97. Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban:
#   iot/servicios/mantenimiento.py (nuevo): crear_orden_automatica(comando, ahora) -> OrdenAutomatica(orden, caso, sufijo), con ``caso`` = ``creada``, ``sin_tecnico`` u ``orden_existente``
#       (``orden`` es nula en ``sin_tecnico``). La llama el escalamiento de ``comandos.py`` (extensión 4b y el último intento vencido «sin respuesta», 2a), en la transacción del mensaje.
#   Se ejercita por los dos caminos que escalan: ``comandos.registrar_resultado`` (el nodo informa «falló» en el último intento) y ``comandos.retirar_comandos`` (el último intento vence).
# Auditoría (postcondición q): la orden es un afectado más del registro ``resolucion_comando_iot``; en ``datos``, ``orden_mantenimiento`` (el código de la creada, o de la existente) o ``sin_orden``
# (``sin_tecnico`` u ``orden_existente``).
# La hora siempre se recibe (``AHORA``): nada lee la fecha por su cuenta.

from datetime import date, datetime, timedelta, timezone as zona
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import AlertaIot, Comando, MantenimientoTecnico, NodoCentral, RegistroComando
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_tecnico

comandos = perezoso("iot.servicios.comandos")
AHORA = datetime(2026, 11, 23, 15, 0, tzinfo=zona.utc)
HOY = date(2026, 11, 23)  # AHORA en hora local de Argentina
VENTILADOR = [("Encender", "ENCENDER"), ("Apagar", "APAGAR"), ("Fijar velocidad", "FIJAR_NIVEL", 0, 100, "%")]
BASE = "norte/extractor · Encender no se ejecutó en 4 intentos (último: falló: Sin corriente)"


def resultado(que="fallo", detalle="Sin corriente", estado=None, informado_en=None):
    return comandos.ResultadoRecibido(resultado=que, detalle=detalle, estado=estado, informado_en=informado_en)


class Escena(fabricas.ConCatalogoIot):
    """Norte con su Agrónomo, su Técnico, su sistema y un actuador con un comando en su último intento."""

    NOMBRE_DEL_TECNICO = ("Tomás", "Quiroga")

    def setUp(self):
        cache.clear()
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.tecnico = crear_tecnico("tecnico@infoponia.com", nombre=self.NOMBRE_DEL_TECNICO[0], apellido=self.NOMBRE_DEL_TECNICO[1])
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=self.tecnico)
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=AHORA - timedelta(seconds=30))
        self.tipo = fabricas.tipo_actuador("Extractor", acciones=VENTILADOR)
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/extractor", ultimo_mensaje_en=AHORA - timedelta(hours=1))
        self.encender, self.apagar, self.velocidad = self.tipo.acciones.order_by("id")
        self.config = configuracion.obtener()
        self.comando = fabricas.comando(self.actuador, self.encender, agronomo=self.laura)

    def ultimo_intento(self, comando=None, hace=10):
        """El comando está en su último intento (el cuarto), retirado hace ``hace`` segundos."""
        Comando.objects.filter(pk=(comando or self.comando).pk).update(cantidad_intentos=4, ultimo_intento_en=AHORA - timedelta(seconds=hace))

    def escalar(self, detalle="Sin corriente", comando=None):
        """El nodo informa «falló» en el último intento."""
        comando = comando or self.comando
        self.ultimo_intento(comando)
        return comandos.registrar_resultado(self.sistema.pk, comando.pk, resultado("fallo", detalle), AHORA)

    def alerta(self):
        return Alerta.objects.filter(tipo_alerta="iot_comando_fallido", estado_alerta="activa").first()

    def ordenes(self):
        return list(MantenimientoTecnico.objects.order_by("pk"))

    def avisos(self, cuenta=None):
        return list(Notificacion.objects.filter(destinatario=cuenta or self.tecnico).order_by("pk"))

    def auditoria(self):
        return RegistroAuditoria.objects.filter(accion="resolucion_comando_iot").latest("pk")


class OrdenAutomaticaTests(Escena, TestCase):
    """Postcondiciones k y l y extensión 4b.4."""

    def test_post_k_crea_la_orden_con_cada_campo_de_la_regla(self):
        """Postcondición k y regla «Orden de mantenimiento automática»: del Técnico del invernadero, con el equipo, la alerta, sin Agrónomo, «revisión», prioridad alta, a realizar, para hoy."""
        self.escalar()
        (orden,) = self.ordenes()
        self.assertEqual(orden.invernadero_id, self.norte.pk)
        self.assertEqual(orden.tecnico_id, self.tecnico.pk)
        self.assertEqual([h.pk for h in orden.hardware.all()], [self.actuador.pk])
        self.assertEqual(orden.alerta_id, self.alerta().pk)
        self.assertIsNone(orden.agronomo)
        self.assertEqual((orden.tipo_mantenimiento, orden.prioridad_orden, orden.estado_orden), ("revision", "alta", "a_realizar"))
        self.assertEqual((orden.fecha_creacion_orden, orden.fecha_programada_orden), (HOY, HOY))
        self.assertEqual(orden.tipo_orden, "mantenimiento")

    def test_post_k_el_codigo_sale_de_la_secuencia_de_produccion(self):
        """El número sale de ``siguiente_numero`` (D-52 punto 3): dos órdenes seguidas tienen números crecientes."""
        self.escalar()
        otro = fabricas.actuador(self.sistema, self.tipo, "norte/extractor2", ultimo_mensaje_en=AHORA)
        segundo = fabricas.comando(otro, self.encender)
        self.escalar(comando=segundo)
        primera, segunda = self.ordenes()
        self.assertLess(primera.numero, segunda.numero)

    def test_post_k_la_descripcion_lleva_el_comando_la_accion_los_intentos_y_el_ultimo_resultado(self):
        """D-79 punto 7: «CMD-{id} · {acción} no se ejecutó en {n} intentos. Último resultado: Falló: {detalle}.»"""
        self.escalar()
        (orden,) = self.ordenes()
        self.assertEqual(orden.descripcion_orden, f"CMD-{self.comando.pk} · Encender no se ejecutó en 4 intentos. Último resultado: Falló: Sin corriente.")

    def test_post_k_la_descripcion_incluye_el_valor_y_la_unidad_si_el_comando_los_lleva(self):
        """D-79 punto 7: «{acción}[ {valor} {unidad}]»."""
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="cancelado", resuelto_en=AHORA)
        pendiente = fabricas.comando(self.actuador, self.velocidad, valor_comando=50)
        self.escalar(comando=pendiente)
        (orden,) = self.ordenes()
        self.assertEqual(
            orden.descripcion_orden, f"CMD-{pendiente.pk} · Fijar velocidad 50 % no se ejecutó en 4 intentos. Último resultado: Falló: Sin corriente."
        )

    def test_post_k_el_escalamiento_por_sin_respuesta_tambien_crea_la_orden(self):
        """Regla «Escalamiento» y 2a: el último intento vencido «sin respuesta» en el retiro escala igual que 4b, y crea la orden con «Sin respuesta»."""
        self.ultimo_intento(hace=70)
        comandos.retirar_comandos(self.sistema.pk, AHORA)
        (orden,) = self.ordenes()
        self.assertEqual(orden.descripcion_orden, f"CMD-{self.comando.pk} · Encender no se ejecutó en 4 intentos. Último resultado: Sin respuesta.")
        self.assertEqual(self.alerta().pk, orden.alerta_id)
        self.assertEqual(len(self.avisos()), 1)

    def test_ext_4f_un_rechazo_no_crea_ninguna_orden(self):
        """Regla «Rechazo» y 4f: el actuador sigue activo y no se crea orden de mantenimiento."""
        self.ultimo_intento()
        comandos.registrar_resultado(self.sistema.pk, self.comando.pk, resultado("rechazado", "No lo conozco"), AHORA)
        self.assertEqual(self.ordenes(), [])
        self.assertEqual(self.avisos(), [])

    def test_ext_4a_un_intento_fallido_con_intentos_restantes_no_crea_ninguna_orden(self):
        """4a: con intentos restantes el comando sigue pendiente y no hay orden."""
        Comando.objects.filter(pk=self.comando.pk).update(cantidad_intentos=2, ultimo_intento_en=AHORA - timedelta(seconds=10))
        comandos.registrar_resultado(self.sistema.pk, self.comando.pk, resultado("fallo"), AHORA)
        self.assertEqual(self.ordenes(), [])

    def test_post_l_notifica_al_tecnico_con_el_texto_de_d_79(self):
        """Postcondición l y D-79 punto 7: título «Orden OT-0231 de mantenimiento asignada»; detalle «Revisión de {identificador} en {invernadero}, prioridad alta, para hoy. {descripción}»."""
        self.escalar()
        (orden,) = self.ordenes()
        (aviso,) = self.avisos()
        self.assertEqual(aviso.titulo, f"Orden {orden.codigo} de mantenimiento asignada")
        self.assertEqual(aviso.detalle, f"Revisión de norte/extractor en Norte, prioridad alta, para hoy. {orden.descripcion_orden}")

    def test_post_l_el_aviso_se_recorta_a_500_con_puntos_suspensivos(self):
        """D-79 punto 7: el detalle del aviso no pasa de 500 y termina en «…» si se recortó. La descripción de la orden tampoco pasa de 500."""
        self.escalar(detalle="x" * 300)
        (orden,) = self.ordenes()
        (aviso,) = self.avisos()
        self.assertLessEqual(len(orden.descripcion_orden), 500)
        self.assertLessEqual(len(aviso.detalle), 500)

    def test_post_l_con_el_tecnico_inactivo_se_crea_la_orden_pero_no_se_avisa(self):
        """D-79 punto 6 y regla «Orden de mantenimiento automática»: la orden se asigna igual al Técnico del invernadero aunque esté inactivo; el aviso, solo con la cuenta activa."""
        type(self.tecnico).objects.filter(pk=self.tecnico.pk).update(is_active=False)
        self.escalar()
        (orden,) = self.ordenes()
        self.assertEqual(orden.tecnico_id, self.tecnico.pk)
        self.assertEqual(self.avisos(), [])

    def test_post_k_la_orden_queda_asociada_a_la_alerta_y_la_alerta_a_la_orden(self):
        """R048: ``orden.alerta`` es la alerta «comando fallido» recién creada."""
        self.escalar()
        (orden,) = self.ordenes()
        self.assertEqual(self.alerta().mantenimiento_tecnico, orden)

    def test_post_q_la_auditoria_lleva_la_orden_como_afectada_y_su_codigo_en_datos(self):
        """Postcondición q: la orden es un afectado más de ``resolucion_comando_iot``; ``datos.orden_mantenimiento`` es su código."""
        self.escalar()
        (orden,) = self.ordenes()
        registro = self.auditoria()
        self.assertIn(("iot.mantenimientotecnico", orden.pk), [(a["modelo"], a["id"]) for a in registro.afectados])
        self.assertEqual(registro.detalle["datos"]["orden_mantenimiento"], orden.codigo)
        self.assertNotIn("sin_orden", registro.detalle["datos"])

    def test_el_escalamiento_es_todo_o_nada_si_falla_el_aviso(self):
        """«Garantías mínimas»: si el aviso falla, no queda ni la orden ni el comando «fallido» ni el actuador fuera de servicio."""
        self.ultimo_intento()
        with mock.patch("core.notificaciones.notificar", side_effect=RuntimeError("falla")), self.assertRaises(RuntimeError):
            comandos.registrar_resultado(self.sistema.pk, self.comando.pk, resultado("fallo"), AHORA)
        self.assertEqual(self.ordenes(), [])
        self.assertIsNone(self.alerta())
        self.comando.refresh_from_db()
        self.actuador.refresh_from_db()
        self.assertEqual((self.comando.estado_comando, self.actuador.estado_hardware), ("pendiente", "activo"))
        self.assertEqual(RegistroComando.objects.filter(comando=self.comando, resultado="fallido").count(), 0)


class SufijoDeLaAlertaTests(Escena, TestCase):
    """Extensiones 4b.4a y 4b.4b y D-79 puntos 3 y 5: el texto de la alerta «comando fallido»."""

    def test_orden_creada_el_texto_nombra_la_orden_y_al_tecnico(self):
        """D-79 punto 3: «{base} · Orden de mantenimiento OT-0231 asignada a {nombre y apellido}.»"""
        self.escalar()
        (orden,) = self.ordenes()
        self.assertEqual(self.alerta().descripcion_alerta, f"{BASE} · Orden de mantenimiento {orden.codigo} asignada a Tomás Quiroga.")

    def test_ext_4b_4a_sin_tecnico_no_se_crea_la_orden_y_la_alerta_lo_dice(self):
        """Extensión 4b.4a y D-79 punto 3: sin Técnico asignado no hay orden; la alerta dice que el invernadero no tiene Técnico. La alerta se genera igual."""
        type(self.norte).objects.filter(pk=self.norte.pk).update(tecnico=None)
        self.escalar()
        self.assertEqual(self.ordenes(), [])
        self.assertEqual(
            self.alerta().descripcion_alerta, f"{BASE} · El invernadero no tiene Técnico: la orden de mantenimiento deberá planificarse cuando se asigne uno."
        )
        self.assertEqual(self.auditoria().detalle["datos"]["sin_orden"], "sin_tecnico")

    def test_ext_4b_4b_con_una_orden_a_realizar_no_se_crea_otra_y_la_alerta_la_nombra(self):
        """Extensión 4b.4b y D-73 punto 5: si el actuador ya tiene una orden a realizar, no se crea otra; la alerta dice «Ya está en la orden de mantenimiento OT-0231, a realizar.»"""
        existente = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        self.escalar()
        self.assertEqual(self.ordenes(), [existente])
        self.assertEqual(self.alerta().descripcion_alerta, f"{BASE} · Ya está en la orden de mantenimiento {existente.codigo}, a realizar.")
        self.assertEqual(self.avisos(), [])  # no se crea, no se avisa
        datos = self.auditoria().detalle["datos"]
        self.assertEqual((datos["sin_orden"], datos["orden_mantenimiento"]), ("orden_existente", existente.codigo))

    def test_ext_4b_4b_la_alerta_nueva_no_se_asocia_a_la_orden_existente(self):
        """4b.4b: la orden existente conserva su alerta (R048 es 0..1): la alerta nueva no se le asocia."""
        existente = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        self.escalar()
        existente.refresh_from_db()
        self.assertIsNone(existente.alerta)

    def test_ext_4b_4b_una_orden_cancelada_o_de_otro_equipo_no_cuenta_como_existente(self):
        """Solo cuenta una «a realizar» del MISMO actuador: con una cancelada, o una de otro equipo, se crea la orden nueva."""
        otro = fabricas.actuador(self.sistema, self.tipo, "norte/otro")
        fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador], estado="cancelada")
        fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [otro])
        self.escalar()
        self.assertEqual(len(self.ordenes()), 3)
        self.assertIn("asignada a Tomás Quiroga", self.alerta().descripcion_alerta)

    def test_regla_el_nombre_del_tecnico_se_recorta_a_40_con_puntos_suspensivos(self):
        """D-79 punto 5: el nombre del Técnico en el sufijo, hasta 40 caracteres con «…»; el sufijo va siempre completo."""
        type(self.tecnico).objects.filter(pk=self.tecnico.pk).update(first_name="Maximiliano", last_name="Fernández de la Vega y Montenegro")
        self.escalar()
        nombre = "Maximiliano Fernández de la Vega y Montenegro"
        recortado = nombre[:39] + "…"
        self.assertEqual(len(recortado), 40)
        self.assertTrue(self.alerta().descripcion_alerta.endswith(f" asignada a {recortado}."))

    def test_regla_si_pasa_de_200_se_recorta_primero_el_detalle_y_el_sufijo_queda_entero(self):
        """D-79 punto 5: la descripción de la alerta es de 200; si el total pasa, se recorta con «…» primero el detalle del último resultado; el sufijo va siempre completo."""
        self.escalar(detalle="x" * 300)
        (orden,) = self.ordenes()
        texto = self.alerta().descripcion_alerta
        sufijo = f" · Orden de mantenimiento {orden.codigo} asignada a Tomás Quiroga."
        self.assertLessEqual(len(texto), 200)
        self.assertTrue(texto.endswith(sufijo))
        cabeza = texto[: -len(sufijo)]
        self.assertTrue(cabeza.startswith("norte/extractor · Encender no se ejecutó en 4 intentos (último: falló: x"))
        self.assertTrue(cabeza.endswith("…)"))

    def test_regla_si_aun_asi_no_entra_se_recorta_el_texto_base(self):
        """D-79 punto 5: si recortar el detalle no alcanza (un identificador larguísimo), se recorta el texto base; el sufijo sigue entero."""
        largo = "n" * 64
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="cancelado", resuelto_en=AHORA)
        grande = fabricas.actuador(self.sistema, self.tipo, largo, ultimo_mensaje_en=AHORA)
        pendiente = fabricas.comando(grande, self.encender)
        type(self.tecnico).objects.filter(pk=self.tecnico.pk).update(first_name="M" * 30, last_name="F" * 30)
        self.escalar(detalle="y" * 300, comando=pendiente)
        (orden,) = self.ordenes()
        texto = self.alerta().descripcion_alerta
        nombre = ("M" * 30 + " " + "F" * 30)[:39] + "…"
        sufijo = f" · Orden de mantenimiento {orden.codigo} asignada a {nombre}."
        self.assertLessEqual(len(texto), 200)
        self.assertTrue(texto.endswith(sufijo))

    def test_regla_un_escalamiento_sin_sufijo_largo_no_recorta_nada(self):
        """Con identificadores y acciones de largo común todo entra sin recortes (D-79 punto 5)."""
        self.escalar()
        self.assertNotIn("…", self.alerta().descripcion_alerta)


class OrdenYAlertaPreexistenteTests(Escena, TestCase):
    """Un segundo escalamiento con la alerta anterior todavía activa no duplica la alerta ni rompe R048."""

    def test_si_la_alerta_ya_tenia_otra_orden_no_se_le_asocia_la_nueva(self):
        """R048 (0..1): la alerta activa de un escalamiento anterior ya quedó asociada a su orden (cancelada después); la orden nueva se crea sin alerta y no hay error."""
        self.escalar()
        (primera,) = self.ordenes()
        MantenimientoTecnico.objects.filter(pk=primera.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_hardware="activo")
        otro = fabricas.comando(self.actuador, self.apagar)
        self.escalar(comando=otro)
        primera.refresh_from_db()
        segunda = [o for o in self.ordenes() if o.pk != primera.pk][0]
        self.assertEqual(primera.alerta_id, self.alerta().pk)
        self.assertIsNone(segunda.alerta_id)
        self.assertEqual(AlertaIot.objects.filter(hardware=self.actuador).count(), 1)
