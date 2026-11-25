# Pruebas de COM-FIN-RUT · Finalizar Ruta (COM-06a, paso 3): `rutas.finalizar_ruta` y `rutas.pendientes_de_la_ruta`. Una por regla (1 a 5) y postcondición (a a c); la ruta de ayer (vencida) no se
# finaliza; finalizar y volver a iniciar el mismo día. Fuente: docs/casos_de_uso/comercial/rutas.md («COM-FIN-RUT» y «Cómo se aplica», «Finalizar la ruta»), MD-118.

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from comercial.models import IntentoFallido, Vehiculo
from comercial.servicios import entregas, rutas
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    entrega,
    envase,
    escenario_comercial,
    reserva_lista,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.models import ReservaInsumo
from produccion.tests.fabricas import lote_maduro, reservar

HOY = timezone.localdate()


def codigos(error):
    """Los códigos de un `ValidationError` con o sin `error_dict`."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


class ComFinRutServicioTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.t = transportista_con_vehiculo(cls.e.invernadero, "800")

    def setUp(self):
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)

    def nueva(self, transportista=None):
        venta = compra_venta(self.e, dias=0)
        r = reserva_lista(detalle(venta, self.e.variedad, 10), self.lote, 10)
        return entrega(venta, [r], transportista=transportista or self.t, fecha=HOY)

    def con_ruta_iniciada(self):
        """Una entrega y la ruta iniciada. Devuelve la entrega."""
        e = self.nueva()
        rutas.iniciar_ruta(self.t, rutas.ruta_del_dia(self.t).huella)
        return e

    def vehiculo(self):
        return Vehiculo.objects.get(transportista=self.t)

    def test_regla_1_con_entregas_a_realizar_de_la_ruta_no_se_finaliza_y_se_las_muestra(self):
        """Regla 1: `ruta_con_entregas_pendientes` con los códigos de las pendientes; la pantalla las ofrece (`pendientes_de_la_ruta`); la ruta sigue iniciada."""
        e = self.con_ruta_iniciada()
        with self.assertRaises(ValidationError) as c:
            rutas.finalizar_ruta(self.t)
        self.assertEqual(codigos(c.exception), ["ruta_con_entregas_pendientes"])
        self.assertEqual(next(iter(c.exception.error_dict.values()))[0].params["pendientes"], [e.codigo])
        self.assertEqual([f.entrega.pk for f in rutas.pendientes_de_la_ruta(self.t)], [e.pk])
        self.assertTrue(self.vehiculo().esta_en_ruta(HOY))

    def test_regla_2_el_intento_fallido_registrado_desde_aca_saca_la_entrega_de_la_ruta_y_deja_finalizar(self):
        """Regla 2: el intento fallido desde la pantalla de finalizar es la misma función de 4a: la entrega pasa a mañana sin transportista, sus envases siguen reservados y ya se puede finalizar."""
        e = self.con_ruta_iniciada()
        b = envase(self.e.invernadero)
        reservar(e, b, 5)
        rutas.registrar_intento_fallido(self.t, e.pk, "cliente_ausente", "")
        self.assertEqual(rutas.pendientes_de_la_ruta(self.t), [])
        self.assertEqual(ReservaInsumo.objects.get(orden_id=e.pk).estado, "activa")
        rutas.finalizar_ruta(self.t)

    def test_post_a_el_vehiculo_deja_de_estar_en_ruta_y_conserva_la_fecha_de_inicio(self):
        """Postcondición a y regla 3: `en_ruta` pasa a falso; `fecha_inicio_ruta` queda (el transportista vuelve a ser candidato y puede iniciar otra)."""
        e = self.con_ruta_iniciada()
        rutas.registrar_intento_fallido(self.t, e.pk, "domicilio_cerrado", "")
        devuelto = rutas.finalizar_ruta(self.t)
        v = self.vehiculo()
        self.assertEqual((v.en_ruta, v.fecha_inicio_ruta, devuelto.pk), (False, HOY, v.pk))
        self.assertFalse(v.esta_en_ruta(HOY))

    def test_post_b_las_entregas_con_intento_fallido_siguen_a_realizar_para_manana_sin_transportista(self):
        """Postcondición b: cada entrega con intento fallido sigue «a realizar», con la fecha de mañana y sin transportista."""
        e = self.con_ruta_iniciada()
        rutas.registrar_intento_fallido(self.t, e.pk, "direccion_incorrecta", "Calle sin número")
        rutas.finalizar_ruta(self.t)
        e.refresh_from_db()
        self.assertEqual((e.estado_orden, e.fecha_programada_orden, e.transportista_id), ("a_realizar", HOY + timedelta(days=1), None))
        self.assertEqual(IntentoFallido.objects.get(entrega=e).descripcion, "Calle sin número")

    def test_post_c_se_audita_el_fin_de_ruta_con_los_intentos_fallidos(self):
        """Postcondición c: un registro `fin_ruta` del Transportista con el vehículo, el cambio de `en_ruta` y los intentos fallidos de la ruta."""
        e = self.con_ruta_iniciada()
        rutas.registrar_intento_fallido(self.t, e.pk, "cliente_ausente", "")
        rutas.finalizar_ruta(self.t)
        r = RegistroAuditoria.objects.get(accion="fin_ruta")
        self.assertEqual(r.usuario_id, self.t.pk)
        self.assertEqual(r.detalle["cambios"]["en_ruta"], {"antes": True, "despues": False})
        self.assertEqual(r.detalle["datos"]["intentos_fallidos"], [f"{e.codigo}: Cliente ausente"])

    def test_precondicion_b_sin_ruta_iniciada_no_hay_nada_que_finalizar(self):
        """Precondición b: sin ruta iniciada hoy, `ruta_no_iniciada`."""
        self.nueva()
        with self.assertRaises(ValidationError) as c:
            rutas.finalizar_ruta(self.t)
        self.assertEqual(codigos(c.exception), ["ruta_no_iniciada"])

    def test_regla_4_la_ruta_de_ayer_vencio_sola_y_no_se_finaliza(self):
        """Regla 4 (MD-118): una ruta que no se finalizó vence al terminar su día; al día siguiente no hay nada que finalizar (`ruta_no_iniciada`) y no se tocó el vehículo."""
        self.nueva()
        Vehiculo.objects.filter(transportista=self.t).update(en_ruta=True, fecha_inicio_ruta=HOY - timedelta(days=1))
        with self.assertRaises(ValidationError) as c:
            rutas.finalizar_ruta(self.t)
        self.assertEqual(codigos(c.exception), ["ruta_no_iniciada"])
        self.assertTrue(self.vehiculo().en_ruta)

    def test_regla_3_finalizar_y_volver_a_iniciar_el_mismo_dia(self):
        """Regla 3: al finalizar, la nueva entrega del día no está «en curso»; al iniciar otra ruta sí, y quedan dos registros `inicio_ruta`."""
        e = self.con_ruta_iniciada()
        rutas.registrar_intento_fallido(self.t, e.pk, "cliente_ausente", "")
        rutas.finalizar_ruta(self.t)
        nueva = self.nueva()
        self.assertFalse(entregas.en_curso(nueva, HOY))
        rutas.iniciar_ruta(self.t, rutas.ruta_del_dia(self.t).huella)
        self.assertTrue(entregas.en_curso(nueva, HOY))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="inicio_ruta").count(), 2)

    def test_regla_5_solo_el_transportista_finaliza_su_ruta(self):
        """Regla 5: ni el Gerente ni el Vendedor finalizan una ruta en su nombre."""
        self.con_ruta_iniciada()
        for cuenta in (crear_gerente(), self.e.vendedor):
            with self.assertRaises(PermissionDenied):
                rutas.finalizar_ruta(cuenta)
        self.assertTrue(self.vehiculo().esta_en_ruta(HOY))

    def test_regla_1_la_pendiente_de_otro_transportista_no_impide_finalizar(self):
        """Solo cuentan las entregas de la ruta propia."""
        e = self.con_ruta_iniciada()
        self.nueva(transportista=transportista_con_vehiculo(self.e.invernadero))
        rutas.registrar_intento_fallido(self.t, e.pk, "cliente_ausente", "")
        rutas.finalizar_ruta(self.t)
