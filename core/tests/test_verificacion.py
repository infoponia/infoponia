# Pruebas de `core/verificacion.py` y del comando `cargar_datos_de_verificacion` (CLAUDE.md, «Datos para la verificación a mano»):
# la guarda de «solo la base local», el registro de cargadores y que el comando no imprime la contraseña ni toca al Administrador.

from contextlib import contextmanager
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings

from core import verificacion
from core.models import Usuario

def _host(valor):
    """Parcha el host de la base conectada (``connection.settings_dict``), que es lo que mira la guarda."""
    return mock.patch.dict(connection.settings_dict, {"HOST": valor})


@contextmanager
def _sin_render(host="localhost"):
    """Un entorno sin ninguna variable de Render (el de la máquina de quien corre las pruebas puede tenerlas) y con la base en ``host``."""
    with mock.patch.dict("os.environ", {}, clear=True), _host(host):
        yield


class GuardaDeBaseLocalTests(SimpleTestCase):
    """`exigir_base_local`: CLAUDE.md pide negarse con DEBUG apagado, con una base que no es localhost y con variables de Render."""

    @override_settings(DEBUG=True)
    def test_d_verificacion_local_con_debug_encendido_pasa(self):
        """CLAUDE.md, «Datos para la verificación a mano»: DEBUG encendido, localhost y sin Render no se niega."""
        with _sin_render():
            verificacion.exigir_base_local()

    @override_settings(DEBUG=False)
    def test_d_verificacion_se_niega_con_debug_apagado(self):
        """CLAUDE.md: se niega si DEBUG está apagado."""
        with _sin_render(), self.assertRaisesMessage(verificacion.BaseNoLocal, "DEBUG está apagado"):
            verificacion.exigir_base_local()

    @override_settings(DEBUG=True)
    def test_d_verificacion_se_niega_con_una_base_que_no_es_localhost(self):
        """CLAUDE.md: se niega si la base no es localhost, y el mensaje no trae el host (puede ser parte de una cadena de conexión)."""
        with _sin_render("ep-algo.neon.tech"), self.assertRaises(verificacion.BaseNoLocal) as contexto:
            verificacion.exigir_base_local()
        self.assertNotIn("neon", str(contexto.exception))

    @override_settings(DEBUG=True)
    def test_d_verificacion_se_niega_con_variables_de_render(self):
        """CLAUDE.md: se niega si hay variables de Render, con `RENDER`, con el prefijo `RENDER_` o con `IS_PULL_REQUEST`."""
        for variable in ("RENDER", "RENDER_SERVICE_ID", "IS_PULL_REQUEST"):
            with self.subTest(variable=variable), mock.patch.dict("os.environ", {variable: "true"}, clear=True), _host("localhost"):
                with self.assertRaisesMessage(verificacion.BaseNoLocal, variable):
                    verificacion.exigir_base_local()

    @override_settings(DEBUG=True)
    def test_d_verificacion_se_niega_sin_host(self):
        """Una base sin HOST (por ejemplo, la que sale de DATABASE_URL sin host) no se toma por local."""
        with _sin_render(""), self.assertRaises(verificacion.BaseNoLocal):
            verificacion.exigir_base_local()


class RegistroDeCargadoresTests(SimpleTestCase):
    """`registrar_cargador`, `cargadores` y `cargar_datos`, con el mismo contrato que el proceso diario (D-56)."""

    def test_d56_el_registro_es_idempotente_y_ordena(self):
        """Un registro idéntico no se duplica y `cargadores()` sale por orden."""
        with mock.patch.object(verificacion, "_CARGADORES", []):
            funcion = lambda contrasena: verificacion.ResumenDeCarga()  # noqa: E731
            verificacion.registrar_cargador("b", "B", 20, funcion)
            verificacion.registrar_cargador("a", "A", 10, funcion)
            verificacion.registrar_cargador("a", "A", 10, funcion)
            self.assertEqual([c.codigo for c in verificacion.cargadores()], ["a", "b"])

    def test_d56_un_codigo_o_un_orden_repetido_se_rechazan(self):
        """Dos cargadores distintos no comparten código ni orden."""
        with mock.patch.object(verificacion, "_CARGADORES", []):
            verificacion.registrar_cargador("a", "A", 10, len)
            with self.assertRaises(RuntimeError):
                verificacion.registrar_cargador("a", "Otro", 10, len)
            with self.assertRaises(RuntimeError):
                verificacion.registrar_cargador("c", "C", 10, len)

    @override_settings(DEBUG=True)
    def test_d56_un_cargador_que_falla_no_frena_a_los_demas(self):
        """Si un cargador falla, se informa y el siguiente corre."""

        def roto(contrasena):
            raise ValueError("falló")

        with _sin_render(), mock.patch.object(verificacion, "_CARGADORES", []):
            verificacion.registrar_cargador("a", "A", 10, roto)
            verificacion.registrar_cargador("b", "B", 20, lambda contrasena: verificacion.ResumenDeCarga(creado=("ok",)))
            resultados = verificacion.cargar_datos("clave")
        self.assertIsInstance(resultados[0][2], ValueError)
        self.assertEqual(resultados[1][1].creado, ("ok",))

    @override_settings(DEBUG=True)
    def test_d56_un_cargador_inexistente_da_value_error(self):
        """`solo` con un código que no existe lista los válidos."""
        with _sin_render(), mock.patch.object(verificacion, "_CARGADORES", []):
            with self.assertRaisesMessage(ValueError, "No hay un cargador"):
                verificacion.cargar_datos("clave", solo="nada")


class ComandoCargarDatosTests(TestCase):
    """El comando: se niega fuera de la base local, no imprime la contraseña y no toca al Administrador."""

    def _correr(self, contrasena=None, *argumentos):
        """Corre el comando con la contraseña en la variable de entorno (la única forma no interactiva: nunca es un argumento)."""
        salida, errores = StringIO(), StringIO()
        entorno = {"INFOPONIA_CONTRASENA_DE_PRUEBA": contrasena} if contrasena else {}
        with mock.patch.dict("os.environ", entorno):
            call_command("cargar_datos_de_verificacion", *argumentos, stdout=salida, stderr=errores)
        return salida.getvalue(), errores.getvalue()

    @override_settings(DEBUG=False)
    def test_d_verificacion_el_comando_se_niega_con_debug_apagado(self):
        """CLAUDE.md: el comando falla con un `CommandError` claro si la guarda se niega."""
        with _sin_render(), self.assertRaisesMessage(CommandError, "DEBUG está apagado"):
            self._correr("secreta")

    @override_settings(DEBUG=True)
    def test_d_verificacion_sin_contrasena_el_comando_pide_la_contrasena(self):
        """Sin `--contrasena` ni variable de entorno, el comando lo dice."""
        with _sin_render(), mock.patch("sys.stdin", StringIO()), self.assertRaisesMessage(CommandError, "Falta la contraseña"):
            self._correr()

    @override_settings(DEBUG=True)
    def test_d_verificacion_la_contrasena_no_es_un_argumento(self):
        """La contraseña no viaja como argumento (quedaría en el historial y en la lista de procesos): `--contrasena` ya no existe."""
        with _sin_render(), self.assertRaises(CommandError):
            call_command("cargar_datos_de_verificacion", "--contrasena", "secreta")

    @override_settings(DEBUG=True)
    def test_d_verificacion_en_una_terminal_pide_la_contrasena_sin_mostrarla(self):
        """Con terminal y sin variable de entorno, la pide con `getpass` (no se ve al escribirla) y no la imprime."""
        recibida = []

        def cargador(contrasena):
            recibida.append(contrasena)
            return verificacion.ResumenDeCarga(creado=("algo",))

        terminal = mock.Mock()
        terminal.isatty.return_value = True
        with _sin_render(), mock.patch.object(verificacion, "_CARGADORES", []), mock.patch("sys.stdin", terminal):
            verificacion.registrar_cargador("x", "Cargador X", 10, cargador)
            with mock.patch("getpass.getpass", return_value="escrita-a-mano") as pedir:
                salida, errores = self._correr()
        pedir.assert_called_once()
        self.assertEqual(recibida, ["escrita-a-mano"])
        self.assertNotIn("escrita-a-mano", salida + errores)

    @override_settings(DEBUG=True)
    def test_d_verificacion_en_una_base_que_no_es_local_no_pide_la_contrasena(self):
        """La guarda va ANTES de pedir nada: en una base que no es local ni se pregunta (no se tipea una contraseña para nada)."""
        with _sin_render("ep-algo.neon.tech"), mock.patch("getpass.getpass") as pedir, self.assertRaisesMessage(CommandError, "no es local"):
            self._correr()
        pedir.assert_not_called()

    @override_settings(DEBUG=True)
    def test_d_verificacion_no_imprime_la_contrasena_y_no_toca_al_administrador(self):
        """Ni la salida ni el error traen la contraseña, y las cuentas del Administrador quedan igual (contraseña incluida)."""
        administrador = Usuario.objects.create_superuser(email="admin@prueba.local", password="la-del-admin")
        antes = (administrador.password, administrador.is_active, Usuario.objects.filter(is_superuser=True).count())

        def cargador(contrasena):
            return verificacion.ResumenDeCarga(creado=("algo",), cuentas=("a@prueba1.local · agronomo",), pendiente=("hacé esto",))

        with _sin_render(), mock.patch.object(verificacion, "_CARGADORES", []):
            verificacion.registrar_cargador("x", "Cargador X", 10, cargador)
            salida, errores = self._correr("secreta-123")
        self.assertNotIn("secreta-123", salida + errores)
        self.assertIn("a@prueba1.local · agronomo", salida)
        self.assertIn("PENDIENTE: hacé esto", salida)
        administrador.refresh_from_db()
        self.assertEqual(
            (administrador.password, administrador.is_active, Usuario.objects.filter(is_superuser=True).count()), antes
        )
