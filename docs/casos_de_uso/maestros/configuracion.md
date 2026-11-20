# Casos de uso · maestros · Configuración operativa y perfil de la organización

Copia para el repo de los casos ADM-MOD-CFG (versión 0.2) y ADM-MOD-ORG (versión 0.1) del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 (MD-89 y MD-93) y con el glosario.

Son casos de uso breves (de alto nivel). **El código va en la app `maestros`** (D-37); el archivo de pruebas es
`maestros/tests/test_adm_mod_cfg.py` y `maestros/tests/test_adm_mod_org.py`.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| ADM-MOD-CFG | Modificar Configuración Operativa | Gerente | `maestros/tests/test_adm_mod_cfg.py` |
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
4. El logo es una imagen. Su tipo y su tamaño máximo están a precisar.
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
  disparador («Cuando exista PerfilOrganizacion»).
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

