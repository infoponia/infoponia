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

Hay migraciones nuevas (`comercial` 0011 y `core` 0048, ninguna de datos). El recorrido por prueba (`test_recorrido_confirmacion_del_cliente`) ya hace de punta a punta lo que sigue, con el cliente de Django: los pasos marcados «lo cubre una prueba» son para ver y sentir, no para descubrir reglas.

**Antes de empezar**

1. En la terminal con el entorno virtual activo: `python manage.py migrate` (aplica `comercial.0011_confirmacion` y `core.0048_comercial_confirmacion`) y `python manage.py runserver`. Abrí `http://localhost:8000`.
2. **El enlace del correo.** Con `DEBUG` el sitio es `http://localhost:8000` (`URL_DEL_SITIO` sin cargar); los correos salen por lo que tengas configurado: con `CORREO_CONSOLA=1` en tu `.env` aparecen enteros en la terminal del `runserver`; con un correo real, en la casilla. Sin ninguno de los dos el correo no sale y el enlace queda «No se pudo enviar» (el paso 50 lo reintenta): configurá uno antes de seguir.
3. **Cuentas** (la contraseña de las cuentas de prueba la sabés; no está en el repo): un **Gerente**, el **Vendedor** del invernadero, un **Transportista** con vehículo asignado a ese invernadero y un **Agrónomo**. Opcional: un **Contador** (para el paso 6, el aviso de «no llegó»).
4. **Qué crear a mano** (si ya tenés lo de COM-06a, alcanza con sumar el segundo suministro):
   1. Un **cliente** «Verdulería Norte» (persona jurídica, CUIT válido de ejemplo, p. ej. `30-71234567-8`) con **tu correo** (que puedas leer) y una dirección de envío activa.
   2. **Dos suministros** de ese cliente (SUM-A y SUM-B), cada uno con un detalle de la misma variedad: 100 plantas por período, primera entrega **hoy**, cláusula del suministrado con plazo de pago de 15 días y cláusula del suministrante con plazo de entrega de 1 día y cantidad mínima de 50.
   3. Producto en la **cámara** de ese invernadero (por lo menos 200 plantas de esa variedad) y que cada período tenga su reserva (la pre-reserva lo hace; si no, corré el paso 40 o esperá a que se planifique la entrega).
   4. Que existan **dos entregas «a realizar» para hoy**, una por suministro, con el **Transportista** asignado (la planificación de entregas las crea y asigna; si no, «Comercial» › «Entregas» › «Asignar»).
5. Con el **Transportista**: «Mi ruta» › **Iniciar ruta**.

**Los pasos**

1. **Concretar y el correo único.** (Transportista, «Mi ruta») Entrá a «Concretar» en la entrega de SUM-A: «Llegaron» 100, «Recibió» 100, marcá «No usé envases», **Ver resumen** y **Confirmar entrega**. *Tiene que verse:* llega **un solo correo** con el comprobante (cantidad, precio, monto, vencimiento del pago) **y** el enlace de confirmación, con «Sirve hasta el» (hoy + 3 días). No llega un segundo correo aparte. Con el **Vendedor**, «Comercial» › «Contratos» › SUM-A: la entrega figura «Concretada» y «No confirmada». Repetí con la entrega de SUM-B (otro correo, otro enlace). *Lo cubre una prueba:* `test_post_l_el_correo_de_un_suministro_es_uno_solo…`, el recorrido (paso 1).
2. **Abrir el enlace desde el celular** (o una ventana privada). Pegá el enlace de SUM-A. *Tiene que verse:* la dirección cambia a `/cliente/enlace/` (el token **no** queda en la barra); la entrega con el producto, «100 entregadas / 100 planificadas», el precio, el monto, «Total de la entrega» y el «Vencimiento del pago»; «Puede responder hasta el …». **No** aparece ninguna cantidad de plantas perdidas ni costos, y no hay menú ni campana. En «Quejas» **no** hay «Retraso» (llegó a tiempo). *Lo cubre una prueba:* `test_flujo_principal_el_cliente_ve_su_entrega_sin_perdidas…`.
3. **Retraso (si podés).** Si tenés una entrega «Demorada» (la fecha de su período ya pasó), concretala y abrí su enlace: «Sí, la recibí pero tengo quejas» ofrece **«Retraso»** con «llegó con N días de retraso» y solo con ese producto. Si no, marcá este paso como no probado a mano. *Lo cubre una prueba:* `test_regla_la_queja_por_retraso_solo_se_ofrece_con_retraso…`.
4. **Errores del formulario.** En el enlace de SUM-A: tocá **Revisar y enviar** sin elegir nada → «Indicá si recibiste la entrega.». Elegí «Sí, la recibí pero tengo quejas» y **Revisar y enviar** sin marcar nada → «Agregá al menos una queja o indicá que recibiste la entrega y estás conforme.». Marcá «Estado de la mercadería» sin producto → «Elegí al menos un producto.»; con producto y **sin motivo** → «El motivo es obligatorio para este tipo de queja.». Elegí «No recibí la entrega» sin motivo → «Contanos qué pasó: el motivo es obligatorio.». *Tiene que verse:* cada error junto a su campo y lo que ya elegiste sigue marcado; nada queda registrado. *Lo cubre una prueba:* `test_ext_3a_4a_4b_y_6a_los_errores_vuelven_al_formulario…`.
5. **Dos quejas.** Elegí «Sí, la recibí pero tengo quejas»; marcá «Estado de la mercadería» (producto marcado, motivo «Llegó con las hojas golpeadas.») y «Otro» (producto marcado, motivo «Faltó el remito.»). **Revisar y enviar**. *Tiene que verse:* el resumen «presenta 2 quejas» con tipo, producto y motivo de cada una y la advertencia «Después de enviarla, este enlace no podrá volver a usarse.»; **Cambiar la respuesta** vuelve al formulario con todo lo que elegiste. Volvé a **Revisar y enviar** y tocá **Enviar respuesta**. *Tiene que verse:* «Gracias. Recibimos su respuesta.», «La recepción de su entrega quedó confirmada y registramos 2 quejas.» con los números `SR-…` y el tipo de cada una; llega el **acuse** por correo con esos números; **Gerente**: dos alertas «Queja de un cliente» (en la campana y en «Alertas»); **Vendedor**: dos avisos «Queja de un cliente en OT-…» («queja por el estado de la mercadería del cliente Verdulería Norte»). En la ficha de SUM-A: la entrega figura «Confirmada» y aparece «Quejas de entrega» con las dos «Pendiente de revisión». *Lo cubre una prueba:* `test_flujo_principal_dos_quejas…`, el recorrido (paso 3).
6. **El enlace no sirve dos veces.** Volvé a pegar el enlace de SUM-A. *Tiene que verse:* «Este enlace no se puede usar», «Este enlace ya se usó: su respuesta quedó registrada.» y los datos del Vendedor (nombre, teléfono si tiene, correo). Con la pantalla final abierta, **Reenviar acuse** manda otro acuse al correo («Le reenviamos el acuse a su correo.») y se puede repetir. *Lo cubre una prueba:* `test_ext_6a_con_el_enlace_usado…`, `test_ext_7a_8a…`.
7. **No recibí la entrega.** Con el enlace de SUM-B (otra ventana privada): «No recibí la entrega», motivo «No llegó nada a la sucursal de Santo Tomé.», **Revisar y enviar** (resumen: «no recibió… No quedará confirmada…») y **Enviar respuesta**. *Tiene que verse:* «Gracias…», «no reconoce la entrega». El **Gerente** tiene una alerta **crítica** «Entrega no reconocida por el cliente»; el **Vendedor**, un aviso con el motivo; la entrega sigue «No confirmada» en la ficha de SUM-B. *Lo cubre una prueba:* `test_flujo_principal_no_recibi_registra…`, el recorrido (paso 5).
8. **El Gerente atiende la alerta.** Entrá con el Gerente, abrí la alerta (campana o «Alertas») y su enlace «Dónde se atiende» (o, en la ficha de SUM-B, **Atender** en «Entregas que el cliente no reconoce»). *Tiene que verse:* «Entrega no reconocida · OT-…», lo que dijo el cliente, la entrega con planificadas/entregadas/perdidas/devueltas, el transportista, la fecha y hora de la concreción, los intentos fallidos, «No confirmada», «Sin cobro registrado» y «Fuera de esta ronda · contabilidad». Tocá **Resolver alerta** sin elegir → «Elegí el resultado de la averiguación.»; elegí un resultado sin descripción → «Contá qué averiguaste: la descripción es obligatoria.». Elegí «No llegó, producto perdido», descripción «Hablé con el cliente y con el chofer: se perdió.» y **Resolver alerta**. *Tiene que verse:* vuelve a la ficha de SUM-B con «La alerta de OT-… quedó resuelta.»; la alerta figura resuelta; el **Vendedor** (y el **Contador**, si hay uno activo; si no, nadie más: el Gerente es quien atendió) tiene el aviso «Corregir los asientos de OT-…: corresponde corregir los asientos a mano.». «Auditoría» muestra «Respuesta del cliente a una entrega» (origen «Cliente (mediante enlace)») y «Atención de entrega no reconocida». *Lo cubre una prueba:* `test_com_atn_enr` (reglas 1 a 5 y postcondiciones), `AtenderEntregaNoReconocidaVistaTests`, el recorrido.
9. **La vigencia sigue al parámetro.** En «Configuración», bajá «Vigencia del enlace de confirmación» a 1 día. Un enlace sin usar de una entrega concretada hace más de 1 día (creá otra entrega, concretala y esperá un día, o probalo con la que quede de una corrida anterior) da «El plazo para confirmar la entrega terminó.». Si lo volvés a subir, vuelve a servir. *Lo cubre una prueba:* `test_regla_cambiar_el_parametro_cambia_la_vigencia…`, el recorrido (paso 6).
10. **Por rol.** *Vendedor:* en la ficha de SUM-A ve «No confirmada»/«Confirmada» por entrega y las quejas, pero **no** ve «Atender»; si escribe a mano `/comercial/entregas/<id>/no-reconocida/` ve «403». *Agrónomo y Transportista:* lo mismo, 403. *Sin sesión:* lo lleva al inicio de sesión. *Gerente:* en la ficha del **cliente** aparece «Quejas pendientes» y «Baja» las informa (no la bloquea). *Lo cubre una prueba:* `test_regla_solo_el_gerente_entra…`, `FichasConQuejasTests`.
11. **Navegador real.** Abrí el enlace de una entrega nueva en una **ventana privada** (sin sesión), completá el formulario con quejas y **enviálo hasta el final**; después volvé a abrir el enlace, y probá **Reenviar acuse**. Tiene que mostrar el resultado esperado. Si aparece una página «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Revisá también que la dirección **nunca** muestre el token después de abrir el enlace.
12. **Sin JavaScript** (opcional). Desactivá JavaScript y repetí los pasos 2 a 5 y 8: el formulario del cliente muestra a la vez los bloques de quejas y de «no recibí» (completás solo el que corresponde), el resumen es otra página y la pantalla del Gerente funciona igual.
13. **En un celular** (opcional). Abrí el enlace del correo: la tabla de la entrega se apila (producto, plantas, precio y monto) y los botones se tocan bien.
14. **Después del merge:** revisá en el log de Render que se aplicaron `comercial.0011` y `core.0048` (los números pueden cambiar si otra tarea se mergeó antes) y que `URL_DEL_SITIO` está cargada en Render (sin ella el enlace queda «No se pudo enviar»).

## Cierre (la completa Claude Code al cerrar)

### Qué se hizo

- **Modelos y migraciones** (`comercial/0011_confirmacion`, `core/0048_comercial_confirmacion`, ninguna de datos): `Queja(SolicitudRevision)` (`tipo_queja`, `motivo_queja`, `cliente`, `detalles`); en `EnlaceCliente`, el tipo `confirmacion_entrega`, la FK `entrega` y sus restricciones (`confirmacion_entrega` ⇔ `entrega` no nula y `compra_venta` nula; `decision_faltante` ⇔ `fecha_vencimiento` no nula; único `(entrega)` sin reemplazo); en `AlertaComercial`, `resultado_averiguacion` y `descripcion_averiguacion` (con sus tres restricciones). `core`: las acciones `respuesta_cliente_entrega` y `atencion_entrega_no_reconocida` (en `ACCIONES_DE_NEGOCIO`), 6 claves de `ETIQUETAS` y 2 de `VALORES_VISIBLES` (verificado con AST: sin claves duplicadas).
- **Servicios**: `enlaces.py` (`crear_enlace(tipo, cliente, *, compra_venta=None, vence=None, entrega=None)`, `vencimiento_de`, `situacion_del_enlace` y `texto_del_motivo` por tipo, `enviar_enlace` con el correo único, `reemitir_enlace`); `concrecion.py` (la postcondición l: `crear_enlace` dentro de la transacción de la concreción); `entregas.planificar_entregas` (parte 4: reemite el enlace); `confirmacion.py` (`datos_para_el_cliente`, `tipos_de_queja_disponibles`, `datos_de_respuesta`, `resumen_de_respuesta`, `registrar_respuesta`, `reenviar_acuse`, `contacto_del_vendedor`, `contacto_de_la_entrega`); `atencion.py` (`ficha_de_no_reconocida`, `atender_entrega_no_reconocida`, `alerta_activa_de`, `enlaces_de_alertas`); `clientes.quejas_pendientes` (ficha y baja del cliente) y la ficha del suministro (`quejas`, `por_atender`). `apps.py` registra los dos tipos de alerta (`comercial_queja`, `comercial_entrega_no_reconocida`) y sus enlaces.
- **Pantallas**: `views_cliente.py` (`_confirmar`, `reenviar_acuse`) con `cliente/confirmacion.html`, `_confirmacion_bloques.html` y `confirmacion_lista.html`; `views_entregas.no_reconocida` con `entregas/no_reconocida.html` (URL `comercial:entrega_no_reconocida`); la ficha del suministro («Entregas que el cliente no reconoce» con «Atender» solo para el Gerente y «Quejas de entrega») y la ficha del cliente («Quejas pendientes»); los correos `confirmacion_entrega.txt` y `acuse_confirmacion.txt`.
- **Contrato de servicios**: `registrar_respuesta(enlace_id, respuesta: DatosDeRespuesta, hoy=None) -> Respuesta(enlace, entrega, respuesta, quejas, alertas, acuse_enviado)`; `atender_entrega_no_reconocida(actor, alerta_id, resultado, descripcion) -> Alerta`; `reemitir_enlace(enlace) -> token | None`. Códigos de error (`ValidationError` con `code`): `respuesta_obligatoria`, `quejas_vacias`, `tipo_no_disponible`, `queja_repetida`, `queja_sin_detalles`, `linea_no_valida`, `motivo_obligatorio`, `motivo_largo`, `enlace_no_sirve` (con `params["motivo"]`: `no_valido`, `usado`, `vencido`, `anulado`), `acuse_no_disponible`, `resultado_obligatorio`, `resultado_invalido`, `descripcion_obligatoria`, `descripcion_larga`, `alerta_resuelta`, `entrega_cobrada`; `PermissionDenied` y `Http404`.
- **Bloqueos** (`docs/patrones/bloqueos.md`, «Confirmar una entrega»): la respuesta toma la cuenta del Vendedor → el invernadero de origen → la entrega → el enlace; la atención toma las cuentas (Gerente, Vendedor y responsable contable, en orden de id) → el invernadero → la entrega → la `AlertaComercial`: mismo sentido, no se cruzan.

### Pruebas (M1)

- `python manage.py test comercial maestros core --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion` (con los clones de la base `test_…` recreados): **4248 pruebas, OK**.
- `python manage.py test comercial --keepdb --tag concurrencia`: **104 pruebas, OK** (incluye las 2 nuevas de `test_confirmacion_concurrencia`).
- `makemigrations --check --dry-run`: sin cambios. `manage.py check`: sin problemas.
- Migraciones: `sqlmigrate comercial 0011` crea la tabla de `Queja` y su muchos a muchos, agrega columnas y restricciones (solo `CREATE`/`ALTER`; el único `DROP` es el de la restricción `enlace_cliente_tipo_valido`, que se vuelve a crear con el tipo nuevo, y el del `DEFAULT` temporal de `descripcion_averiguacion`: ninguna fila se borra ni se reescribe); `core 0048` es `no-op` en SQL (solo `choices`). Se aplicaron en las bases de prueba.

### Verifiqué

- El recorrido `test_recorrido_confirmacion_del_cliente` (pasos 1 a 10 de la «Verificación a mano», por rol y estado, con los correos y avisos reales): verde.
- Las dos migraciones: SQL leído (`sqlmigrate`), sin pérdida de datos, aplicadas en la base de pruebas.
- La suite de las apps tocadas y la concurrencia de `comercial`.

### Lo cubre una prueba

- Cada postcondición y extensión de COM-CNF-ENT y las reglas de COM-ATN-ENR: `test_com_cnf_ent`, `test_com_atn_enr`.
- El enlace de confirmación (crear, sin reemplazo, vigencia calculada, reemisión): `test_enlaces`, `test_com_cnc_ent` (postcondición l y 15a), `test_modelos_confirmacion`.
- Dos respuestas del mismo enlace y la respuesta contra la atención: `test_confirmacion_concurrencia`.
- Cabeceras de `/cliente/`, la sesión, HTMX y sin JavaScript, permisos del Gerente, botones sin 403 y las fichas: `test_confirmacion_vistas`.

### No pude verificar

- Lo que ve un navegador: CSRF y `Origin`, JavaScript de HTMX (el bloque que se redibuja al elegir la respuesta), el aspecto en un celular (paso 11 a 13).
- El envío real de correo (las pruebas usan el servicio simulado) y el despliegue en Render (paso 14).
- La parte 4 del paso 50 con un enlace «pendiente» y el correo real: la cubren las pruebas con el correo simulado.

### Pruebas existentes cambiadas (anotar en el PR)

- `test_com_cnc_ent::test_ext_3a_el_correo_de_un_suministro_lleva_el_comprobante_de_entrega_sin_enlace` → `test_post_l_el_correo_de_un_suministro_es_uno_solo_con_el_comprobante_y_el_enlace_de_confirmacion` (el correo del suministro ahora lleva el enlace: lo permiten «Límites»; la prueba sigue verificando el comprobante y suma el enlace).
- `test_recorrido_ruta_y_concrecion` (paso 3): el comprobante del suministro ahora trae la URL (`assertIn("https://sitio.test/cliente/")` en lugar de `assertNotIn("http")`) y el decorador suma `URL_DEL_SITIO`.
- `test_modelos_cosecha_camara::EnlaceClienteModeloTests`: seis llamadas a `EnlaceCliente.objects.create` que esperan una violación suman `fecha_vencimiento` (con la restricción nueva violarían la base por otra razón; así siguen probando lo que dicen).
- Las pruebas de `crear_enlace` y de `enlace_vigente`/`situacion_del_enlace` de `test_enlaces` no cambiaron: solo se agregaron pruebas. `verificar_invariantes_de_solicitudes` suma las quejas.

### Decisiones tomadas dentro de la tarea (a revisar; van a `docs/temas_abiertos.md`)

1. **El aviso de «no llegó» va al Vendedor y al responsable contable** (el Contador activo o, sin Contador, el Gerente), sin el Gerente que atiende (decisión tuya del 25/11/2026). La tarea y `confirmacion.md` decían «los Gerentes activos y el Vendedor»; `docs/disparadores.md` («Cuando exista el rol Contador», punto 1) manda a `responsable_contable()` y dice que lo programa COM-06b si llega después de CON-02. **Cierra ese disparador.**
2. **Errores**: `ValidationError` con `code` y `error_dict` por campo (patrón de `comercial`); `confirmacion.md` no nombra una clase.
3. **`registrar_respuesta` recibe `DatosDeRespuesta`** (con `QuejaPedida`) y la pantalla arma esos datos con `datos_de_respuesta(request.POST)`; `confirmacion.md` decía «datos».
4. **Un invernadero de origen dado de baja no crea alertas** (`crear_alerta_de_evento` devuelve `None`): la queja se registra igual, sin alerta (como la discrepancia de COM-06a); el invariante «una alerta por solicitud» no cubre ese caso.
5. **Si el correo del enlace no sale no se avisa al Vendedor** (el patrón, sección 3, lo avisa en el faltante): hay reintento (paso 50, 15a), así que el aviso sería ruido; queda `pendiente_envio` y, con `URL_DEL_SITIO` sin cargar, el enlace se reemite cuando se cargue.
6. **Las entregas concretadas antes de esta tarea** (sin enlace) siguen recibiendo el comprobante sin enlace por el reintento del paso 50 (estado de paso, D-68 punto 1); no se les crea enlace.
7. **`acuse_enviado`**: `True`/`False` cuando el acuse ya salió o falló, `None` si todavía corre dentro de una transacción mayor (solo pasa en las pruebas). La pantalla final avisa solo con `False` (7a.3).
8. **El acuse de «no recibí»** deja la constancia sin el motivo (el caso de uso no lo pide); el reenvío (8a) rearma el acuse desde la base.
9. **El formulario del cliente es una sola página** (la respuesta, las tres quejas posibles con casillas y el motivo), no una página por queja: sin JavaScript se ven a la vez el bloque de quejas y el de «no recibí»; con HTMX, al elegir la respuesta se redibuja solo el que corresponde (sin validar). El resumen es la segunda página.
10. **«Atender» solo para el Gerente** en la ficha del suministro (bloque «Entregas que el cliente no reconoce»); el Vendedor ve «No confirmada» en la columna «Confirmación» de sus entregas (la regla «Sin confirmación tácita»).
11. **Regla 5 de COM-ATN-ENR**: `_tiene_cobro_vigente` devuelve siempre `False` hasta COM-08a (la prueba lo simula con `mock.patch`); con «la entrega llegó» no se pide anular el cobro.
12. **`reemitir_enlace(enlace)`** toma la fila (no el id) y se llama fuera de toda transacción, desde la parte 4 del paso 50.
13. **Paralelo**: tras una migración nueva los clones de `--keepdb` quedan sin la columna: hubo que recrearlos con `--noinput` (base `test_…`, D-101).

### Pantallas: lo que se corrigió del prototipo

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| Confirmar Entrega (`VIEWS.cnf`) | El precio unitario se deducía del monto (`e.monto / sumEn`) | Precio guardado de cada línea, su monto, el total y lo que queda a pagar con las indemnizaciones descontadas | Paso 2; PCU 16 |
| Confirmar Entrega | Las quejas se redibujaban mientras se tipeaba (`input` con retardo) y el botón se deshabilitaba solo | «Revisar y enviar» valida; HTMX solo redibuja el bloque al elegir la respuesta y no valida; sin JavaScript, una página | `.claude/rules/interfaz.md` (nada de validar al tipear) |
| Confirmar Entrega | Un único aviso de error para toda la respuesta | El error junto a cada campo (respuesta, productos y motivo de cada queja, motivo de «no recibí») y lo elegido se conserva | Extensiones 3a.4a, 3a.4b, 3a.6a y 3b.1a |
| Confirmar Entrega | «Retraso» ofrecía todas las líneas | Solo los productos demorados, con sus días de retraso | Regla «Queja por retraso» |
| Confirmar Entrega | La pantalla final no ofrecía reenviar el acuse | «Reenviar acuse», con el aviso de que el acuse todavía no se envió cuando falló | Extensiones 7a.3 y 8a |
| Confirmar Entrega | «Volver» al portal «Enlaces recibidos» | No se implementa (es «Solo prototipo»); un enlace que no sirve da la pantalla con el motivo y el contacto del Vendedor | README del prototipo; extensiones 2a y 6a |
| Atender entrega no reconocida (`VIEWS.atnenr`) | Los asientos con datos de ejemplo | «Fuera de esta ronda · contabilidad» | Regla 1; D-57 |
| Atender entrega no reconocida | Resultado `perdido`/`devuelto` y un aviso fijo «se notificará al Vendedor» | `no_llego_perdido`/`no_llego_devuelto` (MD-137) y el aviso dice que llega al Vendedor y a quien registra los asientos; la regla 5 (anular el cobro) se rechaza con `entrega_cobrada` | Reglas 2, 3 y 5; postcondición b |
| Atender entrega no reconocida | Sin estado de error, de permiso ni de alerta ya resuelta | Errores por campo, 403 para los demás roles y, sin alerta activa, vuelta a la ficha del suministro con el mensaje | `.claude/rules/interfaz.md`; D-30 |
| Ficha del suministro y del cliente | Sin quejas ni acceso a la atención | «Quejas de entrega», «Entregas que el cliente no reconoce» (con «Atender» solo para el Gerente) y «Quejas pendientes» (ficha y baja del cliente) | «Lo que completa a otras tareas» |
