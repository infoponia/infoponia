# Revisiones a mano pendientes — InfoPonia

> **Vigente otra vez desde el 23/11/2026 (D-96).** La verificación vuelve a ser a mano, sin navegador automatizado ni cargadores de datos: los datos de prueba los crea quien verifica, con los valores que dice cada tarea.
> Las secciones anteriores a CMP-01 se escribieron cuando todavía existía el cargador (`cargar_datos_de_verificacion`, retirado en D-95): donde lo nombran, hay que crear los datos a mano.

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


## IOT-04 · Tarea IOT-04 (revisión periódica, panel de monitoreo y configuración IoT)

Los 13 pasos están en «Verificación a mano» de `docs/tareas/iot/IOT-04-revision-panel-y-configuracion.md`. Hay una migración nueva (`core` 0024, solo `choices`): `python manage.py migrate`. Los datos se cargan con `python manage.py cargar_datos_de_verificacion --solo iot` (el invernadero «Sur» y un día de lecturas de ayer y de anteayer; el Agrónomo de «Norte» y el Gerente que ya tenés). Hace falta Node-RED con el flujo de lecturas y, para el correo, el servidor de correo del `.env` (si no, la salida dice «pendientes sin servidor de correo»).

- [ ] 1. Con Node-RED mandando, `python manage.py revision_iot --cada 60`: cada minuto, una línea por sistema y la de correos; la primera corrida resume ayer y anteayer y calcula el fotoperíodo de ayer.
- [ ] 2. Como el Agrónomo, IoT · Monitoreo: el nodo «En línea», los sensores agrupados con su gráfico de 24 horas y los valores que cambian solos cada 30 s; con «Parámetros IoT» abierto no se refresca; los selectores no se cierran.
- [ ] 3. Período «Última hora» y «Últimos 7 días» (resúmenes horarios con la franja de mínimo a máximo); «Actualizar» pide el panel al instante.
- [ ] 4. «Nivel de solución bajo»: alerta crítica y, en el minuto siguiente, el correo («Notificada por correo»); la revisión siguiente no lo repite.
- [ ] 5. Detener Node-RED: a los 3 minutos, «Nodo sin comunicación» crítica con su correo y los sensores «Desactualizado»; al volver, se resuelve.
- [ ] 6. «Equipo no registrado (co2)» con «Registrar este equipo»; «Volver a lo normal»: a los 5 minutos la revisión la resuelve.
- [ ] 7. En la campana, la alerta de un sensor lleva a la ficha del equipo; la de «no registrado», al alta con el identificador (en minúsculas).
- [ ] 8. Gerente, Configuración operativa · «Módulo IoT»: fin igual al inicio da error; «1,55» da error y «1,5» entra; bajar la retención a 1 guarda con el aviso y la advertencia amarilla con la fecha.
- [ ] 9. Con la retención en 1, la revisión siguiente borra las lecturas de anteayer y lo dice; los gráficos de 7 días siguen. Volver la retención a 7.
- [ ] 10. La tarjeta de la luz dice «Fotoperíodo de ayer: 10 h» con «En rango».
- [ ] 11. En «Auditoría», `revision_periodica_iot` y `modificacion_configuracion` con su antes y su después.
- [ ] 12. Gerente: en «Sur», «Registrar Sistema IoT»; en «Norte», solo consulta y con el aviso de quién recibe las alertas. El Agrónomo no ve «Modificar parámetros» y a `/configuracion/` le da 403.
- [ ] 13. Sin JavaScript, el panel se ve entero y el período se cambia con «Ver».

## CMP-01 · Tarea CMP-01 (app `compras` y proveedores)

Los 17 pasos son los de «Verificación a mano» de `docs/tareas/compras/CMP-01-app-compras-y-proveedores.md` (con los valores de ejemplo y lo que crea cada paso), copiados acá para ir tachándolos (M5). Hay dos migraciones nuevas (`compras` 0001 y `core` 0026): `python manage.py migrate`. No hay datos cargados: se crean en los pasos. Entrá con el Gerente.

- [ ] 1. «Compras» aparece en el menú (ícono de caja); abre «Proveedores» sin filas y con el texto de que todavía no hay.
- [ ] 2. Alta de una persona jurídica con dos especialidades: la ficha con el aviso «Registramos a …», el CUIT con guiones y las dos categorías.
- [ ] 3. Otra alta con el mismo CUIT: el error sale debajo del CUIT («Ya está registrado como …») y lo escrito se conserva.
- [ ] 4. Varios errores a la vez (CUIT inválido, razón social y correo vacíos, teléfono `abc`): salen todos juntos, cada uno junto a su campo.
- [ ] 5. Persona física: se ocultan los campos de razón social y aparecen nombre y apellido; sin datos da sus errores y con datos se registra.
- [ ] 6. Baja: la ventana se abre sin recargar la página; «Cancelar» no cambia nada; confirmar vuelve a la lista con el aviso y el proveedor deja de verse entre los activos.
- [ ] 7. Reactivar desde el alta: con el CUIT de un inactivo aparece «Reactivar con estos datos» y conserva lo escrito.
- [ ] 8. Reactivar desde la ficha: estado «Inactivos» → ficha con «Reactivar» (sin «Editar datos» ni «Dar de baja»); el formulario trae sus datos y el CUIT fijo.
- [ ] 9. Modificar: cambiar el teléfono, error por campo con el correo vacío, y el CUIT se puede cambiar mientras no tenga pedidos (con pedidos queda fijo).
- [ ] 10. Filtros: por nombre, por CUIT (con y sin guiones, o una parte), por estado y por categoría; «Quitar filtros» y el aviso de que no hay resultados.
- [ ] 11. Categoría dada de baja: no se ve ni se ofrece en la ficha y el formulario, pero el vínculo se conserva al modificar.
- [ ] 12. «Auditoría»: alta, modificación, baja y reactivación de proveedor; el CUIT se audita con 11 dígitos.
- [ ] 13. Agrónomo: ve la lista y la ficha sin botones de cambio, y escribir la dirección de «Nuevo proveedor» a mano da 403.
- [ ] 14. (Opcional) Vendedor o Capataz: sin «Compras» en el menú y `/compras/proveedores/` da 403.
- [ ] 15. (Opcional) Sin JavaScript: «Dar de baja» abre la ficha con la ventana abierta; el alta muestra los dos grupos de campos y todas las categorías.
- [ ] 16. (Opcional) En un ancho de celular (390 px) la página no se desplaza a los costados; la tabla scrollea dentro de su contenedor.
- [ ] 17. **Navegador real (D-96).** En una ventana privada, con sesión del Gerente, repetí el alta (paso 2) y la baja (paso 6) hasta el final: sin «Prohibido (403)», sin «Verificación CSRF fallida» y sin errores en la consola (F12).

## CMP-02a · Tarea CMP-02a (pedido de cotización y portal del proveedor)

Los 19 pasos son los de «Verificación a mano» de `docs/tareas/compras/CMP-02a-pedido-y-portal-del-proveedor.md` (con los datos que hay que crear a mano, en orden, y sus valores), copiados acá para ir tachándolos (M5). Hay dos migraciones nuevas (`compras` 0002 y `core` 0028): `python manage.py migrate`. Para ver los correos sin enviarlos, correo en modo consola (`CORREO_CONSOLA=1` en `.env`).

- [ ] 1. Agrónoma Ana, «Panel de control»: «Insumos bajo el mínimo: 1» con **Pedir**, que abre «Nuevo pedido» con la Lechuga y la cantidad sugerida (15).
- [ ] 2. «Agregar otro insumo del catálogo»: el Nutriente (Invernadero Sur) aparece como segundo renglón; escribir 3.
- [ ] 3. «Habilitarlo en un invernadero» (Sustrato): con precio 0 da el error junto al campo y no se pierde el pedido; con 30,00 queda habilitado y agregado; «Quitar» lo saca.
- [ ] 4. «Revisar pedido» con cantidad 0, fecha de hoy y sin proveedores: los tres errores salen juntos, cada uno junto a su campo, y lo escrito se conserva.
- [ ] 5. Proveedores: filtro propuesto («Los que venden lo que pedís»), «Seleccionar todos» solo de la lista filtrada, «Todos los proveedores» y que un proveedor dado de baja no aparece.
- [ ] 6. Resumen con $ 550,00 (por invernadero, con precio de referencia y subtotal); «Volver a corregir» no muestra errores; «Confirmar pedido» lleva a la ficha con «Enviamos el pedido …».
- [ ] 7. En la terminal, dos correos con enlaces distintos, el detalle, la dirección y la fecha límite, y sin ningún precio; los dos invitados figuran «No cotizó» con el enlace «Vigente».
- [ ] 8. Proveedor (ventana privada): al abrir el enlace la dirección pasa a `/proveedor/enlace/` sin el código; se ve el pedido sin precios de referencia ni el otro proveedor.
- [ ] 9. Portal con errores (nada cotizado; cantidad 0, precio 10,123, plazo 0 y validez anterior a la fecha límite): salen junto a cada campo.
- [ ] 10. Cotizar la Lechuga (20, total 250, 3 días) y el Nutriente (4, total 120, 2 días): el resumen muestra el unitario y la advertencia «se envía una sola vez»; enviar.
- [ ] 11. «Recibimos su cotización…», el acuse en la terminal con $ 370,00 y, al volver a abrir el enlace, «Ya envió su cotización» en solo lectura y sin botón para enviar otra.
- [ ] 12. Ana, ficha: «Cotizó» con el enlace «Usado», la cotización en «Cotizaciones recibidas» y **un** aviso «Pedido … cubierto» en la campana; con el otro proveedor (precio unitario, el rótulo cambia) no llega un segundo aviso.
- [ ] 13. Gerente: «Pedidos» en modo consulta, sin «Nuevo pedido» y sin botones de cambio; la dirección de «Nuevo pedido» a mano da 403; «Auditoría» con «Alta de pedido de cotización» y dos «Alta de cotización» con «Proveedor (mediante enlace)».
- [ ] 14. Ficha del proveedor: la tarjeta «Pedidos» lista el pedido (con «Cotizó») y el CUIT ya no se puede editar.
- [ ] 15. (Opcional) Con el correo sin configurar: cada invitado figura «No se pudo enviar» y aparece el aviso con qué hacer.
- [ ] 16. La otra Agrónoma o el Capataz abren `/compras/pedidos/<número>/`: 403.
- [ ] 17. (Opcional) Con la fecha límite en el pasado (a mano en la base): el enlace da «Este enlace no se puede usar · El plazo para cotizar terminó.» y el pedido figura «Fecha límite vencida».
- [ ] 18. (Opcional) Sin JavaScript y en un ancho de celular (390 px): «Nuevo pedido» y el portal siguen funcionando y no se cortan las tarjetas.
- [ ] 19. **Navegador real (D-96).** En una ventana privada, enviá la cotización hasta el final (y confirmá el pedido y la habilitación del paso 3): sin «Prohibido (403)», sin «Verificación CSRF fallida» y sin errores en la consola (F12).

## COM-03a · Tarea COM-03a (suministros: pactar y consultar)

Los 13 pasos son los de «Verificación a mano» (en el «Cierre») de `docs/tareas/comercial/COM-03a-suministros-pactar-y-consultar.md`, con los datos que hay que crear a mano, en orden, y sus valores, copiados acá para ir tachándolos (M5). Hay dos migraciones nuevas (`comercial` 0003 y `core` 0030): `python manage.py migrate`; después `python manage.py runserver` y abrí `http://127.0.0.1:8000/`. No hay datos cargados: creá un Agrónomo, un Capataz y dos Vendedores; un invernadero con el primer Vendedor y un lote de «Lechuga Crespa» en Maduración con 300 plantas; los clientes «Verdulería Los Pinos S.R.L.» (con correo y dos direcciones) y «Verdulería Sin Correo S.A.» (sin correo); y la pre-reserva de suministros en 14 días.

- [ ] 1. **Lista y selector.** «Contratos»: «Compra-ventas | Suministros»; «Suministros» dice «Todavía no hay suministros.» y tiene el botón «Pactar suministro».
- [ ] 2. **Cliente sin correo.** Aviso «El cliente no tiene correo…» con «Cargar el correo»; las secciones 2 y 3 bloqueadas; al cargarlo se vuelve con el cliente todavía elegido.
- [ ] 3. **Contrato.** Duración 6: «Termina el» con el mismo día del mes, 6 meses después; tolerados 0, multa 50000, plazo de pago 15, indemnización por atraso 100.
- [ ] 4. **Detalle 1 y stock.** 200 plantas cada 7 días: el segundo período dice «No alcanza» (hay 300 para 400); con 150, los dos «Alcanza».
- [ ] 5. **Errores.** Mismo par variedad y dirección: «El contrato ya tiene…»; ajuste periódico 3 % cada 2 meses con sus tramos; cantidad mínima mayor que la cantidad: error, y se corrige.
- [ ] 6. **Pactar.** Resumen, «Confirmar suministro»; ficha con `SUM-0001` vigente, calendario «Reservado» y «Fuera de la ventana»; cosechas notificadas al Capataz y al Agrónomo; «Pacto de suministro» en «Auditoría».
- [ ] 7. **Superposición.** Mismo cliente, variedad y dirección: aviso con `SUM-0001` y «Continuar igual»; sin marcarla no deja; con otro cliente no hay aviso.
- [ ] 8. **Consulta.** Filtros de la lista, «Al límite», «Ver todo el calendario», «Ver comprobante», suministro en la ficha del cliente y «Suministros vigentes» al darlo de baja.
- [ ] 9. **Roles.** Agrónomo: 403 en `/comercial/contratos/?tipo=suministro`; el segundo Vendedor no ve `SUM-0001` y su dirección da 403.
- [ ] 10. **Baja de variedad y cambio de Vendedor.** «Tiene contratos abiertos: 2 suministros.»; el traspaso avisa «Suministros vigentes: 2» y los contratos pasan al Vendedor nuevo.
- [ ] 11. **Navegador real (D-96).** En una ventana privada, pactá un suministro hasta el final y probá «Reenviar comprobante»: sin «Prohibido (403)», sin «Verificación CSRF fallida» y sin errores en la consola (F12).
- [ ] 12. (Opcional) Sin JavaScript y en un ancho de celular (390 px): el pacto funciona con «Actualizar» y nada se desborda.
- [ ] 13. (Opcional) **Después del despliegue:** en el log de Render, que se aplicaron `comercial/0003_suministros` y `core/0030_comercial_suministros`.

## IOT-05 · Tarea IOT-05 (comandos: emitir, retirar, resolver con reintentos y cancelar)

Los 17 pasos son los de «Verificación a mano» de `docs/tareas/iot/IOT-05-comandos.md` (con los datos que hay que crear a mano, en orden, y sus valores), copiados acá para ir tachándolos (M5). Hay tres migraciones nuevas (`iot` 0004, `produccion` 0006 y `core` 0029): `python manage.py migrate`; después `python manage.py runserver` y abrí `http://localhost:8000`. No hay datos cargados: creá a mano, en este orden, (a) un **Agrónomo** (Laura) a cargo del invernadero «Norte», un **Gerente** y un **Técnico**; un segundo invernadero «Libre» **sin Agrónomo**; (b) en «IoT · Sistema IoT» de «Norte», el sistema (anotá el token); (c) en «IoT · Hardware» de «Norte», dos actuadores con un insumo de «Repuestos de hardware» cada uno: `norte/sectorA/ventilador` (tipo «Ventilador», con un sector) y `norte/sectorA/ventana` (tipo «Ventana»); (d) en «Libre», un sistema y `libre/ventilador` (tipo «Ventilador»). Con el Gerente, «Configuración · Módulo IoT»: **1 reintento y 10 s de intervalo** (al final, volver a 3 y 60). Node-RED con los dos flujos (`docs/api/nodo/node-red/README.md`, secciones 1 a 4) y, en otra terminal, `python manage.py revision_iot --cada 30`. Si no tenés Node-RED, los pasos 5 a 12 se pueden cubrir con la API (`GET comandos` y `POST comandos/<id>/resultado`, con `Authorization: Bearer <token>`).

- [ ] 1. **Escenario 6 · Emitir un comando manual.** Con Laura, IoT → «Comandos»: elegí «Ventana · norte/sectorA/ventana» y la acción «Fijar posición»; aparece el campo «Valor (%)» con «Número entero entre 0 y 100 %.». Escribí 40, tocá «Ver resumen» y después «Confirmar y emitir». Tiene que verse el aviso «Comando CMD-n pendiente. El nodo lo retira en su próxima consulta…» y la fila «Pendiente», «0 de 2». En unos segundos, «Ejecutado»; en la ficha de la ventana (Hardware), «Posición 40» y el historial con el comando.
- [ ] 2. **Advertencia «ya está en ese estado» (paso 1 de la tarea).** Con el ventilador ya «Encendido» (por el flujo de Node-RED), elegí «Encender» y «Ver resumen»: «Según el último estado que informó el nodo, el actuador ya está encendido…». Confirmá: queda «Ejecutado».
- [ ] 3. **Errores de validación.** «Fijar posición» con 150, con 12.5 y con el campo vacío, y «Ver resumen»: el error junto al campo («Ingresá un número entero entre 0 y 100 %, sin decimales.» o «Ingresá el valor…») y ningún comando creado. Sin elegir actuador: «Seleccioná un actuador.».
- [ ] 4. **Tiempo mínimo entre comandos (6f).** Justo después de un comando ejecutado, emití otro al mismo actuador: el resumen advierte «El actuador cambió de estado hace… faltan n s… Podés emitirlo igual.» y deja confirmar.
- [ ] 5. **Escenario 7 · Falla del actuador.** En Node-RED, flujo de comandos → «Fallar cada intento»; emití «Apagar» al ventilador. El primer intento falla (la fila sigue «Pendiente», «1 de 2»); al segundo queda «Fallido» con «El actuador falló en 2 intentos…», el ventilador pasa a «Fuera de servicio» y aparece la alerta crítica «Comando fallido» en Monitoreo. En la vuelta siguiente de `revision_iot` llega el correo. «Emitir comando» ya no se ofrece para ese actuador: la pantalla dice «Volvé a activarlo desde Hardware antes de emitir comandos.». Después, en su ficha, «Volver a activar».
- [ ] 6. **Escenario 8 · El nodo no reconoce el comando.** «Rechazar (no reconoce)» y emití «Cerrar» a la ventana: queda «Rechazado por el nodo», sin reintentos y con la nota; aparece «Configuración incompatible», el actuador sigue activo y «Cerrar» ya no se ofrece al emitir (el formulario avisa «El nodo no soporta: Cerrar»).
- [ ] 7. **Escenario 9 · Caída del nodo.** Emití un comando, esperá a que el nodo lo retire y detené los flujos unos 4 minutos. En la vuelta de la revisión: alerta crítica «Nodo sin comunicación» (y su correo). El comando sigue «Pendiente» y no consumió intentos. Volvé a arrancar los flujos: se resuelve la alerta y el comando se ejecuta.
- [ ] 8. **Escenario 13 · Cancelar un comando trabado.** «No responder»; emití un comando. Mientras el nodo lo tiene, «Cancelar» está deshabilitado con «Cancelable en n s» y la ventana (si la abrís a mano) lo explica. Cuando vence el intento, «Cancelar» → «Cancelar comando»: «Cancelado», aviso «CMD-n cancelado…», y se puede emitir otro al mismo actuador.
- [ ] 9. **Modo local (paso 2 de la tarea).** En el flujo de lecturas, «Modo local». Emití un comando: el resumen avisa «El nodo está operando en modo local…» y queda «Pendiente» con «0 de 2» aunque pase el tiempo. «Modo remoto»: el nodo lo retira y se ejecuta.
- [ ] 10. **Bitácora y auditoría (pasos 3 y 4 de la tarea).** Producción → «Bitácora» (invernadero «Norte»): los registros de tipo «Comando» con cada hecho («Falló: …», «Sin respuesta», «cancelado», «ejecutado»). Con el Gerente, «Auditoría»: «Emisión de comando», «Cancelación de comando» y «Resolución de comando (IoT)». (El filtro «Tipo» de la bitácora todavía no ofrece «Comando»: queda para otra tarea.)
- [ ] 11. **Panel y ficha.** Monitoreo: el indicador «Comandos pendientes», la situación «Comando pendiente» del actuador y, en su fila, «Cancelar» (o «Emitir comando» si no hay pendiente). Ficha del actuador (Hardware → «Ver ficha»): «Emitir comando», la tarjeta «Comandos» con los últimos 10 y «Ver todos (n)» filtrado por ese actuador.
- [ ] 12. **Lista y filtros.** «Comandos»: filtrá por estado, actuador y origen (el filtro no recarga la página con JavaScript y aparece «Limpiar filtros»); con más de 25 comandos, «Siguiente» y «Anterior» conservan los filtros.
- [ ] 13. **Gerente.** En «Norte» (tiene Agrónomo activo): ve la lista y el aviso «Norte tiene Agrónomo activo…», pero **sin** formulario ni «Cancelar». En «Libre» (sin Agrónomo): «Operás este invernadero como Gerente…», emite, y su comando sale «Manual · … (Gerente)»; en Auditoría figura su nombre.
- [ ] 14. **Rol sin acceso y alcance.** El Técnico o un Capataz escriben `/iot/comandos/` a mano: 403. Un Agrónomo de otro invernadero, con `?invernadero=<id de Norte>`: 404. Sin sesión: lleva al ingreso. (Los botones nunca llevan a un 403.)
- [ ] 15. **Navegador real (D-96).** En una ventana privada, entrá con Laura y hacé **de punta a punta** el formulario de «Comandos» (elegir actuador y acción, «Ver resumen», «Confirmar y emitir») y la cancelación («Cancelar» → «Cancelar comando»): sin «Prohibido (403)», sin «Verificación CSRF fallida» y sin errores en la consola (F12). Mirá además que la lista, la ficha y el panel se vean bien (la tabla no se corta, «Cancelar» no se parte).
- [ ] 16. (Opcional) **Sin JavaScript y en un celular.** Desactivá JavaScript: elegí el actuador y tocá «Actualizar el formulario», elegí la acción y volvé a tocarlo; «Ver resumen» y «Confirmar y emitir» funcionan; «Cancelar» abre la misma página con la ventana. En un ancho de 390 px no hay desborde horizontal.
- [ ] 17. (Opcional) **Después del despliegue:** en el log de Render, que se aplicaron las tres migraciones.

## CMP-02b · Tarea CMP-02b (cancelar pedido, reenviar invitación y lo que cancela solo)

Los 21 pasos son los de «Verificación a mano» de `docs/tareas/compras/CMP-02b-cancelar-reenviar-y-bajas.md` (con los datos que hay que crear a mano, en orden, y sus valores), copiados acá para ir tachándolos (M5). Hay una migración nueva (`core` 0031, que no cambia ninguna tabla): `python manage.py migrate`. Para ver los correos sin enviarlos, correo en modo consola (`CORREO_CONSOLA=1` en `.env`).

- [ ] 1. Ana: pedido P1 (Lechuga 20, Norte) a los dos proveedores; la ficha ofrece «Cancelar pedido» y «Reenviar invitación» en cada invitado; copiar los enlaces de la terminal (A de Semillas, C de Viveros).
- [ ] 2. «Reenviar invitación» a Semillas del Sur: la ventana dice a quién y que el enlace anterior deja de servir; «Volver» no cambia nada; confirmar manda un correo nuevo (enlace B) y deja «No cotizó» y «Vigente».
- [ ] 3. Proveedor (ventana privada): el enlace A dice «reemplazado por uno más nuevo» sin datos del pedido; el B abre el portal.
- [ ] 4. Viveros cotiza con el enlace C; en la ficha figura «Cotizó» y «Usado» y ya no tiene «Reenviar invitación»; Semillas sí.
- [ ] 5. «Cancelar pedido»: sección 1 con destino, cotizaciones recibidas (1), monto $ 250,00 y las advertencias; sin motivo, el error sale junto al campo.
- [ ] 6. Con motivo, el resumen: cotizaciones que se descartan (1), enlaces que se anulan (1) y a quién se avisa; «Volver a corregir» conserva el motivo.
- [ ] 7. «Confirmar cancelación»: ficha «Cancelado», motivo, «Cancelado por el Agrónomo», sin botones; la cotización «Descartada» y el enlace de Semillas «Anulado»; dos correos sin el motivo, ni el otro proveedor ni precios.
- [ ] 8. Proveedor (ventana privada): los enlaces B y C dicen «El pedido fue cancelado.».
- [ ] 9. La dirección `/compras/pedidos/<n>/cancelar/` de P1 a mano vuelve a la ficha con el aviso de que ya no está en cotización.
- [ ] 10. Gerente: P1 sin botones y 403 en `/cancelar/`; «Auditoría» con «Reenvío de invitación a un proveedor» y «Cancelación de pedido de cotización», sin tokens.
- [ ] 11. Otra Agrónoma o el Capataz: 403 en `/cancelar/`.
- [ ] 12. P2 (Lechuga en Norte y Nutriente en Norte 2) y P3 (Nutriente en Norte 2); el Gerente cambia el Agrónomo de Norte a «Nuevo»: la ventana dice «Se cancela 1 pedido de cotización en curso de Ana…», no dice que «Nuevo» recibe pedidos y no guarda hasta confirmar.
- [ ] 13. Confirmado: P2 «Cancelado» (cancelación automática, «Agrónomo sin el invernadero de destino»), P3 sigue en cotización; avisos en la campana de Ana y de Nuevo y no del Gerente; «Auditoría» con la cancelación de InfoPonia.
- [ ] 14. Baja de la cuenta de Ana: la ventana dice «Pedidos de cotización en curso. Es 1: se cancelan solos…»; P3 queda «Cancelado» («Agrónomo inactivo») y figura en el registro de la baja; el Gerente no recibe aviso.
- [ ] 15. Otra: P4 (Tomate) y P5 (Pepino); «Deshabilitar» el Tomate y «Dar de baja» en el catálogo dicen «Está en el pedido P-…» con «Ver detalle».
- [ ] 16. Gerente: «Dar de baja» el Invernadero Este lista los dos pedidos, cada uno con «Ver detalle».
- [ ] 17. Otra cancela P4: el Tomate se deshabilita; el Pepino sigue impedido por P5.
- [ ] 18. Baja del proveedor Semillas: la ventana avisa que sus enlaces dejan de servir; el enlace D «fue anulado», el E (Viveros) sigue sirviendo, P5 sigue en cotización y «Auditoría» lista los enlaces anulados.
- [ ] 19. **Navegador real (D-96).** Confirmar cancelación, «Reenviar invitación», «Confirmar y guardar» del personal y «Dar de baja» de la cuenta, enviados hasta el final en una ventana privada: sin «Prohibido (403)», sin «Verificación CSRF fallida» y sin errores en la consola (F12); las ventanas abren sin recargar la página.
- [ ] 20. (Opcional) Sin JavaScript: «Reenviar invitación» lleva a la ficha con la ventana abierta y funciona; «Cancelar pedido» y su resumen funcionan.
- [ ] 21. (Opcional) En un ancho de celular (390 px): la ficha, «Cancelar pedido», su resumen y la ventana no se cortan.

## CFG · Configuración del repositorio

1. Después del primer merge con el workflow: en GitHub, Settings → Branches (o Rules), exigir que
   el check de `pruebas.yml` pase para poder mergear a main.

