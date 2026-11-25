# CON-03b · Asientos manuales y contraasientos

Estado: hecha en la rama, falta el PR | App: contabilidad | Rama: feature/con-03b-asientos-manuales-y-contraasientos | Ronda: Contabilidad 1

Depende de: **CON-03a** (las pantallas del libro y las fichas, donde viven las acciones) y CON-02. Si no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Contador (o el Gerente, si no hay Contador) puede registrar un **asiento manual** y **anular** un asiento con un
**contraasiento** (que el Gerente recibe como notificación). Con esto, la contabilidad queda utilizable sola, antes de que ninguna otra
operación del sistema genere asientos.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CON-REG-ASI | Registrar Asiento Manual | docs/casos_de_uso/contabilidad/asientos_manuales.md | Los atajos «asiento de apertura» y «venta previa» son precarga, sin código propio (extensiones 3a y 3b) |
| CON-CTR-ASI | Contraasentar Asiento | docs/casos_de_uso/contabilidad/asientos_manuales.md | La fecha del contraasiento cae en un ejercicio abierto o en cierre (C3): **manda el caso de uso, no el prototipo** |

## Leer

- Casos de uso: el extracto, completo, **incluida la sección «Cómo se aplica (código)»**.
- Modelo: docs/modelo/contabilidad.md (`AsientoContable`, `MovimientoContable`, «Tipo (derivado)»).
- Decisiones: D-84 (puntos 4 a 6 y 9), D-85, D-86, D-30, D-32, D-36, D-42, D-44, D-61.
- API: docs/api/asientos.md («Escritura: asiento manual, contraasiento y ejercicio»), docs/api/notificaciones.md.
- Patrones: docs/patrones/asientos.md (el orden de bloqueos: **el ejercicio va último**), docs/patrones/bloqueos.md,
  docs/patrones/auditoria.md, docs/patrones/abm.md.
- Pantallas: docs/prototipos/compras_contabilidad/ — `k_new`, `INIT.k_new`, `ACT.mvadd`, `ACT.mvdel`, `ACT.mvt`, `ACT['asi-ok']`, `k_contra`,
  `ACT['contra-ok']` (referencia, D-61).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CON-02 y CON-03a, `core/notificaciones.py` (`notificar_a_varios`, `excluir`), y un formulario con filas dinámicas del repo
  (si no hay, el patrón HTMX de `docs/patrones/abm.md`).

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: `core/models.py` solo si CON-02 no dejó alguna acción (`alta_asiento_contable`, `alta_movimiento_contable`) y su
  migración; al cerrar (M3), `docs/disparadores.md`, README de tareas y el plan de la ronda.
- Dependencias nuevas: ninguna.
- Fuera de alcance: los asientos automáticos de cada operación, los pagos, y cambiar el aviso del Vendedor (CON-04d).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Registrar asiento manual (servicio).** `registrar_asiento_manual` y `resumir_asiento_manual`, con las fechas, el importe cero, el balance y
   los errores por línea. — pruebas: `test_con_reg_asi.py` (cada regla, extensión y postcondición) con `verificar_invariantes_contables`.
2. **Contraasentar (servicio).** `contraasentar`, `resumir_contraasiento` y `datos_para_correccion`, el bloqueo del asiento antes del
   ejercicio, la notificación al Gerente y su respaldo sin Gerente. — pruebas: `test_con_ctr_asi.py`.
3. **Concurrencia.** `test_asientos_concurrencia.py` (los casos que enumera el extracto, en especial: dos contraasientos del mismo asiento).
4. **Pantallas.** El formulario con filas dinámicas y buscador de cuenta, el resumen, la confirmación, los atajos de apertura y venta previa,
   y la acción «Contraasentar» en la ficha (visible según `puede_registrar_asientos`). — pruebas: `test_asientos_vistas.py`.

Si el tiempo apremia, lo último que se recorta es: los atajos de apertura y de venta previa (se anota como disparador).

## Hecho cuando

- Un asiento manual válido se registra con número consecutivo y quedan auditados el asiento y cada movimiento; uno inválido no escribe nada.
- Un contraasiento invierte un asiento una sola vez, avisa al Gerente, y el asiento anulado queda marcado en el libro.
- El Gerente con un Contador activo ve el libro pero **no** las acciones, y el servicio le dice «Lo registra el Contador».
- Pruebas verdes (incluida concurrencia).
- Comando de pruebas: `python manage.py test contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test contabilidad --keepdb --tag concurrencia`.

## Verificación a mano

**Esta tarea tiene pantallas y formularios que se envían** (registrar un asiento y contraasentar): por eso lleva el paso de «navegador real» (el paso 39) y el de JavaScript desactivado (el 40). Nada de esto toca producción: es tu base local de desarrollo (`localhost:5433`).

**Aviso antes de empezar.**
- Un **asiento no se puede borrar ni editar** (a propósito: se corrige con un contraasiento). Todo lo que registres en esta verificación **queda en tu base** y en la auditoría. Si querés volver a empezar de cero, avisame y lo vemos (borrar datos de tu base de desarrollo se anota en el «Cierre»; el usuario administrador no se toca).
- **Los pasos 31 a 34 son opcionales e irreversibles** (dejan un ejercicio «en cierre» y, al final, uno «cerrado» que no se reabre). Hacelos al final y solo si no te importa ensuciar esa base. Los pasos 1 a 30 y 35 a 41 no dejan nada irreversible más allá de los asientos.
- La contraseña de las cuentas de prueba es la de siempre; no va en ningún archivo del repo.

**Qué necesitás.**
- Estar en la rama `feature/con-03b-asientos-manuales-y-contraasientos`, con el entorno virtual activo (`.venv\Scripts\Activate.ps1`) y la base local encendida.
- **Tres cuentas**: el **Gerente** (el que ya tenés), un **Contador** activo y un **Vendedor**. Si te falta alguna, creala entrando como Gerente a «Usuarios y seguridad» → «Nuevo usuario». Valores de ejemplo: Contador «Cora Díaz», `contador.prueba@example.com`; Vendedor «Vera Ríos», `vendedor.prueba@example.com`. Solo puede haber **un** Contador activo (si ya tenés uno de otra verificación, usá ese).
- **Tres ventanas privadas** del navegador, una por rol (así no cerrás y abrís sesión cada vez): **A** = Contador, **B** = Gerente, **C** = Vendedor.

### Preparación

**1. Levantá el servidor.** Esta tarea **no tiene migraciones**: si tu base está atrasada, `python manage.py migrate` aplica las de `main`, no las de esta tarea. En PowerShell, en la carpeta del proyecto:

```powershell
.venv\Scripts\Activate.ps1
python manage.py runserver
```

Abrí `http://localhost:8000/` en cada ventana privada.

**2. Mirá en qué estado está tu base de ejercicios.** En otra terminal PowerShell: `python manage.py shell` y pegá (con una línea en blanco al final, por el `for`):

```python
from contabilidad.servicios import ejercicios
for e in ejercicios.ejercicios_numerados(): print("Ejercicio", e.numero, "|", e.ejercicio.fecha_inicio_ejercicio, "al", e.ejercicio.fecha_cierre_ejercicio, "|", e.ejercicio.estado_ejercicio, "|", e.cantidad_de_asientos, "asientos")
```

- **No imprime nada:** seguí con el paso 3.
- **Imprime un ejercicio `abierto`** que ya empezó (con o sin asientos): salteá el paso 3. Si el abierto **ya venció** (su fecha de fin es anterior a hoy) y todavía no corriste el paso diario, igual podés seguir: registrar un asiento abre el siguiente solo.
- **Hay uno `en_cierre`:** ya tenés el estado de los pasos 31 a 33; hacé los pasos 1 a 30 igual (los asientos con fecha de hoy van al ejercicio que contenga hoy).

**3. (Solo si no hay ejercicios) Poné en marcha la contabilidad** con un primer ejercicio que empiece el 1 de enero del año en curso (así podés fechar asientos de meses anteriores). Por ejemplo, si estás en 2026:

```powershell
python manage.py poner_en_marcha_contabilidad --fecha-inicio 2026-01-01
```

Tiene que decir `Primer ejercicio creado: del 01/01/2026 al 31/12/2026.` (con el año que corresponda).

**4. Elegí los valores que vas a usar.** En esta guía, «hoy» es la fecha de tu computadora. Cuando un paso dice «una fecha de hace unos días» usá, por ejemplo, el día 1 de este mes. El primer asiento que registres va a ser el **N.º 1** si tu base no tiene asientos; si ya tiene, los números cambian y en los pasos leelos como «el de la ficha».

**5. Ventana A (Contador).** Entrá con el Contador. En el menú lateral tiene que aparecer **«Contabilidad»**. *(Lo cubre el recorrido, paso 1.)*

### Camino feliz: registrar un asiento manual (ventana A, Contador)

**6. El botón.** «Contabilidad» → pestaña «Libro de gestión». Arriba a la derecha tiene que haber un botón verde **«Registrar asiento»**. *(Lo cubre `test_el_libro_ofrece_registrar_asiento_al_contador_y_al_gerente_sin_contador`.)*

**7. El formulario vacío.** Tocá «Registrar asiento». Tiene que verse el título «Registrar asiento»; la sección «1 Qué pasó» con **Fecha = hoy** y «Descripción» vacía; la sección «2 Cuentas e importes» con **dos filas** vacías (la primera «Debe» y la segunda «Haber»); el botón «Agregar una fila»; arriba, «Precargar:» con dos botones («Asiento de apertura» y «Venta de producción previa»); y abajo «Revisar asiento» y «Cancelar». *(Lo cubre `test_flujo_principal_el_formulario_trae_hoy_dos_filas…`.)*

**8. El atajo de apertura (extensión 3a).** Tocá **«Asiento de apertura»**. Tiene que volver a mostrarse el formulario con la descripción **«Asiento de apertura»**, la primera fila con la cuenta **«1.1.01 · Caja»** (Debe) y la segunda con **«3.1.01 · Capital Inicial»** (Haber), con los **importes vacíos**. No se registra nada (andá al libro para comprobarlo). *(Lo cubre `test_ext_3a_el_atajo_de_apertura…`.)*

**9. El buscador de cuenta.** Hacé clic en el campo «Cuenta» de la primera fila, borrá lo que tiene y escribí `banc`: el navegador tiene que ofrecer **«1.1.02 · Banco c/c»** (la lista tiene las 19 cuentas del plan; escribir parte del código o del nombre filtra). Elegí «1.1.02 · Banco c/c» y volvé a poner «1.1.01 · Caja». *(La lista de cuentas la cubre `test_flujo_principal_el_formulario_trae…`; cómo la muestra el navegador, no: queda a tu criterio.)*

**10. Agregar y quitar filas.** Tocá **«Agregar una fila»**: aparece una tercera fila **sin perder lo que ya escribiste** y sin que la pantalla salte. En la tercera fila tocá el tachito («Quitar»): vuelve a haber dos y, con **dos filas, el tachito no aparece** (un asiento necesita al menos dos movimientos). Volvé a agregar una fila. *(Lo cubren `test_agregar_y_quitar_una_fila_con_htmx…` y `test_quitar_una_fila_no_deja_menos_de_dos`.)*

**11. Cargá la apertura.** Completá así:

| Cuenta | Va al | Importe |
|---|---|---|
| 1.1.01 · Caja | Debe | 1.500,00 |
| 1.1.02 · Banco c/c | Debe | 500,00 |
| 3.1.01 · Capital Inicial | Haber | 2.000,00 |

(El tipo se cambia con el desplegable.) Dejá la fecha de hoy y la descripción «Asiento de apertura». Tocá **«Revisar asiento»**.

**12. El resumen (pasos 4 y 5).** Tiene que verse «Revisá el asiento» con: **Fecha** (hoy), **Ejercicio** («Ejercicio 1 · 01/01/2026 al 31/12/2026 · abierto»), **Descripción**, la tabla con las tres cuentas (cada una con su tipo debajo: «Activo», «Activo», «Patrimonio neto»), los **Totales** (`$ 2.000,00` y `$ 2.000,00`) y **«Diferencia $ 0,00 · Balanceado»**. En el libro todavía **no** hay ningún asiento nuevo. Probá **«Volver a editar»**: vuelve el formulario con todo lo que escribiste. Tocá «Revisar asiento» otra vez. *(Lo cubren `test_flujo_principal_revisar_muestra_el_resumen…` y el recorrido, paso 4.)*

**13. Confirmar (pasos 6 a 8).** Tocá **«Confirmar y registrar»**. Tiene que llevarte a la **ficha del asiento N.º 1** con el aviso verde **«Asiento N.º 1 registrado en el ejercicio 1.»**, la insignia **«Manual»**, «Registrado por **Cora Díaz**» (con «Contador» debajo), el importe `$ 2.000,00`, la descripción y la tabla de movimientos con sus totales. Arriba a la derecha, el botón **«Contraasentar»**. *(Lo cubre el recorrido, paso 4.)*

**14. El libro.** Tocá «Libro de gestión» (la flecha de arriba): el asiento aparece con su descripción, sus tres movimientos y la insignia «Manual». Cambiá a **«Por cuenta»**, elegí «Caja»: el saldo es **`$ 1.500,00`**. *(Lo cubre el recorrido, paso 5.)*

### Errores de validación (ventana A): ninguno registra nada

Para cada uno, abrí «Registrar asiento» (formulario nuevo) y, **salvo lo que dice el paso**, cargá Caja al Debe y Capital Inicial al Haber por `100,00` con la descripción «Prueba». Tocá «Revisar asiento» (o «Confirmar» si ya estás en el resumen: el mensaje es el mismo). **El error tiene que salir junto al campo, en rojo, y lo escrito tiene que conservarse.** Al final de esta sección el libro tiene que seguir mostrando **un solo asiento**. *(Los cubre `test_asientos_vistas.py` y el recorrido, paso 6.)*

**15. Sin descripción (5a).** Borrá la descripción. Debajo del campo: **«La descripción es obligatoria: explicá el motivo del asiento.»**

**16. Debe distinto del Haber (5b).** Poné el Haber en `90,00`. Mensaje arriba de la tabla: **«El Debe ($ 100,00) y el Haber ($ 90,00) no coinciden: la diferencia es de $ 10,00.»**

**17. Importe inválido (5c).** Poné el Haber en `-100` (y probá también `10,005`). Debajo del importe: **«El importe tiene que ser un número mayor que cero, con hasta dos decimales.»**

**18. Cuenta que no existe (7a).** Escribí `xyz` en la cuenta del Haber. Debajo del campo: **«La cuenta contable xyz no existe en el plan de cuentas.»**

**19. Cuenta sin importe y fila vacía (5c).** Con las dos filas bien, tocá «Agregar una fila» y elegí una cuenta en la tercera **sin importe**: «Revisar» marca esa fila con el mensaje del importe (no la ignora). Después **borrá la cuenta** de esa fila (queda totalmente vacía): ahora «Revisar» sigue al resumen y, debajo de la tabla, avisa **«Se omitieron 1 fila con importe cero.»** (las filas vacías se omiten). *(Lo cubre `test_ext_5c_una_cuenta_elegida_sin_importe…`.)*

**20. Fecha futura (5e).** Con todo bien, poné una **fecha de mañana** (el calendario no deja elegirla con el mouse; escribila con el teclado). Junto a la fecha: **«La fecha dd/mm/aaaa no admite un asiento: es posterior a hoy (dd/mm/aaaa) y un asiento no puede llevar una fecha posterior a hoy.»**

**21. Sin fecha o fecha anterior al primer ejercicio (5e).** Borrá la fecha (tecla Supr dentro del campo): **«Indicá una fecha válida.»** Después poné una fecha **anterior al inicio de tu primer ejercicio** (por ejemplo, el 1/1 del año anterior): **«La fecha … no admite un asiento: es anterior al primer ejercicio contable, que empieza el 01/01/2026.»**

### Contraasiento (ventana A, Contador; ventana B, Gerente)

**22. El botón (paso 1).** Abrí la ficha del asiento N.º 1 y tocá **«Contraasentar»**.

**23. El formulario (pasos 2 y 3).** Tiene que verse «Contraasentar el asiento N.º 1» con un aviso amarillo («Un asiento no se modifica ni se borra: se lo anula con otro asiento que hace lo contrario… Se avisa al Gerente.»); «1 Qué se anula» (asiento, fecha, importe `$ 2.000,00`, descripción); «2 Cómo queda el contraasiento» con la tabla **invertida** (Caja y Banco ahora en la columna **Haber**, Capital Inicial en la columna **Debe**) y la **fecha de hoy**; «3 Motivo» vacío. *(Lo cubre `test_flujo_principal_los_movimientos_del_contraasiento_salen_invertidos`.)*

**24. Sin motivo (3a).** Con el motivo vacío tocá «Revisar contraasiento»: **«El motivo es obligatorio: contá por qué se anula el asiento.»** junto al campo, y la fecha se conserva. *(Lo cubre `test_ext_3a_falta_el_motivo…`.)*

**25. Resumen y confirmación (pasos 4 a 8).** Escribí el motivo **«Se cargó el Banco de más»** y, como fecha, **el día 1 de este mes** (o la fecha de hoy si preferís). Tocá «Revisar contraasiento»: «Revisá el contraasiento del asiento N.º 1», con «Se anula: Asiento N.º 1 — quedará marcado como anulado», la fecha, el ejercicio, el motivo y la tabla invertida. En el libro todavía no hay contraasiento. Tocá **«Volver a editar»** (conserva fecha y motivo) y después «Revisar» y **«Confirmar el contraasiento»**. Tiene que llevarte a la ficha del **contraasiento N.º 2**, con el aviso verde **«Asiento N.º 1 anulado con el contraasiento N.º 2.»**, la insignia «Contraasiento», un cuadro «Este contraasiento anula el asiento N.º 1: Asiento de apertura» y otro verde: **«Quedó registrado el contraasiento. ¿Registrás ahora el asiento correcto? Registrar el asiento correcto»**. *(Lo cubre el recorrido, paso 10.)*

**26. El aviso al Gerente (postcondición d, ventana B).** Entrá con el Gerente a otra ventana privada. En la **campana** (arriba) tiene que haber una notificación sin leer; abrila, pestaña «Notificaciones»: **«Contraasiento N.º 2 del asiento N.º 1»** con el detalle **«Lo registró Cora Díaz el dd/mm/aaaa. Motivo: Se cargó el Banco de más»** (la fecha es la que pusiste en el contraasiento). *(Lo cubre `test_post_d_se_notifica_al_gerente_con_el_texto_del_extracto`.)*

**27. El asiento anulado (ventana A).** Abrí la ficha del N.º 1: arriba una alerta roja **«Anulado. Lo anula el asiento N.º 2 del dd/mm/aaaa.»**, la insignia «Anulado» y **ya no está el botón «Contraasentar»**. En la ficha del N.º 2 (el contraasiento) tampoco hay botón. Ahora, **a mano, escribí la dirección** `http://localhost:8000/contabilidad/asientos/<ejercicio>/1/contraasentar/` (copiá de la barra de la ficha el número del ejercicio y agregá `contraasentar/`): tiene que decir **«Este asiento no se puede contraasentar»** y **«Ya está anulado por el contraasiento N.º 2»** con el enlace. Probá lo mismo con la del N.º 2: **«Es un contraasiento: un contraasiento no se anula.»** *(Lo cubren `test_ext_1b_…` y el recorrido, pasos 11 y 18.)*

**28. El asiento correcto (paso 8, C4).** Volvé a la ficha del contraasiento N.º 2 (con `?corregir=1` al final de la dirección si ya no ves el cuadro verde) y tocá **«Registrar el asiento correcto»**. El formulario viene **precargado** con las **líneas del asiento anulado** (no las invertidas: Caja y Banco al Debe, Capital Inicial al Haber), la descripción **«corrección del asiento N.º 1»** y un cuadro azul («Cargamos las mismas cuentas e importes del asiento N.º 1. Cambialos por los correctos.»). Cambiá el Banco a `0,00` borrando su cuenta, la Caja a `1.500,00` y el Capital Inicial a `1.500,00`; revisá y confirmá: queda el **asiento N.º 3**, «Manual», **sin ningún vínculo** con el contraasiento. *(Lo cubren `test_c4_…` y el recorrido, paso 12.)*

**29. Filtros del libro.** En el libro, filtrá **Tipo = «Contraasientos»** (solo el N.º 2) y **Anulados = «Solo anulados»** (solo el N.º 1).

**30. Un asiento automático (opcional).** Si tu base tiene alguno (por ejemplo, de una recepción o un pago de compras), abrí su ficha, tocá «Contraasentar»: el formulario trae además la advertencia **«Es un asiento automático: el contraasiento corrige el libro de gestión, pero no anula la operación que lo originó.»** Si no tenés ninguno, saltealo. *(Lo cubre `test_flujo_principal_para_un_asiento_automatico_advierte…`.)*

### Estados del ejercicio (opcional e irreversible: pasos 31 a 34)

**31. Dejá un ejercicio «en cierre».** En PowerShell, con el día siguiente al fin de tu ejercicio abierto (si termina el 31/12/2026, es el 2027-01-01):

```powershell
python manage.py proceso_diario --solo abrir_ejercicio --fecha 2027-01-01
```

Tiene que decir que el ejercicio pasó a «en cierre» y que se abrió el siguiente. En «Contabilidad» → «Ejercicios» el primero aparece **«en cierre»** (y el Contador ve «Cerrar ejercicio»). *(Lo cubre `test_con_abr_eje.py`.)*

**32. Registrar en el ejercicio en cierre (5d).** «Registrar asiento» con fecha de hoy (que sigue dentro del ejercicio en cierre): en el resumen tiene que aparecer **«Va a un ejercicio en cierre»** y el asiento entra con **la numeración de ese ejercicio**. Hacé lo mismo con «Contraasentar» sobre uno de sus asientos (3b). *(Lo cubren los pasos 7 y 13 del recorrido.)*

**33. Cerrar el ejercicio (irreversible).** «Ejercicios» → «Cerrar ejercicio» → casilla → confirmar (CON-03a). Después **«Registrar asiento» con fecha de hoy se rechaza**: **«La fecha … no admite un asiento: pertenece al ejercicio del … al …, que está cerrado y ya no recibe asientos.»** (porque tu «hoy» real cae en ese ejercicio). Lo mismo con «Contraasentar» y una fecha de ese ejercicio. *(Lo cubre el recorrido, paso 16.)*

**34. Contraasentar un asiento de un ejercicio cerrado.** Con tu fecha real no se puede probar (todas las fechas hasta hoy caen en el ejercicio cerrado y el abierto empieza en el futuro). **Lo cubre una prueba** (recorrido, paso 17: un asiento de un ejercicio cerrado se contraasienta con fecha en el abierto) y es una de las diferencias a revisar (ver «Cierre»).

### Roles (ventanas B y C)

**35. Gerente con Contador activo (solo lectura).** En la ventana B (Gerente): «Contabilidad» → «Libro de gestión»: **no hay botón «Registrar asiento»**; en su lugar, **«Lo registra el Contador. Los asientos manuales los carga él.»** En la ficha de un asiento: sin «Contraasentar» y con **«Lo registra el Contador: contraasentar un asiento es de él.»** Escribí a mano `http://localhost:8000/contabilidad/asientos/nuevo/`: no hay formulario, solo **«Lo registra el Contador»**. Escribí a mano la dirección `…/contraasentar/` de un asiento: **«Prohibido (403)»**. *(Lo cubren `test_ext_1a_el_gerente_con_contador_activo…` y el recorrido, paso 8 y el segundo recorrido.)*

**36. Vendedor.** En la ventana C (Vendedor): en el menú **no** hay «Contabilidad». Escribí a mano `/contabilidad/asientos/nuevo/` y una dirección `…/contraasentar/`: **403** en las dos. *(Lo cubre `test_regla_quien_registra_el_vendedor_recibe_403` y el tercer recorrido.)*

**37. Sin sesión.** En una ventana privada nueva (sin iniciar sesión) escribí `/contabilidad/asientos/nuevo/`: te lleva a **«Iniciar sesión»**. *(Lo cubre el tercer recorrido.)*

**38. Gerente sin Contador activo (opera) y la auditoría.** Como Gerente, en «Usuarios y seguridad» abrí al Contador → **«Dar de baja»** (se puede reactivar después). Recargá el libro (ventana B): ahora **sí** aparece «Registrar asiento». Registrá un asiento cualquiera (p. ej. Caja `10,00` al Debe y Capital Inicial `10,00` al Haber, «Prueba del Gerente») y contraasentalo. **El Gerente no recibe ninguna notificación de lo suyo** (la campana de la ventana B no suma ninguna). En «Auditoría» (ventana B): hay registros **«Alta de asiento contable»** y **«Alta de movimiento contable»** de «Cora Díaz — Contador» (los de los pasos 13 y 25) y los del Gerente con rol «Gerente»; el del contraasiento muestra la fila **«Asiento que anula»**. Al terminar, **reactivá al Contador**. *(Lo cubre el segundo recorrido y `test_post_e_se_audita_…`.)*

**39. Navegador real (obligatorio: hay formularios que se envían).** Abrí **una ventana privada nueva** (sin sesión), **iniciá sesión como Contador**, y hacé el **recorrido completo hasta el final**: «Registrar asiento» → completar → «Revisar asiento» → «Confirmar y registrar»; después, sobre ese asiento, «Contraasentar» → motivo → «Revisar contraasiento» → «Confirmar el contraasiento». Cada envío tiene que mostrar el resultado esperado (los pasos 13 y 25). Si aparece una página **«Prohibido (403)»** o **«Verificación CSRF fallida»**, o un error en la consola del navegador (F12 → «Consola»), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Fijate además que, con JavaScript, **«Agregar una fila» y el tachito no recargan la página ni la hacen saltar**, y que el botón de envío muestra «Revisando…», «Registrando…» mientras envía.

**40. Con JavaScript desactivado (opcional).** En la ventana privada: F12 → ⚙ «Configuración» (o la paleta de comandos con Ctrl+Shift+P) → «Desactivar JavaScript», y recargá. Tiene que seguir funcionando **todo**: «Agregar una fila» y el tachito vuelven a dibujar la página (con lo escrito), el campo de cuenta sigue ofreciendo la lista del plan, el tipo se elige en un desplegable nativo, y «Revisar» / «Confirmar» registran igual.

**41. En un celular (opcional).** Abrí la pantalla desde el celular (o achicá la ventana a unos 400 px): la tabla de filas se ve completa (con scroll horizontal si hace falta), los campos se pueden tocar y los botones no se superponen.

## Cierre

**Qué se hizo.**
- **Asiento manual** (`contabilidad/servicios/asientos.py`): `registrar_asiento_manual` (permisos → validación sin bloquear con **errores por línea y juntos** → autorrecuperación del ejercicio → fecha → revalidación del actor → **bloqueo del ejercicio al final** con revalidación de estado y rango → alta y auditoría), `resumir_asiento_manual` (mismas validaciones, sin escribir ni bloquear; con el abierto vencido calcula en memoria el ejercicio que se abriría con `ejercicios.destino_previsto`), y el auxiliar `_crear_y_auditar` que comparten el automático, el manual y el contraasiento (refactor sin cambio de conducta: lo confirman las 92 pruebas de CON-02).
- **Contraasiento** (mismo archivo): `contraasentar` (permisos, motivo, **bloqueo del asiento antes que el del ejercicio**, verificación de «anulable» con el asiento bloqueado, movimientos invertidos, vínculo `anula`, auditoría con `cambios.anula` y **aviso al Gerente** con `notificar_a_varios(..., excluir=actor)` dentro de la transacción; sin Gerente activo deja `datos.aviso_al_gerente` en la auditoría), `resumir_contraasiento`, `datos_para_correccion` (la precarga del asiento correcto) y `_bloquear_asiento`.
- **Errores** (`contabilidad/errores.py`): `ErrorContable.errores` (lista) y `ErroresContables` (varios errores de campo juntos, patrón ABM).
- **Fechas** (`contabilidad/servicios/ejercicios.py`): los mensajes de fecha del manual y del contraasiento ahora explican el motivo (el de «cerrado» nombra el ejercicio y su rango) y `destino_previsto(fecha, hoy=)`, de solo lectura.
- **Pantallas** (`views.py`, `forms.py`, `urls.py`, `templates/contabilidad/`, `static/.../contabilidad.css`): `asiento_nuevo` y `contraasiento` con sus plantillas (`asiento_nuevo.html`, `_asiento_formulario.html`, `asiento_resumen.html`, `contraasiento.html`, `contraasiento_resumen.html`), los botones «Registrar asiento» (libro) y «Contraasentar» (ficha) según `puede_registrar_asientos`, y la oferta del asiento correcto. Todo funciona sin JavaScript; con HTMX, agregar y quitar una fila solo redibuja el cuerpo del formulario.
- **Fuera de la app** (autorizado): `core/models.py`, solo el diccionario `RegistroAuditoria.ETIQUETAS`, con dos líneas: `anula` → «Asiento que anula» y `aviso_al_gerente` → «Aviso al Gerente». Sin migración y sin acción nueva.
- **Pruebas de CON-03a cambiadas, no debilitadas** (afirmaban que las acciones estaban escondidas «hasta CON-03b», una marca con vencimiento): `test_libro_vistas.py::test_sin_acciones_de_asientos_manuales_hasta_con_03b` pasó a `test_las_acciones_de_asientos_manuales_se_muestran_solo_a_quien_puede_registrar` (quién ve cada acción), y en `test_recorrido_libro_y_cierre.py` el paso 5 ahora afirma que el Contador **ve** «Contraasentar».

**Diferencias con la documentación** (van a `docs/temas_abiertos.md`):
1. **Orden de la fecha y la autorrecuperación (decisión tuya del 25/11/2026).** El extracto de CON-REG-ASI pone «validar la fecha» (paso 2) antes de la «autorrecuperación» (paso 3). Se invirtió: D-84 punto 2 pesa más que el extracto y, si no, una fecha válida se rechazaría como «ejercicio cerrado» cuando el abierto venció y nadie abrió el siguiente. Vale para `registrar_asiento_manual` y `contraasentar`; los `resumir_*` **no escriben nunca**.
2. **`faltan_movimientos` es un error en el asiento manual.** D-84 punto 6 dice que con menos de dos movimientos «el servicio devuelve `None`, no falla»; eso vale para el **automático**. El extracto de CON-REG-ASI (extensión 5c y «Cómo se aplica») pide un error para el manual. Se pide aclararlo en D-84.
3. **Contraasentar un asiento de un ejercicio cerrado se permite.** `docs/disparadores.md` («Cuando se programe CON-03b», punto 1) dice que «Contraasentar» se muestra «solo si el asiento puede anularse y su ejercicio no está cerrado», y el prototipo oculta el botón (`e.est!=='cerrado'`). El caso de uso dice que se anula «cualquier asiento» que no sea contraasiento ni esté anulado, y C3 deja elegir la fecha en cualquier ejercicio abierto o en cierre; manda el caso de uso (L7). Lo fija `test_regla_que_se_anula_un_asiento_de_un_ejercicio_cerrado_tambien_se_anula`. **A confirmar.**
4. **La fecha del aviso al Gerente es la del contraasiento**, no la de hoy (el extracto dice «el dd/mm/aaaa» sin aclarar cuál).
5. **Funciones que no estaban en `docs/api/asientos.md`:** `asientos.resumir_asiento_manual`, `resumir_contraasiento`, `datos_para_correccion`, `ejercicios.destino_previsto` y `ErroresContables`/`ErrorContable.errores` (los resúmenes y la precarga sí los nombraba «Cómo se aplica», pero sin su forma). Se agregaron a esa API (tabla de «Escritura» y la regla 6 de «Reglas para quien llama»).
6. **Texto de la ficha de un asiento de un ejercicio cerrado:** se mantiene «es solo de consulta» (lo exige una prueba de CON-03a) y, a quien puede contraasentar, se le suma que puede corregirlo con una fecha de un ejercicio abierto o en cierre.
7. **El motivo del contraasiento se guarda tal cual como descripción** (el prototipo lo guardaba como «Contraasiento del asiento N.º X: motivo»); la tarea dice que el motivo **es** la descripción. Máximo 300 caracteres (el modelo), no 150 como el prototipo.
8. **Una fila con cuenta y sin importe se marca como error** (en vez de omitirse en silencio) y una fila totalmente vacía se omite (H11); el extracto solo habla de importe cero.
9. **Los atajos precargan dos filas** (Caja/Capital Inicial y Caja/Ventas); el extracto dice «sugieren cuentas» y no cuántas.

**Pantallas: lo que se corrigió del prototipo (D-61).**
1. **Cuenta con buscador**, no un desplegable (`ctaSelH`): un campo con la lista del plan (`<datalist>`), que filtra al escribir sin validar y funciona sin JavaScript (el plan puede crecer, criterio del estudiante).
2. **Sin balance en vivo.** `balrow` del prototipo recalcula Debe, Haber y diferencia mientras se escribe; `.claude/rules/interfaz.md` prohíbe validar y recalcular al tipear. El balance se muestra en el resumen.
3. **Resumen y confirmación en una pantalla aparte.** El prototipo registraba directo con «Registrar asiento» (`asi-ok`); el paso 5 de CON-REG-ASI y el 4 de CON-CTR-ASI piden un resumen antes de confirmar. Con «Volver a editar».
4. **Los dos atajos** («Asiento de apertura» y «Venta de producción previa») no están en el prototipo; los piden las extensiones 3a y 3b y «Cómo se aplica».
5. **Errores por fila y juntos**, junto a su campo y conservando lo escrito (el prototipo marcaba con `bad` y un resumen de errores); textos del servicio con voseo («Elegí la cuenta.», «explicá el motivo»).
6. **Contraasiento:** agregué el resumen previo, la advertencia C5 para un asiento automático y la pantalla «Este asiento no se puede contraasentar» con el enlace al contraasiento (extensión 1b; el prototipo mostraba un vacío genérico). **El botón ya no se oculta en un ejercicio cerrado** (ver la diferencia 3).
7. **El aviso al Gerente** usa el título y el detalle del extracto («Contraasiento N.º X del asiento N.º Y» / «Lo registró … el … Motivo: …»), no el del prototipo («Asiento contraasentado · N.º»).
8. **La oferta de registrar el asiento correcto** va en la ficha del contraasiento con `?corregir=1` (el prototipo lo pasaba con el estado `S.p.nuevo`); el formulario se precarga con `?corrige=<id>` y avisa que las cuentas son las del original.
9. **Estados sin permiso:** el Gerente con un Contador activo ve «Lo registra el Contador» en el libro, en la ficha y en el formulario (el prototipo ocultaba el botón y mostraba un vacío en `k_new`); un acceso directo por dirección es 403.
10. **Desplegables propios** (D-24) para «Debe/Haber», fecha con el selector del navegador y respaldo sin JavaScript en cada botón (agregar, quitar, atajos, revisar).
11. **Selector de rol e interruptor «Hay un Contador activo»:** no se copiaron (solo prototipo).

**Pruebas (M1).**
- `python manage.py test contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **1246 pruebas, OK** (`contabilidad` sola: 475).
- `python manage.py test contabilidad --keepdb --tag concurrencia` → **19 pruebas, OK** (7 nuevas).
- `python manage.py makemigrations --check --dry-run` → **No changes detected**. `python manage.py check` → sin problemas. Sin imports hacia apps de nivel mayor (A1).
- **Pruebas nuevas: 151.** `test_con_reg_asi.py` (51), `test_con_ctr_asi.py` (44), `test_asientos_vistas.py` (46), `test_asientos_concurrencia.py` (7 nuevas, en el mismo archivo y sin tocar las 4 de CON-02) y `test_recorrido_asientos_manuales.py` (3). Las de los pasos 1 y 2 se escribieron primero y se mostró que fallaban (51 y 44 pruebas con `AttributeError`), y recién después se implementó. En el paso 2 se corrigió **una aserción de mi propia prueba** (`test_ext_6a…`: contaba asientos, pero el «otro usuario» se simulaba dentro de la transacción que el rechazo deshace); quedó el mensaje y la prueba de concurrencia real.
- **Experimentos de bloqueo** (la tarea toca bloqueos; cada variante solo en el archivo de trabajo, restaurado con `git checkout` y comprobado): (A) **orden invertido** (ejercicio antes que asiento) en `contraasentar` → fallan exactamente `test_regla_orden_de_bloqueos_el_contraasiento_ya_tiene_el_asiento_antes_de_pedir_el_ejercicio` y `…_no_tiene_el_ejercicio_hasta_haber_bloqueado_el_asiento`; (B) **sin bloqueo del asiento** → fallan `test_ext_6a_dos_contraasientos_del_mismo_asiento_a_la_vez_gana_uno_solo` y la primera de orden; (C) **sin bloqueo del ejercicio** → fallan 5 (las de numeración de manuales y de contraasientos distintos, manual contra cierre y dos de CON-02). Con el código restaurado, las 11 pasan.
- **Fusión con `main`:** `main` avanzó (COM-06a, #88). Con `git fetch` y un `git merge-tree` de solo lectura: **un solo archivo en común** (`core/models.py`), la fusión **no tiene conflictos** y en el archivo fusionado no queda ninguna clave repetida en `ETIQUETAS`. **No se hizo el merge** (lo hace una persona, `docs/patrones/trabajo_en_paralelo.md`): hay que hacer `git merge origin/main` y volver a correr las pruebas antes del PR.

**Decisiones.** Ninguna nueva. Se aplicaron D-84 (puntos 2, 4, 5, 6 y 9), D-85 (puntos 5 y 7), D-86, D-30, D-32, D-36, D-42, D-61 y D-102 (fechas). Las diferencias con el extracto (puntos 1 y 2 de arriba) se proponen como aclaración a D-84.

**Datos de la base de desarrollo.** No se tocó tu base de desarrollo: no se corrió `migrate`, ni el paso diario, ni ningún fragmento contra ella, y no se borró ningún dato. Las pruebas usaron bases `test_…`. Los comandos de los pasos 3 y 31 son los de CON-03a (`poner_en_marcha_contabilidad` y `proceso_diario --solo abrir_ejercicio --fecha`), que ya se verificaron ahí.

### Informe

**Verifiqué:**
- El recorrido `RecorridoDeAsientosManualesTests` (3 pruebas, por rol y por estado): **el Contador** → libro con «Registrar asiento» (el Gerente con Contador y el Vendedor no) → formulario → atajo de apertura → agregar fila → resumen → asiento N.º 1 → ficha y libro → 7 rechazos (descripción, desbalance, importe, cuenta, fecha futura, anterior al primer ejercicio, fecha vacía) → dos asientos en el ejercicio en cierre (numeración propia) → contraasiento (403 para los otros roles, formulario, sin motivo, resumen, confirmar) → aviso al Gerente → original anulado y sin botón → asiento correcto precargado → contraasiento en el ejercicio en cierre → fechas inválidas → cierre del ejercicio → rechazos con el ejercicio cerrado → contraasiento de un asiento de un ejercicio cerrado → asiento ya anulado → auditoría de cada asiento y movimiento; **el Gerente sin Contador activo** opera y no se avisa a sí mismo, y con un Contador activo vuelve a ser de solo lectura (403 en sus envíos); **sin acceso:** el Vendedor y el Agrónomo (403 en GET y POST), sin sesión (a «Iniciar sesión») y asiento inexistente (404).
- `makemigrations --check` y `check` sin cambios ni problemas; la fusión con `main` sin conflictos (solo lectura).
- Los 3 experimentos de bloqueo.

**Lo cubre una prueba:** cada regla, extensión y postcondición de CON-REG-ASI y CON-CTR-ASI está en `test_con_reg_asi.py` y `test_con_ctr_asi.py`; las pantallas en `test_asientos_vistas.py`; la concurrencia en `test_asientos_concurrencia.py`; el encadenado, en `test_recorrido_asientos_manuales.py` (cada paso de la «Verificación a mano» dice cuál).

**No pude verificar:**
- Todo lo que se ve en tu navegador y en tu base de desarrollo (pasos 1 a 41): no abro navegador ni toco esa base.
- **El paso de «navegador real» (paso 39):** el token CSRF, el encabezado `Origin` y el JavaScript de los envíos; cómo se comportan en un navegador el `<datalist>` del buscador de cuenta, HTMX al agregar y quitar filas (que no salte el scroll, `show:none`) y el botón «Revisando…».
- **El paso 40 (sin JavaScript)** y **el 41 (celular)**: el cliente de Django prueba el respaldo sin JavaScript (cada botón es un envío común), pero no cómo se ven.
- **El aspecto** de las pantallas nuevas (la tabla de filas, las insignias, los avisos) y la copia de «Debe/Haber» en el desplegable propio.
- **Los comandos de los pasos 3 y 31 contra tu base** (son los de CON-03a, no se corrieron acá).
- **Contraasentar un asiento de un ejercicio cerrado a mano** (paso 34): con una base real no se puede armar sin esperar a que cambie el año; lo cubre una prueba.
- **La aplicación en Render:** no hay migraciones, pero conviene abrir «Registrar asiento» en producción después del despliegue.
