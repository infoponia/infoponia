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
   - crear una orden le pone `tipo_orden = mantenimiento`, y su código es `OT-NNNN`;
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

**Qué cubre ya una prueba (para que, si tenés poco tiempo, te concentres en lo que se ve y se siente):** el recorrido `iot/tests/test_recorrido_mantenimiento.py` hace todo el flujo con el cliente de Django (escalamiento con y sin Técnico, ficha por rol, cancelar con y sin motivo, volver a activar con «Mantenerla» y con «Cancelarla», orden con otro equipo fuera de servicio, baja bloqueada, traspaso del Técnico, Inicio del Técnico y Gerente sin Agrónomo). Lo que **no** ve es el navegador (CSRF y `Origin`, JavaScript, el aspecto): para eso son los pasos 8 y 9.

### Antes de empezar

1. Terminal con el entorno activo: `.venv\Scripts\Activate.ps1`. Hay **dos migraciones nuevas** (`produccion` 0007 e `iot` 0005): `python manage.py migrate`. Después, `python manage.py runserver` y abrí `http://127.0.0.1:8000/`.
2. Lo de «Antes de empezar» de `docs/api/nodo/escenarios.md` (Node-RED, `revision_iot --cada 30`, reintentos 1 e intervalo 10 s en Configuración operativa · Módulo IoT; al terminar, volver a 3 reintentos, 60 s y 3 lecturas). Con cuentas que ya usás (la contraseña de siempre; no la escribas en ningún archivo):
   - **Gerente** (el administrador no sirve: no tiene módulo IoT).
   - Un **Agrónomo** a cargo de «Norte» y un **Técnico** (por ejemplo «Tomás Quiroga») asignado a «Norte».
   - Un **segundo Técnico** sin asignar (por ejemplo «Nora Paz»; Datos maestros · Personal) y, para el paso 7, un invernadero «Libre» **sin Agrónomo y sin Técnico** con su sistema IoT y un actuador (si no querés crearlo, salteá el paso 7: lo cubre el recorrido).
3. **Ventana privada** con la sesión del Técnico de «Norte», abierta en el Inicio (`/`). Tiene que decir «Mantenimientos a realizar» solo cuando haya órdenes.
4. Un actuador «Ventilador» de «Norte» con identificador `norte/ventilador`, activo.

### Pasos

1. **Escenario 7 (la orden nace).** Con Node-RED en «Fallar cada intento», emití desde IoT · Comandos «Ventilador · Encender». Cuando se agoten los intentos: comando «Fallido», ventilador «Fuera de servicio» y, en la campana y en Monitoreo, la alerta crítica «Comando fallido» cuyo texto termina en **«· Orden de mantenimiento OT-NNNN asignada a Tomás Quiroga.»**. En la ventana privada del Técnico, la campana trae «Orden OT-NNNN de mantenimiento asignada» y el Inicio muestra la orden (con «Vencida» si la fecha ya pasó). *Lo cubre el recorrido, salvo el aspecto.*
2. **La ficha.** IoT · Hardware · `norte/ventilador`: sección **«Órdenes de mantenimiento»** con la orden: código, «Revisión», «A realizar», «Alta», fecha programada de hoy, «Tomás Quiroga» y la descripción («CMD-N · Encender no se ejecutó en 4 intentos. Último resultado: …»). Tiene que verse el botón **«Cancelar orden»**.
3. **Por rol (qué ve cada uno).**
   - Como **Gerente** (con el Agrónomo activo): la ficha muestra la orden **sin** «Cancelar orden». Escribí a mano `/iot/hardware/<id del ventilador>/ordenes/<id de la orden>/cancelar/`: da «403».
   - Como **Técnico** (otra ventana): `/iot/hardware/<id>/` da 403. Como Capataz o Vendedor, igual.
   - Como **otro Agrónomo** (sin «Norte»): da 404.
   - Entrá como Gerente a «Libre» sin Agrónomo activo: ahí sí ve «Cancelar orden».
4. **Dar de baja con la orden.** Como Agrónomo, en la ficha, «Dar de baja»: la ventana dice «Está en la orden de mantenimiento OT-NNNN, a realizar: cancelala desde «Órdenes de mantenimiento», en la ficha del equipo.» y **no tiene botón de confirmar**. IoT · Sistema IoT · «Dar de baja el sistema»: «Hay 1 orden(es) de mantenimiento a realizar (OT-NNNN): cancelalas desde la ficha de cada equipo.», también sin confirmar. *Lo cubren `test_mantenimiento_vistas.py` y el recorrido.*
5. **Escenario 15 (cancelar).** En la ficha, «Cancelar orden»:
   - La ventana muestra el código, «Revisión», el equipo, «Tomás Quiroga», «Sin repuestos reservados», el aviso «La alerta «comando fallido» sigue activa…» y el campo «Motivo de la cancelación».
   - «Confirmar» **sin motivo**: vuelve la ventana con «Indicá el motivo de la cancelación.».
   - Con 301 caracteres: «El motivo no puede pasar de 300 caracteres.» y conserva lo escrito.
   - Con «Se revisó el ventilador»: vuelve a la ficha con «OT-NNNN cancelada.»; la orden figura «Cancelada» con «Motivo: Se revisó el ventilador» y sin botón. El ventilador **sigue «Fuera de servicio»** y la alerta **sigue activa**. El Técnico recibe «…cancelada» y la orden **desaparece** de su Inicio.
   - En Auditoría: un registro `cancelacion_orden` con la orden como afectada y, en los datos, «cancelada_desde: iot» y los equipos de la orden.
6. **Escenario 16 (volver a activar).** Volvé a activar el ventilador desde la ficha (sin órdenes a realizar es la ventana de siempre y resuelve la alerta). Hacelo fallar de nuevo (paso 1): nace una orden nueva. «Volver a activar»:
   - La ventana lista **una fila por orden** con «Cancelarla» marcada de entrada y «Mantenerla».
   - «Confirmar» sin elegir nada no es posible desde la pantalla (viene una opción marcada): el mensaje «Elegí qué hacer con cada orden de mantenimiento.» lo cubren `test_iot_mod_hdw_ordenes.py` y `test_mantenimiento_vistas.py`.
   - Elegí **«Mantenerla»**: el ventilador queda «Activo», la alerta se resuelve y la orden sigue «a realizar». Hacelo fallar otra vez: **no** se crea otra orden y la alerta dice «Ya está en la orden de mantenimiento OT-NNNN, a realizar.» (y el Técnico no recibe un segundo aviso).
   - Volvé a activar eligiendo **«Cancelarla»**: queda «Activo», la alerta resuelta y la orden «Cancelada» con el motivo «Se volvió a activar el equipo norte/ventilador.»; el Técnico recibe el aviso. En Auditoría: `reactivacion_hardware` con `ordenes_canceladas` y `ordenes_mantenidas`.
7. **Sin Técnico (lo hace el invernadero «Libre»).** Hacé fallar su actuador: **no se crea orden** y la alerta termina en «· El invernadero no tiene Técnico: la orden de mantenimiento deberá planificarse cuando se asigne uno.». *Lo cubre el recorrido.*
8. **Traspaso del Técnico.** Con una orden «a realizar» en «Norte», como Gerente: Datos maestros · Invernaderos · «Norte» · Modificar, cambiá el Técnico a «Nora Paz» y confirmá la ventana de personal (tiene que decir «mantenimientos técnicos a realizar: 1»). En la sesión de Nora, el aviso «Quedó a cargo de Norte» menciona **«mantenimientos técnicos a realizar: 1»** y la orden aparece en su Inicio y **ya no** en el de Tomás. En Auditoría, `modificacion_invernadero` con la orden entre los afectados.
9. **Navegador real.** Abrí «Cancelar orden» y «Volver a activar» en la ventana normal **y con JavaScript desactivado** (F12 · Configuración · «Desactivar JavaScript»); en ambos modos **enviá el formulario hasta el final** y volvé a abrir la ficha. Tiene que mostrar el resultado esperado. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Con JavaScript desactivado, la ventana se abre como página completa (la ficha con la ventana arriba).
10. **Baja después de cancelar (opcional).** Con la orden cancelada, «Dar de baja» el equipo funciona y en Auditoría figura. *Lo cubre el recorrido.*
11. **Opcional.** En un celular (o con la ventana angosta), la tabla de órdenes se lee y los botones se tocan.

Al terminar: volver a 3 reintentos, 60 s y 3 lecturas de confirmación (Configuración operativa · Módulo IoT).

## Cierre (la completa Claude Code al cerrar)

### Qué se hizo

- **Modelo:** `MantenimientoTecnico` en `iot` (hija de `OrdenTrabajo`, con Técnico, tipo, alerta opcional y los equipos) y la restricción `ordentrabajo_prioridad_en_mantenimiento` en `produccion`. Migraciones `iot` 0005 y `produccion` 0007 (ninguna en `core`).
- **Servicios** (`iot/servicios/mantenimiento.py`, nuevo): lecturas de la ficha y del Inicio; la orden al escalar un comando (`crear_orden_automatica`, sus tres casos y el texto que suma a la alerta); la cancelación desde la ficha (`resumen_de_cancelacion_de_mantenimiento` y `cancelar_mantenimiento`); el traspaso del Técnico y las asignaciones de su cuenta; la sección del Inicio. Cambios en `comandos.py` (`_escalar`), `hardware.py` (regla 8 al volver a activar e impedimento de baja) y `sistemas.py` (impedimento de baja).
- **Pantallas:** sección «Órdenes de mantenimiento» de la ficha, ventanas «Cancelar orden» y «Volver a activar» (una fila por orden), textos nuevos de las ventanas de baja, sección del Inicio del Técnico.

### Pruebas

- `python manage.py test iot produccion maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **4574 OK**.
- `python manage.py test iot --keepdb --tag concurrencia` → **55 OK** (incluye las 11 de `test_mantenimiento_concurrencia.py`).
- `python manage.py test iot produccion --keepdb --tag migracion` → **4 OK**. `makemigrations --check --dry-run`: «No changes detected».
- Archivos nuevos: `test_modelos_mantenimiento`, `test_iot_rsv_cmd_mantenimiento`, `test_cancelar_mantenimiento`, `test_iot_mod_hdw_ordenes`, `test_traspaso_tecnico`, `test_inicio_tecnico`, `test_mantenimiento_vistas`, `test_mantenimiento_lecturas`, `test_mantenimiento_concurrencia`, `test_recorrido_mantenimiento`. Adaptadas: `test_iot_rsv_cmd.py` (3), `test_iot_baj_hdw.py`, `test_iot_baj_sis.py`, `test_recorrido_comandos.py`.
- **Experimento de bloqueos (concurrencia):** invertí a propósito el orden en `cancelar_mantenimiento` (la orden antes que el invernadero) y falló `test_d78_el_escalamiento_corre_entero_antes_de_que_la_cancelacion_tome_el_invernadero` con el bloqueo mutuo detectado por la base. Revertido: sin marcas en el código y las pruebas en verde.
- Se descartó la prueba de barrera del traspaso (la sacó el estudiante): no discriminaba el orden, porque las cuentas (el Agrónomo es común a las dos operaciones) serializan antes del invernadero. Los casos de (a) y (b) también quedan por resultado, no por orden.

### Informe de verificación (`docs/patrones/verificacion_a_mano.md`)

**Verifiqué**
- Recorrido `RecorridoDeMantenimientoTests.test_recorrido_de_mantenimiento_de_punta_a_punta` → OK (escalamiento con y sin Técnico, ficha por rol, cancelar con y sin motivo, volver a activar con las dos decisiones, orden con otro equipo fuera de servicio, baja bloqueada, traspaso, Inicio, Gerente sin Agrónomo).
- Migraciones: `makemigrations --check` limpio; `sqlmigrate` de `iot` 0005 (crea dos tablas y sus claves, sin borrar ni reescribir datos) y de `produccion` 0007 (un `CHECK`; agrega una restricción, no reescribe filas); las dos aplicadas en la base de pruebas y las 4 pruebas `@tag("migracion")` en OK.

**Lo cubre una prueba**
- Orden al escalar y sus tres casos, aviso y texto de la alerta: `test_iot_rsv_cmd_mantenimiento.py`.
- Cancelar (alcance, motivo, 8a, `cambio_simultaneo`, auditoría): `test_cancelar_mantenimiento.py`.
- Volver a activar con órdenes y bajas: `test_iot_mod_hdw_ordenes.py`, `test_iot_baj_hdw.py`, `test_iot_baj_sis.py`.
- Traspaso y asignaciones: `test_traspaso_tecnico.py`. Inicio del Técnico: `test_inicio_tecnico.py`. Pantallas: `test_mantenimiento_vistas.py`.
- Concurrencia (cancelar y volver a activar, dos cancelaciones, traspaso y cancelación, escalamiento y cancelación): `test_mantenimiento_concurrencia.py`.

**No pude verificar**
- El aspecto, el CSRF y `Origin`, y el JavaScript de las ventanas «Cancelar orden» y «Volver a activar» (paso 9).
- El flujo con Node-RED real y la vuelta de la revisión (correo): solo lo vi por el servicio de resultados; la API del nodo la cubre `test_recorrido_comandos.py`.
- El **orden de bloqueo del traspaso** y de los casos (a) y (b): las cuentas los serializan y no hay forma de hacerlos fallar con el orden invertido (ver «Pruebas»).
- La restricción `ordentrabajo_prioridad_en_mantenimiento` sobre datos de Neon: no hay mantenimientos anteriores a esta tarea, pero conviene confirmarlo antes del despliegue (una orden de tipo mantenimiento sin prioridad la haría fallar).

### Lo que se hizo distinto de lo escrito (va a `temas_abiertos.md`; no se corrigió en silencio)

1. `core/models.py`: solo `ETIQUETAS` y `VALORES_VISIBLES` (autorizado por el estudiante; sin migración). Claves `cancelada_desde`, `equipos_de_la_orden`, `orden_mantenimiento`, `sin_orden`, `ordenes_canceladas`, `ordenes_mantenidas`. El extracto usaba `desde` y `equipos`, que ya existen con otro sentido: corregir el extracto y esta tarea.
2. `produccion/tests/fabricas.py` (fuera de «Permitido fuera de la app», con autorización): `orden_suelta` pone prioridad `media` también al mantenimiento, porque la restricción nueva lo exige. Agregarlo a «Permitido fuera de la app» de esta tarea.
3. El Inicio del Técnico muestra solo el identificador de cada equipo (el extracto pedía «identificador y descripción»: la descripción vive en cada subtipo y costaría una consulta por equipo).
4. El Inicio usa `timezone.localdate()` (el punto de extensión solo recibe al usuario).

### Decisiones de aplicación (validadas por el estudiante en las pausas de pruebas)

- Códigos de error nuevos: `decisiones_incompletas`, `orden_no_cancelable`, `ordenes_cambiaron` (volver a activar); `orden_no_pendiente`, `cambio_simultaneo`, `motivo_obligatorio`, `motivo_largo` (cancelar).
- Baja con varias órdenes: un impedimento por orden en el equipo y uno solo con la lista en el sistema.
- Auditoría de la orden automática: `datos.orden_mantenimiento` (código) o `datos.sin_orden` (`sin_tecnico` o `orden_existente`; en ese caso, también `orden_mantenimiento` con el código de la existente).
- Si la alerta ya tiene otra orden (R048, 0..1), la orden nueva se crea sin alerta.
- `cancelar_mantenimiento` no recibe `ahora`: la fecha la pone `cancelar_orden_incluida` (PRD-01).
- Traspaso del Técnico: bloquea las filas padre `OrdenTrabajo`; «lo que recibe» va por `contar`, no por `registrar_aviso_de_traspaso` (D-98).
- Bloqueos: cancelar = cuentas → invernadero → sistemas y equipos de la orden (por id) → orden. Volver a activar = cuentas → invernadero → sistemas → equipos de las órdenes → órdenes. Escalamiento: el de IOT-05 + la orden existente (`FOR NO KEY UPDATE`). Ninguno toma el tipo (D-82 no aplica).

### Pantallas: lo que se corrigió del prototipo (D-61)

- La ficha no mostraba órdenes: se agregó la sección «Órdenes de mantenimiento» (código, tipo, estado, prioridad, fecha programada, Técnico, descripción y motivo si está cancelada) y «Cancelar orden» solo para quien opera.
- La ventana «Cancelar orden» no existía: resumen, motivo (300) y botón de peligro; funciona sin JavaScript.
- Volver a activar cancelaba sin preguntar: ahora una fila por orden, «Cancelarla» marcada de entrada y «Mantenerla»; si incluye otros equipos fuera de servicio, solo «Mantenerla».
- Las ventanas de baja decían «concretala o cancelala»: ahora «cancelala desde «Órdenes de mantenimiento», en la ficha del equipo.» (en esta ronda no se concreta).

### Base local

No borré ni cargué datos en la base de desarrollo: todo corrió en la base de pruebas.
