# Ayuda para las pruebas de operaciones simultáneas (SEG-15, cuentas vinculadas de D-32). No es un
# archivo de pruebas: lo importan las clases ...ConcurrenciaTests de cada caso de uso.
#
# Cómo simula dos operaciones simultáneas: corre cada una en su propio hilo, con su propia conexión a la
# base (Django abre una por hilo), así que son dos transacciones de verdad, como dos pedidos de dos
# navegadores. Por eso las pruebas que la usan son TransactionTestCase: TestCase envuelve todo en una sola
# transacción de una sola conexión y no puede simular esto.

import threading
import time
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection

from core.models import RegistroAuditoria

# Tiempo máximo de cada espera, en segundos: si algo falla, la prueba termina en vez de colgar el CI.
ESPERA_MAXIMA = 10
# Cuánto se deja correr a la otra operación mientras la primera está detenida con sus bloqueos tomados.
VENTANA_DE_LA_OTRA = 1.5
# Cada cuánto se pregunta, con ``primera``, si la otra operación terminó o quedó esperando un bloqueo.
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


def correr_a_la_vez(operacion_a, operacion_b, primera=None):
    """Corre las dos operaciones a la vez y devuelve ``{"a": resultado_o_excepcion, "b": ...}``.

    1. Los dos hilos arrancan juntos (``threading.Barrier``).
    2. La primera operación que llega a ``RegistroAuditoria.objects.registrar`` (ya tomó sus bloqueos y
       escribió su cambio, pero todavía no confirmó la transacción) se detiene ahí.
    3. Mientras está detenida, la otra corre durante ``VENTANA_DE_LA_OTRA`` segundos. Si el servicio
       bloquea bien las filas, la otra queda esperando el bloqueo; si no, avanza con datos viejos.
    4. Se libera la primera, que confirma, y se espera a que terminen las dos.

    Con ``primera`` ("a" o "b"), el orden deja de depender de la velocidad de la máquina:

    - La otra operación no arranca hasta que ``primera`` se detuvo en ``registrar`` (o terminó sin llegar):
      ``primera`` es siempre la que se detiene.
    - ``primera`` se libera en un punto exacto y no después de ``VENTANA_DE_LA_OTRA``: cuando la otra
      terminó o cuando su conexión quedó esperando un bloqueo de la base (se pregunta a
      ``pg_stat_activity``). Si no pasa ninguna de las dos cosas en ``ESPERA_MAXIMA``, la prueba falla con
      un error que lo dice, en vez de pasar sin haber probado nada.

    Cada hilo cierra su conexión a la base al terminar (``connection.close()``), para no dejar
    conexiones abiertas que hagan fallar el borrado de la base de prueba.
    """
    if primera not in (None, "a", "b"):
        raise ValueError(f"primera tiene que ser 'a', 'b' o None, no {primera!r}")
    barrera = threading.Barrier(2, timeout=ESPERA_MAXIMA)
    hay_una_detenida = threading.Event()
    # Con ``primera``: la otra arranca cuando ``primera`` se detuvo (o terminó sin llegar a detenerse).
    puede_arrancar_la_otra = threading.Event()
    seguir = threading.Event()
    reclamo = threading.Lock()
    estado = {"detenida": None, "la_otra": None}
    resultados = {}
    pids = {}
    registrar_original = RegistroAuditoria.objects.registrar

    def registrar_y_detenerse(*args, **kwargs):
        """Registra y, si es la primera operación en llegar acá, espera la señal para seguir."""
        registro = registrar_original(*args, **kwargs)
        with reclamo:
            soy_la_primera = estado["detenida"] is None
            if soy_la_primera:
                estado["detenida"] = threading.current_thread().name
        if soy_la_primera:
            hay_una_detenida.set()
            puede_arrancar_la_otra.set()
            seguir.wait(ESPERA_MAXIMA)
        return registro

    def correr(nombre, operacion):
        """Cuerpo de cada hilo: espera a la otra (y, con ``primera``, a que ``primera`` se detenga), anota el
        identificador de su conexión, corre la operación y guarda el resultado."""
        try:
            barrera.wait()
            if primera is not None:
                if nombre != primera:
                    puede_arrancar_la_otra.wait(ESPERA_MAXIMA)
                # El identificador de la conexión de este hilo, para preguntar si quedó esperando un bloqueo.
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    pids[nombre] = cursor.fetchone()[0]
            resultados[nombre] = operacion()
        except Exception as error:  # se guarda para que la prueba la inspeccione
            resultados[nombre] = error
        finally:
            if nombre == primera:
                puede_arrancar_la_otra.set()  # si terminó sin detenerse, que la otra no espere de más
            connection.close()

    hilos = {
        nombre: threading.Thread(target=correr, args=(nombre, operacion), name=nombre)
        for nombre, operacion in (("a", operacion_a), ("b", operacion_b))
    }
    with mock.patch.object(
        RegistroAuditoria.objects, "registrar", side_effect=registrar_y_detenerse
    ):
        for hilo in hilos.values():
            hilo.start()
        if hay_una_detenida.wait(ESPERA_MAXIMA):
            otra = "b" if estado["detenida"] == "a" else "a"
            if primera is None:
                hilos[otra].join(VENTANA_DE_LA_OTRA)
            else:
                estado["la_otra"] = _esperar_que_termine_o_se_bloquee(hilos[otra], pids, otra)
        seguir.set()
        for hilo in hilos.values():
            hilo.join(ESPERA_MAXIMA)
    colgados = [nombre for nombre, hilo in hilos.items() if hilo.is_alive()]
    if colgados:
        raise AssertionError(f"Las operaciones {colgados} no terminaron en {ESPERA_MAXIMA} s.")
    if primera is not None and estado["detenida"] != primera:
        raise AssertionError(
            f"Se pidió que «{primera}» se detuviera primero, pero no llegó a registrar la auditoría."
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
