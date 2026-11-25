# Pruebas de la pantalla «Corregir una recepción» (CMP-06, paso 4; ``VIEWS.c_cor``) y de lo que suma a la ficha de la orden (el botón «Corregir una recepción», lo corregido por línea y la sección «Reclamos»).
# Fuente: docs/casos_de_uso/compras/correccion_y_reclamos.md (CMP-COR-RCP pasos 1 a 11 y extensiones 2a, 5a, 5b y 9a), docs/casos_de_uso/compras/ordenes_de_compra.md (CMP-CNS-ODC regla 8) y D-30. Las vistas solo
# orquestan: las reglas las prueban ``test_cmp_cor_rcp.py``.
#
# Contrato de «Corregir una recepción» (``compras:correccion_nueva``, ``?recepcion=``; un formulario sin JavaScript): ``recepcion`` (la elegida), ``cant_<id del detalle de recepción>`` por línea, ``observacion`` y
# ``accion`` = ``revisar`` (paso 7), ``confirmar`` (paso 9) o ``editar``.

from django.core import mail
from django.urls import reverse

from compras.models import CorreccionRecepcion
from compras.tests.base_correcciones import CorreccionBase
from compras.tests.base_recepciones import DANADA, D
from core.tests.fabricas import crear_capataz
from maestros.tests.fabricas import crear_vendedor


class VistasDeCorreccionBase(CorreccionBase):
    def setUp(self):
        super().setUp()
        self.ficha_url = reverse("compras:orden_ficha", args=[self.orden.pk])
        self.corregir_url = reverse("compras:correccion_nueva", args=[self.orden.pk])

    def como(self, usuario):
        self.client.force_login(usuario)

    def corregir_post(self, accion, recepcion, cantidades, observacion="", extra=None):
        """El formulario con ``cantidades = {detalle de la orden: cantidad}``."""
        datos = {"recepcion": recepcion.pk, "observacion": observacion, "accion": accion}
        for detalle_orden, cantidad in cantidades.items():
            datos[f"cant_{self.detalle_de(recepcion, detalle_orden).pk}"] = cantidad
        datos.update(extra or {})
        return self.client.post(self.corregir_url, datos)


class CorreccionVistaTests(VistasDeCorreccionBase):
    """El formulario, el resumen y la confirmación."""

    def test_paso_2_el_formulario_muestra_la_recepcion_las_lineas_lo_recibido_y_lo_maximo(self):
        """Pasos 2 a 5: la recepción, cada línea con lo recibido, lo máximo corregible y el campo para la cantidad; la observación es opcional."""
        recepcion = self.recibir_a()
        self.como(self.ana)
        respuesta = self.client.get(self.corregir_url)
        self.assertEqual(respuesta.status_code, 200)
        for texto in (str(recepcion), "Fertilizante", "Maceta", "Se puede descontar", "Observación", "(opcional)", "Ver resumen", f'name="cant_{self.detalle_de(recepcion, self.l_fert).pk}"'):
            self.assertContains(respuesta, texto)

    def test_paso_2_con_varias_recepciones_corregibles_se_elige_con_enlaces(self):
        """Paso 3: con más de una recepción corregible se elige una con ``?recepcion=``; sin elegir, la primera."""
        a = self.recibir_a()
        b = self.recibir_b()
        self.como(self.ana)
        respuesta = self.client.get(self.corregir_url)
        self.assertContains(respuesta, f"?recepcion={b.pk}")
        self.assertContains(self.client.get(self.corregir_url + f"?recepcion={b.pk}"), "Tomate")
        self.assertContains(respuesta, "Fertilizante")
        self.assertNotContains(respuesta, "Tomate")
        self.assertIsNotNone(a)

    def test_ext_2a_sin_recepciones_corregibles_se_avisa(self):
        """Extensión 2a: sin recepciones corregibles (nada recibido o todo pagado) la pantalla lo dice y no ofrece formulario."""
        self.como(self.ana)
        self.assertContains(self.client.get(self.corregir_url), "No hay recepciones para corregir")
        self.recibir_a()
        self.pagar()
        respuesta = self.client.get(self.corregir_url)
        self.assertContains(respuesta, "No hay recepciones para corregir")
        self.assertNotContains(respuesta, "Ver resumen")

    def test_paso_7_el_resumen_muestra_el_asiento_inverso_y_no_cambia_nada(self):
        """Paso 7: el resumen trae lo que cambia (recibida, stock, tránsito, estado de la orden), el asiento inverso y que se avisa al proveedor; no escribe."""
        recepcion = self.recibir_a()
        antes = self.instantanea_de_correcciones()
        self.como(self.ana)
        respuesta = self.corregir_post("revisar", recepcion, {self.l_fert: "2"}, "Se cargó de más")
        self.assertContains(respuesta, "Confirmá la corrección")
        for texto in ("20,00", "Proveedores", "Insumos en Stock", "Parcialmente recibida", "Pendiente de recibir", self.proveedor.nombre_para_mostrar, 'value="Se cargó de más"'):
            self.assertContains(respuesta, texto)
        self.sin_cambios_de_correcciones(antes)

    def test_paso_9_confirmar_registra_la_correccion_y_vuelve_a_la_ficha_con_el_aviso(self):
        """Pasos 9 a 11: confirmar registra, manda el correo, vuelve a la ficha de la orden y dice cómo quedó."""
        recepcion = self.recibir_a()
        self.como(self.ana)
        correos = len(mail.outbox)
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.corregir_post("confirmar", recepcion, {self.l_fert: "2"}, "Se cargó de más")
        self.assertRedirects(respuesta, self.ficha_url, fetch_redirect_response=False)
        correccion = CorreccionRecepcion.objects.get()
        self.assertEqual((correccion.observacion, self.recibido(self.l_fert), self.estado_de(self.l_fert)), ("Se cargó de más", D("8"), "pendiente"))
        self.assertEqual(len(mail.outbox), correos + 1)
        ficha = self.client.get(self.ficha_url)
        self.assertContains(ficha, f"Registramos la corrección {correccion}")
        self.assertContains(ficha, "se corrigieron")
        self.assertContains(ficha, f"Corregida")

    def test_ext_5a_una_cantidad_que_supera_lo_maximo_vuelve_al_formulario_con_lo_escrito(self):
        """Extensión 5a: el error vuelve al formulario con el mensaje y lo escrito; no cambia nada."""
        recepcion = self.recibir_a()
        antes = self.instantanea_de_correcciones()
        self.como(self.ana)
        respuesta = self.corregir_post("confirmar", recepcion, {self.l_fert: "11"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "como máximo")
        self.assertContains(respuesta, 'value="11"')
        self.sin_cambios_de_correcciones(antes)

    def test_ext_5a_un_texto_que_no_es_numero_se_marca_en_su_linea(self):
        """Lo que no se puede leer como número se marca en su línea con «Escribí un número.»."""
        recepcion = self.recibir_a()
        self.como(self.ana)
        respuesta = self.corregir_post("revisar", recepcion, {self.l_fert: "abc"})
        self.assertContains(respuesta, "Escribí un número.")
        self.assertEqual(CorreccionRecepcion.objects.count(), 0)

    def test_ext_5b_sin_ninguna_cantidad_se_pide_al_menos_una_linea(self):
        """Extensión 5b: la corrección debe incluir al menos una línea con cantidad."""
        recepcion = self.recibir_a()
        self.como(self.ana)
        respuesta = self.corregir_post("revisar", recepcion, {})
        self.assertContains(respuesta, "al menos una línea")

    def test_ext_9a_si_el_proveedor_se_pago_mientras_tanto_vuelve_a_la_ficha_con_el_aviso(self):
        """Extensión 9a: con el proveedor pagado entre el resumen y la confirmación, no se registra nada y se vuelve a la ficha con el aviso."""
        recepcion = self.recibir_a()
        self.como(self.ana)
        self.pagar()
        antes = self.instantanea_de_correcciones()
        respuesta = self.corregir_post("confirmar", recepcion, {self.l_fert: "2"}, extra=None)
        self.assertRedirects(respuesta, self.ficha_url, fetch_redirect_response=False)
        self.assertContains(self.client.get(self.ficha_url), "Ya no hay recepciones para corregir")
        self.sin_cambios_de_correcciones(antes)

    def test_paso_5_una_linea_cerrada_con_faltante_dice_por_que_no_se_corrige(self):
        """Extensión 4b: la línea cerrada con faltante no tiene campo y dice que no se corrige."""
        self.recibir_a_con_faltante()
        self.como(self.ana)
        respuesta = self.client.get(self.corregir_url)
        self.assertContains(respuesta, "cerrada con faltante: no se corrige")

    def test_la_accion_editar_vuelve_al_formulario_con_lo_escrito(self):
        """«Volver» desde el resumen reabre el formulario con lo que se había escrito."""
        recepcion = self.recibir_a()
        self.como(self.ana)
        respuesta = self.corregir_post("editar", recepcion, {self.l_fert: "2"}, "nota")
        self.assertContains(respuesta, 'value="2"')
        self.assertContains(respuesta, "nota")


class CorreccionAccesoTests(VistasDeCorreccionBase):
    """Quién entra y cuándo se ve el botón (D-30)."""

    def test_regla_8_el_boton_corregir_solo_se_ve_si_hay_algo_corregible_y_para_quien_corrige(self):
        """CMP-CNS-ODC regla 8 y D-30: «Corregir una recepción» está para el Agrónomo a cargo y el Gerente con una recepción corregible; no para el Contador; ni sin recepciones; ni con el proveedor pagado."""
        self.como(self.ana)
        self.assertNotContains(self.client.get(self.ficha_url), "Corregir una recepción")
        self.recibir_a()
        self.assertContains(self.client.get(self.ficha_url), "Corregir una recepción")
        self.como(self.gerente)
        self.assertContains(self.client.get(self.ficha_url), "Corregir una recepción")
        self.como(self.contador)
        self.assertNotContains(self.client.get(self.ficha_url), "Corregir una recepción")
        self.pagar()
        self.como(self.ana)
        self.assertNotContains(self.client.get(self.ficha_url), "Corregir una recepción")

    def test_quien_no_corrige_no_entra(self):
        """El Contador, el Vendedor y el Capataz reciben 403; sin sesión, la pantalla de ingreso; otro Agrónomo sin la orden a su cargo, 403; una orden que no existe, 404."""
        self.recibir_a()
        for usuario in (self.contador, crear_vendedor(), crear_capataz(), self.beto):
            with self.subTest(usuario=usuario):
                self.como(usuario)
                self.assertEqual(self.client.get(self.corregir_url).status_code, 403)
                self.assertEqual(self.client.post(self.corregir_url, {"accion": "confirmar"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.corregir_url).status_code, 302)
        self.como(self.ana)
        self.assertEqual(self.client.get(reverse("compras:correccion_nueva", args=[self.orden.pk + 9999])).status_code, 404)

    def test_el_gerente_corrige_cualquier_recepcion(self):
        """Extensión 1a: el Gerente ve y corrige las recepciones de todos los invernaderos."""
        recepcion = self.recibir_a()
        self.como(self.gerente)
        self.assertContains(self.client.get(self.corregir_url), "Fertilizante")
        with self.captureOnCommitCallbacks(execute=True):
            self.corregir_post("confirmar", recepcion, {self.l_fert: "1"})
        self.assertIsNone(CorreccionRecepcion.objects.get().agronomo)

    def test_la_ficha_muestra_los_reclamos_y_su_enlace_salvo_al_contador(self):
        """La sección «Reclamos» de la ficha (CMP-EMT-RCL regla 4): el reclamo con su estado y un enlace a su ficha; el Contador (solo lectura) ve el estado sin enlace."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 2, "Cajas rotas")])])
        self.como(self.gerente)
        ficha = self.client.get(self.ficha_url)
        self.assertContains(ficha, 'id="reclamos"')
        self.assertContains(ficha, "Sin emitir")
        self.assertContains(ficha, "/compras/reclamos/")
        self.como(self.contador)
        contador = self.client.get(self.ficha_url)
        self.assertContains(contador, 'id="reclamos"')
        self.assertNotContains(contador, "/compras/reclamos/")
