# UI-04 · Textos y detalles visuales: nombres legibles, «usted» para el cliente y el proveedor, dinero, avatar, órdenes y paginación (D-109, tanda 2b)

Estado: pendiente | App: core (toca plantillas, correos y filtros de `maestros`, `iot`, `produccion`, `comercial` y `compras`) | Rama: feature/ui-04-textos-y-detalles | Ronda: —

Depende de: UI-02 (red de pantallas). Puede ir antes o después de UI-03, pero no en paralelo con ella (tocan las mismas plantillas;
`docs/patrones/trabajo_en_paralelo.md`).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**Esta tarea no cambia lo que el sistema hace.** Rige la regla de no romper de D-109 (punto 2). Tres riesgos concretos de esta tarea:

- **Correos:** muchas pruebas leen `mail.outbox` y afirman textos. Cada cambio de un correo se busca en las pruebas y se actualiza ahí.
- **Paginación:** cada lista arma sus enlaces conservando los filtros. El parcial común **recibe** las URL ya armadas por la vista
  y no cambia cómo se arman ni el nombre del parámetro de página.
- **Niveles de las apps (A1):** `compras` y `comercial` no se importan entre sí; un filtro se toma de la misma app o de una de nivel
  menor.

## Hallazgos incluidos

| ID | Qué |
|---|---|
| UX-06 | «hoja_verde» y tópicos técnicos como nombre de equipo |
| UX-14 | «Quitar» transportista con el verde de la acción principal |
| UX-16 | Dos anchos de contenido en el Panel de control |
| UX-17 | «Operás como … con la cuenta …» repetido |
| UX-18 | «20000 lux» sin separador |
| UX-19 | Textos de búsqueda cortados |
| UX-20 | Mismo ícono para Comercial y Pagos a proveedores |
| UX-22 | Avatar con la sigla del rol |
| UX-25 | Usted y vos mezclados en los portales |
| UX-29 | Código de orden cortado y botones apilados |
| UX-31 | Detalles de la ficha de solicitud |
| UX-32 | Jerarquía de botones de «Ver resumen» |
| UX-33 | Planificado como texto de ejemplo en Concretar siembra |
| UX-34 | «$49500,00» en los correos |
| UX-36 | Tres formatos de paginación |

El detalle de cada uno (dónde, qué se ve, causa y propuesta) está en `docs/revision_interfaz_2026-11-27.md`.

## Leer

- Decisiones: D-109 (puntos 2, 3, 7 y 12), D-29, D-47, D-61; D-65 y D-88 (enlaces del cliente y del proveedor: qué no se toca), D-70 (el identificador de los equipos no se toca)
- Revisión: `docs/revision_interfaz_2026-11-27.md` (las filas de arriba)
- Reglas: .claude/rules/interfaz.md, .claude/rules/pruebas.md; patrones docs/patrones/verificacion_a_mano.md,
  docs/patrones/enlace_del_cliente.md y docs/patrones/enlace_del_proveedor.md (solo para saber qué no cambiar)
- Código: `core/templates/core/_avatar.html`, `core/context_processors.py`, `core/menu.py`, `core/templatetags/` (filtros `sigla` e
  íconos), `core/templates/core/inicio.html`, los filtros `pesos` de `comercial`, `contabilidad` e `inventario`, las plantillas y
  correos que nombra cada paso.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de `core`: las plantillas, los correos `.txt` y los filtros de plantilla nombrados en los pasos; en los servicios
  del paso 5, solo el texto de los mensajes que leen el cliente o el proveedor y los asuntos de sus correos; textos de avisos
  en vistas (`messages`), nunca la lógica de la vista; `demo/tests/datos/pantallas_esperadas.json` si cambia el código de alguna
  pantalla (no debería); las pruebas que afirmen lo que cambia.
- Dependencias nuevas: ninguna.
- Fuera de alcance: mostrar u ocultar partes del portal del cliente (UI-07); unificar los cinco formateadores de pesos (UI-08): acá
  solo se usan los que ya existen.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Nombres legibles (UX-06).** Perfil familiar con su etiqueta (`get_…_display` o la de la opción): «Hoja verde», no «hoja_verde».
   Grep de dónde se muestra el perfil familiar crudo. Equipos de IoT en la ficha del invernadero y en Monitoreo: nombre por tipo y
   sector («Sensor de humedad · Maduración N1»); el identificador queda como dato secundario en la ficha del equipo y en Hardware (el
   Técnico lo necesita). **El identificador no se cambia en ningún dato ni en ninguna URL**: es lo que manda el nodo (D-70).
2. **Panel de control (UX-16 y UX-17).** Un solo ancho de contenido. «Operás como … con la cuenta …» sale; si querés, dejá solo el
   rol cuando la cuenta tiene cuentas vinculadas (ahí sí aporta). Grep de pruebas que afirmen «Operás como».
3. **Detalles visuales (UX-14, UX-18, UX-19, UX-20, UX-29, UX-31, UX-32 y UX-33).**
   - «Quitar» transportista: el estilo de acción secundaria de peligro que ya usa «Dar de baja».
   - Números de IoT con separador de miles siempre (usá el filtro que ya formatea «20.000»).
   - `placeholder` cortos: «Nombre o email», «Descripción o número».
   - Ícono propio para Pagos a proveedores en `core/menu.py` (uno de `core/templatetags/iconos.py`; si no hay uno adecuado,
     agregalo con el mismo formato).
   - Códigos de documento sin corte de línea (`white-space:nowrap` en la celda o en una clase común). Acciones de cada fila de
     Órdenes: la principal visible («Ver») y las demás en el menú «Más» de Diseño v2, si ya existe el componente; si no existe, solo
     el `nowrap` y anotalo en `docs/temas_abiertos.md`.
   - Ficha de solicitud: separador entre el código y el estado de la entrega; espacio que no corta entre «$» y el importe (en el
     filtro que arma el texto); la advertencia de multa se muestra solo cuando está elegido «aceptar» (con JavaScript; sin él queda
     como hoy, visible).
   - Botones: el que avanza («Ver resumen», «Revisar…») es `btn-primary` y va al final del formulario; en Nuevo pedido, el de
     arriba sale (o pasá su `value` exacto al de abajo si las pruebas lo usan: **el `name` y el `value` del botón no cambian**).
   - Concretar siembra: en vez de `placeholder` con el planificado, la ayuda «Vacío: 200 (lo planificado)». El comportamiento con el
     campo vacío no cambia.
4. **Avatar (UX-22, D-109 punto 12).** `_avatar.html` muestra las iniciales de la persona (primera letra del nombre y del apellido,
   en mayúscula) cuando no tiene foto. Hacelo con un filtro nuevo en `core` (`iniciales`), con la sigla del rol como respaldo si la
   cuenta no tiene nombre. **No quites `sigla` del contexto ni el filtro `sigla`**: Grep de todos sus usos.
5. **«Usted» para el cliente y el proveedor (UX-25, D-109 punto 7).** Los portales ya usan «usted»; se corrige lo que quedó en vos:
   - Los mensajes de error de los portales. Algunos los arma el servicio, como «Indicá si recibiste la entrega.» en
     `comercial/servicios/confirmacion.py`, que pasa a «Indique si recibió la entrega.». Buscá con Grep todos los mensajes que esos
     servicios devuelven al portal del cliente (`confirmacion.py`, `faltantes.py` para la decisión ante un faltante) y al del proveedor
     (`compras/servicios/cotizaciones.py` y los demás que use su vista). **Solo cambia el texto del mensaje:** el código del error
     (`respuesta_obligatoria`, etc.), el campo al que va y la condición quedan iguales.
   - Los correos al cliente (`comercial/templates/comercial/correos/*.txt`) y al proveedor (`compras/templates/compras/correo/*.txt`):
     asunto y cuerpo en «usted» («Confirme que la recibió», «Si tiene dudas, escríbale a su vendedor»). Los asuntos están en los
     servicios (por ejemplo, el diccionario de asuntos de `comercial/servicios/comprobantes.py`): Grep de cada envío.
   - Antes de cambiar, confirmá que cada correo es para el cliente o el proveedor; uno que reciba una cuenta del sistema queda en voseo.
   Lo que leen las cuentas del sistema no cambia. Ni el token, ni el flujo, ni los nombres de campos (D-65, D-88). Las pruebas que
   afirmen estos textos (por ejemplo, `comercial/tests/test_confirmacion_vistas.py`, que busca «Indicá si recibiste la entrega.») se
   actualizan en el mismo PR.
6. **Dinero en los correos (UX-34).** `${{ … }}` en `comercial/templates/comercial/correos/*.txt` pasa al filtro `pesos` de
   `comercial`; en `compras/templates/compras/correo/pago.txt`, al de `contabilidad` (nivel 2; A1). Mirá antes qué tipo de valor
   llega a cada correo (un `Decimal` o un texto ya formateado): si llega texto, formateá en la vista o el servicio que arma el
   contexto del correo, sin cambiar el monto. Pruebas: el correo dice «$ 49.500,00».
7. **Paginación (UX-36).** Un parcial `core/templates/core/_paginacion.html` con un solo texto: «Página 2 de 4 · 153 clientes» (el
   sustantivo lo pasa cada lista) y los enlaces «‹ Anterior» y «Siguiente ›». Recibe el objeto de página y las URL de la anterior y la
   siguiente **ya armadas por cada pantalla como hoy**. Grep de todas las paginaciones (`page`, `pagina`, `Página`, `Siguiente`) y
   listalas en el plan; reemplazá solo el marcado.
8. Red de pantallas entera, comando de pruebas y M1 a M4.

## Hecho cuando

- Ningún valor guardado se ve con su clave; los equipos se nombran por tipo y sector.
- Los portales, sus mensajes de error y los correos al cliente y al proveedor usan «usted»; los correos muestran «$ 1.500,50».
- El avatar sin foto muestra las iniciales.
- Todas las listas paginadas usan el mismo parcial y conservan sus filtros al cambiar de página (prueba por lista: página 2 con un
  filtro activo conserva el filtro).
- La red de pantallas pasa con la misma línea de base.
- Comando de pruebas: python manage.py test --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

<!-- Incluí el paso de «navegador real» (los portales son pantallas públicas): ventana privada, abrir un enlace de cliente y uno de
proveedor tomados de la consola (`CORREO_CONSOLA=1`) y enviar la respuesta hasta el final. Además: el avatar sin foto con iniciales en
el encabezado; una lista con filtro y página 2; Órdenes a 360 px y a 1366 px; un correo de comprobante en la consola con «$ 49.500,00». -->

## Cierre (la completa Claude Code al cerrar)
