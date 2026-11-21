# Pruebas de CMP-BAJ-INS · Baja Insumo (docs/casos_de_uso/inventario/insumos.md). Cita D-28, D-36, D-40 y docs/api/alertas.md.
#
# Servicios que se prueban (inventario/servicios/insumos.py), tomados del módulo dentro de cada prueba:
#   baja_insumo(actor, insumo_id) -> Insumo
#     - Precondición a: Agrónomo activo. Precondición b y regla 1 de CMP-MOD-INS: puede gestionarlo (``insumo_en_uso_por_otros``).
#       Precondición c: está activo (``insumo_inactivo``) y no es una semilla (``insumo_semilla``; regla 3: se dan de baja con su variedad).
#     - Precondición d y regla 2: se juntan TODOS los impedimentos, invernadero por invernadero (stock distinto de cero, también el negativo;
#       reservas; cantidad en tránsito; y los de los registrantes de deshabilitación: orden de compra aprobada, pedido en curso). Un solo
#       ValidationError general con un error por impedimento (código = el del impedimento; texto «<invernadero>: <qué pasa> <cómo resolverlo>»).
#     - Postcondición a y b: el insumo y TODOS sus ``InsumoInvernadero`` pasan a inactivos. Regla 1: conserva lotes y movimientos.
#     - Postcondición c: un registro ``baja_insumo`` y uno ``baja_insumo_invernadero`` por cada habilitación que pasó a inactiva; la
#       alerta «bajo el mínimo» (clave ``insumo:<id>``) de cada una se resuelve y va en ``datos.alertas_resueltas``.
#   impedimentos_de_baja(actor, insumo_id) -> list[ImpedimentoDeBaja(invernadero, codigo, texto, como_resolver)]: los mismos, para la
#       ventana de confirmación (solo lectura; no bloquea ni audita).

from datetime import date
from decimal import Decimal

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase, TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.extensiones import OrdenQueReserva
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    ajuste_simulado,
    asegurar_datos_de_inventario,
    categoria_del_sistema,
    existencia,
    faltante,
    insumo,
    lote,
    perezoso,
    reservas_de_prueba,
    tipo_de_insumo,
)
from maestros.alertas import Destinatario
from maestros.extensiones import Impedimento
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.servicios import invernaderos as servicio_de_invernaderos
from maestros.tests.fabricas import (
    asegurar_datos_de_maestros,
    codigos_de,
    crear_agronomo,
    crear_invernadero,
    crear_invernadero_con_geografia_propia,
    error_de,
)

insumos = perezoso("inventario.servicios.insumos")
BAJA = RegistroAuditoria.Accion.BAJA_INSUMO
BAJA_IIN = RegistroAuditoria.Accion.BAJA_INSUMO_INVERNADERO
BAJO_MINIMO = "inv_insumo_bajo_minimo"


class CmpBajInsServicioTests(ConDatosDeInventario, TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-BAJ-INS."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Gómez")
        self.tipo = tipo_de_insumo("Limpieza")
        self.insumo = insumo("Detergente", tipo=self.tipo, unidad="l")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.agronomo)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.agronomo)

    def baja(self, actor=None, objetivo=None):
        return insumos.baja_insumo(actor or self.agronomo, (objetivo or self.insumo).pk)

    def textos(self, error):
        return " | ".join(error.messages)

    # ---- precondiciones ----

    def test_pre_a_gerente_capataz_y_administrador_no_dan_de_baja(self):
        """CMP-BAJ-INS precondición a: solo un Agrónomo activo."""
        for cuenta in (crear_gerente(), crear_capataz(), crear_administrador()):
            with self.subTest(rol=type(cuenta).__name__):
                with self.assertRaises(PermissionDenied):
                    self.baja(actor=cuenta)

    def test_pre_a_un_insumo_que_no_existe_da_404(self):
        """D-28: un id inexistente da 404."""
        with self.assertRaises(Http404):
            insumos.baja_insumo(self.agronomo, 999999)

    def test_pre_b_quien_no_gestiona_el_insumo_no_lo_da_de_baja(self):
        """CMP-BAJ-INS precondición b: la regla 1 de CMP-MOD-INS; informa quién lo usa (verificación a mano 8)."""
        ajeno = crear_agronomo(email="ajeno@infoponia.com", nombre="Luis", apellido="Paz")
        existencia(self.insumo, crear_invernadero("Invernadero Este", agronomo=ajeno))
        error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["insumo_en_uso_por_otros"])
        self.assertIn("Invernadero Este (Luis Paz)", error.messages[0])
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.estado_insumo, "activo")

    def test_pre_c_un_insumo_ya_inactivo_se_rechaza(self):
        """CMP-BAJ-INS precondición c: el insumo está activo."""
        viejo = insumo("Viejo", tipo=self.tipo, activo=False)
        self.assertEqual(codigos_de(error_de(lambda: self.baja(objetivo=viejo)), NON_FIELD_ERRORS), ["insumo_inactivo"])

    def test_pre_c_una_semilla_se_da_de_baja_junto_con_su_variedad_y_no_aca(self):
        """CMP-BAJ-INS precondición c y regla 3: ``insumo_semilla``."""
        semilla = insumo("Semilla Lechuga Crespa", tipo=categoria_del_sistema("semillas"), unidad="unidad")
        self.assertEqual(codigos_de(error_de(lambda: self.baja(objetivo=semilla)), NON_FIELD_ERRORS), ["insumo_semilla"])
        semilla.refresh_from_db()
        self.assertEqual(semilla.estado_insumo, "activo")

    # ---- precondición d y regla 2: los impedimentos ----

    def test_pre_d_con_stock_no_se_da_de_baja_y_dice_donde_y_como_resolverlo(self):
        """CMP-BAJ-INS precondición d y regla 2 (verificación a mano 9): el mensaje nombra el invernadero, la cantidad y cómo resolverlo."""
        lote(existencia(self.insumo, self.norte), "2.5")
        error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["stock_distinto_de_cero"])
        self.assertIn("Invernadero Norte", error.messages[0])
        self.assertIn("2.500", error.messages[0])
        self.assertIn("ajuste", error.messages[0])
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.estado_insumo, "activo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_pre_d_el_stock_negativo_tambien_impide_la_baja(self):
        """CMP-BAJ-INS regla 2: «el stock negativo también impide la baja»."""
        faltante(existencia(self.insumo, self.norte), 2)
        error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["stock_distinto_de_cero"])
        self.assertIn("negativo", error.messages[0])

    def test_pre_d_un_lote_vencido_con_stock_tambien_impide_la_baja(self):
        """CMP-BAJ-INS precondición d: stock distinto de cero, vencido o no."""
        lote(existencia(self.insumo, self.norte), 3, vence=date(2020, 1, 1))
        self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["stock_distinto_de_cero"])

    def test_pre_d_con_stock_cero_y_lotes_agotados_si_se_da_de_baja(self):
        """CMP-BAJ-INS precondición d: un lote en 0 se conserva pero no impide (stock cero)."""
        lote(existencia(self.insumo, self.norte), 0, ingresada=4)
        self.assertEqual(self.baja().estado_insumo, "inactivo")

    def test_pre_d_con_reservas_no_se_da_de_baja_y_nombra_las_ordenes(self):
        """CMP-BAJ-INS precondición d: reservas por órdenes a realizar (punto de extensión de `produccion`)."""
        iin = existencia(self.insumo, self.norte)
        orden = OrdenQueReserva(7, "Siembra 7", Decimal("2"), date(2026, 12, 1), "/o/7/")
        with reservas_de_prueba(reservado={iin.pk: 2}, ordenes={iin.pk: [orden]}):
            error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["reservas_activas"])
        self.assertIn("Concretá o cancelá", error.messages[0])

    def test_pre_d_con_cantidad_en_transito_no_se_da_de_baja(self):
        """CMP-BAJ-INS precondición d: mercadería en camino (la escribirá `compras`)."""
        existencia(self.insumo, self.norte, transito=3)
        self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["cantidad_en_transito"])

    def test_pre_d_y_e_los_impedimentos_de_compras_tambien_se_informan(self):
        """CMP-BAJ-INS precondiciones d y e: orden de compra aprobada y pedido en curso llegan por el punto de extensión."""
        iin = existencia(self.insumo, self.norte)
        de_compras = [
            Impedimento("orden_de_compra_aprobada", "Hay una orden de compra aprobada.", "Recibila o cerrala."),
            Impedimento("pedido_en_curso", "Está en un pedido en curso.", "Cerralo o quitale el insumo."),
        ]
        with reservas_de_prueba(impedimentos={iin.pk: de_compras}):
            error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["orden_de_compra_aprobada", "pedido_en_curso"])

    def test_regla_2_se_juntan_todos_los_impedimentos_de_todos_los_invernaderos_sin_quedarse_con_el_primero(self):
        """CMP-BAJ-INS regla 2: «invernadero por invernadero, todo lo que lo impide, cada cosa con cómo resolverla»."""
        norte = existencia(self.insumo, self.norte, transito=1)
        sur = existencia(self.insumo, self.sur)
        lote(norte, 4)
        faltante(sur, 1)
        error = error_de(self.baja)
        self.assertEqual(
            codigos_de(error, NON_FIELD_ERRORS), ["stock_distinto_de_cero", "cantidad_en_transito", "stock_distinto_de_cero"]
        )
        texto = self.textos(error)
        self.assertIn("Invernadero Norte", texto)
        self.assertIn("Invernadero Sur", texto)

    def test_regla_2_los_invernaderos_con_el_insumo_deshabilitado_no_aportan_impedimentos(self):
        """CMP-BAJ-INS regla 2: solo cuentan las habilitaciones activas."""
        lote(existencia(self.insumo, self.norte, activo=False), 4)
        self.assertEqual(self.baja().estado_insumo, "inactivo")

    def test_regla_2_impedimentos_de_baja_los_da_para_la_ventana_sin_cambiar_nada(self):
        """CMP-BAJ-INS regla 2: la pantalla pide la lista (invernadero, código, texto y cómo resolverlo); no bloquea, no cambia ni audita."""
        lote(existencia(self.insumo, self.norte), 4)
        lista = insumos.impedimentos_de_baja(self.agronomo, self.insumo.pk)
        self.assertEqual([(i.invernadero.nombre_invernadero, i.codigo) for i in lista], [("Invernadero Norte", "stock_distinto_de_cero")])
        self.assertTrue(lista[0].texto and lista[0].como_resolver)
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.estado_insumo, "activo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_regla_2_impedimentos_de_baja_exige_el_mismo_permiso_que_la_baja(self):
        """CMP-BAJ-INS precondiciones a, b y c también para la ventana de confirmación."""
        with self.assertRaises(PermissionDenied):
            insumos.impedimentos_de_baja(crear_gerente(), self.insumo.pk)
        with self.assertRaises(Http404):
            insumos.impedimentos_de_baja(self.agronomo, 999999)
        viejo = insumo("Viejo", tipo=self.tipo, activo=False)
        self.assertEqual(codigos_de(error_de(lambda: insumos.impedimentos_de_baja(self.agronomo, viejo.pk)), NON_FIELD_ERRORS), ["insumo_inactivo"])

    # ---- postcondiciones ----

    def test_post_a_el_insumo_queda_inactivo_y_conserva_sus_datos_lotes_y_movimientos(self):
        """CMP-BAJ-INS postcondición a y regla 1: baja lógica; no se borra nada."""
        iin = existencia(self.insumo, self.norte)
        agotado = lote(iin, 0, ingresada=4)
        movimientos = MovimientoInsumo.objects.filter(lote_insumo=agotado).count()
        self.baja()
        self.insumo.refresh_from_db()
        self.assertEqual((self.insumo.estado_insumo, self.insumo.nombre_insumo), ("inactivo", "Detergente"))
        self.assertEqual(LoteInsumo.objects.filter(insumo_invernadero=iin).count(), 1)
        self.assertEqual(MovimientoInsumo.objects.filter(lote_insumo=agotado).count(), movimientos)

    def test_post_a_el_insumo_dado_de_baja_solo_ofrece_reactivar(self):
        """CMP-BAJ-INS postcondición a: deja de ofrecerse (sus acciones pasan a ser solo «reactivar»)."""
        self.baja()
        self.insumo.refresh_from_db()
        self.assertEqual(insumos.acciones_permitidas(self.agronomo, self.insumo), {"reactivar"})

    def test_post_b_todas_las_habilitaciones_quedan_inactivas_en_todos_los_invernaderos(self):
        """CMP-BAJ-INS postcondición b: «todos los invernaderos donde estaba habilitado quedaron con el insumo deshabilitado»."""
        norte, sur = existencia(self.insumo, self.norte), existencia(self.insumo, self.sur)
        self.baja()
        self.assertEqual(
            sorted(InsumoInvernadero.objects.filter(insumo=self.insumo).values_list("estado_insumo_invernadero", flat=True)),
            ["inactivo", "inactivo"],
        )
        self.assertEqual(InsumoInvernadero.objects.filter(pk__in=[norte.pk, sur.pk]).count(), 2)

    def test_post_b_un_insumo_sin_habilitar_en_ningun_invernadero_se_da_de_baja(self):
        """CMP-BAJ-INS: sin habilitaciones, la baja solo cambia el insumo (un solo registro)."""
        self.baja()
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA_IIN).count(), 0)

    def test_post_c_audita_la_baja_del_insumo_y_una_por_cada_invernadero_donde_se_deshabilito(self):
        """CMP-BAJ-INS postcondición c y D-36 (verificación a mano 10): usuario, rol, insumo y cambio de estado, y otro registro por
        cada invernadero; las habilitaciones que ya estaban inactivas no generan registro."""
        norte = existencia(self.insumo, self.norte)
        sur = existencia(self.insumo, self.sur)
        existencia(self.insumo, crear_invernadero("Invernadero Este"), activo=False)
        self.baja()
        registro = RegistroAuditoria.objects.get(accion=BAJA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        self.assertEqual([a["id"] for a in registro.afectados], [self.insumo.pk])
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "activo", "despues": "inactivo"})
        por_invernadero = RegistroAuditoria.objects.filter(accion=BAJA_IIN)
        self.assertEqual(por_invernadero.count(), 2)
        afectados = {a["id"] for r in por_invernadero for a in r.afectados if a["modelo"] == "inventario.insumoinvernadero"}
        self.assertEqual(afectados, {norte.pk, sur.pk})
        for r in por_invernadero:
            self.assertEqual(r.detalle["cambios"]["estado"], {"antes": "activo", "despues": "inactivo"})
            self.assertIn("maestros.invernadero", [a["modelo"] for a in r.afectados])

    def test_post_c_resuelve_la_alerta_bajo_el_minimo_de_cada_habilitacion_y_la_registra(self):
        """CMP-BAJ-INS postcondición c y docs/api/alertas.md (sección 6): la alerta ``inv_insumo_bajo_minimo`` (clave ``insumo:<id>``)
        pasa a resuelta y va en ``datos.alertas_resueltas`` del registro de ese invernadero."""
        existencia(self.insumo, self.norte)
        alerta = api_alertas.asegurar_alerta_de_estado(self.norte.pk, BAJO_MINIMO, clave=f"insumo:{self.insumo.pk}")
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.ACTIVA)
        self.baja()
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.RESUELTA)
        registro = RegistroAuditoria.objects.get(accion=BAJA_IIN)
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["alertas_resueltas"]], [alerta.pk])

    def test_post_c_sin_alerta_no_hay_datos_de_alertas_en_el_registro(self):
        """docs/api/alertas.md sección 6: solo las claves que no estén vacías."""
        existencia(self.insumo, self.norte)
        self.baja()
        self.assertNotIn("datos", RegistroAuditoria.objects.get(accion=BAJA_IIN).detalle)

    def test_regla_4_se_reactiva_con_modificar_insumo_y_no_vuelve_a_habilitar(self):
        """CMP-BAJ-INS regla 4: se reactiva con ``reactivar_insumo`` (CMP-MOD-INS); las habilitaciones siguen inactivas."""
        iin = existencia(self.insumo, self.norte)
        self.baja()
        insumos.reactivar_insumo(self.agronomo, self.insumo.pk)
        iin.refresh_from_db()
        self.assertEqual(iin.estado_insumo_invernadero, "inactivo")

    def test_regla_2_un_error_no_cambia_nada_ni_audita_aunque_otro_invernadero_estuviera_bien(self):
        """Todo o nada: ningún invernadero se deshabilita si otro tiene un impedimento."""
        limpio = existencia(self.insumo, self.sur)
        lote(existencia(self.insumo, self.norte), 3)
        error_de(self.baja)
        limpio.refresh_from_db()
        self.assertEqual(limpio.estado_insumo_invernadero, "activo")
        self.assertEqual(RegistroAuditoria.objects.filter(accion__in=[BAJA, BAJA_IIN]).count(), 0)


@tag("concurrencia")
class CmpBajInsConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de ``baja_insumo`` (D-40; docs/patrones/stock.md sección 5: invernaderos → categoría → insumo → existencias). Hereda de
    ``ConDatosDeInventario`` y asegura los datos de inventario y de maestros en cada prueba (el ``flush`` los vacía); el
    invernadero se arma con su propia geografía por la misma razón."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.agronomo = crear_agronomo()
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.gerente = crear_gerente()
        self.tipo = tipo_de_insumo("Limpieza")
        self.insumo = insumo("Detergente", tipo=self.tipo, unidad="l")
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero Uno", agronomo=self.agronomo)
        self.existencia = existencia(self.insumo, self.invernadero)

    def test_pre_d_la_baja_espera_a_un_ajuste_que_carga_stock_y_se_rechaza(self):
        """CMP-BAJ-INS precondición d: quien carga stock bloquea el invernadero antes (contrato de D-40); la baja espera, ve el lote y
        se rechaza con ``stock_distinto_de_cero``. Sin ese bloqueo, el insumo se daría de baja con stock recién cargado."""
        resultados = correr_a_la_vez(
            lambda: ajuste_simulado(self.otro, self.existencia, 5),
            lambda: insumos.baja_insumo(self.agronomo, self.insumo.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["stock_distinto_de_cero"])
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.estado_insumo, "activo")

    def test_pre_d_el_ajuste_espera_a_la_baja_y_no_deja_stock_en_un_insumo_inactivo(self):
        """CMP-BAJ-INS postcondición a: si la baja va primera, quien carga stock espera el invernadero; la baja ya confirmó y el
        insumo quedó inactivo con sus habilitaciones inactivas (la baja no vio stock porque todavía no existía)."""
        resultados = correr_a_la_vez(
            lambda: insumos.baja_insumo(self.agronomo, self.insumo.pk),
            lambda: ajuste_simulado(self.otro, self.existencia, 5),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(rechazos), otros), (0, []))
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.estado_insumo, "inactivo")
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.existencia.pk).estado_insumo_invernadero, "inactivo")

    def test_regla_1_dos_bajas_a_la_vez_la_segunda_encuentra_el_insumo_inactivo(self):
        """CMP-BAJ-INS precondición c: la segunda espera, relee el insumo ya inactivo y se rechaza con ``insumo_inactivo``; un solo
        registro ``baja_insumo``."""
        resultados = correr_a_la_vez(
            lambda: insumos.baja_insumo(self.agronomo, self.insumo.pk),
            lambda: insumos.baja_insumo(self.agronomo, self.insumo.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["insumo_inactivo"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA).count(), 1)

    def test_post_b_la_baja_del_insumo_contra_la_baja_del_invernadero_no_se_traba_y_deja_todo_inactivo(self):
        """CMP-BAJ-INS: el mismo orden de bloqueos (invernadero antes que insumo) que la baja del invernadero evita el deadlock; las
        dos terminan y el insumo y su habilitación quedan inactivos. Sin esta tarea registrada en `maestros`, la baja del
        invernadero no ve la habilitación (INV-02 conecta ese impedimento)."""
        resultados = correr_a_la_vez(
            lambda: insumos.baja_insumo(self.agronomo, self.insumo.pk),
            lambda: servicio_de_invernaderos.baja_invernadero(self.gerente, self.invernadero.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.estado_insumo, "inactivo")
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.existencia.pk).estado_insumo_invernadero, "inactivo")

    def test_post_b_la_baja_del_invernadero_va_primera_y_la_baja_del_insumo_termina_igual(self):
        """CMP-BAJ-INS postcondición b: si la baja del invernadero va primera, la del insumo espera, relee el invernadero ya
        inactivo y deshabilita igual la habilitación (sin error 500)."""
        resultados = correr_a_la_vez(
            lambda: servicio_de_invernaderos.baja_invernadero(self.gerente, self.invernadero.pk),
            lambda: insumos.baja_insumo(self.agronomo, self.insumo.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.estado_insumo, "inactivo")
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.existencia.pk).estado_insumo_invernadero, "inactivo")
