# Pruebas de CON-INI-EJE «Iniciar Ejercicio Contable» (tarea CON-05, paso 2; docs/casos_de_uso/contabilidad/ejercicio.md, «Cómo se aplica»):
# `ejercicios.iniciar_ejercicio`, `ejercicios.resumir_inicio` y `ejercicios.fecha_inicio_minima`. Cada prueba arma sus datos y recibe «hoy».
# Las pantallas (`ConIniEjeVistaTests`, `ConIniEjeEntradasTests`; paso 4) están al final; la concurrencia está en `test_ejercicios_concurrencia.py`.
#
# Contrato que fijan estas pruebas (lo implementa el paso 2):
#   - `iniciar_ejercicio(actor, fecha_inicio, importes, *, hoy=None) -> AsientoContable` (el asiento de apertura; su ejercicio es `asiento.ejercicio`).
#     `importes` es `{codigo_de_cuenta: Decimal}`; una línea ausente, vacía o en cero se omite.
#   - Los errores de datos son `ErrorContable`; todos llevan `.errores` (cada uno con `.codigo` y `.campo`). Con varios errores de campo se lanzan juntos
#     (`ErroresContables`, orden: fecha, líneas, capital, balance), con el `.codigo` del primero. Campos: `fecha_inicio` e `importes[<código de cuenta>]`.
#   - `resumir_inicio(...)` con los mismos argumentos devuelve un `ResumenDeInicio(inicio, cierre, lineas, total_debe, total_haber, diferencia)` y NO
#     escribe ni bloquea nada; `lineas` son `LineaDeResumen` (usan `.codigo`, `.tipo_movimiento` e `.importe`), las del Debe primero.
#   - `fecha_inicio_minima(hoy)`: la fecha de inicio más antigua permitida (el día siguiente a «hoy menos 12 meses»).
import datetime
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, CuentaContable, EjercicioContable, MovimientoContable
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Agronomo, Capataz, Contador, Gerente, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
Accion = RegistroAuditoria.Accion
HOY = datetime.date(2027, 3, 10)
INICIO = datetime.date(2027, 1, 1)


def _d(texto):
    return Decimal(texto)


def _importes(**extra):
    """El caso común: Caja y Deudores al Debe, Capital Inicial y Proveedores al Haber, balanceado (1.500 contra 1.500)."""
    base = {cuentas.CAJA: _d("1000.00"), cuentas.DEUDORES_POR_VENTAS: _d("500.00"), cuentas.CAPITAL_INICIAL: _d("1200.00"), cuentas.PROVEEDORES: _d("300.00")}
    base.update(extra)
    return base


def _errores(error):
    """`[(codigo, campo)]` de un `ErrorContable`, en el orden en que se lanzaron."""
    return [(e.codigo, e.campo) for e in error.errores]


POR_OMISION = object()  # valor por omisión de `actor`: `None` significa «sin cuenta» y no tiene que convertirse en el Contador


class FalloDePrueba(Exception):
    """Fallo forzado en una prueba de «todo o nada»: una clase propia para que ningún otro error pase la prueba sin querer."""


class ConIniEjeBase(PlanDeCuentasMixin, TestCase):
    """Un Contador y un Gerente, sin ningún ejercicio, y las ayudas para llamar al servicio con `hoy` fijo."""

    def setUp(self):
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com", nombre="Cora", apellido="Díaz")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com", nombre="Gabriela", apellido="Sosa")

    def iniciar(self, actor=POR_OMISION, fecha=INICIO, importes=None, **extra):
        return ejercicios.iniciar_ejercicio(self.contador if actor is POR_OMISION else actor, fecha, _importes() if importes is None else importes, **{"hoy": HOY, **extra})

    def resumir(self, actor=POR_OMISION, fecha=INICIO, importes=None, **extra):
        return ejercicios.resumir_inicio(self.contador if actor is POR_OMISION else actor, fecha, _importes() if importes is None else importes, **{"hoy": HOY, **extra})

    def assert_sin_nada_escrito(self):
        """Garantías mínimas: ni ejercicio, ni asiento, ni movimiento, ni auditoría de la contabilidad."""
        self.assertFalse(EjercicioContable.objects.exists())
        self.assertFalse(AsientoContable.objects.exists())
        self.assertFalse(MovimientoContable.objects.exists())
        self.assertFalse(
            RegistroAuditoria.objects.filter(accion__in=[Accion.ALTA_EJERCICIO_CONTABLE, Accion.ALTA_ASIENTO_CONTABLE, Accion.ALTA_MOVIMIENTO_CONTABLE]).exists()
        )


class ConIniEjeServicioTests(ConIniEjeBase):
    """`iniciar_ejercicio`: postcondiciones, reglas y extensiones de CON-INI-EJE."""

    # --- Postcondiciones --------------------------------------------------------------------------------------------------------------------

    def test_post_a_crea_el_ejercicio_abierto_con_cierre_a_12_meses_y_numero_1(self):
        """Postcondición a y regla 5: ejercicio «abierto», con la fecha de inicio, cierre previsto 12 meses menos un día y último número 1."""
        asiento = self.iniciar(fecha=datetime.date(2026, 11, 15))

        ej = EjercicioContable.objects.get()
        self.assertEqual(asiento.ejercicio_id, ej.pk)
        self.assertEqual(
            (ej.estado_ejercicio, ej.fecha_inicio_ejercicio, ej.fecha_cierre_ejercicio, ej.ultimo_numero_asiento),
            (Estado.ABIERTO, datetime.date(2026, 11, 15), datetime.date(2027, 11, 14), 1),
        )
        self.assertIsNone(ej.contador_id)
        verificar_invariantes_contables()

    def test_post_b_el_asiento_es_el_numero_1_sin_origen_con_la_fecha_de_inicio_y_su_descripcion(self):
        """Postcondición b: asiento N.º 1, sin documento de origen ni contraasiento, fecha = fecha de inicio y descripción «Asiento de apertura»."""
        asiento = self.iniciar(fecha=datetime.date(2026, 11, 15))

        self.assertEqual(
            (asiento.numero_asiento, asiento.fecha_asiento, asiento.descripcion_asiento, asiento.origen_id, asiento.anula_id),
            (1, datetime.date(2026, 11, 15), "Asiento de apertura", None, None),
        )
        self.assertEqual(AsientoContable.objects.count(), 1)
        self.assertEqual(asiento.tipo, "manual")  # sin origen ni contraasiento (regla 15 de 8.20)

    def test_post_c_un_movimiento_por_linea_con_importe_y_debe_igual_haber(self):
        """Postcondición c y regla 8: un movimiento por línea con importe mayor que cero; Capital Inicial va al Haber y Debe = Haber."""
        asiento = self.iniciar()

        movimientos = {(m.cuenta.codigo_cuenta, m.tipo_movimiento): m.importe_movimiento for m in asiento.movimientos.select_related("cuenta")}
        self.assertEqual(
            movimientos,
            {
                (cuentas.CAJA, DEBE): _d("1000.00"),
                (cuentas.DEUDORES_POR_VENTAS, DEBE): _d("500.00"),
                (cuentas.CAPITAL_INICIAL, HABER): _d("1200.00"),
                (cuentas.PROVEEDORES, HABER): _d("300.00"),
            },
        )
        debe = sum(v for (_, t), v in movimientos.items() if t == DEBE)
        haber = sum(v for (_, t), v in movimientos.items() if t == HABER)
        self.assertEqual(debe, haber)

    def test_post_d_audita_ejercicio_asiento_y_cada_movimiento_con_el_actor_y_su_rol(self):
        """Postcondición d y regla 12: un registro por el ejercicio, uno por el asiento y uno por cada movimiento, con el usuario real y su rol."""
        asiento = self.iniciar()

        auditorias = RegistroAuditoria.objects.filter(accion__in=[Accion.ALTA_EJERCICIO_CONTABLE, Accion.ALTA_ASIENTO_CONTABLE, Accion.ALTA_MOVIMIENTO_CONTABLE])
        self.assertEqual(auditorias.filter(accion=Accion.ALTA_EJERCICIO_CONTABLE).count(), 1)
        self.assertEqual(auditorias.filter(accion=Accion.ALTA_ASIENTO_CONTABLE).count(), 1)
        self.assertEqual(auditorias.filter(accion=Accion.ALTA_MOVIMIENTO_CONTABLE).count(), 4)
        for registro in auditorias:
            self.assertEqual(registro.usuario_id, self.contador.pk)
            self.assertEqual(registro.rol, "contador")  # el rol con el que actuó

    def test_post_d_el_alta_del_ejercicio_lleva_el_actor_y_el_origen_puesta_en_marcha(self):
        """Postcondición d: `alta_ejercicio_contable` con el actor (no InfoPonia), `datos.origen` «puesta en marcha» y los tres campos en `cambios`."""
        self.iniciar(fecha=datetime.date(2026, 11, 15))

        alta = RegistroAuditoria.objects.get(accion=Accion.ALTA_EJERCICIO_CONTABLE)
        self.assertEqual(alta.usuario_id, self.contador.pk)
        self.assertEqual(alta.detalle["datos"], {"origen": "puesta en marcha"})
        self.assertEqual(
            alta.detalle["cambios"],
            {
                "fecha_inicio_ejercicio": {"antes": None, "despues": "2026-11-15"},
                "fecha_cierre_ejercicio": {"antes": None, "despues": "2027-11-14"},
                "estado_ejercicio": {"antes": None, "despues": "abierto"},
            },
        )

    def test_post_d_el_asiento_se_audita_con_numero_fecha_descripcion_y_ejercicio(self):
        """Postcondición d y D-36: `alta_asiento_contable` con los valores del asiento; las fechas en ISO, los importes como texto."""
        asiento = self.iniciar(fecha=datetime.date(2026, 11, 15))

        registro = RegistroAuditoria.objects.get(accion=Accion.ALTA_ASIENTO_CONTABLE)
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["numero_asiento"], {"antes": None, "despues": 1})
        self.assertEqual(cambios["fecha_asiento"], {"antes": None, "despues": "2026-11-15"})
        self.assertEqual(cambios["descripcion_asiento"], {"antes": None, "despues": "Asiento de apertura"})
        self.assertEqual(cambios["ejercicio"]["despues"]["id"], asiento.ejercicio_id)
        importes = {r.detalle["cambios"]["importe_movimiento"]["despues"] for r in RegistroAuditoria.objects.filter(accion=Accion.ALTA_MOVIMIENTO_CONTABLE)}
        self.assertEqual(importes, {"1000.00", "500.00", "1200.00", "300.00"})

    def test_post_d_el_gerente_sin_contador_queda_como_autor_con_rol_gerente(self):
        """Extensión 1a, punto 2 y regla 12: sin Contador activo inicia el Gerente y el log lo deja como autor, con rol Gerente."""
        Contador.objects.update(is_active=False)

        self.iniciar(actor=self.gerente)

        for registro in RegistroAuditoria.objects.filter(accion__in=[Accion.ALTA_EJERCICIO_CONTABLE, Accion.ALTA_ASIENTO_CONTABLE]):
            self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))

    def test_post_e_la_contabilidad_queda_iniciada(self):
        """Postcondición e: después de iniciar, `contabilidad_iniciada()` es verdadero (la alerta desaparece y los asientos automáticos pueden registrar)."""
        self.assertFalse(ejercicios.contabilidad_iniciada())

        self.iniciar()

        self.assertTrue(ejercicios.contabilidad_iniciada())

    def test_regla_3_no_toca_ninguna_otra_entidad_y_las_invariantes_se_cumplen(self):
        """Regla 3 y «Además»: solo se crean el ejercicio, el asiento y sus movimientos; la numeración y el balance cumplen las invariantes."""
        self.iniciar()

        self.assertEqual((EjercicioContable.objects.count(), AsientoContable.objects.count(), MovimientoContable.objects.count()), (1, 1, 4))
        verificar_invariantes_contables()

    # --- Regla 1 / precondición a: quién inicia -----------------------------------------------------------------------------------------------

    def test_regla_1_el_contador_inicia(self):
        """Regla 1: el Contador activo inicia la contabilidad."""
        self.assertEqual(self.iniciar(actor=self.contador).numero_asiento, 1)

    def test_regla_1_el_gerente_sin_contador_activo_inicia(self):
        """Regla 1 y extensión 1a: sin Contador activo, el Gerente inicia."""
        Contador.objects.update(is_active=False)

        self.assertEqual(self.iniciar(actor=self.gerente).numero_asiento, 1)

    def test_regla_1_el_gerente_con_un_contador_activo_no_inicia(self):
        """Regla 1 y extensión 1a, punto 3: con un Contador activo el Gerente no inicia; el mensaje dice que lo hace el Contador y no queda nada."""
        with self.assertRaises(PermissionDenied) as contexto:
            self.iniciar(actor=self.gerente)

        self.assertIn("Contador", str(contexto.exception))
        self.assert_sin_nada_escrito()

    def test_regla_1_ningun_otro_rol_inicia_ni_sin_cuenta(self):
        """Regla 1: ni el Vendedor ni el Agrónomo ni quien no tiene cuenta inician, aunque no haya Contador activo."""
        Contador.objects.update(is_active=False)
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")

        for actor in (vendedor, agronomo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.iniciar(actor=actor)
        self.assert_sin_nada_escrito()

    def test_regla_1_un_contador_dado_de_baja_no_inicia(self):
        """Regla 1 y D-30: una instancia cargada antes de la baja no inicia: se compara contra la base (el Contador ya no está activo)."""
        Contador.objects.filter(pk=self.contador.pk).update(is_active=False)

        with self.assertRaises(PermissionDenied):
            self.iniciar(actor=self.contador)
        self.assert_sin_nada_escrito()

    def test_regla_1_el_permiso_se_chequea_antes_que_los_datos(self):
        """Regla 1: un Vendedor con datos inválidos recibe `PermissionDenied`, no el error de datos (no se filtra qué estaba mal)."""
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")

        with self.assertRaises(PermissionDenied):
            self.iniciar(actor=vendedor, importes={})

    # --- Regla 2 y extensiones 2a / 7a: una sola vez -------------------------------------------------------------------------------------------

    def test_ext_2a_con_un_ejercicio_en_cualquier_estado_lanza_contabilidad_ya_iniciada(self):
        """Regla 2 y extensión 2a: si ya existe un ejercicio, abierto, en cierre o cerrado, `contabilidad_ya_iniciada` y no se cambia nada."""
        for estado in (Estado.ABIERTO, Estado.EN_CIERRE, Estado.CERRADO):
            with self.subTest(estado=estado):
                EjercicioContable.objects.all().delete()
                previo = ejercicio(estado, datetime.date(2026, 1, 1))

                with self.assertRaises(ErrorContable) as contexto:
                    self.iniciar()

                self.assertEqual(contexto.exception.codigo, "contabilidad_ya_iniciada")
                self.assertEqual(list(EjercicioContable.objects.values_list("pk", flat=True)), [previo.pk])
                self.assertFalse(AsientoContable.objects.exists())

    def test_ext_2a_un_segundo_inicio_con_un_ejercicio_sin_asiento_lanza_contabilidad_ya_iniciada(self):
        """Extensión 2a (el caso de producción: el ejercicio que creó la puesta en marcha automática, sin asientos): un nuevo inicio no lo completa ni lo
        pisa; lanza `contabilidad_ya_iniciada`, no agrega el asiento N.º 1 y deja intacto el ejercicio (último número 0)."""
        previo = ejercicio(Estado.ABIERTO, datetime.date(2026, 11, 26))

        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar(fecha=datetime.date(2026, 11, 1))

        self.assertEqual(contexto.exception.codigo, "contabilidad_ya_iniciada")
        previo.refresh_from_db()
        self.assertEqual((previo.ultimo_numero_asiento, previo.fecha_inicio_ejercicio), (0, datetime.date(2026, 11, 26)))
        self.assertFalse(AsientoContable.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion=Accion.ALTA_ASIENTO_CONTABLE).exists())

    def test_ext_2a_el_segundo_inicio_despues_de_uno_exitoso_no_duplica(self):
        """Regla 2: no hay reinicio; el segundo inicio rechaza y el libro conserva un solo ejercicio con un solo asiento."""
        self.iniciar()

        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar()

        self.assertEqual(contexto.exception.codigo, "contabilidad_ya_iniciada")
        self.assertEqual((EjercicioContable.objects.count(), AsientoContable.objects.count()), (1, 1))

    def test_ext_7a_si_otro_crea_el_ejercicio_a_la_vez_la_restriccion_unica_lo_traduce_a_contabilidad_ya_iniciada(self):
        """Extensión 7a: aunque la lectura previa diga «no iniciada», el alta que choca con la restricción única (un solo ejercicio abierto) se
        traduce a `contabilidad_ya_iniciada` y nunca llega un `IntegrityError` (docs/patrones/bloqueos.md)."""
        ejercicio(Estado.ABIERTO, datetime.date(2026, 1, 1))

        with mock.patch.object(ejercicios, "contabilidad_iniciada", return_value=False):
            with self.assertRaises(ErrorContable) as contexto:
                self.iniciar()

        self.assertEqual(contexto.exception.codigo, "contabilidad_ya_iniciada")
        self.assertEqual(EjercicioContable.objects.count(), 1)
        self.assertFalse(AsientoContable.objects.exists())

    # --- Regla 4: fecha de inicio ---------------------------------------------------------------------------------------------------------------

    def test_ext_5a_una_fecha_futura_se_rechaza_con_fecha_futura(self):
        """Regla 4 y extensión 5a: la fecha de inicio no puede ser posterior a hoy (`fecha_futura`, campo `fecha_inicio`); no queda nada."""
        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar(fecha=HOY + datetime.timedelta(days=1))

        self.assertEqual(_errores(contexto.exception), [("fecha_futura", "fecha_inicio")])
        self.assert_sin_nada_escrito()

    def test_regla_4_hoy_es_una_fecha_valida(self):
        """Regla 4: empezar hoy es válido (borde superior)."""
        asiento = self.iniciar(fecha=HOY)

        self.assertEqual(asiento.fecha_asiento, HOY)

    def test_ext_5b_una_fecha_tan_antigua_que_el_cierre_ya_paso_se_rechaza_y_dice_la_minima(self):
        """Regla 4 y extensión 5b: si la fecha de cierre prevista es anterior a hoy, `fecha_inicio_demasiado_antigua`, y el mensaje nombra la fecha más antigua permitida."""
        minima = ejercicios.fecha_inicio_minima(HOY)

        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar(fecha=minima - datetime.timedelta(days=1))

        self.assertEqual(_errores(contexto.exception), [("fecha_inicio_demasiado_antigua", "fecha_inicio")])
        self.assertIn(f"{minima:%d/%m/%Y}", contexto.exception.mensaje)
        self.assert_sin_nada_escrito()

    def test_regla_4_la_fecha_minima_es_valida(self):
        """Regla 4 (borde): la fecha mínima es válida y su cierre previsto es hoy."""
        minima = ejercicios.fecha_inicio_minima(HOY)

        asiento = self.iniciar(fecha=minima)

        self.assertEqual(asiento.ejercicio.fecha_cierre_ejercicio, HOY)

    def test_regla_4_fecha_inicio_minima_es_el_dia_siguiente_a_hoy_menos_12_meses(self):
        """Extensión 5b y cómo se aplica: `fecha_inicio_minima(hoy)` es el día siguiente a «hoy menos 12 meses»."""
        self.assertEqual(ejercicios.fecha_inicio_minima(datetime.date(2027, 3, 10)), datetime.date(2026, 3, 11))
        self.assertEqual(ejercicios.fecha_inicio_minima(datetime.date(2027, 1, 1)), datetime.date(2026, 1, 2))
        self.assertEqual(ejercicios.fecha_inicio_minima(datetime.date(2028, 2, 29)), datetime.date(2027, 3, 1))  # el 29/2 sin año anterior bisiesto

    def test_regla_4_la_fecha_minima_coincide_con_el_cierre_previsto_en_todo_el_calendario(self):
        """Regla 4 y regla 5: para cada «hoy» de cuatro años (con un 29 de febrero), el cierre previsto de la mínima no es anterior a hoy y el de la
        fecha anterior a la mínima sí (la fecha mínima y la validación no se separan)."""
        dia = datetime.date(2027, 1, 1)
        while dia <= datetime.date(2030, 12, 31):
            minima = ejercicios.fecha_inicio_minima(dia)
            self.assertGreaterEqual(ejercicios.cierre_previsto(minima), dia, dia)
            self.assertLess(ejercicios.cierre_previsto(minima - datetime.timedelta(days=1)), dia, dia)
            dia += datetime.timedelta(days=1)

    def test_regla_5_un_inicio_el_29_de_febrero_cierra_el_28_de_febrero_siguiente(self):
        """Regla 5 (igual que CON-ABR-EJE): un inicio el 29 de febrero cierra el 28 de febrero del año siguiente."""
        asiento = ejercicios.iniciar_ejercicio(self.contador, datetime.date(2028, 2, 29), _importes(), hoy=datetime.date(2028, 3, 5))

        self.assertEqual(asiento.ejercicio.fecha_cierre_ejercicio, datetime.date(2029, 2, 28))

    # --- Regla 6 y 7: cuentas del asiento de apertura ------------------------------------------------------------------------------------------

    def test_regla_6_una_cuenta_fuera_de_las_cinco_no_se_permite_en_la_apertura(self):
        """Regla 6 y regla 7: Insumos en Stock, Productos en Proceso, Productos Terminados, Ventas, etc. no van en la apertura:
        `cuenta_no_permitida_en_apertura`, y no queda nada."""
        for codigo in (cuentas.INSUMOS_EN_STOCK, cuentas.PRODUCTOS_EN_PROCESO, cuentas.PRODUCTOS_TERMINADOS, cuentas.VENTAS, cuentas.GASTOS_GENERALES, cuentas.INDEMNIZACIONES_A_PAGAR):
            with self.subTest(cuenta=codigo), self.assertRaises(ErrorContable) as contexto:
                self.iniciar(importes=_importes(**{codigo: _d("10.00")}))
            self.assertEqual(contexto.exception.codigo, "cuenta_no_permitida_en_apertura")
            self.assertEqual(contexto.exception.campo, f"importes[{codigo}]")
            self.assert_sin_nada_escrito()

    def test_regla_6_un_codigo_que_no_existe_tampoco_se_permite(self):
        """Regla 6: no se pueden agregar otras cuentas: un código desconocido se rechaza con el mismo código."""
        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar(importes=_importes(**{"9.9.99": _d("10.00")}))

        self.assertEqual(contexto.exception.codigo, "cuenta_no_permitida_en_apertura")

    def test_regla_6_una_cuenta_no_permitida_con_importe_cero_tambien_se_rechaza(self):
        """Regla 6: la clave en sí no es válida, aunque su importe sea cero (no se «omite» una cuenta que no corresponde)."""
        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar(importes=_importes(**{cuentas.INSUMOS_EN_STOCK: _d("0.00")}))

        self.assertEqual(contexto.exception.codigo, "cuenta_no_permitida_en_apertura")

    def test_regla_6_las_cinco_cuentas_permitidas_se_aceptan_con_su_lado(self):
        """Regla 6: Caja, Banco c/c y Deudores por Ventas van al Debe; Capital Inicial y Proveedores, al Haber."""
        importes = {
            cuentas.CAJA: _d("100.00"),
            cuentas.BANCO: _d("200.00"),
            cuentas.DEUDORES_POR_VENTAS: _d("300.00"),
            cuentas.CAPITAL_INICIAL: _d("500.00"),
            cuentas.PROVEEDORES: _d("100.00"),
        }

        asiento = self.iniciar(importes=importes)

        lados = {m.cuenta.codigo_cuenta: m.tipo_movimiento for m in asiento.movimientos.select_related("cuenta")}
        self.assertEqual(
            lados,
            {cuentas.CAJA: DEBE, cuentas.BANCO: DEBE, cuentas.DEUDORES_POR_VENTAS: DEBE, cuentas.CAPITAL_INICIAL: HABER, cuentas.PROVEEDORES: HABER},
        )

    # --- Regla 8: importes y balance ------------------------------------------------------------------------------------------------------------

    def test_ext_5c_el_capital_inicial_es_obligatorio(self):
        """Regla 6 y extensión 5c: sin importe en Capital Inicial (ausente) no se inicia: `capital_inicial_obligatorio`; no queda nada."""
        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar(importes={cuentas.CAJA: _d("100.00"), cuentas.PROVEEDORES: _d("100.00")})

        self.assertIn(("capital_inicial_obligatorio", f"importes[{cuentas.CAPITAL_INICIAL}]"), _errores(contexto.exception))
        self.assert_sin_nada_escrito()

    def test_ext_5c_el_capital_inicial_en_cero_o_vacio_tambien_es_obligatorio(self):
        """Extensión 5c: un Capital Inicial en cero se omite y por eso falta; igual que `None`."""
        for valor in (_d("0.00"), _d("0"), None):
            with self.subTest(valor=valor), self.assertRaises(ErrorContable) as contexto:
                self.iniciar(importes={cuentas.CAJA: _d("100.00"), cuentas.CAPITAL_INICIAL: valor})
            self.assertEqual(contexto.exception.codigo, "capital_inicial_obligatorio")

    def test_ext_5c_solo_capital_sin_contrapartida_se_rechaza_por_desbalance(self):
        """Regla 8: con Capital Inicial solo (un lado) el Debe y el Haber no coinciden: `asiento_desbalanceado`."""
        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar(importes={cuentas.CAPITAL_INICIAL: _d("100.00")})

        self.assertEqual(contexto.exception.codigo, "asiento_desbalanceado")

    def test_ext_5d_el_debe_y_el_haber_distintos_se_rechazan_con_la_diferencia_en_el_mensaje(self):
        """Regla 8 y extensión 5d: Debe ≠ Haber lanza `asiento_desbalanceado`, con la diferencia en el mensaje; no queda nada."""
        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar(importes=_importes(**{cuentas.PROVEEDORES: _d("250.00")}))  # Debe 1.500,00; Haber 1.450,00

        self.assertEqual(_errores(contexto.exception), [("asiento_desbalanceado", "importes")])
        self.assertIn("50,00", contexto.exception.mensaje)
        self.assert_sin_nada_escrito()

    def test_ext_5e_un_importe_negativo_se_rechaza_por_linea(self):
        """Regla 8 y extensión 5e: un importe negativo es `importe_invalido`, marcado en el campo de esa cuenta."""
        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar(importes=_importes(**{cuentas.CAJA: _d("-5.00")}))

        self.assertEqual(_errores(contexto.exception), [("importe_invalido", f"importes[{cuentas.CAJA}]")])
        self.assert_sin_nada_escrito()

    def test_ext_5e_un_importe_con_mas_de_dos_decimales_o_que_no_es_decimal_se_rechaza(self):
        """Extensión 5e: más de dos decimales, un `float`, un texto o un valor que no cabe en la columna son `importe_invalido`."""
        for valor in (_d("10.005"), 10.5, "10", _d("NaN"), _d("1000000000000.00")):
            with self.subTest(valor=valor), self.assertRaises(ErrorContable) as contexto:
                self.iniciar(importes=_importes(**{cuentas.CAJA: valor}))
            self.assertEqual(_errores(contexto.exception), [("importe_invalido", f"importes[{cuentas.CAJA}]")])

    def test_ext_5e_las_lineas_en_cero_o_vacias_se_omiten(self):
        """Extensión 5e: las líneas sin importe, `None` o en cero se omiten; el asiento queda solo con las de importe mayor que cero."""
        importes = _importes(**{cuentas.BANCO: _d("0.00"), cuentas.PROVEEDORES: None})
        importes[cuentas.CAPITAL_INICIAL] = _d("1500.00")

        asiento = self.iniciar(importes=importes)

        self.assertEqual(
            sorted(m.cuenta.codigo_cuenta for m in asiento.movimientos.select_related("cuenta")),
            [cuentas.CAJA, cuentas.DEUDORES_POR_VENTAS, cuentas.CAPITAL_INICIAL],
        )

    def test_ext_5e_un_importe_con_un_solo_decimal_se_acepta_en_dos_decimales(self):
        """Regla 8: un `Decimal` con menos decimales vale (se guarda con dos): 1000.5 → 1.000,50."""
        asiento = self.iniciar(importes={cuentas.CAJA: _d("1000.5"), cuentas.CAPITAL_INICIAL: _d("1000.50")})

        self.assertEqual(asiento.movimientos.get(cuenta__codigo_cuenta=cuentas.CAJA).importe_movimiento, _d("1000.50"))

    def test_varios_errores_de_campo_se_lanzan_juntos_en_orden(self):
        """Cómo se aplica: con varios errores de campo se lanzan juntos (`ErroresContables`): fecha, líneas, capital; el `.codigo` es el del primero."""
        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar(fecha=HOY + datetime.timedelta(days=5), importes={cuentas.CAJA: _d("-1.00"), cuentas.PROVEEDORES: _d("10.00")})

        self.assertEqual(
            _errores(contexto.exception),
            [
                ("fecha_futura", "fecha_inicio"),
                ("importe_invalido", f"importes[{cuentas.CAJA}]"),
                ("capital_inicial_obligatorio", f"importes[{cuentas.CAPITAL_INICIAL}]"),
            ],
        )
        self.assertEqual(contexto.exception.codigo, "fecha_futura")
        self.assert_sin_nada_escrito()

    # --- Extensión 7b y todo o nada -------------------------------------------------------------------------------------------------------------

    def test_ext_7b_si_una_cuenta_del_asiento_ya_no_existe_no_se_registra_nada(self):
        """Extensión 7b: si una cuenta del asiento ya no existe en el plan, `cuenta_inexistente` y no queda ejercicio, asiento ni auditoría."""
        CuentaContable.objects.filter(codigo_cuenta=cuentas.DEUDORES_POR_VENTAS).delete()

        with self.assertRaises(ErrorContable) as contexto:
            self.iniciar()

        self.assertEqual(contexto.exception.codigo, "cuenta_inexistente")
        self.assertIn(cuentas.DEUDORES_POR_VENTAS, contexto.exception.mensaje)
        self.assert_sin_nada_escrito()

    def test_garantias_minimas_si_falla_el_asiento_de_apertura_no_queda_el_ejercicio(self):
        """Garantías mínimas y regla 3 («puesta en marcha indivisible»): si falla la creación del asiento de apertura, se deshace también el ejercicio y su auditoría."""
        with mock.patch("contabilidad.servicios.asientos._crear_y_auditar", side_effect=FalloDePrueba):
            with self.assertRaises(FalloDePrueba):
                self.iniciar()

        self.assert_sin_nada_escrito()
        self.assertFalse(ejercicios.contabilidad_iniciada())

    def test_garantias_minimas_si_falla_al_crear_los_movimientos_no_queda_nada(self):
        """Garantías mínimas: un fallo al crear los movimientos deshace el asiento, el ejercicio y el número."""
        with mock.patch.object(MovimientoContable.objects, "bulk_create", side_effect=FalloDePrueba):
            with self.assertRaises(FalloDePrueba):
                self.iniciar()

        self.assert_sin_nada_escrito()

    def test_garantias_minimas_si_falla_la_ultima_auditoria_no_queda_nada(self):
        """Garantías mínimas: si falla el último registro de auditoría (1 del ejercicio + 1 del asiento + 4 de movimientos), no queda ninguno de los anteriores."""
        real = RegistroAuditoria.objects.registrar
        llamadas = []

        def falla_en_el_ultimo(*args, **kwargs):
            llamadas.append(args[1])
            if len(llamadas) == 6:
                raise FalloDePrueba
            return real(*args, **kwargs)

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=falla_en_el_ultimo):
            with self.assertRaises(FalloDePrueba):
                self.iniciar()

        self.assertEqual(len(llamadas), 6)
        self.assert_sin_nada_escrito()

    def test_un_rechazo_de_datos_no_deja_auditoria_parcial(self):
        """Garantías mínimas: un rechazo por datos no escribe ningún registro de auditoría."""
        with self.assertRaises(ErrorContable):
            self.iniciar(importes=_importes(**{cuentas.PROVEEDORES: _d("1.00")}))

        self.assertFalse(RegistroAuditoria.objects.filter(accion__in=[Accion.ALTA_EJERCICIO_CONTABLE, Accion.ALTA_ASIENTO_CONTABLE]).exists())


class ConIniEjeResumenTests(ConIniEjeBase):
    """`resumir_inicio` (paso 5 de CON-INI-EJE): las mismas validaciones que `iniciar_ejercicio`, sin escribir ni bloquear."""

    def test_el_resumen_trae_el_ejercicio_el_asiento_las_lineas_y_los_totales(self):
        """Paso 5: fecha de inicio y de cierre previstas, las líneas con importe (las del Debe primero), el total del Debe, el del Haber y la diferencia (0)."""
        resumen = self.resumir(fecha=datetime.date(2026, 11, 15))

        self.assertEqual((resumen.inicio, resumen.cierre), (datetime.date(2026, 11, 15), datetime.date(2027, 11, 14)))
        self.assertEqual(
            [(l.codigo, l.tipo_movimiento, l.importe) for l in resumen.lineas],
            [
                (cuentas.CAJA, DEBE, _d("1000.00")),
                (cuentas.DEUDORES_POR_VENTAS, DEBE, _d("500.00")),
                (cuentas.CAPITAL_INICIAL, HABER, _d("1200.00")),
                (cuentas.PROVEEDORES, HABER, _d("300.00")),
            ],
        )
        self.assertEqual((resumen.total_debe, resumen.total_haber, resumen.diferencia), (_d("1500.00"), _d("1500.00"), _d("0.00")))

    def test_el_resumen_omite_las_lineas_en_cero(self):
        """Extensión 5e: las líneas sin importe o en cero no figuran en el resumen."""
        resumen = self.resumir(importes=_importes(**{cuentas.BANCO: _d("0.00"), cuentas.DEUDORES_POR_VENTAS: None, cuentas.CAPITAL_INICIAL: _d("700.00")}))

        self.assertEqual([l.codigo for l in resumen.lineas], [cuentas.CAJA, cuentas.CAPITAL_INICIAL, cuentas.PROVEEDORES])

    def test_el_resumen_no_escribe_ni_audita_nada(self):
        """Paso 5: el resumen no crea ejercicio, asiento ni auditoría (ni bloquea: no hay nada que confirmar todavía)."""
        self.resumir()

        self.assert_sin_nada_escrito()
        self.assertFalse(ejercicios.contabilidad_iniciada())

    def test_el_resumen_hace_las_mismas_validaciones_que_iniciar(self):
        """Paso 5: cada rechazo de `iniciar_ejercicio` lo es también del resumen: fecha futura, fecha antigua, cuenta no permitida, capital, desbalance, importe."""
        casos = {
            "fecha_futura": {"fecha": HOY + datetime.timedelta(days=1)},
            "fecha_inicio_demasiado_antigua": {"fecha": ejercicios.fecha_inicio_minima(HOY) - datetime.timedelta(days=1)},
            "cuenta_no_permitida_en_apertura": {"importes": _importes(**{cuentas.VENTAS: _d("1.00")})},
            "capital_inicial_obligatorio": {"importes": {cuentas.CAJA: _d("1.00"), cuentas.PROVEEDORES: _d("1.00")}},
            "asiento_desbalanceado": {"importes": _importes(**{cuentas.PROVEEDORES: _d("1.00")})},
            "importe_invalido": {"importes": _importes(**{cuentas.CAJA: _d("-1.00")})},
        }
        for codigo, argumentos in casos.items():
            with self.subTest(codigo=codigo), self.assertRaises(ErrorContable) as contexto:
                self.resumir(**argumentos)
            self.assertEqual(contexto.exception.codigo, codigo)

    def test_el_resumen_exige_los_mismos_permisos(self):
        """Regla 1: el Gerente con un Contador activo, el Vendedor y quien no tiene cuenta no piden el resumen."""
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")

        for actor in (self.gerente, vendedor, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.resumir(actor=actor)

    def test_el_resumen_con_un_ejercicio_existente_lanza_contabilidad_ya_iniciada(self):
        """Extensión 2a: el paso 2 ya avisa que la contabilidad está iniciada; el resumen tampoco sigue."""
        ejercicio(Estado.CERRADO, datetime.date(2026, 1, 1))

        with self.assertRaises(ErrorContable) as contexto:
            self.resumir()

        self.assertEqual(contexto.exception.codigo, "contabilidad_ya_iniciada")


# =====================================================================================================================================================================
# Paso 4 de CON-05: la pantalla «Iniciar ejercicio». Contrato que fijan estas pruebas (lo implementa el paso 4):
#   - `contabilidad:iniciar` (`/contabilidad/ejercicios/iniciar/`), GET y POST. Solo el responsable contable (regla 1); el Gerente con un Contador activo recibe 403 con el mensaje
#     «Lo inicia el Contador: mientras haya un Contador activo, el Gerente no inicia la contabilidad.» (el mismo del servicio, que se ajusta en este paso); los demás roles, 403.
#   - Campos del formulario: `fecha_inicio` (AAAA-MM-DD, por omisión hoy, con `min` y `max` del rango de la regla 4), `importe_<código de cuenta>` para las cinco cuentas
#     (por ejemplo `importe_1.1.01`; acepta «1.500,50», «1500,5» o «1500.50»; vacío es cero) y, si llegó, `volver` (una ruta del mismo sitio).
#   - `accion`: «calcular» (el botón «Calcular cierre»: recalcula la fecha de cierre previsto, sin validar nada), «revisar» (el botón «Ver resumen», y lo que dispara Enter; paso 5),
#     «editar» («Volver a editar») y «confirmar» («Confirmar e iniciar»; pasos 6 a 8).
#   - Paso 5: el resumen con el ejercicio (inicio y cierre previsto), el asiento N.º 1 con su fecha y descripción, las líneas, los totales del Debe y del Haber y la diferencia.
#   - Paso 8: «confirmar» responde con una redirección a `contabilidad:iniciar?listo=1` (y `&volver=` si llegó), que muestra la confirmación; sin el ejercicio, ese `?listo=1` no cambia nada.
#   - Ya iniciada (extensión 2a): el mensaje «La contabilidad ya está iniciada» con el enlace a «Ejercicios», sin formulario, también al enviar.
# =====================================================================================================================================================================

INICIAR = "contabilidad:iniciar"
TOTAL = "$ 1.500,00"


def _formulario(fecha="2027-03-10", accion="revisar", **importes):
    """El POST de la pantalla: por omisión, el caso común de `_importes()` (Caja 1.000, Deudores 500, Capital 1.200, Proveedores 300); ``importes`` cambia o agrega `importe_<código>`."""
    base = {
        f"importe_{cuentas.CAJA}": "1.000,00",
        f"importe_{cuentas.DEUDORES_POR_VENTAS}": "500,00",
        f"importe_{cuentas.CAPITAL_INICIAL}": "1.200,00",
        f"importe_{cuentas.PROVEEDORES}": "300,00",
    }
    base.update({f"importe_{codigo}": valor for codigo, valor in importes.items()})
    return {"fecha_inicio": fecha, "accion": accion, **base}


class ConIniEjeVistaBase(ConIniEjeBase):
    """Con `hoy` fijo en 10/3/2027 también para las vistas (que lo toman de `timezone.localdate`)."""

    def setUp(self):
        super().setUp()
        cache.clear()
        mock.patch("django.utils.timezone.localdate", return_value=HOY).start()
        self.addCleanup(mock.patch.stopall)
        self.url = reverse(INICIAR)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)
        return cuenta

    def get(self, cuenta=None, url=None, **extra):
        if cuenta is not None:
            self.entrar(cuenta)
        return self.client.get(url or self.url, **extra)

    def post(self, datos, cuenta=None, **extra):
        if cuenta is not None:
            self.entrar(cuenta)
        return self.client.post(self.url, datos, **extra)

    def sin_contador(self):
        Contador.objects.update(is_active=False)


class ConIniEjeVistaTests(ConIniEjeVistaBase):
    """La pantalla «Iniciar ejercicio» (CON-INI-EJE, pasos 2 a 8) por rol y por estado."""

    # --- Quién entra ----------------------------------------------------------------------------------------------------------------------------------------

    def test_regla_1_el_contador_y_el_gerente_sin_contador_ven_el_formulario(self):
        """Regla 1: el Contador, y el Gerente cuando no hay Contador activo, abren la pantalla (200) con el formulario."""
        self.assertContains(self.get(self.contador), 'name="fecha_inicio"')
        self.sin_contador()
        self.assertContains(self.get(self.gerente), 'name="fecha_inicio"')

    def test_regla_1_el_gerente_con_contador_activo_recibe_403_con_el_mensaje_de_iniciar(self):
        """Regla 1 y extensión 1a, punto 3: 403 con «Lo inicia el Contador: mientras haya un Contador activo, el Gerente no inicia la contabilidad.» (no el de «registrar asientos»); lo mismo al enviar."""
        for respuesta in (self.get(self.gerente), self.post(_formulario())):
            self.assertContains(respuesta, "Lo inicia el Contador: mientras haya un Contador activo, el Gerente no inicia la contabilidad.", status_code=403)
        self.assert_sin_nada_escrito()

    def test_regla_1_el_servicio_dice_lo_mismo_al_gerente_con_contador(self):
        """Regla 1: el servicio ajusta su mensaje: «Lo inicia el Contador…» y, para quien no puede iniciar, «inicia la contabilidad» (no «registra asientos»)."""
        with self.assertRaises(PermissionDenied) as contexto:
            ejercicios.iniciar_ejercicio(self.gerente, INICIO, _importes(), hoy=HOY)
        self.assertEqual(str(contexto.exception), "Lo inicia el Contador: mientras haya un Contador activo, el Gerente no inicia la contabilidad.")
        with self.assertRaises(PermissionDenied) as contexto:
            ejercicios.iniciar_ejercicio(crear_cuenta(Vendedor, email="vendedor@infoponia.com"), INICIO, _importes(), hoy=HOY)
        self.assertEqual(str(contexto.exception), "Solo el Contador, o el Gerente si no hay un Contador activo, inicia la contabilidad.")

    def test_regla_1_los_demas_roles_reciben_403_y_sin_sesion_pide_iniciar_sesion(self):
        """Regla 1 y D-30: el Vendedor, el Agrónomo y el Capataz, 403 (también al enviar); sin sesión, la redirección al login."""
        for clase, correo in ((Vendedor, "vendedor@infoponia.com"), (Agronomo, "agronomo@infoponia.com"), (Capataz, "capataz@infoponia.com")):
            cuenta = crear_cuenta(clase, email=correo)
            with self.subTest(rol=clase.__name__):
                self.assertEqual(self.get(cuenta).status_code, 403)
                self.assertEqual(self.post(_formulario(accion="confirmar")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assert_sin_nada_escrito()

    # --- Paso 2: el formulario --------------------------------------------------------------------------------------------------------------------------------

    def test_paso_2_el_formulario_trae_la_fecha_de_hoy_el_rango_las_cinco_cuentas_y_el_texto_de_la_regla_7(self):
        """Paso 2 y reglas 4, 5, 6 y 7: la fecha de inicio (por omisión hoy; `min` la fecha más antigua y `max` hoy), el cierre previsto que resulta, las cinco líneas en «Debe» y «Haber» (con código,
        nombre y un campo de importe cada una, las cuentas ya puestas) y el texto que explica que los insumos y los lotes se cargan después y también acreditan Capital Inicial."""
        respuesta = self.get(self.contador)

        self.assertContains(respuesta, 'name="fecha_inicio"')
        self.assertContains(respuesta, 'value="2027-03-10"')
        self.assertContains(respuesta, 'min="2026-03-11"')
        self.assertContains(respuesta, 'max="2027-03-10"')
        self.assertContains(respuesta, "09/03/2028")  # el cierre previsto de un inicio el 10/3/2027
        for codigo, nombre in ((cuentas.CAJA, "Caja"), (cuentas.BANCO, "Banco c/c"), (cuentas.DEUDORES_POR_VENTAS, "Deudores por Ventas"), (cuentas.CAPITAL_INICIAL, "Capital Inicial"), (cuentas.PROVEEDORES, "Proveedores")):
            self.assertContains(respuesta, f'name="importe_{codigo}"')
            self.assertContains(respuesta, nombre)
        for sobra in (cuentas.INSUMOS_EN_STOCK, cuentas.PRODUCTOS_EN_PROCESO, cuentas.PRODUCTOS_TERMINADOS, cuentas.VENTAS):
            self.assertNotContains(respuesta, f"importe_{sobra}")
        self.assertContains(respuesta, "insumos y los lotes que ya existían")
        self.assertContains(respuesta, "Capital Inicial")
        self.assertContains(respuesta, "Ver resumen")
        self.assertContains(respuesta, "Calcular cierre")

    def test_paso_2_el_calculo_del_cierre_es_un_boton_y_no_valida_mientras_se_escribe(self):
        """interfaz.md («Validaciones e interacción HTMX») y decisión del estudiante: el cierre previsto se recalcula con el botón «Calcular cierre» (HTMX, `data-sin-envio-en-curso`), nunca con
        `hx-trigger="change"` ni «input»; el desplegable o el campo no dispara nada solo."""
        respuesta = self.get(self.contador)

        self.assertContains(respuesta, "hx-post")
        self.assertContains(respuesta, "data-sin-envio-en-curso")
        self.assertNotContains(respuesta, 'hx-trigger="change')
        self.assertNotContains(respuesta, 'hx-trigger="input')
        self.assertNotContains(respuesta, "hx-trigger=\"keyup")

    def test_paso_2_calcular_el_cierre_redibuja_el_cierre_y_conserva_lo_escrito_sin_validar(self):
        """Paso 2: «Calcular cierre» muestra el cierre previsto de la fecha elegida (inicio 15/11/2026 → 14/11/2027), conserva los importes escritos y NO valida (ni errores ni resumen), aunque
        falte el capital o el texto no sea un número; no escribe nada."""
        respuesta = self.post(_formulario(fecha="2026-11-15", accion="calcular", **{cuentas.CAJA: "abc", cuentas.CAPITAL_INICIAL: ""}), cuenta=self.contador)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "14/11/2027")
        self.assertContains(respuesta, 'value="2026-11-15"')
        self.assertContains(respuesta, 'value="abc"')
        self.assertNotContains(respuesta, "El capital inicial es obligatorio")
        self.assertNotContains(respuesta, "Confirmar e iniciar")
        self.assert_sin_nada_escrito()

    def test_paso_2_calcular_con_htmx_devuelve_solo_el_formulario_con_el_cierre_correcto_de_cada_fecha(self):
        """HTMX: el pedido de «Calcular cierre» recibe el fragmento (sin `<html>`) y el cierre previsto que muestra, dentro de `id="cierre-previsto"`, es exactamente el de la fecha escrita
        (un año menos un día; regla 5 de CON-INI-EJE): no el de hoy ni el de otra fecha. Incluye el 1 de enero, un inicio en marzo antes de un año bisiesto y el 29 de febrero."""
        casos = (("2026-11-15", "14/11/2027"), ("2027-01-01", "31/12/2027"), ("2027-03-01", "29/02/2028"), ("2028-02-29", "28/02/2029"), ("2027-03-10", "09/03/2028"))
        for fecha, cierre in casos:
            with self.subTest(fecha=fecha):
                respuesta = self.post(_formulario(fecha=fecha, accion="calcular"), cuenta=self.contador, HTTP_HX_REQUEST="true")

                contenido = respuesta.content.decode()
                self.assertNotIn("<html", contenido)
                self.assertNotIn("HX-Retarget", respuesta.headers)
                self.assertRegex(contenido, r'id="cierre-previsto"[^>]*>\s*' + cierre + r'\s*<')
                self.assertContains(respuesta, f'value="{fecha}"')
                otros = {c for _, c in casos} - {cierre}
                for otro in otros:
                    self.assertNotIn(f'id="cierre-previsto">{otro}', contenido)
        self.assert_sin_nada_escrito()

    def test_paso_2_calcular_con_una_fecha_que_no_es_fecha_no_rompe(self):
        """Paso 2: una fecha ilegible en «Calcular cierre» no da error 500: el cierre queda en blanco y se conserva lo escrito."""
        respuesta = self.post(_formulario(fecha="no-es-fecha", accion="calcular"), cuenta=self.contador)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'value="no-es-fecha"')
        self.assertRegex(respuesta.content.decode(), r'id="cierre-previsto"[^>]*>\s*—\s*<')

    # --- Paso 5: el resumen -----------------------------------------------------------------------------------------------------------------------------------

    def test_paso_5_el_resumen_muestra_el_ejercicio_el_asiento_numero_1_las_lineas_y_los_totales(self):
        """Paso 5: el ejercicio (inicio y cierre previsto), el asiento N.º 1 «Asiento de apertura» con su fecha, las líneas con su importe, el total del Debe, el del Haber y la diferencia (0);
        con «Confirmar e iniciar» y «Volver a editar»; no escribe nada."""
        respuesta = self.post(_formulario(fecha="2026-11-15"), cuenta=self.contador)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "15/11/2026")
        self.assertContains(respuesta, "14/11/2027")
        self.assertContains(respuesta, "N.º 1")
        self.assertContains(respuesta, "Asiento de apertura")
        for texto in ("Caja", "Deudores por Ventas", "Capital Inicial", "Proveedores", "$ 1.000,00", "$ 500,00", "$ 1.200,00", "$ 300,00"):
            self.assertContains(respuesta, texto)
        self.assertNotContains(respuesta, "Banco c/c")  # una línea sin importe no figura
        self.assertContains(respuesta, TOTAL)
        self.assertContains(respuesta, "Diferencia")
        self.assertContains(respuesta, "$ 0,00")
        self.assertContains(respuesta, "Confirmar e iniciar")
        self.assertContains(respuesta, "Volver a editar")
        self.assert_sin_nada_escrito()

    def test_paso_5_el_resumen_lleva_lo_escrito_para_confirmarlo_sin_volver_a_escribirlo(self):
        """Paso 5: el resumen repite la fecha y los importes en campos ocultos (sin JavaScript, «Confirmar» envía lo mismo) y la acción «editar» devuelve el formulario con lo escrito."""
        resumen = self.post(_formulario(fecha="2026-11-15"), cuenta=self.contador)
        self.assertContains(resumen, 'name="fecha_inicio" value="2026-11-15"')
        self.assertContains(resumen, f'name="importe_{cuentas.CAJA}"')

        editado = self.post(_formulario(fecha="2026-11-15", accion="editar"))

        self.assertContains(editado, 'value="2026-11-15"')
        self.assertContains(editado, 'value="1.000,00"')
        self.assertNotContains(editado, "Confirmar e iniciar")

    def test_paso_5_cada_error_vuelve_al_formulario_marcado_junto_a_su_campo_y_con_lo_escrito(self):
        """Extensiones 5a a 5e: la fecha futura, la demasiado antigua, el capital faltante, el desbalance y el importe inválido se señalan en el formulario (no en una página aparte), con los demás
        campos como estaban y sin escribir nada."""
        casos = (
            (_formulario(fecha="2027-03-11"), "La fecha de inicio no puede ser futura."),
            (_formulario(fecha="2026-03-10"), "la más antigua que se puede elegir es el 11/03/2026"),
            (_formulario(**{cuentas.CAPITAL_INICIAL: ""}), "El capital inicial es obligatorio para iniciar la contabilidad."),
            (_formulario(**{cuentas.PROVEEDORES: "250,00"}), "no coinciden: la diferencia es de $ 50,00"),
            (_formulario(**{cuentas.CAJA: "abc"}), "El importe tiene que ser un número mayor que cero, con hasta dos decimales."),
            (_formulario(**{cuentas.CAJA: "-5"}), "El importe tiene que ser un número mayor que cero, con hasta dos decimales."),
            (_formulario(fecha="no-es-fecha"), "Indicá una fecha de inicio válida."),
        )
        for datos, mensaje in casos:
            with self.subTest(mensaje=mensaje):
                respuesta = self.post(datos, cuenta=self.contador)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, mensaje)
                self.assertContains(respuesta, f'value="{datos["fecha_inicio"]}"')
                self.assertContains(respuesta, "Ver resumen")  # sigue en el formulario
                self.assertNotContains(respuesta, "Confirmar e iniciar")
                self.assert_sin_nada_escrito()

    def test_paso_5_varios_errores_se_senalan_juntos(self):
        """Cómo se aplica: con varios errores de campo (fecha futura y capital faltante) la pantalla los marca todos a la vez."""
        respuesta = self.post(_formulario(fecha="2027-03-11", **{cuentas.CAPITAL_INICIAL: ""}), cuenta=self.contador)

        self.assertContains(respuesta, "La fecha de inicio no puede ser futura.")
        self.assertContains(respuesta, "El capital inicial es obligatorio")

    def test_regla_6_una_cuenta_que_no_es_de_las_cinco_enviada_a_mano_se_ignora(self):
        """Regla 6 y regla 7: el formulario solo lee las cinco cuentas; un `importe_<otra cuenta>` escrito a mano no entra al asiento ni se muestra."""
        respuesta = self.post(_formulario(**{cuentas.INSUMOS_EN_STOCK: "999,00"}), cuenta=self.contador)

        self.assertContains(respuesta, "Confirmar e iniciar")
        self.assertNotContains(respuesta, "Insumos en Stock")
        self.assertNotContains(respuesta, "999,00")

    def test_regla_8_el_importe_se_lee_con_coma_o_con_punto(self):
        """Regla 8: «1.500,50», «1500,5» y «1500.50» valen lo mismo; el resumen lo muestra en pesos con dos decimales."""
        for escrito in ("1.500,50", "1500,5", "1500.50"):
            with self.subTest(escrito=escrito):
                respuesta = self.post(_formulario(**{cuentas.CAJA: escrito, cuentas.DEUDORES_POR_VENTAS: "0", cuentas.CAPITAL_INICIAL: "1.200,50", cuentas.PROVEEDORES: "300,00"}), cuenta=self.contador)
                self.assertContains(respuesta, "$ 1.500,50")

    # --- Pasos 6 a 8: confirmar y la confirmación --------------------------------------------------------------------------------------------------------------

    def test_pasos_6_y_7_confirmar_inicia_la_contabilidad_con_el_actor_y_redirige_a_la_confirmacion(self):
        """Pasos 6 y 7: «Confirmar e iniciar» crea el ejercicio y el asiento N.º 1 (fecha de inicio, «Asiento de apertura», cuatro movimientos), audita con el Contador y redirige (PRG) a la confirmación."""
        respuesta = self.post(_formulario(fecha="2026-11-15", accion="confirmar"), cuenta=self.contador)

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta["Location"], f"{self.url}?listo=1")
        ej = EjercicioContable.objects.get()
        self.assertEqual((ej.fecha_inicio_ejercicio, ej.fecha_cierre_ejercicio, ej.estado_ejercicio, ej.ultimo_numero_asiento), (datetime.date(2026, 11, 15), datetime.date(2027, 11, 14), Estado.ABIERTO, 1))
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.numero_asiento, asiento.descripcion_asiento, asiento.fecha_asiento, asiento.movimientos.count()), (1, "Asiento de apertura", datetime.date(2026, 11, 15), 4))
        self.assertEqual(RegistroAuditoria.objects.get(accion=Accion.ALTA_EJERCICIO_CONTABLE).usuario_id, self.contador.pk)
        verificar_invariantes_contables()

    def test_paso_8_la_confirmacion_dice_el_ejercicio_el_asiento_y_ofrece_el_libro_y_lo_que_sigue(self):
        """Paso 8: «La contabilidad quedó iniciada», con el ejercicio y el asiento N.º 1, el enlace al libro de gestión y, para el Contador, el texto que dice quién carga los insumos y los lotes
        existentes (sin enlaces que lleven a un 403, D-30); sin «Volver a la operación» si no llegó `volver`."""
        self.post(_formulario(accion="confirmar"), cuenta=self.contador)

        respuesta = self.client.get(f"{self.url}?listo=1")

        self.assertContains(respuesta, "La contabilidad quedó iniciada")
        self.assertContains(respuesta, "Ejercicio 1")
        self.assertContains(respuesta, "N.º 1")
        self.assertContains(respuesta, f'href="{reverse("contabilidad:libro")}')
        self.assertContains(respuesta, "carga inicial")
        self.assertNotContains(respuesta, reverse("produccion:registrar_lote_existente"))  # es del Agrónomo y del Gerente: el Contador no lo abre (D-30)
        self.assertNotContains(respuesta, reverse("inventario:ajuste"))  # es del Agrónomo
        self.assertNotContains(respuesta, "Volver a la operación")

    def test_paso_8_el_gerente_que_inicia_sin_contador_ve_el_enlace_a_registrar_lote_existente(self):
        """Paso 8: el Gerente (que sí abre «Registrar lote existente») lo ve como enlace; el de la carga inicial de insumos es del Agrónomo y no se enlaza."""
        self.sin_contador()
        self.post(_formulario(accion="confirmar"), cuenta=self.gerente)

        respuesta = self.client.get(f"{self.url}?listo=1")

        self.assertContains(respuesta, f'href="{reverse("produccion:registrar_lote_existente")}')
        self.assertNotContains(respuesta, reverse("inventario:ajuste"))
        self.assertEqual(RegistroAuditoria.objects.get(accion=Accion.ALTA_EJERCICIO_CONTABLE).rol, "gerente")

    def test_paso_8_con_volver_ofrece_volver_a_la_operacion(self):
        """Extensión 1b, paso 4: si llegó `?volver=<ruta>`, el formulario la lleva oculta, la redirección la conserva y la confirmación ofrece «Volver a la operación» a esa ruta."""
        ruta = "/compras/pagos/orden/3/proveedor/4/"
        formulario = self.get(self.contador, f"{self.url}?volver={ruta}")
        self.assertContains(formulario, f'name="volver" value="{ruta}"')

        respuesta = self.post({**_formulario(accion="confirmar"), "volver": ruta})
        self.assertEqual(respuesta["Location"], f"{self.url}?listo=1&volver=%2Fcompras%2Fpagos%2Forden%2F3%2Fproveedor%2F4%2F")

        confirmacion = self.client.get(respuesta["Location"])
        self.assertContains(confirmacion, "Volver a la operación")
        self.assertContains(confirmacion, f'href="{ruta}"')

    def test_paso_8_un_volver_de_otro_sitio_se_descarta(self):
        """Seguridad (redirección abierta): un `volver` que no es una ruta del mismo sitio no se guarda en el formulario ni se ofrece."""
        for malo in ("http://otro-sitio.example/x", "//otro-sitio.example/x", "javascript:alert(1)", "https://testserver.evil.example/"):
            with self.subTest(volver=malo):
                self.assertNotContains(self.get(self.contador, f"{self.url}?volver={malo}"), 'name="volver"')
        self.assert_sin_nada_escrito()
        self.post(_formulario(accion="confirmar"))  # con la contabilidad iniciada la confirmación existe: ahí tampoco se ofrece un `volver` ajeno
        for malo in ("http://otro-sitio.example/x", "//otro-sitio.example/x", "javascript:alert(1)", "https://testserver.evil.example/"):
            with self.subTest(volver_en_la_confirmacion=malo):
                self.assertNotContains(self.client.get(f"{self.url}?listo=1&volver={malo}"), "Volver a la operación")

    def test_ext_2a_con_la_contabilidad_iniciada_se_muestra_el_aviso_y_no_el_formulario(self):
        """Extensión 2a: con un ejercicio (en cualquier estado) la pantalla dice «La contabilidad ya está iniciada», con el enlace a «Ejercicios» y sin formulario; también al enviar (no crea otro)."""
        for estado in (Estado.ABIERTO, Estado.EN_CIERRE, Estado.CERRADO):
            with self.subTest(estado=estado):
                EjercicioContable.objects.all().delete()
                ejercicio(estado, datetime.date(2026, 1, 1))
                for respuesta in (self.get(self.contador), self.post(_formulario(accion="confirmar"))):
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertContains(respuesta, "La contabilidad ya está iniciada")
                    self.assertContains(respuesta, reverse("contabilidad:ejercicios"))
                    self.assertNotContains(respuesta, 'name="fecha_inicio"')
                self.assertEqual(EjercicioContable.objects.count(), 1)
                self.assertFalse(AsientoContable.objects.exists())

    def test_ext_2a_enviar_dos_veces_el_mismo_formulario_no_duplica(self):
        """Extensión 2a: reenviar «Confirmar» (doble clic, o recargar el POST) no crea otro ejercicio ni otro asiento: la segunda vez muestra «ya está iniciada»."""
        self.post(_formulario(accion="confirmar"), cuenta=self.contador)

        segunda = self.post(_formulario(accion="confirmar"))

        self.assertContains(segunda, "La contabilidad ya está iniciada")
        self.assertEqual((EjercicioContable.objects.count(), AsientoContable.objects.count()), (1, 1))

    def test_ext_7a_si_otro_inicio_a_la_vez_la_pantalla_dice_que_ya_esta_iniciada(self):
        """Extensión 7a: si al confirmar otro ya inició (el servicio lanza `contabilidad_ya_iniciada`), la pantalla muestra «ya está iniciada» y no un error."""
        error = ErrorContable("contabilidad_ya_iniciada", "La contabilidad ya está iniciada: ya existe un ejercicio contable.")
        with mock.patch.object(ejercicios, "iniciar_ejercicio", side_effect=error):
            respuesta = self.post(_formulario(accion="confirmar"), cuenta=self.contador)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "La contabilidad ya está iniciada")

    def test_ext_7b_si_una_cuenta_ya_no_existe_vuelve_al_formulario_con_el_mensaje(self):
        """Extensión 7b: si una cuenta del asiento desapareció del plan, la pantalla vuelve al formulario (paso 3) con el mensaje y lo escrito; no queda nada."""
        CuentaContable.objects.filter(codigo_cuenta=cuentas.DEUDORES_POR_VENTAS).delete()

        respuesta = self.post(_formulario(accion="confirmar"), cuenta=self.contador)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, cuentas.DEUDORES_POR_VENTAS)
        self.assertContains(respuesta, "no existe en el plan de cuentas")
        self.assertContains(respuesta, 'value="1.000,00"')
        self.assert_sin_nada_escrito()

    def test_confirmar_con_datos_invalidos_no_inicia(self):
        """Pasos 6 y 7: aunque se envíe «confirmar» sin haber pasado por el resumen, los datos inválidos no inician (desbalance): vuelve al formulario con el error."""
        respuesta = self.post(_formulario(accion="confirmar", **{cuentas.PROVEEDORES: "250,00"}), cuenta=self.contador)

        self.assertContains(respuesta, "no coinciden")
        self.assert_sin_nada_escrito()

    def test_extension_a_cancelar_no_escribe_nada(self):
        """Extensión *a: abrir la pantalla, calcular, ver el resumen y volver a editar sin confirmar no deja ejercicio, asiento ni auditoría."""
        self.get(self.contador)
        self.post(_formulario(accion="calcular"))
        self.post(_formulario(accion="revisar"))
        self.post(_formulario(accion="editar"))

        self.assert_sin_nada_escrito()

    def test_el_listo_sin_ejercicio_no_dice_que_quedo_iniciada(self):
        """El `?listo=1` escrito a mano sin ejercicio no afirma nada falso: muestra el formulario."""
        respuesta = self.get(self.contador, f"{self.url}?listo=1")

        self.assertNotContains(respuesta, "La contabilidad quedó iniciada")
        self.assertContains(respuesta, 'name="fecha_inicio"')

    def test_el_formulario_funciona_sin_javascript_y_sin_csrf_oculto_por_error(self):
        """Sin JavaScript todo son botones de un formulario POST con token CSRF; Enter dispara «Ver resumen» (el primer botón)."""
        respuesta = self.get(self.contador)

        self.assertContains(respuesta, "csrfmiddlewaretoken")
        self.assertContains(respuesta, 'method="post"')
        self.assertContains(respuesta, 'name="accion" value="revisar"')


class ConIniEjeEntradasTests(ConIniEjeVistaBase):
    """Las entradas a la pantalla (pestaña «Ejercicios», libro vacío, «Registrar asiento») y lo que se oculta sin ejercicio (D-30)."""

    def test_la_pestana_ejercicios_sin_ejercicio_ofrece_iniciar_al_responsable(self):
        """Pantallas: «Ejercicios» sin ningún ejercicio: el Contador (y el Gerente sin Contador) ven el botón «Iniciar ejercicio»; el texto viejo del comando ya no está."""
        respuesta = self.get(self.contador, reverse("contabilidad:ejercicios"))

        self.assertContains(respuesta, "Todavía no hay ejercicios contables")
        self.assertContains(respuesta, "Iniciar ejercicio")
        self.assertContains(respuesta, f'href="{self.url}"')
        self.assertNotContains(respuesta, "poner_en_marcha")
        self.sin_contador()
        self.assertContains(self.get(self.gerente, reverse("contabilidad:ejercicios")), f'href="{self.url}"')

    def test_la_pestana_ejercicios_sin_ejercicio_no_ofrece_iniciar_al_gerente_con_contador(self):
        """D-30: el Gerente con un Contador activo no ve el botón (llevaría a un 403); ve «La contabilidad todavía no está iniciada»."""
        respuesta = self.get(self.gerente, reverse("contabilidad:ejercicios"))

        self.assertContains(respuesta, "La contabilidad todavía no está iniciada")
        self.assertNotContains(respuesta, f'href="{self.url}"')
        self.assertNotContains(respuesta, "Iniciar ejercicio")

    def test_el_libro_vacio_ofrece_iniciar_y_oculta_registrar_asiento(self):
        """Pantallas: el libro sin ejercicio muestra «Iniciar ejercicio» al responsable (y «La contabilidad todavía no está iniciada» al Gerente con Contador) y NO muestra «Registrar asiento»."""
        libro = reverse("contabilidad:libro")
        for cuenta, boton in ((self.contador, True), (self.gerente, False)):
            with self.subTest(cuenta=cuenta.email):
                respuesta = self.get(cuenta, libro)
                self.assertContains(respuesta, "Todavía no hay ejercicios contables")
                self.assertNotContains(respuesta, "Registrar asiento")
                self.assertNotContains(respuesta, reverse("contabilidad:asiento_nuevo"))
                if boton:
                    self.assertContains(respuesta, f'href="{self.url}"')
                else:
                    self.assertContains(respuesta, "La contabilidad todavía no está iniciada")
                    self.assertNotContains(respuesta, f'href="{self.url}"')

    def test_con_ejercicio_el_libro_ofrece_registrar_asiento_y_no_iniciar(self):
        """Contrapunto: con un ejercicio el libro vuelve a ofrecer «Registrar asiento» y desaparece el acceso a iniciar."""
        ejercicio_abierto(datetime.date(2027, 1, 1))

        respuesta = self.get(self.contador, reverse("contabilidad:libro"))

        self.assertContains(respuesta, "Registrar asiento")
        self.assertNotContains(respuesta, f'href="{self.url}"')

    def test_registrar_asiento_abierto_a_mano_sin_ejercicio_explica_y_ofrece_iniciar(self):
        """CON-REG-ASI y regla 9: abrir «Registrar asiento» sin ejercicio (GET) no muestra el formulario: dice «La contabilidad todavía no está iniciada» y ofrece «Iniciar ejercicio» al responsable."""
        nuevo = reverse("contabilidad:asiento_nuevo")
        respuesta = self.get(self.contador, nuevo)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "La contabilidad todavía no está iniciada")
        self.assertContains(respuesta, f'href="{self.url}"')
        self.assertNotContains(respuesta, 'name="fila"')
        self.assertNotContains(respuesta, "Revisar asiento")
        self.sin_contador()
        self.assertContains(self.get(self.gerente, nuevo), f'href="{self.url}"')

    def test_registrar_asiento_sin_ejercicio_para_el_gerente_con_contador_sigue_diciendo_que_lo_registra_el_contador(self):
        """Quien no puede registrar sigue viendo «Lo registra el Contador» (el motivo que ya existía, D-30), no el de contabilidad no iniciada."""
        respuesta = self.get(self.gerente, reverse("contabilidad:asiento_nuevo"))

        self.assertContains(respuesta, "Lo registra el Contador")
        self.assertNotContains(respuesta, f'href="{self.url}"')

    def test_extension_3a_quitada_el_atajo_de_apertura_ya_no_se_ofrece_pero_el_de_venta_previa_si(self):
        """CON-REG-ASI, extensión 3a quitada (CON-05): la pantalla de «Registrar asiento» no ofrece «Asiento de apertura» (la apertura es CON-INI-EJE); «Venta de producción previa» (3b) sigue."""
        ejercicio_abierto(datetime.date(2027, 1, 1))

        respuesta = self.get(self.contador, reverse("contabilidad:asiento_nuevo"))

        self.assertNotContains(respuesta, "atajo:apertura")
        self.assertNotContains(respuesta, ">Asiento de apertura<")
        self.assertContains(respuesta, "atajo:venta_previa")

    def test_extension_3a_quitada_enviar_el_atajo_de_apertura_a_mano_no_precarga_nada(self):
        """CON-REG-ASI, extensión 3a quitada: un POST con `accion=atajo:apertura` escrito a mano no precarga la descripción ni las cuentas (se trata como una acción desconocida) y no registra nada."""
        ejercicio_abierto(datetime.date(2027, 1, 1))
        self.entrar(self.contador)

        respuesta = self.client.post(reverse("contabilidad:asiento_nuevo"), {"accion": "atajo:apertura", "fecha": "2027-03-10", "descripcion": "", "fila": ["0", "1"], "cuenta_0": "", "tipo_0": "D", "importe_0": "", "cuenta_1": "", "tipo_1": "H", "importe_1": ""})

        self.assertNotContains(respuesta, 'value="Asiento de apertura"')
        self.assertFalse(AsientoContable.objects.exists())
