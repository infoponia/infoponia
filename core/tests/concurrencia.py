# Ayuda para las pruebas de operaciones simultáneas (SEG-15, cuentas vinculadas de D-32). No es un
# archivo de pruebas: lo importan las clases ...ConcurrenciaTests de cada caso de uso.
#
# Cómo simula dos operaciones simultáneas: corre cada una en su propio hilo, con su propia conexión a la
# base (Django abre una por hilo), así que son dos transacciones de verdad, como dos pedidos de dos
# navegadores. Por eso las pruebas que la usan son TransactionTestCase: TestCase envuelve todo en una sola
# transacción de una sola conexión y no puede simular esto.
#
# El orden de las dos operaciones no depende de la velocidad de la máquina: una de ellas (``primera``) se
# detiene en un punto exacto y recién entonces arranca la otra (ver ``correr_a_la_vez``).

import threading
import time
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection

from core.models import RegistroAuditoria

# Tiempo máximo de cada espera, en segundos: si algo falla, la prueba termina en vez de colgar el CI.
ESPERA_MAXIMA = 10
# Cada cuánto se pregunta si la otra operación terminó o quedó esperando un bloqueo.
INTERVALO_DE_CONSULTA = 0.02


def _esperando_un_bloqueo(pid):
    """True si la conexión ``pid`` de PostgreSQL está esperando un bloqueo (de fila, de tabla o de una
    transacción ajena). Lo pregunta a ``pg_stat_activity`` desde la conexión del hilo principal."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [pid])
        fila = cursor.fetchone()
    return fila is not None and fila[0] == "Lock"


def _esperar_que_termine_o_se_bloquee(hilo, pids, nombre):
    """Espera hasta que el hilo ``nombre`` termine o su conexión quede esperando un bloqueo de la base, sin
    pasar de ``ESPERA_MAXIMA``. Devuelve "terminó", "bloqueada" o "ninguna" (si se venció la espera)."""
    limite = time.monotonic() + ESPERA_MAXIMA
    while time.monotonic() < limite:
        if not hilo.is_alive():
            return "terminó"
        pid = pids.get(nombre)
        if pid is not None and _esperando_un_bloqueo(pid):
            return "bloqueada"
        time.sleep(INTERVALO_DE_CONSULTA)
    return "ninguna"


def correr_a_la_vez(operacion_a, operacion_b, primera, detener_antes_de=None):
    """Corre las dos operaciones en dos hilos y devuelve ``{"a": resultado_o_excepcion, "b": ...}``.

    ``primera`` ("a" o "b", obligatorio) es la operación que se detiene en un punto exacto; la otra no arranca
    hasta que ``primera`` se detuvo. Así el choque que la prueba quiere demostrar no depende de la velocidad de
    la máquina:

    1. ``primera`` corre hasta su punto de parada y se detiene ahí, con lo que tenga tomado hasta ese momento.
       Por defecto es ``RegistroAuditoria.objects.registrar``: ya tomó sus bloqueos y escribió su cambio, pero
       todavía no confirmó la transacción.
    2. Recién entonces arranca la otra operación. Si el servicio bloquea bien las filas, queda esperando el
       bloqueo; si no, avanza con datos viejos.
    3. ``primera`` se libera cuando la otra terminó o cuando su conexión quedó esperando un bloqueo de la base
       (se pregunta a ``pg_stat_activity``), y se espera a que terminen las dos. Si no pasa ninguna de las dos
       cosas en ``ESPERA_MAXIMA``, la prueba falla con un error que lo dice, en vez de pasar sin probar nada.

    ``detener_antes_de`` cambia el punto de parada: ``(objeto, "nombre")`` detiene a ``primera`` justo ANTES de
    que llame a ``objeto.nombre`` (por ejemplo, ``(servicios, "_sacar_del_grupo")``), cuando todavía no tomó
    lo que esa función toma. Sirve para probar el orden de los bloqueos o lo que pasa si algo cambia en el
    medio de una operación, que el punto de parada por defecto, al final, no puede reproducir. Solo se detiene
    la primera llamada de ``primera``.

    Falla con ``AssertionError`` si ``primera`` no llegó a su punto de parada o si la otra no terminó ni
    quedó esperando un bloqueo.

    Cada hilo cierra su conexión a la base al terminar (``connection.close()``), para no dejar
    conexiones abiertas que hagan fallar el borrado de la base de prueba.
    """
    if primera not in ("a", "b"):
        raise ValueError(f"primera tiene que ser 'a' o 'b', no {primera!r}")
    otra = "b" if primera == "a" else "a"
    # ``primera`` se detuvo (o terminó sin llegar a detenerse): la otra puede arrancar.
    primera_libre = threading.Event()
    seguir = threading.Event()
    estado = {"se_detuvo": False, "la_otra": None}
    resultados = {}
    pids = {}

    def es_la_primera_vez_de_primera():
        """Solo se detiene el hilo ``primera``, y solo la primera vez que llega al punto de parada."""
        return threading.current_thread().name == primera and not estado["se_detuvo"]

    def detenerse():
        estado["se_detuvo"] = True
        primera_libre.set()
        seguir.wait(ESPERA_MAXIMA)

    def correr(nombre, operacion):
        """Cuerpo de cada hilo: la otra espera a que ``primera`` se detenga; anota el identificador de su
        conexión (para preguntar si quedó esperando un bloqueo), corre la operación y guarda el resultado."""
        try:
            if nombre != primera:
                primera_libre.wait(ESPERA_MAXIMA)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids[nombre] = cursor.fetchone()[0]
            resultados[nombre] = operacion()
        except Exception as error:  # se guarda para que la prueba la inspeccione
            resultados[nombre] = error
        finally:
            if nombre == primera:
                primera_libre.set()  # si terminó sin detenerse, que la otra no espere de más
            connection.close()

    if detener_antes_de is None:
        objeto, atributo = RegistroAuditoria.objects, "registrar"
        funcion_original = getattr(objeto, atributo)

        def parada(*args, **kwargs):
            """Registra y, si es ``primera``, se detiene DESPUÉS de registrar."""
            registro = funcion_original(*args, **kwargs)
            if es_la_primera_vez_de_primera():
                detenerse()
            return registro

        punto = "registrar la auditoría"
    else:
        objeto, atributo = detener_antes_de
        funcion_original = getattr(objeto, atributo)

        def parada(*args, **kwargs):
            """Si es ``primera``, se detiene ANTES de llamar a la función."""
            if es_la_primera_vez_de_primera():
                detenerse()
            return funcion_original(*args, **kwargs)

        punto = f"llamar a {atributo}"

    hilos = {
        nombre: threading.Thread(target=correr, args=(nombre, operacion), name=nombre)
        for nombre, operacion in (("a", operacion_a), ("b", operacion_b))
    }
    with mock.patch.object(objeto, atributo, side_effect=parada):
        for hilo in hilos.values():
            hilo.start()
        primera_libre.wait(ESPERA_MAXIMA)
        if estado["se_detuvo"]:
            estado["la_otra"] = _esperar_que_termine_o_se_bloquee(hilos[otra], pids, otra)
        seguir.set()
        for hilo in hilos.values():
            hilo.join(ESPERA_MAXIMA)
    colgados = [nombre for nombre, hilo in hilos.items() if hilo.is_alive()]
    if colgados:
        raise AssertionError(f"Las operaciones {colgados} no terminaron en {ESPERA_MAXIMA} s.")
    if not estado["se_detuvo"]:
        raise AssertionError(
            f"Se pidió que «{primera}» se detuviera primero, pero no llegó a {punto}."
        )
    if estado["la_otra"] == "ninguna":
        raise AssertionError(
            f"La otra operación no terminó ni quedó esperando un bloqueo en {ESPERA_MAXIMA} s."
        )
    return resultados


def codigos(error):
    """Todos los códigos de un ``ValidationError``, tenga o no errores por campo."""
    if hasattr(error, "error_dict"):
        return [e.code for errores in error.error_dict.values() for e in errores]
    return [e.code for e in error.error_list]


def separar(resultados):
    """``(exitos, rechazos, otros)``: resultados normales, ``ValidationError`` y cualquier otra
    excepción (un ``IntegrityError`` sin traducir, por ejemplo, que en pantalla sería un error 500)."""
    exitos, rechazos, otros = [], [], []
    for resultado in resultados.values():
        if isinstance(resultado, ValidationError):
            rechazos.append(resultado)
        elif isinstance(resultado, Exception):
            otros.append(resultado)
        else:
            exitos.append(resultado)
    return exitos, rechazos, otros
