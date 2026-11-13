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
- Estado: vigente

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
- Estado: vigente

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
- Estado: vigente

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
- Estado: vigente (reemplaza en parte a D-15)

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
    hacia abajo. En pantallas de menos de 760px ocupan el ancho con 12px de margen.
  - Al aparecer se deslizan desde la derecha con fundido (250ms, ease-out); al irse, por tiempo o por la
    cruz, se desvanecen hacia la derecha (200ms) y recién después se quitan de la página. Con
    `prefers-reduced-motion` no hay desplazamiento ni barra animada: solo aparecen y desaparecen.
  - Sin JavaScript queda el aviso fijo en la página, como respaldo. Los errores que se muestran debajo de
    los campos de un formulario no son avisos y no cambian.
  - El botón secundario (`.btn-ghost`) usa borde y texto en el verde primario sobre fondo blanco: 6,54:1
    (el borde gris anterior tenía 1,37:1); en el hover, verde oscuro sobre verde claro (7,29:1). Los
    botones que son enlaces no se subrayan. Todos los botones muestran el foco al navegar con Tab: un
    borde de 2px en el verde primario (`:focus-visible`), separado 2px del botón.
  - Los archivos estáticos propios (hoja de estilos y scripts) se piden con `{% static_v %}`, que agrega la
    fecha del archivo a la URL, porque `runserver` los sirve sin `Cache-Control`.
- Por qué: el botón secundario tiene que verse en una tarjeta blanca y cumplir el contraste mínimo de texto
  (4,5:1) y de componentes (3:1). Un aviso que se integra con el sistema (tarjeta, colores de estado)
  no parece un cuerpo extraño y no empuja ni tapa el contenido; 10 segundos dan tiempo de leerlo y la
  cruz deja cerrarlo antes. El `role="status"` hace que se anuncie sin quitarle el foco a nadie, y el
  respaldo fijo evita perder el mensaje si el JavaScript no corre. Los colores de texto, cruz e ícono
  sobre el blanco de la tarjeta miden 18,47:1 (texto), 5,82:1 (cruz), 5,36:1 (ícono de éxito) y 6,25:1
  (ícono de error). Sin foco visible, quien navega con teclado no sabe dónde está. Sin `Cache-Control`, el
  navegador guarda por su cuenta los archivos que solo traen `Last-Modified` y no vuelve a pedirlos: un
  cambio de JavaScript no llegaba y los avisos de la 04b parecían no desaparecer; con la fecha del archivo
  en la URL, cada cambio es una URL nueva.
- Fuentes: D-24 y D-25; WCAG 2.x: criterios 1.4.3 (contraste mínimo), 1.4.11 (contraste de componentes),
  2.4.7 (foco visible) y 4.1.3 (mensajes de estado); revisión a mano de la tarea 04b.
- Consecuencias: toda pantalla nueva usa estas convenciones. Las verifican las pruebas
  `test_d29_...` de `core/tests/test_usr_ini_ses.py`; el temporizador, la cruz y las animaciones son
  JavaScript y se prueban a mano. En la tarea 09 se evalúa reemplazar `static_v` por
  `ManifestStaticFilesStorage` de WhiteNoise (`whitenoise.storage`) en producción, que pone un hash en el
  nombre de cada archivo.
- Estado: vigente

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
- Estado: vigente; D-31 cierra su consecuencia sobre la contraseña propia del Administrador

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
