# Bitácora de decisiones — InfoPonia

Cada entrada registra qué había antes (lo escrito, lo planteado o la situación),
qué se decidió, quién lo decidió y por qué. Las entradas no se borran: si una decisión
cambia, se agrega una entrada nueva que la reemplaza y se indica en la anterior.

Formato:

```
## D-NN — Título
- Fecha:
- Decidió:
- Antes:
- Decisión:
- Por qué:
- Fuentes:
- Consecuencias:
- Estado: vigente / reemplazada por D-NN
```

---

## D-01 — Modelo de usuario propio con herencia multi-tabla

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: el proyecto usaba el usuario por defecto de Django (ya migrado en la base local y en Neon,
  sin datos reales). En el modelo de dominio, los seis roles (Gerente, Agrónomo, Capataz, Vendedor,
  Transportista, Técnico) no tienen clase padre común ni relación con el usuario que inicia sesión.
  La propuesta inicial del asesor era una clase base abstracta con los atributos comunes y cada rol
  en relación uno a uno con el usuario.
- Decisión: `Usuario` hereda de `AbstractUser` (`AUTH_USER_MODEL = "core.Usuario"`). Los seis roles
  heredan de `Usuario` con herencia multi-tabla. `Usuario` tiene un campo `rol` que indica de qué
  hijo es. Un usuario tiene un solo rol. Cliente y Proveedor quedan fuera porque entran por enlace temporal.
- Por qué: una persona no puede tener más de un rol, y la herencia lo garantiza por estructura;
  un uno a uno opcional permitiría dos roles por error. Los roles tienen asociaciones y comportamiento
  propio (por ejemplo, Baja Capataz resuelve la alerta "invernadero sin Capataz activo"), por eso
  cada uno necesita su tabla. La auditoría referencia al usuario, y la convención acordada es usar
  multi-tabla cuando otras clases referencian al padre. El campo `rol` evita consultar seis tablas
  para saber el rol de quien inició sesión. Cambiar el modelo de usuario con datos cargados es muy
  costoso, y hoy no hay datos.
- Fuentes: modelo de dominio, secciones Gerente y Transportista y sección 5 (R002 a R006);
  CU extendidos, reglas de negocio de la reserva de stock (extensión 5a).
- Consecuencias: el DER mostrará la jerarquía de usuarios en lugar de seis entidades independientes,
  lo que es un desvío respecto del diagrama. `createsuperuser` crearía un `Usuario` sin rol, así que
  se reemplaza por un comando propio `crear_gerente`. Hay que recrear la base local y reiniciar la de
  Neon antes de mergear la PR, porque Render ejecuta `migrate` en cada despliegue.
- Estado: vigente

## D-02 — Atributos comunes de los roles en Usuario

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: cada rol repite en el diagrama idX, nombreX, apellidoX, telefonoX, emailX y estadoX
  (por ejemplo, idGerente, nombreGerente). La propuesta inicial los ponía en una clase abstracta,
  lo que los duplicaba con los campos que ya trae el usuario de Django.
- Decisión: los atributos comunes viven en `Usuario`, con este mapeo:

  | Diagrama | Código |
  |---|---|
  | idX | `Usuario.id` (los hijos lo heredan) |
  | nombreX | `first_name` |
  | apellidoX | `last_name` |
  | emailX | `email` |
  | telefonoX | `telefono` (campo nuevo) |
  | estadoX (activo / inactivo) | `is_active` (True / False) |

  Las tablas de cada rol solo guardan sus asociaciones. Para estos campos heredados se usan los
  nombres de Django; en los modelos propios, nombres en español (D-05).
  Se mantienen en inglés (`first_name`, `last_name`, `email`, `is_active`) solo porque son nombres
  que ya trae Django: el admin, los formularios, el inicio de sesión y las migraciones de la app
  `auth` dependen de ellos, y renombrarlos exigiría reescribir esas piezas. Es la opción A de
  la discusión del 05/11/2026; la mezcla de idiomas es consciente y se acota a estos campos.
- Por qué: una sola fuente de verdad, sin datos duplicados que puedan desincronizarse. El admin,
  los formularios y el inicio de sesión de Django dependen de estos nombres. `is_active` en False ya
  impide iniciar sesión, que es lo que pide la baja lógica de usuario.
- Fuentes: modelo de dominio, sección de cada rol; Documentación para la IA, CU-27 (baja lógica que restringe el acceso).
- Consecuencias: el mapeo debe figurar en el DER y en el diccionario de datos.
- Estado: vigente

## D-03 — Inicio de sesión con email

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: Django usa por defecto un nombre de usuario. CU-25 y CU-26 solo exigen que no exista un
  usuario con todos sus atributos idénticos, lo que permitiría dos personas con el mismo email.
- Decisión: se inicia sesión con el email, que es único. No hay campo `username`.
- Por qué: el email ya es un dato del modelo (emailX) y es lo que el usuario recuerda. Ser único
  es necesario para usarlo como identificador y para recuperar la contraseña por correo.
- Fuentes: modelo de dominio, sección de cada rol; Documentación para la IA, CU-25 y CU-26.
- Consecuencias: hace falta un manager propio para crear usuarios sin nombre de usuario. Hay que
  ajustar la precondición de unicidad al especificar Alta Usuario y Modificar Usuario.
- Estado: vigente

## D-04 — Asociaciones de los roles se agregan cuando existen sus tablas destino

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: el modelo de dominio tiene asociaciones obligatorias de los roles hacia tablas que todavía
  no existen en el código: Gerente de «contacto» de cada rol (R002 a R006), Transportista con su
  Vehículo (R073) y su Invernadero (R155), entre otras.
- Decisión: la primera PR crea `Usuario` y los seis roles sin asociaciones. Cada asociación se
  agrega en su propia migración cuando se programe la tabla destino.
- Por qué: no se puede crear una clave foránea hacia una tabla inexistente. Como no hay datos,
  agregar después un campo obligatorio no requiere valores por defecto ni migración de datos.
- Fuentes: modelo de dominio, sección 5 y sección Transportista.
- Consecuencias: hasta que se agreguen, el sistema no exige esas asociaciones. Hay que agregarlas
  antes de cargar datos reales.
- Estado: vigente

## D-05 — Nombres de campos en snake_case conservando el sufijo

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: el modelo de dominio usa camelCase con sufijo de la clase y conserva errores de tipeo del
  diagrama (nombreInverdadero, cantplantinesSiembra, MontoConsumo). No define tipos de datos.
- Decisión: snake_case conservando el sufijo (`nombre_invernadero`, no `nombre`). Los errores de
  tipeo se corrigen y cada corrección se registra en esta bitácora. El tipo de cada campo se decide
  al programar y se registra.
- Por qué: snake_case es la convención de Python. El sufijo mantiene la trazabilidad literal con el
  documento. Corregir los errores deja el código legible, y el registro conserva la trazabilidad.
- Fuentes: modelo de dominio (nombres de atributos).
- Consecuencias: excepción a esta regla, los campos heredados de Django (D-02).
- Estado: vigente

## D-06 — Clave primaria automática de Django

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: el diagrama nombra la clave de cada concepto (idGerente, idLote, etc.). Se planteó crear
  campos con esos nombres o usar el `id` de Django.
- Decisión: se usa el `id` automático de Django y se documenta que equivale al idX del diagrama.
- Por qué: es lo que Django espera; evita configuración extra en cada modelo y en cada relación.
- Fuentes: modelo de dominio (atributos idX).
- Consecuencias: el DER y el diccionario de datos indican la equivalencia.
- Estado: vigente

## D-07 — Versión vigente del modelo de dominio

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: el documento de traspaso de la puesta en marcha hablaba de 19 rondas de rediseño. CU
  extendidos ya cita cambios de la ronda 20 (por ejemplo, R039 en 0..1).
- Decisión: se programa a partir de la ronda 20. Sus cambios están aprobados aunque la ronda siga
  abierta porque falta reflejarlos en el diagrama.
- Por qué: es la versión más reciente y aprobada.
- Fuentes: modelo de dominio (copia sincronizada); CU extendidos, Registrar Recepción de Mercadería, reglas de negocio.
- Consecuencias: el diagrama puede no coincidir todavía con el texto. Manda el texto.
- Estado: vigente

## D-08 — Significado de la asociación «contacto» (R002 a R006)

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: el modelo de dominio indica que cada rol tiene exactamente un Gerente de «contacto»
  (R002 a R006), sin explicar su significado. Podía ser el Gerente que dio de alta al usuario o el
  que lo supervisa.
- Decisión: es el Gerente que supervisa en ese momento. Si se da de baja un Gerente y se da de alta
  otro, el nuevo pasa automáticamente a supervisar a los usuarios existentes.
- Por qué: refleja quién es responsable hoy, no quién creó al usuario (eso ya queda en la auditoría).
- Fuentes: modelo de dominio, sección 5 (R002 a R006); aclaración del usuario.
- Consecuencias: como hay un solo Gerente activo (D-09), la asociación se calcula en lugar de
  guardarse como clave foránea.
- Estado: vigente

## D-09 — Un solo Gerente activo; «contacto» se calcula

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: el modelo de dominio no limita la cantidad de Gerentes. R002 a R006 figuran como
  asociaciones con cardinalidad 1 hacia Gerente, lo que sugería una clave foránea en cada rol.
  El glosario, CMP-APR-ODC y COM-EVL-DSC suponían que podía haber varios Gerentes, pero esa
  suposición no tenía respaldo en una decisión registrada del proyecto.
- Decisión: solo puede haber un Gerente activo en el sistema. No se puede dar de alta otro mientras
  haya uno activo. La regla se garantiza en la base con una restricción de unicidad parcial
  (rol = gerente e is_active = True). R002 a R006 no se guardan: el Gerente de «contacto» de
  cualquier usuario es el Gerente activo.
- Por qué: es la regla del negocio indicada por el usuario. La restricción en la base la hace
  cumplir aunque haya errores en el código o dos altas simultáneas. Guardar la clave foránea
  obligaría a actualizar a todos los usuarios cada vez que cambia el Gerente.
- Fuentes: modelo de dominio, sección 5 (R002 a R006); aclaración del usuario.
- Consecuencias: desvío respecto del diagrama, que debe registrarse en pendientes_MD para una
  próxima ronda junto con la regla de un solo Gerente activo. El DER no mostrará R002 a R006.
  Corrige D-04 en lo que respecta a R002 a R006: no se agregarán como claves foráneas.
- Estado: vigente

## D-10 — Administrador técnico, limitado a gestionar al Gerente

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: el modelo de dominio tiene seis roles y ninguno puede crear al primer usuario cuando el
  sistema está vacío. El usuario había planteado en otra conversación un administrador o dueño que
  agregue al Gerente y también a usuarios de otros roles. Se evaluaron tres prácticas usuales:
  cuenta de administración creada al instalar, primer usuario como dueño y asistente de
  primera configuración.
- Decisión: existe un Administrador técnico, que es un `Usuario` con `is_superuser` en True y sin
  `rol`. Se crea al instalar con `createsuperuser`. Solo gestiona al Gerente (alta, baja y reemplazo)
  y no participa en ningún caso de uso de negocio. El Gerente da de alta los invernaderos y los demás
  usuarios desde las pantallas del sistema (CU-25 a CU-28). Regla en la base: un usuario no tiene
  `rol` solo si es superusuario.
- Por qué: continuidad, porque si se da de baja al único Gerente, sin el Administrador nadie podría
  dar de alta al siguiente. Separación de funciones, porque las operaciones de negocio y su auditoría
  quedan en los actores del dominio. Un solo camino para dar de alta los demás roles, en lugar de dos.
- Fuentes: modelo de dominio, sección de cada rol; Documentación para la IA, CU-25 a CU-28 y CU-64;
  aclaración del usuario.
- Consecuencias: el Administrador no es un rol del dominio y debe registrarse en pendientes_MD.
  Ya no hace falta el comando `crear_gerente`. Por ahora el Administrador opera desde el admin de
  Django, que muestra todos los modelos registrados: la limitación a gestionar al Gerente es por
  procedimiento hasta que exista una pantalla propia. El Gerente no entra al admin de Django
  (`is_staff` en False). Si más adelante hay pantalla propia, no será un caso de uso aparte: la
  pantalla de gestión de usuarios (caso por especificar 23 en pendientes_CU) sirve a los dos
  actores, y el Administrador solo ve a los Gerentes.
- Estado: reemplazada en parte por D-16 (alcance del Administrador, pantallas propias y admin de Django en producción); el resto sigue vigente

## D-11 — El rol de un usuario no se modifica

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: no estaba definido si un usuario podía cambiar de rol. Los casos de uso de gestión de
  usuarios (CU-25 a CU-28) no lo prohíben.
- Decisión: el `rol` se asigna al crear el usuario y no cambia nunca. Para cambiar de rol se da de
  baja al usuario y se crea otro con el rol que corresponde.
- Por qué: cada rol es una tabla hija con sus propias asociaciones (D-01); cambiar de rol obligaría a
  borrar una fila y crear otra bajo el mismo `id`. Con baja y alta se conserva el historial de lo
  que hizo cada usuario con su rol de entonces.
- Fuentes: aclaración del usuario; D-01.
- Consecuencias: el formulario de modificación no ofrece el campo rol, y el alta del Gerente no se
  ofrece como rol en el alta que hace el propio Gerente (D-09). Se prueba cuando se implemente la modificación de usuario (CU-26).
- Estado: vigente

## D-12 — Puede haber más de un Administrador

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: D-10 creaba al Administrador técnico sin fijar cuántos podía haber; en `estado.md` figuraba
  como supuesto provisional que podía haber más de uno.
- Decisión: puede haber más de un Administrador. No hay restricción de unicidad sobre los
  superusuarios.
- Por qué: es lo que indicó el usuario. Durante el desarrollo cada integrante necesita el suyo, y en
  producción evita depender de una sola cuenta.
- Fuentes: aclaración del usuario; D-10.
- Consecuencias: ninguna restricción nueva en la base. Deja de ser un tema abierto.
- Estado: vigente

## D-13 — El reemplazo del Gerente son dos operaciones

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: D-09 y D-10 hablaban de "reemplazar" al Gerente sin definir si era una operación o dos.
- Decisión: son dos operaciones separadas: el Administrador da de baja al Gerente actual y después da
  de alta al nuevo. Entre una y otra no hay Gerente activo, y el sistema debe seguir funcionando.
- Por qué: es el flujo indicado por el usuario, y encaja con la restricción de D-09, que solo limita
  a los Gerentes activos.
- Fuentes: aclaración del usuario; D-09; D-10.
- Consecuencias: no hay una operación atómica de reemplazo. Todo lo que notifica al Gerente tolera
  que no haya destinatario (D-14).
- Estado: vigente

## D-14 — Los pendientes del Gerente se definen por estado y rol, no por persona

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández
- Antes: el usuario preguntó qué pasa con las solicitudes de aprobación (por ejemplo, una orden de
  compra) cuando se va el Gerente o cuando no hay ninguno. CMP-APR-ODC ya establecía que la orden no
  se asigna a un Gerente: queda asociado el que la resuelve (R011).
- Decisión: lo que espera una resolución del Gerente no se asigna a una persona: queda en su estado y
  lo ve el Gerente activo. Sin Gerente activo queda esperando, generarlo no falla y la notificación
  sin destinatario se omite. Al dar de alta al Gerente se le envía un único aviso de resumen con la
  cantidad de pendientes. Si alguien genera algo que queda esperando al Gerente y no hay Gerente
  activo, se le avisa que quedará pendiente. Al dar de baja al Gerente se advierte cuántos pendientes
  hay, sin bloquear la baja.
- Por qué: calcular lo pendiente por estado evita copiar o reasignar avisos cada vez que cambia el
  Gerente, igual que «contacto» se calcula (D-09).
- Fuentes: CU extendidos, CMP-APR-ODC, regla "Orden resoluble" y Requisitos especiales (las
  notificaciones se envían fuera de la transacción); aclaración del usuario.
- Consecuencias: los servicios que notifican al Gerente no pueden fallar por falta de destinatario.
  Queda abierto el efecto de los plazos que corren mientras no hay Gerente (por ejemplo, la vigencia
  de las cotizaciones), a resolver en el caso de uso de baja del Gerente.
- Estado: vigente

## D-15 — Tipo del campo telefono

- Fecha: 05/11/2026
- Decidió: Lautaro Fernández (propuesto por Claude Code durante la Tarea 01, sin objeción)
- Antes: `telefono` (telefonoX, D-02) es un campo nuevo que no tiene tipo definido en el
  modelo de dominio.
- Decisión: `CharField(max_length=20, blank=True)`.
- Por qué: un teléfono se escribe, no se calcula ni se suma, así que no es numérico. 20
  caracteres alcanzan para un número local o uno con código de país y separadores
  (espacios o guiones). `blank=True` porque no todos los roles lo cargan desde el alta.
- Fuentes: D-02 (mapeo telefonoX → `telefono`); D-05 (registrar el tipo de cada campo nuevo).
- Consecuencias: ninguna por ahora; si en el futuro se necesita validar formato, se agrega un
  validador sin cambiar el tipo de columna.
- Estado: vigente; completada por D-21 (formato del teléfono); su largo de 20 caracteres fue reemplazado por D-28 (25)

## D-16 — Alcance del Administrador y pantallas propias

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández
- Antes: D-10 limitaba al Administrador a gestionar al Gerente, desde el admin de Django; una
  pantalla propia quedaba para más adelante y la limitación era solo por procedimiento.
- Decisión:
  - El Administrador da de alta solo la cuenta del Gerente. Modifica, restablece, reactiva y da de
    baja la cuenta del Gerente y las de los Administradores, incluida la suya, y consulta esas
    mismas cuentas.
  - Nadie da de alta Administradores desde el Sistema: se crean por consola con `createsuperuser`
    al poner en marcha el Sistema y cuando se necesite otro (SEG-17).
  - Siempre queda al menos un Administrador activo: un Administrador puede darse de baja si no es
    el último (SEG-15).
  - El Administrador corrige sus propios datos personales desde las pantallas de cuentas y cambia
    su contraseña como cualquier persona (USR-CMB-CTR).
  - Las cuentas de Administrador no se vinculan con otras (D-17).
  - La administración de cuentas se hace con pantallas propias de InfoPonia. El admin de Django
    queda deshabilitado en producción (SEG-18); en desarrollo puede seguir disponible.
- Por qué: el admin de Django muestra todos los modelos y no aplica el alcance ni las reglas de las
  cuentas (contraseña temporal, auditoría, invariantes). Con varios Administradores (D-12), tienen
  que poder gestionarse entre sí. Dejar el admin expuesto en producción agrega superficie de ataque.
- Fuentes: CU extendidos, «Casos de uso de alto nivel» (regla 1 de USR-ALT-USR, USR-MOD-USR,
  USR-BAJ-USR y USR-CNS-USR; regla 2 de USR-GST-PRF) y «Especificación complementaria · Seguridad y
  acceso» (SEG-15, SEG-17 y SEG-18); pendientes_MD, MD-58.
- Consecuencias: reemplaza en parte a D-10. El admin de Django se deshabilita en producción recién
  cuando existan las pantallas del Administrador (tarea 05 de `docs/estado.md`); antes, nadie podría
  gestionar al Gerente en producción.
- Estado: vigente

## D-17 — Cuentas vinculadas en un grupo

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández
- Antes: D-01 fija un solo rol por usuario. Una persona con dos funciones (por ejemplo, Agrónomo y
  Vendedor) necesitaba dos cuentas y volver a identificarse para pasar de una a otra.
- Decisión:
  - Una persona puede tener varias cuentas, cada una con su rol y su email. Como el email es único
    (D-03), para un segundo rol se usa otro email o un alias.
  - Las cuentas se agrupan en un grupo de cuentas vinculadas. Cada `Usuario` pertenece a lo sumo a
    un grupo (clave foránea opcional). El vínculo es transitivo: si al vincular cada cuenta está en
    un grupo distinto, los grupos se unen; un grupo que queda con una sola cuenta deja de existir.
  - Solo el dueño vincula y desvincula. Para vincular demuestra que la otra cuenta es suya con su
    email y su contraseña. No se vinculan cuentas inactivas, con contraseña temporal ni de
    Administrador.
  - Restablecer la contraseña de una cuenta o reactivarla la saca de su grupo.
  - Desde el menú de cuenta se pasa a otra cuenta activa del grupo sin volver a identificarse, con un
    identificador de sesión nuevo. El cambio de cuenta no se audita.
- Por qué: conserva D-01 y D-11 (un rol fijo por cuenta, con sus asociaciones y su historial) y evita
  que la persona se identifique varias veces. Un grupo, en lugar de pares de cuentas, hace que el
  vínculo sea transitivo por estructura.
- Fuentes: CU extendidos, USR-VNC-CTA, USR-MOD-USR (postcondición b), SEG-09 y SEG-11;
  pendientes_DER, DER-10; pendientes_MD, MD-58.
- Consecuencias: una tabla nueva y un campo nuevo en `Usuario`, en una migración nueva. Modificar
  `Usuario` requiere el permiso explícito que pide `CLAUDE.md`. El DER se actualiza después, a
  partir del código.
- Estado: vigente

## D-18 — Contraseña temporal

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández
- Antes: los casos preliminares CU-25 a CU-28 no decían quién elige la contraseña inicial ni cómo se
  recupera una cuenta cuya contraseña se olvidó si no hay correo.
- Decisión:
  - El Sistema genera una contraseña temporal al dar de alta, restablecer o reactivar una cuenta:
    12 caracteres aleatorios, letras y dígitos sin caracteres ambiguos (0, O, 1, l, I).
  - Se muestra una sola vez a quien gestiona la cuenta. Nadie elige la contraseña de otra persona.
  - Vence a los 7 días de generada. Vencida, no sirve para identificarse y quien gestiona la cuenta
    tiene que restablecerla.
  - Mientras la cuenta la tenga, la persona solo puede reemplazarla por una propia: el resto de las
    pantallas está bloqueado.
  - Se guarda la fecha y hora de generación; vacía si la contraseña no es temporal.
- Por qué: quien gestiona la cuenta nunca conoce la contraseña definitiva. El vencimiento limita el
  riesgo de una contraseña que se transmitió por otro medio.
- Fuentes: CU extendidos, SEG-04 y SEG-11, USR-ALT-USR (regla 4), USR-MOD-USR (regla 4) y
  USR-CMB-CTR; pendientes_DER, DER-10.
- Consecuencias: campo nuevo en `Usuario` (permiso explícito, como en D-17). La temporal vencida se
  rechaza con el mismo mensaje genérico que cualquier otra falla (D-19).
- Estado: vigente; reemplazada en parte por D-35 (su primer punto, que el Sistema genera una contraseña temporal al dar de alta, restablecer o reactivar, pasa a ser una de dos formas de primer acceso; el resto vale para la temporal)

## D-19 — Sesión e identificación

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández
- Antes: no estaba definido cuánto dura la sesión ni qué se informa cuando falla la identificación.
  El prototipo tenía la opción «mantener sesión iniciada».
- Decisión:
  - La sesión dura mientras el navegador esté abierto. No existe «mantener sesión iniciada».
  - Ante una identificación fallida se muestra un único mensaje genérico, sea cual sea la causa.
  - No hay límite de intentos ni bloqueo de la cuenta.
  - El email se guarda en minúsculas y se compara sin distinguir mayúsculas.
  - Cerrar sesión la invalida en el servidor.
- Por qué: el Capataz, el Técnico y el Transportista trabajan en celulares que pueden ser compartidos,
  y el ingreso con Google (trabajo futuro) hace innecesario recordar la sesión. El mensaje genérico no
  revela qué cuentas existen.
- Fuentes: CU extendidos, USR-INI-SES, SEG-01 y SEG-05 a SEG-08.
- Consecuencias: hoy el email es único distinguiendo mayúsculas (`unique=True`): hay que pasarlo a
  minúsculas al guardar y al identificarse.
- Estado: vigente

## D-20 — Foto de perfil en almacenamiento de objetos

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández
- Antes: el modelo de dominio no tiene foto de perfil.
- Decisión:
  - Cada cuenta puede tener una foto de perfil, que no se comparte con sus cuentas vinculadas.
  - Acepta JPG, PNG o WebP. El servidor verifica que sea una imagen real, la vuelve a codificar, la
    recorta en cuadrado y la achica a 256 px.
  - Se guarda con el almacenamiento de archivos de Django: en desarrollo, el disco local; en
    producción, un almacenamiento de objetos con `django-storages`.
  - La carga, el cambio y la quita no se auditan. Quien gestiona la cuenta puede quitarla, pero no
    cambiarla.
- Por qué: el disco del servidor de Render no es persistente (los archivos subidos se pierden en cada
  despliegue), y un disco persistente se paga aparte e impide los despliegues sin corte. Volver a
  codificar la imagen evita guardar contenido malicioso con apariencia de imagen.
- Fuentes: CU extendidos, SEG-19, USR-GST-PRF (regla 5) y USR-MOD-USR (regla 8); pendientes_DER,
  DER-10 (decisión del 08/11/2026).
- Consecuencias: dependencias nuevas, Pillow y, para producción, `django-storages` con la librería
  del proveedor. Falta decidir el proveedor de almacenamiento antes de la tarea de la foto. Campo
  nuevo en `Usuario` (permiso explícito, como en D-17).
- Estado: vigente

## D-21 — Formato del teléfono

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández
- Antes: D-15 fijó el tipo de `telefono` y dejó para más adelante validar el formato.
- Decisión: si se indica, el teléfono contiene solo dígitos, espacios y los símbolos + - ( ), con el
  + solo al comienzo, y tiene entre 8 y 15 dígitos. Se valida al confirmar el formulario, no mientras
  se escribe.
- Por qué: 15 dígitos es el máximo de un número internacional; 8 cubre un número local. Validar al
  confirmar evita marcar como error un número que todavía se está escribiendo.
- Fuentes: CU extendidos, USR-ALT-USR (regla 9); pendientes_DER, DER-10 (decisión del 08/11/2026);
  D-15.
- Consecuencias: completa a D-15. El validador del campo genera una migración que no cambia la
  columna.
- Estado: vigente

## D-22 — Registro de auditoría

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández (aprobada el 08/11/2026, a propuesta de Claude)
- Antes: varias postcondiciones de los casos de uso piden «un log de auditoría», y el modelo de
  dominio lo menciona en otros procesos, pero ni el modelo ni el DER tienen una entidad que lo guarde.
- Decisión: un modelo `RegistroAuditoria` en `core`, al que solo se agregan filas (nunca se modifican
  ni se borran), con: la cuenta que actuó, su rol en ese momento, fecha y hora, la acción (lista
  cerrada), el identificador de cada cuenta u objeto afectado y un detalle con los cambios. Nunca
  guarda contraseñas. Se escribe desde el servicio del caso de uso, dentro de la misma transacción.
- Por qué: en la misma transacción no puede quedar una operación sin su registro, ni un registro de
  una operación que se deshizo. Guardar el rol del momento conserva el dato aunque la cuenta cambie
  después. Un único modelo sirve a todos los módulos.
- Fuentes: CU extendidos, SEG-14 y las postcondiciones de auditoría de USR-CMB-CTR, USR-RCP-CTR,
  USR-ALT-USR, USR-MOD-USR, USR-BAJ-USR y USR-VNC-CTA; modelo de dominio (menciones del log de
  auditoría).
- Consecuencias: desvío respecto del DER, que no tiene la entidad: se agrega al actualizar el DER a
  partir del código. Los módulos de negocio la reutilizan.
- Estado: vigente; D-36 completa el formato obligatorio del detalle y de los afectados, y la consulta (AUD-CNS-REG)

## D-23 — Ubicación del código: cuentas en core, una app por módulo de negocio

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández (aprobada el 08/11/2026, a propuesta de Claude)
- Antes: todo el código está en la app `core`, que hoy solo tiene `Usuario` y los seis roles. El
  reparto de apps entre los dos integrantes era un tema abierto.
- Decisión:
  - Todo el bloque de cuentas y seguridad va en `core`: modelos, servicios (`core/servicios.py`),
    formularios, vistas, plantillas y pruebas.
  - `core` también guarda lo que comparten todos los módulos: la plantilla base, los estilos, el
    menú, el control de acceso por rol y la auditoría (D-22).
  - Cada módulo de negocio tendrá su propia app, que usa lo de `core`; `core` nunca depende de una
    app de negocio. Los nombres y el reparto de esas apps se deciden al empezar el primer módulo.
- Por qué: `Usuario` ya está en `core`, y mover un modelo de usuario con migraciones aplicadas es muy
  costoso. Todo el bloque gira alrededor de `Usuario`: separarlo en otra app solo agregaría
  dependencias cruzadas. Una app por módulo permite repartir el trabajo entre los dos integrantes con
  menos choques en los mismos archivos.
- Fuentes: `CLAUDE.md` (arquitectura); D-01.
- Consecuencias: resuelve en parte el tema abierto del reparto de apps.
- Estado: vigente

## D-24 — Pantallas del bloque a partir del prototipo HTML

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández (aprobada el 08/11/2026, a propuesta de Claude)
- Antes: el prototipo del ERP es un zip de React (`InfoPonia11.zip`) que no se traslada al repo. El
  bloque de cuentas se diseñó el 07 y el 08/11/2026 en un prototipo HTML aparte.
- Decisión:
  - Las pantallas del bloque se hacen con plantillas de Django y HTMX, tomando como guía visual
    `docs/prototipos/cuentas_y_seguridad.html`, que usa los colores, tipografías y clases del zip.
  - HTMX se incluye como archivo estático dentro del repo.
  - Los desplegables de filtros y formularios son propios y accesibles con teclado, no el `<select>`
    nativo: en Windows, la opción resaltada del nativo se veía en blanco y no se leía.
  - La carga de la foto desde el celular se prueba en un dispositivo real, con el sistema desplegado.
- Fuera del sistema: el prototipo tiene elementos que existen solo para poder probarlo (los
  recuadros «Solo prototipo», los datos de prueba y el interruptor que simula que el correo no está
  configurado). Nada de eso se implementa. La lista completa está en `docs/casos_de_uso/usuarios.md`,
  sección «Elementos del prototipo que no van en el sistema».
- Por qué: los dos problemas quedaron abiertos en el prototipo y no se pudieron resolver dentro de la
  app de Claude. Servir HTMX desde el repo evita depender de un servidor externo.
- Fuentes: `pendientes_prototipo.md`, pendiente 46; `historial_prototipo.md`, «Cuentas y seguridad».
- Consecuencias: el archivo de HTMX es una dependencia nueva y necesita permiso explícito en la
  tarea 02.
- Estado: vigente

## D-25 — Convenciones del bloque Cuentas y seguridad (tarea 02)

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández (aprobada durante la planificación de la tarea 02, a propuesta de Claude)
- Antes: `CLAUDE.md` pide una función de servicio por caso de uso y fija el formato de nombre de las
  pruebas para reglas, extensiones, postcondiciones, flujos y decisiones, pero no para los requisitos
  SEG ni para un caso de uso que no modifica datos. SEG-01 pedía guardar el email en minúsculas, lo que
  cambia `Usuario`. El prototipo muestra los módulos de todos los roles, una campana de notificaciones,
  el nombre «Jardín Botánico» y un pie «En línea · sincronizado».
- Decisión:
  - Iniciar sesión no tiene función en `servicios.py`: no modifica datos y sus reglas las aplican el
    backend `core.backends.BackendEmail` y `FormularioInicioSesion`, con el motivo escrito en un
    comentario. Las pruebas se escriben igual antes de implementar. La clase de pruebas de un caso de
    uso sin servicio se llama `<CodigoCu>ReglasTests`.
  - Las pruebas de un requisito SEG se llaman `test_seg<nn>_<que_espera>`, van en el archivo del caso
    de uso que lo cita y su docstring nombra el SEG. Un requisito transversal (SEG-13) va en el archivo
    del primer caso de uso que lo usa.
  - SEG-01 se divide. Tarea 02: el login compara el email sin distinguir mayúsculas, sin tocar
    `Usuario`; si el email coincide con más de una cuenta activa (posible mientras la unicidad distinga
    mayúsculas), no se identifica ninguna y se muestra el mensaje genérico (SEG-06). Tarea 03: guardar el
    email en minúsculas y la unicidad sin distinguir mayúsculas, con migración de los datos existentes.
  - Toda pantalla exige sesión por defecto (`LoginRequiredMiddleware`); las que no, se eximen con
    `@login_not_required`. El cierre de sesión está eximido (para poder cerrar una sesión vencida) y solo
    acepta POST.
  - El menú lateral muestra solo lo que existe; cada tarea agrega su entrada. El Administrador no tiene
    entradas hasta la tarea 05.
  - Capataz, Técnico y Transportista usan un marco angosto de celular, sin menú lateral. Su pie no dice
    «sincronizado»: el sistema no sincroniza.
  - La campana y las notificaciones quedan para cuando existan notificaciones. El menú de cuenta ofrece
    por ahora solo «Cerrar sesión»; «Cambiar de cuenta» y «Mi perfil» llegan en la tarea 06.
  - El nombre de la organización es la configuración `NOMBRE_ORGANIZACION`, leída de una variable de
    entorno, con «InfoPonia» por defecto. «Jardín Botánico» era un dato del prototipo.
- Por qué: un servicio que solo envolviera `authenticate` y `login` no agregaría nada. Un nombre fijo
  para las pruebas SEG mantiene la trazabilidad con el documento. Dividir SEG-01 evita cambiar el modelo
  de usuario en una tarea que no tiene ese permiso y deja el login ya correcto. Exigir sesión por
  defecto evita que una pantalla nueva quede abierta por olvido. Mostrar solo lo que existe no deja
  enlaces rotos.
- Fuentes: `docs/casos_de_uso/usuarios.md` (USR-INI-SES; SEG-01, SEG-05 a SEG-08 y SEG-13; «Pantallas» y
  «Elementos del prototipo que no van en el sistema»); D-03, D-19 y D-24; `CLAUDE.md` (tests y
  arquitectura).
- Consecuencias: la tarea 03 debe agregar la normalización a minúsculas y la unicidad sin distinguir
  mayúsculas. El ámbito por invernadero de SEG-13 queda pendiente en `core/acceso.py` hasta que exista
  `Invernadero`. `.env.example` y el entorno de Render ganan una variable opcional.
- Estado: vigente

## D-26 — Archivos de terceros incluidos en el repo

- Fecha: 08/11/2026
- Decidió: Lautaro Fernández (HTMX por D-24; fuentes autorizadas en la tarea 02)
- Antes: D-24 decide servir HTMX como archivo estático, pero no su versión ni dónde queda. El prototipo
  carga las fuentes Inter y DM Mono desde Google Fonts.
- Decisión: se incluyen en `core/static/core/`:
  - `vendor/htmx-2.0.11.min.js`: `htmx.org@2.0.11`, licencia Zero-Clause BSD.
  - `fuentes/`: Inter 400, 500, 600 y 700 (`@fontsource/inter@5.3.0`) y DM Mono 400 y 500
    (`@fontsource/dm-mono@5.3.0`), en formato woff2 y subconjunto *latin* (cubre á, ñ, ü, ¿, « » y —),
    licencia SIL Open Font License 1.1.
  - Cada paquete se bajó del registro de npm y se verificó que su `sha512` coincidiera con el
    `integrity` publicado antes de extraerlo. `vendor/LEEME.md` registra el origen, la versión, el
    `integrity` y el SHA-256 de cada archivo. Las licencias van junto a los archivos.
  - Las fuentes se sirven desde el repo, no desde Google Fonts.
- Por qué: servirlos desde el repo evita depender de un servidor externo y de que el navegador de
  quien usa el sistema alcance ese servidor (el mismo motivo de D-24). La OFL pide distribuir la
  licencia con las fuentes.
- Fuentes: D-24; `docs/prototipos/cuentas_y_seguridad.html` (carga de fuentes); registro de npm.
- Consecuencias: no son dependencias de Python ni hay `package.json`; actualizarlos es manual (cambiar
  la versión, repetir la verificación del `integrity` y actualizar `LEEME.md`). Los archivos minificados
  y las fuentes no pueden llevar el comentario inicial que pide `CLAUDE.md`: su propósito queda en
  `LEEME.md`.
- Estado: vigente

## D-27 — Contraseña temporal, auditoría y email: cómo se implementan (tarea 03)

- Fecha: 09/11/2026
- Decidió: Lautaro Fernández (aprobada durante la planificación de la tarea 03, a propuesta de Claude)
- Antes: D-18, D-19 y D-22 fijan qué se hace con la contraseña temporal, el email y el registro de
  auditoría, pero no cómo se implementan. D-25 dejó para esta tarea guardar el email en minúsculas y la
  unicidad sin distinguir mayúsculas.
- Decisión:
  - `RegistroAuditoria` (D-22) es de solo agregar: una fila guardada no se modifica ni se borra. Las
    cuentas u objetos afectados se guardan como una lista JSON. Un detalle con una clave que nombre una
    contraseña se rechaza. Una acción que hace el propio sistema, sin una persona detrás, se guarda sin
    usuario y con el rol «infoponia». `rol_de` y `ADMINISTRADOR` se mudan a `core/models.py` para que los
    modelos no importen `acceso.py`.
  - El cambio de contraseña y su registro de auditoría se guardan en una sola transacción: si falla uno,
    no se guarda ninguno.
  - Con contraseña temporal, solo se puede elegir una propia o cerrar sesión: un middleware bloquea toda
    vista que no tenga la marca `@permitido_con_contrasena_temporal`. A un pedido de HTMX se le responde
    con `HX-Redirect`.
  - La contraseña temporal vence a los 7 días exactos de generada. Una temporal que vence con la sesión
    ya abierta se puede reemplazar igual.
  - El email conserva `unique=True` en el campo, además de la unicidad sin distinguir mayúsculas.
  - El inicio de sesión ya no trata el email ambiguo previsto en D-25: con la unicidad sin distinguir
    mayúsculas no puede haber dos cuentas con el mismo email.
  - La lista de requisitos en vivo muestra solo lo que el navegador puede comprobar (longitud y que no
    sea solo números). Que la contraseña nueva sea distinta de la temporal se valida únicamente en el
    servidor, y el error aparece al guardar.
- Por qué: en la misma transacción que la operación, el registro no queda sin operación ni al revés
  (D-22). Un middleware con marca bloquea por defecto: una pantalla nueva queda bloqueada para estas
  cuentas sin que haya que acordarse (mismo patrón que `LoginRequiredMiddleware`). Django exige un campo
  único para el identificador de la cuenta y no cuenta una restricción con expresión, por eso se
  conservan las dos. El navegador no conoce la contraseña temporal.
- Fuentes: `docs/casos_de_uso/usuarios.md` (USR-INI-SES regla 4, USR-CMB-CTR, SEG-01 a SEG-04, SEG-10 y
  SEG-14); D-18, D-19, D-22 y D-25.
- Consecuencias: migraciones `0003` y `0004`. La `0004` falla, sin cambiar datos, si hay emails repetidos
  sin distinguir mayúsculas: hay que resolverlos a mano antes de migrar (también en Neon).
- Estado: vigente; reemplazada en parte por D-35 (la contraseña temporal ya no es la única forma de primer acceso: la cuenta también puede tener una invitación pendiente) y por D-36 (el formato del detalle de la auditoría)

## D-28 — Usuarios del Gerente: alcance, teléfono y pantallas (tarea 04)

- Fecha: 10/11/2026
- Decidió: Lautaro Fernández (aprobada durante la planificación de la tarea 04, a propuesta de Claude)
- Antes: `estado.md` incluía SEG-15 en la tarea 04. D-15 fijaba `telefono` en 20 caracteres como máximo y
  D-21 admite hasta 15 dígitos con espacios, guiones y paréntesis. `CLAUDE.md` pide un único queryset de
  alcance por modelo, pero no existía. No estaba definido qué ve el Gerente al chocar con una cuenta fuera
  de su alcance, cómo se buscan varias palabras, ni el formato de nombre de las pruebas de precondiciones.
- Decisión:
  - SEG-15 pasa a la tarea 05. Con solo el Gerente en juego, el Administrador activo y el Gerente único
    no se pueden romper desde estas pantallas.
  - `telefono` pasa a 25 caracteres como máximo (reemplaza el `max_length=20` de D-15). El validador de
    D-21 también rechaza más de 25 caracteres, con un único mensaje que nombra el límite. Migración `0005`.
  - El alcance por usuario vive en un solo lugar: `UsuarioQuerySet.en_alcance_de(actor)`. El Gerente
    gestiona las cuentas de Agrónomo, Capataz, Vendedor, Transportista y Técnico, y no la suya, ni otros
    Gerentes, ni Administradores. La rama del Administrador (D-16) se agrega en la tarea 05.
  - La ficha de una cuenta fuera del alcance da error 403 con mensaje (SEG-13); un id que no existe da 404.
  - En el alta, el email de una cuenta fuera del alcance da el mensaje genérico «Ya existe una cuenta con
    ese email.». Solo si la cuenta inactiva está dentro del alcance se ofrece reactivarla (regla 8).
  - La búsqueda de la lista exige que la cuenta coincida con todas las palabras, cada una en el nombre,
    el apellido o el email, sin distinguir mayúsculas.
  - Una modificación sin cambios no guarda ni audita; restablecer la contraseña solo vale para cuentas
    activas y reactivar solo para cuentas inactivas. Esto se implementó en la tarea 04b.
  - Se pueden modificar los datos de una cuenta inactiva: la cuenta sigue inactiva y la modificación se
    audita como cualquier otra. USR-MOD-USR no define esta regla (solo exige que la cuenta esté dentro del
    alcance, a diferencia de USR-BAJ-USR, que exige la cuenta activa): se apoya en el prototipo, donde
    `vUsuario` muestra «Modificar datos» siempre y `save-user` no controla el estado.
  - Restablecer, reactivar y dar de baja piden confirmación: abrir la ventana (GET) no cambia nada y el
    cambio se hace con un POST. La contraseña temporal de un restablecimiento o de una reactivación se
    muestra una sola vez, en la respuesta del POST, y no se guarda en ningún lado.
  - Detalle de la auditoría: la modificación guarda solo los campos que cambiaron, como
    `{campo: [antes, después]}`; la reactivación y la baja guardan `{"estado": [antes, después]}`; el
    restablecimiento no lleva ningún dato de contraseña.
  - Las pruebas de precondiciones se llaman `test_pre_<letra>_<que_espera>`, con la fuente en el
    docstring (como las de reglas, extensiones y postcondiciones de `CLAUDE.md`).
- Por qué: un único queryset evita repetir el alcance en cada servicio y que una pantalla nueva lo olvide.
  Alinear la columna con el validador evita que un número válido según D-21 (por ejemplo,
  «+123 (45) 678-901-2345») falle por el largo del campo. La cuenta fuera del alcance da 403 y no 404
  porque lo pide SEG-13, y quien prueba URLs ya está dentro del sistema: saber que un id existe no le da
  acceso a nada. En el alta, el email de una cuenta fuera del alcance da el mensaje genérico para no
  revelar nada de una cuenta que el Gerente no gestiona. La búsqueda exige todas las palabras para que
  agregar palabras acote el resultado en vez de ampliarlo. Una modificación sin cambios no deja un
  registro de auditoría que no registra nada, y restablecer o reactivar solo donde corresponde evita
  generar una contraseña temporal para una cuenta en el estado equivocado. Permitir modificar los datos de
  una cuenta inactiva deja corregirlos antes de reactivarla (por ejemplo, un email mal escrito); el
  prototipo lo permite y queda auditado igual. Pedir confirmación evita restablecer una contraseña o dar de
  baja por un clic accidental, y que abrir la ventana no cambie nada permite abrirla con un simple enlace.
- Fuentes: `docs/casos_de_uso/usuarios.md` (USR-CNS-USR, USR-ALT-USR, USR-MOD-USR, USR-BAJ-USR, SEG-13 y
  SEG-15); `CLAUDE.md` (arquitectura y tests); D-15, D-16, D-21, D-22 y D-25.
- Consecuencias: migración `0005`, que solo cambia el campo `telefono` (sin cambio de datos). La tarea 05
  agrega la rama del Administrador en `en_alcance_de` y SEG-15. Límite conocido: recargar «Cuenta
  creada» reenvía el formulario y da «Ya existe una cuenta con ese email.». Se acepta porque la
  contraseña temporal no se guarda en ningún lado (ni en la sesión ni en la base), y mostrarla de nuevo
  después de una redirección exigiría guardarla. El mismo límite alcanza a la respuesta de un
  restablecimiento o de una reactivación: recargarla reenvía el formulario. Restablecer generaría otra
  temporal y la mostrada antes dejaría de servir; reactivar daría “La cuenta ya está activa”.
- Estado: vigente (reemplaza en parte a D-15); D-36 reemplaza el formato del detalle de la auditoría de este punto (`{campo: [antes, después]}`)

## D-29 — Convenciones de interfaz del sistema

- Fecha: 11/11/2026
- Decidió: Lautaro Fernández (durante la revisión a mano de la tarea 04b)
- Antes: D-24 fijó que las pantallas siguen el prototipo, pero no cómo se muestran los mensajes que
  vienen de `django.contrib.messages`, ni el aspecto y el foco de los botones, ni cómo llegan al
  navegador los cambios en la hoja de estilos y el JavaScript. En la revisión de la 04b, el botón
  secundario (borde y texto gris claro sobre blanco) casi no se veía; los mensajes se mostraban como un
  bloque fijo en la página, que no desaparecía; y el navegador seguía usando un `infoponia.js` viejo
  después de cambiarlo.
- Decisión:
  - Los avisos (`django.contrib.messages`, y los que genera la propia pantalla, como «Contraseña
    copiada.») se muestran como avisos breves. Cada aviso es una tarjeta (fondo `--card`, borde
    `--border`, radio de 6px, sombra suave) con una franja de 4px a la izquierda del color de su tipo
    (`--status-ok` para éxito, `--status-danger` para error), un ícono del mismo color (check o warn),
    el texto en `--foreground` y una cruz en `--muted-foreground`. Una barra de 3px en la base, del color
    del tipo, se achica durante los 10 segundos.
  - Duran 10 segundos, los de éxito y los de error, y se pueden cerrar antes con la cruz. Van en una
    región con `role="status"`, que está vacía en toda pantalla con sesión, para que los lectores de
    pantalla anuncien cada aviso nuevo.
  - Se ubican arriba a la derecha, debajo del encabezado, con un ancho máximo de 380px, y varios se apilan
    hacia abajo. En pantallas de menos de 760px ocupan el ancho con 12px de margen y van abajo, sobre el
    pie (10px por encima de `--footer-height`), apilados hacia arriba: el primero queda junto al borde y los
    que llegan después se suman encima (actualizado el 14/11/2026).
  - Al aparecer se deslizan desde la derecha con fundido (250ms, ease-out); al irse, por tiempo o por la
    cruz, se desvanecen hacia la derecha (200ms) y recién después se quitan de la página. En pantallas de
    menos de 760px entran deslizándose desde abajo y salen hacia abajo, con la misma duración y la misma
    curva (actualizado el 14/11/2026). Con `prefers-reduced-motion` no hay desplazamiento ni barra animada:
    solo aparecen y desaparecen, también en pantallas angostas.
  - Sin JavaScript queda el aviso fijo en la página, como respaldo. Los errores que se muestran debajo de
    los campos de un formulario no son avisos y no cambian.
  - El botón secundario (`.btn-ghost`) usa borde y texto en el verde primario sobre fondo blanco: 6,54:1
    (el borde gris anterior tenía 1,37:1); en el hover, verde oscuro sobre verde claro (7,29:1). Los
    botones que son enlaces no se subrayan. Todos los botones muestran el foco al navegar con Tab: un
    borde de 2px en el verde primario (`:focus-visible`), separado 2px del botón.
  - Los archivos estáticos propios (hoja de estilos y scripts) se piden con `{% static_v %}`, que agrega la
    fecha del archivo a la URL, porque `runserver` los sirve sin `Cache-Control`.
  - Envíos en curso (actualizado el 16/11/2026): al enviar un formulario POST, el botón de envío se deshabilita
    y muestra un indicador animado con el verbo de la acción («Guardando…» por defecto; otro verbo va en
    `data-enviando`, en el botón o, si no, en su formulario) hasta que llega la respuesta, y un segundo envío del
    mismo formulario se descarta (también con Enter). Lo hace `infoponia.js` para todos los formularios, incluidos
    los de las ventanas que inserta HTMX y los de `hx-post`; los formularios GET (el filtro de la lista) quedan
    afuera. El botón vuelve a su estado al volver atrás desde el caché del navegador, al terminar un pedido de
    HTMX o a los 30 s sin respuesta. Con `prefers-reduced-motion` el indicador no gira. Sin JavaScript, el
    formulario envía como siempre.
  - Errores de HTMX (actualizado el 16/11/2026): si un pedido de HTMX falla, la pantalla queda como estaba y se
    muestra un aviso de error de este mismo estilo, sin apilar uno idéntico a otro que ya se ve. Con un error del
    servidor (4xx o 5xx) dice «No pudimos completar la acción. Volvé a intentarlo.», sin mencionar la conexión; sin
    conexión o sin respuesta a tiempo dice «No pudimos completar la acción. Revisá tu conexión y volvé a
    intentarlo.». El límite de espera es de 30 s (`<meta name="htmx-config">` de `base.html`; HTMX no corta
    ningún pedido por defecto). Render arranca con `gunicorn config.wsgi:application`, sin `--timeout`, así que
    usa el valor por defecto de gunicorn, 30 s, y el límite de HTMX queda bien. Si se cambia el `--timeout` de
    gunicorn, hay que revisar el de HTMX.
  - Volver a la pantalla pedida (actualizado el 16/11/2026; SEG-13 y USR-INI-SES, flujo principal): después de
    iniciar sesión se vuelve a la pantalla pedida (`next`) si el rol de la cuenta puede abrirla; si no (por
    ejemplo, entra otra persona en el mismo navegador), se va al inicio de la cuenta, y no al 403. Lo decide
    `pantalla_accesible_para` (`core/acceso.py`) con los roles que `rol_requerido` deja anotados en la vista. Una
    URL que no existe se conserva como siempre. Una cuenta fuera de alcance dentro de una pantalla permitida
    (por ejemplo, `/usuarios/7/`) sigue dando 403.
- Por qué: el botón secundario tiene que verse en una tarjeta blanca y cumplir el contraste mínimo de texto
  (4,5:1) y de componentes (3:1). Un aviso que se integra con el sistema (tarjeta, colores de estado)
  no parece un cuerpo extraño y no empuja ni tapa el contenido; 10 segundos dan tiempo de leerlo y la
  cruz deja cerrarlo antes. El `role="status"` hace que se anuncie sin quitarle el foco a nadie, y el
  respaldo fijo evita perder el mensaje si el JavaScript no corre. Los colores de texto, cruz e ícono
  sobre el blanco de la tarjeta miden 18,47:1 (texto), 5,82:1 (cruz), 5,36:1 (ícono de éxito) y 6,25:1
  (ícono de error). Sin foco visible, quien navega con teclado no sabe dónde está. Sin `Cache-Control`, el
  navegador guarda por su cuenta los archivos que solo traen `Last-Modified` y no vuelve a pedirlos: un
  cambio de JavaScript no llegaba y los avisos de la 04b parecían no desaparecer; con la fecha del archivo
  en la URL, cada cambio es una URL nueva. Abajo en pantallas angostas (actualizado el 14/11/2026): en menos
  de 760px el aviso de arriba tapaba el título y el texto del comienzo de la página, que es lo primero que se
  lee, y como el aviso ocupa todo el ancho, no queda un costado libre; abajo, sobre el pie, no tapa eso. Se apilan hacia
  arriba para que, como en escritorio, el primer aviso quede junto al borde y los siguientes no lo muevan de
  lugar. Solo cambia la posición y el nombre de la animación (nada de JavaScript): el temporizador, la cruz,
  el `role="status"` y el respaldo sin JavaScript son los de siempre. El bloque de animaciones de pantallas
  angostas va antes del de `prefers-reduced-motion` porque, con la misma especificidad, gana la última regla:
  en el orden inverso, un celular con ese ajuste volvería a animar los avisos. Envíos en curso y errores de HTMX
  (16/11/2026): en producción, la base de Neon (plan Free) se suspende a los 5 minutos sin uso y el primer pedido
  tarda; la página no daba señal de estar trabajando y un usuario tocó Guardar dos veces, y un segundo envío puede
  fallar o duplicar una operación. Un límite de espera menor que el de gunicorn cortaría pedidos que el servidor
  todavía completa, y el aviso «volvé a intentarlo» invitaría a repetir una operación ya hecha. Se distinguen dos
  mensajes porque, si el servidor respondió con un error, la conexión funcionó y pedir que se la revise confunde.
  Volver a la pantalla pedida (16/11/2026): el 403 de una pantalla que la cuenta que acaba de entrar no puede abrir
  es un tropiezo evitable; cubrir también las cuentas fuera de alcance exigiría ejecutar la pantalla pedida dos
  veces, con los efectos que eso tenga en el futuro.
- Fuentes: D-24 y D-25; WCAG 2.x: criterios 1.4.3 (contraste mínimo), 1.4.11 (contraste de componentes),
  2.4.7 (foco visible) y 4.1.3 (mensajes de estado); revisión a mano de las tareas 04b y 06b.
- Consecuencias: toda pantalla nueva usa estas convenciones. Las verifican las pruebas
  `test_d29_...` de `core/tests/test_interfaz.py` (incluidas las de pantallas angostas: avisos abajo, entrada y
  salida por abajo, y «reducir movimiento»); el temporizador y la cruz son JavaScript y se prueban a mano, y
  la posición abajo se mira a mano con el navegador a menos de 760px o en un celular (un teclado virtual abierto
  podría tapar un aviso de abajo). Las pruebas `test_d29_` de `EnviosEnCursoTests` (`core/tests/test_interfaz.py`)
  verifican lo que se ve en el HTML y en la hoja de estilos (botones de envío sin cambios en el HTML del servidor,
  `data-enviando` en los que no dicen «Guardar…», el límite de 30 s y el indicador con «reducir movimiento»); las
  de `test_usr_ini_ses.py` (`test_seg13_next_…`), la vuelta a la pantalla pedida. El comportamiento del botón, el
  doble envío y el aviso de error de HTMX son JavaScript y se prueban a mano (lista en `docs/estado.md`). En la tarea 09 se evalúa reemplazar `static_v` por
  `ManifestStaticFilesStorage` de WhiteNoise (`whitenoise.storage`) en producción, que pone un hash en el
  nombre de cada archivo.
- Estado: vigente; actualizada el 14/11/2026 (avisos abajo en pantallas de menos de 760px) y el 16/11/2026
  (envíos en curso, errores de HTMX y vuelta a la pantalla pedida)

## D-30 — Cuentas del Administrador: SEG-15, pantallas y admin de Django (tarea 05)

- Fecha: 12/11/2026
- Decidió: Lautaro Fernández (durante la planificación de la tarea 05 y la revisión a mano de la 05a, a propuesta de Claude)
- Antes: D-16 dio al Administrador las cuentas del Gerente y las de los Administradores, y pidió apagar el admin de
  Django en producción cuando existieran sus pantallas; D-28 pasó SEG-15 a la tarea 05. Faltaba definir cómo se
  garantizan los invariantes con dos operaciones simultáneas, qué botones ve el Administrador mientras la tarea 05
  no está completa, adónde llega al iniciar sesión, qué se muestra al dar de alta un Gerente cuando ya hay uno
  activo (el prototipo muestra el aviso y el formulario con el botón deshabilitado), qué ofrece la ventana de
  reactivar a un Gerente cuando ya hay otro activo (el prototipo deja confirmar y recién después rechaza), en qué
  orden se bloquean las filas cuando hay que cuidar un invariante y cómo se decide que el admin de Django esté
  apagado.
- Decisión:
  - SEG-15, Gerente (tarea 05a): `alta_usuario` bloquea con `select_for_update()` todas las filas de Gerente, sin
    filtrar por estado y en orden de id, y después, en una consulta aparte, busca si hay un Gerente activo.
  - La restricción `un_solo_gerente_activo` de la base queda como respaldo. Si rechaza un alta, el
    `IntegrityError` se traduce con `raise ... from error`: con ese nombre de restricción da «gerente_activo»; con
    cualquier otro, o si el nombre no se puede leer, da «email repetido». Nunca llega un error 500 a la pantalla.
  - SEG-15, Administrador (tarea 05b): la baja de un Administrador bloquea a todos los Administradores activos y
    se rechaza, con el código «ultimo_administrador», si no queda otro (precondición c de USR-BAJ-USR). No hay
    restricción de la base que lo respalde: el bloqueo es lo único que lo garantiza.
  - Reactivar un Gerente (regla 5 de USR-MOD-USR) sigue el mismo camino que el alta: se bloquean todas las filas de
    Gerente, sin filtrar por estado, y después se busca al Gerente activo en una consulta aparte; el rechazo lleva
    el código «gerente_activo». La restricción `un_solo_gerente_activo` queda de respaldo, traducida como en el
    alta; si no se puede identificar la restricción, el error es «no_se_pudo_reactivar».
  - Orden de los bloqueos en modificar, restablecer, reactivar y dar de baja: primero el grupo de filas que cuida
    un invariante (todos los Gerentes, o todos los Administradores activos), en orden de id; después se vuelve a
    verificar que quien actúa siga activo; por último se bloquea y se vuelve a leer la cuenta. Para saber a qué
    grupo pertenece la cuenta, se la lee antes sin bloquear (el rol no cambia, D-11).
  - Restablecer la propia contraseña se rechaza con el código «propia_cuenta» (regla 4 de USR-MOD-USR): el
    Administrador la cambia con USR-CMB-CTR.
  - El rechazo por un Gerente activo es un error general (`NON_FIELD_ERRORS`, código `gerente_activo`), no un
    error de un campo.
  - Las pantallas muestran solo las acciones de `acciones_permitidas(actor, cuenta)`: ningún botón lleva a un
    403. En la 05a, el Administrador no tenía ninguna; en la 05b cambió solo esa función: el Administrador
    modifica, restablece y da de baja las cuentas activas de su alcance, y modifica y reactiva las inactivas; en
    su propia cuenta no restablece la contraseña (regla 4) y solo se da de baja si queda otro Administrador
    activo (precondición c).
  - La ventana de «Reactivar cuenta» de un Gerente, cuando ya hay otro Gerente activo, no ofrece confirmar:
    muestra directamente el motivo, con «Ver a <nombre>» (la ficha del Gerente activo) y «Cerrar», igual que la
    pantalla de alta. El botón sí se muestra en la ficha. Un envío manual lo rechaza igual el servicio con
    «gerente_activo».
  - Si el Administrador se da de baja a sí mismo (hay otro activo), la ventana de confirmación lo avisa («Es tu
    propia cuenta»); al confirmar, se cierra su sesión y vuelve al inicio de sesión con el aviso «Tu cuenta se dio
    de baja y se cerró la sesión.».
  - Con un Gerente activo, «Alta de Gerente» no muestra el formulario: solo el aviso, con el nombre del Gerente
    activo y qué hay que hacer, y dos botones: «Ver a <nombre>», que lleva a su ficha, y «Volver a Cuentas». Un
    envío manual lo rechaza igual el servicio con «gerente_activo». Esto reemplaza al prototipo en este punto.
  - El Administrador entra directo a «Cuentas» al iniciar sesión, y su menú lateral tiene esa única entrada.
  - El filtro de rol de la lista usa el valor `ADMINISTRADOR` (`core/models.py`) para los superusuarios, que no
    tienen `rol` (D-10); es la misma constante que guarda la auditoría.
  - El admin de Django se enciende solo si `DEBUG` está encendido: `ADMIN_DJANGO_HABILITADO = DEBUG`, sin variable
    propia. Con `DJANGO_DEBUG=0` no se registra ninguna ruta de `/admin/` y responde 404, también a un
    Administrador con la sesión abierta. Se calcula al arrancar (tarea 05b).
  - Las pruebas de operaciones simultáneas van en clases `<CodigoCu>ConcurrenciaTests` (`TransactionTestCase`),
    con el auxiliar `core/tests/concurrencia.py`; las de las decisiones, con el prefijo `test_d30_`; las de
    SEG-15, con `test_seg15_`.
  - Hasta la tarea 06, el Administrador cambia su propia contraseña solo por consola.
- Por qué:
  - Se bloquean todas las filas de Gerente, sin filtrar por estado, porque si se filtrara por activos y no
    hubiera ninguno, no se bloquearía nada y dos altas simultáneas pasarían las dos. Sin filtro, la segunda alta
    espera a que la primera confirme y, cuando sigue, su consulta posterior ya ve al Gerente nuevo. Esa consulta
    es una sentencia aparte, y PostgreSQL, en su modo por defecto, hace que cada sentencia vea lo último que se
    confirmó.
  - El orden por id evita los bloqueos cruzados: si una operación bloqueara primero su cuenta y después las
    demás, y otra lo hiciera al revés, cada una esperaría a la otra y la base abortaría una, que la persona vería
    como un error 500. Con un orden fijo, la segunda simplemente espera.
  - La restricción de la base queda como respaldo porque el bloqueo de filas no cubre el primer Gerente de todos:
    sin ninguna fila de Gerente no hay nada que bloquear, y dos altas simultáneas avanzan juntas. Ahí frena la
    segunda la restricción, y se traduce para que la persona vea el mismo mensaje claro y no un error 500; si el
    nombre de la restricción no se puede leer, se informa un error conocido antes que un error del servidor. Para
    «al menos un Administrador activo» no hay restricción posible: compara varias filas y una restricción mira una
    sola. Haría falta un disparador de la base, que por ahora no se agrega; por eso ahí vale solo el bloqueo.
  - El rechazo es un error general porque no es un problema de un campo: la pantalla lo muestra arriba, como el
    aviso del prototipo, y no debajo de «Rol», que además está fijo para el Administrador.
  - El grupo se bloquea antes que la cuenta porque, si cada operación bloqueara primero la suya y después el
    grupo, dos operaciones sobre cuentas distintas (por ejemplo, dos Administradores que se dan de baja entre sí)
    se esperarían mutuamente y la base abortaría una, que la persona vería como un error 500. Además, la
    auditoría referencia a quien actúa y toma un bloqueo sobre su fila, lo que cruza todavía más las esperas.
    Con el grupo primero y en orden de id, la segunda operación simplemente espera. Quien actúa se vuelve a
    verificar después de bloquear porque su fila es una de las bloqueadas y pudo quedar inactiva mientras esperaba
    (con tres Administradores, A da de baja a B mientras B da de baja a C): sin esa verificación, una cuenta que
    ya cayó seguiría actuando. La cuenta se bloquea y se vuelve a leer al final para trabajar con su estado real,
    no con el que tenía cuando se la leyó para saber su grupo.
  - La ventana de reactivar un Gerente con otro activo no ofrece confirmar por la misma razón que la pantalla de
    alta: la persona confirmaría algo que ya se sabe que se va a rechazar. El botón se muestra igual en la ficha,
    porque no lleva a un 403 y explica qué hay que hacer; el prototipo, en cambio, deja confirmar y recién
    después rechaza.
  - Dar de baja la propia cuenta cierra la sesión porque la cuenta inactiva ya no puede usar el Sistema, y el
    aviso viaja en una cookie porque la sesión se vacía; así la persona no ve un error al pedir la pantalla
    siguiente.
  - `acciones_permitidas` existe para que ningún botón lleve a un 403: quien está en la pantalla no tendría forma
    de saber que una acción no le corresponde, y repetir esa condición en cada plantilla haría que una pantalla
    nueva la olvidara. Es una sola función, y lo que cambia en la 05b es su resultado.
  - El Administrador entra directo a «Cuentas» porque es su única tarea: no tiene rol de negocio ni módulos, y un
    panel vacío no le sirve.
  - Con un Gerente activo no se muestra el formulario porque la persona completaría datos que no se pueden
    guardar y se enteraría recién al enviarlos. Se le dice desde el principio qué pasa y qué hacer, y se le dan
    los dos caminos útiles: ir a la ficha del Gerente o volver a la lista.
  - El admin de Django queda atado a `DEBUG` porque una variable propia podría quedar encendida en producción por
    error, y entonces SEG-18 dependería de que nadie la configure mal. Con `DEBUG`, que en producción tiene que
    estar apagado de todos modos (tarea 09 de `docs/estado.md`), no hay una segunda llave que cuidar.
  - Las operaciones simultáneas se prueban con dos hilos y dos conexiones porque `TestCase` envuelve todo en una
    sola transacción y no puede reproducir dos pedidos a la vez; el bloqueo solo se prueba de verdad así.
- Fuentes: SEG-15 y SEG-18 (`docs/casos_de_uso/usuarios.md`); reglas 1 y 2 de USR-ALT-USR, regla 4 y regla 5 de
  USR-MOD-USR, precondición c y regla 1 de USR-BAJ-USR; D-09, D-10, D-16, D-22 y D-28; prototipo
  `docs/prototipos/cuentas_y_seguridad.html` (`enter()`, `NAV`, `vAlta`, `baja-do`).
- Consecuencias:
  - Cambia `UsuarioQuerySet.en_alcance_de` (rama del Administrador), sin migración.
  - Con la 05b, el Administrador gestiona la cuenta del Gerente y las de los Administradores con las pantallas
    propias, y el aviso de la pantalla de alta («dá de baja al actual desde su ficha») ya se cumple. El admin de
    Django queda apagado en producción; la vía de emergencia es la consola de Render (plan Starter).
  - El valor por defecto de `DJANGO_DEBUG` es «1»: si en Render faltara la variable, `DEBUG` quedaría encendido y,
    con él, el admin. Hay que confirmar que Render tiene `DJANGO_DEBUG=0`; en la tarea 09 `DEBUG` pasa a quedar
    apagado por defecto.
  - Antes de unir la 05b a main, hay que entrar a producción con un Administrador y confirmar que llega a
    «Cuentas», porque después el admin de Django ya no estará disponible en Render.
  - Límite conocido: el alta no vuelve a verificar que quien actúa siga activo. El grupo que bloquea (las filas
    de Gerente) no incluye a quien actúa, y bloquear también a los Administradores en cada alta no se justifica por
    un caso tan improbable: que quien da de alta quede inactivo justo mientras su alta espera el bloqueo. Modificar,
    restablecer, reactivar y dar de baja sí lo verifican.
  - En un entorno de desarrollo con `DEBUG` encendido el admin sigue disponible; en el CI, con `DJANGO_DEBUG=0`, no
    existe, por eso las pruebas no lo usan.
  - La contraseña propia del Administrador solo se cambia por consola hasta la tarea 06.
- Estado: vigente; D-36 suma «Auditoría» al menú del Administrador (ya no tiene una única entrada); D-31 cierra su consecuencia sobre la contraseña propia del Administrador; D-32 (14/11/2026) pasa
  sus bloqueos de filas de `FOR UPDATE` a `FOR NO KEY UPDATE`, sin cambiar su orden

## D-31 — Mi perfil y cambio voluntario de contraseña (tarea 06a)

- Fecha: 13/11/2026
- Decidió: Lautaro Fernández (durante la planificación de la tarea 06 y la revisión a mano de la 06a, a propuesta de Claude)
- Antes: USR-GST-PRF pide una pantalla con los datos de la cuenta con la que se opera, desde la que se cambia la
  contraseña (regla 3), y USR-CMB-CTR pide la contraseña actual cuando no extiende a USR-INI-SES (regla 1). El
  prototipo pone el cambio de contraseña dentro de Mi perfil (`vPerfil`, `chgpw`) y rotula la entrada del menú
  de cuenta «Mi perfil» para las cuentas de los roles y «Mi perfil y contraseña» para el Administrador
  (`accountPop`). D-27 dejó la lista de requisitos en vivo con solo lo que el navegador puede comprobar y D-30
  dejó la contraseña propia del Administrador «solo por consola hasta la tarea 06». D-25 reservó «Mi perfil»
  para la tarea 06. No estaba definido en qué dirección se envía el cambio, ni si la contraseña actual se pide
  también en el formulario, ni a quién se le pide corregir los datos.
- Decisión:
  - Mi perfil (`mi-perfil/`, solo lectura) muestra nombre, apellido, email, teléfono, rol y estado de la cuenta con
    la que se opera, y nunca la contraseña ni su resumen (regla 1). Para el Administrador el rol dice
    «Administrador (sin rol operativo)» (D-10). La consulta no se audita (regla 4, SEG-14).
  - Mi perfil no tiene función en `core/servicios.py`. Sus pruebas se escribieron después de la vista.
  - El cambio de contraseña es un formulario dentro de Mi perfil que se envía a `mi-perfil/contrasena/`, una vista
    propia que solo acepta POST (un GET vuelve a Mi perfil) y lleva `never_cache`. Llama a
    `cambiar_contrasena(request.user, nueva, actual)`, sin cambiarla. Si sale bien: `update_session_auth_hash`
    (SEG-10), un aviso breve (D-29) y redirección a Mi perfil. Si falla: Mi perfil con los errores en los
    campos, sin volver a escribir las contraseñas.
  - `FormularioCambioContrasena` exige también la contraseña actual, con el mismo mensaje que el servicio
    («Ingresá tu contraseña actual.»). El servicio sigue siendo quien decide si es correcta (regla 1).
  - La lista de requisitos suma «Es distinta de la contraseña actual» (`data-requisito="distinta"`) solo en Mi
    perfil: `politica_contrasena.js` la marca comparando con el campo `[data-contrasena-actual]`, que solo existe
    ahí. En «Elegí tu contraseña» la lista no cambia.
  - Regla 2 de USR-GST-PRF: la persona no modifica sus datos desde el perfil. El texto «Para corregir estos
    datos, pedíselo …» nombra a quien gestiona la cuenta según el alcance de D-16 y D-28: «al Administrador» si es
    un Gerente; «al Gerente (<nombre>)» si es de cualquier otro rol, o «al Gerente» si no hay uno activo (D-13).
    El texto lo arma `quien_gestiona(cuenta)` en `core/servicios.py`, una función de lectura. El Administrador,
    que gestiona su propia cuenta, ve en cambio «Modificar mis datos», que lleva a la pantalla de modificar de
    «Cuentas». En su ficha, el Administrador ve «Tu contraseña la cambiás desde Mi perfil» (`vUsuario`).
  - El menú de cuenta ofrece «Mi perfil» a todas las cuentas, también al Administrador. Esto se aparta del
    prototipo, que rotula «Mi perfil y contraseña» para el Administrador.
  - La foto de perfil (SEG-19) es de la tarea 07: queda el avatar con la sigla y el lugar marcado con un
    comentario, sin botones. Las cuentas vinculadas son de la 06b. En celular, la cabecera de Mi perfil muestra
    «Volver» al inicio (`back-btn` del prototipo).
- Por qué:
  - Una vista propia solo POST para el cambio, porque Mi perfil es una consulta sin efectos (regla 4) y el cambio
    es una operación con servicio, auditoría y cambio del resumen de la sesión (SEG-10). Separadas, Mi perfil se
    puede abrir, recargar y volver a él con «Atrás» sin riesgo, y la operación solo ocurre con un POST con CSRF.
    Un GET en la dirección de la operación vuelve a Mi perfil en lugar de mostrar un error 405 sin salida. Si
    sale bien se redirige, así que recargar no reenvía el formulario; `never_cache` evita que el navegador
    conserve la respuesta de una operación sobre contraseñas.
  - La contraseña actual es obligatoria también en el formulario porque el servicio se llama recién cuando el
    formulario es válido. Si el formulario no la exigiera, un envío vacío mostraría primero los errores de la
    contraseña nueva y, recién al corregirlos, el de la actual: dos rondas. Con la exigencia, los tres errores
    aparecen juntos, como en `pwChangeErr` del prototipo. El mensaje es el mismo del servicio para que la
    persona no vea dos textos distintos para lo mismo. Que la contraseña sea correcta lo decide solo el servicio,
    que además la vuelve a pedir: el formulario no es una segunda fuente de la regla.
  - «Distinta de la actual» va solo donde está ese campo porque D-27 limita la lista a lo que el navegador puede
    comprobar. En Mi perfil la persona escribe la actual y el navegador puede compararla; en «Elegí tu contraseña»
    no conoce la temporal, así que la lista allí no puede prometer esa comprobación. La lista es solo una ayuda
    visual: el servidor valida siempre (SEG-03).
  - El texto de a quién pedir los cambios sigue el alcance porque indicarle a la persona alguien que no puede
    modificar su cuenta la dejaría sin salida: esa persona recibiría un 403 si lo intentara (SEG-13). Quién
    gestiona a quién ya lo fijan D-16 y D-28, y el texto dice lo mismo. Sin Gerente activo se dice «al Gerente» sin nombre porque el
    Sistema tiene que funcionar entre la baja de un Gerente y el alta del siguiente (D-13). Se arma en una
    función y no con una condición en la plantilla, por la razón de `acciones_permitidas` (D-30): repetirla en
    cada pantalla haría que una nueva la olvidara. «Al» y no «a el»: el prototipo arma el texto sin la
    contracción.
  - Mi perfil no tiene servicio por el criterio de D-25 para iniciar sesión: un servicio que solo envolviera una
    lectura no agregaría nada. USR-GST-PRF no tiene precondiciones de negocio ni cambios que garantizar mientras
    la persona solo consulta (postcondición a: «no se producen cambios»); el cambio de contraseña ya tiene su
    servicio, `cambiar_contrasena`. La carga de la foto, que sí modifica datos, tendrá el suyo en la tarea 07. Las
    pruebas van después de la vista, como pide `CLAUDE.md` para las pantallas sin reglas de negocio.
  - El menú dice «Mi perfil» para todas las cuentas porque la contraseña está dentro de Mi perfil para todas:
    `vPerfil` ofrece el mismo formulario al Administrador y a los demás roles. Dos nombres para el mismo destino
    confunden, y el rótulo más largo sugeriría que la contraseña de los demás está en otro lado. El prototipo es
    solo guía visual (`CLAUDE.md`, fuente 5) y su rótulo para el Administrador no agrega información: el destino
    y el formulario son los mismos.
- Fuentes: `docs/casos_de_uso/usuarios.md` (USR-GST-PRF reglas 1 a 4; USR-CMB-CTR reglas 1 a 3 y
  postcondiciones c y d; USR-INI-SES regla 4; SEG-03, SEG-04, SEG-10, SEG-13 y SEG-14; «Pantallas»); prototipo
  `docs/prototipos/cuentas_y_seguridad.html` (`vPerfil`, `accountPop`, `chgpw`, `pwChangeErr`, `policyList`,
  `vUsuario`); D-10, D-13, D-16, D-25, D-27, D-28, D-29 y D-30; `CLAUDE.md` (tests).
- Consecuencias:
  - Cierra la consecuencia de D-30 sobre la contraseña propia del Administrador: la cambia desde Mi perfil, con la
    contraseña actual, como cualquier persona. La consola de Render sigue siendo la vía de emergencia (D-30).
  - `quien_gestiona` repite en texto lo que `en_alcance_de` define en código: si cambia el alcance de quién
    gestiona a quién, hay que actualizar las dos. No se la derivó del queryset porque este responde «qué cuentas
    gestiona quien actúa» y no «quién gestiona esta cuenta».
  - Límite conocido: si el cambio falla, la pantalla con los errores es la respuesta del POST a
    `mi-perfil/contrasena/`; recargarla hace que el navegador pida confirmar el reenvío del formulario. Es
    inocuo: las contraseñas no se guardan en ningún lado y, si el reenvío tiene éxito, redirige a Mi perfil.
  - La marca «distinta de la actual» compara con lo que se escribió en el campo, no con la contraseña real: si
    la actual está mal escrita, la marca puede mostrarse igual. Es una ayuda visual; el servicio decide.
  - Hasta la 06b, el menú de cuenta solo ofrece «Mi perfil» y «Cerrar sesión», y Mi perfil no tiene la tarjeta de
    cuentas vinculadas (D-25: solo se muestra lo que existe). La 06b agrega la tarjeta y «Cambiar de cuenta».
  - Pruebas: `core/tests/test_usr_gst_prf.py` (12, incluida `test_d31_`) y 10 nuevas en `UsrCmbCtrVistaTests`
    (`core/tests/test_usr_cmb_ctr.py`). Sin migraciones.
- Estado: vigente

## D-32 — Cuentas vinculadas: grupo, orden de verificaciones y bloqueos (tarea 06b)

- Fecha: 13/11/2026
- Decidió: Lautaro Fernández (durante la planificación de la tarea 06 y la revisión de la 06b, a propuesta de Claude)
- Antes: D-17 fijó el grupo de cuentas vinculadas, quién lo arma, cómo se pasa de una cuenta a otra y SEG-11, pero
  no cómo se implementa: qué tabla, cómo se unen y se disuelven los grupos, en qué orden se verifica y se bloquea,
  ni qué ve quien gestiona una cuenta con vínculos. La regla 8 de USR-VNC-CTA dice que la persona puede desvincular
  «no solo la cuenta con la que está operando», pero el prototipo (`vPerfil`) lista solo las otras. La regla 3 de
  USR-CNS-USR y la regla 7 de USR-MOD-USR piden mostrar los vínculos en solo lectura, y esas cuentas pueden estar
  fuera del alcance de quien mira (D-28). SEG-05 y D-19 no ponen límite a los intentos de identificación.
- Decisión:
  - Modelo (migración `0006`, con el permiso explícito del 13/11/2026 que piden D-17 y `CLAUDE.md`):
    `GrupoCuentas`, solo con `id`; `Usuario.grupo`, clave foránea opcional con `PROTECT`; y la restricción
    `administrador_sin_grupo` (regla 5), que respalda al servicio. Un grupo con una sola cuenta no existe: lo
    borra el servicio.
  - Servicios en `core/servicios.py`: `vincular_cuenta`, `desvincular_cuenta` y `cuenta_para_cambiar` (SEG-09), y
    las consultas de solo lectura `cuentas_vinculadas` y `obtener_cuenta_del_grupo`. `restablecer_contrasena` y
    `reactivar_usuario` sacan la cuenta de su grupo (SEG-11) con `_sacar_del_grupo`, que comparten con desvincular.
  - Al vincular, sin grupos se crea uno; si solo una cuenta tiene grupo, la otra se suma; si cada una tiene el
    suyo, queda el de menor id y el otro se borra.
  - Auditoría. Vinculación: afectadas, las dos cuentas y las que cambiaron de grupo; detalle `{"grupo",
    "grupo_unido"}`. Desvinculación: la cuenta que sale y, si el grupo se disolvió, la que quedaba; detalle
    `{"grupo", "disuelto"}`. Restablecimiento y reactivación suman `sale_del_grupo` (id del grupo) solo si la
    cuenta estaba en uno, y la que quedaba sola figura entre las afectadas. El cambio de cuenta no se audita (SEG-14).
  - `PermissionDenied`, con la misma respuesta, para una cuenta de otro grupo, una sin grupo y un id que no existe,
    tanto al desvincular (también al abrir su ventana) como al cambiar de cuenta. Pasar a la propia cuenta también
    da `PermissionDenied`. Esto reemplaza al 403 y 404 distintos de D-28 en este caso.
  - Orden de las verificaciones de `vincular_cuenta`. Antes de bloquear: que quien opera pueda vincular, email y
    contraseña presentes, «misma_cuenta» y «ya_vinculada» (solo para la cuenta propia y las de su grupo) y la
    contraseña de la otra cuenta junto con que sea vinculable; se guarda el resumen de contraseña leído en ese
    momento. Después de bloquear, con todo releído: (a) la otra cuenta sigue siendo vinculable (activa, sin
    temporal, no Administrador) y su resumen de contraseña es el mismo → si no, «no_se_pudo_vincular»; (b) recién
    entonces, si cambió el grupo de alguna de las dos cuentas → «cambio_simultaneo».
  - `cambio_simultaneo` es un rechazo con mensaje y no un reintento. Un `IntegrityError` al unir los grupos se
    informa también como «cambio_simultaneo» (con `raise ... from error`); nunca llega un 500.
  - Orden de los bloqueos de toda operación que cambia quién está en un grupo (amplía D-30): 1) las filas de
    `GrupoCuentas`, en orden de id; 2) los invariantes, si corresponde; 3) que quien actúa siga activo; 4) las
    cuentas, en orden de id. Los bloqueos nuevos son `FOR NO KEY UPDATE` (`select_for_update(no_key=True)`).
    Restablecer y reactivar relevan el grupo de la cuenta después de bloquearla (`cuida_grupo`) y, si cambió, dan
    «cambio_simultaneo».
  - Desde el 14/11/2026, todos los bloqueos de filas de `core/servicios.py` son `FOR NO KEY UPDATE`, también los
    cuatro anteriores a esta decisión, que eran `FOR UPDATE`: `_bloquear_gerentes` y
    `_bloquear_administradores_activos` (05), el bloqueo de la cuenta en `_bloquear_cuenta_en_alcance` (04b y 05b)
    y el de la propia cuenta en `cambiar_contrasena` (03). El orden de los bloqueos no cambia.
  - El cambio de cuenta no bloquea nada: `login()` guarda el resumen de contraseña de la cuenta a la que se pasa,
    así que si después se la restablece, Django cierra esa sesión; si se la da de baja, deja de cargarla.
  - Al cambiar de cuenta no se muestra un aviso de éxito: la persona llega al inicio de la otra cuenta, que ya
    indica con qué rol y con qué cuenta opera (SEG-09). Sí se muestra el aviso de error si la cuenta ya no está
    disponible (actualizado el 14/11/2026, tarea chica de diseño).
  - «Salir del grupo» (regla 8): Mi perfil ofrece sacar del grupo también la cuenta con la que se opera. Esto se
    aparta del prototipo, que solo lista las otras cuentas.
  - La ficha de quien gestiona una cuenta muestra sus vínculos con rol, email y estado, en solo lectura; la
    cuenta vinculada lleva un enlace a su ficha solo si está dentro del alcance de quien mira.
  - Los textos del prototipo sobre el grupo en las ventanas de restablecer, reactivar y baja («sale de su grupo»,
    «sus cuentas vinculadas no cambian») se muestran solo si la cuenta tiene un grupo. El prototipo los muestra
    siempre.
  - Riesgos aceptados: (1) no hay tope de intentos de identificación (SEG-05, D-19), y `vincular_cuenta` responde
    sí o no a un par de email y contraseña igual que el inicio de sesión; no abre una vía nueva, porque el inicio
    de sesión ya la ofrece sin necesitar sesión. Un tope solo en el vínculo no protegería nada: se evalúa para los
    dos juntos en la tarea 09. (2) Si alguien adivina la contraseña de una cuenta y la vincula a la suya, el
    vínculo sobrevive a que su dueño cambie la contraseña voluntariamente (regla 4 de USR-CMB-CTR: las cuentas
    vinculadas se mantienen). Salidas: restablecer o reactivar la cuenta la saca del grupo (SEG-11); su dueño ve
    el vínculo en su Mi perfil y puede usar «Salir del grupo» (regla 8); la vinculación queda en la auditoría.
- Por qué:
  - Un modelo propio y una clave foránea, y no pares de cuentas, hacen que el vínculo sea transitivo por
    estructura (D-17); la restricción de la base respalda la regla 5 aunque un servicio nuevo la olvidara.
  - Queda el grupo de menor id al unir para que el resultado no dependa del orden en que se vinculó. La auditoría
    incluye a las cuentas que cambiaron de grupo para poder encontrar cualquier cuenta por su id, como en
    restablecer y reactivar.
  - El mismo `PermissionDenied` para todos los casos, porque desde Mi perfil cualquier cuenta podría probar ids
    para averiguar cuáles existen: con respuestas distintas, un id inexistente se distinguiría de uno de otro grupo.
    Pasar a la propia cuenta no tiene sentido: sería volver a iniciar sesión con la misma.
  - La contraseña se verifica antes de bloquear porque calcular el resumen es lento y no se deben mantener
    bloqueos tomados durante ese cálculo. Se guarda el resumen leído y se vuelve a comparar después de bloquear:
    si su dueño la cambió en el intervalo, la contraseña que la persona indicó ya no es la de la cuenta.
    (a) va antes que (b) porque un restablecimiento que disuelve el grupo de la otra cuenta también le cambia el
    grupo, y entonces corresponde el mensaje genérico (la cuenta ya no se puede vincular), no «las cuentas
    cambiaron». Cambiar el grupo de una cuenta que sigue siendo vinculable sí es «cambio_simultaneo».
  - Se rechaza y no se reintenta porque reintentar tomaría bloqueos fuera de orden y podría provocar un
    deadlock, que la persona vería como un error 500.
  - Se bloquea el grupo antes que las cuentas por el mismo motivo que en D-30: si cada operación bloqueara primero
    su cuenta y después el grupo, dos operaciones se esperarían mutuamente. Evidencia (13/11/2026): se
    desactivó en memoria el bloqueo del grupo de `restablecer_contrasena` y la prueba
    `test_seg11_restablecer_y_vincular_a_la_vez_no_dejan_la_temporal_en_el_grupo` falló con
    `OperationalError: deadlock detected`; sin ningún bloqueo en `vincular_cuenta`, las dos vinculaciones
    simultáneas tuvieron éxito y se pisaron (`2 != 1`) y una restablecer con vincular terminó con un
    `IntegrityError` sin traducir; sin ningún bloqueo en `desvincular_cuenta`, el grupo quedó con una sola
    cuenta. Con todo restituido, las tres pasan.
  - `FOR NO KEY UPDATE` y no `FOR UPDATE`, por cómo se guarda la auditoría: al insertar el registro de auditoría,
    la clave foránea hacia quien actúa (`RegistroAuditoria.usuario`) toma un bloqueo `FOR KEY SHARE` sobre la fila de
    esa cuenta. `FOR UPDATE` choca con ese bloqueo (es el único modo con el que choca `FOR KEY SHARE`);
    `FOR NO KEY UPDATE` no choca, porque no modifica la clave. Entre nuestras operaciones sigue habiendo exclusión
    mutua, porque `FOR NO KEY UPDATE` sí choca consigo mismo. Comprobado el 13/11/2026 contra la base de pruebas, con
    dos transacciones: con `FOR UPDATE` tomado sobre la cuenta, la inserción de la auditoría que la referencia
    esperó y venció su `lock_timeout` de 1,5 s; con `FOR NO KEY UPDATE`, se insertó sin esperar. La tabla de
    conflictos entre bloqueos de fila está en la documentación de PostgreSQL 17 (Explicit Locking, Tabla 13.3).
  - El cambio de cuenta no necesita bloquear porque el resumen de contraseña guardado en la sesión ya cubre los dos
    casos peligrosos (restablecimiento y baja), sin tomar ningún bloqueo en cada cambio.
  - Sin aviso de éxito al cambiar de cuenta porque SEG-09 ya pide que el inicio indique con qué rol se opera y lo
    hace («Operás como … con la cuenta …»): el aviso «Operás como Vendedor · Vera Sáenz» repetía eso y solo
    agregaba el nombre completo, que la cabecera muestra en escritorio y el inicio reemplaza por el email, que
    identifica la cuenta. Una persona que usa lector de pantalla recibe una página nueva, y el texto del inicio
    es lo primero que se lee. El aviso de error se mantiene: ahí no hay otra pantalla que explique qué pasó.
  - «Salir del grupo» porque la regla 8 dice que la persona puede desvincular también la cuenta con la que opera,
    y sin ese botón tendría que entrar a otra cuenta del grupo para sacar la que está usando.
  - Enlace a la ficha solo si está en el alcance para que ningún enlace lleve a un 403 (como `acciones_permitidas`,
    D-30); quien mira ve el vínculo igual, que es lo que piden las reglas.
  - Los textos sobre el grupo solo si la cuenta tiene uno porque decir «sale de su grupo» de una cuenta sin grupo
    sería falso; después de restablecer, la ventana de la contraseña temporal usa lo que la cuenta tenía antes.
  - Sin tope de intentos porque lo dicen SEG-05 y D-19 y no cambia con este vínculo; el riesgo del vínculo que
    sobrevive se acepta porque las tres salidas lo acotan y cambiarlo contradiría la regla 4 de USR-CMB-CTR.
- Fuentes: `docs/casos_de_uso/usuarios.md` (USR-VNC-CTA reglas 1 a 8; USR-GST-PRF reglas 1 y 3; USR-CNS-USR regla
  3; USR-MOD-USR postcondiciones b y c, reglas 3 y 7; USR-BAJ-USR regla 2; USR-CMB-CTR regla 4; SEG-04, SEG-05,
  SEG-06, SEG-09, SEG-11, SEG-14 y SEG-15); prototipo `docs/prototipos/cuentas_y_seguridad.html` (`vPerfil`,
  `accountPop`, `modalHtml` 'link', 'unlink', 'reset', 'react' y 'baja', `link-do`); D-17, D-19, D-22, D-28, D-29,
  D-30 y D-31; `CLAUDE.md` (tests y bloqueos); documentación de PostgreSQL 17 (bloqueos de fila).
- Consecuencias:
  - Migración `0006`, sin cambio de datos: no hay grupos todavía. Render la aplica en el despliegue.
  - Límite conocido, resuelto el 14/11/2026: restablecer y reactivar bloqueaban la cuenta con `FOR UPDATE`. Si el
    Administrador restablecía al Gerente justo cuando el Gerente corregía, desde su cuenta, la cuenta de otro rol
    vinculada a la suya, PostgreSQL abortaba una de las dos operaciones (un error 500). El mismo ciclo aparecía
    cuando dos Administradores se modificaban entre sí. Con los cuatro bloqueos anteriores pasados a
    `FOR NO KEY UPDATE` ya no pasa. Ninguno necesitaba `FOR UPDATE`: ese modo solo protege contra un `DELETE` o
    contra el cambio de una columna con índice único, y las cuentas no se borran (baja lógica, y la auditoría las
    protege con `PROTECT`) ni cambian de `id`; la exclusión entre nuestras operaciones sigue igual, porque
    `FOR NO KEY UPDATE` choca consigo mismo. Lo verifican `test_d32_restablecer_al_gerente_mientras_modifica_su_cuenta_vinculada_no_hace_deadlock`
    y `test_d32_dos_administradores_que_se_modifican_entre_si_a_la_vez_no_hacen_deadlock`. Antes del cambio
    fallaban con `OperationalError: deadlock detected`; después pasan. Con todos los bloqueos devueltos en memoria a
    `FOR UPDATE` vuelven a fallar las dos y las otras ocho pasan; sin los bloqueos de los invariantes o sin ningún
    bloqueo, fallan las pruebas de SEG-15 y de las cuentas vinculadas, como antes.
  - Residual: si un `UPDATE` cambia el email (columna con índice único), PostgreSQL toma `FOR UPDATE` en esa
    sentencia, se haya bloqueado antes como se haya bloqueado. Dos Administradores que se cambian el email
    mutuamente en el mismo instante todavía pueden terminar en deadlock. Es mucho menos probable que el caso
    resuelto y no se cubre.
  - Las pruebas que simulan un cambio entre la verificación y el bloqueo lo hacen dentro de la transacción del
    servicio y se deshace con el rechazo; solo verifican qué responde el servicio. Que dos operaciones reales se
    esperen entre sí lo prueban las de concurrencia (`core/tests/concurrencia.py`).
  - Todas las pruebas de concurrencia fijan el orden de las dos operaciones con el parámetro `primera` de
    `correr_a_la_vez` (14/11/2026), que es obligatorio: la otra operación arranca recién cuando la primera se
    detuvo, y la primera se libera cuando la otra terminó o quedó esperando un bloqueo (se pregunta a
    `pg_stat_activity`), no después de un tiempo fijo. Antes, las ocho pruebas de SEG-15 y de las cuentas
    vinculadas esperaban una ventana fija de 1,5 s, y el experimento del 14/11/2026 mostró que en una máquina
    lenta (la segunda operación arrancando 3 s tarde) seis de ellas podían pasar sin probar nada y dos fallaban
    aunque todo estuviera bien. Con `primera` quedaron igual de sensibles en una máquina lenta que en una normal:
    cada una falla cuando falta su protección (matriz de 11 modos, a velocidad normal y con 3 s de demora, sin
    diferencias) y las 13 pasaron cinco corridas seguidas. La ventana fija se eliminó de `correr_a_la_vez`.
  - `correr_a_la_vez` suma `detener_antes_de=(objeto, "nombre")`, que detiene a `primera` justo ANTES de llamar
    a esa función en lugar de después de registrar la auditoría. Hace falta para probar el orden de los
    bloqueos, que el punto de parada por defecto no puede reproducir (ahí la primera ya tomó todos sus
    bloqueos). Lo usan tres pruebas nuevas: `test_d32_restablecer_y_vincular_a_la_vez_respetan_el_orden_de_bloqueos`,
    única que detecta que falte el bloqueo del grupo en `restablecer_contrasena` (sin él, deadlock), y
    `test_d32_restablecer_cuyo_grupo_cambia_mientras_espera_da_cambio_simultaneo` y
    `test_d32_reactivar_cuyo_grupo_cambia_mientras_espera_da_cambio_simultaneo`, que prueban `cuida_grupo`: el
    servicio se detiene antes de su bloqueo previo, ya leída la cuenta, y la otra operación cambia el grupo de la
    cuenta y confirma. Sin `cuida_grupo`, el restablecimiento o la reactivación siguen con un grupo que no
    bloquearon: las dos pruebas fallan.
  - `test_seg11_restablecer_y_vincular_a_la_vez_no_dejan_la_temporal_en_el_grupo` corre los dos órdenes (con
    `subTest`), para que se ejecuten las dos ramas de su final.
  - Quien tiene un grupo suma una consulta por pantalla (el menú de cuenta); sin grupo no consulta la base.
  - El tope de intentos de identificación, para el inicio de sesión y el vínculo juntos, queda para la tarea 09:
    necesita una decisión nueva que reemplace a SEG-05 y D-19, y un modelo o una caché para contar.
  - El DER se actualiza después, a partir del código.
- Estado: vigente; D-36 reemplaza el formato del detalle de la auditoría de este punto; actualizada el 14/11/2026 (sin aviso de éxito al cambiar de cuenta; todos los bloqueos pasan a
  `FOR NO KEY UPDATE` y el límite conocido queda resuelto)

## D-33 — Envío de correo: Gmail por SMTP y una sola fuente de verdad (tarea 08)

- Fecha: 16/11/2026
- Decidió: Lautaro Fernández (en el pedido de la tarea 08)
- Antes: SEG-12 pide que la recuperación por correo solo esté disponible si el envío de correo está configurado
  (variables de entorno del servidor de correo definidas), y `docs/estado.md` dejaba abierto el proveedor. Render pasó
  al plan Starter el 11/11/2026. El proyecto no tiene dominio propio.
- Decisión:
  - Proveedor: Gmail por SMTP (`smtp.gmail.com`, puerto 587, TLS) con la cuenta `infoponia.notificaciones@gmail.com`,
    exclusiva para el correo del sistema y separada de la que administra Neon, Render y Cloudflare. Se autentica con una
    contraseña de aplicación de Google, guardada solo en las variables de entorno de Render (`EMAIL_HOST_USER` y
    `EMAIL_HOST_PASSWORD`); nunca en el código ni en el repositorio.
  - `DEFAULT_FROM_EMAIL = "InfoPonia <infoponia.notificaciones@gmail.com>"` y `EMAIL_TIMEOUT = 10`.
  - Una sola fuente de verdad: `settings.CORREO_CONFIGURADO`, verdadera si están definidas `EMAIL_HOST_USER` y
    `EMAIL_HOST_PASSWORD`, o si se usa la consola. Las reglas están en `config/correo.py` (`correo_configurado` y
    `correo_por_consola`), funciones puras que reciben el entorno y `DEBUG`; `settings.py` las llama una vez al arrancar.
  - Desarrollo sin credenciales: con `DEBUG` encendido y `CORREO_CONSOLA=1`, el correo va al backend de consola y cuenta
    como configurado. Con `DEBUG` apagado, `CORREO_CONSOLA` se ignora.
  - `PASSWORD_RESET_TIMEOUT = 3600` (SEG-12: el enlace vence a la hora).
  - El código lee `settings.CORREO_CONFIGURADO` en cada pedido (no una copia), así que las pruebas lo cambian con
    `override_settings` y no hace falta recargar la configuración.
  - Las pruebas no usan credenciales: el ejecutor de pruebas de Django fuerza el backend en memoria y el correo se lee en
    `mail.outbox`.
- Por qué:
  - Gmail, porque el proyecto no tiene dominio propio y los servicios de correo transaccional (Resend y similares) exigen
    verificar uno. Una cuenta exclusiva para notificaciones limita el daño si se filtra su contraseña de aplicación: no
    da acceso a la infraestructura. Una contraseña de aplicación se revoca sin cambiar la de la cuenta.
  - Gmail exige que el remitente sea la cuenta autenticada; por eso el `From` es esa cuenta.
  - El límite de espera es obligatorio: gunicorn corta a los 30 s (D-29), y un servidor SMTP colgado dejaría al worker
    esperando hasta que lo corten. Con 10 s el pedido falla antes, se registra y la persona recibe la respuesta de siempre.
  - Una sola fuente de verdad evita que el inicio de sesión, el pedido y la confirmación discrepen sobre si la
    recuperación está disponible (precondición a y regla 5 de USR-RCP-CTR).
  - La consola solo con `DEBUG`: en producción imprimiría en los registros del servidor los enlaces de recuperación, y
    quien los lea podría usarlos para entrar a una cuenta.
  - Funciones puras en `config/correo.py`: se prueban sin recargar `settings.py` ni tocar el entorno real.
- Fuentes: `docs/casos_de_uso/usuarios.md` (USR-RCP-CTR precondición a y regla 5; SEG-12); D-29 (tiempo de gunicorn);
  documentación de Django 5.2 (envío de correo y `PASSWORD_RESET_TIMEOUT`).
- Consecuencias:
  - Antes de que la recuperación funcione en producción hay que cargar `EMAIL_HOST_USER` y `EMAIL_HOST_PASSWORD` en
    Render. Mientras falten, el inicio de sesión muestra el aviso de siempre y el sistema funciona igual.
  - Gmail limita los envíos diarios de una cuenta. Sin un tope de pedidos (tarea 09), alguien podría agotarlo. Ver D-34.
  - `.env.example` suma `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` y `CORREO_CONSOLA`, sin valores.
  - Sin dependencias nuevas ni migraciones.
- Estado: vigente

## D-34 — Recuperar contraseña por correo: cómo se implementa (tarea 08)

- Fecha: 16/11/2026
- Decidió: Lautaro Fernández (en el pedido de la tarea 08 y durante su planificación; el punto sobre el Administrador, a
  propuesta de Claude)
- Antes: USR-RCP-CTR y SEG-12 fijan que el enlace es de un solo uso, vence a la hora, la respuesta es siempre la misma y
  se cierran las sesiones, pero no cómo se genera y valida el enlace, qué pasa con dos pedidos simultáneos con el mismo
  enlace, qué pantallas hay ni a quién alcanza. La tarea pedía que «el superusuario sin rol no recupera por acá»; como todo
  Administrador es un superusuario sin rol (D-10), eso lo dejaba afuera, y USR-RCP-CTR lo nombra como actor.
- Decisión:
  - Quién recupera: toda cuenta activa, de cualquier rol y también las de los Administradores (USR-RCP-CTR: «Todos los
    roles y el Administrador»). El email se busca sin distinguir mayúsculas (SEG-01).
  - Token: `default_token_generator` de Django. Firma el id, el resumen de la contraseña, el último inicio de sesión, el
    email y la hora; vence a `PASSWORD_RESET_TIMEOUT` (D-33). Los servicios están en `core/servicios.py`:
    `pedir_recuperacion`, `cuenta_del_enlace` y `confirmar_recuperacion`.
  - Pedido (`pedir_recuperacion`): no escribe en la base ni audita; no usa `transaction.atomic()` a propósito (solo lee y
    envía). No devuelve nada, así que la vista no puede distinguir si la cuenta existía. A una cuenta inactiva o inexistente
    no se le envía nada. Si el envío falla, `logger.exception` con el id de la cuenta (nunca el enlace ni el token) y la
    misma respuesta. Sin el correo configurado, `ValidationError` con el código `correo_no_configurado`.
  - Confirmación (`confirmar_recuperacion`), dentro de `transaction.atomic()`: bloquea la cuenta con
    `select_for_update(no_key=True)` (D-32) y DESPUÉS de bloquear vuelve a validar que el token siga siendo válido y que
    la cuenta siga activa. Luego valida la política (SEG-03, con `validate_password`; la contraseña vacía se controla
    aparte, con el mismo mensaje que `cambiar_contrasena`), guarda la contraseña, deja `fecha_contrasena_temporal` en
    `None`, no toca el grupo de cuentas vinculadas y audita con `RECUPERACION_CONTRASENA` en la misma transacción: el
    usuario y el rol registrados son los de la cuenta afectada; el detalle solo lleva `era_temporal`.
  - Un enlace usado, vencido, alterado o de una cuenta que pasó a inactiva da siempre el mismo error
    (`enlace_invalido`) y la misma pantalla, con la opción de pedir otro.
  - Una cuenta con contraseña temporal, aunque esté vencida, puede recuperar (postcondición b).
  - Las sesiones abiertas de la cuenta se cierran por el mismo mecanismo que el restablecimiento y la baja: al cambiar el
    resumen de la contraseña, Django las invalida. No hay código extra.
  - Pantallas (`recuperar-contrasena/`): pedido, «Revisá tu correo», entrada del enlace, contraseña nueva y «Enlace no
    válido». Todas exentas del login obligatorio, sin caché y solo para quien no tiene sesión (con sesión redirigen al
    inicio). La entrada del enlace guarda el token en la sesión y redirige a una URL sin él; la contraseña nueva se envía
    a esa URL sin token. La ruta del enlace existe en un solo lugar: `core/urls.py` (`core:recuperacion_enlace`); el
    servicio la arma con `reverse` y la base absoluta la pone `construir_url` (`request.build_absolute_uri`).
  - Al confirmar no se inicia sesión: se lleva al inicio de sesión con el aviso «Contraseña actualizada. Ingresá con la
    nueva contraseña.» (D-29).
  - Sin correo configurado: el inicio de sesión no ofrece «¿Olvidaste tu contraseña?» y muestra el aviso de siempre; las
    pantallas de recuperación muestran que hay que pedirle a quien gestiona la cuenta que la restablezca, sin formulario.
  - Correo en texto plano y en español: saludo con el nombre, el enlace, que vence en una hora y sirve una sola vez, y que
    si no lo pidió lo ignore.
  - Desvíos del prototipo (`vRecoverSent`, `vLinkBad`, `vReset`): (1) «Revisá tu correo» no repite el email escrito;
    (2) una sola pantalla de enlace no válido, sin distinguir «ya usado» de «vencido»; (3) la lista de requisitos de la
    contraseña no incluye «distinta de la actual». Tampoco va el recuadro «Solo prototipo» (D-24).
  - Pruebas: `core/tests/test_usr_rcp_ctr.py`, con servicio, vistas, configuración (`test_d33_`) y una de concurrencia con
    dos hilos.
- Por qué:
  - Apoyarse en el generador de tokens de Django evita inventar un esquema de firma. Como el token incluye el resumen de la
    contraseña, el enlace deja de servir en cuanto se usa, sin guardar nada en la base: por eso el pedido no escribe.
  - Se revalida el token después de bloquear porque validarlo solo en la vista no alcanza para que sea de un solo uso: dos
    pedidos simultáneos con el mismo enlace pasan los dos la validación y los dos cambiarían la contraseña. Con la cuenta
    bloqueada, el segundo espera, relee la fila con el resumen nuevo y el token ya no vale. Evidencia (16/11/2026): la
    prueba `test_d34_dos_confirmaciones_con_el_mismo_enlace_cambian_una_sola_vez` pasa tres corridas seguidas; con la
    validación movida antes del bloqueo (en memoria, sin tocar el código) falla con `2 != 1`: las dos confirmaciones
    tuvieron éxito.
  - `FOR NO KEY UPDATE` por la razón de D-32: la auditoría referencia a la cuenta afectada, que acá es también quien
    «actúa», y su clave foránea toma `FOR KEY SHARE` sobre esa fila.
  - El mismo mensaje y la misma redirección en todos los casos (regla 2) para no revelar qué cuentas existen. La causa de
    un enlace inválido tampoco se revela, y el token de Django no permite distinguir «usado» de «vencido».
  - El token sale de la URL antes de mostrar el formulario para que no quede en el historial, en la cabecera Referer ni
    en los registros del servidor mientras la persona escribe su contraseña nueva. Es la técnica de
    `PasswordResetConfirmView`. Se hicieron vistas propias, y no una subclase de la de Django, porque la subclase obligaba a
    apoyarse en detalles internos (la clave de sesión y su `form_valid`) y a validar dos veces con reglas distintas; las
    vistas solo orquestan y la lógica está en el servicio, como pide `CLAUDE.md`.
  - No se inicia sesión sola: tener acceso al correo demuestra el control de la cuenta para elegir la contraseña, pero
    entrar sin escribirla agregaría una vía que USR-RCP-CTR no pide.
  - «Revisá tu correo» no muestra el email porque, tras la redirección, habría que guardarlo en la sesión (una escritura en
    la base, y el pedido no escribe) o ponerlo en la URL (queda en el historial y en los registros).
  - El Administrador recupera igual que los demás porque el caso de uso lo incluye entre sus actores, y la fuente de mayor
    peso entre las que hablan del tema es el caso de uso. Sin esto, perder su contraseña lo obligaría a pedirle a otro
    Administrador que se la restablezca, o a usar la consola de Render.
  - El servicio de pedido no usa `atomic()` porque no escribe, y el envío por SMTP (hasta 10 s) no debe mantener abierta
    una transacción (D-14: las notificaciones van fuera de la transacción).
- Fuentes: `docs/casos_de_uso/usuarios.md` (USR-RCP-CTR, reglas 1 a 5 y postcondiciones a a d; SEG-02, SEG-03, SEG-12,
  SEG-14 y SEG-16; «Pantallas» y «Elementos del prototipo que no van en el sistema»); prototipo
  `docs/prototipos/cuentas_y_seguridad.html` (`vRecover`, `vRecoverSent`, `vReset`, `vLinkBad`); D-10, D-17, D-22, D-27, D-29,
  D-32 y D-33; `CLAUDE.md` (servicios, bloqueos y tests); código de `django.contrib.auth.tokens` y de
  `django.contrib.auth.views` (Django 5.2).
- Consecuencias:
  - Sin migraciones: `RECUPERACION_CONTRASENA` ya estaba en la lista de acciones de la auditoría (D-22).
  - Límite conocido: cuando la cuenta existe, el pedido tarda más (el envío por SMTP lleva uno o dos segundos). Medir ese
    tiempo permite saber si un email tiene cuenta, aunque el texto y la redirección sean iguales. Se puede evaluar en la
    tarea 09 enviar el correo en segundo plano.
  - Límite conocido: no hay tope de pedidos (tarea 09, junto con el de SEG-05 y D-19): alguien podría hacer que el
    sistema le envíe muchos correos a una persona o agotar el límite diario de Gmail.
  - Por cómo arma el token Django, un enlace deja de servir si la cuenta inicia sesión o cambia el email o la contraseña.
    Pedir un enlace nuevo no anula el anterior, pero los dos dejan de servir apenas se usa uno.
  - `build_absolute_uri` toma el host del pedido; lo protege `ALLOWED_HOSTS`. Hay que confirmar que `DJANGO_ALLOWED_HOSTS`
    en Render no tenga `*`. Detrás del proxy de Render el enlace sale con https gracias a `SECURE_PROXY_SSL_HEADER`; la
    prueba manda `Host` y `X-Forwarded-Proto`, como el proxy (sin `Host`, el cliente de prueba hace que Django agregue el
    puerto 80 al armar el host).
  - Con contraseña temporal y sesión iniciada, las pantallas de recuperación terminan en «Elegí tu contraseña», por el
    middleware de SEG-04. Es lo esperado.
  - El texto de `docs/casos_de_uso/usuarios.md` («Lo que queda para más adelante») todavía dice que el proveedor de correo
    no está decidido: es copia del documento de Drive y hay que actualizarlo allá.
- Estado: vigente; D-35 suma `invitacion_pendiente` al detalle de la auditoría de la recuperación y comparte con la invitación el servicio que elige la contraseña con un enlace; D-36 reemplaza el formato de ese detalle (ahora dentro de `datos`)

## D-35 — Invitación por correo como forma de primer acceso (tarea 08b)

- Fecha: 17/11/2026
- Decidió: Lautaro Fernández (en el pedido de la tarea 08b y durante su planificación, a propuesta de Claude: la acción de
  auditoría propia, el servicio compartido con la recuperación y el texto «Restablecer acceso»)
- Antes: D-18 y D-27 hacían que el alta, el restablecimiento y la reactivación siempre generaran una contraseña temporal,
  que quien gestiona la cuenta le pasa a la persona por otro medio. Con el correo funcionando (D-33, D-34), los casos de uso
  (USR-ALT-USR 0.4, USR-MOD-USR 0.5, USR-CNS-USR 0.4, SEG-04 y SEG-20) agregan una invitación por correo como forma de primer
  acceso, y la dejan como opción por defecto.
- Decisión:
  - Estado de la cuenta: la invitación pendiente es una contraseña no utilizable (`set_unusable_password`) más
    `Usuario.fecha_invitacion` (nulo si no hay invitación), análogo a `fecha_contrasena_temporal`. Una cuenta nunca tiene las
    dos fechas a la vez: lo cuidan `asignar_invitacion` y `asignar_contrasena_temporal` y lo respalda la restricción de la
    base `invitacion_o_temporal`. La invitación vence a los 7 días exactos (`invitacion_vencida`), como la temporal.
    Migración `0007`: el campo, la restricción y la acción de auditoría nueva.
  - Token: `core/tokens.py`, `GeneradorInvitacion`, una subclase de `PasswordResetTokenGenerator` con otra `key_salt` (un
    token de recuperación no sirve como invitación ni al revés), con la fecha de la invitación dentro de la firma (cada
    invitación nueva anula la anterior) y vencimiento de 7 días. `PASSWORD_RESET_TIMEOUT` (la hora de la recuperación) no
    cambia.
  - Elegir la contraseña con un enlace: un solo servicio compartido, `_elegir_contrasena_con_enlace` (`atomic`,
    `select_for_update(no_key=True)`, revalidar el enlace y que la cuenta siga activa DESPUÉS de bloquear, SEG-03,
    auditoría con la cuenta afectada como usuario, y deja la cuenta sin invitación ni temporal). Lo usan
    `confirmar_recuperacion` (D-34) y `confirmar_invitacion`. La aceptación se audita con una acción propia,
    `aceptacion_invitacion`, y no exige el correo configurado: aceptar no envía nada.
  - Forma de acceso: `alta_usuario`, `restablecer_contrasena` y `reactivar_usuario` reciben `acceso` («invitacion» o
    «temporal») y `construir_url`, y devuelven un `ResultadoAcceso` (forma, contraseña temporal si la hay, y si la invitación
    salió). La elige quien gestiona la cuenta con un radio (invitación marcada por defecto) en el formulario de alta y en la
    ventana de restablecer y reactivar. Sin `CORREO_CONFIGURADO` el radio no se muestra y la forma es la temporal; el
    servicio rechaza igual una invitación enviada a mano, en el campo `acceso`, con el código `correo_no_configurado`. Con
    el correo configurado el campo es obligatorio (`acceso_invalido`). La auditoría guarda la forma en `acceso`, sin
    contraseñas ni el token.
  - Envío: la escritura y la auditoría van dentro de la transacción; el envío, DESPUÉS de confirmarla (D-14). Si falla, la
    cuenta queda creada o restablecida con la invitación pendiente, `logger.exception` con el id de la cuenta y sin el
    enlace (`_enviar_correo`, compartido con la recuperación), y el resultado vuelve a la vista, que avisa de la falla con un
    aviso de error y ofrece «Restablecer acceso» (regla 11 de USR-ALT-USR).
  - Restablecer o reactivar con invitación: contraseña no utilizable (la anterior deja de servir y se cierran las sesiones),
    `fecha_contrasena_temporal` en `None`, `fecha_invitacion` ahora, y salida del grupo (SEG-11), igual que con la temporal.
    Restablecer con una invitación pendiente invalida el enlace anterior (regla 11 de USR-MOD-USR: reenviar es restablecer).
    Restablecer con una temporal le quita la invitación pendiente.
  - Consulta (USR-CNS-USR regla 3): estado visible «Invitación pendiente» o «Invitación vencida» en la lista y la ficha, con
    el tratamiento de la contraseña temporal sin cambiar o vencida.
  - Pantallas del enlace (`invitacion/<uidb64>/<token>/`): la misma técnica que la recuperación (token a la sesión con su
    propia clave, URL del formulario sin token, una sola pantalla «Invitación no válida», solo sin sesión). Texto: «Elegí tu
    contraseña para empezar a usar InfoPonia». Al terminar lleva al inicio de sesión con el aviso «Contraseña guardada.
    Ingresá con tu nueva contraseña.», sin iniciar sesión. La pantalla de enlace no válido ofrece «Pedir un enlace nuevo»
    (la recuperación, SEG-20: el resultado es el mismo) solo si el correo está configurado.
  - Correo de la invitación en texto plano: saludo con el nombre, que se le creó una cuenta con su rol, el enlace, que vence
    en 7 días y sirve una sola vez, y que si no la esperaba lo ignore.
  - Resultado: «Le enviamos una invitación a <email>. Vence en 7 días. Si no le llega, que revise la carpeta de Spam, o
    restablecé el acceso con una contraseña temporal.» (pantalla «Cuenta creada» y ventana de restablecer y reactivar). La
    pantalla «Revisá tu correo» de la recuperación también sugiere la carpeta de Spam.
  - Los textos pasan de «Restablecer contraseña» a «Restablecer acceso» («¿Restablecer el acceso?», «Acceso restablecido»),
    porque el botón puede mandar una invitación y el caso de uso habla de restablecer el acceso.
  - Vincular cuentas (USR-VNC-CTA): una cuenta con invitación pendiente no se vincula. No hizo falta cambiar el servicio:
    `vincular_cuenta` verifica la contraseña de la otra cuenta (`check_password`) antes de bloquear, y una contraseña no
    utilizable no verifica nunca, así que da `no_se_pudo_vincular`. Lo cubre una prueba.
  - Pruebas: con `manage.py test`, `CORREO_CONFIGURADO` arranca en `False` (`config/settings.py`), para que den lo mismo en
    cada máquina y en el CI; las que necesitan el correo lo encienden con `override_settings`.
- Por qué:
  - La invitación evita que quien gestiona la cuenta conozca y tenga que transmitir una contraseña, aunque sea temporal:
    la persona elige la suya desde el primer momento. Es el mismo principio de D-18, llevado un paso más lejos.
  - Una contraseña no utilizable más una fecha, y no un campo de estado, porque Django ya entiende la contraseña no
    utilizable: la cuenta no puede identificarse (SEG-06) y las sesiones abiertas se cierran, sin tocar el backend ni el
    inicio de sesión. La fecha permite decir desde cuándo y cuándo vence, y entra en la firma del token.
  - La restricción `invitacion_o_temporal` respalda la regla aunque un servicio nuevo olvide limpiar una de las dos fechas;
    dos estados de primer acceso a la vez no tienen sentido.
  - Un generador propio, y no otro `PASSWORD_RESET_TIMEOUT`, porque ese ajuste es global: cambiarlo a 7 días alargaría
    también el plazo de la recuperación, que SEG-12 fija en una hora. Con otra `key_salt`, un enlace de un tipo no sirve para
    el otro, aunque el usuario y la hora coincidan. El costo es repetir las pocas líneas de `check_token` de Django 5.2, que
    no ofrece otro gancho para el plazo (se lee `settings.PASSWORD_RESET_TIMEOUT` dentro del método); hay que revisarlas si se
    actualiza Django, y las pruebas de 7 días ± 1 s y de los tokens cruzados lo detectarían.
  - Un servicio compartido para elegir la contraseña con un enlace, y no dos copias, porque la regla delicada es la
    revalidación después del bloqueo (D-34): con dos copias, una corrección en una podría no llegar a la otra. Las dos
    pruebas de concurrencia (recuperación e invitación) ejercitan la misma función. Evidencia (17/11/2026): con la
    revalidación movida antes del bloqueo (en memoria, sin tocar el código) fallan la de la invitación y la de la
    recuperación (`2 != 1` las dos) y la de «restablecer mientras se acepta»; con el código real, las tres pasan.
  - La aceptación tiene acción de auditoría propia porque se distingue de una recuperación o de un cambio voluntario sin leer
    el detalle: es la primera vez que la persona elige su contraseña, y es el dato que más interesa encontrar.
  - El envío va fuera de la transacción por D-14: un servidor SMTP lento (hasta 10 s, D-33) no puede mantener tomados los
    bloqueos del alta o del restablecimiento (D-30, D-32), ni un correo puede salir para una operación que después se
    deshizo. El costo es que el correo puede fallar con la cuenta ya creada; por eso la regla 11 y el aviso con la salida.
  - El radio se oculta sin correo, y además el servicio lo rechaza, porque la pantalla es una ayuda y la regla la aplica el
    servidor (como la política de contraseñas, D-34). Con el correo configurado el campo es obligatorio para que nadie
    reciba una invitación sin haberla elegido: la invitación viene marcada, pero siempre es una decisión visible.
  - «Restablecer acceso» porque el botón ya no siempre genera una contraseña: un texto que dijera «contraseña» sugeriría una
    temporal que quizá no existe.
  - Aceptar sin exigir el correo configurado, porque la precondición de SEG-12 existe para no ofrecer lo que no se puede
    enviar; aceptar una invitación ya enviada no envía nada, y quien la recibió no tiene por qué perder el acceso si el
    correo deja de estar configurado después.
- Fuentes: `docs/casos_de_uso/usuarios.md` (USR-ALT-USR 0.4, reglas 4, 10 y 11 y postcondiciones a, c y e; USR-MOD-USR 0.5,
  objetivo, postcondiciones b y c y reglas 4, 6 y 11; USR-CNS-USR 0.4, regla 3; SEG-04, SEG-06, SEG-11, SEG-12 y SEG-20);
  D-14, D-18, D-22, D-27, D-30, D-32, D-33 y D-34; código de `django.contrib.auth.tokens` (Django 5.2).
- Consecuencias:
  - Reemplaza en parte a D-27 (la contraseña temporal ya no es la única forma de primer acceso) y a D-18 (su primer punto,
    «el Sistema genera una contraseña temporal al dar de alta, restablecer o reactivar», es ahora una de dos opciones; el
    resto de D-18 vale para la temporal). D-34 suma `invitacion_pendiente` al detalle de la auditoría de la recuperación.
  - Migración `0007`: no hay cuentas con invitación hoy, sin cambio de datos. Para quien tenga la base de pruebas con
    `--keepdb`, hay que recrearla una vez (ver `CLAUDE.md`).
  - Para que la invitación funcione en producción hay que tener el correo configurado en Render (D-33). Mientras no esté,
    todo sigue como antes: solo la contraseña temporal.
  - Límite conocido: si el envío falla, la persona no tiene cómo entrar hasta que quien gestiona la cuenta restablezca el
    acceso; la pantalla lo avisa y ofrece la salida. Si la persona usa «¿Olvidaste tu contraseña?» antes de aceptar la
    invitación, el enlace de recuperación la deja en el mismo estado final (SEG-20), y el enlace de invitación deja de servir.
  - Límite conocido: no hay tope de pedidos de la recuperación (tarea 09), y reenviar invitaciones no tiene tope propio: lo
    hace quien gestiona la cuenta, con sesión.
  - Los textos de los casos de uso que cambian con la invitación (SEG-11, SEG-14 y la precondición b de USR-VNC-CTA) ya
    están actualizados en «CU extendidos» (Drive) y en la copia de `docs/casos_de_uso/usuarios.md`.
- Estado: vigente; D-36 reemplaza el formato del detalle de la auditoría de este punto (la forma de acceso pasa a `datos`)

## D-36 — Formato obligatorio del detalle de la auditoría y consulta del registro (tarea AUD-CNS-REG)

- Fecha: 17/11/2026
- Decidió: (completar con el nombre de quien aprobó) en el pedido de la tarea AUD-CNS-REG, en la revisión de las pruebas y
  de la migración, a propuesta de Claude: guardar el rol en los afectados, el filtro de la ficha, la clasificación de
  las acciones y los índices
- Antes: cada servicio armaba el detalle de `RegistroAuditoria` a su manera (D-22, D-27, D-28, D-32, D-34, D-35): la
  modificación guardaba `{campo: [antes, después]}`; la baja y la reactivación, `{"estado": [antes, después]}`; el alta,
  solo los valores nuevos; la vinculación, ids de grupo. Nada obligaba a guardar el valor anterior, y una lista no se
  distinguía de un «antes y después». Los afectados eran `{"modelo", "id"}`: para mostrar a quién se refería un registro
  había que buscar la cuenta, que pudo haber cambiado de nombre. Se descartó (opción A) agregar las columnas
  `valor_anterior` y `valor_nuevo`: obligan a una fila por campo y rompen «una acción = un registro». AUD-CNS-REG
  (versión 0.1, `docs/casos_de_uso/auditoria.md`) pide ver, de cada dato que cambió, su valor anterior y su valor nuevo, y
  las referencias con el texto que tenían en el momento del cambio.
- Decisión:
  - **Formato del detalle (opción B).** El detalle tiene dos claves opcionales y ninguna más.
    `"cambios": {campo: {"antes": valor, "despues": valor}}` para todo dato que cambió (en un alta, «antes» es
    `null`). `"datos": {clave: valor}` para el contexto que no tiene antes y después (forma de acceso, si la contraseña
    era temporal, grupo vinculado, etc.).
  - **Referencias.** Una referencia a otro objeto (cuenta, grupo y, más adelante, invernadero, insumo...) se guarda
    como `{"id": ..., "texto": "<lo que se veía en ese momento>"}` (`referencia(objeto)` en `core/models.py`;
    `referencia_a_grupo(id)` para un grupo que ya no existe, como el que acaba de disolverse).
  - **Validación en `RegistroAuditoria.objects.registrar`.** Además de rechazar las contraseñas (D-22), rechaza con
    `ValueError`: una clave de primer nivel distinta de «cambios» y «datos»; un cambio que no sea exactamente
    `{"antes", "despues"}`; un cambio con «antes» igual a «despues»; «cambios» o «datos» que no sean diccionarios; y
    un diccionario dentro de un valor que no sea una referencia con exactamente `{"id", "texto"}`. Esto es lo que hace
    obligatorio el valor anterior. Se aceptan nulos, booleanos, números, textos, referencias y listas de esos.
  - **Afectados con texto y rol.** Cada afectado se guarda como `{"modelo", "id", "texto"}`; las cuentas, siempre como
    `core.usuario`, suman `"rol"` (el que devuelve `rol_de`: «administrador» para el Administrador). El texto de una
    cuenta es «Nombre Apellido (email)», o solo el email si no tiene nombre (`texto_de`). El rol de una cuenta no cambia
    (MD-55), así que guardarlo es seguro y permite buscar por rol con una consulta de contención (ver abajo).
  - **Quién actuó.** No se agrega ninguna columna: la pantalla muestra el nombre y el email actuales de la cuenta, con
    el rol que tenía en ese momento (ya guardado desde D-22), y «InfoPonia» si no hubo cuenta. Un cambio de nombre o de
    email de quien actuó queda en su propio registro de modificación.
  - **Detalle nuevo de cada servicio.** Alta: `cambios` con rol, nombre, apellido, email y, si se cargó, teléfono
    (todos con «antes» nulo) y `datos: {acceso}`. Modificación: `cambios` con los campos que cambiaron. Baja: `cambios`
    con el estado. Reactivación: `cambios` con el estado y, si salió de un grupo, `grupo` (de la referencia al grupo a
    nulo), y `datos: {acceso}`. Restablecimiento: `cambios.grupo` si salió de un grupo y `datos: {acceso}`. Cambio de
    contraseña, recuperación y aceptación de invitación: `datos` con `era_temporal` (y `invitacion_pendiente`).
    Vinculación: `datos: {grupo, grupo_unido}` (referencias, la segunda nula si no se unieron grupos). Desvinculación:
    `datos: {grupo, disuelto}`. En la vinculación y la desvinculación el grupo va en «datos» y no en «cambios» porque
    cambian varias cuentas a la vez; las que cambiaron ya figuran entre los afectados.
  - **Textos legibles.** `RegistroAuditoria.ETIQUETAS` da el nombre visible de cada campo y de cada dato, y
    `VALORES_VISIBLES` el de los valores con lista cerrada (rol, estado, forma de acceso); las acciones ya tenían sus
    `choices`. `filas_de_cambios()` y `filas_de_datos()` arman las filas en texto: nulo como «—», booleano como «Sí» o
    «No», referencia con su texto guardado, y una clave desconocida tal cual. El orden de las filas es el de `ETIQUETAS`,
    no el del JSON, porque `jsonb` no conserva el orden de las claves.
  - **Migración de datos `0008_formato_detalle_auditoria`: la única excepción deliberada a D-22.** Convierte los
    registros que ya existen al formato nuevo. D-22 dice que al registro solo se le agregan filas; la migración modifica
    filas ya guardadas. Se hace una sola vez y a propósito, para unificar el formato antes de que exista una pantalla que
    lo lea: con dos formatos, la pantalla (y todo módulo que la use) tendría que entender los dos para siempre. Corre
    sobre el modelo histórico, que no tiene el `save` ni el manager de la app (los que impiden modificar), con
    `filter(pk=...).update(...)`. Es idempotente (un detalle ya convertido, con claves dentro de «cambios» y «datos», y un
    afectado que ya tiene «texto» se dejan como están) y tiene `reverse_code`, que deja el formato viejo. Falla con el id
    del registro, sin cambiar nada, si encuentra un detalle viejo que no reconoce, en vez de descartar datos sin avisar.
    **No llama a ningún código de la app**: el texto «Grupo N» y el texto de las cuentas están copiados dentro de la
    migración, para que produzca siempre el mismo resultado aunque la app cambie después.
  - **Mapeo de la migración.** Alta `{rol, email, nombre, apellido[, acceso]}` → `cambios` (con «antes» nulo) y
    `datos.acceso`. Modificación `{campo: [a, d]}` → `cambios`. Baja y reactivación `{estado: [a, d]}` → `cambios.estado`;
    `sale_del_grupo: g` → `cambios.grupo` (de `ref(g)` a nulo); `acceso` → `datos`. Restablecimiento: lo mismo sin estado.
    Cambio de contraseña, recuperación y aceptación → `datos`. Vinculación y desvinculación → `datos` con referencias.
    Afectados → suman texto y rol de la cuenta. Una cuenta que ya no exista (no debería pasar: no se borran) queda con
    «Cuenta <id>» y sin rol.
  - **Alcance (regla 1 de AUD-CNS-REG, MD-58).** `RegistroAuditoria.objects.visibles_para(actor)` es el único lugar del
    alcance (como `en_alcance_de` para las cuentas). El Administrador activo ve todo. El Gerente activo ve los registros
    de los módulos de negocio y los de cuentas en los que actuó, o fue afectada, una cuenta de rol operativo (Agrónomo,
    Capataz, Vendedor, Transportista, Técnico); no ve los que solo involucran a Administradores o a Gerentes. Cualquier
    otro actor, o una cuenta inactiva: ninguno.
  - **Clasificación de las acciones.** Un registro es «de cuentas» por su acción, no por sus afectados:
    `ACCIONES_DE_CUENTAS` (hoy las 10 acciones) y `ACCIONES_DE_NEGOCIO` (hoy vacío), en `core/models.py`. `visibles_para`
    decide por `ACCIONES_DE_CUENTAS`; lo que no está ahí es de negocio y el Gerente lo ve. **Agregar una acción a
    `RegistroAuditoria.Accion` obliga a clasificarla**: la prueba
    `test_d36_cada_accion_esta_clasificada_en_cuentas_o_en_negocio` exige que cada acción esté en uno de los dos conjuntos
    y en uno solo, y que ninguno nombre acciones que no existen.
  - **Consulta.** `consultar_auditoria(actor, desde, hasta, quien_actuo, accion, afectado_id, cuenta_id)` en
    `core/servicios.py`: precondición de Gerente o Administrador activos (SEG-13, `PermissionDenied`); los filtros se
    combinan; del más reciente al más viejo (`-fecha_hora, -id`). Rango de fechas inclusive en la zona horaria del sistema
    (`>= desde 00:00` y `< hasta + 1 día 00:00`). `quien_actuo` es un id o «infoponia» (registros sin cuenta). No abre
    `atomic`, no escribe y no audita (regla 6, SEG-14). `obtener_registro` da 404 si el registro no existe y 403 si
    está fuera del alcance (D-28).
  - **Filtrar por una cuenta (D-28 aplicado a la auditoría).** El Administrador puede filtrar por cualquier cuenta. El
    Gerente, por cualquiera menos las de Administrador (también por la suya y por las de Gerentes anteriores, que aparecen
    en registros que él ve, por ejemplo un Gerente anterior que modificó a un Capataz); filtrar por una de Administrador
    da 403 y una cuenta que no existe, 404. El filtro nunca amplía el alcance: se aplica sobre `visibles_para`.
  - **Filtro combinado de la ficha.** La regla 2 nombra cuatro filtros (fechas, cuenta que actuó, acción, cuenta afectada).
    La regla 7 pide que «Ver auditoría» abra la lista «con el filtro de esa cuenta ya aplicado»; se agregó `cuenta`
    («actuó o fue afectada»), que la regla 2 no nombra, porque la historia de una cuenta incluye lo que hizo y lo que le
    hicieron. En pantalla es una etiqueta «Registros de <cuenta> (actuó o fue afectada)» con «Quitar filtro». Desde ahí se
    puede pasar a los filtros de la regla 2.
  - **Búsqueda en el JSON.** Los afectados se buscan con `afectados__contains` (el operador `@>` de `jsonb`): una cuenta
    por su id, o «alguna cuenta de rol operativo» con `[{"modelo": "core.usuario", "rol": r}]`. Índices
    (`0009_indices_auditoria`): un GIN sobre `afectados` con `jsonb_path_ops` (sirve a `@>`, más chico y rápido que
    `jsonb_ops`, y alcanza porque no se usa otro operador) y un btree sobre `(-fecha_hora, -id)` (el orden de cada
    página y el rango de fechas). El filtro por la cuenta que actuó ya tiene el índice de su clave foránea.
  - **Pantallas.** «Auditoría» en el menú del Gerente y del Administrador; lista paginada de 25 con los filtros
    (desplegables propios, D-24, y avisos de D-29), detalle con la tabla Campo / Antes / Después y los datos de contexto
    aparte, y «Ver auditoría» en la ficha de una cuenta, solo si quien mira puede abrirla (`puede_ver_auditoria_de`: ningún
    enlace lleva a un 403, D-30). Solo aceptan GET (un POST, PUT o DELETE da 405): ninguna pantalla modifica ni borra
    (regla 4). Con un filtro mal formado (una fecha inválida, «desde» posterior a «hasta», una cuenta que no es un número),
    el aviso va dentro del fragmento de la tabla y la lista sale vacía; así se ve también con HTMX, que solo reemplaza la
    tabla. El detalle vuelve a la lista con los mismos filtros y la misma página.
- Por qué:
  - Un formato único, validado al escribir, hace imposible olvidar el valor anterior: un servicio nuevo que lo omita
    falla en su primera prueba, no meses después al abrir un registro. Con «cambios» y «datos» separados, la pantalla
    sabe qué mostrar como tabla Campo / Antes / Después y qué como contexto, sin adivinar si una lista es «antes y
    después» o una lista de ids. Una fila por acción (y no por campo, opción A) conserva que una acción es un registro.
  - Las referencias con su texto del momento hacen que el registro siga diciendo lo que era aunque el objeto cambie o
    se disuelva (un grupo ya no existe, una cuenta cambió de nombre): es el pedido de la regla 3.
  - El rol dentro de cada afectado evita cruzar el JSON con la tabla de cuentas en cada consulta: la búsqueda del Gerente
    es una contención sobre `jsonb`, que un índice GIN resuelve, y se escribe sin SQL a mano. Como el rol de una cuenta
    no cambia (MD-55), el dato guardado no se desactualiza.
  - Se decide por la acción y no por los afectados porque una acción de un módulo de negocio que afecte solo a la cuenta del
    Gerente (o a un Administrador) se ocultaría por error si «de cuentas» se dedujera de quién aparece. Con un conjunto
    explícito, y una prueba que obliga a clasificar cada acción nueva, un módulo nuevo no puede quedar oculto por
    olvido ni hay que tocar `visibles_para`.
  - La migración es la única excepción a D-22 porque la alternativa, dejar los registros viejos en su formato, obligaría a
    mantener para siempre un lector de dos formatos, y hoy todavía no hay pantallas que dependan de ninguno. Es un
    cambio de formato, no de contenido: no se agrega ni se quita ningún hecho auditado salvo lo que el formato viejo no
    tenía. Va con su vuelta, es idempotente y falla en voz alta, para que no destruya información sin avisar. No llama
    a código de la app porque el texto «Grupo N» o el de una cuenta pueden cambiar mañana, y una migración que ya se
    aplicó (o que se aplica en un despliegue nuevo) tiene que dar siempre lo mismo.
  - `jsonb_path_ops` y no el GIN por defecto porque la tabla solo crece y la consulta solo usa `@>`; el btree sirve al
    orden de cada página, que es la consulta más repetida. Costo: un poco más de trabajo en cada alta de auditoría,
    que son pocas por operación.
  - El Gerente filtra por las cuentas de Gerente y no por las de Administrador porque las primeras aparecen en registros
    que él ve y las segundas nunca; con el mismo criterio de D-28 que en Cuentas (403 fuera del alcance, 404 si no
    existe), un filtro no puede ser una forma de averiguar qué hicieron los Administradores.
  - 25 por página: cada fila ocupa dos o tres renglones (quién, acción y afectados), así que una página entra en una o dos
    pantallas sin recorrer una lista enorme, y la consulta paginada con el orden de `-fecha_hora, -id` usa el índice.
  - Los errores de filtro dentro del fragmento porque HTMX solo reemplaza la tabla: un error junto a cada campo, fuera del
    fragmento, no se vería al filtrar.
- Fuentes: `docs/casos_de_uso/auditoria.md` (AUD-CNS-REG 0.1, reglas 1 a 7); `docs/casos_de_uso/usuarios.md` (SEG-13,
  SEG-14, USR-CNS-USR); D-22, D-24, D-27, D-28, D-29, D-30, D-32, D-34 y D-35; MD-55 y MD-58; documentación de
  Django 5.2 (`GinIndex` en `django.contrib.postgres.indexes`, opción `opclasses` de `Index`, `contains` de
  `JSONField`).
- Consecuencias:
  - Todo servicio nuevo que audite escribe su detalle con «cambios» y «datos» y las referencias con `referencia()`; si no,
    `registrar` lanza `ValueError` en su primera prueba. Todo campo auditado nuevo debería sumar su nombre visible a
    `ETIQUETAS` (si no, la pantalla muestra la clave tal cual). Toda acción nueva se clasifica en
    `ACCIONES_DE_CUENTAS` o en `ACCIONES_DE_NEGOCIO` (una prueba lo exige). Los módulos de negocio guardan sus afectados
    con texto y reutilizan `referencia()`.
  - Migraciones `0008` (datos, más un `AlterField` que solo cambia la ayuda del campo `afectados`) y `0009` (índices). Para
    quien use `--keepdb`, hay que recrear la base de pruebas una vez (`CLAUDE.md`). La prueba de punta a punta de la
    migración desarma y rearma el esquema de la base de pruebas: lleva `@tag("migracion")` y en local se excluye junto con
    las de concurrencia (`CLAUDE.md`); el CI la corre.
  - **Antes de mergear a main**, como Render corre `migrate` en cada despliegue y la 0008 falla si encuentra un detalle
    viejo que no reconoce, conviene probarla contra una copia de la base de producción o revisar los detalles de la
    tabla `core_registroauditoria` de Neon.
  - Límites conocidos: el texto y el rol de los afectados de los registros anteriores a esta tarea son los de las
    cuentas AL MOMENTO DE MIGRAR, no los que tenían cuando se hizo el registro (el formato viejo no los guardó); las altas
    anteriores no guardaron el teléfono; la vuelta de la 0008 pierde el teléfono de las altas nuevas y el texto y el rol de
    los afectados. Los índices se verificaron en el SQL de la migración (`sqlmigrate`) y funcionan, pero no se midió con
    `EXPLAIN` sobre una tabla grande: con pocas filas PostgreSQL recorre la tabla entera igual.
  - `django.contrib.postgres` no está en `INSTALLED_APPS` y no hace falta: la documentación de Django lo pide solo para
    `OpClass`, y `GinIndex` con `opclasses` se importa de `django.contrib.postgres.indexes` y migra sin él (verificado al
    correr las migraciones).
  - El menú del Administrador (D-30) pasa a tener dos entradas, «Cuentas» y «Auditoría». Trabajo futuro, fuera de esta
    tarea: exportar los registros filtrados a CSV.
- Estado: vigente; completa a D-22 (el modelo de solo agregar y la lista de acciones) y reemplaza el formato del detalle
  de D-27, D-28, D-32, D-34 y D-35
