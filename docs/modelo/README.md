# Extractos del modelo de dominio

Un archivo por app (`docs/modelo/<app>.md`) con las clases, los atributos, las asociaciones y las reglas del modelo de
dominio (ronda vigente, D-07) y los términos del glosario que usan las tareas. Se arma en claude.ai **para todas las clases
que necesita una ronda, antes de programar su primera tarea** (D-44): no se amplía tarea por tarea. Claude Code no lee
Drive: el cotejo con pendientes_MD y con el glosario se hace al armar el extracto, no al programar.

Cada clase trae, además de lo del modelo, lo que Claude Code necesita para no buscar: el nombre de código de cada
atributo y su tipo, las restricciones (únicos, obligatorios, rangos), a qué app pertenece la FK (regla A2 de D-37), los
valores fijos (listas y catálogos) y, si el modelo no los define, el valor que adopta el sistema con su decisión. Lo que
cambia respecto del diagrama se anota en la tabla «Pendientes de MD» del extracto, como en `maestros.md`.

Cada extracto empieza con este encabezado:

```
# Modelo de dominio · <app>

Copia para el repo de <documento de Drive>, <secciones>, versión <x> del <fecha>.
Cotejado con pendientes_MD hasta MD-<nn> y con el glosario del <fecha>. PROVISORIO.
Si este archivo y Drive no coinciden, avisá: no elijas en silencio.
```

Después, una sección por clase, con su nombre de código según D-05 cuando difiera del diagrama, y al final las reglas de
la sección 8 que la tocan, con su número (para citarlas en el docstring y en el nombre de las pruebas).
