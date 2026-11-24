# Patrón · Enlace del cliente (acceso temporal sin cuenta)

Cómo se programa el enlace que recibe un cliente por correo para hacer **una** cosa sin tener usuario: decidir un faltante (COM-DCD-FLT,
COM-04c) y, desde COM-06b, confirmar una entrega (COM-CNF-ENT). Decisión: **D-65** (y D-68, puntos 1 y 8, para la confirmación). Lo
programa COM-04c; COM-06b lo reutiliza con dos cambios chicos: `crear_enlace` suma el argumento `entrega` y la vigencia de la confirmación se
calcula (sección 9).
Si algo de acá contradice un caso de uso, manda el caso de uso: avisá.

## 1. Piezas

| Pieza | Dónde | Qué hace |
|---|---|---|
| `nuevo_token() -> (token, resumen)` y `resumen_de(token) -> str` | `core/enlaces.py` (funciones puras, sin modelos) | `secrets.token_urlsafe(32)` y su SHA-256 en hexadecimal (64 caracteres) |
| `EnlaceCliente` | `comercial/models.py` (`docs/modelo/comercial.md`) | El enlace: tipo, cliente, a qué da acceso, resumen del token, vencimiento, estado y resultado del envío. Solo para clientes con correo |
| `comercial/servicios/enlaces.py` | `comercial` | `crear_enlace`, `enlace_vigente`, `bloquear_enlace`, `anular_enlaces_de`, `enviar_enlace` |
| Vistas públicas | `comercial/views_cliente.py`, URL `cliente/` | Sin `login_required`; plantilla base propia (`comercial/cliente/base.html`) sin menú ni campana |

## 2. Crear un enlace (`crear_enlace(tipo, cliente, *, compra_venta, vence) -> (EnlaceCliente, token)`)

- Corre **dentro de la transacción** del caso de uso, con la venta ya bloqueada.
- Solo si el cliente tiene correo: un cliente sin correo no tiene enlace (lo decide el Vendedor, extensión 1a de COM-DCD-FLT). El caso de uso
  base lo sabe antes y, en ese caso, no llama a `crear_enlace` y notifica al Vendedor («El cliente de CV-… no tiene correo: registrá vos su
  decisión sobre el faltante.», con el enlace a «Registrar decisión de faltante»). Igual pasa el enlace vigente, si lo había, a `reemplazado`.
- Si la venta tiene un enlace `vigente` del mismo tipo, lo pasa a `reemplazado` (regla «Enlace de decisión» de COM-DCD-FLT).
- Guarda `token_resumen = resumen_de(token)`, **nunca el token**. El token vive solo en memoria hasta armar el correo.
- Registra `transaction.on_commit(lambda: enviar_enlace(enlace.id, token))`. Si la transacción se revierte, no sale ningún correo.
- Devuelve el token solo para las pruebas: ningún llamador lo guarda ni lo muestra.

## 3. Enviar (`enviar_enlace(enlace_id, token)`, fuera de toda transacción)

1. Lee el enlace y el cliente. Si el enlace ya no está `vigente` (otra operación lo anuló entre el commit y el envío), no envía nada.
2. Si el cliente se quedó sin correo entre el commit y el envío (lo borró una modificación): `pendiente_envio` y la notificación del punto 3.
3. Con correo: `core.correo.enviar_correo(Destinatario(...), asunto, plantilla, contexto)` (USR-10, con el `Destinatario` de `comercial` de
   COM-02). `True` → `enviado`; `False` → `pendiente_envio` y la misma notificación al Vendedor, con «no se pudo enviar el enlace a {correo}».
   Cada resultado se guarda con un `UPDATE` propio (`transaction.atomic()` corto): no se audita (no es un dato del dominio).
4. El correo lleva la URL absoluta `https://<host>/cliente/<token>/` (con `settings` del sitio, como la invitación de USR-08b), la venta, lo
   que el caso de uso pide (8c de PROD-CNL-ORD y 13a de PROD-CNC-CSC: cantidades solicitada y disponible de cada detalle y la fecha pactada) y
   hasta cuándo puede decidir.

## 4. Abrir (`/cliente/<token>/`)

1. `enlace_vigente(token)` busca por `resumen_de(token)`. **Comparar resúmenes** (no tokens) hace innecesario `compare_digest`: el resumen
   es el índice único.
2. Si sirve, guarda `request.session["enlace_cliente"] = enlace.id` y redirige (302) a `/cliente/enlace/` (sin el token). Si no sirve,
   muestra la pantalla «Este enlace no se puede usar» con el motivo que el caso de uso permite (venció, ya se usó, fue reemplazado por uno
   más nuevo, la venta se canceló o ya no tiene nada pendiente) y los datos de contacto del Vendedor. Un token que no existe da «Este enlace
   no es válido», sin más.
3. Las páginas de `/cliente/…` responden con `Cache-Control: no-store`, `Referrer-Policy: same-origin` (no `no-referrer`: con esa política el navegador manda `Origin: null` en los POST y el CSRF los rechaza; D-65 corregida, igual que D-88) y `X-Robots-Tag: noindex`, y con el
   decorador `never_cache`. No leen `request.user`: una sesión de usuario abierta en el mismo navegador no cambia nada.
4. La sesión del enlace no da acceso a otra cosa: cada vista vuelve a leer el enlace por el id de la sesión, verifica que siga sirviendo y
   muestra solo la venta del enlace (garantía «El Cliente solo ve su venta»).

## 5. Registrar (el envío único)

Dentro de la transacción del caso de uso, **después** de sus bloqueos (invernaderos, variedades, lotes, partidas, la venta y sus detalles),
`bloquear_enlace(enlace_id)` (`FOR NO KEY UPDATE`), y con la fila bloqueada se vuelve a verificar `estado = vigente` y `hoy <=
fecha_vencimiento`. El caso de uso pasa el enlace a `usado` con `fecha_uso` y lo pone en su único registro de auditoría. Dos envíos a la vez
(dos pestañas): el segundo espera, ve `usado` y no registra nada (extensión 6a).

## 6. Anular (`anular_enlaces_de(compra_venta)`)

La llaman, dentro de su transacción: PROD-ASG-CAM cuando la venta ya no tiene detalles pendientes (postcondición d), COM-DCD-FLT al
registrar (el usado no se toca) y, desde COM-05, COM-CNL-CVT. Pasa a `anulado` los `vigentes`.

## 7. Vencer (paso diario 27, `avisar_enlaces_vencidos(hoy)`)

Por enlace `vigente` con `fecha_vencimiento < hoy`, en su transacción: `vencido` y una notificación al Vendedor («Venció el plazo del cliente
de CV-… para decidir el faltante: podés registrar la decisión en su nombre.»). Idempotente: un enlace `vencido` no se vuelve a tomar.

## 8. Pruebas mínimas (`comercial/tests/test_enlaces.py`)

- El token no está en la base (se busca el texto en todas las columnas de la fila) y dos tokens seguidos son distintos.
- Abrir con un token válido redirige a una URL sin el token; con uno inválido, vencido, usado, reemplazado y anulado, la pantalla y el
  motivo de cada uno; el día del vencimiento todavía sirve y el siguiente no.
- Los tres encabezados en cada página de `/cliente/`.
- La sesión de un enlace no abre la venta de otro (cambiar el id en la sesión a mano da la pantalla de enlace no válido).
- Un rollback del caso de uso no envía el correo (`captureOnCommitCallbacks`); un `enviar_correo` que devuelve `False` deja
  `pendiente_envio` y notifica al Vendedor.
- Concurrencia (`@tag("concurrencia")`): dos envíos del mismo enlace a la vez registran uno solo.

## 9. La confirmación de una entrega (COM-06b, D-68)

- `crear_enlace("confirmacion_entrega", cliente, entrega=entrega)`: lo llama `concretar_entrega` (COM-06a) en una entrega de suministro de un
  cliente con correo. Uno por entrega, **sin reemplazo** (único `(entrega)` en este tipo) y sin `vence`.
- **Vigencia calculada:** `entrega.fecha_resolucion_orden + dias_vigencia_enlace_confirmacion` (el parámetro vigente al abrir y al
  registrar), porque la regla «Enlace de confirmación» de COM-CNF-ENT cambia la vigencia de los ya enviados si cambia el parámetro.
  `fecha_vencimiento` queda nula; `enlace_vigente` y la verificación de la sección 5 la calculan según el tipo.
- El paso 27 (sección 7) no toma este tipo: un enlace de confirmación no usado no avisa nada («sin confirmación tácita»).
- El correo (sección 3) lleva el comprobante de la entrega y el enlace en uno solo (postcondición l de COM-CNC-ENT).
- **Reintento** (15a de COM-CNC-ENT): `reemitir_enlace(enlace)` da un token nuevo a la misma fila (solo `vigente` y sin usar) y lo manda;
  lo llama la parte 4 del paso 50. El faltante no lo usa (sección 3: sin reintento, aviso al Vendedor).
- Pruebas: las de la sección 8, también para este tipo, más el cambio del parámetro y la falta de reemplazo.
