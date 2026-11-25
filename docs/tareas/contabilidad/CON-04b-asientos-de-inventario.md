# CON-04b · Asientos de los ajustes de stock (reapertura)

Estado: hecha (PR #__, 24/11/2026; revisión a mano pendiente) | App: inventario | Rama: feature/con-04b-asientos-de-inventario | Ronda: Contabilidad 2

Depende de: **CON-02** (si no está en `main`, frená). INV-02 ya está.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Cada movimiento de ajuste de stock de insumos genera su asiento; la **carga inicial** acredita **Capital Inicial** (H3/H4).
Es chica: va bien justo después de CON-02, antes de que se carguen los insumos reales.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Asiento (origen · Debe / Haber · monto · fecha) |
|---|---|---|---|
| CMP-AJT-STK | Ajustar Stock de Insumo (post. e) | docs/casos_de_uso/inventario/ajuste_de_stock.md | Cada `MovimientoInsumo` de ajuste · positivo: Insumos en Stock / (Capital Inicial si el motivo es «carga inicial»; si no, Diferencias de Inventario de Insumos); negativo: al revés · cantidad × `referencia_precio`, redondeado · fecha del ajuste |

**Cambia el extracto (D-92 punto 7):** la carga inicial va contra Capital Inicial, no contra Diferencias de Inventario. La corrección entre lotes
no asienta (extensión 7d, como ya dice el extracto).

## Leer

- Casos de uso: `ajuste_de_stock.md`, solo lo marcado «Fuera de la ronda (D-45)» y la regla «Asiento de un ajuste».
- Decisiones: D-92 (puntos 2 a 7), D-86, D-52 (el movimiento es el origen), D-45, D-44.
- API: docs/api/asientos.md.
- Patrones: docs/patrones/asientos.md, docs/patrones/stock.md (sección 5).
- Reglas: .claude/rules/pruebas.md.
- Código a leer: `inventario/servicios/ajustes.py`, `inventario/models.py` (`MovimientoInsumo.MotivoAjuste`,
  `InsumoInvernadero.referencia_precio`); `contabilidad/servicios/asientos.py`; las pruebas `test_cmp_ajt_stk_*.py`.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: `docs/casos_de_uso/inventario/ajuste_de_stock.md` (la línea del haber de la carga inicial, citando D-92); al cerrar,
  M3 y `docs/disparadores.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: el asiento manual de apertura (Caja, Banco, deudas: lo hace el Contador con CON-REG-ASI).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **El asiento de cada movimiento de ajuste**, con la cuenta según el motivo y el sentido. — pruebas: `test_cmp_ajt_stk_motivos.py` (un caso por
   motivo y sentido; un ajuste cuyo valor redondea a $0,00 → sin asiento, H11), `test_cmp_ajt_stk_recuento.py` (un recuento que toca tres lotes: tres asientos).
2. **Concurrencia:** ajuste contra cierre del ejercicio. — pruebas: `test_cmp_ajt_stk_concurrencia.py`.
3. **Resumen del ajuste:** muestra el asiento que se registrará.

## Hecho cuando

- Una carga inicial de 10 kg a $500 de referencia deja Insumos en Stock 5.000 al Debe y Capital Inicial 5.000 al Haber; un recuento con faltante,
  Diferencias de Inventario al Debe.
- Comando de pruebas: `python manage.py test inventario contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test inventario --keepdb --tag concurrencia`.

## Verificación a mano

Esta tarea no tiene migraciones y no crea pantallas nuevas: el ajuste de stock ya existía (INV-02) y ahora, al confirmarlo, genera su asiento. Lo que cambia
y se ve: el **resumen del ajuste** muestra el asiento que se va a registrar, y el **libro de gestión** (CON-03a) muestra los asientos que quedan.
Los pasos 1 a 15 dejan datos en tu base de desarrollo (un insumo, lotes, movimientos y asientos); no son irreversibles, pero un asiento no se borra:
si querés volver a empezar, avisame y lo vemos (borrar datos de tu base se pregunta antes).

**Qué necesitás.**
- Estar en la rama `feature/con-04b-asientos-de-inventario`, con el entorno virtual activo (`.venv\Scripts\Activate.ps1`) y la base local encendida.
- Cuatro cuentas (cada una con su contraseña de prueba; no va en ningún archivo del repo): un **Agrónomo** activo **con un invernadero activo a su cargo**, el **Contador**, el
  **Gerente** y un **Capataz** (o un Vendedor). Si te falta alguna, creala entrando como Gerente a «Usuarios y seguridad» → «Nuevo usuario».
- Una ventana privada por rol (así no cerrás y abrís sesión cada vez).

### Preparación

**1. Levantá el servidor.** En PowerShell, en la carpeta del proyecto: `python manage.py runserver` y abrí `http://localhost:8000/`. (Sin migraciones nuevas: no hace falta `migrate`.)

**2. Mirá si ya hay un ejercicio contable.** Entrá como **Contador** (o Gerente) → «Contabilidad» → pestaña «Ejercicios».
- Si **no hay ninguno** («Todavía no hay ejercicios contables»): es el caso de los pasos 3 y 4 (el primer asiento abre el ejercicio solo; D-92 punto 2).
- Si **hay uno abierto**: saltá el paso 4 («ejercicio nuevo») y hacé el resto igual.

**3. Creá a mano el insumo de prueba.** Entrá como **Gerente o Agrónomo** (el que pueda) → «Inventario» → pestaña «Catálogo» → «Nuevo insumo»: nombre **«Fertilizante CON-04b»**, una
categoría cualquiera (por ejemplo «Nutrientes»), unidad **kg**, **sin** control de vencimiento. Después, en la misma fila, «Habilitar en un invernadero»: el invernadero del Agrónomo,
mínimo **0** y **precio de referencia $ 500,00**. (Si el insumo ya existe de otra verificación, usalo y comprobá que su precio de referencia sea $ 500,00.)

### Con la cuenta del Agrónomo (en una ventana privada)

**4. Carga inicial de 10 kg.** «Inventario» → «Existencias de insumos» → en la fila de «Fertilizante CON-04b», **Ajustar** (o «Cargar stock inicial» si es la primera vez). Elegí el motivo
**«Carga inicial»**, escribí **cantidad 10** y tocá **«Ver resumen»**. Tiene que verse, en «Qué se va a registrar»:
- Stock **0 → 10 kg**; «Valor del ajuste» **+ $ 5.000,00 (+10 kg × $ 500,00, precio de referencia)**.
- Un renglón **«Asiento contable»**: **«Lote nuevo: Debe Insumos en Stock / Haber Capital Inicial · $ 5.000,00»**, y debajo «Se registra al confirmar, con la fecha de hoy».
- **No** tiene que decir «Solo informativo: el ajuste no genera asiento contable».
Todavía no se creó nada (recargá «Contabilidad» → «Libro de gestión» en otra ventana: sin asientos nuevos). *(Lo cubre `test_flujo_principal_calcula_el_resumen_con_valor_y_asiento_y_confirma` y `test_paso_12_el_resumen_trae_el_asiento_…`.)*

**5. Confirmá.** Tocá **«Confirmar ajuste»**. Vuelve a «Existencias de insumos» con el aviso **«Ajuste registrado: Fertilizante CON-04b queda con 10 kg en <tu invernadero>»**.
*(Lo cubre el recorrido `RecorridoDeAjusteConAsientoTests`.)*

**6. Rotura de 2 kg.** «Ajustar» otra vez, motivo **«Rotura o pérdida»**, el **lote** que acabás de cargar, **cantidad 2**, descripción «Se cayó la bolsa» → «Ver resumen». Tiene que decir stock **10 → 8 kg**, valor
**−$ 1.000,00** y el asiento **«Lote N: Debe Diferencias de Inventario de Insumos / Haber Insumos en Stock · $ 1.000,00»** (al revés que la carga). Confirmá: «queda con 8 kg».
*(Lo cubre `test_post_e_la_rotura_asienta_diferencias_de_inventario_contra_insumos_en_stock`.)*

**7. Recuento con faltante.** «Ajustar» → motivo **«Recuento físico»** → en el lote, **cantidad contada 7** (lo registrado es 8) → «Ver resumen»: diferencia −1 kg y asiento
**Debe Diferencias de Inventario de Insumos / Haber Insumos en Stock · $ 500,00**. Confirmá. Después hacé otro recuento con **«Agregar lote nuevo»** (cantidad **2**) sin cambiar el lote:
el resumen tiene que mostrar **«Lote nuevo: Debe Insumos en Stock / Haber Diferencias de Inventario de Insumos · $ 1.000,00»** (un recuento **no** va contra Capital Inicial). Confirmá.
*(Lo cubren `test_post_e_un_recuento_que_toca_tres_lotes_genera_tres_asientos` y `test_post_b_y_e_el_lote_nuevo_del_recuento_asienta_como_diferencia_…`.)*

**8. Corrección entre lotes: no asienta.** «Ajustar» → motivo **«Corregir entre lotes»**: sale del lote 1, pasa al lote nuevo del paso 7, **cantidad 1** → «Ver resumen»: tiene que decir
**«Sin valor: el stock total no cambia.»** y **«Sin asiento: la corrección entre lotes no cambia el valor del stock.»**. Confirmá. *(Lo cubre `test_post_f_la_correccion_entre_lotes_no_asienta`.)*

**9. Importe cero (opcional).** Cambiá el precio de referencia del insumo en el invernadero a **$ 0,01** («Inventario» → «Existencias de insumos» → modificar la existencia del insumo en ese invernadero) y hacé una **rotura de 0,001 kg**: el resumen dice
**«Sin asiento: el importe redondea a $ 0,00.»**, el ajuste se confirma igual y **no** aparece ningún asiento nuevo. Volvé a poner $ 500,00 después. (Un precio de referencia en $ 0 **no se puede cargar**: la base lo prohíbe.)
*(Lo cubre `test_regla_h11_con_el_precio_minimo_y_una_carga_chica_el_ajuste_se_registra_sin_asiento` y el recorrido.)*

### Con la cuenta del Contador y la del Gerente (ventanas privadas distintas)

**10. El libro.** «Contabilidad» → «Libro de gestión» (ejercicio abierto). Tienen que estar, en este orden, los asientos de los pasos 5, 6, 7 (dos) y no el de la corrección ni el del importe cero:
- «Ajuste de stock (carga inicial): Fertilizante CON-04b, lote N» · origen **«Movimiento de insumo»** · Debe «Insumos en Stock» **5.000,00** / Haber «Capital Inicial» **5.000,00**.
- «Ajuste de stock (rotura o pérdida): …» · Debe «Diferencias de Inventario de Insumos» **1.000,00** / Haber «Insumos en Stock» **1.000,00**.
- Los de recuento, con «(recuento físico)» en la descripción.
- Los números son correlativos, sin huecos. *(Lo cubre el recorrido.)*

**11. La ficha.** Tocá un asiento: fecha **de hoy**, el ejercicio, **«Origen: Movimiento de insumo»** y las dos líneas. **El origen no es un enlace**: inventario no tiene todavía pantalla de movimientos ni registra el enlace
(punto de extensión de CON-03a); queda anotado como tema abierto. La ficha **no** debe decir «Fecha del hecho…» (un ajuste es siempre de hoy, D-102).

**12. Por cuenta.** En el libro, filtrá por la cuenta «Capital Inicial»: ve solo la carga inicial (Haber 5.000,00). Filtrá por «Diferencias de Inventario de Insumos»: el saldo es la suma de los asientos de rotura y recuento.

### Roles y estados

**13. Quien no puede.** Entrá como **Capataz** (o Vendedor) y como **Agrónomo**: el menú **no** muestra «Contabilidad» y, si escribís a mano `http://localhost:8000/contabilidad/`, da **403**. El Agrónomo **de otro invernadero** que abra
`http://localhost:8000/inventario/ajuste/?invernadero=<id del invernadero ajeno>` recibe **403**. *(Lo cubren el recorrido y `AccesoAlAjusteVistaTests`.)*

**14. Sin ejercicio abierto (solo si el paso 2 dijo «ninguno»).** Es lo del paso 4: el **primer ajuste confirmado crea el ejercicio** («Contabilidad» → «Ejercicios»: uno «abierto» que empieza hoy) y su asiento es el **N.º 1**.
*(Lo cubre `test_d92_sin_ejercicio_el_ajuste_se_registra_abre_el_primero_y_muestra_el_valor`.)*

**15. Auditoría.** Como Gerente: «Auditoría» → buscá el ajuste del paso 6: el registro del ajuste (acción `ajuste_stock`) nombra entre sus afectados el **asiento**, y aparecen aparte el alta del asiento y la de sus dos movimientos contables.
*(Lo cubre `test_post_l_el_asiento_entra_en_los_afectados_del_ajuste_y_su_alta_la_audita_contabilidad`.)*

### Navegador real (obligatorio: el ajuste es un formulario que se envía)

**16. Navegador real.** Abrí «Ajustar stock» en una **ventana privada**, entrá como Agrónomo, completá una **carga inicial de 1 kg**, tocá **«Ver resumen»** y después **«Confirmar ajuste»**, **hasta el final**; después abrí el libro como Contador y comprobá
que el asiento está. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: el cliente de Django no ve el CSRF, el encabezado `Origin` ni el JavaScript.
Con **JavaScript desactivado** el resumen y la confirmación tienen que funcionar igual (cada botón es un envío común).

### Opcional

**17. Sin JavaScript y en un celular.** El resumen con el bloque «Asiento contable» tiene que leerse bien en un ancho de 360 px (el renglón se parte, no se sale de la tarjeta).

## Cierre

**Qué se hizo.**
- **El asiento de cada ajuste** (`inventario/servicios/ajustes.py`): `confirmar_ajuste` crea un asiento por cada `MovimientoInsumo` de **ajuste** (positivo o negativo) con `registrar_asiento_automatico`, en la misma transacción,
  después de crear los movimientos, mover el stock y reevaluar las alertas (el ejercicio es lo último que se bloquea, D-86 punto 2). Cuentas (D-92 punto 7): positivo con motivo «carga inicial» → Debe Insumos en Stock / Haber **Capital Inicial**;
  los demás positivos → Haber Diferencias de Inventario de Insumos; negativos, al revés. Importe = cantidad × `referencia_precio`, `ROUND_HALF_UP` a dos decimales; importe 0 → sin asiento y sin error (H11). La corrección entre lotes no asienta (postcondición f).
  El asiento entra en los `afectados` del registro `ajuste_stock` (no se audita aparte). Descripción: «Ajuste de stock (<motivo>): <insumo>, lote N» (o «faltante sin lote»).
- **«Hoy» se recibe** (`calcular_ajuste` y `confirmar_ajuste` aceptan `hoy=`; sin él, `stock.hoy()`): la fecha del asiento es la del ajuste y el servicio no lee la hora solo. Como es siempre hoy, el asiento **nunca lleva la aclaración de H10** (D-102).
- **`Resultado.asientos`** (los asientos creados) y **`Resumen.asientos`** (`AsientoPrevisto(texto, debe, haber, importe)`: el asiento que se registrará, con los nombres de las cuentas, armado con la misma función que el asiento real).
- **Resumen del ajuste** (`_formulario.html`): reemplaza «Solo informativo: el ajuste no genera asiento contable» por el bloque «Asiento contable» (un renglón por movimiento; «Sin asiento…» para la corrección y para el importe cero).
- **Extracto** `docs/casos_de_uso/inventario/ajuste_de_stock.md`: el Haber de la carga inicial, citando D-92 (postcondición e y regla «Asiento de un ajuste»), y, al aplicar el M3, las marcas «Fuera de la ronda (D-45)» que esta tarea volvió falsas (precondiciones c y d, postcondición e, paso 14.4, la regla y la sección «Cómo se aplica en la ronda»; el tema abierto «Cuenta de la carga inicial» queda resuelto).
- Sin modelos, sin migraciones, sin dependencias nuevas y sin tocar `core/models.py`.

**Diferencias con la documentación** (van a `docs/temas_abiertos.md`; proponerlas en M3):
1. **«Con su enlace al movimiento»** (la «Verificación a mano» original): no se puede. Inventario no tiene pantalla de movimientos ni registra el enlace de origen (el punto de extensión de `contabilidad/extensiones.py` lo creó CON-03a y hoy nadie lo usa). La ficha muestra «Movimiento de insumo» sin enlace.
2. **Referencia en cero:** la «Verificación a mano» y el pedido hablaban de un insumo con precio de referencia en cero; la base lo prohíbe (CHECK `insumo_invernadero_precio_positivo`). El importe cero sale de redondear (0,001 kg × $ 0,01).
3. **El valor del resumen y el asiento se redondean distinto:** el «Valor del ajuste» se redondea una sola vez sobre la diferencia total del recuento (regla «Valor del ajuste») y cada asiento se redondea por movimiento (D-92 punto 5). Con varios movimientos y precios con centavos pueden diferir en centavos.
4. **La prueba de concurrencia «ajuste contra cierre del ejercicio»** no puede esperar que el ajuste falle (D-102): se plantea como «el ajuste termina bien y su asiento queda en el ejercicio que corresponde» (ver pruebas).
5. **Las marcas «Fuera de la ronda (D-45)» del extracto** (precondiciones c y d, postcondición e, paso 14.4, regla «Asiento de un ajuste», la mención del asiento en el resumen y la sección «Cómo se aplica en la ronda») quedaron falsas con esta tarea. «Permitido» solo dejaba tocar el haber de la carga inicial, así que se propusieron en el M3 y se aplicaron con tu visto bueno.

**Pantallas: lo que se corrigió del prototipo (D-61).**
1. El resumen del prototipo no mostraba el asiento (el prototipo es anterior a la contabilidad); se agregó el bloque «Asiento contable» con las cuentas por su nombre y el importe, según el paso 3 de la tarea y la postcondición e. Con tres casos que el prototipo no tenía: el asiento de cada movimiento, «Sin asiento» para la corrección y «Sin asiento» para el importe $ 0,00.

**Pruebas (M1).**
- `python manage.py test inventario contabilidad --keepdb --exclude-tag concurrencia --exclude-tag migracion` (en serie) → **1485 pruebas, OK**.
- `python manage.py test inventario --keepdb --tag concurrencia` → **54 pruebas, OK** (6 nuevas de CON-04b).
- `python manage.py test produccion.tests.test_aplicaciones_concurrencia inventario.tests.test_prod_baj_var --keepdb` → **35, OK** (los otros que llaman al servicio de ajuste).
- **Después de traer `main` a la rama** (COM-05a1, #81, y CMP-04, #82; avance directo, sin commit de merge ni conflictos; llegaron `comercial` 0008, `contabilidad` 0006 y `core` 0040 y 0041): `python manage.py test inventario contabilidad compras --noinput --exclude-tag concurrencia --exclude-tag migracion` → **2464 pruebas, OK**; `python manage.py test inventario contabilidad compras --keepdb --tag concurrencia` → **101 pruebas, OK**; `makemigrations --check` → sin cambios.
- **Con `--parallel`** el comando de la tarea falla en esta máquina antes de correr con `UniqueViolation … maestros_provincia_id_georef_key` en `test_ajuste_vistas` (carga de Georef en los clones). **Pasa igual en `main` sin mis cambios** (lo comprobé con `git stash`): no es de esta tarea; el CI arranca de una base nueva.
- Las pruebas del paso 1 se escribieron primero y se mostró que fallaban (18 de 68) antes de implementar. Las de concurrencia pasaron al escribirlas, porque el bloqueo es de `contabilidad` (ya cubierto por CON-02) y el paso 1 ya estaba hecho; no se hicieron experimentos de bloqueo (no los pide la tarea).
- Pruebas existentes que cambiaron (sin debilitarlas): `test_post_l_los_movimientos_no_se_auditan_uno_por_uno` (cuenta los registros no contables y exige los contables esperados), `test_d45_…` → `test_d92_sin_ejercicio_el_ajuste_se_registra_abre_el_primero_…`, y en `test_ajuste_vistas.py` la aserción «no genera asiento contable» pasó a afirmar las cuentas y el importe. `BaseDeAjustes` y `AjusteVistaBase` heredan de `PlanDeCuentasMixin`; `CmpAjtStkConcurrenciaTests.setUp` llama a `asegurar_plan_de_cuentas()`.

**Decisiones.** Ninguna nueva (D-92 puntos 2 a 7, D-86 y D-102).

**Datos de la base de desarrollo.** No se tocó tu base de desarrollo: no se corrió `migrate`, ni `runserver`, ni ningún fragmento contra ella. Las pruebas usaron bases `test_…` (se recrearon con `--noinput` una vez, por una corrida paralela interrumpida).

### Informe

**Verifiqué:**
- El recorrido `RecorridoDeAjusteConAsientoTests` (por rol y por estado): sin ejercicio → carga inicial de 10 L a $ 500 (el resumen anticipa el asiento y confirmar lo crea, abriendo el primer ejercicio) → rotura de 2 L → ajuste de importe $ 0,00 (se registra, sin asiento) → los dos asientos con sus cuentas, importes y origen → el Contador y el Gerente ven el libro y la ficha («Movimiento de insumo», sin enlace) → 403 para el Capataz, el Vendedor y los Agrónomos.
- Migraciones: no hay (no se crearon modelos ni migraciones).
- Concurrencia: el ajuste contra el cierre del ejercicio en los cuatro cruces (el cierre primero o el ajuste primero, con el ejercicio vigente y con el abierto vencido), la numeración sin huecos de dos ajustes a la vez y el orden de bloqueos (el ejercicio último).

**Lo cubre una prueba:** cada paso de la «Verificación a mano» dice cuál (`test_cmp_ajt_stk_motivos.py`, `test_cmp_ajt_stk_recuento.py`, `test_cmp_ajt_stk_concurrencia.py`, `test_ajuste_vistas.py` y `test_recorrido_ajuste_con_asiento.py`).

**No pude verificar:**
- Todo lo que se ve en tu navegador y en tu base de desarrollo (pasos 1 a 17): no abro navegador ni toco esa base.
- **El paso de «navegador real» (paso 16):** el token CSRF, el encabezado `Origin` y el JavaScript del envío del formulario del ajuste.
- El aspecto del bloque «Asiento contable» (en el celular y en el ancho angosto) y el registro en la pantalla «Auditoría».
- Que el comando de pruebas de la tarea corra completo **con `--parallel`** en esta máquina (falla antes por el problema de Georef, que ya existía en `main`).
