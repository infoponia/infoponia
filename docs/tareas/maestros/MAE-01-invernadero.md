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

## Cierre (la completa Claude Code al cerrar)
