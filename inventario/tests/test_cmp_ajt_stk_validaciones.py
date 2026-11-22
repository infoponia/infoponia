# Pruebas de CMP-AJT-STK · precondiciones, reglas y extensiones de validación (docs/casos_de_uso/inventario/ajuste_de_stock.md; INV-02, paso 6).
# Las extensiones se nombran con el número del paso: ``test_extension_7b_3a_rotura_supera_lo_disponible`` (decidido con el estudiante; la regla
# general de .claude/rules/pruebas.md dice ``test_ext_``: la diferencia va a docs/temas_abiertos.md). El contrato del servicio, en
# ``inventario/tests/ajustes_comunes.py``. Todas se prueban sobre ``calcular_ajuste`` (que valida sin escribir); ``confirmar_ajuste`` repite
# las mismas validaciones y no cambia nada si fallan.
#
# Códigos de error. Por campo: obligatorio, invalido, cantidad_invalida, decimales_de_la_unidad, cantidad_no_positiva, cantidad_negativa,
# vencimiento_obligatorio, vencimiento_vencido, lote_invalido, supera_lo_disponible, supera_el_faltante, mismo_lote, sin_lotes y
# lote_vencido_no_sube. Generales (sin campo): sin_lotes_vencidos, sin_diferencias, insumo_no_habilitado e invernadero_inactivo.

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.tests.ajustes_comunes import (
    CARGA_INICIAL,
    CORRECCION,
    OTRO,
    RECUENTO,
    ROTURA,
    VENCIMIENTO,
    BaseDeAjustes,
    ajustes,
)
from inventario.tests.fabricas import existencia, faltante, insumo, lote
from maestros.tests.fabricas import codigos_de, error_de

D = Decimal


class CmpAjtStkPrecondicionesTests(BaseDeAjustes, TestCase):
    def setUp(self):
        self.preparar()
        self.l1 = lote(self.iin, 10, vence=self.vence)

    def test_pre_a_solo_el_agronomo_activo_ajusta(self):
        """Precondición a y regla «Quién lo ejecuta»: el Gerente, el Capataz y el Administrador no; tampoco una cuenta inactiva."""
        entrada = {"lote_id": self.l1.pk, "cantidad": "1"}
        for actor in (crear_gerente(), crear_capataz(), crear_administrador()):
            with self.subTest(actor=actor.email), self.assertRaises(PermissionDenied):
                self.calcular(ROTURA, entrada, actor=actor)
        self.agronomo.is_active = False
        self.agronomo.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            self.calcular(ROTURA, entrada)

    def test_pre_b_un_invernadero_ajeno_da_permiso_denegado(self):
        """Precondición b: el invernadero tiene que estar a cargo del actor (solo accede el Agrónomo a cargo)."""
        with self.assertRaises(PermissionDenied):
            self.calcular(ROTURA, {"lote_id": self.l1.pk, "cantidad": "1"}, actor=self.otro)

    def test_pre_b_un_invernadero_inactivo_se_rechaza(self):
        """Precondición b: el invernadero tiene que estar activo."""
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save(update_fields=["estado_invernadero"])
        error = error_de(lambda: self.calcular(ROTURA, {"lote_id": self.l1.pk, "cantidad": "1"}))
        self.assertEqual(codigos_de(error), ["invernadero_inactivo"])

    def test_pre_b_un_invernadero_o_un_insumo_inexistentes_dan_404(self):
        """Ids inexistentes: 404 (D-28)."""
        with self.assertRaises(Http404):
            ajustes.calcular_ajuste(self.agronomo, 999999, self.insumo.pk, ROTURA, {})
        with self.assertRaises(Http404):
            ajustes.calcular_ajuste(self.agronomo, self.invernadero.pk, 999999, ROTURA, {})

    def test_extension_4a_un_insumo_no_habilitado_en_el_invernadero_se_rechaza_para_ofrecer_habilitarlo(self):
        """Extensión 4a: el insumo no está habilitado; el servicio lo informa (la pantalla ofrece Habilitar Insumo en Invernadero)."""
        otro = insumo("Bolsas", tipo=self.tipo, unidad="unidad")
        error = error_de(
            lambda: ajustes.calcular_ajuste(self.agronomo, self.invernadero.pk, otro.pk, CARGA_INICIAL, {"cantidad": "1"})
        )
        self.assertEqual(codigos_de(error), ["insumo_no_habilitado"])

    def test_extension_4a_un_insumo_deshabilitado_tampoco_se_ajusta(self):
        """Paso 4: el Sistema presenta los insumos habilitados y activos del invernadero: uno deshabilitado no."""
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(estado_insumo_invernadero="inactivo")
        error = error_de(lambda: self.calcular(ROTURA, {"lote_id": self.l1.pk, "cantidad": "1"}))
        self.assertEqual(codigos_de(error), ["insumo_no_habilitado"])

    def test_extension_7_sin_motivo_o_con_un_motivo_desconocido_se_rechaza(self):
        """Paso 7: hay que elegir uno de los seis motivos."""
        self.assertEqual(codigos_de(error_de(lambda: self.calcular(None, {})), "motivo"), ["obligatorio"])
        self.assertEqual(codigos_de(error_de(lambda: self.calcular("regalo", {})), "motivo"), ["invalido"])

    def test_garantia_un_ajuste_invalido_en_confirmar_no_cambia_nada_ni_audita(self):
        """Garantías mínimas: si falla, ningún cambio en lotes, movimientos ni auditoría."""
        huella = self.calcular(ROTURA, {"lote_id": self.l1.pk, "cantidad": "4"}).huella
        antes = (LoteInsumo.objects.count(), MovimientoInsumo.objects.count(), RegistroAuditoria.objects.count())
        with self.assertRaises(Exception) as contexto:
            ajustes.confirmar_ajuste(
                self.agronomo, self.invernadero.pk, self.insumo.pk, ROTURA, {"lote_id": self.l1.pk, "cantidad": "99"}, huella
            )
        self.assertEqual(codigos_de(contexto.exception, "cantidad"), ["supera_lo_disponible"])
        self.assertEqual(
            (LoteInsumo.objects.count(), MovimientoInsumo.objects.count(), RegistroAuditoria.objects.count()), antes
        )
        self.assertEqual(self.disponible(self.l1), D("10"))


class CmpAjtStkCargaTests(BaseDeAjustes, TestCase):
    """Extensión 7a (y la parte que «otro» que suma reutiliza)."""

    def setUp(self):
        self.preparar()

    def error(self, **entrada):
        return error_de(lambda: self.calcular(CARGA_INICIAL, entrada))

    def test_extension_7a_3a_la_cantidad_con_mas_decimales_que_la_unidad_informa_cuantos_admite(self):
        """Extensión 7a.3a: la cantidad no es válida para la unidad: se señala el error y se informa cuántos decimales admite."""
        error = self.error(cantidad="1.2345", vencimiento=self.vence)
        self.assertEqual(codigos_de(error, "cantidad"), ["decimales_de_la_unidad"])
        self.assertIn("3 decimales", error.error_dict["cantidad"][0].messages[0])

    def test_extension_7a_3a_la_unidad_entera_no_admite_decimales(self):
        """Regla «Cantidad válida»: la unidad admite 0 decimales."""
        bolsas = existencia(insumo("Bolsas", tipo=self.tipo, unidad="unidad"), self.invernadero)
        error = error_de(lambda: self.calcular(CARGA_INICIAL, {"cantidad": "2.5"}, iin=bolsas))
        self.assertEqual(codigos_de(error, "cantidad"), ["decimales_de_la_unidad"])

    def test_extension_7a_3a_la_cantidad_es_obligatoria_y_mayor_que_cero(self):
        """Regla «Cantidad válida»: un número mayor que cero."""
        self.assertEqual(codigos_de(self.error(cantidad="", vencimiento=self.vence), "cantidad"), ["obligatorio"])
        self.assertEqual(codigos_de(self.error(vencimiento=self.vence), "cantidad"), ["obligatorio"])
        for malo in ("0", "-3"):
            with self.subTest(cantidad=malo):
                self.assertEqual(codigos_de(self.error(cantidad=malo, vencimiento=self.vence), "cantidad"), ["cantidad_no_positiva"])
        self.assertEqual(codigos_de(self.error(cantidad="mucho", vencimiento=self.vence), "cantidad"), ["cantidad_invalida"])

    def test_extension_7a_3b_falta_la_fecha_de_vencimiento(self):
        """Extensión 7a.3b: si el insumo controla vencimiento, la fecha es obligatoria."""
        error = self.error(cantidad="5")
        self.assertEqual(codigos_de(error, "vencimiento"), ["vencimiento_obligatorio"])

    def test_extension_7a_3b_la_fecha_anterior_a_hoy_informa_que_lo_vencido_no_ingresa(self):
        """Extensión 7a.3b: lo vencido no ingresa al stock (la fecha actual es la del invernadero)."""
        error = self.error(cantidad="5", vencimiento=self.hoy - timedelta(days=1))
        self.assertEqual(codigos_de(error, "vencimiento"), ["vencimiento_vencido"])
        self.assertIn("lo vencido no ingresa al stock", error.error_dict["vencimiento"][0].messages[0])

    def test_extension_7a_los_errores_de_cantidad_y_de_vencimiento_se_informan_juntos(self):
        """Patrón ABM: un solo error con un error por campo."""
        error = self.error(cantidad="0")
        self.assertEqual(set(error.error_dict), {"cantidad", "vencimiento"})

    def test_extension_7a_un_insumo_que_no_controla_vencimiento_no_pide_la_fecha(self):
        """Postcondición b: sin vencimiento si el insumo no lo controla; no hace falta indicarlo."""
        bolsas = existencia(insumo("Bolsas", tipo=self.tipo, unidad="unidad"), self.invernadero)
        r = self.calcular(CARGA_INICIAL, {"cantidad": "5"}, iin=bolsas)
        self.assertEqual(r.lotes_nuevos[0].vencimiento, None)

    def test_extension_7a_una_cantidad_float_se_rechaza(self):
        """Nunca ``float`` con cantidades: se rechaza como cantidad inválida."""
        self.assertEqual(codigos_de(self.error(cantidad=1.5, vencimiento=self.vence), "cantidad"), ["cantidad_invalida"])

    def test_extension_7a_se_acepta_una_cantidad_decimal_o_como_texto(self):
        """Las cantidades pueden ser ``Decimal`` o texto."""
        self.assertEqual(self.calcular(CARGA_INICIAL, {"cantidad": D("2.5"), "vencimiento": self.vence}).diferencia, D("2.5"))
        self.assertEqual(self.calcular(CARGA_INICIAL, {"cantidad": "2,5", "vencimiento": self.vence}).diferencia, D("2.5"))


class CmpAjtStkRoturaTests(BaseDeAjustes, TestCase):
    """Extensión 7b."""

    def setUp(self):
        self.preparar()
        self.l1 = lote(self.iin, 10, vence=self.vence)

    def error(self, **entrada):
        return error_de(lambda: self.calcular(ROTURA, entrada))

    def test_extension_7b_3a_rotura_supera_lo_disponible(self):
        """Extensión 7b.3a: la cantidad supera lo disponible del lote: se señala el error y se informa la cantidad disponible."""
        error = self.error(lote_id=self.l1.pk, cantidad="10.5")
        self.assertEqual(codigos_de(error, "cantidad"), ["supera_lo_disponible"])
        self.assertIn("10", error.error_dict["cantidad"][0].messages[0])

    def test_extension_7b_3a_rotura_con_decimales_que_la_unidad_no_admite(self):
        """Extensión 7b.3a: «no es válida para la unidad»."""
        self.assertEqual(codigos_de(self.error(lote_id=self.l1.pk, cantidad="1.2345"), "cantidad"), ["decimales_de_la_unidad"])

    def test_extension_7b_3a_la_cantidad_es_obligatoria_y_mayor_que_cero(self):
        """Regla «Cantidad válida»."""
        self.assertEqual(codigos_de(self.error(lote_id=self.l1.pk), "cantidad"), ["obligatorio"])
        self.assertEqual(codigos_de(self.error(lote_id=self.l1.pk, cantidad="0"), "cantidad"), ["cantidad_no_positiva"])

    def test_extension_7b_1_el_lote_es_obligatorio(self):
        """Extensión 7b.2: el Agrónomo indica el lote afectado."""
        self.assertEqual(codigos_de(self.error(cantidad="1"), "lote"), ["obligatorio"])

    def test_extension_7b_1_solo_se_ofrecen_lotes_con_cantidad_disponible_mayor_que_cero(self):
        """Extensión 7b.1: lotes con cantidad disponible mayor que cero; uno en 0 se rechaza."""
        agotado = lote(self.iin, 0, vence=self.vence, ingresada=5)
        self.assertEqual(codigos_de(self.error(lote_id=agotado.pk, cantidad="1"), "lote"), ["lote_invalido"])

    def test_regla_8_23_4_la_rotura_nunca_sale_del_faltante_ni_de_lotes_ajenos(self):
        """Regla 4 de 8.23: un ajuste negativo nunca sale del faltante; un lote de otra existencia ni existe para este ajuste."""
        falta = faltante(self.iin, 3)
        ajena = lote(existencia(insumo("Otro", tipo=self.tipo, unidad="l"), self.invernadero), 5)
        for malo in (falta.pk, ajena.pk, 999999):
            with self.subTest(lote=malo):
                self.assertEqual(codigos_de(self.error(lote_id=malo, cantidad="1"), "lote"), ["lote_invalido"])

    def test_extension_7b_se_puede_romper_un_lote_vencido_con_stock(self):
        """Un lote vencido con cantidad mayor que cero está entre los ofrecidos."""
        viejo = lote(self.iin, 3, vence=self.vencido)
        self.assertEqual(self.calcular(ROTURA, {"lote_id": viejo.pk, "cantidad": "3"}).diferencia, D("-3"))


class CmpAjtStkVencimientoTests(BaseDeAjustes, TestCase):
    """Extensión 7c."""

    def setUp(self):
        self.preparar()
        self.l1 = lote(self.iin, 10, vence=self.vence)

    def error(self, entrada):
        return error_de(lambda: self.calcular(VENCIMIENTO, entrada))

    def test_extension_7c_1a_un_insumo_sin_lotes_vencidos_con_cantidad_lo_informa(self):
        """Extensión 7c.1a: el insumo no tiene lotes vencidos con cantidad disponible: el Sistema lo informa."""
        error = self.error({"lotes": [self.l1.pk]})
        self.assertEqual(codigos_de(error), ["sin_lotes_vencidos"])

    def test_extension_7c_1a_un_lote_vencido_ya_agotado_no_cuenta(self):
        """Solo lotes vencidos con cantidad disponible mayor que cero."""
        lote(self.iin, 0, vence=self.vencido, ingresada=4)
        self.assertEqual(codigos_de(self.error({"lotes": []})), ["sin_lotes_vencidos"])

    def test_extension_7c_3a_no_indico_ningun_lote(self):
        """Extensión 7c.3a: el Sistema señala que debe indicar al menos uno."""
        lote(self.iin, 5, vence=self.vencido)
        self.assertEqual(codigos_de(self.error({"lotes": []}), "lotes"), ["sin_lotes"])
        self.assertEqual(codigos_de(self.error({}), "lotes"), ["sin_lotes"])

    def test_extension_7c_solo_se_dan_de_baja_lotes_vencidos(self):
        """Regla «Baja por vencimiento»: solo de lotes vencidos; uno vigente, o que vence hoy, se rechaza."""
        vencido = lote(self.iin, 5, vence=self.vencido)
        vence_hoy = lote(self.iin, 2, vence=self.hoy)
        self.assertEqual(codigos_de(self.error({"lotes": [vencido.pk, self.l1.pk]}), "lotes"), ["lote_invalido"])
        self.assertEqual(codigos_de(self.error({"lotes": [vence_hoy.pk]}), "lotes"), ["lote_invalido"])


class CmpAjtStkCorreccionTests(BaseDeAjustes, TestCase):
    """Extensión 7d."""

    def setUp(self):
        self.preparar()
        self.l1 = lote(self.iin, 10, vence=self.vence)
        self.l2 = lote(self.iin, 20, vence=self.vence + timedelta(days=30))

    def error(self, **entrada):
        return error_de(lambda: self.calcular(CORRECCION, entrada))

    def test_extension_7d_3a_el_destino_es_el_mismo_que_el_origen(self):
        """Extensión 7d.3a: el lote de destino es el mismo que el de origen: se señala el error."""
        error = self.error(origen_id=self.l1.pk, destino_id=self.l1.pk, cantidad="1")
        self.assertEqual(codigos_de(error, "destino"), ["mismo_lote"])

    def test_extension_7d_3b_la_cantidad_supera_lo_disponible_del_origen(self):
        """Extensión 7d.3b: se señala el error y se informa la cantidad disponible del lote de origen."""
        error = self.error(origen_id=self.l1.pk, destino_id=self.l2.pk, cantidad="11")
        self.assertEqual(codigos_de(error, "cantidad"), ["supera_lo_disponible"])
        self.assertIn("10", error.error_dict["cantidad"][0].messages[0])

    def test_extension_7d_3b_la_cantidad_no_es_valida_para_la_unidad(self):
        """Extensión 7d.3b."""
        error = self.error(origen_id=self.l1.pk, destino_id=self.l2.pk, cantidad="0.0001")
        self.assertEqual(codigos_de(error, "cantidad"), ["decimales_de_la_unidad"])

    def test_extension_7d_el_origen_y_el_destino_son_obligatorios(self):
        """Extensión 7d.2: se indica el lote de origen, el de destino y la cantidad."""
        error = self.error(cantidad="1")
        self.assertEqual((codigos_de(error, "origen"), codigos_de(error, "destino")), (["obligatorio"], ["obligatorio"]))

    def test_extension_7d_1_el_origen_tiene_que_tener_cantidad_disponible_y_no_ser_el_faltante(self):
        """Extensión 7d.1: origen posible = lotes con cantidad disponible mayor que cero; el faltante nunca es origen."""
        agotado = lote(self.iin, 0, vence=self.vence, ingresada=4)
        falta = faltante(self.iin, 2)
        for malo in (agotado.pk, falta.pk):
            with self.subTest(origen=malo):
                error = self.error(origen_id=malo, destino_id=self.l2.pk, cantidad="1")
                self.assertEqual(codigos_de(error, "origen"), ["lote_invalido"])

    def test_extension_7d_1_el_destino_puede_ser_cualquier_lote_incluso_uno_agotado(self):
        """Extensión 7d.1: destinos posibles = todos los lotes y el faltante sin lote."""
        agotado = lote(self.iin, 0, vence=self.vence, ingresada=4)
        r = self.calcular(CORRECCION, {"origen_id": self.l1.pk, "destino_id": agotado.pk, "cantidad": "2"})
        self.assertEqual(r.diferencia, D("0"))

    def test_extension_7d_el_destino_que_no_es_de_la_existencia_se_rechaza(self):
        """Un lote de otra existencia no es destino válido."""
        ajena = lote(existencia(insumo("Otro", tipo=self.tipo, unidad="l"), self.invernadero), 5)
        error = self.error(origen_id=self.l1.pk, destino_id=ajena.pk, cantidad="1")
        self.assertEqual(codigos_de(error, "destino"), ["lote_invalido"])

    def test_extension_7d_el_faltante_como_destino_no_puede_pasar_de_cero(self):
        """Interpretación aprobada: el faltante nunca es positivo (regla 4 de 8.23): como destino recibe a lo sumo lo que falta."""
        faltante(self.iin, 3)
        falta = LoteInsumo.objects.get(insumo_invernadero=self.iin, es_faltante_sin_lote=True)
        error = self.error(origen_id=self.l1.pk, destino_id=falta.pk, cantidad="4")
        self.assertEqual(codigos_de(error, "cantidad"), ["supera_el_faltante"])
        self.assertEqual(self.calcular(CORRECCION, {"origen_id": self.l1.pk, "destino_id": falta.pk, "cantidad": "3"}).diferencia, D("0"))


class CmpAjtStkOtroTests(BaseDeAjustes, TestCase):
    """Extensión 7e."""

    def setUp(self):
        self.preparar()
        self.l1 = lote(self.iin, 10, vence=self.vence)

    def error(self, **entrada):
        return error_de(lambda: self.calcular(OTRO, entrada))

    def test_extension_7e_1a_no_indico_si_suma_o_resta(self):
        """Extensión 7e.1a: el Sistema señala el dato que falta."""
        self.assertEqual(codigos_de(self.error(descripcion="x"), "sentido"), ["obligatorio"])

    def test_extension_7e_1a_no_indico_la_descripcion(self):
        """Extensión 7e.1a y regla «Otro»: la descripción es obligatoria (un texto en blanco no vale)."""
        for vacia in ("", "   ", None):
            with self.subTest(descripcion=vacia):
                error = self.error(sentido="resta", lote_id=self.l1.pk, cantidad="1", descripcion=vacia)
                self.assertEqual(codigos_de(error, "descripcion"), ["obligatorio"])

    def test_extension_7e_1a_los_dos_datos_faltantes_se_informan_juntos(self):
        """Un solo error con un error por campo."""
        self.assertEqual(set(self.error().error_dict), {"sentido", "descripcion"})

    def test_extension_7e_un_sentido_desconocido_se_rechaza(self):
        """Solo «suma» o «resta»."""
        self.assertEqual(codigos_de(self.error(sentido="multiplica", descripcion="x"), "sentido"), ["invalido"])

    def test_extension_7e_que_suma_aplica_las_validaciones_de_la_carga(self):
        """Extensión 7e.2: si suma, sigue los pasos 7a.1 a 7a.3: cantidad y vencimiento, con sus errores."""
        error = self.error(sentido="suma", descripcion="x", cantidad="1.2345", vencimiento=self.hoy - timedelta(days=1))
        self.assertEqual(codigos_de(error, "cantidad"), ["decimales_de_la_unidad"])
        self.assertEqual(codigos_de(error, "vencimiento"), ["vencimiento_vencido"])

    def test_extension_7e_que_resta_aplica_las_validaciones_de_la_rotura(self):
        """Extensión 7e.2: si resta, sigue los pasos 7b.1 a 7b.3."""
        error = self.error(sentido="resta", descripcion="x", lote_id=self.l1.pk, cantidad="11")
        self.assertEqual(codigos_de(error, "cantidad"), ["supera_lo_disponible"])


class CmpAjtStkRecuentoValidacionesTests(BaseDeAjustes, TestCase):
    """Extensiones 10a, 10b y 12a."""

    def setUp(self):
        self.preparar()
        self.l1 = lote(self.iin, 10, vence=self.vence)
        self.l2 = lote(self.iin, 20, vence=self.vence + timedelta(days=30))

    def error(self, entrada):
        return error_de(lambda: self.calcular(RECUENTO, entrada))

    def test_extension_10a_la_cantidad_contada_negativa_se_rechaza(self):
        """Extensión 10a: la cantidad contada es negativa."""
        error = self.error({"contados": {self.l1.pk: "-1"}})
        self.assertEqual(codigos_de(error, f"contado_{self.l1.pk}"), ["cantidad_negativa"])

    def test_extension_10a_la_cantidad_contada_con_decimales_que_la_unidad_no_admite_informa_cuantos_admite(self):
        """Extensión 10a: no válida para la unidad: se informa cuántos decimales admite."""
        error = self.error({"contados": {self.l1.pk: "1.2345"}})
        self.assertEqual(codigos_de(error, f"contado_{self.l1.pk}"), ["decimales_de_la_unidad"])
        self.assertIn("3 decimales", error.error_dict[f"contado_{self.l1.pk}"][0].messages[0])

    def test_extension_10a_la_cantidad_contada_que_no_es_un_numero_se_rechaza(self):
        """Extensión 10a."""
        self.assertEqual(codigos_de(self.error({"contados": {self.l1.pk: "muchos"}}), f"contado_{self.l1.pk}"), ["cantidad_invalida"])

    def test_extension_10a_los_errores_de_varios_lotes_se_informan_juntos(self):
        """Un error por campo, todos juntos."""
        error = self.error({"contados": {self.l1.pk: "-1", self.l2.pk: "x"}})
        self.assertEqual(set(error.error_dict), {f"contado_{self.l1.pk}", f"contado_{self.l2.pk}"})

    def test_extension_10a_solo_se_cuentan_lotes_comunes_de_la_existencia(self):
        """El faltante no es algo físico (no se cuenta) y un lote ajeno o inexistente no es de este recuento."""
        falta = faltante(self.iin, 2)
        ajena = lote(existencia(insumo("Otro", tipo=self.tipo, unidad="l"), self.invernadero), 5)
        for malo in (falta.pk, ajena.pk, 999999):
            with self.subTest(lote=malo):
                self.assertEqual(codigos_de(self.error({"contados": {malo: "1"}}), "contados"), ["lote_invalido"])

    def test_extension_10_un_lote_vencido_no_puede_subir_en_el_recuento(self):
        """Interpretación aprobada: lo vencido no ingresa al stock; contar más de lo registrado en un lote vencido se rechaza."""
        viejo = lote(self.iin, 5, vence=self.vencido)
        error = self.error({"contados": {viejo.pk: "6"}})
        self.assertEqual(codigos_de(error, f"contado_{viejo.pk}"), ["lote_vencido_no_sube"])
        self.assertIn("lo vencido no ingresa al stock", error.error_dict[f"contado_{viejo.pk}"][0].messages[0])

    def test_extension_10b_2_el_lote_nuevo_se_verifica_como_en_7a(self):
        """Extensión 10b.2: la cantidad y la fecha del lote nuevo se verifican como en 7a.3a y 7a.3b."""
        nuevos = [
            {"cantidad": "1.2345", "vencimiento": self.vence},
            {"cantidad": "2"},
            {"cantidad": "3", "vencimiento": self.hoy - timedelta(days=1)},
        ]
        error = self.error({"nuevos": nuevos})
        self.assertEqual(codigos_de(error, "nuevo_0_cantidad"), ["decimales_de_la_unidad"])
        self.assertEqual(codigos_de(error, "nuevo_1_vencimiento"), ["vencimiento_obligatorio"])
        self.assertEqual(codigos_de(error, "nuevo_2_vencimiento"), ["vencimiento_vencido"])

    def test_extension_10b_2_el_lote_nuevo_tiene_cantidad_mayor_que_cero(self):
        """Regla «Cantidad válida»: un lote nuevo con cantidad 0 no tiene sentido."""
        self.assertEqual(codigos_de(self.error({"nuevos": [{"cantidad": "0", "vencimiento": self.vence}]}), "nuevo_0_cantidad"), ["cantidad_no_positiva"])

    def test_extension_12a_un_recuento_sin_diferencias_informa_que_no_hay_nada_que_ajustar(self):
        """Extensión 12a: ninguna cantidad contada difiere, no hay lotes nuevos y no hay faltante sin lote."""
        for entrada in ({}, {"contados": {}}, {"contados": {self.l1.pk: "10", self.l2.pk: "20"}}, {"nuevos": []}):
            with self.subTest(entrada=entrada):
                self.assertEqual(codigos_de(self.error(entrada)), ["sin_diferencias"])

    def test_extension_12a_con_faltante_sin_lote_el_recuento_si_tiene_algo_que_ajustar(self):
        """Extensión 12a: el faltante sin lote existente ya es una diferencia (queda en cero)."""
        faltante(self.iin, 1)
        self.assertEqual(self.calcular(RECUENTO, {}).faltante_a_cero, D("1"))

    def test_extension_12a_un_lote_nuevo_ya_es_una_diferencia(self):
        """Extensión 12a: «no hay lotes nuevos»: si hay, hay algo que ajustar."""
        self.assertEqual(self.calcular(RECUENTO, {"nuevos": [{"cantidad": "1", "vencimiento": self.vence}]}).diferencia, D("1"))
