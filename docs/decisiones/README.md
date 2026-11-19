# Decisiones — InfoPonia

Una decisión por archivo (`D-NN.md`), copiada sin cambios de la bitácora original `docs/decisiones.md`; solo se
actualiza la línea «Estado» cuando otra decisión la reemplaza o la completa. Se citan por su
ID («D-36»), sin ruta. Las entradas no se borran ni se reescriben: si una decisión cambia, se agrega una nueva que la
reemplaza y se anota en el «Estado» de la anterior.

Este índice no se lee en cada sesión. Sirve para buscar una decisión que la tarea no nombra. Muchas veces alcanza con
«Qué fija» y no hace falta abrir el archivo.

Las menciones a `docs/estado.md` dentro de una decisión se refieren al estado del día en que se tomó. Hoy ese contenido
está en `docs/historial.md`, `docs/revisiones_pendientes.md`, `docs/temas_abiertos.md` o `docs/tareas/`.

## Formato de una decisión nueva

Archivo `docs/decisiones/D-NN.md`, con la próxima libre (hoy **D-40**):

```
## D-NN — Título

- Fecha:
- Decidió:
- Antes:
- Decisión:
- Por qué:
- Fuentes:
- Consecuencias:
- Estado: vigente / propuesta / reemplazada por D-NN / reemplazada en parte por D-NN
```

Y una fila en la tabla de abajo.

Módulos: transversal, cuentas, auditoría, interfaz, maestros, inventario, producción, compras, comercial,
iot, contabilidad.

## Índice

| ID | Título | Módulo | Estado | Qué fija | Leer si... |
|---|---|---|---|---|---|
| D-01 | Modelo de usuario propio con herencia multi-tabla | cuentas | vigente | `Usuario` hereda de `AbstractUser`; los seis roles heredan de `Usuario` (multi-tabla) y una cuenta tiene un solo rol | tocás `Usuario` o un rol |
| D-02 | Atributos comunes de los roles en Usuario | cuentas | vigente | Mapeo nombreX → `first_name`, estadoX → `is_active`, etc.; las tablas de rol solo guardan asociaciones | agregás un campo a un rol |
| D-03 | Inicio de sesión con email | cuentas | vigente | Se entra con el email, único; no hay `username` | — |
| D-04 | Asociaciones de los roles se agregan cuando existen sus tablas destino | transversal | vigente; reemplazada en parte por D-37 | La FK hacia una tabla nueva se agrega, en su propia migración, al crear esa tabla | agregás una relación con un rol |
| D-05 | Nombres de campos en snake_case conservando el sufijo | transversal | vigente | `nombre_invernadero`, no `nombre`; las correcciones de tipeo del diagrama se registran | creás modelos |
| D-06 | Clave primaria automática de Django | transversal | vigente | `id` automático, equivalente a idX del diagrama | creás modelos |
| D-07 | Versión vigente del modelo de dominio | transversal | vigente | Se programa desde la ronda 20; si el diagrama y el texto no coinciden, manda el texto | el extracto del modelo y el diagrama difieren |
| D-08 | Significado de la asociación «contacto» (R002 a R006) | cuentas | vigente | «Contacto» es el Gerente que supervisa en ese momento | — |
| D-09 | Un solo Gerente activo; «contacto» se calcula | cuentas | vigente | Unicidad parcial en la base; R002 a R006 no se guardan: el contacto es el Gerente activo | necesitás «el Gerente» desde un módulo |
| D-10 | Administrador técnico, limitado a gestionar al Gerente | cuentas | reemplazada en parte por D-16 | Administrador = superusuario sin `rol`; no participa en casos de uso de negocio | — |
| D-11 | El rol de un usuario no se modifica | cuentas | vigente | El rol no cambia nunca; para cambiarlo, baja y alta | — |
| D-12 | Puede haber más de un Administrador | cuentas | vigente | Sin unicidad sobre los superusuarios | — |
| D-13 | El reemplazo del Gerente son dos operaciones | cuentas | vigente | Baja del actual y alta del nuevo; entre ambas no hay Gerente activo y el sistema sigue andando | un caso de uso necesita al Gerente |
| D-14 | Los pendientes del Gerente se definen por estado y rol, no por persona | transversal | vigente | Lo que espera al Gerente queda en su estado; sin Gerente activo no falla y la notificación se omite | un caso de uso deja algo pendiente del Gerente |
| D-15 | Tipo del campo telefono | cuentas | vigente; completada por D-21; largo reemplazado por D-28 | `CharField`, hoy de 25 | — |
| D-16 | Alcance del Administrador y pantallas propias | cuentas | vigente | Qué cuentas gestiona el Administrador; los Administradores se crean por consola | — |
| D-17 | Cuentas vinculadas en un grupo | cuentas | vigente | Una persona con varias cuentas: grupo de cuentas vinculadas, transitivo | — |
| D-18 | Contraseña temporal | cuentas | vigente; reemplazada en parte por D-35 | 12 caracteres sin ambiguos, se muestra una vez, vence a los 7 días | — |
| D-19 | Sesión e identificación | cuentas | vigente | Sesión de navegador, mensaje genérico, sin tope de intentos (ver USR-09) | — |
| D-20 | Foto de perfil en almacenamiento de objetos | cuentas | vigente | JPG/PNG/WebP, recodificada a 256 px, guardada con `django-storages` en producción | trabajás USR-07 |
| D-21 | Formato del teléfono | transversal | vigente | Dígitos, espacios y `+ - ( )`, entre 8 y 15 dígitos | un modelo de negocio tiene teléfono |
| D-22 | Registro de auditoría | auditoría | vigente; completada por D-36 | `RegistroAuditoria` de solo agregar, escrito por el servicio dentro de la misma transacción | tu caso de uso audita |
| D-23 | Ubicación del código: cuentas en core, una app por módulo de negocio | transversal | vigente; completada por D-37 | `core` nunca depende de una app de negocio | creás una app o importás entre apps |
| D-24 | Pantallas del bloque a partir del prototipo HTML | interfaz | vigente | Plantillas + HTMX en el repo; desplegables propios, nunca el `<select>` nativo | hacés pantallas |
| D-25 | Convenciones del bloque Cuentas y seguridad (tarea 02) | transversal | vigente | Caso de uso sin servicio → `<CodigoCu>ReglasTests`; pruebas `test_seg<nn>_`; toda pantalla exige sesión; el menú muestra solo lo que existe; celular para Capataz, Técnico y Transportista | hacés pantallas o pruebas de un caso de uso sin servicio |
| D-26 | Archivos de terceros incluidos en el repo | interfaz | vigente | HTMX y fuentes Inter y DM Mono en `core/static/core/`, con su verificación | — |
| D-27 | Contraseña temporal, auditoría y email: cómo se implementan (tarea 03) | cuentas | vigente; reemplazada en parte por D-35 y D-36 | Acción del propio sistema → sin usuario y rol «infoponia»; un detalle con contraseña se rechaza | tu caso de uso lo dispara el sistema |
| D-28 | Usuarios del Gerente: alcance, teléfono y pantallas (tarea 04) | cuentas | vigente; formato de auditoría reemplazado por D-36 | El alcance vive en un solo queryset por modelo; fuera de alcance → 403, inexistente → 404 | tu caso de uso tiene alcance por usuario |
| D-29 | Convenciones de interfaz del sistema | interfaz | vigente; actualizada el 14 y el 16/11/2026 | Avisos breves, foco, botón secundario, `static_v`, `data-enviando`, errores de HTMX, vuelta a la pantalla pedida | hacés pantallas (resumen en `.claude/rules/interfaz.md`) |
| D-30 | Cuentas del Administrador: SEG-15, pantallas y admin de Django (tarea 05) | cuentas | vigente; bloqueos pasados a `FOR NO KEY UPDATE` por D-32 | Orden de bloqueo grupo → quien actúa → fila; restricción de la base como respaldo, traducida; ningún botón lleva a un 403 | tu servicio cuida un invariante entre filas (ver `docs/patrones/bloqueos.md`) |
| D-31 | Mi perfil y cambio voluntario de contraseña (tarea 06a) | cuentas | vigente | Mi perfil de solo lectura; cambio de contraseña dentro de Mi perfil | — |
| D-32 | Cuentas vinculadas: grupo, orden de verificaciones y bloqueos (tarea 06b) | cuentas | vigente; actualizada el 14/11/2026 | `select_for_update(no_key=True)` en todo bloqueo; verificar lo lento antes de bloquear y revalidar después; rechazar «cambio_simultaneo» en vez de reintentar; `correr_a_la_vez` con `primera` | tu servicio bloquea filas o probás concurrencia |
| D-33 | Envío de correo: Gmail por SMTP y una sola fuente de verdad (tarea 08) | transversal | vigente | `CORREO_CONFIGURADO` es la única fuente de verdad; el correo va fuera de la transacción | tu caso de uso manda correos |
| D-34 | Recuperar contraseña por correo: cómo se implementa (tarea 08) | cuentas | vigente; ver D-35 y D-36 | Token de un solo uso: bloquear y revalidar después de bloquear | — |
| D-35 | Invitación por correo como forma de primer acceso (tarea 08b) | cuentas | vigente; formato de auditoría reemplazado por D-36 | Invitación pendiente = contraseña no utilizable + `fecha_invitacion`; envío fuera de la transacción | — |
| D-36 | Formato obligatorio del detalle de la auditoría y consulta del registro (tarea AUD-CNS-REG) | auditoría | vigente | Detalle con «cambios» y «datos», referencias con `referencia()`, afectados con texto; toda acción nueva se clasifica en `ACCIONES_DE_CUENTAS` o `ACCIONES_DE_NEGOCIO` | tu caso de uso audita (ver `docs/patrones/auditoria.md`) |
| D-37 | Reparto de apps y sentido de las dependencias | transversal | vigente; reemplazada en parte por D-38 | Apps por niveles: `core`, `contabilidad`, `maestros` (con organización, configuración y geografía), `inventario`, `produccion`, `compras` y `comercial`, `iot`; una app solo importa de las de nivel menor; la FK va en la app de nivel mayor; servicios en un paquete por entidad | creás una app, un modelo con FK a otra app o un caso de uso que toca varias apps |
| D-38 | Alerta vive en maestros, no en core | maestros | vigente | `Alerta` va en `maestros` con FK al invernadero; las notificaciones no se modelan; el invernadero se programa antes que la alerta | tu caso de uso genera o resuelve alertas |
| D-39 | Invernadero, dirección y Georef en maestros (tarea MAE-01) | maestros | vigente | Georef recortado en CSV del repo y cargado por migración (3923 localidades); dirección multi-tabla; acciones de auditoría `<acción>_<entidad>` y `accion` de 50 caracteres; validadores de formato y de contenido de los textos (`maestros/validadores.py`); pruebas con datos de migración: mixin `ConGeoref` y `ANALYZE` | creás un modelo o una migración de datos en `maestros`, una acción de auditoría nueva o pruebas que usan datos de una migración (ver `docs/patrones/datos_de_migracion.md`) |
