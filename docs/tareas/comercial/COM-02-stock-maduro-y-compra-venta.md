# COM-02 · Stock maduro y compra-venta

Estado: pendiente | App: comercial (y modelos en produccion, D-59) | Rama: feature/com-02-stock-maduro-y-compra-venta | Ronda: Comercial 1

Depende de: **COM-01**, **USR-10** (`core.correo.enviar_correo`, D-54) y **PRD-04** (con ella, toda la ronda «Producción 1»: INV-02, INV-03 y
PRD-01 a PRD-04 mergeadas; `docs/tareas/ronda_comercial_1.md`, sección 2). Si alguna no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** Crea el núcleo comercial: los **contratos** y la **compra-venta** con sus detalles, las **reservas de stock** y la
**asignación automática de stock maduro** (PROD-ASG-STK), que reserva producto de cámara y de lotes en Maduración y programa las **cosechas**
necesarias. Para eso suma a `produccion` las tablas `Cosecha` y `StockCosechado` (D-59): las cosechas nacen acá, pero se planifican a mano,
se modifican, se concretan y se muestran en la bandeja recién en COM-04; las partidas de cámara las crea COM-04 (acá solo existen en las
pruebas). Además, el cambio de Vendedor de un invernadero pasa sus compra-ventas al Vendedor nuevo (D-60).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-ASG-STK | Asignar Stock Maduro (sin pantalla) | docs/casos_de_uso/produccion/stock_maduro.md | Bases desde COM-REG-CVT; los demás bases los suman COM-03 y COM-04. `lotes_excluidos` (PCU 7): el parámetro y su prueba, lo usa COM-04 |
| COM-REG-CVT | Registrar Compra-venta | docs/casos_de_uso/comercial/compra_venta.md | Postcondición g (planificar la entrega): se completa en COM-05 |
| COM-CNS-CVT | Consultar Compra-venta | docs/casos_de_uso/comercial/compra_venta.md | Regla 4: entregas (COM-05), cobro (COM-06 y COM-08), cancelación (COM-05) y vencimiento del enlace (COM-04). Regla 5: cancelar (COM-05) |

## Leer

- Casos de uso: los dos extractos de la tabla, completos, **incluidas «Cómo se aplica en la ronda» y «Pantallas»**; de
  docs/casos_de_uso/comercial/clientes.md, «Para más adelante» y la regla 7 de ALT.
- Modelo: docs/modelo/comercial.md (Contrato, CompraVenta, DetalleVenta, ReservaStock, DetalleReserva, «Lo que se calcula de las reservas»,
  «Pendientes de MD»); docs/modelo/produccion.md (`OrdenTrabajo`, `ConCapataz`, «Cosecha (COM-02, D-59)», «StockCosechado (COM-02, D-59)»,
  «Diferencias», fila 8); docs/modelo/contabilidad.md (`OrigenDocumento` y su `Tipo`).
- Decisiones: **D-59** y **D-60** (las de esta tarea), D-14, D-25, D-28, D-29, D-36, D-37, D-40, D-41, D-42, D-44, D-50, D-52, D-53,
  D-54, D-57, D-58.
- Patrones: **docs/patrones/stock_maduro.md** (implementalo tal cual), docs/patrones/bloqueos.md, docs/patrones/abm.md,
  docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md («Migraciones»).
- API: **docs/api/extensiones_de_produccion.md** (la declara esta tarea), docs/api/produccion.md (secciones 2, 3 y 5, y el núcleo de la merma
  de la sección 6), docs/api/alertas.md (`asegurar_alerta_de_estado`), docs/api/extensiones_de_maestros.md (traspaso),
  docs/api/extensiones_de_inventario.md («Variedades»: `registrar_impedimento_de_baja_de_variedad`), docs/api/variedades.md,
  docs/api/notificaciones.md y la función de correo que dejó USR-10.
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`). Funciones: `VIEWS.com`, `tabContratos` (solo la rama `cv`), `VIEWS.cv`,
  `INIT.cvnew`, `VIEWS.cvnew`, `ACT['cvnew-ok']`, `ACT.rowadd`, `ACT.rowdel`, `cliPick`, `ACT.bpick`, `retiroFld`, `cliSearch`. Las diferencias
  ya detectadas están en `compra_venta.md`, «Lo que difiere del prototipo».
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` completo (COM-01): modelos, `servicios/clientes.py` (`buscar_clientes`, `direcciones_en_uso`, `pendientes_del_cliente`,
    `volver`), vistas, plantillas, `apps.py`, fábricas;
  - `produccion/models.py` (`OrdenTrabajo`, `ConCapataz`, `Lote`, `TransicionEtapa`), `produccion/servicios/ordenes.py`
    (`ordenes_del_capataz`, `bandeja_del_capataz`, `lista_de_ordenes`, el traspaso del Capataz, el número de orden), `lotes.py`
    (`fecha_de_entrada_a_maduracion`, `fecha_maxima_de_cosecha`), `mermas.py` (`aplicar_merma` y la alerta de plantas comprometidas),
    `produccion/apps.py` (sus registrantes: impedimentos de baja del invernadero y de la variedad), sus fábricas de pruebas;
  - `contabilidad/models.py` (`OrigenDocumento`);
  - `maestros/servicios/alertas.py`, `maestros/servicios/invernaderos.py` (`bloquear_invernadero_activo`, `modificar_invernadero` y cómo
    llama al traspaso), `maestros/extensiones.py`, `maestros/servicios/configuracion.py` (`obtener`);
  - `inventario/servicios/stock.py` (`hoy`), `inventario/servicios/variedades.py`, `inventario/extensiones.py`;
  - `core/correo.py`, `core/notificaciones.py`, `core/models.py` (auditoría).

## Límites

- Crea modelos:
  - en `comercial`: `Contrato` (hija de `contabilidad.OrigenDocumento`), `CompraVenta`, `DetalleVenta`, `ReservaStock`, `DetalleReserva`;
  - en `produccion`: `Cosecha` (hija de `OrdenTrabajo` y de `ConCapataz`) y `StockCosechado` (D-59).
  → revisá docs/disparadores.md: cierra los de la sección 9 del plan para COM-02 (punto 7 de «Pasos»).
- Migraciones:
  - `produccion/migrations/00NN_cosecha_y_stock_cosechado.py`: las dos tablas y la restricción «tipo cosecha ⇒ prioridad no nula» (el valor
    `cosecha` de `OrdenTrabajo.Tipo` ya lo creó PRD-01: D-67, punto 1);
  - `contabilidad/migrations/00NN_tipo_contrato.py`: solo `choices` (`contrato` en `OrigenDocumento.Tipo`);
  - `comercial/migrations/0002_contratos_y_reservas.py`: las cinco tablas y la secuencia `comercial_compraventa_numero_seq` (`RunSQL` con su
    reverso, como `produccion_orden_numero_seq`). Depende de las dos anteriores;
  - `core/migrations/00NN_comercial_compra_venta`: solo `choices` (acción `registro_compra_venta`).
  Con el número libre en `main` al abrir el PR. **Ninguna de datos.** Ninguna en `maestros` ni en `inventario`.
- Permitido fuera de la app:
  - `produccion`: los dos modelos y su admin de solo lectura; la restricción de la prioridad de la cosecha; `produccion/extensiones.py` (nuevo, tal
    cual `docs/api/extensiones_de_produccion.md`); en `servicios/ordenes.py`, sumar `Cosecha` a la unión de `ordenes_del_capataz` y al
    traspaso del Capataz, y **excluirla** de la bandeja del Capataz, de la lista del Agrónomo y de `ordenes_cancelables` (un
    `exclude(tipo=COSECHA)` en cada una, con el comentario «hasta COM-04a»: `cosecha` ya está en `TIPOS_DE_PRODUCCION` desde PRD-01, D-67
    punto 1e); en
    `servicios/mermas.py`, la condición 1 de plantas comprometidas; si PRD-01 contó los impedimentos de baja del invernadero o de la variedad
    por hija y no por `OrdenTrabajo`, sumar `Cosecha`; si la función del número de orden quedó privada, hacerla pública sin cambiarla;
    pruebas nuevas en `produccion/tests/test_extensiones.py` y `test_cosecha_en_produccion.py`. **Ninguna prueba existente de `produccion`
    se modifica**;
  - `contabilidad/models.py`: solo el valor `contrato` de `OrigenDocumento.Tipo`;
  - `core/models.py`: solo `Accion`, `ETIQUETAS` (los campos nuevos), `VALORES_VISIBLES` (`modalidad_entrega`, `estado_venta`,
    `estado_reserva`) y `ACCIONES_DE_NEGOCIO`, y su migración;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y
    `docs/modelo/produccion.md` («Diferencias», fila 8).
- Dependencias nuevas: ninguna.
- Fuera de alcance: suministros (COM-03); planificar, modificar, concretar y cancelar cosechas, la cámara, las partidas reales y la bandeja con
  cosechas (COM-04); entregas, envasado y cancelar la compra-venta (COM-05); cobros (COM-06, COM-08); los asientos (D-57); las alertas
  comerciales propias (la primera es de COM-03, T-01); un reintento automático del comprobante (no hay cola de envíos).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos en `produccion` y `contabilidad`.**
   - `Cosecha` y `StockCosechado` según `docs/modelo/produccion.md`, con **todas** sus restricciones; el tipo `cosecha` y la prioridad
     obligatoria; `OrigenDocumento.Tipo.CONTRATO`.
   - `produccion/extensiones.py` con los dos puntos y sus funciones de uso.
   - `ordenes_del_capataz` suma `Cosecha` (sin consultas por fila); el traspaso del Capataz actualiza `capataz` también en las cosechas «a
     realizar»; bandeja, lista del Agrónomo y cancelables las excluyen (hasta COM-04a).
   - `aplicar_merma`: condición 1 de plantas comprometidas con `reservado_de_lotes`.
   - Fábricas en `produccion/tests/fabricas.py` (si las fábricas de PRD-01 no tienen ya una de lote en Maduración, sumá `lote_maduro`).
   Pruebas: `produccion/tests/test_cosecha_en_produccion.py` (restricciones; `ordenes_del_capataz` con una cosecha; traspaso del Capataz con
   una cosecha; la bandeja, la lista y las cancelables no la muestran; la baja del invernadero y la de la variedad se impiden con una cosecha «a realizar»;
   `assertNumQueries` de la unión con 1 y con 3 cosechas) y `test_extensiones.py` (neutro sin registrante; segundo registrante rechazado).
   Corré **toda** la suite de `produccion`: tiene que dar lo mismo que antes.
2. **Modelos de `comercial` y auditoría.** Las cinco fichas de `docs/modelo/comercial.md`, con **todas** sus restricciones de base (la de
   modalidad; una variedad por venta; cantidades y precios; C1 de la línea; el `OneToOne` de la cosecha); `Contrato.codigo` (propiedad); la
   secuencia; `ContratoQuerySet.en_alcance_de`; el admin de solo lectura. La acción `registro_compra_venta` en `core` y su migración.
   Fábricas en `comercial/tests/fabricas.py`: `compra_venta(...)`, `detalle(...)`, `partida(...)`, `reserva(...)`, y
   `verificar_invariantes_de_reservas()` (`docs/patrones/stock_maduro.md`, sección 6).
   Pruebas: `comercial/tests/test_modelos_contratos.py` (una por restricción, la viola y no la viola; el código `CV-0001`; el alcance).
3. **Stock maduro** (`comercial/servicios/stock_maduro.py`), tal cual el patrón: `disponible`, `asignar`, `cantidad_sin_cubrir`,
   `reservado_de_lotes`, y los registrantes de `produccion/extensiones.py` en `ComercialConfig.ready()`.
   Pruebas: `comercial/tests/test_prod_asg_stk.py` (`ProdAsgStkServicioTests`): una por regla de negocio y por postcondición; las
   extensiones 2a, 3a, 3b (en COM-02, solo que con `parametro="suministro"` se usa la anticipación de suministro; el detalle de
   suministro lo prueba COM-03), 4a, 5a (alerta ya
   activa y alerta que faltaba), 5b, 5c y 5d; el orden de asignación (partidas por vencimiento, lotes por entrada a Maduración y por menor
   stock libre); fecha máxima de cosecha con la fecha programada real (los dos ejemplos de la regla 3 de 8.20); anticipación efectiva menor
   por la postcosecha (el ejemplo de la regla 3 de 8.11); invernadero inactivo; `lotes_excluidos`; sin transacción → `RuntimeError`; las dos
   notificaciones, y ninguna si se revierte. `test_extensiones_de_produccion.py` (las tres pruebas mínimas de la API). Concurrencia
   (`test_stock_maduro_concurrencia.py`, `@tag("concurrencia")`): las cuatro de la sección 6 del patrón.
4. **Registrar compra-venta** (`comercial/servicios/compra_ventas.py` y `comprobantes.py`): `registrar_compra_venta`,
   `datos_del_formulario`, `resumen`, `enviar_comprobante`, `reenviar_comprobante`, con todo lo de `compra_venta.md`, «Cómo se aplica».
   Pruebas: `comercial/tests/test_com_reg_cvt.py` (`ComRegCvtServicioTests`): una por regla, postcondición y extensión (1a, 3a, 5a, 6a, 8a,
   9a, 10a a 10c, 9-10a, 9-10b, 11a, 14a, 16a con `enviar_correo` simulado devolviendo `False`, 16b); el precio propuesto (la venta más
   reciente, también cancelada; de otro Vendedor); el Gerente como actor (audita al Gerente y la venta queda del Vendedor elegido); cliente
   dado de baja, dirección desactivada e invernadero que dejó de ser del Vendedor entre la carga y la confirmación; el correo fuera de la
   transacción (simulado: falla si `transaction.get_connection().in_atomic_block`); `datos_del_formulario` con `assertNumQueries` constante.
   Concurrencia (`test_compra_ventas_concurrencia.py`): las tres de «Concurrencia» del extracto.
5. **Consultar compra-venta**: `buscar_compra_ventas` y `ficha_de_compra_venta`.
   Pruebas: `comercial/tests/test_com_cns_cvt.py` (`ComCnsCvtServicioTests`): una por regla (alcance con 403, filtros, monto «estimado» y
   «final», orden), sin consultas por fila.
6. **Lo que completa a COM-01 y los registrantes de otras apps.**
   - Clientes (`docs/disparadores.md`, «Completan el ABM de cliente», punto 1): `direcciones_en_uso` cuenta las compra-ventas con envío
     (**cualquier estado**: una dirección usada nunca se modifica ni se borra, regla 3 de 8.18); `pendientes_del_cliente`, las abiertas o
     pendientes de decisión; la ficha y la lista del cliente muestran sus compra-ventas (el Vendedor, solo las suyas; «Contratos vigentes»
     de la lista cuenta las abiertas y pendientes); el `volver` de ALT y MOD regresa a «Nueva compra-venta».
   - Traspaso al Vendedor nuevo (D-60): `registrar_traspaso(contar_contratos, traspasar_contratos)`.
   - Baja de una variedad (precondición f de PROD-BAJ-VAR): `inventario.extensiones.registrar_impedimento_de_baja_de_variedad` con el código
     `contratos_abiertos` («Tiene compra-ventas abiertas: N.»; COM-03 suma los suministros).
   Pruebas: las de COM-01 que esperaban «nada» se **reemplazan** por las que esperan los datos (es lo que pidió COM-01 con «Se completa en
   COM-02»; anotalas en el PR); `test_traspaso_de_vendedor.py` (los dos casos de D-60, punto 2, sin entrante, y con el `contar` en la ventana
   de PROD-MOD-INV); `test_impedimento_de_variedad.py` (las tres pruebas mínimas).
7. **Vistas, plantillas y pestaña.** `compra_venta.md`, «Pantallas»: la pestaña «Contratos» primera y `/comercial/` redirigiendo a ella; el
   formulario con sus tres secciones, el recálculo con HTMX (`hx-post` a `calcular/`, `hx-trigger` con retardo de 350 ms en los campos de
   texto), la ventana de resumen, la ficha, el comprobante imprimible y «Reenviar comprobante». Las vistas solo orquestan (`abm.md`, sección
   1), con `rol_requerido`, `never_cache` y `vary_on_headers("HX-Request")`; respaldo sin JavaScript; errores por campo; aviso breve (D-29).
   Pruebas: `comercial/tests/test_compra_ventas_vistas.py` (`ComRegCvtVistaTests`, `ComCnsCvtVistaTests`): permisos (los demás roles, 403;
   ningún botón lleva a un 403; el Vendedor no ve el filtro Vendedor); el flujo completo con HTMX y sin él; `volver` desde el alta del cliente
   con los datos de las secciones 1 y 2; `calcular/` no escribe nada (cuenta de filas igual antes y después).
8. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
   - en `docs/disparadores.md`, tachar o marcar lo de COM-02 de la sección 9 del plan y, en «Cuando exista Entrega», el punto nuevo
     (postcondición g de COM-REG-CVT, para COM-05);
   - en `docs/modelo/produccion.md`, «Diferencias», fila 8: «Se aplica desde COM-02»;
   - marcar COM-02 en `docs/tareas/README.md` y en `docs/tareas/ronda_comercial_1.md` (D-59 y D-60 ya están vigentes).
   Lo que haya quedado distinto de lo escrito va a `docs/temas_abiertos.md`.

Si el tiempo apremia, lo último que se recorta es el comprobante imprimible y «Reenviar» (paso 7; el estado se guarda igual y queda una línea
en `docs/temas_abiertos.md`). No se recortan las restricciones de la base, los bloqueos, el patrón de stock maduro ni las pruebas de
concurrencia.

## Hecho cuando

- El Vendedor (y el Gerente, eligiendo el Vendedor) registran una compra-venta con envío o con retiro: ven el disponible de cada variedad para
  la fecha, el precio propuesto y el monto estimado; al confirmar, el stock queda reservado y, si hace falta, hay cosechas «a realizar» con
  su Capataz, que tienen la notificación (él y el Agrónomo).
- Nunca se reserva más que el stock libre de un lote o de una partida, aun con dos ventas a la vez (lo prueban las de concurrencia), y una
  venta que no alcanza a cubrir todo no se registra.
- El cliente recibe el comprobante por correo, o se imprime; si el correo falla, se puede reenviar desde la ficha.
- La lista y la ficha de compra-ventas muestran lo de COM-CNS-CVT que ya existe; el Vendedor ve solo las suyas.
- El cambio de Vendedor de un invernadero pasa sus compra-ventas según D-60; una variedad con compra-ventas abiertas no se da de baja.
- Todas las pruebas de `produccion` que existían siguen pasando sin cambios.
- Comando de pruebas:
  python manage.py test comercial produccion inventario maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial produccion --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas (`produccion`, `contabilidad`, `comercial`, `core`): `python manage.py migrate`. Datos: un invernadero con Agrónomo,
Capataz y Vendedor activos y un lote de «Lechuga Crespa» en Maduración (el de la verificación de PRD-02, o llevá uno con sus transiciones);
otro invernadero del mismo Vendedor **sin Capataz**, con otro lote de esa variedad en Maduración; un cliente con correo y una dirección (COM-01).

1. Con el Vendedor: «Comercial» abre en «Contratos»; «Nueva compra-venta». Elegí el cliente buscándolo por parte del nombre; «Entrega» se
   habilita.
2. Envío a domicilio, fecha pactada ayer: error en el campo. Fecha dentro de 3 días: «Variedades» se habilita y ofrece «Lechuga Crespa» con su
   disponible (solo el lote del invernadero **con** Capataz). En «Alertas» del Gerente está la de «Invernadero sin Capataz activo» del otro.
3. Cargá más plantas que las disponibles: «Hay N plantas disponibles para esa fecha.» Corregí a la mitad, con precio 0: error. Precio 1500,50.
4. «Revisar y registrar»: el resumen muestra el monto estimado. «Volver a la carga», cambiá la cantidad, y confirmá.
5. La ficha muestra `CV-0001` «Abierta» con su detalle; el aviso dice que se programó 1 cosecha. El Capataz y el Agrónomo tienen la notificación
   «Nueva cosecha OT-…». La bandeja del Capataz **no** la muestra (llega con COM-04). En «Auditoría», un `registro_compra_venta` con la venta, el
   detalle, la reserva, su línea y la cosecha.
6. Si el correo está configurado, el cliente recibió el comprobante; si no, la ficha dice «Pendiente de envío» y «Reenviar comprobante».
   «Ver comprobante» abre la página imprimible.
7. Otra venta por **todo** lo que queda del lote: se registra. Una tercera: la variedad ya no aparece («No hay stock disponible…»).
8. Con el Gerente: «Nueva compra-venta» pide el Vendedor; retiro en invernadero muestra solo los de ese Vendedor.
9. En la ficha del cliente: sus dos compra-ventas. Al modificar el cliente, la dirección usada por la venta con envío ya no se puede corregir
   ni borrar: solo desactivar (regla 4 de COM-MOD-CLT).
10. Con el Gerente, «Modificar invernadero»: cambiá el Vendedor por otro. La ventana avisa «Compra-ventas abiertas: 2»; al confirmar, las dos
    ventas son del Vendedor nuevo (y el anterior ya no las ve).
11. Intentá dar de baja «Lechuga Crespa»: «Tiene compra-ventas abiertas: 2.»
12. Sin JavaScript, los pasos 1 a 4 funcionan con «Actualizar» y el resumen como página.
13. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)
