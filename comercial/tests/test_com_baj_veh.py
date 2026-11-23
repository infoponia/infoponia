# Pruebas de COM-BAJ-VEH, Baja Vehículo (COM-01, paso 4; docs/casos_de_uso/comercial/vehiculos.md): solo el Gerente, el vehículo activo
# y fuera de ruta, las entregas «a realizar» del transportista (se completan en COM-05: acá, con ``mock.patch``), que el vehículo
# queda inactivo y sin transportista, el aviso al transportista y la auditoría.

from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase

from comercial.models import Vehiculo
from comercial.servicios import vehiculos
from comercial.tests.fabricas import vehiculo
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.tests.fabricas import crear_agronomo, crear_transportista, crear_vendedor


def codigos_de(prueba, llamada):
    """Ejecuta ``llamada`` y devuelve los códigos de la ``ValidationError`` que lanza (generales o por campo)."""
    with prueba.assertRaises(ValidationError) as contexto:
        llamada()
    error = contexto.exception
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


class ComBajVehServicioTests(TestCase):
    """``baja_vehiculo(actor, vehiculo_id)``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        self.vehiculo = vehiculo(patente="AE123CD", transportista=self.diego)

    def baja(self, vehiculo_=None):
        return vehiculos.baja_vehiculo(self.gerente, (vehiculo_ or self.vehiculo).pk)

    def test_pre_a_solo_el_gerente_activo_puede(self):
        """Precondición a: otros roles, una cuenta inactiva o ``None`` reciben ``PermissionDenied``."""
        for actor in (crear_vendedor(), crear_agronomo(), self.diego, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                vehiculos.baja_vehiculo(actor, self.vehiculo.pk)
        self.vehiculo.refresh_from_db()
        self.assertEqual(self.vehiculo.estado_vehiculo, "activo")

    def test_pre_a_un_vehiculo_inexistente_da_404(self):
        """D-28: un id inexistente es 404."""
        with self.assertRaises(Http404):
            vehiculos.baja_vehiculo(self.gerente, 999999)

    def test_pre_b_el_vehiculo_tiene_que_estar_activo(self):
        """Precondición b: uno inactivo se rechaza con ``vehiculo_inactivo``."""
        inactivo = vehiculo(patente="ABC123", activo=False)
        self.assertEqual(codigos_de(self, lambda: self.baja(inactivo)), ["vehiculo_inactivo"])
        self.assertFalse(RegistroAuditoria.objects.filter(accion="baja_vehiculo").exists())

    def test_pre_b_un_vehiculo_en_ruta_no_se_da_de_baja(self):
        """Precondición b (MD-118): ``vehiculo_en_ruta``; no cambia nada ni avisa."""
        en_ruta = vehiculo(patente="ABC123", transportista=crear_transportista("carla@infoponia.com"), en_ruta_hoy=True)
        self.assertEqual(codigos_de(self, lambda: self.baja(en_ruta)), ["vehiculo_en_ruta"])
        en_ruta.refresh_from_db()
        self.assertEqual((en_ruta.estado_vehiculo, en_ruta.transportista_id is None), ("activo", False))
        self.assertFalse(Notificacion.objects.exists())

    def test_pre_c_con_entregas_a_realizar_no_se_da_de_baja(self):
        """Precondición c y regla 1: si el transportista tiene entregas «a realizar», ``transportista_con_entregas`` y no cambia nada."""
        with mock.patch.object(vehiculos, "entregas_a_realizar_del_transportista", return_value=["entrega"]) as entregas:
            self.assertEqual(codigos_de(self, self.baja), ["transportista_con_entregas"])
        entregas.assert_called_once()
        self.assertEqual(entregas.call_args.args[0].pk, self.diego.pk)
        self.vehiculo.refresh_from_db()
        self.assertEqual((self.vehiculo.estado_vehiculo, self.vehiculo.transportista_id), ("activo", self.diego.pk))
        self.assertFalse(Notificacion.objects.exists())

    def test_pre_c_un_vehiculo_sin_transportista_no_consulta_entregas(self):
        """Precondición c: sin transportista no hay entregas que mirar."""
        sin = vehiculo(patente="ABC123")
        with mock.patch.object(vehiculos, "entregas_a_realizar_del_transportista", return_value=["entrega"]) as entregas:
            self.baja(sin)
        entregas.assert_not_called()

    def test_post_a_queda_inactivo_y_sin_transportista_en_la_misma_escritura(self):
        """Postcondición a: «inactivo» y sin transportista (la restricción de la base lo exige)."""
        devuelto = self.baja()
        self.vehiculo.refresh_from_db()
        self.assertEqual((devuelto.pk, self.vehiculo.estado_vehiculo, self.vehiculo.transportista_id), (self.vehiculo.pk, "inactivo", None))

    def test_post_b_el_transportista_recibe_el_aviso_de_la_baja(self):
        """Postcondición b: «Tu vehículo se dio de baja»."""
        self.baja()
        aviso = Notificacion.objects.get(destinatario=self.diego)
        self.assertEqual(aviso.titulo, "Tu vehículo se dio de baja")
        self.assertEqual(
            aviso.detalle, "El vehículo AE123CD se dio de baja. No vas a recibir entregas nuevas hasta que te asignen otro."
        )
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_post_b_sin_transportista_no_se_avisa_a_nadie(self):
        """Postcondición b: «si tenía transportista»."""
        self.baja(vehiculo(patente="ABC123"))
        self.assertFalse(Notificacion.objects.exists())

    def test_post_c_audita_la_baja_con_el_estado_y_el_transportista(self):
        """Postcondición c y D-36: ``baja_vehiculo`` con el vehículo y la cuenta del transportista como afectados, el cambio de
        estado y el transportista que tenía."""
        self.baja()
        registro = RegistroAuditoria.objects.get(accion="baja_vehiculo")
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual({a["id"] for a in registro.afectados}, {self.vehiculo.pk, self.diego.pk})
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["estado"], {"antes": "activo", "despues": "inactivo"})
        self.assertEqual((cambios["transportista"]["antes"]["id"], cambios["transportista"]["despues"]), (self.diego.pk, None))

    def test_regla_2_un_vehiculo_inactivo_no_se_ofrece_para_asignarle_un_transportista(self):
        """Regla 2: un inactivo no es candidato; sus entregas pasadas conservan el vínculo con su transportista (acá, que el
        transportista queda libre para otro vehículo)."""
        self.baja()
        otro = vehiculos.alta_vehiculo(
            self.gerente,
            vehiculos.DatosDeVehiculo("ABC123", "moto", "Honda", "XR", "50", transportista_id=self.diego.pk),
        )
        self.assertEqual(otro.transportista_id, self.diego.pk)
        self.assertEqual(Vehiculo.objects.get(pk=self.vehiculo.pk).estado_vehiculo, "inactivo")
