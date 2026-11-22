# Casos de uso · comercial · Clientes

Copia para el repo de los casos COM-ALT-CLT, COM-MOD-CLT, COM-BAJ-CLT y COM-CNS-CLT del documento de Drive «CU · ABM Cliente ·
COM-ALT/MOD/BAJ/CNS-CLT (v0.1)», del 20/11/2026 (carpeta «InfoPonia · Comercial · Análisis»; todavía no está en «CU extendidos»).
Reemplazan a CU-78 a CU-81 de «Documentacion para la IA». Cotejado con pendientes_CU (PCU, secciones 1 a 16), con pendientes_MD hasta
MD-113 más MD-114 a MD-139 del documento comercial, y con el glosario.

Son casos de uso breves (de alto nivel). **El código va en la app `comercial`** (D-37); el archivo de pruebas es
`comercial/tests/test_com_alt_clt.py` y los análogos.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las
postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| COM-ALT-CLT | Alta Cliente | Vendedor o Gerente | `comercial/tests/test_com_alt_clt.py` |
| COM-MOD-CLT | Modificar Cliente | Vendedor o Gerente | `comercial/tests/test_com_mod_clt.py` |
| COM-BAJ-CLT | Baja Cliente | Gerente | `comercial/tests/test_com_baj_clt.py` |
| COM-CNS-CLT | Consultar Cliente | Vendedor o Gerente | `comercial/tests/test_com_cns_clt.py` |

---

## COM-ALT-CLT · Alta Cliente

**Actores:** Vendedor o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** registrar un cliente nuevo, o reactivar uno dado de baja, para poder pactarle compra-ventas o suministros.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Vendedor o de Gerente.

**Postcondición:**

a. Se creó un cliente en estado «activo», con su CUIT, su nombre (razón social, o nombre y apellido) y los datos de contacto indicados.

b. Si se indicaron, se crearon sus direcciones, urbanas o rurales, ubicadas en las localidades elegidas, en estado «activo».

c. Si el CUIT era de un cliente inactivo y el actor eligió reactivarlo, ese cliente pasó a «activo» con los datos que haya corregido, en
lugar de crearse uno nuevo. Si lo reactivó un Vendedor, el Gerente recibió una notificación dentro del Sistema.

d. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del cliente creado o reactivado y de cada dirección creada.

**Reglas:**

1. El CUIT es obligatorio, tiene 11 dígitos con dígito verificador (módulo 11, el mismo cálculo que el CUIT de la organización) y se
   acepta con o sin guiones. Es único entre todos los clientes, activos e inactivos (MD-48).
2. Si el CUIT ya es de un cliente activo, el Sistema lo informa y ofrece abrirlo. Si es de un cliente inactivo, ofrece reactivarlo
   (MD-48). El Vendedor y el Gerente pueden reactivar; si reactiva un Vendedor, se notifica al Gerente, porque es quien da de baja a los
   clientes (MD-47).
3. El cliente es una persona jurídica o una persona física: en la primera, la razón social es obligatoria; en la segunda, el nombre y el
   apellido.
4. El teléfono es opcional y sigue el formato de D-21 (8 a 15 dígitos, con espacios y los signos + - ( )).
5. El correo es opcional, pero sin correo no se puede pactar un suministro y el comprobante de una compra-venta se entrega impreso (regla
   18 de 8.20).
6. Las direcciones son opcionales (MD-128) y siguen las reglas 2 y 3 de PROD-ALT-INV y el formato de D-39: la provincia, el departamento y
   la localidad se eligen de listas precargadas desde Georef y no se crean desde acá (MD-88). Un cliente puede tener varias direcciones
   (por ejemplo, una por sucursal), pero no dos idénticas. La dirección se exige recién cuando hace falta: en una compra-venta con envío y
   en cada detalle de un suministro.
7. Si lo incluyen Registrar Compra-venta o Pactar Suministro (extensión 4a de cada uno), al terminar se vuelve a ese caso de uso con el
   cliente creado o reactivado. El alta queda registrada aunque la venta o el contrato no se confirmen.
8. Un cliente puede darse de alta sin contratos (MD-40).

## COM-MOD-CLT · Modificar Cliente

**Actores:** Vendedor o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** actualizar los datos de contacto y las direcciones de un cliente, activo o inactivo.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Vendedor o de Gerente.

b. Si cambia el CUIT, no existe otro cliente con el CUIT nuevo.

**Postcondición**, según lo que haya hecho el actor:

a. Se actualizaron los datos indicados.

b. Si agregó una dirección, quedó creada en estado «activo».

c. Si cambió una dirección que no usa ninguna venta ni ningún detalle de suministro, quedó actualizada.

d. Si cambió una dirección que ya usa una venta o un detalle de suministro, se creó una dirección nueva con los datos corregidos y la
anterior pasó a «inactiva»; los contratos que la usaban la conservan (regla 3 de 8.18; MD-19).

e. Si desactivó una dirección, quedó «inactiva» y ya no se ofrece para contratos nuevos.

f. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del cliente y de cada dirección afectada, y los cambios.

**Reglas:**

1. Los datos siguen las reglas 1 y 3 a 6 de COM-ALT-CLT.
2. Se puede modificar un cliente inactivo, porque puede tener suministros vigentes que se siguen ejecutando (regla 2 de 8.18). Modificarlo
   no lo reactiva.
3. No se puede quitar el correo de un cliente con un suministro vigente, porque los enlaces de confirmación y las quejas solo llegan por
   correo (regla 18 de 8.20).
4. Una dirección que usa una venta o un detalle de suministro no se modifica ni se borra: se reemplaza por una nueva (regla 3 de 8.18). Una
   dirección que nada usa puede corregirse o borrarse.
5. Si lo incluyen Registrar Compra-venta o Pactar Suministro (dirección nueva o correo faltante), al terminar se vuelve a ese caso de uso.
   El cambio queda registrado aunque la venta o el contrato no se confirmen.

## COM-BAJ-CLT · Baja Cliente

**Actores:** Gerente (MD-47).

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** dar de baja lógica a un cliente para que no se le pacten contratos nuevos.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

b. El cliente está en estado «activo».

**Postcondición:**

a. El cliente pasó a «inactivo». Sus direcciones no cambiaron.

b. Sus contratos vigentes o abiertos siguen ejecutándose (regla 2 de 8.18).

c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del cliente y el cambio de estado.

**Reglas:**

1. La baja no se bloquea. Antes de confirmar, el Sistema informa lo que el cliente tiene pendiente (entregas sin cobrar, suministros
   vigentes, compra-ventas abiertas y quejas o discrepancias pendientes) y que todo eso sigue su curso (MD-47).
2. Un cliente inactivo no aparece para contratos nuevos, pero sí en las consultas y en los cobros.
3. La baja no borra datos: el cliente se reactiva desde COM-ALT-CLT (regla 2), y puede hacerlo el Vendedor o el Gerente.

## COM-CNS-CLT · Consultar Cliente

**Actores:** Vendedor o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** buscar un cliente y ver sus datos y su situación comercial.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Vendedor o de Gerente.

**Postcondición:**

a. No se registra ningún cambio.

**Reglas:**

1. Se busca por CUIT, por razón social o por nombre y apellido, y se filtra por estado.
2. La ficha muestra los datos del cliente; sus direcciones, activas e inactivas; sus contratos, con su estado; y sus entregas sin cobrar,
   con el monto a cobrar y el vencimiento.
3. El Vendedor ve todos los clientes, porque un cliente puede comprarle a varios Vendedores, pero de los contratos y las entregas solo ve
   los de sus contratos. El Gerente ve todo.

---

## Cómo se aplica en la ronda «Comercial 1» (D-44, D-57)

Tarea: **COM-01**. Todo lo de este archivo se implementa, salvo lo marcado «Se completa en COM-NN», que necesita clases que todavía no
existen (está también en `docs/disparadores.md`, «Completan el ABM de cliente»). Decisiones de aplicación:

- **CUIT (regla 1).** `maestros.validadores.validar_cuit` (D-58, `docs/api/direcciones.md`): se guarda sin guiones y se muestra
  `XX-XXXXXXXX-X`. Único entre activos e inactivos, con restricción de la base; dos altas simultáneas con el mismo CUIT dan al segundo el
  mismo error de campo, nunca un 500 (`docs/patrones/abm.md`, sección 2, paso 6).
- **CUIT repetido (regla 2).** Antes de crear, el servicio busca el CUIT normalizado:
  - si es de un cliente **activo**, rechaza con el código `cuit_de_cliente_activo` y el error lleva el id del cliente, para que la
    pantalla ofrezca «Abrir su ficha»;
  - si es de uno **inactivo**, rechaza con `cuit_de_cliente_inactivo` y el id, y la pantalla ofrece «Reactivarlo».
- **Reactivar (postcondición c, regla 2 y regla 3 de BAJ).** Es parte de **este** caso de uso, no de MOD (manda el CU sobre
  `docs/patrones/abm.md`, sección 3). «Reactivarlo» abre el **mismo formulario del alta** con los datos guardados del cliente, que el actor
  puede corregir; al confirmar, `reactivar_cliente(actor, cliente_id, datos)` lo pasa a «activo» con esos datos y suma las direcciones
  nuevas que haya cargado. Desde la ficha de un cliente inactivo, «Reactivar» lleva al mismo formulario. Acción de auditoría:
  `reactivacion_cliente`. Si actúa un Vendedor, `notificar_al_gerente` con:
  - título: «Cliente reactivado: {cliente}»;
  - detalle: «{Nombre Apellido del Vendedor} reactivó al cliente {cliente} (CUIT {CUIT}). Si no correspondía, podés darlo de baja desde
    su ficha.»
  Sin Gerente activo, el aviso se omite y la reactivación no falla (D-14).
- **Tipo de cliente (regla 3).** `tipo_cliente` (`juridica` / `fisica`, `docs/modelo/comercial.md`). Al guardar se conservan solo los
  datos del tipo elegido; los del otro se vacían. Cambiar el tipo en MOD está permitido (corrige un error de carga) y se audita.
- **Teléfono (regla 4).** `core.validadores.validar_telefono` (D-21), como en las cuentas.
- **Correo (regla 5).** Opcional, con el validador de correo de Django. Sin correo, la ficha y el formulario muestran «Necesario para
  pactar suministros» (texto del prototipo).
- **Direcciones (regla 6).** Con la API de `maestros` (`docs/api/direcciones.md`) y la tabla `DireccionCliente` (D-58). Se cargan en el
  mismo formulario del cliente: primero el tipo (urbana o rural), después sus datos y la localidad; «Agregar dirección» la suma a la lista
  del formulario y el alta las crea todas en la misma transacción. «No dos idénticas»: la clave de D-58, punto 6, contra las direcciones
  **activas** del cliente y contra las otras del mismo formulario; el error es `direccion_repetida`, en el campo de la dirección.
- **Volver al caso de uso que lo incluye (regla 7 de ALT y regla 5 de MOD).** Se completa en COM-02 (Registrar Compra-venta) y en COM-03
  (Pactar Suministro): el formulario acepta un parámetro `volver` con la URL interna a la que regresa, validada con
  `url_has_allowed_host_and_scheme`, como la vuelta a la pantalla pedida de D-29. En COM-01 el parámetro existe y se prueba, pero ninguna
  pantalla lo usa todavía.
- **MOD con cliente inactivo (regla 2).** Se puede, y no lo reactiva. La ficha de un inactivo muestra «Modificar» y «Reactivar».
- **Correo con suministro vigente (regla 3 de MOD).** Se completa en COM-03: `comercial/servicios/clientes.py` tiene la función
  `impide_quitar_el_correo(cliente) -> bool`, que en COM-01 devuelve siempre `False`; COM-03 le suma la consulta de suministros vigentes y
  la prueba.
- **Dirección usada (regla 4 de MOD, postcondiciones c y d).** `direcciones_en_uso(ids)`: en COM-01 devuelve un conjunto vacío, así que
  toda dirección se corrige en el lugar (`corregir_direccion`, si sigue siendo de la misma zona) o se borra (`borrar_direccion`, después de
  borrar su `DireccionCliente`). Si la corrección cambia la zona (urbana a rural o al revés), es otra dirección: se crea la nueva, el
  `DireccionCliente` pasa a apuntar a ella y se borra la anterior (`docs/api/direcciones.md`, «Cambio de zona»); en la auditoría va en
  `direcciones_corregidas` con la referencia nueva. Se
  completa en COM-02 (compra-ventas con envío) y COM-03 (detalles de suministro): con la dirección en uso, corregir crea otra y pasa la
  anterior a «inactiva», y «Borrar» no se ofrece.
- **Desactivar una dirección (postcondición e).** Se puede siempre; una inactiva se muestra con su marca y no se reactiva (para usarla de
  nuevo se carga otra).
- **Baja (BAJ).** Solo el Gerente activo; el Vendedor no ve el botón y la URL le da 403. La ventana informa lo pendiente (regla 1) con
  `pendientes_del_cliente(cliente, actor) -> list[str]`, que en COM-01 devuelve una lista vacía y la ventana dice «No tiene contratos ni
  entregas pendientes.». **Se completa en** COM-02 (compra-ventas abiertas), COM-03 (suministros vigentes), COM-06 (entregas sin cobrar,
  quejas y discrepancias pendientes) y COM-08 (estado de pago). La baja no se bloquea nunca. Acción de auditoría: `baja_cliente`.
- **Consulta (CNS).**
  - Lista: búsqueda por CUIT (desde 2 dígitos, con o sin guiones), por razón social o por nombre y apellido, sin distinguir mayúsculas
    (`icontains`; sin `unaccent`, `docs/temas_abiertos.md`); filtro por estado; orden por nombre visible y después id; 50 por página.
    Columnas de COM-01: cliente (con su tipo), CUIT, contacto (correo y teléfono), direcciones activas, estado y acciones. La columna
    «Contratos vigentes» la suma COM-02.
  - Ficha: datos y direcciones (activas e inactivas). **Se completa en** COM-02 y COM-03 (contratos, con el alcance del Vendedor: solo los
    suyos) y COM-06 y COM-08 (entregas sin cobrar, con el monto a cobrar y el vencimiento). Mientras no existan, la ficha **no** muestra
    esas tarjetas (D-25: solo se muestra lo que existe).
  - Alcance: `Cliente.objects.en_alcance_de(actor)`, un único lugar (D-28): Gerente y Vendedor activos ven todos; cualquier otro rol, 403.
- **Bloqueos.** MOD, BAJ y la reactivación toman el cliente con `FOR NO KEY UPDATE` y lo releen; MOD toma además sus `DireccionCliente`,
  en orden de id, antes de corregir o borrar. Sin cambios no se escribe ni se audita (D-28). Dos modificaciones simultáneas: gana la última
  (como D-40 con el invernadero), salvo el CUIT, que respalda la base.
- **Auditoría (D-36).** Acciones `alta_cliente`, `modificacion_cliente`, `baja_cliente` y `reactivacion_cliente`. Afectados: el cliente y
  cada dirección creada, corregida, desactivada o borrada. En `datos`, las claves `direcciones_creadas`, `direcciones_corregidas`,
  `direcciones_reemplazadas` (la anterior, ya inactiva), `direcciones_desactivadas` y `direcciones_borradas`, como listas de
  `referencia()`; en `cambios`, los datos del cliente con «antes» y «después». El CUIT, como texto con guiones.

## Pantallas

Guía visual: `docs/prototipos/comercial/`. Buscá la función y leé solo esa parte (y sus sobrescrituras, si las tiene: ver el
`README.md`).

| Pantalla | Función en el prototipo | Casos de uso |
|---|---|---|
| Comercial · pestaña «Clientes» | `VIEWS.com`, `tabClientes` | COM-CNS-CLT |
| Ficha del cliente | `VIEWS.cli` | COM-CNS-CLT, botones de COM-MOD-CLT, COM-BAJ-CLT y la reactivación |
| Registrar, modificar o reactivar cliente | `VIEWS.cliform`, `INIT.cliform`, `ACT['cliform-ok']`, `ACT.reactcli`, `dirForm`, `dirAdd`, `ACT.dirdesact` | COM-ALT-CLT, COM-MOD-CLT |
| Dar de baja | `MODALS.bajacli` | COM-BAJ-CLT |

**Lo que difiere del prototipo (manda el CU, L7):**

- El formulario del prototipo no deja **corregir** ni **borrar** una dirección, solo agregar y desactivar: el CU (regla 4 de MOD,
  postcondiciones c y d) pide las dos cosas. Cada dirección de la lista tiene «Corregir» (carga sus datos en la caja de dirección) y
  «Borrar» (solo si no está en uso); las dos se confirman al guardar el cliente.
- El prototipo reactiva desde la ficha con un clic, sin dejar corregir: el CU (postcondición c) pide que pueda corregir los datos. Va al
  formulario.
- La caja de dirección del prototipo no tiene «Referencias» para la urbana: se agrega, como en el invernadero (D-39).
- Los textos van con voseo («Ingresá el CUIT», «revisá el dígito verificador»), como el resto del sistema.

**Textos explicativos** (criterio del estudiante: «alguien nuevo debe entender el sistema rápidamente»), además de los del prototipo:

- Bajo el título de la lista: «Los clientes son de toda la organización: cualquier Vendedor les puede vender. Solo el Gerente los da de
  baja.»
- En el formulario, bajo «Direcciones»: «Son opcionales. Se piden recién para una compra-venta con envío o para un suministro. Un cliente
  puede tener varias (una por sucursal), pero no dos iguales.»
- En la ficha de un cliente inactivo: «Cliente dado de baja. Sus contratos vigentes siguen ejecutándose; no puede celebrar contratos
  nuevos.» (texto del prototipo).
- En la ventana de baja: «No podrá celebrar contratos nuevos. Lo que tenga pendiente sigue su curso. Se puede reactivar después.»

## Para más adelante

Cada punto está también en `docs/disparadores.md`, «Completan el ABM de cliente».

- COM-02: contratos de compra-venta en la ficha y en la lista; compra-ventas abiertas en la ventana de baja; direcciones en uso por una
  compra-venta con envío; el regreso a COM-REG-CVT (regla 7 de ALT, regla 5 de MOD).
- COM-03: suministros en la ficha, la lista y la baja; direcciones en uso por un detalle de suministro; la regla 3 de MOD (correo con
  suministro vigente); el regreso a COM-PCT-SUM.
- COM-06: entregas sin cobrar (monto a cobrar y vencimiento) en la ficha y en la baja; quejas y discrepancias pendientes en la baja.
- COM-08: el estado de pago de cada entrega (pagada o en mora) en la ficha.

## Solo prototipo

Los de `docs/prototipos/comercial/README.md`, «Elementos del prototipo que no van en el sistema». En estas pantallas, además:

- La columna y el dato «Deuda» de la ficha con datos de ejemplo (llegan con COM-06 y COM-08).
- Los identificadores `CL-01` a `CL-05`.
- La lista de muestra de localidades (`GEOP`): el sistema usa Georef.
