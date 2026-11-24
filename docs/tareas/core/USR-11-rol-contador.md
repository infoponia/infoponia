# USR-11 · El rol Contador y quién registra los asientos

Estado: pendiente | App: core (y `contabilidad/servicios/responsables.py`) | Rama: feature/usr-11-rol-contador | Ronda: Contabilidad 1

Depende de: — (las tareas de `core` y las apps ya están hechas: PRD-00, CON-01, USR-01…). **Es la primera tarea de la ronda**: CON-02 en
adelante, y todo el módulo de compras, usan «quién registra» (D-85). No empieces ninguna sin esta mergeada.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** Agrega el séptimo rol, **Contador** (uno solo activo, lo gestiona el Gerente, y si falta lo reemplaza el Gerente), y deja
escrita en un solo lugar la regla «quién registra asientos y pagos» para que ningún caso de uso tenga que repetir `if rol == ...`.
Es una tarea **chica** y es la base de todo lo contable.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| USR-ALT-USR | Alta de cuenta (rol Contador) | docs/casos_de_uso/usuarios_rol_contador.md | Solo lo que cambia por el rol nuevo |
| USR-MOD-USR, USR-BAJ-USR, USR-CNS-USR | Modificar, baja, consulta | docs/casos_de_uso/usuarios_rol_contador.md | Idem; la baja del Contador no se bloquea |
| SEG-13, SEG-15 | Alcance por rol e invariantes | docs/casos_de_uso/usuarios_rol_contador.md | Un solo Contador activo; sin acceso a Estadísticas |

(Los códigos y su texto completo están en `docs/casos_de_uso/usuarios.md`; leé este extracto **y** las secciones de esos casos de uso que ya
cumple el código.)

## Leer

- Casos de uso: docs/casos_de_uso/usuarios_rol_contador.md (completo) y, de docs/casos_de_uso/usuarios.md, USR-ALT-USR, USR-BAJ-USR y SEG-15.
- Modelo: docs/modelo/core.md (sección «Contador»; si no existe, D-85 punto 1) — `Usuario`, `RolFijoMixin`.
- Decisiones: D-85 (la de esta tarea), D-01, D-09, D-10, D-11, D-13, D-14, D-36, D-37, D-42.
- API: docs/api/asientos.md, sección «Lectura» (las funciones de `responsables`).
- Patrones: docs/patrones/abm.md, docs/patrones/bloqueos.md (sección del Gerente único), docs/patrones/auditoria.md.
- Pantallas: docs/prototipos/compras_contabilidad/ — leé primero su README; funciones `panelCon`, el selector de rol y el interruptor
  «Hay un Contador activo» (**son del prototipo, no del sistema**).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `core/models.py` (`Usuario`, `Rol`, `RolFijoMixin`, `Gerente`, la restricción `un_solo_gerente_activo`, `ROLES_OPERATIVOS`,
  `Accion`, `ETIQUETAS`), `core/servicios.py` (`_bloquear_gerentes`, alta, baja, reactivación, `RESTRICCION_UN_SOLO_GERENTE_ACTIVO`),
  `core/menu.py`, `core/acceso.py`, `core/admin.py`, `core/notificaciones.py`, y las pruebas de `core` del Gerente único como modelo.

## Límites

- Crea modelos: `core.Contador` (multitabla, igual que los otros cinco roles) → revisá docs/disparadores.md.
- Migraciones: una de `core`, `00NN_rol_contador` (el número libre en `main`): `choices` del rol, la tabla `core_contador` y la restricción
  parcial `un_solo_contador_activo`. Ninguna de datos.
- Permitido fuera de `core`: `contabilidad/servicios/responsables.py` (nuevo) y `contabilidad/tests/test_responsables.py`. Nada más.
- Dependencias nuevas: ninguna.
- Fuera de alcance: cualquier pantalla de contabilidad (CON-03a), el cambio del aviso del Vendedor (CON-04d), el panel del Contador más allá
  de su entrada al menú, y «varios Contadores» (mejora futura).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelo y migración.** `Rol.CONTADOR`, `Contador(RolFijoMixin, Usuario)`, restricción `un_solo_contador_activo`, la migración. —
   pruebas: `core/tests/test_modelos_contador.py` (la restricción rechaza un segundo activo y deja un segundo inactivo).
2. **Servicios.** `_bloquear_contadores`, la llamada en el alta y la reactivación, la traducción del error de la restricción, la baja sin
   impedimento. La auditoría ya registra el alta/baja con el rol. — pruebas: las del ABM de cuentas extendidas, **con concurrencia**: dos altas
   de Contador a la vez (una gana, la otra recibe el mensaje).
3. **`responsables.py`** con las cuatro funciones de D-85, punto 5. — pruebas: `contabilidad/tests/test_responsables.py` (Contador activo;
   sin Contador y con Gerente; sin ninguno → `None`; `puede_registrar_asientos` para cada rol; `notificar_al_responsable_contable` no falla sin
   responsable y respeta `excluir`).
4. **Interfaz.** El rol aparece en el alta, filtros, lista, ficha y el avatar (`CON`); el menú y el control de acceso del Contador (Panel de
   control; sin Estadísticas); el admin. — pruebas de vistas y de acceso por rol.

Si el tiempo apremia, lo último que se recorta es: el admin (se anota como disparador).

## Hecho cuando

- Un Gerente puede dar de alta, modificar, dar de baja y reactivar a un Contador, y no puede haber dos activos ni con dos pedidos a la vez.
- Dado cualquier usuario, `puede_registrar_asientos` responde según D-85; ninguna otra parte del código tiene la regla repetida.
- El Contador entra a su panel y no a otros módulos; el Administrador no lo gestiona.
- Pruebas verdes (incluida `@tag("concurrencia")`), sin migraciones pendientes (`makemigrations --check`).
- Comando de pruebas: `python manage.py test core contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test core --keepdb --tag concurrencia`.

## Verificación a mano

Lo hace el estudiante (D-96). Claude Code no abrió un navegador ni cargó datos: todo lo de abajo se crea a mano.

### Antes de empezar

1. Rama `feature/usr-11-rol-contador`. En PowerShell, con el entorno virtual activo: `python manage.py migrate` (aplica `core` 0035, que crea la
   tabla `core_contador` y el índice `un_solo_contador_activo`) y `python manage.py runserver`. Abrí `http://127.0.0.1:8000/`.
2. Necesitás tres cuentas: el **Administrador** y el **Gerente** que ya tengas en tu base local, y un navegador con ventana privada
   (para tener dos sesiones a la vez). La contraseña de prueba la ponés vos; no la escribas en ningún archivo del repo.
3. **Qué crear a mano, en este orden** (con el Gerente, en «Usuarios y seguridad» → «Nuevo usuario»): un Contador con nombre
   `Carolina`, apellido `Vega`, email `carolina.vega@ejemplo.com`, teléfono vacío, forma de acceso «Contraseña temporal». Anotá la
   temporal que se muestra, que aparece una sola vez. Después, un Vendedor `Mario Rey`, `mario.rey@ejemplo.com`.

### Pasos

1. **Alta del Contador (Gerente).** Entrá como Gerente → «Usuarios y seguridad» → «Nuevo usuario». El desplegable «Rol» tiene que ofrecer
   **Contador** al final de la lista (después de Técnico). Completá los datos del punto 3 de arriba y «Dar de alta». Tiene que aparecer
   «Cuenta creada» con la contraseña temporal. *(Lo cubre el recorrido, paso 2.)*
2. **Un solo Contador activo.** Volvé a «Nuevo usuario», elegí Contador con otro email (`otra.persona@ejemplo.com`) y «Dar de alta».
   Tiene que volver al formulario, con un aviso arriba: «Ya hay un Contador activo: Carolina Vega. Solo puede haber uno a la vez: para dar de
   alta a otro, primero dá de baja al actual desde su ficha.», y con lo que escribiste todavía en los campos. En la lista no aparece la
   cuenta nueva. *(Lo cubren el recorrido, paso 4, y `AltaDeContadorTests`.)*
3. **Lista, filtro y ficha.** En «Usuarios y seguridad», filtrá por rol «Contador»: aparece Carolina Vega con el rol «Contador» y el estado
   «Activo». Abrí su ficha: dice «Contador» y tiene «Modificar», «Restablecer contraseña» y «Dar de baja». *(Recorrido, paso 5.)*
4. **Primer ingreso del Contador.** En una **ventana privada** entrá con `carolina.vega@ejemplo.com` y la temporal. Te lleva a elegir una
   contraseña; elegí una propia. Después llegás al inicio. *(Recorrido, paso 6.)*
5. **Cómo se ve el Contador.** En ese inicio: arriba a la derecha el avatar dice **CON** y «Contador», y el desplegable de cuenta dice
   «Operás como Contador». El menú lateral tiene solo **«Panel de control»**: **no** hay «Estadísticas», «Producción», «Compras»,
   «Comercial», «Usuarios y seguridad» ni «Auditoría». La campana está. «Contabilidad» **todavía no aparece**: la agrega CON-03a.
   *(Recorrido, paso 7.)*
6. **El Contador por la dirección escrita a mano.** Con la sesión del Contador, escribí en la barra `/usuarios/`, `/auditoria/`,
   `/produccion/` y `/compras/pedidos/`. Cada una tiene que mostrar el error 403 («Tu cuenta de Contador no tiene acceso a esta
   pantalla.»). *(Recorrido, paso 8.)*
7. **El Administrador.** Cerrá la sesión y entrá como Administrador → «Cuentas». **No** tiene que aparecer Carolina Vega ni «Contador»
   en el filtro de rol. Si escribís a mano `/usuarios/<id de Carolina>/` (el id está en la dirección cuando el Gerente abre su ficha), da 403.
   *(Recorrido, paso 9.)*
8. **El Gerente es responsable sin Contador, y el Contador lo es cuando existe.** Esto no tiene pantalla todavía (la usan CON-02 y compras):
   lo cubren las pruebas de `responsables`. Solo comprobá que el Gerente **no** pierde nada en su menú por haber un Contador.
   *(`contabilidad/tests/test_responsables.py` y recorrido, pasos 1, 3 y 10.)*
9. **Baja del Contador.** Entrá como Gerente → ficha de Carolina → «Dar de baja». La ventana no lista impedimentos (a diferencia del
   Gerente, no se bloquea por nada) y no dice nada de pendientes. Confirmá: queda «Inactivo». *(Recorrido, paso 10.)*
10. **La sesión del Contador cae.** En la ventana privada, recargá la página: te lleva al inicio de sesión (la cuenta está dada de baja).
    *(Recorrido, paso 11.)*
11. **Reemplazo: baja y alta.** Dá de alta otro Contador (`Otra Persona`, `otra.persona@ejemplo.com`): esta vez te deja.
    *(Recorrido, paso 12.)*
12. **Reactivar con otro activo.** Abrí la ficha de Carolina (inactiva) → «Reactivar». La ventana dice «La cuenta de Carolina Vega
    (Contador) no se puede reactivar: ya hay un Contador activo, **Otra Persona**…» y solo tiene «Ver a Otra Persona» y «Cerrar»: no hay
    botón de confirmar. Si dás de baja a Otra Persona y volvés, ahora «Reactivar» sí ofrece confirmar y deja reactivarla.
    *(Recorrido, paso 13, y `ReactivacionDeContadorTests`.)*
13. **Auditoría.** Como Gerente → «Auditoría»: están el alta, el cambio de contraseña del Contador, las bajas y las reactivaciones, con el
    rol «Contador» en el afectado. El Administrador **no** los ve (son cuentas operativas). *(Recorrido, paso 14.)*
14. **Navegador real (formularios que se envían).** En la ventana normal como Gerente, hacé el alta del paso 1 y la reactivación del paso 12
    **hasta el final** y mirá la consola (F12). Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola, avisá:
    el cliente de Django no ve el CSRF ni el encabezado `Origin`.
15. *(Opcional)* **Sin JavaScript** (desactivalo en el navegador): el alta, la baja y la reactivación siguen funcionando como páginas. **En
    un celular o ventana angosta:** el menú del Contador aparece como chips y las pantallas de cuentas se leen bien.

### Lo que no se prueba a mano

- **Dos altas de Contador a la vez** (y el alta junto a una reactivación): no se puede provocar a mano con fiabilidad. Lo cubren las tres
  pruebas de `ContadorUnicoConcurrenciaTests`, que corren con `--tag concurrencia`.
- **El panel del Contador** (indicadores, pagos pendientes, ejercicio en cierre): es de CON-03a; hoy el inicio es el genérico.

## Cierre

### Qué se hizo

- **Modelo (`core/models.py`) y migración `core` 0035 `rol_contador`.** `Usuario.Rol.CONTADOR`, la clase `Contador(RolFijoMixin, Usuario)` con `clean()`
  de respaldo, y la restricción parcial `un_solo_contador_activo`. La migración crea la tabla `core_contador`, cambia los `choices` (sin SQL) y crea el
  índice único parcial. Ninguna de datos. `ROLES_OPERATIVOS` y los textos de la auditoría lo incluyen solos.
- **Servicios (`core/servicios.py`).** `_bloquear_contadores`, `_contador_activo`, `_error_contador_activo` (código `contador_activo`),
  `RESTRICCION_UN_SOLO_CONTADOR_ACTIVO` y su traducción en el alta y la reactivación; `CONTADOR` en las clases que da de alta el Gerente. La baja no
  cambia (sin impedimento). `gerente_activo_que_impide_reactivar` pasó a llamarse `titular_activo_que_impide_reactivar` y cubre al Gerente y al Contador.
- **`contabilidad/servicios/responsables.py`.** `contador_activo`, `responsable_contable`, `puede_registrar_asientos` y `notificar_al_responsable_contable`.
- **Interfaz.** Menú del Contador (solo «Panel de control», sin Estadísticas), sigla `CON`, admin (`Contador` con `RolAdmin`) y la ventana de reactivación.
- **Auditoría: no hizo falta nada.** El alta y la baja ya registran el rol (`cambios.rol` y `afectados[].rol`), `VALORES_VISIBLES["rol"]` sale de
  `Usuario.Rol.choices` y la clasificación de acciones no cambia: ni acción nueva en `ACCIONES_DE_NEGOCIO` ni migración extra.
- **Base local de desarrollo:** no se tocó. No se borraron datos.

### Pruebas

- `core/tests/test_modelos_contador.py` (4), `core/tests/test_usr_11_rol_contador.py` (19, con 3 de `@tag("concurrencia")`),
  `core/tests/test_rol_contador_vistas.py` (11), `core/tests/test_recorrido_rol_contador.py` (1, de 14 pasos) y
  `contabilidad/tests/test_responsables.py` (12).
- **Una prueba existente cambió** (D-85 la cambia): `test_regla_1_formulario_tiene_select_nativo_con_los_cinco_roles` de `test_usr_alt_usr.py` pasó a
  `..._con_los_seis_roles` y espera `contador` al final de la lista. No se debilitó: sigue comparando la lista exacta.
- Comando 1: `python manage.py test core contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **782 pruebas, OK**.
- Comando 2: `python manage.py test core --keepdb --tag concurrencia` → **19 pruebas, OK**.
- También corrieron, por tocar listas de roles y menús: `maestros` (`test_cns_alr`, `test_alerta`), `comercial` (`test_clientes_vistas`), `iot`
  (`test_tipos_actuador_vistas`) y `produccion` (`test_eventos_vistas`): 289 pruebas, OK. La suite completa la corre el CI.

### Decisiones

Ninguna nueva: todo sale de D-85. No hace falta una decisión.

### Diferencias con la documentación

- **Con `usuarios.md`** (manda `usuarios_rol_contador.md`): las reglas 1 de USR-ALT/MOD/BAJ/CNS-USR dicen «Agrónomo, Capataz, Vendedor, Transportista y
  Técnico»; ahora son seis con el Contador. SEG-15 dice «nunca más de un Gerente activo»; ahora también «de un Contador activo».
- **`docs/api/asientos.md`, tabla «Lectura»:** lista tres funciones de `responsables` y D-85 punto 5 define cuatro; falta `contador_activo()`.
- **`docs/estado.md`:** dice «COM-04a en rama, falta PR», pero #73 ya está mergeado.
- **Dónde está modelado `Usuario`/`Rol`:** no existe `docs/modelo/core.md` (la tarea lo remite a D-85 punto 1). Hoy el rol está en D-01, D-09, D-10, D-11,
  D-85, en `usuarios.md` y en `docs/modelo/contabilidad.md` (MD-114, R010, glosario).

### Pantallas: lo que se corrigió del prototipo (D-61)

- **«Compras» en el menú del Contador.** El prototipo (`NAV.con`) le da «Panel de control», «Compras» y «Contabilidad». No lo hice: D-85 punto 6 dice «Panel de
  control» y «Contabilidad» (y, desde ella, los pagos), sin Compras, y las dos entradas las agregan CON-03a y compras. Hoy el menú queda en «Panel de control».
- **El interruptor «Hay un Contador activo» y el selector «ver como»** son solo del prototipo: no se implementan. El sistema lo calcula desde las cuentas.
- **La ventana «No se puede reactivar»** estaba escrita para el Gerente. Ahora sirve a los dos roles (dice «ya hay un Gerente/Contador activo»); el texto
  del Gerente no cambia.
- **El panel del Contador (`panelCon`)** no se hizo: es de CON-03a (los indicadores y la alerta del ejercicio en cierre).

### Verifiqué (recorrido y migraciones)

- **Recorrido** (`RecorridoDeRolContadorTests`, cliente de Django): alta, segundo alta rechazada, lista y ficha, primer ingreso con la temporal, marco y menú del
  Contador, 403 en otros módulos, el Administrador sin acceso, baja, reemplazo, reactivación rechazada y auditoría. **OK.**
- **Migración:** `makemigrations --check` sin cambios. `sqlmigrate core 0035` crea la tabla `core_contador` con su FK y el índice único parcial
  `un_solo_contador_activo`; el `AlterField` de los `choices` es no-op; no borra ni reescribe datos. Se aplicó en la base de pruebas (las pruebas corrieron
  sobre ella). **OK.**

### Lo cubre una prueba

- Un solo Contador activo, la restricción y el respaldo `clean()`: `ModeloContadorTests`.
- Alta, reactivación, baja y alcance: `AltaDeContadorTests`, `ReactivacionDeContadorTests`, `BajaDeContadorTests`, `ConsultaDeContadorTests`.
- **Concurrencia** (dos altas a la vez, con y sin Contador previo; alta con reactivación): `ContadorUnicoConcurrenciaTests`.
- Quién registra asientos y quién recibe el aviso: `ResponsablesTests`.
- Menú, marco, 403 en otros módulos, ventana de reactivación y auditoría visible: `RolContadorVistasTests`.

### No pude verificar

- **Cómo se ve en un navegador:** el aspecto, el avatar «CON», el foco y el CSRF/`Origin` de los formularios (pasos 5 y 14 de la verificación a mano).
- **Despliegue:** que Render aplique `core` 0035 en Neon.
- **Qué hará el Gerente sin Contador en las pantallas de contabilidad:** todavía no existen (CON-02 y CON-03a); solo está probada la regla.

### Cierre de documentación (M3)

Aplicado el 24/11/2026 a pedido del estudiante: `docs/estado.md`, `docs/tareas/README.md`, `docs/tareas/ronda_contabilidad_1.md`, `docs/historial.md`,
`docs/revisiones_pendientes.md`, `docs/api/asientos.md` (fila `contador_activo()`), `docs/disparadores.md` y `docs/temas_abiertos.md`. Queda sin hacer, a la
espera de su decisión, la creación de un `docs/modelo/core.md`.
