# MAE-02a · Alerta: modelo, API y alertas de personal del invernadero

Estado: hecha, en revisión | App: maestros | Rama: feature/mae-02-alerta

Depende de: MAE-01b (hecha)

## Leer

- Casos de uso: docs/casos_de_uso/maestros/invernaderos.md — PROD-ALT-INV: post d, e y f, reglas 4 y 5; PROD-MOD-INV:
  post b a f, reglas 2 a 5; PROD-BAJ-INV: post e y f
- Modelo: docs/modelo/maestros.md — Alerta (completa, con la regla 7 de 8.18); Invernadero, «Reglas que lo tocan»
  (reglas 3 y 4 de 8.22, MD-60, MD-61, MD-87)
- Decisiones: D-22, D-30, D-32, D-36, D-37, D-38, D-39, D-40, D-41 (nueva)
- Patrones: docs/patrones/bloqueos.md, docs/patrones/auditoria.md, docs/patrones/datos_de_migracion.md
- Pantallas: ninguna nueva (la ventana de la regla 2 de PROD-MOD-INV suma «N alertas activas» en «Recibe»)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md

## Límites

- Crea modelos: Alerta → revisá docs/disparadores.md
- Permitido fuera de la app: core/models.py (solo `RegistroAuditoria.ETIQUETAS`); docs/api/alertas.md (nuevo);
  docs/modelo/maestros.md (copiar la regla 4 de 8.22, MD-61, y la regla 7 de 8.18, con el texto del 19/11/2026)
- Migraciones: solo nuevas, en maestros (0003_alerta, solo esquema). Ninguna en core
- Dependencias nuevas: ninguna
- Fuera de alcance: notificaciones y campana (tarea aparte en core, D-42); baja y reactivación de una cuenta con
  invernaderos a cargo, aviso del Inicio y `abrir_alerta` (MAE-02b); pantalla de alertas (MAE-02b, según CU-46); orígenes
  Hardware, Telemetría, SolicitudRevisión y Merma (disparadores); alertas de invernaderos que ya existen (D9, antes del merge)

## Hecho cuando

- Las alertas «invernadero sin {rol} activo» se crean y se resuelven en alta, modificar, reactivar y baja del invernadero.
- Al cambiar o asignar el Agrónomo, sus alertas pasan según MD-60 y D4 (por destinatario del tipo); la regla 2 las cuenta
  en el aviso.
- La API de docs/api/alertas.md está implementada y probada, y se puede usar sin leer el código.
- Pruebas: maestros/tests/test_alerta.py (AlertaServicioTests, AlertaTiposTests, AlertaConcurrenciaTests) y las de
  test_prod_{alt,mod,baj}_inv.py que reemplazan a las test_d38_…
- Comando de pruebas (suites completas de maestros y de core, porque se toca core/models.py):
  python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test maestros core --keepdb --tag concurrencia

## Verificación a mano

Con el entorno virtual activo y la base local (`python manage.py runserver`, con `DEBUG` encendido para usar `/admin/`). Hay una
migración nueva: `python manage.py migrate` (maestros 0003_alerta). Cuentas: un Gerente, un Agrónomo, un Capataz y un Vendedor.

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

## Cierre (completado el 19/11/2026)

**Qué se hizo**

- `Alerta` en `maestros` (D-38) con la migración `0003_alerta` (solo esquema): destinatarios `para_gerente` y `agronomo` (R007 y
  R049), estados independientes (regla 7 de 8.18), tres restricciones de la base (al menos un destinatario, fecha de resolución
  coherente con el estado y una alerta de estado activa por invernadero, tipo y clave) y el alcance `Alerta.objects.para(usuario)`.
- Registro de tipos (`maestros/alertas.py`, regla A4 de D-37) con los cuatro `sin_{rol}` registrados en `MaestrosConfig.ready()`.
- API de servicios (`maestros/servicios/alertas.py`) y su documento para IoT (`docs/api/alertas.md`).
- Conectadas en `alta_invernadero`, `modificar_invernadero`, `reactivar_invernadero` y `baja_invernadero`: postcondición d de
  PROD-ALT-INV; b, d y e de PROD-MOD-INV (y el «N alertas activas» de la regla 2); e de PROD-BAJ-INV. Las alertas van en los
  `datos` del registro de auditoría (D6).
- Extracto del modelo (`docs/modelo/maestros.md`): copiados el texto de la regla 4 de 8.22 (MD-61) y el de la regla 7 de 8.18.
- No se tocó `CLAUDE.md`. Las notificaciones (postcondiciones e de PROD-ALT-INV y c de PROD-MOD-INV) quedan para una tarea aparte
  en `core` (D1 = B, D-42); por eso las `test_d38_…` se reemplazaron solo por la conducta de las alertas: la mitad «ni
  notificaciones» no tiene qué probar todavía.

**Pruebas** (en serie, con `--keepdb`)

- `maestros` completo: 336 pruebas OK. Sin concurrencia pasó de 234 a 322 y las de concurrencia, de 10 a 14. `core` completo:
  545 OK, sin cambios en esta tarea.
- `python manage.py test maestros core --keepdb --tag concurrencia`: 30 OK.
- Experimento de quitar cada protección (ver D-41): cada prueba de concurrencia falla por su aserción, y con todo restituido
  vuelven a pasar.

**Decisiones**: D-41 (propuesta, abajo); D-42 (notificaciones en `core`), a escribir en su tarea.

**Cosas para saber**

- Las 4 pruebas `test_d38_…` se reemplazaron; tres pruebas existentes que comparaban el `detalle` exacto cambiaron su valor
  esperado para incluir `datos.alertas_creadas` (alta, modificar y reactivar), sin quitar ninguna comprobación.
- Con `--parallel`, un error en una prueba muestra `cannot pickle 'traceback' object` si no está `tblib` (no agregué dependencias):
  para ver el motivo de una falla, correr en serie.

### Para D-41 (decisiones tomadas al escribir las pruebas, aprobadas el 19/11/2026)

1. **«Recibe» de la regla 2 de PROD-MOD-INV:** la entrada `("alertas activas", N)` solo aparece si N > 0 (no se muestra «0 alertas»).
2. **Descripción por defecto** de una alerta de estado sin descripción: el nombre del tipo («Invernadero sin Capataz activo»), sin el del invernadero: ya está en la FK y quedaría viejo si se lo renombra.
3. **`tipo`** en la API es el código registrado (`str`), no el objeto `TipoAlerta`.
4. **Sin cambios no sincroniza (D-28):** si `modificar_invernadero` no cambia nada, no guarda, no audita y no toca las alertas.
   Consecuencia: un invernadero viejo sin alertas (D9: creado antes de MAE-02a), o uno con una persona inactiva asignada
   cuya alerta nunca se creó, **no recibe su alerta al guardar sin cambios**; la recibe en la primera modificación con cambios
   o en una reactivación.

Pruebas existentes cuyo valor esperado se actualizó (igualdad exacta del `detalle`, con `datos.alertas_creadas`):
`test_post_f_el_detalle_tiene_los_datos_cargados_con_antes_nulo` (alta), `test_post_f_audita_la_modificacion_con_el_invernadero_como_afectado`
(modificar; su invernadero viene de la fábrica, no de `alta_invernadero`: es el caso de un invernadero viejo, D9) y
`test_post_f_audita_la_reactivacion_con_el_cambio_de_estado` (reactivar).
