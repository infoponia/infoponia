# CMP-02b · Cancelar pedido, reenviar invitación y lo que cancela solo

Estado: hecha en su rama (falta su PR) | App: compras | Rama: feature/cmp-02b-cancelar-reenviar-y-bajas | Ronda: Compras 1

Depende de: **CMP-02a**. No depende de la contabilidad.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Agrónomo puede **cancelar** un pedido y **reenviar** una invitación; el sistema **cancela solo** los pedidos de un Agrónomo que
se da de baja o deja el invernadero (MD-62); un pedido en curso **impide** deshabilitar el insumo o dar de baja el invernadero (H20), y la baja de
un proveedor **anula** sus enlaces.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-CNL-PED | Cancelar Pedido (manual y la función de las automáticas) | docs/casos_de_uso/compras/pedidos.md | Las automáticas de los pasos 60 y 62 las dispara CMP-03 |
| CMP-CNS-PED (regla 7) | Reenviar invitación | docs/casos_de_uso/compras/pedidos.md | — |
| CMP-BAJ-PRV (regla 3) | Anular los enlaces del proveedor dado de baja | docs/casos_de_uso/compras/proveedores.md | Completa CMP-01 |
| (MD-62, H17) | Cancelación por baja o traspaso del Agrónomo | docs/casos_de_uso/compras/pedidos.md («Cómo se aplica», CMP-CNL-PED) | — |
| (H20) | Impedimento «pedido en curso» | docs/casos_de_uso/compras/pedidos.md («Impedimentos») | — |

## Leer

- Casos de uso: `pedidos.md` (CMP-CNL-PED, la regla 7 de CMP-CNS-PED y su «Cómo se aplica»), `proveedores.md` (CMP-BAJ-PRV).
- Modelo: docs/modelo/compras.md (`Pedido`: `causa_cancelacion`; `EnlaceProveedor`).
- Decisiones: D-87 (puntos 3 y 5), D-88, D-43 (baja de cuenta), D-60 (traspaso, como ejemplo), D-36, D-42, D-44.
- API: docs/api/extensiones_de_maestros.md (traspaso y baja de cuenta), docs/api/extensiones_de_inventario.md
  (`registrar_impedimento_de_deshabilitacion`), docs/api/notificaciones.md.
- Patrones: docs/patrones/enlace_del_proveedor.md, docs/patrones/bloqueos.md («Invernadero» y el contrato de los puntos de extensión).
- Pantallas: `VIEWS.c_pedcnl`, `VIEWS.c_ped` («Reenviar invitación»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CMP-02a; `maestros/extensiones.py` (`registrar_traspaso`, `contar_traspaso`, `traspasar`), `core/extensiones.py`
  (`registrar_efecto_de_baja_de_cuenta` y `registrar_asignaciones_de_cuenta`, para que la ventana de baja diga cuántos pedidos se cancelan), `inventario/extensiones.py`; un registrante existente como modelo (`produccion/apps.py`).

## Límites

- Crea modelos: ninguno (los campos `causa_cancelacion`, etc., ya los creó CMP-02a; si faltara alguno, migración `0003`).
- Migraciones: una de `core` con `cancelacion_pedido` y `reenvio_invitacion`.
- Permitido fuera de la app: `core/models.py` (acciones) y su migración; al cerrar, los archivos de M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: los pasos diarios (CMP-03) y el impedimento de órdenes (CMP-03).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Cancelar** (`_cancelar`, la manual y `cancelar_pedido_automaticamente`). — pruebas: `test_cmp_cnl_ped.py`.
2. **Reenviar invitación.** — pruebas: `test_cmp_cns_ped.py` (amplía).
3. **Registrantes:** baja de cuenta y traspaso del Agrónomo; impedimento `pedido_en_curso`; la baja del proveedor anula sus enlaces. — pruebas:
   `test_registrantes_de_pedidos.py` (las tres pruebas mínimas de cada registrante: con datos, sin datos, sin consultas por fila) y
   `test_cmp_baj_prv.py` (amplía).
4. **Concurrencia:** cancelar contra cotizar; baja del proveedor contra cotizar. — pruebas: `test_pedidos_concurrencia.py` (amplía).
5. **Pantallas:** cancelar con resumen; «Reenviar» en la ficha.

## Hecho cuando

- Un pedido cancelado (a mano o solo) descarta sus cotizaciones, anula los enlaces y avisa a los invitados; el traspaso y la baja del Agrónomo lo
  cancelan y la ventana de confirmación dice cuántos pedidos se cancelarán.
- Deshabilitar un insumo con un pedido en curso se rechaza con un enlace al pedido.
- Pruebas verdes, sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras inventario maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano (`docs/patrones/verificacion_a_mano.md`)

Los pasos del final **los hace el estudiante** y los tacha en `docs/revisiones_pendientes.md` (M5; D-96: sin navegador automatizado ni cargadores: los datos se crean en los pasos). Los tres pasos de la tarea original están en los pasos 2, 3 y 12 de abajo.

### Verifiqué

- **Recorrido con el cliente de Django** (`compras/tests/test_recorrido_cancelar_y_reenviar.py`, `RecorridoDeCancelarYReenviarTests`, 12 pasos, en verde): la Agrónoma hace un pedido (P1) y reenvía la invitación a un proveedor (ventana, correo con el enlace nuevo, auditoría); el enlace viejo da «reemplazado» y el nuevo abre el portal; el otro proveedor cotiza y deja de ofrecerse «Reenviar» (por pantalla y por dirección escrita a mano); el Gerente ve la ficha sin acciones y recibe 403 en cancelar y reenviar, igual que otra Agrónoma y el Capataz; «Cancelar pedido» (formulario, error de motivo, resumen, «Volver a corregir», confirmar) descarta la cotización, anula el enlace vigente y avisa por correo a los dos invitados sin el motivo; después ningún enlace sirve («El pedido fue cancelado.»), no se cancela dos veces ni se reenvía; el Gerente cambia a la Agrónoma de un invernadero (la ventana avisa «Se cancela 1 pedido de cotización en curso…», no dice que el entrante «recibe» pedidos, no guarda hasta confirmar) y se cancela solo el pedido con destino a ese invernadero, con aviso a la Agrónoma de Norte 2 y a la nueva y no al Gerente; la ventana de baja de la cuenta dice «Es 1: se cancelan solos…» y al confirmar se cancela el otro pedido, que queda en el registro de la baja; un pedido en curso impide deshabilitar el insumo y dar de baja el invernadero (con «Ver detalle» al pedido) y, cancelado el pedido, se puede; la baja de un proveedor anula su enlace de un pedido en cotización y deja el del otro proveedor sirviendo; ningún token ni resumen en la auditoría.
- **Migraciones:** `makemigrations --check --dry-run`: sin cambios. `sqlmigrate core 0031`: **no-op** (solo cambian los `choices` de la acción: ninguna sentencia `DROP`, `DELETE`, `UPDATE` ni `ALTER`). `compras` no tiene migración nueva (los campos `causa_cancelacion`, etc. ya los creó CMP-02a). La 0031 se aplicó al crear la base de pruebas.
- **Comandos de «Hecho cuando»:** ver «Pruebas» en el «Cierre».
- **Sin dependencias nuevas.** `compras` no importa de `comercial` ni de `produccion`.

### Lo cubre una prueba

| Qué | Prueba |
|---|---|
| CMP-CNL-PED manual: quién cancela, cuándo (antes y después de la fecha límite), motivo (obligatorio, 500, recortado), postcondiciones a a e, correo sin motivo ni otros proveedores ni precios, 7a, rollback, stock/tránsito/alertas intactos | `test_cmp_cnl_ped.py` (`PrecondicionesYReglasDeQuienYCuandoTests`, `MotivoTests`, `PostcondicionesTests`) |
| Resumen de la cancelación (paso 4) | `test_cmp_cnl_ped.py` (`ResumenDeLaCancelacionTests`) |
| Las cuatro cancelaciones automáticas: texto fijo, auditoría como InfoPonia, H21 y «nunca a quien hizo la acción», `None` si ya no estaba en cotización | `test_cmp_cnl_ped.py` (`CancelacionesAutomaticasTests`) |
| Reenviar invitación: enlace nuevo, correo, falla del correo, auditoría, quién, estados, fecha límite, invitación sin enlace vigente, atomicidad, y las banderas `puede_cancelar` y `puede_reenviar` | `test_cmp_cns_ped.py` (`ReenviarInvitacionTests`, `AccionesDeLaFichaTests`) |
| Registrantes: baja de cuenta, asignaciones, traspaso (`contar`, aviso, `traspasar`), impedimento `pedido_en_curso`, con datos / sin datos / sin consultas por fila, y su integración con `baja_usuario`, `modificar_invernadero`, `deshabilitar_insumo` y `baja_invernadero` | `test_registrantes_de_pedidos.py` (22) |
| La baja del proveedor anula sus enlaces (no los usados, no los de otros pedidos ni proveedores), auditoría sin token y atomicidad | `test_cmp_baj_prv.py` (`CmpBajPrvEnlacesTests`, 9) |
| Punto `registrar_aviso_de_traspaso`, `Impedimento.url`, la ventana de personal y la de baja del invernadero | `maestros/tests/test_aviso_de_traspaso_y_url_de_impedimento.py` (12) |
| «Deshabilitar» y baja del insumo muestran el enlace del impedimento | `inventario/tests/test_existencias_vistas.py` y `test_inventario_catalogo_vistas.py` (3) |
| Concurrencia (`@tag("concurrencia")`): cancelar contra cotizar (los dos órdenes), dos cancelaciones, baja del proveedor contra cotizar (los dos órdenes), reenviar contra cotizar (los dos órdenes) | `test_pedidos_concurrencia.py` (`CancelarReenviarYDarDeBajaConcurrenciaTests`, 7) |
| Pantallas: ficha con y sin acciones, formulario, error de motivo, resumen, «Volver a corregir», confirmar, 6a, 403 y 404; ventana de reenviar (HTMX y sin JavaScript), correo que falla, a quien ya cotizó, fecha vencida | `test_pedidos_vistas.py` (`CancelarYReenviarVistaTests`, 17) |

### No pude verificar

- **Envío real de correo** (SMTP): las pruebas usan el correo simulado; los pasos 2, 7 y 13 los ves en la terminal con `CORREO_CONSOLA=1`.
- **Navegador real:** el cliente de Django no ve el CSRF ni el `Origin`, ni el JavaScript de las ventanas (HTMX) ni el aspecto: ver el paso 21. Las pantallas «Cancelar pedido» y su resumen, la ventana «Reenviar invitación» y el aviso de «cuántos pedidos se cancelan» nunca se miraron en un navegador.
- **Despliegue:** que Render aplique `core 0031` (es un no-op).
- **Concurrencia con carga:** se probó con dos hilos.
- **Criterio de producto:** si los textos de la cancelación, del aviso del traspaso («Se cancelan N pedidos de cotización en curso de …») y de «Ver detalle» son los que se quieren.

### Pasos (los hace el estudiante y los tacha en `docs/revisiones_pendientes.md`, M5)

**Antes de empezar.** En PowerShell, con el entorno virtual activo: `python manage.py migrate` (aplica `core 0031`, que no cambia ninguna tabla) y `python manage.py runserver`; abrí <http://127.0.0.1:8000/>. Para ver los correos sin enviarlos de verdad, la base local tiene que tener el correo en modo consola (`CORREO_CONSOLA=1` en tu `.env`, y reiniciá `runserver`): cada correo se imprime en la terminal y de ahí copiás el enlace (`/proveedor/…`). **No escribas ninguna contraseña en un archivo del repo.**

Datos que hay que crear a mano, **en este orden** (como Gerente, salvo que se diga otra cosa):
1. *Usuarios y seguridad → Nueva cuenta*: tres **Agrónomos**: Ana (`ana@ejemplo.com`), Nuevo (`nuevo@ejemplo.com`) y Otra (`otra@ejemplo.com`), todos con «contraseña temporal» (anotalas fuera del repo), y un **Capataz** (`capataz@ejemplo.com`).
2. *Producción → Invernaderos → Nuevo*: «Invernadero Norte» y «Invernadero Norte 2» (urbanos, calle «Calle 122», número «3310», cualquier localidad), los dos con **Ana** de Agrónoma; y «Invernadero Este» (igual) con **Otra**.
3. *Inventario*: crear en el catálogo «Lechuga» (unidad) y «Nutriente» (kg) (como Ana) y «Tomate» y «Pepino» (kg) (como Otra). Después, *Habilitar insumo*: Lechuga en Norte (mínimo 20, precio 12,50), Nutriente en Norte 2 (mínimo 5, precio 100,00), y Tomate y Pepino en Este (mínimo 5, precios 30,00 y 25,00).
4. *Compras → Proveedores → Nuevo proveedor*: «Semillas del Sur S. A.» (jurídica, CUIT `30-00000013-9`, correo `ventas@ejemplo.com`) y «Viveros del Este S. R. L.» (jurídica, CUIT `30-00000026-0`, correo `info@ejemplo.com`).

**Reenviar y cancelar (como Agrónoma Ana)**
1. *Compras → Pedidos → Nuevo pedido*: Lechuga 20 (Norte), los dos proveedores, fecha límite dentro de 3 días; **Revisar pedido** y **Confirmar pedido**. Es el pedido P1. En la terminal, dos correos; copiá el enlace de «Semillas del Sur» (**enlace A**) y el de «Viveros del Este» (**enlace C**). En la ficha del pedido, arriba a la derecha, aparece **Cancelar pedido** y, en la tabla «Proveedores invitados», **Reenviar invitación** en las dos filas. *(Lo cubre el recorrido.)*
2. En la fila de «Semillas del Sur», tocá **Reenviar invitación**: se abre una ventana «Reenviar invitación a Semillas del Sur S. A.» que dice que se le envía a `ventas@ejemplo.com` y que «El enlace anterior deja de servir». **Volver** la cierra sin cambiar nada. Volvé a abrirla y tocá **Reenviar invitación**: aviso «Enviamos la invitación nueva a Semillas del Sur S. A. El enlace anterior ya no sirve.»; en la terminal, **un** correo nuevo a `ventas@ejemplo.com` con otro enlace (**enlace B**); la fila sigue «No cotizó» con el enlace «Vigente».
3. **Proveedor** (ventana privada, sin iniciar sesión): abrí el enlace A: «Este enlace no se puede usar · Este enlace fue reemplazado por uno más nuevo.», sin ningún dato del pedido. Abrí el enlace B: se abre el portal (la dirección pasa a `/proveedor/enlace/`).
4. Con el enlace C (Viveros), también en la ventana privada: cargá Lechuga, cantidad 20, precio total 250, plazo 3 y enviá la cotización («Recibimos su cotización…»). De vuelta como Ana, en la ficha de P1: «Viveros del Este» figura «Cotizó» con el enlace «Usado» y **ya no tiene** el botón «Reenviar invitación»; «Semillas del Sur» sí lo conserva. *(Lo cubre el recorrido.)*
5. Tocá **Cancelar pedido**. Pantalla «Cancelar el pedido P-…»: sección 1 «Qué se cancela» con el destino «Invernadero Norte», «Cotizaciones recibidas: 1», el monto estimado $ 250,00 y las advertencias («Los proveedores que todavía no cotizaron ya no podrán hacerlo…», «La cancelación no se puede deshacer»). Sin escribir nada, tocá **Revisar cancelación**: el error «Contá por qué se cancela el pedido.» sale junto al campo del motivo.
6. Escribí el motivo «Ya no hace falta.» y **Revisar cancelación**: «Confirmá la cancelación del pedido P-…» con el motivo, «Cotizaciones que se descartan: 1», «Enlaces que se anulan: 1», a quién se avisa (los dos proveedores con su correo) y la lista de cotizaciones con su monto. **Volver a corregir** te devuelve al formulario con el motivo ya escrito y sin cancelar nada.
7. Volvé al resumen y tocá **Confirmar cancelación**. En la ficha: aviso «Pedido P-… cancelado. Se avisó por correo a los proveedores invitados.», el estado «Cancelado», «Motivo de la cancelación: Ya no hace falta.», «Cancelado el … · Cancelado por el Agrónomo», sin botones de acción; la cotización de «Viveros» figura «Descartada» y el enlace de «Semillas» «Anulado». En la terminal, **dos** correos «Pedido de cotización P-… cancelado» (uno a cada proveedor) que dicen que el pedido se canceló y **no** traen el motivo, ni el nombre del otro proveedor, ni precios.
8. **Proveedor** (ventana privada): los enlaces B y C dicen «Este enlace no se puede usar · El pedido fue cancelado.».
9. Probá a mano la dirección `/compras/pedidos/<número de P1>/cancelar/`: te lleva de vuelta a la ficha con el aviso «El pedido P-… ya no está en cotización: cancelado. No se puede cancelar.». *(Lo cubre el recorrido.)*

**Gerente y los demás roles**
10. Como Gerente: *Compras → Pedidos → P1*: sin «Cancelar pedido» ni «Reenviar invitación»; la dirección `/compras/pedidos/<número>/cancelar/` escrita a mano da 403. En *Auditoría* aparecen «Reenvío de invitación a un proveedor» (de Ana, con «Enlace anterior (reemplazado)…» y «Enlace nuevo…») y «Cancelación de pedido de cotización» (de Ana: estado, fecha de cierre, motivo, causa «Cancelado por el Agrónomo», cotización descartada y enlace anulado); ninguna muestra un token. *(Lo cubre el recorrido.)*
11. Con **Otra** (o el **Capataz**) abrí `/compras/pedidos/<número de P1>/cancelar/`: 403. *(Lo cubre el recorrido.)*

**Lo que se cancela solo (MD-62)**
12. Como Ana: hacé el pedido **P2** (Lechuga 20 en Norte y Nutriente 3 en Norte 2) y el **P3** (Nutriente 3 en Norte 2), los dos con los dos proveedores. (Con P2 aparece la advertencia «Ya figura en…» si hubiera otro pedido en cotización con la Lechuga: se puede seguir.) Como Gerente: *Producción → Invernaderos → Invernadero Norte → Modificar*, cambiá el **Agrónomo a «Nuevo»** y **Guardar**: la ventana «Confirmá el cambio de personal» dice, además de quién entra y quién sale, «**Se cancela 1 pedido de cotización en curso de Ana … con destino a este invernadero. Se avisa por correo a los proveedores invitados.**» (solo P2: P3 no va a Norte) y **no** dice que «Nuevo» recibe pedidos. **Volver al formulario**: no se guardó nada (P2 sigue «En cotización»). Repetí y tocá **Confirmar y guardar**.
13. P2 figura «Cancelado» con «Cancelación automática» y el motivo «Agrónomo sin el invernadero de destino»; P3 sigue «En cotización» (solo iba a Norte 2, que Ana conserva). En la terminal, los correos de P2 a los dos proveedores. En la campana de **Ana** y de **Nuevo** hay un aviso «Pedido P-… cancelado» (el de Ana, por su destino Norte 2; el de Nuevo, por Norte); el **Gerente no** recibe ninguno porque fue quien hizo el cambio. En *Auditoría*: «Modificación de invernadero» incluye a P2 entre los afectados y hay una «Cancelación de pedido de cotización» de **InfoPonia**.
14. Como Gerente: *Usuarios y seguridad → Ana → Dar de baja*: la ventana lista «**Pedidos de cotización en curso.** Es 1: se cancelan solos al confirmar la baja y se avisa por correo a los proveedores invitados.». Confirmá la baja. P3 figura «Cancelado» con el motivo «Agrónomo inactivo»; el Gerente no recibe aviso; en *Auditoría*, la «Baja de cuenta» de Ana lista «Pedidos cancelados: P-…».

**Un pedido en curso impide deshabilitar**
15. Como **Otra**: hacé el pedido **P4** (Tomate 10, Este) y el **P5** (Pepino 10, Este) con los dos proveedores; copiá de la terminal el enlace de «Semillas del Sur» de P5 (**enlace D**) y el de «Viveros» (**enlace E**). *Inventario → Existencias*: en el Tomate tocá **Deshabilitar**: «No se puede deshabilitar Tomate en Invernadero Este» con «Está en el pedido P-…, en cotización hasta el dd/mm. Esperá a que se cierre o que el Agrónomo que lo hizo lo cancele.» y un enlace **Ver detalle** que abre la ficha de P4; no ofrece confirmar. En el catálogo, **Dar de baja** al Tomate da el mismo impedimento («Invernadero Este: …»).
16. Como Gerente: *Producción → Invernaderos → Invernadero Este → Dar de baja*: «No se puede dar de baja…» con **dos** impedimentos «Está en el pedido P-…» (P4 y P5), cada uno con su **Ver detalle**.
17. Como Otra: cancelá P4 (motivo «Cambió el plan»). Ahora **Deshabilitar** el Tomate funciona («Tomate quedó deshabilitado…»); el Pepino sigue sin poder (P5 en curso). *(Lo cubre el recorrido.)*

**Baja de un proveedor**
18. Como Gerente: *Compras → Proveedores → Semillas del Sur S. A. → Dar de baja*: la ventana dice «…sus enlaces vigentes de pedidos en cotización dejan de servir…». Confirmá. P5 sigue «En cotización». **Proveedor** (ventana privada): el enlace D dice «Este enlace no se puede usar · Este enlace fue anulado.»; el enlace E (Viveros) sigue abriendo el portal. En *Auditoría*, la «Baja de proveedor» lista «Enlaces anulados».

**Navegador real, sin JavaScript y celular**
19. **Navegador real (D-96).** En una ventana privada, ya con sesión iniciada como Ana, **enviá hasta el final** los formularios de esta tarea: **Confirmar cancelación**, **Reenviar invitación** (ventana) y, como Gerente, **Confirmar y guardar** del cambio de personal y **Dar de baja** de la cuenta. Tienen que mostrar el resultado esperado. Si aparece una página «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Fijate también que **Reenviar invitación** y **Cancelar pedido** abran sin recargar toda la página (HTMX) y que el foco quede en el botón de la ventana.
20. (Opcional) **Sin JavaScript** (desactivalo en el navegador): el enlace «Reenviar invitación» lleva a la ficha del pedido con la ventana abierta y funciona; «Cancelar pedido» y su resumen funcionan igual.
21. (Opcional) En un ancho de celular (390 px): la ficha del pedido (con el botón «Cancelar pedido» y las acciones de la tabla), «Cancelar pedido», su resumen y la ventana de reenvío no se cortan por la derecha.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo.** Los casos de uso CMP-CNL-PED, la regla 7 de CMP-CNS-PED (reenviar), la regla 3 de CMP-BAJ-PRV y los dos disparadores MD-62/H17 y H20, en cinco pasos, con las pruebas de los servicios escritas primero y mostradas fallando antes de implementar (el estudiante las revisó en cada paso).

- **`core/models.py`:** las acciones `cancelacion_pedido` y `reenvio_invitacion` (de negocio), sus `ETIQUETAS` y `VALORES_VISIBLES` (la causa); migración `core/migrations/0031_acciones_de_cancelacion_y_reenvio.py` (solo `choices`).
- **`compras/servicios/pedidos.py`:** `cancelar_pedido`, `resumir_cancelacion`, `cancelar_pedido_automaticamente`, la función interna compartida `_cancelar` y `reenviar_invitacion`; `ficha_de_pedido` suma `puede_cancelar` y `puede_reenviar` por invitado. **`servicios/enlaces.py`:** `anular_enlaces_de_pedido`, `anular_enlaces_de_proveedor`, `reemplazar_enlace` y `enviar_aviso_de_cancelacion` (plantilla `correo/cancelacion.txt`). **`servicios/registrantes.py`** (nuevo) y su registro en `compras/apps.py`. **`servicios/proveedores.py`:** `baja_proveedor` anula los enlaces. **`models.py`:** `MOTIVOS_DE_CANCELACION_AUTOMATICA` (los literales de la regla 3 de CMP-CNL-PED).
- **Pantallas:** «Cancelar pedido» (formulario, resumen y confirmación; `cancelar.html`, `cancelar_resumen.html`), la ventana «Reenviar invitación» (`_ventana_reenviar.html`, con HTMX y con respaldo sin JavaScript), y los botones en la ficha del pedido.
- **Fuera de la app, con tu permiso** (los dos puntos que la tarea no listaba en «Permitido fuera de la app»): `maestros/extensiones.py` (`registrar_aviso_de_traspaso` y `Impedimento.url`), `maestros/servicios/invernaderos.py` (`_aviso_de_personal` suma `avisos`), las plantillas `_ventana_personal.html` y `_ventana_baja.html` de maestros, y en inventario `views_existencias.py`, `servicios/insumos.py` (`ImpedimentoDeBaja.url`) y las ventanas `_ventana_deshabilitar.html` y `catalogo/_ventana_baja.html`.
- **Verificación:** `compras/tests/test_recorrido_cancelar_y_reenviar.py` y la «Verificación a mano» de arriba.

**Pruebas** (resultado del cierre): `python manage.py test compras inventario maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **3564 en verde**; `python manage.py test compras --keepdb --tag concurrencia`: **14 en verde** (7 son de esta tarea); `makemigrations --check --dry-run`: sin cambios. Son de CMP-02b: cancelar 40, reenviar y banderas de la ficha 24, registrantes 22, baja del proveedor 9, maestros 12, inventario 3, pantallas 17, recorrido 1 y 7 de concurrencia. **No se borró ni se debilitó ninguna prueba existente.**

**Decisiones y desvíos** (propuestos para `docs/temas_abiertos.md`; los puntos 1 a 8 podrían ser la decisión D-98 que propongo en el PR):

1. **Un punto nuevo en `maestros`: `registrar_aviso_de_traspaso`** (autorizado por el estudiante, 23/11/2026). «La ventana dice cuántos pedidos se cancelarán» no se podía cumplir con `contar` (lo que **recibe** quien entra: solo se muestra con un Agrónomo entrante y llega a su notificación). `contar` de compras devuelve `[]`.
2. **`Impedimento.url`** (opcional, `None` por omisión; autorizado): el «con un enlace al pedido» de «Hecho cuando». El texto del enlace es «Ver detalle» y no «Ver pedido», porque CMP-03 lo usará para las órdenes.
3. **Las cancelaciones automáticas se auditan como InfoPonia** (`usuario=None`), aunque haya quien dio la baja o hizo el traspaso (decisión del estudiante). Esa persona figura en el registro de la baja o de `modificacion_invernadero`, que lista los pedidos entre los afectados.
4. **Solo se reenvía hasta la fecha límite** (decisión del estudiante): un enlace nuevo después nacería vencido (D-88 punto 2); la regla 7 y el prototipo no dicen nada de la fecha. Código `fecha_limite_vencida`.
5. **«En curso» de H20 = un pedido «en cotización»** (D-87 punto 5 y el caso de uso), no el texto de `docs/api/extensiones_de_inventario.md` («abierto o con cotizaciones, no cancelado, no vencido sin cotizaciones…»). La decisión manda; hay que corregir ese párrafo.
6. **7a:** CMP-CNL-PED dice «el Sistema reintenta el envío», pero D-88 punto 6 dice que no hay reintento automático: la cancelación permanece y no se reintenta.
7. **La cancelación manual no genera notificación de campana** (quien actúa es el único Agrónomo del pedido y los proveedores se enteran por correo). Las automáticas avisan según H21.
8. **El motivo de las automáticas son los literales de la regla 3** («nadie cotizó», «sin cotizaciones elegibles», «Agrónomo inactivo», «Agrónomo sin el invernadero de destino»), en `MOTIVOS_DE_CANCELACION_AUTOMATICA`, y no los rótulos de `Pedido.Causa` (decisión del estudiante).
9. **La ventana de baja de cuentas de `core` no muestra `Asignacion.cantidad`** (solo `texto` y `que_pasa`): para cumplir «dice cuántos pedidos se cancelarán» el número va también en el texto de compras («Es 1:» / «Son N:»). Es un hueco que ya tenía la ventana con las órdenes del Capataz de `produccion`; conviene que `core` muestre la cantidad (fuera de «Permitido fuera de la app»).
10. **El traspaso cancela aunque el Agrónomo saliente siga activo.** «Cuando exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido» (punto 1) dice «si el saliente sigue activo»; MD-62 y CMP-CNL-PED no condicionan nada. Se cancela siempre (`agronomo_sin_invernadero`).
11. **«Reenviar» sin enlace vigente** (por ejemplo, tras la baja y reactivación del proveedor) crea el enlace nuevo; el registro no menciona un enlace anterior.
12. **El resumen del prototipo:** el prototipo no tiene resumen antes de confirmar; el caso de uso lo pide (paso 4) y se agregó.
13. **`TypeError: cannot pickle 'traceback' object`** con `--keepdb --parallel`: apareció una vez, al correr los cuatro módulos justo después de agregar la migración `core 0031`, porque los clones de la base de pruebas no la tenían (`.claude/rules/pruebas.md`); recreando la base una vez con `--noinput` desapareció. Es la misma causa que el «intermitente» anotado en IOT-05.
14. **Datos borrados (regla del estudiante para la base local):** la base de pruebas `test_infoponia_cmp` y sus clones se recrearon una vez con `--noinput` (la migración `core 0031` no llega a los clones de `--keepdb`) y el cierre de cada corrida descartó sus datos. **No se tocó la base local de desarrollo, ni el usuario administrador, ni se escribió ninguna contraseña.**

### Pantallas: lo que se corrigió del prototipo

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| `VIEWS.c_pedcnl` (se conservan) | «Las cotizaciones recibidas se conservan como consulta» | Dice «se descartan» (quedan en la ficha como «Descartada») | Postcondición b de CMP-CNL-PED |
| `VIEWS.c_pedcnl` (confirmar) | Cancelaba directo | Formulario → resumen (cotizaciones, enlaces, a quién se avisa) → confirmar, con «Volver a corregir» | Pasos 2 a 5 y extensión *a de CMP-CNL-PED |
| `VIEWS.c_pedcnl` (motivo) | Un campo que se validaba al enviar | Error junto al campo, hasta 500 caracteres y el motivo se conserva al corregir | Extensión 3a y regla «Motivo»; `interfaz.md` |
| `VIEWS.c_pedcnl` (aviso) | No decía que se avisa a los proveedores | Dice que se avisa por correo a todos los invitados, sin el motivo | Postcondición d y regla «Aviso a los proveedores» |
| `VIEWS.c_ped` / `MODALS.reenviar` (cuándo se ofrece) | «Reenviar» con el enlace «vigente», «vencido» o «fallido» | Solo con el pedido en cotización, el proveedor activo y sin cotizar, hasta la fecha límite; y solo al Agrónomo del pedido | Regla 7 de CMP-CNS-PED; D-88 punto 2; D-30 |
| `MODALS.reenviar` (correo que falla) | Un aviso emergente «pídale al Gerente que corrija el correo» | Aviso con el texto de D-88 punto 6 y «No se pudo enviar» en la ficha; sin notificación de campana | Regla 7; D-88 punto 6; H21 |
| `VIEWS.c_ped` (botones) | «Cancelar pedido» visible para el Gerente | Solo para el Agrónomo del pedido con el pedido en cotización; el Gerente ve «modo consulta» | Regla 1 de CMP-CNS-PED y «Quién cancela»; D-30 |
| Ventana de cambio de personal de PROD-MOD-INV | No avisaba de los pedidos | Una línea «Se cancela N pedidos…» por cambio, con o sin persona entrante | Regla 2 de PROD-MOD-INV y «Hecho cuando» de CMP-02b |
| Ventanas «Deshabilitar», baja del insumo y baja del invernadero | Texto sin enlace | «Ver detalle» al pedido en curso | «Hecho cuando» de CMP-02b (H20) |
| Estados vacíos y de celular | No estaban | Se agregaron (sin cotizaciones, ficha cancelada, tabla de invitados) | D-61 punto 2 |
