# Ayuda para las pruebas de SEG-15 (invariantes de las cuentas con operaciones simultáneas). No es un
# archivo de pruebas: lo importan las clases ...ConcurrenciaTests de cada caso de uso.
#
# Cómo simula dos operaciones simultáneas: corre cada una en su propio hilo, con su propia conexión a la
# base (Django abre una por hilo), así que son dos transacciones de verdad, como dos pedidos de dos
# navegadores. Por eso las pruebas que la usan son TransactionTestCase: TestCase envuelve todo en una sola
# transacción de una sola conexión y no puede simular esto.

import threading
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection

from core.models import RegistroAuditoria

# Tiempo máximo de cada espera, en segundos: si algo falla, la prueba termina en vez de colgar el CI.
ESPERA_MAXIMA = 10
# Cuánto se deja correr a la otra operación mientras la primera está detenida con sus bloqueos tomados.
VENTANA_DE_LA_OTRA = 1.5


def correr_a_la_vez(operacion_a, operacion_b):
    """Corre las dos operaciones a la vez y devuelve ``{"a": resultado_o_excepcion, "b": ...}``.

    1. Los dos hilos arrancan juntos (``threading.Barrier``).
    2. La primera operación que llega a ``RegistroAuditoria.objects.registrar`` (ya tomó sus bloqueos y
       escribió su cambio, pero todavía no confirmó la transacción) se detiene ahí.
    3. Mientras está detenida, la otra corre durante ``VENTANA_DE_LA_OTRA`` segundos. Si el servicio
       bloquea bien las filas, la otra queda esperando el bloqueo; si no, avanza con datos viejos.
    4. Se libera la primera, que confirma, y se espera a que terminen las dos.

    Cada hilo cierra su conexión a la base al terminar (``connection.close()``), para no dejar
    conexiones abiertas que hagan fallar el borrado de la base de prueba.
    """
    barrera = threading.Barrier(2, timeout=ESPERA_MAXIMA)
    hay_una_detenida = threading.Event()
    seguir = threading.Event()
    reclamo = threading.Lock()
    estado = {"detenida": None}
    resultados = {}
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
            seguir.wait(ESPERA_MAXIMA)
        return registro

    def correr(nombre, operacion):
        """Cuerpo de cada hilo: espera a la otra, corre la operación y guarda el resultado."""
        try:
            barrera.wait()
            resultados[nombre] = operacion()
        except Exception as error:  # se guarda para que la prueba la inspeccione
            resultados[nombre] = error
        finally:
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
            hilos[otra].join(VENTANA_DE_LA_OTRA)
        seguir.set()
        for hilo in hilos.values():
            hilo.join(ESPERA_MAXIMA)
    colgados = [nombre for nombre, hilo in hilos.items() if hilo.is_alive()]
    if colgados:
        raise AssertionError(f"Las operaciones {colgados} no terminaron en {ESPERA_MAXIMA} s.")
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
