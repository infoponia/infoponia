# Pruebas de CMP-HAB-IIN · Habilitar Insumo en Invernadero (docs/casos_de_uso/inventario/insumo_invernadero.md; INV-02, paso 3).
#
# Servicio que se prueba (inventario/servicios/insumos_invernadero.py), tomado del módulo dentro de cada prueba:
#   habilitar_insumo(actor, insumo_id, invernadero_id, cant_min, referencia_precio) -> InsumoInvernadero
#     - Precondición a: Agrónomo activo (el Gerente no gestiona insumos: PermissionDenied). Precondición b: invernadero activo
#       (``invernadero_inactivo``) y a cargo del actor (PermissionDenied). Precondición c: insumo activo (``insumo_inactivo``).
#       Precondición d: no habilitado ya (``ya_habilitado``).
#     - Regla 3: ``cant_min`` obligatoria, cero o más, con los decimales de la unidad. Regla 4: ``referencia_precio`` obligatoria y > 0,
#       con 2 decimales. Todos los errores juntos, uno por campo (``cant_min`` y ``referencia_precio``).
#     - Regla 5 y postcondición b: un solo registro por par; un par deshabilitado se REACTIVA (mismo id, con sus lotes).
#     - Postcondición a: registro activo, stock 0, sin lotes. Postcondición c: alerta «bajo el mínimo» si el mínimo es > 0 (y el
#       tránsito no lo alcanza). Postcondición d y D-36: ``habilitacion_insumo_invernadero`` con Decimal como texto.
#   Bloqueos (docs/patrones/stock.md, sección 5): invernadero → insumo → existencia (el insumo se bloquea para que ``baja_insumo``
#   no lo desactive en paralelo).

from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase, TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.models import InsumoInvernadero, LoteInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    asegurar_datos_de_inventario,
    categoria_del_sistema,
    existencia,
    insumo,
    lote,
    perezoso,
    tipo_de_insumo,
    verificar_invariantes,
)
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
insumos = perezoso("inventario.servicios.insumos")
HABILITACION = RegistroAuditoria.Accion.HABILITACION_INSUMO_INVERNADERO
BAJO_MINIMO = "inv_insumo_bajo_minimo"


class CmpHabIinServicioTests(ConDatosDeInventario, TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-HAB-IIN."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Gómez")
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.tipo = tipo_de_insumo("Nutrientes")
        self.insumo = insumo("Nutriente A", tipo=self.tipo, unidad="l", controla_vencimiento=True)
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.agronomo)

    def habilitar(self, actor=None, objetivo=None, invernadero=None, minimo="20", precio="1500"):
        return iin_servicio.habilitar_insumo(
            actor or self.agronomo, (objetivo or self.insumo).pk, (invernadero or self.norte).pk, minimo, precio
        )

    # ---- precondiciones ----

    def test_pre_a_gerente_capataz_y_administrador_no_habilitan(self):
        """Precondición a y regla 1: solo el Agrónomo; el Gerente no gestiona insumos en invernaderos."""
        for actor in (crear_gerente(), crear_capataz(), crear_administrador()):
            with self.subTest(actor=actor.email), self.assertRaises(PermissionDenied):
                self.habilitar(actor)
        self.assertEqual(InsumoInvernadero.objects.count(), 0)

    def test_pre_a_un_agronomo_inactivo_no_habilita(self):
        """Precondición a: la cuenta tiene que estar activa."""
        self.agronomo.is_active = False
        self.agronomo.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            self.habilitar()

    def test_pre_b_un_invernadero_ajeno_da_permiso_denegado(self):
        """Precondición b: el invernadero tiene que estar a cargo del actor."""
        with self.assertRaises(PermissionDenied):
            self.habilitar(self.otro)
        self.assertEqual(InsumoInvernadero.objects.count(), 0)

    def test_pre_b_un_invernadero_inactivo_se_rechaza(self):
        """Precondición b: invernadero activo."""
        inactivo = crear_invernadero("Viejo", activo=False, agronomo=self.agronomo)
        error = error_de(lambda: self.habilitar(invernadero=inactivo))
        self.assertEqual(codigos_de(error), ["invernadero_inactivo"])

    def test_pre_b_un_invernadero_o_un_insumo_que_no_existen_dan_404(self):
        """Ids inexistentes: 404 (D-28)."""
        with self.assertRaises(Http404):
            iin_servicio.habilitar_insumo(self.agronomo, self.insumo.pk, 999999, "1", "1")
        with self.assertRaises(Http404):
            iin_servicio.habilitar_insumo(self.agronomo, 999999, self.norte.pk, "1", "1")

    def test_pre_c_un_insumo_inactivo_del_catalogo_no_se_habilita(self):
        """Precondición c: el insumo está activo en el catálogo."""
        viejo = insumo("Viejo", tipo=self.tipo, activo=False)
        error = error_de(lambda: self.habilitar(objetivo=viejo))
        self.assertEqual(codigos_de(error), ["insumo_inactivo"])

    def test_regla_2_se_incluyen_las_semillas(self):
        """Regla 2: las semillas (insumos de la categoría del sistema) también se habilitan."""
        semilla = insumo("Semilla de lechuga", tipo=categoria_del_sistema("semillas"), unidad="unidad", controla_vencimiento=True)
        self.assertTrue(self.habilitar(objetivo=semilla, minimo="10").activo)

    def test_pre_d_un_insumo_ya_habilitado_se_rechaza(self):
        """Precondición d: no puede estar ya habilitado (y activo) en ese invernadero."""
        self.habilitar()
        error = error_de(lambda: self.habilitar())
        self.assertEqual(codigos_de(error), ["ya_habilitado"])
        self.assertEqual(InsumoInvernadero.objects.count(), 1)

    # ---- reglas de los datos ----

    def test_regla_3_el_minimo_es_obligatorio(self):
        """Regla 3: obligatorio."""
        for vacio in ("", "   ", None):
            with self.subTest(valor=vacio):
                error = error_de(lambda: self.habilitar(minimo=vacio))
                self.assertEqual(codigos_de(error, "cant_min"), ["obligatorio"])

    def test_regla_3_el_minimo_no_puede_ser_negativo(self):
        """Regla 3: cero o más."""
        error = error_de(lambda: self.habilitar(minimo="-1"))
        self.assertEqual(codigos_de(error, "cant_min"), ["minimo_negativo"])

    def test_regla_3_el_minimo_respeta_los_decimales_de_la_unidad(self):
        """Regla 3: con los decimales de la unidad (L: 3; unidad: 0)."""
        error = error_de(lambda: self.habilitar(minimo="1.2345"))
        self.assertEqual(codigos_de(error, "cant_min"), ["decimales_de_la_unidad"])
        bolsas = insumo("Bolsas", tipo=self.tipo, unidad="unidad")
        error = error_de(lambda: self.habilitar(objetivo=bolsas, minimo="2.5"))
        self.assertEqual(codigos_de(error, "cant_min"), ["decimales_de_la_unidad"])

    def test_regla_3_el_minimo_que_no_es_un_numero_se_rechaza(self):
        """Regla 3: un texto no es una cantidad."""
        error = error_de(lambda: self.habilitar(minimo="mucho"))
        self.assertEqual(codigos_de(error, "cant_min"), ["cantidad_invalida"])

    def test_regla_3_el_minimo_cero_es_valido_y_no_genera_alerta(self):
        """Regla 3 y postcondición c: con mínimo 0 no se evalúa la alerta."""
        self.habilitar(minimo="0")
        self.assertEqual(Alerta.objects.filter(tipo_alerta=BAJO_MINIMO).count(), 0)

    def test_regla_4_el_precio_es_obligatorio(self):
        """Regla 4: obligatorio."""
        for vacio in ("", None):
            with self.subTest(valor=vacio):
                error = error_de(lambda: self.habilitar(precio=vacio))
                self.assertEqual(codigos_de(error, "referencia_precio"), ["obligatorio"])

    def test_regla_4_el_precio_tiene_que_ser_mayor_que_cero(self):
        """Regla 4: mayor que cero."""
        for malo in ("0", "-5", "0.00"):
            with self.subTest(precio=malo):
                error = error_de(lambda: self.habilitar(precio=malo))
                self.assertEqual(codigos_de(error, "referencia_precio"), ["precio_invalido"])

    def test_regla_4_el_precio_admite_a_lo_sumo_dos_decimales(self):
        """Regla 4 y modelo: precio con 2 decimales."""
        error = error_de(lambda: self.habilitar(precio="10.555"))
        self.assertEqual(codigos_de(error, "referencia_precio"), ["precio_invalido"])

    def test_regla_3_y_4_los_errores_de_los_dos_campos_se_informan_juntos(self):
        """Patrón ABM: un solo ValidationError con un error por campo."""
        error = error_de(lambda: self.habilitar(minimo="-1", precio="0"))
        self.assertEqual(set(error.error_dict), {"cant_min", "referencia_precio"})

    def test_un_error_de_datos_no_cambia_nada_ni_audita(self):
        """Garantía: todo o nada."""
        error_de(lambda: self.habilitar(minimo="-1"))
        self.assertEqual(InsumoInvernadero.objects.count(), 0)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=HABILITACION).count(), 0)

    # ---- postcondiciones ----

    def test_post_a_crea_el_registro_activo_con_stock_cero_y_sin_lotes(self):
        """Postcondición a y regla 6: nace activo, con stock 0, sin lotes, con el mínimo y el precio indicados."""
        iin = self.habilitar(minimo="20", precio="1500")
        self.assertEqual(iin.estado_insumo_invernadero, "activo")
        self.assertEqual((iin.cant_min_insumo, iin.referencia_precio), (Decimal("20"), Decimal("1500")))
        self.assertEqual(iin.cant_transito_insumo, Decimal("0"))
        self.assertEqual(LoteInsumo.objects.filter(insumo_invernadero=iin).count(), 0)
        self.assertEqual((iin.insumo_id, iin.invernadero_id), (self.insumo.pk, self.norte.pk))

    def test_post_b_un_par_deshabilitado_se_reactiva_con_el_mismo_registro_y_su_historial(self):
        """Postcondición b y regla 5: se reactiva el mismo registro con el mínimo y el precio nuevos y conserva sus lotes."""
        previo = existencia(self.insumo, self.norte, minimo=5, precio="10", activo=False)
        viejo = lote(previo, 0, ingresada=4)
        iin = self.habilitar(minimo="30", precio="2000")
        self.assertEqual(iin.pk, previo.pk)
        previo.refresh_from_db()
        self.assertEqual(
            (previo.estado_insumo_invernadero, previo.cant_min_insumo, previo.referencia_precio),
            ("activo", Decimal("30"), Decimal("2000")),
        )
        self.assertTrue(LoteInsumo.objects.filter(pk=viejo.pk).exists())
        self.assertEqual(InsumoInvernadero.objects.filter(insumo=self.insumo, invernadero=self.norte).count(), 1)

    def test_post_b_reactivar_audita_el_cambio_de_estado(self):
        """Postcondición d: la reactivación también es una habilitación y muestra el estado antes y después."""
        existencia(self.insumo, self.norte, minimo=5, precio="10", activo=False)
        self.habilitar(minimo="30", precio="2000")
        cambios = RegistroAuditoria.objects.get(accion=HABILITACION).detalle["cambios"]
        self.assertEqual(cambios["estado"], {"antes": "inactivo", "despues": "activo"})
        self.assertEqual(cambios["cant_min_insumo"], {"antes": "5.000", "despues": "30.000"})

    def test_post_c_con_minimo_mayor_que_cero_genera_la_alerta_bajo_el_minimo_para_el_agronomo(self):
        """Postcondición c: nace con stock 0, así que queda bajo el mínimo y se alerta al Agrónomo del invernadero."""
        iin = self.habilitar(minimo="20")
        alerta = Alerta.objects.get(tipo_alerta=BAJO_MINIMO)
        self.assertEqual((alerta.clave_estado, alerta.agronomo_id, alerta.invernadero_id), (f"insumo:{iin.pk}", self.agronomo.pk, self.norte.pk))
        self.assertEqual(alerta.estado_alerta, "activa")

    def test_post_c_el_transito_que_alcanza_el_minimo_evita_la_alerta(self):
        """Postcondición c: salvo que haya mercadería en tránsito que alcance el mínimo (la reactivación conserva el tránsito)."""
        existencia(self.insumo, self.norte, minimo=5, precio="10", activo=False, transito="25")
        self.habilitar(minimo="20")
        self.assertEqual(Alerta.objects.filter(tipo_alerta=BAJO_MINIMO).count(), 0)

    def test_post_d_audita_con_usuario_afectados_y_los_decimales_como_texto(self):
        """Postcondición d y D-36: un registro con el insumo y el invernadero, y cantidades y precio como texto."""
        iin = self.habilitar(minimo="20", precio="1500")
        registro = RegistroAuditoria.objects.get(accion=HABILITACION)
        self.assertEqual(registro.usuario_id, self.agronomo.pk)
        modelos = {(a["modelo"], a["id"]) for a in registro.afectados}
        self.assertIn(("inventario.insumoinvernadero", iin.pk), modelos)
        self.assertIn(("maestros.invernadero", self.norte.pk), modelos)
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["cant_min_insumo"], {"antes": None, "despues": "20.000"})
        self.assertEqual(cambios["referencia_precio"], {"antes": None, "despues": "1500.00"})
        self.assertEqual(registro.detalle["datos"]["insumo"]["texto"], "Nutriente A")

    def test_post_c_y_d_la_alerta_creada_va_en_los_datos_del_registro(self):
        """docs/api/alertas.md, «Auditoría»: ``alertas_creadas`` con su referencia."""
        self.habilitar(minimo="20")
        alerta = Alerta.objects.get(tipo_alerta=BAJO_MINIMO)
        registro = RegistroAuditoria.objects.get(accion=HABILITACION)
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["alertas_creadas"]], [alerta.pk])

    def test_regla_1_de_8_4_habilitar_un_insumo_en_dos_invernaderos_crea_un_registro_por_par(self):
        """Regla 1 de 8.4: un registro por (insumo, invernadero)."""
        sur = crear_invernadero("Invernadero Sur", agronomo=self.agronomo)
        self.habilitar()
        self.habilitar(invernadero=sur)
        self.assertEqual(InsumoInvernadero.objects.filter(insumo=self.insumo).count(), 2)

    def test_invariantes_de_stock_tras_reactivar_con_lotes(self):
        """Las invariantes del kárdex siguen valiendo después de reactivar."""
        previo = existencia(self.insumo, self.norte, activo=False)
        lote(previo, 0, ingresada=4)
        self.habilitar()
        verificar_invariantes(previo)


@tag("concurrencia")
class CmpHabIinConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de ``habilitar_insumo`` (D-40; docs/patrones/stock.md sección 5: invernadero → insumo → existencia)."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.agronomo = crear_agronomo()
        self.gerente = crear_gerente()
        self.tipo = tipo_de_insumo("Nutrientes")
        self.insumo = insumo("Nutriente A", tipo=self.tipo, unidad="l")
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero Uno", agronomo=self.agronomo)

    def habilitar(self):
        return iin_servicio.habilitar_insumo(self.agronomo, self.insumo.pk, self.invernadero.pk, "20", "1500")

    def test_regla_5_dos_habilitaciones_del_mismo_par_dejan_un_solo_registro(self):
        """Regla 5: la segunda espera, ve el registro ya activo y se rechaza con ``ya_habilitado``: nunca dos filas ni un 500."""
        resultados = correr_a_la_vez(self.habilitar, self.habilitar, primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["ya_habilitado"])
        self.assertEqual(InsumoInvernadero.objects.filter(insumo=self.insumo, invernadero=self.invernadero).count(), 1)

    def test_regla_5_dos_reactivaciones_del_mismo_par_dejan_el_mismo_registro(self):
        """Postcondición b: con el par deshabilitado, solo una lo reactiva."""
        previo = existencia(self.insumo, self.invernadero, activo=False)
        resultados = correr_a_la_vez(self.habilitar, self.habilitar, primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(InsumoInvernadero.objects.count(), 1)
        self.assertEqual(InsumoInvernadero.objects.get().pk, previo.pk)

    def test_pre_c_habilitar_contra_la_baja_del_insumo_no_deja_una_existencia_activa_de_un_insumo_inactivo(self):
        """Orden invernadero → insumo → existencia: habilitar bloquea el INSUMO. Si habilitar va primero, la baja espera, ve la
        existencia nueva y se rechaza (``cambio_simultaneo``): el insumo sigue activo con su existencia."""
        resultados = correr_a_la_vez(
            self.habilitar, lambda: insumos.baja_insumo(self.agronomo, self.insumo.pk), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["cambio_simultaneo"])
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.estado_insumo, "activo")
        self.assertEqual(InsumoInvernadero.objects.filter(estado_insumo_invernadero="activo").count(), 1)

    def test_pre_c_la_baja_del_insumo_primero_hace_que_habilitar_se_rechace(self):
        """Si la baja va primero, habilitar espera el insumo, lo relee inactivo y se rechaza con ``insumo_inactivo``: no queda
        ninguna existencia activa de un insumo inactivo."""
        resultados = correr_a_la_vez(
            lambda: insumos.baja_insumo(self.agronomo, self.insumo.pk), self.habilitar, primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["insumo_inactivo"])
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.estado_insumo, "inactivo")
        self.assertEqual(InsumoInvernadero.objects.count(), 0)

    def test_contrato_d40_la_baja_del_invernadero_primero_hace_que_habilitar_se_rechace(self):
        """Contrato de D-40: habilitar crea algo que impediría la baja, así que bloquea el invernadero antes. Con la baja primero,
        habilitar espera, encuentra el invernadero inactivo y se rechaza con ``invernadero_inactivo``: no crea nada."""
        resultados = correr_a_la_vez(
            lambda: servicio_de_invernaderos.baja_invernadero(self.gerente, self.invernadero.pk),
            self.habilitar,
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["invernadero_inactivo"])
        self.assertEqual(InsumoInvernadero.objects.count(), 0)

    def test_contrato_d40_habilitar_primero_hace_esperar_a_la_baja_del_invernadero_sin_errores(self):
        """Contrato de D-40: con habilitar primero, la baja del invernadero espera el bloqueo (no da un 500) y ve la existencia
        confirmada. Que la baja la rechace o la pase a inactiva lo conecta el paso 4 (``test_baja_de_invernadero_con_insumos.py``)."""
        resultados = correr_a_la_vez(
            self.habilitar,
            lambda: servicio_de_invernaderos.baja_invernadero(self.gerente, self.invernadero.pk),
            primera="a",
        )
        _, _, otros = separar(resultados)
        self.assertEqual(otros, [])
        self.assertEqual(InsumoInvernadero.objects.filter(invernadero=self.invernadero).count(), 1)
