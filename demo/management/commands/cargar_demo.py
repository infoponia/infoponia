# Comando ``cargar_demo`` (DAT-01; decisión de la demo, hoy ``docs/decisiones/D-01-demo.md``): carga los datos base de la demo de la defensa
# (secciones 1 a 14 de ``docs/demo/datos_de_la_demo.md``). Es la ÚNICA excepción a «no cargues datos de prueba» y vale solo para la base
# ``infoponia_demo``. Primero pasa el doble candado (``demo.candado``); sin eso no escribe nada. Nunca imprime la contraseña.
# Para volver a empezar no hay borrado: se reinicia la rama de Neon y se vuelve a migrar y cargar.

import os

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from contabilidad.errores import ErrorContable
from demo import candado, carga


class Command(BaseCommand):
    """Carga los datos base de la demo.

    Uso (Shell del servicio demo de Render, con ``INFOPONIA_DEMO=1``, ``INFOPONIA_DEMO_CONTRASENA`` e ``INFOPONIA_DEMO_CORREO``):

        python manage.py cargar_demo
    """

    help = "Carga los datos base de la demo de la defensa (solo en la base infoponia_demo y con INFOPONIA_DEMO=1)."

    def handle(self, *args, **opciones):
        candado.verificar_que_se_puede_cargar()
        contexto = carga.Contexto(
            hoy=timezone.localdate(),
            base=os.environ[candado.VARIABLE_DEL_CORREO],
            contrasena=os.environ[candado.VARIABLE_DE_LA_CONTRASENA],
        )
        try:
            lineas = carga.cargar(contexto)
        except ValidationError as error:
            raise CommandError(f"Un servicio rechazó un dato de la demo: {'; '.join(error.messages)}. No se cargó nada.") from error
        except PermissionDenied as error:
            raise CommandError(f"Un servicio rechazó al actor de la demo: {error}. No se cargó nada.") from error
        except ErrorContable as error:
            raise CommandError(f"La contabilidad rechazó la carga: {error.mensaje}. No se cargó nada.") from error
        except Exception as error:  # noqa: BLE001 - errores de negocio de otras apps (ErrorDeCompras, etc.); la transacción ya se deshizo
            raise CommandError(f"La carga falló ({type(error).__name__}): {error}. No se cargó nada.") from error

        for linea in (*lineas, *contexto.avisos):
            self.stdout.write(linea)
        # Rol y correo de cada cuenta, nunca la contraseña.
        self.stdout.write("Cuentas:")
        for clave, rol, *_ in carga.CUENTAS:
            if clave in contexto.cuentas:
                self.stdout.write(f"  {rol.label}: {contexto.cuentas[clave].email}")
        self.stdout.write("Carga terminada. Ahora corré estado_demo para ver si las escenas del guion están listas, o seguí la guía.")
