# Pruebas de CMP-MOD-IIN · Modificar Insumo en Invernadero (docs/casos_de_uso/inventario/insumo_invernadero.md; INV-02, paso 3).
#
# Servicio que se prueba (inventario/servicios/insumos_invernadero.py), tomado del módulo dentro de cada prueba:
#   modificar_insumo_invernadero(actor, iin_id, *, cant_min, referencia_precio) -> InsumoInvernadero
#     - Precondición a: Agrónomo activo. Precondición b: invernadero activo y a cargo del actor (PermissionDenied si es ajeno;
#       ``invernadero_inactivo``). Precondición c y regla 4: el insumo está habilitado (``insumo_deshabilitado``).
#     - Regla 1: solo el mínimo y el precio, validados como en CMP-HAB-IIN (errores juntos, por campo).
#     - Regla 2: el precio nuevo no cambia lo ya registrado (lotes y movimientos).
#     - Postcondición a: se actualizan el mínimo, el precio o los dos. Postcondición b: si cambió el MÍNIMO se reevalúa «bajo el
#       mínimo» (crea o resuelve). Postcondición c y D-28/D-36: ``modificacion_insumo_invernadero`` con antes y después (Decimal como
#       texto); sin cambios no se escribe ni se audita.

from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase, TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from inventario.models import LoteInsumo, MovimientoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    asegurar_datos_de_inventario,
    existencia,
    insumo,
    lote,
    perezoso,
    tipo_de_insumo,
)
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
MODIFICACION = RegistroAuditoria.Accion.MODIFICACION_INSUMO_INVERNADERO
BAJO_MINIMO = "inv_insumo_bajo_minimo"


class CmpModIinServicioTests(ConDatosDeInventario, TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-MOD-IIN."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Gómez")
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.insumo = insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.agronomo)
        self.iin = existencia(self.insumo, self.norte, minimo=20, precio="1500")

    def modificar(self, actor=None, objetivo=None, minimo="20", precio="1500"):
        return iin_servicio.modificar_insumo_invernadero(
            actor or self.agronomo, (objetivo or self.iin).pk, cant_min=minimo, referencia_precio=precio
        )

    # ---- precondiciones ----

    def test_pre_a_el_gerente_no_modifica(self):
        """Precondición a: solo el Agrónomo."""
        with self.assertRaises(PermissionDenied):
            self.modificar(crear_gerente())

    def test_pre_b_un_invernadero_ajeno_da_permiso_denegado(self):
        """Precondición b: a cargo del actor."""
        with self.assertRaises(PermissionDenied):
            self.modificar(self.otro, minimo="30")

    def test_pre_b_un_invernadero_inactivo_se_rechaza(self):
        """Precondición b: invernadero activo."""
        self.norte.estado_invernadero = "inactivo"
        self.norte.save(update_fields=["estado_invernadero"])
        error = error_de(lambda: self.modificar(minimo="30"))
        self.assertEqual(codigos_de(error), ["invernadero_inactivo"])

    def test_pre_c_y_regla_4_un_insumo_deshabilitado_no_se_modifica(self):
        """Precondición c y regla 4: se vuelve a habilitar con CMP-HAB-IIN."""
        self.iin.estado_insumo_invernadero = "inactivo"
        self.iin.save(update_fields=["estado_insumo_invernadero"])
        error = error_de(lambda: self.modificar(minimo="30"))
        self.assertEqual(codigos_de(error), ["insumo_deshabilitado"])

    def test_pre_c_un_id_inexistente_da_404(self):
        """Id inexistente: 404 (D-28)."""
        with self.assertRaises(Http404):
            iin_servicio.modificar_insumo_invernadero(self.agronomo, 999999, cant_min="1", referencia_precio="1")

    # ---- reglas ----

    def test_regla_1_se_validan_el_minimo_y_el_precio_como_en_la_habilitacion(self):
        """Regla 1: reglas 3 y 4 de CMP-HAB-IIN, con todos los errores juntos."""
        error = error_de(lambda: self.modificar(minimo="-2", precio="0"))
        self.assertEqual(codigos_de(error, "cant_min"), ["minimo_negativo"])
        self.assertEqual(codigos_de(error, "referencia_precio"), ["precio_invalido"])
        error = error_de(lambda: self.modificar(minimo="1.5555", precio="10"))
        self.assertEqual(codigos_de(error, "cant_min"), ["decimales_de_la_unidad"])

    def test_regla_1_un_error_no_cambia_nada(self):
        """Todo o nada: con un campo inválido tampoco se guarda el otro."""
        error_de(lambda: self.modificar(minimo="40", precio="0"))
        self.iin.refresh_from_db()
        self.assertEqual((self.iin.cant_min_insumo, self.iin.referencia_precio), (Decimal("20"), Decimal("1500")))

    def test_regla_2_el_precio_nuevo_no_cambia_lo_ya_registrado(self):
        """Regla 2: lotes y movimientos quedan como estaban."""
        lote(self.iin, 10)
        antes = (LoteInsumo.objects.count(), MovimientoInsumo.objects.count(), LoteInsumo.objects.get().cantidad_disponible)
        self.modificar(precio="2500")
        despues = (LoteInsumo.objects.count(), MovimientoInsumo.objects.count(), LoteInsumo.objects.get().cantidad_disponible)
        self.assertEqual(antes, despues)

    # ---- postcondiciones ----

    def test_post_a_actualiza_el_minimo_el_precio_o_los_dos(self):
        """Postcondición a."""
        self.modificar(minimo="30", precio="1500")
        self.iin.refresh_from_db()
        self.assertEqual((self.iin.cant_min_insumo, self.iin.referencia_precio), (Decimal("30"), Decimal("1500")))
        self.modificar(minimo="30", precio="1800.50")
        self.iin.refresh_from_db()
        self.assertEqual((self.iin.cant_min_insumo, self.iin.referencia_precio), (Decimal("30"), Decimal("1800.50")))
        self.modificar(minimo="5", precio="900")
        self.iin.refresh_from_db()
        self.assertEqual((self.iin.cant_min_insumo, self.iin.referencia_precio), (Decimal("5"), Decimal("900")))

    def test_post_b_subir_el_minimo_por_encima_del_stock_genera_la_alerta(self):
        """Postcondición b: si el insumo quedó bajo el mínimo, se genera la alerta para el Agrónomo."""
        lote(self.iin, 25)
        self.modificar(minimo="30")
        alerta = Alerta.objects.get(tipo_alerta=BAJO_MINIMO)
        self.assertEqual((alerta.clave_estado, alerta.agronomo_id), (f"insumo:{self.iin.pk}", self.agronomo.pk))

    def test_post_b_no_duplica_una_alerta_activa(self):
        """Postcondición b: «salvo que ya hubiera una activa»."""
        self.modificar(minimo="30")
        self.modificar(minimo="40")
        self.assertEqual(Alerta.objects.filter(tipo_alerta=BAJO_MINIMO, estado_alerta="activa").count(), 1)

    def test_post_b_bajar_el_minimo_resuelve_la_alerta_activa(self):
        """Postcondición b: si dejó de estar bajo el mínimo, la alerta activa pasa a «resuelta»."""
        lote(self.iin, 25)
        self.modificar(minimo="30")
        self.modificar(minimo="10")
        alerta = Alerta.objects.get(tipo_alerta=BAJO_MINIMO)
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertIsNotNone(alerta.fecha_resolucion)

    def test_post_b_cambiar_solo_el_precio_no_reevalua_las_alertas(self):
        """Postcondición b: solo si cambió el stock mínimo."""
        self.assertEqual(Alerta.objects.filter(tipo_alerta=BAJO_MINIMO).count(), 0)
        self.modificar(precio="2000")
        self.assertEqual(Alerta.objects.filter(tipo_alerta=BAJO_MINIMO).count(), 0)

    def test_post_c_audita_antes_y_despues_con_los_decimales_como_texto(self):
        """Postcondición c y D-36: un registro con los cambios, antes y después, como texto."""
        self.modificar(minimo="30", precio="1750.5")
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual(registro.usuario_id, self.agronomo.pk)
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "cant_min_insumo": {"antes": "20.000", "despues": "30.000"},
                "referencia_precio": {"antes": "1500.00", "despues": "1750.50"},
            },
        )

    def test_post_c_solo_figura_lo_que_cambio(self):
        """D-28: el detalle lleva solo los campos que cambiaron."""
        self.modificar(minimo="20", precio="1600")
        cambios = RegistroAuditoria.objects.get(accion=MODIFICACION).detalle["cambios"]
        self.assertEqual(list(cambios), ["referencia_precio"])

    def test_d28_sin_cambios_no_se_escribe_ni_se_audita(self):
        """D-28: una modificación sin cambios no guarda ni audita, y devuelve la existencia."""
        resultado = self.modificar(minimo="20", precio="1500.00")
        self.assertEqual(resultado.pk, self.iin.pk)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=MODIFICACION).count(), 0)

    def test_post_b_y_c_la_alerta_creada_o_resuelta_va_en_los_datos_del_registro(self):
        """docs/api/alertas.md, «Auditoría»."""
        lote(self.iin, 25)
        self.modificar(minimo="30")
        alerta = Alerta.objects.get(tipo_alerta=BAJO_MINIMO)
        registro = RegistroAuditoria.objects.filter(accion=MODIFICACION).latest("id")
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["alertas_creadas"]], [alerta.pk])
        self.modificar(minimo="1")
        registro = RegistroAuditoria.objects.filter(accion=MODIFICACION).latest("id")
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["alertas_resueltas"]], [alerta.pk])


@tag("concurrencia")
class CmpModIinConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Dos modificaciones a la vez: gana la última (como ``modificar_usuario``; D-40)."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero Uno", agronomo=self.agronomo)
        self.iin = existencia(insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l"), self.invernadero, minimo=20)

    def test_post_c_dos_modificaciones_simultaneas_el_antes_de_la_segunda_es_el_despues_de_la_primera(self):
        """La segunda espera el bloqueo y calcula sus cambios contra lo que dejó la primera: nada se pisa en silencio ni da 500."""
        resultados = correr_a_la_vez(
            lambda: iin_servicio.modificar_insumo_invernadero(self.agronomo, self.iin.pk, cant_min="30", referencia_precio="10"),
            lambda: iin_servicio.modificar_insumo_invernadero(self.agronomo, self.iin.pk, cant_min="40", referencia_precio="10"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.iin.refresh_from_db()
        self.assertEqual(self.iin.cant_min_insumo, Decimal("40"))
        antes_y_despues = [
            r.detalle["cambios"]["cant_min_insumo"] for r in RegistroAuditoria.objects.filter(accion=MODIFICACION).order_by("id")
        ]
        self.assertEqual(antes_y_despues[0]["despues"], antes_y_despues[1]["antes"])
