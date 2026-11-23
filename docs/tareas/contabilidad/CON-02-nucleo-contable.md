# CON-02 · Núcleo contable: ejercicio, asiento, movimiento, plan de cuentas y el servicio de asientos automáticos

Estado: pendiente | App: contabilidad | Rama: feature/con-02-nucleo-contable | Ronda: Contabilidad 1

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
- Migraciones: `contabilidad/migrations/0002_nucleo_contable.py` (esquema; depende de `core` por el FK a `core.Contador`) y
  `0003_plan_de_cuentas.py` (**datos**: las 19 cuentas con `update_or_create`). Una de `core`, solo de `choices`, con las acciones nuevas:
  `00NN_contabilidad_acciones_de_auditoria` (el número libre en `main`).
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
   datos 0003; `plan.arbol()` y `plan.cuenta()`. — pruebas: `test_plan_de_cuentas_datos.py` (con el mixin de migraciones: carga las 18, es
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

Sin pantallas todavía: en la consola, `python manage.py poner_en_marcha_contabilidad` y, en `shell`, creá un asiento con
`registrar_asiento_automatico(...)` sobre un origen de prueba; mirá el asiento, los movimientos y el registro de auditoría. La verificación
visual llega con CON-03a.

## Cierre (M3)

Actualizá `docs/tareas/README.md`, `docs/tareas/ronda_contabilidad_1.md`, `docs/estado.md`, el comentario de `core/procesos.py`, y
`docs/disparadores.md` (nacen: «Cuando exista la recepción de compras (asiento de compras)», «Cuando se reabra COM-CNC-ENT…»). Anotá en el
«Cierre» toda diferencia con D-84 y D-86.
