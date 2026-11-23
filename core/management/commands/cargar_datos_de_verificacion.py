# Comando ``cargar_datos_de_verificacion`` (CLAUDE.md, «Datos para la verificación a mano»): deja la base LOCAL cargada con lo que
# necesita la verificación a mano de una tarea. No tiene lógica propia: valida las opciones, llama a ``core.verificacion`` e imprime.
# Idempotente, no borra nada y no toca al Administrador. Se niega a correr con DEBUG apagado, con una base que no es localhost o con
# variables de Render. La contraseña no es un argumento: se pide sin mostrarla o sale de una variable de entorno. Nunca imprime la contraseña ni un token.

import getpass
import os
import sys

from django.core.management.base import BaseCommand, CommandError

from core import verificacion


VARIABLE_DE_LA_CONTRASENA = "INFOPONIA_CONTRASENA_DE_PRUEBA"


class Command(BaseCommand):
    """Carga los datos de verificación de cada app registrada.

    La contraseña de las cuentas de prueba (la de tu CLAUDE.local.md) **no se pasa como argumento** (quedaría en el historial de la terminal y en la lista de
    procesos): el comando la pide sin mostrarla, o la toma de la variable de entorno ``INFOPONIA_CONTRASENA_DE_PRUEBA``. Uso (PowerShell, entorno virtual activo):

        python manage.py cargar_datos_de_verificacion
        python manage.py cargar_datos_de_verificacion --solo iot
        python manage.py cargar_datos_de_verificacion --listar

    Sin terminal interactiva (un script) la contraseña tiene que venir de la variable de entorno. Termina con código 1 si algún cargador falló.
    """

    help = "Carga en la base LOCAL los datos para la verificación a mano. Opciones: --solo, --listar. La contraseña se pide o sale de INFOPONIA_CONTRASENA_DE_PRUEBA."

    def add_arguments(self, parser):
        parser.add_argument("--solo", metavar="CODIGO", help="Corre solo el cargador con ese código.")
        parser.add_argument("--listar", action="store_true", help="Muestra los cargadores en orden, sin cargar nada.")

    def _contrasena(self):
        """La contraseña de las cuentas de prueba: de la variable de entorno o, si hay terminal, pedida sin mostrarla. Nunca de un argumento."""
        contrasena = os.environ.get(VARIABLE_DE_LA_CONTRASENA)
        if contrasena:
            return contrasena
        if sys.stdin is not None and sys.stdin.isatty():
            contrasena = getpass.getpass("Contraseña de las cuentas de prueba (la de tu CLAUDE.local.md): ")
            if contrasena:
                return contrasena
        raise CommandError(
            f"Falta la contraseña de las cuentas de prueba (la de tu CLAUDE.local.md): corré el comando en una terminal para que te la pida, o definí la variable de entorno {VARIABLE_DE_LA_CONTRASENA}."
        )

    def handle(self, *args, **opciones):
        if opciones["listar"]:
            for cargador in verificacion.cargadores():
                self.stdout.write(f"{cargador.orden:>4}  {cargador.codigo}  {cargador.nombre}")
            return
        try:
            verificacion.exigir_base_local()  # antes de pedir nada: en una base que no es local, ni siquiera se pregunta
            contrasena = self._contrasena()
            resultados = verificacion.cargar_datos(contrasena, solo=opciones["solo"])
        except verificacion.BaseNoLocal as error:
            raise CommandError(str(error)) from None
        except ValueError as error:
            raise CommandError(str(error)) from None

        fallo = False
        for cargador, resumen, error in resultados:
            self.stdout.write(f"== {cargador.nombre}")
            if error is not None:
                fallo = True
                # Solo el tipo y el mensaje: ningún cargador pone secretos en sus excepciones.
                self.stderr.write(f"   FALLÓ: {type(error).__name__}: {error}")
                continue
            for linea in resumen.creado or ("(nada nuevo: ya estaba todo cargado)",):
                self.stdout.write(f"   {linea}")
            for cuenta in resumen.cuentas:
                self.stdout.write(f"   cuenta: {cuenta}")
            for pendiente in resumen.pendiente:
                self.stdout.write(self.style.WARNING(f"   PENDIENTE: {pendiente}"))
        if fallo:
            sys.exit(1)
