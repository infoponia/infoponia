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
- Estado: vigente

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

