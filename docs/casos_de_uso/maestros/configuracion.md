# Casos de uso · maestros · Configuración operativa y perfil de la organización

Copia para el repo de los casos ADM-MOD-CFG (versión 0.2) y ADM-MOD-ORG (versión 0.1) del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 (MD-89 y MD-93) y con el glosario.
**Desde el lote IoT I2b (22/11/2026)** suma, al final, la sección «Módulo IoT» de ADM-MOD-CFG para la ronda «IoT 1» (IOT-04): los 14
parámetros de MD-112 que IOT-ENT-INF («Temas abiertos») pide agregar. Esas reglas **todavía no están en «CU extendidos»**: hay que pasarlas.

Son casos de uso breves (de alto nivel). **El código va en la app `maestros`** (D-37); el archivo de pruebas es
`maestros/tests/test_adm_mod_cfg.py` y `maestros/tests/test_adm_mod_org.py`.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| ADM-MOD-CFG | Modificar Configuración Operativa | Gerente | `maestros/tests/test_adm_mod_cfg.py` (la sección «Módulo IoT»: `maestros/tests/test_adm_mod_cfg_iot.py`, IOT-04) |
| ADM-MOD-ORG | Modificar Perfil de la Organización | Gerente | `maestros/tests/test_adm_mod_org.py` |

---

## ADM-MOD-CFG · Modificar Configuración Operativa

**Actores:** Gerente. **Tipo:** secundario, esencial. **Versión:** 0.2

**Objetivo:** ajustar los parámetros que rigen la operación de la organización.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

**Postcondición:**
a. Se actualizaron los parámetros indicados de la configuración operativa.
b. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la configuración y, de cada parámetro
   modificado, su valor anterior y su valor nuevo.

**Reglas:**
1. Solo el Gerente modifica la configuración. Es un registro único, creado en la puesta en marcha con los valores
   iniciales (MD-89): no se crea ni se elimina. Al entrar, el Sistema muestra los valores actuales.
2. Los parámetros, con su valor inicial, son: en Producción, la merma máxima tolerada por lote (15 %) y el horizonte
   de planificación de cosecha (30 días); en Insumos, el aviso de vencimiento (15 días antes); en Comercial, la pre-
   reserva de suministros (14 días), la anticipación de cosecha de la compra-venta (1 día), la anticipación de cosecha
   del suministro (3 días), la vigencia del enlace de confirmación (3 días) y la vigencia del enlace de decisión ante
   un faltante (2 días); en Compras, los días límite para cotizar (3), la validez de las cotizaciones (7 días) y la
   tolerancia de cobertura del pedido (0 %); en Entregas, el máximo de entregas diarias por transportista (10) y el
   máximo de localidades distintas por día (3).
3. Todos los valores son enteros y obligatorios. La merma máxima va de 1 a 100. La tolerancia de cobertura va de 0 a
   100. Las anticipaciones de cosecha son de 0 o más. Los demás parámetros son de 1 o más, salvo la validez de las
   cotizaciones, que es mayor que 0.
4. La anticipación de cosecha del suministro no puede superar la pre-reserva de suministros. Si no se cumple, el
   Sistema no guarda e indica qué valor corregir.
5. Si el horizonte de cosecha queda menor que la pre-reserva, algunas reservas caerán fuera del horizonte. El Sistema
   lo advierte y deja guardar.
6. Se guarda todo o nada: si un valor no es válido, no se guarda ninguno y el Sistema marca los campos con error.
7. El cambio rige hacia adelante: no recalcula reservas, cosechas programadas ni cotizaciones ya pedidas. La merma
   máxima se aplica desde la próxima merma que se registre, y el aviso de vencimiento, desde la próxima revisión
   diaria. La vigencia del enlace de confirmación sí alcanza a los enlaces ya enviados: se calcula cuando el cliente
   ingresa, con el valor vigente del parámetro.

---

## ADM-MOD-ORG · Modificar Perfil de la Organización

**Actores:** Gerente. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** mantener los datos de identidad de la organización que aparecen en el encabezado y en los documentos que genera el Sistema.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

**Postcondición:**
a. Se actualizaron los datos indicados del perfil de la organización.
b. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del perfil y, de cada dato modificado, su
   valor anterior y su valor nuevo. Del logo se registra que cambió, no la imagen.

**Reglas:**
1. Solo el Gerente modifica el perfil. Es un registro único, creado en la puesta en marcha (MD-89): no se crea ni se
   elimina. Al entrar, el Sistema muestra los datos actuales.
2. El nombre es obligatorio. Los demás datos son opcionales: CUIT, teléfono, email, dirección, logo y hasta cuatro
   colores (MD-93).
3. El email se valida por formato. El CUIT se valida por formato y dígito verificador.
4. El logo es una imagen JPG, PNG o WebP de hasta 5 MB (no SVG). Se guarda sin recortar, con el lado mayor de 512 px como
   máximo y conservando la transparencia (D-106).
5. Los colores se cargan en orden, y el primero es el principal. Si no se carga ninguno, el Sistema usa su paleta por
   defecto.
6. Los datos aparecen en el encabezado y en los comprobantes que genera el Sistema, desde el siguiente documento que
   se emita. Los ya emitidos no cambian.
7. Se guarda todo o nada: si un dato no es válido, no se guarda ninguno.

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45, D-48)

Tarea: **MAE-04**. Todo lo de este archivo se implementa, con estas decisiones de aplicación:

- **Singletons (MD-89).** `ConfiguracionOperativa` y `PerfilOrganizacion` son una sola fila cada una, creada por migración con los
  valores iniciales (`docs/patrones/datos_de_migracion.md`, «Singletons»). No hay alta ni baja: la unicidad la garantiza la
  base (columna `singleton` con valor fijo y restricción única) y el servicio solo la actualiza. El `idConfiguracion` del
  modelo es el `id` automático.
- **Parámetro «vigencia del enlace de decisión ante un faltante».** El caso de uso y el modelo (`diasVigenciaEnlaceFaltante`,
  valor inicial 2) lo tienen; **el prototipo no lo muestra**. Se implementa lo del caso de uso (manda el CU, regla L7): MAE-04
  lo agrega a la pantalla en el grupo «Comercial», con el mismo formato que los demás. Hay que avisarlo al equipo.
- **Parámetros de IoT** (umbrales y tiempos del módulo IoT, MD-112) **no** son de este caso de uso: los agrega la tarea de IoT.
- **Logo.** Fuera de la ronda (D-45). El perfil no tiene el campo y la pantalla no muestra el campo del logo: queda como
  disparador («Cuando exista PerfilOrganizacion»). **Actualización 27/11/2026:** lo implementa USR-07 con las reglas de
  D-106 (puntos 10 a 15): cargar, cambiar y quitar en la pestaña «Organización»; auditoría «sin logo» / «con logo» /
  «logo nuevo»; se ve en el encabezado y en las pantallas sin sesión, no en los correos.
- **Colores.** Hasta cuatro, formato `#RRGGBB`, opcionales; en orden: no se puede cargar el 2.º sin el 1.º ni el 3.º sin el 2.º
  (regla 5). El primero tiñe el sistema (D-48). **El sistema no valida el contraste:** un color muy claro hace ilegible el texto
  blanco de los botones (queda anotado en `docs/temas_abiertos.md`).
- **Nombre de la organización.** Sale del perfil (D-48); sin perfil, de `NOMBRE_ORGANIZACION`. Cambia en el encabezado, los
  correos y las pantallas sin sesión, desde el pedido siguiente.
- **Auditoría (D-36).** Acciones `modificacion_configuracion` y `modificacion_perfil`; en `cambios`, antes y después de cada
  parámetro modificado. Guardar sin cambios no audita (D-28).
- **Bloqueo.** La fila singleton se toma con `FOR NO KEY UPDATE`, se vuelve a leer y se compara contra lo leído
  (dos Gerentes a la vez: gana el último, el segundo ve sus cambios contra el valor ya modificado).
- **Dominios** (ADM-MOD-CFG regla 3): enteros; merma máxima 1 a 100; tolerancia de cobertura 0 a 100; anticipaciones de cosecha
  0 o más; los demás 1 o más (la validez de las cotizaciones, mayor que 0, que es lo mismo que 1 o más en enteros).
- **Reglas 4 y 5 de CFG** como en el prototipo (`cfgErr` y la advertencia del horizonte), pero validadas también en el servidor.
- **Regla 7 de CFG** (rige hacia adelante): `maestros` no recalcula nada; los consumidores leen el valor vigente cuando lo
  necesitan. Quien use un parámetro lo lee con `maestros.servicios.configuracion.obtener()` en cada uso (nunca lo guarda en una
  constante de módulo).

---

## ADM-MOD-CFG · Sección «Módulo IoT» (ronda «IoT 1», IOT-04)

Fuentes: IOT-ENT-INF, «Temas abiertos» («ADM-MOD-CFG debe sumar los parámetros del IoT»); MD-112 y la tabla de `docs/modelo/iot.md`,
«Parámetros IoT de ConfiguracionOperativa», que **manda** en nombres, dominios y valores iniciales; la pantalla `config` y `CFGP` del
prototipo `docs/prototipos/iot/` (textos de ayuda). El caso de uso v0.2 de Drive no los lista todavía: **estas reglas se agregan a ADM-MOD-CFG
en «CU extendidos»** (redactadas como continuación de sus reglas 2, 3, 4 y 7).

**Reglas (a pasar a «CU extendidos»):**

2b. En el Módulo IoT, con su valor inicial: en Comandos, los reintentos de un comando (3) y el intervalo entre intentos (60 segundos); en
    Luz y fotoperíodo, el horario de luz (de 8 a 18 h) y el umbral de luz para el fotoperíodo (1.000 lux); en Actividad y comunicación,
    los minutos sin actividad de un sensor (5), los minutos sin comunicación del nodo (3) y la antigüedad máxima de una lectura (5
    minutos); en Reglas y alertas, las lecturas de confirmación (3) y la histéresis de la temperatura (1 °C), de la humedad (3 % HR), de la
    intensidad lumínica (2.000 lux) y de la temperatura de la solución (1 °C); en Retención, los días de retención de las lecturas (7).
    Todos están a confirmar con el Jardín Botánico.
3b. Son enteros, salvo las dos histéresis de temperatura, que admiten un decimal. Dominios: reintentos de 0 a 10; intervalo de 10 a 3600;
    inicio del horario de luz de 0 a 23 y fin de 1 a 24; umbral de luz de 1 a 100000; minutos sin actividad, sin comunicación y antigüedad,
    de 1 a 1440; lecturas de confirmación de 1 a 10; histéresis de temperatura y de la solución de 0 a 10; de humedad de 0 a 30; de luz de
    0 a 20000; retención de 1 a 365.
4b. El fin del horario de luz es posterior a su inicio. Si no se cumple, el Sistema no guarda e indica qué valor corregir.
5b. Si se reducen los días de retención, el Sistema advierte que la próxima revisión periódica borrará las lecturas anteriores a la nueva
    fecha límite (salvo las que originaron una alerta o dispararon una regla) y deja guardar.
7b. Los parámetros del IoT también rigen hacia adelante: los reintentos y el intervalo, desde el próximo intento de cada comando; el
    horario de luz, las histéresis, la antigüedad máxima y las lecturas de confirmación, desde la próxima lectura; los minutos sin
    actividad y sin comunicación, el umbral de luz y la retención, desde la próxima revisión periódica. No se recalculan los fotoperíodos
    ni los resúmenes ya guardados.

Además, el Agrónomo **consulta** estos parámetros en el panel de monitoreo (regla 6 de IOT-CNS-LEC), en solo lectura: la pantalla de
configuración sigue siendo solo del Gerente (D-76, punto 9).

### Cómo se aplica (IOT-04)

- **Los campos ya existen:** IOT-01 los agregó a `ConfiguracionOperativa` con su migración de `maestros` y sus `CheckConstraint`. IOT-04 no
  crea columnas ni migraciones de `maestros`.
- **Misma pantalla, mismo servicio** (MAE-04): `/configuracion/`, pestaña «Configuración operativa». Suma el grupo «Módulo IoT» al final,
  con los cinco subgrupos de `CFGP` en ese orden, y lo valida y guarda `maestros.servicios.configuracion.modificar_configuracion`, con el
  mismo bloqueo, el mismo «todo o nada» (regla 6) y la misma auditoría (`modificacion_configuracion`, con antes y después de cada
  parámetro). Ningún servicio nuevo. Si COM-04 ya sumó `dias_aviso_vencimiento_camara`, se agrega igual, en su grupo; el orden de las
  migraciones no importa acá porque IOT-04 no tiene (`docs/patrones/trabajo_en_paralelo.md`).
- **Etiquetas y ayudas** (de `CFGP`; las que el prototipo deja vacías, nuevas):

| Campo | Etiqueta | Ayuda |
|---|---|---|
| `cant_reintentos_comando` | Reintentos de un comando | Después del primer intento (0 a 10). |
| `segundos_intervalo_reintento` | Intervalo entre intentos (s) | Espera de respuesta y tiempo mínimo entre intentos (10 a 3600). |
| `hora_inicio_luz` | Horario de luz: inicio (h) | Desde esta hora se compara la intensidad lumínica (0 a 23). |
| `hora_fin_luz` | Horario de luz: fin (h) | Hasta esta hora (1 a 24). |
| `lux_umbral_fotoperiodo` | Umbral de luz para el fotoperíodo (lux) | Las horas por encima de este valor cuentan como luz. Valor inicial: ajustalo según el cultivo. |
| `minutos_sin_actividad` | Minutos sin actividad | Un sensor que ya reportó y deja de informar genera alerta. |
| `minutos_sin_comunicacion` | Minutos sin comunicación | Un nodo que ya se comunicó y deja de hacerlo genera alerta y correo. |
| `minutos_antiguedad_lectura` | Antigüedad máxima de una lectura (min) | Las más viejas se guardan, pero no generan alertas ni disparan reglas. |
| `cant_lecturas_confirmacion` | Lecturas de confirmación | Lecturas seguidas que deben cumplir la condición para disparar una regla. |
| `histeresis_temperatura` | Histéresis de temperatura (°C) | Una alerta o regla se libera recién al alejarse del límite este valor. |
| `histeresis_humedad` | Histéresis de humedad (% HR) | Ídem, para la humedad. |
| `histeresis_luz` | Histéresis de intensidad lumínica (lux) | Ídem, para la intensidad lumínica. |
| `histeresis_temp_solucion` | Histéresis de temperatura de la solución (°C) | Ídem, para el rango de la solución. |
| `dias_retencion_telemetria` | Días de retención de lecturas | Se conservan las que originaron una alerta o una regla. Los resúmenes horarios no se borran. |

- **Mensajes de error por campo:** «Ingresá un entero entre {mín} y {máx}.»; en las dos histéresis de temperatura, «Ingresá un número entre 0
  y 10, con un decimal como máximo.»; regla 4b en `hora_fin_luz`: «El fin tiene que ser posterior al inicio.». La advertencia de la regla 5b
  se muestra como la de la regla 5 (no bloquea): «La próxima revisión periódica borrará las lecturas anteriores al {DD/MM/AAAA}, salvo las
  que originaron una alerta o una regla.».
- **Aviso al guardar** (el del prototipo): «Parámetros guardados. Rigen desde el próximo intento y la próxima lectura.» si cambió alguno del
  IoT; si no, el de MAE-04.
- Los consumidores leen el valor vigente con `obtener()` en cada uso: la API (IOT-03) una vez por pedido y la revisión una vez por corrida
  (regla 7b).

**Lo que difiere del prototipo:** el prototipo pide enteros también en las histéresis de temperatura; el modelo las define con un decimal
(`Decimal(3,1)`): manda el modelo. El prototipo deja entrar al Agrónomo a la pantalla en modo consulta; en el sistema la ve en el panel (D-76,
punto 9). La advertencia de la regla 5b no está en el prototipo: se agrega.

