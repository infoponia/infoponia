# API de alertas (`maestros`)

Para quien programa un módulo que genera alertas (IoT, producción, inventario, comercial) sin leer el código de `maestros`.
Versión de MAE-02b (D-41 y D-43). Si algo de acá contradice una decisión, manda la decisión: avisá.

Todo está en tres lugares:

| Qué | Dónde |
|---|---|
| Tipos de alerta (`TipoAlerta`, `registrar_tipo_de_alerta`, `tipo_de_alerta`, `codigos_con_destinatario`) | `maestros/alertas.py` |
| Crear, asegurar y resolver alertas | `maestros/servicios/alertas.py` |
| Consultar con alcance (`Alerta.objects.para(usuario)`, `.activas()`, `.no_leidas()`) | `maestros/models.py` |
| Consultar y abrir (listado con filtros, detalle y `ItemDeAlerta` de la campana) | `maestros/servicios/alertas.py` (`consultar_alertas`, `filtros_de_alertas`, `detalle_de_alerta`; `enlaces_de_alertas`, de MAE-02d) |
| Enlace de cada alerta a la pantalla de su origen (`Enlace`, `registrar_enlace_de_alerta`; MAE-02d, D-62) | `maestros/extensiones.py` |

`maestros` es de nivel 3: **no conoce tu app**. Vos te registrás en tu `AppConfig.ready()` (regla A4 de D-37) y llamás a esta API.

## 1. Registrar tus tipos

```python
# iot/apps.py
class IotConfig(AppConfig):
    name = "iot"

    def ready(self):
        from maestros.alertas import Clase, Destinatario, Origen, TipoAlerta, registrar_tipo_de_alerta
        from maestros.models import Alerta

        registrar_tipo_de_alerta(TipoAlerta(
            codigo="iot_lectura_fuera_de_rango",     # único, hasta 50 caracteres, con el prefijo de tu app
            nombre="Lectura fuera de rango",
            destinatario=Destinatario.AGRONOMO_O_GERENTE,
            severidad=Alerta.Severidad.CRITICA,
            clase=Clase.EVENTO,
            origen=Origen.TELEMETRIA,                # None si la alerta no tiene origen
        ))
```

- Registrar dos veces **la misma definición** no hace nada (`ready()` puede correr más de una vez). Un código repetido con **otra**
  definición, o de más de 50 caracteres, lanza `ValueError`.
- No hay migración: `Alerta.tipo_alerta` es un texto sin `choices`. Un código no registrado lo rechaza la API con `ValueError`.
- `maestros` registra solo `sin_agronomo`, `sin_capataz`, `sin_vendedor` y `sin_tecnico`.

### Qué define cada tipo

| Campo | Valores |
|---|---|
| `destinatario` | `GERENTE`, `AGRONOMO_O_GERENTE` o `AGRONOMO_Y_GERENTE` (tabla abajo) |
| `severidad` | `Alerta.Severidad.CRITICA`, `ADVERTENCIA` o `INFORMATIVA` (los tres del prototipo; el modelo no los define) |
| `clase` | `Clase.ESTADO` (dura mientras dure la condición; a lo sumo una activa por invernadero, tipo y clave) o `Clase.EVENTO` (una por hecho) |
| `origen` | `None`, `Origen.HARDWARE`, `TELEMETRIA`, `SOLICITUD_REVISION`, `MERMA` y, desde COM-03 (D-62), `ENTREGA`, `SUMINISTRO`, `DETALLE_SUMINISTRO` o `STOCK_COSECHADO` (ver «Origen») |

### Destinatarios (regla 1 de 8.9; reglas 2, 3 y 4 de 8.22; MD-61)

Toda alerta tiene al menos un destinatario: el Gerente (`para_gerente`, R007) y/o el Agrónomo (`agronomo`, R049). Los calcula la
API al crear la alerta, con el Agrónomo del invernadero **en ese momento**. «Agrónomo activo» = el invernadero tiene uno asignado
y su cuenta está activa.

| `destinatario` del tipo | Con Agrónomo activo | Sin Agrónomo activo |
|---|---|---|
| `GERENTE` | `para_gerente=True` | `para_gerente=True` |
| `AGRONOMO_O_GERENTE` | `agronomo=A` | `para_gerente=True` |
| `AGRONOMO_Y_GERENTE` | `agronomo=A`, `para_gerente=True` | `para_gerente=True` |

Cuando después cambia el Agrónomo del invernadero, `modificar_invernadero` mueve las alertas activas (D4 de D-41; vos no hacés
nada): las del saliente pasan al entrante; sin entrante pasan al Gerente (`agronomo=None`, `para_gerente=True`); al asignar un
Agrónomo, las `AGRONOMO_O_GERENTE` que habían ido al Gerente pasan a él y el Gerente deja de recibirlas, las
`AGRONOMO_Y_GERENTE` suman al Agrónomo y el Gerente sigue, y las `GERENTE` no se tocan.

La **baja de la cuenta** del Agrónomo hace lo mismo hacia el Gerente (MD-61, D-43): sus alertas activas pasan a
`agronomo=None, para_gerente=True`, en todos sus invernaderos, activos o no; y **reactivar** su cuenta aplica D4 a los que
sigue teniendo a cargo (D8). Tampoco hacés nada vos: lo hacen `baja_usuario` y `reactivar_usuario` de `core`, por
`core/extensiones.py`.

## 2. Crear y resolver alertas

Todas las funciones de `maestros.servicios.alertas` corren **dentro de la transacción de quien llama** (`transaction.atomic()`).
Ninguna audita: ver «Auditoría». `tipo` es el **código** (`str`) registrado.

```python
from maestros.servicios import alertas
```

| Función | Qué hace |
|---|---|
| `crear_alerta_de_evento(invernadero_id, tipo, descripcion) -> Alerta \| None` | Crea una alerta de evento (activa, no leída). |
| `asegurar_alerta_de_estado(invernadero_id, tipo, clave="", descripcion=None) -> Alerta \| None` | **Idempotente**: devuelve la alerta de estado activa de ese invernadero, tipo y clave; si no hay, la crea. Sin `descripcion`, usa **el nombre del tipo** (no el del invernadero: ya está en la FK y quedaría viejo si se lo renombra; si querés más contexto, pasá tu propia `descripcion`). |
| `resolver_alerta_de_estado(invernadero_id, tipo, clave="") -> Alerta \| None` | Pasa a «resuelta» (con su fecha) la activa de ese tipo y clave. `None` si no había. |
| `resolver_alerta(alerta_id) -> Alerta \| None` | Resuelve una alerta (de evento, por lo general). `None` si ya estaba resuelta; `Http404` si no existe. |
| `abrir_alerta(actor, alerta_id) -> Alerta` | Regla 7 de 8.18: un destinatario (`Alerta.objects.para(actor)`) la abre y su lectura pasa a «leída»; no toca el estado «activa/resuelta» ni audita. `Http404` si no existe y `PermissionDenied` si `actor` no la recibe (sin cambiar nada). Es una sola sentencia condicional: no bloquea el invernadero. |
| `bloquear_invernadero_para_alertas(invernadero_id) -> Invernadero` | Bloquea el invernadero (`FOR NO KEY UPDATE`) y lo devuelve, activo o no. Las de arriba ya la llaman. |

- **Invernadero inactivo:** `crear_alerta_de_evento` y `asegurar_alerta_de_estado` devuelven `None` y **no crean nada** (post e de
  PROD-BAJ-INV: «el invernadero dejó de generar alertas»). No es un error: no lo trates como tal. Resolver siempre se puede.
- **Alertas de estado:** la unicidad (a lo sumo una activa por invernadero, tipo y `clave`) la garantiza el bloqueo del
  invernadero y, de respaldo, un índice parcial de la base. `clave` distingue condiciones del mismo tipo (por ejemplo
  `"lote:12"`); usá `""` si el tipo tiene una sola.
- **Estados** (regla 7 de 8.18): `estado_alerta` (activa/resuelta) y `estado_lectura_alerta` (no leída/leída) son independientes;
  resolver no marca «leída». La resolución carga `fecha_resolucion`.
- **Personal del invernadero:** `sincronizar_alertas_de_personal(invernadero, roles=None)` mantiene las «invernadero sin {rol}
  activo». La llaman `maestros` y, cuando exista `SistemaIoT` (ver `docs/disparadores.md`), vos al registrarlo o darlo de baja (la
  del Técnico solo cuenta con sistema IoT). Con `roles=["capataz"]` (D-43) solo asegura, resuelve y **bloquea** las alertas de esos
  roles: la baja y la reactivación de una cuenta sincronizan solo el rol de la cuenta. `ValueError` con un rol desconocido.

Ejemplo de un servicio de IoT:

```python
def registrar_lectura(telemetria_id, valor):
    with transaction.atomic():
        invernadero = bloquear_invernadero_para_alertas(...)   # ANTES de tus filas (ver «Bloqueos»)
        telemetria = Telemetria.objects.select_for_update(no_key=True).get(pk=telemetria_id)
        ...
        if fuera_de_rango(valor):
            alerta = alertas.crear_alerta_de_evento(
                invernadero.pk, "iot_lectura_fuera_de_rango", f"Temperatura {valor} °C fuera de rango"
            )
            if alerta is not None:                       # None: el invernadero se dio de baja
                telemetria.alerta = alerta               # enlace de origen, en TU app (ver «Origen»)
                telemetria.save(update_fields=["alerta"])
```

## 3. Bloqueos (D-30, D-32, D-40)

Siempre `select_for_update(no_key=True)`. Orden global de `maestros`:

1. las cuentas (`Usuario`), en una consulta y en orden de id;
2. **el invernadero**;
3. **las alertas de ese invernadero**, en orden de id;
4. las filas de las apps altas (las tuyas), después del invernadero y en orden de id.

El invernadero bloqueado es el candado de sus alertas. **Quien crea una alerta bloquea el invernadero antes**; la API lo hace
sola, pero si tu servicio bloquea sus propias filas, llamá a `bloquear_invernadero_para_alertas` **antes** de bloquearlas, o hay
deadlock con `baja_invernadero`. La clave foránea sola no alcanza: el `INSERT` toma `FOR KEY SHARE`, que no choca con el
`FOR NO KEY UPDATE` de la baja, y la baja daría de baja un invernadero que acaba de recibir una alerta.

**Baja y reactivación de una cuenta (D-43).** Primero se bloquea la cuenta (`core`); después `maestros` bloquea **todos** los
invernaderos que la tienen a cargo (activos o no, sin filtrar por estado), en orden de id, y recién después traspasa y
sincroniza sus alertas. `traspasar_alertas_del_agronomo` y `bloquear_alertas_activas` **no** bloquean el invernadero: solo
las alertas, que no ven una que otra transacción creó y no confirmó. Si tu servicio toma una cuenta, tomala antes que el
invernadero.

`bloquear_invernadero_activo` (de `maestros.servicios.invernaderos`) **no** sirve para esto: lanza `invernadero_inactivo`. Es el
contrato para quien crea algo que *impide* la baja (lotes, órdenes, stock…), no para alertas.

## 4. Origen (restricción C5)

`Alerta` no tiene FK a Hardware, Telemetría, SolicitudRevisión ni Merma (D-38, regla A2 de D-37): **el enlace lo declara tu app**
apuntando a la alerta.

- R052 y R053 (Hardware y Telemetría): **el IoT usa una sola tabla de vínculo**, `iot.AlertaIot` (D-72, `docs/modelo/iot.md`), con
  `alerta = OneToOneField("maestros.Alerta")`, el sistema y una FK nula a `Hardware` y otra a `Telemetria` (a lo sumo una), como
  `AlertaComercial` (D-63). `Telemetria` no lleva columna `alerta`. Desde IOT-03, el IoT las crea y las resuelve con `iot/servicios/alertas_iot.py` (`asegurar_alerta_iot` y `resolver_alerta_iot`), que llaman a las funciones de la sección 2 y dejan el `AlertaIot`.

**Orígenes de comercial (D-62, D-63).** `comercial` no agrega columnas a sus clases: guarda el vínculo en su tabla `AlertaComercial`
(`docs/modelo/comercial.md`), con una FK por origen y exactamente una cargada. C5 quedó reescrita como «a lo sumo un origen por alerta», con
la lista completa (confirmación de MD-134).

La C5 («a lo sumo un origen») no la puede garantizar una restricción de la base (abarca tablas de varias apps): se cumple por el
contrato del tipo. El `origen` del `TipoAlerta` dice qué enlace crea tu app, y solo ese, **en la misma transacción** que la alerta.

## 5. Consultar (alcance)

```python
Alerta.objects.para(usuario)                    # el único lugar del alcance
Alerta.objects.para(usuario).activas()
Alerta.objects.para(usuario).activas().no_leidas()   # lo que cuenta la campana
```

El Gerente activo recibe las `para_gerente`; el Agrónomo activo, las suyas; cualquier otro rol (o una cuenta inactiva, o `None`),
ninguna. `abrir_alerta(actor, alerta_id)` (MAE-02b) marca «leída» la que abre un destinatario.

Para listar o mostrar alertas (CU-46, MAE-02c; el panel de IoT, CU-41, las reutiliza) usá estas funciones de
`maestros.servicios.alertas` y no armes la consulta a mano. Son solo lectura: no bloquean, no auditan y no cambian la lectura.

| Función | Qué hace |
|---|---|
| `consultar_alertas(actor, *, invernadero_id=None, tipo=None, tipos=None) -> list[Alerta]` | Las alertas **activas** de `actor` (`para(actor).activas()`), filtradas por invernadero y por tipo (el código; vacío o `None` no filtra) y, **desde MAE-02d**, por varios tipos (`tipos`, una lista o tupla de códigos:
 `None` no filtra, `[]` da `[]`; con `tipo` y `tipos` se cumplen los dos; lo usa el panel del IoT), de la más urgente a la menos (crítica, advertencia, informativa) y, dentro de cada nivel, de la más reciente a la más antigua (con fechas iguales, la de id mayor). Cada alerta trae `severidad` y `nombre_tipo` ya calculados y el invernadero cargado: una sola consulta. Un filtro que no coincide da `[]`, sin error. No filtra por el estado del invernadero. |
| `filtros_de_alertas(actor) -> FiltrosDeAlertas(invernaderos, tipos)` | Las opciones de los filtros: `[(id, nombre)]` y `[(código, nombre)]` de las alertas activas de `actor`. Dos consultas, sin cargar las alertas. |
| `detalle_de_alerta(actor, alerta_id) -> DetalleDeAlerta` | Llama a `abrir_alerta` y devuelve `alerta`, `nombre_tipo`, `severidad`, `era_nueva` (la lectura de antes), `destinatarios` (textos, el Gerente primero), `invernadero_visible` y, desde MAE-02d, `enlace` (el `Enlace` de la sección 8). Abre también una alerta resuelta que `actor` recibe. `Http404` / `PermissionDenied` como `abrir_alerta`. |
| `severidad_efectiva(alerta)`, `nombre_de_tipo(alerta)` | La severidad del tipo registrado y su nombre; si el código ya no está registrado, la severidad guardada y el propio código (MD-109). Las usan también la campana y las pantallas. |

Las pantallas están en `/alertas/` (`alertas:lista`) y `/alertas/<id>/` (`alertas:detalle`); la campana enlaza al detalle, que es
quien marca «leída». Desde MAE-02d, también `/alertas/<id>/ir/` (`alertas:ir`): abre la alerta y redirige a la pantalla de su origen
(sección 8). Abrir el detalle es lo único que cambia algo: el listado y los filtros no (postcondición de CU-46,
propuesta A de MAE-02c).

## 6. Auditoría (D-36, D6 de MAE-02)

La API **no audita**. Las alertas van en los `datos` del registro del caso de uso que las dispara, como listas de referencias:

```python
from core.models import referencia
detalle = {"cambios": {...}, "datos": {"alertas_creadas": [referencia(alerta)]}}   # solo las claves que no estén vacías
```

Claves reconocidas: `alertas_creadas`, `alertas_resueltas`, `alertas_traspasadas`. La baja y la reactivación de una cuenta con
invernaderos a cargo las guardan en los `datos` de su registro (`baja` y `reactivacion`), con esos invernaderos entre los
afectados; `abrir_alerta` no audita. Una alerta de IoT creada fuera de un caso de uso
que audite no deja registro. El texto de la referencia es la descripción de la alerta (por omisión, el nombre del tipo); el invernadero figura entre los afectados del registro.

## 7. Pruebas de tu app

Registrá tipos falsos con el administrador de contexto, que los quita al salir (no contamina el registro global):

```python
from maestros.tests.fabricas import tipo_de_alerta_de_prueba, tipo_falso

with tipo_de_alerta_de_prueba(tipo_falso("prueba_evento", destinatario=Destinatario.GERENTE)):
    alerta = alertas.crear_alerta_de_evento(invernadero.pk, "prueba_evento", "x")
```

`crear_alerta(invernadero, ...)` de las mismas fábricas crea una alerta directo en la base. Las pruebas de concurrencia llevan
`@tag("concurrencia")` y usan `correr_a_la_vez` de `core/tests/concurrencia.py` (`docs/patrones/bloqueos.md`).

## 8. Enlace de una alerta (D-62 con su tercera enmienda; lo crea MAE-02d, lo usan COM-03 en adelante y el IoT)

La campana (`items_de_campana`) y el detalle de la alerta (CU-46) muestran cada alerta con un enlace y un texto debajo del título.
Por omisión, el detalle de la alerta y el nombre de su invernadero. Una app alta cambia eso para sus tipos:

```python
# comercial/apps.py
from maestros import extensiones
extensiones.registrar_enlace_de_alerta(("comercial_periodo_sin_cobertura",), enlaces_de_alertas_de_periodo)

def enlaces_de_alertas_de_periodo(usuario, alertas):     # una consulta para toda la lista
    return {alerta.id: Enlace(url, "Faltan 120 plantas para el 26/11") for ...}
```

- `Enlace = namedtuple("Enlace", "url detalle")`, en `maestros/extensiones.py`. `detalle=None` usa el de omisión.
- Un código de tipo tiene a lo sumo un registrante (`ImproperlyConfigured`; se validan todos los códigos antes de registrar, así
  que un registro con un código tomado no deja los demás a medias). Registrar de nuevo la misma función para el mismo código no hace nada
  (`ready()` puede correr dos veces).. Una alerta que el registrante no devuelve usa el enlace por
  omisión.
- **Nunca un enlace a un 403:** el registrante recibe el usuario y devuelve una pantalla que ese usuario puede abrir (o nada).
- Función de uso: `maestros.servicios.alertas.enlaces_de_alertas(usuario, alertas) -> dict[int, Enlace]`, con todas las claves. Una llamada
  por registrante (nunca una por alerta); lista vacía, `{}` sin consultar la base. **Quien llama pasa cada alerta con su `invernadero` cargado** (`select_related`): el
  enlace por omisión usa su nombre y la función no consulta por alerta. La usan el detalle de la alerta (`DetalleDeAlerta.enlace`:
  la fila «Dónde se atiende», solo con el enlace de una app) y `items_de_campana`, que toma de ahí el `detalle`.
- **La campana** (D-62, tercera enmienda, punto 3): si el enlace es de una app, su `url` es `alertas:ir` (`/alertas/<id>/ir/`: abre la
  alerta, la marca «leída» y redirige al `url` del enlace, nunca fuera del sitio; solo GET —HEAD da 405—, sin caché y con los permisos del detalle; un `url` que no empieza con una sola `/`
  o que es de otro host lleva al detalle). «Enlace de una app» = su `url` es distinto del detalle (`es_enlace_de_app`); si es el de omisión, lleva directo al detalle, que ya la
  abre. Antes se escribía `maestros:alerta_ir`: el nombre real es `alertas:ir`.
- **Por omisión** (ningún registrante para el tipo, o el registrante no devuelve esa alerta), el enlace es el **detalle de la alerta**
  (CU-46, `/alertas/<id>/`) con el nombre del invernadero como texto (segunda enmienda de D-62, 22/11/2026: antes era la ficha del
  invernadero, que el detalle ya enlaza).
- Prueba mínima de cada registrante: con datos (el enlace y el texto esperados para cada rol que recibe la alerta); sin la alerta en la
  lista (`{}` sin consultar la base); sin consultas por alerta (`assertNumQueries` igual con una y con tres).

