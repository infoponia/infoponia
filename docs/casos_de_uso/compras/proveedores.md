# Casos de uso · compras · Proveedores

Copia para el repo de CMP-ALT-PRV, CMP-MOD-PRV, CMP-BAJ-PRV y CMP-CNS-PRV (alto nivel, v0.1). Fuentes: `CMP-alto-nivel.md` (casos de uso de A0, 23/11/2026). Cotejado con `decisiones_A0.md` y `pendientes_para_pegar.md`: **esas decisiones ganan** si algo
difiere (regla del estudiante del 23/11/2026); lo que cambian está en «Actualizaciones de A0 que mandan», al final de cada caso de uso o del
archivo.

**El código va en la app `compras`** (D-37, nivel 6; D-87). Archivos de pruebas bajo `compras/tests/`. Si este archivo y el documento de
Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>`, `test_post_<letra>_<que_espera>` y
`test_ext_<codigo>_<que_espera>`.

---

## **Caso de uso CMP-ALT-PRV: Alta Proveedor**

Reemplaza a CU-86 de «Documentación para la IA» (preliminar).

**Actores:** Gerente. (CU-86 decía «Agrónomo o superior»; cambia por segregación de funciones: el Agrónomo pide y recibe, el Gerente administra los proveedores.)

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** registrar un proveedor al que se le pueden pedir cotizaciones y comprar insumos.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

**Postcondición:**

a. Se creó el proveedor en estado «activo», con CUIT, razón social (o nombre y apellido), correo electrónico, teléfono si se indicó, y los tipos de insumo en que se especializa, si se indicaron.

b. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del proveedor.

c. Si el CUIT era de un proveedor inactivo y el actor eligió reactivarlo, el proveedor pasó a «activo» (con los datos que el actor indicó) y se creó un log de auditoría con el cambio de estado, en lugar de un proveedor nuevo.

**Reglas:**

1.  Datos: CUIT, razón social (si es una organización) o nombre y apellido (si es una persona), correo electrónico y, si quiere, teléfono. El correo es obligatorio, porque el proveedor solo recibe pedidos y órdenes por correo; el teléfono es opcional (decisión P5 del prototipo). (MD › ficha Proveedor; GLO › Proveedor)
2.  CUIT: único entre todos los proveedores, activos e inactivos (H14). Si es el de un proveedor inactivo, el Sistema ofrece reactivarlo (mismo criterio que MD-48 para clientes). Se valida con la API pública de CUIT de `maestros` (D-58).
3.  Especialidad: el proveedor «se especializa en» cero o más tipos de insumo (asociación nueva, opcional; reemplaza al atributo `especialidad`; H13). Sirve para que Realizar Pedido proponga el filtro de proveedores por las categorías de los insumos del pedido.
4.  El proveedor no tiene cuenta en el Sistema: participa solo por enlace (GLO › Proveedor).
5.  No hay dirección del proveedor en el modelo (GLO › Proveedor; ver X7 en el contexto).

---

## **Caso de uso CMP-MOD-PRV: Modificar Proveedor**

Reemplaza a CU-87 (preliminar).

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** actualizar los datos de un proveedor registrado.

**Precondición:**

a. El actor está identificado con una cuenta activa de Gerente.

b. El proveedor está «activo».

**Postcondición:**

a. Se actualizaron los datos indicados, incluidos los tipos de insumo en que se especializa.

b. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del proveedor y los campos modificados (valor anterior y nuevo).

**Reglas:**

1.  Las mismas validaciones que el alta: correo obligatorio, teléfono opcional; CUIT único entre todos los proveedores (H14) y validado con la API de CUIT (D-58).
2.  Teléfono, correo, nombre, apellido, razón social y especialidades se modifican siempre. El CUIT no se modifica si el proveedor ya tiene pedidos u órdenes de compra. Reemplaza la restricción de CU-87 (no modificar con órdenes en curso).
3.  Cambiar el correo no cambia los enlaces ya enviados: siguen siendo del proveedor invitado (H15).
4.  Los tipos de insumo de la especialidad: si una categoría se da de baja, el vínculo se conserva y el filtro muestra solo categorías activas (H13).

---

## **Caso de uso CMP-BAJ-PRV: Baja Proveedor**

Reemplaza a CU-88 (preliminar). Decisión H22 aplicada.

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** dar de baja lógica a un proveedor con el que la organización ya no trabaja, sin perder su historial.

**Precondición:**

a. El actor está identificado con una cuenta activa de Gerente.

b. El proveedor está «activo».

c. No tiene órdenes de compra no terminadas: «pendiente de aprobación», «aprobada» o «parcialmente recibida». (H22)

d. No tiene pagos pendientes (todos sus detalles recibidos o cerrados, sin pago registrado), para no perder la deuda de la cuenta Proveedores. (H22)

**Postcondición:**

a. El proveedor quedó «inactivo» (baja lógica) y dejó de ofrecerse para invitarlo a pedidos.

b. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambio de estado.

**Reglas:**

1.  La baja es lógica: el proveedor conserva sus cotizaciones, recepciones, pagos y reclamos.
2.  Si no se cumple una precondición, el Sistema informa qué lo impide y cómo resolverlo (recibir o cerrar con faltante la mercadería en camino; registrar el pago).
3.  Un proveedor inactivo no se invita a pedidos nuevos. Si estaba invitado a un pedido «en cotización», su enlace deja de servir (pasa a «anulado», CMP-ENV-COT) y su cotización «propuesta» no se puede elegir (CMP-GNR-ODC; H16, paso 62).
4.  Se reactiva con el alta, si se ingresa su CUIT (H14).
5.  Tener pedidos «en cotización» donde el proveedor está invitado no bloquea la baja.


---

## **Caso de uso CMP-CNS-PRV: Consultar Proveedor**

Reemplaza a CU-89 (preliminar).

**Actores:** Agrónomo o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver los proveedores y sus datos, para invitarlos a pedidos o gestionarlos.

**Precondición:**

a. El actor está identificado con una cuenta activa de Agrónomo o de Gerente.

**Postcondición:**

a. Ninguna: es una consulta, no modifica datos ni registra auditoría.

**Reglas:**

1.  Alcance: el Agrónomo y el Gerente ven todos los proveedores, activos e inactivos.
2.  Filtros: estado, texto (razón social, nombre, CUIT) y tipo de insumo en que se especializa.
3.  Listado: razón social o nombre, CUIT, correo, teléfono, tipos de insumo en que se especializa (solo categorías activas) y estado.
4.  Ficha: los datos del proveedor y sus pedidos a los que fue invitado (con si cotizó), sus órdenes de compra con recepciones, pagos y reclamos. [El detalle de esas listas queda sujeto a las consultas de pedidos y órdenes, CMP-CNS-PED y CMP-CNS-ODC.]
5.  Desde la ficha, solo el Gerente puede ir a Modificar Proveedor y a Baja Proveedor, si está activo, y a reactivarlo desde el alta si está inactivo. El Agrónomo solo consulta.
6.  La consulta no se audita (SEG-14).

---


---

## Cómo se aplica (código)

Decisiones: **D-87**, **D-58** (CUIT). Modelo: `docs/modelo/compras.md` (`Proveedor`). Patrón: `docs/patrones/abm.md` (el ABM más parecido es el de
cliente, `docs/casos_de_uso/comercial/clientes.md`: mismo CUIT, misma reactivación, mismo tipo jurídica / física).

- **Servicios** (`compras/servicios/proveedores.py`): `alta_proveedor(actor, datos)` (si el CUIT es de un inactivo, `ErrorDeCompras`
  `cuit_de_inactivo` con el id, y la pantalla ofrece **reactivar**: `reactivar_proveedor(actor, proveedor_id, datos)`), `modificar_proveedor`,
  `baja_proveedor`, y las lecturas `listar_proveedores(actor, filtros)` y `ficha_de_proveedor(actor, id)`. Todos con `rol_requerido` (Gerente para
  escribir; Agrónomo o Gerente para leer).
- **CUIT:** `maestros.validadores.validar_cuit` y `formatear_cuit` (D-58). **Si COM-01 todavía no se mergeó, CMP-01 los crea** exactamente como dice
  `docs/api/direcciones.md` («CUIT»), con sus pruebas, y `maestros/servicios/perfil.py` delega en ella; la tarea que llegue segunda los usa.
- **«El CUIT no se modifica si tiene pedidos u órdenes»** (regla 2 de CMP-MOD-PRV): `proveedor.invitaciones.exists() or
  proveedor.cotizaciones.exists()`. Hasta CMP-02a no hay pedidos: la función ya existe y devuelve `False`.
- **Impedimentos de la baja** (precondiciones c y d de CMP-BAJ-PRV): `impedimentos_de_baja(proveedor) -> list[Impedimento]` con códigos
  `orden_no_terminada` (**se completa en CMP-03**) y `pago_pendiente` (**se completa en CMP-05**). En CMP-01 la función existe y devuelve la lista
  vacía; cada tarea suma su consulta. El texto dice qué lo impide y cómo resolverlo (regla 2).
- **Efecto de la baja** (regla 3): anular sus enlaces vigentes (**se completa en CMP-02b**, `enlaces.anular_enlaces_de_proveedor`).
- **Especialidades:** `ModelMultipleChoiceField` con buscador (criterio del estudiante: buscadores en lugar de desplegables), solo categorías
  activas para elegir; en la ficha se muestran solo las activas (regla 4 de MOD). La auditoría de la modificación lista los nombres antes y después.
- **Bloqueos:** el proveedor (`FOR NO KEY UPDATE`) antes de verificar unicidad, impedimentos y estado. Alta concurrente con el mismo CUIT: la
  restricción única de la base responde y el servicio traduce el `IntegrityError` al mismo mensaje.
- **Auditoría:** `alta_proveedor`, `modificacion_proveedor`, `baja_proveedor`, `reactivacion_proveedor` (acciones nuevas de `core`).

### Pruebas (`compras/tests/`)

| Qué | Archivo |
|---|---|
| CMP-ALT-PRV (incluida la reactivación), CMP-MOD-PRV, CMP-BAJ-PRV y CMP-CNS-PRV: cada regla y postcondición | `test_cmp_alt_prv.py`, `test_cmp_mod_prv.py`, `test_cmp_baj_prv.py`, `test_cmp_cns_prv.py` |
| Acceso por rol (Gerente escribe; Agrónomo solo consulta; los demás, 403) y vistas | `test_proveedores_vistas.py` |
| Concurrencia: dos altas con el mismo CUIT (una gana) | `test_proveedores_concurrencia.py` |

### Pantallas (prototipo: `tabPrv` línea 2638, `VIEWS.c_prv` 2643, `VIEWS.c_prvform` 2661)

Pestaña «Proveedores» de «Compras»: lista con filtros (estado, texto, tipo de insumo), ficha y formulario. El Agrónomo ve la pestaña sin botones
de alta, modificar ni baja. Los pedidos y órdenes de la ficha (regla 4 de CMP-CNS-PRV) se completan en CMP-02a y CMP-03.
