# Pruebas de las pantallas de «Contratos» (COM-02, paso 7; docs/casos_de_uso/comercial/compra_venta.md, «Pantallas»): permisos, el flujo completo con
# HTMX y sin él, el recálculo que no escribe nada, el resumen, la ficha, el comprobante imprimible, «Reenviar comprobante» y el regreso desde el
# alta del cliente (`volver`). Las reglas de negocio ya las prueban los servicios (`test_com_reg_cvt.py`, `test_com_cns_cvt.py`): acá, los
# permisos, el flujo, los errores por campo, los botones y que nada valida al tipear.

import re
from datetime import timedelta
from unittest import mock

from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import Cliente, CompraVenta, DetalleVenta, ReservaStock
from comercial.tests.fabricas import (
    cliente as crear_cliente,
    compra_venta,
    detalle,
    direccion_de_cliente,
    escenario_comercial,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria, Usuario
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_transportista, crear_vendedor
from produccion.models import Cosecha
from produccion.tests.fabricas import lote_maduro

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()


def avisos(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class BaseDeVistas(ConDatosDeInventario, TestCase):
    """Un escenario con 100 plantas en Maduración y una compra-venta ya registrada por otro Vendedor."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.gerente = crear_gerente()
        self.otro = escenario_comercial(sufijo="2")
        self.ajena = compra_venta(self.otro, cliente_=self.e.cliente)
        detalle(self.ajena, self.otro.variedad, 5)
        self.addCleanup(verificar_invariantes_de_reservas)

    def post_de_venta(self, **extra):
        """Lo que manda el formulario completo: un envío de 30 plantas a 1500,50 dentro de 3 días."""
        datos = {
            "cliente": str(self.e.cliente.pk),
            "fecha": str(HOY + timedelta(days=3)),
            "modalidad": "envio",
            "direccion": str(self.e.direccion.pk),
            "renglon-0-variedad": str(self.e.variedad.pk),
            "renglon-0-cantidad": "30",
            "renglon-0-precio": "1500,50",
        }
        datos.update(extra)
        return {k: v for k, v in datos.items() if v is not None}


class ComRegCvtPermisosTests(BaseDeVistas):
    """Quién entra a cada pantalla (SEG-13, D-30)."""

    def urls(self):
        venta = self.ajena.pk
        return [
            reverse("comercial:contratos"),
            reverse("comercial:compra_venta_nueva"),
            reverse("comercial:compra_venta", args=[venta]),
            reverse("comercial:compra_venta_comprobante", args=[venta]),
        ]

    def test_pre_a_los_demas_roles_reciben_403_y_el_anonimo_va_al_inicio_de_sesion(self):
        """Precondición a: Agrónomo, Capataz, Transportista y cualquier otro rol reciben 403 en todas las pantallas y en cada POST; sin sesión, a iniciar sesión."""
        posts = [reverse("comercial:compra_venta_calcular"), reverse("comercial:compra_venta_revisar"),
                 reverse("comercial:compra_venta_reenviar_comprobante", args=[self.ajena.pk])]
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

    def test_regla_1_el_vendedor_no_abre_la_ficha_ni_el_comprobante_de_otro_vendedor(self):
        """Regla 1 de COM-CNS-CVT y SEG-13: 403 con mensaje; un id inexistente, 404."""
        self.client.force_login(self.e.vendedor)
        for nombre in ("compra_venta", "compra_venta_comprobante"):
            respuesta = self.client.get(reverse(f"comercial:{nombre}", args=[self.ajena.pk]))
            self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.client.get(reverse("comercial:compra_venta", args=[999999])).status_code, 404)

    def test_regla_2_el_vendedor_no_ve_el_filtro_de_vendedor_y_el_gerente_si(self):
        """Regla 2 de COM-CNS-CVT: el filtro «Vendedor» es solo del Gerente (y la lista del Vendedor trae solo lo suyo)."""
        self.client.force_login(self.e.vendedor)
        pagina = self.client.get(reverse("comercial:contratos"))
        self.assertNotContains(pagina, 'aria-label="Vendedor"')
        self.assertNotContains(pagina, self.ajena.codigo)
        self.client.force_login(self.gerente)
        pagina = self.client.get(reverse("comercial:contratos"))
        self.assertContains(pagina, 'aria-label="Vendedor"')
        self.assertContains(pagina, self.ajena.codigo)

    def test_regla_ningun_boton_lleva_a_un_403(self):
        """D-30: el Vendedor no ve «Reenviar comprobante» en la ficha de una venta que no es suya (ni la ve), y la ficha propia solo ofrece lo que puede."""
        propia = compra_venta(self.e)
        detalle(propia, self.e.variedad, 5)
        self.client.force_login(self.e.vendedor)
        pagina = self.client.get(reverse("comercial:compra_venta", args=[propia.pk]))
        self.assertContains(pagina, "Reenviar comprobante")
        self.assertNotContains(pagina, "Cancelar compra-venta")  # lo agrega COM-05b (D-25)
        for url in re.findall(r'href="(/comercial/[^"]*)"', pagina.content.decode()):
            self.assertNotEqual(self.client.get(url).status_code, 403, url)

    def test_pre_b_sin_invernaderos_activos_nueva_compra_venta_se_muestra_deshabilitado_con_su_motivo(self):
        """Precondición b: la lista muestra el botón deshabilitado con el motivo, y el POST de registro no registra nada."""
        sin_invernaderos = crear_vendedor(email="sin@infoponia.com")
        self.client.force_login(sin_invernaderos)
        pagina = self.client.get(reverse("comercial:contratos"))
        self.assertContains(pagina, "No tenés invernaderos activos asignados: pedile al Gerente que te asigne uno.")
        self.assertContains(pagina, 'aria-disabled="true"')
        self.client.post(reverse("comercial:compra_venta_nueva"), {**self.post_de_venta(), "confirmar": "1"})
        self.assertEqual(CompraVenta.objects.filter(vendedor=sin_invernaderos).count(), 0)


class ComRegCvtVistaTests(BaseDeVistas):
    """El flujo de «Nueva compra-venta», con HTMX y sin él."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.e.vendedor)
        self.nueva = reverse("comercial:compra_venta_nueva")
        self.calcular = reverse("comercial:compra_venta_calcular")
        self.revisar = reverse("comercial:compra_venta_revisar")

    def test_flujo_principal_con_htmx_calcula_revisa_y_confirma(self):
        """Pasos 1 a 17 con HTMX: el recálculo devuelve el cuerpo del formulario sin escribir nada; «Revisar y registrar» devuelve solo la
        ventana del resumen con el monto estimado; «Confirmar» registra y redirige a la ficha con el aviso breve."""
        filas = lambda: (CompraVenta.objects.count(), DetalleVenta.objects.count(), ReservaStock.objects.count(), Cosecha.objects.count(), RegistroAuditoria.objects.count())  # noqa: E731
        antes = filas()
        cuerpo = self.client.post(self.calcular, self.post_de_venta(), **HTMX)
        self.assertContains(cuerpo, "Disponible: 100 plantas")
        self.assertContains(cuerpo, "$ 45.015,00")
        self.assertNotContains(cuerpo, "<html")
        self.assertEqual(filas(), antes)  # `calcular/` no escribe nada
        ventana = self.client.post(self.revisar, self.post_de_venta(), **HTMX)
        self.assertContains(ventana, "Resumen de la compra-venta")
        self.assertContains(ventana, "Confirmar compra-venta")
        self.assertContains(ventana, "Volver a la carga")
        self.assertContains(ventana, "$ 45.015,00")
        self.assertNotContains(ventana, "<html")
        self.assertEqual(filas(), antes)  # el resumen tampoco
        respuesta = self.client.post(self.nueva, {**self.post_de_venta(), "confirmar": "1"})
        venta = CompraVenta.objects.exclude(pk=self.ajena.pk).get()
        self.assertRedirects(respuesta, reverse("comercial:compra_venta", args=[venta.pk]))
        self.assertTrue(any(f"{venta.codigo} registrada. Se reservó el stock y se programó 1 cosecha." in a for a in avisos(respuesta)))
        self.assertEqual(Notificacion.objects.filter(titulo__startswith="Nueva cosecha").count(), 2)

    def test_flujo_principal_sin_javascript_actualizar_resumen_como_pagina_y_confirmar(self):
        """Sin JavaScript: «Actualizar» vuelve a mostrar la página con los cálculos; «Revisar y registrar» lleva a una página de resumen con los datos
        como campos ocultos; «Volver a la carga» (13a) la devuelve con todo lo cargado; «Confirmar» registra."""
        pagina = self.client.post(self.nueva, {**self.post_de_venta(), "actualizar": "1"})
        self.assertContains(pagina, "<html")
        self.assertContains(pagina, "Disponible: 100 plantas")
        resumen = self.client.post(self.revisar, self.post_de_venta())
        self.assertContains(resumen, "<html")
        self.assertContains(resumen, 'name="renglon-0-cantidad" value="30"')
        volver = self.client.post(self.nueva, {**self.post_de_venta(), "actualizar": "1"})
        self.assertContains(volver, 'value="30"')
        self.client.post(self.nueva, {**self.post_de_venta(), "confirmar": "1"})
        self.assertEqual(CompraVenta.objects.exclude(pk=self.ajena.pk).count(), 1)

    def test_ext_10a_el_error_por_campo_se_muestra_en_su_campo_y_no_se_registra_nada(self):
        """Extensiones 10a y 10c: con una cantidad que supera lo disponible y un precio en cero, cada error aparece junto a su campo (con HTMX, el
        resumen devuelve el cuerpo con los errores y `HX-Retarget`)."""
        datos = self.post_de_venta(**{"renglon-0-cantidad": "500", "renglon-0-precio": "0"})
        respuesta = self.client.post(self.revisar, datos, **HTMX)
        self.assertContains(respuesta, "Hay 100 plantas disponibles para esa fecha.")
        self.assertContains(respuesta, "Ingresá un precio mayor que cero")
        self.assertEqual(respuesta["HX-Retarget"], "#cuerpo-cv")
        sin_js = self.client.post(self.nueva, {**datos, "confirmar": "1"})
        self.assertContains(sin_js, "Hay 100 plantas disponibles para esa fecha.")
        self.assertEqual(CompraVenta.objects.exclude(pk=self.ajena.pk).count(), 0)

    def test_ext_14a_si_el_stock_cambio_el_formulario_marca_los_renglones_y_avisa(self):
        """Extensión 14a: «El stock cambió mientras cargabas la venta.» y la nueva cantidad máxima en cada renglón afectado."""
        falso = {self.e.variedad.pk: mock.Mock(total=1000, lotes=1000, partidas=0)}
        with mock.patch("comercial.servicios.compra_ventas.stock_maduro.disponible", return_value=falso):
            respuesta = self.client.post(self.nueva, {**self.post_de_venta(**{"renglon-0-cantidad": "500"}), "confirmar": "1"})
        self.assertContains(respuesta, "El stock cambió mientras cargabas la venta.")
        self.assertEqual(CompraVenta.objects.exclude(pk=self.ajena.pk).count(), 0)

    def test_regla_nunca_se_valida_ni_se_recalcula_mientras_se_tipea(self):
        """`.claude/rules/interfaz.md`: ningún campo de texto, de número o de fecha lleva disparadores de HTMX; solo los selectores (y los botones) redibujan,
        sin validar, con `hx-swap="innerHTML show:none"` y `data-sin-envio-en-curso`."""
        pagina = self.client.post(self.calcular, self.post_de_venta(), **HTMX).content.decode()
        self.assertNotRegex(pagina, r"hx-trigger=\"[^\"]*(input|keyup|delay)")
        for etiqueta in re.findall(r"<input[^>]*>", pagina):
            if 'type="text"' in etiqueta or 'type="date"' in etiqueta or 'type="search"' in etiqueta:
                self.assertNotIn("hx-", etiqueta, etiqueta)
        selectores = re.findall(r"<select[^>]*>", pagina)
        self.assertTrue(selectores)
        for etiqueta in selectores:
            self.assertIn('hx-swap="innerHTML show:none"', etiqueta)
            self.assertIn("data-sin-envio-en-curso", etiqueta)

    def test_regla_el_boton_de_confirmar_muestra_registrando(self):
        """Requisito especial: el botón muestra «Registrando…» y se deshabilita al enviar (`data-enviando`, indicador de progreso), siempre."""
        ventana = self.client.post(self.revisar, self.post_de_venta(), **HTMX)
        self.assertContains(ventana, 'data-enviando="Registrando…"')

    def test_regla_las_secciones_bloqueadas_dicen_que_falta(self):
        """Criterio de interfaz: Entrega se habilita con el cliente y Variedades con la fecha y la dirección o el invernadero."""
        vacio = self.client.get(self.nueva)
        self.assertContains(vacio, "Elegí primero el cliente.")
        self.assertContains(vacio, "Completá la fecha y")
        con_cliente = self.client.get(self.nueva, {"cliente": self.e.cliente.pk})
        self.assertNotContains(con_cliente, "Elegí primero el cliente.")
        self.assertContains(con_cliente, "El día en que el cliente recibe o retira el producto. Puede ser hoy.")

    def test_regla_el_buscador_de_clientes_ofrece_elegir_y_el_alta_cuando_no_hay_coincidencias(self):
        """Pasos 3 y 3a (`buscar_clientes`): desde 2 caracteres, por nombre o CUIT; sin coincidencias, «No hay clientes que coincidan.» con el enlace al alta."""
        encontrado = self.client.post(self.calcular, {"cliente_q": str(self.e.cliente)[:5]}, **HTMX)
        self.assertContains(encontrado, "Elegir")
        self.assertContains(encontrado, str(self.e.cliente))
        nada = self.client.post(self.calcular, {"cliente_q": "zzzzzz"}, **HTMX)
        self.assertContains(nada, "No hay clientes que coincidan.")
        self.assertContains(nada, reverse("comercial:cliente_nuevo"))

    def test_ext_1a_el_gerente_elige_al_vendedor_y_registra_a_su_nombre(self):
        """Extensión 1a: el formulario del Gerente pide el Vendedor responsable; la venta queda de ese Vendedor."""
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(self.nueva), "Vendedor responsable")
        self.client.post(self.nueva, {**self.post_de_venta(vendedor=str(self.e.vendedor.pk)), "confirmar": "1"})
        self.assertEqual(CompraVenta.objects.exclude(pk=self.ajena.pk).get().vendedor_id, self.e.vendedor.pk)

    def test_regla_el_vendedor_no_ve_el_selector_de_vendedor(self):
        """Paso 1: el Vendedor es el responsable y no lo elige."""
        self.assertNotContains(self.client.get(self.nueva), "Vendedor responsable")

    def test_ext_16b_un_cliente_sin_correo_ofrece_el_comprobante_impreso(self):
        """Extensión 16b: la pantalla avisa que el comprobante va impreso y el aviso final lo recuerda."""
        sin_correo = crear_cliente(razon_social="Sin correo S.A.", email="")
        vinculo = direccion_de_cliente(sin_correo)
        datos = self.post_de_venta(cliente=str(sin_correo.pk), direccion=str(vinculo.direccion_id))
        self.assertContains(self.client.post(self.calcular, datos, **HTMX), "El cliente no tiene correo: el comprobante se entrega impreso.")
        respuesta = self.client.post(self.nueva, {**datos, "confirmar": "1"})
        self.assertTrue(any("imprimí el comprobante" in a for a in avisos(respuesta)))

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_16a_si_el_correo_falla_el_aviso_lo_dice_y_la_ficha_ofrece_reenviar(self):
        """Extensión 16a: «No se pudo enviar el comprobante a {correo}. Podés reenviarlo desde la ficha.»; la ficha ofrece «Reenviar comprobante»,
        que (con el correo ya andando) deja el comprobante enviado."""
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=False):
            respuesta = self.client.post(self.nueva, {**self.post_de_venta(), "confirmar": "1"})
        self.assertTrue(any("No se pudo enviar el comprobante a cliente@ejemplo.com. Podés reenviarlo desde la ficha." in a for a in avisos(respuesta)))
        venta = CompraVenta.objects.exclude(pk=self.ajena.pk).get()
        ficha = self.client.get(reverse("comercial:compra_venta", args=[venta.pk]))
        self.assertContains(ficha, "Pendiente de envío")
        self.assertContains(ficha, "Reenviar comprobante")
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=True):
            reenvio = self.client.post(reverse("comercial:compra_venta_reenviar_comprobante", args=[venta.pk]))
        self.assertRedirects(reenvio, reverse("comercial:compra_venta", args=[venta.pk]))
        self.assertEqual(CompraVenta.objects.get(pk=venta.pk).estado_comprobante, "enviado")
        self.assertNotContains(self.client.get(reverse("comercial:compra_venta", args=[venta.pk])), "Reenviar comprobante")

    def test_regla_reenviar_es_un_post_y_no_acepta_get(self):
        """Reenviar comprobante cambia datos (el estado): solo POST."""
        self.assertEqual(self.client.get(reverse("comercial:compra_venta_reenviar_comprobante", args=[self.ajena.pk])).status_code, 405)


class VolverDesdeElClienteTests(BaseDeVistas):
    """Extensiones 4a y 7a: el alta del cliente y la nueva dirección vuelven a «Nueva compra-venta» con lo elegido (regla 7 de ALT, regla 5 de MOD)."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.e.vendedor)

    def test_ext_4a_el_enlace_al_alta_lleva_los_datos_de_las_secciones_1_y_2_y_avisa_de_las_variedades(self):
        """Pasos 3a.2a y 4a: el enlace «Registrar o reactivar un cliente» lleva `volver` con vendedor, cliente, fecha, modalidad e invernadero (las variedades no
        viajan: lo avisa antes)."""
        pagina = self.client.get(reverse("comercial:compra_venta_nueva"), {"fecha": str(HOY + timedelta(days=3)), "modalidad": "retiro"})
        enlace = re.search(r'href="(/comercial/clientes/nuevo/\?volver=[^"]+)"', pagina.content.decode())
        self.assertIsNotNone(enlace)
        self.assertIn("modalidad%3Dretiro", enlace.group(1))
        con_variedades = self.client.post(reverse("comercial:compra_venta_calcular"), self.post_de_venta(cliente=None), **HTMX)
        self.assertContains(con_variedades, "Vas a tener que volver a cargar las variedades.")

    def test_ext_4a_tras_el_alta_vuelve_a_la_venta_con_el_cliente_elegido(self):
        """Regla 7 de COM-ALT-CLT: el alta vuelve a «Nueva compra-venta» con el cliente nuevo elegido y lo ya cargado en la consulta."""
        volver = reverse("comercial:compra_venta_nueva") + f"?fecha={HOY}&modalidad=retiro"
        respuesta = self.client.post(
            reverse("comercial:cliente_nuevo"),
            {"tipo_cliente": "juridica", "cuit": "30-71234567-1", "razon_social": "Nuevo S.A.", "volver": volver},
        )
        nuevo = Cliente.objects.get(razon_social_cliente="Nuevo S.A.")
        self.assertRedirects(respuesta, f"{volver}&cliente={nuevo.pk}", fetch_redirect_response=False)
        pagina = self.client.get(f"{volver}&cliente={nuevo.pk}")
        self.assertContains(pagina, "Nuevo S.A.")
        self.assertContains(pagina, f'name="cliente" value="{nuevo.pk}"')

    def test_ext_7a_el_enlace_a_la_modificacion_y_el_regreso_con_la_direccion_nueva(self):
        """Extensión 7a y regla 5 de COM-MOD-CLT: «Agregar una dirección al cliente» abre su modificación con `volver`; al guardar, vuelve con
        `direccion=<id>` de la dirección recién creada, que queda elegida."""
        from maestros.tests.fabricas import localidad

        pagina = self.client.get(reverse("comercial:compra_venta_nueva"), {"cliente": self.e.cliente.pk, "modalidad": "envio"})
        self.assertContains(pagina, reverse("comercial:cliente_modificar", args=[self.e.cliente.pk]))
        volver = reverse("comercial:compra_venta_nueva") + f"?cliente={self.e.cliente.pk}&modalidad=envio"
        datos = {
            "tipo_cliente": "juridica", "cuit": self.e.cliente.cuit_cliente, "razon_social": self.e.cliente.razon_social_cliente,
            "email": self.e.cliente.email_cliente, "volver": volver,
            f"corregida-{self.e.direccion.pk}-tipo_direccion": "urbana", f"corregida-{self.e.direccion.pk}-localidad": localidad().pk,
            f"corregida-{self.e.direccion.pk}-calle": "San Martín", f"corregida-{self.e.direccion.pk}-numero_calle": "123",
            "nueva-0-tipo_direccion": "urbana", "nueva-0-localidad": localidad().pk, "nueva-0-calle": "Belgrano", "nueva-0-numero_calle": "45",
        }
        respuesta = self.client.post(reverse("comercial:cliente_modificar", args=[self.e.cliente.pk]), datos)
        nueva = self.e.cliente.direcciones.exclude(direccion_id=self.e.direccion.pk).get().direccion_id
        esperada = reverse("comercial:compra_venta_nueva") + f"?cliente={self.e.cliente.pk}&direccion={nueva}&modalidad=envio"
        self.assertRedirects(respuesta, esperada, fetch_redirect_response=False)
        self.assertContains(self.client.get(esperada), f'<option value="{nueva}" selected>')

    def test_regla_un_volver_externo_se_descarta(self):
        """Regla 7 de COM-ALT-CLT: solo vuelve a URLs internas; con una externa, va a la ficha del cliente."""
        respuesta = self.client.post(
            reverse("comercial:cliente_nuevo"),
            {"tipo_cliente": "juridica", "cuit": "30-71234567-1", "razon_social": "Nuevo S.A.", "volver": "https://evil.example.com/?x=1"},
        )
        nuevo = Cliente.objects.get(razon_social_cliente="Nuevo S.A.")
        self.assertRedirects(respuesta, reverse("comercial:cliente", args=[nuevo.pk]))


class ComCnsCvtVistaTests(BaseDeVistas):
    """La lista, la ficha y el comprobante imprimible."""

    def setUp(self):
        super().setUp()
        self.propia = compra_venta(self.e)
        detalle(self.propia, self.e.variedad, 10, precio="100.00")
        self.client.force_login(self.e.vendedor)

    def test_regla_3_la_lista_muestra_cliente_entrega_monto_y_estado_con_la_etiqueta_estimado(self):
        """Regla 3: compra-venta, cliente, entrega (modalidad y fecha pactada), monto («estimado» si está abierta) y estado."""
        pagina = self.client.get(reverse("comercial:contratos"))
        self.assertContains(pagina, self.propia.codigo)
        self.assertContains(pagina, "$ 1.000,00")
        self.assertContains(pagina, "estimado")
        self.assertContains(pagina, "Abierta")
        self.assertContains(pagina, reverse("comercial:compra_venta", args=[self.propia.pk]))

    def test_regla_2_los_filtros_van_en_la_url_y_el_vacio_dice_que_no_hay_coincidencias(self):
        """Regla 2: los filtros se pueden compartir; sin resultados, «Ninguna compra-venta coincide con los filtros.»."""
        self.assertContains(self.client.get(reverse("comercial:contratos"), {"estado": "cancelada"}), "Ninguna compra-venta coincide con los filtros.")
        self.assertContains(self.client.get(reverse("comercial:contratos"), {"estado": "abierta"}), self.propia.codigo)

    def test_regla_4_la_ficha_muestra_el_detalle_el_comprobante_y_no_ofrece_cancelar(self):
        """Regla 4 y D-25: cliente con enlace, Vendedor, destino, fechas, detalle con subtotal y el aviso de entregas; sin «Cancelar compra-venta»."""
        pagina = self.client.get(reverse("comercial:compra_venta", args=[self.propia.pk]))
        for texto in (self.e.cliente.razon_social_cliente, "San Martín 123", "Abierto", "$ 1.000,00", "La entrega se planifica cuando todo el producto esté listo."):
            self.assertContains(pagina, texto)
        self.assertContains(pagina, reverse("comercial:cliente", args=[self.e.cliente.pk]))
        self.assertNotContains(pagina, "Cancelar compra-venta")

    def test_regla_el_comprobante_imprimible_es_una_pagina_sin_menu_con_la_leyenda(self):
        """Extensiones 16a y 16b: una página con estilos de impresión, sin menú, que dice «Comprobante interno, sin validez fiscal. El pago se realiza
        al recibir el producto.»; existe para toda venta del alcance."""
        pagina = self.client.get(reverse("comercial:compra_venta_comprobante", args=[self.propia.pk]))
        self.assertContains(pagina, "Comprobante interno, sin validez fiscal. El pago se realiza al recibir el producto.")
        self.assertContains(pagina, self.propia.codigo)
        self.assertContains(pagina, "$ 1.000,00")
        self.assertNotContains(pagina, 'class="menu')

    def test_regla_la_ficha_del_cliente_muestra_sus_compra_ventas_y_la_lista_sus_contratos_vigentes(self):
        """COM-02 completa COM-01: la ficha del cliente lista sus compra-ventas (el Vendedor, solo las suyas) y la lista cuenta «Contratos vigentes»."""
        ficha = self.client.get(reverse("comercial:cliente", args=[self.e.cliente.pk]))
        self.assertContains(ficha, self.propia.codigo)
        self.assertNotContains(ficha, self.ajena.codigo)
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(reverse("comercial:cliente", args=[self.e.cliente.pk])), self.ajena.codigo)
        lista = self.client.get(reverse("comercial:clientes"))
        self.assertContains(lista, "Contratos vigentes")

    def test_ext_la_baja_del_cliente_informa_las_compra_ventas_abiertas(self):
        """COM-BAJ-CLT, regla 1: la ventana de baja informa «Compra-ventas abiertas: N» (no bloquea)."""
        self.client.force_login(self.gerente)
        ventana = self.client.get(reverse("comercial:cliente_baja", args=[self.e.cliente.pk]), **HTMX)
        self.assertContains(ventana, "Compra-ventas abiertas: 2")

    def test_regla_la_direccion_usada_por_una_venta_no_se_puede_borrar_en_el_formulario_del_cliente(self):
        """Regla 4 de COM-MOD-CLT: con una venta con envío a esa dirección, el formulario no ofrece «Borrar» (con datos reales, sin simular)."""
        compra_venta(self.e)
        pagina = self.client.get(reverse("comercial:cliente_modificar", args=[self.e.cliente.pk]))
        self.assertNotContains(pagina, f'name="borrar" value="{self.e.direccion.pk}"')


class AgregarVariedadTests(BaseDeVistas):
    """«+ Agregar variedad» (COM-REG-CVT, paso 9 y extensión 9-10a; corrección del 23/11/2026): el botón suma un renglón en blanco conservando todo lo
    cargado, con HTMX y sin JavaScript, y cuando hay stock el formulario siempre ofrece al menos un renglón para completar."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.e.vendedor)
        self.nueva = reverse("comercial:compra_venta_nueva")
        self.calcular = reverse("comercial:compra_venta_calcular")

    def renglones(self, respuesta):
        """Los índices de los renglones dibujados (un selector de variedad por renglón)."""
        return [int(i) for i in re.findall(r'name="renglon-(\d+)-variedad"', respuesta.content.decode())]

    def sin_renglones(self, **extra):
        """Secciones 1 y 2 completas (envío) y ningún renglón: el estado en que el Vendedor llega a la sección 3."""
        datos = self.post_de_venta(**extra)
        return {k: v for k, v in datos.items() if not k.startswith("renglon-")}

    def test_regla_con_stock_y_sin_renglones_el_formulario_ofrece_un_renglon_en_blanco(self):
        """Paso 9 de COM-REG-CVT: con stock para la fecha y el destino, la sección 3 arranca con un renglón listo para completar, sin errores."""
        for respuesta in (
            self.client.post(self.calcular, self.sin_renglones(), **HTMX),
            self.client.post(self.nueva, {**self.sin_renglones(), "actualizar": "1"}),
            self.client.get(self.nueva, self.sin_renglones()),
        ):
            self.assertEqual(self.renglones(respuesta), [0])
            self.assertNotContains(respuesta, "Elegí la variedad.")
            self.assertNotContains(respuesta, "Ingresá un número entero de plantas.")
            self.assertContains(respuesta, "Agregar variedad")

    def test_ext_9_agregar_variedad_con_htmx_suma_un_renglon_y_conserva_lo_cargado(self):
        """«Agregar variedad» con HTMX: el cuerpo vuelve con un renglón más (en blanco) y con el cliente, la fecha, la modalidad, la dirección y el
        renglón ya cargado intactos; no escribe nada."""
        antes = CompraVenta.objects.count()
        cuerpo = self.client.post(self.calcular, {**self.post_de_venta(), "agregar_renglon": "1"}, **HTMX)
        self.assertEqual(self.renglones(cuerpo), [0, 1])
        self.assertNotContains(cuerpo, "<html")
        self.assertContains(cuerpo, f'name="cliente" value="{self.e.cliente.pk}"')
        self.assertContains(cuerpo, f'value="{HOY + timedelta(days=3)}"')
        self.assertContains(cuerpo, 'name="modalidad" value="envio" checked')
        self.assertContains(cuerpo, f'<option value="{self.e.direccion.pk}" selected>')
        self.assertContains(cuerpo, f'<option value="{self.e.variedad.pk}" selected>')
        self.assertContains(cuerpo, 'name="renglon-0-cantidad" value="30"')
        self.assertContains(cuerpo, 'name="renglon-0-precio" value="1500,50"')
        self.assertNotContains(cuerpo, "Elegí la variedad.")
        self.assertEqual(CompraVenta.objects.count(), antes)

    def test_ext_9_agregar_variedad_sin_javascript_devuelve_la_pagina_con_un_renglon_mas(self):
        """«Agregar variedad» sin JavaScript (POST del formulario): la página completa vuelve con un renglón más y todo lo cargado conservado."""
        pagina = self.client.post(self.nueva, {**self.post_de_venta(), "agregar_renglon": "1"})
        self.assertContains(pagina, "<html")
        self.assertEqual(self.renglones(pagina), [0, 1])
        self.assertContains(pagina, f'name="cliente" value="{self.e.cliente.pk}"')
        self.assertContains(pagina, 'name="modalidad" value="envio" checked')
        self.assertContains(pagina, f'<option value="{self.e.direccion.pk}" selected>')
        self.assertContains(pagina, 'name="renglon-0-cantidad" value="30"')
        self.assertEqual(CompraVenta.objects.exclude(pk=self.ajena.pk).count(), 0)

    def test_ext_9_agregar_varias_veces_numera_los_renglones_sin_repetir_indices(self):
        """Cada clic suma un renglón con el índice siguiente, también después de «Quitar» uno del medio (los campos y sus errores se nombran por índice)."""
        datos = {**self.post_de_venta(), "renglon-1-variedad": "", "renglon-1-cantidad": "", "renglon-1-precio": ""}
        con_tres = self.client.post(self.calcular, {**datos, "agregar_renglon": "1"}, **HTMX)
        self.assertEqual(self.renglones(con_tres), [0, 1, 2])
        datos.update({"renglon-2-variedad": "", "renglon-2-cantidad": "", "renglon-2-precio": ""})
        quitado = self.client.post(self.calcular, {**datos, "quitar": "1"}, **HTMX)
        self.assertEqual(self.renglones(quitado), [0, 2])
        agregado = self.client.post(self.calcular, {**datos, "quitar": "1", "agregar_renglon": "1"}, **HTMX)
        self.assertEqual(self.renglones(agregado), [0, 2, 3])

    def test_ext_9_agregar_variedad_conserva_el_vendedor_y_el_invernadero_de_retiro_del_gerente(self):
        """Extensión 1a y paso 5a: con el Gerente, el Vendedor elegido y el invernadero de retiro siguen elegidos al agregar un renglón."""
        self.client.force_login(self.gerente)
        datos = self.post_de_venta(vendedor=str(self.e.vendedor.pk), modalidad="retiro", direccion=None, invernadero=str(self.e.invernadero.pk))
        cuerpo = self.client.post(self.calcular, {**datos, "agregar_renglon": "1"}, **HTMX)
        self.assertEqual(self.renglones(cuerpo), [0, 1])
        self.assertContains(cuerpo, f'<option value="{self.e.vendedor.pk}" selected>')
        self.assertContains(cuerpo, 'name="modalidad" value="retiro" checked')

    def test_regla_el_renglon_en_blanco_no_cuenta_en_el_resumen(self):
        """«Variedades» del resumen cuenta solo los renglones con algo cargado, y el monto estimado no cambia por el renglón en blanco."""
        cuerpo = self.client.post(self.calcular, {**self.post_de_venta(), "agregar_renglon": "1"}, **HTMX)
        self.assertContains(cuerpo, "<dt>Variedades</dt><dd>1</dd>")
        self.assertContains(cuerpo, "$ 45.015,00")
        vacio = self.client.post(self.calcular, self.sin_renglones(), **HTMX)
        self.assertContains(vacio, "<dt>Variedades</dt><dd>0</dd>")

    def test_regla_registrar_ignora_los_renglones_en_blanco(self):
        """Pasos 11 y 15: un renglón en blanco (el que dejó «Agregar variedad») no es un renglón de la venta: se registra con el renglón cargado."""
        datos = {**self.post_de_venta(), "renglon-1-variedad": "", "renglon-1-cantidad": "", "renglon-1-precio": "", "confirmar": "1"}
        self.client.post(self.nueva, datos)
        venta = CompraVenta.objects.exclude(pk=self.ajena.pk).get()
        self.assertEqual(DetalleVenta.objects.filter(compra_venta=venta).count(), 1)

    def test_ext_10a_con_solo_renglones_en_blanco_registrar_pide_cargar_una_variedad(self):
        """Paso 11: sin ninguna variedad cargada, «Cargá al menos una variedad.» y nada se registra (con el renglón en blanco a la vista)."""
        datos = {**self.sin_renglones(), "renglon-0-variedad": "", "renglon-0-cantidad": "", "renglon-0-precio": ""}
        pagina = self.client.post(self.nueva, {**datos, "confirmar": "1"})
        self.assertContains(pagina, "Cargá al menos una variedad.")
        self.assertEqual(self.renglones(pagina), [0])
        self.assertNotContains(pagina, "Elegí la variedad.")
        self.assertEqual(CompraVenta.objects.exclude(pk=self.ajena.pk).count(), 0)
