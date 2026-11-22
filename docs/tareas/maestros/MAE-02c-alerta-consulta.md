# MAE-02c · Alerta: consulta (CU-46) y entrada «Alertas» del menú

Estado: pendiente | App: maestros | Rama: feature/mae-02c-alerta-consulta

Depende de: MAE-02b (hecha: `abrir_alerta`, D-43), UI-01 (estilo y marco, «Diseño v2», D-47) y NOT-01 (la campana, D-42).
Si alguna no está hecha, frená. **Antes de programarla, el estudiante aprueba las tres decisiones de «Decisiones previas».**

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por
paso. Si algo que necesitás no está en «Leer», frená (L9).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CU-46 | Consultar Alerta | docs/casos_de_uso/maestros/alertas.md | Solo existe la versión de alto nivel, completada en el extracto (R1 a R9). Sin origen de la alerta (R6) hasta que existan las apps de origen |

## Decisiones previas (para aprobar con la tarea; M6)

Las dos primeras están explicadas en el extracto, secciones «Contradicción registrada» y «Quién puede consultar». Esta tarea está
escrita con la **propuesta A** y con esas propuestas; si el estudiante elige otra cosa, se corrige este archivo antes de programar.

1. **Abrir el detalle marca «leída» (propuesta A):** manda la regla 7 de 8.18 sobre la postcondición de CU-46. El listado no cambia
   nada; solo el detalle llama a `abrir_alerta`.
2. **Quién consulta:** el Gerente y el Agrónomo (los únicos que reciben alertas). Cualquier otro rol: sin entrada de menú y 403 en
   las rutas.
3. **El detalle abre también una alerta resuelta** que el usuario recibe (la que llega por un enlace viejo), mostrándola como
   «Resuelta»; el listado solo trae las activas. CU-46 no dice nada de esto: es un supuesto de esta tarea.

## Leer

- Casos de uso: docs/casos_de_uso/maestros/alertas.md, completo (reglas R1 a R9, «Quién puede consultar» y «Contradicción
  registrada»)
- Modelo: docs/modelo/maestros.md — Alerta, completa (líneas 160 a 244 en `main`: atributos, R007, R049, regla 1 de 8.9 y regla 7 de
  8.18); Invernadero, solo «Reglas que lo tocan» (regla 3 de 8.22: las alertas de personal; el Agrónomo y las alertas, MD-61/MD-98)
- Decisiones: D-28, D-37, D-38, D-41, D-42, D-43, D-44, D-47
- API: docs/api/alertas.md — secciones 1 («Destinatarios»), 2 (`abrir_alerta` y los estados, líneas 73 a 119) y 5 («Consultar»,
  líneas 155 a 167). Se actualiza al cerrar (paso 5)
- Disparadores: docs/disparadores.md — «Cuando exista el caso de uso de consulta de alertas (CU-46) o el panel de IoT (CU-41)»,
  punto 1 (líneas 212 a 219), y «Cuando exista la primera notificación o alerta», punto 4 (líneas 55 a 59: el enlace de la campana)
- Temas abiertos: docs/temas_abiertos.md — las filas «Respaldo de severidad (MD-109)» (línea 151) y «Abrir una alerta desde la
  campana» (línea 156)
- Patrones: docs/patrones/trabajo_en_paralelo.md (`maestros/apps.py` y el menú, si se hace en paralelo con otra tarea de `maestros`)
- Pantallas: **no hay una pantalla de consulta en el prototipo** (extracto, «Pantallas»). Solo guía de orden y de niveles:
  docs/prototipos/produccion/datos_maestros_y_produccion.html — `alertas()` (líneas 866 a 877) y su uso en `shell` (línea 878).
  Estilo: «Diseño v2» (D-47), el de UI-01; el listado y los filtros se arman con los componentes de lista ya hechos en MAE-03 y
  MAE-04, sin estilos nuevos. Lo que difiera del caso de uso lo decide el caso de uso (L7)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código a leer: maestros/models.py (`Alerta`, el queryset con `para`, `activas` y `no_leidas`), maestros/alertas.py (`TipoAlerta`,
  `tipo_de_alerta`), maestros/servicios/alertas.py (`abrir_alerta`), maestros/servicios/invernaderos.py (`items_de_campana` e
  `ItemDeAlerta`), maestros/apps.py (`MaestrosConfig.ready()`), maestros/views.py y maestros/urls.py, core/menu.py (cómo se
  registra una entrada), y las plantillas de lista de `maestros` ya hechas (por ejemplo `cultivos/lista.html`)

## Límites

- Crea modelos: ninguno
- Migraciones: ninguna
- Permitido fuera de la app: docs/api/alertas.md (sección 5), docs/disparadores.md, docs/tareas/README.md,
  docs/tareas/ronda_produccion_1.md y docs/estado.md al cerrar (M3); core/templatetags/iconos.py solo si hace falta un ícono,
  copiado del prototipo. La entrada «Alertas» del menú se registra desde `MaestrosConfig.ready()`: no se toca `core/menu.py`
  salvo que la tarea no pueda registrarla de otro modo (en ese caso, frená y preguntá)
- Dependencias nuevas: ninguna
- Fuera de alcance: resolver o descartar una alerta desde la pantalla (las alertas se resuelven con el hecho que las originó);
  el origen de la alerta en el detalle (R6: Hardware, Telemetría, Merma y SolicitudRevisión no existen); el panel de IoT
  (CU-41); marcar «no leída»; búsqueda de texto libre; notificaciones y campana (D-42, ya hechas, salvo el enlace del paso 4);
  una pantalla para el Administrador

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Servicio de consulta, con las pruebas primero** (`maestros/servicios/alertas.py`; los nombres son una propuesta):
   `consultar_alertas(actor, *, invernadero_id=None, tipo=None)` y `filtros_de_alertas(actor)`.
   - `consultar_alertas` parte de `Alerta.objects.para(actor).activas()` (R2 y R3), filtra por invernadero y por tipo (R5) y ordena
     por severidad (crítica, advertencia, informativa) y, dentro de cada nivel, de la más reciente a la más antigua (R4). La
     severidad sale del tipo registrado y, si el código ya no está registrado, de la que se guardó con la alerta (misma
     regla que `items_de_campana`, MD-109). Trae `invernadero` con `select_related`: una consulta para toda la lista.
   - `filtros_de_alertas` devuelve las opciones de los dos filtros: los invernaderos y los tipos de las alertas activas del actor
     (no todos los invernaderos ni todos los tipos).
   - Un actor que no es Gerente ni Agrónomo activo recibe una lista vacía de `para`; la vista lo corta con 403 antes (paso 3).
   - Un invernadero o un tipo del filtro que no figura entre las alertas del actor da una lista vacía, sin error y sin revelar si
     existe.
   Pruebas: `maestros/tests/test_cns_alr.py`, clase `CnsAlrServicioTests`: una por regla y por postcondición (R1 a R5): alcance del
   Gerente, del Agrónomo con y sin invernadero a cargo, de un Capataz, un Vendedor, un Técnico, un Administrador y de una cuenta
   inactiva; solo activas (una resuelta no figura); filtro por invernadero, por tipo y por los dos; orden entre niveles y dentro de
   un nivel, con fechas iguales (desempate por id decreciente); tipo no registrado; sin consultas por fila (`assertNumQueries`).
   Alerta de un invernadero inactivo: R3 solo habla del estado de la alerta, así que la consulta **no agrega** un filtro por el
   estado del invernadero (si `para` ya lo hiciera, no lo cambies). Anotá en «Cierre» qué pasa, para `docs/temas_abiertos.md`.
2. **Datos del detalle, con las pruebas primero** (`maestros/servicios/alertas.py`): `detalle_de_alerta(actor, alerta_id)`. Llama a
   `abrir_alerta(actor, alerta_id)` (R7) y devuelve lo que muestra R6: tipo (nombre), severidad, descripción, invernadero, fecha y
   hora, estado, lectura **antes** de abrirla (para mostrar «Nueva» solo en esta visita) y destinatarios (Gerente, Agrónomo con su
   nombre, o ambos). No muestra el origen. `Http404` si la alerta no existe y `PermissionDenied` si el actor no la recibe, sin
   cambiar nada. Una alerta resuelta que el actor recibe **se puede abrir** (llega por un enlace viejo); el detalle la muestra
   como resuelta. Pruebas en `CnsAlrServicioTests`: lectura antes y después, que no cambia `estadoAlerta`, que una segunda apertura
   no falla, el 404 y el 403, y que abrir no deja registro en «Auditoría».
3. **Vistas y plantillas v2.** Rutas `/alertas/` (listado) y `/alertas/<id>/` (detalle), en `maestros/urls.py`. Listado: tabla con
   severidad (con el chip de color del estilo), descripción, invernadero, tipo, fecha y hora y un punto de «no leída»; filtros
   por invernadero y por tipo en un formulario GET (el respaldo sin JavaScript); con HTMX, el filtro reemplaza solo la tabla.
   Sin alertas: «No hay alertas activas.» (con filtros: «Ninguna alerta activa coincide con el filtro.»). Detalle: los campos de R6
   y el enlace «Ver invernadero» (la ficha, solo si el actor tiene acceso a ella; si no, sin enlace) y «Volver a alertas». Permisos
   (D-28): Gerente y Agrónomo activos; cualquier otro rol, 403; sin sesión, la redirección de siempre. Entrada «Alertas» del menú del
   Gerente y del Agrónomo, registrada en `MaestrosConfig.ready()`, con el contador de no leídas que ya da
   `Alerta.objects.para(usuario).activas().no_leidas()`. Pruebas: `CnsAlrVistaTests` en `maestros/tests/test_cns_alr.py`: permisos por
   rol, filtros con GET y con la petición HTMX (que devuelve solo la tabla), mensajes de lista vacía, que el listado **no** marca
   nada como leída, que el detalle sí, el 404 y el 403, y la entrada del menú por rol.
4. **La campana lleva al detalle.** `ItemDeAlerta.url` de `items_de_campana` apunta a `/alertas/<id>/` (cierra el punto 4 de
   «Cuando exista la primera notificación o alerta»): abrir una alerta desde la campana la marca «leída» y apaga el punto rojo.
   Las pruebas de `items_de_campana` que esperan la ficha del invernadero se ajustan (es un cambio de comportamiento pedido por
   esta tarea; anotalas en «Cierre»). Pruebas: en `maestros/tests/` donde ya estén las de `items_de_campana`, y una de punta a
   punta: crear una alerta para el Gerente, abrir su enlace de la campana, y que la cuenta de no leídas baje en uno.
5. **Documentación.** Proponé, sin aplicarlos (M3): la sección 5 de `docs/api/alertas.md` (nombrar `consultar_alertas`,
   `filtros_de_alertas` y `detalle_de_alerta` para que CU-41 las reutilice, y quitar «queda para otra tarea» y el pendiente de la
   postcondición, según la decisión 1); el tachado del punto 1 de «Cuando exista el caso de uso de consulta de alertas (CU-46)…» y del
   punto 4 de «Cuando exista la primera notificación o alerta» en `docs/disparadores.md`; el pendiente de pendientes_CU
   (postcondición de CU-46 ajustada, propuesta A); y lo que implementaste distinto de lo escrito, para `docs/temas_abiertos.md`.

Si el tiempo apremia, lo último que se recorta es el paso 4 (la campana): se anota como disparador y se hace aparte. Los pasos 1
a 3 no se recortan.

## Hecho cuando

- CU-46 está implementado: el listado muestra solo las alertas activas del actor, filtradas por invernadero y por tipo, ordenadas
  por urgencia; el detalle muestra la información completa y marca la alerta «leída» (decisión 1); el listado no cambia nada.
- Solo el Gerente y el Agrónomo activos ven la entrada «Alertas» y entran a las rutas; el resto recibe 403. El detalle de una alerta
  inexistente da 404 y el de una ajena, 403, sin cambiar nada.
- El listado y los filtros funcionan sin JavaScript; con HTMX, el filtro reemplaza solo la tabla.
- La campana lleva al detalle y apaga el punto rojo de lo abierto (paso 4).
- Una prueba por regla (R1 a R9 del extracto) y por postcondición, más las pruebas de vistas; ninguna prueba de `maestros`
  ni de `core` existente cambia salvo las de `items_de_campana` (paso 4).
- No hay migraciones ni modelos nuevos (`makemigrations --check --dry-run` sin cambios).
- Comando de pruebas:
  python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  (no hay pruebas de concurrencia nuevas: la consulta solo lee y `abrir_alerta` es una sola sentencia condicional; las de
  MAE-02a/02b siguen con `python manage.py test maestros core --keepdb --tag concurrencia`)

## Verificación a mano (la completa Claude Code al cerrar)

No hay migraciones: el despliegue de Render no cambia la base. Cuentas: un Gerente, dos Agrónomos (uno a cargo de «Sur» y otro de
«Norte»), un Capataz y un Administrador activos, y los invernaderos «Sur» y «Norte».

1. Como Gerente, dá de baja a un Capataz que esté a cargo de «Sur»: se crea la alerta «Invernadero sin Capataz activo». En el menú,
   «Alertas» muestra el contador en 1.
2. Entrá en «Alertas»: la lista muestra esa alerta, con su severidad, el invernadero «Sur» y un punto de «no leída». Seguís sin ver
   nada marcado como leído (el listado no cambia nada).
3. Filtrá por «Norte»: «Ninguna alerta activa coincide con el filtro.». Filtrá por «Sur» y por el tipo: vuelve a aparecer.
4. Abrí la alerta: el detalle muestra todo (tipo, severidad, descripción, invernadero, fecha y hora, activa, a quién le llegó). Volvé
   a la lista: el punto de «no leída» desapareció y el contador del menú bajó a 0. La alerta sigue activa.
5. Reactivá la cuenta del Capataz: la alerta pasa a resuelta y sale de la lista. Entrá otra vez al detalle por la URL guardada: se
   abre y dice «Resuelta».
6. Con el Agrónomo de «Sur»: «Alertas» muestra solo las suyas (con un Capataz de «Sur» dado de baja, ninguna: las de personal van al
   Gerente). Con el Agrónomo de «Norte», entrá por la URL a la alerta de «Sur»: **403**. A un id inexistente: **404**.
7. Como Capataz o Administrador: sin entrada «Alertas»; la URL `/alertas/` da 403.
8. La campana: con una alerta no leída, abrila desde la campana: te lleva al detalle y el punto rojo se apaga.
9. Sin JavaScript (desactivalo en el navegador): los filtros se envían con un botón «Filtrar» y la página se recarga completa.
10. Con una alerta creada por un tipo que ya no está registrado (por ejemplo, desde `/admin/` con `DJANGO_DEBUG=1`), la lista y la
    campana no se rompen y usan la severidad guardada.
11. `python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` pasa. Después, una
    vez, `python manage.py test maestros core --keepdb --tag concurrencia`.
12. Después del merge: no hay migraciones que verificar en el log de Render.

## Cierre

(Lo completa Claude Code al terminar la tarea: qué se hizo, archivos tocados, pruebas con su resultado, decisiones y diferencias
respecto de la documentación, para `docs/temas_abiertos.md`; nada se corrige en silencio.)
