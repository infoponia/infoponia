# USR-09a · Endurecimiento del despliegue

Estado: hecha, falta PR | App: core (y `config`) | Rama: feature/usr-09a-endurecimiento-del-despliegue | Ronda: —

Depende de: — (USR-09 figuraba «Depende de: —»)

Sale de partir USR-09 (`USR-09-seguridad-produccion.md`): USR-09a es lo de sus puntos 1, 2, 3 y 6. Los puntos 4 y 5 (topes de intentos y de pedidos de recuperación) quedan para USR-09b.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| SEG-16 | Transporte seguro (HTTPS, cookies seguras, HSTS) | docs/casos_de_uso/usuarios.md | — |
| SEG-18 | Pantallas propias (el admin de Django solo con `DEBUG`) | docs/casos_de_uso/usuarios.md | — |

## Leer

- Casos de uso: docs/casos_de_uso/usuarios.md — SEG-16 y SEG-18
- Decisiones: D-29 (`static_v`), D-30 (admin atado a `DEBUG`), D-88 (política de Referer: no se toca)
- Guía del nodo: docs/api/nodo/README.md, sección 7
- Reglas: .claude/rules/pruebas.md

## Límites

- Crea modelos: ninguno
- Migraciones: ninguna
- Permitido fuera de la app: `config/settings.py`, `config/seguridad.py` (nuevo), `.env.example`
- Dependencias nuevas: ninguna
- Fuera de alcance: topes de intentos y de recuperación (USR-09b), ingreso con Google, la variable con la dirección pública del sitio, cualquier cambio de estáticos

## Pasos

1. Pruebas de la función pura (`core/tests/test_seguridad_despliegue.py`); se mostró que fallaban y se revisaron.
2. `config/seguridad.py` (`debug_encendido`, `ajustes_https`) y `config/settings.py`.
3. Recorrido (`core/tests/test_recorrido_seguridad_despliegue.py`) y `.env.example`.
4. `check --deploy` y suite completa.

## Hecho cuando

- Con `DEBUG` apagado: redirección a https, cookies de sesión y CSRF `Secure`, HSTS de 86400 s sin subdominios ni preload. Con `DEBUG` encendido: nada de esto.
- `DEBUG` queda apagado si falta `DJANGO_DEBUG`.
- Comando de pruebas: `python manage.py test core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y la suite completa una vez.

## Cierre

**Qué se hizo**

- `config/seguridad.py` (nuevo): `debug_encendido(entorno)` (solo `DJANGO_DEBUG=1` enciende) y `ajustes_https(debug, corriendo_pruebas)`, funciones puras con el estilo de `config/correo.py`.
- `config/settings.py`: `DEBUG = debug_encendido(os.environ)` (antes, por defecto «1») y los cuatro ajustes (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`) tomados de `ajustes_https`. Con `manage.py test` (detectado con `sys.argv`, como `PASSWORD_HASHERS` y `CORREO_CONFIGURADO`) solo la redirección queda apagada, para que las pruebas con el cliente de Django por http no reciban un 301; el CI no cambia. Las pruebas existentes no se tocaron.
- `.env.example`: `DJANGO_DEBUG=1` con un comentario de que es solo para desarrollo.
- No se tocó: `SESSION_COOKIE_HTTPONLY` (ya es HttpOnly por defecto en Django; lo comprueban las pruebas), `CSRF_COOKIE_HTTPONLY` (queda en `False`; una búsqueda de `csrf` y `cookie` en los `.js` de las apps no encontró nada, pero no se documentó como comprobación completa —las plantillas podrían leerla en línea—, así que no se cambia), `SECURE_REFERRER_POLICY` (D-88), `SECURE_PROXY_SSL_HEADER` (ya existía), `SECURE_HSTS_INCLUDE_SUBDOMAINS` y `SECURE_HSTS_PRELOAD`, y los estáticos (`static_v` se mantiene).
- Punto 6 de USR-09 (correo de recuperación en segundo plano): descartado, no se programó.

**Qué cambia de comportamiento con `DEBUG` apagado por defecto** (`SECRET_KEY` por defecto, `ADMIN_DJANGO_HABILITADO`, `CORREO_CONSOLA`): quien no tenga `DJANGO_DEBUG=1` en su `.env` ya no tiene clave de desarrollo (Django no arranca, «SECRET_KEY must not be empty»), ni `/admin/`, ni correo por consola, y `runserver` redirige a https. Hay que agregar `DJANGO_DEBUG=1` al `.env` local (paso (a) abajo). En Render no cambia nada (ya tiene `DJANGO_DEBUG=0`); en el CI tampoco.

**Pruebas**

- `core.tests.test_seguridad_despliegue` (7) y `core.tests.test_recorrido_seguridad_despliegue` (2): OK, con `DJANGO_DEBUG=0` y con `DJANGO_DEBUG=1`.
- `python manage.py test core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: 770 pruebas, OK, con `DJANGO_DEBUG=0` y con `DJANGO_DEBUG=1`.
- Suite completa (`python manage.py test --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, `DJANGO_DEBUG=0`): 7577 pruebas, OK.
- `check --deploy` (`DJANGO_DEBUG=0`, clave falsa larga, `DJANGO_ALLOWED_HOSTS=infoponia.onrender.com`, sin `SILENCED_SYSTEM_CHECKS`): 2 advertencias, ambas decididas:
  - `security.W005`: falta `SECURE_HSTS_INCLUDE_SUBDOMAINS`. No se activa a propósito: con un día de HSTS y un dominio `onrender.com` compartido, no corresponde obligar a https a subdominios ajenos.
  - `security.W021`: falta `SECURE_HSTS_PRELOAD`. No se activa: la lista de precarga exige un año como mínimo y es difícil de revertir.
- Decisiones: D-99 (`docs/decisiones/D-99.md`; el número se toma al final, después de `git fetch`).

**Verifiqué**

- El recorrido (`RecorridoDeSeguridadDespliegueTests`): http recibe un 301 a `https://testserver/…` en una pantalla pública y en una privada; por https responde 200 con `Strict-Transport-Security: max-age=86400`; el inicio de sesión por https da una cookie `sessionid` con `secure` y `httponly`; con los valores de desarrollo, http responde 200 sin HSTS y con la cookie sin `secure`.
- `check --deploy` (arriba). No hay migraciones.
- Con la documentación de Render ([Web Services](https://render.com/docs/web-services), [TLS](https://render.com/docs/tls), [Health checks](https://render.com/docs/health-checks)): el balanceador termina el TLS, reenvía a la aplicación por HTTP y redirige él mismo http a https; una comprobación HTTP se da por buena con cualquier 2xx o 3xx en 5 s, así que un 301 no la hace fallar, y sin ruta de comprobación es una prueba TCP al puerto.

**Lo cubre una prueba**

- `DEBUG` apagado por defecto: `test_usr09a_debug_apagado_sin_variable`, `test_usr09a_debug_encendido_solo_con_uno`.
- Los valores exactos de los ajustes, la ausencia de subdominios y preload y que `settings.py` los aplica: `Seg16AjustesHttpsTests`.
- La redirección, el HSTS y las cookies `Secure` y `HttpOnly`: `test_recorrido_de_produccion_de_punta_a_punta`; el desarrollo por http: `test_recorrido_de_desarrollo_sigue_andando_por_http`.
- El admin atado a `DEBUG` (SEG-18): `Seg18AdminDjangoTests` (existente, sin cambios).

**No pude verificar**

- **Que Render manda `X-Forwarded-Proto: https`.** La documentación oficial no lo menciona (solo el foro). Si no llegara, Django vería todo pedido como http y entraría en un bucle de redirecciones (`ERR_TOO_MANY_REDIRECTS`). Paso a hacer tras el despliegue: abrir `https://<tu-servicio>.onrender.com/iniciar-sesion/`; si carga, la cabecera llega (es el paso (b) de abajo). Si da el bucle, ver (d).
- **Que la comprobación de salud de Render sigue verde con la redirección.** La documentación dice que un 3xx cuenta como sano y que sin ruta es una prueba TCP; no dice si la comprobación pasa por la redirección ni si manda `X-Forwarded-Proto`. Paso: tras el despliegue, mirar en Render que el despliegue figure como «Live» y no «Failed» (si falla, ver (d)). Si el servicio tiene una ruta de comprobación configurada, el `Host` que manda Render es el dominio propio verificado o el `onrender.com`, que tiene que estar en `DJANGO_ALLOWED_HOSTS`.
- **El `static_v`, los estáticos y el JavaScript detrás de https:** no se tocaron; cuenta como parte del «navegador real».

## Verificación a mano

Lo cubre una prueba (no hace falta repetirlo): que http redirige y https responde, el HSTS de 86400 y las cookies `Secure` y `HttpOnly` (recorrido). Lo que queda es lo que el cliente de Django no ve: el navegador y Render.

### (a) En local: `runserver` sigue andando por http

1. En tu `.env` (no se versiona), agregá la línea `DJANGO_DEBUG=1` (el `.env.example` ahora la trae). Sin ella, Django no arranca: «The SECRET_KEY setting must not be empty». No hace falta tocar nada más.
2. Con el entorno virtual activo: `python manage.py runserver`. Tiene que arrancar sin errores.
3. Abrí `http://localhost:8000/` en el navegador. **Tiene que mostrar el inicio de sesión por http, sin redirigir a https** (la barra de direcciones sigue en `http://`).
4. Iniciá sesión con una cuenta de prueba (con la contraseña de tus cuentas de prueba; nunca la escribas en un archivo del repo). Tiene que entrar al inicio normalmente.
5. En F12 → Application (Aplicación) → Cookies → `http://localhost:8000`: `sessionid` tiene **HttpOnly** tildado y **Secure** sin tildar. En F12 → Network, el pedido de la pantalla **no** trae `Strict-Transport-Security`.
6. `http://localhost:8000/admin/` carga (con `DJANGO_DEBUG=1` el admin existe, D-30).
7. Opcional, para comprobar que sin la variable falla: comentá `DJANGO_DEBUG=1` en `.env` y corré `python manage.py check`: tiene que decir que falta la clave. Volvé a dejarla.

### (b) Tras el despliegue, en Render

Antes: en Render → tu servicio → Environment, comprobá que están `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY` y `DJANGO_ALLOWED_HOSTS` con tu dirección (`<servicio>.onrender.com`, y el dominio propio si lo hay). No cambies nada si ya están.

1. En el panel de Render, el despliegue termina en **Live** (log sin errores, sin migraciones nuevas). Si queda en «Failed»: (d).
2. **Redirección.** Escribí a mano `http://<servicio>.onrender.com/` (con `http://`, no `https://`). Tiene que terminar en `https://<servicio>.onrender.com/iniciar-sesion/?next=/` o similar y cargar la pantalla. Un mensaje de «demasiadas redirecciones» (`ERR_TOO_MANY_REDIRECTS`) es el caso de (d).
3. **Navegador real.** Abrí una **ventana privada** (sin sesión), entrá a la dirección https, iniciá sesión con una cuenta real **hasta el final** (que llegue al inicio de su rol), navegá a dos o tres pantallas y cerrá la sesión. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver.
4. **La cookie.** Con la sesión abierta, F12 → Application → Cookies → tu dirección: `sessionid` tiene **Secure** y **HttpOnly** tildados; `csrftoken`, si aparece, tiene **Secure** (no hace falta que tenga HttpOnly).
5. **HSTS.** F12 → Network → recargá, elegí el primer pedido (el documento) → Headers → Response Headers: tiene que decir `strict-transport-security: max-age=86400` (sin `includeSubDomains` ni `preload`).
6. **Recuperar contraseña (opcional).** Pedí el enlace desde el inicio de sesión: si el correo está configurado, el enlace que llega empieza con `https://`.

### (c) Node-RED

1. En el nodo, con la dirección **https** de la API que muestra la pantalla del sistema IoT (paso 11 de IOT-03), mandá un pedido de prueba como siempre. Tiene que seguir recibiendo **200**.
2. Opcional: con `http://` en lugar de `https://` el pedido recibe una redirección 301 y **no se registra**; es lo esperado (la guía del nodo ya dice «Siempre https»).

### (d) Si algo falla en Render

- **Bucle de redirecciones** (`ERR_TOO_MANY_REDIRECTS`) o el despliegue en «Failed»: probablemente Render no manda `X-Forwarded-Proto`. Volvé atrás en Render → Events → «Rollback» al despliegue anterior (no hace falta tocar el código) y avisame: hay que revisar `SECURE_PROXY_SSL_HEADER` antes de volver a desplegar. Si querés seguir sin esperar, el navegador guardó HSTS por un día: usá una ventana privada o, en Chrome, `chrome://net-internals/#hsts` → «Delete domain security policies».
- **«DisallowedHost» o 400 en la comprobación de salud**: falta el dominio en `DJANGO_ALLOWED_HOSTS`; sumalo en Render → Environment.
- **No arranca por falta de clave** («SECRET_KEY must not be empty»): en Render falta `DJANGO_SECRET_KEY` (en producción ya debería estar; antes también hacía falta).
