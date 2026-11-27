# Datos de la demo de la defensa

Este archivo es la **fuente única** de los datos que carga el comando `cargar_demo` (tareas DAT-01 y DAT-02, decisión D-NN). Claude Code
**copia estos valores tal cual**: no inventa, no redondea, no "mejora". Si un valor choca con una regla del código, frena y avisa (L7):
no lo cambia en silencio.

Reglas de lectura:

- **HOY** es la fecha local del día en que se corre `cargar_demo` (`timezone.localdate()`, zona `America/Argentina/Buenos_Aires`).
  `HOY−3` es tres días antes, `HOY+7` siete días después. Todas las fechas se calculan al cargar, nunca se escriben fijas.
- **Secretos fuera del repo** (el repo es público):
  - La contraseña de todas las cuentas sale de la variable de entorno `INFOPONIA_DEMO_CONTRASENA`.
  - La base de los correos sale de `INFOPONIA_DEMO_CORREO` (la parte antes de `@gmail.com`).
  - La contraseña no se escribe en ningún archivo, prueba ni mensaje de salida. La base de los correos tampoco va en un archivo ni en una
    prueba, pero **sí aparece en la salida** de `cargar_demo` y de `estado_demo`: las dos listan cada cuenta con su correo completo (paso 3 de
    DAT-01), que es lo que el estudiante necesita para entrar.
- **Correos**: `<base>+<rol><número>@gmail.com`. Por ejemplo, con la base `ejemplo`, el Gerente es `ejemplo+gerente1@gmail.com`. Gmail
  entrega todos esos alias a la misma casilla, así que el estudiante ve todos los avisos en un solo buzón.
- **Si una sección depende de algo que no existe en el repo** (marcado «Depende de»), se saltea entera y el comando lo informa en su salida.

## 1. Organización (PerfilOrganizacion)

| Campo | Valor |
|---|---|
| nombre_organizacion | Huerta Hidropónica del Paraná |
| cuit_organizacion | 30712345604 |
| telefono_organizacion | 3764 412345 |
| email_organizacion | `<base>+organizacion1@gmail.com` |
| direccion_organizacion | Ruta Nacional 12 km 1335, Candelaria, Misiones |
| colores | Los que ya tenga (no se tocan) |

## 2. Configuración operativa (ConfiguracionOperativa)

Solo se cambian estos valores. El resto queda en sus valores iniciales.

| Campo | Valor demo | Inicial | Por qué |
|---|---|---|---|
| dias_pre_reserva_suministro | 7 | 14 | Con 7 la ventana de la carga cubre solo dos períodos del suministro S-1, y el S-2 (que empieza en HOY+8) queda afuera hasta que se adelante el día. Así la pre-reserva automática (paso 40) se ve en vivo. |
| cant_reintentos_comando | 1 | 3 | Escalamiento del comando fallido en segundos, no en minutos (`docs/api/nodo/escenarios.md`, «Antes de empezar», punto 5) |
| segundos_intervalo_reintento | 10 | 60 | Ídem |
| cant_lecturas_confirmacion | 2 | 3 | Ídem |

## 3. Geografía (ya cargada por la migración 0002 de maestros)

Se usan estas localidades de Misiones (id de Georef):

| Localidad | id_georef | Departamento |
|---|---|---|
| Candelaria | 54021020 | Candelaria (54021) |
| Posadas | 54028030 | Capital (54028) |
| Garupá | 54028010 | Capital (54028) |
| Oberá | 54091080 | Oberá (54091) |

## 4. Cuentas

Todas activas, con la contraseña de `INFOPONIA_DEMO_CONTRASENA`, **sin contraseña temporal** (`fecha_contrasena_temporal` vacía, para
que nadie tenga que cambiarla al entrar) y sin grupo de cuentas vinculadas.

| Clave | Rol | Nombre | Apellido | Correo | Teléfono | A cargo de |
|---|---|---|---|---|---|---|
| gerente1 | Gerente | Laura | Benítez | `<base>+gerente1@gmail.com` | 3764 400001 | — |
| agronomo1 | Agrónomo | Martín | Sosa | `<base>+agronomo1@gmail.com` | 3764 400002 | Norte |
| agronomo2 | Agrónomo | Paula | Giménez | `<base>+agronomo2@gmail.com` | 3764 400003 | Sur |
| capataz1 | Capataz | Diego | Ramírez | `<base>+capataz1@gmail.com` | 3764 400004 | Norte |
| capataz2 | Capataz | Ana | Duarte | `<base>+capataz2@gmail.com` | 3764 400005 | Sur |
| vendedor1 | Vendedor | Sofía | Acosta | `<base>+vendedor1@gmail.com` | 3764 400006 | Norte y Sur |
| transportista1 | Transportista | Jorge | Medina | `<base>+transportista1@gmail.com` | 3764 400007 | Norte |
| transportista2 | Transportista | Carlos | Núñez | `<base>+transportista2@gmail.com` | 3764 400008 | Sur |
| tecnico1 | Técnico | Lucas | Ferreyra | `<base>+tecnico1@gmail.com` | 3764 400009 | Norte |
| contador1 | Contador | Valeria | Ortiz | `<base>+contador1@gmail.com` | 3764 400010 | — |

## 5. Invernaderos y sectores

| Invernadero | Dirección (rural) | Localidad | Agrónomo | Capataz | Vendedor | Técnico |
|---|---|---|---|---|---|---|
| Norte | Ruta Nacional 12, km 1335, lote 4 | Candelaria | agronomo1 | capataz1 | vendedor1 | tecnico1 |
| Sur | Ruta Provincial 105, km 8, lote 11 | Garupá | agronomo2 | capataz2 | vendedor1 | — |

Sectores (todos activos):

| Invernadero | Sector | Tipo de etapa (código) | Agujeros |
|---|---|---|---|
| Norte | Germinación N1 | germinacion | 400 |
| Norte | Crecimiento N1 | crecimiento | 600 |
| Norte | Maduración N1 | maduracion | 600 |
| Norte | Maduración N2 | maduracion | 400 |
| Sur | Germinación S1 | germinacion | 300 |
| Sur | Crecimiento S1 | crecimiento | 400 |
| Sur | Maduración S1 | maduracion | 400 |

Transportistas por invernadero (`TransportistaInvernadero`, `desde` = ahora): transportista1 → Norte; transportista2 → Sur.

## 6. Cultivos, variedades y ciclos

| Cultivo | Variedad | Perfil | Temp. (°C) | Humedad (%) | Luz | Fotoperíodo (h) | Postcosecha (días) | Peso (g) |
|---|---|---|---|---|---|---|---|---|
| Lechuga | Criolla | hoja_verde | 16–27 | 60–85 | 20000–45000 | 10–16 | 7 | 250 |
| Lechuga | Morada | hoja_verde | 15–28 | 55–85 | 20000–45000 | 10–16 | 6 | 220 |
| Albahaca | Genovesa | hierbas | 18–30 | 50–80 | 20000–45000 | 12–16 | 5 | 80 |

**Sobre la luz.** El campo `intensidad_luz_min/max` de `Variedad` se medía en lux aunque decía «µmol»; D-105 corrigió la unidad. El
simulador de Node-RED manda lux (base 30000) y `iot/servicios/lecturas.py` compara la lectura directo contra ese rango: por eso el rango va
en 20000–45000 y la demo no dispara alertas de luz falsas.

Con esto, el umbral efectivo de Norte (Criolla y Morada) queda en 16–27 °C y 60–85 %. El simulador manda 24 ± 1,5 °C y 70 ± 4 %: todo
adentro. El botón «Temperatura alta (35 °C)» queda afuera.

Ciclos (`EtapaProductiva.duracion_estimada_dias`):

| Variedad | Germinación | Crecimiento | Maduración |
|---|---|---|---|
| Lechuga Criolla | 10 | 20 | 14 |
| Lechuga Morada | 10 | 20 | 14 |
| Albahaca Genovesa | 10 | 25 | 10 |

Cada variedad tiene su semilla (`inventario.servicios.semillas.crear_semilla`, el nombre lo arma el sistema).

## 7. Categorías e insumos

Categorías nuevas (no del sistema):

| Categoría | Consumo directo |
|---|---|
| Nutrientes | como_costo_de_los_lotes |
| Sanidad vegetal | como_costo_de_los_lotes |

Insumos (catálogo):

| Insumo | Categoría | Unidad | Controla vencimiento |
|---|---|---|---|
| Semilla Lechuga Criolla | semillas (del sistema) | unidad | sí |
| Semilla Lechuga Morada | semillas | unidad | sí |
| Semilla Albahaca Genovesa | semillas | unidad | sí |
| Bandeja de cartón x 12 | envases (del sistema) | unidad | no |
| Bolsa compostable 30x40 | envases | unidad | no |
| Solución nutritiva A | Nutrientes | l | no |
| Fungicida biológico | Sanidad vegetal | l | sí |
| Nodo ESP32 | repuestos_de_hardware (del sistema) | unidad | no |
| Sensor DHT22 | repuestos_de_hardware | unidad | no |
| Sensor de luz BH1750 | repuestos_de_hardware | unidad | no |
| Sonda DS18B20 | repuestos_de_hardware | unidad | no |
| Sensor de nivel flotante | repuestos_de_hardware | unidad | no |
| Ventilador 12 V | repuestos_de_hardware | unidad | no |
| Motor de ventana | repuestos_de_hardware | unidad | no |

(Los nombres de las semillas los arma el sistema como «Semilla {cultivo} {variedad}», sin «de»; la tabla ya los trae así.)

Existencias por invernadero (habilitación con mínimo y precio de referencia, y la carga inicial con el motivo `carga_inicial`):

| Invernadero | Insumo | Mínimo | Precio ref. | Lote: cantidad | Vence |
|---|---|---|---|---|---|
| Norte | Semilla Lechuga Criolla | 200 | 15,00 | 2000 | HOY+90 |
| Norte | Semilla Lechuga Morada | 200 | 18,00 | 1500 | HOY+90 |
| Norte | Bandeja de cartón x 12 | 20 | 350,00 | 150 | — |
| Norte | Bolsa compostable 30x40 | 50 | 80,00 | 400 | — |
| Norte | **Solución nutritiva A** | **20** | 4200,00 | **12** | — |
| Norte | **Fungicida biológico** | 2 | 9800,00 | **3** (vence pronto) y 5 | **HOY+3** y HOY+120 |
| Norte | Cada uno de los 7 repuestos de hardware | 0 | (ver abajo) | 2 | — |
| Sur | Semilla Albahaca Genovesa | 150 | 22,00 | 1000 | HOY+90 |
| Sur | Bandeja de cartón x 12 | 20 | 350,00 | 100 | — |
| Sur | Solución nutritiva A | 15 | 4200,00 | 40 | — |

Precios de referencia de los repuestos: nodo 18000, DHT22 6500, BH1750 4800, DS18B20 3900, nivel 5200, ventilador 15000, motor 27000.

Para qué sirve cada fila marcada:

- **Solución nutritiva A en Norte** está por debajo del mínimo (12 < 20). Muestra la alerta de stock bajo, y con CMP-07 el pedido automático
  (paso 63). Con un margen de 20 %, la cantidad pedida es 20 × 1,2 − 12 = **12 l**.
- **Fungicida biológico, lote de 3 l** vence en HOY+3. El paso 10 del proceso diario (`revisar_vencimientos`) lo avisa porque cae dentro de
  `dias_aviso_vencimiento` (15).

## 8. Proveedores

| Clave | Tipo | Razón social / Nombre | CUIT | Correo | Teléfono | Especialidades |
|---|---|---|---|---|---|---|
| proveedor1 | jurídica | Agroinsumos Litoral S.A. | 30718889908 | `<base>+proveedor1@gmail.com` | 3764 420001 | Nutrientes, Sanidad vegetal, semillas |
| proveedor2 | jurídica | Electrónica Guaraní S.R.L. | 30713334401 | `<base>+proveedor2@gmail.com` | 3764 420002 | repuestos_de_hardware |
| proveedor3 | física | Ramón Ojeda | 20334445551 | `<base>+proveedor3@gmail.com` | 3764 420003 | Nutrientes, envases |

Con CMP-07, el pedido automático de la Solución nutritiva A invita a proveedor1 y proveedor3 (los dos especializados en Nutrientes).

## 9. Clientes y direcciones

| Clave | Tipo | Razón social / Nombre | CUIT | Correo | Teléfono | Dirección (urbana) | Localidad |
|---|---|---|---|---|---|---|---|
| cliente1 | jurídica | Súper Del Parque S.A. | 30714567809 | `<base>+cliente1@gmail.com` | 3764 430001 | Av. Uruguay 2450 | Posadas |
| cliente2 | jurídica | Restaurante El Mensú S.R.L. | 30711223300 | `<base>+cliente2@gmail.com` | 3764 430002 | Av. Las Heras 1180 | Garupá |
| cliente3 | física | Marta Villalba | 27315558889 | `<base>+cliente3@gmail.com` | 3764 430003 | Calle Junín 1745 | Posadas |

CUIT de reserva, válido y sin usar, por si hace falta un cliente más en vivo: **20284561237**.

## 10. Vehículos

| Patente | Tipo | Marca | Modelo | Capacidad (kg) | Transportista |
|---|---|---|---|---|---|
| AE123BC | camioneta | Toyota | Hilux | 800 | transportista1 |
| AF456DE | utilitario | Renault | Kangoo | 500 | transportista2 |

## 11. Contabilidad

- La contabilidad se inicia con CON-INI-EJE (`contabilidad.servicios.ejercicios.iniciar_ejercicio`, tarea CON-05), con el Contador de la demo (`contador1`) como actor: el
  ejercicio empieza el **primer día del mes de HOY** y el **asiento de apertura N.º 1** (fecha: ese día) carga **Caja $ 1.000.000,00 al Debe y Capital Inicial $ 1.000.000,00 al
  Haber**. Es la primera sección que se ejecuta después de las cuentas, la organización, la configuración y la geografía: sin ejercicio ninguna operación con asiento se registra.
- No se cargan asientos manuales ni contraasientos. Los demás asientos son los que generan los servicios (carga inicial de stock, lotes existentes).
- **Fechas de asientos manuales y contraasientos:** un asiento manual o un contraasiento con fecha **de un mes anterior al inicio de la demo** se rechaza (la fecha tiene que caer
  dentro del ejercicio, que empieza el primer día del mes de HOY). Si en la presentación se quiere registrar uno, la fecha tiene que ser de ese mes (y no posterior a hoy). Los asientos
  automáticos con una fecha anterior (por ejemplo, un lote existente sembrado hace semanas) no se rechazan: van al ejercicio abierto con la fecha de hoy y la descripción aclara la fecha real (D-102).

## 12. Lotes existentes (PRD-05, `registrar_lote_existente`, actor = el Agrónomo del invernadero)

Se cargan **antes de cualquier siembra normal** (PRD-05 solo vale en un invernadero sin siembras normales concretadas).

| Clave | Invernadero | Variedad | Etapa actual | Fecha de siembra | Ingreso a la etapa | Plantas | Sector: plantas | Costo estimado |
|---|---|---|---|---|---|---|---|---|
| LN-1 | Norte | Lechuga Criolla | maduracion | HOY−32 | HOY−2 | 300 | Maduración N1: 300 | 45000,00 |
| LN-2 | Norte | Lechuga Morada | crecimiento | HOY−29 | HOY−19 | 200 | Crecimiento N1: 200 | 24000,00 |
| LS-1 | Sur | Albahaca Genovesa | maduracion | HOY−39 | HOY−4 | 150 | Maduración S1: 150 | 18000,00 |

Qué muestra cada uno:

- **LN-1** es el stock maduro para la venta en vivo y para el suministro S-1. Su fecha máxima de cosecha es HOY+12.
- **LN-2** está en Crecimiento desde hace 19 días (duración 20). En vivo se le hace la transición a Maduración y pasa a ser stock maduro
  para el suministro S-2.
- **LS-1** muestra el segundo invernadero, con otro cultivo y otro Agrónomo. Su fecha máxima es HOY+6.

## 13. Contratos de suministro (COM-PCT-SUM, `pactar_suministro`, actor = vendedor1)

Se pactan **después** de los lotes, porque el pacto verifica y reserva stock maduro de la ventana (ahora 7 días).

### S-1 · Súper Del Parque (para la resolución por incumplimiento en vivo)

| Campo | Valor |
|---|---|
| Cliente | cliente1 |
| Duración | 3 meses |
| Incumplimientos tolerados | **0** (al primer incumplimiento aceptado se resuelve) |
| Multa de resolución | 50000,00 |
| Cláusula del suministrado | plazo de pago 10 días; indemnización por retraso de pago 1500,00 |
| Detalle | Lechuga Criolla, dirección Av. Uruguay 2450 (Posadas), **60 plantas cada 7 días**, primera entrega **HOY**, precio fijo 900,00 |
| Cláusula del suministrante | plazo de entrega 1 día; indemnización por retraso 2000,00; **cantidad mínima 55**; indemnización por faltante 300,00 |

Al pactarlo, InfoPonia reserva los períodos HOY y HOY+7 (120 plantas de LN-1) y crea sus cosechas. La de HOY queda programada para HOY
(máximo entre hoy y HOY − 3).

### S-2 · Restaurante El Mensú (para la pre-reserva automática en vivo)

| Campo | Valor |
|---|---|
| Cliente | cliente2 |
| Duración | 3 meses |
| Incumplimientos tolerados | 2 |
| Multa de resolución | 30000,00 |
| Cláusula del suministrado | plazo de pago 10 días; indemnización 1500,00 |
| Detalle | Lechuga Morada, dirección Av. Las Heras 1180 (Garupá), **40 plantas cada 7 días**, primera entrega **HOY+8**, precio fijo 1100,00 |
| Cláusula del suministrante | plazo 1 día; indemnización por retraso 2000,00; cantidad mínima 35; indemnización por faltante 350,00 |

Al pactarlo, la primera entrega (HOY+8) queda fuera de la ventana (HOY+7): **no se reserva nada**. Cuando en vivo se corre el proceso
diario con `--fecha HOY+1`, la ventana llega a HOY+8 y el paso 40 reserva las 40 plantas del lote LN-2 (si ya pasó a Maduración) y crea
la cosecha sola. Si LN-2 todavía no pasó, aparece la alerta de período sin cubrir, que también es un resultado automático válido.

## 14. Sistema IoT de Norte (actor = agronomo1)

Sistema: invernadero Norte; rango de la solución 18,0 a 24,0 °C; modelo «ESP32». El registro del sistema (`registrar_sistema_iot`) crea
también el **nodo** («Nodo Norte», insumo Nodo ESP32): no se da de alta con `alta_hardware`.

**El token.** El servicio lo genera siempre al registrar el sistema y lo devuelve en claro; la carga lo descarta sin guardarlo ni
imprimirlo (en la base queda solo su resumen y la fecha). El estudiante lo **regenera** en la pantalla (IoT · Sistema IoT · Regenerar
token), lo copia y lo usa en Node-RED. Así nunca pasa por la salida de un comando; `estado_demo` dice si fue generado y cuándo, no su valor.

Equipos (`alta_hardware`, solo sensores y actuadores; fecha de instalación HOY). El `modelo` es obligatorio en el servicio y sale del
insumo. El actuador no tiene campo de nombre: «Ventilador sector A» y «Ventana sector A» van en su descripción:

| Clase | Identificador | Nombre | Sector | Insumo | Modelo | Variable / tipo |
|---|---|---|---|---|---|---|
| sensor | norte/sectorA/temperatura | Temperatura sector A | Maduración N1 | Sensor DHT22 | DHT22 | temperatura ambiente |
| sensor | norte/sectorA/humedad | Humedad sector A | Maduración N1 | Sensor DHT22 | DHT22 | humedad |
| sensor | norte/sectorA/luz | Luz sector A | Maduración N1 | Sensor de luz BH1750 | BH1750 | intensidad lumínica |
| sensor | norte/tanque1/temp-solucion | Temperatura de la solución | — | Sonda DS18B20 | DS18B20 | temperatura de la solución |
| sensor | norte/tanque1/nivel | Nivel del tanque | — | Sensor de nivel flotante | Sensor de nivel flotante | nivel de solución |
| actuador | norte/sectorA/ventilador | Ventilador sector A (descripción) | Maduración N1 | Ventilador 12 V | Ventilador 12 V | Ventilador (tipo de la migración 0003) |
| actuador | norte/sectorA/ventana | Ventana sector A (descripción) | Maduración N1 | Motor de ventana | Motor de ventana | Ventana (tipo de la migración 0003) |

(Los identificadores son los del flujo de Node-RED, `docs/api/nodo/node-red/README.md`, sección 4. Calibración de los sensores, obligatoria en
todos menos en el nivel (que la ignora): temperatura −10 a 60, humedad 0 a 100, luz 0 a 100000, solución 0 a 50. Cargar los equipos no
consume el stock de los repuestos: las 2 unidades de cada uno quedan como están.)

Reglas de actuación (`alta_regla`):

| Sensor | Condición | Actuador | Acción |
|---|---|---|---|
| norte/sectorA/temperatura | supera_maximo | Ventilador sector A | Encender |
| norte/sectorA/temperatura | vuelve_al_rango | Ventilador sector A | Apagar |

## 15. Lo que NO se carga (se hace en vivo)

- La siembra nueva de Lechuga Criolla en Norte (200 plantas en Germinación N1).
- La transición de LN-2 a Maduración.
- La compra-venta de Marta Villalba (cliente3).
- Las cosechas concretadas, las rutas, las entregas, los cobros y la evaluación de la discrepancia.
- El token del sistema IoT y las lecturas (las manda Node-RED).
