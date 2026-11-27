# Modelo de dominio · contabilidad (extracto)

Copia para el repo de «Copia de modelo_dominio» (bloque Contabilidad, fichas de `EjercicioContable`, `AsientoContable`, `CuentaContable`,
`MovimientoContable` y `OrigenDocumento`; reglas 15 a 17 de 8.20 y reglas 14 de 8.20 y 15 de 8.13 en lo que toca a asientos; ronda 22)
y de «GLO · Glosario de términos», sección 5. Cotejado con pendientes_MD hasta MD-130 (los ítems **MD-114 a MD-119 y MD-129**, «Decidido sin
aplicar» al 23/11/2026, mandan sobre el modelo de dominio y sobre el glosario) y con `decisiones_A0.md` (H1 a H12, C1 a C10 y la pasada
general). **Regla del estudiante (23/11/2026):** lo decidido en esos archivos vale como cierto aunque Drive todavía no lo diga.
Si este archivo y Drive no coinciden, avisá: no elijas en silencio.

Vive en `contabilidad` (nivel 2, D-37). Decisiones de código: **D-84** (ejercicios, numeración, apertura, plan de cuentas), **D-85** (el
rol Contador) y **D-86** (cómo crea un asiento un servicio de otra app). Contrato para las demás apps: `docs/api/asientos.md`; patrón:
`docs/patrones/asientos.md`.

**Qué existe en cada tarea:** `OrigenDocumento` ya existe (CON-01, D-52). **CON-02** crea `EjercicioContable`, `CuentaContable`,
`AsientoContable` y `MovimientoContable` (y el plan de cuentas por migración de datos).

## Convenciones de nombres de este extracto (D-05)

Los atributos van en snake_case con el sufijo de la clase: `fecha_inicio_ejercicio`, `numero_asiento`, `codigo_cuenta`, etc. Los valores
fijos van como `TextChoices` anidados en la clase (`EjercicioContable.Estado`, `CuentaContable.Tipo`, `MovimientoContable.Tipo`).

## EjercicioContable

Bloque: Contabilidad. Período contable de 12 meses donde se registran los asientos (MD-115).

### Atributos

| Atributo (código) | Tipo y restricciones | Nota |
|---|---|---|
| `id` | automático | — |
| `fecha_inicio_ejercicio` | `DateField`, obligatorio | El primero empieza el día que elige el Contador en CON-INI-EJE (no futuro y con el cierre previsto no anterior a hoy; tarea CON-05, reemplaza D-84 punto 3); los demás, el día siguiente al cierre previsto del anterior |
| `fecha_cierre_ejercicio` | `DateField`, obligatorio, ≥ `fecha_inicio_ejercicio` | **Fecha prevista de fin**, fijada al abrir: un año menos un día después del inicio (12 meses). No se modifica (H1) |
| `estado_ejercicio` | `Estado`: `abierto`, `en_cierre`, `cerrado` | Ver reglas |
| `ultimo_numero_asiento` (técnico, D-84 punto 4) | `PositiveIntegerField`, default 0 | Último número usado en el ejercicio; lo toma y suma el servicio con el ejercicio bloqueado |
| `contador` (R010) | FK nula a `core.Contador` (`PROTECT`, `related_name="ejercicios_cerrados"`) | **Contador cierra EjercicioContable** (R010, MD-116): el Contador que lo cerró. Vacío mientras no está cerrado, y vacío si lo cerró el Gerente (sin Contador activo) o el Sistema (C1); la persona o InfoPonia queda en la auditoría (patrón de R050, MD-61) |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R010 | Contador, «cierra» | Ejercicio → Contador = 0..1; Contador → Ejercicio = 0..* | **Modificada (MD-116):** antes Gerente «analiza». FK `contador` (declarada acá: la app de nivel mayor, A2) |
| R013 | AsientoContable, «contiene» | Ejercicio → Asiento = 0..*; Asiento → Ejercicio = 1 | `AsientoContable.ejercicio`, `PROTECT` |

### Restricciones de la base

- A lo sumo **un** ejercicio «abierto» y **uno** «en cierre»: dos `UniqueConstraint` parciales sobre `estado_ejercicio`
  (`un_solo_ejercicio_abierto`, `un_solo_ejercicio_en_cierre`). Respaldo de los servicios (H1).
- `fecha_cierre_ejercicio >= fecha_inicio_ejercicio` (`CheckConstraint`).
- `contador` solo puede estar lleno si el estado es `cerrado` (`CheckConstraint`).
- Los rangos de dos ejercicios **no se superponen**: lo garantiza el servicio de apertura (el nuevo empieza el día siguiente al cierre
  previsto del anterior); la prueba `verificar_invariantes_contables` lo chequea. No hay `ExclusionConstraint`: pediría la extensión
  `btree_gist` y D-84 no suma dependencias.

### Reglas (MD-115)

1. `abierto`: el único donde entran asientos automáticos con fecha de hoy. `en_cierre`: terminó su fecha de cierre y el Contador
   todavía puede cargar asientos con fecha en su rango (H1, H10). `cerrado`: definitivo, no recibe asientos y **no hay reapertura**.
2. **Apertura automática (CON-ABR-EJE).** El día siguiente a `fecha_cierre_ejercicio` del abierto: el abierto pasa a «en cierre» y se
   crea el siguiente (inicio = día siguiente; cierre previsto = un año menos un día después). Si ya había uno «en cierre», el Sistema lo
   **cierra solo** (el más viejo, sin Contador, con aviso, C1) antes de pasar el abierto a «en cierre». Es el paso diario de orden 5 y,
   si ese paso no corrió, la autorrecuperación del servicio de asientos (H9, D-84 punto 2).
3. **Cierre manual (CON-CRR-EJE).** Solo un ejercicio «en cierre» y solo lo cierra el Contador (o el Gerente si no hay Contador activo).
   Sin verificaciones que lo bloqueen (C9).
4. **Sin refundición (H2.3):** el cierre no genera asientos. El libro calcula: las cuentas de resultado, solo del ejercicio elegido; las
   patrimoniales, acumuladas.
5. El **primer ejercicio** lo crea CON-INI-EJE junto con su asiento de apertura N.º 1 (Capital Inicial), en una sola transacción (tarea CON-05; reemplaza D-84 punto 3). Mientras no existe, ninguna operación que genera un asiento se registra (regla 9 de CON-INI-EJE): no hay período de uso con asientos sin contabilidad (MD-119). **2.1.02 «Indemnizaciones a Pagar»** es el haber de la multa por resolución de un suministro (MD-123); la agregó
Ezequiel el 23/11/2026 (faltaba en H5/H6/H7).

## AsientoContable

Bloque: Contabilidad. Registro de un hecho económico con sus movimientos. Concreto (clave `id`). **Inmutable:** `save()` sobre una fila
existente y `delete()` lanzan `AsientoInmutableError`; el queryset (`update`, `delete`) también (como la auditoría, D-22).

### Atributos

| Atributo (código) | Tipo y restricciones | Nota |
|---|---|---|
| `numero_asiento` | `PositiveIntegerField` | Correlativo por ejercicio, sin huecos (H8, MD-117). Indica orden de registro, no de fecha. Único con `ejercicio` |
| `fecha_asiento` | `DateField` | La del hecho (H10). En el ejercicio «en cierre» puede ser anterior a otros ya cargados |
| `descripcion_asiento` | `CharField(max_length=300)`, `blank=True` | **Obligatoria** en un asiento sin documento de origen (manual o contraasiento), donde explica el motivo (regla 16 de 8.20). En un automático la completa el Sistema si hace falta aclarar (por ejemplo, la fecha real, H10) |
| `registrado_el` (técnico) | `DateTimeField(auto_now_add=True)` | Cuándo se registró (el ``fecha de registro`` que nombra H10). No es del modelo de dominio |

### Asociaciones

| ID | Con | Cardinalidad | Código |
|---|---|---|---|
| R012 | OrigenDocumento, «se origina» | Asiento → Origen = 0..1; Origen → Asiento = 0..1 | `origen = OneToOneField("contabilidad.OrigenDocumento", null=True, blank=True, on_delete=PROTECT, related_name="asiento_contable")` |
| R013 | EjercicioContable, «contiene» | Asiento → Ejercicio = 1; Ejercicio → Asiento = 0..* | `ejercicio = ForeignKey(EjercicioContable, on_delete=PROTECT, related_name="asientos")` |
| R161 | AsientoContable, «contraasienta» (reflexiva) | contraasiento → asiento anulado = 0..1; asiento anulado → contraasiento = 0..1 | `anula = OneToOneField("self", null=True, blank=True, on_delete=PROTECT, related_name="contraasiento")` en el **contraasiento** (apunta al asiento anulado). «Anulado» se deriva: `hasattr(asiento, "contraasiento")` |
| R014 | MovimientoContable, «tiene» (composición) | Asiento → Movimiento = 2..*; Movimiento → Asiento = 1 | `movimientos` |

### Tipo (derivado, regla 15 de 8.20)

`automatico` si tiene `origen`; `contraasiento` si tiene `anula`; `manual` si no tiene ninguna de las dos. **No se guarda**: propiedad
`tipo`. Un asiento no puede tener `origen` y `anula` a la vez (`CheckConstraint`).

### Restricciones y reglas

- Único `(ejercicio, numero_asiento)`.
- `descripcion_asiento` no vacía si no tiene `origen` (`CheckConstraint`: `~Q(origen__isnull=True, descripcion_asiento="")`).
- **Debe = Haber**, dos o más movimientos, importes mayores que cero: no hay restricción de base (compara varias filas); lo cuida el
  servicio y lo verifica `verificar_invariantes_contables` en las pruebas. Un asiento de importe cero no se registra (H11).
- **Contraasiento (regla 17 de 8.20):** mismos movimientos que el anulado con Debe y Haber invertidos. Un asiento se anula una sola vez
  (el `OneToOne` de R161 lo garantiza) y **un contraasiento no se anula** (lo controla el servicio). No deshace la operación original (C5).
- **Ejercicio y fecha (H10, C2, C3):** ver D-84 punto 5.
- Tipo de asiento y quién lo registra (regla 16 de 8.20, **cambiada por MD-114**): un asiento sin documento de origen lo registra el
  **Contador** o, si no hay un Contador activo, el **Gerente**; el Vendedor ya no. El usuario real queda en el log de auditoría.
- Nadie borra un documento de origen (D-52): `PROTECT`.

## MovimientoContable

Bloque: Contabilidad. Una línea de un asiento: una cuenta, Debe o Haber, un importe. Inmutable como su asiento.

| Atributo (código) | Tipo y restricciones | Nota |
|---|---|---|
| `tipo_movimiento` | `Tipo`: `debe` (`"D"`), `haber` (`"H"`) | — |
| `importe_movimiento` | `DecimalField(max_digits=14, decimal_places=2)` | Mayor que cero (`CheckConstraint`); dos decimales; pesos argentinos |
| `asiento` (R014) | FK a `AsientoContable`, `PROTECT`, `related_name="movimientos"` | Composición |
| `cuenta` (R015) | FK a `CuentaContable`, `PROTECT`, `related_name="movimientos"` | — |

## CuentaContable

Bloque: Contabilidad. Cuenta del plan de cuentas. **No es un ABM**: el plan se carga por migración de datos (D-37, D-84 punto 7) y se
consulta (CON-CNS-PCT). Mejora futura: ABM de cuentas.

| Atributo (código) | Tipo y restricciones | Nota |
|---|---|---|
| `codigo_cuenta` | `CharField(max_length=10)`, único | Jerárquico `rubro.subrubro.cuenta` (por ejemplo `1.1.01`) |
| `nombre_cuenta` | `CharField(max_length=80)`, único | — |
| `tipo_cuenta` | `Tipo`: `activo`, `pasivo`, `patrimonio_neto`, `resultado_positivo`, `resultado_negativo` | Define el signo del saldo (H7) |

### Plan de cuentas aprobado (MD-118; H5, H6, H7)

| Código | Cuenta | Tipo | Saldo normal |
|---|---|---|---|
| 1.1.01 | Caja | Activo | deudor |
| 1.1.02 | Banco c/c | Activo | deudor |
| 1.1.03 | Deudores por Ventas | Activo | deudor |
| 1.1.04 | Insumos en Stock | Activo | deudor |
| 1.1.05 | Productos en Proceso | Activo | deudor |
| 1.1.06 | Productos Terminados | Activo | deudor |
| 2.1.01 | Proveedores | Pasivo | acreedor |
| 2.1.02 | Indemnizaciones a Pagar | Pasivo | acreedor |
| 3.1.01 | Capital Inicial | Patrimonio neto | acreedor |
| 4.1.01 | Ventas | Resultado positivo | acreedor |
| 4.1.02 | Indemnizaciones por Atraso en el Pago | Resultado positivo | acreedor |
| 4.1.03 | Otros Ingresos | Resultado positivo | acreedor |
| 5.1.01 | Costo de Producción Vendida | Resultado negativo | deudor |
| 5.1.02 | Pérdidas por Mermas | Resultado negativo | deudor |
| 5.1.03 | Gastos de Producción | Resultado negativo | deudor |
| 5.1.04 | Indemnizaciones por Incumplimiento a Cliente | Resultado negativo | deudor |
| 5.1.05 | Indemnizaciones por Resolución de Contratos | Resultado negativo | deudor |
| 5.1.06 | Diferencias de Inventario de Insumos | Resultado negativo (**puede quedar acreedora**) | deudor |
| 5.1.07 | Gastos Generales | Resultado negativo | deudor |

Rubros del árbol: 1 «Activo», 2 «Pasivo», 3 «Patrimonio neto», 4 «Ingresos», 5 «Egresos»; subrubros: 1.1 «Activo corriente», 2.1 «Pasivo
corriente», 3.1 «Capital», 4.1 «Ingresos operativos», 5.1 «Egresos operativos».

**Sin IVA (simplificación declarada).** Saldo: activo y resultado negativo, deudor (Debe − Haber); pasivo, patrimonio neto y resultado
positivo, acreedor (Haber − Debe). Un saldo contrario a su naturaleza **se marca** en el libro (por ejemplo, la cuenta 5.1.06).
**5.1.03 «Gastos de Producción»** cierra la parte de gastos de MD-90; **3.1.01 «Capital Inicial»** es el haber de las cargas iniciales
(MD-119). **2.1.02 «Indemnizaciones a Pagar»** es el haber de la multa por resolución de un suministro (MD-123); la agregó
Ezequiel el 23/11/2026 (faltaba en H5/H6/H7). La descripción de cada cuenta (regla 3 de CON-CNS-PCT: para qué se usa y qué casos de uso la mueven) **no es una columna**: es el diccionario `DESCRIPCION_DE_CUENTA` de `contabilidad/cuentas.py` (texto de `docs/casos_de_uso/contabilidad/plan_de_cuentas.md`), así reabrir un caso de uso no necesita una migración. Constantes en el código: `contabilidad/cuentas.py` (`CAJA`, `BANCO`, `DEUDORES_POR_VENTAS`, `INSUMOS_EN_STOCK`,
`PRODUCTOS_EN_PROCESO`, `PRODUCTOS_TERMINADOS`, `PROVEEDORES`, `INDEMNIZACIONES_A_PAGAR`, `CAPITAL_INICIAL`, `VENTAS`, `INDEMNIZACIONES_POR_ATRASO`,
`OTROS_INGRESOS`, `COSTO_DE_PRODUCCION_VENDIDA`, `PERDIDAS_POR_MERMAS`, `GASTOS_DE_PRODUCCION`, `INDEMNIZACIONES_POR_INCUMPLIMIENTO`,
`INDEMNIZACIONES_POR_RESOLUCION`, `DIFERENCIAS_DE_INVENTARIO`, `GASTOS_GENERALES`).

## OrigenDocumento

Bloque: Contabilidad. Concepto padre de todo lo que, dentro del sistema, genera movimientos y a lo que se corresponden esos movimientos
(R012, R016, R017). En el dominio es abstracta: nadie crea un `OrigenDocumento` solo. **Existe desde CON-01** (D-52).

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `id` | — | El `id` automático. **Compartido** por todos los documentos: no es consecutivo por tipo |
| `tipo` | `OrigenDocumento.Tipo`: `orden_de_trabajo`, `bitacora`, `movimiento_de_insumo`; `contrato` (COM-02); y los que suman las rondas siguientes con su clase (ver abajo) | Discriminador de la herencia. Lo fija la hija directa y nunca cambia |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R012 | AsientoContable, «origina» | OrigenDocumento → AsientoContable = 0..1 | **Vigente desde CON-02**: `AsientoContable.origen` (arriba) |
| R016 | MovimientoInsumo, «se origina» | OrigenDocumento → MovimientoInsumo = 0..*; MovimientoInsumo → OrigenDocumento = 0..1 | Vigente desde D-52 |
| R017 | MovimientoStock, «se origina» | 0..* | COM-02 y COM-04 |

### Hijas directas y tipos que se suman

Hoy: `OrdenTrabajo`, `Bitacora`, `MovimientoInsumo` (y `Contrato`, planificada en COM-02). Las siguientes se suman **con su tarea**, cada
una con su valor de `Tipo` (cambio de `choices`, una migración de `contabilidad` con solo ese cambio): `Pago`, `PagoCliente`,
`SolicitudRevision`, `Suministro`, `Entrega`, `MovimientoStock`, `Anulacion` (comercial) y, de **Compras 1**, `Recepcion`
(`recepcion`), `CorreccionRecepcion` (`correccion_de_recepcion`) y `Pago` de compras (`pago`). **Ojo con los nombres:** `Pago` (de
proveedores, `compras`) y `PagoCliente` (`comercial`) son dos clases distintas.

### Restricciones y reglas

- `tipo` obligatorio y dentro de la lista; `OrigenDocumento.save()` lanza error si lo llama alguien que no es una hija directa.
- Nadie borra un documento de origen: todas las claves que lo apuntan son `PROTECT`.
- Un accesorio inverso de cada hija con su nombre en minúsculas (`bitacora`, `ordentrabajo`…) ya existe: **al declarar una relación hacia
  `OrigenDocumento` usá un `related_name` propio** (por eso R012 se llama `asiento_contable`) y no el nombre de una hija (D-83).

## Qué cambia respecto del modelo de dominio y del glosario (pendientes_MD)

| Ítem | Qué cambia | Dónde se aplica |
|---|---|---|
| MD-114 | Rol **Contador**: uno solo activo; registra asientos y contraasientos, registra pagos a proveedores, cierra ejercicios y consulta el libro; sin Contador activo, el Gerente. El Vendedor deja de registrar asientos (MD-31). El Gerente siempre consulta el libro y recibe un aviso de cada contraasiento | `docs/tareas/core/USR-11-rol-contador.md`; D-85 |
| MD-115 | Estados del ejercicio (`abierto` / `en_cierre` / `cerrado`), duración de 12 meses, apertura automática, cierre manual, sin refundición | arriba; D-84 |
| MD-116 | R010 pasa a «Contador cierra EjercicioContable» (0..1) | arriba |
| MD-117 | Numeración correlativa por ejercicio sin huecos; fecha del hecho; ejercicio destino; importe cero; contraasiento con fecha elegida, corrección en dos operaciones, sin restricción de cuentas | arriba; D-84 |
| MD-118 | Plan de cuentas completo (códigos y tipos) | arriba |
| MD-119 | Contabilidad activa desde la puesta en marcha; cuenta **Capital Inicial**; el ajuste de insumo «carga inicial» se asienta contra Capital Inicial (cambia la regla 2 de 8.19); las ventas de producción previa, con asiento manual | `docs/casos_de_uso/contabilidad/asientos_manuales.md` (extensiones 3a y 3b); CON-04a |
| MD-129 | Glosario: «Libro de gestión» (nombre del mecanismo contable interno; **no** es libro diario ni mayor legal ni está homologado), «Contador», «Ejercicio en cierre»; Asiento Contable ya no dice «libro diario» | este archivo y los extractos de `casos_de_uso/contabilidad/` |
| MD-90 | Decidido: Gastos de Producción = 5.1.03; carga inicial contra Capital Inicial 3.1.01 | arriba |
| H21 | Regla general: **nunca se notifica a quien hizo la acción** | D-85; `docs/api/notificaciones.md` |

## Reglas de la sección 8 que tocan a la contabilidad

- **Regla 14 de 8.20 (asientos de la compra):** la recepción origina Debe Insumos en Stock / Haber Proveedores (valorizada con el precio
  total por línea, MD-125); el pago, Debe Proveedores / Haber Caja (efectivo) o Banco c/c (los demás medios). Sin ingreso al stock, no hay
  asiento. (Los asientos de compras los escribe `compras`, ronda «Compras 1»; `docs/modelo/compras.md`.)
- **Regla 15 de 8.20 (tipo de asiento):** automático / contraasiento / manual, se deduce.
- **Regla 16 de 8.20 (sin documento de origen):** descripción obligatoria; el usuario queda en el log. *(Actor cambiado por MD-114.)*
- **Regla 17 de 8.20 (contraasiento):** mismos movimientos invertidos; un asiento se anula una vez; un contraasiento no se anula. El
  ejemplo del modelo (asiento 85 → contraasiento 120 → manual 121) sigue valiendo.
- **Regla 15 de 8.13 (medio de pago):** efectivo → Caja; transferencia, tarjeta de débito y de crédito → Banco c/c.
- **Contabilidad por devengado** (glosario, «Base Devengado»): el asiento nace cuando nace el hecho (recepción, entrega concretada),
  no cuando se cobra.

## Glosario (términos que usa la ronda)

- **Libro de gestión:** el registro interno de asientos de InfoPonia, con una vista cronológica y una vista por cuenta. No es el libro
  diario ni el libro mayor legal y no está homologado.
- **Ejercicio contable:** período de 12 meses donde se registran asientos; abierto, en cierre o cerrado.
- **Ejercicio en cierre:** el que terminó su fecha prevista pero todavía admite asientos con fecha en su rango hasta que el Contador lo cierra.
- **Contraasiento:** asiento que anula a otro con los mismos movimientos invertidos. Corrige el libro, no deshace la operación.
- **Asiento manual:** asiento sin documento de origen; lo carga el Contador (o el Gerente sin Contador activo).
- **Capital Inicial:** cuenta de patrimonio neto que acredita todo lo que ya existía al poner en marcha InfoPonia.
- **Contador:** rol nuevo; uno solo activo.
