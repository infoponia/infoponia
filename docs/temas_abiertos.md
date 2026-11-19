# Temas abiertos — InfoPonia

Temas que todavía no tienen tarea ni disparador. Se leen al planificar, no en cada sesión. Cuando un tema pasa a tener
tarea (`docs/tareas/`) o disparador (`docs/disparadores.md`), se saca de acá y se anota adónde fue.

Copiados sin cambios de `docs/estado.md`, «Temas abiertos», el 18/11/2026.

- Lista cerrada de los casos de uso del 80% y orden de implementación.
- Ingreso con Google: trabajo futuro, fuera de este bloque.
- Hacer configurables por `.env` el host, el puerto, el nombre y el usuario de la base local.
- Integrar el logo de InfoPonia: favicon y marca en el inicio de sesión. Cuándo: cuando esté el logo definitivo.
- Funciones de pruebas con el mismo nombre y distinto trabajo, que no se unificaron a propósito: `datos_validos`
  (`test_usr_alt_usr.py` arma los datos de un alta; `test_usr_mod_usr.py` toma los datos actuales de una cuenta) y
  `codigos` (`core/tests/concurrencia.py` devuelve todos los códigos de un error; `test_usr_cmb_ctr.py` recibe el
  campo y devuelve solo los de ese campo). Si se renombran, que sea sin cambiar lo que verifica ninguna prueba.
  Cuándo: opcional, sin fecha.
- Búsqueda de la lista de cuentas sin distinguir tildes, con `unaccent` de PostgreSQL. Cuándo: opcional, sin
  fecha.
- Volver a la pantalla pedida después de iniciar sesión (D-29): solo se evalúa el rol. Una cuenta fuera de alcance
  dentro de una pantalla permitida (por ejemplo, `/usuarios/7/`) sigue dando 403; cubrirla exigiría ejecutar la
  pantalla pedida dos veces. Cuándo: sin fecha.
- Mecanismo de notificaciones (agregado el 18/11/2026, D-38). Las notificaciones no se modelan: son una característica
  del sistema, no un concepto del negocio. Pero varias postcondiciones las piden (PROD-ALT-INV e, PROD-MOD-INV c,
  USR-ALT-USR d) y el prototipo las muestra en la campana. Falta decidir si se construye el mecanismo y cuándo. Mientras
  tanto, esas postcondiciones quedan sin implementar. Cuándo: sin fecha.

## Adónde fueron los demás temas de `estado.md` (18/11/2026)

| Tema | Ahora está en |
|---|---|
| Reparto final de apps | D-37 |
| Tope de pedidos de recuperación de contraseña | `docs/tareas/usuarios/USR-09-seguridad-produccion.md` |
| Tope de intentos de identificación | `docs/tareas/usuarios/USR-09-seguridad-produccion.md` |
| `DEBUG` apagado por defecto (Render ya tiene `DJANGO_DEBUG=0`) | `docs/tareas/usuarios/USR-09-seguridad-produccion.md` |
| Proveedor del almacenamiento para la foto de perfil | `docs/tareas/usuarios/USR-07-foto-perfil.md` y «Esperas» de `docs/estado.md` |
| Logo y nombre de la organización configurables | `docs/disparadores.md`, «Cuando exista PerfilOrganizacion» |
| Campana y notificaciones del marco | `docs/disparadores.md`, «Cuando exista la primera notificación» |
| Ámbito por invernadero de SEG-13 | `docs/disparadores.md`, «Cuando exista Invernadero» |
