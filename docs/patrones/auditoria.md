# Patrón · Cómo audita un servicio de un módulo de negocio

Resumen vigente de D-22 y D-36 para los módulos de negocio. Si algo de acá contradice una de esas decisiones, manda
la decisión: avisá.

## Dónde y cuándo

- El registro lo escribe el servicio del caso de uso, dentro de su `transaction.atomic()`, con
  `RegistroAuditoria.objects.registrar(usuario, accion, afectados, detalle)` (`core/models.py`). Así no queda una
  operación sin registro ni un registro de una operación que se deshizo (D-22).
- `usuario`: la cuenta que actuó, o `None` si la acción la hace el sistema (se guarda con el rol «infoponia», D-27).
- Las consultas no se auditan (SEG-14).

## El detalle (D-36)

- Dos claves opcionales y ninguna más:
  - `"cambios": {campo: {"antes": valor, "despues": valor}}` para todo dato que cambió. En un alta, «antes» es `None`.
    «Antes» igual a «despues» se rechaza.
  - `"datos": {clave: valor}` para el contexto que no tiene antes y después.
- Una referencia a otro objeto (invernadero, sector, insumo, lote...) va como `referencia(objeto)`, que guarda
  `{"id", "texto"}` con el texto de ese momento. El texto sale del `__str__` del modelo: definilo para que sirva al leer
  la auditoría.
- Valores permitidos: nulos, booleanos, `int`, `float`, textos, referencias y listas de esos
  (`_validar_valor`). Un `Decimal` o una fecha no son ninguno de ellos y lanzan `ValueError`: hay que convertirlos (por
  ejemplo, a texto) antes de registrarlos. Convenilo en el plan de la primera tarea que audite dinero, cantidades o
  fechas.
- Nunca una contraseña: un detalle con una clave que contenga «contrase» o «password» se rechaza.
- Cualquier otra forma lanza `ValueError` en la primera prueba del servicio.

## Los afectados

- Una lista de instancias de modelo. Cada una se guarda como `{"modelo", "id", "texto"}` (las cuentas suman `"rol"`).

## Lo que hay que tocar en `core` al auditar una acción nueva

Una tarea de negocio que audita por primera vez una acción tiene que declarar en «Permitido fuera de la app»:

1. `core/models.py`, `RegistroAuditoria.Accion`: la acción nueva. El campo `accion` tiene `choices`, así que también
   hace falta **una migración nueva en `core`** (solo cambia los `choices`).
2. `core/models.py`, `ACCIONES_DE_NEGOCIO`: la acción nueva. La prueba
   `test_d36_cada_accion_esta_clasificada_en_cuentas_o_en_negocio` falla si una acción no está clasificada, o si está en
   los dos conjuntos.
3. `core/models.py`, `RegistroAuditoria.ETIQUETAS` (nombre visible de cada campo y dato nuevo) y, si el valor tiene lista
   cerrada, `VALORES_VISIBLES`. Si no se agrega, la pantalla muestra la clave tal cual.

Con eso, el Gerente ve la acción en «Auditoría» sin tocar `visibles_para`.

## Lo que no está decidido (se resuelve en la primera tarea que audite)

- **Nombres de las acciones.** Las acciones de cuentas se llaman `alta`, `baja`, `modificacion`..., y están en
  `ACCIONES_DE_CUENTAS`: un módulo de negocio no puede reutilizarlas, porque el Gerente dejaría de ver sus registros
  según quién figure entre los afectados. Hay que elegir una forma (por ejemplo, `alta_invernadero`) y registrarla en
  una decisión.
- **Claves compartidas en `ETIQUETAS` y `VALORES_VISIBLES`.** Son diccionarios únicos para todo el sistema.
  `VALORES_VISIBLES["estado"]` hoy solo conoce «activo» e «inactivo»: un sector «fuera de servicio» se mostraría con su
  clave. Hay que decidir si se amplía la entrada común o se usan claves con prefijo.
- **Dependencia hacia `core`.** Que una app de negocio edite `core/models.py` no rompe D-23 (`core` sigue sin importar
  nada de negocio), pero hace que cada módulo nuevo genere migraciones en `core`. Si molesta, la alternativa es un
  punto de extensión (D-37, regla A4).
