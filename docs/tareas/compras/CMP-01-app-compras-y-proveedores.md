# CMP-01 · App `compras` y proveedores

Estado: pendiente | App: compras | Rama: feature/cmp-01-app-compras-y-proveedores | Ronda: Compras 1

Depende de: INV-02 (`TipoInsumo`, hecha). **No depende de la contabilidad.** `validar_cuit`: si COM-01 ya se mergeó, se usa; si no, esta tarea
lo crea (ver «Límites»). Puede empezar en paralelo con la ronda «Contabilidad 1».

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** Crea la app `compras` (nivel 6) y el dato maestro que necesita todo lo demás: el **proveedor**, con su CUIT único, sus
especialidades (tipos de insumo) y su baja lógica con reactivación. Lo administra solo el Gerente; el Agrónomo lo consulta para invitarlo.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-ALT-PRV | Alta Proveedor (con la reactivación) | docs/casos_de_uso/compras/proveedores.md | — |
| CMP-MOD-PRV | Modificar Proveedor | docs/casos_de_uso/compras/proveedores.md | Regla 2 (CUIT con pedidos u órdenes): la consulta existe y hoy da `False`; se completa en CMP-02a |
| CMP-BAJ-PRV | Baja Proveedor | docs/casos_de_uso/compras/proveedores.md | Precondición c: se completa en CMP-03; d: en CMP-05; regla 3 (anular enlaces): en CMP-02b |
| CMP-CNS-PRV | Consultar Proveedor | docs/casos_de_uso/compras/proveedores.md | Regla 4 (pedidos, órdenes, pagos y reclamos de la ficha): se completa en CMP-02a a CMP-06 |

## Leer

- Casos de uso: el extracto, completo, **incluida «Cómo se aplica (código)»**.
- Modelo: docs/modelo/compras.md («Convenciones» y `Proveedor`).
- Decisiones: D-87 (la de la ronda), D-58 (CUIT), D-05, D-06, D-21, D-22, D-28, D-30, D-36, D-37, D-44, D-61.
- API: docs/api/direcciones.md (solo la sección «CUIT»).
- Patrones: docs/patrones/abm.md, docs/patrones/bloqueos.md, docs/patrones/auditoria.md.
- Pantallas: docs/prototipos/compras_contabilidad/ — leé primero su `README.md`. Funciones: `tabPrv`, `VIEWS.c_prv`, `VIEWS.c_prvform`, `NAV.ger` y
  `NAV.agr` (líneas 2277 a 2279).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: el ABM de cliente si ya existe (`comercial/servicios/clientes.py`); si no, `maestros/servicios/cultivos.py` (el ABM más
  parecido); `maestros/validadores.py`, `maestros/servicios/perfil.py` (`_cuit_valido`); `inventario/models.py` (`TipoInsumo`); `inventario/apps.py`
  (cómo una app registra su menú); `core/models.py` (`Accion`, `ETIQUETAS`, `ACCIONES_DE_NEGOCIO`), `core/menu.py`, `core/acceso.py`
  (`rol_requerido`), `core/validadores.py` (`validar_telefono`).

## Límites

- Crea modelos: `compras.Proveedor` (con `especialidades`, M2M a `inventario.TipoInsumo`) → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0001_initial.py`; una de `core`, solo de `choices`, con las cuatro acciones (`alta_proveedor`,
  `modificacion_proveedor`, `baja_proveedor`, `reactivacion_proveedor`), con el número libre en `main`.
- Permitido fuera de la app: `config/settings.py` (`'compras'` en `INSTALLED_APPS` después de `'produccion'`, comentario `# nivel 6`);
  `config/urls.py` y `core/tests/urls_prueba_acceso.py` (una línea cada uno); `core/models.py` (solo las acciones) y su migración; íconos que falten
  en `core/templatetags/iconos.py`, copiados del prototipo; **si COM-01 no se mergeó:** `maestros/validadores.py` (`validar_cuit` y
  `formatear_cuit`, tal cual `docs/api/direcciones.md`), el reemplazo de `_cuit_valido` en `maestros/servicios/perfil.py` por la pública, y
  `maestros/tests/test_validar_cuit.py`. Al cerrar (M3): `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_compras_1.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: pedidos, cotizaciones, órdenes y todo lo marcado «se completa en CMP-NN».

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **App, modelo y auditoría.** La app (`apps.py` con el docstring de nivel), `Proveedor` con sus restricciones (CUIT único y de 11 dígitos; por
   tipo), las acciones de auditoría. — pruebas: `compras/tests/test_modelos.py`.
2. **CUIT** (si hace falta, ver «Límites»). — pruebas: `maestros/tests/test_validar_cuit.py`.
3. **Servicios** de alta (con reactivación), modificación, baja (con `impedimentos_de_baja` vacío) y consulta. — pruebas:
   `test_cmp_alt_prv.py`, `test_cmp_mod_prv.py`, `test_cmp_baj_prv.py`, `test_cmp_cns_prv.py`, `test_proveedores_concurrencia.py`.
4. **Pantallas y menú:** «Compras › Proveedores» para el Gerente (lista, ficha, formulario, baja, reactivación) y para el Agrónomo (lista y
   ficha). — pruebas: `test_proveedores_vistas.py`.

Si el tiempo apremia, lo último que se recorta es: el filtro por tipo de insumo de la lista (se anota como disparador).

## Hecho cuando

- El Gerente da de alta, modifica, da de baja y reactiva proveedores; el CUIT no se repite ni con dos pedidos a la vez; el Agrónomo los ve y no
  los cambia; los demás roles no entran.
- Pruebas verdes (incluida `@tag("concurrencia")`), `makemigrations --check` limpio, sin imports de `comercial` ni de `produccion`.
- Comando de pruebas: `python manage.py test compras maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano (`docs/patrones/verificacion_a_mano.md`)

Esta tarea se cerró primero con el esquema de D-95 (verificación por Claude Code, con navegador y capturas) y se pasó a **verificación a mano** por pedido del estudiante (D-96, 23/11/2026): los pasos del final son los que hace el estudiante y están en `docs/revisiones_pendientes.md`. No hay cargador de datos: lo que haga falta se crea en los pasos.

**Verifiqué**

- **Recorrido de punta a punta** (`compras/tests/test_recorrido_proveedores.py`, 1 prueba, 11 pasos, verde): alta con dos especialidades y aviso; CUIT repetido y errores por campo todos a la vez; persona física; baja con su ventana de confirmación; volver a cargar el CUIT ofrece reactivar
  y reactivar no crea un segundo proveedor; reactivar desde la ficha con el CUIT fijo; modificar (sin cambios no se audita); categoría dada de baja que no se ve ni se ofrece pero se conserva; filtros por texto (con y sin guiones) y por categoría; «Auditoría» con nombres legibles; el Agrónomo sin botones y con 403 al escribir.
- **Un navegador real, antes de D-96** (Playwright, hoy retirado) encontró que el nombre del proveedor en la lista salía con el azul subrayado por defecto del navegador, distinto del resto del sistema (el cliente de Django no lo ve); se corrigió con `.prv-nombre` en `compras/static/compras/css/compras.css`. Ya no se verifica así: lo visual lo mira quien hace los pasos a mano.
- **Migraciones:** `makemigrations --check` limpio. `sqlmigrate compras 0001`: solo crea `compras_proveedor` y la tabla de especialidades, con sus restricciones y claves (no toca nada existente). `sqlmigrate core 0026`: no-op (solo cambia `choices`). Aplicadas en la base local y en la de pruebas.

**Lo cubre una prueba:** cada regla, extensión y postcondición de los cuatro casos de uso (`test_cmp_alt_prv.py`, `test_cmp_mod_prv.py`, `test_cmp_baj_prv.py`, `test_cmp_cns_prv.py`); el acceso por rol y las pantallas (`test_proveedores_vistas.py`); la concurrencia (`test_proveedores_concurrencia.py`:
dos altas con el mismo CUIT, un alta contra una modificación y dos bajas); el modelo y sus restricciones (`test_modelos.py`).

**No pude verificar**

- **El despliegue:** que Render aplique `compras 0001` y `core 0026` sin errores (log de Render) y que la pantalla abra en producción.
- **El aspecto y el JavaScript** (buscador de categorías, campos según el tipo, ventana de la baja, respaldo sin JavaScript, celular): la prueba visual automática se retiró (D-96); los cubren los pasos 2, 5, 6, 15, 16 y 17 de abajo. En un celular las tablas se desplazan dentro de su contenedor (como las demás del sistema) y las acciones de la derecha quedan fuera de vista hasta desplazar.
- **El criterio de producto** (si el flujo le resulta natural a quien lo va a usar).

**Verificación a mano (D-96).** La hace el estudiante y la tacha en `docs/revisiones_pendientes.md` (M5). Entre paréntesis, lo que ya cubre una prueba.

*Antes de empezar.* En PowerShell, en la carpeta del proyecto y con el entorno activo (`.venv\Scripts\Activate.ps1`): `python manage.py migrate` y después `python manage.py runserver`. Abrí `http://127.0.0.1:8000/` e iniciá sesión con **tu Gerente**. No hay datos de prueba cargados: lo que haga falta se crea en los pasos.
CUITs válidos para probar (escribilos con o sin guiones): **A** `30-71234567-1`, **B** `20-12345671-9`, **C** `30-71234562-0`. Uno inválido: `30-71234567-2`.
Categorías: el sistema ya trae cuatro activas (Semillas, Envases, Repuestos de hardware, Infraestructura); alcanzan para los pasos 1 a 9.

1. **Menú y lista vacía** (lo cubre el recorrido). En el menú lateral aparece «Compras» (con un ícono de caja). Tocalo: ves la pestaña «Proveedores», los filtros y, como no hay proveedores, el texto «Todavía no hay proveedores. Registrá el primero con «Nuevo proveedor».».
2. **Alta con dos especialidades** (lo cubre el recorrido). «Nuevo proveedor» → dejá «Persona jurídica», CUIT **A**, razón social «Semillas del Sur», correo `ventas@semillasdelsur.com`, teléfono `376 400-1001`. En «Qué vende» escribí «sem» en el buscador: solo queda «Semillas»; marcala; borrá el buscador y marcá también «Envases» (la marcada no se pierde al buscar). «Registrar proveedor».
   *Esperás:* la ficha de «Semillas del Sur», el aviso «Registramos a Semillas del Sur.», el CUIT con guiones y las dos categorías.
3. **CUIT repetido** (recorrido). «Nuevo proveedor» otra vez con el CUIT **A** y otra razón social: el error aparece **debajo del CUIT**, «Ya está registrado como Semillas del Sur.», y lo que escribiste queda en el formulario.
4. **Varios errores a la vez** (lo cubre el recorrido). «Nuevo proveedor» con CUIT `30-71234567-2`, razón social vacía, correo vacío y teléfono `abc`: aparecen **todos juntos**, cada uno junto a su campo («El CUIT no es válido…», «Ingresá la razón social.», «Ingresá el correo: es donde recibe los pedidos.», «El teléfono solo puede tener números, espacios y los símbolos + - ( ). El + va solo al comienzo.»).
5. **Persona física** (lo cubre el recorrido). «Nuevo proveedor» → elegí «Persona física»: se ocultan los campos de razón social y aparecen nombre y apellido. Registrá vacío (da «Ingresá el nombre.» y «Ingresá el apellido.») y después con CUIT **B**, nombre «Ana», apellido «Gómez», correo `ana@mail.com`, sin teléfono. En la lista figura como «Ana Gómez», «Persona física».
6. **Baja** (lo cubre el recorrido). En la ficha de «Semillas del Sur» → «Dar de baja»: se abre una ventana sin recargar la página («¿Dar de baja a Semillas del Sur?»). «Cancelar» no cambia nada. Repetí y confirmá: vuelve a la lista con «Semillas del Sur quedó inactivo.» y ya no está entre los activos.
7. **Reactivar desde el alta** (lo cubre el recorrido). «Nuevo proveedor» con el CUIT **A**, razón social «Semillas del Sur S. R. L.» y otro correo → «Registrar proveedor». Aparece el aviso de que está dado de baja y el botón **«Reactivar con estos datos»**; tocalo: «… está activo otra vez.», con la razón social y el correo nuevos. La lista sigue teniendo **un solo** proveedor con ese CUIT.
8. **Reactivar desde la ficha** (recorrido). Dá de baja a «Ana Gómez». En la lista elegí el estado «Inactivos» → «Filtrar» → entrá a su ficha: ves **«Reactivar»** y no «Editar datos» ni «Dar de baja». Tocá «Reactivar»: el formulario trae sus datos, con el CUIT y el tipo **fijos** (como texto, no editables). Corregí el correo y confirmá.
9. **Modificar** (recorrido). «Editar datos» de «Ana Gómez»: cambiá el teléfono a `376 400-2002` y guardá («Guardamos los cambios.»). Probá dejar el correo vacío (error por campo) y cambiar el CUIT a **C** (se puede, porque todavía no tiene pedidos). Guardá **sin cambiar nada**: aparece el aviso pero **no** queda un registro nuevo en «Auditoría».
10. **Filtros** (recorrido). En la lista: buscá «sur» (por nombre), el CUIT **A** con guiones y solo `712345` (por parte del CUIT), elegí «Todos» y «Inactivos», y filtrá por una categoría. Con filtros aparece «Quitar filtros» y, si no hay resultados, «No hay proveedores con esos filtros.».
11. **Categoría dada de baja** (recorrido). Entrá como **Agrónomo** (ver paso 13 para crearlo) a «Inventario › Categorías», creá «Descontinuada» y dala de baja **después** de vincularla: primero, como Gerente, editá «Semillas del Sur» y marcala; luego el Agrónomo la da de baja. En la ficha de «Semillas del Sur» ya no aparece «Descontinuada» ni se ofrece al editar, pero el vínculo **se conserva**: al guardar otra modificación no se pierde (límite conocido: el Gerente no puede ver ni quitar ese vínculo).
12. **Auditoría** (recorrido). Con el Gerente, «Auditoría»: ves alta, modificación, baja y reactivación de proveedor. Abrí una modificación: la tabla Campo / Antes / Después muestra «CUIT» **con 11 dígitos** (sin guiones), «Razón social», «Tipo de proveedor» («Persona jurídica») y «Categorías de insumos» con sus nombres.
13. **Agrónomo: solo consulta** (lo cubre el recorrido). Con el Gerente, «Usuarios y seguridad» → «Nuevo usuario»: rol Agrónomo, un correo cualquiera y «contraseña temporal»; copiá la contraseña (se muestra una sola vez), cerrá sesión y entrá con esa cuenta (te pide elegir una nueva). En el menú ve «Compras» (después de «Inventario»). En «Compras › Proveedores» ve la lista (con «Todos» también los inactivos) y las fichas, **sin** «Nuevo proveedor», «Editar», «Dar de baja» ni «Reactivar». Escribí a mano `/compras/proveedores/nuevo/` y `/compras/proveedores/<número>/editar/` (el número está en la dirección de una ficha): ambas dan **error 403**.
14. **Otros roles** (opcional; recorrido). Con un Vendedor o un Capataz: no tienen «Compras» en el menú y `/compras/proveedores/` da 403.
15. **Sin JavaScript** (opcional). Con JavaScript desactivado en el navegador: «Dar de baja» abre la ficha con la ventana abierta; en el alta se ven los dos grupos de campos (razón social y nombre/apellido) y todas las categorías (sin buscador).
16. **Celular** (opcional). Con las herramientas del navegador, ancho de celular (390 px): la página no se desplaza a los costados; la tabla de la lista se desplaza dentro de su contenedor.
17. **Navegador real (D-96).** Abrí una **ventana privada**, iniciá sesión con el Gerente y repetí el alta (paso 2) y la baja (paso 6) **hasta el final**: tienen que completarse con sus avisos, sin una página «Prohibido (403)» ni «Verificación CSRF fallida» y sin errores en la consola del navegador (F12). Es lo único que el recorrido con el cliente de Django no puede ver: el JavaScript, el CSRF y los encabezados del navegador.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo.** Los cuatro casos de uso (CMP-ALT-PRV con su reactivación, CMP-MOD-PRV, CMP-BAJ-PRV y CMP-CNS-PRV), en cuatro pasos: la app `compras` (nivel 6) con `Proveedor`, la API pública del CUIT, los servicios y las pantallas «Compras › Proveedores».

- App y modelo: `compras/apps.py` (menú «Compras» para el Gerente, después de «Producción», y para el Agrónomo, después de «Inventario»), `compras/models.py` (`Proveedor`, `ProveedorQuerySet.en_alcance_de`),
  `compras/migrations/0001_initial.py` y, en `core`, la migración `0026_acciones_de_proveedor` (solo `choices`: las cuatro acciones; se regeneró sobre la 0025 de `main`, porque COM-01 e IOT-04 ya habían tomado la 0024 y la 0025). `config/settings.py`: `'compras',  # nivel 6`.
- CUIT: COM-01 **ya estaba mergeada** (la API pública `validar_cuit` y `formatear_cuit` de `maestros/validadores.py`, con sus pruebas, y `perfil.py` delegando en ella son de COM-01): CMP-01 **no creó nada de eso** y solo las usa (servicio, formulario y `Proveedor.cuit_formateado`). Se desechó el paso 2 de la tarea (y `maestros/tests/test_validar_cuit.py`) por haberse hecho antes; durante la implementación se escribió una versión propia, que se descartó al integrar `main`.
- Servicios (`compras/servicios/proveedores.py`, errores en `compras/errores.py`): `alta_proveedor`, `reactivar_proveedor`, `modificar_proveedor`, `baja_proveedor`, `impedimentos_de_baja` (vacía), `tiene_pedidos_u_ordenes` (da `False`), `listar_proveedores`, `ficha_de_proveedor` y `acciones_permitidas`.
- Pantallas: `compras/views.py`, `forms.py`, `urls.py`, plantillas en `compras/templates/compras/proveedores/`, `static/compras/css/compras.css` y `js/proveedores.js`; el ícono `pkg` en `core/templatetags/iconos.py`; una línea en `config/urls.py` y en `core/tests/urls_prueba_acceso.py`.
- Verificación: `compras/tests/test_recorrido_proveedores.py` (el recorrido) y la «Verificación a mano» de arriba (`docs/patrones/verificacion_a_mano.md`). La verificación visual con Playwright (`test_visual_proveedores.py`, `core/tests/visual.py`, `requirements-dev.txt`) se hizo y después se retiró (D-96).

**Pruebas** (resultado del cierre): `python manage.py test compras maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **2107 en verde** (ya integrada con `main`: COM-01 e IOT-04; el recuento incluía 5 pruebas visuales que se retiraron en D-96); `python manage.py test compras --keepdb --tag concurrencia`: **4 en verde**;
`makemigrations --check --dry-run`: sin cambios; `manage.py check`: sin problemas; sin imports de `comercial` ni de `produccion` en `compras`.
De esas, son de CMP-01: modelo 17, alta y reactivación 38, modificación 21, baja 12, consulta 19, vistas 42, recorrido 1 (más las 4 de concurrencia). En el paso 3 las pruebas se escribieron primero y se mostraron fallando; el estudiante las revisó y pidió auditar el CUIT con 11 dígitos (se ajustaron).

**Decisiones y desvíos** (propuestos para `docs/temas_abiertos.md`; ninguno cambia una decisión vigente):

1. `core/models.py`: «Límites» decía «solo las acciones», pero `docs/patrones/auditoria.md` (paso 3) pide también el nombre visible de cada campo nuevo. Se sumaron `tipo_proveedor`, `cuit`, `razon_social` y `especialidades` a `ETIQUETAS` y `tipo_proveedor` a `VALORES_VISIBLES` (aprobado por el estudiante); no se tocó `VALORES_VISIBLES["estado"]` ni otra clave compartida.
2. El **tipo** (jurídica/física) **no se cambia** al modificar ni al reactivar (decisión del estudiante; el extracto no lo dice y el prototipo tampoco lo deja cambiar). Como el CUIT es único, un proveedor cargado con el tipo equivocado **no se puede corregir** (ni dándolo de baja y cargándolo de nuevo, porque el CUIT sigue ocupado): conviene decidir si se permite.
3. **Categorías dadas de baja:** el vínculo se conserva al modificar (regla 4 de CMP-MOD-PRV), así que **el Gerente no puede ver ni quitar esos vínculos** (la ficha y el formulario solo muestran las activas). Queda para `docs/temas_abiertos.md`.
4. El **CUIT se audita con los 11 dígitos**, sin guiones (como `cuit_organizacion` en `perfil.py`); los guiones se agregan solo al mostrar (`formatear_cuit`, D-58).
5. `ErrorDeCompras` (`compras/errores.py`) lleva `codigo`, `mensaje`, `campo` y `datos`, como `ErrorDeProduccion`. Códigos: `cuit_de_inactivo` (con `proveedor_id`), `proveedor_inactivo`, `proveedor_no_inactivo` y `baja_con_impedimentos` (con todos los impedimentos). Los errores de datos son `ValidationError` por campo (`cuit_invalido`, `cuit_repetido`, `cuit_con_pedidos`, `obligatorio`, `sin_contenido`, `demasiado_largo`, `email_invalido`, `telefono_*`, `categoria_inactiva`, `categoria_inexistente`).
6. El servicio reutiliza `_actor_sigue_activo` y `_tiene_contenido` de `maestros.servicios.invernaderos` (privadas), como ya hace `inventario`.
7. Se usan `validar_cuit` y `formatear_cuit` tal como las dejó COM-01 (rechazan vacío, aceptan guiones y espacios; `formatear_cuit` devuelve tal cual lo que no son 11 dígitos).
8. `tiene_pedidos_u_ordenes` e `impedimentos_de_baja` existen hoy vacías: **CMP-02a** completa la primera (`invitaciones`/`cotizaciones`), **CMP-02b** suma la anulación de enlaces a la baja (regla 3 de CMP-BAJ-PRV), **CMP-03** el impedimento `orden_no_terminada` y **CMP-05** `pago_pendiente`. Hasta entonces dan `False` y `[]`.
9. «Leer» no traía los archivos de vistas, formularios y plantillas de cultivos (`maestros/views.py`, `forms.py`, `templates/maestros/cultivos/`), que hacen falta para copiar el patrón de pantallas: **hueco de documentación**; el estudiante autorizó leerlos.
10. Las pestañas de «Compras» tienen hoy solo «Proveedores» (`_pestanas.html`); cada tarea suma la suya. El buscador de categorías es un campo que oculta casillas (con JavaScript), no un componente nuevo de la hoja de estilos.
11. Nombres de las pruebas: por precondición `test_pre_<letra>_…` (D-28), por regla `test_regla_<n>_…` y por postcondición `test_post_<letra>_…`.
12. **Cambio del esquema de verificación = D-95** (pedido del estudiante, con permiso explícito para Playwright como dependencia solo de desarrollo): se dejó de verificar a mano y de cargar datos de prueba; la verificación la hace Claude Code (recorrido, visual y revisión de migraciones) y, al final de cada ronda, el estudiante recibe los «Pasos para replicar», opcionales. Se retiró **todo** el esquema de cargadores: `core/verificacion.py`, el comando `cargar_datos_de_verificacion`, los `<app>/verificacion.py` de `maestros`, `iot`, `produccion` y `comercial` con sus pruebas, y `docs/patrones/datos_de_verificacion.md` (el de `compras` no llegó a mergearse). Cambian `CLAUDE.md`, `docs/README.md`, `docs/tareas/_plantilla.md`, `.claude/rules/pruebas.md`, `docs/patrones/verificacion_por_claude.md` (nuevo), `docs/decisiones/D-95.md` (nuevo) y su fila en `docs/decisiones/README.md`; `docs/revisiones_pendientes.md` queda congelado. **D-96 (23/11/2026) revirtió parte de esto:** la verificación vuelve a ser a mano, sin navegador (se retiran Playwright, `core/tests/visual.py`, `requirements-dev.txt` y las pruebas visuales); siguen el recorrido, la revisión de migraciones y el retiro de los cargadores.
13. **Pruebas retiradas por pedido del estudiante:** `core/tests/test_verificacion.py`, `maestros/tests/test_cargar_datos_de_verificacion.py`, `iot/tests/test_verificacion.py`, `produccion/tests/test_verificacion.py` y `comercial/tests/test_verificacion.py` (probaban el cargador retirado; sin ellas no se debilitó ninguna regla de negocio).

### Pantallas: lo que se corrigió del prototipo

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| `VIEWS.c_prvform` (CUIT al editar) | El CUIT era de solo lectura siempre | Se puede corregir mientras no tenga pedidos ni órdenes; con ellos, se ve de solo lectura con el motivo | Regla 2 de CMP-MOD-PRV |
| `MODALS.prvbaja` / `prvBloq` | Bloqueaba la baja si el proveedor tenía un enlace de cotización abierto | No bloquea (la lista de impedimentos es vacía hasta CMP-03 y CMP-05); la ventana ya sabe mostrar impedimentos con «cómo resolverlo» | Regla 5 de CMP-BAJ-PRV |
| `MODALS.prvalta` | Reactivaba con un solo clic, sin los datos del formulario | Desde el alta, «Reactivar con estos datos» (conserva lo escrito); desde la ficha, un formulario con sus datos y el CUIT fijo | Postcondición c y regla 2 de CMP-ALT-PRV |
| `tabPrv` y `c_prvform` (rubros) | «Rubros» y chips como botones | «Categorías de insumos» (nombre de `TipoInsumo`) y casillas con buscador, solo categorías activas | Regla 3 de CMP-ALT-PRV; criterio del estudiante (buscadores) |
| `tabPrv` (acciones) | «Editar» siempre | «Editar»/«Reactivar» solo para el Gerente y según el estado; el Agrónomo no ve botones | Regla 5 de CMP-CNS-PRV; D-30 |
| `tabPrv` (filtros) | Filtros que se aplican al elegir | Botón «Filtrar» (nada se valida mientras se escribe), con «Quitar filtros» y estado vacío con filtros | `.claude/rules/interfaz.md`, «Validaciones e interacción HTMX» |
| `prvErr` (teléfono) | Mínimo 6 dígitos | Formato de D-21 (8 a 15 dígitos, hasta 25 caracteres) | Regla 1 de CMP-ALT-PRV; D-21 |
| `VIEWS.c_prv` | Tarjeta de órdenes y aviso «Correo con problemas» | Se omiten (todavía no hay órdenes ni envío de correos); tarjeta «Pedidos y órdenes de compra» con un texto de «todavía no hay» | CMP-02a a CMP-06; regla 4 de CMP-CNS-PRV |
| Estados vacíos y de error | No había estado vacío con filtros ni de «sin permiso» | Se agregaron, y el aviso de proveedor inactivo al abrir editar o baja a mano | D-61 punto 2 |
