# Apoyo común de las pruebas de CMP-AJT-STK (INV-02, paso 6; docs/casos_de_uso/inventario/ajuste_de_stock.md). NO es un archivo de pruebas:
# lo importan test_cmp_ajt_stk_recuento.py, _motivos.py, _validaciones.py, _alertas.py, _concurrencia.py y _semilla_inactiva.py.
#
# CONTRATO del servicio (inventario/servicios/ajustes.py), tomado del módulo dentro de cada prueba:
#
#   situacion_del_insumo(actor, invernadero_id, insumo_id) -> Situacion
#       Pasos 4 a 6 del CU, para la pantalla: ``iin`` (la existencia), ``insumo``, ``stock_actual``, ``lotes`` (lista de
#       ``LoteConEstado`` de ``insumos_invernadero``, con stock primero, después los agotados y por último el faltante sin lote),
#       ``faltante`` (el lote del faltante o ``None``), ``precio``, ``controla_vencimiento`` y ``motivos`` (``MOTIVOS``).
#   calcular_ajuste(actor, invernadero_id, insumo_id, motivo, entrada) -> Resumen        (NO escribe, no bloquea, no audita)
#       Valida y calcula. ``Resumen``: ``lotes`` (lista de ``CambioDeLote(lote, registrada, contada, diferencia)``: los lotes que
#       cambian), ``lotes_nuevos`` (``LoteNuevo(cantidad, vencimiento)``), ``faltante_a_cero`` (lo que faltaba, en positivo, o 0),
#       ``stock_antes``, ``stock_despues``, ``diferencia`` (stock después − antes), ``valor`` (con signo, en pesos con 2 decimales:
#       diferencia × precio de referencia), ``con_valor`` (False en la corrección entre lotes), ``advertencia`` (``None`` o
#       ``Advertencia(ordenes, stock_vigente, reservado)``: la extensión 12b) y ``huella`` (el estado que usó).
#   confirmar_ajuste(actor, invernadero_id, insumo_id, motivo, entrada, huella) -> Resultado
#       Bloquea (invernadero → existencia → lotes), RECALCULA, compara la huella (``AjusteDesactualizado`` si cambió: extensión 14a, sin
#       cambiar nada) y escribe todo en una transacción. ``Resultado``: ``resumen``, ``movimientos``, ``lotes_nuevos`` (``LoteInsumo``),
#       ``stock_actual``, ``alertas_creadas``, ``alertas_resueltas`` e ``inconsistente`` («resuelta», «activa» o ``None``; paso 15).
#   ``AjusteDesactualizado.vigente``: ``{"lotes": {lote_id: disponible}, "reservado": Decimal}`` con lo que hay ahora.
#
# MOTIVOS (códigos) y ``entrada`` de cada uno (``descripcion`` es opcional salvo en «otro»; las cantidades pueden ser ``Decimal`` o texto):
#   recuento_fisico         {"contados": {lote_id: cantidad}, "nuevos": [{"cantidad", "vencimiento"}]}  (solo los lotes que difieren)
#   carga_inicial           {"cantidad", "vencimiento"}
#   rotura_o_perdida        {"lote_id", "cantidad"}
#   vencimiento             {"lotes": [lote_id, ...]}
#   correccion_entre_lotes  {"origen_id", "destino_id", "cantidad"}   (el destino puede ser el faltante sin lote)
#   otro                    {"sentido": "suma" | "resta", "descripcion", y los datos de carga_inicial (suma) o de rotura (resta)}
# Los errores de datos son un ``ValidationError`` con un error por campo: ``motivo``, ``cantidad``, ``vencimiento``, ``lote``,
# ``lotes``, ``origen``, ``destino``, ``sentido``, ``descripcion``, ``contado_<lote_id>``, ``nuevo_<n>_cantidad`` y
# ``nuevo_<n>_vencimiento`` (n desde 0), o general (``__all__``).

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    insumo,
    perezoso,
    tipo_de_insumo,
    verificar_invariantes,
)
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_invernadero_con_geografia_propia

ajustes = perezoso("inventario.servicios.ajustes")
D = Decimal

RECUENTO = "recuento_fisico"
CARGA_INICIAL = "carga_inicial"
ROTURA = "rotura_o_perdida"
VENCIMIENTO = "vencimiento"
CORRECCION = "correccion_entre_lotes"
OTRO = "otro"


class BaseDeAjustes(ConDatosDeInventario):
    """Mixin: arma un Agrónomo con un invernadero y un insumo con vencimiento (L, precio de referencia 100) habilitado con mínimo 0."""

    def preparar(self, geografia_propia=False):
        crear = crear_invernadero_con_geografia_propia if geografia_propia else crear_invernadero
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Gómez")
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.invernadero = crear("Invernadero Norte", agronomo=self.agronomo)
        self.tipo = tipo_de_insumo("Nutrientes")
        self.insumo = insumo("Nutriente A", tipo=self.tipo, unidad="l", controla_vencimiento=True)
        self.iin = existencia(self.insumo, self.invernadero, minimo=0, precio="100")
        self.hoy = timezone.localdate()
        self.vence = self.hoy + timedelta(days=60)
        self.vencido = self.hoy - timedelta(days=3)

    def calcular(self, motivo, entrada, actor=None, iin=None):
        iin = iin or self.iin
        return ajustes.calcular_ajuste(actor or self.agronomo, iin.invernadero_id, iin.insumo_id, motivo, entrada)

    def confirmar(self, motivo, entrada, huella=None, actor=None, iin=None):
        iin = iin or self.iin
        if huella is None:
            huella = self.calcular(motivo, entrada, actor, iin).huella
        return ajustes.confirmar_ajuste(actor or self.agronomo, iin.invernadero_id, iin.insumo_id, motivo, entrada, huella)

    def disponible(self, un_lote):
        un_lote.refresh_from_db()
        return un_lote.cantidad_disponible

    def invariantes(self, iin=None):
        verificar_invariantes(iin or self.iin)
