---
paths:
  - "**/templates/**"
  - "**/static/**"
---

# Interfaz

Resumen de lo vigente de D-24, D-25, D-26, D-29, D-30 y D-47 para hacer pantallas. Se carga sola al abrir una plantilla o un
estático; igual leela antes de tocar plantillas o estilos (regla L3 de `CLAUDE.md`). Si algo de acá contradice una
decisión, manda la decisión: avisá.

## Base

- Plantillas de Django con HTMX. HTMX y la fuente Inter están en el repo, en `core/static/core/` (D-24,
  D-26). No se agregan archivos de terceros sin permiso.
- **Estilo (D-47): el de «Diseño v2» del prototipo de producción**, no el de `infoponia.css` anterior. Las variables
  (`--primary`, `--radius`, `--status-*`, colores de etapa, `--font-sans`) están en el bloque `<style>` del prototipo
  (`docs/prototipos/produccion/datos_maestros_y_produccion.html`, líneas 9 a 561; buscá solo las clases que necesites, L6).
  La tarea UI-01 las pasa a la hoja de estilos del sistema; hasta que esté hecha, `core/static/core/css/infoponia.css` es
  el estilo anterior y no se usa para pantallas nuevas. Solo Inter, con cifras tabulares (`.mono`); bordes de 10 px.   La hoja ya es la de Diseño v2 (UI-01). Dos excepciones, por D-29: `.btn-ghost` (borde y texto en el verde primario) y los avisos breves (`.toast`, `.avisos`) conservan sus reglas.
  Ninguna pantalla define su propia paleta.
- Toda pantalla exige sesión (`LoginRequiredMiddleware`); la que no, se exime con `@login_not_required` (D-25).
- El menú lateral muestra solo lo que existe: cada tarea agrega su entrada (D-25).
- Capataz, Técnico y Transportista usan el marco angosto de celular, sin menú lateral (D-25).
- Ningún botón ni enlace lleva a un 403: si la cuenta no puede hacer algo, la acción no se muestra (D-30).

## Componentes

- Desplegables: propios y accesibles con teclado, nunca el `<select>` nativo, con el aspecto de Diseño v2 (aunque el
  prototipo use el nativo en sus filtros, D-24 sigue vigente en esto: en Windows la opción resaltada se veía en blanco);
  sin JavaScript queda el nativo como respaldo.
- Avisos breves (D-29): tarjeta con franja de 4 px del color de su tipo, ícono, cruz y barra de tiempo; duran 10 s;
  región `role="status"`; arriba a la derecha, y abajo sobre el pie en pantallas de menos de 760 px; sin movimiento con
  `prefers-reduced-motion`; sin JavaScript queda el aviso fijo. Los errores debajo de un campo no son avisos.
- Botón secundario (`.btn-ghost`): borde y texto en el verde primario sobre blanco. Todos los botones muestran el foco
  con Tab (`:focus-visible`). Los botones que son enlaces no se subrayan (D-29).
- Envíos en curso (D-29): `infoponia.js` deshabilita el botón de todo formulario POST y muestra el verbo de la acción.
  El verbo va en `data-enviando` («Guardando…» por defecto); no hace falta código propio en cada pantalla. Un pedido de HTMX que solo
  vuelve a dibujar el formulario sin guardarlo (agregar o quitar una fila, un combo que cambia otros campos) lleva `data-sin-envio-en-curso`
  en su elemento y no deshabilita el botón de guardar (D-29, actualizada el 22/11/2026).
- Errores de HTMX (D-29): ya los resuelve `base.html` (límite de 30 s y dos avisos de error). No se agregan manejadores
  propios.

## Estáticos

- Los archivos estáticos propios se piden con `{% static_v %}`, no con `{% static %}`, porque `runserver` los sirve sin
  `Cache-Control` y el navegador guarda la versión vieja (D-29).

## Prototipos

- El prototipo es una referencia, no una especificación (D-61, regla L7): si su lógica difiere del caso de uso, manda el
  caso de uso. Puede tener errores o faltantes, también fuera de la lista «Lo que difiere del prototipo» de cada extracto.
- **Corregí y completá la pantalla con tu criterio de diseñador**, sin frenar, cuando hace falta para que el caso de uso se
  pueda concretar o para que la pantalla funcione bien: el campo, botón, columna, filtro o paso que falta; los estados vacío,
  de error, de carga y sin permiso; la ventana de confirmación o de resumen; un control que no sirve para el dato o un flujo
  que no cierra; los textos que falten (con el tono de este archivo); accesibilidad, teclado, celular y respaldo sin
  JavaScript. Mantené el estilo del prototipo (D-47) en lo que agregues.
- **Frená y preguntá** (L7, L9) solo si la corrección necesita una regla de negocio, un permiso, un cálculo o una columna que no
  están en el caso de uso, el modelo o una decisión, o si contradice alguno de ellos o el código mergeado.
- Anotá cada corrección en el «Cierre» de la tarea, en «Pantallas: lo que se corrigió del prototipo»: qué tenía, qué hiciste y
  qué paso o regla lo pide.
- Buscá con Grep la función que nombra la tarea y leé solo esa parte. El índice de funciones de cada prototipo está en
  su `README.md` (`docs/prototipos/<carpeta>/README.md`), salvo el de cuentas, cuyo índice está en
  `docs/casos_de_uso/usuarios.md`, sección «Pantallas».
- Los elementos «Solo prototipo» no se implementan (lista en el `README.md` de cada prototipo y en cada caso de uso).
- Del prototipo de producción se toma la estructura, el contenido y el estilo (D-47); la lógica la manda el caso de uso.

## Validaciones e interacción HTMX (desde INV-02)
- Prohibido disparar validaciones ni recálculos mientras el usuario tipea (nada de `hx-trigger="input delay:..."` ni `change` validando campos numéricos, de texto o fechas).
- Las validaciones y resúmenes corren únicamente al presionar botones de acción («Ver resumen», «Confirmar», etc.).
- Si un selector redibuja campos dependientes por HTMX, debe hacerlo sin validar, usando `hx-swap="innerHTML show:none"` para no mover el scroll ni robar el foco, manteniendo siempre el respaldo funcional sin JavaScript.
## Revisión de interfaz (D-109, desde UI-02)

- **No romper.** Las tareas de interfaz no cambian modelos, migraciones, servicios, permisos, rutas, nombres de URL, nombres de campos
  ni valores de botones, ni los `id`, `data-*`, `hx-*` o clases que usan los scripts o las pruebas. Antes de cambiar algo compartido
  (marco, `infoponia.css`, `_avatar.html`, `infoponia.js`, filtros, parciales incluidos en varias pantallas), buscá con Grep cada uso
  en todo el repo y revisá cada uno; poné la lista en el plan. Una prueba que afirma un texto o un estilo que cambiás a propósito se
  actualiza en el mismo PR (nunca se borra) y se lista en el «Cierre».
- **Red de pantallas.** `demo/tests/test_red_de_pantallas.py` (UI-02) recorre las pantallas de las diez cuentas de la demo: ninguna
  da 500, cada una da el código de su línea de base (`demo/tests/datos/pantallas_esperadas.json`) y ninguna muestra códigos internos.
  Corrala en toda tarea que toque plantillas o estilos.
- **Grillas:** la columna del contenido y la del encabezado usan `minmax(0,1fr)`, nunca `1fr` solo.
- **Color:** todo texto cumple 4,5:1. `--faint` es para bordes e íconos decorativos; no va texto blanco chico sobre un color de etapa.
- **Enlaces:** los del contenido van en `--primary`; las pestañas que son enlaces usan la regla común `a.tab`; «volver» usa el ícono
  `back`, nunca `chev`.
- **Textos visibles** (pantallas, avisos, correos y PDF): sin códigos de tareas, casos de uso, decisiones ni rondas; fieles a lo que
  el código hace hoy; valores guardados con su nombre legible; «usted» en lo que leen el cliente y el proveedor (portales por enlace,
  sus mensajes de error y los correos que se les mandan) y voseo en todo lo demás; dinero como «$ 1.500,50» con el
  filtro de la app o de una de nivel menor; plurales con tilde («órdenes»); los códigos de documento no se cortan en dos líneas.
- **Accesibilidad:** columna de acciones con «Acciones» solo para lectores; vista activa con `aria-current="page"` (o `aria-selected`
  con `role="tab"`), nunca `aria-pressed` en un enlace; todo campo con etiqueta; títulos sin saltos de nivel.
- **Resumen y errores a la vista:** el resumen, o el primer error, lleva `data-llevar-vista` y `tabindex="-1"`; `infoponia.js` le
  lleva la vista y el foco. Los selectores que solo redibujan campos siguen sin mover la vista (regla de INV-02).
- **Montos que se calculan al tocar un botón:** mientras no se calcularon, «—» con la ayuda «Se calcula al tocar «Actualizar»».
- **`style="…"`** solo para valores calculados en el momento; en lo que toques, usá clases y los tamaños y colores de `:root`.
