# USR-07 · Foto de perfil

Estado: bloqueada | App: core | Rama: feature/usr-07-foto-perfil

Depende de: el proveedor del almacenamiento de objetos y el permiso para agregar Pillow y `django-storages` (D-20). Sin
las dos cosas, frená.

## Leer

- Casos de uso: docs/casos_de_uso/usuarios.md — USR-GST-PRF (regla sobre la foto), SEG-19, «Pistas técnicas» (SEG-19)
- Decisiones: D-20, D-24 (la carga desde el celular se prueba en un dispositivo real), D-31 (el lugar de la foto ya
  está preparado en Mi perfil)
- Pantallas: docs/prototipos/cuentas_y_seguridad.html — `vPerfil`, `handlePhoto`
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md

## Límites

- Crea modelos: ningún modelo nuevo; un campo nuevo en `Usuario` (con el permiso para modificar un modelo mergeado)
- Permitido fuera de la app: `config/settings.py` (almacenamiento), `requirements.txt` (Pillow y `django-storages`)
- Migraciones: solo nuevas, en core
- Dependencias nuevas: Pillow y `django-storages`, cuando las apruebe el estudiante
- Fuera de alcance: la foto de las cuentas vinculadas (no se comparte, D-20)

## Hecho cuando

- Cada cuenta puede cargar, cambiar y quitar su foto desde Mi perfil, con las reglas de SEG-19 y D-20.
- Pruebas: core/tests/test_usr_gst_prf.py
- Comando de pruebas: python manage.py test core.tests.test_usr_gst_prf --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

## Cierre (la completa Claude Code al cerrar)
