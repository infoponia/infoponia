# Pruebas de las pantallas de variedades de INV-03 (paso 8; integración con el cliente de prueba de Django): la tabla de cada tarjeta de «Cultivos y
# variedades» (PROD-CNS-VAR), el formulario de alta y de modificación con su resumen y la advertencia de rangos (PROD-ALT-VAR, PROD-MOD-VAR), «Qué sigue»,
# la baja (PROD-BAJ-VAR) y la reactivación. Fuente: docs/casos_de_uso/inventario/variedades.md («Decisiones de aplicación», «Sin JavaScript»), D-30 y D-47.
# Solo el Agrónomo: el Gerente recibe 404 en toda ruta de variedades (regla 5 de PROD-CNS-VAR), los demás roles 403. Cada paso es una página (respaldo
# sin JavaScript); HTMX solo redibuja las etapas del perfil.

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.extensiones import UsoDeVariedad
from inventario.models import InsumoInvernadero, Semilla
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    usos_de_variedad_de_prueba,
    variedad_con_semilla,
    variedades_presentes_de_prueba,
)
from inventario.tests.test_prod_mod_var import datos_de
from maestros.extensiones import Impedimento
from maestros.models import Variedad
from maestros.tests.fabricas import crear_agronomo, crear_cultivo, crear_invernadero

HX = {"HTTP_HX_REQUEST": "true"}
ETAPAS = [("germinacion", 5), ("crecimiento", 10), ("maduracion", 20)]


def post_de(datos, **extra):
    """Los campos que envía el formulario para unos ``DatosDeVariedad`` (como los reenvía cada paso); ``extra`` pisa campos (por ejemplo ``accion``)."""
    campos = {
        "nombre": datos.nombre,
        "perfil_familia": datos.perfil_familia,
        "duracion_post_cosecha": datos.duracion_post_cosecha,
        "peso_promedio_planta": datos.peso_promedio_planta,
    }
    for columna in ("temp_ambiente", "humedad", "intensidad_luz", "fotoperiodo"):
        campos[f"{columna}_min"] = getattr(datos, f"{columna}_min")
        campos[f"{columna}_max"] = getattr(datos, f"{columna}_max")
    for codigo, dias in datos.etapas:
        campos[f"etapa_{codigo}"] = "1"
        campos[f"duracion_{codigo}"] = dias
    campos.update(extra)
    return campos


def datos_validos(**cambios):
    """Los datos de una variedad nueva válida («Butterhead», hoja verde, 35 días de ciclo)."""
    from inventario.servicios.variedades import DatosDeVariedad

    base = {
        "nombre": "Butterhead",
        "perfil_familia": "hoja_verde",
        "etapas": (("germinacion", "5"), ("crecimiento", "10"), ("maduracion", "20")),
        "temp_ambiente_min": "18,5", "temp_ambiente_max": "24",
        "humedad_min": "60", "humedad_max": "80",
        "intensidad_luz_min": "200", "intensidad_luz_max": "400",
        "fotoperiodo_min": "12", "fotoperiodo_max": "16",
        "duracion_post_cosecha": "7",
        "peso_promedio_planta": "150",
    }
    base.update(cambios)
    return DatosDeVariedad(**base)


class VistasDeVariedadesBase(ConDatosDeInventario, TestCase):
    """Dos Agrónomos con un invernadero cada uno, un Gerente, un Capataz y la variedad «Lechuga Crespa» (hoja verde, 35 días de ciclo)."""

    def setUp(self):
        self.ana = crear_agronomo("ana@infoponia.com", nombre="Ana", apellido="Pérez")
        self.beto = crear_agronomo("beto@infoponia.com", nombre="Beto", apellido="Gómez")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.beto)
        self.gerente = crear_gerente()
        self.cultivo = crear_cultivo("Lechuga")
        self.variedad = variedad_con_semilla(self.cultivo, "Crespa", etapas=ETAPAS)
        self.client.force_login(self.ana)

    def semilla(self, variedad=None):
        return Semilla.objects.get(variedad=variedad or self.variedad)

    def url_nueva(self):
        return reverse("variedades:variedad_nueva", args=[self.cultivo.pk])

    def url(self, nombre, variedad=None):
        return reverse(f"variedades:{nombre}", args=[(variedad or self.variedad).pk])

    def enviar(self, url, datos, accion, **extra):
        return self.client.post(url, post_de(datos, accion=accion, **extra))


class PermisosTests(VistasDeVariedadesBase):
    """Regla 5 de PROD-CNS-VAR y SEG-13: solo el Agrónomo; el Gerente no ve que las rutas existen."""

    def rutas(self):
        return [
            self.url_nueva(),
            self.url("variedad"),
            self.url("variedad_creada"),
            self.url("variedad_baja"),
            self.url("variedad_reactivar"),
            reverse("variedades:etapas_del_perfil"),
        ]

    def test_regla_5_cns_el_gerente_recibe_404_en_toda_ruta_de_variedades(self):
        """PROD-CNS-VAR regla 5: el Gerente no consulta variedades; la URL le da 404, con y sin HTMX."""
        self.client.force_login(self.gerente)
        for ruta in self.rutas():
            self.assertEqual(self.client.get(ruta).status_code, 404, ruta)
            self.assertEqual(self.client.get(ruta, **HX).status_code, 404, ruta)
            self.assertEqual(self.client.post(ruta, {}).status_code, 404, ruta)

    def test_otros_roles_reciben_403(self):
        """SEG-13: un Capataz no entra a las pantallas de variedades."""
        self.client.force_login(crear_capataz())
        for ruta in self.rutas():
            self.assertEqual(self.client.get(ruta).status_code, 403, ruta)

    def test_sin_sesion_lleva_al_inicio_de_sesion(self):
        """D-25: toda pantalla exige sesión."""
        self.client.logout()
        for ruta in self.rutas():
            self.assertEqual(self.client.get(ruta).status_code, 302, ruta)

    def test_el_gerente_no_ve_la_pestana_de_cultivos(self):
        """PROD-CNS-VAR regla 5: la tabla de variedades vive en «Cultivos y variedades», que el Gerente no consulta."""
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("maestros:cultivos")).status_code, 404)


class TablaDeVariedadesTests(VistasDeVariedadesBase):
    """PROD-CNS-VAR reglas 1, 2 y 4: lo que el registrante entrega a la tarjeta de cada cultivo."""

    def get(self):
        return self.client.get(reverse("maestros:cultivos"))

    def test_regla_2_cns_la_tabla_muestra_perfil_ciclo_semilla_y_estado(self):
        """PROD-CNS-VAR regla 2: nombre, perfil, duración del ciclo con sus etapas, semilla «Sin habilitar» y estado."""
        respuesta = self.get()
        self.assertContains(respuesta, "Crespa")
        self.assertContains(respuesta, "Hoja verde")
        self.assertContains(respuesta, "35 días")
        self.assertContains(respuesta, "Germinación")
        self.assertContains(respuesta, "Semilla Lechuga Crespa")
        self.assertContains(respuesta, "Sin habilitar")
        self.assertContains(respuesta, "Activa")

    def test_regla_2_cns_la_semilla_habilitada_muestra_sus_invernaderos(self):
        """PROD-CNS-VAR regla 2: «Habilitada en Invernadero Norte»."""
        existencia(self.semilla(), self.norte)
        self.assertContains(self.get(), "Habilitada en Invernadero Norte")

    def test_regla_1_cns_se_ven_las_variedades_inactivas_con_su_reactivar(self):
        """PROD-CNS-VAR reglas 1 y 4: una inactiva figura y ofrece reactivar (el cultivo está activo)."""
        inactiva = variedad_con_semilla(self.cultivo, "Romana", activa=False)
        respuesta = self.get()
        self.assertContains(respuesta, "Romana")
        self.assertContains(respuesta, "Inactiva")
        self.assertContains(respuesta, self.url("variedad_reactivar", inactiva))

    def test_regla_4_cns_el_boton_agregar_variedad_solo_con_el_cultivo_activo(self):
        """PROD-CNS-VAR regla 4 y D-30: «+ Variedad» lleva al alta del cultivo activo; un cultivo inactivo no lo ofrece."""
        self.assertContains(self.get(), self.url_nueva())
        inactivo = crear_cultivo("Rúcula", activo=False)
        self.assertNotContains(self.get(), reverse("variedades:variedad_nueva", args=[inactivo.pk]))

    def test_regla_4_cns_sin_permiso_las_acciones_se_ven_deshabilitadas_con_el_motivo(self):
        """PROD-CNS-VAR regla 4 y D-30: si la usa otro invernadero, modificar y dar de baja no llevan a ningún lado y dicen quién la usa."""
        existencia(self.semilla(), self.sur)
        respuesta = self.get()
        self.assertContains(respuesta, "Solo la usa Invernadero Sur (Beto Gómez).")
        self.assertNotContains(respuesta, self.url("variedad_baja"))

    def test_regla_4_cns_con_el_cultivo_inactivo_no_se_reactiva_la_variedad(self):
        """PROD-CNS-VAR regla 4: «Primero reactivá el cultivo Lechuga» y el enlace de reactivar no se ofrece."""
        inactiva = variedad_con_semilla(self.cultivo, "Romana", activa=False)
        self.cultivo.estado_cultivo = "inactivo"
        self.cultivo.save()
        respuesta = self.get()
        self.assertContains(respuesta, "Primero reactivá el cultivo Lechuga.")
        self.assertNotContains(respuesta, self.url("variedad_reactivar", inactiva))

    def test_regla_2_cns_un_cultivo_sin_variedades_lo_dice(self):
        """PROD-CNS-VAR regla 1: un cultivo sin variedades muestra «Todavía no tiene variedades»."""
        crear_cultivo("Rúcula")
        self.assertContains(self.get(), "Todavía no tiene variedades")

    def test_la_tabla_escapa_los_nombres(self):
        """Seguridad: un nombre con HTML se muestra escapado."""
        variedad_con_semilla(self.cultivo, "<i>Rara</i>")
        respuesta = self.get()
        self.assertContains(respuesta, "&lt;i&gt;Rara&lt;/i&gt;")
        self.assertNotContains(respuesta, "<i>Rara</i>")

    def test_la_tabla_no_hace_consultas_por_fila(self):
        """PROD-CNS-VAR: la cantidad de consultas no crece con la cantidad de variedades (ni de cultivos)."""
        existencia(self.semilla(), self.norte)  # una semilla habilitada: con ninguna, hay una consulta de invernaderos que se omite
        self.get()  # calienta cachés (tipos de contenido, sesión)
        with CaptureQueriesContext(connection) as pocas:
            self.get()
        for i in range(5):
            otro = crear_cultivo(f"Cultivo {i}")
            for j in range(3):
                variedad = variedad_con_semilla(otro, f"Variedad {j}", etapas=ETAPAS)
                existencia(self.semilla(variedad), self.norte)
        with CaptureQueriesContext(connection) as muchas:
            self.get()
        self.assertEqual(len(muchas), len(pocas))


class AltaDeVariedadTests(VistasDeVariedadesBase):
    """PROD-ALT-VAR: formulario, resumen, confirmación y «Qué sigue»."""

    def test_flujo_principal_formulario_resumen_alta_y_que_sigue(self):
        """PROD-ALT-VAR reglas 8 y 9: el formulario, el resumen sin escribir, la creación con un solo registro y «Qué sigue» con el botón de habilitar."""
        self.assertContains(self.client.get(self.url_nueva()), "Nueva variedad")
        resumen = self.enviar(self.url_nueva(), datos_validos(), "revisar")
        self.assertContains(resumen, "Resumen de la nueva variedad")
        self.assertContains(resumen, "35 días")  # duración del ciclo (la suma)
        self.assertContains(resumen, "15 días de la siembra")  # cosecha estimada
        self.assertContains(resumen, "Semilla Lechuga Butterhead")
        self.assertFalse(Variedad.objects.filter(nombre_variedad="Butterhead").exists())
        creada = self.enviar(self.url_nueva(), datos_validos(), "guardar")
        nueva = Variedad.objects.get(nombre_variedad="Butterhead")
        self.assertRedirects(creada, self.url("variedad_creada", nueva))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_variedad").count(), 1)
        que_sigue = self.client.get(self.url("variedad_creada", nueva))
        self.assertContains(que_sigue, "Qué sigue")
        self.assertContains(que_sigue, f"{reverse('inventario:habilitar')}?insumo={self.semilla(nueva).pk}")

    def test_regla_8_el_resumen_conserva_lo_escrito_en_campos_ocultos(self):
        """PROD-ALT-VAR regla 8: «Volver a editar» regresa al formulario con lo ya escrito."""
        resumen = self.enviar(self.url_nueva(), datos_validos(), "revisar")
        self.assertContains(resumen, 'name="nombre" value="Butterhead"')
        vuelta = self.enviar(self.url_nueva(), datos_validos(), "volver")
        self.assertContains(vuelta, 'value="Butterhead"')
        self.assertContains(vuelta, 'value="18,5"')

    def test_errores_por_campo_al_revisar_sin_completar_nada(self):
        """PROD-ALT-VAR reglas 2 a 7: sin validación en vivo, al revisar cada campo marca su error (textos del prototipo, en voseo)."""
        respuesta = self.client.post(self.url_nueva(), {"accion": "revisar"})
        self.assertContains(respuesta, "Ingresá el nombre de la variedad.")
        self.assertContains(respuesta, "Elegí el perfil familiar.")
        self.assertContains(respuesta, "Ingresá la mínima.")  # temperatura, humedad e intensidad (femenino)
        self.assertContains(respuesta, "Ingresá el mínimo.")  # fotoperíodo (masculino)
        self.assertContains(respuesta, "Ingresá los días de postcosecha.")
        self.assertContains(respuesta, "Ingresá los días.")
        self.assertContains(respuesta, "Revisá los campos marcados.")

    def test_regla_6_el_minimo_mayor_que_el_maximo_marca_el_campo(self):
        """PROD-ALT-VAR regla 6: el mínimo no puede ser mayor que el máximo."""
        respuesta = self.enviar(self.url_nueva(), datos_validos(humedad_min="90", humedad_max="80"), "revisar")
        self.assertContains(respuesta, "no puede ser menor que")

    def test_regla_2_el_nombre_repetido_con_otras_mayusculas_da_error(self):
        """PROD-ALT-VAR regla 2: el nombre es único en el cultivo sin distinguir mayúsculas."""
        respuesta = self.enviar(self.url_nueva(), datos_validos(nombre="crespa"), "revisar")
        self.assertContains(respuesta, "Ya existe la variedad Lechuga crespa.")

    def test_regla_4_al_elegir_el_perfil_se_ofrecen_solo_sus_etapas(self):
        """PROD-ALT-VAR regla 4: el fragmento de etapas ofrece las del perfil; Germinación y Maduración siempre."""
        hoja = self.client.get(reverse("variedades:etapas_del_perfil"), {"perfil_familia": "hoja_verde"}, **HX)
        for presente in ("Germinación", "Crecimiento", "Maduración"):
            self.assertContains(hoja, presente)
        for ausente in ("Floración", "Fructificación"):
            self.assertNotContains(hoja, f'name="etapa_{ausente.lower().replace("ó", "o").replace("í", "i")}"')
        frutos = self.client.get(reverse("variedades:etapas_del_perfil"), {"perfil_familia": "frutos_grandes"}, **HX)
        self.assertContains(frutos, 'name="etapa_floracion"')
        self.assertContains(frutos, 'name="etapa_fructificacion"')

    def test_el_fragmento_de_etapas_no_valida(self):
        """Interfaz: redibujar las etapas no muestra errores aunque falte todo."""
        respuesta = self.client.get(reverse("variedades:etapas_del_perfil"), {"perfil_familia": "flores"}, **HX)
        self.assertNotContains(respuesta, "Ingresá")

    def test_sin_javascript_actualizar_etapas_reenvia_sin_validar(self):
        """Interfaz: el botón «Actualizar etapas» (sin JavaScript) vuelve a dibujar las etapas del perfil sin errores."""
        respuesta = self.client.post(self.url_nueva(), {"accion": "actualizar", "perfil_familia": "frutos_pequenos"})
        self.assertContains(respuesta, 'name="etapa_fructificacion"')
        self.assertNotContains(respuesta, "Ingresá el nombre")
        self.assertContains(respuesta, 'value="actualizar"')

    def test_regla_4_el_servicio_no_confia_en_la_pantalla(self):
        """PROD-ALT-VAR regla 4: una etapa no permitida por el perfil, aunque llegue en el pedido, no se crea."""
        datos = post_de(datos_validos(), accion="guardar", etapa_floracion="1", duracion_floracion="3")
        self.client.post(self.url_nueva(), datos)
        self.assertEqual(Variedad.objects.get(nombre_variedad="Butterhead").ciclo.etapas.count(), 3)

    def test_el_alta_en_un_cultivo_inactivo_vuelve_a_la_lista_con_el_motivo(self):
        """PROD-ALT-VAR precondición b: un cultivo inactivo no recibe variedades."""
        self.cultivo.estado_cultivo = "inactivo"
        self.cultivo.save()
        respuesta = self.client.get(self.url_nueva(), follow=True)
        self.assertContains(respuesta, "está inactivo")

    def test_que_sigue_sin_invernadero_a_cargo_no_ofrece_habilitar(self):
        """D-30: sin invernaderos a su cargo, el Agrónomo no ve un botón que no podría usar."""
        sin = crear_agronomo("sin@infoponia.com")
        self.client.force_login(sin)
        self.assertNotContains(self.client.get(self.url("variedad_creada")), "Habilitar la semilla")

    def test_habilitar_acepta_la_semilla_fijada_pero_la_lista_general_no_la_ofrece(self):
        """INV-03 paso 8: la ventana de CMP-HAB-IIN abre con la semilla elegida; sin ella, la lista general sigue sin semillas (INV-02)."""
        semilla = self.semilla()
        fijada = self.client.get(reverse("inventario:habilitar"), {"insumo": semilla.pk}, **HX)
        self.assertContains(fijada, semilla.nombre_insumo)
        self.assertContains(fijada, f'name="insumo" value="{semilla.pk}"')
        general = self.client.get(reverse("inventario:habilitar"), **HX)
        self.assertNotContains(general, semilla.nombre_insumo)
        enviada = self.client.post(
            reverse("inventario:habilitar"),
            {"insumo": semilla.pk, "invernadero": self.norte.pk, "cant_min": "10", "referencia_precio": "5"},
        )
        self.assertEqual(enviada.status_code, 302)
        self.assertTrue(InsumoInvernadero.objects.filter(insumo=semilla, invernadero=self.norte).exists())


class ModificacionDeVariedadTests(VistasDeVariedadesBase):
    """PROD-MOD-VAR y PROD-CNS-VAR regla 3: el formulario es también el detalle."""

    def datos(self, **cambios):
        return datos_de(self.variedad, **cambios)

    def test_regla_3_cns_el_formulario_muestra_todos_los_datos(self):
        """PROD-CNS-VAR regla 3: rangos, postcosecha, peso, ciclo guardado y semilla en el formulario de la variedad."""
        respuesta = self.client.get(self.url("variedad"))
        self.assertContains(respuesta, "Modificar variedad")
        self.assertContains(respuesta, 'value="Crespa"')
        self.assertContains(respuesta, "35 días")
        self.assertContains(respuesta, "Semilla Lechuga Crespa")
        self.assertContains(respuesta, "sin habilitar en ningún invernadero")

    def test_regla_8_el_resumen_muestra_los_valores_anteriores_y_el_nombre_nuevo_de_la_semilla(self):
        """PROD-MOD-VAR reglas 6 y 8: el resumen trae lo anterior y el nombre nuevo de la semilla."""
        resumen = self.enviar(self.url("variedad"), self.datos(nombre="Romana"), "revisar")
        self.assertContains(resumen, "antes Crespa")
        self.assertContains(resumen, "Semilla Lechuga Romana")
        self.assertContains(resumen, "se renombra a")

    def test_regla_7_el_resumen_avisa_a_quienes_se_notificara(self):
        """PROD-MOD-VAR regla 7: antes de confirmar dice a qué invernaderos se les avisará."""
        existencia(self.semilla(), self.norte)
        existencia(self.semilla(), self.sur)
        resumen = self.enviar(self.url("variedad"), self.datos(nombre="Romana"), "revisar")
        self.assertContains(resumen, "se notificarán a los Agrónomos de: Invernadero Sur")

    def test_regla_2_guardar_aplica_los_cambios_y_vuelve_a_cultivos(self):
        """PROD-MOD-VAR postcondiciones a, b y e: guarda, renombra la semilla y deja un registro."""
        respuesta = self.enviar(self.url("variedad"), self.datos(nombre="Romana"), "guardar")
        self.assertRedirects(respuesta, reverse("maestros:cultivos"))
        self.variedad.refresh_from_db()
        self.assertEqual(self.variedad.nombre_variedad, "Romana")
        self.assertEqual(self.semilla().nombre_insumo, "Semilla Lechuga Romana")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_variedad").count(), 1)

    def test_d28_guardar_sin_cambios_no_audita(self):
        """D-28: sin cambios no se escribe ni se audita; el resumen lo dice."""
        resumen = self.enviar(self.url("variedad"), self.datos(), "revisar")
        self.assertContains(resumen, "No cambiaste nada")
        self.enviar(self.url("variedad"), self.datos(), "guardar")
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_variedad").exists())

    def test_los_errores_del_servicio_vuelven_al_formulario_por_campo(self):
        """PROD-MOD-VAR regla 2: las reglas del alta valen igual; el error sale en su campo."""
        respuesta = self.enviar(self.url("variedad"), self.datos(duracion_post_cosecha="61"), "revisar")
        self.assertContains(respuesta, "Ingresá un entero entre 1 y 60.")

    def test_regla_5_la_advertencia_de_rangos_ofrece_volver_o_guardar_igual(self):
        """PROD-MOD-VAR regla 5: con lotes activos y una incompatibilidad, «Guardar» muestra «Revise antes de guardar»; «Guardar igual» confirma."""
        otra = variedad_con_semilla(self.cultivo, "Romana", temp_ambiente_min="10", temp_ambiente_max="12")
        uso = {self.variedad.pk: UsoDeVariedad(True, 1, 0, frozenset({self.norte.pk}))}
        with usos_de_variedad_de_prueba(uso), variedades_presentes_de_prueba({self.norte.pk: {self.variedad.pk, otra.pk}}):
            cambios = self.datos(temp_ambiente_min="19", temp_ambiente_max="20")
            aviso = self.enviar(self.url("variedad"), cambios, "guardar")
            self.assertContains(aviso, "Revise antes de guardar")
            self.assertContains(aviso, "Invernadero Norte")
            self.assertContains(aviso, "temperatura ambiente")
            self.assertContains(aviso, "Lechuga Romana")
            self.variedad.refresh_from_db()
            self.assertNotEqual(str(self.variedad.temp_ambiente_min), "19.00")
            self.enviar(self.url("variedad"), cambios, "guardar_igual")
        self.variedad.refresh_from_db()
        self.assertEqual(str(self.variedad.temp_ambiente_min), "19.00")

    def test_regla_3_con_lotes_las_etapas_se_ven_congeladas(self):
        """PROD-MOD-VAR regla 3: con lotes no se agregan ni quitan etapas: las casillas quedan deshabilitadas y se reenvían."""
        uso = {self.variedad.pk: UsoDeVariedad(True, 0, 0, frozenset())}
        with usos_de_variedad_de_prueba(uso):
            respuesta = self.client.get(self.url("variedad"))
            self.assertContains(respuesta, "ya tiene lotes")
            self.assertContains(respuesta, 'name="etapa_crecimiento" value="1" checked disabled')
            self.assertContains(respuesta, '<input type="hidden" name="etapa_crecimiento" value="1">')

    def test_regla_4_con_lotes_activos_el_perfil_se_ve_bloqueado(self):
        """PROD-MOD-VAR regla 4: con lotes activos el perfil no se cambia y lo dice."""
        uso = {self.variedad.pk: UsoDeVariedad(True, 2, 0, frozenset({self.norte.pk}))}
        with usos_de_variedad_de_prueba(uso):
            respuesta = self.client.get(self.url("variedad"))
            self.assertContains(respuesta, "No se cambia mientras tenga lotes activos")
            self.assertContains(respuesta, '<select name="perfil_familia"')
            self.assertRegex(respuesta.content.decode(), r'<select name="perfil_familia"[^>]* disabled')

    def test_d30_una_variedad_inactiva_se_ve_deshabilitada_con_su_motivo(self):
        """PROD-CNS-VAR regla 4 y D-30: la inactiva no se edita: campos deshabilitados, el motivo y sin «Revisar resumen»."""
        inactiva = variedad_con_semilla(self.cultivo, "Romana", activa=False)
        respuesta = self.client.get(self.url("variedad", inactiva))
        self.assertContains(respuesta, "Esta variedad está inactiva")
        self.assertNotContains(respuesta, "Revisar resumen")
        self.assertRegex(respuesta.content.decode(), r'<input type="text" name="nombre"[^>]* disabled')
        self.assertContains(respuesta, self.url("variedad_reactivar", inactiva))

    def test_d30_sin_permiso_el_formulario_se_ve_deshabilitado_con_quien_la_usa(self):
        """PROD-CNS-VAR regla 4: si solo la usa otro invernadero, se ve deshabilitada con «Solo la usa …»."""
        existencia(self.semilla(), self.sur)
        respuesta = self.client.get(self.url("variedad"))
        self.assertContains(respuesta, "Solo la usa Invernadero Sur (Beto Gómez).")
        self.assertNotContains(respuesta, "Revisar resumen")

    def test_enviar_un_cambio_sin_permiso_no_modifica_nada(self):
        """PROD-MOD-VAR regla 1: un POST de quien no la gestiona vuelve al formulario con un error y no cambia la variedad."""
        existencia(self.semilla(), self.sur)
        self.enviar(self.url("variedad"), self.datos(nombre="Romana"), "guardar")
        self.variedad.refresh_from_db()
        self.assertEqual(self.variedad.nombre_variedad, "Crespa")

    def test_el_detalle_de_otra_variedad_inexistente_da_404(self):
        """Una variedad que no existe da 404."""
        self.assertEqual(self.client.get(reverse("variedades:variedad", args=[999999])).status_code, 404)

    def test_el_formulario_escapa_el_nombre(self):
        """Seguridad: el nombre con HTML se escapa en el formulario."""
        rara = variedad_con_semilla(self.cultivo, '"><script>x</script>')
        respuesta = self.client.get(self.url("variedad", rara))
        self.assertNotContains(respuesta, "<script>x</script>")


class BajaYReactivacionTests(VistasDeVariedadesBase):
    """PROD-BAJ-VAR y la reactivación de PROD-MOD-VAR (regla 9)."""

    def test_flujo_principal_la_baja_pide_confirmar_y_deja_inactivas_variedad_y_semilla(self):
        """PROD-BAJ-VAR: abrir la página no cambia nada; confirmar da de baja la variedad y su semilla."""
        pagina = self.client.get(self.url("variedad_baja"))
        self.assertContains(pagina, "¿Dar de baja Lechuga Crespa?")
        self.variedad.refresh_from_db()
        self.assertTrue(self.variedad.activa)
        respuesta = self.client.post(self.url("variedad_baja"))
        self.assertRedirects(respuesta, reverse("maestros:cultivos"))
        self.variedad.refresh_from_db()
        self.assertFalse(self.variedad.activa)
        self.assertFalse(self.semilla().activo)

    def test_regla_3_la_baja_informa_donde_esta_habilitada_la_semilla_y_el_stock(self):
        """PROD-BAJ-VAR regla 3: informa los invernaderos donde está habilitada la semilla, sin bloquear."""
        existencia(self.semilla(), self.norte)
        self.assertContains(self.client.get(self.url("variedad_baja")), "habilitada en: Invernadero Norte")

    def test_regla_2_los_impedimentos_se_dicen_todos_y_no_se_ofrece_confirmar(self):
        """PROD-BAJ-VAR regla 2: con impedimentos (registrantes falsos) los lista todos con cómo resolverlos y no ofrece la baja."""
        impedimentos = {
            self.variedad.pk: [
                Impedimento("lotes_activos", "Tiene 2 lotes activos.", "Terminá con la cosecha o la merma."),
                Impedimento("ordenes_a_realizar", "Tiene 1 orden a realizar.", "Concretala o cancelala."),
            ]
        }
        with usos_de_variedad_de_prueba(impedimentos=impedimentos):
            pagina = self.client.get(self.url("variedad_baja"))
            self.assertContains(pagina, "No se puede dar de baja Lechuga Crespa")
            self.assertContains(pagina, "Tiene 2 lotes activos. Terminá con la cosecha o la merma.")
            self.assertContains(pagina, "Tiene 1 orden a realizar. Concretala o cancelala.")
            self.assertNotContains(pagina, ">Dar de baja</button>")
            self.client.post(self.url("variedad_baja"))
        self.variedad.refresh_from_db()
        self.assertTrue(self.variedad.activa)

    def test_d30_sin_permiso_la_baja_vuelve_a_cultivos_con_el_motivo(self):
        """PROD-BAJ-VAR precondición b y D-30: quien no la gestiona no ve la página de baja."""
        existencia(self.semilla(), self.sur)
        respuesta = self.client.get(self.url("variedad_baja"), follow=True)
        self.assertContains(respuesta, "Solo la usa Invernadero Sur")

    def test_la_baja_de_una_variedad_inactiva_vuelve_a_cultivos(self):
        """PROD-BAJ-VAR precondición c: una variedad inactiva no se vuelve a dar de baja."""
        inactiva = variedad_con_semilla(self.cultivo, "Romana", activa=False)
        respuesta = self.client.get(self.url("variedad_baja", inactiva), follow=True)
        self.assertRedirects(respuesta, reverse("maestros:cultivos"))

    def test_regla_9_reactivar_pide_confirmar_y_reactiva_variedad_y_semilla(self):
        """PROD-MOD-VAR regla 9: reactiva la variedad y su semilla con el cultivo activo."""
        inactiva = variedad_con_semilla(self.cultivo, "Romana", activa=False)
        self.assertContains(self.client.get(self.url("variedad_reactivar", inactiva)), "¿Reactivar Lechuga Romana?")
        respuesta = self.client.post(self.url("variedad_reactivar", inactiva))
        self.assertRedirects(respuesta, reverse("maestros:cultivos"))
        inactiva.refresh_from_db()
        self.assertTrue(inactiva.activa)
        self.assertTrue(self.semilla(inactiva).activo)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="reactivacion_variedad").count(), 1)

    def test_regla_9_con_el_cultivo_inactivo_no_se_reactiva(self):
        """PROD-MOD-VAR regla 9: «Primero reactivá el cultivo Lechuga.»"""
        inactiva = variedad_con_semilla(self.cultivo, "Romana", activa=False)
        self.cultivo.estado_cultivo = "inactivo"
        self.cultivo.save()
        respuesta = self.client.post(self.url("variedad_reactivar", inactiva), follow=True)
        self.assertContains(respuesta, "Primero reactivá el cultivo Lechuga.")
        inactiva.refresh_from_db()
        self.assertFalse(inactiva.activa)

    def test_reactivar_una_variedad_activa_vuelve_a_cultivos(self):
        """PROD-MOD-VAR: una variedad que ya está activa no se reactiva."""
        respuesta = self.client.get(self.url("variedad_reactivar"), follow=True)
        self.assertRedirects(respuesta, reverse("maestros:cultivos"))
