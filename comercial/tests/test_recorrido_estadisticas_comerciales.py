# Recorrido de COM-08c (docs/patrones/verificacion_a_mano.md, D-96): las estadísticas comerciales de punta a punta con el cliente de Django, por rol y por estado. Arma a mano un mes con datos que se distinguen
# (una venta a tiempo y otra con retraso, una entrega reprogramada concretada en la fecha prometida, una resolución anulada, un cobro anulado que vuelve a ser deuda, otro mes, otro invernadero y otro Vendedor) y mira
# lo que ve cada rol: el Vendedor (solo lo suyo; el mes, otro mes, un rango, un rango de más de un año y el invernadero), el Gerente (todo y el filtro por Vendedor), el panel con y sin «Resultados del mes en curso» y
# los enlaces de cada indicador. No reemplaza la «Verificación a mano» del estudiante: lo que solo un navegador ve (CSRF, JavaScript) va ahí. Fuente: docs/casos_de_uso/comercial/estadisticas.md, «Hecho cuando» de COM-08c.

from datetime import timedelta
from decimal import Decimal
from html import unescape

from django.urls import reverse

from comercial.models import Entrega
from comercial.tests.fabricas import anulacion, anulacion_de_cobro, cobro, discrepancia_aceptada, segundo_invernadero
from comercial.tests.test_com_cns_est import HACE_UN_MES, HOY, PERIODO_ANTERIOR, BaseDeEstadisticas
from produccion.tests.fabricas import lote_maduro

D = Decimal


def texto(respuesta):
    return unescape(respuesta.content.decode())


class RecorridoDeEstadisticasComercialesTests(BaseDeEstadisticas):
    def ver(self, usuario, **get):
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("comercial:estadisticas"), get)
        self.assertEqual(respuesta.status_code, 200)
        return respuesta

    def armar(self):
        """Los datos del recorrido. Devuelve lo que los pasos necesitan."""
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        # Este mes, del Vendedor:
        self.venta(cantidad=10, precio="100.00", pactada=1)  # $ 1.000, Norte, a tiempo
        reprogramada = self.venta(cantidad=10, precio="100.00", pactada=0)  # prometida hoy y concretada hoy
        self.reprogramar(reprogramada, HOY - timedelta(days=1))  # reprogramada: la programada no es la prometida (con ella sería retraso)
        self.venta(cantidad=30, precio="100.00", pactada=-4, lote=lote_maduro(sur, 5000))  # $ 3.000, Sur, 4 días de retraso
        aceptada = discrepancia_aceptada(self.suministro(cantidad=10, precio="100.00"), monto="300.00", descontado="300.00", con_alerta=False)  # indemnizado $ 300
        anulada = discrepancia_aceptada(self.suministro(cantidad=10, precio="100.00"), monto="900.00", descontado="900.00", con_alerta=False)
        anulacion(anulada)  # una resolución anulada: no cuenta
        con_cobro_anulado = self.en_mora(5)  # venció hace 5 días; se la deja concretada hoy para que cuente en el mes sin depender del día del mes
        Entrega.objects.filter(pk=con_cobro_anulado.pk).update(fecha_resolucion_orden=HOY)
        anulacion_de_cobro(cobro([con_cobro_anulado]))  # un cobro anulado: vuelve a ser deuda en mora
        # Otro mes y otro Vendedor:
        self.venta(cantidad=20, precio="100.00", hace=HACE_UN_MES)  # $ 2.000, el mes anterior
        self.del_otro_vendedor(cantidad=50, precio="100.00")  # $ 5.000 de otro Vendedor
        return sur, aceptada

    def test_recorrido_del_vendedor_y_del_gerente(self):
        sur, _ = self.armar()
        vendedor, gerente = self.e.vendedor, self.gerente

        # 1. El Vendedor abre Estadísticas: el mes actual, solo sus contratos.
        r = self.ver(vendedor)
        datos = r.context["datos"]
        # ventas: 1.000 + 1.000 + 3.000 + 1.000 + 1.000 (los dos suministros) + 1.000 (la entrega en mora) = $ 8.000
        self.assertEqual(datos.ventas.total, D("8000.00"))
        self.assertEqual(datos.ventas.entregas, 6)
        # puntualidad: 6 concretadas; con retraso solo la de 4 días (la reprogramada es a tiempo)
        self.assertEqual((datos.puntualidad.a_tiempo, datos.puntualidad.con_retraso, datos.puntualidad.promedio_de_retraso), (5, 1, D(4)))
        self.assertEqual((datos.incumplimientos.cantidad, datos.incumplimientos.total), (1, D("300.00")))  # la anulada no cuenta
        self.assertEqual((datos.cobranza.en_mora_cantidad, datos.cobranza.en_mora_total), (1, D("1000.00")))  # el cobro anulado volvió a ser deuda
        html = texto(r)
        for esperado in ("$ 8.000,00", "6 entregas concretadas", "83 %", "1 con retraso", "$ 300,00", "1 solicitud aceptada", "$ 1.000,00"):
            self.assertIn(esperado, html)
        self.assertNotIn(self.otro_cliente.nombre_visible, html)  # nada del otro Vendedor
        self.assertNotIn('name="vendedor"', html)

        # 2. Otro mes: $ 2.000 y nada de lo de este mes.
        anterior = self.ver(vendedor, periodo=PERIODO_ANTERIOR).context["datos"]
        self.assertEqual((anterior.ventas.total, anterior.ventas.entregas), (D("2000.00"), 1))
        self.assertEqual(anterior.cobranza, datos.cobranza)  # la cobranza es la de hoy, con cualquier período

        # 3. Un rango que cruza los dos meses.
        desde = (HOY - timedelta(days=HACE_UN_MES + 1)).isoformat()
        cruzado = self.ver(vendedor, periodo="rango", desde=desde, hasta=HOY.isoformat()).context["datos"]
        self.assertEqual(cruzado.ventas.total, D("10000.00"))

        # 4. Un rango de más de un año da error y no muestra números.
        largo = texto(self.ver(vendedor, periodo="rango", desde=(HOY - timedelta(days=400)).isoformat(), hasta=HOY.isoformat()))
        self.assertIn("El período no puede ser mayor que un año.", largo)
        self.assertNotIn("$ 8.000,00", largo)

        # 5. Filtro por invernadero: solo lo que salió del Sur.
        del_sur = self.ver(vendedor, invernadero=sur.invernadero.pk).context["datos"]
        self.assertEqual((del_sur.ventas.total, del_sur.ventas.entregas), (D("3000.00"), 1))
        self.assertEqual(del_sur.puntualidad.con_retraso, 1)
        self.assertEqual(del_sur.cobranza.en_mora_total, D("0.00"))  # la mora es de Norte

        # 6. El Gerente ve todo y filtra por Vendedor.
        todo = self.ver(gerente).context["datos"]
        self.assertEqual(todo.ventas.total, D("13000.00"))
        self.assertIn('name="vendedor"', texto(self.ver(gerente)))
        del_otro = self.ver(gerente, vendedor=self.otro_vendedor.pk).context["datos"]
        self.assertEqual(del_otro.ventas.total, D("5000.00"))
        propio = self.ver(gerente, vendedor=self.e.vendedor.pk).context["datos"]
        self.assertEqual(propio.ventas.total, D("8000.00"))

        # 7. Los enlaces de cada indicador responden con su filtro puesto.
        enlaces = propio.enlaces
        for url in (enlaces.compra_ventas, enlaces.suministros, enlaces.entregas, enlaces.solicitudes, enlaces.cobranza, enlaces.faltantes):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(enlaces.solicitudes, f"{reverse('comercial:solicitudes')}?estado=aceptada&vendedor={self.e.vendedor.pk}")

        # 8. El panel: el Vendedor tiene «Resultados del mes en curso»; el Gerente, no.
        self.client.force_login(vendedor)
        panel = texto(self.client.get("/"))
        self.assertIn("(mes en curso)", panel)
        self.assertIn("$ 8.000,00", panel)
        self.assertIn(reverse("comercial:estadisticas"), panel)
        self.client.force_login(gerente)
        self.assertNotIn("(mes en curso)", texto(self.client.get("/")))

    def test_un_vendedor_sin_datos_ve_ceros_y_sin_errores(self):
        """Estado vacío: un Vendedor sin contratos abre la pantalla y el panel sin errores, con todo en cero."""
        self.venta()  # de otro Vendedor para el nuevo
        nuevo = self.otro_vendedor
        r = self.ver(nuevo)
        self.assertEqual(r.context["datos"].ventas.total, D("0.00"))
        self.assertIn("Sin ventas en el período.", texto(r))
        self.client.force_login(nuevo)
        self.assertEqual(self.client.get("/").status_code, 200)
