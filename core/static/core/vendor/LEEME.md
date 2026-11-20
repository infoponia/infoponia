# Archivos de terceros incluidos en el repo

Este archivo registra el origen de cada archivo de terceros que se sirve como estático desde `core`.
Los archivos minificados y las fuentes no pueden llevar el comentario inicial que pide `CLAUDE.md`,
así que su propósito, su versión y su origen quedan acá. Fuente: D-24 (HTMX como archivo estático) y
la autorización del 08/11/2026 para las fuentes (tarea 02).

Cada paquete se bajó del registro de npm, y antes de extraerlo se verificó que su `sha512` coincidiera
con el `integrity` publicado en el registro. La columna SHA-256 corresponde al archivo copiado, para
poder comprobar después que no cambió.

## HTMX

| Archivo | Paquete npm | Licencia |
|---|---|---|
| `vendor/htmx-2.0.11.min.js` (copia de `dist/htmx.min.js`) | `htmx.org@2.0.11` | Zero-Clause BSD (`vendor/htmx-LICENSE.txt`) |

- Integrity del paquete: `sha512-Thx/WtpeOQqSrqBCw/A1cwGJGg4UrVa3+sW0GmrM3p4gJgO89ecH4qtbnyzDDWFvBTqjnIMCgELTNt636dtamA==`
- SHA-256 del archivo: `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717`

## Fuentes (subconjunto *latin*: U+0000–00FF, U+2000–206F y otros; cubre á, ñ, ü, ¿, « » y —)

| Archivo | Paquete npm | SHA-256 |
|---|---|---|
| `fuentes/inter-latin-400-normal.woff2` | `@fontsource/inter@5.3.0` | `8909904ab6c872eb994093482a88a28eca2cd95912d7b6fecd72103b0dc07edc` |
| `fuentes/inter-latin-500-normal.woff2` | `@fontsource/inter@5.3.0` | `f3779f1efccc4bdcdf9c0a02ab95bf6bd092ed09c48c08cedc725889edd1d19f` |
| `fuentes/inter-latin-600-normal.woff2` | `@fontsource/inter@5.3.0` | `f9a06e79cd3a2a20951c0f0e28f66dd0e6d3fda73911d640a2125c8fcb78f21a` |
| `fuentes/inter-latin-700-normal.woff2` | `@fontsource/inter@5.3.0` | `6f56409fd3d64bb85f7d070bce20749db2d66b6d63cec586cc22d1c761be2491` |

- Integrity de `@fontsource/inter@5.3.0`: `sha512-RofMylZmjlJEfELXeNHFWBRcSs75rGU/6bV2S2jfnvv/3rPXPGe0LgUJTklcHZ9lM4OZmAVFhcJPnACfb91A3g==`
- Licencia: SIL Open Font License 1.1 (`fuentes/OFL-inter.txt`). La OFL pide distribuir la licencia junto con las fuentes;
  por eso la copia está en la misma carpeta. DM Mono se quitó en UI-01 (D-47): el estilo v2 usa solo Inter.

## Para actualizar

Cambiá la versión en el nombre del archivo y en las plantillas que lo cargan, repetí la verificación
del `integrity` y actualizá esta tabla.
