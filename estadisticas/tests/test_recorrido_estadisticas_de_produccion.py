# Recorrido de EST-01 (D-96, docs/patrones/verificacion_a_mano.md): una prueba larga con el cliente de Django que hace, como una persona, lo que
# hace la «Verificación a mano» de la tarea: el Agrónomo (solo sus invernaderos) y el Gerente (todos y por invernadero) abren «Estadísticas»,
# cambian el período (por defecto, anterior y a mano), prueban un rango de más de un año, miran un invernadero sin IoT y uno con IoT, prenden y
# apagan la comparación y usan el selector «Todas / Solo de producción»; el Capataz, el Técnico, el Vendedor y el Contador reciben 403.
# No reemplaza la verificación a mano: el cliente de Django no ve el JavaScript, el encabezado Origin ni el aspecto.

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.models import Contador
from core.tests.fabricas import crear_cuenta, crear_gerente
from estadisticas.tests.fabricas import HOY, aplicacion_de, consumo_de, dos_invernaderos, instante_utc, lote_sembrado, merma_de, orden, salida_por_cosecha
from iot.tests.fabricas import ConCatalogoIot, sistema
from maestros.tests.fabricas import crear_alerta, crear_tecnico, crear_vendedor
from produccion.models import OrdenTrabajo

URL = reverse("estadisticas:produccion")
T = OrdenTrabajo.Tipo


class RecorridoDeEstadisticasDeProduccionTests(ConCatalogoIot, TestCase):
    """El recorrido de la pantalla «Estadísticas» por rol y por estado (EST-CNS-PRD)."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        cls.gerente = crear_gerente()
        # Norte, mes actual (01/11 al 26/11): 100 plantas sembradas el 05/11, 5 perdidas por plaga, 40 cosechadas a $ 2,50 y dos consumos.
        lote = lote_sembrado(cls.n, 100, date(2026, 11, 5), variedad=None)
        merma_de(lote, 5, "plaga", date(2026, 11, 8))
        salida_por_cosecha(lote, 40, date(2026, 11, 20), "2.5000")
        consumo_de(cls.n.invernadero, cls.n.existencia_semilla, "200.00", "100.000", date(2026, 11, 5), siembra=lote.siembra)
        consumo_de(cls.n.invernadero, cls.n.existencia_semilla, "10.00", "5.000", date(2026, 11, 10), aplicacion=aplicacion_de(cls.n.invernadero, date(2026, 11, 10)))
        orden(cls.n.invernadero, T.ENTREGA, date(2026, 11, 15), resolucion=date(2026, 11, 16))  # una entrega vencida
        # Norte, período anterior (06/10 al 31/10): 60 plantas.
        lote_sembrado(cls.n, 60, date(2026, 10, 10))
        # Sur: 40 plantas sembradas el 06/11, sin IoT.
        lote_sembrado(cls.s, 40, date(2026, 11, 6))

    def setUp(self):
        parche = mock.patch("estadisticas.views.timezone.localdate", return_value=HOY)
        parche.start()
        self.addCleanup(parche.stop)

    def abrir(self, cuenta, **parametros):
        """Abre la pantalla como `cuenta` (una persona que escribe la URL o aprieta un botón del formulario)."""
        self.client.force_login(cuenta)
        return self.client.get(URL, parametros)

    def test_recorrido_por_rol_y_estado(self):
        """Todo el recorrido de EST-01, en el orden en que lo haría una persona."""
        # 1. El Agrónomo abre «Estadísticas»: el mes actual con la comparación prendida, solo con sus invernaderos.
        agronomo = self.abrir(self.n.agronomo)
        self.assertEqual(agronomo.status_code, 200)
        self.assertContains(agronomo, "01/11/2026 al 26/11/2026")
        self.assertContains(agronomo, "se compara con 06/10/2026 al 31/10/2026")
        self.assertNotContains(agronomo, "Invernadero Sur")
        a = agronomo.context["resultado"].actual
        self.assertEqual(a.sembradas_y_cosechadas.sembradas, 100)
        self.assertEqual(a.sembradas_y_cosechadas.cosechadas, 40)
        self.assertEqual(str(a.costo.costo_por_planta), "2.50")
        self.assertEqual(a.merma.perdidas, 5)
        self.assertEqual(str(a.merma.porcentaje), "3.1")  # 5 ÷ (60 al inicio + 100 sembradas) = 3,125 → 3,1 %
        self.assertContains(agronomo, "▲ 40 (66,7 %) frente al período anterior")  # sembradas: 100 contra 60
        self.assertEqual(a.consumo.monto_total, 210)
        self.assertNotContains(agronomo, "Alertas del IoT")  # el invernadero no tiene IoT

        # 2. Cambia a «Mes anterior» y a un rango a mano.
        anterior = self.abrir(self.n.agronomo, periodo="mes_anterior")
        self.assertContains(anterior, "01/10/2026 al 31/10/2026")
        self.assertEqual(anterior.context["resultado"].actual.sembradas_y_cosechadas.sembradas, 60)
        a_mano = self.abrir(self.n.agronomo, periodo="personalizado", desde="2026-11-01", hasta="2026-11-10")
        self.assertContains(a_mano, "01/11/2026 al 10/11/2026")
        self.assertEqual(a_mano.context["resultado"].actual.sembradas_y_cosechadas.cosechadas, 0)  # la cosecha fue el 20/11

        # 3. Un rango de más de un año: mensaje claro y ninguna tarjeta.
        largo = self.abrir(self.n.agronomo, periodo="personalizado", desde="2025-01-01", hasta="2026-11-26")
        self.assertContains(largo, "El período no puede ser mayor que un año.")
        self.assertNotContains(largo, "Plantas sembradas")

        # 4. Sin comparación y con ella.
        sin = self.abrir(self.n.agronomo, enviado="1", periodo="mes")
        self.assertNotContains(sin, "frente al período anterior")
        con = self.abrir(self.n.agronomo, enviado="1", periodo="mes", comparar="on")
        self.assertContains(con, "frente al período anterior")

        # 5. Selector «Todas / Solo de producción»: la entrega vencida solo se cuenta en «Todas».
        self.assertContains(self.abrir(self.n.agronomo, ordenes="todas"), "<td>Entrega</td>")
        self.assertNotContains(self.abrir(self.n.agronomo, ordenes="produccion"), "<td>Entrega</td>")

        # 6. El invernadero ajeno: aviso y ningún dato.
        ajeno = self.abrir(self.n.agronomo, invernadero=self.s.invernadero.pk)
        self.assertContains(ajeno, "No tenés acceso a ese invernadero.")

        # 7. El Gerente: todos (140 + 60 del período anterior no entran: 100 + 40), y por invernadero.
        gerente = self.abrir(self.gerente)
        self.assertEqual(gerente.context["resultado"].actual.sembradas_y_cosechadas.sembradas, 140)
        self.assertContains(gerente, "Invernadero Sur")
        sur = self.abrir(self.gerente, invernadero=self.s.invernadero.pk)
        self.assertEqual(sur.context["resultado"].actual.sembradas_y_cosechadas.sembradas, 40)
        self.assertEqual(sur.context["resultado"].actual.sembradas_y_cosechadas.cosechadas, 0)

        # 8. IoT: el Norte lo tiene desde ahora y registra alertas; el Sur, no. El bloque aparece solo donde corresponde.
        sistema(self.n.invernadero)
        crear_alerta(self.n.invernadero, "iot_fuera_de_umbral", fecha_hora_alerta=instante_utc(2026, 11, 12, 15))
        crear_alerta(self.n.invernadero, "iot_fuera_de_umbral", fecha_hora_alerta=instante_utc(2026, 11, 13, 15))
        con_iot = self.abrir(self.gerente, invernadero=self.n.invernadero.pk)
        self.assertContains(con_iot, "Alertas del IoT")
        self.assertContains(con_iot, "2 alertas")
        self.assertNotContains(self.abrir(self.gerente, invernadero=self.s.invernadero.pk), "Alertas del IoT")

        # 9. Capataz, Técnico, Vendedor y Contador: 403.
        for cuenta in (self.n.capataz, crear_tecnico(), crear_vendedor(), crear_cuenta(Contador, email="contador@infoponia.com")):
            self.assertEqual(self.abrir(cuenta).status_code, 403)
