# NOT-01 · Notificaciones y campana (D-42)

Estado: pendiente | App: core (toca servicios de `core` y de `maestros`) | Rama: feature/not-01-notificaciones | Ronda: Producción 1

Depende de: UI-01 (si no está hecha, frená: el marco y la identidad en `core/extensiones.py` los deja ella). MAE-02a y MAE-02b ya están mergeadas

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

## Casos de uso incluidos

No es un caso de uso: es una característica del sistema (D-38, D-42) que cierra postcondiciones de aviso de casos de uso ya
hechos. Los extractos con sus textos exactos:

| Código | Postcondición que se cierra | Extracto | Marcas |
|---|---|---|---|
| USR-ALT-USR | d: al alta de un Gerente, una única notificación al nuevo Gerente con la cantidad de pendientes | docs/casos_de_uso/usuarios.md | — |
| USR-BAJ-USR | c: al dar de baja al Gerente, la pantalla de la baja informa al Administrador cuántos pendientes quedan | docs/casos_de_uso/usuarios.md | No es una notificación: es un texto de la pantalla |
| PROD-ALT-INV | e: cada persona asignada recibe una notificación de que quedó a cargo del invernadero | docs/casos_de_uso/maestros/invernaderos.md | — |
| PROD-MOD-INV | c: cada persona que queda a cargo (nueva) recibe la notificación, con lo que recibe (regla 2) | docs/casos_de_uso/maestros/invernaderos.md | — |

## Leer

- Decisiones: D-14, D-25, D-36, D-38, D-41, D-42, D-47, D-48 (solo la parte de `core/extensiones.py`)
- API: docs/api/notificaciones.md (es el contrato: implementalo tal cual)
- Casos de uso: los de la tabla, solo las postcondiciones indicadas y las reglas que las nombran (USR-ALT-USR regla de rol
  Gerente; USR-BAJ-USR reglas 3 y 4; PROD-MOD-INV regla 2)
- Modelo: docs/modelo/maestros.md — Alerta (solo atributos y reglas; la campana usa `Alerta.objects.para(usuario)`)
- Patrones: docs/patrones/auditoria.md (para no auditar las notificaciones)
- Pantallas: docs/prototipos/produccion/ — `shell`, `alertas`, `myNotif`; docs/prototipos/cuentas_y_seguridad.html — `notifPop`
  (solo guía visual)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código: core/servicios.py (`alta_usuario`, `baja_usuario`), maestros/servicios/invernaderos.py (`alta_invernadero`,
  `modificar_invernadero`, `_aviso_de_personal`), maestros/extensiones.py (`contar_traspaso`)

## Límites

- Crea modelos: `core.Notificacion` → revisá docs/disparadores.md («Cuando exista la primera notificación o alerta»)
- Migraciones: solo nuevas, en `core` (una de esquema para `Notificacion`). Ninguna en `maestros`
- Archivos nuevos: `core/notificaciones.py`, `core/templates/core/_campana.html` (y sus fragmentos), `core/tests/test_notificaciones.py`
- Permitido fuera de `core`: `maestros/apps.py` (registrar la fuente de alertas y el contador de pendientes),
  `maestros/servicios/invernaderos.py` (las llamadas a `notificar_a_varios`), `maestros/tests/test_prod_alt_inv.py` y
  `test_prod_mod_inv.py` (pruebas de las postcondiciones e y c), `core/extensiones.py` (existe desde MAE-02b y UI-01 le sumó la identidad: se le agregan
  `registrar_fuente_de_alertas`, `ItemDeAlerta` y `registrar_contador_de_pendientes`)
- Dependencias nuevas: ninguna
- Fuera de alcance: marcar una alerta como leída (ya existe: `abrir_alerta`, MAE-02b), pantalla de alertas (MAE-02c), historial completo de
  notificaciones, envío por correo, notificaciones de las apps de producción (las escribe cada tarea con esta API), logo

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelo y migración.** `Notificacion` (D-42) con índice por `(destinatario, fecha_hora)` y `Meta.ordering` de la más
   reciente a la más antigua. Pruebas: `core/tests/test_notificaciones.py` — `NotificacionModeloTests` (valores por defecto,
   orden, `leida` falsa al crear).
2. **API.** `notificar`, `notificar_al_gerente`, `notificar_a_varios`, `de_la_cuenta`, `marcar_vistas` y `pendientes_del_gerente`,
   con las reglas de `docs/api/notificaciones.md`: sin Gerente activo no falla, sin repetir cuentas, sin `None`, sin la cuenta
   excluida, título y detalle con contenido y dentro del largo (`ValueError`), `marcar_vistas` ignora las ajenas. Pruebas:
   `NotificacionApiTests`, incluido que dentro de `transaction.atomic()` que falla no queda nada.
3. **Puntos de extensión.** En `core/extensiones.py`: `registrar_fuente_de_alertas`, `ItemDeAlerta`, `alertas_para(usuario)` (junta
   las fuentes, ordena por severidad crítica, advertencia, informativa, sin perder el orden de cada una) y
   `registrar_contador_de_pendientes`. Pruebas: `ExtensionesCampanaTests` con registrantes falsos.
4. **Campana.** En el marco (el lugar que dejó UI-01): botón con punto rojo (alerta activa no leída o notificación sin leer) y
   el panel de dos pestañas, con el aspecto del prototipo (D-47). Con HTMX: abrir trae el panel (`GET core:campana`) y cerrarlo
   hace `POST core:campana_vista` con los ids de las notificaciones mostradas, que quedan leídas. Sin JavaScript, el botón es un
   enlace a `core:campana` como página completa. Para los roles de campo (celular) el botón mide 44 px. Pruebas:
   `CampanaVistaTests` (solo ve las suyas; el orden; el contador; el punto; que cerrar marca leídas solo las mostradas; que otro
   usuario no puede marcar las ajenas; sin sesión redirige al inicio de sesión).
5. **Avisos de `core`.** USR-ALT-USR d: dentro de `alta_usuario`, si el rol es Gerente, una notificación al nuevo Gerente con el
   total y el detalle de `pendientes_del_gerente()` («No tiene pendientes» si es 0). USR-BAJ-USR c: la pantalla de la baja del
   Gerente muestra el total y el detalle. **La ventana de baja ya existe** (MAE-02b, D-43: `core/templates/core/usuarios/_ventana_confirmar.html`
   y `asignaciones_de_cuenta` de `core/extensiones.py`): leé D-43 y agregá el texto de pendientes ahí, sin duplicar la ventana ni cambiar
   lo que ya lista. Pruebas: se agregan a los archivos existentes de esos casos de uso
   (`test_post_d_…` y `test_post_c_…`); sin Gerente activo la notificación se omite y el alta no falla (D-14).
6. **Fuentes de `maestros`.** En `MaestrosConfig.ready()` registrar la fuente de alertas (las activas de
   `Alerta.objects.para(usuario)`, con severidad desde el tipo registrado, `url` a la ficha del invernadero, `leida` según
   `estado_lectura_alerta`) y el contador de pendientes del Gerente (alertas activas con `para_gerente=True`). Pruebas:
   `maestros/tests/test_campana_alertas.py`.
7. **Avisos de invernadero.** PROD-ALT-INV e y PROD-MOD-INV c: en las transacciones de `alta_invernadero` y
   `modificar_invernadero`, `notificar_a_varios` a cada persona asignada (en la modificación, solo a las que **quedan a cargo**
   en este cambio), con el texto de D-42 y, en la modificación, lo que recibe (`contar_traspaso`, ya armado por
   `_aviso_de_personal`). Nunca al actor. Pruebas: `test_post_e_…` y `test_post_c_…` en los archivos de esos casos de uso;
   incluir que una modificación sin cambios no notifica (D-28) y que la persona saliente no recibe nada.
8. **Cierre de documentación.** Actualizar los comentarios y docstrings que dicen «las notificaciones no existen todavía» o
   «tarea aparte en core, D-42» (en `core/servicios.py` y `maestros/servicios/invernaderos.py`), y marcar cerrada la sección
   «Cuando exista la primera notificación o alerta» de `docs/disparadores.md` y las filas de `docs/tareas/README.md` y de
   `docs/tareas/ronda_produccion_1.md`.

Si el tiempo apremia, lo último que se recorta es el paso 7 (se anota como disparador); los pasos 1 a 6 no se recortan porque
MAE-03 y PRD-01 usan la API.

## Hecho cuando

- La campana funciona para todos los roles, con y sin JavaScript, y marca como leídas solo las notificaciones mostradas al cerrar.
- Las cuatro postcondiciones de la tabla están implementadas y probadas; ninguna se audita.
- `docs/api/notificaciones.md` coincide con el código (si hubo que cambiar algo, se cambió el documento y se avisó).
- Pruebas: `core/tests/test_notificaciones.py` y `maestros/tests/test_campana_alertas.py`, más las de las postcondiciones.
- Comando de pruebas (suites completas de core y maestros, porque se tocan servicios de ambos):
  python manage.py test core maestros --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test core maestros --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva: `python manage.py migrate`. Cuentas: Gerente, Administrador, Agrónomo, Capataz.

1. Con el Gerente, dar de alta un invernadero con Agrónomo y Capataz. Con cada una de esas cuentas: la campana tiene punto rojo y
   «Notificaciones (1 sin leer)»; cerrar el panel deja la notificación leída y el punto desaparece.
2. «Modificar» ese invernadero y cambiar el Agrónomo: el nuevo recibe el aviso con lo que recibe; el anterior no recibe nada.
   Guardar sin cambiar nada no genera avisos.
3. Con el Administrador, dar de baja al Gerente: la pantalla de la baja muestra cuántos pendientes quedan. Dar de alta
   uno nuevo: tiene una notificación con los pendientes (las alertas activas para el Gerente).
4. Con un invernadero sin Capataz, el Gerente ve en «Alertas» la de «sin Capataz» con su severidad y el enlace a la ficha.
5. Sin JavaScript, el botón de la campana abre la página completa y se ven las dos pestañas.
6. A 375 px el panel entra en la pantalla y el botón mide al menos 44 px en los roles de campo.

## Cierre (la completa Claude Code al cerrar)
