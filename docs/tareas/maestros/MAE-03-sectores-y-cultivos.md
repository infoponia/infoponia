# MAE-03 · Sectores y cultivos, con los tipos de etapa

Estado: pendiente | App: maestros | Rama: feature/mae-03-sectores-y-cultivos | Ronda: Producción 1

Depende de: UI-01 (estilo y marco) y NOT-01 (notificación de PROD-MOD-CLT b). Si alguna no está hecha, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-ALT-SCT | Alta Sector | docs/casos_de_uso/maestros/sectores.md | — |
| PROD-MOD-SCT | Modificar Sector | docs/casos_de_uso/maestros/sectores.md | Postcondición b y regla 5 (volver a activar un sector fuera de servicio): solo el cambio de estado y el punto de extensión; el registro «Fuera de servicio» y la bitácora son de PRD-04 |
| PROD-BAJ-SCT | Baja Sector | docs/casos_de_uso/maestros/sectores.md | Impedimentos de agujeros y hardware por punto de extensión (los registran PRD-01 e IoT) |
| PROD-CNS-SCT | Consultar Sector | docs/casos_de_uso/maestros/sectores.md | La barra de ocupados y comprometidos, el perfil, los lotes, las órdenes y el hardware salen de puntos de extensión |
| PROD-ALT-CLT | Alta Cultivo | docs/casos_de_uso/maestros/cultivos.md | — |
| PROD-MOD-CLT | Modificar Cultivo | docs/casos_de_uso/maestros/cultivos.md | El renombre de semillas y los invernaderos que usan el cultivo, por puntos de extensión (los registra INV-03) |
| PROD-BAJ-CLT | Baja Cultivo | docs/casos_de_uso/maestros/cultivos.md | — |
| PROD-CNS-CLT | Consultar Cultivo | docs/casos_de_uso/maestros/cultivos.md | Las variedades aparecen cuando INV-03 las crea; sin ellas, «no tiene variedades» |

## Leer

- Casos de uso: los dos extractos de la tabla, completos, **incluida la sección «Cómo se aplica en la ronda»** de cada uno
- Modelo: docs/modelo/maestros.md — TipoEtapa, SectorProduccion, Cultivo, «Variedad, Ciclo y EtapaProductiva (solo lo que
  necesitan los cultivos y los sectores)» e Invernadero (solo «Asociaciones» R098 y «Reglas que lo tocan»)
- Decisiones: D-05, D-06, D-22, D-28, D-30, D-32, D-36, D-37, D-39, D-40, D-42, D-44, D-45, D-47
- API: docs/api/extensiones_de_maestros.md (el contrato de los puntos de extensión; implementalo tal cual) y
  docs/api/notificaciones.md
- Patrones: docs/patrones/bloqueos.md (sección «Invernadero»), docs/patrones/auditoria.md, docs/patrones/datos_de_migracion.md
  (incluida «Singletons y catálogos fijos»), docs/patrones/abm.md, docs/patrones/trabajo_en_paralelo.md
- Pantallas: docs/prototipos/produccion/ — `sectoresTab`, `sectorCard`, `MODALS['sector-form']`, `MODALS['sector-baja']`,
  `MODALS['sector-activar']`, `ultimoAviso`, `cultivosTab`, `MODALS.cultivo`, `MODALS['cult-baja']`, `VIEWS.prod` (solo las
  pestañas), `et` (el chip de tipo de etapa y su color). Solo guía visual: lo que difiera de los CU lo decide el CU (L7)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código a leer: maestros/models.py (Invernadero, `tiene_sectores`), maestros/extensiones.py, maestros/servicios/invernaderos.py
  (`bloquear_invernadero_activo`, `_exigir_gerente`, `_detalle_con_alertas`), maestros/views.py y su plantilla de ficha, core/menu.py

## Límites

- Crea modelos: `TipoEtapa`, `SectorProduccion`, `Cultivo`, `Variedad` (columnas mínimas), `Ciclo`, `EtapaProductiva`
  (columnas mínimas) → revisá docs/disparadores.md («Cuando exista SectorProduccion»)
- Migraciones: solo nuevas, en `maestros`: una de esquema (los seis modelos y sus restricciones) y una de datos
  (`cargar_tipos_de_etapa`, con los cinco tipos). Con una de `core` si se agregan acciones de auditoría (choices; ver
  `docs/patrones/trabajo_en_paralelo.md`)
- Permitido fuera de la app: `core/models.py` (solo `RegistroAuditoria.Accion`, `ETIQUETAS` y `ACCIONES_DE_NEGOCIO`: `alta_sector`,
  `modificacion_sector`, `baja_sector`, `reactivacion_sector`, `alta_cultivo`, `modificacion_cultivo`, `baja_cultivo`,
  `reactivacion_cultivo`), su migración, `core/menu.py` si hace falta una entrada, y los tres textos de
  `docs/disparadores.md`, `docs/tareas/README.md` y `docs/tareas/ronda_produccion_1.md` al cerrar (M3)
- Dependencias nuevas: ninguna
- Fuera de alcance: alta, modificación, baja y consulta de variedades (INV-03); las semillas (INV-03); poner un sector fuera de
  servicio, su registro y su bitácora (PRD-04); lotes, órdenes y ocupaciones (PRD-01); hardware (IoT); alta de variedad desde la
  pantalla de cultivos; PerfilOrganizacion y configuración (MAE-04)

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y migraciones.** Los seis modelos de la ficha, con sus restricciones de base (único `(invernadero,
   lower(nombre_sector))`, único `lower(nombre_cultivo)`, `nombre_cultivo` de hasta **40 caracteres** (con la variedad de hasta 50, el nombre de la semilla «Semilla {cultivo} {variedad}» nunca pasa de los 100 del insumo; lo valida INV-03 y el renombre del cultivo), `cant_agujeros_total > 0`, estados válidos, `puesto_global` y `codigo`
   únicos, una etapa por tipo en cada ciclo) y todas las claves foráneas protegidas. Migración de datos con los cinco tipos
   (`docs/patrones/datos_de_migracion.md`). En `maestros/tests/fabricas.py`: `ConDatosDeMaestros` y fábricas de sector, cultivo,
   variedad y ciclo. `Invernadero.tiene_sectores()` pasa a mirar los sectores activos o fuera de servicio (hoy devuelve falso
   siempre). Pruebas: `maestros/tests/test_sectores_modelo.py` (restricciones, `tiene_sectores`, la migración sobre tablas
   vacías, que los cinco tipos cargados coinciden con la ficha).
2. **Puntos de extensión.** Los de `docs/api/extensiones_de_maestros.md` en `maestros/extensiones.py` (sectores y cultivos, incluido
   `registrar_variedades_de_cultivo`, que admite un solo registrante),
   más `registrar_efecto_de_vuelta_a_servicio(funcion)` con `funcion(actor, sector)` (lo registra PRD-04). Cada uno con su
   resultado neutro sin registrantes. Pruebas: `maestros/tests/test_extensiones_sectores.py` con registrantes falsos
   (`mock.patch.object`), incluido que se juntan los de todos los registrantes sin quedarse con el primero.
3. **Servicios de sector** en `maestros/servicios/sectores.py`: `alta_sector`, `modificar_sector`, `reactivar_sector`,
   `volver_a_servicio_sector`, `baja_sector`, `consultar_sectores`, `obtener_sector`, `bloquear_sectores`, `agujeros_de`,
   `avisos_de_cambio_de_tipo`, `impedimentos_de_baja_de_sector`, `contenido_de_sectores`, `perfiles_de_sectores`,
   `acciones_permitidas`. Cada CU es una función en
   `transaction.atomic()` con el orden de bloqueo invernadero → sector, verifica después de bloquear que el actor siga activo
   y a cargo, y audita (D-36, acciones nuevas). Las advertencias de las reglas 4 de MOD y de BAJ se devuelven como un aviso
   que la vista muestra antes de confirmar; `modificar_sector` y `baja_sector` reciben `advertencia_confirmada` y, sin ella, lanzan
   `FaltaConfirmarAdvertencia` con los avisos (como `FaltaConfirmarPersonal` en MAE-01b). Registrar `registrar_efecto_de_baja` en
   `MaestrosConfig.ready()`: al dar de baja el invernadero, sus sectores pasan a inactivos, con un log de auditoría por sector
   (postcondición f de PROD-BAJ-INV). Pruebas: `test_prod_alt_sct.py`, `test_prod_mod_sct.py`, `test_prod_baj_sct.py`,
   `test_prod_cns_sct.py` (una prueba por regla y por postcondición; alcance Agrónomo/Gerente; nombre repetido con
   inactivos y con otro invernadero), y `test_sectores_concurrencia.py` (etiqueta `concurrencia`: dos altas con el mismo
   nombre, modificación del total contra una reserva simulada con registrante falso, baja del invernadero contra el alta de un
   sector).
4. **Pantallas de sectores.** La pestaña «Sectores» de la ficha del invernadero (PROD-CNS-INV regla 3; ya existe el aviso de
   «sin sectores» en lista y ficha), con las tarjetas por tipo de etapa y los dados de baja aparte, y el menú «⋯» de cada
   sector según su estado. Ventanas (HTMX con respaldo sin JavaScript): agregar, modificar (con el aviso de cambio de tipo y
   «Continuar igual»), baja (con los impedimentos listados), reactivar y volver a servicio. Sin JavaScript, cada ventana es una
   página. Rutas bajo `/produccion/<id>/sectores/…`. Pruebas: `maestros/tests/test_sectores_vistas.py` (permisos por rol, que
   el Gerente ve sin acciones, que un Agrónomo ajeno no ve acciones, mensajes de error por campo, el aviso, la baja con
   impedimentos falsos).
5. **Servicios de cultivo** en `maestros/servicios/cultivos.py`: `alta_cultivo`, `modificar_cultivo` (renombrar y reactivar),
   `baja_cultivo`, `consultar_cultivos`, `acciones_permitidas`. `modificar_cultivo` informa antes de confirmar cuántas
   semillas se renombran (`contar_semillas_a_renombrar`) y, dentro de la transacción, llama a `renombrar_semillas`, notifica
   (`notificar_a_varios`, NOT-01) al Agrónomo de cada invernadero de `invernaderos_que_usan_el_cultivo`, excluido el actor, y
   audita. Pruebas: `test_prod_alt_clt.py`, `test_prod_mod_clt.py`, `test_prod_baj_clt.py`, `test_prod_cns_clt.py` y
   `test_cultivos_concurrencia.py` (dos altas iguales; dos renombres a la vez; baja contra una variedad creada, con registrante
   falso).
6. **Pantallas de cultivos.** La página «Producción» del Agrónomo gana su barra de pestañas con «Invernaderos» (la lista de
   MAE-01) y «Cultivos y variedades» (`/produccion/cultivos/`; PRD-01 agrega después «Órdenes de trabajo»); el Gerente no la
   ve (regla 4 de PROD-CNS-CLT, un 404 si entra por la URL). Tarjetas por cultivo; el cuerpo y los botones de variedades salen de
   `variedades_de_cultivos(actor, cultivos)` (punto `registrar_variedades_de_cultivo`; lo registra INV-03; sin registrante, vacías:
   «no tiene variedades»), ventanas de nuevo, renombrar (con el aviso de semillas y de invernaderos notificados) y baja (con el
   conteo de variedades activas), reactivar. Los botones de variedades **no se muestran** hasta INV-03. Pruebas:
   `maestros/tests/test_cultivos_vistas.py`.
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3): anotar en `docs/disparadores.md` lo que dejan registrado las otras tareas (quién se registra en
   cada punto de extensión) y cerrar «Cuando exista SectorProduccion»; marcar MAE-03 en `docs/tareas/README.md` y en
   `docs/tareas/ronda_produccion_1.md`; si la API cambió, proponé también el cambio de `docs/api/extensiones_de_maestros.md` y avisá.

Si el tiempo apremia, lo último que se recorta es la parte de cultivos (pasos 5 y 6; se anota y se hace aparte); los sectores
no se recortan porque PRD-01 los necesita.

## Hecho cuando

- Los ocho casos de uso están implementados con una prueba por regla y por postcondición, más sus pruebas de vistas.
- Los puntos de extensión coinciden con `docs/api/extensiones_de_maestros.md` y se prueban con registrantes falsos.
- Las pruebas de concurrencia pasan con `--tag concurrencia`.
- La baja de un invernadero pasa sus sectores a inactivos con un log por sector.
- Comando de pruebas:
  python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test maestros --keepdb --tag concurrencia
  python manage.py test maestros --keepdb --tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas: `python manage.py migrate`. Cuentas: Gerente, dos Agrónomos (uno a cargo de un invernadero y otro no),
Capataz.

1. `migrate` aplica las migraciones de `maestros` (0004 esquema y 0005 datos) y de `core` (0012). En `/admin/` (solo con
   `DJANGO_DEBUG=1`, D-30) hay cinco tipos de etapa con sus perfiles.
2. Con el Agrónomo a cargo: ficha del invernadero → «Sectores»: aparece el aviso «sin sectores». «Agregar sector» con nombre
   repetido (mayúsculas distintas) muestra el error; con total 0 también.
3. Agregar tres sectores de tipos distintos: se agrupan por etapa con su cantidad de sectores y de agujeros; la marca «sin
   sectores» desaparece de la lista y de la ficha. Un sector nuevo muestra «Sin plantas: acepta cualquier perfil» y todo libre.
4. Modificar: subir y bajar el total; cambiar el tipo del único sector de una etapa muestra el aviso («variedades que dejan de
   poder sembrarse» sale con las variedades que cargue a mano en `/admin/`) y «Continuar igual» guarda. Guardar sin cambios no
   crea registro en «Auditoría» (D-28).
5. Dar de baja un sector: pasa a «Dados de baja», sin acciones salvo «Reactivar». Reactivarlo: vuelve activo.
6. Con el Gerente: ve los sectores de cualquier invernadero pero ninguna acción (ni «Agregar sector» ni el menú «⋯»). Con el
   Agrónomo ajeno (el que no está a cargo): **403** en la ficha y en cada ruta de sectores, porque la regla 1 de PROD-CNS-SCT y
   D-28 limitan al Agrónomo a los invernaderos activos a su cargo (corregido: el texto anterior decía «ven los sectores sin
   acciones»).
7. Dar de baja el invernadero: «Auditoría» muestra un log por sector con la baja. Reactivar el invernadero no reactiva sus sectores
   (regla 6 de PROD-BAJ-INV: los reactiva el Agrónomo con PROD-MOD-SCT).
8. «Producción» → «Cultivos y variedades» (Agrónomo): alta de «Acelga»; el nombre repetido da error; renombrar a «Acelga común»;
   dar de baja y reactivar. El Gerente no ve la pestaña y `/produccion/cultivos/` (y las demás rutas de cultivos) le da 404,
   también con JavaScript (HTMX) y sin él. Con el nombre de un cultivo que usa otro invernadero (cuando exista INV-03) el aviso
   de renombrar dice a qué invernaderos se notifica; hoy no hay semillas ni invernaderos que lo usen y no aparece.
9. En `/admin/`, crear una variedad activa del cultivo: la baja del cultivo ahora dice cuántas variedades activas tiene y no deja.
10. Sin JavaScript, los pasos 3, 4 y 8 funcionan igual (cada ventana es una página).
11. `python manage.py test maestros --keepdb --tag concurrencia` pasa. Después, una vez, la corrida sin concurrencia: el mixin
    vuelve a cargar los tipos de etapa.
12. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre

Hecha el 20/11/2026, en la rama `feature/mae-03-sectores-y-cultivos`. Los ocho casos de uso están implementados.

**Qué se hizo**

- Modelos (`maestros/models.py`): `TipoEtapa` (catálogo fijo con `codigo`, `puesto_global` y `perfiles_permitidos`),
  `SectorProduccion`, `Cultivo`, y `Variedad`, `Ciclo` y `EtapaProductiva` con columnas mínimas, con todas sus restricciones de base y
  claves foráneas protegidas. `Invernadero.tiene_sectores()` ya mira los sectores activos o fuera de servicio.
- Migraciones nuevas: `maestros/0004_sectores_y_cultivos` (esquema), `maestros/0005_cargar_tipos_de_etapa` (datos, idempotente por
  `codigo`, con `cargar` y `descargar`) y `core/0012_sector_y_cultivo_acciones_de_auditoria` (solo `choices`). Ninguna migración ya
  mergeada se tocó.
- Puntos de extensión (`maestros/extensiones.py`): los de `docs/api/extensiones_de_maestros.md` (sectores, cultivos y
  `registrar_efecto_de_baja_de_sector`), cada uno con su resultado neutro sin registrantes.
- Servicios: `maestros/servicios/sectores.py` y `maestros/servicios/cultivos.py`. La baja de un invernadero pasa sus sectores a
  inactivos con un log `baja_sector` por sector (registrante en `MaestrosConfig.ready()`).
- Pantallas: pestaña «Sectores» y tarjeta «Capacidad» en la ficha del invernadero, con ventanas de agregar, modificar (con el aviso
  de cambio de tipo), baja, reactivar y volver a activar; y la pestaña «Cultivos y variedades» de «Producción». Todas con HTMX y con
  respaldo sin JavaScript (cada ventana es una página).
- `core/models.py` (permitido): las 8 acciones nuevas en `Accion` y `ACCIONES_DE_NEGOCIO`, `ETIQUETAS` (`tipo_etapa`,
  `cant_agujeros_total`, `invernadero`, `semillas_renombradas`) y, con permiso explícito del estudiante, `fuera_de_servicio` en
  `VALORES_VISIBLES["estado"]`.

**Archivos modificados o creados**

- `core`: `models.py`, `migrations/0012_…`.
- `maestros`: `models.py`, `extensiones.py`, `apps.py`, `admin.py`, `forms.py`, `views.py`, `urls.py`; `migrations/0004_…` y `0005_…`;
  `servicios/sectores.py` y `servicios/cultivos.py`.
- Plantillas: `invernaderos/ficha.html` y `invernaderos/lista.html` (modificadas); `sectores/` (`_pestana`, `_tarjeta`, `_capacidad` y
  cinco ventanas); `cultivos/` (`lista`, `_pestanas_de_produccion`, `_variedades_simples` y dos ventanas).
- Estáticos: `static/maestros/css/sectores.css`, `static/maestros/css/cultivos.css` y `static/maestros/js/sectores.js`. Los tres se piden
  con `{% static_v %}` (interfaz.md), que llama a `static()` y funciona igual con `DEBUG` apagado (verificado con
  `DJANGO_DEBUG=0`); `sectores.js` solo cierra el menú «⋯» (un `<details>`) y no es necesario para usar las pantallas.
- Pruebas (`maestros/tests/`): `fabricas.py` (modificado) y los archivos nuevos `test_sectores_modelo.py`,
  `test_extensiones_sectores.py`, `test_prod_alt_sct.py`, `test_prod_mod_sct.py`, `test_prod_baj_sct.py`, `test_prod_cns_sct.py`,
  `test_sectores_vistas.py`, `test_sectores_concurrencia.py`, `test_prod_alt_clt.py`, `test_prod_mod_clt.py`, `test_prod_baj_clt.py`,
  `test_prod_cns_clt.py`, `test_cultivos_vistas.py` y `test_cultivos_concurrencia.py`.

**Pruebas (M1, 20/11/2026)**

- `python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: 1459 pruebas, OK
  (también corrida después de la de concurrencia: el mixin `ConDatosDeMaestros` recargó los cinco tipos de etapa).
- `python manage.py test maestros core --keepdb --tag concurrencia`: 43 pruebas, OK (9 son de MAE-03).
- `python manage.py test maestros core --keepdb --tag migracion`: 1 prueba, OK.
- `python manage.py makemigrations --check --dry-run`: «No changes detected». Pruebas de pantallas también OK con
  `DJANGO_DEBUG=0`.
- Pruebas nuevas de MAE-03: 368 (modelos 28, extensiones 23, sectores: alta 27, modificación 45, baja 37, consulta 28, vistas 51,
  concurrencia 4; cultivos: alta 14, modificación 32, baja 14, consulta 19, vistas 41, concurrencia 5).
- Cada paso de servicios (3 y 5) se hizo con las pruebas escritas primero, vistas fallar y aprobadas por el estudiante. Un detalle: con
  `--keepdb --parallel`, tras las migraciones nuevas hubo que recrear la base una vez (`--noinput`, sin `--keepdb`).

**Decisiones y diferencias respecto de la documentación** (para `docs/temas_abiertos.md`; nada se corrigió en silencio)

1. Agrónomo ajeno: manda la regla 1 de PROD-CNS-SCT (403), no el texto de la «Verificación a mano» ni del paso 4. Corregido arriba.
2. `nombre_sector` de hasta 40 caracteres y códigos de perfil `hoja_verde`, `pastura`, `frutos_grandes`, `frutos_pequenos`, `flores` y
   `hierbas`: la ficha del modelo no los fija. Para pasar a `docs/modelo/maestros.md`.
3. Texto de la notificación de PROD-MOD-CLT b (el CU no lo fija): título «Cambió el cultivo {anterior}», detalle «{Nombre Apellido}
   lo renombró a {nuevo}. Sus variedades siguen igual.». Una sola llamada a `notificar_a_varios` (sin el invernadero de cada
   destinatario, que variaría por cuenta). Se notifica solo a Agrónomos activos de invernaderos activos, sin el actor.
4. De `docs/api/extensiones_de_maestros.md` («Lote 5») se hizo `registrar_efecto_de_baja_de_sector`; `pasar_a_fuera_de_servicio`
   queda para PRD-04. `bloquear_sectores` verifica también que el invernadero esté activo (la API no lo decía).
5. Regla 4 de PROD-MOD-SCT y de PROD-BAJ-SCT: la advertencia se dispara cuando el sector activo es el último de su tipo (como
   `ultimoAviso` del prototipo), aunque no haya lotes ni variedades afectados; un sector fuera de servicio no la dispara. En la baja,
   los impedimentos se informan antes que la advertencia.
6. `variedades_de_cultivos` sin registrante, o para un cultivo que el registrante no trae, usa lo propio de `maestros`
   («No tiene variedades» o la lista simple de nombres, escapada).
7. El menú «⋯» es un `<details>` propio de `maestros` (el componente de `core` no existe). «Volver a activar» muestra un texto
   genérico: la fecha y el motivo de «fuera de servicio» son de PRD-04. «Renombrar» muestra siempre el aviso de semillas y de
   invernaderos notificados (sin JavaScript no se sabe si el nombre cambió).
8. Contrato nuevo que conviene documentar en `docs/api/extensiones_de_maestros.md`: quien crea una variedad (INV-03) bloquea el cultivo
   (`FOR NO KEY UPDATE`) antes de insertarla (cultivo → variedad); `baja_cultivo` cuenta las variedades activas después de bloquear.
9. Al Gerente, toda ruta de cultivos le da 404 también con método distinto de GET (no 405), para no delatar la ruta.
