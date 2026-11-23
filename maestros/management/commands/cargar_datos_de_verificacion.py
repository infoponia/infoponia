# Comando ``cargar_datos_de_verificacion`` (CLAUDE.md, «Datos para la verificación a mano»): deja la base LOCAL con lo que el
# estudiante necesita para verificar a mano una tarea, sin que cargue nada a mano. Es idempotente: cada tarea lo amplía. Lo creó
# MAE-02d, la primera que lo necesitó, en ``maestros`` porque ``core`` no puede importar los modelos de ``maestros`` (regla A1
# de D-37); si una app de nivel mayor tiene que ampliarlo, se decide entonces si se muda.
#
# Seguridad: se niega a correr con DEBUG apagado, con una base que no sea localhost o con variables de Render. Nunca toca al
# Administrador ni a ninguna cuenta que no creó él (las cuentas de prueba son ``<rol>@prueba<N>.local``), no borra nada y no
# crea Gerente: D-09 permite uno solo activo y la base local ya tiene el del estudiante, que entra con su propia cuenta.
# La contraseña de las cuentas de prueba entra por ``--clave`` (está en ``CLAUDE.local.md``, que no se versiona): jamás se
# escribe en un archivo del repo, que es público.

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.models import Agronomo, Capataz, Gerente
from maestros.models import Alerta, Invernadero, Localidad
from maestros.servicios import alertas as api_alertas
from maestros.servicios.invernaderos import alta_invernadero

HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}

# MAE-02d: dos invernaderos, cada uno con su Agrónomo, y un Capataz sin invernadero (para probar el 403). El invernadero 1 no
# tiene Capataz: por la regla 3 de 8.22 tiene la alerta «Invernadero sin Capataz activo», la que usa la verificación a mano.
INVERNADERO_1 = "Invernadero Verificación 1"
INVERNADERO_2 = "Invernadero Verificación 2"
CUENTAS = (
    # (clase, correo, nombre, apellido)
    (Agronomo, "agronomo@prueba1.local", "Agustina", "Prueba Uno"),
    (Agronomo, "agronomo@prueba2.local", "Armando", "Prueba Dos"),
    (Capataz, "capataz@prueba1.local", "Camila", "Prueba Uno"),
)


def _motivo_de_negativa():
    """El motivo por el que NO se puede correr, o ``None`` si es una base local de desarrollo."""
    if not settings.DEBUG:
        return "DEBUG está apagado: este comando es solo para desarrollo."
    host = connection.settings_dict.get("HOST") or "localhost"
    if host not in HOSTS_LOCALES:
        return f"la base no es local (host «{host}»): este comando solo corre contra localhost."
    render = sorted(nombre for nombre in os.environ if nombre.upper().startswith("RENDER"))
    if render:
        return f"hay variables de Render ({', '.join(render)}): este comando no corre en el servidor."
    return None


class Command(BaseCommand):
    """Carga (o repara) los datos de verificación a mano de las tareas hechas. Uso (PowerShell, entorno virtual activo):

        python manage.py cargar_datos_de_verificacion --clave <la de CLAUDE.local.md>
    """

    help = "Deja la base local con los datos para verificar a mano (solo desarrollo, idempotente)."

    def add_arguments(self, parser):
        parser.add_argument("--clave", required=True, help="Contraseña de las cuentas de prueba (la de CLAUDE.local.md).")

    def handle(self, *args, clave, **opciones):
        motivo = _motivo_de_negativa()
        if motivo:
            raise CommandError(f"Me niego a correr: {motivo}")
        with transaction.atomic():
            gerente = Gerente.objects.filter(is_active=True).first()
            if gerente is None:
                raise CommandError("No hay un Gerente activo: hace falta uno para dar de alta los invernaderos de prueba.")
            cuentas = self._cuentas(clave)
            invernadero_1 = self._invernadero(gerente, INVERNADERO_1, cuentas["agronomo@prueba1.local"])
            self._invernadero(gerente, INVERNADERO_2, cuentas["agronomo@prueba2.local"])
            alerta = self._alerta_sin_capataz(invernadero_1)
        self.stdout.write(self.style.SUCCESS("Datos de verificación cargados."))
        self.stdout.write(f"  Gerente: el de la base ({gerente.email}), con su propia contraseña.")
        for correo in cuentas:
            self.stdout.write(f"  {correo} (contraseña: la de CLAUDE.local.md)")
        self.stdout.write(f"  «{INVERNADERO_1}»: alerta «{alerta.descripcion_alerta}» (id {alerta.pk}), no leída.")

    def _cuentas(self, clave):
        """Crea las cuentas de prueba que falten (no toca las que ya existen) y devuelve ``{correo: cuenta}``."""
        cuentas = {}
        for clase, correo, nombre, apellido in CUENTAS:
            cuenta = clase.objects.filter(email=correo).first()
            if cuenta is None:
                cuenta = clase.objects.create_user(email=correo, password=clave, first_name=nombre, last_name=apellido)
            cuentas[correo] = cuenta
        return cuentas

    def _invernadero(self, gerente, nombre, agronomo):
        """El invernadero de prueba ``nombre``; si no existe, lo da de alta con el servicio real (que audita y avisa, D-22)."""
        existente = Invernadero.objects.filter(nombre_invernadero=nombre).first()
        if existente is not None:
            return existente
        localidad = Localidad.objects.order_by("id").first()
        if localidad is None:
            raise CommandError("Falta la geografía de Georef (migración 0002 de maestros).")
        return alta_invernadero(
            gerente,
            nombre,
            tipo_direccion="urbana",
            localidad_id=localidad.pk,
            calle="Calle de prueba",
            numero_calle="100",
            agronomo_id=agronomo.pk,
        )

    def _alerta_sin_capataz(self, invernadero):
        """Deja activa y no leída la alerta «sin Capataz» del invernadero 1 (la repone si se resolvió) y la devuelve."""
        invernadero.refresh_from_db()
        if invernadero.capataz_id is not None:
            raise CommandError(
                f"«{invernadero.nombre_invernadero}» ya tiene un Capataz y la alerta «sin Capataz» no puede existir: "
                "quitale el Capataz desde la ficha para repetir la verificación."
            )
        api_alertas.sincronizar_alertas_de_personal(invernadero, roles=["capataz"])
        alerta = Alerta.objects.activas().get(invernadero=invernadero, tipo_alerta="sin_capataz")
        Alerta.objects.filter(pk=alerta.pk).update(estado_lectura_alerta=Alerta.Lectura.NO_LEIDA)
        alerta.refresh_from_db()
        return alerta
