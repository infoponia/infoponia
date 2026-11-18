---
paths:
  - "**/templates/**"
  - "**/static/**"
---

# Interfaz

Resumen de lo vigente de D-24, D-25, D-26, D-29 y D-30 para hacer pantallas. Se carga sola al abrir una plantilla o un
estático; igual leela antes de tocar plantillas o estilos (regla L3 de `CLAUDE.md`). Si algo de acá contradice una
decisión, manda la decisión: avisá.

## Base

- Plantillas de Django con HTMX. HTMX y las fuentes (Inter y DM Mono) están en el repo, en `core/static/core/` (D-24,
  D-26). No se agregan archivos de terceros sin permiso.
- Los estilos son los de `core/static/core/css/infoponia.css`. Ninguna pantalla nueva define su propia paleta.
- Toda pantalla exige sesión (`LoginRequiredMiddleware`); la que no, se exime con `@login_not_required` (D-25).
- El menú lateral muestra solo lo que existe: cada tarea agrega su entrada (D-25).
- Capataz, Técnico y Transportista usan el marco angosto de celular, sin menú lateral (D-25).
- Ningún botón ni enlace lleva a un 403: si la cuenta no puede hacer algo, la acción no se muestra (D-30).

## Componentes

- Desplegables: propios y accesibles con teclado, nunca el `<select>` nativo; sin JavaScript queda el nativo como
  respaldo (D-24).
- Avisos breves (D-29): tarjeta con franja de 4 px del color de su tipo, ícono, cruz y barra de tiempo; duran 10 s;
  región `role="status"`; arriba a la derecha, y abajo sobre el pie en pantallas de menos de 760 px; sin movimiento con
  `prefers-reduced-motion`; sin JavaScript queda el aviso fijo. Los errores debajo de un campo no son avisos.
- Botón secundario (`.btn-ghost`): borde y texto en el verde primario sobre blanco. Todos los botones muestran el foco
  con Tab (`:focus-visible`). Los botones que son enlaces no se subrayan (D-29).
- Envíos en curso (D-29): `infoponia.js` deshabilita el botón de todo formulario POST y muestra el verbo de la acción.
  El verbo va en `data-enviando` («Guardando…» por defecto); no hace falta código propio en cada pantalla.
- Errores de HTMX (D-29): ya los resuelve `base.html` (límite de 30 s y dos avisos de error). No se agregan manejadores
  propios.

## Estáticos

- Los archivos estáticos propios se piden con `{% static_v %}`, no con `{% static %}`, porque `runserver` los sirve sin
  `Cache-Control` y el navegador guarda la versión vieja (D-29).

## Prototipos

- El prototipo es solo una guía visual: si su lógica difiere del caso de uso, manda el caso de uso (regla L7).
- Buscá con Grep la función que nombra la tarea y leé solo esa parte. El índice de funciones de cada prototipo está en
  su `README.md` (`docs/prototipos/<carpeta>/README.md`), salvo el de cuentas, cuyo índice está en
  `docs/casos_de_uso/usuarios.md`, sección «Pantallas».
- Los elementos «Solo prototipo» no se implementan (lista en el `README.md` de cada prototipo y en cada caso de uso).
- El prototipo de producción usa otro estilo («Diseño v2»: solo Inter, bordes de 10 px, `<select>` nativo en los
  filtros). Mientras no se decida (ver `docs/temas_abiertos.md`), tomá de él la estructura y el contenido de cada
  pantalla, y el estilo del sistema.
