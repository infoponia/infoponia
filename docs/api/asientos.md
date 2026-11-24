# API · Asientos contables (`contabilidad.servicios`)

Para quien programa un caso de uso con asiento (producción, inventario, comercial y compras) o una pantalla que muestra datos contables, sin
leer el código de `contabilidad`. Versión de CON-02 (la escribe esa tarea; este archivo es su contrato). Las decisiones están en **D-84**,
**D-85** y **D-86**; el patrón de uso, en `docs/patrones/asientos.md`. Si algo de acá contradice una decisión o un caso de uso, manda la
decisión o el caso de uso: avisá.

`contabilidad` es de nivel 2: **todas** las apps de nivel mayor pueden importarla (regla A1 de D-37). Ella no importa de ninguna.

## Constantes

```python
from contabilidad import cuentas            # códigos del plan de cuentas (docs/modelo/contabilidad.md)
from contabilidad.constantes import DEBE, HABER      # "D" y "H"
```

`cuentas.CAJA == "1.1.01"`, `cuentas.PROVEEDORES == "2.1.01"`, etc. (la lista completa está en el modelo). **Nunca escribas un código a mano.**

## Escritura: crear el asiento automático de una operación

```python
from contabilidad.servicios import asientos

asiento = asientos.registrar_asiento_automatico(
    actor,                      # la cuenta que actúa, o None si lo hace InfoPonia (paso diario)
    origen,                     # instancia ya guardada de una hija de OrigenDocumento (recepción, pago, entrega...)
    fecha,                      # date: la fecha del HECHO (H10), no la de registro
    [(cuentas.INSUMOS_EN_STOCK, DEBE, Decimal("3000.00")),
     (cuentas.PROVEEDORES,      HABER, Decimal("3000.00"))],
    descripcion="",             # opcional en un asiento automático
    hoy=None,                   # solo para pruebas: la fecha de hoy
)
```

- **Devuelve** el `AsientoContable`, o **`None`** si no corresponde asiento: los movimientos de importe 0 se omiten y con menos de dos
  movimientos no hay asiento (H11). Quien llama **no** falla por eso.
- **Dentro de la transacción de quien llama**, con sus bloqueos ya tomados. Bloquea el ejercicio **al final** (`docs/patrones/asientos.md`).
- **Elige el ejercicio** por la fecha (D-84 punto 5): el que contiene la fecha, abierto o en cierre. **Nunca rechaza por la fecha** (D-102): si cae en
  un ejercicio *cerrado*, es anterior al primer ejercicio o es posterior a hoy, el asiento va al abierto con la fecha de hoy y la descripción
  aclara la fecha real: «Fecha del hecho: dd/mm/aaaa (el ejercicio de esa fecha ya está cerrado | anterior al primer ejercicio | posterior a la
  fecha de hoy); se registra con la fecha de hoy.». Tu `descripcion` va primero, separada por « — »; el total no pasa de 300 caracteres (se
  recorta la tuya, terminada en «…», nunca la aclaración). Antes de elegir, **se recupera solo** si el ejercicio
  abierto ya venció (H9) o si todavía no hay ninguno (puesta en marcha).
- **Numera** correlativo por ejercicio (H8) y **audita** el asiento y cada movimiento (`alta_asiento_contable`, `alta_movimiento_contable`):
  no los audites vos. En tu propio registro de auditoría nombrá el asiento entre los `afectados` o con `referencia(asiento)` en `datos`.
- **Lanza `ErrorContable`** (siempre errores de programación): `asiento_desbalanceado` (Debe ≠ Haber), `cuenta_inexistente`,
  `origen_con_asiento` (ese origen ya tiene su asiento: R012 en 0..1), `importe_invalido` (negativo o con más de dos decimales),
  `tipo_de_movimiento_invalido`.
- `Decimal`, nunca `float`. Los importes llegan con dos decimales (redondeá vos con `ROUND_HALF_UP` antes de llamar y documentá cómo).

```python
class ErrorContable(Exception):
    codigo: str          # uno de los de arriba o de CON-03
    mensaje: str         # en español, para mostrar
    campo: str | None
```

## Escritura: asiento manual, contraasiento y ejercicio (CON-03b y CON-03a; los usa la interfaz de contabilidad)

| Función | Qué hace |
|---|---|
| `asientos.registrar_asiento_manual(actor, fecha, descripcion, movimientos) -> AsientoContable` | CON-REG-ASI completo (permisos, fecha, auditoría). Las demás apps **no** la llaman |
| `asientos.contraasentar(actor, asiento_id, fecha, descripcion) -> AsientoContable` | CON-CTR-ASI completo, con la notificación al Gerente |
| `ejercicios.cerrar_ejercicio(actor, ejercicio_id) -> EjercicioContable` | CON-CRR-EJE |
| `ejercicios.abrir_ejercicio_si_corresponde(hoy=None) -> ResultadoApertura` | CON-ABR-EJE. La llaman el paso diario `abrir_ejercicio` y el servicio de asientos; idempotente. `ResultadoApertura` suma `cantidad_creados` y `cantidad_cerrados_solos` (varias vueltas si el sistema estuvo apagado) |
| `ejercicios.crear_primer_ejercicio(fecha_inicio) -> EjercicioContable` | La puesta en marcha (D-84 punto 3); la llama el comando `poner_en_marcha_contabilidad` |

## Lectura (no escribe, no bloquea)

| Función | Devuelve |
|---|---|
| `ejercicios.ejercicio_abierto()` | El `EjercicioContable` abierto o `None` |
| `ejercicios.ejercicio_en_cierre()` | El en cierre o `None` |
| `ejercicios.ejercicio_para(fecha, *, automatico, hoy=None)` | El ejercicio donde iría un asiento con esa fecha, o `ErrorContable` (`fecha_en_ejercicio_cerrado`, `fecha_futura`, `fecha_anterior_al_primer_ejercicio`) si es manual y no entra. Lo usa la interfaz para validar la fecha de un formulario |
| `libro.saldo_por_cuenta(ejercicio_id) -> dict[str, Saldo]` | `Saldo(debe, haber, saldo_inicial, saldo, contrario)` por `codigo_cuenta`; cuentas de resultado desde cero, patrimoniales con lo acumulado (D-84 punto 8) |
| `libro.movimientos_de_cuenta(codigo, ejercicio_id)` | Los movimientos con su saldo acumulado, para la vista por cuenta |
| `libro.resultado_del_periodo(desde, hasta)` | `Resultado(ingresos, egresos, resultado)` por **fecha del asiento**, aunque el período cruce dos ejercicios (lo usa Estadísticas, EST-02) |
| `libro.total_por_cuenta_en_periodo(codigo, desde, hasta, *, tipo=None)` | Por fecha del asiento (extremos inclusivos). Con `tipo` «D» o «H», la suma de ese lado; con `tipo=None`, el saldo según la naturaleza de la cuenta (Debe − Haber en una deudora, Haber − Debe en una acreedora), con su signo aunque quede contrario. Otro `tipo`: `tipo_de_movimiento_invalido` (D-102) |
| `responsables.contador_activo()` | El `Contador` activo o `None` (D-85 punto 5; lo usa `responsable_contable`) |
| `responsables.responsable_contable()` | El Contador activo o, si no hay, el Gerente activo, o `None` (D-85 punto 5) |
| `responsables.puede_registrar_asientos(usuario)` | `True` si es el Contador activo, o el Gerente activo **sin Contador activo**. Vale también para registrar pagos |
| `responsables.notificar_al_responsable_contable(titulo, detalle, *, excluir=None)` | Una notificación (D-42) al responsable contable, sin la cuenta `excluir`; sin responsable no hace nada ni falla |

## Reglas para quien llama

1. **Un origen, un asiento.** Si tu operación tiene dos asientos (por ejemplo la venta y su costo), cada uno necesita su propio documento de
   origen o los dos son **un asiento compuesto**: lo dice el caso de uso. Nunca llames dos veces con el mismo `origen`.
2. **Llamala después de crear el documento de origen** y de bloquear todo lo tuyo (invernadero, sectores, insumos, lotes, órdenes…), y **antes**
   de salir de la transacción. Ver `docs/patrones/asientos.md`.
3. Si tu caso de uso corrige algo ya asentado, **no edites el asiento**: el caso de uso define el asiento inverso (como en CMP-COR-RCP) o el
   Contador hace un contraasiento a mano. Un asiento no se edita ni se borra.
4. Un servicio **no pregunta por el rol** del actor para decidir quién registra o paga: usa `responsables`.
5. Todo importe es `Decimal` con dos decimales; en la auditoría, como texto (`docs/patrones/auditoria.md`).

## Pruebas de tu app

`contabilidad/tests/fabricas.py` (lo crea CON-02):

- `ejercicio_abierto(inicio=None, cierre=None)`, `ejercicio(estado, inicio, cierre)` y `asiento_de_prueba(...)`.
- `PlanDeCuentasMixin`: las clases de pruebas que usan cuentas heredan de él (carga una vez, confirma y corre `ANALYZE`;
  `docs/patrones/datos_de_migracion.md`).
- `verificar_invariantes_contables()`: Debe = Haber en cada asiento, dos o más movimientos, numeración correlativa sin huecos por
  ejercicio, un abierto y un en cierre como máximo, rangos que no se pisan. Llamala al final de toda prueba que cree asientos.
