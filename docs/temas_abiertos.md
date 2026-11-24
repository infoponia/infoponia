# Temas abiertos — InfoPonia

Temas que todavía no tienen tarea ni disparador. Se leen al planificar, no en cada sesión. Cuando un tema pasa a tener
tarea (`docs/tareas/`) o disparador (`docs/disparadores.md`), se saca de acá y se anota adónde fue.

Copiados sin cambios de `docs/estado.md`, «Temas abiertos», el 18/11/2026. Actualizado el 19/11/2026 (lote 0 de la ronda
«Producción 1»).

- Lista cerrada de los casos de uso del 80% y orden de implementación. Tienen plan «Producción 1»
  (`docs/tareas/ronda_produccion_1.md`) y «Comercial 1», con cosecha (`docs/tareas/ronda_comercial_1.md`, 21/11/2026); faltan el del
  IoT (en lotes aparte) y los de compras y contabilidad.
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
| Tope de pedidos de recuperación de contraseña | USR-09b: `docs/tareas/usuarios/USR-09-seguridad-produccion.md` |
| Tope de intentos de identificación | USR-09b: `docs/tareas/usuarios/USR-09-seguridad-produccion.md` |
| `DEBUG` apagado por defecto (Render ya tiene `DJANGO_DEBUG=0`) | Hecho en USR-09a: D-99 |
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
| Costo del cron job de Render | Render cobra un mínimo de 1 dólar por mes por cada cron job (verificado en su documentación el 19/11/2026). Alternativa gratuita, si molesta: ninguna que sea confiable (un hilo dentro del web service muere cuando Render lo duerme) | Al final de la implementación, cuando se arme el único cron job (D-56) |
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
| Variedades presentes y «umbral efectivo» | La advertencia de rangos de PROD-MOD-VAR usa las variedades de lotes activos **y de órdenes de siembra a realizar** (la definición de PROD-PNF-SMB); el prototipo y el texto de MOD-VAR hablan solo de lotes. Se tomó la definición de PRD-01 para que los dos avisos coincidan. Desde el 21/11/2026 el umbral se calcula en una sola función de `inventario`, `umbral_efectivo`, que usan PRD-01 y el IoT (`docs/api/variedades.md`, «Umbral efectivo») | Al validar el lote 3 |

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

Lo que el módulo `iot` necesitaba de lo ya documentado y lo que el estudiante decidió el 20 y el 21/11/2026. **Desde el lote IoT 0
(21/11/2026) todos tienen dónde aplicarse**: quedan acá como registro y se tachan cuando la tarea que los aplica se mergea.

| Tema | Qué se decidió | Dónde se aplica |
|---|---|---|
| El IoT y la producción | El IoT va en paralelo con «Comercial 1» y cada tarea espera solo a las de producción que necesita; **IOT-01 e IOT-02 van en paralelo con «Producción 1»** (estudiante, 21/11/2026) | `docs/tareas/ronda_iot_1.md`, sección 2 |
| Neon Free (100 horas de cómputo por mes y suspensión al llegar al límite, verificado el 20/11/2026) | Revisión periódica con un comando a mano mientras se desarrolla; cron job al final, encendido solo para presentar. No se paga un plan | D-71; IOT-04 |
| La revisión periódica genera la alerta y envía el correo de las críticas | Un retraso de hasta 5 minutos no es crítico. El correo sale fuera de la transacción con `core.correo.enviar_correo` (D-54) | D-71; IOT-04 |
| Ficha del nodo y API | Node-RED como nodo de referencia; API `/api/iot/v1/` dentro de InfoPonia, con vistas que devuelven JSON (sin dependencias nuevas) y token guardado como resumen | D-70; contrato v1 en `docs/api/nodo/` (lote I2a, D-74) |
| Cambios permitidos en otras apps | `core`: acciones de auditoría y `core/enlaces.py` si no existe; `maestros`: punto de extensión del estado del IoT, los 14 parámetros y la sección «Módulo IoT» de la pantalla de configuración (IOT-04); `produccion`: el valor `comando` de `Bitacora.TipoEvento` (IOT-05), y la restricción de la prioridad del mantenimiento (IOT-07; el valor `mantenimiento` lo crea PRD-01, D-67 punto 1); `inventario`: solo lectura (R072 y `umbral_efectivo`) | `ronda_iot_1.md`, sección 5; «Permitido fuera de la app» de cada tarea |
| Pendientes de MD del IoT | MD-98 a MD-113 aplicados en el extracto | `docs/modelo/iot.md` |
| Ronda 23 en el documento del modelo | «Copia de modelo_dominio» todavía no tiene la sección 8.24 ni las fichas nuevas; el repo ya las usa | Cuando se aplique la ronda 23 en Drive (sin fecha) |
| Textos de los casos de uso que hay que corregir en «CU extendidos» | IOT-REG-SIS («Temas abiertos»: cita `docs/api_nodo.md` y el simulador); IOT-ENT-INF (regla «Alertas», extensiones 1a, \*b y 5g) e IOT-RSV-CMD (4b.3): el correo sale por la revisión periódica (D-71) | Con los extractos: lote I1 (REG-SIS), I2a (ENT-INF: **ya corregido en `entregar_informacion.md`**, falta pasarlo a Drive) e I3 (RSV-CMD: **ya corregido en `resolver_comando.md`**, falta pasarlo a Drive) |
| Pendientes de Drive fuera del repo | DCU con el paquete IoT; caso 21 de pendientes_CU; correcciones de CU-90 y CU-92 de la «Documentación para la IA» | Sin fecha (no frenan a Claude Code) |
| Interpretaciones de IOT-ENT-INF en el código (lote I2a) | Siete puntos que el caso de uso no resuelve: «cambiado en el invernadero» inicial, histéresis en un umbral angosto, variable del umbral vacía, resolución al quedarse sin umbral, identificador mal formado, reglas de los estados y sector fuera de servicio | D-75 (**validada el 22/11/2026**; falta pasarla a «CU extendidos») |
| Aviso de compatibilidad del actuador, sin JavaScript (IOT-02, D-61) | Con HTMX, el aviso «el nodo no anunció el comando de…» llega al cambiar el identificador o el tipo. Sin JavaScript no hay evento de cambio: aparece al volver a dibujar el formulario y, si el actuador queda incompatible, en el aviso de después de guardar. Interpretación de Claude Code; el caso de uso no distingue | Confirmar con el equipo que alcanza; IOT-ALT-HDW (`docs/casos_de_uso/iot/hardware.md`) |
| Reglas nuevas de la revisión, del panel y de la configuración IoT (lote I2b) | Inactividad, «no registrado» sin mensajes, resúmenes, fotoperíodo, retención, correo y refresco; reglas 2b a 7b de ADM-MOD-CFG | D-76 (**validada el 22/11/2026**; falta pasarla a «CU extendidos», en IOT-ENT-INF y en ADM-MOD-CFG) |
| Correo de una alerta crítica sin enlace | El comando de la revisión no conoce la dirección del sitio (no hay una variable de configuración): el correo dice «entrá a InfoPonia, menú «Alertas»» (D-76, punto 7) | Si se agrega una variable con la dirección pública (por ejemplo con USR-09) |
| Revisión que corre poco | Con el cron apagado fuera de las presentaciones (D-71), la primera corrida después de mucho tiempo resume y calcula todo lo pendiente antes de borrar (D-76, puntos 4 a 6): puede tardar más. Medirlo en la primera presentación | Al armar el cron (disparador «Cuando se arme el cron único») |
| Interpretaciones de comandos y reglas (lote I3) | Doce puntos que IOT-EMT-CMD, IOT-RSV-CMD, IOT-CNL-CMD y las reglas no fijan | D-78 (**validada el 22/11/2026**; falta pasarla a «CU extendidos») |
| MAE-02c en dos versiones | La PR #46 trajo una MAE-02c sin el enlace de D-62; los lotes tenían otra con él. Se unieron en los documentos (decisión del estudiante, 22/11/2026), pero **la PR #47 programó la versión de `main`**, sin el punto de enlaces, sin la ruta que abre y redirige y con un solo `tipo` en `consultar_alertas` | **Resuelto en MAE-02d** (22/11/2026; D-62, tercera enmienda, validada). COM-03b e IOT-04 ya pueden usar el enlace |
| Contador de pedidos con varios procesos | La caché local cuenta por proceso de gunicorn (D-70, punto 5): con más de un proceso, el límite real se multiplica | Si cambia el despliegue (sin fecha) |
| La orden de mantenimiento automática (lote I4) | Se cancela solo desde la ficha, con el alcance del IoT; sufijos de la alerta; aviso y sección del Inicio para el Técnico (estudiante, 22/11/2026). Claude sumó cinco puntos: el largo de la alerta, los avisos solo con la cuenta activa, sus textos, «Cancelarla» marcada al volver a activar, y el traspaso y las asignaciones de la cuenta | D-79 (puntos 1 a 4 vigentes; **5 a 9, a validar**); IOT-07 |
| Textos y permisos que hay que pasar a «CU extendidos» (lote I4) | IOT-RSV-CMD: los textos de la alerta en 4b.4a y 4b.4b (D-79, punto 3). PROD-CNL-ORD: el mantenimiento del IoT lo cancela quien tiene el alcance del IoT, también el Gerente sin Agrónomo activo (D-79, punto 2), y su tema abierto «Alerta que originó un mantenimiento» queda respondido por D-73 (punto 4) | En Drive (no frena a Claude Code) |
| ~~`produccion` frente al tipo `mantenimiento`~~ | ~~IOT-07 supone que `cancelar_orden_incluida` acepta una orden sin reservas ni sectores de cualquier tipo, y que la bandeja y las listas de órdenes filtran por tipo~~ | **Resuelto en la documentación (lote C5b, D-67 punto 1):** lo hace y lo prueba PRD-01 («Tipos de orden futuros» de su «Límites»), que además crea el valor `mantenimiento`. Se tacha del todo cuando PRD-01 se mergee |


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
| Abrir una alerta desde la campana | El enlace de cada alerta lleva a la ficha del invernadero y no llama a `abrir_alerta`: la alerta sigue «no leída» y el punto rojo no se apaga. Está en `docs/disparadores.md` («Cuando exista la primera notificación o alerta», punto 4) | ~~MAE-02c~~ Hecho el 22/11/2026 |

## Abiertos desde MAE-02c (22/11/2026)

- **Fuera de «Permitido fuera de la app»:** `config/urls.py` (`path("alertas/", ...)`, aprobada al planificar) y `core/tests/urls_prueba_acceso.py` (la misma línea; sin ella fallan dos pruebas de `core` que arman el marco con ese URLconf, como con MAE-04 e INV-01). Agregar ambos a «Permitido fuera de la app» de la tarea.
- **La entrada «Alertas» no tiene contador.** La tarea lo pedía y `core.menu` no lo admite. Corregir el texto de la tarea o decidir ampliar el menú (disparador nuevo en `docs/disparadores.md`).
- **Nombre de un tipo no registrado.** La tarea no decía qué mostrar: se muestra el código guardado (columna, filtro y detalle). La severidad sale de la guardada (MD-109). Anotarlo en el extracto y en `docs/api/alertas.md`.
- **Una regla de CSS nueva** (`.alerta-punto`, en `maestros/static/maestros/css/alertas.css`): no hay una clase equivalente para un punto dentro de una fila.
- **Alertas de un invernadero inactivo.** La consulta no filtra por el estado del invernadero (R3 habla del estado de la alerta; `para` tampoco): figuran en el listado. Al Agrónomo, el detalle no le ofrece «Ver invernadero» (esa ficha no está en su alcance). Decidir si una baja de invernadero debería sacarlas del listado.
- **El detalle solo responde a GET** (HEAD da 405) y no se cachea, porque abrirlo cambia la lectura. Escribirlo en R7 del extracto.
- **Filtros inválidos:** un `invernadero` no numérico, negativo, cero o fuera de rango da una lista vacía con el mensaje del filtro, sin error.
- **R4 y el prototipo.** El extracto atribuye «la más reciente primero» a `alertas()` del prototipo, pero este conserva el orden previo dentro de cada nivel. Se implementó lo que dice R4.
- **Sigue pendiente** el docstring de `AlertaQuerySet.no_leidas` (esta tarea no tocó `maestros/models.py`).
- **Pendientes de Drive** (no tengo escritura): la postcondición de CU-46 con la propuesta A, «Solo cambia el estado de lectura de la alerta que el usuario abre; el listado y la búsqueda no cambian nada» (pendientes_CU), y el origen de la alerta (R6) cuando existan Hardware, Telemetría, Merma y SolicitudRevisión.
- **Sin verificar:** HTMX en vivo y el aspecto de las pantallas en un navegador real (no hay pruebas de navegador, por regla).

## Abiertos desde MAE-02d (22/11/2026)

- **Comando `cargar_datos_de_verificacion`** (`maestros/management/commands/`, con sus pruebas): lo exige CLAUDE.md, pero no estaba en «Permitido fuera de la app» ni en ningún documento. Va en `maestros` porque `core` no puede importar sus modelos (A1). No crea ni toca ningún Gerente (D-09). Los correos llevan siempre el número (`agronomo@prueba1.local`). Las próximas tareas lo amplían: si una app de nivel mayor tiene que hacerlo, decidir si se muda. Agregarlo a «Permitido fuera de la app» de la plantilla de tarea. *(Actualización 23/11/2026, IOT-03: ya se decidió: el comando es uno solo, en `core`, con una función por app; la de `maestros` vive en `maestros/verificacion.py`; `docs/patrones/datos_de_verificacion.md`.)*
- **`maestros/servicios/invernaderos.py`** no figuraba en los pasos, pero es donde vive `items_de_campana` (paso 5).
- **`ItemDeAlerta` en `core/extensiones.py`:** su comentario dice que `url` lleva «a la ficha del invernadero» (ya no es cierto desde MAE-02c). No se tocó (nada de `core`); corregir cuando se toque ese archivo.
- **Un registrante registrado en dos pasos:** la misma función para `("a",)` y después para `("a", "b")` queda como dos pares y se la llama dos veces. No pasa con el uso previsto; si una app registra en dos pasos, agrupar por función.
- **Base de pruebas `test_infoponia`:** hubo que recrearla una vez (sin `--keepdb`, autorizado) por una historia de migraciones inconsistente tras integrar PRD-02 (`produccion.0002` antes de `core.0020`). Si el CI o otro equipo ve el mismo error, es lo mismo.
- **Sin verificar:** el paso por `alertas:ir` desde la campana con una app real (ninguna registra enlaces todavía): lo cubren las pruebas con registrantes falsos, incluida la de punta a punta.

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

## Abiertos desde DIA-01 (21/11/2026)

- **Lo implementado distinto de lo escrito, o que la tarea no decía:**
  - Solo un registro idéntico de un paso (código, nombre, orden y función) es idempotente; el mismo código y la misma función con otro nombre u otro orden dan `RuntimeError`. D-56 y la tarea solo nombraban el código con otra función y el orden repetido.
  - `--fecha` exige `AAAA-MM-DD` con ceros: `strptime` acepta `2026-1-5`, por eso se compara además con `isoformat()`.
  - Los textos de la salida del comando (encabezado «Proceso diario del AAAA-MM-DD.», cierre «Pasos correctos: N · fallidos: N.», «No hay pasos registrados.») no estaban fijados en D-56. Conviene anotarlos en D-56 si INV-02 o el cron los usan.
  - La fecha se valida antes que `--listar`: `--listar --fecha 2026-13-01` da error. Sin pasos registrados, `--solo <cualquier código>` dice «No hay pasos registrados.» y termina en 0, en lugar de «código inexistente».
- **Pendiente para INV-02 y las demás apps:** registrar sus pasos con `registrar_paso_diario` desde su `AppConfig.ready()`. Si registran un orden que ya usa otro paso, `ready()` lanza `RuntimeError` al arrancar: es lo buscado, pero conviene que lo sepan.

## Abiertos desde INV-02 (21/11/2026)

- **Lo implementado distinto de lo escrito, o que la tarea no decía** (detalle en el «Cierre» del archivo de la tarea):
  - Rama distinta de la de la tarea; prefijo de pruebas de extensión: la tarea pide `test_extension_...` y `.claude/rules/pruebas.md` pide `test_ext_...`.
  - `reevaluar_alertas_del_insumo` recibe el id (`docs/api/stock.md`), no el objeto (`docs/patrones/stock.md`): unificar el patrón.
  - Servicios de `InsumoInvernadero`: validación después de los bloqueos; `habilitar_insumo` siempre reevalúa; los ganchos de la baja filtran `reservas_activas` y auditan con el actor de la baja.
  - `registrar_salida_por_consumo`: `ValueError` ante datos inválidos, consolida lotes repetidos, crea o incrementa el faltante y no audita.
  - Ajuste: recuento de todos los lotes, no se sube un lote vencido, tope del faltante como destino, huella con lotes y reservas, sin `cambios` si el stock neto no cambia, redondeo mitad hacia arriba, se puede ajustar la existencia activa de una semilla dada de baja.
  - Vencimientos: sin Agrónomo activo no se alerta (manda el CU sobre D-41); audita con `usuario=None` por alerta creada; el paso diario lanza el error al terminar; el comando importa `_leer_fecha` de `proceso_diario`.
- **Cambio de criterio en el paso 8 de INV-02 (revisión a mano, 21/11/2026):** la tarea decía «la pantalla se actualiza tras cada dato». Ahora el ajuste valida y calcula solo con «Ver resumen» y «Confirmar ajuste»; los selectores redibujan sin validar. Corregir la frase del paso 8 de la tarea y, si hay un caso de uso con ese texto, también ahí.
  - Dos pruebas de INV-01 cambiadas (redirect del inicio de `/inventario/` y del alta de insumo).
  - La tarea dice que de «Cuando existan los pedidos de `compras`» «los tres puntos ya existen»: la sección tiene dos.
- **Para decidir:** si D-41 (sin Agrónomo, la alerta va al Gerente) debe corregirse o si la revisión de vencimientos es la excepción que fija el CU.
- **Sin verificar:** HTMX en vivo y el aspecto de las pantallas en un navegador real (no hay pruebas de navegador, por regla).

## Abiertos desde MAE-05 (21/11/2026)

- **Fuera de «Permitido fuera de la app», con permiso expreso del estudiante:** el ícono `truck` en `core/templatetags/iconos.py` (una línea, copiada de `logistica_transportista.html`).
- **«Transportistas» sin etiqueta en la auditoría.** `RegistroAuditoria.ETIQUETAS` (`core/models.py`, fuera de lo permitido) no tiene la clave `transportistas`: el detalle de `modificacion_invernadero` se ve con la clave tal cual. Sumarla en una tarea chica de `core`.
- **Cuenta reactivada de un Transportista con fila en un invernadero inactivo (D-55, punto 8).** Queda activo en un invernadero inactivo: no se puede quitar (regla 5 de PROD-MOD-INV), pero sí trasladar. Ningún documento lo cubre; decidir si el invernadero inactivo debe dejar quitarlo.
- **Interpretaciones sin texto en la tarea:** el origen de un traslado se bloquea con `select_for_update(no_key=True, of=("self",))` y puede estar inactivo; `candidatos` devuelve `Candidato(transportista, invernadero)` y ordena en la base (`Lower(...)`, con collation); un id que no es de un Transportista da 404; quitar a un inactivo también notifica; sin elegir a nadie la ventana dice «Elegí un transportista.»; el texto del impedimento va en singular y plural («Tiene 1 transportista activo» / «Tiene N transportistas activos»), no con «(s)»; el contador de «Personal por asignar» dice «1 pendiente».
- **Sin traducción de `IntegrityError`.** La restricción única es un respaldo: el bloqueo de la cuenta la hace inalcanzable y la tarea no da un código para ella.
- **La ventana «Agregar» no resalta el candidato elegido.** Usa radios nativos dentro de `label.opt`; el prototipo marca la opción con `aria-pressed`, que hoy no se actualiza sin JavaScript.
- **Sin verificar:** HTMX en vivo y el aspecto de las pantallas en un navegador real (no hay pruebas de navegador, por regla).

## Abiertos desde el lote C6 de «Comercial 1» (22/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| ~~D-68, puntos 5 a 9~~ | Los propuso Claude en el lote C6 (los puntos 1 a 4 los validó el estudiante antes de escribir). Los más discutibles: guardar `SolicitudRevision.entrega` aunque el modelo la deduzca (punto 5); la tabla `IntentoFallido`, que el modelo no tiene (punto 6); `cant_perdida` y `cant_devuelta` en la línea (punto 7); la vigencia calculada del enlace de confirmación (punto 8) | **Validados el 22/11/2026** |
| Estado de paso entre COM-06a y COM-06b | Las entregas de suministro concretadas en ese lapso reciben el comprobante sin enlace y quedan «no confirmado» para siempre (COM-06b no les crea enlace). No rompe datos | Programar COM-06b enseguida de COM-06a |
| COM-04a suma lo de `produccion` de las entregas | Decisión del estudiante (D-68, punto 3): COM-04a, ya escrita y validada en el C5b, suma la sección 10 de `docs/api/produccion.md`. Si COM-04a ya se hubiera programado, lo haría COM-06a con otra migración de `produccion` | Al programar COM-04a |
| Exceso de envases: la utilizada real | Con la opción A, `ReservaInsumo.cantidad_utilizada` guarda la utilizada **topeada** en la reservada; la real queda en el consumo (que la incluye) y en la auditoría. Una consulta futura de «utilizado por orden» tiene que leer el consumo, no la reserva | Al escribir una consulta de envases |
| Aviso a «quien registra los asientos manuales» | COM-ATN-ENR (postcondición b) lo pide; ese rol es de la ronda de contabilidad. Hasta entonces se avisa a los Gerentes activos y al Vendedor | Ronda de contabilidad |
| Planificada de una línea concretada | Después de concretar, la planificada se lee como `entregada + perdida + devuelta` (las reservas de un detalle rechazado quedan «liberadas» y ya no la dan). Lo que COM-05a1 calcula de las reservas vale solo «a realizar» | Ya resuelto en el código (D-68, punto 7) |
| Correo del intento fallido al cliente | COM-CNC-ENT 4a dice «notifica al cliente»: se hace por correo, con el resultado en `estado_aviso_cliente` y el reintento del paso 50 (como los demás correos de la entrega) | — |
| Pendientes de Drive del lote C6 | pendientes_CU: nada nuevo de los casos de uso (los cambios son del código). pendientes_MD: proponer que el modelo registre los intentos fallidos (D-68, punto 6; tema abierto de COM-RSV-QJA). MD-132, MD-136 y MD-137 ya están en «MD · Cambios… (comercial)» | Al pegar en Drive |

## Abiertos desde el lote C7 de «Comercial 1» (22/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| D-69, puntos 9 a 17 | Los propuso Claude con el lote (los puntos 1 a 8 los validó el estudiante antes de escribir). Los más discutibles: guardar lo descontado y lo reintegrado en la solicitud (punto 9); la copia de la resolución en `Anulacion` (punto 10); el disparo de COM-RSV-SUM con `on_commit` en el mismo pedido (punto 13); la severidad `CRITICA` de «suministro resuelto» (punto 14) | Al validar el lote C7 |
| Estado de paso entre COM-07a y COM-07b | Una aceptación que supera los tolerados deja el contrato «vigente» con más incumplimientos que los tolerados; el paso 33 de COM-07b lo resuelve en su primera ejecución. Mientras tanto, la pre-reserva y la planificación siguen actuando sobre ese contrato (lo que creen, COM-RSV-SUM lo deshace). No rompe datos | Programar COM-07b enseguida de COM-07a |
| Notificaciones sin enlace (D-42) | La regla 6 de COM-CNS-SRV pide abrir la ficha desde la notificación; hoy la notificación nombra la solicitud y la pestaña la busca por número (D-69, punto 16). El Gerente tiene la alerta, que sí tiene enlace | Cuando las notificaciones tengan enlace |
| Recordatorio de solicitudes pendientes | Temas abiertos de COM-EVL-DSC y de COM-RSV-QJA: no hay plazo ni recordatorio; mientras tanto, el contador de la pestaña y el grupo del panel | Al decidirlo con el Jardín Botánico |
| Quién ejecuta el reintegro | «El reintegro se considera hecho al aceptar» (los dos casos de uso): nadie recibe un aviso para hacerlo. Hoy queda en la ficha (monto y medio) y en el comprobante | Al decidirlo con el Jardín Botánico; la ronda de contabilidad |
| La alerta «período sin cobertura completa» al resolver un contrato | COM-RSV-SUM no lo dice; COM-07b la resuelve (regla 7 de 8.18). Anotarlo en pendientes_CU | Al pegar en Drive |
| Un registro de auditoría por COM-RSV-SUM | La postcondición m pide que las cancelaciones de PROD-CNL-ORD dejen «sus propios logs»; el código deja uno solo con todo lo afectado (como COM-CNL-CVT, D-36). Anotarlo en pendientes_CU | Al pegar en Drive |
| `avisar_agronomo` en las dos cancelaciones incluidas | Argumento nuevo de COM-07b (por omisión `True`): el Agrónomo recibe una sola notificación por invernadero en una resolución (situación 9 de COM-RSV-SUM) | Al programar COM-07b |
| El extracto de COM-RSV-SUM | El plan decía `comercial/suministro.md`; va en `comercial/resolucion.md` porque `suministro.md` ya pasa de mil líneas y COM-07b no necesita leer COM-PCT-SUM ni COM-MOD-SUM. `suministro.md` remite al nuevo | — |
| Pendientes de Drive del lote C7 | pendientes_CU: COM-EVL-DSC v0.3 con la extensión 6d (MD-115) y «Lo sigue: COM-ANL-SRV»; COM-ANL-SRV v0.2 con la alerta (D-69 punto 4), los bloqueos 2a y 2c (punto 5) y la bitácora (punto 6); COM-CNS-SRV, regla 6 (punto 16); COM-RSV-SUM, las dos filas de arriba. pendientes_MD: el tipo de bitácora «anulación de una resolución»; que MD-115 diga que el descuento y el reintegro se registran en la solicitud | Al pegar en Drive |

## Abiertos desde el lote C8 de «Comercial 1» (23/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| D-94 completa | La propuso Claude con el lote (el estudiante pidió escribirlo sin validar el corte antes). Los más discutibles: el corte en tres (punto 1), R154 como `LineaPago` y no `Entrega.pago` (punto 2), la fecha del cobro que corrige uno anulado (punto 10) y las fechas del indicador de faltantes y rechazos (punto 15) | Al validar el lote C8 |
| Número de la decisión del C8 | El contexto del C8 decía «desde D-80», pero D-80 a D-83 ya las usaron IoT y producción. Con la regla de `docs/decisiones/README.md` («Numeración») es **D-94**; si al abrir el PR está tomada, se renumera | Al abrir el PR del lote |
| Estado de paso entre COM-08a y COM-08b | Un cobro mal registrado no se puede anular; la extensión 2b de COM-ANL-SRV bloquea para siempre la anulación de una solicitud cuya entrega se cobró con descuento; COM-CNL-CVT sigue rechazando `venta_con_entregas_concretadas`. No rompe datos | Programar COM-08b enseguida de COM-08a |
| R154 en el modelo | Entrega → PagoCliente = 0..1 no admite el cobro anulado y el correcto de la misma entrega (MD-136): pasa a 0..\*, con a lo sumo un pago vigente. Anotarlo en pendientes_MD | Al pegar en Drive |
| La fecha del cobro anulado (7a de COM-ANL-CBR) | COM-REG-CBR v0.2 dice «sin fechas retroactivas»; PCU 14 decide que propone la del cobro anulado. D-94 (punto 10) la acota: solo el Gerente, solo las entregas del cobro anulado, una vez. Anotarlo en pendientes_CU (COM-REG-CBR v0.3) | Al pegar en Drive |
| La indemnización por día después de modificar la cláusula | El atraso se calcula con la cláusula del suministrado **al cobrar** (regla del caso de uso); MD-132 fijó el vencimiento, no el monto por día. Si COM-MOD-SUM cambia ese monto, las entregas ya vencidas y sin cobrar usan el nuevo. Confirmar con el Jardín Botánico si debería ser el vigente al concretar | Al validar el lote C8 |
| La alerta «pago en mora» con el invernadero dado de baja | La API no crea alertas de un invernadero inactivo: la entrega queda en mora sin alerta (el aviso al Vendedor y el correo salen igual). El Gerente la ve en «Cobranza» | Si el Jardín Botánico lo pide |
| Fechas del indicador 7 de COM-CNS-EST | El modelo no guarda la fecha de la decisión del cliente ni la del rechazo: D-94 (punto 15) usa `fecha_pendiente_decision`, la concreción de la entrega y la cancelación de la venta. Anotarlo en pendientes_CU | Al pegar en Drive |
| Índice para las estadísticas | Si `test_com_cns_est.py` muestra consultas lentas por `fecha_resolucion_orden`, hace falta un índice en `OrdenTrabajo` (migración de `produccion`): no entra en COM-08c | Al programar COM-08c |
| `ordenes_cancelables` y las cosechas | El código de PRD-01 cruza `TIPOS_DE_PRODUCCION` con `TIPOS_QUE_CANCELA_PRODUCCION` y no lista cosechas; D-67 (1e) esperaba que COM-04a las mostrara. Corrección del C8: COM-02 ya no le pone `exclude` y COM-04a la cambia para que liste todos los de `TIPOS_DE_PRODUCCION`, con la acción «Cancelar» de `comercial` en la fila de una cosecha. A validar | Al validar el lote C8 |
| Pendientes de Drive del lote C8 | pendientes_CU: COM-REG-CBR v0.3 («en mora»; la fecha de 7a; «Lo sigue: COM-ANL-CBR»; COM-VNC-PAG como paso 30); COM-VNC-PAG v0.2 («pago en mora»; la regla 7 definida); COM-CNS-EST (fechas del indicador 7). pendientes_MD: R154 en 0..\* | Al pegar en Drive |

## Abiertos desde INV-03 (22/11/2026)

- **Lo implementado distinto de lo escrito, o que la tarea no decía** (detalle en el «Cierre» del archivo de la tarea):
  - **Reactivar es una página de confirmación**, no un botón directo como en el prototipo: la tabla de variedades la arma `inventario` para `maestros` sin recibir el pedido y no puede llevar un formulario con CSRF. Escribirlo en PROD-MOD-VAR (regla 9) si se acepta.
  - **Fuera de «Permitido fuera de la app»:** `core/tests/urls_prueba_acceso.py` (la misma línea de rutas que `config/urls.py`; sin ella las pruebas de interfaz de `core` no resuelven los enlaces).
  - **Tres pruebas existentes adaptadas:** `maestros/tests/test_cultivos_concurrencia.py` (usa `crear_variedad(cultivo, "Crespa")`) y dos de `maestros/tests/test_extensiones_sectores.py` (`test_ext_semillas_sin_registrantes_son_cero` y `test_ext_uso_de_cultivo_sin_registrantes_no_hay_invernaderos`, que ahora aíslan el punto con `mock.patch.object`): con `inventario` instalado esos puntos ya tienen registrante. La fábrica `crear_variedad` también cambió (valores por defecto válidos).
  - **`gestion_de` y `acciones_de`** en `inventario/servicios/variedades.py`: la regla de `puede_gestionar` y `acciones_permitidas` para toda la tabla en una consulta; las dos de antes delegan en ellas.
  - **`habilitar` de INV-02** acepta una semilla activa que llega con `?insumo=`; la lista general sigue sin semillas.
  - **El comando de pruebas de migración** de la tarea no incluía `core` (la migración `core/0016` también se prueba): corregir la tarea.
- **Hueco conocido:** la precondición f de PROD-BAJ-VAR (contratos) no se verifica hasta que `comercial` registre `contratos_abiertos`.
- **`reactivar_variedad` no reevalúa las alertas de stock** de las existencias que quedaron activas (la baja sí). Decidir en PRD-01.
- **`habilitar_insumo` (INV-02) no mira la variedad de una semilla:** la ventana entre habilitar y dar de baja la variedad la cubre la baja con `cambio_simultaneo` (no reintenta, para no bloquear fuera de orden).
- **Variedad sin Agrónomo:** si todos los invernaderos que usan una variedad están sin Agrónomo, nadie la gestiona hasta que el Gerente asigne uno.
- **`renombrar_semillas(actor, cultivo, nombre_anterior)`:** `nombre_anterior` no se usa (el nombre de la semilla se arma con el cultivo y la variedad). Sacarlo de la firma de `docs/api/extensiones_de_maestros.md` o usarlo.
- **Prueba de espacios al borde:** documenta la frontera entre la base (no recorta) y el servicio (recorta antes de comparar).
- **Cruce de concurrencia agregado:** alta de una variedad contra el renombre de su cultivo (la tarea no lo pedía).
- **Sin verificar:** HTMX en vivo y el aspecto de las pantallas en un navegador real (no hay pruebas de navegador, por regla).

## Abiertos desde H2 (20/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Registrar H2 en el modelo de Drive | Ítem nuevo de pendientes_MD: `OrdenTrabajo.motivoCancelacion` (texto, obligatorio al cancelar, 1 a 300) y `fechaResolucionOrden` también como fecha de cancelación; ya aplicado en `docs/modelo/produccion.md` (Diferencias n.º 17). Pegalo vos: no tengo escritura en Drive | Antes de cerrar la ronda del modelo |
| Aviso al Vendedor con el motivo (PROD-CNL-ORD, postcondición l) | Fuera de la ronda (D-45). La versión 0.1 del CU no menciona el motivo en ese aviso; ajustarla en Drive (pendientes_CU). Se programa con Cosecha | Cuando exista Cosecha |

## Abiertos desde la planificación de «Comercial 1» (21/11/2026, lotes C0 y C1)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Dónde viven los servicios de cosecha y cámara (P5 de TEC) | D-37 ya ubica los modelos (`Cosecha` y `StockCosechado` en `produccion`, `ReservaStock` en `comercial`). Falta registrar que los casos de uso que tocan reservas viven en `comercial` (regla A3) y resolver que D-56 ubica el paso 20 («vencer partidas en cámara») en `produccion`, aunque PROD-VNC-CAM toca reservas. Detalle en `docs/tareas/ronda_comercial_1.md`, sección 8 | ~~Lote C2~~ **Resuelto en el lote C2: D-59** (vigente) |
| Enlace de una alerta en la campana | `items_de_campana` (`maestros`) lleva toda alerta a la ficha del invernadero, y `Origen` (C5) solo tiene cuatro valores. Comercial necesita llevar a su pantalla y orígenes nuevos (MD-122, MD-133, MD-134). Coordinar con el IoT y con MAE-02c | ~~Lote C3~~ **Resuelto en el lote C3: D-62** (vigente) |
| Cambio de Vendedor de un invernadero | Al asignar otro Vendedor, sus contratos vigentes o abiertos pasan al nuevo (regla 3 de 8.22). Si el saliente conserva otros invernaderos, pendientes_CU (caso 22, MD-46) dice que el Gerente decide contrato por contrato; un suministro puede tomar stock de varios invernaderos del Vendedor. Falta decidir si se hace en la ventana de PROD-MOD-INV (`maestros`, por punto de extensión) o con un caso de uso propio | ~~Lote C2~~ **Resuelto en el lote C2: D-60** (vigente; cambia la regla 8 de 8.21, a corregir en pendientes_MD) |
| PCU, sección 5, en Drive | Dice que antes de comercial va una ronda de contabilidad; D-57 (con PCU 16) dice que no. Corregirlo en pendientes_CU (lo pega el estudiante) | Al pegar PCU |
| Vehículo de un Transportista dado de baja | Ningún caso de uso dice qué pasa con el vehículo cuando se da de baja la cuenta de su transportista: COM-01 lo deja asignado (se ve con la marca «Inactivo» y se puede quitar en COM-MOD-VEH), y Planificar Entrega no lo toma porque el transportista está inactivo. Decidir si la baja de la cuenta debe liberar el vehículo | Lote C5 (COM-05), con la baja de un Transportista |
| Ícono `truck` y MAE-05 | El bloque «Logística» del prototipo de MAE-05 usa el ícono `truck`, que no está en `core/templatetags/iconos.py`, y MAE-05 no tiene ese archivo en «Permitido fuera de la app». COM-01 lo agrega si falta | Al programar MAE-05 |
| Ficha del vehículo | El prototipo no la tiene; COM-01 la arma con el estilo de la ficha del cliente (COM-CNS-VEH, regla 2) | Revisión a mano de COM-01 |

## Abiertos desde el lote C2 de «Comercial 1» (21/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Correo a quien no tiene cuenta | `core.correo.enviar_correo` (USR-10) espera una cuenta (`.pk`, `.email`). El comprobante de COM-REG-CVT va a un cliente, que no tiene cuenta: COM-02 le pasa un `Destinatario` de `comercial`, y el registro de una falla dice «cuenta N» con el id del cliente. Si molesta, una función hermana en `core` que reciba solo la dirección (decisión aparte) | Cuando lo usen COM-03 o COM-04 (enlaces al cliente) |
| Comprobante sin reintento automático | La extensión 16a de COM-REG-CVT pide reintentar; no hay cola de envíos. COM-02 guarda el estado y ofrece «Reenviar comprobante» a mano | Si se agrega una cola (fuera del alcance de USR-10) |
| Notificaciones de PROD-ASG-STK | El caso de uso las envía después de confirmar y las reintenta (paso 10, 10a); en el código van dentro de la transacción (D-42), sin reintento. Ya es la regla de todo el sistema («Notificaciones», lote 4) | Al pegar PCU: anotarlo en el caso de uso |
| Alerta de PROD-ASG-STK 5a | El caso de uso pide una alerta propia en una transacción aparte. Se usa la `sin_capataz` de `maestros` (D-41), que ya existe mientras falte el Capataz. Corregir el caso de uso en su próxima versión | Al pegar PCU |
| Recálculo por concurrencia (8a de PROD-ASG-STK) | Con los bloqueos de `docs/patrones/stock_maduro.md` no hace falta: el cálculo ya se hace sobre el stock vigente. Quitar la extensión en la próxima versión del caso de uso | Al pegar PCU |
| Una venta de varios invernaderos | Tema abierto de PROD-ASG-STK: con la regla 7 de 8.6 un detalle puede tomar stock de varios invernaderos (una cosecha y una entrega por cada uno). Observarlo en el uso real | Revisión a mano de COM-02 y COM-05 |

## Abiertos desde el lote C3 de «Comercial 1» (21/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Meses del ajuste de un detalle **agregado** al modificar | COM-MOD-SUM cuenta los meses «desde la primera entrega del detalle nuevo»; no distingue el sucesor del agregado con 5b. Se aplica a los dos (`fecha_base_ajuste`, `suministro.md`) | ~~Validación del lote C3~~ **Validado por el estudiante el 21/11/2026** |
| Detalle que se queda sin períodos al acortar la duración | Ningún caso de uso lo dice: COM-03 lo pasa a «finalizado» con su último período como fecha de fin | ~~Validación del lote C3; anotarlo en COM-MOD-SUM al pegar PCU~~ **Validado por el estudiante el 21/11/2026** |
| Contrato con todo finalizado | COM-MOD-SUM no dice qué pasa con el estado del contrato al terminar todos sus detalles: COM-03 lo finaliza si no queda ningún período pendiente; si queda, lo hace COM-06 al concretar el último (disparador «Cuando exista Entrega», punto 5) | Al pegar PCU |
| Detalle finalizado con un período de la ventana que pierde su reserva | Si se cancela la cosecha de un período de un detalle ya finalizado (terminado por COM-MOD-SUM), la pre-reserva no lo vuelve a tomar (solo toma detalles vigentes, PROD-PRR-SUM). Lo trata PROD-CNL-ORD (qué hace con lo no cubierto) | ~~COM-04~~ **Propuesta en D-64, punto 8 (lote C4):** el período con fecha ≤ `fecha_fin_detalle` de un detalle finalizado todavía se debe; la pre-reserva y la cámara lo vuelven a tomar. **Validado el 21/11/2026** |
| Numeración de COM-MOD-SUM | En el documento de Drive los pasos 7 a 12 se numeran otra vez desde 1; las extensiones los citan como 7 a 12. La copia del repo los numera 7 a 12 | Al pegar PCU (corregir el documento) |
| Reintentos de correo y notificaciones en suministros | COM-PCT-SUM 15a, COM-MOD-SUM 11a y PROD-PRR-SUM 5a piden reintentar: no hay cola. Se resuelve igual que en COM-02 («Reenviar comprobante» a mano; notificaciones dentro de la transacción) | Si se agrega una cola |
| Invernadero de la alerta de período | D-63, punto 3: el de la primera reserva del período o el activo de menor id del Vendedor. Ver en el uso real si conviene otra regla | Revisión a mano de COM-03 |
| Calendario en el comprobante | La variación 15a pide «calendario de entregas»; un contrato largo puede tener cientos de fechas. El comprobante muestra primera y última fecha, cantidad de entregas y tramos de precio | ~~Validación del lote C3~~ **Validado por el estudiante el 21/11/2026** |
| COM-RSC-SUM y COM-ANL-RSC en Drive | Los dos casos de uso nuevos están solo en el repo (`suministro.md`). Pasarlos a Drive con la tabla de casos de uso, la propuesta MD-140 y el glosario (texto en el LEEME del lote) | Al pegar PCU y pendientes_MD |
| Plazo de la rescisión | Se conservan los períodos de la ventana de pre-reserva (14 días con la configuración actual). Confirmar con el Jardín Botánico (tema abierto de COM-RSC-SUM) | Revisión a mano de COM-03 |

## Abiertos desde el lote C4 de «Comercial 1» (21/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| Detalle confirmado que pierde producto de cámara | ~~Ningún caso de uso lo trata~~ **Decidido por el estudiante el 21/11/2026 (opción b, D-64 punto 13):** se intenta cubrir y, si no alcanza, el detalle vuelve a pendiente y el cliente decide de nuevo | Al pegar PCU (PROD-REG-MRM y PROD-VNC-CAM) |
| Orden de la bandeja del Capataz | PROD-CNC-CSC (paso 2) ordena por prioridad y después por fecha; la bandeja de PRD-01, por fecha, prioridad e id, en grupos «Vencidas», «Hoy», «Próximas». COM-04 usa la de la bandeja (una sola para todas las órdenes) | **Validado por el estudiante el 21/11/2026**; falta pegarlo en Drive |
| Numeración de PROD-MOD-CSC y PROD-VNC-CAM en Drive | Los pasos que siguen a la repetición se numeran otra vez desde 1; las extensiones los citan con la numeración seguida. Las copias del repo los numeran seguido | **Validado por el estudiante el 21/11/2026**; falta pegarlo en Drive |
| Asignación de cámara «en segundo plano» | PROD-ASG-CAM pide segundo plano y reintento; no hay cola: corre con `on_commit` en el mismo pedido y la recupera el paso diario 25 (D-64 punto 9) | Si se agrega una cola de tareas |
| Cosechas vencidas sin concretar | Los dos casos de uso de la cosecha lo dejan abierto; la bandeja y la lista las muestran en «Vencidas», sin aviso automático | Con el Jardín Botánico |
| Merma en cámara: ¿alerta o notificación al Agrónomo? | La extensión 10c de PROD-REG-MRM dice «notifica»; la regla 2 de 8.9, «alerta». COM-04 usa la alerta `comercial_merma_camara_reservada` (D-64 punto 10) | **Validado por el estudiante el 21/11/2026**; falta pegarlo en Drive |
| Correo del enlace que no sale | **Validado el 21/11/2026.** D-65 punto 6: el Vendedor puede decidir por el cliente si el envío falla (suma a la extensión 1a de COM-DCD-FLT). No hay reenvío | Al pegar PCU (COM-DCD-FLT); el reenvío, mejora futura |
| Partidas cerradas en la pestaña «Cámara» | Se muestran las agotadas y vencidas de los últimos 30 días (para que la tabla no crezca); el caso de uso no lo fija | Revisión a mano de COM-04 |

## Abiertos desde el lote C5a de «Comercial 1» (22/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| ~~D-66 y la tercera enmienda de D-62~~ | ~~Las propuso Claude en el lote C5a. Las más discutibles: el corte de COM-05 (punto 1), el agrupamiento de una compra-venta (punto 7) y la restricción de `ReservaInsumo` (punto 8); en D-62, que la campana pase por `alertas:ir` solo con el enlace de una app (punto 3)~~ | **Validadas el 22/11/2026** |
| ~~Riesgo con PRD-01: las entregas son órdenes~~ | ~~COM-05a supone que la lista de órdenes, las cancelables y la bandeja de PRD-01 excluyen `tipo = entrega`, que `cancelar_orden` la rechaza, que `cancelar_orden_incluida` acepta una orden sin sectores ni Capataz y que el registrante de reservas de insumo cuenta todas las órdenes~~ | **Resuelto en la documentación (lote C5b, D-67 punto 1):** los seis puntos están en PRD-01 con sus pruebas; COM-05a1 y COM-05a2 ya no lo completan. Se tacha del todo cuando PRD-01 se mergee |
| La campana y `alertas:ir` | MAE-02c (PR #47) dejó la campana yendo al detalle. MAE-02d suma `alertas:ir` solo para las alertas con enlace de una app (D-62, tercera enmienda, punto 3) | Al programar MAE-02d |
| Acceso al envasado «desde la notificación» | PROD-PNF-ENV (1a y un requisito especial) pide un acceso directo desde la notificación de COM-PNF-ENT; las notificaciones no tienen enlace (D-42). El texto dice dónde está | pendientes_CU (PROD-PNF-ENV); o ampliar `core.notificaciones` con un enlace (cambio de D-42) |
| Entre COM-05a y COM-05b (desde el C5b: entre COM-05a1 y COM-05b) | Mergeada COM-05a y no COM-05b, un transportista con entregas no se puede quitar ni trasladar (`transportista_con_entregas`) y todavía no hay «Asignar transportista»; tampoco se concretan (COM-06). No rompe nada: es un estado de paso | Programar COM-05b enseguida de COM-05a |
| ~~Exceso de envases al concretar~~ | ~~La regla 21 de 8.8 admite usar más envases que los reservados; PRD-01 tiene restricciones que lo impiden~~ | **Cerrado en el lote C6 (D-68, punto 2, opción A, 22/11/2026):** las restricciones no cambian; el exceso va en el consumo del envase |
| ~~Números de decisión de «Comercial 1»~~ | ~~Quedan D-67 a D-69 para los lotes C5b a C8~~ ~~El C5b usó D-67: quedan D-68 y D-69 para C6 a C8~~ ~~El C6 usó D-68: queda D-69 para C7 y C8~~ | **Cerrado el 22/11/2026:** el C7 usó D-69; ~~el C8 empieza en D-80~~ el C8 toma la siguiente libre al escribirse: **D-94** (23/11/2026; `docs/decisiones/README.md`, «Numeración») |
| ~~D-66, punto 3: los datos copiados en `Entrega`~~ | `contrato`, `modalidad_entrega` y `direccion_destino` se guardan en la entrega aunque se deducen de sus detalles. Preocupación del estudiante: que no coincidan. Respuesta del 22/11/2026: las tres son claves que apuntan a las mismas filas (no copian valores), se escriben una sola vez al crear la entrega y su fuente no cambia (una compra-venta no se modifica; COM-MOD-SUM no cambia la dirección de un detalle: crea un sucesor con la misma, MD-131). Propuesta de refuerzo: una sola función las escribe, el servicio rechaza un detalle de otro contrato, modalidad o dirección, y `verificar_invariantes_de_entregas` lo revisa en cada prueba que escribe. La otra opción es no guardarlas y calcularlas desde los detalles | **Cerrado el 22/11/2026: opción A** (guardarlas con los refuerzos; D-66, punto 3) |
| Pendientes de Drive del lote C5a | pendientes_CU: COM-PNF-ENT (D-66 punto 7; la postcondición n de PCU 8 ya está decidida) y PROD-PNF-ENV (1a). «CU extendidos»: la tercera enmienda de D-62 no toca casos de uso. pendientes_MD: nada nuevo (lo del modelo es del código, `docs/modelo/comercial.md`, «Pendientes de MD») | Al pegar en Drive |

## Abiertos desde el lote C5b de «Comercial 1» (22/11/2026)

| Tema | Qué falta | Cuándo |
|---|---|---|
| ~~D-67~~ | ~~La propuso Claude en el lote C5b. Las más discutibles: crear en PRD-01 los cinco valores del tipo y probar con órdenes sueltas (punto 1d); `cancelar_orden` también rechaza la cosecha (punto 1b); los nombres COM-05a1 y COM-05a2 (punto 2); cancelar los detalles confirmados sin entregar (punto 4)~~ | **Validada el 22/11/2026** |
| ~~La cosecha en `TIPOS_DE_PRODUCCION` desde PRD-01~~ | ~~Lo pidió así el estudiante (lista final con las tres), pero COM-02 oculta las cosechas hasta COM-04a: queda un `exclude` temporal en COM-02 (D-67, punto 1e). La otra opción es que PRD-01 deje la constante con siembra y transición y que COM-04a sume la cosecha (sin `exclude`)~~ | **Cerrado el 22/11/2026:** queda como está (la constante con las tres y el `exclude` temporal de COM-02), por el traspaso del Capataz (D-67, alternativas) |
| Estados de paso entre las partes | Entre COM-03a y COM-03b, un suministro reserva solo los períodos de la ventana (no hay pre-reserva diaria). Entre COM-04a y COM-04b, lo que entra a la cámara no se asigna solo (el paso 25 lo recupera después). Entre COM-04a y COM-04c, una venta «pendiente de decisión del cliente» no tiene enlace ni pantalla para decidir. Entre COM-05a1 y COM-05a2, las entregas no tienen envasado ni aparecen en el panel ni en las fichas. Ninguno rompe datos | Programar cada parte enseguida de la anterior |
| COM-CNL-CVT: los detalles «confirmados» | El caso de uso dice que no se cancelan porque están «ya entregados»; en el sistema un detalle se confirma también al aceptar un faltante, antes de entregarse. Se cancelan los confirmados sin línea en una entrega concretada (D-67, punto 4) | **Validado el 22/11/2026.** Falta pegarlo en pendientes_CU (COM-CNL-CVT, regla «Detalles afectados») |
| COM-CNL-CVT: la descripción con «otro» | El caso de uso la deja opcional siempre; con «otro» sin descripción el motivo no dice nada. Sugerencia: obligatoria con «otro», como en la rescisión (COM-RSC-SUM) | pendientes_CU (decide el estudiante) |
| COM-CNL-CVT con entregas concretadas | La extensión 6a cobra lo entregado con `PagoCliente` (desde el lote C6 lo crea COM-06a, D-68 punto 4; el cobro de 6a sigue en COM-08); antes de COM-06 no puede darse. COM-05b rechaza `venta_con_entregas_concretadas` y COM-06 y COM-08 lo completan (`docs/disparadores.md`, «Cuando exista Entrega», punto 9). Entre COM-06 y COM-08 una venta de varios invernaderos con una entrega concretada no se puede cancelar | Al escribir C6 y C8 |
| ~~«La cancelación de entregas en PROD-CNL-ORD» del pedido del lote C5b~~ | ~~La «Cancelación de una entrega» ya la trajo el lote C5a (COM-05a1). Se interpretó como la inclusión desde COM-CNL-CVT (cosechas y entregas de la venta, con el aviso al cliente por el comprobante): sección nueva de `cancelar_orden.md`~~ | **Cerrado el 22/11/2026:** el estudiante confirma que está cubierto (sección «la compra-venta cancelada» de `cancelar_orden.md`) |
| Pendientes de Drive del lote C5b | pendientes_CU: COM-CNL-CVT (los dos de arriba); COM-ASG-TRP: la regla de «Transportista en el invernadero» ya está aplicada en el extracto (igual a 3a). pendientes_MD: nada nuevo (MD-130 ya está; las restricciones son del código) | Al pegar en Drive |

## Abiertos desde PRD-01 (22/11/2026)

- **Lo implementado distinto de lo escrito, o que la tarea no decía** (detalle en el «Cierre» de `docs/tareas/produccion/PRD-01-siembra-ordenes-y-bandeja.md`):
  - **Semillas en «Habilitar insumo» (desvío de INV-02, corregido en PRD-01 con permiso explícito del estudiante, 22/11/2026):** INV-02 sacó las semillas de la lista de «Habilitar insumo» y del botón del Catálogo (solo se habilitaban desde «Qué sigue» de la variedad), contra la regla 2 de CMP-HAB-IIN y la regla 3 de CMP-CNS-INS («incluidas las semillas»). Un segundo Agrónomo no podía habilitar la semilla de una variedad ya creada y la extensión 8b de PROD-PNF-SMB quedaba sin salida. Ahora la lista de `inventario:habilitar` y el botón del Catálogo incluyen las semillas activas, y PRD-01 enlaza a `inventario:habilitar?insumo=<semilla>&invernadero=<invernadero>` (`ErrorDeProduccion.datos`). Tocó `inventario/views_existencias.py`, `inventario/templates/inventario/catalogo/lista.html` y tres pruebas (dos de INV-02/INV-03 cambiadas y cinco nuevas). Falta anotarlo en el «Cierre» de INV-02 y en el de INV-03 (el parche de `?insumo=` ya no hace falta).
  - **`OrdenTrabajo.tipo_orden`, no `tipo`** (D-81): `OrigenDocumento` ya tiene `tipo` y Django no admite el mismo nombre en la hija. Corregir `docs/modelo/produccion.md`, `docs/api/produccion.md` y las tareas COM-02, COM-05a1/a2 e IOT-07 (el valor, `OrdenTrabajo.Tipo`, y las constantes no cambian).
  - **Una línea de `contabilidad/models.py`** (archivo mergeado, con permiso): `OrigenDocumento.save()` valida con `OrigenDocumento.Tipo.values` y no con `self.Tipo`, que `OrdenTrabajo.Tipo` tapaba. Sin migración.
  - **`traspasar` devuelve las instancias tocadas** (D-81): actualizar `docs/api/extensiones_de_maestros.md` (contrato) y el último párrafo del «Traspaso del Técnico» de `docs/casos_de_uso/iot/mantenimiento_automatico.md`.
  - **Cuatro códigos de error que no estaban en `docs/api/produccion.md`:** `insumo_no_elegible`, `prioridad_invalida`, `descripcion_larga` y `variedad_inactiva`. Agregarlos a la sección 1.
  - **Textos de los impedimentos y avisos** (baja de sector, de invernadero y de variedad; avisos de cambio de tipo): los casos de uso no traen el texto literal; son de PRD-01, en voseo.
  - **`ordenes_cancelables` filtra por `TIPOS_DE_PRODUCCION` y por `TIPOS_QUE_CANCELA_PRODUCCION`:** no lista cosechas, que se cancelan por `comercial.cancelar_cosecha` (D-64). `docs/api/produccion.md` (secciones 2 y 9) dice que lista los de `TIPOS_DE_PRODUCCION`: corregir o decidir en COM-04a.
  - **Traspaso del Capataz:** pasan al entrante todas las órdenes «a realizar» del invernadero que no sean suyas (no solo las del saliente), para que también las reciba quien se asigna después de un rol vacío (MD-60).
  - **17b de PROD-CNC-SMB:** el total de los lotes elegidos no puede superar lo consumido y lo que no cubren sale del «faltante sin lote» (el caso de uso dice a la vez «igual» y «lo que no cubren sale del faltante»).
  - **Siete pruebas existentes adaptadas** porque ahora `produccion` registra sus puntos de extensión: dos de `inventario/tests/test_stock_lectura.py` y las cinco de `ExtensionesDeSectoresTests` en `maestros/tests/test_extensiones_sectores.py`. Solo se aísla la lista de registrantes; no cambia lo que afirman.
  - **Fechas de etapas posteriores a la primera:** `None` hasta PRD-02 (ver `docs/disparadores.md`, «Cuando exista TransicionEtapa»).
- **Pantallas: lo que se corrigió del prototipo** (D-61): el Capataz, sin menú lateral, llega a «Mis órdenes» desde el Inicio y su enlace «Ver todas»; el Gerente ve la lista y el detalle en solo lectura; «Cancelar orden» suma el motivo y el resumen; «Concretar siembra» permite elegir los lotes de insumo (17b). **Revisar con el estudiante** si la bandeja del Capataz necesita una entrada de menú propia en el marco de celular.
- **Panel «Ritmo sostenible»** (`ritmo`, `ritmoPanel` del prototipo): recortado (paso 9). No está en ningún caso de uso. Decidir si se retoma o se descarta.
- **Pruebas que la tarea pedía y no están:** «precio de referencia vacío» (`InsumoInvernadero.referencia_precio` es obligatorio y mayor que cero desde INV-01; `docs/patrones/costo_del_lote.md` dice que no lo es: corregirlo). «Cancelar contra planificar otra transición» pasa a PRD-02. «Concretar contra cancelar» quedó en `test_cancelar_concurrencia.py`.
- **Hueco en `inventario`:** `registrar_salida_por_consumo` solo manda lo que falta al «faltante sin lote» si recibe algún lote de la existencia; con una existencia sin ningún lote no se puede registrar el consumo. No pasa en el flujo normal (reservar exige haber tenido stock y los lotes no se borran). Decidir si `inventario` suma un parámetro `resto`.
- **Sigue abierto de INV-03:** si `reactivar_variedad` debe reevaluar las alertas de las existencias activas (`docs/disparadores.md`, «Cuando exista PRD-01», punto 2).


## Abiertos desde PRD-02 (22/11/2026)

- **Lo implementado distinto de lo escrito, o que la tarea no decía** (detalle en el «Cierre» de `docs/tareas/produccion/PRD-02-transicion-de-etapa.md`):
  - **`TransicionEtapa.bitacora_de_transicion`, no `bitacora`** (D-83, aprobada el 22/11/2026): `OrigenDocumento` ya tiene el accesorio `bitacora` hacia su hija `Bitacora` y Django lo rechaza (`models.E006`). Corregir `docs/modelo/produccion.md` (ficha `TransicionEtapa`, R080) y `docs/api/produccion.md`.
  - **Tres códigos de error que no estaban en `docs/api/produccion.md`** (D-83): `causa_invalida` (campo `causa`), `descripcion_larga` (campo `descripcion`, hasta 300 caracteres en la merma) y `lote_sin_plantas` (extensión 4a de PROD-CNC-TRN). Agregarlos a la sección 1.
  - **`lotes_trasladables(actor)` devuelve todos los lotes del Agrónomo con su `motivo`** (`ultima_etapa`, `transicion_a_realizar` o `sin_capataz`), no solo los trasladables, para que la pantalla los muestre deshabilitados con su explicación (extensiones 3a y 3b). `docs/api/produccion.md`, sección 2, dice «los lotes trasladables».
  - **Datos que la persona vio:** `DatosDeTransicion` suma `cantidad` y `etapa_actual_id` y `DatosDeConcrecionDeTransicion`, `cantidad`; si cambiaron al confirmar, `cambio_simultaneo` con el dato nuevo (13a, 13b y 13c), comparados después de bloquear el lote. Documentarlos en `docs/api/produccion.md`.
  - **Tipos de alerta de la merma:** la documentación no daba nombre ni severidad. `produccion_merma_umbral` = «Merma sobre el umbral» (crítica) y `produccion_plantas_comprometidas` = «Plantas comprometidas por una transición» (advertencia), los del prototipo. Las descripciones nunca pasan de 200 caracteres (se acorta el nombre de la variedad con «…»).
  - **Umbral de merma:** se alerta si la merma acumulada **supera** el porcentaje y el lote **no tuvo** una alerta de umbral (decisión del estudiante, 22/11/2026), no «al cruzarlo por primera vez»: así un lote que ya estaba por encima la recibe aunque el Gerente haya bajado el porcentaje. `merma.md` (PRD-03) dice «al cruzar»: alinearlo.
  - **«Con el porcentaje en 0»** (prueba pedida por la tarea): la configuración admite de 1 a 100; se probó con la merma acumulada en 0 % (solo descarte por selección) y con el umbral en 1 %.
  - **`Bitacora.descripcion_evento` de la merma** = «Merma de 12 plantas por plaga.» más la descripción del Capataz (hasta 300 caracteres).
  - **Restricciones de la base que cumplen los servicios:** `cant_transferido` y `fecha_transicion` se cargan juntas y la cantidad es positiva en la base; que sean nulas si y solo si la orden no está concretada (el estado vive en el padre) y que `Merma.tipo_evento` sea «merma» los garantizan los servicios.
  - **Planificar:** «otra transición a realizar» se mira con el lote bloqueado (no en la pasada previa), para que planificar otra no se rechace de más mientras la cancelación de la anterior está por confirmarse.
  - **Auditoría:** `cancelacion_orden` no lleva el lote entre los afectados (no cambia); `concrecion_transicion` solo registra `cantidad_actual` y `costo_acumulado` del lote si hubo merma (D-36 rechaza un cambio sin diferencia).
  - **Notificación de la concreción:** va al Agrónomo a cargo del invernadero (el CU dice «responsable del invernadero»), aunque la haya planificado InfoPonia; sin Agrónomo activo no se avisa a nadie.
  - **`resumen_de_cancelacion`** suma `lote`, `etapa_origen` y `etapa_destino` (nombres; `None` en una siembra): `docs/api/produccion.md`, sección 2.
  - **Pruebas:** `python manage.py test produccion --keepdb --tag migracion` no corre ninguna (la tarea no tiene migraciones de datos). La condición 2 de plantas comprometidas queda probada solo por función hasta PRD-03.
- **Pantallas: lo que se corrigió del prototipo** (D-61): se sacó el recálculo al escribir (`trCalc`, `ctCalc`) a favor de «Continuar», «Actualizar fechas», «Ver resumen» y «Confirmar»; la descripción de la causa «Otra» es opcional (como en el CU); la causa aparece al pedir el resumen cuando faltan plantas. **«Repartir por mí» (`tr-auto`) no se implementó:** repartir automáticamente al planificar necesita una regla que ningún caso de uso define; si se quiere, hay que documentarla (L9).

## Abiertos desde IOT-03 (23/11/2026)

- **Lo implementado distinto de lo escrito, o que la tarea no decía** (detalle en el «Cierre» de `docs/tareas/iot/IOT-03-api-del-nodo-lecturas.md`):
  - **Auditoría:** manda D-36 (`datos` y `cambios` arriba, no `cambios` dentro de `datos`); un mensaje que solo resolvió «nodo sin comunicación» se audita con `mensaje: "comunicacion"`, que el caso de uso no prevé. `RegistroAuditoria.ETIQUETAS` no se amplió: la pantalla de Auditoría muestra las claves de `datos` y `cambios` tal cual.
  - **«Lectura inválida»:** el valor lleva la unidad del sensor (`999 °C`) y los límites van sin unidad (`-10 a 60`): el extracto no lo precisa.
  - **Respuesta del anuncio:** los actuadores salen ordenados por identificador (sin distinguir mayúsculas), como en el ejemplo; `docs/api/nodo/mensajes.md`, sección 4, no fija el orden.
  - **Contador de pedidos** (D-70, punto 5): vive en la caché por proceso de gunicorn; con más de un proceso, cada uno cuenta aparte. Anotarlo si cambia el despliegue.
  - **Lista de Hardware:** hace 21 consultas con 3 equipos y 21 con 8 (no crecen con la cantidad); la prueba compara las dos cantidades y no fija el 21, que incluye las del marco de la página.
  - **Cargador de datos de verificación:** `temp-vieja` (sensor dado de baja) no se carga hasta que IOT-06 traiga `baja_hardware`; el motivo `equipo_dado_de_baja` no se prueba a mano.


## Abiertos desde PRD-03 (23/11/2026)

- **Lo implementado distinto de lo escrito, o que la tarea no decía** (detalle en el «Cierre» de `docs/tareas/produccion/PRD-03-eventos-del-lote-merma-aplicacion-bitacora.md`):
  - **`registrar_aplicacion` devuelve `ResultadoDeAplicacion(aplicacion, lineas)`** y no `AplicacionInsumos` (`docs/api/produccion.md`, sección 6): así el Agrónomo ve montos, reparto y faltante (paso 13) y el Capataz recibe `None`. Se aprobó con el estudiante.
  - **Agregados no previstos:** `produccion/servicios/alcance.py` (quién registra y dónde, compartido por los tres casos de uso), `aplicaciones.plantas_del_alcance` (lo que la pantalla guarda como `plantas_vistas`, extensión 12a) y `lotes` y `sectores` en `PaginaDeBitacora` (opciones de los filtros).
  - **Extensión 4b:** no hay código `sin_lotes_activos`: `lotes_con_merma_posible` devuelve la lista vacía y la pantalla informa y deshabilita el formulario.
  - **Códigos de error nuevos** (no estaban en `docs/api/produccion.md`, sección 1): ver «Contrato de los servicios» del Cierre; incluye `descripcion_obligatoria`, `sin_sectores`, `sin_insumos`, `insumo_no_aplicable`, `insumo_repetido`, `reparto_supera_lote`, `distribucion_incompleta`, `lote_no_activo` y `filtro_invalido`.
  - **Extensión 12a:** un insumo que ya no es aplicable da `cambio_simultaneo` solo si la línea trae `lotes_vistos` (lo que la persona vio); sin eso, `insumo_no_aplicable`. La pantalla guarda lo que mostró el resumen y «Ver resumen» no lo compara.
  - **Evento sin etapa:** un «otro evento» no guarda `etapa` aunque lleve lote (el caso de uso no la pide); `PROD-CNS-BIT` no la muestra.
  - **Un Agrónomo consulta también los invernaderos dados de baja que tenía a su cargo** (regla 2 de PROD-CNS-BIT: la baja conserva el historial); el caso de uso solo lo dice para el Gerente («cualquiera registrado»).
  - **`siembras.py` (PRD-01):** se corrigió el orden de bloqueos (`Insumo` antes que `InsumoInvernadero`, `docs/patrones/stock.md`, sección 5). Hasta entonces una siembra y una aplicación sobre el mismo insumo podían trabarse entre sí.
  - **`core/models.py`:** se agregaron etiquetas de auditoría que todavía no se usan todas (`evento`, `alcance`, `monto_consumo`, `cantidad_consumida`, `faltante_sin_lote`) y `core/tests/urls_prueba_acceso.py` incluye `produccion.urls` por la entrada «Bitácora» del menú del Gerente.
  - **Merma contra poner el sector fuera de servicio:** sin prueba hasta PRD-04 (disparador nuevo).
  - **Cargador de datos de verificación:** la primera corrida habilitó en «Verificación Producción» un insumo «abono» que ya existía en la base del estudiante (sin stock); no se borró. Los insumos de prueba llevan «(prueba)» en el nombre para no chocar con datos propios.
  - **Montos en pantalla** con coma decimal («$160,00»), como el resto del sistema; los de la auditoría, como texto con punto.


  ## Abiertos desde PRD-04 (23/11/2026)

- **Agujeros libres de un destino y las órdenes que se cancelan:** la tarea («sin contar los de las órdenes que se cancelan») y el extracto («no se cuentan como libres») admiten dos lecturas. PRD-04 tomó la conservadora: lo que comprometen esas órdenes NO se cuenta como libre, para no depender del orden y no pasarse de la capacidad. Falta confirmarlo y dejar una sola redacción.
- **Motivo de las órdenes canceladas:** «Sector fuera de servicio: <sector>. <motivo>» (tarea y `cancelar_orden.md`); el extracto de PROD-PNR-FDS dice «Sector <nombre> fuera de servicio: <motivo>». Corregir el extracto.
- **Inicio del Agrónomo:** sin el filtro por invernadero del prototipo, y «Insumos por vencer» cuenta solo las alertas activas `inv_insumo_por_vencer` (el prototipo suma también los vencidos). Disparador nuevo en `docs/disparadores.md`.
- **Auditoría de la vuelta a servicio:** `modificacion_sector` (de `maestros`) no incluye el registro «Fuera de servicio» entre sus afectados; incluirlo exige tocar `maestros`.
- **`maestros`, fuera de lo listado:** se tocaron `sectores/_tarjeta.html` y `sectores/_ventana_baja.html` (entradas pedidas por la tarea) con permiso del estudiante. El punto `registrar_efecto_de_baja_de_sector` ya existía desde MAE-03: corregir el texto de la tarea y de `extensiones_de_maestros.md` («lote 5») que lo presentan como nuevo.
- **Pruebas ajustadas** sin debilitar reglas: `test_modelos_aplicacion` (tipos de bitácora), `test_extensiones_sectores` (lista vacía a propósito), `test_registrantes_de_core` (solo la sección del Capataz) y `test_prod_cns_bit` (lista del filtro).
- **`docs/api/produccion.md`:** sumar el código `sector_no_activo`, `DatosDeFueraDeServicio` y los registrantes `efecto_de_vuelta_a_servicio`, `efecto_de_baja_de_sector`, `efecto_de_baja_del_invernadero` y `seccion_de_inicio_del_agronomo`.
- **Fecha mínima:** sin registro de auditoría de alta o reactivación (datos cargados a mano) ese componente no cuenta.
- **Descripción de la `Reubicacion`:** lleva las plantas por destino («… a Germinación 2 (25) y Germinación 3 (10).»).
- **Cargador de verificación:** el sector ya fuera de servicio es de Maduración (el ciclo de la variedad de prueba exige un sector de cada etapa) y no se vuelve a sacar de servicio uno que ya se activó.

## Abiertos desde la documentación de Contabilidad, Compras y Estadísticas (23/11/2026)

- **Numeración de decisiones.** Contabilidad, Compras y Estadísticas usan D-84 a D-93 (aprobadas); la del lote C8 de Comercial, escrita como
  D-84, pasó a **D-94** en el mismo paquete (regla de `docs/decisiones/README.md`).
- **Indicadores de estadísticas (D-93).** Son provisorios: se revisan después de la entrevista a un productor (H26).

## Abiertos desde IOT-04 (23/11/2026)

- **Alertas del Gerente en el panel (regla 7 de IOT-CNS-LEC vs R007 de MAE-02).** El panel arma las alertas con `consultar_alertas(actor, …)`, como dice el documento (opción a); `Alerta.objects.para` le da al Gerente solo las `para_gerente`, y las del IoT van al Agrónomo
  mientras esté activo: el Gerente que mira un invernadero con Agrónomo ve «0 alertas». Por eso el bloque dice «Las alertas de este invernadero las recibe {Agrónomo}; vos las recibís si no tiene un Agrónomo activo.». **Alternativa (b), a decidir con el análisis:** una consulta propia del panel para que
  el Gerente vea todas las del invernadero (la regla 7 y la regla 1 dicen que consulta todo).
- **Paso 9 de la «Verificación a mano» de IOT-04 vs D-76 punto 5.** El paso decía que `--ahora` calculaba «el fotoperíodo de hoy»; manda D-76 (el día en curso nunca se calcula; un día D se calcula desde D+1 a la 01:00). Resuelto en la tarea; queda a modo de registro.
- **La reserva del correo antes de enviar (D-76 punto 7, corregido el 23/11/2026).** Costo: un proceso que muere entre reservar y enviar pierde ese correo (no hay duplicados). Mientras dura el envío, el panel muestra «Notificada por correo». `intentos_correo` cuenta fallos.
- **Advertencia 5b de la retención.** Viaja por la sesión y no por `django.contrib.messages`: `core/templates/core/base_con_sesion.html` dibuja todo mensaje que no es de error con el estilo de éxito (un `warning` sale verde). Si se quiere un estilo de advertencia para los mensajes, es un cambio de `core`.
- **Sin sesión con HTMX.** El proyecto no tiene un patrón para un pedido HTMX sin sesión (solo para la contraseña temporal, con `HX-Redirect`): manda el `LoginRequiredMiddleware` (302 al inicio de sesión) y HTMX mete esa pantalla dentro del panel que se refresca. Decidir un patrón común (por ejemplo, `HX-Redirect`).
- **Guardados simultáneos desde la pantalla de configuración (límite conocido, igual que MAE-04).** El formulario manda todos los campos: un formulario viejo puede pisar un campo que otra persona acaba de cambiar (gana el último). El servicio solo toca lo que recibe.
- **El menú lateral de «IoT»** apunta a `/iot/`, que redirige a «Monitoreo»: mejora menor (apuntarlo directo).
- **Tabla de «Situación de un sensor» (`consultar_lecturas.md`).** Se sumó la fila 4b «Sin lecturas» (el sensor tiene último mensaje pero la retención ya borró sus lecturas); corregida en el extracto el 23/11/2026.
- **Un Agrónomo dado de baja no recibe el correo** (se pide cuenta activa y con email); si la alerta no tiene a quién mandarse, suma un intento y deja un `logger.warning`. D-76 punto 7 no lo dice: sumarlo a la decisión si se confirma.
- **Auditoría de la revisión.** Los afectados son solo las alertas (como dice el extracto): una corrida que solo borra lecturas deja `afectados` vacío y el sistema va en `datos`.
- **Retención.** El «un solo `DELETE` por sistema» es un `queryset.delete()` del ORM (lee los ids y borra por lotes, por las claves `PROTECT`).
- **Panel.** El identificador de un sensor no es un enlace a su ficha (solo los actuadores tienen «Ver equipo»); el enlace «Registrar este equipo» lleva el identificador en minúsculas (el de la clave de la alerta); los grupos de sensores van siempre abiertos (el botón de plegar del prototipo no se implementa).

## Abiertos desde COM-01 (23/11/2026)

- **Una prueba de `maestros` se tocó.** `maestros/tests/test_datos_de_cuenta_transportista.py`, clase `DatosDeCuentaDelTransportistaTests`, se aísla del «Vehículo» de `comercial` con `mock.patch.object(core.extensiones, "_DATOS_DE_CUENTA", [...])`. La tarea decía que ninguna prueba de `maestros` cambia; con un segundo registrante de `datos_de_cuenta` es inevitable. Cada app que se sume a ese punto tendrá que aislar esas cuatro pruebas o filtrar por etiqueta.
- **Cuentas del cargador.** `transportista2@prueba5.local` rompe el patrón `<rol>@prueba<N>.local` (hace falta un segundo Transportista). Y `docs/patrones/datos_de_verificacion.md` dice «Hoy: `maestros` e `iot`» y «la siguiente app usa `prueba4`»: ya están `produccion` (orden 15, `prueba4`) y `comercial` (orden 20, `prueba5`).
- **Menú del Gerente.** Queda «Panel de control, Producción, IoT, Comercial…»: el prototipo pone «Comercial» antes de «IoT», pero la prueba de IOT-01 exige «IoT» justo después de «Producción» y el orden sigue al de `INSTALLED_APPS`. No se cambió nada de `core`.
- **«Dirección en uso» ya escrita.** El extracto de clientes la daba por completar en COM-02 y COM-03; la rama (corregir crea otra y deja inactiva la anterior; no se borra) está en `modificar_cliente` y se prueba con `mock.patch`. Falta solo la consulta de `direcciones_en_uso`.
- **Si se desactiva o se borra una dirección, su corrección se ignora.** El formulario manda siempre la corrección de todas las direcciones existentes (sin cambios no pasa nada, D-28); lo resuelve el servicio.
- **Contratos de código que fijaron las pruebas** (los revisó el estudiante antes de implementar): `DatosDeCliente` (`desde_post` con `nueva-<i>-<campo>`, `corregida-<id>-<campo>`, `desactivar`, `borrar`) y `DatosDeVehiculo`; códigos `cuit_de_cliente_activo|inactivo` (con `params["cliente_id"]`), `direccion_repetida|invalida|en_uso`, `correo_con_suministro_vigente`, `patente_invalida|repetida`, `capacidad_invalida`, `capacidad_menor_que_la_carga`, `transportista_invalido|con_vehiculo|con_entregas`, `vehiculo_en_ruta|inactivo|no_inactivo` y `cambio_simultaneo`. COM-02 y COM-03 los reutilizan al volver a COM-REG-CVT y COM-PCT-SUM (`volver`).
- **Notificaciones de vehículo.** El extracto da «con {tipo} {patente} ({capacidad} kg)»; el código dice «con camioneta AE123CD (800 kg)» (tipo en minúscula y `texto_capacidad`).
- **Bloqueos de vehículos.** Cuentas (quien actúa y los transportistas que entran o salen, en una consulta y por id) y después el vehículo. Con un solo Gerente activo (D-09), todo el ABM de vehículos queda serializado por su cuenta: las carreras de patente y de transportista las resuelve el bloqueo y la base queda como respaldo.
- **Búsqueda sin `unaccent`.** La búsqueda de clientes y de vehículos usa `icontains`, como pide el extracto (la ya anotada falta de `unaccent`).


## Abiertos desde COM-02 (23/11/2026)

- **`detalle_de_cosechas` sí se llama en COM-02.** `docs/api/extensiones_de_produccion.md` decía «nadie lo llama en COM-02»; la condición 1 de la merma (`produccion/servicios/mermas.py`, `_alerta_por_reservas_de_cosecha`) lo usa para nombrar en la alerta las cosechas «a realizar» sin cobertura (extensión 10a de PRD-MER). Sin registrante, la alerta sale sin los códigos.
- **El comprobante lo envía el servicio, no la vista.** `compra_venta.md` (paso 16) decía que la vista llama a `enviar_comprobante`. Lo hace `registrar_compra_venta`, fuera de su `transaction.atomic()`. La venta nace `pendiente_envio` (con correo) o `para_imprimir` (sin correo); el envío la pasa a `enviado`. Si falla y registró el Gerente, el Vendedor responsable recibe «El comprobante de CV-… quedó pendiente de envío.». COM-03 y COM-04b deben seguir este mismo patrón.
- **`detalle_de_orden` devuelve 404 para una cosecha hasta COM-04a.** La tarea solo pedía ocultarla de la bandeja y de la lista (`exclude(tipo_orden=COSECHA)`); en `produccion/servicios/ordenes.py` se agregó el mismo `exclude` con el comentario «hasta COM-04a» para no abrir una ventana que no existe. COM-04a debe quitar las tres líneas.
- **«Agregar variedad» no agregaba el renglón (corregido en COM-02).** `_analizar` descartaba los renglones en blanco también en el cálculo de pantalla. Ahora, con `estricto=False`, se conservan sin validar; al resumir y registrar se ignoran. `FormularioDeCompraVenta.cargadas` cuenta los renglones con algo cargado (resumen y `puede_revisar`). COM-03 (suministro) tiene un formulario igual: reutilizar este criterio.
- **Códigos y campos de error de COM-REG-CVT que fijó el código** (para COM-03 y COM-05): `vendedor_obligatorio|invalido|inactivo`, `cliente_obligatorio|inactivo`, `fecha_obligatoria|invalida|pasada`, `modalidad_invalida`, `direccion_obligatoria|no_valida`, `invernadero_obligatorio|no_habilitado`, `variedad_obligatoria|repetida|inactiva`, `cantidad_invalida`, `supera_disponible`, `precio_invalido`, `sin_renglones`, `stock_insuficiente`, `cambio_simultaneo`, `comprobante_no_pendiente`, `cliente_sin_correo`. Campos: `vendedor`, `cliente`, `fecha_pactada`, `modalidad`, `direccion`, `invernadero`, `renglon-<i>-variedad|cantidad|precio` y `__all__`.
- **Formatos que aceptan los campos.** Precio con coma o punto decimal («1.500,50» y «1500.50»); fecha `aaaa-mm-dd` o `dd/mm/aaaa`.
- **La lista de contratos filtra el cliente también por texto** (`cliente_q`, además de `cliente`).
- **«Una venta contra la baja del invernadero»** solo prueba que la baja rechaza antes la venta con retiro (`invernadero_no_habilitado`). Que una reserva de cámara impida la baja llega con COM-04 (partidas).
- **La fábrica `orden_suelta` de `produccion` pone prioridad «media» a la cosecha** (la restricción «cosecha ⇒ prioridad» la exige); ninguna prueba existente cambió.

## Abiertos desde CMP-01 (23/11/2026)

- **El tipo del proveedor no se cambia** (decisión del estudiante en la sesión; el extracto de CMP-MOD-PRV no lo nombra y el prototipo tampoco lo deja cambiar). Como el CUIT es único entre activos e inactivos, un proveedor cargado con el tipo equivocado no tiene corrección posible, ni dándolo de baja y volviendo a cargarlo. Decidir si se permite cambiarlo (y qué pasa con la razón social o el nombre y el apellido).
- **Categorías dadas de baja:** el vínculo se conserva al modificar (regla 4 de CMP-MOD-PRV), así que el Gerente no puede ver ni quitar esos vínculos: la ficha y el formulario solo muestran las categorías activas. Decidir si hace falta una forma de verlos o quitarlos.
- **`core/models.py` más allá de «Límites»:** la tarea decía «solo las acciones»; `docs/patrones/auditoria.md` (paso 3) pide también las etiquetas, y se sumaron `tipo_proveedor` y `especialidades` a `ETIQUETAS` (`cuit` y `razon_social` ya las había sumado COM-01) y `tipo_proveedor` a `VALORES_VISIBLES` (aprobado por el estudiante). Conviene que «Límites» de las tareas que auditan por primera vez nombre las etiquetas.
- **El CUIT se audita con los 11 dígitos**, sin guiones, como `cuit_organizacion` en `perfil.py`; los guiones se agregan al mostrar (D-58).
- **Hueco de documentación:** «Leer» de CMP-01 no traía los archivos de vistas, formularios y plantillas de cultivos (`maestros/views.py`, `maestros/forms.py`, `maestros/templates/maestros/cultivos/`) que hacen falta para copiar el patrón de pantallas; el estudiante autorizó leerlos. Conviene listarlos en «Leer» de las tareas de pantallas de ABM, o resumir el patrón en `docs/patrones/abm.md`.
- **Funciones privadas de `maestros` reutilizadas:** `compras` importa `_actor_sigue_activo`, `_error_general` y `_tiene_contenido` de `maestros.servicios.invernaderos`, como ya hace `inventario`. Si se quiere evitar importar nombres privados, hay que hacerlas públicas en una tarea de `maestros`.
- **Pestañas de «Compras»:** hoy tienen solo «Proveedores» (`compras/templates/compras/proveedores/_pestanas.html`); cada tarea de la ronda suma la suya y, cuando sean varias, conviene mover la barra a una plantilla de `compras/`.
- **Esquema de verificación nuevo (D-95).** Se retiraron `core/verificacion.py`, el comando `cargar_datos_de_verificacion`, los `<app>/verificacion.py` de `maestros`, `iot`, `produccion` y `comercial` y sus pruebas (incluida `comercial/tests/test_verificacion.py`), y `docs/patrones/datos_de_verificacion.md`. Quedan sin tocar `docs/decisiones/D-56.md` y `docs/decisiones/D-94.md` (históricas; D-94 pide ampliar el cargador de `comercial`: ya no aplica) y las 69 tareas que traen «Verificación a mano» o nombran el cargador: manda `CLAUDE.md` (se ignora y cada paso a mano se convierte en un recorrido). Las secciones de `docs/historial.md` y `docs/revisiones_pendientes.md` que hablan de cargadores son historial.


## Abiertos desde COM-03a (23/11/2026)

- **Cantidad sin cubrir de un período.** `docs/patrones/stock_maduro.md` (sección 7) la escribe con `Σ cantidad_reservada`; se usa la cantidad **cubierta** (`min(cosechada, reservada)` en un lote ya cosechado), igual que COM-02 y la regla 10 de 8.8. Corregir el patrón.
- **`simular_varias` y `_leer_varias`.** El patrón nombra solo `simular`; la verificación acumulada de varias variedades y fechas hace una consulta por tabla. Sumarlas a la sección 7.
- **`rige_desde`.** Su definición está en `suministro.md:833` (COM-MOD-SUM), que «Leer» de COM-03a no listaba. Sumarla a «Leer».
- **Marca «Al límite» y su aviso.** El prototipo la pone con 1 tolerado restante; se pone también con todos usados (incumplimientos ≥ tolerados − 1). Con 0 tolerados, el aviso es texto propio: «El contrato no tolera incumplimientos: el primero lo resuelve y se aplica la multa.». Anotarlo en pendientes_CU (COM-CNS-SUM, regla 9).
- **Texto de la baja de variedad** (cambia el de COM-02): «Tiene contratos abiertos: N compra-ventas y M suministros.», sin el número que vale 0 y con singular.
- **Traspaso.** `contar` suma «Suministros vigentes: M» y `traspasar` devuelve compra-ventas y suministros. `pendientes_del_cliente` informa primero los suministros.
- **Superposición (9d).** La casilla «Continuar igual» es por detalle y, sin ella, el servicio rechaza con `superposicion_sin_confirmar` (también al Gerente).
- **Códigos de error y campos** (los reutilizan COM-03b y COM-05): `vendedor_obligatorio|invalido|inactivo|sin_invernaderos`, `cliente_obligatorio|inactivo|sin_correo`, `duracion_invalida`, `tolerados_invalidos`, `multa_invalida`, `plazo_pago_invalido`, `indemnizacion_pago_invalida`, `variedad_obligatoria|inactiva`, `direccion_obligatoria|no_valida`, `cantidad_invalida`, `periodo_invalido`, `fecha_obligatoria|invalida|fuera_de_rango`, `mecanismo_invalido`, `precio_invalido`, `porcentaje_invalido`, `meses_invalidos`, `plazo_entrega_invalido`, `indemnizacion_retraso_invalida`, `cantidad_minima_invalida`, `indemnizacion_faltante_invalida`, `par_repetido`, `superposicion_sin_confirmar`, `supera_disponible` (9e, al revisar), `stock_insuficiente` (14a, al confirmar), `sin_detalles`, `cambio_simultaneo`. Campos: `vendedor`, `cliente`, `duracion`, `tolerados`, `multa`, `plazo_pago`, `indemnizacion_pago`, `detalle-<i>-<campo>` y `__all__`.
- **`Suministro.solicitud_resolucion` no se crea** (lo crea COM-07a con su restricción).
- **El comprobante de COM-02** se tocó solo en su plantilla (le faltaba la hoja de estilos del sistema); también `comercial.css` (el CUIT del cliente y el resumen angosto del formulario de COM-02).
- **Selector «Compra-ventas / Suministros»** como dos enlaces en vez de un `<select>` (D-61). El prototipo lo tenía como `<select>`.
- **Prueba ajena a la tarea:** `produccion…test_prod_reg_apl…consumo_originado_en_el_consumo` falla después de las 21 h en Argentina (compara la fecha UTC del movimiento con la local). Arreglarla en una tarea de `produccion` o `inventario`.
- **Prueba visual retirada.** `comercial/tests/test_visual_suministros.py` (Playwright) importaba `core.tests.visual`, que nunca se versionó, y rompía el descubrimiento de pruebas del CI. Se borró por D-96; las correcciones de aspecto que encontró siguen en el «Cierre».
- **Pendientes de Drive.** pendientes_CU: COM-CNS-SUM (regla 9 y el aviso con 0 tolerados). pendientes_MD: nada nuevo.

## Abiertos desde CMP-02a (23/11/2026)

- **`Referrer-Policy: same-origin`, no `no-referrer` (D-88 punto 4 y D-65 punto 3).** Con `no-referrer`, Chromium manda `Origin: null` en los POST del mismo sitio y el CSRF de Django los rechaza: el portal no podía enviar una cotización en un navegador real (lo encontró una verificación con navegador real, antes de D-96; el cliente de Django no lo ve). Se corrigieron D-88, D-65 y los dos patrones; COM-04c (portal del cliente) tiene que usar `same-origin`. Solo se verificó en Chromium: falta probar Safari (iPhone) y Firefox con el portal real.
- **Cotizaciones visibles desde que llegan** (regla 6 de CMP-CNS-PED y prototipo; decisión del estudiante, 23/11/2026). «Cómo se aplica» de `docs/casos_de_uso/compras/pedidos.md` dice «solo después del final del día de la fecha límite»: hay que corregirlo.
- **Regla 4c de CMP-RLZ-PED incompleta a propósito:** `ya_pedido` cuenta solo los pedidos «en cotización»; la parte de la orden «pendiente de aprobación» la completa CMP-03, que crea `OrdenCompra` (disparador en `docs/disparadores.md`).
- **Correo de invitación que falla:** el aviso va en la pantalla del paso 13 con el texto de D-88 punto 6, y la ficha marca «No se pudo enviar»; no hay notificación de campana para quien actuó (H21; decisión del estudiante). No hay reintento automático: es «Reenviar invitación» (CMP-02b).
- **Aviso de pedido cubierto:** va a `destinatarios_por_destino` (D-87 punto 3: el Agrónomo activo de cada invernadero de destino o, si falta, el Gerente), no solo «al Agrónomo que realizó el pedido» como dice CMP-ENV-COT; y es una notificación **dentro** de la transacción (D-42), no «fuera» como dice el caso de uso: así no queda un aviso de algo que se revirtió.
- **El pedido se muestra como `P-0031`** (el de «Cómo se aplica» de CMP-02b), no `PED-0031` del prototipo (decisión del estudiante).
- **Tolerancia del 100 %:** con `porc_tolerancia_cobertura_pedido = 100` el mínimo de cada detalle es 0 y todo pedido queda «cubierto» sin cotizaciones; como el aviso sale al pasar de «no cubierto» a «cubierto», nunca sale. Decidir si «cubierto» exige al menos una cotización. No se probó ese borde.
- **Cobertura exacta:** el mínimo `pedida × (1 − tolerancia)` no se redondea a dos decimales (el prototipo redondea en `tolMin`); manda el caso de uso. El unitario mostrado es el de cuatro decimales redondeado a dos; si unitario × cantidad no da el total, se muestra solo el total (D-89 punto 7).
- **El filtro «InfoPonia» de la auditoría** (`consultar_auditoria`, `usuario` nulo) trae también los registros de los actores externos (proveedor mediante enlace, y el cliente cuando exista COM-04c). No se tocó `core/servicios.py` (fuera de «Permitido fuera de la app»): conviene filtrar por `rol` (o sumar «Proveedor (mediante enlace)» como opción).
- **`core` más allá de «Permitido fuera de la app»** (aprobado por el estudiante): `ETIQUETAS` y `VALORES_VISIBLES` (los roles externos y los estados del pedido) y las dos plantillas de auditoría (`registro.html` y `_tabla_auditoria.html`). **Choque con COM-02 al bajar `main`:** `ETIQUETAS` ya traía `detalles`, `lineas` y `monto_estimado` de la compra-venta; repetirlas las pisaba en silencio y cambiaba el texto de aquellas pantallas. Se sacaron las repetidas y las líneas de la cotización usan su propia clave (`lineas_cotizadas`). Una prueba de CMP-01 cambió con permiso: «Compras» abre en «Pedidos».
- **Migración de `core` renumerada a 0028:** COM-02 también creó una `0027` (`0027_comercial_compra_venta`); la de CMP-02a (`0028_acciones_de_pedido`) depende de ella y `compras` 0002, de la 0028.
- **Nombres que difieren de los patrones:** `docs/patrones/enlace_del_proveedor.md` (sección 1) llama `enlace_vigente(token)` a lo que es `enlace_por_token(token)` más `situacion_del_enlace(enlace)` (que dice si sirve, está en solo lectura o por qué no sirve); `crear_enlace(invitacion, construir_url)` y `enviar_invitacion(enlace_id, url)` reciben la URL absoluta (la vista pasa `request.build_absolute_uri`), no el token. `anular_enlaces_de_pedido`, `anular_enlaces_de_proveedor` y `reemplazar_enlace` son de CMP-02b.
- **«Nuevo pedido» es un formulario que se vuelve a dibujar con cada botón** (sin JavaScript ni HTMX: `interfaz.md` prohíbe validar y recalcular mientras se escribe). El selector del catálogo (extensión 3a) agrupa por invernadero y **no tiene buscador por nombre ni por tipo** (la «Lista de tecnología» 3a lo menciona); el filtro propuesto de proveedores por categoría sí está completo. En un celular, la tabla de «insumos bajo el mínimo» scrollea adentro (el caso de uso piensa la interfaz del Agrónomo para computadora).
- **El portal y el correo de invitación hablan de «usted»** (como el prototipo); las pantallas internas, de «vos». Un token inexistente da 404 con «Este enlace no es válido»; uno que no sirve da 200 con el motivo y sin datos del pedido.
- **Pruebas:** en un `TestCase` el `on_commit` no corre solo y la redirección sigue antes de `captureOnCommitCallbacks`; las pruebas de las pantallas y el recorrido lo reemplazan por una llamada inmediata, que es lo que pasa en producción. `panelAgr` trae por ahora solo «Insumos bajo el mínimo» y «Esperando cotizaciones»; «Pedidos por resolver» es de CMP-03.

## Abiertos desde CMP-02b (24/11/2026)

- **7a de CMP-CNL-PED dice «el Sistema reintenta el envío»; D-88 punto 6 dice que no hay reintento automático.** Se implementó D-88 (la cancelación permanece y el correo que falla no se reintenta). Corregir la extensión 7a del extracto.
- **La cancelación manual no genera notificación de campana.** Quien actúa es el único Agrónomo del pedido y los proveedores se enteran por correo. Confirmar si el Gerente debería recibir un aviso.
- **«En curso» de H20** en `docs/api/extensiones_de_inventario.md` («abierto o con cotizaciones, no cancelado, no vencido sin cotizaciones, sin orden aprobada») no coincide con D-87 punto 5 y el caso de uso («en cotización»). Se implementó lo segundo; corregir el párrafo.
- **Reenviar solo hasta la fecha límite:** la regla 7 de CMP-CNS-PED y el prototipo no lo dicen; agregarlo a la regla.
- **Las cancelaciones automáticas se auditan como InfoPonia** aunque haya quien dio la baja (CMP-CNL-PED: «con actor=None»); la persona figura en el registro de la baja o del traspaso. Aclararlo en «Cómo se aplica».
- **El traspaso cancela aunque el Agrónomo saliente siga activo.** El disparador «Cuando exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido» decía «si el saliente sigue activo»; MD-62 no lo condiciona.
- **La ventana de baja de cuentas de `core` no muestra `Asignacion.cantidad`.** CMP-02b pone el número en el texto de lo que pasa; PRD-01 tiene el mismo hueco con las órdenes del Capataz.
- **El «Ver detalle» de `Impedimento.url`** es genérico (no «Ver pedido»), porque CMP-03 lo usará para las órdenes.
- **Prototipo:** `c_pedcnl` dice que las cotizaciones «se conservan como consulta» (el caso de uso las descarta) y no tiene resumen antes de confirmar (el caso de uso lo pide, paso 4).
- **Prueba paralela:** `TypeError: cannot pickle 'traceback' object` con `--keepdb --parallel` tras una migración nueva: es el clon desactualizado de la base de pruebas (`.claude/rules/pruebas.md`), no un fallo intermitente. Corregir la nota de IOT-05.

## Abiertos desde D-96 (23/11/2026)

- **La verificación vuelve a ser a mano** (pedido del estudiante: mirar capturas consumía demasiados tokens). Se retiraron Playwright, `core/tests/visual.py`, `requirements-dev.txt` y las pruebas visuales de CMP-01 y CMP-02a; siguen el recorrido con el cliente de Django, la revisión de migraciones y el retiro de los cargadores (D-95, puntos 1.a, 1.c y 3). Se reactivó la regla M5 y `docs/revisiones_pendientes.md`, con las secciones de CMP-01 y CMP-02a.
- **Lo que se pierde:** un defecto de aspecto o de comportamiento del navegador ya no lo ve una prueba. Por eso toda tarea con pantallas públicas o formularios lleva el paso de «navegador real» (ventana privada y enviar hasta el final): con `Referrer-Policy: no-referrer` el portal de CMP-02a no podía enviar nada y solo lo mostró un navegador real.
- **Tareas con la verificación en el esquema viejo:** `docs/tareas/comercial/COM-02-stock-maduro-y-compra-venta.md` (y las demás de comercial) nombran el cargador `cargar_datos_de_verificacion` y los «Datos para verificar», retirados en D-95 y que no vuelven: sus pasos de «Verificación a mano» valen, pero los datos se crean a mano. COM-02 no tiene sección en `docs/revisiones_pendientes.md` ni fila en el historial: las completa quien la cerró.

## Abiertos desde IOT-05 (23/11/2026)

- **`ahora` es un parámetro más** en `datos_para_emitir(actor, invernadero_id, ahora, actuador_id=None)`, `cancelar_comando_incluido(comando, motivo, ahora, responsable=None)` y `segundos_para_cancelar(comando, ahora)`: la firma de `emitir_comando.md` y `cancelar_comando.md` no lo trae (los servicios no leen la hora). Corregir los extractos.
- **La regla 2 y la regla 5 de IOT-CNL-CMD usan el mismo código (`comando_en_curso`) y el mismo mensaje** («El nodo acaba de retirar el comando: no se canceló. Podés cancelarlo cuando venza el intento (en n s).»): el servicio no distingue «se retiró hace un rato» de «se retiró entre la pantalla y la confirmación». La ventana de cancelar sí dice «El nodo puede estar ejecutándolo: podés cancelarlo en n s.».
- **Los códigos de error de `validar_comando` los comparte IOT-06** (reglas de actuación): `accion_no_disponible`, `accion_incompatible`, `valor_requerido`, `valor_invalido` y `valor_de_mas`. Quedan nombrados en su docstring; IOT-06 los reusa tal cual.
- **Texto de «configuración incompatible» por un rechazo (4f)**, que ningún documento fijaba: «{tipo} {identificador} · el nodo rechazó {COMANDO} (acción «{acción}»)[: {detalle}]». Falta en `entregar_informacion.md`, «Alertas: textos y origen» (D-97).
- **El contrato no define las razones de un `informado_en` inválido o futuro** en el resultado de un comando (`respuestas_y_errores.md`, sección 4b solo lista las de `resultado`, `detalle` y `estado`). Se usó «tiene que ser una fecha ISO 8601 con zona horaria» y «es más de 5 minutos posterior a la hora de InfoPonia». Sumarlas a la sección 4b.
- **La emisión usa una sola URL** (`comandos/`, con `paso` = `refrescar`, `resumen` o `emitir`) y la ventana de cancelar es `comandos/<id>/cancelar/`; los extractos no fijan las rutas.
- **La emisión bloquea el tipo antes que el invernadero** (D-82 y D-97): `emitir_comando.md` y D-78 punto 11 no nombran el tipo.
- **El filtro «Tipo» de la bitácora (PROD-CNS-BIT) no ofrece «Comando»**: `bitacora.TIPOS_DE_FILTRO` está fuera de «Permitido fuera de la app» de IOT-05. Los registros se listan igual. Sumarlo en otra tarea (ver `docs/disparadores.md`, «Cuando exista PROD-PNR-FDS»).
- **«Actuadores operativos» del panel no resta a un actuador que espera un comando:** cuenta su situación sin el comando pendiente (la fila sí muestra «Comando pendiente»). Confirmar con `consultar_lecturas.md`.
- **El retiro audita una vez por retiro**, con los hechos juntos (`datos.hechos`), y no un registro por comando (D-97).
- **Prueba paralela intermitente:** un primer intento de `python manage.py test iot produccion core --keepdb --parallel …` terminó con `TypeError: cannot pickle 'traceback' object` (el runner no puede mostrar un fallo). No se reprodujo en cuatro corridas más; si reaparece, correr en serie para ver el fallo.


## Abiertos desde COM-03b (24/11/2026)

- **D-64, punto 8 queda para COM-04a** (decisión del estudiante): la pre-reserva toma solo detalles «vigentes». Si una modificación ocurre antes de la corrida del día, el período que entra hoy en la ventana del detalle finalizado queda sin reservar y el calendario lo muestra «Reservado» (sin alerta). `pre_reserva.md` y la sección 7 del patrón de stock ya decían «desde COM-04».
- **Enlace del Agrónomo = la ficha del invernadero, explícito** (`maestros:invernadero`): la segunda enmienda de D-62 hace del detalle de la alerta el enlace *por omisión* y `pre_reserva.md` dice «la ficha del invernadero (enlace por omisión)». Corregir el texto de `pre_reserva.md`.
- **Comprobante único del estado actual** (sin columnas nuevas): `enviar_comprobante(contrato, tipo, cambios)` cambia asunto e introducción (modificación, rescisión, rescisión sin efecto); «Reenviar» deduce la constancia de la rescisión de `motivo_rescision`. Después de dejarla sin efecto no hay marca: ver `docs/disparadores.md`.
- **Rescisión sin períodos conservados (2a):** `fecha_ultima_entrega_rescision` y `fecha_rescision` valen hoy (la restricción `suministro_rescision_completa` exige la fecha). Decirlo en COM-RSC-SUM (pendientes_CU).
- **Rescisión después de una modificación:** `periodos_conservados` ignora los detalles finalizados por una modificación, cuyos períodos de la ventana se siguen entregando. Ver `docs/disparadores.md` (COM-05a1 y COM-06) y aclararlo en COM-RSC-SUM.
- **D-63, punto 4:** el aviso al Vendedor y al Gerente por falta de invernaderos activos sale una sola vez por texto. **«Se resuelve al llegar su fecha»:** la consulta con auditoría `pre_reserva_periodo` al empezar la corrida del día siguiente.
- **`asignar` usa `stock.hoy()`:** con `proceso_diario --fecha` la cosecha programada toma la fecha real de hoy, no la simulada (código de COM-02).
- **Detalle sin ningún período hasta la nueva fecha de fin** (acortar la duración): pasa a «finalizado» con `fecha_fin_detalle` = la nueva fecha de fin. COM-MOD-SUM solo dice «su último período».
- **Quién cambia el Vendedor:** un Vendedor que manda `vendedor` distinto del actual recibe `PermissionDenied`; mandar el actual no es un cambio.
- **Concurrencia:** la pre-reserva usa una transacción por período, así que «pre-reserva primero» solo garantiza el primer período frente a una modificación o rescisión que llegue en el medio.
- **`huella` y `conservados` en `None` no se comparan** en `rescindir_suministro` y `dejar_sin_efecto_rescision`.
- **Códigos y campos de error** (los reutilizan COM-04, COM-05 y COM-07): ver el «Cierre» de la tarea, punto 14.
- **Pruebas existentes reescritas:** `test_regla_10_las_acciones_de_la_ficha_son_solo_las_que_existen_en_com_03a` (ahora `…_sin_las_de_otras_tareas`) y `test_regla_ningun_boton_lleva_a_un_403`: «Modificar suministro» ya existe en la ficha del Vendedor.
- **Tema abierto con el Jardín Botánico:** que un preaviso igual a la ventana de pre-reserva (14 días) sea aceptable para modificar y rescindir.
- **Pendientes de Drive.** pendientes_CU: COM-RSC-SUM (2a con la fecha de hoy; el cierre y la rescisión después de una modificación); COM-ANL-RSC (los códigos `sin_rescision` y `rescision_cerrada`); COM-MOD-SUM (detalle sin períodos hasta la nueva fecha de fin; Vendedor solo el Gerente); PROD-PRR-SUM (el aviso de D-63 punto 4 una sola vez; el enlace del Agrónomo). pendientes_MD: nada nuevo.

## Abiertos desde IOT-06 (24/11/2026)

- **`iot/verificacion.py` y el cargador de datos de verificación** (la tarea pedía sumar `norte/sectorA/temp-vieja` y un paso del motivo `equipo_dado_de_baja`): no se hizo, porque D-95 los retiró. El paso del motivo `equipo_dado_de_baja` se cubre en las pruebas (`test_iot_baj_hdw.py`) y en los pasos 26 y 27 de la «Verificación a mano».
- **`comandos.filas_de_comandos`** es un nombre público nuevo sobre `_filas_de` (IOT-05), para reutilizar el aspecto de la lista de comandos en la ficha de la regla. Está fuera de «Permitido fuera de la app»: confirmar o moverlo.
- **El historial de la ficha de una regla muestra los últimos 25 comandos** y enlaza a «Comandos» con el origen «Regla de actuación» (el extracto no fija un límite).
- **«Activar» el sistema es un botón directo** (un POST, sin ventana, como `sys-activar` del prototipo); desactivar y dar de baja llevan ventana. El extracto no dice cuál.
- **Las pantallas de Hardware, Comandos y Reglas de un sistema dado de baja** dicen «no tiene Sistema IoT» (`sistema_del_invernadero` solo ve el vigente): el historial de un sistema dado de baja no tiene pantalla propia.
- **Panel de monitoreo:** el enlace a las reglas de actuación (punto 7 de «Cuando existan actuadores, comandos y reglas del IoT», de `docs/disparadores.md`) quedó sin hacer: la tarea no lo pedía.
- **Migración renumerada:** la de IOT-06 era `core` 0031 y pasó a 0032 al traer `main` (CMP-02b trajo la suya).

## COM-04a (24/11/2026): lo que se implementó distinto de lo escrito
- **Máximo al concretar (8b de PROD-CNC-CSC):** el texto dice «reservada + stock libre sin contar esta reserva», que cuenta dos veces las plantas de la propia reserva. Se implementó **cantidad actual − lo que reservan las demás órdenes**. Corregir el extracto (`cosecha.md`) y el documento de Drive.
- **Plantas no cosechadas ni perdidas:** quedan como stock libre y `asignar` puede volver a reservarlas al cubrir el faltante (no excluye los lotes de la cosecha, a diferencia de la cancelación). Confirmar si es lo querido.
- **Costo de lo cosechado:** `costo_de_la_merma` (si se cosecha todo, el costo entero) y costo por planta de 4 decimales para el movimiento y la partida; `docs/patrones/costo_del_lote.md` dice «Cosecha: fuera de la ronda».
- **Bitácora `cosecha`:** `sectores` = todos los del lote (también los de 0 plantas); la merma de las perdidas lleva la fecha de hoy, no la efectiva.
- **Códigos y contratos nuevos** (`docs/api/produccion.md` y `docs/api/extensiones_de_produccion.md` no los nombran): `supera_maximo`, `supera_no_cosechadas`, `cosecha_cambio`, `cosecha_resuelta`, `cosecha_duplicada` (se verifica **antes** que lo demás), `lotes_no_alcanzan`, claves `cv:<id>` y `sum:<id>:<fecha>`, `EntradasDeComercial` con 2 campos (COM-05a2 suma `envasado`).
- **Sectores:** se bloquean directo y no con `bloquear_sectores` (que rechaza un sector fuera de servicio).
- **Baja del invernadero:** una partida «disponible» la impide aunque su lote esté finalizado (D-64 punto 12); una prueba de concurrencia de COM-02 se ajustó.
- **Cancelar cosecha** es una página, no una ventana (D-47). `detalle_de_orden` abre las cosechas (API, sección 9).
- **Invariantes de las fábricas:** lo cubierto de un lote cosechado es `min(cosechada, reservada)` (regla 9 de 8.8); en producción `cantidad_sin_cubrir` ya lo hacía.

## Abiertos desde IOT-07 (24/11/2026)

- **Claves de auditoría del extracto.** `mantenimiento_automatico.md` y la tarea decían `desde` y `equipos` para la cancelación; esas claves ya existen con otro sentido (reactivación y baja del sistema). Se usaron `cancelada_desde` y `equipos_de_la_orden` (más `orden_mantenimiento`, `sin_orden`, `ordenes_canceladas` y `ordenes_mantenidas`). Hay que corregir el extracto y la tarea. Tocó `core/models.py` (solo `ETIQUETAS` y `VALORES_VISIBLES`, sin migración), fuera de «Permitido fuera de la app»: autorizado por el estudiante.
- **`produccion/tests/fabricas.py`** (fuera de «Permitido fuera de la app», autorizado): `orden_suelta` pone prioridad `media` también al mantenimiento, porque la restricción nueva `ordentrabajo_prioridad_en_mantenimiento` la exige. Sumarlo a «Permitido fuera de la app» de la tarea.
- **El Inicio del Técnico muestra solo el identificador de cada equipo** (el extracto pedía «identificador y descripción»: la descripción vive en cada subtipo y costaría una consulta por equipo).
- **El Inicio usa `timezone.localdate()`** para marcar las órdenes vencidas: el punto de extensión de `core` solo recibe al usuario, no la fecha.
- **El orden de bloqueo del traspaso y de dos operaciones del mismo actor no se puede probar con barrera.** Todas empiezan por las cuentas, y el Agrónomo es común, así que se serializan antes del invernadero: invertir el orden no las hace fallar. Solo la prueba de escalamiento contra cancelación (`test_d78_el_escalamiento_corre_entero_antes_de_que_la_cancelacion_tome_el_invernadero`) discrimina (con el orden invertido, bloqueo mutuo). Se descartó la prueba de barrera del traspaso.
- **Restricción `ordentrabajo_prioridad_en_mantenimiento` en Neon.** No hay mantenimientos anteriores a IOT-07, pero conviene confirmar antes del despliegue que ninguna orden de tipo mantenimiento tenga la prioridad vacía (la migración 0007 fallaría).
- **La baja con varias órdenes** da un impedimento por orden en el equipo y uno solo con la lista en el sistema; los códigos de error nuevos (`decisiones_incompletas`, `orden_no_cancelable`, `ordenes_cambiaron`, `orden_no_pendiente`, `cambio_simultaneo`, `motivo_obligatorio`, `motivo_largo`) no estaban en el extracto.
- **Si la alerta ya tiene otra orden (R048, 0..1)**, la orden nueva se crea sin alerta.

## USR-11 (24/11/2026): lo que se implementó distinto de lo escrito

- **Pruebas de servicio en un archivo aparte.** La tarea pedía extender las pruebas del ABM de cuentas; están en `core/tests/test_usr_11_rol_contador.py` (alta, reactivación, baja, consulta y concurrencia del Contador). Cambió una prueba existente: el `<select>` del alta ahora espera seis roles.
- **`docs/casos_de_uso/usuarios.md` sigue diciendo "cinco roles"** en la regla 1 de USR-ALT/MOD/BAJ/CNS-USR y "nunca más de un Gerente activo" en SEG-15. Manda `usuarios_rol_contador.md`; conviene actualizar `usuarios.md` en la próxima ronda de documentación.
- **Menú del Contador.** El prototipo (`NAV.con`) le da «Panel de control», «Compras» y «Contabilidad»; D-85 punto 6 dice solo «Panel de control» y «Contabilidad», y las dos entradas las registran CON-03a y compras. Hoy el menú es solo «Panel de control».
- **No existe `docs/modelo/core.md`.** `Usuario` y los roles están en D-01, D-09, D-11 y D-85, y el Contador también en `docs/modelo/contabilidad.md` (MD-114, R010). Pendiente decidir si se crea un extracto de `core`.
- **La ventana de reactivación** (`_ventana_confirmar.html`) usa la variable `titular_activo` en lugar de `gerente_activo`.

## CMP-03 (24/11/2026): lo que se implementó distinto de lo escrito

- **Las pruebas «aprobar contra la baja del proveedor» y «contra la baja del invernadero» son invariantes, no carreras.** Una orden no terminada ya impide las dos bajas (H20 y H22), así que la baja se rechaza siempre y no hay resultado que dependa del orden de bloqueo; las carreras reales son generar contra la baja del proveedor y dos aprobaciones del mismo insumo (esta última solo falla al sacar a la vez los bloqueos del invernadero, de la existencia y de los proveedores y el de `sumar_transito`).
- **La generación audita con un solo registro** (`generacion_orden_compra`: pedido, cotizaciones, orden y detalles); las postcondiciones g y h del caso de uso piden dos.
- **«Mañana vence la cotización» (paso 61)** se tomó como `fecha_validez == hoy + 1` y se recuerda solo la primera elegible; el documento no dice qué día cuenta como «mañana» ni qué pasa con varias (D-100, a validar).
- **«Órdenes rechazadas» del Inicio del Agrónomo** muestra las de los últimos 7 días (el criterio del prototipo `panelAgr`): ningún documento lo fija.
- **`cancelar_pedido_automaticamente` acepta `hoy` y `aviso`** (opcionales): sin `hoy`, `--fecha` no podría simular la fecha de cierre; sin `aviso`, el paso 62 no podría usar el texto de D-87.
- **Textos de CMP-03 redactados al implementar:** los correos de descarte y de aprobación y las notificaciones de la orden (pendiente de aprobación, aprobada, rechazada) y de los pasos 60 y 61; los documentos fijan qué dicen, no sus palabras.
- **La lista de órdenes no tiene paginación** (como la de pedidos): con muchas órdenes conviene paginarla.
