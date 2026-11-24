# Pruebas de las pantallas de IOT-07 (paso 7; docs/casos_de_uso/iot/mantenimiento_automatico.md, «Pantallas»; D-79 puntos 1, 2 y 8; D-30: ningún botón lleva a un 403): la sección «Órdenes de mantenimiento» de la ficha
# del equipo y su ventana «Cancelar orden» (IOT-CNS-HDW regla 6 y PROD-CNL-ORD para un mantenimiento), la ventana de volver a activar con una fila por orden (IOT-MOD-HDW regla 8), los textos nuevos de las ventanas de baja
# del equipo y del sistema (IOT-BAJ-HDW y IOT-BAJ-SIS, precondición d) y, de punta a punta, que `produccion` no muestra los mantenimientos (D-67 punto 1).
# Integración con el cliente de prueba de Django; lo que solo ve un navegador (CSRF y Origin, JavaScript) va como paso de «navegador real» en la «Verificación a mano».
# La sección del Inicio del Técnico se prueba en test_inicio_tecnico.py.

from django.test import TestCase
from django.urls import reverse

from core.models import Notificacion
from core.tests.fabricas import crear_capataz
from iot.models import Actuador, Comando, MantenimientoTecnico
from iot.tests import fabricas
from iot.tests.test_iot_rsv_cmd_mantenimiento import AHORA, Escena
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo
from produccion.servicios import ordenes as ordenes_de_produccion

MOTIVO = "Se revisó el extractor en el invernadero"
HTMX = {"HX-Request": "true"}
ELIGE = "Elegí qué hacer con cada orden de mantenimiento."


class Base(Escena, TestCase):
    """Norte con su Agrónomo (Laura), su Técnico y un actuador «fuera de servicio» con una orden «a realizar»."""

    def setUp(self):
        super().setUp()
        Actuador.objects.filter(pk=self.actuador.pk).update(estado_hardware="fuera_de_servicio")
        Comando.objects.filter(pk=self.comando.pk).update(estado_comando="fallido", resuelto_en=AHORA)
        self.orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador], descripcion_orden="CMD-1 · Encender no se ejecutó en 4 intentos.")
        self.client.force_login(self.laura)

    def url(self, nombre, *args):
        return reverse(f"iot:{nombre}", args=args)

    def ficha(self):
        return self.url("hardware_ficha", self.actuador.pk)

    def ruta_de_cancelar(self, orden=None):
        return self.url("hardware_cancelar_orden", self.actuador.pk, (orden or self.orden).pk)

    def como(self, usuario):
        self.client.force_login(usuario)

    def sin_agronomo_activo(self):
        type(self.laura).objects.filter(pk=self.laura.pk).update(is_active=False)

    def otro_equipo(self, estado="fuera_de_servicio"):
        return fabricas.actuador(self.sistema, self.tipo, "norte/otro", estado=estado)


class FichaDelEquipoTests(Base):
    """IOT-CNS-HDW regla 6 y D-79 punto 1: la sección «Órdenes de mantenimiento»."""

    def test_regla_6_la_ficha_muestra_la_tabla_de_ordenes_con_sus_datos(self):
        respuesta = self.client.get(self.ficha())
        self.assertContains(respuesta, "Órdenes de mantenimiento")
        for texto in (self.orden.codigo, "Revisión", "A realizar", "Alta", "Tomás Quiroga", "CMD-1 · Encender no se ejecutó en 4 intentos."):
            self.assertContains(respuesta, texto)
        self.assertContains(respuesta, "Cancelar orden")

    def test_regla_6_sin_ordenes_la_seccion_lo_dice(self):
        MantenimientoTecnico.objects.all().delete()
        self.assertContains(self.client.get(self.ficha()), "Este equipo no tiene órdenes de mantenimiento.")

    def test_regla_6_una_cancelada_se_ve_con_su_motivo_y_sin_boton(self):
        MantenimientoTecnico.objects.filter(pk=self.orden.pk).update(estado_orden="cancelada", fecha_resolucion_orden=self.orden.fecha_programada_orden, motivo_cancelacion="Ya funciona")
        respuesta = self.client.get(self.ficha())
        self.assertContains(respuesta, "Cancelada")
        self.assertContains(respuesta, "Motivo: Ya funciona")
        self.assertNotContains(respuesta, "Cancelar orden")

    def test_regla_6_las_a_realizar_van_antes_que_las_canceladas(self):
        vieja = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador], estado="cancelada")
        html = self.client.get(self.ficha()).content.decode()
        self.assertLess(html.index(self.orden.codigo), html.index(vieja.codigo))

    def test_regla_6_un_sensor_tambien_muestra_las_ordenes_que_lo_incluyen(self):
        sensor = fabricas.sensor(self.sistema, "norte/temp")
        orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [sensor])
        self.assertContains(self.client.get(self.url("hardware_ficha", sensor.pk)), orden.codigo)

    def test_regla_6_la_ficha_de_un_equipo_no_muestra_las_ordenes_de_otro(self):
        otra = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.otro_equipo()])
        self.assertNotContains(self.client.get(self.ficha()), otra.codigo)

    def test_d30_el_gerente_con_agronomo_activo_ve_la_orden_sin_el_boton(self):
        self.como(self.gerente)
        respuesta = self.client.get(self.ficha())
        self.assertContains(respuesta, self.orden.codigo)
        self.assertNotContains(respuesta, "Cancelar orden")

    def test_d30_el_gerente_sin_agronomo_activo_ve_el_boton(self):
        self.sin_agronomo_activo()
        self.como(self.gerente)
        self.assertContains(self.client.get(self.ficha()), "Cancelar orden")

    def test_d30_ningun_boton_lleva_a_un_403(self):
        """El botón «Cancelar orden» solo está donde la ventana abre: para cada cuenta que lo ve, el enlace responde 200."""
        casos = [("laura", self.laura, False), ("gerente sin agrónomo activo", self.gerente, True)]
        for nombre, usuario, sin_agronomo in casos:
            with self.subTest(nombre):
                if sin_agronomo:
                    self.sin_agronomo_activo()
                self.como(usuario)
                html = self.client.get(self.ficha()).content.decode()
                self.assertIn(self.ruta_de_cancelar(), html)
                self.assertEqual(self.client.get(self.ruta_de_cancelar()).status_code, 200)
                self.assertEqual(self.client.get(self.ruta_de_cancelar(), headers=HTMX).status_code, 200)

    def test_otros_roles_y_otro_agronomo_no_ven_la_ficha(self):
        self.como(crear_capataz())
        self.assertEqual(self.client.get(self.ficha()).status_code, 403)
        self.como(self.tecnico)
        self.assertEqual(self.client.get(self.ficha()).status_code, 403)
        self.como(crear_agronomo("otro@infoponia.com"))
        self.assertEqual(self.client.get(self.ficha()).status_code, 404)


class VentanaCancelarOrdenTests(Base):
    """PROD-CNL-ORD pasos 4d, 5 y 6 y extensiones 6a y 8a, desde la ficha."""

    def test_ext_4d_abrir_la_ventana_con_htmx_es_un_fragmento_con_el_resumen_y_no_cambia_nada(self):
        respuesta = self.client.get(self.ruta_de_cancelar(), headers=HTMX)
        self.assertNotContains(respuesta, "<html")
        for texto in (f"Cancelar la orden {self.orden.codigo}", "Revisión", "norte/extractor", "Tomás Quiroga", "Sin repuestos reservados", "La alerta «comando fallido» sigue activa", "Motivo de la cancelación"):
            self.assertContains(respuesta, texto)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado_orden, "a_realizar")

    def test_ext_4d_sin_javascript_es_la_ficha_con_la_ventana_abierta(self):
        respuesta = self.client.get(self.ruta_de_cancelar())
        self.assertContains(respuesta, "<html")
        self.assertContains(respuesta, f"Cancelar la orden {self.orden.codigo}")
        self.assertContains(respuesta, "Órdenes de mantenimiento")

    def test_ext_6a_sin_motivo_la_ventana_vuelve_a_abrirse_con_el_error_y_no_cancela(self):
        respuesta = self.client.post(self.ruta_de_cancelar(), {"motivo": "   "})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Indicá el motivo de la cancelación.")
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado_orden, "a_realizar")

    def test_ext_6a_un_motivo_de_301_caracteres_vuelve_con_el_error_y_lo_escrito(self):
        respuesta = self.client.post(self.ruta_de_cancelar(), {"motivo": "x" * 301})
        self.assertContains(respuesta, "El motivo no puede pasar de 300 caracteres.")
        self.assertContains(respuesta, "x" * 301)

    def test_post_k_cancelar_vuelve_a_la_ficha_avisa_y_deja_la_orden_cancelada(self):
        """El flujo completo sin HTMX y con HTMX: redirige a la ficha, avisa, la orden queda cancelada y el equipo sigue fuera de servicio."""
        for cabeceras in ({}, HTMX):
            with self.subTest(htmx=bool(cabeceras)):
                orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
                respuesta = self.client.post(self.ruta_de_cancelar(orden), {"motivo": MOTIVO}, headers=cabeceras, follow=True)
                self.assertRedirects(respuesta, self.ficha())
                self.assertContains(respuesta, f"{orden.codigo} cancelada.")
                self.assertContains(respuesta, f"Motivo: {MOTIVO}")
                orden.refresh_from_db()
                self.actuador.refresh_from_db()
                self.assertEqual((orden.estado_orden, self.actuador.estado_hardware), ("cancelada", "fuera_de_servicio"))
        self.assertEqual(Notificacion.objects.filter(destinatario=self.tecnico, titulo__endswith="cancelada").count(), 2)

    def test_ext_8a_una_orden_que_ya_no_esta_a_realizar_vuelve_a_la_ficha_con_el_aviso(self):
        """La orden ya está cancelada: abrir la ventana o confirmar de nuevo manda a la ficha con «La orden ya no está a realizar: otra operación la canceló.»."""
        self.client.post(self.ruta_de_cancelar(), {"motivo": MOTIVO})
        aviso = "La orden ya no está a realizar: otra operación la canceló."
        abrir = self.client.get(self.ruta_de_cancelar(), follow=True)
        self.assertRedirects(abrir, self.ficha())
        self.assertContains(abrir, aviso)
        confirmar = self.client.post(self.ruta_de_cancelar(), {"motivo": "otra vez"}, follow=True)
        self.assertRedirects(confirmar, self.ficha())
        self.assertContains(confirmar, aviso)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.motivo_cancelacion, MOTIVO)

    def test_regla_la_orden_de_otro_equipo_en_la_url_da_404(self):
        ajena = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.otro_equipo()])
        self.assertEqual(self.client.get(self.ruta_de_cancelar(ajena)).status_code, 404)
        self.assertEqual(self.client.post(self.ruta_de_cancelar(ajena), {"motivo": MOTIVO}).status_code, 404)
        ajena.refresh_from_db()
        self.assertEqual(ajena.estado_orden, "a_realizar")

    def test_regla_alcance_el_gerente_con_agronomo_activo_recibe_403_por_la_direccion_escrita_a_mano(self):
        self.como(self.gerente)
        self.assertEqual(self.client.get(self.ruta_de_cancelar()).status_code, 403)
        self.assertEqual(self.client.post(self.ruta_de_cancelar(), {"motivo": MOTIVO}).status_code, 403)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado_orden, "a_realizar")

    def test_regla_alcance_el_gerente_sin_agronomo_activo_cancela(self):
        self.sin_agronomo_activo()
        self.como(self.gerente)
        self.client.post(self.ruta_de_cancelar(), {"motivo": MOTIVO})
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado_orden, "cancelada")

    def test_regla_alcance_otro_agronomo_el_tecnico_y_otros_roles_no_entran(self):
        casos = [(crear_agronomo("otro@infoponia.com"), 404), (self.tecnico, 403), (crear_capataz(), 403)]
        for usuario, estado in casos:
            with self.subTest(usuario=type(usuario).__name__):
                self.como(usuario)
                self.assertEqual(self.client.get(self.ruta_de_cancelar()).status_code, estado)
                self.assertEqual(self.client.post(self.ruta_de_cancelar(), {"motivo": MOTIVO}).status_code, estado)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado_orden, "a_realizar")

    def test_sin_sesion_va_al_ingreso(self):
        self.client.logout()
        respuesta = self.client.get(self.ruta_de_cancelar())
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith("/iniciar-sesion/"))

    def test_metodo_no_permitido(self):
        self.assertEqual(self.client.delete(self.ruta_de_cancelar()).status_code, 405)


class VentanaVolverAActivarTests(Base):
    """IOT-MOD-HDW regla 8 y D-79 punto 8: una fila por orden, con «Cancelarla» marcada de entrada y «Mantenerla»."""

    def ruta(self):
        return self.url("hardware_volver_a_activar", self.actuador.pk)

    def test_regla_8_la_ventana_lista_cada_orden_con_cancelarla_marcada_y_mantenerla(self):
        respuesta = self.client.get(self.ruta(), headers=HTMX)
        self.assertNotContains(respuesta, "<html")
        self.assertContains(respuesta, "Órdenes de mantenimiento a realizar")
        self.assertContains(respuesta, self.orden.codigo)
        self.assertContains(respuesta, f'name="decision_{self.orden.pk}" value="cancelar" checked')
        self.assertContains(respuesta, f'name="decision_{self.orden.pk}" value="mantener"')
        self.assertNotContains(respuesta, f'name="decision_{self.orden.pk}" value="mantener" checked')

    def test_regla_8_sin_ordenes_la_ventana_es_la_de_iot_02(self):
        MantenimientoTecnico.objects.all().delete()
        respuesta = self.client.get(self.ruta(), headers=HTMX)
        self.assertContains(respuesta, "El equipo vuelve a estar activo y puede recibir comandos.")
        self.assertNotContains(respuesta, "Órdenes de mantenimiento a realizar")

    def test_regla_8_una_orden_con_otro_equipo_fuera_de_servicio_solo_ofrece_mantenerla(self):
        otro = self.otro_equipo()
        orden = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador, otro])
        respuesta = self.client.get(self.ruta(), headers=HTMX)
        self.assertContains(respuesta, "Incluye otros equipos fuera de servicio: ")
        self.assertContains(respuesta, "norte/otro")
        self.assertNotContains(respuesta, f'name="decision_{orden.pk}" value="cancelar"')
        self.assertContains(respuesta, f'name="decision_{orden.pk}" value="mantener" checked')

    def test_regla_8_abrir_la_ventana_no_cambia_nada(self):
        self.client.get(self.ruta())
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.estado_hardware, "fuera_de_servicio")

    def test_post_b_cancelar_la_orden_y_volver_a_activar(self):
        respuesta = self.client.post(self.ruta(), {f"decision_{self.orden.pk}": "cancelar"}, follow=True)
        self.assertRedirects(respuesta, self.ficha())
        self.assertContains(respuesta, "volvió a estar activo")
        self.orden.refresh_from_db()
        self.actuador.refresh_from_db()
        self.assertEqual((self.actuador.estado_hardware, self.orden.estado_orden, self.orden.motivo_cancelacion), ("activo", "cancelada", "Se volvió a activar el equipo norte/extractor."))

    def test_post_b_mantener_la_orden_y_volver_a_activar(self):
        self.client.post(self.ruta(), {f"decision_{self.orden.pk}": "mantener"})
        self.orden.refresh_from_db()
        self.actuador.refresh_from_db()
        self.assertEqual((self.actuador.estado_hardware, self.orden.estado_orden), ("activo", "a_realizar"))

    def test_regla_8_sin_elegir_la_ventana_vuelve_con_el_mensaje_y_no_activa(self):
        respuesta = self.client.post(self.ruta(), {})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, ELIGE)
        self.assertContains(respuesta, self.orden.codigo)
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.estado_hardware, "fuera_de_servicio")

    def test_regla_8_si_falta_elegir_una_se_conserva_lo_marcado_en_la_otra(self):
        otra = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.actuador])
        respuesta = self.client.post(self.ruta(), {f"decision_{self.orden.pk}": "mantener"})
        self.assertContains(respuesta, ELIGE)
        self.assertContains(respuesta, f'name="decision_{self.orden.pk}" value="mantener" checked')
        self.assertContains(respuesta, f'name="decision_{otra.pk}" value="cancelar" checked')  # la que no se había elegido vuelve a la opción de entrada

    def test_regla_8_las_ordenes_cambiaron_la_ventana_se_vuelve_a_abrir_con_las_de_ahora(self):
        MantenimientoTecnico.objects.filter(pk=self.orden.pk).update(estado_orden="cancelada", fecha_resolucion_orden=self.orden.fecha_programada_orden, motivo_cancelacion="x")
        respuesta = self.client.post(self.ruta(), {f"decision_{self.orden.pk}": "cancelar"})
        self.assertContains(respuesta, "Las órdenes del equipo cambiaron mientras confirmabas: revisalas de nuevo.")
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.estado_hardware, "fuera_de_servicio")

    def test_regla_8_una_decision_ajena_o_basura_no_cancela_nada(self):
        ajena = fabricas.mantenimiento_tecnico(self.norte, self.tecnico, [self.otro_equipo()])
        self.client.post(self.ruta(), {f"decision_{self.orden.pk}": "mantener", f"decision_{ajena.pk}": "cancelar", "decision_x": "cancelar"})
        ajena.refresh_from_db()
        self.assertEqual(ajena.estado_orden, "a_realizar")

    def test_regla_8_sin_ordenes_volver_a_activar_sigue_igual_que_en_iot_02(self):
        MantenimientoTecnico.objects.all().delete()
        respuesta = self.client.post(self.ruta(), follow=True)
        self.assertContains(respuesta, "volvió a estar activo")


class VentanasDeBajaTests(Base):
    """IOT-BAJ-HDW e IOT-BAJ-SIS, precondición d: los textos nuevos de los impedimentos."""

    def test_precondicion_d_la_ventana_de_baja_del_equipo_nombra_la_orden_y_no_deja_confirmar(self):
        respuesta = self.client.get(self.url("hardware_baja", self.actuador.pk), headers=HTMX)
        self.assertContains(respuesta, f"Está en la orden de mantenimiento {self.orden.codigo}, a realizar: cancelala desde «Órdenes de mantenimiento», en la ficha del equipo.")
        self.assertNotContains(respuesta, "Concretala")
        self.assertNotContains(respuesta, 'data-enviando="Dando de baja…"')

    def test_precondicion_d_la_ventana_de_baja_del_sistema_nombra_las_ordenes_y_no_deja_confirmar(self):
        respuesta = self.client.get(self.url("sistema_baja", self.sistema.pk), headers=HTMX)
        self.assertContains(respuesta, f"Hay 1 orden(es) de mantenimiento a realizar ({self.orden.codigo}): cancelalas desde la ficha de cada equipo.")
        self.assertNotContains(respuesta, "Concretalas")

    def test_precondicion_d_con_la_orden_cancelada_la_ventana_del_equipo_deja_dar_de_baja(self):
        self.client.post(self.ruta_de_cancelar(), {"motivo": MOTIVO})
        respuesta = self.client.get(self.url("hardware_baja", self.actuador.pk), headers=HTMX)
        self.assertNotContains(respuesta, "de mantenimiento")
        self.assertContains(respuesta, 'data-enviando="Dando de baja…"')


class ProduccionNoMuestraLosMantenimientosTests(Base):
    """D-67 punto 1 y `docs/api/produccion.md`, sección 9: con un mantenimiento REAL (la hija de `iot`), la bandeja del Capataz, `lista_de_ordenes` y `ordenes_cancelables` no lo incluyen. La lógica es de PRD-01; acá se
    confirma que la hija real no cambia nada."""

    def test_la_bandeja_del_capataz_no_lo_incluye(self):
        capataz = crear_capataz_activo()
        type(self.norte).objects.filter(pk=self.norte.pk).update(capataz=capataz)
        bandeja = ordenes_de_produccion.bandeja_del_capataz(capataz)
        self.assertEqual((bandeja.vencidas, bandeja.hoy, bandeja.proximas), ([], [], []))
        self.assertEqual(ordenes_de_produccion.ordenes_del_capataz(capataz), [])

    def test_la_lista_de_ordenes_del_agronomo_y_del_gerente_no_lo_incluye(self):
        for usuario in (self.laura, self.gerente):
            with self.subTest(usuario=type(usuario).__name__):
                ids = [f.orden_id for f in ordenes_de_produccion.lista_de_ordenes(usuario, ordenes_de_produccion.FiltrosDeOrdenes())]
                self.assertNotIn(self.orden.pk, ids)

    def test_las_ordenes_cancelables_no_lo_incluyen(self):
        self.assertEqual(ordenes_de_produccion.ordenes_cancelables(self.laura), [])

    def test_cancelar_orden_de_produccion_lo_rechaza_y_no_lo_toca(self):
        from produccion.errores import ErrorDeProduccion

        with self.assertRaises(ErrorDeProduccion) as contexto:
            ordenes_de_produccion.cancelar_orden(self.laura, self.orden.pk, "motivo")
        self.assertEqual(contexto.exception.codigo, "orden_no_cancelable")
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado_orden, "a_realizar")

    def test_la_pantalla_de_ordenes_de_produccion_no_lo_muestra_ni_abre_su_detalle(self):
        respuesta = self.client.get(reverse("produccion:ordenes"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, self.orden.codigo)
        self.assertEqual(self.client.get(reverse("produccion:orden", args=[self.orden.pk])).status_code, 404)
