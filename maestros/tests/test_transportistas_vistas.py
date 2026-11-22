# Pruebas de las pantallas de transportistas de la ficha del invernadero (MAE-05, paso 6; D-55; ``logistica``, ``ventanaAgregar`` y
# ``ventanaQuitar`` de docs/prototipos/produccion/logistica_transportista.html): la tarjeta «Logística» (regla 3 de PROD-CNS-INV),
# «Agregar transportista» y «Quitar» (reglas 5 y 8 a 10 de PROD-MOD-INV), con permisos (SEG-13, D-30), HTMX y respaldo sin
# JavaScript (cada ventana es una página), los avisos breves (D-29) y sin consultas por fila.
#
# Rutas: ``maestros:transportista_agregar`` (invernadero_id) y ``maestros:transportista_quitar`` (invernadero_id, transportista_id).

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.extensiones import Impedimento, Logistica
from maestros.models import Invernadero, TransportistaInvernadero
from maestros.tests.fabricas import (
    ConGeoref,
    asignar_transportista,
    con_extension,
    crear_agronomo,
    crear_invernadero,
    crear_transportista,
)

EN_RUTA = Impedimento("transportista_en_ruta", "Está en ruta.", "Podés hacerlo cuando finalice la ruta.")
CON_ENTREGAS = Impedimento("transportista_con_entregas", "Tiene 2 entregas a realizar.", "Reasignalas antes.")


class TransportistasVistasBase(ConGeoref, TestCase):
    """Un Gerente con sesión, dos invernaderos activos y tres transportistas activos sin invernadero."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.force_login(self.gerente)
        self.agronomo = crear_agronomo()
        self.norte = crear_invernadero("Norte", agronomo=self.agronomo)
        self.sur = crear_invernadero("Sur")
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        self.carla = crear_transportista("carla@infoponia.com", nombre="Carla", apellido="Sosa")
        self.ana = crear_transportista("ana@infoponia.com", nombre="Ana", apellido="Torres")

    def url_agregar(self, invernadero=None):
        return reverse("maestros:transportista_agregar", args=[(invernadero or self.norte).pk])

    def url_quitar(self, transportista, invernadero=None):
        return reverse("maestros:transportista_quitar", args=[(invernadero or self.norte).pk, transportista.pk])

    def ficha(self, invernadero=None):
        return reverse("maestros:invernadero", args=[(invernadero or self.norte).pk])

    def fila(self, transportista):
        return TransportistaInvernadero.objects.filter(transportista_id=transportista.pk).first()


class LogisticaTarjetaTests(TransportistasVistasBase):
    """La tarjeta «Logística» de la ficha (regla 3 de PROD-CNS-INV)."""

    def test_regla_3_sin_transportistas_muestra_el_texto_del_prototipo_y_el_boton(self):
        """PROD-CNS-INV regla 3 y ``logistica``: sin transportistas, el texto y, para el Gerente, «Agregar transportista»."""
        respuesta = self.client.get(self.ficha())
        self.assertContains(respuesta, "Logística")
        self.assertContains(respuesta, "El invernadero no tiene transportistas. Puede vender con retiro")
        self.assertContains(respuesta, "Agregalos con «Agregar transportista».")
        self.assertContains(respuesta, "Agregar transportista")

    def test_regla_3_lista_los_transportistas_con_su_nombre_y_la_marca_inactivo(self):
        """PROD-CNS-INV regla 3: cada transportista con su nombre y la marca «Inactivo» si su cuenta lo está."""
        asignar_transportista(self.diego, self.norte)
        asignar_transportista(crear_transportista("vieja@infoponia.com", nombre="Vera", apellido="Zapata", activo=False), self.norte)
        asignar_transportista(self.carla, self.sur)

        respuesta = self.client.get(self.ficha())

        self.assertContains(respuesta, "Diego Ferreyra")
        self.assertContains(respuesta, "Vera Zapata")
        self.assertContains(respuesta, '<span class="status-badge status-warn">Inactivo</span>', count=1)
        self.assertNotContains(respuesta, "Carla Sosa")  # trabaja para otro invernadero

    def test_ext_transportistas_sin_registrante_no_aparecen_las_columnas_de_comercial(self):
        """D-55 punto 5 y API «Transportistas»: sin registrante, solo el nombre y el estado de la cuenta."""
        asignar_transportista(self.diego, self.norte)
        with con_extension("_LOGISTICA"):
            respuesta = self.client.get(self.ficha())
        self.assertNotContains(respuesta, "Entregas a realizar")
        self.assertNotContains(respuesta, "Situación")
        self.assertNotContains(respuesta, "Sin vehículo")

    def test_ext_transportistas_con_registrante_aparecen_vehiculo_situacion_y_entregas(self):
        """D-55 punto 5: con registrante falso, el vehículo (o «Sin vehículo»), la situación y las entregas a realizar."""
        asignar_transportista(self.diego, self.norte)
        asignar_transportista(self.carla, self.norte)

        def logistica(transportistas):
            return {
                self.diego.pk: Logistica("Camioneta AE123CD · 800 kg", False, 0, None),
                self.carla.pk: Logistica(None, True, 3, None),
            }

        with con_extension("_LOGISTICA", logistica):
            respuesta = self.client.get(self.ficha())

        self.assertContains(respuesta, "Camioneta AE123CD · 800 kg")
        self.assertContains(respuesta, "Sin vehículo")
        self.assertContains(respuesta, "En ruta")
        self.assertContains(respuesta, "En el invernadero")
        self.assertContains(respuesta, "Entregas a realizar")

    def test_regla_3_el_agronomo_ve_la_tarjeta_sin_botones(self):
        """PROD-CNS-INV regla 3 y D-30: el Agrónomo a cargo ve la misma tarjeta, sin «Agregar transportista» ni «Quitar»."""
        asignar_transportista(self.diego, self.norte)
        self.client.force_login(self.agronomo)

        respuesta = self.client.get(self.ficha())

        self.assertContains(respuesta, "Diego Ferreyra")
        self.assertNotContains(respuesta, "Agregar transportista")
        self.assertNotContains(respuesta, "Quitar")
        self.assertNotContains(respuesta, self.url_agregar())
        self.assertNotContains(respuesta, self.url_quitar(self.diego))

    def test_regla_5_un_invernadero_inactivo_no_muestra_botones(self):
        """PROD-MOD-INV regla 5 y D-30: uno inactivo no se modifica; el Gerente ve la tarjeta pero sin botones."""
        asignar_transportista(self.diego, self.norte)
        Invernadero.objects.filter(pk=self.norte.pk).update(estado_invernadero="inactivo")

        respuesta = self.client.get(self.ficha())

        self.assertContains(respuesta, "Diego Ferreyra")
        self.assertNotContains(respuesta, "Agregar transportista")
        self.assertNotContains(respuesta, self.url_quitar(self.diego))

    def test_regla_3_el_gerente_ve_agregar_y_quitar_en_un_invernadero_activo(self):
        """PROD-MOD-INV regla 8 y D-30: el Gerente ve los enlaces, que apuntan a las ventanas."""
        asignar_transportista(self.diego, self.norte)
        respuesta = self.client.get(self.ficha())
        self.assertContains(respuesta, f'href="{self.url_agregar()}"')
        self.assertContains(respuesta, f'href="{self.url_quitar(self.diego)}"')

    def test_regla_3_la_ficha_no_hace_consultas_por_fila(self):
        """Interfaz (D-55, API «Transportistas»): con tres transportistas la ficha hace las mismas consultas que con ninguno,
        incluso con un registrante de logística (una sola llamada para toda la lista)."""

        def logistica(transportistas):
            return {t.pk: Logistica("Camioneta", False, 1, None) for t in transportistas}

        with con_extension("_LOGISTICA", logistica):
            self.client.get(self.ficha())  # calienta cachés (sesión, tipos de etapa, etc.)
            with CaptureQueriesContext(connection) as sin_transportistas:
                self.client.get(self.ficha())
            for transportista in (self.diego, self.carla, self.ana):
                asignar_transportista(transportista, self.norte)
            with self.assertNumQueries(len(sin_transportistas.captured_queries)):
                respuesta = self.client.get(self.ficha())
        self.assertContains(respuesta, "Ana Torres")


class AgregarTransportistaVistaTests(TransportistasVistasBase):
    """La ventana «Agregar transportista» y su POST."""

    def test_pre_a_el_agronomo_recibe_403_y_sin_sesion_va_al_inicio_de_sesion(self):
        """PROD-MOD-INV precondición a y SEG-13: solo el Gerente; el Agrónomo recibe 403."""
        self.client.force_login(self.agronomo)
        self.assertEqual(self.client.get(self.url_agregar()).status_code, 403)
        self.assertEqual(self.client.post(self.url_agregar(), {"transportista_id": self.diego.pk}).status_code, 403)
        self.assertIsNone(self.fila(self.diego))
        self.client.logout()
        self.assertEqual(self.client.get(self.url_agregar()).status_code, 302)

    def test_flujo_principal_sin_javascript_la_ventana_llega_en_la_ficha_y_no_cambia_nada(self):
        """Interfaz: sin HTMX, la ventana es una página (la ficha con la ventana abierta); abrirla no cambia nada. Ofrece a
        los tres activos con su invernadero actual."""
        asignar_transportista(self.carla, self.sur)

        respuesta = self.client.get(self.url_agregar())

        self.assertContains(respuesta, "Agregar transportista a Norte")
        self.assertContains(respuesta, "<h1>Norte</h1>")  # la ficha queda detrás
        self.assertContains(respuesta, "Sin invernadero", count=2)
        self.assertContains(respuesta, "Trabaja para Sur")
        self.assertContains(respuesta, "data-cerrar-ventana")
        self.assertEqual(TransportistaInvernadero.objects.count(), 1)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_flujo_principal_con_htmx_llega_solo_la_ventana(self):
        """Interfaz: un pedido de HTMX recibe solo la ventana, para insertarla sobre la ficha."""
        respuesta = self.client.get(self.url_agregar(), headers={"HX-Request": "true"})
        self.assertContains(respuesta, "Agregar transportista a Norte")
        self.assertNotContains(respuesta, "<h1>")

    def test_flujo_principal_agregar_a_uno_sin_invernadero_vuelve_a_la_ficha_con_el_aviso(self):
        """PROD-MOD-INV regla 8 y D-29: agrega, notifica, audita y vuelve a la ficha con «{Nombre} ahora trabaja para…»."""
        respuesta = self.client.post(self.url_agregar(), {"transportista_id": self.diego.pk}, follow=True)

        self.assertRedirects(respuesta, self.ficha())
        self.assertContains(respuesta, "Diego Ferreyra ahora trabaja para Norte.")
        self.assertEqual(self.fila(self.diego).invernadero_id, self.norte.pk)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.diego).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.count(), 1)

    def test_regla_8_un_traslado_sin_confirmar_vuelve_a_la_ventana_con_el_aviso_y_no_cambia_nada(self):
        """PROD-MOD-INV regla 8: la ventana avisa del traslado y ofrece «Confirmar traslado»; no cambia nada."""
        asignar_transportista(self.diego, self.sur)

        respuesta = self.client.post(self.url_agregar(), {"transportista_id": self.diego.pk})

        self.assertContains(respuesta, "Diego Ferreyra trabaja para Sur.")
        self.assertContains(respuesta, "pasa a Norte y deja de trabajar para Sur")
        self.assertContains(respuesta, "Confirmar traslado")
        self.assertContains(respuesta, 'name="traslado_confirmado"')
        self.assertEqual(self.fila(self.diego).invernadero_id, self.sur.pk)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_8_confirmar_el_traslado_cambia_de_invernadero_y_avisa(self):
        """PROD-MOD-INV regla 8 y D-29: confirmado, traslada y vuelve a la ficha con «{Nombre} pasó de {origen} a {destino}.»."""
        asignar_transportista(self.diego, self.sur)

        respuesta = self.client.post(
            self.url_agregar(), {"transportista_id": self.diego.pk, "traslado_confirmado": "1"}, follow=True
        )

        self.assertRedirects(respuesta, self.ficha())
        self.assertContains(respuesta, "Diego Ferreyra pasó de Sur a Norte.")
        self.assertEqual(self.fila(self.diego).invernadero_id, self.norte.pk)
        self.assertEqual(RegistroAuditoria.objects.count(), 2)

    def test_regla_9_un_traslado_con_impedimentos_los_lista_y_no_ofrece_confirmar(self):
        """PROD-MOD-INV reglas 9 y 10: la ventana lista todos los impedimentos y no ofrece confirmar; nada cambia."""
        asignar_transportista(self.diego, self.sur)
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", lambda t: [EN_RUTA], lambda t: [CON_ENTREGAS]):
            respuesta = self.client.post(
                self.url_agregar(), {"transportista_id": self.diego.pk, "traslado_confirmado": "1"}
            )

        self.assertContains(respuesta, "Está en ruta. Podés hacerlo cuando finalice la ruta.")
        self.assertContains(respuesta, "Tiene 2 entregas a realizar. Reasignalas antes.")
        self.assertNotContains(respuesta, "Confirmar traslado")
        self.assertEqual(self.fila(self.diego).invernadero_id, self.sur.pk)

    def test_regla_9_ver_sus_entregas_solo_si_comercial_dio_la_url(self):
        """API «Transportistas»: «Ver sus entregas» lleva a ``url_entregas`` y solo aparece si el registrante la dio."""
        asignar_transportista(self.diego, self.sur)
        datos = {"transportista_id": self.diego.pk, "traslado_confirmado": "1"}
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", lambda t: [CON_ENTREGAS]):
            sin_url = self.client.post(self.url_agregar(), datos)
            with con_extension(
                "_LOGISTICA", lambda ts: {t.pk: Logistica(None, False, 2, "/entregas/?transportista=1") for t in ts}
            ):
                con_url = self.client.post(self.url_agregar(), datos)

        self.assertNotContains(sin_url, "Ver sus entregas")
        self.assertContains(con_url, "Ver sus entregas")
        self.assertContains(con_url, 'href="/entregas/?transportista=1"')

    def test_regla_8_sin_elegir_a_nadie_la_ventana_vuelve_con_el_error(self):
        """Errores en la ventana: sin un candidato elegido, «Elegí un transportista.» y no cambia nada."""
        respuesta = self.client.post(self.url_agregar(), {})
        self.assertContains(respuesta, "Elegí un transportista.")
        self.assertFalse(TransportistaInvernadero.objects.exists())

    def test_regla_8_un_transportista_inactivo_vuelve_a_la_ventana_con_el_motivo(self):
        """Errores en la ventana: un rechazo del servicio (el elegido se dio de baja mientras tanto) vuelve con el motivo."""
        inactivo = crear_transportista("baja@infoponia.com", nombre="Baja", apellido="Reciente", activo=False)
        respuesta = self.client.post(self.url_agregar(), {"transportista_id": inactivo.pk})
        self.assertContains(respuesta, "Solo se agregan transportistas activos.")
        self.assertFalse(TransportistaInvernadero.objects.exists())

    def test_regla_5_un_invernadero_inactivo_vuelve_a_la_ficha_con_el_motivo(self):
        """PROD-MOD-INV regla 5 y D-30: la ventana de uno inactivo no se abre; vuelve a la ficha con el motivo."""
        Invernadero.objects.filter(pk=self.norte.pk).update(estado_invernadero="inactivo")
        respuesta = self.client.get(self.url_agregar(), follow=True)
        self.assertRedirects(respuesta, self.ficha())
        self.assertContains(respuesta, "El invernadero está inactivo: solo se puede reactivar.")

    def test_regla_8_sin_candidatos_la_ventana_lo_dice_y_solo_ofrece_cerrar(self):
        """Interfaz: sin transportistas activos para agregar, la ventana lo dice y no ofrece agregar."""
        for transportista in (self.diego, self.carla, self.ana):
            asignar_transportista(transportista, self.norte)
        respuesta = self.client.get(self.url_agregar())
        self.assertContains(respuesta, "No hay transportistas activos para agregar.")
        self.assertNotContains(respuesta, 'data-enviando="Agregando…"')

    def test_pre_a_un_invernadero_inexistente_da_404(self):
        """D-28: un id inexistente da 404."""
        self.assertEqual(
            self.client.get(reverse("maestros:transportista_agregar", args=[self.norte.pk + 1000])).status_code, 404
        )


class QuitarTransportistaVistaTests(TransportistasVistasBase):
    """La ventana «Quitar transportista» y su POST."""

    def setUp(self):
        super().setUp()
        asignar_transportista(self.diego, self.norte)

    def test_pre_a_el_agronomo_recibe_403(self):
        """PROD-MOD-INV precondición a y SEG-13: solo el Gerente."""
        self.client.force_login(self.agronomo)
        self.assertEqual(self.client.get(self.url_quitar(self.diego)).status_code, 403)
        self.assertEqual(self.client.post(self.url_quitar(self.diego)).status_code, 403)
        self.assertIsNotNone(self.fila(self.diego))

    def test_flujo_principal_la_ventana_pide_confirmar_y_no_cambia_nada(self):
        """PROD-MOD-INV, ``ventanaQuitar``: abrirla (GET) muestra la confirmación sobre la ficha, sin cambiar ni auditar nada."""
        respuesta = self.client.get(self.url_quitar(self.diego))
        self.assertContains(respuesta, "Quitar a Diego Ferreyra")
        self.assertContains(respuesta, "Deja de trabajar para Norte y queda sin invernadero")
        self.assertContains(respuesta, "<h1>Norte</h1>")
        self.assertIsNotNone(self.fila(self.diego))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_flujo_principal_con_htmx_llega_solo_la_ventana(self):
        """Interfaz: un pedido de HTMX recibe solo la ventana."""
        respuesta = self.client.get(self.url_quitar(self.diego), headers={"HX-Request": "true"})
        self.assertContains(respuesta, "Quitar a Diego Ferreyra")
        self.assertNotContains(respuesta, "<h1>")

    def test_flujo_principal_confirmar_quita_y_vuelve_a_la_ficha_con_el_aviso(self):
        """PROD-MOD-INV postcondición g y D-29: quita, notifica, audita y vuelve a la ficha con el aviso."""
        respuesta = self.client.post(self.url_quitar(self.diego), follow=True)

        self.assertRedirects(respuesta, self.ficha())
        self.assertContains(respuesta, "Diego Ferreyra ya no trabaja para Norte.")
        self.assertIsNone(self.fila(self.diego))
        self.assertEqual(Notificacion.objects.filter(destinatario=self.diego).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.count(), 1)

    def test_regla_9_con_impedimentos_la_ventana_los_lista_y_no_ofrece_quitar(self):
        """PROD-MOD-INV reglas 9 y 10: la ventana lista los impedimentos, con «Ver sus entregas» si hay URL, y no ofrece quitar."""
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", lambda t: [EN_RUTA], lambda t: [CON_ENTREGAS]), con_extension(
            "_LOGISTICA", lambda ts: {t.pk: Logistica(None, True, 2, "/entregas/?t=1") for t in ts}
        ):
            respuesta = self.client.get(self.url_quitar(self.diego))

        self.assertContains(respuesta, "Está en ruta. Podés hacerlo cuando finalice la ruta.")
        self.assertContains(respuesta, "Tiene 2 entregas a realizar. Reasignalas antes.")
        self.assertContains(respuesta, 'href="/entregas/?t=1"')
        self.assertNotContains(respuesta, 'data-enviando="Quitando…"')

    def test_regla_9_un_impedimento_que_aparece_antes_de_confirmar_vuelve_a_la_ventana(self):
        """PROD-MOD-INV reglas 9 y 10: si apareció un impedimento con la ventana abierta, el POST no quita y la ventana vuelve."""
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", lambda t: [EN_RUTA]):
            respuesta = self.client.post(self.url_quitar(self.diego))
        self.assertContains(respuesta, "Está en ruta.")
        self.assertIsNotNone(self.fila(self.diego))

    def test_regla_9_un_transportista_inactivo_se_puede_quitar(self):
        """Nota «Cómo se aplica» de PROD-MOD-INV: un inactivo vinculado se muestra con «Inactivo» y se puede quitar."""
        from core.models import Usuario

        Usuario.objects.filter(pk=self.diego.pk).update(is_active=False)
        respuesta = self.client.post(self.url_quitar(self.diego), follow=True)
        self.assertContains(respuesta, "Diego Ferreyra ya no trabaja para Norte.")
        self.assertIsNone(self.fila(self.diego))

    def test_regla_8_quien_no_trabaja_para_el_invernadero_vuelve_a_la_ficha_con_el_motivo(self):
        """D-30: ningún botón lleva a un error; si no pertenece, vuelve a la ficha con el motivo y no cambia nada."""
        respuesta = self.client.get(self.url_quitar(self.carla), follow=True)
        self.assertRedirects(respuesta, self.ficha())
        self.assertContains(respuesta, "Ese transportista no trabaja para este invernadero.")

    def test_regla_5_un_invernadero_inactivo_vuelve_a_la_ficha_con_el_motivo(self):
        """PROD-MOD-INV regla 5: no se quita en un invernadero inactivo."""
        Invernadero.objects.filter(pk=self.norte.pk).update(estado_invernadero="inactivo")
        respuesta = self.client.post(self.url_quitar(self.diego), follow=True)
        self.assertRedirects(respuesta, self.ficha())
        self.assertIsNotNone(self.fila(self.diego))

    def test_pre_a_ids_inexistentes_dan_404(self):
        """D-28: un invernadero o un transportista inexistente dan 404."""
        self.assertEqual(
            self.client.get(reverse("maestros:transportista_quitar", args=[self.norte.pk, self.diego.pk + 1000])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("maestros:transportista_quitar", args=[self.norte.pk + 1000, self.diego.pk])).status_code,
            404,
        )
