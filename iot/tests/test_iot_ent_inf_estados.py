# Pruebas de IOT-ENT-INF, parte de los estados y del modo del nodo (IOT-03; docs/casos_de_uso/iot/entregar_informacion.md). Este archivo se
# escribe por pasos de la tarea: el paso 2 trae `IotEntInfModoServicioTests` (extensión 1b, postcondición q); el paso 4 suma
# `IotEntInfEstadosServicioTests` (extensión 1a, postcondiciones m a p). Se escribieron ANTES que el servicio (`.claude/rules/pruebas.md`).
#
# Servicios que se prueban (iot/servicios/nodo.py):
#   registrar_modo(sistema_id, modo, ahora) -> bool            (``True`` si el modo cambió; no escribe ni audita si no cambió)
#   al_volver_a_remoto(sistema)                               (vacía hasta IOT-06: «Se completa en IOT-06»)
# iot/servicios/estados.py:
#   registrar_estado(sistema_id, estado, ahora) -> ResultadoDeEstado(resultado, motivo, detalle)     (``aceptado`` o ``rechazado``)
#   explica_un_comando(actuador, estado) -> bool                                                     (falso hasta IOT-05)

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.api.traduccion import EstadoRecibido
from iot.models import AlertaIot, NodoCentral
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

nodo = perezoso("iot.servicios.nodo")
estados = perezoso("iot.servicios.estados")
alertas_iot = perezoso("iot.servicios.alertas_iot")

AHORA = datetime(2026, 11, 21, 17, 5, 0, tzinfo=timezone.utc)


class IotEntInfModoServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Extensión 1b y postcondición q: el nodo informa su modo (``remoto`` o ``local``) y InfoPonia lo registra."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)

    def auditorias(self):
        return RegistroAuditoria.objects.filter(accion="entrega_informacion_iot")

    def test_post_q_el_modo_informado_queda_registrado(self):
        """Postcondición q: si el nodo informó su modo, quedó registrado («remoto» o «local»); el servicio dice que cambió."""
        self.assertEqual(self.nodo.modo, "remoto")
        self.assertTrue(nodo.registrar_modo(self.sistema.pk, "local", AHORA))
        self.nodo.refresh_from_db()
        self.assertEqual(self.nodo.modo, "local")
        self.assertTrue(nodo.registrar_modo(self.sistema.pk, "remoto", AHORA))
        self.nodo.refresh_from_db()
        self.assertEqual(self.nodo.modo, "remoto")

    def test_ext_1b_repetir_el_modo_devuelve_cambio_falso_y_no_escribe_ni_audita(self):
        """Mensajes.md, sección 3: `cambio` es falso si el nodo ya estaba en ese modo, y repetirlo no hace nada (sin auditoría)."""
        self.assertFalse(nodo.registrar_modo(self.sistema.pk, "remoto", AHORA))
        self.assertEqual(self.auditorias().count(), 0)
        nodo.registrar_modo(self.sistema.pk, "local", AHORA)
        antes = self.auditorias().count()
        self.assertFalse(nodo.registrar_modo(self.sistema.pk, "local", AHORA))
        self.assertEqual(self.auditorias().count(), antes)

    def test_post_z_un_cambio_de_modo_se_audita_con_actor_none_y_el_formato_de_d36(self):
        """Postcondición z y D-36: un registro `entrega_informacion_iot`, actor `None`; `datos` con origen, sistema (referencia), mensaje, identificador y
        las alertas; `cambios` solo con el modo antes y después; afectado, el nodo."""
        nodo.registrar_modo(self.sistema.pk, "local", AHORA)
        [registro] = self.auditorias()
        self.assertIsNone(registro.usuario)
        self.assertEqual(registro.rol, "infoponia")
        self.assertEqual(set(registro.detalle), {"datos", "cambios"})
        self.assertEqual(
            registro.detalle["datos"],
            {
                "origen": "nodo_central",
                "sistema": {"id": self.sistema.pk, "texto": str(self.sistema)},
                "mensaje": "modo",
                "identificador": None,
                "alertas_generadas": [],
                "alertas_resueltas": [],
            },
        )
        self.assertEqual(registro.detalle["cambios"], {"modo": {"antes": "remoto", "despues": "local"}})
        self.assertEqual([(a["modelo"], a["id"]) for a in registro.afectados], [("iot.nodocentral", self.nodo.pk)])

    def test_ext_1b3_al_volver_a_remoto_se_llama_a_al_volver_a_remoto_con_el_sistema(self):
        """Extensión 1b.3: si el modo volvió a `remoto`, el servicio llama a `al_volver_a_remoto(sistema)` (IOT-06 la completa). Con otro cambio o sin
        cambio, no la llama."""
        with mock.patch("iot.servicios.nodo.al_volver_a_remoto") as volver:
            nodo.registrar_modo(self.sistema.pk, "local", AHORA)
            nodo.registrar_modo(self.sistema.pk, "local", AHORA)
            volver.assert_not_called()
            nodo.registrar_modo(self.sistema.pk, "remoto", AHORA)
            nodo.registrar_modo(self.sistema.pk, "remoto", AHORA)
        volver.assert_called_once()
        self.assertEqual(volver.call_args.args[0].pk, self.sistema.pk)

    def test_ext_1b3_al_volver_a_remoto_no_hace_nada_hasta_iot_06(self):
        """«Reparto»: `al_volver_a_remoto` queda escrita sin hacer nada (dice «Se completa en IOT-06»): una regla cumplida sigue cumplida."""
        sensor = fabricas.sensor(self.sistema, "norte/temp")
        regla = fabricas.regla(sensor, fabricas.actuador(self.sistema, identificador="norte/vent"), ultima_evaluacion="cumplida", contador_confirmacion=2)
        nodo.al_volver_a_remoto(self.sistema)
        regla.refresh_from_db()
        self.assertEqual((regla.ultima_evaluacion, regla.contador_confirmacion), ("cumplida", 2))

    def test_ext_astar_a_un_sistema_desconectado_no_se_le_registra_el_modo(self):
        """Extensión *a: un sistema desconectado no acepta mensajes (el servicio relee el estado ya bloqueado): `SistemaDesconectado`, sin cambios."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        with self.assertRaises(nodo.SistemaDesconectado):
            nodo.registrar_modo(self.sistema.pk, "local", AHORA)
        self.nodo.refresh_from_db()
        self.assertEqual(self.nodo.modo, "remoto")
        self.assertEqual(self.auditorias().count(), 0)


class IotEntInfEstadosServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Extensión 1a y postcondiciones m a p y t: el nodo informa el estado de un equipo (D-75, puntos 1 y 6)."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.humedad = fabricas.sensor(self.sistema, "norte/sectorA/humedad", "humedad")
        self.ventilador = fabricas.actuador(self.sistema, identificador="norte/sectorA/ventilador")
        self.n = 0

    def informar(self, identificador, estado, informado_en=None, ahora=AHORA):
        recibido = EstadoRecibido(self.n, identificador, identificador.strip(), estado, informado_en)
        self.n += 1
        return estados.registrar_estado(self.sistema.pk, recibido, ahora)

    def alertas(self, tipo):
        return Alerta.objects.filter(tipo_alerta=tipo, estado_alerta="activa")

    def auditorias(self):
        return RegistroAuditoria.objects.filter(accion="entrega_informacion_iot")

    def recargar(self):
        self.humedad.refresh_from_db()
        self.ventilador.refresh_from_db()

    def test_post_m_en_linea_resuelve_la_alerta_sin_actividad(self):
        """Postcondición m: «en línea» resuelve «dispositivo sin actividad» del equipo, si la tenía."""
        alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, "iot_dispositivo_sin_actividad", f"hw:{self.humedad.pk}", "x", hardware=self.humedad)
        self.assertEqual(self.informar("norte/sectorA/humedad", "en_linea").resultado, "aceptado")
        self.assertFalse(self.alertas("iot_dispositivo_sin_actividad").exists())

    def test_post_n_desconectado_genera_la_alerta_sin_actividad_una_sola_vez(self):
        """Postcondición n: «desconectado» genera «dispositivo sin actividad» con origen en el equipo y el texto «{id} · el nodo lo informó desconectado»."""
        self.informar("norte/sectorA/humedad", "desconectado")
        self.informar("norte/sectorA/humedad", "desconectado")
        [alerta] = self.alertas("iot_dispositivo_sin_actividad")
        self.assertEqual(alerta.descripcion_alerta, "norte/sectorA/humedad · el nodo lo informó desconectado")
        self.assertEqual(AlertaIot.objects.get(alerta=alerta).hardware_id, self.humedad.pk)

    def test_post_o_en_falla_pasa_el_equipo_a_fuera_de_servicio_y_genera_la_alerta_critica(self):
        """Postcondición o: «en falla» pasa el equipo a «fuera de servicio» y genera «dispositivo en falla» (crítica, sin correo todavía); no crea una orden de mantenimiento."""
        self.informar("norte/sectorA/humedad", "en_falla")
        self.recargar()
        self.assertEqual(self.humedad.estado_hardware, "fuera_de_servicio")
        [alerta] = self.alertas("iot_dispositivo_en_falla")
        vinculo = AlertaIot.objects.get(alerta=alerta)
        self.assertEqual((alerta.nivel_severidad, vinculo.correo_enviado_en, vinculo.hardware_id), ("critica", None, self.humedad.pk))
        self.assertEqual(alerta.descripcion_alerta, "norte/sectorA/humedad · el nodo lo informó en falla")

    def test_post_o_en_falla_de_un_equipo_ya_fuera_de_servicio_no_cambia_su_estado(self):
        """Extensión 1a: si ya estaba fuera de servicio no cambia; la alerta se asegura igual."""
        self.humedad.estado_hardware = "fuera_de_servicio"
        self.humedad.save(update_fields=["estado_hardware"])
        self.informar("norte/sectorA/humedad", "en_falla")
        self.recargar()
        self.assertEqual(self.humedad.estado_hardware, "fuera_de_servicio")
        self.assertEqual(self.alertas("iot_dispositivo_en_falla").count(), 1)

    def test_post_p_el_primer_estado_operativo_no_marca_cambiado_en_el_invernadero(self):
        """D-75, punto 1: el primer estado operativo (antes «desconocido») es la sincronización inicial, no un cambio: se guarda con su fecha y no se marca."""
        self.informar("norte/sectorA/ventilador", "encendido", informado_en="2026-11-21T14:02:10-03:00")
        self.recargar()
        self.assertEqual(self.ventilador.estado_informado, "encendido")
        self.assertEqual(self.ventilador.estado_informado_en, datetime(2026, 11, 21, 17, 2, 10, tzinfo=timezone.utc))
        self.assertFalse(self.ventilador.cambiado_en_invernadero)

    def test_post_p_un_segundo_estado_distinto_se_marca_cambiado_en_el_invernadero(self):
        """D-75, punto 1: otro estado distinto, que no explica un comando de InfoPonia (`explica_un_comando` es falso hasta IOT-05), se marca."""
        self.informar("norte/sectorA/ventilador", "encendido")
        self.informar("norte/sectorA/ventilador", "apagado")
        self.recargar()
        self.assertEqual((self.ventilador.estado_informado, self.ventilador.cambiado_en_invernadero), ("apagado", True))

    def test_post_p_el_mismo_estado_repetido_no_cambia_nada(self):
        """D-75, punto 1: un estado igual al anterior no cambia la marca ni la hora."""
        self.informar("norte/sectorA/ventilador", "encendido")
        self.informar("norte/sectorA/ventilador", "apagado")
        self.recargar()
        hora = self.ventilador.estado_informado_en
        self.informar("norte/sectorA/ventilador", "apagado", ahora=AHORA + timedelta(minutes=1), informado_en=(AHORA + timedelta(minutes=1)).isoformat())
        self.recargar()
        self.assertEqual((self.ventilador.cambiado_en_invernadero, self.ventilador.estado_informado_en), (True, hora))

    def test_post_p_nivel_y_posicion_con_enteros_se_aceptan(self):
        """D-75, punto 6: `nivel:60` y `posicion:-15` son estados operativos válidos."""
        self.assertEqual(self.informar("norte/sectorA/ventilador", "nivel:60").resultado, "aceptado")
        self.assertEqual(self.informar("norte/sectorA/ventilador", "posicion:-15").resultado, "aceptado")
        self.recargar()
        self.assertEqual(self.ventilador.estado_informado, "posicion:-15")

    def test_regla_estado_invalido_para_un_valor_fuera_del_contrato(self):
        """D-75, punto 6: `nivel:alto`, `girando` u otro texto: `estado_invalido` con ««{estado}» no es un estado del contrato.»; no se guarda nada."""
        for estado in ("nivel:alto", "girando", "nivel:", "posicion:1.5", "ENCENDIDO", None, 5):
            with self.subTest(estado=estado):
                r = self.informar("norte/sectorA/ventilador", estado)
                self.assertEqual((r.resultado, r.motivo, r.detalle), ("rechazado", "estado_invalido", f"«{estado}» no es un estado del contrato."))
        self.recargar()
        self.assertIsNone(self.ventilador.estado_informado)

    def test_regla_un_estado_operativo_para_un_sensor_es_estado_invalido(self):
        """D-75, punto 6: `encendido` para un sensor: `estado_invalido` con ««encendido» es un estado de actuador y «{id}» es un sensor.»."""
        r = self.informar("norte/sectorA/humedad", "encendido")
        self.assertEqual((r.resultado, r.motivo), ("rechazado", "estado_invalido"))
        self.assertEqual(r.detalle, "«encendido» es un estado de actuador y «norte/sectorA/humedad» es un sensor.")

    def test_ext_1a_cualquier_estado_aceptado_actualiza_el_ultimo_mensaje_del_equipo(self):
        """Regla «Estado actual de un equipo»: con su primer mensaje deja de estar «sin confirmar»."""
        self.informar("norte/sectorA/ventilador", "en_linea")
        self.recargar()
        self.assertEqual(self.ventilador.ultimo_mensaje_en, AHORA)

    def test_d75_6_la_fecha_futura_o_invalida_rechaza_el_estado(self):
        """D-75, punto 6: `informado_en` sigue las reglas de la fecha de una lectura: futura (más de 5 min) o sin zona se rechaza."""
        futura = (AHORA + timedelta(minutes=6)).isoformat()
        r = self.informar("norte/sectorA/ventilador", "encendido", informado_en=futura)
        self.assertEqual((r.motivo, r.detalle), ("fecha_futura", f"La fecha {futura} es más de 5 minutos posterior a la hora de InfoPonia."))
        r = self.informar("norte/sectorA/ventilador", "encendido", informado_en="2026-11-21T14:00:00")
        self.assertEqual(r.motivo, "fecha_invalida")
        self.recargar()
        self.assertIsNone(self.ventilador.estado_informado)

    def test_post_t_un_equipo_no_registrado_genera_la_alerta_con_el_estado_en_la_descripcion(self):
        """Postcondición t y extensión 3a: `equipo_no_registrado`, y la alerta lleva el estado: «El nodo envió el estado «{estado}» de «{id}», que no está registrado.»."""
        r = self.informar("norte/sectorB/co2", "en_falla")
        self.assertEqual((r.resultado, r.motivo), ("rechazado", "equipo_no_registrado"))
        self.assertEqual(r.detalle, "«norte/sectorB/co2» no es un equipo registrado de este sistema IoT.")
        [alerta] = self.alertas("iot_dispositivo_no_registrado")
        self.assertEqual(alerta.descripcion_alerta, "El nodo envió el estado «en_falla» de «norte/sectorB/co2», que no está registrado.")
        self.assertEqual(alerta.clave_estado, "id:norte/sectorb/co2")
        self.assertEqual(AlertaIot.objects.get(alerta=alerta).ultimo_mensaje_en, AHORA)

    def test_ext_3a_un_equipo_dado_de_baja_se_rechaza_equipo_dado_de_baja(self):
        """Extensión 3a: el estado de un equipo dado de baja: `equipo_dado_de_baja` y la alerta «no registrado»."""
        fabricas.sensor(self.sistema, "norte/sectorA/temp-vieja", estado="inactivo")
        r = self.informar("norte/sectorA/temp-vieja", "desconectado")
        self.assertEqual((r.motivo, r.detalle), ("equipo_dado_de_baja", "«norte/sectorA/temp-vieja» era de un equipo dado de baja de este sistema IoT."))
        self.assertEqual(self.alertas("iot_dispositivo_no_registrado").count(), 1)

    def test_ext_astar_un_sistema_desconectado_rechaza_el_estado_sin_escribir(self):
        """Extensión *a y respuestas_y_errores.md, sección 4: `sistema_desconectado` y nada escrito."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        r = self.informar("norte/sectorA/ventilador", "encendido")
        self.assertEqual((r.resultado, r.motivo), ("rechazado", "sistema_desconectado"))
        self.recargar()
        self.assertIsNone(self.ventilador.estado_informado)

    def test_post_z_un_estado_que_cambia_algo_se_audita_con_cambios_y_afectados(self):
        """Postcondición z y D-36: `datos` (mensaje `estado`, identificador, alertas) y `cambios` con el estado del equipo, antes y después."""
        self.informar("norte/sectorA/humedad", "en_falla")
        [registro] = self.auditorias()
        self.assertEqual(registro.detalle["datos"]["mensaje"], "estado")
        self.assertEqual(registro.detalle["datos"]["identificador"], "norte/sectorA/humedad")
        self.assertEqual(registro.detalle["cambios"], {"estado_hardware": {"antes": "activo", "despues": "fuera_de_servicio"}})
        self.assertEqual(len(registro.detalle["datos"]["alertas_generadas"]), 1)
        self.assertIn(("iot.sensor", self.humedad.pk), [(a["modelo"], a["id"]) for a in registro.afectados])

    def test_post_z_el_estado_informado_de_un_actuador_se_audita_como_cambio(self):
        """Postcondición z: el cambio del estado informado queda con antes (`null`) y después; la marca «cambiado en el invernadero» también si cambió."""
        self.informar("norte/sectorA/ventilador", "encendido")
        self.informar("norte/sectorA/ventilador", "apagado")
        primero, segundo = self.auditorias().order_by("id")
        self.assertEqual(primero.detalle["cambios"], {"estado_informado": {"antes": None, "despues": "encendido"}})
        self.assertEqual(
            segundo.detalle["cambios"],
            {
                "estado_informado": {"antes": "encendido", "despues": "apagado"},
                "cambiado_en_invernadero": {"antes": False, "despues": True},
            },
        )

    def test_post_z_un_estado_que_no_cambia_nada_no_se_audita(self):
        """«Auditoría»: «en línea» de un equipo sin alerta ni cambio solo actualiza el último mensaje: sin registro."""
        self.informar("norte/sectorA/humedad", "en_linea")
        self.assertEqual(self.auditorias().count(), 0)

    def test_d75_1_explica_un_comando_devuelve_falso_hasta_iot_05(self):
        """«Reparto»: `explica_un_comando(actuador, estado)` devuelve falso (IOT-05 la completa)."""
        self.assertIs(estados.explica_un_comando(self.ventilador, "encendido"), False)
