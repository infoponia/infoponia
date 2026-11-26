# CON-04c · Asientos de cosecha, cámara y entregas (comercial con stock)

Estado: hecha (pendiente de PR) | App: comercial (y produccion donde vive el núcleo de la cosecha, D-64) | Rama: feature/con-04c-asientos-comercial-stock | Ronda: Contabilidad 2

Depende de: **CON-02** y de las tareas de Comercial que programan cada caso de uso de la tabla (COM-04a, COM-04b, COM-06a). **Leé D-92 punto 9:** si
CON-02 ya estaba en `main` cuando se programó una de esas tareas, su fila ya está hecha (la marca su «Cierre»); acá hacés solo las filas que
falten. Si ninguna falta, la tarea se cierra sin código.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Lo que mueve producto valorizado (cosechar, vencer o perder en cámara, entregar, consumir envases en la entrega) genera su
asiento. Todo lo que hace falta ya lo guardan esos casos de uso (D-45, D-57, D-64): no hay migraciones.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Asiento (origen · Debe / Haber · monto) | Lo programa |
|---|---|---|---|---|
| PROD-CNC-CSC | Concretar Cosecha (post. f) | docs/casos_de_uso/produccion/cosecha.md | Cada `MovimientoStock` «salida por cosecha» · Productos Terminados / Productos en Proceso · su costo | COM-04a o esta tarea |
| PROD-REG-MRM (cámara, post. i) | Merma de una partida en cámara | docs/casos_de_uso/produccion/merma.md | La `Merma` · Pérdidas por Mermas / Productos Terminados · cantidad × costo unitario de la partida | COM-04b o esta tarea |
| PROD-VNC-CAM | Vencer Partidas en Cámara (post. b; paso diario) | docs/casos_de_uso/produccion/camara.md | Cada `Merma` por vencimiento · Pérdidas por Mermas / Productos Terminados · cantidad × costo unitario | COM-04b o esta tarea |
| COM-CNC-ENT | Concretar Entrega (post. e, g y h) | docs/casos_de_uso/comercial/rutas.md | (e) cada merma «daño en la entrega» · Pérdidas por Mermas / Productos Terminados; (g) cada `Consumo` de envase · Costo de Producción Vendida / Insumos en Stock; (h) la entrega, **un asiento compuesto** · Deudores por Ventas / Ventas por el monto total y Costo de Producción Vendida / Productos Terminados por el costo de lo entregado | COM-06a o esta tarea |

Fecha de cada asiento: la del hecho (D-92 punto 4): la de la cosecha, la de la merma, la del paso diario, la de resolución de la entrega. En el
paso diario el actor es `None` (InfoPonia).

## Leer

- Casos de uso: de cada extracto, la postcondición del asiento, su regla «Asiento» y la sección «Fuera de esta ronda · contabilidad (D-57)».
- Decisiones: D-92, D-86, D-64 (cosecha y cámara en el código), D-66 y D-68 (entregas), D-57, D-45, D-44.
- API: docs/api/asientos.md.
- Patrones: docs/patrones/asientos.md, docs/patrones/stock_maduro.md, docs/patrones/bloqueos.md («`comercial`» y «Contabilidad»).
- Reglas: .claude/rules/pruebas.md.
- Código a leer: los servicios que la «Cómo se aplica» de cada extracto nombra, sus pruebas y las de concurrencia; `contabilidad/servicios/asientos.py`.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: `produccion/servicios/` del núcleo de cosecha y cámara (D-64: vive en produccion); al cerrar, M3 y `docs/disparadores.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: lo que mueve dinero sin stock (CON-04d).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Cosecha.** — pruebas: las de PROD-CNC-CSC (un asiento por movimiento) y su concurrencia contra el cierre del ejercicio.
2. **Cámara:** merma y vencimiento. — pruebas: las de PROD-REG-MRM en cámara y PROD-VNC-CAM (el paso diario corrido dos veces no duplica asientos).
3. **Entrega:** mermas, consumos de envase y el asiento compuesto (sin venta ni cobro → sin asiento, post. h). — pruebas: las de COM-CNC-ENT,
   incluida una entrega de compra-venta con un detalle rechazado.
4. **Resúmenes** que muestran el asiento.

## Hecho cuando

- Cada fila de la tabla asienta lo que dice, una vez por origen; las filas que ya hizo su tarea de Comercial están marcadas en el «Cierre».
- Comando de pruebas: `python manage.py test comercial produccion contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test comercial produccion --keepdb --tag concurrencia`.

## Verificación a mano

Para la persona que revisa. No hace falta haber visto la sesión ni el código. **Ninguna base se cargó ni se tocó**: los datos los creás vos. Esta tarea tiene **formularios que se envían** (concretar cosecha, registrar merma, concretar entrega): por eso el paso 14 es de «navegador real».

**Antes de empezar**

- No hay migración nueva: alcanza con tener la base local al día (`python manage.py migrate`) y levantar el servidor (`python manage.py runserver`, `http://localhost:8000`). La contraseña de las cuentas va por tu variable o por prompt; no la escribas en ningún archivo.
- Cuentas necesarias (Gerente › «Cuentas»): un **Agrónomo**, un **Capataz**, un **Vendedor**, un **Transportista** (con un vehículo activo de 800 kg, asignado al invernadero desde su ficha › «Logística») y un **Contador**. Dejá al **Gerente** como está.
- Crear a mano, en este orden y con estos valores:
  1. **Invernadero «Invernadero Norte»** con el Agrónomo a cargo, el Capataz asignado y el Vendedor.
  2. Un **sector de Maduración** con 200 agujeros, una variedad **«Lechuga Crespa»** y un **lote en Maduración de 100 plantas con costo total $ 200,00** (2,00 por planta: por ejemplo, sembrá 100 plantines con una semilla de precio de referencia $ 2,00 y llevalo a Maduración). Así cada planta cuesta $ 2,00 y los importes de abajo son fáciles de controlar.
  3. Un **cliente con correo** y una dirección activa («Panadería Sol», CUIT `30-71234567-8`).
  4. Un insumo **«Bandeja PET»** de la categoría «Envases», habilitado en el invernadero con **precio $ 3,00** y 30 unidades (solo para el paso 8).
  5. No hay que poner en marcha la contabilidad: el primer ejercicio se abre solo con el primer asiento (D-84 punto 3).

**Pasos** (los marcados «lo cubre…» ya los prueba el CI; si tenés poco tiempo, concentrate en los demás)

1. **El libro, vacío.** Entrá como **Contador** › «Contabilidad › Libro de gestión»: no tiene que haber asientos. *(lo cubre `RecorridoDeAsientosComercialesTests`)*
2. **Cosecha con contrato (PROD-CNC-CSC post. f).** Como **Agrónomo**: «Producción › Cosechas › Planificar cosecha», invernadero Norte, con contrato (una compra-venta con envío de 50 plantas de Lechuga Crespa para dentro de 10 días), **40 plantas** del lote. Como **Capataz**: «Bandeja» › la cosecha › «Concretar». Cosechá **30** y declarás **4 plantas perdidas** por «Plaga» (aparece el campo «Causa»). Tocá **«Ver resumen»** (todavía **no** hay asientos: miralo con el Contador) y después **«Confirmar»**. Como **Contador**, en el libro tiene que haber **dos asientos nuevos**: el **N.º 1**, con la fecha de hoy, **Debe Productos Terminados / Haber Productos en Proceso $ 60,00** (30 × $ 2,00) y el **N.º 2**, **Debe Pérdidas por Mermas / Haber Productos en Proceso $ 8,00** (el lote queda con 70 plantas y $ 140,00: 140 × 4 ÷ 70). *(lo cubren `ConcretarCosechaAsientoTests` y el recorrido)*
3. **Cosecha sin contrato.** Planificá y concretá otra cosecha de **20 plantas** sin contrato: asiento nuevo **Debe Productos Terminados / Haber Productos en Proceso $ 40,00**, y las 20 plantas pasan a la cámara. Una cosecha que rinde **0** plantas (concretala con 0) **no** genera asiento y no da error. *(lo cubre `test_post_f_un_lote_que_rindio_cero…`)*
4. **Merma en cámara (PROD-REG-MRM post. i).** Como **Agrónomo**: «Producción › Registrar merma › Pérdida en cámara», la partida del paso 3, **5 plantas**, causa «Daño en cámara». Resumen y confirmar. Asiento nuevo **Debe Pérdidas por Mermas / Haber Productos Terminados $ 10,00** (5 × $ 2,00, el costo de la partida). *(lo cubre `RegistrarMermaEnCamaraAsientoTests`)*
5. **Entrega de un suministro (COM-CNC-ENT e y h).** Registrá un suministro (Lechuga Crespa, 100 plantas por período, cantidad mínima 100, plazo de pago 15 días, **precio $ 100,00**, primera entrega hoy) y esperá su entrega para hoy con el Transportista (o asignala desde «Asignar transportista»). Como **Transportista**: «Mi ruta › Iniciar ruta» y «Concretar»: «Llegaron» **95**, «Recibió el cliente» **95**, «No se usaron envases». Resumen y «Confirmar entrega». En el libro, **dos asientos nuevos**: la merma «daño en la entrega» (**Debe Pérdidas por Mermas / Haber Productos Terminados $ 10,00**, 5 × $ 2,00) y **un solo asiento compuesto de la entrega**: **Debe Deudores por Ventas $ 9.500,00 / Haber Ventas $ 9.500,00** y **Debe Costo de Producción Vendida $ 190,00 / Haber Productos Terminados $ 190,00** (95 × $ 2,00). *(lo cubren `test_post_h_suministro…`, `test_post_e_…` y el recorrido)*
6. **Retiro de una compra-venta, cobrado en efectivo.** Registrá una compra-venta con **retiro** en el invernadero (hoy, 20 plantas a $ 100,00). Como **Vendedor**: «Comercial › Entregas › Concretar retiro», «Llegaron» 20, «Acepta», «Efectivo», sin envases. Un asiento compuesto: **Debe Caja $ 2.000,00 / Haber Ventas $ 2.000,00** y **Debe Costo de Producción Vendida $ 40,00 / Haber Productos Terminados $ 40,00**. Repetilo con **transferencia**: el Debe pasa a **Banco c/c**. *(lo cubre `test_regla_venta_registrada_por_entrega_una_sola_entrega_cobra_con_caja…`)*
7. **Una compra-venta en dos entregas.** *(Difícil de armar a mano: la cubre una prueba.)* La primera registra la venta contra **Deudores por Ventas**; la última cobra el total con **Caja o Banco**, acredita Ventas por lo suyo y **cancela lo acumulado en Deudores**; si la primera se concretó antes de esta tarea (sin asiento), esa parte va a Ventas y Deudores no queda con saldo contrario. *(lo cubren `test_regla_venta_registrada_por_entrega_la_no_ultima…` y `…transicion…`)*
8. **Envases con exceso (COM-CNC-ENT g).** En otra entrega con envasado planificado de 10 bandejas, escribí **12 utilizadas** y confirmá el exceso: asiento nuevo **Debe Costo de Producción Vendida / Haber Insumos en Stock $ 36,00** (12 × $ 3,00, el exceso incluido), además del asiento de la entrega. Lo **devuelto** no genera asiento. *(lo cubre `test_post_g_…`)*
9. **Entrega rechazada, sin venta.** Con una compra-venta cuyo cliente **rechaza** todo lo que llegó (no tilda «Acepta»): la venta queda cancelada y **no** hay asiento de la entrega ni de cobro. *(lo cubre `test_post_h_si_no_hubo_venta_ni_cobro…`)*
10. **Vencimiento en cámara (paso diario).** *(Opcional, lo cubren las pruebas.)* Para verlo a mano hay que tener una partida con la fecha límite vencida y correr `python manage.py proceso_diario`: aparece **Debe Pérdidas por Mermas / Haber Productos Terminados** por cantidad × costo de la partida, y correr el paso **dos veces** no duplica el asiento. También lo cubre la devolución de una entrega a una partida **ya vencida**. *(lo cubren `ProdVncCamAsientoTests` y `test_regla_8_6_29_…`)*
11. **El libro y la ficha.** Como **Contador**: «Libro de gestión» con «Totales (N asientos)» y Debe = Haber; filtrá por cuenta «Productos Terminados» y «Deudores por Ventas»; abrí la ficha de un asiento de cada tipo: **el origen es un texto sin enlace** («Salida por cosecha · OT-…, lote L-…, 30 plantas», «Merma del lote L-…», «Entrega OT-… · CV-…, Panadería Sol»). Como **Gerente**: se ve igual.
12. **Roles.** Entrá como **Capataz**, **Agrónomo**, **Vendedor** y **Transportista** y escribí a mano `http://localhost:8000/contabilidad/`: tiene que dar **403** (solo entran el Contador y el Gerente). *(lo cubre el recorrido)*
13. **Auditoría.** Como **Gerente** › «Auditoría»: el registro «Concreción de cosecha» (y «Concreción de entrega», «Registro de merma») nombra los asientos creados, y aparecen registros aparte de «alta de asiento contable» y «alta de movimiento contable» (los hace Contabilidad). *(lo cubren `test_post_r_…` y `test_post_q_…`)*
14. **Navegador real.** Abrí **una ventana privada**, entrá como **Capataz** y **enviá hasta el final** «Concretar» una cosecha; después, como **Transportista**, «Concretar» una entrega; y como **Agrónomo**, «Registrar merma en cámara». En cada una tocá «Ver resumen» y «Confirmar» y volvé a abrir la pantalla: tiene que mostrar el resultado esperado y el asiento tiene que estar en el libro. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver.
15. *(Opcional)* **Sin JavaScript** (desactivalo) en «Concretar» cosecha y entrega: los dos pasos (resumen y confirmar) funcionan con envíos comunes. *(Opcional)* **En el celular**, la bandeja del Capataz y «Mi ruta».
16. **Todo o nada y la fecha del hecho en un ejercicio cerrado (D-102).** No se pueden forzar a mano: los cubren las pruebas (`test_garantia_si_falla_el_asiento…`, `test_d102_…`).

## Cierre

### Qué se hizo

**Ninguna de las cuatro filas estaba hecha** (COM-04a, COM-04b y COM-06a se mergearon con «Fuera de esta ronda · contabilidad»; el código no llamaba a `registrar_asiento_automatico`): se hicieron las cuatro. Sin modelos, sin migraciones, sin dependencias.

| Fila | Dónde | Asiento |
|---|---|---|
| PROD-CNC-CSC (f) | `cosechas.concretar_cosecha` | uno por `MovimientoStock` «salida por cosecha»: Debe Productos Terminados / Haber Productos en Proceso por `cantidad × costo_unitario`, fecha efectiva |
| PROD-CNC-CSC (ext. 10a) | `cosechas.concretar_cosecha` | uno por merma de lote (reutiliza `asientos_de_produccion.asentar_merma`), fecha de hoy |
| PROD-REG-MRM cámara (i) | `merma_camara._registrar` | Debe Pérdidas por Mermas / Haber Productos Terminados por cantidad × costo de la partida |
| PROD-VNC-CAM (b) | `camara._vencer_en_transaccion` | igual, actor `None`; corrido dos veces no duplica |
| COM-CNC-ENT (e, g, h) | `concrecion._registrar` | mermas «daño en la entrega» (Σ perdida × costo de cada origen) y de lo devuelto a una partida vencida; un asiento por consumo de envase; un compuesto por entrega (suministro: Deudores / Ventas; compra-venta: ver «Decisiones»; siempre Costo de Producción Vendida / Productos Terminados) |

- **Archivo nuevo `comercial/servicios/asientos_comerciales.py`** con las funciones de asiento y los dos textos de origen. El asiento va **después de todos los bloqueos de negocio** (el ejercicio se bloquea al final, D-86) y los asientos entran en los `afectados` y en `datos["asientos"]` del único registro de auditoría de cada caso de uso.
- **Texto de origen en el libro** (`comercial/apps.py`: `movimiento_de_stock` y `orden_de_trabajo`): **sin dirección** (el Contador no abre esas pantallas y D-30 prohíbe un enlace que lleve a un error; mismo criterio que CON-04a).
- **Pruebas existentes que cambiaron** (sin debilitarlas, porque el servicio ahora asienta): las `Base` de `test_prod_cnc_csc`, `test_prod_reg_mrm_camara`, `test_prod_vnc_cam` y `test_com_cnc_ent` suman `PlanDeCuentasMixin`; los `armar` de `test_cosechas_concurrencia`, `test_camara_concurrencia` y `test_concrecion_concurrencia` cargan el plan; `test_post_p_q_y_r…` cuenta solo los registros `concrecion_cosecha` (ahora `contabilidad` suma los suyos) y `test_post_h_no_hay_asientos_contables` se reemplazó por las pruebas de los asientos.

**Decisiones del estudiante del 26/11/2026** (se registran en `docs/temas_abiertos.md`):
1. La merma de un lote en pie dentro de la cosecha (ext. 10a) **se asienta acá**, reutilizando `asentar_merma` (la tabla de la tarea no la nombraba; CON-04a, diferencia 10).
2. Lo devuelto a una partida **ya vencida** en la entrega (regla 29 de 8.6) **asienta como un vencimiento**: Debe Pérdidas por Mermas / Haber Productos Terminados (COM-CNC-ENT no lo decía).
3. En la entrega de una **compra-venta** se sigue la regla «Venta registrada por entrega» de COM-CNC-ENT y **no la fila (h) de la tarea**: las no últimas debitan Deudores por Ventas / Haber Ventas; la última cobra con Caja (efectivo) o Banco c/c y cancela lo acumulado en Deudores; siempre se suma el asiento de Costo de Producción Vendida / Productos Terminados.
4. **Transición** (D-92 punto 1, sin asientos hacia atrás): para compra-ventas con entregas anteriores sin asiento, el Haber a Deudores es solo por las que sí tienen asiento y el resto se reconoce en Ventas en la entrega final, para que Deudores nunca quede con saldo contrario.

**Diferencias con la documentación** (para `docs/temas_abiertos.md`): ver el punto 3 (fila (h) de la tarea vs. el caso de uso) y además: (a) «Resúmenes» (paso 4 de la tarea): ningún extracto muestra el asiento en un resumen y el resumen de `cncent` del prototipo es «Solo prototipo», así que no hay pantallas nuevas; (b) «con sus enlaces» de la «Verificación a mano» original: no se puede (el origen es un texto sin dirección, D-30); (c) el cosecha asienta por **movimiento** (D-92 punto 6) y con el costo del movimiento (D-92 punto 5), no «cantidad cosechada × costo del lote» recalculado; (d) las marcas «Fuera de esta ronda · contabilidad» de `cosecha.md`, `camara.md`, `merma.md` y `rutas.md` quedan falsas (se actualizan en el M3).

**Pantallas: lo que se corrigió del prototipo (D-61).** Ninguna: la tarea no tiene pantallas nuevas.

**Datos de la base de desarrollo.** No se tocó tu base de desarrollo: no se corrió `migrate`, ni `runserver`, ni nada contra ella. Las pruebas usaron bases `test_…`. No se borró nada.

**Decisiones.** Ninguna nueva (D-92, D-86, D-102, D-64, D-68, D-36).

### Pruebas (M1)

- `python manage.py test comercial produccion contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **4628 pruebas, OK** (incluye `estadisticas`, ya integrada con `main`: la PR #99 está mergeada).
- `python manage.py test comercial produccion --keepdb --tag concurrencia` → **223 pruebas, OK** (en serie).
- `makemigrations --check`: sin cambios.
- 54 pruebas nuevas de servicio (cosecha 12, merma en cámara 6, vencimiento 8, entrega 16 más las del texto de origen), 12 de concurrencia (cosecha 4, cámara 4, entrega 4) y 2 del recorrido.
- **Las pruebas de cada paso se escribieron primero y se mostró que fallaban** (cosecha 9 de 11, cámara 11 de 14, entrega 14 de 15; las verdes son los controles de «sin asiento») antes de implementar, y las revisaste antes de cada servicio.

### Informe

**Verifiqué:**
- El recorrido `RecorridoDeAsientosComercialesTests` (2 pruebas, por rol y por estado): sin ejercicio → el Capataz concreta una cosecha con 4 plantas perdidas («Ver resumen» no asienta) → el Transportista concreta un suministro con pérdida (merma y compuesto con Deudores) → el Vendedor concreta un retiro en efectivo (Caja) → el paso diario vence una partida y, corrido dos veces, no duplica → el Capataz, el Agrónomo, el Vendedor y el Transportista reciben 403 en el libro; el Contador y el Gerente lo ven → la ficha de cada asiento muestra su origen sin enlace. Y el estado «la fecha del hecho cae en un ejercicio cerrado» (D-102).
- Migraciones: no hay (`makemigrations --check`: «No changes detected»).
- Concurrencia de cada caso de uso contra el cierre del ejercicio (los dos órdenes), numeración sin huecos y el ejercicio como último bloqueo.

**Lo cubre una prueba:** cada paso de la «Verificación a mano» dice cuál.

**No pude verificar:**
- Todo lo que se ve en tu navegador y en tu base de desarrollo (pasos 1 a 15): no abro navegador ni toco esa base.
- **El paso de «navegador real» (paso 14):** CSRF, `Origin` y JavaScript de los formularios de concretar cosecha, entrega y merma en cámara.
- El vencimiento por el paso diario y la compra-venta en dos entregas **a mano**: dependen de fechas y de planificación que las pruebas arman directo.
- El registro en la pantalla «Auditoría» (paso 13), que solo se ve en el navegador.
