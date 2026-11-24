# USR-09b · Topes de intentos de identificación y de pedidos de recuperación

Estado: pendiente | App: core | Rama: feature/usr-09b-topes-de-intentos

Depende de: —

Nota: este archivo era USR-09 (seguridad de producción). USR-09a (`USR-09a-endurecimiento-del-despliegue.md`) hizo los
puntos de HTTPS, cookies y HSTS (SEG-16), `DEBUG` apagado por defecto, `static_v` (se mantiene) y el correo de
recuperación en segundo plano (descartado), registrados en D-99. Quedan los dos puntos de abajo. El nombre del archivo se
conserva para no romper los enlaces.

Origen: `docs/estado.md`, «Siguiente», tarea 09, y dos temas abiertos (tope de intentos de identificación y tope de
pedidos de recuperación), traspasados sin cambios el 18/11/2026.

## Leer

- Casos de uso: docs/casos_de_uso/usuarios.md — SEG-05, SEG-12, USR-INI-SES, USR-RCP-CTR, USR-VNC-CTA
- Decisiones: D-19, D-32 (`vincular_cuenta`), D-33, D-34
- Reglas: .claude/rules/pruebas.md

## Límites

- Crea modelos: solo si el tope necesita un modelo para contar (o una caché) → revisá docs/disparadores.md
- Permitido fuera de la app: `config/settings.py`
- Migraciones: solo nuevas, en core
- Dependencias nuevas: ninguna
- Fuera de alcance: ingreso con Google (`docs/temas_abiertos.md`)

## Contenido

1. Tope de intentos de identificación para el inicio de sesión y `vincular_cuenta` juntos, que reemplazaría a SEG-05 y
   D-19 (ver D-32). SEG-05 y D-19 no lo tienen. El inicio de sesión y `vincular_cuenta` son el mismo oráculo de
   contraseñas, así que se evalúan juntos, por ejemplo con una espera creciente y no con el bloqueo de la cuenta
   (bloquearla dejaría sin acceso a quien tenga un email conocido). Necesita una decisión nueva que reemplace a D-19 y
   SEG-05, y un modelo o una caché para contar.
2. Tope de pedidos del enlace de recuperación (D-34): sin él se puede llenar de correos a una persona o agotar el límite
   diario de Gmail; las invitaciones las envía quien gestiona la cuenta, con sesión, pero el límite diario es el mismo.
   Se decide junto con el tope de identificación.

## Hecho cuando

- Los dos puntos tienen su decisión nueva (reemplaza a D-19 y a SEG-05).
- Pruebas: en el archivo del primer caso de uso que cita cada requisito SEG (D-25); se fijan en el plan.
- Comando de pruebas: se fija en el plan, con los módulos que toque.

## Verificación a mano (la completa Claude Code al cerrar)

## Cierre (la completa Claude Code al cerrar)
