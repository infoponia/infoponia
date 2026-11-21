# Pruebas de CMP-ALT-TIN · Alta Tipo de Insumo (docs/casos_de_uso/inventario/tipos_de_insumo.md). Cita D-22, D-28 y D-36.
#
# Servicio que se prueba (inventario/servicios/tipos_de_insumo.py), tomado del módulo dentro de cada prueba:
#   alta_tipo_insumo(actor, *, nombre, consumo_directo) -> TipoInsumo
#     - Precondición a y regla 1: cualquier Agrónomo activo (PermissionDenied si no).
#     - Regla 2: nombre obligatorio (``obligatorio``), con contenido (``sin_contenido``), de hasta 100 (``demasiado_largo``) y único
#       sin distinguir mayúsculas ni espacios al borde, entre activas e inactivas y del sistema (``nombre_repetido``). Error en el campo ``nombre``.
#     - Regla 3: consumo directo obligatorio (``obligatorio``) y uno de los tres valores (``invalido``). Error en el campo ``consumo_directo``.
#     - Todos los errores de campo juntos en un solo ValidationError (docs/patrones/abm.md, sección 2).
#     - Regla 4: nunca crea una del sistema.
#     - Postcondición b: un registro ``alta_tipo_insumo`` (D-36).

from django.core.exceptions import PermissionDenied
from django.test import TestCase, TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.models import TipoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    asegurar_datos_de_inventario,
    perezoso,
    tipo_de_insumo,
)
from maestros.tests.fabricas import asegurar_datos_de_maestros, codigos_de, crear_agronomo, crear_vendedor, error_de

tipos = perezoso("inventario.servicios.tipos_de_insumo")
ALTA = RegistroAuditoria.Accion.ALTA_TIPO_INSUMO


class CmpAltTinServicioTests(ConDatosDeInventario, TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-ALT-TIN."""

    def setUp(self):
        self.agronomo = crear_agronomo()

    def alta(self, nombre="Limpieza", consumo="como_gasto", actor=None):
        return tipos.alta_tipo_insumo(actor or self.agronomo, nombre=nombre, consumo_directo=consumo)

    # ---- precondición a y regla 1 ----

    def test_pre_a_un_gerente_no_da_de_alta(self):
        """CMP-ALT-TIN precondición a: solo un Agrónomo activo (el Gerente no gestiona categorías)."""
        with self.assertRaises(PermissionDenied):
            self.alta(actor=crear_gerente())

    def test_pre_a_capataz_vendedor_y_administrador_no_dan_de_alta(self):
        """CMP-ALT-TIN precondición a: ningún otro rol."""
        for cuenta in (crear_capataz(), crear_vendedor(), crear_administrador()):
            with self.subTest(rol=type(cuenta).__name__):
                with self.assertRaises(PermissionDenied):
                    self.alta(actor=cuenta)

    def test_pre_a_un_agronomo_inactivo_no_da_de_alta(self):
        """CMP-ALT-TIN precondición a: la cuenta tiene que estar activa (SEG-13)."""
        inactivo = crear_agronomo(email="inactivo@infoponia.com", activo=False)
        with self.assertRaises(PermissionDenied):
            self.alta(actor=inactivo)

    def test_regla_1_cualquier_agronomo_activo_da_de_alta_sin_invernadero_a_cargo(self):
        """CMP-ALT-TIN regla 1: la categoría es del catálogo y vale para todos los invernaderos: no hay «a cargo»."""
        self.assertEqual(self.alta().nombre_tipo_insumo, "Limpieza")

    # ---- regla 2: el nombre ----

    def test_regla_2_el_nombre_es_obligatorio(self):
        """CMP-ALT-TIN regla 2: nombre vacío o de solo espacios se rechaza en el campo ``nombre``."""
        for vacio in ("", "   ", None):
            with self.subTest(nombre=vacio):
                error = error_de(lambda: self.alta(nombre=vacio))
                self.assertEqual(codigos_de(error, "nombre"), ["obligatorio"])

    def test_regla_2_el_nombre_necesita_una_letra_o_un_numero(self):
        """CMP-ALT-TIN regla 2 (D-39, contenido real): «-----» no es un nombre."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre="-----")), "nombre"), ["sin_contenido"])

    def test_regla_2_el_nombre_tiene_hasta_100_caracteres(self):
        """Modelo: 100 caracteres. El largo es de esta ronda (los CU no lo fijan) y se prueba en el límite."""
        self.assertEqual(len(self.alta(nombre="a" * 100).nombre_tipo_insumo), 100)
        self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre="b" * 101)), "nombre"), ["demasiado_largo"])

    def test_regla_2_el_nombre_se_guarda_recortado(self):
        """CMP-ALT-TIN regla 2: sin espacios al principio o al final."""
        self.assertEqual(self.alta(nombre="  Limpieza  ").nombre_tipo_insumo, "Limpieza")

    def test_regla_2_el_nombre_repetido_se_rechaza_sin_distinguir_mayusculas_ni_espacios(self):
        """CMP-ALT-TIN regla 2 y verificación a mano 3: «limpieza » (minúscula, con espacio) da nombre repetido."""
        self.alta("Limpieza")
        error = error_de(lambda: self.alta(nombre="limpieza "))
        self.assertEqual(codigos_de(error, "nombre"), ["nombre_repetido"])
        self.assertEqual(TipoInsumo.objects.filter(nombre_tipo_insumo__iexact="limpieza").count(), 1)

    def test_regla_2_cuenta_tambien_una_categoria_inactiva(self):
        """CMP-ALT-TIN regla 2: el nombre es único entre activas e inactivas."""
        tipo_de_insumo("Nutrientes", activo=False)
        self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre="nutrientes")), "nombre"), ["nombre_repetido"])

    def test_regla_2_cuenta_tambien_el_nombre_de_una_categoria_del_sistema(self):
        """CMP-ALT-TIN («Cómo se aplica»): nadie crea otra «Envases»."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre="ENVASES")), "nombre"), ["nombre_repetido"])

    # ---- regla 3: el consumo directo ----

    def test_regla_3_el_consumo_directo_es_obligatorio(self):
        """CMP-ALT-TIN regla 3 y verificación a mano 3: dejarlo sin elegir da error en su campo."""
        for vacio in ("", None):
            with self.subTest(consumo=vacio):
                error = error_de(lambda: self.alta(consumo=vacio))
                self.assertEqual(codigos_de(error, "consumo_directo"), ["obligatorio"])

    def test_regla_3_el_consumo_directo_tiene_que_ser_uno_de_los_tres(self):
        """CMP-ALT-TIN regla 3: «no admite», «como gasto» o «como costo de los lotes»."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(consumo="siempre")), "consumo_directo"), ["invalido"])

    def test_regla_3_se_guardan_los_tres_consumos_directos(self):
        """CMP-ALT-TIN regla 3: los tres valores se pueden elegir."""
        for consumo in ("no_admite", "como_gasto", "como_costo_de_los_lotes"):
            with self.subTest(consumo=consumo):
                self.assertEqual(self.alta(nombre=f"C {consumo}", consumo=consumo).consumo_directo, consumo)

    def test_regla_2_y_3_los_errores_de_campo_vienen_todos_juntos(self):
        """docs/patrones/abm.md sección 2: un solo ValidationError con un error por campo, para que la pantalla los marque a la vez."""
        error = error_de(lambda: self.alta(nombre="", consumo=""))
        self.assertEqual(codigos_de(error, "nombre"), ["obligatorio"])
        self.assertEqual(codigos_de(error, "consumo_directo"), ["obligatorio"])

    def test_regla_2_y_3_un_error_no_crea_nada_ni_audita(self):
        """Todo o nada: con un error de validación no queda ninguna fila nueva ni registro de auditoría."""
        antes = TipoInsumo.objects.count()
        error_de(lambda: self.alta(nombre="", consumo=""))
        self.assertEqual(TipoInsumo.objects.count(), antes)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    # ---- regla 4 y postcondición a ----

    def test_regla_4_la_categoria_creada_no_es_del_sistema(self):
        """CMP-ALT-TIN regla 4: desde este caso de uso no se crean categorías del sistema (sin código)."""
        tipo = self.alta()
        self.assertFalse(tipo.es_del_sistema)
        self.assertIsNone(tipo.codigo)
        self.assertEqual(TipoInsumo.objects.filter(es_del_sistema=True).count(), 4)

    def test_post_a_nace_activa_con_su_nombre_y_su_consumo_y_sin_insumos(self):
        """CMP-ALT-TIN postcondición a: activa, con su nombre y consumo directo, que no es del sistema y no tiene insumos."""
        tipo = self.alta("Nutrientes", "como_costo_de_los_lotes")
        tipo.refresh_from_db()
        self.assertEqual(
            (tipo.nombre_tipo_insumo, tipo.consumo_directo, tipo.estado_tipo_insumo, tipo.es_del_sistema),
            ("Nutrientes", "como_costo_de_los_lotes", "activo", False),
        )
        self.assertEqual(tipo.insumos.count(), 0)

    def test_post_b_audita_el_alta_con_usuario_rol_y_la_categoria_creada(self):
        """CMP-ALT-TIN postcondición b y D-36: usuario, rol, identificador de la categoría y los datos con «antes» nulo."""
        tipo = self.alta("Limpieza", "como_gasto")
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        self.assertEqual([(a["modelo"], a["id"], a["texto"]) for a in registro.afectados], [("inventario.tipoinsumo", tipo.pk, "Limpieza")])
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "nombre": {"antes": None, "despues": "Limpieza"},
                "consumo_directo": {"antes": None, "despues": "como_gasto"},
                "estado": {"antes": None, "despues": "activo"},
            },
        )

    def test_post_b_el_registro_se_lee_en_la_pantalla_de_auditoria(self):
        """D-36: las filas de cambios se muestran con el nombre visible de cada campo y de cada valor."""
        self.alta("Limpieza", "como_gasto")
        filas = RegistroAuditoria.objects.get(accion=ALTA).filas_de_cambios()
        self.assertEqual(
            filas,
            [("Nombre", "—", "Limpieza"), ("Estado", "—", "Activo"), ("Consumo directo", "—", "Como gasto")],
        )


@tag("concurrencia")
class CmpAltTinConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Dos altas a la vez (docs/patrones/abm.md, sección 4: el segundo recibe el mismo error de campo, no un 500). Es un
    ``TransactionTestCase``: su ``flush`` vacía las categorías del sistema, así que hereda de ``ConDatosDeInventario`` (que
    ya trae los datos de maestros) y las asegura de nuevo en cada prueba."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.uno = crear_agronomo()
        self.otro = crear_agronomo(email="otro@infoponia.com")

    def test_regla_2_dos_altas_con_el_mismo_nombre_crean_una_sola_categoria(self):
        """CMP-ALT-TIN regla 2: la segunda recibe ``nombre_repetido`` (la restricción única de la base lo respalda), nunca un 500."""
        resultados = correr_a_la_vez(
            lambda: tipos.alta_tipo_insumo(self.uno, nombre="Limpieza", consumo_directo="como_gasto"),
            lambda: tipos.alta_tipo_insumo(self.otro, nombre="limpieza", consumo_directo="no_admite"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["nombre_repetido"])
        self.assertEqual(TipoInsumo.objects.filter(nombre_tipo_insumo__iexact="limpieza").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ALTA).count(), 1)
