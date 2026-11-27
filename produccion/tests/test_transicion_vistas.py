# Pruebas de las pantallas de transición de `produccion` (PRD-02, paso 7): «Nueva transición» (Agrónomo), «Concretar transición» (Capataz, para
# celular), la rama de transición del detalle, la lista, la bandeja y «Cancelar orden». Las vistas solo orquestan: las reglas de negocio ya
# se prueban en los servicios; acá, quién ve qué (D-30), los errores por campo, que el HTML se escapa, que el formulario está deshabilitado
# con su motivo cuando no hay lotes trasladables, que la causa de la merma aparece solo cuando faltan plantas, que no hay consultas por fila y
# que todo funciona sin JavaScript (un POST común) y con HTMX (solo el bloque que cambia, sin validar). Cliente de prueba de Django.

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.models import Notificacion
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Invernadero, SectorProduccion
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo
from produccion.models import Lote, TransicionEtapa
from produccion.tests.fabricas import invernadero_con_produccion, lote_con_ciclo, orden_de_transicion
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HX = {"HTTP_HX_REQUEST": "true"}


def hoy():
    return timezone.localdate()


class Base(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):  # CON-04a: estos servicios asientan
    def setUp(self):
        self.e = invernadero_con_produccion()
        self.gerente = crear_gerente()
        self.lote = lote_con_ciclo(self.e, cantidad=50, costo="100.00")
        self.destino = self.e.sectores["floracion"]

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def nueva(self, **cambios):
        datos = {
            "lote": self.lote.pk,
            "fecha_programada": (hoy() + timedelta(days=10)).isoformat(),
            "cantidad_vista": "50",
            "etapa_vista": self.lote.etapa_id,
            "prioridad": "",
            "descripcion": "",
            f"sector_{self.destino.pk}": "50",
        }
        datos.update(cambios)
        return datos


class PermisosPorRolTests(Base):
    """D-30: ningún botón lleva a un 403; el Gerente no ve estas pantallas (404); el Capataz concreta solo lo suyo."""

    def test_pre_nueva_transicion_es_del_agronomo_el_gerente_obtiene_404_y_el_capataz_403(self):
        url = reverse("produccion:nueva_transicion")
        self.entrar(self.e.agronomo)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.entrar(self.gerente)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {}).status_code, 404)
        self.entrar(self.e.capataz)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_pre_concretar_una_transicion_es_solo_del_capataz_asignado(self):
        orden = orden_de_transicion(self.e, self.lote)
        url = reverse("produccion:concretar", args=[orden.pk])
        for cuenta in (self.e.agronomo, self.gerente):
            self.entrar(cuenta)
            self.assertEqual(self.client.get(url).status_code, 403)
        self.entrar(crear_capataz_activo("otro.capataz@infoponia.com"))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.entrar(self.e.capataz)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_pre_el_detalle_y_la_lista_muestran_solo_los_botones_que_la_cuenta_puede_usar(self):
        orden = orden_de_transicion(self.e, self.lote)
        url = reverse("produccion:orden", args=[orden.pk])
        self.entrar(self.e.agronomo)
        html = self.client.get(url).content.decode()
        self.assertIn("Cancelar orden", html)
        self.assertNotIn("Concretar transición", html)
        self.assertIn("Nueva transición", self.client.get(reverse("produccion:ordenes")).content.decode())
        self.entrar(self.gerente)
        html = self.client.get(url).content.decode()
        self.assertNotIn("Cancelar orden", html)
        self.assertNotIn("Concretar transición", html)
        self.assertNotIn("Nueva transición", self.client.get(reverse("produccion:ordenes")).content.decode())
        self.entrar(self.e.capataz)
        html = self.client.get(url).content.decode()
        self.assertIn("Concretar transición", html)
        self.assertNotIn("Cancelar orden", html)


class NuevaTransicionTests(Base):
    url = property(lambda self: reverse("produccion:nueva_transicion"))

    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)

    def test_paso_2_la_pagina_lista_los_lotes_y_no_ofrece_nada_hasta_elegir_uno(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn(self.lote.codigo, html)
        self.assertIn("Crecimiento", html)
        self.assertIn("Floración", html)
        self.assertNotIn('name="cantidad_vista"', html)  # sin lote elegido no hay fecha ni distribución
        self.assertIn("disabled", html.split("Ver resumen")[0][-120:])  # el botón de resumen está deshabilitado

    def test_paso_4_al_elegir_el_lote_se_ofrecen_la_fecha_propuesta_y_los_sectores(self):
        html = self.client.get(self.url, {"lote": self.lote.pk}).content.decode()
        self.assertIn(f'name="sector_{self.destino.pk}"', html)
        self.assertIn((hoy() + timedelta(days=10)).isoformat(), html)
        self.assertIn('name="cantidad_vista" value="50"', html)

    def test_con_htmx_elegir_el_lote_solo_redibuja_el_bloque_y_no_valida(self):
        """Elegir el lote (HTMX) trae el bloque del formulario, sin la página completa y sin errores ni resumen (.claude/rules/interfaz.md)."""
        respuesta = self.client.post(self.url, {"accion": "actualizar", "lote": self.lote.pk, "cantidad_vista": "", "fecha_programada": ""}, **HX)
        html = respuesta.content.decode()
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("<html", html)
        self.assertIn(f'name="sector_{self.destino.pk}"', html)
        self.assertNotIn('class="err"', html)
        self.assertNotIn("Confirmar transición", html)
        self.assertIn('hx-trigger="change"', html)

    def test_sin_javascript_el_flujo_completo_funciona_con_posts_comunes(self):
        """Continuar → Ver resumen → Confirmar, todo con POST común (sin HTMX): crea la orden y avisa al Capataz."""
        resumen = self.client.post(self.url, self.nueva(accion="calcular"))
        html = resumen.content.decode()
        self.assertIn("Resumen", html)
        self.assertIn("Confirmar transición", html)
        self.assertEqual(TransicionEtapa.objects.filter(estado_orden="a_realizar").count(), 0)  # el resumen no escribe
        firma = resumen.context["firma"]
        respuesta = self.client.post(self.url, self.nueva(accion="confirmar", firma=firma))
        self.assertRedirects(respuesta, reverse("produccion:ordenes"))
        orden = TransicionEtapa.objects.get(estado_orden="a_realizar")
        self.assertEqual((orden.lote_id, orden.capataz_id), (self.lote.pk, self.e.capataz.pk))
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.capataz).count(), 1)

    def test_confirmar_sin_haber_visto_el_resumen_de_lo_que_se_envia_no_escribe(self):
        """Si cambió un dato después de ver el resumen (la firma no coincide), no se confirma lo que no se vio: se muestra el resumen nuevo."""
        resumen = self.client.post(self.url, self.nueva(accion="calcular"))
        respuesta = self.client.post(self.url, self.nueva(accion="confirmar", firma=resumen.context["firma"], descripcion="Otra"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("revisalo de nuevo", respuesta.content.decode())
        self.assertEqual(TransicionEtapa.objects.filter(estado_orden="a_realizar").count(), 0)

    def test_los_errores_van_debajo_de_su_campo(self):
        """Fecha pasada, distribución incompleta y prioridad inválida: cada error con su campo; nada se crea."""
        html = self.client.post(self.url, self.nueva(accion="calcular", fecha_programada=(hoy() - timedelta(days=1)).isoformat())).content.decode()
        self.assertIn("no puede ser anterior a hoy", html)
        html = self.client.post(self.url, self.nueva(accion="calcular", **{f"sector_{self.destino.pk}": "40"})).content.decode()
        self.assertIn("faltan ubicar 10", html)
        html = self.client.post(self.url, self.nueva(accion="calcular", prioridad="urgente")).content.decode()
        self.assertIn("alta, media o baja", html)
        self.assertEqual(TransicionEtapa.objects.filter(estado_orden="a_realizar").count(), 0)

    def test_ext_13b_si_cambio_la_cantidad_se_descarta_la_distribucion_y_se_muestra_la_nueva(self):
        """Extensión 13b: una merma bajó la cantidad: no se registra nada, se informa la nueva y la distribución vuelve a cero."""
        Lote.objects.filter(pk=self.lote.pk).update(cantidad_actual=45)
        respuesta = self.client.post(self.url, self.nueva(accion="calcular"))
        html = respuesta.content.decode()
        self.assertIn("ahora tiene 45 plantas", html)
        self.assertNotIn("Confirmar transición", html)
        self.assertIn('name="cantidad_vista" value="45"', html)

    def test_ext_3a_un_lote_con_otra_transicion_no_se_puede_elegir_y_se_dice_cual(self):
        orden = orden_de_transicion(self.e, self.lote, dias=3)
        html = self.client.get(self.url).content.decode()
        self.assertIn(f"Ya tiene la transición {orden.codigo}", html)
        respuesta = self.client.post(self.url, self.nueva(accion="calcular"))
        self.assertIn(orden.codigo, respuesta.content.decode())
        self.assertEqual(TransicionEtapa.objects.filter(estado_orden="a_realizar").count(), 1)

    def test_sin_lotes_el_formulario_esta_deshabilitado_con_su_motivo(self):
        """Sin ningún lote en los invernaderos activos a cargo (acá, el único está inactivo): se dice por qué y el botón de resumen queda
        deshabilitado."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        html = self.client.get(self.url).content.decode()
        self.assertIn("No hay lotes activos", html)
        self.assertIn("disabled", html.split("Ver resumen")[0][-120:])

    def test_sin_lotes_para_trasladar_dice_por_que_cada_uno_no_se_puede(self):
        otro = lote_con_ciclo(self.e, cantidad=5, etapa="maduracion")
        orden_de_transicion(self.e, self.lote)
        html = self.client.get(self.url).content.decode()
        self.assertIn("Ningún lote se puede trasladar por ahora", html)
        self.assertIn("última etapa de su ciclo", html)
        self.assertIn(otro.codigo, html)
        self.assertIn("disabled", html.split("Ver resumen")[0][-120:])
        self.assertNotIn('hx-trigger="change"', html)  # ningún lote se puede elegir: ninguno dispara el redibujado

    def test_el_html_escapa_los_nombres(self):
        """Todo lo que viene de la base se escapa: la descripción escrita y los nombres de invernadero y de sector no se interpretan."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(nombre_invernadero="<script>alert(1)</script>")
        SectorProduccion.objects.filter(pk=self.destino.pk).update(nombre_sector="<b>Sector</b>")
        html = self.client.post(self.url, self.nueva(accion="calcular", descripcion="<img src=x onerror=alert(2)>")).content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<b>Sector</b>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)

    def test_no_hace_consultas_por_fila(self):
        def consultas():
            with CaptureQueriesContext(connection) as capturadas:
                self.client.get(self.url, {"lote": self.lote.pk})
            return len(capturadas)

        con_uno = consultas()
        for _ in range(3):
            lote_con_ciclo(self.e, cantidad=5)
        self.assertEqual(con_uno, consultas())


class ConcretarTransicionTests(Base):
    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        super().setUp()
        self.orden = orden_de_transicion(self.e, self.lote)
        self.url = reverse("produccion:concretar", args=[self.orden.pk])
        self.entrar(self.e.capataz)

    def datos(self, **cambios):
        datos = {"fecha_efectiva": hoy().isoformat(), "cantidad_vista": "50", f"ubicadas_{self.destino.pk}": "", "causa": "", "descripcion": "", "accion": "calcular"}
        datos.update(cambios)
        return datos

    def test_paso_4_propone_lo_planificado_y_no_pide_la_causa_todavia(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("Concretar", html)
        self.assertIn(f'name="ubicadas_{self.destino.pk}"', html)
        self.assertIn('placeholder="50"', html)
        self.assertNotIn('name="causa"', html)  # la causa aparece solo cuando faltan plantas

    def test_la_causa_aparece_solo_cuando_faltan_plantas(self):
        """Extensión 10a: con el total completo no hay causa; al ubicar menos plantas, el resumen se rechaza pidiéndola y el campo aparece."""
        completo = self.client.post(self.url, self.datos())
        self.assertNotIn('name="causa"', completo.content.decode())
        self.assertIn("Confirmar transición", completo.content.decode())
        faltan = self.client.post(self.url, self.datos(**{f"ubicadas_{self.destino.pk}": "40"}))
        html = faltan.content.decode()
        self.assertIn('name="causa"', html)
        self.assertIn("obligatoria", html)
        self.assertNotIn("Confirmar transición", html)

    def test_el_resumen_del_capataz_muestra_la_merma_con_su_causa(self):
        datos = self.datos(**{f"ubicadas_{self.destino.pk}": "40"}, causa="plaga", descripcion="Hongo")
        html = self.client.post(self.url, datos).content.decode()
        self.assertIn("10 plantas sin trasladar", html)
        self.assertIn("Plaga", html)
        self.assertIn("Hongo", html)
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 50)  # el resumen no escribe

    def test_sin_javascript_el_flujo_completo_funciona_y_concreta(self):
        resumen = self.client.post(self.url, self.datos(**{f"ubicadas_{self.destino.pk}": "40"}, causa="plaga"))
        confirmar = self.datos(**{f"ubicadas_{self.destino.pk}": "40"}, causa="plaga", accion="confirmar", firma=resumen.context["firma"])
        respuesta = self.client.post(self.url, confirmar)
        self.assertRedirects(respuesta, reverse("produccion:bandeja"))
        lote = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual((lote.etapa_id, lote.cantidad_actual), (self.orden.etapa_destino_id, 40))
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "concretada")
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.agronomo).count(), 1)

    def test_errores_por_campo_fecha_y_cantidad(self):
        html = self.client.post(self.url, self.datos(fecha_efectiva=(hoy() + timedelta(days=1)).isoformat())).content.decode()
        self.assertIn("no puede ser posterior a hoy", html)
        html = self.client.post(self.url, self.datos(**{f"ubicadas_{self.destino.pk}": "51"})).content.decode()
        self.assertIn("indicá una cantidad menor", html)
        html = self.client.post(self.url, self.datos(**{f"ubicadas_{self.destino.pk}": "0"}, causa="plaga")).content.decode()
        self.assertIn("sin plantas trasladadas", html)
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "a_realizar")

    def test_ext_13c_si_cambio_la_cantidad_vuelve_a_proponer_con_la_nueva(self):
        Lote.objects.filter(pk=self.lote.pk).update(cantidad_actual=45)
        html = self.client.post(self.url, self.datos()).content.decode()
        self.assertIn("ahora tiene 45 plantas", html)
        self.assertIn('placeholder="45"', html)
        self.assertIn('name="cantidad_vista" value="45"', html)
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "a_realizar")

    def test_ext_13b_una_orden_que_ya_no_esta_a_realizar_vuelve_a_la_bandeja_con_su_estado(self):
        TransicionEtapa.objects.filter(pk=self.orden.pk).update(
            estado_orden="cancelada", fecha_resolucion_orden=hoy(), motivo_cancelacion="Ya no hace falta"
        )
        respuesta = self.client.get(self.url)
        self.assertRedirects(respuesta, reverse("produccion:bandeja"))
        self.assertIn("cancelada", [m.message for m in respuesta.wsgi_request._messages][0])

    def test_ext_11a_con_maduracion_vencida_el_resumen_advierte_sin_bloquear(self):
        e = invernadero_con_produccion(nombre="Corto", sufijo="c", etapas=("germinacion", "crecimiento", "maduracion"))
        lote = lote_con_ciclo(e, cantidad=10, dias_en_etapa=30)
        orden = orden_de_transicion(e, lote, distribucion={"maduracion": 10})
        self.entrar(e.capataz)
        datos = {"fecha_efectiva": (hoy() - timedelta(days=25)).isoformat(), "cantidad_vista": "10", "accion": "calcular"}
        html = self.client.post(reverse("produccion:concretar", args=[orden.pk]), datos).content.decode()
        self.assertIn("no contará como stock maduro libre", html)
        self.assertIn("Confirmar transición", html)

    def test_el_html_escapa_la_descripcion_y_los_nombres(self):
        SectorProduccion.objects.filter(pk=self.destino.pk).update(nombre_sector="<b>Sector</b>")
        datos = self.datos(**{f"ubicadas_{self.destino.pk}": "40"}, causa="otra", descripcion="<script>x</script>")
        html = self.client.post(self.url, datos).content.decode()
        self.assertNotIn("<script>x</script>", html)
        self.assertNotIn("<b>Sector</b>", html)

    def test_la_bandeja_ofrece_concretar_transicion_y_no_hace_consultas_por_fila(self):
        html = self.client.get(reverse("produccion:bandeja")).content.decode()
        self.assertIn("Concretar transición", html)
        self.assertIn(self.orden.codigo, html)

        def consultas():
            with CaptureQueriesContext(connection) as capturadas:
                self.client.get(reverse("produccion:bandeja"))
            return len(capturadas)

        con_una = consultas()
        for _ in range(3):
            orden_de_transicion(self.e, lote_con_ciclo(self.e, cantidad=5))
        self.assertEqual(con_una, consultas())


class CancelarTransicionDesdeLaPantallaTests(Base):
    def setUp(self):
        super().setUp()
        self.orden = orden_de_transicion(self.e, self.lote)
        self.url = reverse("produccion:cancelar", args=[self.orden.pk])
        self.entrar(self.e.agronomo)

    def test_la_pantalla_muestra_el_lote_las_etapas_y_los_agujeros_que_se_liberan(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn(self.lote.codigo, html)
        self.assertIn("Crecimiento → Floración", html)
        self.assertIn(self.destino.nombre_sector, html)
        self.assertIn("No tiene reservas de insumo", html)

    def test_sin_motivo_error_debajo_del_campo_y_con_motivo_cancela(self):
        html = self.client.post(self.url, {"motivo": "  "}).content.decode()
        self.assertIn("Indicá el motivo", html)
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "a_realizar")
        self.assertRedirects(self.client.post(self.url, {"motivo": "Cambio de planes"}), reverse("produccion:ordenes"))
        self.assertEqual(TransicionEtapa.objects.get(pk=self.orden.pk).estado_orden, "cancelada")

    def test_la_lista_incluye_las_transiciones_y_el_detalle_muestra_su_lote_y_etapa(self):
        html = self.client.get(reverse("produccion:ordenes")).content.decode()
        self.assertIn(self.orden.codigo, html)
        self.assertIn(self.lote.codigo, html)
        detalle = self.client.get(reverse("produccion:orden", args=[self.orden.pk])).content.decode()
        for texto in (self.lote.codigo, "Floración", "Transición de etapa"):
            self.assertIn(texto, detalle)
        self.assertNotIn("Plantines planificados", detalle)
