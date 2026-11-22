# Pruebas de la conexión de `inventario` con la baja del invernadero (INV-02, paso 4; disparador «Cuando exista InsumoInvernadero»;
# docs/api/extensiones_de_inventario.md, «Lo que inventario registra en maestros»; PROD-BAJ-INV precondición f y postcondición c).
#
# Funciones que se prueban (inventario/servicios/insumos_invernadero.py), tomadas del módulo dentro de cada prueba y registradas en
# ``InventarioConfig.ready()`` con ``maestros.extensiones``:
#   impedimentos_de_baja_de_invernadero(invernadero) -> list[Impedimento]
#     Por cada ``InsumoInvernadero`` ACTIVO del invernadero, en orden de id: stock distinto de cero (``stock_distinto_de_cero``, también
#     el negativo), cantidad en tránsito (``cantidad_en_transito``) y los de los registrantes de ``registrar_impedimento_de_deshabilitacion``
#     (``compras``). NO incluye las reservas (``reservas_activas``): las órdenes que reservan son impedimento de `produccion`.
#   efecto_de_baja_de_invernadero(actor, invernadero)
#     Pasa a inactivos los ``InsumoInvernadero`` activos (en orden de id), con un ``baja_insumo_invernadero`` por cada uno, y resuelve las
#     alertas activas de ese insumo en el invernadero (van en ``datos.alertas_resueltas``). Conserva lotes y movimientos.
# Se prueban también a través de ``baja_invernadero`` y ``reactivar_invernadero`` reales (regla 6: la reactivación no reactiva los insumos).

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
from maestros import extensiones as extensiones_de_maestros
from maestros.extensiones import Impedimento
from maestros.models import Alerta
from maestros.servicios import invernaderos as servicio_de_invernaderos
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
BAJA_INV = RegistroAuditoria.Accion.BAJA_INVERNADERO
BAJO_MINIMO = "inv_insumo_bajo_minimo"


class ConexionConLaBajaDelInvernaderoTests(ConDatosDeInventario, TestCase):
    """Las dos funciones, directo y a través de ``baja_invernadero``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.agronomo)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.agronomo)
        tipo = tipo_de_insumo("Nutrientes")
        self.a = insumo("Nutriente A", tipo=tipo, unidad="l", controla_vencimiento=True)
        self.b = insumo("Bolsas", tipo=tipo, unidad="unidad")
        self.iin_a = existencia(self.a, self.norte, minimo=0)
        self.iin_b = existencia(self.b, self.norte, minimo=0)

    def impedimentos(self, invernadero=None):
        return iin_servicio.impedimentos_de_baja_de_invernadero(invernadero or self.norte)

    def baja(self, invernadero=None):
        return servicio_de_invernaderos.baja_invernadero(self.gerente, (invernadero or self.norte).pk)

    # ---- registro en maestros ----

    def test_los_dos_hooks_estan_registrados_en_maestros(self):
        """Disparador «Cuando exista InsumoInvernadero»: ``ready()`` los registra en los puntos de `maestros`."""
        self.assertIn(iin_servicio.impedimentos_de_baja_de_invernadero, extensiones_de_maestros._IMPEDIMENTOS)
        self.assertIn(iin_servicio.efecto_de_baja_de_invernadero, extensiones_de_maestros._EFECTOS_DE_BAJA)

    # ---- impedimentos_de_baja_de_invernadero ----

    def test_pre_f_sin_stock_ni_transito_no_hay_impedimentos(self):
        """Precondición f: con todo en 0 no impide nada (un lote agotado no es stock)."""
        lote(self.iin_a, 0, ingresada=5)
        self.assertEqual(self.impedimentos(), [])

    def test_pre_f_un_invernadero_sin_insumos_no_tiene_impedimentos(self):
        """Sin existencias no hay nada que impida."""
        self.assertEqual(self.impedimentos(self.sur), [])

    def test_pre_f_el_stock_distinto_de_cero_impide_y_nombra_el_insumo(self):
        """Precondición f: stock distinto de cero, con su texto y cómo resolverlo."""
        lote(self.iin_a, 5)
        [impedimento] = self.impedimentos()
        self.assertEqual(impedimento.codigo, "stock_distinto_de_cero")
        self.assertIn("Nutriente A", impedimento.texto)
        self.assertTrue(impedimento.como_resolver)

    def test_pre_f_el_stock_negativo_tambien_impide(self):
        """«Distinto de cero»: el faltante sin lote cuenta."""
        faltante(self.iin_b, 2)
        self.assertEqual([i.codigo for i in self.impedimentos()], ["stock_distinto_de_cero"])

    def test_pre_f_la_cantidad_en_transito_impide(self):
        """Precondición f: cantidad en tránsito."""
        InsumoInvernadero.objects.filter(pk=self.iin_a.pk).update(cant_transito_insumo=3)
        self.assertEqual([i.codigo for i in self.impedimentos()], ["cantidad_en_transito"])

    def test_pre_f_los_impedimentos_de_compras_se_suman(self):
        """Registrantes de deshabilitación (orden de compra aprobada, pedido en curso): se informan también."""
        falso = Impedimento("pedido_en_curso", "Está en un pedido en curso.", "Cerralo.")
        with reservas_de_prueba(impedimentos={self.iin_a.pk: [falso]}):
            self.assertEqual([i.codigo for i in self.impedimentos()], ["pedido_en_curso"])

    def test_pre_f_se_juntan_los_impedimentos_de_todos_los_insumos_en_orden_de_id(self):
        """Regla 2 de PROD-BAJ-INV: todos juntos, insumo por insumo en orden de id, sin quedarse con el primero."""
        lote(self.iin_a, 5)
        InsumoInvernadero.objects.filter(pk=self.iin_b.pk).update(cant_transito_insumo=2)
        faltante(self.iin_b, 1)
        self.assertEqual(
            [i.codigo for i in self.impedimentos()],
            ["stock_distinto_de_cero", "stock_distinto_de_cero", "cantidad_en_transito"],
        )
        textos = [i.texto for i in self.impedimentos()]
        self.assertIn("Nutriente A", textos[0])
        self.assertIn("Bolsas", textos[1])

    def test_pre_f_un_insumo_deshabilitado_no_aporta_impedimentos(self):
        """Solo cuentan los ``InsumoInvernadero`` activos."""
        InsumoInvernadero.objects.filter(pk=self.iin_b.pk).update(estado_insumo_invernadero="inactivo", cant_transito_insumo=9)
        self.assertEqual(self.impedimentos(), [])

    def test_pre_f_los_insumos_de_otro_invernadero_no_se_mezclan(self):
        """El alcance es el invernadero que se da de baja."""
        otro = existencia(self.a, self.sur)
        lote(otro, 50)
        self.assertEqual(self.impedimentos(self.norte), [])
        self.assertEqual(len(self.impedimentos(self.sur)), 1)

    def test_pre_f_las_reservas_no_se_duplican_con_las_de_produccion(self):
        """Solo reservas, sin stock: `produccion` informa las órdenes que reservan como su propio impedimento; `inventario` no las
        repite con ``reservas_activas``."""
        with reservas_de_prueba(reservado={self.iin_a.pk: "4"}):
            self.assertEqual(self.impedimentos(), [])

    def test_pre_f_con_stock_y_reservas_el_stock_figura_una_sola_vez(self):
        """El stock aparece una vez y las reservas no se suman como impedimento."""
        lote(self.iin_a, 5)
        with reservas_de_prueba(reservado={self.iin_a.pk: "4"}):
            self.assertEqual([i.codigo for i in self.impedimentos()], ["stock_distinto_de_cero"])

    # ---- precondición f a través de baja_invernadero ----

    def test_pre_f_baja_invernadero_se_rechaza_con_stock_y_no_cambia_nada(self):
        """PROD-BAJ-INV precondición f con ``baja_invernadero`` real: se rechaza, informa y no cambia nada."""
        lote(self.iin_a, 5)
        error = error_de(self.baja)
        self.assertEqual(codigos_de(error), ["stock_distinto_de_cero"])
        self.assertIn("Nutriente A", " ".join(error.messages))
        self.norte.refresh_from_db()
        self.iin_a.refresh_from_db()
        self.assertEqual((self.norte.estado_invernadero, self.iin_a.estado_insumo_invernadero), ("activo", "activo"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion__in=[BAJA_INV, BAJA_IIN]).count(), 0)

    def test_pre_f_baja_invernadero_informa_todos_los_impedimentos_juntos(self):
        """Regla 2 de PROD-BAJ-INV: stock de uno, tránsito de otro y un pedido en curso, todos en el mismo rechazo."""
        lote(self.iin_a, 5)
        InsumoInvernadero.objects.filter(pk=self.iin_b.pk).update(cant_transito_insumo=2)
        falso = Impedimento("pedido_en_curso", "Está en un pedido en curso.", "Cerralo.")
        with reservas_de_prueba(impedimentos={self.iin_a.pk: [falso]}):
            error = error_de(self.baja)
        self.assertEqual(
            sorted(codigos_de(error)), sorted(["stock_distinto_de_cero", "pedido_en_curso", "cantidad_en_transito"])
        )

    # ---- efecto_de_baja_de_invernadero ----

    def efecto(self, invernadero=None):
        return iin_servicio.efecto_de_baja_de_invernadero(self.agronomo, invernadero or self.norte)

    def test_post_c_pasa_a_inactivos_los_insumos_del_invernadero_y_solo_los_de_el(self):
        """Postcondición c: los activos de ese invernadero pasan a inactivos; los de otro invernadero, no."""
        ajeno = existencia(self.a, self.sur)
        self.efecto()
        self.assertEqual(
            set(InsumoInvernadero.objects.filter(invernadero=self.norte).values_list("estado_insumo_invernadero", flat=True)),
            {"inactivo"},
        )
        ajeno.refresh_from_db()
        self.assertTrue(ajeno.activo)

    def test_post_c_audita_un_baja_insumo_invernadero_por_cada_insumo_en_orden_de_id(self):
        """Postcondición c y D-36: un registro por insumo, en orden de id, con el cambio de estado, el actor y el invernadero."""
        self.efecto()
        registros = list(RegistroAuditoria.objects.filter(accion=BAJA_IIN).order_by("id"))
        self.assertEqual(len(registros), 2)
        afectados = [next(a["id"] for a in r.afectados if a["modelo"] == "inventario.insumoinvernadero") for r in registros]
        self.assertEqual(afectados, sorted([self.iin_a.pk, self.iin_b.pk]))
        for registro in registros:
            self.assertEqual(registro.usuario_id, self.agronomo.pk)
            self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "activo", "despues": "inactivo"}})
            self.assertIn(self.norte.pk, [a["id"] for a in registro.afectados if a["modelo"] == "maestros.invernadero"])

    def test_post_c_un_insumo_ya_deshabilitado_no_cambia_ni_se_audita(self):
        """Solo los activos: uno ya inactivo no genera registro."""
        InsumoInvernadero.objects.filter(pk=self.iin_b.pk).update(estado_insumo_invernadero="inactivo")
        self.efecto()
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA_IIN).count(), 1)

    def test_post_c_un_invernadero_sin_insumos_no_audita_nada(self):
        """Sin existencias, sin registros."""
        self.efecto(self.sur)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA_IIN).count(), 0)

    def test_post_c_conserva_los_lotes_y_los_movimientos(self):
        """Regla 1 de CMP-DSH-IIN: la baja es lógica; conserva lotes y movimientos."""
        agotado = lote(self.iin_a, 0, ingresada=5)
        movimientos = MovimientoInsumo.objects.count()
        self.efecto()
        self.assertTrue(LoteInsumo.objects.filter(pk=agotado.pk).exists())
        self.assertEqual(MovimientoInsumo.objects.count(), movimientos)
        verificar_invariantes(self.iin_a)

    def test_post_c_resuelve_las_alertas_activas_del_insumo_en_ese_invernadero(self):
        """Pedido del estudiante: al deshabilitar por la baja del invernadero también se resuelven las alertas activas del insumo;
        van en ``datos.alertas_resueltas`` del registro de ese insumo."""
        InsumoInvernadero.objects.filter(pk=self.iin_a.pk).update(cant_min_insumo=20)
        propia = Alerta.objects.create(
            invernadero=self.norte, tipo_alerta=BAJO_MINIMO, descripcion_alerta="x", nivel_severidad="advertencia",
            agronomo=self.agronomo, clave_estado=f"insumo:{self.iin_a.pk}",
        )
        de_b = Alerta.objects.create(
            invernadero=self.norte, tipo_alerta=BAJO_MINIMO, descripcion_alerta="y", nivel_severidad="advertencia",
            agronomo=self.agronomo, clave_estado=f"insumo:{self.iin_b.pk}",
        )
        ajena = Alerta.objects.create(
            invernadero=self.sur, tipo_alerta=BAJO_MINIMO, descripcion_alerta="z", nivel_severidad="advertencia",
            agronomo=self.agronomo, clave_estado=f"insumo:{self.iin_a.pk}",
        )
        self.efecto()
        for alerta in (propia, de_b, ajena):
            alerta.refresh_from_db()
        self.assertEqual((propia.estado_alerta, de_b.estado_alerta, ajena.estado_alerta), ("resuelta", "resuelta", "activa"))
        registro_a = next(
            r for r in RegistroAuditoria.objects.filter(accion=BAJA_IIN) if self.iin_a.pk in [a["id"] for a in r.afectados if a["modelo"] == "inventario.insumoinvernadero"]
        )
        self.assertEqual([r["id"] for r in registro_a.detalle["datos"]["alertas_resueltas"]], [propia.pk])

    # ---- postcondición c a través de baja_invernadero ----

    def test_post_c_baja_invernadero_con_todo_en_cero_pasa_los_insumos_a_inactivos(self):
        """PROD-BAJ-INV postcondiciones b y c con ``baja_invernadero`` real."""
        self.baja()
        self.norte.refresh_from_db()
        self.assertEqual(self.norte.estado_invernadero, "inactivo")
        self.assertEqual(
            set(InsumoInvernadero.objects.filter(invernadero=self.norte).values_list("estado_insumo_invernadero", flat=True)),
            {"inactivo"},
        )
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA_IIN).count(), 2)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA_INV).count(), 1)

    def test_post_c_baja_invernadero_deja_los_insumos_de_otros_invernaderos_como_estaban(self):
        """El efecto es solo del invernadero dado de baja."""
        otro = existencia(self.a, self.sur)
        self.baja()
        otro.refresh_from_db()
        self.assertTrue(otro.activo)

    def test_regla_6_reactivar_el_invernadero_no_reactiva_los_insumos(self):
        """Regla 6 de PROD-BAJ-INV: los reactiva el Agrónomo con Habilitar Insumo en Invernadero."""
        self.baja()
        servicio_de_invernaderos.reactivar_invernadero(self.gerente, self.norte.pk)
        self.assertEqual(
            set(InsumoInvernadero.objects.filter(invernadero=self.norte).values_list("estado_insumo_invernadero", flat=True)),
            {"inactivo"},
        )

    def test_regla_5_habilitar_de_nuevo_reactiva_el_mismo_registro_despues_de_la_baja_y_la_reactivacion(self):
        """Habilitar reactiva el mismo registro con su historial."""
        self.baja()
        servicio_de_invernaderos.reactivar_invernadero(self.gerente, self.norte.pk)
        de_nuevo = iin_servicio.habilitar_insumo(self.agronomo, self.a.pk, self.norte.pk, "5", "10")
        self.assertEqual(de_nuevo.pk, self.iin_a.pk)


@tag("concurrencia")
class ConexionConLaBajaConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Contrato de D-40 con la baja del invernadero real: quien carga stock o habilita bloquea el invernadero antes."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero Uno", agronomo=self.agronomo)
        self.insumo = insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l")
        self.iin = existencia(self.insumo, self.invernadero)

    def baja(self):
        return servicio_de_invernaderos.baja_invernadero(self.gerente, self.invernadero.pk)

    def test_pre_f_un_ajuste_que_carga_stock_primero_hace_que_la_baja_se_rechace(self):
        """Quien carga stock bloquea el invernadero; la baja espera, ve el lote y se rechaza con ``stock_distinto_de_cero``."""
        resultados = correr_a_la_vez(lambda: ajuste_simulado(self.otro, self.iin, 5), self.baja, primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["stock_distinto_de_cero"])
        self.invernadero.refresh_from_db()
        self.assertEqual(self.invernadero.estado_invernadero, "activo")

    def test_pre_f_la_baja_primero_hace_que_el_ajuste_se_rechace_y_no_deja_stock_en_un_invernadero_inactivo(self):
        """Con la baja primero, quien carga stock espera, encuentra el invernadero inactivo y se rechaza."""
        resultados = correr_a_la_vez(self.baja, lambda: ajuste_simulado(self.otro, self.iin, 5), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["invernadero_inactivo"])
        self.assertEqual(LoteInsumo.objects.count(), 0)

    def test_post_c_habilitar_primero_y_la_baja_despues_deja_el_insumo_nuevo_inactivo(self):
        """Habilitar un insumo (stock 0) y darse de baja el invernadero a la vez: la baja espera, ve la existencia nueva y la pasa a
        inactiva. Nunca queda una existencia activa en un invernadero inactivo."""
        otro_insumo = insumo("Bolsas", tipo=tipo_de_insumo("Envasado"), unidad="unidad")
        resultados = correr_a_la_vez(
            lambda: iin_servicio.habilitar_insumo(self.agronomo, otro_insumo.pk, self.invernadero.pk, "2", "10"),
            self.baja,
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(InsumoInvernadero.objects.filter(invernadero=self.invernadero, estado_insumo_invernadero="activo").count(), 0)
        self.assertEqual(InsumoInvernadero.objects.filter(invernadero=self.invernadero).count(), 2)
