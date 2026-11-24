# Pruebas del traspaso de las órdenes de mantenimiento al cambiar el Técnico del invernadero y de lo que la ventana de baja de su cuenta informa (IOT-07, paso 6): PROD-MOD-INV (regla 3, regla 2 y
# postcondiciones b y c) y USR-BAJ-USR (regla 4) para el rol Técnico. Fuentes: docs/casos_de_uso/iot/mantenimiento_automatico.md («Traspaso del Técnico», «Asignaciones de la cuenta»), D-53 (punto 5),
# D-79 (punto 9), docs/api/produccion.md (sección 3, «tres pruebas mínimas de cada registrante») y D-98 (punto 1: el aviso «recibe» va por ``contar``; ``registrar_aviso_de_traspaso`` es para lo que se cancela).
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban (iot/servicios/mantenimiento.py), registrados en ``IotConfig.ready()``:
#   contar_traspaso(invernadero, rol, saliente, entrante) -> list[(descripcion, cantidad)]     (``maestros.extensiones.registrar_traspaso``, ``contar``)
#       rol ``tecnico`` y con entrante: ``[("mantenimientos técnicos a realizar", n)]`` con las órdenes «a realizar» del invernadero que todavía no son del entrante (n > 0); si no, ``[]``.
#   traspasar_mantenimientos(actor, invernadero, rol, saliente, entrante) -> list[MantenimientoTecnico]     (``traspasar``)
#       las mismas órdenes pasan al entrante con una consulta de actualización; devuelve las tocadas (quedan entre los afectados de ``modificacion_invernadero``). Sin entrante o con otro rol, ``[]``.
#   asignaciones_del_tecnico(cuenta) -> list[Asignacion]                                       (``core.extensiones.registrar_asignaciones_de_cuenta``)
#       la cuenta de un Técnico con órdenes a realizar: ``Asignacion("Mantenimientos técnicos a realizar", n, "Pasan a quien el Gerente asigne al modificar el invernadero.")``; otra cuenta, ``[]``.

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core import extensiones as extensiones_de_core
from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import perezoso
from iot.models import MantenimientoTecnico
from iot.tests import fabricas
from iot.tests.test_iot_rsv_cmd_mantenimiento import Escena
from maestros import extensiones as extensiones_de_maestros
from maestros.servicios import invernaderos
from maestros.tests.fabricas import crear_capataz_activo, crear_invernadero, crear_tecnico
from maestros.tests.test_prod_mod_inv import datos_de

mantenimiento = perezoso("iot.servicios.mantenimiento")
RECIBE = "mantenimientos técnicos a realizar"


def consultas(llamada):
    """Cuántas consultas hace ``llamada()``."""
    with CaptureQueriesContext(connection) as capturadas:
        llamada()
    return len(capturadas)


class Base(Escena, TestCase):
    """Norte con su Técnico, su Agrónomo y una orden «a realizar» del actuador, más un Técnico nuevo para asignar."""

    def setUp(self):
        super().setUp()
        self.nuevo = crear_tecnico("nuevo@infoponia.com", nombre="Nora", apellido="Paz")
        self.orden = self.otra_orden()

    def otra_orden(self, tecnico=None, invernadero=None, equipos=None, **extra):
        return fabricas.mantenimiento_tecnico(invernadero or self.norte, tecnico or self.tecnico, equipos or [self.actuador], **extra)

    def modificar(self, confirmado=True, **cambios):
        """Modifica Norte como el Gerente (el formulario completo, con lo que no cambia igual); ``cambios`` pisa el personal."""
        self.norte.refresh_from_db()
        datos = datos_de(self.norte) | cambios | {"personal_confirmado": confirmado}
        return invernaderos.modificar_invernadero(self.gerente, self.norte.pk, **datos)

    def tecnico_de(self, orden):
        orden.refresh_from_db()
        return orden.tecnico_id


class TraspasoPorModificarElInvernaderoTests(Base):
    """PROD-MOD-INV, regla 3 y postcondiciones b y c: el cambio de Técnico del invernadero."""

    def test_post_b_las_ordenes_a_realizar_pasan_al_tecnico_nuevo(self):
        self.modificar(tecnico_id=self.nuevo.pk)
        self.assertEqual(self.tecnico_de(self.orden), self.nuevo.pk)

    def test_post_b_las_canceladas_y_las_concretadas_no_pasan(self):
        cancelada = self.otra_orden(estado="cancelada")
        concretada = self.otra_orden(estado="concretada")
        self.modificar(tecnico_id=self.nuevo.pk)
        self.assertEqual((self.tecnico_de(cancelada), self.tecnico_de(concretada)), (self.tecnico.pk, self.tecnico.pk))

    def test_post_b_pasan_todas_las_del_invernadero_no_solo_las_del_saliente(self):
        """D-79, punto 9: «queda sin responsable y pasa a quien se asigne después»: también las que eran de otro Técnico."""
        de_otro = self.otra_orden(tecnico=crear_tecnico("otro.tecnico@infoponia.com"))
        self.modificar(tecnico_id=self.nuevo.pk)
        self.assertEqual((self.tecnico_de(self.orden), self.tecnico_de(de_otro)), (self.nuevo.pk, self.nuevo.pk))

    def test_post_b_las_ordenes_de_otro_invernadero_no_cambian(self):
        sur = crear_invernadero("Sur", agronomo=self.laura, tecnico=self.tecnico)
        equipo = fabricas.actuador(fabricas.sistema(sur), self.tipo, "sur/extractor")
        ajena = self.otra_orden(invernadero=sur, equipos=[equipo])
        self.modificar(tecnico_id=self.nuevo.pk)
        self.assertEqual(self.tecnico_de(ajena), self.tecnico.pk)

    def test_post_b_con_el_rol_vacio_y_despues_un_tecnico_nuevo_las_recibe_el_nuevo(self):
        """Sin entrante no cambia nada (`tecnico` es obligatorio: la orden queda con el Técnico anterior); cuando después se asigna uno, le pasan."""
        self.modificar(tecnico_id=None)
        self.assertEqual(self.tecnico_de(self.orden), self.tecnico.pk)
        self.modificar(tecnico_id=self.nuevo.pk)
        self.assertEqual(self.tecnico_de(self.orden), self.nuevo.pk)

    def test_post_b_el_cambio_de_capataz_no_las_toca(self):
        self.modificar(capataz_id=crear_capataz_activo().pk)
        self.assertEqual(self.tecnico_de(self.orden), self.tecnico.pk)

    def test_post_b_un_cambio_que_no_es_de_personal_no_las_toca(self):
        self.modificar(nombre="Norte 2")
        self.assertEqual(self.tecnico_de(self.orden), self.tecnico.pk)

    def test_post_c_el_aviso_al_tecnico_nuevo_dice_los_mantenimientos_que_recibe(self):
        """Postcondición c: «Recibe: mantenimientos técnicos a realizar: 1.» (por ``contar``, no por ``registrar_aviso_de_traspaso``)."""
        self.otra_orden()
        self.modificar(tecnico_id=self.nuevo.pk)
        (aviso,) = Notificacion.objects.filter(destinatario=self.nuevo)
        self.assertEqual(aviso.titulo, "Quedó a cargo de Norte")
        self.assertIn(f"{RECIBE}: 2", aviso.detalle)

    def test_regla_2_la_ventana_de_confirmacion_informa_lo_que_recibe_el_tecnico_nuevo(self):
        """Regla 2: antes de guardar, el aviso de la ventana trae lo que recibiría la persona entrante."""
        with self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
            self.modificar(confirmado=False, tecnico_id=self.nuevo.pk)
        (entrada,) = [e for e in contexto.exception.aviso if e["rol"] == "tecnico"]
        self.assertEqual(entrada["recibe"], [(RECIBE, 1)])
        self.assertEqual(self.tecnico_de(self.orden), self.tecnico.pk)  # no se guardó nada

    def test_regla_2_el_aviso_de_lo_que_se_cancela_no_incluye_a_los_mantenimientos(self):
        """D-98, punto 1: los mantenimientos no se cancelan: pasan. No van por ``avisos_de_traspaso``."""
        with self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
            self.modificar(confirmado=False, tecnico_id=self.nuevo.pk)
        (entrada,) = [e for e in contexto.exception.aviso if e["rol"] == "tecnico"]
        self.assertFalse(any("mantenimiento" in texto for texto in entrada["avisos"]))

    def test_post_f_la_orden_queda_entre_los_afectados_de_modificacion_invernadero(self):
        """D-36 y D-81: lo que tocó el registrante queda entre los afectados del único registro."""
        self.modificar(tecnico_id=self.nuevo.pk)
        registro = RegistroAuditoria.objects.filter(accion="modificacion_invernadero").latest("pk")
        self.assertIn(("iot.mantenimientotecnico", self.orden.pk), [(a["modelo"], a["id"]) for a in registro.afectados])

    def test_ext_el_traspaso_esta_registrado_una_sola_vez(self):
        registrado = (mantenimiento.contar_traspaso, mantenimiento.traspasar_mantenimientos)
        self.assertEqual(extensiones_de_maestros._TRASPASOS.count(registrado), 1)


class RegistranteDeTraspasoTests(Base):
    """Las tres pruebas mínimas de cada registrante (docs/api/produccion.md, sección 3): con datos, neutro sin datos y sin consultas por fila."""

    def test_contar_con_datos(self):
        self.otra_orden()
        self.assertEqual(mantenimiento.contar_traspaso(self.norte, "tecnico", self.tecnico, self.nuevo), [(RECIBE, 2)])

    def test_contar_no_cuenta_las_que_ya_son_del_entrante(self):
        self.otra_orden(tecnico=self.nuevo)
        self.assertEqual(mantenimiento.contar_traspaso(self.norte, "tecnico", self.tecnico, self.nuevo), [(RECIBE, 1)])

    def test_contar_neutro_sin_datos(self):
        """Neutro: otro rol, sin entrante o sin órdenes «a realizar»: lista vacía."""
        self.assertEqual(mantenimiento.contar_traspaso(self.norte, "capataz", None, crear_capataz_activo()), [])
        self.assertEqual(mantenimiento.contar_traspaso(self.norte, "tecnico", self.tecnico, None), [])
        type(self.orden).objects.filter(pk=self.orden.pk).update(estado_orden="cancelada", fecha_resolucion_orden=self.orden.fecha_programada_orden, motivo_cancelacion="x")
        self.assertEqual(mantenimiento.contar_traspaso(self.norte, "tecnico", self.tecnico, self.nuevo), [])

    def test_contar_sin_consultas_por_fila(self):
        con_una = consultas(lambda: mantenimiento.contar_traspaso(self.norte, "tecnico", self.tecnico, self.nuevo))
        for _ in range(4):
            self.otra_orden()
        self.assertEqual(con_una, consultas(lambda: mantenimiento.contar_traspaso(self.norte, "tecnico", self.tecnico, self.nuevo)))

    def test_traspasar_con_datos_devuelve_lo_que_toco(self):
        otra = self.otra_orden()
        tocadas = mantenimiento.traspasar_mantenimientos(self.gerente, self.norte, "tecnico", self.tecnico, self.nuevo)
        self.assertEqual(sorted(o.pk for o in tocadas), sorted([self.orden.pk, otra.pk]))
        self.assertEqual((self.tecnico_de(self.orden), self.tecnico_de(otra)), (self.nuevo.pk, self.nuevo.pk))

    def test_traspasar_neutro_sin_datos(self):
        self.assertEqual(mantenimiento.traspasar_mantenimientos(self.gerente, self.norte, "capataz", None, crear_capataz_activo()), [])
        self.assertEqual(mantenimiento.traspasar_mantenimientos(self.gerente, self.norte, "tecnico", self.tecnico, None), [])
        self.assertEqual(self.tecnico_de(self.orden), self.tecnico.pk)
        mantenimiento.traspasar_mantenimientos(self.gerente, self.norte, "tecnico", self.tecnico, self.nuevo)
        self.assertEqual(mantenimiento.traspasar_mantenimientos(self.gerente, self.norte, "tecnico", self.nuevo, self.nuevo), [])  # ya son suyas

    def test_traspasar_sin_consultas_por_fila(self):
        """Una cantidad fija de consultas al pasar 1 orden y al pasar 6 (una consulta de actualización, no una por orden)."""
        con_una = consultas(lambda: mantenimiento.traspasar_mantenimientos(self.gerente, self.norte, "tecnico", self.tecnico, self.nuevo))
        otro = crear_tecnico("tercero@infoponia.com")
        for _ in range(5):
            self.otra_orden(tecnico=otro)
        con_seis = consultas(lambda: mantenimiento.traspasar_mantenimientos(self.gerente, self.norte, "tecnico", self.nuevo, self.tecnico))
        self.assertEqual(con_una, con_seis)
        self.assertEqual(MantenimientoTecnico.objects.exclude(tecnico=self.tecnico).count(), 0)


class AsignacionesDeLaCuentaTests(Base):
    """USR-BAJ-USR, regla 4 y D-79 punto 9: lo que la ventana de baja de la cuenta de un Técnico informa."""

    ESPERADA = ("Mantenimientos técnicos a realizar", "Pasan a quien el Gerente asigne al modificar el invernadero.")

    def test_regla_4_con_datos_la_ventana_informa_los_mantenimientos_a_realizar(self):
        self.otra_orden()
        (asignacion,) = mantenimiento.asignaciones_del_tecnico(self.tecnico)
        self.assertEqual((asignacion.texto, asignacion.que_pasa), self.ESPERADA)
        self.assertEqual(asignacion.cantidad, 2)

    def test_regla_4_no_cuenta_las_canceladas_ni_las_de_otro_tecnico(self):
        self.otra_orden(estado="cancelada")
        self.otra_orden(tecnico=self.nuevo)
        self.assertEqual([a.cantidad for a in mantenimiento.asignaciones_del_tecnico(self.tecnico)], [1])

    def test_regla_4_neutro_para_otras_cuentas_y_sin_ordenes(self):
        self.assertEqual(mantenimiento.asignaciones_del_tecnico(self.laura), [])
        self.assertEqual(mantenimiento.asignaciones_del_tecnico(self.gerente), [])
        self.assertEqual(mantenimiento.asignaciones_del_tecnico(self.nuevo), [])

    def test_regla_4_sin_consultas_por_fila(self):
        con_una = consultas(lambda: mantenimiento.asignaciones_del_tecnico(self.tecnico))
        for _ in range(4):
            self.otra_orden()
        self.assertEqual(con_una, consultas(lambda: mantenimiento.asignaciones_del_tecnico(self.tecnico)))

    def test_regla_4_esta_registrada_una_sola_vez_y_la_junta_core(self):
        self.assertEqual(extensiones_de_core._ASIGNACIONES_DE_CUENTA.count(mantenimiento.asignaciones_del_tecnico), 1)
        textos = [a.texto for a in extensiones_de_core.asignaciones_de_cuenta(self.tecnico)]
        self.assertIn("Mantenimientos técnicos a realizar", textos)
