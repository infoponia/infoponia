# Temas abiertos — InfoPonia

Temas que todavía no tienen tarea ni disparador. Se leen al planificar, no en cada sesión. Cuando un tema pasa a tener
tarea (`docs/tareas/`) o disparador (`docs/disparadores.md`), se saca de acá y se anota adónde fue.

Copiados sin cambios de `docs/estado.md`, «Temas abiertos», el 18/11/2026. Actualizado el 19/11/2026 (lote 0 de la ronda
«Producción 1»).

- Lista cerrada de los casos de uso del 80% y orden de implementación. La primera ronda ya tiene su plan
  (`docs/tareas/ronda_produccion_1.md`); falta el de las rondas siguientes (cosecha, comercial, compras, IoT).
- Ingreso con Google: trabajo futuro, fuera de este bloque.
- Hacer configurables por `.env` el host, el puerto, el nombre y el usuario de la base local.
- Integrar el logo de InfoPonia: favicon y marca en el inicio de sesión. Cuándo: cuando esté el logo definitivo.
- Funciones de pruebas con el mismo nombre y distinto trabajo, que no se unificaron a propósito: `datos_validos`
  (`test_usr_alt_usr.py` arma los datos de un alta; `test_usr_mod_usr.py` toma los datos actuales de una cuenta) y
  `codigos` (`core/tests/concurrencia.py` devuelve todos los códigos de un error; `test_usr_cmb_ctr.py` recibe el
  campo y devuelve solo los de ese campo). Si se renombran, que sea sin cambiar lo que verifica ninguna prueba.
  Cuándo: opcional, sin fecha.
- Búsqueda de la lista de cuentas sin distinguir tildes, con `unaccent` de PostgreSQL. Cuándo: opcional, sin
  fecha.
- Volver a la pantalla pedida después de iniciar sesión (D-29): solo se evalúa el rol. Una cuenta fuera de alcance
  dentro de una pantalla permitida (por ejemplo, `/usuarios/7/`) sigue dando 403; cubrirla exigiría ejecutar la
  pantalla pedida dos veces. Cuándo: sin fecha.
- Alcance de lo que quedó fuera de la ronda «Producción 1» (D-45): asientos contables, cámara de frío, logo, datos de compras.
  Cada uno tiene su disparador en `docs/disparadores.md`; acá queda solo el orden en que se retoman. Cuándo: sin fecha.

## Adónde fueron los demás temas de `estado.md` (18/11/2026)

| Tema | Ahora está en |
|---|---|
| Reparto final de apps | D-37 |
| Tope de pedidos de recuperación de contraseña | `docs/tareas/usuarios/USR-09-seguridad-produccion.md` |
| Tope de intentos de identificación | `docs/tareas/usuarios/USR-09-seguridad-produccion.md` |
| `DEBUG` apagado por defecto (Render ya tiene `DJANGO_DEBUG=0`) | `docs/tareas/usuarios/USR-09-seguridad-produccion.md` |
| Proveedor del almacenamiento para la foto de perfil | `docs/tareas/usuarios/USR-07-foto-perfil.md` y «Esperas» de `docs/estado.md` |
| Logo y nombre de la organización configurables | `docs/disparadores.md`, «Cuando exista PerfilOrganizacion» |
| Estilo del prototipo de producción contra el del sistema | D-47 y la tarea UI-01 (`docs/tareas/ronda_produccion_1.md`) |
| Campana y notificaciones del marco | `docs/disparadores.md`, «Cuando exista la primera notificación», y la tarea NOT-01 (`docs/tareas/ronda_produccion_1.md`; el tema salió de acá el 19/11/2026) |
| Ámbito por invernadero de SEG-13 | `docs/disparadores.md`, «Cuando exista Invernadero» |

## Abiertos desde el lote 2 de la ronda «Producción 1» (19/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Actualizar el modelo en Drive (pendientes_MD) | Seis diferencias entre el modelo y los CU de inventario, resueltas a favor del CU (`docs/modelo/inventario.md`, «Diferencias con el caso de uso»; la sexta es del lote 3: la semilla de una variedad dada de baja conserva sus existencias): el «otro» que suma crea lote; el faltante sin lote solo lo regulariza un recuento; «stock inconsistente» mide sin lotes vencidos; R139 es por `InsumoInvernadero` (D-46 corregida); las alertas de vencimiento no se generan sin Agrónomo; la semilla de una variedad dada de baja conserva sus existencias activas. **Aprobadas por el equipo el 19/11/2026** | Pegarlas en pendientes_MD (las pega la persona, no Claude) |
| Alertas sin Agrónomo | La API de alertas (D-41, MD-61) manda toda alerta al Gerente si no hay Agrónomo; CMP-REV-VNC dice que no se genera. Se hizo lo del CU solo para las de vencimiento. **Aprobado el 19/11/2026**: queda así para vencimientos. Falta decidir, más adelante, si se unifica con la API de alertas | Cuando se revise la API de alertas |
| «Stock inconsistente» cuando vence un lote | Con la medida del CU (sin lotes vencidos), un lote que vence puede volver inconsistente un insumo sin que nadie opere, y CMP-REV-VNC no reevalúa esa alerta (no lo pide). Se reevalúa en la próxima operación. **Aprobado el 19/11/2026**: queda como está (se reevalúa en la próxima operación). Revisar si molesta en uso real | Con uso real |
| Cuenta de la carga inicial (MD-90) y valor del ajuste | El asiento está fuera de la ronda; el valor del ajuste se muestra igual (cantidad × precio de referencia) | Cuando exista contabilidad |
| Recepción pendiente en el recuento | El aviso de CMP-AJT-STK sobre la recepción sin cargar es texto fijo: `compras` no existe en la ronda | Con `compras` |
| Costo del cron job de Render | Render cobra un mínimo de 1 dólar por mes por cada cron job (verificado en su documentación el 19/11/2026). Alternativa gratuita, si molesta: ninguna que sea confiable (un hilo dentro del web service muere cuando Render lo duerme) | Antes de crear el cron job |
| Topes de largo de nombre y descripción | 100 y 300 caracteres: los fija esta ronda; los CU no los dicen | Sin fecha |
| Categoría «Infraestructura» | El prototipo no la muestra; el CU y el modelo sí. No tiene insumos en esta ronda. **Resuelto el 20/11/2026:** `iot` **no** la usa (el hardware se asocia a «Repuestos de hardware», R072, `repuestos_de_hardware`). «Infraestructura» queda para reparaciones de la infraestructura del invernadero (por ejemplo de un sector), aunque ese mantenimiento no tenga una orden propia: la usará una ronda futura de mantenimiento | Con la ronda de mantenimiento de infraestructura |

## Abiertos desde el lote 1 de la ronda «Producción 1» (19/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Contraste del color principal de la organización | ADM-MOD-ORG deja elegir hasta cuatro colores y D-48 tiñe el sistema con el primero. Un color muy claro vuelve ilegible el texto blanco de los botones. Opciones: no validar (hoy), advertir al guardar, o calcular el color del texto según la luminosidad | Decidir antes de MAE-04 si se quiere más que «no validar» |
| Nombres de `colorTerciario` y `colorCuaternario` y de dos parámetros «provisionales» | El modelo los marca «a confirmar» | Sin fecha; se usan los nombres de la ficha |
| Nota en `pendientes_CU` (Drive) sobre los asientos | Anotar: «los asientos contables de los seis CU (PROD-CNC-SMB, PROD-CNC-TRN, PROD-REG-MRM, PROD-PNR-FDS, CMP-AJT-STK, PROD-REG-APL) quedan fuera de la ronda Producción 1 (D-45) y se retoman cuando exista contabilidad». Claude no tiene permiso de edición sobre ese documento | Lo anota el estudiante |

## Abiertos desde el lote 3 de la ronda «Producción 1» (19/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Actualizar el modelo y el glosario en Drive (pendientes_MD) | MD-69 ya aplicado en la ficha (peso en gramos, sin `densidad`); dos cosas nuevas que no están en el modelo: la sexta diferencia de `modelo/inventario.md` (semilla inactiva con existencias activas) y que `descripcionEtapa` no la usa ningún caso de uso | Al validar el lote 3 |
| Variedades de prueba cargadas a mano | Si en `/admin/` quedaron variedades de la verificación de MAE-03, la migración de INV-03 las rechaza con un mensaje (no les inventa rangos). Hay que borrarlas en local y en Neon antes de mergear INV-03 | Antes de mergear INV-03 |
| Precondición f de PROD-BAJ-VAR (contratos) | No se verifica: `comercial` no existe en la ronda. Una variedad con un contrato abierto se puede dar de baja. Se cierra cuando `comercial` registre su impedimento (`contratos_abiertos`) | Con `comercial` |
| Variedad usada solo en invernaderos sin Agrónomo | Nadie puede modificarla ni darla de baja (la regla 1 de PROD-MOD-VAR pide un Agrónomo de un invernadero que la use; el Gerente no gestiona variedades) hasta que el Gerente asigne uno. Hoy es un caso raro; decidir si el Gerente o cualquier Agrónomo pueden en ese caso | Si molesta en uso real |
| Nombre de la semilla y largos | **Aprobado el 19/11/2026 (D-49).** Los CU no fijan largos: cultivo hasta 40 y variedad hasta 50. Si el Jardín Botánico necesita nombres más largos, hay que subir el del insumo (100) y revisar esa cuenta | Al validar el lote 3 |
| Variedades presentes y «umbral efectivo» | La advertencia de rangos de PROD-MOD-VAR usa las variedades de lotes activos **y de órdenes de siembra a realizar** (la definición de PROD-PNF-SMB); el prototipo y el texto de MOD-VAR hablan solo de lotes. Se tomó la definición de PRD-01 para que los dos avisos coincidan | Al validar el lote 3 |

## Abiertos desde el lote 4 de la ronda «Producción 1» (20/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Costo por planta: regla 15 de 8.9 contra MD-79 y los CU | El modelo divide por la cantidad inicial; PROD-CNC-SMB, PROD-REG-MRM y MD-79 («decidido sin aplicar») dividen por la cantidad **actual** y bajan el costo con la merma. Se aplica el CU (`docs/patrones/costo_del_lote.md`, D-50). Falta pasar MD-79 al modelo y reescribir la regla 15 en Drive (pendientes_MD) | Al aplicar pendientes_MD |
| Nota de «asientos fuera de la ronda» en pendientes_CU (Drive) | Para PROD-CNC-SMB, PROD-CNC-TRN y PROD-REG-MRM (las precondiciones de ejercicio y cuentas y los asientos quedan fuera, D-45). Ya está en la lista del lote 1: **pegala vos**, no tengo escritura en esos documentos | Antes de PRD-01 |
| Pendientes de MD que las fichas ya aplican | MD-73 (prioridad opcional), MD-77 (Agrónomo–Bitácora «registra»), MD-78 (causa «descarte por selección») y MD-79 (costo): «decidido sin aplicar» en Drive, aplicados en `modelo/produccion.md`. Pegalos en pendientes_MD para que Drive quede igual | Al aplicar pendientes_MD |
| Numeración de PROD-PNF-SMB, PROD-CNC-SMB y PROD-CNC-TRN en Drive | El export reinicia la numeración después de las líneas en cursiva y PROD-CNC-TRN todavía tiene los pasos 4 y 5 separados (pendiente 2 de pendientes_CU). Los extractos ya están corregidos | Al aplicar pendientes_CU |
| ~~`OrigenDocumento` no se implementa~~ | **Resuelto el 20/11/2026 (D-52):** se crea en `contabilidad` (tarea CON-01) y `OrdenTrabajo`, `Bitacora` y `MovimientoInsumo` heredan de él. Lo único que sigue fuera son los asientos (D-45) | Cerrado |
| Sin Capataz activo (extensión 3a de PROD-PNF-SMB) | El prototipo deja planificar con un aviso; el CU lo bloquea. Se aplica el CU. Si el Jardín Botánico prefiere poder planificar sin Capataz, hay que cambiar el CU | Sin fecha |
| Panel «Ritmo sostenible» | Está en el prototipo y en ningún caso de uso. Se implementa último, informativo y recortable (PRD-01, paso 9). Decidir si queda, si se hace un CU o si se saca | Al cerrar PRD-01 |
| Habilitar la semilla (extensión 8b) | El CU la ofrece en el paso 8; el prototipo, al elegir la variedad. Mismo efecto; se deja como el prototipo | Sin fecha |
| Cancelar orden en el prototipo | `orden-cancelar` no pide motivo ni muestra resumen; el CU exige ambos. Se aplica el CU | Sin fecha |
| Notificaciones | El CU las manda «fuera de la transacción» y reintenta (extensiones 19a de PNF-SMB, 20a de CNC-SMB, 14a de CNC-TRN, 9b de CNL-ORD). Con D-42 van **dentro** de la transacción y esas extensiones no aplican | Sin fecha |
| Pestaña «Lotes activos» de la ficha | MAE-03 no dejó un punto de extensión para pestañas. PRD-01 agrega `registrar_pestana_de_invernadero` (`api/extensiones_de_maestros.md`); si se necesitara más, se frena | PRD-01 |
| Alerta de plantas comprometidas | La condición 1 (reservas de cosecha) queda fuera (D-45); la condición 2 está programada pero desde Concretar Transición no puede dispararse. Se ejercita con la merma de PRD-03 | PRD-03 |
| Fecha de los movimientos de insumo de una siembra | La fecha efectiva puede ser anterior a hoy; los movimientos y el consumo llevan esa fecha (D-50 punto 7) y `registrar_salida_por_consumo` recibe `fecha` opcional. Si INV-02 ya se programó sin ese parámetro, es un cambio chico en esa función | Antes de PRD-01 |
| Verificación de lote de insumo por fecha | Un lote de insumo que ya estaba vencido en la fecha efectiva (anterior a hoy) lo propone FEFO si no estaba vencido a esa fecha: es lo correcto, pero puede sorprender | Sin fecha |

## Abiertos desde el lote 5 de la ronda «Producción 1» (20/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Fecha de activación del sector | `SectorProduccion` no la guarda; PROD-PNR-FDS la necesita para la fecha mínima. Se **deriva** de la auditoría (`alta_sector`, `reactivacion_sector`) y del último `fecha_fin` (D-51 punto 6). Si se quiere un campo propio, es una migración en `maestros` | Si resulta lento o confuso |
| Reparto del costo de una aplicación: MD-28 contra el CU | MD-28 dice «cantidad actual del lote»; PROD-REG-APL dice plantas en los sectores del alcance. Manda el CU (D-51 punto 4). Hay que corregir MD-28 en pendientes_MD | Al pegar las notas |
| Pendientes de MD que las fichas ya aplican | MD-75 (Reubicación), MD-76 (`OcupacionSector` con `reubicacion` y la restricción C9), MD-77 (`Bitacora.sectores`) y MD-28 (imputación): anotarlos como «decididos» en pendientes_MD (Drive, solo lectura para Claude) | Al validar el lote 5 |
| Cuenta «Gastos de Producción» (MD-90) | Sigue siendo una propuesta; sin asientos en la ronda no hace falta | Con `contabilidad` |
| ~~Hardware de un sector fuera de servicio~~ | **Resuelto el 20/11/2026 (IOT-CNS-LEC, regla 8; IOT-ALT-HDW, regla 3):** poner un sector fuera de servicio **no cambia** el estado de su hardware; sus sensores se muestran con la marca «sector fuera de servicio» y **no generan alertas ambientales**. `iot` lo consulta directamente (importa `maestros`, nivel 7 > 3); no hace falta un punto de extensión. PROD-PNR-FDS no se modifica | Cerrado |
| Insumo vencido usado igual | PROD-REG-APL no lo ofrece; se corrige con un ajuste de stock. Queda como está | Sin fecha |
| Vuelta a servicio escribe un `otro_evento` | MAE-03 dice «se registró en la bitácora» y PROD-CNS-BIT no tiene un tipo propio; se usa `otro_evento` con el sector | Si se quiere un tipo propio |
| Inicio del Agrónomo sin caso de uso | Es una sección con indicadores (D-51 punto 10), no un CU. Decidir si se documenta como CU | Sin fecha |
| Consulta de bitácora sin cosecha ni incumplimiento | Esos tipos los suman sus rondas; el Capataz no consulta la bitácora (el CU no lo incluye) | Con cosecha |
| Descripciones legibles | La consulta no tiene detalle, así que todo servicio que escribe bitácora arma su `descripcion_evento` (D-51 punto 8); se corrigieron PRD-01 y PRD-02 | Ya aplicado |

## Abiertos desde la revisión del lote 5 (D-52, 20/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| `EtapaProductiva` hereda de `OrigenDocumento` en el modelo de dominio | Parece un error del modelo (una etapa es configuración, no un documento). No se implementa. Corregir en el modelo y en pendientes_MD | Al validar el lote 5 |
| R040 derivado | El modelo guarda la asociación Lote–MovimientoInsumo; se deriva por el consumo y sus imputaciones (D-52 punto 6). Anotar en pendientes_MD | Al validar el lote 5 |
| `OrigenDocumento` en pendientes_MD | Anotar que existe desde esta ronda, con `tipo` discriminador, y que `MovimientoInsumo.origen` reemplaza a `movimiento_origen` | Al validar el lote 5 |
| Huecos en el número de orden | `OT-{numero}` viene de una secuencia de PostgreSQL: una transacción deshecha deja un hueco. Si se quisiera sin huecos, se pasa a un contador bloqueado (más lento y con un nivel más de bloqueo) | Sin fecha |

## Abiertos desde la preparación del IoT (20/11/2026)

Lo que el módulo `iot` necesita de lo ya documentado y lo que el estudiante decidió el 20/11/2026. Las tareas y los extractos del IoT se
agregan en los lotes de documentación del IoT; **hasta entonces estos temas son el registro** (ninguno está aplicado).

| Tema | Qué se decidió | Dónde se aplica |
|---|---|---|
| El IoT no puede ir en paralelo con producción | Sus tareas se hacen **después** de PRD-04 y de USR-10 (D-54); el orden entre el estudiante y su compañero lo fija el plan `docs/tareas/ronda_iot_1.md` (lote IoT 1) | Lote IoT 1 |
| Neon Free (100 horas de cómputo por mes y suspensión al llegar al límite, verificado el 20/11/2026) | La revisión periódica del IoT corre cada 5 minutos y el nodo no consulta con una frecuencia que mantenga la base despierta todo el día; política de uso a documentar. No se paga un plan | Decisión nueva en el lote IoT 1 |
| La revisión periódica genera la alerta y envía el correo de las críticas | Un retraso de hasta 5 minutos no es crítico. El correo sale fuera de la transacción con `core.correo.enviar_correo` (D-54) | IOT-03 |
| Ficha del nodo y API | Node-RED como nodo de referencia; API `/api/iot/v1/` dentro de InfoPonia, con vistas que devuelven JSON (sin dependencias nuevas) y token guardado como resumen | Lote IoT 3 |
| Cambios permitidos en otras apps | Cada tarea del IoT los lista (`core`: acciones de auditoría; `maestros`: punto de extensión de `tiene_sistema_iot` y parámetros de `ConfiguracionOperativa`; `produccion`: valor `mantenimiento` y la restricción de prioridad; `inventario`: R072 y el consumo de repuestos) | Cada tarea IOT-NN |
| Pendientes de MD del IoT | MD-98 a MD-113 están «decididos sin aplicar» en Drive; el modelo del IoT los adopta cuando se escriba `docs/modelo/iot.md` | Lote IoT 1 |


## Abiertos desde UI-01 (20/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| `.mono` | La tarea UI-01 pedía quitar `.mono`; se conservó con la definición del prototipo (solo cifras tabulares) porque el prototipo lo usa unas 40 veces y la tarea pide poder copiar su HTML. Corregir el texto de UI-01 | Al validar UI-01 |
| D-29 contra el prototipo | `.btn-ghost` (contraste AA del borde) y los avisos breves (radio de 6 px, animaciones, posición abajo en menos de 760 px) conservan D-29 y difieren del prototipo. Decidir si D-29 se actualiza al aspecto v2 y se ajustan las pruebas `test_d29_` | Sin fecha |
| Íconos | `core/templatetags/iconos.py` no estaba en «Permitido fuera de la app» de UI-01; se le agregaron los 20 íconos del prototipo que faltaban para que las tareas de la ronda no toquen `core`. Anotarlo como permitido en la tarea | Al validar UI-01 |
| `.mnav` del prototipo | El prototipo la deja siempre oculta (su `display:none` va después de la media query). En el sistema se muestra en menos de 760 px. Corregir el prototipo | Sin fecha |
| Color de la organización | Las variantes oscura y clara salen de `color-mix()` (D-48, ver arriba); si MAE-04 quiere otro cálculo o validar el contraste del color elegido, se decide ahí | MAE-04 |
| Revisión visual de UI-01 | No hubo navegador en la sesión: las pantallas de `core` (usuarios, auditoría, Mi perfil) conservan su HTML con los componentes v2 que ya usaban; falta confirmar a mano que ninguna se vea con el aspecto viejo | Revisión a mano de UI-01 |



## Abiertos desde NOT-01 (20/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| «Todos los roles» (D-42) | D-42 dice que todos los roles ven la campana, pero `docs/casos_de_uso/usuarios.md` («Pantallas») la define para los seis roles operativos y dice que el Administrador no la tiene. Se implementó sin campana para el Administrador (`core:campana` le da 403). Corregir D-42 | Al validar NOT-01 |
| Textos de los avisos | D-42 y el paso 7 decían «con el texto de D-42» sin traer ninguno. Se usaron los aprobados: «Quedó a cargo de <invernadero>» / «El Gerente le asignó el rol de <rol>. Recibe: <descripción>: <cantidad>, … o No recibe nada pendiente.»; «Pendientes que esperan al Gerente» / «Tiene N pendiente(s). … o No tiene pendientes.»; y el de la ventana de baja del Gerente. Escribirlos en D-42 y en `docs/api/notificaciones.md`, cuyo ejemplo dice «lo asignó como Agrónomo» | Al validar NOT-01 |
| D-14 en el alta del Gerente | El paso 5 pide que, sin Gerente activo, la notificación se omita y el alta no falle. En `alta_usuario` el destinatario es el Gerente recién creado, que ya es el activo (D-09): ese caso no existe ahí y solo aplica a `notificar_al_gerente` (probado en la API). Corregir el texto del paso 5 | Al validar NOT-01 |
| Respaldo de severidad (MD-109) | `items_de_campana` toma la severidad del tipo registrado y, si el código ya no está registrado, la que se guardó con la alerta, en vez de fallar y romper la campana de todas las pantallas. D-42 y el paso 6 no lo preveían. Anotarlo en D-42 y en `docs/api/alertas.md` | Al validar NOT-01 |
| Aviso antes del traspaso | `modificar_invernadero` calcula `_aviso_de_personal` antes de guardar y traspasar (después ya no queda nada en la persona saliente) y solo si hay al menos un rol entrante no nulo; con el cambio confirmado, `contar_traspaso` ahora también se llama, una vez por rol entrante. El paso 7 decía «ya armado por `_aviso_de_personal`» sin precisar cuándo | Al validar NOT-01 |
| Punto rojo y marca de lectura | El panel marca como leídas, al cerrarse, las 30 notificaciones mostradas solo si se vio la pestaña «Notificaciones» mientras estuvo abierto (el prototipo, solo si esa pestaña estaba a la vista al cerrar). El punto rojo sigue a D-42 (alerta activa no leída o notificación sin leer) y no al prototipo, que lo muestra con cualquier alerta | Revisión a mano de NOT-01 |
| `test_campana_alertas.py` | `maestros/tests/test_campana_alertas.py` lo piden el paso 6 y «Hecho cuando», pero no figura entre los «Archivos nuevos» de «Límites». Agregarlo | Al validar NOT-01 |
| Docstring de `no_leidas` | El docstring de `AlertaQuerySet.no_leidas` (`maestros/models.py`) dice «las que cuenta la campana, tarea de notificaciones». No se tocó porque `maestros/models.py` no estaba en «Permitido fuera de la app». Cambiarlo por «las que prenden el punto rojo de la campana, NOT-01 y D-42» | La próxima tarea que toque `maestros/models.py` |
| Abrir una alerta desde la campana | El enlace de cada alerta lleva a la ficha del invernadero y no llama a `abrir_alerta`: la alerta sigue «no leída» y el punto rojo no se apaga. Está en `docs/disparadores.md` («Cuando exista la primera notificación o alerta», punto 4) | MAE-02c |


## Abiertos desde MAE-03 (20/11/2026)

- **Agrónomo ajeno:** la «Verificación a mano» y el paso 4 de la tarea decían que ve los sectores sin acciones; manda la regla 1 de PROD-CNS-SCT y D-28: recibe 403. Texto corregido en la tarea.
- **Modelo (`docs/modelo/maestros.md`):** `nombre_sector` de hasta 40 caracteres y los códigos de perfil `hoja_verde`, `pastura`, `frutos_grandes`, `frutos_pequenos`, `flores` y `hierbas` no estaban fijados. Pasar a la ficha.
- **Notificación de PROD-MOD-CLT b:** el CU no fija el texto. Título «Cambió el cultivo {anterior}», detalle «{Nombre Apellido} lo renombró a {nuevo}. Sus variedades siguen igual.»; una sola llamada a `notificar_a_varios`, sin el invernadero de cada destinatario (el prototipo lo incluía). Se notifica solo a Agrónomos activos de invernaderos activos, sin el actor. Pasar al CU.
- **Regla 4 de PROD-MOD-SCT y de PROD-BAJ-SCT:** la advertencia se dispara cuando el sector activo es el último de su tipo (como `ultimoAviso`), aunque no haya lotes ni variedades afectados; un sector fuera de servicio no la dispara. En la baja, los impedimentos van antes que la advertencia. Aclarar en el CU.
- **API de `maestros`:** se hizo `registrar_efecto_de_baja_de_sector` y no `pasar_a_fuera_de_servicio` (queda para PRD-04). `bloquear_sectores` verifica también que el invernadero esté activo. `variedades_de_cultivos` usa lo propio de `maestros` también para un cultivo que el registrante no trae.
- **Interfaz:** el menú «⋯» es un `<details>` propio de `maestros` (no existe el componente en `core`). «Volver a activar» muestra un texto genérico (la fecha y el motivo son de PRD-04). «Renombrar» muestra siempre el aviso de semillas e invernaderos: sin JavaScript no se sabe si el nombre cambió.
- **Al Gerente, toda ruta de cultivos le da 404, también con otro método HTTP** (no 405), para no delatar la ruta.

## Abiertos desde MAE-04 (21/11/2026)

- **Contraste del color principal:** el sistema no valida el contraste; un color muy claro hace ilegible el texto blanco de los botones (ADM-MOD-ORG; fuera de alcance de MAE-04).
- **Permisos explícitos fuera de «Límites»:** `core/tests/test_usr_ini_ses.py` (solo `test_d24…`, que ahora vacía el punto de extensión de identidad), `core/tests/urls_prueba_acceso.py` (una línea, `path("configuracion/", include("maestros.urls_configuracion"))`) y `config/urls.py` (una línea para `/configuracion/`). Quien agregue otra entrada del menú de `maestros` tiene que sumarla también a ese urlconf de prueba.
- **Lo implementado distinto de lo escrito:** la entrada del menú se registra con `registrar_entrada` desde `ready()` (al final del menú del Gerente), no en `core/menu.py`; las rutas están en `maestros/urls_configuracion.py` (la tarea no fijaba la URL); la rama real es `feature/mae-04-configuracion-y-organizacion`.
- **Decisiones de aplicación sin documento:** colores guardados en mayúsculas; error de orden de colores en el color cargado fuera de orden; opcional vacío como nulo en la auditoría; guardar sin cambios confirma igual el aviso; tope de cada parámetro igual al entero de la columna. Pasar a la ficha de `PerfilOrganizacion` y a ADM-MOD-ORG.

## Abiertos desde INV-01 (21/11/2026)

- **Permisos explícitos fuera de «Límites»:** una línea `path("inventario/", include("inventario.urls"))` en `config/urls.py` y otra en `core/tests/urls_prueba_acceso.py`.
- **Lo implementado distinto de lo escrito:** el menú se registra con `registrar_entrada` desde `InventarioConfig.ready()`, no en `core/menu.py`; la tarea pide «filtros» pero el prototipo no los tiene en el catálogo ni en las categorías, así que no se hicieron; la baja de categoría confirma en una ventana (el prototipo usa un aviso directo); la rama real es `feature/inv-01-tipos-de-insumo-y-catalogo`; los textos del prototipo («Ingrese», «Habilítelo») pasan al voseo del sistema.
- **Decisiones de aplicación sin documento:** las 15 del «Cierre» de la tarea (`tipo_movimiento`, `CheckConstraint` extra de `TipoInsumo`, `isnull=False` explícito, unidades en minúscula en la base, `max_length=30`, claves de `motivo_ajuste`, clave de alertas `insumo:<id>`, lote inicial como `ajuste_positivo`/`carga_inicial`, claves de auditoría, aviso MOD-INS en una llamada, insumo de un invernadero sin Agrónomo no gestionable, bloqueos solo si cambia el valor, baja sobre habilitaciones de invernaderos inactivos, orden de categorías, pantallas). Pasar a la fila de decisiones si el equipo las confirma.


## Abiertos desde H2 (20/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Registrar H2 en el modelo de Drive | Ítem nuevo de pendientes_MD: `OrdenTrabajo.motivoCancelacion` (texto, obligatorio al cancelar, 1 a 300) y `fechaResolucionOrden` también como fecha de cancelación; ya aplicado en `docs/modelo/produccion.md` (Diferencias n.º 17). Pegalo vos: no tengo escritura en Drive | Antes de cerrar la ronda del modelo |
| Aviso al Vendedor con el motivo (PROD-CNL-ORD, postcondición l) | Fuera de la ronda (D-45). La versión 0.1 del CU no menciona el motivo en ese aviso; ajustarla en Drive (pendientes_CU). Se programa con Cosecha | Cuando exista Cosecha |
