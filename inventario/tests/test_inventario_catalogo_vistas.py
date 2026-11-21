# Pruebas de las pantallas de INV-01 (paso 6; integración con el cliente de prueba de Django): «Inventario» → «Catálogo» (CMP-CNS-INS,
# CMP-ALT-INS, CMP-MOD-INS, CMP-BAJ-INS) y «Categorías» (CMP-CNS-TIN, CMP-ALT-TIN, CMP-MOD-TIN, CMP-BAJ-TIN). Cada ventana es una página
# (respaldo sin JavaScript) y, con HTMX (``HX-Request``), un fragmento. Solo el Agrónomo: otros roles reciben 403 y sin sesión, el
# inicio de sesión (SEG-13). Las vistas de lectura no se auditan (SEG-14). Cita D-24, D-29, D-30 y D-47.

from django.test import TestCase
from django.urls import reverse

from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.models import Insumo, TipoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    categoria_del_sistema,
    existencia,
    insumo,
    lote,
    reservas_de_prueba,
    tipo_de_insumo,
)
from inventario.extensiones import Impedimento
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

HX = {"HTTP_HX_REQUEST": "true"}


class VistasDeInventarioBase(ConDatosDeInventario, TestCase):
    """Un Agrónomo con sesión (a cargo de un invernadero) y las rutas de cada pantalla."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Paz")
        self.invernadero = crear_invernadero("Invernadero Uno", agronomo=self.agronomo)
        self.client.force_login(self.agronomo)
        self.catalogo = reverse("inventario:catalogo")
        self.categorias = reverse("inventario:categorias")

    def url(self, nombre, objeto):
        return reverse(f"inventario:{nombre}", args=[objeto.pk])


class AccesoAInventarioVistaTests(VistasDeInventarioBase):
    """Quién llega a cada pantalla (SEG-13, regla 5 de CMP-CNS-TIN y regla 4 de CMP-CNS-INS)."""

    def rutas(self):
        tipo = tipo_de_insumo("Limpieza")
        objetivo = insumo("Detergente", tipo=tipo)
        return [
            self.catalogo,
            self.categorias,
            reverse("inventario:insumo_nuevo"),
            reverse("inventario:categoria_nueva"),
            self.url("insumo_modificar", objetivo),
            self.url("insumo_baja", objetivo),
            self.url("insumo_reactivar", objetivo),
            self.url("categoria_modificar", tipo),
            self.url("categoria_baja", tipo),
            self.url("categoria_reactivar", tipo),
        ]

    def test_flujo_principal_otros_roles_reciben_403_en_todas_las_rutas(self):
        """SEG-13 y regla 5 de CMP-CNS-TIN: el Gerente, el Capataz y el Administrador no ven ni consultan inventario: 403 (GET y POST)."""
        rutas = self.rutas()
        for cuenta in (crear_gerente(), crear_capataz(), crear_administrador()):
            self.client.force_login(cuenta)
            for ruta in rutas:
                with self.subTest(rol=cuenta.rol, ruta=ruta):
                    self.assertEqual(self.client.get(ruta).status_code, 403)
                    self.assertEqual(self.client.post(ruta).status_code, 403)

    def test_flujo_principal_sin_sesion_va_al_inicio_de_sesion(self):
        """D-25: toda pantalla exige sesión; sin ella, redirige al inicio de sesión."""
        rutas = self.rutas()
        self.client.logout()
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn(reverse("core:iniciar_sesion"), respuesta["Location"])

    def test_flujo_principal_el_menu_tiene_inventario_solo_para_el_agronomo(self):
        """Paso 6 de INV-01: la entrada «Inventario» es del Agrónomo; el Gerente, el Capataz y el Administrador no la ven."""
        self.assertContains(self.client.get(self.catalogo), 'href="/inventario/catalogo/"')
        for cuenta in (crear_gerente(), crear_administrador()):
            self.client.force_login(cuenta)
            respuesta = self.client.get(reverse("core:inicio"), follow=True)
            self.assertNotContains(respuesta, 'href="/inventario/catalogo/"')

    def test_flujo_principal_el_inicio_de_inventario_lleva_al_catalogo(self):
        """El inicio de /inventario/ lleva al catálogo (INV-02 pondrá primero «Existencias»)."""
        self.assertRedirects(self.client.get(reverse("inventario:inicio")), self.catalogo)

    def test_flujo_principal_las_vistas_de_lectura_no_auditan(self):
        """SEG-14: consultar el catálogo y las categorías no deja registro de auditoría."""
        antes = RegistroAuditoria.objects.count()
        self.client.get(self.catalogo)
        self.client.get(self.categorias)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)


class CategoriasVistaTests(VistasDeInventarioBase):
    """CMP-CNS-TIN, CMP-ALT-TIN, CMP-MOD-TIN y CMP-BAJ-TIN en pantalla."""

    def test_regla_2_cns_tin_lista_las_cuatro_del_sistema_con_candado_y_sin_acciones(self):
        """CMP-CNS-TIN y «Cómo se aplica»: las cuatro categorías del sistema, con el candado y sin botones de modificar ni de baja."""
        respuesta = self.client.get(self.categorias)
        for nombre in ("Semillas", "Envases", "Repuestos de hardware", "Infraestructura"):
            self.assertContains(respuesta, nombre)
        self.assertContains(respuesta, "Del sistema", count=4)
        self.assertNotContains(respuesta, "/modificar/")
        self.assertNotContains(respuesta, "/baja/")

    def test_flujo_principal_alta_de_categoria_crea_y_avisa(self):
        """CMP-ALT-TIN: el POST crea la categoría, redirige a la pestaña y deja el aviso breve."""
        respuesta = self.client.post(
            reverse("inventario:categoria_nueva"), {"nombre": "Limpieza", "consumo_directo": "como_gasto"}, follow=True
        )
        self.assertRedirects(respuesta, self.categorias)
        self.assertContains(respuesta, "Categoría creada: Limpieza.")
        self.assertTrue(TipoInsumo.objects.filter(nombre_tipo_insumo="Limpieza", consumo_directo="como_gasto").exists())

    def test_regla_2_alta_tin_nombre_repetido_da_error_en_el_campo_nombre(self):
        """CMP-ALT-TIN regla 2: «limpieza » (minúscula, con espacio) repite el nombre; el error va en su campo y no se guarda."""
        tipo_de_insumo("Limpieza")
        respuesta = self.client.post(
            reverse("inventario:categoria_nueva"), {"nombre": "limpieza ", "consumo_directo": "como_gasto"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["form"].errors["nombre"], ["Ya existe una categoría con ese nombre."])
        self.assertEqual(TipoInsumo.objects.filter(nombre_tipo_insumo__iexact="limpieza").count(), 1)

    def test_regla_3_alta_tin_consumo_directo_sin_elegir_da_error_en_su_campo(self):
        """CMP-ALT-TIN regla 3: el consumo directo sin elegir da error en su propio campo y no se guarda."""
        respuesta = self.client.post(reverse("inventario:categoria_nueva"), {"nombre": "Limpieza", "consumo_directo": ""})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("consumo_directo", respuesta.context["form"].errors)
        self.assertNotIn("nombre", respuesta.context["form"].errors)
        self.assertFalse(TipoInsumo.objects.filter(nombre_tipo_insumo="Limpieza").exists())

    def test_flujo_principal_ventana_con_htmx_es_un_fragmento_y_sin_htmx_la_pagina(self):
        """D-47: con HTMX la ventana viene sola; sin JavaScript, la pestaña completa con la ventana abierta."""
        sola = self.client.get(reverse("inventario:categoria_nueva"), **HX)
        self.assertContains(sola, "Nueva categoría")
        self.assertNotContains(sola, "<html")
        completa = self.client.get(reverse("inventario:categoria_nueva"))
        self.assertContains(completa, "<html")
        self.assertContains(completa, 'data-ventana')

    def test_flujo_principal_modificar_categoria_guarda_y_sin_cambios_no_audita(self):
        """CMP-MOD-TIN y D-28: cambia el consumo directo y el nombre; guardar sin cambios no deja registro."""
        tipo = tipo_de_insumo("Limpieza", "como_gasto")
        url = self.url("categoria_modificar", tipo)
        self.client.post(url, {"nombre": "Higiene", "consumo_directo": "como_costo_de_los_lotes"})
        tipo.refresh_from_db()
        self.assertEqual((tipo.nombre_tipo_insumo, tipo.consumo_directo), ("Higiene", "como_costo_de_los_lotes"))
        antes = RegistroAuditoria.objects.count()
        self.client.post(url, {"nombre": "Higiene", "consumo_directo": "como_costo_de_los_lotes"})
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_regla_1_mod_tin_una_del_sistema_no_se_modifica_ni_se_da_de_baja(self):
        """CMP-MOD-TIN / CMP-BAJ-TIN: una categoría del sistema vuelve a la pestaña con el motivo (D-30) y no cambia."""
        envases = categoria_del_sistema("envases")
        for nombre in ("categoria_modificar", "categoria_baja"):
            respuesta = self.client.post(self.url(nombre, envases), {"nombre": "Otro", "consumo_directo": "como_gasto"}, follow=True)
            self.assertRedirects(respuesta, self.categorias)
        envases.refresh_from_db()
        self.assertEqual(envases.nombre_tipo_insumo, "Envases")
        self.assertEqual(envases.estado_tipo_insumo, "activo")

    def test_regla_3_baja_tin_con_insumos_activos_informa_cuantos_y_sin_ellos_pasa_a_inactiva_y_se_reactiva(self):
        """CMP-BAJ-TIN: con un insumo activo la ventana vuelve con el motivo; sin insumos queda inactiva y luego se reactiva."""
        tipo = tipo_de_insumo("Limpieza")
        detergente = insumo("Detergente", tipo=tipo)
        url = self.url("categoria_baja", tipo)
        self.assertContains(self.client.get(url, **HX), "¿Dar de baja la categoría Limpieza?")
        respuesta = self.client.post(url, **HX)
        self.assertContains(respuesta, "1 insumo")
        tipo.refresh_from_db()
        self.assertEqual(tipo.estado_tipo_insumo, "activo")
        detergente.estado_insumo = "inactivo"
        detergente.save()
        self.assertRedirects(self.client.post(url), self.categorias)
        tipo.refresh_from_db()
        self.assertEqual(tipo.estado_tipo_insumo, "inactivo")
        self.client.post(self.url("categoria_reactivar", tipo))
        tipo.refresh_from_db()
        self.assertEqual(tipo.estado_tipo_insumo, "activo")

    def test_regla_1_abrir_la_baja_con_get_no_cambia_nada(self):
        """Abrir la ventana de baja (GET) no da de baja ni audita."""
        tipo = tipo_de_insumo("Limpieza")
        antes = RegistroAuditoria.objects.count()
        self.client.get(self.url("categoria_baja", tipo))
        tipo.refresh_from_db()
        self.assertEqual(tipo.estado_tipo_insumo, "activo")
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_regla_1_reactivar_solo_acepta_post(self):
        """Reactivar es un POST: un GET da 405."""
        tipo = tipo_de_insumo("Limpieza", activo=False)
        self.assertEqual(self.client.get(self.url("categoria_reactivar", tipo)).status_code, 405)

    def test_regla_1_categoria_inexistente_da_404(self):
        """Un id inexistente da 404 (D-28)."""
        self.assertEqual(self.client.get(reverse("inventario:categoria_modificar", args=[999999])).status_code, 404)


class CatalogoVistaTests(VistasDeInventarioBase):
    """CMP-CNS-INS, CMP-ALT-INS, CMP-MOD-INS y CMP-BAJ-INS en pantalla."""

    def setUp(self):
        super().setUp()
        self.tipo = tipo_de_insumo("Limpieza", "como_gasto")

    def datos(self, **cambios):
        base = {"nombre": "Detergente", "descripcion": "", "categoria": self.tipo.pk, "unidad": "l"}
        return base | cambios

    def test_regla_3_cns_ins_lista_ninguno_en_habilitado_y_ofrece_las_ocho_unidades(self):
        """CMP-CNS-INS: un insumo sin habilitar dice «Ninguno»; el formulario ofrece las ocho unidades con el texto de sus decimales."""
        insumo("Detergente", tipo=self.tipo)
        self.assertContains(self.client.get(self.catalogo), "Ninguno")
        respuesta = self.client.get(reverse("inventario:insumo_nuevo"), **HX)
        for texto in ("unidad (solo enteros)", "kg (admite 3 decimales)", "g (admite 2 decimales)", "L (admite 3 decimales)",
                      "mL (admite 2 decimales)", "m³ (admite 3 decimales)", "m (admite 2 decimales)", "m² (admite 2 decimales)"):
            self.assertContains(respuesta, texto)

    def test_regla_4_alta_ins_no_ofrece_semillas_y_si_las_otras_activas(self):
        """CMP-ALT-INS regla 4: la lista de categorías no ofrece Semillas ni las inactivas."""
        tipo_de_insumo("Vieja", activo=False)
        opciones = self.client.get(reverse("inventario:insumo_nuevo")).context["form"].fields["categoria"].widget.choices
        categorias = [texto for valor, texto in opciones if valor]
        self.assertIn("Limpieza", categorias)
        self.assertNotIn("Semillas", categorias)
        self.assertNotIn("Vieja", categorias)

    def test_flujo_principal_alta_de_insumo_crea_activo_y_avisa_que_hay_que_habilitarlo(self):
        """CMP-ALT-INS y paso 5 de la verificación: el insumo aparece activo y el aviso pide habilitarlo en un invernadero."""
        respuesta = self.client.post(reverse("inventario:insumo_nuevo"), self.datos(), follow=True)
        self.assertRedirects(respuesta, self.catalogo)
        self.assertContains(respuesta, "Insumo creado: Detergente. Habilitalo en un invernadero")
        creado = Insumo.objects.get(nombre_insumo="Detergente")
        self.assertEqual((creado.estado_insumo, creado.unidad_medida_insumo, creado.controla_vencimiento), ("activo", "l", False))

    def test_regla_2_alta_ins_errores_por_campo(self):
        """CMP-ALT-INS reglas 2 a 5: nombre repetido en otras mayúsculas, categoría y unidad sin elegir: cada error en su campo; no se guarda."""
        insumo("Detergente", tipo=self.tipo)
        respuesta = self.client.post(reverse("inventario:insumo_nuevo"), self.datos(nombre="DETERGENTE", categoria="", unidad=""))
        errores = respuesta.context["form"].errors
        self.assertEqual(errores["nombre"], ["Ya existe un insumo con ese nombre."])
        self.assertIn("categoria", errores)
        self.assertIn("unidad", errores)
        self.assertEqual(Insumo.objects.count(), 1)

    def test_regla_3_mod_ins_muestra_bloqueados_la_unidad_y_el_vencimiento_con_stock_y_los_conserva(self):
        """CMP-MOD-INS regla 3: con stock, la unidad y «controla vencimiento» se muestran bloqueados con su motivo y el guardado no los cambia."""
        con_stock = insumo("Detergente", tipo=self.tipo, unidad="l")
        lote(existencia(con_stock, self.invernadero), "5")
        url = self.url("insumo_modificar", con_stock)
        respuesta = self.client.get(url, **HX)
        self.assertContains(respuesta, "No se cambia: el insumo ya tuvo stock o movimientos.")
        self.assertContains(respuesta, "No se cambia mientras tenga stock")
        self.client.post(url, {"nombre": "Detergente neutro", "descripcion": "", "categoria": self.tipo.pk, "unidad": "kg"})
        con_stock.refresh_from_db()
        self.assertEqual((con_stock.nombre_insumo, con_stock.unidad_medida_insumo), ("Detergente neutro", "l"))

    def test_regla_5_mod_ins_informa_a_quienes_se_avisara_y_notifica_a_los_otros_agronomos(self):
        """CMP-MOD-INS regla 5: la ventana dice a qué invernaderos se avisará; al guardar, el otro Agrónomo recibe la notificación."""
        otro = crear_agronomo("otro@infoponia.com", nombre="Luis", apellido="Gil")
        invernadero_otro = crear_invernadero("Invernadero Dos", agronomo=otro)
        compartido = insumo("Detergente", tipo=self.tipo)
        existencia(compartido, self.invernadero)
        existencia(compartido, invernadero_otro)
        url = self.url("insumo_modificar", compartido)
        self.assertContains(self.client.get(url, **HX), "También lo usan: Invernadero Dos")
        self.client.post(url, self.datos(nombre="Detergente líquido"))
        aviso = Notificacion.objects.get(destinatario=otro)
        self.assertEqual(aviso.titulo, "Cambió el insumo Detergente")

    def test_regla_1_mod_ins_quien_no_lo_usa_ve_las_acciones_deshabilitadas_con_el_nombre_de_quien_si(self):
        """CMP-CNS-INS regla 3 y CMP-MOD-INS regla 1: con otro Agrónomo usándolo, los botones salen deshabilitados con su nombre y la URL vuelve al catálogo."""
        otro = crear_agronomo("otro@infoponia.com", nombre="Luis", apellido="Gil")
        existencia(insumo("Detergente", tipo=self.tipo), crear_invernadero("Invernadero Dos", agronomo=otro))
        respuesta = self.client.get(self.catalogo)
        self.assertContains(respuesta, "No disponible: solo lo usa Invernadero Dos (Luis Gil).")
        self.assertContains(respuesta, 'aria-disabled="true"')
        self.assertNotContains(respuesta, "/modificar/")
        objetivo = Insumo.objects.get(nombre_insumo="Detergente")
        self.assertRedirects(self.client.get(self.url("insumo_modificar", objetivo)), self.catalogo)
        self.assertRedirects(self.client.get(self.url("insumo_baja", objetivo)), self.catalogo)

    def test_regla_4_una_semilla_indica_que_viene_de_su_variedad_y_no_tiene_botones(self):
        """CMP-CNS-INS regla 2 y CMP-MOD-INS regla 4: una semilla dice que viene de su variedad, no tiene botones y su URL vuelve al catálogo."""
        semilla = insumo("Semilla de lechuga", tipo=categoria_del_sistema("semillas"), unidad="g")
        respuesta = self.client.get(self.catalogo)
        self.assertContains(respuesta, "Viene del alta de la variedad")
        self.assertNotContains(respuesta, "/modificar/")
        self.assertRedirects(self.client.get(self.url("insumo_modificar", semilla)), self.catalogo)

    def test_regla_2_baja_ins_con_stock_informa_por_invernadero_y_no_da_de_baja(self):
        """CMP-BAJ-INS regla 2: con stock (también negativo) la ventana dice dónde está y cómo resolverlo, sin ofrecer confirmar."""
        con_stock = insumo("Detergente", tipo=self.tipo)
        lote(existencia(con_stock, self.invernadero), "5")
        url = self.url("insumo_baja", con_stock)
        respuesta = self.client.get(url, **HX)
        self.assertContains(respuesta, "No se puede dar de baja Detergente")
        self.assertContains(respuesta, "Invernadero Uno:")
        self.assertNotContains(respuesta, "Dar de baja</button>")
        self.client.post(url)
        con_stock.refresh_from_db()
        self.assertEqual(con_stock.estado_insumo, "activo")

    def test_regla_2_baja_ins_junta_los_impedimentos_de_otras_apps(self):
        """CMP-BAJ-INS regla 2: los impedimentos de los registrantes de deshabilitación (compras) también se listan."""
        objetivo = insumo("Detergente", tipo=self.tipo)
        habilitado = existencia(objetivo, self.invernadero)
        pendiente = Impedimento("pedido_en_curso", "Hay un pedido en curso.", "Recibilo o cancelalo.")
        with reservas_de_prueba(impedimentos={habilitado.pk: [pendiente]}):
            respuesta = self.client.get(self.url("insumo_baja", objetivo), **HX)
        self.assertContains(respuesta, "Hay un pedido en curso.")

    def test_flujo_principal_baja_ins_sin_impedimentos_confirma_pasa_a_inactivo_y_se_reactiva(self):
        """CMP-BAJ-INS y CMP-MOD-INS (c): sin impedimentos la baja pide confirmar y deja el insumo inactivo; reactivarlo no lo vuelve a habilitar."""
        objetivo = insumo("Detergente", tipo=self.tipo)
        habilitado = existencia(objetivo, self.invernadero)
        url = self.url("insumo_baja", objetivo)
        self.assertContains(self.client.get(url, **HX), "¿Dar de baja Detergente?")
        self.assertRedirects(self.client.post(url), self.catalogo)
        objetivo.refresh_from_db()
        habilitado.refresh_from_db()
        self.assertEqual((objetivo.estado_insumo, habilitado.estado_insumo_invernadero), ("inactivo", "inactivo"))
        self.client.post(self.url("insumo_reactivar", objetivo))
        objetivo.refresh_from_db()
        habilitado.refresh_from_db()
        self.assertEqual((objetivo.estado_insumo, habilitado.estado_insumo_invernadero), ("activo", "inactivo"))

    def test_regla_6_reactivar_con_categoria_inactiva_muestra_el_motivo(self):
        """CMP-MOD-INS regla 6: con la categoría inactiva el servicio rechaza la reactivación y la pantalla muestra el motivo."""
        inactiva = tipo_de_insumo("Vieja", activo=False)
        objetivo = insumo("Detergente", tipo=inactiva, activo=False)
        respuesta = self.client.post(self.url("insumo_reactivar", objetivo), follow=True)
        self.assertContains(respuesta, "la categoría Vieja está inactiva")
        objetivo.refresh_from_db()
        self.assertEqual(objetivo.estado_insumo, "inactivo")
