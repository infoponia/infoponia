# USR-10 · Envío de correo público de `core` (D-54)

Estado: pendiente | App: core | Rama: feature/usr-10-envio-de-correo-publico | Ronda: IoT (se hace después de «Producción 1»)

Depende de: — (no necesita nada de la ronda de producción; se puede hacer en cualquier momento antes de IOT-03)

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9). Es una tarea **chica**: una refactorización sin cambio de comportamiento.

## Casos de uso incluidos

No es un caso de uso: es una pieza de infraestructura (D-54) que dejan lista `core` para que otras apps envíen correo.

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| USR-RCP-CTR, USR-ALT-USR | Siguen funcionando igual (recuperación de contraseña e invitación usan el envío) | docs/casos_de_uso/usuarios.md | Solo para no romperlos |

## Leer

- Código: `core/servicios.py` (`_enviar_correo` y quienes la llaman), `core/tests/` (las pruebas de recuperación e invitación)
- Decisiones: D-14, D-33, D-35, D-54
- Reglas: .claude/rules/pruebas.md

## Límites

- Crea modelos: ninguno
- Migraciones: ninguna
- Permitido fuera de la app: nada (toda la tarea es en `core`)
- Dependencias nuevas: ninguna
- Fuera de alcance: cambiar plantillas existentes; enviar correos en HTML; cola de envíos (si hiciera falta, es otra decisión)

## Pasos

1. **`core/correo.py`** con `enviar_correo(cuenta, asunto, plantilla, contexto) -> bool` y `correo_configurado() -> bool` (D-54, punto 1). El cuerpo es el de `_enviar_correo` actual, movido sin cambiarlo. Docstring: se llama **siempre fuera de una transacción** (D-14) y no registra el contenido. Pruebas: `test_correo.py` (sale y devuelve `True`; falla del servidor → `False` y un registro de error con el id de la cuenta y sin el cuerpo; `correo_configurado` sigue a `settings.CORREO_CONFIGURADO` en cada llamada).
2. **`_enviar_correo` delega** en la pública, sin cambiar su firma. Las pruebas de recuperación e invitación pasan sin tocarlas.
3. **Documentar** en `docs/api/` (un párrafo en `notificaciones.md` o un archivo `correo.md`, el que corresponda) la función y la regla de uso.

## Hecho cuando

- Ninguna prueba existente de `core` cambió y todas pasan.
- Un llamador de otra app puede importar `core.correo.enviar_correo` (la prueba lo importa desde otra ruta).
- Comando de pruebas: python manage.py test core.tests --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

## Cierre (la completa Claude Code al cerrar)
