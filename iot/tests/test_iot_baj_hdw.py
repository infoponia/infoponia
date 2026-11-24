# Pruebas de IOT-BAJ-HDW · Baja Hardware (docs/casos_de_uso/iot/hardware.md, con «Baja (BAJ, IOT-06)» de «Cómo se aplica») y de lo que cita: D-82 (el tipo no se bloquea: la baja no crea nada que impida bajar un tipo), D-36, D-28
# y la regla 8 (IOT-ENT-INF, extensión 3a).
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban (iot/servicios/hardware.py), tomados del módulo dentro de cada prueba:
#   datos_de_baja_del_equipo(actor, equipo_id) -> DatosDeBajaDelEquipo(equipo, impedimentos, advertencia)
#       lo que muestra la ventana ``baj:<id>``: los impedimentos de las precondiciones c a e (``maestros.extensiones.Impedimento``: ``codigo``, ``texto``, ``como_resolver``) y, de un actuador,
#       ``advertencia`` con su último estado informado (regla 7; «desconocido» si el nodo nunca informó; ``None`` en un sensor). No escribe ni audita.
#   baja_hardware(actor, equipo_id, ahora) -> equipo
#   mantenimientos_a_realizar(equipo) -> list      (precondición d; ya existe, vacía hasta IOT-07)
#   acciones_permitidas(actor, equipo)             (suma ``baja``: D-30)
# Errores: ``PermissionDenied`` (otro rol), ``Http404`` (equipo inexistente, el nodo —se da de baja con IOT-BAJ-SIS— o fuera del alcance de consulta), ``ValidationError`` general:
# ``fuera_de_alcance`` (regla 1), ``equipo_dado_de_baja`` (precondición b), y los impedimentos, juntos (regla 2): ``comandos_pendientes`` (c), ``ordenes_de_mantenimiento`` (d) y
# ``reglas_activas`` (e).

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.db import IntegrityError
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz
from inventario.tests.fabricas import perezoso, variedad_con_semilla, variedades_presentes_de_prueba
from iot.api.traduccion import LecturaRecibida
from iot.models import AlertaIot, Hardware, NodoCentral
from iot.servicios import alertas_iot
from iot.tests import fabricas
from iot.tests.escena_de_reglas import AHORA, ConEscenaDeReglas
from maestros.extensiones import Impedimento
from maestros.models import Alerta
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_tecnico, error_de

hardware = perezoso("iot.servicios.hardware")
lecturas = perezoso("iot.servicios.lecturas")


class IotBajHdwServicioTests(ConEscenaDeReglas, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-BAJ-HDW."""

    def baja(self, equipo=None, actor=None):
        return hardware.baja_hardware(actor or self.laura, (equipo or self.hum).pk, AHORA)

    def alerta(self, tipo, clave, hardware_=None, telemetria=None):
        return alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, tipo, clave, "x", hardware=hardware_, telemetria=telemetria).alerta

    # ---- postcondiciones ----

    def test_post_a_el_equipo_queda_inactivo_con_su_fecha_y_conserva_su_historial(self):
        """Postcondición a: baja lógica (``inactivo``, ``fecha_baja`` = hoy) de un sensor o un actuador, también si está fuera de servicio; su telemetría y sus comandos no se tocan."""
        lectura = fabricas.telemetria(self.hum, 70)
        comando = fabricas.comando(self.ventana, self.fijar, estado="ejecutado", valor_comando=10)
        type(self.ventana).objects.filter(pk=self.ventana.pk).update(estado_hardware="fuera_de_servicio")
        self.baja(self.hum)
        self.baja(self.ventana)
        for equipo in (self.hum, self.ventana):
            equipo.refresh_from_db()
            self.assertEqual((equipo.estado_hardware, equipo.fecha_baja), ("inactivo", AHORA.date()))
        self.assertTrue(type(lectura).objects.filter(pk=lectura.pk).exists() and type(comando).objects.filter(pk=comando.pk).exists())
        self.temp.refresh_from_db()
        self.assertEqual(self.temp.estado_hardware, "activo")

    def test_post_b_resuelve_las_alertas_del_equipo_y_solo_las_suyas(self):
        """Postcondición b: las alertas activas originadas en el equipo (``hw:<id>`` y ``sensor:<id>``) pasan a «resuelta»; las de otro equipo y la de «dispositivo no registrado» no se tocan."""
        lectura = fabricas.telemetria(self.hum, 95)
        propias = [
            self.alerta("iot_dispositivo_sin_actividad", f"hw:{self.hum.pk}", hardware_=self.hum),
            self.alerta("iot_lectura_invalida", f"hw:{self.hum.pk}x", hardware_=self.hum),
            self.alerta("iot_fuera_de_umbral", f"sensor:{self.hum.pk}", telemetria=lectura),
        ]
        ajenas = [self.alerta("iot_dispositivo_sin_actividad", f"hw:{self.temp.pk}", hardware_=self.temp), self.alerta("iot_dispositivo_no_registrado", "id:co2")]
        self.baja()
        for alerta in propias:
            alerta.refresh_from_db()
            self.assertEqual(alerta.estado_alerta, "resuelta", alerta.clave_estado)
        for alerta in ajenas:
            alerta.refresh_from_db()
            self.assertEqual(alerta.estado_alerta, "activa")

    def test_post_c_audita_la_baja_con_el_cambio_de_estado_y_cada_alerta_resuelta(self):
        """Postcondición c y D-36: ``baja_hardware`` con el usuario, el equipo y cada alerta resuelta como afectados, y el cambio de estado."""
        alerta = self.alerta("iot_dispositivo_sin_actividad", f"hw:{self.hum.pk}", hardware_=self.hum)
        self.baja()
        auditoria = RegistroAuditoria.objects.get(accion="baja_hardware")
        self.assertEqual(auditoria.usuario_id, self.laura.pk)
        self.assertEqual(auditoria.detalle["cambios"]["estado_hardware"], {"antes": "activo", "despues": "inactivo"})
        ids = {(a["modelo"], a["id"]) for a in auditoria.afectados}
        self.assertIn(("maestros.alerta", alerta.pk), ids)
        self.assertIn(self.hum.pk, {i for m, i in ids if m != "maestros.alerta"})

    def test_garantia_si_falla_la_auditoria_el_equipo_sigue_activo_y_la_alerta_activa(self):
        """Atomicidad."""
        alerta = self.alerta("iot_dispositivo_sin_actividad", f"hw:{self.hum.pk}", hardware_=self.hum)
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.baja()
        self.hum.refresh_from_db(), alerta.refresh_from_db()
        self.assertEqual((self.hum.estado_hardware, alerta.estado_alerta), ("activo", "activa"))

    # ---- precondiciones y regla 1 ----

    def test_regla_1_otros_roles_reciben_403_y_un_equipo_ajeno_inexistente_o_el_nodo_dan_404(self):
        """Precondición a y D-28; el nodo central se da de baja con IOT-BAJ-SIS, no con este caso de uso (regla 3)."""
        for otro in (crear_tecnico(), crear_capataz()):
            with self.assertRaises(PermissionDenied):
                self.baja(actor=otro)
        with self.assertRaises(Http404):
            self.baja(actor=crear_agronomo("otro@infoponia.com"))
        with self.assertRaises(Http404):
            hardware.baja_hardware(self.laura, 99999, AHORA)
        with self.assertRaises(Http404):
            hardware.baja_hardware(self.laura, NodoCentral.objects.get(sistema=self.sistema).pk, AHORA)

    def test_regla_1_el_gerente_no_da_de_baja_con_agronomo_activo_y_si_sin_el(self):
        """Regla 1 (la de IOT-DSC-SIS)."""
        self.assertEqual(codigos_de(error_de(lambda: self.baja(actor=self.gerente)), NON_FIELD_ERRORS), ["fuera_de_alcance"])
        self.norte.agronomo = None
        self.norte.save()
        self.baja(actor=self.gerente)
        self.assertEqual(RegistroAuditoria.objects.get(accion="baja_hardware").usuario_id, self.gerente.pk)

    def test_precondicion_b_un_equipo_ya_dado_de_baja_no_se_da_de_baja_otra_vez(self):
        """Precondición b: activo o fuera de servicio."""
        self.baja()
        self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["equipo_dado_de_baja"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_hardware").count(), 1)

    # ---- precondiciones c, d y e (regla 2) ----

    def test_precondicion_c_un_actuador_con_un_comando_pendiente_no_se_da_de_baja(self):
        """Precondición c y regla 2: «esperá su resultado o cancelalo» (IOT-CNL-CMD), nombrando el comando; no cambia nada."""
        comando = fabricas.comando(self.ventilador, self.encender)
        error = error_de(lambda: self.baja(self.ventilador))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["comandos_pendientes"])
        self.assertIn(f"CMD-{comando.pk}", " ".join(error.messages))
        self.ventilador.refresh_from_db()
        self.assertEqual(self.ventilador.estado_hardware, "activo")

    def test_precondicion_d_con_una_orden_de_mantenimiento_a_realizar_no_se_da_de_baja(self):
        """Precondición d: hasta IOT-07 ``mantenimientos_a_realizar`` devuelve una lista vacía y la baja procede; con una orden, no («concretala o cancelala»)."""
        self.assertEqual(hardware.mantenimientos_a_realizar(self.hum), [])
        with mock.patch("iot.servicios.hardware.mantenimientos_a_realizar", return_value=["OT-1"]):
            self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["ordenes_de_mantenimiento"])

    def test_precondicion_e_un_equipo_usado_por_una_regla_activa_no_se_da_de_baja_y_explica_que_hay_que_darla_de_baja(self):
        """Precondición e y regla 2: un sensor o un actuador que usa una regla ACTIVA no se da de baja; el error nombra la regla (``RGL-n``) y dice que se da de baja primero (IOT-BAJ-RGL)."""
        regla = fabricas.regla(self.temp, self.ventilador, self.encender)
        for equipo in (self.temp, self.ventilador):
            error = error_de(lambda: self.baja(equipo))
            self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["reglas_activas"])
            self.assertIn(f"RGL-{regla.pk}", " ".join(error.messages))
            self.assertIn("baja", " ".join(error.messages).lower())
        self.temp.refresh_from_db()
        self.assertEqual(self.temp.estado_hardware, "activo")

    def test_precondicion_e_una_regla_inactiva_no_impide_la_baja(self):
        """Precondición e: solo cuentan las reglas activas (la baja de la regla deja el historial)."""
        fabricas.regla(self.temp, self.ventilador, self.encender, estado_regla="inactiva")
        self.baja(self.temp)
        self.baja(self.ventilador)

    def test_regla_2_los_impedimentos_llegan_juntos(self):
        """Regla 2: si hay más de uno, el servicio informa todos a la vez, cada uno con cómo resolverlo."""
        fabricas.regla(self.temp, self.ventilador, self.encender)
        fabricas.comando(self.ventilador, self.apagar)
        with mock.patch("iot.servicios.hardware.mantenimientos_a_realizar", return_value=["OT-1"]):
            error = error_de(lambda: self.baja(self.ventilador))
        self.assertEqual(sorted(codigos_de(error, NON_FIELD_ERRORS)), ["comandos_pendientes", "ordenes_de_mantenimiento", "reglas_activas"])

    # ---- la ventana (reglas 2 y 7) ----

    def test_regla_2_la_ventana_trae_los_impedimentos_con_como_resolverlos_y_no_audita(self):
        """Regla 2: la ventana muestra los impedimentos como ``Impedimento`` (código, texto y cómo resolver) y no deja confirmar; es una consulta: no escribe ni audita."""
        fabricas.regla(self.temp, self.ventilador, self.encender)
        comando = fabricas.comando(self.ventilador, self.apagar)
        antes = RegistroAuditoria.objects.count()
        datos = hardware.datos_de_baja_del_equipo(self.laura, self.ventilador.pk)
        self.assertEqual(sorted(i.codigo for i in datos.impedimentos), ["comandos_pendientes", "reglas_activas"])
        self.assertTrue(all(isinstance(i, Impedimento) and i.como_resolver for i in datos.impedimentos))
        self.assertIn(f"CMD-{comando.pk}", " ".join(i.texto for i in datos.impedimentos))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        self.ventilador.refresh_from_db()
        self.assertEqual(self.ventilador.estado_hardware, "activo")

    def test_regla_7_un_actuador_advierte_su_ultimo_estado_informado_y_la_advertencia_no_impide_la_baja(self):
        """Regla 7: antes de confirmar se muestra el último estado informado («encendido desde las 14:09») y se advierte que, después de la baja, InfoPonia no podrá enviarle comandos; no impide la baja."""
        type(self.ventilador).objects.filter(pk=self.ventilador.pk).update(estado_informado="encendido", estado_informado_en=AHORA)
        datos = hardware.datos_de_baja_del_equipo(self.laura, self.ventilador.pk)
        self.assertEqual(datos.impedimentos, [])
        self.assertIn("encendido", datos.advertencia.lower())
        self.assertIn("comandos", datos.advertencia)
        self.baja(self.ventilador)
        self.ventilador.refresh_from_db()
        self.assertEqual(self.ventilador.estado_hardware, "inactivo")

    def test_regla_7_si_el_nodo_nunca_informo_el_estado_se_advierte_desconocido(self):
        """Regla 7: sin estado informado, «desconocido»."""
        self.assertIn("desconocido", hardware.datos_de_baja_del_equipo(self.laura, self.ventilador.pk).advertencia.lower())

    def test_regla_7_un_sensor_no_lleva_advertencia_de_estado(self):
        """Regla 7 es de los actuadores."""
        self.assertIsNone(hardware.datos_de_baja_del_equipo(self.laura, self.hum.pk).advertencia)

    def test_regla_2_la_ventana_exige_operar_el_invernadero(self):
        """Mismo alcance que la baja: otros roles, 403; el Gerente con Agrónomo activo, 403 (no ve el botón); un Agrónomo ajeno, 404; un equipo ya dado de baja, ``equipo_dado_de_baja``."""
        with self.assertRaises(PermissionDenied):
            hardware.datos_de_baja_del_equipo(crear_tecnico(), self.hum.pk)
        with self.assertRaises(PermissionDenied):
            hardware.datos_de_baja_del_equipo(self.gerente, self.hum.pk)
        with self.assertRaises(Http404):
            hardware.datos_de_baja_del_equipo(crear_agronomo("otro@infoponia.com"), self.hum.pk)
        self.baja()
        self.assertEqual(codigos_de(error_de(lambda: hardware.datos_de_baja_del_equipo(self.laura, self.hum.pk)), NON_FIELD_ERRORS), ["equipo_dado_de_baja"])

    # ---- reglas 5, 6 y 8 (después de la baja) ----

    def test_regla_8_sus_mensajes_se_rechazan_y_generan_dispositivo_no_registrado_que_dice_de_que_equipo_era(self):
        """Regla 8 y extensión 3a de IOT-ENT-INF (la parte de IOT-03): después de la baja, una lectura con su identificador se rechaza con el motivo ``equipo_dado_de_baja``, genera la alerta
        «dispositivo no registrado» y el equipo se deduce por el identificador (``baja_con_identificador``: el vínculo no se guarda en la alerta)."""
        self.baja()
        self.enterContext(variedades_presentes_de_prueba({self.norte.pk: {variedad_con_semilla(nombre="Crespa").pk}}))
        contexto = lecturas.contexto_del_mensaje(self.sistema, AHORA)
        lectura = LecturaRecibida(1, "norte/hum", "norte/hum", Decimal("70"), (AHORA - timedelta(seconds=5)).isoformat())
        resultado = lecturas.registrar_lectura(contexto, lectura, AHORA)
        self.assertEqual((resultado.resultado, resultado.motivo), ("rechazada", "equipo_dado_de_baja"))
        self.assertEqual(Alerta.objects.filter(tipo_alerta="iot_dispositivo_no_registrado", clave_estado="id:norte/hum", estado_alerta="activa").count(), 1)
        self.assertEqual(hardware.baja_con_identificador(self.sistema, "norte/hum").pk, self.hum.pk)

    def test_regla_6_el_identificador_queda_libre_para_un_equipo_de_reemplazo(self):
        """Regla 6: se puede registrar un equipo con el mismo identificador (el índice único cuenta solo los no dados de baja), que empieza su propio historial."""
        self.baja()
        nuevo = fabricas.sensor(self.sistema, "norte/hum", "humedad", valor_calibracion_min=0, valor_calibracion_max=100)
        self.assertNotEqual(nuevo.pk, self.hum.pk)
        # Mientras el de reemplazo esté activo, el dado de baja no se puede reactivar (regla 10 de IOT-MOD-HDW).
        self.assertEqual(codigos_de(error_de(lambda: hardware.reactivar_hardware(self.laura, self.hum.pk)), NON_FIELD_ERRORS), ["identificador_en_uso"])

    def test_regla_5_se_reactiva_con_iot_mod_hdw(self):
        """Regla 5: el equipo dado de baja vuelve a «activo» con ``reactivar_hardware``."""
        self.baja()
        hardware.reactivar_hardware(self.laura, self.hum.pk)
        self.hum.refresh_from_db()
        self.assertEqual((self.hum.estado_hardware, self.hum.fecha_baja), ("activo", None))

    def test_regla_3_la_baja_del_sistema_no_pasa_por_este_caso_de_uso_y_baja_todo_el_hardware(self):
        """Regla 3: la baja en cascada es de IOT-BAJ-SIS; este caso de uso da de baja de a uno (el invernadero activo y el nodo no cambian)."""
        self.baja()
        self.sistema.refresh_from_db()
        self.assertEqual(self.sistema.estado_sistema, "activo")
        self.assertEqual(Hardware.objects.filter(sistema=self.sistema, estado_hardware="inactivo").count(), 1)

    # ---- D-30 ----

    def test_d30_la_baja_se_ofrece_a_quien_opera_en_un_equipo_activo_o_fuera_de_servicio(self):
        """D-30: ``baja`` junto con las demás acciones del estado: activo (modificar y baja); fuera de servicio (modificar, volver a activar y baja); dado de baja, solo reactivar; quien solo consulta, ninguna."""
        self.assertEqual(hardware.acciones_permitidas(self.laura, self.hum), {hardware.ACCION_MODIFICAR, hardware.ACCION_BAJA})
        type(self.hum).objects.filter(pk=self.hum.pk).update(estado_hardware="fuera_de_servicio")
        self.hum.refresh_from_db()
        self.assertEqual(hardware.acciones_permitidas(self.laura, self.hum), {hardware.ACCION_MODIFICAR, hardware.ACCION_VOLVER_A_ACTIVAR, hardware.ACCION_BAJA})
        self.assertEqual(hardware.acciones_permitidas(self.gerente, self.hum), frozenset())
        type(self.hum).objects.filter(pk=self.hum.pk).update(estado_hardware="inactivo")
        self.hum.refresh_from_db()
        self.assertEqual(hardware.acciones_permitidas(self.laura, self.hum), {hardware.ACCION_REACTIVAR})
