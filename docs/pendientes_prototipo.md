# Pendientes del prototipo (lo que el prototipo trae y el sistema no implementa)

Cada entrada dice qué tiene el prototipo, por qué no se implementó y dónde queda anotado. Si una entrada se decide hacer, pasa a una decisión nueva (`docs/decisiones/`) y se saca de acá. El prototipo es una referencia, no una especificación (D-61).

## Compras y contabilidad

- **Número de comprobante del pago** (`VIEWS.c_pag`, campo «Número de comprobante», opcional: «Número de transferencia, recibo o ticket»). No se implementó en CMP-05: el modelo `Pago`, D-91 punto 1 y el caso de uso CMP-REG-PAG («No hay comprobante ni número de operación en el modelo») no lo tienen. **Mejora futura:** necesita una columna en `Pago` y una decisión nueva.
