# Pruebas de la pantalla «Estadísticas» consolidadas (EST-02, paso 4): acceso solo del Gerente, las cuatro pestañas, el período por GET, la comparación, los
# enlaces y el menú. Fuente: EST-CNS-CNS reglas 1, 2, 4 y 7 (docs/casos_de_uso/estadisticas/estadisticas.md) y D-93 puntos 2 y 6. El día de «hoy» se fija en `HOY`
# (26/11/2026) con un `patch` de `timezone.localdate`, así las pruebas no dependen del día en que corren.

from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import EjercicioContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin, asiento_de_prueba, ejercicio
from core.menu import menu_de
from core.models import Contador, RegistroAuditoria, Usuario
from core.tests.fabricas import crear_cuenta, crear_gerente
from estadisticas.tests.fabricas import HOY, dos_invernaderos, lote_sembrado, merma_de_camara, salida_por_cosecha
from iot.tests.fabricas import ConCatalogoIot
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_tecnico, crear_vendedor

URL = reverse("estadisticas:consolidadas")
Rol = Usuario.Rol
D = Decimal


class EstCnsCnsVistaTests(PlanDeCuentasMixin, ConCatalogoIot, TestCase):
    """La pantalla consolidada: solo el Gerente la ve. Los datos: dos invernaderos con producción, un ejercicio abierto y asientos de ventas y gastos."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        cls.gerente = crear_gerente()
        lote = lote_sembrado(cls.n, 100, date(2026, 11, 5))
        salida_por_cosecha(lote, 30, date(2026, 11, 10), "2.0000")
        merma_de_camara(lote, 4, "dano_en_camara", date(2026, 11, 12))
        lote_sembrado(cls.s, 40, date(2026, 11, 6), variedad=cls.s.variedad)
        cls.ejercicio = ejercicio(EjercicioContable.Estado.ABIERTO, date(2026, 1, 1))
        asiento_de_prueba(cls.ejercicio, date(2026, 11, 10), [(cuentas.CAJA, DEBE, D("1000.00")), (cuentas.VENTAS, HABER, D("1000.00"))])
        asiento_de_prueba(cls.ejercicio, date(2026, 11, 12), [(cuentas.GASTOS_DE_PRODUCCION, DEBE, D("300.00")), (cuentas.CAJA, HABER, D("300.00"))])
        asiento_de_prueba(cls.ejercicio, date(2026, 10, 12), [(cuentas.GASTOS_DE_PRODUCCION, DEBE, D("50.00")), (cuentas.CAJA, HABER, D("50.00"))])  # del período anterior

    def setUp(self):
        parche = mock.patch("estadisticas.views.timezone.localdate", return_value=HOY)
        parche.start()
        self.addCleanup(parche.stop)

    def ver(self, cuenta=None, **parametros):
        """Abre la pantalla como `cuenta` (por defecto, el Gerente) con los parámetros GET."""
        self.client.force_login(cuenta or self.gerente)
        return self.client.get(URL, parametros)

    # ---- Acceso (regla 1) ----

    def test_regla_1_solo_el_gerente_entra_los_demas_roles_reciben_403(self):
        """EST-CNS-CNS regla 1: solo el Gerente. El Contador tiene el libro; el Vendedor, sus estadísticas comerciales; el Agrónomo, la pantalla de producción."""
        cuentas_ = {
            "agronomo": self.n.agronomo,
            "capataz": self.n.capataz,
            "tecnico": crear_tecnico(),
            "vendedor": crear_vendedor(),
            "contador": crear_cuenta(Contador, email="contador@infoponia.com"),
        }
        for nombre, cuenta in cuentas_.items():
            with self.subTest(rol=nombre):
                self.assertEqual(self.ver(cuenta).status_code, 403)

    def test_regla_1_sin_sesion_pide_iniciar_sesion(self):
        """Toda pantalla exige sesión (D-25): sin cuenta, redirige al ingreso."""
        self.assertEqual(self.client.get(URL).status_code, 302)

    def test_regla_1_el_gerente_entra(self):
        """EST-CNS-CNS regla 1: el Gerente consulta las consolidadas."""
        self.assertEqual(self.ver().status_code, 200)

    def test_regla_7_menu_el_gerente_entra_por_las_consolidadas_y_el_agronomo_por_produccion(self):
        """EST-CNS-CNS regla 7 y H28: la entrada «Estadísticas» del Gerente lleva a las consolidadas; la del Agrónomo, a la de producción; los demás roles no la tienen."""
        esperado = {
            Rol.GERENTE: ("Estadísticas", "estadisticas:consolidadas", "chart"),
            Rol.AGRONOMO: ("Estadísticas", "estadisticas:produccion", "chart"),
        }
        for rol in (Rol.GERENTE, Rol.AGRONOMO, Rol.VENDEDOR, Rol.CONTADOR, Rol.CAPATAZ, Rol.TECNICO):
            with self.subTest(rol=rol):
                entradas = [e for e in menu_de(rol) if e[0] == "Estadísticas"]
                self.assertEqual(entradas, [esperado[rol]] if rol in esperado else [])

    def test_regla_7_la_consulta_no_audita_y_solo_se_consulta_con_get(self):
        """EST-CNS-CNS regla 7 y SEG-14: una consulta no registra auditoría ni recibe envíos POST."""
        antes = RegistroAuditoria.objects.count()
        self.ver(pestana="resultados", periodo="tres_meses")
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        self.assertEqual(self.client.post(URL, {}).status_code, 405)

    # ---- Pestañas ----

    def test_pestanas_la_pantalla_ofrece_resumen_produccion_compras_y_resultados(self):
        """Prototipo `statsTabs` (sin «Comercial», que llega con EST-03): cuatro pestañas; abre en «Resumen» y una pestaña desconocida también."""
        respuesta = self.ver()
        self.assertEqual(respuesta.context["pestana"], "resumen")
        for codigo in ("resumen", "produccion", "compras", "resultados"):
            self.assertContains(respuesta, f'name="pestana" value="{codigo}"')
        self.assertNotContains(respuesta, 'value="comercial"')
        self.assertEqual(self.ver(pestana="inventada").context["pestana"], "resumen")

    def test_pestana_resumen_muestra_ventas_compras_resultado_y_plantas_cosechadas(self):
        """Prototipo `stRes`: ventas $ 1.000,00 (4.1.01), compras recibidas $ 0,00, resultado $ 700,00 (1.000 − 300) y 30 plantas cosechadas."""
        respuesta = self.ver(pestana="resumen")
        a = respuesta.context["resultado"].actual
        self.assertEqual((a.libro.ventas, a.libro.resultado, a.compras.total, a.por_invernadero.total.cosechadas), (D("1000.00"), D("700.00"), D("0.00"), 30))
        self.assertContains(respuesta, "$ 1.000,00")
        self.assertContains(respuesta, "$ 700,00")

    def test_pestana_resumen_cada_cifra_lleva_a_su_pestana_con_el_mismo_filtro(self):
        """EST-CNS-CNS regla 4: desde cada indicador se llega a la consulta que lo detalla con el mismo filtro."""
        respuesta = self.ver(pestana="resumen", periodo="mes_anterior")
        for destino in ("resultados", "compras", "produccion"):
            self.assertContains(respuesta, f"{URL}?enviado=1&amp;periodo=mes_anterior&amp;ordenes=todas&amp;comparar=on&amp;pestana={destino}")

    def test_pestana_produccion_compara_invernaderos_y_muestra_la_merma_en_camara_aparte(self):
        """D-93 punto 4.7: una fila por invernadero y el total, y la tarjeta «Merma en cámara» con sus 4 plantas y el valor «—» (todavía sin asiento)."""
        respuesta = self.ver(pestana="produccion")
        for texto in ("Invernadero Norte", "Invernadero Sur", "Total de la organización", "Merma en cámara", "Daño en cámara", "Todavía no hay asientos para estas mermas."):
            self.assertContains(respuesta, texto)
        self.assertEqual(respuesta.context["resultado"].actual.merma_en_camara.valor, None)
        self.assertEqual(respuesta.context["resultado"].actual.por_invernadero.total.sembradas, 140)

    def test_pestana_produccion_cada_invernadero_lleva_a_la_pantalla_de_produccion_con_el_mismo_periodo(self):
        """EST-CNS-CNS regla 4 y EST-CNS-PRD regla 5: la fila enlaza a EST-01 con ese invernadero y el período (personalizado)."""
        respuesta = self.ver(pestana="produccion")
        url = reverse("estadisticas:produccion") + f"?enviado=1&amp;periodo=personalizado&amp;desde=2026-11-01&amp;hasta=2026-11-26&amp;invernadero={self.n.invernadero.pk}"
        self.assertContains(respuesta, f'href="{url}"')

    def test_pestana_produccion_el_selector_de_ordenes_se_conserva(self):
        """D-93 punto 3.3: «Solo de producción» llega al servicio y la pestaña lo muestra elegido."""
        respuesta = self.ver(pestana="produccion", ordenes="produccion")
        self.assertContains(respuesta, 'name="ordenes" value="produccion" aria-pressed="true"')

    def test_pestana_produccion_un_invernadero_dado_de_baja_con_actividad_tiene_su_fila(self):
        """Decisión del estudiante (26/11/2026): el Sur se da de baja; su actividad va en «Dados de baja» y el total no cambia."""
        antes = self.ver(pestana="produccion").context["resultado"].actual.por_invernadero.total
        Invernadero.objects.filter(pk=self.s.invernadero.pk).update(estado_invernadero="inactivo")
        respuesta = self.ver(pestana="produccion")
        self.assertContains(respuesta, "Dados de baja")
        self.assertNotContains(respuesta, "Invernadero Sur")
        self.assertEqual(respuesta.context["resultado"].actual.por_invernadero.total, antes)

    def test_pestana_compras_sin_recepciones_dice_que_no_se_recibio_mercaderia(self):
        """Prototipo `stCmp` (estado vacío): «No se recibió mercadería en este período»."""
        self.assertContains(self.ver(pestana="compras"), "No se recibió mercadería en este período")

    def test_pestana_resultados_muestra_ingresos_egresos_y_el_resultado_por_cuenta(self):
        """Prototipo `stRtd`: ingresos $ 1.000,00, egresos $ 300,00 y resultado $ 700,00; Ventas con el 100 % de los ingresos y Gastos de Producción con el 100 % de los egresos."""
        respuesta = self.ver(pestana="resultados")
        for texto in ("De dónde vienen los ingresos", "En qué se gasta", "Ventas", "Gastos de Producción", "$ 1.000,00", "$ 300,00", "$ 700,00"):
            self.assertContains(respuesta, texto)

    def test_pestana_resultados_cada_cuenta_lleva_al_libro_con_el_periodo(self):
        """EST-CNS-CNS regla 4: la cuenta enlaza a los asientos del libro de ese ejercicio, con la cuenta y las fechas del período."""
        respuesta = self.ver(pestana="resultados")
        libro = reverse("contabilidad:libro")
        self.assertContains(respuesta, f"{libro}?ejercicio={self.ejercicio.pk}&amp;desde=2026-11-01&amp;hasta=2026-11-26&amp;cuenta=4.1.01")

    def test_pestana_resultados_un_periodo_que_cruza_dos_ejercicios_suma_los_dos_y_ofrece_un_enlace_por_ejercicio(self):
        """EST-CNS-CNS «Decididas» 1: del 01/11 al 26/11 el período cruza dos ejercicios (el 1 cierra el 15/11 y el 2 abre el 16/11): las cifras suman los dos y el libro se ofrece por ejercicio."""
        EjercicioContable.objects.filter(pk=self.ejercicio.pk).update(
            estado_ejercicio=EjercicioContable.Estado.CERRADO, fecha_cierre_ejercicio=date(2026, 11, 15)
        )
        nuevo = ejercicio(EjercicioContable.Estado.ABIERTO, date(2026, 11, 16))
        asiento_de_prueba(nuevo, date(2026, 11, 20), [(cuentas.CAJA, DEBE, D("500.00")), (cuentas.VENTAS, HABER, D("500.00"))])
        respuesta = self.ver(pestana="resultados")
        self.assertEqual(respuesta.context["resultado"].actual.libro.ventas, D("1500.00"))
        self.assertContains(respuesta, "El período cruza dos ejercicios")
        self.assertEqual([t for t, _ in respuesta.context["enlaces_al_libro"]], ["Ejercicio 1", "Ejercicio 2"])

    def test_pestana_resultados_sin_movimientos_muestra_el_estado_vacio(self):
        """Prototipo `stRtd` (estado vacío): «No hay movimientos en este período»."""
        self.assertContains(self.ver(pestana="resultados", periodo="personalizado", desde="2026-03-01", hasta="2026-03-31"), "No hay movimientos en este período")

    # ---- Período y comparación (regla 2) ----

    def test_regla_2_por_defecto_es_este_mes_hasta_hoy_y_compara_con_el_anterior(self):
        """EST-CNS-CNS regla 2 y D-93 punto 2: del 01/11 al 26/11 (hoy), comparado con el 06/10 al 31/10; la comparación viene prendida la primera vez."""
        respuesta = self.ver()
        resultado = respuesta.context["resultado"]
        self.assertEqual((resultado.periodo.desde, resultado.periodo.hasta), (date(2026, 11, 1), date(2026, 11, 26)))
        self.assertEqual((resultado.anterior.desde, resultado.anterior.hasta), (date(2026, 10, 6), date(2026, 10, 31)))
        self.assertContains(respuesta, "se compara con 06/10/2026 al 31/10/2026")
        self.assertTrue(resultado.comparaciones)

    def test_regla_2_la_comparacion_apagada_no_calcula_el_periodo_anterior(self):
        """EST-CNS-CNS regla 2: sin «Comparar con el período anterior» solo se arma el período actual."""
        resultado = self.ver(enviado=1, pestana="resultados").context["resultado"]
        self.assertEqual((resultado.previo, resultado.comparaciones), (None, {}))

    def test_regla_2_los_egresos_se_comparan_con_el_periodo_anterior(self):
        """D-93 punto 2: egresos $ 300,00 contra $ 50,00 del período anterior: sube $ 250,00 (500,0 %), y subir un egreso es malo (clase «dn»)."""
        deltas = self.ver(pestana="resultados").context["deltas"]
        self.assertEqual(deltas["egresos"]["clase"], "dn")
        self.assertIn("250,00", deltas["egresos"]["texto"])

    def test_regla_2_un_periodo_personalizado_a_mano(self):
        """D-93 punto 2: el Gerente elige «Personalizado» con sus fechas: del 10/11 al 12/11 las ventas son las del asiento del 10/11."""
        resultado = self.ver(periodo="personalizado", desde="2026-11-10", hasta="2026-11-12", pestana="resultados").context["resultado"]
        self.assertEqual((resultado.actual.libro.ventas, resultado.actual.libro.egresos), (D("1000.00"), D("300.00")))

    def test_regla_2_un_periodo_invalido_muestra_el_error_y_ningun_dato(self):
        """EST-CNS-PRD regla 2: «desde» posterior a «hasta», un fin posterior a hoy o más de un año muestran el mensaje y el formulario, sin datos."""
        casos = {
            ("2026-11-20", "2026-11-10"): "La fecha “desde” no puede ser posterior a “hasta”.",
            ("2026-11-01", "2026-12-31"): "El período no puede terminar después de hoy.",
            ("2025-01-01", "2026-11-26"): "El período no puede ser mayor que un año.",
        }
        for (desde, hasta), mensaje in casos.items():
            with self.subTest(desde=desde, hasta=hasta):
                respuesta = self.ver(periodo="personalizado", desde=desde, hasta=hasta)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, mensaje)
                self.assertIsNone(respuesta.context["resultado"])

    def test_regla_2_el_filtro_viaja_entre_pestanas(self):
        """El formulario es un GET: el período y la comparación elegidos quedan escondidos y se envían con la pestaña que se aprieta."""
        respuesta = self.ver(pestana="compras", periodo="tres_meses", enviado=1, comparar="on")
        self.assertContains(respuesta, '<input type="hidden" name="periodo" value="tres_meses">')
        self.assertContains(respuesta, '<input type="hidden" name="pestana" value="compras">')
        self.assertContains(respuesta, "checked")

    # ---- Desde EST-01 ----

    def test_la_pantalla_de_produccion_ofrece_volver_a_las_consolidadas_solo_al_gerente(self):
        """El Gerente llega a la pantalla de producción (EST-01) desde la pestaña «Producción» y puede volver; el Agrónomo no tiene consolidadas (D-30: sin enlaces que lleven a un 403)."""
        produccion = reverse("estadisticas:produccion")
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(produccion), "Estadísticas consolidadas")
        self.client.force_login(self.n.agronomo)
        self.assertNotContains(self.client.get(produccion), "Estadísticas consolidadas")
