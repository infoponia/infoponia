# Casos de uso · comercial · Vehículos

Copia para el repo de los casos COM-ALT-VEH, COM-MOD-VEH, COM-BAJ-VEH y COM-CNS-VEH del documento de Drive «CU · ABM Vehículo ·
COM-ALT/MOD/BAJ/CNS-VEH (v0.1)», del 20/11/2026 (carpeta «InfoPonia · Comercial · Análisis»; todavía no está en «CU extendidos»).
Reemplazan a CU-23, CU-07 y CU-30 de «Documentacion para la IA». Cotejado con pendientes_CU (PCU, secciones 1 a 16), con pendientes_MD
hasta MD-113 más MD-114 a MD-139 del documento comercial (MD-118, MD-129 y MD-138), y con el glosario.

Son casos de uso breves (de alto nivel). **El código va en la app `comercial`** (D-37); el archivo de pruebas es
`comercial/tests/test_com_alt_veh.py` y los análogos.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: `test_regla_<numero>_<que_espera>`, `test_post_<letra>_<que_espera>` y, para las precondiciones,
`test_pre_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| COM-ALT-VEH | Alta Vehículo | Gerente | `comercial/tests/test_com_alt_veh.py` |
| COM-MOD-VEH | Modificar Vehículo | Gerente | `comercial/tests/test_com_mod_veh.py` |
| COM-BAJ-VEH | Baja Vehículo | Gerente | `comercial/tests/test_com_baj_veh.py` |
| COM-CNS-VEH | Consultar Vehículo | Gerente | `comercial/tests/test_com_cns_veh.py` |

---

## COM-ALT-VEH · Alta Vehículo

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** registrar un vehículo con el que los transportistas hacen las entregas con envío y, si ya se sabe, asignarle su
transportista.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

b. No existe otro vehículo con la misma patente.

**Postcondición:**

a. Se creó un vehículo en estado «activo», sin ruta iniciada, con su patente, su tipo, su marca, su modelo y su capacidad de carga.

b. Si se asignó, el vehículo quedó asociado a su transportista (R073), y el transportista recibió una notificación dentro del Sistema.

c. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del vehículo creado.

**Reglas:**

1. La patente es obligatoria y única entre todos los vehículos, activos e inactivos. Se aceptan los formatos argentinos AAA123 y AA123AA,
   sin distinguir mayúsculas y sin espacios ni guiones, y se guarda en mayúsculas (MD-129).
2. El tipo se elige de una lista cerrada: camioneta, furgón, camión, utilitario y moto (MD-129). La marca y el modelo son textos
   obligatorios.
3. La capacidad de carga es obligatoria y mayor que cero, en kilogramos con hasta dos decimales. Es el peso máximo que el vehículo lleva
   en el día, en un solo viaje (regla 6 de 8.12).
4. El transportista es opcional (R073 en 0..1). Solo se ofrecen los transportistas activos que no tienen otro vehículo. El vehículo
   trabaja para el invernadero de su transportista (R155).
5. Sin transportista, el vehículo no participa de ninguna planificación hasta que se le asigne uno con COM-MOD-VEH.

## COM-MOD-VEH · Modificar Vehículo

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** actualizar los datos de un vehículo, cambiar o quitar su transportista, o reactivar un vehículo dado de baja.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

b. El vehículo no está en ruta (MD-118).

c. Si cambia la patente, no existe otro vehículo con la patente nueva.

**Postcondición**, según lo que haya hecho el actor:

a. Se actualizaron los datos indicados.

b. Si asignó, cambió o quitó el transportista, el vehículo quedó con el nuevo o sin ninguno, y el transportista entrante y el saliente
recibieron una notificación dentro del Sistema.

c. Si reactivó el vehículo, quedó en estado «activo», sin transportista.

d. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del vehículo y los cambios.

**Reglas:**

1. Los datos siguen las reglas 1 a 4 de COM-ALT-VEH.
2. No se baja la capacidad de carga por debajo del peso que el vehículo ya tiene asignado en cualquier fecha de hoy en adelante, es decir,
   la suma de las entregas no canceladas de su transportista en esa fecha (regla 6 de 8.12). El Sistema informa la fecha con más carga y
   sus entregas, para reasignarlas primero con COM-ASG-TRP.
3. No se quita ni se cambia el transportista si ese transportista tiene entregas «a realizar»: quedaría sin vehículo y no podría
   concretarlas. El Sistema muestra esas entregas para reasignarlas primero con COM-ASG-TRP.
4. Un vehículo inactivo no se modifica: solo se reactiva. Después de reactivarlo, se modifica como cualquier otro y se le puede asignar un
   transportista.

## COM-BAJ-VEH · Baja Vehículo

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** dar de baja lógica a un vehículo que ya no se usa.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

b. El vehículo está «activo» y no está en ruta (MD-118).

c. Si tiene transportista, ese transportista no tiene entregas «a realizar».

**Postcondición:**

a. El vehículo pasó a «inactivo» y quedó sin transportista.

b. Si tenía transportista, recibió una notificación dentro del Sistema de que quedó sin vehículo y no recibirá entregas nuevas.

c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del vehículo y los cambios.

**Reglas:**

1. Si el transportista tiene entregas «a realizar», el Sistema las muestra y no permite la baja hasta reasignarlas con COM-ASG-TRP (mismo
   criterio que la regla 3 de COM-MOD-VEH).
2. Un vehículo inactivo no se ofrece para asignarle un transportista ni cuenta como candidato en Planificar Entrega (regla 13 de 8.12). Sus
   entregas pasadas conservan el vínculo con su transportista.

## COM-CNS-VEH · Consultar Vehículo

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver los vehículos de la organización y su situación.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

**Postcondición:**

a. No se registra ningún cambio.

**Reglas:**

1. Se busca por patente, tipo o transportista, y se filtra por estado y por invernadero (el de su transportista).
2. La ficha muestra los datos del vehículo, su transportista y su invernadero, si está en ruta hoy y la carga asignada frente a su
   capacidad en los próximos días.

---

## Cómo se aplica en la ronda «Comercial 1» (D-44, D-57)

Tarea: **COM-01**. Todo lo de este archivo se implementa, salvo lo marcado «Se completa en COM-05», que necesita `Entrega` (está también
en `docs/disparadores.md`, «Completan el ABM de vehículo»). Decisiones de aplicación:

- **Quién.** Solo el Gerente activo. El Vendedor no ve la pestaña «Vehículos» y las URL le dan 403 (como al resto de los roles).
- **Patente (regla 1 de ALT y precondición c de MOD).** Se normaliza (mayúsculas, sin espacios ni guiones) antes de validar el formato y la
  unicidad. Restricción de la base: única y con su `CheckConstraint` de formato (`docs/modelo/comercial.md`). En MOD **se puede cambiar**
  (precondición c); el prototipo la muestra fija («No se modifica»): manda el CU (L7). Códigos: `patente_invalida`, `patente_repetida`.
- **Tipo, marca y modelo (regla 2).** El tipo, de la lista cerrada (`TextChoices`), con el desplegable propio (D-24). **Marca y modelo son
  dos campos** obligatorios (el prototipo tiene uno, «Marca y modelo»: manda el CU y MD-129).
- **Capacidad (regla 3).** Se acepta con coma o con punto decimal, hasta dos decimales, mayor que 0; se guarda como `Decimal`. Código
  `capacidad_invalida`, con el texto del prototipo: «Un número mayor que 0, en kg, con hasta 2 decimales.»
- **Transportista (regla 4 de ALT, postcondición b de ALT y MOD).** Se ofrecen los Transportistas **activos** sin otro vehículo (más el
  actual, en MOD), cada uno con su invernadero o «sin invernadero» (`TransportistaInvernadero`, D-55). Lo garantiza la base
  (`OneToOneField`): dos vehículos que eligen a la vez al mismo transportista dan al segundo el error de campo `transportista_con_vehiculo`,
  nunca un 500. Un transportista sin invernadero se puede asignar: el aviso del formulario dice «No recibe entregas hasta que se lo agregue a
  un invernadero, en "Logística".»
- **Notificaciones** (`notificar_a_varios`, con `excluir=actor`; voseo, como MAE-05):

  | Caso | Título | Detalle |
  |---|---|---|
  | Asignado (ALT b, MOD b, entrante) | «Tenés un vehículo asignado» | «Desde ahora hacés tus entregas con {tipo} {patente} ({capacidad} kg).» |
  | Quitado o cambiado (MOD b, saliente) | «Ya no tenés el vehículo {patente}» | «No vas a recibir entregas con envío hasta que te asignen otro vehículo.» |
  | Baja (BAJ b) | «Tu vehículo se dio de baja» | «El vehículo {patente} se dio de baja. No vas a recibir entregas nuevas hasta que te asignen otro.» |

- **En ruta (precondición b de MOD y de BAJ).** `vehiculo.esta_en_ruta(hoy)` (MD-118). Rechazo con el código `vehiculo_en_ruta` y el texto
  «El vehículo está en ruta: el producto de las entregas de hoy está cargado. Podés modificarlo o darlo de baja cuando finalice la ruta.»
  En COM-01 nadie inicia una ruta (lo hace COM-06), así que las pruebas cargan `en_ruta` y `fecha_inicio_ruta` directo con la fábrica.
- **Carga asignada (regla 2 de MOD) y entregas a realizar (regla 3 de MOD, precondición c y regla 1 de BAJ).** **Se completan en COM-05**,
  cuando exista `Entrega`. En COM-01, `comercial/servicios/vehiculos.py` tiene `entregas_a_realizar_del_transportista(transportista) ->
  list` y `carga_maxima_asignada(vehiculo, desde) -> (Decimal, date | None)`, que devuelven lista vacía y `(0, None)`; el servicio ya las
  llama en el lugar que corresponde y las pruebas las cubren con `mock.patch`. COM-05 les pone la consulta real.
- **Inactivo (regla 4 de MOD y postcondición c).** Un vehículo inactivo no se modifica: solo «Reactivar», que lo deja activo y **sin
  transportista** (lo exige la base, `docs/modelo/comercial.md`). Acción de auditoría `reactivacion_vehiculo`.
- **Baja (BAJ).** Deja el vehículo inactivo y sin transportista en la misma escritura (la restricción de la base lo exige). Acción
  `baja_vehiculo`.
- **Consulta (CNS).**
  - Lista: búsqueda por patente, tipo o nombre del transportista; filtros por estado y por invernadero (el del transportista, por
    `TransportistaInvernadero`); orden por patente. Columnas de COM-01: patente, tipo y modelo, capacidad, transportista (con su
    invernadero), situación («En ruta» o nada) y estado. La columna «Entregas a realizar» la suma COM-05.
  - Ficha (el prototipo no la tiene: se arma con el mismo estilo que la ficha del cliente, `VIEWS.cli`): datos, transportista, invernadero
    del transportista, «En ruta hoy» o «En el invernadero». La carga asignada frente a la capacidad de los próximos días **se completa en
    COM-05**; hasta entonces la tarjeta no se muestra (D-25).
- **Bloqueos.** Orden: la cuenta del transportista entrante y la del saliente (en orden de id, D-40: las cuentas primero), después el
  vehículo, con `FOR NO KEY UPDATE`, y releer. Sin cambios no se escribe ni se audita (D-28).
- **Auditoría (D-36).** Acciones `alta_vehiculo`, `modificacion_vehiculo`, `baja_vehiculo` y `reactivacion_vehiculo`. Afectados: el
  vehículo y las cuentas de los transportistas que entran o salen. La capacidad, como texto («800,00»).
- **Texto de la capacidad.** `texto_capacidad(Decimal) -> str` en `comercial/servicios/vehiculos.py`: kilogramos con coma decimal y sin
  ceros de más («800 kg», «800,5 kg», «1.250,25 kg»). Lo usan la lista, la ficha, las notificaciones, «Logística» y la ficha de la cuenta. En
  la auditoría la capacidad va con dos decimales («800,00»).
- **Vehículo en la ficha de la cuenta (decisión del estudiante del 21/11/2026).** Además de lo que piden los casos de uso, la ficha de la
  cuenta de un Transportista (USR-CNS-USR, regla 3) y su «Mi perfil» (USR-GST-PRF, regla 1) muestran su vehículo, solo para consultar.
  COM-01 registra `core.extensiones.registrar_datos_de_cuenta` (contrato en `docs/api/extensiones_de_maestros.md`, «Transportistas»):
  para un Transportista devuelve `DatoDeCuenta("Vehículo", "Camioneta AE123CD · 800 kg" o "Sin vehículo", nota)`, con la nota «Se asigna
  desde el vehículo, en Comercial › Vehículos.»; para los demás roles, una lista vacía. Va después del «Invernadero» de `maestros`, porque
  `comercial` se registra después en `INSTALLED_APPS`. Un vehículo inactivo no cuenta (no tiene transportista). Hay que anotarlo en
  pendientes_CU (lo pega el estudiante): USR-CNS-USR regla 3 y USR-GST-PRF regla 1 suman el vehículo del Transportista.
- **«Logística» de la ficha del invernadero (D-55).** COM-01 registra `registrar_logistica_de_transportista` (un solo registrante) con
  `Logistica(vehiculo, en_ruta, entregas_a_realizar=0, url_entregas=None)`: el vehículo activo del transportista como «Camioneta AE123CD ·
  800 kg» o `None`, y `en_ruta` con `esta_en_ruta(hoy)`. Una consulta por tabla para toda la lista, nunca una por transportista. COM-05
  completa las entregas y la URL.

## Pantallas

Guía visual: `docs/prototipos/comercial/`. Buscá la función y leé solo esa parte (y sus sobrescrituras: ver el `README.md`).

| Pantalla | Función en el prototipo | Casos de uso |
|---|---|---|
| Comercial · pestaña «Vehículos» (solo el Gerente) | `VIEWS.com`, `tabVehiculos` | COM-CNS-VEH |
| Ficha del vehículo | — (no está: con el estilo de `VIEWS.cli`) | COM-CNS-VEH |
| Registrar o modificar vehículo | `VIEWS.vehform` (líneas 1136 y 1807), `ACT['vehform-ok']` (1142 y 1817) | COM-ALT-VEH, COM-MOD-VEH |
| Dar de baja y reactivar | `MODALS.bajaveh`, `ACT.reactveh` | COM-BAJ-VEH, COM-MOD-VEH |

**Textos explicativos:**

- Bajo el título de la pestaña: «Con estos vehículos los transportistas hacen las entregas con envío. Cada vehículo tiene a lo sumo un
  transportista y trabaja para el invernadero de él.»
- En el formulario, junto a la capacidad: «Peso máximo que lleva en el día, en un solo viaje. Los envases no cuentan.» (glosario,
  «Capacidad de carga»).
- En el campo del transportista: «Solo transportistas activos sin otro vehículo. El vehículo trabaja para el invernadero de su
  transportista.» (texto del prototipo).

## Para más adelante

Cada punto está también en `docs/disparadores.md`, «Completan el ABM de vehículo».

- COM-05: la regla 2 de MOD (capacidad frente a la carga de cada día), la regla 3 de MOD y la precondición c y la regla 1 de BAJ (entregas a
  realizar del transportista, con «Ver sus entregas»), la columna «Entregas a realizar» de la lista y la carga de los próximos días en la
  ficha; las entregas a realizar y la URL en «Logística».
- COM-06: `en_ruta` y `fecha_inicio_ruta` los escriben COM-INI-RUT y COM-FIN-RUT. Nada que cambiar en el ABM.

## Solo prototipo

Los de `docs/prototipos/comercial/README.md`, «Elementos del prototipo que no van en el sistema». En estas pantallas, además, las patentes
y los transportistas de ejemplo.
