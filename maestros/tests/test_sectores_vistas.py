# Pruebas de las pantallas de sectores de MAE-03 (paso 4; integración con el cliente de prueba de Django): la pestaña «Sectores»
# y la tarjeta «Capacidad» de la ficha del invernadero (PROD-CNS-SCT, regla 3 de PROD-CNS-INV) y las ventanas de alta, modificación
# (con el aviso de cambio de tipo), baja, reactivación y vuelta a servicio (PROD-ALT-SCT, PROD-MOD-SCT, PROD-BAJ-SCT). Cada ventana
# es una página (respaldo sin JavaScript) y, con HTMX (``HX-Request``), un fragmento. Alcance: solo el Agrónomo a cargo hace
# acciones; el Gerente consulta sin ellas; un Agrónomo ajeno recibe 403 (regla 1 de PROD-CNS-SCT, D-28 y D-30).

from django.test import TestCase
from django.urls import reverse

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from maestros.extensiones import Aviso, Contenido, Impedimento
from maestros.models import SectorProduccion
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    con_agujeros,
    con_extension,
    crear_agronomo,
    crear_agronomo_con_invernadero,
    crear_invernadero,
    crear_sector,
    tipo_etapa,
)

HX = {"HTTP_HX_REQUEST": "true"}


class SectoresVistasBase(ConDatosDeMaestros, TestCase):
    """Un Agrónomo con su invernadero, un Gerente y un Agrónomo ajeno; las rutas de cada ventana."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()
        self.gerente = crear_gerente()
        self.ajeno = crear_agronomo(email="ajeno@infoponia.com")
        self.client.force_login(self.agronomo)
        self.ficha = reverse("maestros:invernadero", args=[self.invernadero.pk])
        self.url_nuevo = reverse("maestros:sector_nuevo", args=[self.invernadero.pk])

    def url(self, nombre, sector):
        return reverse(f"maestros:{nombre}", args=[self.invernadero.pk, sector.pk])

    def datos(self, **extra):
        return {"nombre": "C-1", "tipo_etapa": tipo_etapa("germinacion").pk, "cant_agujeros_total": "100"} | extra


class FichaConSectoresVistaTests(SectoresVistasBase):
    """La pestaña «Sectores» y la capacidad (PROD-CNS-SCT)."""

    def test_regla_5_sin_sectores_la_pestana_lo_informa_y_ofrece_agregar(self):
        """PROD-CNS-SCT regla 5: el Sistema informa que sin sectores no se puede sembrar y al Agrónomo a cargo le ofrece uno."""
        respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, "Este invernadero aún no tiene sectores registrados")
        self.assertContains(respuesta, "Sin sectores no es posible sembrar.")
        self.assertContains(respuesta, "Agregar sector")
        self.assertContains(respuesta, "Sin sectores: todavía no se puede sembrar")
        self.assertNotContains(respuesta, "Capacidad")

    def test_regla_5_el_gerente_ve_el_aviso_sin_el_boton_de_agregar(self):
        """PROD-CNS-SCT regla 5 y D-30: al Gerente se le explica quién los registra; ningún botón lleva a un 403."""
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, "Los registra el Agrónomo del invernadero.")
        self.assertNotContains(respuesta, "Agregar sector")

    def test_regla_2_los_sectores_se_agrupan_por_etapa_con_sus_cantidades(self):
        """PROD-CNS-SCT regla 2: cada grupo dice cuántos sectores y agujeros tiene; los dados de baja van aparte."""
        crear_sector(self.invernadero, "G-1", "germinacion", 100)
        crear_sector(self.invernadero, "G-2", "germinacion", 50)
        crear_sector(self.invernadero, "F-1", "floracion", 30)
        crear_sector(self.invernadero, "B-1", "crecimiento", 10, estado="inactivo")
        respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, "2 sectores · 150 agujeros")
        self.assertContains(respuesta, "1 sector · 30 agujeros")
        self.assertContains(respuesta, "Dados de baja")
        contenido = respuesta.content.decode()
        self.assertLess(contenido.index("G-1"), contenido.index("F-1"))  # el orden de las etapas
        self.assertLess(contenido.index("F-1"), contenido.index("Dados de baja"))

    def test_post_b_con_sectores_desaparece_la_marca_de_sin_sectores(self):
        """PROD-ALT-SCT postcondición b: la marca «sin sectores» deja de mostrarse en la ficha y en la lista."""
        crear_sector(self.invernadero, "G-1")
        self.assertNotContains(self.client.get(self.ficha), "Sin sectores: todavía no se puede sembrar")
        self.assertNotContains(self.client.get(reverse("maestros:invernaderos")), "Sin sectores")

    def test_regla_3_un_sector_nuevo_muestra_todo_libre_y_sin_plantas(self):
        """PROD-CNS-SCT regla 3: «Sin plantas: acepta cualquier perfil» y los agujeros libres sobre el total."""
        crear_sector(self.invernadero, "G-1", agujeros=120)
        respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, "Sin plantas: acepta cualquier perfil")
        self.assertContains(respuesta, "libres de 120 agujeros")

    def test_regla_3_el_perfil_la_ocupacion_y_el_contenido_salen_de_los_registrantes(self):
        """PROD-CNS-SCT regla 3: perfil familiar, barra de ocupados y comprometidos y lotes, de los puntos de extensión."""
        sector = crear_sector(self.invernadero, "G-1", agujeros=100)
        lote = Contenido("lote", "L-7 · Lechuga Crespa", 40, None, None)
        with (
            con_agujeros(**{f"s{sector.pk}": (40, 10)}),
            con_extension("_PERFILES", lambda ids: {i: "Hoja verde" for i in ids}),
            con_extension("_CONTENIDOS", lambda ss: {s.pk: [lote] for s in ss}),
        ):
            respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, "Perfil familiar: Hoja verde")
        self.assertContains(respuesta, "libres de 100 agujeros")
        self.assertContains(respuesta, "width:40%")
        self.assertContains(respuesta, "width:10%")
        self.assertContains(respuesta, "L-7 · Lechuga Crespa")

    def test_regla_3_de_cns_inv_la_capacidad_cuenta_activos_y_fuera_de_servicio(self):
        """PROD-CNS-INV regla 3: por etapa, los agujeros, los libres y los sectores; los dados de baja no cuentan."""
        crear_sector(self.invernadero, "G-1", "germinacion", 100)
        crear_sector(self.invernadero, "G-2", "germinacion", 40, estado="fuera_de_servicio")
        crear_sector(self.invernadero, "G-3", "germinacion", 999, estado="inactivo")
        respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, "Capacidad")
        self.assertContains(respuesta, "agujeros · 140 libres · 2 sectores")
        self.assertContains(respuesta, "ocupado · 0 de 140 agujeros")

    def test_regla_4_un_sector_fuera_de_servicio_y_uno_dado_de_baja_se_distinguen(self):
        """PROD-CNS-SCT regla 4: el primero cuenta como capacidad pero no recibe plantas ni órdenes; el segundo, no cuenta."""
        crear_sector(self.invernadero, "F-1", "crecimiento", estado="fuera_de_servicio")
        crear_sector(self.invernadero, "B-1", "crecimiento", estado="inactivo")
        respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, "No recibe plantas ni órdenes, pero cuenta como capacidad.")
        self.assertContains(respuesta, "Dado de baja: no cuenta como capacidad. Conserva su historial.")

    def test_regla_6_el_menu_ofrece_las_acciones_segun_el_estado(self):
        """PROD-CNS-SCT regla 6 y D-30: activo -> modificar y baja; fuera de servicio -> modificar, volver a activar y baja;
        dado de baja -> solo reactivar."""
        activo = crear_sector(self.invernadero, "A-1")
        fuera = crear_sector(self.invernadero, "F-1", "crecimiento", estado="fuera_de_servicio")
        baja = crear_sector(self.invernadero, "B-1", "floracion", estado="inactivo")
        contenido = self.client.get(self.ficha).content.decode()
        for nombre, sector, presente in (
            ("sector_modificar", activo, True),
            ("sector_baja", activo, True),
            ("sector_volver_a_servicio", activo, False),
            ("sector_reactivar", activo, False),
            ("sector_volver_a_servicio", fuera, True),
            ("sector_modificar", fuera, True),
            ("sector_baja", fuera, True),
            ("sector_reactivar", fuera, False),
            ("sector_reactivar", baja, True),
            ("sector_modificar", baja, False),
            ("sector_baja", baja, False),
        ):
            with self.subTest(accion=nombre, sector=sector.nombre_sector):
                self.assertEqual(f'href="{self.url(nombre, sector)}"' in contenido, presente)

    def test_regla_1_el_gerente_ve_los_sectores_sin_ninguna_accion(self):
        """PROD-CNS-SCT regla 1 y D-30: el Gerente consulta en solo lectura; no hay menú ni botones."""
        sector = crear_sector(self.invernadero, "G-1")
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, "G-1")
        self.assertNotContains(respuesta, "sec-kb")
        self.assertNotContains(respuesta, self.url("sector_modificar", sector))
        self.assertNotContains(respuesta, "Las acciones de cada sector están en el menú")

    def test_regla_1_un_agronomo_ajeno_recibe_403_en_la_ficha(self):
        """PROD-CNS-SCT regla 1 y D-28: el Agrónomo consulta solo los invernaderos activos a su cargo (se aparta del texto de la
        «Verificación a mano» de la tarea, que decía «ve los sectores sin acciones»: manda el caso de uso)."""
        crear_sector(self.invernadero, "G-1")
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(self.ficha).status_code, 403)

    def test_regla_1_los_demas_roles_no_ven_la_ficha(self):
        """SEG-13: el Capataz no consulta invernaderos."""
        self.client.force_login(crear_capataz())
        self.assertEqual(self.client.get(self.ficha).status_code, 403)

    def test_regla_7_consultar_no_audita(self):
        """PROD-CNS-SCT regla 7 y SEG-14."""
        crear_sector(self.invernadero, "G-1")
        self.client.get(self.ficha)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_d29_la_ficha_pide_la_hoja_de_estilos_y_el_script_con_static_v(self):
        """Interfaz (D-29): los estáticos propios se piden con ``static_v`` (versión en la URL), también bajo DEBUG apagado."""
        respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, "maestros/css/sectores.css?v=")
        self.assertContains(respuesta, "maestros/js/sectores.js?v=")


class AccesoALasVentanasDeSectoresTests(SectoresVistasBase):
    """Quién llega a cada ventana (SEG-13, D-28, D-30)."""

    def rutas(self):
        sector = crear_sector(self.invernadero, "G-1")
        return [
            self.url_nuevo,
            self.url("sector_modificar", sector),
            self.url("sector_baja", sector),
            self.url("sector_reactivar", sector),
            self.url("sector_volver_a_servicio", sector),
        ]

    def test_el_gerente_recibe_403_en_todas_las_ventanas(self):
        """D-30 y regla 1 de PROD-CNS-SCT: solo el Agrónomo a cargo hace acciones (ningún botón del Gerente lleva ahí)."""
        rutas = self.rutas()
        self.client.force_login(self.gerente)
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 403)
                self.assertEqual(self.client.post(ruta, self.datos()).status_code, 403)

    def test_un_agronomo_ajeno_recibe_403_en_todas_las_ventanas(self):
        """PROD-ALT-SCT regla 1: solo el Agrónomo a cargo del invernadero."""
        rutas = self.rutas()
        self.client.force_login(self.ajeno)
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 403)
                self.assertEqual(self.client.post(ruta, self.datos()).status_code, 403)
        self.assertEqual(SectorProduccion.objects.count(), 1)

    def test_sin_sesion_redirige_al_inicio_de_sesion(self):
        """Toda pantalla exige sesión (D-25)."""
        rutas = self.rutas()
        self.client.logout()
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 302)

    def test_un_sector_de_otro_invernadero_del_mismo_agronomo_da_404(self):
        """Un sector se pide por su propio invernadero: si es de otro invernadero del mismo Agrónomo, 404."""
        otro = crear_invernadero("Otro", agronomo=self.agronomo)
        sector_de_otro = crear_sector(otro, "X-1")
        ruta = reverse("maestros:sector_modificar", args=[self.invernadero.pk, sector_de_otro.pk])
        self.assertEqual(self.client.get(ruta).status_code, 404)

    def test_un_sector_de_un_invernadero_ajeno_da_403(self):
        """D-28: un sector fuera del alcance da 403, no 404 (saber que existe no da acceso a nada)."""
        ajeno = crear_invernadero("Ajeno", agronomo=self.ajeno)
        sector_ajeno = crear_sector(ajeno, "X-1")
        ruta = reverse("maestros:sector_modificar", args=[self.invernadero.pk, sector_ajeno.pk])
        self.assertEqual(self.client.get(ruta).status_code, 403)

    def test_un_sector_que_no_existe_da_404(self):
        """D-28: un id inexistente da 404."""
        self.assertEqual(self.client.get(reverse("maestros:sector_baja", args=[self.invernadero.pk, 999999])).status_code, 404)

    def test_abrir_una_ventana_con_get_no_cambia_nada(self):
        """D-28 (confirmaciones): abrir la ventana no cambia ni audita nada; el cambio se hace con un POST."""
        activo = crear_sector(self.invernadero, "A-1")
        baja = crear_sector(self.invernadero, "B-1", "floracion", estado="inactivo")
        for ruta in (self.url("sector_baja", activo), self.url("sector_modificar", activo), self.url("sector_reactivar", baja), self.url_nuevo):
            self.client.get(ruta)
            self.client.get(ruta, **HX)
        activo.refresh_from_db()
        baja.refresh_from_db()
        self.assertEqual((activo.estado_sector, baja.estado_sector), ("activo", "inactivo"))
        self.assertEqual(SectorProduccion.objects.count(), 2)
        self.assertFalse(RegistroAuditoria.objects.exists())


class ProdAltSctVistaTests(SectoresVistasBase):
    """Ventana «Agregar sector» (PROD-ALT-SCT)."""

    def test_flujo_principal_la_ventana_viene_en_la_pagina_sin_javascript(self):
        """Respaldo sin JavaScript: la página es la ficha con la ventana abierta (``data-ventana``)."""
        respuesta = self.client.get(self.url_nuevo)
        self.assertContains(respuesta, "Agregar sector")
        self.assertContains(respuesta, "data-ventana")
        self.assertContains(respuesta, "Una planta ocupa un agujero en todas las etapas.")
        self.assertContains(respuesta, self.invernadero.nombre_invernadero)
        self.assertContains(respuesta, "Este invernadero aún no tiene sectores registrados")  # la ficha detrás
        for etapa in ("Germinación", "Crecimiento", "Floración", "Fructificación", "Maduración"):
            self.assertContains(respuesta, etapa)

    def test_flujo_principal_con_htmx_devuelve_solo_la_ventana(self):
        """HTMX inserta solo el fragmento sobre la ficha."""
        respuesta = self.client.get(self.url_nuevo, **HX)
        self.assertContains(respuesta, "Agregar sector")
        self.assertNotContains(respuesta, "Este invernadero aún no tiene sectores registrados")
        self.assertNotContains(respuesta, "<html")

    def test_las_ventanas_varian_por_htmx_y_no_se_guardan_en_cache(self):
        """Patrón ABM §7: ``@vary_on_headers("HX-Request")`` y ``@never_cache``."""
        respuesta = self.client.get(self.url_nuevo)
        self.assertIn("HX-Request", respuesta["Vary"])
        self.assertIn("no-cache", respuesta["Cache-Control"])

    def test_flujo_principal_agrega_el_sector_y_vuelve_a_la_ficha_con_un_aviso(self):
        """PROD-ALT-SCT: crea el sector, lo audita y vuelve a la ficha con «Sector C-1 agregado.»."""
        respuesta = self.client.post(self.url_nuevo, self.datos(), follow=True)
        self.assertRedirects(respuesta, self.ficha)
        self.assertContains(respuesta, "Sector C-1 agregado.")
        sector = SectorProduccion.objects.get()
        self.assertEqual((sector.nombre_sector, sector.cant_agujeros_total, sector.tipo_etapa.codigo), ("C-1", 100, "germinacion"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_sector").count(), 1)

    def test_regla_2_el_nombre_repetido_muestra_el_error_en_el_campo_y_conserva_lo_escrito(self):
        """PROD-ALT-SCT regla 2: el error va junto al campo, sin importar mayúsculas, y el formulario conserva lo escrito."""
        crear_sector(self.invernadero, "C-1")
        respuesta = self.client.post(self.url_nuevo, self.datos(nombre="c-1", cant_agujeros_total="77"))
        self.assertContains(respuesta, "Ya hay un sector con ese nombre en este invernadero.")
        self.assertContains(respuesta, 'value="c-1"')
        self.assertContains(respuesta, 'value="77"')
        self.assertEqual(SectorProduccion.objects.count(), 1)

    def test_regla_4_la_cantidad_cero_muestra_el_error_en_el_campo(self):
        """PROD-ALT-SCT regla 4: un entero mayor que cero."""
        respuesta = self.client.post(self.url_nuevo, self.datos(cant_agujeros_total="0"))
        self.assertContains(respuesta, "Ingresá un número entero mayor que 0.")
        self.assertFalse(SectorProduccion.objects.exists())

    def test_regla_3_sin_tipo_de_etapa_muestra_el_error_y_marca_el_elegido(self):
        """PROD-ALT-SCT regla 3: el tipo es obligatorio; con uno elegido, la ficha de radio queda marcada al reenviar."""
        respuesta = self.client.post(self.url_nuevo, self.datos(tipo_etapa=""))
        self.assertContains(respuesta, "Elegí el tipo de etapa.")
        respuesta = self.client.post(self.url_nuevo, self.datos(nombre="", tipo_etapa=tipo_etapa("floracion").pk))
        self.assertContains(respuesta, "Ingresá el nombre del sector.")
        self.assertContains(respuesta, f'value="{tipo_etapa("floracion").pk}" checked')

    def test_regla_2_todos_los_errores_se_muestran_juntos(self):
        """Patrón ABM §2: un error por campo, todos a la vez."""
        respuesta = self.client.post(self.url_nuevo, self.datos(nombre="", tipo_etapa="", cant_agujeros_total=""))
        for texto in ("Ingresá el nombre del sector.", "Elegí el tipo de etapa.", "Ingresá la cantidad de agujeros."):
            self.assertContains(respuesta, texto)


class ProdModSctVistaTests(SectoresVistasBase):
    """Ventana «Modificar sector» y su aviso de cambio de tipo (PROD-MOD-SCT)."""

    def setUp(self):
        super().setUp()
        self.sector = crear_sector(self.invernadero, "C-1", "germinacion", 100)
        self.ruta = self.url("sector_modificar", self.sector)

    def test_flujo_principal_la_ventana_trae_los_datos_del_sector(self):
        """PROD-MOD-SCT: el formulario arranca con el nombre y los agujeros; el invernadero no se cambia."""
        respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "Modificar sector C-1")
        self.assertContains(respuesta, "el invernadero de un sector no se cambia")
        self.assertContains(respuesta, 'value="C-1"')
        self.assertContains(respuesta, 'value="100"')
        self.assertContains(respuesta, "Se puede cambiar porque el sector está vacío y sin reservas.")

    def test_regla_1_con_agujeros_en_uso_el_tipo_queda_bloqueado_con_su_motivo(self):
        """PROD-MOD-SCT regla 1: el Sistema lo informa y el campo queda bloqueado."""
        with con_agujeros(ocupados=30, comprometidos=20):
            respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "No se puede cambiar mientras el sector tenga agujeros ocupados (30) o comprometidos (20).")
        self.assertContains(respuesta, "disabled")
        self.assertContains(respuesta, f'name="tipo_etapa" value="{self.sector.tipo_etapa_id}"')  # va en un campo oculto

    def test_regla_1_con_el_tipo_bloqueado_se_puede_guardar_el_nombre(self):
        """El bloqueo no impide cambiar lo demás: el tipo viaja en el campo oculto."""
        with con_agujeros(ocupados=30):
            self.client.post(self.ruta, self.datos(nombre="Nuevo", tipo_etapa=self.sector.tipo_etapa_id), follow=True)
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.nombre_sector, "Nuevo")

    def test_regla_1_bajar_por_debajo_del_minimo_muestra_el_error_en_el_campo(self):
        """PROD-MOD-SCT regla 1: «hay N ocupados y M comprometidos: como mínimo X»."""
        with con_agujeros(ocupados=30, comprometidos=20):
            respuesta = self.client.post(self.ruta, self.datos(cant_agujeros_total="40", tipo_etapa=self.sector.tipo_etapa_id))
        self.assertContains(respuesta, "Hay 30 agujeros ocupados y 20 comprometidos: como mínimo 50.")

    def test_flujo_principal_guarda_y_vuelve_a_la_ficha_con_un_aviso(self):
        """PROD-MOD-SCT: «Se guardaron los cambios del sector Nuevo.» y un registro de auditoría."""
        respuesta = self.client.post(self.ruta, self.datos(nombre="Nuevo", tipo_etapa=self.sector.tipo_etapa_id, cant_agujeros_total="150"), follow=True)
        self.assertRedirects(respuesta, self.ficha)
        self.assertContains(respuesta, "Se guardaron los cambios del sector Nuevo.")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_sector").count(), 1)

    def test_d28_guardar_sin_cambios_no_audita(self):
        """D-28: una modificación sin cambios no deja registro."""
        self.client.post(self.ruta, self.datos(tipo_etapa=self.sector.tipo_etapa_id), follow=True)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_4_cambiar_el_tipo_del_ultimo_sector_de_la_etapa_muestra_el_aviso_sin_guardar(self):
        """PROD-MOD-SCT regla 4: advierte antes de confirmar, sin cambiar nada."""
        respuesta = self.client.post(self.ruta, self.datos(tipo_etapa=tipo_etapa("crecimiento").pk))
        self.assertContains(respuesta, "Antes de cambiar el tipo de C-1")
        self.assertContains(respuesta, "es el último sector activo de Germinación")
        self.assertContains(respuesta, "Continuar igual")
        self.assertContains(respuesta, "Volver")
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.tipo_etapa.codigo, "germinacion")
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_4_el_aviso_suma_lo_que_informan_los_registrantes(self):
        """PROD-MOD-SCT regla 4: lotes y siembras afectados salen de los puntos de extensión."""
        aviso = Aviso("Siembras a realizar afectadas: OT-9.", 1)
        with con_extension("_AVISOS_DE_CAMBIO_DE_TIPO", lambda inv, tipo: [aviso]):
            respuesta = self.client.post(self.ruta, self.datos(tipo_etapa=tipo_etapa("crecimiento").pk))
        self.assertContains(respuesta, "Siembras a realizar afectadas: OT-9.")

    def test_regla_4_volver_reenvia_el_formulario_sin_guardar_y_con_lo_escrito(self):
        """PROD-MOD-SCT regla 4 («Volver»): vuelve a la ventana con los datos y no cambia nada."""
        respuesta = self.client.post(self.ruta, self.datos(nombre="Otro", tipo_etapa=tipo_etapa("crecimiento").pk, volver="1"))
        self.assertContains(respuesta, "Modificar sector C-1")
        self.assertContains(respuesta, 'value="Otro"')
        self.assertContains(respuesta, f'value="{tipo_etapa("crecimiento").pk}" checked')
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.nombre_sector, "C-1")

    def test_regla_4_continuar_igual_guarda_el_cambio_de_tipo(self):
        """PROD-MOD-SCT regla 4 («Continuar igual»): se guarda y vuelve a la ficha."""
        respuesta = self.client.post(
            self.ruta, self.datos(tipo_etapa=tipo_etapa("crecimiento").pk, advertencia_confirmada="1"), follow=True
        )
        self.assertRedirects(respuesta, self.ficha)
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.tipo_etapa.codigo, "crecimiento")

    def test_regla_3_un_sector_dado_de_baja_no_se_modifica_y_vuelve_a_la_ficha_con_el_motivo(self):
        """PROD-MOD-SCT regla 3: solo se reactiva; sin 403 (D-30)."""
        baja = crear_sector(self.invernadero, "B-1", "floracion", estado="inactivo")
        respuesta = self.client.get(self.url("sector_modificar", baja), follow=True)
        self.assertRedirects(respuesta, self.ficha)
        self.assertContains(respuesta, "El sector está dado de baja: solo se puede reactivar.")


class ProdBajSctVistaTests(SectoresVistasBase):
    """Ventana de baja de un sector (PROD-BAJ-SCT)."""

    def setUp(self):
        super().setUp()
        crear_sector(self.invernadero, "G-2", "germinacion")  # evita la advertencia de la regla 4
        self.sector = crear_sector(self.invernadero, "G-1", "germinacion")
        self.ruta = self.url("sector_baja", self.sector)

    def test_flujo_principal_la_ventana_pide_confirmar_y_no_cambia_nada(self):
        """PROD-BAJ-SCT: abrir la ventana (GET) muestra la confirmación sobre la ficha."""
        respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "¿Dar de baja G-1?")
        self.assertContains(respuesta, "deja de contar como capacidad del invernadero y conserva su historial")
        self.assertContains(respuesta, "Dando de baja…")
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.estado_sector, "activo")

    def test_flujo_principal_confirmar_da_de_baja_y_vuelve_a_la_ficha(self):
        """PROD-BAJ-SCT: «Sector G-1 dado de baja.» y un registro de auditoría."""
        respuesta = self.client.post(self.ruta, follow=True)
        self.assertRedirects(respuesta, self.ficha)
        self.assertContains(respuesta, "Sector G-1 dado de baja.")
        self.assertContains(respuesta, "Dados de baja")
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.estado_sector, "inactivo")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_sector").count(), 1)

    def test_regla_2_con_impedimentos_la_ventana_los_lista_todos_y_no_ofrece_confirmar(self):
        """PROD-BAJ-SCT reglas 2 y 3: dice todo lo que lo impide con cómo resolverlo; sin botón de baja (D-30)."""
        impedimentos = lambda s: [  # noqa: E731
            Impedimento("agujeros_ocupados", "Tiene 3 agujeros ocupados por L-1.", "Sacalo de servicio."),
            Impedimento("hardware_activo", "Tiene el equipo Sensor 1.", "Quitale el sector."),
        ]
        with con_extension("_IMPEDIMENTOS_DE_SECTOR", impedimentos):
            respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "No se puede dar de baja G-1")
        self.assertContains(respuesta, "Tiene 3 agujeros ocupados por L-1. Sacalo de servicio.")
        self.assertContains(respuesta, "Tiene el equipo Sensor 1. Quitale el sector.")
        self.assertNotContains(respuesta, "Dando de baja…")

    def test_regla_2_un_impedimento_que_aparece_antes_de_confirmar_se_muestra_y_no_da_de_baja(self):
        """El POST vuelve a verificar con todo bloqueado: la ventana vuelve a mostrarse con el impedimento."""
        impedimento = lambda s: [Impedimento("agujeros_ocupados", "Tiene agujeros ocupados.", "Sacalo de servicio.")]  # noqa: E731
        with con_extension("_IMPEDIMENTOS_DE_SECTOR", impedimento):
            respuesta = self.client.post(self.ruta)
        self.assertContains(respuesta, "No se puede dar de baja G-1")
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.estado_sector, "activo")

    def test_regla_4_el_ultimo_sector_del_tipo_muestra_la_advertencia_y_la_ventana_es_la_confirmacion(self):
        """PROD-BAJ-SCT regla 4: la advertencia va en la ventana (ultimoAviso del prototipo) y el POST la confirma."""
        unico = crear_sector(self.invernadero, "M-1", "maduracion")
        ruta = self.url("sector_baja", unico)
        respuesta = self.client.get(ruta)
        self.assertContains(respuesta, "es el último sector activo de Maduración")
        self.assertContains(respuesta, 'name="advertencia_confirmada"')
        self.client.post(ruta, {"advertencia_confirmada": "1"}, follow=True)
        unico.refresh_from_db()
        self.assertEqual(unico.estado_sector, "inactivo")

    def test_regla_4_un_envio_sin_confirmar_vuelve_a_mostrar_la_advertencia(self):
        """Patrón ABM §5: sin confirmación no se cambia nada; la ventana muestra lo que apareció."""
        unico = crear_sector(self.invernadero, "M-1", "maduracion")
        respuesta = self.client.post(self.url("sector_baja", unico))
        self.assertContains(respuesta, "es el último sector activo de Maduración")
        unico.refresh_from_db()
        self.assertEqual(unico.estado_sector, "activo")

    def test_pre_c_un_sector_ya_dado_de_baja_vuelve_a_la_ficha_con_el_motivo(self):
        """D-30: sin 403; la ficha explica por qué."""
        baja = crear_sector(self.invernadero, "B-1", "floracion", estado="inactivo")
        respuesta = self.client.get(self.url("sector_baja", baja), follow=True)
        self.assertContains(respuesta, "El sector ya está dado de baja.")


class ReactivarYVolverAServicioVistaTests(SectoresVistasBase):
    """Reactivar un sector dado de baja y volver a activar uno fuera de servicio (PROD-MOD-SCT, postcondiciones b y c)."""

    def test_post_c_reactivar_pide_confirmar_y_despues_deja_el_sector_activo(self):
        """PROD-MOD-SCT postcondición c: GET sin cambios; POST reactiva y avisa."""
        baja = crear_sector(self.invernadero, "B-1", "floracion", estado="inactivo")
        ruta = self.url("sector_reactivar", baja)
        respuesta = self.client.get(ruta)
        self.assertContains(respuesta, "¿Reactivar B-1?")
        self.assertContains(respuesta, "vuelve a contar como capacidad de Floración")
        baja.refresh_from_db()
        self.assertEqual(baja.estado_sector, "inactivo")
        respuesta = self.client.post(ruta, follow=True)
        self.assertRedirects(respuesta, self.ficha)
        self.assertContains(respuesta, "Sector B-1 activo de nuevo.")
        baja.refresh_from_db()
        self.assertEqual(baja.estado_sector, "activo")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="reactivacion_sector").count(), 1)

    def test_post_b_volver_a_activar_un_sector_fuera_de_servicio(self):
        """PROD-MOD-SCT postcondición b: GET sin cambios; POST lo deja activo (la bitácora es de PRD-04)."""
        fuera = crear_sector(self.invernadero, "F-1", "crecimiento", estado="fuera_de_servicio")
        ruta = self.url("sector_volver_a_servicio", fuera)
        self.assertContains(self.client.get(ruta), "¿Volver a activar F-1?")
        fuera.refresh_from_db()
        self.assertEqual(fuera.estado_sector, "fuera_de_servicio")
        self.assertContains(self.client.post(ruta, follow=True), "Sector F-1 activo de nuevo.")
        fuera.refresh_from_db()
        self.assertEqual(fuera.estado_sector, "activo")

    def test_regla_5_reactivar_un_sector_activo_vuelve_a_la_ficha_con_el_motivo(self):
        """D-30: ningún botón lleva a un error; si el estado no lo permite, la ficha explica por qué."""
        activo = crear_sector(self.invernadero, "A-1")
        respuesta = self.client.post(self.url("sector_reactivar", activo), follow=True)
        self.assertContains(respuesta, "El sector no está dado de baja.")
        respuesta = self.client.post(self.url("sector_volver_a_servicio", activo), follow=True)
        self.assertContains(respuesta, "El sector no está fuera de servicio.")

    def test_pre_b_reactivar_con_el_invernadero_inactivo_no_llega_a_la_ventana(self):
        """Un Agrónomo no consulta invernaderos inactivos (D-28): 403."""
        baja = crear_sector(self.invernadero, "B-1", "floracion", estado="inactivo")
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save()
        self.assertEqual(self.client.get(self.url("sector_reactivar", baja)).status_code, 403)
