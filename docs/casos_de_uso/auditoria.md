# Casos de uso del bloque Auditoría

Copia para el repo del caso de uso AUD-CNS-REG del documento de Drive «CU extendidos» (versión 0.1, 17/11/2026). Si este
archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Es un caso de uso nuevo y propio: no está en `usuarios.md` porque la auditoría no es del bloque de cuentas. La usan hoy
las cuentas y la usarán los módulos de negocio (D-36). Las decisiones que lo acompañan están en `docs/decisiones.md`
(D-22 y D-36). Los ítems MD-nn y SEG-nn que se citan están en los documentos de Drive y en `docs/casos_de_uso/usuarios.md`
(SEG-13, SEG-14).

No hay prototipo de esta pantalla (D-24): sigue el estilo de la lista de Cuentas y las convenciones de D-29.

Para nombrar las pruebas: las reglas están numeradas, así que se usa `test_regla_<numero>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| AUD-CNS-REG | Consultar Registro de Auditoría | Gerente y Administrador | `core/tests/test_aud_cns_reg.py` |

---

## AUD-CNS-REG · Consultar Registro de Auditoría

**Versión:** 0.1

**Actores:** Gerente y Administrador, cada uno con su alcance (regla 1).

**Objetivo:** consultar quién hizo qué, cuándo y con qué cambios, para controlar las operaciones y reconstruir lo que
pasó con una cuenta u objeto.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Gerente o de Administrador.

**Postcondición:**
a. No se producen cambios en el Sistema.

**Reglas:**
1. Alcance: el Administrador consulta todos los registros. El Gerente consulta los registros de los módulos de negocio y
   los de cuentas en los que actuó o fue afectada una cuenta de Agrónomo, Capataz, Vendedor, Transportista o Técnico; no
   consulta los registros en los que solo intervienen Administradores o la cuenta del Gerente (MD-58).
2. Se filtra por rango de fechas, por la cuenta que actuó, por acción y por la cuenta u objeto afectado. Por defecto se
   muestran primero los registros más recientes.
3. De cada registro se ven la fecha y hora, la cuenta que actuó y su rol en ese momento («InfoPonia» si actuó el
   Sistema), la acción, los afectados y, de cada dato que cambió, su valor anterior y su valor nuevo. Las referencias a
   otros objetos se muestran con el texto que tenían en el momento del cambio.
4. Los registros no se modifican ni se borran desde ninguna pantalla.
5. Ninguna contraseña ni enlace de acceso aparece en la auditoría (SEG-14).
6. La consulta no se audita (SEG-14).
7. Desde la ficha de una cuenta (USR-CNS-USR) se accede a sus registros con el filtro de esa cuenta ya aplicado.

**Trabajo futuro:** exportar los registros filtrados a CSV. Fuera de la tarea AUD-CNS-REG.

## Cómo quedó implementado (referencia para quien lo lea después)

Esta sección no es parte del caso de uso: resume dónde está cada cosa. El detalle y el porqué están en D-36.

- Alcance (regla 1): `RegistroAuditoria.objects.visibles_para(actor)`, en `core/models.py`. Un registro es «de cuentas» por
  su acción (`ACCIONES_DE_CUENTAS`); los de cualquier otra acción (los módulos de negocio, `ACCIONES_DE_NEGOCIO`) los ve el
  Gerente.
- Consulta y filtros (regla 2): `consultar_auditoria`, `obtener_registro` y `puede_ver_auditoria_de`, en
  `core/servicios.py`. Filtrar por una cuenta fuera del alcance del Gerente da 403; por una que no existe, 404 (D-28).
- Pantallas (reglas 3, 4 y 7): «Auditoría» (`/auditoria/`) y su detalle (`/auditoria/<id>/`); «Ver auditoría» en la ficha.
  Solo aceptan GET.
- Formato de lo que se ve (regla 3): `cambios` con antes y después, `datos` de contexto y referencias `{id, texto}`
  (D-36); `RegistroAuditoria.objects.registrar` lo valida, y no deja guardar contraseñas (reglas 5 y SEG-14).
