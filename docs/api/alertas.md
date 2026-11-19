# API de alertas (`maestros`)

Para quien programa un módulo que genera alertas (IoT, producción, inventario, comercial) sin leer el código de `maestros`.
Versión de MAE-02a (D-41). Si algo de acá contradice una decisión, manda la decisión: avisá.

Todo está en tres lugares:

| Qué | Dónde |
|---|---|
| Tipos de alerta (`TipoAlerta`, `registrar_tipo_de_alerta`, `tipo_de_alerta`, `codigos_con_destinatario`) | `maestros/alertas.py` |
| Crear, asegurar y resolver alertas | `maestros/servicios/alertas.py` |
| Consultar con alcance (`Alerta.objects.para(usuario)`, `.activas()`, `.no_leidas()`) | `maestros/models.py` |

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
| `origen` | `None`, `Origen.HARDWARE`, `TELEMETRIA`, `SOLICITUD_REVISION` o `MERMA` (ver «Origen») |

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
| `bloquear_invernadero_para_alertas(invernadero_id) -> Invernadero` | Bloquea el invernadero (`FOR NO KEY UPDATE`) y lo devuelve, activo o no. Las de arriba ya la llaman. |

- **Invernadero inactivo:** `crear_alerta_de_evento` y `asegurar_alerta_de_estado` devuelven `None` y **no crean nada** (post e de
  PROD-BAJ-INV: «el invernadero dejó de generar alertas»). No es un error: no lo trates como tal. Resolver siempre se puede.
- **Alertas de estado:** la unicidad (a lo sumo una activa por invernadero, tipo y `clave`) la garantiza el bloqueo del
  invernadero y, de respaldo, un índice parcial de la base. `clave` distingue condiciones del mismo tipo (por ejemplo
  `"lote:12"`); usá `""` si el tipo tiene una sola.
- **Estados** (regla 7 de 8.18): `estado_alerta` (activa/resuelta) y `estado_lectura_alerta` (no leída/leída) son independientes;
  resolver no marca «leída». La resolución carga `fecha_resolucion`.
- **Personal del invernadero:** `sincronizar_alertas_de_personal(invernadero)` mantiene las «invernadero sin {rol} activo». La
  llaman `maestros` y, cuando exista `SistemaIoT` (ver `docs/disparadores.md`), vos al registrarlo o darlo de baja (la del
  Técnico solo cuenta con sistema IoT).

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

`bloquear_invernadero_activo` (de `maestros.servicios.invernaderos`) **no** sirve para esto: lanza `invernadero_inactivo`. Es el
contrato para quien crea algo que *impide* la baja (lotes, órdenes, stock…), no para alertas.

## 4. Origen (restricción C5)

`Alerta` no tiene FK a Hardware, Telemetría, SolicitudRevisión ni Merma (D-38, regla A2 de D-37): **el enlace lo declara tu app**
apuntando a la alerta.

- R053 (Telemetría): `Telemetria.alerta = OneToOneField("maestros.Alerta", null=True, on_delete=PROTECT)`.
- R052 (Hardware, una alerta tiene a lo sumo un hardware): una tabla de enlace en tu app con
  `alerta = OneToOneField("maestros.Alerta")` y `hardware = ForeignKey(Hardware)`.

La C5 («a lo sumo un origen») no la puede garantizar una restricción de la base (abarca tablas de varias apps): se cumple por el
contrato del tipo. El `origen` del `TipoAlerta` dice qué enlace crea tu app, y solo ese, **en la misma transacción** que la alerta.

## 5. Consultar (alcance)

```python
Alerta.objects.para(usuario)                    # el único lugar del alcance
Alerta.objects.para(usuario).activas()
Alerta.objects.para(usuario).activas().no_leidas()   # lo que cuenta la campana
```

El Gerente activo recibe las `para_gerente`; el Agrónomo activo, las suyas; cualquier otro rol (o una cuenta inactiva, o `None`),
ninguna. La pantalla de consulta de alertas (CU-46) y `abrir_alerta` llegan con MAE-02b.

## 6. Auditoría (D-36, D6 de MAE-02)

La API **no audita**. Las alertas van en los `datos` del registro del caso de uso que las dispara, como listas de referencias:

```python
from core.models import referencia
detalle = {"cambios": {...}, "datos": {"alertas_creadas": [referencia(alerta)]}}   # solo las claves que no estén vacías
```

Claves reconocidas: `alertas_creadas`, `alertas_resueltas`, `alertas_traspasadas`. Una alerta de IoT creada fuera de un caso de uso
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
