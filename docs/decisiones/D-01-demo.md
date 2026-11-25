## D-NN — Datos y servicio de la demo de la defensa (reemplaza el punto 5 de D-96 solo para la demo)

- Fecha: <la del cierre>
- Decidió: el estudiante, a propuesta de Claude (hilo de planificación de la demo), antes de DAT-01.
- Antes:
  - D-95 punto 3 y D-96 punto 5 retiraron los cargadores de datos de prueba.
  - `CLAUDE.md` dice «no cargues datos de prueba».
  - La verificación a mano se hace creando todo a mano (`docs/patrones/verificacion_a_mano.md`).
  - Esto sigue valiendo para el desarrollo. Pero la defensa necesita una base con lotes en distintas etapas, contratos, stock e IoT listos el
    mismo día. Armar todo eso a mano, delante del tribunal, no entra en el tiempo de la defensa.
- Decisión:
  1. **Un solo comando de carga, `cargar_demo`, en una app nueva `demo`**, nivel 9 de D-37: puede importar de todas las apps y ninguna
     importa de ella. No tiene modelos ni migraciones.
  2. **Los datos están escritos en `docs/demo/datos_de_la_demo.md`** y el comando los aplica tal cual. Las fechas se calculan respecto del
     día de la carga (HOY).
  3. **El comando escribe solo a través de los servicios de cada app** (los mismos que usan las pantallas), con el actor que pide cada
     caso de uso. Así se respetan las reglas, la auditoría, los asientos y los avisos. Hay una sola excepción: lo que no tiene servicio
     (por ejemplo, el perfil de la organización o el alta de un usuario con contraseña fija) se escribe con el ORM, y la tarea lo anota.
  4. **Doble candado.** El comando se niega a correr, sin escribir nada, salvo que se cumplan las dos condiciones:
     - la variable de entorno `INFOPONIA_DEMO` vale `1`;
     - el nombre de la base conectada (`connection.settings_dict["NAME"]`) es exactamente `infoponia_demo`.

     También se niega si la base ya tiene cuentas con rol. La carga es para una base recién migrada: no mezcla datos.
  5. **La app `demo` solo se instala cuando `INFOPONIA_DEMO=1` o durante las pruebas.** En el servicio de producción el comando ni
     siquiera existe.
  6. **Los secretos no van al repo.** La contraseña de las cuentas sale de `INFOPONIA_DEMO_CONTRASENA` y la base de los correos, de
     `INFOPONIA_DEMO_CORREO`. El comando no los imprime.
  7. **Dónde corre: un servicio web aparte en Render (`infoponia-demo`, instancia Starter con Shell)**, del mismo repo y la misma rama que
     producción. Su base es un proyecto aparte de Neon (`infoponia-demo`) con la base `infoponia_demo`:
     - la rama raíz `main` queda vacía;
     - el servicio apunta a la rama hija `vivo`;
     - entre ensayos, `vivo` se reinicia desde `main` y se vuelve a migrar y cargar.

     Claude Code no se conecta a ninguna base de Neon (regla vigente de `CLAUDE.md`): el comando lo corre el estudiante en la Shell del
     servicio demo.
  8. **Fuera de la demo no cambia nada.** El punto 5 de D-96 y «no cargues datos de prueba» siguen vigentes para el desarrollo y las
     verificaciones a mano. `cargar_demo` no se usa para verificar tareas.
- Por qué:
  - Una base cargada por servicios es la única forma de mostrar en el día el flujo completo y los procesos automáticos sin falsear datos.
  - El doble candado y la app condicionada hacen imposible cargar la demo en la base de desarrollo o de producción por error.
  - Un proyecto de Neon aparte deja la base de producción fuera de alcance: otra cadena de conexión, otro proyecto.
- Alternativas descartadas:
  - Un volcado `pg_dump` de una base armada a mano: queda viejo de un día para el otro, porque las fechas importan.
  - Una copia local en la PC de la facultad: requiere instalar Python, PostgreSQL y dependencias en una PC ajena.
  - Una rama de Neon dentro del proyecto de producción: comparte el proyecto y su cuota, y un error de rama toca producción.
  - Render gratis: no tiene Shell ni tareas de un solo uso.
- Consecuencias:
  - `config/settings.py` suma `demo` a `INSTALLED_APPS` de forma condicional.
  - `CLAUDE.md` suma una línea: «Excepción: `cargar_demo` (D-NN), solo para la base `infoponia_demo`».
  - Las tareas DAT-01 y DAT-02 lo implementan.
- Fuentes: D-37, D-56, D-95, D-96, D-101; `docs/api/nodo/escenarios.md`; `docs/patrones/stock_maduro.md`; `docs/casos_de_uso/produccion/lote_existente.md`.
- Estado: propuesta (la aprueba el estudiante al cerrar DAT-01)
