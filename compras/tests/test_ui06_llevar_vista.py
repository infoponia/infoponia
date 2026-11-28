# Pruebas de UI-06 (D-109 punto 9, UX-24) en `compras`: «Nuevo pedido» lleva a una página de resumen (el resumen no lleva marca: ya es la página); si el envío vuelve con errores, el primer
# error lleva la vista y el foco, y la carga inicial no lleva nada. Se usan la base y los datos de las pruebas de vista de pedidos.

from django.test import override_settings
from django.urls import reverse

from compras.tests import test_cmp_env_cot as t_cotizacion
from compras.tests import test_correcciones_vistas as t_correcciones
from compras.tests import test_ordenes_vistas as t_ordenes
from compras.tests import test_pagos_vistas as t_pagos
from compras.tests import test_pedidos_vistas as t_pedidos
from compras.tests import test_recepciones_vistas as t_recepciones
from core.tests.marcas_ui06 import Marcas


class NuevoPedidoTests(Marcas, t_pedidos.PedidosVistasBase):
    """CMP-REG-PED, `pedidos/nuevo.html`."""

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.nuevo))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        respuesta = self.client.post(self.nuevo, self.formulario())
        self.assertContains(respuesta, "Revisar el pedido")
        self.sin_marcas(respuesta)

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.nuevo, self.formulario(detalle_iin=[], detalle_cantidad=[]))
        self.una_marca(respuesta)
        self.assertIn("al menos un insumo", self.texto_marcado(respuesta))


# ---- Las demás pantallas con paso de resumen: el resumen es otra página (sin marca) y un envío con errores lleva la vista al primer error. ----


class CancelarPedidoTests(Marcas, t_pedidos.PedidosVistasBase):
    """CMP-02b, `pedidos/cancelar.html`."""

    def setUp(self):
        super().setUp()
        self.pedido = t_pedidos.armar_pedido(self.ana, dias_al_limite=3)
        t_pedidos.detalle_de_pedido(self.pedido, self.lechuga, cantidad="20")
        t_pedidos.enlace_de(t_pedidos.invitar(self.pedido, self.sur))
        self.cancelar = reverse("compras:pedido_cancelar", args=[self.pedido.pk])

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.cancelar))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        respuesta = self.client.post(self.cancelar, {"accion": "revisar", "motivo": "Cambió el presupuesto."})
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Contá por qué se cancela el pedido.")
        self.sin_marcas(respuesta)

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.cancelar, {"accion": "revisar", "motivo": "   "})
        self.una_marca(respuesta)
        self.assertEqual(self.texto_marcado(respuesta), "Contá por qué se cancela el pedido.")


class GenerarOrdenTests(Marcas, t_ordenes.OrdenesVistasBase):
    """CMP-GEN-ORD, `ordenes/generar.html`."""

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.client.force_login(self.ana)
        self.sin_marcas(self.client.get(self.generar_url))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        respuesta = self.generar(cotizacion=[self.cot_a.pk, self.cot_b.pk], accion="revisar")
        self.assertEqual(respuesta.templates[0].name, "compras/ordenes/generar_resumen.html")
        self.sin_marcas(respuesta)

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.generar(accion="revisar")
        self.una_marca(respuesta)


class ResolverOrdenTests(Marcas, t_ordenes.OrdenesVistasBase):
    """CMP-APR-ODC, `ordenes/resolver.html`: el aviso fijo «no se puede aprobar» es informativo y no lleva marca."""

    def setUp(self):
        super().setUp()
        self.orden = self.generada()

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.client.force_login(self.gerente)
        self.sin_marcas(self.client.get(self.resolver_url(self.orden)))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        self.sin_marcas(self.resolver(self.orden, accion="revisar_aprobacion"))

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.resolver(self.orden, accion="revisar_rechazo", motivo="   ")
        self.una_marca(respuesta)
        self.assertEqual(self.texto_marcado(respuesta), "Contá por qué se rechaza la orden.")


class RegistrarRecepcionTests(Marcas, t_recepciones.VistasDeRecepcionBase):
    """CMP-REG-RCP, `recepciones/recepcion_form.html`."""

    def setUp(self):
        super().setUp()
        self.como(self.ana)

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.recibir_url + self.entrega_a))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        self.sin_marcas(self.recibir_post("revisar", {self.l_fert: {"cant": "4", "venc": self.vence.isoformat()}}))

    def test_ui06_el_primer_error_lleva_la_vista(self):
        self.una_marca(self.recibir_post("revisar"))


class CierreConFaltanteTests(Marcas, t_recepciones.VistasDeRecepcionBase):
    """CMP-CRR-FLT, `recepciones/cierre_form.html`."""

    def setUp(self):
        super().setUp()
        self.como(self.ana)

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.cerrar_url))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        self.sin_marcas(self.cierre_post("revisar", {self.l_maceta: "No lo fabrican más."}))

    def test_ui06_el_primer_error_lleva_la_vista(self):
        self.una_marca(self.cierre_post("revisar", {}))


class RegistrarPagoTests(Marcas, t_pagos.PagosVistasBase):
    """CMP-REG-PGO, `pagos/formulario.html` (los errores de campo llevan la clase `field-error`)."""

    def setUp(self):
        super().setUp()
        self.recibir_a()
        self.entrar(self.contador)

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.formulario()))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        self.sin_marcas(self.enviar("revisar", medio="transferencia"))

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.enviar("revisar", medio=None)
        self.una_marca(respuesta)
        self.assertEqual(self.texto_marcado(respuesta), "Elegí el medio de pago.")


class CorreccionDeRecepcionTests(Marcas, t_correcciones.VistasDeCorreccionBase):
    """CMP-COR-RCP, `correcciones/formulario.html`."""

    def setUp(self):
        super().setUp()
        self.recepcion = self.recibir_a()
        self.como(self.ana)

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.corregir_url))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        self.sin_marcas(self.corregir_post("revisar", self.recepcion, {self.l_fert: "2"}, "Se cargó de más"))

    def test_ui06_el_primer_error_lleva_la_vista(self):
        self.una_marca(self.corregir_post("revisar", self.recepcion, {}))


class PortalDelProveedorTests(Marcas, t_cotizacion.CotizacionBase):
    """CMP-ENV-COT (portal público del proveedor, sin cuenta), `proveedor/portal.html`."""

    def setUp(self):
        super().setUp()
        correo = override_settings(CORREO_CONFIGURADO=True)
        correo.enable()
        self.addCleanup(correo.disable)

    def abrir(self):
        return self.client.get(f"/proveedor/{self.token_sur}/", follow=True)

    def formulario(self, **cambios):
        datos = {
            "accion": "revisar", "modo": "total", f"cantidad_{self.d_lechuga.pk}": "20", f"precio_{self.d_lechuga.pk}": "250.00",
            f"plazo_{self.d_lechuga.pk}": "3", "validez": self.validez.isoformat(), "observaciones": "",
        }
        datos.update(cambios)
        return datos

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.abrir())

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        self.abrir()
        self.sin_marcas(self.client.post("/proveedor/enlace/", self.formulario()))

    def test_ui06_el_primer_error_lleva_la_vista(self):
        self.abrir()
        self.una_marca(self.client.post("/proveedor/enlace/", self.formulario(**{f"cantidad_{self.d_lechuga.pk}": "0", f"plazo_{self.d_lechuga.pk}": "0"})))
