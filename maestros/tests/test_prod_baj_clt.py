# Pruebas de PROD-BAJ-CLT · Baja Cultivo (docs/casos_de_uso/maestros/cultivos.md). Cita D-22 y D-36 (auditoría).
#
# Servicio que se prueba (maestros/servicios/cultivos.py), tomado del módulo dentro de cada prueba:
#   baja_cultivo(actor, cultivo_id) -> Cultivo
#     - Precondición b: el cultivo no está activo -> ValidationError general ``cultivo_inactivo``.
#     - Precondición c y regla 2: con variedades activas -> ValidationError general ``variedades_activas`` que dice cuántas son.

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from maestros.servicios import cultivos
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    codigos_de,
    crear_agronomo,
    crear_cultivo,
    crear_invernadero,
    crear_variedad,
    error_de,
)

BAJA = RegistroAuditoria.Accion.BAJA_CULTIVO


class ProdBajCltServicioTests(ConDatosDeMaestros, TestCase):
    """Precondiciones, reglas y postcondiciones de PROD-BAJ-CLT."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.cultivo = crear_cultivo("Lechuga")

    def baja(self, cultivo=None, actor=None):
        return cultivos.baja_cultivo(actor or self.agronomo, (cultivo or self.cultivo).pk)

    # ---- precondiciones y regla 3 ----

    def test_pre_a_un_gerente_no_da_de_baja(self):
        """PROD-BAJ-CLT precondición a: solo un Agrónomo activo."""
        with self.assertRaises(PermissionDenied):
            self.baja(actor=crear_gerente())

    def test_pre_a_un_capataz_no_da_de_baja(self):
        """PROD-BAJ-CLT precondición a."""
        with self.assertRaises(PermissionDenied):
            self.baja(actor=crear_capataz())

    def test_pre_a_un_cultivo_que_no_existe_da_404(self):
        """Un id inexistente da 404."""
        with self.assertRaises(Http404):
            cultivos.baja_cultivo(self.agronomo, 999999)

    def test_regla_3_cualquier_agronomo_da_de_baja_un_cultivo_sin_variedades_activas(self):
        """PROD-BAJ-CLT regla 3: como no tiene variedades activas, no lo usa ningún invernadero; no hay «a cargo»."""
        otro = crear_agronomo(email="otro@infoponia.com")
        crear_invernadero("Inv", agronomo=otro)
        self.assertEqual(self.baja(actor=otro).estado_cultivo, "inactivo")

    def test_pre_b_un_cultivo_ya_dado_de_baja_se_rechaza(self):
        """PROD-BAJ-CLT precondición b: el cultivo está activo."""
        inactivo = crear_cultivo("Acelga", activo=False)
        error = error_de(lambda: self.baja(cultivo=inactivo))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["cultivo_inactivo"])

    # ---- precondición c y regla 2: variedades activas ----

    def test_pre_c_con_variedades_activas_no_se_da_de_baja_y_dice_cuantas_son(self):
        """PROD-BAJ-CLT precondición c y regla 2: no permite la baja e indica cuántas variedades activas tiene."""
        crear_variedad(self.cultivo, "Crespa")
        crear_variedad(self.cultivo, "Lisa")
        error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["variedades_activas"])
        self.assertIn("2 variedades activas", error.messages[0])
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.estado_cultivo, "activo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_pre_c_con_una_sola_variedad_activa_el_mensaje_va_en_singular(self):
        """Redacción: «1 variedad activa»."""
        crear_variedad(self.cultivo, "Crespa")
        self.assertIn("1 variedad activa", error_de(self.baja).messages[0])

    def test_regla_2_las_variedades_inactivas_no_impiden_la_baja_y_no_se_tocan(self):
        """PROD-BAJ-CLT regla 1 y 2: la baja no es en cascada; el cultivo conserva sus variedades inactivas."""
        variedad = crear_variedad(self.cultivo, "Crespa", activa=False)
        self.baja()
        variedad.refresh_from_db()
        self.assertEqual(variedad.estado_variedad, "inactivo")
        self.assertEqual(variedad.cultivo_id, self.cultivo.pk)

    def test_regla_2_las_variedades_de_otro_cultivo_no_cuentan(self):
        """Las variedades se cuentan por cultivo."""
        crear_variedad(crear_cultivo("Acelga"), "Común")
        self.assertEqual(self.baja().estado_cultivo, "inactivo")

    # ---- postcondiciones ----

    def test_post_a_el_cultivo_queda_inactivo_y_conserva_su_nombre(self):
        """PROD-BAJ-CLT postcondición a y regla 1: baja lógica."""
        self.baja()
        self.cultivo.refresh_from_db()
        self.assertEqual((self.cultivo.estado_cultivo, self.cultivo.nombre_cultivo), ("inactivo", "Lechuga"))

    def test_post_a_el_cultivo_dado_de_baja_deja_de_ofrecerse_para_variedades(self):
        """PROD-BAJ-CLT postcondición a: sus acciones pasan a ser solo «reactivar» (no se le crean variedades)."""
        self.baja()
        self.cultivo.refresh_from_db()
        self.assertEqual(cultivos.acciones_permitidas(self.agronomo, self.cultivo), {"reactivar"})

    def test_post_b_audita_la_baja_con_el_cambio_de_estado(self):
        """PROD-BAJ-CLT postcondición b y D-36: usuario, rol, cultivo y cambio de estado."""
        self.baja()
        registro = RegistroAuditoria.objects.get(accion=BAJA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        self.assertEqual([a["id"] for a in registro.afectados], [self.cultivo.pk])
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "activo", "despues": "inactivo"})

    def test_regla_4_se_reactiva_con_modificar_cultivo(self):
        """PROD-BAJ-CLT regla 4: se reactiva con PROD-MOD-CLT."""
        self.baja()
        self.assertEqual(cultivos.reactivar_cultivo(self.agronomo, self.cultivo.pk).estado_cultivo, "activo")

    def test_flujo_principal_da_de_baja_y_lo_deja_como_inactivo_en_la_consulta(self):
        """PROD-BAJ-CLT, flujo principal: los activos primero y el inactivo, al final."""
        crear_cultivo("Acelga")
        self.baja()
        self.assertEqual(
            [(c.nombre_cultivo, c.estado_cultivo) for c in cultivos.consultar_cultivos(self.agronomo)],
            [("Acelga", "activo"), ("Lechuga", "inactivo")],
        )
