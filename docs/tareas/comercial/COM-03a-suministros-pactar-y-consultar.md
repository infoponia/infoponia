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

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
