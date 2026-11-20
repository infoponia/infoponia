# Casos de uso · maestros · Invernadero

Copia para el repo de los casos PROD-ALT-INV, PROD-MOD-INV, PROD-BAJ-INV y PROD-CNS-INV del documento de Drive
«CU extendidos», consultados el 18/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Son casos de uso breves (de alto nivel), no extendidos: tienen precondiciones, postcondiciones y reglas, sin escenario
principal paso a paso. Reemplazan a CU-64 y CU-65 de la Documentación para la IA.

**El código va en la app `maestros`, no en `produccion`** (D-37): el código del caso de uso (`PROD-...`) viene del
bloque del modelo de dominio y no cambia. Por eso el archivo de pruebas es `maestros/tests/test_prod_alt_inv.py`.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa
`test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-ALT-INV | Alta Invernadero | Gerente | `maestros/tests/test_prod_alt_inv.py` |
| PROD-MOD-INV | Modificar Invernadero | Gerente | `maestros/tests/test_prod_mod_inv.py` |
| PROD-BAJ-INV | Baja Invernadero | Gerente | `maestros/tests/test_prod_baj_inv.py` |
| PROD-CNS-INV | Consultar Invernadero | Gerente y Agrónomo | `maestros/tests/test_prod_cns_inv.py` |

---

## PROD-ALT-INV · Alta Invernadero

**Actores:** Gerente. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** registrar un invernadero nuevo con su nombre, su dirección y, si se conoce, su personal, para que el
Agrónomo pueda registrar sus sectores y empezar a producir.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.
b. No existe otro invernadero con el mismo nombre.

**Postcondición:**

a. Se creó un invernadero en estado «activo», con su nombre, sin sectores, sin insumos habilitados y sin sistema IoT.
b. Se creó su dirección, urbana o rural, con sus datos, ubicada en la localidad elegida.
c. Si se asignaron, el invernadero quedó asociado a su Agrónomo, su Capataz y su Vendedor (R051, R149 y R097).
d. Por cada uno de esos tres roles que quedó sin asignar, quedó para el Gerente una alerta activa «invernadero sin
   {rol} activo».
e. Cada persona asignada recibió una notificación dentro del Sistema que le avisa que quedó a cargo del invernadero.
f. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del invernadero creado.

**Reglas:**

1. El nombre es obligatorio y único entre todos los invernaderos, activos o inactivos, sin distinguir mayúsculas ni
   espacios al principio o al final.
2. La dirección es urbana o rural. Urbana: la calle y el número son obligatorios; el piso, el departamento (unidad), el
   barrio y las referencias, opcionales. Rural: la ruta o camino y el kilómetro son obligatorios; el lote, opcional.
3. La provincia, el departamento y la localidad se eligen de listas encadenadas, precargadas con las localidades de
   Georef. No se escriben ni se crean desde este caso de uso. Si el invernadero está en un paraje que no figura como
   localidad, se elige la localidad más cercana, y la ruta y el kilómetro dan la ubicación exacta.
4. El personal es opcional: el invernadero puede existir sin él y asignarse después con PROD-MOD-INV (R051, R149, R097
   y R134 en 0..1). Se ofrecen solo las cuentas activas de cada rol. Una misma cuenta puede estar a cargo de varios
   invernaderos.
5. El Técnico solo hace falta si el invernadero tiene sistema IoT. Como un invernadero nuevo no lo tiene, no genera la
   alerta de Técnico faltante.
6. Los transportistas no se asignan acá: cada uno se vincula a su invernadero desde su cuenta (USR-ALT-USR y
   USR-MOD-USR).
7. El alta no crea sectores, porque los registra el Agrónomo del invernadero. Mientras no tenga sectores, el
   invernadero muestra la marca «sin sectores: todavía no se puede sembrar».
8. El sistema IoT se registra en el bloque IoT, no acá.

---

## PROD-MOD-INV · Modificar Invernadero

**Actores:** Gerente. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** actualizar el nombre, la dirección o el personal de un invernadero, o reactivar uno dado de baja.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.
b. Si cambia el nombre, no existe otro invernadero con el nombre nuevo.

**Postcondición**, según lo que haya hecho el actor:

a. Se actualizaron el nombre y la dirección indicados.
b. Si asignó una persona a un rol, o reemplazó a la que estaba, lo que tenía el saliente en ese invernadero pasó a la
   persona entrante (MD-60): al Capataz, las órdenes a realizar del invernadero; al Técnico, los mantenimientos a
   realizar del invernadero; al Vendedor, los contratos vigentes o abiertos del invernadero (regla 8 de 8.21); al
   Agrónomo, las alertas activas del invernadero. Además, si el Agrónomo saliente sigue activo, se cancelaron sus
   pedidos sin orden de compra con destino a ese invernadero y se avisó a los proveedores invitados (MD-62). La alerta
   «invernadero sin {rol} activo» de ese rol pasó a «resuelta».
c. Cada persona asignada recibió una notificación dentro del Sistema con el invernadero y lo que recibió: la cantidad
   de órdenes, mantenimientos, contratos y alertas.
d. Si dejó un rol sin asignar, quedó para el Gerente una alerta activa «invernadero sin {rol} activo». La del Técnico
   solo se genera si el invernadero tiene sistema IoT.
e. Si reactivó el invernadero, quedó en estado «activo», sus sectores y sus insumos siguieron inactivos, y quedó una
   alerta «invernadero sin {rol} activo» por cada rol sin una persona activa.
f. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del invernadero y los cambios.

**Reglas:**

1. El nombre y la dirección siguen las reglas 1 a 3 de PROD-ALT-INV.
2. Antes de confirmar un cambio de personal, el Sistema informa qué pasa al guardar: qué recibe la persona entrante y,
   si un rol queda vacío, que no se podrán realizar las tareas que dependen de él hasta que se asigne a alguien.
3. Si se quita a una persona sin reemplazarla, lo que tenía en el invernadero queda sin responsable y pasa a quien se
   asigne después.
4. Se ofrecen solo las cuentas activas de cada rol. Si la persona asignada está inactiva, se muestra con esa marca
   hasta que se la reemplace.
5. Un invernadero inactivo no se modifica: solo se reactiva. Después de reactivarlo, se modifica como cualquier otro.
6. La reactivación no reactiva sus sectores ni sus insumos. Los sectores los reactiva el Agrónomo con PROD-MOD-SCT, y
   los insumos se vuelven a habilitar con Habilitar Insumo en Invernadero.
7. El sistema IoT no se modifica acá: su estado lo informa el bloque IoT.

---

## PROD-BAJ-INV · Baja Invernadero

**Actores:** Gerente. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** dar de baja lógica un invernadero que deja de operar, sin perder su historial.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.
b. El invernadero está activo.
c. El invernadero no tiene lotes activos.
d. El invernadero no tiene órdenes de trabajo a realizar, de ningún tipo.
e. El invernadero no tiene partidas en cámara disponibles.
f. Ninguno de sus insumos tiene stock actual distinto de cero, cantidad en tránsito ni una orden de compra aprobada sin
   recibir.
g. El invernadero no tiene transportistas activos vinculados.
h. El invernadero no tiene un sistema IoT activo.

**Postcondición:**

a. El invernadero quedó en estado «inactivo» (baja lógica).
b. Todos sus sectores, incluidos los que estaban fuera de servicio, quedaron en estado «inactivo».
c. Todos sus insumos habilitados quedaron inactivos en ese invernadero.
d. El personal asignado se conservó como historial.
e. Las alertas activas del invernadero pasaron a «resuelta», y el invernadero dejó de generar alertas.
f. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del invernadero y el cambio de estado, y
   otro por cada sector e insumo que cambió de estado.

**Reglas:**

1. La baja es lógica: el invernadero conserva sus sectores, sus lotes finalizados, su bitácora, sus movimientos y su
   contabilidad.
2. Si no se cumple alguna de las precondiciones c a h, el Sistema no da de baja el invernadero e informa todo lo que lo
   impide, cada cosa con cómo resolverla: los lotes activos se cosechan o se registra su merma; las órdenes se
   concretan o se cancelan; las partidas en cámara se venden o se registra su merma; el stock se usa o se ajusta a
   cero; la mercadería en camino se recibe o se cierra la orden de compra; los transportistas activos se vinculan a
   otro invernadero con USR-MOD-USR; el sistema IoT se da de baja en el bloque IoT.
3. Los transportistas inactivos vinculados no impiden la baja: quedan como historial, igual que el resto del personal.
4. Un invernadero inactivo no aparece en las planificaciones, en los pedidos, en la asignación de stock ni en el
   reintento diario de las entregas.
5. Se reactiva con PROD-MOD-INV.

---

## PROD-CNS-INV · Consultar Invernadero

**Actores:** Gerente y Agrónomo, cada uno con su alcance (regla 1). **Tipo:** secundario, esencial. **Versión:** 0.2

**Objetivo:** consultar los invernaderos, ver su estado, su capacidad y su personal, y acceder a la ficha de cada uno.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente o de Agrónomo.

**Postcondición:**

a. No se producen cambios en el Sistema.

**Reglas:**

1. Alcance: el Gerente consulta todos los invernaderos, activos e inactivos. El Agrónomo, solo los activos a su cargo.
   El Capataz no consulta invernaderos: trabaja desde su bandeja de órdenes y registra en la bitácora.
2. En la lista, de cada invernadero se ve su nombre, su estado y si tiene sistema IoT; su dirección; el porcentaje de
   agujeros ocupados; la cantidad de sectores y de lotes activos; y su personal, con la marca «sin asignar» o
   «inactivo» cuando corresponde. Se marcan los invernaderos sin sectores («todavía no se puede sembrar») y los que
   tienen personal por asignar.
3. En la ficha se ven la ubicación (la dirección, el departamento, la zona urbana o rural y el estado del sistema IoT);
   el equipo; la capacidad por tipo de etapa (los agujeros, los libres y la cantidad de sectores); y pestañas con los
   sectores, los lotes activos, el stock en cámara y la bitácora (PROD-CNS-BIT).
4. Si al invernadero le falta personal, la ficha lo avisa. Al Gerente le ofrece ir a PROD-MOD-INV para asignarlo.
5. En su Inicio, el Gerente ve los invernaderos con personal por asignar, con un acceso a PROD-MOD-INV para cada uno.
6. Desde la ficha, el Agrónomo a cargo inicia los casos de uso de sus sectores y de su bitácora (PROD-REG-EVT,
   PROD-REG-MRM y PROD-REG-APL). El Gerente solo modifica, da de baja o reactiva el invernadero y consulta la bitácora,
   sin registrar.
7. La consulta no se audita (SEG-14).

---

## Pantallas

Guía visual: `docs/prototipos/produccion/`. Buscá la función con Grep y leé solo esa parte.

| Pantalla | Función en el prototipo | Casos de uso |
|---|---|---|
| Lista de invernaderos (tarjeta de cada uno) | `invCard`, `invListBody` | PROD-CNS-INV |
| Ficha del invernadero, con sus pestañas | `VIEWS.inv`, `capInv`, `people`, `person` | PROD-CNS-INV |
| Alta y modificación | `VIEWS['inv-form']`, `invErrs`, `INIT['inv-form']`, `ACT['inv-save']` | PROD-ALT-INV, PROD-MOD-INV |
| Baja y reactivación | `MODALS['inv-baja']`, `ACT['inv-baja-ok']`, `ACT['inv-react']` | PROD-BAJ-INV, PROD-MOD-INV |
| Personal por asignar, en el Inicio del Gerente | `personalCard`, `alertasInv` | PROD-CNS-INV (regla 5) |
| Pestaña de cámara (solo lectura) | `camaraTab` | PROD-CNS-INV (regla 3) |

## Para más adelante

Partes que dependen de clases que todavía no existen. Siguen la regla de D-04: se agregan cuando se programe la tabla
destino. Cada una está también en `docs/disparadores.md`.

- **Alertas** (postcondición d de PROD-ALT-INV; postcondiciones b, d y e de PROD-MOD-INV; postcondición e de
  PROD-BAJ-INV): las genera y las resuelve MAE-02, que crea `Alerta` (D-38).
- **Notificaciones** (postcondición e de PROD-ALT-INV, postcondición c de PROD-MOD-INV): hecho en NOT-01 (D-42).

  por decidir si se construye el mecanismo.
- **Lo que recibe la persona entrante** (postcondición b de PROD-MOD-INV): órdenes de trabajo, mantenimientos,
  contratos y pedidos. Cada uno se conecta cuando exista su app.
- **Precondiciones c a h de PROD-BAJ-INV:** lotes, órdenes, partidas en cámara, stock de insumos, transportistas y
  sistema IoT. Mientras esas clases no existan, cada condición se da por cumplida, y se conecta con un punto de
  extensión (regla A4 de D-37) cuando la app que la tiene se programe.
- **Capacidad, sectores, lotes y bitácora de la ficha** (regla 3 de PROD-CNS-INV): llegan con sus propias tareas.
- **Transportistas vinculados** (regla 6 de PROD-ALT-INV, regla 3 de PROD-BAJ-INV): es R155, que está en el disparador
  «Cuando exista Invernadero».

## Solo prototipo

Lo que el prototipo muestra y no va en el sistema. La lista completa está en
`docs/prototipos/produccion/README.md`. Lo que toca a estas pantallas:

- El selector «Solo prototipo — ver como», para cambiar de rol.
- El aviso de que Georef está recortado en el formulario de dirección: el sistema trae todas las localidades.
- La nota del Dashboard en el inicio del Gerente.
- La ventana «Registrar sistema IoT» (`MODALS['iot-info']`): el estado del sistema IoT lo informa el bloque IoT.
- Los nombres fijos en los textos de las notificaciones.
- Que `ACT['inv-save']` notifique también a la persona saliente y avise de los cambios de nombre: el caso de uso
  solo notifica a la persona asignada (postcondición c de PROD-MOD-INV), y manda el caso de uso (L7).
