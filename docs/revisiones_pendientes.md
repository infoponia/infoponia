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

## CFG · Configuración del repositorio

1. Después del primer merge con el workflow: en GitHub, Settings → Branches (o Rules), exigir que
   el check de `pruebas.yml` pase para poder mergear a main.

