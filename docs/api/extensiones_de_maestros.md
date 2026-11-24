# API · Puntos de extensión de `maestros` para sectores y cultivos (MAE-03)

Contrato para las tareas que crean lo que `maestros` no puede importar (regla A4 de D-37): lotes, órdenes, hardware, semillas.
Se suman a los tres puntos de invernadero de `maestros/extensiones.py` (impedimentos de baja, efectos de baja, traspaso).
Cada app los registra en su `AppConfig.ready()`. **Sin registrantes, cada punto da un resultado neutro** (0, lista vacía) y
`maestros` se prueba con registrantes falsos (`mock.patch.object` sobre las listas de módulo, como los tres primeros).

Contrato común: todo corre **dentro de la transacción** del servicio, **después** de que el servicio tomó el invernadero y los
sectores o el cultivo; un registrante que bloquee filas propias lo hace después y en orden de id (`docs/patrones/bloqueos.md`).

## Sectores

| Registro | Firma de la función registrada | Qué calcula `maestros` con ella | Quién se registra |
|---|---|---|---|
| `registrar_agujeros_de_sector(funcion)` | `funcion(ids) -> dict[int, tuple[int, int]]`: por sector, `(ocupados, comprometidos)`; lo que no figura es `(0, 0)` | `agujeros_de(sectores) -> dict[int, Agujeros]`, con `Agujeros(total, ocupados, comprometidos, libres)`, sumando todos los registrantes. Lo usan MOD (piso de la cantidad y bloqueo del tipo), BAJ y la consulta | `produccion` (PRD-01: ocupaciones de lotes y órdenes de siembra y transición a realizar) |
| `registrar_impedimento_de_baja_de_sector(funcion)` | `funcion(sector) -> list[Impedimento]` (el `namedtuple` ya existente: `codigo`, `texto`, `como_resolver`). Códigos: `agujeros_ocupados`, `agujeros_comprometidos`, `hardware_activo` | `impedimentos_de_baja_de_sector(sector)`: juntos, sin quedarse con el primero (reglas 2 y 3 de PROD-BAJ-SCT) | `produccion` (lotes que ocupan y órdenes que reservan); `iot` (hardware activo) |
| `registrar_contenido_de_sector(funcion)` | `funcion(sectores) -> dict[int, list[Contenido]]`, `Contenido = namedtuple("Contenido", "tipo texto cantidad fecha url")`, con `tipo` en `lote`, `orden` o `hardware` | `contenido_de_sectores(sectores)`: lo que muestra cada tarjeta (regla 3 de PROD-CNS-SCT) | `produccion`, `iot` |
| `registrar_perfil_de_sector(funcion)` | `funcion(ids) -> dict[int, str \| None]`: el perfil familiar de las plantas del sector; `None` si está vacío | `perfiles_de_sectores(ids)`: «Perfil familiar: X» o «Sin plantas: acepta cualquier perfil» | `produccion` |
| `registrar_aviso_de_cambio_de_tipo(funcion)` | `funcion(invernadero, tipo_etapa) -> list[Aviso]`, `Aviso = namedtuple("Aviso", "texto cantidad")`: lo que queda sin un sector activo de ese `tipo_etapa` (lotes que deben pasar por esa etapa con su fecha, siembras a realizar) | `avisos_de_cambio_de_tipo(invernadero, tipo_etapa)`: los registrados más el propio de `maestros` (variedades que dejan de poder sembrarse). Reglas 4 de PROD-MOD-SCT y de PROD-BAJ-SCT | `produccion` |
| `registrar_efecto_de_vuelta_a_servicio(funcion)` | `funcion(actor, sector)`: cierra el registro «Fuera de servicio» abierto con la fecha de hoy y escribe en la bitácora que el sector vuelve a estar activo con el período que estuvo fuera (postcondición b de PROD-MOD-SCT) | `volver_a_servicio_sector(actor, sector_id)` pasa el sector de «fuera de servicio» a «activo» y llama a los registrantes dentro de su transacción | `produccion` (PRD-04) |
| `registrar_efecto_de_baja_de_sector(funcion)` **(nuevo, lote 5, D-51 punto 7)** | `funcion(actor, sector)`: cierra el registro «Fuera de servicio» abierto con la fecha de hoy (postcondición b de PROD-BAJ-SCT). Antes no había dónde engancharlo | `baja_sector(actor, sector_id)` lo llama dentro de su transacción, después del chequeo de impedimentos | `produccion` (PRD-04) |

Quien reserva o libera agujeros (PRD-01 y PRD-02) usa las funciones de `maestros.servicios.sectores`:

```python
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from maestros.servicios.sectores import bloquear_sectores, agujeros_de
invernadero = bloquear_invernadero_activo(invernadero_id)
sectores = bloquear_sectores(invernadero_id, ids)   # FOR NO KEY UPDATE, en orden de id, ya releídos; solo activos
libres = agujeros_de(sectores)                       # ya con sus propias reservas confirmadas
```

`bloquear_sectores` rechaza un sector que no es del invernadero, uno inactivo o uno fuera de servicio (no recibe plantas ni
órdenes) con `ValidationError` de código `sector_no_disponible`. `bloquear_sectores(invernadero_id, ids)` también rechaza un invernadero inactivo (`invernadero_inactivo`).

## Cultivos

| Registro | Firma | Qué calcula `maestros` | Quién se registra |
|---|---|---|---|
| `registrar_semillas_de_cultivo(contar, renombrar)` | `contar(cultivo) -> int` (semillas que cambiarían de nombre); `renombrar(actor, cultivo, nombre_anterior) -> int` (las renombra y escribe su propio log por semilla, acción `modificacion_semilla`, D-36) | `contar_semillas_a_renombrar(cultivo)` y, en `modificar_cultivo`, `renombrar_semillas(...)` (regla 3 de PROD-MOD-CLT) | `inventario` (INV-03) |
| `registrar_uso_de_cultivo(funcion)` | `funcion(cultivo) -> set[int]`: ids de los invernaderos **activos** que usan alguna variedad del cultivo (con la semilla habilitada o con lotes activos; regla 4 de PROD-MOD-CLT) | `invernaderos_que_usan_el_cultivo(cultivo)` | **Solo `inventario` (INV-03)**: arma el conjunto con la semilla habilitada y con los lotes activos que le informa `produccion` por `registrar_uso_de_variedad` (`docs/api/extensiones_de_inventario.md`). `produccion` no se registra acá (corrección del lote 3) |
| `registrar_variedades_de_cultivo(funcion)` | `funcion(actor, cultivos) -> dict[int, VariedadesDelCultivo]`, con `VariedadesDelCultivo = namedtuple("VariedadesDelCultivo", "cabecera cuerpo")`: dos fragmentos de HTML ya armados (`SafeString`) por id de cultivo, `cabecera` (los botones «+ Variedad» de la tarjeta) y `cuerpo` (la tabla de variedades con su ciclo, semilla, estado y acciones). **Es el único registrante** (una segunda llamada a `registrar_...` lanza `RuntimeError`) | `variedades_de_cultivos(actor, cultivos)`: la página «Cultivos y variedades» pone `cabecera` y `cuerpo` en cada tarjeta, y completa con lo propio de `maestros` cualquier cultivo que el registrante no devuelva. **Sin registrante** (hasta INV-03) usa lo propio de `maestros`: cuerpo con el texto «No tiene variedades» (o la lista simple de nombres si las hay, cargadas a mano) y sin botones | `inventario` (INV-03), porque la semilla y sus invernaderos son de `inventario` y `maestros` no puede importarlo (A1) |

## Cultivos: bloqueo (MAE-03)

Quien crea una variedad (INV-03) bloquea la fila del cultivo (`Cultivo.objects.select_for_update(no_key=True)`) **antes** de insertar la variedad: así `baja_cultivo`, que cuenta las variedades activas después de bloquear el cultivo, espera, ve la variedad y se rechaza con `variedades_activas`. `modificar_cultivo` y `reactivar_cultivo` bloquean igual y, recién después, llaman a los registrantes (semillas, en orden de id).

## Prueba mínima de cada registrante (para quien se registra)

Tres pruebas (el registrante de `registrar_variedades_de_cultivo` suma una cuarta: el HTML escapa el nombre de la variedad): devuelve lo esperado con datos; devuelve el neutro sin datos; no hace consultas por fila (una consulta por tabla
para toda la lista de ids).

## Pestañas de la ficha del invernadero (lote 4, PRD-01)

La ficha del invernadero tiene una pestaña «Lotes activos» que `maestros` no puede armar (A1). MAE-03 no definió cómo una app de nivel mayor agrega pestañas; PRD-01 declara este punto en `maestros/extensiones.py`:

| Registro | Firma de la función registrada | Qué hace `maestros` con ella | Quién se registra |
|---|---|---|---|
| `registrar_pestana_de_invernadero(clave, titulo, funcion)` | `funcion(actor, invernadero) -> SafeString \| None`: el HTML ya armado y escapado; `None` si el actor no la ve | `pestanas_de_invernadero(actor, invernadero)`: las pestañas registradas, **en orden de registro**, que la ficha muestra después de las propias. Sin registrantes, ninguna. `clave` única: repetirla lanza `RuntimeError` | `produccion` (PRD-01: `lotes`, «Lotes activos») y, más adelante, `iot` |

Si hace falta tocar más que esto en `maestros` (por ejemplo, cambiar cómo se arma la ficha), frená y avisá: no se hace en PRD-01.
Prueba mínima: pestaña registrada se muestra; sin registrantes no hay pestañas extra; el HTML no se escapa dos veces; sin consultas por fila.

## Lote 5: lo que PRD-04 pide a `maestros` (y nada más)

- **Función nueva** `maestros/servicios/sectores.py::pasar_a_fuera_de_servicio(sector)`: cambia `estado_sector` a «fuera de servicio» y nada más. **No** audita, **no** valida el rol y **no** bloquea: el llamador (`poner_fuera_de_servicio`, de `produccion`) ya bloqueó el sector con `bloquear_sectores` **antes** de llamarla (después del cambio `bloquear_sectores` ya no lo acepta, porque solo toma activos). Prueba mínima en `maestros`: cambia el estado; con un sector que no está activo lanza `ValueError`.
- **Punto nuevo** `registrar_efecto_de_baja_de_sector` (tabla de «Sectores»). Prueba mínima en `maestros`: sin registrantes la baja funciona igual; con uno, se llama una vez, dentro de la transacción y con el sector bloqueado; si lanza, no queda nada hecho.
- Si hace falta tocar más que esto en `maestros`, frená y avisá.

## Transportistas (MAE-05, D-55)

`maestros` guarda a qué invernadero pertenece cada Transportista (`TransportistaInvernadero`). No conoce `Entrega` ni `Vehiculo`,
que vivirán en `comercial`. Por eso pregunta por estos dos puntos, que declara MAE-05 en `maestros/extensiones.py`. Sin
registrantes, los dos dan su resultado neutro.

| Registro | Firma de la función registrada | Qué hace `maestros` con ella | Quién se registra |
|---|---|---|---|
| `registrar_impedimento_de_transportista(funcion)` | `funcion(transportista) -> list[Impedimento]` (el `namedtuple` ya existente). Códigos: `transportista_en_ruta` y `transportista_con_entregas`. Solo lectura: lo llama `maestros` con la cuenta y los invernaderos ya bloqueados | `impedimentos_de_transportista(transportista)`, todos juntos. Lo usan quitar y trasladar (reglas 9 y 10 de PROD-MOD-INV) y la ventana que los informa. Sin registrantes, lista vacía: no se bloquea nada | `comercial` |
| `registrar_logistica_de_transportista(funcion)` | `funcion(transportistas) -> dict[int, Logistica]`, con `Logistica = namedtuple("Logistica", "vehiculo en_ruta entregas_a_realizar url_entregas")`. `vehiculo` es un texto («Camioneta AE123CD · 800 kg») o `None` (sin vehículo); `url_entregas` lleva a sus entregas (COM-ASG-TRP). **Admite un solo registrante**: una segunda llamada lanza `RuntimeError` | `logistica_de(transportistas)`: `None` si no hay registrante; si no, el diccionario. Sin registrante, «Logística» muestra solo el nombre y el estado de la cuenta, sin las columnas de vehículo, situación y entregas. Una sola llamada para toda la lista (sin consultas por fila) | `comercial` |

`core` declara también dos puntos para la cuenta, en `core/extensiones.py`, porque `core` no puede importar `maestros` (A1):

| Registro | Firma | Qué hace `core` con ella | Quién se registra |
|---|---|---|---|
| `registrar_impedimento_de_baja_de_cuenta(funcion)` | `funcion(cuenta) -> list[ImpedimentoDeCuenta]`, con `ImpedimentoDeCuenta = namedtuple("ImpedimentoDeCuenta", "codigo texto como_resolver")` | `baja_usuario` los junta después de bloquear la cuenta y, si hay alguno, rechaza la baja con esos códigos sin cambiar nada (precondición d de USR-BAJ-USR). La ventana de baja los muestra y no ofrece confirmar. Sin registrantes, ninguno | `comercial` (`transportista_en_ruta`) |
| `registrar_datos_de_cuenta(funcion)` | `funcion(cuenta) -> list[DatoDeCuenta]`, con `DatoDeCuenta = namedtuple("DatoDeCuenta", "etiqueta valor nota")`; `valor` es texto plano (se escapa); `nota` es opcional | `datos_de_cuenta(cuenta)`: los muestran la ficha de la cuenta (regla 3 de USR-CNS-USR) y «Mi perfil» (regla 1 de USR-GST-PRF, sin la nota). Solo lectura | `maestros` (MAE-05: el «Invernadero» del Transportista) |

Pruebas mínimas: sin registrantes, quitar y trasladar funcionan y «Logística» no muestra las columnas de `comercial`. Con un
registrante falso, quitar y trasladar se rechazan con su código y no cambian nada. La baja de cuenta con un impedimento falso no
cambia nada. Una segunda `registrar_logistica_de_transportista` lanza `RuntimeError`.

## Estado del IoT del invernadero (IOT-02)

`maestros` muestra en la ficha del invernadero («Ubicación») y en la lista («Con IoT») si el invernadero tiene sistema IoT, y lo usa en
la alerta del Técnico (regla 3 de 8.22) y en el campo del Técnico del alta (regla 5 de PROD-ALT-INV). No puede importar `iot` (A1): hoy
`Invernadero.tiene_sistema_iot()` devuelve siempre `False`. IOT-02 declara este punto en `maestros/extensiones.py` y lo registra desde
`IotConfig.ready()`. Sin registrante, todo queda como hoy.

| Registro | Firma de las funciones registradas | Qué hace `maestros` con ellas | Quién se registra |
|---|---|---|---|
| `registrar_estado_iot(estados, url_de_registro)` | `estados(invernadero_ids) -> dict[int, EstadoIot]`, con `EstadoIot = namedtuple("EstadoIot", "estado url")`: solo los invernaderos con un sistema **no dado de baja**; `estado` es `activo` o `desconectado`; `url` lleva a la pestaña «Sistema IoT» de ese invernadero. `url_de_registro(actor, invernadero) -> str \| None`: el enlace «Registrar sistema IoT», o `None` si el actor no opera el IoT del invernadero. **Admite un solo registrante**: una segunda llamada lanza `RuntimeError` | `estados_iot(ids) -> dict[int, EstadoIot]` (vacío sin registrante; una sola llamada para toda la lista). `Invernadero.tiene_sistema_iot()` pasa a ser `self.pk in estados_iot([self.pk])`. La ficha muestra «Activo», «Desconectado» (con el enlace `url`) o «Sin registrar» (con el enlace de `url_de_registro` si no es `None`); la lista, la marca «Con IoT» donde haya estado | `iot` (IOT-02) |

Los otros dos registrantes de IOT-02 usan puntos que ya existen:

- `registrar_impedimento_de_baja` (invernadero): código `sistema_iot` si el invernadero tiene un sistema no dado de baja; texto «Tiene el
  sistema IoT «{nombre del nodo}».», `como_resolver` «Dalo de baja desde IoT · Sistema IoT.» (precondición h de PROD-BAJ-INV).
- `registrar_impedimento_de_baja_de_sector` y `registrar_contenido_de_sector`: ver la tabla de «Sectores» (código `hardware_activo`, tipo
  `hardware`).

Cambios permitidos en `maestros` (y nada más): el registro y la función `estados_iot` en `maestros/extensiones.py`; el cuerpo de
`Invernadero.tiene_sistema_iot()`; en la ficha y en la lista, mostrar el estado con `estados_iot` (una consulta para toda la lista). Si
hace falta tocar más, frená y avisá.

**Lo que se implementó en IOT-02 (con su razón).** Además de lo anterior: `Invernadero.estado_iot()` (el estado del invernadero, que `tiene_sistema_iot()` y las
pantallas reutilizan), `precargar_estado_iot` en `maestros/servicios/invernaderos.py` y una llamada a ella en `maestros/views.py` (la lista y la ficha). La razón: `roles_faltantes()`,
`equipo()` y la plantilla preguntan por el IoT de cada invernadero, y sin precarga cada pregunta sería una llamada al registrante por fila; con ella, **una sola llamada
al registrante por lista o por ficha**, que deja el estado en cada instancia (si no está cargado, `estado_iot()` consulta). La vista de la lista le pasa a la plantilla una lista en vez de un queryset.

Prueba mínima en `maestros` (registrante falso con `mock.patch.object`): sin registrante,
`tiene_sistema_iot()` es `False` y la ficha dice «Sin registrar» sin enlace; con uno, la ficha muestra el estado y el enlace; la lista
no hace una consulta por fila; una segunda llamada a `registrar_estado_iot` lanza `RuntimeError`.

## Traspaso: lo que se cancela (CMP-02b, D-98)

`ventana de PROD-MOD-INV` (regla 2) informa lo que **recibe** quien entra (`registrar_traspaso`, `contar`). Para lo que se **cancela** o se pierde hay un punto aparte, en `maestros/extensiones.py`:

| Registro | Firma de la función registrada | Qué hace `maestros` con ella | Quién se registra |
|---|---|---|---|
| `registrar_aviso_de_traspaso(funcion)` | `funcion(invernadero, rol, saliente, entrante) -> list[str]`: lo que se cancela o se pierde al cambiar a la persona de ese rol, con o sin entrante. Solo lectura | `avisos_de_traspaso(...)`; `_aviso_de_personal` lo suma como `avisos` de cada cambio y la ventana lo muestra. No llega a la notificación de quien entra | `compras` (los pedidos del Agrónomo saliente) |

`Impedimento` suma `url` (opcional, `None`): las ventanas de baja y de deshabilitación muestran «Ver detalle» si la hay. Prueba mínima: sin registrantes, lista vacía; con uno, se llama una vez por cambio; el aviso aparece con y sin entrante.
