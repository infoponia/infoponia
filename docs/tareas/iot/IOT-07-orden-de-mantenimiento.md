# IOT-07 · Orden de mantenimiento automática, su cancelación y el traspaso del Técnico

Estado: pendiente | App: iot (y una migración en produccion) | Rama: feature/iot-07-orden-de-mantenimiento | Ronda: IoT 1

Depende de: **IOT-06** (con ella vienen IOT-02 a IOT-05: el escalamiento de los comandos, `volver_a_activar`, las bajas y sus funciones
`mantenimientos_a_realizar`) y **PRD-01** (`OrdenTrabajo` con el valor `mantenimiento` de su tipo, `siguiente_numero`, `cancelar_orden_incluida`
para cualquier tipo, las listas y la bandeja filtradas por tipo, el registrante del traspaso del Capataz y la acción `cancelacion_orden`;
D-67, punto 1). Si alguna no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** Cuando un comando agota sus intentos, además de dejar el actuador fuera de servicio y avisar con la alerta (IOT-05),
InfoPonia **crea una orden de mantenimiento** para el Técnico del invernadero y se la avisa. La orden se ve en la ficha del equipo y en el
Inicio del Técnico. El Agrónomo la **cierra cancelándola**: desde la ficha o al volver a activar el equipo. Al cambiar el Técnico del
invernadero, las órdenes pasan al nuevo. Planificar y concretar mantenimientos es de la etapa 2 (D-73): acá no se hace.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| IOT-RSV-CMD | Resolver comando: **postcondiciones k y l, extensiones 4b.4, 4b.4a y 4b.4b** | docs/casos_de_uso/iot/resolver_comando.md | Lo demás es de IOT-05 |
| IOT-MOD-HDW | Modificar hardware: **regla 8 y postcondiciones b y e** (las órdenes) | docs/casos_de_uso/iot/hardware.md | Lo demás es de IOT-02 |
| IOT-CNS-HDW | Consultar hardware: **regla 6** (las órdenes de la ficha) | docs/casos_de_uso/iot/hardware.md | Lo demás es de IOT-02 a IOT-06 |
| IOT-BAJ-HDW, IOT-BAJ-SIS | Bajas: **precondición d** | docs/casos_de_uso/iot/hardware.md, sistema_iot.md | Lo demás es de IOT-06 |
| PROD-CNL-ORD | Cancelar orden, **para un mantenimiento** (4d, 8a, 8e, 9a, j, k, m), desde la ficha del equipo | docs/casos_de_uso/produccion/cancelar_orden.md | Con el alcance del IoT (D-79, punto 2) |
| PROD-MOD-INV, USR-BAJ-USR | Traspaso del Técnico (regla 3, postcondición b) y lo asignado a su cuenta (regla 4) | docs/casos_de_uso/iot/mantenimiento_automatico.md | Lo ejecutan `maestros` y `core` |

**El extracto de la tarea es `docs/casos_de_uso/iot/mantenimiento_automatico.md`**: junta lo de todos y dice cómo se aplica.

## Leer

- Casos de uso:
  - `mantenimiento_automatico.md` **completo**;
  - de `resolver_comando.md`: la extensión 4b y sus 4b.4a y 4b.4b, las postcondiciones h a m y q, las reglas «Escalamiento», «Orden de
    mantenimiento automática» y «Alerta «comando fallido»», y de «Cómo se aplica», «El resultado» (el punto `fallo` en el último intento)
    y «El retiro» (punto 5);
  - de `hardware.md`: IOT-MOD-HDW (postcondiciones b y e, reglas 7 y 8), IOT-BAJ-HDW (precondición d, regla 2) y la regla 6 de
    IOT-CNS-HDW; de «Cómo se aplica», «Modificar (MOD)» (volver a activar), «Baja (BAJ, IOT-06)», «Consulta (CNS)» y «Auditoría»;
  - de `sistema_iot.md`: IOT-BAJ-SIS (precondición d, regla 4) y su parte de «Cómo se aplica»;
  - de `docs/casos_de_uso/produccion/cancelar_orden.md`: las extensiones 4d, 6a, 8a, 8e y 9a, las postcondiciones j, k y m, «Reglas de
    negocio» y, de «Cómo se aplica en la ronda «Producción 1»», «Permisos», «Bloqueos», «Motivo obligatorio», «Notificación» y «Desde otro
    caso de uso».
- Modelo: docs/modelo/iot.md («MantenimientoTecnico», «AlertaIot», «Tipos de alerta del IoT»); docs/modelo/produccion.md («Listas
  fijas» y «OrdenTrabajo», con sus restricciones).
- Decisiones: **D-79**, **D-73**, D-67 (solo el punto 1), D-53 (puntos 5 y 6), D-78 (puntos 10 y 11), D-52 (punto 3, el código de la orden), D-62, D-28, D-30,
  D-36, D-37, D-42, D-43, D-44, D-61.
- API: docs/api/produccion.md (secciones 1, 2, 3 y 5, y de la 9 solo «Lo que deja hecho PRD-01»); docs/api/alertas.md (secciones 2 y 3); docs/api/notificaciones.md.
- Patrones: docs/patrones/bloqueos.md, docs/patrones/auditoria.md.
- Pantallas: docs/prototipos/iot/ — leé primero su `README.md`. Funciones: `failCmd`; en `hardware`, la rama `hw-ficha`; en `modalHtml`,
  `react:<id>`, `baj:<id>` y `baj` (del sistema) (referencia, D-61).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - todo `iot/` (lo que dejaron IOT-01 a IOT-06), en particular `iot/servicios/comandos.py` (el escalamiento y la función que asegura la
    alerta «comando fallido»), `hardware.py` (`volver_a_activar`, `mantenimientos_a_realizar`, `ficha_del_equipo`), `sistemas.py`
    (`ordenes_a_realizar_del_sistema`) y `alcance.py`;
  - `produccion/models.py` (`OrdenTrabajo` y sus restricciones) y `produccion/servicios/ordenes.py` (`siguiente_numero`,
    `cancelar_orden_incluida`, el registrante del traspaso del Capataz);
  - `maestros/extensiones.py` (`registrar_traspaso`, su «CONTRATO») y `maestros/servicios/invernaderos.py` (`modificar_invernadero`, cómo
    llama al traspaso);
  - `core/extensiones.py` (`registrar_seccion_de_inicio`, `registrar_asignaciones_de_cuenta`) y `core/notificaciones.py`.

## Límites

- Crea modelos: **`MantenimientoTecnico`** (hija de `produccion.OrdenTrabajo`, en `iot`). → revisá docs/disparadores.md: cierra «Cuando
  exista SistemaIoT», punto 0 del traspaso del Técnico; la parte de IOT-07 de los puntos 2 y 3 de «Cuando existan actuadores, comandos y
  reglas del IoT»; y, de «Cuando exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido», punto 1, la parte del Técnico.
- Migraciones:
  - `produccion`: `00NN_ordentrabajo_prioridad_en_mantenimiento` (solo el `CheckConstraint` `ordentrabajo_prioridad_en_mantenimiento`; el
    valor `mantenimiento` de `OrdenTrabajo.Tipo` ya lo creó PRD-01, D-67 punto 1);
  - `iot`: `00NN_mantenimiento_tecnico`, que depende de la anterior.
  **Ninguna en `core`** ni de datos.
- Permitido fuera de la app:
  - `produccion/models.py`: solo la restricción de la prioridad, con su migración (D-73, punto 3; D-67, punto 1). **Nada más de
    `produccion`**: que `cancelar_orden_incluida` acepte un mantenimiento y que la bandeja y las listas no lo muestren **ya lo dejó hecho y
    probado PRD-01** (`docs/api/produccion.md`, sección 9, «Lo que deja hecho PRD-01»). Verificalo leyendo el código; si no está, frená y
    avisá (es un error de PRD-01, no algo para completar acá);
  - `maestros/extensiones.py`: solo si `traspasar` no le entrega el rol a quien registra (corrección chica prevista en
    `docs/disparadores.md`, «Cuando exista SistemaIoT», punto 0). Hoy ya lo entrega;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_iot_1.md` y `docs/estado.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: planificar y concretar mantenimientos (CU-05 y CU-06, etapa 2, D-73); reservar repuestos; la bitácora y el consumo del
  mantenimiento (R056, R135); cancelar desde la lista de órdenes de `produccion` o desde el detalle de la alerta (D-79, punto 1).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelo y migraciones** («Modelo y migraciones» del extracto). Pruebas (`iot/tests/test_modelos_mantenimiento.py`):
   - crear una orden le pone `tipo = mantenimiento`, y su código es `OT-NNNN`;
   - un mantenimiento sin prioridad no se guarda (`IntegrityError`, la restricción);
   - una siembra sin prioridad se sigue guardando;
   - `tecnico` es obligatorio;
   - una orden de la fábrica tiene al menos un equipo (prueba de invariante).
   Prueba de migración (`@tag("migracion")`): las dos migran y vuelven atrás.
2. **Lecturas** (`mantenimientos_a_realizar`, `ordenes_a_realizar_del_sistema`, `mantenimientos_del_equipo`,
   `mantenimientos_a_realizar_del_tecnico`). Pruebas: el orden, que una cancelada no cuenta, sin consultas por fila
   (`assertNumQueries` con 1 y con 5 órdenes). Con datos reales, corré de nuevo **todas** las de `test_iot_baj_hdw.py` y
   `test_iot_baj_sis.py`, y sumá los casos de la precondición d con sus textos.
3. **La orden al escalar** (`crear_orden_automatica`; «La orden al escalar»). Pruebas (`test_iot_rsv_cmd_mantenimiento.py`):
   - postcondición k, con cada campo: Técnico, equipo, alerta, sin Agrónomo, «Revisión», alta, hoy y la descripción;
   - l: el aviso, y sin aviso con el Técnico inactivo (con la orden creada igual);
   - 4b.4a, 4b.4b y los tres sufijos de la alerta;
   - el recorte a 200 con un detalle largo (el sufijo queda entero);
   - el escalamiento **por «sin respuesta»** en el retiro también crea la orden;
   - un rechazo (4f) no crea ninguna orden;
   - la auditoría con la orden como afectado;
   - todo o nada: si el aviso falla, no queda ni la orden ni el comando «fallido».
   Corré además **todas** las de `test_iot_rsv_cmd.py`: tienen que dar lo mismo, salvo el texto de la alerta, que ahora lleva el sufijo.
4. **Cancelar desde la ficha** (`resumen_de_cancelacion_de_mantenimiento`, `cancelar_mantenimiento`; «Cancelar la orden desde la
   ficha»). Pruebas (`test_cancelar_mantenimiento.py`):
   - permisos: el Agrónomo a cargo; el Gerente sin Agrónomo activo, sí; con Agrónomo activo, no; otro Agrónomo, no;
   - el motivo vacío y el de 301 caracteres;
   - la orden ya cancelada (8a);
   - j: el equipo sigue «fuera de servicio» y la alerta sigue activa;
   - k con y sin el Técnico activo;
   - m.
5. **Volver a activar** (`volver_a_activar` con `decisiones`; «Volver a activar un equipo con órdenes»). Pruebas
   (`test_iot_mod_hdw_ordenes.py`):
   - cancelar una y mantener otra;
   - sin decisiones con órdenes;
   - una orden de la fábrica con otro equipo fuera de servicio solo se mantiene;
   - las órdenes cambiaron mientras tanto;
   - el aviso de cada cancelada;
   - `reactivacion_hardware` con `ordenes_canceladas` y `ordenes_mantenidas`;
   - sin órdenes, todo igual que en IOT-02.
6. **Traspaso, asignaciones e Inicio** («Traspaso del Técnico», «Asignaciones de la cuenta», «El Inicio del Técnico»). Pruebas
   (`test_traspaso_tecnico.py`, `test_inicio_tecnico.py`), con las **tres pruebas mínimas de cada registrante** (con datos, neutro sin
   datos, sin consultas por fila; `docs/api/produccion.md`, sección 3):
   - `modificar_invernadero` con un Técnico nuevo pasa las órdenes a realizar (no las canceladas) y su aviso dice «mantenimientos técnicos a
     realizar: n»;
   - con el rol vacío y después un Técnico nuevo, las recibe el nuevo;
   - el cambio de Capataz no las toca;
   - la ventana de baja de la cuenta del Técnico las informa;
   - el Inicio del Técnico, con órdenes (y una vencida) y sin órdenes; el de otro rol no tiene la sección.
7. **Pantallas** («Pantallas» del extracto):
   - en la ficha del equipo, la sección «Órdenes de mantenimiento» y la ventana «Cancelar orden»;
   - la ventana de volver a activar con las órdenes;
   - los textos nuevos de las ventanas de baja;
   - la sección del Inicio del Técnico.
   Pruebas (`test_mantenimiento_vistas.py`): permisos y alcance; el Gerente con Agrónomo activo no ve el botón; el flujo con HTMX y sin él;
   ningún botón lleva a un 403. Y **`produccion` no muestra los mantenimientos**: una prueba de punta a punta, con un mantenimiento
   **real** (no una orden suelta), confirma que la bandeja del Capataz, `lista_de_ordenes` y `ordenes_cancelables` no lo incluyen (la
   lógica y sus pruebas son de PRD-01; esta solo confirma que la hija real no cambia nada).
8. **Concurrencia** (`@tag("concurrencia")`, `test_mantenimiento_concurrencia.py`):
   - cancelar desde la ficha y volver a activar a la vez (la orden se cancela una sola vez; la otra operación da su mensaje);
   - dos cancelaciones a la vez;
   - el traspaso del Técnico y una cancelación a la vez;
   - el escalamiento de un comando y la cancelación de la orden anterior del mismo actuador (o se crea una nueva, o la alerta menciona la
     existente; nunca dos a realizar).
9. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
   - en `docs/disparadores.md`: tachar el punto 0 del traspaso de «Cuando exista SistemaIoT»; marcar hecha la parte de IOT-07 de los puntos 2
     y 3 de «Cuando existan actuadores, comandos y reglas del IoT»; y anotar la parte del Técnico en el punto 1 de «Cuando exista
     OrdenTrabajo, MantenimientoIoT, Contrato o Pedido»;
   - marcar IOT-07 en `docs/tareas/README.md` y en `docs/tareas/ronda_iot_1.md`.
   Lo que haya quedado distinto de lo escrito va a `docs/temas_abiertos.md`.

Si el tiempo apremia, lo último que se recorta es la sección del Inicio del Técnico (el aviso alcanza para la postcondición l; se anota en
`temas_abiertos.md`). No se recortan la orden al escalar, sus tres casos, la cancelación, la regla 8, el traspaso ni las pruebas de
concurrencia.

## Hecho cuando

- Un comando que agota sus intentos crea la orden «a realizar» para el Técnico, con prioridad alta y la descripción. La alerta la nombra y
  el Técnico recibe el aviso. Sin Técnico, o con una orden a realizar del actuador, no se crea y la alerta lo dice.
- El Agrónomo cancela la orden desde la ficha, con motivo. El equipo y la alerta no cambian y el Técnico recibe el aviso.
- Volver a activar el equipo deja elegir, por cada orden, cancelarla o mantenerla.
- Las bajas del equipo y del sistema no se confirman con órdenes a realizar.
- Al asignar otro Técnico al invernadero, las órdenes pasan a él. El Técnico ve las suyas en el Inicio.
- Pruebas: `test_modelos_mantenimiento.py`, `test_iot_rsv_cmd_mantenimiento.py`, `test_cancelar_mantenimiento.py`,
  `test_iot_mod_hdw_ordenes.py`, `test_traspaso_tecnico.py`, `test_inicio_tecnico.py`, `test_mantenimiento_vistas.py`,
  `test_mantenimiento_concurrencia.py` y los casos nuevos de `test_iot_baj_hdw.py` y `test_iot_baj_sis.py`.
- Comando de pruebas:
  python manage.py test iot produccion maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test iot --keepdb --tag concurrencia
  python manage.py test iot produccion --keepdb --tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Hay dos migraciones nuevas (`produccion` e `iot`): `python manage.py migrate`. Lo de «Antes de empezar» de `docs/api/nodo/escenarios.md`
(con un Técnico asignado a «Norte» y una sesión suya abierta en otra ventana). Seguí los escenarios 7, 15 y 16, y además:

1. Sin Técnico asignado a «Norte», repetir el escenario 7: no se crea la orden y la alerta dice que el invernadero no tiene Técnico.
2. Volver a activar el ventilador eligiendo «Mantenerla», hacerlo fallar de nuevo: no se crea otra orden y la alerta nombra la existente.
3. Intentar dar de baja el ventilador con la orden a realizar: no deja y explica cómo cancelarla.
4. Como Gerente, con el Agrónomo a cargo activo: la ficha muestra la orden sin «Cancelar orden».
5. Asignar otro Técnico a «Norte» (Datos maestros): el aviso dice «mantenimientos técnicos a realizar: 1» y la orden aparece en su Inicio.
6. En «Auditoría», la orden en `resolucion_comando_iot`, `cancelacion_orden` y `reactivacion_hardware`.

## Cierre (la completa Claude Code al cerrar)
