# Revisión de interfaz del 27/11/2026 (fuente de D-109)

Relevamiento hecho por Claude en claude.ai sobre una copia de `main` en el PR #105, con los datos de `cargar_demo` y las diez
cuentas de la demo (siete roles):

- **Pantallas:** 136, con capturas a 1366 px (computadora) y a 360 px (celular).
- **Accesibilidad:** axe-core con las reglas WCAG 2.2 AA.
- **Flujos recorridos de punta a punta desde la interfaz:** siembra, transición, concretar siembra y cosecha en el celular, ruta,
  entrega con devolución, portal del cliente con una queja, resolución, cobro, compra-venta, pedido de cotización y portal del
  proveedor.
- **IoT:** 24 h de lecturas enviadas a la API, con valores fuera de umbral.
- **Formularios:** todos los de alta, enviados vacíos.
- **Volumen:** 150 clientes, 40 proveedores y 120 asientos cargados con los servicios.

Gravedad de 0 a 4 (escala de Nielsen); esfuerzo bajo, medio o alto. La columna «Tarea» dice dónde se corrige. Las rutas de archivo
son las del 27/11/2026: antes de tocar, buscá con Grep, porque pueden haber cambiado.

| ID | Grav. | Esf. | Dónde | Qué se ve | Causa o archivo | Propuesta | Tarea |
|---|---|---|---|---|---|---|---|
| UX-01 | 4 | bajo | Todas las pantallas a 360 px, todos los roles | El encabezado y el contenido miden 459 px (Gerente) o 437 px (Capataz) en 360. El botón de la cuenta queda fuera de vista, y los avisos, las tablas y el panel de la campana aparecen cortados | `infoponia.css`: `.shell:not(.field){grid-template-columns:1fr}` (bloque `@media(max-width:760px)`), `.shell.field{…grid-template-columns:1fr…}` y `.shell.sin-lateral{grid-template-columns:1fr}`. `1fr` no baja del ancho mínimo de su contenido, y la fila `.mnav` suma unos 430 px | `minmax(0,1fr)` en las tres reglas (y en la de escritorio, `var(--sidebar-width) minmax(0,1fr)`); `.mnav .chip{flex-shrink:0;white-space:nowrap}`. Probado: el ancho vuelve a 360 px | UI-02 |
| UX-02 | 3 | medio | Listas de Comercial, Compras, Usuarios, Contabilidad e Inventario en el celular | La tabla conserva sus columnas y se desplaza de costado; en Clientes, el nombre se parte en 4 líneas | `.tablewrap` sin versión angosta | Debajo de 760 px, cada fila como tarjeta apilada (el patrón `.lotlist` ya existe) | UI-05 |
| UX-03 | 3 | bajo | 113 de 136 pantallas | Rótulo «Módulos» del menú, `.faint`, fechas de la campana: #8a94a0 da 3,07:1 sobre blanco y 2,75:1 sobre #eaf5ee | `--faint` en `:root` | `--faint` que cumpla 4,5:1 (propuesta `#5f6b78`). Texto blanco sobre color de etapa (gráfico de Variedades): 3,72 a 4,25:1; usar el texto oscuro sobre fondo claro de `.etapa` | UI-02 |
| UX-04 | 3 | alto | Todo el sistema | 831 atributos `style="…"` en plantillas, 19 tamaños de letra (de 10 a 28 px, con 12,5, 13,5, 14,5 y 15,5), 68 colores escritos a mano, 11 CSS de app que repiten reglas del común, 5 funciones distintas para formatear pesos | Cada tarea copió lo que tenía a mano | Escala de 6 tamaños en variables, colores solo de `:root`, `style=` solo para valores calculados, CSS de app sin reglas repetidas | UI-08 |
| UX-05 | 3 | bajo | Ficha del invernadero, IoT, Comercial | «Activo» (sistema IoT) en el azul por defecto del navegador; pestañas subrayadas que parecen enlaces | Sin estilo base para `a`; `a.tab{text-decoration:none}` copiado en `compras.css`, `contabilidad.css`, `inventario.css` y `cultivos.css`, y falta en el resto | Estilo base de enlaces del contenido con `--primary`; `a.tab` una sola vez en `infoponia.css` | UI-02 |
| UX-06 | 3 | bajo | Ficha del invernadero (sectores), IoT | «Perfil familiar: hoja_verde» (la clave guardada); sensores nombrados por su tópico, como «Sensor de humedad norte/sectorA/humedad» | Plantillas que muestran el valor y no su etiqueta | Nombre legible («Hoja verde»). Equipos: tipo y sector («Sensor de humedad · Maduración N1»), con el identificador solo como dato secundario en la ficha del equipo | UI-04 |
| UX-07 | 3 | medio | Celular, Gerente y Agrónomo | Los módulos pasan a una fila de botones que se desplaza de costado; el Gerente tiene 13 y se ven 3 o 4, sin indicio de que hay más | `.mnav` | Botón «Menú» en el encabezado que despliega la lista del menú lateral, con `<details>` (sin JavaScript) | UI-05 |
| UX-08 | 2 | bajo | 26 plantillas de Producción, Comercial e Inventario | El enlace «volver» usa el ícono `chev` (flecha hacia abajo) | `<a class="back" …>{% icono "chev" 14 %}` | Ícono `back`, como las otras 54 plantillas | UI-02 |
| UX-09 | 2 | bajo | 38 pantallas con tablas | Columna de acciones con el encabezado vacío | `<th></th>` | «Acciones» visible solo para lectores de pantalla | UI-03 |
| UX-10 | 2 | bajo | Compras (órdenes, reclamos), Cobranza, Contabilidad (8 pantallas) | Enlaces con forma de botón redondeado (`.chip`) con `aria-pressed`, que solo vale en un botón | `aria-pressed` en `<a>` | `aria-current="page"` en el activo, o `aria-selected` si tiene `role="tab"` | UI-03 |
| UX-11 | 2 | bajo | Variedades (duraciones de etapa), Mi perfil (campo de la cámara), Concretar cosecha (plantas perdidas, causa, descripción) | Campos sin etiqueta asociada, o con la etiqueta oculta | Falta `<label for>` o `aria-label` | Etiqueta asociada a cada campo (puede ser solo para lectores) | UI-03 |
| UX-12 | 2 | bajo | Nuevo invernadero, con errores | Solo Localidad se marca en rojo; Provincia y Departamento, también obligatorios, no | Errores solo en el último campo del grupo | Marcar el grupo, o los tres | UI-03 |
| UX-13 | 2 | medio | IoT · Monitoreo | Sin datos: tres avisos seguidos y cinco «Sin lecturas» iguales. Con datos se lee bien, pero cada tipo de sensor ocupa una caja de ancho completo con una tarjeta de un tercio | Una sección por variable | Grilla de tarjetas de sensor; un solo estado vacío cuando no hay ninguna lectura | UI-07 |
| UX-14 | 2 | bajo | Ficha del invernadero (Logística) | «Quitar» (al transportista) usa el verde de la acción principal | Clase del botón | Estilo secundario o de peligro, como «Dar de baja» | UI-04 |
| UX-15 | 1 | bajo | 27 pantallas | Títulos de tarjeta en `h3` directamente bajo el `h1` | `.card-h > h3` | `h2` donde corresponda | UI-03 |
| UX-16 | 1 | bajo | Panel de control | El título y el aviso de personal están en una columna 99 px más angosta que las secciones | Dos anchos de contenido | Un solo ancho | UI-04 |
| UX-17 | 1 | bajo | Panel de control | «Operás como Gerente con la cuenta …@gmail.com» repite el encabezado | `core/inicio.html` | Quitarlo, o un dato útil del día | UI-04 |
| UX-18 | 1 | bajo | IoT | «20.000 a 45.000 lux» y «20000 lux» en la misma pantalla | Formato de número | Separador de miles siempre | UI-04 |
| UX-19 | 1 | bajo | Usuarios, Contabilidad | Textos de búsqueda cortados: «Buscar por nombre, apellido o em» | `placeholder` largo | Más corto («Nombre o email») | UI-04 |
| UX-20 | 1 | bajo | Menú lateral | Comercial y Pagos a proveedores usan el mismo carrito | Ícono | Ícono propio para pagos | UI-04 |
| UX-21 | 1 | bajo | Pie | «Sistema operativo» en oficina (se lee como Windows o Android) y «En línea» en el modo campo | `base_con_sesion.html` | «En línea» en los dos | UI-02 |
| UX-22 | 1 | bajo | Encabezado | El avatar sin foto muestra la sigla del rol («GER»); la ficha del invernadero, las iniciales de la persona | `_avatar.html` recibe «sigla» | Iniciales de la persona (D-109 punto 12) | UI-04 |
| UX-23 | 3 | bajo | Registrar cobro, ficha de solicitud | «… El asiento no se genera en esta ronda (contabilidad).», pero el cobro genera su asiento desde CON-04d. «Hasta que se complete COM-07b, el contrato queda «vigente»», pero COM-07b ya resuelve el contrato | `comercial/views_cobranza.py` (aviso de `registrar`), `comercial/templates/comercial/solicitudes/ficha.html` (advertencia de la resolución) y los que encuentre la red de pantallas | Textos fieles al código, sin códigos internos | UI-02 |
| UX-24 | 3 | bajo | Nueva siembra, portal del cliente y otros formularios largos | Después de «Ver resumen» o de un error, la página vuelve arriba y el foco queda en `body`. El resumen de Nueva siembra queda unos 1.200 px más abajo; el error del portal, a 1.300 px | Nadie lleva la vista | `data-llevar-vista` (D-109 punto 9) | UI-06 |
| UX-25 | 2 | bajo | Portales del cliente y del proveedor | «Confirme la recepción…» y «Puede cotizar…» (usted), pero el error dice «Indicá si recibiste la entrega» y los correos usan vos | Tratos mezclados | «Usted» en portales, sus errores y los correos al cliente y al proveedor; voseo dentro del sistema (D-109 punto 7) | UI-04 |
| UX-26 | 2 | medio | Portal del cliente | Las quejas y «Si no recibió la entrega…» se ven siempre, con «*» de obligatorio, aunque el cliente esté conforme | Todo el formulario a la vista | Cada parte solo para su opción (con JavaScript; sin él, todo visible como hoy) | UI-07 |
| UX-27 | 2 | medio | Nueva siembra | Con Plantines, Fecha y Distribución vacíos, solo marca Plantines; Nuevo invernadero, en cambio, marca todo | La vista corta en el primer error | Los obligatorios independientes se validan juntos (D-109 punto 9) | UI-06 |
| UX-28 | 2 | medio | Nueva compra-venta | El resumen lateral y el subtotal dicen «$ 0,00» y «—» mientras la ventana de confirmación dice $ 19.000,00 | Se calcula al tocar «Actualizar» (regla de INV-02) | «—» con «Se calcula al tocar «Actualizar»» (D-109 punto 10) | UI-07 |
| UX-29 | 2 | bajo | Órdenes de trabajo | «OT-» y «0004» en dos líneas; hasta tres botones apilados por fila | Sin `white-space:nowrap` | Códigos sin corte; acciones secundarias en el menú «Más» de Diseño v2 | UI-04 |
| UX-30 | 2 | bajo | Órdenes de trabajo | El aviso de éxito tapa los botones del encabezado | D-29 lo ubica arriba a la derecha | **Descartado** (D-109 punto 1) | — |
| UX-31 | 2 | bajo | Ficha de solicitud | «OT-0008Concretada» sin separación; advertencia roja de multa antes de elegir «aceptar»; «$» y el importe en líneas distintas | Plantilla | Separador; advertencia solo al elegir aceptar (con JavaScript; sin él, como hoy); espacio que no corta | UI-04 |
| UX-32 | 1 | bajo | Siembra, transición, solicitudes, nuevo pedido | «Ver resumen» secundario en unas pantallas y principal en otras; en Nuevo pedido, «Revisar pedido» también arriba de todo | Sin regla | El botón que avanza es principal y va al final | UI-04 |
| UX-33 | 1 | bajo | Concretar siembra | El planificado se ve como texto de ejemplo gris («200») y parece cargado | `placeholder` | Ayuda «Vacío: 200 (lo planificado)» | UI-04 |
| UX-34 | 1 | bajo | Correos al cliente y al proveedor | «$49500,00» sin separador ni espacio | `${{ total }}` en `comercial/templates/comercial/correos/*.txt` y `compras/templates/compras/correo/pago.txt` | «$ 49.500,00» (D-109 punto 7; A1) | UI-04 |
| UX-35 | 1 | bajo | Panel del Capataz, Registrar cobro, Concretar siembra | «Tenés 2 ordenes próximas», «S.A..» (doble punto: la razón social termina en punto), «200 unidad» | `produccion/_seccion_de_inicio.html` (`pluralize:",es"`), aviso de cobro, unidad sin plural | Corregir | UI-02 |
| UX-36 | 1 | bajo | Clientes, Contabilidad, Auditoría | Paginación con tres textos: «Página 1 de 4 · 153 clientes», «145 en total · página 1 de 3», «Registros 1 a 25 de 744» | Una paginación por app | Un solo parcial de paginación | UI-04 |

Después de la revisión, el estudiante sumó los colores de la organización (la pestaña pide códigos hexadecimales, solo se usa el
primero y no se valida el contraste): D-110 y UI-09.

Lo que la revisión confirmó que está bien y hay que conservar: formularios con secciones, ayudas y errores junto al campo; estados
vacíos que explican; resumen antes de confirmar en los flujos que cambian datos; avisos de éxito que dicen qué pasó y qué sigue;
errores de negocio concretos; una sola tipografía con cifras tabulares; foco visible; colores fijos por etapa; respaldo sin
JavaScript; controles grandes en el modo campo; el editor de encuadre de la foto (diálogo accesible, teclado); gráficos de IoT con la
banda del umbral; paginación en las listas largas y pantallas que cargan en menos de un segundo.

No es un error: los campos de fecha mostraron «mm/dd/yyyy» en el navegador automatizado; con Chrome en español muestran «dd/mm/aaaa».
