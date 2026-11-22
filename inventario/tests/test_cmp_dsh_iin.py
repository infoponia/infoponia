# Pruebas de CMP-DSH-IIN · Deshabilitar Insumo en Invernadero (docs/casos_de_uso/inventario/insumo_invernadero.md; INV-02, paso 3).
#
# Servicios que se prueban (inventario/servicios/insumos_invernadero.py), tomados del módulo dentro de cada prueba:
#   deshabilitar_insumo(actor, iin_id) -> InsumoInvernadero
#     - Precondiciones a, b y c: Agrónomo activo; invernadero activo y a cargo (PermissionDenied si es ajeno; ``invernadero_inactivo``);
#       el insumo está habilitado (``insumo_deshabilitado``).
#     - Precondiciones d y e y regla 2: se juntan TODOS los impedimentos (``impedimentos_de_deshabilitacion`` de inventario.extensiones:
#       stock distinto de cero —también el negativo—, reservas, tránsito y los de ``compras``), en un solo ValidationError con un error
#       por impedimento; el código es el del impedimento y el mensaje trae qué pasa y cómo resolverlo. No se cambia nada.
#     - Postcondición a y regla 1: queda «inactivo» y conserva lotes, movimientos e historial. Postcondición b: la alerta «bajo el
#       mínimo» activa se resuelve (y va en ``datos.alertas_resueltas``). Postcondición c: ``baja_insumo_invernadero`` con el cambio de estado.
#   impedimentos_para_deshabilitar(actor, iin_id) -> list[Impedimento]: los mismos, para la ventana (solo lectura; no bloquea ni audita).
#   Regla 3: volver a habilitar reactiva el mismo registro (CMP-HAB-IIN).

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.test import TestCase, TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    ajuste_simulado,
    asegurar_datos_de_inventario,
    existencia,
    faltante,
    insumo,
    lote,
    perezoso,
    reservas_de_prueba,
    tipo_de_insumo,
    verificar_invariantes,
)
from maestros.extensiones import Impedimento
from maestros.models import Alerta
from maestros.tests.fabricas import (
    asegurar_datos_de_maestros,
    codigos_de,
    crear_agronomo,
    crear_invernadero,
    crear_invernadero_con_geografia_propia,
    error_de,
)

iin_servicio = perezoso("inventario.servicios.insumos_invernadero")
BAJA_IIN = RegistroAuditoria.Accion.BAJA_INSUMO_INVERNADERO
BAJO_MINIMO = "inv_insumo_bajo_minimo"


class CmpDshIinServicioTests(ConDatosDeInventario, TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-DSH-IIN."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Gómez")
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.insumo = insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.agronomo)
        self.iin = existencia(self.insumo, self.norte, minimo=0)

    def deshabilitar(self, actor=None):
        return iin_servicio.deshabilitar_insumo(actor or self.agronomo, self.iin.pk)

    # ---- precondiciones a, b y c ----

    def test_pre_a_el_gerente_no_deshabilita(self):
        """Precondición a: solo el Agrónomo."""
        with self.assertRaises(PermissionDenied):
            self.deshabilitar(crear_gerente())

    def test_pre_b_un_invernadero_ajeno_da_permiso_denegado(self):
        """Precondición b: a cargo del actor."""
        with self.assertRaises(PermissionDenied):
            self.deshabilitar(self.otro)
        self.iin.refresh_from_db()
        self.assertTrue(self.iin.activo)

    def test_pre_b_un_invernadero_inactivo_se_rechaza(self):
        """Precondición b: invernadero activo."""
        self.norte.estado_invernadero = "inactivo"
        self.norte.save(update_fields=["estado_invernadero"])
        self.assertEqual(codigos_de(error_de(self.deshabilitar)), ["invernadero_inactivo"])

    def test_pre_c_un_insumo_ya_deshabilitado_se_rechaza(self):
        """Precondición c: el insumo está habilitado en el invernadero."""
        self.deshabilitar()
        self.assertEqual(codigos_de(error_de(self.deshabilitar)), ["insumo_deshabilitado"])

    # ---- precondiciones d y e: los impedimentos ----

    def textos(self, error):
        return " | ".join(error.messages)

    def test_pre_d_con_stock_positivo_no_se_deshabilita_y_dice_como_resolverlo(self):
        """Precondición d y regla 2: el stock se usa o se lleva a cero con un ajuste."""
        lote(self.iin, 5)
        error = error_de(self.deshabilitar)
        self.assertEqual(codigos_de(error), ["stock_distinto_de_cero"])
        self.assertIn("ajuste", self.textos(error))
        self.iin.refresh_from_db()
        self.assertTrue(self.iin.activo)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA_IIN).count(), 0)

    def test_pre_d_el_stock_negativo_tambien_impide(self):
        """Precondición d: «ni positivo ni negativo»: el faltante sin lote cuenta."""
        faltante(self.iin, 2)
        self.assertEqual(codigos_de(error_de(self.deshabilitar)), ["stock_distinto_de_cero"])

    def test_pre_d_las_reservas_activas_impiden_y_nombran_cuanto(self):
        """Precondición d: cantidades reservadas (punto de extensión de `produccion`)."""
        with reservas_de_prueba(reservado={self.iin.pk: "3"}):
            error = error_de(self.deshabilitar)
        self.assertEqual(codigos_de(error), ["reservas_activas"])
        self.assertIn("3", self.textos(error))

    def test_pre_d_la_cantidad_en_transito_impide(self):
        """Precondición d: cantidad en tránsito."""
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(cant_transito_insumo=4)
        self.assertEqual(codigos_de(error_de(self.deshabilitar)), ["cantidad_en_transito"])

    def test_pre_d_y_e_los_impedimentos_de_compras_tambien_se_informan(self):
        """Precondiciones d y e: orden de compra aprobada y pedido en curso, por ``registrar_impedimento_de_deshabilitacion``."""
        falsos = [
            Impedimento("orden_de_compra_aprobada", "Hay una orden de compra aprobada.", "Recibila o cerrala."),
            Impedimento("pedido_en_curso", "Está en un pedido en curso.", "Cerralo o quitale el insumo."),
        ]
        with reservas_de_prueba(impedimentos={self.iin.pk: falsos}):
            error = error_de(self.deshabilitar)
        self.assertEqual(codigos_de(error), ["orden_de_compra_aprobada", "pedido_en_curso"])
        self.assertIn("Recibila o cerrala.", self.textos(error))

    def test_regla_2_se_juntan_todos_los_impedimentos_sin_quedarse_con_el_primero(self):
        """Regla 2: stock, reservas, tránsito y los de compras, todos juntos, en un error por impedimento."""
        lote(self.iin, 5)
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(cant_transito_insumo=4)
        falso = Impedimento("pedido_en_curso", "Está en un pedido en curso.", "Cerralo.")
        with reservas_de_prueba(reservado={self.iin.pk: "2"}, impedimentos={self.iin.pk: [falso]}):
            error = error_de(self.deshabilitar)
        self.assertEqual(
            codigos_de(error),
            ["stock_distinto_de_cero", "reservas_activas", "cantidad_en_transito", "pedido_en_curso"],
        )
        self.assertEqual(set(error.error_dict), {NON_FIELD_ERRORS})

    def test_regla_2_los_impedimentos_para_la_ventana_son_los_mismos_y_no_cambian_nada(self):
        """Solo lectura: lista los impedimentos con su código, qué pasa y cómo resolverlo, sin auditar."""
        lote(self.iin, 5)
        impedimentos = iin_servicio.impedimentos_para_deshabilitar(self.agronomo, self.iin.pk)
        self.assertEqual([i.codigo for i in impedimentos], ["stock_distinto_de_cero"])
        self.assertTrue(impedimentos[0].texto and impedimentos[0].como_resolver)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA_IIN).count(), 0)
        self.iin.refresh_from_db()
        self.assertTrue(self.iin.activo)

    def test_regla_2_los_impedimentos_para_la_ventana_exigen_los_mismos_permisos(self):
        """Mismas precondiciones a y b que la baja."""
        with self.assertRaises(PermissionDenied):
            iin_servicio.impedimentos_para_deshabilitar(self.otro, self.iin.pk)
        with self.assertRaises(PermissionDenied):
            iin_servicio.impedimentos_para_deshabilitar(crear_gerente(), self.iin.pk)

    # ---- postcondiciones y reglas ----

    def test_post_a_con_stock_cero_queda_inactivo(self):
        """Postcondición a: con stock cero y sin nada pendiente se deshabilita."""
        resultado = self.deshabilitar()
        self.iin.refresh_from_db()
        self.assertEqual(self.iin.estado_insumo_invernadero, "inactivo")
        self.assertEqual(resultado.pk, self.iin.pk)

    def test_post_a_con_lotes_agotados_si_se_deshabilita(self):
        """Precondición d: un lote en 0 no es stock."""
        lote(self.iin, 0, ingresada=5)
        self.deshabilitar()
        self.iin.refresh_from_db()
        self.assertFalse(self.iin.activo)

    def test_regla_1_conserva_sus_lotes_y_movimientos(self):
        """Regla 1: la deshabilitación es lógica; conserva lotes, movimientos e historial."""
        agotado = lote(self.iin, 0, ingresada=5)
        movimientos = MovimientoInsumo.objects.filter(lote_insumo=agotado).count()
        self.deshabilitar()
        self.assertTrue(LoteInsumo.objects.filter(pk=agotado.pk).exists())
        self.assertEqual(MovimientoInsumo.objects.filter(lote_insumo=agotado).count(), movimientos)
        verificar_invariantes(self.iin)

    def test_post_b_la_alerta_bajo_el_minimo_activa_se_resuelve_y_va_en_los_datos(self):
        """Postcondición b: si estaba activa, pasa a «resuelta» y figura en ``datos.alertas_resueltas``."""
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(cant_min_insumo=20)
        alerta = Alerta.objects.create(
            invernadero=self.norte, tipo_alerta=BAJO_MINIMO, descripcion_alerta="x", nivel_severidad="advertencia",
            agronomo=self.agronomo, clave_estado=f"insumo:{self.iin.pk}",
        )
        self.deshabilitar()
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        registro = RegistroAuditoria.objects.get(accion=BAJA_IIN)
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["alertas_resueltas"]], [alerta.pk])

    def test_post_c_audita_el_cambio_de_estado(self):
        """Postcondición c y D-36: usuario, insumo e invernadero afectados y el cambio de estado."""
        self.deshabilitar()
        registro = RegistroAuditoria.objects.get(accion=BAJA_IIN)
        self.assertEqual(registro.usuario_id, self.agronomo.pk)
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "activo", "despues": "inactivo"}})
        self.assertNotIn("datos", registro.detalle)
        self.assertEqual({a["id"] for a in registro.afectados if a["modelo"] == "maestros.invernadero"}, {self.norte.pk})

    def test_regla_3_volver_a_habilitar_reactiva_el_mismo_registro(self):
        """Regla 3: el insumo sigue en el catálogo y CMP-HAB-IIN reactiva el mismo registro."""
        self.deshabilitar()
        otra = perezoso("inventario.servicios.insumos_invernadero").habilitar_insumo(
            self.agronomo, self.insumo.pk, self.norte.pk, "5", "10"
        )
        self.assertEqual(otra.pk, self.iin.pk)
        self.assertTrue(otra.activo)

    def test_acciones_permitidas_segun_el_estado(self):
        """D-30: un activo se modifica, se deshabilita y se ajusta; uno deshabilitado no ofrece nada; el Gerente, nada."""
        activas = iin_servicio.acciones_permitidas(self.agronomo, self.iin)
        self.assertEqual(activas, frozenset({"modificar", "deshabilitar", "ajustar"}))
        self.assertEqual(iin_servicio.acciones_permitidas(crear_gerente(), self.iin), frozenset())
        self.assertEqual(iin_servicio.acciones_permitidas(self.otro, self.iin), frozenset())
        self.deshabilitar()
        self.iin.refresh_from_db()
        self.assertEqual(iin_servicio.acciones_permitidas(self.agronomo, self.iin), frozenset())


@tag("concurrencia")
class CmpDshIinConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de ``deshabilitar_insumo``: invernadero → existencia (docs/patrones/stock.md, sección 5)."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.agronomo = crear_agronomo()
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero Uno", agronomo=self.agronomo)
        self.iin = existencia(insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l"), self.invernadero)

    def test_pre_d_deshabilitar_espera_a_un_ajuste_que_carga_stock_y_se_rechaza(self):
        """Precondición d: quien carga stock bloquea el invernadero antes (contrato de D-40); deshabilitar espera, ve el lote y se
        rechaza con ``stock_distinto_de_cero``. Sin ese bloqueo se deshabilitaría un insumo con stock recién cargado."""
        resultados = correr_a_la_vez(
            lambda: ajuste_simulado(self.otro, self.iin, 5),
            lambda: iin_servicio.deshabilitar_insumo(self.agronomo, self.iin.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["stock_distinto_de_cero"])
        self.iin.refresh_from_db()
        self.assertTrue(self.iin.activo)

    def test_pre_c_dos_deshabilitaciones_a_la_vez_la_segunda_se_rechaza_sin_error_500(self):
        """Precondición c: la segunda espera, relee el registro ya inactivo y se rechaza con ``insumo_deshabilitado``."""
        resultados = correr_a_la_vez(
            lambda: iin_servicio.deshabilitar_insumo(self.agronomo, self.iin.pk),
            lambda: iin_servicio.deshabilitar_insumo(self.agronomo, self.iin.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["insumo_deshabilitado"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA_IIN).count(), 1)
