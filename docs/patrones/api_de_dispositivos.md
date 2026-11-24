# Patrón · Cómo se escribe una ruta de la API de dispositivos

Para quien programa una ruta nueva de la API del nodo central (`/api/iot/v1/`, D-70): IOT-05 (comandos) y las que vengan. El contrato (rutas, mensajes, códigos y motivos)
es `docs/api/nodo/`; esto explica cómo se programa. Lo creó IOT-03. Si algo de acá contradice una decisión, manda la decisión: avisá.

## Las piezas (`iot/api/`)

- `urls.py`: una ruta por mensaje, sin barra final, y al final una que atrapa cualquier otra y responde 404 `ruta_inexistente` en JSON. **Una ruta nueva va antes de esa.**
- `vistas.py`: una vista por ruta, con `login_not_required`, `csrf_exempt` y `never_cache` (el proyecto exige sesión en toda vista, SEG-13; la API se protege con el token). La vista **solo
  traduce y orquesta**: ninguna regla de negocio (D-70, punto 4).
- `traduccion.py`: convierte el JSON en objetos simples y verifica **solo la forma** (claves exactas, tipos de la envoltura, forma del identificador). No consulta la base.
- `autenticacion.py` (solo calcula el resumen SHA-256 del token), `limites.py` (el contador de pedidos), `respuestas.py` (el cuerpo y los encabezados) y `reloj.py` (la hora).

## Las rutas de comandos (IOT-05)

- `GET comandos` (el retiro; sin cuerpo) y `POST comandos/<int:id>/resultado` (un resultado), las dos **antes** de la ruta que atrapa todo. El retiro usa `_atender(request, tratar, metodo="GET", con_cuerpo=False)` y salta las verificaciones 7 a 11.
- **La comunicación del nodo la registra el servicio** (`retirar_comandos`, `registrar_resultado`), no `_comunicacion`: el retiro tiene que leer la comunicación **anterior** antes de actualizarla (D-78 punto 2, el «sin señal» de 2a.1a). Un resultado de un comando que no existe o no es del nodo (4e) no registra la comunicación; uno de un comando nunca entregado (D-78 punto 12) sí.
- Los servicios lanzan `SistemaDesconectado` (403) y `ComandoInexistente` (404 `comando_inexistente`); un resultado repetido es 200 `ya_resuelto` y queda en el registro técnico.

## El orden de verificación

Es el de **`docs/api/nodo/respuestas_y_errores.md`, sección 3**: no se copia acá (si cambia, cambia allá primero, D-70 punto 1). En el código lo hacen `_recibir` (las verificaciones de método, token,
límite, sistema, tamaño, tipo y JSON) y la vista (la forma del mensaje y la cantidad de elementos), y `_atender` lo envuelve todo: lee la hora una vez y convierte una falla inesperada en 500
`error_interno`. Una ruta nueva usa `_atender` y no repite esas verificaciones.

## Qué se hace después de verificar

1. **La comunicación del nodo**, en su propia transacción y antes de procesar los elementos (`nodo.registrar_comunicacion`). Un lote vacío hace solo esto: es el latido.
2. **Una transacción por elemento** (cada lectura, cada estado) y una sola para un mensaje que se procesa entero o nada (el anuncio). Un error inesperado en un elemento se registra con
   `logger.exception` y ese elemento vuelve con `error_interno`; los demás se procesan igual.
3. **Los servicios no conocen HTTP**: reciben `ahora` y los datos ya traducidos (`ElementoMalFormado` cuando la forma no sirve). Una sola hora por pedido: `reloj.ahora()` se llama una vez y se pasa.
4. **La auditoría** de lo que cambió va por `iot/servicios/auditoria_nodo.py` (`auditar_entrega`): una acción, actor `None`, con `datos` y `cambios` (D-36). Se audita solo si cambió algo.
5. **Los bloqueos** siguen el orden de toda la API: invernadero → sistema (releído) → equipo (`docs/patrones/bloqueos.md`).

## El registro del servidor y el token

`logging.getLogger("iot.api")`: un `warning` por elemento rechazado (sistema, identificador y motivo) y `exception` por cada `error_interno`. **Nunca el token ni el encabezado `Authorization`**: de ellos
solo se calcula el resumen, que tampoco se escribe en ningún registro. Hay una prueba que lo comprueba con un pedido con rechazos y una falla simulada.

## Pruebas

- **Los ejemplos del contrato** (`iot/tests/test_api_ejemplos.py`): se arma el escenario de `docs/api/nodo/ejemplos/README.md`, se manda cada `*.pedido.json` y se compara la respuesta con su
  `*.respuesta.json` campo por campo, salvo `servidor_en`. Los archivos se leen desde `settings.BASE_DIR`: si cambia un ejemplo, la prueba lo sigue. Un ejemplo nuevo del contrato lleva su prueba.
- **Las vistas** (`iot/tests/test_api_nodo.py`): cada código HTTP con sus encabezados, el orden de verificación, que no hace falta sesión ni CSRF (el cliente exige CSRF) y que el token no aparece
  en ningún registro. La hora se reemplaza con `mock.patch("iot.api.reloj.ahora", ...)`.
- **La concurrencia** (`iot/tests/test_api_concurrencia.py`, `@tag("concurrencia")`): `correr_a_la_vez` con `detener_antes_de` para fijar el orden (`docs/patrones/bloqueos.md`).
- **Parches sobre el módulo real.** En las pruebas de servicios se usa `perezoso` (`inventario/tests/fabricas.py`): un objeto que importa el módulo recién cuando se le pide algo, para que el archivo
  de pruebas no falle al importarse mientras el servicio no existe. Un parche sobre ese objeto **no llega al módulo real**: parcheá por ruta (`mock.patch("iot.servicios.lecturas.registrar_lectura")`)
  o con `importlib.import_module`.
