# Pruebas de PROD-ALT-SCT · Alta Sector (docs/casos_de_uso/maestros/sectores.md) y de lo que cita: D-22 y D-36 (auditoría),
# D-37 (apps por niveles) y D-40 (orden de bloqueos). Modelo de dominio: ronda 22 (docs/modelo/maestros.md).
#
# Servicio que se prueba (maestros/servicios/sectores.py), tomado del módulo dentro de cada prueba:
#   alta_sector(actor, invernadero_id, *, nombre, tipo_etapa_id, cant_agujeros_total) -> SectorProduccion
#     - Precondición a: actor no es un Agrónomo activo -> PermissionDenied.
#     - Precondición b: invernadero inexistente -> Http404; de otro Agrónomo -> PermissionDenied; inactivo -> ValidationError
#       general, código ``invernadero_inactivo``.
#     - Errores de campo (un ValidationError con ``error_dict``, todos juntos): ``nombre``, ``tipo_etapa`` y
#       ``cant_agujeros_total``.

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from maestros.models import SectorProduccion
from maestros.servicios import sectores
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    codigos_de,
    crear_agronomo,
    crear_agronomo_con_invernadero,
    crear_invernadero,
    crear_sector,
    error_de,
    tipo_etapa,
)

ALTA = RegistroAuditoria.Accion.ALTA_SECTOR


class ProdAltSctServicioTests(ConDatosDeMaestros, TestCase):
    """Reglas, precondiciones y postcondiciones de PROD-ALT-SCT."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()

    def alta(self, actor=None, invernadero=None, **datos):
        """Llama al servicio con datos válidos; ``datos`` pisa cualquiera."""
        datos = {"nombre": "C-1", "tipo_etapa_id": tipo_etapa("germinacion").pk, "cant_agujeros_total": 100} | datos
        return sectores.alta_sector(
            actor or self.agronomo, (invernadero or self.invernadero).pk, **datos
        )

    # ---- precondiciones ----

    def test_pre_a_un_gerente_no_da_de_alta(self):
        """PROD-ALT-SCT precondición a: solo un Agrónomo activo (SEG-13)."""
        with self.assertRaises(PermissionDenied):
            self.alta(actor=crear_gerente())

    def test_pre_a_un_capataz_no_da_de_alta(self):
        """PROD-ALT-SCT precondición a."""
        with self.assertRaises(PermissionDenied):
            self.alta(actor=crear_capataz())

    def test_pre_a_un_agronomo_inactivo_no_da_de_alta(self):
        """PROD-ALT-SCT precondición a: la cuenta tiene que estar activa."""
        self.agronomo.is_active = False
        self.agronomo.save()
        with self.assertRaises(PermissionDenied):
            self.alta()

    def test_pre_b_el_agronomo_de_otro_invernadero_no_da_de_alta(self):
        """PROD-ALT-SCT precondición b y regla 1: el invernadero tiene que estar a cargo del actor."""
        otro = crear_agronomo(email="otro@infoponia.com")
        with self.assertRaises(PermissionDenied):
            self.alta(actor=otro)
        self.assertFalse(SectorProduccion.objects.exists())

    def test_pre_b_un_invernadero_inactivo_se_rechaza(self):
        """PROD-ALT-SCT precondición b: el invernadero está activo (``invernadero_inactivo``)."""
        inactivo = crear_invernadero("Inactivo", activo=False, agronomo=self.agronomo)
        error = error_de(lambda: self.alta(invernadero=inactivo))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["invernadero_inactivo"])

    def test_pre_b_un_invernadero_que_no_existe_da_404(self):
        """PROD-ALT-SCT precondición b: un id inexistente da 404."""
        with self.assertRaises(Http404):
            sectores.alta_sector(
                self.agronomo, 999999, nombre="C-1", tipo_etapa_id=tipo_etapa().pk, cant_agujeros_total=10
            )

    # ---- regla 2: nombre ----

    def test_regla_2_el_nombre_es_obligatorio(self):
        """PROD-ALT-SCT regla 2: el nombre es obligatorio."""
        for vacio in ("", "   ", None):
            with self.subTest(vacio=vacio):
                self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre=vacio)), "nombre"), ["obligatorio"])

    def test_regla_2_el_nombre_tiene_que_tener_contenido(self):
        """PROD-ALT-SCT regla 2 y D-39: no puede ser solo símbolos."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre="-----")), "nombre"), ["sin_contenido"])

    def test_regla_2_el_nombre_tiene_hasta_40_caracteres(self):
        """Modelo «SectorProduccion» (decisión de MAE-03): hasta 40 caracteres, con un error de campo."""
        self.alta(nombre="a" * 40)
        self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre="b" * 41)), "nombre"), ["demasiado_largo"])

    def test_regla_2_el_nombre_se_guarda_recortado(self):
        """Modelo «SectorProduccion»: único sin espacios al borde; el servicio recorta."""
        self.assertEqual(self.alta(nombre="  C-9  ").nombre_sector, "C-9")

    def test_regla_2_el_nombre_repetido_en_el_invernadero_se_rechaza_sin_distinguir_mayusculas(self):
        """PROD-ALT-SCT regla 2 y precondición c."""
        crear_sector(self.invernadero, "C-1")
        error = error_de(lambda: self.alta(nombre=" c-1 "))
        self.assertEqual(codigos_de(error, "nombre"), ["nombre_repetido"])
        self.assertEqual(SectorProduccion.objects.count(), 1)

    def test_regla_2_el_nombre_repetido_cuenta_tambien_entre_los_dados_de_baja(self):
        """PROD-ALT-SCT regla 2: se cuentan también los sectores dados de baja."""
        crear_sector(self.invernadero, "C-1", estado="inactivo")
        self.assertEqual(codigos_de(error_de(lambda: self.alta(nombre="C-1")), "nombre"), ["nombre_repetido"])

    def test_regla_2_dos_invernaderos_pueden_tener_sectores_con_el_mismo_nombre(self):
        """PROD-ALT-SCT regla 2."""
        otro = crear_invernadero("Otro", agronomo=self.agronomo)
        crear_sector(otro, "C-1")
        self.assertEqual(self.alta(nombre="C-1").nombre_sector, "C-1")

    # ---- regla 3: tipo de etapa ----

    def test_regla_3_el_tipo_de_etapa_es_obligatorio(self):
        """PROD-ALT-SCT regla 3: se elige del catálogo."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(tipo_etapa_id=None)), "tipo_etapa"), ["obligatorio"])

    def test_regla_3_un_tipo_de_etapa_que_no_existe_se_rechaza(self):
        """PROD-ALT-SCT regla 3: solo los cinco tipos del catálogo fijo."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta(tipo_etapa_id=999999)), "tipo_etapa"), ["no_existe"])

    def test_regla_3_acepta_cada_uno_de_los_cinco_tipos(self):
        """PROD-ALT-SCT regla 3: Germinación, Crecimiento, Floración, Fructificación y Maduración."""
        for numero, codigo in enumerate(("germinacion", "crecimiento", "floracion", "fructificacion", "maduracion")):
            with self.subTest(codigo=codigo):
                sector = self.alta(nombre=f"S{numero}", tipo_etapa_id=tipo_etapa(codigo).pk)
                self.assertEqual(sector.tipo_etapa.codigo, codigo)

    # ---- regla 4: agujeros ----

    def test_regla_4_la_cantidad_tiene_que_ser_un_entero_mayor_que_cero(self):
        """PROD-ALT-SCT regla 4."""
        for invalida in (0, -5, "0", "abc", "1.5", "", None, "  "):
            with self.subTest(invalida=invalida):
                error = error_de(lambda: self.alta(cant_agujeros_total=invalida))
                self.assertEqual(len(codigos_de(error, "cant_agujeros_total")), 1)
        self.assertFalse(SectorProduccion.objects.exists())

    def test_regla_4_acepta_un_entero_o_un_texto_con_un_entero(self):
        """PROD-ALT-SCT regla 4: el formulario manda texto."""
        self.assertEqual(self.alta(nombre="A", cant_agujeros_total="12").cant_agujeros_total, 12)
        self.assertEqual(self.alta(nombre="B", cant_agujeros_total=" 7 ").cant_agujeros_total, 7)

    def test_regla_4_todos_los_errores_de_campo_vuelven_juntos(self):
        """Patrón ABM, §2: un solo ValidationError con un error por campo."""
        error = error_de(lambda: self.alta(nombre="", tipo_etapa_id=None, cant_agujeros_total=0))
        self.assertEqual(set(error.error_dict), {"nombre", "tipo_etapa", "cant_agujeros_total"})

    # ---- reglas 5 y 6 ----

    def test_regla_5_un_sector_nuevo_tiene_todos_sus_agujeros_libres(self):
        """PROD-ALT-SCT regla 5: ocupados, comprometidos y libres se calculan; el nuevo tiene todo libre."""
        sector = self.alta(cant_agujeros_total=120)
        agujeros = sectores.agujeros_de([sector])[sector.pk]
        self.assertEqual(tuple(agujeros), (120, 0, 0, 120))

    def test_regla_6_el_sector_no_tiene_ubicacion_ni_densidad(self):
        """PROD-ALT-SCT regla 6: un sector genérico con su cantidad de agujeros."""
        campos = {campo.name for campo in SectorProduccion._meta.get_fields()}
        self.assertFalse(campos & {"ubicacion", "densidad"})

    # ---- postcondiciones ----

    def test_post_a_crea_un_sector_activo_con_sus_datos_y_asociaciones(self):
        """PROD-ALT-SCT postcondición a."""
        sector = self.alta(nombre="C-1", cant_agujeros_total=80, tipo_etapa_id=tipo_etapa("floracion").pk)
        sector.refresh_from_db()
        self.assertEqual(
            (sector.nombre_sector, sector.cant_agujeros_total, sector.estado_sector, sector.invernadero, sector.tipo_etapa.codigo),
            ("C-1", 80, "activo", self.invernadero, "floracion"),
        )

    def test_post_b_la_marca_sin_sectores_deja_de_mostrarse(self):
        """PROD-ALT-SCT postcondición b."""
        self.assertFalse(self.invernadero.tiene_sectores())
        self.alta()
        self.assertTrue(self.invernadero.tiene_sectores())

    def test_post_c_crea_un_log_con_usuario_rol_y_el_sector_creado(self):
        """PROD-ALT-SCT postcondición c y D-36: acción ``alta_sector``, afectados (sector e invernadero) y cambios."""
        sector = self.alta(nombre="C-1", cant_agujeros_total=80)
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        self.assertEqual(registro.usuario_id, self.agronomo.pk)
        self.assertEqual(registro.rol, "agronomo")
        self.assertEqual({a["id"] for a in registro.afectados}, {sector.pk, self.invernadero.pk})
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["nombre"], {"antes": None, "despues": "C-1"})
        self.assertEqual(cambios["cant_agujeros_total"], {"antes": None, "despues": 80})
        self.assertEqual(cambios["estado"], {"antes": None, "despues": "activo"})
        self.assertEqual(cambios["tipo_etapa"]["despues"]["texto"], "Germinación")

    def test_post_c_un_alta_rechazada_no_deja_registro_ni_sector(self):
        """D-22: no queda un registro de una operación que no se hizo."""
        error_de(lambda: self.alta(nombre=""))
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    def test_flujo_principal_el_agronomo_a_cargo_agrega_un_sector(self):
        """PROD-ALT-SCT, flujo principal: devuelve el sector creado y queda consultable por quien lo creó."""
        sector = self.alta()
        self.assertIn(sector, list(sectores.consultar_sectores(self.agronomo, self.invernadero.pk)))

    def test_el_error_general_y_los_de_campo_son_validation_error(self):
        """Los rechazos de datos son ValidationError (nunca un 500)."""
        with self.assertRaises(ValidationError):
            self.alta(nombre="")
