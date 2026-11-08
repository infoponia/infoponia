# Casos de uso del bloque Cuentas y seguridad

Copia para el repo de las secciones «Casos de uso de alto nivel» y «Especificación complementaria ·
Seguridad y acceso» del documento de Drive «CU extendidos» (versión del 08/11/2026). Si este archivo
y el documento de Drive no coinciden, avisá: no elijas en silencio.

Estos casos de uso son de alto nivel (breves): reemplazan a CU-12 y CU-25 a CU-28 de la
Documentación para la IA y especifican el caso 23 de pendientes_CU. Las decisiones que los
acompañan están en `docs/decisiones.md` (D-01 a D-24). Los ítems MD-nn y DER-nn que se citan
están en los documentos de Drive pendientes_MD y pendientes_DER, y no hace falta leerlos.

Para nombrar las pruebas: en este archivo las reglas de cada caso de uso están numeradas, así que
se usa `test_regla_<numero>_<que_espera>` (por ejemplo, `test_regla_8_email_de_cuenta_inactiva_no_crea_otra`)
y, para los requisitos de seguridad, `test_seg_<numero>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| USR-INI-SES | Iniciar Sesión | Todos los roles y el Administrador | `core/tests/test_usr_ini_ses.py` |
| USR-CMB-CTR | Cambiar Contraseña | Todos los roles y el Administrador | `core/tests/test_usr_cmb_ctr.py` |
| USR-RCP-CTR | Recuperar Contraseña | Todos los roles y el Administrador | `core/tests/test_usr_rcp_ctr.py` |
| USR-ALT-USR | Alta Usuario | Gerente y Administrador | `core/tests/test_usr_alt_usr.py` |
| USR-MOD-USR | Modificar Usuario | Gerente y Administrador | `core/tests/test_usr_mod_usr.py` |
| USR-BAJ-USR | Baja Usuario | Gerente y Administrador | `core/tests/test_usr_baj_usr.py` |
| USR-CNS-USR | Consultar Usuario | Gerente y Administrador | `core/tests/test_usr_cns_usr.py` |
| USR-GST-PRF | Gestionar Mi Perfil | Todos los roles y el Administrador | `core/tests/test_usr_gst_prf.py` |
| USR-VNC-CTA | Vincular y Desvincular Cuenta | Todos los roles, no el Administrador | `core/tests/test_usr_vnc_cta.py` |

«Todos los roles» son Gerente, Agrónomo, Capataz, Vendedor, Transportista y Técnico.

## Lo que queda para más adelante

Algunas partes dependen de tablas que todavía no existen. Siguen la regla de D-04: se agregan
cuando se programe la tabla destino, y hasta entonces no se exigen.

- **Invernadero del Transportista (R155):** precondición d, postcondición b y reglas 5 y 7 de
  USR-ALT-USR; postcondición a de USR-MOD-USR; regla 3 de USR-CNS-USR; regla 1 de USR-GST-PRF.
  Mientras no exista Invernadero, el Transportista se da de alta sin invernadero.
- **Pendientes del Gerente:** postcondición d de USR-ALT-USR (aviso de resumen al nuevo Gerente) y
  postcondición c de USR-BAJ-USR (cantidad de pendientes al dar de baja al Gerente). Hoy no hay nada
  que pueda quedar pendiente.
- **Efectos de la baja sobre lo asignado:** postcondiciones e, f y g y regla 4 de USR-BAJ-USR
  (alertas por invernadero, pedidos y entregas).
- **Recuperar Contraseña por correo:** necesita un proveedor de correo, que todavía no está decidido.
  En desarrollo se usa el backend de consola de Django.
- **Ingreso con Google:** trabajo futuro; no se implementa en este bloque.

---

## USR-INI-SES · Iniciar Sesión

**Objetivo:** que la persona se identifique ante el Sistema para operar con una de sus cuentas, con
los permisos de esa cuenta: los de su rol o, si es de Administrador, los de la administración de
cuentas.

**Relaciones:** es extendido por USR-CMB-CTR cuando la cuenta tiene contraseña temporal; el punto de
extensión es inmediatamente después de la identificación.

**Precondición:**
a. Existe una cuenta activa con el email que indica la persona.

**Postcondición:**
a. La persona quedó identificada en el Sistema con esa cuenta y opera con los permisos que le
corresponden.
b. Si la cuenta tenía contraseña temporal, la persona la reemplazó por una nueva (USR-CMB-CTR).

**Reglas:**
1. La persona se identifica con el email de la cuenta, que es único, y su contraseña (SEG-01).
2. Solo se identifican las cuentas activas.
3. Si la identificación falla, el Sistema no revela si la cuenta existe, si está inactiva ni qué dato
   falló (SEG-06).
4. Con contraseña temporal, la persona no puede operar hasta reemplazarla. Una contraseña temporal
   vencida no sirve para identificarse (SEG-04).
5. Se opera con la cuenta indicada, aunque tenga cuentas vinculadas.
6. La identificación no se audita (SEG-14).

**Requisitos de seguridad:** SEG-01 a SEG-07.

## USR-CMB-CTR · Cambiar Contraseña

**Objetivo:** que la persona reemplace la contraseña de su propia cuenta por una nueva que solo ella
conoce.

**Relaciones:** extiende a USR-INI-SES cuando la cuenta tiene contraseña temporal. También se ejecuta
por sí mismo, desde USR-GST-PRF.

**Precondición:**
a. La persona está identificada en el Sistema con la cuenta cuya contraseña cambia.

**Postcondición:**
a. La contraseña de la cuenta se reemplazó por la nueva.
b. Si la contraseña era temporal, dejó de serlo.
c. Se cerraron las demás sesiones abiertas con esa cuenta; la sesión actual sigue.
d. Se creó un registro de auditoría con usuario, rol, fecha, hora, identificador de la cuenta y el
cambio de contraseña, sin registrar ninguna contraseña.

**Reglas:**
1. El Sistema pide la contraseña actual, salvo cuando este caso extiende a USR-INI-SES.
2. La contraseña nueva cumple la política de contraseñas y es distinta de la actual (SEG-03).
3. Cada persona cambia solo la contraseña de su propia cuenta. Quien gestiona una cuenta ajena no
   elige su contraseña: solo puede restablecerla (USR-MOD-USR).
4. Las cuentas vinculadas se mantienen.

## USR-RCP-CTR · Recuperar Contraseña

**Objetivo:** que quien olvidó su contraseña demuestre que controla el correo de su cuenta y elija
una nueva.

**Precondición:**
a. El envío de correo está configurado en el Sistema.
b. Existe una cuenta activa con el email que indica la persona.

**Postcondición:**
a. La contraseña de la cuenta se reemplazó por la que eligió su dueño.
b. Si la contraseña era temporal, dejó de serlo.
c. Se cerraron las sesiones abiertas con esa cuenta.
d. Se creó un registro de auditoría con fecha, hora, identificador de la cuenta afectada y el cambio
de contraseña; el usuario y el rol registrados son los de la cuenta afectada.

**Reglas:**
1. La persona demuestra que controla el correo con un enlace de un solo uso, que vence (SEG-12).
2. La respuesta del Sistema es la misma exista o no la cuenta, y no se envía nada a cuentas
   inactivas (SEG-12).
3. No se genera contraseña temporal y se mantienen las cuentas vinculadas.
4. La contraseña nueva cumple la política de contraseñas (SEG-03).
5. Si el envío de correo no está configurado, este caso de uso no está disponible: la persona le pide
   a quien gestiona su cuenta que la restablezca (USR-MOD-USR).

## USR-ALT-USR · Alta Usuario

**Objetivo:** registrar una nueva cuenta de usuario con un rol y los datos personales de la persona,
para que pueda operar en el Sistema.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Gerente o de Administrador.
b. No existe otra cuenta con el mismo email.
c. Si el rol es Gerente, no hay un Gerente activo.
d. Si el rol es Transportista, existe al menos un invernadero activo. *(Para más adelante.)*

**Postcondición:**
a. Se creó una cuenta en estado «activo», con el rol indicado, nombre, apellido, email, teléfono si
se indicó, y una contraseña temporal generada por el Sistema.
b. Si el rol es Transportista, la cuenta quedó asociada a su invernadero (R155). *(Para más adelante.)*
c. El Sistema le informó la contraseña temporal a quien hizo el alta, una única vez.
d. Si el rol es Gerente, se le envió al nuevo Gerente una única notificación dentro del Sistema con la
cantidad de pendientes que esperan una resolución del Gerente. *(Para más adelante.)*
e. Se creó un registro de auditoría con usuario, rol, fecha, hora e identificador de la nueva cuenta.

**Reglas:**
1. Alcance: el Gerente da de alta cuentas de Agrónomo, Capataz, Vendedor, Transportista y Técnico;
   el Administrador da de alta solo la cuenta del Gerente; nadie da de alta Administradores desde el
   Sistema, porque se crean en la puesta en marcha (SEG-17).
2. Hay un solo Gerente activo a la vez (D-09).
3. El email es único entre todas las cuentas (SEG-01).
4. La contraseña inicial la genera el Sistema, es temporal y vence a los 7 días si no se cambia;
   quien da de alta no la elige (SEG-04).
5. Los invernaderos del Agrónomo, el Vendedor, el Técnico y el Capataz se asignan desde el
   invernadero, y el vehículo del Transportista desde el vehículo; en el alta solo se indica el
   invernadero del Transportista. *(Para más adelante.)*
6. El rol no se modifica después del alta (D-11).
7. Son obligatorios el nombre, el apellido, el email y el rol; el teléfono es opcional; el invernadero
   es obligatorio solo para el Transportista *(para más adelante)*.
8. Si el email pertenece a una cuenta inactiva, no se da de alta otra cuenta: se reactiva esa
   (USR-MOD-USR) y se conserva su historial. Si la persona necesita otro rol, se le da de alta una
   cuenta nueva con otro email o con un alias.
9. El teléfono, si se indica, contiene solo dígitos, espacios y los símbolos + - ( ), con el + solo
   al comienzo, y tiene entre 8 y 15 dígitos (D-21).

## USR-MOD-USR · Modificar Usuario

**Objetivo:** actualizar los datos personales de una cuenta, restablecer su contraseña, reactivarla o
quitar su foto de perfil.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Gerente o de Administrador.
b. La cuenta a modificar está dentro de su alcance.
c. Si cambia el email, no existe otra cuenta con el email nuevo.

**Postcondición**, según lo que haya hecho el actor:
a. Se actualizaron los datos personales indicados: nombre, apellido, email, teléfono y, si es
Transportista, su invernadero *(para más adelante)*.
b. Si restableció la contraseña, la cuenta tiene una nueva contraseña temporal generada por el
Sistema, que se le informó una única vez a quien la restableció; se cerraron las sesiones abiertas
con esa cuenta, y la cuenta salió de su grupo de cuentas vinculadas.
c. Si reactivó la cuenta, quedó en estado «activo» y su contraseña se restableció como en «b».
d. Se creó un registro de auditoría con usuario, rol, fecha, hora, identificador de la cuenta y los
cambios, sin registrar ninguna contraseña. La quita de la foto no se audita.
e. Si quitó la foto, la cuenta quedó sin foto de perfil.

**Reglas:**
1. Alcance: el Gerente modifica las cuentas de Agrónomo, Capataz, Vendedor, Transportista y Técnico,
   y no la suya ni la de ningún Administrador; el Administrador modifica la cuenta del Gerente y las
   de los Administradores, incluida la suya (D-16).
2. El rol no se modifica (D-11).
3. El email se puede cambiar, siempre que siga siendo único; cambiarlo no afecta las cuentas
   vinculadas.
4. Nadie elige la contraseña de otra persona: solo se restablece. La nueva contraseña temporal vence a
   los 7 días si no se cambia. Para su propia cuenta, el Administrador usa USR-CMB-CTR (SEG-04 y
   SEG-11).
5. Solo se reactiva un Gerente si no hay otro Gerente activo (D-09).
6. Toda reactivación restablece la contraseña.
7. Quien gestiona la cuenta ve sus cuentas vinculadas en solo lectura, pero no las cambia.
8. Quien gestiona la cuenta puede quitar su foto de perfil, pero no cambiarla.
9. El teléfono cumple la regla 9 de USR-ALT-USR.

## USR-BAJ-USR · Baja Usuario

**Objetivo:** dar de baja lógica una cuenta, impidiendo su acceso sin perder la trazabilidad de lo
que hizo.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Gerente o de Administrador.
b. La cuenta está activa y dentro de su alcance.
c. Si la cuenta es de un Administrador, queda al menos otro Administrador activo.

**Postcondición:**
a. La cuenta quedó en estado «inactivo» (baja lógica).
b. Se cerraron las sesiones abiertas con esa cuenta.
c. Si la cuenta era del Gerente, el Sistema le informó al Administrador, en la pantalla de la baja,
cuántos pendientes quedan esperando hasta el alta de otro Gerente. *(Para más adelante.)*
d. Se creó un registro de auditoría con usuario, rol, fecha, hora, identificador de la cuenta y el
cambio de estado.
e. Si la cuenta tenía invernaderos a cargo, quedó para el Gerente una alerta «invernadero sin {rol}
activo» por cada uno. *(Para más adelante.)*
f. Si la cuenta era de un Agrónomo, se cancelaron sus pedidos sin orden de compra generada y se avisó
a los proveedores invitados. *(Para más adelante.)*
g. Si la cuenta era de un Transportista, sus entregas a realizar quedaron sin transportista.
*(Para más adelante.)*

**Reglas:**
1. Alcance: el mismo que en USR-MOD-USR. El Administrador puede darse de baja a sí mismo si no es el
   último Administrador activo.
2. La baja no afecta a las cuentas vinculadas: la cuenta sigue en su grupo, pero nadie puede pasar a
   ella mientras esté inactiva.
3. La baja del Gerente no se bloquea por los pendientes que tenga. Sin Gerente activo, sus pendientes
   esperan: ninguno tiene plazo (D-14).
4. La baja no se bloquea por lo que la cuenta tiene asignado. Antes de confirmar, el Sistema informa
   cuántos invernaderos, órdenes a realizar, contratos vigentes o abiertos, entregas a realizar y
   pedidos sin orden de compra tiene la cuenta, y qué pasará con cada uno. Lo asignado en un
   invernadero pasa a quien el Gerente asigne al modificar el invernadero; los pedidos sin orden de
   compra se cancelan; las entregas se reasignan según las reglas 10 a 12 de 8.12 del modelo de
   dominio. *(Para más adelante.)*

## USR-CNS-USR · Consultar Usuario

**Objetivo:** consultar las cuentas de usuario, buscar una en particular y ver sus datos.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Gerente o de Administrador.

**Postcondición:**
a. No se producen cambios en el Sistema.

**Reglas:**
1. Alcance: el Gerente consulta las cuentas de Agrónomo, Capataz, Vendedor, Transportista y Técnico;
   el Administrador, las del Gerente y de los Administradores (D-16).
2. Se filtra por rol y por estado, y se busca por nombre, apellido o email.
3. Datos visibles de cada cuenta: nombre, apellido, email, teléfono, rol, estado, foto de perfil si
   tiene, si tiene una contraseña temporal sin cambiar y si venció, el invernadero si es
   Transportista *(para más adelante)*, y sus cuentas vinculadas en solo lectura. Nunca se muestra
   una contraseña.
4. La consulta no se audita (SEG-14).

## USR-GST-PRF · Gestionar Mi Perfil

**Objetivo:** que la persona consulte los datos de la cuenta con la que opera y sus cuentas
vinculadas, y cargue, cambie o quite su foto de perfil.

**Precondición:**
a. La persona está identificada en el Sistema con una de sus cuentas.

**Postcondición:**
a. Si cargó, cambió o quitó su foto, la cuenta quedó con la foto nueva o sin foto. En otro caso, no
se producen cambios en el Sistema.

**Reglas:**
1. Datos visibles: nombre, apellido, email, teléfono, rol, estado y foto de perfil de la cuenta con la
   que opera; el invernadero, si es Transportista *(para más adelante)*; y sus cuentas vinculadas
   (las cuentas de Administrador no tienen vínculos). Nunca se muestra la contraseña.
2. La persona no modifica sus datos personales desde el perfil: para corregirlos recurre a quien
   gestiona su cuenta (USR-MOD-USR). El Administrador sí modifica los suyos, porque gestiona su propia
   cuenta.
3. Desde el perfil, la persona puede cambiar su contraseña (USR-CMB-CTR) y vincular o desvincular
   cuentas (USR-VNC-CTA).
4. Ni la consulta ni el cambio de foto se auditan (SEG-14).
5. La foto se carga desde un archivo o desde la cámara del dispositivo. Es por cuenta: no se comparte
   con las cuentas vinculadas (SEG-19).

## USR-VNC-CTA · Vincular y Desvincular Cuenta

**Objetivo:** que una persona con varias cuentas las agrupe para pasar de una a otra sin volver a
identificarse, o que saque una cuenta de ese grupo.

**Precondición:**
a. La persona está identificada en el Sistema con una de sus cuentas.
b. Para vincular: existe otra cuenta activa, sin contraseña temporal, cuyo email y contraseña conoce
la persona.
c. Para desvincular: la cuenta que se desvincula pertenece al mismo grupo que la cuenta con la que
opera la persona.

**Postcondición:**
a. Si vinculó, las dos cuentas quedaron en un mismo grupo: si ninguna tenía grupo, se creó uno con las
dos; si solo una tenía grupo, la otra se sumó a ese grupo; si cada una tenía su propio grupo, los dos
grupos se unieron en uno solo. Desde cualquier cuenta del grupo se puede pasar a las demás cuentas
activas (SEG-09).
b. Si desvinculó, la cuenta salió de su grupo; si el grupo quedó con una sola cuenta, el grupo dejó de
existir.
c. Se creó un registro de auditoría con usuario, rol, fecha, hora y el identificador de cada cuenta
afectada, indicando si se vinculó o se desvinculó.

**Reglas:**
1. La persona demuestra que la otra cuenta es suya indicando su email y su contraseña.
2. El vínculo es transitivo: las cuentas vinculadas forman un grupo (D-17).
3. Si al vincular cada cuenta ya pertenece a un grupo distinto, los dos grupos se unen en uno solo.
   Si las dos cuentas ya están en el mismo grupo, no hay nada que vincular.
4. No se vincula una cuenta con contraseña temporal, ni una cuenta inactiva, ni una cuenta consigo
   misma.
5. Las cuentas de Administrador no se vinculan.
6. Solo el dueño vincula y desvincula; quien gestiona la cuenta ve sus vínculos en solo lectura. Los
   vínculos se anulan además al restablecer la contraseña o al reactivar la cuenta (SEG-11).
7. Si el email o la contraseña de la otra cuenta son incorrectos, el Sistema usa el mismo mensaje
   genérico que al identificarse (SEG-06). Cuando la cuenta indicada es la misma con la que opera, o
   ya pertenece a su grupo, el Sistema lo dice, porque no revela nada de una cuenta ajena.
8. La persona puede desvincular cualquier cuenta de su grupo, incluso una inactiva, y no solo la
   cuenta con la que está operando.

---

## Especificación complementaria · Seguridad y acceso

Requisitos técnicos que citan los casos de uso. No son pasos de un actor.

- **SEG-01 · Identificador.** La cuenta se identifica con su email, que es único entre todas las
  cuentas. El Sistema lo guarda en minúsculas y lo compara sin distinguir mayúsculas.
- **SEG-02 · Almacenamiento de contraseñas.** Las contraseñas se guardan solo como resumen
  criptográfico con sal, con el algoritmo por defecto de Django. Nunca se muestran, ni se registran en
  la auditoría ni en los registros de errores.
- **SEG-03 · Política de contraseñas.** Una contraseña nueva tiene al menos 8 caracteres; no es de uso
  común (lista de contraseñas comunes de Django); no es solo numérica; no se parece al nombre, al
  apellido ni al email de la cuenta, y es distinta de la actual. Se controla con los validadores de
  contraseñas de Django.
- **SEG-04 · Contraseña temporal.** El Sistema la genera al dar de alta, restablecer o reactivar una
  cuenta. Tiene 12 caracteres aleatorios, letras y dígitos sin caracteres ambiguos (0, O, 1, l, I).
  Se muestra una sola vez a quien gestiona la cuenta. Mientras la cuenta la tenga, la persona solo
  puede reemplazarla por una propia; el resto de las pantallas está bloqueado. Vence a los 7 días de
  generada: una contraseña temporal vencida no sirve para identificarse, y quien gestiona la cuenta
  tiene que restablecerla. El Sistema guarda la fecha y hora de generación.
- **SEG-05 · Intentos de identificación.** No hay límite de intentos ni bloqueo de la cuenta por
  intentos fallidos.
- **SEG-06 · Mensaje genérico.** Ante una identificación fallida, el Sistema muestra el mismo mensaje
  sea cual sea la causa: email inexistente, contraseña incorrecta, cuenta inactiva o contraseña
  temporal vencida.
- **SEG-07 · Duración de la sesión.** La sesión dura mientras el navegador esté abierto; al cerrarlo,
  hay que volver a identificarse. No existe la opción de mantener la sesión iniciada.
- **SEG-08 · Cerrar sesión.** La persona puede cerrar su sesión en cualquier momento. El Sistema la
  invalida en el servidor, no solo en el navegador.
- **SEG-09 · Cambiar de cuenta vinculada.** Desde el menú de cuenta, la persona pasa a otra cuenta
  activa de su grupo sin volver a identificarse. Antes de cambiar, el Sistema verifica que esa cuenta
  siga activa y en el grupo. La sesión pasa a la otra cuenta con un identificador de sesión nuevo, y
  la persona llega al inicio de esa cuenta, que indica con qué rol opera. El cambio no se audita.
- **SEG-10 · Efecto del cambio de la propia contraseña.** Se cierran las demás sesiones abiertas con
  esa cuenta y la actual sigue abierta.
- **SEG-11 · Efecto del restablecimiento y la reactivación.** Generan una contraseña temporal nueva,
  cierran todas las sesiones de la cuenta y la sacan de su grupo de cuentas vinculadas.
- **SEG-12 · Recuperación por correo.** Solo está disponible si el envío de correo está configurado
  (variables de entorno del servidor de correo definidas). El enlace es de un solo uso y vence a la
  hora. La respuesta al pedirlo es siempre la misma, exista o no la cuenta, y no se envía nada a
  cuentas inactivas. Si el envío falla estando configurado, la persona recibe la misma respuesta y la
  falla queda en los registros de errores. Al usar el enlace se cierran las sesiones abiertas de la
  cuenta.
- **SEG-13 · Acceso según el rol.** Cada pantalla y cada acción verifican el rol de la cuenta con la
  que se opera y, cuando corresponde, su ámbito por invernadero. Si no le corresponde, el Sistema
  rechaza el acceso (error 403) con un mensaje que lo explica.
- **SEG-14 · Qué se audita.** Se auditan el alta, la modificación, la baja, la reactivación y el
  restablecimiento de cuentas; el cambio y la recuperación de contraseña, y la vinculación y
  desvinculación de cuentas. No se auditan la identificación, el cierre de sesión, el cambio de cuenta
  vinculada, las consultas, ni la carga, el cambio o la quita de la foto de perfil. Ninguna contraseña
  queda en la auditoría (D-22).
- **SEG-15 · Invariantes de las cuentas.** Siempre hay al menos un Administrador activo y nunca hay
  más de un Gerente activo. El Sistema lo verifica bloqueando las filas involucradas durante la
  operación, para que dos operaciones simultáneas no lo rompan.
- **SEG-16 · Transporte seguro.** El Sistema solo funciona por HTTPS. Las cookies de sesión son
  seguras y no accesibles desde scripts, y el navegador recibe la indicación de usar siempre HTTPS
  (HSTS).
- **SEG-17 · Puesta en marcha.** Los Administradores se crean por consola, fuera de la aplicación, al
  poner en marcha el Sistema y cuando se necesite otro. No es un caso de uso.
- **SEG-18 · Pantallas propias.** La administración de cuentas se hace con pantallas propias de
  InfoPonia. El panel de administración de Django está deshabilitado en producción.
- **SEG-19 · Foto de perfil.** Acepta JPG, PNG o WebP. El servidor verifica que el archivo sea una
  imagen real y la vuelve a codificar; después la recorta en cuadrado y la achica a 256 px. Se guarda
  en almacenamiento de objetos, no en el disco del servidor (D-20).

**Trabajo futuro:** ingreso con Google, conectando la cuenta desde el perfil y sin crear cuentas
nuevas; rol activo dentro de una misma cuenta; recordatorios de pendientes sin resolver.

---

## Pantallas

Guía visual: `docs/prototipos/cuentas_y_seguridad.html`. Es un solo archivo; cada pantalla es una
función de JavaScript. Buscá la función y leé solo esa parte.

| Pantalla | Función en el prototipo | Casos de uso |
|---|---|---|
| Inicio de sesión | `vLogin` | USR-INI-SES |
| Recuperar contraseña: pedido, correo enviado, contraseña nueva y enlace no válido | `vRecover`, `vRecoverSent`, `vReset`, `vLinkBad` | USR-RCP-CTR |
| Cambio obligatorio de la contraseña temporal | `vForced` | USR-CMB-CTR |
| Inicio de cada cuenta | `vHome` | USR-INI-SES, SEG-09 |
| Marco: cabecera, menú lateral y notificaciones | `shell`, `notifPop` | — |
| Menú de cuenta y cambio de cuenta vinculada | `accountPop` | SEG-09 |
| Mi perfil (foto, contraseña y cuentas vinculadas) | `vPerfil`, `handlePhoto` | USR-GST-PRF, USR-CMB-CTR, USR-VNC-CTA |
| Usuarios del Gerente y Cuentas del Administrador | `vUsuarios` | USR-CNS-USR |
| Ficha de una cuenta y sus acciones | `vUsuario` | USR-CNS-USR, USR-MOD-USR, USR-BAJ-USR |
| Alta y contraseña temporal | `vAlta`, `vAltaOk`, `tempPanel` | USR-ALT-USR |
| Ventanas de confirmación y de contraseña temporal | `modalHtml` | USR-ALT-USR, USR-MOD-USR, USR-BAJ-USR |
| Lista de requisitos de la contraseña | `policyList` | SEG-03 |

### Elementos del prototipo que no van en el sistema

El prototipo es una maqueta: tiene elementos que existen solo para poder recorrerlo sin servidor. En
el sistema real **no se implementa ninguno de ellos**. Si una pantalla del sistema los muestra, es un
error.

| Dónde está en el prototipo | Qué es | Qué hace el sistema real |
|---|---|---|
| Inicio de sesión: recuadro «Solo prototipo — cuentas de prueba» (botones «Usar», lista de cuentas y la contraseña común) | Atajo para entrar con cuentas inventadas | Nada: solo el formulario de email y contraseña |
| Inicio de sesión: casilla «Simular: el correo no está configurado en el Sistema» | Interruptor para ver las dos variantes | Lo decide la configuración del servidor (SEG-12): si el correo está configurado, se ofrece «¿Olvidaste tu contraseña?»; si no, se muestra el aviso. Sin casilla |
| Recuperar contraseña: recuadro «Solo prototipo — enlace del correo» (botones «Enlace válido», «Ya usado» y «Vencido») | Simula abrir el enlace que llegaría por correo | El enlace llega por correo. El Sistema decide si es válido, ya usado o vencido y muestra la pantalla que corresponde |
| Mi perfil, al vincular una cuenta: recuadro «Solo prototipo» con cuentas y contraseña de ejemplo | Ayuda para probar el vínculo | Nada: solo los campos de email y contraseña |
| Datos de prueba (cuentas, nombres, contraseñas, la contraseña temporal vencida de ejemplo y los avisos de la campana) | Datos fijos en memoria (`seed`) | Los datos reales vienen de la base de datos. Las cuentas de prueba para desarrollo se cargan aparte (comando o fixture) y nunca en producción |
| La contraseña temporal que «se completa sola» en el inicio de sesión | Comodidad de la maqueta | Quien la recibe la escribe |
| Datos que se pierden al recargar (todo vive en memoria) | Limitación de la maqueta | Se guarda en la base de datos |

Lo que sí es parte del sistema y no hay que confundir con lo anterior: el botón «Copiar» de la
contraseña temporal, los avisos breves, los filtros y la búsqueda, y el aviso de que el correo no
está configurado.

Comportamientos de pantalla que ya están decididos:

- El inicio de sesión, la recuperación y el cambio obligatorio se ven fuera del marco del ERP.
- El error de identificación es una sola alerta que no dice qué dato falló.
- La lista de requisitos de la contraseña nueva se tilda mientras se escribe.
- La contraseña temporal se muestra en una ventana que bloquea el fondo hasta tocar «Entendido», con
  un botón «Copiar».
- Los avisos breves aparecen arriba a la izquierda y desaparecen solos a los 3,5 segundos.
- En celular, el menú de cuenta se abre como hoja inferior y Mi perfil tiene un botón «Volver» en la
  cabecera.
- Al editar una cuenta, el rol se ve bloqueado. Si el email del alta es de una cuenta inactiva, se
  ofrece reactivarla.
- El teléfono se valida al confirmar, no mientras se escribe.
- El Administrador solo ve «Cuentas», sin campana ni módulos del ERP.
- Los formularios van centrados en el espacio disponible.
- Los desplegables son propios y accesibles con teclado, no el `<select>` nativo (D-24).

## Pistas técnicas

Son orientaciones, no instrucciones: antes de usar cada una, verificá su comportamiento en la
documentación de Django 5.2.

- **SEG-07:** `SESSION_EXPIRE_AT_BROWSER_CLOSE`.
- **SEG-09:** volver a llamar a `login()` con la otra cuenta genera un identificador de sesión nuevo.
- **SEG-10:** `update_session_auth_hash()` mantiene la sesión actual después de cambiar la
  contraseña; las demás quedan inválidas porque cambió el resumen de la contraseña.
- **SEG-12:** las vistas de restablecimiento de contraseña de Django y `PASSWORD_RESET_TIMEOUT`.
- **SEG-15:** `select_for_update()` dentro de `transaction.atomic()`, como pide `CLAUDE.md`.
- **SEG-04:** el módulo `secrets` de Python para generar la contraseña temporal.
- **SEG-19:** Pillow para verificar y volver a codificar la imagen; el almacenamiento con la
  configuración `STORAGES` de Django.
