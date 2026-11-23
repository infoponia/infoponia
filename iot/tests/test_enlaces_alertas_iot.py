# Pruebas del enlace de cada alerta del IoT (IOT-04, paso 5; D-62 con su tercera enmienda; docs/casos_de_uso/iot/consultar_lecturas.md, «Enlaces de las alertas del IoT»;
# docs/api/alertas.md, sección 8). Se escribieron ANTES que el registrante (`.claude/rules/pruebas.md`).
#
# Servicio que se prueba (iot/servicios/alertas_iot.py): enlaces_de_alertas_iot(usuario, alertas) -> {id de alerta: Enlace(url, detalle)}, registrado en
# ``IotConfig.ready()`` con ``registrar_enlace_de_alerta(CODIGOS_DE_ALERTAS_IOT, ...)``. Las pruebas lo usan por la función de uso de `maestros`
# (``enlaces_de_alertas``), como la campana y el detalle de la alerta. Nunca un enlace a un 403: se sigue con el cliente de pruebas y se verifica 200.
# Los enlaces a «Monitoreo» solo se verifican por su ruta: la pantalla es del paso 7 (su 200 está en `test_monitoreo_vistas.py`).

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.alertas import CODIGOS_DE_ALERTAS_IOT
from iot.models import NodoCentral
from iot.tests import fabricas
from maestros.extensiones import Enlace, enlaces_registrados
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

alertas_iot = perezoso("iot.servicios.alertas_iot")

LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")
AHORA = datetime(2026, 11, 23, 12, 0, tzinfo=LOCAL)


class EnlacesAlertasIotTests(fabricas.ConCatalogoIot, TestCase):
    """Cada fila de la tabla de «Enlaces de las alertas del IoT», para el Agrónomo que opera y para el Gerente que solo consulta."""

    def setUp(self):
        cache.clear()
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.temp = fabricas.sensor(self.sistema, "norte/sectorA/temperatura")

    # ---- ayudas ----

    def aseguradas(self, tipo, clave, descripcion, **origen):
        return alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, tipo, clave, descripcion, **origen).alerta

    def enlaces(self, usuario, *alertas):
        """Los enlaces que arma la función de uso de `maestros`, con las alertas leídas como lo hace ``consultar_alertas`` (con su invernadero cargado)."""
        cargadas = list(Alerta.objects.filter(pk__in=[a.pk for a in alertas]).select_related("invernadero"))
        return api_alertas.enlaces_de_alertas(usuario, cargadas)

    def enlace(self, usuario, alerta):
        return self.enlaces(usuario, alerta)[alerta.pk]

    def ficha(self, equipo):
        return f"{reverse('iot:hardware_ficha', args=[equipo.pk])}?invernadero={self.norte.pk}"

    def monitoreo(self):
        return f"{reverse('iot:monitoreo')}?invernadero={self.norte.pk}"

    def sigue(self, usuario, url):
        """Entra con ``usuario``, sigue ``url`` y verifica 200 (ningún enlace lleva a un 403)."""
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(url).status_code, 200, url)

    def baja_de(self, identificador="norte/vieja"):
        """Un sensor dado de baja del sistema con ``identificador`` (el que el nodo sigue mandando)."""
        return fabricas.sensor(
            self.sistema, identificador, estado="inactivo", fecha_baja=date(2026, 11, 20), nombre_sensor=""
        )

    # ---- el registro ----

    def test_regla_enlaces_el_registrante_cubre_los_once_codigos_de_alerta_del_iot(self):
        """D-62 punto 2: `IotConfig.ready()` registra `enlaces_de_alertas_iot` para los códigos del IoT (uno solo, sin duplicar)."""
        registrados = [codigos for codigos, funcion in enlaces_registrados() if funcion is alertas_iot.enlaces_de_alertas_iot]
        self.assertEqual(registrados, [CODIGOS_DE_ALERTAS_IOT])
        self.assertEqual(len(CODIGOS_DE_ALERTAS_IOT), 11)

    # ---- con equipo o con lectura: la ficha del equipo ----

    def test_regla_enlaces_una_alerta_con_equipo_lleva_a_la_ficha_del_equipo_con_su_descripcion(self):
        """Tabla, fila 1: la alerta con origen en un equipo (R052) lleva a la ficha del equipo (`hardware/<id>/`, con `?invernadero=`) y su detalle es la descripción. Para el
        Agrónomo que opera y para el Gerente que solo consulta; los dos siguen el enlace y reciben 200."""
        alerta = self.aseguradas("iot_dispositivo_sin_actividad", f"hw:{self.temp.pk}", "norte/sectorA/temperatura · sin lecturas desde las 11:54 del 23/11", hardware=self.temp)
        for usuario in (self.laura, self.gerente):
            with self.subTest(usuario=usuario.email):
                self.assertEqual(self.enlace(usuario, alerta), Enlace(self.ficha(self.temp), alerta.descripcion_alerta))
                self.sigue(usuario, self.enlace(usuario, alerta).url)

    def test_regla_enlaces_una_alerta_con_lectura_lleva_a_la_ficha_del_sensor_de_la_lectura(self):
        """Tabla, fila 1: la alerta con origen en una lectura (R053) lleva a la ficha de SU SENSOR."""
        nivel = fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        alerta = self.aseguradas(
            "iot_nivel_solucion_bajo", f"sensor:{nivel.pk}", "norte/tanque1/nivel · informa «bajo»", telemetria=fabricas.telemetria(nivel)
        )
        for usuario in (self.laura, self.gerente):
            with self.subTest(usuario=usuario.email):
                self.assertEqual(self.enlace(usuario, alerta), Enlace(self.ficha(nivel), alerta.descripcion_alerta))
                self.sigue(usuario, self.enlace(usuario, alerta).url)

    # ---- nodo sin comunicación: el panel ----

    def test_regla_enlaces_nodo_sin_comunicacion_lleva_al_panel_del_invernadero(self):
        """Tabla, fila 2: «nodo sin comunicación» (sin hardware ni lectura) lleva a `iot:monitoreo` del invernadero y su detalle es la descripción."""
        alerta = self.aseguradas("iot_nodo_sin_comunicacion", f"nodo:{self.nodo.pk}", "Nodo de prueba · sin comunicación desde las 11:56 del 23/11")
        for usuario in (self.laura, self.gerente):
            with self.subTest(usuario=usuario.email):
                enlace = self.enlace(usuario, alerta)
                self.assertEqual(enlace, Enlace(self.monitoreo(), alerta.descripcion_alerta))
                self.assertEqual(resolve(enlace.url.split("?")[0]).url_name, "monitoreo")

    # ---- dispositivo no registrado ----

    def test_regla_enlaces_no_registrado_de_un_equipo_dado_de_baja_lleva_a_su_ficha_y_lo_dice(self):
        """Tabla, fila 3 («Reactivar», IOT-02): el identificador era de un equipo dado de baja del sistema: la ficha de ese equipo y el detalle «{identificador} era de {equipo},
        dado de baja el DD/MM». Para quien opera y para quien solo consulta (los dos pueden abrir la ficha)."""
        baja = self.baja_de("norte/vieja")
        alerta = self.aseguradas("iot_dispositivo_no_registrado", "id:norte/vieja", "El nodo envió una lectura de «norte/vieja» (24), que no está registrado.")
        for usuario in (self.laura, self.gerente):
            with self.subTest(usuario=usuario.email):
                self.assertEqual(self.enlace(usuario, alerta), Enlace(self.ficha(baja), "norte/vieja era de Temperatura, dado de baja el 20/11"))
                self.sigue(usuario, self.enlace(usuario, alerta).url)

    def test_regla_enlaces_no_registrado_de_otro_identificador_lleva_al_alta_a_quien_opera(self):
        """Tabla, fila 4: «dispositivo no registrado» de un identificador sin equipo dado de baja lleva, a quien opera, al alta con `?identificador=` (regla 12 de IOT-ALT-HDW);
        el detalle es la descripción. El Agrónomo sigue el enlace y recibe 200 (el formulario viene con el identificador)."""
        alerta = self.aseguradas("iot_dispositivo_no_registrado", "id:norte/nuevo", "El nodo envió una lectura de «norte/nuevo» (24), que no está registrado.")
        enlace = self.enlace(self.laura, alerta)
        self.assertEqual(enlace, Enlace(f"{reverse('iot:hardware_nuevo')}?invernadero={self.norte.pk}&identificador=norte%2Fnuevo", alerta.descripcion_alerta))
        self.client.force_login(self.laura)
        respuesta = self.client.get(enlace.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "norte/nuevo")

    def test_regla_enlaces_no_registrado_de_otro_identificador_lleva_al_panel_a_quien_solo_consulta(self):
        """Tabla, fila 4: a quien solo consulta (el Gerente de un invernadero con Agrónomo activo) no se le ofrece el alta (daría 403 al guardar): lo lleva a `iot:monitoreo`."""
        alerta = self.aseguradas("iot_dispositivo_no_registrado", "id:norte/nuevo", "El nodo envió una lectura de «norte/nuevo» (24), que no está registrado.")
        enlace = self.enlace(self.gerente, alerta)
        self.assertEqual(enlace, Enlace(self.monitoreo(), alerta.descripcion_alerta))

    def test_regla_enlaces_el_gerente_que_opera_un_invernadero_sin_agronomo_va_al_alta(self):
        """Regla «Alcance» (MD-98): el Gerente opera los invernaderos SIN Agrónomo activo; ahí el alta sí se le ofrece (y recibe 200)."""
        sur = crear_invernadero("Sur")
        sistema_sur = fabricas.sistema(sur)
        alerta = alertas_iot.asegurar_alerta_iot(sur.pk, sistema_sur, "iot_dispositivo_no_registrado", "id:sur/nuevo", "El nodo envió una lectura de «sur/nuevo» (24), que no está registrado.").alerta
        enlace = self.enlace(self.gerente, alerta)
        self.assertEqual(enlace.url, f"{reverse('iot:hardware_nuevo')}?invernadero={sur.pk}&identificador=sur%2Fnuevo")
        self.sigue(self.gerente, enlace.url)

    def test_regla_enlaces_un_identificador_en_uso_por_un_equipo_vigente_no_cuenta_como_dado_de_baja(self):
        """Regla 12 de IOT-ALT-HDW: si el identificador lo usa hoy un equipo NO dado de baja, no hay equipo «dado de baja» a reactivar: se trata como otro identificador (el
        alta; y el servicio de alta avisará del identificador en uso)."""
        self.baja_de("norte/repetido")
        fabricas.sensor(self.sistema, "norte/repetido", "humedad")
        alerta = self.aseguradas("iot_dispositivo_no_registrado", "id:norte/repetido", "El nodo envió una lectura de «norte/repetido» (24), que no está registrado.")
        self.assertIn(reverse("iot:hardware_nuevo"), self.enlace(self.laura, alerta).url)

    # ---- sin la alerta, y sin consultas por alerta ----

    def test_regla_enlaces_sin_alertas_devuelve_vacio_sin_consultar(self):
        """Prueba mínima de cada registrante (docs/api/alertas.md, sección 8): sin la alerta en la lista, `{}` sin consultar la base."""
        with CaptureQueriesContext(connection) as consultas:
            self.assertEqual(alertas_iot.enlaces_de_alertas_iot(self.laura, []), {})
            self.assertEqual(api_alertas.enlaces_de_alertas(self.laura, []), {})
        self.assertEqual(len(consultas), 0)

    def test_regla_enlaces_la_cantidad_de_consultas_no_depende_de_la_cantidad_de_alertas(self):
        """Prueba mínima de cada registrante: `assertNumQueries` igual con una y con tres alertas, de cada clase (con equipo, con lectura, nodo, no registrado)."""
        sensores = [fabricas.sensor(self.sistema, f"norte/s{i}") for i in range(3)]

        def consultas(alertas, usuario=self.laura):
            cargadas = list(Alerta.objects.filter(pk__in=[a.pk for a in alertas]).select_related("invernadero"))
            with CaptureQueriesContext(connection) as contexto:
                api_alertas.enlaces_de_alertas(usuario, cargadas)
            return len(contexto)

        con_equipo = [self.aseguradas("iot_dispositivo_sin_actividad", f"hw:{s.pk}", f"{s.identificador_equipo} · sin actividad", hardware=s) for s in sensores]
        con_lectura = [
            self.aseguradas("iot_fuera_de_umbral", f"sensor:{s.pk}", f"{s.identificador_equipo} · fuera", telemetria=fabricas.telemetria(s)) for s in sensores
        ]
        no_registradas = [self.aseguradas("iot_dispositivo_no_registrado", f"id:otro{i}", f"otro{i} no registrado") for i in range(3)]
        bajas = [self.baja_de(f"norte/baja{i}") for i in range(3)]
        de_baja = [self.aseguradas("iot_dispositivo_no_registrado", f"id:norte/baja{i}", f"baja{i} no registrado") for i in range(3)]
        for clase in (con_equipo, con_lectura, no_registradas, de_baja):
            with self.subTest(primera=clase[0].descripcion_alerta):
                self.assertEqual(consultas(clase[:1]), consultas(clase))
        self.assertEqual(len(bajas), 3)
