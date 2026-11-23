# CON-04d · Asientos de cobros, indemnizaciones y multas (comercial con dinero)

Estado: pendiente | App: comercial | Rama: feature/con-04d-asientos-comercial-dinero | Ronda: Contabilidad 2

Depende de: **CON-02**, **USR-11** y de las tareas de Comercial que programan cada caso de uso (COM-06b, COM-07a, COM-07b, COM-08a, COM-08b). **D-92 punto
9:** si CON-02 ya estaba en `main` cuando se programó una de ellas, su fila ya está hecha; acá van solo las que falten.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Lo que mueve dinero en comercial sin mover stock: el cobro de un suministro y su anulación, el cobro al cancelar una
compra-venta, las indemnizaciones de las solicitudes de revisión y su anulación, la multa por resolución del suministro. Y el aviso «corregir con asiento manual» de una entrega no
reconocida pasa del Vendedor al **responsable contable** (H12).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Asiento (origen · Debe / Haber · monto) | Lo programa |
|---|---|---|---|---|
| COM-REG-CBR | Registrar Cobro (post. d) | docs/casos_de_uso/comercial/cobranza.md | El `PagoCliente`, **un asiento compuesto** · Debe Caja (efectivo) o Banco c/c (los demás medios) por `monto_pagado` / Haber Deudores por Ventas por Σ `LineaPago.monto_cobrado` y Haber Indemnizaciones por Atraso en el Pago por Σ `indemnizacion_atraso`, si es mayor que 0 · fecha del cobro | COM-08a o esta tarea |
| COM-ANL-CBR | Anular Cobro (post. c) | docs/casos_de_uso/comercial/cobranza.md | La `Anulacion` · el contraasiento del cobro completo (incluida la indemnización por atraso), invertido, fecha actual | COM-08b o esta tarea |
| COM-CNL-CVT | Cancelar Compra-venta (post. f, ext. 6a) | docs/casos_de_uso/comercial/compra_venta.md («La extensión 6a (COM-08b)») | El `PagoCliente` de compra-venta · Caja o Banco c/c (según el medio) / Deudores por Ventas · lo cobrado | COM-08b o esta tarea |
| COM-EVL-DSC | Evaluar Discrepancia (post. e) | docs/casos_de_uso/comercial/solicitudes.md | La `SolicitudRevision` · Indemnizaciones por Incumplimiento a Cliente / Deudores por Ventas (sin pagar) o Caja o Banco c/c (ya pagada, según el medio de reintegro) · la indemnización | COM-07a o esta tarea |
| COM-RSV-QJA | Resolver Queja (post. e) | docs/casos_de_uso/comercial/solicitudes.md | Igual, con el caso compuesto (parte contra Deudores, el resto contra Caja o Banco) · solo si el monto es mayor que 0 | COM-07a o esta tarea |
| COM-ANL-SRV | Anular Resolución de Solicitud (post. c) | docs/casos_de_uso/comercial/solicitudes.md | La `Anulacion` · el contraasiento del de la solicitud (mismas cuentas e importes, invertidos), fecha actual; si el ejercicio del original está cerrado, va al abierto | COM-07a o esta tarea |
| COM-RSV-SUM | Resolver Suministro por Incumplimientos (post. h) | docs/casos_de_uso/comercial/resolucion.md | El `Suministro` (R012) · Indemnizaciones por Resolución de Contratos / **2.1.02 Indemnizaciones a Pagar** · la multa, si es mayor que 0 | COM-07b o esta tarea |
| COM-ATN-ENR | Atender Entrega No Reconocida (post. b) | docs/casos_de_uso/comercial/confirmacion.md | Sin asiento: el aviso «corresponde corregir con un asiento manual» va a `responsable_contable()` (y al Gerente), no al Vendedor | COM-06b o esta tarea |

La cuenta **2.1.02 Indemnizaciones a Pagar** ya la carga CON-02 (D-84 punto 7; la aprobó Ezequiel el 23/11/2026). El pago de la multa no tiene
caso de uso: el Contador lo registra con un asiento manual (Debe Indemnizaciones a Pagar / Haber Caja o Banco c/c; D-92 punto 10).

## Leer

- Casos de uso: de cada extracto, la postcondición del asiento, su regla «Asiento», lo marcado «Fuera de esta ronda · contabilidad» y, en
  `resolucion.md`, los temas abiertos de la multa (quedan resueltos por D-92 punto 10).
- Decisiones: D-92, D-86, D-85 (responsable contable), D-94 (cobranza: `LineaPago`, puntos 2, 3, 10 y 14), D-69 (punto 8), D-67, D-68, D-57, D-44.
- API: docs/api/asientos.md (`registrar_asiento_automatico` y `responsables.notificar_al_responsable_contable`). `contraasentar` es del Contador
  (CON-03b): la anulación usa `registrar_asiento_automatico` con los movimientos del original invertidos y la `Anulacion` como origen.
- Patrones: docs/patrones/asientos.md, docs/patrones/bloqueos.md.
- Reglas: .claude/rules/pruebas.md.
- Código a leer: los servicios que nombra la «Cómo se aplica» de cada extracto, sus pruebas y las de concurrencia.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: `docs/casos_de_uso/comercial/resolucion.md` (cerrar los temas abiertos de la multa citando D-92); al cerrar, M3 y
  `docs/disparadores.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: el cobro de una compra-venta en su última entrega (va dentro del asiento compuesto de la entrega: CON-04c).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Cobros:** el de un suministro (con y sin indemnización por atraso), su anulación y el cobro al cancelar una compra-venta. — pruebas: las de
   COM-REG-CBR, COM-ANL-CBR y COM-CNL-CVT (ext. 6a).
2. **Indemnizaciones** (discrepancia y queja, con el caso compuesto). — pruebas: las de COM-EVL-DSC y COM-RSV-QJA (sin asiento con monto 0).
3. **Anulación** con el contraasiento (también cuando el original quedó en un ejercicio cerrado). — pruebas: las de COM-ANL-SRV.
4. **Multa** del suministro. — pruebas: las de COM-RSV-SUM (multa 0 → sin asiento).
5. **Aviso de COM-ATN-ENR** al responsable contable. — pruebas: las de COM-ATN-ENR (con y sin Contador activo).

## Hecho cuando

- Cada fila asienta lo que dice; el Vendedor ya no recibe el aviso de COM-ATN-ENR y el Contador (o el Gerente sin Contador) sí.
- Comando de pruebas: `python manage.py test comercial contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test comercial --keepdb --tag concurrencia`.

## Verificación a mano

1. Aceptá una discrepancia de una entrega sin pagar: asiento contra Deudores por Ventas. Anulala: el contraasiento aparece en el libro.
2. Resolvé un suministro con multa: la cuenta Indemnizaciones a Pagar queda con saldo acreedor.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`; en `docs/disparadores.md`, tachá «Comercial 1 (COM-07, D-69)» y el disparador «Cuando exista
el rol Contador» (el aviso de COM-ATN-ENR).
