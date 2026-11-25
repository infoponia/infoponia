# Pruebas de las pantallas de «Contabilidad» (CON-03a paso 4; CON-CNS-LGS, CON-CNS-PCT y CON-CRR-EJE, «Pantallas»): acceso por rol, las dos vistas del libro, filtros,
# paginación, enlaces, la ficha del asiento, la lista de ejercicios, el cierre por pantalla, la alerta del Panel y el menú. Con el cliente de Django; cada prueba arma sus datos
# y lo que depende de la fecha recibe «hoy» (se fija `timezone.localdate`). La consulta no audita (SEG-14).
import datetime
import html
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from contabilidad import cuentas, extensiones
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import EjercicioContable, OrigenDocumento
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import PlanDeCuentasMixin, asiento_de_prueba, ejercicio, origen_de_prueba
from core.models import Agronomo, Capataz, Contador, Gerente, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
HOY = datetime.date(2027, 3, 10)
LIBRO = reverse("contabilidad:libro")
EJERCICIOS = reverse("contabilidad:ejercicios")
PLAN = reverse("contabilidad:plan")


def _d(texto):
    return Decimal(texto)


def _caja_a_ventas(importe="100.00"):
    return [(cuentas.CAJA, DEBE, _d(importe)), (cuentas.VENTAS, HABER, _d(importe))]


def _texto(respuesta):
    return html.unescape(respuesta.content.decode())


class VistaBase(PlanDeCuentasMixin, TestCase):
    """Datos comunes: un Contador, un Gerente, el ejercicio de 2026 «cerrado» y el de 2027 «abierto». «Hoy» es el 10/3/2027."""

    def setUp(self):
        patcher = mock.patch("django.utils.timezone.localdate", return_value=HOY)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com")
        self.cerrado = ejercicio(Estado.CERRADO, datetime.date(2026, 1, 1))
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))

    def get(self, usuario, url, **parametros):
        self.client.force_login(usuario)
        return self.client.get(url, parametros)

    def mensajes(self, respuesta):
        return [str(m) for m in respuesta.context["messages"]]


class AccesoPorRolTests(VistaBase):
    """Regla 1 de CON-CNS-LGS, CON-CNS-PCT y CON-CRR-EJE (SEG-13): el Contador y el Gerente entran; el Vendedor y los demás, 403; sin sesión, al inicio de sesión."""

    def setUp(self):
        super().setUp()
        self.asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        self.urls = [
            LIBRO,
            PLAN,
            EJERCICIOS,
            reverse("contabilidad:asiento", args=[self.abierto.pk, self.asiento.numero_asiento]),
        ]

    def test_regla_1_el_contador_y_el_gerente_entran_a_todas_las_pantallas_de_consulta(self):
        """Regla 1: el Contador y el Gerente ven el libro, el plan, los ejercicios y la ficha, haya o no Contador activo."""
        for url in self.urls:
            for cuenta in (self.contador, self.gerente):
                with self.subTest(url=url, rol=cuenta.rol):
                    self.assertEqual(self.get(cuenta, url).status_code, 200)
        Contador.objects.update(is_active=False)
        for url in self.urls:
            with self.subTest(url=url, rol="gerente sin contador"):
                self.assertEqual(self.get(self.gerente, url).status_code, 200)

    def test_regla_1_el_vendedor_y_los_demas_roles_reciben_403_en_todas_las_pantallas(self):
        """Regla 1 y X3: el Vendedor no tiene acceso; tampoco el Agrónomo ni el Capataz (ni por la dirección escrita a mano)."""
        en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2025, 1, 1))
        urls = self.urls + [reverse("contabilidad:cierre", args=[en_cierre.pk])]
        for clase, email in ((Vendedor, "v@infoponia.com"), (Agronomo, "a@infoponia.com"), (Capataz, "c@infoponia.com")):
            cuenta = crear_cuenta(clase, email=email)
            for url in urls:
                with self.subTest(url=url, rol=clase.__name__):
                    self.assertEqual(self.get(cuenta, url).status_code, 403)

    def test_sin_sesion_lleva_al_inicio_de_sesion(self):
        """Toda pantalla exige sesión (D-25)."""
        for url in self.urls:
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 302)
                self.assertNotEqual(respuesta["Location"], url)

    def test_el_menu_trae_contabilidad_para_el_contador_y_el_gerente_y_no_para_los_demas(self):
        """Disparador de CON-03a: la entrada «Contabilidad» del menú, para el Contador y el Gerente; el Vendedor y el Agrónomo no la ven."""
        for cuenta in (self.contador, self.gerente):
            textos = [e["texto"] for e in self.get(cuenta, reverse("core:inicio")).context["menu"]]
            self.assertIn("Contabilidad", textos)
        for clase, email in ((Vendedor, "v@infoponia.com"), (Agronomo, "a@infoponia.com")):
            textos = [e["texto"] for e in self.get(crear_cuenta(clase, email=email), reverse("core:inicio")).context["menu"]]
            self.assertNotIn("Contabilidad", textos)


class LibroCronologicoVistaTests(VistaBase):
    """Regla 2 de CON-CNS-LGS: la vista cronológica y sus filtros."""

    def test_regla_2_muestra_los_asientos_del_ejercicio_abierto_con_su_numero_fecha_descripcion_tipo_y_movimientos(self):
        """Regla 2: de cada asiento se ve el número, la fecha, la descripción, el tipo, el total y si está anulado; los de otro ejercicio no aparecen."""
        asiento_de_prueba(self.cerrado, datetime.date(2026, 5, 1), _caja_a_ventas("777.00"), descripcion="Asiento viejo")
        asiento_de_prueba(self.abierto, datetime.date(2027, 2, 3), _caja_a_ventas("250.00"), descripcion="Venta de mostrador")
        asiento_de_prueba(self.abierto, datetime.date(2027, 2, 4), _caja_a_ventas("90.00"), origen=origen_de_prueba(OrigenDocumento.Tipo.BITACORA))

        contenido = _texto(self.get(self.contador, LIBRO))

        self.assertIn("Venta de mostrador", contenido)
        self.assertIn("N.º 1", contenido)
        self.assertIn("03/02/2027", contenido)
        self.assertIn("$ 250,00", contenido)
        self.assertIn("Manual", contenido)
        self.assertIn("Automático", contenido)
        self.assertIn("1.1.01 · Caja", contenido)
        self.assertNotIn("Asiento viejo", contenido)
        self.assertIn("Totales (2 asientos)", contenido)
        self.assertIn("$ 340,00", contenido)

    def test_regla_2_el_orden_es_por_fecha_y_a_igual_fecha_por_numero(self):
        """Regla 2 y H8: por fecha y, a igual fecha, por número de asiento."""
        asiento_de_prueba(self.abierto, datetime.date(2027, 3, 1), _caja_a_ventas(), descripcion="Tardío N1")
        asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), _caja_a_ventas(), descripcion="Temprano N2")
        asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), _caja_a_ventas(), descripcion="Temprano N3")

        contenido = _texto(self.get(self.contador, LIBRO))

        self.assertLess(contenido.index("Temprano N2"), contenido.index("Temprano N3"))
        self.assertLess(contenido.index("Temprano N3"), contenido.index("Tardío N1"))

    def test_regla_2_el_selector_de_ejercicio_muestra_otro_ejercicio(self):
        """Regla 2: «ejercicio (por defecto el abierto)»; con otro elegido se ven sus asientos."""
        asiento_de_prueba(self.cerrado, datetime.date(2026, 5, 1), _caja_a_ventas(), descripcion="Asiento viejo")

        contenido = _texto(self.get(self.contador, LIBRO, ejercicio=self.cerrado.pk))

        self.assertIn("Asiento viejo", contenido)

    def test_regla_2_los_filtros_de_texto_tipo_anulados_fechas_cuenta_y_origen(self):
        """Regla 2: filtros por texto, tipo, anulados, rango de fechas, cuenta y origen."""
        anulado = asiento_de_prueba(self.abierto, datetime.date(2027, 1, 10), _caja_a_ventas(), descripcion="Anulado A")
        asiento_de_prueba(self.abierto, datetime.date(2027, 1, 11), _caja_a_ventas(), descripcion="Contra de A", anula=anulado)
        asiento_de_prueba(
            self.abierto, datetime.date(2027, 2, 10), [(cuentas.BANCO, DEBE, _d("5.00")), (cuentas.OTROS_INGRESOS, HABER, _d("5.00"))], descripcion="Con banco"
        )
        asiento_de_prueba(self.abierto, datetime.date(2027, 2, 20), _caja_a_ventas(), origen=origen_de_prueba(OrigenDocumento.Tipo.CONTRATO))
        casos = (
            ({"q": "banco"}, ["Con banco"], ["Anulado A"]),
            ({"tipo": "contraasiento"}, ["Contra de A"], ["Con banco"]),
            ({"tipo": "automatico"}, ["Contrato"], ["Con banco"]),
            ({"anulados": "si"}, ["Anulado A"], ["Con banco"]),
            ({"anulados": "no"}, ["Contra de A"], ["Anulado A"]),
            ({"desde": "2027-02-01", "hasta": "2027-02-15"}, ["Con banco"], ["Anulado A"]),
            ({"cuenta": cuentas.BANCO}, ["Con banco"], ["Anulado A"]),
            ({"origen": "contrato"}, ["Contrato"], ["Con banco"]),
        )
        for parametros, deben_estar, no_deben_estar in casos:
            with self.subTest(filtros=parametros):
                contenido = _texto(self.get(self.contador, LIBRO, **parametros))
                for texto in deben_estar:
                    self.assertIn(texto, contenido)
                for texto in no_deben_estar:
                    self.assertNotIn(texto, contenido)

    def test_regla_2_sin_resultados_con_filtros_dice_que_pruebes_quitarlos(self):
        """El estado vacío con filtros se distingue del ejercicio sin asientos y ofrece «Quitar filtros»."""
        asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), descripcion="Algo")

        con_filtro = _texto(self.get(self.contador, LIBRO, q="zzz"))
        sin_filtro = _texto(self.get(self.contador, LIBRO, ejercicio=self.cerrado.pk))

        self.assertIn("No hay asientos con esos filtros", con_filtro)
        self.assertIn("Quitar filtros", con_filtro)
        self.assertIn("Este ejercicio todavía no tiene asientos", sin_filtro)
        self.assertNotIn("Quitar filtros", sin_filtro)

    def test_un_filtro_invalido_se_marca_y_la_pantalla_sigue_viendose(self):
        """Fechas al revés y un tipo desconocido: la pantalla responde 200, marca el error y ignora lo inválido (nunca un 500)."""
        asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), descripcion="Sigue visible")

        al_reves = self.get(self.contador, LIBRO, desde="2027-03-01", hasta="2027-01-01")
        tipo_malo = self.get(self.contador, LIBRO, tipo="inventado", ejercicio="no-es-un-numero")

        for respuesta in (al_reves, tipo_malo):
            self.assertEqual(respuesta.status_code, 200)
            self.assertIn("Sigue visible", _texto(respuesta))
        self.assertIn("no puede ser anterior", _texto(al_reves))

    def test_regla_6_el_ejercicio_en_cierre_y_el_cerrado_llevan_su_aviso(self):
        """Regla 6 y «Pantallas»: en cierre, «todavía se pueden registrar asientos de ese período»; cerrado, «solo de consulta»."""
        en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2025, 1, 1))

        self.assertIn("Todavía se pueden registrar asientos de ese período", _texto(self.get(self.contador, LIBRO, ejercicio=en_cierre.pk)))
        self.assertIn("está cerrado. Sus asientos son solo de consulta", _texto(self.get(self.contador, LIBRO, ejercicio=self.cerrado.pk)))
        self.assertNotIn("solo de consulta", _texto(self.get(self.contador, LIBRO)))

    def test_sin_ejercicios_la_pantalla_lo_explica(self):
        """Contabilidad sin poner en marcha: ni error ni tabla vacía, un texto que dice qué hacer."""
        EjercicioContable.objects.all().delete()

        respuesta = self.get(self.contador, LIBRO)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Todavía no hay ejercicios contables", _texto(respuesta))

    def test_la_pantalla_explica_que_no_es_el_libro_diario_legal(self):
        """«Pantallas»: una línea bajo el título explica «Libro de gestión» (glosario: no es el libro diario legal)."""
        self.assertIn("No es el libro diario ni el mayor legales", _texto(self.get(self.contador, LIBRO)))

    def test_las_acciones_de_asientos_manuales_se_muestran_solo_a_quien_puede_registrar(self):
        """Marca del caso de uso (CON-03b, reemplaza a la de «escondidas hasta CON-03b»): «Registrar asiento» y «Contraasentar» las ve el Contador; el Gerente con un Contador
        activo ve el libro y la ficha sin acciones y con «Lo registra el Contador»; sin Contador activo, el Gerente las ve (D-85 punto 5)."""
        asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        ficha = reverse("contabilidad:asiento", args=[self.abierto.pk, asiento.numero_asiento])
        for url in (LIBRO, ficha):
            contenido = _texto(self.get(self.contador, url))
            self.assertTrue("Registrar asiento" in contenido or "Contraasentar" in contenido)
            self.assertNotIn("Lo registra el Contador", contenido)
            contenido = _texto(self.get(self.gerente, url))
            self.assertNotIn("Contraasentar", contenido)
            self.assertNotIn("Registrar asiento", contenido)
            self.assertIn("Lo registra el Contador", contenido)
        self.assertIn("Registrar asiento", _texto(self.get(self.contador, LIBRO)))
        self.assertIn("Contraasentar", _texto(self.get(self.contador, ficha)))
        Contador.objects.update(is_active=False)
        self.assertIn("Registrar asiento", _texto(self.get(self.gerente, LIBRO)))
        self.assertIn("Contraasentar", _texto(self.get(self.gerente, ficha)))

    def test_paginacion_de_50_asientos_conserva_los_filtros(self):
        """«Paginación»: 50 asientos por página; «Siguiente» conserva los filtros."""
        for i in range(51):
            asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), _caja_a_ventas(), descripcion=f"Venta {i:02d}")

        primera = _texto(self.get(self.contador, LIBRO, q="Venta"))
        segunda = _texto(self.get(self.contador, LIBRO, q="Venta", pagina=2))

        self.assertIn("página 1 de 2", primera)
        self.assertEqual(primera.count('class="grp-a"'), 50)
        self.assertIn("pagina=2", primera)
        self.assertIn("q=Venta", primera[primera.index("pagina=2") - 80 : primera.index("pagina=2") + 20])
        self.assertEqual(segunda.count('class="grp-a"'), 1)
        self.assertIn("Totales (51 asientos)", segunda)
        self.assertNotIn("pagina=3", segunda)

    def test_la_lista_no_hace_consultas_por_asiento(self):
        """«Hecho cuando»: sin consultas por fila; con 3 y con 25 asientos se hacen las mismas consultas."""
        self.client.force_login(self.contador)
        for _ in range(3):
            asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen_de_prueba())
        self.client.get(LIBRO)
        with CaptureQueriesContext(connection) as pocas:
            self.client.get(LIBRO)
        for _ in range(22):
            asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), descripcion="Manual")
        with CaptureQueriesContext(connection) as muchas:
            self.client.get(LIBRO)

        self.assertEqual(len(pocas), len(muchas))

    def test_regla_9_el_libro_no_audita(self):
        """Regla 9 (SEG-14): ver el libro, la ficha, los ejercicios y el plan no escribe en la auditoría."""
        asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        antes = RegistroAuditoria.objects.count()

        for url in (LIBRO, EJERCICIOS, PLAN, reverse("contabilidad:asiento", args=[self.abierto.pk, asiento.numero_asiento])):
            self.get(self.contador, url)

        self.assertEqual(RegistroAuditoria.objects.count(), antes)


class LibroPorCuentaVistaTests(VistaBase):
    """Reglas 3, 4 y 8 de CON-CNS-LGS: la vista por cuenta."""

    def test_regla_3_sin_cuenta_elegida_muestra_el_plan_con_saldos_y_enlaces(self):
        """Regla 3: «Elegí una cuenta»: las 19 cuentas con saldo al inicio y actual y un enlace a sus movimientos."""
        asiento_de_prueba(self.abierto, HOY, _caja_a_ventas("100.00"))

        contenido = _texto(self.get(self.contador, LIBRO, vista="cuenta"))

        self.assertIn("Elegí una cuenta para ver sus movimientos", contenido)
        for codigo in cuentas.TODAS:
            self.assertIn(f"cuenta={codigo}", contenido)
        self.assertIn("$ 100,00", contenido)

    def test_regla_3_con_una_cuenta_muestra_debe_haber_y_saldo_acumulado(self):
        """Regla 3: los movimientos de la cuenta con Debe, Haber y saldo acumulado, y el enlace a cada asiento."""
        asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), _caja_a_ventas("300.00"), descripcion="Cobro")
        asiento_de_prueba(self.abierto, datetime.date(2027, 3, 1), [(cuentas.GASTOS_GENERALES, DEBE, _d("50.00")), (cuentas.CAJA, HABER, _d("50.00"))], descripcion="Pago")

        contenido = _texto(self.get(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.CAJA))

        self.assertIn("1.1.01 · Caja", contenido)
        self.assertIn("$ 300,00", contenido)
        self.assertIn("$ 250,00", contenido)  # saldo después del pago
        self.assertIn("Saldo actual", contenido)
        self.assertIn(reverse("contabilidad:asiento", args=[self.abierto.pk, 1]), contenido)

    def test_regla_4_la_patrimonial_arrastra_y_la_de_resultado_empieza_en_cero(self):
        """Regla 4: Caja arrastra el saldo de 2026; Ventas (resultado) no. Cada una lo dice."""
        asiento_de_prueba(self.cerrado, datetime.date(2026, 5, 1), _caja_a_ventas("1000.00"))
        asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), _caja_a_ventas("300.00"))

        caja = _texto(self.get(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.CAJA))
        ventas = _texto(self.get(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.VENTAS))

        self.assertIn("Arrastra los ejercicios anteriores", caja)
        self.assertIn("$ 1.000,00", caja)
        self.assertIn("$ 1.300,00", caja)
        self.assertIn("Empieza en cero cada ejercicio", ventas)
        self.assertNotIn("$ 1.000,00", ventas)

    def test_regla_4_un_saldo_contrario_a_su_naturaleza_se_marca(self):
        """Regla 4: Diferencias de Inventario (5.1.06) acreedora se marca, también en la vista por cuenta."""
        asiento_de_prueba(self.abierto, HOY, [(cuentas.CAJA, DEBE, _d("20.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, HABER, _d("20.00"))])

        contenido = _texto(self.get(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.DIFERENCIAS_DE_INVENTARIO))

        self.assertIn("saldo contrario a su naturaleza", contenido)

    def test_regla_8_desde_cada_cuenta_se_va_a_su_ficha_en_el_plan(self):
        """Regla 8: desde la cuenta se puede ir al plan de cuentas (CON-CNS-PCT)."""
        contenido = _texto(self.get(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.CAJA))

        self.assertIn(f"{PLAN}#cuenta-1.1.01", contenido)

    def test_una_cuenta_sin_movimientos_lo_dice(self):
        """El estado vacío de la vista por cuenta."""
        self.assertIn("Esta cuenta no tiene movimientos en el ejercicio", _texto(self.get(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.BANCO)))

    def test_paginacion_de_100_movimientos_por_pagina_con_el_saldo_que_sigue(self):
        """«Paginación»: 100 movimientos por página; la página 2 sigue el saldo de la 1."""
        for _ in range(101):
            asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), _caja_a_ventas("1.00"))

        primera = _texto(self.get(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.CAJA))
        segunda = _texto(self.get(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.CAJA, pagina=2))

        self.assertIn("página 1 de 2", primera)
        self.assertIn("$ 100,00", primera)
        self.assertIn("$ 101,00", segunda)
        self.assertIn("vista=cuenta", primera[primera.index("pagina=2") - 120 : primera.index("pagina=2") + 20])

    def test_una_cuenta_inexistente_se_marca_y_la_pantalla_se_ve(self):
        """Un código que no existe en la dirección: error en el filtro y se muestra el plan; nunca un 500."""
        respuesta = self.get(self.contador, LIBRO, vista="cuenta", cuenta="9.9.99")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Elegí una cuenta para ver sus movimientos", _texto(respuesta))

    def test_la_vista_por_cuenta_no_hace_consultas_por_cuenta(self):
        """Sin consultas por fila: el listado de cuentas hace las mismas consultas con y sin movimientos."""
        self.client.force_login(self.contador)
        self.client.get(LIBRO, {"vista": "cuenta"})
        with CaptureQueriesContext(connection) as sin_asientos:
            self.client.get(LIBRO, {"vista": "cuenta"})
        for _ in range(5):
            asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        with CaptureQueriesContext(connection) as con_asientos:
            self.client.get(LIBRO, {"vista": "cuenta"})

        self.assertEqual(len(sin_asientos), len(con_asientos))


class FichaDelAsientoVistaTests(VistaBase):
    """Reglas 5 y 6 de CON-CNS-LGS: la ficha del asiento."""

    def ficha(self, asiento, cuenta=None):
        return self.get(cuenta or self.contador, reverse("contabilidad:asiento", args=[asiento.ejercicio_id, asiento.numero_asiento]))

    def test_regla_5_la_ficha_trae_fecha_ejercicio_descripcion_movimientos_y_totales(self):
        """Regla 5: número, fecha, ejercicio, descripción y movimientos (cuenta, Debe o Haber, importe)."""
        asiento = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 3), _caja_a_ventas("250.00"), descripcion="Venta de mostrador")

        contenido = _texto(self.ficha(asiento))

        self.assertIn("Asiento N.º 1", contenido)
        self.assertIn("03/02/2027", contenido)
        self.assertIn("Ejercicio 2", contenido)
        self.assertIn("Venta de mostrador", contenido)
        self.assertIn("1.1.01 · Caja", contenido)
        self.assertIn("4.1.01 · Ventas", contenido)
        self.assertIn("$ 250,00", contenido)
        self.assertIn("Sin documento de origen", contenido)

    def test_regla_5_el_origen_lleva_su_enlace_si_la_app_lo_registro_y_si_no_solo_el_texto(self):
        """Regla 5 y «Enlace al origen»: con registrante, el documento es un enlace; sin registrante, solo el texto del tipo."""
        origen = origen_de_prueba(OrigenDocumento.Tipo.BITACORA)
        asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen)
        with mock.patch.object(extensiones, "_ENLACES_DE_ORIGEN", {}):
            sin = _texto(self.ficha(asiento))
            extensiones.registrar_enlace_de_origen("bitacora", lambda o: (f"Bitácora N.º {o.pk}", "/produccion/bitacora/"))
            con = _texto(self.ficha(asiento))

        self.assertIn("Bitácora", sin)
        self.assertNotIn('href="/produccion/bitacora/"', sin)
        self.assertIn('<a class="link" href="/produccion/bitacora/">', con)

    def test_regla_5_un_origen_con_enlace_peligroso_no_ejecuta_nada(self):
        """El texto y la dirección que devuelve un registrante se escapan en la ficha (nada de HTML sin escapar)."""
        asiento = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen_de_prueba(OrigenDocumento.Tipo.BITACORA))
        with mock.patch.object(extensiones, "_ENLACES_DE_ORIGEN", {}):
            extensiones.registrar_enlace_de_origen("bitacora", lambda o: ("<script>x</script>", "/a/?b=1&c=2"))
            crudo = self.ficha(asiento).content.decode()

        self.assertNotIn("<script>x</script>", crudo)
        self.assertIn("&lt;script&gt;", crudo)

    def test_regla_5_quien_registro_un_manual_sale_de_la_auditoria_y_en_un_automatico_no_se_muestra(self):
        """Regla 5: «quién lo registró (si es manual o contraasiento; si lo registró el Gerente, desde el log de auditoría)»."""
        manual = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())
        RegistroAuditoria.objects.registrar(self.gerente, RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE, [manual], {})
        automatico = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), origen=origen_de_prueba())

        self.assertIn("Registrado por", _texto(self.ficha(manual)))
        self.assertIn('<span class="d">Gerente</span>', _texto(self.ficha(manual)))
        self.assertNotIn("Registrado por", _texto(self.ficha(automatico)))

    def test_regla_5_un_anulado_enlaza_a_su_contraasiento_y_el_contraasiento_al_anulado(self):
        """Regla 5: «si anula a otro asiento o fue anulado por otro (con acceso a él)»."""
        original = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), descripcion="Mal cargado")
        contra = asiento_de_prueba(self.abierto, HOY, _caja_a_ventas(), descripcion="Contraasiento de N.º 1", anula=original)

        de_original = _texto(self.ficha(original))
        de_contra = _texto(self.ficha(contra))

        self.assertIn("Anulado.", de_original)
        self.assertIn(reverse("contabilidad:asiento", args=[self.abierto.pk, contra.numero_asiento]), de_original)
        self.assertIn("Este contraasiento anula el asiento", de_contra)
        self.assertIn(reverse("contabilidad:asiento", args=[self.abierto.pk, original.numero_asiento]), de_contra)

    def test_regla_6_un_asiento_de_un_ejercicio_cerrado_se_ve_y_lo_dice(self):
        """Regla 6: los asientos de un ejercicio cerrado se ven pero no se modifican."""
        asiento = asiento_de_prueba(self.cerrado, datetime.date(2026, 5, 1), _caja_a_ventas())

        self.assertIn("es solo de consulta", _texto(self.ficha(asiento)))

    def test_un_asiento_inexistente_es_404(self):
        """Un número que no existe en ese ejercicio."""
        self.assertEqual(self.get(self.contador, reverse("contabilidad:asiento", args=[self.abierto.pk, 99])).status_code, 404)

    def test_la_ficha_vuelve_al_libro_del_mismo_ejercicio(self):
        """El enlace «Libro de gestión» de la ficha conserva el ejercicio."""
        asiento = asiento_de_prueba(self.cerrado, datetime.date(2026, 5, 1), _caja_a_ventas())

        self.assertIn(f"{LIBRO}?ejercicio={self.cerrado.pk}", _texto(self.ficha(asiento)))


class EjerciciosVistaTests(VistaBase):
    """CON-CRR-EJE, «Pantallas»: la pestaña «Ejercicios»."""

    def setUp(self):
        super().setUp()
        self.abierto.delete()
        self.cerrado.delete()
        # Tres ejercicios consecutivos que no se pisan: el último ya cerrado, uno que terminó el 28/2/2027 (hace 10 días) y el abierto.
        self.cerrado = ejercicio(Estado.CERRADO, datetime.date(2025, 3, 1))
        self.en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 3, 1))
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 3, 1))

    def test_la_lista_trae_numero_rango_estado_asientos_y_quien_lo_cerro(self):
        """«Pantallas»: número, rango, estado, cantidad de asientos y quién lo cerró; el número es la posición por fecha de inicio."""
        EjercicioContable.objects.filter(pk=self.cerrado.pk).update(contador=self.contador)
        asiento_de_prueba(self.cerrado, datetime.date(2025, 5, 1), _caja_a_ventas())
        asiento_de_prueba(self.cerrado, datetime.date(2025, 5, 2), _caja_a_ventas())

        contenido = _texto(self.get(self.contador, EJERCICIOS))

        for numero in (1, 2, 3):
            self.assertIn(f"Ejercicio {numero}", contenido)
        self.assertLess(contenido.index("Ejercicio 3"), contenido.index("Ejercicio 1"))  # del más nuevo al más viejo
        self.assertIn("En cierre", contenido)
        self.assertIn("Terminó hace 10 días", contenido)  # 28/2/2027 → 10/3/2027
        self.assertIn("Lo cerró", contenido)
        self.assertIn("contador@infoponia.com", contenido)

    def test_el_texto_de_cuando_termino_no_dice_dias_negativos_con_fechas_simuladas(self):
        """Con `proceso_diario --fecha` (verificación a mano) un ejercicio «en cierre» puede terminar «en el futuro» de la fecha real: dice «Terminó hoy» o la fecha, nunca «hace -N días»."""
        with mock.patch("django.utils.timezone.localdate", return_value=datetime.date(2027, 2, 28)):
            hoy = _texto(self.get(self.contador, EJERCICIOS))
        with mock.patch("django.utils.timezone.localdate", return_value=datetime.date(2026, 12, 1)):
            antes = _texto(self.get(self.contador, EJERCICIOS))

        self.assertIn("Terminó hoy", hoy)
        self.assertIn("Terminó el 28/02/2027", antes)
        self.assertNotIn("hace -", antes)

    def test_regla_5_el_contador_ve_cerrar_ejercicio_y_el_gerente_solo_si_no_hay_contador_activo(self):
        """Regla 5 y D-30: «Cerrar ejercicio» se muestra a quien puede cerrar; el Gerente con un Contador activo ve la lista sin el botón."""
        cierre = reverse("contabilidad:cierre", args=[self.en_cierre.pk])

        self.assertIn(cierre, _texto(self.get(self.contador, EJERCICIOS)))
        self.assertNotIn(cierre, _texto(self.get(self.gerente, EJERCICIOS)))
        Contador.objects.update(is_active=False)
        self.assertIn(cierre, _texto(self.get(self.gerente, EJERCICIOS)))

    def test_solo_el_ejercicio_en_cierre_tiene_el_boton_y_todos_tienen_ver_libro(self):
        """Regla 1 de CON-CRR-EJE: el abierto y el cerrado no se cierran a mano; «Ver libro» abre el libro de cada uno."""
        contenido = _texto(self.get(self.contador, EJERCICIOS))

        self.assertEqual(contenido.count("Cerrar ejercicio"), 1)
        for ej in (self.cerrado, self.en_cierre, self.abierto):
            self.assertIn(f"{LIBRO}?ejercicio={ej.pk}", contenido)

    def test_la_pestana_ejercicios_marca_el_cierre_pendiente(self):
        """La barra de pestañas avisa «en cierre» (``ts`` del prototipo) y deja de avisar cuando no hay ninguno."""
        self.assertIn("en cierre", _texto(self.get(self.contador, PLAN)).split('aria-label="Contabilidad"')[1].split("</div>")[0])
        EjercicioContable.objects.filter(pk=self.en_cierre.pk).update(estado_ejercicio=Estado.CERRADO)
        self.assertNotIn("status-warn", _texto(self.get(self.contador, PLAN)).split('aria-label="Contabilidad"')[1].split("</div>")[0])

    def test_sin_ejercicios_la_lista_lo_explica(self):
        """Estado vacío."""
        EjercicioContable.objects.all().delete()

        self.assertIn("Todavía no hay ejercicios contables", _texto(self.get(self.contador, EJERCICIOS)))

    def test_no_hace_consultas_por_ejercicio(self):
        """Sin consultas por fila: con 3 y con 8 ejercicios se hacen las mismas consultas."""
        self.client.force_login(self.contador)
        self.client.get(EJERCICIOS)
        with CaptureQueriesContext(connection) as pocas:
            self.client.get(EJERCICIOS)
        for anio in range(2010, 2015):
            ejercicio(Estado.CERRADO, datetime.date(anio, 1, 1))
        with CaptureQueriesContext(connection) as muchas:
            self.client.get(EJERCICIOS)

        self.assertEqual(len(pocas), len(muchas))

    def test_ejercicios_numerados_cuenta_los_asientos_y_numera_por_fecha_de_inicio(self):
        """El número («Ejercicio 1») es la posición por fecha de inicio y trae la cantidad de asientos de cada uno, en una consulta."""
        asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())

        numerados = ejercicios.ejercicios_numerados()

        self.assertEqual([n.numero for n in numerados], [1, 2, 3])
        self.assertEqual([n.ejercicio for n in numerados], [self.cerrado, self.en_cierre, self.abierto])
        self.assertEqual([n.cantidad_de_asientos for n in numerados], [0, 0, 1])


class CierreVistaTests(VistaBase):
    """CON-CRR-EJE regla 4: la pantalla de confirmación del cierre y su envío."""

    def setUp(self):
        super().setUp()
        self.abierto.delete()
        self.cerrado.delete()
        self.en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))
        self.url = reverse("contabilidad:cierre", args=[self.en_cierre.pk])

    def test_regla_4_el_resumen_trae_rango_asientos_totales_y_el_aviso_de_que_no_se_deshace(self):
        """Regla 4: antes de confirmar, rango, cantidad de asientos, total del Debe y del Haber, y el aviso de que no se puede deshacer."""
        asiento_de_prueba(self.en_cierre, datetime.date(2026, 3, 1), _caja_a_ventas("100.00"))
        asiento_de_prueba(self.en_cierre, datetime.date(2026, 4, 1), _caja_a_ventas("40.50"))

        contenido = _texto(self.get(self.contador, self.url))

        self.assertIn("01/01/2026 al 31/12/2026", contenido)
        self.assertEqual(contenido.count("$ 140,50"), 2)
        self.assertIn("El cierre no se puede deshacer", contenido)
        self.assertIn("Revisé el libro de gestión", contenido)
        self.assertIn("al ejercicio 2", contenido)
        self.assertNotIn("porque no hay un Contador activo", contenido)

    def test_regla_4_un_gerente_sin_contador_ve_por_que_cierra_el_y_no_el_contador(self):
        """Regla 5: sin Contador activo, el Gerente cierra y la pantalla lo aclara."""
        Contador.objects.update(is_active=False)

        self.assertIn("porque no hay un Contador activo", _texto(self.get(self.gerente, self.url)))

    def test_regla_4_enviar_sin_confirmar_no_cierra_y_marca_el_error(self):
        """C9: sin la casilla marcada no se cierra: la pantalla vuelve con el error junto a la casilla."""
        self.client.force_login(self.contador)

        respuesta = self.client.post(self.url, {})

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Confirmá que revisaste el libro", _texto(respuesta))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, Estado.EN_CIERRE)

    def test_post_a_b_y_c_el_contador_confirma_y_el_ejercicio_queda_cerrado_con_su_auditoria(self):
        """Postcondiciones a, b y c por la pantalla: cerrado, asociado al Contador, auditado; vuelve a la lista con el aviso de éxito."""
        self.client.force_login(self.contador)

        respuesta = self.client.post(self.url, {"confirmo": "1"}, follow=True)

        self.assertRedirects(respuesta, EJERCICIOS)
        cerrado = EjercicioContable.objects.get(pk=self.en_cierre.pk)
        self.assertEqual((cerrado.estado_ejercicio, cerrado.contador_id), (Estado.CERRADO, self.contador.pk))
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_EJERCICIO_CONTABLE, usuario=self.contador).count(), 1)
        self.assertEqual(self.mensajes(respuesta), ["Cerraste el ejercicio N.º 1. Ya no recibe asientos."])
        self.assertNotIn(self.url, _texto(respuesta))  # ya no hay botón de cierre

    def test_regla_5_el_gerente_sin_contador_cierra_y_la_asociacion_queda_vacia(self):
        """Regla 5 y postcondición b: lo cierra el Gerente y `contador` queda vacío."""
        Contador.objects.update(is_active=False)
        self.client.force_login(self.gerente)

        self.client.post(self.url, {"confirmo": "1"})

        cerrado = EjercicioContable.objects.get(pk=self.en_cierre.pk)
        self.assertEqual((cerrado.estado_ejercicio, cerrado.contador_id), (Estado.CERRADO, None))

    def test_regla_5_el_gerente_con_contador_activo_recibe_403_y_no_cierra(self):
        """Regla 5: ni por GET ni por POST (la dirección escrita a mano): 403 y nada cambia."""
        self.client.force_login(self.gerente)

        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"confirmo": "1"}).status_code, 403)
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, Estado.EN_CIERRE)

    def test_regla_1_un_ejercicio_que_no_esta_en_cierre_vuelve_a_la_lista_con_un_aviso(self):
        """Regla 1: el abierto no se cierra a mano; la pantalla no lo ofrece y la dirección escrita a mano da un aviso, no un error."""
        self.client.force_login(self.contador)

        respuesta = self.client.get(reverse("contabilidad:cierre", args=[self.abierto.pk]), follow=True)

        self.assertRedirects(respuesta, EJERCICIOS)
        self.assertEqual(self.mensajes(respuesta), ["El ejercicio N.º 2 no está en cierre: no se puede cerrar."])
        self.assertEqual(EjercicioContable.objects.get(pk=self.abierto.pk).estado_ejercicio, Estado.ABIERTO)

    def test_un_ejercicio_inexistente_es_404(self):
        """Un id que no existe."""
        self.assertEqual(self.get(self.contador, reverse("contabilidad:cierre", args=[999999])).status_code, 404)

    def test_si_otro_lo_cerro_mientras_se_miraba_el_resumen_avisa_sin_romper(self):
        """`ejercicio_no_esta_en_cierre` del servicio (cambio simultáneo) se muestra como aviso y vuelve a la lista."""
        self.client.force_login(self.contador)
        with mock.patch.object(ejercicios, "cerrar_ejercicio", side_effect=ErrorContable("ejercicio_no_esta_en_cierre", "Ese ejercicio ya no está en cierre.")):
            respuesta = self.client.post(self.url, {"confirmo": "1"}, follow=True)

        self.assertRedirects(respuesta, EJERCICIOS)
        self.assertEqual(self.mensajes(respuesta), ["Ese ejercicio ya no está en cierre."])

    def test_el_envio_exige_el_token_csrf(self):
        """El cierre es un formulario que se envía: sin el token CSRF se rechaza (el navegador real lo manda; el cliente de prueba común no lo exige)."""
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.contador)

        self.assertEqual(cliente.post(self.url, {"confirmo": "1"}).status_code, 403)
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, Estado.EN_CIERRE)

    def test_las_etiquetas_de_la_auditoria_del_cierre_estan_en_castellano(self):
        """Toque autorizado en `core/models.py`: «cerrado_por» y «contador» se muestran con su etiqueta en la Auditoría."""
        self.assertEqual(RegistroAuditoria.ETIQUETAS["cerrado_por"], "Cerrado por")
        self.assertEqual(RegistroAuditoria.ETIQUETAS["contador"], "Contador que lo cerró")


class PanelVistaTests(VistaBase):
    """Disparador de CON-03a: la alerta del «ejercicio en cierre» en el Panel del responsable contable (sin Contador, al Gerente)."""

    def setUp(self):
        super().setUp()
        self.cerrado.delete()
        self.abierto.delete()
        self.en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))
        self.cierre = reverse("contabilidad:cierre", args=[self.en_cierre.pk])

    def panel(self, cuenta):
        return _texto(self.get(cuenta, reverse("core:inicio")))

    def test_el_contador_ve_la_alerta_con_el_enlace_para_cerrar(self):
        """El Contador activo ve «El ejercicio 1 terminó el 31/12/2026» con «Cerrar ejercicio»."""
        contenido = self.panel(self.contador)

        self.assertIn("El ejercicio 1 terminó el 31/12/2026", contenido)
        self.assertIn(self.cierre, contenido)

    def test_el_gerente_ve_la_alerta_solo_si_no_hay_contador_activo(self):
        """Decisión del estudiante (24/11/2026): la alerta es del responsable contable; con un Contador activo el Gerente no la ve."""
        self.assertNotIn("terminó el 31/12/2026", self.panel(self.gerente))
        Contador.objects.update(is_active=False)
        self.assertIn("El ejercicio 1 terminó el 31/12/2026", self.panel(self.gerente))

    def test_sin_ejercicio_en_cierre_no_hay_alerta(self):
        """La alerta se calcula: al cerrarse el ejercicio desaparece."""
        EjercicioContable.objects.filter(pk=self.en_cierre.pk).update(estado_ejercicio=Estado.CERRADO)

        self.assertNotIn("terminó el 31/12/2026", self.panel(self.contador))

    def test_el_vendedor_y_el_agronomo_no_ven_la_alerta(self):
        """Los demás roles no ven nada de contabilidad en su Panel."""
        for clase, email in ((Vendedor, "v@infoponia.com"), (Agronomo, "a@infoponia.com")):
            self.assertNotIn("terminó el 31/12/2026", self.panel(crear_cuenta(clase, email=email)))
