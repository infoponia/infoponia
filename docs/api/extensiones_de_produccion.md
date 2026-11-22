# API · Puntos de extensión de `produccion` (`produccion/extensiones.py`)

Contrato de los puntos por los que `produccion` (nivel 5) pregunta a `comercial` (nivel 6) lo que no puede importar (regla A1 de D-37):
las reservas de stock son de `comercial` y `produccion` necesita saber cuánto de un lote o de una cosecha está reservado. Los declara
**COM-02** (D-59, punto 3; puntos 1 y 2) y **COM-04** (D-64, punto 11; puntos 3 y 4: qué botones de `comercial` muestran las pantallas de
`produccion`), y los registra `comercial` en `ComercialConfig.ready()` (regla A4). Si algo de acá contradice una decisión,
manda la decisión: avisá.

Mismo estilo que `maestros/extensiones.py` y `core/extensiones.py`: una lista privada por punto, una función `registrar_…` que agrega y una
función que la usa `produccion`. **Sin registrante, cada punto da su resultado neutro** (nada reservado, ningún detalle), que es lo que pasa
hoy con las pruebas de `produccion` que no instalan `comercial`.

## 1. `registrar_reservado_de_lote(funcion)`

- **Firma del registrante:** `funcion(lote_ids: list[int]) -> dict[int, int]`: por lote, las plantas reservadas en líneas de reservas
  «activas» (las que todavía no se cosecharon; regla 9 de 8.6). Un lote sin reservas puede faltar en el diccionario.
- **Lo usa:** `produccion.extensiones.reservado_de_lotes(lote_ids) -> dict[int, int]` (siempre con todas las claves, 0 por defecto).
- **A lo sumo un registrante** (`comercial`): un segundo lanza `ImproperlyConfigured`.
- **Quién lo llama en `produccion`:** `mermas.aplicar_merma` (PRD-02), para la **condición 1** de la alerta `produccion_plantas_comprometidas`
  (regla 15 de 8.8): después de bajar la cantidad del lote, si lo reservado supera la cantidad actual, se crea la alerta. COM-02 suma esa
  condición (D-59; `docs/modelo/produccion.md`, «Diferencias», fila 8, que pasa a «Se aplica desde COM-02»). La condición 2 no cambia.
- **Dentro de la transacción de quien llama**, con el lote ya bloqueado: el registrante **no bloquea** (lee las líneas de reserva, que una
  asignación de stock solo crea después de bloquear el lote: `docs/patrones/stock_maduro.md`, sección 3).
- La misma función la usa `comercial` en su cálculo de stock libre (`stock_maduro.reservado_de_lotes`): una sola definición.

## 2. `registrar_detalle_de_cosecha(funcion)`

- **Firma del registrante:** `funcion(cosecha_ids: list[int]) -> dict[int, DetalleDeCosecha]`, con
  `DetalleDeCosecha = namedtuple("DetalleDeCosecha", "contrato fecha_entrega lotes")`: `contrato` es el código visible (`CV-0044`,
  `SUM-0003`) o `None` en una cosecha sin contrato (COM-04); `lotes` es una lista de `(lote_id, cantidad_reservada, cantidad_cosechada)`
  en orden de id de lote (`cantidad_cosechada` es `None` hasta concretar).
- **Lo usa:** `produccion.extensiones.detalle_de_cosechas(cosecha_ids)` (sin registrante: `{}`).
- **A lo sumo un registrante** (`comercial`).
- **Quién lo llama:** nadie en COM-02. Lo declara COM-02 para que el contrato quede junto al del punto 1; lo usan desde COM-04 la bandeja del
  Capataz, la lista de órdenes del Agrónomo y el aviso de baja de la cuenta del Capataz, cuando muestran cosechas.
- Una consulta por tabla, sin consultas por cosecha.

## 3. `registrar_acciones_de_cosecha(funcion)` (COM-04, D-64 punto 11)

- **Firma del registrante:** `funcion(usuario, cosecha_ids: list[int]) -> dict[int, AccionesDeCosecha]`, con
  `AccionesDeCosecha = namedtuple("AccionesDeCosecha", "concretar modificar cancelar")`: cada campo es una URL o `None`. `concretar`, solo
  para el Capataz asignado a la cosecha; `modificar` y `cancelar`, solo para el Agrónomo a cargo del invernadero; todas `None` si la cosecha
  ya no está «a realizar». **Nunca una URL a un 403** (mismo criterio que D-62).
- **Lo usa:** `produccion.extensiones.acciones_de_cosechas(usuario, cosecha_ids)` (sin registrante: `{}`; la pantalla no muestra botones).
- **A lo sumo un registrante** (`comercial`).
- **Quién lo llama:** la bandeja del Capataz y la lista de órdenes del Agrónomo (PRD-01), al mostrar las filas de cosecha.

## 4. `registrar_entradas_de_comercial(funcion)` (COM-04, D-64 punto 11; COM-05a2 suma `envasado`, D-66)

- **Firma del registrante:** `funcion(usuario) -> EntradasDeComercial`, con
  `EntradasDeComercial = namedtuple("EntradasDeComercial", "planificar_cosecha merma_en_camara envasado", defaults=(None,))`: URL o `None`.
  `planificar_cosecha`, para el Agrónomo con algún invernadero activo; `merma_en_camara`, para el Capataz y el Agrónomo con algún invernadero
  en su ámbito; **`envasado`** (COM-05a2, D-66): la pantalla «Envasado» de `comercial`, para el Agrónomo con algún invernadero activo a cargo
  (el campo tiene valor por defecto, así que lo que ya construye la tupla con dos campos sigue funcionando).
- **Lo usa:** `produccion.extensiones.entradas_de_comercial(usuario)` (sin registrante: las dos `None`).
- **A lo sumo un registrante** (`comercial`).
- **Quién lo llama:** la lista de órdenes del Agrónomo (botón «Planificar cosecha», y la opción «Cosecha» de la ventana «Nueva orden») y la
  pantalla «Registrar merma» (PRD-03), que en el paso 4 ofrece «Pérdida en cámara» (extensión 4a de PROD-REG-MRM) y lleva a la pantalla de
  `comercial`.
- **Desde COM-05a2:** la lista de órdenes del Agrónomo muestra, con `envasado`, el acceso «Envasado» junto a las órdenes (en el prototipo,
  la pestaña `tabEnvasado` de `VIEWS.prod`). Si la pantalla de PRD-01 tiene pestañas, es una más; si no, un botón en la cabecera.

## 5. Prueba mínima de cada registrante (`comercial/tests/test_extensiones_de_produccion.py`)

Como en `docs/api/extensiones_de_maestros.md`, «Prueba mínima de cada registrante»:

1. **Con datos:** un lote con dos reservas activas y una liberada devuelve la suma de las activas; una cosecha devuelve su contrato, su fecha y
   sus lotes; las acciones de una cosecha, por rol (Capataz asignado, otro Capataz, Agrónomo a cargo, otro Agrónomo, Gerente) y para una
   cosecha ya concretada; las entradas, por rol.
2. **Neutro:** un lote sin reservas da 0; una lista vacía da `{}` sin consultar la base (`assertNumQueries(0)`).
3. **Sin consultas por fila:** con tres lotes y con tres cosechas, la misma cantidad de consultas que con uno.

Y en `produccion/tests/test_extensiones.py` (las crea COM-02; COM-04 suma las de los puntos 3 y 4): sin registrante, cada punto da su
resultado neutro; un segundo registrante lanza `ImproperlyConfigured`.
