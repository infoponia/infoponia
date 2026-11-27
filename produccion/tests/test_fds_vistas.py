# Pruebas de la pantalla «Poner fuera de servicio» (PRD-04, paso 7; PROD-PNR-FDS, `VIEWS.fs`): las vistas solo orquestan, las reglas ya se prueban en los
# servicios (`test_prod_pnr_fds.py`). Acá: quién entra (solo el Agrónomo a cargo; el resto, 404), el estado deshabilitado sin sectores, que elegir el sector no valida,
# el resumen antes de escribir (la «firma» y lo que la persona vio, extensión 14a), los errores por campo, que el HTML se escapa, las entradas desde la ficha del
# sector y desde la ventana de la baja (maestros) y que todo funciona sin JavaScript (un POST común) y con HTMX (solo el bloque que cambia).

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import SectorProduccion
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_sector, crear_vendedor
from produccion.models import FueraDeServicio, Merma, OcupacionSector, OrdenTrabajo, Reubicacion
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo, orden_de_siembra
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HX = {"HTTP_HX_REQUEST": "true"}
URL = "produccion:fuera_de_servicio"


class Base(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):  # CON-04a: estos servicios asientan
    """Un invernadero con un sector por etapa; `germ` es el de origen y `g2` un destino de Germinación."""

    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        self.e = invernadero_con_produccion()
        self.germ = self.e.sectores["germinacion"]
        self.g2 = crear_sector(self.e.invernadero, "Germinación 2", "germinacion", 100)
        self.hoy = timezone.localdate()
        self.client.force_login(self.e.agronomo)

    def datos(self, **cambios):
        """Un POST válido para un sector vacío: el sector, el motivo y la fecha de hoy."""
        base = {"sector": self.germ.pk, "motivo": "Se rompió el canal de retorno", "fecha": self.hoy.isoformat()}
        base.update(cambios)
        return base


class PermisosTests(Base):
    """D-30: solo el Agrónomo a cargo; el resto recibe 404 (no se le revela la ruta); el anónimo va al ingreso."""

    def test_el_agronomo_abre_la_pantalla(self):
        self.assertEqual(self.client.get(reverse(URL)).status_code, 200)

    def test_el_resto_de_los_roles_recibe_404_y_el_anonimo_va_al_ingreso(self):
        for cuenta in (self.e.capataz, crear_gerente(), crear_vendedor()):
            self.client.force_login(cuenta)
            self.assertEqual(self.client.get(reverse(URL)).status_code, 404, cuenta)
            self.assertEqual(self.client.post(reverse(URL), self.datos(accion="calcular")).status_code, 404, cuenta)
        self.client.logout()
        self.assertEqual(self.client.get(reverse(URL)).status_code, 302)

    def test_un_agronomo_ajeno_no_ve_el_sector_ni_puede_ponerlo_fuera_de_servicio(self):
        """Un sector que no es de sus invernaderos no se ofrece: la pantalla lo dice y no muestra datos del sector."""
        self.client.force_login(crear_agronomo(email="ajeno@infoponia.com"))
        respuesta = self.client.get(reverse(URL), {"sector": self.germ.pk})
        self.assertContains(respuesta, "No hay sectores activos")
        self.assertNotContains(respuesta, "Qué hay en el sector")
        self.client.post(reverse(URL), self.datos(accion="confirmar"))
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "activo")


class EleccionDelSectorTests(Base):
    """Paso 2 y 3: los sectores activos agrupados; elegir uno muestra su detalle sin validar."""

    def test_se_ofrecen_solo_los_sectores_activos_del_agronomo_agrupados_por_etapa(self):
        crear_sector(self.e.invernadero, "Fuera", "crecimiento", 10, "fuera_de_servicio")
        crear_sector(self.e.invernadero, "De baja", "crecimiento", 10, "inactivo")
        crear_sector(crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com")), "Ajeno-1", "germinacion")
        respuesta = self.client.get(reverse(URL))
        self.assertContains(respuesta, "Germinación 2")
        self.assertContains(respuesta, "Invernadero Norte · Germinación")
        for texto in ("Fuera", "De baja", "Ajeno-1"):
            self.assertNotContains(respuesta, f">{texto} (")

    def test_sin_sectores_activos_el_formulario_queda_deshabilitado_con_su_motivo(self):
        SectorProduccion.objects.update(estado_sector="inactivo")
        respuesta = self.client.get(reverse(URL))
        self.assertContains(respuesta, "No hay sectores activos")
        self.assertNotContains(respuesta, 'name="sector"')

    def test_elegir_el_sector_muestra_el_detalle_sin_validar_el_motivo_ni_la_fecha(self):
        """Interfaz: elegir otro sector (accion «actualizar») no valida nada: sin motivo ni fecha no hay errores."""
        lote_activo(self.e, cantidad=30)
        orden_de_siembra(self.e, plantines=9, sector="germinacion")
        respuesta = self.client.post(reverse(URL), {"sector": self.germ.pk, "accion": "actualizar", "motivo": ""})
        self.assertContains(respuesta, "Qué hay en el sector")
        self.assertContains(respuesta, "30 planta")
        self.assertContains(respuesta, "9 agujeros reservados")
        self.assertNotContains(respuesta, "Indicá el motivo")
        self.assertFalse(FueraDeServicio.objects.exists())

    def test_con_htmx_solo_se_devuelve_el_bloque_que_cambia_y_el_selector_no_valida(self):
        """HTMX: el fragmento (sin el marco de la página); el selector redibuja con `show:none` y `data-sin-envio-en-curso`, sin `keyup` ni `input`."""
        respuesta = self.client.post(reverse(URL), {"sector": self.germ.pk, "accion": "actualizar"}, **HX)
        self.assertNotContains(respuesta, "<html")
        pagina = self.client.get(reverse(URL)).content.decode()
        self.assertIn('hx-swap="innerHTML show:none"', pagina)
        self.assertIn("data-sin-envio-en-curso", respuesta.content.decode() + self.client.get(reverse(URL)).content.decode())
        self.assertNotIn("keyup", pagina)
        self.assertNotIn("input delay", pagina)

    def test_sin_javascript_hay_un_boton_continuar_en_noscript(self):
        self.assertContains(self.client.get(reverse(URL)), 'name="accion" value="actualizar"')

    def test_la_entrada_con_sector_en_la_url_lo_deja_elegido(self):
        """Entrada desde la ficha del sector y desde la ventana de la baja: `?sector=<id>`."""
        respuesta = self.client.get(reverse(URL), {"sector": self.germ.pk})
        self.assertContains(respuesta, "Qué hay en el sector")
        self.assertContains(respuesta, f'<option value="{self.germ.pk}" selected>')

    def test_el_nombre_del_sector_y_el_motivo_se_escapan(self):
        """Escape de HTML: nada de lo escrito o guardado se interpreta como marcado."""
        SectorProduccion.objects.filter(pk=self.germ.pk).update(nombre_sector="<script>x</script>")
        respuesta = self.client.post(reverse(URL), self.datos(motivo="<b>mal</b>", accion="calcular"))
        self.assertNotContains(respuesta, "<script>x</script>")
        self.assertNotContains(respuesta, "<b>mal</b>")


class ResumenYConfirmacionTests(Base):
    """Pasos 11 a 14: «Ver resumen» valida y no escribe; «Confirmar» escribe."""

    def armar_con_lote(self):
        self.lote = lote_activo(self.e, cantidad=40)
        self.siembra = orden_de_siembra(self.e, plantines=8, sector="germinacion")

    def con_lote(self, **cambios):
        datos = self.datos(**{f"reub_{self.lote.pk}_{self.g2.pk}": "25", f"causa_{self.lote.pk}": "plaga", f"desc_{self.lote.pk}": ""})
        datos.update(cambios)
        return datos

    def test_ver_resumen_muestra_lo_que_se_confirma_y_no_escribe(self):
        self.armar_con_lote()
        respuesta = self.client.post(reverse(URL), self.con_lote(accion="calcular"))
        self.assertContains(respuesta, "Resumen")
        self.assertContains(respuesta, "25 se reubican en Germinación 2 (25)")
        self.assertContains(respuesta, "15 se registran como merma por «plaga»")
        self.assertContains(respuesta, self.siembra.codigo)
        self.assertContains(respuesta, 'name="firma"')
        self.assertContains(respuesta, "Confirmar y poner fuera de servicio")
        self.assertFalse(FueraDeServicio.objects.exists() or Merma.objects.exists() or Reubicacion.objects.exists())
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "activo")

    def test_confirmar_con_la_firma_del_resumen_escribe_y_vuelve_a_la_ficha_con_el_aviso(self):
        """Flujo principal sin JavaScript: dos POST comunes (resumen y confirmar); el sector queda fuera de servicio, con un aviso que lista las órdenes por replanificar."""
        self.armar_con_lote()
        resumen = self.client.post(reverse(URL), self.con_lote(accion="calcular"))
        campos = {n: resumen.context["firma"] if n == "firma" else resumen.context["vistos"][n.removeprefix("visto_")] for n in ("firma", "visto_plantas", "visto_libres", "visto_ordenes")}
        respuesta = self.client.post(reverse(URL), self.con_lote(accion="confirmar", **campos), follow=True)
        self.assertRedirects(respuesta, reverse("maestros:invernadero", args=[self.e.invernadero.pk]))
        self.assertContains(respuesta, "quedó fuera de servicio")
        self.assertContains(respuesta, self.siembra.codigo)
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "fuera_de_servicio")
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.siembra.pk).estado_orden, "cancelada")
        self.assertEqual(Merma.objects.get().cant_merma, 15)
        self.assertEqual(OcupacionSector.objects.filter(reubicacion__isnull=False).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="fuera_de_servicio_sector").count(), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.capataz).count(), 1)

    def test_confirmar_sin_resumen_previo_no_escribe_y_muestra_el_resumen(self):
        """Sin la firma de un resumen visto no se confirma lo que la persona no vio: se calcula y se muestra."""
        self.armar_con_lote()
        respuesta = self.client.post(reverse(URL), self.con_lote(accion="confirmar"))
        self.assertContains(respuesta, "Cambiaste un dato después de ver el resumen")
        self.assertFalse(FueraDeServicio.objects.exists())

    def test_cambiar_un_dato_despues_del_resumen_pide_revisar_de_nuevo(self):
        self.armar_con_lote()
        resumen = self.client.post(reverse(URL), self.con_lote(accion="calcular"))
        respuesta = self.client.post(reverse(URL), self.con_lote(accion="confirmar", firma=resumen.context["firma"], motivo="Otro motivo"))
        self.assertContains(respuesta, "Cambiaste un dato después de ver el resumen")
        self.assertFalse(FueraDeServicio.objects.exists())

    def test_extension_14a_si_cambio_lo_que_vio_vuelve_con_lo_vigente_y_no_escribe(self):
        """Extensión 14a: otra operación cambió las plantas del lote después del resumen: `cambio_simultaneo`, nada escrito, el resumen se muestra con lo vigente."""
        self.armar_con_lote()
        resumen = self.client.post(reverse(URL), self.con_lote(accion="calcular"))
        campos = {n: resumen.context["firma"] if n == "firma" else resumen.context["vistos"][n.removeprefix("visto_")] for n in ("firma", "visto_plantas", "visto_libres", "visto_ordenes")}
        type(self.lote).objects.filter(pk=self.lote.pk).update(cantidad_actual=39)
        OcupacionSector.objects.filter(lote=self.lote, sector=self.germ).update(cant_agujeros_ocupados=39)
        respuesta = self.client.post(reverse(URL), self.con_lote(accion="confirmar", **campos))
        self.assertContains(respuesta, "Mientras cargabas los datos")
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(FueraDeServicio.objects.exists())
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "activo")

    def test_un_sector_vacio_solo_cambia_de_estado(self):
        """Extensión 6d: sin plantas ni órdenes el resumen lo dice y confirmar deja el sector fuera de servicio."""
        resumen = self.client.post(reverse(URL), self.datos(accion="calcular"))
        self.assertContains(resumen, "no tiene plantas")
        self.client.post(reverse(URL), self.datos(accion="confirmar", firma=resumen.context["firma"]))
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "fuera_de_servicio")


class ErroresPorCampoTests(Base):
    """Las reglas se rechazan en el campo que corresponde, sin perder lo escrito."""

    def test_motivo_y_fecha_se_rechazan_en_su_campo(self):
        respuesta = self.client.post(reverse(URL), self.datos(accion="calcular", motivo=""))
        self.assertContains(respuesta, "Indicá el motivo.")
        respuesta = self.client.post(reverse(URL), self.datos(accion="calcular", fecha=(self.hoy + timedelta(days=1)).isoformat()))
        self.assertContains(respuesta, "La fecha no puede ser posterior a hoy.")
        respuesta = self.client.post(reverse(URL), self.datos(accion="calcular", fecha="no-es-una-fecha"))
        self.assertContains(respuesta, "Indicá la fecha")
        self.assertEqual(respuesta.status_code, 200)

    def test_la_fecha_anterior_a_la_minima_dice_de_donde_sale(self):
        lote = lote_activo(self.e, cantidad=5)
        lote.siembra.fecha_siembra = self.hoy - timedelta(days=3)
        lote.siembra.save(update_fields=["fecha_siembra"])
        datos = self.datos(accion="calcular", fecha=(self.hoy - timedelta(days=4)).isoformat(), **{f"causa_{lote.pk}": "plaga"})
        respuesta = self.client.post(reverse(URL), datos)
        self.assertContains(respuesta, f"llegada del lote {lote.codigo}")

    def test_una_cantidad_invalida_se_rechaza_en_el_destino_y_conserva_lo_escrito(self):
        lote = lote_activo(self.e, cantidad=10)
        datos = self.datos(accion="calcular", **{f"reub_{lote.pk}_{self.g2.pk}": "11", f"causa_{lote.pk}": "plaga", f"desc_{lote.pk}": "Pulgón"})
        respuesta = self.client.post(reverse(URL), datos)
        self.assertContains(respuesta, "El lote tiene 10 plantas en el sector y reubicás 11")
        self.assertContains(respuesta, "Pulgón")
        self.assertContains(respuesta, 'value="11"')

    def test_una_cantidad_que_no_es_un_numero_se_rechaza_sin_romper(self):
        lote = lote_activo(self.e, cantidad=10)
        respuesta = self.client.post(reverse(URL), self.datos(accion="calcular", **{f"reub_{lote.pk}_{self.g2.pk}": "abc", f"causa_{lote.pk}": "plaga"}))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "número entero")

    def test_un_lote_con_plantas_sin_reubicar_sin_causa_se_rechaza_en_la_causa(self):
        lote = lote_activo(self.e, cantidad=10)
        respuesta = self.client.post(reverse(URL), self.datos(accion="calcular"))
        self.assertContains(respuesta, f"Indicá la causa de la merma del lote {lote.codigo}")

    def test_el_descarte_por_seleccion_no_se_ofrece_como_causa(self):
        lote_activo(self.e, cantidad=10)
        respuesta = self.client.get(reverse(URL), {"sector": self.germ.pk})
        self.assertContains(respuesta, "Plaga")
        self.assertNotContains(respuesta, "Descarte por selección")

    def test_un_lote_sin_destinos_elegibles_avisa_que_se_registra_como_merma(self):
        SectorProduccion.objects.filter(pk=self.g2.pk).update(estado_sector="inactivo")
        lote_activo(self.e, cantidad=10)
        self.assertContains(self.client.get(reverse(URL), {"sector": self.germ.pk}), "las plantas no se pueden reubicar y se registran como merma")

    def test_el_ultimo_sector_de_su_tipo_advierte_sin_bloquear(self):
        SectorProduccion.objects.filter(pk=self.g2.pk).update(estado_sector="inactivo")
        respuesta = self.client.get(reverse(URL), {"sector": self.germ.pk})
        self.assertContains(respuesta, "se queda sin sectores activos de Germinación")
        self.assertContains(respuesta, "Ver resumen")


class EntradasDeMaestrosTests(Base):
    """Las dos entradas: el menú de la tarjeta del sector y la ventana de la baja con impedimentos (D-30: solo si corresponde)."""

    def test_la_tarjeta_del_sector_activo_ofrece_poner_fuera_de_servicio_al_agronomo_a_cargo(self):
        respuesta = self.client.get(reverse("maestros:invernadero", args=[self.e.invernadero.pk]), {"tab": "sectores"})
        self.assertContains(respuesta, f"{reverse(URL)}?sector={self.germ.pk}")

    def test_un_sector_fuera_de_servicio_o_el_gerente_no_ven_la_entrada(self):
        SectorProduccion.objects.filter(pk=self.germ.pk).update(estado_sector="fuera_de_servicio")
        pagina = reverse("maestros:invernadero", args=[self.e.invernadero.pk])
        self.assertNotContains(self.client.get(pagina, {"tab": "sectores"}), f"{reverse(URL)}?sector={self.germ.pk}")
        self.client.force_login(crear_gerente())
        self.assertNotContains(self.client.get(pagina, {"tab": "sectores"}), reverse(URL))

    def test_la_ventana_de_la_baja_con_impedimentos_lleva_a_poner_fuera_de_servicio(self):
        lote_activo(self.e, cantidad=10)
        respuesta = self.client.get(reverse("maestros:sector_baja", args=[self.e.invernadero.pk, self.germ.pk]))
        self.assertContains(respuesta, "Lo ocupan")
        self.assertContains(respuesta, f"{reverse(URL)}?sector={self.germ.pk}")


class BitacoraTests(Base):
    """PROD-CNS-BIT con los dos tipos nuevos (docs/disparadores.md, «Cuando exista PROD-PNR-FDS»): se listan y se pueden filtrar."""

    def poner(self):
        from produccion.servicios import sectores_fuera_de_servicio as fds

        lote = lote_activo(self.e, cantidad=10)
        lote.siembra.fecha_siembra = self.hoy - timedelta(days=2)
        lote.siembra.save(update_fields=["fecha_siembra"])
        fds.poner_fuera_de_servicio(
            self.e.agronomo,
            fds.DatosDeFueraDeServicio(
                sector_id=self.germ.pk, motivo="Rotura", fecha=self.hoy, reubicaciones=((lote.pk, self.g2.pk, 6),), causas=((lote.pk, "plaga", ""),)
            ),
        )

    def test_la_consulta_lista_el_fuera_de_servicio_la_reubicacion_y_la_merma_y_el_filtro_los_ofrece(self):
        self.poner()
        respuesta = self.client.get(reverse("produccion:bitacora"), {"invernadero": self.e.invernadero.pk})
        for texto in ("Sector fuera de servicio", "Reubicación de plantas", "Merma", "quedó fuera de servicio", "Reubicación de 6 plantas"):
            self.assertContains(respuesta, texto)
        self.assertContains(respuesta, 'value="fuera_de_servicio"')
        self.assertContains(respuesta, 'value="reubicacion"')

    def test_el_filtro_por_tipo_deja_solo_los_registros_de_ese_tipo(self):
        self.poner()
        respuesta = self.client.get(reverse("produccion:bitacora"), {"invernadero": self.e.invernadero.pk, "tipo": "reubicacion"})
        self.assertContains(respuesta, "Reubicación de 6 plantas")
        self.assertNotContains(respuesta, "quedó fuera de servicio desde")
        self.assertEqual(respuesta.status_code, 200)
