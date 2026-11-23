# CON-04c · Asientos de cosecha, cámara y entregas (comercial con stock)

Estado: pendiente | App: comercial (y produccion donde vive el núcleo de la cosecha, D-64) | Rama: feature/con-04c-asientos-comercial-stock | Ronda: Contabilidad 2

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

1. Concretá una cosecha y una entrega de un suministro: en el libro, el asiento de la cosecha y el compuesto de la entrega, con sus enlaces.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`; en `docs/disparadores.md`, tachá «Comercial 1 (COM-04, D-64)» de «Cuando exista
contabilidad con asientos».
