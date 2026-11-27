# Pruebas de `registrar_asiento_automatico` (CON-02 paso 4; D-86, D-84 puntos 4, 5, 6 y 9; docs/api/asientos.md): cada error, el importe cero, el
# todo o nada, la numeración, la auditoría, la autorrecuperación, el ejercicio destino y la aclaración de la fecha (H10). Las lecturas del
# libro están en `test_libro.py` y la concurrencia en `test_asientos_concurrencia.py`. Cada prueba arma sus propios datos.
import datetime
from decimal import Decimal
from unittest import mock

from django.db import transaction
from django.test import TestCase

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable, MovimientoContable
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import (
    PlanDeCuentasMixin,
    ejercicio,
    ejercicio_abierto,
    origen_de_prueba,
    verificar_invariantes_contables,
)
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente

Estado = EjercicioContable.Estado
INICIO = datetime.date(2027, 1, 1)
HOY = datetime.date(2027, 6, 15)
MOVIMIENTOS = [
    (cuentas.INSUMOS_EN_STOCK, DEBE, Decimal("3000.00")),
    (cuentas.PROVEEDORES, HABER, Decimal("3000.00")),
]


class FalloDePrueba(Exception):
    """Fallo forzado en una prueba de «todo o nada»: una clase propia, para que ningún otro error (por ejemplo `NotImplementedError`,
    que es un `RuntimeError`) pase la prueba sin querer."""


def _registrar(origen=None, fecha=HOY, movimientos=MOVIMIENTOS, actor=None, **extra):
    """Llama al servicio con `hoy=HOY` y, si no se pasa, un origen nuevo."""
    return asientos.registrar_asiento_automatico(
        actor, origen or origen_de_prueba(), fecha, movimientos, **{"hoy": HOY, **extra}
    )


def _sin_nada_escrito(prueba):
    """Verifica que no quedó ningún asiento, movimiento ni auditoría contable y que la numeración no se consumió."""
    prueba.assertFalse(AsientoContable.objects.exists())
    prueba.assertFalse(MovimientoContable.objects.exists())
    prueba.assertEqual(EjercicioContable.objects.get(estado_ejercicio=Estado.ABIERTO).ultimo_numero_asiento, 0)
    prueba.assertFalse(RegistroAuditoria.objects.filter(accion__in=[
        RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE, RegistroAuditoria.Accion.ALTA_MOVIMIENTO_CONTABLE]).exists())


class AsientoAutomaticoErroresTests(PlanDeCuentasMixin, TestCase):
    """D-86 punto 3 y docs/api/asientos.md: los errores de programación del servicio, todos con `ErrorContable` y sin escribir nada."""

    def setUp(self):
        ejercicio_abierto(INICIO)

    def _codigo_del_error(self, **llamada):
        with self.assertRaises(ErrorContable) as contexto:
            _registrar(**llamada)
        return contexto.exception

    def test_regla_asiento_desbalanceado_cuando_debe_no_es_igual_a_haber(self):
        """D-86 punto 3: Debe ≠ Haber lanza `asiento_desbalanceado` y no deja nada escrito."""
        error = self._codigo_del_error(
            movimientos=[(cuentas.INSUMOS_EN_STOCK, DEBE, Decimal("3000.00")), (cuentas.PROVEEDORES, HABER, Decimal("2999.99"))]
        )

        self.assertEqual(error.codigo, "asiento_desbalanceado")
        _sin_nada_escrito(self)

    def test_regla_asiento_desbalanceado_con_varias_lineas_que_no_suman_igual(self):
        """D-86 punto 3: la comparación es entre las SUMAS de cada lado (dos Debe contra un Haber)."""
        asiento = _registrar(
            movimientos=[
                (cuentas.CAJA, DEBE, Decimal("40.00")),
                (cuentas.BANCO, DEBE, Decimal("60.00")),
                (cuentas.VENTAS, HABER, Decimal("100.00")),
            ]
        )
        self.assertEqual(asiento.movimientos.count(), 3)

        error = self._codigo_del_error(
            movimientos=[
                (cuentas.CAJA, DEBE, Decimal("40.00")),
                (cuentas.BANCO, DEBE, Decimal("60.00")),
                (cuentas.VENTAS, HABER, Decimal("99.00")),
            ]
        )
        self.assertEqual(error.codigo, "asiento_desbalanceado")

    def test_regla_cuenta_inexistente_lanza_el_error_con_el_codigo_que_no_existe(self):
        """D-86 punto 3: un código de cuenta que no existe lanza `cuenta_inexistente` (el mensaje nombra el código)."""
        error = self._codigo_del_error(
            movimientos=[("9.9.99", DEBE, Decimal("10.00")), (cuentas.PROVEEDORES, HABER, Decimal("10.00"))]
        )

        self.assertEqual(error.codigo, "cuenta_inexistente")
        self.assertIn("9.9.99", error.mensaje)
        _sin_nada_escrito(self)

    def test_regla_cuenta_inexistente_se_detecta_aunque_el_importe_sea_cero(self):
        """D-86 punto 3: un error de programación aparece siempre, también en una línea de importe cero que se omitiría."""
        error = self._codigo_del_error(
            movimientos=[
                (cuentas.CAJA, DEBE, Decimal("10.00")),
                (cuentas.VENTAS, HABER, Decimal("10.00")),
                ("9.9.99", DEBE, Decimal("0.00")),
            ]
        )

        self.assertEqual(error.codigo, "cuenta_inexistente")

    def test_regla_origen_con_asiento_cuando_el_origen_ya_tiene_su_asiento(self):
        """D-86 punto 5 y R012: un origen, un asiento; la segunda llamada con el mismo origen lanza `origen_con_asiento`."""
        origen = origen_de_prueba()
        _registrar(origen=origen)

        error = self._codigo_del_error(origen=origen)

        self.assertEqual(error.codigo, "origen_con_asiento")
        self.assertEqual(AsientoContable.objects.count(), 1)
        self.assertEqual(EjercicioContable.objects.get().ultimo_numero_asiento, 1)
        verificar_invariantes_contables()

    def test_regla_importe_invalido_negativo_con_demasiados_decimales_o_que_no_es_decimal(self):
        """docs/api/asientos.md: `importe_invalido` si es negativo, tiene más de dos decimales o no es `Decimal` (nunca `float`)."""
        for importe in (Decimal("-1.00"), Decimal("1.001"), 1.5, "10.00", Decimal("NaN"), Decimal("1234567890123.00")):
            with self.subTest(importe=importe):
                error = self._codigo_del_error(movimientos=[(cuentas.CAJA, DEBE, importe), (cuentas.VENTAS, HABER, Decimal("10.00"))])
                self.assertEqual(error.codigo, "importe_invalido")
        _sin_nada_escrito(self)

    def test_regla_importe_con_ceros_de_mas_a_la_derecha_es_valido(self):
        """docs/api/asientos.md: «con dos decimales»: `Decimal("10.500")` vale 10,50 y es válido (no hay más de dos decimales significativos)."""
        asiento = _registrar(movimientos=[(cuentas.CAJA, DEBE, Decimal("10.500")), (cuentas.VENTAS, HABER, Decimal("10.50"))])

        self.assertEqual(list(asiento.movimientos.values_list("importe_movimiento", flat=True)), [Decimal("10.50"), Decimal("10.50")])

    def test_regla_tipo_de_movimiento_invalido(self):
        """docs/api/asientos.md: el tipo es `"D"` o `"H"`; cualquier otro lanza `tipo_de_movimiento_invalido`."""
        for tipo in ("X", "d", "Debe", None):
            with self.subTest(tipo=tipo):
                error = self._codigo_del_error(
                    movimientos=[(cuentas.CAJA, tipo, Decimal("10.00")), (cuentas.VENTAS, HABER, Decimal("10.00"))]
                )
                self.assertEqual(error.codigo, "tipo_de_movimiento_invalido")
        _sin_nada_escrito(self)


class AsientoAutomaticoImporteCeroTests(PlanDeCuentasMixin, TestCase):
    """D-84 punto 6 (H11): los movimientos de importe 0 se omiten y con menos de dos movimientos no hay asiento (devuelve `None`)."""

    def setUp(self):
        ejercicio_abierto(INICIO)

    def test_regla_h11_las_lineas_de_importe_cero_se_omiten(self):
        """D-84 punto 6: los movimientos de importe 0 se omiten; el asiento se crea con los demás."""
        asiento = _registrar(
            movimientos=[
                (cuentas.CAJA, DEBE, Decimal("100.00")),
                (cuentas.VENTAS, HABER, Decimal("100.00")),
                (cuentas.BANCO, DEBE, Decimal("0.00")),
                (cuentas.OTROS_INGRESOS, HABER, Decimal("0")),
            ]
        )

        self.assertEqual(asiento.movimientos.count(), 2)
        self.assertEqual(sorted(asiento.movimientos.values_list("cuenta__codigo_cuenta", flat=True)), [cuentas.CAJA, cuentas.VENTAS])

    def test_regla_h11_todo_en_cero_no_registra_asiento_ni_falla(self):
        """D-84 punto 6 y API: con todos los importes en cero devuelve `None`, sin asiento, sin auditoría y sin consumir número."""
        resultado = _registrar(
            movimientos=[(cuentas.CAJA, DEBE, Decimal("0.00")), (cuentas.VENTAS, HABER, Decimal("0.00"))]
        )

        self.assertIsNone(resultado)
        _sin_nada_escrito(self)

    def test_regla_h11_con_un_solo_movimiento_no_nulo_no_hay_asiento(self):
        """D-84 punto 6: con menos de dos movimientos (después de omitir los de cero) no hay asiento y no es un error."""
        resultado = _registrar(
            movimientos=[(cuentas.CAJA, DEBE, Decimal("100.00")), (cuentas.VENTAS, HABER, Decimal("0.00"))]
        )

        self.assertIsNone(resultado)
        _sin_nada_escrito(self)

    def test_regla_h11_sin_movimientos_no_hay_asiento(self):
        """D-84 punto 6: una lista vacía tampoco genera asiento."""
        self.assertIsNone(_registrar(movimientos=[]))
        _sin_nada_escrito(self)

    def test_regla_h11_el_origen_sigue_libre_si_no_hubo_asiento(self):
        """D-86 punto 5: si no hubo asiento por importe cero, el origen no queda con asiento (se puede asentar después)."""
        origen = origen_de_prueba()
        self.assertIsNone(_registrar(origen=origen, movimientos=[(cuentas.CAJA, DEBE, Decimal("0.00")), (cuentas.VENTAS, HABER, Decimal("0.00"))]))

        self.assertIsNotNone(_registrar(origen=origen))


class AsientoAutomaticoTodoONadaTests(PlanDeCuentasMixin, TestCase):
    """docs/patrones/asientos.md, sección 4 («todo o nada») y D-22: el asiento, sus movimientos y su auditoría, de una vez o ninguno."""

    def setUp(self):
        ejercicio_abierto(INICIO)

    def test_regla_si_falla_la_ultima_auditoria_no_queda_ningun_asiento(self):
        """D-86 punto 2 y D-22: si falla un registro de auditoría ya creados el asiento y sus movimientos, no queda nada (ni el número)."""
        original = RegistroAuditoria.objects.registrar
        llamadas = []

        def falla_en_la_ultima(*args, **kwargs):
            llamadas.append(args)
            if len(llamadas) == 3:  # 1 = el asiento, 2 y 3 = sus dos movimientos
                raise FalloDePrueba("falló la auditoría del último movimiento")
            return original(*args, **kwargs)

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=falla_en_la_ultima):
            with self.assertRaises(FalloDePrueba):
                _registrar()

        self.assertEqual(len(llamadas), 3)
        _sin_nada_escrito(self)

    def test_regla_si_falla_el_caso_de_uso_despues_del_asiento_no_queda_el_asiento(self):
        """D-86 punto 2: corre dentro de la transacción de quien llama; si ese caso de uso falla después, el asiento se deshace."""
        origen = origen_de_prueba()
        with self.assertRaises(FalloDePrueba):
            with transaction.atomic():
                self.assertIsNotNone(_registrar(origen=origen))  # el asiento SÍ se creó dentro de la transacción de quien llama
                raise FalloDePrueba("falló el caso de uso")

        _sin_nada_escrito(self)
        self.assertIsNotNone(_registrar(origen=origen))  # y el origen quedó libre


class AsientoAutomaticoRegistroTests(PlanDeCuentasMixin, TestCase):
    """D-86 y D-84 puntos 4 y 9: el asiento creado, su numeración y su auditoría."""

    def setUp(self):
        self.ejercicio = ejercicio_abierto(INICIO)

    def test_flujo_principal_crea_el_asiento_con_origen_ejercicio_y_movimientos_exactos(self):
        """D-86 punto 1: el asiento queda con el origen correcto, el ejercicio esperado, la fecha del hecho y los movimientos exactos."""
        origen = origen_de_prueba()
        fecha = datetime.date(2027, 6, 10)

        asiento = _registrar(origen=origen, fecha=fecha)

        asiento.refresh_from_db()
        self.assertEqual(asiento.origen_id, origen.pk)
        self.assertEqual(asiento.ejercicio_id, self.ejercicio.pk)
        self.assertEqual(asiento.fecha_asiento, fecha)  # la fecha del HECHO (H10), no la de hoy
        self.assertEqual(asiento.descripcion_asiento, "")
        self.assertEqual(asiento.tipo, AsientoContable.Tipo.AUTOMATICO)
        self.assertEqual(origen.asiento_contable.pk, asiento.pk)
        self.assertEqual(
            [(m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.order_by("id")],
            [("1.1.04", "D", Decimal("3000.00")), ("2.1.01", "H", Decimal("3000.00"))],
        )
        verificar_invariantes_contables()

    def test_regla_una_descripcion_del_que_llama_se_guarda_tal_cual_si_no_hay_aclaracion(self):
        """docs/api/asientos.md: `descripcion` es opcional en un asiento automático; sin redirección de fecha se guarda tal cual."""
        asiento = _registrar(descripcion="Recepción N.º 7")

        self.assertEqual(asiento.descripcion_asiento, "Recepción N.º 7")

    def test_regla_h8_la_numeracion_es_correlativa_sin_huecos(self):
        """H8 y D-84 punto 4: números 1, 2, 3 en orden de registro (no de fecha) y `ultimo_numero_asiento` los acompaña."""
        primero = _registrar(fecha=datetime.date(2027, 6, 10))
        segundo = _registrar(fecha=datetime.date(2027, 2, 1))  # fecha anterior: igual toma el 2
        tercero = _registrar()

        self.assertEqual([primero.numero_asiento, segundo.numero_asiento, tercero.numero_asiento], [1, 2, 3])
        self.ejercicio.refresh_from_db()
        self.assertEqual(self.ejercicio.ultimo_numero_asiento, 3)
        verificar_invariantes_contables()

    def test_regla_h8_un_rechazo_no_consume_numero(self):
        """H8 (sin huecos): un asiento rechazado por desbalanceado no consume un número."""
        _registrar()
        with self.assertRaises(ErrorContable):
            _registrar(movimientos=[(cuentas.CAJA, DEBE, Decimal("5.00")), (cuentas.VENTAS, HABER, Decimal("4.00"))])
        siguiente = _registrar()

        self.assertEqual(siguiente.numero_asiento, 2)
        verificar_invariantes_contables()

    def test_regla_h8_cada_ejercicio_numera_por_su_cuenta(self):
        """H8 y regla 6 de CON-ABR-EJE: el número se reinicia en cada ejercicio; uno en cierre y el abierto numeran aparte."""
        self.ejercicio.delete()
        en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        abierto = ejercicio_abierto(INICIO)

        en_el_viejo = _registrar(fecha=datetime.date(2026, 12, 20))
        en_el_nuevo = _registrar()
        otro_en_el_viejo = _registrar(fecha=datetime.date(2026, 12, 21))

        self.assertEqual((en_el_viejo.ejercicio_id, en_el_viejo.numero_asiento), (en_cierre.pk, 1))
        self.assertEqual((en_el_nuevo.ejercicio_id, en_el_nuevo.numero_asiento), (abierto.pk, 1))
        self.assertEqual((otro_en_el_viejo.ejercicio_id, otro_en_el_viejo.numero_asiento), (en_cierre.pk, 2))
        verificar_invariantes_contables()

    def test_regla_d84_punto_5_en_cierre_acepta_cualquier_fecha_de_su_rango_con_su_fecha_real(self):
        """D-84 punto 5: «en cierre» acepta cualquier asiento con fecha en su rango; el asiento conserva su fecha y no se aclara nada."""
        self.ejercicio.delete()
        ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        ejercicio_abierto(INICIO)

        asiento = _registrar(fecha=datetime.date(2026, 11, 3), descripcion="")

        self.assertEqual(asiento.fecha_asiento, datetime.date(2026, 11, 3))
        self.assertEqual(asiento.descripcion_asiento, "")

    def test_post_audita_el_asiento_y_cada_movimiento_con_el_actor(self):
        """D-84 punto 9 y D-86 punto 4: un registro `alta_asiento_contable` y uno `alta_movimiento_contable` por cada movimiento, con el actor."""
        actor = crear_gerente()
        origen = origen_de_prueba()

        asiento = _registrar(origen=origen, actor=actor, fecha=datetime.date(2027, 6, 10))

        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE)
        self.assertEqual((registro.usuario_id, registro.rol), (actor.pk, "gerente"))
        self.assertEqual(
            [(a["modelo"], a["id"]) for a in registro.afectados],
            [("contabilidad.asientocontable", asiento.pk), ("contabilidad.origendocumento", origen.pk)],
        )
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "numero_asiento": {"antes": None, "despues": 1},
                "fecha_asiento": {"antes": None, "despues": "2027-06-10"},
                "descripcion_asiento": {"antes": None, "despues": ""},
                "ejercicio": {"antes": None, "despues": {"id": self.ejercicio.pk, "texto": str(self.ejercicio)}},
                "origen": {"antes": None, "despues": {"id": origen.pk, "texto": str(origen)}},
            },
        )
        movimientos = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA_MOVIMIENTO_CONTABLE).order_by("id")
        self.assertEqual(movimientos.count(), 2)
        primero, segundo = list(movimientos)
        self.assertEqual(
            primero.detalle["cambios"],
            {
                "cuenta_contable": {"antes": None, "despues": {"id": asiento.movimientos.order_by("id")[0].cuenta_id, "texto": "1.1.04 Insumos en Stock"}},
                "tipo_movimiento": {"antes": None, "despues": "D"},
                "importe_movimiento": {"antes": None, "despues": "3000.00"},
            },
        )
        self.assertEqual(segundo.detalle["cambios"]["tipo_movimiento"], {"antes": None, "despues": "H"})
        self.assertEqual(segundo.detalle["cambios"]["importe_movimiento"], {"antes": None, "despues": "3000.00"})
        self.assertEqual(
            [(a["modelo"], a["id"]) for a in primero.afectados],
            [("contabilidad.movimientocontable", asiento.movimientos.order_by("id")[0].pk), ("contabilidad.asientocontable", asiento.pk)],
        )
        self.assertEqual((primero.usuario_id, segundo.usuario_id), (actor.pk, actor.pk))

    def test_post_sin_actor_la_auditoria_es_de_infoponia(self):
        """D-84 punto 9: con `actor=None` (el paso diario) los registros se guardan con actor `None` y rol «infoponia»."""
        _registrar(actor=None)

        for accion in (RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE, RegistroAuditoria.Accion.ALTA_MOVIMIENTO_CONTABLE):
            for registro in RegistroAuditoria.objects.filter(accion=accion):
                self.assertIsNone(registro.usuario)
                self.assertEqual(registro.rol, "infoponia")

    def test_regla_un_origen_que_no_esta_guardado_es_un_error_de_uso(self):
        """docs/api/asientos.md: el origen es una instancia YA guardada; una sin guardar lanza `ValueError` y no escribe nada."""
        from contabilidad.models import OrigenDocumento

        with self.assertRaises(ValueError):
            _registrar(origen=OrigenDocumento(tipo=OrigenDocumento.Tipo.BITACORA))

        _sin_nada_escrito(self)


class AsientoAutomaticoAutorrecuperacionTests(PlanDeCuentasMixin, TestCase):
    """CON-ABR-EJE regla 5 y D-84 puntos 2 y 3 (H9): antes de registrar, el servicio abre el ejercicio si venció o si todavía no hay ninguno."""

    def test_regla_5_si_el_abierto_vencio_lo_recupera_y_asienta_en_el_nuevo(self):
        """Regla 5 de CON-ABR-EJE: con el abierto vencido y el paso diario sin correr, el asiento de hoy va al ejercicio nuevo, número 1."""
        viejo = ejercicio_abierto(INICIO)
        hoy = datetime.date(2028, 2, 10)

        asiento = asientos.registrar_asiento_automatico(None, origen_de_prueba(), hoy, MOVIMIENTOS, hoy=hoy)

        viejo.refresh_from_db()
        self.assertEqual(viejo.estado_ejercicio, Estado.EN_CIERRE)
        nuevo = EjercicioContable.objects.get(estado_ejercicio=Estado.ABIERTO)
        self.assertEqual(nuevo.fecha_inicio_ejercicio, datetime.date(2028, 1, 1))
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento, asiento.fecha_asiento), (nuevo.pk, 1, hoy))
        verificar_invariantes_contables()

    def test_regla_5_un_hecho_del_ejercicio_que_paso_a_en_cierre_va_a_ese_ejercicio(self):
        """D-84 punto 5 y H10: tras la recuperación, un hecho con fecha del ejercicio ahora «en cierre» entra a ese, con su fecha real."""
        viejo = ejercicio_abierto(INICIO)
        hoy = datetime.date(2028, 2, 10)

        asiento = asientos.registrar_asiento_automatico(None, origen_de_prueba(), datetime.date(2027, 12, 20), MOVIMIENTOS, hoy=hoy)

        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento), (viejo.pk, 1))
        self.assertEqual(asiento.fecha_asiento, datetime.date(2027, 12, 20))
        self.assertEqual(asiento.descripcion_asiento, "")

    def test_regla_9_sin_ningun_ejercicio_no_crea_el_primero_y_lanza_contabilidad_no_iniciada(self):
        """Regla 9 de CON-INI-EJE (CON-05; reemplaza la prueba de D-84 punto 3, «la primera operación crea el primer ejercicio»): sin ejercicio
        no se crea ninguno ni se asienta, y se lanza `contabilidad_no_iniciada`."""
        with self.assertRaises(ErrorContable) as contexto:
            _registrar(fecha=HOY)

        self.assertEqual(contexto.exception.codigo, "contabilidad_no_iniciada")
        self.assertFalse(EjercicioContable.objects.exists())
        self.assertFalse(AsientoContable.objects.exists())


class AsientoAutomaticoFechaTests(PlanDeCuentasMixin, TestCase):
    """D-84 punto 5 y H10 (decisión de esta tarea): el asiento AUTOMÁTICO nunca se rechaza por la fecha; si cae en un ejercicio cerrado, es anterior al
    primer ejercicio o es futura, va al ejercicio abierto con la fecha de hoy y la descripción aclara la fecha real."""

    def setUp(self):
        self.cerrado = ejercicio(Estado.CERRADO, datetime.date(2026, 1, 1))
        self.abierto = ejercicio_abierto(INICIO)

    def test_regla_h10_la_fecha_en_un_ejercicio_cerrado_va_al_abierto_con_la_fecha_de_hoy(self):
        """D-84 punto 5: fecha en un ejercicio CERRADO ⇒ ejercicio abierto, `fecha_asiento` = hoy, y la descripción aclara la fecha real."""
        asiento = _registrar(fecha=datetime.date(2026, 3, 15))

        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento), (self.abierto.pk, HOY))
        self.assertEqual(
            asiento.descripcion_asiento,
            "Fecha del hecho: 15/03/2026 (el ejercicio de esa fecha ya está cerrado); se registra con la fecha de hoy.",
        )

    def test_regla_h10_la_fecha_anterior_al_primer_ejercicio_va_al_abierto(self):
        """Decisión de CON-02: una fecha anterior al primer ejercicio también va al abierto, con el motivo «anterior al primer ejercicio»."""
        asiento = _registrar(fecha=datetime.date(2025, 12, 31))

        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento), (self.abierto.pk, HOY))
        self.assertEqual(
            asiento.descripcion_asiento,
            "Fecha del hecho: 31/12/2025 (anterior al primer ejercicio); se registra con la fecha de hoy.",
        )

    def test_regla_h10_la_fecha_futura_va_al_abierto_con_la_fecha_de_hoy(self):
        """Decisión de CON-02: una fecha futura (posterior a hoy) va al abierto con la fecha de hoy, motivo «posterior a la fecha de hoy»."""
        asiento = _registrar(fecha=datetime.date(2027, 9, 1))  # dentro del rango del abierto, pero después de hoy

        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento), (self.abierto.pk, HOY))
        self.assertEqual(
            asiento.descripcion_asiento,
            "Fecha del hecho: 01/09/2027 (posterior a la fecha de hoy); se registra con la fecha de hoy.",
        )

    def test_regla_h10_la_descripcion_de_quien_llama_va_primero_separada_por_raya(self):
        """Decisión de CON-02: la descripción de quien llama va primero y la aclaración después, separadas por « — »."""
        asiento = _registrar(fecha=datetime.date(2026, 3, 15), descripcion="Recepción N.º 7")

        self.assertEqual(
            asiento.descripcion_asiento,
            "Recepción N.º 7 — Fecha del hecho: 15/03/2026 (el ejercicio de esa fecha ya está cerrado); se registra con la fecha de hoy.",
        )

    def test_regla_h10_si_se_pasa_de_300_se_recorta_la_descripcion_de_quien_llama_nunca_la_aclaracion(self):
        """Decisión de CON-02: el total no pasa de 300 caracteres; se recorta la descripción de quien llama (termina en «…») y la aclaración queda entera."""
        aclaracion = "Fecha del hecho: 15/03/2026 (el ejercicio de esa fecha ya está cerrado); se registra con la fecha de hoy."

        asiento = _registrar(fecha=datetime.date(2026, 3, 15), descripcion="x" * 400)

        self.assertEqual(len(asiento.descripcion_asiento), 300)
        self.assertTrue(asiento.descripcion_asiento.endswith(" — " + aclaracion))
        propia = asiento.descripcion_asiento[: -len(" — " + aclaracion)]
        self.assertEqual(propia, "x" * (len(propia) - 1) + "…")

    def test_regla_h10_una_descripcion_justa_no_se_recorta(self):
        """Decisión de CON-02: si cabe exacto en 300 caracteres, no se recorta (ni se agrega «…»)."""
        aclaracion = "Fecha del hecho: 15/03/2026 (el ejercicio de esa fecha ya está cerrado); se registra con la fecha de hoy."
        propia = "y" * (300 - len(" — ") - len(aclaracion))

        asiento = _registrar(fecha=datetime.date(2026, 3, 15), descripcion=propia)

        self.assertEqual(asiento.descripcion_asiento, f"{propia} — {aclaracion}")
        self.assertEqual(len(asiento.descripcion_asiento), 300)

    def test_regla_h10_la_fecha_de_hoy_dentro_del_abierto_no_lleva_aclaracion(self):
        """D-84 punto 5: un hecho de hoy, o de un día pasado del abierto, se asienta con su fecha y sin aclaración."""
        de_hoy = _registrar(fecha=HOY)
        de_antes = _registrar(fecha=datetime.date(2027, 3, 3))

        self.assertEqual((de_hoy.fecha_asiento, de_hoy.descripcion_asiento), (HOY, ""))
        self.assertEqual((de_antes.fecha_asiento, de_antes.descripcion_asiento), (datetime.date(2027, 3, 3), ""))

    def test_regla_h10_el_automatico_nunca_lanza_error_de_fecha(self):
        """Decisión de CON-02 y docs/api/asientos.md (lista cerrada de errores del automático): ninguno es de fecha."""
        for fecha in (datetime.date(2026, 3, 15), datetime.date(2020, 1, 1), datetime.date(2030, 1, 1)):
            with self.subTest(fecha=fecha):
                self.assertIsNotNone(_registrar(fecha=fecha))
        verificar_invariantes_contables()


class EjercicioParaTests(TestCase):
    """docs/api/asientos.md, «Lectura»: `ejercicio_para(fecha, *, automatico, hoy=None)` (D-84 punto 5)."""

    def setUp(self):
        self.cerrado = ejercicio(Estado.CERRADO, datetime.date(2025, 1, 1))
        self.en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        self.abierto = ejercicio_abierto(INICIO)

    def _para(self, fecha, automatico):
        return ejercicios.ejercicio_para(fecha, automatico=automatico, hoy=HOY)

    def test_regla_una_fecha_en_el_abierto_o_en_el_en_cierre_devuelve_ese_ejercicio(self):
        """D-84 punto 5: el ejercicio cuyo rango contiene la fecha, abierto o en cierre, para un asiento automático y para uno manual."""
        for automatico in (True, False):
            with self.subTest(automatico=automatico):
                self.assertEqual(self._para(datetime.date(2027, 3, 1), automatico).pk, self.abierto.pk)
                self.assertEqual(self._para(HOY, automatico).pk, self.abierto.pk)
                self.assertEqual(self._para(datetime.date(2026, 12, 31), automatico).pk, self.en_cierre.pk)

    def test_regla_el_automatico_con_fecha_cerrada_anterior_o_futura_devuelve_el_abierto_sin_error(self):
        """Decisión de CON-02: `automatico=True` no lanza error de fecha; devuelve el abierto (donde irá con la fecha de hoy)."""
        for fecha in (datetime.date(2025, 6, 1), datetime.date(2024, 12, 31), datetime.date(2028, 1, 1), datetime.date(2027, 9, 1)):
            with self.subTest(fecha=fecha):
                self.assertEqual(self._para(fecha, True).pk, self.abierto.pk)

    def test_regla_el_manual_con_fecha_en_ejercicio_cerrado_se_rechaza(self):
        """D-84 punto 5: un asiento manual con fecha en un ejercicio cerrado lanza `fecha_en_ejercicio_cerrado`."""
        with self.assertRaises(ErrorContable) as contexto:
            self._para(datetime.date(2025, 6, 1), False)

        self.assertEqual(contexto.exception.codigo, "fecha_en_ejercicio_cerrado")

    def test_regla_el_manual_con_fecha_anterior_al_primer_ejercicio_se_rechaza(self):
        """D-84 punto 5: un manual anterior al primer ejercicio lanza `fecha_anterior_al_primer_ejercicio`."""
        with self.assertRaises(ErrorContable) as contexto:
            self._para(datetime.date(2024, 12, 31), False)

        self.assertEqual(contexto.exception.codigo, "fecha_anterior_al_primer_ejercicio")

    def test_regla_el_manual_con_fecha_futura_se_rechaza_aunque_este_en_el_rango_del_abierto(self):
        """D-84 punto 5: un manual futuro (posterior a hoy) lanza `fecha_futura`, también si cae dentro del rango del abierto."""
        for fecha in (datetime.date(2027, 6, 16), datetime.date(2030, 1, 1)):
            with self.subTest(fecha=fecha):
                with self.assertRaises(ErrorContable) as contexto:
                    self._para(fecha, False)
                self.assertEqual(contexto.exception.codigo, "fecha_futura")

    def test_regla_la_fecha_de_hoy_no_es_futura_para_un_manual(self):
        """D-84 punto 5: la fecha de hoy es válida para un manual."""
        self.assertEqual(self._para(HOY, False).pk, self.abierto.pk)
