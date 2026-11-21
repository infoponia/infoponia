# Pruebas de CMP-BAJ-TIN · Baja Tipo de Insumo (docs/casos_de_uso/inventario/tipos_de_insumo.md). Cita D-28, D-36 y D-40.
#
# Servicio que se prueba (inventario/servicios/tipos_de_insumo.py), tomado del módulo dentro de cada prueba:
#   baja_tipo_insumo(actor, tipo_id) -> TipoInsumo
#     - Precondición a: Agrónomo activo (cualquiera). Precondición b: la categoría está activa (``categoria_inactiva``) y no es del
#       sistema (``categoria_del_sistema``).
#     - Precondición c y regla 2: sin insumos ACTIVOS; si los tiene, ``insumos_activos`` (error general) y dice cuántos son. Los
#       inactivos no impiden la baja.
#     - Postcondición a y regla 1: baja lógica, conserva sus insumos inactivos. Postcondición b: un registro ``baja_tipo_insumo``.
#     - Regla 3: se reactiva con ``reactivar_tipo_insumo`` (CMP-MOD-TIN).
#   El cruce «baja de la categoría contra alta de un insumo» (que necesita ``alta_insumo``) está en test_cmp_alt_ins.py (paso 5).

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.db import transaction
from django.http import Http404
from django.test import TestCase, TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.models import Insumo, TipoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    asegurar_datos_de_inventario,
    categoria_del_sistema,
    insumo,
    perezoso,
    tipo_de_insumo,
)
from maestros.tests.fabricas import asegurar_datos_de_maestros, codigos_de, crear_agronomo, error_de

tipos = perezoso("inventario.servicios.tipos_de_insumo")
BAJA = RegistroAuditoria.Accion.BAJA_TIPO_INSUMO


class CmpBajTinServicioTests(ConDatosDeInventario, TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-BAJ-TIN."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.tipo = tipo_de_insumo("Limpieza")

    def baja(self, tipo=None, actor=None):
        return tipos.baja_tipo_insumo(actor or self.agronomo, (tipo or self.tipo).pk)

    # ---- precondiciones ----

    def test_pre_a_un_gerente_no_da_de_baja(self):
        """CMP-BAJ-TIN precondición a: solo un Agrónomo activo."""
        with self.assertRaises(PermissionDenied):
            self.baja(actor=crear_gerente())

    def test_pre_a_capataz_y_administrador_no_dan_de_baja(self):
        """CMP-BAJ-TIN precondición a: ningún otro rol."""
        for cuenta in (crear_capataz(), crear_administrador()):
            with self.subTest(rol=type(cuenta).__name__):
                with self.assertRaises(PermissionDenied):
                    self.baja(actor=cuenta)

    def test_pre_a_una_categoria_que_no_existe_da_404(self):
        """D-28: un id inexistente da 404."""
        with self.assertRaises(Http404):
            tipos.baja_tipo_insumo(self.agronomo, 999999)

    def test_pre_b_una_categoria_del_sistema_no_se_da_de_baja_aunque_se_pida(self):
        """CMP-BAJ-TIN precondición b: el servicio las rechaza con ``categoria_del_sistema`` (no alcanza con esconder el botón)."""
        for codigo in ("semillas", "envases", "repuestos_de_hardware", "infraestructura"):
            categoria = categoria_del_sistema(codigo)
            with self.subTest(codigo=codigo):
                error = error_de(lambda: self.baja(tipo=categoria))
                self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["categoria_del_sistema"])
                categoria.refresh_from_db()
                self.assertEqual(categoria.estado_tipo_insumo, "activo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_pre_b_una_categoria_ya_dada_de_baja_se_rechaza(self):
        """CMP-BAJ-TIN precondición b: la categoría está activa."""
        inactiva = tipo_de_insumo("Vieja", activo=False)
        error = error_de(lambda: self.baja(tipo=inactiva))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["categoria_inactiva"])

    # ---- precondición c y regla 2: insumos activos ----

    def test_pre_c_con_insumos_activos_no_se_da_de_baja_y_dice_cuantos_son(self):
        """CMP-BAJ-TIN precondición c y regla 2 (verificación a mano 7): informa cuántos insumos activos tiene y no cambia nada."""
        insumo("Detergente", tipo=self.tipo)
        insumo("Lavandina", tipo=self.tipo)
        error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["insumos_activos"])
        self.assertIn("2 insumos activos", error.messages[0])
        self.assertIn("Modificar", error.messages[0])  # «deben pasarse a otra categoría con Modificar Insumo»
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.estado_tipo_insumo, "activo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_pre_c_con_un_solo_insumo_activo_el_mensaje_va_en_singular(self):
        """Redacción: «1 insumo activo»."""
        insumo("Detergente", tipo=self.tipo)
        self.assertIn("1 insumo activo", error_de(self.baja).messages[0])

    def test_regla_2_los_insumos_inactivos_no_impiden_la_baja(self):
        """CMP-BAJ-TIN regla 2: «Los insumos inactivos no impiden la baja»."""
        insumo("Detergente", tipo=self.tipo, activo=False)
        self.assertEqual(self.baja().estado_tipo_insumo, "inactivo")

    def test_regla_2_los_insumos_de_otra_categoria_no_cuentan(self):
        """CMP-BAJ-TIN regla 2: los insumos se cuentan por categoría."""
        insumo("Nitrato", tipo=tipo_de_insumo("Nutrientes"))
        self.assertEqual(self.baja().estado_tipo_insumo, "inactivo")

    def test_regla_2_pasar_el_insumo_a_otra_categoria_permite_la_baja(self):
        """Verificación a mano 7: «Pasarlo a otra categoría (modificar) y volver a probar»."""
        un_insumo = insumo("Detergente", tipo=self.tipo)
        error_de(self.baja)
        un_insumo.tipo_insumo = tipo_de_insumo("Higiene")
        un_insumo.save()
        self.assertEqual(self.baja().estado_tipo_insumo, "inactivo")

    # ---- regla 1 y postcondiciones ----

    def test_regla_1_la_baja_es_logica_y_conserva_los_insumos_inactivos_y_el_nombre(self):
        """CMP-BAJ-TIN regla 1: la categoría conserva sus insumos inactivos y su historial."""
        viejo = insumo("Detergente", tipo=self.tipo, activo=False)
        self.baja()
        self.tipo.refresh_from_db()
        viejo.refresh_from_db()
        self.assertEqual((self.tipo.estado_tipo_insumo, self.tipo.nombre_tipo_insumo), ("inactivo", "Limpieza"))
        self.assertEqual(viejo.tipo_insumo_id, self.tipo.pk)

    def test_post_a_la_categoria_dada_de_baja_solo_ofrece_reactivar(self):
        """CMP-BAJ-TIN postcondición a: deja de ofrecerse (sus acciones pasan a ser solo «reactivar»)."""
        self.baja()
        self.tipo.refresh_from_db()
        self.assertEqual(tipos.acciones_permitidas(self.agronomo, self.tipo), {"reactivar"})

    def test_post_b_audita_la_baja_con_el_cambio_de_estado(self):
        """CMP-BAJ-TIN postcondición b y D-36: usuario, rol, categoría y el cambio de estado."""
        self.baja()
        registro = RegistroAuditoria.objects.get(accion=BAJA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        self.assertEqual([a["id"] for a in registro.afectados], [self.tipo.pk])
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "activo", "despues": "inactivo"})

    def test_regla_3_se_reactiva_con_modificar_tipo_de_insumo(self):
        """CMP-BAJ-TIN regla 3 y verificación a mano 4: se reactiva con ``reactivar_tipo_insumo`` (CMP-MOD-TIN)."""
        self.baja()
        self.assertEqual(tipos.reactivar_tipo_insumo(self.agronomo, self.tipo.pk).estado_tipo_insumo, "activo")


@tag("concurrencia")
class CmpBajTinConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de ``baja_tipo_insumo`` (D-40; docs/patrones/stock.md sección 5: ``TipoInsumo`` se toma con ``FOR NO KEY UPDATE``).
    Hereda de ``ConDatosDeInventario`` y asegura los datos en cada prueba: el ``flush`` de la anterior vacía las tablas."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.uno = crear_agronomo()
        self.otro = crear_agronomo(email="otro@infoponia.com")

    def test_pre_b_dos_bajas_a_la_vez_la_segunda_encuentra_la_categoria_inactiva(self):
        """CMP-BAJ-TIN precondición b: la segunda espera el bloqueo, relee la categoría ya inactiva y se rechaza con
        ``categoria_inactiva`` (sin 500 y con un solo registro de auditoría)."""
        tipo = tipo_de_insumo("Limpieza")
        resultados = correr_a_la_vez(
            lambda: tipos.baja_tipo_insumo(self.uno, tipo.pk),
            lambda: tipos.baja_tipo_insumo(self.otro, tipo.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["categoria_inactiva"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA).count(), 1)

    def test_pre_c_la_baja_espera_a_un_insumo_que_se_esta_pasando_a_la_categoria(self):
        """CMP-BAJ-TIN precondición c: quien agrega un insumo activo a la categoría la bloquea ANTES (``TipoInsumo`` → ``Insumo``);
        la baja espera, lo ve y se rechaza con ``insumos_activos``. Se simula con un cambio de categoría dentro de una transacción
        que toma el mismo bloqueo, como lo hace ``modificar_insumo`` (paso 5)."""
        tipo = tipo_de_insumo("Limpieza")
        un_insumo = insumo("Detergente", tipo=tipo_de_insumo("Higiene"))

        def pasar_el_insumo():
            with transaction.atomic():
                TipoInsumo.objects.select_for_update(no_key=True).get(pk=tipo.pk)
                Insumo.objects.filter(pk=un_insumo.pk).update(tipo_insumo=tipo)
                RegistroAuditoria.objects.registrar(
                    usuario=self.otro,
                    accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO,
                    afectados=[un_insumo],
                    detalle={"cambios": {"nombre": {"antes": "a", "despues": "b"}}},
                )

        resultados = correr_a_la_vez(
            pasar_el_insumo,
            lambda: tipos.baja_tipo_insumo(self.uno, tipo.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(rechazos), otros), (1, []))
        self.assertEqual(codigos(rechazos[0]), ["insumos_activos"])
        tipo.refresh_from_db()
        self.assertEqual(tipo.estado_tipo_insumo, "activo")
