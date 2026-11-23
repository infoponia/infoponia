# Casos de uso · usuarios · El rol Contador (cambios sobre USR-ALT/MOD/BAJ/CNS-USR, SEG-13 y SEG-15)

Extracto **de cambios**, no de casos de uso completos. Los casos de uso de cuentas ya están en `docs/casos_de_uso/usuarios.md` y
funcionan hoy para seis roles; este archivo dice qué se les suma por el rol nuevo. Fuente: `pendientes_para_pegar.md` (MD-114, ítem 2.A-11)
y `decisiones_A0.md` (X3, H2, H12, H23, pasada general punto 5). **Esas decisiones ganan** aunque todavía no estén en los documentos de
Drive (regla del estudiante del 23/11/2026). Decisión de implementación: **D-85**. Tarea: **USR-11**.

Si este archivo y `usuarios.md` difieren en lo que se dice del rol, **manda este** y se anota en el «Cierre».

## Qué dice la fuente

> Se agrega el rol **Contador**: uno solo activo a la vez (restricción como la del Gerente, MD-55). Registra asientos manuales y
> contraasientos, registra pagos a proveedores (H23), cierra los ejercicios (H2.1) y consulta el libro de gestión. Sin Contador activo,
> lo reemplaza el Gerente en todo eso. El Vendedor deja de registrar asientos y deja de recibir su aviso (H12). El Gerente siempre
> consulta el libro y es notificado de cada contraasiento (X3/C10). Mejora futura: varios Contadores.

Reemplazo del Contador (pasada general, 2.A-11): como el del Gerente. Lo pendiente pasa al nuevo y **las bandejas se calculan** (MD-114, MD-55).

## Cambios por caso de uso

| Caso de uso | Qué cambia |
|---|---|
| USR-ALT-USR (Alta de cuenta) | El rol «Contador» aparece entre los que el Gerente puede dar de alta. Un solo Contador activo: si ya hay uno, se rechaza con el mismo tipo de mensaje que el segundo Gerente («Ya hay un Contador activo: dalo de baja antes»). El alta bloquea todas las filas de Contador (`_bloquear_contadores`, como `_bloquear_gerentes`). |
| USR-MOD-USR | Igual que cualquier rol que no cambia: el rol no se modifica (D-11). Sin reglas nuevas. |
| USR-BAJ-USR | El Gerente da de baja al Contador sin impedimento (a diferencia del Gerente, que no se puede dar de baja con la organización sin otro). Queda la regla «sin Contador activo, el Gerente hace lo del Contador». |
| USR-REA / reactivación | Reactivar a un Contador con otro activo se rechaza (mismo bloqueo que el alta). |
| USR-CNS-USR (lista y ficha) | El rol aparece en los filtros y en la ficha; sigla `CON` en el avatar. Alcance: el Gerente gestiona; el Administrador no ve ni gestiona al Contador. |
| SEG-13 (alcance por rol) | El Contador entra al Panel de control y a «Contabilidad» (y, a través de ella, a «Pagos a proveedores»). **No** tiene acceso a Estadísticas (H28), ni a producción, comercial, inventario ni maestros. Interfaz de escritorio. |
| SEG-15 (invariantes) | Nuevo invariante: a lo sumo un Contador activo (restricción de base `un_solo_contador_activo` + bloqueo + `clean()`). |
| COM-ATN-ENR, postcondición b | El Vendedor deja de recibir el aviso «registrar asiento manual»; lo recibe quien registra asientos (`responsable_contable`). **Se aplica en CON-04d**, no en USR-11. |
| MD-31 (asiento manual) | Queda reemplazado en su actor: lo registra el Contador, o el Gerente si no hay Contador activo. |

## Cómo se aplica (código)

Ver D-85 completa. Resumen operativo, para quien programa USR-11:

- `core/models.py`: `Usuario.Rol.CONTADOR`, clase `Contador(RolFijoMixin, Usuario)` con `ROL = Usuario.Rol.CONTADOR`, restricción parcial
  `un_solo_contador_activo`, `ROLES_OPERATIVOS` lo incluye solo (derivado de `Rol.values`, no hay que tocarlo).
- `core/servicios.py`: `_bloquear_contadores()`, copia de `_bloquear_gerentes`, llamada en el alta y la reactivación cuando el rol es Contador;
  la constante `RESTRICCION_UN_SOLO_CONTADOR_ACTIVO` y su traducción a un mensaje legible.
- `core/menu.py` y `core/acceso.py`: el menú y las pantallas del Contador (`Panel de control`; `Contabilidad` aparece en CON-03a).
- `core/admin.py`: reconocer el rol nuevo en lo que ya enumera los otros.
- `contabilidad/servicios/responsables.py`: las cuatro funciones de D-85, punto 5 (las crea USR-11 porque el rol es de `core` y las
  necesitan todas las tareas posteriores; **`contabilidad` importa de `core`, nunca al revés**, regla A1).
- Pruebas: `core/tests/` (alta, reactivación, un solo activo, concurrencia de dos altas a la vez, auditoría, menú) y
  `contabilidad/tests/test_responsables.py`.

**Lo que NO hace USR-11:** ninguna pantalla de contabilidad, ni el cambio del aviso de COM-ATN-ENR (CON-04d).
