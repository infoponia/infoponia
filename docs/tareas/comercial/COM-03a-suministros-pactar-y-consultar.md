# COM-03a · Suministros: pactar y consultar

Estado: pendiente | App: comercial | Rama: feature/com-03a-suministros-pactar-y-consultar | Ronda: Comercial 1

Depende de: **COM-02** (contratos, reservas, `stock_maduro`, comprobantes). Si no está mergeada, frená. No necesita DIA-01 ni MAE-02d:
esta parte no tiene paso diario ni alertas (las trae COM-03b).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La primera mitad de COM-03 (D-67, punto 2): el **modelo del suministro**, **pactar** un contrato (con la verificación del
stock de los períodos que caen en la ventana de pre-reserva y su reserva en el mismo registro), el **calendario y el precio** de cada
entrega y la **consulta** (lista y ficha). Modificar, rescindir, la pre-reserva diaria y la primera alerta comercial son de **COM-03b**.

**Estado de paso** (entre COM-03a y COM-03b; `docs/temas_abiertos.md`, «Abiertos desde el lote C5b»): un suministro pactado reserva solo los
períodos de la ventana; los siguientes recién se reservan con la pre-reserva diaria (paso 40, COM-03b). No rompe nada: es un estado de
desarrollo, como el de COM-05a1 y COM-05b.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-PCT-SUM | Pactar Suministro | docs/casos_de_uso/comercial/suministro.md | Postcondición f (planificar la entrega): se completa en COM-05a1 |
| COM-CNS-SUM | Consultar Suministro | docs/casos_de_uso/comercial/suministro.md | Se completan en COM-03b: «Sin cobertura completa» por alerta, la rescisión en la ficha y en la lista, «Ver historial de cambios» y los botones de la regla 10. Reglas 6 (entregado, con faltante), 7, 8 y 10 (cobro, solicitudes): COM-05a2 a COM-08 |

## Leer

- Casos de uso: de docs/casos_de_uso/comercial/suministro.md, **COM-PCT-SUM y COM-CNS-SUM completos**, «Cambios ya decididos» y, de «Cómo se
  aplica», las secciones «Fechas y precios», «COM-PCT-SUM», «COM-CNS-SUM» y «Lo que completa a COM-01, COM-02 y otras apps»; «Pantallas» y
  «Lo que difiere del prototipo» (las filas de pactar y consultar). De docs/casos_de_uso/produccion/stock_maduro.md, «Cómo se aplica»; de
  docs/casos_de_uso/comercial/compra_venta.md, «Cómo se aplica» (COM-REG-CVT: es el mismo esquema de formulario, recálculo, resumen,
  transacción y comprobante); de clientes.md, «Para más adelante».
- Modelo: docs/modelo/comercial.md (Contrato, ReservaStock, **Suministro, DetalleSuministro, ClausulaSuministrado y ClausulaSuministrante**,
  «Pendientes de MD», «Diferencias», filas 5 a 9). `AlertaComercial` **no**: es de COM-03b.
- Decisiones: D-61, D-59, D-60, D-14, D-25, D-27, D-28, D-29, D-36, D-37, D-44, D-54, D-57, D-58; **D-67, punto 2** (el corte).
- Patrones: **docs/patrones/stock_maduro.md, sección 7** (y las 1 a 6, ya programadas), docs/patrones/bloqueos.md (secciones `produccion` y
  `comercial`), docs/patrones/abm.md, docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md («Migraciones»).
- API: docs/api/notificaciones.md, docs/api/extensiones_de_maestros.md (traspaso), docs/api/extensiones_de_inventario.md (impedimento de baja
  de variedad).
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`): `tabContratos` (rama `sum`) y `ctrSel`; `INIT.sumnew`, `VIEWS.sumnew`,
  `detForm` y `detErr` (la **segunda** definición), `ACT['sumnew-ok']`; `VIEWS.sum` (la segunda definición, sin las partes de la
  rescisión), `versiones`, `ultimas`.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` completo (COM-01 y COM-02): modelos, `servicios/` (`clientes.py`, `compra_ventas.py`, `stock_maduro.py`, `comprobantes.py`),
    vistas, plantillas de compra-venta (el formulario se arma igual), `apps.py`, fábricas;
  - `maestros/servicios/invernaderos.py` (`bloquear_invernadero_activo`), `maestros/servicios/configuracion.py`;
  - `core/notificaciones.py`, `core/correo.py`, `core/models.py` (auditoría);
  - `inventario/servicios/stock.py` (`hoy`), `inventario/servicios/variedades.py`.

## Límites

- Crea modelos en `comercial`: `Suministro` (hija de `Contrato`), `DetalleSuministro`, `ClausulaSuministrado`, `ClausulaSuministrante`
  (con la abstracta `ClausulaResolutoria`), **con todos los campos y restricciones de sus fichas** (también los de la rescisión y
  `reemplaza_a`/`fecha_fin_detalle`, aunque los escriban COM-03b: así hay una sola migración de esas tablas); agrega
  `ReservaStock.detalle_suministro` con la restricción C3. `AlertaComercial` es de COM-03b.
  → revisá docs/disparadores.md: cierra «Completan el ABM de cliente», punto 2 (suministros), y la parte de suministros de «Cuando existan
  lotes, órdenes de trabajo y contratos», punto 2, y de «Cuando exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido» (traspaso, D-60).
- Migraciones:
  - `comercial/migrations/00NN_suministros.py`: las cuatro tablas, la FK nueva de `ReservaStock` con su restricción y la secuencia
    `comercial_suministro_numero_seq` (`RunSQL` con su reverso);
  - `core/migrations/00NN_comercial_suministros`: solo `choices` (acción `pacto_suministro`).
  Con el número libre en `main` al abrir el PR. **Ninguna de datos.** Ninguna en `maestros`.
- Permitido fuera de la app:
  - `core/models.py`: solo `Accion`, `ETIQUETAS` (los campos nuevos), `VALORES_VISIBLES` (`estado_suministro`, `mecanismo_precio`,
    `estado_detalle_suministro`) y `ACCIONES_DE_NEGOCIO`, y su migración;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`.
- Dependencias nuevas: ninguna (las fechas en meses se calculan con `calendar` de la biblioteca estándar).
- Fuera de alcance: **COM-03b** (modificar, rescindir, dejar sin efecto, la pre-reserva diaria y los pasos 35 y 40, `AlertaComercial` y la
  alerta «período sin cobertura completa», los orígenes de alertas en `maestros`); entregas (COM-05a1; postcondición f); concreción
  (COM-06); solicitudes y resolución (COM-07); cobros (COM-08); los asientos (D-57); reintentos automáticos de correos.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y auditoría.** Las fichas de `docs/modelo/comercial.md` con **todas** sus restricciones (rangos, mecanismo, par vigente, C3);
   `Suministro.codigo` (`SUM-0001`); la secuencia; la acción `pacto_suministro`. Fábricas: `suministro(...)`, `detalle_suministro(...)`,
   `periodo(...)`; y `verificar_invariantes_de_reservas()` con los invariantes nuevos de la sección 7 del patrón (salvo el de la rescisión,
   que suma COM-03b).
   Pruebas: `comercial/tests/test_modelos_suministros.py` (una por restricción, la viola y no la viola, también las de los campos de la
   rescisión).
2. **Calendario y precios** (`comercial/servicios/calendario.py`): `sumar_meses`, `meses_transcurridos`, `calendario`, `precio_en`,
   `rige_desde`, `ventana(hoy)`.
   Pruebas: `comercial/tests/test_calendario.py`, de tabla: 31/01 + 1 mes (año común y bisiesto), 30/11 + 3, 31/12 + 2; los dos ejemplos de
   meses transcurridos (22/10 → 21/12 y 22/12); el ejemplo del precio ($1.000, 3 %, cada 2 meses: meses 0 a 5) y el redondeo sin acumular;
   calendario con `fecha_fin_detalle`, con la fecha de fin del contrato y con un tramo `desde`/`hasta`; `fecha_base_ajuste` de un sucesor
   (con un sucesor de fábrica: el servicio que lo crea es de COM-03b).
3. **Stock maduro para períodos** (sección 7 del patrón): `Periodo`, `asignar` con un `Periodo`, `cantidad_sin_cubrir` y
   `sin_cubrir_de_periodos`, `repartir` (pura, la usa `asignar`) y `simular`.
   Pruebas: en `comercial/tests/test_prod_asg_stk.py`, las de un detalle de suministro (3b, anticipación de suministro, regla 3 de 8.11 con la
   postcosecha); `test_simular.py`: acumulado por variedad (dos períodos de 7 días con 14 de ventana y stock para uno solo: el segundo da su
   disponible real); **`simular` y `asignar` coinciden** con los mismos datos; ningún período con más cubierto que su cantidad.
4. **Pactar** (`comercial/servicios/suministros.py`): `pactar_suministro`, `datos_del_formulario`, `resumen`; el comprobante del suministro en
   `comprobantes.py`.
   Pruebas: `comercial/tests/test_com_pct_sum.py` (`ComPctSumServicioTests`): una por regla, postcondición y extensión (1a, 3a, 4a, 4b, 6a,
   8a, 8b, 9a a 9f, 11a, 11b, 7-11a, 12a, 13a.1a a 13a.1c, 14a, 15a); tolerados 0; superposición sin la casilla rechazada y con ella
   registrada; sin períodos en la ventana (no toma stock ni bloquea lotes: `assertNumQueries`); el Gerente como actor; el correo fuera de la
   transacción. Concurrencia (`test_suministros_concurrencia.py`): las tres del extracto (un pacto y una compra-venta por el último stock; un
   pacto contra la baja del cliente; dos pactos con el mismo par).
5. **Consultar** y lo que completa a COM-01 y COM-02: `buscar_suministros`, `ficha_de_suministro` (con el calendario por tramos); clientes,
   baja de variedad y traspaso de Vendedor (`suministro.md`, «Lo que completa…»).
   Pruebas: `comercial/tests/test_com_cns_sum.py` (`ComCnsSumServicioTests`): una por regla (alcance con 403; filtros; detalle como una línea
   por cadena; situación de cada período —«Fuera de la ventana», «Reservado», «Sin cobertura completa» por cantidad sin cubrir, «Pasado»—;
   «al límite»; sin consultas por fila). Las de COM-01 y COM-02 que esperaban «solo compra-ventas» se **reemplazan** por las que suman
   suministros (anotalas en el PR).
6. **Vistas, plantillas y pestaña.** Selector «Compra-ventas / Suministros» en «Contratos»; «Pactar suministro» (tres secciones y resumen a
   la derecha, como el prototipo, más la ventana de resumen), la ficha con el calendario, el comprobante imprimible y «Reenviar comprobante».
   Vistas que solo orquestan (`abm.md`, sección 1), `rol_requerido`, `never_cache`, `vary_on_headers("HX-Request")`, respaldo sin
   JavaScript, errores por campo, aviso breve (D-29). La ficha **todavía no** muestra «Modificar», «Rescindir» ni «Ver historial» (D-25: los
   suma COM-03b).
   Pruebas: `comercial/tests/test_suministros_vistas.py` (`ComPctSumVistaTests`, `ComCnsSumVistaTests`): permisos (los demás roles, 403;
   ningún botón lleva a un 403); los flujos con HTMX y sin él; `volver` desde el alta del cliente y desde «Cargar el correo»; `calcular/` no
   escribe nada.
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar los de «Límites»; marcar COM-03a en
   `docs/tareas/README.md` y en el plan; lo distinto de lo escrito, a `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió del
   prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es «Ver todo el calendario» de la ficha (queda el tramo por defecto y una línea en
`docs/temas_abiertos.md`). No se recortan las restricciones de la base, la verificación acumulada (9e), los bloqueos ni las pruebas de
concurrencia.

## Hecho cuando

- El Vendedor (y el Gerente, eligiendo el Vendedor) pacta un suministro con uno o más detalles: ve la fecha de fin, el calendario y el precio
  de cada entrega, y si los períodos de la ventana tienen stock; al confirmar, esos períodos quedan reservados (con sus cosechas si hace
  falta) y el cliente recibe el comprobante.
- La lista y la ficha de suministros muestran lo de COM-CNS-SUM que ya existe; el Vendedor ve solo los suyos.
- Todas las pruebas de `core` y de las tareas anteriores de `comercial` siguen pasando (las reemplazadas, anotadas).
- Comando de pruebas:
  python manage.py test comercial core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

**Datos para verificar** (`CLAUDE.md`, «Datos para la verificación a mano»; `docs/patrones/datos_de_verificacion.md`): antes de pedirle
al estudiante la verificación, Claude Code deja la base local cargada con lo que piden los pasos de abajo, ampliando el cargador de
`comercial` (`comercial/verificacion.py`, registrado en `ComercialConfig.ready()` con `registrar_cargador`, orden 20; lo crea COM-01;
cuentas `<rol>@prueba<N>.local` con el número libre al crearlo: hoy `prueba5`, porque `maestros` usa 1 y 2, `iot` 3 y `produccion` 4),
siempre llamando a los servicios. El estudiante no carga datos a mano. En el «Cierre», qué quedó cargado y con qué cuentas.

Hay migraciones nuevas (`comercial`, `core`): `python manage.py migrate`. Datos: los de la verificación de COM-02 (un invernadero con
Agrónomo, Capataz y Vendedor y un lote de «Lechuga Crespa» en Maduración con, por ejemplo, 300 plantas libres); un cliente **sin correo**
y otro con correo y dos direcciones. En «Configuración», pre-reserva de 14 días.

1. Con el Vendedor: «Contratos» › «Suministros» › «Pactar suministro». Elegí el cliente sin correo: las secciones 2 y 3 quedan bloqueadas y
   aparece «Cargar el correo». Cargalo y volvé: el cliente sigue elegido.
2. Duración 6 meses: «Termina el …» (mismo día del mes, 6 meses después). Tolerados 0: se acepta. Multa 50000, plazo de pago 15, atraso 100.
3. Detalle 1: Lechuga Crespa, dirección 1, 200 plantas cada 7 días, primera entrega en 3 días, precio fijo 1500. El calendario muestra dos
   fechas «se reserva ahora» y la segunda dice que no alcanza (hay 300 para 400). Cambiá a 150 plantas: las dos alcanzan.
4. Agregá el mismo par (variedad y dirección 1): error «El contrato ya tiene…». Cambiá a la dirección 2, ajuste periódico 3 % cada 2 meses:
   el calendario muestra los tramos de precio. Cláusulas de los dos detalles, con mínimo mayor que la cantidad: error; corregilo.
5. «Revisar y pactar»: el resumen; confirmá. La ficha: `SUM-0001` vigente, la cláusula, los dos detalles y el calendario con los períodos
   «Reservado» y los «Fuera de la ventana». Las cosechas notificadas al Capataz y al Agrónomo. En «Auditoría», un `pacto_suministro`.
6. Con otro cliente, pactá el mismo par: aviso de superposición con `SUM-0001`; sin marcar «Continuar igual» no deja confirmar.
7. Sin JavaScript, el pacto funciona con «Actualizar» y el resumen como página.
8. Después del merge: revisar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo** (rama `feature/com-03a-suministros-pactar-y-consultar`, 23/11/2026)

- **Modelos y migraciones** (ninguna de datos; `sqlmigrate` leído: solo `CREATE`, ningún `DROP`, `DELETE` ni `UPDATE`):
  - `comercial/0003_suministros`: `Suministro` (hija de `Contrato`, con los campos de la rescisión y `fecha_resolucion_suministro`), `DetalleSuministro`
    (con `reemplaza_a`, `fecha_fin_detalle` y `fecha_base_ajuste`), `ClausulaSuministrado` y `ClausulaSuministrante` (con la abstracta `ClausulaResolutoria`),
    `ReservaStock.detalle_suministro` con la restricción C3 (`reserva_stock_un_solo_detalle`) y la secuencia `comercial_suministro_numero_seq` (con su reverso). Todas las
    restricciones de las fichas; el par vigente (variedad, dirección) es un `UniqueConstraint` con `condition`.
  - `core/0028_comercial_suministros`: solo `choices` (`pacto_suministro`; SQL vacío). `core/models.py`: `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`, nada más.
- **Servicios de `comercial`:**
  - `calendario.py` (nuevo, funciones puras): `sumar_meses`, `meses_transcurridos`, `calendario`, `precio_en`, `tramos_de_precio`, `ventana` y `rige_desde`.
  - `stock_maduro.py`: `Periodo`, `asignar` y `cantidad_sin_cubrir` con un período, `sin_cubrir_de_periodos` (una consulta), `simular` y `simular_varias` (verificación
    acumulada), `Cobertura`, y la lectura de candidatos para varias fechas y variedades de una vez (`_leer_varias`). `disponible` y `asignar` de compra-venta hacen
    **exactamente las mismas consultas que antes** (9 y 23 en el escenario de comparación, medidos contra el módulo de `HEAD`).
  - `suministros.py` (nuevo): `pactar_suministro`, `datos_del_formulario`, `resumen`, `puede_pactar`, `datos_del_comprobante`, `buscar_suministros`, `ficha_de_suministro`,
    `calendario_completo` y `suministro_del_alcance`.
  - `comprobantes.py`: una sola función para los dos tipos (asunto, plantilla y contexto por tipo; plantilla `comprobante_suministro.txt`). El correo sale fuera de la transacción.
  - Lo que completa a COM-01 y COM-02: `clientes.py` (`direcciones_en_uso`, `impide_quitar_el_correo`, `pendientes_del_cliente`, `contratos_del_cliente`,
    `contratos_vigentes_por_cliente`) y `registrantes.py` (traspaso de Vendedor de D-60 e impedimento `contratos_abiertos`).
- **Pantallas:** pestaña «Contratos» con el selector «Compra-ventas / Suministros»; lista de suministros con filtros en la URL; «Pactar suministro» (tres secciones y resumen a
  la derecha, recálculo HTMX solo en selectores y botones, ventana de resumen y página sin JavaScript); ficha con el calendario; «Ver todo el calendario»; comprobante
  imprimible y «Reenviar comprobante»; los suministros en la ficha y en la lista de clientes. Vistas en `views_suministros.py` (las de COM-02 siguen en `views_contratos.py`).
- **Disparadores** que se cumplieron (para tachar, M3): «Completan el ABM de cliente», punto 2; la parte de suministros de «Cuando existan lotes, órdenes de trabajo y contratos»,
  punto 2; y el traspaso de «Cuando exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido», punto 1 (suministros vigentes, D-60).
- **Estado de paso** (hasta COM-03b): un suministro pactado reserva solo los períodos de la ventana; los siguientes los reserva la pre-reserva diaria (paso 40, COM-03b).
  La ficha todavía no tiene «Modificar», «Rescindir» ni «Ver historial» (D-25). Postcondición f (planificar la entrega) se completa en COM-05.

**Pruebas** (M1; comandos de «Hecho cuando»)

- `manage.py test comercial core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **1513 pruebas, OK** (6 omitidas: las visuales, que se corren aparte).
- `manage.py test comercial --keepdb --tag concurrencia`: **27 pruebas, OK** (22 de antes y las 5 nuevas).
- Además, por haber tocado los puntos de extensión que usan otras apps: `maestros`, `inventario` y `produccion` (3223 pruebas, en serie): **un solo fallo, ajeno a la tarea**:
  `produccion.tests.test_prod_reg_apl…consumo_originado_en_el_consumo` espera la fecha local y el movimiento de insumo toma la de UTC; falla después de las 21 h en Argentina
  (UTC−3), con o sin esta tarea (no se tocó `produccion` ni `inventario`). Anotado en `docs/temas_abiertos.md`.
- Nuevas: `test_modelos_suministros.py` (30), `test_calendario.py` (35), `test_simular.py` (13), `test_com_pct_sum.py` (70), `test_suministros_concurrencia.py` (5), `test_com_cns_sum.py` (29),
  `test_suministros_vistas.py` (38), `test_recorrido_suministros.py` (2) y `test_visual_suministros.py` (6, Playwright). Ampliadas: `test_prod_asg_stk.py` (+23, en la clase de períodos),
  `test_extensiones_de_produccion.py` (+1), `test_impedimento_de_variedad.py` (+6), `test_traspaso_de_vendedor.py` (+8), `test_clientes_con_compra_ventas.py` (+7) y `test_com_mod_clt.py` (+3).
- **Pruebas de COM-01 y COM-02 reemplazadas** (para anotar en el PR; ninguna se borró ni se debilitó: cambió la regla):
  - `test_prod_asg_stk.py`: «Hasta COM-03 el detalle es un `DetalleVenta`» → ahora acepta también un `Periodo` y rechaza cualquier otra cosa.
  - `test_impedimento_de_variedad.py` (3) y `test_stock_maduro_concurrencia.py` (1): el texto «Tiene compra-ventas abiertas: N.» pasa a «Tiene contratos abiertos: 2 compra-ventas y 1 suministro.».
  - `test_clientes_con_compra_ventas.py`: `contratos_vigentes_por_cliente` hace 2 consultas (una por clase de contrato), no 1.
  - `test_com_mod_clt.py`: «`impide_quitar_el_correo` devuelve siempre `False` en COM-01» → solo el caso sin suministros (los demás, en `ComModCltConSuministrosTests`).
  - `test_clientes_vistas.py`: «Todavía no tiene compra-ventas.» → «Todavía no tiene contratos.».

**Decisiones:** ninguna nueva de equipo (`D-NN`). Aplicadas D-14, D-25, D-27, D-28, D-29, D-36, D-37, D-44, D-54, D-57, D-58, D-59, D-60, D-61 y D-67 (punto 2). Las decisiones de aplicación que aprobaste con
el plan y los desvíos (para `docs/temas_abiertos.md`; no los corregí en silencio):

1. **Cantidad sin cubrir de un período**: la sección 7 del patrón la escribe con `Σ cantidad_reservada`; se usa la cantidad **cubierta** (`min(cosechada, reservada)` en un lote ya cosechado), igual que
   `cantidad_sin_cubrir` de COM-02 y que la regla 10 de 8.8. Hasta COM-04 no hay cosechas concretadas y dan lo mismo.
2. **`simular_varias`** (el patrón nombra solo `simular`) y la lectura de candidatos para varias fechas: una consulta por tabla con 1 o con 40 períodos. `Cobertura.disponible` es lo libre
   para ese pedido después de los anteriores; `cubierta` es `min(cantidad, disponible)`.
3. **`rige_desde(detalle, hoy)`**: su definición está en «Cómo se aplica · COM-MOD-SUM» (`suministro.md`, línea 833), que «Leer» no listaba; se leyó solo esa línea. Conviene sumarla a «Leer».
4. **Marca «Al límite»** (regla 9): el prototipo la pone cuando queda 1 tolerado; se pone también cuando ya se usaron todos (incumplimientos ≥ tolerados − 1). El aviso de la ficha tiene tres textos:
   los dos del prototipo y, con 0 tolerados, «El contrato no tolera incumplimientos: el primero lo resuelve y se aplica la multa.» (texto propio: el extracto no cubre ese caso).
5. **Texto de la baja de variedad**: «Tiene contratos abiertos: N compra-ventas y M suministros.» omitiendo el número que vale 0 y con singular («1 suministro»). Cambia el texto de COM-02.
6. **Traspaso**: `contar` suma la línea «Suministros vigentes: M» después de «Compra-ventas abiertas: N»; `traspasar` devuelve las dos clases. `pendientes_del_cliente` informa primero los
   suministros vigentes (orden de la regla 1 de COM-BAJ-CLT).
7. **Superposición (9d)**: la casilla «Continuar igual» es por detalle (`detalle-<i>-continuar`); sin ella el servicio rechaza con `superposicion_sin_confirmar`, también en un pacto del Gerente.
8. **Códigos y campos de error** (los usan COM-03b y COM-05): `vendedor_obligatorio|invalido|inactivo|sin_invernaderos`, `cliente_obligatorio|inactivo|sin_correo`, `duracion_invalida`,
   `tolerados_invalidos`, `multa_invalida`, `plazo_pago_invalido`, `indemnizacion_pago_invalida`, `variedad_obligatoria|inactiva`, `direccion_obligatoria|no_valida`, `cantidad_invalida`,
   `periodo_invalido`, `fecha_obligatoria|invalida|fuera_de_rango`, `mecanismo_invalido`, `precio_invalido`, `porcentaje_invalido`, `meses_invalidos`, `plazo_entrega_invalido`,
   `indemnizacion_retraso_invalida`, `cantidad_minima_invalida`, `indemnizacion_faltante_invalida`, `par_repetido`, `superposicion_sin_confirmar`, `supera_disponible` (9e, al revisar),
   `stock_insuficiente` (14a, al confirmar), `sin_detalles`, `cambio_simultaneo`. Campos: `vendedor`, `cliente`, `duracion`, `tolerados`, `multa`, `plazo_pago`, `indemnizacion_pago`,
   `detalle-<i>-<campo>` (`variedad`, `direccion`, `cantidad`, `periodo`, `primera_entrega`, `mecanismo`, `precio`, `porcentaje`, `meses`, `plazo_entrega`, `indemnizacion_retraso`,
   `cantidad_minima`, `indemnizacion_faltante`, `continuar`) y `__all__`. Importes con coma o punto decimal; fechas `aaaa-mm-dd` o `dd/mm/aaaa`.
9. **Ficha con detalles finalizados**: un período de un detalle finalizado que cae dentro de la ventana se muestra «Reservado» si no tiene cantidad sin cubrir (los finalizados no la tienen
   hasta COM-04, D-64 punto 8). Es un hueco conocido: COM-03b/COM-04 lo cierran.
10. **`Suministro.solicitud_resolucion` no se crea** (lo crea COM-07a con su restricción); sí `fecha_resolucion_suministro` y los seis campos de la rescisión.
11. **Fuera de lo que decía «Permitido fuera de la app»**: nada de `maestros`, `produccion` ni `inventario`. En `comercial` se tocaron cosas de COM-01 y COM-02 que el cierre lista arriba y esto:
    `contratos/lista.html` (el selector), `clientes/ficha.html` (suministros), `contratos/comprobante.html` (le faltaba la hoja de estilos del sistema: salía con el estilo del navegador) y
    `comercial.css` (reglas nuevas y tres correcciones: la unidad de un campo, el CUIT y el resumen del formulario de COM-02).
12. **La tarea nombraba `comercial/verificacion.py` y el cargador** de datos de verificación: se ignoraron (D-95). Los pasos de «Verificación a mano» se convirtieron en el recorrido.
13. **Playwright**: no estaba instalado en el entorno de desarrollo; se instaló desde `requirements-dev.txt` (ya listado; no se tocó `requirements.txt`) y Chromium con `python -m playwright install chromium`.

**Pantallas: lo que se corrigió del prototipo** (D-61)

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| `sumnew`, `summod` | Pactaba sin resumen | Ventana de resumen (y página sin JavaScript) con «Confirmar suministro» y «Volver a la carga» | Pasos 12, 13 y 13a |
| `sumnew` | Fecha de fin = hoy + 30 × meses; duración «de 1 a 36 meses» | `sumar_meses` («Termina el dd/mm/aaaa» al lado de la duración); de 1 a 120 | Regla «Fecha de fin» y «Datos del contrato» |
| `detForm` | Re-dibujaba al tipear (a los 400 ms) y validaba | Solo los selectores y los botones redibujan, sin validar; «Actualizar» y el primer botón oculto del formulario (así «Enter» no quita nada) | `.claude/rules/interfaz.md` |
| `detForm` | Sin opciones rápidas de período | Botones 7, 14 y 30 días junto al campo libre | Variación 8b |
| `detForm` | Tolerancia de entrega opcional; plazo de pago desde 1 | Obligatoria, de 0 a 365; plazo de pago desde 0 | Reglas de las dos cláusulas |
| `sumnew` | Calendario: solo la cantidad de entregas | Cantidad, total de plantas, las primeras 12 fechas con «se reserva ahora» (y «y N más»), los tramos de precio y la verificación de stock de la ventana | Paso 9, 8b y 9e |
| `sumnew` | Sin avisos de superposición ni de ajuste sin efecto | Aviso 9d con enlace al otro contrato y la casilla «Continuar igual»; aviso 9f | Extensiones 9d y 9f |
| `sumnew` | Correo del cliente: aviso que deja seguir | Bloquea las secciones 2 y 3 y ofrece «Cargar el correo» (vuelve con el cliente elegido) | Extensión 4b |
| `sumnew` | El cliente se elegía de una lista | Buscador con «Buscar» y «Elegir» (nunca al tipear) y enlace al alta con `volver`; «Cambiar» descarta las direcciones de los detalles | Pasos 3, 3a y 4a; 13a.1b |
| `ctrSel` | Un `<select>` en la barra de filtros | Dos enlaces «Compra-ventas / Suministros» (cada tipo es una página con sus filtros; funciona sin JavaScript) | D-61; interfaz |
| `VIEWS.sum` | Calendario con un tramo fijo | El tramo por defecto (30 días atrás hasta 28 después de la ventana) y «Ver todo el calendario» paginado de a 100; «Reservado» y «Sin cobertura completa · faltan N» salen de las reservas | Regla 6 |
| `VIEWS.sum` | «Registrar cobro» y solicitudes en la ficha | No se muestran (las suman COM-07 y COM-08); tampoco «Modificar», «Rescindir» ni «Ver historial» (COM-03b) | D-25 |
| `VIEWS.sum` | Sin estado del comprobante | Estado, «Ver comprobante» imprimible y «Reenviar comprobante» | Extensión 15a |
| `VIEWS.sum` | Sin estado vacío ni secciones bloqueadas | Estado vacío de la lista, «Pactar suministro» deshabilitado con su motivo (b y c), pasos bloqueados con lo que falta | Precondiciones b y c |
| *Verificación visual* | La unidad de un campo («meses», «$ por día») quedaba debajo del campo | Unidad junto al campo (`.suf`) | Criterio de interfaz |
| *Verificación visual* | CUIT pegado al nombre del cliente; resumen angosto con textos cortados (también en COM-02) | Línea propia para el CUIT y el resumen en una columna | Criterio de interfaz |
| *Verificación visual* | En un celular la grilla ensanchaba la página; en la ficha los enlaces eran azules del navegador | `minmax(0, 1fr)` y `min-width: 0`; enlaces en el verde primario | Interfaz; celular |
| *Verificación visual* | «Ajuste» y «Cada» aplastados en la cuarta columna | Fila propia para el ajuste periódico | Extensión 8b |
| *Verificación visual* | El comprobante imprimible salía con el estilo por defecto del navegador (también el de COM-02) | Se carga la hoja de estilos del sistema | Variación 15a |
| *Verificación visual* | El precio del calendario se partía en dos líneas en un celular | Sin cortes (`nowrap`) | Celular |
| *Verificación visual* | El resumen mostraba «50000 $» tal como se tipeó | Importes en pesos con formato («$ 50.000,00») | Reglas «Datos del contrato» |

**Recorrido de verificación y verificación** (D-95: la hizo Claude Code; el estudiante no cargó datos ni verificó a mano)

*Recorrido* (`comercial/tests/test_recorrido_suministros.py`, `RecorridoDeSuministrosTests`): los pasos 1 a 7 de la antigua «Verificación a mano», de punta a punta con el cliente de Django:
(1) un cliente sin correo bloquea las secciones y «Cargar el correo» vuelve con el cliente elegido; (2) la fecha de fin y tolerados 0; (3) con 300 plantas, dos períodos de 200 en la ventana: el segundo no alcanza;
con 150, sí; (4) par repetido, ajuste periódico con sus tramos, mínimo mayor que la cantidad; (5) resumen, pacto, reservas, notificaciones al Capataz y al Agrónomo, auditoría `pacto_suministro` y comprobante;
(6) superposición con y sin la casilla; (7) todo sin JavaScript. Y por rol: el Gerente elige al Vendedor, el Vendedor ajeno recibe 403 (con mensaje) y no lo ve en su lista, el Agrónomo recibe 403 en todo.

*Visual* (`test_visual_suministros.py`, Playwright + Chromium, 6 pruebas, 19 capturas que miré una por una): la lista con el selector, el formulario con HTMX (recálculo, ajuste periódico, opciones de período,
error de stock, ventana del resumen), la ficha con todas las situaciones del calendario, el calendario completo, el comprobante, el Gerente, el Agrónomo (403), cuatro pantallas en un celular (sin scroll horizontal)
y el pacto entero sin JavaScript. Sin errores de JavaScript ni de consola. Lo que vi mal se corrigió (tabla de arriba).

*Migraciones*: `makemigrations --check` sin cambios; `sqlmigrate comercial 0003` leído (solo `CREATE`; la secuencia con su reverso) y `core 0028` (sin SQL); aplicadas en la base de pruebas (se recreó dos veces); `manage.py check` sin problemas.

**Verifiqué:** todo lo anterior, con su resultado. Además, medí que `disponible` y `asignar` de compra-venta mantienen sus consultas (9 y 23) contra el módulo de `HEAD`.

**Lo cubre una prueba:** pactar (`test_com_pct_sum.py`: una por regla, postcondición y extensión de la lista de la tarea); los bloqueos y los tres choques de concurrencia (`test_suministros_concurrencia.py`);
la consulta (`test_com_cns_sum.py`); el cálculo (`test_calendario.py`, `test_simular.py`, `test_prod_asg_stk.py`); lo que completa a clientes, baja de variedad y traspaso (los cuatro archivos ampliados);
las pantallas y el `volver` (`test_suministros_vistas.py`); el flujo completo (`test_recorrido_suministros.py`).

**No pude verificar:**
- El envío real de un correo (las pruebas usan `enviar_correo` simulado): con SMTP real, que el comprobante llegue y se lea bien.
- Que Render aplicó `comercial/0003` y `core/0028` (log del despliegue) y que las pantallas abren en producción (Neon).
- Impresión real del comprobante (el botón «Imprimir» y el papel) y navegadores que no sean Chromium (Firefox, Edge).
- Georef real de producción (las pruebas usan los datos de la migración): que las direcciones del cliente se listen con su localidad.
- Criterio de producto: si la pantalla «Pactar suministro» (con muchos detalles) se siente cómoda para el Jardín Botánico.

**Pasos para replicar** (opcionales; para el estudiante, autocontenidos)

*Antes de empezar.* Con el entorno virtual activo: `python manage.py migrate` (aplica `comercial` 0003 y `core` 0028) y `python manage.py runserver`; abrí `http://127.0.0.1:8000/`. No hay datos
cargados: hay que crearlos a mano, en este orden. (1) Con el Gerente, en «Usuarios y seguridad», creá un Agrónomo, un Capataz y dos Vendedores (el segundo, para el paso 11); la contraseña es la que definas.
(2) En «Producción», creá un invernadero con ese Agrónomo, ese Capataz y el primer Vendedor, sus sectores y una variedad («Lechuga Crespa») con su ciclo; sembrá y avanzá un lote hasta «Maduración» con
**300 plantas**, como en las rondas de producción (las pruebas lo arman por código, así que este paso es el único que no pude recorrer en el navegador). (3) En «Comercial» › «Clientes», creá «Verdulería Los Pinos S.R.L.» (CUIT de ejemplo 30-71234567-1) **con** correo
(`compras@lospinos.com`) y dos direcciones («San Martín 123, Garupá» y «Belgrano 45, Garupá»), y «Verdulería Sin Correo S.A.» (CUIT 30-71234568-9) **sin** correo y con una dirección. (4) En «Configuración», la
pre-reserva de suministros en 14 días (viene así). Entrá con el primer Vendedor.

1. **Lista y selector.** «Comercial» › «Contratos»: arriba a la izquierda, «Compra-ventas | Suministros». Tocá «Suministros»: dice «Todavía no hay suministros.» y hay un botón verde «Pactar suministro».
2. **Cliente sin correo.** «Pactar suministro». En «Buscar al cliente» escribí «Sin Correo» y tocá «Buscar» › «Elegir». Tiene que aparecer un aviso rojo «El cliente no tiene correo…» con «Cargar el correo», y las
   secciones 2 y 3 dicen «Cargá el correo del cliente para seguir.». Tocá «Cargar el correo», escribí un correo, guardá: volvés a «Pactar suministro» con el cliente todavía elegido y la sección 2 habilitada.
   Tocá «Cambiar» y elegí «Los Pinos».
3. **Contrato.** Duración 6: al lado dice «Termina el» con el mismo día del mes, 6 meses después. Tolerados 0, multa 50000, plazo de pago 15, indemnización por atraso 100.
4. **Detalle 1 y el stock.** Variedad «Lechuga Crespa», la dirección San Martín, cantidad 200, período 7 (o el botón «7»), primera entrega dentro de 3 días, precio fijo 1500, tolerancia 1, retraso 100, mínima 50,
   faltante 30. Tocá «Actualizar»: aparecen las fechas (las dos primeras dicen «se reserva ahora») y una tabla «Se reserva ahora» donde el segundo período dice **No alcanza** (hay 300 para 400). Cambiá la
   cantidad a 150 y «Actualizar»: los dos dicen **Alcanza**.
5. **Errores.** «Agregar detalle», misma variedad y misma dirección: al «Revisar y pactar» el error «El contrato ya tiene Lechuga Crespa para esa dirección: es el detalle 1.». Cambiá a la dirección Belgrano,
   mecanismo «Ajuste periódico», 3 % cada 2 meses: se ve «Desde el dd/mm: $ …» con tramos. Poné cantidad mínima 20 con cantidad 10: «Ingresá un número entero de plantas, de 1 a 10.»; corregilo (5).
6. **Pactar.** «Revisar y pactar»: la ventana con el resumen (cliente, fechas, cláusulas, cada detalle). «Confirmar suministro». La ficha: `SUM-0001` «Vigente», «Al límite» no (con tolerados 0 sí: dice «El contrato no
   tolera incumplimientos…»), la cláusula, los dos detalles y el calendario con «Reservado» (los dos períodos de la ventana) y «Fuera de la ventana». Con el Capataz y el Agrónomo: la campana tiene «Nueva cosecha OT-…» (dos
   por cada uno). Con el Gerente, «Auditoría»: un registro «Pacto de suministro». Con el correo del sistema sin configurar, el aviso dice que el comprobante quedó pendiente: «Reenviar comprobante» en la ficha.
7. **Superposición.** Pactá otro suministro con el mismo cliente, variedad y dirección: debajo del detalle sale el aviso con `SUM-0001` y la casilla «Continuar igual»; sin marcarla, «Revisar y pactar» no deja. Con
   otro cliente, no hay aviso.
8. **Consulta.** En «Contratos» › «Suministros»: filtros por cliente, estado y fechas; «Al límite» en el que tiene 0 tolerados. En la ficha: «Ver todo el calendario» (página de períodos) y «Ver comprobante» (se abre
   la hoja imprimible). En «Clientes» › «Verdulería Los Pinos» ➔ «Contratos»: aparece el suministro. Con el Gerente, «Dar de baja» al cliente: la ventana nombra «Suministros vigentes: …».
9. **Roles.** Entrá con el Agrónomo y escribí `/comercial/contratos/?tipo=suministro` en la barra: 403. Entrá con el segundo Vendedor: la lista no trae el `SUM-0001` y `/comercial/contratos/suministros/<id>/` da 403.
10. **Baja de variedad y cambio de Vendedor.** Con el Agrónomo, intentá dar de baja «Lechuga Crespa»: «Tiene contratos abiertos: 2 suministros.». Con el Gerente, en el invernadero, cambiá su Vendedor por el
    segundo: el aviso dice «Suministros vigentes: 2» y después los contratos son del Vendedor nuevo (las reservas no se mueven).
11. *(opcional)* **Sin JavaScript** (desactivalo en el navegador): el pacto funciona con «Actualizar» y el resumen como página. **En un celular** (ancho de 390 px): la lista, el formulario, la ficha y el
    calendario no se desbordan.
12. *(después del merge)* En el log de Render, que se aplicaron `comercial/0003_suministros` y `core/0028_comercial_suministros`.

*Lo que ya cubre el recorrido*: los pasos 2 a 8 (con el cliente de Django) y las capturas del navegador; si tenés poco tiempo, concentrate en el 4 (tabla de stock), el 6 (ficha y avisos) y el 9.
