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
| `fuentes/dm-mono-latin-400-normal.woff2` | `@fontsource/dm-mono@5.3.0` | `e1896b13b2b1bb112fac2f9571bd6c40e118746e77a4511edbf43fbb41bf3e1e` |
| `fuentes/dm-mono-latin-500-normal.woff2` | `@fontsource/dm-mono@5.3.0` | `9964608a849396bd00c4bfd7034afe03486469dcf20b4f6b8cbdfdd310369951` |

- Integrity de `@fontsource/inter@5.3.0`: `sha512-RofMylZmjlJEfELXeNHFWBRcSs75rGU/6bV2S2jfnvv/3rPXPGe0LgUJTklcHZ9lM4OZmAVFhcJPnACfb91A3g==`
- Integrity de `@fontsource/dm-mono@5.3.0`: `sha512-OINjI8C1S/wpchhQxl7njZdMn4+hnDCpQ4YtvvOpKNARo+0J8O1x1IcrChxNjHOhfVv1by8C/FQoy3hXK+C1Ug==`
- Licencia: SIL Open Font License 1.1 (`fuentes/OFL-inter.txt` y `fuentes/OFL-dm-mono.txt`). La OFL pide
  distribuir la licencia junto con las fuentes; por eso las dos copias están en la misma carpeta.

## Para actualizar

Cambiá la versión en el nombre del archivo y en las plantillas que lo cargan, repetí la verificación
del `integrity` y actualizá esta tabla.
