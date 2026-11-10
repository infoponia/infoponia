# Estado del proyecto — InfoPonia

Última actualización: 09/11/2026. Este archivo se reescribe al final de cada sesión.

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
- Neon reiniciado y migrado; Administradores recreados (06/11/2026).
- Tarea chica: renombradas las 10 pruebas de `core/tests/test_usuario.py` con la convención de
  `CLAUDE.md` (prefijo `test_d<numero>_`), ordenadas por decisión; no se cambió lo que verifican.
- Confirmado que los commits de la rama `feature/usuario-base` no llevan línea de coautor.
- Tarea chica: workflow de GitHub Actions (`.github/workflows/pruebas.yml`) que corre `check`,
  `makemigrations --check --dry-run` y `test` contra PostgreSQL 17 en cada PR y push a main.
- Casos de uso del bloque Cuentas y seguridad (08/11/2026): nueve casos de uso de alto nivel
  (USR-INI-SES a USR-VNC-CTA) y la especificación de seguridad SEG-01 a SEG-19, copiados en
  `docs/casos_de_uso/usuarios.md`. Prototipo HTML del bloque en
  `docs/prototipos/cuentas_y_seguridad.html`. Decisiones D-16 a D-24, todas vigentes.
- Tarea 02: plantilla base con los estilos del prototipo y HTMX 2.0.11 servido desde el repo (D-24);
  inicio y cierre de sesión con email sin distinguir mayúsculas (USR-INI-SES, SEG-01 en parte, SEG-05 a
  SEG-08); inicio de cada cuenta según el rol, con marco de celular para Capataz, Técnico y Transportista;
  acceso según el rol con `rol_requerido` y `LoginRequiredMiddleware` (SEG-13, sin el ámbito por
  invernadero). Fuentes Inter y DM Mono en el repo. Nombre de la organización configurable
  (`NOMBRE_ORGANIZACION`). 24 pruebas nuevas en `core/tests/test_usr_ini_ses.py` (34 en total), sin
  migraciones. Carpeta renombrada a `docs/casos_de_uso`. Verificada a mano. Rama
  `feature/plantilla-front`. Decisiones D-25 y D-26.
- Tarea 03: Registro de auditoría `RegistroAuditoria` (D-22), contraseña temporal (D-18, SEG-04) y
  cambio de contraseña (USR-CMB-CTR, SEG-03, SEG-10) con la pantalla «Elegí tu contraseña». Email en
  minúsculas y único sin distinguir mayúsculas (SEG-01), con migración que falla si hay duplicados. 72
  pruebas en total. Migraciones `0003` y `0004`. Rama `feature/password-temporal`. Decisión D-27.

## En curso

- Nada por ahora.

## Siguiente

1. Después del primer merge con el workflow: en GitHub, Settings → Branches (o Rules), exigir que
   el check de `pruebas.yml` pase para poder mergear a main.
2. Bloque Cuentas y seguridad, una tarea por rama y por PR, en este orden (cada una cita las
   secciones de `docs/casos_de_uso/usuarios.md` que usa):

   | Tarea | Contenido | Necesita |
   |---|---|---|
   | 04 | Usuarios del Gerente: consulta, alta, modificación, restablecer, reactivar y baja (USR-CNS-USR, USR-ALT-USR, USR-MOD-USR y USR-BAJ-USR, SEG-11 y SEG-15), y validación del teléfono (D-21) | — |
   | 05 | Cuentas del Administrador con el mismo flujo y su alcance (D-16); admin de Django deshabilitado en producción (SEG-18); entrada «Cuentas» en el menú lateral del Administrador | — |
   | 06 | Mi perfil y cuentas vinculadas (USR-GST-PRF, USR-VNC-CTA y SEG-09); «Cambiar de cuenta» y «Mi perfil» en el menú de cuenta; pantalla de cambio voluntario de contraseña (USR-CMB-CTR, con contraseña actual), usando el servicio de la tarea 03 | Permiso para modificar `Usuario` y crear el grupo (D-17) |
   | 07 | Foto de perfil (SEG-19) | Proveedor de almacenamiento decidido; permiso para Pillow y `django-storages` (D-20) |
   | 08 | Recuperar contraseña (USR-RCP-CTR, SEG-12) | Proveedor de correo decidido; en desarrollo, backend de consola |
   | 09 | Seguridad de producción: HTTPS, cookies seguras y HSTS (SEG-16); `DEBUG` apagado si falta la variable de entorno | — |

## Registrado el 05/11/2026

- Administrador técnico, un solo Gerente activo y R002 a R006 calculadas: ya están en pendientes_MD
  (MD-55), pendientes_DER (DER-10), pendientes_CU (caso 23 y ajustes en COM-EVL-DSC y CMP-APR-ODC),
  el glosario y pendientes_prototipo (pendiente 45). Pendientes por rol (D-14) registrado el mismo
  día en pendientes_CU, pendientes_MD y pendientes_prototipo. Los CU extendidos y el diagrama del
  modelo de dominio no se tocaron: se ajustan en la próxima ronda.

## Registrado el 08/11/2026

- Resueltos: la pantalla propia del Administrador (D-16); los plazos sin Gerente activo (ninguno de
  sus pendientes tiene plazo: regla 3 de USR-BAJ-USR); los casos de uso de iniciar sesión, cerrar
  sesión y recuperar contraseña (`docs/casos_de_uso/usuarios.md`).
- Las decisiones del bloque también están en los documentos de Drive: pendientes_MD (MD-58 a MD-64),
  pendientes_DER (DER-10, DER-12 y DER-13), pendientes_CU y CU extendidos. El DER se actualiza
  después, a partir del código.

## Temas abiertos

- Reparto final de apps entre los dos integrantes: D-23 fija cuentas en `core` y una app por módulo
  de negocio; faltan los nombres y quién toma cada una.
- Lista cerrada de los casos de uso del 80% y orden de implementación.
- Recuperar contraseña depende del correo, que solo funcionará en Render pago. Falta decidir el
  proveedor de correo (tarea 08).
- Proveedor del almacenamiento de objetos para la foto de perfil (tarea 07).
- Ingreso con Google: trabajo futuro, fuera de este bloque.
- Hacer configurables por `.env` el host, el puerto, el nombre y el usuario de la base local.
- `requirements.txt` está guardado en UTF-16 (probablemente generado con `pip freeze >` desde
  PowerShell): pip lo lee, pero Git lo muestra como texto ilegible. Convertirlo a UTF-8.
- Logo de la organización: hoy es un ícono fijo; será una imagen configurable junto con el nombre, en la
  configuración de la organización.
- Campana y notificaciones del marco: se agregan cuando exista el primer aviso (por ejemplo, el resumen
  de pendientes del Gerente, D-14). El prototipo ya tiene el diseño (`notifPop`).
- Ámbito por invernadero de SEG-13: se agrega en `core/acceso.py` cuando exista `Invernadero`.
