# Pruebas de concurrencia de las reglas de actuación y del ciclo de vida del IoT (IOT-06, paso 6; docs/casos_de_uso/iot/entregar_informacion.md, «Bloqueos y concurrencia» y «Reglas de
# actuación»; sistema_iot.md y hardware.md, «Cómo se aplica»; docs/patrones/bloqueos.md; D-78, puntos 8, 9 y 11; D-82): una regla que dispara y un comando manual a la vez sobre el mismo
# actuador; desactivar el sistema mientras llega una lectura que dispara una regla (o se emite y se cancela, o no se emite: nunca un pendiente en un sistema desconectado); y dar de baja un
# equipo mientras se da de alta una regla que lo usa (nunca una regla activa sobre un equipo dado de baja). Dos hilos, dos conexiones, el orden fijado con ``primera``
# (core/tests/concurrencia.py). ``TransactionTestCase``: su ``flush`` vacía todas las tablas al terminar, así que cada prueba vuelve a asegurar los datos en ``setUp``
# (docs/patrones/datos_de_migracion.md) y limpia la caché.

from datetime import datetime, timedelta, timezone as zona
from decimal import Decimal

from django.core.cache import cache
from django.test import TransactionTestCase, tag

from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import variedad_con_semilla, variedades_presentes_de_prueba
from iot.api.traduccion import LecturaRecibida
from iot.models import Comando, NodoCentral, ReglaActuacion, SistemaIoT, TipoActuador
from iot.servicios import comandos, hardware, lecturas, reglas, sistemas
from iot.tests import fabricas
from maestros.tests.fabricas import asegurar_datos_de_maestros, crear_agronomo, crear_invernadero_con_geografia_propia

AHORA = datetime(2026, 11, 23, 15, 0, 0, tzinfo=zona.utc)


@tag("concurrencia")
class ReglasConcurrenciaTests(fabricas.ConCatalogoIot, TransactionTestCase):
    """Reglas, comandos manuales, desactivación del sistema y baja de equipos a la vez."""

    def setUp(self):
        cache.clear()
        fabricas.asegurar_datos_de_iot()
        asegurar_datos_de_maestros()
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero_con_geografia_propia("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        NodoCentral.objects.filter(sistema=self.sistema).update(ultima_comunicacion=AHORA)
        self.temp = fabricas.sensor(self.sistema, "norte/temperatura")
        self.tipo = TipoActuador.objects.get(nombre_actuador="Ventilador")
        self.ventilador = fabricas.actuador(self.sistema, self.tipo, "norte/ventilador", ultimo_mensaje_en=AHORA)
        self.encender = self.tipo.acciones.get(nombre_accion="Encender")
        self.apagar = self.tipo.acciones.get(nombre_accion="Apagar")
        # Umbral efectivo de «Crespa» (temperatura 18 a 24 °C) y 3 lecturas de confirmación (por defecto).
        self.enterContext(variedades_presentes_de_prueba({self.norte.pk: {variedad_con_semilla(nombre="Crespa").pk}}))

    # ---- ayudas ----

    def regla_a_punto_de_disparar(self):
        """Una regla «temperatura supera el máximo → Ventilador: Encender» con 2 de las 3 lecturas de confirmación: la próxima lectura alta la dispara."""
        return fabricas.regla(self.temp, self.ventilador, self.encender, "supera_maximo", ultima_evaluacion="no_cumplida", contador_confirmacion=2)

    def lectura_alta(self):
        """Lo que hace el nodo: UNA lectura de 30 °C (supera el máximo de 24 °C), medida 5 s antes de ``AHORA``."""
        contexto = lecturas.contexto_del_mensaje(self.sistema, AHORA)
        recibida = LecturaRecibida(1, self.temp.identificador_equipo, self.temp.identificador_equipo, Decimal("30"), (AHORA - timedelta(seconds=5)).isoformat())
        return lambda: lecturas.registrar_lectura(contexto, recibida, AHORA)

    def emitir_manual(self):
        return lambda: comandos.emitir_comando(self.laura, self.ventilador.pk, comandos.DatosDeComando(accion_id=self.apagar.pk), AHORA)

    def pendientes(self):
        return Comando.objects.filter(actuador=self.ventilador, estado_comando="pendiente")

    # ---- una regla que dispara y un comando manual a la vez ----

    def test_regla_8_la_regla_gana_y_el_comando_manual_recibe_comando_pendiente(self):
        """«Actuador ocupado» y «Bloqueos y concurrencia»: la lectura emite el comando de la regla; el comando manual que llega a la vez recibe ``comando_pendiente``. Nunca dos pendientes."""
        regla = self.regla_a_punto_de_disparar()
        resultados = correr_a_la_vez(self.lectura_alta(), self.emitir_manual(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["comando_pendiente"])
        regla.refresh_from_db()
        (pendiente,) = self.pendientes()
        self.assertEqual(pendiente.regla_id, regla.pk)
        self.assertEqual((regla.ultima_evaluacion, regla.contador_confirmacion), ("cumplida", 0))

    def test_regla_8_el_manual_gana_y_la_regla_queda_ocupada_para_intentar_con_la_lectura_siguiente(self):
        """Extensión 6a.1a: si el comando manual llegó primero, la regla no emite; queda «no cumplida» con el contador EN la confirmación (3) y la lectura se acepta. Un solo pendiente."""
        regla = self.regla_a_punto_de_disparar()
        resultados = correr_a_la_vez(self.lectura_alta(), self.emitir_manual(), primera="b")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        regla.refresh_from_db()
        (pendiente,) = self.pendientes()
        self.assertIsNone(pendiente.regla_id)
        self.assertEqual((regla.ultima_evaluacion, regla.contador_confirmacion), ("no_cumplida", 3))

    # ---- desactivar el sistema mientras llega una lectura que dispara una regla ----

    def test_post_b_si_desactiva_primero_la_lectura_se_rechaza_y_no_se_emite_nada(self):
        """Desactivar primero: la lectura vuelve a mirar el estado del sistema después de bloquear (paso 1) y se rechaza con ``sistema_desconectado``: ningún comando."""
        self.regla_a_punto_de_disparar()
        desactivar = lambda: sistemas.desactivar_sistema_iot(self.laura, self.sistema.pk, AHORA)  # noqa: E731
        resultados = correr_a_la_vez(desactivar, self.lectura_alta(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(resultados["b"].resultado, "rechazada")
        self.assertEqual(resultados["b"].motivo, "sistema_desconectado")
        self.assertEqual(SistemaIoT.objects.get(pk=self.sistema.pk).estado_sistema, "desconectado")
        self.assertFalse(Comando.objects.exists())

    def test_post_b_si_llega_primero_la_lectura_el_comando_emitido_se_cancela(self):
        """La lectura emite el pendiente y la desactivación, que esperaba, lo cancela: el sistema queda desconectado y NINGÚN pendiente."""
        self.regla_a_punto_de_disparar()
        desactivar = lambda: sistemas.desactivar_sistema_iot(self.laura, self.sistema.pk, AHORA)  # noqa: E731
        resultados = correr_a_la_vez(self.lectura_alta(), desactivar, primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        (comando,) = Comando.objects.all()
        self.assertEqual(comando.estado_comando, "cancelado")
        self.assertEqual(SistemaIoT.objects.get(pk=self.sistema.pk).estado_sistema, "desconectado")
        self.assertFalse(self.pendientes().exists())

    # ---- dar de baja un equipo mientras se da de alta una regla que lo usa ----

    def alta_de_regla(self):
        datos = reglas.DatosDeRegla(sensor_id=self.temp.pk, actuador_id=self.ventilador.pk, condicion="supera_maximo", accion_id=self.encender.pk)
        return lambda: reglas.alta_regla(self.laura, self.norte.pk, datos, AHORA)

    def test_regla_2_si_la_baja_llega_primero_la_regla_no_se_crea(self):
        """IOT-ALT-RGL regla 2 e IOT-BAJ-HDW precondición e: la baja del actuador gana; el alta, que esperaba, ve el actuador inactivo y recibe ``actuador_no_disponible``. Ninguna regla."""
        baja = lambda: hardware.baja_hardware(self.laura, self.ventilador.pk, AHORA)  # noqa: E731
        resultados = correr_a_la_vez(baja, self.alta_de_regla(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["actuador_no_disponible"])
        self.ventilador.refresh_from_db()
        self.assertEqual(self.ventilador.estado_hardware, "inactivo")
        self.assertFalse(ReglaActuacion.objects.exists())

    def test_regla_2_si_el_alta_llega_primero_la_baja_se_rechaza_porque_una_regla_lo_usa(self):
        """El alta gana; la baja, que esperaba, ve la regla activa y recibe ``reglas_activas``. Nunca una regla activa sobre un equipo dado de baja."""
        alta_primero = correr_a_la_vez(self.alta_de_regla(), lambda: hardware.baja_hardware(self.laura, self.ventilador.pk, AHORA), primera="a")
        exitos, rechazos, otros = separar(alta_primero)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["reglas_activas"])
        self.ventilador.refresh_from_db()
        self.assertEqual(self.ventilador.estado_hardware, "activo")
        self.assertEqual(ReglaActuacion.objects.filter(estado_regla="activa").count(), 1)

    def test_regla_2_la_baja_del_sensor_y_el_alta_de_una_regla_con_ese_sensor_tampoco_se_cruzan(self):
        """Lo mismo con el sensor: la baja gana y el alta recibe ``sensor_no_disponible``."""
        baja = lambda: hardware.baja_hardware(self.laura, self.temp.pk, AHORA)  # noqa: E731
        resultados = correr_a_la_vez(baja, self.alta_de_regla(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["sensor_no_disponible"])
        self.assertFalse(ReglaActuacion.objects.exists())
