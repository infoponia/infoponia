# API · Notificaciones (`core/notificaciones.py`)

Contrato de D-42. Lo implementa NOT-01; las demás tareas la usan sin leer el código de `core`. Si algo de acá no alcanza,
frená (L9): no inventes otra forma de avisar.

## Modelo

`core.Notificacion`: `destinatario` (FK a `Usuario`), `titulo` (hasta 120), `detalle` (hasta 500), `fecha_hora`, `leida`
(falso al crear). Se ordena de la más reciente a la más antigua.

## Funciones

| Función | Qué hace | Devuelve |
|---|---|---|
| `notificar(destinatario, titulo, detalle)` | Crea una notificación para una cuenta (`Usuario` o cualquiera de sus roles). Falla con `ValueError` si el título o el detalle están vacíos o pasan el largo | la `Notificacion` |
| `notificar_al_gerente(titulo, detalle)` | La crea para el Gerente activo. **Sin Gerente activo no hace nada y no falla** (D-14) | la `Notificacion` o `None` |
| `notificar_a_varios(cuentas, titulo, detalle, *, excluir=None)` | Una por cuenta, sin repetir cuentas, sin la cuenta `excluir` (el actor) y sin `None` en la lista (un rol sin responsable) | lista de `Notificacion` |
| `de_la_cuenta(usuario)` | Las del usuario, más recientes primero (las usa la campana) | `QuerySet` |
| `marcar_vistas(usuario, ids)` | Marca como leídas las del usuario con esos ids. Ignora las ajenas | cantidad marcada |

## Reglas de uso

1. Se llaman **dentro de la transacción del caso de uso**, después de los cambios y antes de salir: si el caso de uso falla, no
   queda ninguna notificación.
2. No se auditan (D-42). El registro de auditoría del caso de uso no lleva el texto del aviso.
3. El texto lo arma quien notifica, con nombres y no con ids. Ejemplo: título «Quedó a cargo de Invernadero Norte»; detalle
   «El Gerente lo asignó como Agrónomo. Recibe: 2 órdenes a realizar.»
4. Notificar al propio actor es un error de uso: se pasa como `excluir`.
5. Un caso de uso que notifica a «cada Agrónomo de los invernaderos que usan X» arma la lista de cuentas y llama una vez a
   `notificar_a_varios`.

## Campana: fuentes de alertas (`core/extensiones.py`)

`registrar_fuente_de_alertas(funcion)`, con `funcion(usuario) -> list[ItemDeAlerta]`. `ItemDeAlerta` es un `namedtuple`
(`severidad`, `titulo`, `detalle`, `url`, `leida`). `severidad` es `critica`, `advertencia` o `informativa`. Cada app lo registra en
`AppConfig.ready()`. `core` ordena por severidad y no importa a quien registra.

## Pendientes del Gerente (`core/extensiones.py`)

`registrar_contador_de_pendientes(funcion)`, con `funcion() -> list[tuple[str, int]]` (descripción y cantidad; sin nada
pendiente, lista vacía). `pendientes_del_gerente()` (en `core/notificaciones.py`) devuelve `(total, detalle)`: el total y la lista
de `(descripción, cantidad)` con cantidad mayor que cero. Lo usan USR-ALT-USR (postcondición d) y USR-BAJ-USR (postcondición c).

Los textos aprobados: título «Quedó a cargo de <invernadero>»; detalle «El Gerente le asignó el rol de <rol>. [Recibe: <descripción>: <n>, … | No recibe nada pendiente.]»; «Pendientes que esperan al Gerente» / «Tiene N pendiente(s). <desc>: <n>.» / «No tiene pendientes.»; ventana de baja «Pendientes del Gerente: N (…). Quedan esperando hasta el alta de otro Gerente; la baja no se bloquea por ellos.».
El Administrador no tiene campana (D-42 decía «todos los roles»).
estado_de_la_campana y contadores_de_pendientes como funciones de la API.
El texto se valida (con contenido, recortado) aunque no haya destinatarios.
El título del ejemplo de la API pasa a «El Gerente le asignó el rol de Agrónomo.».