# Pruebas de las pantallas de PRD-03 (paso 7): «Registrar en bitácora», «Registrar merma», «Registrar aplicación», «Otro evento», la consulta de la bitácora (página y
# pestaña de la ficha del invernadero) y las entradas de menú según el rol. Las vistas solo orquestan: las reglas de negocio ya se prueban en los servicios; acá, quién
# ve qué (D-30), los 404 donde corresponde, los errores por campo, que el HTML se escapa, que la respuesta del Capataz NO contiene valores en dinero, que «Ver resumen» no
# escribe y que todo funciona sin JavaScript (un POST común) y con HTMX (solo el bloque que cambia, sin validar). Cliente de prueba de Django.

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.menu import menu_de
from core.models import RegistroAuditoria, Usuario
from core.tests.fabricas import crear_gerente
from inventario.models import LoteInsumo, TipoInsumo
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote as lote_de_insumo, tipo_de_insumo
from maestros.extensiones import pestanas_de_invernadero
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_invernadero
from produccion.models import AplicacionInsumos, Bitacora, Lote, Merma
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo

HX = {"HTTP_HX_REQUEST": "true"}
D = Decimal


def hoy():
    return timezone.localdate()


class Base(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = invernadero_con_produccion()
        self.gerente = crear_gerente()
        self.lote = lote_activo(self.e, cantidad=50, sector="germinacion", costo="100.00")
        self.sector = self.e.sectores["germinacion"]
        tipo = TipoInsumo.objects.filter(nombre_tipo_insumo="Cat costo").first() or tipo_de_insumo("Cat costo", consumo="como_costo_de_los_lotes")
        self.abono = existencia(insumo("Abono verde", tipo=tipo, unidad="kg"), self.e.invernadero, precio="4.00")
        self.lote_de_abono = lote_de_insumo(self.abono, 30)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def merma(self, **cambios):
        datos = {"invernadero": self.e.invernadero.pk, "lote": self.lote.pk, f"cant_{self.sector.pk}": "5", "causa": "plaga", "descripcion": ""}
        datos.update(cambios)
        return datos

    def aplicacion(self, **cambios):
        datos = {"invernadero": self.e.invernadero.pk, "alcance": "todo", f"cantidad_{self.abono.pk}": "7", "descripcion": ""}
        datos.update(cambios)
        return datos


class PermisosPorRolTests(Base):
    """D-30: el Agrónomo a cargo y el Capataz asignado registran; el Gerente solo consulta la bitácora (en lo demás, 404); el Capataz no consulta."""

    RUTAS_DE_REGISTRO = ("produccion:registrar", "produccion:registrar_merma", "produccion:registrar_aplicacion", "produccion:registrar_evento")

    def test_el_agronomo_y_el_capataz_abren_las_pantallas_de_registro(self):
        for cuenta in (self.e.agronomo, self.e.capataz):
            self.entrar(cuenta)
            for ruta in self.RUTAS_DE_REGISTRO:
                self.assertEqual(self.client.get(reverse(ruta)).status_code, 200, (cuenta, ruta))

    def test_el_gerente_recibe_404_en_las_pantallas_de_registro_y_el_anonimo_va_al_ingreso(self):
        self.entrar(self.gerente)
        for ruta in self.RUTAS_DE_REGISTRO:
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 404, ruta)
            if ruta != "produccion:registrar":  # el menú solo admite GET
                self.assertEqual(self.client.post(reverse(ruta), {}).status_code, 404, ruta)
        self.client.logout()
        for ruta in self.RUTAS_DE_REGISTRO + ("produccion:bitacora",):
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 302, ruta)

    def test_otro_rol_recibe_403_en_registrar(self):
        """Un rol que no usa la pantalla (Vendedor, por ejemplo) no entra: 403 del decorador de roles."""
        from maestros.tests.fabricas import crear_vendedor

        self.entrar(crear_vendedor())
        self.assertEqual(self.client.get(reverse("produccion:registrar_merma")).status_code, 403)

    def test_la_bitacora_la_consultan_el_agronomo_y_el_gerente_y_el_capataz_no(self):
        for cuenta, estado in ((self.e.agronomo, 200), (self.gerente, 200), (self.e.capataz, 403)):
            self.entrar(cuenta)
            self.assertEqual(self.client.get(reverse("produccion:bitacora")).status_code, estado, cuenta)

    def test_un_invernadero_inexistente_es_404_y_uno_ajeno_es_403_sin_mostrar_datos(self):
        self.entrar(self.e.capataz)
        self.assertEqual(self.client.get(reverse("produccion:registrar_merma"), {"invernadero": 999999}).status_code, 404)
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com"))
        self.assertEqual(self.client.get(reverse("produccion:registrar_merma"), {"invernadero": ajeno.pk}).status_code, 403)
        self.entrar(self.e.agronomo)
        self.assertEqual(self.client.get(reverse("produccion:bitacora"), {"invernadero": ajeno.pk}).status_code, 403)
        self.assertEqual(self.client.get(reverse("produccion:bitacora"), {"invernadero": 999999}).status_code, 404)

    def test_las_entradas_de_menu_segun_el_rol(self):
        """El Gerente tiene «Bitácora» en el menú (solo consulta); el Agrónomo entra desde «Producción»; el Capataz, desde su bandeja (no tiene menú lateral)."""
        textos = lambda rol: [texto for texto, _, _ in menu_de(rol)]
        self.assertIn("Bitácora", textos(Usuario.Rol.GERENTE))
        self.assertNotIn("Bitácora", textos(Usuario.Rol.AGRONOMO))
        self.assertNotIn("Bitácora", textos(Usuario.Rol.CAPATAZ))
        self.entrar(self.e.agronomo)
        pagina = self.client.get(reverse("produccion:ordenes")).content.decode()
        self.assertIn(reverse("produccion:registrar"), pagina)
        self.assertIn(reverse("produccion:bitacora"), pagina)
        self.entrar(self.e.capataz)
        bandeja = self.client.get(reverse("produccion:bandeja")).content.decode()
        for ruta in ("produccion:registrar_merma", "produccion:registrar_aplicacion", "produccion:registrar_evento"):
            self.assertIn(reverse(ruta), bandeja)


class RegistrarMermaTests(Base):
    def test_ver_resumen_no_escribe_y_confirmar_registra_la_merma_y_vuelve_a_la_bandeja(self):
        """Flujo del Capataz: «Ver resumen» valida y no escribe; «Confirmar» registra y vuelve a su bandeja."""
        self.entrar(self.e.capataz)
        url = reverse("produccion:registrar_merma")
        respuesta = self.client.post(url, {**self.merma(), "accion": "calcular"})
        self.assertContains(respuesta, "Resumen")
        self.assertFalse(Merma.objects.exists())
        firma = respuesta.context["firma"]
        confirmada = self.client.post(url, {**self.merma(), "accion": "confirmar", "firma": firma, "visto_cantidad": "50", "visto_ocupados": f"{self.sector.pk}:50"})
        self.assertRedirects(confirmada, reverse("produccion:bandeja"))
        self.assertEqual(Merma.objects.get().cant_merma, 5)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_merma").count(), 1)

    def test_el_agronomo_vuelve_a_la_bitacora_del_invernadero(self):
        self.entrar(self.e.agronomo)
        url = reverse("produccion:registrar_merma")
        firma = self.client.post(url, {**self.merma(), "accion": "calcular"}).context["firma"]
        confirmada = self.client.post(url, {**self.merma(), "accion": "confirmar", "firma": firma})
        self.assertRedirects(confirmada, f"{reverse('produccion:bitacora')}?invernadero={self.e.invernadero.pk}")

    def test_un_cambio_despues_del_resumen_pide_revisarlo_de_nuevo_sin_registrar(self):
        """Confirmar con una firma que ya no coincide (sin JavaScript se puede cambiar un dato después del resumen): no registra y vuelve a mostrar el resumen."""
        self.entrar(self.e.capataz)
        url = reverse("produccion:registrar_merma")
        firma = self.client.post(url, {**self.merma(), "accion": "calcular"}).context["firma"]
        respuesta = self.client.post(url, {**self.merma(**{f"cant_{self.sector.pk}": "6"}), "accion": "confirmar", "firma": firma})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cambiaste un dato después de ver el resumen")
        self.assertFalse(Merma.objects.exists())

    def test_los_errores_salen_debajo_de_cada_campo(self):
        """Extensiones 8a, 8b y 8c: el error de un sector va debajo de su campo; el total en cero y la causa, en los suyos."""
        self.entrar(self.e.capataz)
        url = reverse("produccion:registrar_merma")
        pasado = self.client.post(url, {**self.merma(**{f"cant_{self.sector.pk}": "51"}), "accion": "calcular"})
        self.assertEqual(list(pasado.context["errores"]), [f"sector_{self.sector.pk}"])
        self.assertContains(pasado, "entre 0 y 50")
        self.assertEqual(list(self.client.post(url, {**self.merma(**{f"cant_{self.sector.pk}": ""}), "accion": "calcular"}).context["errores"]), ["cantidad"])
        self.assertEqual(list(self.client.post(url, {**self.merma(causa=""), "accion": "calcular"}).context["errores"]), ["causa"])
        self.assertFalse(Merma.objects.exists())

    def test_ext_10d_un_lote_que_cambio_se_informa_y_se_vuelve_a_cargar(self):
        """Extensión 10d: otro registro bajó el lote entre el resumen y la confirmación: `cambio_simultaneo` en pantalla (con lo vigente), sin 500 y sin registrar."""
        self.entrar(self.e.capataz)
        url = reverse("produccion:registrar_merma")
        firma = self.client.post(url, {**self.merma(), "accion": "calcular"}).context["firma"]
        Lote.objects.filter(pk=self.lote.pk).update(cantidad_actual=40)
        respuesta = self.client.post(url, {**self.merma(), "accion": "confirmar", "firma": firma, "visto_cantidad": "50", "visto_ocupados": f"{self.sector.pk}:50"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "cambió")
        self.assertFalse(Merma.objects.exists())

    def test_sin_lotes_activos_el_formulario_queda_deshabilitado_con_su_motivo(self):
        """Extensión 4b: sin lotes activos, el formulario informa el motivo y no ofrece enviar."""
        otro = crear_invernadero("Vacio", agronomo=self.e.agronomo)
        self.entrar(self.e.agronomo)
        respuesta = self.client.get(reverse("produccion:registrar_merma"), {"invernadero": otro.pk})
        self.assertContains(respuesta, "No hay lotes activos en este invernadero")
        self.assertNotContains(respuesta, "Ver resumen")

    def test_el_selector_de_invernadero_redibuja_solo_el_bloque_sin_validar_y_sin_mover_el_scroll(self):
        """.claude/rules/interfaz.md: el selector dependiente cambia por HTMX con `hx-swap="innerHTML show:none"` (en el contenedor) y respuesta parcial, sin validar;
        con respaldo sin JavaScript (el botón «Continuar» y los POST comunes)."""
        self.entrar(self.e.capataz)
        pagina = self.client.get(reverse("produccion:registrar_merma")).content.decode()
        self.assertIn('hx-swap="innerHTML show:none"', pagina)
        self.assertIn('data-sin-envio-en-curso', pagina)
        self.assertIn("<noscript>", pagina)
        parcial = self.client.post(reverse("produccion:registrar_merma"), {"invernadero": self.e.invernadero.pk, "accion": "actualizar"}, **HX)
        self.assertNotContains(parcial, "<html")
        self.assertContains(parcial, self.lote.codigo)
        self.assertEqual(parcial.context["errores"], {})
        self.assertNotContains(parcial, 'class="err"')

    def test_la_descripcion_se_escapa(self):
        """Todo lo que escribe una persona se escapa en el resumen."""
        self.entrar(self.e.capataz)
        respuesta = self.client.post(reverse("produccion:registrar_merma"), {**self.merma(descripcion="<script>alert(1)</script>"), "accion": "calcular"})
        self.assertNotContains(respuesta, "<script>alert(1)</script>")
        self.assertContains(respuesta, "&lt;script&gt;")

    def test_el_gerente_no_puede_registrar_ni_con_un_post(self):
        self.entrar(self.gerente)
        self.assertEqual(self.client.post(reverse("produccion:registrar_merma"), {**self.merma(), "accion": "confirmar", "firma": "x"}).status_code, 404)
        self.assertFalse(Merma.objects.exists())


class RegistrarAplicacionTests(Base):
    def test_el_capataz_ve_los_insumos_y_cantidades_pero_ningun_valor_en_dinero(self):
        """Requisito del paso 4: la respuesta del Capataz no contiene valores en dinero, destinos, reparto ni avisos de stock, en ningún paso."""
        self.entrar(self.e.capataz)
        url = reverse("produccion:registrar_aplicacion")
        formulario = self.client.get(url, {"invernadero": self.e.invernadero.pk}).content.decode()
        resumen = self.client.post(url, {**self.aplicacion(**{f"cantidad_{self.abono.pk}": "40"}), "accion": "calcular"}).content.decode()
        for pagina in (formulario, resumen):
            self.assertNotIn("$", pagina)
            for monto in ("4.00", "4,00", "160.00", "160,00", "28,00"):
                self.assertNotIn(monto, pagina)
            self.assertNotIn("costo de los lotes", pagina)
            self.assertNotIn("sin lote", pagina)
            self.assertNotIn("negativo", pagina)
        self.assertIn("Abono verde", resumen)

    def test_el_agronomo_ve_el_valor_el_destino_el_reparto_y_el_faltante(self):
        """Pasos 6 y 10: al Agrónomo se le presenta además el destino, el valor, el reparto entre los lotes de plantas y lo que queda sin lote."""
        self.entrar(self.e.agronomo)
        url = reverse("produccion:registrar_aplicacion")
        formulario = self.client.get(url, {"invernadero": self.e.invernadero.pk}).content.decode()
        self.assertIn("va al costo de los lotes", formulario)
        resumen = self.client.post(url, {**self.aplicacion(**{f"cantidad_{self.abono.pk}": "40"}), "accion": "calcular"}).content.decode()
        self.assertIn("$160,00", resumen)
        self.assertIn("costo de los lotes", resumen)
        self.assertIn("sin lote", resumen)
        self.assertIn(self.lote.codigo, resumen)

    def test_ver_resumen_no_escribe_y_confirmar_registra_y_deja_un_solo_registro_de_auditoria(self):
        """Flujo: «Ver resumen» no escribe; «Confirmar» registra la aplicación, descuenta el stock y vuelve a la bandeja (Capataz)."""
        self.entrar(self.e.capataz)
        url = reverse("produccion:registrar_aplicacion")
        respuesta = self.client.post(url, {**self.aplicacion(), "accion": "calcular"})
        self.assertFalse(AplicacionInsumos.objects.exists())
        confirmada = self.client.post(
            url,
            {**self.aplicacion(), "accion": "confirmar", "firma": respuesta.context["firma"],
             "plantas_vistas": respuesta.context["plantas_vistas"], f"vistos_{self.abono.pk}": respuesta.context["vistos"][self.abono.pk]},
        )
        self.assertRedirects(confirmada, reverse("produccion:bandeja"))
        self.assertEqual(AplicacionInsumos.objects.count(), 1)
        self.assertEqual(LoteInsumo.objects.get(pk=self.lote_de_abono.pk).cantidad_disponible, D("23"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_aplicacion").count(), 1)

    def test_el_resumen_trae_lo_que_la_persona_vio_para_la_extension_12a(self):
        """Extensión 12a: el resumen guarda las plantas de los lotes del alcance y los lotes de insumo vistos; si cambian antes de confirmar, la pantalla lo informa y no registra."""
        self.entrar(self.e.capataz)
        url = reverse("produccion:registrar_aplicacion")
        resumen = self.client.post(url, {**self.aplicacion(), "accion": "calcular"})
        LoteInsumo.objects.filter(pk=self.lote_de_abono.pk).update(cantidad_disponible=D("12"))
        respuesta = self.client.post(
            url,
            {**self.aplicacion(), "accion": "confirmar", "firma": resumen.context["firma"],
             "plantas_vistas": resumen.context["plantas_vistas"], f"vistos_{self.abono.pk}": resumen.context["vistos"][self.abono.pk]},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "cambió")
        self.assertFalse(AplicacionInsumos.objects.exists())

    def test_los_errores_salen_debajo_de_su_campo(self):
        """Extensiones 6a, 8a y 10a: sectores sin marcar, cantidad inválida y ningún insumo, cada uno en su lugar."""
        self.entrar(self.e.agronomo)
        url = reverse("produccion:registrar_aplicacion")
        self.assertEqual(list(self.client.post(url, {**self.aplicacion(alcance="sectores"), "accion": "calcular"}).context["errores"]), ["sector_ids"])
        self.assertEqual(list(self.client.post(url, {**self.aplicacion(**{f"cantidad_{self.abono.pk}": "abc"}), "accion": "calcular"}).context["errores"]), [f"cantidad_{self.abono.pk}"])
        self.assertEqual(list(self.client.post(url, {**self.aplicacion(**{f"cantidad_{self.abono.pk}": ""}), "accion": "calcular"}).context["errores"]), ["general"])
        self.assertFalse(AplicacionInsumos.objects.exists())

    def test_sin_insumos_aplicables_informa_y_no_ofrece_enviar(self):
        """Extensión 6b: el invernadero sin insumos que admitan consumo directo lo informa y termina sin registrar."""
        vacio = crear_invernadero("Vacio", agronomo=self.e.agronomo)
        self.entrar(self.e.agronomo)
        respuesta = self.client.get(reverse("produccion:registrar_aplicacion"), {"invernadero": vacio.pk})
        self.assertContains(respuesta, "no tiene insumos para aplicar")
        self.assertNotContains(respuesta, "Ver resumen")

    def test_el_invernadero_nunca_se_elige_solo_y_el_selector_es_dependiente_sin_validar(self):
        """Regla «Quién lo registra»: el Sistema nunca elige el invernadero solo, aunque haya uno; con HTMX el selector redibuja solo el bloque, sin validar."""
        self.entrar(self.e.capataz)
        pagina = self.client.get(reverse("produccion:registrar_aplicacion"))
        self.assertIsNone(pagina.context["invernadero_id"])
        self.assertContains(pagina, 'hx-swap="innerHTML show:none"')
        parcial = self.client.post(reverse("produccion:registrar_aplicacion"), {"invernadero": self.e.invernadero.pk, "accion": "actualizar"}, **HX)
        self.assertNotContains(parcial, "<html")
        self.assertContains(parcial, "Abono verde")
        self.assertEqual(parcial.context["errores"], {})

    def test_la_descripcion_y_los_nombres_se_escapan(self):
        self.entrar(self.e.agronomo)
        respuesta = self.client.post(reverse("produccion:registrar_aplicacion"), {**self.aplicacion(descripcion="<b>x</b>"), "accion": "calcular"})
        self.assertNotContains(respuesta, "<b>x</b>")
        self.assertContains(respuesta, "&lt;b&gt;x&lt;/b&gt;")


class RegistrarEventoTests(Base):
    def test_con_un_solo_invernadero_viene_elegido_y_se_registra_sin_alertas(self):
        """Regla 1: con un solo invernadero viene elegido; «Registrar evento» escribe y vuelve (Capataz: a la bandeja)."""
        self.entrar(self.e.capataz)
        url = reverse("produccion:registrar_evento")
        self.assertContains(self.client.get(url), 'name="invernadero" value="%d"' % self.e.invernadero.pk)
        confirmada = self.client.post(url, {"accion": "confirmar", "descripcion": "Corte de energía", "lote": self.lote.pk})
        self.assertRedirects(confirmada, reverse("produccion:bandeja"))
        evento = Bitacora.objects.get(tipo_evento="otro_evento")
        self.assertEqual((evento.lote_id, evento.descripcion_evento), (self.lote.pk, "Corte de energía"))

    def test_los_errores_de_la_descripcion_salen_debajo_del_campo(self):
        """Regla 2: la descripción es obligatoria y de hasta 500 caracteres."""
        self.entrar(self.e.agronomo)
        url = reverse("produccion:registrar_evento")
        vacia = self.client.post(url, {"accion": "confirmar", "invernadero": self.e.invernadero.pk, "descripcion": ""})
        self.assertEqual(list(vacia.context["errores"]), ["descripcion"])
        larga = self.client.post(url, {"accion": "confirmar", "invernadero": self.e.invernadero.pk, "descripcion": "a" * 501})
        self.assertContains(larga, "hasta 500 caracteres")
        self.assertFalse(Bitacora.objects.filter(tipo_evento="otro_evento").exists())

    def test_la_descripcion_se_escapa_en_la_pantalla_y_en_la_bitacora(self):
        self.entrar(self.e.agronomo)
        self.client.post(reverse("produccion:registrar_evento"), {"accion": "confirmar", "invernadero": self.e.invernadero.pk, "descripcion": "<script>alert(1)</script>"})
        pagina = self.client.get(reverse("produccion:bitacora"), {"invernadero": self.e.invernadero.pk})
        self.assertNotContains(pagina, "<script>alert(1)</script>")
        self.assertContains(pagina, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_con_varios_invernaderos_el_selector_redibuja_lotes_y_sectores_sin_validar(self):
        otro = crear_invernadero("Otro", agronomo=self.e.agronomo)
        self.entrar(self.e.agronomo)
        parcial = self.client.post(reverse("produccion:registrar_evento"), {"invernadero": self.e.invernadero.pk, "accion": "actualizar", "descripcion": ""}, **HX)
        self.assertNotContains(parcial, "<html")
        self.assertContains(parcial, self.lote.codigo)
        self.assertEqual(parcial.context["errores"], {})
        self.assertContains(self.client.get(reverse("produccion:registrar_evento")), otro.nombre_invernadero)

    def test_no_existen_vistas_de_edicion_ni_de_baja_de_un_registro_de_bitacora(self):
        """Regla 5: ninguna ruta nueva edita ni borra; el único camino es registrar otro evento (la guarda de `test_prod_reg_evt` recorre todas las rutas)."""
        for ruta in ("produccion:registrar_evento", "produccion:bitacora"):
            self.assertEqual(reverse(ruta).count("editar") + reverse(ruta).count("eliminar") + reverse(ruta).count("borrar"), 0)
        evento = Bitacora.objects.create(
            invernadero=self.e.invernadero, tipo_evento="otro_evento", fecha_bitacora=hoy(), hora_bitacora=timezone.localtime().time(), descripcion_evento="X"
        )
        self.entrar(self.e.agronomo)
        for sufijo in ("editar", "eliminar", "borrar", "baja"):
            self.assertEqual(self.client.post(f"/produccion/bitacora/{evento.pk}/{sufijo}/").status_code, 404)


class ConsultaDeBitacoraTests(Base):
    def registrar_un_evento(self, descripcion="Riego revisado", **extra):
        return Bitacora.objects.create(
            invernadero=self.e.invernadero, tipo_evento="otro_evento", fecha_bitacora=extra.pop("dia", hoy()), hora_bitacora=extra.pop("hora", timezone.localtime().time()),
            descripcion_evento=descripcion, responsable=self.e.capataz, **extra,
        )

    def test_el_agronomo_y_el_gerente_ven_la_bitacora_con_un_invernadero_ya_elegido_si_hay_uno_solo(self):
        """Regla 1: si el actor tiene un solo invernadero, viene elegido."""
        self.registrar_un_evento()
        self.entrar(self.e.agronomo)
        self.assertContains(self.client.get(reverse("produccion:bitacora")), "Riego revisado")

    def test_los_filtros_se_combinan_y_quitar_filtros_vuelve_a_todo(self):
        """Reglas 6 y 8: filtros combinados (GET, sin JavaScript); sin coincidencias, se informa y se ofrece «Quitar filtros»."""
        self.registrar_un_evento("Riego revisado")
        self.registrar_un_evento("Corte de luz")
        self.entrar(self.e.agronomo)
        url = reverse("produccion:bitacora")
        uno = self.client.get(url, {"invernadero": self.e.invernadero.pk, "q": "corte", "tipo": "otro_evento"})
        self.assertContains(uno, "Corte de luz")
        self.assertNotContains(uno, "Riego revisado")
        ninguno = self.client.get(url, {"invernadero": self.e.invernadero.pk, "q": "zzz"})
        self.assertContains(ninguno, "Ningún registro coincide con los filtros")
        self.assertContains(ninguno, "quitá los filtros")
        self.assertContains(self.client.get(url, {"invernadero": self.e.invernadero.pk}), "Riego revisado")

    def test_con_htmx_solo_se_redibuja_el_bloque_de_resultados(self):
        """Interfaz: cada filtro reemplaza solo los resultados, sin validar."""
        self.registrar_un_evento()
        self.entrar(self.e.agronomo)
        parcial = self.client.get(reverse("produccion:bitacora"), {"invernadero": self.e.invernadero.pk, "q": "riego"}, **HX)
        self.assertNotContains(parcial, "<html")
        self.assertContains(parcial, "Riego revisado")

    def test_un_tipo_que_no_se_ofrece_no_rompe_la_pantalla(self):
        """Regla 5: un tipo inventado en la URL no da un 500: se muestra sin filtros y con el aviso."""
        self.registrar_un_evento()
        self.entrar(self.e.agronomo)
        respuesta = self.client.get(reverse("produccion:bitacora"), {"invernadero": self.e.invernadero.pk, "tipo": "inventado"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ese tipo de evento no existe")
        self.assertContains(respuesta, "Riego revisado")

    def test_la_pestana_de_la_ficha_la_ven_el_agronomo_y_el_gerente_y_el_capataz_no(self):
        """Pestaña «Bitácora»: el Agrónomo a cargo y el Gerente la ven; el Capataz no. Solo el Agrónomo tiene los botones de registro, con el invernadero ya elegido."""
        self.registrar_un_evento()
        claves = lambda actor: {p.clave: p for p in pestanas_de_invernadero(actor, self.e.invernadero)}
        agronomo, gerente, capataz = claves(self.e.agronomo), claves(self.gerente), claves(self.e.capataz)
        self.assertIn("bitacora", agronomo)
        self.assertIn("bitacora", gerente)
        self.assertNotIn("bitacora", capataz)
        self.assertIn("Riego revisado", agronomo["bitacora"].html)
        self.assertIn(f"{reverse('produccion:registrar_evento')}?invernadero={self.e.invernadero.pk}", agronomo["bitacora"].html)
        self.assertIn(f"{reverse('produccion:registrar_aplicacion')}?invernadero={self.e.invernadero.pk}", agronomo["bitacora"].html)
        self.assertNotIn(reverse("produccion:registrar_evento"), gerente["bitacora"].html)

    def test_la_pestana_de_un_invernadero_dado_de_baja_sigue_mostrando_el_historial_sin_botones(self):
        """Regla 2 de PROD-CNS-BIT: la baja es lógica y conserva el historial; en un invernadero inactivo no se ofrece registrar."""
        self.registrar_un_evento()
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        pestana = {p.clave: p for p in pestanas_de_invernadero(self.gerente, Invernadero.objects.get(pk=self.e.invernadero.pk))}["bitacora"]
        self.assertIn("Riego revisado", pestana.html)
        self.assertNotIn(reverse("produccion:registrar_evento"), pestana.html)

    def test_la_consulta_no_audita(self):
        self.entrar(self.e.agronomo)
        antes = RegistroAuditoria.objects.count()
        self.client.get(reverse("produccion:bitacora"), {"invernadero": self.e.invernadero.pk})
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
