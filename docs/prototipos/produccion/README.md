# Prototipo · Datos maestros y producción

Archivo: `datos_maestros_y_produccion.html` (en esta carpeta). Es la guía visual de las apps `maestros`,
`inventario` y `produccion` (D-24): manda el caso de uso, y si la lógica del prototipo difiere, se avisa (regla L7).

Es un solo archivo de 1.768 líneas. Cada pantalla es una función de JavaScript: buscala con Grep por el nombre de
abajo y leé solo esa parte. El CSS (líneas 9 a 561 aproximadamente) no se lee entero: buscá solo las clases que
necesites. No leas el archivo entero (regla L6).

> **Estilo (D-47).** Este prototipo es el estilo del sistema («Diseño v2»: solo Inter con cifras tabulares, bordes de 10 px,
> tarjetas por bloques). La tarea UI-01 pasa sus variables y su marco al sistema. Una sola salvedad: sus filtros usan el
> `<select>` nativo, que D-24 descartó; se usa el desplegable propio con este aspecto. Qué pantalla va en qué tarea:
> `docs/tareas/ronda_produccion_1.md`, sección 4.

## Pantallas

| Pantalla | Funciones |
|---|---|
| Marco, campana (alertas y notificaciones) | `shell`, `alertas`, `myNotif` |
| Inicio del Agrónomo y del Gerente | `VIEWS.inicio`, `personalCard` |
| Producción y órdenes | `VIEWS.prod`, `ordenesTab`, `MODALS['nueva-orden']`, `MODALS.orden` |
| Invernaderos: lista, ficha, alta y modificación, baja | `invCard`, `VIEWS.inv`, `VIEWS['inv-form']`, `invErrs`, `MODALS['inv-baja']`, `camaraTab` |
| Sectores | `sectoresTab`, `sectorCard`, `MODALS['sector-form']`, `MODALS['sector-baja']`, `MODALS['sector-activar']`, `ultimoAviso` |
| Sacar un sector de servicio | `VIEWS.fs`, `fsCalc` |
| Lotes y bitácora | `lotesTab`, `bitTab`, `VIEWS['bit-reg']`, `VIEWS.evento` |
| Configuración y organización | `VIEWS.config`, `CFG`, `cuitOk`, `aplicarMarca` |
| Cultivos y variedades | `cultivosTab`, `MODALS.cultivo`, `VIEWS['var-form']`, `varCalc`, `MODALS['var-baja']`, `MODALS['var-umbral']` |
| Inventario: existencias, catálogo, categorías, habilitar | `VIEWS.insumos`, `existTab`, `catalogoTab`, `tiposTab`, `MODALS['insumo-form']`, `insLocks`, `MODALS['cat-form']`, `MODALS.habilitar`, `MODALS['ex-form']` |
| Ajustar stock | `VIEWS.ajuste`, `ajCalc` |
| Aplicación de insumos | `VIEWS.aplic`, `apCalc`, `reparto`, `fefo` |
| Planificar siembra | `VIEWS.siembra`, `smbCalc`, `bloqueos`, `incompat`, `ritmo`, `ritmoPanel`, `reqPanel` |
| Planificar transición | `VIEWS.transicion`, `trCalc` |
| Capataz en el celular: bandeja, concretar siembra, concretar transición | `VIEWS.bandeja`, `VIEWS['c-siembra']`, `csCalc`, `VIEWS['c-trans']`, `ctCalc`, `propTrans` |
| Registrar merma | `VIEWS.merma`, `mrCalc`, `mermaInfo`, `aplicarMerma` |
| Bajas que faltaban en la lista: cultivo, insumo del catálogo, insumo en un invernadero | `MODALS['cult-baja']`, `MODALS['ins-baja']`, `MODALS['ex-baja']` |
| Cálculos comunes que usan varias pantallas | `ocup`, `comp`, `libre` (agujeros de un sector), `compatible`, `perfilSector`, `capEtapa`, `alertasInv` (personal por asignar), `alertasMerma`, `stock`, `reservado`, `libreAl` |

Todos los nombres de esta tabla se verificaron contra el archivo el 18/11/2026.

**Archivo aparte (21/11/2026):** `logistica_transportista.html` es la guía visual de MAE-05 (D-55): el bloque «Logística» de la
ficha del invernadero, agregar y quitar transportista, el transportista sin invernadero en «Personal por asignar», el invernadero en
la ficha de la cuenta y la baja de una cuenta en ruta. Es chico: se puede leer entero. Funciones: `logistica`, `ventanaAgregar`,
`ventanaQuitar`, `personalPorAsignar`, `fichaDeCuenta` y `bajaDeCuentaEnRuta`. El selector de pantallas es «solo prototipo».

La pantalla de concretar cosecha no está en este archivo: está en el prototipo comercial, `docs/prototipos/comercial/` (`VIEWS.capcsc`).

## Elementos del prototipo que no van en el sistema

Cada caso de uso de estas apps los repite en su lista «Solo prototipo», como `docs/casos_de_uso/usuarios.md`.

- El selector «Solo prototipo — ver como», para cambiar de rol.
- El pie con «Reiniciar datos de ejemplo» y «Prototipo de pantallas».
- La fecha fija HOY (12/11/2026) y la hora 10:00 que se repite en la bitácora.
- Los recuadros «Solo prototipo — resultado al confirmar» (`simBox`), que simulan un cambio simultáneo o el aviso de
  umbral.
- El aviso de que Georef está recortado.
- El botón «Editar hardware», que en el prototipo quita el sector.
- La ventana «Registrar sistema IoT».
- La nota del Dashboard en el inicio del Gerente.
- Las fuentes de Google (el sistema usa las del repo, D-26).
- Los nombres fijos en los textos de las notificaciones.
- Que `ACT['inv-save']` notifique también a la persona saliente y avise de los cambios de nombre: el caso de uso
  solo notifica a la persona asignada (postcondición c de PROD-MOD-INV), y manda el caso de uso (L7).
- Los datos de ejemplo (seed).
