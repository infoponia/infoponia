# MAE-02d · Enlace de cada alerta a la pantalla de su origen y filtro por varios tipos (D-62)

Estado: pendiente | App: maestros | Rama: feature/mae-02d-enlace-de-alertas | Ronda: — (la usan «Comercial 1» e «IoT 1»)

Depende de: **MAE-02c** (hecha, PR #47: `consultar_alertas`, `detalle_de_alerta`, las rutas `alertas:lista` y `alertas:detalle`, y la
campana que lleva al detalle). Si no está en `main`, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Por qué existe.** MAE-02c se programó con la versión de la PR #46, que no traía lo que pide **D-62**: el punto de extensión por el que cada
app dice adónde lleva su alerta, la ruta que la abre y redirige, y el filtro por varios tipos que usa el panel del IoT. Esta tarea lo agrega
sobre lo que ya está mergeado, **sin cambiar lo que MAE-02c ya hace** cuando ninguna app registró un enlace. Las reglas de cómo se aplica
D-62 sobre el código de `main` están en su **tercera enmienda** (22/11/2026). De ella dependen COM-03b (la primera alerta comercial) e IOT-04
(el panel del IoT).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CU-46 | Consultar Alerta (lo que faltaba: R6, el enlace del detalle; R9, varios tipos; R10, la campana) | docs/casos_de_uso/maestros/alertas.md | R1 a R5, R7 y R8 ya los hizo MAE-02c: no se tocan. Sin origen de la alerta en el detalle (R6) |

## Leer

- Casos de uso: docs/casos_de_uso/maestros/alertas.md — R6, R9, R10 y la sección «Enlace de cada alerta (D-62)», completa.
- Modelo: docs/modelo/maestros.md — Alerta (solo el párrafo «Regla 7 de 8.18»).
- Decisiones: **D-62** (con sus tres enmiendas), D-28, D-30, D-37 (A1 y A4), D-41, D-42, D-43, D-44.
- API: docs/api/alertas.md — secciones 5 («Consultar») y **8** («Enlace de una alerta»). Se actualizan al cerrar (paso 6).
- Disparadores: docs/disparadores.md — «Cuando exista la primera notificación o alerta», punto 4 (la línea «Queda para MAE-02d»).
- Temas abiertos: docs/temas_abiertos.md — la fila «MAE-02c en dos versiones» y «Abiertos desde MAE-02c (22/11/2026)» (solo para saber qué
  quedó afuera; ninguno se resuelve acá).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `maestros/extensiones.py` (el estilo de los registros), `maestros/servicios/alertas.py` (`consultar_alertas`,
  `detalle_de_alerta`, `DetalleDeAlerta`, `abrir_alerta`, `severidad_efectiva`), `maestros/servicios/invernaderos.py` (`items_de_campana`,
  `ItemDeAlerta`), `maestros/views.py` (`alertas` y `alerta`), `maestros/urls_alertas.py`, `maestros/templates/maestros/alertas/detalle.html`,
  y las pruebas `maestros/tests/test_cns_alr.py` y `maestros/tests/test_campana_alertas.py` (para no romperlas).

## Límites

- Crea modelos: ninguno.
- Migraciones: ninguna (`makemigrations --check --dry-run` sin cambios).
- Permitido fuera de la app: al cerrar (M3), `docs/api/alertas.md` (secciones 5 y 8), `docs/disparadores.md`, `docs/tareas/README.md`,
  `docs/temas_abiertos.md` y `docs/estado.md`. Nada de `core`: la ruta nueva va en `maestros/urls_alertas.py`, que ya está incluido en
  `config/urls.py` (y en `core/tests/urls_prueba_acceso.py`).
- Dependencias nuevas: ninguna.
- Fuera de alcance:
  - los cuatro valores nuevos de `Origen` (son de COM-03b, D-62 punto 1);
  - los enlaces reales de cada app (los registran COM-03b, COM-04b, COM-05a1 e IOT-04);
  - el origen de la alerta en el detalle (R6: sus apps todavía no existen);
  - el contador de la entrada «Alertas» del menú (disparador «Cuando exista el caso de uso de consulta de alertas…», punto 2);
  - los demás temas abiertos de MAE-02c.
- **Ninguna prueba existente de `maestros` ni de `core` cambia.** Si alguna falla, es porque cambiaste un comportamiento sin registrante: frená.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Punto de extensión del enlace (D-62, puntos 2 y 3), con las pruebas primero.**
   - En `maestros/extensiones.py`: `Enlace = namedtuple("Enlace", "url detalle")` y `registrar_enlace_de_alerta(codigos, funcion)`.
     `codigos` es una tupla de códigos de tipo; un código con dos registrantes lanza `ImproperlyConfigured` al registrar. Una lista de módulo
     (`_ENLACES`) que las pruebas reemplazan con `mock.patch.object`, como las demás.
   - En `maestros/servicios/alertas.py`: `enlaces_de_alertas(usuario, alertas) -> dict[int, Enlace]`, con **todas** las claves:
     - agrupa las alertas por registrante (según su `tipo_alerta`) y llama **una vez** a cada uno con su lista;
     - el registrante devuelve `dict[int, Enlace]`; una alerta que no devuelve, o un tipo sin registrante, usa el **enlace por omisión**:
       `Enlace(reverse("alertas:detalle", args=[alerta.pk]), alerta.invernadero.nombre_invernadero)` (D-62, segunda enmienda);
     - `detalle=None` del registrante usa el texto de omisión con el `url` del registrante;
     - lista vacía: `{}` sin consultar la base.
   - El registrante decide adónde lleva **a ese usuario**; nunca a una pantalla que le dé 403 (D-62, punto 4). Eso lo prueba cada app.
   Pruebas: `maestros/tests/test_enlaces_de_alertas.py`: sin registrante, todas por omisión (url del detalle y nombre del invernadero); con un
   registrante falso, su enlace y su texto, y el de omisión para la alerta que no devuelve; `detalle=None`; dos registrantes del mismo código
   (`ImproperlyConfigured`); dos registrantes de códigos distintos, cada uno con lo suyo; una llamada por registrante (no por alerta) y
   `assertNumQueries` igual con una y con tres alertas; lista vacía con `assertNumQueries(0)`.
2. **Filtro por varios tipos (R9), con las pruebas primero.** `consultar_alertas(actor, *, invernadero_id=None, tipo=None, tipos=None)`:
   - `tipo` sigue como está (la pantalla de CU-46, que pasa uno o ninguno: **no cambies la vista**);
   - `tipos` (una lista o tupla de códigos, la del panel del IoT): `None` no filtra; una lista vacía da `[]` sin consultar la base;
   - con `tipo` y `tipos` a la vez se cumplen los dos (el código tiene que ser `tipo` **y** estar en `tipos`);
   - el orden, el `select_related` y el resto, sin cambios.
   Pruebas: en `CnsAlrServicioTests` (`maestros/tests/test_cns_alr.py`), clases o métodos nuevos, sin tocar los existentes: por varios tipos;
   por varios tipos y un invernadero; `tipos=[]`; `tipo` y `tipos` combinados (coinciden y no coinciden); un código de `tipos` que no figura
   entre las alertas del actor.
3. **El enlace en el detalle (R6), con las pruebas primero.** `DetalleDeAlerta` suma el campo `enlace` **al final** (el `Enlace` de
   `enlaces_de_alertas` para esa alerta y ese actor). En `detalle.html`, si `enlace.url` no es el del propio detalle, una fila nueva
   «Dónde se atiende» con `<a class="link" href="{{ enlace.url }}">{{ enlace.detalle }}</a>`, después de «Invernadero». Con el enlace por
   omisión, la pantalla queda exactamente como hoy.
   Pruebas: en `CnsAlrServicioTests`, el enlace por omisión y el de un registrante falso; en `CnsAlrVistaTests`, que la fila aparece solo con
   un registrante y que su `href` es el del registrante.
4. **La ruta que abre y redirige (D-62, primera enmienda; tercera, puntos 2 y 3).** `alerta_ir` en `maestros/views.py`, ruta
   `<int:alerta_id>/ir/` en `maestros/urls_alertas.py`, nombre **`alertas:ir`**:
   - solo GET (como el detalle: HEAD da 405) y `never_cache`; mismos permisos que el detalle (Gerente y Agrónomo activos; otro rol, 403; sin
     sesión, la redirección de siempre);
   - llama a `abrir_alerta(request.user, alerta_id)` (404 si no existe; 403 si el usuario no la recibe, **sin marcar nada**) y redirige
     (302) al `url` de `enlaces_de_alertas(request.user, [alerta])`;
   - si el `url` no empieza con una sola `/` (por ejemplo, vacío o `https://…`), redirige al detalle: `alertas:ir` nunca saca del sitio
     (`url_has_allowed_host_and_scheme` con `allowed_hosts={request.get_host()}`).
   Pruebas: `maestros/tests/test_alerta_ir.py` (`AlertaIrVistaTests`): con un registrante falso, redirige a su `url` y la alerta queda
   «leída»; sin registrante, redirige al detalle; 404; 403 sin marcar nada; un Capataz, 403; un `url` externo del registrante, al detalle;
   HEAD, 405.
5. **La campana (R10; D-62, tercera enmienda, punto 3).** `items_de_campana` toma el `detalle` del `Enlace` (una llamada a
   `enlaces_de_alertas` para toda la lista) y su `url` es:
   - el del detalle (`alertas:detalle`) cuando el enlace es el de omisión, **como hoy**: el detalle ya abre la alerta y muestra «Nueva»;
   - `alertas:ir` cuando el enlace es de una app: abre la alerta y lleva en un clic a donde se atiende.
   Sin registrantes, `items_de_campana` devuelve exactamente lo mismo que hoy (las pruebas de `test_campana_alertas.py` no cambian).
   Pruebas, en `maestros/tests/test_campana_alertas.py` (métodos nuevos): con un registrante falso, `url` = `alertas:ir` y `detalle` = el del
   registrante; las demás alertas, como antes; `assertNumQueries` igual con una y con tres alertas de un tipo con registrante; de punta a
   punta: una alerta con registrante, abrir su `url` de la campana, que la cuenta de no leídas baje en uno y que la respuesta final sea la
   pantalla del registrante.
6. **Documentación.** Proponé, sin aplicarlos (M3): la sección 5 de `docs/api/alertas.md` con `tipos` y la 8 con lo que quedó (nombres
   reales y la regla de la campana); el tachado de la línea «Queda para MAE-02d» del punto 4 de «Cuando exista la primera notificación o
   alerta» en `docs/disparadores.md`; la fila de la tarea en `docs/tareas/README.md`; la fila «MAE-02c en dos versiones» de
   `docs/temas_abiertos.md` como resuelta; y lo que implementaste distinto de lo escrito.

Si el tiempo apremia, lo último que se recorta es el paso 3 (la fila del detalle); se anota como disparador. Los pasos 1, 2, 4 y 5 no se
recortan: COM-03b e IOT-04 los necesitan.

## Hecho cuando

- Una app puede registrar, por código de tipo, adónde lleva cada alerta y qué texto va debajo del título; sin registrante, todo se ve como
  con MAE-02c.
- `consultar_alertas` filtra por varios tipos (`tipos`), además de por uno (`tipo`).
- La campana lleva en un clic a la pantalla del origen (pasando por `alertas:ir`, que marca la alerta «leída»), o al detalle si la app no
  registró un enlace.
- El detalle muestra «Dónde se atiende» cuando la alerta tiene un enlace de una app.
- Ninguna prueba existente cambia; las nuevas cubren los pasos 1 a 5.
- No hay migraciones ni modelos nuevos.
- Comando de pruebas:
  python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

No hay migraciones: el despliegue de Render no cambia la base. Todavía ninguna app registra un enlace (lo hacen COM-03b en adelante e IOT-04),
así que la verificación a mano comprueba que **nada cambió** y que la ruta nueva funciona con el enlace por omisión.

1. Como Gerente, generá la alerta «Invernadero sin Capataz activo» (dando de baja a un Capataz a cargo). Desde la campana, abrila: te lleva al
   detalle (como antes), que muestra «Nueva», y el punto rojo se apaga. El detalle **no** tiene la fila «Dónde se atiende».
2. Escribí en la barra `/alertas/<id>/ir/` con el id de esa alerta: te redirige al detalle.
3. Con un Agrónomo de otro invernadero, la misma URL: 403. Con un id inexistente: 404.
4. «Alertas» y sus filtros funcionan igual que antes.
5. `python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` pasa.

## Cierre (la completa Claude Code al cerrar)
