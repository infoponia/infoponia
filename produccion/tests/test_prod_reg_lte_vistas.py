# Pruebas de la pantalla «Registrar lote existente» de `produccion` (PRD-05, paso 4; PROD-REG-LTE). Las vistas solo orquestan: las reglas ya se prueban en
# `test_prod_reg_lte.py`; acá, quién ve qué (D-30), los errores por campo, que el HTML se escapa, el patrón de «Nueva siembra» (D-61: HTMX sin validar, un POST
# común sin JavaScript, «Ver resumen» y «Confirmar» con firma), la acción «Registrar lote existente» solo cuando hay un invernadero disponible, y que la carga
# aparezca bien (sin Capataz) en la lista, el detalle y la ficha. Cliente de prueba de Django.

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contabilidad.models import AsientoContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin, verificar_invariantes_contables
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import EtapaProductiva
from maestros.tests.fabricas import crear_agronomo, crear_sector
from produccion.models import Lote, Siembra
from produccion.servicios import registrantes
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo, lote_de_carga_inicial
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HX = {"HTTP_HX_REQUEST": "true"}
URL = "produccion:registrar_lote_existente"


def hoy():
    return timezone.localdate()


class Base(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        self.e = invernadero_con_produccion()
        self.e.sectores["maduracion_2"] = crear_sector(self.e.invernadero, nombre="Sector maduracion 2", tipo="maduracion", agujeros=100)
        self.gerente = crear_gerente()
        self.url = reverse(URL)
        self.client.force_login(self.e.agronomo)

    def etapa(self, codigo="maduracion"):
        return EtapaProductiva.objects.get(ciclo__variedad=self.e.variedad, tipo_etapa__codigo=codigo).pk

    def carga(self, **cambios):
        datos = {
            "invernadero": self.e.invernadero.pk,
            "variedad": self.e.variedad.pk,
            "etapa": self.etapa(),
            "fecha_siembra": (hoy() - timedelta(days=40)).isoformat(),
            "fecha_ingreso_etapa": (hoy() - timedelta(days=10)).isoformat(),
            "cantidad": "180",
            "costo_estimado": "12000",
            f"sector_{self.e.sectores['maduracion'].pk}": "100",
            f"sector_{self.e.sectores['maduracion_2'].pk}": "80",
        }
        datos.update(cambios)
        return datos

    def calcular(self, **cambios):
        return self.client.post(self.url, {**self.carga(**cambios), "accion": "calcular"})

    def firma_de(self, respuesta):
        return respuesta.context["firma"]


class PermisosPorRolTests(Base):
    """D-30: es del Agrónomo a cargo; el Gerente obtiene 404 (como en «Nueva siembra»), el Capataz 403 y quien no inició sesión va al ingreso."""

    def test_pre_la_pantalla_es_del_agronomo_a_cargo(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_pre_el_gerente_obtiene_404_en_get_y_en_post(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"accion": "calcular"}).status_code, 404)

    def test_pre_el_capataz_obtiene_403(self):
        self.client.force_login(self.e.capataz)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_pre_sin_sesion_se_redirige_al_ingreso(self):
        self.client.logout()
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("iniciar-sesion", respuesta["Location"])

    def test_pre_el_agronomo_de_otro_invernadero_no_puede_cargar_en_el_mio(self):
        """Un Agrónomo ajeno que escribe a mano el invernadero ajeno obtiene el motivo (403) y no escribe nada."""
        self.client.force_login(crear_agronomo(email="ajeno@infoponia.com"))
        respuesta = self.calcular()
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(Lote.objects.count(), 0)


class PasosYEstadosTests(Base):
    def test_paso_2_lista_los_invernaderos_disponibles_y_la_etapa_espera_a_la_variedad(self):
        """Paso 2: el desplegable de invernaderos; la variedad y la etapa están deshabilitadas hasta elegir lo anterior."""
        contenido = self.client.get(self.url).content.decode()
        self.assertIn(self.e.invernadero.nombre_invernadero, contenido)
        self.assertIn("Elegí primero el invernadero", contenido)
        self.assertIn("Elegí primero la variedad", contenido)
        self.assertNotIn("Ver resumen", contenido)

    def test_ext_2a_sin_invernaderos_disponibles_informa_por_que(self):
        """Extensión 2a: con una siembra normal concretada no hay dónde cargar: el estado vacío lo explica y no hay formulario."""
        lote_activo(self.e, cantidad=5)
        contenido = self.client.get(self.url).content.decode()
        self.assertIn("No hay invernaderos donde cargar un lote existente", contenido)
        self.assertIn("siembras por el flujo normal", contenido)
        self.assertNotIn("Ver resumen", contenido)

    def test_pasos_4_y_6_con_todo_elegido_aparecen_los_campos_y_los_sectores_con_sus_libres(self):
        """Paso 4 y 6: elegida la etapa se muestran las fechas, la cantidad, el costo (por defecto 0) y los sectores con sus agujeros libres."""
        contenido = self.client.get(self.url, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "etapa": self.etapa()}).content.decode()
        for texto in ("Fecha de siembra", "Fecha de ingreso a la etapa actual", "Cantidad de plantas", "Costo estimado del lote", "Sector maduracion 2", "(libres: 100)"):
            self.assertIn(texto, contenido)
        self.assertIn('value="0"', contenido)

    def test_ext_7d_sin_sectores_compatibles_informa_que_no_hay_donde_ubicar_el_lote(self):
        """Extensión 7d: sin sectores elegibles para la etapa, la pantalla lo dice y ofrece elegir otra etapa o crear un sector."""
        from maestros.models import SectorProduccion

        SectorProduccion.objects.filter(invernadero=self.e.invernadero, tipo_etapa__codigo="maduracion").update(estado_sector="fuera_de_servicio")
        contenido = self.client.get(self.url, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "etapa": self.etapa()}).content.decode()
        self.assertIn("no hay dónde ubicar el lote", contenido)
        self.assertIn("Fuera de servicio", contenido)

    def test_regla_la_ayuda_de_la_primera_etapa_solo_aparece_en_la_primera(self):
        """Decisión del estudiante (25/11/2026): en la primera etapa, debajo del ingreso, «Suele coincidir con la fecha de siembra» (sin precargar ni validar)."""
        primera = self.client.get(self.url, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "etapa": self.etapa("germinacion")}).content.decode()
        otra = self.client.get(self.url, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "etapa": self.etapa("maduracion")}).content.decode()
        self.assertIn("Suele coincidir con la fecha de siembra", primera)
        self.assertNotIn("Suele coincidir con la fecha de siembra", otra)

    def test_regla_el_html_se_escapa(self):
        """Los nombres que vienen de la base (un sector) se escapan en el formulario."""
        crear_sector(self.e.invernadero, nombre="<b>Peligro</b>", tipo="maduracion", agujeros=10)
        contenido = self.client.get(self.url, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "etapa": self.etapa()}).content.decode()
        self.assertNotIn("<b>Peligro</b>", contenido)
        self.assertIn("&lt;b&gt;Peligro&lt;/b&gt;", contenido)

    def test_regla_con_htmx_solo_se_redibuja_el_bloque_y_sin_validar(self):
        """Interfaz (INV-02): cambiar el invernadero, la variedad o la etapa devuelve solo el formulario y NO valida lo escrito."""
        datos = self.carga(cantidad="0", costo_estimado="-3")
        respuesta = self.client.post(self.url, {**datos, "accion": "actualizar"}, **HX)
        contenido = respuesta.content.decode()
        self.assertNotIn("<html", contenido)
        self.assertIn('id="lote-existente-form"', contenido)
        self.assertNotIn('class="err"', contenido)
        self.assertEqual(Lote.objects.count(), 0)

    def test_regla_sin_javascript_cada_boton_es_un_post_comun_con_su_accion(self):
        """Sin JavaScript: «Continuar» (noscript), «Ver resumen» y «Confirmar» son botones con su `accion`."""
        pagina = self.client.get(self.url).content.decode()
        self.assertIn('value="actualizar"', pagina)
        con_todo = self.client.get(self.url, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "etapa": self.etapa()}).content.decode()
        self.assertIn('value="calcular"', con_todo)
        self.assertNotIn('value="confirmar"', con_todo)

    def test_regla_elegir_antes_de_seguir_si_falta_el_invernadero_la_variedad_o_la_etapa(self):
        """Un «Ver resumen» sin elegir etapa no calcula nada: avisa que hay que elegir."""
        respuesta = self.client.post(self.url, {**self.carga(etapa=""), "accion": "calcular"})
        self.assertIn("Elegí el invernadero, la variedad y la etapa antes de seguir", respuesta.content.decode())


class ResumenYConfirmacionTests(Base):
    def test_paso_8_ver_resumen_muestra_todo_con_el_asiento_y_no_escribe(self):
        """Paso 8: el resumen trae la variedad, la etapa, las cantidades, el costo estimado y por planta, la ocupación por sector con lo que queda libre y
        el asiento (Debe Productos en Proceso / Haber Capital Inicial); no escribe."""
        respuesta = self.calcular()
        contenido = respuesta.content.decode()
        self.assertIsNotNone(respuesta.context["resumen"])
        for texto in ("Resumen del lote", "Maduración", "180", "Productos en Proceso", "Capital Inicial", "quedan 0 libres", "quedan 20 libres", "Confirmar registro"):
            self.assertIn(texto, contenido)
        self.assertEqual((Lote.objects.count(), Siembra.objects.count(), AsientoContable.objects.count()), (0, 0, 0))

    def test_paso_8_con_costo_cero_el_resumen_dice_que_no_hay_asiento(self):
        """H11: con costo $0 el resumen lo avisa."""
        contenido = self.calcular(costo_estimado="0").content.decode()
        self.assertIn("con costo $0 no se registra ningún asiento", contenido)

    def test_ext_5_los_errores_van_debajo_de_su_campo(self):
        """Extensiones 5a, 5b y 5c: cada error con su campo, y no hay resumen ni confirmación."""
        for cambios, campo in (
            ({"cantidad": "0"}, "cantidad"),
            ({"costo_estimado": "-1"}, "costo_estimado"),
            ({"costo_estimado": "abc"}, "costo_estimado"),
            ({"fecha_siembra": (hoy() + timedelta(days=1)).isoformat()}, "fecha_siembra"),
            ({"fecha_ingreso_etapa": (hoy() + timedelta(days=1)).isoformat()}, "fecha_ingreso_etapa"),
            ({"fecha_siembra": ""}, "fecha_siembra"),
        ):
            respuesta = self.calcular(**cambios)
            self.assertIn(campo, respuesta.context["errores"], cambios)
            self.assertIsNone(respuesta.context["resumen"])
            self.assertNotIn("Confirmar registro", respuesta.content.decode())

    def test_ext_7_los_errores_de_la_distribucion_se_muestran_con_los_libres(self):
        """Extensiones 7a y 7b: la suma que no cierra y los agujeros que no alcanzan se muestran debajo de la distribución."""
        sector = self.e.sectores["maduracion"].pk
        falta = self.calcular(cantidad="180", **{f"sector_{sector}": "100", f"sector_{self.e.sectores['maduracion_2'].pk}": ""}).content.decode()
        self.assertIn("faltan ubicar 80", falta)
        demasiado = self.calcular(cantidad="150", **{f"sector_{sector}": "150", f"sector_{self.e.sectores['maduracion_2'].pk}": ""}).content.decode()
        self.assertIn("100 agujeros libres", demasiado)

    def test_ext_5b_una_cantidad_en_un_sector_que_no_es_un_entero_se_rechaza(self):
        """Un sector con un texto en vez de un número lo rechaza el servicio (`cantidad_invalida`), no un 500."""
        respuesta = self.calcular(**{f"sector_{self.e.sectores['maduracion'].pk}": "diez"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("distribucion", respuesta.context["errores"])

    def test_paso_10_confirmar_registra_redirige_y_muestra_la_confirmacion_con_sus_enlaces(self):
        """Pasos 10 y 11: «Confirmar registro» con la firma vigente escribe todo y vuelve con el lote registrado, su identificador y el acceso a planificar
        su transición."""
        firma = self.firma_de(self.calcular())
        respuesta = self.client.post(self.url, {**self.carga(), "accion": "confirmar", "firma": firma})
        self.assertEqual(respuesta.status_code, 302)
        lote = Lote.objects.get()
        self.assertEqual(respuesta["Location"], f"{self.url}?registrado={lote.pk}")
        pagina = self.client.get(respuesta["Location"])
        contenido = pagina.content.decode()
        self.assertIn(lote.codigo, contenido)
        self.assertIn("quedó registrado", contenido)
        self.assertIn(f"{reverse('produccion:nueva_transicion')}?lote={lote.pk}", contenido)
        self.assertEqual(AsientoContable.objects.count(), 1)
        verificar_invariantes_contables()

    def test_regla_si_cambio_un_dato_despues_del_resumen_no_se_confirma_lo_que_no_vio(self):
        """Firma: si se cambia un dato y se confirma sin recalcular (posible sin JavaScript), no se registra: se vuelve a mostrar el resumen nuevo."""
        firma = self.firma_de(self.calcular())
        respuesta = self.client.post(self.url, {**self.carga(costo_estimado="99999"), "accion": "confirmar", "firma": firma})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Cambiaste un dato después de ver el resumen", respuesta.content.decode())
        self.assertEqual(Lote.objects.count(), 0)

    def test_regla_la_confirmacion_solo_se_muestra_de_un_lote_de_un_invernadero_a_cargo(self):
        """El `?registrado=` de un lote de otro Agrónomo no muestra nada (no se revela que existe)."""
        otro = invernadero_con_produccion(nombre="Otro", sufijo="2")
        ajeno = lote_de_carga_inicial(otro, cantidad=5, etapa="maduracion")
        contenido = self.client.get(self.url, {"registrado": ajeno.pk}).content.decode()
        self.assertNotIn(ajeno.codigo, contenido)
        self.assertNotIn("quedó registrado", contenido)

    def test_regla_despues_de_concretar_una_siembra_normal_la_pantalla_deja_de_ofrecer_el_invernadero(self):
        """Hecho cuando de PRD-05: concretada una siembra normal, la acción desaparece para ese invernadero (y una carga a mano se rechaza)."""
        firma = self.firma_de(self.calcular())
        lote_activo(self.e, cantidad=5)
        respuesta = self.client.post(self.url, {**self.carga(), "accion": "confirmar", "firma": firma})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("invernadero", respuesta.context["errores"])
        self.assertEqual(Lote.objects.filter(siembra__tipo_siembra="carga_inicial").count(), 0)


class AccionYPantallasDeLaCargaTests(Base):
    def test_regla_la_accion_se_ve_solo_si_hay_un_invernadero_disponible(self):
        """La acción «Registrar lote existente» de «Producción» se ve para el Agrónomo con un invernadero disponible, no para el Gerente ni cuando ya hay
        una siembra normal concretada."""
        self.assertIn("Registrar lote existente", self.client.get(reverse("produccion:ordenes")).content.decode())
        self.client.force_login(self.gerente)
        self.assertNotIn("Registrar lote existente", self.client.get(reverse("produccion:ordenes")).content.decode())
        self.client.force_login(self.e.agronomo)
        lote_activo(self.e, cantidad=5)
        self.assertNotIn("Registrar lote existente", self.client.get(reverse("produccion:ordenes")).content.decode())

    def test_regla_la_pestana_de_lotes_ofrece_la_accion_solo_si_el_invernadero_esta_disponible(self):
        """La pestaña «Lotes activos» de la ficha ofrece la acción para ese invernadero mientras está disponible, con el invernadero ya elegido."""
        html = registrantes.pestana_de_lotes(self.e.agronomo, self.e.invernadero)
        self.assertIn("Registrar lote existente", html)
        self.assertIn(f"?invernadero={self.e.invernadero.pk}", html)
        self.assertIsNone(registrantes.pestana_de_lotes(self.e.capataz, self.e.invernadero))
        self.assertNotIn("Registrar lote existente", registrantes.pestana_de_lotes(self.gerente, self.e.invernadero))
        lote_activo(self.e, cantidad=5)
        self.assertNotIn("Registrar lote existente", registrantes.pestana_de_lotes(self.e.agronomo, self.e.invernadero))

    def test_regla_el_enlace_de_la_pestana_deja_el_invernadero_elegido(self):
        """`?invernadero=` deja elegido el invernadero y habilita la variedad."""
        contenido = self.client.get(self.url, {"invernadero": self.e.invernadero.pk}).content.decode()
        self.assertIn(f'<option value="{self.e.invernadero.pk}" selected>', contenido)
        self.assertIn("Seleccionar…", contenido)

    def test_regla_la_lista_el_detalle_y_la_bandeja_no_se_rompen_con_una_siembra_sin_capataz(self):
        """D-92 punto 12 (L1): la orden de la carga no tiene Capataz. La lista (Agrónomo y Gerente) la muestra como «carga inicial», el detalle dice «Sin
        Capataz» y no aparece en la bandeja del Capataz."""
        lote = lote_de_carga_inicial(self.e, cantidad=30, etapa="maduracion")
        for cuenta in (self.e.agronomo, self.gerente):
            self.client.force_login(cuenta)
            lista = self.client.get(reverse("produccion:ordenes"))
            self.assertEqual(lista.status_code, 200)
            self.assertIn("carga inicial", lista.content.decode())
            detalle = self.client.get(reverse("produccion:orden", args=[lote.siembra_id]))
            self.assertEqual(detalle.status_code, 200)
            self.assertIn("Sin Capataz (carga inicial)", detalle.content.decode())
        self.client.force_login(self.e.capataz)
        self.assertEqual(self.client.get(reverse("produccion:bandeja")).status_code, 200)
        self.assertNotIn(lote.siembra.codigo, self.client.get(reverse("produccion:bandeja")).content.decode())
        self.assertEqual(self.client.get(reverse("produccion:orden", args=[lote.siembra_id])).status_code, 404)

    def test_regla_cancelar_la_orden_de_una_carga_inicial_avisa_y_no_rompe(self):
        """La orden de la carga ya está concretada: «Cancelar orden» avisa que no está pendiente y vuelve a la lista (sin 500)."""
        lote = lote_de_carga_inicial(self.e, cantidad=30, etapa="maduracion")
        respuesta = self.client.post(reverse("produccion:cancelar", args=[lote.siembra_id]), {"motivo": "Prueba"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Lote.objects.get(pk=lote.pk).estado_lote, "activo")

    def test_regla_la_ficha_del_lote_cargado_aparece_en_los_lotes_activos_con_su_entrada(self):
        """El lote cargado aparece en la pestaña «Lotes activos» con la fecha de ingreso cargada como entrada a la etapa."""
        lote_de_carga_inicial(self.e, cantidad=30, etapa="maduracion", ingreso=hoy() - timedelta(days=4))
        html = registrantes.pestana_de_lotes(self.e.agronomo, self.e.invernadero)
        self.assertIn((hoy() - timedelta(days=4)).strftime("%d/%m/%Y"), html)
        self.assertIn("Maduración", html)
