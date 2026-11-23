# COM-01 · App `comercial`, clientes y vehículos

Estado: pendiente | App: comercial (y la API de direcciones y CUIT en maestros, D-58) | Rama: feature/com-01-clientes-y-vehiculos |
Ronda: Comercial 1

Depende de: **MAE-05** (`TransportistaInvernadero` y el punto `registrar_logistica_de_transportista`, D-55), UI-01 y NOT-01. UI-01 y NOT-01
están hechas. **No depende de ninguna tarea de producción.** Si MAE-05 no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** Crea la app `comercial` (nivel 6 de D-37) con los dos datos maestros que necesita todo lo demás de la ronda: los
**clientes** (con sus direcciones) y los **vehículos** (con su transportista). Las reglas que dependen de contratos o de entregas, que todavía
no existen, quedan escritas como funciones que hoy devuelven «nada» y que completan COM-02 a COM-08 (están marcadas «Se completa en COM-NN»
en los extractos).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-ALT-CLT | Alta Cliente (con la reactivación) | docs/casos_de_uso/comercial/clientes.md | La regla 7 (volver al caso de uso que lo incluye) deja el parámetro listo; la usan COM-02 y COM-03 |
| COM-MOD-CLT | Modificar Cliente | docs/casos_de_uso/comercial/clientes.md | Regla 3 (correo con suministro vigente): se completa en COM-03. Dirección en uso (regla 4): se completa en COM-02 y COM-03 |
| COM-BAJ-CLT | Baja Cliente | docs/casos_de_uso/comercial/clientes.md | Lo pendiente que informa la regla 1: se completa en COM-02, COM-03, COM-06 y COM-08 |
| COM-CNS-CLT | Consultar Cliente | docs/casos_de_uso/comercial/clientes.md | Contratos y entregas de la ficha (regla 2): se completan en COM-02, COM-03, COM-06 y COM-08 |
| COM-ALT-VEH | Alta Vehículo | docs/casos_de_uso/comercial/vehiculos.md | — |
| COM-MOD-VEH | Modificar Vehículo (con la reactivación) | docs/casos_de_uso/comercial/vehiculos.md | Reglas 2 y 3 (carga asignada, entregas a realizar): se completan en COM-05 |
| COM-BAJ-VEH | Baja Vehículo | docs/casos_de_uso/comercial/vehiculos.md | Precondición c y regla 1 (entregas a realizar): se completan en COM-05 |
| COM-CNS-VEH | Consultar Vehículo | docs/casos_de_uso/comercial/vehiculos.md | Carga de los próximos días (regla 2): se completa en COM-05 |

## Leer

- Casos de uso: los dos extractos de la tabla, completos, **incluida la sección «Cómo se aplica en la ronda»** de cada uno.
- Modelo: docs/modelo/comercial.md (las tres fichas, «Pendientes de MD» y «Diferencias con el caso de uso»); de docs/modelo/maestros.md,
  `Direccion` y «`TransportistaInvernadero`».
- Decisiones: D-58 (la de esta tarea), D-05, D-06, D-14, D-21, D-22, D-24, D-28, D-29, D-30, D-32, D-36, D-37, D-39, D-40, D-42, D-44,
  D-47, D-55, D-57.
- API: docs/api/direcciones.md (implementala tal cual: es parte de esta tarea), docs/api/extensiones_de_maestros.md (sección
  «Transportistas»: el registrante de logística y `registrar_datos_de_cuenta` de `core`), docs/api/notificaciones.md.
- Patrones: docs/patrones/abm.md, docs/patrones/bloqueos.md, docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md.
- Pantallas: docs/prototipos/comercial/ — leé primero su `README.md` («Cómo está armado»). Funciones: `VIEWS.com`, `tabClientes`, `VIEWS.cli`,
  `INIT.cliform`, `VIEWS.cliform`, `ACT['cliform-ok']`, `ACT.reactcli`, `dirForm` y `dirAdd` (la versión de las líneas 1532 a 1540),
  `ACT.dirdesact`, `MODALS.bajacli`, `tabVehiculos`, `INIT.vehform`, `VIEWS.vehform` y `ACT['vehform-ok']` (con sus sobrescrituras de las
  líneas 1807 y 1817), `MODALS.bajaveh`, `ACT.reactveh`, y `NAV.ger` y `NAV.ven` de la línea 1383 (referencia, D-61; lo que difiera de los
  casos de uso lo decide el caso de uso, L7: las diferencias ya detectadas están en cada extracto, «Lo que difiere del prototipo»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `maestros/models.py` (`Direccion`, `DireccionUrbana`, `DireccionRural`, `Localidad`) y `maestros/servicios/invernaderos.py`
    (`_limpiar_direccion`, `_crear_direccion`, `_buscar_localidad`, `datos_de_la_direccion`, `FORMATOS`, `_largo_excedido`, `_error`, y
    cómo `modificar_invernadero` cambia una dirección de zona), `maestros/servicios/perfil.py` (`_cuit_valido`), `maestros/validadores.py`,
    `maestros/servicios/geografia.py`;
  - `maestros/servicios/transportistas.py` y `maestros/extensiones.py` (lo que dejó MAE-05);
  - `maestros/views.py` y `maestros/forms.py`: los fragmentos de dirección del invernadero (`campos_direccion`, `departamentos`,
    `localidades`) y sus plantillas, como modelo de los de `comercial`;
  - `maestros/servicios/cultivos.py` (el ABM más parecido), `inventario/apps.py` (cómo una app registra su menú y sus puntos);
  - `core/models.py` (auditoría: `Accion`, `ETIQUETAS`, `VALORES_VISIBLES`, `ACCIONES_DE_NEGOCIO`), `core/notificaciones.py`, `core/menu.py`,
    `core/validadores.py` (`validar_telefono`), `core/acceso.py` (`rol_requerido`), `core/templatetags/iconos.py`.

## Límites

- Crea modelos: `comercial.Cliente`, `comercial.DireccionCliente` y `comercial.Vehiculo` (`docs/modelo/comercial.md`, con todas sus
  restricciones de base) → revisá docs/disparadores.md: cierra «Cuando exista Cliente o CompraVenta» y, en parte, el punto 3 de «Cuando exista
  Entrega»; nacen «Completan el ABM de cliente» y «Completan el ABM de vehículo» (ya escritos en el lote C1).
- Crea también el cargador de datos de verificación de `comercial` (`comercial/verificacion.py`, con su registro en `ComercialConfig.ready()`
  y `comercial/tests/test_verificacion.py`; `docs/patrones/datos_de_verificacion.md`): nació después del lote C1 (CLAUDE.md, MAE-02d e
  IOT-03). Las tareas COM siguientes lo amplían.
- Migraciones: `comercial/migrations/0001_initial.py` (esquema; depende de la última de `maestros` y de `core`). Una de `core`, solo de
  `choices`, con las ocho acciones nuevas: `00NN_comercial_acciones_de_auditoria`, con el número libre en `main` al abrir el PR. **Ninguna
  en `maestros`.** Ninguna de datos.
- Permitido fuera de la app:
  - `config/settings.py`: `'comercial'` en `INSTALLED_APPS`, después de `'produccion'`, con el comentario `# nivel 6`;
  - `config/urls.py`: una línea, `path("comercial/", include("comercial.urls"))`; y la misma en `core/tests/urls_prueba_acceso.py`
    (lo pidieron MAE-04 e INV-01, `docs/temas_abiertos.md`);
  - `core/models.py`: solo `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO` (`alta_cliente`, `modificacion_cliente`,
    `baja_cliente`, `reactivacion_cliente`, `alta_vehiculo`, `modificacion_vehiculo`, `baja_vehiculo`, `reactivacion_vehiculo`), y su
    migración;
  - `core/templatetags/iconos.py`: los íconos `cart` y, si MAE-05 no lo agregó, `truck`, copiados del prototipo comercial (objeto `XI`, línea 791);
  - `maestros/servicios/direcciones.py` (nuevo), `maestros/validadores.py` (`validar_cuit` y `formatear_cuit`), y en
    `maestros/servicios/invernaderos.py` y `maestros/servicios/perfil.py` **solo** el reemplazo de las funciones privadas por llamadas a las
    públicas (D-58). Pruebas nuevas en `maestros/tests/test_direcciones.py` y `test_validar_cuit.py`; ninguna prueba existente de `maestros`
    se modifica;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md` y `docs/tareas/ronda_comercial_1.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: contratos, entregas, rutas y todo lo que se marca «Se completa en COM-NN» en los extractos; el impedimento de quitar o
  trasladar un transportista (`registrar_impedimento_de_transportista`: COM-05 y COM-06) y el de la baja de su cuenta (COM-06); los
  asientos (D-57).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **App, modelos y auditoría.**
   - La app: `comercial/__init__.py`, `apps.py` (`ComercialConfig`, con el docstring de nivel como las demás), `models.py`, `servicios/`,
     `tests/`, y su lugar en `INSTALLED_APPS`.
   - Los tres modelos de `docs/modelo/comercial.md`, con **todas** sus restricciones de base: CUIT único y de 11 dígitos; la restricción por
     tipo de cliente; patente única y con formato; capacidad mayor que 0; `en_ruta` ⇒ fecha; inactivo ⇒ sin transportista; los
     `OneToOneField` de `DireccionCliente.direccion` y de `Vehiculo.transportista`. Los `QuerySet` con `en_alcance_de` (un único lugar, D-28),
     `Vehiculo.esta_en_ruta(hoy)`, los `__str__` y `verbose_name` en castellano; el admin de solo lectura, como los demás.
   - Las ocho acciones de auditoría en `core/models.py` (con `ETIQUETAS` para los campos nuevos y `VALORES_VISIBLES` para `tipo_cliente` y
     `tipo_vehiculo`) y su migración.
   - Las fábricas en `comercial/tests/fabricas.py`: `cliente(...)`, `direccion_de_cliente(cliente, ...)` (crea la dirección con la API del
     paso 2 y su vínculo) y `vehiculo(..., transportista=None, en_ruta_hoy=False)`.
   Pruebas, en `comercial/tests/test_modelos_comercial.py`: una por restricción de la base (la viola y no la viola) y `esta_en_ruta` (en ruta
   hoy, ruta de ayer sin finalizar, sin ruta).
2. **API de direcciones y CUIT en `maestros`** (D-58), tal cual `docs/api/direcciones.md`. Primero las pruebas nuevas de `maestros`
   (`test_direcciones.py`, `test_validar_cuit.py`); después el módulo y la delegación en `invernaderos.py` y `perfil.py`. Corré **toda** la
   suite de `maestros`: tiene que dar lo mismo que antes. Si alguna prueba existente falla, el refactor cambió algo: frená.
3. **Servicios de clientes**, en `comercial/servicios/clientes.py`. Un caso de uso = una función en `transaction.atomic()`, con el orden de
   `docs/patrones/abm.md`, sección 2:
   - `alta_cliente(actor, datos)`, `reactivar_cliente(actor, cliente_id, datos)`, `modificar_cliente(actor, cliente_id, datos)` y
     `baja_cliente(actor, cliente_id)`. `datos` es un `dataclass` (`DatosDeCliente`, con la lista de direcciones nuevas, corregidas,
     desactivadas y borradas) que arma `desde_post`.
   - Lectura: `buscar_clientes(actor, texto, estado, pagina)`, `ficha_del_cliente(actor, cliente_id)`, `acciones_permitidas(actor, cliente)`.
   - Las funciones que completan otras tareas, con su docstring «Se completa en COM-NN»: `direcciones_en_uso(ids)`,
     `impide_quitar_el_correo(cliente)` y `pendientes_del_cliente(cliente, actor)`.
   - Todas las reglas y decisiones de `clientes.md` («Cómo se aplica»): los dos rechazos del CUIT repetido con su id, la reactivación con el
     formulario del alta y el aviso al Gerente, la dirección idéntica, el tipo de cliente, la auditoría.
   Pruebas: `comercial/tests/test_com_alt_clt.py`, `test_com_mod_clt.py`, `test_com_baj_clt.py`, `test_com_cns_clt.py` (las clases
   `<CodigoCu>ServicioTests`). Una por regla y por postcondición; además: C6 (ninguna dirección de un cliente es la de un invernadero, ni
   siquiera si los datos coinciden); el Vendedor no da de baja; el aviso al Gerente solo cuando reactiva un Vendedor, y sin Gerente activo la
   reactivación no falla; sin cambios no se audita. Concurrencia (`@tag("concurrencia")`, `test_clientes_concurrencia.py`): dos altas con el
   mismo CUIT (una crea, la otra recibe el error de campo); baja y modificación a la vez del mismo cliente (las dos terminan, sin 500).
4. **Servicios de vehículos**, en `comercial/servicios/vehiculos.py`:
   - `alta_vehiculo(actor, datos)`, `modificar_vehiculo(actor, vehiculo_id, datos)`, `reactivar_vehiculo(actor, vehiculo_id)`,
     `baja_vehiculo(actor, vehiculo_id)`;
   - lectura: `buscar_vehiculos(actor, texto, estado, invernadero_id)`, `ficha_del_vehiculo(actor, vehiculo_id)`,
     `transportistas_disponibles(actor, vehiculo=None)`, `acciones_permitidas(actor, vehiculo)`;
   - las que completa COM-05: `entregas_a_realizar_del_transportista(transportista)` y `carga_maxima_asignada(vehiculo, desde)`;
   - el registrante de logística: `logistica_de_transportistas(transportistas) -> dict[int, Logistica]`.
   Todas las reglas y decisiones de `vehiculos.md` («Cómo se aplica»): bloqueos (cuentas, después el vehículo), en ruta, patente, capacidad,
   transportista, las tres notificaciones, la auditoría.
   Pruebas: `test_com_alt_veh.py`, `test_com_mod_veh.py`, `test_com_baj_veh.py`, `test_com_cns_veh.py`. Las reglas 2 y 3 de MOD y la
   precondición c de BAJ se prueban con `mock.patch` sobre las dos funciones de COM-05 (que ya se llamen y que su respuesta rechace).
   Concurrencia (`test_vehiculos_concurrencia.py`): dos vehículos que eligen al mismo transportista a la vez (uno lo logra, el otro recibe
   `transportista_con_vehiculo`).
5. **Vistas, plantillas y menú.**
   - `comercial/urls.py` (`app_name = "comercial"`): `/comercial/` (nombre `inicio`) redirige a la lista de clientes (hasta COM-02, que la
     cambia por «Contratos»); `clientes/`,
     `clientes/nuevo/`, `clientes/<id>/`, `clientes/<id>/modificar/`, `clientes/<id>/reactivar/`, `clientes/<id>/baja/`; `vehiculos/`,
     `vehiculos/nuevo/`, `vehiculos/<id>/`, `vehiculos/<id>/modificar/`, `vehiculos/<id>/reactivar/`, `vehiculos/<id>/baja/`; y los
     fragmentos de dirección (`direccion/campos/`, `direccion/departamentos/`, `direccion/localidades/`), solo `GET`, para el Gerente y el
     Vendedor, que leen Georef con `maestros.servicios.geografia` (D-58, punto 7).
   - La pantalla «Comercial» con pestañas (`VIEWS.com`): en esta tarea, «Clientes» y, solo para el Gerente, «Vehículos». Las demás las suma
     cada tarea (D-25: el menú y las pestañas muestran solo lo que existe).
   - Las vistas solo orquestan (`docs/patrones/abm.md`, sección 1), con `rol_requerido`, `never_cache` y `vary_on_headers("HX-Request")` donde
     haya fragmento; ventanas con HTMX y respaldo sin JavaScript; errores por campo; aviso breve al terminar (D-29). Textos con voseo y los
     textos explicativos de cada extracto («Pantallas»).
   - La entrada del menú, desde `ComercialConfig.ready()`: `registrar_entrada(("Comercial", "comercial:inicio", "cart"), (GERENTE, VENDEDOR),
     despues_de="Producción")`. Al Vendedor, que no tiene «Producción», le queda después de «Panel de control».
   Pruebas: `comercial/tests/test_clientes_vistas.py` y `test_vehiculos_vistas.py` (permisos: el Vendedor no ve ni abre «Vehículos» ni la baja
   de un cliente; los demás roles reciben 403; ningún botón lleva a un 403; el flujo con HTMX y sin él; los errores por campo; el
   parámetro `volver` acepta solo URL internas), y la entrada del menú para los dos roles.
6. **«Logística» y ficha de la cuenta.** `ComercialConfig.ready()` registra:
   - `logistica_de_transportistas` en `maestros.extensiones.registrar_logistica_de_transportista`;
   - `datos_de_cuenta_del_transportista` en `core.extensiones.registrar_datos_de_cuenta`: el «Vehículo» del Transportista (decisión del
     estudiante del 21/11/2026; texto y nota en `vehiculos.md`, «Cómo se aplica»).
   Pruebas mínimas de cada registrante (`comercial/tests/test_logistica.py` y `test_datos_de_cuenta.py`): con datos (vehículo activo y
   situación), neutro sin datos (un transportista sin vehículo da `vehiculo=None` y «Sin vehículo»; otro rol, lista vacía), sin consultas
   por fila en la logística (`assertNumQueries` con tres transportistas), y en pantalla: la ficha del invernadero muestra las tres columnas y
   la ficha de la cuenta y «Mi perfil» muestran «Vehículo» después de «Invernadero» (en «Mi perfil», sin la nota).
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
   - en `docs/disparadores.md`: tachar «Cuando exista Cliente o CompraVenta» (con la nota de C6) y marcar como hecha la parte de COM-01 del
     punto 3 de «Cuando exista Entrega»;
   - marcar COM-01 en `docs/tareas/README.md` y en `docs/tareas/ronda_comercial_1.md`;
   - pasar D-58 a «vigente» si el estudiante la validó.
   Lo que haya quedado distinto de lo escrito va a `docs/temas_abiertos.md`.

Si el tiempo apremia, lo último que se recorta es el paso 6 (se anota en «Cuando exista Entrega», punto 3, y en una línea nueva para el
vehículo de la cuenta). No se recortan las
restricciones de la base, los bloqueos ni la API de `maestros`.

## Hecho cuando

- El Vendedor y el Gerente registran, modifican, buscan y consultan clientes; el Gerente los da de baja; los dos pueden reactivar uno
  inactivo, y si lo hace el Vendedor, el Gerente recibe la notificación.
- Un CUIT inválido o repetido se rechaza con su mensaje, con «Abrir su ficha» o «Reactivarlo» según el caso; nunca hay dos clientes con el
  mismo CUIT (lo garantiza la base).
- Un cliente tiene cero o más direcciones, nunca dos idénticas activas, y ninguna es de un invernadero (C6).
- El Gerente registra, modifica, reactiva, da de baja y consulta vehículos; un transportista nunca queda con dos vehículos (lo garantiza
  la base); un vehículo en ruta no se modifica ni se da de baja.
- «Logística» muestra el vehículo y la situación de cada transportista; la ficha de la cuenta y «Mi perfil» del Transportista, su vehículo.
- Todas las pruebas de `maestros` que existían siguen pasando sin cambios.
- Pruebas: `comercial/tests/test_com_<cu>.py` (una por caso de uso, con `<CodigoCu>ServicioTests` y `<CodigoCu>VistaTests` donde haya
  pantalla), `test_modelos_comercial.py`, `test_logistica.py`, `test_datos_de_cuenta.py`, `maestros/tests/test_direcciones.py` y `test_validar_cuit.py`.
- Comando de pruebas:
  python manage.py test comercial maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

**Datos para verificar** (`CLAUDE.md`, «Datos para la verificación a mano»; `docs/patrones/datos_de_verificacion.md`): antes de pedirle
al estudiante la verificación, Claude Code deja la base local cargada con lo que piden los pasos de abajo, ampliando el cargador de
`comercial` (`comercial/verificacion.py`, registrado en `ComercialConfig.ready()` con `registrar_cargador`, orden 20; lo crea COM-01;
cuentas `<rol>@prueba<N>.local` con el número libre al crearlo: hoy `prueba5`, porque `maestros` usa 1 y 2, `iot` 3 y `produccion` 4),
siempre llamando a los servicios. El estudiante no carga datos a mano. En el «Cierre», qué quedó cargado y con qué cuentas.

Hay migraciones nuevas (`comercial` y `core`): `python manage.py migrate`. **Ya están cargados los datos** (comando `cargar_datos_de_verificacion --solo comercial`,
con la contraseña de `CLAUDE.local.md`). Cuentas: el Gerente de siempre (solo hay uno activo), `vendedor@prueba5.local`, `transportista@prueba5.local` (ya agregado a
«Invernadero Comercial» desde «Logística», MAE-05) y `transportista2@prueba5.local` (sin invernadero). Clientes cargados: «Verdulería Los Pinos S.R.L. (prueba)» (con correo
y dos direcciones), «Marta Gómez (prueba)» (física, sin correo) y «Cerrado S.A. (prueba)» (dado de baja); vehículo cargado: `ZZZ999`, dado de baja. Los CUIT de los pasos 2 a 6
tienen que ser otros (por ejemplo 30-71234567-1 y 20-12345678-6).

1. Con el Vendedor: el menú muestra «Comercial» después de «Panel de control»; la pantalla abre en «Clientes» y no tiene la pestaña
   «Vehículos».
2. Registrar una persona jurídica sin correo ni dirección: se crea; la ficha dice «Necesario para pactar suministros» junto al correo.
3. Registrar otra con un CUIT mal tipeado: error en el campo. Con el CUIT del paso 2: aviso con «Abrir su ficha».
4. Registrar una persona física con dos direcciones (una urbana y una rural); intentar agregar una tercera igual a la urbana, cambiando solo
   las mayúsculas: «El cliente ya tiene esa dirección».
5. Modificar el cliente del paso 4: corregir la rural, desactivar la urbana y borrar la que quedó sin usar; en «Auditoría» hay un
   `modificacion_cliente` con las direcciones afectadas.
6. Con el Gerente: dar de baja el cliente del paso 2 (la ventana dice que no tiene pendientes). Con el Vendedor: registrar uno nuevo con ese
   mismo CUIT: ofrece «Reactivarlo»; corregir el teléfono y confirmar. El Gerente tiene la notificación «Cliente reactivado: …».
7. Con el Gerente, «Vehículos»: registrar una camioneta `ae-123 cd` (se guarda `AE123CD`) con 800 kg y el Transportista con invernadero. Ese
   Transportista tiene la notificación. En la ficha de su invernadero, «Logística» muestra «Camioneta AE123CD · 800 kg» y «En el invernadero».
   En la ficha de su cuenta (y en su «Mi perfil») aparece «Vehículo: Camioneta AE123CD · 800 kg».
8. Registrar un segundo vehículo: el Transportista del paso 7 ya no aparece en la lista para elegir.
9. Modificar el vehículo: cambiar el transportista por el que no tiene invernadero (aviso «No recibe entregas hasta…»); los dos
   Transportistas reciben su notificación. Darlo de baja: queda inactivo y sin transportista; «Reactivar» lo deja activo, sin transportista.
10. Sin JavaScript, los pasos 2 a 6 y 7 a 9 funcionan igual: cada ventana es una página.
11. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre

**Qué se hizo** (rama `feature/com-01-clientes-y-vehiculos`, 23/11/2026)

- **App `comercial`** (nivel 6, D-37) en `INSTALLED_APPS`: `Cliente`, `DireccionCliente` y `Vehiculo` con todas las restricciones de la base (CUIT único y de
  11 dígitos, datos por tipo de cliente, patente única y con formato, capacidad mayor que 0, `en_ruta` ⇒ fecha, inactivo ⇒ sin transportista y los dos
  `OneToOneField`), `en_alcance_de` en un único lugar (D-28), `esta_en_ruta(hoy)` y el admin de solo lectura. Migraciones `comercial` 0001 y `core` 0024
  (`0024_comercial_acciones_de_auditoria`, solo `choices`, con las ocho acciones). Ninguna migración en `maestros`.
- **API de `maestros` (D-58):** `maestros/servicios/direcciones.py` (`validar_direccion`, `crear_direccion`, `corregir_direccion`, `inactivar_direccion`,
  `borrar_direccion`, `datos_de_la_direccion`, `clave_de_ubicacion`) y `validar_cuit` / `formatear_cuit` en `maestros/validadores.py`. `invernaderos.py` y
  `perfil.py` delegan en ellas sin cambiar su comportamiento (el CUIT vacío del perfil sigue permitido, con el mismo mensaje y código).
- **Servicios de clientes** (`comercial/servicios/clientes.py`): `alta_cliente`, `reactivar_cliente`, `modificar_cliente`, `baja_cliente`, `buscar_clientes`,
  `ficha_del_cliente`, `acciones_permitidas`, `DatosDeCliente.desde_post` y las tres funciones que completan otras tareas (`direcciones_en_uso`,
  `impide_quitar_el_correo`, `pendientes_del_cliente`, neutras).
- **Servicios de vehículos** (`comercial/servicios/vehiculos.py`): alta, modificación, reactivación, baja, búsqueda, ficha, `transportistas_disponibles`,
  `texto_capacidad`, `entregas_a_realizar_del_transportista` y `carga_maxima_asignada` (neutras, las completa COM-05) y los dos registrantes.
- **Pantallas:** «Comercial» con las pestañas «Clientes» y, solo para el Gerente, «Vehículos»; lista, ficha, formulario y ventana de baja de cada uno; los tres
  fragmentos de dirección (solo GET); el ícono `cart`; la entrada «Comercial» del menú; `config/urls.py` y `core/tests/urls_prueba_acceso.py`.
- **Registros en `ready()`** (con guarda contra el doble registro): «Logística» (`registrar_logistica_de_transportista`), el «Vehículo» de la ficha de la
  cuenta y de «Mi perfil» (`registrar_datos_de_cuenta`) y el cargador de datos de verificación (orden 20).

**Pruebas** (M1)

- `python manage.py test comercial maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: 2223 pruebas, OK.
- `python manage.py test comercial --keepdb --tag concurrencia`: 10 pruebas, OK. Además, `maestros --tag concurrencia`: 38, OK (se tocaron el alta y la
  modificación del invernadero).
- `makemigrations --check --dry-run`: sin cambios. `manage.py check`: sin problemas.
- Corrida extra de toda la suite (sin concurrencia ni migración): 5048 pruebas, OK.
- Pruebas nuevas: `comercial/tests/test_modelos_comercial.py`, `test_com_{alt,mod,baj,cns}_{clt,veh}.py`, `test_clientes_concurrencia.py`,
  `test_vehiculos_concurrencia.py`, `test_clientes_vistas.py`, `test_vehiculos_vistas.py`, `test_logistica.py`, `test_datos_de_cuenta.py`,
  `test_verificacion.py`; y en `maestros`: `test_direcciones.py` y `test_validar_cuit.py`.

**Decisiones:** ninguna nueva (se aplicó D-58, ya vigente). Los contratos de código que fijaron las pruebas (códigos de error, nombres de los campos
del formulario, `DatosDeCliente`, `DatosDeVehiculo`) están anotados en `docs/temas_abiertos.md` (propuesta de M3).

**Una prueba existente de `maestros` se tocó, con permiso del estudiante** (la tarea dice que ninguna se modifica, pero lo pide a la vez el registrante de
`datos_de_cuenta`): `maestros/tests/test_datos_de_cuenta_transportista.py`, clase `DatosDeCuentaDelTransportistaTests`. Esas pruebas usaban los registrantes reales y
esperaban exactamente `[DatoDeCuenta("Invernadero", …)]` y una sola consulta; con el «Vehículo» de `comercial` fallan. Se aíslan con
`mock.patch.object(core.extensiones, "_DATOS_DE_CUENTA", [transportistas.datos_de_cuenta])` en `setUp`. Prueban lo mismo (el registrante de `maestros`) y
nada se debilitó; las pantallas, que siguen con los registrantes reales, pasan sin cambios.

**Pantallas: lo que se corrigió del prototipo** (D-61)

| Qué tenía el prototipo | Qué se hizo | Qué paso o regla lo pide |
|---|---|---|
| El formulario del cliente solo agregaba y desactivaba direcciones | Cada dirección activa se puede corregir (en el lugar, o creando otra si la usa un contrato), desactivar y borrar (solo si nada la usa); se confirma al guardar | Regla 4 y postcondiciones c, d y e de COM-MOD-CLT |
| «Reactivar» activaba al cliente con un clic | Lleva al formulario del alta con los datos guardados, para corregirlos; el Vendedor ve que se avisa al Gerente | Postcondición c y regla 2 de COM-ALT-CLT |
| La caja de dirección urbana no tenía «Referencias» | Se agregó, como en el invernadero | D-39 |
| Las direcciones se cargaban con una caja y un botón «Agregar» que redibujaba todo en el navegador | Bloques de dirección con tipo, provincia, departamento y localidad encadenados por HTMX (`show:none`, sin validar), y «Agregar dirección» y «Actualizar» como botones de envío para que funcione sin JavaScript. Un bloque vacío se ignora | `interfaz.md` («Validaciones e interacción HTMX») y D-58, punto 7 |
| El CUIT repetido y el error del dígito verificador se mostraban al tipear | Se muestran al guardar, junto al campo, con «Abrir su ficha» o «Reactivarlo» | `interfaz.md` y regla 2 de COM-ALT-CLT |
| La razón social o el nombre y el apellido se alternaban con JavaScript | Se alternan con CSS (`:has`), sin JavaScript y sin pedir nada al servidor; se descarta lo del tipo no elegido | Regla 3 de COM-ALT-CLT |
| La lista de clientes filtraba al tipear | Formulario GET común con «Filtrar», que funciona sin JavaScript | `interfaz.md` |
| La lista de clientes traía «Contratos vigentes»; la ficha, «Deuda» y «Contratos» con datos de ejemplo | No se muestran hasta que existan (COM-02, COM-03, COM-06, COM-08) | D-25; «Solo prototipo» de `clientes.md` |
| La lista de vehículos no tenía búsqueda ni filtros | Búsqueda por patente, tipo o transportista, y filtros por estado y por invernadero; columna «Situación»; sin «Entregas a realizar» (la suma COM-05) | Regla 1 de COM-CNS-VEH |
| «Marca y modelo» era un solo campo y la patente no se podía cambiar al modificar | Dos campos obligatorios; la patente se puede cambiar | MD-129 y precondición c de COM-MOD-VEH |
| No había ficha del vehículo | Se armó con el estilo de la ficha del cliente: datos, transportista, invernadero y situación | Regla 2 de COM-CNS-VEH |
| «Reactivar» un vehículo no decía qué pasaba con el transportista | El aviso dice que queda sin transportista; «Dar de baja» se explica en la ventana y no ofrece confirmar con la ruta iniciada o con entregas a realizar | Postcondición c de COM-MOD-VEH y precondiciones b y c de COM-BAJ-VEH |
| El transportista sin invernadero no tenía aviso | El formulario avisa «No recibe entregas hasta que se lo agregue a un invernadero, en "Logística".» | «Transportista» de `vehiculos.md` |
| Sin estados vacíos ni foco | Estados vacíos con cómo empezar, Enter guarda (el primer botón del formulario es el de guardar, no «Agregar dirección») y foco inicial en las ventanas | `interfaz.md` |
| El menú del prototipo pone «Comercial» antes de «IoT» | Queda después de «IoT» (cada app se registra después de «Producción» en el orden de `INSTALLED_APPS`, y una prueba de `iot` pide «IoT» justo después de «Producción») | Paso 5 de la tarea; sin cambios en `core` |

**Datos que quedaron cargados en la base local** (`python manage.py cargar_datos_de_verificacion --solo comercial`, contraseña de `CLAUDE.local.md` por
la variable de entorno; idempotente)

- Cuentas (todas con la contraseña de quien trabaja): `vendedor@prueba5.local`, `transportista@prueba5.local` (agregado a «Invernadero Comercial» desde «Logística»)
  y `transportista2@prueba5.local` (sin invernadero). El Gerente es el de la base (solo puede haber uno activo, D-09).
- «Invernadero Comercial», sin personal.
- Clientes: «Verdulería Los Pinos S.R.L. (prueba)» (CUIT 30-50000001-1, con correo, teléfono y dos direcciones: una urbana y una rural, cargado por el Vendedor);
  «Marta Gómez (prueba)» (física, 20-50000003-2, sin correo ni direcciones); «Cerrado S.A. (prueba)» (30-50000004-6, dado de baja).
- Vehículos: `ZZZ999` (furgón, dado de baja). **No** se carga la camioneta `AE123CD` de los pasos 7 a 9: la registra la persona.
- Se aplicaron las migraciones nuevas a la base local (`migrate`); no se borró ni se tocó nada.

**Diferencias con lo escrito (van a `docs/temas_abiertos.md`)**

- La cuenta del segundo Transportista es `transportista2@prueba5.local` (el patrón `<rol>@prueba<N>.local` no alcanza para dos del mismo rol).
- `docs/patrones/datos_de_verificacion.md` dice «Hoy: `maestros` (orden 5, MAE-02d) e `iot` (orden 10)» y que la siguiente app usa `prueba4`: ya están `produccion` (orden 15,
  `prueba4`) y ahora `comercial` (orden 20, `prueba5`).
- La rama de «dirección en uso» de `modificar_cliente` (crear otra, dejar la anterior inactiva, no borrar) ya está escrita y probada con `mock.patch`: COM-02 y COM-03 solo
  reescriben `direcciones_en_uso`. El extracto la daba por completar en esas tareas.
- Si se desactiva o se borra una dirección, su corrección (que el formulario manda siempre, sin cambios) se ignora: `modificar_cliente` y `reactivar_cliente` lo resuelven en
  el servicio.
- Código y nombres que fijaron las pruebas: `DatosDeCliente` (`desde_post` con `nueva-<i>-<campo>`, `corregida-<id>-<campo>`, `desactivar` y `borrar`), `DatosDeVehiculo`,
  códigos `cuit_de_cliente_activo|inactivo` (con `params["cliente_id"]`), `direccion_repetida`, `direccion_invalida`, `direccion_en_uso`,
  `correo_con_suministro_vigente`, `patente_invalida|repetida`, `capacidad_invalida`, `capacidad_menor_que_la_carga`, `transportista_invalido|con_vehiculo|con_entregas`,
  `vehiculo_en_ruta|inactivo|no_inactivo` y `cambio_simultaneo`.
- Textos de las notificaciones de vehículo (el extracto da «con {tipo} {patente} ({capacidad} kg)»): «Desde ahora hacés tus entregas con camioneta AE123CD (800 kg).», con el
  tipo en minúscula.
- Los vehículos se bloquean con las cuentas primero (quien actúa y los transportistas que entran o salen, en una consulta y por id) y después el vehículo; como hay un solo
  Gerente activo, todo el ABM de vehículos queda serializado por su cuenta. La restricción de la base respalda la patente y el transportista.
