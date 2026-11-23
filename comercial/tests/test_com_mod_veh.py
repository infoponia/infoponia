# Pruebas de COM-MOD-VEH, Modificar Vehículo, con su reactivación (COM-01, paso 4; docs/casos_de_uso/comercial/vehiculos.md): los
# datos, la patente, el vehículo en ruta, el vehículo inactivo (solo se reactiva), la capacidad contra la carga asignada y el cambio de
# transportista contra sus entregas «a realizar» (las dos se completan en COM-05: acá, con ``mock.patch``), las notificaciones y la
# auditoría.
#
# ``modificar_vehiculo(actor, vehiculo_id, datos)`` (``datos`` es el mismo ``DatosDeVehiculo`` del alta; ``transportista_id`` vacío
# lo quita) y ``reactivar_vehiculo(actor, vehiculo_id)``. Códigos nuevos: ``vehiculo_en_ruta`` y ``vehiculo_inactivo`` (generales),
# ``capacidad_menor_que_la_carga`` (en ``capacidad_carga``), ``transportista_con_entregas`` (en ``transportista``) y
# ``vehiculo_no_inactivo`` (al reactivar uno activo).

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from comercial.models import Vehiculo
from comercial.servicios import vehiculos
from comercial.tests.fabricas import datos_de_vehiculo_de, vehiculo
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.tests.fabricas import crear_agronomo, crear_transportista, crear_vendedor

EN_RUTA = "El vehículo está en ruta: el producto de las entregas de hoy está cargado. Podés modificarlo o darlo de baja cuando finalice la ruta."


def errores_de(prueba, llamada):
    """Ejecuta ``llamada`` y devuelve los errores que lanza como ``{campo: [ValidationError]}``."""
    with prueba.assertRaises(ValidationError) as contexto:
        llamada()
    return contexto.exception


def codigos(error, campo=None):
    """Los códigos de una ``ValidationError``; con ``campo``, solo los de ese campo."""
    if campo is None:
        return [e.code for e in error.error_list] if not hasattr(error, "error_dict") else [
            e.code for lista in error.error_dict.values() for e in lista
        ]
    return [e.code for e in error.error_dict.get(campo, [])]


def avisos(cuenta):
    """Las notificaciones de ``cuenta`` como ``[(título, detalle)]``, de la más vieja a la más nueva."""
    return [(n.titulo, n.detalle) for n in Notificacion.objects.filter(destinatario=cuenta).order_by("id")]


class ComModVehServicioTests(TestCase):
    """``modificar_vehiculo(actor, vehiculo_id, datos)``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        self.carla = crear_transportista("carla@infoponia.com", nombre="Carla", apellido="Sosa")
        self.vehiculo = vehiculo(patente="AE123CD", capacidad="800", transportista=self.diego)

    def modificar(self, vehiculo_=None, **extra):
        vehiculo_ = vehiculo_ or self.vehiculo
        vehiculo_.refresh_from_db()
        return vehiculos.modificar_vehiculo(self.gerente, vehiculo_.pk, datos_de_vehiculo_de(vehiculo_, **extra))

    def auditoria(self):
        return RegistroAuditoria.objects.filter(accion="modificacion_vehiculo")

    # -- precondiciones --

    def test_pre_a_solo_el_gerente_activo_puede(self):
        """Precondición a: otros roles, una cuenta inactiva o ``None`` reciben ``PermissionDenied``."""
        for actor in (crear_vendedor(), crear_agronomo(), self.diego, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                vehiculos.modificar_vehiculo(actor, self.vehiculo.pk, datos_de_vehiculo_de(self.vehiculo))

    def test_pre_a_un_vehiculo_inexistente_da_404(self):
        """D-28: un id inexistente es 404."""
        with self.assertRaises(Http404):
            vehiculos.modificar_vehiculo(self.gerente, 999999, datos_de_vehiculo_de(self.vehiculo))

    def test_pre_b_un_vehiculo_en_ruta_no_se_modifica(self):
        """Precondición b (MD-118): ``vehiculo_en_ruta`` con el texto del extracto; no cambia nada."""
        en_ruta = vehiculo(en_ruta_hoy=True)
        error = errores_de(self, lambda: self.modificar(en_ruta, marca="Fiat"))
        self.assertEqual(codigos(error), ["vehiculo_en_ruta"])
        self.assertEqual(error.messages, [EN_RUTA])
        en_ruta.refresh_from_db()
        self.assertEqual(en_ruta.marca, "Ford")

    def test_pre_b_una_ruta_de_ayer_sin_finalizar_ya_no_impide_modificar(self):
        """MD-118: la ruta que no se finalizó deja de estar vigente al terminar el día."""
        de_ayer = vehiculo(patente="ABC123")
        Vehiculo.objects.filter(pk=de_ayer.pk).update(en_ruta=True, fecha_inicio_ruta=timezone.localdate() - timedelta(days=1))
        self.assertEqual(self.modificar(de_ayer, marca="Fiat").marca, "Fiat")

    def test_pre_c_la_patente_nueva_no_puede_ser_la_de_otro_vehiculo(self):
        """Precondición c: ``patente_repetida`` con la patente de otro vehículo, activo o inactivo; la propia no cuenta."""
        vehiculo(patente="ABC123")
        vehiculo(patente="XYZ789", activo=False)
        for patente in ("abc-123", "XYZ 789"):
            with self.subTest(patente=patente):
                self.assertEqual(codigos(errores_de(self, lambda: self.modificar(patente=patente)), "patente"), ["patente_repetida"])
        self.assertEqual(self.modificar(patente="ae 123 cd", marca="Fiat").marca, "Fiat")

    def test_pre_c_la_patente_se_puede_cambiar_a_una_libre_y_se_audita(self):
        """Precondición c (el prototipo la muestra fija: manda el CU): cambiar la patente a una libre."""
        self.modificar(patente="ab-999-cd")
        self.vehiculo.refresh_from_db()
        self.assertEqual(self.vehiculo.patente, "AB999CD")
        self.assertEqual(self.auditoria().get().detalle["cambios"]["patente"], {"antes": "AE123CD", "despues": "AB999CD"})

    def test_regla_1_los_datos_siguen_las_reglas_del_alta(self):
        """Regla 1: patente, tipo, marca, modelo y capacidad se validan igual que en el alta, todos a la vez."""
        error = errores_de(self, lambda: self.modificar(patente="x", tipo_vehiculo="", marca="", capacidad_carga="0"))
        self.assertEqual(set(error.error_dict), {"patente", "tipo_vehiculo", "marca", "capacidad_carga"})

    # -- postcondición a y d --

    def test_post_a_actualiza_los_datos_indicados(self):
        """Postcondición a: se actualizaron los datos indicados."""
        self.modificar(tipo_vehiculo="furgon", marca="Fiat", modelo="Ducato", capacidad_carga="1250,25")
        self.vehiculo.refresh_from_db()
        self.assertEqual(
            (self.vehiculo.tipo_vehiculo, self.vehiculo.marca, self.vehiculo.modelo, self.vehiculo.capacidad_carga),
            ("furgon", "Fiat", "Ducato", Decimal("1250.25")),
        )

    def test_d28_sin_cambios_no_se_escribe_ni_se_audita_ni_se_notifica(self):
        """D-28: si nada cambia, no hay registro de auditoría ni notificaciones."""
        self.modificar()
        self.assertFalse(self.auditoria().exists())
        self.assertFalse(Notificacion.objects.exists())

    def test_post_d_audita_con_el_vehiculo_y_los_cambios_antes_y_despues(self):
        """Postcondición d y D-36: ``modificacion_vehiculo``; la capacidad va como texto con dos decimales."""
        self.modificar(capacidad_carga="900", marca="Fiat")
        registro = self.auditoria().get()
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual([afectado["id"] for afectado in registro.afectados], [self.vehiculo.pk])
        self.assertEqual(
            registro.detalle["cambios"],
            {"marca": {"antes": "Ford", "despues": "Fiat"}, "capacidad_carga": {"antes": "800,00", "despues": "900,00"}},
        )

    # -- regla 4 (inactivo) y reactivación --

    def test_regla_4_un_vehiculo_inactivo_no_se_modifica_solo_se_reactiva(self):
        """Regla 4: ``vehiculo_inactivo``; no cambia nada."""
        inactivo = vehiculo(patente="ABC123", activo=False)
        error = errores_de(self, lambda: self.modificar(inactivo, marca="Fiat"))
        self.assertEqual(codigos(error), ["vehiculo_inactivo"])
        self.assertFalse(self.auditoria().exists())

    def test_post_c_reactivar_deja_el_vehiculo_activo_y_sin_transportista(self):
        """Postcondición c: «activo», sin transportista; ``reactivacion_vehiculo`` con el cambio de estado."""
        inactivo = vehiculo(patente="ABC123", activo=False)
        devuelto = vehiculos.reactivar_vehiculo(self.gerente, inactivo.pk)
        inactivo.refresh_from_db()
        self.assertEqual((devuelto.pk, inactivo.estado_vehiculo, inactivo.transportista_id), (inactivo.pk, "activo", None))
        registro = RegistroAuditoria.objects.get(accion="reactivacion_vehiculo")
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "inactivo", "despues": "activo"}})
        self.assertEqual([afectado["id"] for afectado in registro.afectados], [inactivo.pk])
        self.assertFalse(Notificacion.objects.exists())

    def test_post_c_despues_de_reactivarlo_se_modifica_y_se_le_asigna_un_transportista(self):
        """Regla 4: «Después de reactivarlo, se modifica como cualquier otro y se le puede asignar un transportista»."""
        inactivo = vehiculo(patente="ABC123", activo=False)
        vehiculos.reactivar_vehiculo(self.gerente, inactivo.pk)
        self.modificar(inactivo, transportista_id=self.carla.pk)
        inactivo.refresh_from_db()
        self.assertEqual(inactivo.transportista_id, self.carla.pk)

    def test_post_c_solo_se_reactiva_uno_inactivo_y_solo_el_gerente(self):
        """Reactivar un activo es ``vehiculo_no_inactivo``; otros roles, ``PermissionDenied``; inexistente, 404."""
        self.assertEqual(codigos(errores_de(self, lambda: vehiculos.reactivar_vehiculo(self.gerente, self.vehiculo.pk))), ["vehiculo_no_inactivo"])
        inactivo = vehiculo(patente="ABC123", activo=False)
        for actor in (crear_vendedor(), crear_agronomo(), None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                vehiculos.reactivar_vehiculo(actor, inactivo.pk)
        with self.assertRaises(Http404):
            vehiculos.reactivar_vehiculo(self.gerente, 999999)

    # -- regla 2 (capacidad contra la carga asignada: COM-05) --

    def test_regla_2_no_se_baja_la_capacidad_por_debajo_de_la_carga_asignada(self):
        """Regla 2: si ``carga_maxima_asignada`` informa más que la capacidad nueva, ``capacidad_menor_que_la_carga`` con la fecha
        con más carga; se la consulta con el vehículo y la fecha de hoy («de hoy en adelante»)."""
        hoy = timezone.localdate()
        with mock.patch.object(vehiculos, "carga_maxima_asignada", return_value=(Decimal("500"), date(2026, 12, 1))) as carga:
            error = errores_de(self, lambda: self.modificar(capacidad_carga="400"))
        carga.assert_called_once()
        self.assertEqual(carga.call_args.args[1], hoy)
        self.assertEqual(codigos(error, "capacidad_carga"), ["capacidad_menor_que_la_carga"])
        self.assertIn("01/12/2026", error.error_dict["capacidad_carga"][0].messages[0])
        self.assertIn("500", error.error_dict["capacidad_carga"][0].messages[0])
        self.vehiculo.refresh_from_db()
        self.assertEqual(self.vehiculo.capacidad_carga, Decimal("800.00"))

    def test_regla_2_se_puede_bajar_hasta_la_carga_asignada_o_dejarla_igual_o_subirla(self):
        """Regla 2: hasta el peso ya asignado se puede; si no baja, ni se consulta."""
        with mock.patch.object(vehiculos, "carga_maxima_asignada", return_value=(Decimal("500"), date(2026, 12, 1))) as carga:
            self.assertEqual(Vehiculo.objects.get(pk=self.modificar(capacidad_carga="500").pk).capacidad_carga, Decimal("500.00"))
            carga.assert_called_once()
            carga.reset_mock()
            self.modificar(capacidad_carga="900")
            self.modificar(marca="Fiat")
            carga.assert_not_called()

    def test_regla_2_un_vehiculo_sin_transportista_no_tiene_carga_asignada(self):
        """Regla 2: la carga es la de las entregas de su transportista; sin transportista no se consulta."""
        sin = vehiculo(patente="ABC123", capacidad="800")
        with mock.patch.object(vehiculos, "carga_maxima_asignada", return_value=(Decimal("500"), date(2026, 12, 1))) as carga:
            self.modificar(sin, capacidad_carga="100")
        carga.assert_not_called()

    def test_regla_2_carga_maxima_asignada_devuelve_cero_y_sin_fecha_en_com_01(self):
        """«Carga asignada» (cómo se aplica): en COM-01, ``(0, None)``; COM-05 le pone la consulta real."""
        self.assertEqual(vehiculos.carga_maxima_asignada(self.vehiculo, date.today()), (Decimal("0"), None))

    # -- regla 3 (entregas a realizar: COM-05) y postcondición b (transportista) --

    def test_regla_3_no_se_quita_ni_se_cambia_el_transportista_con_entregas_a_realizar(self):
        """Regla 3: ``transportista_con_entregas`` al quitarlo o cambiarlo si ``entregas_a_realizar_del_transportista`` no es vacía."""
        for nuevo in (None, self.carla.pk):
            with self.subTest(transportista_id=nuevo):
                with mock.patch.object(vehiculos, "entregas_a_realizar_del_transportista", return_value=["entrega"]) as entregas:
                    error = errores_de(self, lambda: self.modificar(transportista_id=nuevo))
                entregas.assert_called_once()
                self.assertEqual(entregas.call_args.args[0].pk, self.diego.pk)
                self.assertEqual(codigos(error, "transportista"), ["transportista_con_entregas"])
                self.vehiculo.refresh_from_db()
                self.assertEqual(self.vehiculo.transportista_id, self.diego.pk)
        self.assertFalse(Notificacion.objects.exists())

    def test_regla_3_si_no_cambia_el_transportista_ni_se_consulta(self):
        """Regla 3: dejarlo igual, o asignar uno a un vehículo que no tenía, no consulta las entregas."""
        sin = vehiculo(patente="ABC123")
        with mock.patch.object(vehiculos, "entregas_a_realizar_del_transportista", return_value=["entrega"]) as entregas:
            self.modificar(marca="Fiat")
            self.modificar(sin, transportista_id=self.carla.pk)
        entregas.assert_not_called()

    def test_regla_3_entregas_a_realizar_devuelve_una_lista_vacia_en_com_01(self):
        """«Entregas a realizar»: en COM-01, lista vacía; COM-05 le pone la consulta real."""
        self.assertEqual(vehiculos.entregas_a_realizar_del_transportista(self.diego), [])

    def test_post_b_asignar_un_transportista_le_avisa_al_entrante(self):
        """Postcondición b: el entrante recibe «Tenés un vehículo asignado»."""
        sin = vehiculo(patente="ABC123", tipo="furgon", capacidad="1250.5")
        self.modificar(sin, transportista_id=self.carla.pk)
        self.assertEqual(
            avisos(self.carla), [("Tenés un vehículo asignado", "Desde ahora hacés tus entregas con furgón ABC123 (1.250,5 kg).")]
        )

    def test_post_b_cambiar_el_transportista_avisa_al_entrante_y_al_saliente(self):
        """Postcondición b: el entrante recibe el aviso de asignación y el saliente «Ya no tenés el vehículo {patente}»."""
        self.modificar(transportista_id=self.carla.pk)
        self.vehiculo.refresh_from_db()
        self.assertEqual(self.vehiculo.transportista_id, self.carla.pk)
        self.assertEqual(
            avisos(self.diego),
            [("Ya no tenés el vehículo AE123CD", "No vas a recibir entregas con envío hasta que te asignen otro vehículo.")],
        )
        self.assertEqual(avisos(self.carla)[0][0], "Tenés un vehículo asignado")
        self.assertEqual(Notificacion.objects.count(), 2)

    def test_post_b_quitar_el_transportista_solo_avisa_al_saliente(self):
        """Postcondición b: sin entrante, solo el saliente recibe aviso; el vehículo queda sin transportista."""
        self.modificar(transportista_id="")
        self.vehiculo.refresh_from_db()
        self.assertIsNone(self.vehiculo.transportista_id)
        self.assertEqual(Notificacion.objects.count(), 1)
        self.assertEqual(avisos(self.diego)[0][0], "Ya no tenés el vehículo AE123CD")

    def test_post_b_cambiar_otros_datos_no_avisa_al_transportista(self):
        """Postcondición b: si el transportista no cambia, no se le avisa."""
        self.modificar(marca="Fiat")
        self.assertFalse(Notificacion.objects.exists())

    def test_regla_4_de_alt_el_transportista_nuevo_tiene_que_ser_valido_y_estar_libre(self):
        """Regla 4 de ALT (vale en MOD): activo y sin otro vehículo (``transportista_con_vehiculo``); el actual se acepta."""
        ocupado = vehiculo(patente="ABC123", transportista=self.carla)
        self.assertEqual(codigos(errores_de(self, lambda: self.modificar(transportista_id=self.carla.pk)), "transportista"), ["transportista_con_vehiculo"])
        inactivo = crear_transportista("inactivo@infoponia.com", activo=False)
        self.assertEqual(codigos(errores_de(self, lambda: self.modificar(transportista_id=inactivo.pk)), "transportista"), ["transportista_invalido"])
        self.modificar(transportista_id=self.diego.pk, marca="Fiat")  # el actual, aunque cambie otra cosa
        self.assertEqual(ocupado.transportista_id, self.carla.pk)

    def test_regla_4_de_alt_el_transportista_actual_se_conserva_aunque_su_cuenta_este_inactiva(self):
        """Regla 4 de ALT: «más el actual, en MOD»: si no se lo cambia, una cuenta inactiva no impide modificar otros datos."""
        Vehiculo.objects.filter(pk=self.vehiculo.pk).update(transportista=self.diego)
        self.diego.is_active = False
        self.diego.save()
        self.assertEqual(self.modificar(marca="Fiat").marca, "Fiat")

    def test_post_d_audita_el_cambio_de_transportista_con_las_dos_cuentas(self):
        """Postcondición d: afectados el vehículo y las cuentas del saliente y del entrante; el cambio de transportista con referencias."""
        self.modificar(transportista_id=self.carla.pk)
        registro = self.auditoria().get()
        self.assertEqual({a["id"] for a in registro.afectados}, {self.vehiculo.pk, self.diego.pk, self.carla.pk})
        cambio = registro.detalle["cambios"]["transportista"]
        self.assertEqual((cambio["antes"]["id"], cambio["despues"]["id"]), (self.diego.pk, self.carla.pk))
        self.modificar(transportista_id="")
        quitado = self.auditoria().order_by("id").last().detalle["cambios"]["transportista"]
        self.assertEqual((quitado["antes"]["id"], quitado["despues"]), (self.carla.pk, None))
