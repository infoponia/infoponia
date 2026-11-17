# Migración de datos de la tarea AUD-CNS-REG (D-36): convierte los registros de auditoría que ya existen al formato
# obligatorio del detalle ("cambios" con antes y después, "datos" de contexto, referencias {id, texto}) y suma el
# texto y el rol de cada cuenta afectada. Más un AlterField que solo cambia la ayuda del campo ``afectados``.
#
# ES LA ÚNICA EXCEPCIÓN DELIBERADA A D-22 (al registro de auditoría solo se le agregan filas). Se justifica en D-36:
# hay que unificar el formato antes de que exista una pantalla que lo lea. Corre sobre el modelo histórico, que no
# tiene el ``save`` ni el manager de la app (los que impiden modificar), y escribe con ``filter(pk=...).update(...)``.
#
# NO IMPORTA CÓDIGO DE LA APP, a propósito: ni ``GrupoCuentas.texto_de``, ni ``texto_de`` de ``core.models``, ni
# ninguna otra función. Toda la lógica está copiada acá abajo (el texto «Grupo N» y el texto de las cuentas),
# para que esta migración produzca siempre el mismo resultado aunque la app cambie después. Si mañana cambia el
# texto de un grupo o de una cuenta, los registros que esta migración ya convirtió y los que convierta en un
# despliegue nuevo seguirán con el texto de acá. El texto de las cuentas es el de sus datos AL MOMENTO DE MIGRAR,
# no el que tenían cuando se hizo el registro (el formato viejo no lo guardó).
#
# Idempotente: un detalle que ya está en el formato nuevo (sus claves están dentro de «cambios» y «datos»; ningún
# formato viejo usa esas claves) y un afectado que ya tiene «texto» se dejan como están. Volver a correrla, o
# correrla sobre registros escritos con el código nuevo, no los cambia.
#
# Si encuentra un detalle viejo que no reconoce, FALLA (ValueError con el id del registro) y no cambia nada, en
# vez de descartar datos de una auditoría sin avisar.
#
# Vuelta (reverse): deja los registros en el formato viejo. Lo único que se pierde es lo que el formato viejo no
# tenía: el teléfono cargado en un alta nueva, y el texto y el rol de los afectados.

from django.db import migrations, models

# Los detalles nuevos solo tienen estas claves en el primer nivel.
CLAVES_NUEVAS = {"cambios", "datos"}
MODELO_CUENTA = "core.usuario"
ADMINISTRADOR = "administrador"  # rol que la auditoría guarda para un superusuario (D-10)


def texto_de_cuenta(nombre, apellido, email):
    """«Nombre Apellido (email)», o solo el email si la cuenta no tiene nombre (copia de la lógica de la app)."""
    completo = f"{nombre} {apellido}".strip()
    return f"{completo} ({email})" if completo else email


def referencia_a_grupo(grupo_id):
    """Referencia a un grupo de cuentas vinculadas: ``{"id", "texto"}``. El texto «Grupo N» está escrito acá a
    propósito (ver el encabezado): no se pide a la app, porque el grupo puede ya no existir."""
    return {"id": grupo_id, "texto": f"Grupo {grupo_id}"}


def _cambio(antes, despues):
    return {"antes": antes, "despues": despues}


def _par(valor, campo):
    """El ``[antes, despues]`` del formato viejo."""
    if not isinstance(valor, (list, tuple)) or len(valor) != 2:
        raise ValueError(f"el campo {campo!r} no tiene la forma [antes, despues]: {valor!r}")
    return valor


def _sin_vacios(cambios, datos):
    """Un detalle nuevo con solo las claves que tienen contenido."""
    detalle = {}
    if cambios:
        detalle["cambios"] = cambios
    if datos:
        detalle["datos"] = datos
    return detalle


def detalle_a_nuevo(accion, viejo):
    """Convierte un detalle del formato viejo al nuevo (D-36). Uno que ya está en el nuevo no cambia."""
    if set(viejo) <= CLAVES_NUEVAS:
        return viejo
    resto = dict(viejo)
    cambios, datos = {}, {}

    if accion == "alta":
        # Alta: todo dato cargado es un cambio con «antes» nulo. El formato viejo no guardó el teléfono.
        for campo in ("rol", "nombre", "apellido", "email"):
            if campo in resto:
                cambios[campo] = _cambio(None, resto.pop(campo))
        if "acceso" in resto:
            datos["acceso"] = resto.pop("acceso")
    elif accion == "modificacion":
        for campo in list(resto):
            antes, despues = _par(resto.pop(campo), campo)
            cambios[campo] = _cambio(antes, despues)
    elif accion in ("baja", "reactivacion", "restablecimiento"):
        if "estado" in resto:
            antes, despues = _par(resto.pop("estado"), "estado")
            cambios["estado"] = _cambio(antes, despues)
        if "sale_del_grupo" in resto:
            cambios["grupo"] = _cambio(referencia_a_grupo(resto.pop("sale_del_grupo")), None)
        if "acceso" in resto:
            datos["acceso"] = resto.pop("acceso")
    elif accion in ("cambio_contrasena", "recuperacion_contrasena", "aceptacion_invitacion"):
        for clave in ("era_temporal", "invitacion_pendiente"):
            if clave in resto:
                datos[clave] = resto.pop(clave)
    elif accion == "vinculacion":
        datos["grupo"] = referencia_a_grupo(resto.pop("grupo"))
        grupo_unido = resto.pop("grupo_unido", None)
        datos["grupo_unido"] = None if grupo_unido is None else referencia_a_grupo(grupo_unido)
    elif accion == "desvinculacion":
        datos["grupo"] = referencia_a_grupo(resto.pop("grupo"))
        datos["disuelto"] = resto.pop("disuelto")
    else:
        raise ValueError(f"acción desconocida: {accion!r}")

    if resto:
        raise ValueError(f"claves que no se reconocen en el detalle de {accion!r}: {sorted(resto)}")
    return _sin_vacios(cambios, datos)


def detalle_a_viejo(accion, nuevo):
    """Convierte un detalle del formato nuevo al viejo. Uno que ya está en el viejo no cambia."""
    if not set(nuevo) <= CLAVES_NUEVAS:
        return nuevo
    cambios = dict(nuevo.get("cambios", {}))
    datos = dict(nuevo.get("datos", {}))
    viejo = {}

    def despues(campo):
        return cambios.pop(campo)["despues"]

    if accion == "alta":
        for campo in ("rol", "nombre", "apellido", "email"):
            if campo in cambios:
                viejo[campo] = despues(campo)
        cambios.pop("telefono", None)  # el formato viejo no lo guardaba
        if "acceso" in datos:
            viejo["acceso"] = datos.pop("acceso")
    elif accion == "modificacion":
        for campo in list(cambios):
            par = cambios.pop(campo)
            viejo[campo] = [par["antes"], par["despues"]]
    elif accion in ("baja", "reactivacion", "restablecimiento"):
        if "estado" in cambios:
            par = cambios.pop("estado")
            viejo["estado"] = [par["antes"], par["despues"]]
        if "acceso" in datos:
            viejo["acceso"] = datos.pop("acceso")
        if "grupo" in cambios:
            viejo["sale_del_grupo"] = cambios.pop("grupo")["antes"]["id"]
    elif accion in ("cambio_contrasena", "recuperacion_contrasena", "aceptacion_invitacion"):
        for clave in ("era_temporal", "invitacion_pendiente"):
            if clave in datos:
                viejo[clave] = datos.pop(clave)
    elif accion == "vinculacion":
        viejo["grupo"] = datos.pop("grupo")["id"]
        grupo_unido = datos.pop("grupo_unido", None)
        viejo["grupo_unido"] = None if grupo_unido is None else grupo_unido["id"]
    elif accion == "desvinculacion":
        viejo["grupo"] = datos.pop("grupo")["id"]
        viejo["disuelto"] = datos.pop("disuelto")
    else:
        raise ValueError(f"acción desconocida: {accion!r}")

    if cambios or datos:
        raise ValueError(
            f"datos que no se reconocen en el detalle de {accion!r}: {sorted(cambios) + sorted(datos)}"
        )
    return viejo


def afectados_a_nuevo(afectados, cuentas):
    """Suma «texto» y, en las cuentas, «rol» a cada afectado. ``cuentas`` es ``{id: {"texto", "rol"}}``. Un
    afectado que ya tiene texto no cambia. Una cuenta que ya no existe (no debería pasar: no se borran) queda
    con el texto «Cuenta <id>» y sin rol."""
    convertidos = []
    for afectado in afectados:
        if "texto" in afectado:
            convertidos.append(afectado)
            continue
        nuevo = {"modelo": afectado["modelo"], "id": afectado["id"]}
        if afectado["modelo"] == MODELO_CUENTA:
            cuenta = cuentas.get(afectado["id"])
            if cuenta is None:
                nuevo["texto"] = f"Cuenta {afectado['id']}"
            else:
                nuevo["texto"] = cuenta["texto"]
                nuevo["rol"] = cuenta["rol"]
        else:
            nuevo["texto"] = f"{afectado['modelo']} {afectado['id']}"
        convertidos.append(nuevo)
    return convertidos


def afectados_a_viejo(afectados):
    """Deja cada afectado como ``{"modelo", "id"}``."""
    return [{"modelo": a["modelo"], "id": a["id"]} for a in afectados]


def a_formato_nuevo(accion, detalle, afectados, cuentas):
    """``(detalle, afectados)`` en el formato nuevo. Es lo que prueba ``core/tests/test_migracion_0008.py``."""
    return detalle_a_nuevo(accion, detalle), afectados_a_nuevo(afectados, cuentas)


def a_formato_viejo(accion, detalle, afectados):
    """``(detalle, afectados)`` en el formato viejo (la vuelta)."""
    return detalle_a_viejo(accion, detalle), afectados_a_viejo(afectados)


def cuentas_actuales(Usuario):
    """``{id: {"texto", "rol"}}`` de todas las cuentas, con el modelo histórico. El rol es «administrador» para un
    superusuario (que no tiene ``rol``) y el ``rol`` del dominio para el resto (D-10)."""
    filas = Usuario.objects.values_list("pk", "first_name", "last_name", "email", "is_superuser", "rol")
    return {
        pk: {
            "texto": texto_de_cuenta(nombre, apellido, email),
            "rol": ADMINISTRADOR if es_superusuario else rol,
        }
        for pk, nombre, apellido, email, es_superusuario, rol in filas
    }


def _convertir(apps, convertir):
    """Aplica ``convertir(registro) -> (detalle, afectados)`` a cada registro y escribe solo los que cambian."""
    Registro = apps.get_model("core", "RegistroAuditoria")
    for registro in Registro.objects.all().order_by("pk").iterator(chunk_size=500):
        try:
            detalle, afectados = convertir(registro)
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"Registro de auditoría {registro.pk}: {error}") from error
        if detalle != registro.detalle or afectados != registro.afectados:
            # ``update`` del modelo histórico: sin el save ni el manager de la app (única excepción a D-22).
            Registro.objects.filter(pk=registro.pk).update(detalle=detalle, afectados=afectados)


def migrar_adelante(apps, schema_editor):
    """Pasa todos los registros existentes al formato nuevo."""
    cuentas = cuentas_actuales(apps.get_model("core", "Usuario"))
    _convertir(
        apps,
        lambda r: a_formato_nuevo(r.accion, r.detalle, r.afectados, cuentas),
    )


def migrar_atras(apps, schema_editor):
    """Deja todos los registros en el formato viejo."""
    _convertir(apps, lambda r: a_formato_viejo(r.accion, r.detalle, r.afectados))


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_invitacion_por_correo"),
    ]

    operations = [
        # Solo cambia la ayuda del campo: no toca la base.
        migrations.AlterField(
            model_name="registroauditoria",
            name="afectados",
            field=models.JSONField(
                default=list,
                help_text='Lista de {"modelo": "core.usuario", "id": 7, "texto": "...", "rol": "capataz"}.',
                verbose_name="cuentas u objetos afectados",
            ),
        ),
        migrations.RunPython(migrar_adelante, migrar_atras),
    ]
