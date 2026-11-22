# Modelo de dominio · iot

Copia para el repo de «Copia de modelo_dominio»: fichas del bloque «Infraestructura IoT y Telemetría» (`SistemaIoT`, `NodoCentral`,
`Hardware`, `Sensor`, `Actuador`, `TipoActuador`, `Accion`, `Comando`, `ReglaActuacion`, `Telemetria`), `MantenimientoTecnico` y las
reglas 20 y 21 de 8.20 y 4 de 8.22. Versión de la ronda 22, consultada el 21/11/2026, **con la ronda 23 aplicada** (MD-98 a MD-113,
«decididos sin aplicar» en pendientes_MD el 19/11/2026: rigen en el repo aunque el documento del modelo todavía no los tenga, como en
los demás extractos). Cotejado con pendientes_MD hasta MD-113, con los casos de uso IOT-* de «CU extendidos» (Lote 1 v5.6, Lote 2 v3,
Lote 3 v3.2, Lote 4 v2.4) y con el glosario del 19/11/2026. **PROVISORIO.**

Si este archivo y Drive no coinciden, avisá: no elijas en silencio. Si el modelo y un caso de uso no coinciden, **manda el caso de uso**;
las diferencias que ya detectamos están en «Diferencias» al final. Cómo se lleva al código lo que el modelo no dice: **D-72**.

---

## Quién crea qué

| Modelo | App | Tarea |
|---|---|---|
| `Capacidad`, `ComandoCatalogo` (catálogo, cargado por migración) | `iot` | IOT-01 |
| `TipoActuador`, `Accion` (con los seis tipos iniciales por migración) | `iot` | IOT-01 |
| `SistemaIoT`, `Hardware`, `NodoCentral`, `Sensor`, `Actuador`, `EquipoAnunciado` | `iot` | IOT-01 |
| `Telemetria`, `ResumenHorario`, `FotoperiodoDiario`, `AlertaIot` | `iot` | IOT-01 |
| `Comando`, `ReglaActuacion`, `RegistroComando(Bitacora)` | `iot` | IOT-01 (los modelos); `RegistroComando` en IOT-05, porque necesita `produccion.Bitacora` (PRD-01) |
| Los 14 parámetros IoT de `ConfiguracionOperativa` | `maestros` (migración propia) | IOT-01 |
| `MantenimientoTecnico(OrdenTrabajo)` y la restricción de su prioridad (el valor `mantenimiento` de `OrdenTrabajo.Tipo` lo crea PRD-01, D-67 punto 1) | `iot` y `produccion` | IOT-07 |

IOT-01 crea **todos** los modelos de la tabla salvo los de las dos últimas filas que dependen de `produccion`, en una sola migración
inicial de `iot`, para que el esquema no cambie de tarea en tarea (mismo criterio que INV-01). Las demás tareas agregan comportamiento.

## Convenciones de esta ficha

- Nombres de código según D-05 (snake_case, conservando el sufijo del modelo). Fecha y hora del modelo van juntas en un `DateTimeField`
  (`fechaComando` + `horaComando` → `emitido_en`), como `Alerta`.
- **Bajas:** lógicas. Nunca se borra una fila de negocio. La única excepción es la telemetría vencida por la retención (MD-107) y los
  equipos anunciados que el nodo deja de anunciar (son datos de diseño). Las claves foráneas son `PROTECT`.
- **Textos** recortados al guardar. Los largos que ni el modelo ni los casos de uso fijan los fija esta ficha (columna «Nota»).
- **Comparación de nombres e identificadores:** sin distinguir mayúsculas ni espacios al borde (`Lower` en los índices únicos).
- **Alcance:** el IoT se opera por invernadero (regla 4 de 8.22, reescrita por MD-98, abajo). Cada `QuerySet` del IoT tiene un
  método `para(usuario)` y otro `operables_por(usuario)` (D-28).

---

## Catálogo de capacidades (MD-103)

Contrato con el nodo central (IOT-ALT-TAC, regla 7): sin alta, baja ni modificación; cambia solo con una versión nueva de la API
(`docs/api/nodo/`, lote IoT 2). Es una tabla cargada por migración, **como `TipoEtapa`**.

### `Capacidad`

| Atributo | Valores | Nota |
|---|---|---|
| `codigo` | `encendido`, `nivel`, `posicion` | Único. Fijo |
| `nombre` | «Encendido», «Nivel», «Posición» | |

### `ComandoCatalogo`

| Atributo | Valores | Nota |
|---|---|---|
| `codigo` | `ENCENDER`, `APAGAR`, `FIJAR_NIVEL`, `ABRIR`, `CERRAR`, `FIJAR_POSICION` | Único. Es lo que viaja al nodo |
| `capacidad` | FK a `Capacidad`, `PROTECT` | `ENCENDER` y `APAGAR` → encendido; `FIJAR_NIVEL` → nivel; los otros tres → posición |
| `lleva_valor` | booleano | Verdadero solo en `FIJAR_NIVEL` y `FIJAR_POSICION` |

**Unidades de los valores** (IOT-ALT-TAC, regla 10): lista cerrada **en el código** (`iot/catalogo.py`, `UNIDADES_POR_COMANDO`), no tabla:

| Comando | Unidades (valor → texto) |
|---|---|
| `FIJAR_NIVEL` | `%` → «% (porcentaje de la potencia)»; `rpm` → «rpm (vueltas por minuto)»; `L/min` → «L/min (litros por minuto)» |
| `FIJAR_POSICION` | `%` → «% (porcentaje de apertura)»; `°` → «° (grados)»; `cm` → «cm (centímetros)» |

Estado de un actuador que deja cada comando (para la extensión 6c de IOT-EMT-CMD, «ya está en ese estado»): `ENCENDER` → `encendido`,
`APAGAR` → `apagado`, `ABRIR` → `abierto`, `CERRAR` → `cerrado`; los comandos con valor dejan `nivel:<n>` o `posicion:<n>`. El
contrato de la API fija los mismos textos.

---

## TipoActuador (MD-104)

Bloque IoT. Común a toda la organización: lo administra **solo el Gerente** (MD-98); el Agrónomo lo consulta.

| Atributo | Valores | Nota |
|---|---|---|
| `idTipoActuador` | — | El `id` automático |
| `nombreActuador` | texto | → `nombre_actuador`. Hasta 60 caracteres. Único entre **todos** los tipos, activos o inactivos (`UniqueConstraint(Lower(...))`) |
| (nuevo) `tiempoMinimoEntreComandos` | entero ≥ 0, segundos | → `tiempo_minimo_entre_comandos`. Inicial 60 (a confirmar con el Jardín Botánico) |
| (nuevo) `estadoTipoActuador` | `activo` / `inactivo` | → `estado`. Baja lógica; se reactiva con IOT-MOD-TAC |

| ID | Con | Cardinalidad | En el código |
|---|---|---|---|
| R059 | Accion, composición | TipoActuador → Accion = 1..\* | `Accion.tipo_actuador`. «Al menos una acción **activa**» lo controla el servicio |
| R060 | Actuador | TipoActuador → Actuador = 0..\* | `Actuador.tipo_actuador` |
| ~~R061~~ | ~~ReglaActuacion~~ | — | **Eliminada** (MD-106) |

**Datos iniciales** (migración de datos de IOT-01; IOT-ALT-TAC, regla 5), todos con 60 segundos y activos:

| Tipo | Acciones (nombre · comando · rango y unidad) |
|---|---|
| Ventilador | Encender · `ENCENDER`; Apagar · `APAGAR`; Fijar velocidad · `FIJAR_NIVEL` · 0 a 100 % |
| Bomba | Encender · `ENCENDER`; Apagar · `APAGAR` |
| Luminaria | Encender · `ENCENDER`; Apagar · `APAGAR` |
| Calefactor | Encender · `ENCENDER`; Apagar · `APAGAR` |
| Ventana | Abrir · `ABRIR`; Cerrar · `CERRAR`; Fijar posición · `FIJAR_POSICION` · 0 a 100 % |
| Media sombra | Abrir · `ABRIR`; Cerrar · `CERRAR`; Fijar posición · `FIJAR_POSICION` · 0 a 100 % |

## Accion (MD-103)

| Atributo | Valores | Nota |
|---|---|---|
| `nombreAccion` | texto | → `nombre_accion`. Hasta 40 caracteres. Único dentro del tipo entre las **activas**. Una acción quitada **sin** comandos en su historial se borra (IOT-MOD-TAC, postcondición a): es la única baja física de una fila de negocio, junto con la retención de la telemetría |
| (nuevo) `comando` | FK a `ComandoCatalogo`, `PROTECT` | Obligatorio. Dos acciones **activas** del mismo tipo no usan el mismo comando |
| `requiereValor` | — | **No se guarda**: es `comando.lleva_valor` (MD-103) |
| `unidadValor` | lista de `UNIDADES_POR_COMANDO[comando]`, nula | → `unidad_valor`. Hasta 5 caracteres. Obligatoria si el comando lleva valor; nula si no |
| (nuevo) `valorMinimo`, `valorMaximo` | enteros, nulos | → `valor_minimo`, `valor_maximo`. Obligatorios si el comando lleva valor (y entonces mínimo < máximo); nulos si no |
| (nuevo) `estadoAccion` | `activa` / `inactiva` | → `estado`. Una acción quitada con comandos en su historial queda inactiva (IOT-MOD-TAC) |

| ID | Con | Cardinalidad | En el código |
|---|---|---|---|
| R059 | TipoActuador | Accion → TipoActuador = 1 | `tipo_actuador`, `PROTECT`, `related_name="acciones"` |
| R058 | Comando | Accion → Comando = 0..\* | `Comando.accion` |
| R069 | ReglaActuacion | Accion → ReglaActuacion = 0..\* | `ReglaActuacion.accion` |
| (nueva, MD-102) | Actuador, «incompatible con el nodo» | 0..\* – 0..\* | `Actuador.acciones_incompatibles` |

Restricciones de la base: `CheckConstraint` «unidad, mínimo y máximo, los tres nulos o los tres no nulos, con mínimo < máximo» (que
coincidan con `lleva_valor` lo controla el servicio: está en otra tabla). Índices únicos parciales `(tipo_actuador, Lower(nombre_accion))`
y `(tipo_actuador, comando)`, los dos con `estado = activa`. `CheckConstraint` `accion_rango_segun_unidad` (D-80): con unidad «%», mínimo ≥ 0 y máximo ≤ 100; con «rpm», «L/min» o «cm», mínimo ≥ 0; «°» sin límite fijo; y la unidad es una de las cuatro (más la nula).

---

## SistemaIoT (MD-99)

Parte de un invernadero (R068, composición). Vive en `iot`; la FK al invernadero va acá (D-37 A2).

| Atributo | Valores | Nota |
|---|---|---|
| `estadoSistema` | `activo` / `desconectado` / `inactivo` | → `estado_sistema`. Desconectado se revierte (IOT-ACT-SIS); inactivo es la baja, **definitiva** y en cascada |
| (nuevo) rango de temperatura de la solución | dos `Decimal(4,1)` en °C, nulos | → `temp_solucion_min`, `temp_solucion_max`. Los dos o ninguno; mínimo < máximo (IOT-MOD-SIS, regla 7) |
| (diseño) token del nodo | — | → `token_resumen` (SHA-256 en hexadecimal, 64, único, nulo después de la baja) y `token_generado_en`. El token nunca se guarda (D-70) |
| (diseño) `fecha_baja` | fecha, nula | La de la baja; nula mientras no está inactivo |

| ID | Con | Cardinalidad | En el código |
|---|---|---|---|
| R068 | Invernadero, composición | SistemaIoT → Invernadero = 1; Invernadero → SistemaIoT = 0..1 **sin contar los inactivos** (MD-99) | `invernadero`, FK a `maestros.Invernadero`, `PROTECT`. Índice único parcial `(invernadero)` con `estado_sistema != inactivo` |
| R066 | NodoCentral | 1 – 1 | `Hardware.sistema` con `clase = nodo` (ver Hardware) |
| ~~R067~~ | ~~Comando~~ | — | **Eliminada** (MD-105): el sistema de un comando se deduce por actuador → sistema |

## Hardware (abstracta en el modelo; tabla base en el código, D-72)

Herencia de varias tablas, como `OrdenTrabajo` (D-50): una tabla `Hardware` y una por hija. La columna `clase` dice cuál es.

| Atributo | Valores | Nota |
|---|---|---|
| (nuevo) `clase` | `nodo` / `sensor` / `actuador` | Discriminador. Nunca cambia |
| `modeloHardware` | texto | → `modelo_hardware`. Obligatorio. Hasta 60 caracteres |
| `numeroSerie` | texto, opcional | → `numero_serie`. Hasta 60. **Opcional y no único** (MD-100) |
| `fechaInstalacion` | fecha | → `fecha_instalacion`. Obligatoria; nunca posterior a hoy |
| `estadoHardware` | `activo` / `fuera_de_servicio` / `inactivo` | → `estado_hardware` (MD-100) |
| (nuevo) `identificadorEquipo` | texto, nulo | → `identificador_equipo`. Hasta 64, solo letras, números, `-`, `_`, `.` y `/` (`^[A-Za-z0-9._/-]{1,64}$`). **Obligatorio en sensor y actuador, nulo en el nodo** (MD-100). Solo se corrige si el equipo nunca reportó |
| (diseño) `ultimo_mensaje_en` | fecha y hora, nula | Último mensaje del nodo **sobre este equipo** (lectura, estado o resultado). Nula = «sin confirmar» (regla «Estado actual de un equipo» de IOT-ENT-INF) |
| (diseño) `fecha_baja` | fecha, nula | Nula salvo en inactivo (la muestra la alerta «dispositivo no registrado» de un identificador dado de baja) |

| ID | Con | Cardinalidad | En el código |
|---|---|---|---|
| R064, R065, R066 | NodoCentral / SistemaIoT | Cada equipo es de un nodo; cada nodo, de un sistema | **Una sola FK `sistema`** a `SistemaIoT`, `PROTECT`, en todos los equipos. Como el sistema tiene un solo nodo (R066 = 1 – 1), el nodo de un sensor o actuador es el nodo de su sistema (D-72). R065 pasa a 0..\* (MD-101) |
| R070 | SectorProduccion | Hardware → Sector = 0..1 | `sector`, FK nula a `maestros.SectorProduccion`, `PROTECT`. Nula en el nodo (regla 21 de 8.20) |
| R072 | Insumo | Hardware → Insumo = 1 | `insumo`, FK a `inventario.Insumo`, `PROTECT`. De la categoría `repuestos_de_hardware` (lo controla el servicio) |
| R052 | Alerta | 0..1 – 0..\* | En `AlertaIot.hardware` (abajo) |
| R057 | MantenimientoTecnico | 0..\* | `MantenimientoTecnico.hardware` (IOT-07) |

Restricciones de la base:
- `clase = nodo` ⇔ `identificador_equipo` nulo; `clase = nodo` ⇒ `sector` nulo.
- Índice único parcial `(sistema, Lower(identificador_equipo))` con `estado_hardware != inactivo` e identificador no nulo: **un identificador no se repite entre los equipos no dados de baja del mismo sistema** (MD-100). Un reemplazo puede reusar el de uno dado de baja.
- Índice único parcial `(sistema)` con `clase = nodo`: un nodo por sistema.
- Que el sector sea del invernadero del sistema (regla 21 de 8.20) lo controla el servicio.

### NodoCentral (hija)

| Atributo | Valores | Nota |
|---|---|---|
| `nombreNodo` | texto | → `nombre_nodo`. Obligatorio, hasta 60 |
| `idNodo` | — | Es el `id` |
| (nuevo) `modo` | `remoto` / `local` | Inicial `remoto`. Lo informa el nodo (MD-99) |
| (diseño) `ultima_comunicacion` | fecha y hora, nula | Cada mensaje aceptado la actualiza. Nula = «sin señal» porque nunca se comunicó. **La conectividad no se guarda**: «en línea» si la última comunicación es más reciente que `minutos_sin_comunicacion` |

### Sensor (hija, MD-101)

| Atributo | Valores | Nota |
|---|---|---|
| `tipoVariableSensor` | `temperatura`, `humedad`, `intensidad_luz`, `temperatura_solucion`, `nivel_solucion` | → `tipo_variable_sensor`. Sin fotoperíodo. Cambia solo si el sensor no tiene lecturas (IOT-MOD-HDW, regla 3) |
| `unidadMedidaSensor` | — | **No se guarda**: la fija la variable: °C, % HR, lux, °C y sin unidad para el nivel |
| `valorCalibracionMin`, `valorCalibracionMax` | `Decimal(9,2)`, nulos | Obligatorios salvo en el nivel, donde son nulos; mínimo < máximo (`CheckConstraint`) |
| `nombreSensor` | texto, opcional | → `nombre_sensor`. Hasta 60; vacío si no se indicó. Los casos de uso lo nombran (IOT-ALT-HDW postcondición b, IOT-MOD-HDW regla 2, IOT-CNS-HDW regla 5) pero no lo exigen, y el prototipo no lo tiene: se agrega como opcional (D-61) |
| `idSensor` | — | Es el `id` |

Solo `temperatura`, `humedad` e `intensidad_luz` admiten reglas de actuación (MD-101).

### Actuador (hija, MD-102)

| Atributo | Valores | Nota |
|---|---|---|
| `descripcionActuador` | texto, opcional | → `descripcion_actuador`. Hasta 300 |
| `idActuador` | — | Es el `id` |
| (nuevo) estado informado | texto, nulo | → `estado_informado`, hasta 30 caracteres (`encendido`, `apagado`, `abierto`, `cerrado`, `nivel:<n>`, `posicion:<n>`; ver el catálogo) y `estado_informado_en`. Nulo = «desconocido» |
| (diseño) `cambiado_en_invernadero` | booleano | Verdadero si el último estado informado no lo explica un comando de InfoPonia ejecutado sobre él |
| (nuevo) compatibilidad | `compatible` / `incompatible` / `sin_verificar` | → `compatibilidad`. Inicial `sin_verificar` |

| ID | Con | Cardinalidad | En el código |
|---|---|---|---|
| R060 | TipoActuador | Actuador → TipoActuador = 1 | `tipo_actuador`, `PROTECT`. Cambia solo si el actuador no tiene comandos ni reglas (IOT-MOD-HDW, regla 3) |
| (nueva, MD-102) | Accion, «incompatible con el nodo» | 0..\* – 0..\* | `acciones_incompatibles`, `ManyToManyField` a `Accion` |

### EquipoAnunciado (dato de diseño, MD-102)

Lo que el nodo anunció (IOT-ENT-INF, extensión 1c). Cada anuncio **reemplaza** los equipos anunciados del sistema.

| Atributo | Nota |
|---|---|
| `sistema` | FK a `SistemaIoT`, `CASCADE` |
| `identificador_equipo` | Como en Hardware. Único por sistema (`Lower`) |
| `clase` | `sensor` / `actuador` |
| `comandos` | `ManyToManyField` a `ComandoCatalogo` (vacío en un sensor) |
| `anunciado_en` | Fecha y hora del anuncio |

---

## Telemetria (MD-107)

| Atributo | Valores | Nota |
|---|---|---|
| `idTelemetria` | — | El `id` (`BigAutoField`: es la tabla que más crece) |
| `fechaTelemetria` + `horaTelemetria` | — | → `medida_en`. La de medición que informó el nodo o, si no vino, la de recepción (extensión 3e) |
| `valorMedido` | `Decimal(9,2)`, nulo | → `valor_medido`. Nulo solo en el nivel de la solución |
| (nuevo) `estadoNivelMedido` | `normal` / `bajo`, nulo | → `estado_nivel_medido`. Solo en el nivel |
| `unidadMedidaTelemetria` | texto, nulo | → `unidad_medida_telemetria`. Hasta 10 caracteres. La del sensor al recibirla; nula en el nivel |
| (nuevo) marca de validez | booleano, nulo | → `valida`. Nula en el nivel. Se guarda: no cambia si después cambia la calibración |

| ID | Con | Cardinalidad | En el código |
|---|---|---|---|
| R063 | Sensor | Telemetria → Sensor = 1 | `sensor`, FK a `Sensor`, `PROTECT` |
| R053 | Alerta | 0..1 – 0..1 | En `AlertaIot.telemetria` (D-72) |
| R062 | ReglaActuacion, «dispara» | 0..\* – 0..\* | `ReglaActuacion.telemetrias`, `ManyToManyField` |

Restricciones e índices: `num_nonnulls(valor_medido, estado_nivel_medido) = 1`; `valida` nula ⇔ `estado_nivel_medido` no nulo. Índice
**único** `(sensor, medida_en)`: no hay dos lecturas del mismo sensor en el mismo instante, y así un lote reenviado por el nodo no se
duplica (D-74, punto 6; corregido el 21/11/2026, lote I2a: antes era un índice común).

**Retención (MD-107):** la revisión periódica borra las lecturas con `medida_en` anterior a hoy menos `dias_retencion_telemetria`,
**salvo** las que tienen una `AlertaIot` o están en `ReglaActuacion.telemetrias`. Es la única baja física de una tabla de negocio.

### ResumenHorario y FotoperiodoDiario (datos de diseño, MD-107)

| Modelo | Atributos | Clave |
|---|---|---|
| `ResumenHorario` | `sensor` (FK, `PROTECT`), `hora` (fecha y hora con minutos en 0), `minimo`, `promedio`, `maximo` (`Decimal(9,2)`, nulos si no hubo válidas), `cantidad_lecturas`, `cantidad_invalidas` | Única `(sensor, hora)`. No hay resúmenes del nivel |
| `FotoperiodoDiario` | `sensor` (FK a un sensor de intensidad lumínica), `fecha`, `horas` (`Decimal(4,2)`, de 0 a 24), `incompleto` (booleano) | Única `(sensor, fecha)` |

Ninguno de los dos se borra por la retención.

---

## ReglaActuacion (MD-106)

| Atributo | Valores | Nota |
|---|---|---|
| `condicion` | `supera_maximo` / `baja_del_minimo` / `vuelve_al_rango` | Textos: «supera el máximo del umbral efectivo», «baja del mínimo del umbral efectivo», «vuelve a quedar dentro del umbral efectivo» |
| `aplicarValor` | entero, nulo | → `aplicar_valor`. Obligatorio si el comando de la acción lleva valor, dentro del rango de la acción |
| `tipoVariableRegla` | — | **Eliminado** (MD-106): la variable la da el sensor |
| `estadoRegla` | `activa` / `inactiva` | → `estado_regla` |
| (nuevo) `ultimaEvaluacion` | `cumplida` / `no_cumplida` / `sin_evaluar` | → `ultima_evaluacion`. Inicial `sin_evaluar` |
| (nuevo) `contadorConfirmacion` | entero ≥ 0 | → `contador_confirmacion`. Inicial 0 |

| ID | Con | Cardinalidad | En el código |
|---|---|---|---|
| (nueva) | Sensor | ReglaActuacion → Sensor = 1 | `sensor`, `PROTECT`. No cambia |
| (nueva) | Actuador | ReglaActuacion → Actuador = 1 | `actuador`, `PROTECT`. No cambia |
| R069 | Accion | ReglaActuacion → Accion = 1 | `accion`, `PROTECT`. Una acción activa del tipo del actuador |
| R062 | Telemetria | 0..\* – 0..\* | `telemetrias`, `ManyToManyField` (la lectura que completó la confirmación) |
| ~~R061~~ | ~~TipoActuador~~ | — | **Eliminada** |

Restricciones: índice único parcial `(sensor, condicion, actuador)` con `estado_regla = activa`; `contador_confirmacion >= 0`. Que el
sensor y el actuador sean del mismo sistema lo controla el servicio.

## Comando (MD-105)

| Atributo | Valores | Nota |
|---|---|---|
| `fechaComando` + `horaComando` | — | → `emitido_en` |
| `estadoComando` | `pendiente` / `ejecutado` / `fallido` / `cancelado` | → `estado_comando`. El rechazo del nodo es `fallido` con resultado `rechazado` |
| `valorComando` | entero, nulo | → `valor_comando`. Solo si la acción lleva valor |
| `descripcionComando` | texto, opcional | → `descripcion_comando`. Hasta 300. En un automático, la escribe InfoPonia con la regla |
| (nuevo) `resultadoComando` | `ejecutado` / `fallo` / `rechazado` / `sin_respuesta`, nulo | → `resultado_comando`: el último que informó el nodo o el vencimiento. `detalle_resultado`: texto, hasta 300 |
| (nuevo) intentos | entero ≥ 0 | → `cantidad_intentos`. Inicial 0. Cada retiro suma uno |
| (nuevo) último intento | fecha y hora, nula | → `ultimo_intento_en` |
| `fechaRecepcionComando` + `horaRecepcionComando` | — | → `resuelto_en`, nula. Momento de la resolución (ejecutado, fallido o cancelado) |

| ID | Con | Cardinalidad | En el código |
|---|---|---|---|
| (nueva) | Actuador | Comando → Actuador = 1 | `actuador`, `PROTECT` |
| R058 | Accion | Comando → Accion = 1 | `accion`, `PROTECT` |
| (nueva) | ReglaActuacion | Comando → ReglaActuacion = 0..1 | `regla`, FK nula. Nula = comando manual |
| R050 | Agrónomo | Comando → Agrónomo = 0..1 | `agronomo`, FK nula a `core.Agronomo`. Nula en los automáticos y en los del Gerente (la persona va en la auditoría) |

Restricciones: **índice único parcial `(actuador)` con `estado_comando = pendiente`** (un solo comando pendiente por actuador, también
frente a las reglas: la base lo garantiza). `resuelto_en` nula ⇔ `pendiente`. `cantidad_intentos >= 0`. Índice `(actuador, emitido_en)`.

## RegistroComando (hija de `produccion.Bitacora`, MD-110)

El registro de bitácora de tipo `comando` (`Bitacora.TipoEvento` suma `comando`). Vive en `iot` (A2) y lo crea IOT-05.

| Atributo | Nota |
|---|---|
| `comando` | FK a `Comando`, `PROTECT` |
| `numero_intento` | Entero, nulo. Lleno en un intento fallido o sin respuesta |
| `resultado` | `emitido` / `intento_fallido` / `ejecutado` / `fallido` / `rechazado` / `cancelado` |

Del padre: `invernadero` (el del sistema), `lote` nulo, `responsable` (el Agrónomo o Gerente que lo emitió o canceló; nulo si fue
InfoPonia) y `descripcion_evento` legible («Ventilador norte/sectorA/ventilador: Encender · intento 2 sin respuesta»).

---

## AlertaIot (D-72)

Vínculo de cada alerta del IoT con su sistema y su origen (R052 o R053), como `AlertaComercial` (D-63). Reemplaza, para el IoT, el
`Telemetria.alerta` que sugería `docs/api/alertas.md`, sección 4.

| Atributo | Nota |
|---|---|
| `alerta` | `OneToOneField` a `maestros.Alerta`, `PROTECT` |
| `sistema` | FK a `SistemaIoT`, `PROTECT`. Siempre |
| `hardware` | FK nula a `Hardware` (R052) |
| `telemetria` | FK nula a `Telemetria` (R053) |
| `correo_enviado_en` | Fecha y hora, nula. La carga la revisión periódica al mandar el correo de una alerta crítica (D-71) |
| `intentos_correo` | Entero ≥ 0 |
| `ultimo_mensaje_en` | Fecha y hora, nula. Solo en «dispositivo no registrado»: el último mensaje rechazado con ese identificador. La carga IOT-03 al crear la alerta y en cada rechazo que la encuentra activa; con ella la revisión periódica resuelve la alerta sin mensajes recientes (\*b.3, D-76 punto 3; agregado el 22/11/2026, lote I2b) |

Restricción: `num_nonnulls(hardware, telemetria) <= 1` (C5).

### Tipos de alerta del IoT (MD-108 y MD-109)

Todos con `destinatario = AGRONOMO_O_GERENTE` y `clase = ESTADO` (a lo sumo una activa por invernadero, tipo y clave; se resuelven
solas, nunca a mano). Los registra IOT-01 en `IotConfig.ready()`.

| Código | Nombre visible | Severidad | Origen | Clave |
|---|---|---|---|---|
| `iot_fuera_de_umbral` | Fuera de umbral efectivo | advertencia | `TELEMETRIA` | `sensor:<id>` |
| `iot_fotoperiodo_fuera_de_umbral` | Fuera de umbral efectivo (fotoperíodo) | advertencia | `HARDWARE` | `sensor:<id>` |
| `iot_solucion_fuera_de_rango` | Solución fuera de rango | advertencia | `TELEMETRIA` | `sensor:<id>` |
| `iot_nivel_solucion_bajo` | Nivel de solución bajo | **crítica** | `TELEMETRIA` | `sensor:<id>` |
| `iot_lectura_invalida` | Lectura inválida | advertencia | `HARDWARE` | `hw:<id>` |
| `iot_dispositivo_sin_actividad` | Dispositivo sin actividad | advertencia | `HARDWARE` | `hw:<id>` |
| `iot_dispositivo_en_falla` | Dispositivo en falla | **crítica** | `HARDWARE` | `hw:<id>` |
| `iot_comando_fallido` | Comando fallido | **crítica** | `HARDWARE` | `hw:<id>` |
| `iot_configuracion_incompatible` | Configuración incompatible | advertencia | `HARDWARE` | `hw:<id>` |
| `iot_dispositivo_no_registrado` | Dispositivo no registrado | informativa | `None` | `id:<identificador en minúsculas>` |
| `iot_nodo_sin_comunicacion` | Nodo sin comunicación | **crítica** | `None` | `nodo:<id>` |

El fotoperíodo usa un código propio porque su origen es el sensor y no una lectura: el `TipoAlerta` tiene un solo origen.

---

## MantenimientoTecnico (IOT-07)

Hija de `produccion.OrdenTrabajo` **sin** `ConCapataz` (D-53). En esta ronda solo la crea InfoPonia al fallar un comando
(IOT-RSV-CMD, extensión 4b). Planificarla y concretarla son CU-05 y CU-06, de la etapa 2 (fuera de la ronda; D-73).

| Atributo | Valores | Nota |
|---|---|---|
| `prioridadOrden` | `alta` / `media` / `baja` | Del padre. **Obligatoria** en mantenimiento: `CheckConstraint` por `tipo` en `produccion` (IOT-07) |
| `tipoMantenimiento` | `revision` / `reparacion` / `calibracion` / `reemplazo` / `mantenimiento_general` | → `tipo_mantenimiento` (MD-111). La automática es `revision` |

| ID | Con | Cardinalidad | En el código |
|---|---|---|---|
| R047 | Técnico | 1 | `tecnico`, FK a `core.Tecnico`, `PROTECT` |
| R057 | Hardware | 1..\* | `hardware`, `ManyToManyField` a `Hardware` |
| R048 | Alerta | 0..1 – 0..1 | `alerta`, `OneToOneField` nulo a `maestros.Alerta` |
| R056, R135 | Bitácora, Consumo | — | Etapa 2 (concretar el mantenimiento) |

`OrdenTrabajo.Tipo` ya tiene `mantenimiento` desde PRD-01 (D-67, punto 1). La orden automática: `agronomo` nulo, `invernadero` el del sistema, prioridad `alta`, fecha
programada hoy y la descripción con el comando, la acción, los intentos y el último resultado. Los nombres en el código (`related_name`, la
restricción, las migraciones) y el texto de la descripción están en `docs/casos_de_uso/iot/mantenimiento_automatico.md`, «Modelo y
migraciones» (lote I4; D-79).

---

## Parámetros IoT de ConfiguracionOperativa (MD-112, en `maestros`)

Los agrega IOT-01 con una migración propia en `maestros` (los muestra y edita IOT-04, sección «Módulo IoT» de ADM-MOD-CFG). Todos los
valores iniciales están a confirmar con el Jardín Botánico. Son 14: la histéresis de la temperatura de la solución es un parámetro
propio (decisión del estudiante del 21/11/2026).

| Atributo (en código) | Dominio | Inicial | Para qué |
|---|---|---|---|
| `cant_reintentos_comando` | entero de 0 a 10 | 3 | Intentos de un comando = 1 + este valor |
| `segundos_intervalo_reintento` | entero de 10 a 3600 | 60 | Espera de respuesta y tiempo mínimo entre intentos |
| `hora_inicio_luz` | entero de 0 a 23 | 8 | Horario de luz |
| `hora_fin_luz` | entero de 1 a 24, mayor que el inicio | 18 | Horario de luz |
| `lux_umbral_fotoperiodo` | entero de 1 a 100000 | 1000 | Luz que cuenta para el fotoperíodo |
| `minutos_sin_actividad` | entero de 1 a 1440 | 5 | Sensor sin lecturas |
| `minutos_sin_comunicacion` | entero de 1 a 1440 | 3 | Nodo sin comunicación |
| `minutos_antiguedad_lectura` | entero de 1 a 1440 | 5 | Lectura atrasada |
| `cant_lecturas_confirmacion` | entero de 1 a 10 | 3 | Confirmación de una regla |
| `histeresis_temperatura` | `Decimal(3,1)` de 0 a 10 | 1,0 | °C |
| `histeresis_humedad` | entero de 0 a 30 | 3 | % HR |
| `histeresis_luz` | entero de 0 a 20000 | 2000 | lux |
| `histeresis_temp_solucion` | `Decimal(3,1)` de 0 a 10 | 1,0 | °C |
| `dias_retencion_telemetria` | entero de 1 a 365 | 7 | Retención |

`CheckConstraint` por cada rango y `hora_fin_luz > hora_inicio_luz`. Los edita el Gerente; el Agrónomo los ve en solo lectura en el
panel (IOT-CNS-LEC, regla 6).

---

## Reglas que tocan al IoT

**Regla 4 de 8.22, reescrita por MD-98 (decidido el 18 y el 19/11/2026).** «El IoT se opera por invernadero (R068): cada consulta y
cada acción es sobre un invernadero elegido, nunca sobre todos a la vez. El Agrónomo opera el IoT de los invernaderos activos a su
cargo (R051): telemetría, alertas, reglas de actuación, comandos y mantenimientos técnicos manuales. El Gerente lo opera solo en los
invernaderos sin un Agrónomo activo (sin asignar o con el asignado inactivo), hasta que se asigne uno, y consulta siempre. Los tipos
de actuador no dependen de un invernadero: los administra solo el Gerente y el Agrónomo los consulta. Las alertas de un invernadero
van a su Agrónomo (R049), y van al Gerente activo (R007) solo mientras el invernadero no tenga un Agrónomo activo.» (El mismo texto
está en `docs/modelo/maestros.md`.)

**Regla 20 de 8.20.** El invernadero de un hardware se obtiene por su sistema (en el código, `hardware.sistema.invernadero`).

**Regla 21 de 8.20.** El sector de un hardware es opcional; si lo tiene, es del mismo invernadero que su nodo. Un NodoCentral no tiene sector.

**Umbral efectivo.** Lo calcula `inventario.servicios.variedades.umbral_efectivo` (`docs/api/variedades.md`, «Umbral efectivo»): `iot`
no lo calcula por su cuenta (IOT-ENT-INF, «Requisitos especiales»).

**Reglas nuevas de la ronda 23** (MD-98 a MD-112): están en las fichas de arriba y, completas, en los casos de uso IOT-*. Cada regla de
negocio implementada cita el caso de uso y la regla («# IOT-ENT-INF, regla «Histéresis»»), porque el documento del modelo todavía no
tiene la sección 8.24.

---

## Pendientes de MD y diferencias

| N.º | ID | Qué | Cómo queda en el código |
|---|---|---|---|
| 1 | MD-98 a MD-113 | Ronda 23, decidida sin aplicar | **Aplicada en esta ficha** |
| 2 | MD-100 | El modelo no tiene clase propia para el identificador | Atributo de `Hardware`, nulo en el nodo, con índice único parcial que la base garantiza porque `sistema` está en la misma tabla (D-72) |
| 3 | R064, R065, R066 | Tres asociaciones al nodo y al sistema | Una sola FK `Hardware.sistema` (D-72). El nodo de un equipo es el del sistema |
| 4 | `idSensor`, `idActuador`, `idNodo` | Atributos del diagrama | El `id` de Django. En pantalla, un equipo se nombra por su tipo (variable o tipo de actuador) y su identificador; el sensor, además, por su nombre si lo tiene |
| 5 | `unidadMedidaSensor`, `requiereValor` | Atributos del diagrama | Derivados (MD-101, MD-103): no se guardan |
| 6 | R053 | `Alerta → Telemetría` | En `AlertaIot`, no en una columna de `Telemetria` (D-72) |
| 7 | Capacidad | MD-103: «clase de catálogo» | Tablas `Capacidad` y `ComandoCatalogo` por migración; las unidades, constantes en el código |
| 8 | R056, R135 | Bitácora y consumo del mantenimiento | Etapa 2 (D-73) |
| 9 | Telemetria | El modelo no dice si dos lecturas del mismo sensor pueden tener la misma fecha y hora | Índice único `(sensor, medida_en)` (D-74, punto 6) |
| 10 | AlertaIot | El caso de uso pide resolver «no registrado» sin mensajes recientes, y nada guarda cuándo llegó el último | `AlertaIot.ultimo_mensaje_en` (D-76, punto 3) |
