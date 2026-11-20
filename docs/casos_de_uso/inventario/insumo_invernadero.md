# Casos de uso · inventario · Insumos en el invernadero y existencias

Copia para el repo de los casos CMP-HAB-IIN, CMP-MOD-IIN, CMP-DSH-IIN y CMP-CNS-IIN del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario.

Son casos de uso breves (de alto nivel). **El código va en la app `inventario`** (D-37); el archivo de pruebas es
`inventario/tests/test_cmp_hab_iin.py` y los análogos.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| CMP-HAB-IIN | Habilitar Insumo en Invernadero | Agrónomo | `inventario/tests/test_cmp_hab_iin.py` |
| CMP-MOD-IIN | Modificar Insumo en Invernadero | Agrónomo | `inventario/tests/test_cmp_mod_iin.py` |
| CMP-DSH-IIN | Deshabilitar Insumo en Invernadero | Agrónomo | `inventario/tests/test_cmp_dsh_iin.py` |
| CMP-CNS-IIN | Consultar Existencias de Insumos | Agrónomo | `inventario/tests/test_cmp_cns_iin.py` |

---

## CMP-HAB-IIN · Habilitar Insumo en Invernadero

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: habilitar un insumo del catálogo en un invernadero a cargo del actor, con su stock mínimo y su precio de referencia, para poder pedirlo, recibirlo y consumirlo ahí.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El invernadero está activo y a cargo del actor.
c. El insumo está activo en el catálogo.
d. El insumo no está habilitado en ese invernadero.

**Postcondición, según lo que haya hecho el actor:**
a. Si el insumo nunca había estado habilitado en el invernadero, se creó su registro de insumo en invernadero en
   estado «activo», con stock cero, sin lotes de insumo y con el stock mínimo y el precio de referencia indicados.
b. Si ya había estado habilitado y luego se deshabilitó, se reactivó ese mismo registro con el mínimo y el precio
   nuevos, y se conservó su historial.
c. Si el stock mínimo es mayor que cero, el Sistema evaluó la alerta de stock bajo el mínimo. Como el insumo nace con
   stock cero, se generó la alerta para el Agrónomo, salvo que el insumo ya tuviera mercadería en tránsito hacia ese
   invernadero que alcance el mínimo.
d. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del insumo y del invernadero, y los
   valores cargados.

**Reglas:**
1. Solo habilita el Agrónomo a cargo del invernadero. El Gerente no gestiona insumos en invernaderos.
2. El insumo se elige entre los insumos activos del catálogo que no están habilitados en ese invernadero. Se incluyen
   las semillas.
3. El stock mínimo es obligatorio: cero o más, con los decimales que admite la unidad del insumo.
4. El precio de referencia es obligatorio y mayor que cero. Es el precio por unidad de medida del insumo puesto en el
   invernadero, y se usa para valorizar consumos y ajustes.
5. Hay un solo registro por cada par de insumo e invernadero (regla 1 de 8.4). Por eso una nueva habilitación reactiva
   el registro anterior en lugar de crear otro.
6. El insumo nace con stock cero. Al terminar, el Sistema ofrece «Cargar stock inicial», que inicia CMP-AJT-STK con el
   motivo «carga inicial».
7. Este caso de uso extiende («extend») a cuatro casos: CMP-CNS-INS, desde el catálogo; CMP-ALT-INS y PROD-ALT-VAR, al
   terminar el alta; PROD-PNF-SMB, cuando la semilla no está habilitada en el invernadero; y CMP-RLZ-PED, cuando el
   insumo que se quiere pedir no está habilitado en el invernadero de destino. En esos casos, el insumo o el
   invernadero ya vienen elegidos.
8. La alerta se evalúa con la regla 3 de CMP-MOD-IIN, igual que al modificar el mínimo.

---

## CMP-MOD-IIN · Modificar Insumo en Invernadero

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: actualizar el stock mínimo y el precio de referencia de un insumo habilitado en un invernadero.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El invernadero está activo y a cargo del actor.
c. El insumo está habilitado en ese invernadero.

**Postcondición:**
a. Se actualizaron el stock mínimo, el precio de referencia o los dos.
b. Si cambió el stock mínimo, el Sistema volvió a evaluar la alerta de stock bajo el mínimo: si el insumo quedó bajo
   el mínimo, se generó la alerta para el Agrónomo, salvo que ya hubiera una activa; si dejó de estar bajo el mínimo,
   la alerta activa pasó a «resuelta».
c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del insumo y del invernadero, y los
   cambios.

**Reglas:**
1. Solo se modifican el stock mínimo y el precio de referencia. Se validan con las reglas 3 y 4 de CMP-HAB-IIN. El
   stock se corrige con un ajuste (CMP-AJT-STK).
2. El precio nuevo rige para los consumos y ajustes desde ese momento. Lo ya registrado no cambia.
3. Un insumo está bajo el mínimo cuando su stock libre más lo que está en tránsito queda por debajo del mínimo (regla
   «Insumo bajo el mínimo» de CMP-RLZ-PED).
4. Un insumo deshabilitado no se modifica: se vuelve a habilitar con CMP-HAB-IIN.

---

## CMP-DSH-IIN · Deshabilitar Insumo en Invernadero

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: dejar de usar un insumo en un invernadero sin perder su historial.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El invernadero está activo y a cargo del actor.
c. El insumo está habilitado en ese invernadero.
d. En ese invernadero, el insumo tiene stock cero (ni positivo ni negativo). Tampoco tiene cantidades reservadas,
   cantidad en tránsito ni una orden de compra aprobada sin recibir.
e. El insumo no figura en ningún pedido en curso con destino a ese invernadero, es decir, en ningún pedido que todavía
   no tiene orden de compra.

**Postcondición:**
a. El registro del insumo en el invernadero quedó en estado «inactivo». En ese invernadero, el insumo dejó de
   ofrecerse para pedidos, órdenes de trabajo y aplicaciones de insumos.
b. La alerta de stock bajo el mínimo del insumo en ese invernadero, si estaba activa, pasó a «resuelta».
c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del insumo y del invernadero, y el cambio
   de estado.

**Reglas:**
1. La deshabilitación es lógica: el insumo conserva en ese invernadero sus lotes de insumo, sus movimientos, sus
   consumos y su historial.
2. Si no se cumple la precondición d o la e, el Sistema no deshabilita el insumo e informa todo lo que lo impide, cada
   cosa con cómo resolverla: el stock, incluso el negativo, se usa o se lleva a cero con un ajuste (CMP-AJT-STK); las
   órdenes que lo reservan se concretan o se cancelan; la mercadería en camino se recibe o se cierra su orden de
   compra; los pedidos en curso se cierran o se les quita el insumo.
3. El insumo sigue en el catálogo y se vuelve a habilitar con CMP-HAB-IIN, que reactiva el mismo registro.

---

## CMP-CNS-IIN · Consultar Existencias de Insumos

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: consultar el stock de los insumos habilitados en los invernaderos a cargo del actor, con sus lotes de insumo y sus vencimientos.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.

**Postcondición:**
a. No se producen cambios en el Sistema.

**Reglas:**
1. El Agrónomo ve los insumos habilitados en los invernaderos activos a su cargo. El Gerente no consulta existencias.
2. Se puede filtrar por invernadero, por categoría, por «con vencimientos» y por «bajo el mínimo».
3. De cada insumo se ve: el stock libre, sobre el stock total; lo reservado y lo que está en tránsito; el stock
   mínimo, con la marca «bajo el mínimo»; el estado del vencimiento; y la marca «stock negativo» o «no cubre las
   reservas», si corresponde.
4. Cada fila se despliega para mostrar los lotes de insumo, cada uno con su fecha de ingreso, lo disponible sobre lo
   ingresado, su vencimiento y su estado.
5. Desde cada fila se puede iniciar CMP-MOD-IIN, CMP-DSH-IIN o CMP-AJT-STK. En los lotes vencidos aparece «Dar de
   baja», que inicia CMP-AJT-STK con el motivo «vencimiento».
6. La consulta no se audita (SEG-14).

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45)

Tarea: **INV-02** (los modelos `InsumoInvernadero`, `LoteInsumo` y `MovimientoInsumo` los crea INV-01).

- **«A cargo».** El invernadero está «a cargo del actor» si el Agrónomo asignado al invernadero es el actor y su cuenta está activa.
  Los servicios lo verifican **después** de bloquear el invernadero (`bloquear_invernadero_activo`, D-40) y vuelven a verificar
  el estado del insumo.
- **El registro único del par.** Una restricción de la base garantiza un solo `InsumoInvernadero` por `(insumo, invernadero)`.
  Habilitar un par que ya existió reactiva ese mismo registro con el mínimo y el precio nuevos (postcondición b).
- **Stock en tránsito.** La columna `cant_transito_insumo` existe y vale 0: solo la escribe `compras` (D-45). INV-02 la lee en las
  reglas de «bajo el mínimo» y de los impedimentos, sin tocarla.
- **Stock libre y «bajo el mínimo».** Se calculan con las funciones de `inventario/servicios/stock.py`
  (`docs/patrones/stock.md`): libre = lo disponible en los lotes **no vencidos hoy** (más el faltante sin lote, que es negativo)
  menos las reservas activas; el insumo está bajo el mínimo si el mínimo es mayor que cero y libre + tránsito < mínimo. Las
  reservas las informa `produccion` por el punto de extensión; sin ellas, valen 0.
- **Alerta «insumo bajo el mínimo».** Tipo de estado de `inventario` (`inv_insumo_bajo_minimo`, clave `insumo:<id del
  InsumoInvernadero>`), destinada al Agrónomo o, sin Agrónomo activo, al Gerente (D-41). La evalúa `reevaluar_alertas_del_insumo`
  al habilitar, al modificar el mínimo, al ajustar, al deshabilitar y, después, en cada operación de stock. Un solo punto: ver
  `docs/patrones/stock.md`, «Alertas».
- **Pantalla de existencias (CNS-IIN).** Es la pestaña «Existencias de insumos» de `VIEWS.insumos` del prototipo. Filtros: invernadero,
  categoría, «Vencidos o por vencer» (la regla 2 pide «con vencimientos») y «Bajo el mínimo». Cada fila despliega sus lotes; los
  lotes vencidos ofrecen «Dar de baja» (abre CMP-AJT-STK con el motivo «vencimiento»). Los consumos de «Registrar aplicación de
  insumos» y los pedidos no son de esta tarea.
- **Qué hace falta para deshabilitar (DSH).** Todos los impedimentos se juntan y se informan juntos, cada uno con su código,
  texto y cómo resolverlo (`Impedimento` de `maestros.extensiones`): `stock_distinto_de_cero` (incluido el negativo y el
  faltante sin lote), `reservas_activas` (punto de extensión), `cantidad_en_transito`, y los de `compras`
  (`orden_de_compra_aprobada`, `pedido_en_curso`) por `registrar_impedimento_de_deshabilitacion`.
- **Baja del invernadero (disparador «Cuando exista InsumoInvernadero»).** INV-02 registra en `maestros/extensiones.py`:
  `registrar_impedimento_de_baja` (stock distinto de cero, tránsito y orden de compra aprobada de cualquiera de sus insumos:
  precondición f de PROD-BAJ-INV) y `registrar_efecto_de_baja` (los `InsumoInvernadero` activos pasan a inactivos, con un log
  `baja_insumo_invernadero` por cada uno: postcondición c y parte de la f). Todo servicio de INV-02 que deje stock distinto de
  cero llama a `bloquear_invernadero_activo` antes (contrato de D-40).
- **Auditoría (D-36).** Acciones `habilitacion_insumo_invernadero` (alta o reactivación), `modificacion_insumo_invernadero` y
  `baja_insumo_invernadero`. Las cantidades y los precios son `Decimal`: **van como texto** en `cambios` y `datos` (el
  validador de D-36 rechaza `Decimal`).
- **Extienden este caso de uso** (regla 7 de HAB): CMP-ALT-INS, PROD-ALT-VAR, PROD-PNF-SMB y CMP-RLZ-PED. En esta ronda lo usan
  el catálogo (INV-01/INV-02) y PRD-01 (cuando una semilla no está habilitada). La función de servicio recibe el insumo y el
  invernadero ya elegidos: `habilitar_insumo(actor, insumo_id, invernadero_id, cant_min, referencia_precio)`.

