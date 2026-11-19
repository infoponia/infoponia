# MAE-01 · Invernadero: alta, modificación, baja y consulta

Estado: pendiente | App: maestros | Rama: feature/mae-01-invernadero

Depende de: PRD-00 (si las apps no existen, frená)

Es la primera tarea de un módulo de negocio: también es la primera que audita, la primera que crea pantallas fuera de
`core` y la primera que carga datos por migración. Conviene hacerla con cuidado, porque fija el patrón de las que
siguen.

## Leer

- Casos de uso: `docs/casos_de_uso/maestros/invernaderos.md` — completo (es corto): PROD-ALT-INV, PROD-MOD-INV,
  PROD-BAJ-INV y PROD-CNS-INV, «Pantallas», «Para más adelante» y «Solo prototipo»
- Modelo: `docs/modelo/maestros.md` — `Invernadero`, `Direccion`, `DireccionUrbana`, `DireccionRural` y la geografía.
  **No** la sección de `Alerta`, que es de MAE-02
- Decisiones: D-04, D-05, D-06, D-22, D-28 (alcance por usuario), D-36, D-37
- Patrones: `docs/patrones/auditoria.md`
- Pantallas: `docs/prototipos/produccion/` — `invCard`, `invListBody`, `VIEWS.inv`, `capInv`, `people`, `person`,
  `VIEWS['inv-form']`, `invErrs`, `INIT['inv-form']`, `ACT['inv-save']`, `MODALS['inv-baja']`, `personalCard`,
  `alertasInv`
- Reglas: `.claude/rules/pruebas.md`, `.claude/rules/interfaz.md`

## Límites

- **Crea modelos:** `Invernadero`, `Direccion` (abstracta), `DireccionUrbana`, `DireccionRural`, `Provincia`,
  `Departamento` y `Localidad` → revisá `docs/disparadores.md`, que tiene una sección «Cuando exista Invernadero»
- **Permitido fuera de la app:** `core/models.py`, solo para agregar las acciones de auditoría nuevas a
  `RegistroAuditoria.Accion`, a `ACCIONES_DE_NEGOCIO` y a `ETIQUETAS` (ver `docs/patrones/auditoria.md`), con su
  migración en `core`; `core/menu.py` y la plantilla del menú, para la entrada del Gerente y del Agrónomo;
  `config/urls.py`, para las URL de la app
- **Migraciones:** nuevas, en `maestros`; más una en `core` solo por los `choices` de las acciones
- **Dependencias nuevas:** ninguna
- **Fuera de alcance:**
  - las alertas de personal faltante (postcondición d de PROD-ALT-INV; b, d y e de PROD-MOD-INV; e de PROD-BAJ-INV):
    las hace MAE-02, que crea `Alerta` (D-38);
  - las notificaciones (postcondición e de PROD-ALT-INV, c de PROD-MOD-INV): no se modelan (D-38);
  - las precondiciones c a h de PROD-BAJ-INV: sus clases no existen todavía, así que se dan por cumplidas y se deja
    previsto el punto de extensión (regla A4 de D-37);
  - lo que recibe la persona entrante al cambiar un rol (postcondición b de PROD-MOD-INV): sus clases no existen;
  - los sectores, la capacidad, los lotes, la cámara y la bitácora de la ficha (regla 3 de PROD-CNS-INV);
  - los transportistas vinculados (R155);
  - el sistema IoT: su estado lo informa el bloque IoT.

## Decisiones que hay que tomar en el plan

Avisá y esperá respuesta antes de implementarlas; después van a una decisión D-39 (regla L7).

1. **El nombre del modelo tiene un error de tipeo en el diagrama** (`nombreInverdadero`). D-05 pide corregirlo y
   registrarlo: sería `nombre_invernadero`.
2. **Cómo se cargan las localidades de Georef.** MD-88 dice que se precargan y que no tienen ABM. Hay que decidir de
   dónde sale el archivo de datos y si la migración lo carga entero o un subconjunto.
3. **La dirección es una jerarquía** (`Direccion` abstracta con dos hijas). Hay que elegir cómo se representa en
   Django: herencia multi-tabla, como `Usuario` y los roles (D-01), o un solo modelo con un campo que distinga urbana
   de rural. Decidilo con su motivo.
4. **Nombres de las acciones de auditoría.** Las de cuentas ya usan `alta`, `modificacion` y `baja`, y un módulo de
   negocio no puede reutilizarlas (`docs/patrones/auditoria.md`). Proponé la forma, por ejemplo
   `alta_invernadero`.
5. **El personal y los sectores son opcionales.** El modelo todavía dice que son obligatorios (R051, R097, R134, R149
   y R098), pero MD-87 y MD-74 ya lo resolvieron y los casos de uso usan la forma nueva. Manda el caso de uso: el
   invernadero se crea sin personal y sin sectores.

## Hecho cuando

- El Gerente da de alta, modifica, da de baja y reactiva invernaderos, con su dirección urbana o rural y su personal
  opcional, según PROD-ALT-INV, PROD-MOD-INV y PROD-BAJ-INV.
- El Gerente y el Agrónomo consultan los invernaderos con el alcance de la regla 1 de PROD-CNS-INV: el Gerente, todos;
  el Agrónomo, solo los activos a su cargo. El alcance vive en un único queryset (D-28).
- Las localidades de Georef están cargadas por migración y las listas de provincia, departamento y localidad están
  encadenadas.
- Cada operación que modifica datos deja su registro de auditoría con el formato de D-36. La consulta no se audita
  (SEG-14).
- Pruebas: `maestros/tests/test_prod_alt_inv.py`, `test_prod_mod_inv.py`, `test_prod_baj_inv.py` y
  `test_prod_cns_inv.py`, cada uno con `<CodigoCu>ServicioTests` y `<CodigoCu>VistaTests`.
- Comando de pruebas: `python manage.py test maestros --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`

## Verificación a mano (la completa Claude Code al cerrar)

**MAE-01a** (la tarea se partió en 01a y 01b; ver «Cierre»). Con el entorno virtual activo y la base local:

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

## Cierre (la completa Claude Code al cerrar)

**Estado: MAE-01a hecha; MAE-01b pendiente.** La tarea se partió en dos, como la 04a y la 04b (D-39).

**Qué se hizo (MAE-01a)**

- Modelos de `maestros`: `Provincia`, `Departamento`, `Localidad`, `Direccion` (con `DireccionUrbana` y `DireccionRural`,
  multi-tabla) e `Invernadero` con sus cuatro FK de personal opcionales. Migraciones `0001_initial` y `0002_cargar_georef`
  (carga 24 provincias, 527 departamentos y 3923 localidades desde `maestros/datos/georef_2026-11-18/`).
- `core`: cuatro acciones de auditoría (`alta_invernadero`, `modificacion_invernadero`, `baja_invernadero` y
  `reactivacion_invernadero`), `accion` con `max_length=50`, `ACCIONES_DE_NEGOCIO`, `ETIQUETAS` y `VALORES_VISIBLES`;
  migración `core/0010` (solo `ALTER COLUMN ... TYPE varchar(50)`, verificado con `sqlmigrate`); cinco íconos nuevos;
  entrada «Producción» en el menú del Gerente y del Agrónomo.
- Servicios en `maestros/servicios/invernaderos.py` (`alta_invernadero`, con todo después de `actor, nombre` solo por
  nombre; `consultar_invernaderos`, `obtener_invernadero` y `cuentas_asignables`) y `geografia.py`.
- Pantallas: lista, ficha y alta, con listas encadenadas por HTMX y respaldo sin JavaScript.
- Casos de uso cubiertos: PROD-ALT-INV (menos las postcondiciones d y e) y PROD-CNS-INV (reglas 1, 2, 4 y 7, y la regla 3
  sin capacidad ni pestañas).

**Pruebas:** `maestros/tests/test_prod_alt_inv.py` y `test_prod_cns_inv.py`, con sus clases `...ServicioTests` y
`...VistaTests`: 99 pruebas, todas pasan con el comando de pruebas. También pasan las de `core` que tocan el menú, las
acciones de auditoría y los íconos.

**Decisiones:** D-39 (propuesta aparte): corrección de `nombreInverdadero`; Georef recortado y cargado por migración desde
CSV del repo; dirección multi-tabla; acciones `<acción>_invernadero` y `accion` de 50 caracteres; personal y sectores
opcionales; tipos y largos de los campos; formato de `kilometro` y de `numero_calle` (validadores en
`maestros/validadores.py`; es un hueco de la regla 2 de PROD-ALT-INV, anotado para pendientes_CU); contenido mínimo
(una letra o un número) de los textos libres; íconos.

**Fuera de lo previsto en «Permitido fuera de la app»** (cambios mínimos, para que el equipo los revise):
`core/templatetags/iconos.py` (autorizado en el plan) y `core/tests/urls_prueba_acceso.py` (el URLconf de apoyo de dos
pruebas de `core` no resolvía la entrada «Producción» del menú, así que incluye también `maestros.urls`).

**Para más adelante:** el aviso «Personal por asignar» del Inicio del Gerente (regla 5 de PROD-CNS-INV) pasa a MAE-02, que
crea las alertas; las postcondiciones d y e de PROD-ALT-INV, a MAE-02 y a la decisión sobre las notificaciones (D-38).
MAE-01b: modificar, reactivar y dar de baja.
