# Disparadores — InfoPonia

Obligaciones que nacen cuando aparece algo en el código: «cuando exista X, hay que hacer Y». Claude Code lo lee cuando
la tarea crea modelos («Límites» de la tarea). Al cerrar una tarea que crea modelos, propone tachar los disparadores que
se cumplieron (con la fecha y el ID de la tarea) y agregar los que nacen (regla M3).

Cada obligación cita su fuente. Las de las cuentas vienen de `docs/casos_de_uso/usuarios.md`, sección «Lo que queda para
más adelante», que sigue la regla de D-04: se agregan cuando se programa la tabla destino.

## Cuando exista Invernadero

1. ~~**Roles del invernadero.**~~ Hecho el 19/11/2026 en MAE-01a (FK nulas en `Invernadero`). Las asociaciones del invernadero con su Agrónomo, Capataz, Vendedor y Técnico se agregan
   en la misma tarea que crea `Invernadero` (D-04). Según D-37, son FK declaradas en `Invernadero` (regla
   A2), no campos en los roles de `core`.
2. **Invernadero del Transportista (R155).** Precondición d, postcondición b y reglas 5 y 7 de USR-ALT-USR;
   postcondición a de USR-MOD-USR; regla 3 de USR-CNS-USR; regla 1 de USR-GST-PRF. Mientras no exista `Invernadero`, el
   Transportista se da de alta sin invernadero (`usuarios.md`, «Lo que queda para más adelante»). Según D-37,
   R155 es una M2M en `Invernadero` (A2). **Pendiente de decidir:** cómo se asigna (MAE-01 lo dejó fuera; sigue abierto). Hay dos opciones: el alta de
   Transportista de `core` muestra el campo por un punto de extensión (A4), o el Transportista se asigna desde el
   invernadero, como los otros cuatro roles; la segunda cambia el caso de uso y va a pendientes_CU.
   La precondición g y la regla 3 de PROD-BAJ-INV (los transportistas inactivos no impiden la baja) se conectan con un
   registrante de impedimentos de la baja (`maestros/extensiones.py`). D-39 ya decidió que manda el caso de uso: solo los
   transportistas activos impiden la baja, aunque la regla 4 de 8.4 del modelo diga «sin importar su estado»; falta corregir
   MD-87 en el modelo, que está en Drive.
3. **Ámbito por invernadero de SEG-13.** `estado.md` lo ubicaba en `core/acceso.py`, pero `core` no puede importar una
   app de negocio (D-23). Va como un punto de extensión de `core` en el que `maestros` registra el ámbito (D-37, regla
   A4). En MAE-01 el alcance vive en `InvernaderoQuerySet.en_alcance_de`; sigue abierto hasta que una pantalla fuera de
   `maestros` lo necesite.
4. **Efectos de la baja de una cuenta con invernaderos a cargo.** Postcondición e de USR-BAJ-USR (queda para el Gerente
   una alerta «invernadero sin {rol}») y regla 4 (antes de confirmar, la baja informa lo que la cuenta tiene asignado).
   La alerta necesita también `Alerta` (ver «Cuando exista la primera notificación»). `Alerta` ya existe (MAE-02a). Va con MAE-02b, por un punto de extensión de `core` (`core/extensiones.py`). Tiene que bloquear en el orden de `docs/patrones/bloqueos.md`, sección «Invernadero» (D-40): la cuenta
   primero y después los invernaderos.

5. ~~**Alerta con su invernadero.**~~ Hecho el 19/11/2026 en MAE-02a (FK `Alerta.invernadero`); la asociación está anotada en `docs/modelo/maestros.md`, pendientes de MD. Texto original: `Alerta` vive en `maestros` y apunta al invernadero con una clave foránea (D-38). La
   crea MAE-02, después de MAE-01. El modelo no tiene esa asociación: anotarlo en pendientes_MD.

## Cuando exista PerfilOrganizacion

1. **Logo y nombre configurables.** El nombre deja de salir de `NOMBRE_ORGANIZACION` (D-25) y el logo deja de ser un
   ícono fijo: los dos se configuran en la organización. En el prototipo de producción: `VIEWS.config`, `CFG` y
   `aplicarMarca`.

## Cuando exista la primera notificación o alerta

Los tres puntos pasan a la tarea de notificaciones en `core` (NOT-01, D-42). La campana suma las alertas no leídas con
`Alerta.objects.para(usuario).activas().no_leidas()` (ya existe, MAE-02a) por un punto de extensión de `core`.

1. **Campana y notificaciones del marco.** Se agregan al marco de `core` (D-25). Diseño: `notifPop` en
   `docs/prototipos/cuentas_y_seguridad.html`; `shell`, `alertas` y `myNotif` en el prototipo de producción.
2. **Pendientes del Gerente (D-14).** Postcondición d de USR-ALT-USR (aviso de resumen al Gerente nuevo con la cantidad
   de pendientes) y postcondición c de USR-BAJ-USR (cantidad de pendientes al dar de baja al Gerente). Sin Gerente
   activo, generar un pendiente no falla y la notificación sin destinatario se omite.
3. **Avisos a las personas asignadas al invernadero.** Postcondición e de PROD-ALT-INV y postcondición c de PROD-MOD-INV: cada
   persona asignada recibe una notificación con el invernadero y lo que recibió (la cantidad de órdenes, mantenimientos,
   contratos y alertas, que sale de `maestros.extensiones.contar_traspaso`). D-38 las dejó sin modelar. Nació en MAE-01b.

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

## Cuando exista SectorProduccion

1. **Sectores del invernadero.** La marca «sin sectores» (`Invernadero.tiene_sectores`, hoy `False`), la capacidad y la
   pestaña de sectores de la ficha (regla 3 de PROD-CNS-INV) y la postcondición b de PROD-BAJ-INV (los sectores pasan a
   inactivos). Nació en MAE-01a. La postcondición b y el log por sector (f) se conectan con `registrar_efecto_de_baja`: el
   registrante audita su propio log por sector.

## Cuando exista SistemaIoT

1. **IoT del invernadero.** `Invernadero.tiene_sistema_iot` (hoy `False`), la alerta y el campo del Técnico (regla 5 de
   PROD-ALT-INV) y la precondición h de PROD-BAJ-INV. Nació en MAE-01a. La precondición h se conecta con
   `registrar_impedimento_de_baja`.

## Cuando exista InsumoInvernadero

1. **Insumos del invernadero.** Postcondición c y precondición f de PROD-BAJ-INV. Nació en MAE-01a. La c (y el log por insumo
   de la f) se conecta con `registrar_efecto_de_baja`; la f, con `registrar_impedimento_de_baja`.

## Cuando exista Lote, OrdenTrabajo o StockCosechado

1. **Baja del invernadero y ficha.** Precondiciones c, d y e de PROD-BAJ-INV y las pestañas de lotes y de cámara de la
   ficha. Se conectan por el punto de extensión `maestros/extensiones.py` (D-37, regla A4), creado en MAE-01b. Se registra con
   `registrar_impedimento_de_baja` en `AppConfig.ready()`. Todo caso de uso que cree algo que impide la baja llama a
   `bloquear_invernadero_activo` antes de crearlo (contrato de D-40 y de `docs/patrones/bloqueos.md`). Nació en MAE-01a.

## Cuando exista Alerta (MAE-02)

1. ~~**Alertas de personal faltante del invernadero.**~~ Hecho el 19/11/2026 en MAE-02a (las `test_d38_…` se reemplazaron). Texto original: Postcondición d de PROD-ALT-INV (una alerta «invernadero sin {rol} activo»
   por cada rol sin asignar); de PROD-MOD-INV, la b (la alerta del rol que se asigna pasa a «resuelta»), la d (alerta si deja
   un rol sin asignar; la del Técnico solo con sistema IoT) y la e (alertas al reactivar); y la e de PROD-BAJ-INV (las alertas
   activas pasan a «resuelta»). Se conectan en `alta_invernadero`, `modificar_invernadero`, `reactivar_invernadero` y
   `baja_invernadero`; sus pruebas `test_d38_…` hay que cambiarlas. Nació en MAE-01b.

## Cuando exista SistemaIoT (alertas)

1. **Alerta del Técnico.** Al registrar o dar de baja el `SistemaIoT` de un invernadero, el caso de uso llama a
   `maestros.servicios.alertas.sincronizar_alertas_de_personal` (la alerta «invernadero sin Técnico activo» solo cuenta con sistema
   IoT, regla 3 de 8.22). Hoy `Invernadero.tiene_sistema_iot()` es `False`. Nació en MAE-02a.

## Cuando exista Hardware, Telemetría, Merma o SolicitudRevisión

1. **Origen de la alerta (restricción C5).** Cada app declara el enlace desde su propia app (`OneToOneField` a `Alerta`, o una tabla de
   enlace para Hardware, R052), en la misma transacción que la alerta; el `origen` de su `TipoAlerta` dice cuál. Contrato en
   `docs/api/alertas.md`, sección 4. Mostrar el origen en una pantalla va por un punto de extensión. Nació en MAE-02a.

## Cuando exista el caso de uso de consulta de alertas (CU-46) o el panel de IoT (CU-41)

1. **Consulta de alertas.** MAE-02b hace CU-46 como último paso; si queda afuera por tiempo, nace acá. CU-41 reutiliza
   `consultar_alertas` (`docs/api/alertas.md`). Nació en MAE-02a.

## Cuando el invernadero ya exista en Neon con datos (D9)

1. **Invernaderos anteriores a MAE-02a.** No tienen alertas de personal hasta su primera modificación con cambios o su
   reactivación; guardar sin cambios no las crea (D-28). Decidir antes de desplegar si hace falta una migración de datos (sería una
   tarea nueva, con D-39 y `docs/patrones/datos_de_migracion.md`). Nació en MAE-02a.

## Cuando exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido

1. **Traspaso por cambio de personal.** Postcondición b de PROD-MOD-INV (MD-60 y MD-62). Cada app registra
   `registrar_traspaso(contar, traspasar)` de `maestros/extensiones.py`: al Capataz, las órdenes a realizar del invernadero;
   al Técnico, los mantenimientos a realizar; al Vendedor, los contratos vigentes o abiertos (regla 8 de 8.21); al Agrónomo,
   las alertas activas (hecho en MAE-02a, directo en `modificar_invernadero`, no por registrante) y, si el saliente sigue activo, se cancelan sus pedidos sin orden de compra con destino a ese
   invernadero y se avisa a los proveedores invitados. `contar` alimenta el aviso de la regla 2 y la notificación de la
   postcondición c. Bloquean sus filas después del invernadero y en orden de id. Nació en MAE-01b.

## Cuando exista un caso de uso que planifique, haga pedidos, asigne stock o reintente entregas

1. **Invernaderos inactivos (regla 4 de PROD-BAJ-INV).** «Un invernadero inactivo no aparece en las planificaciones, en los
   pedidos, en la asignación de stock ni en el reintento diario de las entregas»: cada app que lo programe excluye los
   invernaderos inactivos. Hoy no hay ninguno. Nació en MAE-01b.

## Cuando exista Cliente o CompraVenta

1. **Dirección usada.** Regla 3 de 8.18: una dirección que usa una compra-venta o un detalle de suministro no se modifica
   ni se elimina; se registra una nueva y la anterior pasa a inactiva. `modificar_invernadero` (MAE-01b) crea la dirección nueva al cambiar de
   urbana a rural y borra la anterior con `Direccion.objects.filter(pk=...).delete()`: cuando existan esas clases hay que
   cambiarlo por «pasa a inactiva», o el borrado falla por PROTECT. Nació en MAE-01a.

## Cuando se actualicen los datos de Georef

1. **Carpeta y migración nuevas.** Los CSV de `maestros/datos/georef_2026-11-18/` no se editan: una actualización va en una
   carpeta nueva y una migración nueva (D-39).

## Cuando una migración cargue datos que las pruebas usen

1. **Plan de cuentas de `contabilidad`, categorías de `inventario`, Georef de `maestros`.** Las clases de pruebas que los
   usan heredan del mixin que los carga una vez, los confirma y corre `ANALYZE`. Cómo hacerlo:
   `docs/patrones/datos_de_migracion.md`.
