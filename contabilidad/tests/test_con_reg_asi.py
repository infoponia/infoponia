# Pruebas de CON-REG-ASI «Registrar Asiento Manual» (CON-03b paso 1; docs/casos_de_uso/contabilidad/asientos_manuales.md; D-84 puntos 1, 2, 4, 5, 6 y 9; D-85 punto 5; D-30):
# `asientos.registrar_asiento_manual` y `asientos.resumir_asiento_manual`. Cada prueba arma sus datos y recibe «hoy» (nunca lee la hora sola).
# Escenario común: un ejercicio cerrado (2025), uno en cierre (2026) y uno abierto (2027); hoy es el 10/3/2027.
# La concurrencia está en `test_asientos_concurrencia.py` y las pantallas en `test_asientos_vistas.py`.
#
# Contrato que fijan estas pruebas (lo implementa el paso 1):
#   - `registrar_asiento_manual(actor, fecha, descripcion, movimientos, *, hoy=None) -> AsientoContable`, con `movimientos = [(codigo, "D"|"H", Decimal)]`.
#   - `resumir_asiento_manual(...)` con los mismos argumentos devuelve un `ResumenDeAsiento` y NO escribe ni bloquea nada.
#   - Los errores de datos son `ErrorContable`; todos llevan `.errores` (la lista de errores, cada uno con `.codigo` y `.campo`). Cuando hay varios
#     errores de campo se lanzan juntos (en el orden: descripción, líneas, balance), con el `.codigo` del primero.
#   - Los errores de línea llevan `campo="movimientos[i].cuenta"` o `"movimientos[i].importe"`, con `i` la posición en la lista recibida.
import datetime
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable, MovimientoContable, OrigenDocumento
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio, verificar_invariantes_contables
from core.models import Agronomo, Contador, Gerente, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
Accion = RegistroAuditoria.Accion
HOY = datetime.date(2027, 3, 10)
EN_EL_CERRADO = datetime.date(2025, 6, 1)
EN_EL_EN_CIERRE = datetime.date(2026, 12, 1)
ANTES_DEL_PRIMERO = datetime.date(2024, 6, 1)
DESCRIPCION = "Asiento de apertura"


def _d(texto):
    return Decimal(texto)


def _apertura(importe="1000.00"):
    """Caja contra Capital Inicial: el asiento de apertura de la extensión 3a."""
    return [(cuentas.CAJA, DEBE, _d(importe)), (cuentas.CAPITAL_INICIAL, HABER, _d(importe))]


def _errores(error):
    """`[(codigo, campo)]` de un `ErrorContable`, en el orden en que se lanzaron."""
    return [(e.codigo, e.campo) for e in error.errores]


class FalloDePrueba(Exception):
    """Fallo forzado en una prueba de «todo o nada»: una clase propia para que ningún otro error pase la prueba sin querer."""


class ConRegAsiBase(PlanDeCuentasMixin, TestCase):
    """Cuentas y ejercicios comunes, y las ayudas para llamar al servicio con `hoy` fijo."""

    def setUp(self):
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com", nombre="Cora", apellido="Díaz")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com", nombre="Gabriela", apellido="Sosa")
        self.cerrado = ejercicio(Estado.CERRADO, datetime.date(2025, 1, 1))
        self.en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))

    def registrar(self, actor=None, fecha=HOY, descripcion=DESCRIPCION, movimientos=None, **extra):
        return asientos.registrar_asiento_manual(
            actor or self.contador, fecha, descripcion, _apertura() if movimientos is None else movimientos, **{"hoy": HOY, **extra}
        )

    def resumir(self, actor=None, fecha=HOY, descripcion=DESCRIPCION, movimientos=None, **extra):
        return asientos.resumir_asiento_manual(
            actor or self.contador, fecha, descripcion, _apertura() if movimientos is None else movimientos, **{"hoy": HOY, **extra}
        )

    def recargar(self, ej):
        return EjercicioContable.objects.get(pk=ej.pk)

    def assert_sin_nada_escrito(self):
        """Garantías mínimas: ningún asiento ni movimiento, ninguna auditoría contable y ningún número consumido."""
        self.assertFalse(AsientoContable.objects.exists())
        self.assertFalse(MovimientoContable.objects.exists())
        self.assertEqual(set(EjercicioContable.objects.values_list("ultimo_numero_asiento", flat=True)), {0})
        self.assertFalse(RegistroAuditoria.objects.filter(accion__in=[Accion.ALTA_ASIENTO_CONTABLE, Accion.ALTA_MOVIMIENTO_CONTABLE]).exists())


class ConRegAsiQuienRegistraTests(ConRegAsiBase):
    """Precondición a, regla «Quién registra» y extensión 1a: el Contador; sin Contador activo, el Gerente; el resto no."""

    def test_regla_quien_registra_el_contador_activo_registra(self):
        """Regla «Quién registra»: el Contador activo registra el asiento."""
        asiento = self.registrar(self.contador)

        self.assertEqual(asiento.numero_asiento, 1)
        verificar_invariantes_contables()

    def test_ext_1a_el_gerente_registra_si_no_hay_contador_activo(self):
        """Extensión 1a (puntos 1 y 2) y D-85 punto 4: sin Contador activo registra el Gerente y la auditoría lo deja como autor, con rol Gerente."""
        Contador.objects.update(is_active=False)

        asiento = self.registrar(self.gerente)

        registro = RegistroAuditoria.objects.get(accion=Accion.ALTA_ASIENTO_CONTABLE, afectados__contains=[{"id": asiento.pk}])
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.rol, "gerente")

    def test_ext_1a_el_gerente_con_contador_activo_no_registra(self):
        """Extensión 1a, punto 3: con un Contador activo el Gerente no registra y el mensaje dice «Lo registra el Contador»; no se escribe nada."""
        with self.assertRaises(PermissionDenied) as contexto:
            self.registrar(self.gerente)

        self.assertIn("Lo registra el Contador", str(contexto.exception))
        self.assert_sin_nada_escrito()

    def test_regla_quien_registra_el_vendedor_y_los_demas_roles_no_registran(self):
        """Regla «Quién registra» y D-85 punto 8: ni el Vendedor ni ningún otro rol registran asientos, aunque no haya Contador activo."""
        Contador.objects.update(is_active=False)
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")

        for actor in (vendedor, agronomo):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.registrar(actor)
        with self.assertRaises(PermissionDenied):  # sin cuenta
            asientos.registrar_asiento_manual(None, HOY, DESCRIPCION, _apertura(), hoy=HOY)
        self.assert_sin_nada_escrito()

    def test_regla_quien_registra_un_contador_dado_de_baja_no_registra(self):
        """Precondición a: la cuenta tiene que estar activa; el servicio compara contra la base, no contra la instancia que recibió."""
        Contador.objects.update(is_active=False)

        with self.assertRaises(PermissionDenied):
            self.registrar(self.contador)
        self.assert_sin_nada_escrito()

    def test_regla_d30_el_actor_que_deja_de_ser_responsable_mientras_espera_no_registra(self):
        """D-30 punto 3 y docs/patrones/bloqueos.md: se vuelve a verificar que quien actúa siga siendo el responsable antes de bloquear el ejercicio."""

        def da_de_baja_al_contador(*args, **kwargs):
            Contador.objects.update(is_active=False)

        with mock.patch.object(ejercicios, "abrir_ejercicio_si_corresponde", side_effect=da_de_baja_al_contador):
            with self.assertRaises(PermissionDenied):
                self.registrar(self.contador)
        self.assert_sin_nada_escrito()


class ConRegAsiDatosTests(ConRegAsiBase):
    """Reglas «Descripción» y «Balance» (H11) y extensiones 5a, 5b, 5c y 7a: los errores de datos, por campo y por línea, sin escribir nada."""

    def test_ext_5a_falta_la_descripcion(self):
        """Extensión 5a y regla «Descripción»: la descripción es obligatoria; una vacía o de solo espacios se rechaza en el campo `descripcion`."""
        for descripcion in ("", "   ", None):
            with self.subTest(descripcion=descripcion), self.assertRaises(ErrorContable) as contexto:
                self.registrar(descripcion=descripcion)
            self.assertEqual(_errores(contexto.exception), [("descripcion_obligatoria", "descripcion")])
        self.assert_sin_nada_escrito()

    def test_regla_descripcion_se_guarda_recortada(self):
        """Regla «Descripción»: se guarda sin los espacios del principio y del final."""
        asiento = self.registrar(descripcion="   Asiento de apertura  ")

        self.assertEqual(asiento.descripcion_asiento, "Asiento de apertura")

    def test_regla_descripcion_de_mas_de_300_caracteres_se_rechaza(self):
        """Modelo `descripcion_asiento` (máximo 300): una más larga se rechaza con un mensaje, no con un error de base."""
        self.registrar(descripcion="a" * 300)  # control: 300 entra

        with self.assertRaises(ErrorContable) as contexto:
            self.registrar(descripcion="a" * 301)
        self.assertEqual(_errores(contexto.exception), [("descripcion_muy_larga", "descripcion")])

    def test_ext_5b_debe_y_haber_distintos_se_rechaza_con_la_diferencia(self):
        """Extensión 5b: el Debe y el Haber no suman lo mismo; el mensaje trae la diferencia y no se escribe nada."""
        movimientos = [(cuentas.CAJA, DEBE, _d("1000.00")), (cuentas.CAPITAL_INICIAL, HABER, _d("950.00"))]

        with self.assertRaises(ErrorContable) as contexto:
            self.registrar(movimientos=movimientos)

        self.assertEqual(_errores(contexto.exception), [("asiento_desbalanceado", "movimientos")])
        self.assertIn("50,00", contexto.exception.mensaje)
        self.assert_sin_nada_escrito()

    def test_ext_5b_todo_al_debe_es_un_asiento_desbalanceado(self):
        """Extensión 5b: dos líneas al Debe y ninguna al Haber no balancean."""
        movimientos = [(cuentas.CAJA, DEBE, _d("100.00")), (cuentas.BANCO, DEBE, _d("100.00"))]

        with self.assertRaises(ErrorContable) as contexto:
            self.registrar(movimientos=movimientos)
        self.assertEqual(contexto.exception.codigo, "asiento_desbalanceado")

    def test_ext_5c_con_menos_de_dos_movimientos_no_hay_asiento(self):
        """Extensión 5c y regla «Balance»: menos de dos movimientos es `faltan_movimientos`, en el manual un error (D-84 punto 6 vale para el automático)."""
        for movimientos in ([], [(cuentas.CAJA, DEBE, _d("100.00"))]):
            with self.subTest(movimientos=movimientos), self.assertRaises(ErrorContable) as contexto:
                self.registrar(movimientos=movimientos)
            self.assertEqual(_errores(contexto.exception), [("faltan_movimientos", "movimientos")])
        self.assert_sin_nada_escrito()

    def test_ext_5c_una_linea_de_importe_cero_se_omite_antes_de_contar(self):
        """Extensión 5c y H11: la línea de importe cero se omite y el asiento se registra con las demás; no queda ningún movimiento de cero."""
        movimientos = _apertura() + [(cuentas.BANCO, DEBE, _d("0.00"))]

        asiento = self.registrar(movimientos=movimientos)

        self.assertEqual(asiento.movimientos.count(), 2)
        self.assertFalse(asiento.movimientos.filter(cuenta__codigo_cuenta=cuentas.BANCO).exists())

    def test_ext_5c_la_linea_de_importe_cero_se_omite_aunque_no_tenga_cuenta(self):
        """H11: una fila a medio completar (sin cuenta y en cero) se omite sin marcarla como error de cuenta."""
        movimientos = _apertura() + [("", DEBE, _d("0.00"))]

        asiento = self.registrar(movimientos=movimientos)

        self.assertEqual(asiento.movimientos.count(), 2)

    def test_ext_5c_si_al_omitir_las_de_cero_quedan_menos_de_dos_no_hay_asiento(self):
        """Extensión 5c: dos líneas pero una de cero deja un solo movimiento: `faltan_movimientos`."""
        movimientos = [(cuentas.CAJA, DEBE, _d("100.00")), (cuentas.CAPITAL_INICIAL, HABER, _d("0.00"))]

        with self.assertRaises(ErrorContable) as contexto:
            self.registrar(movimientos=movimientos)
        self.assertEqual(contexto.exception.codigo, "faltan_movimientos")

    def test_ext_5c_importe_negativo_o_con_mas_de_dos_decimales_se_marca_en_su_linea(self):
        """Extensión 5c: un importe negativo o con más de dos decimales es `importe_invalido` y señala la línea (`movimientos[i].importe`), contando las de cero."""
        for importe in ("-5.00", "10.005"):
            movimientos = [(cuentas.CAJA, DEBE, _d("0.00")), (cuentas.CAJA, DEBE, _d(importe)), (cuentas.CAPITAL_INICIAL, HABER, _d("10.00"))]
            with self.subTest(importe=importe), self.assertRaises(ErrorContable) as contexto:
                self.registrar(movimientos=movimientos)
            self.assertEqual(_errores(contexto.exception), [("importe_invalido", "movimientos[1].importe")])
        self.assert_sin_nada_escrito()

    def test_ext_7a_cuenta_inexistente_o_vacia_se_marca_en_su_linea(self):
        """Extensión 7a: una cuenta que no existe en el plan, o sin elegir, es `cuenta_inexistente` y señala la línea (`movimientos[i].cuenta`)."""
        for codigo in ("9.9.99", ""):
            movimientos = [(cuentas.CAJA, DEBE, _d("100.00")), (codigo, HABER, _d("100.00"))]
            with self.subTest(codigo=codigo), self.assertRaises(ErrorContable) as contexto:
                self.registrar(movimientos=movimientos)
            self.assertEqual(_errores(contexto.exception), [("cuenta_inexistente", "movimientos[1].cuenta")])
        self.assert_sin_nada_escrito()

    def test_ext_5_los_errores_de_campo_se_juntan_y_se_lanzan_a_la_vez(self):
        """Patrón ABM, sección 2: descripción y varias líneas con error se informan juntas (en ese orden) para que la pantalla marque todas las filas."""
        movimientos = [(cuentas.CAJA, DEBE, _d("-1.00")), ("9.9.99", HABER, _d("100.00")), (cuentas.BANCO, DEBE, _d("100.00"))]

        with self.assertRaises(ErrorContable) as contexto:
            self.registrar(descripcion="", movimientos=movimientos)

        self.assertEqual(
            _errores(contexto.exception),
            [("descripcion_obligatoria", "descripcion"), ("importe_invalido", "movimientos[0].importe"), ("cuenta_inexistente", "movimientos[1].cuenta")],
        )
        self.assertEqual(contexto.exception.codigo, "descripcion_obligatoria")

    def test_ext_5_el_balance_no_se_evalua_si_hay_errores_de_linea(self):
        """Una línea inválida no permite calcular el balance: solo se informa el error de la línea y no un «desbalanceado» engañoso."""
        movimientos = [(cuentas.CAJA, DEBE, _d("-100.00")), (cuentas.CAPITAL_INICIAL, HABER, _d("100.00"))]

        with self.assertRaises(ErrorContable) as contexto:
            self.registrar(movimientos=movimientos)
        self.assertEqual([codigo for codigo, _ in _errores(contexto.exception)], ["importe_invalido"])

    def test_regla_plan_de_cuentas_no_hay_restricciones_sobre_que_cuentas_se_usan(self):
        """Regla «Plan de cuentas» (C6): cualquier cuenta del plan se puede usar a mano, también del lado contrario a su naturaleza."""
        movimientos = [(cuentas.VENTAS, DEBE, _d("80.00")), (cuentas.PERDIDAS_POR_MERMAS, HABER, _d("80.00"))]

        asiento = self.registrar(movimientos=movimientos)

        self.assertEqual(asiento.movimientos.count(), 2)


class ConRegAsiFechaTests(ConRegAsiBase):
    """Reglas «Ejercicio del asiento» y «Fecha» (H1, H10, C2) y extensiones 5d y 5e."""

    def test_regla_fecha_es_la_del_hecho_y_va_al_ejercicio_que_la_contiene(self):
        """Regla «Fecha» (H10): se guarda la fecha indicada, no la de hoy, y va al ejercicio cuyo rango la contiene."""
        asiento = self.registrar(fecha=datetime.date(2027, 1, 15))

        self.assertEqual(asiento.fecha_asiento, datetime.date(2027, 1, 15))
        self.assertEqual(asiento.ejercicio_id, self.abierto.pk)

    def test_regla_fecha_de_hoy_es_valida(self):
        """Regla «Fecha»: «no posterior a hoy» incluye hoy."""
        self.assertEqual(self.registrar(fecha=HOY).fecha_asiento, HOY)

    def test_ext_5d_la_fecha_en_un_ejercicio_en_cierre_se_acepta(self):
        """Extensión 5d y H1: en el ejercicio «en cierre» entran los asientos manuales con fecha en su rango; el número es el suyo (no el del abierto)."""
        asiento = self.registrar(fecha=EN_EL_EN_CIERRE)

        self.assertEqual(asiento.ejercicio_id, self.en_cierre.pk)
        self.assertEqual(asiento.numero_asiento, 1)
        self.assertEqual(self.recargar(self.en_cierre).ultimo_numero_asiento, 1)
        self.assertEqual(self.recargar(self.abierto).ultimo_numero_asiento, 0)

    def test_ext_5e_la_fecha_en_un_ejercicio_cerrado_se_rechaza_nombrandolo(self):
        """Extensión 5e y C2: un manual con fecha en un ejercicio cerrado se rechaza (no se redirige al abierto como el automático); el mensaje nombra el ejercicio y su rango."""
        with self.assertRaises(ErrorContable) as contexto:
            self.registrar(fecha=EN_EL_CERRADO)

        self.assertEqual(_errores(contexto.exception), [("fecha_en_ejercicio_cerrado", "fecha")])
        self.assertIn("cerrado", contexto.exception.mensaje)
        self.assertIn("01/01/2025", contexto.exception.mensaje)
        self.assertIn("31/12/2025", contexto.exception.mensaje)
        self.assert_sin_nada_escrito()

    def test_ext_5e_la_fecha_anterior_al_primer_ejercicio_se_rechaza(self):
        """Extensión 5e: una fecha anterior al primer ejercicio se rechaza con un mensaje que explica el motivo."""
        with self.assertRaises(ErrorContable) as contexto:
            self.registrar(fecha=ANTES_DEL_PRIMERO)

        self.assertEqual(_errores(contexto.exception), [("fecha_anterior_al_primer_ejercicio", "fecha")])
        self.assertIn("01/01/2025", contexto.exception.mensaje)  # dice desde cuándo hay contabilidad
        self.assert_sin_nada_escrito()

    def test_ext_5e_la_fecha_posterior_a_hoy_se_rechaza(self):
        """Extensión 5e: una fecha futura se rechaza; el mensaje dice que no puede ser posterior a hoy."""
        with self.assertRaises(ErrorContable) as contexto:
            self.registrar(fecha=HOY + datetime.timedelta(days=1))

        self.assertEqual(_errores(contexto.exception), [("fecha_futura", "fecha")])
        self.assertIn("posterior a hoy", contexto.exception.mensaje)
        self.assert_sin_nada_escrito()

    def test_ext_7b_el_ejercicio_cambia_de_estado_mientras_se_registra(self):
        """Extensión 7b: si al bloquear el ejercicio ya pasó a «cerrado», no se registra nada y se informa `cambio_simultaneo` con el nuevo estado."""
        bloquear = asientos._bloquear_ejercicio

        def cierran_el_ejercicio_justo_antes_de_bloquearlo(pk):
            EjercicioContable.objects.filter(pk=pk).update(estado_ejercicio=Estado.CERRADO)
            return bloquear(pk)

        with mock.patch.object(asientos, "_bloquear_ejercicio", side_effect=cierran_el_ejercicio_justo_antes_de_bloquearlo):
            with self.assertRaises(ErrorContable) as contexto:
                self.registrar(fecha=EN_EL_EN_CIERRE)

        self.assertEqual(contexto.exception.codigo, "cambio_simultaneo")
        self.assertIn("cerrado", contexto.exception.mensaje)
        self.assertFalse(AsientoContable.objects.exists())
        self.assertEqual(self.recargar(self.en_cierre).ultimo_numero_asiento, 0)


class ConRegAsiPostcondicionesTests(ConRegAsiBase):
    """Postcondiciones a a d y regla «Numeración» (H8); regla «Sin efecto operativo»; todo o nada."""

    def test_flujo_principal_registra_el_asiento_manual_de_apertura(self):
        """Flujo principal (pasos 5 a 8) y extensión 3a: la apertura (Caja contra Capital Inicial) es un asiento manual común, balanceado y con su número."""
        asiento = self.registrar(descripcion="Asiento de apertura")

        self.assertEqual(asiento.tipo, AsientoContable.Tipo.MANUAL)
        self.assertEqual(asiento.numero_asiento, 1)
        self.assertEqual(asiento.descripcion_asiento, "Asiento de apertura")
        verificar_invariantes_contables()

    def test_ext_3b_la_venta_de_produccion_previa_es_un_asiento_manual_comun(self):
        """Extensión 3b: Debe Banco / Haber Ventas se registra igual que cualquier asiento manual (los atajos son solo precarga de la pantalla)."""
        asiento = self.registrar(descripcion="Venta de producción previa", movimientos=[(cuentas.BANCO, DEBE, _d("500.00")), (cuentas.VENTAS, HABER, _d("500.00"))])

        self.assertEqual(asiento.tipo, AsientoContable.Tipo.MANUAL)
        verificar_invariantes_contables()

    def test_post_a_el_asiento_no_tiene_origen_ni_contraasiento(self):
        """Postcondición a: asiento sin documento de origen, con la fecha, la descripción y el número indicados; su tipo (derivado) es manual."""
        asiento = self.registrar(fecha=datetime.date(2027, 2, 1), descripcion="Arqueo de caja")

        self.assertIsNone(asiento.origen_id)
        self.assertIsNone(asiento.anula_id)
        self.assertEqual((asiento.fecha_asiento, asiento.descripcion_asiento, asiento.numero_asiento), (datetime.date(2027, 2, 1), "Arqueo de caja", 1))
        self.assertEqual(asiento.tipo, "manual")

    def test_post_b_un_movimiento_por_linea_con_debe_igual_a_haber(self):
        """Postcondición b: un movimiento por línea (cuenta, Debe o Haber, importe) y la suma del Debe es la del Haber."""
        movimientos = [
            (cuentas.CAJA, DEBE, _d("600.00")),
            (cuentas.BANCO, DEBE, _d("400.00")),
            (cuentas.CAPITAL_INICIAL, HABER, _d("900.50")),
            (cuentas.PROVEEDORES, HABER, _d("99.50")),
        ]

        asiento = self.registrar(movimientos=movimientos)

        creados = [(m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.select_related("cuenta").order_by("id")]
        self.assertEqual(creados, movimientos)
        verificar_invariantes_contables()

    def test_post_c_el_ejercicio_guarda_el_nuevo_ultimo_numero(self):
        """Postcondición c: el ejercicio que contiene al asiento guarda el nuevo último número."""
        self.registrar()

        self.assertEqual(self.recargar(self.abierto).ultimo_numero_asiento, 1)

    def test_post_d_se_audita_el_asiento_y_cada_movimiento_con_usuario_y_rol(self):
        """Postcondición d (regla 16 de 8.20): un registro por el asiento y uno por cada movimiento, con usuario, rol, fecha e identificador; sin documento de origen, el usuario queda en el log."""
        asiento = self.registrar(fecha=datetime.date(2027, 2, 1), descripcion="Arqueo de caja")

        registro = RegistroAuditoria.objects.get(accion=Accion.ALTA_ASIENTO_CONTABLE)
        self.assertEqual((registro.usuario_id, registro.rol), (self.contador.pk, "contador"))
        self.assertIn({"modelo": "contabilidad.asientocontable", "id": asiento.pk}, [{k: a[k] for k in ("modelo", "id")} for a in registro.afectados])
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["numero_asiento"], {"antes": None, "despues": 1})
        self.assertEqual(cambios["fecha_asiento"], {"antes": None, "despues": "2027-02-01"})
        self.assertEqual(cambios["descripcion_asiento"], {"antes": None, "despues": "Arqueo de caja"})
        self.assertEqual(cambios["ejercicio"]["despues"]["id"], self.abierto.pk)
        movimientos = RegistroAuditoria.objects.filter(accion=Accion.ALTA_MOVIMIENTO_CONTABLE).order_by("id")
        self.assertEqual(movimientos.count(), 2)
        primero = movimientos[0].detalle["cambios"]
        self.assertEqual(primero["cuenta_contable"]["despues"]["id"], asiento.movimientos.order_by("id")[0].cuenta_id)
        self.assertEqual((primero["tipo_movimiento"]["despues"], primero["importe_movimiento"]["despues"]), ("D", "1000.00"))
        self.assertEqual({r.usuario_id for r in movimientos}, {self.contador.pk})

    def test_regla_h8_la_numeracion_es_correlativa_por_ejercicio_y_sigue_el_orden_de_registro(self):
        """Regla «Numeración» (H8): el número es el siguiente al último del ejercicio y marca el orden de registro, no el de la fecha; cada ejercicio numera por su cuenta."""
        primero = self.registrar(fecha=datetime.date(2027, 3, 1))
        segundo = self.registrar(fecha=datetime.date(2027, 1, 5))  # fecha anterior, número posterior
        del_en_cierre = self.registrar(fecha=EN_EL_EN_CIERRE)

        self.assertEqual((primero.numero_asiento, segundo.numero_asiento), (1, 2))
        self.assertEqual(del_en_cierre.numero_asiento, 1)
        verificar_invariantes_contables()

    def test_regla_sin_efecto_operativo_solo_toca_la_contabilidad(self):
        """Regla «Sin efecto operativo»: el asiento manual no crea ningún documento de origen ni toca otra entidad."""
        antes = OrigenDocumento.objects.count()

        self.registrar()

        self.assertEqual(OrigenDocumento.objects.count(), antes)
        self.assertEqual(AsientoContable.objects.count(), 1)

    def test_garantias_minimas_si_falla_la_auditoria_no_queda_nada(self):
        """Garantías mínimas y requisito «una única transacción»: si falla la auditoría de un movimiento, no queda asiento, ni movimientos, ni número consumido, ni auditoría parcial."""
        llamadas = []
        real = RegistroAuditoria.objects.registrar

        def falla_en_el_ultimo(*args, **kwargs):
            llamadas.append(1)
            if len(llamadas) == 3:  # el asiento y sus dos movimientos
                raise FalloDePrueba
            return real(*args, **kwargs)

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=falla_en_el_ultimo):
            with self.assertRaises(FalloDePrueba):
                self.registrar()

        self.assertEqual(len(llamadas), 3)
        self.assert_sin_nada_escrito()

    def test_garantias_minimas_si_falla_al_crear_los_movimientos_no_queda_nada(self):
        """Garantías mínimas: un fallo al crear los movimientos deshace también el asiento y el número."""
        with mock.patch.object(MovimientoContable.objects, "bulk_create", side_effect=FalloDePrueba):
            with self.assertRaises(FalloDePrueba):
                self.registrar()

        self.assert_sin_nada_escrito()


class ConRegAsiEjercicioVencidoTests(PlanDeCuentasMixin, TestCase):
    """D-84 punto 2 y H9: con el ejercicio abierto vencido y sin que nadie haya abierto el siguiente, registrar autorrecupera ANTES de validar la fecha."""

    def setUp(self):
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.vencido = ejercicio(Estado.ABIERTO, datetime.date(2026, 1, 1))  # terminó el 31/12/2026; hoy es el 10/3/2027

    def test_regla_h9_registrar_con_fecha_de_hoy_abre_el_ejercicio_nuevo_y_asienta_en_el(self):
        """D-84 punto 2: una fecha válida (hoy) no se rechaza como «ejercicio cerrado»: la autorrecuperación abre el de 2027 y el asiento va ahí; el vencido pasa a «en cierre»."""
        asiento = asientos.registrar_asiento_manual(self.contador, HOY, DESCRIPCION, _apertura(), hoy=HOY)

        self.assertEqual(asiento.ejercicio.fecha_inicio_ejercicio, datetime.date(2027, 1, 1))
        self.assertEqual(asiento.ejercicio.estado_ejercicio, Estado.ABIERTO)
        self.assertEqual(asiento.numero_asiento, 1)
        self.assertEqual(EjercicioContable.objects.get(pk=self.vencido.pk).estado_ejercicio, Estado.EN_CIERRE)
        verificar_invariantes_contables()

    def test_regla_h9_registrar_con_fecha_del_ejercicio_vencido_va_al_que_quedo_en_cierre(self):
        """H1 y H9: una fecha de diciembre de 2026 entra en el ejercicio que la autorrecuperación acaba de pasar a «en cierre»."""
        asiento = asientos.registrar_asiento_manual(self.contador, datetime.date(2026, 12, 1), DESCRIPCION, _apertura(), hoy=HOY)

        self.assertEqual(asiento.ejercicio_id, self.vencido.pk)
        self.assertEqual(EjercicioContable.objects.get(pk=self.vencido.pk).estado_ejercicio, Estado.EN_CIERRE)
        verificar_invariantes_contables()

    def test_ext_5e_una_fecha_anterior_al_primer_ejercicio_se_rechaza_sin_haber_dejado_nada_a_medias(self):
        """Extensión 5e: con el ejercicio vencido, una fecha anterior al primero se rechaza; no queda ningún asiento."""
        with self.assertRaises(ErrorContable) as contexto:
            asientos.registrar_asiento_manual(self.contador, datetime.date(2025, 12, 1), DESCRIPCION, _apertura(), hoy=HOY)

        self.assertEqual(contexto.exception.codigo, "fecha_anterior_al_primer_ejercicio")
        self.assertFalse(AsientoContable.objects.exists())


class ConRegAsiResumenTests(ConRegAsiBase):
    """Paso 5 del flujo básico y «Cómo se aplica»: `resumir_asiento_manual` hace las mismas validaciones y devuelve el resumen sin escribir ni bloquear."""

    def test_flujo_principal_el_resumen_trae_el_ejercicio_los_totales_la_diferencia_y_el_tipo_de_cada_cuenta(self):
        """Paso 5: el ejercicio al que irá (número, rango y estado), el total del Debe, el del Haber, la diferencia (0) y el tipo de cada cuenta."""
        resumen = self.resumir()

        self.assertEqual((resumen.ejercicio_numero, resumen.ejercicio_estado), (3, Estado.ABIERTO))
        self.assertEqual((resumen.ejercicio_inicio, resumen.ejercicio_cierre), (datetime.date(2027, 1, 1), datetime.date(2027, 12, 31)))
        self.assertFalse(resumen.ejercicio_por_abrir)
        self.assertEqual((resumen.total_debe, resumen.total_haber, resumen.diferencia), (_d("1000.00"), _d("1000.00"), _d("0.00")))
        self.assertEqual(
            [(l.codigo, l.tipo_movimiento, l.importe, l.tipo_cuenta_texto) for l in resumen.lineas],
            [(cuentas.CAJA, DEBE, _d("1000.00"), "Activo"), (cuentas.CAPITAL_INICIAL, HABER, _d("1000.00"), "Patrimonio neto")],
        )
        self.assertEqual(resumen.lineas[0].nombre, "Caja")

    def test_ext_5d_el_resumen_indica_que_el_asiento_va_al_ejercicio_en_cierre(self):
        """Extensión 5d, punto 2: el resumen dice que el asiento va al ejercicio en cierre."""
        resumen = self.resumir(fecha=EN_EL_EN_CIERRE)

        self.assertEqual((resumen.ejercicio_numero, resumen.ejercicio_estado), (2, Estado.EN_CIERRE))

    def test_flujo_principal_el_resumen_cuenta_las_lineas_de_importe_cero_omitidas(self):
        """H11: las líneas de importe cero no figuran en el resumen y se informa cuántas se omitieron."""
        resumen = self.resumir(movimientos=_apertura() + [(cuentas.BANCO, DEBE, _d("0.00"))])

        self.assertEqual(len(resumen.lineas), 2)
        self.assertEqual(resumen.omitidas, 1)

    def test_regla_el_resumen_hace_las_mismas_validaciones_que_registrar(self):
        """«Resumen previo»: el resumen lanza los mismos errores (descripción, balance, líneas, fecha) que el registro, con los mismos códigos y campos."""
        casos = {
            "descripcion": dict(descripcion=""),
            "balance": dict(movimientos=[(cuentas.CAJA, DEBE, _d("1.00")), (cuentas.CAPITAL_INICIAL, HABER, _d("2.00"))]),
            "linea": dict(movimientos=[(cuentas.CAJA, DEBE, _d("1.00")), ("9.9.99", HABER, _d("1.00"))]),
            "cerrado": dict(fecha=EN_EL_CERRADO),
            "futura": dict(fecha=HOY + datetime.timedelta(days=1)),
        }
        for nombre, argumentos in casos.items():
            with self.subTest(nombre):
                with self.assertRaises(ErrorContable) as del_resumen:
                    self.resumir(**argumentos)
                with self.assertRaises(ErrorContable) as del_registro:
                    self.registrar(**argumentos)
                self.assertEqual(_errores(del_resumen.exception), _errores(del_registro.exception))

    def test_regla_el_resumen_respeta_quien_registra(self):
        """«Quién registra»: el Gerente con un Contador activo tampoco puede pedir el resumen (la pantalla no se la muestra)."""
        with self.assertRaises(PermissionDenied):
            self.resumir(self.gerente)

    def test_regla_el_resumen_no_escribe_ni_audita_ni_consume_numero(self):
        """Resumen previo y garantías mínimas: pedir el resumen no deja ningún asiento, movimiento, auditoría ni número consumido."""
        self.resumir()
        self.resumir(fecha=EN_EL_EN_CIERRE)

        self.assert_sin_nada_escrito()
        self.assertEqual(RegistroAuditoria.objects.filter(accion__in=[Accion.ALTA_EJERCICIO_CONTABLE, Accion.MODIFICACION_EJERCICIO_CONTABLE]).count(), 0)

    def test_regla_el_resumen_no_bloquea_el_ejercicio(self):
        """Resumen previo: no toma ningún bloqueo (el único bloqueo del manual es el del ejercicio, al registrar)."""
        with mock.patch.object(asientos, "_bloquear_ejercicio", side_effect=AssertionError("el resumen no bloquea")):
            self.resumir()


class ConRegAsiResumenConEjercicioVencidoTests(PlanDeCuentasMixin, TestCase):
    """El resumen no escribe NUNCA, ni siquiera la apertura que haría el registro: calcula, sin crearlo, el ejercicio que se abriría (decisión del 25/11/2026)."""

    def setUp(self):
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")

    def resumir(self, fecha):
        return asientos.resumir_asiento_manual(self.contador, fecha, DESCRIPCION, _apertura(), hoy=HOY)

    def estado_de_la_base(self):
        return (
            list(EjercicioContable.objects.order_by("id").values_list("id", "estado_ejercicio", "ultimo_numero_asiento")),
            AsientoContable.objects.count(),
            MovimientoContable.objects.count(),
            RegistroAuditoria.objects.count(),
        )

    def test_regla_h9_con_el_abierto_vencido_el_resumen_no_rechaza_la_fecha_de_hoy_ni_crea_nada(self):
        """El resumen de una fecha de hoy con el ejercicio abierto vencido NO la rechaza como «cerrado»: muestra el ejercicio que se abriría (2027, N.º 2, por abrir) y no escribe nada."""
        ejercicio(Estado.ABIERTO, datetime.date(2026, 1, 1))
        antes = self.estado_de_la_base()

        resumen = self.resumir(HOY)

        self.assertTrue(resumen.ejercicio_por_abrir)
        self.assertEqual((resumen.ejercicio_numero, resumen.ejercicio_estado), (2, Estado.ABIERTO))
        self.assertEqual((resumen.ejercicio_inicio, resumen.ejercicio_cierre), (datetime.date(2027, 1, 1), datetime.date(2027, 12, 31)))
        self.assertEqual(self.estado_de_la_base(), antes)  # ni ejercicios, ni asientos, ni auditoría, ni cambios de estado

    def test_regla_h9_con_el_abierto_vencido_una_fecha_de_su_rango_va_al_que_pasaria_a_en_cierre(self):
        """El ejercicio vencido aparece «en cierre» en el resumen (es lo que será al registrar) sin haber cambiado todavía."""
        vencido = ejercicio(Estado.ABIERTO, datetime.date(2026, 1, 1))
        antes = self.estado_de_la_base()

        resumen = self.resumir(datetime.date(2026, 12, 1))

        self.assertEqual((resumen.ejercicio_numero, resumen.ejercicio_estado, resumen.ejercicio_por_abrir), (1, Estado.EN_CIERRE, False))
        self.assertEqual(EjercicioContable.objects.get(pk=vencido.pk).estado_ejercicio, Estado.ABIERTO)
        self.assertEqual(self.estado_de_la_base(), antes)

    def test_ext_5e_con_el_abierto_vencido_una_fecha_anterior_al_primero_se_rechaza(self):
        """La validación de la fecha del resumen usa el ejercicio previsto: una anterior al primero sigue siendo `fecha_anterior_al_primer_ejercicio`."""
        ejercicio(Estado.ABIERTO, datetime.date(2026, 1, 1))

        with self.assertRaises(ErrorContable) as contexto:
            self.resumir(datetime.date(2025, 12, 1))
        self.assertEqual(contexto.exception.codigo, "fecha_anterior_al_primer_ejercicio")

    def test_regla_h9_con_varios_ejercicios_atrasados_el_resumen_reproduce_las_vueltas_de_la_apertura(self):
        """CON-ABR-EJE («varias vueltas»): con el abierto de 2025 y hoy en 2027 el sistema abriría 2026 (que queda «en cierre») y 2027; 2025 quedaría cerrado. El resumen lo anticipa y el registro lo confirma."""
        vencido = ejercicio(Estado.ABIERTO, datetime.date(2025, 1, 1))
        antes = self.estado_de_la_base()

        de_2026 = self.resumir(datetime.date(2026, 6, 1))
        de_hoy = self.resumir(HOY)
        with self.assertRaises(ErrorContable) as contexto:
            self.resumir(datetime.date(2025, 6, 1))

        self.assertEqual((de_2026.ejercicio_numero, de_2026.ejercicio_estado, de_2026.ejercicio_por_abrir), (2, Estado.EN_CIERRE, True))
        self.assertEqual((de_hoy.ejercicio_numero, de_hoy.ejercicio_estado, de_hoy.ejercicio_por_abrir), (3, Estado.ABIERTO, True))
        self.assertEqual(contexto.exception.codigo, "fecha_en_ejercicio_cerrado")
        self.assertIn("31/12/2025", contexto.exception.mensaje)
        self.assertEqual(self.estado_de_la_base(), antes)
        # Control: registrar de verdad cae donde dijo el resumen.
        asiento = asientos.registrar_asiento_manual(self.contador, datetime.date(2026, 6, 1), DESCRIPCION, _apertura(), hoy=HOY)
        self.assertEqual(asiento.ejercicio.fecha_inicio_ejercicio, datetime.date(2026, 1, 1))
        self.assertEqual(asiento.ejercicio.estado_ejercicio, Estado.EN_CIERRE)
        self.assertEqual(EjercicioContable.objects.get(pk=vencido.pk).estado_ejercicio, Estado.CERRADO)
        verificar_invariantes_contables()
