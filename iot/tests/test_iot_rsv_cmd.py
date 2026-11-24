# Pruebas de IOT-RSV-CMD · Resolver Comando, sin la orden de mantenimiento (docs/casos_de_uso/iot/resolver_comando.md, v0.2, con «Cómo se aplica en la ronda «IoT 1»») y de lo que cita:
# D-77 (el contrato), D-78 (puntos 1 a 5, 10, 11 y 12), D-71 (el correo lo manda la revisión), D-36 y D-75 (punto 1). Se escribieron ANTES que el servicio.
# La orden de mantenimiento (postcondiciones k y l, extensiones 4b.4, 4b.4a y 4b.4b) es de IOT-07: acá se prueba que NO se crea.
#
# Servicios que se prueban (iot/servicios/comandos.py), tomados del módulo dentro de cada prueba:
#   retirar_comandos(sistema_id, ahora) -> Retiro(modo, comandos)                  cada comando: EntregaDeComando(id, identificador, comando, valor, intento, espera_segundos)
#       ``iot.servicios.nodo.SistemaDesconectado`` si el sistema ya no está activo (extensión *a).
#   registrar_resultado(sistema_id, comando_id, ResultadoRecibido(resultado, detalle, estado, informado_en), ahora) -> ResultadoDeComando(resultado, estado_comando)
#       ``resultado`` es ``aceptado`` o ``ya_resuelto``; ``ComandoInexistente`` en la extensión 4e y en D-78 punto 12 (nunca entregado); ``SistemaDesconectado`` como arriba.
#   estados.explica_un_comando(actuador, estado) -> bool                              (D-78, punto 4; completa lo de IOT-03)
# La comunicación del nodo la registra el propio servicio (postcondición a), en la misma transacción, DESPUÉS de leer la anterior (D-78, punto 2).

import logging
from datetime import datetime, timedelta, timezone as zona
from unittest import mock

from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import AlertaIot, Comando, NodoCentral, RegistroComando
from iot.servicios.nodo import SistemaDesconectado
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

comandos = perezoso("iot.servicios.comandos")
estados = perezoso("iot.servicios.estados")
AHORA = datetime(2026, 11, 23, 15, 0, tzinfo=zona.utc)
VENTILADOR = [("Encender", "ENCENDER"), ("Apagar", "APAGAR"), ("Fijar velocidad", "FIJAR_NIVEL", 0, 100, "%")]


def resultado(que="ejecutado", detalle="", estado=None, informado_en=None):
    """Lo que el nodo informó, ya traducido."""
    return comandos.ResultadoRecibido(resultado=que, detalle=detalle, estado=estado, informado_en=informado_en)


class IotRsvCmdServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Postcondiciones a a j y m a q, extensiones *a, 2a, 2a.1a, 2b, 2c, 2d, 4a, 4b (sin 4b.4), 4c, 4d, 4e y 4f, y las reglas de IOT-RSV-CMD."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.tipo = fabricas.tipo_actuador("Extractor", acciones=VENTILADOR)
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/extractor", ultimo_mensaje_en=AHORA - timedelta(hours=1))
        self.encender, self.apagar, self.velocidad = self.tipo.acciones.order_by("id")
        self.comunicado_hace(30)
        self.config = configuracion.obtener()  # 3 reintentos (4 intentos) e intervalo de 60 s
        self.comando = fabricas.comando(self.actuador, self.encender, agronomo=self.laura)

    # ---- ayudas ----

    def comunicado_hace(self, segundos):
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=AHORA - timedelta(seconds=segundos) if segundos is not None else None)

    def retirado(self, hace, intentos=1, comando=None):
        """El comando fue retirado por última vez hace ``hace`` segundos, en su intento ``intentos``."""
        Comando.objects.filter(pk=(comando or self.comando).pk).update(cantidad_intentos=intentos, ultimo_intento_en=AHORA - timedelta(seconds=hace))

    def retirar(self, ahora=AHORA):
        return comandos.retirar_comandos(self.sistema.pk, ahora)

    def resolver(self, que="ejecutado", comando=None, ahora=AHORA, **extra):
        return comandos.registrar_resultado(self.sistema.pk, (comando or self.comando).pk, resultado(que, **extra), ahora)

    def recargar(self):
        for objeto in (self.comando, self.actuador, self.nodo):
            objeto.refresh_from_db()

    def registros(self, **filtro):
        return list(RegistroComando.objects.filter(comando=self.comando, **filtro).order_by("pk"))

    def alerta(self, tipo):
        return Alerta.objects.filter(tipo_alerta=tipo, estado_alerta="activa").first()

    def auditorias(self):
        return RegistroAuditoria.objects.filter(accion="resolucion_comando_iot")

    def ids(self, retiro):
        return [c.id for c in retiro.comandos]

    # ================= el retiro =================

    def test_post_a_el_retiro_registra_la_comunicacion_del_nodo(self):
        """Postcondición a: la comunicación queda registrada con ``ahora`` y el nodo, «en línea»."""
        self.comunicado_hace(None)
        self.retirar()
        self.nodo.refresh_from_db()
        self.assertEqual(self.nodo.ultima_comunicacion, AHORA)

    def test_post_a_el_retiro_resuelve_nodo_sin_comunicacion(self):
        """Postcondición a (como en IOT-03): una alerta «nodo sin comunicación» activa se resuelve con el retiro."""
        self.comunicado_hace(3600)
        from iot.servicios import alertas_iot

        alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, "iot_nodo_sin_comunicacion", f"nodo:{self.nodo.pk}", "Nodo sin comunicación")
        self.retirar()
        self.assertIsNone(self.alerta("iot_nodo_sin_comunicacion"))

    def test_post_b_cada_comando_entregado_suma_un_intento_y_registra_el_ultimo_intento(self):
        """Postcondición b: +1 intento y ``ultimo_intento_en`` = ahora."""
        self.retirar()
        self.recargar()
        self.assertEqual((self.comando.cantidad_intentos, self.comando.ultimo_intento_en, self.comando.estado_comando), (1, AHORA, "pendiente"))

    def test_paso_2_la_entrega_trae_lo_que_dice_el_contrato(self):
        """Paso 2 y ``mensajes.md``, sección 5: id, identificador del actuador, comando del catálogo, valor, intento y la espera (el intervalo de la configuración)."""
        con_valor = fabricas.actuador(self.sistema, self.tipo, "norte/otro")
        pedido = fabricas.comando(con_valor, self.velocidad, valor_comando=60)
        retiro = self.retirar()
        por_id = {c.id: c for c in retiro.comandos}
        self.assertEqual(retiro.modo, "remoto")
        entrega = por_id[self.comando.pk]
        self.assertEqual((entrega.identificador, entrega.comando, entrega.valor, entrega.intento, entrega.espera_segundos), ("norte/extractor", "ENCENDER", None, 1, 60))
        con = por_id[pedido.pk]
        self.assertEqual((con.identificador, con.comando, con.valor, con.intento), ("norte/otro", "FIJAR_NIVEL", 60, 1))

    def test_regla_el_retiro_no_se_registra_en_la_bitacora_ni_se_audita(self):
        """Regla «Bitácora» y «Cómo se aplica»: «El retiro del comando no se registra»; la entrega sola no se audita."""
        self.retirar()
        self.assertEqual((RegistroComando.objects.count(), self.auditorias().count()), (0, 0))

    def test_ext_2b_sin_comandos_responde_la_lista_vacia(self):
        """Extensión 2b: no hay comandos disponibles."""
        Comando.objects.all().update(estado_comando="cancelado", resuelto_en=AHORA)
        retiro = self.retirar()
        self.assertEqual((retiro.modo, retiro.comandos), ("remoto", []))

    def test_regla_comando_disponible_uno_dentro_de_su_espera_no_se_vuelve_a_entregar(self):
        """Regla «Comando disponible»: retirado hace 20 s con 60 s de espera, no se entrega y no consume intentos."""
        self.retirado(20)
        self.assertEqual(self.ids(self.retirar()), [])
        self.recargar()
        self.assertEqual(self.comando.cantidad_intentos, 1)

    def test_regla_comando_disponible_dos_retiros_seguidos_lo_entregan_una_sola_vez(self):
        """Ejemplos ``comandos_retiro`` y ``comandos_retiro_vacio``: el segundo retiro, enseguida, viene vacío."""
        self.assertEqual(self.ids(self.retirar()), [self.comando.pk])
        self.assertEqual(self.ids(self.retirar(AHORA + timedelta(seconds=5))), [])

    def test_regla_comando_disponible_el_nodo_solo_retira_los_de_su_sistema(self):
        """Garantía mínima: el nodo solo retira comandos de los actuadores de su propio sistema IoT."""
        sur = crear_invernadero("Sur", agronomo=crear_agronomo("otro@infoponia.com"))
        ajeno = fabricas.comando(fabricas.actuador(fabricas.sistema(sur), self.tipo, "sur/extractor"), self.encender)
        self.assertEqual(self.ids(self.retirar()), [self.comando.pk])
        ajeno.refresh_from_db()
        self.assertEqual(ajeno.cantidad_intentos, 0)

    def test_ext_2d_en_modo_local_no_entrega_ni_consume_intentos_pero_registra_la_comunicacion(self):
        """Extensión 2d: el modo local registra la comunicación y no entrega; los pendientes no consumen intentos."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local", ultima_comunicacion=None)
        retiro = self.retirar()
        self.assertEqual((retiro.modo, retiro.comandos), ("local", []))
        self.recargar()
        self.assertEqual((self.comando.cantidad_intentos, self.comando.ultimo_intento_en, self.nodo.ultima_comunicacion), (0, None, AHORA))

    def test_ext_2d_en_modo_local_no_revisa_vencimientos(self):
        """Extensión 2d: «No se toca ningún comando»: un intento vencido tampoco se resuelve mientras el nodo está en local."""
        self.retirado(500)
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local")
        self.retirar()
        self.recargar()
        self.assertEqual((self.comando.cantidad_intentos, self.comando.estado_comando, RegistroComando.objects.count()), (1, "pendiente", 0))

    def test_ext_2d_al_volver_a_remoto_se_entrega_con_el_intento_uno(self):
        """Extensión 2d y regla «Estado inicial e intentos»: sin consumir intentos en local, al volver el primer intento es el 1."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local")
        self.retirar()
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="remoto")
        self.assertEqual([c.intento for c in self.retirar().comandos], [1])

    def test_ext_asterisco_a_un_sistema_desconectado_no_entrega_ni_registra(self):
        """Extensión *a: con el sistema desconectado se rechaza sin registrar ningún cambio (ni siquiera la comunicación)."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        with self.assertRaises(SistemaDesconectado):
            self.retirar()
        self.recargar()
        self.assertEqual(self.comando.cantidad_intentos, 0)
        self.assertNotEqual(self.nodo.ultima_comunicacion, AHORA)

    # ---- 2c ----

    def test_ext_2c_el_comando_de_un_actuador_que_no_esta_activo_se_cancela_y_no_se_entrega(self):
        """Extensión 2c: el pendiente de un actuador fuera de servicio pasa a «cancelado» (``resuelto_en`` = ahora), con su registro, y no se entrega."""
        for estado in ("fuera_de_servicio", "inactivo"):
            Comando.objects.filter(pk=self.comando.pk).update(estado_comando="pendiente", resuelto_en=None)
            RegistroComando.objects.all().delete()
            type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_hardware=estado)
            self.assertEqual(self.ids(self.retirar()), [])
            self.recargar()
            self.assertEqual((self.comando.estado_comando, self.comando.resuelto_en), ("cancelado", AHORA))
            registro = self.registros()[0]
            self.assertEqual((registro.resultado, registro.responsable_id), ("cancelado", None))
            self.assertIn("fuera de servicio" if estado == "fuera_de_servicio" else "dado de baja", registro.descripcion_evento)

    def test_ext_2c_se_audita_con_actor_none_origen_nodo_central_y_se_sigue_con_los_demas(self):
        """Extensión 2c y postcondición q: ``resolucion_comando_iot`` con actor ``None`` y origen «nodo_central»; los demás comandos se entregan igual."""
        otro = fabricas.actuador(self.sistema, self.tipo, "norte/otro", ultimo_mensaje_en=AHORA)
        entregable = fabricas.comando(otro, self.encender)
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_hardware="fuera_de_servicio")
        self.assertEqual(self.ids(self.retirar()), [entregable.pk])
        auditoria = self.auditorias().get()
        self.assertIsNone(auditoria.usuario_id)
        self.assertEqual(auditoria.detalle["datos"]["origen"], "nodo_central")
        self.assertIn(("iot.comando", self.comando.pk), {(a["modelo"], a["id"]) for a in auditoria.afectados})

    # ---- regla 4 de IOT-CNL-CMD: un cancelado no se reintenta ----

    def test_regla_4_de_cnl_un_comando_cancelado_no_se_entrega_ni_se_reintenta(self):
        """IOT-CNL-CMD regla 4: un cancelado no se reintenta; el retiro no lo entrega, ni siquiera con el último intento vencido."""
        self.retirado(500)
        comandos.cancelar_comando(self.laura, self.comando.pk, AHORA)
        self.assertEqual(self.ids(self.retirar(AHORA + timedelta(seconds=10))), [])
        self.recargar()
        self.assertEqual((self.comando.estado_comando, self.comando.cantidad_intentos), ("cancelado", 1))

    # ---- 2a: intento vencido ----

    def test_ext_2a_un_intento_vencido_con_el_nodo_en_linea_es_un_intento_fallido_sin_respuesta(self):
        """Extensión 2a y D-78 puntos 1 y 3: con intentos restantes sigue pendiente, ``resultado_comando = sin_respuesta`` y un registro ``intento_fallido`` con su número y «Sin respuesta»."""
        self.retirado(70, intentos=1)
        retiro = self.retirar()
        self.assertEqual([c.intento for c in retiro.comandos], [2])  # se vuelve a entregar, ahora en el intento 2
        self.recargar()
        self.assertEqual((self.comando.estado_comando, self.comando.resultado_comando, self.comando.cantidad_intentos), ("pendiente", "sin_respuesta", 2))
        registro = self.registros()[0]
        self.assertEqual((registro.resultado, registro.numero_intento), ("intento_fallido", 1))
        self.assertIn("Sin respuesta", registro.descripcion_evento)

    def test_ext_2a_justo_al_vencer_el_intervalo_ya_cuenta_como_vencido(self):
        """D-78 punto 1: ``ultimo_intento_en + intervalo <= ahora``."""
        self.retirado(60)
        self.assertEqual([c.intento for c in self.retirar().comandos], [2])

    def test_ext_2a_el_intento_vencido_se_audita(self):
        """Decisión del estudiante: se audita cada hecho que crea bitácora; un intento «sin respuesta» con intentos restantes crea la suya."""
        self.retirado(70)
        self.retirar()
        auditoria = self.auditorias().get()
        self.assertIsNone(auditoria.usuario_id)
        self.assertEqual(auditoria.detalle["datos"]["origen"], "nodo_central")
        self.assertIn(("iot.comando", self.comando.pk), {(a["modelo"], a["id"]) for a in auditoria.afectados})

    def test_ext_2a_1a_un_intento_vencido_con_el_nodo_sin_senal_se_descuenta(self):
        """Extensión 2a.1a y D-78 punto 2: si entre la comunicación anterior y ahora pasaron más que ``minutos_sin_comunicacion`` (3), el intento no cuenta: ``cantidad_intentos − 1`` y el comando vuelve a estar disponible en ese mismo retiro, con el mismo número de intento."""
        self.retirado(600, intentos=2)
        self.comunicado_hace(600)
        retiro = self.retirar()
        self.assertEqual([c.intento for c in retiro.comandos], [2])  # 2 − 1 + 1
        self.recargar()
        self.assertEqual((self.comando.cantidad_intentos, self.comando.resultado_comando, self.comando.estado_comando), (2, None, "pendiente"))

    def test_ext_2a_1a_el_descuento_no_deja_bitacora_ni_alerta_ni_cambia_al_actuador(self):
        """Regla «Revisión de vencimientos»: una caída del nodo no deja actuadores fuera de servicio ni genera alertas ni bitácora."""
        self.retirado(600, intentos=4)  # el último intento: sin el descuento, escalaría
        self.comunicado_hace(600)
        self.retirar()
        self.recargar()
        self.assertEqual((self.comando.estado_comando, self.actuador.estado_hardware, RegistroComando.objects.count()), ("pendiente", "activo", 0))
        self.assertIsNone(self.alerta("iot_comando_fallido"))
        self.assertEqual(self.auditorias().count(), 0)

    def test_ext_2a_1a_el_umbral_es_la_configuracion_operativa(self):
        """D-78 punto 2: «sin señal» es más que ``minutos_sin_comunicacion``; con 2 minutos entre medio y el parámetro en 3, el nodo no estuvo sin señal."""
        self.retirado(200, intentos=1)
        self.comunicado_hace(120)
        retiro = self.retirar()
        self.assertEqual([c.intento for c in retiro.comandos], [2])
        self.assertEqual(self.registros()[0].resultado, "intento_fallido")  # sí contó

    def test_ext_2a_el_ultimo_intento_sin_respuesta_escala(self):
        """Extensión 2a, D-78 puntos 1 y 10 y 4b: al agotarse los intentos sin respuesta, el comando pasa a «fallido» con ``resultado_comando = sin_respuesta``, el actuador queda fuera de servicio, se genera la alerta crítica y no se entrega."""
        self.retirado(70, intentos=4)
        retiro = self.retirar()
        self.assertEqual(retiro.comandos, [])
        self.recargar()
        self.assertEqual((self.comando.estado_comando, self.comando.resultado_comando, self.comando.resuelto_en), ("fallido", "sin_respuesta", AHORA))
        self.assertEqual(self.actuador.estado_hardware, "fuera_de_servicio")
        self.assertIsNotNone(self.alerta("iot_comando_fallido"))
        self.assertEqual([r.resultado for r in self.registros()], ["fallido"])

    def test_ext_2a_con_un_solo_reintento_configurado_el_segundo_intento_es_el_ultimo(self):
        """Regla «Intentos»: 1 + ``cant_reintentos_comando`` (con 1, dos intentos)."""
        self.config.cant_reintentos_comando = 1
        self.config.save()
        self.retirado(70, intentos=2)
        self.retirar()
        self.recargar()
        self.assertEqual(self.comando.estado_comando, "fallido")

    # ---- un intento que el nodo SÍ respondió con «falló» no es un intento «sin respuesta» (hallado por el recorrido de IOT-05) ----

    def test_ext_2a_un_intento_que_el_nodo_respondio_con_fallo_no_se_da_por_sin_respuesta_al_vencer(self):
        """Extensiones 2a y 4a: el intento 1 falló y el nodo lo informó (registro ``intento_fallido`` n.º 1). Al pasar la espera, el retiro lo entrega de nuevo como intento 2 SIN
        registrar otro «Sin respuesta» ni pisar el último resultado: el nodo respondió, no se calló."""
        self.retirado(10, intentos=1)
        self.resolver("fallo", detalle="Relé trabado")
        retiro = self.retirar(AHORA + timedelta(seconds=61))
        self.assertEqual([c.intento for c in retiro.comandos], [2])
        self.recargar()
        self.assertEqual((self.comando.resultado_comando, self.comando.detalle_resultado, self.comando.cantidad_intentos), ("fallo", "Relé trabado", 2))
        self.assertEqual([(r.resultado, r.numero_intento) for r in self.registros()], [("intento_fallido", 1)])

    def test_ext_2a_1a_un_intento_respondido_con_fallo_no_se_descuenta_aunque_el_nodo_haya_estado_sin_senal(self):
        """Extensión 2a.1a: solo se descuenta un intento cuyo vencimiento se debe al nodo. Si el nodo respondió «falló» y después estuvo sin señal, ese intento ya se gastó."""
        self.retirado(10, intentos=1)
        self.resolver("fallo", detalle="x")
        self.comunicado_hace(600)
        retiro = self.retirar(AHORA + timedelta(seconds=600))
        self.assertEqual([c.intento for c in retiro.comandos], [2])  # y no 1: no se le devolvió el intento

    def test_ext_2a_un_intento_sin_respuesta_despues_de_uno_que_fallo_si_se_da_por_vencido(self):
        """El intento 2 no tuvo respuesta (el 1 sí falló): al vencer queda su propio registro «Sin respuesta», con su número 2."""
        self.retirado(10, intentos=1)
        self.resolver("fallo", detalle="x")
        self.retirar(AHORA + timedelta(seconds=61))  # entrega el intento 2
        self.retirar(AHORA + timedelta(seconds=140))  # el 2 venció sin respuesta
        self.assertEqual([(r.resultado, r.numero_intento) for r in self.registros()], [("intento_fallido", 1), ("intento_fallido", 2)])
        self.recargar()
        self.assertEqual((self.comando.resultado_comando, self.comando.cantidad_intentos), ("sin_respuesta", 3))

    # ================= el resultado =================

    def test_post_c_ejecutado_pasa_a_ejecutado_con_el_resultado_y_la_recepcion(self):
        """Postcondición c: ``ejecutado``, con el detalle que informó el nodo y ``resuelto_en`` = ahora."""
        self.retirado(10)
        respuesta = self.resolver(detalle="Velocidad al 60 %.")
        self.recargar()
        self.assertEqual((respuesta.resultado, respuesta.estado_comando), ("aceptado", "ejecutado"))
        self.assertEqual((self.comando.estado_comando, self.comando.resultado_comando, self.comando.detalle_resultado, self.comando.resuelto_en), ("ejecutado", "ejecutado", "Velocidad al 60 %.", AHORA))

    def test_post_c_el_estado_que_informa_el_resultado_pasa_a_ser_el_estado_informado(self):
        """Postcondición c y D-78 punto 4: el estado y la hora de ``informado_en``, y ``cambiado_en_invernadero`` falso (aunque antes fuera verdadero)."""
        self.retirado(10)
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_informado="apagado", estado_informado_en=AHORA - timedelta(hours=2), cambiado_en_invernadero=True)
        informado = AHORA - timedelta(seconds=2)
        self.resolver(estado="encendido", informado_en=informado)
        self.recargar()
        self.assertEqual((self.actuador.estado_informado, self.actuador.estado_informado_en, self.actuador.cambiado_en_invernadero), ("encendido", informado, False))

    def test_post_c_sin_informado_en_usa_la_hora_de_recepcion(self):
        """``mensajes.md``, sección 6: si ``informado_en`` falta, la de recepción."""
        self.retirado(10)
        self.resolver(estado="encendido")
        self.recargar()
        self.assertEqual(self.actuador.estado_informado_en, AHORA)

    def test_post_c_sin_estado_el_estado_informado_no_cambia(self):
        """Postcondición c: «si el nodo informó el estado»; si no, no se toca."""
        self.retirado(10)
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_informado="apagado", estado_informado_en=AHORA - timedelta(hours=2))
        self.resolver()
        self.recargar()
        self.assertEqual((self.actuador.estado_informado, self.actuador.estado_informado_en), ("apagado", AHORA - timedelta(hours=2)))

    def test_post_c_el_resultado_carga_el_ultimo_mensaje_del_actuador_y_la_comunicacion_del_nodo(self):
        """«Lo que esto completa»: ``ultimo_mensaje_en`` del actuador también lo carga un resultado; y el resultado es una comunicación del nodo."""
        self.retirado(10)
        self.comunicado_hace(None)
        self.resolver()
        self.recargar()
        self.assertEqual((self.actuador.ultimo_mensaje_en, self.nodo.ultima_comunicacion), (AHORA, AHORA))

    def test_post_d_ejecutado_crea_el_registro_de_bitacora_con_el_resultado(self):
        """Postcondición d y D-78 punto 3: un RegistroComando ``ejecutado``, sin lote, sin responsable (lo hizo el nodo), con el actuador y la acción."""
        self.retirado(10)
        self.resolver(detalle="Listo")
        registro = self.registros()[0]
        self.assertEqual((registro.resultado, registro.responsable_id, registro.lote_id, registro.tipo_evento), ("ejecutado", None, None, "comando"))
        self.assertIn("norte/extractor", registro.descripcion_evento)
        self.assertIn("Encender", registro.descripcion_evento)

    def test_post_e_ejecutado_resuelve_dispositivo_sin_actividad_y_deja_de_estar_sin_confirmar(self):
        """Postcondición e: la alerta «dispositivo sin actividad» pasa a resuelta y el actuador deja de estar «sin confirmar»."""
        from iot.servicios import alertas_iot

        self.retirado(10)
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(ultimo_mensaje_en=None)
        alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, "iot_dispositivo_sin_actividad", f"hw:{self.actuador.pk}", "Sin actividad", hardware=self.actuador)
        self.resolver()
        self.recargar()
        self.assertIsNone(self.alerta("iot_dispositivo_sin_actividad"))
        self.assertIsNotNone(self.actuador.ultimo_mensaje_en)

    def test_post_q_ejecutado_se_audita_con_actor_none_y_los_cambios(self):
        """Postcondición q: ``resolucion_comando_iot``, actor ``None``, origen «nodo_central», con el comando, el registro de bitácora y el cambio de estado."""
        self.retirado(10)
        self.resolver(estado="encendido")
        auditoria = self.auditorias().get()
        self.assertIsNone(auditoria.usuario_id)
        self.assertEqual(auditoria.detalle["datos"]["origen"], "nodo_central")
        self.assertEqual(auditoria.detalle["cambios"]["estado_comando"], {"antes": "pendiente", "despues": "ejecutado"})
        afectados = {(a["modelo"], a["id"]) for a in auditoria.afectados}
        self.assertIn(("iot.comando", self.comando.pk), afectados)
        self.assertIn(("iot.registrocomando", self.registros()[0].pk), afectados)

    def test_garantia_si_falla_la_auditoria_no_se_registra_el_resultado(self):
        """Garantía mínima: el resultado, la bitácora y los logs se registran juntos o no se registra ninguno."""
        self.retirado(10)
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.resolver()
        self.recargar()
        self.assertEqual((self.comando.estado_comando, RegistroComando.objects.count()), ("pendiente", 0))

    # ---- 4a: falla con intentos restantes ----

    def test_ext_4a_un_fallo_con_intentos_restantes_deja_el_comando_pendiente(self):
        """Extensión 4a, postcondiciones f y g: sigue pendiente con ``resultado_comando = fallo`` y su detalle; un registro ``intento_fallido`` con el número de intento y «Falló: {detalle}»."""
        self.retirado(10, intentos=1)
        respuesta = self.resolver("fallo", detalle="El variador no respondió.")
        self.recargar()
        self.assertEqual((respuesta.resultado, respuesta.estado_comando), ("aceptado", "pendiente"))
        self.assertEqual((self.comando.estado_comando, self.comando.resultado_comando, self.comando.detalle_resultado, self.comando.resuelto_en), ("pendiente", "fallo", "El variador no respondió.", None))
        registro = self.registros()[0]
        self.assertEqual((registro.resultado, registro.numero_intento), ("intento_fallido", 1))
        self.assertIn("Falló: El variador no respondió.", registro.descripcion_evento)
        self.assertEqual(self.actuador.estado_hardware, "activo")

    def test_ext_4a_no_se_vuelve_a_entregar_antes_de_que_pase_la_espera_desde_el_ultimo_intento(self):
        """«Cómo se aplica», 4a: el comando fallido no vuelve a entregarse antes de que pase la espera; después, sí, con el intento siguiente."""
        self.retirado(10, intentos=1)
        self.resolver("fallo", detalle="x")
        self.assertEqual(self.ids(self.retirar()), [])
        self.assertEqual([c.intento for c in self.retirar(AHORA + timedelta(seconds=51)).comandos], [2])

    def test_ext_4a_cada_intento_fallido_deja_su_registro_con_su_numero(self):
        """D-78 punto 3: un registro por intento fallido, con su número."""
        for intento in (1, 2, 3):
            self.retirado(10, intentos=intento)
            self.resolver("fallo", detalle=f"falla {intento}")
        self.assertEqual([(r.resultado, r.numero_intento) for r in self.registros()], [("intento_fallido", 1), ("intento_fallido", 2), ("intento_fallido", 3)])

    def test_ext_4a_el_detalle_largo_se_recorta_a_300(self):
        """Contrato: el detalle admite hasta 300 caracteres; la bitácora admite 500 y no se rompe."""
        self.retirado(10)
        self.resolver("fallo", detalle="x" * 300)
        self.assertLessEqual(len(self.registros()[0].descripcion_evento), 500)

    # ---- 4b: escalamiento ----

    def escalar(self, detalle="Sin corriente."):
        self.retirado(10, intentos=4)
        return self.resolver("fallo", detalle=detalle)

    def test_ext_4b_el_ultimo_intento_fallido_pasa_el_comando_a_fallido_y_el_actuador_a_fuera_de_servicio(self):
        """Extensión 4b, postcondiciones h e i: ``fallido`` con el último resultado y ``resuelto_en``; el actuador, ``fuera_de_servicio``."""
        respuesta = self.escalar()
        self.recargar()
        self.assertEqual((respuesta.resultado, respuesta.estado_comando), ("aceptado", "fallido"))
        self.assertEqual((self.comando.estado_comando, self.comando.resultado_comando, self.comando.resuelto_en), ("fallido", "fallo", AHORA))
        self.assertEqual(self.actuador.estado_hardware, "fuera_de_servicio")

    def test_ext_4b_genera_la_alerta_comando_fallido_critica_con_su_texto_y_origen(self):
        """Postcondición j y D-78 punto 10: clave ``hw:<id>``, origen el actuador, severidad crítica y la descripción «{identificador} · {acción} no se ejecutó en {n} intentos (último: falló: detalle)»."""
        self.escalar("Sin corriente.")
        alerta = self.alerta("iot_comando_fallido")
        self.assertEqual((alerta.clave_estado, alerta.nivel_severidad), (f"hw:{self.actuador.pk}", "critica"))
        self.assertEqual(alerta.descripcion_alerta, "norte/extractor · Encender no se ejecutó en 4 intentos (último: falló: Sin corriente.)")
        vinculo = AlertaIot.objects.get(alerta=alerta)
        self.assertEqual((vinculo.hardware_id, vinculo.sistema_id), (self.actuador.pk, self.sistema.pk))

    def test_ext_4b_el_correo_no_sale_al_generarse_lo_manda_la_revision(self):
        """Postcondición j (corregida por D-71): ``correo_enviado_en`` queda nulo; la revisión periódica manda el correo."""
        self.escalar()
        self.assertIsNone(AlertaIot.objects.get(alerta=self.alerta("iot_comando_fallido")).correo_enviado_en)

    def test_ext_4b_la_alerta_es_para_el_agronomo_o_el_gerente_sin_agronomo_activo(self):
        """Regla «Alerta «comando fallido»»: la recibe el Agrónomo del invernadero o, sin Agrónomo activo, el Gerente."""
        self.escalar()
        alerta = self.alerta("iot_comando_fallido")
        self.assertEqual(alerta.invernadero_id, self.norte.pk)

    def test_ext_4b_con_el_ultimo_resultado_sin_respuesta_el_texto_dice_sin_respuesta(self):
        """D-78 punto 10: «(último: sin respuesta)» cuando fue un vencimiento."""
        self.retirado(70, intentos=4)
        self.retirar()
        self.assertTrue(self.alerta("iot_comando_fallido").descripcion_alerta.endswith("(último: sin respuesta)"))

    def test_ext_4b_deja_el_registro_fallido_y_audita_con_la_alerta_y_el_actuador(self):
        """Postcondición m: el fallo definitivo queda en la bitácora. Postcondición q: la auditoría incluye comando, actuador, alerta y registro."""
        self.escalar()
        self.assertEqual([(r.resultado, r.numero_intento) for r in self.registros()], [("fallido", None)])
        afectados = {a["modelo"] for a in self.auditorias().get().afectados}
        self.assertTrue({"iot.comando", "iot.actuador", "maestros.alerta", "iot.registrocomando"} <= afectados)

    def test_ext_4b_hasta_iot_07_no_se_crea_la_orden_de_mantenimiento_ni_se_nombra_en_la_alerta(self):
        """«Cómo se aplica»: la orden de mantenimiento (4b.4, 4b.4a y 4b.4b) la suma IOT-07; hasta entonces no se crea y la alerta no menciona ninguna orden."""
        self.escalar()
        self.assertNotIn("orden", self.alerta("iot_comando_fallido").descripcion_alerta.lower())

    def test_ext_4b_un_segundo_escalamiento_no_duplica_la_alerta(self):
        """D-78 punto 10 y regla de alertas de estado: una activa por invernadero, tipo y clave."""
        self.escalar()
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_hardware="activo")
        otro = fabricas.comando(self.actuador, self.apagar)
        Comando.objects.filter(pk=otro.pk).update(cantidad_intentos=4, ultimo_intento_en=AHORA - timedelta(seconds=10))
        self.resolver("fallo", comando=otro, detalle="otra")
        self.assertEqual(Alerta.objects.filter(tipo_alerta="iot_comando_fallido", estado_alerta="activa").count(), 1)

    # ---- 4c y 4d ----

    def test_ext_4c_un_resultado_tardio_de_un_comando_todavia_pendiente_se_acepta(self):
        """Extensión 4c: llega después de que venció el intervalo pero el comando sigue pendiente: se acepta como respuesta del último intento."""
        self.retirado(300, intentos=1)
        respuesta = self.resolver()
        self.recargar()
        self.assertEqual((respuesta.resultado, self.comando.estado_comando), ("aceptado", "ejecutado"))

    def test_ext_4d_un_resultado_repetido_es_ya_resuelto_y_no_cambia_nada(self):
        """Extensión 4d y D-77 punto 2: el segundo resultado responde ``ya_resuelto`` con el estado final y no escribe nada más."""
        self.retirado(10)
        self.resolver()
        antes = (RegistroComando.objects.count(), self.auditorias().count())
        respuesta = self.resolver()
        self.assertEqual((respuesta.resultado, respuesta.estado_comando), ("ya_resuelto", "ejecutado"))
        self.assertEqual((RegistroComando.objects.count(), self.auditorias().count()), antes)

    def test_ext_4d_un_resultado_de_un_comando_fallido_o_cancelado_es_ya_resuelto(self):
        """Extensión 4d: ejecutado, fallido o cancelado: se ignora. Un fallido no vuelve a ser ejecutado por un resultado tardío."""
        for estado in ("fallido", "cancelado"):
            Comando.objects.filter(pk=self.comando.pk).update(estado_comando=estado, resuelto_en=AHORA, cantidad_intentos=1, ultimo_intento_en=AHORA)
            respuesta = self.resolver("ejecutado")
            self.assertEqual((respuesta.resultado, respuesta.estado_comando), ("ya_resuelto", estado))
            self.comando.refresh_from_db()
            self.assertEqual(self.comando.estado_comando, estado)

    def test_ext_4d_ya_resuelto_no_cambia_el_estado_del_actuador(self):
        """Extensión 4d: un resultado con ``estado`` para un comando ya resuelto no toca el estado informado."""
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="cancelado", resuelto_en=AHORA, cantidad_intentos=1, ultimo_intento_en=AHORA)
        self.resolver("ejecutado", estado="encendido")
        self.recargar()
        self.assertIsNone(self.actuador.estado_informado)

    # ---- 4e y D-78 punto 12 ----

    def test_ext_4e_un_comando_que_no_existe_se_rechaza_sin_registrar_nada(self):
        """Extensión 4e: ``ComandoInexistente`` y ningún cambio (ni siquiera la comunicación)."""
        self.comunicado_hace(None)
        with self.assertRaises(comandos.ComandoInexistente):
            comandos.registrar_resultado(self.sistema.pk, 99999, resultado(), AHORA)
        self.nodo.refresh_from_db()
        self.assertIsNone(self.nodo.ultima_comunicacion)

    def test_ext_4e_un_comando_de_otro_sistema_se_rechaza_como_inexistente(self):
        """Extensión 4e: el comando no es de un actuador del nodo."""
        sur = crear_invernadero("Sur", agronomo=crear_agronomo("otro@infoponia.com"))
        ajeno = fabricas.comando(fabricas.actuador(fabricas.sistema(sur), self.tipo, "sur/extractor"), self.encender, cantidad_intentos=1, ultimo_intento_en=AHORA)
        with self.assertRaises(comandos.ComandoInexistente):
            self.resolver(comando=ajeno)
        ajeno.refresh_from_db()
        self.assertEqual(ajeno.estado_comando, "pendiente")

    def test_d78_punto_12_un_resultado_de_un_comando_pendiente_nunca_entregado_es_inexistente(self):
        """D-78 punto 12: pendiente con ``cantidad_intentos = 0``: el nodo no pudo haberlo recibido; se trata como 4e y no cambia nada."""
        self.comunicado_hace(None)
        with self.assertRaises(comandos.ComandoInexistente):
            self.resolver()
        self.recargar()
        self.assertEqual((self.comando.estado_comando, RegistroComando.objects.count()), ("pendiente", 0))
        # A diferencia de 4e (se detecta antes de bloquear y no registra nada), éste se detecta DESPUÉS de bloquear y de registrar la comunicación: la registra.
        self.assertEqual(self.nodo.ultima_comunicacion, AHORA)

    def test_ext_asterisco_a_un_resultado_con_el_sistema_desconectado_se_rechaza(self):
        """Extensión *a: el nodo no puede resolver comandos de un sistema desconectado."""
        self.retirado(10)
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        with self.assertRaises(SistemaDesconectado):
            self.resolver()

    # ---- 4f: rechazo ----

    def rechazar(self, detalle="ENCENDER no está configurado."):
        self.retirado(10, intentos=1)
        return self.resolver("rechazado", detalle=detalle)

    def test_ext_4f_un_rechazo_pasa_el_comando_a_fallido_sin_reintentos_y_el_actuador_sigue_activo(self):
        """Extensión 4f, postcondición n: ``fallido`` con ``resultado_comando = rechazado``, el motivo y ``resuelto_en``; el actuador sigue «activo» aunque queden intentos."""
        respuesta = self.rechazar()
        self.recargar()
        self.assertEqual((respuesta.resultado, respuesta.estado_comando), ("aceptado", "fallido"))
        self.assertEqual((self.comando.estado_comando, self.comando.resultado_comando, self.comando.detalle_resultado, self.comando.resuelto_en), ("fallido", "rechazado", "ENCENDER no está configurado.", AHORA))
        self.assertEqual(self.actuador.estado_hardware, "activo")

    def test_ext_4f_marca_la_accion_como_incompatible_y_deja_al_actuador_incompatible(self):
        """Postcondición o y D-78 punto 5: la acción se suma a ``acciones_incompatibles`` y el actuador queda ``incompatible``."""
        self.rechazar()
        self.recargar()
        self.assertEqual(list(self.actuador.acciones_incompatibles.all()), [self.encender])
        self.assertEqual(self.actuador.compatibilidad, "incompatible")

    def test_ext_4f_genera_la_alerta_configuracion_incompatible_con_el_texto_del_estudiante(self):
        """Postcondición o: la alerta (advertencia, origen el actuador) con la descripción «{tipo} {identificador} · el nodo rechazó {COMANDO} (acción «{acción}»): {detalle}»."""
        self.rechazar("ENCENDER no está configurado.")
        alerta = self.alerta("iot_configuracion_incompatible")
        self.assertEqual(alerta.clave_estado, f"hw:{self.actuador.pk}")
        self.assertEqual(alerta.descripcion_alerta, "Extractor norte/extractor · el nodo rechazó ENCENDER (acción «Encender»): ENCENDER no está configurado.")
        self.assertEqual(AlertaIot.objects.get(alerta=alerta).hardware_id, self.actuador.pk)

    def test_ext_4f_sin_detalle_la_descripcion_no_lleva_los_dos_puntos(self):
        """El texto de la alerta sin detalle termina en «)»."""
        self.rechazar(detalle="")
        self.assertTrue(self.alerta("iot_configuracion_incompatible").descripcion_alerta.endswith("(acción «Encender»)"))

    def test_ext_4f_si_la_alerta_ya_existia_no_se_genera_otra(self):
        """Extensión 4f: «si no la tenía, genera la alerta»."""
        from iot.servicios import alertas_iot

        alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, "iot_configuracion_incompatible", f"hw:{self.actuador.pk}", "ya estaba", hardware=self.actuador)
        self.rechazar()
        self.assertEqual(Alerta.objects.filter(tipo_alerta="iot_configuracion_incompatible", estado_alerta="activa").count(), 1)

    def test_ext_4f_no_crea_orden_de_mantenimiento_ni_alerta_de_comando_fallido(self):
        """Garantía mínima: un comando que el nodo no reconoce no deja al actuador fuera de servicio ni genera orden de mantenimiento ni la alerta crítica."""
        self.rechazar()
        self.assertIsNone(self.alerta("iot_comando_fallido"))

    def test_ext_4f_deja_el_registro_rechazado_y_audita(self):
        """Postcondición p: un RegistroComando ``rechazado``. Postcondición q: auditoría con el comando, el actuador, la alerta y el registro."""
        self.rechazar()
        self.assertEqual([r.resultado for r in self.registros()], ["rechazado"])
        afectados = {a["modelo"] for a in self.auditorias().get().afectados}
        self.assertTrue({"iot.comando", "iot.actuador", "maestros.alerta", "iot.registrocomando"} <= afectados)

    def test_ext_4f_la_accion_incompatible_deja_de_ofrecerse(self):
        """Regla «Rechazo» y regla 14 de IOT-ALT-HDW: la acción deja de ofrecerse en comandos."""
        self.rechazar()
        datos = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA, actuador_id=self.actuador.pk)
        self.assertNotIn(self.encender.pk, [a.pk for a in datos.acciones])
        self.assertEqual([a.pk for a in datos.acciones_incompatibles], [self.encender.pk])

    def test_d78_punto_5_un_anuncio_que_cubre_la_accion_quita_la_marca_y_resuelve_la_alerta(self):
        """D-78 punto 5: la compatibilidad la calcula solo ``recalcular_compatibilidad`` desde el anuncio; si el anuncio cubre el comando, la marca se va (el nodo «anuncia la capacidad»)."""
        from iot.servicios import compatibilidad

        self.rechazar()
        fabricas.equipo_anunciado(self.sistema, "norte/extractor", ("ENCENDER", "APAGAR", "FIJAR_NIVEL"))
        self.actuador.refresh_from_db()
        compatibilidad.recalcular_compatibilidad([self.actuador])
        self.actuador.refresh_from_db()
        self.assertEqual((self.actuador.compatibilidad, self.actuador.acciones_incompatibles.count()), ("compatible", 0))
        self.assertIsNone(self.alerta("iot_configuracion_incompatible"))

    # ---- explica_un_comando (D-78 punto 4) ----

    def ejecutado(self, accion, valor=None, resuelto_en=None):
        return fabricas.comando(self.actuador, accion, estado="ejecutado", valor_comando=valor, resuelto_en=resuelto_en or AHORA)

    def test_d78_punto_4_un_estado_igual_al_que_deja_el_ultimo_comando_ejecutado_lo_explica(self):
        """D-78 punto 4: el último ejecutado deja exactamente ese estado y se resolvió después del estado informado anterior (o no había uno)."""
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="cancelado", resuelto_en=AHORA)
        self.ejecutado(self.encender)
        self.assertTrue(estados.explica_un_comando(self.actuador, "encendido"))

    def test_d78_punto_4_con_valor_compara_nivel_y_posicion(self):
        """D-78 punto 4: el valor va en ``nivel:<n>`` y ``posicion:<n>``."""
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="cancelado", resuelto_en=AHORA)
        self.ejecutado(self.velocidad, 60)
        self.assertTrue(estados.explica_un_comando(self.actuador, "nivel:60"))
        self.assertFalse(estados.explica_un_comando(self.actuador, "nivel:70"))

    def test_d78_punto_4_un_estado_distinto_no_lo_explica_un_comando(self):
        """D-78 punto 4: otro estado se marca «cambiado en el invernadero»."""
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="cancelado", resuelto_en=AHORA)
        self.ejecutado(self.encender)
        self.assertFalse(estados.explica_un_comando(self.actuador, "apagado"))

    def test_d78_punto_4_sin_comandos_ejecutados_no_hay_nada_que_lo_explique(self):
        """D-78 punto 4: sin comando ejecutado, no."""
        self.assertFalse(estados.explica_un_comando(self.actuador, "encendido"))

    def test_d78_punto_4_solo_cuenta_el_ultimo_ejecutado(self):
        """D-78 punto 4: «el ÚLTIMO comando ejecutado»: uno anterior que dejó ese estado no alcanza."""
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="cancelado", resuelto_en=AHORA)
        self.ejecutado(self.encender, resuelto_en=AHORA - timedelta(hours=2))
        self.ejecutado(self.apagar, resuelto_en=AHORA - timedelta(hours=1))
        self.assertFalse(estados.explica_un_comando(self.actuador, "encendido"))
        self.assertTrue(estados.explica_un_comando(self.actuador, "apagado"))

    def test_d78_punto_4_el_comando_tiene_que_ser_posterior_al_estado_informado_anterior(self):
        """D-78 punto 4: se resolvió DESPUÉS del estado informado anterior; si el nodo ya había informado algo después, no lo explica."""
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="cancelado", resuelto_en=AHORA)
        self.ejecutado(self.encender, resuelto_en=AHORA - timedelta(hours=2))
        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_informado="apagado", estado_informado_en=AHORA - timedelta(hours=1))
        self.actuador.refresh_from_db()
        self.assertFalse(estados.explica_un_comando(self.actuador, "encendido"))

    def test_d78_punto_4_un_comando_fallido_o_cancelado_no_explica_nada(self):
        """D-78 punto 4: solo cuentan los EJECUTADOS."""
        fabricas.comando(self.actuador, self.apagar, estado="fallido", resuelto_en=AHORA)
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="cancelado", resuelto_en=AHORA)
        self.assertFalse(estados.explica_un_comando(self.actuador, "apagado"))

    def test_d75_punto_1_un_estado_que_informa_el_nodo_despues_de_un_comando_ejecutado_no_queda_cambiado_en_el_invernadero(self):
        """De punta a punta con IOT-03: tras un comando ejecutado, el estado que informa el nodo por ``estados`` no se marca; si es otro, sí."""
        from iot.api.traduccion import EstadoRecibido

        type(self.actuador).objects.filter(pk=self.actuador.pk).update(estado_informado="apagado", estado_informado_en=AHORA - timedelta(hours=3))
        self.retirado(10)
        self.resolver()  # ejecutado, sin estado
        mismo = EstadoRecibido(0, "norte/extractor", "norte/extractor", "encendido", None)
        estados.registrar_estado(self.sistema.pk, mismo, AHORA + timedelta(seconds=5))
        self.actuador.refresh_from_db()
        self.assertFalse(self.actuador.cambiado_en_invernadero)
        otro = EstadoRecibido(1, "norte/extractor", "norte/extractor", "apagado", None)
        estados.registrar_estado(self.sistema.pk, otro, AHORA + timedelta(seconds=10))
        self.actuador.refresh_from_db()
        self.assertTrue(self.actuador.cambiado_en_invernadero)

    # ---- bitácora y varios ----

    def test_regla_bitacora_la_descripcion_lleva_tipo_identificador_accion_valor_y_que_paso(self):
        """D-78 punto 3: «{tipo} {identificador}: {acción}[ {valor} {unidad}] · {qué pasó}», hasta 500."""
        otro = fabricas.actuador(self.sistema, self.tipo, "norte/otro", ultimo_mensaje_en=AHORA)
        con_valor = fabricas.comando(otro, self.velocidad, valor_comando=60, cantidad_intentos=1, ultimo_intento_en=AHORA - timedelta(seconds=5))
        self.resolver("ejecutado", comando=con_valor)
        registro = RegistroComando.objects.get(comando=con_valor)
        self.assertTrue(registro.descripcion_evento.startswith("Extractor norte/otro: Fijar velocidad 60 % · "))
