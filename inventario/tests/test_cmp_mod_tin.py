# Pruebas de CMP-MOD-TIN · Modificar Tipo de Insumo (docs/casos_de_uso/inventario/tipos_de_insumo.md). Cita D-28, D-36 y D-40.
#
# Servicios que se prueban (inventario/servicios/tipos_de_insumo.py), tomados del módulo dentro de cada prueba:
#   modificar_tipo_insumo(actor, tipo_id, *, nombre, consumo_directo) -> TipoInsumo
#     - Precondición a y regla 1: cualquier Agrónomo activo. Precondición b y regla 3: una del sistema se rechaza con
#       ``categoria_del_sistema`` (error general), aunque la pantalla no ofrezca la acción.
#     - Precondición c: el nombre nuevo no lo tiene otra categoría (``nombre_repetido``, campo ``nombre``).
#     - Regla 2: las reglas 2 y 3 de CMP-ALT-TIN.
#     - Regla 4: el consumo directo no cambia si algún insumo de la categoría tiene cantidades reservadas por órdenes a realizar
#       (``reservas_activas``, campo ``consumo_directo``; los insumos y las órdenes van en el texto). El nombre sí se cambia.
#     - Regla 6: una inactiva no se modifica (``categoria_inactiva``).
#     - D-28: sin cambios no se escribe ni se audita.
#   reactivar_tipo_insumo(actor, tipo_id) -> TipoInsumo
#     - Regla 6: sin validaciones; una que no está inactiva se rechaza con ``categoria_no_inactiva``.

from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase, TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario import extensiones
from inventario.extensiones import OrdenQueReserva
from inventario.models import TipoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    asegurar_datos_de_inventario,
    categoria_del_sistema,
    existencia,
    insumo,
    perezoso,
    reservas_de_prueba,
    tipo_de_insumo,
)
from maestros.tests.fabricas import (
    asegurar_datos_de_maestros,
    codigos_de,
    crear_agronomo,
    crear_invernadero,
    error_de,
)

tipos = perezoso("inventario.servicios.tipos_de_insumo")
MODIFICACION = RegistroAuditoria.Accion.MODIFICACION_TIPO_INSUMO
REACTIVACION = RegistroAuditoria.Accion.REACTIVACION_TIPO_INSUMO


class CmpModTinServicioTests(ConDatosDeInventario, TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-MOD-TIN."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.tipo = tipo_de_insumo("Limpieza", "como_gasto")

    def modificar(self, tipo=None, nombre="Limpieza", consumo="como_gasto", actor=None):
        return tipos.modificar_tipo_insumo(actor or self.agronomo, (tipo or self.tipo).pk, nombre=nombre, consumo_directo=consumo)

    def con_reservas(self):
        """Un insumo de la categoría con 3 unidades reservadas por la orden 7: devuelve el administrador de contexto."""
        iin = existencia(insumo("Detergente", tipo=self.tipo), crear_invernadero("Invernadero Uno"))
        orden = OrdenQueReserva(7, "Siembra 7 de Lechuga", Decimal("3"), date(2026, 12, 1), "/ordenes/7/")
        return reservas_de_prueba(reservado={iin.pk: 3}, ordenes={iin.pk: [orden]})

    # ---- precondición a y regla 1 ----

    def test_pre_a_un_gerente_no_modifica(self):
        """CMP-MOD-TIN precondición a: solo un Agrónomo activo."""
        with self.assertRaises(PermissionDenied):
            self.modificar(actor=crear_gerente(), nombre="Otra")

    def test_pre_a_capataz_y_administrador_no_modifican(self):
        """CMP-MOD-TIN precondición a: ningún otro rol."""
        for cuenta in (crear_capataz(), crear_administrador()):
            with self.subTest(rol=type(cuenta).__name__):
                with self.assertRaises(PermissionDenied):
                    self.modificar(actor=cuenta, nombre="Otra")

    def test_regla_1_cualquier_agronomo_activo_modifica_sin_invernadero_a_cargo(self):
        """CMP-MOD-TIN regla 1: la categoría es del catálogo; no hay «a cargo»."""
        otro = crear_agronomo(email="otro@infoponia.com")
        self.assertEqual(self.modificar(actor=otro, nombre="Higiene").nombre_tipo_insumo, "Higiene")

    def test_pre_a_una_categoria_que_no_existe_da_404(self):
        """D-28: un id inexistente da 404."""
        with self.assertRaises(Http404):
            tipos.modificar_tipo_insumo(self.agronomo, 999999, nombre="X", consumo_directo="como_gasto")

    # ---- precondición b y regla 3: las del sistema ----

    def test_pre_b_una_categoria_del_sistema_no_se_modifica_aunque_se_pida(self):
        """CMP-MOD-TIN precondición b y regla 3 («Cómo se aplica»): el servicio la rechaza con ``categoria_del_sistema``."""
        envases = categoria_del_sistema("envases")
        error = error_de(lambda: self.modificar(tipo=envases, nombre="Cajas", consumo="como_gasto"))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["categoria_del_sistema"])
        envases.refresh_from_db()
        self.assertEqual((envases.nombre_tipo_insumo, envases.consumo_directo), ("Envases", "no_admite"))
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_pre_b_ninguna_de_las_cuatro_del_sistema_se_modifica_ni_se_reactiva(self):
        """CMP-MOD-TIN regla 3: ni siquiera guardando sin cambios."""
        for codigo in ("semillas", "envases", "repuestos_de_hardware", "infraestructura"):
            categoria = categoria_del_sistema(codigo)
            with self.subTest(codigo=codigo):
                modificar = error_de(
                    lambda: self.modificar(tipo=categoria, nombre=categoria.nombre_tipo_insumo, consumo="no_admite")
                )
                self.assertEqual(codigos_de(modificar, NON_FIELD_ERRORS), ["categoria_del_sistema"])
                reactivar = error_de(lambda: tipos.reactivar_tipo_insumo(self.agronomo, categoria.pk))
                self.assertEqual(codigos_de(reactivar, NON_FIELD_ERRORS), ["categoria_del_sistema"])

    # ---- precondición c y regla 2: el nombre y el consumo ----

    def test_pre_c_el_nombre_de_otra_categoria_se_rechaza_sin_distinguir_mayusculas_ni_espacios(self):
        """CMP-MOD-TIN precondición c: no existe otra categoría con el nombre nuevo."""
        tipo_de_insumo("Nutrientes")
        error = error_de(lambda: self.modificar(nombre=" nutrientes "))
        self.assertEqual(codigos_de(error, "nombre"), ["nombre_repetido"])
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.nombre_tipo_insumo, "Limpieza")

    def test_pre_c_el_nombre_de_una_del_sistema_o_de_una_inactiva_tambien_cuenta(self):
        """CMP-MOD-TIN precondición c: el nombre es único entre todas."""
        tipo_de_insumo("Vieja", activo=False)
        for nombre in ("envases", "VIEJA"):
            with self.subTest(nombre=nombre):
                self.assertEqual(codigos_de(error_de(lambda: self.modificar(nombre=nombre)), "nombre"), ["nombre_repetido"])

    def test_pre_c_cambiar_solo_las_mayusculas_del_propio_nombre_no_es_un_repetido(self):
        """CMP-MOD-TIN precondición c: «otra categoría»: la propia no cuenta."""
        self.assertEqual(self.modificar(nombre="LIMPIEZA").nombre_tipo_insumo, "LIMPIEZA")

    def test_regla_2_se_validan_el_nombre_y_el_consumo_como_en_el_alta(self):
        """CMP-MOD-TIN regla 2: reglas 2 y 3 de CMP-ALT-TIN, con todos los errores de campo juntos."""
        error = error_de(lambda: self.modificar(nombre="  ", consumo=""))
        self.assertEqual(codigos_de(error, "nombre"), ["obligatorio"])
        self.assertEqual(codigos_de(error, "consumo_directo"), ["obligatorio"])
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(nombre="x" * 101)), "nombre"), ["demasiado_largo"])
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(consumo="nunca")), "consumo_directo"), ["invalido"])

    # ---- regla 4: reservas ----

    def test_regla_4_con_reservas_el_consumo_directo_no_cambia_y_el_error_dice_insumos_y_ordenes(self):
        """CMP-MOD-TIN regla 4: informa los insumos y las órdenes, y no cambia nada (ni audita)."""
        with self.con_reservas():
            error = error_de(lambda: self.modificar(consumo="como_costo_de_los_lotes"))
        self.assertEqual(codigos_de(error, "consumo_directo"), ["reservas_activas"])
        texto = " ".join(error.messages)
        self.assertIn("Detergente", texto)
        self.assertIn("Siembra 7 de Lechuga", texto)
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.consumo_directo, "como_gasto")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_regla_4_con_reservas_el_nombre_si_se_puede_cambiar(self):
        """CMP-MOD-TIN regla 4: «El nombre sí se puede cambiar»."""
        with self.con_reservas():
            self.modificar(nombre="Higiene")
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.nombre_tipo_insumo, "Higiene")

    def test_regla_4_con_reservas_dejar_el_mismo_consumo_directo_no_es_un_cambio(self):
        """CMP-MOD-TIN regla 4: solo se bloquea el CAMBIO del consumo directo."""
        with self.con_reservas():
            self.assertEqual(self.modificar(nombre="Higiene", consumo="como_gasto").consumo_directo, "como_gasto")

    def test_regla_4_sin_reservas_el_consumo_directo_cambia(self):
        """CMP-MOD-TIN regla 4: sin cantidades reservadas el cambio pasa (sin registrantes, el neutro es «sin reservas»)."""
        with self.con_reservas(), mock.patch.object(extensiones, "_RESERVAS", []):
            self.assertEqual(self.modificar(consumo="no_admite").consumo_directo, "no_admite")

    def test_regla_4_solo_pregunta_por_reservas_si_cambia_el_consumo_directo(self):
        """D-40 / docs/api: el registrante se llama dentro de la transacción y solo cuando hace falta (cambia el consumo)."""
        llamadas = []

        def registrante(ids):
            llamadas.append(list(ids))
            return {}

        iin = existencia(insumo("Detergente", tipo=self.tipo), crear_invernadero("Invernadero Uno"))
        with mock.patch.object(extensiones, "_RESERVAS", [registrante]):
            self.modificar(nombre="Higiene")
            self.assertEqual(llamadas, [])
            self.modificar(tipo=self.tipo, nombre="Higiene", consumo="no_admite")
        self.assertEqual(llamadas, [[iin.pk]])

    def test_regla_4_las_reservas_de_los_insumos_de_otra_categoria_no_cuentan(self):
        """CMP-MOD-TIN regla 4: solo los insumos de ESTA categoría."""
        otro = tipo_de_insumo("Nutrientes")
        iin = existencia(insumo("Nitrato", tipo=otro), crear_invernadero("Invernadero Uno"))
        with reservas_de_prueba(reservado={iin.pk: 5}):
            self.assertEqual(self.modificar(consumo="no_admite").consumo_directo, "no_admite")

    def test_regla_5_el_cambio_de_consumo_directo_rige_desde_ese_momento_y_no_toca_los_insumos(self):
        """CMP-MOD-TIN regla 5: los insumos de la categoría quedan como estaban (nada retroactivo)."""
        un_insumo = insumo("Detergente", tipo=self.tipo)
        self.modificar(consumo="como_costo_de_los_lotes")
        un_insumo.refresh_from_db()
        self.assertEqual((un_insumo.tipo_insumo_id, un_insumo.estado_insumo), (self.tipo.pk, "activo"))

    # ---- regla 6: inactivas y reactivación ----

    def test_regla_6_una_categoria_inactiva_no_se_modifica_solo_se_reactiva(self):
        """CMP-MOD-TIN regla 6: se rechaza con ``categoria_inactiva``."""
        inactiva = tipo_de_insumo("Vieja", activo=False)
        error = error_de(lambda: self.modificar(tipo=inactiva, nombre="Nueva"))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["categoria_inactiva"])

    def test_regla_6_reactivar_no_valida_nada_y_queda_activa(self):
        """CMP-MOD-TIN regla 6 y postcondición b: sin validaciones; después se modifica como cualquier otra."""
        inactiva = tipo_de_insumo("Vieja", "como_costo_de_los_lotes", activo=False)
        reactivada = tipos.reactivar_tipo_insumo(self.agronomo, inactiva.pk)
        self.assertEqual((reactivada.estado_tipo_insumo, reactivada.nombre_tipo_insumo), ("activo", "Vieja"))
        self.assertEqual(self.modificar(tipo=inactiva, nombre="Renovada", consumo="como_gasto").nombre_tipo_insumo, "Renovada")

    def test_regla_6_reactivar_una_categoria_activa_se_rechaza(self):
        """Misma función que el alta de la reactivación: una que no está dada de baja no se reactiva."""
        error = error_de(lambda: tipos.reactivar_tipo_insumo(self.agronomo, self.tipo.pk))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["categoria_no_inactiva"])

    def test_pre_a_reactivar_exige_un_agronomo_activo_y_el_id_existe(self):
        """CMP-MOD-TIN precondición a y D-28 para la reactivación."""
        inactiva = tipo_de_insumo("Vieja", activo=False)
        with self.assertRaises(PermissionDenied):
            tipos.reactivar_tipo_insumo(crear_gerente(), inactiva.pk)
        with self.assertRaises(Http404):
            tipos.reactivar_tipo_insumo(self.agronomo, 999999)

    # ---- D-28 y postcondiciones ----

    def test_d28_sin_cambios_no_se_escribe_ni_se_audita(self):
        """D-28: guardar los mismos valores (aunque cambien los espacios del borde) no escribe ni deja registro."""
        resultado = self.modificar(nombre="  Limpieza ", consumo="como_gasto")
        self.assertEqual(resultado.pk, self.tipo.pk)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_post_a_se_actualizan_el_nombre_y_el_consumo_directo(self):
        """CMP-MOD-TIN postcondición a y verificación a mano 4: «Como costo de los lotes» y renombrar."""
        self.modificar(nombre="Higiene", consumo="como_costo_de_los_lotes")
        self.tipo.refresh_from_db()
        self.assertEqual((self.tipo.nombre_tipo_insumo, self.tipo.consumo_directo), ("Higiene", "como_costo_de_los_lotes"))

    def test_post_c_audita_solo_lo_que_cambio_con_antes_y_despues(self):
        """CMP-MOD-TIN postcondición c y D-36: usuario, rol, categoría y los cambios; en un cambio de consumo directo, «antes» y
        «después» llevan el valor (que la pantalla muestra con su nombre visible)."""
        self.modificar(nombre="Limpieza", consumo="como_costo_de_los_lotes")
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        self.assertEqual([a["id"] for a in registro.afectados], [self.tipo.pk])
        self.assertEqual(
            registro.detalle["cambios"],
            {"consumo_directo": {"antes": "como_gasto", "despues": "como_costo_de_los_lotes"}},
        )
        self.assertEqual(registro.filas_de_cambios(), [("Consumo directo", "Como gasto", "Como costo de los lotes")])

    def test_post_c_audita_el_cambio_de_nombre(self):
        """CMP-MOD-TIN postcondición c: el cambio de nombre con su antes y después."""
        self.modificar(nombre="Higiene")
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual(registro.detalle["cambios"], {"nombre": {"antes": "Limpieza", "despues": "Higiene"}})

    def test_post_c_audita_la_reactivacion_con_su_propia_accion(self):
        """CMP-MOD-TIN postcondición c y docs/patrones/abm.md sección 3: ``reactivacion_tipo_insumo`` con el estado."""
        inactiva = tipo_de_insumo("Vieja", activo=False)
        tipos.reactivar_tipo_insumo(self.agronomo, inactiva.pk)
        registro = RegistroAuditoria.objects.get(accion=REACTIVACION)
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "inactivo", "despues": "activo"}})
        self.assertEqual([a["id"] for a in registro.afectados], [inactiva.pk])

    def test_regla_2_un_error_no_cambia_nada(self):
        """Todo o nada: un error de validación no deja la categoría a medio cambiar ni audita."""
        error_de(lambda: self.modificar(nombre="Higiene", consumo="nunca"))
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.nombre_tipo_insumo, "Limpieza")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())


@tag("concurrencia")
class CmpModTinConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de ``modificar_tipo_insumo`` (D-40, docs/patrones/stock.md sección 5; verificación a mano 11). Hereda de
    ``ConDatosDeInventario`` (con los datos de maestros) y asegura los datos en cada prueba: el ``flush`` los vacía."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.uno = crear_agronomo()
        self.otro = crear_agronomo(email="otro@infoponia.com")

    def test_regla_2_dos_modificaciones_del_mismo_nombre_a_valores_distintos_gana_el_ultimo(self):
        """Verificación a mano 11: dos Agrónomos renombran la misma categoría a la vez: gana el último, sin error 500. El
        «antes» del registro del segundo es el «después» del primero (misma convención que ``modificar_cultivo``)."""
        tipo = tipo_de_insumo("Limpieza")
        resultados = correr_a_la_vez(
            lambda: tipos.modificar_tipo_insumo(self.uno, tipo.pk, nombre="Limpieza A", consumo_directo="como_gasto"),
            lambda: tipos.modificar_tipo_insumo(self.otro, tipo.pk, nombre="Limpieza B", consumo_directo="como_gasto"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        tipo.refresh_from_db()
        self.assertEqual(tipo.nombre_tipo_insumo, "Limpieza B")
        cambios = [
            (r.usuario_id, r.detalle["cambios"]["nombre"])
            for r in RegistroAuditoria.objects.filter(accion=MODIFICACION).order_by("id")
        ]
        self.assertEqual(
            cambios,
            [
                (self.uno.pk, {"antes": "Limpieza", "despues": "Limpieza A"}),
                (self.otro.pk, {"antes": "Limpieza A", "despues": "Limpieza B"}),
            ],
        )

    def test_pre_c_dos_renombres_de_categorias_distintas_al_mismo_nombre_dejan_una_sola(self):
        """CMP-MOD-TIN precondición c: el segundo espera el índice único y el ``IntegrityError`` se traduce a ``nombre_repetido``."""
        a, b = tipo_de_insumo("Limpieza"), tipo_de_insumo("Nutrientes")
        resultados = correr_a_la_vez(
            lambda: tipos.modificar_tipo_insumo(self.uno, a.pk, nombre="Higiene", consumo_directo="como_gasto"),
            lambda: tipos.modificar_tipo_insumo(self.otro, b.pk, nombre="higiene", consumo_directo="como_gasto"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["nombre_repetido"])
        self.assertEqual(TipoInsumo.objects.filter(nombre_tipo_insumo__iexact="higiene").count(), 1)
