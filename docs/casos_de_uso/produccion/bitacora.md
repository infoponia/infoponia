# Casos de uso · produccion · Bitácora

Copia para el repo de los casos PROD-REG-EVT (versión 0.1) y PROD-CNS-BIT (versión 0.2) del documento de Drive «CU extendidos» (casos breves), consultados el 20/11/2026. El código va en la app `produccion`.
Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026. Se quitaron las marcas ⛔ y los `**` sueltos del export de Drive y se corrigió la numeración. No cambió ninguna regla.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-REG-EVT | Registrar Evento | Agrónomo, Capataz | `produccion/tests/test_prod_reg_evt.py` |
| PROD-CNS-BIT | Consultar Bitácora | Agrónomo, Gerente | `produccion/tests/test_prod_cns_bit.py` |

---

## PROD-REG-EVT · Registrar Evento

Actores: Agrónomo y Capataz.
Tipo: secundario, esencial.
Versión: 0.1
Objetivo: dejar constancia en la bitácora de un hecho de un invernadero que no es una merma, una aplicación de insumos
   ni una operación que el Sistema ya registra.
Precondición:
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Capataz.
b. El actor tiene a su cargo (Agrónomo) o abarca (Capataz) al menos un invernadero activo.
Postcondición:
a. Se registró en la bitácora un evento de tipo «otro evento», con la fecha y la hora actuales, la descripción
   indicada y el actor como responsable. Está asociado al invernadero y, si se indicaron, al lote y al sector.
b. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del registro.
Reglas:
1. El invernadero se elige entre los activos a cargo del Agrónomo o abarcados por el Capataz. Si hay uno solo, viene
   elegido.
2. La descripción es obligatoria, de texto libre y de hasta 500 caracteres.
3. El lote es opcional y se elige entre los lotes activos del invernadero. El sector es opcional, uno solo, y se elige
   entre los sectores del invernadero que no estén inactivos. No se exige que el lote esté en ese sector. Un hecho que
   afecta a varios sectores se registra sin sector, asociado al invernadero.
4. La fecha y la hora son las del momento del registro (MD-77). No hay fechas retroactivas: si el hecho ocurrió antes,
   se aclara en la descripción.
5. Un registro de bitácora no se modifica ni se elimina. Si hay un error, se registra otro evento que lo aclare.
6. El registro no genera alertas ni notificaciones.
7. Este caso de uso no registra mermas, aplicaciones de insumos, salidas de servicio ni reubicaciones: cada una tiene
   su propio caso de uso. Las siembras, las transiciones y las cosechas se registran solas al concretar la orden.

---

## PROD-CNS-BIT · Consultar Bitácora

Actores: Agrónomo y Gerente.
Tipo: secundario, esencial.
Versión: 0.2
Objetivo: consultar los registros de la bitácora de un invernadero, buscar los que interesan y ver toda su
   información.
Precondición:
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.
b. El actor tiene acceso a al menos un invernadero: el Agrónomo, a uno a su cargo, y el Gerente, a cualquiera
   registrado.
Postcondición:
No se producen cambios en el Sistema.
Reglas:
1. Se consulta la bitácora de un invernadero por vez. El Agrónomo elige entre los invernaderos a su cargo; el Gerente,
   entre todos. Si el actor tiene uno solo, viene elegido.
2. También se pueden consultar los invernaderos dados de baja: la baja es lógica y conserva el historial.
3. Los registros se muestran del más reciente al más antiguo, agrupados por día, de a 50 por página.
4. Cada registro muestra la fecha y la hora, el tipo, el lote, la partida de cámara y los sectores si los tiene, la
   descripción y quién lo registró. Si lo generó el Sistema, lo indica como «InfoPonia».
5. Los tipos de evento son siembra, transición, cosecha, merma, reubicación, aplicación de insumos, fuera de servicio,
   otro evento e incumplimiento de cláusula suministrante.
6. Se puede filtrar por texto en la descripción, tipo de evento, lote, sector y rango de fechas. Los filtros se
   combinan. El filtro por sector encuentra los registros con ese sector entre los suyos, que pueden ser varios en una
   aplicación de insumos (MD-28).
7. Toda la información de un registro se ve en el propio listado: no hay pantalla de detalle aparte.
8. Si el invernadero no tiene registros, o ninguno coincide con los filtros, el Sistema lo informa y permite quitar
   los filtros.
9. La consulta no genera log de auditoría (SEG-14).

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45, D-50, D-51)

### Qué hace cada parte

| Parte | Código |
|---|---|
| Registrar evento | `produccion/servicios/bitacora.py`: `datos_de_evento`, `registrar_evento(actor, datos)` |
| Consultar bitácora | `produccion/servicios/bitacora.py`: `invernaderos_de_bitacora(actor)`, `consultar_bitacora(actor, invernadero_id, filtros, pagina)` |

### PROD-REG-EVT · decisiones de aplicación

- Un `Bitacora` de tipo `otro_evento` (sin hijo), con `descripcion_evento` **obligatoria** (hasta 500 caracteres), fecha y hora **actuales**, `responsable` = el actor, invernadero, lote opcional (entre los **activos** del invernadero) y sector opcional (**uno**, de los no inactivos; puede ser un sector fuera de servicio; no se exige que el lote esté en él).
- Un hecho que afecta a varios sectores se registra sin sector. El invernadero viene elegido si hay uno solo (regla 1).
- Sin alertas ni notificaciones. Un registro de bitácora **no se modifica ni se elimina** (no hay servicio que lo haga; la prueba de invariantes verifica que no existan vistas de edición).
- **Auditoría**: un registro `registro_evento` con la bitácora. Bloqueos: cuentas → invernadero (`bloquear_invernadero_activo`) → fila del lote si se eligió.
- Pruebas: `produccion/tests/test_prod_reg_evt.py` (una por regla 1 a 7 y por postcondición a y b; descripción vacía y de 501 caracteres; invernadero inactivo; lote finalizado; sector inactivo; Capataz fuera de su invernadero).

### PROD-CNS-BIT · decisiones de aplicación

- **Quién**: el Agrónomo (invernaderos a su cargo) y el Gerente (todos, **también los dados de baja**). El Capataz no consulta la bitácora (el CU no lo incluye).
- **Qué se lista**: las filas de `Bitacora` del invernadero con `tipo_evento` distinto del interno `consumo`. En la ronda hay siembra, transición, merma, aplicación de insumos, fuera de servicio, reubicación y otro evento; **cosecha e incumplimiento de cláusula suministrante** no existen todavía y no se ofrecen en el filtro de tipos (los suma su ronda). Un consumo de siembra se lista como un registro «siembra» por insumo (así lo pide PROD-CNC-SMB); los de una aplicación se muestran **dentro** de la aplicación (insumo y cantidad).
- **Orden y paginación**: del más reciente al más antiguo por `(fecha_bitacora, hora_bitacora, id)`, agrupados por día, de a 50. El agrupamiento por día se hace en la vista sobre la página.
- **Cada registro muestra**: fecha y hora, tipo, lote (`L-3`), sectores, `descripcion_evento` (por eso **todo servicio que escribe bitácora arma una descripción legible**, D-51 punto 8) y quién lo registró («InfoPonia» si `responsable` es nulo). Sin pantalla de detalle (regla 7).
- **Filtros combinables**: texto en la descripción (`icontains`), tipo, lote, sector (por `Bitacora.sectores`, que encuentra el registro si el sector es uno de los suyos) y rango de fechas. Sin resultados: mensaje y botón «Quitar filtros».
- Una consulta por página para todo lo mostrado (`select_related` / `prefetch_related`); sin consultas por fila. **No se audita** (SEG-14).
- Pantalla: pestaña «Bitácora» de la ficha del invernadero (`registrar_pestana_de_invernadero`, PRD-01) y, desde allí, los botones «Registrar evento» y «Registrar aplicación» (extensión 1a de PROD-REG-APL). Prototipo: `bitTab`, `VIEWS['bit-reg']`, `VIEWS.evento`.
- Pruebas: `produccion/tests/test_prod_cns_bit.py` (una por regla 1 a 9: Agrónomo ve solo sus invernaderos; Gerente ve todos y los dados de baja; orden, agrupación por día y 50 por página; el consumo interno no aparece; los de una aplicación se ven dentro; «InfoPonia»; cada filtro y su combinación; filtro por sector con una aplicación en varios; sin registros; que no genera auditoría; `assertNumQueries` constante con 1 y con 50 filas).
