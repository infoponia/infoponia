# API · Direcciones y CUIT (`maestros/servicios/direcciones.py` y `maestros/validadores.py`)

Contrato de D-58. Lo implementa COM-01 en `maestros` (sacando a la luz lo que hoy es privado de `invernaderos.py` y de `perfil.py`) y lo
usa `comercial` para las direcciones de los clientes. Si algo de acá no alcanza, frená (L9): no copies la validación en tu app.

`maestros` es de nivel 3: `comercial` (6) puede importarlo. Estas funciones **no** auditan, **no** validan el rol y **no** notifican:
eso es del caso de uso que las llama. Corren dentro de la transacción de quien llama.

## Datos de una dirección

Los nombres de los campos son los que ya usa el formulario del invernadero (D-39), para que las dos pantallas se parezcan:

| Campo | Zona | Obligatorio | Nota |
|---|---|---|---|
| `tipo_direccion` | — | sí | `urbana` o `rural` (regla 2 de PROD-ALT-INV) |
| `calle`, `numero_calle` | urbana | sí | El número es texto («S/N», «1234 bis»), con su validador de formato |
| `piso`, `departamento_unidad`, `barrio`, `referencias` | urbana | no | `departamento_unidad` se guarda en `DireccionUrbana.departamento` |
| `ruta`, `kilometro` | rural | sí | El kilómetro tiene su validador de formato |
| `lote_rural` | rural | no | Se guarda en `DireccionRural.lote` |
| `localidad` | — | sí | Id de una `Localidad` de Georef (regla 3 de PROD-ALT-INV, MD-88). `provincia` y `departamento` sirven solo para filtrar la lista |

Los textos se recortan; los datos de la otra zona se descartan; los largos son los de las columnas de `DireccionUrbana` y
`DireccionRural`. Los mensajes y los códigos de error son **los mismos** que hoy da el alta del invernadero.

## Funciones (`maestros/servicios/direcciones.py`)

| Función | Qué hace | Devuelve o lanza |
|---|---|---|
| `validar_direccion(datos) -> DireccionValidada` | Valida sin tocar la base, salvo para leer la localidad. Junta todos los errores | `DireccionValidada = namedtuple("DireccionValidada", "zona localidad campos")`, con `campos` ya limpios; o `ValidationError` con un error por campo (`error_dict`) |
| `crear_direccion(validada) -> DireccionUrbana \| DireccionRural` | Crea la dirección, activa | La hija creada |
| `corregir_direccion(hija, validada) -> DireccionUrbana \| DireccionRural` | Corrige **en el lugar** una dirección de la **misma zona** (urbana con urbana, rural con rural). Con otra zona lanza `ValueError`: el cambio de zona es otra dirección (abajo). **Quien llama** decide antes que la dirección no está en uso | La misma hija, actualizada |
| `inactivar_direccion(direccion)` | `estado_direccion = inactivo`. No hace nada si ya lo estaba | — |
| `borrar_direccion(direccion)` | Borra la hija y su `Direccion`. Lanza `ProtectedError` si algo la referencia (por eso quien llama borra antes su vínculo) | — |
| `datos_de_la_direccion(hija)` | Ya existe en `invernaderos.py`: se mueve acá y `invernaderos.py` la importa | `{campo: valor o None}` |
| `clave_de_ubicacion(hija) -> tuple` | La clave de «dirección idéntica» (D-58, punto 6): zona, localidad y los datos de ubicación normalizados | Tupla comparable |

**Cambio de zona** (urbana a rural o al revés): como hace hoy `modificar_invernadero`, es **otra dirección**. Quien llama crea la nueva
(`crear_direccion`), cambia su propio vínculo para que apunte a ella (el invernadero o el `DireccionCliente`) y recién después borra la
anterior (`borrar_direccion`): con el vínculo apuntando a la vieja, el `PROTECT` lo impide.

`maestros/servicios/invernaderos.py` deja de tener `_limpiar_direccion`, `_crear_direccion` y su propio `_buscar_localidad`: llama a
estas. **Ninguna prueba de `maestros` cambia**; si alguna falla, el refactor cambió comportamiento y hay que frenar.

## CUIT (`maestros/validadores.py`)

`validar_cuit(valor) -> str`: acepta el CUIT con o sin guiones ni espacios; devuelve los 11 dígitos. Si no son 11 dígitos o el dígito
verificador no da (módulo 11 con los pesos 5, 4, 3, 2, 7, 6, 5, 4, 3, 2; un resto que da 11 vale 0 y uno que da 10 no es válido), lanza
`ValidationError("El CUIT no es válido: revisá los números (11 dígitos, con su dígito verificador).", code="cuit_invalido")`. Es el
mensaje que ya usa ADM-MOD-ORG. `maestros/servicios/perfil.py` deja `_cuit_valido` y llama a esta.

Para mostrarlo: `formatear_cuit("30712345671") -> "30-71234567-1"`.

## Pruebas mínimas (en `maestros`)

- `maestros/tests/test_direcciones.py`: validar una urbana y una rural válidas; cada obligatorio que falta y cada formato inválido, con
  su código; la localidad que no existe; crear, corregir (misma zona y cambio de zona), inactivar y borrar; `clave_de_ubicacion` igual
  para dos direcciones que solo difieren en mayúsculas y espacios, y distinta si cambia la localidad.
- `maestros/tests/test_validar_cuit.py`: válidos con y sin guiones, verificador 0 por resto 11, verificador 10 inválido, menos y más de
  11 dígitos, letras.
- La suite de `maestros` entera sigue igual (alta, modificación y perfil).
