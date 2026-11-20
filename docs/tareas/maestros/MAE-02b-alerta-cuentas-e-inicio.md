# MAE-02b · Alerta: baja y reactivación de cuenta, Inicio del Gerente y consulta (CU-46)

Estado: hecha, en revisión (sin el paso 4: pasa a MAE-02c) | App: maestros | Rama: feature/mae-02-alerta

Depende de: MAE-02a (si no está hecha, frená)

## Leer

- Casos de uso: docs/casos_de_uso/usuarios.md — USR-BAJ-USR: post e y regla 4; USR-MOD-USR: la reactivación.
  docs/casos_de_uso/maestros/invernaderos.md — PROD-CNS-INV: regla 5.
  CU-46 (Consultar Alerta), que no tiene copia en el repo; texto del documento de alto nivel:
  > «Actores: Agrónomo o superior. Objetivo: consultar el listado de alertas en estado “activa”, buscar una en particular
  > y acceder a su información completa. Postcondición: no se produjeron cambios en el sistema».
- Modelo: docs/modelo/maestros.md — Alerta (regla 7 de 8.18; reglas 3 y 4 de 8.22, MD-60 y MD-61)
- Decisiones: D-22, D-30, D-32, D-36, D-37, D-38, D-40, D-41
- Patrones: docs/patrones/bloqueos.md, docs/patrones/auditoria.md
- Pantallas: docs/prototipos/produccion/datos_maestros_y_produccion.html — `personalCard` y `alertas()` (solo guía visual)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md

## Orden de los pasos (para poder recortar lo último)

1. Puntos de extensión de `core` (`core/extensiones.py`) y la baja y reactivación de cuenta.
2. El Inicio del Gerente («Personal por asignar», regla 5 de PROD-CNS-INV).
3. `abrir_alerta` (regla 7 de 8.18).
4. **Al final, la pantalla de CU-46.** Si falta tiempo, se deja para otra tarea y nace como disparador.

## Supuestos de CU-46 (el caso de uso de alto nivel no los precisa)

- El alcance es `Alerta.objects.para(usuario)`.
- Muestra solo las alertas activas.
- Filtra por invernadero y por tipo.
- Abrir el detalle llama a `abrir_alerta`.
- Funciona sin JavaScript (HTMX solo reemplaza la tabla).
- Vive en `maestros`.
- El panel de CU-41 de IoT reutiliza la consulta (se documenta en docs/api/alertas.md).
- Que abrir la alerta la marque «leída» contradice la postcondición de CU-46: va al cierre como pendiente de pendientes_CU.

## Límites

- Crea modelos: ninguno
- Permitido fuera de la app: core/extensiones.py (nuevo); core/servicios.py (`baja_usuario` y `reactivar_usuario`);
  core/views.py (`inicio` y la ventana de baja de cuenta); core/templates/core/inicio.html y la plantilla de la ventana
  de baja; core/templatetags/iconos.py (solo si hace falta un ícono, copiado del prototipo); docs/api/alertas.md.
  La entrada «Alertas» del menú se registra desde `MaestrosConfig.ready()`.
- Migraciones: ninguna
- Dependencias nuevas: ninguna
- Fuera de alcance: notificaciones y campana (tarea aparte en core, D-42)

## Hecho cuando

- La baja de una cuenta con invernaderos a cargo crea las alertas `sin_{rol}` y, si es un Agrónomo, pasa sus alertas
  activas al Gerente (regla 4 de 8.22, MD-61); la ventana informa los invernaderos a cargo (regla 4 de USR-BAJ-USR).
- Reactivar la cuenta resuelve la alerta de su rol y, si es un Agrónomo, aplica D4.
- El Inicio del Gerente lista los invernaderos con personal por asignar, con el acceso a modificar.
- `abrir_alerta` y la pantalla de CU-46.
- Pruebas: core/tests/test_usr_baj_usr.py, core/tests/test_usr_mod_usr.py, maestros/tests/test_usr_baj_usr.py,
  maestros/tests/test_usr_mod_usr.py, maestros/tests/test_prod_cns_inv.py, maestros/tests/test_alerta.py y
  maestros/tests/test_cns_alr.py (CnsAlrServicioTests y CnsAlrVistaTests; el código es una propuesta).
- Pruebas de concurrencia P5, P6 y P7 (plan de MAE-02).
- Comando de pruebas:
  python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test maestros core --keepdb --tag concurrencia

## Decisiones de la tarea (D-43)

- **D8:** al reactivar una cuenta de Agrónomo se aplica D4 de D-41, completo: sus invernaderos a cargo le pasan las alertas
  `AGRONOMO_O_GERENTE` que habían ido al Gerente por falta de Agrónomo (y el Gerente deja de recibirlas) y le suman las
  `AGRONOMO_Y_GERENTE` (el Gerente sigue); las `GERENTE` no se tocan. La baja hacia el Gerente es MD-61, no D8.
- Solo se sincroniza la alerta «sin {rol}» del rol de la cuenta (`roles`, API nueva de `sincronizar_alertas_de_personal`).
- `abrir_alerta` con un id inexistente da `Http404` (D-28); para quien no la recibe, `PermissionDenied`.
- P5, P6 y P7 (el plan de MAE-02 no está en el repo): P5, baja del Capataz mientras se reactiva su invernadero; P6, baja del
  Agrónomo mientras se crea una alerta `AGRONOMO_O_GERENTE`; P7, lo mismo con la reactivación.
- Se trabajó en `feature/mae-02-alerta`, sin rama nueva. El paso 4 (pantalla de CU-46) quedó fuera por decisión del equipo.

## Verificación a mano

Con el entorno virtual activo y la base local (`python manage.py runserver`, con `DEBUG` encendido para usar `/admin/`). **No hay
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

## Cierre (completado el 19/11/2026)

**Qué se hizo**

- `core/extensiones.py` (nuevo): cuatro puntos de extensión (efectos de la baja y de la reactivación de una cuenta,
  asignaciones de la cuenta y secciones del Inicio), idempotentes (regla A4 de D-37).
- `core`: `baja_usuario` y `reactivar_usuario` los aplican después de bloquear las cuentas y suman los afectados y los `datos`
  a la auditoría (`_auditar_con_salida_del_grupo` recibe `otros_afectados`); la ventana de baja lista lo asignado; el Inicio
  incluye las secciones registradas.
- `maestros`: la baja crea la alerta «sin {rol}» de cada invernadero a cargo y pasa al Gerente las alertas del Agrónomo (post e y
  regla 4 de USR-BAJ-USR, MD-61); la reactivación resuelve la del rol y aplica D4 (D8); «Personal por asignar» en el Inicio del
  Gerente (regla 5 de PROD-CNS-INV); `abrir_alerta` (regla 7 de 8.18); `roles` en `sincronizar_alertas_de_personal` (un rol desconocido lanza `ValueError`).
- Documentación: `docs/api/alertas.md`.
- **Fuera:** el paso 4 (pantalla de CU-46, con la entrada «Alertas» del menú): nace como disparador y pasa a MAE-02c.

**Pruebas** (en serie, con `--keepdb`; base de la fase 0 entre paréntesis)

- Concurrencia: 34 OK (30). Resto de `maestros` y `core`: 941 OK (855). Con `--parallel`, el comando de la tarea: 941 OK.
- TDD: las 85 pruebas nuevas del resto y las 4 de concurrencia se escribieron antes con `NotImplementedError` (la 86.ª, la del `ValueError` de `roles`, se agregó después de la pausa, a pedido del equipo); en la pausa fallaban
  por aserción o por `NotImplementedError` (ningún `TypeError`, `AttributeError`, `ImportError` ni error de fábricas).
- Experimento de quitar cada protección (E1 a E5, ver D-43): cada prueba falla por su aserción y, con todo restituido, pasan.

**Decisiones:** D-43 (propuesta, abajo).

**Cosas para saber**

- Ninguna prueba existente se modificó. Los archivos de pruebas de `core` suman clases (`UsrBajUsrExtensionTests`,
  `UsrModUsrExtensionTests`, `InicioExtensionTests`).
- `abrir_alerta` no audita y no bloquea el invernadero; frente a un traspaso simultáneo, su protección es razonada y no probada.
- **Pendiente para pendientes_CU, sin resolver:** que abrir la alerta la marque «leída» choca con la postcondición de CU-46 («no
  se produjeron cambios en el sistema»).
- Los archivos tocados se dejaron con finales de línea LF.
