# Recorrido de UI-06 (D-109 punto 9; UX-24 y UX-27) con el cliente de Django: Nueva siembra de punta a punta como lo haría una persona, por rol y por estado, y la concreción del Capataz.
# Lo que cada paso verifica: dónde queda la marca `data-llevar-vista` (que `infoponia.js` usa para llevar la vista y el foco), que los obligatorios independientes salen juntos y que lo que
# depende de otro valor (la distribución) espera. No reemplaza la «Verificación a mano»: el salto, el foco y el lector de pantalla son del navegador (docs/patrones/verificacion_a_mano.md).

from django.urls import reverse

from core.tests.obligatorios_ui06 import ObligatoriosJuntos, textos_de_error
from produccion.models import OrdenTrabajo, Siembra
from produccion.tests import test_produccion_vistas as t_prod

HX = {"HTTP_HX_REQUEST": "true"}
CANTIDAD = "La cantidad de plantines tiene que ser un número entero mayor que cero."
FECHA = "Indicá la fecha programada."


class RecorridoDeResumenYErroresTests(ObligatoriosJuntos, t_prod.Base):
    """PROD-PNF-SMB y PROD-CNC-SMB: del formulario vacío al resumen, la confirmación y la concreción."""

    def test_recorrido_de_nueva_siembra_a_la_concrecion_del_capataz(self):
        url = reverse("produccion:nueva_siembra")
        sector = self.e.sectores["germinacion"].pk
        valido = self.datos_de_siembra(cantidad="30", **{f"sector_{sector}": "30"})

        # 1. Rol: el Gerente no ve la pantalla (404) y el Capataz tampoco la abre (403): ninguno llega a ver una marca (D-30).
        self.entrar(self.gerente)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.entrar(self.e.capataz)
        self.assertEqual(self.client.get(url).status_code, 403)

        # 2. Estado inicial (el Agrónomo): la página abre sin resumen ni errores, y elegir el invernadero y la variedad (HTMX) solo redibuja campos: ninguna marca (regla de INV-02).
        self.entrar(self.e.agronomo)
        self.sin_marcas(self.client.get(url))
        self.sin_marcas(self.client.post(url, {"invernadero": self.e.invernadero.pk, "accion": "actualizar"}, **HX))
        redibujo = self.client.post(url, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "accion": "actualizar", "cantidad": "", "fecha_programada": ""}, **HX)
        self.sin_errores(redibujo)
        self.assertContains(redibujo, 'name="cantidad"')

        # 3. UX-27: «Ver resumen» con Plantines y Fecha vacíos marca los dos a la vez, con el texto del servicio; UX-24: la vista va al primero (una sola marca).
        vacio = self.client.post(url, {**valido, "cantidad": "", "fecha_programada": "", "accion": "calcular"})
        textos = textos_de_error(vacio)
        self.assertEqual((textos[0], textos[1]), (CANTIDAD, FECHA))
        self.una_marca(vacio)
        self.assertEqual(self.texto_marcado(vacio), CANTIDAD)

        # 4. Con la cantidad ya escrita solo queda la fecha: es el único error y es el que lleva la vista.
        solo_fecha = self.client.post(url, {**valido, "fecha_programada": "", "accion": "calcular"})
        self.assertEqual(textos_de_error(solo_fecha), [FECHA])
        self.assertEqual(self.texto_marcado(solo_fecha), FECHA)

        # 5. Lo que depende de otro valor espera: con la cantidad válida y los sectores sin repartir, el único error es el de la distribución (el de hoy) y lleva la vista.
        mal_repartido = self.client.post(url, {**valido, f"sector_{sector}": "10", "accion": "calcular"})
        self.assertEqual(len(textos_de_error(mal_repartido)), 1)
        self.assertIn("La distribución tiene que sumar 30", self.texto_marcado(mal_repartido))

        # 6. Todo válido: «Ver resumen» no escribe, y la marca está en el resumen (no en un error). Nada quedó creado todavía.
        resumen = self.client.post(url, {**valido, "accion": "calcular"})
        self.assertEqual(textos_de_error(resumen), [])
        self.assertIn('aria-label="Resumen de la orden"', self.una_marca(resumen))
        self.assertEqual(Siembra.objects.count(), 0)

        # 7. «Confirmar planificación» con la firma de lo que se vio: la orden queda planificada y se vuelve a la lista, que no lleva ninguna marca.
        confirmada = self.client.post(url, {**valido, "accion": "confirmar", "firma": resumen.context["firma"]}, follow=True)
        self.assertRedirects(confirmada, reverse("produccion:ordenes"))
        self.assertEqual(Siembra.objects.count(), 1)
        self.sin_marcas(confirmada)

        # 8. El Capataz concreta desde su bandeja (pantalla para celular): la carga inicial no lleva marca; un error (más plantas que las planificadas) lleva la vista al error;
        #    el resumen lleva la vista al resumen.
        orden = OrdenTrabajo.objects.get()
        concretar = reverse("produccion:concretar", args=[orden.pk])
        self.entrar(self.e.capataz)
        self.sin_marcas(self.client.get(concretar))
        con_error = self.client.post(concretar, {f"sembrado_{sector}": "99", "accion": "calcular"})
        self.assertNotIn('role="region"', self.una_marca(con_error))
        con_resumen = self.client.post(concretar, {f"sembrado_{sector}": "30", "accion": "calcular"})
        self.assertIn('aria-label="Resumen de la concreción"', self.una_marca(con_resumen))
