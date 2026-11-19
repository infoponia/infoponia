# MAE-02b · Alerta: baja y reactivación de cuenta, Inicio del Gerente y consulta (CU-46)

Estado: pendiente | App: maestros | Rama: feature/mae-02-alerta (o la que indique el equipo)

Depende de: MAE-02a (si no está hecha, frená)

## Leer

- Casos de uso: docs/casos_de_uso/usuarios.md — USR-BAJ-USR: post e y regla 4; USR-MOD-USR: la reactivación.
  docs/casos_de_uso/maestros/invernaderos.md — PROD-CNS-INV: regla 5.
  CU-46 (Consultar Alerta), que no tiene copia en el repo; texto del documento de alto nivel:
  > «Actores: Agrónomo o superior. Objetivo: consultar el listado de alertas en estado “activa”, buscar una en particular
  > y acceder a su información completa. Postcondición: no se produjeron cambios en el sistema».
- Modelo: docs/modelo/maestros.md — Alerta (regla 7 de 8.18; reglas 3 y 4 de 8.22, MD-60 y MD-61)
- Decisiones: D-22, D-30, D-32, D-36, D-37, D-38, D-40, D-41
- Patrones: docs/patrones/bloqueos.md, docs/patrones/auditoria.md
- Pantallas: docs/prototipos/produccion/datos_maestros_y_produccion.html — `personalCard` y `alertas()` (solo guía visual)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md

## Orden de los pasos (para poder recortar lo último)

1. Puntos de extensión de `core` (`core/extensiones.py`) y la baja y reactivación de cuenta.
2. El Inicio del Gerente («Personal por asignar», regla 5 de PROD-CNS-INV).
3. `abrir_alerta` (regla 7 de 8.18).
4. **Al final, la pantalla de CU-46.** Si falta tiempo, se deja para otra tarea y nace como disparador.

## Supuestos de CU-46 (el caso de uso de alto nivel no los precisa)

- El alcance es `Alerta.objects.para(usuario)`.
- Muestra solo las alertas activas.
- Filtra por invernadero y por tipo.
- Abrir el detalle llama a `abrir_alerta`.
- Funciona sin JavaScript (HTMX solo reemplaza la tabla).
- Vive en `maestros`.
- El panel de CU-41 de IoT reutiliza la consulta (se documenta en docs/api/alertas.md).
- Que abrir la alerta la marque «leída» contradice la postcondición de CU-46: va al cierre como pendiente de pendientes_CU.

## Límites

- Crea modelos: ninguno
- Permitido fuera de la app: core/extensiones.py (nuevo); core/servicios.py (`baja_usuario` y `reactivar_usuario`);
  core/views.py (`inicio` y la ventana de baja de cuenta); core/templates/core/inicio.html y la plantilla de la ventana
  de baja; core/templatetags/iconos.py (solo si hace falta un ícono, copiado del prototipo); docs/api/alertas.md.
  La entrada «Alertas» del menú se registra desde `MaestrosConfig.ready()`.
- Migraciones: ninguna
- Dependencias nuevas: ninguna
- Fuera de alcance: notificaciones y campana (tarea aparte en core, D-42)

## Hecho cuando

- La baja de una cuenta con invernaderos a cargo crea las alertas `sin_{rol}` y, si es un Agrónomo, pasa sus alertas
  activas al Gerente (regla 4 de 8.22, MD-61); la ventana informa los invernaderos a cargo (regla 4 de USR-BAJ-USR).
- Reactivar la cuenta resuelve la alerta de su rol y, si es un Agrónomo, aplica D4.
- El Inicio del Gerente lista los invernaderos con personal por asignar, con el acceso a modificar.
- `abrir_alerta` y la pantalla de CU-46.
- Pruebas: core/tests/test_usr_baj_usr.py, core/tests/test_usr_mod_usr.py, maestros/tests/test_usr_baj_usr.py,
  maestros/tests/test_usr_mod_usr.py, maestros/tests/test_prod_cns_inv.py, maestros/tests/test_alerta.py y
  maestros/tests/test_cns_alr.py (CnsAlrServicioTests y CnsAlrVistaTests; el código es una propuesta).
- Pruebas de concurrencia P5, P6 y P7 (plan de MAE-02).
- Comando de pruebas:
  python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test maestros core --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

## Cierre (la completa Claude Code al cerrar)
