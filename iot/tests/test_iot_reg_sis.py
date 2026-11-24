# Pruebas de IOT-REG-SIS · Registrar Sistema IoT (docs/casos_de_uso/iot/sistema_iot.md, v0.2 extendido, con «Cómo se aplica en la ronda
# IoT 1») y de lo que cita: D-70 (el token), D-72, D-36 (auditoría), D-40 y docs/patrones/bloqueos.md. Se escribieron ANTES que el servicio.
#
# Servicios que se prueban (iot/servicios/sistemas.py), tomados del módulo dentro de cada prueba:
#   resumen_de_registro(actor, datos: DatosDeSistema) -> ResumenDeRegistro        (pasos 5 y 6: valida todo y NO escribe)
#   registrar_sistema_iot(actor, datos: DatosDeSistema) -> (SistemaIoT, token)    (paso 8)
#   invernaderos_para_registrar(actor) -> [Elegible(invernadero, tecnico, tuvo_sistema)]       (paso 2 y extensión 1a)
#   sistema_del_invernadero(actor, invernadero_id) -> SistemaIoT | None
#   conectividad(nodo, ahora) -> Conectividad(estado, texto)
#   acciones_permitidas(actor, sistema) -> frozenset
#   insumos_de_hardware() -> los insumos activos de la categoría «Repuestos de hardware» (precondición c)
# Errores: ``PermissionDenied`` (rol), ``Http404`` (invernadero inexistente), ``ValidationError`` por campo (``nombre``, ``modelo``,
# ``numero_serie``, ``fecha_instalacion``, ``insumo``, ``temp_solucion_max``) o general (``__all__``: ``fuera_de_alcance``,
# ``invernadero_inactivo``, ``sistema_existente``, ``sin_insumos_de_hardware``).
# El estado del IoT que ve `maestros` (para la alerta del Técnico) lo da un registrante falso: ``fabricas.con_iot_registrado()``.

import json
from datetime import timedelta
from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from core.enlaces import resumen_de
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.categorias import ENVASES
from inventario.models import Insumo
from inventario.tests.fabricas import categoria_del_sistema, perezoso
from iot.models import NodoCentral, SistemaIoT
from iot.tests import fabricas
from iot.tests.fabricas import datos_de_sistema
from maestros.models import Alerta
from maestros.tests.fabricas import (
    codigos_de,
    crear_agronomo,
    crear_invernadero,
    crear_tecnico,
    crear_vendedor,
    error_de,
)

sistemas = perezoso("iot.servicios.sistemas")
ALTA = "alta_sistema_iot"


class IotRegSisServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondiciones, flujo, extensiones, reglas y postcondiciones de IOT-REG-SIS."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.tecnico = crear_tecnico("tecnico@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=self.tecnico)
        self.datos = datos_de_sistema(self.norte)

    def registrar(self, datos=None, actor=None):
        """Llama al servicio de registro (el Agrónomo Laura y su invernadero por defecto)."""
        return sistemas.registrar_sistema_iot(actor or self.laura, datos or self.datos)

    def codigos(self, datos=None, campo=None, actor=None):
        """Los códigos de error de ``campo`` (o de todos) que da el registro con ``datos``."""
        return codigos_de(error_de(lambda: self.registrar(datos, actor)), campo)

    def alertas_de_tecnico(self):
        return Alerta.objects.filter(tipo_alerta="sin_tecnico", estado_alerta="activa")

    # ---- precondición a: el actor ----

    def test_pre_a_otros_roles_no_registran(self):
        """IOT-REG-SIS precondición a: cuenta activa de Agrónomo o de Gerente; el Capataz, el Vendedor, el Técnico y el Administrador reciben 403."""
        for actor in (crear_capataz(), crear_vendedor(), crear_tecnico("otro.tecnico@infoponia.com"), crear_administrador()):
            for funcion in (sistemas.registrar_sistema_iot, sistemas.resumen_de_registro):
                with self.subTest(actor=actor.email, funcion=funcion.__name__), self.assertRaises(PermissionDenied):
                    funcion(actor, self.datos)
        self.assertFalse(SistemaIoT.objects.exists())

    def test_pre_a_una_cuenta_inactiva_no_registra(self):
        """IOT-REG-SIS precondición a: «cuenta activa»."""
        self.laura.is_active = False
        self.laura.save()
        with self.assertRaises(PermissionDenied):
            self.registrar()

    def test_pre_a_sin_actor_no_registra(self):
        """IOT-REG-SIS precondición a: sin cuenta no hay registro."""
        with self.assertRaises(PermissionDenied):
            sistemas.registrar_sistema_iot(None, self.datos)

    # ---- precondición b, regla «Alcance», regla «Invernadero elegible» y extensiones 1a, 8a y 8b ----

    def test_regla_alcance_el_agronomo_registra_en_su_invernadero(self):
        """IOT-REG-SIS regla «Alcance»: el Agrónomo opera el IoT de los invernaderos activos a su cargo."""
        sistema, _ = self.registrar()
        self.assertEqual(sistema.invernadero, self.norte)

    def test_regla_alcance_el_agronomo_no_registra_en_el_invernadero_de_otro(self):
        """IOT-REG-SIS regla «Alcance» y extensión 8b: un invernadero que no está a su cargo se rechaza con ``fuera_de_alcance``."""
        sur = crear_invernadero("Sur", agronomo=crear_agronomo("otra@infoponia.com"))
        self.assertEqual(self.codigos(datos_de_sistema(sur)), ["fuera_de_alcance"])
        self.assertFalse(SistemaIoT.objects.exists())

    def test_ext_1a_el_gerente_no_registra_en_un_invernadero_con_agronomo_activo(self):
        """IOT-REG-SIS regla «Alcance»: el Gerente lo opera solo donde no hay Agrónomo activo; en los demás, solo consulta."""
        errores = self.codigos(actor=self.gerente)
        self.assertEqual(errores, ["fuera_de_alcance"])
        self.assertFalse(SistemaIoT.objects.exists())

    def test_ext_1a_el_gerente_registra_en_un_invernadero_sin_agronomo(self):
        """IOT-REG-SIS extensión 1a: sin Agrónomo asignado, el Gerente registra."""
        libre = crear_invernadero("Libre")
        sistema, _ = self.registrar(datos_de_sistema(libre), self.gerente)
        self.assertEqual(sistema.invernadero, libre)

    def test_ext_1a_el_gerente_registra_si_el_agronomo_asignado_esta_inactivo(self):
        """IOT-REG-SIS regla «Alcance»: «sin asignar, o con el asignado inactivo»."""
        self.laura.is_active = False
        self.laura.save()
        sistema, _ = self.registrar(actor=self.gerente)
        self.assertEqual(sistema.invernadero, self.norte)

    def test_pre_b_un_invernadero_inactivo_se_rechaza(self):
        """IOT-REG-SIS precondición b y extensión 8b: el invernadero tiene que estar activo (``invernadero_inactivo``)."""
        inactivo = crear_invernadero("Viejo", activo=False, agronomo=self.laura)
        self.assertEqual(self.codigos(datos_de_sistema(inactivo)), ["invernadero_inactivo"])

    def test_pre_b_un_invernadero_que_no_existe_da_404(self):
        """IOT-REG-SIS precondición b: un id que no existe da ``Http404``."""
        with self.assertRaises(Http404):
            self.registrar(datos_de_sistema(self.norte, invernadero_id=999999))

    def test_regla_invernadero_elegible_un_sistema_no_dado_de_baja_por_invernadero(self):
        """IOT-REG-SIS regla «Invernadero elegible» y extensión 8a: con un sistema activo o desconectado, no se registra otro."""
        for estado in ("activo", "desconectado"):
            with self.subTest(estado=estado):
                invernadero = crear_invernadero(f"Con {estado}", agronomo=self.laura)
                fabricas.sistema(invernadero, estado)
                self.assertEqual(self.codigos(datos_de_sistema(invernadero)), ["sistema_existente"])
                self.assertEqual(SistemaIoT.objects.filter(invernadero=invernadero).count(), 1)

    def test_ext_3a_un_invernadero_con_el_sistema_dado_de_baja_registra_uno_nuevo(self):
        """IOT-REG-SIS extensión 3a y regla «Invernadero elegible»: el sistema dado de baja queda como historial y se registra uno
        nuevo, con un nodo central nuevo."""
        anterior = fabricas.sistema(self.norte, "inactivo")
        nuevo, _ = self.registrar()
        self.assertNotEqual(nuevo.pk, anterior.pk)
        self.assertEqual(list(SistemaIoT.objects.filter(invernadero=self.norte).order_by("id")), [anterior, nuevo])
        self.assertEqual((anterior.estado_sistema, nuevo.estado_sistema), ("inactivo", "activo"))
        anterior.refresh_from_db()
        self.assertEqual(anterior.estado_sistema, "inactivo")
        self.assertEqual(NodoCentral.objects.filter(sistema=nuevo).count(), 1)

    def test_ext_8b_el_agronomo_que_deja_de_estar_a_cargo_entre_el_resumen_y_la_confirmacion(self):
        """IOT-REG-SIS extensión 8b y regla «Alcance»: el alcance se verifica DESPUÉS de bloquear. Sin cambios y con el motivo."""
        sistemas.resumen_de_registro(self.laura, self.datos)  # el resumen estaba bien
        self.norte.agronomo = crear_agronomo("nueva@infoponia.com")
        self.norte.save()
        error = error_de(lambda: self.registrar())
        self.assertEqual(codigos_de(error), ["fuera_de_alcance"])
        self.assertIn("Ya no operás el IoT de este invernadero", error.error_dict[NON_FIELD_ERRORS][0].message)
        self.assertFalse(SistemaIoT.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    def test_ext_8b_el_gerente_que_deja_de_poder_operar_porque_se_asigno_un_agronomo(self):
        """IOT-REG-SIS extensión 8b: «si el actor es el Gerente, se asignó un Agrónomo activo»."""
        libre = crear_invernadero("Libre")
        datos = datos_de_sistema(libre)
        sistemas.resumen_de_registro(self.gerente, datos)
        libre.agronomo = self.laura
        libre.save()
        self.assertEqual(self.codigos(datos, actor=self.gerente), ["fuera_de_alcance"])
        self.assertFalse(SistemaIoT.objects.exists())

    def test_ext_8b_el_invernadero_paso_a_inactivo_entre_el_resumen_y_la_confirmacion(self):
        """IOT-REG-SIS extensión 8b: «el invernadero pasó a inactivo»: se rechaza sin crear nada."""
        sistemas.resumen_de_registro(self.laura, self.datos)
        self.norte.estado_invernadero = "inactivo"
        self.norte.save()
        self.assertEqual(self.codigos(), ["invernadero_inactivo"])
        self.assertFalse(SistemaIoT.objects.exists())

    def test_ext_8a_otro_actor_registro_el_sistema_antes(self):
        """IOT-REG-SIS extensión 8a: si el invernadero ya tiene un sistema no dado de baja (otro actor lo registró), no se registra nada."""
        sistemas.resumen_de_registro(self.laura, self.datos)
        fabricas.sistema(self.norte)
        self.assertEqual(self.codigos(), ["sistema_existente"])
        self.assertEqual(SistemaIoT.objects.count(), 1)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    # ---- precondición c: el insumo ----

    def test_pre_c_sin_ningun_insumo_de_repuestos_de_hardware_no_se_registra(self):
        """IOT-REG-SIS precondición c: «Existe al menos un insumo activo de la categoría «Repuestos de hardware»»."""
        from iot.servicios.sistemas import DatosDeSistema

        sin_insumo = DatosDeSistema(
            invernadero_id=self.norte.pk, nombre="Nodo", modelo="Pi", fecha_instalacion=timezone.localdate(), insumo_id=None
        )
        Insumo.objects.all().delete()  # solo datos de esta prueba: el ``setUp`` ya creó uno para ``self.datos``
        self.assertEqual(self.codigos(sin_insumo), ["sin_insumos_de_hardware"])
        self.assertEqual(list(sistemas.insumos_de_hardware()), [])

    def test_pre_c_un_insumo_inactivo_no_cuenta(self):
        """IOT-REG-SIS precondición c: el insumo tiene que estar activo; si el único está inactivo, no hay con qué registrar."""
        Insumo.objects.all().delete()  # solo datos de esta prueba: el ``setUp`` ya creó uno activo para ``self.datos``
        insumo = fabricas.insumo_de_hardware()
        insumo.estado_insumo = "inactivo"
        insumo.save()
        self.assertEqual(self.codigos(datos_de_sistema(self.norte, insumo=insumo)), ["sin_insumos_de_hardware"])

    def test_regla_datos_del_nodo_el_insumo_es_obligatorio(self):
        """IOT-REG-SIS regla «Datos del nodo central»: el insumo es obligatorio (error de campo ``insumo``)."""
        fabricas.insumo_de_hardware()  # hay insumos para elegir, pero no se eligió ninguno
        self.assertEqual(self.codigos(datos_de_sistema(self.norte, insumo_id=None), "insumo"), ["obligatorio"])

    def test_regla_datos_del_nodo_el_insumo_tiene_que_ser_de_repuestos_de_hardware(self):
        """IOT-REG-SIS regla «Datos del nodo central» (regla 8 de IOT-ALT-HDW): un insumo de otra categoría se rechaza."""
        envase = Insumo.objects.create(
            nombre_insumo="Bandeja", tipo_insumo=categoria_del_sistema(ENVASES), unidad_medida_insumo="unidad"
        )
        fabricas.insumo_de_hardware()
        self.assertEqual(self.codigos(datos_de_sistema(self.norte, insumo=envase), "insumo"), ["insumo_invalido"])

    def test_regla_datos_del_nodo_un_insumo_inactivo_se_rechaza_si_hay_otros(self):
        """IOT-REG-SIS regla «Datos del nodo central»: «insumo de ``repuestos_de_hardware`` activo»."""
        inactivo = fabricas.insumo_de_hardware()
        inactivo.estado_insumo = "inactivo"
        inactivo.save()
        fabricas.insumo_de_hardware()
        self.assertEqual(self.codigos(datos_de_sistema(self.norte, insumo=inactivo), "insumo"), ["insumo_invalido"])

    def test_regla_datos_del_nodo_el_insumo_no_necesita_estar_habilitado_ni_tener_stock(self):
        """IOT-REG-SIS regla «Datos del nodo central»: «no hace falta que esté habilitado ni que tenga stock»."""
        sistema, _ = self.registrar()  # el insumo de la fábrica no está habilitado en ningún invernadero ni tiene lotes
        self.assertEqual(NodoCentral.objects.get(sistema=sistema).insumo, Insumo.objects.get())

    # ---- regla «Datos del nodo central» (paso 5 y extensión 6a) ----

    def test_ext_6a_faltan_datos_obligatorios_y_se_marcan_todos_juntos(self):
        """IOT-REG-SIS extensión 6a: «falta un dato obligatorio»: el sistema señala TODOS los datos con error."""
        error = error_de(lambda: self.registrar(datos_de_sistema(self.norte, nombre="  ", modelo="", fecha_instalacion=None)))
        self.assertEqual(sorted(error.error_dict), ["fecha_instalacion", "modelo", "nombre"])
        self.assertEqual(codigos_de(error, "nombre"), ["obligatorio"])
        self.assertEqual(codigos_de(error, "fecha_instalacion"), ["obligatorio"])

    def test_regla_datos_del_nodo_nombre_y_modelo_hasta_60_caracteres(self):
        """IOT-REG-SIS regla «Datos del nodo central»: nombre y modelo, hasta 60 caracteres (se guardan recortados)."""
        self.assertEqual(self.codigos(datos_de_sistema(self.norte, nombre="x" * 61), "nombre"), ["demasiado_largo"])
        self.assertEqual(self.codigos(datos_de_sistema(self.norte, modelo="x" * 61), "modelo"), ["demasiado_largo"])
        sistema, _ = self.registrar(datos_de_sistema(self.norte, nombre="  " + "x" * 60 + "  "))
        self.assertEqual(NodoCentral.objects.get(sistema=sistema).nombre_nodo, "x" * 60)

    def test_regla_datos_del_nodo_el_numero_de_serie_es_opcional_y_no_es_unico(self):
        """IOT-REG-SIS regla «Datos del nodo central»: el número de serie es opcional, hasta 60, y no es único (MD-100)."""
        self.assertEqual(self.codigos(datos_de_sistema(self.norte, numero_serie="s" * 61), "numero_serie"), ["demasiado_largo"])
        otro = crear_invernadero("Otro", agronomo=self.laura)
        primero, _ = self.registrar(datos_de_sistema(self.norte, numero_serie="SN-1"))
        segundo, _ = self.registrar(datos_de_sistema(otro, numero_serie="SN-1"))
        self.assertEqual(NodoCentral.objects.get(sistema=primero).numero_serie, "SN-1")
        self.assertEqual(NodoCentral.objects.get(sistema=segundo).numero_serie, "SN-1")

    def test_regla_datos_del_nodo_la_fecha_de_instalacion_no_es_posterior_a_hoy(self):
        """IOT-REG-SIS extensión 6a y regla «Datos del nodo central» (regla 9 de IOT-ALT-HDW): hoy se acepta; mañana, no."""
        hoy = timezone.localdate()
        self.assertEqual(
            self.codigos(datos_de_sistema(self.norte, fecha_instalacion=hoy + timedelta(days=1)), "fecha_instalacion"), ["fecha_futura"]
        )
        sistema, _ = self.registrar(datos_de_sistema(self.norte, fecha_instalacion=hoy))
        self.assertEqual(NodoCentral.objects.get(sistema=sistema).fecha_instalacion, hoy)

    def test_regla_datos_del_nodo_la_fecha_llega_como_texto_del_formulario(self):
        """IOT-REG-SIS paso 5: el formulario manda la fecha como texto ``AAAA-MM-DD``; un texto que no es fecha es un error del campo."""
        sistema, _ = self.registrar(datos_de_sistema(self.norte, fecha_instalacion="2026-10-01"))
        self.assertEqual(str(NodoCentral.objects.get(sistema=sistema).fecha_instalacion), "2026-10-01")
        self.assertEqual(self.codigos(datos_de_sistema(self.norte, fecha_instalacion="ayer"), "fecha_instalacion"), ["fecha_invalida"])

    def test_regla_datos_del_nodo_el_nodo_no_tiene_sector_ni_identificador(self):
        """IOT-REG-SIS regla «Datos del nodo central» (regla 21 de 8.20) y postcondición b: «sin sector»; el nodo no tiene identificador (MD-100)."""
        sistema, _ = self.registrar()
        nodo = NodoCentral.objects.get(sistema=sistema)
        self.assertIsNone(nodo.sector)
        self.assertIsNone(nodo.identificador_equipo)

    # ---- regla «Rango de temperatura de la solución» (regla 7 de IOT-MOD-SIS; extensión 6a) ----

    def test_regla_rango_es_opcional(self):
        """IOT-REG-SIS regla «Rango de temperatura de la solución»: opcional al registrar; sin él, queda sin rango."""
        sistema, _ = self.registrar()
        self.assertEqual((sistema.temp_solucion_min, sistema.temp_solucion_max), (None, None))

    def test_regla_rango_con_los_dos_valores_se_guarda(self):
        """IOT-REG-SIS postcondición a: «con su rango de temperatura de la solución si se indicó»."""
        sistema, _ = self.registrar(datos_de_sistema(self.norte, temp_min="18", temp_max="24.5"))
        sistema.refresh_from_db()
        self.assertEqual((str(sistema.temp_solucion_min), str(sistema.temp_solucion_max)), ("18.0", "24.5"))

    def test_ext_6a_el_rango_se_indica_completo_o_no_se_indica(self):
        """IOT-REG-SIS extensión 6a y «Cómo se aplica»: «los dos valores o ninguno» (error de ``temp_solucion_max``)."""
        for minimo, maximo in (("18", ""), ("", "24")):
            with self.subTest(minimo=minimo, maximo=maximo):
                self.assertEqual(
                    self.codigos(datos_de_sistema(self.norte, temp_min=minimo, temp_max=maximo), "temp_solucion_max"), ["rango_incompleto"]
                )

    def test_ext_6a_el_minimo_tiene_que_ser_menor_que_el_maximo(self):
        """IOT-REG-SIS extensión 6a: «el mínimo menor que el máximo»; iguales o al revés se rechazan."""
        for minimo, maximo in (("24", "18"), ("20", "20")):
            with self.subTest(minimo=minimo, maximo=maximo):
                self.assertEqual(
                    self.codigos(datos_de_sistema(self.norte, temp_min=minimo, temp_max=maximo), "temp_solucion_max"), ["rango_invertido"]
                )

    def test_regla_rango_con_un_decimal_como_mucho_y_un_numero(self):
        """IOT-REG-SIS «Lista de tecnología y variaciones de datos», 5a: dos números en °C, con hasta un decimal."""
        self.assertEqual(
            self.codigos(datos_de_sistema(self.norte, temp_min="18.55", temp_max="24"), "temp_solucion_min"), ["rango_un_decimal"]
        )
        self.assertEqual(
            self.codigos(datos_de_sistema(self.norte, temp_min="frío", temp_max="24"), "temp_solucion_min"), ["rango_invalido"]
        )

    def test_regla_rango_cabe_en_la_columna(self):
        """D-72 y docs/modelo/iot.md: ``Decimal(4,1)``: un valor que no cabe es un error de campo, nunca un 500."""
        self.assertEqual(
            self.codigos(datos_de_sistema(self.norte, temp_min="10", temp_max="1000"), "temp_solucion_max"), ["rango_invalido"]
        )

    # ---- paso 6: el resumen (no escribe) ----

    def test_paso_6_el_resumen_valida_sin_escribir(self):
        """IOT-REG-SIS paso 6 y «Cómo se aplica»: ``resumen_de_registro`` valida todo y no crea ni audita nada."""
        resumen = sistemas.resumen_de_registro(self.laura, datos_de_sistema(self.norte, temp_min="18", temp_max="24"))
        self.assertEqual(resumen.invernadero, self.norte)
        self.assertEqual((resumen.nombre, resumen.modelo), ("Raspberry del galpón", "Raspberry Pi 4"))
        self.assertEqual((str(resumen.temp_min), str(resumen.temp_max)), ("18.0", "24.0"))
        self.assertFalse(SistemaIoT.objects.exists())
        self.assertFalse(NodoCentral.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    def test_paso_6_el_resumen_rechaza_lo_mismo_que_el_registro(self):
        """IOT-REG-SIS paso 6: el resumen da los mismos errores por campo que el registro (la pantalla vuelve al paso 5)."""
        malos = datos_de_sistema(self.norte, nombre="", temp_min="30", temp_max="20")
        con_resumen = error_de(lambda: sistemas.resumen_de_registro(self.laura, malos))
        con_registro = error_de(lambda: self.registrar(malos))
        self.assertEqual(sorted(con_resumen.error_dict), sorted(con_registro.error_dict))

    def test_ext_6b_el_resumen_avisa_si_el_invernadero_no_tiene_tecnico_activo(self):
        """IOT-REG-SIS extensión 6b: sin Técnico activo, el resumen advierte de la alerta «invernadero sin Técnico activo»."""
        self.assertFalse(sistemas.resumen_de_registro(self.laura, self.datos).sin_tecnico)
        sin = crear_invernadero("Sin tecnico", agronomo=self.laura)
        self.assertTrue(sistemas.resumen_de_registro(self.laura, datos_de_sistema(sin)).sin_tecnico)
        self.tecnico.is_active = False
        self.tecnico.save()
        self.assertTrue(sistemas.resumen_de_registro(self.laura, self.datos).sin_tecnico)

    def test_ext_3a_el_resumen_informa_que_el_invernadero_tuvo_un_sistema_dado_de_baja(self):
        """IOT-REG-SIS extensión 3a: «el sistema anterior queda como historial y se registra uno nuevo, con un nodo central nuevo»."""
        self.assertFalse(sistemas.resumen_de_registro(self.laura, self.datos).tuvo_sistema_dado_de_baja)
        fabricas.sistema(self.norte, "inactivo")
        self.assertTrue(sistemas.resumen_de_registro(self.laura, self.datos).tuvo_sistema_dado_de_baja)

    # ---- postcondiciones ----

    def test_post_a_crea_el_sistema_activo_asociado_al_invernadero(self):
        """IOT-REG-SIS postcondición a: sistema «activo», asociado al invernadero (R068), sin baja."""
        sistema, _ = self.registrar()
        sistema.refresh_from_db()
        self.assertEqual((sistema.invernadero, sistema.estado_sistema, sistema.fecha_baja), (self.norte, "activo", None))

    def test_post_b_crea_el_nodo_central_activo_con_sus_datos(self):
        """IOT-REG-SIS postcondición b: nodo «activo» con nombre, modelo, serie, fecha e insumo (R066 y R072), sin sector, en modo «remoto»."""
        insumo = fabricas.insumo_de_hardware("Raspberry Pi 4 (repuesto)")
        datos = datos_de_sistema(self.norte, insumo=insumo, numero_serie="SN-77", fecha_instalacion="2026-10-15")
        sistema, _ = self.registrar(datos)
        nodo = NodoCentral.objects.get(sistema=sistema)
        self.assertEqual(
            (nodo.clase, nodo.estado_hardware, nodo.nombre_nodo, nodo.modelo_hardware, nodo.numero_serie, nodo.insumo, nodo.modo),
            ("nodo", "activo", "Raspberry del galpón", "Raspberry Pi 4", "SN-77", insumo, "remoto"),
        )
        self.assertEqual(str(nodo.fecha_instalacion), "2026-10-15")
        self.assertIsNone(nodo.ultima_comunicacion)

    def test_post_c_genera_el_token_y_guarda_solo_su_resumen(self):
        """IOT-REG-SIS postcondición c y D-70, punto 3: se devuelve el token y se guarda solo su SHA-256 (64 caracteres)."""
        sistema, token = self.registrar()
        sistema.refresh_from_db()
        self.assertEqual(sistema.token_resumen, resumen_de(token))
        self.assertEqual(len(sistema.token_resumen), 64)
        self.assertNotEqual(sistema.token_resumen, token)
        self.assertIsNotNone(sistema.token_generado_en)

    def test_post_c_el_token_no_esta_en_ninguna_columna_de_la_base(self):
        """IOT-REG-SIS garantía mínima y postcondición c: el token no se guarda en texto plano en ningún campo de los modelos creados."""
        sistema, token = self.registrar()
        nodo = NodoCentral.objects.get(sistema=sistema)
        for objeto in (sistema, nodo):
            for campo in objeto._meta.concrete_fields:
                self.assertNotIn(token, str(getattr(objeto, campo.attname) or ""))

    def test_post_c_dos_registros_dan_tokens_distintos(self):
        """D-70, punto 3: ``secrets.token_urlsafe(32)``: dos tokens nunca coinciden (y el resumen es único en la base)."""
        otro = crear_invernadero("Otro", agronomo=self.laura)
        _, uno = self.registrar()
        _, dos = self.registrar(datos_de_sistema(otro))
        self.assertNotEqual(uno, dos)
        self.assertEqual(SistemaIoT.objects.values("token_resumen").distinct().count(), 2)

    def test_post_d_la_conectividad_nace_sin_senal(self):
        """IOT-REG-SIS postcondición d y regla «Estado inicial, conectividad y modo»: «sin señal» porque todavía no se comunicó."""
        sistema, _ = self.registrar()
        conectividad = sistemas.conectividad(NodoCentral.objects.get(sistema=sistema), timezone.now())
        self.assertEqual((conectividad.estado, conectividad.texto), ("sin_senal", "Todavía no se comunicó"))

    def test_post_e_sin_tecnico_activo_crea_la_alerta_del_gerente(self):
        """IOT-REG-SIS postcondición e y regla «Técnico»: sin Técnico activo, alerta activa «invernadero sin Técnico activo» para el Gerente."""
        sin = crear_invernadero("Sin tecnico", agronomo=self.laura)
        sistemas.registrar_sistema_iot(self.laura, datos_de_sistema(sin))
        alerta = self.alertas_de_tecnico().get()
        self.assertEqual((alerta.invernadero, alerta.para_gerente), (sin, True))

    def test_post_e_con_tecnico_activo_no_crea_la_alerta(self):
        """IOT-REG-SIS postcondición e: con Técnico activo no se genera ninguna alerta."""
        self.registrar()
        self.assertFalse(self.alertas_de_tecnico().exists())

    def test_post_e_con_el_tecnico_inactivo_si_crea_la_alerta(self):
        """IOT-REG-SIS postcondición e: «no tiene un Técnico activo» incluye al asignado que está inactivo."""
        self.tecnico.is_active = False
        self.tecnico.save()
        self.registrar()
        self.assertEqual(self.alertas_de_tecnico().get().invernadero, self.norte)

    def test_post_e_si_la_alerta_ya_existia_no_se_duplica(self):
        """IOT-REG-SIS postcondición e: «y no existía la alerta»: una sola activa por invernadero y tipo."""
        sin = crear_invernadero("Sin tecnico", agronomo=self.laura)
        existente = Alerta.objects.create(
            invernadero=sin, tipo_alerta="sin_tecnico", descripcion_alerta="Invernadero sin Técnico activo", nivel_severidad="advertencia",
            para_gerente=True, clave_estado="",
        )
        sistemas.registrar_sistema_iot(self.laura, datos_de_sistema(sin))
        self.assertEqual(list(self.alertas_de_tecnico()), [existente])
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        self.assertNotIn("maestros.alerta", [a["modelo"] for a in registro.afectados])

    def test_post_e_solo_toca_la_alerta_del_tecnico(self):
        """IOT-REG-SIS postcondición e: registrar el sistema no genera las alertas de los otros roles (D-43: ``roles=["tecnico"]``)."""
        sin = crear_invernadero("Sin nadie", agronomo=self.laura)  # sin capataz ni vendedor
        sistemas.registrar_sistema_iot(self.laura, datos_de_sistema(sin))
        self.assertEqual(list(Alerta.objects.values_list("tipo_alerta", flat=True)), ["sin_tecnico"])

    def test_post_f_audita_con_el_sistema_el_nodo_y_la_alerta_y_sin_el_token(self):
        """IOT-REG-SIS postcondición f y «Auditoría» (D-36): ``alta_sistema_iot`` con el sistema, el nodo y la alerta; datos: invernadero,
        nodo y rango. Nunca el token ni su resumen."""
        sin = crear_invernadero("Sin tecnico", agronomo=self.laura)
        sistema, token = sistemas.registrar_sistema_iot(self.laura, datos_de_sistema(sin, temp_min="18", temp_max="24"))
        nodo = NodoCentral.objects.get(sistema=sistema)
        alerta = self.alertas_de_tecnico().get()
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.laura.pk, "agronomo"))
        self.assertEqual(
            [(a["modelo"], a["id"]) for a in registro.afectados],
            [("iot.sistemaiot", sistema.pk), ("iot.nodocentral", nodo.pk), ("maestros.alerta", alerta.pk)],
        )
        datos = registro.detalle["datos"]
        self.assertEqual(datos["invernadero"], {"id": sin.pk, "texto": "Sin tecnico"})
        self.assertEqual(datos["nodo"], {"id": nodo.pk, "texto": "Raspberry del galpón"})
        self.assertIn("18.0", json.dumps(datos["rango_de_la_solucion"]))
        self.assertEqual(set(registro.detalle), {"datos"})

    def test_post_f_el_token_y_su_resumen_no_estan_en_ningun_registro_de_auditoria(self):
        """IOT-REG-SIS garantía mínima y postcondición f: el token no aparece en los logs de auditoría (ni su resumen)."""
        sistema, token = self.registrar()
        todo = json.dumps(
            [{"detalle": r.detalle, "afectados": r.afectados} for r in RegistroAuditoria.objects.all()], ensure_ascii=False
        )
        self.assertNotIn(token, todo)
        self.assertNotIn(sistema.token_resumen, todo)

    def test_post_f_el_registro_se_puede_leer_en_la_pantalla_de_auditoria(self):
        """D-36: los datos del registro tienen su nombre visible (``ETIQUETAS``) y el Gerente lo ve (acción de negocio)."""
        self.registrar(datos_de_sistema(self.norte, temp_min="18", temp_max="24"))
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        etiquetas = dict(registro.filas_de_datos())
        for etiqueta in ("Invernadero", "Nodo central", "Rango de temperatura de la solución"):
            self.assertIn(etiqueta, etiquetas)
        self.assertIn(registro, RegistroAuditoria.objects.visibles_para(self.gerente))

    def test_post_f_un_registro_rechazado_no_audita(self):
        """IOT-REG-SIS garantía mínima y D-22: no queda un registro de una operación que no se hizo."""
        self.codigos(datos_de_sistema(self.norte, nombre=""))
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    def test_garantia_el_registro_es_atomico(self):
        """IOT-REG-SIS garantía mínima: si algo falla a mitad, no queda ningún sistema, nodo, token, alerta ni log parcial."""
        sin = crear_invernadero("Sin tecnico", agronomo=self.laura)
        with mock.patch("maestros.servicios.alertas.sincronizar_alertas_de_personal", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                sistemas.registrar_sistema_iot(self.laura, datos_de_sistema(sin))
        self.assertFalse(SistemaIoT.objects.exists())
        self.assertFalse(NodoCentral.objects.exists())
        self.assertFalse(Alerta.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    # ---- paso 2: qué invernaderos se ofrecen ----

    def test_paso_2_el_agronomo_ve_sus_invernaderos_activos_sin_sistema_con_su_tecnico(self):
        """IOT-REG-SIS paso 2: los invernaderos activos a su cargo sin sistema IoT, cada uno con su Técnico o la marca «sin Técnico»."""
        sin_tecnico = crear_invernadero("Este", agronomo=self.laura)
        crear_invernadero("Ajeno", agronomo=crear_agronomo("otra@infoponia.com"))
        crear_invernadero("Inactivo", activo=False, agronomo=self.laura)
        con_sistema = crear_invernadero("Con sistema", agronomo=self.laura)
        fabricas.sistema(con_sistema)
        elegibles = sistemas.invernaderos_para_registrar(self.laura)
        self.assertEqual([e.invernadero for e in elegibles], [sin_tecnico, self.norte])  # por nombre: Este, Norte
        self.assertEqual([e.tecnico for e in elegibles], [None, self.tecnico])

    def test_paso_2_un_sistema_dado_de_baja_no_saca_al_invernadero_de_la_lista(self):
        """IOT-REG-SIS paso 2 y extensión 3a: «o cuyo sistema IoT está dado de baja»; se marca para avisar que tuvo uno."""
        fabricas.sistema(self.norte, "inactivo")
        (elegible,) = sistemas.invernaderos_para_registrar(self.laura)
        self.assertEqual((elegible.invernadero, elegible.tuvo_sistema), (self.norte, True))

    def test_ext_1a_el_gerente_ve_solo_los_invernaderos_sin_agronomo_activo(self):
        """IOT-REG-SIS extensión 1a: al Gerente se le ofrecen los invernaderos activos sin un Agrónomo activo."""
        libre = crear_invernadero("Libre")
        de_baja = crear_agronomo("baja@infoponia.com")
        de_baja.is_active = False
        de_baja.save()
        inactivo_asignado = crear_invernadero("Con agronomo inactivo", agronomo=de_baja)
        self.assertEqual(
            [e.invernadero for e in sistemas.invernaderos_para_registrar(self.gerente)], [inactivo_asignado, libre]
        )

    def test_paso_2_un_tecnico_inactivo_se_marca_como_sin_tecnico(self):
        """IOT-REG-SIS paso 2 y extensión 6b: el Técnico que se muestra es el activo; uno inactivo es «sin Técnico»."""
        self.tecnico.is_active = False
        self.tecnico.save()
        (elegible,) = sistemas.invernaderos_para_registrar(self.laura)
        self.assertIsNone(elegible.tecnico)

    def test_paso_2_otros_roles_no_ven_nada(self):
        """IOT-REG-SIS precondición a: los demás roles reciben 403."""
        with self.assertRaises(PermissionDenied):
            sistemas.invernaderos_para_registrar(crear_capataz())

    # ---- lectura: sistema del invernadero, conectividad y botones ----

    def test_cns_el_sistema_del_invernadero_es_el_que_no_esta_dado_de_baja(self):
        """«Para los cinco», «Elección del invernadero»: el sistema vigente (activo o desconectado), o ``None``."""
        self.assertIsNone(sistemas.sistema_del_invernadero(self.laura, self.norte.pk))
        fabricas.sistema(self.norte, "inactivo")
        self.assertIsNone(sistemas.sistema_del_invernadero(self.laura, self.norte.pk))
        vigente = fabricas.sistema(self.norte, "desconectado")
        self.assertEqual(sistemas.sistema_del_invernadero(self.laura, self.norte.pk), vigente)

    def test_cns_el_invernadero_fuera_del_alcance_de_consulta_da_404(self):
        """«Para los cinco», «Elección del invernadero»: con un invernadero fuera del alcance, 404; el Gerente consulta todos."""
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo("otra@infoponia.com"))
        with self.assertRaises(Http404):
            sistemas.sistema_del_invernadero(self.laura, ajeno.pk)
        self.assertIsNone(sistemas.sistema_del_invernadero(self.gerente, ajeno.pk))
        with self.assertRaises(Http404):
            sistemas.sistema_del_invernadero(self.gerente, 999999)
        with self.assertRaises(PermissionDenied):
            sistemas.sistema_del_invernadero(crear_capataz(), self.norte.pk)

    def test_conectividad_en_linea_si_la_ultima_comunicacion_es_mas_reciente_que_el_plazo(self):
        """«Para los cinco», «Conectividad»; regla 3 de IOT-ACT-SIS: ``en_linea`` si es más reciente que ``minutos_sin_comunicacion`` (3 por defecto)."""
        sistema = fabricas.sistema(self.norte)
        nodo = NodoCentral.objects.get(sistema=sistema)
        ahora = timezone.now()
        nodo.ultima_comunicacion = ahora - timedelta(minutes=2)
        self.assertEqual(sistemas.conectividad(nodo, ahora).estado, "en_linea")
        nodo.ultima_comunicacion = ahora - timedelta(minutes=3)  # justo en el plazo: ya no es «más reciente»
        self.assertEqual(sistemas.conectividad(nodo, ahora).estado, "sin_senal")
        nodo.ultima_comunicacion = ahora - timedelta(hours=1)
        self.assertEqual(sistemas.conectividad(nodo, ahora).estado, "sin_senal")

    def test_conectividad_usa_el_parametro_de_la_configuracion_operativa(self):
        """«Para los cinco», «Conectividad»: el plazo es el parámetro ``minutos_sin_comunicacion`` (MD-112), leído en cada uso."""
        from maestros.models import ConfiguracionOperativa

        ConfiguracionOperativa.objects.filter(singleton=1).update(minutos_sin_comunicacion=10)
        nodo = NodoCentral.objects.get(sistema=fabricas.sistema(self.norte))
        ahora = timezone.now()
        nodo.ultima_comunicacion = ahora - timedelta(minutes=9)
        self.assertEqual(sistemas.conectividad(nodo, ahora).estado, "en_linea")

    def test_conectividad_nunca_comunicada_es_sin_senal_con_su_texto(self):
        """«Para los cinco», «Conectividad»: con ``ultima_comunicacion`` nula, ``sin_senal`` y «Todavía no se comunicó»."""
        nodo = NodoCentral.objects.get(sistema=fabricas.sistema(self.norte))
        conectividad = sistemas.conectividad(nodo, timezone.now())
        self.assertEqual((conectividad.estado, conectividad.texto), ("sin_senal", "Todavía no se comunicó"))

    def test_acciones_permitidas_ningun_boton_lleva_a_un_403(self):
        """D-30 y IOT-MOD-SIS regla 1: quien opera el IoT del invernadero modifica y regenera el token (y, desde IOT-06, desactiva el sistema activo y lo da de baja); quien solo consulta, nada."""
        sistema = fabricas.sistema(self.norte)
        esperado = frozenset({sistemas.ACCION_MODIFICAR, sistemas.ACCION_REGENERAR_TOKEN, sistemas.ACCION_DESACTIVAR, sistemas.ACCION_BAJA})
        self.assertEqual(sistemas.acciones_permitidas(self.laura, sistema), esperado)
        self.assertEqual(sistemas.acciones_permitidas(self.gerente, sistema), frozenset())  # hay Agrónomo activo: solo consulta
        libre = fabricas.sistema(crear_invernadero("Libre"))
        self.assertEqual(sistemas.acciones_permitidas(self.gerente, libre), esperado)
        self.assertEqual(sistemas.acciones_permitidas(crear_capataz(), sistema), frozenset())

    def test_acciones_permitidas_un_sistema_dado_de_baja_no_tiene_acciones(self):
        """IOT-MOD-SIS regla 6: un sistema IoT dado de baja no se modifica (ni se le regenera el token): sin botones."""
        baja = fabricas.sistema(self.norte, "inactivo")
        self.assertEqual(sistemas.acciones_permitidas(self.laura, baja), frozenset())

    def test_acciones_permitidas_un_sistema_desconectado_se_modifica(self):
        """IOT-MOD-SIS precondición b: el sistema está «activo» o «desconectado»."""
        desconectado = fabricas.sistema(self.norte, "desconectado")
        self.assertIn(sistemas.ACCION_MODIFICAR, sistemas.acciones_permitidas(self.laura, desconectado))
