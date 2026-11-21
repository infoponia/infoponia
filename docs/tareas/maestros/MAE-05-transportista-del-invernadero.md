# MAE-05 · Transportista del invernadero: «Logística», agregar, trasladar y quitar

Estado: pendiente | App: maestros (y dos puntos de extensión en core) | Rama: feature/mae-05-transportista-del-invernadero | Ronda: —
(corrección previa al módulo comercial)

Depende de: MAE-01b (invernadero), MAE-02b (Inicio del Gerente y puntos de `core/extensiones.py`) y NOT-01 (notificaciones). Las tres
están hechas. No depende de ninguna tarea de la ronda «Producción 1»: se puede hacer en paralelo con INV-02 (ver «Límites»,
migraciones).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por
paso. Si algo que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Hasta hoy el Transportista se daba de alta sin invernadero: R155 quedó «pendiente de decidir»
(`docs/disparadores.md`, «Cuando exista Invernadero», punto 2). D-55 lo decide:
- un Transportista pertenece a **un invernadero o a ninguno**;
- se asigna **desde la ficha del invernadero**, en un bloque nuevo «Logística» debajo de «Equipo»;
- no se quita ni se traslada si está en ruta o tiene entregas a realizar. Eso lo informa `comercial` por un punto de
  extensión: mientras `comercial` no exista, no bloquea nada.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-MOD-INV | Modificar Invernadero (0.2) | docs/casos_de_uso/maestros/invernaderos.md | Solo lo marcado *(MAE-05)*: postcondición g y reglas 8 a 11. Las reglas 9 y 10 van por punto de extensión (las conecta `comercial`) |
| PROD-ALT-INV | Alta Invernadero (0.2) | docs/casos_de_uso/maestros/invernaderos.md | Postcondiciones c y e y regla 6 *(MAE-05)*: el formulario de alta no cambia; ver «Cómo se aplica» de la regla 6 |
| PROD-BAJ-INV | Baja Invernadero | docs/casos_de_uso/maestros/invernaderos.md | Precondición g, reglas 2 y 3: los transportistas activos impiden la baja |
| PROD-CNS-INV | Consultar Invernadero (0.3) | docs/casos_de_uso/maestros/invernaderos.md | Regla 3 (bloque «Logística»; el vehículo, por punto de extensión) y regla 5 (transportista sin invernadero en «Personal por asignar») |
| USR-ALT-USR, USR-MOD-USR | Alta y Modificar Usuario | docs/casos_de_uso/usuarios.md | Sin código nuevo: el invernadero nunca se programó en la cuenta. Solo se corrige el comentario de `core/templates/core/usuarios/alta.html` |
| USR-CNS-USR, USR-GST-PRF | Consultar Usuario y Mi Perfil | docs/casos_de_uso/usuarios.md | Regla 3 y regla 1: el invernadero del Transportista, solo para consultar, por punto de extensión de `core` |
| USR-BAJ-USR | Baja Usuario | docs/casos_de_uso/usuarios.md | Precondición d nueva (no está en ruta): solo el punto de extensión de `core`; lo conecta `comercial` |

## Leer

- Casos de uso: los dos extractos de la tabla. De `invernaderos.md`, los cuatro casos completos, con sus «Cómo se aplica». De
  `usuarios.md`, las secciones USR-ALT-USR, USR-MOD-USR, USR-BAJ-USR, USR-CNS-USR y USR-GST-PRF.
- Modelo: docs/modelo/maestros.md — Invernadero («Asociaciones», R155; «Reglas que lo tocan», la regla 4 de 8.4) y
  «`TransportistaInvernadero`».
- Decisiones: D-55 (la de esta tarea), D-22, D-28, D-29, D-30, D-36, D-37, D-39, D-40, D-42, D-43, D-47.
- API: docs/api/extensiones_de_maestros.md, sección «Transportistas» (implementala tal cual); docs/api/notificaciones.md.
- Patrones: docs/patrones/bloqueos.md (sección «Invernadero»), docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md.
- Pantallas: `docs/prototipos/produccion/logistica_transportista.html` (archivo chico: se puede leer entero). Funciones:
  - `logistica`: el bloque de la ficha. Usá la versión «sin comercial»; la «con comercial» es lo que mostrará el registrante.
  - `ventanaAgregar` y `ventanaQuitar`.
  - `personalPorAsignar`, `fichaDeCuenta` y `bajaDeCuentaEnRuta`.
  Es solo una guía visual: lo que difiera de los casos de uso lo decide el caso de uso (L7).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `maestros/models.py` (Invernadero) y `maestros/extensiones.py`;
  - de `maestros/servicios/invernaderos.py`: `bloquear_invernadero_activo`, `_bloquear_invernadero`, `_exigir_gerente`,
    `_actor_sigue_activo`, `FaltaConfirmarPersonal`, `impedimentos_para_baja`, `baja_invernadero`, `seccion_de_inicio`,
    `invernaderos_con_personal_por_asignar`;
  - `maestros/views.py` (`invernadero`, `_contexto_de_la_ficha` e `invernadero_baja`, que es el modelo de ventana con HTMX);
  - las plantillas `maestros/templates/maestros/invernaderos/ficha.html`, `_ventana_baja.html` y `_inicio_personal.html`;
  - `maestros/apps.py`, `core/extensiones.py`, `core/servicios.py` (`baja_usuario`, `_bloquear_cuenta_en_alcance`) y
    `core/notificaciones.py`;
  - las vistas y plantillas de la ficha de la cuenta, de «Mi perfil» y de la ventana de baja de cuenta
    (`core/views.py`: `_render_mi_perfil` y `_gestionar_cuenta`; `core/templates/core/usuarios/ficha.html`,
    `core/templates/core/mi_perfil.html` y `core/templates/core/usuarios/_ventana_confirmar.html`).

## Límites

- Crea modelos: `maestros.TransportistaInvernadero` → revisá `docs/disparadores.md`: cierra «Cuando exista Invernadero», punto 2.
- Migraciones: una sola, nueva, en `maestros`, de esquema: `00NN_transportista_invernadero`, con el número libre en `main` al
  abrir el PR. INV-03 también agrega una migración en `maestros`: si chocan los números, seguí
  `docs/patrones/trabajo_en_paralelo.md`. **Ninguna en `core`**: se usa la acción de auditoría que ya existe,
  `modificacion_invernadero`.
- Permitido fuera de la app:
  - `core/extensiones.py`: solo los dos puntos nuevos, `registrar_impedimento_de_baja_de_cuenta` y `registrar_datos_de_cuenta`,
    con sus `namedtuple`;
  - `core/servicios.py`: solo `baja_usuario`, para pedir los impedimentos, y una función de lectura `impedimentos_de_baja`
    para la ventana;
  - `core/views.py` y las plantillas de la ficha de la cuenta, de «Mi perfil» y de la ventana de baja: solo mostrar los datos y
    los impedimentos;
  - el comentario de `core/templates/core/usuarios/alta.html`;
  - las pruebas de `core` que hagan falta;
  - al cerrar (M3), los textos de `docs/disparadores.md` y `docs/tareas/README.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance:
  - `Entrega`, `Vehiculo`, la ruta y COM-ASG-TRP (`comercial`). Esta tarea solo deja los puntos de extensión y los prueba con
    registrantes falsos.
  - Agregar transportistas desde el formulario de alta o de modificación del invernadero: se agregan desde «Logística»
    («Cómo se aplica» de la regla 6 de PROD-ALT-INV).
  - Cambiar el alta de la cuenta: nunca pidió invernadero.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelo y migración.** `TransportistaInvernadero` según `docs/modelo/maestros.md`:
   - `OneToOneField` a `core.Transportista` y `ForeignKey` a `Invernadero`, las dos con `PROTECT`;
   - `desde`, sin valor por defecto, porque lo fija el servicio;
   - `__str__`, y `verbose_name` en castellano;
   - registro de solo lectura en el admin, como los demás.
   En `Invernadero`, un método `transportistas()` que devuelve los `core.Transportista` vinculados, ordenados por apellido y
   nombre sin distinguir mayúsculas, con una sola consulta.
   Pruebas, en `maestros/tests/test_transportista_invernadero_modelo.py`:
   - un Transportista no puede tener dos filas (`IntegrityError`);
   - no se puede borrar un invernadero ni una cuenta que tengan fila (`ProtectedError`).
2. **Puntos de extensión.**
   - En `maestros/extensiones.py`: `Logistica`, `registrar_impedimento_de_transportista`, `impedimentos_de_transportista`,
     `registrar_logistica_de_transportista` (un solo registrante) y `logistica_de`, tal como dice la API.
   - En `core/extensiones.py`: `ImpedimentoDeCuenta`, `DatoDeCuenta`, `registrar_impedimento_de_baja_de_cuenta`,
     `impedimentos_de_baja_de_cuenta`, `registrar_datos_de_cuenta` y `datos_de_cuenta`, idempotentes como los demás de ese archivo.
   Pruebas: `maestros/tests/test_extensiones_transportistas.py` y `core/tests/test_extensiones_cuenta.py`. Sin registrantes,
   resultado neutro; con registrantes falsos, se juntan todos; un segundo registrante de logística lanza `RuntimeError`.
3. **Servicios**, en un archivo nuevo `maestros/servicios/transportistas.py`, para que `invernaderos.py` no siga creciendo:
   - **`candidatos(actor, invernadero_id)`** (regla 8): los Transportistas **activos** que no trabajan para ese invernadero, cada
     uno con su invernadero actual o `None`. Sin invernadero primero, después por invernadero y por nombre. Gerente activo;
     invernadero activo. Solo lectura.
   - **`agregar_transportista(actor, invernadero_id, transportista_id, *, traslado_confirmado=False)`** (regla 8, postcondición g):
     - **Bloqueos, en este orden** (D-40: las cuentas primero):
       1. que quien actúa siga activo;
       2. la cuenta del Transportista (`FOR NO KEY UPDATE`);
       3. los invernaderos que intervienen (el de destino y, si lo hay, el de origen), en orden de id. El de destino con
          `bloquear_invernadero_activo`, porque agregar a un Transportista activo crea algo que impide la baja (contrato de
          `maestros/extensiones.py`).
       Después, releer la fila de `TransportistaInvernadero`.
     - **Rechazos**, con `ValidationError` y su código:
       - Transportista inactivo: `transportista_inactivo`;
       - ya trabaja para ese invernadero: `ya_pertenece`;
       - destino inactivo: `invernadero_inactivo`.
     - **Traslado** (tiene otro invernadero): si `traslado_confirmado` es falso, lanzar `FaltaConfirmarTraslado` con el
       invernadero de origen, como hace `FaltaConfirmarPersonal`, y no cambiar nada. Si es verdadero, pedir
       `impedimentos_de_transportista`: si hay alguno, rechazar con sus códigos y no cambiar nada (reglas 9 y 10). Si no, actualizar
       `invernadero` y `desde`.
     - **Sin invernadero:** crear la fila.
     - **Notificación** al Transportista (`notificar_a_varios(..., excluir=actor)`), con los textos de abajo.
     - **Auditoría:** un `modificacion_invernadero` por cada invernadero que cambió (el de destino y, en un traslado, también el
       de origen). Afectados: el invernadero y la cuenta. `cambios` con
       `{"transportistas": {"antes": [referencias], "despues": [referencias]}}` (D-36, `referencia()`).
   - **`quitar_transportista(actor, invernadero_id, transportista_id)`** (reglas 9 y 10, postcondición g):
     - los mismos bloqueos (la cuenta y, después, el invernadero);
     - rechazos: el invernadero está inactivo (`invernadero_inactivo`, regla 5); el Transportista no trabaja para él
       (`no_pertenece`); hay impedimentos (sus códigos), y en ese caso no se cambia nada;
     - si no, se borra la fila, se notifica y se audita. Un Transportista **inactivo** se puede quitar: los impedimentos se
       piden igual.
   - **`impedimentos_para_quitar(actor, invernadero_id, transportista_id)`:** solo lectura, para la ventana.
   - **Textos de las notificaciones** (voseo, como el resto):

     | Caso | Título | Detalle |
     |---|---|---|
     | Agregado | «Trabajás para {invernadero}» | «Desde ahora podés recibir entregas de {invernadero}.» |
     | Trasladado | «Te pasaron a {destino}» | «Dejás de trabajar para {origen}. Desde ahora podés recibir entregas de {destino}.» |
     | Quitado | «Ya no trabajás para {invernadero}» | «No vas a recibir entregas hasta que te agreguen a otro invernadero.» |

   Pruebas, en `maestros/tests/test_prod_mod_inv_transportistas.py`: una por regla (8 a 11) y por postcondición (g), con
   registrantes falsos para la 9 y la 10. Además:
   - el traslado sin confirmar no cambia nada;
   - un traslado deja dos registros de auditoría;
   - la notificación tiene el texto correcto;
   - ni el Agrónomo ni un Gerente inactivo pueden hacerlo;
   - de la regla 11: agregar no toca nada más.
   Concurrencia (`@tag("concurrencia")`), en `test_transportistas_concurrencia.py`:
   - dos `agregar_transportista` simultáneos del mismo Transportista a dos invernaderos: queda una sola fila y el otro recibe un
     rechazo claro (nunca un 500 por `IntegrityError`);
   - agregar contra `baja_invernadero` del destino: o la baja ve al Transportista y se rechaza, o el agregado ve el invernadero
     inactivo.
4. **Baja del invernadero** (precondición g, reglas 2 y 3 de PROD-BAJ-INV). Hay que sumar a lo que juntan `impedimentos_para_baja`
   y `baja_invernadero` un impedimento propio de `maestros`:
   - código `transportistas_activos`;
   - texto: «Tiene {N} transportista(s) activo(s): {nombres}.»;
   - cómo resolverlo: «Trasladalos a otro invernadero o quitalos desde “Logística”.»
   Los inactivos no cuentan (D-39). Va junto con los de los registrantes, sin quedarse con el primero. Pruebas, en
   `test_prod_baj_inv.py`:
   - con un Transportista activo se rechaza;
   - con uno inactivo, no;
   - la ventana lo muestra.
   Quitá el comentario «espera a R155» del docstring y de la prueba.
5. **Personal por asignar** (regla 5 de PROD-CNS-INV). `seccion_de_inicio` suma al contexto los
   `transportistas_sin_invernadero`: los activos sin fila, ordenados por apellido y nombre.
   - En `_inicio_personal.html`, una fila por cada uno con el ícono `info`, el nombre, «Transportista sin invernadero: no recibe
     entregas.» y «Asignar», que lleva a la lista de invernaderos.
   - El contador de la cabecera pasa a decir «N pendientes»: invernaderos más transportistas.
   - «Todos los invernaderos activos tienen su personal asignado» se muestra solo si no hay ninguna de las dos cosas.
   - Un invernadero sin transportistas **no** aparece (decisión D de D-55).
   Pruebas, en `test_prod_cns_inv.py`: aparece el activo sin invernadero; el inactivo no aparece; el que tiene invernadero, tampoco.
6. **Ficha del invernadero.** La tarjeta «Logística», entre «Ubicación y Equipo» y «Capacidad» (`logistica` del prototipo, versión
   «sin comercial»), en una plantilla nueva `maestros/invernaderos/_logistica.html`:
   - cada transportista con su nombre y la marca «Inactivo» si corresponde;
   - para el Gerente, «Agregar transportista» y «Quitar» por fila, solo si `"modificar" in acciones` (D-30);
   - si `logistica_de(...)` no es `None`, las tres columnas del registrante: vehículo o «Sin vehículo», situación y entregas a
     realizar;
   - sin transportistas, el texto del prototipo.
   El Agrónomo ve la misma tarjeta sin botones. Las ventanas son como la de baja: con HTMX, con la respuesta completa si no hay
   JavaScript y con «Volver». Las vistas, en `maestros/views.py`, con `rol_requerido(GERENTE)`, `never_cache` y
   `vary_on_headers("HX-Request")`:
   - `transportista_agregar`, en `<int:invernadero_id>/transportistas/agregar/`. GET muestra los candidatos. POST con un
     candidato:
     - si es un traslado sin confirmar, vuelve a mostrar la ventana con el aviso y «Confirmar traslado»;
     - si hay impedimentos, los muestra (con «Ver sus entregas» si el registrante dio `url_entregas`) y no ofrece confirmar;
     - si sale bien, vuelve a la ficha con un aviso breve (D-29): «{Nombre} ahora trabaja para {invernadero}.» o «{Nombre} pasó
       de {origen} a {invernadero}.».
   - `transportista_quitar`, en `<int:invernadero_id>/transportistas/<int:transportista_id>/quitar/`. GET muestra la
     confirmación o los impedimentos; POST quita y vuelve a la ficha con «{Nombre} ya no trabaja para {invernadero}.».
   Pruebas, en `maestros/tests/test_transportistas_vistas.py`:
   - permisos: el Agrónomo recibe 403 en las rutas y no ve los botones; un invernadero inactivo no muestra botones;
   - el flujo con HTMX y sin él;
   - los errores en la ventana;
   - sin consultas por fila en la ficha (`assertNumQueries` con tres transportistas).
7. **La cuenta del Transportista.** `maestros` registra, en `MaestrosConfig.ready()`, `datos_de_cuenta`:
   - para un Transportista, `DatoDeCuenta("Invernadero", nombre o "Sin invernadero", nota)`, con la nota «Se asigna desde la
     ficha del invernadero, en “Logística”.»;
   - para los demás roles, nada.
   `core` muestra esos datos en la ficha de la cuenta y en «Mi perfil» (sin la nota). `baja_usuario`:
   - junta `impedimentos_de_baja_de_cuenta(cuenta)` después de bloquear la cuenta y antes de cambiar nada; si hay alguno, lanza
     `ValidationError` con sus códigos;
   - la ventana de baja los muestra y no ofrece confirmar (`bajaDeCuentaEnRuta`).
   En `alta.html`, el comentario deja de decir «invernadero del Transportista (para más adelante)».
   Pruebas: en `core/tests/test_usr_baj_usr.py`, la baja se rechaza con un impedimento falso y no cambia nada; en
   `test_usr_cns_usr.py` y `test_usr_gst_prf.py`, el dato aparece con un registrante falso. En `maestros`, una prueba de que
   el Transportista con invernadero ve su nombre y el que no tiene, «Sin invernadero».
8. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
   - tachar el punto 2 de «Cuando exista Invernadero» en `docs/disparadores.md`;
   - marcar MAE-05 en `docs/tareas/README.md`;
   - pasar D-55 a «vigente» si el estudiante la validó.
   Lo que haya quedado distinto de lo escrito va a `docs/temas_abiertos.md`.

Si el tiempo apremia, no se recortan:
- los bloqueos;
- la restricción única;
- el impedimento de la baja del invernadero.

Se puede dejar para una tarea chica aparte, anotada como disparador, el paso 7 (la cuenta): no lo usa nadie hasta que exista
`comercial`.

## Hecho cuando

- Un Transportista se agrega, se traslada y se quita desde «Logística», con su notificación y su auditoría, y nunca queda en dos
  invernaderos (lo garantiza la base de datos).
- Los transportistas activos impiden la baja del invernadero; los inactivos, no.
- «Personal por asignar» muestra a los Transportistas activos sin invernadero.
- Los cuatro puntos de extensión coinciden con `docs/api/extensiones_de_maestros.md`, sección «Transportistas», y se prueban con
  registrantes falsos. Sin registrantes, nada se bloquea y no aparecen las columnas de `comercial`.
- Comando de pruebas:
  python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test maestros --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva: `python manage.py migrate`. Cuentas: Gerente, un Agrónomo a cargo de un invernadero y tres Transportistas
(uno lo vas a dar de baja). Dos invernaderos activos: «Norte» y «Sur».

1. Panel de control del Gerente: los tres Transportistas aparecen en «Personal por asignar» como «Transportista sin
   invernadero», con «Asignar».
2. Ficha de «Norte» → «Logística»: «El invernadero no tiene transportistas…». «Agregar transportista» lista a los tres con «Sin
   invernadero». Agregar a uno: aviso breve, aparece en la tabla, desaparece de «Personal por asignar», y en «Auditoría» hay un
   `modificacion_invernadero` de «Norte». Entrar con ese Transportista: tiene la notificación.
3. Ficha de «Sur» → «Agregar transportista»: el de «Norte» aparece con «Trabaja para Norte». Elegirlo: la ventana avisa del
   traslado y pide «Confirmar traslado». Al confirmar pasa a «Sur», y «Auditoría» tiene dos registros, uno por invernadero.
4. Quitarlo de «Sur»: queda sin invernadero y vuelve a «Personal por asignar».
5. Agregar otro a «Norte» y dar de baja «Norte»: se rechaza con «Tiene 1 transportista activo…». Dar de baja la cuenta de ese
   Transportista y volver a intentar la baja de «Norte»: ahora el Transportista no la impide. Si no hay otro impedimento, se da de
   baja. Reactivar «Norte» para seguir.
6. Ficha de la cuenta del Transportista (Gerente) y su «Mi perfil»: muestran «Invernadero» con el nombre o «Sin invernadero».
7. Con el Agrónomo: ve «Logística» sin botones; las URL de agregar y quitar dan 403.
8. Sin JavaScript, los pasos 2 a 4 funcionan igual: cada ventana es una página.
9. Con dos sesiones, agregar el mismo Transportista a dos invernaderos a la vez. Si no se puede, alcanza con la prueba de
   concurrencia: uno lo agrega y el otro ve el motivo, sin error 500.
10. Después del merge: verificar en el log de Render que se aplicó la migración nueva.

## Cierre (la completa Claude Code al cerrar)
