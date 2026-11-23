# Casos de uso · contabilidad · Libro de gestión

Copia para el repo de CON-CNS-LGS, de los archivos fuente de la ronda de Contabilidad (CON-alto-nivel.md). Cotejado con `decisiones_A0.md` y
`pendientes_para_pegar.md` (**esas decisiones ganan** si algo difiere, regla de Ezequiel del 23/11/2026).

**El código va en la app `contabilidad`** (D-37, nivel 2); archivos de pruebas bajo `contabilidad/tests/`. Si este archivo y el
documento de Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>` y `test_post_<letra>_<que_espera>`.

---

## **Caso de uso CON-CNS-LGS: Consultar Libro de Gestión**

Reemplaza a CON-CNS-LDR (Libro Diario) y CON-CNS-LMY (Libro Mayor), propuestos en el contexto (sección 3.2), y a CU-68 y CU-69 de «Documentación para la IA». X9: «Libro de gestión» es el nombre del mecanismo contable interno de InfoPonia; no es libro diario ni mayor legal y no está homologado. Un solo caso de uso con dos vistas.

**Actores:** Contador o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver los asientos de la organización, en orden de fecha o por cuenta con su saldo, para controlar la contabilidad y saber cómo van los números.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Contador o de Gerente.

**Postcondición:**

a. Ninguna: es una consulta, no modifica datos ni registra auditoría.

**Reglas:**

1.  Alcance: el Contador y el Gerente ven todo. El Gerente siempre consulta el libro, haya o no Contador. El Vendedor no tiene acceso (X3). No hay precondición de invernaderos (X10).
2.  **Vista cronológica:** lista los asientos ordenados por fecha y, a igual fecha, por número (H8: el número es de orden de registro, no de fecha). De cada uno se ve el número, la fecha, la descripción, el tipo (automático, manual o contraasiento; se deduce, regla 15 de 8.20), el total y si está anulado. Filtros: ejercicio (por defecto el abierto), rango de fechas, tipo, origen (tipo de documento), cuenta y anulados sí o no.
3.  **Vista por cuenta:** muestra los movimientos de una cuenta con Debe, Haber y saldo acumulado. Siempre filtra un ejercicio (por defecto el abierto). (H2.3)
4.  **Saldos:** las cuentas de resultado (positivo o negativo) muestran solo los movimientos del ejercicio elegido, desde cero. Las patrimoniales (activo, pasivo y patrimonio neto) arrancan con el saldo acumulado de los ejercicios anteriores. El signo depende del tipo: activo y resultado negativo, saldo deudor (Debe − Haber); pasivo, patrimonio neto y resultado positivo, saldo acreedor (Haber − Debe). Un saldo contrario a su naturaleza se marca (por ejemplo, Diferencias de Inventario de Insumos puede quedar acreedora, H5). (H2.3, H7)
5.  **Ficha del asiento:** número, fecha, ejercicio, descripción, movimientos (cuenta, Debe o Haber, importe), documento de origen con acceso a su consulta (si lo tiene), quién lo registró (si es manual o contraasiento; si lo registró el Gerente, desde el log de auditoría), y si anula a otro asiento o fue anulado por otro (con acceso a él).
6.  Los asientos de un ejercicio «cerrado» se ven pero no se modifican. Si un asiento corresponde a un hecho de un ejercicio cerrado, la descripción lo aclara (H10).
7.  Acciones: desde la ficha, el actor que registra asientos ve el acceso a Contraasentar Asiento (CON-CTR-ASI), si el asiento puede anularse, y desde la lista el acceso a Registrar Asiento Manual (CON-REG-ASI). El Gerente solo las ve si no hay un Contador activo. (X3)
8.  Desde cada cuenta se puede ir a su ficha en el plan de cuentas (CON-CNS-PCT).
9.  La consulta no se audita (SEG-14).

---

---

## Cómo se aplica (código)

Decisión **D-84** (puntos 5, 8 y 10). Modelo: `docs/modelo/contabilidad.md`. Contrato de lectura: `docs/api/asientos.md` («Lectura»).

### Servicios de lectura (`contabilidad/servicios/libro.py`)

- `listar_asientos(actor, ejercicio_id=None, desde=None, hasta=None, tipo=None, origen_tipo=None, cuenta=None, anulados=None, texto="")`:
  precondición a (cuenta activa de Contador o de Gerente; si no, `PermissionDenied`), `QuerySet` ordenado por `(fecha_asiento, numero_asiento)`
  con `prefetch_related("movimientos__cuenta")` y `select_related("origen", "ejercicio")`. **El ejercicio por defecto es el abierto.** `tipo` es
  `automatico`, `manual` o `contraasiento` (se filtra con `origen__isnull`, `anula__isnull`). `anulados` es `True`/`False`/`None` (se filtra con
  la existencia del `contraasiento`). `texto` busca en la descripción, en el número exacto y en el identificador del origen.
- `ficha_de_asiento(actor, ejercicio_id, numero)`: el asiento con sus movimientos, su origen (con el enlace a su consulta si el tipo de origen
  la tiene: la función `enlace_de_origen(origen)` consulta un punto de extensión, ver abajo), quién lo registró (ver abajo), el asiento que
  anula y el que lo anuló.
- `saldo_por_cuenta(ejercicio_id)` y `movimientos_de_cuenta(codigo, ejercicio_id)` (contrato en `docs/api/asientos.md`): consultas agregadas
  con `Sum(Case(When(tipo_movimiento="D", ...)))`; las cuentas **patrimoniales** (activo, pasivo, patrimonio neto) arrancan con el saldo
  acumulado de los ejercicios de `fecha_inicio_ejercicio` menor; las **de resultado**, desde cero (regla 4). Un saldo contrario a su naturaleza
  se devuelve con `contrario=True` (la pantalla lo marca en rojo).
- **Quién registró (regla 5):** el asiento manual y el contraasiento guardan el usuario solo en la auditoría (regla 16 de 8.20, patrón de
  R050). `ficha_de_asiento` lo busca en `RegistroAuditoria` por la acción `alta_asiento_contable` y el afectado. No hay campo.
- **Enlace al origen (regla 5) — punto de extensión:** `contabilidad` no puede importar las apps que originan los asientos (A1). Se agrega
  `contabilidad/extensiones.py` con `registrar_enlace_de_origen(tipo, funcion)`; `funcion(origen) -> (texto, url) | None`. Cada app que
  reabre un caso de uso (CON-04a, b, c y compras) registra el suyo en `ready()`; sin registrante, la ficha muestra solo el texto del tipo
  («Recepción», «Entrega»…) sin enlace.
- **Paginación:** 50 asientos por página, en el servidor. La vista por cuenta pagina por movimientos (100 por página); el saldo acumulado de la
  primera fila de cada página se calcula con el saldo inicial más lo anterior de esa cuenta.

### Pantallas (prototipo: `tabLibro`, `libroCron`, `libroCta`, `VIEWS.k_asi`)

Pestaña «Libro de gestión» (la primera de «Contabilidad»): selector de ejercicio, interruptor Cronológica / Por cuenta, filtros y lista; cuando
el ejercicio está «en cierre» o «cerrado», un aviso arriba (en cierre: «terminó el …, todavía se pueden registrar asientos de ese período»;
cerrado: «solo lectura»). Ficha del asiento con sus acciones: «Contraasentar» (solo quien registra asientos: el Contador, o el Gerente sin
Contador activo, y solo si el asiento puede anularse y su ejercicio no está cerrado) y «Registrar asiento» desde la lista. El Gerente con un
Contador activo ve el libro **sin** esas acciones. Textos explicativos siempre: una línea bajo el título explica «Libro de gestión» (ver el
glosario: no es el libro diario legal).

### Pruebas (`contabilidad/tests/`)

| Qué | Archivo |
|---|---|
| Cada regla (alcance, filtros, orden, saldos patrimoniales y de resultado, saldo contrario, ficha, ejercicio cerrado) | `test_con_cns_lgs.py` |
| `saldo_por_cuenta`, `movimientos_de_cuenta`, `resultado_del_periodo` y `total_por_cuenta_en_periodo` con datos de dos ejercicios | `test_libro.py` |
| Vistas: acceso por rol, las dos vistas, filtros, paginación, enlaces, acciones visibles según quién es el actor | `test_libro_vistas.py` |
| Sin consultas por fila (`assertNumQueries` acotado) | en `test_con_cns_lgs.py` |

## Solo prototipo

El selector de rol, el interruptor «Hay un Contador activo» y los datos de ejemplo («Reiniciar datos de ejemplo»).
