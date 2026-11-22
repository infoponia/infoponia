# Pruebas de IOT-ALT-HDW · Alta Hardware (docs/casos_de_uso/iot/hardware.md, v0.2, con «Cómo se aplica en la ronda IoT 1») y de lo que cita: D-36
# (auditoría), D-40 (bloqueos) y D-72 (modelo). Se escribieron ANTES que el servicio.
#
# Servicios que se prueban (iot/servicios/hardware.py), tomados del módulo dentro de cada prueba:
#   alta_hardware(actor, sistema_id, datos: DatosDeEquipo) -> Sensor | Actuador
#   baja_con_identificador(sistema, identificador) -> el equipo dado de baja que tenía ese identificador, o None (regla 12)
#   identificadores_anunciados_libres(sistema) -> [Anunciado(identificador, clase, era_de)] (regla 14)
# Errores: ``PermissionDenied`` (rol), ``Http404`` (sistema inexistente), ``ValidationError`` por campo (``clase``, ``variable``, ``tipo_actuador``,
# ``identificador``, ``modelo``, ``numero_serie``, ``nombre_sensor``, ``descripcion``, ``calibracion_min``, ``calibracion_max``, ``fecha_instalacion``,
# ``insumo``, ``sector``) o general (``fuera_de_alcance``, ``sistema_dado_de_baja``).

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.categorias import ENVASES
from inventario.models import Insumo, MovimientoInsumo
from inventario.tests.fabricas import categoria_del_sistema, perezoso
from iot.models import Actuador, Hardware, Sensor
from iot.tests import fabricas
from iot.tests.fabricas import datos_de_equipo
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import (
    codigos_de,
    crear_agronomo,
    crear_invernadero,
    crear_sector,
    crear_tecnico,
    crear_vendedor,
    error_de,
)

hardware = perezoso("iot.servicios.hardware")
ALTA = "alta_hardware"


class IotAltHdwServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-ALT-HDW."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=crear_tecnico("t@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.sector = crear_sector(self.norte, "Sector A")

    def alta(self, datos=None, sistema=None, actor=None):
        """Llama al servicio (un sensor válido, en el sistema de Norte y como Laura por defecto)."""
        return hardware.alta_hardware(actor or self.laura, (sistema or self.sistema).pk, datos or datos_de_equipo())

    def codigos(self, datos, campo=None, sistema=None, actor=None):
        """Los códigos de error de ``campo`` (o de todos) que da el alta con ``datos``."""
        return codigos_de(error_de(lambda: self.alta(datos, sistema, actor)), campo)

    # ---- precondición a, regla 1 (alcance) y precondición b ----

    def test_pre_a_otros_roles_no_dan_de_alta(self):
        """IOT-ALT-HDW precondición a: cuenta activa de Agrónomo o de Gerente; los demás roles reciben 403."""
        for actor in (crear_capataz(), crear_vendedor(), crear_tecnico("otro@infoponia.com"), crear_administrador()):
            with self.subTest(actor=actor.email), self.assertRaises(PermissionDenied):
                self.alta(actor=actor)
        self.assertFalse(Hardware.objects.filter(clase="sensor").exists())

    def test_pre_a_una_cuenta_inactiva_no_da_de_alta(self):
        """IOT-ALT-HDW precondición a: «cuenta activa»."""
        self.laura.is_active = False
        self.laura.save()
        with self.assertRaises(PermissionDenied):
            self.alta()

    def test_regla_1_el_agronomo_da_de_alta_en_su_invernadero_y_no_en_el_de_otro(self):
        """IOT-ALT-HDW regla 1 (alcance de IOT-DSC-SIS): el Agrónomo opera los invernaderos a su cargo."""
        self.assertEqual(self.alta().sistema, self.sistema)
        ajeno = fabricas.sistema(crear_invernadero("Ajeno", agronomo=crear_agronomo("otra@infoponia.com")))
        self.assertEqual(self.codigos(datos_de_equipo(), sistema=ajeno), ["fuera_de_alcance"])

    def test_regla_1_el_gerente_opera_solo_donde_no_hay_agronomo_activo(self):
        """IOT-ALT-HDW regla 1: el Gerente opera solo los invernaderos sin Agrónomo activo; en los demás, solo consulta."""
        self.assertEqual(self.codigos(datos_de_equipo(), actor=self.gerente), ["fuera_de_alcance"])
        libre = fabricas.sistema(crear_invernadero("Libre"))
        self.assertEqual(self.alta(sistema=libre, actor=self.gerente).sistema, libre)

    def test_pre_b_un_sistema_que_no_existe_da_404(self):
        """IOT-ALT-HDW precondición b: un id de sistema que no existe da ``Http404``."""
        with self.assertRaises(Http404):
            hardware.alta_hardware(self.laura, 999999, datos_de_equipo())

    def test_pre_b_un_sistema_dado_de_baja_no_recibe_equipos(self):
        """IOT-ALT-HDW precondición b: el sistema está «activo» o «desconectado» (``sistema_dado_de_baja``)."""
        baja = fabricas.sistema(crear_invernadero("Viejo", agronomo=self.laura), "inactivo")
        self.assertEqual(self.codigos(datos_de_equipo(), sistema=baja), ["sistema_dado_de_baja"])

    def test_regla_11_con_el_sistema_desconectado_el_equipo_queda_registrado(self):
        """IOT-ALT-HDW regla 11: con el sistema desconectado el equipo se registra igual."""
        desconectado = fabricas.sistema(crear_invernadero("Otro", agronomo=self.laura), "desconectado")
        self.assertEqual(self.alta(sistema=desconectado).estado_hardware, "activo")

    # ---- regla 2: el identificador ----

    def test_regla_2_el_identificador_es_obligatorio(self):
        """IOT-ALT-HDW regla 2: obligatorio."""
        self.assertEqual(self.codigos(datos_de_equipo(identificador="   "), "identificador"), ["obligatorio"])

    def test_regla_2_el_identificador_no_lleva_espacios_ni_caracteres_raros(self):
        """IOT-ALT-HDW regla 2: sin espacios, de letras, números y «- _ . /»."""
        for malo in ("norte sectorA", "norte#1", "ñandú", "a,b", "temp@1"):
            with self.subTest(identificador=malo):
                self.assertEqual(self.codigos(datos_de_equipo(identificador=malo), "identificador"), ["identificador_invalido"])

    def test_regla_2_el_identificador_admite_hasta_64_caracteres(self):
        """IOT-ALT-HDW regla 2: hasta 64 caracteres."""
        self.assertEqual(self.codigos(datos_de_equipo(identificador="a" * 65), "identificador"), ["identificador_invalido"])
        self.assertEqual(self.alta(datos_de_equipo(identificador="a" * 64)).identificador_equipo, "a" * 64)

    def test_regla_2_el_identificador_se_guarda_como_se_escribio_y_recortado(self):
        """IOT-ALT-HDW regla 2 y «Cómo se aplica»: se recorta y se guarda como se escribió (la comparación es en minúsculas)."""
        self.assertEqual(self.alta(datos_de_equipo(identificador="  Norte/Sector-A_1.temp ")).identificador_equipo, "Norte/Sector-A_1.temp")

    def test_regla_2_el_identificador_es_unico_entre_los_equipos_no_dados_de_baja_sin_distinguir_mayusculas(self):
        """IOT-ALT-HDW regla 2 y precondición c: «Ya lo usa {equipo} en este sistema IoT.» como error del campo; ``{equipo}`` es el nombre del equipo del prototipo (``hwName``: la variable del sensor o el tipo del actuador)."""
        fabricas.sensor(self.sistema, "NORTE/sectorA/temperatura")
        error = error_de(lambda: self.alta(datos_de_equipo(identificador="norte/SECTORa/temperatura")))
        self.assertEqual(codigos_de(error, "identificador"), ["identificador_en_uso"])
        self.assertEqual(error.error_dict["identificador"][0].message, "Ya lo usa Temperatura en este sistema IoT.")

    def test_regla_2_un_equipo_de_reemplazo_puede_usar_el_identificador_de_uno_dado_de_baja(self):
        """IOT-ALT-HDW regla 2: «un equipo de reemplazo puede usar el identificador de uno dado de baja»; el anterior conserva su historial."""
        viejo = fabricas.sensor(self.sistema, "norte/sectorA/temperatura", estado="inactivo")
        nuevo = self.alta()
        self.assertNotEqual(nuevo.pk, viejo.pk)
        viejo.refresh_from_db()
        self.assertEqual((viejo.estado_hardware, nuevo.estado_hardware), ("inactivo", "activo"))

    def test_regla_2_dos_sistemas_pueden_usar_los_mismos_identificadores(self):
        """IOT-ALT-HDW regla 2: «dos sistemas IoT pueden usar los mismos identificadores»."""
        otro = fabricas.sistema(crear_invernadero("Sur", agronomo=self.laura))
        fabricas.sensor(otro, "norte/sectorA/temperatura")
        self.assertTrue(self.alta())

    # ---- el tipo de equipo, regla 4 (sensor) y regla 5 (calibración) ----

    def test_el_tipo_de_equipo_es_obligatorio_y_de_la_lista(self):
        """IOT-ALT-HDW: el equipo es un sensor o un actuador (campo ``clase``)."""
        for clase in ("", "nodo", "otro"):
            with self.subTest(clase=clase):
                self.assertEqual(self.codigos(datos_de_equipo(clase=clase), "clase"), ["clase_invalida"])

    def test_regla_4_la_variable_se_elige_de_la_lista_fija(self):
        """IOT-ALT-HDW regla 4: temperatura, humedad, intensidad lumínica, temperatura de la solución y nivel de la solución."""
        self.assertEqual(self.codigos(datos_de_equipo(variable=""), "variable"), ["obligatorio"])
        self.assertEqual(self.codigos(datos_de_equipo(variable="fotoperiodo"), "variable"), ["variable_invalida"])
        for variable in ("temperatura", "humedad", "intensidad_luz", "temperatura_solucion", "nivel_solucion"):
            with self.subTest(variable=variable):
                sensor = self.alta(datos_de_equipo(identificador=f"id/{variable}", variable=variable))
                self.assertEqual(sensor.tipo_variable_sensor, variable)

    def test_regla_4_la_unidad_la_fija_la_variable(self):
        """IOT-ALT-HDW regla 4: °C, % HR, lux, °C y sin unidad para el nivel (no se guarda: sale de la variable)."""
        esperado = {"temperatura": "°C", "humedad": "% HR", "intensidad_luz": "lux", "temperatura_solucion": "°C", "nivel_solucion": ""}
        for variable, unidad in esperado.items():
            with self.subTest(variable=variable):
                self.assertEqual(self.alta(datos_de_equipo(identificador=f"u/{variable}", variable=variable)).unidad_medida, unidad)

    def test_regla_5_la_calibracion_es_obligatoria_y_el_minimo_menor_que_el_maximo(self):
        """IOT-ALT-HDW regla 5: obligatoria salvo en el nivel; el mínimo es menor que el máximo (error del máximo)."""
        self.assertEqual(self.codigos(datos_de_equipo(calibracion_min=""), "calibracion_min"), ["obligatorio"])
        self.assertEqual(self.codigos(datos_de_equipo(calibracion_max=""), "calibracion_max"), ["obligatorio"])
        for minimo, maximo in (("50", "0"), ("10", "10")):
            with self.subTest(minimo=minimo, maximo=maximo):
                self.assertEqual(
                    self.codigos(datos_de_equipo(calibracion_min=minimo, calibracion_max=maximo), "calibracion_max"), ["calibracion_invertida"]
                )

    def test_regla_5_la_calibracion_son_numeros_con_dos_decimales_como_mucho(self):
        """docs/modelo/iot.md, «Sensor»: ``Decimal(9,2)``; un texto o un valor que no cabe es un error del campo."""
        self.assertEqual(self.codigos(datos_de_equipo(calibracion_min="frío"), "calibracion_min"), ["calibracion_invalida"])
        self.assertEqual(self.codigos(datos_de_equipo(calibracion_min="1.234"), "calibracion_min"), ["calibracion_invalida"])
        self.assertEqual(self.codigos(datos_de_equipo(calibracion_max="99999999"), "calibracion_max"), ["calibracion_invalida"])
        self.assertEqual(self.alta(datos_de_equipo(calibracion_min="-10.5", calibracion_max="60")).valor_calibracion_min, Decimal("-10.50"))

    def test_regla_5_el_nivel_de_la_solucion_no_lleva_calibracion(self):
        """IOT-ALT-HDW regla 5 y postcondición b: el nivel solo informa «normal» o «bajo»: la calibración queda nula aunque se envíe."""
        sensor = self.alta(datos_de_equipo(variable="nivel_solucion", calibracion_min="", calibracion_max=""))
        self.assertEqual((sensor.valor_calibracion_min, sensor.valor_calibracion_max), (None, None))
        sensor = self.alta(datos_de_equipo(identificador="otro/nivel", variable="nivel_solucion", calibracion_min="1", calibracion_max="5"))
        self.assertEqual((sensor.valor_calibracion_min, sensor.valor_calibracion_max), (None, None))

    def test_postcondicion_b_el_nombre_del_sensor_es_opcional_y_hasta_60(self):
        """IOT-ALT-HDW postcondición b y docs/modelo/iot.md, «Sensor»: nombre opcional, hasta 60 caracteres, recortado."""
        self.assertEqual(self.alta(datos_de_equipo(nombre_sensor="  Del fondo ")).nombre_sensor, "Del fondo")
        self.assertEqual(self.codigos(datos_de_equipo(identificador="x/1", nombre_sensor="n" * 61), "nombre_sensor"), ["demasiado_largo"])
        self.assertEqual(self.alta(datos_de_equipo(identificador="x/2")).nombre_sensor, "")

    # ---- regla 7: el tipo de actuador ----

    def test_regla_7_el_tipo_de_actuador_se_elige_entre_los_activos(self):
        """IOT-ALT-HDW regla 7: un tipo activo; uno inactivo, uno inexistente o ninguno se rechazan (error de ``tipo_actuador``)."""
        inactivo = fabricas.tipo_actuador("Viejo", activo=False)
        self.assertEqual(self.codigos(datos_de_equipo("actuador", tipo_actuador_id=inactivo.pk), "tipo_actuador"), ["tipo_inactivo"])
        self.assertEqual(self.codigos(datos_de_equipo("actuador", tipo_actuador_id=999999), "tipo_actuador"), ["tipo_invalido"])
        self.assertEqual(self.codigos(datos_de_equipo("actuador", tipo_actuador_id=None), "tipo_actuador"), ["obligatorio"])

    def test_regla_7_un_sensor_ignora_el_tipo_de_actuador_y_un_actuador_la_variable(self):
        """IOT-ALT-HDW postcondiciones b y c: cada clase lleva sus datos; los de la otra se ignoran (no son errores)."""
        sensor = self.alta(datos_de_equipo(tipo_actuador_id=None))
        self.assertIsInstance(sensor, Sensor)
        actuador = self.alta(datos_de_equipo("actuador", variable="", calibracion_min="x"))
        self.assertIsInstance(actuador, Actuador)

    def test_postcondicion_c_el_actuador_queda_con_su_descripcion_y_su_tipo(self):
        """IOT-ALT-HDW postcondición c: descripción opcional (hasta 300) y asociado a su tipo; compatibilidad inicial «sin verificar»."""
        tipo = fabricas.tipo_actuador("Extractor")
        actuador = self.alta(datos_de_equipo("actuador", tipo_actuador_id=tipo.pk, descripcion="  Del galpón  "))
        self.assertEqual((actuador.tipo_actuador, actuador.descripcion_actuador, actuador.compatibilidad), (tipo, "Del galpón", "sin_verificar"))
        self.assertEqual(self.codigos(datos_de_equipo("actuador", identificador="x/2", descripcion="d" * 301), "descripcion"), ["demasiado_largo"])

    def test_regla_7_el_alta_de_un_actuador_bloquea_el_tipo_antes_de_crearlo(self):
        """Contrato de ``bloquear_tipo_activo`` (D-40, IOT-BAJ-TAC): quien crea un actuador bloquea el tipo ANTES de insertarlo."""
        tipo = fabricas.tipo_actuador("Extractor")
        with mock.patch("iot.servicios.hardware.bloquear_tipo_activo", wraps=lambda tipo_id: tipo) as bloqueo:
            self.alta(datos_de_equipo("actuador", tipo_actuador_id=tipo.pk))
        bloqueo.assert_called_once_with(tipo.pk)

    # ---- reglas 3, 8, 9 y 13 ----

    def test_regla_3_el_sector_es_opcional_y_del_mismo_invernadero(self):
        """IOT-ALT-HDW regla 3: sin sector el equipo es general del invernadero; con sector, uno activo o fuera de servicio del mismo invernadero."""
        self.assertIsNone(self.alta().sector)
        self.assertEqual(self.alta(datos_de_equipo(identificador="s/1", sector_id=self.sector.pk)).sector, self.sector)
        fuera = crear_sector(self.norte, "Sector B", estado="fuera_de_servicio")
        self.assertEqual(self.alta(datos_de_equipo(identificador="s/2", sector_id=fuera.pk)).sector, fuera)

    def test_regla_3_un_sector_inactivo_o_de_otro_invernadero_se_rechaza(self):
        """IOT-ALT-HDW regla 3 (regla 21 de 8.20): un sector dado de baja o de otro invernadero, o que no existe, es un error de ``sector``."""
        inactivo = crear_sector(self.norte, "Sector C", estado="inactivo")
        ajeno = crear_sector(crear_invernadero("Sur", agronomo=self.laura), "Sector D")
        for sector_id in (inactivo.pk, ajeno.pk, 999999):
            with self.subTest(sector_id=sector_id):
                self.assertEqual(self.codigos(datos_de_equipo(sector_id=sector_id), "sector"), ["sector_invalido"])

    def test_regla_8_el_insumo_es_de_repuestos_de_hardware_y_activo(self):
        """IOT-ALT-HDW regla 8: obligatorio; un insumo de otra categoría o inactivo se rechaza."""
        envase = Insumo.objects.create(nombre_insumo="Bandeja", tipo_insumo=categoria_del_sistema(ENVASES), unidad_medida_insumo="unidad")
        inactivo = fabricas.insumo_de_hardware()
        inactivo.estado_insumo = "inactivo"
        inactivo.save()
        self.assertEqual(self.codigos(datos_de_equipo(insumo_id=None), "insumo"), ["obligatorio"])
        for insumo in (envase, inactivo):
            with self.subTest(insumo=insumo.nombre_insumo):
                self.assertEqual(self.codigos(datos_de_equipo(insumo_id=insumo.pk), "insumo"), ["insumo_invalido"])

    def test_regla_8_el_alta_no_habilita_ni_consume_stock_del_insumo(self):
        """IOT-ALT-HDW regla 8: no hace falta que esté habilitado ni que tenga stock; dar de alta un equipo no mueve stock."""
        equipo = self.alta()
        self.assertEqual(equipo.insumo.tipo_insumo.codigo, "repuestos_de_hardware")
        self.assertFalse(MovimientoInsumo.objects.exists())

    def test_regla_9_la_fecha_de_instalacion_es_obligatoria_y_no_posterior_a_hoy(self):
        """IOT-ALT-HDW regla 9: obligatoria; hoy se acepta, mañana no."""
        self.assertEqual(self.codigos(datos_de_equipo(fecha_instalacion=None), "fecha_instalacion"), ["obligatorio"])
        hoy = timezone.localdate()
        self.assertEqual(self.codigos(datos_de_equipo(fecha_instalacion=hoy + timedelta(days=1)), "fecha_instalacion"), ["fecha_futura"])
        self.assertEqual(self.alta(datos_de_equipo(fecha_instalacion=hoy)).fecha_instalacion, hoy)
        self.assertEqual(self.alta(datos_de_equipo(identificador="f/1", fecha_instalacion="2026-10-01")).fecha_instalacion.isoformat(), "2026-10-01")

    def test_regla_13_el_numero_de_serie_es_opcional_y_no_es_unico(self):
        """IOT-ALT-HDW regla 13: un aparato que mide dos variables se registra como dos sensores con el mismo número de serie."""
        uno = self.alta(datos_de_equipo(identificador="dht/temperatura", numero_serie="SN-1"))
        dos = self.alta(datos_de_equipo(identificador="dht/humedad", variable="humedad", numero_serie="SN-1"))
        self.assertEqual((uno.numero_serie, dos.numero_serie), ("SN-1", "SN-1"))
        self.assertEqual(self.codigos(datos_de_equipo(identificador="x/1", numero_serie="s" * 61), "numero_serie"), ["demasiado_largo"])

    def test_el_modelo_es_obligatorio_y_hasta_60_caracteres(self):
        """docs/modelo/iot.md, «Hardware»: ``modelo_hardware`` obligatorio, hasta 60."""
        self.assertEqual(self.codigos(datos_de_equipo(modelo=""), "modelo"), ["obligatorio"])
        self.assertEqual(self.codigos(datos_de_equipo(modelo="m" * 61), "modelo"), ["demasiado_largo"])

    def test_todos_los_errores_se_marcan_juntos(self):
        """docs/patrones/abm.md, sección 2, paso 2: un solo ``ValidationError`` con un error por campo."""
        error = error_de(lambda: self.alta(datos_de_equipo(identificador="", modelo="", fecha_instalacion=None, calibracion_min="")))
        self.assertEqual(sorted(error.error_dict), ["calibracion_min", "fecha_instalacion", "identificador", "modelo"])

    # ---- postcondiciones ----

    def test_post_a_crea_el_equipo_activo_asociado_al_sistema_al_insumo_y_al_sector(self):
        """IOT-ALT-HDW postcondición a: estado «activo», con identificador, modelo, serie y fecha, asociado al sistema, al insumo y al sector."""
        datos = datos_de_equipo(numero_serie="SN-5", sector_id=self.sector.pk)
        sensor = self.alta(datos)
        sensor.refresh_from_db()
        self.assertEqual(
            (sensor.clase, sensor.estado_hardware, sensor.identificador_equipo, sensor.modelo_hardware, sensor.numero_serie, sensor.sistema, sensor.sector),
            ("sensor", "activo", "norte/sectorA/temperatura", "DHT22", "SN-5", self.sistema, self.sector),
        )
        self.assertEqual(sensor.insumo_id, datos.insumo_id)
        self.assertEqual((sensor.ultimo_mensaje_en, sensor.fecha_baja), (None, None))

    def test_post_b_el_sensor_queda_con_su_variable_y_su_calibracion(self):
        """IOT-ALT-HDW postcondición b: variable, unidad y calibración (mínimo y máximo)."""
        sensor = self.alta(datos_de_equipo(variable="humedad", calibracion_min="0", calibracion_max="100"))
        sensor.refresh_from_db()
        self.assertEqual((sensor.tipo_variable_sensor, sensor.valor_calibracion_min, sensor.valor_calibracion_max), ("humedad", Decimal("0"), Decimal("100")))

    def test_post_d_resuelve_la_alerta_de_dispositivo_no_registrado_con_ese_identificador(self):
        """IOT-ALT-HDW postcondición d y regla 12: la alerta activa «dispositivo no registrado» con ese identificador (en minúsculas) pasa a «resuelta»."""
        api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_no_registrado", "id:norte/sectora/temperatura")
        otra = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_no_registrado", "id:otro/equipo")
        self.alta(datos_de_equipo(identificador="Norte/sectorA/temperatura"))
        estados = dict(Alerta.objects.values_list("clave_estado", "estado_alerta"))
        self.assertEqual(estados, {"id:norte/sectora/temperatura": "resuelta", "id:otro/equipo": "activa"})
        self.assertEqual(Alerta.objects.get(pk=otra.pk).estado_alerta, "activa")

    def test_post_e_audita_el_equipo_y_la_alerta_resuelta(self):
        """IOT-ALT-HDW postcondición e y «Auditoría» (D-36): un registro ``alta_hardware`` con el equipo y la alerta resuelta."""
        alerta = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_no_registrado", "id:norte/sectora/temperatura")
        sensor = self.alta(datos_de_equipo(sector_id=self.sector.pk))
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.laura.pk, "agronomo"))
        self.assertEqual(
            [(a["modelo"], a["id"]) for a in registro.afectados], [("iot.sensor", sensor.pk), ("maestros.alerta", alerta.pk)]
        )
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["identificador_equipo"], {"antes": None, "despues": "norte/sectorA/temperatura"})
        self.assertEqual(cambios["sector"], {"antes": None, "despues": {"id": self.sector.pk, "texto": str(self.sector)}})

    def test_post_e_el_registro_se_puede_leer_en_la_pantalla_de_auditoria(self):
        """D-36: los campos del registro tienen su nombre visible (``ETIQUETAS``) y el Gerente lo ve."""
        self.alta()
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        filas = {campo for campo, _, _ in registro.filas_de_cambios()}
        self.assertTrue({"Identificador del equipo", "Modelo", "Insumo"} <= filas)
        self.assertIn(registro, RegistroAuditoria.objects.visibles_para(self.gerente))

    def test_post_e_un_alta_rechazada_no_audita_ni_crea_nada(self):
        """D-22: no queda un registro ni un equipo de una operación que no se hizo."""
        self.codigos(datos_de_equipo(modelo=""))
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())
        self.assertFalse(Hardware.objects.filter(clase="sensor").exists())

    # ---- regla 12 y 14: identificadores anunciados y compatibilidad ----

    def test_regla_14_un_actuador_anunciado_compatible_queda_compatible(self):
        """IOT-ALT-HDW regla 14: si el nodo anunció el equipo y soporta los comandos de las acciones del tipo, queda «compatible»."""
        fabricas.equipo_anunciado(self.sistema, "norte/sectorA/ventilador", ("ENCENDER", "APAGAR"))
        actuador = self.alta(datos_de_equipo("actuador"))
        self.assertEqual(actuador.compatibilidad, "compatible")

    def test_regla_14_un_actuador_anunciado_incompatible_se_advierte_pero_se_registra(self):
        """IOT-ALT-HDW regla 14: una incompatibilidad se advierte y no impide el alta; queda la alerta «configuración incompatible»."""
        fabricas.equipo_anunciado(self.sistema, "norte/sectorA/ventilador", ("ENCENDER",))
        actuador = self.alta(datos_de_equipo("actuador"))
        self.assertEqual(actuador.compatibilidad, "incompatible")
        self.assertEqual([a.nombre_accion for a in actuador.acciones_incompatibles.all()], ["Apagar"])
        self.assertTrue(Alerta.objects.filter(tipo_alerta="iot_configuracion_incompatible", clave_estado=f"hw:{actuador.pk}", estado_alerta="activa").exists())

    def test_regla_14_sin_anuncio_la_compatibilidad_queda_sin_verificar(self):
        """IOT-ALT-HDW regla 14: si el nodo no anuncia sus equipos, «sin verificar» y no se restringe ninguna acción."""
        actuador = self.alta(datos_de_equipo("actuador"))
        self.assertEqual((actuador.compatibilidad, actuador.acciones_incompatibles.count()), ("sin_verificar", 0))
        self.assertFalse(Alerta.objects.filter(tipo_alerta="iot_configuracion_incompatible").exists())

    def test_regla_14_un_sensor_no_tiene_compatibilidad(self):
        """IOT-ALT-HDW regla 14: la compatibilidad es de los actuadores."""
        fabricas.equipo_anunciado(self.sistema, "norte/sectorA/temperatura", clase="sensor")
        self.alta()
        self.assertFalse(Alerta.objects.filter(tipo_alerta="iot_configuracion_incompatible").exists())

    def test_regla_14_los_identificadores_anunciados_libres_marcan_los_que_eran_de_un_equipo_dado_de_baja(self):
        """IOT-ALT-HDW reglas 12 y 14: se ofrecen los anunciados que todavía no están registrados, marcando los de un equipo dado de baja."""
        fabricas.sensor(self.sistema, "ya/registrado")
        viejo = fabricas.sensor(self.sistema, "era/de/baja", estado="inactivo")
        for identificador in ("YA/registrado", "era/de/baja", "nuevo/uno"):
            fabricas.equipo_anunciado(self.sistema, identificador, clase="sensor" if identificador != "nuevo/uno" else "actuador")
        libres = {a.identificador: a for a in hardware.identificadores_anunciados_libres(self.sistema)}
        self.assertEqual(sorted(libres), ["era/de/baja", "nuevo/uno"])
        self.assertEqual((libres["era/de/baja"].era_de, libres["nuevo/uno"].era_de), (viejo, None))
        self.assertEqual(libres["nuevo/uno"].clase, "actuador")

    def test_regla_12_baja_con_identificador_encuentra_el_equipo_dado_de_baja(self):
        """IOT-ALT-HDW regla 12: si el identificador es el de un equipo dado de baja, el alta lo advierte y ofrece reactivarlo."""
        viejo = fabricas.sensor(self.sistema, "era/de/baja", estado="inactivo")
        self.assertEqual(hardware.baja_con_identificador(self.sistema, " ERA/de/baja "), viejo)
        self.assertIsNone(hardware.baja_con_identificador(self.sistema, "otro/id"))
        fabricas.sensor(self.sistema, "era/de/baja")  # ya hay uno en uso con ese identificador: no hay nada que reactivar
        self.assertIsNone(hardware.baja_con_identificador(self.sistema, "era/de/baja"))
