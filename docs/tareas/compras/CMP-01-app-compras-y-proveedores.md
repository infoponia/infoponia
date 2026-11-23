# CMP-01 · App `compras` y proveedores

Estado: pendiente | App: compras | Rama: feature/cmp-01-app-compras-y-proveedores | Ronda: Compras 1

Depende de: INV-02 (`TipoInsumo`, hecha). **No depende de la contabilidad.** `validar_cuit`: si COM-01 ya se mergeó, se usa; si no, esta tarea
lo crea (ver «Límites»). Puede empezar en paralelo con la ronda «Contabilidad 1».

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** Crea la app `compras` (nivel 6) y el dato maestro que necesita todo lo demás: el **proveedor**, con su CUIT único, sus
especialidades (tipos de insumo) y su baja lógica con reactivación. Lo administra solo el Gerente; el Agrónomo lo consulta para invitarlo.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-ALT-PRV | Alta Proveedor (con la reactivación) | docs/casos_de_uso/compras/proveedores.md | — |
| CMP-MOD-PRV | Modificar Proveedor | docs/casos_de_uso/compras/proveedores.md | Regla 2 (CUIT con pedidos u órdenes): la consulta existe y hoy da `False`; se completa en CMP-02a |
| CMP-BAJ-PRV | Baja Proveedor | docs/casos_de_uso/compras/proveedores.md | Precondición c: se completa en CMP-03; d: en CMP-05; regla 3 (anular enlaces): en CMP-02b |
| CMP-CNS-PRV | Consultar Proveedor | docs/casos_de_uso/compras/proveedores.md | Regla 4 (pedidos, órdenes, pagos y reclamos de la ficha): se completa en CMP-02a a CMP-06 |

## Leer

- Casos de uso: el extracto, completo, **incluida «Cómo se aplica (código)»**.
- Modelo: docs/modelo/compras.md («Convenciones» y `Proveedor`).
- Decisiones: D-87 (la de la ronda), D-58 (CUIT), D-05, D-06, D-21, D-22, D-28, D-30, D-36, D-37, D-44, D-61.
- API: docs/api/direcciones.md (solo la sección «CUIT»).
- Patrones: docs/patrones/abm.md, docs/patrones/bloqueos.md, docs/patrones/auditoria.md.
- Pantallas: docs/prototipos/compras_contabilidad/ — leé primero su `README.md`. Funciones: `tabPrv`, `VIEWS.c_prv`, `VIEWS.c_prvform`, `NAV.ger` y
  `NAV.agr` (líneas 2275 a 2277).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: el ABM de cliente si ya existe (`comercial/servicios/clientes.py`); si no, `maestros/servicios/cultivos.py` (el ABM más
  parecido); `maestros/validadores.py`, `maestros/servicios/perfil.py` (`_cuit_valido`); `inventario/models.py` (`TipoInsumo`); `inventario/apps.py`
  (cómo una app registra su menú); `core/models.py` (`Accion`, `ETIQUETAS`, `ACCIONES_DE_NEGOCIO`), `core/menu.py`, `core/acceso.py`
  (`rol_requerido`), `core/validadores.py` (`validar_telefono`).

## Límites

- Crea modelos: `compras.Proveedor` (con `especialidades`, M2M a `inventario.TipoInsumo`) → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0001_initial.py`; una de `core`, solo de `choices`, con las cuatro acciones (`alta_proveedor`,
  `modificacion_proveedor`, `baja_proveedor`, `reactivacion_proveedor`), con el número libre en `main`.
- Permitido fuera de la app: `config/settings.py` (`'compras'` en `INSTALLED_APPS` después de `'produccion'`, comentario `# nivel 6`);
  `config/urls.py` y `core/tests/urls_prueba_acceso.py` (una línea cada uno); `core/models.py` (solo las acciones) y su migración; íconos que falten
  en `core/templatetags/iconos.py`, copiados del prototipo; **si COM-01 no se mergeó:** `maestros/validadores.py` (`validar_cuit` y
  `formatear_cuit`, tal cual `docs/api/direcciones.md`), el reemplazo de `_cuit_valido` en `maestros/servicios/perfil.py` por la pública, y
  `maestros/tests/test_validar_cuit.py`. Al cerrar (M3): `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_compras_1.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: pedidos, cotizaciones, órdenes y todo lo marcado «se completa en CMP-NN».

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **App, modelo y auditoría.** La app (`apps.py` con el docstring de nivel), `Proveedor` con sus restricciones (CUIT único y de 11 dígitos; por
   tipo), las acciones de auditoría. — pruebas: `compras/tests/test_modelos.py`.
2. **CUIT** (si hace falta, ver «Límites»). — pruebas: `maestros/tests/test_validar_cuit.py`.
3. **Servicios** de alta (con reactivación), modificación, baja (con `impedimentos_de_baja` vacío) y consulta. — pruebas:
   `test_cmp_alt_prv.py`, `test_cmp_mod_prv.py`, `test_cmp_baj_prv.py`, `test_cmp_cns_prv.py`, `test_proveedores_concurrencia.py`.
4. **Pantallas y menú:** «Compras › Proveedores» para el Gerente (lista, ficha, formulario, baja, reactivación) y para el Agrónomo (lista y
   ficha). — pruebas: `test_proveedores_vistas.py`.

Si el tiempo apremia, lo último que se recorta es: el filtro por tipo de insumo de la lista (se anota como disparador).

## Hecho cuando

- El Gerente da de alta, modifica, da de baja y reactiva proveedores; el CUIT no se repite ni con dos pedidos a la vez; el Agrónomo los ve y no
  los cambia; los demás roles no entran.
- Pruebas verdes (incluida `@tag("concurrencia")`), `makemigrations --check` limpio, sin imports de `comercial` ni de `produccion`.
- Comando de pruebas: `python manage.py test compras maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

1. Como Gerente, creá un proveedor con dos especialidades; intentá otro con el mismo CUIT: rechazo claro.
2. Dalo de baja y volvé a cargar su CUIT: te ofrece reactivarlo.
3. Como Agrónomo, abrí «Compras › Proveedores»: ves la lista y la ficha, sin botones de cambio.

## Cierre (M3)

Actualizá README de tareas, el plan de la ronda y `docs/estado.md`; anotá en el «Cierre» si creaste `validar_cuit` (para que COM-01 lo sepa).
