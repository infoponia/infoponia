# Cargador de datos de verificación de `produccion` (PRD-03; docs/patrones/datos_de_verificacion.md; CLAUDE.md, «Datos para la verificación a mano»). Lo registra
# ``ProduccionConfig.ready()`` en ``core.verificacion`` (regla A4 de D-37) y lo corre ``manage.py cargar_datos_de_verificacion``. SIEMPRE llama a los servicios de las apps
# (nunca inserciones directas: así quedan la auditoría y las reglas como en una pantalla real). No borra nada, no toca al Administrador ni a ninguna cuenta que no creó
# (las cuentas de prueba son ``<rol>@prueba4.local``: prueba1 y prueba2 son de ``maestros``; prueba3, de ``iot``). Idempotente: lo que ya existe se reutiliza.
#
# Deja lo que pide la «Verificación a mano» de PRD-03, en cada estado que hay que probar:
#   - «Verificación Producción»: con el Agrónomo y el Capataz de prueba, tres sectores (dos de germinación y uno de maduración) y un LOTE ACTIVO con plantas en los dos sectores de
#     germinación (100 plantines sembrados con el servicio real y concretados por el Capataz). El lote ya tiene una merma de 14 plantas: está a una planta de cruzar el umbral
#     del 15 % (pasos 2 y 3) y tiene una transición «a realizar» de 86 plantas, así que una merma más deja la transición sin cobertura (alerta de plantas comprometidas);
#   - los insumos habilitados con consumo directo: «Detergente» (como gasto, 20 L), «Abono verde (prueba)» (como costo de los lotes, 30 kg), «Guantes» (como gasto, en unidades) y «Nutriente líquido (prueba)»
#     (como costo de los lotes, con vencimiento y DOS lotes: 4 L que vencen en 10 días y 10 L que vencen en 40) para el reparto FEFO y su corrección;
#   - «Verificación Producción Vacío»: otro invernadero del mismo Agrónomo, sin sectores, lotes ni insumos (extensiones 4a, 4b y 6b: formularios deshabilitados con su motivo).
# La bitácora tiene entonces la siembra, la transición y la merma para mirar la pestaña «Bitácora». No carga eventos ni aplicaciones: esos los registra quien verifica.
#
# PRD-04 suma lo que pide su «Verificación a mano» (pasos 2 a 9), con los mismos servicios:
#   - «Verificación Fuera de Servicio» (Agrónomo y Capataz de prueba): tres sectores de Germinación (el primero con un LOTE de 40 plantas y una siembra «a realizar» con agujeros
#     comprometidos en él y en el segundo; el segundo con lugar, para reubicar; el tercero vacío, sin plantas ni órdenes: solo cambia de estado) y un sector de Maduración YA
#     puesto fuera de servicio con `poner_fuera_de_servicio` (para volver a servicio o darlo de baja y ver cómo se cierra su registro);
#   - «Verificación Fuera de Servicio Baja»: otro invernadero del mismo Agrónomo, sin lotes ni órdenes ni insumos, con un sector fuera de servicio (para dar de baja el invernadero,
#     que cierra el registro abierto). Se da de baja con la cuenta del Gerente.

from datetime import timedelta

from django.utils import timezone

from core import verificacion
from core.models import Agronomo, Capataz, Gerente, Usuario
from core.servicios import ACCESO_TEMPORAL, alta_usuario, cambiar_contrasena
from core.verificacion import ErrorDeCarga
from inventario.models import Insumo, InsumoInvernadero, TipoInsumo
from inventario.servicios import ajustes, insumos, insumos_invernadero, tipos_de_insumo
from inventario.servicios.variedades import DatosDeVariedad, alta_variedad
from maestros.models import Cultivo, Invernadero, Localidad, SectorProduccion, TipoEtapa, Variedad
from maestros.servicios import cultivos as servicio_cultivos
from maestros.servicios import invernaderos as servicio_invernaderos
from maestros.servicios import sectores as servicio_sectores
from produccion.models import FueraDeServicio, Lote, Merma, OrdenTrabajo, Siembra, TransicionEtapa
from produccion.servicios import mermas, sectores_fuera_de_servicio, siembras, transiciones

CODIGO = "produccion"
SUFIJO = "prueba4.local"
INVERNADERO = "Verificación Producción"
INVERNADERO_VACIO = "Verificación Producción Vacío"
CULTIVO = "Albahaca (prueba)"
VARIEDAD = "Genovesa"
SECTORES = (  # (nombre, tipo de etapa, agujeros)
    ("Germinación A", "germinacion", 100),
    ("Germinación B", "germinacion", 100),
    ("Maduración A", "maduracion", 100),
)
CATEGORIAS = (("Limpieza (prueba)", "como_gasto"), ("Nutrientes (prueba)", "como_costo_de_los_lotes"))
# (nombre, categoría, unidad, controla vencimiento, precio de referencia, lotes: [(cantidad, días hasta el vencimiento o None)])
INSUMOS = (
    ("Detergente", "Limpieza (prueba)", "l", False, "5.00", [("20", None)]),
    ("Guantes", "Limpieza (prueba)", "unidad", False, "2.00", [("10", None)]),
    ("Abono verde (prueba)", "Nutrientes (prueba)", "kg", False, "4.00", [("30", None)]),
    ("Nutriente líquido (prueba)", "Nutrientes (prueba)", "l", True, "6.00", [("4", 10), ("10", 40)]),
)
MERMA_PREVIA = 14  # de 100 plantas: 14 % (el umbral se cruza con más de 15 %)
# PRD-04: los dos invernaderos de la verificación de «Poner fuera de servicio».
INVERNADERO_FDS = "Verificación Fuera de Servicio"
INVERNADERO_FDS_BAJA = "Verificación Fuera de Servicio Baja"
SECTORES_FDS = (
    ("FDS Germinación 1", "germinacion", 100),  # con el lote y la siembra «a realizar»
    ("FDS Germinación 2", "germinacion", 100),  # destino con lugar
    ("FDS Germinación 3", "germinacion", 100),  # vacío: solo cambia de estado
    ("FDS Maduración", "maduracion", 50),  # ya fuera de servicio
)


def _gerente_activo():
    """El Gerente activo, que da de alta cuentas e invernaderos. Sin Gerente no se puede cargar nada: se lo dice."""
    gerente = Gerente.objects.filter(is_active=True).first()
    if gerente is None:
        raise ErrorDeCarga("No hay un Gerente activo: creá uno antes de cargar los datos de verificación.")
    return gerente


def _cuenta(gerente, rol, nombre, contrasena, creado, cuentas):
    """La cuenta ``<rol>@prueba4.local``: se reutiliza si existe; si no, se da de alta con ``alta_usuario`` y se le pone la contraseña de quien trabaja con
    ``cambiar_contrasena`` (la temporal se descarta: nunca se muestra)."""
    email = f"{rol}@{SUFIJO}"
    cuenta = Usuario.objects.filter(email__iexact=email).first()
    if cuenta is None:
        cuenta, _ = alta_usuario(gerente, rol, nombre, "de prueba", email, acceso=ACCESO_TEMPORAL)
        cambiar_contrasena(cuenta, contrasena)
        creado.append(f"Cuenta {email} ({nombre}).")
    cuentas.append(f"{email} · {nombre}")
    return cuenta


def _invernadero(gerente, nombre, agronomo, capataz, creado):
    """El invernadero ``nombre`` (``alta_invernadero``); si ya existe, se reutiliza."""
    invernadero = Invernadero.objects.filter(nombre_invernadero__iexact=nombre).first()
    if invernadero is None:
        localidad = Localidad.objects.filter(nombre_localidad="Garupá").first() or Localidad.objects.first()
        if localidad is None:
            raise ErrorDeCarga("Falta la geografía de Georef (migración 0002 de maestros).")
        invernadero = servicio_invernaderos.alta_invernadero(
            gerente,
            nombre,
            tipo_direccion="urbana",
            localidad_id=localidad.pk,
            calle="Calle 2",
            numero_calle="200",
            agronomo_id=agronomo.pk,
            capataz_id=capataz.pk if capataz else None,
        )
        creado.append(f"Invernadero «{nombre}»{' (Agrónomo y Capataz de prueba)' if capataz else ' (solo el Agrónomo de prueba, sin sectores ni insumos)'}.")
    return invernadero


def _sectores(agronomo, invernadero, creado, definiciones=SECTORES):
    """Los sectores de un invernadero de prueba (``alta_sector``; por omisión los tres de «Verificación Producción»). Devuelve `{nombre: sector}`."""
    resultado = {}
    for nombre, tipo, agujeros in definiciones:
        sector = SectorProduccion.objects.filter(invernadero=invernadero, nombre_sector__iexact=nombre).first()
        if sector is None:
            sector = servicio_sectores.alta_sector(
                agronomo, invernadero.pk, nombre=nombre, tipo_etapa_id=TipoEtapa.objects.get(codigo=tipo).pk, cant_agujeros_total=agujeros
            )
            creado.append(f"Sector «{nombre}» ({tipo}, {agujeros} agujeros).")
        resultado[nombre] = sector
    return resultado


def _variedad(agronomo, creado):
    """Cultivo y variedad con ciclo de dos etapas (germinación y maduración) y su semilla (``alta_cultivo`` y ``alta_variedad``)."""
    cultivo = Cultivo.objects.filter(nombre_cultivo__iexact=CULTIVO).first()
    if cultivo is None:
        cultivo = servicio_cultivos.alta_cultivo(agronomo, nombre=CULTIVO)
        creado.append(f"Cultivo «{CULTIVO}».")
    variedad = Variedad.objects.filter(cultivo=cultivo, nombre_variedad__iexact=VARIEDAD).first()
    if variedad is None:
        variedad = alta_variedad(
            agronomo,
            cultivo.pk,
            DatosDeVariedad(
                nombre=VARIEDAD,
                perfil_familia="hoja_verde",
                etapas=(("germinacion", "7"), ("maduracion", "21")),
                temp_ambiente_min="18",
                temp_ambiente_max="26",
                humedad_min="60",
                humedad_max="80",
                intensidad_luz_min="10000",
                intensidad_luz_max="30000",
                fotoperiodo_min="8",
                fotoperiodo_max="14",
                duracion_post_cosecha="5",
                peso_promedio_planta="150",
            ),
        )
        creado.append(f"Variedad «{CULTIVO} {VARIEDAD}» con su semilla.")
    return variedad


def _cargar_stock(agronomo, invernadero, insumo, lotes):
    """El stock de un insumo habilitado con los ajustes del servicio: el primer lote con «carga inicial» y los siguientes con «recuento físico» (lote nuevo)."""
    hoy = timezone.localdate()
    for n, (cantidad, dias) in enumerate(lotes):
        lote = {"cantidad": cantidad}
        if dias is not None:
            lote["vencimiento"] = (hoy + timedelta(days=dias)).isoformat()
        if n == 0:
            motivo, entrada = ajustes.CARGA_INICIAL, lote
        else:
            motivo, entrada = ajustes.RECUENTO, {"nuevos": [lote]}
        resumen = ajustes.calcular_ajuste(agronomo, invernadero.pk, insumo.pk, motivo, entrada)
        ajustes.confirmar_ajuste(agronomo, invernadero.pk, insumo.pk, motivo, entrada, resumen.huella)


def _insumos(agronomo, invernadero, creado):
    """Las categorías de prueba, los insumos y su habilitación con stock (``alta_tipo_insumo``, ``alta_insumo``, ``habilitar_insumo`` y los ajustes)."""
    tipos = {}
    for nombre, consumo in CATEGORIAS:
        tipo = TipoInsumo.objects.filter(nombre_tipo_insumo__iexact=nombre).first()
        if tipo is None:
            tipo = tipos_de_insumo.alta_tipo_insumo(agronomo, nombre=nombre, consumo_directo=consumo)
            creado.append(f"Categoría «{nombre}» ({consumo.replace('_', ' ')}).")
        tipos[nombre] = tipo
    semillas = []
    for nombre, categoria, unidad, vence, precio, lotes in INSUMOS:
        insumo = Insumo.objects.filter(nombre_insumo__iexact=nombre).first()
        if insumo is None:
            insumo = insumos.alta_insumo(agronomo, nombre=nombre, tipo_insumo_id=tipos[categoria].pk, unidad=unidad, controla_vencimiento=vence)
        elif (insumo.unidad_medida_insumo, insumo.controla_vencimiento, insumo.tipo_insumo.consumo_directo) != (unidad, vence, dict(CATEGORIAS)[categoria]):
            # Un insumo que ya existía con ese nombre (por ejemplo, uno cargado a mano) pero distinto: no se lo pisa ni se carga stock sobre él.
            raise ErrorDeCarga(f"Ya existe un insumo «{nombre}» con otra unidad, otra categoría o distinto control de vencimiento: renombralo o dalo de baja y volvé a correr el comando.")
        existencia = InsumoInvernadero.objects.filter(insumo=insumo, invernadero=invernadero).first()
        if existencia is None:
            existencia = insumos_invernadero.habilitar_insumo(agronomo, insumo.pk, invernadero.pk, "0", precio)
            creado.append(f"Insumo «{nombre}» habilitado.")
        if not existencia.lotes.exists():
            _cargar_stock(agronomo, invernadero, insumo, lotes)
            creado.append(f"Stock de «{nombre}»: {' y '.join(c + ' ' + unidad for c, _ in lotes)}.")
    return semillas


def _semilla_con_stock(agronomo, invernadero, variedad, creado):
    """Habilita la semilla de la variedad y le carga stock con un ajuste de «carga inicial»."""
    semilla = variedad.semilla
    if not InsumoInvernadero.objects.filter(insumo_id=semilla.pk, invernadero=invernadero).exists():
        insumos_invernadero.habilitar_insumo(agronomo, semilla.pk, invernadero.pk, "10", "2.00")
        entrada = {"cantidad": "1000", "vencimiento": (timezone.localdate() + timedelta(days=365)).isoformat()}
        resumen = ajustes.calcular_ajuste(agronomo, invernadero.pk, semilla.pk, ajustes.CARGA_INICIAL, entrada)
        ajustes.confirmar_ajuste(agronomo, invernadero.pk, semilla.pk, ajustes.CARGA_INICIAL, entrada, resumen.huella)
        creado.append("Semilla habilitada con 1.000 unidades.")


def _lote(agronomo, capataz, invernadero, sectores, variedad, creado):
    """Un lote activo de 100 plantas en los dos sectores de germinación: se planifica la siembra (``planificar_siembra``) y la concreta el Capataz (``concretar_siembra``)."""
    if Lote.objects.filter(invernadero=invernadero).exists():
        return Lote.objects.filter(invernadero=invernadero).order_by("pk").first()
    orden = siembras.planificar_siembra(
        agronomo,
        siembras.DatosDeSiembra(
            invernadero_id=invernadero.pk,
            variedad_id=variedad.pk,
            cantidad=100,
            fecha_programada=timezone.localdate() + timedelta(days=1),
            distribucion=((sectores["Germinación A"].pk, 60), (sectores["Germinación B"].pk, 40)),
        ),
    )
    lote = siembras.concretar_siembra(capataz, orden.pk, siembras.DatosDeConcrecion())
    creado.append(f"Lote {lote.codigo} de 100 plantas (60 en «Germinación A» y 40 en «Germinación B»).")
    return lote


def _merma_previa_y_transicion(agronomo, capataz, lote, sectores, creado):
    """La merma de 14 plantas (14 %: a una planta del umbral) y la transición «a realizar» de 86 plantas a «Maduración A»."""
    if not Merma.objects.filter(lote=lote).exists():
        mermas.registrar_merma(
            capataz,
            mermas.DatosDeMerma(lote_id=lote.pk, cantidades=((sectores["Germinación A"].pk, MERMA_PREVIA),), causa="plaga", descripcion="Pulgón (dato de prueba)"),
        )
        creado.append(f"Merma de {MERMA_PREVIA} plantas del lote {lote.codigo}: está a una planta del umbral del 15 %.")
    if not TransicionEtapa.objects.filter(lote=lote, estado_orden=OrdenTrabajo.Estado.A_REALIZAR).exists():
        lote.refresh_from_db()
        transiciones.planificar_transicion(
            agronomo,
            transiciones.DatosDeTransicion(
                lote_id=lote.pk,
                fecha_programada=timezone.localdate() + timedelta(days=3),
                distribucion=((sectores["Maduración A"].pk, lote.cantidad_actual),),
            ),
        )
        creado.append(f"Transición «a realizar» de {lote.cantidad_actual} plantas: una merma más la deja sin cobertura.")


def _fuera_de_servicio(agronomo, sector, motivo, creado):
    """Pone el sector fuera de servicio con el caso de uso (``poner_fuera_de_servicio``) si nunca estuvo: si ya tiene un registro (abierto o cerrado) no se repite, para no
    volver a sacar de servicio un sector que quien verifica ya volvió a activar."""
    if FueraDeServicio.objects.filter(sector=sector).exists():
        return
    sector.refresh_from_db()
    if sector.estado_sector != SectorProduccion.Estado.ACTIVO:
        return
    sectores_fuera_de_servicio.poner_fuera_de_servicio(
        agronomo, sectores_fuera_de_servicio.DatosDeFueraDeServicio(sector_id=sector.pk, motivo=motivo, fecha=timezone.localdate())
    )
    creado.append(f"Sector «{sector.nombre_sector}» puesto fuera de servicio (motivo: {motivo}).")


def _escenario_fds(agronomo, capataz, gerente, variedad, creado):
    """El invernadero «Verificación Fuera de Servicio» (ver el encabezado) y el que sirve para la baja del invernadero (PRD-04)."""
    invernadero = _invernadero(gerente, INVERNADERO_FDS, agronomo, capataz, creado)
    sectores = _sectores(agronomo, invernadero, creado, SECTORES_FDS)
    _semilla_con_stock(agronomo, invernadero, variedad, creado)
    origen = sectores["FDS Germinación 1"]
    if not Lote.objects.filter(invernadero=invernadero).exists():
        orden = siembras.planificar_siembra(
            agronomo,
            siembras.DatosDeSiembra(
                invernadero_id=invernadero.pk,
                variedad_id=variedad.pk,
                cantidad=40,
                fecha_programada=timezone.localdate() + timedelta(days=1),
                distribucion=((origen.pk, 40),),
            ),
        )
        lote = siembras.concretar_siembra(capataz, orden.pk, siembras.DatosDeConcrecion())
        creado.append(f"Lote {lote.codigo} de 40 plantas en «FDS Germinación 1».")
    if not Siembra.objects.filter(invernadero=invernadero, estado_orden=OrdenTrabajo.Estado.A_REALIZAR).exists():
        siembras.planificar_siembra(
            agronomo,
            siembras.DatosDeSiembra(
                invernadero_id=invernadero.pk,
                variedad_id=variedad.pk,
                cantidad=20,
                fecha_programada=timezone.localdate() + timedelta(days=2),
                distribucion=((origen.pk, 12), (sectores["FDS Germinación 2"].pk, 8)),
            ),
        )
        creado.append("Siembra «a realizar» de 20 plantines con agujeros comprometidos en «FDS Germinación 1» (12) y «FDS Germinación 2» (8).")
    _fuera_de_servicio(agronomo, sectores["FDS Maduración"], "Se rompió el canal de retorno (dato de prueba)", creado)

    baja = _invernadero(gerente, INVERNADERO_FDS_BAJA, agronomo, None, creado)
    para_baja = _sectores(agronomo, baja, creado, (("FDS Baja Germinación", "germinacion", 30),))
    _fuera_de_servicio(agronomo, para_baja["FDS Baja Germinación"], "Reparación prolongada (dato de prueba)", creado)


def cargar(contrasena):
    """El cargador de `produccion`: ver el encabezado del archivo. Devuelve un ``ResumenDeCarga``. Nunca imprime ni devuelve la contraseña."""
    creado, cuentas = [], []
    gerente = _gerente_activo()
    agronomo = Agronomo.objects.get(pk=_cuenta(gerente, "agronomo", "Agrónomo", contrasena, creado, cuentas).pk)
    capataz = Capataz.objects.get(pk=_cuenta(gerente, "capataz", "Capataz", contrasena, creado, cuentas).pk)
    invernadero = _invernadero(gerente, INVERNADERO, agronomo, capataz, creado)
    _invernadero(gerente, INVERNADERO_VACIO, agronomo, None, creado)
    sectores = _sectores(agronomo, invernadero, creado)
    variedad = _variedad(agronomo, creado)
    _insumos(agronomo, invernadero, creado)
    _semilla_con_stock(agronomo, invernadero, variedad, creado)
    lote = _lote(agronomo, capataz, invernadero, sectores, variedad, creado)
    _merma_previa_y_transicion(agronomo, capataz, lote, sectores, creado)
    _escenario_fds(agronomo, capataz, gerente, variedad, creado)
    return verificacion.ResumenDeCarga(creado=tuple(creado), cuentas=tuple(cuentas), pendiente=())
