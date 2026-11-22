# Casos de uso · maestros · alertas

Copia para el repo del caso de uso **CU-46 · Consultar Alerta**, tomado del documento de alto nivel «Documentación para la IA»
(Drive). **Es la única versión que existe:** CU-46 no tiene todavía una versión extendida en «CU extendidos» (no hay precondiciones
ampliadas, flujo, extensiones ni reglas). Este archivo la completa con lo ya decidido en el repo (supuestos de MAE-02b, regla 7 de
8.18, D-41, D-42 y D-43) y deja marcado lo que es **propuesta a aprobar** (M6). Si este archivo y el documento de Drive no
coinciden, avisá: no elijas en silencio.

Ubicación: `docs/casos_de_uso/maestros/alertas.md`. Tarea que lo implementa: `docs/tareas/maestros/MAE-02c-alerta-consulta.md`.

Para nombrar las pruebas: no hay reglas numeradas; las reglas de abajo se numeran R1 a R9 para este archivo. La clave del caso de uso
(`XXX-CNS-ALR`) está por definir al extenderlo; el repo propone `test_cns_alr.py` (MAE-02b) para sus pruebas.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| CU-46 | Consultar Alerta | Agrónomo o superior (ver «Quién puede consultar») | `maestros/tests/test_cns_alr.py` |

## CU-46 · Consultar Alerta

### Texto del caso de uso de alto nivel (copiado sin cambios)

| CU-46 | Consultar Alerta |
|---|---|
| **Actores:** | Usuarios con el rol de Agrónomo o superior |
| **Objetivo:** | Consultar el listado de alertas generadas por el sistema que se encuentran en estado «activa», buscar una en particular y acceder a la información completa de la misma. |
| **Precondición:** | a. El usuario está autenticado en el sistema con rol Agrónomo o superior. |
| **Postcondición:** | No se produjeron cambios en el sistema. |

Fuente: «Documentación para la IA», CU-46. Es un caso de uso preliminar de alto nivel (D-44, fuentes de verdad: pesa menos que el
modelo de dominio y que las decisiones del repo).

### Reglas aplicadas en el repo (decididas; salen del modelo y de las decisiones)

- **R1. Quién recibe (regla 1 de 8.9; R007 y R049).** Una alerta tiene como destinatario al Gerente (`para_gerente`), al Agrónomo
  del invernadero (`agronomo`) o a los dos, según su tipo (tabla de destinatarios de `docs/api/alertas.md`, sección 1). Otros roles
  no reciben alertas.
- **R2. Alcance (D-28, `docs/api/alertas.md` sección 5).** Se consulta con `Alerta.objects.para(usuario)`, el único lugar del
  alcance: el Gerente activo ve las suyas (`para_gerente`), el Agrónomo activo, las de él, y cualquier otro rol, una cuenta inactiva
  o ninguna cuenta, ninguna.
- **R3. Solo las activas.** El listado muestra las alertas con `estadoAlerta = activa` (`.activas()`). Las resueltas no figuran.
- **R4. Orden.** Más urgente arriba: crítica, advertencia, informativa; dentro de cada nivel, la más reciente primero (criterio de
  `alertas()` del prototipo; MD-109 fija que la severidad la define el tipo y se guarda con la alerta).
- **R5. Filtros.** Por invernadero y por tipo de alerta (supuesto de MAE-02b, anotado en `docs/disparadores.md`). Son la «búsqueda de
  una en particular» del objetivo; no hay búsqueda de texto libre.
- **R6. Información completa.** El detalle muestra: tipo, severidad, descripción, invernadero, fecha y hora, estado (activa), lectura
  (no leída / leída) y a quién le llegó (Gerente, Agrónomo o ambos). El **origen** (hardware, telemetría, solicitud de revisión,
  merma) no se muestra hasta que exista su app (`docs/disparadores.md`, «Cuando exista Hardware, Telemetría, Merma o
  SolicitudRevisión»).
- **R7. Abrir el detalle llama a `abrir_alerta(actor, alerta_id)`** (regla 7 de 8.18, MAE-02b, D-43): un destinatario la abre y su
  lectura pasa a «leída». No toca `estadoAlerta`, no audita y no bloquea el invernadero. `Http404` si la alerta no existe y 403
  (`PermissionDenied`) si el usuario no la recibe (D-28). **Propuesta (a aprobar):** el detalle también abre una alerta ya resuelta que
  el usuario recibe (llega por un enlace viejo) y la muestra como «Resuelta»; el listado solo trae las activas.
- **R8. Sin JavaScript.** Funciona completo sin JavaScript; HTMX solo reemplaza la tabla al filtrar (D-47, `.claude/rules/interfaz.md`).
- **R9. Dónde vive.** En `maestros` (la entidad `Alerta` es de `maestros`, D-38). La consulta de alertas del panel de IoT (CU-41)
  reutiliza la función de consulta (`docs/disparadores.md`, «Cuando exista… (CU-41)»).

### Quién puede consultar

El caso de uso dice «Agrónomo o superior». En el repo, `Alerta.objects.para(usuario)` solo entrega alertas al Gerente y al Agrónomo
(R1 y R2). **Propuesta (a aprobar):** la entrada «Alertas» del menú y las rutas son del Gerente y del Agrónomo; un Administrador, un
Capataz, un Vendedor o un Técnico no la ven y reciben 403 si entran por la URL. Un Administrador no tiene alertas propias que
consultar, y darle una pantalla vacía no aporta. Si el equipo quiere que el Administrador la vea, hay que decidir **qué** vería
(ninguna, o todas) y cambiar el alcance (no es un cambio de esta tarea).

### Contradicción registrada: «no se produjeron cambios» frente a «leída» (decidir antes de programar)

- La postcondición de CU-46 dice «No se produjeron cambios en el sistema».
- La regla 7 de 8.18 (modelo de dominio, ronda 17, texto copiado el 19/11/2026) dice que `estadoLecturaAlerta` pasa a «leída» cuando
  un destinatario **abre** la alerta. MAE-02b implementó `abrir_alerta` así y dejó el pendiente «sin resolver» para pendientes_CU.
- Peso de las fuentes (`CLAUDE.md`): el modelo (2) manda sobre un caso de uso original o de alto nivel (4).
- **Propuesta A (recomendada):** manda el modelo. Abrir el detalle marca «leída»; el listado **no** cambia nada. La postcondición de
  CU-46 se ajusta a: «Solo cambia el estado de lectura de la alerta que el usuario abre; el listado y la búsqueda no cambian nada».
  Motivo: sin esto la campana (que cuenta las no leídas) no se apagaría nunca y la regla 7 quedaría sin uso.
- **Alternativa B:** CU-46 manda; abrir no marca nada y se agrega una acción explícita «Marcar como leída». Exige cambiar la
  regla 7 de 8.18 y `abrir_alerta` (ya mergeada).
- Hasta que el estudiante elija, la tarea MAE-02c **no se programa** (se anota en el cierre de documentación). La propuesta A
  deja el cambio en pendientes_CU (CU-46, postcondición) y en la regla 7 de 8.18 no hace falta tocar nada.

## Pantallas

Guía visual: `docs/prototipos/produccion/datos_maestros_y_produccion.html`. **El prototipo no tiene una pantalla de consulta de
alertas**: solo las muestra dentro de la campana (`shell` y `alertas()`) y dentro de la ficha del invernadero. La pantalla de
CU-46 se arma con el estilo «Diseño v2» (D-47) y los patrones de lista del sistema, sin un prototipo propio; la tarea MAE-02c
describe el diseño en palabras. Lo que sí sirve del prototipo es el orden por urgencia y los textos de cada alerta (`alertas()`).

| Pantalla | Función en el prototipo | Casos de uso |
|---|---|---|
| Campana: lista de alertas por urgencia (solo guía del orden y de los niveles `danger`, `warn`, `info`) | `shell`, `alertas`, `RK` | CU-46 (orden) |
| Lista de alertas con filtros y detalle | Ninguna | CU-46 |

## Para más adelante

- **Origen de la alerta en el detalle (R6):** cuando existan Hardware, Telemetría, Merma o SolicitudRevisión; va por un punto de
  extensión (`docs/disparadores.md`, «Cuando exista Hardware, Telemetría, Merma o SolicitudRevisión»).
- **Panel de alertas de IoT (CU-41):** reutiliza la consulta de R2 a R5.
- **Extender CU-46:** al pasar a «CU extendidos» hay que escribir precondiciones, flujo, extensiones y reglas; este archivo se
  reemplaza entonces por la copia fiel.

## Solo prototipo

Nada: el prototipo no tiene esta pantalla.
