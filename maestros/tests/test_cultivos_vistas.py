# Pruebas de las pantallas de cultivos de MAE-03 (paso 6; integración con el cliente de prueba de Django): «Producción» →
# «Cultivos y variedades» (PROD-CNS-CLT) y las ventanas de nuevo, renombrar, baja y reactivar (PROD-ALT-CLT, PROD-MOD-CLT,
# PROD-BAJ-CLT). Cada ventana es una página (respaldo sin JavaScript) y, con HTMX (``HX-Request``), un fragmento. Solo el Agrónomo:
# el Gerente no consulta cultivos (regla 4 de PROD-CNS-CLT) y toda ruta de cultivos le da 404, con HTMX o sin JavaScript.

from django.core.exceptions import ValidationError  # noqa: F401  (los servicios lanzan ValidationError)
from django.test import TestCase
from django.urls import reverse
from django.utils.safestring import mark_safe

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from maestros.extensiones import VariedadesDelCultivo
from maestros.models import Cultivo
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    con_extension,
    crear_agronomo,
    crear_cultivo,
    crear_invernadero,
    crear_variedad,
)

HX = {"HTTP_HX_REQUEST": "true"}


class CultivosVistasBase(ConDatosDeMaestros, TestCase):
    """Un Agrónomo con sesión y un Gerente; la ruta de la página y las de cada ventana."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Paz")
        self.gerente = crear_gerente()
        self.client.force_login(self.agronomo)
        self.pagina = reverse("maestros:cultivos")
        self.url_nuevo = reverse("maestros:cultivo_nuevo")

    def url(self, nombre, cultivo):
        return reverse(f"maestros:{nombre}", args=[cultivo.pk])


class AccesoACultivosVistaTests(CultivosVistasBase):
    """Quién llega a cada pantalla (SEG-13, regla 4 de PROD-CNS-CLT)."""

    def rutas(self):
        cultivo = crear_cultivo("Lechuga")
        return [
            self.pagina,
            self.url_nuevo,
            self.url("cultivo_renombrar", cultivo),
            self.url("cultivo_baja", cultivo),
            self.url("cultivo_reactivar", cultivo),
        ]

    def test_regla_4_el_gerente_recibe_404_en_todas_las_rutas_de_cultivos_sin_javascript(self):
        """PROD-CNS-CLT regla 4: el Gerente no consulta cultivos; si entra por la URL, 404 (GET y POST)."""
        rutas = self.rutas()
        self.client.force_login(self.gerente)
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 404)
                self.assertEqual(self.client.post(ruta, {"nombre": "Acelga"}).status_code, 404)
        self.assertEqual(Cultivo.objects.count(), 1)

    def test_regla_4_el_gerente_recibe_404_tambien_con_htmx(self):
        """PROD-CNS-CLT regla 4: con el encabezado de HTMX, igual 404 (el fragmento tampoco se le entrega)."""
        rutas = self.rutas()
        self.client.force_login(self.gerente)
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta, **HX).status_code, 404)
                self.assertEqual(self.client.post(ruta, {"nombre": "Acelga"}, **HX).status_code, 404)

    def test_regla_4_el_gerente_no_ve_la_pestana_de_cultivos(self):
        """PROD-CNS-CLT regla 4: su «Producción» tiene solo «Invernaderos» (VIEWS.prod del prototipo); ningún enlace lleva a un 404."""
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("maestros:invernaderos"))
        self.assertContains(respuesta, "Invernaderos")
        self.assertNotContains(respuesta, "Cultivos y variedades")
        self.assertNotContains(respuesta, self.pagina)

    def test_pre_a_los_demas_roles_reciben_403(self):
        """SEG-13: el Capataz no tiene acceso a esta pantalla."""
        rutas = self.rutas()
        self.client.force_login(crear_capataz())
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 403)

    def test_sin_sesion_redirige_al_inicio_de_sesion(self):
        """Toda pantalla exige sesión (D-25)."""
        rutas = self.rutas()
        self.client.logout()
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 302)

    def test_un_cultivo_que_no_existe_da_404(self):
        """Un id inexistente da 404."""
        for nombre in ("cultivo_renombrar", "cultivo_baja"):
            self.assertEqual(self.client.get(reverse(f"maestros:{nombre}", args=[999999])).status_code, 404)

    def test_abrir_una_ventana_con_get_no_cambia_nada(self):
        """Las confirmaciones: abrir la ventana no cambia ni audita nada; el cambio se hace con un POST."""
        cultivo = crear_cultivo("Lechuga")
        for ruta in (self.url("cultivo_baja", cultivo), self.url("cultivo_renombrar", cultivo), self.url_nuevo):
            self.client.get(ruta)
            self.client.get(ruta, **HX)
        cultivo.refresh_from_db()
        self.assertEqual((cultivo.estado_cultivo, cultivo.nombre_cultivo), ("activo", "Lechuga"))
        self.assertEqual(Cultivo.objects.count(), 1)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_reactivar_solo_acepta_post(self):
        """«Reactivar» es una acción: un GET no la hace (405)."""
        inactivo = crear_cultivo("Acelga", activo=False)
        self.assertEqual(self.client.get(self.url("cultivo_reactivar", inactivo)).status_code, 405)


class ProdCnsCltVistaTests(CultivosVistasBase):
    """La página «Cultivos y variedades» (PROD-CNS-CLT)."""

    def test_flujo_principal_el_agronomo_ve_las_dos_pestanas_y_los_cultivos(self):
        """VIEWS.prod del prototipo: «Invernaderos» y «Cultivos y variedades»; los cultivos activos primero."""
        crear_cultivo("Rúcula", activo=False)
        crear_cultivo("Lechuga")
        respuesta = self.client.get(self.pagina)
        self.assertContains(respuesta, "Cultivos y variedades")
        self.assertContains(respuesta, reverse("maestros:invernaderos"))
        contenido = respuesta.content.decode()
        self.assertLess(contenido.index("Lechuga"), contenido.index("Rúcula"))
        self.assertContains(respuesta, "Inactivo")

    def test_la_lista_de_invernaderos_del_agronomo_tiene_el_enlace_a_cultivos(self):
        """El Agrónomo llega a la pestaña desde la lista de invernaderos."""
        respuesta = self.client.get(reverse("maestros:invernaderos"))
        self.assertContains(respuesta, 'href="%s"' % self.pagina)

    def test_regla_2_cada_cultivo_dice_cuantas_variedades_activas_tiene(self):
        """PROD-CNS-CLT regla 2: «N variedades activas» (las inactivas no cuentan) o «Inactivo»."""
        lechuga = crear_cultivo("Lechuga")
        crear_variedad(lechuga, "Crespa")
        crear_variedad(lechuga, "Lisa")
        crear_variedad(lechuga, "Vieja", activa=False)
        crear_variedad(crear_cultivo("Acelga"), "Común")
        respuesta = self.client.get(self.pagina)
        self.assertContains(respuesta, "2 variedades activas")
        self.assertContains(respuesta, "1 variedad activa")

    def test_regla_2_sin_variedades_dice_no_tiene_variedades_y_no_hay_botones_de_variedad(self):
        """PROD-CNS-CLT regla 2 y «Cómo se aplica»: sin registrante (hasta INV-03), «No tiene variedades» y sin botones."""
        crear_cultivo("Lechuga")
        with con_extension("_VARIEDADES"):
            respuesta = self.client.get(self.pagina)
        self.assertContains(respuesta, "No tiene variedades")
        self.assertNotContains(respuesta, "+ Variedad")

    def test_regla_2_las_variedades_cargadas_a_mano_se_listan_con_sus_nombres_escapados(self):
        """API: sin registrante, la lista simple de nombres; los datos se escapan."""
        lechuga = crear_cultivo("Lechuga")
        crear_variedad(lechuga, "Crespa")
        crear_variedad(lechuga, "<i>Rara</i>", activa=False)
        with con_extension("_VARIEDADES"):
            respuesta = self.client.get(self.pagina)
        self.assertContains(respuesta, "Crespa")
        self.assertContains(respuesta, "&lt;i&gt;Rara&lt;/i&gt;")
        self.assertNotContains(respuesta, "<i>Rara</i>")

    def test_regla_2_con_el_registrante_de_inventario_usa_su_cabecera_y_su_cuerpo(self):
        """API: la página pone la cabecera y el cuerpo del registrante (INV-03) en cada tarjeta."""
        lechuga = crear_cultivo("Lechuga")
        propias = {lechuga.pk: VariedadesDelCultivo(mark_safe('<b id="cabecera-de-prueba">+ Variedad</b>'), mark_safe("<table id='cuerpo-de-prueba'></table>"))}
        with con_extension("_VARIEDADES", lambda actor, cultivos: propias):
            respuesta = self.client.get(self.pagina)
        self.assertContains(respuesta, '<b id="cabecera-de-prueba">+ Variedad</b>', html=False)
        self.assertContains(respuesta, "<table id='cuerpo-de-prueba'></table>", html=False)

    def test_regla_3_un_cultivo_activo_ofrece_renombrar_y_baja_y_uno_inactivo_solo_reactivar(self):
        """PROD-CNS-CLT regla 3 y D-30: lo que no corresponde no se muestra."""
        activo = crear_cultivo("Lechuga")
        inactivo = crear_cultivo("Acelga", activo=False)
        contenido = self.client.get(self.pagina).content.decode()
        for nombre, cultivo, presente in (
            ("cultivo_renombrar", activo, True),
            ("cultivo_baja", activo, True),
            ("cultivo_reactivar", activo, False),
            ("cultivo_reactivar", inactivo, True),
            ("cultivo_renombrar", inactivo, False),
            ("cultivo_baja", inactivo, False),
        ):
            with self.subTest(accion=nombre, cultivo=cultivo.nombre_cultivo):
                self.assertEqual(f'"{self.url(nombre, cultivo)}"' in contenido, presente)

    def test_regla_5_consultar_no_audita(self):
        """PROD-CNS-CLT regla 5 y SEG-14."""
        crear_cultivo("Lechuga")
        self.client.get(self.pagina)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_d29_la_pagina_pide_la_hoja_de_estilos_con_static_v(self):
        """Interfaz (D-29): los estáticos propios con ``static_v``, también con DEBUG apagado."""
        self.assertContains(self.client.get(self.pagina), "maestros/css/cultivos.css?v=")

    def test_sin_cultivos_la_pagina_lo_dice_y_ofrece_crear_uno(self):
        """Estado vacío: invita a registrar el primero."""
        respuesta = self.client.get(self.pagina)
        self.assertContains(respuesta, "Todavía no hay cultivos")
        self.assertContains(respuesta, "Nuevo cultivo")


class ProdAltCltVistaTests(CultivosVistasBase):
    """Ventana «Nuevo cultivo» (PROD-ALT-CLT)."""

    def test_flujo_principal_la_ventana_viene_en_la_pagina_sin_javascript(self):
        """Respaldo sin JavaScript: la página de cultivos con la ventana abierta."""
        crear_cultivo("Lechuga")
        respuesta = self.client.get(self.url_nuevo)
        self.assertContains(respuesta, "Nuevo cultivo")
        self.assertContains(respuesta, "data-ventana")
        self.assertContains(respuesta, "Crear cultivo")
        self.assertContains(respuesta, "Lechuga")  # la página detrás

    def test_flujo_principal_con_htmx_devuelve_solo_la_ventana(self):
        """HTMX inserta solo el fragmento."""
        crear_cultivo("Lechuga")
        respuesta = self.client.get(self.url_nuevo, **HX)
        self.assertContains(respuesta, "Crear cultivo")
        self.assertNotContains(respuesta, "Lechuga")
        self.assertNotContains(respuesta, "<html")

    def test_las_ventanas_varian_por_htmx_y_no_se_guardan_en_cache(self):
        """Patrón ABM §7."""
        respuesta = self.client.get(self.url_nuevo)
        self.assertIn("HX-Request", respuesta["Vary"])
        self.assertIn("no-cache", respuesta["Cache-Control"])

    def test_flujo_principal_crea_el_cultivo_y_vuelve_a_la_pagina_con_un_aviso(self):
        """PROD-ALT-CLT: «Cultivo creado: Acelga.» y un registro de auditoría."""
        respuesta = self.client.post(self.url_nuevo, {"nombre": "Acelga"}, follow=True)
        self.assertRedirects(respuesta, self.pagina)
        self.assertContains(respuesta, "Cultivo creado: Acelga.")
        self.assertEqual(Cultivo.objects.get().nombre_cultivo, "Acelga")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_cultivo").count(), 1)

    def test_regla_2_el_nombre_repetido_muestra_el_error_en_el_campo_y_conserva_lo_escrito(self):
        """PROD-ALT-CLT regla 2: «Ya existe un cultivo con ese nombre.», sin distinguir mayúsculas."""
        crear_cultivo("Acelga")
        respuesta = self.client.post(self.url_nuevo, {"nombre": "acelga"})
        self.assertContains(respuesta, "Ya existe un cultivo con ese nombre.")
        self.assertContains(respuesta, 'value="acelga"')
        self.assertEqual(Cultivo.objects.count(), 1)

    def test_regla_2_sin_nombre_muestra_el_error_en_el_campo(self):
        """PROD-ALT-CLT regla 2: el nombre es obligatorio."""
        self.assertContains(self.client.post(self.url_nuevo, {"nombre": " "}), "Ingresá el nombre del cultivo.")
        self.assertFalse(Cultivo.objects.exists())

    def test_regla_2_un_nombre_de_mas_de_40_caracteres_muestra_el_error_en_el_campo(self):
        """Modelo «Cultivo»: hasta 40 caracteres, con un error de campo y no un 500."""
        self.assertContains(self.client.post(self.url_nuevo, {"nombre": "x" * 41}), "Usá como máximo 40 caracteres.")


class ProdModCltVistaTests(CultivosVistasBase):
    """Ventana «Renombrar cultivo» (PROD-MOD-CLT)."""

    def setUp(self):
        super().setUp()
        self.cultivo = crear_cultivo("Lechuga")
        self.ruta = self.url("cultivo_renombrar", self.cultivo)

    def test_flujo_principal_la_ventana_trae_el_nombre_actual(self):
        """PROD-MOD-CLT: el formulario arranca con el nombre del cultivo."""
        respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "Renombrar cultivo")
        self.assertContains(respuesta, 'value="Lechuga"')
        self.assertContains(respuesta, "Guardar cambios")

    def test_regla_3_informa_cuantas_semillas_cambian_de_nombre(self):
        """PROD-MOD-CLT regla 3: antes de confirmar, el Sistema informa cuántas semillas cambian de nombre."""
        from maestros.tests.test_prod_mod_clt import SemillasFalsas

        with SemillasFalsas(cantidad=3).registrar():
            respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "se actualiza el nombre de las 3 semillas de sus variedades")

    def test_regla_3_sin_semillas_no_muestra_ese_aviso(self):
        """«Cómo se aplica»: sin registrantes, 0 semillas."""
        self.assertNotContains(self.client.get(self.ruta), "se actualiza el nombre")

    def test_regla_4_informa_a_que_invernaderos_se_les_avisa(self):
        """PROD-MOD-CLT regla 4 y prototipo: «se notificará a los Agrónomos de …»."""
        otro = crear_agronomo(email="otro@infoponia.com")
        invernadero = crear_invernadero("Invernadero Norte", agronomo=otro)
        with con_extension("_USOS_DE_CULTIVO", lambda c: {invernadero.pk}):
            respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "se notificará a los Agrónomos de Invernadero Norte")

    def test_flujo_principal_renombra_y_vuelve_a_la_pagina_con_un_aviso(self):
        """PROD-MOD-CLT: «Se guardó el cultivo …» y un registro de auditoría."""
        respuesta = self.client.post(self.ruta, {"nombre": "Lechuga criolla"}, follow=True)
        self.assertRedirects(respuesta, self.pagina)
        self.assertContains(respuesta, "Se guardó el cultivo Lechuga criolla.")
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.nombre_cultivo, "Lechuga criolla")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_cultivo").count(), 1)

    def test_regla_3_el_aviso_de_exito_dice_cuantas_semillas_se_actualizaron(self):
        """Prototipo: «Se actualizó el nombre de N semillas.»."""
        from maestros.tests.test_prod_mod_clt import SemillasFalsas

        with SemillasFalsas(cantidad=2).registrar():
            respuesta = self.client.post(self.ruta, {"nombre": "Lechuga criolla"}, follow=True)
        self.assertContains(respuesta, "Se actualizó el nombre de 2 semillas.")

    def test_pre_b_el_nombre_repetido_muestra_el_error_en_el_campo(self):
        """PROD-MOD-CLT precondición b."""
        crear_cultivo("Acelga")
        respuesta = self.client.post(self.ruta, {"nombre": "ACELGA"})
        self.assertContains(respuesta, "Ya existe un cultivo con ese nombre.")
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.nombre_cultivo, "Lechuga")

    def test_d28_guardar_sin_cambios_no_audita(self):
        """D-28: una modificación sin cambios no deja registro."""
        self.client.post(self.ruta, {"nombre": "Lechuga"}, follow=True)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_5_un_cultivo_inactivo_no_se_renombra_y_vuelve_a_la_pagina_con_el_motivo(self):
        """PROD-MOD-CLT regla 5: solo se reactiva; sin 403 (D-30)."""
        inactivo = crear_cultivo("Acelga", activo=False)
        respuesta = self.client.get(self.url("cultivo_renombrar", inactivo), follow=True)
        self.assertRedirects(respuesta, self.pagina)
        self.assertContains(respuesta, "El cultivo está inactivo: solo se puede reactivar.")


class ProdBajCltVistaTests(CultivosVistasBase):
    """Ventana de baja de un cultivo y reactivación (PROD-BAJ-CLT, PROD-MOD-CLT postcondición c)."""

    def setUp(self):
        super().setUp()
        self.cultivo = crear_cultivo("Lechuga")
        self.ruta = self.url("cultivo_baja", self.cultivo)

    def test_flujo_principal_la_ventana_pide_confirmar_y_no_cambia_nada(self):
        """PROD-BAJ-CLT: abrir la ventana (GET) muestra la confirmación sobre la página, sin cambiar nada."""
        respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "¿Dar de baja el cultivo Lechuga?")
        self.assertContains(respuesta, "Deja de ofrecerse para crear variedades.")
        self.assertContains(respuesta, "Dando de baja…")
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.estado_cultivo, "activo")

    def test_flujo_principal_confirmar_da_de_baja_y_vuelve_a_la_pagina(self):
        """PROD-BAJ-CLT: «El cultivo Lechuga quedó inactivo.» y un registro de auditoría."""
        respuesta = self.client.post(self.ruta, follow=True)
        self.assertRedirects(respuesta, self.pagina)
        self.assertContains(respuesta, "El cultivo Lechuga quedó inactivo.")
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.estado_cultivo, "inactivo")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_cultivo").count(), 1)

    def test_pre_c_con_variedades_activas_la_ventana_dice_cuantas_son_y_no_ofrece_confirmar(self):
        """PROD-BAJ-CLT precondición c y regla 2: con el conteo; sin botón de baja (D-30)."""
        crear_variedad(self.cultivo, "Crespa")
        crear_variedad(self.cultivo, "Lisa")
        respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "No se puede dar de baja el cultivo Lechuga")
        self.assertContains(respuesta, "Tiene 2 variedades activas. Primero se dan de baja con Baja Variedad.")
        self.assertNotContains(respuesta, "Dando de baja…")

    def test_pre_c_una_variedad_que_aparece_antes_de_confirmar_se_muestra_y_no_da_de_baja(self):
        """El POST vuelve a verificar con el cultivo bloqueado: la ventana vuelve a mostrarse con el conteo."""
        ventana = self.client.get(self.ruta)
        self.assertContains(ventana, "Dando de baja…")
        crear_variedad(self.cultivo, "Crespa")
        respuesta = self.client.post(self.ruta)
        self.assertContains(respuesta, "Tiene 1 variedad activa.")
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.estado_cultivo, "activo")

    def test_pre_b_un_cultivo_ya_dado_de_baja_vuelve_a_la_pagina_con_el_motivo(self):
        """D-30: sin 403; la página explica por qué."""
        inactivo = crear_cultivo("Acelga", activo=False)
        respuesta = self.client.get(self.url("cultivo_baja", inactivo), follow=True)
        self.assertContains(respuesta, "El cultivo ya está dado de baja.")

    def test_post_c_reactivar_deja_el_cultivo_activo_y_no_toca_sus_variedades(self):
        """PROD-MOD-CLT postcondición c y regla 6: «El cultivo Acelga está activo de nuevo.»."""
        inactivo = crear_cultivo("Acelga", activo=False)
        variedad = crear_variedad(inactivo, "Común", activa=False)
        respuesta = self.client.post(self.url("cultivo_reactivar", inactivo), follow=True)
        self.assertRedirects(respuesta, self.pagina)
        self.assertContains(respuesta, "El cultivo Acelga está activo de nuevo.")
        inactivo.refresh_from_db()
        variedad.refresh_from_db()
        self.assertEqual((inactivo.estado_cultivo, variedad.estado_variedad), ("activo", "inactivo"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="reactivacion_cultivo").count(), 1)

    def test_post_c_reactivar_un_cultivo_activo_vuelve_a_la_pagina_con_el_motivo(self):
        """Un cultivo que no está dado de baja no se reactiva: la página lo explica."""
        respuesta = self.client.post(self.url("cultivo_reactivar", self.cultivo), follow=True)
        self.assertContains(respuesta, "El cultivo no está dado de baja.")
