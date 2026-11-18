# Extractos del modelo de dominio

Un archivo por app (`docs/modelo/<app>.md`) con las clases, los atributos, las asociaciones y las reglas del modelo de
dominio (ronda vigente, D-07) y los términos del glosario que usan sus tareas. Se arma en claude.ai, al escribir la
primera tarea que lo necesita, y se amplía con cada tarea nueva («justo a tiempo»). Claude Code no lee Drive: el cotejo
con pendientes_MD se hace al armar el extracto, no al programar.

Cada extracto empieza con este encabezado:

```
# Modelo de dominio · <app>

Copia para el repo de <documento de Drive>, <secciones>, versión <x> del <fecha>.
Cotejado con pendientes_MD hasta MD-<nn> y con el glosario del <fecha>. PROVISORIO.
Si este archivo y Drive no coinciden, avisá: no elijas en silencio.
```

Después, una sección por clase, con su nombre de código según D-05 cuando difiera del diagrama, y al final las reglas de
la sección 8 que la tocan, con su número (para citarlas en el docstring y en el nombre de las pruebas).
