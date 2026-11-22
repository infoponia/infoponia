# Pruebas de las pantallas del Hardware (IOT-02, paso 6; docs/casos_de_uso/iot/hardware.md, «Cómo se aplica» y «Pantallas»; D-29, D-30): la lista con sus filtros y la ficha
# (IOT-CNS-HDW), el formulario de alta y de modificación con sus avisos (IOT-ALT-HDW, IOT-MOD-HDW) y las ventanas de volver a activar y reactivar. Integración con el cliente de
# prueba de Django: permisos y alcance (otros roles 403, fuera del alcance 404, el Gerente con Agrónomo activo en solo lectura, ningún botón lleva a un 403), el flujo con HTMX
# y sin él, y los errores por campo. Las reglas de negocio las prueban ``test_iot_alt_hdw.py``, ``test_iot_mod_hdw.py`` y ``test_iot_cns_hdw.py``.

import re

from django.test import TestCase
from django.urls import reverse

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from iot.models import Actuador, Hardware, Sensor
from iot.tests import fabricas
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_sector, crear_tecnico, crear_vendedor


class HardwareVistasBase(fabricas.ConCatalogoIot, TestCase):
    """Laura es la Agrónoma de Norte (con sistema, un sector y un insumo de hardware); Libre no tiene Agrónomo (lo opera el Gerente)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=crear_tecnico("t@infoponia.com"))
        self.libre = crear_invernadero("Libre")
        self.sistema = fabricas.sistema(self.norte)
        self.sector = crear_sector(self.norte, "Sector A")
        self.tipo = fabricas.tipo_actuador("Extractor")
        self.insumo = fabricas.insumo_de_hardware("DHT22 de repuesto")

    def url(self, nombre, *args, invernadero=None, **consulta):
        ruta = reverse(f"iot:{nombre}", args=args)
        if invernadero is not None:
            consulta = {"invernadero": invernadero.pk} | consulta
        return ruta + ("?" + "&".join(f"{k}={v}" for k, v in consulta.items()) if consulta else "")

    def post_del_sensor(self, **cambios):
        """Lo que manda el formulario de registrar un sensor (con el invernadero Norte)."""
        datos = {
            "clase": "sensor",
            "variable": "temperatura",
            "identificador": "norte/sectorA/temperatura",
            "modelo": "DHT22",
            "numero_serie": "",
            "nombre_sensor": "",
            "calibracion_min": "0",
            "calibracion_max": "50",
            "fecha_instalacion": "2026-10-01",
            "insumo": self.insumo.pk,
            "sector": self.sector.pk,
        }
        return datos | cambios

    def post_del_actuador(self, **cambios):
        datos = {
            "clase": "actuador",
            "tipo_actuador": self.tipo.pk,
            "identificador": "norte/sectorA/ventilador",
            "modelo": "Relé",
            "numero_serie": "",
            "descripcion": "",
            "fecha_instalacion": "2026-10-01",
            "insumo": self.insumo.pk,
            "sector": "",
        }
        return datos | cambios


class AccesoAHardwareVistaTests(HardwareVistasBase):
    """SEG-13 y D-30."""

    def rutas(self):
        sensor = fabricas.sensor(self.sistema, "norte/uno")
        return [
            self.url("hardware"),
            self.url("hardware_nuevo"),
            self.url("hardware_avisos"),
            self.url("hardware_ficha", sensor.pk),
            self.url("hardware_modificar", sensor.pk),
            self.url("hardware_volver_a_activar", sensor.pk),
            self.url("hardware_reactivar", sensor.pk),
        ]

    def test_pre_a_los_demas_roles_reciben_403_con_get_y_con_post(self):
        """IOT-ALT/MOD/CNS-HDW precondición a: Capataz, Vendedor, Técnico y Administrador, 403 en cada ruta."""
        rutas = self.rutas()
        for cuenta in (crear_capataz(), crear_vendedor(), crear_tecnico("otro@infoponia.com"), crear_administrador()):
            self.client.force_login(cuenta)
            for ruta in rutas:
                for metodo in (self.client.get, self.client.post):
                    with self.subTest(cuenta=cuenta.email, ruta=ruta, metodo=metodo.__name__):
                        self.assertEqual(metodo(ruta).status_code, 403)

    def test_un_equipo_o_un_invernadero_fuera_del_alcance_da_404(self):
        """IOT-CNS-HDW regla 1 (D-28): el Agrónomo de otro invernadero no ve la ficha ni los formularios del equipo, y la lista de un invernadero ajeno da 404."""
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo("otra@infoponia.com"))
        equipo = fabricas.sensor(fabricas.sistema(ajeno), "ajeno/1")
        self.client.force_login(self.laura)
        self.assertEqual(self.client.get(self.url("hardware", invernadero=ajeno)).status_code, 404)
        for nombre in ("hardware_ficha", "hardware_modificar", "hardware_volver_a_activar", "hardware_reactivar"):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.get(self.url(nombre, equipo.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url("hardware_ficha", 999999)).status_code, 404)

    def test_la_lista_y_la_ficha_solo_aceptan_get(self):
        """SEG-14: consultar no cambia nada."""
        sensor = fabricas.sensor(self.sistema, "norte/uno")
        self.client.force_login(self.laura)
        self.assertEqual(self.client.post(self.url("hardware")).status_code, 405)
        self.assertEqual(self.client.post(self.url("hardware_ficha", sensor.pk)).status_code, 405)


class IotCnsHdwVistaTests(HardwareVistasBase):
    """La pestaña «Hardware»: el nodo, los filtros, la tabla y la ficha."""

    def setUp(self):
        super().setUp()
        self.temperatura = fabricas.sensor(self.sistema, "norte/b/temperatura", sector=self.sector)
        self.humedad = fabricas.sensor(self.sistema, "norte/a/humedad", variable="humedad", nombre_sensor="Del fondo")
        self.ventilador = fabricas.actuador(self.sistema, self.tipo, "norte/ventilador")
        self.client.force_login(self.laura)

    def test_flujo_principal_la_lista_muestra_el_nodo_y_los_equipos_en_orden(self):
        """IOT-CNS-HDW reglas 2 y 3: el nodo (estado, conectividad, modo) y los equipos, sensores y después actuadores, por identificador."""
        respuesta = self.client.get(self.url("hardware"))
        self.assertContains(respuesta, "Nodo de prueba")
        self.assertContains(respuesta, "Sin señal")
        html = respuesta.content.decode()
        orden = [html.index(i) for i in ("norte/a/humedad", "norte/b/temperatura", "norte/ventilador")]
        self.assertEqual(orden, sorted(orden))
        self.assertContains(respuesta, "Sin confirmar")
        self.assertContains(respuesta, "General")

    def test_sin_sistema_dice_que_hay_que_registrarlo_antes(self):
        """«Cómo se aplica»: sin sistema IoT, la pestaña lo avisa con el enlace a «Sistema IoT»."""
        self.sistema.estado_sistema = "inactivo"
        self.sistema.save()
        respuesta = self.client.get(self.url("hardware", invernadero=self.norte))
        self.assertContains(respuesta, "Este invernadero no tiene Sistema IoT")

    def test_regla_5_los_filtros_se_aplican_con_get(self):
        """IOT-CNS-HDW regla 5: tipo, estado, sector y búsqueda (formulario GET: funciona sin JavaScript)."""
        self.assertNotContains(self.client.get(self.url("hardware", tipo="actuador")), "norte/a/humedad")
        self.assertContains(self.client.get(self.url("hardware", tipo="actuador")), "norte/ventilador")
        self.assertContains(self.client.get(self.url("hardware", q="fondo")), "norte/a/humedad")
        self.assertNotContains(self.client.get(self.url("hardware", q="fondo")), "norte/b/temperatura")
        self.assertContains(self.client.get(self.url("hardware", sector=self.sector.pk)), "norte/b/temperatura")
        self.assertNotContains(self.client.get(self.url("hardware", sector=self.sector.pk)), "norte/a/humedad")
        self.assertContains(self.client.get(self.url("hardware", q="zzz")), "Ningún equipo coincide con los filtros.")

    def test_con_htmx_los_filtros_reemplazan_solo_la_tabla(self):
        """docs/patrones/abm.md, sección 7: con ``HX-Request`` la respuesta es solo la tabla (sin la página entera)."""
        respuesta = self.client.get(self.url("hardware", q="fondo"), headers={"HX-Request": "true"})
        self.assertNotContains(respuesta, "<html")
        self.assertContains(respuesta, "norte/a/humedad")
        self.assertNotContains(respuesta, "Nodo de prueba")

    def test_el_agronomo_ve_registrar_hardware_y_el_gerente_con_agronomo_activo_no(self):
        """D-30: solo quien opera el IoT del invernadero ve «Registrar hardware»; el Gerente en solo lectura ve el aviso y ningún botón de escritura."""
        self.assertContains(self.client.get(self.url("hardware")), "Registrar hardware")
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.url("hardware", invernadero=self.norte))
        self.assertNotContains(respuesta, "Registrar hardware")
        self.assertContains(respuesta, "Norte tiene Agrónomo activo")

    def test_regla_14_avisa_de_los_identificadores_anunciados_que_faltan_registrar(self):
        """IOT-ALT-HDW regla 14: el nodo anunció equipos que todavía no están registrados: la lista los nombra (solo a quien opera)."""
        fabricas.equipo_anunciado(self.sistema, "norte/nuevo", clase="sensor")
        self.assertContains(self.client.get(self.url("hardware")), "norte/nuevo")
        self.client.force_login(self.gerente)
        self.assertNotContains(self.client.get(self.url("hardware", invernadero=self.norte)), "norte/nuevo")

    def test_la_ficha_muestra_los_datos_de_un_sensor(self):
        """IOT-CNS-HDW regla 6: identificador, tipo, sector, situación, modelo, instalación, insumo y calibración; «Última lectura» «—» hasta IOT-03."""
        respuesta = self.client.get(self.url("hardware_ficha", self.temperatura.pk))
        for texto in ("norte/b/temperatura", "Sensor · Temperatura", "Sector A", "Sin confirmar", "DHT22", "-10,00 a 60,00 °C", "Última lectura"):
            self.assertContains(respuesta, texto)

    def test_la_ficha_muestra_los_datos_de_un_actuador(self):
        """IOT-CNS-HDW regla 6: tipo, compatibilidad, estado informado «Desconocido» y tiempo mínimo."""
        respuesta = self.client.get(self.url("hardware_ficha", self.ventilador.pk))
        for texto in ("Actuador · Extractor", "Sin verificar", "Desconocido", "60 s"):
            self.assertContains(respuesta, texto)

    def test_la_ficha_muestra_las_alertas_activas_del_equipo(self):
        """IOT-CNS-HDW regla 6: sus alertas activas."""
        from iot.models import AlertaIot

        alerta = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_en_falla", f"hw:{self.ventilador.pk}", "Falla del ventilador")
        AlertaIot.objects.create(alerta=alerta, sistema=self.sistema, hardware=self.ventilador)
        self.assertContains(self.client.get(self.url("hardware_ficha", self.ventilador.pk)), "Falla del ventilador")

    def test_los_botones_de_la_ficha_dependen_del_estado_y_de_quien_mira(self):
        """D-30: activo, «Modificar»; fuera de servicio, también «Volver a activar»; dado de baja, solo «Reactivar»; el Gerente con Agrónomo activo, ninguno."""
        fuera = fabricas.sensor(self.sistema, "norte/fuera", estado="fuera_de_servicio")
        baja = fabricas.sensor(self.sistema, "norte/baja", estado="inactivo")
        ficha = lambda equipo: self.client.get(self.url("hardware_ficha", equipo.pk))  # noqa: E731
        self.assertContains(ficha(self.temperatura), "Modificar")
        self.assertNotContains(ficha(self.temperatura), "Volver a activar")
        self.assertContains(ficha(fuera), "Volver a activar")
        self.assertContains(ficha(baja), "Reactivar")
        self.assertNotContains(ficha(baja), "Modificar")
        self.client.force_login(self.gerente)
        for equipo in (self.temperatura, fuera, baja):
            for boton in ("Modificar", "Volver a activar", "Reactivar"):
                self.assertNotContains(ficha(equipo), boton)

    def test_ningun_enlace_de_la_lista_ni_de_la_ficha_lleva_a_un_403(self):
        """D-30: cada enlace de las dos pantallas, para cada actor que las ve, se puede abrir (nunca 403)."""
        fuera = fabricas.sensor(self.sistema, "norte/fuera", estado="fuera_de_servicio")
        baja = fabricas.sensor(self.sistema, "norte/baja", estado="inactivo")
        for cuenta in (self.laura, self.gerente):
            self.client.force_login(cuenta)
            paginas = [self.url("hardware", invernadero=self.norte)] + [self.url("hardware_ficha", e.pk) for e in (self.temperatura, self.ventilador, fuera, baja)]
            for pagina in paginas:
                html = self.client.get(pagina).content.decode()
                for ruta in set(re.findall(r'href="(/iot/[^"#]*)"', html)):
                    with self.subTest(cuenta=cuenta.email, pagina=pagina, ruta=ruta):
                        self.assertNotEqual(self.client.get(ruta.replace("&amp;", "&")).status_code, 403)

    def test_la_consulta_no_audita(self):
        """IOT-CNS-HDW regla 8 (SEG-14)."""
        self.client.get(self.url("hardware"))
        self.client.get(self.url("hardware_ficha", self.temperatura.pk))
        self.assertFalse(RegistroAuditoria.objects.exists())


class IotAltHdwVistaTests(HardwareVistasBase):
    """IOT-ALT-HDW: el formulario de alta."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.laura)
        self.nuevo = self.url("hardware_nuevo", invernadero=self.norte)

    def test_el_formulario_arranca_pidiendo_el_tipo_de_equipo(self):
        """IOT-ALT-HDW: primero se elige sensor o actuador; los demás datos aparecen según la elección."""
        respuesta = self.client.get(self.nuevo)
        self.assertContains(respuesta, "Tipo de equipo")
        self.assertNotContains(respuesta, "Variable que mide")
        self.assertContains(respuesta, "Fecha de instalación")

    def test_refrescar_dibuja_los_campos_del_sensor_sin_guardar(self):
        """«Cómo se aplica»: el cambio del tipo de equipo vuelve a dibujar el formulario SIN guardar (sin JavaScript, ``refrescar``)."""
        respuesta = self.client.post(self.nuevo, {"clase": "sensor", "refrescar": "1"})
        self.assertContains(respuesta, "Variable que mide")
        self.assertContains(respuesta, "El fotoperíodo no es un sensor: InfoPonia lo calcula con los sensores de intensidad lumínica.")
        self.assertNotContains(respuesta, "Tipo de actuador")
        self.assertFalse(Hardware.objects.filter(clase="sensor").exists())

    def test_refrescar_dibuja_los_campos_del_actuador_con_el_texto_para_el_agronomo(self):
        """IOT-ALT-HDW regla 7: para el Agrónomo, «Si falta el tipo que necesitás, pedíselo al Gerente: los tipos son comunes a toda la organización.»."""
        respuesta = self.client.post(self.nuevo, {"clase": "actuador", "refrescar": "1"})
        self.assertContains(respuesta, "Si falta el tipo que necesitás, pedíselo al Gerente: los tipos son comunes a toda la organización.")
        self.assertContains(respuesta, "Extractor")

    def test_con_htmx_el_formulario_se_reemplaza_por_su_propia_pagina_completa(self):
        """El cambio con HTMX manda ``refrescar`` y ``hx-select`` toma ``#formulario`` de la respuesta: la respuesta lleva ese bloque."""
        respuesta = self.client.post(self.nuevo, {"clase": "sensor", "refrescar": "1"}, headers={"HX-Request": "true"})
        self.assertContains(respuesta, 'id="formulario"')

    def test_calibracion_aparece_al_elegir_una_variable_que_la_tiene_y_no_con_el_nivel(self):
        """IOT-ALT-HDW regla 5: la calibración con su unidad (°C); el nivel de la solución no la lleva."""
        con = self.client.post(self.nuevo, {"clase": "sensor", "variable": "temperatura", "refrescar": "1"})
        self.assertContains(con, "Calibración: mínimo (°C)")
        sin = self.client.post(self.nuevo, {"clase": "sensor", "variable": "nivel_solucion", "refrescar": "1"})
        self.assertNotContains(sin, "Calibración: mínimo")

    def test_flujo_principal_registra_un_sensor_y_va_a_su_ficha(self):
        """IOT-ALT-HDW y «Verificación a mano» 5: un sensor de temperatura en un sector, con calibración 0 a 50; vuelve a la ficha con un aviso."""
        respuesta = self.client.post(self.nuevo, self.post_del_sensor(), follow=True)
        sensor = Sensor.objects.get()
        self.assertRedirects(respuesta, self.url("hardware_ficha", sensor.pk))
        self.assertContains(respuesta, "registrado correctamente")
        self.assertEqual((sensor.identificador_equipo, sensor.sector, sensor.sistema), ("norte/sectorA/temperatura", self.sector, self.sistema))

    def test_el_identificador_repetido_da_error_en_el_campo_y_conserva_lo_escrito(self):
        """IOT-ALT-HDW regla 2 y «Verificación a mano» 5: ``NORTE/sectorA/temperatura`` repetido: «Ya lo usa… en este sistema IoT.» en el identificador, con lo escrito."""
        fabricas.sensor(self.sistema, "norte/sectorA/temperatura")
        respuesta = self.client.post(self.nuevo, self.post_del_sensor(identificador="NORTE/sectorA/temperatura", modelo="Mi modelo"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ya lo usa Temperatura en este sistema IoT.")
        self.assertContains(respuesta, 'value="Mi modelo"')
        self.assertEqual(Sensor.objects.count(), 1)

    def test_un_actuador_queda_sin_verificar_y_se_registra(self):
        """IOT-ALT-HDW regla 14 y «Verificación a mano» 5: sin anuncio, el actuador queda «sin verificar»."""
        respuesta = self.client.post(self.nuevo, self.post_del_actuador(), follow=True)
        self.assertEqual(Actuador.objects.get().compatibilidad, "sin_verificar")
        self.assertContains(respuesta, "Sin verificar")

    def test_un_actuador_incompatible_se_registra_y_lo_avisa(self):
        """IOT-ALT-HDW regla 14: una incompatibilidad se advierte y no impide el alta."""
        fabricas.equipo_anunciado(self.sistema, "norte/sectorA/ventilador", ("ENCENDER",))
        respuesta = self.client.post(self.nuevo, self.post_del_actuador(), follow=True)
        self.assertEqual(Actuador.objects.get().compatibilidad, "incompatible")
        self.assertContains(respuesta, "configuración incompatible")

    def test_un_sensor_en_un_sector_fuera_de_servicio_avisa_que_no_generara_alertas(self):
        """«Cómo se aplica», «Sector»: «El {sector} está fuera de servicio: este sensor no generará alertas ni activará reglas.»"""
        fuera = crear_sector(self.norte, "Sector B", estado="fuera_de_servicio")
        respuesta = self.client.post(self.nuevo, self.post_del_sensor(sector=fuera.pk), follow=True)
        self.assertContains(respuesta, "Sector B está fuera de servicio: este sensor no generará alertas ni activará reglas.")

    def test_regla_12_desde_una_alerta_carga_el_identificador_con_su_texto(self):
        """IOT-ALT-HDW regla 12: ``?identificador=`` carga el campo con «Tomado de la alerta «Dispositivo no registrado».»."""
        respuesta = self.client.get(self.url("hardware_nuevo", invernadero=self.norte, identificador="norte/sin/registrar"))
        self.assertContains(respuesta, 'value="norte/sin/registrar"')
        self.assertContains(respuesta, "Tomado de la alerta «Dispositivo no registrado».")

    def test_regla_12_si_el_identificador_era_de_un_equipo_dado_de_baja_ofrece_reactivarlo(self):
        """IOT-ALT-HDW regla 12: lo advierte y ofrece «Reactivar {equipo}» (conserva su historial) además de seguir con el alta."""
        viejo = fabricas.sensor(self.sistema, "norte/viejo", estado="inactivo")
        respuesta = self.client.get(self.url("hardware_nuevo", invernadero=self.norte, identificador="norte/viejo"))
        self.assertContains(respuesta, "Este identificador era de")
        self.assertContains(respuesta, self.url("hardware_reactivar", viejo.pk))

    def test_regla_14_el_campo_ofrece_los_identificadores_anunciados_sin_registrar(self):
        """IOT-ALT-HDW regla 14: ``datalist`` con los anunciados que todavía no están registrados, marcando los de un equipo dado de baja."""
        fabricas.sensor(self.sistema, "norte/ya", estado="inactivo")
        fabricas.equipo_anunciado(self.sistema, "norte/ya", clase="sensor")
        fabricas.equipo_anunciado(self.sistema, "norte/libre", clase="sensor")
        respuesta = self.client.get(self.nuevo)
        self.assertContains(respuesta, '<datalist id="anunciados">')
        self.assertContains(respuesta, 'value="norte/libre"')
        self.assertContains(respuesta, 'label="Era de norte/ya, dado de baja"')

    def test_el_fragmento_de_avisos_dice_si_el_nodo_soporta_las_acciones_del_tipo(self):
        """IOT-ALT-HDW regla 14 (HTMX): al cambiar el identificador, el fragmento dice «Compatible», la lista de las acciones que faltan o «sin verificar»."""
        ruta = self.url("hardware_avisos", invernadero=self.norte)
        consulta = {"clase": "actuador", "tipo_actuador": self.tipo.pk, "identificador": "norte/sectorA/ventilador"}
        self.assertContains(self.client.get(ruta, consulta), "sin verificar")
        anuncio = fabricas.equipo_anunciado(self.sistema, "norte/sectorA/ventilador", ("ENCENDER",))
        self.assertContains(self.client.get(ruta, consulta), "Apagar")
        anuncio.comandos.add(fabricas.comando_del_catalogo("APAGAR"))
        self.assertContains(self.client.get(ruta, consulta), "Compatible: el nodo soporta todas las acciones del tipo.")

    def test_el_gerente_con_agronomo_activo_no_registra_y_vuelve_a_la_lista_sin_403(self):
        """D-30: solo consulta: aunque llegue por la URL, vuelve a la lista con un aviso (nunca un 403 ni un alta)."""
        self.client.force_login(self.gerente)
        for metodo, datos in ((self.client.get, None), (self.client.post, self.post_del_sensor())):
            respuesta = metodo(self.nuevo, datos, follow=True) if datos else metodo(self.nuevo, follow=True)
            self.assertContains(respuesta, "Solo consultás el IoT de este invernadero")
        self.assertFalse(Sensor.objects.exists())

    def test_el_gerente_sin_agronomo_registra(self):
        """«Verificación a mano» 8: en el invernadero sin Agrónomo, el Gerente puede registrar."""
        fabricas.sistema(self.libre)
        self.client.force_login(self.gerente)
        respuesta = self.client.post(self.url("hardware_nuevo", invernadero=self.libre), self.post_del_sensor(sector=""), follow=True)
        self.assertEqual(Sensor.objects.get().sistema.invernadero, self.libre)
        self.assertContains(respuesta, "registrado correctamente")

    def test_sin_sistema_vuelve_a_sistema_iot_con_un_aviso(self):
        """«Cómo se aplica»: sin sistema no se cargan equipos."""
        sin = crear_invernadero("Sin sistema", agronomo=self.laura)
        respuesta = self.client.get(self.url("hardware_nuevo", invernadero=sin), follow=True)
        self.assertContains(respuesta, "no tiene Sistema IoT")


class IotModHdwVistaTests(HardwareVistasBase):
    """IOT-MOD-HDW: modificar, volver a activar y reactivar."""

    def setUp(self):
        super().setUp()
        self.sensor = fabricas.sensor(self.sistema, "norte/sensor", sector=self.sector)
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/actuador")
        self.client.force_login(self.laura)

    def modificar(self, equipo):
        return self.url("hardware_modificar", equipo.pk)

    def test_el_formulario_de_modificar_trae_los_datos_y_no_pide_fecha_ni_insumo(self):
        """IOT-MOD-HDW regla 2: modelo, serie, sector, nombre y calibración; el tipo de equipo, la fecha y el insumo no se editan."""
        respuesta = self.client.get(self.modificar(self.sensor))
        self.assertContains(respuesta, 'value="DHT22"')
        self.assertContains(respuesta, "Guardar cambios")
        self.assertNotContains(respuesta, "Fecha de instalación")
        self.assertNotContains(respuesta, 'name="insumo"')
        self.assertNotContains(respuesta, 'name="clase"')

    def test_regla_3_la_variable_con_lecturas_se_muestra_deshabilitada_con_su_motivo(self):
        """IOT-MOD-HDW regla 3: el sensor con lecturas no cambia de variable: el campo va deshabilitado con la explicación."""
        fabricas.telemetria(self.sensor)
        respuesta = self.client.get(self.modificar(self.sensor))
        self.assertContains(respuesta, "No se puede cambiar: el sensor ya tiene lecturas.")
        self.assertContains(respuesta, '<input type="hidden" name="variable" value="temperatura">')

    def test_regla_3_el_tipo_con_comandos_se_muestra_deshabilitado_y_el_sin_historial_se_puede_cambiar(self):
        """IOT-MOD-HDW regla 3: el tipo del actuador se cambia solo sin comandos ni reglas; la ficha del prototipo da los dos textos."""
        self.assertContains(self.client.get(self.modificar(self.actuador)), "Se puede cambiar porque todavía no tiene comandos ni reglas.")
        fabricas.comando(self.actuador, self.tipo.acciones.first(), "ejecutado")
        self.assertContains(self.client.get(self.modificar(self.actuador)), "No se puede cambiar: ya tiene comandos o reglas de actuación.")

    def test_regla_4_el_identificador_de_un_equipo_que_reporto_no_se_corrige(self):
        """IOT-MOD-HDW regla 4: «Ya reportó: identifica su historial y no se puede corregir.»"""
        fabricas.telemetria(self.sensor)
        self.assertContains(self.client.get(self.modificar(self.sensor)), "Ya reportó: identifica su historial y no se puede corregir.")

    def test_modificar_guarda_avisa_y_vuelve_a_la_ficha(self):
        """IOT-MOD-HDW regla 2 y «Verificación a mano» 6: cambia la variable (sin lecturas) y el sector; vuelve a la ficha con un aviso."""
        otro_sector = crear_sector(self.norte, "Sector B")
        datos = self.post_del_sensor(variable="humedad", identificador="norte/sensor", sector=otro_sector.pk, calibracion_max="100")
        respuesta = self.client.post(self.modificar(self.sensor), datos, follow=True)
        self.assertRedirects(respuesta, self.url("hardware_ficha", self.sensor.pk))
        self.assertContains(respuesta, "modificado correctamente")
        self.sensor.refresh_from_db()
        self.assertEqual((self.sensor.tipo_variable_sensor, self.sensor.sector), ("humedad", otro_sector))

    def test_modificar_con_errores_los_muestra_por_campo(self):
        """IOT-MOD-HDW regla 2: errores por campo, con lo escrito."""
        respuesta = self.client.post(self.modificar(self.sensor), self.post_del_sensor(identificador="norte/sensor", modelo="", calibracion_min="90"))
        self.assertContains(respuesta, "Ingresá el modelo.")
        self.assertContains(respuesta, "El mínimo tiene que ser menor que el máximo.")

    def test_un_equipo_dado_de_baja_no_se_modifica_y_vuelve_a_la_ficha(self):
        """IOT-MOD-HDW regla 9: solo se reactiva."""
        baja = fabricas.sensor(self.sistema, "norte/baja", estado="inactivo")
        respuesta = self.client.get(self.modificar(baja), follow=True)
        self.assertRedirects(respuesta, self.url("hardware_ficha", baja.pk))
        self.assertContains(respuesta, "no se puede modificar")

    def test_el_gerente_con_agronomo_activo_no_modifica_y_vuelve_a_la_ficha_sin_403(self):
        """D-30: solo consulta."""
        self.client.force_login(self.gerente)
        respuesta = self.client.post(self.modificar(self.sensor), self.post_del_sensor(identificador="norte/sensor", modelo="Otro"), follow=True)
        self.assertRedirects(respuesta, self.url("hardware_ficha", self.sensor.pk))
        self.sensor.refresh_from_db()
        self.assertEqual(self.sensor.modelo_hardware, "DHT22")

    # ---- volver a activar ----

    def fuera_de_servicio(self):
        self.sensor.estado_hardware = "fuera_de_servicio"
        self.sensor.save()
        return self.url("hardware_volver_a_activar", self.sensor.pk)

    def test_la_ventana_de_volver_a_activar_no_cambia_nada_al_abrirse(self):
        """IOT-MOD-HDW regla 7: abrir la ventana (GET) no cambia nada; con HTMX es un fragmento y sin JavaScript, la ficha con la ventana."""
        ruta = self.fuera_de_servicio()
        con = self.client.get(ruta, headers={"HX-Request": "true"})
        self.assertNotContains(con, "<html")
        self.assertContains(con, "El equipo vuelve a estar activo y puede recibir comandos.")
        sin = self.client.get(ruta)
        self.assertContains(sin, "<html")
        self.assertContains(sin, "norte/sensor")
        self.sensor.refresh_from_db()
        self.assertEqual(self.sensor.estado_hardware, "fuera_de_servicio")

    def test_volver_a_activar_pasa_el_equipo_a_activo_y_resuelve_sus_alertas(self):
        """IOT-MOD-HDW postcondición b: el equipo vuelve a «activo»; la alerta de falla pasa a «resuelta»."""
        ruta = self.fuera_de_servicio()
        alerta = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_en_falla", f"hw:{self.sensor.pk}")
        respuesta = self.client.post(ruta, follow=True)
        self.assertRedirects(respuesta, self.url("hardware_ficha", self.sensor.pk))
        self.assertContains(respuesta, "volvió a estar activo")
        self.sensor.refresh_from_db()
        alerta.refresh_from_db()
        self.assertEqual((self.sensor.estado_hardware, alerta.estado_alerta), ("activo", "resuelta"))

    def test_volver_a_activar_un_equipo_activo_vuelve_a_la_ficha_sin_403(self):
        """D-30: ninguna acción que no corresponde se ofrece ni lleva a un 403."""
        respuesta = self.client.get(self.url("hardware_volver_a_activar", self.sensor.pk), follow=True)
        self.assertRedirects(respuesta, self.url("hardware_ficha", self.sensor.pk))

    # ---- reactivar ----

    def dar_de_baja(self, equipo):
        equipo.estado_hardware = "inactivo"
        equipo.save()
        return self.url("hardware_reactivar", equipo.pk)

    def test_la_ventana_de_reactivar_ofrece_confirmar(self):
        """IOT-MOD-HDW postcondición c: «El equipo vuelve a estar activo con su historial.»"""
        ruta = self.dar_de_baja(self.sensor)
        self.assertContains(self.client.get(ruta, headers={"HX-Request": "true"}), "El equipo vuelve a estar activo con su historial.")

    def test_la_ventana_de_reactivar_un_actuador_avisa_si_queda_incompatible(self):
        """IOT-MOD-HDW regla 10: informa el resultado antes de guardar; una incompatibilidad se advierte y no impide reactivar."""
        fabricas.equipo_anunciado(self.sistema, "norte/actuador", ("ENCENDER",))
        ruta = self.dar_de_baja(self.actuador)
        respuesta = self.client.get(ruta, headers={"HX-Request": "true"})
        self.assertContains(respuesta, "El nodo no anunció el comando de")
        self.assertContains(respuesta, "Apagar")

    def test_la_ventana_de_reactivar_dice_que_no_se_puede_si_otro_equipo_usa_el_identificador(self):
        """IOT-MOD-HDW regla 9: «No se puede reactivar: el identificador X ya lo usa {equipo} (registrado como reemplazo).»; no ofrece confirmar."""
        ruta = self.dar_de_baja(self.sensor)
        fabricas.sensor(self.sistema, "NORTE/sensor")
        respuesta = self.client.get(ruta, headers={"HX-Request": "true"})
        self.assertContains(respuesta, "No se puede reactivar: el identificador norte/sensor ya lo usa Temperatura (registrado como reemplazo).")
        self.assertNotContains(respuesta, 'type="submit"')
        self.client.post(ruta)
        self.sensor.refresh_from_db()
        self.assertEqual(self.sensor.estado_hardware, "inactivo")

    def test_reactivar_pasa_el_equipo_a_activo_con_su_historial(self):
        """IOT-MOD-HDW postcondición c y «Verificación a mano»: reactivar deja el equipo activo y vuelve a su ficha con un aviso."""
        lectura = fabricas.telemetria(self.sensor)
        ruta = self.dar_de_baja(self.sensor)
        respuesta = self.client.post(ruta, follow=True)
        self.assertRedirects(respuesta, self.url("hardware_ficha", self.sensor.pk))
        self.assertContains(respuesta, "se reactivó con su historial")
        self.sensor.refresh_from_db()
        self.assertEqual((self.sensor.estado_hardware, list(self.sensor.telemetrias.all())), ("activo", [lectura]))
