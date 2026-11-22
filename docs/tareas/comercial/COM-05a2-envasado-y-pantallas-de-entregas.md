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

Hay migraciones nuevas (`produccion`, `core`): `python manage.py migrate`. Datos: los de COM-05a1; un envase «Bandeja PET 1 kg» habilitado en
«Sur» con 30 unidades.

1. Planificá una entrega nueva (una venta que sale toda de cámara, o una cosecha concretada): el Agrónomo tiene «Planificá el envasado…».
2. Con el Agrónomo: «Producción» › «Envasado»: la entrega dice «Sin planificar». Planificá 40 bandejas: «Supera lo disponible: quedan 30…».
   Poné 20, revisá el resumen y confirmá: «Planificado». Volvé a entrar: cambiá a 25, quitá y volvé a agregar la bandeja; el resumen muestra
   antes y después. Sin cambios: «No hay cambios para registrar.».
3. En la ficha de la compra-venta: la sección «Entregas»; en la del suministro, «Entrega planificada» en el calendario y la sección de entregas.
4. En el panel del Gerente y del Vendedor, el grupo «Entregas»; en el del Agrónomo, «Entregas sin envasado».
5. Vehículos: la columna «Entregas a realizar» y, en la ficha, la carga de los próximos días.
6. Vencé en cámara la partida de una entrega con envasado que queda vacía: la entrega se cancela, el Agrónomo tiene el aviso y las bandejas
   vuelven a estar libres.
7. Sin JavaScript: el envasado funciona con «Actualizar».
8. Después del merge: revisar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
