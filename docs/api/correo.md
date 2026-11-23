# API · Correo (`core/correo.py`)

Contrato de USR-10 (D-54). Lo usan las apps de nivel mayor que mandan correo; la primera es `iot` (IOT-04). Si algo de
acá no alcanza, frená (L9): no copies `_enviar_correo`.

## Funciones

| Función | Qué hace | Devuelve |
|---|---|---|
| `enviar_correo(cuenta, asunto, plantilla, contexto)` | Envía a `cuenta` un correo en texto plano. `cuenta` necesita `.pk` y `.email` | `True` si salió; `False` si el servidor falló (el error no se propaga) |
| `correo_configurado()` | Lee `settings.CORREO_CONFIGURADO` en cada llamada (D-33) | `bool` |

## Reglas de uso

1. Se llama **después de cerrar el `atomic()` que creó lo que se avisa** (como `_enviar_invitacion`, D-35), nunca
   adentro: un servidor SMTP lento (hasta `EMAIL_TIMEOUT`) no puede mantener bloqueos tomados, y el correo no debe salir
   para algo que después se deshizo (D-14).
2. La plantilla recibe `contexto` más `nombre_organizacion` (la identidad registrada, D-48): quien llama no lo pasa.
3. Quien llama pone su plantilla en su propia app (la primera, `iot`: `iot/templates/iot/correo/`). `core` no conoce a
   quienes la llaman (A4).
4. Si falla, el registro de errores (logger `core.correo`) lleva el id de la cuenta y nunca el contenido, que puede
   traer un enlace que da acceso. Quien llama decide qué ve la persona.
5. `enviar_correo` no comprueba que el correo esté configurado: preguntá antes con `correo_configurado()`.
6. No llames a `core.servicios._enviar_correo`: es la envoltura de la recuperación y la invitación.
