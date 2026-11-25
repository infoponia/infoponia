# Pruebas de CON-CNS-LGS «Consultar Libro de Gestión» (CON-03a paso 1; docs/casos_de_uso/contabilidad/libro_de_gestion.md; D-84 puntos 5, 8 y 10; D-102).
# Servicios de lectura: `libro.listar_asientos`, `libro.ficha_de_asiento` y el punto de extensión `contabilidad/extensiones.py`
# (`registrar_enlace_de_origen`). Los asientos se arman directo en la base con `asiento_de_prueba` y la auditoría con `RegistroAuditoria.objects.registrar`.
# Cada prueba arma sus datos. Una consulta no audita (regla 9, SEG-14).
import datetime
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from contabilidad import cuentas, extensiones
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable, EjercicioContable, OrigenDocumento
from contabilidad.servicios import libro
from contabilidad.tests.fabricas import PlanDeCuentasMixin, asiento_de_prueba, ejercicio, origen_de_prueba
from core.models import Agronomo, Capataz, Contador, Gerente, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
Accion = RegistroAuditoria.Accion
HOY = datetime.date(2027, 6, 15)


def _d(texto):
    return Decimal(texto)


def _caja_a_ventas(importe="100.00"):
    return [(cuentas.CAJA, DEBE, _d(importe)), (cuentas.VENTAS, HABER, _d(importe))]


class ConCnsLgsBase(PlanDeCuentasMixin, TestCase):
    """Datos comunes: un Contador, un Gerente y un ejercicio abierto que empieza el 1/1/2027."""

    def setUp(self):
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com")
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))


class ConCnsLgsAlcanceTests(ConCnsLgsBase):
    """Precondición a y regla 1: el Contador y el Gerente ven todo; el Vendedor y los demás roles no."""

    def test_regla_1_el_contador_activo_consulta(self):
        """Regla 1 de CON-CNS-LGS: el Contador ve el libro."""
        asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())

        self.assertEqual(libro.listar_asientos(self.contador).count(), 1)

    def test_regla_1_el_gerente_consulta_haya_o_no_contador_activo(self):
        """Regla 1: el Gerente siempre consulta el libro, haya o no Contador activo."""
        asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())

        self.assertEqual(libro.listar_asientos(self.gerente).count(), 1)
        Contador.objects.update(is_active=False)
        self.assertEqual(libro.listar_asientos(self.gerente).count(), 1)

    def test_regla_1_el_vendedor_y_los_demas_roles_no_consultan(self):
        """Regla 1 y X3: el Vendedor no tiene acceso; tampoco el Agrónomo ni el Capataz."""
        for clase, email in ((Vendedor, "v@infoponia.com"), (Agronomo, "a@infoponia.com"), (Capataz, "c@infoponia.com")):
            with self.subTest(rol=clase.__name__):
                with self.assertRaises(PermissionDenied):
                    libro.listar_asientos(crear_cuenta(clase, email=email))

    def test_precondicion_a_una_cuenta_inactiva_o_sin_sesion_no_consulta(self):
        """Precondición a: «cuenta activa de Contador o de Gerente»; una cuenta dada de baja o ninguna cuenta se rechazan."""
        inactivo = crear_cuenta(Gerente, email="viejo@infoponia.com", activo=False)

        with self.assertRaises(PermissionDenied):
            libro.listar_asientos(inactivo)
        with self.assertRaises(PermissionDenied):
            libro.listar_asientos(None)
        with self.assertRaises(PermissionDenied):
            libro.ficha_de_asiento(inactivo, self.abierto.pk, 1)


class ConCnsLgsVistaCronologicaTests(ConCnsLgsBase):
    """Regla 2: la vista cronológica, su orden y sus filtros."""

    def test_regla_2_por_defecto_muestra_el_ejercicio_abierto(self):
        """Regla 2: el ejercicio por defecto es el abierto; los asientos de otro ejercicio no aparecen."""
        cerrado = ejercicio(Estado.CERRADO, datetime.date(2026, 1, 1))
        viejo = asiento_de_prueba(cerrado, datetime.date(2026, 5, 1), _caja_a_ventas())
        nuevo = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())

        self.assertEqual(list(libro.listar_asientos(self.contador)), [nuevo])
        self.assertEqual(list(libro.listar_asientos(self.contador, ejercicio_id=cerrado.pk)), [viejo])

    def test_regla_2_sin_ejercicio_abierto_y_sin_ejercicio_elegido_no_hay_asientos(self):
        """Regla 2: sin ejercicio abierto ni elegido no hay qué listar (lista vacía, no un error)."""
        EjercicioContable.objects.all().delete()

        self.assertEqual(list(libro.listar_asientos(self.contador)), [])

    def test_regla_2_ordena_por_fecha_y_a_igual_fecha_por_numero(self):
        """Regla 2 y H8: orden por fecha y, a igual fecha, por número (el número es de orden de registro, no de fecha)."""
        primero = asiento_de_prueba(self.abierto, datetime.date(2027, 5, 10), _caja_a_ventas())  # N.º 1, fecha tardía
        segundo = asiento_de_prueba(self.abierto, datetime.date(2027, 3, 1), _caja_a_ventas())  # N.º 2, fecha temprana
        tercero = asiento_de_prueba(self.abierto, datetime.date(2027, 3, 1), _caja_a_ventas())  # N.º 3, misma fecha que el 2

        self.assertEqual(list(libro.listar_asientos(self.contador)), [segundo, tercero, primero])

    def test_regla_2_filtra_por_rango_de_fechas_con_extremos_inclusivos(self):
        """Regla 2: «rango de fechas» (desde y hasta incluidos)."""
        marzo = asiento_de_prueba(self.abierto, datetime.date(2027, 3, 1), _caja_a_ventas())
        abril = asiento_de_prueba(self.abierto, datetime.date(2027, 4, 1), _caja_a_ventas())
        mayo = asiento_de_prueba(self.abierto, datetime.date(2027, 5, 1), _caja_a_ventas())

        self.assertEqual(list(libro.listar_asientos(self.contador, desde=datetime.date(2027, 4, 1))), [abril, mayo])
        self.assertEqual(list(libro.listar_asientos(self.contador, hasta=datetime.date(2027, 4, 1))), [marzo, abril])
        self.assertEqual(
            list(libro.listar_asientos(self.contador, desde=datetime.date(2027, 4, 1), hasta=datetime.date(2027, 4, 1))), [abril]
        )

    def test_regla_2_filtra_por_tipo_automatico_manual_y_contraasiento(self):
        """Regla 2 y regla 15 de 8.20: el tipo se deduce (`origen`, `anula`); se filtra por `automatico`, `manual` y `contraasiento`."""
        automatico = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen_de_prueba())
        manual = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        contra = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), anula=manual)

        self.assertEqual(list(libro.listar_asientos(self.contador, tipo="automatico")), [automatico])
        self.assertEqual(list(libro.listar_asientos(self.contador, tipo="manual")), [manual])
        self.assertEqual(list(libro.listar_asientos(self.contador, tipo="contraasiento")), [contra])

    def test_regla_2_un_tipo_desconocido_es_un_error_de_programacion(self):
        """Regla 2: los tipos son tres; otro valor no se ignora en silencio (mostraría todo sin avisar)."""
        with self.assertRaises(ValueError):
            libro.listar_asientos(self.contador, tipo="inventado")

    def test_regla_2_filtra_por_tipo_de_documento_de_origen(self):
        """Regla 2: filtro «origen (tipo de documento)»."""
        de_bitacora = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen_de_prueba(OrigenDocumento.Tipo.BITACORA))
        asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen_de_prueba(OrigenDocumento.Tipo.CONTRATO))

        self.assertEqual(list(libro.listar_asientos(self.contador, origen_tipo="bitacora")), [de_bitacora])

    def test_regla_2_filtra_por_cuenta_sin_repetir_el_asiento(self):
        """Regla 2: filtro por cuenta; un asiento con dos movimientos de la misma cuenta aparece una sola vez."""
        con_caja = asiento_de_prueba(
            self.abierto,
            HOY,
            [(cuentas.CAJA, DEBE, _d("50.00")), (cuentas.CAJA, DEBE, _d("50.00")), (cuentas.VENTAS, HABER, _d("100.00"))],
        )
        asiento_de_prueba(self.abierto, HOY, [(cuentas.BANCO, DEBE, _d("10.00")), (cuentas.VENTAS, HABER, _d("10.00"))])

        self.assertEqual(list(libro.listar_asientos(self.contador, cuenta=cuentas.CAJA)), [con_caja])

    def test_regla_2_filtra_por_anulados_si_no_o_todos(self):
        """Regla 2: «anulados sí o no»; `None` los muestra todos. Anulado es tener contraasiento."""
        anulado = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        contra = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), anula=anulado)
        vigente = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())

        self.assertEqual(list(libro.listar_asientos(self.contador, anulados=True)), [anulado])
        self.assertEqual(list(libro.listar_asientos(self.contador, anulados=False)), [contra, vigente])
        self.assertEqual(list(libro.listar_asientos(self.contador, anulados=None)), [anulado, contra, vigente])

    def test_regla_2_el_texto_busca_en_la_descripcion_el_numero_exacto_y_el_origen(self):
        """CON-CNS-LGS, «Servicios de lectura»: `texto` busca en la descripción, en el número exacto y en el identificador del origen."""
        luz = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), descripcion="Pago de la factura de luz")  # N.º 1
        origen = origen_de_prueba()
        automatico = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen)  # N.º 2

        self.assertEqual(list(libro.listar_asientos(self.contador, texto="FACTURA")), [luz])
        self.assertEqual(list(libro.listar_asientos(self.contador, texto="2")), [automatico])  # el número exacto, no «contiene 2»
        self.assertEqual(list(libro.listar_asientos(self.contador, texto=str(origen.pk))), [automatico])
        self.assertEqual(list(libro.listar_asientos(self.contador, texto="no existe")), [])

    def test_regla_2_el_total_y_el_tipo_de_cada_asiento_salen_sin_consultas_por_fila(self):
        """Regla 2 y «Hecho cuando»: lo que se muestra de cada asiento (número, fecha, descripción, tipo, anulado, movimientos y cuentas) no hace consultas por fila."""

        anio = [2000]

        def consultas(cantidad):
            anio[0] += 1  # un ejercicio cerrado nuevo por medición (a lo sumo uno abierto, y los asientos protegen su ejercicio)
            ej = ejercicio(Estado.CERRADO, datetime.date(anio[0], 1, 1))
            fecha = datetime.date(anio[0], 6, 1)
            for _ in range(cantidad):
                asiento_de_prueba(ej, fecha, _caja_a_ventas(), origen=origen_de_prueba())
                manual = asiento_de_prueba(ej, fecha, _caja_a_ventas(), descripcion="Manual")
                asiento_de_prueba(ej, fecha, _caja_a_ventas(), anula=manual)
            with CaptureQueriesContext(connection) as capturadas:
                for asiento in libro.listar_asientos(self.contador, ejercicio_id=ej.pk):
                    _ = (
                        asiento.numero_asiento,
                        asiento.fecha_asiento,
                        asiento.descripcion_asiento,
                        asiento.tipo,
                        asiento.origen,
                        asiento.ejercicio,
                        hasattr(asiento, "contraasiento"),
                        [(m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.all()],
                    )
            return len(capturadas)

        self.assertEqual(consultas(1), consultas(5))
        self.assertLessEqual(consultas(1), 6)

    def test_regla_9_la_consulta_no_audita(self):
        """Regla 9 de CON-CNS-LGS (SEG-14): ni la lista ni la ficha escriben en la auditoría."""
        asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        antes = RegistroAuditoria.objects.count()

        list(libro.listar_asientos(self.contador))
        libro.ficha_de_asiento(self.contador, self.abierto.pk, asiento.numero_asiento)

        self.assertEqual(RegistroAuditoria.objects.count(), antes)


class ConCnsLgsSaldosTests(ConCnsLgsBase):
    """Regla 4: saldos patrimoniales acumulados, de resultado desde cero y saldo contrario a la naturaleza (lo que muestra la vista por cuenta)."""

    def setUp(self):
        super().setUp()
        self.anterior = ejercicio(Estado.CERRADO, datetime.date(2026, 1, 1))
        self.abierto.delete()
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))
        asiento_de_prueba(self.anterior, datetime.date(2026, 4, 1), [(cuentas.CAJA, DEBE, _d("1000.00")), (cuentas.CAPITAL_INICIAL, HABER, _d("1000.00"))])
        asiento_de_prueba(self.anterior, datetime.date(2026, 5, 1), [(cuentas.CAJA, DEBE, _d("400.00")), (cuentas.VENTAS, HABER, _d("400.00"))])
        asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), [(cuentas.CAJA, DEBE, _d("300.00")), (cuentas.VENTAS, HABER, _d("300.00"))])

    def test_regla_4_la_cuenta_patrimonial_arranca_con_el_saldo_acumulado(self):
        """Regla 4: las patrimoniales (activo, pasivo, patrimonio neto) arrancan con el saldo de los ejercicios anteriores."""
        caja = libro.saldo_por_cuenta(self.abierto.pk)[cuentas.CAJA]

        self.assertEqual((caja.saldo_inicial, caja.saldo), (_d("1400.00"), _d("1700.00")))

    def test_regla_4_la_cuenta_de_resultado_arranca_en_cero(self):
        """Regla 4: las de resultado muestran solo los movimientos del ejercicio elegido, desde cero (Ventas 2026 = 400 no se arrastra)."""
        ventas = libro.saldo_por_cuenta(self.abierto.pk)[cuentas.VENTAS]

        self.assertEqual((ventas.saldo_inicial, ventas.saldo), (_d("0.00"), _d("300.00")))

    def test_regla_4_el_signo_depende_del_tipo_y_el_saldo_contrario_se_marca(self):
        """Regla 4 y H5: activo y resultado negativo, deudor (Debe − Haber); resultado positivo, acreedor; un saldo contrario se marca (5.1.06 acreedora)."""
        asiento_de_prueba(
            self.abierto,
            datetime.date(2027, 3, 1),
            [(cuentas.CAJA, DEBE, _d("20.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, HABER, _d("20.00"))],
        )

        saldos = libro.saldo_por_cuenta(self.abierto.pk)

        self.assertEqual(saldos[cuentas.DIFERENCIAS_DE_INVENTARIO].saldo, _d("-20.00"))
        self.assertTrue(saldos[cuentas.DIFERENCIAS_DE_INVENTARIO].contrario)
        self.assertFalse(saldos[cuentas.CAJA].contrario)
        self.assertFalse(saldos[cuentas.VENTAS].contrario)

    def test_regla_3_los_movimientos_de_la_cuenta_traen_su_saldo_acumulado(self):
        """Regla 3: la vista por cuenta muestra Debe, Haber y saldo acumulado, partiendo del saldo inicial de la cuenta patrimonial."""
        filas = libro.movimientos_de_cuenta(cuentas.CAJA, self.abierto.pk)

        self.assertEqual([f.saldo for f in filas], [_d("1700.00")])


class ConCnsLgsFichaTests(ConCnsLgsBase):
    """Reglas 5, 6 y 8: la ficha del asiento."""

    def test_regla_5_la_ficha_trae_numero_fecha_ejercicio_descripcion_y_movimientos(self):
        """Regla 5: número, fecha, ejercicio, descripción y movimientos (cuenta, Debe o Haber, importe); el total es la suma del Debe."""
        asiento = asiento_de_prueba(self.abierto, datetime.date(2027, 4, 2), _caja_a_ventas("250.00"), descripcion="Venta de mostrador")

        ficha = libro.ficha_de_asiento(self.contador, self.abierto.pk, asiento.numero_asiento)

        self.assertEqual(ficha.asiento, asiento)
        self.assertEqual(ficha.total, _d("250.00"))
        self.assertEqual(
            [(m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in ficha.movimientos],
            [(cuentas.CAJA, "D", _d("250.00")), (cuentas.VENTAS, "H", _d("250.00"))],
        )
        self.assertIsNone(ficha.anula)
        self.assertIsNone(ficha.anulado_por)

    def test_regla_5_un_asiento_inexistente_es_404(self):
        """Regla 5: pedir un número que no existe en ese ejercicio es 404."""
        with self.assertRaises(Http404):
            libro.ficha_de_asiento(self.contador, self.abierto.pk, 99)

    def test_regla_5_el_documento_de_origen_sin_registrante_muestra_solo_el_texto_del_tipo(self):
        """Regla 5 y «Enlace al origen»: sin registrante, la ficha muestra solo el texto del tipo, sin enlace."""
        origen = origen_de_prueba(OrigenDocumento.Tipo.BITACORA)
        asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen)

        with mock.patch.object(extensiones, "_ENLACES_DE_ORIGEN", {}):
            ficha = libro.ficha_de_asiento(self.contador, self.abierto.pk, asiento.numero_asiento)

        self.assertEqual((ficha.origen_texto, ficha.origen_url), ("Bitácora", None))

    def test_regla_5_el_documento_de_origen_con_registrante_trae_su_enlace(self):
        """Regla 5 y «Enlace al origen»: la app que reabre el caso de uso registra `funcion(origen) -> (texto, url)`; la ficha lo muestra."""
        origen = origen_de_prueba(OrigenDocumento.Tipo.BITACORA)
        asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen)

        with mock.patch.object(extensiones, "_ENLACES_DE_ORIGEN", {}):
            extensiones.registrar_enlace_de_origen("bitacora", lambda o: (f"Bitácora N.º {o.pk}", f"/bitacora/{o.pk}/"))
            ficha = libro.ficha_de_asiento(self.contador, self.abierto.pk, asiento.numero_asiento)

        self.assertEqual((ficha.origen_texto, ficha.origen_url), (f"Bitácora N.º {origen.pk}", f"/bitacora/{origen.pk}/"))

    def test_regla_5_un_asiento_manual_no_tiene_origen(self):
        """Regla 5: «documento de origen (si lo tiene)»: un manual no lo tiene."""
        asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())

        ficha = libro.ficha_de_asiento(self.contador, self.abierto.pk, asiento.numero_asiento)

        self.assertEqual((ficha.origen_texto, ficha.origen_url), (None, None))

    def test_regla_5_quien_registro_un_manual_sale_de_la_auditoria(self):
        """Regla 5 y regla 16 de 8.20: el manual guarda a quien lo registró solo en la auditoría (`alta_asiento_contable`); si fue el Gerente, también."""
        por_contador = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        por_gerente = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        RegistroAuditoria.objects.registrar(self.contador, Accion.ALTA_ASIENTO_CONTABLE, [por_contador], {})
        RegistroAuditoria.objects.registrar(self.gerente, Accion.ALTA_ASIENTO_CONTABLE, [por_gerente], {})

        ficha_c = libro.ficha_de_asiento(self.contador, self.abierto.pk, por_contador.numero_asiento)
        ficha_g = libro.ficha_de_asiento(self.contador, self.abierto.pk, por_gerente.numero_asiento)

        self.assertEqual(ficha_c.registrado_por, self.contador.usuario_ptr)
        self.assertEqual(ficha_g.registrado_por, self.gerente.usuario_ptr)

    def test_regla_5_un_automatico_no_muestra_quien_lo_registro(self):
        """Regla 5: «quién lo registró (si es manual o contraasiento)»: un automático no."""
        asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen_de_prueba())
        RegistroAuditoria.objects.registrar(None, Accion.ALTA_ASIENTO_CONTABLE, [asiento], {})

        ficha = libro.ficha_de_asiento(self.contador, self.abierto.pk, asiento.numero_asiento)

        self.assertIsNone(ficha.registrado_por)

    def test_regla_5_la_auditoria_de_otro_asiento_con_el_mismo_id_no_se_confunde(self):
        """Regla 5: la búsqueda en la auditoría exige el modelo además del id (un movimiento con el mismo id no cuenta)."""
        asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        movimiento = asiento.movimientos.first()
        RegistroAuditoria.objects.registrar(self.gerente, Accion.ALTA_MOVIMIENTO_CONTABLE, [movimiento], {})

        ficha = libro.ficha_de_asiento(self.contador, self.abierto.pk, asiento.numero_asiento)

        self.assertIsNone(ficha.registrado_por)

    def test_regla_5_la_ficha_enlaza_el_asiento_que_anula_y_el_que_lo_anulo(self):
        """Regla 5: si anula a otro asiento o fue anulado por otro, la ficha trae el otro (con acceso a él)."""
        original = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        contra = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), anula=original)

        ficha_original = libro.ficha_de_asiento(self.contador, self.abierto.pk, original.numero_asiento)
        ficha_contra = libro.ficha_de_asiento(self.contador, self.abierto.pk, contra.numero_asiento)

        self.assertEqual(ficha_original.anulado_por, contra)
        self.assertIsNone(ficha_original.anula)
        self.assertEqual(ficha_contra.anula, original)
        self.assertIsNone(ficha_contra.anulado_por)

    def test_regla_5_el_contraasiento_puede_estar_en_otro_ejercicio(self):
        """Regla 5 (ejemplo 85 → 120 del modelo) y D-84 punto 5: el contraasiento puede caer en un ejercicio distinto del anulado; la ficha lo encuentra igual."""
        en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        original = asiento_de_prueba(en_cierre, datetime.date(2026, 12, 1), _caja_a_ventas())
        contra = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), anula=original)

        ficha = libro.ficha_de_asiento(self.contador, en_cierre.pk, original.numero_asiento)

        self.assertEqual(ficha.anulado_por, contra)
        self.assertEqual(ficha.anulado_por.ejercicio, self.abierto)

    def test_regla_6_los_asientos_de_un_ejercicio_cerrado_se_ven(self):
        """Regla 6: los asientos de un ejercicio «cerrado» se ven (no se modifican; el modelo ya lo impide)."""
        cerrado = ejercicio(Estado.CERRADO, datetime.date(2025, 1, 1))
        asiento = asiento_de_prueba(cerrado, datetime.date(2025, 6, 1), _caja_a_ventas())

        ficha = libro.ficha_de_asiento(self.gerente, cerrado.pk, asiento.numero_asiento)

        self.assertEqual(ficha.asiento, asiento)
        self.assertEqual(list(libro.listar_asientos(self.gerente, ejercicio_id=cerrado.pk)), [asiento])

    def test_regla_5_la_ficha_no_hace_consultas_por_movimiento(self):
        """«Hecho cuando»: sin consultas por fila; la ficha de un asiento de 2 movimientos y la de uno de 8 hacen las mismas."""

        def consultas(pares):
            movimientos = [(cuentas.CAJA, DEBE, _d("10.00"))] * pares + [(cuentas.VENTAS, HABER, _d(str(10 * pares) + ".00"))]
            asiento = asiento_de_prueba(self.abierto, HOY, movimientos, origen=origen_de_prueba())
            with CaptureQueriesContext(connection) as capturadas:
                ficha = libro.ficha_de_asiento(self.contador, self.abierto.pk, asiento.numero_asiento)
                [(m.cuenta.codigo_cuenta, m.cuenta.get_tipo_cuenta_display()) for m in ficha.movimientos]
            return len(capturadas)

        self.assertEqual(consultas(1), consultas(7))


class ConCnsLgsExtensionesTests(TestCase):
    """El punto de extensión `contabilidad/extensiones.py` (D-37, regla A4; CON-CNS-LGS, «Enlace al origen»)."""

    def test_registrar_el_mismo_enlace_dos_veces_no_lo_repite(self):
        """Contrato de los puntos de extensión: `registrar_enlace_de_origen` es idempotente (`ready()` puede correr más de una vez)."""

        def enlace(origen):
            return ("X", "/x/")

        with mock.patch.object(extensiones, "_ENLACES_DE_ORIGEN", {}):
            extensiones.registrar_enlace_de_origen("bitacora", enlace)
            extensiones.registrar_enlace_de_origen("bitacora", enlace)

            self.assertEqual(extensiones._ENLACES_DE_ORIGEN, {"bitacora": [enlace]})

    def test_un_registrante_que_devuelve_none_deja_el_texto_del_tipo_sin_enlace(self):
        """«Enlace al origen»: `funcion(origen) -> (texto, url) | None`; con `None` (por ejemplo, el documento no tiene pantalla) vale el texto del tipo."""
        origen = OrigenDocumento(tipo=OrigenDocumento.Tipo.CONTRATO)

        with mock.patch.object(extensiones, "_ENLACES_DE_ORIGEN", {}):
            extensiones.registrar_enlace_de_origen("contrato", lambda o: None)
            self.assertEqual(extensiones.enlace_de_origen(origen), ("Contrato", None))

    def test_el_primer_registrante_que_responde_gana(self):
        """Dos apps no registran el mismo tipo; si pasara, gana el primero que devuelve algo."""
        origen = OrigenDocumento(tipo=OrigenDocumento.Tipo.CONTRATO)

        with mock.patch.object(extensiones, "_ENLACES_DE_ORIGEN", {}):
            extensiones.registrar_enlace_de_origen("contrato", lambda o: None)
            extensiones.registrar_enlace_de_origen("contrato", lambda o: ("Contrato 7", "/contratos/7/"))
            self.assertEqual(extensiones.enlace_de_origen(origen), ("Contrato 7", "/contratos/7/"))
