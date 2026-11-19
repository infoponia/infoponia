# MAE-01b · Invernadero: modificar, reactivar y dar de baja

Estado: hecha (en revisión) | App: maestros | Rama: feature/mae-01-invernadero

Depende de: MAE-01a (si no está hecha, frená)

Sigue a MAE-01a (D-39). La reactivación es parte de PROD-MOD-INV (regla 5 de PROD-BAJ-INV). Es la primera tarea que
crea puntos de extensión (regla A4 de D-37) y que bloquea filas fuera de core.

## Leer

- Casos de uso: docs/casos_de_uso/maestros/invernaderos.md — PROD-MOD-INV, PROD-BAJ-INV, «Pantallas», «Para más
  adelante» y «Solo prototipo»; de PROD-ALT-INV, las reglas 1 a 4 (las cita la regla 1 de PROD-MOD-INV); de
  PROD-CNS-INV, las reglas 4 y 6
- Modelo: docs/modelo/maestros.md — Invernadero y Dirección (no Alerta). Versión de la ronda 22
- Decisiones: D-28, D-30, D-32, D-36, D-37, D-38, D-39
- Patrones: docs/patrones/auditoria.md, docs/patrones/bloqueos.md, docs/patrones/datos_de_migracion.md
- Pantallas: docs/prototipos/produccion/ — VIEWS['inv-form'], INIT['inv-form'], ACT['inv-save'], MODALS['inv-baja'],
  ACT['inv-baja-ok'], ACT['inv-react'] y la línea `acts` de VIEWS.inv
- Código de referencia: core/servicios.py — _bloquear_cuenta_en_alcance, modificar_usuario, baja_usuario;
  core/views.py — _gestionar_cuenta; core/tests/concurrencia.py
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md

## Límites

- Crea modelos: ninguno
- Permitido fuera de la app:
  - core/menu.py y core/context_processors.py: punto de extensión del menú (las apps registran su entrada en
    AppConfig.ready()); la entrada «Producción» pasa a registrarla maestros
  - docs/patrones/bloqueos.md: sección del invernadero (orden de bloqueos y contrato de los puntos de extensión)
  - core/tests/test_menu.py: las pruebas del punto de extensión del menú (`registrar_entrada` y `menu_de`)
- Migraciones: ninguna (las acciones de auditoría ya existen desde MAE-01a)
- Dependencias nuevas: ninguna
- Fuera de alcance (cada uno con su disparador):
  - alertas: postcondiciones b (la alerta del rol pasa a «resuelta»), d y e de PROD-MOD-INV y e de PROD-BAJ-INV →
    «Cuando exista Alerta» (MAE-02, D-38);
  - notificación de la postcondición c de PROD-MOD-INV → «Cuando exista la primera notificación o alerta» (D-38);
  - precondiciones c a f y h, postcondiciones b y c y los logs por sector e insumo de la f de PROD-BAJ-INV, y lo que
    recibe la persona entrante (postcondición b de PROD-MOD-INV): se conectan por los puntos de extensión que crea esta
    tarea, cuando existan sus clases;
  - precondición g de PROD-BAJ-INV (transportistas activos): R155 no existe → disparador 2 de «Cuando exista
    Invernadero»;
  - el aviso «Personal por asignar» del Inicio del Gerente (regla 5 de PROD-CNS-INV): MAE-02.

## Pendiente de MAE-01a que entra acá

1. Punto de extensión del menú: core/menu.py deja de nombrar `maestros:invernaderos`.
2. Pruebas de concurrencia de modificar_invernadero (y de la baja y la reactivación).
3. Punto de extensión de los impedimentos de la baja (maestros/extensiones.py, disparador «Cuando exista Lote,
   OrdenTrabajo o StockCosechado»), más los de efectos de la baja y traspaso por cambio de personal.

## Hecho cuando

- El Gerente modifica el nombre, la dirección (también de urbana a rural) y el personal de un invernadero activo, con
  el aviso de la regla 2 antes de confirmar un cambio de personal; reactiva uno inactivo; y da de baja uno activo, o ve
  todo lo que lo impide, cada cosa con cómo resolverla.
- Un invernadero inactivo no se modifica (regla 5). Se ofrecen solo cuentas activas; la persona inactiva ya asignada se
  muestra con su marca y se puede conservar (regla 4).
- Los tres puntos de extensión existen, documentados con su contrato, sin ninguna app registrada, y probados con
  registrantes falsos.
- Cada operación audita con el formato de D-36: modificacion_invernadero, baja_invernadero y reactivacion_invernadero.
- Las pruebas de concurrencia pasan, y cada una falla al quitar la protección que cuida (D-32).
- Pruebas: maestros/tests/test_prod_mod_inv.py (ProdModInvServicioTests, ProdModInvVistaTests,
  ProdModInvConcurrenciaTests) y test_prod_baj_inv.py (ProdBajInvServicioTests, ProdBajInvVistaTests,
  ProdBajInvConcurrenciaTests).
- Comando de pruebas (maestros y las de core que cubren core/menu.py y core/context_processors.py):
  python manage.py test maestros core.tests.test_usr_ini_ses core.tests.test_usr_cns_usr core.tests.test_aud_cns_reg core.tests.test_usr_gst_prf core.tests.test_usr_vnc_cta core.tests.test_interfaz core.tests.test_menu --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  y, por tocar bloqueos, las de concurrencia del módulo:
  python manage.py test maestros --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Con el entorno virtual activo y la base local (`python manage.py runserver`). No hay migraciones nuevas. Cuentas de prueba:
un Gerente, un Agrónomo, un Capataz y un Vendedor activos; y dos invernaderos creados con «Nuevo invernadero» (por ejemplo,
«Sur» urbano con Agrónomo y Capataz, y «Norte» rural sin personal).

1. Como Gerente, «Producción» → «Sur». En la ficha aparece la tarjeta «Acciones» con «Modificar» y «Dar de baja». Con la cuenta
   de Agrónomo (a cargo de «Sur») la ficha no tiene ninguna acción. El menú lateral sigue mostrando «Producción» en el mismo
   lugar (la entrada ahora la registra `maestros` al arrancar).
2. «Modificar»: el formulario arranca con el nombre, el tipo de dirección, la provincia, el departamento, la localidad, los
   datos de la dirección y el personal de «Sur». Cambiá solo el nombre y guardá: vas a la ficha con «Se guardaron los cambios
   de …» y, en «Auditoría», aparece «Modificación de invernadero» con una sola fila Campo / Antes / Después (Nombre).
3. Guardá sin cambiar nada: no se crea ningún registro nuevo en «Auditoría».
4. Probá el nombre de «Norte» escrito en otras mayúsculas o con espacios: el error sale junto al campo y se conserva lo escrito.
   Un nombre de puros guiones, o más de 80 caracteres, también se rechaza.
5. Cambiá solo la localidad (otra del mismo departamento): en «Auditoría» la única fila es «Localidad». Cambiá el tipo de
   dirección de urbana a rural (completando ruta y kilómetro) y guardá: «Auditoría» muestra «Tipo de dirección» urbana → rural,
   la calle y el número a «—» y la ruta y el kilómetro desde «—». Después volvé de rural a urbana: el espejo.
6. Aviso de la regla 2: cambiá el Capataz por otro y guardá. No se guarda: aparece la ventana «Confirmá el cambio de personal»
   con quién reemplaza a quién (todavía sin «Recibe…», porque aún no hay órdenes). «Volver al formulario» te deja con lo que
   escribiste, sin guardar. «Confirmar y guardar» guarda y va a la ficha; «Auditoría» muestra el Capataz anterior y el nuevo, y
   ambos figuran como afectados. Dejá el Agrónomo en «Sin asignar»: la ventana dice «El invernadero queda sin Agrónomo…».
7. Dá de baja la cuenta de un Capataz asignado (desde «Usuarios y seguridad») y abrí «Modificar» en su invernadero: el Capataz
   sigue elegido con «— inactivo». Guardar sin tocarlo no pide confirmar; reemplazarlo sí, y la lista no ofrece cuentas inactivas.
8. «Dar de baja» en «Sur»: se abre la ventana «¿Dar de baja Sur?» (no hay impedimentos todavía, porque aún no existen lotes,
   órdenes ni stock). «Cancelar» la cierra. «Dar de baja» te lleva a la ficha con «Sur se dio de baja.», «Inactivo» junto al
   nombre, el personal conservado y, en «Auditoría», «Baja de invernadero» (Estado: Activo → Inactivo).
9. Con el invernadero inactivo, la ficha ofrece solo «Reactivar» (no «Modificar» ni «Dar de baja»). Escribir a mano
   `/produccion/<id>/modificar/` te devuelve a la ficha con «solo se puede reactivar». «Reactivar» lo deja activo, sin ventana,
   con el aviso «Sus sectores siguen inactivos: los reactiva el Agrónomo», y «Auditoría» muestra «Reactivación de invernadero».
10. Con el Agrónomo o el Capataz: escribir a mano `/produccion/<id>/modificar/` o `/baja/` da el 403.
11. Sin JavaScript (desactivalo en el navegador): repetí los pasos 6 y 8. La ventana del cambio de personal y la de la baja
    vienen en la página (al principio), con sus botones; «Dar de baja» y «Confirmar y guardar» funcionan igual. Con
    JavaScript, las ventanas se abren sobre la página, con el foco en el botón principal y se cierran con Esc.
12. Con HTMX, «Dar de baja» abre la ventana sin recargar la página (compará la barra de direcciones: no cambia).
13. Pruebas de concurrencia (no hace falta el navegador): `python manage.py test maestros --keepdb --tag concurrencia` da
    10 pruebas OK. Corré una vez después `python manage.py test maestros --keepdb --parallel --exclude-tag concurrencia
    --exclude-tag migracion`: las de concurrencia vacían Georef y `ConGeoref` lo vuelve a cargar solo.
14. Antes de mergear a main: esta tarea no tiene migraciones, así que el despliegue de Render no cambia la base. Si todavía no se
    aplicaron en Neon las de MAE-01a (`core 0010`, `maestros 0001` y `0002`), hay que hacerlo antes.

## Cierre (la completa Claude Code al cerrar)

**Estado: MAE-01b hecha.** Con esta tarea queda completo el invernadero (MAE-01a y MAE-01b).

**Qué se hizo**

- Servicios en `maestros/servicios/invernaderos.py`: `modificar_invernadero` (PROD-MOD-INV), `reactivar_invernadero`,
  `baja_invernadero` e `impedimentos_para_baja` (PROD-BAJ-INV), `bloquear_invernadero_activo` (contrato de los puntos de
  extensión), `acciones_permitidas` (`frozenset`, como la de `core`) y la excepción `FaltaConfirmarPersonal` (regla 2). El alta
  se refactorizó sin cambiar su comportamiento: `_validar_nombre` y `_buscar_localidad` los comparte con la modificación.
- Tres puntos de extensión en `maestros/extensiones.py` (regla A4 de D-37), sin ninguna app registrada y probados con
  registrantes falsos: impedimentos de la baja (se informan todos, regla 2), efectos de la baja y traspaso por cambio de
  personal (`contar_traspaso` para el aviso de la regla 2 y `traspasar` para la postcondición b).
- Pantallas: formulario de modificar (el mismo del alta, con los datos del invernadero), ventana de confirmación del cambio de
  personal (regla 2) y ventana de la baja con sus impedimentos, botón «Reactivar» sin ventana, y las acciones de la ficha según
  `acciones_permitidas`. Sin JavaScript propio: las ventanas se arman en el servidor.
- Menú: punto de extensión en `core/menu.py` (`registrar_entrada`, `menu_de`); `core` ya no nombra «Producción»: la registra
  `MaestrosConfig.ready()`. Es lo último que se implementó.
- `docs/patrones/bloqueos.md`: sección «Invernadero» con el orden de bloqueos, el contrato de los puntos de extensión y el
  motivo de hacer el `UPDATE` del invernadero antes de los traspasos.
- Casos de uso cubiertos: PROD-MOD-INV (postcondiciones a, b —el traspaso—, e —sin alertas— y f; reglas 1 a 7; reactivación) y
  PROD-BAJ-INV (precondiciones a y b y, por el punto de extensión, c a f y h; postcondiciones a, d y f, y b y c por el punto de
  extensión; reglas 1, 2 y 5).

**Pruebas:** `maestros` pasa de 99 a 234 pruebas sin concurrencia (136 nuevas y una de MAE-01a reemplazada: ProdModInv: servicio,
reactivación, acciones y vista; ProdBajInv: servicio, bloqueo y vista; una de `test_prod_cns_inv.py` reemplazada por dos) y suma
10 de concurrencia, 244 en total (`ProdModInvConcurrenciaTests` y `ProdBajInvConcurrenciaTests`); `core/tests/test_menu.py` suma 6 del punto de extensión del
menú. El comando de pruebas de la tarea da 465 pruebas OK; las de concurrencia, 10 OK, tres corridas seguidas.

**Experimentos sin protección** (D-32, la tarea toca bloqueos; se quitó una protección por vez en memoria y se restauró):

| Protección que se quita | Pruebas que fallan |
|---|---|
| Bloqueo del invernadero (`_bloquear_invernadero`) | 6: las dos del contrato de D-37, dos bajas, dos reactivaciones, baja y modificación en los dos órdenes |
| Bloqueo de las cuentas en `modificar_invernadero` | 1: asignar una cuenta que se da de baja a la vez |
| Los dos bloqueos anteriores | 8: esas siete y la de dos modificaciones a la vez (con uno solo de los dos bloqueos, esta pasa: ver abajo) |
| Traducción del `IntegrityError` del nombre | 1: renombrar dos invernaderos al mismo nombre |
| Revalidar el personal después de bloquear las cuentas | 1: asignar una cuenta que se da de baja a la vez |
| Que el creador falso bloquee el invernadero (contrato de D-37) | 2: las dos del contrato |

- Con los dos bloqueos quitados fallan 8: las 6 de «Bloqueo del invernadero», la de asignar una cuenta que se da de baja
  (que falla al quitar el bloqueo de las cuentas) y la de dos modificaciones a la vez (que solo falla si faltan los dos).
- Ninguna prueba falla al invertir el orden de bloqueo (cuentas → invernadero → apps altas) porque hoy nadie más bloquea
  invernaderos y cuentas en el orden contrario; `test_regla_4_la_baja_de_una_cuenta_que_espera_a_su_asignacion_…` documenta
  el orden que tendrá que seguir la baja de cuenta futura. No hay protección que quitar.

**Decisiones:** D-40 (propuesta aparte): gana el último al modificar; cambio de dirección con la dirección nueva y la anterior
borrada, con el `UPDATE` antes de los traspasos; aviso de la regla 2 por `FaltaConfirmarPersonal` y ventana armada en el
servidor; orden de bloqueos y contrato de los puntos de extensión.

**Lo que hay que saber**

- Como la fila de quien actúa entra en la misma consulta que las cuentas de personal, **todas las modificaciones del mismo
  Gerente se serializan**, y hoy hay un solo Gerente activo (D-09). Por eso la prueba de dos modificaciones a la vez solo falla
  si se quitan los dos bloqueos. La baja y la reactivación no bloquean al actor, así que se serializan por el invernadero.
- Los traspasos, los impedimentos y los efectos no hacen nada todavía: no hay ninguna app registrada.
- La prueba temporal de MAE-01a `test_regla_6_la_ficha_de_mae_01a_no_ofrece_modificar_ni_dar_de_baja` se reemplazó (aprobado
  en el plan) por dos pruebas de la regla 6 de PROD-CNS-INV.
- No se probó en un navegador real: la apertura de las ventanas con HTMX, el foco y la tecla Esc quedan para la verificación a
  mano (pasos 11 y 12).

**Fuera de lo previsto en «Permitido fuera de la app»** (cambios mínimos, para que el equipo los revise): `core/tests/test_menu.py`
(archivo nuevo con las pruebas del punto de extensión del menú, que no figuraba) y `maestros/tests/fabricas.py` suma
`crear_invernadero_con_geografia_propia` para las pruebas de concurrencia (el `flush` de un `TransactionTestCase` vacía Georef).
`CLAUDE.md` no se tocó (la corrección de la ronda va en `feature/doc-esquema-nuevo`).

**Para más adelante** (cada una con su disparador en `docs/disparadores.md`, ver las propuestas): alertas (MAE-02),
notificaciones (D-38), precondición g y regla 3 de PROD-BAJ-INV (R155), regla 4 de PROD-BAJ-INV (cada app que planifique, pida,
asigne stock o reintente entregas excluye los invernaderos inactivos) y el registro de cada app alta en los tres puntos de
extensión cuando existan sus clases.
