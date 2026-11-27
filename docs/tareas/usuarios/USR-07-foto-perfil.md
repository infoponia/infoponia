# USR-07 · Foto de perfil y logo de la organización

Estado: hecha (27/11/2026) | App: core y maestros | Rama: feature/usr-07-foto-perfil | Ronda: —

Depende de: nada en el código. Las decisiones están cerradas (D-20 y D-106). R2 ya está activado, con el bucket privado,
el token limitado y las variables cargadas en Render (27/11/2026). Con `DJANGO_DEBUG` distinto de `1` y sin esas variables,
Django no arranca (D-106, punto 4).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| USR-GST-PRF | Gestionar Perfil (la foto) | docs/casos_de_uso/usuarios.md | Solo la foto; el resto ya está hecho |
| USR-MOD-USR | Modificar Usuario (quitar la foto, regla 8) | docs/casos_de_uso/usuarios.md | Solo la quita de la foto |
| ADM-MOD-ORG | Modificar Perfil de la Organización (el logo) | docs/casos_de_uso/maestros/configuracion.md | Solo el logo; el resto ya está hecho (MAE-04) |

## Leer

- Casos de uso: docs/casos_de_uso/usuarios.md — USR-GST-PRF (regla sobre la foto), USR-MOD-USR (regla 8), SEG-19,
  «Pistas técnicas» (SEG-19); docs/casos_de_uso/maestros/configuracion.md — ADM-MOD-ORG y «Cómo se aplica…» (Logo)
- Modelo: docs/modelo/maestros.md — `PerfilOrganizacion` (fila `logo`)
- Decisiones: D-106 (todo: almacenamiento, foto y logo), D-20, D-48 (identidad: el logo se suma a `Identidad`), D-28
  (sin cambios no se audita), D-29 (`STORAGES["staticfiles"]` no se toca), D-24 (la carga desde el celular se prueba en
  un dispositivo real), D-31 (el lugar de la foto ya está preparado en Mi perfil)
- Código existente: core/extensiones.py («Identidad de la organización»), core/identidad.py, maestros/servicios/perfil.py,
  la pestaña «Organización» (maestros/forms.py, maestros/views.py y su plantilla), core/templates/core/base_con_sesion.html
  y base_sin_sesion.html (el cuadro `.logo`)
- Pantallas: docs/prototipos/cuentas_y_seguridad.html — `vPerfil`, `handlePhoto`; docs/prototipos/produccion/
  datos_maestros_y_produccion.html — `INIT.config` (campo del logo; su texto «formato no definido» ya no rige: D-106)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md

## Límites

- Crea modelos: ningún modelo nuevo. Dos campos nuevos en modelos mergeados, con permiso del estudiante (D-106): la foto en
  `core.Usuario` y `logo` en `maestros.PerfilOrganizacion`
- Migraciones: solo nuevas, una en `core` (la foto) y una en `maestros` (el logo). Ninguna carga datos
- Permitido fuera de las apps: `config/settings.py` (almacenamiento), `requirements.txt` (Pillow y `django-storages[s3]`)
- Dependencias nuevas: Pillow y `django-storages[s3]` (incluye `boto3`), aprobadas en D-106
- Fuera de alcance: la foto de las cuentas vinculadas (no se comparte, D-20); el logo en los correos y en los comprobantes
  (D-106, punto 14)

## Pasos

1. **Almacenamiento y módulo de imágenes.** `STORAGES` en `config/settings.py` (D-106, puntos 1 a 4) y `core/imagenes.py`
   (puntos 5 a 8), con sus pruebas.
2. **Foto de perfil** (`core`): campo, servicio, Mi perfil (cargar, cambiar, quitar) y la quita desde Modificar Usuario. Ampliación
   del 27/11/2026: el **editor de encuadre** (recorte cuadrado elegido por la persona; `core/imagenes.py` recibe `recorte` y
   `lado_minimo`, el servicio y la vista lo pasan, `encuadre_foto.js` arma el editor).
3. **Logo** (`maestros`): campo, servicio `modificar_perfil` (todo o nada y auditoría, puntos 12 y 13), pestaña
   «Organización» y registro de la identidad con `logo_url`.
4. **Marco** (`core`): `Identidad` con `logo_url` (punto 15) y el cuadro `.logo` del encabezado y de las pantallas sin
   sesión (punto 14).
5. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, «Cuando exista
   PerfilOrganizacion», cerrar el logo; en `docs/modelo/maestros.md`, la fila `logo` como hecha.

## Hecho cuando

- Cada cuenta puede cargar, cambiar y quitar su foto desde Mi perfil, con las reglas de SEG-19, D-20 y D-106; quien
  gestiona la cuenta puede quitarla pero no cambiarla.
- El Gerente puede cargar, cambiar y quitar el logo en la pestaña «Organización»; se ve en el encabezado y en las
  pantallas sin sesión; sin logo, sigue el ícono.
- `STORAGES["default"]` elige R2 si existe `R2_BUCKET`, el disco local si no (solo en desarrollo), e `InMemoryStorage`
  en las pruebas. Con `DJANGO_DEBUG` distinto de `1` y alguna variable de R2 faltante, `config/settings.py` lanza
  `ImproperlyConfigured` nombrando la variable (D-106, punto 4); una prueba lo cubre.
- Las pruebas cubren, como mínimo:
  - Del módulo de imágenes: un archivo de más de 5 MB rechazado; un archivo que no es imagen (aunque tenga extensión
    `.jpg`) rechazado; un GIF y un SVG rechazados; una imagen con orientación EXIF que queda derecha; la salida es WebP
    sin metadatos.
  - De la foto: salida de 256 × 256; nombre `fotos_perfil/<uuid4>.webp`; el archivo anterior se borra al cambiar y al
    quitar, y no se borra si la transacción se deshace.
  - Del logo: una imagen de 1000 × 400 queda de 512 × 205 (sin recorte); una de 300 × 100 no se agranda; la
    transparencia se conserva; nombre `logos/<uuid4>.webp`; un logo inválido junto con un nombre válido no guarda nada
    (regla 7); la auditoría registra «sin logo» → «con logo», «con logo» → «logo nuevo» y «con logo» → «sin logo», y no
    menciona el logo si no cambió; solo el Gerente lo modifica; el archivo nuevo se borra si la transacción se deshace.
  - Del marco: con logo, el encabezado y la pantalla de inicio de sesión muestran la imagen en lugar del ícono; sin logo,
    el ícono; `Identidad("Nombre", "#336699")` sigue funcionando con dos valores.
- Pruebas: core/tests/test_imagenes.py, core/tests/test_usr_gst_prf.py, core/tests/test_identidad.py,
  maestros/tests/test_adm_mod_org.py, maestros/tests/test_identidad_organizacion.py
- Comando de pruebas: python manage.py test core.tests.test_imagenes core.tests.test_usr_gst_prf core.tests.test_identidad maestros.tests.test_adm_mod_org maestros.tests.test_identidad_organizacion --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Ya hecho por el estudiante (27/11/2026): R2 activado, bucket **sin acceso público**, token de lectura y escritura de
objetos limitado al bucket, y `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` y `R2_BUCKET` en Render.

### Antes de empezar

- **Entorno.** En la rama `feature/usr-07-foto-perfil`, con el entorno virtual activo: `pip install -r requirements.txt` (suma Pillow,
  `django-storages`, `boto3` y lo que traen, y `tblib`) y `python manage.py migrate`. Aplica dos migraciones: `core` 0053 (la columna
  `foto_perfil`) y `maestros` 0014 (la columna `logo`). Cada una agrega **una columna vacía**; no toca datos.
- **En desarrollo se guarda en el disco, no en R2.** En tu `.env` las cuatro variables de R2 están **comentadas** y `DJANGO_DEBUG=1`:
  las imágenes van a la carpeta `media/` de la raíz del proyecto (`media/fotos_perfil/` y `media/logos/`), que Git ignora. Los pasos 1 a 23
  se hacen así. R2 se prueba una sola vez, en el paso 24.
- **Arrancar:** `python manage.py runserver` y abrí `http://localhost:8000`.
- **Cuentas que hay que tener** (si no existen, crealas; las contraseñas las elegís vos, no las escribas en ningún archivo del repo):
  1. **Administrador**: `python manage.py createsuperuser`.
  2. **Gerente**: entrá como Administrador → «Cuentas» → «Alta de Gerente» (por ejemplo, Gabriela Sosa, `gabriela.sosa@example.com`) con contraseña
     temporal; entrá con ella y elegí una propia.
  3. **Vendedor**: como Gerente → «Usuarios y seguridad» → «Nuevo usuario» (Vera Gómez, `vera.gomez@example.com`, rol Vendedor), contraseña temporal;
     entrá con ella y elegí una propia.
  4. **Agrónomo**: otro usuario (Aníbal Ríos, `anibal.rios@example.com`), igual que el anterior. Solo se usa para ver que no tiene acceso.
- **Imágenes de prueba** (tenelas en una carpeta aparte, fuera del repo):
  - (a) una **foto vertical sacada con el celular**, JPG de 2 a 4 MB;
  - (b) una imagen **de más de 5 MB** (una foto sin comprimir o un PNG grande);
  - (c) `texto.jpg`: un archivo de texto cualquiera al que le cambiás la extensión a `.jpg`;
  - (d) un `.gif` (cualquiera); (e) un `.svg` (cualquiera);
  - (f) un **PNG con fondo transparente de unos 1000 × 400 px** (cualquier logo);
  - (g) una imagen chica de 100 × 80 px;
  - (h) una imagen de 50 × 50 px;
  - (i) una foto con un detalle fácil de reconocer lejos del centro (una cara o un cartel en una esquina).

### Foto de perfil (entrá como Vera, el Vendedor)

1. **Sin foto.** Menú de cuenta (arriba a la derecha) → «Mi perfil». Tiene que verse el avatar con las letras «VEN», los botones «Elegir foto» (y
   «Tomar foto» solo en un celular), el texto «JPG, PNG o WebP, de hasta 5 MB. Se recorta en forma cuadrada y se achica sola.» y **ningún** botón «Quitar».
   ✔ `test_flujo_principal_sin_foto_ofrece_elegirla_y_muestra_la_sigla`.
2. **Cargar.** «Elegir foto» → imagen (a). Se abre la ventana «Encuadrá tu foto» (pasos 32 a 38); tocá «Guardar foto» sin mover nada: aparece «Subiendo la foto…» y, al volver, el aviso
   «Foto de perfil actualizada.». El avatar de Mi perfil (72 px) y el del encabezado muestran la foto, redonda, recortada en cuadrado y centrada; los botones pasan a «Cambiar foto» y «Quitar». En
   `media/fotos_perfil/` hay **un** archivo `.webp` con un nombre de letras y números, **no** el de tu archivo.
   ✔ `test_flujo_principal_carga_la_foto_y_se_ve_en_el_perfil_y_en_el_encabezado`, recorrido (primer paso).
3. **Orientación.** La foto vertical del celular se ve **derecha**, no acostada. ✔ `test_d106_la_orientacion_exif_queda_derecha` (con píxeles); el
   aspecto lo confirmás vos.
4. **No se agranda.** «Cambiar foto» → imagen (g, 100 × 80) → «Guardar foto» sin mover nada. Queda de **80 × 80** (clic derecho sobre el archivo de `media/fotos_perfil/` → Propiedades →
   Detalles): se recortó en cuadrado y no se agrandó. ✔ `test_d106_una_foto_chica_no_se_agranda`, `test_recorte_valido_sobre_una_imagen_chica_no_se_agranda`.
5. **Cambiar.** «Cambiar foto» → otra imagen (a o cualquiera). Mismo aviso. En `media/fotos_perfil/` sigue habiendo **un solo** archivo: el anterior se
   borró. ✔ `test_flujo_principal_cambiar_reemplaza_la_foto`.
6. **Errores.** Probá cada uno; en todos, la foto de antes queda y **no** aparece un archivo nuevo en `media/fotos_perfil/`:
   - (b) más de 5 MB → **al elegirla**, sin subir nada, aparece debajo de los botones «La imagen pesa más de 5 MB. Elegí una más liviana.», sin subir nada y **sin abrir el editor** (es JavaScript;
     el servidor también lo controla);
   - (c) `texto.jpg` → no se abre el editor y debajo de los botones aparece «No se pudo abrir esa imagen. Probá con una foto en formato JPG, PNG o WebP.» (el navegador no puede abrirla);
   - (d) el `.gif` → el editor se abre (el navegador sí puede mostrarla) y, al «Guardar foto», aviso rojo «Solo se aceptan imágenes JPG, PNG o WebP.» (si el selector no te deja elegirla, cambiá su filtro a «Todos los archivos»);
   - (e) el `.svg` → puede abrirse el editor; al «Guardar foto», aviso rojo «No se pudo abrir ese archivo como imagen. …» (o, si el navegador no la abre, el mensaje de (c));
   - (h) la imagen de 50 × 50 → debajo de los botones, «La foto es demasiado chica: tiene que medir al menos 64 px de lado.», y **no** se abre el editor.
   ✔ `test_ext_archivos_no_validos_avisan_el_motivo_y_no_cambian_la_foto`, `test_d106_un_gif_se_rechaza`, `test_d106_un_svg_se_rechaza`.
7. **Quitar.** «Quitar» → aviso «Se quitó la foto de perfil.»; vuelven las letras «VEN» y `media/fotos_perfil/` queda vacía.
   ✔ `test_flujo_principal_quitar_deja_la_cuenta_sin_foto`.
8. **Dejala cargada.** Cargá otra foto (para el paso siguiente).

### Quien gestiona la cuenta solo puede quitar la foto (Gerente y Administrador)

9. **La ficha.** Entrá como **Gerente** → «Usuarios y seguridad» → Vera Gómez. En «Datos» se ve su foto, el botón «Quitar foto» y el texto «Cada persona
   cambia su foto desde Mi perfil; acá solo se puede quitar.». **No hay forma de cargar ni de cambiar** una foto (tampoco en «Modificar datos»).
   ✔ `test_flujo_principal_la_ficha_con_foto_la_muestra_y_ofrece_quitarla`, `test_regla_8_modificar_datos_no_permite_cambiar_la_foto`.
10. **Confirmar.** «Quitar foto» → ventana «¿Quitar la foto de perfil?». «Cancelar»: no cambia nada. Otra vez «Quitar foto» → «Quitar foto»: aviso «Se quitó
    la foto de perfil de Vera Gómez.», la ficha dice «Sin foto de perfil.», ya no hay botón y el archivo desapareció de `media/fotos_perfil/`.
    ✔ `test_flujo_principal_abrir_la_ventana_no_cambia_nada`, `test_flujo_principal_confirmar_quita_la_foto_y_avisa`.
11. **No se audita.** «Auditoría»: no hay ningún registro de la carga, del cambio ni de la quita de una foto.
    ✔ `test_post_d_quitar_la_foto_no_se_audita`, `test_regla_4_ni_la_carga_ni_la_quita_se_auditan`, recorrido (cierre del primer recorrido).
12. **Alcance.** Como Gerente cargá tu propia foto en «Mi perfil». Entrá como **Administrador** → «Cuentas» → ficha del Gerente: «Quitar foto» está y
    funciona. De vuelta como **Gerente**, escribí `http://localhost:8000/usuarios/<id del Administrador>/foto/quitar/` (el id está en la dirección de su ficha
    en la sesión del Administrador): «Prohibido (403)» y la foto del Administrador sigue.
    ✔ `test_regla_1_fuera_del_alcance_da_403_y_la_foto_queda`, `test_recorrido_alcance_por_rol_en_la_foto`.
13. **Sin acceso.** Como **Agrónomo**, escribí `http://localhost:8000/usuarios/<id de Vera>/foto/quitar/`: «Prohibido (403)». Sin sesión: te lleva a iniciar sesión.
    ✔ `test_seg13_quien_no_gestiona_recibe_403`.

### Logo de la organización (entrá como Gerente)

14. **Estado inicial.** «Configuración» → pestaña «Organización». En «Identidad visual», debajo de los colores, hay «Logo (opcional)» con el campo para elegir
    un archivo y el texto «JPG, PNG o WebP, de hasta 5 MB. No se recorta: el lado mayor queda en 512 px como máximo y se conserva la transparencia. Si no
    elegís un archivo, el logo no cambia.». **No** hay casilla «Quitar el logo». El encabezado muestra el ícono de siempre.
    ✔ `test_flujo_principal_la_pestana_organizacion_muestra_los_datos_actuales_y_el_campo_del_logo`.
15. **Cargar.** Elegí el logo (f) → «Guardar cambios». Aviso «Se guardó la configuración.». La pestaña muestra la miniatura «Logo actual de la organización» y
    la casilla «Quitar el logo». El **encabezado** muestra el logo en un cuadro blanco de 32 px con borde, **sin deformarse** y sin quedar sobre el verde.
    En `media/logos/` hay **un** `.webp`; en Propiedades mide **512 × 205** (si el tuyo es de otra proporción, el lado mayor mide 512).
    ✔ `test_flujo_principal_carga_el_logo_y_se_ve_en_la_pestana`, `test_regla_4_un_logo_apaisado_se_achica_a_512_de_lado_mayor_sin_recortar`, recorrido.
16. **Pantalla sin sesión.** Cerrá la sesión: el inicio de sesión muestra el logo junto al nombre de la organización, no el ícono.
    ✔ `test_d106_con_logo_el_marco_muestra_la_imagen_en_lugar_del_icono`.
17. **Sin tocar el logo.** Entrá de nuevo, cambiá solo el teléfono y guardá: el logo sigue igual y el archivo de `media/logos/` es **el mismo**.
    ✔ `test_regla_1_guardar_sin_elegir_un_archivo_no_toca_el_logo`.
18. **Cambiar.** Elegí otro logo → guardar. En `media/logos/` sigue **un solo** archivo.
19. **Errores del logo.** Cambiá el «Nombre» a «Vivero de prueba» y elegí (c) `texto.jpg`: debajo del campo del logo, «No se pudo abrir ese archivo como imagen…».
    **No se guardó nada**, ni el nombre; el campo «Nombre» **conserva lo que escribiste**. Repetí con (d) el `.gif` (mensaje «Solo se aceptan imágenes JPG, PNG o
    WebP.») y con (b) la imagen de más de 5 MB («La imagen pesa más de 5 MB…»). Ver que no aparece ningún archivo nuevo en `media/logos/`.
    ✔ `test_regla_7_un_logo_invalido_marca_su_campo_y_conserva_lo_que_escribio_el_gerente`.
20. **Logo nuevo y «Quitar» a la vez.** Con un logo ya cargado: escribí «Calle 123» en «Dirección», elegí un archivo y marcá «Quitar el logo» → «Guardar cambios».
    Error debajo del campo del logo: «Elegí un logo nuevo o marcá «Quitar el logo», pero no las dos cosas.». «Dirección» conserva «Calle 123», la casilla sigue
    marcada, el logo actual se ve igual y **no se guardó nada**. (El archivo elegido hay que elegirlo otra vez: el navegador no permite conservarlo.)
    ✔ `test_regla_7_un_logo_nuevo_con_quitar_marcado_es_un_error_que_conserva_lo_escrito`.
21. **Quitar.** Marcá «Quitar el logo» y guardá: vuelve el ícono en el encabezado y en el inicio de sesión, la casilla desaparece y `media/logos/` queda vacía.
    Con la organización **sin logo**, guardar cambios no muestra ninguna casilla. ✔ `test_flujo_principal_quitar_el_logo_borra_el_archivo_y_la_casilla_desaparece`,
    `test_d28_quitar_el_logo_sin_logo_no_falla_no_audita_y_no_toca_el_almacenamiento`.
22. **Auditoría.** «Auditoría» → los registros de «modificación de perfil» de estos pasos dicen del logo «sin logo → con logo», «con logo → logo nuevo» y «con logo
    → sin logo»: nunca la imagen ni su nombre; el paso 17 (solo teléfono) no menciona el logo. ✔ `test_post_b_*` de `AdmModOrgLogoServicioTests`, recorrido (auditoría).
23. **Otros roles.** Como **Agrónomo** (o Vendedor) escribí `http://localhost:8000/configuracion/?pestana=organizacion`: «Prohibido (403)».
    ✔ `test_pre_a_solo_el_gerente_guarda_el_logo`, recorrido (final).

### R2 de verdad (una sola vez, antes de mergear)

24. En el `.env`, **descomentá** las cuatro variables (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`) y reiniciá `runserver`. Cargá una foto
    (como Vera, paso 2) y un logo (paso 15): se ven en la app (la dirección de la imagen empieza con `https://<tu cuenta>.r2.cloudflarestorage.com/` y lleva una firma larga).
    En el panel de Cloudflare → R2 → tu bucket aparecen `fotos_perfil/<…>.webp` y `logos/<…>.webp`. «Quitar» la foto y «Quitar el logo»: los objetos **desaparecen**
    del bucket (refrescá el panel). **Ojo:** es el mismo bucket que usa Render; lo que cargues acá queda en el bucket real, así que dejalo vacío al terminar.
25. **Volvé a comentar las cuatro variables** del `.env` y reiniciá `runserver`: en desarrollo se vuelve a usar `media/`.

### Navegador real (obligatorio: hay formularios con archivo y una pantalla sin sesión)

26. **Navegador real.** Abrí la pantalla de **inicio de sesión en una ventana privada** (sin sesión): tiene que mostrar el logo (paso 16). Después, con sesión, **enviá hasta el
    final** el formulario de la foto (paso 2) y el de la pestaña «Organización» con el logo (paso 15). Tienen que terminar con su aviso. Si aparece «Prohibido (403)» o
    «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver.
27. **(Opcional) Sin JavaScript.** Desactivá JavaScript y abrí «Mi perfil»: aparece el botón «Guardar foto»; elegí un archivo y tocalo: se carga igual, recortada desde el centro (sin JavaScript no hay editor de encuadre y el texto lo dice). En «Organización» el logo
    se guarda con «Guardar cambios» y los errores salen debajo del campo (la página entera).
28. **(Opcional) Teclado.** Con Tab, el foco llega al campo de archivo (los botones «Elegir foto» y «Tomar foto» son etiquetas de un campo oculto): si no ves ninguna señal
    de foco, avisá (riesgo conocido, ver «No pude verificar»).

### Editor de encuadre de la foto (computadora y celular; ampliación del 27/11/2026)

Los pasos 32 a 41 están numerados al final para no cambiar los de arriba. Entrá como **Vera** (Vendedor) en «Mi perfil». Lo que hace el JavaScript no lo ve el cliente de Django: esto se
prueba solo a mano.

32. **Se abre el editor.** «Elegir foto» → imagen (i). **No** se envía sola: se abre la ventana «Encuadrá tu foto» con la foto dentro de un cuadro oscuro, un círculo blanco que marca el avatar (lo de afuera
    del círculo se oscurece), los botones «−» y «+», «Cancelar» y «Guardar foto», y la indicación «Arrastrá la foto o usá las flechas; acercá o alejá con + y −.». Al abrir, la foto está centrada y el
    cuadro cubre su lado corto; el foco está en el cuadro (se ve su borde). El fondo de la página queda bloqueado. ✔ la pantalla trae la ventana, los botones, los tres campos ocultos y el respaldo sin JavaScript:
    `test_flujo_principal_la_pantalla_trae_el_editor_y_el_respaldo_sin_javascript`.
33. **Arrastrar y zoom con el mouse.** Arrastrá la foto con el botón apretado: se mueve y **nunca deja un hueco** (el borde de la foto no entra al cuadro). Con la rueda del mouse acercás y alejás alrededor del
    puntero. Alejando no pasa del mínimo (la foto no se achica más que el cuadro) y acercando hay un máximo.
34. **Botones y teclado.** Los botones «+» y «−» acercan y alejan un 10 % hacia el centro. Con el foco en el cuadro (Tab), las **flechas** mueven la foto (con Shift, más rápido) y las teclas **+** y **−** hacen
    zoom. Todo se puede hacer sin mouse; con Tab se llega a «Cancelar» y «Guardar foto», y el foco no sale de la ventana.
35. **La foto guardada coincide con la guía.** Encuadrá el detalle (la cara o el cartel) dentro del círculo y tocá «Guardar foto»: aviso «Foto de perfil actualizada.». El avatar de Mi perfil y el del encabezado
    muestran **exactamente lo que había dentro del círculo** (mismo detalle, misma posición y mismo tamaño). ✔ el servidor recorta la zona pedida: `test_recorte_cada_cuadrante_sale_con_su_color`,
    `test_flujo_principal_con_coordenadas_guarda_la_zona_elegida`; que el editor mande las coordenadas correctas, a mano.
36. **Cancelar y Esc.** Elegí otra foto, movela y tocá «Cancelar»: la ventana se cierra, la foto actual no cambia, no se sube nada y el foco vuelve a «Elegir foto». Volvé a elegir **el mismo archivo**: el editor
    se abre de nuevo. Repetí con la tecla **Esc**.
37. **Foto girada (EXIF).** Con la imagen (a) (vertical, sacada con el celular): en el editor se ve **derecha**, igual que en tu visor de fotos. Encuadrá un detalle de la mitad de arriba y guardá: la foto guardada
    muestra ese detalle y derecha. Si el detalle sale de otra zona o la foto sale acostada, **avisá**: es el riesgo principal del editor (las coordenadas son las de la imagen ya girada; D-106).
    ✔ el servidor: `test_recorte_con_exif_rotado_usa_las_coordenadas_de_la_imagen_girada`; lo que ve el navegador, solo a mano.
38. **Zoom máximo.** Con la imagen (g, 100 × 80) acercá todo lo que deje el editor: se detiene cuando el círculo cubre 64 px de la imagen. Guardá: la foto mide **64 × 64**.
    ✔ `test_recorte_los_bordes_validos_se_aceptan`.
39. **Celular: dedo.** En el celular, «Elegir foto» (galería). En el editor, un dedo arrastra y **dos dedos pellizcan** (acercan y alejan alrededor de los dedos). Mientras tocás el cuadro, la página **no** se
    desplaza ni se agranda por su cuenta. (D-24)
40. **Celular: cámara.** «Tomar foto» (cámara frontal; solo se ve en pantallas táctiles): sacá la foto, se abre el editor, encuadrá y guardá: se ve en el avatar con lo encuadrado. Probá en vertical y en horizontal.
41. **Celular: la ventana.** En pantalla angosta la ventana entra completa o se desplaza dentro de sí misma, los botones «Cancelar» y «Guardar foto» se ven y se tocan (también con el teclado en pantalla
    abierto), y «Cancelar» cierra y deja todo como estaba.

### Después del despliegue en Render

29. **Despliegue.** En el log de Render, `migrate` aplicó `core` 0053 y `maestros` 0014 y el servicio **arrancó** (si faltara alguna de las cuatro variables de R2, Django no arranca
    y el log lo dice con el nombre de la variable).
30. **Celular (D-24).** Entrá a Mi perfil desde el celular: se ve «Tomar foto». Sacá una foto con la cámara: se carga derecha y se ve en el encabezado. Probá también una de la
    galería. Mirá el logo en el encabezado y en el inicio de sesión.
31. **Vencimiento de la URL (D-106 punto 2).** Con la imagen a la vista, clic derecho → «Copiar dirección de la imagen». En una ventana privada abre. **Pasada la hora**, la misma
    dirección ya no abre (error de acceso). Sin los parámetros que siguen al `?`, nunca abre.

## Cierre (la completa Claude Code al cerrar)

### Qué se hizo

- **Almacenamiento** (`config/settings.py`): `STORAGES["default"]`: `InMemoryStorage` con `manage.py test`; R2 (`S3Storage` de `django-storages`, endpoint
  `https://<cuenta>.r2.cloudflarestorage.com`, región `auto`, firma `s3v4`, URL firmada de 3600 s) si existe `R2_BUCKET`; disco local (`media/`) solo con DEBUG.
  Con `DJANGO_DEBUG` distinto de `1` y sin las cuatro variables, `ImproperlyConfigured` con los nombres que faltan. `STORAGES["staticfiles"]` queda con
  `StaticFilesStorage`, el de hoy.
- **`core/imagenes.py`** (nuevo): tope de 5 MB antes de abrir, formato real (JPG, PNG, WebP; no GIF ni SVG), límite propio de 40 millones de píxeles decidido con la cabecera,
  aviso de «bomba de descompresión» de Pillow tratado como error, `Image.draft()` en los JPEG, orientación EXIF, recorte cuadrado **elegido por la persona** (o central) con `recorte=(x, y, lado)` y `lado_minimo`, WebP sin metadatos desde una imagen nueva,
  nombre `uuid4`, borrado del archivo anterior con `transaction.on_commit` y del nuevo si la operación falla.
- **Foto** (`core`): `Usuario.foto_perfil` + migración `0053`; servicios `cambiar_foto_perfil`, `quitar_foto_perfil` y `quitar_foto_de_cuenta` (con el bloqueo `FOR NO KEY UPDATE`
  de la cuenta); «quitar_foto» en `acciones_permitidas`; Mi perfil (`mi-perfil/foto/` y `mi-perfil/foto/quitar/`), la ficha (`usuarios/<id>/foto/quitar/`, con ventana de confirmación) y el avatar
  del encabezado con la foto (`_avatar.html`); el **editor de encuadre** (`core/static/core/js/encuadre_foto.js`, propio, sin bibliotecas: arrastrar, pellizcar, rueda, «+» y «−», flechas; «Guardar foto»
  completa `recorte_x`, `recorte_y` y `recorte_lado` y envía el formulario) sobre la ventana de `infoponia.js`, que ahora se puede abrir desde otro script y avisa al cerrarse; la vista lee los tres campos y los pasa a
  `cambiar_foto_perfil(usuario, archivo, recorte=None)`.
- **Logo** (`maestros`): `PerfilOrganizacion.logo` + migración `0014`; `modificar_perfil(actor, logo=None, quitar_logo=False, **datos)` (todo o nada, auditoría «sin logo» / «con logo» / «logo nuevo»);
  la pestaña «Organización» con miniatura, casilla y campo de archivo; `Identidad.logo_url` y `identidad.logo_de_la_organizacion()`; el cuadro `.logo` del encabezado y de las pantallas
  sin sesión (`_logo.html`).
- **Fuera de las apps, autorizado por el estudiante:** `.github/workflows/pruebas.yml` (cuatro variables de R2 falsas; el CI corre `check` y `makemigrations --check` con DEBUG apagado),
  `config/urls.py` (sirve `media/` solo con DEBUG y disco local), `.gitignore` (`media/`) y `.env.example`.
- **Dependencias** (D-106, aprobadas): `pillow==13.0.0`, `django-storages==1.14.6` y lo que traen: `boto3==1.44.12`, `botocore==1.44.12`, `s3transfer==0.19.3`, `jmespath==1.1.0`,
  `python-dateutil==2.9.0.post0`, `six==1.17.0` y `urllib3==2.8.0`. Pillow 13.0.0 exige Python ≥ 3.11 (PyPI): lo cumplen el `.venv` (3.11.0) y `pruebas.yml` (3.11).

### Precisiones de D-106 (decididas con el estudiante durante la tarea)

1. **Punto 4, R2 incompleto en desarrollo.** Con `R2_BUCKET` y DEBUG, si falta otra de las tres variables también se lanza `ImproperlyConfigured` (sin ellas `boto3` buscaría credenciales por su cuenta). Una
   variable vacía o de solo espacios cuenta como faltante.
2. **Punto 5, la foto no se agranda.** Se recorta en cuadrado y se achica **hasta** 256 × 256, nunca se agranda (D-20 dice «la achica»): una foto de 100 × 80 sale de 80 × 80.
3. **Punto 5, límite propio de píxeles.** Además de la protección de Pillow, se rechazan las imágenes de más de 40 millones de píxeles (`imagen_enorme`), con la cabecera y sin decodificar; el aviso de Pillow
   (entre su límite y el doble) también es un rechazo. En los JPEG se usa `Image.draft()` para decodificar a escala reducida.
4. **Punto 12, logo nuevo y «Quitar el logo» a la vez** es un error en el campo `logo` (código `logo_y_quitar`): no se guarda nada y los demás campos conservan lo que escribió el Gerente.
5. **Punto 11, redondeo.** Al achicar el logo, el lado mayor pasa a 512 y el menor se proporciona y se **redondea al entero más cercano** (1000 × 400 → 512 × 204,8 → 512 × 205).
6. **Punto 13, «Quitar el logo» sin logo** no falla, no registra «sin logo» y no toca el almacenamiento; enviar el formulario sin archivo (`logo=None`) deja el logo y su archivo intactos.
7. **Nombre del campo** de la foto: `Usuario.foto_perfil` (D-20 y D-106 no lo nombraban).
8. **Punto 4 y D-29, `staticfiles`.** Dicen «el de WhiteNoise», pero hoy `settings.py` no define `STORAGES`: WhiteNoise solo sirve como middleware y los estáticos usan el
   `StaticFilesStorage` de Django. Se dejó ese (no cambia nada); falta corregir el texto de las dos decisiones (va a `temas_abiertos`).
9. **Ampliación del 27/11/2026: el recorte de la foto lo elige la persona** (reemplaza al central fijo de la precisión 2; sin JavaScript sigue central). Viajan el archivo y tres enteros, `recorte_x`, `recorte_y` y
   `recorte_lado`, en píxeles de la imagen ya orientada; el servidor orienta, valida, recorta y achica; códigos `recorte_incompleto`, `recorte_no_numerico`, `recorte_negativo`, `recorte_chico`,
   `recorte_mayor_que_la_imagen` y `recorte_fuera_de_la_imagen`; todo o nada.
10. **Lado mínimo de 64 px para toda foto**, con o sin encuadre (`imagen_chica`); el logo no tiene mínimo. Una foto de 64 × 48, que antes entraba (salía de 48 × 48), ahora se rechaza.
11. **Punto 8:** `procesar` suma `recorte` y `lado_minimo` (el recorte solo con recorte cuadrado, si no `ValueError`).
12. **`Image.draft()` con encuadre:** se pide un tamaño que deje el recorte reducido en al menos lo que mide la salida y las coordenadas se escalan de forma explícita; el límite de 40 millones se sigue decidiendo
    desde la cabecera. En un PNG (la etiqueta de orientación viene después de los píxeles) el recorte se valida con la imagen ya decodificada y orientada.

### Pantallas: lo que se corrigió del prototipo (D-61)

- **El error de una foto no válida** (`S.photoErr` del prototipo, debajo de los botones) se muestra como **aviso breve** (D-29), porque después del POST se vuelve a Mi perfil con una redirección.
  Respaldo en D-29, frase exacta: «Los avisos (`django.contrib.messages`, y los que genera la propia pantalla, como «Contraseña copiada.») se muestran como avisos breves.». Aclaración
  honesta: esa frase habla de los avisos en general y no menciona los errores de un archivo; la misma decisión dice «Los errores que se muestran debajo de los campos de un formulario no son avisos y
  no cambian» (los del logo, que sí son de un campo, quedan debajo de su campo). La corrección de la foto la aprobó el estudiante. Precedente en el código: `maestros/views.py` ya muestra con
  `messages.error` el rechazo de un servicio.
- **Tope de 30 MB y JPEG del prototipo** (`handlePhoto` recorta en un lienzo del navegador): en el sistema el tope es de 5 MB (SEG-19), se avisa al elegir el archivo y el servidor vuelve a
  codificarlo en WebP.
- **Sin JavaScript**: el prototipo no tiene servidor; el formulario de la foto trae un botón «Guardar foto» dentro de `<noscript>`.
- **«Quitar foto» en la ficha de otra cuenta**: el prototipo no lo tiene; lo piden USR-MOD-USR (regla 8 y postcondición e) y se hizo con la ventana de confirmación de las otras acciones (D-28).
- **Campo del logo** (`INIT.config`): `accept="image/*"` y «Todavía no está definido el formato ni el tamaño permitido» pasan a JPG/PNG/WebP, el tope y lo que hace el sistema; se suman la miniatura
  del logo actual y la casilla «Quitar el logo», que solo se muestra si ya hay un logo (D-106 punto 12).
- **Cuadro `.logo`**: la imagen va sobre fondo blanco con borde, no sobre el verde, para que un logo transparente o claro se lea; sin logo, el ícono de siempre.
- **La lista de cuentas no muestra la foto** (USR-CNS-USR regla 3 habla de «datos visibles de cada cuenta»; se cubrió en la ficha). Aprobado por el estudiante; la miniatura en la lista queda como posible
  mejora futura (`temas_abiertos`).
- **Editor de encuadre** (el prototipo **no tiene** pantalla de encuadre: `handlePhoto` recorta al centro en un lienzo apenas se elige el archivo): antes de guardar se abre la ventana «Encuadrá tu foto», con guía
  circular (el avatar), arrastrar, pellizcar, rueda, botones «+» y «−» y flechas, «Cancelar» y «Guardar foto». Los textos cambian: «Se recorta en forma cuadrada y se achica sola.» pasa a «Al elegirla, la encuadrás
  en el círculo.», y sin JavaScript se aclara que se recorta desde el centro. Lo pide el estudiante (27/11/2026). Los errores que detecta el navegador (más de 5 MB, no se puede abrir, menos de 64 px) van debajo
  de los botones, no como aviso breve; los del servidor, como aviso breve (D-29).

### Pruebas

Comando de la tarea (más los módulos que se suman: `test_usr_mod_usr`, `test_configuracion_vistas` y el recorrido), con la base `test_…` recreada por las migraciones nuevas:

```
python manage.py test core.tests.test_imagenes core.tests.test_usr_gst_prf core.tests.test_usr_mod_usr core.tests.test_identidad maestros.tests.test_adm_mod_org maestros.tests.test_identidad_organizacion maestros.tests.test_configuracion_vistas maestros.tests.test_recorrido_foto_y_logo --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion
```
Resultado: **322 pruebas, OK** (con el editor de encuadre). Además: concurrencia de `test_adm_mod_org` y `test_usr_mod_usr` (`--tag concurrencia`): 4, OK; `test_admin_django`, `test_seguridad_despliegue` y `test_correo`
(las que cargan `settings.py`): 15, OK; `test_usr_cns_usr`, `test_interfaz` y `test_usr_vnc_cta` (usan el marco): OK. La suite completa la corre el CI.

### Decisiones

Ninguna decisión nueva. Las precisiones de arriba se proponen como anexo a D-106 (ver la propuesta de cierre).

### Informe

**Verifiqué**
- Recorrido (`maestros/tests/test_recorrido_foto_y_logo.py`, 3 pruebas, OK): la foto de una cuenta de punta a punta (Vendedor: sin foto → archivo → cámara → encuadre elegido y encuadre inválido → archivo inválido → quita; Gerente: ficha → ventana → quita; sin
  auditoría), el alcance por rol (Gerente, Administrador, Agrónomo) y el logo (sin logo → carga con HTMX → encabezado y login → error por logo + quitar → logo inválido → cambio → quita → ícono; auditoría; otros roles sin acceso).
- Migraciones: `makemigrations --check --dry-run` → «No changes detected»; `sqlmigrate core 0053` y `sqlmigrate maestros 0014` → un `ALTER TABLE … ADD COLUMN … varchar(100) DEFAULT '' NOT NULL` y un `DROP DEFAULT`; no borra ni reescribe
  datos; aplicadas en la base de pruebas (recreada con `--noinput`).
- `manage.py check` en desarrollo.

**Lo cubre una prueba**
- Módulo de imágenes: `test_d106_archivo_de_mas_de_5_mb_se_rechaza_sin_abrirlo`, `…_un_archivo_que_no_es_imagen_se_rechaza_aunque_diga_jpg`, `…_un_gif_se_rechaza`, `…_un_svg_se_rechaza`,
  `…_la_orientacion_exif_queda_derecha`, `…_la_salida_es_webp_sin_metadatos`, `…_el_limite_propio_de_40_millones_de_pixeles`, `…_un_jpeg_se_decodifica_reducido_con_draft`.
- Editor de encuadre: `RecorteElegidoTests` (cuatro cuadrantes de colores, central sin coordenadas, cada código de error, mínimo de 64 px, imagen chica sin agrandar, EXIF rotado en JPEG y PNG, `draft` con escalado explícito, sin metadatos, 40 millones desde la cabecera), `UsrGstPrfFotoRecorteServicioTests` y `UsrGstPrfFotoRecorteVistaTests`.
- Almacenamiento: `AlmacenamientoTests` (cada rama de `STORAGES`, el `ImproperlyConfigured` con el nombre de cada variable y la URL firmada de 3600 s, sin red).
- Foto: `UsrGstPrfFotoServicioTests` / `UsrGstPrfFotoVistaTests`; la quita por quien gestiona: `UsrModUsrQuitarFotoServicioTests` / `UsrModUsrQuitarFotoVistaTests`.
- Logo: `AdmModOrgLogoServicioTests` (512 × 205, 300 × 100, transparencia, `logos/<uuid4>.webp`, regla 7 en los dos sentidos, `logo_y_quitar`, auditoría, archivos al deshacer) y `ConfiguracionLogoVistasTests`.
- Marco: `LogoDeLaIdentidadTests`, `LogoEnElMarcoTests` (incluye `Identidad("Nombre", "#336699")` con dos valores).

**No pude verificar**
- **R2 real**: las pruebas usan memoria; de R2 solo se prueba, sin red, la forma de la URL firmada. Paso 24.
- **El JavaScript** (`encuadre_foto.js`, solo revisado de sintaxis con `node --check`): abrir el editor al elegir el archivo, arrastrar, pellizcar, rueda, «+» y «−», flechas, Cancelar y Esc, el aviso de más de 5 MB y el reinicio del «Subiendo…»
  al volver con «Atrás». Pasos 2, 6 y 32 a 41.
- **Que el navegador dé las coordenadas sobre la imagen ya girada** (riesgo principal del editor) y que la foto guardada coincida con la guía circular. Pasos 35 y 37.
- **El pellizco con dos dedos** y la ventana en un celular real. Pasos 39 a 41.
- **La cámara del celular** (`capture="user"`) y el botón «Tomar foto» solo en pantallas táctiles (D-24). Paso 30.
- **El aspecto**: el avatar redondo, la miniatura y el cuadro blanco del logo de 32 px. Pasos 2, 15 y 16.
- **El CSRF y el `Origin` de un navegador real** con formularios que llevan archivo. Paso 26.
- **El foco con el teclado** en «Elegir foto» y «Tomar foto» (son etiquetas de un campo que se oculta con la clase `.sr`, como en el prototipo): puede no verse el foco. Paso 28.
- **Render**: que las migraciones se apliquen y que arranque con las variables de R2; el vencimiento de la URL a la hora. Pasos 29 a 31.
- **La suite completa** (la corre el CI). Localmente `tblib` no está instalado en el `.venv`: con `--parallel`, un fallo no muestra su traza (está en `requirements.txt`).
