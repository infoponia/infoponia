# Pruebas de PROD-ALT-CLT · Alta Cultivo (docs/casos_de_uso/maestros/cultivos.md) y de lo que cita: D-22 y D-36 (auditoría) y
# D-37. Modelo de dominio: ronda 22 (docs/modelo/maestros.md, «Cultivo»).
#
# Servicio que se prueba (maestros/servicios/cultivos.py), tomado del módulo dentro de cada prueba:
#   alta_cultivo(actor, *, nombre) -> Cultivo
#     - Precondición a: actor no es un Agrónomo activo -> PermissionDenied.
#     - Regla 2 / precondición b: errores de campo ``nombre`` (un ValidationError con ``error_dict``).

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from maestros.models import Cultivo
from maestros.servicios import cultivos
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    codigos_de,
    crear_agronomo,
    crear_cultivo,
    crear_invernadero,
    error_de,
)

ALTA = RegistroAuditoria.Accion.ALTA_CULTIVO


class ProdAltCltServicioTests(ConDatosDeMaestros, TestCase):
    """Reglas, precondiciones y postcondiciones de PROD-ALT-CLT."""

    def setUp(self):
        self.agronomo = crear_agronomo()

    def alta(self, nombre="Lechuga", actor=None):
        return cultivos.alta_cultivo(actor or self.agronomo, nombre=nombre)

    # ---- precondición a y regla 1 ----

    def test_pre_a_un_gerente_no_da_de_alta(self):
        """PROD-ALT-CLT precondición a: solo un Agrónomo activo (SEG-13)."""
        with self.assertRaises(PermissionDenied):
            self.alta(actor=crear_gerente())

    def test_pre_a_un_capataz_no_da_de_alta(self):
        """PROD-ALT-CLT precondición a."""
        with self.assertRaises(PermissionDenied):
            self.alta(actor=crear_capataz())

    def test_pre_a_un_agronomo_inactivo_no_da_de_alta(self):
        """PROD-ALT-CLT precondición a: la cuenta tiene que estar activa."""
        self.agronomo.is_active = False
        self.agronomo.save()
        with self.assertRaises(PermissionDenied):
            self.alta()

    def test_regla_1_cualquier_agronomo_activo_registra_cultivos_sin_tener_invernadero(self):
        """PROD-ALT-CLT regla 1: el cultivo no pertenece a un invernadero y lo comparten todos."""
        self.assertEqual(self.alta().nombre_cultivo, "Lechuga")
        otro = crear_agronomo(email="otro@infoponia.com")
        crear_invernadero("Inv", agronomo=otro)
        self.assertEqual(self.alta("Acelga", actor=otro).nombre_cultivo, "Acelga")

    # ---- regla 2: nombre ----

    def test_regla_2_el_nombre_es_obligatorio(self):
        """PROD-ALT-CLT regla 2."""
        for vacio in ("", "   ", None):
            with self.subTest(vacio=vacio):
                self.assertEqual(codigos_de(error_de(lambda: self.alta(vacio)), "nombre"), ["obligatorio"])

    def test_regla_2_el_nombre_tiene_que_tener_contenido(self):
        """PROD-ALT-CLT regla 2 y D-39: no puede ser solo símbolos."""
        self.assertEqual(codigos_de(error_de(lambda: self.alta("-----")), "nombre"), ["sin_contenido"])

    def test_regla_2_el_nombre_tiene_hasta_40_caracteres(self):
        """Modelo «Cultivo» (límite de esta ronda): hasta 40, con un error de campo y no un 500."""
        self.alta("a" * 40)
        self.assertEqual(codigos_de(error_de(lambda: self.alta("b" * 41)), "nombre"), ["demasiado_largo"])

    def test_regla_2_el_nombre_se_guarda_recortado(self):
        """PROD-ALT-CLT regla 2: sin espacios al principio o al final."""
        self.assertEqual(self.alta("  Lechuga  ").nombre_cultivo, "Lechuga")

    def test_regla_2_el_nombre_repetido_se_rechaza_sin_distinguir_mayusculas_ni_espacios(self):
        """PROD-ALT-CLT regla 2 y precondición b."""
        crear_cultivo("Lechuga")
        error = error_de(lambda: self.alta("  LECHUGA "))
        self.assertEqual(codigos_de(error, "nombre"), ["nombre_repetido"])
        self.assertEqual(Cultivo.objects.count(), 1)

    def test_regla_2_el_nombre_repetido_cuenta_tambien_entre_los_inactivos(self):
        """PROD-ALT-CLT regla 2: único entre todos los cultivos, activos o inactivos."""
        crear_cultivo("Lechuga", activo=False)
        self.assertEqual(codigos_de(error_de(lambda: self.alta("lechuga")), "nombre"), ["nombre_repetido"])

    # ---- postcondiciones y reglas 3 ----

    def test_post_a_crea_un_cultivo_activo_con_su_nombre_y_sin_variedades(self):
        """PROD-ALT-CLT postcondición a y regla 3."""
        cultivo = self.alta()
        cultivo.refresh_from_db()
        self.assertEqual((cultivo.nombre_cultivo, cultivo.estado_cultivo), ("Lechuga", "activo"))
        self.assertFalse(cultivo.variedades.exists())

    def test_post_b_crea_un_log_con_usuario_rol_y_el_cultivo_creado(self):
        """PROD-ALT-CLT postcondición b y D-36: acción ``alta_cultivo``, el cultivo afectado y sus cambios con «antes» nulo."""
        cultivo = self.alta()
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        self.assertEqual([a["id"] for a in registro.afectados], [cultivo.pk])
        self.assertEqual(registro.detalle["cambios"]["nombre"], {"antes": None, "despues": "Lechuga"})
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": None, "despues": "activo"})

    def test_post_b_un_alta_rechazada_no_deja_registro_ni_cultivo(self):
        """D-22: no queda un registro de una operación que no se hizo."""
        error_de(lambda: self.alta(""))
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())
        self.assertFalse(Cultivo.objects.exists())

    def test_flujo_principal_el_cultivo_creado_se_consulta(self):
        """PROD-ALT-CLT, flujo principal."""
        cultivo = self.alta()
        self.assertIn(cultivo, list(cultivos.consultar_cultivos(self.agronomo)))
