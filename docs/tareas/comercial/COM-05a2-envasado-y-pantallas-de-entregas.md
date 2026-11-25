# COM-05a2 · Envasado y las entregas en el panel, las fichas y los vehículos

Estado: pendiente | App: comercial (y la restricción de `ReservaInsumo` y el núcleo de reservas en produccion, D-66) | Rama: feature/com-05a2-envasado-y-pantallas-de-entregas | Ronda: Comercial 1

Depende de: **COM-05a1** (`Entrega`, su planificación, la cancelación incluida y la lista de entregas) y, con ella, todo lo anterior. Si no
está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La segunda mitad de COM-05a (D-66 punto 1; D-67 punto 2): el Agrónomo **planifica el envasado** de cada entrega reservando
envases del depósito (PROD-PNF-ENV), y recibe el aviso «Planificá el envasado» al crearse cada entrega (postcondición h de COM-PNF-ENT). Las
entregas aparecen en el **panel de control** (Gerente, Vendedor y Agrónomo), en las **fichas de compra-venta y de suministro** y en las
pantallas de **vehículos**.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-PNF-ENV | Planificar Envasado (con la modificación) | docs/casos_de_uso/produccion/envasado.md | 1a «desde la notificación»: no aplica (D-42) |
| COM-PNF-ENT | Lo que completa: el aviso de envasado al Agrónomo (postcondición h, paso 10) | docs/casos_de_uso/comercial/entregas.md | La base es de COM-05a1 |
| COM-CNS-CVT, COM-CNS-SUM, COM-CNS-VEH | Lo que completa: las entregas en las fichas y en los vehículos | entregas.md, «Lo que completa a otras tareas» (filas de COM-02, COM-03 y COM-01) | — |

## Leer

- Casos de uso: docs/casos_de_uso/produccion/envasado.md **completo**; de docs/casos_de_uso/comercial/entregas.md, «Avisos y textos» (la
  fila del paso 10), «Lo que completa a otras tareas» (filas de COM-01 vehículos —la columna y la carga de los próximos días—, COM-02 CNS-CVT y
  COM-03 CNS-SUM) y «Pantallas» (panel, fichas, vehículos); de cancelar_orden.md, «Comercial 1: entregas y envasado» (el aviso al Agrónomo
  ya lo hizo COM-05a1).
- Modelo: docs/modelo/produccion.md (**ReservaInsumo** con la restricción nueva), docs/modelo/comercial.md (Entrega: «Tiene envasado»).
- Decisiones: **D-66** (puntos 4, 8, 11 y 13), D-30, D-36, D-37, D-40, D-42, D-43, D-44, D-61; **D-67, puntos 1 y 2**.
- Patrones: docs/patrones/bloqueos.md («Entregas y envasado»: planificar el envasado), docs/patrones/stock.md (secciones 1 y 5: lo disponible
  y el orden de bloqueo de `inventario`), docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md («Migraciones»).
- API: **docs/api/produccion.md, sección 9, «Lo que suma COM-05a2»**; docs/api/extensiones_de_produccion.md (sección 4, el campo
  `envasado`); docs/api/stock.md (`disponible_para_planificar`).
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`): `tabEnvasado`, `INIT.env`, `VIEWS.env` (las dos definiciones),
  `envDisp`, `envErr`, `dupOf`, `secComercial` (las dos), `secCosecha` (el indicador de envasado), `tabVehiculos`, `VIEWS.vehform` (las dos), y
  en `VIEWS.cv` y `VIEWS.sum` solo las secciones de entregas.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` (COM-05a1 en particular: `servicios/entregas.py`, `vehiculos.py`, las vistas de la lista de entregas, las fichas de
    contrato, el panel que dejaron COM-04a y COM-04b);
  - `produccion/`: `models.py` (`ReservaInsumo`), `extensiones.py` (`EntradasDeComercial`), la pantalla de órdenes del Agrónomo;
  - `inventario/servicios/stock.py` (`disponible_para_planificar`, `hoy`), `inventario/categorias.py` (`ENVASES`), `inventario/unidades.py`
    (`decimales_de`), `inventario/models.py` (`InsumoInvernadero`) y cómo lee una cantidad un formulario de `inventario`;
  - `core/extensiones.py` (`registrar_seccion_de_inicio`), `core/models.py` (auditoría).

## Límites

- Crea modelos: en `produccion`, la restricción de `ReservaInsumo` «a lo sumo una activa» (D-66, punto 8). Nada en `comercial`.
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `produccion/migrations/00NN_reserva_insumo_una_activa.py`: quita «Único `(orden, insumo_invernadero)`» y agrega la condicional;
  - `core/migrations/00NN_comercial_envasado.py`: solo `choices` (acción `planificacion_envasado`).
- Permitido fuera de `comercial`:
  - `produccion`: la migración de arriba; `produccion/servicios/reservas.py` (nuevo, sección 9 de `docs/api/produccion.md`, «Lo que suma
    COM-05a2»); el campo `envasado` de `EntradasDeComercial` y su acceso en la pantalla de órdenes. **Nada de las listas, la bandeja,
    `cancelar_orden` ni los registrantes**: es de PRD-01 (D-67, punto 1). **Las pruebas existentes de `produccion` no se modifican**: se
    suman métodos nuevos;
  - `core`: en `core/models.py`, la acción, `ETIQUETAS` y `ACCIONES_DE_NEGOCIO`;
  - `config/urls.py` y `core/tests/urls_prueba_acceso.py`, una línea cada uno, **solo si** las rutas del envasado necesitan otro prefijo que
    el que ya dejó COM-04a (frená y preguntá antes);
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md`, `docs/temas_abiertos.md`
    y `docs/estado.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: COM-ASG-TRP y COM-CNL-CVT (COM-05b); el exceso de envases y su consumo al concretar (COM-06); montos y pago (COM-06 y
  COM-08); los temas abiertos del caso de uso.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Núcleo en `produccion`** (D-66 punto 8; `docs/api/produccion.md`, sección 9, «Lo que suma COM-05a2»): la restricción de `ReservaInsumo`;
   `reservas.reservar`, `cambiar_cantidad` y `cancelar`; el campo `envasado` de `EntradasDeComercial`; la acción de `core`. Fábrica `envase(invernadero,
   stock, unidad, ...)` en `comercial/tests/fabricas.py`.
   Pruebas: `produccion/tests/test_reservas_nucleo.py`; en `comercial/tests/test_modelos_entregas.py`, la de `ReservaInsumo` (dos activas del
   mismo insumo fallan, una cancelada y una activa no). Corré **toda** la suite de `produccion`: tiene que dar lo mismo que antes (la prueba
   de PRD-01 que verificaba «único sin condición» con una cancelada se **reemplaza** por la nueva: anotala en el PR).
2. **PROD-PNF-ENV** (`envasado.md`, «Servicios» y «Reglas en el código»): `comercial/servicios/envasado.py`.
   Pruebas: `comercial/tests/test_prod_pnf_env.py` y `test_envasado_concurrencia.py` (la lista de «Pruebas» de `envasado.md`); en
   `test_entregas_concurrencia.py`, la de la merma en cámara contra el envasado.
3. **El aviso de envasado** (postcondición h de COM-PNF-ENT; `entregas.md`, «Avisos y textos», paso 10): en `planificar_venta` y
   `planificar_periodo` (y en el agrupamiento, con la entrega completa).
   Pruebas: en `test_com_pnf_ent.py`, métodos nuevos (con y sin Agrónomo activo; el agrupamiento).
4. **Vistas, plantillas y pantallas compartidas** («Pantallas» de los dos extractos): «Envasado» (lista, carga, resumen) y su acceso desde la
   pantalla de órdenes; el grupo «Entregas» del panel del Gerente y del Vendedor y el indicador «Entregas sin envasado» del Agrónomo; las
   secciones de entregas de las fichas de compra-venta y de suministro (y «Entrega planificada» en el calendario); la columna «Entregas a
   realizar» de la lista de vehículos y «Carga de los próximos días» en su ficha. Vistas que solo orquestan, `rol_requerido`, `never_cache`,
   `vary_on_headers("HX-Request")`, respaldo sin JavaScript, errores por campo y aviso breve (D-29). Antes de tocar el panel y la pantalla de
   órdenes, mirá qué dejaron COM-01 a COM-05a1 y PRD-01 a PRD-04 en ellas (criterio de la sección 5 del plan).
   Pruebas: `test_envasado_vistas.py`; en `test_entregas_vistas.py`, métodos nuevos (el panel por rol, las secciones de las fichas de
   contrato, la columna y la carga de los vehículos).
5. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar lo de COM-05a2 y dejar lo que nace (COM-06: el
   exceso de envases); la fila de la tarea en `docs/tareas/README.md` y en el plan; lo distinto de lo escrito, a `docs/temas_abiertos.md`; y la
   lista «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es la tarjeta «Próximas entregas» del panel y la carga de los próximos días de la ficha del
vehículo (quedan en `docs/temas_abiertos.md`). No se recortan las restricciones de la base, los bloqueos, la relectura de 10a a 10c ni las
pruebas de concurrencia.

## Hecho cuando

- El Agrónomo recibe «Planificá el envasado» por cada entrega nueva y reserva, cambia y quita envases de una entrega; nunca por encima de lo
  disponible y nunca de una entrega en curso, concretada o cancelada.
- El panel, las fichas de los contratos y los vehículos muestran las entregas.
- Todas las pruebas de `produccion`, `maestros`, `core`, `inventario` y de las tareas anteriores de `comercial` siguen pasando (las que
  cambian, anotadas).
- Comando de pruebas:
  python manage.py test comercial produccion maestros inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial produccion --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Esta sección la escribió Claude Code al cerrar la tarea (D-96, `docs/patrones/verificacion_a_mano.md`). **No hay cargador de datos** (D-95): los datos los creás vos, con los valores de abajo. Nunca escribas
una contraseña en un archivo del repo: usá la de tus cuentas de prueba.

**Antes de empezar**

1. En PowerShell, con el entorno virtual activo: `python manage.py migrate` (aplica `produccion 0009_reserva_insumo_una_activa` y `core 0041_comercial_envasado`; no tocan datos) y `python manage.py runserver`. Abrí `http://localhost:8000`.
2. Cuentas: necesitás un **Gerente**, un **Vendedor**, un **Agrónomo**, un **Capataz** y un **Transportista**, todos activos. El Agrónomo, el Capataz y el Vendedor tienen que estar a cargo del mismo invernadero (lo llamo «Sur»).
3. Datos que tenés que crear a mano, en este orden (si ya tenés los de COM-05a1, reusalos y salteá lo que ya está):
   a. El invernadero «Sur» activo, con su Agrónomo, su Capataz y su Vendedor; una variedad «Lechuga Crespa» con su ciclo y un lote en maduración (para que haya producto).
   b. Un Transportista asignado a «Sur» (Maestros › Invernaderos › ficha › «Logística») y, con el Gerente, su vehículo: «Comercial › Vehículos › Registrar vehículo», patente `AB123CD`, camioneta, Ford Ranger, 800 kg, con ese transportista.
   c. Un cliente con una dirección (Comercial › Clientes), por ejemplo «Verdulería Pérez».
   d. **El envase**: un insumo «Bandeja PET 1 kg», categoría **Envases**, unidad **unidad**, habilitado en «Sur» y con **30 unidades** de stock (Inventario › Ajustar stock: ajuste positivo de 30). Con ese mismo envase, un segundo insumo «Caja de cartón» con 10 unidades (para probar el buscador y los quitados).
   e. **Una compra-venta con envío** del cliente, de 100 «Lechuga Crespa» para dentro de 3 días, cuyo producto salga **todo de la cámara** (o con una cosecha concretada), de modo que quede «lista para entrega». Planificá la entrega con el paso diario: `python manage.py proceso_diario --solo planificar_entregas` (si el código del paso es otro, `python manage.py proceso_diario --listar` los muestra; es el número 50). Tiene que aparecer una entrega «OT-…».
   f. Opcional, para el paso 3: un **suministro** del mismo cliente con un detalle de 20 plantas por período y la primera entrega dentro de 3 días, también con producto listo.

**Pasos** (entre paréntesis, lo que ya cubre una prueba)

1. **El aviso.** Entrá con el **Agrónomo**. En la campana tiene que haber «Planificá el envasado de OT-…» con el cliente, la fecha, «(envío)», el contenido, el peso y «Está en Producción › Envasado.». En «Panel de control», dentro de «Cosechas y cámara», el indicador **«Entregas sin envasado»** vale 1, en ámbar, y lleva a «Envasado». (Lo cubren `test_post_h_…` y `test_regla_el_agronomo_ve_entregas_sin_envasado_y_lleva_a_envasado`.)
2. **La lista.** «Producción» › «Envasado» (o el indicador). Arriba dice: «Las entregas las planifica InfoPonia. Reservá los envases de cada una: se descuentan del stock recién al concretarla.». La fila de la entrega muestra el código y el contrato, el cliente con el transportista (o «Retiro» o «Sin transportista»), el contenido y el peso, la fecha, **«Sin planificar»** en ámbar y la acción **«Planificar envasado»**. Probá el filtro de fecha (una fecha sin entregas → «No hay entregas para envasar con estos filtros.»). Con un solo invernadero a cargo no hay selector de invernadero. (`ListaTests`.)
3. **La carga y sus errores.** Entrá a «Planificar envasado». Vas a ver los datos de la entrega y, abajo, «Agregar un envase» con la «Bandeja PET 1 kg» (disponible 30 unidades) y la «Caja de cartón».
   - Escribí `40` en la cantidad de la bandeja y apretá **«Agregar»**: la fila aparece con el error **«Supera lo disponible: quedan 30 unidades (sin contar los lotes que estarán vencidos el dd/mm).»** y la ayuda «Si necesitás más, pedilo con un pedido de compra o, si el depósito tiene más de lo registrado, ajustá el stock.». El botón **«Revisar»** queda deshabilitado.
   - Probá `0`, `-3`, `2,5` y vacío: **«Ingresá una cantidad mayor que 0, un número entero (unidad).»**. Con `abc` lo mismo.
   - Corregí a `20` y apretá **«Actualizar»**: el error desaparece y «Revisar» se habilita. Buscá «cart» en el buscador y apretá «Buscar»: solo queda la caja. Agregá la bandeja otra vez con `9`: dice **«Ya estaba en la lista: se reemplazó la cantidad.»** y la fila queda en 9. Dejala en `20`. «Quitar» saca la fila. (`CalcularTests`.)
   - Mientras tipeás nada se valida ni se recalcula: solo reaccionan los botones.
4. **El resumen y la confirmación.** Con la bandeja en `20`, «Revisar»: página «Resumen del envasado»: cliente, fecha, modalidad, la bandeja con «Antes —», «Ahora 20 unidades» y «Queda disponible 10». «Volver a la carga» te devuelve con lo mismo; «Cancelar» vuelve a la lista sin guardar. «Confirmar envasado»: vuelve a la lista con el aviso **«Envasado de OT-… planificado.»** y la fila dice **«Planificado»** con «Modificar envasado». El indicador del panel baja a 0. (`ResumenYConfirmacionTests` y el recorrido.)
5. **Modificar.** «Modificar envasado»: la bandeja viene con `20` y «Disponible 30» (suma lo propio). Poné `25` y «Revisar»: el resumen muestra **20 → 25**. Confirmá. Volvé a entrar y apretá «Revisar» sin tocar nada: **«No hay cambios para registrar.»**. Quitá la bandeja y «Revisar»: el resumen dice «Se quita» y **«La entrega va a quedar sin envasado planificado: al concretarla se declaran los envases usados.»**; confirmá. Volvé a agregar la bandeja con `10` y confirmá: queda planificado (por dentro hay dos reservas, una cancelada y una activa). Sin ningún envase en una entrega que no tenía: «Revisar» dice **«Indicá al menos un envase.»**. (`test_ext_8a…`, `8b`, `8c`, el recorrido.)
6. **Dos personas a la vez (10c y 10b).** Abrí la misma entrega en dos ventanas con el Agrónomo. En la primera confirmá `5`; en la segunda, sin recargar, poné `7` y confirmá: vuelve a la carga con **«Mientras cargabas, el envasado de esta entrega cambió…»** y las reservas vigentes. Para 10b: con otra entrega, reservá la mayor parte de las 30 bandejas y confirmá en la otra una cantidad que ya no alcance: vuelve a la carga con **«Mientras cargabas, cambió lo disponible…»** y conserva lo que escribiste. (Lo cubren `test_ext_10b…` y `test_ext_10c…` y las pruebas de concurrencia.)
7. **Fichas, panel y vehículos (Gerente y Vendedor).** Con el **Gerente** y con el **Vendedor**: en «Panel de control», el grupo **«Entregas»** con «Entregas de hoy», «Sin transportista» (en rojo si hay) y «Próximas entregas» con «Ver todas»; cada indicador abre «Comercial › Entregas» (el de «Sin transportista», ya filtrado). El Vendedor solo cuenta las entregas de sus contratos. En la ficha de la compra-venta, la sección **«Entregas»** muestra el invernadero, la fecha, el estado («Atrasada» si la fecha pasó) y el transportista o «Retiro»; sin entregas dice «La entrega se planifica cuando todo el producto esté listo.». En la ficha del suministro: «Entregas» con «No confirmada» y, en el calendario, el período de esa entrega dice **«Entrega planificada»**. (`PanelDeControlTests`, `FichasDeContratoTests`.)
8. **Vehículos (Gerente).** «Comercial › Vehículos»: la columna **«Entregas a realizar»** muestra el número (enlace a las entregas de ese transportista). En la ficha del vehículo, **«Carga de los próximos días»**: hasta 7 fechas con su cantidad de entregas, el peso y la capacidad (el peso en rojo si supera la capacidad); sin entregas, «Sin entregas asignadas para los próximos días.». (`VehiculosTests`.)
9. **La entrega que se cancela.** Con el Agrónomo, dejá la entrega con 20 bandejas. Vencé en cámara la partida de esa entrega para que quede vacía (Producción › merma/cámara, según tus datos): la entrega se cancela, el Agrónomo recibe el aviso de cancelación y las bandejas vuelven a estar libres (disponible 30). Si abrís «Envasado» por la URL de esa entrega, vuelve a la lista con «… ya no está a realizar: está cancelada.». (Lo cubre `test_estado_la_entrega_cancelada_libera_los_envases_…` del recorrido.)
10. **Entrega en curso (3b).** Con una entrega de hoy con envío cuyo transportista tenga la ruta iniciada (COM-06 todavía no la inicia: solo se prueba por prueba), la fila diría «En curso» sin botón. (Lo cubren `test_ext_3b_…`; **no se puede probar a mano** hasta COM-06.)
11. **Permisos.** Con el Gerente, el Vendedor, el Capataz y el Transportista, escribí `/comercial/envasado/` en la barra: 403. Con **otro Agrónomo** (de otro invernadero), `/comercial/envasado/<id de la entrega>/`: 403 («no está a tu cargo») y la lista no muestra esa entrega. (`PermisosTests`.)
12. **Navegador real (obligatorio: hay formularios que se envían).** Abrí «Envasado» en una **ventana privada**, entrá con el Agrónomo, abrí una entrega, agregá un envase, «Revisar» y **«Confirmar envasado» hasta el final**; volvé a abrirla: tiene que mostrar lo reservado. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no ve. Con JavaScript, comprobá que «Agregar», «Quitar», «Buscar» y «Actualizar» solo redibujan la carga (sin saltar el scroll) y que el botón «Confirmar envasado» no queda deshabilitado por ellos.
13. **Opcional: sin JavaScript** (desactivalo en el navegador): todo el envasado funciona con «Actualizar», «Agregar», «Quitar», «Buscar», «Revisar» y «Confirmar envasado» (cada uno recarga la página). **Opcional: celular**: la lista y la carga se leen en pantalla angosta.
14. **Después del merge:** revisar en el log de Render que se aplicaron `produccion.0009_reserva_insumo_una_activa` y `core.0041_comercial_envasado`.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo.** Bloque 1 (núcleo): restricción «a lo sumo una reserva de insumo activa por (orden, envase)» con su migración, `produccion/servicios/reservas.py`, el campo `envasado` de `EntradasDeComercial` y el acceso en la pantalla de órdenes, la acción `planificacion_envasado`
de `core`. Bloque 2 (servicio): `comercial/servicios/envasado.py` (lista, carga, resumen y registro con los bloqueos de `docs/patrones/bloqueos.md`) y el aviso «Planificá el envasado» al crearse cada entrega. Bloque 3 (pantallas): las vistas y plantillas de «Envasado» (lista, carga con buscador
de envases, resumen y confirmación; `calcular/` y `revisar/` no escriben), el grupo «Entregas» del panel del Gerente y del Vendedor, el indicador «Entregas sin envasado» del Agrónomo, las secciones «Entregas» de las fichas de compra-venta y de suministro («Entrega planificada» en el calendario),
la columna «Entregas a realizar» de la lista de vehículos y «Carga de los próximos días» de su ficha.

**Pruebas (M1).**
- `python manage.py test comercial produccion maestros inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: 5924 pruebas en 603 s, corridas sin `--parallel` (con `--parallel` Django se cortó al serializar un fallo): 1 falla, `test_vehiculos_vistas…test_regla_1_la_lista_muestra_las_columnas_de_com_01`, que afirmaba que la columna «Entregas a realizar» no existía; se invirtió la aserción (la columna es de esta tarea) y el módulo volvió a pasar (30 de 30). No volví a correr la suite entera después de ese cambio.
- `python manage.py test comercial produccion --keepdb --tag concurrencia`: 125 pruebas, OK (435 s)
- Pruebas nuevas del bloque 3: `comercial/tests/test_envasado_vistas.py`, las clases `PanelDeControlTests`, `FichasDeContratoTests` y `VehiculosTests` de `test_entregas_vistas.py` y `test_recorrido_envasado_y_entregas.py` (3 recorridos).

**Verifiqué** (recorrido y migraciones): el recorrido `RecorridoDeEnvasadoYEntregasTests` (aviso → panel → lista → carga con error de lo disponible → resumen → confirmación → modificación con antes y después → «sin cambios» → quitar y volver a agregar → panel, ficha de compra-venta,
vehículos y suministro por rol → cancelación de la entrega que libera los envases → 403 de los otros roles); `makemigrations --check` sin cambios; `sqlmigrate produccion 0009` (quita la restricción única y crea el índice único parcial `WHERE estado = 'activa'`: no toca filas) y `sqlmigrate core 0041` (no-op, solo `choices`); las dos migraciones aplicadas en la base de pruebas.

**Lo cubre una prueba**: permisos, lista, carga, resumen y confirmación (`test_envasado_vistas.py`); 3a, 3b, 4a, 4b, 6a a 6c, 8a a 8c, 10a a 10c (`test_prod_pnf_env.py`, `test_envasado_vistas.py`); concurrencia (`test_envasado_concurrencia.py`, `test_entregas_concurrencia.py`); el aviso de envasado (`test_com_pnf_ent.py`); el panel, las fichas y los vehículos
(`PanelDeControlTests`, `FichasDeContratoTests`, `VehiculosTests`); sin consultas por fila en la lista de envasado, el panel, la ficha del contrato y la lista de vehículos.

**No pude verificar**: el CSRF, el encabezado `Origin`, el JavaScript de HTMX y el aspecto (paso «navegador real»); una entrega «en curso» a mano (la ruta la inicia COM-06, solo está cubierta por prueba); el envío real del correo al cliente; el log de Render después del merge.

### Pantallas: lo que se corrigió del prototipo

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| `VIEWS.env` (carga) | `<select>` nativo para elegir el envase | Buscador por nombre con lo disponible y la unidad de cada envase, y «Agregar» | Variación 5 del caso de uso; D-24 |
| `dupOf` | Error «Ese envase ya está en otra fila» | Indicarlo otra vez reemplaza la cantidad, con el aviso «Ya estaba en la lista: se reemplazó la cantidad.» | Extensión 6c |
| `envErr` | Solo enteros | La cantidad admite los decimales de la unidad del envase; error con la cantidad de decimales | Regla «Cantidad válida», extensión 6a |
| `ACT['env-ok']` | Registraba sin resumen | «Revisar» → página de resumen (anterior → nueva, quitados, aviso 8b) → «Confirmar envasado»; «Volver a la carga» y «Cancelar» | Pasos 8 y 9, extensiones 8a a 8d, \*a |
| `tabEnvasado` | Solo el invernadero «A» | Los invernaderos a cargo, con filtro de invernadero (si hay más de uno) y de fecha, y «En curso» sin botón | Paso 2, extensión 3b |
| `VIEWS.env` | Sin 4a ni 4b | «Este invernadero no tiene envases habilitados.» con el acceso a las existencias, y el aviso de entrega atrasada | Extensiones 4a y 4b |
| `VIEWS.env` | Sugería la cantidad de bandejas | Sin cantidad sugerida | Regla «Sin cantidad sugerida» |
| `secComercial` (panel) | Sin estado vacío | Con 0 entregas a realizar, el mensaje «No hay entregas a realizar» en lugar de indicadores en cero | Criterio de diseño (D-61): estados vacíos |
| `VIEWS.cv` / `VIEWS.sum` (Entregas) | Datos de ejemplo | Tabla con la entrega, el invernadero, la fecha (con «Atrasada»), el estado y el transportista o «Retiro»; en el suministro, la confirmación y «—» en monto, vencimiento y pago | Reglas 4 de COM-CNS-CVT y 7 de COM-CNS-SUM |
| `VIEWS.vehform` (ficha) | Sin carga | «Carga de los próximos días» con el peso en rojo si supera la capacidad y su estado vacío | Regla 2 de COM-CNS-VEH |

**Desvíos respecto de la documentación (para `docs/temas_abiertos.md`, M3):**
- La sección «Datos para verificar» de la tarea nombraba el cargador `comercial/verificacion.py`, retirado por D-95: no se creó; la «Verificación a mano» pide crear los datos a mano.
- «Cada indicador lleva a la lista con su filtro»: «Entregas de hoy» lleva a la lista de entregas «a realizar» sin filtro de fecha, porque la lista de COM-05a1 no tiene filtro por fecha (se podría sumar `?hasta=`). «Sin transportista» sí va filtrado (`?transportista=_`).
- El indicador «Entregas sin envasado» cuenta también las entregas en curso (no las excluye) y solo las de invernaderos activos a cargo del Agrónomo.
- La entrega de un suministro muestra «Confirmación» y deja monto, vencimiento y pago en «—» (COM-06 y COM-08).
- «Entrega planificada» del calendario gana sobre «Pasado», «Reservado» y «Sin cobertura completa» (también para una entrega atrasada).
