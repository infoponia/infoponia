# Pruebas de CMP-ALT-INS · Alta Insumo (docs/casos_de_uso/inventario/insumos.md). Cita D-22, D-28, D-36 y D-40.
#
# Servicio que se prueba (inventario/servicios/insumos.py), tomado del módulo dentro de cada prueba:
#   alta_insumo(actor, *, nombre, tipo_insumo_id, unidad, descripcion="", controla_vencimiento=False) -> Insumo
#     - Precondición a y regla 1: cualquier Agrónomo activo (PermissionDenied si no).
#     - Precondición b y regla 2: nombre obligatorio, con contenido, de hasta 100 y único entre todos los insumos (activos e inactivos),
#       sin distinguir mayúsculas ni espacios al borde (``nombre_repetido``). Error en el campo ``nombre``.
#     - Regla 3: descripción opcional, recortada, de hasta 300 (``demasiado_largo``). Campo ``descripcion``.
#     - Regla 4: la categoría se elige entre las ACTIVAS y no es Semillas. Campo ``categoria``: ``obligatorio``, ``invalida`` (no
#       existe), ``categoria_inactiva``, ``categoria_de_semillas``.
#     - Regla 5: la unidad es una de las ocho. Campo ``unidad``: ``obligatorio``, ``invalida``.
#     - Regla 6: ``controla_vencimiento`` (booleano). Regla 7: el aviso de «habilitar» es de la pantalla; el servicio no habilita.
#     - Postcondición b: un registro ``alta_insumo`` (D-36).
#   Concurrencia: el alta bloquea la categoría ANTES de crear el insumo (orden de docs/patrones/stock.md, sección 5): una baja
#   simultánea de la categoría no deja un insumo activo en una categoría inactiva.

from django.core.exceptions import PermissionDenied
from django.test import TestCase, TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.models import Insumo, InsumoInvernadero, TipoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    asegurar_datos_de_inventario,
    categoria_del_sistema,
    insumo,
    perezoso,
    tipo_de_insumo,
)
from maestros.tests.fabricas import (
    asegurar_datos_de_maestros,
    codigos_de,
    crear_agronomo,
    crear_vendedor,
    error_de,
)

insumos = perezoso("inventario.servicios.insumos")
tipos = perezoso("inventario.servicios.tipos_de_insumo")
ALTA = RegistroAuditoria.Accion.ALTA_INSUMO
UNIDADES = ["unidad", "kg", "g", "l", "ml", "m3", "m", "m2"]


class CmpAltInsServicioTests(ConDatosDeInventario, TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-ALT-INS."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.tipo = tipo_de_insumo("Limpieza")

    def alta(self, actor=None, **datos):
        base = {"nombre": "Detergente", "tipo_insumo_id": self.tipo.pk, "unidad": "l"}
        return insumos.alta_insumo(actor or self.agronomo, **(base | datos))

    # ---- precondición a y regla 1 ----

    def test_pre_a_un_gerente_no_da_de_alta(self):
        """CMP-ALT-INS precondición a: solo un Agrónomo activo (el Gerente no gestiona el catálogo)."""
        with self.assertRaises(PermissionDenied):
            self.alta(actor=crear_gerente())

    def test_pre_a_capataz_vendedor_y_administrador_no_dan_de_alta(self):
        """CMP-ALT-INS precondición a: ningún otro rol."""
        for cuenta in (crear_capataz(), crear_vendedor(), crear_administrador()):
            with self.subTest(rol=type(cuenta).__name__):
                with self.assertRaises(PermissionDenied):
                    self.alta(actor=cuenta)

    def test_pre_a_un_agronomo_inactivo_no_da_de_alta(self):
        """CMP-ALT-INS precondición a: la cuenta tiene que estar activa."""
        with self.assertRaises(PermissionDenied):
            self.alta(actor=crear_agronomo(email="inactivo@infoponia.com", activo=False))

    def test_regla_1_cualquier_agronomo_activo_da_de_alta_sin_invernadero_a_cargo(self):
        """CMP-ALT-INS regla 1: el catálogo es el mismo para toda la organización."""
        self.assertEqual(self.alta().nombre_insumo, "Detergente")

    # ---- regla 2: el nombre ----

    def test_regla_2_el_nombre_es_obligatorio(self):
        """CMP-ALT-INS regla 2: vacío o solo espacios se rechaza en el campo ``nombre``."""
        for vacio in ("", "   ", None):
            with self.subTest(nombre=vacio):
                self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre=vacio)), "nombre"), ["obligatorio"])

    def test_regla_2_el_nombre_necesita_una_letra_o_un_numero(self):
        """CMP-ALT-INS regla 2 (D-39, contenido real)."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre="---")), "nombre"), ["sin_contenido"])

    def test_regla_2_el_nombre_tiene_hasta_100_caracteres(self):
        """CMP-ALT-INS («Cómo se aplica»): nombre hasta 100; el límite se prueba."""
        self.assertEqual(len(self.alta(nombre="a" * 100).nombre_insumo), 100)
        self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre="b" * 101)), "nombre"), ["demasiado_largo"])

    def test_regla_2_el_nombre_se_guarda_recortado(self):
        """CMP-ALT-INS regla 2: sin espacios al principio o al final."""
        self.assertEqual(self.alta(nombre="  Detergente  ").nombre_insumo, "Detergente")

    def test_regla_2_el_nombre_repetido_se_rechaza_sin_distinguir_mayusculas_ni_espacios(self):
        """CMP-ALT-INS precondición b y regla 2 (verificación a mano 5): otras mayúsculas dan error de nombre."""
        self.alta(nombre="Detergente")
        error = error_de(lambda: self.alta(nombre="dETERGENTE "))
        self.assertEqual(codigos_de(error, "nombre"), ["nombre_repetido"])
        self.assertEqual(Insumo.objects.count(), 1)

    def test_regla_2_cuenta_tambien_un_insumo_inactivo(self):
        """CMP-ALT-INS regla 2: único entre activos e inactivos."""
        insumo("Viejo", tipo=self.tipo, activo=False)
        self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre="viejo")), "nombre"), ["nombre_repetido"])

    # ---- regla 3: la descripción ----

    def test_regla_3_la_descripcion_es_opcional_y_queda_vacia(self):
        """CMP-ALT-INS regla 3: opcional."""
        self.assertEqual(self.alta().descripcion_insumo, "")
        self.assertEqual(self.alta(nombre="Otro", descripcion=None).descripcion_insumo, "")

    def test_regla_3_la_descripcion_se_guarda_recortada_y_admite_hasta_300(self):
        """CMP-ALT-INS regla 3 y «Cómo se aplica»: texto libre, recortado, hasta 300 caracteres."""
        self.assertEqual(self.alta(descripcion="  Solución 2 ml/L  ").descripcion_insumo, "Solución 2 ml/L")
        self.assertEqual(len(self.alta(nombre="Otro", descripcion="d" * 300).descripcion_insumo), 300)
        self.assertEqual(
            codigos_de(error_de(lambda: self.alta(nombre="Tercero", descripcion="d" * 301)), "descripcion"), ["demasiado_largo"]
        )

    # ---- regla 4: la categoría ----

    def test_regla_4_la_categoria_es_obligatoria(self):
        """CMP-ALT-INS regla 4: sin elegir, error en ``categoria``."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(tipo_insumo_id=None)), "categoria"), ["obligatorio"])

    def test_regla_4_una_categoria_que_no_existe_se_rechaza(self):
        """CMP-ALT-INS regla 4: la categoría se elige entre las existentes."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(tipo_insumo_id=999999)), "categoria"), ["invalida"])

    def test_regla_4_una_categoria_inactiva_no_se_ofrece_y_se_rechaza(self):
        """CMP-ALT-INS regla 4: «entre las categorías activas»."""
        inactiva = tipo_de_insumo("Vieja", activo=False)
        self.assertEqual(codigos_de(error_de(lambda: self.alta(tipo_insumo_id=inactiva.pk)), "categoria"), ["categoria_inactiva"])

    def test_regla_4_la_categoria_semillas_no_se_ofrece_y_se_rechaza(self):
        """CMP-ALT-INS regla 4 y verificación a mano 6: las semillas se crean solas con su variedad (PROD-ALT-VAR)."""
        semillas = categoria_del_sistema("semillas")
        error = error_de(lambda: self.alta(tipo_insumo_id=semillas.pk))
        self.assertEqual(codigos_de(error, "categoria"), ["categoria_de_semillas"])
        self.assertEqual(Insumo.objects.count(), 0)

    def test_regla_4_las_otras_categorias_del_sistema_si_se_pueden_elegir(self):
        """CMP-ALT-INS regla 4: solo Semillas no se ofrece; un envase puede crearse en «Envases»."""
        envases = categoria_del_sistema("envases")
        self.assertEqual(self.alta(nombre="Sobres", tipo_insumo_id=envases.pk, unidad="unidad").tipo_insumo_id, envases.pk)

    # ---- regla 5: la unidad ----

    def test_regla_5_la_unidad_es_obligatoria_y_de_la_lista_fija(self):
        """CMP-ALT-INS regla 5: obligatoria; una fuera de la lista se rechaza."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(unidad="")), "unidad"), ["obligatorio"])
        self.assertEqual(codigos_de(error_de(lambda: self.alta(unidad="docena")), "unidad"), ["invalida"])

    def test_regla_5_se_aceptan_las_ocho_unidades(self):
        """CMP-ALT-INS regla 5 y verificación a mano 6: las ocho unidades."""
        for n, unidad in enumerate(UNIDADES):
            with self.subTest(unidad=unidad):
                self.assertEqual(self.alta(nombre=f"I{n}", unidad=unidad).unidad_medida_insumo, unidad)

    # ---- regla 6 ----

    def test_regla_6_controla_vencimiento_se_guarda_y_por_omision_no_controla(self):
        """CMP-ALT-INS regla 6: «controla vencimiento» verdadero o falso (por omisión, falso)."""
        self.assertFalse(self.alta().controla_vencimiento)
        self.assertTrue(self.alta(nombre="Nutriente", controla_vencimiento=True).controla_vencimiento)

    # ---- errores juntos, todo o nada ----

    def test_regla_2_a_5_los_errores_de_campo_vienen_todos_juntos(self):
        """docs/patrones/abm.md sección 2: un solo ValidationError con un error por campo."""
        error = error_de(lambda: self.alta(nombre="", tipo_insumo_id=None, unidad=""))
        self.assertEqual(sorted(error.error_dict), ["categoria", "nombre", "unidad"])

    def test_regla_2_a_5_un_error_no_crea_nada_ni_audita(self):
        """Todo o nada."""
        error_de(lambda: self.alta(nombre="", unidad=""))
        self.assertEqual(Insumo.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    # ---- postcondiciones ----

    def test_post_a_nace_activo_con_sus_datos_y_sin_habilitar_en_ningun_invernadero(self):
        """CMP-ALT-INS postcondición a y verificación a mano 5: activo, asociado a su categoría y sin habilitar."""
        nuevo = self.alta(descripcion="5 L", controla_vencimiento=True)
        nuevo.refresh_from_db()
        self.assertEqual(
            (nuevo.nombre_insumo, nuevo.descripcion_insumo, nuevo.tipo_insumo_id, nuevo.unidad_medida_insumo),
            ("Detergente", "5 L", self.tipo.pk, "l"),
        )
        self.assertEqual((nuevo.estado_insumo, nuevo.controla_vencimiento), ("activo", True))
        self.assertEqual(InsumoInvernadero.objects.filter(insumo=nuevo).count(), 0)

    def test_post_b_audita_el_alta_con_usuario_rol_e_insumo_creado(self):
        """CMP-ALT-INS postcondición b y D-36: usuario, rol, identificador del insumo y los datos con «antes» nulo."""
        nuevo = self.alta(descripcion="5 L", unidad="l", controla_vencimiento=True)
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        self.assertEqual([(a["modelo"], a["id"]) for a in registro.afectados], [("inventario.insumo", nuevo.pk)])
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["nombre"], {"antes": None, "despues": "Detergente"})
        self.assertEqual(cambios["descripcion"], {"antes": None, "despues": "5 L"})
        self.assertEqual(cambios["categoria"], {"antes": None, "despues": {"id": self.tipo.pk, "texto": "Limpieza"}})
        self.assertEqual(cambios["unidad_medida"], {"antes": None, "despues": "l"})
        self.assertEqual(cambios["controla_vencimiento"], {"antes": None, "despues": True})
        self.assertEqual(cambios["estado"], {"antes": None, "despues": "activo"})

    def test_post_b_sin_descripcion_no_figura_en_la_auditoria(self):
        """CMP-ALT-INS postcondición a: «su descripción (si se indicó)»: lo que no se indicó no se audita."""
        self.alta()
        self.assertNotIn("descripcion", RegistroAuditoria.objects.get(accion=ALTA).detalle["cambios"])


@tag("concurrencia")
class CmpAltInsConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de ``alta_insumo`` (D-40; docs/patrones/stock.md sección 5). Hereda de ``ConDatosDeInventario`` (con los datos
    de maestros) y asegura los datos en cada prueba: el ``flush`` de la anterior vacía las tablas."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.uno = crear_agronomo()
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.tipo = tipo_de_insumo("Limpieza")

    def test_regla_2_dos_altas_con_el_mismo_nombre_crean_un_solo_insumo(self):
        """CMP-ALT-INS regla 2: la segunda espera el índice único y recibe ``nombre_repetido`` (nunca un 500)."""
        resultados = correr_a_la_vez(
            lambda: insumos.alta_insumo(self.uno, nombre="Detergente", tipo_insumo_id=self.tipo.pk, unidad="l"),
            lambda: insumos.alta_insumo(self.otro, nombre="detergente", tipo_insumo_id=self.tipo.pk, unidad="kg"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["nombre_repetido"])
        self.assertEqual(Insumo.objects.count(), 1)

    def test_pre_c_la_baja_de_la_categoria_espera_al_alta_y_ve_el_insumo_nuevo(self):
        """CMP-BAJ-TIN precondición c y docs de CMP-ALT-TIN («Bloqueo»): el alta toma la categoría antes de crear el insumo; la
        baja espera, lo ve y se rechaza con ``insumos_activos``. Nunca queda un insumo activo en una categoría inactiva."""
        resultados = correr_a_la_vez(
            lambda: insumos.alta_insumo(self.uno, nombre="Detergente", tipo_insumo_id=self.tipo.pk, unidad="l"),
            lambda: tipos.baja_tipo_insumo(self.otro, self.tipo.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["insumos_activos"])
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.estado_tipo_insumo, "activo")
        self.assertEqual(Insumo.objects.filter(estado_insumo="activo").count(), 1)

    def test_regla_4_el_alta_espera_a_la_baja_de_la_categoria_y_la_encuentra_inactiva(self):
        """CMP-ALT-INS regla 4: si la baja de la categoría va primera, el alta espera, relee la categoría inactiva y se
        rechaza con ``categoria_inactiva``: no queda un insumo activo en una categoría inactiva."""
        resultados = correr_a_la_vez(
            lambda: tipos.baja_tipo_insumo(self.otro, self.tipo.pk),
            lambda: insumos.alta_insumo(self.uno, nombre="Detergente", tipo_insumo_id=self.tipo.pk, unidad="l"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["categoria_inactiva"])
        self.assertEqual(Insumo.objects.count(), 0)
        self.assertEqual(TipoInsumo.objects.get(pk=self.tipo.pk).estado_tipo_insumo, "inactivo")
