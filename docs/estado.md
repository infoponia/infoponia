# Estado del proyecto — InfoPonia

Última actualización: 06/11/2026. Este archivo se reescribe al final de cada sesión.

## Hecho

- Hito 0: proyecto Django mínimo corriendo en local; repositorio `infoponia/infoponia` con main
  protegida (PR obligatoria con una aprobación); despliegue automático en Render desde main;
  base de producción en Neon.
- Decisiones D-01 a D-15 (modelo de usuario, nombres, claves, versión del modelo de dominio,
  «contacto», un solo Gerente activo, Administrador técnico, el rol no se modifica, varios
  Administradores, reemplazo del Gerente en dos operaciones, pendientes por rol, tipo de
  `telefono`). Ver `docs/decisiones.md`.
- Política de pruebas fijada en `CLAUDE.md`: acumulación, unidad por regla, integración por flujo
  principal, TDD por lote en servicios con revisión del estudiante y convención de nombres.
- Tarea 01: modelo de usuario propio en la app `core` (D-01 a D-03, D-09 a D-11, D-15).
  `Usuario` con email único y sin username; seis roles con herencia multi-tabla (Gerente,
  Agrónomo, Capataz, Vendedor, Transportista, Técnico); restricciones en la base (rol vacío
  solo para superusuario, un solo Gerente activo) con `Gerente.clean()` como respaldo de
  formulario; admin con nombres visibles por rol, sin alta de `Usuario` genérico y `rol` de
  solo lectura; 10 pruebas en `core/tests/test_usuario.py`; migraciones `0001_initial` y
  `0002_alter_agronomo_options_alter_capataz_options_and_more`. Verificado a mano en el admin
  local. Rama `feature/usuario-base`.

## En curso

- Nada por ahora.

## Siguiente

1. Reiniciar la base de Neon **antes** de mergear la PR del usuario propio y volver a crear los
   Administradores con `createsuperuser` (lo hace el estudiante; Claude Code no opera contra Neon).
2. Confirmar que los commits de esta rama no llevan línea de coautor.
3. Tarea chica: renombrar las 10 pruebas de `core/tests/test_usuario.py` con la convención de
   `CLAUDE.md` (prefijo `test_d<numero>_`), sin cambiar lo que verifican.
4. Escribir al menos una versión breve de los casos de uso de iniciar sesión, alta, modificación
   y baja de usuario, antes de empezar la Tarea 02.
5. Tarea chica aparte: configurar GitHub Actions para correr la suite de pruebas en cada PR.

## Registrado el 05/11/2026

- Administrador técnico, un solo Gerente activo y R002 a R006 calculadas: ya están en pendientes_MD
  (MD-55), pendientes_DER (DER-10), pendientes_CU (caso 23 y ajustes en COM-EVL-DSC y CMP-APR-ODC),
  el glosario y pendientes_prototipo (pendiente 45). Pendientes por rol (D-14) registrado el mismo
  día en pendientes_CU, pendientes_MD y pendientes_prototipo. Los CU extendidos y el diagrama del
  modelo de dominio no se tocaron: se ajustan en la próxima ronda.

## Temas abiertos

- Pantalla propia para el Administrador: por ahora usa el admin de Django; si se hace, comparte la
  pantalla de usuarios (caso 23 de pendientes_CU).
- Plazos que corren mientras no hay Gerente activo (por ejemplo, la vigencia de las cotizaciones):
  a resolver en el CU de baja del Gerente.
- Reparto final de apps entre los dos integrantes.
- Lista cerrada de los casos de uso del 80% y orden de implementación.
- Casos de uso de iniciar sesión, cerrar sesión y recuperar contraseña: no están escritos (ver
  punto 4 de "Siguiente").
- Recuperar contraseña depende del correo, que solo funcionará en Render pago.
- Hacer configurables por `.env` el host, el puerto, el nombre y el usuario de la base local.
