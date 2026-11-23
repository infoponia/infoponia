# Revisiones a mano pendientes — InfoPonia

Pasos que una persona tiene que hacer a mano (en el navegador, en Render o en GitHub) y que las pruebas no cubren.
Claude Code no lee este archivo salvo que el estudiante lo pida; `docs/estado.md` tiene una línea por sección.

Cómo se usa (regla M5):

- Quien hace un paso lo tacha acá (`~~...~~`, con la fecha) en el mismo commit o PR en que lo hace, y actualiza la línea
  de esa sección en `docs/estado.md`.
- Cuando una sección queda toda tachada, se borra de acá y de `estado.md`, y se anota una línea en `docs/historial.md`.
- Al cerrar una tarea, Claude Code propone su sección nueva con los pasos de su «Verificación a mano».

Copiado sin cambios de `docs/estado.md` («En curso» y «Siguiente», punto 1) el 18/11/2026. Puede haber pasos ya hechos
que nadie tachó: revisalos antes de empezar.

## UX · Tarea chica de experiencia de uso

Revisión a mano de la tarea chica de experiencia de uso (JavaScript, no probado en un navegador):

1. Doble clic y doble Enter en un formulario con el servidor lento: llega un solo POST.
2. El botón muestra el indicador y el verbo, no cambia de ancho y se restaura al volver atrás desde el caché.
3. Con «Reducir movimiento» activado en el sistema, el indicador no gira.
4. Con JavaScript desactivado, el formulario envía igual.
5. Servidor apagado o sin red, clic en «Restablecer» o «Dar de baja»: aviso «Revisá tu conexión…», la pantalla no
   cambia y el aviso se cierra solo a los 10 s.
6. Un 500 en un pedido de HTMX (forzado en local) muestra «Volvé a intentarlo.», sin mencionar la conexión; un
   pedido que supera los 30 s, el de la conexión.
7. Sesión vencida en `/usuarios/` con un Gerente, entra un Capataz en el mismo navegador: llega a su inicio.
8. Al deshabilitarse el botón enfocado dentro de una ventana, el foco se pierde (comportamiento del navegador):
   ver si molesta.

## USR-08 · Tarea 08

Tarea 08 (correo y recuperación de contraseña), a mano:

1. En local, con `DJANGO_DEBUG=1` y `CORREO_CONSOLA=1` en `.env`: pedir el enlace desde el inicio de sesión, ver el
   correo en la consola de `runserver`, abrir el enlace, elegir una contraseña nueva y entrar con ella. La URL de «Elegí
   una contraseña nueva» no lleva el token.
2. Abrir el mismo enlace una segunda vez, y uno viejo después de iniciar sesión: «Enlace no válido» con «Pedir un enlace
   nuevo».
3. Sin `CORREO_CONSOLA`: el inicio de sesión muestra el aviso y `/recuperar-contrasena/` no tiene formulario.
4. En Render: cargar `EMAIL_HOST_USER` (`infoponia.notificaciones@gmail.com`) y `EMAIL_HOST_PASSWORD` (contraseña de
   aplicación de Google) en las variables de entorno; confirmar que `DJANGO_ALLOWED_HOSTS` no tenga `*`; hacer un pedido
   real y comprobar que el enlace del correo empieza con `https://` y que el correo llega (revisar también la carpeta de
   correo no deseado).
5. El botón «Enviar enlace» muestra «Enviando…» y no deja enviar dos veces (JavaScript, D-29).

## USR-08b · Tarea 08b

Tarea 08b (invitación por correo), a mano:

1. En local, con `DJANGO_DEBUG=1` y `CORREO_CONSOLA=1` en `.env`: «Nuevo usuario» muestra el radio con la invitación
   marcada. Al dar de alta con la invitación, la consola de `runserver` imprime el correo con el enlace; abrirlo, elegir la
   contraseña y entrar con ella. La URL de «Elegí tu contraseña» no lleva el token.
2. La lista y la ficha de esa cuenta, antes de aceptar, muestran «Invitación pendiente». Reenviar la invitación
   (Restablecer acceso, eligiendo la invitación) deja sin efecto el enlace anterior.
3. Sin `CORREO_CONSOLA`: el alta y las ventanas de restablecer y reactivar no muestran el radio y dan la temporal de
   siempre.
4. Con una falla de envío (por ejemplo, `EMAIL_HOST_PASSWORD` mal cargada en Render): el alta o el restablecimiento
   avisan con el aviso de error y ofrecen «Restablecer acceso»; la cuenta queda con la invitación pendiente.
5. En Render, con el correo cargado: dar de alta una cuenta propia con la invitación, ver que llega (y en qué carpeta) y
   que el enlace empieza con `https://`.
6. Los botones «Dar de alta», «Restablecer» y «Reactivar» muestran «Dando de alta…», «Restableciendo…» y «Reactivando…» y
   no dejan enviar dos veces (JavaScript, D-29).

## AUD-01 · Tarea AUD-CNS-REG

> Nota del traspaso: el PR #26 ya está mergeado en main, así que Render ya corrió la `0008`. Si el despliegue
> terminó bien, el paso 1 se cumplió: tachalo.

Tarea AUD-CNS-REG (auditoría), a mano:

1. Antes de mergear: Render corre `migrate` y la `0008` falla, sin cambiar nada, si encuentra un detalle viejo que no
   reconoce. Probarla contra una copia de la base de producción, o mirar los detalles de `core_registroauditoria` en Neon.
2. En local, con registros reales (alta, modificación, baja, reactivación, restablecimiento, vinculación...): entrar
   como Gerente y como Administrador a «Auditoría» y comprobar que cada registro muestra bien la tabla Campo / Antes /
   Después y los datos de contexto, con «—» para los valores nulos y los textos de las cuentas y de los grupos.
3. Los filtros con el navegador: fechas, la cuenta que actuó (incluida «InfoPonia»), acción y cuenta afectada; los
   desplegables con teclado; el paginado (hace falta pasar de 25 registros) y que «Volver» desde el detalle deje la
   misma lista. Con JavaScript desactivado, «Filtrar» envía el formulario.
4. «Ver auditoría» en la ficha de una cuenta: abre la lista con la etiqueta «Registros de … (actuó o fue afectada)» y
   «Quitar filtro» la saca. Como Gerente, probar a mano `?actuo=<id de un Administrador>`: da 403.
5. Que el Gerente no vea lo que solo involucra a Administradores o a su cuenta (por ejemplo, el cambio de su propia
   contraseña), y que el Administrador vea todo.
6. Los índices (D-36) no se midieron con `EXPLAIN` en una tabla grande; revisar cuando haya volumen.

## MAE-02b · Tarea MAE-02b (alerta: baja y reactivación de cuenta, Inicio del Gerente y `abrir_alerta`)

Tarea MAE-02b (maestros y core), a mano. Con el entorno virtual activo y la base local (`python manage.py runserver`, con `DEBUG` encendido para usar `/admin/`). **No hay
migraciones.** Cuentas: un Gerente, un Agrónomo, un Capataz y un Vendedor activos, y dos invernaderos («Sur» y «Norte») creados
con «Nuevo invernadero».

1. Iniciá sesión como Gerente. En «Panel de control» aparece «Personal por asignar» con los invernaderos activos que no tienen todo
   su personal (por ejemplo, «Falta Agrónomo · Falta Vendedor»). «Asignar» abre «Modificar» de ese invernadero.
2. Asigná el personal que falta a todos los invernaderos activos: el Inicio pasa a decir «Todos los invernaderos activos tienen su
   personal asignado.». Sin ningún invernadero activo no dice nada.
3. Dejá a un Capataz a cargo de «Sur» y «Norte» y dá de baja uno de los dos (con «Modificar» y «Dar de baja») para tener uno inactivo.
   En «Usuarios y seguridad», abrí la ficha de ese Capataz → «Dar de baja»: la ventana lista «Lo que tiene asignado» (solo el
   invernadero activo) y la alerta que quedará.
4. Confirmá la baja. En «Auditoría» aparece «Baja de usuario» con «Alertas creadas» (una) y el invernadero entre los afectados. En
   `/admin/` hay una alerta «Invernadero sin Capataz activo» para el Gerente, activa y no leída, y ninguna en el inactivo. El Inicio
   muestra «Capataz inactivo (nombre)» en el invernadero.
5. Reactivá la cuenta del Capataz: «Auditoría» muestra «Alertas resueltas»; en el admin la alerta queda resuelta, con su fecha de
   resolución. El invernadero deja de figurar en el Inicio solo si no le falta otro rol: si también le falta el Agrónomo o el
   Vendedor, sigue listado con lo que falta.
6. Repetí 3 a 5 con un Agrónomo: se crea y se resuelve «Invernadero sin Agrónomo activo». El traspaso de MD-61 y D8 no se ve a mano
   (ningún tipo de `maestros` va al Agrónomo): lo cubren las pruebas.
7. Dá de baja a un Agrónomo sin alertas activas: la ventana lista sus invernaderos pero no la línea «Alertas activas».
8. Dá de baja a un Gerente (como Administrador, desde «Cuentas») y a un Administrador (con otro activo): la ventana de baja no
   muestra «Lo que tiene asignado».
9. Iniciá sesión como Agrónomo (a cargo de un invernadero al que le falta el Capataz o el Vendedor): su Inicio no muestra «Personal
   por asignar».
10. Sin JavaScript (desactivalo en el navegador): los pasos 3 a 5 funcionan igual (la ventana de baja viene en la ficha) y «Asignar»,
    en el Inicio, es un enlace común.
11. `abrir_alerta` y CU-46 no tienen pantalla todavía.
12. `python manage.py test maestros core --keepdb --tag concurrencia` da 34 pruebas OK. Después, una vez,
    `python manage.py test maestros core --keepdb --exclude-tag concurrencia --exclude-tag migracion`: da 941 OK (las de
    concurrencia vacían Georef y `ConGeoref` lo vuelve a cargar solo).
13. No hay migraciones: el despliegue de Render no cambia la base.
14. Después del despliegue: entrá como Gerente en Render y confirmá que «Personal por asignar» aparece y que lista los invernaderos
    viejos (creados antes de MAE-02a) a los que les falta personal (D9: sale de lo que falta, no de las alertas).

## UI-01 · Tarea UI-01 (estilo «Diseño v2», marco e identidad de la organización)

Tarea UI-01 (core y maestros), a mano. Con el entorno virtual activo: `python manage.py runserver`. **No hay migraciones.** Cuentas: Gerente, Agrónomo, Capataz y Administrador.

1. Escritorio, con cada rol: el marco tiene cabecera con marca y nombre, menú lateral por rol y pie. Entre el espacio y el menú de cuenta está el botón de la campana (NOT-01), salvo para el Administrador.

2. A 375 px: el menú lateral desaparece y aparece la fila de fichas con las mismas entradas (Gerente, Agrónomo, Administrador). El Capataz usa el marco de celular y no la ve.
3. Sin JavaScript (desactivarlo en las herramientas del navegador): inicio de sesión, lista de usuarios y lista de invernaderos se ven y funcionan; los desplegables quedan nativos.
4. Guardar algo (por ejemplo, Mi perfil): el aviso breve sale arriba a la derecha (abajo, sobre el pie, a 375 px) y se va a los 10 s o con la cruz.
5. Recorrer, en escritorio y a 375 px: inicio de sesión; Panel de control de cada rol (el del Gerente con «Personal por asignar»); Mi perfil; Usuarios (lista, alta, ficha, modificar, baja y ventanas); Auditoría (lista y registro); Producción (lista, ficha, alta, modificar, baja y reactivar de un invernadero). Ninguna pantalla debe verse con el aspecto viejo (bordes de 4 px, letra de consola).
6. El color de la organización no se puede ver en pantalla hasta MAE-04 (lo registra); lo cubren las pruebas de `core/tests/test_identidad.py`. Se revisa en MAE-04.

## NOT-01 · Tarea NOT-01 (notificaciones y campana)

Tarea NOT-01 (core y maestros), a mano. Hay una migración nueva: `python manage.py migrate`. Después, con el entorno virtual activo: `python manage.py runserver`. Cuentas: Gerente, Administrador, Agrónomo y Capataz. No hay navegador en la sesión de Claude Code: **el JavaScript de la campana (abrir, cerrar, pestañas, marcar como leídas) se probó solo con pruebas de las vistas y con `node --check`; lo recorrés vos.**

1. Con el Gerente, dar de alta un invernadero con Agrónomo y Capataz. Con cada una de esas cuentas: la campana tiene punto rojo y la pestaña dice «Notificaciones (1 sin leer)»; el título es «Quedó a cargo de <invernadero>» y el detalle, «El Gerente le asignó el rol de Agrónomo.» (o Capataz). Abrir la pestaña «Notificaciones» y cerrar el panel (clic en la campana, clic afuera o Esc): la notificación queda leída y, al volver a mirar, el punto desapareció.
2. Abrir el panel con la pestaña «Alertas» a la vista y cerrarlo: las notificaciones **no** quedan leídas (solo se marcan si se vio su pestaña). Cambiar de pestaña no recarga la página.
3. «Modificar» ese invernadero y cambiar el Agrónomo: el nuevo recibe el aviso con lo que recibe («Recibe: alertas activas: N.» si tenía alertas, o «No recibe nada pendiente.»); el anterior no recibe nada. Guardar sin cambiar nada, o cambiando solo el nombre, no genera avisos.
4. Con el Administrador, abrir la baja del Gerente: la ventana muestra «Pendientes del Gerente: N (Alertas activas para el Gerente: N)…» o «No tiene pendientes.». Dar de baja al Gerente y dar de alta uno nuevo: el nuevo tiene una notificación «Pendientes que esperan al Gerente» con el mismo total.
5. Con un invernadero sin Capataz, el Gerente ve en la pestaña «Alertas» la de «Invernadero sin Capataz activo», con el nombre del invernadero, su severidad (advertencia) y un enlace a la ficha. Mientras la alerta siga sin leer, el punto rojo del Gerente sigue prendido: abrir la ficha no la marca como leída (eso lo hace `abrir_alerta` desde la pantalla de alertas, MAE-02c). El Administrador no tiene campana.
6. Sin JavaScript (desactivalo en las herramientas del navegador): el botón de la campana abre la página completa «Alertas y notificaciones» con las dos pestañas (son enlaces); «Cerrar» marca las notificaciones solo si se estaba viendo esa pestaña y vuelve a la pantalla de donde se vino.
7. A 375 px el panel entra en la pantalla (con el Gerente) y, con el Capataz (marco de celular), se abre como hoja inferior y el botón de la campana mide al menos 44 px.

## MAE-03 · Tarea MAE-03 (sectores y cultivos)

Tarea MAE-03 (maestros y core), a mano. Hay migraciones nuevas: `python manage.py migrate`. Después, con el entorno virtual activo: `python manage.py runserver`. Cuentas: Gerente, dos Agrónomos (uno a cargo de un invernadero y otro no) y Capataz. `/admin/` solo existe con `DJANGO_DEBUG=1`.

1. `migrate` aplica las migraciones de `maestros` (0004 y 0005) y de `core` (0012). En `/admin/` hay cinco tipos de etapa con sus perfiles.
2. Con el Agrónomo a cargo: ficha del invernadero → «Sectores»: aparece el aviso «sin sectores». «Agregar sector» con nombre repetido (mayúsculas distintas) muestra el error; con total 0 también.
3. Agregar tres sectores de tipos distintos: se agrupan por etapa con su cantidad de sectores y de agujeros; la marca «sin sectores» desaparece de la lista y de la ficha, y aparece la tarjeta «Capacidad». Un sector nuevo muestra «Sin plantas: acepta cualquier perfil» y todo libre.
4. Modificar: subir y bajar el total; cambiar el tipo del único sector de una etapa muestra el aviso («variedades que dejan de poder sembrarse» sale con las variedades que cargue a mano en `/admin/`) y «Continuar igual» guarda; «Volver» no guarda. Guardar sin cambios no crea registro en «Auditoría» (D-28).
5. Dar de baja un sector: pasa a «Dados de baja», sin acciones salvo «Reactivar». Reactivarlo: vuelve activo.
6. Con el Gerente: ve los sectores de cualquier invernadero pero ninguna acción. Con el Agrónomo ajeno: 403 en la ficha y en las rutas de sectores (regla 1 de PROD-CNS-SCT).
7. Dar de baja el invernadero: «Auditoría» muestra un log por sector con la baja. Reactivar el invernadero no reactiva sus sectores (regla 6 de PROD-BAJ-INV).
8. «Producción» → «Cultivos y variedades» (Agrónomo): alta de «Acelga»; el nombre repetido da error; renombrar a «Acelga común»; dar de baja y reactivar. El Gerente no ve la pestaña y `/produccion/cultivos/` le da 404.
9. En `/admin/`, crear una variedad activa del cultivo: la baja del cultivo dice cuántas variedades activas tiene y no deja.
10. Sin JavaScript, los pasos 3, 4 y 8 funcionan igual (cada ventana es una página).
11. `python manage.py test maestros --keepdb --tag concurrencia` pasa. Después, una vez, la corrida sin concurrencia: el mixin vuelve a cargar los tipos de etapa.
12. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.


## MAE-04 · Tarea MAE-04 (configuración operativa y perfil de la organización)

Los 10 pasos están en «Verificación a mano» de `docs/tareas/maestros/MAE-04-configuracion-y-organizacion.md`. Hay migraciones nuevas: `python manage.py migrate`. Cuentas: Gerente, Agrónomo y Administrador. `/admin/` solo existe con `DJANGO_DEBUG=1`.

1. `migrate` aplica `maestros` 0006 y 0007 y `core` 0013; una fila de cada singleton en `/admin/`.
2. «Configuración» al final del menú del Gerente; 403 para Agrónomo, Capataz y Administrador.
3. Errores por campo y todo o nada en «Parámetros operativos»; advertencia del horizonte (10 con pre-reserva 14).
4. Sin cambios: sin registro en «Auditoría»; dos cambios: un registro con antes y después.
5. «Organización»: nombre vacío, CUIT, email, colores y color 2 sin el 1.
6. Color 1 `#2E7D32` tiñe el sistema; borrarlo vuelve a la paleta.
7. Nombre «Vivero Los Álamos» en el encabezado, el inicio de sesión y un correo.
8. Dos sesiones del Gerente: gana el último, sin error 500.
9. Sin JavaScript, los pasos 3 a 5 funcionan igual.
10. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## CON-01 · Tarea CON-01 (`OrigenDocumento`)

Los 6 pasos están en «Verificación a mano» de `docs/tareas/contabilidad/CON-01-origen-documento.md`. Hay una migración nueva: `python manage.py migrate`. No hace falta ninguna cuenta (no hay pantallas).

1. `migrate` aplica `contabilidad` 0001.
2. `makemigrations --check --dry-run` no detecta cambios.
3. En `shell`, `OrigenDocumento(tipo="bitacora").save()` falla con `TypeError` y un mensaje claro.
4. `OrigenDocumento.objects.count()` da 0.
5. `/admin/` no muestra «Documentos de origen» (esperado).
6. Después del merge: verificar en el log de Render que se aplicó la migración.

## INV-01 · Tarea INV-01 (tipos de insumo y catálogo)

Los 14 pasos están en «Verificación a mano» de `docs/tareas/inventario/INV-01-tipos-de-insumo-y-catalogo.md`. Hay migraciones nuevas (`core` 0014, `inventario` 0001 y 0002): `python manage.py migrate`. Cuentas: Agrónomo con invernadero, otro Agrónomo con otro invernadero, Gerente, Capataz y Administrador.

1. Cuatro categorías del sistema con candado y sin botones. 2. Menú «Inventario» solo del Agrónomo; 403 para los demás. 3. Alta de categoría con errores por campo. 4. Modificar, dar de baja y reactivar una categoría. 5. Alta de insumo y aviso de habilitar. 6. Semillas no se ofrece; las ocho unidades. 7. Baja de categoría con insumos activos. 8. Acciones deshabilitadas con el nombre de quien lo usa y notificación al modificar. 9. Baja con stock (también negativo). 10. Auditoría. 11. Modificación simultánea sin 500. 12. Sin JavaScript. 13. Fichas de consumo directo resaltadas. 14. Después del merge: migraciones en el log de Render.

## DIA-01 · Tarea DIA-01 (proceso diario sin cron job)

Los 3 pasos están en «Verificación a mano» de `docs/tareas/core/DIA-01-proceso-diario.md`. Sin migraciones. Se corren con PowerShell y el entorno virtual activo.

1. `python manage.py proceso_diario --listar` dice «No hay pasos registrados.» y `echo $LASTEXITCODE` da 0.
2. `python manage.py proceso_diario --fecha 2026-13-01` y `--fecha 2026-1-5` dan un error claro, sin traza de Python, y `echo $LASTEXITCODE` da 1.
3. Cuando INV-02 esté mergeada: `--listar` muestra «10 · revisar_vencimientos · Revisar vencimientos de insumos»; correrlo dos veces seguidas no duplica alertas; `--fecha` con un día de dentro de un mes genera las alertas «por vencer» que correspondan.

Los pasos están en «Verificación a mano» de `docs/tareas/inventario/INV-02-insumos-del-invernadero-stock-y-vencimientos.md`. Hay una migración nueva (`core` 0015): `python manage.py migrate`. Cuentas: Agrónomo con invernadero, otro Agrónomo, Gerente. Las pantallas no se vieron en un navegador antes del PR: empezá por ahí.

1. Habilitar y alerta «bajo el mínimo» con «Cargar stock inicial». 2. Cargas con vencimiento y errores por campo. 3. Existencias y lotes. 4. Recuento físico con lote nuevo. 5. Rotura y corrección entre lotes. 6. «Vencimiento» y «Dar de baja». 7. Consumo por encima del stock y faltante. 8. 403 para un Agrónomo ajeno; el Gerente no ve «Inventario». 9. Mínimo y precio con auditoría. 10. Deshabilitar y reactivar. 11. Baja del invernadero con stock. 12. `proceso_diario` y `revisar_vencimientos`. 13. Dos ajustes simultáneos. 14. Sin JavaScript. 15. Habilitar desde el catálogo y desde el aviso del alta. 16. Después del merge: migraciones en el log de Render.

## MAE-05 · Tarea MAE-05 (transportista del invernadero)

Los 10 pasos están en «Verificación a mano» de `docs/tareas/maestros/MAE-05-transportista-del-invernadero.md`. Hay una migración nueva (`maestros` 0008): `python manage.py migrate`. Cuentas: Gerente, un Agrónomo a cargo de un invernadero y tres Transportistas (uno se da de baja). Dos invernaderos activos, «Norte» y «Sur». Las pantallas no se vieron en un navegador.

1. «Personal por asignar» del Gerente lista a los tres Transportistas como «Transportista sin invernadero», con «Asignar».
2. Ficha de «Norte» → «Logística»: texto de vacío; «Agregar transportista» los lista a los tres con «Sin invernadero»; al agregar a uno hay aviso breve, aparece en la tabla, sale de «Personal por asignar», queda un `modificacion_invernadero` en «Auditoría» y el Transportista tiene su notificación.
3. Ficha de «Sur» → «Agregar transportista»: el de «Norte» aparece con «Trabaja para Norte»; la ventana avisa del traslado y pide «Confirmar traslado»; al confirmar pasa a «Sur» y «Auditoría» tiene dos registros, uno por invernadero.
4. Quitarlo de «Sur»: queda sin invernadero y vuelve a «Personal por asignar».
5. Agregar otro a «Norte» y dar de baja «Norte»: se rechaza con «Tiene 1 transportista activo…». Dar de baja la cuenta de ese Transportista y repetir: ya no lo impide. Reactivar «Norte» para seguir.
6. Ficha de la cuenta del Transportista (Gerente) y su «Mi perfil»: muestran «Invernadero» con el nombre o «Sin invernadero» (la nota solo en la ficha).
7. Con el Agrónomo: «Logística» sin botones; las URL de agregar y quitar dan 403.
8. Sin JavaScript, los pasos 2 a 4 funcionan igual: cada ventana es una página.
9. Con dos sesiones, agregar el mismo Transportista a dos invernaderos a la vez (o alcanza con la prueba de concurrencia): uno lo agrega y el otro ve el aviso de traslado, sin error 500.
10. Después del merge: verificar en el log de Render que se aplicó la migración nueva (el último paso, tras el despliegue).

## MAE-02c · Tarea MAE-02c (consulta de alertas)

Los 12 pasos están en «Verificación a mano» de `docs/tareas/maestros/MAE-02c-alerta-consulta.md`. No hay migraciones nuevas. Cuentas: Gerente, dos Agrónomos (a cargo de «Sur» y de «Norte»), un Capataz y un Administrador; invernaderos «Sur» y «Norte». Las pantallas no se vieron en un navegador.

1. Baja de un Capataz de «Sur»: alerta «sin Capataz» y punto rojo en la campana. 2. «Alertas» lista la alerta con su punto de «no leída»; listar no marca nada. 3. Filtros por «Norte» (vacío con mensaje) y por «Sur» y tipo. 4. El detalle muestra todo; la lista pierde el punto y la campana se apaga. 5. Reactivar al Capataz: sale de la lista y el detalle viejo dice «Resuelta». 6. Agrónomo de «Sur» (las suyas), Agrónomo de «Norte» (403 en la ajena, 404 en un id inexistente). 7. Capataz y Administrador: sin entrada y 403. 8. Abrir una alerta desde la campana. 9. Sin JavaScript. 10. Tipo no registrado desde `/admin/`. 11. Pruebas, y una vez la concurrencia. 12. Después del merge: sin migraciones que verificar en Render.

## INV-03 · Tarea INV-03 (variedades y semillas)

Los 14 pasos están en «Verificación a mano» de `docs/tareas/inventario/INV-03-variedades-y-semillas.md`. Hay migraciones nuevas (`maestros` 0009, `inventario` 0003 y `core` 0016): `python manage.py migrate`. **Antes de migrar, en tu base local y en Neon, borrá desde `/admin/` las variedades cargadas a mano (las que no tienen ciclo).** Cuentas: Gerente, dos Agrónomos (cada uno con un invernadero a cargo) y un Capataz; un cultivo «Lechuga». Las pantallas no se vieron en un navegador.

1. `migrate` pasa sin errores con la tabla de variedades vacía; con variedades a mano, falla con un mensaje claro.
2. «Cultivos y variedades» (Agrónomo): la tarjeta de «Lechuga» tiene «+ Variedad»; el Gerente no ve la pestaña y la URL le da 404.
3. «Nueva variedad» «Butterhead»: sin completar nada cada campo marca su error; «Hoja verde» ofrece solo Germinación, Crecimiento y Maduración, y «Frutos grandes» las cinco; mínimo mayor que el máximo y nombre repetido dan error.
4. Con datos válidos, «Revisar resumen» muestra el ciclo (suma), la cosecha estimada y «Semilla Lechuga Butterhead»; «Volver a editar» conserva lo escrito; «Crear variedad» lleva a «Qué sigue».
5. «Auditoría» (Gerente) tiene un solo `alta_variedad`; en «Inventario» → «Catálogo» aparece la semilla y no se puede modificar ni dar de baja desde ahí.
6. «Habilitar la semilla en un invernadero» abre la ventana de INV-02 con la semilla elegida y la habilita; la tabla muestra «Habilitada en Invernadero …».
7. Con el Agrónomo que no tiene a cargo ese invernadero, modificar y dar de baja se ven deshabilitados con «Solo la usa …»; con el otro, funcionan.
8. Cambiar nombre y una duración: el resumen muestra lo anterior, el nombre nuevo de la semilla y a quiénes se notificará; sin cambios no hay registro; con cambios, el otro Agrónomo recibe la notificación.
9. Renombrar el cultivo: el aviso dice cuántas semillas cambian y «Auditoría» muestra un `modificacion_semilla` por semilla.
10. Dar de baja con la semilla habilitada y con stock: la página informa dónde y cuánto; variedad y semilla quedan inactivas, la existencia sigue activa. «Reactivar» abre una confirmación; con el cultivo inactivo, «Primero reactivá el cultivo»; con el cultivo activo, no vuelve a habilitar nada.
11. Con lotes u órdenes simulados desde la consola (registrante falso, solo para probar): la baja lista todo junto y el perfil no se puede cambiar.
12. Dos Agrónomos crean «Butterhead» a la vez: una sola gana, la otra ve el error de nombre repetido, sin error 500.
13. Sin JavaScript, los pasos 3, 4, 8 y 10 funcionan igual (botón «Actualizar etapas»).
14. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas (el último paso).

## IOT-01 · Tarea IOT-01 (app `iot` y tipos de actuador)

Los 11 pasos están en «Verificación a mano» de `docs/tareas/iot/IOT-01-app-modelos-y-tipos-de-actuador.md`. Hay migraciones nuevas (`core` 0017, `maestros` 0010 e `iot` 0001 a 0003): `python manage.py migrate`. Cuentas: Gerente, un Agrónomo y, para el paso 6, un Capataz, un Vendedor o un Técnico. Las pantallas no se vieron en un navegador. El último paso se hace después del despliegue.

---

## PRD-01 · Tarea PRD-01 (siembra, órdenes y bandeja del Capataz)

Los 15 pasos son los de «Verificación a mano» de `docs/tareas/produccion/PRD-01-siembra-ordenes-y-bandeja.md`, copiados acá para ir tachándolos (M5). Hay migraciones nuevas (`core` 0018 y `produccion` 0001, esta última con la secuencia `produccion_orden_numero_seq`): `python manage.py migrate`. Las pantallas no se vieron en un navegador. Cuentas: Gerente, dos Agrónomos (cada uno con un invernadero a cargo), dos Capataces (uno por invernadero). Hace falta un invernadero con un Capataz activo, un sector por tipo de etapa, una variedad con ciclo y semilla **habilitada y con stock** en un lote vigente, y otra variedad de otro perfil familiar.

- [ ] 1. `migrate` pasa sin errores. «Producción» aparece en el menú del Agrónomo y «Mis órdenes» en Inicio y en el enlace «Ver todas» del Capataz (que no tiene menú lateral); el Gerente solo ve la lista y el detalle, en solo lectura.
- [ ] 2. «Nueva siembra»: sin completar nada, cada paso marca lo que falta. Un invernadero sin Capataz activo aparece deshabilitado con su motivo. Con una variedad de otro perfil familiar y un lote activo, la variedad aparece como no compatible y dice con qué conflicta.
- [ ] 3. Con datos válidos, la distribución por sector no deja pasar más que la capacidad libre; el resumen muestra la fecha estimada de cosecha, la distribución y las reservas. Confirmar crea la orden `OT-000N`; el Capataz recibe la notificación (campana). «Auditoría» (Gerente) tiene **un** registro `planificacion_siembra`.
- [ ] 4. En «Existencias de insumos», el stock libre de la semilla bajó en lo reservado y el stock actual no cambió. En «Sectores», los agujeros comprometidos subieron.
- [ ] 5. Planificar la misma orden otra vez: el rechazo de duplicado nombra la orden existente. Planificar más plantines que semillas libres: error de stock. Con la fecha de ayer: error.
- [ ] 6. Como Capataz: la bandeja muestra la orden en el grupo que corresponde. «Concretar siembra» en el celular (o con el navegador angosto): se propone la fecha de hoy y las cantidades planificadas; con menos plantines que los planificados pide el motivo (opcional); con 0 total, error.
- [ ] 7. Confirmar: aparece el lote `L-N` en «Lotes activos» de la ficha del invernadero, en Germinación, con su costo. La existencia de la semilla bajó, hay movimientos (uno por lote) con la fecha efectiva, y el Agrónomo recibe la notificación con las diferencias. «Auditoría» tiene **un** registro `concrecion_siembra`.
- [ ] 8. Dejar el stock de un insumo adicional en menos de lo consumido (con un ajuste previo): concretar no se rechaza, sale del «faltante sin lote» y aparece la alerta «stock inconsistente» para el Agrónomo.
- [ ] 9. Con otra orden «a realizar»: «Cancelar orden» pide el motivo, muestra qué libera, y al confirmar la deja cancelada; los agujeros comprometidos y el stock libre vuelven; el Capataz recibe la notificación. Concretar la orden cancelada da el mensaje del estado actual.
- [ ] 10. Intentar dar de baja el sector, la variedad o el invernadero con lotes: la baja lista los impedimentos. Cambiar el Capataz del invernadero (`modificar_invernadero`) con una orden «a realizar»: pasa al nuevo y queda en auditoría.
- [ ] 11. Dos Agrónomos (o dos pestañas) planifican a la vez sobre la última semilla: una gana y la otra ve el error, sin 500.
- [ ] 12. Sin JavaScript, los pasos 2, 3, 6, 7 y 9 funcionan igual.
- [ ] 13. Ficha del invernadero: la pestaña «Lotes activos» lista el lote con su etapa y su costo (Agrónomo y Gerente); «Órdenes de trabajo» lista las órdenes del invernadero en solo lectura. Con una entrega o un mantenimiento sueltos creados desde la consola, no aparecen en «Producción» ni en la bandeja.
- [ ] 14. El panel «Ritmo sostenible» no existe (recortado, paso 9): no hay que buscarlo.
- [ ] 15. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas (el último paso).


## PRD-02 · Tarea PRD-02 (transición de etapa y núcleo de la merma)

Los 10 pasos son los de «Verificación a mano» de `docs/tareas/produccion/PRD-02-transicion-de-etapa.md`, copiados acá para ir tachándolos (M5). Hay migraciones nuevas (`core` 0019 y `produccion` 0002): `python manage.py migrate`. Las pantallas no se vieron en un navegador. Cuentas: Gerente, dos Agrónomos (cada uno con un invernadero a cargo; el segundo sirve para el paso 8) y el Capataz del invernadero del primero. Hace falta lo de PRD-01 más un lote activo (concretá una siembra), un sector con lugar por cada etapa que sigue en el ciclo y, para probar el paso a Maduración, una variedad con ciclo de tres etapas (Germinación, Crecimiento y Maduración). Un lote recién sembrado está en Germinación: «Nueva transición» lo lleva a Crecimiento.

- [ ] 1. `migrate` pasa sin errores (`core` 0019 y `produccion` 0002). Como Agrónomo, «Órdenes de trabajo» muestra el botón «Nueva transición»; el Gerente ve la lista y el detalle en solo lectura, sin ese botón y con 404 si abre `/produccion/ordenes/nueva-transicion/`.
- [ ] 2. «Nueva transición»: se listan todos los lotes de tus invernaderos con su código, variedad, plantas, etapa actual → siguiente y fin estimado. Los que no se pueden trasladar aparecen deshabilitados con su motivo: en la última etapa, con otra transición «a realizar» (dice cuál es y para cuándo) o en un invernadero sin Capataz activo. Al elegir uno, la etapa destino la fija el sistema (no se elige) y la fecha propuesta es el fin estimado de la etapa actual; si ya pasó, propone hoy y dice cuántos días de atraso. Con otra fecha, «Actualizar fechas» informa la diferencia en días con el fin estimado, sin bloquear; con destino Maduración, muestra la fecha máxima de cosecha estimada.
- [ ] 3. La distribución por sector: con más plantas que la capacidad libre de un sector, error debajo del campo con esa capacidad; con menos o más que las del lote, «Ver resumen» dice cuántas faltan o sobran; los sectores de otro perfil familiar o fuera de servicio no se ofrecen y se explica por qué. «Ver resumen» no escribe (verificalo en la lista de órdenes). «Confirmar transición» crea la orden `OT-000N`; el Capataz recibe la notificación (campana); «Auditoría» (Gerente) tiene **un** registro `planificacion_transicion`; en «Sectores», los agujeros comprometidos subieron y los ocupados no. El lote ya no se puede elegir para otra transición.
- [ ] 4. Como Capataz (celular), «Mis órdenes» → «Concretar transición»: propone la fecha de hoy y las cantidades planificadas, y dice entre qué fechas se puede elegir. Una fecha posterior a hoy da error; una anterior a la fecha mínima da el error con su explicación (entrada a la etapa o último registro de la bitácora); una anterior a la creación de la orden se acepta y la notificación al Agrónomo lo avisa.
- [ ] 5. Ubicar menos plantas que las del lote y pedir el resumen: aparece el campo «Causa» (obligatoria; sin ella, error) y el resumen muestra las plantas perdidas con su causa. Con 0 plantas en total, error «sin plantas trasladadas»; con más de las planificadas en un sector, error con lo planificado. Confirmar: el lote pasa a la etapa nueva con la cantidad ubicada, los sectores de origen quedan libres, el Agrónomo recibe la notificación con lo planificado y lo realizado por sector, y «Auditoría» tiene **un** registro `concrecion_transicion` (con la merma adentro, sin un `registro_merma` aparte).
- [ ] 6. En «Lotes activos» de la ficha del invernadero, el lote tiene la etapa nueva y el costo por planta **igual** que antes de la merma (cambió el costo total, no el unitario). Si la merma superó el 15 % de la cantidad inicial, el Agrónomo y el Gerente tienen la alerta «Merma sobre el umbral» (una sola vez, aunque haya otras mermas); con la causa «descarte por selección» no suma ni alerta.
- [ ] 7. Cancelar una transición «a realizar» (como Agrónomo, «Cancelar orden»): la pantalla muestra el lote, la etapa actual y la destino y los agujeros que libera, e indica que no tiene reservas de insumo; pide el motivo (sin él, error debajo del campo); al confirmar libera los agujeros comprometidos, el Capataz recibe el aviso con el motivo, el lote conserva su etapa y sus plantas y vuelve a aparecer disponible en «Nueva transición».
- [ ] 8. Con dos Agrónomos (o dos pestañas del mismo) planificando la misma transición a la vez: uno gana y el otro ve el error «ya tiene la transición…», sin 500. Con dos pestañas, concretar y cancelar la misma orden a la vez: una sola gana y la otra ve el estado actual de la orden y vuelve a la lista o a la bandeja.
- [ ] 9. Sin JavaScript (desactivalo en el navegador), los pasos 2, 3, 4, 5 y 7 funcionan igual: los botones «Continuar», «Actualizar fechas», «Ver resumen» y «Confirmar» son envíos comunes, y la causa de la merma aparece igual al pedir el resumen.
- [ ] 10. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas (el último paso).

## IOT-02 · Tarea IOT-02 (sistema IoT y hardware)

Los 15 pasos están en «Verificación a mano» de `docs/tareas/iot/IOT-02-sistema-iot-y-hardware.md`. Hay una migración nueva (`core` 0019, solo `choices`): `python manage.py migrate`. Cuentas: Gerente, un Agrónomo a cargo de un invernadero sin Técnico y otro invernadero sin Agrónomo; un insumo activo de «Repuestos de hardware». Verificada en parte a mano por el estudiante el 22/11/2026; quedan los pasos que piden cargar datos a mano (11 a 14) y los ajustes visuales, pospuestos. El último paso se hace después del despliegue.

- [ ] 1. Con el Agrónomo: «IoT» abre en «Sistema IoT», con «Este invernadero no tiene Sistema IoT» y «Registrar sistema IoT». La ficha del invernadero (Datos maestros) dice «Sin registrar» con el mismo enlace.
- [ ] 2. Registrar el sistema con un rango de la solución de un solo valor: error en el rango. Completarlo, «Revisar»: el resumen avisa de la alerta del Técnico. Confirmar: aparece el token con «Copiar», la dirección de la API y la guía; «Cerrar» se habilita al marcar «Ya guardé el token». Recargar la página: el token no aparece.
- [ ] 3. La campana del Gerente tiene «Invernadero sin Técnico activo». La ficha del invernadero dice «Activo»; la lista, «Con IoT».
- [ ] 4. Regenerar el token: confirma y muestra el nuevo una sola vez. En «Auditoría» están `alta_sistema_iot` y `regeneracion_token_iot`, sin token.
- [ ] 5. «Hardware» · «Registrar hardware»: un sensor de temperatura `norte/sectorA/temperatura` en un sector, con calibración 0 a 50. Otro con `NORTE/sectorA/temperatura`: error en el identificador. Un actuador «Ventilador» `norte/sectorA/ventilador`: queda «Sin verificar».
- [ ] 6. Modificar el sensor: cambiar la variable (todavía no tiene lecturas) y el sector. Intentar dar de baja ese sector desde Datos maestros: lo impide y lista el equipo con «Quitales el sector…».
- [ ] 7. Intentar dar de baja el invernadero: lo impide con «Tiene el sistema IoT…».
- [ ] 8. Con el Gerente, en el invernadero del Agrónomo: ve todo en solo lectura con el aviso; en el invernadero sin Agrónomo, puede registrar.
- [ ] 9. Sin JavaScript, los pasos 2, 4, 5 y 6 funcionan igual: cada ventana es una página.
- [ ] 10. Hardware · «Ver ficha» del sensor: identificador, tipo, sector, «Sin confirmar», modelo, insumo y calibración; «Última lectura» dice «—». Con el Agrónomo, «Modificar»; con el Gerente en el invernadero con Agrónomo, ningún botón.
- [ ] 11. Un equipo que todavía no reportó: «Modificar» deja corregir el identificador. Si hay lecturas (se pueden crear a mano en la base), el campo sale deshabilitado con «Ya reportó…».
- [ ] 12. Dar de baja un equipo a mano en la base (`estado_hardware = inactivo`): su ficha ofrece «Reactivar». Si hay otro equipo con su identificador, la ventana dice «No se puede reactivar…». Con uno `fuera_de_servicio`, la ficha ofrece «Volver a activar».
- [ ] 13. «Hardware · Registrar hardware» con `?identificador=norte/algo` en la URL: el campo trae el identificador con «Tomado de la alerta «Dispositivo no registrado».».
- [ ] 14. Como Gerente, en «Tipos de actuador», modificar las acciones de un tipo con un actuador: si el nodo anunció equipos, la compatibilidad y la alerta «Configuración incompatible» se actualizan.
- [ ] 15. Después del merge: verificar en el log de Render que se aplicó la migración nueva.


---

## MAE-02d · Tarea MAE-02d (enlace de alertas)

Los 7 pasos están en «Verificación a mano» de `docs/tareas/maestros/MAE-02d-enlace-de-alertas.md`. Sin migraciones. Datos: `python manage.py cargar_datos_de_verificacion` (pide la contraseña de `CLAUDE.local.md`; ya no existe `--clave`; ya corrido, se puede repetir). Cuentas: el Gerente de la base (su propia contraseña), `agronomo@prueba1.local`, `agronomo@prueba2.local` y `capataz@prueba1.local`. Todavía ninguna app registra un enlace: se verifica que nada cambió y que `alertas:ir` anda con el enlace por omisión.

- [ ] 1. Como Gerente, en la campana: «Invernadero sin Capataz activo» con «Invernadero Verificación 1» debajo y su punto rojo. Abrila desde la campana: te lleva al detalle (`/alertas/<id>/`), que muestra «Nueva», y el punto rojo de esa alerta se apaga. El detalle no tiene la fila «Dónde se atiende».
- [ ] 2. Escribí `/alertas/<id>/ir/` con el id de esa alerta: te redirige al detalle (ahora sin «Nueva»).
- [ ] 3. Con `agronomo@prueba2.local`, la misma URL: 403. Con un id inexistente (`/alertas/999999/ir/`): 404.
- [ ] 4. Con `capataz@prueba1.local`, la misma URL: 403. Sin sesión (otro navegador): te manda a iniciar sesión.
- [ ] 5. «Alertas» y sus filtros (invernadero y tipo) funcionan igual que antes: filtrá por «Invernadero Verificación 1» y por «Invernadero sin Capataz activo»; «Limpiar filtros» vuelve a la lista completa.
- [ ] 6. Volvé a correr el comando de carga: la alerta vuelve a «no leída» y no se duplica nada (mismo id).
- [ ] 7. `python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` pasa.

## IOT-03 · Tarea IOT-03 (API del nodo I: lecturas, estados, modo y anuncio)

Los 13 pasos (0 a 12) están en «Verificación a mano» de `docs/tareas/iot/IOT-03-api-del-nodo-lecturas.md`, con la preparación de datos y de Node-RED. Hay una migración nueva (`core` 0021, solo `choices`): `python manage.py migrate`. Los datos se cargan con `python manage.py cargar_datos_de_verificacion --solo iot` (cuentas `@prueba3.local`). El motivo `equipo_dado_de_baja` no se prueba a mano (es de IOT-06).

- [ ] 0. Entrá como `agronomo@prueba3.local` (si «Norte» ya existía de antes, como el Agrónomo que tenga), en IoT · Sistema IoT registrá el sistema de «Norte» y **copiá el token** (se muestra una sola vez). Volvé a correr `cargar_datos_de_verificacion --solo iot`: carga el rango de la solución (18,0 a 24,0 °C) y los siete equipos del flujo (los identificadores de `docs/api/nodo/node-red/README.md`, sección 4). El token no pasa por el comando.
- [ ] 1. Arrancá Node-RED con `INFOPONIA_URL` e `INFOPONIA_TOKEN` e importá el flujo: «Configuración de equipos» queda en verde. En IoT · Hardware están los siete equipos, «Sin confirmar».
- [ ] 2. En menos de un minuto, IoT · Hardware: el nodo está «En línea» y los sensores dejan de estar «Sin confirmar»: cada uno muestra su última lectura y hace cuánto.
- [ ] 3. «Anunciar ahora» y después «Ventana sin FIJAR_POSICION (anuncio)» + «Anunciar ahora»: la ventana pasa a incompatible y aparece la alerta «Configuración incompatible». «Volver a lo normal» + «Anunciar ahora»: se resuelve.
- [ ] 4. «Temperatura alta (35 °C)»: la situación del sensor pasa a «Fuera de umbral» y aparece «Fuera de umbral efectivo» en la campana, con el valor y el máximo efectivo (26 °C). «Volver a lo normal»: se resuelve cuando la lectura queda a más de 1 °C dentro del umbral.
- [ ] 5. «Lectura inválida (999 °C)»: aparece «Lectura inválida» en la campana. «Volver a lo normal»: se resuelve con la lectura siguiente.
- [ ] 6. «Nivel de solución bajo»: aparece la alerta crítica (sin correo hasta IOT-04) y el sensor muestra «Nivel bajo». «Solución caliente (27 °C)»: «Solución fuera de rango».
- [ ] 7. «Equipo no registrado (co2)»: la lectura vuelve rechazada (barra de depuración de Node-RED) y aparece «Dispositivo no registrado»; desde la alerta se puede registrar el equipo (IOT-02).
- [ ] 8. «Humedad en falla»: el sensor queda «Fuera de servicio» con «Dispositivo en falla». «Ventilador encendido»: la ficha del actuador muestra «Encendido» con la hora; después «Ventilador apagado»: aparece «Cambiado en el invernadero».
- [ ] 9. Detené `runserver` dos minutos y volvé a arrancarlo: Node-RED reintenta (estado «falla …: reintento en …»), vacía la cola y las lecturas de esos minutos llegan atrasadas, sin alertas.
- [ ] 10. Regenerá el token en InfoPonia: Node-RED recibe 401 y no reintenta. Cargá el nuevo y reiniciá Node-RED: vuelve a «En línea».
- [ ] 11. En «Auditoría» están los registros `entrega_informacion_iot` (sin token) y los registros del servidor no muestran el token.
- [ ] 12. Después del merge, en Render: la dirección de la API que muestra el registro del sistema empieza con `https://` (si no, es la configuración del proxy de USR-09: anotalo en `temas_abiertos.md`) y Node-RED, apuntado a esa dirección, recibe 200.

## PRD-03 · Tarea PRD-03 (eventos del lote: merma, aplicación de insumos, evento y bitácora)

Los 12 pasos son los de «Verificación a mano» de `docs/tareas/produccion/PRD-03-eventos-del-lote-merma-aplicacion-bitacora.md`, copiados acá para ir tachándolos (M5). Hay dos migraciones nuevas (`core` 0022 y `produccion` 0003): `python manage.py migrate`. Los datos ya están cargados en la base local (`python manage.py cargar_datos_de_verificacion --solo produccion`, idempotente). Cuentas: `agronomo@prueba4.local`, `capataz@prueba4.local` y tu Gerente. Invernadero «Verificación Producción»: el lote L-3 (86 plantas en «Germinación A» y «Germinación B», con una merma previa de 14 de 100: a una planta del umbral del 15 %), una transición «a realizar» de 86 plantas y los insumos Detergente (gasto, 20 L), Guantes (gasto, unidades), Abono verde (prueba) (costo de los lotes, 30 kg) y Nutriente líquido (prueba) (costo de los lotes, con vencimiento y dos lotes: 4 L y 10 L). «Verificación Producción Vacío» no tiene sectores, lotes ni insumos. Las pantallas no se vieron en un navegador. Hacé el paso 4 al final (deja sin plantas al lote).

- [ ] 1. `migrate` pasa sin errores (también con una siembra ya creada). Como Agrónomo, «Producción» muestra «Registrar en bitácora» y «Bitácora». El Gerente tiene «Bitácora» en el menú, ve la consulta y recibe 404 si abre `/produccion/registrar/merma/`; el Capataz ve en «Mis órdenes» los botones «Merma», «Aplicación de insumos» y «Otro evento» y no tiene la bitácora.
- [ ] 2. «Registrar merma» (Capataz): elegir «Verificación Producción» y el lote L-3 (solo se ofrecen lotes activos; «Verificación Producción Vacío» dice «No hay lotes activos en este invernadero» y no deja enviar). Las cantidades por sector no pasan de lo ocupado (con una mayor, error debajo del sector); sin causa, error; con total 0, error. Registrar 1 planta por «Descarte por selección» y confirmar: el lote baja a 85, el costo por planta queda igual (se ve en «Lotes activos» de la ficha) y aparece en la bitácora («Merma de 1 planta por descarte por selección.»). En «Auditoría» (Gerente) hay un `registro_merma`.
- [ ] 3. Alertas (Agrónomo y Gerente, campana): la merma del paso 2 ya creó «Plantas comprometidas por una transición» (la transición planificó 86 y el lote queda con 85). Registrar ahora 2 plantas por «Plaga»: la merma acumulada pasa de 14 % a 16 % y se crea «Merma sobre el umbral» una sola vez; una merma más no crea otra. El «descarte por selección» del paso 2 no suma al porcentaje.
- [ ] 4. (Al final) Registrar una merma por todas las plantas que quedan del lote L-3 (una cantidad por sector): el lote pasa a «finalizado» con costo 0, deja de estar en «Lotes activos» y los sectores recuperan los agujeros.
- [ ] 5. «Registrar aplicación» (Capataz): el invernadero no viene elegido aunque sea el único. Con «Algunos sectores» sin marcar ninguno, error; elegir «Germinación A». Se ofrecen Detergente, Guantes, Abono verde y Nutriente líquido (más el «abono» sin stock), nunca un insumo que no admita consumo directo. No se ve ningún valor en dinero, destino, reparto ni aviso de stock, ni en el formulario ni en el resumen. Guantes con 1,5: error (solo enteros). Nutriente líquido: 6 L propone 4 del lote que vence antes y 2 del otro; corregirlo a 3 y 3 se acepta; un reparto que no suma 6 da error con cuánto debe sumar; más de lo disponible en un lote, error con lo disponible. Confirmar descuenta el stock (Inventario → Existencias) y aparece en la bitácora, con sus insumos adentro y sin los consumos internos como filas.
- [ ] 6. La misma aplicación como Agrónomo: el formulario dice el destino de cada insumo; el resumen muestra el valor ($28,00 por 7 kg de Abono verde), su destino, el reparto entre los lotes con plantas en el alcance (con el costo por planta antes y después) y lo que va a gasto. Con «Todo el invernadero», el costo del lote L-3 sube en ese monto (la suma de las partes es exacta al centavo); con «Maduración A» (sin plantas) el costo va a gasto y el resumen lo avisa; Detergente («como gasto») no imputa.
- [ ] 7. Aplicar más que el stock: 25 L de Detergente (hay 20). Se registra; lo que falta sale del faltante sin lote; el Agrónomo (no el Capataz) recibe la alerta «Stock inconsistente» y el resumen del Agrónomo dice cuántos litros quedaron sin lote.
- [ ] 8. «Otro evento» (Agrónomo o Capataz): con un solo invernadero viene elegido. Sin descripción, error debajo del campo; con 501 caracteres, error; con lote y sector opcionales (un sector fuera de servicio se acepta; ninguno inactivo). Quedan en la bitácora con la fecha y la hora de ahora. No hay forma de editar ni borrar un registro de bitácora.
- [ ] 9. Pestaña «Bitácora» de la ficha del invernadero (Agrónomo y Gerente; el Capataz no la ve): del más reciente al más antiguo, agrupado por día; con «Registrar evento» y «Registrar aplicación» (solo el Agrónomo) ya con el invernadero elegido; los filtros (texto, tipo, lote, sector, fechas) se combinan; «Quitar filtros» funciona; el filtro por sector encuentra también las aplicaciones en varios sectores. Un invernadero dado de baja se puede consultar (Gerente y su Agrónomo) y no ofrece registrar.
- [ ] 10. Con dos pestañas del mismo lote: registrar dos mermas a la vez sobre las mismas plantas: el lote nunca queda negativo y la otra ve «cambió» con la cantidad vigente, sin 500. Dos aplicaciones a la vez sobre el último lote de un insumo: las dos se registran y el resto sale del faltante sin lote, sin descontar dos veces lo mismo.
- [ ] 11. Sin JavaScript (desactivalo en el navegador), los pasos 2, 5, 6 y 8 funcionan igual: «Continuar», «Ver resumen» y «Confirmar» son envíos comunes.
- [ ] 12. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas (`core` 0022 y `produccion` 0003; el último paso).


## PRD-04 · Tarea PRD-04 (sector fuera de servicio e Inicio del Agrónomo)

Los 11 pasos son los de «Verificación a mano» de `docs/tareas/produccion/PRD-04-sector-fuera-de-servicio-e-inicio.md`, copiados acá para ir tachándolos (M5). Hay dos migraciones nuevas (`core` 0023 y `produccion` 0004): `python manage.py migrate`. Los datos ya están cargados en la base local (`python manage.py cargar_datos_de_verificacion`, idempotente). Cuentas: `agronomo@prueba4.local`, `capataz@prueba4.local` y tu Gerente. Invernadero «Verificación Fuera de Servicio»: «FDS Germinación 1» (lote de 40 plantas y una siembra «a realizar» de 20 plantines con 12 agujeros comprometidos ahí y 8 en «FDS Germinación 2»), «FDS Germinación 2» (con lugar), «FDS Germinación 3» (vacío) y «FDS Maduración» (ya fuera de servicio, con su registro abierto). «Verificación Fuera de Servicio Baja»: sin lotes ni órdenes, con «FDS Baja Germinación» fuera de servicio. Las pantallas no se vieron en un navegador. Los pasos 3 y 4 cambian el estado de «FDS Germinación 1»: hacelos en ese orden.

- [ ] 1. `migrate` pasa sin errores (con ocupaciones ya existentes). Como Agrónomo, el Inicio muestra «Mi producción» con los cuatro indicadores.
- [ ] 2. «Poner fuera de servicio» (menú ⋯ de un sector activo de «Sectores», o el botón de la ventana de la baja cuando hay impedimentos): solo se ofrecen sectores activos de tus invernaderos, agrupados por tipo de etapa. Elegir el sector muestra su lote, sus órdenes y el aviso si es el último de su tipo, sin validar nada. Poner una fecha anterior a la mínima explica de dónde sale; una posterior a hoy y un motivo vacío dan error en su campo.
- [ ] 3. En «FDS Germinación 1», reubicar plantas del lote: solo se ofrecen destinos de Germinación del mismo invernadero, con perfil compatible y lugar. «Ver resumen» sin causa y con plantas sin reubicar pide la causa por lote (sin «descarte por selección»); el resumen muestra la merma con su valor, las órdenes que se cancelan y que se avisa al Capataz.
- [ ] 4. Confirmar: «FDS Germinación 1» queda «fuera de servicio» sin ocupados ni comprometidos; el lote conserva etapa y fecha de entrada y tiene una ocupación nueva en el destino; la merma (si hubo) y la reubicación están en la bitácora (filtro «Reubicación de plantas» y «Sector fuera de servicio»); la siembra queda cancelada con su motivo, sus reservas liberadas y los 8 agujeros de «FDS Germinación 2» libres; el Capataz recibe **una** notificación; «Auditoría» tiene **un** registro `fuera_de_servicio_sector`.
- [ ] 5. «FDS Maduración» (ya fuera de servicio) → «Volver a activar»: el registro se cierra con la fecha de hoy y la bitácora dice «… vuelve a estar activo … N días».
- [ ] 6. Dar de baja un sector fuera de servicio (por ejemplo «FDS Germinación 1» después del paso 4) cierra su registro. Con el Gerente, dar de baja «Verificación Fuera de Servicio Baja» cierra el registro de «FDS Baja Germinación».
- [ ] 7. «FDS Germinación 3» (sin plantas ni órdenes): solo cambia de estado, sin reubicaciones, mermas ni cancelaciones.
- [ ] 8. Dos pestañas (o dos Agrónomos) ponen fuera de servicio el mismo sector, o una lo pone mientras el Capataz concreta una transición sobre él: una sola gana y la otra ve el estado actual, sin error 500.
- [ ] 9. Inicio del Agrónomo: lotes activos, órdenes vencidas, ocupación (solo sectores activos) e insumos por vencer coinciden con las pantallas de origen; sin invernaderos a cargo dice cómo empezar.
- [ ] 10. Sin JavaScript, los pasos 2, 3, 4 y 5 funcionan igual (cada botón es un POST común).
- [ ] 11. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## COM-01 · Tarea COM-01 (clientes y vehículos)

Los 11 pasos son los de «Verificación a mano» de `docs/tareas/comercial/COM-01-clientes-y-vehiculos.md`, copiados acá para ir tachándolos (M5). Hay dos migraciones nuevas (`comercial` 0001 y `core` 0024): `python manage.py migrate`. Los datos ya están cargados en la base local (`cargar_datos_de_verificacion --solo comercial`): cuentas `vendedor@prueba5.local`, `transportista@prueba5.local` (ya en «Invernadero Comercial») y `transportista2@prueba5.local` (sin invernadero), y el Gerente de siempre. Para los CUIT de los pasos 2 a 6, usá otros (por ejemplo 30-71234567-1 y 20-12345678-6).

- [ ] 1. Con el Vendedor: el menú muestra «Comercial» después de «Panel de control»; la pantalla abre en «Clientes» y no tiene la
 pestaña «Vehículos».
- [ ] 2. Registrar una persona jurídica sin correo ni dirección: se crea; la ficha dice «Necesario para pactar suministros» junto al correo.
- [ ] 3. Registrar otra con un CUIT mal tipeado: error en el campo. Con el CUIT del paso 2: aviso con «Abrir su ficha».
- [ ] 4. Registrar una persona física con dos direcciones (una urbana y una rural; «Agregar dirección» suma el bloque); intentar agregar una tercera igual a la urbana, cambiando solo las mayúsculas: «El cliente ya tiene esa dirección.»
- [ ] 5. Modificar el cliente del paso 4: corregir la rural, desactivar la urbana y borrar la que quedó sin usar; en «Auditoría» hay un `modificacion_cliente` con las direcciones afectadas. En «Verdulería Los Pinos (prueba)», cambiar una dirección de urbana a rural la reemplaza por otra.
- [ ] 6. Con el Gerente: dar de baja el cliente del paso 2 (la ventana dice que no tiene pendientes). Con el Vendedor: registrar uno nuevo con ese mismo CUIT: ofrece «Reactivarlo»; corregir el teléfono y confirmar. El Gerente tiene la notificación «Cliente reactivado: …». Probar también «Reactivar» en «Cerrado S.A. (prueba)».
- [ ] 7. Con el Gerente, «Vehículos»: registrar una camioneta `ae-123 cd` (se guarda `AE123CD`) con 800 kg y `transportista@prueba5.local`. Ese Transportista tiene la notificación. En la ficha de «Invernadero Comercial», «Logística» muestra «Camioneta AE123CD · 800 kg» y «En el invernadero». En la ficha de su cuenta (y en su «Mi perfil») aparece «Vehículo: Camioneta AE123CD · 800 kg».
- [ ] 8. Registrar un segundo vehículo: el Transportista del paso 7 ya no aparece en la lista para elegir.
- [ ] 9. Modificar el vehículo: cambiar el transportista por `transportista2@prueba5.local` (sin invernadero: aviso «No recibe entregas hasta…»); los dos Transportistas reciben su notificación. Darlo de baja: queda inactivo y sin transportista; «Reactivar» lo deja activo, sin transportista. Probar también «Reactivar» en `ZZZ999`.
- [ ] 10. Sin JavaScript, los pasos 2 a 6 y 7 a 9 funcionan igual: cada ventana es una página.
- [ ] 11. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.


## CFG · Configuración del repositorio

1. Después del primer merge con el workflow: en GitHub, Settings → Branches (o Rules), exigir que
   el check de `pruebas.yml` pase para poder mergear a main.

