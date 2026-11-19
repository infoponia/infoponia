# USR-09 · Seguridad de producción

Estado: pendiente | App: core | Rama: feature/usr-09-seguridad-produccion

Depende de: —

Origen: `docs/estado.md`, «Siguiente», tarea 09, y tres temas abiertos (tope de intentos de identificación, tope de
pedidos de recuperación y `DEBUG` en Render), traspasados sin cambios el 18/11/2026.

## Leer

- Casos de uso: docs/casos_de_uso/usuarios.md — SEG-05, SEG-12, SEG-16, USR-INI-SES, USR-RCP-CTR, USR-VNC-CTA
- Decisiones: D-19, D-29 (`static_v`), D-32 (`vincular_cuenta`), D-33, D-34
- Reglas: .claude/rules/pruebas.md

## Límites

- Crea modelos: solo si el tope de intentos lo necesita (un modelo o una caché para contar) → revisá docs/disparadores.md
- Permitido fuera de la app: `config/settings.py`
- Migraciones: solo nuevas, en core
- Dependencias nuevas: ninguna
- Fuera de alcance: ingreso con Google (`docs/temas_abiertos.md`)

## Contenido (tal cual estaba en `estado.md`)

1. Seguridad de producción: HTTPS, cookies seguras y HSTS (SEG-16).
2. `DEBUG` apagado si falta la variable de entorno. Render ya tiene `DJANGO_DEBUG=0` (verificado el 12/11/2026); en
   esta tarea, `DEBUG` queda apagado por defecto en el código.
3. Evaluar reemplazar `static_v` por `ManifestStaticFilesStorage` de WhiteNoise en producción (D-29).
4. Tope de intentos de identificación para el inicio de sesión y `vincular_cuenta` juntos, que reemplazaría a SEG-05 y
   D-19 (ver D-32). SEG-05 y D-19 no lo tienen. El inicio de sesión y `vincular_cuenta` son el mismo oráculo de
   contraseñas, así que se evalúan juntos, por ejemplo con una espera creciente y no con el bloqueo de la cuenta
   (bloquearla dejaría sin acceso a quien tenga un email conocido). Necesita una decisión nueva que reemplace a D-19 y
   SEG-05, y un modelo o una caché para contar.
5. Tope de pedidos del enlace de recuperación (D-34): sin él se puede llenar de correos a una persona o agotar el límite
   diario de Gmail; las invitaciones las envía quien gestiona la cuenta, con sesión, pero el límite diario es el mismo.
   Se decide junto con el tope de identificación.
6. Evaluar enviar el correo de recuperación en segundo plano (hoy el pedido tarda más cuando la cuenta existe).

## Hecho cuando

- Los seis puntos están resueltos o descartados con una decisión registrada.
- Los puntos 4 y 5 tienen su decisión nueva (reemplaza a D-19 y a SEG-05).
- Pruebas: en el archivo del primer caso de uso que cita cada requisito SEG (D-25); se fijan en el plan.
- Comando de pruebas: se fija en el plan, con los módulos que toque.

## Verificación a mano (la completa Claude Code al cerrar)

## Cierre (la completa Claude Code al cerrar)
