# Estado del proyecto — InfoPonia

Última actualización: 05/11/2026. Este archivo se reescribe al final de cada sesión.

## Hecho

- Hito 0: proyecto Django mínimo corriendo en local; repositorio `infoponia/infoponia` con main
  protegida (PR obligatoria con una aprobación); despliegue automático en Render desde main;
  base de producción en Neon.
- Decisiones D-01 a D-14 (modelo de usuario, nombres, claves, versión del modelo de dominio,
  «contacto», un solo Gerente activo, Administrador técnico, el rol no se modifica, varios Administradores, reemplazo del Gerente en dos operaciones,
  pendientes por rol). Ver `docs/decisiones.md`.

## En curso

- Tarea 01: modelo de usuario propio en la app `core` (D-01 a D-03, D-09 a D-11).
  Rama: `feature/usuario-propio`.

## Siguiente

1. Recrear la base local antes de la primera migración de `core` (lo hace el estudiante en pgAdmin).
2. Reiniciar la base de Neon **antes** de mergear la PR del usuario propio y volver a crear los
   Administradores con `createsuperuser` (lo hace el estudiante; Claude Code no opera contra Neon).
3. Confirmar que `.claude/settings.json` (atribución vacía, bloqueo de `.env`) está en main y que el
   primer commit no lleva línea de coautor.

## Registrado el 05/11/2026

- Administrador técnico, un solo Gerente activo y R002 a R006 calculadas: ya están en pendientes_MD
  (MD-55), pendientes_DER (DER-10), pendientes_CU (caso 23 y ajustes en COM-EVL-DSC y CMP-APR-ODC),
  el glosario y pendientes_prototipo (pendiente 45). Pendientes por rol (D-14) registrado el mismo día en pendientes_CU, pendientes_MD y pendientes_prototipo. Los CU extendidos y el diagrama del modelo de
  dominio no se tocaron: se ajustan en la próxima ronda.

## Temas abiertos

- Pantalla propia para el Administrador: por ahora usa el admin de Django; si se hace, comparte la
  pantalla de usuarios (caso 23 de pendientes_CU).
- Plazos que corren mientras no hay Gerente activo (por ejemplo, la vigencia de las cotizaciones): a resolver en el CU de baja del Gerente.
- Reparto final de apps entre los dos integrantes.
- Lista cerrada de los casos de uso del 80% y orden de implementación.
- Enfoque de pruebas (un test por regla numerada, TDD en servicios): sin confirmar.
- Casos de uso de iniciar sesión, cerrar sesión y recuperar contraseña: no están escritos. Antes de la tarea 02 hay que escribir al menos una versión breve de iniciar sesión, alta, modificación y baja de usuario.
- Recuperar contraseña depende del correo, que solo funcionará en Render pago.
- Hacer configurables por `.env` el host, el puerto, el nombre y el usuario de la base local.
