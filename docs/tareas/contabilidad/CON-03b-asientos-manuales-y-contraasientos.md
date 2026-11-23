# CON-03b · Asientos manuales y contraasientos

Estado: pendiente | App: contabilidad | Rama: feature/con-03b-asientos-manuales-y-contraasientos | Ronda: Contabilidad 1

Depende de: **CON-03a** (las pantallas del libro y las fichas, donde viven las acciones) y CON-02. Si no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Contador (o el Gerente, si no hay Contador) puede registrar un **asiento manual** y **anular** un asiento con un
**contraasiento** (que el Gerente recibe como notificación). Con esto, la contabilidad queda utilizable sola, antes de que ninguna otra
operación del sistema genere asientos.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CON-REG-ASI | Registrar Asiento Manual | docs/casos_de_uso/contabilidad/asientos_manuales.md | Los atajos «asiento de apertura» y «venta previa» son precarga, sin código propio (extensiones 3a y 3b) |
| CON-CTR-ASI | Contraasentar Asiento | docs/casos_de_uso/contabilidad/asientos_manuales.md | La fecha del contraasiento cae en un ejercicio abierto o en cierre (C3): **manda el caso de uso, no el prototipo** |

## Leer

- Casos de uso: el extracto, completo, **incluida la sección «Cómo se aplica (código)»**.
- Modelo: docs/modelo/contabilidad.md (`AsientoContable`, `MovimientoContable`, «Tipo (derivado)»).
- Decisiones: D-84 (puntos 4 a 6 y 9), D-85, D-86, D-30, D-32, D-36, D-42, D-44, D-61.
- API: docs/api/asientos.md («Escritura: asiento manual, contraasiento y ejercicio»), docs/api/notificaciones.md.
- Patrones: docs/patrones/asientos.md (el orden de bloqueos: **el ejercicio va último**), docs/patrones/bloqueos.md,
  docs/patrones/auditoria.md, docs/patrones/abm.md.
- Pantallas: docs/prototipos/compras_contabilidad/ — `k_new`, `INIT.k_new`, `ACT.mvadd`, `ACT.mvdel`, `ACT.mvt`, `ACT['asi-ok']`, `k_contra`,
  `ACT['contra-ok']` (referencia, D-61).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CON-02 y CON-03a, `core/notificaciones.py` (`notificar_a_varios`, `excluir`), y un formulario con filas dinámicas del repo
  (si no hay, el patrón HTMX de `docs/patrones/abm.md`).

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: `core/models.py` solo si CON-02 no dejó alguna acción (`alta_asiento_contable`, `alta_movimiento_contable`) y su
  migración; al cerrar (M3), `docs/disparadores.md`, README de tareas y el plan de la ronda.
- Dependencias nuevas: ninguna.
- Fuera de alcance: los asientos automáticos de cada operación, los pagos, y cambiar el aviso del Vendedor (CON-04d).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Registrar asiento manual (servicio).** `registrar_asiento_manual` y `resumir_asiento_manual`, con las fechas, el importe cero, el balance y
   los errores por línea. — pruebas: `test_con_reg_asi.py` (cada regla, extensión y postcondición) con `verificar_invariantes_contables`.
2. **Contraasentar (servicio).** `contraasentar`, `resumir_contraasiento` y `datos_para_correccion`, el bloqueo del asiento antes del
   ejercicio, la notificación al Gerente y su respaldo sin Gerente. — pruebas: `test_con_ctr_asi.py`.
3. **Concurrencia.** `test_asientos_concurrencia.py` (los casos que enumera el extracto, en especial: dos contraasientos del mismo asiento).
4. **Pantallas.** El formulario con filas dinámicas y buscador de cuenta, el resumen, la confirmación, los atajos de apertura y venta previa,
   y la acción «Contraasentar» en la ficha (visible según `puede_registrar_asientos`). — pruebas: `test_asientos_vistas.py`.

Si el tiempo apremia, lo último que se recorta es: los atajos de apertura y de venta previa (se anota como disparador).

## Hecho cuando

- Un asiento manual válido se registra con número consecutivo y quedan auditados el asiento y cada movimiento; uno inválido no escribe nada.
- Un contraasiento invierte un asiento una sola vez, avisa al Gerente, y el asiento anulado queda marcado en el libro.
- El Gerente con un Contador activo ve el libro pero **no** las acciones, y el servicio le dice «Lo registra el Contador».
- Pruebas verdes (incluida concurrencia).
- Comando de pruebas: `python manage.py test contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test contabilidad --keepdb --tag concurrencia`.

## Verificación a mano

1. Como Contador, registrá un asiento de apertura (Caja contra Capital Inicial) y mirá el libro.
2. Contraasentalo con otra fecha; verificá que el Gerente recibe la notificación y que el asiento original aparece como anulado.
3. Intentá un asiento desbalanceado y uno con fecha futura: deben rechazarse con un mensaje claro.

## Cierre (M3)

Actualizá README de tareas, el plan de la ronda y `docs/estado.md`. Anotá en el «Cierre» las diferencias con el prototipo (la fecha del
contraasiento, en cualquier ejercicio abierto o en cierre, ya está corregida en él).
