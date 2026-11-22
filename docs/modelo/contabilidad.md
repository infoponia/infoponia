# Modelo de dominio · contabilidad (extracto)

Versión de la ronda «Producción 1». Vive en `contabilidad` (nivel 2, D-37). **En esta ronda existe una sola clase**: `OrigenDocumento` (D-52). `EjercicioContable`, `AsientoContable`, `CuentaContable` y `MovimientoContable` quedan fuera (D-45) y se suman cuando se programe la contabilidad.

## OrigenDocumento

Bloque: Contabilidad. Es el concepto padre de todo lo que, dentro del sistema, genera movimientos y a lo que se corresponden esos movimientos. Para `contabilidad`, es la manera de saber **qué hecho originó cada asiento** (R012). En el modelo de dominio es abstracta: nadie crea un `OrigenDocumento` solo.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `id` | — | El `id` automático. **Compartido** por todos los documentos: no es consecutivo por tipo |
| `tipo` (nuevo) | `OrigenDocumento.Tipo`: `orden_de_trabajo`, `bitacora`, `movimiento_de_insumo`; `contrato` (COM-02, D-59: `comercial.Contrato`) | Discriminador de la herencia. Lo fija la hija directa y nunca cambia. Los tipos de las rondas futuras (contrato, pago, entrega, solicitud de revisión, movimiento de stock) se suman con su clase |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R012 | AsientoContable, «origina» | OrigenDocumento → AsientoContable = 0..1 | **Fuera de la ronda (D-45)**: la declara `contabilidad` cuando exista el asiento |
| R016 | MovimientoInsumo, «se origina» | OrigenDocumento → MovimientoInsumo = 0..*; MovimientoInsumo → OrigenDocumento = 0..1 | Vigente desde D-52: `MovimientoInsumo.origen` (`docs/modelo/inventario.md`) |
| R017 | MovimientoStock, «se origina» | 0..* | Cuando exista el stock maduro y comercial (ronda futura) |

### Herencias

Hijas directas **en esta ronda**: `OrdenTrabajo` (`produccion`), `Bitacora` (`produccion`) y `MovimientoInsumo` (`inventario`). Implementación: herencia multitabla de Django; la clave primaria de la hija es `origendocumento_ptr`. Las hijas de las hijas (`Siembra`, `Consumo`, etc.) no cambian.

Rondas futuras: `Cosecha`, `Entrega` y `MantenimientoTecnico` (por `OrdenTrabajo`), `Contrato`/`Suministro`, `Pago`, `PagoCliente`, `SolicitudRevision` y `MovimientoStock`.

**No hereda `EtapaProductiva`**, aunque el modelo de dominio lo dice en su ficha: una etapa es configuración y no un documento (D-52 punto 7; posible error del modelo, anotado en `docs/temas_abiertos.md`).

### Restricciones y reglas

- `tipo` obligatorio y dentro de la lista; `OrigenDocumento.save()` lanza error si lo llama alguien que no es una hija directa (la hija fija su `tipo`).
- Nadie borra un documento de origen: todas las claves que lo apuntan son `PROTECT`.
- No tiene reglas de negocio propias: las de cada documento están en su ficha.
