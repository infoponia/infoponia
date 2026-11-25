# CON-04a · Asientos de producción (reapertura)

Estado: pendiente | App: produccion | Rama: feature/con-04a-asientos-de-produccion | Ronda: Contabilidad 2

Depende de: **CON-02** (si no está en `main`, frená). PRD-01 a PRD-04 ya están (PRD-04 se mergeó el 23/11/2026, PR #58, sin CON-02):
la fila de PROD-PNR-FDS la hacés acá (D-92 punto 9).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Los casos de uso de producción que hoy guardan su monto pero no asientan (D-45) pasan a generar su asiento automático. No hay
pantallas nuevas: los resúmenes y las fichas suman «el asiento que se registrará» o «el asiento registrado» donde el caso de uso lo dice.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Asiento (origen · Debe / Haber · monto · fecha) | Dónde (código actual) |
|---|---|---|---|---|
| PROD-CNC-SMB | Concretar Siembra (post. j) | docs/casos_de_uso/produccion/siembra.md | Cada `Consumo` · Productos en Proceso / Insumos en Stock · `monto_consumo` · fecha efectiva de la siembra | `siembras._registrar_concrecion`, después de crear cada consumo |
| PROD-CNC-TRN | Concretar Transición (merma, post. e) | docs/casos_de_uso/produccion/transicion.md | La `Merma` · Pérdidas por Mermas / Productos en Proceso · `ResultadoMerma.costo` · fecha efectiva | `transiciones._escribir_concrecion`, después de `aplicar_merma` |
| PROD-REG-MRM | Registrar Merma (lote en pie, post. e) | docs/casos_de_uso/produccion/merma.md | La `Merma` · Pérdidas por Mermas / Productos en Proceso · `ResultadoMerma.costo` · fecha de la merma | `mermas._escribir`, después de `aplicar_merma` |
| PROD-REG-APL | Registrar Aplicación de Insumos (post. f) | docs/casos_de_uso/produccion/aplicacion_de_insumos.md | Cada `Consumo` · Productos en Proceso (si se imputó a lotes) o Gastos de Producción (si va a gasto) / Insumos en Stock · `monto_consumo` · fecha de la aplicación | `aplicaciones._escribir`, después de cada consumo y sus imputaciones |
| PROD-PNR-FDS | Poner Sector Fuera de Servicio (mermas) | docs/casos_de_uso/produccion/sector_fuera_de_servicio.md | Cada `Merma` · Pérdidas por Mermas / Productos en Proceso · su costo · fecha del fuera de servicio | `sectores_fuera_de_servicio._escribir`, después de cada `aplicar_merma` (D-92 punto 9) |

Las marcas «Fuera de la ronda (D-45)» de esos extractos, en lo contable, **se programan acá**. Las precondiciones «existe un ejercicio
vigente y existen las cuentas…» y sus extensiones no se programan (D-92 punto 2).

## Leer

- Casos de uso: de cada extracto, **solo** la postcondición del asiento, la regla «Asientos» y la sección «Fuera de la ronda (D-45)».
- Decisiones: D-92 (la de la ronda), D-86 (el contrato), D-84 (puntos 5 y 7), D-50 (punto 5, costo), D-51 (punto 4, reparto), D-45, D-44.
- API: docs/api/asientos.md (`registrar_asiento_automatico`).
- Patrones: docs/patrones/asientos.md, docs/patrones/bloqueos.md («Contabilidad: el ejercicio se bloquea último» y «`produccion`»),
  docs/patrones/costo_del_lote.md.
- Reglas: .claude/rules/pruebas.md.
- Código a leer: `produccion/servicios/siembras.py` (`_registrar_concrecion`), `transiciones.py` (`_escribir_concrecion`), `mermas.py`
  (`aplicar_merma`, `_escribir`), `aplicaciones.py` (`_escribir`), `costos.py`; `contabilidad/servicios/asientos.py` y `contabilidad/cuentas.py`;
  las pruebas de cada caso de uso (`test_prod_cnc_smb.py`, `test_prod_cnc_trn.py`, `test_prod_reg_mrm.py`, `test_prod_reg_apl.py`) y las de
  concurrencia (`test_siembras_concurrencia.py`, `test_transiciones_concurrencia.py`, `test_merma_concurrencia.py`, `test_aplicaciones_concurrencia.py`).

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: `contabilidad/cuentas.py` (solo el texto de `DESCRIPCION_DE_CUENTA` de las cuentas que esta tarea mueve, si
  difiere de `docs/casos_de_uso/contabilidad/plan_de_cuentas.md`); al cerrar, los archivos de M3 y `docs/disparadores.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: inventario (CON-04b), comercial (CON-04c y CON-04d), el lote existente (PRD-05), asientos hacia atrás (D-92 punto 1).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Siembra.** — pruebas: `test_prod_cnc_smb.py` (postcondición j: un asiento por consumo; consumo de $0 sin asiento) y
   `test_siembras_concurrencia.py` (concretar contra cerrar el ejercicio en cierre).
2. **Merma y transición** (las dos llaman a `aplicar_merma`; el asiento va en quien llama, D-92 «alternativas»). — pruebas:
   `test_prod_reg_mrm.py`, `test_prod_cnc_trn.py` (post. e), `test_merma_concurrencia.py`.
3. **Aplicación de insumos** (lote o gasto, según el destino del consumo). — pruebas: `test_prod_reg_apl.py`, `test_aplicaciones_concurrencia.py`.
4. **Fuera de servicio** (`poner_fuera_de_servicio`: un asiento por cada merma; la reubicación no asienta). — pruebas: `test_prod_pnr_fds.py`,
   `test_fds_concurrencia.py` (poner fuera de servicio contra cerrar el ejercicio en cierre).
5. **Resúmenes:** donde el caso de uso muestra el asiento antes de confirmar o después, mostralo (cuentas e importe).

## Hecho cuando

- Cada caso de uso de la tabla genera su asiento con las cuentas, el importe y la fecha de la tabla; el libro de gestión (CON-03a) lo muestra con
  su enlace al origen.
- Ninguna prueba previa se rompe salvo las que verificaban «no hay asiento», que se actualizan.
- Comando de pruebas: `python manage.py test produccion contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test produccion --keepdb --tag concurrencia`.

## Verificación a mano

Para la persona que revisa. No hace falta haber visto la sesión ni el código. **Ninguna base se cargó ni se tocó**: los datos los creás vos.

**Antes de empezar**
- No hay migración nueva: alcanza con tener la base local al día (`python manage.py migrate`) y levantar el servidor (`python manage.py runserver`, dirección `http://localhost:8000`). La contraseña de las cuentas va por tu variable o por prompt; no la escribas en ningún archivo.
- Cuentas necesarias (Gerente → «Cuentas»): un **Agrónomo**, un **Capataz**, un **Contador** y un **Vendedor** (este último solo para el paso 13). Dejá al **Gerente** como está.
- Datos, en este orden y con estos valores:
  1. **Invernadero** «Invernadero Norte» con el Agrónomo a cargo y el Capataz asignado.
  2. **Sectores** (dentro del invernadero): «Germinación 1» (tipo Germinación, 100 agujeros), «Crecimiento 1» (tipo Crecimiento, 100 agujeros) y «Crecimiento 2» (tipo Crecimiento, 100 agujeros).
  3. **Variedad** «Lechuga Crespa» con un ciclo de dos etapas: Germinación y Crecimiento (10 días cada una). Habilitá su semilla en el invernadero con **precio de referencia $ 2,00** y ajustá el stock a **1.000 unidades**.
  4. Un insumo **«Limpiador»** (unidad: litros) de una categoría con consumo **«como gasto»**, habilitado en el invernadero con **precio $ 5,00** y **20 L** de stock. Un insumo **«Abono»** (kg) de una categoría con consumo **«como costo de los lotes»**, **precio $ 4,00**, **30 kg** de stock.
  5. No hay que poner en marcha la contabilidad: el primer ejercicio se abre solo con el primer asiento (D-84 punto 3).

**Pasos** (los marcados «lo cubre…» ya los prueba el CI; si tenés poco tiempo, concentrate en los demás)

1. **El libro, vacío.** Entrá como **Contador** → «Contabilidad › Libro de gestión». No tiene que haber asientos. *(lo cubre `test_recorrido_asientos_de_produccion.py`)*
2. **Siembra (post. j de PROD-CNC-SMB).** Como **Agrónomo**: «Producción › Nueva siembra», 50 plantines de «Lechuga Crespa» en «Germinación 1», con la semilla. Como **Capataz**: «Bandeja» → la orden → «Concretar». Dejá todo lo propuesto, tocá **«Ver resumen»** y después **«Confirmar concreción»**. Tiene que volver a la bandeja con el aviso «La siembra quedó concretada: se creó el lote L-…». Tomá nota del código del lote.
3. **Su asiento.** Como **Contador**: «Contabilidad › Libro de gestión». Tiene que haber **un asiento N.º 1**, con la fecha de hoy: Debe **Productos en Proceso** $ 100,00 / Haber **Insumos en Stock** $ 100,00 (50 × $ 2,00). Entrá a su ficha: el origen dice «Consumo · Siembra OT-…: Semilla Lechuga Crespa, 50 unidades» y **no es un enlace** (a propósito: el Contador no abre las pantallas de producción). *(lo cubre `ConcretarSiembraAsientoTests`)*
4. **Un asiento por consumo.** Repetí la siembra (otra orden, 10 plantines en «Crecimiento 1») reservando también 5 kg de «Abono» como insumo adicional. En el libro tienen que aparecer **dos asientos nuevos** (uno por la semilla y uno por el abono, de $ 20,00 y $ 20,00 en este caso), cada uno con su consumo. *(lo cubre `test_post_j_un_asiento_por_consumo…` y `test_regla_h8_dos_concreciones…`)*
5. **Transición con plantas perdidas (post. e de PROD-REG-MRM desde la transición).** Como **Agrónomo**: planificá la transición del primer lote a Crecimiento (todo el lote a «Crecimiento 1»). Como **Capataz**: concretala indicando **40** plantas ubicadas de 50; aparece el campo «Causa»: elegí «Plaga» y escribí «Hongo». «Ver resumen» y «Confirmar transición». En el libro: nuevo asiento **Debe Pérdidas por Mermas / Haber Productos en Proceso por $ 20,00** (10 plantas × $ 2,00), origen «Merma del lote L-… · Merma de 10 plantas por plaga. Hongo». Probá también concretar **sin** perder plantas: **no** debe aparecer ningún asiento. *(lo cubre `ConcretarTransicionAsientoTests`)*
6. **Merma (post. e de PROD-REG-MRM).** Como **Capataz**: «Registrar › Merma», el lote, **4 plantas** del sector, causa «Plaga». Resumen y confirmar. Asiento nuevo por **$ 8,00** (el costo del lote ya bajó: $ 80,00 × 4 ÷ 40). *(lo cubre `RegistrarMermaAsientoTests`)*
7. **Aplicación a gasto (post. f de PROD-REG-APL).** Como **Capataz**: «Registrar › Aplicación de insumos», todo el invernadero, **2 L de «Limpiador»**. Mientras la cargás **no tenés que ver ningún importe** ni destino del costo. Confirmá. Como **Contador**: asiento nuevo **Debe Gastos de Producción / Haber Insumos en Stock por $ 10,00**, origen «Consumo · Aplicación: Limpiador, 2 L (dd/mm/aaaa)». *(lo cubre `RegistrarAsientoTests`)*
8. **Aplicación imputada a lotes.** Igual, con **7 kg de «Abono»** y alcance «todo el invernadero»: un solo asiento **Debe Productos en Proceso / Haber Insumos en Stock por $ 28,00**, aunque el costo se reparta entre dos lotes. Repetila con un sector donde **no hay plantas** (por ejemplo «Crecimiento 2» solo): el asiento pasa a ser **Gastos de Producción**, porque el consumo quedó sin lotes entre los que repartirse. *(lo cubre `test_post_f_sin_lotes_de_plantas…`)*
9. **Fuera de servicio (PROD-PNR-FDS).** Como **Agrónomo**: «Producción › Poner fuera de servicio» sobre «Crecimiento 1» con plantas del primer lote: **reubicá 20 plantas** a «Crecimiento 2» y dejá el resto sin reubicar, causa «Plaga», motivo «Rotura del canal». Resumen y confirmar. En el libro: **un asiento por la merma de las plantas sin reubicar** (Debe Pérdidas por Mermas / Haber Productos en Proceso, con el costo proporcional) y **ninguno por la reubicación**; si el sector tiene dos lotes con plantas sin reubicar, un asiento por cada uno. Cancelar la orden de siembra pendiente que haya en el sector **no** genera asiento. *(lo cubre `AsientosDeLasMermasTests`)*
10. **Importe cero.** Con un insumo de precio $ 0,01, aplicá 0,4 kg: la aplicación se registra y **no aparece ningún asiento** nuevo (el consumo vale $ 0,00). *(lo cubre `test_post_f_un_consumo_de_cero_pesos…`)*
11. **El libro y la ficha.** Como **Contador**: «Libro de gestión» con «Totales (N asientos)» y Debe = Haber; filtrá por cuenta «Pérdidas por Mermas»; abrí la ficha de un asiento de cada tipo (siembra, merma, aplicación, fuera de servicio): cuentas, importe, fecha y origen; **ninguno de los orígenes es un enlace**. Entrá a «Plan de cuentas»: las cuentas 1.1.04, 1.1.05, 5.1.02 y 5.1.03 tienen movimientos. Como **Gerente**: el libro se ve igual.
12. **Auditoría.** Como **Gerente**: «Auditoría». Para la concreción de la siembra tiene que haber un registro «Concreción de siembra» que nombra los consumos y los asientos, y registros aparte de «alta de asiento contable» y «alta de movimiento contable» (los hace Contabilidad; no se repiten). Lo mismo para la merma, la transición, la aplicación y el fuera de servicio. *(lo cubre `test_post_o_…`, `test_post_m_…` y `test_post_i_…`)*
13. **Roles.** Entrá como **Capataz**, como **Agrónomo** y como **Vendedor** y escribí a mano `http://localhost:8000/contabilidad/`: tiene que dar **403** (solo entran el Contador y el Gerente). *(lo cubre el recorrido y `test_libro_vistas.py`)*
14. **Todo o nada.** Lo cubre una prueba (`test_garantia_si_falla_el_segundo_asiento…`, una por caso de uso): no se puede forzar a mano un fallo del asiento.
15. **La fecha del hecho en un ejercicio cerrado (D-102).** Lo cubren las pruebas y el recorrido (`test_d102_…`): para verlo a mano habría que cerrar un ejercicio de verdad y no vale la pena. Si querés, igual: con un ejercicio cerrado que contenga la fecha efectiva, concretá una siembra con esa fecha: el asiento va al ejercicio abierto con la fecha de hoy y la ficha dice «Fecha del hecho: dd/mm/aaaa (el ejercicio de esa fecha ya está cerrado); se registra con la fecha de hoy.».
16. **Navegador real.** Estas pantallas envían formularios que el cliente de Django no ve en un navegador (CSRF, encabezado `Origin`, HTMX). Abrí **una ventana privada**, iniciá sesión como **Capataz** y **enviá hasta el final** «Concretar» (siembra), «Registrar merma» y «Registrar aplicación»; después, como **Agrónomo**, «Poner fuera de servicio». En cada una, tocá «Ver resumen» y después «Confirmar» y volvé a abrir la pantalla: tiene que mostrar el resultado esperado. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver.
17. *(Opcional)* **Sin JavaScript** (desactivalo en el navegador) en «Concretar» y en «Registrar merma»: los dos pasos (resumen y confirmar) tienen que funcionar con envíos comunes. *(Opcional)* **En el celular**, la bandeja del Capataz y una concreción.

## Cierre

**Qué se hizo.**
- **El asiento de cinco casos de uso de producción** (D-92 puntos 2 a 6 y 9, D-86), con `registrar_asiento_automatico` dentro de la transacción de cada servicio, **después de todos sus bloqueos** (el ejercicio es lo último que se bloquea):
  | Caso de uso | Dónde | Asiento |
  |---|---|---|
  | PROD-CNC-SMB | `siembras._registrar_concrecion` | uno por consumo: Debe Productos en Proceso / Haber Insumos en Stock por `monto_consumo`, con la fecha efectiva |
  | PROD-CNC-TRN | `transiciones._escribir_concrecion` | el de la merma de las plantas sin trasladar, con la fecha efectiva (sin merma, nada) |
  | PROD-REG-MRM | `mermas._escribir` | el de la merma: Debe Pérdidas por Mermas / Haber Productos en Proceso por `ResultadoMerma.costo`, fecha de hoy |
  | PROD-REG-APL | `aplicaciones._escribir` | uno por consumo (no por imputación): Productos en Proceso si se imputó a lotes, Gastos de Producción si quedó sin imputaciones |
  | PROD-PNR-FDS | `sectores_fuera_de_servicio._escribir` | uno por cada merma de las plantas sin reubicar, con la fecha efectiva; la reubicación y la cancelación de órdenes no asientan |
- **Archivo nuevo `produccion/servicios/asientos_de_produccion.py`**: `asentar_consumo`, `asentar_merma` y el texto de origen. `aplicar_merma` no cambia (D-92, «alternativas»). Importe cero: sin asiento y sin error (H11); importes con `redondear_monto` (`ROUND_HALF_UP`).
- **Auditoría:** cada asiento entra en los `afectados` del único registro del caso de uso y en `datos` (`asientos`, en lista; `asiento`, en singular, en la merma y la transición). Los registros del asiento y de sus movimientos los hace `contabilidad`.
- **Texto de origen en el libro** (`produccion/apps.py` registra `enlace_de_origen("bitacora", …)`): «Consumo · …» y «Merma del lote L-n · …», **sin dirección**.
- **Defecto previo corregido (aprobado por vos):** `registrar_merma` y `concretar_transicion` agregaban `costo_acumulado` a la auditoría aunque no cambiara (lote con costo $ 0,00, que PRD-05 permite) y la auditoría lo rechaza (D-36). Ahora solo se registra si cambió. Sin esto, la merma de un lote sin costo, que D-92 punto 5 manda aceptar, fallaba entera.
- Sin modelos, sin migraciones (`makemigrations --check`: sin cambios), sin dependencias nuevas, y sin tocar `contabilidad/cuentas.py` (las descripciones de 1.1.04, 1.1.05, 5.1.02 y 5.1.03 coinciden con `plan_de_cuentas.md`).

**Diferencias con la documentación** (anotadas en `docs/temas_abiertos.md`):
1. **Paso 5 («Resúmenes») sin pantallas:** ningún extracto muestra el asiento en un resumen ni en una ficha, y el Capataz no ve valores. No hay bloque «Asiento contable» (decidido con vos el 25/11/2026).
2. **«Con su enlace al origen»:** no se puede. El origen de los cinco asientos es una fila de bitácora y las pantallas de producción (ficha de la orden, bitácora) no las abre el Contador (404; D-30 no admite un enlace que lleve a un error). La ficha muestra un **texto descriptivo sin enlace**.
3. **Las marcas «Fuera de la ronda (D-45)» de los cinco extractos** (precondiciones c y d, postcondiciones del asiento, la sección «Cómo se aplica en la ronda» y los encabezados de código) quedan falsas. «Permitido» solo deja tocar `cuentas.py` fuera de la app, así que se actualizaron en el M3 (con tu visto bueno).
4. **`DESCRIPCION_DE_CUENTA`:** «Productos en Proceso» dice que las **transiciones** la mueven (Debe), pero la transición no asienta por sí misma (solo su merma); y «Gastos de Producción» sigue figurando como «propuesta (MD-90)» en el extracto de la aplicación, aunque el plan de cuentas aprobado la incluye. Coinciden con `plan_de_cuentas.md`, así que no se tocaron.
5. **La cuenta de gasto se decide por el resultado, no por la categoría:** un insumo «como costo de los lotes» sin lotes de plantas en el alcance (extensión 10c) asienta a **Gastos de Producción**, igual que uno «como gasto».
6. **Descripción del asiento:** la documentación no dice qué texto lleva; se usó la `descripcion_evento` del consumo o de la merma.
7. **Fecha del asiento de la merma:** es la de la merma (hoy) en PROD-REG-MRM y la **efectiva** en la transición y en el fuera de servicio (D-92 punto 4).
8. **Estas pruebas existentes cambiaron** (sin debilitarlas; solo porque el servicio ahora asienta): `Base` de seis archivos de pruebas de `produccion` suma `PlanDeCuentasMixin`; el `armar` de cinco archivos de concurrencia de `produccion` y el de `comercial/tests/test_stock_maduro_concurrencia.py` cargan el plan; `test_prod_reg_lte_concurrencia.py` cuenta 1 y 2 asientos en lugar de 0 y 1 (la siembra normal que concreta ahora asienta su consumo); y `test_post_j_ninguna_otra_accion_de_auditoria…` (fuera de servicio) ahora admite los registros de ejercicio, asiento y movimiento que hace `contabilidad`.
9. **Una prueba de `comercial` tocada, con tu permiso del 25/11/2026** (fuera de «Permitido fuera de la app»): `comercial/tests/test_stock_maduro_concurrencia.py` armaba su escenario sin el plan de cuentas y llama a `registrar_merma`, que ahora asienta; fallaban dos pruebas. Se agregó `asegurar_plan_de_cuentas()` en su `armar` (y el `import`). No cambia lo que verifican.
10. **Cosecha, entrega y cámara** (CON-04c) llaman a `aplicar_merma` y no asientan todavía: sigue pendiente, es de esa tarea.

**Pantallas: lo que se corrigió del prototipo (D-61).** Ninguna: la tarea no tiene pantallas nuevas.

**Pruebas (M1).**
- `python manage.py test produccion contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **1622 pruebas, OK**.
- `python manage.py test produccion --keepdb --tag concurrencia` → **69 pruebas, OK** (en serie).
- Además, en serie: `produccion contabilidad` sin concurrencia → **1620, OK** (antes del recorrido); `comercial` sin concurrencia, con `--parallel` → **2527, OK**; `comercial --tag concurrencia` → **124 pruebas, OK** (después del arreglo de la diferencia 9).
- 69 pruebas nuevas: 45 de servicio (siembra 9, merma 9, transición 7, aplicación 10, fuera de servicio 10), 20 de concurrencia (5, 4, 3, 4 y 4), 2 del texto de origen (`test_extensiones.py`) y 2 del recorrido.
- **Las pruebas de cada paso se escribieron primero y se mostró que fallaban** (siembra 7 de 8 de servicio y 5 de concurrencia; merma y transición 19 de 22; aplicación 12; fuera de servicio 9) antes de implementar, y las revisaste antes de cada servicio. Al implementar, varios defectos eran de las pruebas y no del servicio (orden de las líneas del asiento, un tipo de insumo compartido entre dos invernaderos que los serializaba por el bloqueo del `TipoInsumo`, y un ejercicio previo que faltaba para fechar un asiento en el pasado).

**Decisiones.** Ninguna nueva (D-92, D-86, D-102 y D-36).

**Datos de la base de desarrollo.** No se tocó tu base de desarrollo: no se corrió `migrate`, ni `runserver`, ni nada contra ella. Las pruebas usaron bases `test_…`.

### Informe

**Verifiqué:**
- El recorrido `RecorridoDeAsientosDeProduccionTests` (2 pruebas, por rol y por estado): sin ejercicio → el Capataz concreta una siembra («Ver resumen» no asienta; «Confirmar» crea el asiento N.º 1 y abre el primer ejercicio) → concreta la transición con 10 plantas perdidas ($ 20,00) → registra una merma ($ 8,00) → registra una aplicación a gasto ($ 10,00, sin ver importes) → el Agrónomo pone fuera de servicio el sector ($ 72,00) → los cinco asientos con sus cuentas, importes y números 1 a 5 → el Capataz, el Agrónomo y el Vendedor reciben 403 en el libro; el Contador y el Gerente lo ven → la ficha de cada asiento muestra su origen sin enlace. Y el estado «la fecha del hecho cae en un ejercicio cerrado»: el asiento va al abierto con la aclaración.
- Migraciones: no hay (no se crearon modelos ni migraciones; `makemigrations --check`: «No changes detected»).
- Concurrencia de cada caso de uso: contra el cierre del ejercicio en cierre (los dos órdenes), numeración sin huecos y el ejercicio como último bloqueo.

**Lo cubre una prueba:** cada paso de la «Verificación a mano» dice cuál (`test_prod_cnc_smb.py`, `test_prod_cnc_trn.py`, `test_prod_reg_mrm.py`, `test_prod_reg_apl.py`, `test_prod_pnr_fds.py`, las cinco `*_concurrencia.py`, `test_extensiones.py` y `test_recorrido_asientos_de_produccion.py`).

**No pude verificar:**
- Todo lo que se ve en tu navegador y en tu base de desarrollo (pasos 1 a 17): no abro navegador ni toco esa base.
- **El paso de «navegador real» (paso 16):** el token CSRF, el encabezado `Origin` y el JavaScript de los formularios de concreción, merma, aplicación y fuera de servicio.
- Que el `--parallel` pase **antes de que existiera el plan de cuentas en cada clon**: la primera corrida paralela falló porque seis clases de pruebas de `produccion` no cargaban el plan (en serie pasaba porque otra clase lo dejaba cargado); quedó corregido y el comando de la tarea pasa completo.
- El registro en la pantalla «Auditoría» (paso 12), que solo se ve en el navegador.
