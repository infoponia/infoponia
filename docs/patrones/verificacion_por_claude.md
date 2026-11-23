# Patrón · Verificación hecha por Claude Code (D-95)

Reemplaza a la «Verificación a mano» y a los datos de verificación (el cargador `cargar_datos_de_verificacion` se retiró). Lo que antes eran pasos para el
estudiante pasa a ser trabajo de Claude Code, que lo hace antes de cerrar la tarea y lo deja escrito en el «Cierre». Si algo de acá contradice a `CLAUDE.md`,
manda `CLAUDE.md`: avisá.

## Por qué

El estudiante prefiere dedicar su tiempo a implementar. Casi todo lo que verificaba a mano lo puede hacer una prueba (el flujo, los roles, los estados) y, para lo
visual, un navegador automatizado. Lo que una tarea posterior detecta y corrige sin costo no justifica una revisión manual; lo que **no** se corrige después
(una migración ya aplicada en Neon, datos de producción) sí se sigue cuidando (ver «Lo que no se automatiza»).

## Qué hace Claude Code antes de cerrar una tarea

| # | Qué | Cuándo | Dónde queda |
|---|---|---|---|
| 1 | **Recorrido** con el cliente de Django: cada paso que antes sería «a mano», en el orden en que lo haría una persona, por rol y por estado (con y sin datos, activo e inactivo, con error y sin él, rol sin permiso). | Siempre | `<app>/tests/test_recorrido_<tema>.py`, permanente (lo corre el CI) |
| 2 | **Visual** con un navegador real (Playwright + Chromium): el JavaScript y el HTMX funcionan, no hay errores de consola, el respaldo sin JavaScript anda, en un celular la página no se desborda, y **mirar las capturas** (la herramienta de lectura de imágenes) para detectar lo que una prueba no ve: estilos por defecto del navegador, textos cortados, alineaciones, botones que faltan. | Si la tarea tiene pantallas | `<app>/tests/test_visual_<tema>.py`, permanente (no corre en el CI) |
| 3 | **Migraciones:** `makemigrations --check`, `sqlmigrate` de la migración nueva (leer el SQL: que no borre ni reescriba datos) y aplicarla en la base de pruebas. Si hay migración de datos, su prueba `@tag("migracion")`. | Si la tarea tiene migración | Informe |
| 4 | **Informe en el «Cierre»**, sección «Verificación», con tres listas: **Verifiqué** (lo que hice, con el resultado), **Lo cubre una prueba** (nombre de la prueba) y **No pude verificar** (y por qué). Lo que no pudo verificar es lo único que le queda al estudiante, si decide mirarlo. | Siempre | Archivo de la tarea |
| 5 | **Pasos para replicar** (ver abajo): los pasos a mano con mucho detalle, para el estudiante, **opcionales**. | Al final de la ronda | Archivo de la tarea, mensaje de cierre y texto del PR |

Una captura que muestra algo mal es un hallazgo: se corrige (D-61, punto 2) y se anota en el «Cierre»; no se deja para después.

## El recorrido (con el cliente de Django)

- Una prueba larga a propósito (`RecorridoDe<Tema>Tests`): lo que se verifica es que el flujo completo **encadena** bien. Las reglas sueltas ya las prueban
  `test_<codigo_cu>.py` y `test_<tema>_vistas.py`.
- Cada paso lleva un comentario con el caso de uso y la regla que verifica. Ejemplo: `compras/tests/test_recorrido_proveedores.py`.
- Arma sus propios datos (`.claude/rules/pruebas.md`): no hay cargadores ni datos previos.

## Lo visual (Playwright)

**Lo usa Claude Code; el estudiante no necesita instalar ni correr nada de esto.** **Instalación (una vez, solo en desarrollo).** Playwright está permitido únicamente como dependencia de desarrollo (permiso del estudiante, 23/11/2026):
va en `requirements-dev.txt`, **nunca** en `requirements.txt` (que instalan el CI y Render).

```
pip install -r requirements-dev.txt
python -m playwright install chromium
```

**Cómo se corre.** Las pruebas visuales están apagadas por defecto (no entran en las corridas normales ni en el CI). Se activan con una variable de entorno y su etiqueta:

```
# PowerShell
$env:INFOPONIA_VISUAL = "1"; python manage.py test compras.tests.test_visual_proveedores --keepdb --tag visual; Remove-Item Env:INFOPONIA_VISUAL
# Bash (la herramienta de Claude Code)
INFOPONIA_VISUAL=1 .venv/Scripts/python.exe manage.py test compras.tests.test_visual_proveedores --keepdb --tag visual
```

Las capturas van a `INFOPONIA_CAPTURAS` (si se define) o a la carpeta temporal `infoponia_capturas`; Claude Code las deja en su carpeta temporal de la sesión y las mira.

**Cómo se escribe** (`core/tests/visual.py`, clase `PruebaVisual`; ejemplo: `compras/tests/test_visual_proveedores.py`):

- Hereda de `PruebaVisual`, que levanta el sistema de verdad en **su propia base de pruebas** (nunca toca la base local de desarrollo ni la de Neon) y da `nueva_pagina()`,
  `entrar(pagina, cuenta)`, `capturar(pagina, nombre)`, `assertSinScrollHorizontal` y `assertSinErroresDeJavaScript`.
- En `setUp` vuelve a asegurar los datos de las migraciones (`asegurar_datos_de_inventario()` y `asegurar_datos_de_maestros()`), porque el `flush` de cada prueba los vacía
  (`docs/patrones/datos_de_migracion.md`). Las cuentas y los datos los arma la propia prueba con las fábricas.
- Inicia sesión por el formulario real; nunca escribe una contraseña propia (usa la de las fábricas de prueba).
- Pruebas mínimas por pantalla: los elementos interactivos (lo que hace JavaScript o HTMX), un rol sin permiso, un celular (`ANCHO_DE_CELULAR`) y sin JavaScript
  (`nueva_pagina(javascript=False)`).

## Pasos para replicar (para el estudiante, opcionales)

Al final de una ronda, cuando Claude Code da el mensaje de commit y la propuesta de M3, **siempre** le entrega al estudiante los pasos de verificación a mano, **aunque este no tenga tiempo de hacerlos**, para que pueda replicarlos si se hace tiempo. No hay
revisiones pendientes ni nada que tachar: son una ayuda. Quedan en la sección «Verificación» de la tarea, en el mensaje de cierre y en el texto del PR. Cómo se escriben:

- **Antes de empezar:** cómo preparar el entorno (`migrate`, `runserver`, la dirección local, con qué cuenta entrar y qué rol necesita). Como ya no hay datos cargados, **qué hay que crear a mano** y con qué valores concretos (por ejemplo, un CUIT válido de ejemplo), en el orden en que se crean.
- **Cada paso numerado** dice: dónde está (menú y pantalla), qué hacer (qué tocar y qué escribir, con valores de ejemplo), **qué tiene que ver** (el aviso exacto, el error junto al campo, qué aparece o desaparece) y, si corresponde, dónde se comprueba el efecto (por ejemplo, el registro en «Auditoría»).
- **Cubre**, en este orden: el camino feliz; cada error de validación importante; cada estado (activo e inactivo, con y sin datos); cada rol (el que puede, el que solo consulta y el que no tiene acceso: qué ve y qué pasa por la dirección escrita a mano); y, al final y marcados como opcionales, sin JavaScript y en un celular.
- **Marca lo que ya cubre una prueba** (por ejemplo, «lo cubre el recorrido») para que quien tenga poco tiempo se concentre en lo que se ve y se siente.
- **Es autocontenido:** quien lo lee no necesita haber visto la sesión, ni el código ni este patrón.

## Lo que no se automatiza (sigue siendo del estudiante, y solo si lo decide)

- **Despliegue:** que Render aplicó las migraciones (log de Render) y que la pantalla abre en producción.
- **Envío real de correo** y cualquier servicio externo (Georef, almacenamiento): las pruebas usan los servicios simulados.
- **Datos de producción:** si una migración de datos toca filas existentes en Neon, conviene probarla antes contra una copia (`docs/patrones/datos_de_migracion.md`).
- **Criterio de producto:** si una pantalla «se siente bien» para quien la va a usar; las capturas solo detectan lo que está objetivamente mal.

Todo esto va, si corresponde, en «No pude verificar» del «Cierre».

## Qué reemplaza

- La sección «Verificación a mano» de cada tarea (las 69 tareas que ya la tienen no se reescriben): si una tarea la trae, se convierte en recorridos.
- Los cargadores de datos (`<app>/verificacion.py`), `core/verificacion.py`, el comando `cargar_datos_de_verificacion` y sus pruebas: **retirados** (D-95). Si una tarea los nombra, se ignoran.
- `docs/revisiones_pendientes.md` y la regla M5: congelados; lo anotado ahí queda como historial.
