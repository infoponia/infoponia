# CMP-02a · Pedido de cotización y portal del proveedor

Estado: hecha en su rama (falta su PR) | App: compras (y una constante en core) | Rama: feature/cmp-02a-pedido-y-portal-del-proveedor | Ronda: Compras 1

Depende de: **CMP-01**, USR-10 (correo público, hecha), INV-02 (hecha). **No depende de la contabilidad.** Si CMP-01 no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Agrónomo arma un **pedido** de cotización (con los insumos bajo el mínimo, para uno o varios invernaderos) e invita
proveedores; cada proveedor recibe un **enlace** y cotiza **sin cuenta**, una sola vez. El Agrónomo y el Gerente consultan los pedidos.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-RLZ-PED | Realizar Pedido | docs/casos_de_uso/compras/pedidos.md | 6a obsoleta (P5); 12a: el aviso al Agrónomo sale, el reintento es «Reenviar invitación» de CMP-02b |
| CMP-ENV-COT | Enviar Cotización (portal del proveedor) | docs/casos_de_uso/compras/pedidos.md | Con las actualizaciones de A0 (cantidad mayor que la pedida, total por línea, plazo ≥ 1) |
| CMP-CNS-PED | Consultar Pedido | docs/casos_de_uso/compras/pedidos.md | Regla 7 («Reenviar invitación») y la acción «Cancelar»: CMP-02b; «Generar orden»: CMP-03 |

## Leer

- Casos de uso: el extracto `pedidos.md`, **solo** CMP-RLZ-PED, CMP-ENV-COT y CMP-CNS-PED, sus actualizaciones de A0 y su «Cómo se aplica».
- Modelo: docs/modelo/compras.md (`Pedido`, `DetallePedido`, `InvitacionPedido`, `EnlaceProveedor`, `Cotizacion`, `DetalleCotizacion`).
- Decisiones: D-87, D-88 (la del enlace), D-89 (precios), D-65 (enlace del cliente, del que se copia), D-54, D-36, D-37, D-42, D-44.
- API: docs/api/stock.md («Lectura»), docs/api/notificaciones.md, docs/api/correo.md.
- Patrones: docs/patrones/enlace_del_proveedor.md **y** docs/patrones/enlace_del_cliente.md, docs/patrones/bloqueos.md, docs/patrones/auditoria.md,
  docs/patrones/stock.md (sección 5).
- Pantallas: docs/prototipos/compras_contabilidad/ — `VIEWS.c_main`, `tabPed`, `VIEWS.c_pednew`, `VIEWS.c_ped`, `VIEWS.c_cotz` (sin el selector «enlace
  de ejemplo», que es solo del prototipo), `panelAgr` (la sección «pedidos que vencieron» va en CMP-03).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `core/enlaces.py`, `core/correo.py`, `core/notificaciones.py`; `core/models.py` (`RegistroAuditoria.objects.registrar` y, si ya
  existe, `rol_externo` y `ROL_CLIENTE_ENLACE`); `inventario/servicios/stock.py` (`existencias`), `inventario/servicios/insumos_invernadero.py`
  (`habilitados`, `habilitar_insumo`); `maestros/servicios/configuracion.py` (`obtener`); `maestros/servicios/invernaderos.py`
  (`bloquear_invernadero_activo`); si ya existe, `comercial/servicios/enlaces.py` y `comercial/views_cliente.py` como modelo.

## Límites

- Crea modelos: `Pedido`, `DetallePedido`, `InvitacionPedido`, `EnlaceProveedor`, `Cotizacion`, `DetalleCotizacion` → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0002_pedidos_y_cotizaciones.py`; una de `core` con las acciones (`alta_pedido`, `alta_cotizacion` y las que
  uses) y, si no existe, `rol_externo` + `ROL_CLIENTE_ENLACE` + `ROL_PROVEEDOR_ENLACE` (D-88 punto 5; D-65 punto 8).
- Permitido fuera de la app: `core/models.py` (acciones, `ROL_PROVEEDOR_ENLACE` y, si falta, `rol_externo` con su prueba en `core/tests/`);
  `config/urls.py` (la URL pública `proveedor/`); al cerrar, los archivos de M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: cancelar, reenviar, impedimentos y lo que cancela solo (CMP-02b); la orden de compra y los pasos diarios (CMP-03).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y migración** con todas sus restricciones (C8 por la única `(pedido, proveedor)`). — pruebas: `test_modelos.py` (amplía).
2. **`compras/precios.py`** (`precio_unitario`, `valor_recibido`, D-89) y **`compras/servicios/cobertura.py`**. — pruebas: `test_precios.py`,
   `test_cobertura.py` (los cuatro ejemplos de la regla de cobertura).
3. **CMP-RLZ-PED** (servicio y resumen) y `compras/servicios/enlaces.py` (crear y enviar). — pruebas: `test_cmp_rlz_ped.py`, `test_enlaces.py`.
4. **CMP-ENV-COT** (vistas públicas, servicio y aviso de pedido cubierto) y `compras/servicios/avisos.py` (`destinatarios_por_destino`, D-87 punto
   3). — pruebas: `test_cmp_env_cot.py`, `test_avisos.py`, `test_pedidos_concurrencia.py` (dos envíos del mismo proveedor; dos que cubren a la vez).
5. **CMP-CNS-PED** y las pantallas del Agrónomo y del Gerente. — pruebas: `test_cmp_cns_ped.py`, `test_pedidos_vistas.py`.

Si el tiempo apremia, lo último que se recorta es: el filtro propuesto por especialidad en el paso 6 (se anota como disparador).

## Hecho cuando

- Un Agrónomo arma un pedido para dos invernaderos, invita proveedores y cada uno recibe su enlace; un proveedor cotiza una vez (total o unitario
  por línea), recibe el acuse y ve su cotización en solo lectura; el aviso de pedido cubierto sale una sola vez.
- El token no está en la base; la auditoría muestra «Proveedor (mediante enlace)».
- Pruebas verdes (incluida concurrencia), sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano (`docs/patrones/verificacion_a_mano.md`)

La «Verificación a mano» original de la tarea (tres pasos) se amplió a los pasos del final, que **hace el estudiante** y se anotan en `docs/revisiones_pendientes.md` (D-96: sin navegador automatizado ni cargadores; los datos se crean en los pasos). Los pasos 1 a 6 de la tarea original están en los pasos 1 a 7 de abajo; el 2, en los 8 a 11; y el 3, en los 7 y 13.

### Verifiqué

- **Recorrido con el cliente de Django** (`compras/tests/test_recorrido_pedidos.py`, 17 pasos, en verde): inicio del Agrónomo con «Pedir» (1a), agregar del catálogo (3a) y habilitar un insumo desde el pedido (3a.1a, con error y con éxito), errores 4a/4b/5a/8a/8b juntos, filtro propuesto de proveedores y «seleccionar todos», resumen, confirmar (un correo por proveedor, cada uno con **su** enlace y sin precios de referencia), ficha del Agrónomo y del Gerente (modo consulta), 403 para otro Agrónomo y el Capataz, portal sin cuenta (redirección sin el token, sin precio de referencia ni otros invitados), errores 6a/6b/6c/9a, envío con una cantidad mayor que la pedida, acuse, solo lectura, un segundo envío rechazado, aviso de pedido cubierto **una sola vez**, el segundo proveedor cotizando con precio unitario, cotizaciones visibles en la ficha, auditoría con «Proveedor (mediante enlace)», el token ausente de `compras_enlaceproveedor` y de `core_registroauditoria`, la tarjeta de pedidos de la ficha del proveedor, el CUIT que deja de editarse y el enlace vencido.
- **Un navegador real, antes de D-96** (Playwright, hoy retirado) encontró cuatro defectos que el cliente de Django no ve; los cuatro se corrigieron:
  1. **El portal no podía enviar nada en un navegador real**: con `Referrer-Policy: no-referrer` (D-88 punto 4) Chromium manda `Origin: null` en los POST del mismo sitio y Django rechazaba el CSRF («Verificación CSRF fallida»). Se pasó a `same-origin`.
  2. En el celular, las tarjetas de la ficha se cortaban por la derecha (la grilla `.stack` se ensanchaba con la tabla); se corrigió con `.stack > *{min-width:0}`.
  3. El nombre del proveedor y su categoría salían pegados («Semillas del Sur S. A.Semillas y plantines»).
  4. Doble punto en la cabecera del portal («Semillas del Sur S. A.. Pedido P-0331»).
  Ya no se verifica así (D-96): esos cuatro puntos los cubren los pasos 12, 18 y 19 de abajo.
- **Migraciones:** `makemigrations --check --dry-run`: sin cambios. `sqlmigrate compras 0002`: solo `CREATE TABLE` (seis), `CHECK`, `UNIQUE`, claves foráneas y un índice único parcial; **ninguna** sentencia `DROP`, `DELETE`, `UPDATE` ni `ALTER COLUMN`. `sqlmigrate core 0028`: no-op (solo cambian los `choices` de la acción). Ambas se aplicaron al crear la base de pruebas.
- **Comandos de «Hecho cuando»:** ver «Pruebas» en el «Cierre».
- **Sin dependencias nuevas**; `compras` no importa de `comercial` ni de `produccion`.

### Lo cubre una prueba

| Qué | Prueba |
|---|---|
| Restricciones de la base: estado ⇔ cierre, cancelado ⇔ causa, manual ⇒ motivo, fecha límite, detalle único, invitación única, un enlace vigente, `usado` ⇔ fecha de uso, **C8**, línea única, cantidad/total/plazo | `test_modelos.py` (`PedidosRestriccionesTests`, 19) |
| `rol_externo` (solo sin cuenta y con una de las dos constantes) | `core/tests/test_registro_auditoria.py` (`test_d88_*`, 2) |
| Precio unitario derivado, total desde el unitario, valor recibido (tres recepciones parciales suman el total) | `test_precios.py` (13) |
| Los cuatro ejemplos de cobertura (20 lechugas y 20 tomates, 10 %) y la tolerancia leída en cada uso | `test_cobertura.py` (12) |
| CMP-RLZ-PED: cada regla, extensión (1a, 2a, 3a, 4a a 4c, 5a, 8a, 8b, 11a, 12a) y postcondición (a a g) | `test_cmp_rlz_ped.py` (44) |
| Enlace del proveedor (token no guardado, rollback sin correo, correo que falla, situaciones) | `test_enlaces.py` (21) |
| CMP-ENV-COT: reglas, extensiones, postcondiciones, 11a/11b/11c y el portal público (encabezados, sesión, motivos) | `test_cmp_env_cot.py` (57) |
| Regla única de destinatarios (H21) | `test_avisos.py` (9) |
| Concurrencia: dos envíos del mismo proveedor; dos proveedores que cubren a la vez (12 + 12 y 20 + 20) → un solo aviso | `test_pedidos_concurrencia.py` (3) |
| CMP-CNS-PED: alcance, listado, filtros, ficha, cotizaciones, `tiene_pedidos_u_ordenes`, pedidos del proveedor | `test_cmp_cns_ped.py` (27) |
| Pantallas: lista, ficha, «Nuevo pedido» (acciones, errores, 12a, 11a, 3a.1a), inicio del Agrónomo, ficha del proveedor, menú | `test_pedidos_vistas.py` (39) y `test_proveedores_vistas.py` (el menú) |

### No pude verificar

- **Envío real de correo** (SMTP) y que los enlaces de los correos se armen bien con el dominio de producción detrás del proxy de Render (`request.build_absolute_uri` con `SECURE_PROXY_SSL_HEADER`): las pruebas usan el correo simulado.
- **Despliegue:** que Render aplique `compras 0002` y `core 0028` y que el portal abra en producción.
- **Otros navegadores:** la corrección de `Referrer-Policy` se verificó solo en Chromium; Safari (iPhone) y Firefox no se probaron con el portal real, que es donde van a cotizar los proveedores (paso 19).
- **El aspecto y el JavaScript:** la verificación visual automática se retiró (D-96); los cubren los pasos 12, 18 y 19. El Agrónomo en un celular: el caso de uso lo piensa para computadora y en un celular la tabla de «insumos bajo el mínimo» scrollea adentro.
- **Criterio de producto:** si «Nuevo pedido» (un formulario que se vuelve a dibujar con cada botón) y el «usted» del portal son lo que se quiere. Concurrencia con carga (se probó con dos hilos).

### Pasos (los hace el estudiante y los tacha en `docs/revisiones_pendientes.md`, M5)

**Antes de empezar.** En PowerShell, con el entorno virtual activo: `python manage.py migrate` (aplica `compras 0002` y `core 0028`) y `python manage.py runserver`; abrí <http://127.0.0.1:8000/>. Para ver los correos sin enviarlos de verdad, la base local tiene que tener el correo en modo consola (`CORREO_CONSOLA=1` en tu `.env`, y reiniciá `runserver`): cada correo se imprime en la terminal y de ahí copiás el enlace. Sin eso, los enlaces quedan «No se pudo enviar» (también es un caso para mirar, paso 15). **No escribas ninguna contraseña en un archivo del repo.**

Datos que hay que crear a mano, **en este orden** (como Gerente, salvo que se diga otra cosa):
1. *Usuarios y seguridad → Nueva cuenta*: un **Agrónomo** (por ejemplo `ana@ejemplo.com`, con «contraseña temporal»: anotala fuera del repo). Otra cuenta de **Agrónomo** (`otra@ejemplo.com`) y un **Capataz** (`capataz@ejemplo.com`), para ver qué no pueden hacer.
2. *Producción → Invernaderos → Nuevo*: «Invernadero Norte» (urbana, calle «Calle 122», número «3310», cualquier localidad) y «Invernadero Sur», los dos con **Ana** de Agrónoma.
3. *Inventario* (como Agrónoma Ana): tres insumos del catálogo, «Lechuga» (unidad: unidad), «Nutriente» (kg) y «Sustrato» (kg); después, *Habilitar insumo*: Lechuga en Norte (mínimo 20, precio 12,50) con **stock inicial 5**; Nutriente en Sur (mínimo 5, precio 100,00) con stock inicial 9. **No** habilites el Sustrato.
4. *Compras → Proveedores → Nuevo proveedor*: «Semillas del Sur S. A.» (jurídica, CUIT `30-00000013-9`, correo `ventas@ejemplo.com`, con la categoría de la Lechuga) y «Viveros del Este S. R. L.» (jurídica, CUIT `30-00000026-0`, correo `info@ejemplo.com`).

**Como Agrónoma Ana** (el recorrido cubre todo lo que no diga «a mano»):
1. *Panel de control*: en la sección «Compras» ves «Insumos bajo el mínimo: 1» (la Lechuga; el Nutriente está sobre el mínimo) y a su lado el botón **Pedir**. Tocalo: te lleva a «Nuevo pedido» con la Lechuga ya agregada y la cantidad sugerida **15** (20 − 5).
2. En «Agregar otro insumo del catálogo» elegí «Nutriente» (grupo Invernadero Sur) y tocá **Agregar insumo**: aparece como segundo renglón (sugerida: 0 → cantidad vacía). Escribí **3**.
3. Abrí «¿El insumo no está en la lista? Habilitarlo en un invernadero». Elegí Invernadero Sur, Sustrato, mínimo 2 y precio **0**, y tocá **Habilitar y agregar al pedido**. Tiene que verse el error «Ingresá un precio mayor que 0…» junto al campo, con la ventana abierta y el pedido intacto. Corregí el precio a **30,00** y repetí: el Sustrato queda habilitado y aparece como tercer renglón. Quitalo con **Quitar** (no hace falta pedirlo).
4. Cambiá la cantidad de la Lechuga a **0**, dejá la fecha límite de hoy y ningún proveedor tildado, y tocá **Revisar pedido**: tienen que verse a la vez, cada uno junto a su campo, «Ingresá una cantidad mayor que cero», «La fecha límite tiene que ser desde el…» y «Tenés que invitar al menos a un proveedor». Lo que escribiste se conserva.
5. Corregí: Lechuga **20**, fecha límite dentro de 3 días. En «A quién se lo pedís» está el filtro «Los que venden lo que pedís» (solo «Semillas del Sur», con la marca verde). Tocá **Seleccionar todos** (se marca solo ese) y después elegí «Todos los proveedores», **Filtrar** y **Seleccionar todos**: se marcan los dos. «Agro Norte» u otro proveedor dado de baja no aparece.
6. **Revisar pedido**: el resumen agrupa por invernadero, con precio de referencia y subtotal, y suma **$ 550,00** (20 × 12,50 + 3 × 100,00). **Volver a corregir** vuelve al formulario sin errores. Entrá de nuevo al resumen y tocá **Confirmar pedido**.
7. Llegás a la ficha del pedido, con el aviso «Enviamos el pedido P-… a 2 proveedores.». En la terminal aparecen **dos correos**, cada uno con un enlace distinto (`/proveedor/…`), el detalle, la dirección del invernadero y la fecha límite, y **sin ningún precio**. Los dos invitados figuran «No cotizó» con el enlace «Vigente».

**Como proveedor** (ventana privada, sin iniciar sesión; copiá el enlace del correo de «Semillas del Sur»):
8. Al abrir el enlace, la barra de direcciones pasa a `/proveedor/enlace/` (sin el código). Ves el pedido: insumos con su descripción y cantidad, dónde se entrega y hasta cuándo se puede cotizar; **no** ves precios de referencia ni al otro proveedor.
9. Tocá **Revisar y enviar** sin completar nada: «Cotice al menos un detalle». Después poné en la Lechuga cantidad **0**, precio **10,123** y plazo **0**, y una validez anterior a la fecha límite: los cuatro errores salen junto a cada campo.
10. Cotizá la Lechuga con cantidad **20**, precio total **250** y plazo **3**, y el Nutriente con cantidad **4** (más de lo pedido: se acepta), precio total **120** y plazo **2**. **Revisar y enviar**: el resumen muestra el precio unitario calculado y la advertencia «se envía una sola vez». **Enviar cotización**.
11. Ves «Recibimos su cotización…» y, en la terminal, el **acuse** con el monto $ 370,00. Volvé a abrir el enlace: «Ya envió su cotización», en solo lectura, sin botón para enviar otra.

**De vuelta como Ana y como Gerente:**
12. Como Ana, abrí el pedido: «Semillas del Sur» figura «Cotizó» con el enlace «Usado», y la cotización se ve completa en «Cotizaciones recibidas» (solo se pueden ver). En la campana hay **un aviso**: «Pedido P-… cubierto» (con la tolerancia en 0 %, 20 y 4 cubren 20 y 3). Pedí la cotización del otro proveedor con el **precio unitario** (elegí «Precio unitario» arriba: el rótulo cambia): **no** llega un segundo aviso.
13. Como Gerente: *Compras → Pedidos* (sin «Nuevo pedido»; dice «modo consulta»); abrí el pedido y comprobá que no hay ningún botón de cambio. Si escribís `/compras/pedidos/nuevo/` en la barra, da 403. *Auditoría*: «Alta de pedido de cotización» (de Ana) y dos «Alta de cotización» con «**Proveedor (mediante enlace)**» como quien actuó; abrí una y miralo en el detalle.
14. *Compras → Proveedores → Semillas del Sur S. A.*: la tarjeta «Pedidos» lista el pedido (con «Cotizó») y, al editarlo, el **CUIT ya no se puede cambiar**.
15. (Opcional) Con el correo **sin** configurar (quitá `CORREO_CONSOLA`), hacé otro pedido: en la ficha, cada invitado figura «No se pudo enviar» y aparece el aviso «No se pudo enviar la invitación a …: pedile al Gerente que revise su correo y reenviá la invitación» (el reenvío es CMP-02b).
16. Con la otra Agrónoma o el Capataz, abrí la ficha del pedido (`/compras/pedidos/<número>/`): 403.
17. (Opcional, a mano en la base) Poné la fecha límite del pedido en el pasado: el enlace del proveedor da «Este enlace no se puede usar · El plazo para cotizar terminó.» y el pedido figura «Fecha límite vencida».
18. (Opcional) Sin JavaScript (desactivalo en el navegador) y en un celular (ancho 390 px): «Nuevo pedido» y el portal siguen funcionando; solo el rótulo del precio deja de cambiar con la elección.
19. **Navegador real (D-96).** Los pasos 8 a 11 ya son en una ventana privada: **enviá la cotización hasta el final** y comprobá que aparece «Recibimos su cotización…» y no una página «Prohibido (403)» o «Verificación CSRF fallida»; abrí la consola del navegador (F12) y que no haya errores en rojo. Repetí lo mismo con el pedido del paso 6 (**Confirmar pedido**) y con el formulario de habilitar del paso 3. Es lo único que el recorrido con el cliente de Django no puede ver: el CSRF, el encabezado `Origin` y el JavaScript. (Un defecto así existió: con `Referrer-Policy: no-referrer` el portal no podía enviar nada en Chromium; se corrigió con `same-origin`.)

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo.** Los tres casos de uso (CMP-RLZ-PED, CMP-ENV-COT y CMP-CNS-PED), en cinco pasos, con las pruebas de los servicios escritas primero y mostradas fallando antes de implementar (el estudiante las revisó en cada paso).

- **Modelos y migraciones** (`compras/models.py`): `Pedido`, `DetallePedido`, `InvitacionPedido`, `EnlaceProveedor`, `Cotizacion` y `DetalleCotizacion`, con todas las restricciones del extracto (**C8** por la única `(pedido, proveedor)`); `compras/migrations/0002_pedidos_y_cotizaciones.py` y `core/migrations/0028_acciones_de_pedido.py` (solo `choices`: `alta_pedido` y `alta_cotizacion`).
- **`core/models.py`:** `ROL_CLIENTE_ENLACE` y `ROL_PROVEEDOR_ENLACE` (D-65 punto 8, D-88 punto 5: `rol_externo` **no existía**; lo creó esta tarea, COM-04c solo suma su uso), el argumento `rol_externo` de `RegistroAuditoria.objects.registrar` (solo sin cuenta y con una de las dos constantes), las dos acciones (de negocio), `ETIQUETAS` nuevas y los roles externos y los estados del pedido en `VALORES_VISIBLES`; y las dos plantillas de auditoría, que muestran el origen externo en lugar de «InfoPonia».
- **Servicios:** `compras/precios.py` (D-89), `servicios/cobertura.py`, `servicios/pedidos.py` (`insumos_bajo_el_minimo`, `insumos_pedibles`, `ya_pedido`, `proponer_fecha_limite`, `categorias_del_pedido`, `proveedores_invitables`, `resumir_pedido`, `registrar_pedido`, `consultar_pedidos`, `ficha_de_pedido`), `servicios/enlaces.py`, `servicios/cotizaciones.py`, `servicios/avisos.py` (`destinatarios_por_destino`, D-87 punto 3) y `servicios/inicio.py`; en `servicios/proveedores.py`, `tiene_pedidos_u_ordenes` y `pedidos_del_proveedor`.
- **Pantallas:** `compras/views_pedidos.py` (lista, ficha y «Nuevo pedido»), `views_proveedor.py` y `urls_proveedor.py` (el portal público, `proveedor/` en `config/urls.py`), plantillas en `compras/templates/compras/pedidos/` y `proveedor/`, los correos de invitación y de acuse (`correo/`), la sección «Compras» del Inicio del Agrónomo, la tarjeta de pedidos de la ficha del proveedor, las pestañas «Pedidos» y «Proveedores» y la entrada «Compras» del menú (abre en «Pedidos»); `static/compras/css/compras.css` y `js/portal.js` (solo cambia el rótulo del precio).
- **Verificación:** `compras/tests/test_recorrido_pedidos.py` y la «Verificación a mano» de arriba. La verificación visual con Playwright se hizo y después se retiró (D-96).

**Pruebas** (resultado del cierre): `python manage.py test compras core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **1121 en verde**; `python manage.py test compras --keepdb --tag concurrencia`: **7 en verde**; `makemigrations --check --dry-run`: sin cambios.
Son de CMP-02a: modelo 19, precios 13, cobertura 12, CMP-RLZ-PED 44, enlaces 21, CMP-ENV-COT 57, avisos 9, CMP-CNS-PED 27, pantallas 39, recorrido 1 y 2 de `rol_externo` en `core` (más las 3 de concurrencia). Una prueba de CMP-01 **cambió con el permiso del estudiante**: `MenuDeComprasVistaTests` ahora dice que «Compras» abre en «Pedidos» (antes «Proveedores», la única pestaña); no se borró ni se debilitó ninguna otra.

**Decisiones y desvíos** (propuestos para `docs/temas_abiertos.md`; el 1 propone una enmienda de D-88):

1. **`Referrer-Policy: same-origin`, no `no-referrer` (D-88 punto 4).** Con `no-referrer`, Chromium manda `Origin: null` en los POST del mismo sitio y el CSRF de Django los rechaza: el portal no podía enviar la cotización en un navegador real (lo encontró un navegador real, antes de D-96). `same-origin` protege igual (el token solo viaja en `/proveedor/<token>/`, que responde una redirección sin página, y a otro sitio no se manda ningún `Referer`). **COM-04c va a tropezar con lo mismo** en el portal del cliente (`docs/patrones/enlace_del_cliente.md`, sección 4, punto 3): conviene enmendar los dos patrones.
2. **Cotizaciones visibles desde que llegan** (regla 6 de CMP-CNS-PED y prototipo; decisión del estudiante, 23/11/2026). «Cómo se aplica» de `pedidos.md` decía «solo después del final del día de la fecha límite»: hay que corregirlo.
3. **Regla 4c incompleta a propósito:** «ya pedido» cuenta solo los pedidos «en cotización»; la parte de la orden «pendiente de aprobación» la completa CMP-03, que crea `OrdenCompra`.
4. **Correo de invitación que falla:** el aviso va en la pantalla del paso 13 con el texto de D-88 punto 6 y la ficha marca «No se pudo enviar»; **sin notificación de campana** para quien actuó (H21; decisión del estudiante).
5. **Aviso de pedido cubierto:** va a `destinatarios_por_destino` (D-87 punto 3: el Agrónomo activo de cada invernadero de destino, o el Gerente), no solo «al Agrónomo que realizó el pedido» como dice el caso de uso; y es una notificación **dentro** de la transacción (D-42), no «fuera» como dice el caso de uso (para que no quede un aviso de algo que se revirtió).
6. **Identificador `P-0031`** (el de «Cómo se aplica» de CMP-02b), no `PED-0031` del prototipo (decisión del estudiante).
7. **Tolerancia del 100 %:** con ese valor todo pedido queda «cubierto» sin cotizaciones y el aviso nunca sale (se compara antes y después). No se probó ese borde; conviene decidir si «cubierto» exige al menos una cotización.
8. **Cobertura exacta:** el mínimo `pedida × (1 − tolerancia)` no se redondea a dos decimales (el prototipo redondea en `tolMin`); manda el caso de uso («alcanza la cantidad × (1 − porcentaje)»).
9. **Unitario mostrado:** el de cuatro decimales redondeado a dos (la función única de D-89 punto 1); si unitario × cantidad no da el total, se muestra solo el total (D-89 punto 7).
10. **La auditoría sigue sin distinguir a los actores externos en el filtro «InfoPonia»** de `consultar_auditoria` (`usuario` nulo): filtrar por «InfoPonia» trae también las cotizaciones de los proveedores. No se tocó `core/servicios.py` (fuera de «Permitido fuera de la app»).
11. **`core` fuera de lo listado en «Permitido fuera de la app»** (aprobado por el estudiante): `ETIQUETAS` y `VALORES_VISIBLES` (los roles externos y los estados del pedido) y las dos plantillas de auditoría.
12. **«Nuevo pedido» es un formulario que se vuelve a dibujar con cada botón** (sin JavaScript ni HTMX, porque `interfaz.md` prohíbe validar y recalcular mientras se escribe). En la extensión 3a el insumo se elige de un selector agrupado por invernadero, **sin buscador por nombre ni por tipo** (la «Lista de tecnología» 3a lo menciona); el filtro propuesto de proveedores por categoría **sí** está completo (no se recortó).
13. **El correo de invitación y el portal hablan de «usted»** (como el prototipo y los textos `ENL_MSG`); las pantallas internas, de «vos».
14. **Un token inexistente da 404** con «Este enlace no es válido»; uno que no sirve da 200 con «Este enlace no se puede usar» y el motivo, sin datos del pedido.
15. `ErrorDeCompras` suma `enlace_no_sirve` (con la `situacion`) y `ya_cotizo`. El servicio reutiliza `_actor_sigue_activo` (privada de `maestros`), como `proveedores.py`.
16. **En las pruebas**, en un `TestCase` el `on_commit` no corre solo y la redirección sigue antes de ejecutar `captureOnCommitCallbacks`: las pruebas de las pantallas y el recorrido lo reemplazan por una llamada inmediata, que es lo que pasa en producción.
17. Los pedidos y las órdenes de la ficha del proveedor (regla 4 de CMP-CNS-PRV) muestran hoy solo los pedidos; las órdenes, pagos y reclamos se suman de CMP-03 a CMP-06.
19. **Datos borrados (regla del estudiante para la base local):** la base de pruebas `test_infoponia_cmp` y sus clones se recrearon con `--noinput` (la migración nueva no llega a los clones de `--keepdb`; `.claude/rules/pruebas.md`) y el cierre de cada corrida de pruebas descartó sus datos. **No se tocó la base local de desarrollo, ni el usuario administrador, ni se escribió ninguna contraseña.**
20. **Al bajar `main` (COM-02, #65) hubo dos choques, resueltos sin tocar lo de la colega:** (a) las dos tareas habían creado una migración `core` 0027; la de CMP-02a pasó a **0028** (`0028_acciones_de_pedido`, depende de `0027_comercial_compra_venta`) y `compras` 0002 depende de ella; (b) `RegistroAuditoria.ETIQUETAS` ya traía `detalles` («Detalles»), `lineas` («Líneas de reserva») y `monto_estimado` de la compra-venta: mis claves repetidas las pisaban en silencio y habrían cambiado el texto de sus pantallas; se sacaron y las líneas de la cotización usan `lineas_cotizadas`. La acción y las etiquetas de COM-02 quedaron intactas.
18. «Pedidos por resolver», que `panelAgr` suma como indicador, es de CMP-03 (la tarea lo dice); acá solo «Insumos bajo el mínimo» y «Esperando cotizaciones».

### Pantallas: lo que se corrigió del prototipo

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| `VIEWS.c_pednew` (alta de insumos) | Un renglón con un selector de insumo por invernadero y recálculo mientras se escribe | Los insumos bajo el mínimo con «Agregar», el catálogo agrupado por invernadero y «Quitar»; el resumen se calcula al apretar «Revisar pedido» | Pasos 2 a 4 y extensión 3a de CMP-RLZ-PED; `interfaz.md` (nada de recálculos al tipear) |
| `VIEWS.c_pednew` (3a.1a) | No ofrecía habilitar un insumo | Ventana «Habilitarlo en un invernadero» (mínimo y precio) que vuelve al pedido con el insumo agregado | Extensión 3a.1a de CMP-RLZ-PED |
| `VIEWS.c_pednew` (proveedores) | Chips con la lista completa y un orden por «vende lo que pide» | Filtro propuesto por las categorías de lo que se pide, «Todos» o una categoría, y «Seleccionar todos» solo de la lista filtrada | Paso 6, extensiones 7a y 7b de CMP-RLZ-PED; H13, MD-121 |
| `VIEWS.c_pednew` (Enter) | Cualquier botón podía dispararse con Enter | El primer botón del formulario es «Revisar pedido» (oculto): Enter nunca agrega ni quita un insumo | Se vio con un navegador real; criterio de la regla D-61 |
| `VIEWS.c_pednew` (fecha) | Fecha límite desde «posterior a hoy» | Fecha límite desde mañana, con la propuesta de la configuración operativa | Regla «Fecha límite de cotizaciones»; extensión 8a |
| `VIEWS.c_pednew` (resumen) | No había resumen: enviaba directo | Pantalla de resumen con el monto, la fecha, los proveedores y las advertencias de 4c, con «Confirmar pedido» y «Volver a corregir» | Pasos 9 y 10 y extensión 10a de CMP-RLZ-PED |
| `VIEWS.c_pednew` (correo que falla) | Un aviso emergente con el reintento «desde el pedido» | Aviso en la pantalla del paso 13 con qué hacer, y «No se pudo enviar» en la ficha; sin reintento (es «Reenviar invitación», CMP-02b) | Extensión 12a; D-88 punto 6; H21 |
| `tabPed` | Filtros que se aplican al elegir, sin distinguir fecha del pedido y fecha límite | Botón «Filtrar», «Quitar filtros», fecha de pedido o de la fecha límite, estado vacío con filtros; el Gerente suma «Agrónomo» | Regla 2 de CMP-CNS-PED; `interfaz.md` |
| `tabPed` / `c_ped` (acciones) | «Resolver» y «Cancelar pedido» siempre | No se muestran (CMP-02b y CMP-03 las suman); el Gerente ve «modo consulta» | Regla 1 y 8 de CMP-CNS-PED; D-30 |
| `VIEWS.c_ped` (cotizaciones) | Solo se podían ver «hasta el final de la fecha límite» | Se ven en solo lectura desde que llegan | Regla 6 de CMP-CNS-PED (decisión del estudiante) |
| `VIEWS.c_cotz` (selector «enlace de ejemplo») | Barra solo del prototipo para elegir un enlace | Se quitó; el portal abre por el token real | «Solo prototipo» de la tarea |
| `VIEWS.c_cotz` (precio) | Un conmutador que borraba lo escrito | Un grupo de opciones «Precio total» o «Precio unitario» que solo cambia el rótulo de los campos; el otro valor se calcula en el resumen | D-89 punto 2; `interfaz.md` |
| `VIEWS.c_cotz` (cantidad y plazo) | Cantidad mayor que la pedida rechazada con «entero ≥ 0» | Cantidad mayor que la pedida aceptada y plazo entero de 1 o más | Actualizaciones de A0 (P2, MD-130) |
| `VIEWS.c_cotz` (errores y estados) | Mensajes de un enlace usado solo para ese estado | Pantallas «no válido» (404), «no se puede usar» con el motivo, resumen con advertencia y solo lectura | Extensiones 2a, 2b, 9 y 11 de CMP-ENV-COT |
| `panelAgr` | «Insumos bajo el mínimo», «Pedidos por resolver», «Por recibir» y «Esperando cotizaciones» | Solo «Insumos bajo el mínimo» (con «Pedir») y «Esperando cotizaciones»; el resto es de CMP-03 y CMP-04 | Extensión 1a de CMP-RLZ-PED; la tarea |
| Estados vacíos, de error y de celular | No estaban | Se agregaron (sin pedidos, sin insumos bajo el mínimo, sin proveedores, errores por campo, tarjetas que no se cortan en un celular) | D-61 punto 2 |
