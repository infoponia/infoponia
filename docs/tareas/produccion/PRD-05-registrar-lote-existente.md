# PRD-05 · Registrar Lote Existente

Estado: hecha (PR #__, 25/11/2026; revisión a mano pendiente) | App: produccion | Rama: feature/prd-05-registrar-lote-existente | Ronda: Contabilidad 2

Depende de: **CON-02** (el asiento) y PRD-03 (la bitácora; hecha). No depende de PRD-04. Si CON-02 no está en `main`, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). La pantalla no está en el prototipo: armala con el patrón de la siembra (D-61) y anotala en el «Cierre».

**Qué resuelve.** Al poner en marcha InfoPonia, el Agrónomo carga los lotes de plantas que ya estaban en los sectores (con su etapa actual y un
costo estimado), para seguir planificando sus transiciones y cosechas desde el sistema. Su valor entra contra **Capital Inicial**. Solo se puede
en un invernadero que todavía no tuvo siembras por el flujo normal.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-REG-LTE | Registrar Lote Existente | docs/casos_de_uso/produccion/lote_existente.md | Precondición d: no se programa (D-92 punto 2) |

## Leer

- Casos de uso: el extracto completo, incluida «Cómo se aplica (código)».
- Modelo: docs/modelo/produccion.md (`Siembra`, `Lote`, `OcupacionSector`, `Bitacora`).
- Decisiones: D-92 (punto 12), D-86, D-50, D-51, D-53, D-83, D-44, D-61.
- API: docs/api/asientos.md, docs/api/produccion.md (códigos de error).
- Patrones: docs/patrones/bloqueos.md («`produccion`» y «Contabilidad»), docs/patrones/costo_del_lote.md, docs/patrones/auditoria.md.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `produccion/models.py` (`ConCapataz`, `OrdenTrabajo`, `Siembra`, `Lote`, `OcupacionSector`, `Bitacora`); `produccion/servicios/siembras.py`
  (`planificar_siembra`, `_registrar_concrecion`: el modelo de escritura), `transiciones.py` (`_sectores_del_destino`), `lotes.py`, `bitacora.py`;
  las plantillas de la planificación de siembra.

## Límites

- Crea modelos: ninguno; cambia `Siembra` (`tipo_siembra`, `capataz` nulo) y `Bitacora.TipoEvento` → revisá docs/disparadores.md.
- Migraciones: una de `produccion` (los dos campos y los CHECK); una de `core`, solo de `choices`, con `registro_lote_existente`.
- Permitido fuera de la app: `core/models.py` (la acción) y su migración; al cerrar, M3, `docs/modelo/produccion.md` (los cambios de `Siembra` y
  `Bitacora`).
- Dependencias nuevas: ninguna.
- Fuera de alcance: partidas en cámara previas y cosechas previas (asiento manual del Contador); cambiar `TransicionEtapa`.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelo y migración.** — pruebas: `test_modelos_produccion.py` (amplía: los CHECK; las siembras existentes quedan `normal` y con Capataz).
2. **Lectura de la fecha de entrada** desde la carga inicial. — pruebas: `test_lotes_lectura.py` (amplía).
3. **Servicio** `lotes_existentes.py` con el asiento. — pruebas: `test_prod_reg_lte.py`, `test_prod_reg_lte_concurrencia.py`.
4. **Pantalla** (formulario, resumen, confirmación) y el filtro «Carga inicial» de la bitácora. — pruebas: `test_prod_reg_lte_vistas.py`,
   `test_prod_cns_bit.py` (amplía).

## Hecho cuando

- En un invernadero sin siembras, el Agrónomo carga un lote en Maduración en dos sectores con costo $12.000: el lote aparece en la lista, los
  agujeros bajan, la bitácora muestra «Carga inicial» y el libro tiene Productos en Proceso / Capital Inicial por $12.000; con costo $0, sin
  asiento. Planificar su cosecha usa la fecha de ingreso a Maduración cargada.
- Concretada una siembra normal, la acción desaparece para ese invernadero.
- Comando de pruebas: `python manage.py test produccion contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test produccion --keepdb --tag concurrencia`.

## Verificación a mano

Esta tarea tiene **migraciones** (`produccion` 0010 y `core` 0045: columnas y restricciones nuevas, nada de datos) y **una pantalla nueva** («Registrar lote existente»). Los pasos 1 a 27
dejan datos en tu base de desarrollo (un invernadero de verificación, sus sectores, dos lotes, una orden de transición y un asiento). Un asiento no se borra: si querés volver a empezar,
avisame y lo vemos (borrar datos de tu base se pregunta antes). **Usá un invernadero de verificación nuevo, no uno real:** el paso 27 concreta una siembra normal en él y, desde ese momento,
la acción «Registrar lote existente» **desaparece para ese invernadero y no vuelve** (es la regla del caso de uso, no un defecto).

**Qué necesitás.**
- Estar en la rama `feature/prd-05-registrar-lote-existente`, con el entorno virtual activo (`.venv\Scripts\Activate.ps1`) y la base local encendida (puerto 5433).
- Cuatro cuentas, cada una con su contraseña de prueba (no va en ningún archivo del repo): el **Gerente**, el **Contador**, un **Agrónomo** que no tenga invernaderos y un **Capataz**. Si te falta alguna,
  entrá como Gerente a «Usuarios y seguridad» → «Nuevo usuario». Usá correos de prueba, por ejemplo `agronomo.carga@infoponia.com` y `capataz.carga@infoponia.com`.
- Una **variedad activa** cuyo ciclo tenga **Crecimiento y Maduración** (y una etapa después de Crecimiento, por ejemplo Floración o Maduración). Si ya probaste las tareas de producción, tenés una:
  mirá en «Producción» → «Cultivos y variedades» que la variedad esté activa y que su ciclo tenga esas etapas. Si no tenés ninguna, creala ahí (cultivo y variedad, con ese ciclo).
- Una ventana privada por rol (así no cerrás y abrís sesión cada vez).

### Preparación

**1. Aplicá las migraciones.** En PowerShell, en la carpeta del proyecto:
```powershell
python manage.py migrate
python manage.py showmigrations produccion core
```
Tienen que aparecer aplicadas (`[X]`) **`produccion` 0010_carga_inicial_de_lotes** y **`core` 0045_carga_inicial_de_lotes**, y no puede aparecer ninguna con `[ ]`. Las siembras que ya tenías quedan como «Normal» y con su Capataz.
*(Lo cubre `test_d92_las_siembras_existentes_quedan_normales_y_con_capataz`; los CHECK, `test_d92_check_siembra_capataz_segun_tipo`.)*

**2. Levantá el servidor.** `python manage.py runserver` y abrí `http://localhost:8000/`.

**3. Creá el invernadero de verificación.** Entrá como **Gerente** → «Producción» → pestaña «Invernaderos» → «Nuevo invernadero»: nombre **«Invernadero Carga Inicial»**, tipo de dirección **Urbana**, cualquier provincia,
departamento y localidad de la lista (si no se llenan, tocá «Actualizar listas y datos de la dirección»), calle **«Calle Falsa»**, número **«123»**, **Agrónomo** = `agronomo.carga@infoponia.com`,
**Capataz** = `capataz.carga@infoponia.com`. «Crear invernadero». Tiene que aparecer en la lista con el estado «Activo».

**4. Creá sus sectores.** Entrá como el **Agrónomo nuevo** → «Producción» → «Invernaderos» → «Invernadero Carga Inicial» → pestaña de sectores → «Agregar sector», seis veces, siempre con **100 agujeros**:

| Nombre | Tipo de etapa |
|---|---|
| G-1 | Germinación |
| C-1 | Crecimiento |
| F-1 | Floración |
| FR-1 | Fructificación |
| M-1 | Maduración |
| M-2 | Maduración |

Un sector de cada tipo para que sirva cualquier ciclo. Tienen que quedar los seis activos, con 100 agujeros y sin plantas.

**5. Mirá que no haya siembras.** Todavía como Agrónomo: «Producción» → «Órdenes de trabajo». No tiene que haber ninguna orden de «Invernadero Carga Inicial» (si hay, ese invernadero no sirve: creá otro).

### Camino feliz: un lote en Maduración, en dos sectores, con costo $12.000

**6. La acción se ve.** Como **Agrónomo**: «Producción» → arriba a la derecha tiene que estar el botón **«Registrar lote existente»**. En «Invernaderos» → «Invernadero Carga Inicial» → pestaña **«Lotes activos»**: aparece el aviso
«Sin lotes activos… o registres un lote existente» y el botón **«+ Registrar lote existente»**.

**7. Elegí paso a paso.** Tocá «Registrar lote existente». En el desplegable «Invernadero» tienen que figurar solo los invernaderos tuyos sin siembras normales (el de verificación). Elegilo: se habilita «Variedad» y **no aparece ningún error**.
Elegí la variedad: se habilita «Etapa actual del lote» (las etapas del ciclo, con sus días). Elegí **Maduración**: aparecen «Fecha de siembra», «Fecha de ingreso a la etapa actual», «Cantidad de plantas», «Costo estimado del lote ($)» (con **0**)
y «Distribución por sector» con **M-1 (libres: 100)** y **M-2 (libres: 100)**; G-1, C-1, F-1 y FR-1 no aparecen.
*(Lo cubre `test_pasos_4_y_6_con_todo_elegido_aparecen_los_campos_y_los_sectores_con_sus_libres`.)*

**8. Completá y mirá el resumen.** Fechas en el selector del navegador (o escribilas como `dd/mm/aaaa`). Para sacar las fechas, en PowerShell:
```powershell
(Get-Date).AddDays(-40).ToString("dd/MM/yyyy")   # fecha de siembra
(Get-Date).AddDays(-10).ToString("dd/MM/yyyy")   # ingreso a la etapa
```
Fecha de siembra = la de hace 40 días, ingreso = la de hace 10 días, plantas **180**, costo **12000**, M-1 **100**, M-2 **80**. Tocá **«Ver resumen»**. Tiene que mostrar: variedad, **Etapa actual: Maduración**, las dos fechas,
plantas 180, **costo estimado $12000,00** y **costo por planta $66,67**, «M-1: 100 (quedan 0 libres) · M-2: 80 (quedan 20 libres)» y **«Asiento contable: Debe Productos en Proceso / Haber Capital Inicial por $12000,00, con la fecha de hoy»**.
Aparece el botón «Confirmar registro». **Nada se guardó todavía:** en «Producción» → «Órdenes de trabajo» no hay ninguna orden nueva.
*(Lo cubre `test_paso_8_ver_resumen_muestra_todo_con_el_asiento_y_no_escribe`.)*

**9. Cambiar un dato después del resumen no se confirma a ciegas.** Sin tocar «Ver resumen», cambiá el costo a **13000** y tocá «Confirmar registro». Tiene que volver a mostrar el resumen (con $13000,00) y el aviso
**«Cambiaste un dato después de ver el resumen: revisalo de nuevo antes de confirmar»**, y no registrar nada. Volvé el costo a **12000**, tocá «Ver resumen» otra vez.
*(Lo cubre `test_regla_si_cambio_un_dato_despues_del_resumen_no_se_confirma_lo_que_no_vio`.)*

**10. Confirmá.** Tocá **«Confirmar registro»**. Tiene que aparecer el aviso verde «El lote L-N quedó registrado» y, arriba del formulario, la tarjeta **«El lote L-N quedó registrado en Maduración: …, 180 plantas»** con los botones
**«Planificar su transición»**, «Registrar otro lote» (y «Planificar su cosecha» si tu instalación tiene esa entrada). Anotá el código del lote.
*(Lo cubre `test_paso_10_confirmar_registra_redirige_y_muestra_la_confirmacion_con_sus_enlaces` y el recorrido.)*

**11. El lote, en la lista.** «Invernaderos» → «Invernadero Carga Inicial» → «Lotes activos»: el lote en **Maduración**, **180 de 180** plantas, costo por planta **$66.67**, «Entró a la etapa» = la fecha de hace 10 días y «Fin estimado» = esa fecha + los días de Maduración.
Ya no aparece el aviso de «Sin lotes activos».

**12. Los agujeros bajaron.** En la pestaña de sectores: **M-1** sin agujeros libres (100 ocupados), **M-2** con 20 libres (80 ocupados); el resto, sin cambios. *(Lo cubre `test_post_c_una_ocupacion_por_sector_y_los_agujeros_libres_bajan`.)*

**13. La orden de la carga.** «Producción» → «Órdenes de trabajo»: una fila nueva, tipo **Siembra**, estado **concretada**, «… · 180 plantas · carga inicial». Abrila: «Tipo de siembra: **Carga inicial (lote existente)**», **«Capataz: Sin Capataz (carga inicial)»**,
«Plantines planificados» 180, «Fecha de siembra» = hace 40 días, **«Fecha programada», «Creada» y «Resuelta» = hoy**, y «Distribución por sector» M-1 100/100 y M-2 80/80. No tiene botones de cancelar ni de concretar.
Como **Capataz**: «Mis órdenes» **no** la muestra, y su dirección escrita a mano da «página no encontrada».
*(Lo cubre `test_regla_la_lista_el_detalle_y_la_bandeja_no_se_rompen_con_una_siembra_sin_capataz` y `test_regla_fechas_de_la_orden_son_hoy_y_la_fecha_de_siembra_es_la_indicada`.)*

**14. La bitácora.** Como **Agrónomo**: «Producción» → «Bitácora» → «Invernadero Carga Inicial». Con el filtro **Tipo = «Carga inicial»** aparece un registro: fecha = hace 10 días, tu nombre, el lote, los sectores **M-1 y M-2** y la descripción
**«Carga inicial del lote L-N: 180 plantas de … en Maduración, desde el dd/mm/aaaa.»**. *(Lo cubre `test_regla_5_prd_05_la_carga_inicial_se_lista_con_su_texto_su_lote_y_sus_sectores_y_se_filtra_por_tipo`.)*

**15. El libro de gestión.** Entrá como **Contador** → «Contabilidad» → «Libro de gestión» (si no había ejercicio contable, el primer asiento lo abrió solo: mirá «Ejercicios»). Tiene que haber un asiento con la **fecha de hoy** y la descripción
**«Carga inicial del lote L-N: …»**. Abrilo: **Debe 1.1.05 Productos en Proceso $12.000,00 / Haber 3.1.01 Capital Inicial $12.000,00**, origen la orden de trabajo de la carga. Con «Por cuenta» y la cuenta Capital Inicial, el saldo acreedor es $12.000,00.
*(Lo cubre `test_post_d_asiento_productos_en_proceso_contra_capital_inicial_con_la_fecha_actual` y el recorrido.)*

**16. Auditoría.** Como **Gerente**: «Auditoría» → el registro **«Registro de lote existente»** de tu Agrónomo. Sus afectados incluyen la siembra, el lote, las dos ocupaciones, los dos sectores, la entrada de bitácora y el asiento; en «datos»: tipo de siembra «Carga inicial»,
fecha de ingreso a la etapa, costo estimado, y en «cambios» los agujeros ocupados de M-1 y M-2 antes y después. *(Lo cubre `test_post_e_un_registro_de_auditoria_con_todo_lo_creado_entre_los_afectados`.)*

**17. Las fechas de la orden, en la base (opcional, solo lectura).** En PowerShell, en la carpeta del proyecto (no escribe nada):
```powershell
@'
from produccion.models import Siembra
for s in Siembra.objects.filter(tipo_siembra="carga_inicial").order_by("-id")[:1]:
    print(s.codigo, s.tipo_siembra, s.estado_orden, "capataz:", s.capataz_id)
    print("creada", s.fecha_creacion_orden, "| programada", s.fecha_programada_orden, "| resuelta", s.fecha_resolucion_orden, "| siembra", s.fecha_siembra)
'@ | python manage.py shell
```
Las tres primeras fechas son **hoy**, la de siembra es **hace 40 días** y el Capataz es `None`.

### Segundo lote: Crecimiento con costo $0, y su transición

**18. Costo $0 no genera asiento.** Como **Agrónomo**: «Registrar otro lote» → mismo invernadero y variedad, etapa **Crecimiento**, siembra hace 30 días, ingreso hace **4 días** (`(Get-Date).AddDays(-4)`), **50** plantas, costo **0**, C-1 **50**. «Ver resumen»:
**«con costo $0 no se registra ningún asiento»** y costo por planta $0,00. Confirmá. Como Contador, el libro **sigue con un solo asiento** (el del paso 15).
*(Lo cubre `test_post_d_con_costo_cero_no_hay_asiento_y_no_falla` y `test_paso_8_el_resumen_con_costo_cero_no_muestra_asiento`.)*

**19. La ayuda de la primera etapa.** «Registrar lote existente» → elegí invernadero, variedad y **Germinación**: debajo de «Fecha de ingreso a la etapa actual» dice **«Suele coincidir con la fecha de siembra»**. Con Crecimiento o Maduración, esa frase no está.
No cargues este lote (cancelá). *(Lo cubre `test_regla_la_ayuda_de_la_primera_etapa_solo_aparece_en_la_primera`.)*

**20. Planificá la transición del lote de Crecimiento.** «Producción» → «Nueva transición» → elegí el lote de Crecimiento. Tiene que mostrar que Crecimiento **«termina el»** la fecha de ingreso (hace 4 días) más los días de Crecimiento de tu ciclo.
Fecha programada = hoy + 2, repartí las 50 plantas en un sector de la etapa siguiente (hay uno de cada tipo, con 100 libres), «Ver resumen» y «Confirmar». Quedó una orden de transición «a realizar» para el Capataz.
*(Lo cubre el recorrido: `ofrecido.lote.fecha_estimada_de_fin`.)*

**21. La fecha mínima sale del ingreso cargado.** Como **Capataz** (`capataz.carga@infoponia.com`): «Mis órdenes» → la transición → «Concretar». Debajo de «Fecha del traslado»: **«Entre el [fecha de ingreso, hace 4 días] (entrada a Crecimiento) y hoy»**.
Probá la fecha de hace 6 días: tiene que rechazarla (es anterior al ingreso). Con la de hoy, concretá: el lote pasa a la etapa siguiente. *(Lo cubre el recorrido: `fecha_minima_de_transicion`.)*

### Errores de validación

**22. Cada error, junto a su campo** (en «Registrar lote existente», con Maduración, «Ver resumen»; nunca se registra nada):
- plantas **0** → bajo «Cantidad de plantas»: «La cantidad de plantas tiene que ser un número entero mayor que cero.»
- costo **-5**, **10,555** o **abc** → bajo «Costo estimado»: «El costo estimado tiene que ser un monto de cero o más, con hasta dos decimales.»
- fecha de siembra **mañana** → bajo «Fecha de siembra»: «no puede ser posterior a hoy».
- ingreso **anterior a la siembra** o **mañana** → bajo «Fecha de ingreso a la etapa».
- suma de sectores distinta de las plantas → bajo la distribución: **«faltan ubicar N»** o **«te pasaste por N»**.
- 150 plantas en M-1 sola (después de cargar el lote del paso 10, M-1 no tiene libres) → **«… tiene 0 agujeros libres…»**.
*(Lo cubren `test_ext_5_los_errores_van_debajo_de_su_campo` y `test_ext_7_los_errores_de_la_distribucion_se_muestran_con_los_libres`.)*

**23. Sin sectores para la etapa (extensión 7d).** Lo cubre `test_ext_7d_sin_sectores_compatibles_con_la_etapa_informa_que_no_hay_donde_ubicar_el_lote`; no hace falta armarlo a mano (habría que poner M-1 y M-2 fuera de servicio).

### Roles

**24. Gerente.** En «Producción» **no** hay botón «Registrar lote existente»; la dirección escrita a mano (`http://localhost:8000/produccion/lotes/registrar-existente/`) da «página no encontrada». Sí ve la orden de la carga y la bitácora, en solo lectura.
*(Lo cubre `test_pre_el_gerente_obtiene_404_en_get_y_en_post`.)*

**25. Capataz y otro Agrónomo.** El Capataz con esa dirección escrita a mano obtiene «acceso denegado». Un Agrónomo que tenga **otro** invernadero ve la acción, pero «Invernadero Carga Inicial» **no** figura en su desplegable.
*(Lo cubre `test_pre_el_capataz_obtiene_403` y `test_paso_2_invernaderos_disponibles_son_los_activos_a_cargo_sin_siembras_normales`.)*

### Navegador real (obligatorio: es un formulario que se envía)

**26. Navegador real.** Abrí «Registrar lote existente» en una **ventana privada**, entrá como Agrónomo, completá una carga (por ejemplo **10 plantas en Floración, costo 100**), tocá **«Ver resumen»** y después **«Confirmar registro»**, **hasta el final**;
después volvé a abrir la pantalla. Tiene que mostrar el aviso y la tarjeta de confirmación. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: el cliente de Django no ve el CSRF,
el encabezado `Origin` ni el JavaScript. Repetilo con **JavaScript desactivado**: «Continuar» (en lugar del cambio automático de los desplegables), «Ver resumen» y «Confirmar registro» tienen que funcionar igual (cada botón es un envío común).

### Lo último: la acción desaparece (irreversible para este invernadero)

**27. Concretada una siembra normal, la acción desaparece y no vuelve.** Hacelo **al final**. Como Agrónomo: «Nueva siembra» en este invernadero (necesita la semilla de la variedad habilitada con stock y un sector de Germinación con lugar; si no la tenés,
habilitala en «Inventario»), y como Capataz concretala. Después: en «Producción» **ya no está** el botón «Registrar lote existente»; en la pestaña «Lotes activos» tampoco; «Registrar lote existente» escrito a mano dice
**«No hay invernaderos donde cargar un lote existente… ya tiene una siembra concretada»**. Los lotes cargados siguen ahí y se comportan como cualquier lote.
*(Lo cubre `test_regla_despues_de_concretar_una_siembra_normal_la_pantalla_deja_de_ofrecer_el_invernadero` y el recorrido.)*

### Opcional

**28. En un celular.** La pantalla, con el resumen y el asiento, se lee bien en un ancho de 360 px (los campos en una columna, los botones se parten en renglones sin salirse).

## Cierre

**Qué se hizo.**
- **Modelo y migraciones** (`produccion/models.py`): `Siembra.TipoSiembra` (`normal`, `carga_inicial`) y `tipo_siembra` (por defecto `normal`); `Siembra.capataz` redeclarado nulo (L1, R078 0..1); CHECK `siembra_tipo_valido` y
  `siembra_capataz_segun_tipo` (nulo si y solo si `carga_inicial`); `Bitacora.TipoEvento.CARGA_INICIAL` y el valor en `bitacora_tipo_evento_valido`. Migración `produccion` **0010_carga_inicial_de_lotes** (en `main` ya estaban la 0009 de COM-05a2 y,
  de `core`, la 0042; al traer `main` el 25/11 aparecieron la 0043 y la 0044 de COM-05b y CMP-05, así que renumeré la mía: `core` **0045_carga_inicial_de_lotes**, solo de `choices`, encadenada a la 0044). `core/models.py`: acción `registro_lote_existente` (en `ACCIONES_DE_NEGOCIO`), `ETIQUETAS` (`tipo_siembra`,
  `fecha_ingreso_etapa`, `costo_estimado`) y `VALORES_VISIBLES["tipo_siembra"]`.
- **Lectura de la fecha de entrada** (`produccion/servicios/lotes.py`): `entradas_a_la_etapa` y `fecha_de_entrada_a_maduracion` toman la `fecha_bitacora` de la entrada `carga_inicial` del lote en la etapa actual cuando no hay una transición
  concretada hacia ella; `fecha_maxima_de_cosecha` hereda. Los otros lectores (`lotes_activos_de`, transiciones, `comercial` cosechas y stock maduro) la heredan sin cambios.
- **Servicio** `produccion/servicios/lotes_existentes.py`: `invernaderos_disponibles`, `datos_de_registro`, `resumen_de_registro` (con el asiento previsto) y `registrar_lote_existente` (siembra, lote, ocupaciones, bitácora, asiento y un registro de
  auditoría `registro_lote_existente`, todo en una transacción). Bloqueos: cuenta del Agrónomo → invernadero → variedad → sectores (id) → ejercicio (al final, lo toma `registrar_asiento_automatico`), con la relectura completa bajo bloqueo (10a).
  El asiento: Debe Productos en Proceso / Haber Capital Inicial por el costo, origen la `Siembra`, con la fecha **actual** (D-92 punto 4); costo 0, sin asiento (H11). `siembras._registrar_concrecion` no se tocó (CON-04a).
- **Sectores elegibles compartidos**: la lógica de `transiciones._sectores_del_destino` se movió a `produccion/servicios/sectores_elegibles.py` **sin cambiar su comportamiento** (`transiciones` la llama con los datos del lote y conserva el nombre
  `SectorNoElegible`). Las pruebas de transición pasaron sin tocarlas. La compatibilidad de perfil familiar se aplica igual que en el resto (el caso de uso lo dejó anotado para el hilo de análisis).
- **Pantalla**: «Registrar lote existente» (`/produccion/lotes/registrar-existente/`), la acción en «Producción» y en la pestaña «Lotes activos» (solo con un invernadero disponible), «Carga inicial» en el filtro de la bitácora, «Sin Capataz (carga inicial)» en el detalle
  de la orden y «· carga inicial» en su fila de la lista.
- **Capataz nulo** (aclaración 3): se revisó todo lo que lee `siembra.capataz` o `capataz_id` en `produccion` (`ordenes._fila`, `_ordenes_del_capataz`, `_hija_con_capataz`, `cancelar_orden`, `detalle_de_orden`/`es_su_capataz`, `registrantes._ordenes_a_traspasar`,
  `alcance.py`, `detalle.html`) y en `comercial` (no leen el Capataz de la siembra); `estadisticas` no existe. La única plantilla que fallaba en silencio era `detalle.html` (mostraba una celda vacía): ahora dice «Sin Capataz (carga inicial)».
  Probado: lista del Gerente y del Agrónomo, ficha, bandeja del Capataz, «Cancelar orden» y la consulta de la bitácora.
- Sin dependencias nuevas; sin modelos nuevos.

**Diferencias con la documentación.**
1. **Fechas de la orden (difiere de D-92 punto 12).** La decisión pedía `fecha_creacion_orden = hoy` y `fecha_programada_orden = fecha de siembra` (pasada), pero el CHECK ya mergeado `orden_trabajo_programada_desde_creacion` (programada ≥ creación) vive en la tabla
   padre y no puede exceptuar una siembra de carga inicial. Se guardó `fecha_creacion_orden = fecha_programada_orden = fecha_resolucion_orden = hoy` y la fecha indicada va en `Siembra.fecha_siembra` (que es la que lee todo el sistema). El estudiante lo decidió el 25/11/2026; no se tocó el CHECK ni
   ninguna migración mergeada. **Propuesta en M3:** una decisión nueva que corrija el punto 12 y la corrección de «Cómo se aplica» de `lote_existente.md` (no va a `temas_abiertos.md`).
2. **Código nuevo `etapa_invalida`** (la etapa elegida no es del ciclo de la variedad, campo `etapa`): un dato mal formado que el caso de uso no nombra. No está en `docs/api/produccion.md`.
3. **`supera_agujeros` trae `datos={"libres": {sector_id: libres}}`**, con los libres de cada sector que no alcanza (el caso de uso dice «informa los agujeros disponibles de ese sector»).
4. **`distribucion`** acepta un diccionario `{sector_id: plantas}` (como dice el caso de uso) o una secuencia de pares (para poder rechazar un sector repetido).
5. **Interpretación (para el hilo de análisis).** En la **primera etapa** del ciclo, el caso de uso dice que la entrada `carga_inicial` se lee «cuando no hay una transición concretada hacia la etapa actual», y en la primera nunca la hay: se leyó literal y manda la **fecha de
   ingreso cargada**, no la de siembra. La validación 5a se mantiene (siembra ≤ ingreso ≤ hoy) y el formulario dice, en la primera etapa, «Suele coincidir con la fecha de siembra».
6. **El bloqueo del invernadero es redundante en este servicio**: `maestros.bloquear_sectores` vuelve a bloquear el invernadero por dentro, así que quitar mi línea explícita de `bloquear_invernadero_activo` no rompe ninguna prueba (ver el experimento). Se mantiene explícito
   por el orden de `docs/patrones/bloqueos.md`. Del mismo modo, en «dos cargas sobre el mismo sector» (mismo Agrónomo, mismo invernadero) el invernadero ya serializa y el bloqueo de los sectores es redundante; se mantiene por el orden global (sectores antes que insumos, D-50 punto 10),
   no porque esa prueba lo exija.

**Pantallas: lo que se corrigió del prototipo (D-61).** La pantalla **no está en el prototipo**: se armó con el patrón de «Nueva siembra» (PROD-PNF-SMB).
1. **Formulario**: invernadero → variedad → etapa actual → fechas, plantas y costo → distribución por sector → resumen. Los tres desplegables redibujan por HTMX **sin validar** y sin mover el scroll (`hx-swap="innerHTML show:none"`, `data-sin-envio-en-curso`); sin JavaScript
   queda «Continuar» (`<noscript>`). Validar es solo con «Ver resumen» y «Confirmar registro» (con la «firma» del resumen: un dato cambiado después del resumen no se confirma). Sin JavaScript propio.
2. **Resumen** (paso 8): variedad, etapa, fechas, plantas, costo estimado y por planta, la ocupación por sector con los libres que quedan y **el asiento** (Debe Productos en Proceso / Haber Capital Inicial, o «con costo $0 no se registra ningún asiento»).
3. **Confirmación** (paso 11): tras registrar, vuelve a la misma dirección con `?registrado=<lote>` (POST-redirección-GET: recargar no repite el registro) y muestra el identificador con los accesos a «Planificar su transición» y, si hay, «Planificar su cosecha». Solo muestra un lote de un
   invernadero a cargo de quien mira.
4. **Estados que faltaban**: sin invernaderos disponibles (extensión 2a: explica que la acción desaparece al concretarse una siembra normal), sin sectores compatibles (7d, con el motivo de cada sector no elegible), sin variedades, el aviso de «cambiaste un dato» y, si el invernadero dejó de
   estar disponible entre el resumen y la confirmación (10a), el mensaje de qué cambió en lugar de uno genérico.
5. **Ayuda** «Suele coincidir con la fecha de siembra» debajo del ingreso cuando la etapa es la primera (decisión del estudiante); costo por defecto 0.
6. **Acción «Registrar lote existente»**: en «Producción» y en la pestaña «Lotes activos» de la ficha (con el invernadero ya elegido), solo si `invernaderos_disponibles` no está vacío (D-30: ningún botón lleva a un 403 ni a una pantalla vacía).
7. **Bitácora**: «Carga inicial» entra al filtro de tipos.

**Pruebas (M1).**
- `python manage.py test produccion contabilidad core --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion` → **2200 pruebas, OK** (base de pruebas recreada con `--noinput`, por la migración nueva).
- `python manage.py test produccion --keepdb --tag concurrencia` → **49 pruebas, OK** (4 nuevas).
- Suite completa como el CI (`python manage.py test --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion`, porque se tocó `core`) → ****9309 pruebas, OK****.
- `makemigrations --check` → sin cambios; `sqlmigrate produccion 0010` (revisado: agrega la columna `tipo_siembra` con default `normal`, vuelve nula `capataz_id`, recrea el CHECK de la bitácora y crea los dos CHECK de la siembra; no borra ni reescribe filas, y las existentes —«normal» y con Capataz— los cumplen);
  `core` 0045 solo cambia `choices` (sin SQL). Las dos se aplicaron en las bases `test_…` al crearlas.
- Archivos nuevos: `test_prod_reg_lte.py` (53, una por postcondición y por extensión), `test_prod_reg_lte_concurrencia.py` (4), `test_prod_reg_lte_vistas.py` (29), `test_recorrido_lote_existente.py` (1); ampliados `test_modelos_produccion.py` (5), `test_lotes_lectura.py` (7), `test_prod_cns_bit.py` (1).
  Las pruebas del servicio se escribieron primero y se mostró que fallaban (53 de 53) antes de implementar; el estudiante las revisó y aprobó.
- **Pruebas existentes que cambiaron (sin debilitarlas):** en `test_prod_cns_bit.py`, la lista exacta de tipos del filtro suma `carga_inicial`. En `test_prod_reg_lte.py`, ya aprobadas, dos ajustes de armado: los parches de `bloquear_invernadero_activo` y `bloquear_variedad` apuntan al módulo real (el proxy `perezoso`
  no propaga el parche) y la aserción de «agujeros cambiaron» espera 0 lotes (el lote «ajeno» que simula el parche se crea dentro de la transacción del servicio y se revierte con ella).
- **Experimentos de bloqueos** (aclaración 7; el archivo se restauró desde una copia y `cmp` dio idéntico, sin marcas de experimento):
  1. Quitar mi línea de `bloquear_invernadero_activo`: **la prueba contra concretar sigue pasando**, porque `bloquear_sectores` de `maestros` vuelve a bloquear el invernadero (redundancia).
  2. Quitar además ese camino (bloqueo directo de los sectores): **falla** `test_regla_concretar_una_siembra_normal_primero_la_carga_espera_y_se_rechaza_porque_ve_la_siembra` con `(2, 0, []) != (1, 1, [])`: se registraría una carga sobre un invernadero con siembra normal concretada.
  3. Quitar la relectura bajo bloqueo (10a): **fallan** la prueba de dos cargas sobre el mismo sector (`(2, 0, []) != (1, 1, [])`: 120 plantas en un sector de 100), la de concretar y las dos pruebas unitarias de 10a.
- La prueba «la carga primero, concretar después» **no falla** al quitar un bloqueo (terminan bien las dos con o sin él); solo prueba que el orden no se traba. Lo dice su docstring.

**Decisiones.** Se propone una nueva (M3): corrige el punto 12 de D-92 (las fechas de la orden de carga inicial). El número se toma de `git fetch` mirando `main`.

**Datos de la base de desarrollo.** No se tocó tu base de desarrollo: no se corrió `migrate`, ni `runserver`, ni ningún fragmento contra ella. Las pruebas usaron bases `test_…` (se recrearon con `--noinput`). `docs/estado.md` y el resto de la documentación de M3 están **propuestos, sin aplicar**.

### Informe

**Verifiqué:**
- El recorrido `RecorridoDeLoteExistenteTests` (por rol y por estado): Gerente (404, sin botón) y Capataz (403) → Agrónomo ve la acción → elige invernadero, variedad y etapa → errores por campo sin escribir → resumen con el asiento → confirmación → lote de 180 plantas en dos
  sectores con costo $12.000 (agujeros 0 y 20 libres, siembra de carga inicial sin Capataz, orden en la lista y el detalle del Agrónomo y del Gerente, ausente de la bandeja del Capataz, bitácora «Carga inicial» para el Agrónomo y el Gerente, asiento Debe 1.1.05 / Haber 3.1.01 por $12.000 con la fecha de hoy
  visible en el libro del Contador y del Gerente, un registro de auditoría) → segundo lote en Crecimiento con costo $0 (sin asiento) → fecha mínima y fin estimado salen del ingreso cargado y la transición se planifica y se concreta → concretada una siembra normal, la acción desaparece, la pantalla lo explica y una
  carga a mano se rechaza → invariantes contables.
- Migraciones: `makemigrations --check`, `sqlmigrate` de `produccion` 0010 (leído) y las dos aplicadas en la base de pruebas.
- Concurrencia: contra concretar una siembra normal (en los dos órdenes), dos cargas sobre el mismo sector y dos que no compiten; y los experimentos de arriba.

**Lo cubre una prueba:** cada paso de la «Verificación a mano» dice cuál (`test_prod_reg_lte.py`, `test_prod_reg_lte_vistas.py`, `test_prod_reg_lte_concurrencia.py`, `test_lotes_lectura.py`, `test_modelos_produccion.py` y `test_recorrido_lote_existente.py`).

**No pude verificar:**
- Todo lo que se ve en tu navegador y en tu base de desarrollo (pasos 1 a 28): no abro navegador ni toco esa base.
- **El paso de «navegador real» (paso 26):** el token CSRF, el encabezado `Origin` y el JavaScript de los tres desplegables y de «Continuar»/«Ver resumen»/«Confirmar registro».
- El aspecto de la pantalla (el resumen con el asiento, la tarjeta de confirmación y los estados vacíos) y su lectura en un celular.
- La **creación a mano del invernadero, los sectores y las cuentas** (pasos 3 y 4) con las pantallas de `maestros` y de cuentas, que esta tarea no toca: están descritos con los nombres de campo del código, pero no los recorrí.
- La carga con **datos reales de Georef** y con un ciclo de tu variedad (las pruebas usan los de las fábricas: cinco etapas de 10 días).
- El registro en la pantalla «Auditoría» (las pruebas verifican el registro, no cómo se dibuja).
