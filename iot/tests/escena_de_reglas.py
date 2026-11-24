# Escena compartida por las pruebas de las reglas de actuación (IOT-06): un invernadero «Norte» con su Agrónomo, su sistema IoT, dos sensores que admiten reglas, uno que no
# (nivel de la solución) y dos actuadores (los tipos iniciales «Ventilador» y «Ventana»). Las pruebas parten de acá y cambian lo que quieren probar.
# ``DatosDeRegla`` y los servicios se toman dentro de cada función: mientras no existen, falla cada prueba y no se cae la importación de todo el archivo.

from datetime import datetime, timezone as zona

from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import TipoActuador
from iot.tests import fabricas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

reglas = perezoso("iot.servicios.reglas")
AHORA = datetime(2026, 11, 23, 15, 0, tzinfo=zona.utc)


class ConEscenaDeReglas(fabricas.ConCatalogoIot):
    """Mixin: ``class MisTests(ConEscenaDeReglas, TestCase)``. Arma la escena en ``setUp`` (la clase puede ampliarla con ``super().setUp()``)."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        self.temp = fabricas.sensor(self.sistema, "norte/temp", "temperatura")
        self.hum = fabricas.sensor(self.sistema, "norte/hum", "humedad")
        self.nivel = fabricas.sensor(self.sistema, "norte/nivel", "nivel_solucion")
        # Los tipos iniciales de la migración 0003 (Ventilador: Encender, Apagar y Fijar velocidad; Ventana: Abrir, Cerrar y Fijar posición 0 a 100 %), con 60 s entre comandos.
        self.tipo_ventilador = TipoActuador.objects.get(nombre_actuador="Ventilador")
        self.tipo_ventana = TipoActuador.objects.get(nombre_actuador="Ventana")
        self.ventilador = fabricas.actuador(self.sistema, self.tipo_ventilador, "norte/ventilador")
        self.ventana = fabricas.actuador(self.sistema, self.tipo_ventana, "norte/ventana")
        self.encender = self.tipo_ventilador.acciones.get(nombre_accion="Encender")
        self.apagar = self.tipo_ventilador.acciones.get(nombre_accion="Apagar")
        self.fijar = self.tipo_ventana.acciones.get(nombre_accion="Fijar posición")

    def datos(self, sensor=None, actuador=None, condicion="supera_maximo", accion=None, valor=None):
        """Los datos del formulario de una regla (``DatosDeRegla``); por defecto, «temperatura supera el máximo → Ventilador: Encender»."""
        actuador = actuador or self.ventilador
        accion = accion or (self.encender if actuador.pk == self.ventilador.pk else self.fijar)
        return reglas.DatosDeRegla(sensor_id=(sensor or self.temp).pk, actuador_id=actuador.pk, condicion=condicion, accion_id=accion.pk, valor=valor)

    def alta(self, actor=None, **datos):
        """Da de alta una regla con el servicio, como el Agrónomo (o ``actor``)."""
        return reglas.alta_regla(actor or self.laura, self.norte.pk, self.datos(**datos), AHORA)
