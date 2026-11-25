# Pruebas de CON-CNS-PCT «Consultar Plan de Cuentas» (CON-03a paso 2; docs/casos_de_uso/contabilidad/plan_de_cuentas.md; D-84 punto 7): la pestaña «Plan de
# cuentas» de «Contabilidad», con el cliente de Django. Cada prueba arma sus datos. La consulta no audita (regla 6, SEG-14).
import datetime
import html
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import EjercicioContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin, asiento_de_prueba, ejercicio
from core.models import Agronomo, Capataz, Contador, Gerente, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
URL = reverse("contabilidad:plan")


def _texto(respuesta):
    return html.unescape(respuesta.content.decode())


class ConCnsPctBase(PlanDeCuentasMixin, TestCase):
    def setUp(self):
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com")
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))

    def ver(self, cuenta, **parametros):
        self.client.force_login(cuenta)
        return self.client.get(URL, parametros)


class ConCnsPctAlcanceTests(ConCnsPctBase):
    """Regla 1: el Contador y el Gerente ven el plan completo; el Vendedor no (y ningún otro rol)."""

    def test_regla_1_el_contador_ve_el_plan(self):
        """Regla 1 de CON-CNS-PCT: el Contador ve el plan."""
        self.assertEqual(self.ver(self.contador).status_code, 200)

    def test_regla_1_el_gerente_ve_el_plan_con_y_sin_contador_activo(self):
        """Regla 1: el Gerente ve el plan completo, haya o no Contador activo."""
        self.assertEqual(self.ver(self.gerente).status_code, 200)
        Contador.objects.update(is_active=False)
        self.assertEqual(self.ver(self.gerente).status_code, 200)

    def test_regla_1_el_vendedor_y_los_demas_roles_reciben_403(self):
        """Regla 1 y SEG-13: el Vendedor no ve el plan; tampoco el Agrónomo ni el Capataz."""
        for clase, email in ((Vendedor, "v@infoponia.com"), (Agronomo, "a@infoponia.com"), (Capataz, "c@infoponia.com")):
            with self.subTest(rol=clase.__name__):
                self.assertEqual(self.ver(crear_cuenta(clase, email=email)).status_code, 403)

    def test_regla_1_sin_sesion_lleva_al_inicio_de_sesion(self):
        """Toda pantalla exige sesión (D-25)."""
        respuesta = self.client.get(URL)

        self.assertEqual(respuesta.status_code, 302)
        self.assertNotEqual(respuesta["Location"], URL)


class ConCnsPctArbolTests(ConCnsPctBase):
    """Reglas 2 y 3: el árbol completo y ordenado, con el tipo y la descripción de cada cuenta."""

    def test_regla_2_muestra_las_19_cuentas_ordenadas_por_codigo_con_sus_rubros(self):
        """Regla 2: árbol por rubro y subrubro con código, nombre y tipo; las 19 cuentas del plan aprobado, en orden de código."""
        contenido = _texto(self.ver(self.contador))

        posiciones = [contenido.index(f'id="cuenta-{codigo}"') for codigo in cuentas.TODAS]
        self.assertEqual(posiciones, sorted(posiciones))
        self.assertEqual(len(cuentas.TODAS), 19)
        for rubro in ("Activo", "Pasivo", "Patrimonio neto", "Ingresos", "Egresos"):
            self.assertIn(rubro, contenido)
        for subrubro in cuentas.SUBRUBROS.values():
            self.assertIn(subrubro, contenido)

    def test_regla_2_cada_cuenta_trae_su_codigo_su_nombre_y_su_tipo(self):
        """Regla 2: código, nombre y tipo (Activo, Pasivo, Patrimonio neto, Resultado positivo, Resultado negativo)."""
        contenido = _texto(self.ver(self.contador))

        for codigo, nombre, tipo in (
            ("1.1.01", "Caja", "Activo"),
            ("2.1.02", "Indemnizaciones a Pagar", "Pasivo"),
            ("3.1.01", "Capital Inicial", "Patrimonio neto"),
            ("4.1.01", "Ventas", "Resultado positivo"),
            ("5.1.06", "Diferencias de Inventario de Insumos", "Resultado negativo"),
        ):
            with self.subTest(cuenta=codigo):
                self.assertIn(codigo, contenido)
                self.assertIn(nombre, contenido)
                self.assertIn(tipo, contenido)

    def test_regla_3_cada_cuenta_del_plan_tiene_su_descripcion(self):
        """Regla 3: el diccionario `DESCRIPCION_DE_CUENTA` cubre exactamente las cuentas del plan (si una tarea suma una cuenta y no su texto, falla)."""
        self.assertEqual(set(cuentas.DESCRIPCION_DE_CUENTA), set(cuentas.TODAS))
        self.assertTrue(all(texto.strip() for texto in cuentas.DESCRIPCION_DE_CUENTA.values()))

    def test_regla_3_la_pantalla_muestra_la_descripcion_de_cada_cuenta(self):
        """Regla 3: para cada cuenta se ve para qué se usa y qué casos de uso la mueven."""
        contenido = _texto(self.ver(self.contador))

        for codigo in cuentas.TODAS:
            with self.subTest(cuenta=codigo):
                self.assertIn(cuentas.DESCRIPCION_DE_CUENTA[codigo], contenido)

    def test_regla_5_avisa_que_no_hay_iva(self):
        """Regla 5: «Sin IVA (simplificación declarada)» se dice en la pantalla."""
        self.assertContains(self.ver(self.contador), "Sin IVA: es una simplificación declarada")

    def test_regla_2_el_buscador_filtra_por_codigo_y_por_nombre(self):
        """El buscador de `tabPlan`: por código o por nombre; sin coincidencias, un aviso y no una tabla vacía."""
        por_codigo = _texto(self.ver(self.contador, q="5.1.0"))
        por_nombre = _texto(self.ver(self.contador, q="caja"))
        ninguna = _texto(self.ver(self.contador, q="zzz"))

        self.assertIn('id="cuenta-5.1.01"', por_codigo)
        self.assertNotIn('id="cuenta-1.1.01"', por_codigo)
        self.assertIn('id="cuenta-1.1.01"', por_nombre)
        self.assertNotIn('id="cuenta-4.1.01"', por_nombre)
        self.assertIn("No hay cuentas con ese texto", ninguna)
        self.assertNotIn("<table", ninguna)


class ConCnsPctSaldosYEnlacesTests(ConCnsPctBase):
    """Regla 4: desde cada cuenta se va al libro de gestión, vista por cuenta, con su filtro ya puesto."""

    def test_regla_4_cada_cuenta_enlaza_al_libro_por_cuenta_con_el_ejercicio_abierto(self):
        """Regla 4: el enlace lleva al libro, vista por cuenta, con la cuenta y el ejercicio ya elegidos."""
        contenido = _texto(self.ver(self.contador))

        libro = reverse("contabilidad:libro")
        for codigo in cuentas.TODAS:
            with self.subTest(cuenta=codigo):
                self.assertIn(f"{libro}?vista=cuenta&cuenta={codigo}&ejercicio={self.abierto.pk}", contenido)

    def test_regla_4_una_cuenta_con_movimientos_muestra_su_saldo_y_una_sin_movimientos_lo_dice(self):
        """El saldo del ejercicio abierto sale de `libro.saldo_por_cuenta`; sin movimientos dice «Sin movimientos»."""
        asiento_de_prueba(
            self.abierto,
            datetime.date(2027, 3, 1),
            [(cuentas.CAJA, DEBE, Decimal("1500.00")), (cuentas.CAPITAL_INICIAL, HABER, Decimal("1500.00"))],
        )

        contenido = _texto(self.ver(self.contador))

        self.assertIn("$ 1.500,00", contenido)
        self.assertIn("Sin movimientos", contenido)

    def test_regla_4_un_saldo_contrario_a_su_naturaleza_se_marca(self):
        """Regla 4 de CON-CNS-LGS (vale acá también): 5.1.06 acreedora se marca «saldo contrario a su naturaleza»."""
        asiento_de_prueba(
            self.abierto,
            datetime.date(2027, 3, 1),
            [(cuentas.CAJA, DEBE, Decimal("20.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, HABER, Decimal("20.00"))],
        )

        self.assertContains(self.ver(self.contador), "saldo contrario a su naturaleza", count=1)

    def test_sin_ejercicio_abierto_el_plan_se_ve_sin_saldos_ni_enlaces(self):
        """Sin ejercicio abierto (contabilidad sin poner en marcha) el plan igual se consulta: sin saldos, sin enlaces y con un aviso."""
        EjercicioContable.objects.all().delete()

        respuesta = self.ver(self.contador)

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "?vista=cuenta")
        self.assertContains(respuesta, "Todavía no hay un ejercicio abierto")

    def test_regla_6_la_consulta_no_audita(self):
        """Regla 6 de CON-CNS-PCT (SEG-14): ver el plan no escribe en la auditoría."""
        antes = RegistroAuditoria.objects.count()

        self.ver(self.contador, q="caja")
        self.ver(self.gerente)

        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_la_pantalla_no_hace_consultas_por_cuenta(self):
        """«Hecho cuando»: sin consultas por fila; con y sin movimientos cargados se hacen las mismas consultas."""
        self.client.force_login(self.contador)
        self.client.get(URL)  # la primera vez arma cachés
        with CaptureQueriesContext(connection) as sin_asientos:
            self.client.get(URL)
        for _ in range(5):
            asiento_de_prueba(
                self.abierto,
                datetime.date(2027, 3, 1),
                [(cuentas.CAJA, DEBE, Decimal("10.00")), (cuentas.VENTAS, HABER, Decimal("10.00"))],
            )
        with CaptureQueriesContext(connection) as con_asientos:
            self.client.get(URL)

        self.assertEqual(len(sin_asientos), len(con_asientos))
        self.assertLessEqual(len(con_asientos), 20)
