# Patrón · Verificación a mano, con el recorrido por prueba (D-96)

Cómo se verifica una tarea antes de darla por cerrada. Reemplaza a `verificacion_por_claude.md` (D-95): el estudiante vuelve a verificar a mano, **sin navegador automatizado ni capturas**, y los datos de
prueba los crea él (los cargadores no vuelven). Si algo de acá contradice a `CLAUDE.md`, manda `CLAUDE.md`: avisá.

## Qué hace cada uno

| # | Quién | Qué | Dónde queda |
|---|---|---|---|
| 1 | Claude Code | El «Comando de pruebas» de la tarea (M1). | «Cierre» |
| 2 | Claude Code | **Recorrido** con el cliente de Django: cada paso del flujo, en el orden en que lo haría una persona, por rol y por estado (con y sin datos, activo e inactivo, con error y sin él, rol sin permiso). Lo corre el CI. | `<app>/tests/test_recorrido_<tema>.py` |
| 3 | Claude Code | **Migraciones**, si la tarea tiene: `makemigrations --check`, `sqlmigrate` de la nueva (leer el SQL: que no borre ni reescriba datos) y aplicarla en la base de pruebas. Si hay migración de datos, su prueba `@tag("migracion")`. | «Cierre» |
| 4 | Claude Code | **Informe** en el «Cierre», con tres listas: **Verifiqué** (el recorrido y las migraciones, con su resultado), **Lo cubre una prueba** (nombre de la prueba) y **No pude verificar** (y por qué). | Archivo de la tarea |
| 5 | Claude Code | **Verificación a mano**: los pasos para el estudiante, con mucho detalle (abajo). Se anotan en `docs/revisiones_pendientes.md` (M5). | Archivo de la tarea, `revisiones_pendientes.md`, texto del PR |
| 6 | El estudiante | Hace los pasos y los tacha en `revisiones_pendientes.md` (y en `estado.md`) en el mismo commit o PR. | `revisiones_pendientes.md` |

Claude Code **no abre un navegador ni mira capturas** y no deja la base local cargada: no toca la base local de desarrollo.

## El recorrido (con el cliente de Django)

- Una prueba larga a propósito (`RecorridoDe<Tema>Tests`): lo que se verifica es que el flujo completo **encadena** bien. Las reglas sueltas ya las prueban `test_<codigo_cu>.py` y `test_<tema>_vistas.py`.
- Cada paso lleva un comentario con el caso de uso y la regla que verifica. Ejemplos: `compras/tests/test_recorrido_proveedores.py` y `compras/tests/test_recorrido_pedidos.py`.
- Arma sus propios datos (`.claude/rules/pruebas.md`): no hay cargadores ni datos previos.
- Si una vista deja correos para `transaction.on_commit`, en un `TestCase` hay que ejecutarlos (`captureOnCommitCallbacks`) o reemplazar `on_commit` por una llamada inmediata, porque la prueba entera vive dentro de una transacción.

## La verificación a mano (la escribe Claude Code, la hace el estudiante)

Va en la sección «Verificación a mano» del archivo de la tarea, y se copia (una línea por paso, con casilla) a `docs/revisiones_pendientes.md`. Cómo se escribe:

- **Antes de empezar:** cómo preparar el entorno (`migrate`, `runserver`, la dirección local, con qué cuenta entrar y qué rol necesita). Como no hay datos cargados, **qué hay que crear a mano** y con qué valores concretos
  (por ejemplo, un CUIT válido de ejemplo), en el orden en que se crean. Nunca una contraseña en un archivo del repo (es público).
- **Cada paso numerado** dice: dónde está (menú y pantalla), qué hacer (qué tocar y qué escribir, con valores de ejemplo), **qué tiene que ver** (el aviso exacto, el error junto al campo, qué aparece o desaparece) y, si
  corresponde, dónde se comprueba el efecto (por ejemplo, el registro en «Auditoría»).
- **Cubre**, en este orden: el camino feliz; cada error de validación importante; cada estado (activo e inactivo, con y sin datos); cada rol (el que puede, el que solo consulta y el que no tiene acceso: qué ve y qué
  pasa por la dirección escrita a mano); y, al final y marcados como opcionales, sin JavaScript y en un celular.
- **Marca lo que ya cubre una prueba** (por ejemplo, «lo cubre el recorrido») para que quien tenga poco tiempo se concentre en lo que se ve y se siente.
- **Es autocontenido:** quien lo lee no necesita haber visto la sesión, ni el código ni este patrón.

### El paso de «navegador real» (obligatorio en las tareas con pantallas)

El cliente de Django **no ve** lo que hace un navegador: el CSRF y el encabezado `Origin`, los encabezados de seguridad, el JavaScript ni el aspecto. Por eso, si la tarea tiene **pantallas públicas (sin cuenta) o formularios
que se envían**, la verificación a mano lleva un paso que dice, con estas palabras o parecidas:

> **Navegador real.** Abrí la pantalla en una **ventana privada** (sin sesión), completá el formulario y **enviálo hasta el final**; después volvé a abrirla. Tiene que mostrar el resultado esperado. Si aparece una página
> «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver.

Es el paso que habría encontrado el defecto de CMP-02a (`Referrer-Policy: no-referrer` hace que el navegador mande `Origin: null` y Django rechaza el envío; D-88, corregida). Si la pantalla tiene JavaScript propio
(buscadores, ventanas, HTMX), el paso también dice qué probar con JavaScript desactivado.

## Lo que sigue siendo del estudiante, si lo decide

- **Despliegue:** que Render aplicó las migraciones (log de Render) y que la pantalla abre en producción.
- **Envío real de correo** y cualquier servicio externo (Georef, almacenamiento): las pruebas usan los servicios simulados.
- **Datos de producción:** si una migración de datos toca filas existentes en Neon, conviene probarla antes contra una copia (`docs/patrones/datos_de_migracion.md`).
- **Criterio de producto:** si una pantalla «se siente bien» para quien la va a usar.

Todo esto va, si corresponde, en «No pude verificar» del «Cierre».
