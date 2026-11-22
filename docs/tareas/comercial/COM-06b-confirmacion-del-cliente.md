# COM-06b · Confirmación del cliente: el enlace de confirmación, las quejas y la entrega no reconocida

Estado: pendiente | App: comercial | Rama: feature/com-06b-confirmacion-del-cliente | Ronda: Comercial 1

Depende de: **COM-06a** (y, con ella, COM-04c: el enlace del cliente, `core/enlaces.py` y la entrada pública `/cliente/`). Si COM-06a no
está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La segunda parte de COM-06 (D-68, punto 1): al concretarse una entrega de suministro, el cliente recibe **un correo con el
comprobante y el enlace** para **confirmar la recepción** desde el celular, sin usuario; si no está conforme, presenta **quejas** (estado de
la mercadería, retraso u otro), y si dice que **no la recibió**, el Gerente recibe una alerta y la **atiende** registrando lo que averiguó.
Las quejas y la discrepancia se resuelven en COM-07.

**Estado de paso:** las entregas de suministro concretadas antes de esta tarea no reciben enlace (D-68, punto 1): quedan «no confirmado».

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-CNF-ENT | Confirmar Entrega | docs/casos_de_uso/comercial/confirmacion.md | Resolver las quejas: COM-07 |
| COM-ATN-ENR | Atender Entrega No Reconocida (alto nivel) | docs/casos_de_uso/comercial/confirmacion.md | Los asientos de la regla 1 y el aviso a quien registra los asientos manuales (postcondición b): fuera, D-57. El cobro de la regla 1 y la regla 5: COM-08 |
| COM-CNC-ENT | Concretar Entrega (solo la postcondición l: el enlace) | docs/casos_de_uso/comercial/rutas.md y confirmacion.md («El enlace de confirmación») | — |

## Leer

- Casos de uso: docs/casos_de_uso/comercial/confirmacion.md **completo**; de rutas.md, «Cómo se aplica» (lo que deja COM-06a: la
  concreción, `crear_solicitud`, `intentos_fallidos`, `monto_a_cobrar`, los correos); de faltante.md, «Cómo se aplica» (COM-DCD-FLT: cómo se
  usó el enlace).
- Modelo: docs/modelo/comercial.md (**Queja**, **SolicitudRevision**, **EnlaceCliente**, **AlertaComercial**, Entrega, DetalleEntrega, las
  cláusulas); docs/modelo/maestros.md (`dias_vigencia_enlace_confirmacion`).
- Decisiones: **D-68** (puntos 1, 5, 8 y 9), **D-65**, D-63, D-62 (con su tercera enmienda), D-57, D-42, D-36, D-29, D-27, D-25.
- Patrones: **docs/patrones/enlace_del_cliente.md** (con la sección 9), docs/patrones/bloqueos.md («Confirmar una entrega»),
  docs/patrones/auditoria.md, docs/patrones/abm.md (sección 1).
- API: docs/api/alertas.md (secciones 1, 2, 4 y 8), docs/api/notificaciones.md.
- Pantallas: docs/prototipos/comercial/ (`README.md`): `VIEWS.portal`, `INIT.cnf`, `VIEWS.cnf` (vale la última), `qErr`, `INIT.atnenr`,
  `VIEWS.atnenr`.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `comercial/` completo (COM-01 a COM-06a), en especial `servicios/enlaces.py`, `views_cliente.py` y sus plantillas,
  `servicios/concrecion.py`, `servicios/entregas.py`, `apps.py` y las fábricas; `core/enlaces.py`, `core/correo.py`, `core/notificaciones.py`,
  `core/models.py`; `maestros/servicios/alertas.py`, `maestros/extensiones.py` (`registrar_enlace_de_alerta`), `maestros/servicios/configuracion.py` (`obtener()`).

## Límites

- Crea modelos (en `comercial`): `Queja`; en `EnlaceCliente`, el tipo `confirmacion_entrega`, `entrega` y `fecha_vencimiento` nula; en
  `AlertaComercial`, `resultado_averiguacion` y `descripcion_averiguacion`.
  → revisá docs/disparadores.md: cierra lo que deja COM-06a para COM-06b (el enlace en la concreción) y «Completan el ABM de cliente» para las
  quejas.
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `comercial/migrations/00NN_confirmacion.py`: la tabla de `Queja` (y su muchos a muchos), los campos y las restricciones de las fichas (las
    de `EnlaceCliente` se reescriben con el tipo nuevo);
  - `core/migrations/00NN_comercial_confirmacion.py`: solo `choices` (acciones `respuesta_cliente_entrega`, `atencion_entrega_no_reconocida`).
- Permitido fuera de `comercial`: `core/models.py` (las acciones, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`); al cerrar (M3),
  los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`. Las pruebas de
  COM-04c y de COM-06a no se modifican, salvo las del correo de la concreción de un suministro (que ahora lleva el enlace) y las de
  `crear_enlace` y `enlace_vigente` que esperaban un solo tipo: anotalas en el PR.
- Dependencias nuevas: ninguna.
- Fuera de alcance: resolver quejas y discrepancias (COM-07); el cobro (COM-08); los asientos y el rol de quien los registra (ronda de
  contabilidad, D-57); crear enlaces para las entregas concretadas antes de esta tarea; que el Vendedor registre una queja en nombre del
  cliente o reenvíe el enlace (temas abiertos del caso de uso).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y migraciones** (las fichas; D-68, puntos 5, 8 y 9). Fábricas: `enlace_de_confirmacion(...)`, `queja(...)`,
   `alerta_no_reconocida(...)`; invariantes de quejas en `verificar_invariantes_de_solicitudes`.
   Pruebas: `comercial/tests/test_modelos_confirmacion.py` (una por restricción).
2. **El enlace de confirmación** (`confirmacion.md`, «El enlace de confirmación»; `enlace_del_cliente.md`, sección 9): `crear_enlace` con
   `entrega`, `enlace_vigente` por tipo, la llamada en `concretar_entrega`, el correo único y `reemitir_enlace` en la parte 4 del paso 50.
   Pruebas: en `test_enlaces.py`, las del patrón para este tipo, el cambio del parámetro, la falta de reemplazo y la reemisión (el token
   viejo deja de servir; usado o vencido no se reemite); en `test_com_cnc_ent.py`, la postcondición l y 15a.
3. **Confirmar la entrega** (`confirmacion.md`, «Servicios» y «Registrar la respuesta»).
   Pruebas: `test_com_cnf_ent.py`, `test_confirmacion_concurrencia.py`.
4. **Atender una entrega no reconocida** (`confirmacion.md`, «Atender una entrega no reconocida»), con el enlace de la alerta
   (`registrar_enlace_de_alerta`).
   Pruebas: `test_com_atn_enr.py`.
5. **Lo que completa a otras tareas** (`confirmacion.md`, «Lo que completa a otras tareas»): la ficha del suministro (confirmación y quejas)
   y la baja del cliente (quejas pendientes).
6. **Vistas y plantillas** (`confirmacion.md`, «Pantallas»): el portal del cliente y la pantalla del Gerente.
   Pruebas: `test_confirmacion_vistas.py`.
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar lo de «Límites» y dejar lo que nace (COM-07:
   las quejas pendientes; COM-08: el cobro en COM-ATN-ENR; contabilidad: el aviso de la postcondición b); marcar COM-06b en
   `docs/tareas/README.md` y en el plan; lo distinto de lo escrito, a `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió del
   prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es «Reenviar acuse» (8a; queda en `docs/temas_abiertos.md`). No se recortan las
restricciones de la base, los bloqueos, la vigencia calculada ni las pruebas de concurrencia y de seguridad del enlace.

## Hecho cuando

- Al concretarse una entrega de suministro, el cliente con correo recibe un solo correo con el comprobante y el enlace.
- El cliente abre el enlace desde el celular, ve su entrega (sin perdidas ni costos), confirma o presenta quejas, o dice que no la recibió;
  el enlace no sirve dos veces ni vencido, y su vigencia sigue al parámetro de la configuración.
- Cada queja queda «pendiente» con su alerta para el Gerente y el aviso al Vendedor; la entrega no reconocida crea su alerta crítica.
- El Gerente atiende la entrega no reconocida con todo a la vista, registra el resultado y la alerta queda resuelta.
- Todas las pruebas de `comercial`, `maestros` y `core` siguen pasando (las reemplazadas, anotadas).
- Comando de pruebas:
  python manage.py test comercial maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas (`comercial`, `core`): `python manage.py migrate`. Datos: los de COM-06a, con un cliente de suministro **con un correo
que puedas leer** y una entrega del suministro planificada para hoy, con un período demorado.

1. Concretá la entrega con el Transportista: llega un solo correo, con el comprobante y el enlace.
2. Abrí el enlace en el celular: la URL deja de tener el token; ves cantidades, precio, monto, total y vencimiento, y no las perdidas.
3. «Recibí pero tengo quejas»: «Retraso» aparece (hay retraso) y solo con las líneas demoradas; una de «Estado de la mercadería» sin motivo
   da error. Enviá dos quejas: el acuse trae sus números; el Gerente tiene dos alertas y el Vendedor dos avisos.
4. Volvé a abrir el enlace: «Este enlace ya no se puede usar», con el contacto del Vendedor.
5. Con otra entrega: «No recibí la entrega» con motivo: alerta crítica para el Gerente. Con el Gerente, desde la alerta: la pantalla muestra
   todo; registrá «No llegó, producto perdido» con descripción: la alerta se resuelve y el Vendedor tiene el aviso.
6. En «Configuración», bajá los días de vigencia del enlace: un enlace sin usar de hace más días deja de servir.
7. Sin JavaScript: el portal y la pantalla del Gerente funcionan.
8. Después del merge: revisar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
