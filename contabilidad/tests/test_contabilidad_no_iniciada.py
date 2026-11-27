# Pruebas de la regla 9 de CON-INI-EJE, «Sin ejercicio no hay asiento» (docs/casos_de_uso/contabilidad/ejercicio.md; tarea CON-05).
# Paso 1: el servicio de asientos; paso 3 (más abajo): el middleware, las vistas, la campana y los pasos diarios. El asiento automático, el manual y el contraasiento sin ningún ejercicio lanzan `contabilidad_no_iniciada`
# antes de bloquear nada y no dejan rastro. Cada prueba arma sus propios datos.
import datetime
import importlib
from decimal import Decimal
from unittest import mock
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable, OrigenDocumento
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio_abierto, origen_de_prueba
from core import extensiones, procesos
from core.models import Agronomo, Capataz, Contador, Gerente, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

HOY = datetime.date(2027, 3, 10)
MOVIMIENTOS = [(cuentas.CAJA, DEBE, Decimal("100.00")), (cuentas.VENTAS, HABER, Decimal("100.00"))]


class SinEjercicioServiciosTests(PlanDeCuentasMixin, TestCase):
    """Regla 9 de CON-INI-EJE: sin ejercicio, ningún servicio de asientos registra nada."""

    def setUp(self):
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")

    def _no_queda_nada(self):
        self.assertFalse(EjercicioContable.objects.exists())
        self.assertFalse(AsientoContable.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion__in=["alta_ejercicio_contable", "alta_asiento_contable", "alta_movimiento_contable"]).exists())

    def test_regla_9_el_asiento_automatico_sin_ejercicio_lanza_contabilidad_no_iniciada(self):
        """Regla 9: `registrar_asiento_automatico` sin ejercicio lanza `contabilidad_no_iniciada`; no crea el ejercicio ni el asiento."""
        with self.assertRaises(ErrorContable) as contexto:
            asientos.registrar_asiento_automatico(self.contador, origen_de_prueba(), HOY, MOVIMIENTOS, hoy=HOY)

        self.assertEqual(contexto.exception.codigo, "contabilidad_no_iniciada")
        self.assertEqual(contexto.exception.mensaje, "La contabilidad no está iniciada.")
        self._no_queda_nada()

    def test_regla_9_el_asiento_automatico_de_importe_cero_tambien_se_rechaza(self):
        """Decisión del estudiante (26/11/2026): el chequeo va al principio; una operación de importe cero también se rechaza sin ejercicio."""
        ceros = [(cuentas.CAJA, DEBE, Decimal("0.00")), (cuentas.VENTAS, HABER, Decimal("0.00"))]

        with self.assertRaises(ErrorContable) as contexto:
            asientos.registrar_asiento_automatico(None, origen_de_prueba(), HOY, ceros, hoy=HOY)

        self.assertEqual(contexto.exception.codigo, "contabilidad_no_iniciada")

    def test_regla_9_el_asiento_manual_sin_ejercicio_lanza_contabilidad_no_iniciada(self):
        """Regla 9 y «Sin ejercicio» de CON-REG-ASI: `registrar_asiento_manual` sin ejercicio lanza `contabilidad_no_iniciada`."""
        with self.assertRaises(ErrorContable) as contexto:
            asientos.registrar_asiento_manual(self.contador, HOY, "Prueba", MOVIMIENTOS, hoy=HOY)

        self.assertEqual(contexto.exception.codigo, "contabilidad_no_iniciada")
        self._no_queda_nada()

    def test_regla_9_el_resumen_del_asiento_manual_sin_ejercicio_lanza_lo_mismo(self):
        """Regla 9: el paso 5 de CON-REG-ASI (`resumir_asiento_manual`) tampoco inventa un ejercicio por abrir."""
        with self.assertRaises(ErrorContable) as contexto:
            asientos.resumir_asiento_manual(self.contador, HOY, "Prueba", MOVIMIENTOS, hoy=HOY)

        self.assertEqual(contexto.exception.codigo, "contabilidad_no_iniciada")

    def test_regla_9_el_contraasiento_sin_ejercicio_lanza_contabilidad_no_iniciada(self):
        """Regla 9: `contraasentar` sin ejercicio lanza `contabilidad_no_iniciada` (el asiento a anular no puede existir sin ejercicio, así que se pasa un id cualquiera)."""
        with self.assertRaises(ErrorContable) as contexto:
            asientos.contraasentar(self.contador, 1, HOY, "Motivo", hoy=HOY)

        self.assertEqual(contexto.exception.codigo, "contabilidad_no_iniciada")
        self._no_queda_nada()

    def test_regla_9_con_ejercicio_un_asiento_inexistente_sigue_dando_404(self):
        """Regla 9 (contrapunto): el chequeo de contabilidad no iniciada no tapa el `Http404` de un asiento que no existe cuando sí hay ejercicio."""
        ejercicio_abierto(datetime.date(2027, 1, 1))

        with self.assertRaises(Http404):
            asientos.contraasentar(self.contador, 999999, HOY, "Motivo", hoy=HOY)

    def test_regla_9_con_un_ejercicio_los_servicios_funcionan_igual(self):
        """Regla 9 (contrapunto): con un ejercicio existente, el automático y el manual registran y `contabilidad_iniciada()` es verdadero."""
        ejercicio_abierto(datetime.date(2027, 1, 1))

        automatico = asientos.registrar_asiento_automatico(self.contador, origen_de_prueba(), HOY, MOVIMIENTOS, hoy=HOY)
        manual = asientos.registrar_asiento_manual(self.contador, HOY, "Prueba", MOVIMIENTOS, hoy=HOY)

        self.assertEqual((automatico.numero_asiento, manual.numero_asiento), (1, 2))
        self.assertTrue(ejercicios.contabilidad_iniciada())


# =====================================================================================================================================================================
# Paso 3 de CON-05: la ventana del middleware, las vistas que re-lanzan, la campana y los pasos diarios. Contrato que fijan estas pruebas (lo implementa el paso 3):
#   - `contabilidad.middleware.ContabilidadNoIniciadaMiddleware` (en `MIDDLEWARE`, después de `AuthenticationMiddleware` y de `MessageMiddleware`) con `process_exception`: SOLO
#     atiende `ErrorContable` con código `contabilidad_no_iniciada`; no tiene `process_request`, `process_view` ni lógica en `__call__` (por eso no puede bloquear el login, el logout, los
#     estáticos ni la pantalla de iniciar, ni armar un bucle de redirecciones: no redirige nunca).
#   - Responde con estado 200. Pedido HTMX (`HX-Request`): la plantilla `contabilidad/_ventana_contabilidad_no_iniciada.html` con `HX-Retarget: body` y `HX-Reswap: beforeend`.
#     Pedido común: la página `contabilidad/contabilidad_no_iniciada.html`, sin esos encabezados.
#   - Texto según quién: el responsable contable (`responsables.puede_registrar_asientos`), la ventana con «Iniciar ejercicio» y «Cerrar»; cualquier otro usuario con cuenta, el aviso
#     sin botón; sin usuario (pantallas de enlace), el mensaje genérico sin nombrar la contabilidad.
#   - El botón: en la ventana HTMX abre la pantalla en otra pestaña (`target="_blank" rel="noopener"`, decisión del estudiante, 26/11/2026); en la página común lleva
#     `?volver=<ruta del Referer>` solo si el Referer es del mismo sitio.
#   - `contabilidad.servicios.inicio.items_de_campana(usuario)`: la fuente de la campana, registrada en `ContabilidadConfig.ready()`.
#   - `contabilidad:iniciar` (`/contabilidad/ejercicios/iniciar/`): la ruta de la pantalla de inicio (el paso 4 la completa).
# =====================================================================================================================================================================

TEXTO_DEL_RESPONSABLE = "Lo que estás registrando genera un asiento contable y la contabilidad todavía no está iniciada. La operación no se registró."
TEXTO_DE_OTROS = "La contabilidad no está iniciada. Pedile al Contador o al Gerente que la inicie. La operación no se registró."
TEXTO_EXTERNO = "No pudimos registrar la operación. Probá de nuevo más tarde."
TEXTO_OTRA_PESTANA = "Se abre en otra pestaña. Cuando termines, volvé a esta y confirmá la operación de nuevo."
URLCONF_DE_PRUEBA = "contabilidad.tests.urls_de_prueba"


def _middleware():
    """El módulo del middleware, importado recién acá: así, mientras no exista, fallan estas pruebas y no el archivo entero."""
    return importlib.import_module("contabilidad.middleware")


class RegistroDelMiddlewareTests(TestCase):
    """El middleware está en `MIDDLEWARE` y en el lugar que pide el «Cómo se aplica»."""

    def test_regla_9_esta_en_middleware_despues_de_autenticacion_y_mensajes(self):
        """Cómo se aplica, regla 9: `ContabilidadNoIniciadaMiddleware` va en `MIDDLEWARE` después de los de sesión y autenticación (y de `MessageMiddleware`, que usa la ventana)."""
        ruta = "contabilidad.middleware.ContabilidadNoIniciadaMiddleware"
        self.assertIn(ruta, settings.MIDDLEWARE)
        self.assertGreater(settings.MIDDLEWARE.index(ruta), settings.MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware"))
        self.assertGreater(settings.MIDDLEWARE.index(ruta), settings.MIDDLEWARE.index("django.contrib.messages.middleware.MessageMiddleware"))

    def test_regla_9_solo_atiende_excepciones(self):
        """Regla 9: el middleware no mira ningún pedido (ni `process_request` ni `process_view`): solo `process_exception`. Por eso nunca redirige ni bloquea una pantalla."""
        clase = _middleware().ContabilidadNoIniciadaMiddleware
        self.assertFalse(hasattr(clase, "process_request"))
        self.assertFalse(hasattr(clase, "process_view"))
        self.assertTrue(callable(clase.process_exception))


@override_settings(ROOT_URLCONF=URLCONF_DE_PRUEBA)
class VentanaDeContabilidadNoIniciadaTests(PlanDeCuentasMixin, TestCase):
    """Regla 9 y extensión 1b de CON-INI-EJE: qué ve cada quien cuando una operación con asiento se intenta sin ejercicio. Sin ejercicio en toda la clase."""

    def setUp(self):
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com")
        self.iniciar = reverse("contabilidad:iniciar")

    def pedir(self, nombre="prueba_operacion", usuario=None, htmx=False, referer=None):
        if usuario is not None:
            self.client.force_login(usuario)
        extra = {}
        if htmx:
            extra["HTTP_HX_REQUEST"] = "true"
        if referer:
            extra["HTTP_REFERER"] = referer
        return self.client.get(reverse(nombre), **extra)

    # --- Quién ve qué (HTMX) ------------------------------------------------------------------------------------------------------------------------------------

    def test_ext_1b_htmx_el_contador_ve_la_ventana_con_el_boton_en_otra_pestana(self):
        """Extensión 1b y regla 9: pedido HTMX del Contador: 200, la ventana (no la página), los encabezados `HX-Retarget: body` y `HX-Reswap: beforeend`, el texto del responsable, «Iniciar
        ejercicio» que abre la pantalla de inicio en otra pestaña (`target="_blank" rel="noopener"`) con el aviso de esa pestaña, y «Cerrar»."""
        respuesta = self.pedir(usuario=self.contador, htmx=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual((respuesta["HX-Retarget"], respuesta["HX-Reswap"]), ("body", "beforeend"))
        self.assertTemplateUsed(respuesta, "contabilidad/_ventana_contabilidad_no_iniciada.html")
        self.assertNotContains(respuesta, "<html")  # es un fragmento que se agrega encima de la pantalla actual
        self.assertContains(respuesta, "data-ventana")
        self.assertContains(respuesta, TEXTO_DEL_RESPONSABLE)
        self.assertContains(respuesta, f'href="{self.iniciar}"')
        self.assertContains(respuesta, 'target="_blank"')
        self.assertContains(respuesta, 'rel="noopener"')
        self.assertContains(respuesta, TEXTO_OTRA_PESTANA)
        self.assertContains(respuesta, "Iniciar ejercicio")
        self.assertContains(respuesta, "Cerrar")
        self.assertNotContains(respuesta, "volver=")  # la operación sigue abierta en esta pestaña: no hace falta

    def test_ext_1a_htmx_el_gerente_sin_contador_activo_tambien_ve_el_boton(self):
        """Extensión 1a y regla 9: sin Contador activo, el Gerente (que sí puede iniciar) ve la ventana con el botón."""
        Contador.objects.update(is_active=False)

        respuesta = self.pedir(usuario=self.gerente, htmx=True)

        self.assertContains(respuesta, TEXTO_DEL_RESPONSABLE)
        self.assertContains(respuesta, f'href="{self.iniciar}"')

    def test_regla_9_htmx_el_gerente_con_un_contador_activo_ve_el_aviso_sin_boton(self):
        """Regla 9: con un Contador activo el Gerente no inicia: ve el aviso de «otro usuario» y solo «Cerrar», sin enlace a la pantalla de inicio."""
        respuesta = self.pedir(usuario=self.gerente, htmx=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, TEXTO_DE_OTROS)
        self.assertNotContains(respuesta, "Iniciar ejercicio")
        self.assertNotContains(respuesta, self.iniciar)
        self.assertNotContains(respuesta, TEXTO_OTRA_PESTANA)
        self.assertContains(respuesta, "Cerrar")

    def test_regla_9_los_demas_roles_ven_el_aviso_sin_boton_en_htmx_y_en_pagina(self):
        """Regla 9: el Vendedor, el Agrónomo y el Capataz (cualquier rol que no sea Contador ni Gerente) ven el aviso sin botón, con y sin HTMX; el 200 y los encabezados de HTMX siguen."""
        for clase, correo in ((Vendedor, "vendedor@infoponia.com"), (Agronomo, "agronomo@infoponia.com"), (Capataz, "capataz@infoponia.com")):
            cuenta = crear_cuenta(clase, email=correo)
            for htmx in (True, False):
                with self.subTest(rol=clase.__name__, htmx=htmx):
                    respuesta = self.pedir(usuario=cuenta, htmx=htmx)
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertContains(respuesta, TEXTO_DE_OTROS)
                    self.assertNotContains(respuesta, "Iniciar ejercicio")
                    self.assertNotContains(respuesta, self.iniciar)
                    self.assertContains(respuesta, "Cerrar")
                    self.assertEqual(respuesta.headers.get("HX-Retarget"), "body" if htmx else None)

    def test_regla_9_el_gerente_sin_contador_tambien_ve_el_boton_en_la_pagina_comun(self):
        """Regla 9 (pedido común): el Gerente que puede iniciar ve el botón en la página, no el aviso de otros."""
        Contador.objects.update(is_active=False)

        respuesta = self.pedir(usuario=self.gerente)

        self.assertContains(respuesta, TEXTO_DEL_RESPONSABLE)
        self.assertContains(respuesta, "Iniciar ejercicio")

    def test_regla_9_el_enlace_externo_ve_el_mensaje_generico_sin_mencionar_la_contabilidad(self):
        """Regla 9: un actor externo (proveedor, cliente o transportista, sin cuenta) ve «No pudimos registrar la operación…», sin botón y sin nombrar la contabilidad; con HTMX, con los encabezados."""
        for htmx in (True, False):
            with self.subTest(htmx=htmx):
                respuesta = self.pedir("prueba_enlace", htmx=htmx)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, TEXTO_EXTERNO)
                self.assertNotContains(respuesta, "ontabilidad")
                self.assertNotContains(respuesta, "Iniciar ejercicio")
                self.assertNotContains(respuesta, self.iniciar)
                if htmx:
                    self.assertEqual((respuesta["HX-Retarget"], respuesta["HX-Reswap"]), ("body", "beforeend"))
                else:
                    self.assertNotIn("HX-Retarget", respuesta.headers)

    # --- Página común y `volver` ---------------------------------------------------------------------------------------------------------------------------------

    def test_ext_1b_pagina_comun_el_responsable_ve_la_pagina_sin_encabezados_de_htmx(self):
        """Extensión 1b: pedido común: la página completa (no la ventana), sin `HX-Retarget` ni `HX-Reswap`, con el botón en la misma pestaña (sin `target`)."""
        respuesta = self.pedir(usuario=self.contador)

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "contabilidad/contabilidad_no_iniciada.html")
        self.assertNotIn("HX-Retarget", respuesta.headers)
        self.assertNotIn("HX-Reswap", respuesta.headers)
        self.assertContains(respuesta, "<html")
        self.assertContains(respuesta, TEXTO_DEL_RESPONSABLE)
        self.assertContains(respuesta, f'href="{self.iniciar}')
        self.assertNotContains(respuesta, 'target="_blank"')
        self.assertNotContains(respuesta, "volver=")  # sin Referer no hay a dónde volver

    def test_ext_1b_pagina_comun_el_referer_del_mismo_sitio_va_como_volver(self):
        """Extensión 1b, paso 4 y cómo se aplica: el `Referer` del mismo sitio (ruta y consulta) viaja como `?volver=` para ofrecer «Volver a la operación» al terminar."""
        referer = "http://testserver/compras/pagos/orden/3/proveedor/4/?medio=efectivo"

        respuesta = self.pedir(usuario=self.contador, referer=referer)

        esperado = quote("/compras/pagos/orden/3/proveedor/4/?medio=efectivo", safe="")
        self.assertContains(respuesta, f"{self.iniciar}?volver={esperado}")

    def test_ext_1b_pagina_comun_un_referer_de_otro_sitio_se_descarta(self):
        """Seguridad (redirección abierta): un `Referer` de otro host, o que no es una URL, no viaja como `volver`."""
        for referer in ("http://otro-sitio.example/compras/", "https://testserver.evil.example/x", "javascript:alert(1)", "//otro-sitio.example/x"):
            with self.subTest(referer=referer):
                respuesta = self.pedir(usuario=self.contador, referer=referer)
                self.assertContains(respuesta, TEXTO_DEL_RESPONSABLE)
                self.assertNotContains(respuesta, "volver=")

    # --- La operación no queda registrada --------------------------------------------------------------------------------------------------------------------

    def test_regla_9_la_operacion_no_queda_registrada_en_ninguna_variante(self):
        """Regla 9 y garantías mínimas: lo que la operación había creado antes de pedir el asiento se deshace (el origen de prueba), para cada quien y con o sin HTMX; no se crea ejercicio."""
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        for usuario, nombre in ((self.contador, "prueba_operacion"), (vendedor, "prueba_operacion"), (None, "prueba_enlace")):
            for htmx in (True, False):
                with self.subTest(usuario=usuario, htmx=htmx):
                    self.pedir(nombre, usuario=usuario, htmx=htmx)
                    self.assertFalse(OrigenDocumento.objects.exists())
                    self.assertFalse(EjercicioContable.objects.exists())
                    self.assertFalse(AsientoContable.objects.exists())

    def test_regla_9_con_ejercicio_la_misma_operacion_se_registra(self):
        """Contrapunto: con un ejercicio que contiene la fecha, la misma vista registra y el middleware no interviene."""
        ejercicio_abierto(datetime.date(2027, 1, 1))
        self.client.force_login(self.contador)

        respuesta = self.client.get(reverse("prueba_operacion"))

        self.assertEqual((respuesta.status_code, respuesta.content), (200, b"registrada"))
        self.assertEqual(AsientoContable.objects.count(), 1)

    # --- Solo atiende ese código --------------------------------------------------------------------------------------------------------------------------------

    def test_regla_9_otro_error_contable_o_cualquier_excepcion_pasan_de_largo(self):
        """El middleware devuelve `None` (no atiende) ante un `ErrorContable` de otro código o cualquier otra excepción; la vista que lanza otro `ErrorContable` termina en un 500 sin la ventana."""
        middleware = _middleware().ContabilidadNoIniciadaMiddleware(lambda request: HttpResponse("x"))
        request = RequestFactory().get("/_prueba/")
        request.user = self.contador
        for excepcion in (ErrorContable("asiento_desbalanceado", "x"), ValueError("x"), Http404("x"), PermissionDenied("x")):
            with self.subTest(excepcion=type(excepcion).__name__):
                self.assertIsNone(middleware.process_exception(request, excepcion))

        self.client.raise_request_exception = False
        self.client.force_login(self.contador)
        respuesta = self.client.get(reverse("prueba_otro_error"))
        self.assertEqual(respuesta.status_code, 500)
        self.assertNotContains(respuesta, TEXTO_DEL_RESPONSABLE, status_code=500)

    # --- No bloquea nada: sin bucle de redirección ---------------------------------------------------------------------------------------------------------

    def test_regla_9_no_interviene_en_un_pedido_sin_excepcion_ni_consulta_la_base(self):
        """El middleware no toca el login, el logout, los estáticos ni la pantalla de iniciar: devuelve tal cual la respuesta de la vista y no hace ninguna consulta."""
        middleware = _middleware().ContabilidadNoIniciadaMiddleware(lambda request: HttpResponse("la respuesta de la vista"))
        rutas = ("/static/core/css/infoponia.css", reverse("core:iniciar_sesion"), reverse("core:cerrar_sesion"), self.iniciar, reverse("core:inicio"))
        for ruta in rutas:
            with self.subTest(ruta=ruta), self.assertNumQueries(0):
                request = RequestFactory().get(ruta)
                request.user = self.contador
                respuesta = middleware(request)
                self.assertEqual((respuesta.status_code, respuesta.content), (200, b"la respuesta de la vista"))

    def test_regla_9_sin_ejercicio_el_login_el_logout_y_una_vista_normal_andan(self):
        """Sin ejercicio: la pantalla de iniciar sesión abre (200), cerrar sesión redirige al login (302, una sola vez) y una pantalla normal responde 200: nada se bloquea."""
        self.assertEqual(self.client.get(reverse("core:iniciar_sesion")).status_code, 200)
        self.client.force_login(self.contador)
        self.assertEqual(self.client.get(reverse("prueba_ok")).content, b"ok")
        cierre = self.client.post(reverse("core:cerrar_sesion"))
        self.assertEqual(cierre.status_code, 302)
        self.assertNotIn(self.iniciar, cierre.url)

    def test_regla_9_la_pantalla_de_iniciar_abre_sin_ejercicio_y_sin_redireccion(self):
        """Sin ejercicio, la pantalla de iniciar responde 200 al responsable, con y sin HTMX y sin ninguna redirección (no hay bucle); no recibe los encabezados de la ventana."""
        self.client.force_login(self.contador)
        for htmx in (False, True):
            with self.subTest(htmx=htmx):
                extra = {"HTTP_HX_REQUEST": "true"} if htmx else {}
                respuesta = self.client.get(self.iniciar, follow=True, **extra)
                self.assertEqual(respuesta.redirect_chain, [])
                self.assertEqual(respuesta.status_code, 200)
                self.assertNotIn("HX-Retarget", respuesta.headers)

    def test_regla_1_la_pantalla_de_iniciar_es_solo_del_responsable(self):
        """Regla 1: la pantalla de iniciar da 403 al Gerente con Contador activo y al Vendedor (no hay botón que lleve ahí, D-30), y pide sesión a quien no la tiene."""
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(self.iniciar).status_code, 403)
        self.client.force_login(crear_cuenta(Vendedor, email="vendedor@infoponia.com"))
        self.assertEqual(self.client.get(self.iniciar).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.iniciar).status_code, 302)


class VistasQueRelanzanTests(PlanDeCuentasMixin, TestCase):
    """Cómo se aplica: las vistas que atrapaban `ErrorContable` de forma general tienen que volver a lanzar `contabilidad_no_iniciada` para que lo atienda el middleware."""

    def setUp(self):
        cache.clear()
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.client.force_login(self.contador)

    def test_regla_9_el_asiento_manual_sin_ejercicio_muestra_la_ventana_y_no_el_formulario_con_error(self):
        """CON-REG-ASI: con «Revisar» y con «Confirmar» sin ejercicio, la vista no muestra el error en el formulario: responde la ventana del middleware."""
        datos = {
            "fecha": "2027-03-10",
            "descripcion": "Prueba",
            "fila": ["0", "1"],
            "cuenta_0": cuentas.CAJA, "tipo_0": DEBE, "importe_0": "10,00",
            "cuenta_1": cuentas.VENTAS, "tipo_1": HABER, "importe_1": "10,00",
        }
        for accion in ("revisar", "confirmar"):
            with self.subTest(accion=accion):
                respuesta = self.client.post(reverse("contabilidad:asiento_nuevo"), {**datos, "accion": accion})
                self.assertEqual(respuesta.status_code, 200)
                self.assertTemplateUsed(respuesta, "contabilidad/contabilidad_no_iniciada.html")
                self.assertContains(respuesta, TEXTO_DEL_RESPONSABLE)

    def test_regla_9_el_asiento_manual_sin_fecha_valida_tambien_muestra_la_ventana(self):
        """CON-REG-ASI: aun con una fecha inválida (la vista valida igual los demás campos), sin ejercicio manda la ventana en lugar de marcar campos."""
        respuesta = self.client.post(reverse("contabilidad:asiento_nuevo"), {"accion": "revisar", "fecha": "no-es-una-fecha"})

        self.assertTemplateUsed(respuesta, "contabilidad/contabilidad_no_iniciada.html")

    def test_regla_9_el_pago_a_proveedor_sin_ejercicio_muestra_la_ventana(self):
        """CMP-REG-PAG (`compras/views_pagos.py`): el pago que pide su asiento sin ejercicio no vuelve al formulario con el error: responde la ventana del middleware. El servicio se reemplaza
        por uno que lanza el error, porque armar una orden pagable no es de esta prueba."""
        error = ErrorContable("contabilidad_no_iniciada", "La contabilidad no está iniciada.")
        with mock.patch("compras.views_pagos.api.detalle_del_pago"), mock.patch("compras.views_pagos.api.registrar_pago", side_effect=error):
            respuesta = self.client.post(
                reverse("compras:pago_nuevo", args=[1, 1]), {"accion": "confirmar", "medio_pago": "efectivo", "fecha": "2027-03-10"}
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "contabilidad/contabilidad_no_iniciada.html")
        self.assertContains(respuesta, TEXTO_DEL_RESPONSABLE)

    def test_regla_9_el_resumen_del_pago_sin_ejercicio_muestra_la_ventana(self):
        """CMP-REG-PAG, paso 6: `resumir_pago` (que arma el asiento previsto) también re-lanza el error."""
        error = ErrorContable("contabilidad_no_iniciada", "La contabilidad no está iniciada.")
        with mock.patch("compras.views_pagos.api.detalle_del_pago"), mock.patch("compras.views_pagos.api.resumir_pago", side_effect=error):
            respuesta = self.client.post(
                reverse("compras:pago_nuevo", args=[1, 1]), {"accion": "revisar", "medio_pago": "efectivo", "fecha": "2027-03-10"}
            )

        self.assertTemplateUsed(respuesta, "contabilidad/contabilidad_no_iniciada.html")


class AlertaDeLaCampanaTests(PlanDeCuentasMixin, TestCase):
    """Regla 10 de CON-INI-EJE: «Falta iniciar la contabilidad» en la campana del responsable contable."""

    def setUp(self):
        cache.clear()
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com")

    def items(self, usuario):
        return importlib.import_module("contabilidad.servicios.inicio").items_de_campana(usuario)

    def test_regla_10_la_fuente_esta_registrada_para_la_campana(self):
        """Regla 10 y cómo se aplica: `ready()` registra la fuente con `registrar_fuente_de_alertas`; `alertas_para` la incluye."""
        self.assertIn(importlib.import_module("contabilidad.servicios.inicio").items_de_campana, extensiones._FUENTES_DE_ALERTAS)
        self.assertIn("Falta iniciar la contabilidad", [item.titulo for item in extensiones.alertas_para(self.contador)])

    def test_regla_10_el_contador_ve_la_advertencia_con_el_acceso_a_la_pantalla(self):
        """Regla 10: una `ItemDeAlerta` de severidad «advertencia», con el título, el detalle de la tarea, la URL de la pantalla de inicio y sin leer (no es una alerta guardada)."""
        self.assertEqual(
            self.items(self.contador),
            [
                extensiones.ItemDeAlerta(
                    "advertencia",
                    "Falta iniciar la contabilidad",
                    "Iniciá el primer ejercicio y cargá el capital inicial antes de registrar operaciones que generan asientos.",
                    reverse("contabilidad:iniciar"),
                    False,
                )
            ],
        )

    def test_regla_10_el_gerente_la_ve_solo_si_no_hay_contador_activo(self):
        """Regla 10: la ve el Gerente solo cuando no hay Contador activo (es quien inicia en ese caso)."""
        self.assertEqual(self.items(self.gerente), [])
        Contador.objects.update(is_active=False)
        self.assertEqual([item.titulo for item in self.items(self.gerente)], ["Falta iniciar la contabilidad"])

    def test_regla_10_los_demas_roles_y_quien_no_tiene_cuenta_no_la_ven_y_no_consultan(self):
        """Regla 10: el Vendedor, el Agrónomo y `None` no ven nada, y se resuelve por el rol sin ninguna consulta (la campana corre en cada pantalla)."""
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")
        for usuario in (vendedor, agronomo, None):
            with self.subTest(usuario=usuario), self.assertNumQueries(0):
                self.assertEqual(self.items(usuario), [])

    def test_regla_10_una_cuenta_dada_de_baja_no_la_ve(self):
        """Regla 10 y D-30: una instancia cargada antes de la baja no recibe la alerta (se compara contra la base)."""
        Contador.objects.filter(pk=self.contador.pk).update(is_active=False)
        self.assertEqual(self.items(self.contador), [])

    def test_regla_10_desaparece_cuando_la_contabilidad_esta_iniciada(self):
        """Postcondición e de CON-INI-EJE: con cualquier ejercicio (abierto, en cierre o cerrado) la alerta desaparece, y la consulta es un `exists()` liviano."""
        ejercicio_abierto(datetime.date(2027, 1, 1))

        with self.assertNumQueries(1):
            self.assertEqual(self.items(self.contador), [])

    def test_regla_10_es_una_consulta_liviana_que_no_crea_alertas_en_la_base(self):
        """Regla 10: no crea filas de `Alerta`: el ítem se calcula en cada consulta."""
        from maestros.models import Alerta

        self.items(self.contador)
        self.items(self.contador)

        self.assertFalse(Alerta.objects.exists())


class PasosDiariosSinEjercicioTests(PlanDeCuentasMixin, TestCase):
    """Regla 9 de CON-INI-EJE: los pasos diarios con asientos (el 20 y el 33) no procesan nada, informan el motivo y reintentan al día siguiente. Los realistas, con sus fixtures de
    cámara y de suministros, están en `comercial/tests/test_pasos_diarios_sin_contabilidad.py`; acá, el contrato del paso y que ninguno falle."""

    HOY = datetime.date(2027, 3, 10)
    TEXTO = "contabilidad no iniciada: queda pendiente para mañana"

    def paso(self, codigo):
        return next(p for p in procesos.pasos_diarios() if p.codigo == codigo)

    def test_regla_9_los_pasos_20_y_33_dicen_contabilidad_no_iniciada_y_no_leen_nada(self):
        """Regla 9: sin ejercicio, `vencer_partidas_en_camara` (20) y `resolver_suministros` (33) devuelven `ResumenDePaso(0, 0, 0, «contabilidad no iniciada: queda pendiente para mañana»)` sin
        buscar candidatos ni avisar; el reintento es el día siguiente (los pasos son idempotentes)."""
        objetivos = {
            "vencer_partidas_en_camara": ("comercial.servicios.camara._vencer_partida", "comercial.servicios.camara._avisar_por_vencer"),
            "resolver_suministros": ("comercial.servicios.resoluciones.resolver_suministro", "comercial.servicios.resoluciones._candidatos"),
        }
        for codigo, rutas in objetivos.items():
            with self.subTest(paso=codigo):
                with mock.patch(rutas[0]) as primero, mock.patch(rutas[1]) as segundo:
                    resumen = self.paso(codigo).funcion(self.HOY)
                self.assertEqual(tuple(resumen), (0, 0, 0, self.TEXTO))
                primero.assert_not_called()
                segundo.assert_not_called()
        self.assertFalse(AsientoContable.objects.exists())

    def test_regla_9_con_ejercicio_los_pasos_20_y_33_corren_normalmente(self):
        """Contrapunto: con un ejercicio, la guarda no actúa (sin partidas ni suministros no hay nada que hacer, pero el detalle no es el de «no iniciada»)."""
        ejercicio_abierto(datetime.date(2027, 1, 1))
        for codigo in ("vencer_partidas_en_camara", "resolver_suministros"):
            with self.subTest(paso=codigo):
                self.assertNotEqual(self.paso(codigo).funcion(self.HOY).detalle, self.TEXTO)

    def test_regla_9_todo_el_proceso_diario_sin_ejercicio_termina_sin_errores_ni_asientos(self):
        """Regla 9 y D-56 punto 5: el proceso diario completo sin ejercicio no tiene ningún paso con error, no crea ejercicio ni asientos; el paso 5 informa «contabilidad no iniciada»."""
        resultados = procesos.correr_proceso_diario(hoy=self.HOY)

        self.assertEqual([(paso.codigo, error) for paso, _, error in resultados if error is not None], [])
        self.assertEqual(next(r for p, r, _ in resultados if p.codigo == "abrir_ejercicio").detalle, "contabilidad no iniciada")
        self.assertFalse(EjercicioContable.objects.exists())
        self.assertFalse(AsientoContable.objects.exists())
