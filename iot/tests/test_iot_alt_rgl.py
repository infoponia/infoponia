# Pruebas de IOT-ALT-RGL · Alta Regla de Actuación (docs/casos_de_uso/iot/reglas_de_actuacion.md, con «Cómo se aplica en la ronda «IoT 1»») y de lo que cita: D-78 (punto 11), D-82, D-36 y D-28.
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban (iot/servicios/reglas.py), tomados del módulo dentro de cada prueba:
#   DatosDeRegla(sensor_id, actuador_id, condicion, accion_id, valor)
#   alta_regla(actor, invernadero_id, datos, ahora) -> ReglaActuacion        (``ahora`` es un parámetro más que el extracto: los servicios no leen la hora)
#   sin_umbral_efectivo(invernadero_id) -> bool                              (regla 7: la pantalla muestra la advertencia; el alta deja continuar)
#   datos_para_regla(actor, invernadero_id, actuador_id=None) -> DatosParaRegla(sensores, actuadores, acciones)   (lo que ofrece el formulario)
# Errores: ``PermissionDenied`` (otro rol), ``Http404`` (invernadero fuera del alcance de consulta), ``ValidationError``:
#   general: ``fuera_de_alcance`` (regla 1), ``sin_sistema_iot`` (precondición b), ``regla_repetida`` (regla 6; «Ya hay una regla activa igual: …»);
#   por campo: ``sensor`` (``obligatorio``, ``sensor_no_disponible``, ``sensor_no_admite_reglas``), ``actuador`` (``obligatorio``, ``actuador_no_disponible``),
#   ``condicion`` (``obligatorio``, ``condicion_invalida``), ``accion`` y ``valor`` (los códigos de ``comandos.validar_comando``).

from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz
from inventario.tests.fabricas import variedad_con_semilla, variedades_presentes_de_prueba
from iot.models import ReglaActuacion
from iot.tests import fabricas
from iot.tests.escena_de_reglas import AHORA, ConEscenaDeReglas, reglas
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_invernadero, crear_sector, crear_tecnico, error_de


def invernadero_ajeno():
    """Un invernadero de otro Agrónomo, para probar equipos «de otro invernadero»."""
    return crear_invernadero("Sur", agronomo=crear_agronomo("sur@infoponia.com"))


class IotAltRglServicioTests(ConEscenaDeReglas, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-ALT-RGL."""

    # ---- postcondiciones ----

    def test_post_a_crea_la_regla_activa_con_sus_datos_y_sin_evaluar(self):
        """Postcondición a y regla «Disparo de una regla»: activa, con condición, acción, sensor y actuador; última evaluación «sin evaluar» y contador en 0."""
        regla = self.alta(condicion="baja_del_minimo", accion=self.apagar)
        regla.refresh_from_db()
        self.assertEqual((regla.sensor_id, regla.actuador_id, regla.accion_id, regla.condicion), (self.temp.pk, self.ventilador.pk, self.apagar.pk, "baja_del_minimo"))
        self.assertEqual((regla.estado_regla, regla.ultima_evaluacion, regla.contador_confirmacion, regla.aplicar_valor), ("activa", "sin_evaluar", 0, None))

    def test_post_a_guarda_el_valor_a_aplicar_de_una_accion_con_valor(self):
        """Postcondición a: si la acción lleva valor, se guarda como entero (el formulario lo manda como texto)."""
        self.assertEqual(self.alta(actuador=self.ventana, valor="40").aplicar_valor, 40)

    def test_post_b_audita_el_alta_con_el_usuario_la_regla_y_sus_datos(self):
        """Postcondición b y D-36: ``alta_regla_actuacion``, el usuario, la regla como afectada, la condición, el estado y las referencias a sensor, actuador y acción."""
        regla = self.alta()
        auditoria = RegistroAuditoria.objects.get(accion="alta_regla_actuacion")
        self.assertEqual(auditoria.usuario_id, self.laura.pk)
        self.assertEqual([(a["modelo"], a["id"]) for a in auditoria.afectados], [("iot.reglaactuacion", regla.pk)])
        self.assertEqual(auditoria.detalle["cambios"]["condicion"], {"antes": None, "despues": "supera_maximo"})
        self.assertEqual(auditoria.detalle["cambios"]["estado_regla"], {"antes": None, "despues": "activa"})
        for clave in ("sensor", "actuador", "accion"):
            self.assertIn("id", auditoria.detalle["datos"][clave])

    def test_garantia_si_falla_la_auditoria_no_se_crea_la_regla(self):
        """Atomicidad: si falla la auditoría, no queda la regla."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.alta()
        self.assertEqual(ReglaActuacion.objects.count(), 0)

    # ---- precondición a y regla 1 (alcance) ----

    def test_regla_1_otros_roles_reciben_403(self):
        """Precondición a: solo Agrónomo y Gerente activos."""
        for otro in (crear_tecnico(), crear_capataz()):
            with self.assertRaises(PermissionDenied):
                self.alta(actor=otro)
        self.laura.is_active = False
        self.laura.save()
        with self.assertRaises(PermissionDenied):
            self.alta()
        self.assertEqual(ReglaActuacion.objects.count(), 0)

    def test_regla_1_un_agronomo_de_otro_invernadero_da_404(self):
        """D-28: fuera del alcance de consulta, el invernadero no existe."""
        with self.assertRaises(Http404):
            self.alta(actor=crear_agronomo("otro@infoponia.com"))

    def test_regla_1_el_gerente_no_crea_con_agronomo_activo_y_si_sin_el(self):
        """Regla 1 (la de IOT-DSC-SIS): el Gerente opera solo los invernaderos sin Agrónomo activo."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(actor=self.gerente)), NON_FIELD_ERRORS), ["fuera_de_alcance"])
        self.norte.agronomo = None
        self.norte.save()
        regla = self.alta(actor=self.gerente)
        self.assertEqual(RegistroAuditoria.objects.get(accion="alta_regla_actuacion").usuario_id, self.gerente.pk)
        self.assertEqual(regla.estado_regla, "activa")

    # ---- precondición b y regla 9 ----

    def test_precondicion_b_sin_sistema_iot_no_se_crea(self):
        """Precondición b: el invernadero tiene un sistema IoT activo o desconectado; uno dado de baja no cuenta."""
        self.sistema.estado_sistema = "inactivo"
        self.sistema.save()
        self.assertEqual(codigos_de(error_de(self.alta), NON_FIELD_ERRORS), ["sin_sistema_iot"])

    def test_regla_9_con_el_sistema_desconectado_se_crea_igual(self):
        """Regla 9: una regla de un sistema desconectado se crea igual y se evalúa cuando el sistema se activa."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        self.assertEqual(self.alta().estado_regla, "activa")

    # ---- regla 2 (sensor y actuador) y regla 5 (variables que admiten reglas) ----

    def test_regla_2_el_sensor_y_el_actuador_son_obligatorios(self):
        """Regla 2: sin sensor y sin actuador, un error por campo."""
        datos = reglas.DatosDeRegla(sensor_id=None, actuador_id=None, condicion="supera_maximo", accion_id=None, valor=None)
        error = error_de(lambda: reglas.alta_regla(self.laura, self.norte.pk, datos, AHORA))
        self.assertEqual(codigos_de(error, "sensor"), ["obligatorio"])
        self.assertEqual(codigos_de(error, "actuador"), ["obligatorio"])

    def test_regla_2_un_sensor_de_otro_invernadero_o_no_activo_no_se_acepta(self):
        """Regla 2: el sensor es del invernadero y está activo (ni fuera de servicio ni dado de baja)."""
        ajeno = fabricas.sensor(fabricas.sistema(invernadero_ajeno()), "otro/temp")
        for sensor in (ajeno, fabricas.sensor(self.sistema, "norte/t2", estado="fuera_de_servicio"), fabricas.sensor(self.sistema, "norte/t3", estado="inactivo")):
            error = error_de(lambda: self.alta(sensor=sensor))
            self.assertEqual(codigos_de(error, "sensor"), ["sensor_no_disponible"], sensor.identificador_equipo)

    def test_regla_2_un_actuador_de_otro_invernadero_o_no_activo_no_se_acepta(self):
        """Regla 2: el actuador es del invernadero y está activo."""
        ajeno = fabricas.actuador(fabricas.sistema(invernadero_ajeno()), self.tipo_ventilador, "otro/ventilador")
        otros = (ajeno, fabricas.actuador(self.sistema, self.tipo_ventilador, "norte/v2", estado="fuera_de_servicio"), fabricas.actuador(self.sistema, self.tipo_ventilador, "norte/v3", estado="inactivo"))
        for actuador in otros:
            error = error_de(lambda: self.alta(actuador=actuador, accion=self.encender))
            self.assertEqual(codigos_de(error, "actuador"), ["actuador_no_disponible"], actuador.identificador_equipo)

    def test_regla_5_un_sensor_de_la_solucion_o_de_nivel_no_admite_reglas(self):
        """Regla 5: solo temperatura, humedad e intensidad lumínica; la temperatura y el nivel de la solución se monitorean con alertas."""
        for sensor in (self.nivel, fabricas.sensor(self.sistema, "norte/tsol", "temperatura_solucion")):
            error = error_de(lambda: self.alta(sensor=sensor))
            self.assertEqual(codigos_de(error, "sensor"), ["sensor_no_admite_reglas"], sensor.identificador_equipo)

    def test_regla_5_humedad_e_intensidad_luminica_si_admiten_reglas(self):
        """Regla 5: las tres variables que admiten reglas."""
        luz = fabricas.sensor(self.sistema, "norte/luz", "intensidad_luz")
        for sensor in (self.hum, luz):
            self.assertEqual(self.alta(sensor=sensor).sensor_id, sensor.pk)

    # ---- regla 3 (condición) ----

    def test_regla_3_la_condicion_es_una_de_las_tres(self):
        """Regla 3: supera el máximo, baja del mínimo o vuelve al rango; nada más (no hay valores fijos)."""
        for condicion in ("supera_maximo", "baja_del_minimo", "vuelve_al_rango"):
            self.assertEqual(self.alta(condicion=condicion).condicion, condicion)
        self.assertEqual(codigos_de(error_de(lambda: self.alta(condicion="mayor_que_30")), "condicion"), ["condicion_invalida"])
        self.assertEqual(codigos_de(error_de(lambda: self.alta(condicion="")), "condicion"), ["obligatorio"])

    # ---- regla 4 (acción y valor: validar_comando) ----

    def test_regla_4_la_accion_tiene_que_ser_activa_del_tipo_del_actuador(self):
        """Regla 4 y «Comando válido»: una acción de otro tipo, o inactiva, es ``accion_no_disponible`` (el código de ``validar_comando``)."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(accion=self.fijar)), "accion"), ["accion_no_disponible"])
        self.encender.estado = "inactiva"
        self.encender.save()
        self.assertEqual(codigos_de(error_de(self.alta), "accion"), ["accion_no_disponible"])

    def test_regla_4_una_accion_incompatible_con_el_nodo_no_se_acepta(self):
        """Regla 4: compatible con las capacidades que el nodo anunció (regla 14 de IOT-ALT-HDW)."""
        self.ventilador.acciones_incompatibles.add(self.encender)
        self.assertEqual(codigos_de(error_de(self.alta), "accion"), ["accion_incompatible"])

    def test_regla_4_el_valor_es_obligatorio_entero_y_dentro_del_rango_de_la_accion(self):
        """Regla 4: obligatorio si la acción lleva valor, entero y entre el mínimo y el máximo; con un valor de más en una acción sin valor, error."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(actuador=self.ventana)), "valor"), ["valor_requerido"])
        for malo in ("abc", "40.5", "101", "-1"):
            self.assertEqual(codigos_de(error_de(lambda: self.alta(actuador=self.ventana, valor=malo)), "valor"), ["valor_invalido"], malo)
        self.assertEqual(codigos_de(error_de(lambda: self.alta(valor="5")), "valor"), ["valor_de_mas"])
        self.assertEqual(self.alta(actuador=self.ventana, valor="0", condicion="baja_del_minimo").aplicar_valor, 0)
        self.assertEqual(self.alta(actuador=self.ventana, valor="100").aplicar_valor, 100)

    def test_regla_4_todos_los_errores_llegan_juntos(self):
        """Patrón ABM, sección 2: un solo ``ValidationError`` con un error por campo."""
        datos = reglas.DatosDeRegla(sensor_id=None, actuador_id=self.ventana.pk, condicion="x", accion_id=self.fijar.pk, valor="")
        error = error_de(lambda: reglas.alta_regla(self.laura, self.norte.pk, datos, AHORA))
        self.assertEqual(set(error.error_dict), {"sensor", "condicion", "valor"})

    # ---- regla 6 (unicidad) ----

    def test_regla_6_no_puede_haber_dos_reglas_activas_iguales(self):
        """Regla 6 y precondición c: mismo sensor, misma condición y mismo actuador; el mensaje nombra la regla igual."""
        primera = self.alta()
        error = error_de(self.alta)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["regla_repetida"])
        self.assertIn("Ya hay una regla activa igual", error.messages[0])
        self.assertIn("norte/temp", error.messages[0])
        self.assertEqual(ReglaActuacion.objects.get().pk, primera.pk)

    def test_regla_6_distinta_condicion_actuador_o_sensor_no_es_igual(self):
        """Regla 6: basta que cambie una de las tres (la acción y el valor no cuentan: la igualdad es sensor, condición y actuador)."""
        self.alta()
        self.alta(condicion="baja_del_minimo")
        self.alta(sensor=self.hum)
        self.alta(actuador=self.ventana, valor="10")
        self.assertEqual(ReglaActuacion.objects.count(), 4)

    def test_regla_6_una_regla_igual_dada_de_baja_no_cuenta(self):
        """Regla 6: solo las activas."""
        ReglaActuacion.objects.filter(pk=self.alta().pk).update(estado_regla="inactiva")
        self.assertEqual(self.alta().estado_regla, "activa")

    def test_regla_6_si_la_base_rechaza_la_regla_igual_el_error_es_el_mismo_y_no_un_500(self):
        """Dos altas a la vez: si el chequeo del servicio no la ve, el índice único parcial de la base respalda y su ``IntegrityError`` se traduce al mismo error."""
        self.alta()
        with mock.patch.object(reglas, "_regla_igual_activa", return_value=None):
            error = error_de(self.alta)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["regla_repetida"])
        self.assertEqual(ReglaActuacion.objects.count(), 1)

    # ---- regla 7 (sin umbral efectivo) ----

    def test_regla_7_sin_umbral_efectivo_se_advierte_y_se_guarda(self):
        """Regla 7: sin lotes activos ni siembras a realizar, ``sin_umbral_efectivo`` es verdadero y el alta deja continuar."""
        self.assertTrue(reglas.sin_umbral_efectivo(self.norte.pk))
        self.assertEqual(self.alta().estado_regla, "activa")

    def test_regla_7_con_umbral_efectivo_no_hay_advertencia(self):
        """Regla 7: con variedades presentes, no se advierte."""
        with variedades_presentes_de_prueba({self.norte.pk: {variedad_con_semilla(nombre="Crespa").pk}}):
            self.assertFalse(reglas.sin_umbral_efectivo(self.norte.pk))

    # ---- lo que ofrece el formulario (``datos_para_regla``; prototipo ``rglSensors``) ----

    def test_datos_para_regla_ofrece_sensores_que_admiten_reglas_actuadores_y_acciones_del_elegido(self):
        """Prototipo ``rglSensors`` y ``r-act``: solo sensores activos de temperatura, humedad e intensidad lumínica; los actuadores activos; y, del elegido, sus acciones activas compatibles."""
        fabricas.sensor(self.sistema, "norte/viejo", estado="inactivo")
        fabricas.actuador(self.sistema, self.tipo_ventilador, "norte/roto", estado="fuera_de_servicio")
        self.ventilador.acciones_incompatibles.add(self.apagar)
        datos = reglas.datos_para_regla(self.laura, self.norte.pk, self.ventilador.pk)
        self.assertEqual({s.pk for s in datos.sensores}, {self.temp.pk, self.hum.pk})
        self.assertEqual({a.pk for a in datos.actuadores}, {self.ventilador.pk, self.ventana.pk})
        # El tipo «Ventilador» trae también «Fijar velocidad»: solo falta la acción marcada incompatible con el nodo.
        self.assertEqual({a.nombre_accion for a in datos.acciones}, {"Encender", "Fijar velocidad"})

    def test_datos_para_regla_ofrece_los_sensores_de_un_sector_fuera_de_servicio(self):
        """«Lo que difiere del prototipo»: el CU no excluye esos sensores; se ofrecen y la situación avisa que no se evalúan."""
        sector = crear_sector(self.norte, "Sector A", "germinacion", 50, estado="fuera_de_servicio")
        en_sector = fabricas.sensor(self.sistema, "norte/sa", sector=sector)
        self.assertIn(en_sector.pk, {s.pk for s in reglas.datos_para_regla(self.laura, self.norte.pk).sensores})

    def test_datos_para_regla_exige_operar_el_invernadero(self):
        """Mismo alcance que el alta: el Gerente con Agrónomo activo no opera (403); un Agrónomo ajeno, 404."""
        with self.assertRaises(PermissionDenied):
            reglas.datos_para_regla(self.gerente, self.norte.pk)
        with self.assertRaises(Http404):
            reglas.datos_para_regla(crear_agronomo("otro@infoponia.com"), self.norte.pk)
