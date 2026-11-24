# CON-03a · Pantallas de «Contabilidad»: libro de gestión, plan de cuentas y ejercicios

Estado: hecha en la rama, falta el PR | App: contabilidad | Rama: feature/con-03a-libro-plan-y-ejercicios | Ronda: Contabilidad 1

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
  que falten, copiados del prototipo; `core/models.py` (solo el diccionario `RegistroAuditoria.ETIQUETAS`: `cerrado_por` y `contador`; autorizado el 24/11/2026); las aserciones del menú del Contador de `core/tests/test_rol_contador_vistas.py` y `core/tests/test_recorrido_rol_contador.py`; al cerrar (M3), `docs/disparadores.md`, `docs/tareas/README.md` y el plan de la ronda.
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

**Esta tarea tiene pantallas y un formulario que se envía** (el cierre del ejercicio): por eso lleva el paso de «navegador real» (el paso 20). Nada de esto toca producción: es tu base local de desarrollo (`localhost:5433`). Los pasos 1 a 12 son de consulta y no cambian nada importante; **los pasos 15 y 20 en adelante sí dejan huellas que no se pueden sacar** (leé el aviso).

**Aviso antes de empezar.**
- Un **asiento no se puede borrar ni editar** (es a propósito: se corrige con un contraasiento, que llega con CON-03b) y un ejercicio **«cerrado» no se reabre**.
- El paso diario con `--fecha` simulada (paso 15) deja en tu base un ejercicio «en cierre» y otro «abierto» que **empieza en el futuro**. Después de eso, no cargues más asientos automáticos «reales» en esa base: usá solo los fragmentos de esta verificación (llevan su `hoy` simulado).
- Si querés volver a empezar de cero, avisame y lo vemos (borrar datos de tu base de desarrollo se pregunta antes). Si preferís no ensuciar esa base, hacé solo los pasos 1 a 14 y el 18 (el resumen, sin confirmar), que no dejan nada irreversible.

**Qué necesitás.**
- Estar en la rama `feature/con-03a-libro-plan-y-ejercicios`, con el entorno virtual activo (`.venv\Scripts\Activate.ps1`) y la base local encendida.
- **Tres cuentas, cada una con su contraseña de prueba** (la de siempre; no va en ningún archivo del repo): un **Contador** activo, el **Gerente** y un **Vendedor**. Si te falta alguna, creala entrando como Gerente a «Usuarios y seguridad» → «Nuevo usuario». Solo puede haber **un** Contador activo (si ya tenés uno de la verificación de USR-11, usá ese).
- Para entrar con una cuenta distinta, abrí **una ventana privada** por rol (así no cerrás y abrís sesión cada vez).

### Preparación

**1. Levantá el servidor.** Esta tarea no tiene migraciones: si tu base está atrasada, `python manage.py migrate` aplica las de COM-04c que llegaron con `main` (`core` 0039 y `comercial` 0007), no las de esta tarea. En PowerShell, en la carpeta del proyecto:

```powershell
.venv\Scripts\Activate.ps1
python manage.py runserver
```

Abrí `http://localhost:8000/` en el navegador.

**2. Mirá en qué estado está tu base de ejercicios.** En otra terminal PowerShell: `python manage.py shell` y pegá (con una línea en blanco al final, por el `for`):

```python
from contabilidad.servicios import ejercicios
for e in ejercicios.ejercicios_numerados(): print("Ejercicio", e.numero, "|", e.ejercicio.fecha_inicio_ejercicio, "al", e.ejercicio.fecha_cierre_ejercicio, "|", e.ejercicio.estado_ejercicio, "|", e.cantidad_de_asientos, "asientos")
```

Según lo que imprima:
- **No imprime nada** (no hay ejercicios): seguí con el paso 3.
- **Hay un ejercicio `abierto`** y ninguno `en_cierre`: salteá el paso 3 y seguí con el 4.
- **Hay uno `en_cierre`** (por los pasos opcionales de CON-02): ya tenés el estado de los pasos 15 a 17. Hacé los pasos 4 a 14 igual y, en vez del 15, seguí con el 16.

**3. (Solo si no hay ejercicios) Poné en marcha la contabilidad.** En PowerShell:

```powershell
python manage.py poner_en_marcha_contabilidad
```

Tiene que decir `Primer ejercicio creado: del <hoy> al <hoy + 1 año − 1 día>.` (lo cubre `test_con_abr_eje.py` y el recorrido).

**4. Creá dos asientos de prueba: uno automático y uno manual.** Todavía no hay pantalla para cargar un asiento manual (llega con CON-03b), así que se arman desde la consola. En la consola de Django (`shell`), pegá el bloque entero:

```python
from decimal import Decimal
from django.utils import timezone
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import EjercicioContable, OrigenDocumento
from contabilidad.servicios import asientos
from contabilidad.tests.fabricas import asiento_de_prueba
from core.models import Contador, Gerente, RegistroAuditoria

hoy = timezone.localdate()
quien = Contador.objects.filter(is_active=True).first() or Gerente.objects.filter(is_active=True).first()
origen = OrigenDocumento.objects.bulk_create([OrigenDocumento(tipo="bitacora")])[0]
automatico = asientos.registrar_asiento_automatico(
    quien, origen, hoy,
    [(cuentas.CAJA, DEBE, Decimal("1000.00")), (cuentas.VENTAS, HABER, Decimal("1000.00"))],
    descripcion="CON-03a: venta de prueba",
)
ejercicio = EjercicioContable.objects.get(pk=automatico.ejercicio_id)
manual = asiento_de_prueba(
    ejercicio, hoy,
    [(cuentas.GASTOS_GENERALES, DEBE, Decimal("50.00")), (cuentas.CAJA, HABER, Decimal("50.00"))],
    descripcion="CON-03a: pago de la luz",
)
RegistroAuditoria.objects.registrar(quien, RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE, [manual], {})
print("Automático: N.º", automatico.numero_asiento, "| Manual: N.º", manual.numero_asiento, "| ejercicio:", ejercicio)
```

Tiene que imprimir algo como `Automático: N.º 1 | Manual: N.º 2 | ejercicio: Ejercicio 24/11/2026 al 23/11/2027` (si tu base ya tenía asientos, los números siguen a los que había). El `OrigenDocumento` suelto es un documento de prueba (el real lo crea la recepción, el pago, etc.) y el asiento «manual» se arma directo porque aún no existe el caso de uso que los registra.

### Con la cuenta del Contador

Entrá con el **Contador** (ventana privada A).

**5. El menú.** En el menú lateral aparece **«Contabilidad»** entre «Panel de control» y «Compras» (con un ícono de libro). Al hacer clic abre «Libro de gestión» y arriba hay tres pestañas: **Libro de gestión**, **Ejercicios** y **Plan de cuentas**. Debajo del título, una línea explica qué es el libro de gestión («No es el libro diario ni el mayor legales y no está homologado»). *(Lo cubre `test_libro_vistas.py`: `AccesoPorRolTests` y `test_la_pantalla_explica_que_no_es_el_libro_diario_legal`.)*

**6. Libro cronológico.** En «Libro de gestión» (vista «Cronológica», ejercicio abierto por defecto) ves tus dos asientos: `N.º … · <hoy>` con su descripción en negrita, la insignia **Automático** (azul) o **Manual** (gris) y, debajo, las líneas de cuenta: `1.1.01 · Caja`, `4.1.01 · Ventas`, etc., con los importes en las columnas **Debe** y **Haber** (las líneas del Haber van con una «a» adelante). Al pie: **Totales (N asientos)** con el mismo importe en Debe y en Haber. *(Cubierto: `LibroCronologicoVistaTests`, `test_con_cns_lgs.py`.)*

**7. Filtros.** Probá, uno por uno, con «Filtrar» (no filtran solos mientras escribís):
- **Tipo → Manuales:** queda solo «CON-03a: pago de la luz». **Automáticos:** solo «venta de prueba».
- **Buscar** `luz`: queda solo el de la luz. Buscar el **número** de un asiento (por ejemplo `2`) trae ese asiento exacto.
- **Cuenta → 1.1.02 Banco c/c:** «No hay asientos con esos filtros», con «Quitar filtros»; al apretarlo vuelve todo.
- **Desde / Hasta** con la fecha de hoy en las dos: ves los dos asientos. Poné **Desde mañana** y **Hasta ayer** (al revés): aparece un aviso rojo «La fecha «hasta» no puede ser anterior a «desde»» y la pantalla sigue viéndose, sin error.
- **Anulados → Solo anulados:** ninguno (todavía no hay contraasientos).

*(Cubierto: `test_regla_2_los_filtros_de_texto_tipo_anulados_fechas_cuenta_y_origen`, `test_un_filtro_invalido_se_marca_y_la_pantalla_sigue_viendose`.)*

**8. Vista por cuenta.** Apretá **«Por cuenta»**. Aparece «Elegí una cuenta para ver sus movimientos» y las 19 cuentas agrupadas, con «Saldo al inicio» y «Saldo actual». Hacé clic en **Caja**: arriba una ficha con *Cuenta, Tipo, Saldo al inicio, Saldo actual* y abajo cada movimiento con **Debe, Haber y Saldo** acumulado (el +1.000,00 de la venta y el −50,00 de la luz; el saldo acumulado tiene que ir sumando). En una cuenta patrimonial como Caja dice «Arrastra los ejercicios anteriores»; en **Ventas** (de resultado) dice «Empieza en cero cada ejercicio». Cada «N.º» abre la ficha del asiento. «Ver en el plan de cuentas» te lleva a esa cuenta en el plan. *(Cubierto: `LibroPorCuentaVistaTests`.)*

**9. Ficha del asiento.** Abrí el asiento **manual**. Se ve: *Fecha, Ejercicio (con su rango y estado), Origen («Sin documento de origen»), **Registrado por** (tu Contador o Gerente, con su rol), Importe*, la descripción y la tabla de **Movimientos** con los totales. Abrí el **automático**: no tiene «Registrado por» y en «Origen» dice «Bitácora» (sin enlace, porque ninguna app registró todavía su enlace) y, abajo, «Este asiento lo genera el sistema…». **No hay ningún botón «Contraasentar» ni «Registrar asiento»** (llegan con CON-03b). *(Cubierto: `FichaDelAsientoVistaTests`.)*

**10. Plan de cuentas.** Pestaña «Plan de cuentas»: árbol por rubro (**1 Activo, 2 Pasivo, 3 Patrimonio neto, 4 Ingresos, 5 Egresos**) y subrubro, con **19 cuentas** (de `1.1.01 Caja` a `5.1.07 Gastos Generales`, con `2.1.02 Indemnizaciones a Pagar`), el tipo de cada una, **para qué se usa** (por ejemplo, Caja: «Efectivo de la organización. La mueven: …») y su saldo del ejercicio abierto como enlace (Caja: `$ 950,00` más lo que ya tuvieras; las demás, «Sin movimientos»). Aviso fijo: «Sin IVA: es una simplificación declarada». Probá el buscador: `caja` deja solo Caja; `5.1.0` las de egresos; `zzz` dice «No hay cuentas con ese texto». Hacé clic en el saldo de Caja: abre el libro, vista por cuenta, con Caja y el ejercicio ya elegidos. *(Cubierto: `test_con_cns_pct.py`.)*

**11. Ejercicios (abierto).** Pestaña «Ejercicios»: una fila por ejercicio, del más nuevo al más viejo, con «Ejercicio N», el rango, la insignia **Abierto**, la cantidad de asientos y **«Ver libro»**. **No hay botón «Cerrar ejercicio»** (el abierto no se cierra a mano). Abajo no dice nada especial para vos (sos el responsable). *(Cubierto: `EjerciciosVistaTests`.)*

### Con las otras cuentas

**12. Gerente con el Contador activo.** Entrá con el **Gerente** (ventana privada B): ve «Contabilidad» y las tres pestañas con los mismos datos (siempre consulta el libro). En «Ejercicios» no hay botón de cerrar y abajo dice «Los ejercicios los cierra el Contador (si no hay un Contador activo, el Gerente). Acá solo los consultás.». En su Panel de control no hay ninguna alerta de contabilidad. *(Cubierto: `AccesoPorRolTests`, `PanelVistaTests`.)*

**13. Vendedor.** Entrá con el **Vendedor** (ventana privada C): en el menú **no** aparece «Contabilidad». Escribí a mano en la barra de direcciones `http://localhost:8000/contabilidad/`, `…/contabilidad/plan-de-cuentas/` y `…/contabilidad/ejercicios/`: las tres tienen que dar **403** (página «Prohibido»). *(Cubierto: `test_regla_1_el_vendedor_y_los_demas_roles_reciben_403_en_todas_las_pantallas`; con el cliente de Django ya está probado, acá confirmás que el 403 se ve bien.)*

**14. Sin sesión.** Cerrá sesión y probá `http://localhost:8000/contabilidad/`: te manda a iniciar sesión. *(Cubierto: `test_sin_sesion_lleva_al_inicio_de_sesion`.)*

### El cierre del ejercicio (deja huellas que no se pueden sacar)

**15. Dejá un ejercicio «en cierre».** Se hace con el paso diario y una fecha simulada: el día siguiente al fin del ejercicio abierto. Primero averiguá cuál es ese día; en la consola de Django:

```python
import datetime
from contabilidad.servicios import ejercicios

abierto = ejercicios.ejercicio_abierto()
dia = abierto.fecha_cierre_ejercicio + datetime.timedelta(days=1)
print("Ejercicio abierto:", abierto)
print("Corré el paso diario con --fecha", dia)
```

Después, en PowerShell, con la fecha que imprimió (por ejemplo, `2027-11-24`):

```powershell
python manage.py proceso_diario --solo abrir_ejercicio --fecha 2027-11-24
```

Tiene que decir algo como `Abrir ejercicio contable: procesados 1 · creados 1 · resueltos 0 · Ejercicio … pasó a «en cierre»; abierto: Ejercicio …`. Volvé a correr el fragmento del paso 2: ahora el primero figura `en_cierre` y hay uno nuevo `abierto` con 0 asientos. *(Cubierto: el recorrido, paso 8; `test_con_abr_eje.py`.)*

**16. La alerta y la pestaña (Contador).** Con el **Contador**, volvé al «Panel de control»: aparece una sección **«Contabilidad»** con un aviso amarillo «El ejercicio 1 terminó el … Revisá el libro de gestión y cerralo cuando estés conforme.» y los enlaces «Ver el libro» y «Cerrar ejercicio». En «Contabilidad» la pestaña **«Ejercicios» lleva la marca «en cierre»**. En la lista, el ejercicio 1 está **En cierre** con el botón azul **«Cerrar ejercicio»** (el «Terminó hace N días» puede decir «Terminó el …» porque la fecha es simulada). En «Libro de gestión» → elegí el ejercicio 1 en el desplegable y «Filtrar»: arriba un aviso amarillo «El ejercicio 1 está en cierre. Terminó el … Todavía se pueden registrar asientos de ese período hasta que se cierre.» *(Cubierto: `PanelVistaTests`, `test_regla_6_el_ejercicio_en_cierre_y_el_cerrado_llevan_su_aviso`.)*

**17. Quien no puede cerrar (Gerente con Contador activo).** Con el **Gerente**: en el Panel **no** hay alerta y en «Ejercicios» **no** hay botón. Copiá la dirección del botón del Contador (clic derecho → copiar enlace; es `…/contabilidad/ejercicios/<número>/cerrar/`) y pegala en la ventana del Gerente: **403**. Con el **Vendedor**, la misma dirección: **403**. *(Cubierto: `test_regla_5_el_gerente_con_contador_activo_recibe_403_y_no_cierra`, recorrido paso 12.)*

**18. El resumen y la confirmación (Contador).** Con el **Contador**, apretá **«Cerrar ejercicio»**. Aparece «Cerrar el ejercicio 1» con: **1 · Resumen** (*Período* `dd/mm/aaaa al dd/mm/aaaa`, *Asientos* = la cantidad real, *Total del Debe* y *Total del Haber* **iguales**; con los dos asientos de esta verificación sumá 1.050,00 más lo que ya hubiera), un aviso amarillo **«El cierre no se puede deshacer…»** (dice que un automático con fecha de ese período irá al ejercicio abierto con la fecha de hoy, que un manual se rechaza, y que los saldos patrimoniales pasan al siguiente mientras los de resultado empiezan en cero) y **2 · Confirmación** con la casilla «Revisé el libro de gestión y quiero cerrar el ejercicio 1». Apretá **«Cerrar el ejercicio 1» sin marcar la casilla**: vuelve la misma pantalla con el error rojo **«Confirmá que revisaste el libro para cerrar el ejercicio»** y **no** se cierra nada (miralo en «Ejercicios»). *(Cubierto: `CierreVistaTests`.)*

**19. Cancelar.** En esa misma pantalla, «Cancelar» vuelve a «Ejercicios» sin cambiar nada. *(Cubierto.)*

**20. Navegador real: enviá el formulario de cierre hasta el final.** Este es el paso que el cliente de Django no ve (el token CSRF, el encabezado `Origin`, el JavaScript). Con la **consola del navegador abierta (F12 → «Consola»)**, volvé a «Cerrar ejercicio», **marcá la casilla** y apretá **«Cerrar el ejercicio 1»** (el botón pasa a decir «Cerrando…»). Tiene que volver a «Ejercicios» con un aviso verde arriba: **«Cerraste el ejercicio N.º 1. Ya no recibe asientos.»**; el ejercicio 1 figura **Cerrado**, con «Lo cerró <nombre del Contador>», sin botón de cierre, y «Ver libro». El Panel ya no tiene la alerta. **Si aparece una página «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola, avisame:** lo más probable es un encabezado que el cliente de Django no puede ver. *(El flujo está cubierto por el recorrido y `test_el_envio_exige_el_token_csrf`; lo que solo ves acá es el navegador real.)*

**21. La Auditoría (Gerente).** Entrá con el **Gerente** → «Auditoría»: hay un registro **«Modificación de ejercicio contable»** del Contador con el cambio **«Estado del ejercicio: En cierre → Cerrado»**, **«Contador que lo cerró»** (nombre del Contador) y **«Cerrado por: contador»** (estas dos etiquetas son las que se agregaron en esta tarea; si ves `contador` o `cerrado_por` crudos, avisame). *(Cubierto: `test_post_c_*` de `test_con_crr_eje.py`; acá se ve cómo queda en la pantalla.)*

**22. Ya no recibe asientos.** En la consola de Django, pegá el bloque entero (simula el día siguiente al fin del ejercicio cerrado y asienta un hecho con fecha de ese ejercicio):

```python
import datetime
from decimal import Decimal
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import EjercicioContable, OrigenDocumento
from contabilidad.servicios import asientos

cerrado = EjercicioContable.objects.filter(estado_ejercicio="cerrado").order_by("-fecha_inicio_ejercicio").first()
hoy_simulado = cerrado.fecha_cierre_ejercicio + datetime.timedelta(days=1)
origen = OrigenDocumento.objects.bulk_create([OrigenDocumento(tipo="bitacora")])[0]
nuevo = asientos.registrar_asiento_automatico(
    None, origen, cerrado.fecha_cierre_ejercicio,
    [(cuentas.CAJA, DEBE, Decimal("1.00")), (cuentas.VENTAS, HABER, Decimal("1.00"))],
    descripcion="CON-03a: después del cierre", hoy=hoy_simulado,
)
print(nuevo.ejercicio, "|", nuevo.fecha_asiento, "|", nuevo.descripcion_asiento)
```

Tiene que imprimir el ejercicio **abierto** (no el cerrado), la fecha del día siguiente y una descripción que termina en «Fecha del hecho: dd/mm/aaaa (el ejercicio de esa fecha ya está cerrado); se registra con la fecha de hoy.». El ejercicio 1 sigue con la misma cantidad de asientos (miralo en «Ejercicios»). *(Cubierto: `test_regla_2_despues_del_cierre_un_asiento_automatico_con_fecha_en_su_rango_va_al_abierto`; el rechazo del asiento manual lo cubre `test_regla_2_despues_del_cierre_un_asiento_manual_con_fecha_en_su_rango_se_rechaza` y se verá en pantalla con CON-03b.)*

**23. Estado «cerrado» y saldos entre ejercicios.** En «Libro de gestión» elegí el **ejercicio 1** (cerrado): aviso azul «El ejercicio 1 está cerrado. Sus asientos son solo de consulta.»; la ficha de un asiento suyo dice «Este asiento es de un ejercicio cerrado: es solo de consulta.». Elegí el **ejercicio 2** → «Por cuenta» → **Caja**: «Saldo al inicio» = lo que dejó el ejercicio 1 (950,00 más lo que ya tuvieras) y dice «Arrastra los ejercicios anteriores»; **Ventas**: «Saldo al inicio» en «—» y «Empieza en cero cada ejercicio». *(Cubierto: el recorrido, paso 18; `LibroPorCuentaVistaTests`.)*

**24. Cerrar de nuevo.** Escribí a mano la dirección del cierre del ejercicio 1 (`…/contabilidad/ejercicios/<número>/cerrar/`): vuelve a «Ejercicios» con un aviso rojo «El ejercicio N.º 1 no está en cierre: no se puede cerrar.» *(Cubierto: `test_regla_1_un_ejercicio_que_no_esta_en_cierre_vuelve_a_la_lista_con_un_aviso`.)*

### Cuando no hay Contador activo (opcional; deja otro ejercicio más en la base)

**25. El Gerente cierra.** Repetí el paso 15 (el fragmento imprime la fecha del ejercicio 2, que ahora es el abierto; correlo con esa fecha). Después, como Gerente, en «Usuarios y seguridad» **dá de baja al Contador** (se puede reactivar). Con el **Gerente**: en el Panel aparece la alerta y en «Ejercicios» el botón «Cerrar ejercicio». En la pantalla de cierre, el aviso agrega «Lo cerrás vos porque no hay un Contador activo.» Cerralo (casilla + botón): el ejercicio queda **Cerrado** con «Sin Contador asociado (lo cerró el Gerente o el Sistema; ver la Auditoría)» y en la Auditoría figura el Gerente con «Cerrado por: gerente». **Al terminar, reactivá al Contador.** *(Cubierto: `test_recorrido_del_gerente_sin_contador_activo_cierra_el_y_la_asociacion_queda_vacia`.)*

### Opcional

**26. Sin JavaScript.** Desactivá JavaScript en el navegador (herramientas de desarrollo → «Disable JavaScript») y repetí los pasos 7 (filtros), 8 (cambiar de vista y de cuenta) y 10 (buscador): todo se envía con los botones «Filtrar»/«Buscar» y funciona igual; los desplegables se ven como los nativos.

**27. Celular.** No aplica: el Contador y el Gerente usan la interfaz de escritorio (D-85 punto 6, D-25).

**28. Paginación.** Con más de 50 asientos en un ejercicio, el libro cronológico muestra 50 y «Siguiente» (conserva los filtros); la vista por cuenta, 100. Está cubierto por `test_paginacion_de_50_asientos_conserva_los_filtros` y `test_paginacion_de_100_movimientos_por_pagina_con_el_saldo_que_sigue`; armarlo a mano es mucho trabajo para lo poco que agrega.

---

## Cierre

**Qué se hizo.**
- **Servicios de lectura del libro** (`contabilidad/servicios/libro.py`, se agregaron funciones y no se cambió lo de CON-02): `listar_asientos` (filtros de la regla 2, ejercicio abierto por defecto, sin consultas por fila), `ficha_de_asiento` (origen con enlace, quién lo registró desde la auditoría, el que anula y el que lo anuló), `pagina_de_movimientos_de_cuenta` (100 por página; el saldo de la primera fila sale de una suma agregada) y `total_de_los_asientos` (el pie «Totales»).
- **Punto de extensión** `contabilidad/extensiones.py`: `registrar_enlace_de_origen(tipo, funcion)` (idempotente; varios registrantes por tipo, gana el primero que responde) y `enlace_de_origen(origen)`.
- **Cierre del ejercicio** (`contabilidad/servicios/ejercicios.py`): `cerrar_ejercicio` (bloquea solo la fila del ejercicio, relee, revalida al actor, asocia al Contador, audita `modificacion_ejercicio_contable` con `datos.cerrado_por`), `resumen_para_cierre`, `ejercicios_numerados` y `numero_de_ejercicio`.
- **Pantallas** (`views.py`, `forms.py`, `urls.py`, `templates/contabilidad/`, `static/contabilidad/css/contabilidad.css`, `templatetags/formato_contable.py`): las tres pestañas, la ficha del asiento y la pantalla de cierre. Todo funciona sin JavaScript.
- **Menú y Panel** (`apps.py`, `servicios/inicio.py`): la entrada «Contabilidad» (Gerente y Contador) y la alerta del «ejercicio en cierre», registradas en `ready()`.
- **Fuera de la app:** `config/urls.py` y `core/tests/urls_prueba_acceso.py` (una línea cada uno), el ícono `book` en `core/templatetags/iconos.py` y el comentario de `core/menu.py` (la entrada no se agregó ahí; ver abajo).
- **Toque autorizado fuera de «Permitido»** (con tu autorización): `core/models.py`, solo el diccionario `RegistroAuditoria.ETIQUETAS`, con dos líneas: `cerrado_por` → «Cerrado por» y `contador` → «Contador que lo cerró». Sin migración (`makemigrations --check`: sin cambios) y sin acción nueva; las pruebas de auditoría de `core` pasan (74).

**Diferencias con la documentación** (van a `docs/temas_abiertos.md`):
1. **La entrada del menú no está en `core/menu.py`.** La tarea («Permitido») la ubicaba ahí; se registró desde `ContabilidadConfig.ready()` con `core.menu.registrar_entrada`, que es el patrón vigente (D-40, regla A4 de D-37: `core` no nombra URLs de las apps). En `core/menu.py` solo se actualizó el comentario.
2. **Tres aserciones de pruebas de `core` ya no podían pasar** y se actualizaron sin debilitarlas (el menú del Contador ahora es «Panel de control, Contabilidad, Compras»): `core/tests/test_rol_contador_vistas.py` (dos líneas) y `core/tests/test_recorrido_rol_contador.py` (una). La primera se renombró (`…su_menu_es_panel_contabilidad_y_compras`) porque su nombre ya no era cierto. Se agregaron a «Permitido» con tu visto bueno.
3. **Funciones que no estaban en `docs/api/asientos.md`:** `libro.listar_asientos`, `ficha_de_asiento`, `pagina_de_movimientos_de_cuenta` y `total_de_los_asientos`, y `ejercicios.resumen_para_cierre`, `ejercicios_numerados` y `numero_de_ejercicio`, más el punto de extensión de enlaces al origen. Se agregaron a esa API (tabla de «Lectura» y una sección nueva).
4. **«Deja de aceptar asientos»** (hecho cuando): por D-102 punto 1 se lee como «ya no recibe ningún asiento»: un automático con fecha de su rango va al abierto con la fecha de hoy y la aclaración; un manual o un contraasiento se rechaza (`fecha_en_ejercicio_cerrado`). El texto del cierre lo dice así.
5. **Un asiento inexistente y un ejercicio inexistente dan 404** (la documentación no lo dice; sigue D-28).
6. **La ficha muestra «quién lo registró» con nombre y rol**, no con el correo (la documentación dice solo «quién lo registró»).

**Pantallas: lo que se corrigió del prototipo (D-61).**
1. **Estados vacíos** que el prototipo no tenía (regla L7, D-61 punto 2): sin ejercicios, ejercicio sin asientos, filtros sin resultados («No hay asientos con esos filtros» con «Quitar filtros»), cuenta sin movimientos y buscador del plan sin coincidencias.
2. **Texto del cierre.** El prototipo dice «los asientos del ejercicio ya no se pueden registrar, modificar ni contraasentar»; es impreciso frente a D-102 y a la regla 2 de CON-CRR-EJE. Se escribió: el automático va al abierto con la fecha de hoy y lo aclara, el manual se rechaza, y no se deshace.
3. **Sin el aviso de «pagos pendientes a proveedores»** de `VIEWS.k_cierre`: los pagos son de `compras` (`contabilidad` es de nivel 2 y no puede importarla) y la regla 4 dice que el cierre no tiene verificaciones.
4. **Sin las columnas «Ingresos / Egresos / Resultado»** de `tabEje`: el caso de uso no las pide («número, rango, estado, cantidad de asientos, quién lo cerró») y calcularlas por ejercicio sería una consulta por fila. El resumen del cierre trae lo que pide la regla 4 (rango, cantidad de asientos, Debe y Haber).
5. **«Quién lo cerró» sin fecha de cierre.** El prototipo muestra «Cerrado el dd/mm»; el modelo no guarda esa fecha y no se inventó una columna (D-61 punto 3). Si lo cerró el Gerente o el Sistema, la fila dice «Sin Contador asociado… ver la Auditoría».
6. **Alerta del Panel solo para el responsable contable.** El prototipo (`panelGer`) también se la muestra al Gerente cuando hay un Contador activo; por tu decisión (24/11/2026) el Gerente la ve solo si no hay Contador activo. El resto del `panelCon` (proveedores para pagar, asientos del mes, resultado del mes) no es de esta tarea.
7. **Menú del Gerente:** «Contabilidad» queda justo antes de «Usuarios y seguridad», no después de «Compras» como en el prototipo: depende del orden en que cada app registra su entrada en `ready()` (el Contador sí queda «Panel, Contabilidad, Compras»).
8. **Desplegables propios** (D-24) con el aspecto de Diseño v2 en lugar de los `<select>` nativos del prototipo; los filtros se envían con «Filtrar» (no validan mientras se tipea) y la paginación (50 y 100) es del servidor, con enlaces que conservan los filtros.
9. **Selector de rol e interruptor «Hay un Contador activo»:** no se copiaron (solo prototipo).
10. **Subrubro 4.1:** el prototipo lo rotula «Ingresos de gestión»; se usó el del modelo, «Ingresos operativos».
11. **Cuando el ejercicio terminó «en el futuro»** (solo pasa al simular fechas): el texto dice «Terminó el dd/mm/aaaa» o «Terminó hoy», nunca «hace -N días».

**Pruebas (M1).**
- `python manage.py test contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **1101 pruebas, OK** (`contabilidad` sola: 331).
- `python manage.py test contabilidad --keepdb --tag concurrencia` → **12 pruebas, OK** (5 nuevas de CON-CRR-EJE).
- `python manage.py makemigrations --check --dry-run` → sin cambios. `python manage.py check` → sin problemas. Sin imports hacia apps de nivel mayor (A1).
- Pruebas de auditoría de `core` (`test_registro_auditoria`, `test_aud_cns_reg`, `test_auditoria_produccion`) → **74, OK**.
- **Experimentos de bloqueo** (los pedidos para esta tarea; quité cada protección, la prueba correspondiente falló y restauré el código): (A) sin releer el estado del ejercicio después de bloquearlo, en `registrar_asiento_automatico`, falló «el cierre primero y un asiento a la vez» (el asiento quedaba en un ejercicio cerrado); (B) con la verificación del estado **antes** de bloquear en `cerrar_ejercicio`, fallaron «dos cierres a la vez» y «la apertura primero y el cierre a la vez» (el cierre pasaba con datos viejos). El cierre bloquea una sola fila, así que no hay un «orden invertido» que probar: la protección que cuida la prueba es «bloquear y releer».
- Las pruebas nuevas se escribieron primero y se mostró que fallaban (pasos 1 y 3), y recién después se implementó.
- **Después de traer `main` (COM-04c, #79) a la rama** (avance directo, sin commit de merge; un solo conflicto, en `config/urls.py`, resuelto conservando las dos líneas): `python manage.py test contabilidad core comercial --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion` → **2570 pruebas, OK**; `python manage.py test contabilidad comercial --keepdb --tag concurrencia` → **81 pruebas, OK**; pruebas de auditoría de `core` → **74, OK**; `makemigrations --check` → sin cambios. Lo programado por COM-04c quedó idéntico al de `main`.

**Decisiones.** Ninguna nueva. Se aplicó D-102 (punto 1) a lo que significa «deja de aceptar asientos».

**Datos de la base de desarrollo.** No se tocó tu base de desarrollo: no se corrió `migrate`, ni el paso diario, ni ningún fragmento contra ella. Los fragmentos de la «Verificación a mano» se validaron en una prueba temporal contra una base `test_…` (ya borrada). Las pruebas usaron bases `test_…`.

### Informe

**Verifiqué:**
- El recorrido `RecorridoDeLibroYCierreTests` (dos pruebas, por rol y por estado del ejercicio): sin ejercicios → puesta en marcha → asiento automático y manual → libro cronológico, filtro por tipo, vista por cuenta, ficha (con y sin «quién lo registró»), plan → 403 para el Vendedor y el Agrónomo en cada pantalla → paso diario que deja el ejercicio «en cierre» → alerta del Panel (el Contador sí; el Gerente con Contador y el Vendedor no) → botón en «Ejercicios» → asiento dentro del «en cierre» → el Gerente con Contador y el Vendedor reciben 403 al cerrar → resumen (rango, 3 asientos, Debe y Haber de 1.250) → envío sin casilla (error) → cierre del Contador (cerrado, asociado, auditado, aviso de éxito) → «cerrado» (libro de consulta, sin alerta, no se cierra dos veces) → un automático con fecha de su rango va al abierto con la aclaración → saldos entre ejercicios (Caja arrastra; Ventas en cero). Y, en la segunda prueba, el Gerente sin Contador activo cierra y la asociación queda vacía.
- Migraciones: no hay (`makemigrations --check` sin cambios).
- Que los fragmentos de la «Verificación a mano» corren (prueba temporal, ya borrada).
- Los 2 experimentos de bloqueo.

**Lo cubre una prueba:** cada regla, postcondición y pantalla está en `test_con_cns_lgs.py`, `test_con_cns_pct.py`, `test_con_crr_eje.py`, `test_libro.py`, `test_libro_vistas.py`, `test_ejercicios_concurrencia.py` y `test_recorrido_libro_y_cierre.py` (cada paso de la «Verificación a mano» dice cuál).

**No pude verificar:**
- Todo lo que se ve en tu navegador y en tu base de desarrollo (pasos 1 a 28): no abro navegador ni toco esa base.
- **El paso de «navegador real» (paso 20):** el token CSRF, el encabezado `Origin` y el JavaScript del envío del formulario de cierre.
- Cómo se ve el registro del cierre en la pantalla «Auditoría» (paso 21) y el aspecto de las pantallas, de los desplegables propios y de las insignias.
- La aplicación en Render: no hay migraciones, pero conviene abrir «Contabilidad» en producción después del despliegue.
