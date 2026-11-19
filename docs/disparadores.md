# Disparadores — InfoPonia

Obligaciones que nacen cuando aparece algo en el código: «cuando exista X, hay que hacer Y». Claude Code lo lee cuando
la tarea crea modelos («Límites» de la tarea). Al cerrar una tarea que crea modelos, propone tachar los disparadores que
se cumplieron (con la fecha y el ID de la tarea) y agregar los que nacen (regla M3).

Cada obligación cita su fuente. Las de las cuentas vienen de `docs/casos_de_uso/usuarios.md`, sección «Lo que queda para
más adelante», que sigue la regla de D-04: se agregan cuando se programa la tabla destino.

## Cuando exista Invernadero

1. **Roles del invernadero.** Las asociaciones del invernadero con su Agrónomo, Capataz, Vendedor y Técnico se agregan
   en la misma tarea que crea `Invernadero` (D-04). Según D-37, son FK declaradas en `Invernadero` (regla
   A2), no campos en los roles de `core`.
2. **Invernadero del Transportista (R155).** Precondición d, postcondición b y reglas 5 y 7 de USR-ALT-USR;
   postcondición a de USR-MOD-USR; regla 3 de USR-CNS-USR; regla 1 de USR-GST-PRF. Mientras no exista `Invernadero`, el
   Transportista se da de alta sin invernadero (`usuarios.md`, «Lo que queda para más adelante»). Según D-37,
   R155 es una M2M en `Invernadero` (A2). **Pendiente de decidir:** cómo se asigna. Hay dos opciones: el alta de
   Transportista de `core` muestra el campo por un punto de extensión (A4), o el Transportista se asigna desde el
   invernadero, como los otros cuatro roles; la segunda cambia el caso de uso y va a pendientes_CU.
3. **Ámbito por invernadero de SEG-13.** `estado.md` lo ubicaba en `core/acceso.py`, pero `core` no puede importar una
   app de negocio (D-23). Va como un punto de extensión de `core` en el que `maestros` registra el ámbito (D-37, regla
   A4).
4. **Efectos de la baja de una cuenta con invernaderos a cargo.** Postcondición e de USR-BAJ-USR (queda para el Gerente
   una alerta «invernadero sin {rol}») y regla 4 (antes de confirmar, la baja informa lo que la cuenta tiene asignado).
   La alerta necesita también `Alerta` (ver «Cuando exista la primera notificación»).

5. **Alerta con su invernadero.** `Alerta` vive en `maestros` y apunta al invernadero con una clave foránea (D-38). La
   crea MAE-02, después de MAE-01. El modelo no tiene esa asociación: anotarlo en pendientes_MD.

## Cuando exista PerfilOrganizacion

1. **Logo y nombre configurables.** El nombre deja de salir de `NOMBRE_ORGANIZACION` (D-25) y el logo deja de ser un
   ícono fijo: los dos se configuran en la organización. En el prototipo de producción: `VIEWS.config`, `CFG` y
   `aplicarMarca`.

## Cuando exista la primera notificación o alerta

1. **Campana y notificaciones del marco.** Se agregan al marco de `core` (D-25). Diseño: `notifPop` en
   `docs/prototipos/cuentas_y_seguridad.html`; `shell`, `alertas` y `myNotif` en el prototipo de producción.
2. **Pendientes del Gerente (D-14).** Postcondición d de USR-ALT-USR (aviso de resumen al Gerente nuevo con la cantidad
   de pendientes) y postcondición c de USR-BAJ-USR (cantidad de pendientes al dar de baja al Gerente). Sin Gerente
   activo, generar un pendiente no falla y la notificación sin destinatario se omite.

## Cuando exista Pedido

1. **Baja de un Agrónomo.** Postcondición f de USR-BAJ-USR: se cancelan sus pedidos sin orden de compra generada y se
   avisa. Regla 4: la baja lo informa antes de confirmar.

## Cuando exista Entrega

1. **Baja de un Transportista.** Postcondición g de USR-BAJ-USR: sus entregas a realizar quedan sin transportista. Regla
   4: la baja lo informa antes de confirmar.

## Cuando exista Cosecha

1. **Pantalla de concretar cosecha.** El prototipo de producción deriva esa pantalla a otro archivo (InfoPonia11), que
   no está en el repo. Hay que traerlo a `docs/prototipos/produccion/` antes de escribir esa tarea (D-24).

## Cuando un módulo de negocio audite por primera vez

1. **Formato y clasificación (D-36).** Detalle con «cambios» y «datos», referencias con `referencia()`, nombres visibles
   en `RegistroAuditoria.ETIQUETAS` y cada acción nueva en `ACCIONES_DE_NEGOCIO`. Cómo hacerlo: `docs/patrones/auditoria.md`.
