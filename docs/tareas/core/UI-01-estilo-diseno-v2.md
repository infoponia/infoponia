# UI-01 · Estilo «Diseño v2» (D-47): hoja de estilos, marco y pantallas ya hechas

Estado: hecha, a la espera de la revisión a mano | App: core (toca las plantillas y los estilos de `maestros`) | Rama: feature/ui-01-estilo-v2 | Ronda: Producción 1

Depende de: — (es la primera de la ronda). MAE-02b ya está mergeada (PR #32, 19/11/2026): sus plantillas y su Inicio del Gerente se adaptan acá.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

## Casos de uso incluidos

Ninguno: no cambia reglas de negocio. Es un cambio de aspecto y de marco que habilita a todas las tareas siguientes.

## Leer

- Decisiones: D-24, D-25, D-29, D-47, D-48 (la parte de `core/extensiones.py` y de `core/identidad.py`)
- Regla: .claude/rules/interfaz.md (estilo = Diseño v2) y .claude/rules/pruebas.md
- Prototipo: docs/prototipos/produccion/datos_maestros_y_produccion.html — **solo el `<style>` (líneas 9 a 561)**, la función
  `shell` (878) y `toast`. No se lee el resto (L6)
- Código a adaptar: core/static/core/css/infoponia.css, maestros/static/maestros/css/invernaderos.css,
  core/templates/core/base*.html, core/templatetags/iconos.py, core/context_processors.py, core/static/core/js/desplegable.js

## Límites

- Crea modelos: ninguno
- Migraciones: ninguna
- Permitido fuera de `core`: `maestros/static/maestros/css/invernaderos.css` y las plantillas de `maestros/templates/` (solo
  clases y estructura visual), incluidas las de MAE-02b (Inicio del Gerente y `maestros/templates/maestros/invernaderos/_inicio_personal.html`)
- Archivos nuevos: `core/identidad.py`
  (`nombre_de_la_organizacion()` e `identidad()`), una prueba en `core/tests/test_identidad.py`. **`core/extensiones.py` ya existe** (lo creó MAE-02b, D-43, con cuatro puntos de cuentas e Inicio): acá se le **agregan** `Identidad` y `registrar_identidad_de_la_organizacion`, sin tocar lo que hay
- Dependencias nuevas: ninguna. La fuente es Inter, ya servida desde `core/static/core/fuentes/`; se **quita DM Mono** (el estilo v2
  no usa letra de consola: los números alinean con `font-variant-numeric: tabular-nums`)
- Fuera de alcance: campana y notificaciones (NOT-01, aunque el marco deja el lugar del botón), pantallas nuevas de otras tareas,
  modo oscuro, el logo (D-45), el color de la organización (MAE-04 lo escribe; acá solo queda la consulta con valor por defecto)

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Inventario de clases.** Listá las clases CSS que usan las plantillas hoy y cuáles de ellas existen en el `<style>` del
   prototipo. Para cada una que cambió de nombre o de estructura, anotá el reemplazo en un comentario del PR. Pruebas: ninguna;
   la lista guía el paso 2.
2. **Hoja de estilos.** Reemplazá `infoponia.css` por el del prototipo (variables, componentes, tarjetas, tablas, insignias,
   barras de segmentos, modales, avisos) conservando lo que el sistema ya necesita y el prototipo no tiene (por ejemplo la
   clase `.sr`, el respaldo sin JavaScript y lo de `desplegable.js`). Una sola salvedad con el prototipo: sus filtros usan
   `<select>` nativo y D-24 lo descartó; los desplegables se siguen haciendo con el componente propio, con el aspecto v2.
   Variables: las del prototipo, sin renombrar, para que cualquier tarea pueda copiar su HTML. Quitá `--font-mono` y `.mono`.
   Los colores de tipo de etapa (`--st-germ`, etc., o como se llamen en el prototipo) quedan definidos acá aunque todavía
   nada los use. Pruebas: `python manage.py test core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`
   sigue verde.
3. **Marco.** Adaptá `base_con_sesion.html`, `base_sin_sesion.html` y `base.html` al marco de `shell`: cabecera con marca y
   nombre, menú lateral con los elementos del prototipo, `mnav` en pantallas angostas, pie, región de avisos y marco de celular
   para los roles de campo. Dejá en la cabecera el lugar del botón de la campana **vacío y comentado** (NOT-01 lo llena).
   El ícono de cada entrada sale de `iconos.py`: sumá los íconos del prototipo que falten (`leafmark`, `bell`, `grid`, `sprout`,
   `move`, `cut`, `tool`, `wifi`, `clock`, `warn`, `check`, `plus`, `eye`, `users`, `dash`, `leaf`; verificá cuáles existen).
   Pruebas: las de marco existentes de `core` (menú por rol, celular, sin sesión) pasan sin cambiar su lógica; las que
   verifican una clase CSS concreta se actualizan y se anota en el PR.
4. **Identidad de la organización (D-48).** Agregá a `core/extensiones.py` (que ya existe; usá su mismo estilo de registrante idempotente) `Identidad = namedtuple("Identidad", "nombre
   color_principal")`, `registrar_identidad_de_la_organizacion` e `identidad_registrada()`, y creá `core/identidad.py`
   (`nombre_de_la_organizacion()`, `color_principal()`, ambas con el valor por defecto de D-48). El procesador de contexto
   entrega `nombre_organizacion` y `color_principal`; el marco escribe el `<style>` con `--primary`, `--primary-dark` y
   `--primary-soft` **solo si el color cumple `^#[0-9a-fA-F]{6}$`**; los correos de `core/servicios.py` usan
   `nombre_de_la_organizacion()`. Sin registrante, todo se ve igual que antes. Pruebas: `core/tests/test_identidad.py`
   (sin registrante usa `NOMBRE_ORGANIZACION`; con un registrante falso usa su nombre; un color inválido no se escribe; un
   nombre vacío cae al valor por defecto; el correo usa el nombre registrado).
5. **Pantallas hechas.** Pasá al estilo v2 las pantallas de `core` (inicio de sesión, recuperación y elección de contraseña,
   invitación, inicio, Mi perfil, usuarios: lista, alta, ficha, modificar, ventanas; auditoría) y las de `maestros` hechas
   (lista de invernaderos, ficha, alta, modificar, baja, reactivar y las ventanas de confirmación). El contenido y la lógica no
   cambian; cambian el HTML y las clases para usar los componentes del prototipo (tarjeta con título, `facts`, insignias,
   `alert`, `footbar`). También el Inicio del Gerente de MAE-02b. La pantalla de alertas (CU-46) todavía no existe: es MAE-02c. Pruebas: las de vistas
   de cada pantalla pasan; las que verifican texto o estructura que el estilo cambió se ajustan, una por una, anotadas en el PR.
6. **Recorrida.** `python manage.py runserver` y recorré cada pantalla de la tabla de «Verificación a mano» en escritorio, a
   375 px de ancho y sin JavaScript. Corregí lo que se vea roto. Anotá en el PR qué pantallas quedaron revisadas.

Si el tiempo apremia, lo último que se recorta es la adaptación de las pantallas de auditoría y de usuarios del Administrador
(se anota como disparador y se hace en la tarea que las toque).

## Hecho cuando

- Todas las pantallas existentes usan el estilo v2 (mismas variables, mismo marco) y no queda ninguna referencia a DM Mono ni
  a `.mono`.
- `core/extensiones.py` tiene la API de identidad de D-48 (sin cambiar los cuatro puntos de D-43), `core/identidad.py` existe y sus pruebas pasan.
- El marco deja el lugar de la campana y el menú sigue siendo por rol.
- Suites completas de `core` y `maestros` en verde:
  python manage.py test core maestros --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
- Una persona que no conoce el cambio no ve ninguna pantalla con el aspecto viejo (verificado en la recorrida).

## Verificación a mano (la completa Claude Code al cerrar)

Con el entorno virtual activo: `python manage.py runserver`. Cuentas: Gerente, Agrónomo, Capataz, Administrador.
Recorrer, en escritorio y a 375 px: inicio de sesión; inicio de cada rol; Mi perfil; Usuarios (lista, alta, ficha, modificar,
baja, ventanas); Auditoría; Producción (lista, ficha, alta, modificar, baja y reactivar de un invernadero). Sin JavaScript:
inicio de sesión, lista de usuarios y lista de invernaderos.

Pasos para vos, además de lo de arriba (no hay navegador en la sesión de Claude Code: lo que se ve lo mirás vos):

1. Escritorio: el marco (cabecera con marca, menú lateral, pie) y que el hueco de la campana, entre el espacio y el menú de cuenta, esté vacío.
2. 375 px: desaparece el menú lateral y aparece la fila de fichas (`mnav`) con las mismas entradas; Capataz (marco de celular) no la muestra.
3. Sin JavaScript (desactivalo en las herramientas del navegador): inicio de sesión, lista de usuarios y lista de invernaderos se ven y funcionan; los desplegables quedan nativos.
4. Avisos breves (D-29): guardar algo y ver el aviso arriba a la derecha (abajo a 375 px); cierra a los 10 s.
5. Color de la organización (D-48): todavía no hay registrante (lo registra MAE-04), así que no se puede ver en pantalla; lo cubren las pruebas de `core/tests/test_identidad.py`.
6. Recorrida por rol: Gerente (Inicio con «Personal por asignar», Usuarios, Auditoría, Producción), Agrónomo, Capataz, Administrador.

## Cierre

**Qué se hizo.** La hoja `core/static/core/css/infoponia.css` pasó al «Diseño v2» del prototipo (mismas variables y nombres de clase, un solo tema, solo Inter), con los agregados propios del sistema al final. El marco (`base.html`, `base_con_sesion.html`) tiene el `mnav` de pantallas angostas y deja vacío y comentado el lugar de la campana. Se sumaron a `iconos.py` los 20 íconos del prototipo que faltaban. Identidad de la organización (D-48): `Identidad`, `registrar_identidad_de_la_organizacion` e `identidad_registrada()` en `core/extensiones.py` (sin tocar los cuatro puntos de D-43), `core/identidad.py`, el procesador de contexto (una consulta por pedido), el `<style>` de color en `base.html` (con y sin sesión, solo si el color cumple `#RRGGBB`) y los correos con `nombre_de_la_organizacion()`. Pantallas de `maestros` (lista, ficha, formulario, Inicio del Gerente) pasadas a `gh`, `split`, `facts`, `back` y `footbar`; las de `core` conservan sus componentes (`card`, `card-title`, `dl`, `tablewrap`), que son los mismos del v2, y los botones «Volver» pasaron a `.back`. Se borraron los archivos de DM Mono.

**Pruebas.** `core/tests/test_identidad.py` (10 pruebas; se escribieron antes y fallaron por no existir el módulo). `python manage.py test core maestros --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: 951 pruebas, OK. Ninguna prueba existente se modificó. No se corrieron las de concurrencia ni las de migración: la tarea no toca servicios con bloqueos ni migraciones.

**Decisiones y diferencias con la documentación.**
- `.mono` se conserva con su definición v2 (solo cifras tabulares), contra «quitá `.mono`» de la tarea; sí se quitó `--font-mono`. Lo elegiste vos.
- `.btn-ghost` y los avisos breves conservan las reglas de D-29 (contraste AA del borde, radio de 6 px, animaciones, posición abajo en < 760 px), porque `test_interfaz.py` las verifica y D-47 conserva D-29; difieren del prototipo.
- Se quitó la regla del prototipo que dejaba sin borde a los botones de las tablas (rompe el contraste de D-29).
- El oscuro y el claro de la marca salen de `color-mix()` (80 % con negro y 10 % con blanco): ningún documento lo definía. El hover de `.btn-ghost` queda con colores literales en la hoja (una prueba de contraste los lee) y el marco los reescribe con variables cuando hay color propio.
- Se agregaron todos los íconos de `ic()` y no solo los listados, aunque `iconos.py` no está en «Permitido fuera de la app» (lo elegiste vos).
- El prototipo deja `.mnav` oculto siempre (su `display:none` va después de la media query); acá se muestra en menos de 760 px.
- Recorrida (paso 6): no se pudo hacer con navegador. Se verificó que todas las clases de las plantillas estén definidas en la hoja, que la hoja esté balanceada y las pruebas de vistas; lo visual queda en la verificación a mano.
- Pantallas de auditoría y de usuarios del Administrador: solo cambiaron el «Volver» y lo que da la hoja nueva; el resto usa los mismos componentes v2 y no se rehízo su HTML.
