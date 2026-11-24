# Pruebas de las pantallas de las cosechas (COM-04a, paso 7; docs/casos_de_uso/produccion/cosecha.md, «Pantallas»): permisos (cada rol ve lo suyo y ningún botón
# lleva a un 403), los flujos de planificar, modificar, concretar y cancelar con HTMX y sin él, las páginas `calcular/` y `revisar/` que no escriben nada, los errores
# por campo y los botones de la lista de órdenes y la bandeja de `produccion`. Las reglas de negocio ya las prueban los servicios (`test_prod_pnf_csc.py`,
# `test_prod_mod_csc.py`, `test_prod_cnc_csc.py`, `test_prod_cnl_ord_cosechas.py`): acá, los permisos, el flujo y lo que muestra cada pantalla.

import re
from datetime import timedelta
from html import unescape

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import CompraVenta
from comercial.servicios import cosechas
from comercial.tests.fabricas import compra_venta, cosecha_manual, detalle, escenario_comercial, verificar_invariantes_de_reservas
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo
from produccion.models import Cosecha, Lote, OrdenTrabajo
from produccion.tests.fabricas import lote_maduro

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()


def iso(dias):
    return str(HOY + timedelta(days=dias))


def avisos(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


def texto(respuesta):
    return unescape(respuesta.content.decode())


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con Agrónomo, Capataz y Vendedor, un lote de 100 en Maduración, una venta con envío de 50 plantas para dentro de 10 días y una cosecha
    automática de 30 que la cubre."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.sector = self.e.sectores["maduracion"]
        self.venta = compra_venta(self.e, dias=10)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.cosecha = cosecha_manual(self.e, [(self.lote, 30)], detalle_=self.detalle, dias=5, origen="automatica")
        self.addCleanup(verificar_invariantes_de_reservas)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def post_de_planificacion(self, **extra):
        """Lo que manda el formulario: el invernadero, sin contrato, la variedad, la fecha y 20 plantas del lote."""
        datos = {
            "invernadero": str(self.e.invernadero.pk), "modo": "sin", "variedad": str(self.e.variedad.pk), "fecha_programada": iso(4), "prioridad": "media",
            "descripcion": "", f"lote_{self.lote.pk}": "20",
        }
        datos.update(extra)
        return datos


class PermisosTests(Base):
    def test_regla_cada_pantalla_es_de_su_rol_y_nadie_mas_entra(self):
        """Planificar, modificar y cancelar son del Agrónomo; concretar, del Capataz. El Gerente, el Vendedor y el otro rol reciben 403 (sin cuenta, al login)."""
        urls_del_agronomo = [
            reverse("comercial:cosecha_planificar"), reverse("comercial:cosecha_modificar", args=[self.cosecha.pk]), reverse("comercial:cosecha_cancelar", args=[self.cosecha.pk]),
        ]
        url_del_capataz = reverse("comercial:cosecha_concretar", args=[self.cosecha.pk])
        gerente = crear_gerente()
        for cuenta in (gerente, self.e.vendedor, self.e.capataz):
            self.entrar(cuenta)
            for url in urls_del_agronomo:
                self.assertEqual(self.client.get(url).status_code, 403, f"{cuenta.rol} {url}")
        for cuenta in (gerente, self.e.vendedor, self.e.agronomo):
            self.entrar(cuenta)
            self.assertEqual(self.client.get(url_del_capataz).status_code, 403, cuenta.rol)
        self.client.logout()
        self.assertEqual(self.client.get(urls_del_agronomo[0]).status_code, 302)

    def test_regla_el_capataz_no_concreta_una_cosecha_ajena_ni_el_agronomo_ajeno_la_modifica(self):
        """Un Capataz que no es el asignado y un Agrónomo que no tiene el invernadero a cargo reciben 403; la cosecha no cambia."""
        self.entrar(crear_capataz_activo(email="ajeno@infoponia.com"))
        self.assertEqual(self.client.get(reverse("comercial:cosecha_concretar", args=[self.cosecha.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("comercial:cosecha_concretar", args=[self.cosecha.pk]), {}).status_code, 403)
        self.entrar(crear_agronomo(email="ajeno2@infoponia.com"))
        for nombre in ("cosecha_modificar", "cosecha_cancelar"):
            self.assertEqual(self.client.get(reverse(f"comercial:{nombre}", args=[self.cosecha.pk])).status_code, 403, nombre)
        self.assertEqual(self.client.post(reverse("comercial:cosecha_cancelar", args=[self.cosecha.pk]), {"motivo": "x", "huella": "x"}).status_code, 403)
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).estado_orden, "a_realizar")

    def test_regla_ningun_boton_de_la_lista_ni_de_la_bandeja_lleva_a_un_403(self):
        """D-30: cada enlace de cosecha que ve cada rol en la lista de órdenes, en el detalle y en la bandeja se abre (no da 403 ni 404)."""
        for cuenta, url in (
            (self.e.agronomo, reverse("produccion:ordenes") + "?tipo=cosecha"),
            (self.e.agronomo, reverse("produccion:orden", args=[self.cosecha.pk])),
            (self.e.capataz, reverse("produccion:bandeja")),
            (self.e.capataz, reverse("produccion:orden", args=[self.cosecha.pk])),
            (crear_gerente(), reverse("produccion:ordenes") + "?tipo=cosecha"),
        ):
            self.entrar(cuenta)
            pagina = self.client.get(url)
            self.assertEqual(pagina.status_code, 200, url)
            for enlace in set(re.findall(r'href="(/comercial/cosechas/[^"]+)"', pagina.content.decode())):
                self.assertEqual(self.client.get(enlace).status_code, 200, f"{cuenta.rol}: {enlace}")


class ListaYBandejaTests(Base):
    def test_regla_la_lista_filtrada_por_cosecha_muestra_origen_contrato_y_los_botones_del_agronomo(self):
        """La vista «Cosecha» suma las columnas «Origen» y «Contrato»; el Agrónomo ve «Planificar cosecha», «Modificar» y «Cancelar»; el Gerente, solo la lista."""
        self.entrar(self.e.agronomo)
        pagina = texto(self.client.get(reverse("produccion:ordenes") + "?tipo=cosecha"))
        for esperado in ("Origen", "Contrato", "Automática", self.venta.codigo, "Planificar cosecha", "Modificar", "Cancelar", self.cosecha.codigo):
            self.assertIn(esperado, pagina)
        self.entrar(crear_gerente())
        pagina = texto(self.client.get(reverse("produccion:ordenes") + "?tipo=cosecha"))
        self.assertIn(self.cosecha.codigo, pagina)
        for ausente in ("Planificar cosecha", "Modificar", "/cancelar/"):
            self.assertNotIn(ausente, pagina)

    def test_regla_la_lista_sin_filtro_muestra_la_cosecha_y_con_htmx_solo_la_tabla(self):
        """Sin los `exclude` de COM-02, la cosecha está en la lista; con HTMX vuelve solo el fragmento de la tabla."""
        self.entrar(self.e.agronomo)
        self.assertIn(self.cosecha.codigo, texto(self.client.get(reverse("produccion:ordenes"))))
        fragmento = texto(self.client.get(reverse("produccion:ordenes") + "?tipo=cosecha", **HTMX))
        self.assertIn(self.cosecha.codigo, fragmento)
        self.assertNotIn("<html", fragmento)

    def test_regla_la_bandeja_del_capataz_trae_la_cosecha_con_su_boton_y_el_otro_capataz_no_la_ve(self):
        """La bandeja muestra la cosecha con «Concretar cosecha»; el detalle muestra el contrato y los lotes; otro Capataz no ve nada."""
        self.entrar(self.e.capataz)
        pagina = texto(self.client.get(reverse("produccion:bandeja")))
        self.assertIn(self.cosecha.codigo, pagina)
        self.assertIn("Concretar cosecha", pagina)
        detalle_ = texto(self.client.get(reverse("produccion:orden", args=[self.cosecha.pk])))
        self.assertIn(self.venta.codigo, detalle_)
        self.assertIn(f"L-{self.lote.pk}", detalle_)
        self.entrar(crear_capataz_activo(email="otro@infoponia.com"))
        self.assertNotIn(self.cosecha.codigo, texto(self.client.get(reverse("produccion:bandeja"))))

    def test_regla_el_inicio_del_agronomo_trae_el_grupo_cosechas(self):
        """`secCosecha`: el Inicio del Agrónomo suma el grupo «Cosechas» con lo a realizar."""
        self.entrar(self.e.agronomo)
        pagina = texto(self.client.get(reverse("core:inicio")))
        self.assertIn("Cosechas", pagina)
        self.assertIn("A realizar", pagina)

    def test_regla_el_inicio_del_capataz_lleva_a_concretar_la_cosecha_de_hoy(self):
        """La sección «Mis órdenes» del Inicio del Capataz también ofrece «Concretar cosecha» para una cosecha de hoy."""
        hoy = cosecha_manual(self.e, [(self.lote, 5)], dias=0)
        self.entrar(self.e.capataz)
        self.assertIn(reverse("comercial:cosecha_concretar", args=[hoy.pk]), texto(self.client.get(reverse("core:inicio"))))


class PlanificarTests(Base):
    def test_flujo_principal_sin_javascript_actualizar_resumen_y_confirmar(self):
        """El flujo completo con páginas: elegir el invernadero (Actualizar), ver el resumen (con su firma) y confirmar; la cosecha queda planificada y el
        Agrónomo vuelve a la lista de cosechas con un aviso."""
        self.entrar(self.e.agronomo)
        self.assertEqual(self.client.get(reverse("comercial:cosecha_planificar")).status_code, 200)
        calculo = self.client.post(reverse("comercial:cosecha_planificar_calcular"), {"invernadero": str(self.e.invernadero.pk), "modo": "contrato"})
        self.assertEqual(calculo.status_code, 200)
        self.assertIn(self.venta.codigo, texto(calculo))  # el detalle aparece para elegirlo
        datos = self.post_de_planificacion()
        resumen = self.client.post(reverse("comercial:cosecha_planificar_revisar"), datos)
        self.assertEqual(resumen.status_code, 200)
        self.assertIn("Confirmar planificación", texto(resumen))
        self.assertFalse(Cosecha.objects.filter(origen_cosecha="manual").exists())  # el resumen no escribe
        datos["firma"] = resumen.context["firma"]
        respuesta = self.client.post(reverse("comercial:cosecha_planificar"), datos)
        self.assertRedirects(respuesta, reverse("produccion:ordenes") + "?tipo=cosecha", fetch_redirect_response=False)
        nueva = Cosecha.objects.get(origen_cosecha="manual")
        self.assertEqual((nueva.agronomo_id, nueva.fecha_programada_orden), (self.e.agronomo.pk, HOY + timedelta(days=4)))
        self.assertTrue(any(nueva.codigo in a for a in avisos(respuesta)))
        self.assertTrue(Notificacion.objects.filter(destinatario=self.e.capataz, titulo=f"Nueva cosecha {nueva.codigo}").exists())

    def test_regla_calcular_no_escribe_nada_y_con_htmx_devuelve_solo_el_formulario(self):
        """Las páginas `calcular/` redibujan sin validar ni escribir (ni auditoría ni avisos); con HTMX, solo el bloque del formulario."""
        self.entrar(self.e.agronomo)
        antes = (Cosecha.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count())
        datos = self.post_de_planificacion(fecha_programada="no-es-una-fecha", **{f"lote_{self.lote.pk}": "9999"})
        respuesta = self.client.post(reverse("comercial:cosecha_planificar_calcular"), datos, **HTMX)
        self.assertEqual(respuesta.status_code, 200)
        contenido = texto(respuesta)
        self.assertNotIn("<html", contenido)
        self.assertNotIn('class="err"', contenido)  # no valida
        self.assertEqual((Cosecha.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)

    def test_regla_los_selectores_redibujan_por_htmx_sin_validar_al_tipear(self):
        """`.claude/rules/interfaz.md`: los selectores usan `change`, `hx-swap="innerHTML show:none"` y `data-sin-envio-en-curso`; ningún campo valida con `input`."""
        self.entrar(self.e.agronomo)
        pagina = texto(self.client.post(reverse("comercial:cosecha_planificar_calcular"), {"invernadero": str(self.e.invernadero.pk), "modo": "contrato"}))
        self.assertIn('hx-trigger="change"', pagina)
        self.assertIn('hx-swap="innerHTML show:none"', pagina)
        self.assertIn("data-sin-envio-en-curso", pagina)
        self.assertNotIn("input delay", pagina)
        self.assertIn('formaction="' + reverse("comercial:cosecha_planificar_calcular"), pagina)  # respaldo sin JavaScript

    def test_regla_los_errores_salen_por_campo(self):
        """«Ver resumen» con una fecha pasada y más plantas que el stock libre muestra cada error debajo de su campo y no muestra el resumen."""
        self.entrar(self.e.agronomo)
        datos = self.post_de_planificacion(fecha_programada=iso(-1), **{f"lote_{self.lote.pk}": "500"})
        pagina = texto(self.client.post(reverse("comercial:cosecha_planificar_revisar"), datos))
        self.assertIn("no puede ser anterior a hoy", pagina)
        self.assertIn("libres", pagina)
        self.assertNotIn("Confirmar planificación", pagina)

    def test_regla_confirmar_sin_ver_el_resumen_o_con_un_dato_cambiado_vuelve_a_mostrarlo(self):
        """Sin la firma del resumen (o con otra) no se escribe: se muestra el resumen con el aviso de que cambió algo."""
        self.entrar(self.e.agronomo)
        datos = self.post_de_planificacion()
        sin_firma = self.client.post(reverse("comercial:cosecha_planificar"), datos)
        self.assertIn("Cambiaste un dato", texto(sin_firma))
        self.assertEqual(Cosecha.objects.filter(origen_cosecha="manual").count(), 0)

    def test_regla_un_rechazo_de_la_verificacion_bajo_bloqueo_vuelve_con_su_error(self):
        """15b: si entre el resumen y la confirmación otra cosecha tomó el stock, la confirmación no escribe y muestra el error del lote."""
        self.entrar(self.e.agronomo)
        datos = self.post_de_planificacion(**{f"lote_{self.lote.pk}": "70"})
        resumen = self.client.post(reverse("comercial:cosecha_planificar_revisar"), datos)
        datos["firma"] = resumen.context["firma"]
        cosecha_manual(self.e, [(self.lote, 60)], dias=1)  # otra operación reserva el stock (30 + 60 = 90; quedan 10)
        pagina = texto(self.client.post(reverse("comercial:cosecha_planificar"), datos))
        self.assertIn("libres", pagina)
        self.assertEqual(Cosecha.objects.filter(origen_cosecha="manual").count(), 1)  # solo la de «la otra operación»


class ModificarTests(Base):
    def post_de_modificacion(self, **extra):
        datos = {"fecha_programada": iso(5), "prioridad": "media", "descripcion": "", f"lote_{self.lote.pk}": "30", "huella": cosechas.huella_de(self.cosecha)}
        datos.update(extra)
        return datos

    def test_flujo_principal_resumen_con_antes_y_despues_y_confirmar(self):
        """GET con lo guardado, «Ver resumen» con la tabla antes/después (sin escribir) y «Confirmar cambios»: cambia la prioridad y se avisa al Capataz."""
        self.entrar(self.e.agronomo)
        pagina = texto(self.client.get(reverse("comercial:cosecha_modificar", args=[self.cosecha.pk])))
        self.assertIn(self.cosecha.codigo, pagina)
        self.assertIn(self.venta.codigo, pagina)
        self.assertNotIn("Variedad</label>", pagina)  # 5c: no ofrece variedad, invernadero, contrato ni cantidad total
        datos = self.post_de_modificacion(prioridad="alta")
        resumen = self.client.post(reverse("comercial:cosecha_modificar_revisar", args=[self.cosecha.pk]), datos)
        contenido = texto(resumen)
        self.assertIn("Resumen de los cambios", contenido)
        self.assertIn("media", contenido)
        self.assertIn("alta", contenido)
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).prioridad_orden, "media")
        datos["firma"] = resumen.context["firma"]
        respuesta = self.client.post(reverse("comercial:cosecha_modificar", args=[self.cosecha.pk]), datos)
        self.assertRedirects(respuesta, reverse("produccion:ordenes") + "?tipo=cosecha", fetch_redirect_response=False)
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).prioridad_orden, "alta")
        self.assertTrue(Notificacion.objects.filter(destinatario=self.e.capataz, titulo=f"Cosecha {self.cosecha.codigo} modificada").exists())

    def test_regla_sin_cambios_y_total_distinto_salen_como_errores(self):
        """7a y 5b.4a: «Ver resumen» sin cambios dice que no hay nada que modificar; con un total distinto del reservado no deja terminar."""
        self.entrar(self.e.agronomo)
        sin_cambios = texto(self.client.post(reverse("comercial:cosecha_modificar_revisar", args=[self.cosecha.pk]), self.post_de_modificacion()))
        self.assertIn("No indicaste ningún cambio", sin_cambios)
        distinto = texto(self.client.post(reverse("comercial:cosecha_modificar_revisar", args=[self.cosecha.pk]), self.post_de_modificacion(**{f"lote_{self.lote.pk}": "20"})))
        self.assertIn("no coincide con el reservado", distinto)
        self.assertNotIn("Confirmar cambios", distinto)

    def test_regla_si_la_cosecha_cambio_mientras_se_editaba_se_vuelve_a_abrir(self):
        """10a: con la huella vieja (otra persona modificó la cosecha), no se escribe y se vuelve a abrir con un aviso."""
        self.entrar(self.e.agronomo)
        datos = self.post_de_modificacion(prioridad="alta")
        resumen = self.client.post(reverse("comercial:cosecha_modificar_revisar", args=[self.cosecha.pk]), datos)
        datos["firma"] = resumen.context["firma"]
        OrdenTrabajo.objects.filter(pk=self.cosecha.pk).update(descripcion_orden="la tocó otro")
        respuesta = self.client.post(reverse("comercial:cosecha_modificar", args=[self.cosecha.pk]), datos)
        self.assertRedirects(respuesta, reverse("comercial:cosecha_modificar", args=[self.cosecha.pk]), fetch_redirect_response=False)
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).prioridad_orden, "media")

    def test_regla_una_cosecha_resuelta_vuelve_a_la_lista_con_su_estado(self):
        """10a: una cosecha cancelada mientras tanto no se abre: vuelve a la lista de cosechas con el estado actual."""
        self.entrar(self.e.agronomo)
        OrdenTrabajo.objects.filter(pk=self.cosecha.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")
        respuesta = self.client.get(reverse("comercial:cosecha_modificar", args=[self.cosecha.pk]))
        self.assertRedirects(respuesta, reverse("produccion:ordenes") + "?tipo=cosecha", fetch_redirect_response=False)
        self.assertTrue(any("cancelada" in a for a in avisos(respuesta)))

    def test_regla_calcular_no_escribe_nada(self):
        """`calcular/` redibuja con lo escrito, sin validar ni escribir."""
        self.entrar(self.e.agronomo)
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        respuesta = self.client.post(reverse("comercial:cosecha_modificar_calcular", args=[self.cosecha.pk]), self.post_de_modificacion(fecha_programada="x", prioridad="alta"), **HTMX)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("<html", texto(respuesta))
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).prioridad_orden, "media")


class ConcretarTests(Base):
    def test_flujo_principal_propuesta_resumen_y_confirmar(self):
        """GET con la propuesta por sector como texto de ayuda; «Ver resumen» con perdidas (4) y el destino; «Confirmar concreción» concreta y vuelve a la bandeja."""
        self.entrar(self.e.capataz)
        pagina = texto(self.client.get(reverse("comercial:cosecha_concretar", args=[self.cosecha.pk])))
        self.assertIn(f'placeholder="30"', pagina)
        self.assertIn("Fecha efectiva", pagina)
        datos = {
            "fecha_efectiva": iso(0), f"cant_{self.lote.pk}_{self.sector.pk}": "25", f"perd_{self.lote.pk}_{self.sector.pk}": "4", f"causa_{self.lote.pk}": "plaga", f"desc_{self.lote.pk}": "",
        }
        resumen = self.client.post(reverse("comercial:cosecha_concretar_revisar", args=[self.cosecha.pk]), datos)
        contenido = texto(resumen)
        self.assertIn("Resumen", contenido)
        self.assertIn("Faltan 5", contenido)
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).estado_orden, "a_realizar")
        datos["firma"] = resumen.context["firma"]
        respuesta = self.client.post(reverse("comercial:cosecha_concretar", args=[self.cosecha.pk]), datos)
        self.assertRedirects(respuesta, reverse("produccion:bandeja"), fetch_redirect_response=False)
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).estado_orden, "concretada")
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 71)

    def test_regla_los_errores_salen_por_campo_y_no_se_muestra_el_resumen(self):
        """8a, 6a y 10a.3b: más plantas que los agujeros del sector, una fecha futura y plantas perdidas sin causa."""
        self.entrar(self.e.capataz)
        datos = {"fecha_efectiva": iso(2), f"cant_{self.lote.pk}_{self.sector.pk}": "101", f"perd_{self.lote.pk}_{self.sector.pk}": "1"}
        pagina = texto(self.client.post(reverse("comercial:cosecha_concretar_revisar", args=[self.cosecha.pk]), datos))
        self.assertIn("posterior a hoy", pagina)
        self.assertIn("ocupa 100 agujeros", pagina)
        self.assertNotIn("Confirmar concreción", pagina)

    def test_regla_una_cosecha_que_ya_no_esta_a_realizar_no_se_abre_y_vuelve_a_la_bandeja(self):
        """13b: se informa el estado actual y se vuelve a la bandeja; ni el GET ni el POST concretan otra vez."""
        self.entrar(self.e.capataz)
        OrdenTrabajo.objects.filter(pk=self.cosecha.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")
        respuesta = self.client.get(reverse("comercial:cosecha_concretar", args=[self.cosecha.pk]))
        self.assertRedirects(respuesta, reverse("produccion:bandeja"), fetch_redirect_response=False)
        self.assertTrue(any("cancelada" in a for a in avisos(respuesta)))

    def test_regla_calcular_y_revisar_no_escriben_nada(self):
        """Las páginas `calcular/` y `revisar/` no cambian el lote, la cosecha, la auditoría ni los avisos."""
        self.entrar(self.e.capataz)
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        for nombre in ("cosecha_concretar_calcular", "cosecha_concretar_revisar"):
            self.client.post(reverse(f"comercial:{nombre}", args=[self.cosecha.pk]), {"fecha_efectiva": iso(0), f"cant_{self.lote.pk}_{self.sector.pk}": "30"}, **HTMX)
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)
        self.assertEqual((Lote.objects.get(pk=self.lote.pk).cantidad_actual, Cosecha.objects.get(pk=self.cosecha.pk).estado_orden), (100, "a_realizar"))


class CancelarTests(Base):
    def test_flujo_principal_resumen_motivo_obligatorio_y_cancelar(self):
        """El resumen trae lo que se libera, el contrato y la estimación; con el motivo vacío da error; con motivo cancela, avisa al Capataz y vuelve a la lista."""
        self.entrar(self.e.agronomo)
        pagina = self.client.get(reverse("comercial:cosecha_cancelar", args=[self.cosecha.pk]))
        contenido = texto(pagina)
        self.assertIn(self.venta.codigo, contenido)
        self.assertIn(f"L-{self.lote.pk}", contenido)
        self.assertIn("Modificar cosecha", contenido)  # el recordatorio de PROD-MOD-CSC
        huella = pagina.context["resumen"].huella
        vacio = self.client.post(reverse("comercial:cosecha_cancelar", args=[self.cosecha.pk]), {"motivo": "  ", "huella": huella})
        self.assertIn("Indicá el motivo", texto(vacio))
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).estado_orden, "a_realizar")
        respuesta = self.client.post(reverse("comercial:cosecha_cancelar", args=[self.cosecha.pk]), {"motivo": "Se rompió el riego", "huella": huella})
        self.assertRedirects(respuesta, reverse("produccion:ordenes") + "?tipo=cosecha", fetch_redirect_response=False)
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).estado_orden, "cancelada")
        self.assertTrue(Notificacion.objects.filter(destinatario=self.e.capataz, titulo=f"Orden {self.cosecha.codigo} cancelada").exists())

    def test_regla_si_el_contrato_cambio_se_vuelve_a_abrir_el_resumen(self):
        """8b: si el detalle cambió de estado mientras se miraba el resumen, no se cancela y se vuelve a abrir la ventana."""
        self.entrar(self.e.agronomo)
        huella = self.client.get(reverse("comercial:cosecha_cancelar", args=[self.cosecha.pk])).context["resumen"].huella
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="cancelada")
        respuesta = self.client.post(reverse("comercial:cosecha_cancelar", args=[self.cosecha.pk]), {"motivo": "x", "huella": huella})
        self.assertRedirects(respuesta, reverse("comercial:cosecha_cancelar", args=[self.cosecha.pk]), fetch_redirect_response=False)
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).estado_orden, "a_realizar")

    def test_regla_la_pagina_de_cancelar_no_escribe_con_get(self):
        """El GET es una lectura: no cambia nada."""
        self.entrar(self.e.agronomo)
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        self.client.get(reverse("comercial:cosecha_cancelar", args=[self.cosecha.pk]))
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)
