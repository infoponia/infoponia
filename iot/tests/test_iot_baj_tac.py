# Pruebas de IOT-BAJ-TAC · Baja Tipo de Actuador (docs/casos_de_uso/iot/tipos_de_actuador.md, v0.2) y de lo que cita: D-36
# (auditoría) y D-72. Se escribieron ANTES que el servicio.
#
# Servicio que se prueba (iot/servicios/tipos_actuador.py), tomado del módulo dentro de cada prueba:
#   baja_tipo_actuador(actor, tipo_id) -> TipoActuador
#     - Precondición a: actor no es un Gerente activo -> PermissionDenied; un id que no existe -> Http404.
#     - Precondición b: el tipo ya está inactivo -> error general ``tipo_inactivo`` (``__all__``).
#     - Precondición c y regla 2: equipos no dados de baja del tipo -> error general ``equipos_activos`` con la cuenta y los
#       invernaderos. La cuenta ya está escrita; tiene datos desde IOT-02 (las pruebas arman los actuadores con la fábrica).
#   equipos_afectados(tipo) -> list[tuple[Invernadero, int]]

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import Accion, TipoActuador
from iot.tests import fabricas
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_invernadero, error_de

tipos = perezoso("iot.servicios.tipos_actuador")
BAJA = RegistroAuditoria.Accion.BAJA_TIPO_ACTUADOR


class IotBajTacServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-BAJ-TAC."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.tipo = fabricas.tipo_actuador("Extractor")

    def baja(self, actor=None, tipo_id=None):
        """Llama al servicio sobre el tipo de la prueba."""
        return tipos.baja_tipo_actuador(actor or self.gerente, tipo_id or self.tipo.pk)

    def equipo(self, invernadero, estado="activo"):
        """Un actuador del tipo de la prueba en el sistema del ``invernadero`` (que se crea si hace falta)."""
        sistema = invernadero.sistemas_iot.first() or fabricas.sistema(invernadero)
        return fabricas.actuador(sistema, self.tipo, estado=estado)

    # ---- precondiciones ----

    def test_pre_a_solo_el_gerente_activo_da_de_baja(self):
        """IOT-BAJ-TAC precondición a."""
        for actor in (crear_agronomo(), crear_capataz()):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.baja(actor)
        self.gerente.is_active = False
        self.gerente.save()
        with self.assertRaises(PermissionDenied):
            self.baja()
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.estado, "activo")

    def test_pre_a_un_tipo_que_no_existe_da_404(self):
        """docs/patrones/abm.md, sección 2."""
        with self.assertRaises(Http404):
            self.baja(tipo_id=999999)

    def test_pre_b_un_tipo_inactivo_no_se_da_de_baja_otra_vez(self):
        """IOT-BAJ-TAC precondición b: el tipo está activo."""
        self.baja()
        self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["tipo_inactivo"])

    def test_pre_c_un_tipo_con_equipos_no_se_da_de_baja(self):
        """IOT-BAJ-TAC precondición c, regla 2 y mensaje de «Baja»: informa cuántos son y de qué invernadero."""
        self.equipo(crear_invernadero("Invernadero Norte"))
        error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["equipos_activos"])
        self.assertEqual(
            error.error_dict[NON_FIELD_ERRORS][0].message,
            "Hay 1 equipo de este tipo en Invernadero Norte. Dalos de baja antes de dar de baja el tipo.",
        )
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.estado, "activo")

    def test_pre_c_el_mensaje_cuenta_los_equipos_y_nombra_los_invernaderos(self):
        """IOT-BAJ-TAC regla 2: con varios invernaderos, los nombra todos, por nombre (``e`` delante de una «I»)."""
        norte, sur = crear_invernadero("Invernadero Norte"), crear_invernadero("Invernadero Sur")
        self.equipo(norte)
        self.equipo(norte)
        self.equipo(sur)
        mensaje = error_de(self.baja).error_dict[NON_FIELD_ERRORS][0].message
        self.assertEqual(
            mensaje,
            "Hay 3 equipos de este tipo en Invernadero Norte e Invernadero Sur. Dalos de baja antes de dar de baja el tipo.",
        )

    def test_pre_c_con_tres_invernaderos_los_separa_con_comas(self):
        """IOT-BAJ-TAC regla 2: «A, B y C»."""
        for nombre in ("Bosque", "Campo", "Aguada"):
            self.equipo(crear_invernadero(nombre))
        mensaje = error_de(self.baja).error_dict[NON_FIELD_ERRORS][0].message
        self.assertIn("en Aguada, Bosque y Campo.", mensaje)

    def test_pre_c_un_equipo_dado_de_baja_no_cuenta(self):
        """IOT-BAJ-TAC precondición c: solo los actuadores que NO están dados de baja."""
        norte = crear_invernadero("Norte")
        self.equipo(norte, estado="inactivo")
        self.assertEqual(self.baja().estado, "inactivo")

    def test_pre_c_un_equipo_fuera_de_servicio_si_cuenta(self):
        """IOT-BAJ-TAC precondición c: «fuera de servicio» no es «dado de baja»."""
        self.equipo(crear_invernadero("Norte"), estado="fuera_de_servicio")
        self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["equipos_activos"])

    def test_pre_c_los_equipos_de_otro_tipo_no_cuentan(self):
        """IOT-BAJ-TAC precondición c: solo los de este tipo."""
        sistema = fabricas.sistema(crear_invernadero("Norte"))
        fabricas.actuador(sistema, fabricas.tipo_actuador("Otro tipo"))
        self.assertEqual(self.baja().estado, "inactivo")

    def test_pre_c_equipos_afectados_agrupa_por_invernadero_y_ordena_por_nombre(self):
        """«Cómo se aplica», «Baja»: la cuenta de equipos ya está escrita (con datos desde IOT-02)."""
        sur, norte = crear_invernadero("Sur"), crear_invernadero("Norte")
        self.equipo(sur)
        self.equipo(norte)
        self.equipo(norte)
        self.equipo(norte, estado="inactivo")
        self.assertEqual([(i.nombre_invernadero, n) for i, n in tipos.equipos_afectados(self.tipo)], [("Norte", 2), ("Sur", 1)])

    def test_pre_c_sin_equipos_la_cuenta_esta_vacia(self):
        """IOT-01: todavía no hay actuadores y ``equipos_afectados`` devuelve una lista vacía."""
        self.assertEqual(tipos.equipos_afectados(self.tipo), [])

    # ---- postcondiciones y reglas ----

    def test_post_a_el_tipo_queda_inactivo(self):
        """IOT-BAJ-TAC postcondición a: baja lógica."""
        tipo = self.baja()
        tipo.refresh_from_db()
        self.assertEqual(tipo.estado, "inactivo")

    def test_regla_1_la_baja_es_logica_y_conserva_sus_acciones(self):
        """IOT-BAJ-TAC regla 1: el tipo conserva sus acciones y su historial; nunca se borra una fila."""
        acciones = list(self.tipo.acciones.values_list("id", "estado"))
        self.baja()
        self.assertTrue(TipoActuador.objects.filter(pk=self.tipo.pk).exists())
        self.assertEqual(list(Accion.objects.filter(tipo_actuador=self.tipo).values_list("id", "estado")), acciones)

    def test_regla_3_un_tipo_dado_de_baja_se_reactiva_con_iot_mod_tac(self):
        """IOT-BAJ-TAC regla 3."""
        self.baja()
        self.assertEqual(tipos.reactivar_tipo_actuador(self.gerente, self.tipo.pk).estado, "activo")

    def test_post_b_audita_el_cambio_de_estado(self):
        """IOT-BAJ-TAC postcondición b: ``baja_tipo_actuador`` con el tipo y el cambio de estado."""
        self.baja()
        registro = RegistroAuditoria.objects.get(accion=BAJA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "activo", "despues": "inactivo"}})
        self.assertEqual(registro.afectados, [{"modelo": "iot.tipoactuador", "id": self.tipo.pk, "texto": "Extractor"}])

    def test_post_b_una_baja_rechazada_no_audita(self):
        """D-22."""
        self.equipo(crear_invernadero("Norte"))
        error_de(self.baja)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_bloquear_tipo_activo_rechaza_un_tipo_inactivo(self):
        """Contrato para IOT-02 (como ``bloquear_invernadero_activo``, D-40): quien crea un actuador bloquea el tipo antes de
        insertarlo, así la baja espera, ve el actuador y se rechaza; un tipo inactivo no se puede usar."""
        from django.db import transaction

        with transaction.atomic():
            self.assertEqual(tipos.bloquear_tipo_activo(self.tipo.pk).pk, self.tipo.pk)
        self.baja()
        with transaction.atomic():
            error = error_de(lambda: tipos.bloquear_tipo_activo(self.tipo.pk))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["tipo_inactivo"])
        with self.assertRaises(Http404):
            tipos.bloquear_tipo_activo(999999)
