# CON-02 · Núcleo contable: ejercicio, asiento, movimiento, plan de cuentas y el servicio de asientos automáticos

Estado: hecha en la rama, falta el PR | App: contabilidad | Rama: feature/con-02-nucleo-contable | Ronda: Contabilidad 1

Depende de: **USR-11** (el rol Contador y `responsables.py`) y **CON-01** (`OrigenDocumento`, ya hecha). Si USR-11 no está mergeada, frená.
**La necesitan** CON-03a, CON-03b, todo el módulo de compras (CMP-02 en adelante) y las reaperturas CON-04a/b/c: es el servicio que usan
todas las demás apps para asentar.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Todo lo que hace falta para poder crear un asiento desde cualquier parte del sistema, **sin pantallas todavía**: los
cuatro modelos, el plan de cuentas de 19 cuentas cargado por migración, el ejercicio (primero, apertura diaria, autorrecuperación), la
numeración sin huecos y el servicio `registrar_asiento_automatico`. Es la tarea más delicada de la ronda: cualquier error acá se hereda en
toda la contabilidad.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CON-ABR-EJE | Abrir Ejercicio Contable (paso diario 5, primer ejercicio, autorrecuperación) | docs/casos_de_uso/contabilidad/ejercicio.md | Solo la mitad «abrir»; el cierre es CON-03a |
| (estructura) | Asiento automático (`registrar_asiento_automatico`) | docs/api/asientos.md | No es un caso de uso: es el servicio común (D-86) |
| (estructura) | Plan de cuentas (datos) | docs/casos_de_uso/contabilidad/plan_de_cuentas.md | Solo la carga; la pantalla es CON-03a |

## Leer

- Casos de uso: docs/casos_de_uso/contabilidad/ejercicio.md (solo CON-ABR-EJE y «Cómo se aplica»), plan_de_cuentas.md (la tabla de cuentas).
- Modelo: docs/modelo/contabilidad.md **completo** (las cuatro clases, el plan aprobado, «Qué cambia respecto del modelo de dominio»).
- Decisiones: **D-84, D-86** (las de esta tarea), D-85, D-52, D-05, D-22, D-30, D-32, D-36, D-37, D-39, D-44, D-56, D-83.
- API: docs/api/asientos.md **completo** (implementalo tal cual, es parte de esta tarea), docs/api/auditoria.md (si existe) y docs/api/notificaciones.md.
- Patrones: docs/patrones/asientos.md, docs/patrones/bloqueos.md, docs/patrones/auditoria.md, docs/patrones/datos_de_migracion.md, docs/patrones/trabajo_en_paralelo.md.
- Pantallas: ninguna (esta tarea no tiene interfaz).
- Reglas: .claude/rules/pruebas.md (y su sección de concurrencia).
- Código a leer: `contabilidad/models.py` (`OrigenDocumento`, y la migración `0001_initial`), `contabilidad/apps.py`, `core/procesos.py`
  (`registrar_paso_diario`, `ResumenDePaso` y el comentario con la tabla de órdenes), `core/models.py` (`RegistroAuditoria.objects.registrar`,
  `Accion`, `ETIQUETAS`, `ACCIONES_DE_NEGOCIO`, `VALORES_VISIBLES`), `core/servicios.py` (patrón de bloqueos y de auditoría), un servicio de
  `maestros` o `inventario` como modelo de estilo, y `docs/patrones/datos_de_migracion.md` (mixin de pruebas de migraciones de datos).

## Límites

- Crea modelos: `EjercicioContable`, `AsientoContable`, `MovimientoContable`, `CuentaContable` (`docs/modelo/contabilidad.md`, con **todas** sus
  restricciones de base: `ultimo_numero_asiento >= 0`, un solo ejercicio abierto, un solo «en cierre», unicidad `(ejercicio, numero_asiento)`,
  importe > 0, una cuenta por `codigo_cuenta`, el `OneToOne` del origen y el de `anula`) → revisá docs/disparadores.md.
- Migraciones: `contabilidad/migrations/0004_nucleo_contable.py` (esquema; depende de `core` por el FK a `core.Contador`) y
  `0005_plan_de_cuentas.py` (**datos**: las 19 cuentas con `update_or_create`). Una de `core`, solo de `choices`, con las acciones nuevas:
  `0038_contabilidad_acciones_de_auditoria` (el número libre en `main`: la 0037 la tomó COM-04b).
- Permitido fuera de la app:
  - `config/settings.py`: nada (la app ya está instalada);
  - `core/models.py`: solo `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO` (las acciones de `docs/modelo/contabilidad.md`: alta y
    modificación de ejercicio, alta de asiento y de movimiento, …) y su migración;
  - `core/procesos.py`: **solo el comentario** de la tabla de órdenes (fila `5 | Abrir ejercicio contable | contabilidad`);
  - al cerrar (M3), `docs/disparadores.md`, `docs/tareas/README.md` y `docs/tareas/ronda_contabilidad_1.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: **toda pantalla**, el asiento manual y el contraasiento (CON-03b), el cierre de ejercicio y el plan en pantalla
  (CON-03a), y los asientos de cada caso de uso (CON-04a/b/c y compras).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos, auditoría y migraciones de esquema.** Las cuatro clases con sus restricciones; las acciones de auditoría; `makemigrations`. —
   pruebas: `contabilidad/tests/test_modelos.py` (cada restricción de base se verifica con un `IntegrityError`).
2. **Plan de cuentas.** `contabilidad/cuentas.py` (constantes `CAJA`, `BANCO`, … `DEBE`, `HABER`, `DESCRIPCION_DE_CUENTA`) y la migración de
   datos 0005; `plan.arbol()` y `plan.cuenta()`. — pruebas: `test_plan_de_cuentas_datos.py` (con el mixin de migraciones: carga las 19, es
   idempotente, cada cuenta tiene descripción).
3. **Ejercicio.** `ejercicios.py`: `abrir_ejercicio_si_corresponde`, `crear_primer_ejercicio`, el paso diario 5 en `ready()`, el comando
   `poner_en_marcha_contabilidad`, el aviso de «en cierre». (**El cierre manual no va acá**: es CON-03a.) — pruebas: `test_con_abr_eje.py`,
   `test_paso_diario_ejercicio.py`, `test_ejercicios_concurrencia.py` (la parte de aperturas).
4. **Servicio de asientos automáticos.** `asientos.registrar_asiento_automatico` con el orden de bloqueos de D-86, las lecturas
   (`ejercicio_abierto`, `ejercicio_para`, `libro.saldo_por_cuenta`, `libro.movimientos_de_cuenta`, `libro.resultado_del_periodo`,
   `libro.total_por_cuenta_en_periodo`) y `responsables` ya hecho por USR-11. — pruebas: `test_asientos_automaticos.py` (cada error:
   `asiento_desbalanceado`, `cuenta_inexistente`, `origen_con_asiento`; importe cero; todo-o-nada; auditoría) y
   `test_asientos_concurrencia.py` (**dos asientos a la vez toman números consecutivos sin hueco**; mismo origen a la vez: uno solo gana).
5. **Utilidades de prueba para las demás apps.** `contabilidad/tests/fabricas.py` (`PlanDeCuentasMixin`, fábricas de ejercicio y de asiento) y
   `verificar_invariantes_contables`, tal como las describe `docs/api/asientos.md` («Pruebas de tu app»). — pruebas: una que las usa.

Si el tiempo apremia, lo último que se recorta es: `resultado_del_periodo` y `total_por_cuenta_en_periodo` (las usa Estadísticas, la última
ronda); se anota como disparador.

## Hecho cuando

- `registrar_asiento_automatico` crea el asiento, sus movimientos y su auditoría de una vez o ninguno; la numeración no tiene huecos aunque
  haya concurrencia; el origen no puede tener dos asientos.
- El primer ejercicio se crea con el comando o con la primera operación, y el paso diario 5 cierra y abre ejercicios según las fechas.
- La tabla de cuentas está cargada y es idéntica a la del modelo (19 cuentas).
- Pruebas verdes (incluidas las de `@tag("concurrencia")`), `makemigrations --check` limpio, sin imports hacia apps de nivel superior (A1).
- Comando de pruebas: `python manage.py test contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test contabilidad --keepdb --tag concurrencia`.

## Verificación a mano

Esta tarea **no tiene pantallas**: se verifica en PowerShell y en la consola de Django (`shell`). No hay paso de «navegador real» (no hay pantallas públicas ni formularios que se envíen). Nada de esto toca producción: es tu base local de desarrollo (`localhost:5433`).

**Aviso antes de empezar.** Lo que crees acá queda en tu base de desarrollo. Un **asiento no se puede borrar ni editar** (es a propósito: se corrige con un contraasiento) y un ejercicio «cerrado» no se reabre. Si querés volver a empezar de cero, avisame y lo vemos (borrar datos de tu base de desarrollo se pregunta antes). Por eso los pasos 14 a 16, que simulan fechas futuras, son **opcionales**: dejan ejercicios de 2027 y 2028 que después no se pueden sacar. Los cubre el recorrido por prueba.

**Qué necesitás.** Tener la rama `feature/con-02-nucleo-contable`, el entorno virtual activo y la base local encendida. No hace falta ninguna cuenta ni contraseña: los asientos de esta verificación los hace «InfoPonia» (`actor=None`).

### Preparación

**1. Aplicá las migraciones.** En PowerShell, en la carpeta del proyecto:

```powershell
.venv\Scripts\Activate.ps1
python manage.py migrate
```

Tiene que terminar sin errores y mostrar, entre otras, `Applying core.0038_contabilidad_acciones_de_auditoria... OK`, `Applying contabilidad.0004_nucleo_contable... OK` y `Applying contabilidad.0005_plan_de_cuentas... OK`.

**2. Mirá que el plan de cuentas esté cargado (19 cuentas).** Abrí la consola de Django con `python manage.py shell` y pegá:

```python
from contabilidad.models import CuentaContable
print(CuentaContable.objects.count())
for c in CuentaContable.objects.all(): print(c.codigo_cuenta, "|", c.nombre_cuenta, "|", c.tipo_cuenta)
```

(Los bloques con `for` o `try` llevan una línea en blanco al final al pegarlos.) Tiene que imprimir **19** y la lista, de `1.1.01 | Caja | activo` a `5.1.07 | Gastos Generales | resultado_negativo`; entre ellas, `2.1.02 | Indemnizaciones a Pagar | pasivo`. Dejá esta consola abierta para los pasos siguientes que dicen «en la consola».

**3. Mirá que el proceso diario tenga el paso nuevo, primero de todos.** En otra terminal PowerShell:

```powershell
python manage.py proceso_diario --listar
```

La primera línea tiene que ser `5 · abrir_ejercicio · Abrir ejercicio contable`, antes de `10 · revisar_vencimientos · ...`.

### El primer ejercicio

**4. Poné en marcha la contabilidad** con un primer ejercicio que empieza el 1 de noviembre de 2026:

```powershell
python manage.py poner_en_marcha_contabilidad --fecha-inicio 2026-11-01
```

Tiene que decir: `Primer ejercicio creado: del 01/11/2026 al 31/10/2027.`

**5. Corrélo de nuevo (tiene que ser idempotente):**

```powershell
python manage.py poner_en_marcha_contabilidad --fecha-inicio 2026-01-01
```

Tiene que decir `Ya existe un ejercicio contable (Ejercicio 01/11/2026 al 31/10/2027): no se hizo nada.` y **no** crear otro. Probá también una fecha futura, `--fecha-inicio 2030-01-01` (tiene que dar un error que diga que la fecha no puede ser futura), y un formato malo, `--fecha-inicio 1-1-2026` (tiene que decir que uses `AAAA-MM-DD`).

### Un asiento automático

**6. Creá un asiento.** En la consola de Django, pegá el bloque entero:

```python
import datetime
from decimal import Decimal
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import OrigenDocumento
from contabilidad.servicios import asientos

origen = OrigenDocumento.objects.bulk_create([OrigenDocumento(tipo="bitacora")])[0]
asiento = asientos.registrar_asiento_automatico(
    None,
    origen,
    datetime.date(2026, 11, 20),
    [(cuentas.INSUMOS_EN_STOCK, DEBE, Decimal("3000.00")), (cuentas.PROVEEDORES, HABER, Decimal("3000.00"))],
    descripcion="Verificación a mano de CON-02",
)
print(asiento, "|", asiento.numero_asiento, asiento.fecha_asiento, asiento.tipo, "|", asiento.descripcion_asiento)
for m in asiento.movimientos.all(): print(m.cuenta, m.tipo_movimiento, m.importe_movimiento)
```

(El `OrigenDocumento` suelto es un documento de prueba: en el sistema real lo crea la recepción, el pago, etc. Queda en la base como dato de prueba.)

Tiene que imprimir algo como `Asiento N.º 1 del Ejercicio 01/11/2026 al 31/10/2027 | 1 2026-11-20 automatico | Verificación a mano de CON-02` y las dos líneas `1.1.04 Insumos en Stock D 3000.00` y `2.1.01 Proveedores H 3000.00`. Fijate: el número es **1**, la fecha es la del hecho (20/11) y el tipo es `automatico`.

**7. Mirá la auditoría** (en la consola):

```python
from core.models import RegistroAuditoria
for r in RegistroAuditoria.objects.filter(accion__endswith="_contable").order_by("id"):
    print(r.accion, "| rol:", r.rol, "|", [a["texto"] for a in r.afectados])
    print("   ", r.detalle)
```

Tiene que haber, en este orden: **1** `alta_ejercicio_contable` (la puesta en marcha del paso 4, con `datos: origen: puesta en marcha`), **1** `alta_asiento_contable` y **2** `alta_movimiento_contable`, todos con `rol: infoponia` (porque pasamos `None` como actor). En el detalle del asiento se ven `numero_asiento`, `fecha_asiento` (`2026-11-20`), `descripcion_asiento`, `ejercicio` y `origen`; en el de cada movimiento, `cuenta_contable`, `tipo_movimiento` (`D` o `H`) e `importe_movimiento` (`3000.00`, como texto). Opcional: si entrás a la pantalla «Auditoría» como Gerente, esos registros se tienen que ver con nombres en castellano («Alta de asiento contable», «Importe», «Debe o Haber»), no con claves sueltas.

**8. Un segundo asiento y la numeración.** En la consola:

```python
origen2 = OrigenDocumento.objects.bulk_create([OrigenDocumento(tipo="bitacora")])[0]
segundo = asientos.registrar_asiento_automatico(
    None, origen2, datetime.date(2026, 11, 21),
    [(cuentas.CAJA, DEBE, Decimal("500.00")), (cuentas.VENTAS, HABER, Decimal("500.00"))],
)
print(segundo.numero_asiento)
```

Tiene que imprimir **2** (correlativo, sin saltos).

### Cómo provocar errores (todos se rechazan sin dejar nada)

**9. Un asiento desbalanceado.** En la consola (con una línea en blanco al final):

```python
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable
origen3 = OrigenDocumento.objects.bulk_create([OrigenDocumento(tipo="bitacora")])[0]
try:
    asientos.registrar_asiento_automatico(
        None, origen3, datetime.date(2026, 11, 22),
        [(cuentas.CAJA, DEBE, Decimal("100.00")), (cuentas.VENTAS, HABER, Decimal("90.00"))],
    )
except ErrorContable as error:
    print(error.codigo, "|", error.mensaje)

print(AsientoContable.objects.count())
```

Tiene que imprimir `asiento_desbalanceado | El asiento no está balanceado: Debe 100.00 y Haber 90.00.` y después `2` (no se creó nada). Después, con la misma estructura de `try/except`, probá cada uno y verificá el código que imprime:

- Una cuenta que no existe: `("9.9.99", DEBE, Decimal("10.00"))` junto con `(cuentas.VENTAS, HABER, Decimal("10.00"))` → `cuenta_inexistente`.
- Un importe con decimales de más, `Decimal("1.001")` → `importe_invalido`; y con `float` (`10.5`) → también `importe_invalido`.
- Un tipo que no es `"D"` ni `"H"` (por ejemplo `"X"`) → `tipo_de_movimiento_invalido`.
- El mismo origen dos veces: llamá otra vez con `origen` (el del paso 6) → `origen_con_asiento`.

**10. Importe cero (no es un error).** En la consola:

```python
r = asientos.registrar_asiento_automatico(
    None, origen3, datetime.date(2026, 11, 22),
    [(cuentas.CAJA, DEBE, Decimal("0.00")), (cuentas.VENTAS, HABER, Decimal("0.00"))],
)
print(r, AsientoContable.objects.count())
```

Tiene que imprimir `None 2`: no hay asiento y tampoco error.

**11. Un asiento no se edita ni se borra.** En la consola (con una línea en blanco al final):

```python
from contabilidad.models import AsientoInmutableError
try:
    asiento.descripcion_asiento = "otra"
    asiento.save()
except AsientoInmutableError as error:
    print("save:", error)

try:
    asiento.delete()
except AsientoInmutableError as error:
    print("delete:", error)
```

Los dos tienen que imprimir un mensaje que dice que se corrige con un contraasiento.

**12. Una fecha que no cabe en ningún ejercicio** (anterior al primero). En la consola:

```python
origen4 = OrigenDocumento.objects.bulk_create([OrigenDocumento(tipo="bitacora")])[0]
a = asientos.registrar_asiento_automatico(
    None, origen4, datetime.date(2026, 5, 5),
    [(cuentas.CAJA, DEBE, Decimal("10.00")), (cuentas.VENTAS, HABER, Decimal("10.00"))],
)
print(a.numero_asiento, a.fecha_asiento, "|", a.descripcion_asiento)
```

Tiene que **no** fallar: el asiento es el número 3, se registra con la fecha de **hoy** y la descripción dice `Fecha del hecho: 05/05/2026 (anterior al primer ejercicio); se registra con la fecha de hoy.` Lo mismo pasaría con una fecha futura («posterior a la fecha de hoy») o dentro de un ejercicio ya cerrado.

### El libro (lectura)

**13. Saldos.** En la consola:

```python
from contabilidad.servicios import libro, ejercicios
ej = ejercicios.ejercicio_abierto()
saldos = libro.saldo_por_cuenta(ej.pk)
for codigo in ("1.1.01", "1.1.04", "2.1.01", "4.1.01"): print(codigo, saldos[codigo])
print(libro.resultado_del_periodo(datetime.date(2026, 11, 1), datetime.date(2026, 12, 31)))
```

Tiene que mostrar `1.1.01` con saldo `510.00` (500 del segundo asiento más 10 del paso 12), `1.1.04` y `2.1.01` con `3000.00`, `4.1.01` con `510.00`, y un resultado con ingresos `510.00` y egresos `0.00`.

### El paso diario y los ejercicios que vencen (opcional: deja fechas futuras en la base)

**14. El último día del ejercicio no pasa nada:**

```powershell
python manage.py proceso_diario --solo abrir_ejercicio --fecha 2027-10-31
```

Tiene que mostrar `Abrir ejercicio contable: procesados 1 · creados 0 · resueltos 0 · sin cambios`.

**15. Al día siguiente, el ejercicio pasa a «en cierre» y se abre el siguiente:**

```powershell
python manage.py proceso_diario --solo abrir_ejercicio --fecha 2027-11-01
```

Tiene que mostrar `creados 1` y, en el detalle, el ejercicio que pasó a «en cierre» y el nuevo abierto (`01/11/2027 al 31/10/2028`). En la consola, `ejercicios.ejercicio_en_cierre()` devuelve el de 2026 y `ejercicios.ejercicio_abierto()`, el de 2027. Si hay un Contador (o, si no, el Gerente) activo, en su campana tiene que aparecer «El ejercicio N.º 1 pasó a «en cierre»». Corrélo otra vez el mismo día: ahora tiene que decir `creados 0` (idempotente).

**16. Un año más: el que estaba «en cierre» se cierra solo:**

```powershell
python manage.py proceso_diario --solo abrir_ejercicio --fecha 2028-11-01
```

Tiene que mostrar `resueltos 1`. El de 2026 queda «cerrado» (sin Contador) y el de 2027 «en cierre». Quien sea responsable contable recibe «El ejercicio N.º 1 se cerró solo».

### Qué cubre ya una prueba

| Paso | Lo cubre |
|---|---|
| 1, 2 | `PlanDeCuentasMigracionTests` (19 cuentas, idempotente, idénticas al modelo) y `PlanDeCuentasConstantesTests` |
| 3 | `PasoDiarioEjercicioTests.test_regla_7_*` |
| 4, 5 | `PonerEnMarchaContabilidadTests` (crea, idempotente, fecha futura, formato) y `ConAbrEjePrimerEjercicioTests` |
| 6, 8 | `AsientoAutomaticoRegistroTests` y el recorrido `RecorridoDeNucleoContableTests` |
| 7 | `test_post_audita_el_asiento_y_cada_movimiento_con_el_actor` y `test_post_sin_actor_la_auditoria_es_de_infoponia` |
| 9, 10 | `AsientoAutomaticoErroresTests`, `AsientoAutomaticoImporteCeroTests` y `AsientoAutomaticoTodoONadaTests` |
| 11 | `AsientoContableModeloTests.test_d84_*` y `MovimientoContableModeloTests` |
| 12 | `AsientoAutomaticoFechaTests` |
| 13 | `test_libro.py` |
| 14 a 16 | `ConAbrEjeAperturaTests`, `ConAbrEjeCierreSoloTests`, `ConAbrEjeSistemaApagadoTests` y el recorrido |
| Dos asientos a la vez, mismo origen, dos aperturas a la vez | `test_asientos_concurrencia.py` y `test_ejercicios_concurrencia.py`; no se puede hacer a mano con una sola persona |

Si tenés poco tiempo, hacé los pasos 1 a 6, 9 y 12: son lo que se **ve** (migrar, el comando, el asiento con sus movimientos y los rechazos). El resto lo cubren las pruebas.

## Cierre

**Qué se hizo.**
- **Modelos y migraciones.** `EjercicioContable`, `CuentaContable`, `AsientoContable` y `MovimientoContable`, con todas sus restricciones de base y la inmutabilidad de asientos y movimientos. Migraciones: `contabilidad/0004_nucleo_contable` (esquema), `contabilidad/0005_plan_de_cuentas` (datos: las **19** cuentas) y `core/0038_contabilidad_acciones_de_auditoria` (solo `choices`).
- **Auditoría en `core`.** Cuatro acciones nuevas (`alta_ejercicio_contable`, `modificacion_ejercicio_contable`, `alta_asiento_contable` y `alta_movimiento_contable`), clasificadas y con sus etiquetas.
- **Plan de cuentas.** `constantes.py`, `cuentas.py` (19 constantes, rubros y `DESCRIPCION_DE_CUENTA`) y `servicios/plan.py` (`arbol()` y `cuenta()`).
- **Ejercicios.** `servicios/ejercicios.py`: apertura automática (`abrir_ejercicio_si_corresponde`), primer ejercicio, lecturas, `destino_del_asiento` y `ejercicio_para`, paso diario 5 (registrado en `ContabilidadConfig.ready()`) y el comando `poner_en_marcha_contabilidad`. El comentario de la tabla de órdenes de `core/procesos.py` tiene la fila del 5.
- **Asientos y libro.** `servicios/asientos.py` (`registrar_asiento_automatico`, con el ejercicio bloqueado al final) y `servicios/libro.py` (las cuatro lecturas).
- **Utilidades de prueba.** `contabilidad/tests/fabricas.py` y `contabilidad/errores.py` (`ErrorContable`).

**Diferencias con la documentación** (van a `docs/temas_abiertos.md` y a la decisión nueva):
1. **Fecha del asiento automático (diferencia con D-84 punto 5).** Nunca se rechaza por la fecha: una fecha en un ejercicio cerrado, anterior al primer ejercicio o futura va al ejercicio abierto con la fecha de hoy, y la descripción aclara la fecha real («Fecha del hecho: dd/mm/aaaa (<motivo>); se registra con la fecha de hoy.»; si pasa de 300 caracteres se recorta la descripción de quien llama, nunca la aclaración). `ejercicio_para(automatico=True)` no lanza; con `automatico=False` lanza los tres errores de fecha. D-84 solo decía qué hacer con un ejercicio cerrado.
2. **`total_por_cuenta_en_periodo(tipo=None)`** devuelve el saldo según la naturaleza de la cuenta (con signo); con «D» o «H», la suma de ese lado; otro valor, `tipo_de_movimiento_invalido`. La API decía solo «suma de los movimientos».
3. **Migraciones:** son la 0004 y la 0005 de `contabilidad` (la 0002 y la 0003 ya estaban ocupadas) y la 0038 de `core`. D-84 punto 7 nombra `0003_plan_de_cuentas.py`.
4. **«Carga las 18»** del paso 2 de la tarea es un error de tipeo: el plan tiene 19 cuentas y la prueba verifica 19.
5. **`DEBE` y `HABER`** viven en `contabilidad/constantes.py` (como importa la API) y `cuentas.py` los reexporta (como dice la tarea).
6. **`ResultadoApertura`** tiene dos campos más (`cantidad_creados`, `cantidad_cerrados_solos`): el resumen del paso diario necesita el total cuando hay varias vueltas.
7. **`crear_primer_ejercicio(fecha_inicio, hoy=None)`** suma `hoy` opcional y, si ya hay un ejercicio, devuelve el que existe.
8. **Auditoría:** la documentación no decía qué claves lleva cada acción; siguen D-36 (fechas ISO, importes como texto). La cuenta del movimiento se llama `cuenta_contable` (no `cuenta`, para no confundirla con las cuentas de usuario), y `estado_ejercicio` y `tipo_movimiento` tienen su propia lista en `VALORES_VISIBLES`.
9. **Textos de aviso** nuevos: «El ejercicio N.º X se cerró solo» y «Se cerró solo porque venció el siguiente (terminó el dd/mm/aaaa).».
10. **`docs/api/auditoria.md`** no existe: se ignoró esa mención de «Leer».
11. **Libro:** `saldo_por_cuenta` devuelve las 19 cuentas (también las sin movimientos). Las pruebas del libro están en `test_libro.py` (la tarea las ponía dentro de las de asientos).

12. **Dos pruebas de otras tareas ya no podían pasar y se ajustaron** (con tu aprobación, sin debilitarlas): `comercial/tests/test_com_reg_cvt.py::test_regla_la_venta_no_genera_pago_ni_asiento` preguntaba si existía el modelo `AsientoContable` (ahora existe) y pasa a comprobar que la venta no deje ningún asiento; `inventario/tests/test_paso_diario_vencimientos.py::test_d56_el_paso_es_el_primero_del_proceso_diario` afirmaba que el paso 10 era el primero y ahora acepta que solo lo antecede el paso 5 de contabilidad (D-84).
13. **`core` 0038:** la migración de `core` se regeneró después de mergear `main` (COM-04b tomó la 0037).

**Pantallas: lo que se corrigió del prototipo (D-61).** No aplica: la tarea no tiene pantallas.

**Pruebas (M1).**
- `python manage.py test contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **961 pruebas, OK** (`contabilidad` sola: 191). Una corrida anterior del mismo comando falló por un `OperationalError('the connection is closed')` de `core.tests.test_usr_ini_ses.MigracionEmailTests` bajo `--parallel`; esa clase pasa sola y en serie, y la corrida en serie de `contabilidad core` (961) salió limpia. Parece intermitente del paralelo y no de esta tarea, pero no lo pude confirmar contra `main`.
- `python manage.py test contabilidad --keepdb --tag concurrencia` → **7 pruebas, OK**.
- `makemigrations --check --dry-run` → sin cambios. Sin imports hacia apps de nivel mayor (A1).
- **Experimento de bloqueos** (pedido para esta tarea): quité cada protección, la prueba correspondiente falló y restauré el código. Sin el `select_for_update` del ejercicio fallaron «dos asientos a la vez» y «mismo origen»; sin la verificación del origen con el ejercicio bloqueado falló «mismo origen» (el rechazo pasaba a salir del `IntegrityError`); bloqueando el ejercicio antes falló «el ejercicio va último»; sin el bloqueo de la apertura fallaron las dos pruebas de aperturas a la vez; sin atrapar el `IntegrityError` del primer ejercicio fallaron las dos de puesta en marcha a la vez.

**Decisiones.** Se propone una decisión nueva (sin número hasta el M3, después de `git fetch` y mirando `docs/decisiones/` en `main`): fecha del asiento automático, texto de H10 y `tipo=None` de `total_por_cuenta_en_periodo`.

**Datos de la base de desarrollo.** No se borró ni se cargó nada en la base de desarrollo: solo se corrió `makemigrations`; el `migrate` lo hacés vos en el paso 1. Las pruebas usaron bases `test_…`.

### Informe

**Verifiqué:**
- El recorrido `RecorridoDeNucleoContableTests`: puesta en marcha con el comando → primer ejercicio → asiento automático con sus movimientos y su auditoría → numeración → asiento desbalanceado rechazado → paso diario el último día (sin cambios) y al día siguiente (pasa a «en cierre», se abre el siguiente, avisa) → asientos en cada ejercicio → arrastre de saldos → un año más, el viejo se cierra solo → idempotencia.
- `sqlmigrate`: la 0004 solo crea 4 tablas, índices y restricciones (no borra ni reescribe datos); la 0005 es una carga en Python con `update_or_create`; la 0038 de `core` no cambia el SQL. Las tres se aplicaron en la base de pruebas.
- Los 5 experimentos de bloqueo.

**Lo cubre una prueba:** cada regla, postcondición y error está en `test_modelos.py`, `test_plan_de_cuentas_datos.py`, `test_con_abr_eje.py`, `test_paso_diario_ejercicio.py`, `test_asientos_automaticos.py`, `test_libro.py`, `test_fabricas.py`, `test_ejercicios_concurrencia.py` y `test_asientos_concurrencia.py` (la tabla de la «Verificación a mano» dice cuál cubre cada paso).

**No pude verificar:**
- El `migrate` sobre tu base de desarrollo y todo lo que se ve en ella (pasos 1 a 16): no la toco.
- Cómo se ven los registros en la pantalla «Auditoría» (opcional del paso 7).
- Los avisos en la campana de un Contador o Gerente real (paso 15).
- La migración de datos sobre la base de Neon (producción): Render la aplica en el despliegue; conviene mirar el log.
- Si la falla intermitente de `MigracionEmailTests` bajo `--parallel` ya existía en `main`.
