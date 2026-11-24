# Pruebas de las pantallas de suministros (COM-03a, paso 6; docs/casos_de_uso/comercial/suministro.md, «Pantallas»): permisos, el flujo completo de «Pactar
# suministro» con HTMX y sin él, el recálculo que no escribe nada, el resumen, la lista con el selector, la ficha, el calendario, el comprobante imprimible,
# «Reenviar comprobante» y el regreso desde el alta del cliente y desde «Cargar el correo» (`volver`). Las reglas de negocio ya las prueban los servicios
# (`test_com_pct_sum.py`, `test_com_cns_sum.py`): acá, los permisos, el flujo, los errores por campo, los botones y que nada valida al tipear.

import re
from datetime import timedelta
from html import unescape
from unittest import mock

from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import Cliente, ClausulaSuministrado, DetalleSuministro, ReservaStock, Suministro
from comercial.servicios import calendario, suministros
from comercial.tests.fabricas import (
    cliente as crear_cliente,
    detalle_suministro,
    direccion_de_cliente,
    escenario_comercial,
    reserva_de_periodo,
    suministro,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_transportista, crear_vendedor
from produccion.models import Cosecha
from produccion.tests.fabricas import lote_maduro

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()


def iso(dias):
    return str(HOY + timedelta(days=dias))


def avisos(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class BaseDeVistas(ConDatosDeInventario, TestCase):
    """Un escenario con 100 plantas en Maduración y un suministro ya pactado por otro Vendedor."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.gerente = crear_gerente()
        self.otro = escenario_comercial(sufijo="2")
        self.ajeno = suministro(self.otro)
        detalle_suministro(self.ajeno, self.otro.variedad, direccion=self.otro.direccion, primera_en_dias=40)
        self.addCleanup(verificar_invariantes_de_reservas)

    def post_de_pacto(self, **extra):
        """Lo que manda el formulario completo: 30 plantas cada 7 días a 1500,50, la primera dentro de 3 días (entran dos períodos en la ventana)."""
        datos = {
            "cliente": str(self.e.cliente.pk),
            "duracion": "6",
            "tolerados": "3",
            "multa": "50000",
            "plazo_pago": "15",
            "indemnizacion_pago": "100",
            "detalle-0-variedad": str(self.e.variedad.pk),
            "detalle-0-direccion": str(self.e.direccion.pk),
            "detalle-0-cantidad": "30",
            "detalle-0-periodo": "7",
            "detalle-0-primera_entrega": iso(3),
            "detalle-0-mecanismo": "fijo",
            "detalle-0-precio": "1500,50",
            "detalle-0-plazo_entrega": "1",
            "detalle-0-indemnizacion_retraso": "100",
            "detalle-0-cantidad_minima": "10",
            "detalle-0-indemnizacion_faltante": "50",
        }
        datos.update(extra)
        return {k: v for k, v in datos.items() if v is not None}

    def propio(self, **extra):
        """Un suministro propio con un detalle."""
        s = suministro(self.e, **extra)
        detalle_suministro(s, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=3)
        return s


class PermisosTests(BaseDeVistas):
    """Quién entra a cada pantalla (SEG-13, D-30)."""

    def urls(self):
        s = self.ajeno.pk
        return [
            reverse("comercial:contratos") + "?tipo=suministro",
            reverse("comercial:suministro_nuevo"),
            reverse("comercial:suministro", args=[s]),
            reverse("comercial:suministro_calendario", args=[s]),
            reverse("comercial:suministro_comprobante", args=[s]),
        ]

    def test_pre_a_los_demas_roles_reciben_403_y_el_anonimo_va_al_inicio_de_sesion(self):
        """Precondición a: Agrónomo, Capataz, Transportista: 403 en todas las pantallas y en cada POST; sin sesión, a iniciar sesión."""
        posts = [
            reverse("comercial:suministro_calcular"),
            reverse("comercial:suministro_revisar"),
            reverse("comercial:suministro_reenviar_comprobante", args=[self.ajeno.pk]),
        ]
        for cuenta in (self.e.agronomo, self.e.capataz, crear_transportista()):
            self.client.force_login(cuenta)
            for url in self.urls():
                with self.subTest(rol=cuenta.rol, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
            for url in posts:
                with self.subTest(rol=cuenta.rol, post=url):
                    self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.client.logout()
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_regla_1_el_vendedor_no_abre_la_ficha_el_calendario_ni_el_comprobante_de_otro_vendedor(self):
        """Regla 1 de COM-CNS-SUM y SEG-13: 403 con mensaje; un id inexistente, 404."""
        self.client.force_login(self.e.vendedor)
        for nombre in ("suministro", "suministro_calendario", "suministro_comprobante"):
            self.assertEqual(self.client.get(reverse(f"comercial:{nombre}", args=[self.ajeno.pk])).status_code, 403, nombre)
            self.assertEqual(self.client.get(reverse(f"comercial:{nombre}", args=[999999])).status_code, 404, nombre)
        self.assertEqual(self.client.post(reverse("comercial:suministro_reenviar_comprobante", args=[self.ajeno.pk])).status_code, 403)

    def test_regla_2_el_vendedor_no_ve_el_filtro_de_vendedor_ni_los_suministros_ajenos_y_el_gerente_si(self):
        """Regla 2 de COM-CNS-SUM: el filtro «Vendedor» es solo del Gerente (y la lista del Vendedor trae solo lo suyo)."""
        propio = self.propio()
        self.client.force_login(self.e.vendedor)
        pagina = self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"})
        self.assertNotContains(pagina, 'aria-label="Vendedor"')
        self.assertContains(pagina, propio.codigo)
        self.assertNotContains(pagina, self.ajeno.codigo)
        self.client.force_login(self.gerente)
        pagina = self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"})
        self.assertContains(pagina, 'aria-label="Vendedor"')
        self.assertContains(pagina, self.ajeno.codigo)

    def test_regla_ningun_boton_lleva_a_un_403(self):
        """D-30 y D-25: la ficha propia ofrece solo lo que la persona puede hacer y existe («Modificar suministro» desde COM-03b: antes esta prueba decía que no; sin «Rescindir»
        —es del Gerente—, sin «Ver historial» —no tiene cambios— ni «Registrar cobro») y ningún enlace lleva a un 403."""
        propio = self.propio()
        self.client.force_login(self.e.vendedor)
        pagina = self.client.get(reverse("comercial:suministro", args=[propio.pk]))
        self.assertContains(pagina, "Reenviar comprobante")
        self.assertContains(pagina, "Modificar suministro")
        for texto in ("Rescindir", "Dejar sin efecto la rescisión", "Ver historial de cambios", "Registrar cobro"):
            self.assertNotContains(pagina, texto)
        for url in re.findall(r'href="(/comercial/[^"]*)"', pagina.content.decode()):
            self.assertNotEqual(self.client.get(url).status_code, 403, url)

    def test_pre_b_sin_invernaderos_activos_pactar_suministro_se_muestra_deshabilitado_con_su_motivo(self):
        """Precondición b: la lista muestra el botón deshabilitado con el motivo y el POST de confirmar no pacta nada."""
        sin_invernaderos = crear_vendedor(email="sin@infoponia.com")
        self.client.force_login(sin_invernaderos)
        pagina = self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"})
        self.assertContains(pagina, "No tenés invernaderos activos asignados: pedile al Gerente que te asigne uno.")
        self.assertContains(pagina, 'aria-disabled="true"')
        self.client.post(reverse("comercial:suministro_nuevo"), {**self.post_de_pacto(), "confirmar": "1"})
        self.assertEqual(Suministro.objects.filter(vendedor=sin_invernaderos).count(), 0)

    def test_pre_c_sin_variedades_activas_el_motivo_se_muestra(self):
        """Precondición c: «No hay variedades activas.» en la lista y en el formulario."""
        type(self.e.variedad).objects.update(estado_variedad="inactivo")  # todas: el otro escenario tiene la suya
        self.client.force_login(self.e.vendedor)
        self.assertContains(self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"}), "No hay variedades activas.")
        self.assertContains(self.client.get(reverse("comercial:suministro_nuevo")), "No hay variedades activas.")


class SelectorYListaTests(BaseDeVistas):
    """La pestaña «Contratos» con el selector «Compra-ventas / Suministros» (`ctrSel`) y la lista de suministros."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.gerente)

    def test_regla_el_selector_lleva_de_un_tipo_al_otro_y_marca_el_activo(self):
        """`ctrSel` (corregido a dos enlaces, sin JavaScript): cada tipo es una página con sus filtros; el activo lleva `aria-current`."""
        compra_ventas = self.client.get(reverse("comercial:contratos"))
        self.assertContains(compra_ventas, "?tipo=suministro")
        self.assertRegex(compra_ventas.content.decode(), r'<a href="/comercial/contratos/" aria-current="page">Compra-ventas</a>')
        lista = self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"})
        self.assertRegex(lista.content.decode(), r'<a href="/comercial/contratos/\?tipo=suministro" aria-current="page">Suministros</a>')
        self.assertContains(lista, "Pactar suministro")
        self.assertNotContains(lista, "Nueva compra-venta")

    def test_regla_3_la_lista_trae_las_columnas_la_marca_al_limite_y_los_filtros_de_la_url(self):
        """Regla 3: código, cliente, vigencia, detalles vigentes, incumplimientos «N de M» con «Al límite» y estado; con filtro por estado en la URL."""
        al_limite = self.propio(tolerados=2, incumplimientos=1)
        self.propio(estado="finalizado")
        pagina = self.client.get(reverse("comercial:contratos"), {"tipo": "suministro", "estado": "vigente"})
        self.assertContains(pagina, al_limite.codigo)
        self.assertContains(pagina, "1 de 2")
        self.assertContains(pagina, "Al límite")
        self.assertContains(pagina, "6 meses")
        self.assertNotContains(pagina, "Ningún suministro coincide")
        vacia = self.client.get(reverse("comercial:contratos"), {"tipo": "suministro", "estado": "resuelto"})
        self.assertContains(vacia, "Ningún suministro coincide con los filtros.")

    def test_regla_la_lista_sin_suministros_invita_a_pactar_el_primero(self):
        """Estado vacío: «Todavía no hay suministros.» si no hay ninguno (sin filtros)."""
        self.client.force_login(self.e.vendedor)
        self.assertContains(self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"}), "Todavía no hay suministros.")

    def test_regla_el_tipo_desconocido_muestra_las_compra_ventas(self):
        """Un `tipo` que no es «suministro» no rompe: es la lista de compra-ventas."""
        self.assertContains(self.client.get(reverse("comercial:contratos"), {"tipo": "otro"}), "Nueva compra-venta")


class PactarVistaTests(BaseDeVistas):
    """El flujo de «Pactar suministro», con HTMX y sin él."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.e.vendedor)
        self.nueva = reverse("comercial:suministro_nuevo")
        self.calcular = reverse("comercial:suministro_calcular")
        self.revisar = reverse("comercial:suministro_revisar")

    def filas(self):
        return (Suministro.objects.count(), DetalleSuministro.objects.count(), ReservaStock.objects.count(), Cosecha.objects.count(), RegistroAuditoria.objects.count())

    def test_flujo_principal_con_htmx_calcula_revisa_y_confirma(self):
        """Pasos 1 a 16 con HTMX: el recálculo devuelve el cuerpo del formulario con el calendario y la verificación de stock sin escribir nada;
        «Revisar y pactar» devuelve solo la ventana del resumen; «Confirmar» pacta y redirige a la ficha con el aviso breve."""
        antes = self.filas()
        cuerpo = self.client.post(self.calcular, self.post_de_pacto(), **HTMX)
        self.assertContains(cuerpo, "se reserva ahora")
        self.assertContains(cuerpo, "Alcanza")
        self.assertContains(cuerpo, "Termina el")
        self.assertNotContains(cuerpo, "<html")
        self.assertEqual(self.filas(), antes)  # `calcular/` no escribe nada
        ventana = self.client.post(self.revisar, self.post_de_pacto(), **HTMX)
        self.assertContains(ventana, "Resumen del suministro")
        self.assertContains(ventana, "Confirmar suministro")
        self.assertContains(ventana, "Volver a la carga")
        self.assertNotContains(ventana, "<html")
        self.assertEqual(self.filas(), antes)  # el resumen tampoco
        respuesta = self.client.post(self.nueva, {**self.post_de_pacto(), "confirmar": "1"})
        s = Suministro.objects.exclude(pk=self.ajeno.pk).get()
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[s.pk]))
        self.assertTrue(any(f"{s.codigo} pactado. Se reservaron 2 períodos y se programaron 2 cosechas." in a for a in avisos(respuesta)))
        self.assertEqual(Notificacion.objects.filter(titulo__startswith="Nueva cosecha").count(), 4)
        self.assertTrue(ClausulaSuministrado.objects.filter(suministro=s).exists())

    def test_flujo_principal_sin_javascript_actualizar_resumen_como_pagina_y_confirmar(self):
        """Sin JavaScript: «Actualizar» muestra la página con los cálculos; «Revisar y pactar» lleva a una página con los datos como campos ocultos;
        «Volver a la carga» (13a) la devuelve con todo lo cargado; «Confirmar» pacta."""
        pagina = self.client.post(self.nueva, {**self.post_de_pacto(), "actualizar": "1"})
        self.assertContains(pagina, "<html")
        self.assertContains(pagina, "se reserva ahora")
        resumen = self.client.post(self.revisar, self.post_de_pacto())
        self.assertContains(resumen, "<html")
        self.assertContains(resumen, 'name="detalle-0-cantidad" value="30"')
        self.assertContains(resumen, 'name="detalle-0-primera_entrega"')
        volver = self.client.post(self.nueva, {**self.post_de_pacto(), "actualizar": "1"})
        self.assertContains(volver, 'value="30"')
        self.client.post(self.nueva, {**self.post_de_pacto(), "confirmar": "1"})
        self.assertEqual(Suministro.objects.exclude(pk=self.ajeno.pk).count(), 1)

    def test_ext_9b_el_error_por_campo_se_muestra_en_su_campo_y_no_se_pacta_nada(self):
        """Extensiones 9b y 9e: una cantidad que supera lo disponible y un precio en cero, cada error junto a su campo (con HTMX, el resumen
        devuelve el cuerpo con los errores y `HX-Retarget`)."""
        datos = self.post_de_pacto(**{"detalle-0-cantidad": "500", "detalle-0-precio": "0"})
        respuesta = self.client.post(self.revisar, datos, **HTMX)
        self.assertContains(respuesta, "plantas disponibles de")
        self.assertContains(respuesta, "Ingresá un precio de $ 0,01")
        self.assertEqual(respuesta["HX-Retarget"], "#cuerpo-sum")
        sin_js = self.client.post(self.nueva, {**datos, "confirmar": "1"})
        self.assertContains(sin_js, "plantas disponibles de")
        self.assertEqual(Suministro.objects.exclude(pk=self.ajeno.pk).count(), 0)

    def test_ext_14a_si_el_stock_cambio_el_formulario_marca_el_detalle_y_avisa(self):
        """Extensión 14a: «El stock cambió mientras cargabas el contrato.» y la cantidad disponible en el detalle afectado."""
        falso = {self.e.variedad.pk: [suministros.stock_maduro.Cobertura(HOY + timedelta(days=3), 500, 1000), suministros.stock_maduro.Cobertura(HOY + timedelta(days=10), 500, 1000)]}
        with mock.patch.object(suministros.stock_maduro, "simular_varias", return_value=falso):
            respuesta = self.client.post(self.nueva, {**self.post_de_pacto(**{"detalle-0-cantidad": "500", "detalle-0-cantidad_minima": "1"}), "confirmar": "1"})
        self.assertContains(respuesta, "El stock cambió mientras cargabas el contrato.")
        self.assertContains(respuesta, "plantas disponibles para esa fecha")
        self.assertEqual(Suministro.objects.exclude(pk=self.ajeno.pk).count(), 0)

    def test_regla_nunca_se_valida_ni_se_recalcula_mientras_se_tipea(self):
        """`.claude/rules/interfaz.md`: ningún campo de texto, de número o de fecha lleva disparadores de HTMX; solo los selectores y los botones redibujan,
        sin validar, con `hx-swap="innerHTML show:none"` y `data-sin-envio-en-curso`."""
        pagina = self.client.post(self.calcular, self.post_de_pacto(), **HTMX).content.decode()
        self.assertNotRegex(pagina, r"hx-trigger=\"[^\"]*(input|keyup|delay)")
        for etiqueta in re.findall(r"<input[^>]*>", pagina):
            if 'type="text"' in etiqueta or 'type="date"' in etiqueta or 'type="search"' in etiqueta:
                self.assertNotIn("hx-", etiqueta, etiqueta)
        selectores = re.findall(r"<select[^>]*>", pagina)
        self.assertTrue(selectores)
        for etiqueta in selectores:
            self.assertIn('hx-swap="innerHTML show:none"', etiqueta)
            self.assertIn("data-sin-envio-en-curso", etiqueta)

    def test_regla_el_primer_boton_del_formulario_es_actualizar_para_que_enter_no_quite_nada(self):
        """Sin JavaScript, «Enter» en un campo manda el primer botón del formulario: tiene que ser «Actualizar» (no «Quitar» ni una opción de período)."""
        pagina = self.client.get(self.nueva).content.decode()
        primero = re.search(r'<button[^>]*type="submit"[^>]*>', pagina[pagina.index('<form id="form-sum"'):])
        self.assertIn('name="actualizar"', primero.group(0))

    def test_regla_el_boton_de_confirmar_muestra_pactando(self):
        """Requisito especial: el botón muestra «Pactando…» y se deshabilita al enviar (`data-enviando`), siempre."""
        self.assertContains(self.client.post(self.revisar, self.post_de_pacto(), **HTMX), 'data-enviando="Pactando…"')

    def test_regla_las_secciones_bloqueadas_dicen_que_falta(self):
        """Criterio de interfaz: Contrato y Detalles se habilitan con el cliente elegido."""
        vacio = self.client.get(self.nueva)
        self.assertContains(vacio, "Elegí primero el cliente.")
        con_cliente = self.client.get(self.nueva, {"cliente": self.e.cliente.pk})
        self.assertNotContains(con_cliente, "Elegí primero el cliente.")
        self.assertContains(con_cliente, "Cuántos incumplimientos acepta el contrato. Al superarlos, se resuelve. Con 0, el primero lo resuelve.")
        self.assertContains(con_cliente, "Cada variedad va una vez por dirección. El calendario y el precio de cada entrega se calculan solos.")
        self.assertContains(con_cliente, "Las entregas que caen en los próximos 14 días se reservan al pactar.")

    def test_ext_4b_un_cliente_sin_correo_bloquea_las_secciones_y_ofrece_cargar_el_correo(self):
        """Extensión 4b: con un cliente sin correo, las secciones 2 y 3 quedan bloqueadas con el aviso y «Cargar el correo» (COM-MOD-CLT con `volver`)."""
        sin_correo = crear_cliente(razon_social="Sin correo S.A.", email="")
        direccion_de_cliente(sin_correo)
        pagina = self.client.get(self.nueva, {"cliente": sin_correo.pk})
        self.assertContains(pagina, "El cliente no tiene correo. Hace falta para el comprobante y para los enlaces de confirmación de cada entrega.")
        self.assertContains(pagina, "Cargá el correo del cliente para seguir.")
        self.assertContains(pagina, f"/comercial/clientes/{sin_correo.pk}/modificar/?volver=")
        self.assertNotContains(pagina, 'name="duracion"')

    def test_regla_el_buscador_de_clientes_ofrece_elegir_y_el_alta_cuando_no_hay_coincidencias(self):
        """Pasos 3 y 3a: desde 2 caracteres; sin coincidencias, «No hay clientes que coincidan.» con el enlace al alta."""
        encontrado = self.client.post(self.calcular, {"cliente_q": str(self.e.cliente)[:5]}, **HTMX)
        self.assertContains(encontrado, "Elegir")
        self.assertContains(encontrado, str(self.e.cliente))
        nada = self.client.post(self.calcular, {"cliente_q": "zzzzzz"}, **HTMX)
        self.assertContains(nada, "No hay clientes que coincidan.")
        self.assertContains(nada, reverse("comercial:cliente_nuevo"))

    def test_ext_1a_el_gerente_elige_al_vendedor_y_pacta_a_su_nombre(self):
        """Extensión 1a: el formulario del Gerente pide el Vendedor responsable; el contrato queda de ese Vendedor."""
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(self.nueva), "Vendedor responsable")
        self.client.post(self.nueva, {**self.post_de_pacto(vendedor=str(self.e.vendedor.pk)), "confirmar": "1"})
        self.assertEqual(Suministro.objects.exclude(pk=self.ajeno.pk).get().vendedor_id, self.e.vendedor.pk)

    def test_regla_el_vendedor_no_ve_el_selector_de_vendedor(self):
        """Paso 1: el Vendedor es el responsable y no lo elige."""
        self.assertNotContains(self.client.get(self.nueva), "Vendedor responsable")

    def test_ext_9d_la_superposicion_se_advierte_con_su_casilla_y_sin_ella_no_se_pacta(self):
        """Extensión 9d: aviso con el código del otro contrato y la casilla «Continuar igual»; sin marcarla, no se pacta; marcada, sí."""
        otro = suministro(self.e)
        detalle_suministro(otro, self.e.variedad, direccion=self.e.direccion)
        cuerpo = self.client.post(self.calcular, self.post_de_pacto(), **HTMX)
        self.assertContains(cuerpo, otro.codigo)
        self.assertContains(cuerpo, "Continuar igual")
        sin_marcar = self.client.post(self.nueva, {**self.post_de_pacto(), "confirmar": "1"})
        self.assertContains(sin_marcar, "Marcá «Continuar igual»")
        self.assertEqual(Suministro.objects.exclude(pk__in=[self.ajeno.pk, otro.pk]).count(), 0)
        self.client.post(self.nueva, {**self.post_de_pacto(**{"detalle-0-continuar": "1"}), "confirmar": "1"})
        self.assertEqual(Suministro.objects.exclude(pk__in=[self.ajeno.pk, otro.pk]).count(), 1)

    def test_ext_8b_con_ajuste_periodico_aparecen_el_porcentaje_los_meses_y_los_tramos_de_precio(self):
        """Extensión 8b: con el mecanismo de ajuste periódico se piden el porcentaje y los meses y se muestran los tramos «Desde el dd/mm: $ …»."""
        datos = self.post_de_pacto(**{"detalle-0-mecanismo": "ajuste_periodico", "detalle-0-porcentaje": "3", "detalle-0-meses": "2", "detalle-0-periodo": "30", "detalle-0-primera_entrega": iso(0)})
        cuerpo = self.client.post(self.calcular, datos, **HTMX)
        self.assertContains(cuerpo, 'name="detalle-0-porcentaje"')
        self.assertContains(cuerpo, "Desde el")
        self.assertNotContains(self.client.post(self.calcular, self.post_de_pacto(), **HTMX), 'name="detalle-0-porcentaje"')

    def test_ext_7_11a_agregar_quitar_y_las_opciones_rapidas_de_periodo(self):
        """Agregar detalle suma un renglón en blanco sin validar y conserva lo cargado; Quitar lo saca; las opciones 7, 14 y 30 cargan el período."""
        con_dos = self.client.post(self.calcular, {**self.post_de_pacto(), "agregar_detalle": "1"}, **HTMX)
        self.assertContains(con_dos, "Detalle 2")
        self.assertContains(con_dos, 'name="detalle-1-variedad"')
        self.assertNotContains(con_dos, 'class="err"')
        self.assertContains(con_dos, 'value="30"')
        sin_el_segundo = self.client.post(self.calcular, {**self.post_de_pacto(**{"detalle-1-variedad": ""}), "quitar": "1"}, **HTMX)
        self.assertNotContains(sin_el_segundo, "Detalle 2")
        rapido = self.client.post(self.calcular, {**self.post_de_pacto(), "periodo_rapido": "0:14"}, **HTMX)
        self.assertContains(rapido, 'name="detalle-0-periodo" value="14"')

    def test_ext_13a_1b_cambiar_el_cliente_descarta_la_direccion_de_los_detalles(self):
        """13a.1b: «Cambiar» el cliente vuelve a la búsqueda y deja las direcciones de los detalles sin elegir."""
        respuesta = self.client.post(self.calcular, {**self.post_de_pacto(), "cambiar_cliente": "1"}, **HTMX)
        self.assertContains(respuesta, "Buscar al cliente")
        self.assertNotContains(respuesta, 'name="detalle-0-cantidad"')

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_15a_si_el_correo_falla_el_aviso_lo_dice_y_la_ficha_ofrece_reenviar(self):
        """Extensión 15a: «No se pudo enviar el comprobante a {correo}. Podés reenviarlo desde la ficha.»; «Reenviar comprobante» lo deja enviado."""
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=False):
            respuesta = self.client.post(self.nueva, {**self.post_de_pacto(), "confirmar": "1"})
        self.assertTrue(any("No se pudo enviar el comprobante a cliente@ejemplo.com. Podés reenviarlo desde la ficha." in a for a in avisos(respuesta)))
        s = Suministro.objects.exclude(pk=self.ajeno.pk).get()
        ficha = self.client.get(reverse("comercial:suministro", args=[s.pk]))
        self.assertContains(ficha, "Pendiente de envío")
        self.assertContains(ficha, "Reenviar comprobante")
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=True):
            reenvio = self.client.post(reverse("comercial:suministro_reenviar_comprobante", args=[s.pk]))
        self.assertRedirects(reenvio, reverse("comercial:suministro", args=[s.pk]))
        self.assertEqual(Suministro.objects.get(pk=s.pk).estado_comprobante, "enviado")
        self.assertNotContains(self.client.get(reverse("comercial:suministro", args=[s.pk])), "Reenviar comprobante")

    def test_regla_reenviar_es_un_post_y_no_acepta_get(self):
        """Reenviar comprobante cambia datos (el estado): solo POST."""
        self.assertEqual(self.client.get(reverse("comercial:suministro_reenviar_comprobante", args=[self.ajeno.pk])).status_code, 405)


class VolverDesdeElClienteTests(BaseDeVistas):
    """Extensiones 4a, 4b y 8a: el alta del cliente, «Cargar el correo» y la nueva dirección vuelven a «Pactar suministro» con lo cargado."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.e.vendedor)

    def test_ext_4a_el_enlace_al_alta_lleva_los_datos_de_las_secciones_1_y_2_y_avisa_de_los_detalles(self):
        """El enlace «Registrar o reactivar un cliente» lleva `volver` con la duración, los tolerados, la multa y las cláusulas (los detalles no
        viajan: lo avisa antes)."""
        pagina = self.client.get(reverse("comercial:suministro_nuevo"), {"duracion": "12", "multa": "500"})
        enlace = re.search(r'href="(/comercial/clientes/nuevo/\?volver=[^"]+)"', pagina.content.decode())
        self.assertIsNotNone(enlace)
        self.assertIn("duracion%3D12", enlace.group(1))
        con_detalles = self.client.post(reverse("comercial:suministro_calcular"), self.post_de_pacto(cliente=None), **HTMX)
        self.assertContains(con_detalles, "Vas a tener que volver a cargar los detalles.")

    def test_ext_4a_tras_el_alta_vuelve_al_pacto_con_el_cliente_elegido(self):
        """Regla 7 de COM-ALT-CLT: el alta vuelve a «Pactar suministro» con el cliente nuevo elegido y lo ya cargado en la consulta."""
        volver = reverse("comercial:suministro_nuevo") + "?duracion=12&multa=500"
        respuesta = self.client.post(
            reverse("comercial:cliente_nuevo"),
            {"tipo_cliente": "juridica", "cuit": "30-71234567-1", "razon_social": "Nuevo S.A.", "email": "nuevo@ejemplo.com", "volver": volver},
        )
        nuevo = Cliente.objects.get(razon_social_cliente="Nuevo S.A.")
        self.assertRedirects(respuesta, f"{volver}&cliente={nuevo.pk}", fetch_redirect_response=False)
        pagina = self.client.get(f"{volver}&cliente={nuevo.pk}")
        self.assertContains(pagina, "Nuevo S.A.")
        self.assertContains(pagina, f'name="cliente" value="{nuevo.pk}"')
        self.assertContains(pagina, 'name="duracion" value="12"')

    def test_ext_4b_cargar_el_correo_vuelve_al_pacto_con_el_mismo_cliente_elegido(self):
        """Extensión 4b y regla 5 de COM-MOD-CLT: «Cargar el correo» abre la modificación del cliente con `volver`; al guardar vuelve al pacto con el
        cliente todavía elegido y con la sección 2 ya habilitada."""
        sin_correo = crear_cliente(razon_social="Sin correo S.A.", email="")
        vinculo = direccion_de_cliente(sin_correo)
        pagina = self.client.get(reverse("comercial:suministro_nuevo"), {"cliente": sin_correo.pk, "duracion": "12"})
        enlace = re.search(r'href="(/comercial/clientes/\d+/modificar/\?volver=[^"]+)"', pagina.content.decode()).group(1)
        self.assertContains(self.client.get(enlace), 'name="volver"')
        volver = reverse("comercial:suministro_nuevo") + f"?cliente={sin_correo.pk}&duracion=12"
        from maestros.tests.fabricas import localidad

        datos = {
            "tipo_cliente": "juridica", "cuit": sin_correo.cuit_cliente, "razon_social": sin_correo.razon_social_cliente, "email": "ya@ejemplo.com",
            "volver": volver, f"corregida-{vinculo.direccion_id}-tipo_direccion": "urbana", f"corregida-{vinculo.direccion_id}-localidad": localidad().pk,
            f"corregida-{vinculo.direccion_id}-calle": "San Martín", f"corregida-{vinculo.direccion_id}-numero_calle": "123",
        }
        respuesta = self.client.post(reverse("comercial:cliente_modificar", args=[sin_correo.pk]), datos)
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith(reverse("comercial:suministro_nuevo")))
        vuelta = self.client.get(respuesta.url)
        self.assertContains(vuelta, f'name="cliente" value="{sin_correo.pk}"')
        self.assertContains(vuelta, 'name="duracion" value="12"')
        self.assertNotContains(vuelta, "Cargá el correo del cliente para seguir.")

    def test_regla_un_volver_externo_se_descarta(self):
        """Regla 7 de COM-ALT-CLT: solo vuelve a URLs internas; con una externa, va a la ficha del cliente."""
        respuesta = self.client.post(
            reverse("comercial:cliente_nuevo"),
            {"tipo_cliente": "juridica", "cuit": "30-71234567-1", "razon_social": "Nuevo S.A.", "volver": "https://evil.example.com/?x=1"},
        )
        nuevo = Cliente.objects.get(razon_social_cliente="Nuevo S.A.")
        self.assertRedirects(respuesta, reverse("comercial:cliente", args=[nuevo.pk]))


class FichaCalendarioYComprobanteTests(BaseDeVistas):
    """La ficha, el calendario completo, el comprobante imprimible y la ficha del cliente."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.e.vendedor)

    def test_regla_4_a_6_la_ficha_muestra_el_contrato_los_detalles_y_la_situacion_de_cada_periodo(self):
        """Reglas 4 a 6: datos y cláusula del suministrado, detalles con el precio vigente, calendario con «Reservado», «Sin cobertura completa» y
        «Fuera de la ventana», la ventana de pre-reserva y el comprobante."""
        s = self.propio(duracion=6)
        d = s.detalles.get()
        reserva_de_periodo(d, d.fecha_primer_entrega, [(self.lote, 30)])
        pagina = self.client.get(reverse("comercial:suministro", args=[s.pk]))
        for texto in ("Reservado", "Sin cobertura completa · faltan 30", "Fuera de la ventana", "Ventana de pre-reserva: hasta el", "Precio vigente", "Pago de cada entrega", "Ver todo el calendario", "Ver comprobante"):
            self.assertContains(pagina, texto)

    def test_regla_9_la_ficha_destaca_el_limite_de_incumplimientos(self):
        """Regla 9: el aviso aparece en la ficha cuando le queda un tolerado."""
        s = self.propio(tolerados=2, incumplimientos=1)
        self.assertContains(self.client.get(reverse("comercial:suministro", args=[s.pk])), "Al contrato le queda un incumplimiento tolerado.")

    def test_regla_6_ver_todo_el_calendario_lista_y_pagina_los_periodos(self):
        """Regla 6: la página del calendario completo pagina de a 100 y vuelve a la ficha."""
        s = suministro(self.e, duracion=12)
        detalle_suministro(s, self.e.variedad, cantidad=1, periodo=1, primera_en_dias=0)
        pagina = self.client.get(reverse("comercial:suministro_calendario", args=[s.pk]))
        self.assertContains(pagina, "Página 1 de 4")
        self.assertContains(self.client.get(reverse("comercial:suministro_calendario", args=[s.pk]), {"pagina": "2"}), "Página 2 de 4")
        self.assertContains(pagina, reverse("comercial:suministro", args=[s.pk]))

    def test_ext_15a_el_comprobante_imprimible_dice_el_calendario_resumido_y_la_aclaracion_fiscal(self):
        """Variación 15a: el comprobante imprimible trae las cláusulas, la cantidad de entregas con su primera y última fecha, y «Comprobante interno,
        sin validez fiscal.»; no lista cada fecha."""
        s = self.propio(duracion=6)
        pagina = self.client.get(reverse("comercial:suministro_comprobante", args=[s.pk]))
        self.assertContains(pagina, "Comprobante interno, sin validez fiscal.")
        self.assertContains(pagina, f"Comprobante de suministro {s.codigo}")
        self.assertContains(pagina, "Cláusula del suministrante")
        self.assertContains(pagina, "entregas, del")
        self.assertNotContains(pagina, "<nav")

    def test_regla_2_la_ficha_del_cliente_lista_los_suministros_y_la_lista_cuenta_los_vigentes(self):
        """COM-03a completa COM-01: la ficha del cliente lista sus suministros (el Vendedor, solo los suyos) y «Contratos vigentes» los suma."""
        propio = self.propio()
        ajeno_del_mismo_cliente = suministro(self.otro, cliente_=self.e.cliente)
        ficha = self.client.get(reverse("comercial:cliente", args=[self.e.cliente.pk]))
        self.assertContains(ficha, propio.codigo)
        self.assertNotContains(ficha, ajeno_del_mismo_cliente.codigo)
        self.assertContains(ficha, reverse("comercial:suministro", args=[propio.pk]))
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(reverse("comercial:cliente", args=[self.e.cliente.pk])), ajeno_del_mismo_cliente.codigo)
        self.assertContains(self.client.get(reverse("comercial:clientes")), "Contratos vigentes")

    def test_regla_la_baja_del_cliente_informa_los_suministros_vigentes(self):
        """Regla 1 de COM-BAJ-CLT: la ventana de baja del cliente nombra el suministro vigente."""
        propio = self.propio()
        self.client.force_login(self.gerente)
        ventana = self.client.get(reverse("comercial:cliente_baja", args=[self.e.cliente.pk]), **HTMX)
        self.assertContains(ventana, f"Suministros vigentes: 1 ({propio.codigo}).")


# ---- COM-03b: modificar, rescindir, dejar sin efecto la rescisión e historial (paso 7 de la tarea) ----
#
# Los permisos, los flujos con HTMX y sin él, los errores por campo, los botones y que `calcular/` y `revisar/` no escriben nada. Las reglas de negocio ya las prueban los
# servicios (`test_com_mod_sum.py`, `test_com_rsc_sum.py`, `test_com_anl_rsc.py`, `test_com_cns_sum.py`).


def campos_ocultos(respuesta):
    """``{nombre: valor}`` de los campos ocultos de una respuesta (lo que el resumen manda de vuelta al confirmar: sin JavaScript es lo único que viaja)."""
    html = respuesta.content.decode()
    return {nombre: unescape(valor) for nombre, valor in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', html)}


class BaseDeModificacionEnVistas(BaseDeVistas):
    """Un suministro propio (30 plantas cada 7 días desde dentro de 3: períodos a los 3, 10, 17…; el cambio rige desde el día 17) para el Vendedor y el Gerente."""

    def setUp(self):
        super().setUp()
        self.s = self.propio()
        self.d = self.s.detalles.get()
        self.url = reverse("comercial:suministro_modificar", args=[self.s.pk])

    def huella(self):
        return suministros.huella_de(Suministro.objects.get(pk=self.s.pk))

    def cambios(self, **extra):
        """Lo que manda el formulario al modificar la cantidad del detalle a 40 (con la huella y la propuesta que vio la persona)."""
        datos = {
            "huella": self.huella(),
            f"modificar-{self.d.pk}-accion": "modificar",
            f"modificar-{self.d.pk}-cantidad": "40",
            f"modificar-{self.d.pk}-rige_visto": iso(17),
        }
        datos.update(extra)
        return {k: v for k, v in datos.items() if v is not None}

    def cuenta_de_lo_escrito(self):
        return (DetalleSuministro.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count(), ReservaStock.objects.count())


class ComModSumVistaTests(BaseDeModificacionEnVistas):
    """«Modificar suministro»: pantalla, recálculo, resumen y confirmación."""

    def test_pre_a_los_demas_roles_y_otro_vendedor_reciben_403_y_el_anonimo_va_al_inicio_de_sesion(self):
        """Precondición a y regla «Quién modifica»: Agrónomo, Capataz y Transportista, y un Vendedor ajeno, 403 en la pantalla, el recálculo, el resumen y la
        confirmación; sin sesión, a iniciar sesión; un id que no existe, 404."""
        urls = [self.url, self.url + "calcular/", self.url + "revisar/"]
        for cuenta in (self.e.agronomo, self.e.capataz, crear_transportista(), self.otro.vendedor):
            self.client.force_login(cuenta)
            self.assertEqual(self.client.get(self.url).status_code, 403, cuenta)
            for url in urls[1:]:
                self.assertEqual(self.client.post(url, self.cambios()).status_code, 403, (cuenta, url))
            self.assertEqual(self.client.post(self.url, {**self.cambios(), "confirmar": "1"}).status_code, 403, cuenta)
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code in (302, 405), True, url)
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("comercial:suministro_modificar", args=[999999])).status_code, 404)
        self.assertEqual(self.cuenta_de_lo_escrito()[0], 2)  # nada se escribió (el ajeno y el propio)

    def test_regla_la_pantalla_trae_los_valores_actuales_y_lo_que_no_se_modifica(self):
        """Pasos 4 y 5: el formulario viene cargado con lo actual, dice desde cuándo rige un cambio y muestra el cliente y la fecha de realización como texto (extensión 5g)."""
        self.client.force_login(self.e.vendedor)
        pagina = self.client.get(self.url)
        self.assertContains(pagina, f"Modificar suministro <span class=\"mono\">{self.s.codigo}</span>")
        self.assertContains(pagina, f'name="modificar-{self.d.pk}-cantidad" value="30"')
        self.assertContains(pagina, f'name="modificar-{self.d.pk}-rige_visto" value="{iso(17)}"')
        self.assertContains(pagina, "No se modifican: para otro cliente o desde otra fecha, pactá un suministro nuevo.")
        self.assertContains(pagina, "Los cambios rigen desde el primer período posterior al")
        self.assertNotContains(pagina, 'name="cliente"')
        self.assertContains(pagina, f'name="huella" value="{self.huella()}"')

    def test_regla_solo_el_gerente_ve_el_vendedor_responsable(self):
        """Extensión 1a: el selector de Vendedor es del Gerente; el Vendedor no lo ve y, si lo manda, recibe 403."""
        self.client.force_login(self.e.vendedor)
        self.assertNotContains(self.client.get(self.url), 'name="vendedor"')
        self.assertEqual(self.client.post(self.url + "revisar/", {**self.cambios(), "vendedor": str(self.otro.vendedor.pk)}).status_code, 403)
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(self.url), 'name="vendedor"')

    def test_regla_un_contrato_con_rescision_acordada_vuelve_a_la_ficha_con_el_motivo(self):
        """Precondición nueva de COM-RSC-SUM: con una rescisión acordada, la pantalla no se abre; vuelve a la ficha con «Tiene una rescisión acordada…» (con HTMX,
        por `HX-Redirect`)."""
        lectura = suministros.datos_de_rescision(self.gerente, self.s.pk)
        suministros.rescindir_suministro(
            self.gerente, self.s.pk, suministros.PedidoDeRescision("a_pedido_del_cliente", "", iso(0), "1"), lectura.huella, lectura.conservados
        )
        self.client.force_login(self.e.vendedor)
        respuesta = self.client.get(self.url)
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.s.pk]), fetch_redirect_response=False)
        self.assertIn("Tiene una rescisión acordada: dejala sin efecto para modificarlo.", avisos(respuesta))
        htmx = self.client.post(self.url + "calcular/", self.cambios(), **HTMX)
        self.assertEqual((htmx.status_code, htmx["HX-Redirect"]), (204, reverse("comercial:suministro", args=[self.s.pk])))

    def test_regla_calcular_devuelve_el_cuerpo_con_los_cambios_y_no_escribe_nada(self):
        """Paso 6: `calcular/` redibuja el cuerpo con el panel «Cambios» (la fecha desde la que rige) sin guardar ni auditar ni avisar; solo POST."""
        self.client.force_login(self.gerente)
        antes = self.cuenta_de_lo_escrito()
        pagina = self.client.post(self.url + "calcular/", self.cambios(), **HTMX)
        self.assertContains(pagina, "cantidad por período: de 30 a 40")
        self.assertContains(pagina, f"Rige desde el {(HOY + timedelta(days=17)):%d/%m/%Y}")
        self.assertNotContains(pagina, "<html")
        self.assertEqual(self.cuenta_de_lo_escrito(), antes)
        self.assertEqual(self.client.get(self.url + "calcular/").status_code, 405)

    def test_regla_agregar_y_quitar_un_detalle_nuevo_sin_validar(self):
        """Extensión 5b: «Agregar detalle» suma un bloque en blanco sin errores; «Quitar» lo saca (con la convención de COM-02: nada valida al tipear)."""
        self.client.force_login(self.gerente)
        con_nuevo = self.client.post(self.url + "calcular/", {**self.cambios(), "agregar_detalle": "1"}, **HTMX)
        self.assertContains(con_nuevo, "Detalle nuevo")
        self.assertNotContains(con_nuevo, 'class="err"')
        sin_nuevo = self.client.post(self.url + "calcular/", {**self.cambios(), "detalle-0-cantidad": "5", "quitar_nuevo": "0"}, **HTMX)
        self.assertNotContains(sin_nuevo, "Detalle nuevo")

    def test_regla_terminar_el_unico_detalle_avisa_que_equivale_a_terminar_el_contrato(self):
        """Extensión 5c.1a: aviso con el botón «Acortar la duración hasta el dd/mm/aaaa»; el botón manda `acortar_duracion` y la pantalla lo recalcula."""
        self.client.force_login(self.gerente)
        datos = {"huella": self.huella(), f"modificar-{self.d.pk}-accion": "terminar", f"modificar-{self.d.pk}-rige_visto": iso(17)}
        pagina = self.client.post(self.url + "calcular/", datos, **HTMX)
        self.assertContains(pagina, "Equivale a terminar el contrato")
        self.assertContains(pagina, "Acortar la duración hasta el")
        acortada = self.client.post(self.url + "calcular/", {**datos, "acortar_duracion": "1"}, **HTMX)
        self.assertContains(acortada, 'name="duracion" value="1"')

    def test_regla_revisar_con_htmx_muestra_la_ventana_de_resumen_y_no_escribe(self):
        """Pasos 7 a 9: «Guardar cambios» abre el resumen sobre el formulario, con cada cambio y la fecha desde la que rige; «Confirmar cambios» está ahí, no en el formulario."""
        self.client.force_login(self.e.vendedor)
        antes = self.cuenta_de_lo_escrito()
        ventana = self.client.post(self.url + "revisar/", self.cambios(), **HTMX)
        self.assertContains(ventana, "data-ventana")
        self.assertContains(ventana, f"Resumen de los cambios de {self.s.codigo}")
        self.assertContains(ventana, "Confirmar cambios")
        self.assertContains(ventana, f"rige desde el {(HOY + timedelta(days=17)):%d/%m/%Y}")
        self.assertNotContains(self.client.get(self.url), "Confirmar cambios")
        self.assertEqual(self.cuenta_de_lo_escrito(), antes)

    def test_regla_revisar_sin_javascript_es_una_pagina(self):
        """Sin JavaScript el resumen es otra página, con «Volver a la carga» y «Confirmar cambios»."""
        self.client.force_login(self.e.vendedor)
        pagina = self.client.post(self.url + "revisar/", self.cambios())
        self.assertContains(pagina, "<html")
        self.assertContains(pagina, "Resumen de los cambios de")
        self.assertContains(pagina, "Volver a la carga")
        self.assertContains(pagina, "Confirmar cambios")

    def test_ext_6a_un_dato_invalido_vuelve_al_formulario_con_el_error_en_su_campo(self):
        """6a: cantidad 0 al revisar: con HTMX, el cuerpo con el error junto al campo y `HX-Retarget` (no la ventana); sin HTMX, el formulario completo."""
        self.client.force_login(self.e.vendedor)
        malo = self.cambios(**{f"modificar-{self.d.pk}-cantidad": "0"})
        htmx = self.client.post(self.url + "revisar/", malo, **HTMX)
        self.assertEqual((htmx["HX-Retarget"], htmx["HX-Reswap"]), ("#cuerpo-mod", "innerHTML show:none"))
        self.assertContains(htmx, "Ingresá un número entero de plantas, de 1 a 500.000.")
        self.assertNotContains(htmx, "data-ventana")
        plano = self.client.post(self.url + "revisar/", malo)
        self.assertContains(plano, "<html")
        self.assertContains(plano, "Ingresá un número entero de plantas, de 1 a 500.000.")

    def test_ext_7a_sin_ningun_cambio_se_informa(self):
        """7a: revisar sin cambios muestra «No indicaste ningún cambio.» y no abre el resumen."""
        self.client.force_login(self.e.vendedor)
        pagina = self.client.post(self.url + "revisar/", {"huella": self.huella()}, **HTMX)
        self.assertContains(pagina, "No indicaste ningún cambio.")
        self.assertNotContains(pagina, "data-ventana")

    def test_flujo_principal_el_resumen_lleva_todo_y_confirmar_modifica(self):
        """Flujo de punta a punta sin JavaScript: el resumen manda de vuelta, en campos ocultos, todo lo cargado (incluida la huella y la propuesta que vio la persona);
        «Confirmar cambios» modifica: el detalle pasa a «finalizado», nace su sucesor, un solo registro de auditoría y el aviso breve; la ficha muestra «Con cambios desde» y el historial."""
        self.client.force_login(self.e.vendedor)
        resumen = self.client.post(self.url + "revisar/", self.cambios())
        confirmacion = {**campos_ocultos(resumen), "confirmar": "1"}
        self.assertEqual(confirmacion["huella"], self.huella())
        respuesta = self.client.post(self.url, confirmacion)
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.s.pk]), fetch_redirect_response=False)
        self.assertTrue(any(a.startswith(f"{self.s.codigo} modificado.") for a in avisos(respuesta)))
        self.assertEqual(DetalleSuministro.objects.get(pk=self.d.pk).estado_detalle_suministro, "finalizado")
        (sucesor,) = DetalleSuministro.objects.filter(reemplaza_a=self.d)
        self.assertEqual((sucesor.cantidad_por_periodo, sucesor.fecha_primer_entrega), (40, HOY + timedelta(days=17)))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_suministro").count(), 1)
        ficha = self.client.get(reverse("comercial:suministro", args=[self.s.pk]))
        self.assertContains(ficha, f"Con cambios desde el {(HOY + timedelta(days=17)):%d/%m/%Y}")
        self.assertContains(ficha, "Ver historial de cambios")

    def test_ext_10b_si_el_contrato_cambio_vuelve_a_la_ficha_sin_registrar_nada(self):
        """10b: con la huella vieja, «El contrato cambió mientras lo modificabas…» en la ficha; no se registra nada."""
        self.client.force_login(self.e.vendedor)
        datos = {**self.cambios(), "confirmar": "1"}
        Suministro.objects.filter(pk=self.s.pk).update(incumplimientos_tolerados=9)
        respuesta = self.client.post(self.url, datos)
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.s.pk]), fetch_redirect_response=False)
        self.assertTrue(any("El contrato cambió mientras lo modificabas" in a for a in avisos(respuesta)))
        self.assertEqual(DetalleSuministro.objects.filter(reemplaza_a=self.d).count(), 0)

    def test_ext_10a_si_un_periodo_entro_en_la_ventana_se_vuelve_a_mostrar_con_las_fechas_recalculadas(self):
        """10a: la propuesta que vio la persona ya no es la de hoy: «Desde que abriste la pantalla, un período entró en la ventana. Revisá las fechas nuevas.» con el formulario
        otra vez (la propuesta nueva en lugar de la vieja); no se registra nada."""
        self.client.force_login(self.e.vendedor)
        respuesta = self.client.post(self.url, {**self.cambios(**{f"modificar-{self.d.pk}-rige_visto": iso(10)}), "confirmar": "1"})
        self.assertContains(respuesta, "Desde que abriste la pantalla, un período entró en la ventana. Revisá las fechas nuevas.")
        self.assertContains(respuesta, f'name="modificar-{self.d.pk}-rige_visto" value="{iso(17)}"')
        self.assertEqual(DetalleSuministro.objects.filter(reemplaza_a=self.d).count(), 0)

    def test_regla_un_detalle_nuevo_se_agrega_con_su_reserva_de_la_ventana(self):
        """Extensión 5b de punta a punta con el formulario: agregar un detalle en otra dirección, revisar y confirmar; el período de la ventana queda reservado."""
        otra = direccion_de_cliente(self.e.cliente).direccion
        nuevo = {
            "detalle-0-variedad": str(self.e.variedad.pk), "detalle-0-direccion": str(otra.pk), "detalle-0-cantidad": "20", "detalle-0-periodo": "30",
            "detalle-0-primera_entrega": iso(5), "detalle-0-mecanismo": "fijo", "detalle-0-precio": "1500,50", "detalle-0-plazo_entrega": "1",
            "detalle-0-indemnizacion_retraso": "100", "detalle-0-cantidad_minima": "10", "detalle-0-indemnizacion_faltante": "50",
        }
        self.client.force_login(self.e.vendedor)
        resumen = self.client.post(self.url + "revisar/", {"huella": self.huella(), **nuevo})
        self.assertContains(resumen, "Se agrega")
        self.client.post(self.url, {**campos_ocultos(resumen), "confirmar": "1"})
        creado = DetalleSuministro.objects.exclude(pk=self.d.pk).get(suministro=self.s)
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=creado).count(), 1)

    def test_regla_con_cambios_no_hay_boton_que_lleve_a_un_403(self):
        """D-30: ninguna ficha (de Gerente ni de Vendedor, vigente, con cambios o rescindida) tiene un enlace que dé 403, incluidas las pantallas nuevas."""
        self.client.force_login(self.e.vendedor)
        self.client.post(self.url, {**campos_ocultos(self.client.post(self.url + "revisar/", self.cambios())), "confirmar": "1"})
        for cuenta in (self.e.vendedor, self.gerente):
            self.client.force_login(cuenta)
            pagina = self.client.get(reverse("comercial:suministro", args=[self.s.pk]))
            for url in set(re.findall(r'href="(/comercial/[^"#]*)"', pagina.content.decode())):
                with self.subTest(cuenta=cuenta.rol, url=url):
                    self.assertNotEqual(self.client.get(url).status_code, 403)


class ComRscSumVistaTests(BaseDeModificacionEnVistas):
    """«Rescindir suministro», «Dejar sin efecto la rescisión» y «Ver historial de cambios»."""

    def setUp(self):
        super().setUp()
        self.rescindir_url = reverse("comercial:suministro_rescindir", args=[self.s.pk])
        self.anular_url = reverse("comercial:suministro_dejar_sin_efecto", args=[self.s.pk])
        self.historial_url = reverse("comercial:suministro_historial", args=[self.s.pk])

    def pedido(self, **extra):
        """Lo que manda la ventana de rescindir: a pedido del cliente, acordado ayer, con la casilla, y lo que vio el Gerente (la huella y los períodos que se conservan)."""
        lectura = suministros.datos_de_rescision(self.gerente, self.s.pk)
        datos = {
            "motivo": "a_pedido_del_cliente", "descripcion": "", "fecha_acuerdo": iso(-1), "acuerdo": "1", "huella": lectura.huella,
            "conservado": [f"{d}:{f}" for d, f in lectura.conservados],
        }
        datos.update(extra)
        return datos

    def rescindir(self):
        lectura = suministros.datos_de_rescision(self.gerente, self.s.pk)
        suministros.rescindir_suministro(
            self.gerente, self.s.pk, suministros.PedidoDeRescision("a_pedido_del_cliente", "", iso(-1), "1"), lectura.huella, lectura.conservados
        )

    def test_regla_solo_el_gerente_rescinde_y_deja_sin_efecto(self):
        """Regla «Quién rescinde»: el Vendedor del contrato, otro Vendedor y los demás roles reciben 403 en las dos pantallas y en sus POST; el Vendedor no ve el botón."""
        self.rescindir()
        for cuenta in (self.e.vendedor, self.otro.vendedor, self.e.agronomo, crear_transportista()):
            self.client.force_login(cuenta)
            for url in (self.rescindir_url, self.anular_url):
                self.assertEqual(self.client.get(url).status_code, 403, (cuenta, url))
                self.assertEqual(self.client.post(url, {}).status_code, 403, (cuenta, url))
        self.client.logout()
        self.assertEqual(self.client.get(self.rescindir_url).status_code, 302)
        self.client.force_login(self.e.vendedor)
        self.assertNotContains(self.client.get(reverse("comercial:suministro", args=[self.s.pk])), "Dejar sin efecto la rescisión")

    def test_regla_la_ventana_de_rescindir_presenta_lo_que_pasara_y_abrirla_no_cambia_nada(self):
        """Pasos 1 y 2: con HTMX llega solo la ventana; sin JavaScript, la ficha con la ventana abierta. Dice los períodos que se conservan, la fecha de la última entrega y que no hay
        multa; lleva ocultos la huella y los períodos que ve el Gerente. Abrirla (GET) no escribe nada."""
        self.client.force_login(self.gerente)
        antes = self.cuenta_de_lo_escrito()
        htmx = self.client.get(self.rescindir_url, **HTMX)
        self.assertNotContains(htmx, "<html")
        for texto in (f"Rescindir {self.s.codigo}", (HOY + timedelta(days=10)).strftime("%d/%m/%Y"), "no lleva multa ni indemnización", "Registrar rescisión",
                      "Confirmo que la rescisión se acordó con el cliente"):
            self.assertContains(htmx, texto)
        self.assertIn("huella", campos_ocultos(htmx))  # y los períodos que vio el Gerente, en `conservado`
        self.assertContains(htmx, 'name="conservado"', count=2)
        pagina = self.client.get(self.rescindir_url)
        self.assertContains(pagina, "<html")
        self.assertContains(pagina, "Registrar rescisión")
        self.assertContains(pagina, f"{self.s.codigo}")
        self.assertEqual(self.cuenta_de_lo_escrito(), antes)

    def test_flujo_principal_registrar_la_rescision_vuelve_a_la_ficha_con_el_aviso(self):
        """Pasos 3 a 8 sin JavaScript: un POST común registra; vuelve a la ficha con el aviso breve («Se entrega hasta el dd/mm/aaaa»), el contrato sigue «vigente» y la ficha avisa la
        rescisión, sin «Modificar» ni «Rescindir» y con «Dejar sin efecto la rescisión»."""
        self.client.force_login(self.gerente)
        respuesta = self.client.post(self.rescindir_url, self.pedido())
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.s.pk]), fetch_redirect_response=False)
        self.assertTrue(any(f"Se entrega hasta el {(HOY + timedelta(days=10)):%d/%m/%Y}" in a for a in avisos(respuesta)))
        self.assertEqual(Suministro.objects.get(pk=self.s.pk).estado_suministro, "vigente")
        ficha = self.client.get(reverse("comercial:suministro", args=[self.s.pk]))
        self.assertContains(ficha, "Rescisión acordada el")
        self.assertContains(ficha, "Dejar sin efecto la rescisión")
        for texto in ("Modificar suministro", "Rescindir suministro"):
            self.assertNotContains(ficha, texto)

    def test_ext_4a_los_errores_vuelven_en_la_ventana_con_lo_cargado(self):
        """4a: sin la casilla, con «Otro» sin descripción y con fecha futura, la ficha vuelve con la ventana abierta, cada error junto a su campo y lo que se había cargado; no se registra nada."""
        self.client.force_login(self.gerente)
        respuesta = self.client.post(self.rescindir_url, self.pedido(motivo="otro", descripcion="", fecha_acuerdo=iso(2), acuerdo=""))
        self.assertEqual(respuesta.status_code, 200)
        for texto in ("Con el motivo «Otro», contá cuál fue.", "No puede ser posterior al", "Confirmá que la rescisión se acordó con el cliente"):
            self.assertContains(respuesta, texto)
        self.assertContains(respuesta, f'value="{iso(2)}"')
        self.assertIsNone(Suministro.objects.get(pk=self.s.pk).motivo_rescision)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="rescision_suministro").count(), 0)

    def test_ext_6a_si_un_periodo_entro_en_la_ventana_la_ventana_se_vuelve_a_presentar(self):
        """6a: lo que vio el Gerente ya no es lo que se conserva: «Desde que abriste la pantalla, un período entró en la ventana…» y los períodos de ahora; no se registra nada."""
        self.client.force_login(self.gerente)
        respuesta = self.client.post(self.rescindir_url, self.pedido(conservado=[f"{self.d.pk}:{iso(3)}"]))
        self.assertContains(respuesta, "Desde que abriste la pantalla, un período entró en la ventana. Revisá las fechas nuevas.")
        self.assertIsNone(Suministro.objects.get(pk=self.s.pk).motivo_rescision)

    def test_ext_6b_si_el_contrato_cambio_vuelve_a_la_ficha(self):
        """6b: con la huella vieja, a la ficha con la situación actual; y un contrato que ya tiene la rescisión no abre la ventana."""
        self.client.force_login(self.gerente)
        datos = self.pedido()
        Suministro.objects.filter(pk=self.s.pk).update(incumplimientos_tolerados=9)
        respuesta = self.client.post(self.rescindir_url, datos)
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.s.pk]), fetch_redirect_response=False)
        self.assertTrue(any("El contrato cambió mientras lo modificabas" in a for a in avisos(respuesta)))
        Suministro.objects.filter(pk=self.s.pk).update(incumplimientos_tolerados=3)
        self.rescindir()
        respuesta = self.client.get(self.rescindir_url)
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.s.pk]), fetch_redirect_response=False)
        self.assertIn("Ya tiene una rescisión acordada.", avisos(respuesta))
        htmx = self.client.get(self.rescindir_url, **HTMX)
        self.assertEqual(htmx.status_code, 204)

    def test_ext_2a_sin_periodos_conservados_la_ventana_avisa_que_queda_rescindido_en_el_acto(self):
        """2a: con todo fuera de la ventana, la ventana dice que el contrato queda rescindido al confirmar; al registrar, el aviso lo dice."""
        solo = suministro(self.e)
        detalle_suministro(solo, self.e.variedad, direccion=direccion_de_cliente(self.e.cliente).direccion, primera_en_dias=30)
        self.client.force_login(self.gerente)
        url = reverse("comercial:suministro_rescindir", args=[solo.pk])
        self.assertContains(self.client.get(url, **HTMX), "el contrato queda rescindido en el momento de confirmar")
        lectura = suministros.datos_de_rescision(self.gerente, solo.pk)
        respuesta = self.client.post(url, {"motivo": "a_pedido_de_la_empresa", "fecha_acuerdo": iso(0), "acuerdo": "1", "huella": lectura.huella})
        self.assertEqual(Suministro.objects.get(pk=solo.pk).estado_suministro, "rescindido")
        self.assertTrue(any("quedó rescindido" in a for a in avisos(respuesta)))

    def test_flujo_dejar_sin_efecto_la_rescision(self):
        """COM-ANL-RSC: la ventana pide el motivo (obligatorio: sin él, el error junto al campo y la rescisión sigue); con motivo, el contrato vuelve a «Modificar»."""
        self.rescindir()
        self.client.force_login(self.gerente)
        ventana = self.client.get(self.anular_url, **HTMX)
        self.assertContains(ventana, f"Dejar sin efecto la rescisión de {self.s.codigo}")
        sin_motivo = self.client.post(self.anular_url, {"motivo": "  ", "huella": campos_ocultos(ventana)["huella"]})
        self.assertContains(sin_motivo, "Contá por qué se deja sin efecto la rescisión.")
        self.assertTrue(Suministro.objects.get(pk=self.s.pk).tiene_rescision_acordada)
        respuesta = self.client.post(self.anular_url, {"motivo": "Siguen con el contrato", "huella": campos_ocultos(ventana)["huella"]})
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.s.pk]), fetch_redirect_response=False)
        self.assertTrue(any("la rescisión quedó sin efecto" in a for a in avisos(respuesta)))
        self.assertFalse(Suministro.objects.get(pk=self.s.pk).tiene_rescision_acordada)
        self.assertContains(self.client.get(reverse("comercial:suministro", args=[self.s.pk])), "Modificar suministro")

    def test_regla_pasada_la_ultima_entrega_ya_no_hay_boton_ni_pantalla(self):
        """Ningún botón lleva a un error: pasada la fecha de la última entrega, «Dejar sin efecto la rescisión» no se ofrece y abrir la pantalla vuelve a la ficha con el motivo."""
        self.rescindir()
        Suministro.objects.filter(pk=self.s.pk).update(fecha_ultima_entrega_rescision=HOY - timedelta(days=1))
        self.client.force_login(self.gerente)
        self.assertNotContains(self.client.get(reverse("comercial:suministro", args=[self.s.pk])), "Dejar sin efecto la rescisión")
        respuesta = self.client.get(self.anular_url)
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.s.pk]), fetch_redirect_response=False)
        self.assertIn("La rescisión ya no se puede dejar sin efecto.", avisos(respuesta))

    def test_regla_5_el_historial_es_una_ventana_de_solo_lectura_y_respeta_el_alcance(self):
        """«Ver historial de cambios»: con HTMX la ventana y sin JavaScript la ficha con la ventana abierta; trae los tramos; el Vendedor propio y el Gerente la ven, otro Vendedor recibe 403; solo GET."""
        self.client.force_login(self.e.vendedor)
        self.client.post(self.url, {**campos_ocultos(self.client.post(self.url + "revisar/", self.cambios())), "confirmar": "1"})
        ventana = self.client.get(self.historial_url, **HTMX)
        self.assertContains(ventana, f"Historial de cambios de {self.s.codigo}")
        self.assertContains(ventana, "fin del contrato")
        self.assertContains(ventana, (HOY + timedelta(days=17)).strftime("%d/%m/%Y"))
        self.assertNotContains(ventana, "<html")
        self.assertContains(self.client.get(self.historial_url), "Historial de cambios de")
        self.assertEqual(self.client.post(self.historial_url).status_code, 405)
        self.client.force_login(self.otro.vendedor)
        self.assertEqual(self.client.get(self.historial_url).status_code, 403)
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(self.historial_url).status_code, 200)

    def test_regla_la_lista_marca_la_rescision_acordada_y_el_contrato_rescindido(self):
        """La lista (COM-CNS-SUM): la marca «Rescisión acordada» y, ya cerrado, el estado «Rescindido» (también con el filtro)."""
        self.rescindir()
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"}), "Rescisión acordada")
        suministros.cerrar_rescisiones(HOY + timedelta(days=11))
        lista = self.client.get(reverse("comercial:contratos"), {"tipo": "suministro", "estado": "rescindido"})
        self.assertContains(lista, self.s.codigo)
        self.assertContains(lista, "Rescindido")
