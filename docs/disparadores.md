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
4. ~~**Efectos de la baja de una cuenta con invernaderos a cargo.**~~ Hecho el 19/11/2026 en MAE-02b, por los puntos de extensión de
   `core/extensiones.py` (D-43). Texto original: postcondición e de USR-BAJ-USR (queda para el Gerente una alerta «invernadero sin
   {rol}») y regla 4 (antes de confirmar, la baja informa lo que la cuenta tiene asignado). Tiene que bloquear en el orden de
   `docs/patrones/bloqueos.md`, sección «Invernadero» (D-40): la cuenta primero y después los invernaderos.

5. ~~**Alerta con su invernadero.**~~ Hecho el 19/11/2026 en MAE-02a (FK `Alerta.invernadero`); la asociación está anotada en `docs/modelo/maestros.md`, pendientes de MD. Texto original: `Alerta` vive en `maestros` y apunta al invernadero con una clave foránea (D-38). La
   crea MAE-02, después de MAE-01. El modelo no tiene esa asociación: anotarlo en pendientes_MD.

## Cuando exista PerfilOrganizacion

1. ~~**Nombre y color configurables (MAE-04, D-48).**~~ Hecho el 21/11/2026 en MAE-04 (maestros/servicios/perfil.py, registrado en MaestrosConfig.ready()). **Sigue abierto: el logo** (fuera de la ronda, D-45). Texto original: El nombre sale del perfil, por el punto de
   extensión de `core` (D-48); `NOMBRE_ORGANIZACION` (D-25) queda como valor por defecto. El logo deja de ser un ícono fijo cuando el almacenamiento esté resuelto (USR-07, D-20); mientras tanto la
   organización queda sin logo. En el prototipo de producción: `VIEWS.config`, `CFG` y `aplicarMarca`.

## Cuando exista la primera notificación o alerta

Los tres puntos los cerró NOT-01 (20/11/2026, D-42). La campana suma las alertas no leídas con
`Alerta.objects.para(usuario).activas().no_leidas()` (ya existe, MAE-02a) por un punto de extensión de `core`
(`registrar_fuente_de_alertas`). Los dos puntos que siguen nacieron al cerrarla.

1. ~~**Campana y notificaciones del marco.**~~ Hecho el 20/11/2026 en NOT-01 (`core/extensiones.py`, `core/notificaciones.py`, `core/views.py`,
   `core/templates/core/_campana*.html` y `campana.html`; el Administrador no la tiene). Texto original: Se agregan al marco de `core` (D-25).
   Diseño: `notifPop` en `docs/prototipos/cuentas_y_seguridad.html`; `shell`, `alertas` y `myNotif` en el prototipo de producción.
2. ~~**Pendientes del Gerente (D-14).**~~ Hecho el 20/11/2026 en NOT-01 (`alta_usuario` avisa al Gerente nuevo; la ventana de baja del
   Gerente muestra el total y el detalle; `registrar_contador_de_pendientes` y `pendientes_del_gerente`). Texto original: Postcondición d de
   USR-ALT-USR (aviso de resumen al Gerente nuevo con la cantidad de pendientes) y postcondición c de USR-BAJ-USR (cantidad de pendientes
   al dar de baja al Gerente). Sin Gerente activo, generar un pendiente no falla y la notificación sin destinatario se omite.
3. ~~**Avisos a las personas asignadas al invernadero.**~~ Hecho el 20/11/2026 en NOT-01 (`alta_invernadero` y `modificar_invernadero` llaman
   a `notificar_a_varios`; en la modificación, solo a quien queda a cargo, con lo que recibe). Texto original: Postcondición e de
   PROD-ALT-INV y postcondición c de PROD-MOD-INV: cada persona asignada recibe una notificación con el invernadero y lo que recibió (la
   cantidad de órdenes, mantenimientos, contratos y alertas, que sale de `maestros.extensiones.contar_traspaso`). D-38 las dejó sin
   modelar. Nació en MAE-01b.
4. **Abrir una alerta desde la campana (MAE-02c).** El enlace de cada alerta de la campana lleva a la ficha del invernadero y no llama a
   `abrir_alerta`: la alerta sigue «no leída» y el punto rojo del Gerente (o del Agrónomo) no se apaga. Cuando exista la pantalla de
   consulta de alertas (CU-46, MAE-02c), la campana tiene que llevar a ese detalle (que sí llama a `abrir_alerta`), o la
   `ItemDeAlerta.url` de `maestros.servicios.invernaderos.items_de_campana` tiene que apuntar a él. Va junto con el pendiente de
   pendientes_CU de la sección de CU-46 (abrir la alerta la marca «leída», regla 7 de 8.18). Nació en NOT-01.
5. **Lo que espera una resolución del Gerente.** Cada app que cree algo que queda esperando al Gerente (órdenes de compra por aprobar,
   solicitudes de revisión; D-14) registra su contador en `AppConfig.ready()` con
   `core.extensiones.registrar_contador_de_pendientes(funcion)`, con `funcion() -> list[tuple[str, int]]` (descripción y cantidad; sin
   nada pendiente, lista vacía). Así el aviso al Gerente nuevo (`alta_usuario`) y la ventana de baja del Gerente los cuentan sin tocar
   `core`. Si además quien genera algo y no hay Gerente activo debe avisarle a quien lo genera que quedará pendiente (D-14), lo hace
   con `core.notificaciones.notificar` y no con `notificar_al_gerente`, que en ese caso no hace nada. Hoy solo `maestros` registra el suyo
   (alertas activas para el Gerente). Nació en NOT-01.


## Cuando exista Pedido

1. **Baja de un Agrónomo.** Postcondición f de USR-BAJ-USR: se cancelan sus pedidos sin orden de compra generada y se avisa. Regla 4:
   la baja lo informa antes de confirmar. Se conecta con `registrar_efecto_de_baja_de_cuenta` y `registrar_asignaciones_de_cuenta` de
   `core/extensiones.py` (D-43); bloquea sus filas después del invernadero y en orden de id.

## Cuando exista Entrega

1. **Baja de un Transportista.** Postcondición g de USR-BAJ-USR: sus entregas a realizar quedan sin transportista. Regla 4: la baja
   lo informa antes de confirmar. Se conecta con `registrar_efecto_de_baja_de_cuenta` y `registrar_asignaciones_de_cuenta` de
   `core/extensiones.py` (D-43).

## Cuando exista Cosecha

1. **Pantalla de concretar cosecha.** El prototipo de producción deriva esa pantalla a otro archivo (InfoPonia11), que
   no está en el repo. Hay que traerlo a `docs/prototipos/produccion/` antes de escribir esa tarea (D-24).

## Cuando un módulo de negocio audite por primera vez

1. **Formato y clasificación (D-36).** Detalle con «cambios» y «datos», referencias con `referencia()`, nombres visibles
   en `RegistroAuditoria.ETIQUETAS` y cada acción nueva en `ACCIONES_DE_NEGOCIO`. Cómo hacerlo: `docs/patrones/auditoria.md`.

## Cuando exista SectorProduccion

1. ~~**Sectores del invernadero.**~~ Hecho el 20/11/2026 en MAE-03 (`Invernadero.tiene_sectores` mira los sectores activos o fuera de servicio, pestaña «Sectores» y tarjeta «Capacidad» de la ficha, y la baja del invernadero pasa sus sectores a inactivos con un log por sector, por `registrar_efecto_de_baja`). Texto original: la marca «sin sectores» (`Invernadero.tiene_sectores`, hoy `False`), la capacidad y la pestaña de sectores de la ficha (regla 3 de PROD-CNS-INV) y la postcondición b de PROD-BAJ-INV (los sectores pasan a inactivos). Nació en MAE-01a.


## Cuando exista una ocupación de sector, una variedad con semilla o un hardware (registrantes de los puntos de extensión de MAE-03)

MAE-03 crea los puntos de extensión de sectores y cultivos (`docs/api/extensiones_de_maestros.md`) **sin registrantes**. Cada tarea
que crea lo que falta se registra en el `AppConfig.ready()` de su app y prueba su registrante:

1. **PRD-01 (`produccion`):** `registrar_agujeros_de_sector` (ocupados y comprometidos), `registrar_impedimento_de_baja_de_sector`
   (agujeros ocupados y comprometidos, con los lotes y órdenes), `registrar_contenido_de_sector` (lotes y órdenes),
   `registrar_perfil_de_sector` y `registrar_aviso_de_cambio_de_tipo` (lotes que deben pasar por la etapa y siembras a realizar).
   Al reservar agujeros usa `bloquear_invernadero_activo` y `bloquear_sectores`.
2. **PRD-04 (`produccion`):** `registrar_efecto_de_vuelta_a_servicio` (cierra el registro «Fuera de servicio» y escribe la bitácora),
   `registrar_efecto_de_baja_de_sector` (punto nuevo de `maestros`, D-51 punto 7) y `registrar_efecto_de_baja` (cierra los registros abiertos al dar de baja el invernadero; en el lote 4 se había dicho que no registraba nada)
   y el caso de uso PROD-PNR-FDS, que es el que produce el estado «fuera de servicio». También el Inicio del Agrónomo, como sección registrada
   con `registrar_seccion_de_inicio` de `core/extensiones.py` (D-43; la alerta de insumos y de merma del prototipo salen de ahí).
3. **INV-03 (`inventario`):** `registrar_semillas_de_cultivo` (contar y renombrar con su log `modificacion_semilla`) y
   `registrar_uso_de_cultivo` (la semilla habilitada más los lotes activos que le informa `produccion`, ver el punto siguiente).
   Además agrega a `Variedad` las columnas que faltan (rangos, postcosecha y peso en gramos). `EtapaProductiva` **no** tiene estado
   (opción A, 19/11/2026): no hay nada que agregar ahí.
4. **Módulo IoT (`iot`) — hecho en la documentación el 20/11/2026, se implementa en IOT-02:** `registrar_impedimento_de_baja_de_sector` con `hardware_activo` (códigos y textos de PROD-BAJ-SCT, regla 3)
   y `registrar_contenido_de_sector` con el hardware.

## Cuando exista una ocupación de sector, una variedad con semilla o un hardware (registrantes de los puntos de extensión de MAE-03)

MAE-03 creó los puntos de extensión de sectores y cultivos (`docs/api/extensiones_de_maestros.md`) el 20/11/2026 **sin registrantes** (probados con registrantes falsos). Cada tarea que crea lo que falta se registra en el `AppConfig.ready()` de su app y prueba su registrante:

1. **PRD-01 y PRD-02 (`produccion`):** `registrar_agujeros_de_sector` (ocupados y comprometidos), `registrar_impedimento_de_baja_de_sector`
   (agujeros ocupados y comprometidos, con los lotes y órdenes), `registrar_contenido_de_sector` (lotes y órdenes),
   `registrar_perfil_de_sector` y `registrar_aviso_de_cambio_de_tipo` (lotes que deben pasar por la etapa y siembras a realizar).
   Al reservar agujeros (`PRD-01` y `PRD-02`), llamar a `bloquear_sectores`, que ya bloquea el invernadero activo y después los sectores activos, y rechaza con `sector_no_disponible`.
2. **PRD-04 (`produccion`):** `registrar_efecto_de_vuelta_a_servicio` (cierra el registro «Fuera de servicio» y escribe la bitácora),
   `registrar_efecto_de_baja_de_sector` (punto nuevo de `maestros`, D-51 punto 7) y `registrar_efecto_de_baja` (cierra los registros abiertos al dar de baja el invernadero; en el lote 4 se había dicho que no registraba nada)
   y el caso de uso PROD-PNR-FDS, que es el que produce el estado «fuera de servicio». También el Inicio del Agrónomo, como sección registrada
   con `registrar_seccion_de_inicio` de `core/extensiones.py` (D-43; la alerta de insumos y de merma del prototipo salen de ahí).
3. **INV-03 (`inventario`):** `registrar_semillas_de_cultivo` (contar y renombrar con su log `modificacion_semilla`) y
   `registrar_uso_de_cultivo` (la semilla habilitada más los lotes activos que le informa `produccion`, ver el punto siguiente).
   **Contrato de bloqueo:** quien crea una variedad bloquea el cultivo (`FOR NO KEY UPDATE`) antes de insertarla (`cultivo → variedad`); `baja_cultivo` cuenta las variedades activas después de bloquear.
   Además agrega a `Variedad` las columnas que faltan (rangos, postcosecha y peso en gramos). `EtapaProductiva` **no** tiene estado
   (opción A, 19/11/2026): no hay nada que agregar ahí.
4. **Módulo IoT (`iot`) — hecho en la documentación el 20/11/2026, se implementa en IOT-02:** `registrar_impedimento_de_baja_de_sector` con `hardware_activo` (códigos y textos de PROD-BAJ-SCT, regla 3)
   y `registrar_contenido_de_sector` con el hardware.

## Cuando existan lotes, órdenes de trabajo y contratos (puntos de extensión de variedades, lote 3)

INV-03 crea los tres puntos de variedades de `docs/api/extensiones_de_inventario.md` («Variedades») **sin registrantes**: sin ellos,
ninguna variedad tiene lotes, órdenes ni contratos, y todas pueden modificarse y darse de baja sin impedimentos. Cada tarea que crea lo
que falta se registra en el `AppConfig.ready()` de su app y prueba su registrante:

1. **PRD-01 (`produccion`):** `registrar_uso_de_variedad` (lotes de la variedad, lotes activos por invernadero, órdenes de siembra y de
   transición a realizar), `registrar_variedades_presentes` (variedades de lotes activos y de órdenes de siembra a realizar por
   invernadero: la misma definición del «umbral efectivo» de PROD-PNF-SMB) y `registrar_impedimento_de_baja_de_variedad` con los códigos
   `lotes_activos` y `ordenes_a_realizar`. PRD-01 también llama a `inventario.servicios.variedades` (`docs/api/variedades.md`) para
   leer la variedad, su ciclo y su semilla; no consulta las tablas a mano.
2. **`comercial` (ronda futura):** `registrar_impedimento_de_baja_de_variedad` con el código `contratos_abiertos` (contratos vigentes
   o abiertos con un detalle de la variedad; precondición f de PROD-BAJ-VAR). **Hasta entonces la precondición f no se verifica** (no
   hay contratos): se anota en el cierre de INV-03 y en `docs/temas_abiertos.md`.

## Cuando exista SistemaIoT

0. **Traspaso del Técnico y órdenes de mantenimiento** (D-53): IOT-05 agrega el valor `mantenimiento` a `OrdenTrabajo.Tipo`, el `CheckConstraint` de la prioridad obligatoria en ese tipo y su `registrar_traspaso` para el rol Técnico (el punto ya admite varios registrantes y recibe el rol). Si `maestros/extensiones.py` no entrega el rol a quien registra, es una corrección chica dentro de IOT-05.
0. **Envío de correo desde `iot`** (D-54): usar `core.correo.enviar_correo`, nunca `_enviar_correo`. Lo deja USR-10.
1. **IoT del invernadero.** `Invernadero.tiene_sistema_iot` (hoy `False`), la alerta y el campo del Técnico (regla 5 de
   PROD-ALT-INV) y la precondición h de PROD-BAJ-INV. Nació en MAE-01a. La precondición h se conecta con
   `registrar_impedimento_de_baja`.

## Cuando exista InsumoInvernadero

(INV-01 crea el modelo; INV-02 conecta lo de abajo.)

1. **Insumos del invernadero.** Postcondición c y precondición f de PROD-BAJ-INV. Nació en MAE-01a. La c (y el log por insumo
   de la f) se conecta con `registrar_efecto_de_baja`; la f, con `registrar_impedimento_de_baja`.

## Cuando exista Lote, OrdenTrabajo o StockCosechado

1. **Baja del invernadero y ficha.** Precondiciones c, d y e de PROD-BAJ-INV y las pestañas de lotes y de cámara de la
   ficha (la pestaña de lotes la registra PRD-01 con `registrar_pestana_de_invernadero`, ver `docs/api/extensiones_de_maestros.md`; la de cámara queda fuera, D-45). Se conectan por el punto de extensión `maestros/extensiones.py` (D-37, regla A4), creado en MAE-01b. Se registra con
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

1. **Consulta de alertas (CU-46).** MAE-02b dejó afuera la pantalla (paso 4): pasa a MAE-02c. Incluye la entrada «Alertas» del menú
   (desde `MaestrosConfig.ready()`), el alcance `Alerta.objects.para(usuario)`, solo las activas, filtros por invernadero y tipo, el
   detalle que llama a `abrir_alerta` (ya existe), que funcione sin JavaScript (HTMX solo reemplaza la tabla) y que viva en `maestros`.
   **Pendiente para pendientes_CU:** abrir la alerta la marca «leída» (regla 7 de 8.18) y choca con la postcondición de CU-46 («no se
   produjeron cambios en el sistema»). CU-41 reutiliza la consulta: `docs/api/alertas.md` todavía no nombra esa función. Nació en
   MAE-02a.

## Cuando una app necesite sumar algo al Inicio, a la ventana de baja o a la reactivación de una cuenta

1. **Puntos de extensión de `core` (D-43).** Se registran en `AppConfig.ready()` con `registrar_seccion_de_inicio`,
   `registrar_asignaciones_de_cuenta`, `registrar_efecto_de_baja_de_cuenta` y `registrar_efecto_de_reactivacion_de_cuenta`. Un efecto
   corre con la cuenta ya bloqueada y bloquea sus filas después del invernadero y en orden de id (`core/extensiones.py`). Nació en
   MAE-02b.

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

## Cuando exista contabilidad con asientos (D-45)

0. **Inventario.** `MovimientoInsumo` **ya hereda** de `OrigenDocumento` (D-52, CON-01 e INV-02): no hay nada que migrar. CMP-AJT-STK (INV-02) vuelve a verificar el
   ejercicio y las cuentas y crea el asiento de cada ajuste (`docs/casos_de_uso/inventario/ajuste_de_stock.md`: lo marcado «Fuera de la
   ronda (D-45)»; el asiento de cada ajuste referencia al movimiento como su `OrigenDocumento`). Decidir antes la cuenta del haber de la carga inicial (MD-90, tema abierto del CU).

1. **Reabrir seis casos de uso de la ronda «Producción 1».** Hasta entonces no verifican el ejercicio vigente ni las
   cuentas, ni crean `AsientoContable`: PROD-CNC-SMB y PROD-CNC-TRN (precondiciones c y d y su asiento), PROD-REG-MRM,
   PROD-PNR-FDS, CMP-AJT-STK y PROD-REG-APL (el asiento y las precondiciones contables que cada uno tenga en «CU
   extendidos»; el extracto de cada caso de uso las marca «Fuera de la ronda (D-45)»). Hay que reabrir sus servicios (PRD-01,
   PRD-02, PRD-03, PRD-04 e INV-02) y sus pruebas, incluidas las de concurrencia, y respetar el orden de bloqueos del
   patrón. Anotar lo mismo en pendientes_CU (Drive).

## Cuando se retome la cámara de frío (D-45)

1. **Cámara.** Pestaña `camaraTab` de la ficha del invernadero, `PROD-ASG-CAM` y la extensión 10c de `PROD-REG-MRM` (recorta las
   reservas de `comercial`). Va con la ronda de cosecha y comercial: necesita `StockCosechado` y `ReservaStock`.

## Cuando existan los pedidos de `compras` (D-45)

1. **Insumo en tránsito y compras.** En la ronda «Producción 1» el stock en tránsito es 0: la columna `cant_transito_insumo` existe y
   solo la escribirá `compras`. `compras` se enchufa a `inventario` por dos vías ya documentadas (`docs/api/extensiones_de_inventario.md`):
   el punto `registrar_impedimento_de_deshabilitacion` (orden de compra aprobada sin recibir, pedido en curso: los usan CMP-DSH-IIN, CMP-BAJ-INS y
   la baja del invernadero) y los servicios de stock (`docs/api/stock.md`) para la **recepción**.
2. **Recepción y faltante sin lote.** Por la regla 4 de 8.23 la recepción cancela primero el faltante sin lote y crea un lote nuevo por partida
   (y por fecha de vencimiento); hoy solo lo regulariza un recuento físico (`docs/modelo/inventario.md`, «Diferencias con el caso de uso»). Al
   escribir la recepción hay que verificar que resuelva la alerta «stock inconsistente» y la de «bajo el mínimo» (tema abierto de CMP-AJT-STK), y
   que agregue el vínculo `OneToOne` desde su tabla a `MovimientoInsumo` (A2).

## Cuando exista `produccion` completa (lote 5)

1. **Pestaña «Bitácora» de la ficha del invernadero** (`registrar_pestana_de_invernadero`, PRD-03): la de «Lotes activos» ya la registra PRD-01.
2. **Contabilidad** (ronda futura): los asientos de merma, aplicación de insumos (cuenta «Gastos de Producción», MD-90) y fuera de servicio salen de los registros de `produccion` (`Merma`, `AplicacionInsumos` e `ImputacionCosto`); hoy llevan su monto y no hay asiento (D-45).
3. **Cosecha** (ronda futura): suma a la bitácora los tipos `cosecha` e `incumplimiento de cláusula suministrante` (hoy no se ofrecen en el filtro de PROD-CNS-BIT) y la condición 1 de la alerta de plantas comprometidas (`aplicar_merma`).
4. ~~**Módulo IoT** (en paralelo): decide qué pasa con el hardware de un sector que sale de servicio.~~ **Resuelto el 20/11/2026:** no se toca; sus sensores no generan alertas ambientales mientras el sector esté fuera de servicio (`temas_abiertos.md`). PROD-PNR-FDS no cambia.
5. **Cámara de producto** (ronda futura): las partidas de cámara de PROD-REG-MRM (extensiones 4a y 10c, causas de cámara) y el movimiento «salida por merma».


## Cuando exista el modelo completo de Variedad (INV-03)

1. **Restricciones de `Variedad`.** MAE-03 la creó con columnas mínimas. INV-03 agrega la restricción única `(cultivo, lower(nombre_variedad))`, los rangos y el resto, con una migración propia en `maestros` (`docs/modelo/maestros.md`, «Variedad»).

## Cuando exista PROD-PNR-FDS (PRD-04)

1. **Estado «fuera de servicio».** Ningún caso de uso de MAE-03 lo produce; `maestros` ya lo muestra y ya ofrece «Volver a activar» y «Dar de baja». PRD-04 agrega `maestros/servicios/sectores.py::pasar_a_fuera_de_servicio` (lote 5 de `docs/api/extensiones_de_maestros.md`) y registra `registrar_efecto_de_vuelta_a_servicio` y `registrar_efecto_de_baja_de_sector`. La clave `fuera_de_servicio` ya está en `VALORES_VISIBLES["estado"]`.
