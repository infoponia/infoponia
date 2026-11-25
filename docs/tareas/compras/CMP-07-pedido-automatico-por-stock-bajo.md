# CMP-07 · Pedido automático por stock bajo

Estado: hecha (revisión a mano pendiente) | App: compras | Rama: feature/cmp-07-pedido-automatico-por-stock-bajo | Ronda: —

Depende de: **CMP-03** (paso diario 60 a 62, mergeada) y **CMP-02a** (pedido e invitaciones, mergeada). Si alguna no está en `main`, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Hoy el Agrónomo arma el pedido de cotización a mano. Este paso diario lo arma solo, uno por invernadero, con los insumos bajo el mínimo, y manda las invitaciones a los proveedores. El Agrónomo y el Gerente siguen decidiendo desde la cotización en adelante.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-AUT-PED | Generar Pedidos Automáticos por Stock Bajo | docs/casos_de_uso/compras/pedido_automatico.md | — |

## Leer

- Casos de uso: `pedido_automatico.md` completo y, de `pedidos.md`, CMP-RLZ-PED con sus «Actualizaciones de A0» y «Cómo se aplica».
- Modelo: docs/modelo/compras.md (`Pedido`, `DetallePedido`, `InvitacionPedido`, `EnlaceProveedor`) y docs/modelo/maestros.md (`ConfiguracionOperativa`).
- Decisiones: D-NN (esta tarea), D-56, D-22, D-27, D-42, D-87, D-88, D-100 (pasos 60 a 62).
- API: docs/api/stock.md (`existencias`, `bajo_minimo`), docs/api/notificaciones.md.
- Patrones: docs/patrones/bloqueos.md (orden de compras), docs/patrones/enlace_del_proveedor.md, docs/patrones/auditoria.md.
- Código a leer: `compras/servicios/pedidos.py` (`insumos_bajo_el_minimo`, `ya_pedido`, `proveedores_invitables`, `categorias_del_pedido`, `_validar`, `registrar_pedido`, `cancelar_pedido_automaticamente`), `compras/procesos.py` y `compras/apps.py` (cómo se registran los pasos 60 a 62), `core/procesos.py`, `maestros/servicios/configuracion.py` y la pantalla de configuración operativa.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.

## Límites

- Crea modelos: ninguno.
- Migraciones: **una de `maestros`** que agrega `ConfiguracionOperativa.porc_margen_pedido_automatico` (entero, 0 a 100, por defecto 20, con su validación y su CHECK). **Permiso expreso del estudiante (25/11/2026)** para tocar este modelo ya mergeado. No se toca ninguna otra migración.
- Permitido fuera de la app: `maestros/models.py`, su migración, el formulario y la plantilla de la configuración operativa, el servicio que la audita, y sus pruebas; `core/procesos.py` (**solo el comentario** de la tabla de órdenes: fila 63); al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: marcar el pedido como «automático» en un campo propio (queda en la auditoría); calcular cantidades por consumo histórico; cambiar CMP-02a, CMP-02b o CMP-03.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Margen configurable.** Columna, migración, formulario, pantalla y auditoría del cambio, como los demás parámetros de la configuración. — pruebas: `maestros/tests/` (amplía las de configuración).
2. **Servicio.** `compras/servicios/pedidos_automaticos.py`: `calcular_cantidad`, la selección de insumos por invernadero y `generar_pedidos_automaticos(hoy) -> ResumenDePaso`. Reutilizá las validaciones y el alta de `pedidos.py`; si hace falta partir `registrar_pedido` en una función interna que acepte el actor de auditoría, hacelo sin cambiar el comportamiento del pedido manual (sus pruebas tienen que seguir iguales). Una transacción por invernadero, con el orden de bloqueo de `bloqueos.md`. — pruebas: `compras/tests/test_cmp_aut_ped.py`.
3. **Paso diario.** Registrarlo en `compras/apps.py` como `generar_pedidos_automaticos`, orden 63, nombre «Pedidos automáticos por stock bajo»; las URLs de los enlaces salen de `URL_DEL_SITIO`. Notificaciones y avisos de las extensiones 3a y 5a. — pruebas: las mismas, más `proceso_diario --solo generar_pedidos_automaticos --fecha`.
4. **Concurrencia e idempotencia.** Dos corridas seguidas no duplican; un pedido manual que tome el mismo insumo entre la lectura y el bloqueo no genera uno repetido (5b). — pruebas: `test_pedidos_automaticos_concurrencia.py` (etiqueta `concurrencia`).

Si el tiempo apremia, lo último que se recorta es el paso 4 (se anota como disparador).

## Hecho cuando

- El paso 63 aparece en `proceso_diario --listar` y crea un pedido por invernadero con insumos bajo el mínimo, con la cantidad y el margen de la decisión.
- Cada extensión de CMP-AUT-PED (1a, 1b, 3a, 5a, 5b, 8a) tiene su prueba.
- El pedido manual sigue pasando todas sus pruebas sin cambios.
- El Gerente puede cambiar el margen y queda auditado.
- Comando de pruebas: python manage.py test compras.tests maestros.tests --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion (y las de concurrencia y migración de esta tarea, con sus etiquetas).

## Verificación a mano (la completa Claude Code al cerrar)

**Antes de empezar**

- Con el entorno virtual activo: `python manage.py migrate` (aplica `maestros` 0013) y `python manage.py runserver`; abrí `http://localhost:8000`.
- Necesitás un **Gerente**, un **Agrónomo** y un **Capataz** activos (si no los tenés, creálos desde «Usuarios» con el Gerente; la contraseña la elegís vos, no va en ningún archivo).
- Creá a mano, en este orden y con el Gerente salvo que se diga otra cosa:
  1. «Inventario › Categorías»: una categoría común **«Fertilizantes»** (si ya existe una parecida, usala).
  2. «Inventario › Insumos»: **«Nutriente A»**, unidad **kg**, categoría «Fertilizantes»; y **«Lechuga plantín»**, unidad **unidad**, categoría «Fertilizantes».
  3. Un invernadero activo **«Invernadero Norte»** a cargo del Agrónomo (si ya tenés uno, usalo).
  4. Habilitá en ese invernadero los dos insumos: Nutriente A con **mínimo 5** y precio **100,00**; Lechuga plantín con **mínimo 20** y precio **12,50**. Sin cargar lotes: ambos quedan con stock 0, es decir, bajo el mínimo.
  5. «Compras › Proveedores»: dos proveedores activos con correo (por ejemplo «Semillas del Sur S. A.», `ventas@sur.test`, y «Viveros del Este S. R. L.», `info@este.test`, cada uno con un CUIT válido distinto), ambos **especializados en «Fertilizantes»**.

**Pasos**

1. **El margen en la configuración** (Gerente). «Configuración › Parámetros operativos», tarjeta **«Compras»**. Tiene que verse el campo **«Margen del pedido automático (%)»** con el valor **20** y la ayuda «El pedido automático por stock bajo pide el mínimo más este porcentaje…». *(Lo cubre `test_configuracion_vistas`.)*
2. **Error de validación.** Escribí **101** (o −1) y guardá: el error aparece junto al campo, no se guarda nada y los demás valores no cambian. *(Lo cubren `test_adm_mod_cfg` y `test_configuracion_vistas`.)*
3. **Guardar el margen.** Escribí **50** y guardá: aviso «Se guardó la configuración.». En «Auditoría» aparece «Modificación de configuración» con **«Margen del pedido automático (%)»: antes 20, después 50** (el nombre legible, no la clave `porc_margen_pedido_automatico`). Volvé a poner **20** y guardá. *(Lo cubre el recorrido.)*
4. **Roles.** Entrá como Agrónomo y como Capataz y escribí a mano `/configuracion/`: «Prohibido (403)»; el menú no la muestra. *(Lo cubren `test_pre_a_solo_el_gerente_entra_a_las_tres_vistas` y el recorrido.)*
5. **Navegador real.** Abrí «Configuración» en una **ventana privada** (sin sesión), iniciá sesión como Gerente, cambiá el margen (por ejemplo a 30) y **enviá el formulario hasta el final**; después recargá la pantalla: tiene que mostrar 30 y el aviso de guardado. Si aparece «Prohibido (403)», «Verificación CSRF fallida» o un error en la consola del navegador (F12), avisá: el cliente de Django no ve el CSRF, el encabezado `Origin` ni el JavaScript. Dejalo en **20**. (Opcional: con JavaScript desactivado el guardado también tiene que funcionar.)
6. **Ver el paso.** En la terminal: `python manage.py proceso_diario --listar`. Tiene que aparecer `63 · generar_pedidos_automaticos · Pedidos automáticos por stock bajo`, después de las líneas del 60, 61 y 62. *(Lo cubre `PasoDiarioTests`.)*
7. **Correr el paso con una fecha** (simula un día; sin `--fecha` usa hoy), con una fecha real `AAAA-MM-DD`:
   `python manage.py proceso_diario --solo generar_pedidos_automaticos --fecha 2026-11-26`
   Tiene que imprimir `Pedidos automáticos por stock bajo: procesados N · creados 1 · resueltos 0` (N = invernaderos activos) y `Pasos correctos: 1 · fallidos: 0.`. Si tu `.env` tiene el correo en consola, los dos correos aparecen impresos en la terminal; si no, los enlaces quedan «pendiente de envío» y no pasa nada más (es lo esperado). *(Lo cubre el recorrido.)*
8. **El pedido** (Agrónomo). «Compras › Pedidos»: hay un pedido nuevo «En cotización» de «Invernadero Norte» con dos detalles: **Lechuga plantín 24** (20 × 1,2) y **Nutriente A 6** (5 × 1,2); fecha límite = la fecha que corriste + 3 días; los dos proveedores invitados. En la campana hay un aviso «Pedido P-… creado automáticamente» con «2 insumos bajo el mínimo en Invernadero Norte». *(Lo cubren `GeneracionDelPedidoTests` y el recorrido.)*
9. **Auditoría.** Como Gerente, en «Auditoría»: «Alta de pedido de cotización» sin usuario, con rol «InfoPonia», y en el detalle el origen «automático» y el margen aplicado. *(Lo cubre el recorrido.)*
10. **Idempotencia.** Corré el mismo comando otra vez con la **misma fecha**: `creados 0`, sin pedido, aviso ni correo nuevos. *(Lo cubren `test_ext_1a_dos_corridas_el_mismo_dia_no_duplican` y la concurrencia.)*
11. **Cantidad con stock.** Cargá (ajuste de stock) **5 de Lechuga plantín**, cancelá el pedido anterior (Agrónomo, «Compras › Pedidos», «Cancelar») y corré el paso de nuevo: el pedido nuevo pide **19** de lechuga (20 × 1,2 − 5). Con margen 0 pediría 15, la cantidad sugerida de la pantalla manual. *(Lo cubre `GeneracionDelPedidoTests`.)*
12. **Sin proveedores (3a).** Dá de baja a los dos proveedores (o sacales la especialidad), cancelá el pedido y corré el paso con otra fecha: no se crea pedido; el Agrónomo y el Gerente reciben «Sin proveedores para el pedido automático de Invernadero Norte (dd/mm/aaaa)». Corriéndolo de nuevo el mismo día no se repite. *(Lo cubre `test_ext_3a_*`.)*
13. **Sin Agrónomo (5a).** Dejá un invernadero activo con un insumo bajo el mínimo sin Agrónomo a cargo y corré el paso: no se crea pedido y solo el Gerente recibe «Pedido automático sin Agrónomo en …». *(Lo cubre `test_ext_5a_*`.)*
14. **El pedido es común.** Con un pedido automático «En cotización», abrí el enlace de uno de los proveedores (desde el correo en consola, o con «Reenviar invitación» del Gerente) en una **ventana privada**: se ve el pedido sin precios y se puede cotizar como en un pedido manual. *(El recorrido cubre hasta abrir el portal; enviar la cotización en un navegador real es de CMP-02a.)*
15. **Opcional, celular.** La pantalla de configuración en un celular: el campo nuevo se ve completo y se abre el teclado numérico.

**Después:** tachá los pasos hechos en `docs/revisiones_pendientes.md` y en `docs/estado.md` en el mismo commit o PR. **En Render:** confirmá en el log que se aplicó `maestros` 0013 y que `URL_DEL_SITIO` está configurada (sin ella los enlaces del correo quedan «pendiente de envío»).

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo**

- **Paso 1.** `ConfiguracionOperativa.porc_margen_pedido_automatico` (entero 0 a 100, por defecto 20, con su CHECK) en la migración `maestros` 0013 (solo `AddField` y `AddConstraint`), su campo en la tarjeta «Compras», su etiqueta en la auditoría (`core/models.py`, una línea; permiso del estudiante, 25/11/2026) y la validación y auditoría que ya hacía `modificar_configuracion`.
- **Paso 2.** `compras/servicios/pedidos_automaticos.py` (`calcular_cantidad`, selección por invernadero y `generar_pedidos_automaticos(hoy)`). `registrar_pedido` se partió y su alta pasó a `pedidos._crear_pedido`, con el mismo comportamiento (las pruebas del pedido manual no cambiaron). `enlaces.enviar_invitacion` no envía si la URL no es absoluta (queda «pendiente de envío»).
- **Paso 3.** Paso diario 63 «Pedidos automáticos por stock bajo» registrado en `ComprasConfig.ready()`; comentarios de la tabla en `core/procesos.py` y `compras/procesos.py`.
- **Paso 4.** `test_pedidos_automaticos_concurrencia.py`: pedido manual contra el automático (todos los insumos y solo uno) y dos corridas a la vez.
- **Lo que difiere de la documentación (a proponer en M3):** (a) los textos de los avisos 3a y 5a, y que «una vez por día» se resuelve sin columna, con un título que lleva la fecha (aprobado por el estudiante); (b) 5a se evalúa antes que 3a; (c) con `URL_DEL_SITIO` vacía el enlace queda «pendiente de envío»; (d) si tras el bloqueo no queda proveedor activo, o cambió el Agrónomo o el invernadero, no se crea nada ni se avisa y la próxima corrida lo trata; (e) el `datos` de la auditoría lleva `origen` y `porc_margen_pedido_automatico`; (f) `D-104.md` se titula «D-NN» pero ya está en `main`: el número es 104.
- **Pantallas: lo que se corrigió del prototipo.** Sin diferencias: el campo nuevo sigue la grilla de «Compras» y lleva su ayuda; no hay pantalla nueva.
- **Datos locales:** no toqué tu base de desarrollo; todo corrió en bases `test_…`.
- **Pruebas existentes que cambiaron de expectativa** (no se debilitó ninguna): tres contaban 14 campos del formulario de configuración y ahora cuentan 15, y la del CHECK de la base suma el margen.

**Pruebas (M1)**

- `compras.tests` y `maestros.tests` (`--keepdb --parallel`, sin concurrencia ni migración): 2460 pruebas, OK.
- Concurrencia (`--tag concurrencia`): `test_pedidos_automaticos_concurrencia` y la de configuración, 7 OK; además `test_pedidos_concurrencia` y `test_ordenes_concurrencia`, 24 OK.
- Migración (`--tag migracion`, singletons de maestros): 4 OK. `makemigrations --check`: sin cambios.

**Verifiqué**

- Recorrido `compras/tests/test_recorrido_pedido_automatico.py`: margen, auditoría, 403 del Agrónomo, corrida con `--fecha`, pedido, aviso, portal del proveedor sin precios, idempotencia y avisos 3a y 5a. OK.
- `sqlmigrate maestros 0013`: solo `ADD COLUMN … DEFAULT 20` y `ADD CONSTRAINT … CHECK (0 a 100)`; no toca datos. Aplicada en la base de pruebas.

**Lo cubre una prueba**

- Cantidad y redondeo: `CalcularCantidadTests`. Flujo, postcondiciones y reglas: `GeneracionDelPedidoTests`. Precondiciones: `PrecondicionesTests`. Extensiones 1a, 1b, 3a, 5a y 8a: `ExtensionesTests`. 5b y el invernadero que falla: `RelecturaConBloqueoTests`. Paso 63: `PasoDiarioTests`. 5b y corridas simultáneas: `PedidosAutomaticosConcurrenciaTests`. Margen: `test_adm_mod_cfg`, `test_configuracion_vistas`, `test_singletons_modelo`.

**No pude verificar**

- El formulario de configuración en un navegador real (CSRF, `Origin`, JavaScript): paso 5 de la verificación a mano.
- El envío real de correos y el portal con un enlace recibido por correo.
- La aplicación de la migración 0013 en Render y la variable `URL_DEL_SITIO` en producción.
- Las pruebas de concurrencia no se corrieron con los bloqueos quitados (la tarea no lo pedía).
