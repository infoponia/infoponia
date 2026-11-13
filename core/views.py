# Vistas de core: inicio de sesión, cierre de sesión, elegir contraseña (cambio forzado por contraseña
# temporal), Mi perfil con el cambio voluntario de contraseña y las cuentas vinculadas, inicio de cada cuenta
# y cuentas del Gerente y del Administrador. Solo orquestan: validan la entrada, llaman al servicio y
# renderizan.

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from core.acceso import ADMINISTRADOR, nombre_visible_del_rol, rol_de, rol_requerido
from core.forms import (
    FormularioAltaUsuario,
    FormularioCambioContrasena,
    FormularioContrasenaNueva,
    FormularioFiltroUsuarios,
    FormularioInicioSesion,
    FormularioModificarUsuario,
    FormularioVincularCuenta,
)
from core.middleware import permitido_con_contrasena_temporal
from core.models import Usuario
from core.servicios import (
    MENSAJE_FUERA_DEL_GRUPO,
    acciones_permitidas,
    alta_usuario,
    baja_usuario,
    cambiar_contrasena,
    consultar_usuarios,
    cuenta_para_cambiar,
    cuentas_vinculadas,
    desvincular_cuenta,
    gerente_activo_que_impide_el_alta,
    gerente_activo_que_impide_reactivar,
    modificar_usuario,
    obtener_cuenta,
    obtener_cuenta_del_grupo,
    quien_gestiona,
    reactivar_usuario,
    restablecer_contrasena,
    vincular_cuenta,
)


class IniciarSesionView(LoginView):
    """Pantalla de inicio de sesión (USR-INI-SES, SEG-01). Exenta del login obligatorio por Django.

    Una cuenta que ya tiene sesión es llevada directamente a su inicio.
    """

    template_name = "core/iniciar_sesion.html"
    authentication_form = FormularioInicioSesion
    redirect_authenticated_user = True


# SEG-08: Django vacía la sesión en el servidor, no solo la cookie, y solo acepta POST.
# Se exime del login obligatorio para que una sesión ya vencida pueda cerrarse sin rebotar, y
# del bloqueo por contraseña temporal para que quien la tiene pueda salir (regla 4 de USR-INI-SES).
cerrar_sesion = permitido_con_contrasena_temporal(login_not_required(LogoutView.as_view()))


@permitido_con_contrasena_temporal
def elegir_contrasena(request):
    """Pantalla «Elegí tu contraseña» (vForced): USR-CMB-CTR cuando extiende a USR-INI-SES.

    Solo para cuentas con contraseña temporal (las demás van al inicio). Cambia siempre la
    contraseña de ``request.user`` (regla 3): la cuenta no viaja en la URL ni en el formulario.
    """
    if not request.user.tiene_contrasena_temporal:
        return redirect("core:inicio")

    if request.method == "POST":
        form = FormularioContrasenaNueva(request.POST)
        if form.is_valid():
            try:
                cambiar_contrasena(request.user, form.cleaned_data["contrasena_nueva"])
            except ValidationError as error:
                for campo, errores in error.error_dict.items():
                    for e in errores:
                        # Un error de un campo que este formulario no tiene (por ejemplo, la
                        # contraseña actual, si la temporal se reemplazó en otra pestaña) va general.
                        form.add_error(campo if campo in form.fields else None, e)
            else:
                # SEG-10: el cambio invalida las demás sesiones de la cuenta; esta se mantiene.
                update_session_auth_hash(request, request.user)
                return redirect("core:inicio")
    else:
        form = FormularioContrasenaNueva()
    return render(request, "core/elegir_contrasena.html", {"form": form})


# ---- Mi perfil y cambio voluntario de contraseña (USR-GST-PRF y USR-CMB-CTR, tarea 06a) ----
# Mi perfil no tiene servicio: solo muestra la cuenta con la que se opera y no modifica nada, igual que
# iniciar sesión (D-25). La foto de perfil (SEG-19) llega en la tarea 07. Las cuentas vinculadas (06b) se
# ven y se gestionan desde acá: ver más abajo.

MENSAJE_CONTRASENA_ACTUALIZADA = (
    "Contraseña actualizada. Se cerraron las demás sesiones abiertas con esta cuenta; esta sigue abierta."
)


def _render_mi_perfil(request, form, ventana=None, **extra):
    """Mi perfil con el formulario de cambio de contraseña ``form`` (vacío o con los errores del envío).

    ``ventana`` ("vincular" o "desvincular") abre esa ventana sobre la pantalla; ``extra`` trae lo que la
    ventana necesita. Sin JavaScript, la ventana se pide con un GET y llega así; con HTMX se inserta sola.
    """
    contexto = {
        "form": form,
        "quien_gestiona": quien_gestiona(request.user),
        "vinculadas": cuentas_vinculadas(request.user),  # [] sin grupo, sin consultar la base
        "ventana": ventana,
    }
    contexto.update(extra)
    return render(request, "core/mi_perfil.html", contexto)


def mi_perfil(request):
    """Mi perfil (USR-GST-PRF, vPerfil): los datos de la cuenta con la que se opera y el cambio de contraseña.

    - Regla 1: nombre, apellido, email, teléfono, rol y estado; nunca la contraseña.
    - Regla 2: la persona no modifica sus datos desde acá, salvo el Administrador, que gestiona su cuenta.
    - Regla 4 y SEG-14: la consulta no se audita.
    Con contraseña temporal no se llega: el middleware lleva a «Elegí tu contraseña» (SEG-04).
    """
    return _render_mi_perfil(request, FormularioCambioContrasena())


@never_cache
def cambiar_mi_contrasena(request):
    """Cambio voluntario de la contraseña desde Mi perfil (USR-CMB-CTR por sí mismo, USR-GST-PRF regla 3).

    Solo acepta POST: un GET vuelve a Mi perfil. Cambia siempre la contraseña de ``request.user`` (regla 3):
    la cuenta no viaja en la URL ni en el formulario. El servicio pide la contraseña actual (regla 1) y aplica
    la política (regla 2, SEG-03). Si sale bien, conserva esta sesión y cierra las demás (SEG-10) y vuelve a
    Mi perfil con un aviso breve (D-29); si no, muestra Mi perfil con los errores, sin volver a escribir las
    contraseñas en los campos. Sin la marca ``@permitido_con_contrasena_temporal``: con una temporal, el
    middleware lleva a «Elegí tu contraseña» (SEG-04).
    """
    if request.method != "POST":
        return redirect("core:mi_perfil")
    form = FormularioCambioContrasena(request.POST)
    if form.is_valid():
        try:
            cambiar_contrasena(
                request.user,
                form.cleaned_data["contrasena_nueva"],
                contrasena_actual=form.cleaned_data["contrasena_actual"],
            )
        except ValidationError as error:
            for campo, errores in error.error_dict.items():
                for e in errores:
                    form.add_error(campo if campo in form.fields else None, e)
        else:
            update_session_auth_hash(request, request.user)  # SEG-10
            messages.success(request, MENSAJE_CONTRASENA_ACTUALIZADA)
            return redirect("core:mi_perfil")
    return _render_mi_perfil(request, form)


# ---- Cuentas vinculadas (USR-VNC-CTA y SEG-09, tarea 06b) ----
# Solo las cuentas de un rol del dominio: el Administrador no tiene vínculos (regla 5, SEG-13), así que recibe un
# 403 con el mensaje de ``rol_requerido``. Las ventanas siguen el patrón de las confirmaciones de cuentas
# (D-28): abrirlas (GET) no cambia nada; con HTMX se inserta solo la ventana, sin JavaScript llega Mi perfil
# con la ventana abierta; la operación es un POST de un formulario común, que al salir bien redirige a Mi perfil
# con un aviso breve (D-29).

ROLES_CON_VINCULOS = tuple(Usuario.Rol)


def _es_pedido_htmx(request):
    """True si el pedido lo hizo HTMX (inserta la ventana) y no es una restauración del historial."""
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


@rol_requerido(*ROLES_CON_VINCULOS)
@never_cache
@vary_on_headers("HX-Request")
def vincular(request):
    """Vincular otra cuenta (USR-VNC-CTA, ventana ``link`` del prototipo): pide el email y la contraseña de la otra
    cuenta (reglas 1 y 7).

    GET: la ventana, sin cambiar nada. POST: ``vincular_cuenta``; si sale bien, vuelve a Mi perfil con un aviso;
    si se rechaza, la ventana vuelve con el motivo (el mensaje genérico de SEG-06 no dice qué dato falló) y sin
    la contraseña escrita. Un error de otra clase (PermissionDenied) da el 403 del servicio.
    """
    if request.method == "POST":
        form = FormularioVincularCuenta(request.POST)
        form.is_valid()  # todos los campos son opcionales; las reglas son del servicio
        try:
            otra = vincular_cuenta(
                request.user, form.cleaned_data["email"], form.cleaned_data["contrasena"]
            )
        except ValidationError as error:
            for campo, errores in error.error_dict.items():
                for e in errores:
                    form.add_error(campo if campo in form.fields else None, e)
        else:
            messages.success(
                request,
                f"Cuenta vinculada: {otra.email} ({nombre_visible_del_rol(otra)}). "
                "Ya podés pasar a ella desde el menú de cuenta.",
            )
            return redirect("core:mi_perfil")
    else:
        form = FormularioVincularCuenta()
        if _es_pedido_htmx(request):
            return render(request, "core/_ventana_vincular.html", {"form": form})
    return _render_mi_perfil(
        request, FormularioCambioContrasena(), ventana="vincular", form_vincular=form
    )


@rol_requerido(*ROLES_CON_VINCULOS)
@never_cache
@vary_on_headers("HX-Request")
def desvincular(request, cuenta_id):
    """Desvincular una cuenta del grupo, o salir del grupo con la propia (USR-VNC-CTA reglas 6 y 8; ventana
    ``unlink`` del prototipo, y «Salir del grupo», D-32).

    La ventana pide confirmar: abrirla (GET) no cambia nada y solo existe para la propia cuenta o una de su
    grupo; cualquier otra, un id inexistente o una cuenta sin grupo dan el mismo 403 (``obtener_cuenta_del_grupo``,
    D-32). El cambio es un POST. Si el servicio lo rechaza (por ejemplo, el grupo cambió mientras tanto), la
    ventana vuelve con el motivo.
    """
    cuenta = obtener_cuenta_del_grupo(request.user, cuenta_id)
    propia = cuenta.pk == request.user.pk
    error = None
    if request.method == "POST":
        try:
            desvincular_cuenta(request.user, cuenta.pk)
        except ValidationError as e:
            error = e.messages[0]
        else:
            messages.success(
                request,
                "Saliste del grupo de cuentas vinculadas."
                if propia
                else f"Se desvinculó {cuenta.email}.",
            )
            return redirect("core:mi_perfil")
    elif _es_pedido_htmx(request):
        return render(
            request,
            "core/_ventana_desvincular.html",
            {"cuenta": cuenta, "propia": propia, "error": error},
        )
    return _render_mi_perfil(
        request,
        FormularioCambioContrasena(),
        ventana="desvincular",
        cuenta_ventana=cuenta,
        propia=propia,
        error=error,
    )


@rol_requerido(*ROLES_CON_VINCULOS)
@require_POST
def cambiar_de_cuenta(request):
    """Pasar a otra cuenta vinculada sin volver a identificarse (SEG-09). Solo POST.

    ``cuenta_para_cambiar`` verifica que la cuenta esté en el grupo, activa y sin contraseña temporal. Después,
    ``login()`` con la otra cuenta: Django vacía la sesión anterior y crea una con un identificador nuevo. Hay un
    solo backend de autenticación configurado, así que no hace falta indicarlo. El aviso se agrega DESPUÉS del
    ``login()`` para que quede en la sesión nueva. El cambio no se audita (SEG-14). La persona llega al inicio de
    la otra cuenta, que dice con qué rol opera. Si la cuenta ya no está disponible, aviso de error y vuelta al
    inicio; una cuenta fuera del grupo o un dato mal formado dan el 403.
    """
    try:
        cuenta_id = int(request.POST.get("cuenta_id", ""))
    except ValueError:
        raise PermissionDenied(MENSAJE_FUERA_DEL_GRUPO)
    try:
        cuenta = cuenta_para_cambiar(request.user, cuenta_id)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("core:inicio")
    login(request, cuenta)
    messages.success(
        request, f"Operás como {nombre_visible_del_rol(cuenta)} · {cuenta.get_full_name()}"
    )
    return redirect("core:inicio")


def inicio(request):
    """Inicio de la cuenta: indica con qué rol opera (USR-INI-SES postcondición a, vHome).

    El contenido del panel de cada rol llega con los módulos de negocio. El Administrador no tiene panel:
    va directo a «Cuentas», como en el prototipo (``enter()``; D-16 y D-30).
    """
    if rol_de(request.user) == ADMINISTRADOR:
        return redirect("core:usuarios")
    return render(request, "core/inicio.html")


# ---- Cuentas: consultar y alta (USR-CNS-USR y USR-ALT-USR, tareas 04a y 05a) ----
# El Gerente y el Administrador usan las mismas pantallas, cada uno con su alcance (D-16, D-28): lo
# aplican los servicios. Las plantillas cambian títulos y textos con ``es_administrador``.


@rol_requerido(Usuario.Rol.GERENTE, ADMINISTRADOR)
@vary_on_headers("HX-Request")
def usuarios(request):
    """Lista de cuentas con filtros y búsqueda (USR-CNS-USR, vUsuarios): «Usuarios y seguridad» para el
    Gerente, «Cuentas» para el Administrador.

    Un pedido de HTMX (los filtros) recibe solo la tabla; los demás, la pantalla entera. Un pedido
    de restauración del historial de HTMX necesita la pantalla entera.
    """
    form = FormularioFiltroUsuarios(request.GET, actor=request.user)
    form.is_valid()  # todos los campos son opcionales: siempre hay cleaned_data
    cuentas = consultar_usuarios(
        request.user,
        rol=form.cleaned_data["rol"],
        estado=form.cleaned_data["estado"],
        busqueda=form.cleaned_data["q"],
    )
    parcial = (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )
    plantilla = "core/usuarios/_tabla_usuarios.html" if parcial else "core/usuarios/lista.html"
    return render(request, plantilla, {"form": form, "cuentas": cuentas})


@rol_requerido(Usuario.Rol.GERENTE, ADMINISTRADOR)
def usuario_ficha(request, cuenta_id):
    """Ficha de una cuenta (USR-CNS-USR, vUsuario). Fuera del alcance da 403; un id inexistente, 404.

    Muestra solo los botones de ``acciones_permitidas`` (D-30): nadie llega por un botón a un 403.
    """
    cuenta = obtener_cuenta(request.user, cuenta_id)
    return render(
        request,
        "core/usuarios/ficha.html",
        {
            "cuenta": cuenta,
            "acciones": acciones_permitidas(request.user, cuenta),
            # Regla 3 de USR-CNS-USR y regla 7 de USR-MOD-USR: los vínculos, en solo lectura.
            "vinculadas": cuentas_vinculadas(cuenta, actor=request.user),
        },
    )


@rol_requerido(Usuario.Rol.GERENTE, ADMINISTRADOR)
@never_cache
def usuario_nuevo(request):
    """Alta de una cuenta (USR-ALT-USR, vAlta y vAltaOk): «Nuevo usuario» para el Gerente, «Alta de
    Gerente» para el Administrador (regla 1, D-16).

    La contraseña temporal solo viaja en la respuesta del POST: no se guarda en la sesión ni en la
    base, y ``never_cache`` evita que el navegador la conserve para el botón «Atrás». Límite
    conocido (D-28): recargar «Cuenta creada» reenvía el formulario y da el error de email repetido.
    Regla 2: si ya hay un Gerente activo, el Administrador lo ve antes de completar el formulario y
    «Dar de alta» queda deshabilitado (prototipo vAlta); el servicio lo vuelve a controlar.
    """
    cuenta_inactiva = None
    if request.method == "POST":
        form = FormularioAltaUsuario(request.POST, actor=request.user)
        form.is_valid()  # todos los campos son opcionales; las reglas son del servicio
        try:
            cuenta, contrasena_temporal = alta_usuario(request.user, **form.cleaned_data)
        except ValidationError as error:
            for campo, errores in error.error_dict.items():
                for e in errores:
                    if e.code == "email_de_cuenta_inactiva":
                        # Regla 8: en vez de un error del campo, se ofrece reactivar esa cuenta.
                        cuenta_inactiva = e.params["cuenta"]
                        continue
                    form.add_error(campo if campo in form.fields else None, e)
        else:
            return render(
                request,
                "core/usuarios/alta_ok.html",
                {"cuenta": cuenta, "contrasena_temporal": contrasena_temporal},
            )
    else:
        form = FormularioAltaUsuario(actor=request.user)
    return render(
        request,
        "core/usuarios/alta.html",
        {
            "form": form,
            "cuenta_inactiva": cuenta_inactiva,
            # Regla 8 y D-30: «Reactivar cuenta» solo si quien da de alta puede reactivarla hoy.
            "puede_reactivar": cuenta_inactiva is not None
            and "reactivar" in acciones_permitidas(request.user, cuenta_inactiva),
            "gerente_activo": gerente_activo_que_impide_el_alta(request.user),
        },
    )


# ---- Modificar, restablecer, reactivar y dar de baja (USR-MOD-USR y USR-BAJ-USR, tareas 04b y 05b) ----
# El Gerente y el Administrador usan las mismas pantallas, cada uno con su alcance (D-16, D-28). La ficha
# solo ofrece los botones de ``acciones_permitidas`` (D-30).


@rol_requerido(Usuario.Rol.GERENTE, ADMINISTRADOR)
def usuario_modificar(request, cuenta_id):
    """Modificar los datos de una cuenta (USR-MOD-USR, la parte de edición de vUsuario).

    El formulario no tiene campo de rol (regla 2, D-11): un ``rol`` enviado a mano se ignora. También
    se pueden corregir los datos de una cuenta inactiva (D-28). Al guardar, vuelve a la ficha con un
    aviso breve.
    """
    cuenta = obtener_cuenta(request.user, cuenta_id)
    if request.method == "POST":
        form = FormularioModificarUsuario(request.POST)
        form.is_valid()  # todos los campos son opcionales; las reglas son del servicio
        try:
            modificar_usuario(request.user, cuenta.pk, **form.cleaned_data)
        except ValidationError as error:
            for campo, errores in error.error_dict.items():
                for e in errores:
                    form.add_error(campo if campo in form.fields else None, e)
        else:
            messages.success(request, "Cambios guardados.")
            return redirect("core:usuario", cuenta.pk)
    else:
        form = FormularioModificarUsuario(
            initial={
                "nombre": cuenta.first_name,
                "apellido": cuenta.last_name,
                "email": cuenta.email,
                "telefono": cuenta.telefono,
            }
        )
    return render(request, "core/usuarios/modificar.html", {"cuenta": cuenta, "form": form})


# Servicio que ejecuta el POST de cada acción confirmada sobre una cuenta.
_SERVICIO_DE_ACCION = {
    "restablecer": restablecer_contrasena,
    "reactivar": reactivar_usuario,
    "baja": baja_usuario,
}


def _gestionar_cuenta(request, cuenta_id, accion):
    """Restablecer, reactivar o dar de baja una cuenta, con confirmación previa.

    - GET: no cambia nada; muestra la ventana de confirmación. Un pedido de HTMX recibe solo la
      ventana (se inserta sobre la ficha); los demás, la ficha con la ventana abierta.
    - POST: ejecuta el servicio. Restablecer y reactivar responden con la ficha y la ventana de la
      contraseña temporal, que solo existe en esta respuesta (no se guarda en la sesión ni en la base,
      y ``never_cache`` evita que el navegador la conserve). La baja vuelve a la ficha con un aviso.
      Límite conocido (como en el alta, D-28): recargar la respuesta reenvía el formulario.
    - Si el servicio rechaza la operación (por ejemplo, la cuenta ya cambió de estado), la ventana de
      confirmación vuelve a mostrarse con el motivo.
    - Reactivar un Gerente con otro Gerente activo (regla 5, D-30): la ventana no ofrece confirmar; muestra
      el motivo, con «Ver a <nombre>» y «Cerrar». Un POST manual lo rechaza el servicio igual.
    - Dar de baja la propia cuenta (solo el Administrador, regla 1 de USR-BAJ-USR): se cierra la sesión y se
      vuelve al inicio de sesión con el aviso.
    """
    cuenta = obtener_cuenta(request.user, cuenta_id)
    actor_id = request.user.pk
    contexto = {
        "cuenta": cuenta,
        "accion": accion,
        "acciones": acciones_permitidas(request.user, cuenta),
        # SEG-11: restablecer y reactivar sacan la cuenta de su grupo. Se anota ANTES del POST si lo tenía, para
        # que la ventana de la contraseña temporal pueda decir que salió.
        "tenia_grupo": cuenta.grupo_id is not None,
        "vinculadas": cuentas_vinculadas(cuenta, actor=request.user),
    }
    if accion == "reactivar":
        contexto["gerente_activo"] = gerente_activo_que_impide_reactivar(cuenta)
    if request.method == "POST":
        try:
            resultado = _SERVICIO_DE_ACCION[accion](request.user, cuenta.pk)
        except ValidationError as error:
            contexto["error"] = error.messages[0]
            if accion == "reactivar":
                # Otra operación pudo activar a un Gerente mientras la ventana estaba abierta.
                contexto["gerente_activo"] = gerente_activo_que_impide_reactivar(cuenta)
        else:
            if accion == "baja" and cuenta.pk == actor_id:
                # La baja ya cerró la sesión de esta cuenta (``is_active`` en False); se vacía la sesión
                # en el servidor (SEG-08) y el aviso viaja en una cookie, porque la sesión ya no existe.
                logout(request)
                messages.success(request, "Tu cuenta se dio de baja y se cerró la sesión.")
                return redirect("core:iniciar_sesion")
            if accion == "baja":
                messages.success(
                    request,
                    f"Se dio de baja la cuenta de {cuenta.get_full_name()}. "
                    "Se cerraron sus sesiones abiertas.",
                )
                return redirect("core:usuario", cuenta.pk)
            cuenta.refresh_from_db()
            contexto["acciones"] = acciones_permitidas(request.user, cuenta)
            # La ficha que queda detrás de la ventana muestra los vínculos de ahora (la cuenta salió de su grupo).
            contexto["vinculadas"] = cuentas_vinculadas(cuenta, actor=request.user)
            contexto["contrasena_temporal"] = resultado
    elif request.headers.get("HX-Request") == "true":
        return render(request, "core/usuarios/_ventana_confirmar.html", contexto)
    return render(request, "core/usuarios/ficha.html", contexto)


@rol_requerido(Usuario.Rol.GERENTE, ADMINISTRADOR)
@never_cache
@vary_on_headers("HX-Request")
def usuario_restablecer(request, cuenta_id):
    """Restablecer la contraseña de una cuenta activa (USR-MOD-USR, regla 4)."""
    return _gestionar_cuenta(request, cuenta_id, "restablecer")


@rol_requerido(Usuario.Rol.GERENTE, ADMINISTRADOR)
@never_cache
@vary_on_headers("HX-Request")
def usuario_reactivar(request, cuenta_id):
    """Reactivar una cuenta inactiva (USR-MOD-USR, regla 6)."""
    return _gestionar_cuenta(request, cuenta_id, "reactivar")


@rol_requerido(Usuario.Rol.GERENTE, ADMINISTRADOR)
@never_cache
@vary_on_headers("HX-Request")
def usuario_baja(request, cuenta_id):
    """Dar de baja una cuenta activa (USR-BAJ-USR)."""
    return _gestionar_cuenta(request, cuenta_id, "baja")
