# Pruebas de las pantallas de la ruta y la concreción (COM-06a, paso 6; docs/casos_de_uso/comercial/rutas.md, «Pantallas» y «Pruebas»): permisos (el Transportista, solo lo suyo; el Vendedor, solo los retiros de sus
# contratos; el Gerente, el Agrónomo y el Capataz no concretan: 403, y **ningún botón lleva a un 403**), el flujo completo con HTMX y sin JavaScript (la plantilla, no un navegador), que `calcular/` no escribe
# nada (cuenta de filas igual antes y después), la entrada «Mi ruta», la sección «Ruta de hoy» del Panel de control, «Concretar retiro» en la lista de entregas y las secciones nuevas de las fichas (compra-venta,
# suministro y cliente). El cliente de Django no ve el CSRF ni el JavaScript: eso va como paso de «navegador real» en la «Verificación a mano».

from datetime import timedelta
from decimal import Decimal
from html import unescape

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import Entrega, IntentoFallido, PagoCliente
from comercial.servicios import clientes, rutas
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    entrega,
    entrega_concretable,
    envase,
    escenario_comercial,
    reserva_lista,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_solicitudes,
)
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_agronomo, crear_vendedor
from produccion.tests.fabricas import lote_maduro

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class Base(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 5000)
        self.gerente = crear_gerente()
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)

    def concretable(self, **opciones):
        return entrega_concretable(self.e, self.lote, **opciones)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def get(self, cuenta, nombre, *args, **extra):
        self.entrar(cuenta)
        return self.client.get(reverse(f"comercial:{nombre}", args=args), **extra)

    def post(self, cuenta, nombre, datos=None, *args, **extra):
        self.entrar(cuenta)
        return self.client.post(reverse(f"comercial:{nombre}", args=args), datos or {}, **extra)

    def linea(self, x):
        return x.entrega.lineas.get()

    def formulario(self, x, **extra):
        """Lo que manda el formulario de concretar con todo por omisión (venta: acepta todo, sin envases) más `extra`."""
        datos = {f"llego_{self.linea(x).pk}": "50", f"acepta_{self.linea(x).pk}": "1", "sin_envases": "1", "medio_pago": "efectivo"}
        datos.update(extra)
        return datos

    def huella_de(self, respuesta):
        html = respuesta.content.decode()  # crudo: la huella es JSON y la plantilla escapa sus comillas (&quot;)
        i = html.index('name="huella" value="') + len('name="huella" value="')
        return unescape(html[i : html.index('"', i)])


class PermisosTests(Base):
    def test_regla_solo_el_transportista_ve_mi_ruta(self):
        """«Mi ruta» es del Transportista: el Gerente, el Vendedor, el Agrónomo y el Capataz reciben 403; el Transportista, 200."""
        t = transportista_con_vehiculo(self.e.invernadero)
        self.assertEqual(self.get(t, "ruta").status_code, 200)
        for cuenta in (self.gerente, self.e.vendedor, crear_agronomo(email="a2@infoponia.com"), crear_capataz(email="capataz.ajeno@infoponia.com")):
            self.assertEqual(self.get(cuenta, "ruta").status_code, 403, cuenta)
            self.assertEqual(self.get(cuenta, "ruta_iniciar").status_code, 403, cuenta)
            self.assertEqual(self.get(cuenta, "ruta_finalizar").status_code, 403, cuenta)

    def test_regla_gerente_agronomo_y_capataz_no_concretan_y_el_vendedor_solo_un_retiro_propio(self):
        """Regla «Entrega concretable»: 403 para el Gerente, el Agrónomo, el Capataz, otro transportista, el Vendedor (en una entrega con envío) y el Transportista (en un retiro)."""
        envio, retiro = self.concretable(), self.concretable(retiro=True)
        otro = transportista_con_vehiculo(self.e.invernadero)
        ajeno = crear_vendedor(email="otro.vendedor@infoponia.com")
        for cuenta in (self.gerente, crear_agronomo(email="a2@infoponia.com"), crear_capataz(email="capataz.ajeno@infoponia.com"), otro, self.e.vendedor):
            self.assertEqual(self.get(cuenta, "entrega_concretar", envio.entrega.pk).status_code, 403, cuenta)
            self.assertEqual(self.post(cuenta, "entrega_concretar_calcular", self.formulario(envio), envio.entrega.pk).status_code, 403, cuenta)
            self.assertEqual(self.post(cuenta, "entrega_concretar", self.formulario(envio), envio.entrega.pk).status_code, 403, cuenta)
        for cuenta in (self.gerente, envio.transportista, ajeno):
            self.assertEqual(self.get(cuenta, "entrega_concretar", retiro.entrega.pk).status_code, 403, cuenta)
        self.assertEqual(self.get(envio.transportista, "entrega_concretar", envio.entrega.pk).status_code, 200)
        self.assertEqual(self.get(self.e.vendedor, "entrega_concretar", retiro.entrega.pk).status_code, 200)

    def test_regla_el_intento_fallido_es_solo_del_transportista_asignado(self):
        """El Vendedor, el Gerente y otro transportista reciben 403 al abrir o mandar el intento fallido; el asignado, 200."""
        x = self.concretable()
        otro = transportista_con_vehiculo(self.e.invernadero)
        for cuenta in (self.gerente, self.e.vendedor, otro):
            self.assertEqual(self.get(cuenta, "entrega_intento_fallido", x.entrega.pk).status_code, 403, cuenta)
            self.assertEqual(self.post(cuenta, "entrega_intento_fallido", {"motivo": "otro"}, x.entrega.pk).status_code, 403, cuenta)
        self.assertEqual(self.get(x.transportista, "entrega_intento_fallido", x.entrega.pk).status_code, 200)
        self.assertEqual(IntentoFallido.objects.count(), 0)

    def test_regla_una_entrega_que_no_existe_es_404(self):
        t = transportista_con_vehiculo(self.e.invernadero)
        self.assertEqual(self.get(t, "entrega_intento_fallido", 99999).status_code, 404)


class MiRutaTests(Base):
    def test_flujo_principal_mi_ruta_con_la_ruta_sin_iniciar_ofrece_iniciar_y_no_concretar(self):
        """Antes de iniciar: el vehículo, el peso, la capacidad, «Iniciar ruta» y **ningún** botón «Concretar» ni «Intento fallido» (llevarían a un rechazo)."""
        x = self.concretable(ruta_iniciada=False)
        html = texto(self.get(x.transportista, "ruta"))
        self.assertIn(x.entrega.codigo, html)
        self.assertIn(reverse("comercial:ruta_iniciar"), html)
        self.assertNotIn(reverse("comercial:entrega_concretar", args=[x.entrega.pk]), html)
        self.assertNotIn(reverse("comercial:entrega_intento_fallido", args=[x.entrega.pk]), html)
        self.assertNotIn(reverse("comercial:ruta_finalizar"), html)
        self.assertIn("Sin envasado", html)
        self.assertIn("800", html)

    def test_flujo_principal_con_la_ruta_iniciada_aparecen_concretar_intento_fallido_y_finalizar(self):
        """Con la ruta iniciada: cada entrega ofrece «Concretar» e «Intento fallido» y la pantalla ofrece «Finalizar ruta» (los botones del HTML de la ficha padre para el rol autorizado)."""
        x = self.concretable()
        html = texto(self.get(x.transportista, "ruta"))
        self.assertIn(reverse("comercial:entrega_concretar", args=[x.entrega.pk]), html)
        self.assertIn(reverse("comercial:entrega_intento_fallido", args=[x.entrega.pk]), html)
        self.assertIn(reverse("comercial:ruta_finalizar"), html)
        self.assertNotIn(reverse("comercial:ruta_iniciar"), html)

    def test_ext_2b_las_demoradas_aparecen_primero_con_sus_dias(self):
        """Extensión 2b: las atrasadas van primero con «hace N días»."""
        t = transportista_con_vehiculo(self.e.invernadero)
        for dias in (0, 3):
            venta = compra_venta(self.e, dias=0)
            entrega(venta, [reserva_lista(detalle(venta, self.e.variedad, 10), self.lote, 10)], transportista=t, fecha=HOY - timedelta(days=dias))
        html = texto(self.get(t, "ruta"))
        self.assertIn("hace 3 días", html)

    def test_ext_2a_sin_entregas_dice_cuando_es_la_proxima_y_no_ofrece_iniciar(self):
        """Extensión 2a: sin entregas de hoy, el aviso con la fecha de la próxima y ningún «Iniciar ruta»."""
        t = transportista_con_vehiculo(self.e.invernadero)
        venta = compra_venta(self.e, dias=4)
        entrega(venta, [reserva_lista(detalle(venta, self.e.variedad, 10), self.lote, 10)], transportista=t, fecha=HOY + timedelta(days=4))
        html = texto(self.get(t, "ruta"))
        self.assertIn("No tenés entregas para hoy", html)
        self.assertIn(f"{HOY + timedelta(days=4):%d/%m/%Y}", html)
        self.assertNotIn(reverse("comercial:ruta_iniciar"), html)

    def test_ext_1a_sin_vehiculo_lo_dice_y_no_ofrece_iniciar(self):
        """Extensión 1a: «No tenés un vehículo activo», sin botón de iniciar."""
        t = transportista_con_vehiculo(self.e.invernadero, con_vehiculo=False)
        html = texto(self.get(t, "ruta"))
        self.assertIn("No tenés un vehículo activo", html)
        self.assertNotIn(reverse("comercial:ruta_iniciar"), html)

    def test_regla_la_entrada_del_menu_y_la_seccion_ruta_de_hoy_llevan_a_mi_ruta(self):
        """El Panel de control del Transportista trae la sección «Ruta de hoy» con el acceso a «Mi ruta»; las demás cuentas no la ven."""
        x = self.concretable(ruta_iniciada=False)
        self.entrar(x.transportista)
        html = texto(self.client.get(reverse("core:inicio")))
        self.assertIn("Ruta de hoy", html)
        self.assertIn(reverse("comercial:ruta"), html)
        self.entrar(self.e.vendedor)
        self.assertNotIn("Ruta de hoy", texto(self.client.get(reverse("core:inicio"))))
        from core.menu import menu_de
        from core.models import Usuario

        self.assertIn(("Mi ruta", "comercial:ruta", "truck"), menu_de(Usuario.Rol.TRANSPORTISTA))
        self.assertNotIn(("Mi ruta", "comercial:ruta", "truck"), menu_de(Usuario.Rol.VENDEDOR))


class IniciarYFinalizarTests(Base):
    def test_flujo_principal_iniciar_con_confirmacion_y_sin_javascript(self):
        """Iniciar es una página (GET con la lista, POST con la huella): la ruta queda iniciada y se vuelve a «Mi ruta» con el aviso."""
        x = self.concretable(ruta_iniciada=False)
        pagina = self.get(x.transportista, "ruta_iniciar")
        self.assertContains(pagina, x.entrega.codigo)
        respuesta = self.post(x.transportista, "ruta_iniciar", {"huella": self.huella_de(pagina)})
        self.assertRedirects(respuesta, reverse("comercial:ruta"))
        self.assertTrue(rutas.ruta_del_dia(x.transportista).situacion == "en_ruta")
        self.assertTrue(RegistroAuditoria.objects.filter(accion="inicio_ruta").exists())

    def test_ext_5c_si_las_entregas_cambiaron_vuelve_al_paso_2_con_lo_agregado(self):
        """Extensión 5c: con la huella vieja, la misma página con lo que se sumó; no se inicia."""
        x = self.concretable(ruta_iniciada=False)
        huella = self.huella_de(self.get(x.transportista, "ruta_iniciar"))
        venta = compra_venta(self.e, dias=0)
        otra = entrega(venta, [reserva_lista(detalle(venta, self.e.variedad, 5), self.lote, 5)], transportista=x.transportista, fecha=HOY)
        respuesta = self.post(x.transportista, "ruta_iniciar", {"huella": huella})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(otra.codigo, texto(respuesta))
        self.assertFalse(rutas.ruta_del_dia(x.transportista).situacion == "en_ruta")

    def test_ext_1b_iniciar_dos_veces_vuelve_a_mi_ruta_con_el_mensaje(self):
        """5a: la segunda vez no cambia nada, vuelve a «Mi ruta» con el mensaje de que ya estaba iniciada."""
        x = self.concretable(ruta_iniciada=False)
        huella = rutas.ruta_del_dia(x.transportista).huella
        self.post(x.transportista, "ruta_iniciar", {"huella": huella})
        respuesta = self.post(x.transportista, "ruta_iniciar", {"huella": huella}, follow=True)
        self.assertContains(respuesta, "ya estaba iniciada")

    def test_ext_finalizar_con_pendientes_muestra_cada_una_con_concretar_e_intento_fallido(self):
        """Regla 1 de COM-FIN-RUT: con entregas pendientes se las lista con sus dos acciones y no hay botón de finalizar."""
        x = self.concretable()
        html = texto(self.get(x.transportista, "ruta_finalizar"))
        self.assertIn(reverse("comercial:entrega_concretar", args=[x.entrega.pk]), html)
        self.assertIn(reverse("comercial:entrega_intento_fallido", args=[x.entrega.pk]), html)
        self.assertNotIn('data-enviando="Finalizando…"', html)
        respuesta = self.post(x.transportista, "ruta_finalizar", follow=True)
        self.assertContains(respuesta, "sin resolver")
        self.assertTrue(rutas.ruta_del_dia(x.transportista).situacion == "en_ruta")

    def test_flujo_principal_finalizar_sin_pendientes_confirma_y_finaliza(self):
        """Sin pendientes: la confirmación y, al enviarla, la ruta deja de estar en curso."""
        x = self.concretable()
        self.post(x.transportista, "entrega_intento_fallido", {"motivo": "cliente_ausente"}, x.entrega.pk)
        pagina = texto(self.get(x.transportista, "ruta_finalizar"))
        self.assertIn('data-enviando="Finalizando…"', pagina)
        self.assertRedirects(self.post(x.transportista, "ruta_finalizar"), reverse("comercial:ruta"))
        self.assertNotEqual(rutas.ruta_del_dia(x.transportista).situacion, "en_ruta")


class IntentoFallidoTests(Base):
    def test_flujo_principal_registra_el_intento_y_vuelve_a_mi_ruta(self):
        """Sin JavaScript, una página: motivo + descripción; la entrega pasa a mañana sin transportista."""
        x = self.concretable()
        respuesta = self.post(x.transportista, "entrega_intento_fallido", {"motivo": "domicilio_cerrado", "descripcion": "Portón cerrado"}, x.entrega.pk)
        self.assertRedirects(respuesta, reverse("comercial:ruta"))
        e = Entrega.objects.get(pk=x.entrega.pk)
        self.assertEqual((e.fecha_programada_orden, e.transportista_id), (HOY + timedelta(days=1), None))
        self.assertEqual(IntentoFallido.objects.get().descripcion, "Portón cerrado")

    def test_ext_el_motivo_es_obligatorio_y_el_error_sale_bajo_el_campo(self):
        """Sin motivo, la misma página con el error del campo y sin registrar nada."""
        x = self.concretable()
        respuesta = self.post(x.transportista, "entrega_intento_fallido", {"motivo": "", "descripcion": "x" * 301}, x.entrega.pk)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Elegí el motivo")
        self.assertEqual(IntentoFallido.objects.count(), 0)

    def test_ext_14a_una_entrega_que_ya_paso_a_mañana_vuelve_a_mi_ruta_con_el_mensaje(self):
        """Una entrega que ya no es concretable no deja un 500: vuelve a «Mi ruta» con el mensaje."""
        x = self.concretable()
        self.post(x.transportista, "entrega_intento_fallido", {"motivo": "otro"}, x.entrega.pk)
        respuesta = self.post(x.transportista, "entrega_intento_fallido", {"motivo": "otro"}, x.entrega.pk, follow=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(IntentoFallido.objects.count(), 1)


class ConcretarTests(Base):
    def test_flujo_principal_sin_javascript_ver_resumen_y_confirmar(self):
        """En un ancho de celular y sin JavaScript: la pantalla con los pasos, «Ver resumen» (la misma página con el resumen y su huella), «Confirmar entrega» y el comprobante."""
        x = self.concretable()
        pagina = self.get(x.transportista, "entrega_concretar", x.entrega.pk)
        html = texto(pagina)
        for paso in ("1. Lo que llegó", "2. Envases", "3. Cobro", "Ver resumen"):
            self.assertIn(paso, html)
        resumen = self.post(x.transportista, "entrega_concretar_calcular", self.formulario(x), x.entrega.pk)
        self.assertEqual(resumen.status_code, 200)
        self.assertContains(resumen, "Confirmar entrega")
        self.assertContains(resumen, "Resumen de la concreción")
        final = self.post(x.transportista, "entrega_concretar", self.formulario(x, huella=self.huella_de(resumen)), x.entrega.pk)
        self.assertRedirects(final, reverse("comercial:entrega_comprobante", args=[x.entrega.pk]))
        self.assertEqual(Entrega.objects.get(pk=x.entrega.pk).estado_orden, "concretada")
        self.assertEqual(PagoCliente.objects.get().monto_pagado, Decimal("5000.00"))
        comprobante = self.get(x.transportista, "entrega_comprobante", x.entrega.pk)
        self.assertContains(comprobante, "Total cobrado")
        self.assertContains(comprobante, "Imprimir comprobante")

    def test_flujo_principal_con_htmx_solo_se_redibuja_el_resumen(self):
        """Con HTMX, `calcular/` devuelve el fragmento (sin la página completa) con el botón de confirmar."""
        x = self.concretable()
        respuesta = self.post(x.transportista, "entrega_concretar_calcular", self.formulario(x), x.entrega.pk, **HTMX)
        html = texto(respuesta)
        self.assertIn("Confirmar entrega", html)
        self.assertNotIn("<html", html.lower())
        self.assertNotIn("Lo que llegó y lo que recibió", html)

    def test_regla_calcular_no_escribe_nada(self):
        """`calcular/` (con y sin HTMX) no cambia ninguna fila: ni entregas, ni movimientos, ni pagos, ni auditoría."""
        from produccion.models import Merma, MovimientoStock

        x = self.concretable(con_envasado=True)
        antes = lambda: (Entrega.objects.filter(estado_orden="concretada").count(), MovimientoStock.objects.count(), Merma.objects.count(), PagoCliente.objects.count(), RegistroAuditoria.objects.count())
        previo = antes()
        datos = self.formulario(x, **{f"llego_{self.linea(x).pk}": "45", f"utilizada_{x.envases.pk}": "10"})
        datos.pop("sin_envases")
        self.post(x.transportista, "entrega_concretar_calcular", datos, x.entrega.pk)
        self.post(x.transportista, "entrega_concretar_calcular", datos, x.entrega.pk, **HTMX)
        self.assertEqual(antes(), previo)

    def test_ext_5b_una_cantidad_invalida_sale_bajo_su_campo_y_no_hay_boton_de_confirmar(self):
        """Extensión 5b: el error por campo (con lo planificado) y, con errores, el resumen no ofrece confirmar."""
        x = self.concretable()
        respuesta = self.post(x.transportista, "entrega_concretar_calcular", self.formulario(x, **{f"llego_{self.linea(x).pk}": "99"}), x.entrega.pk)
        self.assertContains(respuesta, "entre 0 y 50")
        self.assertNotContains(respuesta, "Confirmar entrega")

    def test_ext_10b_el_exceso_de_envases_pide_confirmar_la_cantidad(self):
        """Extensión 10b: sin la casilla «Confirmo la cantidad utilizada» el resumen lo marca y no deja confirmar; con ella, sí."""
        x = self.concretable(con_envasado=True)
        datos = self.formulario(x, **{f"utilizada_{x.envases.pk}": "12"})
        datos.pop("sin_envases")
        self.assertNotContains(self.post(x.transportista, "entrega_concretar_calcular", datos, x.entrega.pk), "Confirmar entrega")
        datos[f"confirmo_exceso_{x.envases.pk}"] = "1"
        resumen = self.post(x.transportista, "entrega_concretar_calcular", datos, x.entrega.pk)
        self.assertContains(resumen, "Confirmar entrega")
        self.assertContains(resumen, "2 de más")

    def test_ext_9a_sin_envasado_la_pantalla_pide_declarar_los_envases_o_marcar_que_no_se_usaron(self):
        """Extensión 9a: una fila por envase habilitado y la casilla «No se usaron envases»; sin declarar ni marcar, el error."""
        x = self.concretable()
        b = envase(self.e.invernadero)
        html = texto(self.get(x.transportista, "entrega_concretar", x.entrega.pk))
        self.assertIn(f'name="declarado_{b.pk}"', html)
        self.assertIn("No se usaron envases", html)
        datos = self.formulario(x)
        datos.pop("sin_envases")
        self.assertContains(self.post(x.transportista, "entrega_concretar_calcular", datos, x.entrega.pk), "Declará los envases usados")

    def test_regla_en_la_ultima_entrega_hace_falta_el_medio_de_pago_y_en_una_que_no_lo_es_no_se_pide(self):
        """Paso 11: sin medio de pago, el error bajo el campo; con un suministro (sin cobro) no se muestra el paso de cobro."""
        x = self.concretable()
        self.assertContains(self.post(x.transportista, "entrega_concretar_calcular", self.formulario(x, medio_pago=""), x.entrega.pk), "medio de pago")
        s = self.concretable(tipo="suministro", cantidad=20)
        self.assertNotIn("3. Cobro", texto(self.get(s.transportista, "entrega_concretar", s.entrega.pk)))

    def test_ext_3a_un_suministro_pide_lo_que_recibio_el_cliente_y_muestra_el_vencimiento(self):
        """Extensión 3a: el campo «Recibió el cliente» y, en el resumen, el vencimiento del pago."""
        s = self.concretable(tipo="suministro", cantidad=20, plazo_pago=15)
        html = texto(self.get(s.transportista, "entrega_concretar", s.entrega.pk))
        self.assertIn("Recibió el cliente", html)
        resumen = texto(self.post(s.transportista, "entrega_concretar_calcular", {f"llego_{self.linea(s).pk}": "20", "sin_envases": "1"}, s.entrega.pk))
        self.assertIn(f"{HOY + timedelta(days=15):%d/%m/%Y}", resumen)

    def test_ext_14a_una_entrega_ya_concretada_vuelve_a_mi_ruta_con_el_mensaje_sin_error_500(self):
        """Extensión 14a: abrir o confirmar una entrega que ya no es concretable vuelve a «Mi ruta» con el mensaje."""
        x = self.concretable()
        resumen = self.post(x.transportista, "entrega_concretar_calcular", self.formulario(x), x.entrega.pk)
        huella = self.huella_de(resumen)
        self.post(x.transportista, "entrega_concretar", self.formulario(x, huella=huella), x.entrega.pk)
        otra = self.post(x.transportista, "entrega_concretar", self.formulario(x, huella=huella), x.entrega.pk)
        self.assertRedirects(otra, reverse("comercial:ruta"), fetch_redirect_response=False)
        self.assertRedirects(self.get(x.transportista, "entrega_concretar", x.entrega.pk), reverse("comercial:ruta"), fetch_redirect_response=False)

    def test_regla_un_cambio_simultaneo_vuelve_a_la_pantalla_con_el_aviso(self):
        """Si cambió el envasado de un retiro mientras se cargaba, `cambio_simultaneo`: la misma pantalla con el aviso y nada registrado."""
        from produccion.models import ReservaInsumo

        x = self.concretable(retiro=True, con_envasado=True)
        datos = self.formulario(x, **{f"utilizada_{x.envases.pk}": "10"})
        datos.pop("sin_envases")
        huella = self.huella_de(self.post(self.e.vendedor, "entrega_concretar_calcular", datos, x.entrega.pk))
        ReservaInsumo.objects.filter(orden_id=x.entrega.pk).update(cantidad_reservada=Decimal("8"))
        respuesta = self.post(self.e.vendedor, "entrega_concretar", {**datos, "huella": huella}, x.entrega.pk)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "cambió")
        self.assertEqual(Entrega.objects.get(pk=x.entrega.pk).estado_orden, "a_realizar")

    def test_regla_el_comprobante_es_solo_de_quien_concreto(self):
        """La pantalla final y el comprobante son del Transportista asignado o del Vendedor del retiro; los demás, 403; una entrega sin concretar, 403."""
        x = self.concretable()
        self.assertEqual(self.get(x.transportista, "entrega_comprobante", x.entrega.pk).status_code, 403)
        resumen = self.post(x.transportista, "entrega_concretar_calcular", self.formulario(x), x.entrega.pk)
        self.post(x.transportista, "entrega_concretar", self.formulario(x, huella=self.huella_de(resumen)), x.entrega.pk)
        self.assertEqual(self.get(x.transportista, "entrega_comprobante", x.entrega.pk).status_code, 200)
        for cuenta in (self.gerente, self.e.vendedor, transportista_con_vehiculo(self.e.invernadero)):
            self.assertEqual(self.get(cuenta, "entrega_comprobante", x.entrega.pk).status_code, 403, cuenta)


class ConcretarRetiroTests(Base):
    def test_flujo_principal_el_vendedor_concreta_un_retiro_desde_la_lista_de_entregas(self):
        """«Concretar retiro» en la lista de Comercial › Entregas: solo el Vendedor del contrato, con la fecha de hoy o anterior; el Gerente no lo ve; otro Vendedor tampoco. Después cobra y vuelve a la lista."""
        x = self.concretable(retiro=True)
        enlace = reverse("comercial:entrega_concretar", args=[x.entrega.pk])
        self.entrar(self.e.vendedor)
        self.assertContains(self.client.get(reverse("comercial:entregas")), enlace)
        self.entrar(self.gerente)
        self.assertNotContains(self.client.get(reverse("comercial:entregas")), enlace)
        ajeno = crear_vendedor(email="ajeno@infoponia.com")
        self.entrar(ajeno)
        self.assertNotContains(self.client.get(reverse("comercial:entregas")), enlace)
        resumen = self.post(self.e.vendedor, "entrega_concretar_calcular", {f"llego_{self.linea(x).pk}": "50", f"acepta_{self.linea(x).pk}": "1", "sin_envases": "1", "medio_pago": "transferencia"}, x.entrega.pk)
        self.assertContains(resumen, "Confirmar entrega")
        datos = {f"llego_{self.linea(x).pk}": "50", f"acepta_{self.linea(x).pk}": "1", "sin_envases": "1", "medio_pago": "transferencia", "huella": self.huella_de(resumen)}
        self.assertEqual(self.post(self.e.vendedor, "entrega_concretar", datos, x.entrega.pk).status_code, 302)
        self.assertEqual(PagoCliente.objects.get().medio_pago, "transferencia")
        self.assertNotContains(self.get(self.e.vendedor, "entregas"), enlace)

    def test_regla_un_retiro_de_fecha_futura_no_ofrece_concretar(self):
        """Ningún botón lleva a un rechazo: un retiro con la fecha programada futura no muestra «Concretar retiro»."""
        x = self.concretable(retiro=True, dias=3)
        self.assertNotContains(self.get(self.e.vendedor, "entregas"), reverse("comercial:entrega_concretar", args=[x.entrega.pk]))


class FichasTests(Base):
    """COM-06a, «Lo que completa a otras tareas»: las fichas de la compra-venta, del suministro y del cliente, y la baja del cliente."""

    def concretar(self, x, **datos):
        actor = x.transportista or self.e.vendedor
        from comercial.servicios import concrecion

        d = concrecion.DatosDeConcrecion(sin_envases=True, medio_pago="efectivo", **datos)
        r = concrecion.resumen_de_concrecion(actor, x.entrega.pk, d)
        return concrecion.concretar_entrega(actor, x.entrega.pk, d, r.huella)

    def test_regla_la_ficha_de_la_compra_venta_muestra_la_fecha_de_concrecion_el_pago_y_lo_entregado(self):
        """La ficha de la venta concretada: fecha de concreción, el pago (medio, fecha y monto) y la cantidad entregada por detalle."""
        x = self.concretable()
        self.concretar(x)
        html = texto(self.get(self.e.vendedor, "compra_venta", x.contrato.pk))
        self.assertIn("Efectivo", html)
        self.assertIn("5.000", html)
        self.assertIn(f"{HOY:%d/%m/%Y}", html)
        self.assertIn("Pago", html)

    def test_regla_la_ficha_de_una_venta_sin_cobrar_no_muestra_el_cuadro_de_pago(self):
        """D-25: no se muestra lo que todavía no existe."""
        x = self.concretable()
        self.assertNotIn(">Pago<", texto(self.get(self.e.vendedor, "compra_venta", x.contrato.pk)))

    def test_regla_la_ficha_del_suministro_muestra_entregado_monto_vencimiento_estado_de_pago_y_discrepancias(self):
        """Regla 6 de COM-CNS-SUM («Entregado»), regla 7 (monto, vencimiento y estado de pago) y regla 8 (discrepancias pendientes)."""
        s = self.concretable(tipo="suministro", cantidad=100, minima=100, plazo_pago=10)
        self.concretar(s, llego={self.linea(s).pk: "80"})
        html = texto(self.get(self.e.vendedor, "suministro", s.contrato.pk))
        self.assertIn("Entregado", html)
        self.assertIn(f"{HOY + timedelta(days=10):%d/%m/%Y}", html)
        self.assertIn("Pendiente", html)
        self.assertIn("8.000", html)
        # COM-07a (regla 8 de COM-CNS-SUM): la sección es «Solicitudes de revisión» (antes «Discrepancias de entrega»); las cantidades («80 de 100 mínimas») están en la ficha de la solicitud.
        self.assertIn("Solicitudes de revisión", html)
        self.assertIn("Discrepancia de cantidad", html)
        self.assertIn("Pendiente de revisión", html)

    def test_regla_la_ficha_del_cliente_y_su_baja_informan_las_entregas_sin_cobrar_y_las_discrepancias(self):
        """`clientes.md`, «Se completa en»: la ficha suma las entregas sin cobrar (monto a cobrar y vencimiento) y las discrepancias pendientes, y la baja las informa (sin bloquearse)."""
        s = self.concretable(tipo="suministro", cantidad=100, minima=100, plazo_pago=10)
        self.concretar(s, llego={self.linea(s).pk: "80"})
        cliente = self.e.cliente
        html = texto(self.get(self.gerente, "cliente", cliente.pk))
        self.assertIn("Entregas sin cobrar", html)
        self.assertIn("Discrepancias pendientes", html)
        pendientes = clientes.pendientes_del_cliente(cliente, self.gerente)
        self.assertTrue(any(p.startswith("Entregas sin cobrar: 1") for p in pendientes), pendientes)
        self.assertTrue(any(p.startswith("Discrepancias pendientes: 1") for p in pendientes), pendientes)

    def test_regla_el_vendedor_de_otro_contrato_no_ve_las_entregas_sin_cobrar_ajenas(self):
        """El alcance (D-28): en la ficha del cliente, el Vendedor solo ve las entregas de sus contratos."""
        s = self.concretable(tipo="suministro", cantidad=100, minima=100)
        self.concretar(s)
        ajeno = crear_vendedor(email="ajeno2@infoponia.com")
        self.assertEqual(clientes.entregas_sin_cobrar(ajeno, self.e.cliente), [])
        self.assertEqual(len(clientes.entregas_sin_cobrar(self.e.vendedor, self.e.cliente)), 1)

    def test_regla_la_ficha_de_un_cliente_sin_entregas_no_muestra_esos_cuadros(self):
        """D-25: sin entregas sin cobrar ni discrepancias, la ficha no los muestra."""
        html = texto(self.get(self.gerente, "cliente", self.e.cliente.pk))
        self.assertNotIn("Entregas sin cobrar", html)
        self.assertNotIn("Discrepancias pendientes", html)
