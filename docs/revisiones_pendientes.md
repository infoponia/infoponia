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

## MAE-01a · Tarea MAE-01a (invernadero: modelos, alta y consulta)

Tarea MAE-01a (maestros), a mano. Con el entorno virtual activo y la base local:

1. `python manage.py migrate`. Tiene que aplicar `core 0010` y `maestros 0001` y `0002` (la 0002 carga Georef y tarda unos
   segundos). Comprobá en `python manage.py shell`: `from maestros.models import *; Provincia.objects.count(),
   Departamento.objects.count(), Localidad.objects.count()` da `(24, 527, 3923)`.
2. `python manage.py runserver` e iniciá sesión como Gerente. En el menú lateral aparece «Producción». Con una cuenta de
   Agrónomo también aparece; con una de Vendedor, no.
3. Como Gerente, «Producción» → «Nuevo invernadero». Elegí «Urbana»: aparecen calle y número (obligatorios), piso,
   departamento (unidad), barrio y referencias. Elegí «Rural»: ruta y kilómetro (obligatorios) y lote.
4. Listas encadenadas: elegí una provincia (por ejemplo Misiones): el departamento se llena con sus departamentos y la
   localidad queda vacía. Elegí el departamento: la localidad se llena con las suyas. Cambiá la provincia: el
   departamento y la localidad se reinician. Probá con el teclado (flechas, Enter, Esc) y en un celular o con la ventana
   angosta.
5. Intentá guardar sin nombre, o con el nombre de un invernadero existente en otras mayúsculas o con espacios: el error sale
   junto al campo y lo escrito se conserva. Probá el formato: en una rural, el kilómetro «4», «4,5» y «875,5» se aceptan, y
   «abc», «4.5» (con punto) y «6,7777» no; en una urbana, el número «1234», «1234 bis» y «S/N» se aceptan, y «casa» no.
   Probá también el contenido: una ruta o una calle «-----------------» se rechaza, y «12», «RN 12» y «Ruta Nacional 12»
   se aceptan; un piso o un barrio de puros símbolos se rechaza, y vacío se acepta. Guardá una urbana y una rural, la primera sin personal y la segunda con
   un Agrónomo, un Capataz y un Vendedor.
6. Después de guardar vas a la ficha con el aviso «Invernadero creado: …». La ficha muestra la ubicación, el equipo, la
   marca «Sin sectores: todavía no se puede sembrar» y, en la que no tiene personal, el aviso «Faltan asignar…». No hay
   botones de modificar ni de baja (llegan con MAE-01b).
7. En «Producción» las dos tarjetas muestran su dirección, «Personal por asignar» y los «Sin asignar» y «No hace falta
   sin IoT» que correspondan. Dá de baja (en el admin de Django o con `shell`) la cuenta de un Capataz asignado: su
   invernadero pasa a mostrar «Inactivo» junto a su nombre.
8. Como Agrónomo, «Producción» muestra solo los invernaderos activos a tu cargo y no ofrece «Nuevo invernadero».
   Escribiendo a mano `/produccion/nuevo/` da el 403. Con la cuenta de Capataz, `/produccion/` da el 403.
9. Como Gerente, «Auditoría»: aparece «Alta de invernadero» con el invernadero y las personas asignadas como afectados y
   la tabla Campo / Antes / Después (Nombre, Estado, Tipo de dirección, Localidad…). Entrar a la lista o a la ficha no
   deja ningún registro nuevo.
10. Sin JavaScript (desactivalo en el navegador): al elegir el tipo de dirección o una provincia, el botón «Actualizar
    listas y datos de la dirección» arma los datos y las listas sin guardar.
11. Antes de mergear a main: Render corre `migrate` en cada despliegue. La `maestros 0002` inserta 3923 filas (unos
    segundos) y la `core 0010` cambia el `varchar` de `accion`. Revisá el log del primer despliegue.

## MAE-01b · Tarea MAE-01b (invernadero: modificar, reactivar y dar de baja)

Tarea MAE-01b (maestros), a mano. Con el entorno virtual activo y la base local (`python manage.py runserver`). No hay migraciones nuevas. Cuentas de prueba:
un Gerente, un Agrónomo, un Capataz y un Vendedor activos; y dos invernaderos creados con «Nuevo invernadero» (por ejemplo,
«Sur» urbano con Agrónomo y Capataz, y «Norte» rural sin personal).

1. Como Gerente, «Producción» → «Sur». En la ficha aparece la tarjeta «Acciones» con «Modificar» y «Dar de baja». Con la cuenta
   de Agrónomo (a cargo de «Sur») la ficha no tiene ninguna acción. El menú lateral sigue mostrando «Producción» en el mismo
   lugar (la entrada ahora la registra `maestros` al arrancar).
2. «Modificar»: el formulario arranca con el nombre, el tipo de dirección, la provincia, el departamento, la localidad, los
   datos de la dirección y el personal de «Sur». Cambiá solo el nombre y guardá: vas a la ficha con «Se guardaron los cambios
   de …» y, en «Auditoría», aparece «Modificación de invernadero» con una sola fila Campo / Antes / Después (Nombre).
3. Guardá sin cambiar nada: no se crea ningún registro nuevo en «Auditoría».
4. Probá el nombre de «Norte» escrito en otras mayúsculas o con espacios: el error sale junto al campo y se conserva lo escrito.
   Un nombre de puros guiones, o más de 80 caracteres, también se rechaza.
5. Cambiá solo la localidad (otra del mismo departamento): en «Auditoría» la única fila es «Localidad». Cambiá el tipo de
   dirección de urbana a rural (completando ruta y kilómetro) y guardá: «Auditoría» muestra «Tipo de dirección» urbana → rural,
   la calle y el número a «—» y la ruta y el kilómetro desde «—». Después volvé de rural a urbana: el espejo.
6. Aviso de la regla 2: cambiá el Capataz por otro y guardá. No se guarda: aparece la ventana «Confirmá el cambio de personal»
   con quién reemplaza a quién (todavía sin «Recibe…», porque aún no hay órdenes). «Volver al formulario» te deja con lo que
   escribiste, sin guardar. «Confirmar y guardar» guarda y va a la ficha; «Auditoría» muestra el Capataz anterior y el nuevo, y
   ambos figuran como afectados. Dejá el Agrónomo en «Sin asignar»: la ventana dice «El invernadero queda sin Agrónomo…».
7. Dá de baja la cuenta de un Capataz asignado (desde «Usuarios y seguridad») y abrí «Modificar» en su invernadero: el Capataz
   sigue elegido con «— inactivo». Guardar sin tocarlo no pide confirmar; reemplazarlo sí, y la lista no ofrece cuentas inactivas.
8. «Dar de baja» en «Sur»: se abre la ventana «¿Dar de baja Sur?» (no hay impedimentos todavía, porque aún no existen lotes,
   órdenes ni stock). «Cancelar» la cierra. «Dar de baja» te lleva a la ficha con «Sur se dio de baja.», «Inactivo» junto al
   nombre, el personal conservado y, en «Auditoría», «Baja de invernadero» (Estado: Activo → Inactivo).
9. Con el invernadero inactivo, la ficha ofrece solo «Reactivar» (no «Modificar» ni «Dar de baja»). Escribir a mano
   `/produccion/<id>/modificar/` te devuelve a la ficha con «solo se puede reactivar». «Reactivar» lo deja activo, sin ventana,
   con el aviso «Sus sectores siguen inactivos: los reactiva el Agrónomo», y «Auditoría» muestra «Reactivación de invernadero».
10. Con el Agrónomo o el Capataz: escribir a mano `/produccion/<id>/modificar/` o `/baja/` da el 403.
11. Sin JavaScript (desactivalo en el navegador): repetí los pasos 6 y 8. La ventana del cambio de personal y la de la baja
    vienen en la página (al principio), con sus botones; «Dar de baja» y «Confirmar y guardar» funcionan igual. Con
    JavaScript, las ventanas se abren sobre la página, con el foco en el botón principal y se cierran con Esc.
12. Con HTMX, «Dar de baja» abre la ventana sin recargar la página (compará la barra de direcciones: no cambia).
13. Pruebas de concurrencia (no hace falta el navegador): `python manage.py test maestros --keepdb --tag concurrencia` da
    10 pruebas OK. Corré una vez después `python manage.py test maestros --keepdb --parallel --exclude-tag concurrencia
    --exclude-tag migracion`: las de concurrencia vacían Georef y `ConGeoref` lo vuelve a cargar solo.
14. Antes de mergear a main: esta tarea no tiene migraciones, así que el despliegue de Render no cambia la base. Si todavía no se
    aplicaron en Neon las de MAE-01a (`core 0010`, `maestros 0001` y `0002`), hay que hacerlo antes.

## MAE-02a · Tarea MAE-02a (alerta: modelo, API y alertas de personal del invernadero)

Tarea MAE-02a (maestros), a mano. Con el entorno virtual activo y la base local (`python manage.py runserver`, con `DEBUG` encendido
para usar `/admin/`). Hay una migración nueva: `python manage.py migrate`. Cuentas de prueba: un Gerente, un Agrónomo, un Capataz y un
Vendedor activos.

1. `python manage.py migrate` aplica `maestros 0003_alerta`.
2. «Producción» → «Nuevo invernadero» sin personal. En «Auditoría», el alta muestra «Alertas creadas» (sin Agrónomo, sin Capataz y
   sin Vendedor; no sin Técnico). En `/admin/` hay 3 alertas activas, todas «para el Gerente».
3. «Nuevo invernadero» con el personal completo (Agrónomo, Capataz y Vendedor): no se crea ninguna alerta y el alta no muestra
   «Alertas creadas» en «Auditoría».
4. En el invernadero sin personal, «Modificar», asigná un Capataz y confirmá. «Auditoría» muestra «Alertas resueltas» con
   «Invernadero sin Capataz activo»; en el admin esa alerta queda resuelta, con su fecha de resolución, y sigue «no leída». Las de
   Agrónomo y Vendedor siguen activas.
5. Quitá el Capataz: la ventana dice que el rol queda vacío; al confirmar se crea una alerta nueva y la anterior sigue resuelta.
6. Guardá sin cambiar nada: no hay registro nuevo en «Auditoría» ni alertas nuevas (D-28).
7. Dá de baja el invernadero: «Auditoría» lista «Alertas resueltas» con todas las activas y en el admin no queda ninguna activa.
   Reactivalo: se vuelven a crear las de los roles sin una persona activa.
8. Asigná un Capataz, dá de baja su cuenta (desde «Usuarios y seguridad») y después modificá solo el nombre del invernadero: se
   crea «Invernadero sin Capataz activo» (consecuencia de D-41: la baja de la cuenta todavía no crea la alerta, es de MAE-02b, y
   el invernadero la recibe en su primera modificación con cambios; guardar sin cambios no la crea).
9. Renombrá un invernadero que tenga alertas activas: en el admin, ninguna muestra el nombre viejo (la descripción es solo el nombre
   del tipo; el invernadero está en su propio campo).
10. Sin JavaScript (desactivalo en el navegador), los pasos 4, 5 y 7 funcionan igual: no hay pantallas nuevas.
11. El traspaso de MD-60, la regla D4 y el «N alertas activas» de la regla 2 no se pueden ver a mano en la 02a: ningún tipo de
    `maestros` va al Agrónomo (los cuatro `sin_{rol}` son de destinatario `GERENTE`), así que la ventana nunca muestra alertas en
    «Recibe». Los cubren solo las pruebas.
12. `python manage.py test maestros core --keepdb --tag concurrencia` da 30 pruebas OK. Después, una vez,
    `python manage.py test maestros core --keepdb --exclude-tag concurrencia`: las de concurrencia vacían Georef y `ConGeoref` lo
    vuelve a cargar solo.
13. Después del merge: verificar en el log del despliegue de Render que se aplicó `maestros 0003_alerta` (Render corre `migrate` en
    cada despliegue; la migración es solo esquema).

## CFG · Configuración del repositorio

1. Después del primer merge con el workflow: en GitHub, Settings → Branches (o Rules), exigir que
   el check de `pruebas.yml` pase para poder mergear a main.
