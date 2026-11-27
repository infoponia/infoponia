# Carga de la demo (secciones 1 a 14 de ``docs/demo/datos_de_la_demo.md``; tareas DAT-01 y DAT-02 y decisión de la demo, hoy
# ``docs/decisiones/D-01-demo.md``). Una función por sección, en el orden del archivo de datos, y todas corren dentro de UNA transacción:
# si una falla, no queda nada a medias.
#
# Escribe solo a través de los servicios de cada app, con el actor que pide el caso de uso (los mismos que usan las pantallas), con dos
# excepciones por ORM (punto 3 de la decisión): el Gerente (no hay un actor que lo dé de alta en una base recién migrada) y la
# contraseña fija de las 10 cuentas (``alta_usuario`` no recibe contraseña: regla 4 de USR-ALT-USR, SEG-04).
#
# Orden de EJECUCIÓN distinto del orden del archivo (decisión del estudiante, 25/11/2026): 4, 1, 2, 3, 11, 5 a 10, 12, 14 y 13 (los suministros,
# al final: reservan el stock de los lotes y su comprobante sale por correo solo si todo lo anterior anduvo). Las secciones 1 y 2
# exigen un Gerente activo (que nace en la 4) y la carga inicial de stock (7) genera asientos: desde CON-05 (regla 9 de CON-INI-EJE) sin ejercicio
# ninguna operación con asiento se registra, así que la sección 11 inicia la contabilidad (el ejercicio y el asiento de apertura N.º 1) antes de todo lo que asienta.
# La salida se informa en el orden del archivo.
#
# Los secretos (contraseña y base de los correos) entran por ``Contexto`` y no se escriben en ningún mensaje ni archivo.

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from comercial.servicios import clientes as servicios_clientes
from comercial.servicios import suministros as servicios_suministros
from comercial.servicios import vehiculos as servicios_vehiculos
from compras.servicios import proveedores as servicios_proveedores
from contabilidad import cuentas as plan_de_cuentas
from contabilidad.servicios import ejercicios
from core import servicios as servicios_core
from core.models import Gerente, Usuario
from inventario.models import TipoInsumo
from inventario.servicios import ajustes, ciclos, insumos, insumos_invernadero, tipos_de_insumo, variedades
from inventario.servicios.variedades import DatosDeVariedad
from iot.models import Accion, TipoActuador
from iot.servicios import hardware as servicios_hardware
from iot.servicios import reglas as servicios_reglas
from iot.servicios import sistemas as servicios_sistemas
from maestros.models import Localidad, SectorProduccion, TipoEtapa
from maestros.servicios import configuracion, cultivos, invernaderos, perfil, sectores, transportistas
from produccion.servicios import lotes_existentes


class Salteada(Exception):
    """Una sección depende de algo que no existe: se saltea entera y se informa («Salteado: <sección> (falta <qué>)»).
    Se lanza ANTES de escribir nada en la sección (la carga completa corre en una transacción, así que no deja nada a medias)."""


@dataclass
class Contexto:
    """Lo que comparten las secciones: la fecha de hoy, los secretos y lo que va quedando cargado."""

    hoy: date
    base: str  # la parte del correo antes de @gmail.com
    contrasena: str  # nunca se imprime
    cuentas: dict = field(default_factory=dict)  # clave -> cuenta (instancia del rol)
    localidades: dict = field(default_factory=dict)  # nombre -> pk
    invernaderos: dict = field(default_factory=dict)  # nombre -> Invernadero
    categorias: dict = field(default_factory=dict)  # clave -> pk de TipoInsumo
    insumos: dict = field(default_factory=dict)  # nombre de la tabla -> Insumo
    variedades: dict = field(default_factory=dict)  # nombre de la variedad -> Variedad
    clientes: dict = field(default_factory=dict)  # clave -> Cliente
    lotes: dict = field(default_factory=dict)  # clave (LN-1, LN-2, LS-1) -> Lote
    suministros: dict = field(default_factory=dict)  # clave (S-1, S-2) -> Suministro
    avisos: list = field(default_factory=list)  # líneas extra de la salida

    def correo(self, clave):
        """«<base>+<clave>@gmail.com» (en minúsculas, como los guarda el sistema, SEG-01)."""
        return f"{self.base}+{clave}@gmail.com".lower()

    def cuenta(self, clave):
        """La cuenta cargada en la sección 4; si no está, la sección que la necesita se saltea."""
        if clave not in self.cuentas:
            raise Salteada(f"la cuenta {clave} (sección 4)")
        return self.cuentas[clave]

    def invernadero(self, nombre):
        """El invernadero cargado en la sección 5; si no está, se saltea."""
        if nombre not in self.invernaderos:
            raise Salteada(f"el invernadero {nombre} (sección 5)")
        return self.invernaderos[nombre]


# ---------------------------------------------------------------------------------------------------------------------------------
# Datos (copiados tal cual de docs/demo/datos_de_la_demo.md; las fechas se calculan con HOY al cargar)
# ---------------------------------------------------------------------------------------------------------------------------------

# Sección 1
ORGANIZACION = {
    "nombre_organizacion": "Huerta Hidropónica del Paraná",
    "cuit_organizacion": "30712345604",
    "telefono_organizacion": "3764 412345",
    "direccion_organizacion": "Ruta Nacional 12 km 1335, Candelaria, Misiones",
}

# Sección 2 (solo estos cuatro valores; el resto queda en sus valores iniciales)
CONFIGURACION = {
    "dias_pre_reserva_suministro": 7,
    "cant_reintentos_comando": 1,
    "segundos_intervalo_reintento": 10,
    "cant_lecturas_confirmacion": 2,
}

# Sección 3: nombre -> id_georef
LOCALIDADES = {"Candelaria": "54021020", "Posadas": "54028030", "Garupá": "54028010", "Oberá": "54091080"}

# Sección 4: (clave, rol, nombre, apellido, teléfono). El Gerente va primero: es el actor que da de alta a los demás.
CUENTAS = (
    ("gerente1", Usuario.Rol.GERENTE, "Laura", "Benítez", "3764 400001"),
    ("agronomo1", Usuario.Rol.AGRONOMO, "Martín", "Sosa", "3764 400002"),
    ("agronomo2", Usuario.Rol.AGRONOMO, "Paula", "Giménez", "3764 400003"),
    ("capataz1", Usuario.Rol.CAPATAZ, "Diego", "Ramírez", "3764 400004"),
    ("capataz2", Usuario.Rol.CAPATAZ, "Ana", "Duarte", "3764 400005"),
    ("vendedor1", Usuario.Rol.VENDEDOR, "Sofía", "Acosta", "3764 400006"),
    ("transportista1", Usuario.Rol.TRANSPORTISTA, "Jorge", "Medina", "3764 400007"),
    ("transportista2", Usuario.Rol.TRANSPORTISTA, "Carlos", "Núñez", "3764 400008"),
    ("tecnico1", Usuario.Rol.TECNICO, "Lucas", "Ferreyra", "3764 400009"),
    ("contador1", Usuario.Rol.CONTADOR, "Valeria", "Ortiz", "3764 400010"),
)

# Sección 5: (nombre, ruta, kilómetro, lote, localidad, agrónomo, capataz, vendedor, técnico)
INVERNADEROS = (
    ("Norte", "Ruta Nacional 12", "1335", "4", "Candelaria", "agronomo1", "capataz1", "vendedor1", "tecnico1"),
    ("Sur", "Ruta Provincial 105", "8", "11", "Garupá", "agronomo2", "capataz2", "vendedor1", None),
)
# (invernadero, sector, código del tipo de etapa, agujeros)
SECTORES = (
    ("Norte", "Germinación N1", "germinacion", 400),
    ("Norte", "Crecimiento N1", "crecimiento", 600),
    ("Norte", "Maduración N1", "maduracion", 600),
    ("Norte", "Maduración N2", "maduracion", 400),
    ("Sur", "Germinación S1", "germinacion", 300),
    ("Sur", "Crecimiento S1", "crecimiento", 400),
    ("Sur", "Maduración S1", "maduracion", 400),
)
TRANSPORTISTAS_POR_INVERNADERO = (("transportista1", "Norte"), ("transportista2", "Sur"))

# Sección 6: (cultivo, variedad, perfil, temp, humedad, luz, fotoperíodo, postcosecha, peso, (germinación, crecimiento, maduración))
VARIEDADES = (
    ("Lechuga", "Criolla", "hoja_verde", ("16", "27"), ("60", "85"), ("20000", "45000"), ("10", "16"), "7", "250", ("10", "20", "14")),
    ("Lechuga", "Morada", "hoja_verde", ("15", "28"), ("55", "85"), ("20000", "45000"), ("10", "16"), "6", "220", ("10", "20", "14")),
    ("Albahaca", "Genovesa", "hierbas", ("18", "30"), ("50", "80"), ("20000", "45000"), ("12", "16"), "5", "80", ("10", "25", "10")),
)

# Sección 7: categorías nuevas (nombre, consumo directo) e insumos del catálogo (nombre, categoría, unidad, controla vencimiento).
# La clave de la categoría es su nombre o, para las del sistema, su código.
CATEGORIAS = (("Nutrientes", "como_costo_de_los_lotes"), ("Sanidad vegetal", "como_costo_de_los_lotes"))
INSUMOS = (
    ("Bandeja de cartón x 12", "envases", "unidad", False),
    ("Bolsa compostable 30x40", "envases", "unidad", False),
    ("Solución nutritiva A", "Nutrientes", "l", False),
    ("Fungicida biológico", "Sanidad vegetal", "l", True),
    ("Nodo ESP32", "repuestos_de_hardware", "unidad", False),
    ("Sensor DHT22", "repuestos_de_hardware", "unidad", False),
    ("Sensor de luz BH1750", "repuestos_de_hardware", "unidad", False),
    ("Sonda DS18B20", "repuestos_de_hardware", "unidad", False),
    ("Sensor de nivel flotante", "repuestos_de_hardware", "unidad", False),
    ("Ventilador 12 V", "repuestos_de_hardware", "unidad", False),
    ("Motor de ventana", "repuestos_de_hardware", "unidad", False),
)
# La semilla de cada variedad la crea el servicio de la variedad: (nombre en la tabla del archivo, variedad)
SEMILLAS = (
    ("Semilla Lechuga Criolla", "Criolla"),
    ("Semilla Lechuga Morada", "Morada"),
    ("Semilla Albahaca Genovesa", "Genovesa"),
)
PRECIOS_DE_REPUESTOS = {
    "Nodo ESP32": "18000",
    "Sensor DHT22": "6500",
    "Sensor de luz BH1750": "4800",
    "Sonda DS18B20": "3900",
    "Sensor de nivel flotante": "5200",
    "Ventilador 12 V": "15000",
    "Motor de ventana": "27000",
}
# (invernadero, insumo, mínimo, precio de referencia, lotes [(cantidad, días hasta el vencimiento o None)])
EXISTENCIAS = (
    ("Norte", "Semilla Lechuga Criolla", "200", "15.00", [("2000", 90)]),
    ("Norte", "Semilla Lechuga Morada", "200", "18.00", [("1500", 90)]),
    ("Norte", "Bandeja de cartón x 12", "20", "350.00", [("150", None)]),
    ("Norte", "Bolsa compostable 30x40", "50", "80.00", [("400", None)]),
    ("Norte", "Solución nutritiva A", "20", "4200.00", [("12", None)]),  # por debajo del mínimo a propósito
    ("Norte", "Fungicida biológico", "2", "9800.00", [("3", 3), ("5", 120)]),  # el de 3 l vence pronto a propósito
    *(("Norte", nombre, "0", precio, [("2", None)]) for nombre, precio in PRECIOS_DE_REPUESTOS.items()),
    ("Sur", "Semilla Albahaca Genovesa", "150", "22.00", [("1000", 90)]),
    ("Sur", "Bandeja de cartón x 12", "20", "350.00", [("100", None)]),
    ("Sur", "Solución nutritiva A", "15", "4200.00", [("40", None)]),
)

# Sección 8: (tipo, razón social o (nombre, apellido), CUIT, teléfono, especialidades)
PROVEEDORES = (
    ("proveedor1", "juridica", "Agroinsumos Litoral S.A.", "30718889908", "3764 420001", ("Nutrientes", "Sanidad vegetal", "semillas")),
    ("proveedor2", "juridica", "Electrónica Guaraní S.R.L.", "30713334401", "3764 420002", ("repuestos_de_hardware",)),
    ("proveedor3", "fisica", ("Ramón", "Ojeda"), "20334445551", "3764 420003", ("Nutrientes", "envases")),
)

# Sección 9: (clave, tipo, razón social o (nombre, apellido), CUIT, teléfono, calle, número, localidad)
CLIENTES = (
    ("cliente1", "juridica", "Súper Del Parque S.A.", "30714567809", "3764 430001", "Av. Uruguay", "2450", "Posadas"),
    ("cliente2", "juridica", "Restaurante El Mensú S.R.L.", "30711223300", "3764 430002", "Av. Las Heras", "1180", "Garupá"),
    ("cliente3", "fisica", ("Marta", "Villalba"), "27315558889", "3764 430003", "Calle Junín", "1745", "Posadas"),
)

# Sección 10: (patente, tipo, marca, modelo, capacidad en kg, transportista)
VEHICULOS = (
    ("AE123BC", "camioneta", "Toyota", "Hilux", "800", "transportista1"),
    ("AF456DE", "utilitario", "Renault", "Kangoo", "500", "transportista2"),
)

# Sección 12: lotes existentes (PRD-05). (clave, invernadero, variedad, código de la etapa actual, días desde la siembra, días desde el
# ingreso a la etapa, plantas, sector, costo estimado). El actor es el Agrónomo de cada invernadero.
LOTES_EXISTENTES = (
    ("LN-1", "Norte", "Criolla", "maduracion", 32, 2, 300, "Maduración N1", "45000.00"),
    ("LN-2", "Norte", "Morada", "crecimiento", 29, 19, 200, "Crecimiento N1", "24000.00"),
    ("LS-1", "Sur", "Genovesa", "maduracion", 39, 4, 150, "Maduración S1", "18000.00"),
)

# Sección 14: sistema IoT de Norte (actor: agronomo1). El ``modelo`` es obligatorio en el servicio y el archivo de datos no lo traía: se
# tomó del insumo (decisión del estudiante, 25/11/2026).
SISTEMA_IOT = {"nombre": "Nodo Norte", "modelo": "ESP32", "insumo": "Nodo ESP32", "temp_min": "18.0", "temp_max": "24.0"}
# (identificador, nombre, sector o None, insumo, modelo, variable, calibración mín., calibración máx.)
SENSORES = (
    ("norte/sectorA/temperatura", "Temperatura sector A", "Maduración N1", "Sensor DHT22", "DHT22", "temperatura", "-10", "60"),
    ("norte/sectorA/humedad", "Humedad sector A", "Maduración N1", "Sensor DHT22", "DHT22", "humedad", "0", "100"),
    ("norte/sectorA/luz", "Luz sector A", "Maduración N1", "Sensor de luz BH1750", "BH1750", "intensidad_luz", "0", "100000"),
    ("norte/tanque1/temp-solucion", "Temperatura de la solución", None, "Sonda DS18B20", "DS18B20", "temperatura_solucion", "0", "50"),
    # El nivel flotante no lleva calibración: el servicio la ignora.
    ("norte/tanque1/nivel", "Nivel del tanque", None, "Sensor de nivel flotante", "Sensor de nivel flotante", "nivel_solucion", "", ""),
)
# (identificador, descripción, sector, insumo, modelo, tipo de actuador). El actuador no tiene campo de nombre: va en la descripción.
ACTUADORES = (
    ("norte/sectorA/ventilador", "Ventilador sector A", "Maduración N1", "Ventilador 12 V", "Ventilador 12 V", "Ventilador"),
    ("norte/sectorA/ventana", "Ventana sector A", "Maduración N1", "Motor de ventana", "Motor de ventana", "Ventana"),
)
# (identificador del sensor, condición, identificador del actuador, nombre de la acción)
REGLAS = (
    ("norte/sectorA/temperatura", "supera_maximo", "norte/sectorA/ventilador", "Encender"),
    ("norte/sectorA/temperatura", "vuelve_al_rango", "norte/sectorA/ventilador", "Apagar"),
)

# Sección 13: suministros (COM-PCT-SUM). Actor: vendedor1. El día de la primera entrega es HOY + ``dias_primera_entrega``.
# (clave, cliente, duración en meses, incumplimientos tolerados, multa, plazo de pago, indemnización por retraso de pago, variedad,
#  plantas por período, días entre períodos, días hasta la primera entrega, precio fijo, plazo de entrega, indemnización por retraso,
#  cantidad mínima, indemnización por faltante)
SUMINISTROS = (
    ("S-1", "cliente1", "3", "0", "50000,00", "10", "1500,00", "Criolla", "60", "7", 0, "900,00", "1", "2000,00", "55", "300,00"),
    ("S-2", "cliente2", "3", "2", "30000,00", "10", "1500,00", "Morada", "40", "7", 8, "1100,00", "1", "2000,00", "35", "350,00"),
)


# ---------------------------------------------------------------------------------------------------------------------------------
# Secciones
# ---------------------------------------------------------------------------------------------------------------------------------


def _fijar_contrasena(cuenta, contrasena):
    """Deja la contraseña de la variable y sin contraseña temporal (D-18): nadie tiene que cambiarla al entrar.
    Va por ORM porque ningún servicio recibe una contraseña elegida (regla 4 de USR-ALT-USR, SEG-04)."""
    cuenta.set_password(contrasena)
    cuenta.fecha_contrasena_temporal = None
    cuenta.save(update_fields=["password", "fecha_contrasena_temporal"])


def cargar_cuentas(ctx):
    """Sección 4. El Gerente por ORM (no hay actor que lo dé de alta); los otros nueve con ``alta_usuario`` (actor: el Gerente), para que
    queden auditados. Activas, sin contraseña temporal y sin grupo de cuentas vinculadas."""
    for clave, rol, nombre, apellido, telefono in CUENTAS:
        if rol == Usuario.Rol.GERENTE:
            cuenta = Gerente(
                email=ctx.correo(clave), first_name=nombre, last_name=apellido, telefono=telefono, is_active=True
            )
            cuenta.set_password(ctx.contrasena)  # sin contraseña temporal: ``fecha_contrasena_temporal`` queda vacía
            cuenta.save()
        else:
            # La contraseña temporal que devuelve el servicio se descarta sin usarla ni imprimirla.
            cuenta, _ = servicios_core.alta_usuario(
                ctx.cuentas["gerente1"],
                rol,
                nombre,
                apellido,
                ctx.correo(clave),
                telefono,
                acceso=servicios_core.ACCESO_TEMPORAL,
            )
            _fijar_contrasena(cuenta, ctx.contrasena)
        ctx.cuentas[clave] = cuenta
    return f"{len(CUENTAS)} cuentas"


def cargar_organizacion(ctx):
    """Sección 1: el perfil de la organización (ADM-MOD-ORG). Los colores no se tocan."""
    gerente = ctx.cuenta("gerente1")
    perfil.modificar_perfil(gerente, email_organizacion=ctx.correo("organizacion1"), **ORGANIZACION)
    return ORGANIZACION["nombre_organizacion"]


def cargar_configuracion(ctx):
    """Sección 2: solo los cuatro valores de la demo (ADM-MOD-CFG); el resto queda en sus valores iniciales."""
    gerente = ctx.cuenta("gerente1")
    configuracion.modificar_configuracion(gerente, **CONFIGURACION)
    return f"{len(CONFIGURACION)} valores de la configuración operativa"


def cargar_geografia(ctx):
    """Sección 3: no escribe nada; busca las localidades de la migración 0002 de maestros y guarda su pk (los servicios piden la pk,
    no el ``id_georef``)."""
    for nombre, id_georef in LOCALIDADES.items():
        localidad = Localidad.objects.filter(id_georef=id_georef).first()
        if localidad is None:
            raise Salteada(f"la localidad {nombre} (id_georef {id_georef}) de la migración 0002 de maestros")
        ctx.localidades[nombre] = localidad.pk
    return f"{len(LOCALIDADES)} localidades de Misiones (ya cargadas por la migración)"


def cargar_contabilidad(ctx):
    """Sección 11 (CON-INI-EJE, CON-05): la contabilidad se inicia el **primer día del mes de HOY**, con el Contador de la demo como actor, y el asiento de apertura N.º 1 con la caja y el capital
    inicial (1.000.000,00 cada uno: la demo no usaba ningún capital). Desde esa fecha se aceptan asientos manuales y contraasientos; uno con fecha de un mes anterior al inicio se rechaza
    (`fecha_anterior_al_primer_ejercicio`). Los asientos automáticos con una fecha anterior van al ejercicio abierto con la fecha de hoy (D-102)."""
    capital = Decimal("1000000.00")
    asiento = ejercicios.iniciar_ejercicio(
        ctx.cuenta("contador1"), ctx.hoy.replace(day=1), {plan_de_cuentas.CAJA: capital, plan_de_cuentas.CAPITAL_INICIAL: capital}, hoy=ctx.hoy
    )
    ejercicio = asiento.ejercicio
    return f"ejercicio del {ejercicio.fecha_inicio_ejercicio:%d/%m/%Y} al {ejercicio.fecha_cierre_ejercicio:%d/%m/%Y}, con el asiento de apertura N.º 1 (capital inicial de $ 1.000.000,00)"


def cargar_invernaderos_y_sectores(ctx):
    """Sección 5: los invernaderos con su personal (actor: el Gerente), los sectores (actor: el Agrónomo a cargo de cada invernadero) y
    los transportistas de cada invernadero (actor: el Gerente)."""
    gerente = ctx.cuenta("gerente1")
    for clave in ("agronomo1", "agronomo2", "capataz1", "capataz2", "vendedor1", "tecnico1", "transportista1", "transportista2"):
        ctx.cuenta(clave)
    if not ctx.localidades:
        raise Salteada("las localidades (sección 3)")
    tipos = {tipo.codigo: tipo.pk for tipo in TipoEtapa.objects.all()}
    for nombre, ruta, kilometro, lote, localidad, agronomo, capataz, vendedor, tecnico in INVERNADEROS:
        ctx.invernaderos[nombre] = invernaderos.alta_invernadero(
            gerente,
            nombre,
            tipo_direccion="rural",
            localidad_id=ctx.localidades[localidad],
            ruta=ruta,
            kilometro=kilometro,
            lote_rural=lote,
            agronomo_id=ctx.cuentas[agronomo].pk,
            capataz_id=ctx.cuentas[capataz].pk,
            vendedor_id=ctx.cuentas[vendedor].pk,
            tecnico_id=ctx.cuentas[tecnico].pk if tecnico else None,
        )
    for nombre_invernadero, nombre, codigo, agujeros in SECTORES:
        invernadero = ctx.invernaderos[nombre_invernadero]
        sectores.alta_sector(
            invernadero.agronomo,
            invernadero.pk,
            nombre=nombre,
            tipo_etapa_id=tipos[codigo],
            cant_agujeros_total=agujeros,
        )
    for transportista, nombre_invernadero in TRANSPORTISTAS_POR_INVERNADERO:
        transportistas.agregar_transportista(
            gerente, ctx.invernaderos[nombre_invernadero].pk, ctx.cuentas[transportista].pk
        )
    return f"{len(INVERNADEROS)} invernaderos con su personal, {len(SECTORES)} sectores y {len(TRANSPORTISTAS_POR_INVERNADERO)} transportistas"


def cargar_cultivos_y_variedades(ctx):
    """Sección 6: cultivos, variedades con su ciclo y rangos, y la semilla de cada variedad (la crea el propio alta de la variedad).
    Actor: el Agrónomo (cualquiera: el catálogo es de toda la organización)."""
    agronomo = ctx.cuenta("agronomo1")
    cultivos_cargados = {}
    for cultivo, variedad, perfil_familia, temp, humedad, luz, foto, postcosecha, peso, ciclo in VARIEDADES:
        if cultivo not in cultivos_cargados:
            cultivos_cargados[cultivo] = cultivos.alta_cultivo(agronomo, nombre=cultivo)
        datos = DatosDeVariedad(
            nombre=variedad,
            perfil_familia=perfil_familia,
            etapas=(("germinacion", ciclo[0]), ("crecimiento", ciclo[1]), ("maduracion", ciclo[2])),
            temp_ambiente_min=temp[0],
            temp_ambiente_max=temp[1],
            humedad_min=humedad[0],
            humedad_max=humedad[1],
            intensidad_luz_min=luz[0],
            intensidad_luz_max=luz[1],
            fotoperiodo_min=foto[0],
            fotoperiodo_max=foto[1],
            duracion_post_cosecha=postcosecha,
            peso_promedio_planta=peso,
        )
        creada = variedades.alta_variedad(agronomo, cultivos_cargados[cultivo].pk, datos)
        ctx.variedades[variedad] = creada
        semilla = variedades.semilla_de([creada.pk])[creada.pk]
        # La tabla del archivo nombra la semilla; si el sistema la nombró distinto, vale el del sistema (sección 7 del archivo).
        for nombre_de_tabla, nombre_variedad in SEMILLAS:
            if nombre_variedad == variedad:
                ctx.insumos[nombre_de_tabla] = semilla
                if semilla.nombre_insumo != nombre_de_tabla:
                    ctx.avisos.append(f"Aviso: la semilla «{nombre_de_tabla}» del archivo de datos se llama «{semilla.nombre_insumo}» en el sistema.")
    return f"{len(cultivos_cargados)} cultivos, {len(VARIEDADES)} variedades con su ciclo y {len(SEMILLAS)} semillas"


def _cargar_lote_inicial(ctx, actor, invernadero, insumo, cantidad, dias):
    """Un lote con el motivo ``carga_inicial`` (CMP-AJT-STK): admite UN lote por ajuste, así que un insumo con dos lotes lleva dos ajustes."""
    entrada = {"cantidad": cantidad}
    if dias is not None:
        entrada["vencimiento"] = ctx.hoy + timedelta(days=dias)
    resumen = ajustes.calcular_ajuste(actor, invernadero.pk, insumo.pk, ajustes.CARGA_INICIAL, entrada, hoy=ctx.hoy)
    ajustes.confirmar_ajuste(
        actor, invernadero.pk, insumo.pk, ajustes.CARGA_INICIAL, entrada, resumen.huella, hoy=ctx.hoy
    )


def cargar_insumos_y_existencias(ctx):
    """Sección 7: categorías (actor: Agrónomo), insumos del catálogo (actor: Agrónomo), habilitación en cada invernadero con mínimo y
    precio de referencia (actor: el Agrónomo a cargo) y la carga inicial de stock (motivo ``carga_inicial``, mismo actor)."""
    agronomo = ctx.cuenta("agronomo1")
    if not ctx.invernaderos:
        raise Salteada("los invernaderos (sección 5)")
    if len(ctx.insumos) < len(SEMILLAS):
        raise Salteada("las semillas de las variedades (sección 6)")
    # Categorías: las nuevas por servicio; las del sistema se buscan por su código (nunca por el nombre, regla 1 de 8.23).
    for nombre, consumo in CATEGORIAS:
        ctx.categorias[nombre] = tipos_de_insumo.alta_tipo_insumo(agronomo, nombre=nombre, consumo_directo=consumo).pk
    for tipo in TipoInsumo.objects.filter(es_del_sistema=True):
        ctx.categorias[tipo.codigo] = tipo.pk
    for nombre, categoria, unidad, vence in INSUMOS:
        ctx.insumos[nombre] = insumos.alta_insumo(
            agronomo, nombre=nombre, tipo_insumo_id=ctx.categorias[categoria], unidad=unidad, controla_vencimiento=vence
        )
    lotes = 0
    for nombre_invernadero, nombre, minimo, precio, partes in EXISTENCIAS:
        invernadero = ctx.invernaderos[nombre_invernadero]
        a_cargo = invernadero.agronomo
        insumo = ctx.insumos[nombre]
        insumos_invernadero.habilitar_insumo(a_cargo, insumo.pk, invernadero.pk, Decimal(minimo), Decimal(precio))
        for cantidad, dias in partes:
            _cargar_lote_inicial(ctx, a_cargo, invernadero, insumo, cantidad, dias)
            lotes += 1
    return (
        f"{len(CATEGORIAS)} categorías, {len(INSUMOS) + len(SEMILLAS)} insumos, {len(EXISTENCIAS)} habilitaciones y {lotes} lotes de la carga inicial"
    )


def cargar_proveedores(ctx):
    """Sección 8: proveedores (CMP-ALT-PRV). Actor: el Gerente. Las especialidades son las categorías de insumo."""
    gerente = ctx.cuenta("gerente1")
    if not ctx.categorias:
        raise Salteada("las categorías de insumo (sección 7)")
    for clave, tipo, nombre, cuit, telefono, especialidades in PROVEEDORES:
        datos = {
            "tipo": tipo,
            "cuit": cuit,
            "email": ctx.correo(clave),
            "telefono": telefono,
            "especialidades": [ctx.categorias[e] for e in especialidades],
        }
        if tipo == "juridica":
            datos["razon_social"] = nombre
        else:
            datos["nombre"], datos["apellido"] = nombre
        servicios_proveedores.alta_proveedor(gerente, datos)
    return f"{len(PROVEEDORES)} proveedores"


def cargar_clientes(ctx):
    """Sección 9: clientes con su dirección urbana (COM-ALT-CLT). Actor: el Vendedor."""
    vendedor = ctx.cuenta("vendedor1")
    if not ctx.localidades:
        raise Salteada("las localidades (sección 3)")
    for clave, tipo, nombre, cuit, telefono, calle, numero, localidad in CLIENTES:
        datos = servicios_clientes.DatosDeCliente(
            tipo_cliente=tipo,
            cuit=cuit,
            telefono=telefono,
            email=ctx.correo(clave),
            direcciones_nuevas=[
                {"tipo_direccion": "urbana", "localidad": ctx.localidades[localidad], "calle": calle, "numero_calle": numero}
            ],
        )
        if tipo == "juridica":
            datos.razon_social = nombre
        else:
            datos.nombre, datos.apellido = nombre
        ctx.clientes[clave] = servicios_clientes.alta_cliente(vendedor, datos)
    return f"{len(CLIENTES)} clientes con su dirección"


def cargar_vehiculos(ctx):
    """Sección 10: vehículos, cada uno con su transportista (COM-ALT-VEH). Actor: el Gerente."""
    gerente = ctx.cuenta("gerente1")
    for *_, transportista in VEHICULOS:
        ctx.cuenta(transportista)  # las guardas, antes de escribir
    for patente, tipo, marca, modelo, capacidad, transportista in VEHICULOS:
        servicios_vehiculos.alta_vehiculo(
            gerente,
            servicios_vehiculos.DatosDeVehiculo(
                patente=patente,
                tipo_vehiculo=tipo,
                marca=marca,
                modelo=modelo,
                capacidad_carga=capacidad,
                transportista_id=ctx.cuentas[transportista].pk,
            ),
        )
    return f"{len(VEHICULOS)} vehículos"


def cargar_lotes_existentes(ctx):
    """Sección 12 (DAT-02): los tres lotes existentes con PRD-05 (``registrar_lote_existente``). Actor: el Agrónomo de cada invernadero.
    Tienen que cargarse ANTES de cualquier siembra normal (D-92 punto 12) y antes de los suministros, que reservan su stock maduro.
    Las fechas de la orden las fija el servicio en hoy (D-103); la de siembra va solo en ``Siembra.fecha_siembra``."""
    if not ctx.invernaderos:
        raise Salteada("los invernaderos (sección 5)")
    if len(ctx.variedades) < len(VARIEDADES):
        raise Salteada("las variedades (sección 6)")
    for clave, nombre_invernadero, nombre_variedad, codigo_etapa, dias_siembra, dias_ingreso, plantas, sector, costo in LOTES_EXISTENTES:
        invernadero = ctx.invernadero(nombre_invernadero)
        variedad = ctx.variedades[nombre_variedad]
        etapa = next(e for e in ciclos.etapas_de([variedad.pk])[variedad.pk] if e.codigo == codigo_etapa)
        sector_elegido = SectorProduccion.objects.get(invernadero=invernadero, nombre_sector=sector)
        ctx.lotes[clave] = lotes_existentes.registrar_lote_existente(
            invernadero.agronomo,
            lotes_existentes.DatosDeLoteExistente(
                invernadero_id=invernadero.pk,
                variedad_id=variedad.pk,
                etapa_id=etapa.etapa_id,
                fecha_siembra=ctx.hoy - timedelta(days=dias_siembra),
                fecha_ingreso_etapa=ctx.hoy - timedelta(days=dias_ingreso),
                cantidad=plantas,
                costo_estimado=Decimal(costo),
                distribucion=((sector_elegido.pk, plantas),),
            ),
            hoy=ctx.hoy,
        )
    return f"{len(LOTES_EXISTENTES)} lotes existentes (LN-1, LN-2 y LS-1)"


def cargar_iot(ctx):
    """Sección 14 (DAT-02): el sistema IoT de Norte con su nodo, 5 sensores, 2 actuadores y 2 reglas. Actor: agronomo1.

    El servicio genera el token SIEMPRE al registrar el sistema y lo devuelve en claro; acá se descarta sin guardarlo ni mostrarlo
    (``sistema, _ = …``): el estudiante lo regenera en la pantalla (IoT · Sistema IoT · Regenerar token). El nodo lo crea el propio
    registro del sistema, no ``alta_hardware``. Nada de esto consume el stock de los repuestos."""
    agronomo = ctx.cuenta("agronomo1")
    norte = ctx.invernadero("Norte")
    for nombre in {SISTEMA_IOT["insumo"], *(s[3] for s in SENSORES), *(a[3] for a in ACTUADORES)}:
        if nombre not in ctx.insumos:
            raise Salteada(f"el repuesto «{nombre}» (sección 7)")
    sistema, _token_descartado = servicios_sistemas.registrar_sistema_iot(
        agronomo,
        servicios_sistemas.DatosDeSistema(
            invernadero_id=norte.pk,
            nombre=SISTEMA_IOT["nombre"],
            modelo=SISTEMA_IOT["modelo"],
            fecha_instalacion=ctx.hoy,
            insumo_id=ctx.insumos[SISTEMA_IOT["insumo"]].pk,
            temp_min=SISTEMA_IOT["temp_min"],
            temp_max=SISTEMA_IOT["temp_max"],
        ),
    )
    equipos = {}

    def sector_de(nombre):
        return SectorProduccion.objects.get(invernadero=norte, nombre_sector=nombre).pk if nombre else None

    for identificador, nombre, sector, insumo, modelo, variable, minimo, maximo in SENSORES:
        equipos[identificador] = servicios_hardware.alta_hardware(
            agronomo,
            sistema.pk,
            servicios_hardware.DatosDeEquipo(
                clase="sensor",
                identificador=identificador,
                modelo=modelo,
                fecha_instalacion=ctx.hoy,
                insumo_id=ctx.insumos[insumo].pk,
                sector_id=sector_de(sector),
                variable=variable,
                nombre_sensor=nombre,
                calibracion_min=minimo,
                calibracion_max=maximo,
            ),
        )
    tipos = {tipo.nombre_actuador: tipo for tipo in TipoActuador.objects.all()}
    for identificador, descripcion, sector, insumo, modelo, tipo in ACTUADORES:
        equipos[identificador] = servicios_hardware.alta_hardware(
            agronomo,
            sistema.pk,
            servicios_hardware.DatosDeEquipo(
                clase="actuador",
                identificador=identificador,
                modelo=modelo,
                fecha_instalacion=ctx.hoy,
                insumo_id=ctx.insumos[insumo].pk,
                sector_id=sector_de(sector),
                tipo_actuador_id=tipos[tipo].pk,
                descripcion=descripcion,
            ),
        )
    for sensor, condicion, actuador, accion in REGLAS:
        servicios_reglas.alta_regla(
            agronomo,
            norte.pk,
            servicios_reglas.DatosDeRegla(
                sensor_id=equipos[sensor].pk,
                actuador_id=equipos[actuador].pk,
                condicion=condicion,
                accion_id=Accion.objects.get(tipo_actuador=equipos[actuador].tipo_actuador, nombre_accion=accion).pk,
            ),
            timezone.now(),
        )
    return f"sistema IoT de Norte con su nodo, {len(SENSORES)} sensores, {len(ACTUADORES)} actuadores y {len(REGLAS)} reglas (sin token a la vista)"


def cargar_suministros(ctx):
    """Sección 13 (DAT-02): S-1 y S-2 con COM-PCT-SUM (``pactar_suministro``). Actor: vendedor1. Se pactan DESPUÉS de los lotes (el pacto
    verifica y reserva stock maduro de la ventana, ahora de 7 días) y al FINAL de la carga: el servicio envía el comprobante por correo
    al cliente, fuera de su transacción, así que solo sale si todo lo anterior anduvo. Las fechas son relativas a HOY: el servicio no
    recibe ``hoy`` y usa la fecha real, la misma que ``ctx.hoy``."""
    vendedor = ctx.cuenta("vendedor1")
    if len(ctx.lotes) < len(LOTES_EXISTENTES):
        raise Salteada("los lotes existentes (sección 12)")
    for _clave, cliente, *_ in SUMINISTROS:
        if cliente not in ctx.clientes:
            raise Salteada(f"el cliente {cliente} (sección 9)")
    for clave, cliente, meses, tolerados, multa, plazo_pago, indemnizacion_pago, variedad, plantas, periodo, dias, precio, plazo, retraso, minima, faltante in SUMINISTROS:
        cliente_cargado = ctx.clientes[cliente]
        direccion = cliente_cargado.direcciones.get()  # DireccionCliente: una sola por cliente en la demo
        ctx.suministros[clave] = servicios_suministros.pactar_suministro(
            vendedor,
            servicios_suministros.DatosDeSuministro(
                cliente_id=str(cliente_cargado.pk),
                duracion=meses,
                tolerados=tolerados,
                multa=multa,
                plazo_pago=plazo_pago,
                indemnizacion_pago=indemnizacion_pago,
                renglones=[
                    servicios_suministros.RenglonDeSuministro(
                        indice=0,
                        variedad_id=str(ctx.variedades[variedad].pk),
                        direccion_id=str(direccion.direccion_id),
                        cantidad=plantas,
                        periodo=periodo,
                        primera_entrega=(ctx.hoy + timedelta(days=dias)).isoformat(),
                        mecanismo="fijo",
                        precio=precio,
                        plazo_entrega=plazo,
                        indemnizacion_retraso=retraso,
                        cantidad_minima=minima,
                        indemnizacion_faltante=faltante,
                    )
                ],
            ),
        )
    reservados = ", ".join(f"{c} con {s.periodos_reservados} períodos reservados" for c, s in ctx.suministros.items())
    return f"{len(SUMINISTROS)} suministros pactados: {reservados}"


# (número y nombre de la sección en el archivo de datos, función). El orden de este diccionario es el de EJECUCIÓN.
SECCIONES = {
    4: ("Cuentas", cargar_cuentas),
    1: ("Organización", cargar_organizacion),
    2: ("Configuración operativa", cargar_configuracion),
    3: ("Geografía", cargar_geografia),
    11: ("Contabilidad", cargar_contabilidad),
    5: ("Invernaderos y sectores", cargar_invernaderos_y_sectores),
    6: ("Cultivos y variedades", cargar_cultivos_y_variedades),
    7: ("Categorías e insumos", cargar_insumos_y_existencias),
    8: ("Proveedores", cargar_proveedores),
    9: ("Clientes", cargar_clientes),
    10: ("Vehículos", cargar_vehiculos),
    # DAT-02: los lotes antes que los suministros (que reservan su stock) y los suministros al final (envían correo).
    12: ("Lotes existentes", cargar_lotes_existentes),
    14: ("Sistema IoT de Norte", cargar_iot),
    13: ("Suministros", cargar_suministros),
}


def cargar(ctx):
    """Corre las secciones 1 a 11 en una sola transacción y devuelve una línea por sección, en el orden del archivo de datos:
    «Cargado: …» o «Salteado: <sección> (falta <qué>)». Si una sección falla con un error de un servicio, no queda nada."""
    lineas = {}
    with transaction.atomic():
        for numero, (nombre, funcion) in SECCIONES.items():
            try:
                lineas[numero] = f"Cargado: {numero}. {nombre} ({funcion(ctx)})"
            except Salteada as motivo:
                lineas[numero] = f"Salteado: {numero}. {nombre} (falta {motivo})"
    return [lineas[numero] for numero in sorted(lineas)]
