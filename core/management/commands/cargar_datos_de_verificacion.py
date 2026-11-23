# Comando ``cargar_datos_de_verificacion`` (CLAUDE.md, «Datos para la verificación a mano»): deja la base LOCAL cargada con lo que
# necesita la verificación a mano de una tarea. No tiene lógica propia: valida las opciones, llama a ``core.verificacion`` e imprime.
# Idempotente, no borra nada y no toca al Administrador. Se niega a correr con DEBUG apagado, con una base que no es localhost o con
# variables de Render. Nunca imprime la contraseña ni un token.

import os
import sys

from django.core.management.base import BaseCommand, CommandError

from core import verificacion


class Command(BaseCommand):
    """Carga los datos de verificación de cada app registrada.

    Uso (PowerShell, con el entorno virtual activo; la contraseña es la de tu CLAUDE.local.md):

        python manage.py cargar_datos_de_verificacion --contrasena <contraseña>
        python manage.py cargar_datos_de_verificacion --listar
        python manage.py cargar_datos_de_verificacion --contrasena <contraseña> --solo iot

    Sin ``--contrasena`` lee la variable de entorno ``INFOPONIA_CONTRASENA_DE_PRUEBA``. Termina con código 1 si algún cargador falló.
    """

    help = "Carga en la base LOCAL los datos para la verificación a mano. Opciones: --contrasena, --solo, --listar."

    def add_arguments(self, parser):
        parser.add_argument("--contrasena", help="Contraseña de las cuentas de prueba (la de tu CLAUDE.local.md).")
        parser.add_argument("--solo", metavar="CODIGO", help="Corre solo el cargador con ese código.")
        parser.add_argument("--listar", action="store_true", help="Muestra los cargadores en orden, sin cargar nada.")

    def handle(self, *args, **opciones):
        if opciones["listar"]:
            for cargador in verificacion.cargadores():
                self.stdout.write(f"{cargador.orden:>4}  {cargador.codigo}  {cargador.nombre}")
            return
        contrasena = opciones["contrasena"] or os.environ.get("INFOPONIA_CONTRASENA_DE_PRUEBA")
        if not contrasena:
            raise CommandError("Falta la contraseña de las cuentas de prueba: pasá --contrasena (está en tu CLAUDE.local.md).")
        try:
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
