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

1. Entrá como Gerente, creá un Contador. Intentá crear otro: debe rechazarlo con un mensaje claro.
2. Dá de baja al Contador y creá uno nuevo: debe dejarte.
3. Entrá como Contador: ves el Panel de control y nada de estadísticas.

## Cierre (M3)

Actualizá `docs/tareas/README.md` (fila de USR-11), `docs/tareas/ronda_contabilidad_1.md`, `docs/estado.md`, y anotá en el «Cierre» las
diferencias con `usuarios.md`. Cerrá en `docs/disparadores.md` lo que corresponda («Cuando exista el rol Contador»).
