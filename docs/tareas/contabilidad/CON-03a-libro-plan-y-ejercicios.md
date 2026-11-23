# CON-03a · Pantallas de «Contabilidad»: libro de gestión, plan de cuentas y ejercicios

Estado: pendiente | App: contabilidad | Rama: feature/con-03a-libro-plan-y-ejercicios | Ronda: Contabilidad 1

Depende de: **CON-02** (el núcleo) y USR-11. Si CON-02 no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas del prototipo son una referencia (D-61): corregí y completá lo que haga falta.

**Qué resuelve.** La parte de **consulta** de la contabilidad: el **libro de gestión** (cronológico y por cuenta), el **plan de cuentas** y los
**ejercicios** con el **cierre manual**. Es la primera vez que el Contador y el Gerente ven la contabilidad en pantalla.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CON-CNS-LGS | Consultar Libro de Gestión | docs/casos_de_uso/contabilidad/libro_de_gestion.md | Las acciones de la ficha (contraasentar, registrar) quedan escondidas hasta CON-03b; el punto de extensión de enlaces a origen lo crea esta tarea |
| CON-CNS-PCT | Consultar Plan de Cuentas | docs/casos_de_uso/contabilidad/plan_de_cuentas.md | — |
| CON-CRR-EJE | Cerrar Ejercicio Contable | docs/casos_de_uso/contabilidad/ejercicio.md | Solo la mitad «cerrar»; la apertura la hizo CON-02 |

## Leer

- Casos de uso: los tres extractos, completos, **incluida la sección «Cómo se aplica (código)»** de cada uno.
- Modelo: docs/modelo/contabilidad.md (las cuatro clases y el plan).
- Decisiones: D-84 (puntos 5, 7, 8 y 10), D-85, D-86, D-37, D-39, D-40, D-42, D-44, D-61.
- API: docs/api/asientos.md (las secciones «Lectura» y «Escritura»: `cerrar_ejercicio` se implementa acá).
- Patrones: docs/patrones/abm.md (listados y filtros), docs/patrones/bloqueos.md, docs/patrones/auditoria.md, docs/patrones/asientos.md.
- Pantallas: docs/prototipos/compras_contabilidad/ — leé primero su `README.md`. Funciones: `k_main`, `tabLibro`, `libroCron`, `libroCta`,
  `VIEWS.k_asi`, `tabPlan`, `PLAN`, `RUBROS`, `tabEje`, `VIEWS.k_cierre`, `ACT['cierre-ok']` (referencia, D-61; lo que difiera de los casos de
  uso lo decide el caso de uso, L7). **No copies** el selector de rol ni «Hay un Contador activo».
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `contabilidad/servicios/*` (lo de CON-02), `core/menu.py` y `core/acceso.py`, una app con pestañas (`comercial/views.py` y sus
  plantillas) como modelo de organización, `core/templates/` (marco y componentes).

## Límites

- Crea modelos: ninguno.
- Migraciones: ninguna.
- Permitido fuera de la app: `config/urls.py` (una línea, `path("contabilidad/", include("contabilidad.urls"))`) y la misma en
  `core/tests/urls_prueba_acceso.py`; `core/menu.py` (la entrada «Contabilidad» para Contador y Gerente); íconos de `core/templatetags/iconos.py`
  que falten, copiados del prototipo; al cerrar (M3), `docs/disparadores.md`, `docs/tareas/README.md` y el plan de la ronda.
- Dependencias nuevas: ninguna.
- Fuera de alcance: registrar asientos manuales y contraasientos (CON-03b), pagos a proveedores y toda la bandeja de compras, y los
  asientos de cada operación.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Servicios de lectura del libro.** `libro.listar_asientos`, `ficha_de_asiento`, el punto de extensión `contabilidad/extensiones.py`
   (`registrar_enlace_de_origen`), paginación. — pruebas: `test_con_cns_lgs.py`, `test_libro.py`.
2. **Plan de cuentas (servicio y pantalla).** `plan.arbol()` ya existe (CON-02); la vista con el árbol y los enlaces al libro por cuenta. —
   pruebas: `test_con_cns_pct.py`.
3. **Cierre de ejercicio.** `ejercicios.cerrar_ejercicio` y `resumen_para_cierre`; la pestaña «Ejercicios» y la pantalla de confirmación. —
   pruebas: `test_con_crr_eje.py` y la parte del cierre de `test_ejercicios_concurrencia.py` (cierre contra un asiento a la vez).
4. **Pantallas y menú.** Las tres pestañas, la entrada del menú, las dos vistas del libro, los textos explicativos, las alertas de
   «ejercicio en cierre» en el Panel del Contador y del Gerente. — pruebas: `test_libro_vistas.py` y de acceso por rol (Contador y Gerente sí;
   Vendedor y los demás, 403).

Si el tiempo apremia, lo último que se recorta es: la alerta del Panel (se anota como disparador).

## Hecho cuando

- El Contador y el Gerente ven el libro (las dos vistas), el plan y los ejercicios; los demás roles no entran.
- Un ejercicio «en cierre» se cierra desde la pantalla, con resumen y confirmación, y deja de aceptar asientos.
- Los saldos patrimoniales acumulan entre ejercicios y los de resultado no.
- Pruebas verdes (incluida concurrencia), sin consultas por fila, sin migraciones pendientes.
- Comando de pruebas: `python manage.py test contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test contabilidad --keepdb --tag concurrencia`.

## Verificación a mano

1. Como Contador, abrí «Contabilidad»: ves el libro (vacío si no hay asientos), el plan de 19 cuentas y un ejercicio abierto.
2. Con un asiento creado desde la consola (CON-02), probá ambas vistas y los filtros.
3. Forzá un ejercicio «en cierre» (`fecha_cierre_ejercicio` pasada + paso diario) y cerralo.

## Cierre (M3)

Actualizá README de tareas, el plan de la ronda y `docs/estado.md`. Anotá cada diferencia con el prototipo (en especial las de las pantallas).
