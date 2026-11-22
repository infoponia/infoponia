# Pruebas de las pantallas de «Existencias de insumos» (INV-02, paso 8; integración con el cliente de prueba de Django): la pestaña (CMP-CNS-IIN),
# las ventanas «Habilitar insumo» (CMP-HAB-IIN), «Mínimo y precio» (CMP-MOD-IIN) y «Deshabilitar» (CMP-DSH-IIN), el botón «Habilitar en un
# invernadero» del catálogo y el aviso «Cargar stock inicial». Cada ventana es una página (respaldo sin JavaScript) y, con HTMX (``HX-Request``),
# un fragmento. Solo el Agrónomo a cargo: otros roles reciben 403, un Agrónomo ajeno también (D-28) y sin sesión, el inicio de sesión.
# Las reglas de negocio las prueban los tests de servicio; acá se prueban permisos, errores por campo, textos y flujos. Cita D-24, D-29, D-30 y D-47.

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.extensiones import Impedimento
from inventario.models import InsumoInvernadero
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    faltante,
    insumo,
    lote,
    reservas_de_prueba,
    tipo_de_insumo,
    verificar_invariantes,
)
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

HX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()


def en(dias):
    return HOY + timedelta(days=dias)


class ExistenciasBase(ConDatosDeInventario, TestCase):
    """Un Agrónomo con sesión (a cargo de un invernadero) con «Nutriente A» (L, vence) y «Bolsas» (unidad) habilitados."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Paz")
        self.invernadero = crear_invernadero("Invernadero Uno", agronomo=self.agronomo)
        self.nutrientes = tipo_de_insumo("Nutrientes")
        self.nutriente = insumo("Nutriente A", tipo=self.nutrientes, unidad="l", controla_vencimiento=True)
        self.bolsas = insumo("Bolsas", tipo=tipo_de_insumo("Limpieza"), unidad="unidad")
        self.client.force_login(self.agronomo)
        self.lista = reverse("inventario:existencias")

    def habilitar_nutriente(self, minimo=20):
        self.iin = existencia(self.nutriente, self.invernadero, minimo=minimo, precio="1500.00")
        return self.iin

    def url(self, nombre, iin):
        return reverse(f"inventario:{nombre}", args=[iin.pk])


class AccesoAExistenciasVistaTests(ExistenciasBase):
    """Quién llega a cada pantalla (SEG-13, D-28, D-30)."""

    def rutas(self):
        iin = self.habilitar_nutriente()
        return [
            self.lista,
            reverse("inventario:habilitar"),
            self.url("existencia_modificar", iin),
            self.url("existencia_deshabilitar", iin),
            reverse("inventario:ajuste"),
        ]

    def test_flujo_principal_otros_roles_reciben_403_en_todas_las_rutas(self):
        """SEG-13 y regla 1 de CMP-CNS-IIN: el Gerente, el Capataz y el Administrador no ven ni usan las existencias: 403 (GET y POST)."""
        rutas = self.rutas()
        for cuenta in (crear_gerente(), crear_capataz(), crear_administrador()):
            self.client.force_login(cuenta)
            for ruta in rutas:
                with self.subTest(rol=cuenta.rol, ruta=ruta):
                    self.assertEqual(self.client.get(ruta).status_code, 403)
                    self.assertEqual(self.client.post(ruta).status_code, 403)

    def test_flujo_principal_sin_sesion_va_al_inicio_de_sesion(self):
        """D-25: toda pantalla exige sesión."""
        rutas = self.rutas()
        self.client.logout()
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn(reverse("core:iniciar_sesion"), respuesta["Location"])

    def test_regla_5_un_agronomo_ajeno_recibe_403_en_las_ventanas_de_una_existencia_ajena(self):
        """D-28 y regla 5 de CMP-CNS-IIN: las ventanas de una existencia de otro invernadero dan 403 (GET y POST), y no cambian nada."""
        iin = self.habilitar_nutriente()
        self.client.force_login(crear_agronomo(email="otro@infoponia.com"))
        for ruta in (self.url("existencia_modificar", iin), self.url("existencia_deshabilitar", iin)):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 403)
                self.assertEqual(self.client.post(ruta, {"cant_min": "1", "referencia_precio": "1"}).status_code, 403)
        iin.refresh_from_db()
        self.assertEqual((iin.cant_min_insumo, iin.estado_insumo_invernadero), (Decimal("20"), "activo"))

    def test_regla_2_filtrar_por_un_invernadero_ajeno_da_403(self):
        """Regla 2 de CMP-CNS-IIN y D-28: filtrar por el invernadero de otro Agrónomo es 403."""
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com"))
        self.assertEqual(self.client.get(self.lista, {"invernadero": ajeno.pk}).status_code, 403)

    def test_flujo_principal_el_inicio_y_el_menu_llevan_a_las_existencias(self):
        """Paso 8 de INV-02: /inventario/ y la entrada «Inventario» del menú llevan a «Existencias de insumos»; el Gerente no la ve."""
        self.assertRedirects(self.client.get(reverse("inventario:inicio")), self.lista)
        self.assertContains(self.client.get(self.lista), f'href="{self.lista}"')
        pagina = self.client.get(reverse("core:inicio"), follow=True)
        self.assertContains(pagina, f'<a class="nav-item" href="{self.lista}">')
        self.client.force_login(crear_gerente())
        self.assertNotContains(self.client.get(reverse("core:inicio"), follow=True), f'href="{self.lista}"')


class ExistenciasListaVistaTests(ExistenciasBase):
    """La pestaña (CMP-CNS-IIN): filas, lotes desplegables, estados y filtros."""

    def test_flujo_principal_sin_insumos_habilitados_invita_a_habilitar_el_primero(self):
        """Verificación a mano 1: no hay nada; la pantalla ofrece «Habilitar insumo». Es la primera pestaña."""
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, "Todavía no hay insumos habilitados")
        self.assertContains(respuesta, "Habilitar insumo")
        self.assertContains(respuesta, 'aria-selected="true">Existencias de insumos</a>')
        contenido = respuesta.content.decode()
        self.assertLess(contenido.index("Existencias de insumos"), contenido.index("Catálogo"))

    def test_flujo_principal_cada_fila_muestra_stock_minimo_vencimiento_y_lotes(self):
        """Reglas 3 y 4: stock libre, lo reservado, el mínimo, lo por vencer y los lotes con su estado («vence en 5 días»)."""
        iin = self.habilitar_nutriente()
        lote(iin, 30, vence=en(40))
        lote(iin, 10, vence=en(5))
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, "Nutriente A")
        self.assertContains(respuesta, "Invernadero Uno")
        self.assertContains(respuesta, "40")  # stock
        self.assertContains(respuesta, "vence en 5 días")
        self.assertContains(respuesta, "10 por vencer")
        self.assertContains(respuesta, "Al día")
        self.assertEqual(len(respuesta.context["filas"]), 1)

    def test_regla_3_la_fila_marca_stock_negativo_y_lo_que_no_cubre_las_reservas(self):
        """Regla 3: «Stock negativo» (faltante sin lote) y «No cubre las reservas» (reservado mayor que el stock sin vencidos)."""
        iin = self.habilitar_nutriente()
        faltante(iin, 4)
        self.assertContains(self.client.get(self.lista), "Stock negativo")
        iin2 = existencia(self.bolsas, self.invernadero)
        lote(iin2, 3)
        with reservas_de_prueba(reservado={iin2.pk: "5"}):
            self.assertContains(self.client.get(self.lista), "No cubre las reservas")

    def test_regla_4_un_lote_vencido_ofrece_dar_de_baja_con_el_motivo_vencimiento(self):
        """Paso 8 de INV-02: «Dar de baja» en un lote vencido abre el ajuste con el motivo «vencimiento» y el lote marcado; uno vigente no lo ofrece."""
        iin = self.habilitar_nutriente()
        vencido = lote(iin, 5, vence=en(-2))
        respuesta = self.client.get(self.lista)
        esperado = f"{reverse('inventario:ajuste')}?invernadero={self.invernadero.pk}&amp;insumo={self.nutriente.pk}&amp;motivo=vencimiento&amp;lotes={vencido.pk}"
        self.assertContains(respuesta, esperado)
        self.assertContains(respuesta, "Vencido hace 2 días")
        sano = existencia(self.bolsas, self.invernadero)
        lote(sano, 3)
        self.assertEqual(self.client.get(self.lista).content.decode().count("Dar de baja"), 1)

    def test_regla_3_un_insumo_sin_lotes_ofrece_cargar_stock_inicial(self):
        """Verificación a mano 1: sin lotes, la fila dice que no tiene y ofrece el ajuste de «carga inicial»."""
        self.habilitar_nutriente()
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, "Todavía no tiene lotes")
        self.assertContains(respuesta, "motivo=carga_inicial")

    def test_regla_2_filtros_por_invernadero_categoria_vencimientos_y_bajo_el_minimo(self):
        """Regla 2: cada filtro deja solo lo que corresponde; «Quitar filtros» aparece cuando hay uno."""
        otro = crear_invernadero("Invernadero Dos", agronomo=self.agronomo)
        iin = self.habilitar_nutriente(minimo=100)
        lote(iin, 10, vence=en(-1))
        bolsas = existencia(self.bolsas, otro, minimo=0)
        lote(bolsas, 50)
        casos = [
            ({"invernadero": otro.pk}, ["Bolsas"]),
            ({"categoria": self.nutrientes.pk}, ["Nutriente A"]),
            ({"vencimientos": "1"}, ["Nutriente A"]),
            ({"bajo_minimo": "1"}, ["Nutriente A"]),
            ({}, ["Bolsas", "Nutriente A"]),
        ]
        for filtros, esperado in casos:
            with self.subTest(filtros=filtros):
                respuesta = self.client.get(self.lista, filtros)
                self.assertEqual(sorted(f.iin.insumo.nombre_insumo for f in respuesta.context["filas"]), esperado)
        self.assertContains(self.client.get(self.lista, {"bajo_minimo": "1"}), "Quitar filtros")
        self.assertContains(self.client.get(self.lista, {"categoria": "999999"}), "Ninguna existencia coincide")

    def test_regla_1_solo_muestra_los_invernaderos_a_cargo(self):
        """Regla 1 y D-28: las existencias de otro Agrónomo no aparecen."""
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com"))
        existencia(self.bolsas, ajeno)
        self.habilitar_nutriente()
        self.assertEqual([f.iin.insumo.nombre_insumo for f in self.client.get(self.lista).context["filas"]], ["Nutriente A"])

    def test_regla_6_consultar_no_audita(self):
        """Regla 6 y SEG-14: las vistas de lectura no escriben auditoría."""
        self.habilitar_nutriente()
        antes = RegistroAuditoria.objects.count()
        self.client.get(self.lista)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_flujo_principal_el_aviso_de_recien_habilitado_solo_se_muestra_para_una_existencia_propia(self):
        """Verificación a mano 1: ``?recien=`` muestra «Cargar stock inicial» de esa existencia; la de otro Agrónomo no revela nada."""
        iin = self.habilitar_nutriente()
        propia = self.client.get(self.lista, {"recien": iin.pk})
        self.assertContains(propia, "ya se puede pedir y usar en Invernadero Uno")
        self.assertEqual(propia.context["recien"], iin)
        ajeno = existencia(self.bolsas, crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com")))
        respuesta = self.client.get(self.lista, {"recien": ajeno.pk})
        self.assertNotContains(respuesta, "ya se puede pedir y usar")
        self.assertIsNone(respuesta.context["recien"])


class HabilitarVistaTests(ExistenciasBase):
    """«Habilitar insumo» (CMP-HAB-IIN): la ventana, los errores por campo y el flujo."""

    def setUp(self):
        super().setUp()
        self.ruta = reverse("inventario:habilitar")

    def test_flujo_principal_la_ventana_con_htmx_es_un_fragmento_y_sin_htmx_la_pestana_con_la_ventana_abierta(self):
        """Patrón ABM §7: HTMX recibe solo la ventana; sin JavaScript, la pestaña completa con la ventana abierta."""
        fragmento = self.client.get(self.ruta, **HX)
        self.assertContains(fragmento, "Habilitar insumo en un invernadero")
        self.assertNotContains(fragmento, "<html")
        pagina = self.client.get(self.ruta)
        self.assertContains(pagina, "Habilitar insumo en un invernadero")
        self.assertContains(pagina, "Existencias de insumos")

    def test_flujo_principal_la_lista_de_insumos_no_ofrece_semillas_ni_inactivos_y_la_de_invernaderos_solo_los_propios(self):
        """Las semillas nacen con su variedad (INV-03); no se habilita un insumo inactivo; solo los invernaderos a cargo."""
        from inventario.categorias import SEMILLAS
        from inventario.tests.fabricas import categoria_del_sistema

        insumo("Semilla de lechuga", tipo=categoria_del_sistema(SEMILLAS))
        insumo("Viejo", tipo=self.nutrientes, activo=False)
        crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com"))
        form = self.client.get(self.ruta).context["form"]
        insumos = [texto for valor, texto in form.fields["insumo"].widget.choices if valor]
        invernaderos = [texto for valor, texto in form.fields["invernadero"].widget.choices if valor]
        self.assertEqual(sorted(insumos), ["Bolsas", "Nutriente A"])
        self.assertEqual(invernaderos, ["Invernadero Uno"])

    def test_flujo_principal_desde_el_catalogo_el_insumo_viene_elegido_y_no_se_cambia(self):
        """El botón «Habilitar en un invernadero» del catálogo abre la ventana con el insumo fijo."""
        respuesta = self.client.get(self.ruta, {"insumo": self.nutriente.pk}, **HX)
        self.assertContains(respuesta, '<b class="lockedval">Nutriente A</b>')
        self.assertContains(respuesta, f'name="insumo" value="{self.nutriente.pk}"')

    def test_flujo_principal_habilita_y_la_pestana_ofrece_cargar_stock_inicial(self):
        """Verificación a mano 1: habilitar con mínimo 20 y precio 1500 crea la existencia, la alerta «bajo el mínimo» y el aviso con «Cargar stock inicial»."""
        respuesta = self.client.post(
            self.ruta,
            {"insumo": self.nutriente.pk, "invernadero": self.invernadero.pk, "cant_min": "20", "referencia_precio": "1500"},
            follow=True,
        )
        iin = InsumoInvernadero.objects.get(insumo=self.nutriente, invernadero=self.invernadero)
        self.assertRedirects(respuesta, f"{self.lista}?recien={iin.pk}")
        self.assertContains(respuesta, "Nutriente A habilitado en Invernadero Uno.")
        self.assertContains(respuesta, "Cargar stock inicial")
        self.assertEqual((iin.cant_min_insumo, iin.referencia_precio), (Decimal("20.000"), Decimal("1500.00")))
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_insumo_bajo_minimo", estado_alerta="activa").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="habilitacion_insumo_invernadero").count(), 1)

    def test_regla_2_sin_elegir_insumo_ni_invernadero_cada_error_va_en_su_campo_y_no_se_guarda(self):
        """Pasos 2 y 3 del CU: el insumo y el invernadero son obligatorios; el error está en su campo y no se llama al servicio."""
        respuesta = self.client.post(self.ruta, {"cant_min": "5", "referencia_precio": "10"})
        errores = respuesta.context["form"].errors
        self.assertEqual((errores["insumo"], errores["invernadero"]), (["Elegí el insumo."], ["Elegí el invernadero."]))
        self.assertEqual(InsumoInvernadero.objects.count(), 0)

    def test_regla_3_y_4_minimo_y_precio_invalidos_dan_un_error_por_campo(self):
        """Reglas 3 y 4 de CMP-HAB-IIN: el error de cada campo sale del servicio; los decimales de la unidad y el precio con más de 2 decimales."""
        respuesta = self.client.post(
            self.ruta, {"insumo": self.bolsas.pk, "invernadero": self.invernadero.pk, "cant_min": "1,5", "referencia_precio": "0"}
        )
        errores = respuesta.context["form"].errors
        self.assertIn("cant_min", errores)
        self.assertIn("referencia_precio", errores)
        self.assertEqual(InsumoInvernadero.objects.count(), 0)

    def test_precondicion_d_ya_habilitado_se_informa_sin_error_500(self):
        """Precondición d: habilitar de nuevo el mismo par se rechaza con el mensaje y no duplica."""
        self.habilitar_nutriente()
        respuesta = self.client.post(
            self.ruta, {"insumo": self.nutriente.pk, "invernadero": self.invernadero.pk, "cant_min": "1", "referencia_precio": "10"}
        )
        self.assertContains(respuesta, "Ese insumo ya está habilitado en el invernadero.")
        self.assertEqual(InsumoInvernadero.objects.count(), 1)

    def test_precondicion_b_un_invernadero_ajeno_no_se_ofrece_y_forzarlo_da_error_de_campo(self):
        """D-28: un invernadero que no es del actor no está en la lista; enviarlo igual no habilita nada (error de campo, sin 403 ni fuga)."""
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com"))
        respuesta = self.client.post(
            self.ruta, {"insumo": self.nutriente.pk, "invernadero": ajeno.pk, "cant_min": "1", "referencia_precio": "10"}
        )
        self.assertEqual(respuesta.context["form"].errors["invernadero"], ["Elegí el invernadero."])
        self.assertEqual(InsumoInvernadero.objects.count(), 0)

    def test_flujo_principal_sin_invernaderos_a_cargo_la_ventana_lo_dice(self):
        """Sin invernadero activo a cargo no hay dónde habilitar: la ventana lo explica y no ofrece el formulario."""
        sin = crear_agronomo(email="sin@infoponia.com")
        self.client.force_login(sin)
        respuesta = self.client.get(self.ruta, **HX)
        self.assertContains(respuesta, "No tenés invernaderos activos a tu cargo")
        self.assertNotContains(respuesta, "<form")
        self.assertNotContains(self.client.get(self.lista), f'hx-get="{self.ruta}"')

    def test_flujo_principal_el_catalogo_ofrece_habilitar_en_un_invernadero(self):
        """Paso 8 de INV-02: el catálogo muestra «Habilitar en un invernadero» en los insumos activos (no en las semillas)."""
        respuesta = self.client.get(reverse("inventario:catalogo"))
        self.assertContains(respuesta, f"{self.ruta}?insumo={self.nutriente.pk}")


class MinimoYPrecioVistaTests(ExistenciasBase):
    """«Mínimo y precio» (CMP-MOD-IIN)."""

    def setUp(self):
        super().setUp()
        self.iin = self.habilitar_nutriente()
        self.ruta = self.url("existencia_modificar", self.iin)

    def test_flujo_principal_la_ventana_arranca_con_los_valores_actuales(self):
        """El formulario muestra el mínimo y el precio vigentes."""
        form = self.client.get(self.ruta, **HX).context["form"]
        self.assertEqual((form["cant_min"].value(), form["referencia_precio"].value()), ("20", "1500,00"))

    def test_flujo_principal_guarda_y_audita_con_antes_y_despues_como_texto(self):
        """Verificación a mano 9: con cambios hay un registro con antes y después (como texto)."""
        respuesta = self.client.post(self.ruta, {"cant_min": "30", "referencia_precio": "1600,50"}, follow=True)
        self.assertRedirects(respuesta, self.lista)
        self.assertContains(respuesta, "Se guardaron el mínimo y el precio.")
        self.iin.refresh_from_db()
        self.assertEqual((self.iin.cant_min_insumo, self.iin.referencia_precio), (Decimal("30"), Decimal("1600.50")))
        registro = RegistroAuditoria.objects.get(accion="modificacion_insumo_invernadero")
        self.assertEqual(registro.detalle["cambios"]["cant_min_insumo"], {"antes": "20.000", "despues": "30.000"})

    def test_d28_sin_cambios_no_hay_registro_de_auditoria(self):
        """D-28 y verificación a mano 9: guardar lo mismo no escribe auditoría."""
        self.client.post(self.ruta, {"cant_min": "20", "referencia_precio": "1500"})
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_insumo_invernadero").count(), 0)

    def test_regla_1_los_errores_van_por_campo_y_no_se_guarda(self):
        """Regla 1 de CMP-MOD-IIN: se validan como en CMP-HAB-IIN, un error por campo."""
        respuesta = self.client.post(self.ruta, {"cant_min": "-1", "referencia_precio": ""})
        errores = respuesta.context["form"].errors
        self.assertIn("cant_min", errores)
        self.assertIn("referencia_precio", errores)
        self.iin.refresh_from_db()
        self.assertEqual(self.iin.cant_min_insumo, Decimal("20"))

    def test_d30_una_existencia_deshabilitada_no_se_modifica_y_vuelve_con_el_motivo(self):
        """D-30: ningún botón lleva a un 403, pero una URL de una existencia deshabilitada vuelve a la pestaña con el motivo."""
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(estado_insumo_invernadero="inactivo")
        respuesta = self.client.get(self.ruta, follow=True)
        self.assertRedirects(respuesta, self.lista)
        self.assertContains(respuesta, "no se puede modificar")


class DeshabilitarVistaTests(ExistenciasBase):
    """«Deshabilitar» (CMP-DSH-IIN)."""

    def setUp(self):
        super().setUp()
        self.iin = self.habilitar_nutriente()
        self.ruta = self.url("existencia_deshabilitar", self.iin)

    def test_flujo_principal_con_stock_cero_pide_confirmar_y_deshabilita_solo_con_post(self):
        """Verificación a mano 10: abrir (GET) no cambia nada; el POST deshabilita y conserva el registro (reactivable)."""
        self.assertContains(self.client.get(self.ruta, **HX), "¿Deshabilitar Nutriente A en Invernadero Uno?")
        self.iin.refresh_from_db()
        self.assertEqual(self.iin.estado_insumo_invernadero, "activo")
        respuesta = self.client.post(self.ruta, follow=True)
        self.assertRedirects(respuesta, self.lista)
        self.assertContains(respuesta, "Nutriente A quedó deshabilitado en Invernadero Uno.")
        self.iin.refresh_from_db()
        self.assertEqual(self.iin.estado_insumo_invernadero, "inactivo")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_insumo_invernadero").count(), 1)

    def test_regla_2_con_stock_lista_todos_los_impedimentos_con_como_resolverlos_y_no_ofrece_confirmar(self):
        """Regla 2: la ventana junta stock, reservas y el impedimento de `compras`, cada uno con su texto; no ofrece confirmar; el POST no cambia nada."""
        lote(self.iin, 5, vence=en(30))
        compras = Impedimento("orden_de_compra", "Hay una orden de compra sin recibir.", "Recibila o cancelala.")
        with reservas_de_prueba(reservado={self.iin.pk: "2"}, impedimentos={self.iin.pk: [compras]}):
            respuesta = self.client.get(self.ruta, **HX)
            self.assertContains(respuesta, "No se puede deshabilitar Nutriente A")
            self.assertContains(respuesta, "Hay una orden de compra sin recibir. Recibila o cancelala.")
            self.assertNotContains(respuesta, "<form")
            self.client.post(self.ruta)
        self.iin.refresh_from_db()
        self.assertEqual(self.iin.estado_insumo_invernadero, "activo")
        self.assertGreaterEqual(respuesta.content.decode().count("<li>"), 2)

    def test_regla_2_si_aparece_un_impedimento_con_la_ventana_abierta_el_post_vuelve_a_mostrarlo(self):
        """El POST se rechaza si entre tanto entró stock: la ventana vuelve con los impedimentos, sin error 500 y sin cambiar nada."""
        self.assertEqual(self.client.get(self.ruta, **HX).status_code, 200)
        lote(self.iin, 5, vence=en(30))
        respuesta = self.client.post(self.ruta)
        self.assertContains(respuesta, "No se puede deshabilitar Nutriente A")
        self.iin.refresh_from_db()
        self.assertEqual(self.iin.estado_insumo_invernadero, "activo")
        verificar_invariantes(self.iin)

    def test_volver_a_habilitar_reactiva_el_mismo_registro(self):
        """Verificación a mano 10: después de deshabilitar, «Habilitar insumo» reactiva el mismo registro."""
        self.client.post(self.ruta)
        self.client.post(
            reverse("inventario:habilitar"),
            {"insumo": self.nutriente.pk, "invernadero": self.invernadero.pk, "cant_min": "10", "referencia_precio": "9"},
        )
        self.assertEqual(InsumoInvernadero.objects.count(), 1)
        self.iin.refresh_from_db()
        self.assertEqual(self.iin.estado_insumo_invernadero, "activo")
