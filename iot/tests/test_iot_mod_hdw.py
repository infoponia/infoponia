# Pruebas de IOT-MOD-HDW · Modificar Hardware, con volver a activar y reactivar (docs/casos_de_uso/iot/hardware.md, v0.2, con «Cómo se aplica en la
# ronda IoT 1») y de lo que cita: D-28 (sin cambios no se audita), D-36 y D-40. Se escribieron ANTES que el servicio.
#
# Servicios que se prueban (iot/servicios/hardware.py), tomados del módulo dentro de cada prueba:
#   modificar_hardware(actor, equipo_id, datos: DatosDeEquipo) -> Sensor | Actuador
#   volver_a_activar(actor, equipo_id) -> equipo          (fuera de servicio -> activo)
#   reactivar_hardware(actor, equipo_id) -> equipo        (dado de baja -> activo)
#   tiene_lecturas(sensor), tiene_comandos(actuador), tiene_comando_pendiente(actuador), tiene_reglas(equipo), mantenimientos_a_realizar(equipo)
#       Las completan IOT-03, IOT-05, IOT-06 e IOT-07: en IOT-02 consultan sus tablas, vacías hasta entonces, y acá se prueban con filas de la fábrica.
# Errores: ``PermissionDenied`` (rol), ``Http404`` (equipo inexistente), ``ValidationError`` por campo (las del alta, más ``variable``, ``tipo_actuador``
# e ``identificador`` cuando el equipo ya tiene historial) o general (``fuera_de_alcance``, ``sistema_dado_de_baja``, ``comando_pendiente``,
# ``equipo_dado_de_baja``, ``equipo_no_fuera_de_servicio``, ``equipo_no_inactivo``, ``identificador_en_uso``, ``tipo_inactivo``).

from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from iot.tests import fabricas
from iot.tests.fabricas import datos_de_equipo_guardado as guardado
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_invernadero, crear_sector, crear_tecnico, error_de

hardware = perezoso("iot.servicios.hardware")
MODIFICACION = "modificacion_hardware"
REACTIVACION = "reactivacion_hardware"


class IotModHdwServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-MOD-HDW."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=crear_tecnico("t@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.sector = crear_sector(self.norte, "Sector A")
        self.sensor = fabricas.sensor(self.sistema, "norte/sectorA/temperatura", sector=self.sector, numero_serie="SN-1")
        self.tipo = fabricas.tipo_actuador("Extractor")
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/sectorA/ventilador")

    def modificar(self, datos, equipo=None, actor=None):
        """Llama al servicio sobre ``equipo`` (el sensor de la prueba por defecto) como Laura por defecto."""
        return hardware.modificar_hardware(actor or self.laura, (equipo or self.sensor).pk, datos)

    def cambiar(self, equipo=None, **campos):
        """Los datos guardados de ``equipo`` (el sensor por defecto) con ``campos`` pisados."""
        return guardado(equipo or self.sensor, **campos)

    def codigos(self, datos, campo=None, equipo=None):
        return codigos_de(error_de(lambda: self.modificar(datos, equipo)), campo)

    def recargar(self, equipo=None):
        (equipo or self.sensor).refresh_from_db()
        return equipo or self.sensor

    # ---- precondición a, regla 1, precondición b y c, regla 9 ----

    def test_pre_a_otros_roles_no_modifican(self):
        """IOT-MOD-HDW precondición a: cuenta activa de Agrónomo o de Gerente."""
        for actor in (crear_capataz(), crear_tecnico("otro@infoponia.com"), crear_administrador()):
            with self.subTest(actor=actor.email):
                for llamada in (
                    lambda: self.modificar(self.cambiar(), actor=actor),
                    lambda: hardware.volver_a_activar(actor, self.sensor.pk),
                    lambda: hardware.reactivar_hardware(actor, self.sensor.pk),
                ):
                    with self.assertRaises(PermissionDenied):
                        llamada()

    def test_pre_a_un_equipo_que_no_existe_da_404(self):
        """IOT-MOD-HDW: un id que no existe da ``Http404``."""
        for llamada in (
            lambda: hardware.modificar_hardware(self.laura, 999999, fabricas.datos_de_equipo()),
            lambda: hardware.volver_a_activar(self.laura, 999999),
            lambda: hardware.reactivar_hardware(self.laura, 999999),
        ):
            with self.assertRaises(Http404):
                llamada()

    def test_regla_1_el_alcance_es_el_de_iot_dsc_sis(self):
        """IOT-MOD-HDW regla 1: el Agrónomo de otro invernadero y el Gerente con Agrónomo activo no operan; el Gerente sin Agrónomo, sí."""
        otra = crear_agronomo("otra@infoponia.com")
        for actor in (otra, self.gerente):
            with self.subTest(actor=actor.email):
                self.assertEqual(codigos_de(error_de(lambda: self.modificar(self.cambiar(), actor=actor))), ["fuera_de_alcance"])
                self.assertEqual(codigos_de(error_de(lambda: hardware.volver_a_activar(actor, self.sensor.pk))), ["fuera_de_alcance"])
        libre = fabricas.sensor(fabricas.sistema(crear_invernadero("Libre")), "libre/1")
        self.assertEqual(self.modificar(guardado(libre, modelo="Otro"), libre, self.gerente).modelo_hardware, "Otro")

    def test_pre_b_el_sistema_esta_activo_o_desconectado(self):
        """IOT-MOD-HDW precondición b: el equipo pertenece a un sistema «activo» o «desconectado»; si no, ``sistema_dado_de_baja``."""
        desconectado = fabricas.sensor(fabricas.sistema(crear_invernadero("Otro", agronomo=self.laura), "desconectado"), "otro/1")
        self.assertEqual(self.modificar(guardado(desconectado, modelo="Nuevo"), desconectado).modelo_hardware, "Nuevo")
        baja = fabricas.sensor(fabricas.sistema(crear_invernadero("Viejo", agronomo=self.laura), "inactivo"), "viejo/1")
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(guardado(baja, modelo="X"), baja))), ["sistema_dado_de_baja"])

    def test_pre_c_y_regla_5_un_equipo_con_comando_pendiente_no_se_modifica(self):
        """IOT-MOD-HDW precondición c y regla 5: un equipo con comandos pendientes no se modifica (ni se vuelve a activar)."""
        fabricas.comando(self.actuador, self.tipo.acciones.first(), "pendiente")
        self.assertEqual(self.codigos(guardado(self.actuador, modelo="Otro"), equipo=self.actuador), ["comando_pendiente"])
        self.actuador.estado_hardware = "fuera_de_servicio"
        self.actuador.save()
        self.assertEqual(codigos_de(error_de(lambda: hardware.volver_a_activar(self.laura, self.actuador.pk))), ["comando_pendiente"])

    def test_regla_9_un_equipo_dado_de_baja_no_se_modifica(self):
        """IOT-MOD-HDW regla 9: un equipo dado de baja no se modifica: solo se reactiva."""
        baja = fabricas.sensor(self.sistema, "viejo/1", estado="inactivo")
        self.assertEqual(self.codigos(guardado(baja, modelo="X"), equipo=baja), ["equipo_dado_de_baja"])

    # ---- regla 2: qué cambia ----

    def test_regla_2_cambia_el_modelo_la_serie_el_sector_el_nombre_y_la_calibracion_del_sensor(self):
        """IOT-MOD-HDW regla 2: el modelo, el número de serie, el sector, el nombre del sensor y su calibración."""
        otro_sector = crear_sector(self.norte, "Sector B")
        self.modificar(
            self.cambiar(modelo="DHT11", numero_serie="SN-2", sector_id=otro_sector.pk, nombre_sensor="Del fondo", calibracion_min="-5", calibracion_max="45.5")
        )
        sensor = self.recargar()
        self.assertEqual(
            (sensor.modelo_hardware, sensor.numero_serie, sensor.sector, sensor.nombre_sensor, sensor.valor_calibracion_min, sensor.valor_calibracion_max),
            ("DHT11", "SN-2", otro_sector, "Del fondo", Decimal("-5"), Decimal("45.5")),
        )

    def test_regla_2_el_sector_se_puede_quitar_y_sigue_las_reglas_del_alta(self):
        """IOT-MOD-HDW regla 2 y regla 3 de IOT-ALT-HDW: sin sector el equipo es general; uno inactivo o ajeno se rechaza."""
        self.modificar(self.cambiar(sector_id=None))
        self.assertIsNone(self.recargar().sector)
        inactivo = crear_sector(self.norte, "Sector C", estado="inactivo")
        self.assertEqual(self.codigos(self.cambiar(sector_id=inactivo.pk), "sector"), ["sector_invalido"])

    def test_regla_2_cambia_la_descripcion_del_actuador(self):
        """IOT-MOD-HDW regla 2: la descripción del actuador."""
        self.modificar(guardado(self.actuador, descripcion="Del galpón"), self.actuador)
        self.assertEqual(self.recargar(self.actuador).descripcion_actuador, "Del galpón")

    def test_regla_2_la_calibracion_sigue_la_regla_5_del_alta(self):
        """IOT-MOD-HDW regla 2 y regla 5 de IOT-ALT-HDW: obligatoria y con el mínimo menor que el máximo; las mismas validaciones del alta."""
        self.assertEqual(self.codigos(self.cambiar(calibracion_min="60", calibracion_max="10"), "calibracion_max"), ["calibracion_invertida"])
        self.assertEqual(self.codigos(self.cambiar(calibracion_min=""), "calibracion_min"), ["obligatorio"])
        error = error_de(lambda: self.modificar(self.cambiar(modelo="", numero_serie="s" * 61)))
        self.assertEqual(sorted(error.error_dict), ["modelo", "numero_serie"])

    def test_regla_2_la_fecha_y_el_insumo_no_se_modifican(self):
        """IOT-MOD-HDW regla 2: solo esos datos; la fecha de instalación y el insumo del formulario se ignoran."""
        fecha, insumo = self.sensor.fecha_instalacion, self.sensor.insumo
        self.modificar(self.cambiar(modelo="Otro", fecha_instalacion="2026-01-01", insumo_id=fabricas.insumo_de_hardware().pk))
        sensor = self.recargar()
        self.assertEqual((sensor.fecha_instalacion, sensor.insumo), (fecha, insumo))

    def test_regla_3_el_tipo_de_equipo_nunca_cambia(self):
        """IOT-MOD-HDW regla 3: no se puede cambiar si el equipo es un sensor o un actuador (la ``clase`` del formulario se ignora)."""
        self.modificar(self.cambiar(clase="actuador", modelo="Otro"))
        self.assertEqual((self.recargar().clase, self.sensor.modelo_hardware), ("sensor", "Otro"))

    def test_regla_6_el_cambio_de_calibracion_no_toca_las_lecturas_anteriores(self):
        """IOT-MOD-HDW regla 6: el cambio rige desde la próxima lectura: las anteriores quedan como se guardaron."""
        lectura = fabricas.telemetria(self.sensor, "70")
        self.modificar(self.cambiar(calibracion_min="0", calibracion_max="60"))
        lectura.refresh_from_db()
        self.assertEqual((lectura.valor_medido, lectura.valida), (Decimal("70.00"), True))

    # ---- regla 3: la variable y el tipo ----

    def test_regla_3_la_variable_cambia_si_el_sensor_no_tiene_lecturas(self):
        """IOT-MOD-HDW regla 3: la variable de un sensor se cambia mientras no tenga lecturas."""
        self.modificar(self.cambiar(variable="humedad", calibracion_min="0", calibracion_max="100"))
        self.assertEqual(self.recargar().tipo_variable_sensor, "humedad")

    def test_regla_3_la_variable_no_cambia_si_el_sensor_ya_tiene_lecturas(self):
        """IOT-MOD-HDW regla 3: con lecturas, un cambio de variable se rechaza (error de ``variable``); el mismo valor no es un cambio."""
        fabricas.telemetria(self.sensor)
        self.assertEqual(self.codigos(self.cambiar(variable="humedad"), "variable"), ["variable_con_lecturas"])
        self.assertEqual(self.modificar(self.cambiar(modelo="Nuevo")).modelo_hardware, "Nuevo")

    def test_regla_3_el_tipo_del_actuador_cambia_si_no_tiene_reglas_ni_comandos(self):
        """IOT-MOD-HDW regla 3: el tipo de un actuador cambia mientras no tenga reglas de actuación ni comandos."""
        otro = fabricas.tipo_actuador("Aspersor")
        self.modificar(guardado(self.actuador, tipo_actuador_id=otro.pk), self.actuador)
        self.assertEqual(self.recargar(self.actuador).tipo_actuador, otro)

    def test_regla_3_el_tipo_del_actuador_no_cambia_con_reglas_o_comandos(self):
        """IOT-MOD-HDW regla 3: con reglas o con comandos (también resueltos), el cambio de tipo se rechaza (error de ``tipo_actuador``)."""
        otro = fabricas.tipo_actuador("Aspersor")
        con_regla = fabricas.actuador(self.sistema, self.tipo, "norte/r")
        fabricas.regla(self.sensor, con_regla)
        con_comando = fabricas.actuador(self.sistema, self.tipo, "norte/c")
        fabricas.comando(con_comando, self.tipo.acciones.first(), "ejecutado")
        for equipo in (con_regla, con_comando):
            with self.subTest(equipo=equipo.identificador_equipo):
                self.assertEqual(self.codigos(guardado(equipo, tipo_actuador_id=otro.pk), "tipo_actuador", equipo), ["tipo_con_historial"])

    def test_regla_3_el_tipo_nuevo_tiene_que_estar_activo_y_se_bloquea_antes_de_cambiar(self):
        """IOT-MOD-HDW regla 3 y regla 7 de IOT-ALT-HDW: el tipo nuevo es uno activo (``tipo_inactivo``), bloqueado como en el alta (D-40)."""
        inactivo = fabricas.tipo_actuador("Viejo", activo=False)
        self.assertEqual(self.codigos(guardado(self.actuador, tipo_actuador_id=inactivo.pk), "tipo_actuador", self.actuador), ["tipo_inactivo"])

    def test_regla_10_al_cambiar_el_tipo_se_recalcula_la_compatibilidad(self):
        """IOT-MOD-HDW regla 10 y postcondición d: con el nuevo tipo se compara con el último anuncio y se genera o resuelve la alerta."""
        fabricas.equipo_anunciado(self.sistema, "norte/sectorA/ventilador", ("ENCENDER", "APAGAR"))
        hardware_a_recalcular = fabricas.tipo_actuador("Persiana de prueba", acciones=[("Abrir", "ABRIR"), ("Cerrar", "CERRAR")])
        self.modificar(guardado(self.actuador, tipo_actuador_id=hardware_a_recalcular.pk), self.actuador)
        actuador = self.recargar(self.actuador)
        self.assertEqual(actuador.compatibilidad, "incompatible")
        self.assertTrue(Alerta.objects.filter(tipo_alerta="iot_configuracion_incompatible", clave_estado=f"hw:{actuador.pk}", estado_alerta="activa").exists())

    # ---- regla 4: el identificador ----

    def test_regla_4_el_identificador_se_corrige_si_el_equipo_nunca_reporto(self):
        """IOT-MOD-HDW regla 4: sin lecturas, estados informados ni comandos, el identificador mal cargado se corrige."""
        self.modificar(self.cambiar(identificador="norte/sectorA/temp"))
        self.assertEqual(self.recargar().identificador_equipo, "norte/sectorA/temp")

    def test_regla_4_el_identificador_nuevo_sigue_la_regla_2_del_alta(self):
        """IOT-MOD-HDW regla 4: el identificador nuevo es válido y único (sin distinguir mayúsculas) entre los no dados de baja."""
        self.assertEqual(self.codigos(self.cambiar(identificador="con espacio"), "identificador"), ["identificador_invalido"])
        self.assertEqual(self.codigos(self.cambiar(identificador="NORTE/sectorA/VENTILADOR"), "identificador"), ["identificador_en_uso"])
        self.modificar(self.cambiar(identificador="NORTE/SECTORA/TEMPERATURA"))  # el mismo, con otras mayúsculas: no choca con él mismo
        self.assertEqual(self.recargar().identificador_equipo, "NORTE/SECTORA/TEMPERATURA")

    def test_regla_4_un_equipo_que_ya_reporto_conserva_su_identificador(self):
        """IOT-MOD-HDW regla 4: con lecturas, un estado informado, un mensaje del nodo o comandos, no se corrige (``identificador_ya_reporto``)."""
        con_lecturas = fabricas.sensor(self.sistema, "a/1")
        fabricas.telemetria(con_lecturas)
        con_mensaje = fabricas.sensor(self.sistema, "a/2", ultimo_mensaje_en=timezone.now())
        con_comandos = fabricas.actuador(self.sistema, self.tipo, "a/3")
        fabricas.comando(con_comandos, self.tipo.acciones.first(), "ejecutado")
        for equipo in (con_lecturas, con_mensaje, con_comandos):
            with self.subTest(equipo=equipo.identificador_equipo):
                datos = guardado(equipo, identificador=equipo.identificador_equipo + "x")
                self.assertEqual(self.codigos(datos, "identificador", equipo), ["identificador_ya_reporto"])

    def test_regla_4_corregir_el_identificador_resuelve_la_alerta_de_dispositivo_no_registrado(self):
        """IOT-MOD-HDW regla 4 y postcondición c de ALT: la alerta activa con el identificador NUEVO pasa a «resuelta»."""
        api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_no_registrado", "id:norte/sectora/temp")
        self.modificar(self.cambiar(identificador="norte/sectorA/temp"))
        self.assertEqual(Alerta.objects.get(clave_estado="id:norte/sectora/temp").estado_alerta, "resuelta")

    # ---- D-28 y auditoría ----

    def test_d28_sin_cambios_no_se_escribe_ni_se_audita(self):
        """D-28 y «Cómo se aplica» (IOT-MOD-HDW): sin cambios no se escribe ni se audita."""
        self.modificar(self.cambiar())
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_post_a_y_e_audita_el_antes_y_el_despues_de_lo_que_cambio(self):
        """IOT-MOD-HDW postcondiciones a y e (D-36): ``modificacion_hardware`` con el antes y el después de cada dato que cambió."""
        otro_sector = crear_sector(self.norte, "Sector B")
        self.modificar(self.cambiar(modelo="DHT11", sector_id=otro_sector.pk, calibracion_max="55"))
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual((registro.usuario_id, registro.rol), (self.laura.pk, "agronomo"))
        self.assertEqual([(a["modelo"], a["id"]) for a in registro.afectados], [("iot.sensor", self.sensor.pk)])
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["modelo_hardware"], {"antes": "DHT22", "despues": "DHT11"})
        self.assertEqual(cambios["valor_calibracion_max"], {"antes": "60.00", "despues": "55.00"})
        self.assertEqual(cambios["sector"]["despues"], {"id": otro_sector.pk, "texto": str(otro_sector)})
        self.assertNotIn("numero_serie", cambios)

    def test_post_e_el_registro_se_puede_leer_en_la_pantalla_de_auditoria(self):
        """D-36: los campos del registro tienen su nombre visible (``ETIQUETAS``)."""
        self.modificar(self.cambiar(modelo="DHT11", calibracion_max="55"))
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        filas = {campo for campo, _, _ in registro.filas_de_cambios()}
        self.assertTrue({"Modelo", "Calibración máxima"} <= filas)

    # ---- volver a activar (postcondición b, reglas 7 y 8) ----

    def test_post_b_volver_a_activar_pasa_el_equipo_a_activo_y_resuelve_sus_alertas_de_falla(self):
        """IOT-MOD-HDW postcondición b y regla 7: el equipo fuera de servicio pasa a «activo» y sus alertas activas de falla (en falla y comando fallido) a «resuelta»."""
        self.actuador.estado_hardware = "fuera_de_servicio"
        self.actuador.save()
        falla = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_en_falla", f"hw:{self.actuador.pk}")
        fallido = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_comando_fallido", f"hw:{self.actuador.pk}")
        ajena = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_en_falla", f"hw:{self.sensor.pk}")
        equipo = hardware.volver_a_activar(self.laura, self.actuador.pk)
        self.assertEqual(equipo.estado_hardware, "activo")
        self.assertEqual(
            {a.pk: a.estado_alerta for a in Alerta.objects.all()}, {falla.pk: "resuelta", fallido.pk: "resuelta", ajena.pk: "activa"}
        )

    def test_pre_volver_a_activar_solo_un_equipo_fuera_de_servicio(self):
        """IOT-MOD-HDW regla 7: volver a activar es para un equipo «fuera de servicio»; uno activo o dado de baja se rechaza."""
        baja = fabricas.sensor(self.sistema, "viejo/1", estado="inactivo")
        self.assertEqual(codigos_de(error_de(lambda: hardware.volver_a_activar(self.laura, self.sensor.pk))), ["equipo_no_fuera_de_servicio"])
        self.assertEqual(codigos_de(error_de(lambda: hardware.volver_a_activar(self.laura, baja.pk))), ["equipo_no_fuera_de_servicio"])

    def test_regla_8_las_ordenes_de_mantenimiento_se_completan_en_iot_07(self):
        """IOT-MOD-HDW regla 8: hasta IOT-07, ``mantenimientos_a_realizar(equipo)`` devuelve una lista vacía (Se completa en IOT-07)."""
        self.assertEqual(hardware.mantenimientos_a_realizar(self.sensor), [])

    def test_post_e_volver_a_activar_audita_como_reactivacion_desde_fuera_de_servicio(self):
        """IOT-MOD-HDW postcondición e y «Auditoría»: ``reactivacion_hardware`` con ``datos.desde = fuera_de_servicio`` y las alertas resueltas."""
        self.sensor.estado_hardware = "fuera_de_servicio"
        self.sensor.save()
        falla = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_en_falla", f"hw:{self.sensor.pk}")
        hardware.volver_a_activar(self.laura, self.sensor.pk)
        registro = RegistroAuditoria.objects.get(accion=REACTIVACION)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "fuera_de_servicio", "despues": "activo"})
        self.assertEqual(registro.detalle["datos"]["desde"], "fuera_de_servicio")
        self.assertEqual([(a["modelo"], a["id"]) for a in registro.afectados], [("iot.sensor", self.sensor.pk), ("maestros.alerta", falla.pk)])

    # ---- reactivar un equipo dado de baja (postcondición c, regla 9) ----

    def baja(self, equipo=None):
        """Da de baja directo en la base un equipo (el sensor por defecto)."""
        equipo = equipo or self.sensor
        equipo.estado_hardware, equipo.fecha_baja = "inactivo", timezone.localdate()
        equipo.save()
        return equipo

    def test_post_c_reactivar_deja_el_equipo_activo_con_su_historial_y_sin_fecha_de_baja(self):
        """IOT-MOD-HDW postcondición c y «Cómo se aplica»: pasa a «activo» y ``fecha_baja`` a nulo; conserva su historial."""
        lectura = fabricas.telemetria(self.sensor)
        self.baja()
        equipo = hardware.reactivar_hardware(self.laura, self.sensor.pk)
        equipo.refresh_from_db()
        self.assertEqual((equipo.estado_hardware, equipo.fecha_baja), ("activo", None))
        self.assertEqual(list(equipo.telemetrias.all()), [lectura])

    def test_post_c_reactivar_resuelve_la_alerta_de_dispositivo_no_registrado_con_su_identificador(self):
        """IOT-MOD-HDW postcondición c: la alerta activa «dispositivo no registrado» con su identificador pasa a «resuelta»."""
        self.baja()
        api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_no_registrado", "id:norte/sectora/temperatura")
        hardware.reactivar_hardware(self.laura, self.sensor.pk)
        self.assertEqual(Alerta.objects.get().estado_alerta, "resuelta")

    def test_regla_9_no_se_reactiva_si_otro_equipo_no_dado_de_baja_usa_el_identificador(self):
        """IOT-MOD-HDW regla 9: «No se puede reactivar: el identificador X ya lo usa {equipo} (registrado como reemplazo).»"""
        self.baja()
        fabricas.sensor(self.sistema, "NORTE/sectorA/temperatura")  # el reemplazo, con otras mayúsculas
        error = error_de(lambda: hardware.reactivar_hardware(self.laura, self.sensor.pk))
        self.assertEqual(codigos_de(error), ["identificador_en_uso"])
        self.assertEqual(
            error.error_dict["__all__"][0].message,
            "No se puede reactivar: el identificador norte/sectorA/temperatura ya lo usa Temperatura (registrado como reemplazo).",
        )
        self.assertEqual(self.recargar().estado_hardware, "inactivo")

    def test_regla_9_no_se_reactiva_si_su_sistema_esta_dado_de_baja(self):
        """IOT-MOD-HDW regla 9 (regla 2 de IOT-BAJ-SIS): un equipo de un sistema dado de baja no se reactiva."""
        self.baja()
        self.sistema.estado_sistema = "inactivo"
        self.sistema.save()
        self.assertEqual(codigos_de(error_de(lambda: hardware.reactivar_hardware(self.laura, self.sensor.pk))), ["sistema_dado_de_baja"])

    def test_pre_reactivar_solo_un_equipo_dado_de_baja(self):
        """IOT-MOD-HDW: reactivar es para un equipo dado de baja; uno activo se rechaza (``equipo_no_inactivo``)."""
        self.assertEqual(codigos_de(error_de(lambda: hardware.reactivar_hardware(self.laura, self.sensor.pk))), ["equipo_no_inactivo"])

    def test_regla_10_reactivar_un_actuador_recalcula_su_compatibilidad(self):
        """IOT-MOD-HDW regla 10 y postcondición d: al reactivar un actuador se compara con el último anuncio y se genera la alerta si es incompatible."""
        fabricas.equipo_anunciado(self.sistema, "norte/sectorA/ventilador", ("ENCENDER",))
        self.baja(self.actuador)
        equipo = hardware.reactivar_hardware(self.laura, self.actuador.pk)
        self.assertEqual(equipo.compatibilidad, "incompatible")
        self.assertTrue(Alerta.objects.filter(tipo_alerta="iot_configuracion_incompatible", estado_alerta="activa").exists())

    def test_regla_9_no_se_reactiva_un_actuador_cuyo_tipo_esta_dado_de_baja(self):
        """Decisión del plan de IOT-02 (completa la regla 9, L7): un actuador activo de un tipo inactivo rompería IOT-BAJ-TAC (``tipo_inactivo``)."""
        self.baja(self.actuador)
        self.tipo.estado = "inactivo"
        self.tipo.save()
        self.assertEqual(codigos_de(error_de(lambda: hardware.reactivar_hardware(self.laura, self.actuador.pk))), ["tipo_inactivo"])
        self.assertEqual(self.recargar(self.actuador).estado_hardware, "inactivo")

    def test_post_e_reactivar_audita_como_reactivacion_desde_inactivo(self):
        """IOT-MOD-HDW postcondición e y «Auditoría»: ``reactivacion_hardware`` con ``datos.desde = inactivo`` y la alerta resuelta."""
        self.baja()
        alerta = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_no_registrado", "id:norte/sectora/temperatura")
        hardware.reactivar_hardware(self.laura, self.sensor.pk)
        registro = RegistroAuditoria.objects.get(accion=REACTIVACION)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "inactivo", "despues": "activo"})
        self.assertEqual(registro.detalle["datos"]["desde"], "inactivo")
        self.assertEqual([(a["modelo"], a["id"]) for a in registro.afectados], [("iot.sensor", self.sensor.pk), ("maestros.alerta", alerta.pk)])

    # ---- las funciones que completan otras tareas ----

    def test_tiene_lecturas_consulta_la_tabla_de_lecturas(self):
        """IOT-MOD-HDW regla 3 («Se completa en IOT-03»): ``tiene_lecturas(sensor)`` es verdadero con una lectura creada por la fábrica."""
        self.assertFalse(hardware.tiene_lecturas(self.sensor))
        fabricas.telemetria(self.sensor)
        self.assertTrue(hardware.tiene_lecturas(self.sensor))

    def test_tiene_comandos_y_tiene_comando_pendiente_consultan_la_tabla_de_comandos(self):
        """IOT-MOD-HDW regla 3 y precondición c («Se completa en IOT-05»): un comando resuelto cuenta como comando; solo el pendiente cuenta como pendiente."""
        accion = self.tipo.acciones.first()
        self.assertEqual((hardware.tiene_comandos(self.actuador), hardware.tiene_comando_pendiente(self.actuador)), (False, False))
        fabricas.comando(self.actuador, accion, "ejecutado")
        self.assertEqual((hardware.tiene_comandos(self.actuador), hardware.tiene_comando_pendiente(self.actuador)), (True, False))
        fabricas.comando(self.actuador, accion, "pendiente")
        self.assertTrue(hardware.tiene_comando_pendiente(self.actuador))

    def test_tiene_reglas_cuenta_las_del_sensor_y_las_del_actuador(self):
        """IOT-MOD-HDW regla 3 («Se completa en IOT-06»): ``tiene_reglas(equipo)`` mira las reglas en que el equipo es el sensor o el actuador."""
        self.assertEqual((hardware.tiene_reglas(self.sensor), hardware.tiene_reglas(self.actuador)), (False, False))
        fabricas.regla(self.sensor, self.actuador)
        self.assertEqual((hardware.tiene_reglas(self.sensor), hardware.tiene_reglas(self.actuador)), (True, True))
