# Pruebas de las pantallas de `produccion` (PRD-01, paso 8): «Producción y órdenes» (lista y detalle), «Nueva siembra», la bandeja y «Concretar
# siembra» del Capataz, «Cancelar orden», la pestaña «Lotes activos» y la sección del Inicio del Capataz. Las vistas solo orquestan: las reglas de
# negocio ya se prueban en los servicios; acá, quién ve qué (D-30), los errores por campo, que el HTML se escapa, el resumen antes de escribir, que no
# hay consultas por fila y que todo funciona sin JavaScript (un POST común) y con HTMX (solo el bloque que cambia). Cliente de prueba de Django.

from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.models import Notificacion
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo
from produccion.models import Lote, OrdenTrabajo, ReservaInsumo, Siembra
from produccion.tests.fabricas import (
    insumo_adicional,
    invernadero_con_produccion,
    lote_activo,
    orden_de_siembra,
    orden_suelta,
    variedad_con_stock,
)

HX = {"HTTP_HX_REQUEST": "true"}


def hoy():
    return timezone.localdate()


class Base(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = invernadero_con_produccion()
        self.gerente = crear_gerente()

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def datos_de_siembra(self, **cambios):
        datos = {
            "invernadero": self.e.invernadero.pk,
            "variedad": self.e.variedad.pk,
            "cantidad": "30",
            "fecha_programada": (hoy() + timedelta(days=2)).isoformat(),
            "prioridad": "",
            "descripcion": "",
            f"sector_{self.e.sectores['germinacion'].pk}": "30",
        }
        datos.update(cambios)
        return datos


class PermisosPorRolTests(Base):
    """D-30: ningún botón lleva a un 403; el Gerente solo ve la lista y el detalle (en lo demás, 404, como «Cultivos»)."""

    def test_pre_la_lista_la_ven_el_agronomo_y_el_gerente_y_el_capataz_no(self):
        self.entrar(self.e.agronomo)
        self.assertEqual(self.client.get(reverse("produccion:ordenes")).status_code, 200)
        self.entrar(self.gerente)
        self.assertEqual(self.client.get(reverse("produccion:ordenes")).status_code, 200)
        self.entrar(self.e.capataz)
        self.assertEqual(self.client.get(reverse("produccion:ordenes")).status_code, 403)

    def test_pre_el_gerente_no_ve_nueva_siembra_ni_cancelar_y_obtiene_404(self):
        orden = orden_de_siembra(self.e, plantines=5)
        self.entrar(self.gerente)
        self.assertEqual(self.client.get(reverse("produccion:nueva_siembra")).status_code, 404)
        self.assertEqual(self.client.post(reverse("produccion:nueva_siembra"), {}).status_code, 404)
        self.assertEqual(self.client.get(reverse("produccion:cancelar", args=[orden.pk])).status_code, 404)

    def test_pre_la_bandeja_y_concretar_son_solo_del_capataz(self):
        orden = orden_de_siembra(self.e, plantines=5)
        for cuenta in (self.e.agronomo, self.gerente):
            self.entrar(cuenta)
            self.assertEqual(self.client.get(reverse("produccion:bandeja")).status_code, 403)
            self.assertEqual(self.client.get(reverse("produccion:concretar", args=[orden.pk])).status_code, 403)
        self.entrar(self.e.capataz)
        self.assertEqual(self.client.get(reverse("produccion:bandeja")).status_code, 200)
        self.assertEqual(self.client.get(reverse("produccion:concretar", args=[orden.pk])).status_code, 200)

    def test_pre_otro_capataz_u_otro_agronomo_no_ven_la_orden_ajena(self):
        """Una orden que la cuenta no ve da 404 en el detalle y 403 al concretarla o cancelarla (D-28)."""
        orden = orden_de_siembra(self.e, plantines=5)
        self.entrar(crear_capataz_activo("otro.capataz@infoponia.com"))
        self.assertEqual(self.client.get(reverse("produccion:orden", args=[orden.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("produccion:concretar", args=[orden.pk])).status_code, 403)
        self.entrar(crear_agronomo("ajeno@infoponia.com"))
        self.assertEqual(self.client.get(reverse("produccion:orden", args=[orden.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("produccion:cancelar", args=[orden.pk])).status_code, 403)

    def test_pre_el_detalle_muestra_solo_los_botones_que_la_cuenta_puede_usar(self):
        orden = orden_de_siembra(self.e, plantines=5)
        self.entrar(self.e.agronomo)
        html = self.client.get(reverse("produccion:orden", args=[orden.pk])).content.decode()
        self.assertIn("Cancelar orden", html)
        self.assertNotIn("Concretar siembra", html)
        self.entrar(self.gerente)
        html = self.client.get(reverse("produccion:orden", args=[orden.pk])).content.decode()
        self.assertNotIn("Cancelar orden", html)
        self.assertNotIn("Concretar siembra", html)
        self.entrar(self.e.capataz)
        html = self.client.get(reverse("produccion:orden", args=[orden.pk])).content.decode()
        self.assertIn("Concretar siembra", html)
        self.assertNotIn("Cancelar orden", html)


class ListaDeOrdenesTests(Base):
    def test_el_filtro_de_tipo_ofrece_solo_siembra_transicion_y_cosecha(self):
        """D-67 punto 1: el filtro «Tipo» ofrece los tres de producción, no `Tipo.choices`."""
        self.entrar(self.e.agronomo)
        html = self.client.get(reverse("produccion:ordenes")).content.decode()
        for texto in ("Siembra", "Transición de etapa", "Cosecha"):
            self.assertIn(f">{texto}</option>", html)
        for texto in ("Entrega", "Mantenimiento técnico"):
            self.assertNotIn(f">{texto}</option>", html)

    def test_una_entrega_suelta_no_aparece_en_la_lista_ni_en_cancelar_ni_en_la_bandeja(self):
        siembra = orden_de_siembra(self.e, plantines=5)
        entrega = orden_suelta(self.e.invernadero, "entrega")
        self.entrar(self.e.agronomo)
        html = self.client.get(reverse("produccion:ordenes")).content.decode()
        self.assertIn(siembra.codigo, html)
        self.assertNotIn(entrega.codigo, html)
        self.assertEqual(self.client.get(reverse("produccion:cancelar", args=[entrega.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("produccion:orden", args=[entrega.pk])).status_code, 404)
        self.entrar(self.e.capataz)
        self.assertNotIn(entrega.codigo, self.client.get(reverse("produccion:bandeja")).content.decode())

    def test_filtra_por_estado_y_con_htmx_devuelve_solo_la_tabla(self):
        pendiente = orden_de_siembra(self.e, plantines=5)
        cancelada = orden_de_siembra(self.e, plantines=5, sector="crecimiento", estado="cancelada")
        self.entrar(self.e.agronomo)
        completa = self.client.get(reverse("produccion:ordenes"), {"estado": "cancelada"}).content.decode()
        self.assertIn("<html", completa)
        self.assertIn(cancelada.codigo, completa)
        self.assertNotIn(pendiente.codigo, completa)
        parcial = self.client.get(reverse("produccion:ordenes"), {"estado": "a_realizar"}, **HX).content.decode()
        self.assertNotIn("<html", parcial)
        self.assertIn(pendiente.codigo, parcial)

    def test_el_html_escapa_los_nombres(self):
        """Todo lo que viene de la base se escapa: un invernadero y una variedad con HTML no se interpretan."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(nombre_invernadero="<script>alert(1)</script>")
        orden_de_siembra(self.e, plantines=5)
        self.entrar(self.gerente)
        html = self.client.get(reverse("produccion:ordenes")).content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_no_hace_consultas_por_fila(self):
        orden_de_siembra(self.e, plantines=1)
        self.entrar(self.e.agronomo)
        with CaptureQueriesContext(connection) as una:
            self.client.get(reverse("produccion:ordenes"))
        for sector in ("crecimiento", "floracion", "fructificacion", "maduracion"):
            orden_de_siembra(self.e, plantines=1, sector=sector)
        with CaptureQueriesContext(connection) as varias:
            self.client.get(reverse("produccion:ordenes"))
        self.assertEqual(len(una), len(varias))


class NuevaSiembraTests(Base):
    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)
        self.url = reverse("produccion:nueva_siembra")

    def test_abrirla_no_escribe_y_pide_primero_el_invernadero(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("Elegí primero el invernadero", html)
        self.assertNotIn('name="cantidad"', html)
        self.assertEqual(OrdenTrabajo.objects.count(), 0)

    def test_cambiar_el_invernadero_o_la_variedad_solo_redibuja_sin_validar(self):
        """.claude/rules/interfaz.md: un selector que redibuja campos dependientes lo hace sin validar; con HTMX devuelve solo el formulario."""
        parcial = self.client.post(self.url, {"invernadero": self.e.invernadero.pk, "accion": "actualizar", "cantidad": "abc"}, **HX).content.decode()
        self.assertNotIn("<html", parcial)
        self.assertNotIn('class="err"', parcial)
        completo = self.client.post(self.url, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "accion": "actualizar", "cantidad": "abc"}).content.decode()
        self.assertIn('name="cantidad"', completo)
        self.assertIn(f'name="sector_{self.e.sectores["germinacion"].pk}"', completo)
        self.assertNotIn('class="err"', completo)

    def test_los_selectores_cumplen_las_reglas_de_interfaz(self):
        """Sin refrescos al escribir (nada de `input delay`), `hx-swap="innerHTML show:none"` en el contenedor y respaldo sin JavaScript."""
        html = self.client.get(self.url, {"invernadero": self.e.invernadero.pk}).content.decode()
        self.assertNotIn("delay:", html)
        self.assertIn('hx-swap="innerHTML show:none"', html)
        self.assertIn('<noscript><button class="btn btn-ghost btn-sm" type="submit" name="accion" value="actualizar">Continuar</button></noscript>', html)
        self.assertEqual(html.count('hx-trigger="change"'), 2)  # solo invernadero y variedad

    def test_un_invernadero_sin_capataz_aparece_deshabilitado_con_su_motivo(self):
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(capataz=None)
        html = self.client.get(self.url).content.decode()
        self.assertIn("disabled>Invernadero Norte — No tiene un Capataz activo", html)

    def test_una_variedad_no_compatible_aparece_deshabilitada_y_dice_con_que_choca(self):
        lote = lote_activo(self.e, cantidad=5)
        variedad_con_stock(self.e, "Calida", temp_ambiente_min="30", temp_ambiente_max="35")
        html = self.client.get(self.url, {"invernadero": self.e.invernadero.pk}).content.decode()
        self.assertIn("no compatible: temperatura ambiente: choca con " + lote.codigo, html)
        self.assertRegex(html, r"disabled>Lechuga Calida")

    def test_ver_resumen_valida_y_muestra_el_resumen_sin_escribir(self):
        respuesta = self.client.post(self.url, {**self.datos_de_siembra(), "accion": "calcular"})
        html = respuesta.content.decode()
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Resumen de la orden", html)
        self.assertIn("Confirmar planificación", html)
        self.assertEqual((OrdenTrabajo.objects.count(), ReservaInsumo.objects.count(), Notificacion.objects.count()), (0, 0, 0))

    def test_ext_8b_la_semilla_sin_habilitar_enlaza_a_habilitarla_con_el_insumo_y_el_invernadero_elegidos(self):
        """PROD-PNF-SMB extensión 8b: el aviso enlaza a CMP-HAB-IIN con `?insumo=<semilla>&invernadero=<invernadero>` (no a la lista de
        existencias, donde la semilla no se encontraba), con y sin HTMX (respaldo sin JavaScript)."""
        nueva, _ = variedad_con_stock(self.e, "Nueva", habilitar=False)
        enlace = f"{reverse('inventario:habilitar')}?insumo={nueva.semilla.pk}&invernadero={self.e.invernadero.pk}"
        datos = {**self.datos_de_siembra(variedad=nueva.pk), "accion": "calcular"}
        for extra in ({}, HX):
            respuesta = self.client.post(self.url, datos, **extra)
            self.assertContains(respuesta, "no está habilitada en este invernadero")
            self.assertContains(respuesta, f'href="{enlace}"')
            self.assertContains(respuesta, "Habilitar la semilla")

    def test_confirmar_planifica_y_va_a_la_lista_con_un_aviso(self):
        calculo = self.client.post(self.url, {**self.datos_de_siembra(), "accion": "calcular"}).content.decode()
        firma = calculo.split('name="firma" value="')[1].split('"')[0]
        respuesta = self.client.post(self.url, {**self.datos_de_siembra(), "accion": "confirmar", "firma": firma}, follow=True)
        self.assertRedirects(respuesta, reverse("produccion:ordenes"))
        siembra = Siembra.objects.get()
        self.assertContains(respuesta, siembra.codigo)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.capataz).count(), 1)

    def test_confirmar_sin_ver_el_resumen_o_cambiando_un_dato_no_escribe_y_vuelve_a_mostrarlo(self):
        """Sin JavaScript se puede cambiar un dato después del resumen: no se confirma lo que no se vio."""
        respuesta = self.client.post(self.url, {**self.datos_de_siembra(), "accion": "confirmar", "firma": "vieja"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cambiaste un dato después de ver el resumen")
        self.assertEqual(OrdenTrabajo.objects.count(), 0)

    def test_los_errores_van_debajo_de_su_campo(self):
        ayer = (hoy() - timedelta(days=1)).isoformat()
        html = self.client.post(self.url, {**self.datos_de_siembra(fecha_programada=ayer), "accion": "calcular"}).content.decode()
        self.assertIn("La fecha programada no puede ser anterior a hoy.", html)
        self.assertEqual(OrdenTrabajo.objects.count(), 0)
        sin_semilla = self.client.post(self.url, {**self.datos_de_siembra(cantidad="5000", **{f"sector_{self.e.sectores['germinacion'].pk}": "5000"}), "accion": "calcular"}).content.decode()
        self.assertIn("stock libre", sin_semilla)

    def test_el_html_escapa_la_descripcion_y_los_nombres(self):
        type(self.e.variedad).objects.filter(pk=self.e.variedad.pk).update(nombre_variedad="<i>x</i>")
        html = self.client.post(self.url, {**self.datos_de_siembra(descripcion="<b>hola</b>"), "accion": "calcular"}).content.decode()
        self.assertNotIn("<b>hola</b>", html)
        self.assertIn("&lt;b&gt;hola&lt;/b&gt;", html)
        self.assertNotIn("<i>x</i>", html)

    def test_un_invernadero_inactivo_no_rompe_la_pantalla(self):
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(self.client.get(self.url, {"invernadero": self.e.invernadero.pk}).status_code, 200)

    def test_los_insumos_adicionales_se_ofrecen_y_se_reservan(self):
        fertilizante = insumo_adicional(self.e, "Fertilizante", stock=50)
        html = self.client.get(self.url, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk}).content.decode()
        self.assertIn(f'name="insumo_{fertilizante.pk}"', html)
        datos = self.datos_de_siembra(**{f"insumo_{fertilizante.pk}": "5,5"})
        firma = self.client.post(self.url, {**datos, "accion": "calcular"}).content.decode().split('name="firma" value="')[1].split('"')[0]
        self.client.post(self.url, {**datos, "accion": "confirmar", "firma": firma})
        self.assertEqual(Siembra.objects.get().reservas.count(), 2)


class BandejaYConcretarTests(Base):
    def setUp(self):
        super().setUp()
        self.orden = orden_de_siembra(self.e, plantines=40)
        self.entrar(self.e.capataz)
        self.url = reverse("produccion:concretar", args=[self.orden.pk])

    def test_la_bandeja_agrupa_y_lleva_a_concretar(self):
        vencida = orden_de_siembra(self.e, plantines=5, sector="crecimiento", dias=-2)
        html = self.client.get(reverse("produccion:bandeja")).content.decode()
        self.assertLess(html.index("Vencidas"), html.index("Para hoy"))
        self.assertIn(reverse("produccion:concretar", args=[vencida.pk]), html)

    def test_la_bandeja_no_hace_consultas_por_fila(self):
        with CaptureQueriesContext(connection) as una:
            self.client.get(reverse("produccion:bandeja"))
        for sector in ("crecimiento", "floracion", "fructificacion", "maduracion"):
            orden_de_siembra(self.e, plantines=1, sector=sector)
        with CaptureQueriesContext(connection) as varias:
            self.client.get(reverse("produccion:bandeja"))
        self.assertEqual(len(una), len(varias))

    def test_el_sistema_propone_lo_planificado_y_hoy(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn(f'value="{hoy():%Y-%m-%d}"', html)
        self.assertIn('placeholder="40"', html)
        self.assertNotIn("Confirmar concreción", html)

    def test_ver_resumen_no_escribe_y_confirmar_concreta_y_vuelve_a_la_bandeja(self):
        sector = self.e.sectores["germinacion"].pk
        datos = {"fecha_efectiva": hoy().isoformat(), f"sembrado_{sector}": "35", "motivo_diferencia": "Faltó turba"}
        calculo = self.client.post(self.url, {**datos, "accion": "calcular"})
        self.assertContains(calculo, "35 de 40 planificados")
        self.assertEqual(Lote.objects.count(), 0)
        firma = calculo.content.decode().split('name="firma" value="')[1].split('"')[0]
        respuesta = self.client.post(self.url, {**datos, "accion": "confirmar", "firma": firma}, follow=True)
        self.assertRedirects(respuesta, reverse("produccion:bandeja"))
        lote = Lote.objects.get()
        self.assertEqual(lote.cantidad_inicial, 35)
        self.assertContains(respuesta, lote.codigo)

    def test_los_errores_van_debajo_de_su_campo_y_no_se_escribe(self):
        sector = self.e.sectores["germinacion"].pk
        html = self.client.post(self.url, {f"sembrado_{sector}": "99", "accion": "calcular"}).content.decode()
        self.assertIn("sembraste de más", html)
        html = self.client.post(self.url, {"fecha_efectiva": (hoy() + timedelta(days=3)).isoformat(), "accion": "calcular"}).content.decode()
        self.assertIn("no puede ser posterior a hoy", html)
        self.assertEqual(Lote.objects.count(), 0)

    def test_una_orden_ya_cancelada_no_se_abre_e_informa_su_estado(self):
        cancelada = orden_de_siembra(self.e, plantines=5, sector="crecimiento", estado="cancelada")
        respuesta = self.client.get(reverse("produccion:concretar", args=[cancelada.pk]), follow=True)
        self.assertRedirects(respuesta, reverse("produccion:bandeja"))
        self.assertContains(respuesta, "cancelada")

    def test_el_html_escapa_el_motivo_y_los_insumos(self):
        html = self.client.post(self.url, {"motivo_diferencia": "<script>x</script>", f"sembrado_{self.e.sectores['germinacion'].pk}": "10", "accion": "calcular"}).content.decode()
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", html)

    def test_la_pantalla_es_de_marco_de_celular_y_no_valida_al_escribir(self):
        html = self.client.get(self.url).content.decode()
        formulario = html[html.index('<form method="post"'):html.index("</form>")]
        self.assertNotIn("hx-", formulario)  # nada se valida ni se recalcula mientras se escribe (el marco de la página tiene los suyos)
        self.assertIn('class="shell field"', html)


class CancelarOrdenVistaTests(Base):
    def setUp(self):
        super().setUp()
        self.orden = orden_de_siembra(self.e, plantines=20)
        self.entrar(self.e.agronomo)
        self.url = reverse("produccion:cancelar", args=[self.orden.pk])

    def test_muestra_lo_que_libera_y_pide_el_motivo(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("Lo que libera la cancelación", html)
        self.assertIn(self.e.semilla.nombre_insumo, html)
        self.assertIn('name="motivo"', html)

    def test_sin_motivo_muestra_el_error_debajo_del_campo_y_no_cancela(self):
        html = self.client.post(self.url, {"motivo": "   "}).content.decode()
        self.assertIn("Indicá el motivo de la cancelación.", html)
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.orden.pk).estado_orden, "a_realizar")

    def test_confirmar_cancela_avisa_y_vuelve_a_la_lista(self):
        respuesta = self.client.post(self.url, {"motivo": "<b>Cambio de planes</b>"}, follow=True)
        self.assertRedirects(respuesta, reverse("produccion:ordenes"))
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.orden.pk).estado_orden, "cancelada")
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.capataz).count(), 1)
        detalle = self.client.get(reverse("produccion:orden", args=[self.orden.pk])).content.decode()
        self.assertIn("&lt;b&gt;Cambio de planes&lt;/b&gt;", detalle)
        self.assertNotIn("<b>Cambio de planes</b>", detalle)

    def test_una_orden_ya_concretada_informa_el_estado_y_vuelve_a_la_lista(self):
        concretada = orden_de_siembra(self.e, plantines=5, sector="crecimiento", estado="concretada", con_reserva=False)
        respuesta = self.client.get(reverse("produccion:cancelar", args=[concretada.pk]), follow=True)
        self.assertRedirects(respuesta, reverse("produccion:ordenes"))
        self.assertContains(respuesta, "concretada")


class LotesActivosYSeccionDeInicioTests(Base):
    def test_la_pestana_lotes_activos_aparece_en_la_ficha_del_invernadero(self):
        lote = lote_activo(self.e, cantidad=10)
        self.entrar(self.e.agronomo)
        url = reverse("maestros:invernadero", args=[self.e.invernadero.pk])
        self.assertContains(self.client.get(url), "Lotes activos")
        self.assertContains(self.client.get(url, {"pestana": "lotes"}), lote.codigo)

    def test_la_seccion_de_inicio_del_capataz_muestra_su_bandeja(self):
        orden = orden_de_siembra(self.e, plantines=5)
        self.entrar(self.e.capataz)
        html = self.client.get(reverse("core:inicio")).content.decode()
        self.assertIn("Mis órdenes", html)
        self.assertIn(orden.codigo, html)
        self.assertIn(reverse("produccion:concretar", args=[orden.pk]), html)

    def test_el_gerente_y_el_agronomo_ven_la_pestana_de_ordenes_en_produccion(self):
        for cuenta in (self.e.agronomo, self.gerente):
            self.entrar(cuenta)
            self.assertContains(self.client.get(reverse("maestros:invernaderos")), reverse("produccion:ordenes"))
