# Pruebas de las restricciones de la base de los cinco modelos de `inventario` (INV-01, paso 1): una por restricción, con el caso
# que la viola y el que no. Fuente: docs/modelo/inventario.md (fichas y «Restricciones de la base», D-36) y D-52.

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from contabilidad.models import OrigenDocumento
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo, TipoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    categoria_del_sistema,
    existencia,
    insumo,
    lote,
    movimiento,
    origen_falso,
    tipo_de_insumo,
)
from maestros.tests.fabricas import crear_invernadero

Mov = MovimientoInsumo.TipoMovimiento
Motivo = MovimientoInsumo.MotivoAjuste


class RestriccionesTests(ConDatosDeInventario, TestCase):
    """Base de las pruebas: ``viola`` exige que la base rechace la operación sin romper la transacción de la prueba."""

    def viola(self, operacion):
        with self.assertRaises(IntegrityError), transaction.atomic():
            operacion()


class TipoInsumoRestriccionesTests(RestriccionesTests):
    """Restricciones de la ficha de TipoInsumo (regla 1 de 8.23 y reglas 2 y 3 de CMP-ALT-TIN)."""

    def test_regla_cmp_alt_tin_2_nombre_unico_sin_distinguir_mayusculas_viola(self):
        """CMP-ALT-TIN regla 2: otro nombre igual con otras mayúsculas lo rechaza la base (también contra una del sistema)."""
        tipo_de_insumo("Limpieza")
        self.viola(lambda: tipo_de_insumo("lIMPIEZA"))
        self.viola(lambda: tipo_de_insumo("ENVASES"))

    def test_regla_cmp_alt_tin_2_nombre_unico_no_viola_con_otro_nombre(self):
        """CMP-ALT-TIN regla 2: dos nombres distintos conviven."""
        tipo_de_insumo("Limpieza")
        self.assertEqual(tipo_de_insumo("Nutrientes").pk is not None, True)

    def test_regla_8_23_1_codigo_unico_viola(self):
        """Regla 1 de 8.23: el `codigo` es único (no puede haber dos con el mismo)."""
        self.viola(
            lambda: TipoInsumo.objects.create(
                nombre_tipo_insumo="Otra", consumo_directo="no_admite", es_del_sistema=True, codigo="envases"
            )
        )

    def test_regla_8_23_1_codigo_nulo_repetido_no_viola(self):
        """Regla 1 de 8.23: las categorías comunes tienen `codigo` nulo y pueden ser muchas."""
        tipo_de_insumo("A")
        tipo_de_insumo("B")
        self.assertEqual(TipoInsumo.objects.filter(codigo__isnull=True).count(), 2)

    def test_regla_8_23_1_estado_fuera_de_dominio_viola(self):
        """D-36: el dominio de `estado_tipo_insumo`."""
        self.viola(
            lambda: TipoInsumo.objects.create(
                nombre_tipo_insumo="X", consumo_directo="como_gasto", estado_tipo_insumo="suspendido"
            )
        )

    def test_regla_8_23_1_estado_inactivo_no_viola(self):
        """D-36: «inactivo» está en el dominio."""
        self.assertEqual(tipo_de_insumo("X", activo=False).estado_tipo_insumo, "inactivo")

    def test_regla_8_23_1_consumo_directo_fuera_de_dominio_viola(self):
        """D-36: el dominio de `consumo_directo`."""
        self.viola(lambda: tipo_de_insumo("X", consumo="siempre"))

    def test_regla_8_23_1_consumo_directo_en_cada_valor_no_viola(self):
        """D-36: los tres valores del dominio."""
        for i, consumo in enumerate(["no_admite", "como_gasto", "como_costo_de_los_lotes"]):
            self.assertIsNotNone(tipo_de_insumo(f"C{i}", consumo=consumo).pk)

    def test_regla_8_23_1_del_sistema_con_consumo_directo_viola(self):
        """Regla 1 de 8.23: una categoría del sistema no admite consumo directo."""
        self.viola(
            lambda: TipoInsumo.objects.filter(codigo="envases").update(consumo_directo="como_gasto"),
        )

    def test_regla_8_23_1_del_sistema_sin_codigo_viola(self):
        """Regla 1 de 8.23: `es_del_sistema` implica `codigo` no nulo."""
        self.viola(
            lambda: TipoInsumo.objects.create(
                nombre_tipo_insumo="Semillas", consumo_directo="no_admite", es_del_sistema=True
            )
        )

    def test_regla_8_23_1_codigo_en_una_comun_viola(self):
        """Modelo: el `codigo` es nulo si no es del sistema."""
        self.viola(
            lambda: TipoInsumo.objects.create(
                nombre_tipo_insumo="Común", consumo_directo="como_gasto", codigo="comun"
            )
        )

    def test_regla_cmp_mod_tin_3_del_sistema_no_se_da_de_baja_viola(self):
        """CMP-MOD-TIN regla 3 (respaldo de la base, decidido en INV-01): una del sistema no pasa a inactiva."""
        self.viola(lambda: TipoInsumo.objects.filter(codigo="semillas").update(estado_tipo_insumo="inactivo"))

    def test_regla_cmp_mod_tin_3_del_sistema_no_se_renombra_viola(self):
        """CMP-MOD-TIN regla 3: el nombre de una del sistema no cambia, ni a otra capitalización."""
        self.viola(lambda: TipoInsumo.objects.filter(codigo="semillas").update(nombre_tipo_insumo="Semillitas"))
        self.viola(lambda: TipoInsumo.objects.filter(codigo="semillas").update(nombre_tipo_insumo="envases"))

    def test_regla_cmp_mod_tin_3_del_sistema_sin_cambios_no_viola(self):
        """CMP-MOD-TIN regla 3: guardarla igual (por ejemplo, reescribir el nombre actual) no viola nada."""
        categoria = categoria_del_sistema("infraestructura")
        TipoInsumo.objects.filter(pk=categoria.pk).update(nombre_tipo_insumo="Infraestructura")
        categoria.refresh_from_db()
        self.assertEqual(categoria.nombre_tipo_insumo, "Infraestructura")


class InsumoRestriccionesTests(RestriccionesTests):
    """Restricciones de la ficha de Insumo (regla 2 de CMP-ALT-INS y D-36)."""

    def test_regla_cmp_alt_ins_2_nombre_unico_sin_distinguir_mayusculas_viola(self):
        """CMP-ALT-INS regla 2: el nombre es único entre activos e inactivos, sin distinguir mayúsculas."""
        insumo("Detergente", activo=False)
        self.viola(lambda: insumo("dETERGENTE"))

    def test_regla_cmp_alt_ins_2_nombres_distintos_no_viola(self):
        """CMP-ALT-INS regla 2: dos nombres distintos conviven."""
        insumo("Detergente")
        self.assertIsNotNone(insumo("Lavandina").pk)

    def test_regla_cmp_alt_ins_5_unidad_fuera_de_dominio_viola(self):
        """CMP-ALT-INS regla 5: la unidad está en la lista fija."""
        self.viola(lambda: insumo("X", unidad="docena"))

    def test_regla_cmp_alt_ins_5_cada_unidad_no_viola(self):
        """CMP-ALT-INS regla 5: las ocho unidades se guardan."""
        for i, unidad in enumerate(["unidad", "kg", "g", "l", "ml", "m3", "m", "m2"]):
            self.assertIsNotNone(insumo(f"I{i}", unidad=unidad).pk)

    def test_regla_8_4_3_estado_fuera_de_dominio_viola(self):
        """D-36: el dominio de `estado_insumo`."""
        self.viola(lambda: insumo("X").__class__.objects.filter(nombre_insumo="X").update(estado_insumo="baja"))


class InsumoInvernaderoRestriccionesTests(RestriccionesTests):
    """Restricciones de la ficha de InsumoInvernadero (regla 1 de 8.4 y D-36)."""

    def setUp(self):
        self.invernadero = crear_invernadero("Invernadero Uno")
        self.insumo = insumo()

    def test_regla_8_4_1_un_solo_registro_por_insumo_e_invernadero_viola(self):
        """Regla 1 de 8.4: un solo `InsumoInvernadero` por (insumo, invernadero), activo o inactivo."""
        existencia(self.insumo, self.invernadero, activo=False)
        self.viola(lambda: existencia(self.insumo, self.invernadero))

    def test_regla_8_4_1_mismo_insumo_en_otro_invernadero_no_viola(self):
        """Regla 1 de 8.4: el mismo insumo en otro invernadero es otro registro."""
        existencia(self.insumo, self.invernadero)
        self.assertIsNotNone(existencia(self.insumo, crear_invernadero("Invernadero Dos")).pk)

    def test_regla_8_4_1_minimo_negativo_viola_y_cero_no(self):
        """Modelo: `cant_min_insumo >= 0`."""
        self.viola(lambda: existencia(self.insumo, self.invernadero, minimo=-1))
        self.assertEqual(existencia(self.insumo, self.invernadero, minimo=0).cant_min_insumo, 0)

    def test_regla_8_4_1_transito_negativo_viola_y_cero_no(self):
        """Modelo: `cant_transito_insumo >= 0`."""
        self.viola(lambda: existencia(self.insumo, self.invernadero, transito=-1))
        self.assertEqual(existencia(self.insumo, self.invernadero, transito=0).cant_transito_insumo, 0)

    def test_regla_8_4_1_precio_cero_o_negativo_viola_y_positivo_no(self):
        """Modelo: `referencia_precio > 0`."""
        self.viola(lambda: existencia(self.insumo, self.invernadero, precio=0))
        self.viola(lambda: existencia(self.insumo, self.invernadero, precio=-5))
        self.assertEqual(existencia(self.insumo, self.invernadero, precio="0.01").referencia_precio, Decimal("0.01"))

    def test_regla_8_4_1_estado_fuera_de_dominio_viola(self):
        """D-36: el dominio de `estado_insumo_invernadero`."""
        creada = existencia(self.insumo, self.invernadero)
        self.viola(lambda: InsumoInvernadero.objects.filter(pk=creada.pk).update(estado_insumo_invernadero="baja"))


class LoteInsumoRestriccionesTests(RestriccionesTests):
    """Restricciones de la ficha de LoteInsumo (reglas 3 y 4 de 8.23)."""

    def setUp(self):
        self.existencia = existencia(insumo(), crear_invernadero("Invernadero Uno"))

    def faltante(self, disponible="-1", **extra):
        datos = {"insumo_invernadero": self.existencia, "cantidad_disponible": Decimal(disponible), "es_faltante_sin_lote": True}
        return LoteInsumo.objects.create(**(datos | extra))

    def comun(self, **extra):
        datos = {
            "insumo_invernadero": self.existencia,
            "cantidad_ingresada": Decimal("5"),
            "cantidad_disponible": Decimal("5"),
            "fecha_ingreso": timezone.localdate(),
        }
        return LoteInsumo.objects.create(**(datos | extra))

    def test_regla_8_23_4_a_lo_sumo_un_faltante_por_existencia_viola(self):
        """Regla 4 de 8.23: un segundo faltante sin lote de la misma existencia lo rechaza la base."""
        self.faltante()
        self.viola(lambda: self.faltante("-2"))

    def test_regla_8_23_4_un_faltante_en_otra_existencia_no_viola(self):
        """Regla 4 de 8.23: el límite es por `InsumoInvernadero`."""
        self.faltante()
        otra = existencia(insumo("Lavandina"), self.existencia.invernadero)
        self.assertIsNotNone(LoteInsumo.objects.create(insumo_invernadero=otra, cantidad_disponible=-1, es_faltante_sin_lote=True).pk)

    def test_regla_8_23_4_faltante_positivo_viola_y_cero_no(self):
        """Regla 4 de 8.23: el faltante nunca es positivo."""
        self.viola(lambda: self.faltante("1"))
        self.assertEqual(self.faltante("0").cantidad_disponible, 0)

    def test_regla_8_23_4_faltante_con_datos_de_lote_viola(self):
        """Regla 4 de 8.23: el faltante no lleva cantidad ingresada, ingreso ni vencimiento."""
        self.viola(lambda: self.faltante(cantidad_ingresada=Decimal("3")))
        self.viola(lambda: self.faltante(fecha_ingreso=timezone.localdate()))
        self.viola(lambda: self.faltante(fecha_vencimiento=timezone.localdate()))

    def test_regla_8_23_3_lote_comun_negativo_viola_y_cero_no(self):
        """Regla 3 de 8.23: un lote común nunca queda negativo; en 0 se conserva (trazabilidad)."""
        self.viola(lambda: self.comun(cantidad_disponible=Decimal("-0.001")))
        self.assertEqual(self.comun(cantidad_disponible=Decimal("0")).cantidad_disponible, 0)

    def test_regla_8_23_3_lote_comun_sin_ingresada_positiva_viola(self):
        """Regla 3 de 8.23: un lote común tiene `cantidad_ingresada` mayor que cero."""
        self.viola(lambda: self.comun(cantidad_ingresada=None))
        self.viola(lambda: self.comun(cantidad_ingresada=Decimal("0")))

    def test_regla_8_23_3_lote_comun_sin_fecha_de_ingreso_viola(self):
        """Regla 3 de 8.23: un lote común tiene `fecha_ingreso`."""
        self.viola(lambda: self.comun(fecha_ingreso=None))

    def test_regla_8_23_3_lote_comun_con_vencimiento_o_sin_el_no_viola(self):
        """Regla 3 de 8.23: el vencimiento puede estar o no en la base (según el insumo lo verifica el servicio)."""
        self.assertIsNone(self.comun().fecha_vencimiento)
        self.assertIsNotNone(self.comun(fecha_vencimiento=timezone.localdate()).fecha_vencimiento)


class MovimientoInsumoRestriccionesTests(RestriccionesTests):
    """Restricciones de la ficha de MovimientoInsumo (reglas 1 a 4 de 8.19 y D-52)."""

    def setUp(self):
        self.lote = lote(existencia(insumo(), crear_invernadero("Invernadero Uno")), 10)

    def crear(self, tipo, cantidad="1", motivo=None, descripcion="", origen=None):
        return MovimientoInsumo.objects.create(
            lote_insumo=self.lote,
            cantidad=Decimal(cantidad),
            tipo_movimiento=tipo,
            motivo_ajuste=motivo,
            descripcion_ajuste=descripcion,
            origen=origen,
        )

    def test_regla_8_19_cantidad_cero_o_negativa_viola_y_positiva_no(self):
        """Modelo: `cantidad > 0` (el sentido lo da el tipo)."""
        self.viola(lambda: self.crear(Mov.AJUSTE_POSITIVO, "0", Motivo.RECUENTO_FISICO))
        self.viola(lambda: self.crear(Mov.AJUSTE_POSITIVO, "-1", Motivo.RECUENTO_FISICO))
        self.assertIsNotNone(self.crear(Mov.AJUSTE_POSITIVO, "0.001", Motivo.RECUENTO_FISICO).pk)

    def test_regla_8_19_tipo_fuera_de_dominio_viola(self):
        """Modelo: el dominio de `tipo_movimiento`."""
        self.viola(lambda: self.crear("regalo", origen=origen_falso()))

    def test_regla_8_19_cada_tipo_no_viola(self):
        """Modelo: los seis tipos con sus condiciones (ajustes con motivo y sin origen; el resto con origen)."""
        self.crear(Mov.AJUSTE_POSITIVO, motivo=Motivo.CARGA_INICIAL)
        self.crear(Mov.AJUSTE_NEGATIVO, motivo=Motivo.ROTURA_O_PERDIDA)
        self.crear(Mov.SALIDA_POR_CORRECCION)
        self.crear(Mov.SALIDA_POR_CONSUMO, origen=origen_falso())
        self.crear(Mov.ENTRADA_POR_CORRECCION, origen=origen_falso())
        self.crear(Mov.INGRESO_POR_RECEPCION, origen=origen_falso())

    def test_regla_8_19_motivo_en_un_movimiento_que_no_es_ajuste_viola(self):
        """Modelo: `motivo_ajuste` es nulo si el tipo no es de ajuste."""
        self.viola(lambda: self.crear(Mov.SALIDA_POR_CONSUMO, motivo=Motivo.OTRO, descripcion="x", origen=origen_falso()))

    def test_regla_8_19_ajuste_sin_motivo_viola(self):
        """Modelo: `motivo_ajuste` es obligatorio en los ajustes."""
        self.viola(lambda: self.crear(Mov.AJUSTE_NEGATIVO))

    def test_regla_8_19_motivo_fuera_de_dominio_viola(self):
        """Modelo: el dominio de `motivo_ajuste`."""
        self.viola(lambda: self.crear(Mov.AJUSTE_NEGATIVO, motivo="capricho"))

    def test_regla_8_19_motivo_otro_sin_descripcion_viola_y_con_descripcion_no(self):
        """Modelo: `descripcion_ajuste` no vacía si el motivo es «otro»."""
        self.viola(lambda: self.crear(Mov.AJUSTE_POSITIVO, motivo=Motivo.OTRO))
        self.assertIsNotNone(self.crear(Mov.AJUSTE_POSITIVO, motivo=Motivo.OTRO, descripcion="Donación").pk)

    def test_regla_8_19_3_ajuste_con_origen_viola(self):
        """Regla 3 de 8.19 (D-52 punto 4): un ajuste no tiene origen."""
        self.viola(lambda: self.crear(Mov.AJUSTE_POSITIVO, motivo=Motivo.CARGA_INICIAL, origen=origen_falso()))

    def test_regla_8_19_3_salida_por_correccion_con_origen_viola(self):
        """Regla 3 de 8.19: la salida por corrección entre lotes no tiene origen."""
        self.viola(lambda: self.crear(Mov.SALIDA_POR_CORRECCION, origen=origen_falso()))

    def test_regla_8_19_3_salida_por_consumo_sin_origen_viola(self):
        """Regla 3 de 8.19: la salida por consumo siempre tiene origen (el consumo)."""
        self.viola(lambda: self.crear(Mov.SALIDA_POR_CONSUMO))

    def test_regla_8_19_3_entrada_por_correccion_sin_origen_viola_y_con_su_salida_no(self):
        """Regla 3 de 8.19 y D-52 punto 4: la entrada por corrección apunta a su salida (un movimiento es un documento)."""
        self.viola(lambda: self.crear(Mov.ENTRADA_POR_CORRECCION))
        salida = self.crear(Mov.SALIDA_POR_CORRECCION)
        entrada = self.crear(Mov.ENTRADA_POR_CORRECCION, origen=OrigenDocumento.objects.get(pk=salida.pk))
        self.assertEqual(entrada.origen_id, salida.pk)

    def test_d52_el_movimiento_es_un_origen_de_documento_de_tipo_movimiento_de_insumo(self):
        """D-52 puntos 1 y 2: la herencia multitabla fija `tipo` y comparte el `id` con `OrigenDocumento`."""
        creado = self.crear(Mov.AJUSTE_POSITIVO, motivo=Motivo.CARGA_INICIAL)
        documento = OrigenDocumento.objects.get(pk=creado.pk)
        self.assertEqual(documento.tipo, OrigenDocumento.Tipo.MOVIMIENTO_DE_INSUMO)
        self.assertEqual(creado.origendocumento_ptr_id, creado.id)

    def test_d52_origen_se_lee_con_related_name_movimientos_de_insumo(self):
        """D-52 punto 4: el origen lee sus movimientos con `movimientos_de_insumo`."""
        origen = origen_falso()
        movimiento_de_consumo = self.crear(Mov.SALIDA_POR_CONSUMO, origen=origen)
        self.assertEqual(list(origen.movimientos_de_insumo.all()), [movimiento_de_consumo])

    def test_regla_8_19_la_fabrica_de_movimientos_respeta_las_restricciones(self):
        """Las fábricas arman movimientos que cumplen todas las restricciones (para las pruebas que las usan)."""
        movimiento(self.lote, Mov.AJUSTE_NEGATIVO, 1)
        movimiento(self.lote, Mov.SALIDA_POR_CONSUMO, 1)
        self.assertEqual(self.lote.movimientos.count(), 3)
