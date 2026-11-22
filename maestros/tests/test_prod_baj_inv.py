# Pruebas de PROD-BAJ-INV · Baja Invernadero (docs/casos_de_uso/maestros/invernaderos.md) y de lo que cita: D-22 (auditoría
# en la misma transacción), D-36 (formato del detalle), D-37 (puntos de extensión, regla A4) y D-38 (sin alertas ni
# notificaciones). Modelo de dominio: ronda 22 (docs/modelo/maestros.md).
#
# Servicios que se prueban (maestros/servicios/invernaderos.py), tomados del módulo dentro de cada prueba:
#   baja_invernadero(actor, invernadero_id) -> Invernadero
#     - Precondición a: actor no es un Gerente activo -> PermissionDenied. Un id inexistente -> Http404.
#     - Precondición b: el invernadero está inactivo -> ValidationError general, código ``invernadero_inactivo``.
#     - Regla 2: si algún registrante de maestros.extensiones declara un impedimento, ValidationError general con UN error
#       por impedimento (código = ``Impedimento.codigo``, mensaje = texto + cómo resolverlo); no cambia nada.
#   impedimentos_para_baja(actor, invernadero_id) -> list[Impedimento]: solo lectura, para la ventana de confirmación.
#   bloquear_invernadero_activo(invernadero_id) -> Invernadero: contrato de los puntos de extensión (D-37, A4): bloquea el
#     invernadero y rechaza uno inactivo con ``invernadero_inactivo``.
# Puntos de extensión que se prueban con registrantes falsos (maestros/extensiones.py): ``_IMPEDIMENTOS`` (funciones
# ``f(invernadero) -> list[Impedimento]``) y ``_EFECTOS_DE_BAJA`` (funciones ``f(actor, invernadero)``).
#
# La precondición g (transportistas activos, regla 3 y D-39) la prueba ``ProdBajInvTransportistasTests`` (MAE-05, D-55): es un
# impedimento propio de `maestros`, que lee ``TransportistaInvernadero``, y no un registrante. Su cruce de concurrencia con
# agregar un Transportista está en ``test_transportistas_concurrencia.py``.
#
# Sin prueba por ahora, con su disparador (D-38, D-39 y «Límites» de MAE-01b): las postcondiciones b y c y los logs por
# sector e insumo de la f (los hacen los registrantes cuando existan sus clases). Las pruebas de vista y de concurrencia
# se agregan después de la pausa de revisión.

from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.http import Http404
from django.test import TestCase, TransactionTestCase, tag
from django.urls import reverse

from core.models import RegistroAuditoria, Usuario
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from maestros import extensiones
from maestros.extensiones import Impedimento
from maestros.alertas import Clase
from maestros.models import Alerta, Direccion, Invernadero
from maestros.servicios import alertas, invernaderos
from maestros.tests.fabricas import (
    ConGeoref,
    crear_agronomo,
    crear_alerta,
    crear_capataz_activo,
    crear_invernadero,
    asignar_transportista,
    crear_invernadero_con_geografia_propia,
    crear_transportista,
    tipo_de_alerta_de_prueba,
    tipo_falso,
)

BAJA = RegistroAuditoria.Accion.BAJA_INVERNADERO


class FallaDePrueba(Exception):
    """Falla propia de las pruebas: no es un ``RuntimeError``, para que un ``NotImplementedError`` (que sí lo es)
    no haga pasar por casualidad una prueba que espera que algo falle."""


def impedimento(codigo="lotes_activos", texto="Tiene 2 lotes activos.", como="Cosechalos o registrá su merma."):
    """Un impedimento de prueba."""
    return Impedimento(codigo, texto, como)


def con_impedimentos(*funciones):
    """Reemplaza la lista de registrantes de impedimentos por ``funciones``."""
    return mock.patch.object(extensiones, "_IMPEDIMENTOS", list(funciones))


def con_efectos(*funciones):
    """Reemplaza la lista de registrantes de efectos de la baja por ``funciones``."""
    return mock.patch.object(extensiones, "_EFECTOS_DE_BAJA", list(funciones))


def error_de(llamada):
    """Ejecuta ``llamada`` y devuelve la ``ValidationError`` que lanza; si no la lanza, la prueba falla."""
    try:
        llamada()
    except ValidationError as error:
        return error
    raise AssertionError("Se esperaba una ValidationError y no se lanzó.")


class ProdBajInvServicioTests(ConGeoref, TestCase):
    """Servicio ``baja_invernadero`` (PROD-BAJ-INV): precondiciones a y b, postcondiciones a, d y f, y reglas 1 y 2."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo, self.capataz = crear_agronomo(), crear_capataz_activo()
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo, capataz=self.capataz)

    def baja(self, actor=None, invernadero=None):
        return invernaderos.baja_invernadero(actor or self.gerente, (invernadero or self.invernadero).pk)

    def recargado(self):
        return Invernadero.objects.get(pk=self.invernadero.pk)

    # ---- Firma ----

    def test_firma_recibe_actor_e_id(self):
        """Firma de ``baja_invernadero`` (D-39, decisión «Firma» del alta; PROD-BAJ-INV): recibe ``(actor,
        invernadero_id)``; faltar el id es un ``TypeError``."""
        with self.assertRaises(TypeError):
            invernaderos.baja_invernadero(self.gerente)

    # ---- Precondiciones ----

    def test_pre_a_un_gerente_activo_da_de_baja(self):
        """PROD-BAJ-INV, precondición a: el Gerente activo puede dar de baja."""
        self.assertFalse(self.baja().activo)

    def test_pre_a_otro_rol_no_da_de_baja(self):
        """PROD-BAJ-INV, precondición a: un Agrónomo, un Capataz o un Administrador reciben PermissionDenied."""
        for actor in (self.agronomo, crear_capataz(), crear_administrador()):
            with self.subTest(actor=actor.email), self.assertRaises(PermissionDenied):
                self.baja(actor)
        self.assertTrue(self.recargado().activo)

    def test_pre_a_un_gerente_inactivo_o_sin_actor_no_da_de_baja(self):
        """PROD-BAJ-INV, precondición a: «con una cuenta activa de Gerente»."""
        with self.assertRaises(PermissionDenied):
            invernaderos.baja_invernadero(None, self.invernadero.pk)
        self.gerente.is_active = False
        self.gerente.save()
        with self.assertRaises(PermissionDenied):
            self.baja()

    def test_pre_a_un_invernadero_inexistente_da_404(self):
        """PROD-BAJ-INV y D-28: un id que no existe es Http404."""
        with self.assertRaises(Http404):
            invernaderos.baja_invernadero(self.gerente, 0)

    def test_pre_b_un_invernadero_inactivo_no_se_da_de_baja(self):
        """PROD-BAJ-INV, precondición b: «el invernadero está activo»; uno inactivo se rechaza con
        ``invernadero_inactivo`` y no audita."""
        inactivo = crear_invernadero("Viejo", activo=False)
        self.assertEqual(codigos(error_de(lambda: self.baja(invernadero=inactivo))), ["invernadero_inactivo"])
        self.assertFalse(RegistroAuditoria.objects.exists())

    # ---- Precondiciones c a h y regla 2: impedimentos (punto de extensión) ----

    def test_pre_c_a_h_sin_registrantes_se_dan_por_cumplidas(self):
        """PROD-BAJ-INV, precondiciones c a h y «Para más adelante»: mientras las clases no existan (ninguna app
        registrada), cada condición se da por cumplida y la baja procede."""
        with con_impedimentos():
            self.assertFalse(self.baja().activo)

    def test_regla_2_un_registrante_sin_impedimentos_no_impide_la_baja(self):
        """PROD-BAJ-INV, regla 2: un registrante que devuelve una lista vacía no impide."""
        with con_impedimentos(lambda invernadero: []):
            self.assertFalse(self.baja().activo)

    def test_regla_2_un_impedimento_no_da_de_baja_e_informa_el_texto_y_como_resolverlo(self):
        """PROD-BAJ-INV, regla 2: el Sistema no da de baja e informa lo que lo impide, con cómo resolverlo."""
        with con_impedimentos(lambda invernadero: [impedimento()]):
            error = error_de(self.baja)
        self.assertEqual(codigos(error), ["lotes_activos"])
        (mensaje,) = error.messages
        self.assertIn("Tiene 2 lotes activos.", mensaje)
        self.assertIn("Cosechalos o registrá su merma.", mensaje)
        self.assertTrue(self.recargado().activo)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_2_informa_todos_los_impedimentos_y_no_se_queda_con_el_primero(self):
        """PROD-BAJ-INV, regla 2: «informa todo lo que lo impide»: los de varios registrantes y los varios de uno solo."""
        lotes = impedimento("lotes_activos", "Tiene 2 lotes activos.", "Cosechalos.")
        ordenes = impedimento("ordenes_a_realizar", "Tiene 3 órdenes a realizar.", "Concretalas o cancelalas.")
        stock = impedimento("stock_de_insumos", "Hay 1 insumo con stock.", "Usalo o ajustalo a cero.")
        iot = impedimento("iot_activo", "El sistema IoT sigue activo.", "Dalo de baja en el bloque IoT.")
        with con_impedimentos(lambda invernadero: [lotes, ordenes], lambda invernadero: [stock], lambda invernadero: [iot]):
            error = error_de(self.baja)
        self.assertEqual(codigos(error), ["lotes_activos", "ordenes_a_realizar", "stock_de_insumos", "iot_activo"])
        self.assertEqual(len(error.messages), 4)

    def test_regla_2_los_registrantes_reciben_el_invernadero(self):
        """PROD-BAJ-INV y D-37 (A4): cada registrante recibe el invernadero que se da de baja."""
        registrante = mock.Mock(return_value=[])
        with con_impedimentos(registrante):
            self.baja()
        (llamada,) = registrante.call_args_list
        self.assertEqual(llamada.args[0].pk, self.invernadero.pk)

    def test_regla_2_un_impedimento_no_corre_los_efectos(self):
        """PROD-BAJ-INV, regla 2: si hay impedimentos, no se cambia nada, tampoco lo de los efectos."""
        efecto = mock.Mock()
        with con_impedimentos(lambda invernadero: [impedimento()]), con_efectos(efecto):
            error_de(self.baja)
        efecto.assert_not_called()

    def test_regla_2_un_impedimento_no_cambia_el_personal_ni_la_direccion(self):
        """PROD-BAJ-INV, regla 2: la baja rechazada no deja ningún cambio."""
        direccion = self.invernadero.direccion_id
        with con_impedimentos(lambda invernadero: [impedimento()]):
            error_de(self.baja)
        invernadero = self.recargado()
        self.assertEqual((invernadero.agronomo_id, invernadero.capataz_id, invernadero.direccion_id), (self.agronomo.pk, self.capataz.pk, direccion))

    # ---- impedimentos_para_baja: la ventana de confirmación ----

    def test_regla_2_impedimentos_para_baja_devuelve_los_de_todos_los_registrantes(self):
        """PROD-BAJ-INV, regla 2 y «Pantallas»: la ventana muestra todo lo que impide, sin dar de baja ni auditar."""
        lotes, stock = impedimento("lotes_activos"), impedimento("stock_de_insumos", "Hay stock.", "Usalo.")
        with con_impedimentos(lambda invernadero: [lotes], lambda invernadero: [stock]):
            devueltos = invernaderos.impedimentos_para_baja(self.gerente, self.invernadero.pk)
        self.assertEqual(list(devueltos), [lotes, stock])
        self.assertTrue(self.recargado().activo)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_2_impedimentos_para_baja_sin_registrantes_es_vacio(self):
        """PROD-BAJ-INV, regla 2: sin impedimentos la ventana ofrece confirmar."""
        with con_impedimentos():
            self.assertEqual(list(invernaderos.impedimentos_para_baja(self.gerente, self.invernadero.pk)), [])

    def test_pre_a_impedimentos_para_baja_exige_un_gerente_activo(self):
        """PROD-BAJ-INV, precondición a: la ventana también es solo del Gerente (D-30)."""
        for actor in (self.agronomo, crear_capataz(), crear_administrador(), None):
            with self.subTest(actor=getattr(actor, "email", None)), self.assertRaises(PermissionDenied):
                invernaderos.impedimentos_para_baja(actor, self.invernadero.pk)

    def test_pre_b_impedimentos_para_baja_rechaza_uno_inactivo(self):
        """PROD-BAJ-INV, precondición b: sobre uno inactivo no hay baja que confirmar (``invernadero_inactivo``)."""
        inactivo = crear_invernadero("Viejo", activo=False)
        error = error_de(lambda: invernaderos.impedimentos_para_baja(self.gerente, inactivo.pk))
        self.assertEqual(codigos(error), ["invernadero_inactivo"])

    # ---- Postcondiciones ----

    def test_post_a_el_invernadero_queda_inactivo(self):
        """PROD-BAJ-INV, postcondición a: el invernadero quedó en estado «inactivo» (baja lógica)."""
        devuelto = self.baja()
        self.assertFalse(devuelto.activo)
        self.assertEqual(self.recargado().estado_invernadero, "inactivo")

    def test_post_d_el_personal_asignado_se_conserva_como_historial(self):
        """PROD-BAJ-INV, postcondición d: el personal asignado se conservó."""
        self.baja()
        invernadero = self.recargado()
        self.assertEqual((invernadero.agronomo_id, invernadero.capataz_id), (self.agronomo.pk, self.capataz.pk))

    def test_regla_1_la_baja_es_logica_y_conserva_el_nombre_y_la_direccion(self):
        """PROD-BAJ-INV, regla 1: la baja es lógica; el invernadero, su nombre y su dirección siguen en la base."""
        direccion = self.invernadero.direccion_id
        self.baja()
        invernadero = self.recargado()
        self.assertEqual((invernadero.nombre_invernadero, invernadero.direccion_id), ("Invernadero A", direccion))
        self.assertTrue(Direccion.objects.filter(pk=direccion).exists())

    def test_regla_5_se_reactiva_con_modificar(self):
        """PROD-BAJ-INV, regla 5: «se reactiva con PROD-MOD-INV»; tras la baja, la reactivación lo deja activo."""
        self.baja()
        self.assertTrue(invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk).activo)

    def test_post_b_y_c_los_efectos_corren_una_vez_con_el_actor_y_el_invernadero(self):
        """PROD-BAJ-INV, postcondiciones b y c (punto de extensión): cada registrante de efectos corre una vez con el
        actor y el invernadero, cuando ya no hay impedimentos."""
        efecto = mock.Mock()
        with con_impedimentos(), con_efectos(efecto):
            self.baja()
        (llamada,) = efecto.call_args_list
        self.assertEqual(llamada.args[0], self.gerente)
        self.assertEqual(llamada.args[1].pk, self.invernadero.pk)

    def test_post_b_y_c_los_efectos_corren_despues_de_verificar_los_impedimentos(self):
        """PROD-BAJ-INV, regla 2 y postcondiciones b y c: primero se juntan los impedimentos; los efectos, después."""
        orden = []
        with (
            con_impedimentos(lambda invernadero: orden.append("impedimentos") or []),
            con_efectos(lambda actor, invernadero: orden.append("efectos")),
        ):
            self.baja()
        self.assertEqual(orden, ["impedimentos", "efectos"])

    def test_post_b_y_c_los_efectos_ven_al_invernadero_ya_inactivo(self):
        """PROD-BAJ-INV, postcondiciones b y c: los efectos (sectores e insumos pasan a inactivos) corren con el
        invernadero ya dado de baja en la base, dentro de la misma transacción."""
        vistos = []
        efecto = lambda actor, invernadero: vistos.append(Invernadero.objects.get(pk=invernadero.pk).estado_invernadero)  # noqa: E731
        with con_efectos(efecto):
            self.baja()
        self.assertEqual(vistos, ["inactivo"])

    def test_post_b_y_c_si_un_efecto_falla_no_queda_la_baja(self):
        """PROD-BAJ-INV y D-22: los efectos corren en la misma transacción; si uno falla, el invernadero sigue activo."""
        with con_efectos(mock.Mock(side_effect=FallaDePrueba("falla"))):
            with self.assertRaises(FallaDePrueba), transaction.atomic():
                self.baja()
        self.assertTrue(self.recargado().activo)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_post_f_audita_la_baja_con_el_cambio_de_estado(self):
        """PROD-BAJ-INV, postcondición f y D-36: un registro con quien actuó, la acción, el invernadero y el estado."""
        self.baja()
        registro = RegistroAuditoria.objects.get(accion=BAJA)
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.rol, "gerente")
        self.assertEqual(
            registro.afectados,
            [{"modelo": "maestros.invernadero", "id": self.invernadero.pk, "texto": "Invernadero A"}],
        )
        self.assertEqual(registro.detalle, {"cambios": {"estado": {"antes": "activo", "despues": "inactivo"}}})

    def test_post_f_un_solo_registro_por_baja(self):
        """PROD-BAJ-INV, postcondición f: «una acción = un registro» (D-36); los de sectores e insumos los audita
        cada registrante de efectos."""
        self.baja()
        self.assertEqual(RegistroAuditoria.objects.count(), 1)

    def test_post_f_una_baja_rechazada_no_audita(self):
        """PROD-BAJ-INV, postcondición f: si la baja se rechaza, no queda ningún registro."""
        with con_impedimentos(lambda invernadero: [impedimento()]):
            error_de(self.baja)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_d22_si_falla_la_auditoria_no_queda_la_baja(self):
        """D-22: la auditoría se escribe en la misma transacción; si falla, el invernadero sigue activo."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=FallaDePrueba("falla")):
            with self.assertRaises(FallaDePrueba), transaction.atomic():
                self.baja()
        self.assertTrue(self.recargado().activo)

    # ---- MAE-02a: alertas (postcondición e; reemplazan a test_d38_la_baja_…) ----

    def test_post_e_las_alertas_activas_pasan_a_resuelta_con_su_fecha(self):
        """PROD-BAJ-INV, postcondición e: las alertas activas del invernadero (de estado y de evento) pasaron a
        «resuelta», con su fecha; las ya resueltas conservan la suya y las de otro invernadero no se tocan."""
        otro = crear_invernadero("Invernadero B")
        de_estado = crear_alerta(self.invernadero, tipo_alerta="sin_vendedor", clave_estado="")
        de_evento = crear_alerta(self.invernadero)
        vieja = crear_alerta(self.invernadero, resuelta=True)
        fecha_vieja = vieja.fecha_resolucion
        ajena = crear_alerta(otro)
        self.baja()
        for alerta in (de_estado, de_evento, vieja, ajena):
            alerta.refresh_from_db()
        for alerta in (de_estado, de_evento):
            self.assertEqual(alerta.estado_alerta, "resuelta")
            self.assertIsNotNone(alerta.fecha_resolucion)
        self.assertEqual(vieja.fecha_resolucion, fecha_vieja)
        self.assertEqual(ajena.estado_alerta, "activa")

    def test_post_e_la_baja_no_cambia_la_lectura_de_las_alertas(self):
        """Regla 7 de 8.18: los dos estados son independientes; resolver no marca «leída»."""
        alerta = crear_alerta(self.invernadero)
        self.baja()
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_lectura_alerta, "no_leida")

    def test_post_e_un_invernadero_inactivo_no_genera_alertas(self):
        """PROD-BAJ-INV, postcondición e: «el invernadero dejó de generar alertas»: después de la baja, la API no crea
        alertas de evento ni de estado ni de personal."""
        self.baja()
        with tipo_de_alerta_de_prueba(tipo_falso("prueba_evento"), tipo_falso("prueba_estado", clase=Clase.ESTADO)):
            self.assertIsNone(alertas.crear_alerta_de_evento(self.invernadero.pk, "prueba_evento", "x"))
            self.assertIsNone(alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado"))
        self.assertEqual(list(alertas.sincronizar_alertas_de_personal(self.recargado()).creadas), [])
        self.assertFalse(Alerta.objects.filter(estado_alerta="activa").exists())

    def test_post_e_una_baja_rechazada_no_resuelve_alertas(self):
        """PROD-BAJ-INV, postcondición e y regla 2: si un impedimento rechaza la baja, las alertas siguen activas."""
        alerta = crear_alerta(self.invernadero)
        with con_impedimentos(lambda invernadero: [impedimento()]), self.assertRaises(ValidationError):
            self.baja()
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "activa")

    def test_post_e_si_falla_la_auditoria_las_alertas_siguen_activas(self):
        """D-22 y postcondición e: las alertas se resuelven en la misma transacción; si la auditoría falla, se deshace."""
        alerta = crear_alerta(self.invernadero)
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=FallaDePrueba("falla")):
            with self.assertRaises(FallaDePrueba), transaction.atomic():
                self.baja()
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "activa")

    def test_post_f_un_solo_registro_con_las_alertas_resueltas_en_datos(self):
        """PROD-BAJ-INV, postcondición f y D-36 (D6 de MAE-02): un solo registro con el cambio de estado en ``cambios`` y
        las alertas resueltas en ``datos.alertas_resueltas`` (solo las que pasaron de activa a resuelta)."""
        activa = crear_alerta(self.invernadero, descripcion_alerta="Activa")
        crear_alerta(self.invernadero, descripcion_alerta="Vieja", resuelta=True)
        self.baja()
        self.assertEqual(RegistroAuditoria.objects.count(), 1)
        detalle = RegistroAuditoria.objects.get(accion=BAJA).detalle
        self.assertEqual(detalle["cambios"], {"estado": {"antes": "activo", "despues": "inactivo"}})
        self.assertEqual(detalle["datos"], {"alertas_resueltas": [{"id": activa.pk, "texto": "Activa"}]})


class ProdBajInvBloqueoTests(ConGeoref, TestCase):
    """``bloquear_invernadero_activo``: el contrato que cumple todo caso de uso futuro que cree algo que impide la baja
    (docstring de maestros/extensiones.py y docs/patrones/bloqueos.md). La espera de verdad la prueban las de concurrencia."""

    def test_devuelve_el_invernadero_activo(self):
        """Contrato de D-37 (A4): un invernadero activo se devuelve para seguir trabajando con él."""
        invernadero = crear_invernadero("Activo")
        with transaction.atomic():
            self.assertEqual(invernaderos.bloquear_invernadero_activo(invernadero.pk), invernadero)

    def test_rechaza_un_invernadero_inactivo(self):
        """Contrato de D-37 (A4): no se crea nada sobre un invernadero inactivo; el código es ``invernadero_inactivo``."""
        inactivo = crear_invernadero("Viejo", activo=False)
        with transaction.atomic():
            error = error_de(lambda: invernaderos.bloquear_invernadero_activo(inactivo.pk))
        self.assertEqual(codigos(error), ["invernadero_inactivo"])

    def test_un_invernadero_inexistente_da_404(self):
        """Contrato de D-37 (A4): un id que no existe es Http404."""
        with transaction.atomic(), self.assertRaises(Http404):
            invernaderos.bloquear_invernadero_activo(0)


class _Pausa:
    """Punto de parada del creador falso: ``correr_a_la_vez(..., detener_antes_de=(pausa, "punto"))`` lo detiene acá,
    con su fila insertada y su transacción sin confirmar."""

    def punto(self):
        """No hace nada: es donde se detiene la prueba."""


pausa = _Pausa()
TABLA_FALSA = "prueba_impedimento_falso"


def hay_filas_falsas(invernadero_id):
    """True si hay algo en la tabla falsa para ese invernadero (lo que cuenta el registrante de impedimentos falso)."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT 1 FROM {TABLA_FALSA} WHERE invernadero_id = %s LIMIT 1", [invernadero_id])
        return cursor.fetchone() is not None


def impedimentos_falsos(invernadero):
    """Registrante de impedimentos falso: algo creado por un caso de uso de una app alta que impide la baja."""
    if hay_filas_falsas(invernadero.pk):
        return [Impedimento("registro_falso", "Hay un registro falso.", "Borralo.")]
    return []


def crear_algo_que_impide_la_baja(invernadero_id):
    """El caso de uso falso de una app alta que cumple el contrato de D-37 (A4): bloquea el invernadero, verifica que siga
    activo y recién entonces inserta su fila (con una FK real al invernadero, que toma ``FOR KEY SHARE``)."""
    with transaction.atomic():
        invernaderos.bloquear_invernadero_activo(invernadero_id)
        with connection.cursor() as cursor:
            cursor.execute(f"INSERT INTO {TABLA_FALSA} (invernadero_id) VALUES (%s)", [invernadero_id])
        pausa.punto()


@tag("concurrencia")
class ProdBajInvConcurrenciaTests(TransactionTestCase):
    """Bloqueos de ``baja_invernadero`` (docs/patrones/bloqueos.md, D-30 y D-32) y contrato de los puntos de extensión
    (D-37, A4). Dos hilos, dos conexiones, el orden fijado con ``primera`` (``core/tests/concurrencia.py``). La tabla
    falsa (con una FK real al invernadero) se crea en ``setUp`` y se borra siempre antes del ``flush`` de Django: si
    quedara de una corrida cortada, su FK haría fallar el ``TRUNCATE`` y la base de pruebas con ``--keepdb`` quedaría
    rota; por eso ``setUpClass`` también la borra."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._borrar_tabla_falsa()

    @staticmethod
    def _borrar_tabla_falsa():
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {TABLA_FALSA}")

    def setUp(self):
        self.addCleanup(self._borrar_tabla_falsa)  # corre antes del flush de Django, pase lo que pase
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {TABLA_FALSA} "
                "(id serial PRIMARY KEY, invernadero_id bigint NOT NULL REFERENCES maestros_invernadero (id))"
            )
        self.gerente = crear_gerente()
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero A")

    def baja(self):
        return lambda: invernaderos.baja_invernadero(self.gerente, self.invernadero.pk)

    def test_pre_b_dos_bajas_a_la_vez_dan_de_baja_una_sola_vez(self):
        """PROD-BAJ-INV, precondición b: la segunda baja espera el bloqueo del invernadero, lo lee inactivo y se rechaza con
        ``invernadero_inactivo``; queda un solo registro de baja. Sin el bloqueo, las dos pasan y dejan dos registros."""
        resultados = correr_a_la_vez(self.baja(), self.baja(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["invernadero_inactivo"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA).count(), 1)

    def test_d37_la_baja_espera_a_quien_crea_algo_que_la_impide_y_se_rechaza(self):
        """Contrato de D-37 (A4): quien crea algo que impide la baja bloquea el invernadero antes; la baja espera a que
        confirme y entonces ve el impedimento. Sin el bloqueo del creador (el ``INSERT`` solo toma ``FOR KEY SHARE``, que no
        choca con el ``FOR NO KEY UPDATE`` de la baja), la baja no espera, no ve lo que no se confirmó y da de baja un
        invernadero con un impedimento."""
        with mock.patch.object(extensiones, "_IMPEDIMENTOS", [impedimentos_falsos]):
            resultados = correr_a_la_vez(
                lambda: crear_algo_que_impide_la_baja(self.invernadero.pk),
                self.baja(),
                primera="a",
                detener_antes_de=(pausa, "punto"),
            )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["registro_falso"])
        self.assertTrue(hay_filas_falsas(self.invernadero.pk))
        self.assertTrue(Invernadero.objects.get(pk=self.invernadero.pk).activo)

    def test_d37_quien_crea_algo_espera_a_la_baja_y_se_rechaza(self):
        """Contrato de D-37 (A4): la baja va primera y el creador espera el bloqueo; cuando sigue, el invernadero está
        inactivo y no crea nada (``invernadero_inactivo``). Sin el bloqueo, el creador inserta sobre un invernadero dado
        de baja."""
        with mock.patch.object(extensiones, "_IMPEDIMENTOS", [impedimentos_falsos]):
            resultados = correr_a_la_vez(
                self.baja(),
                lambda: crear_algo_que_impide_la_baja(self.invernadero.pk),
                primera="a",
            )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["invernadero_inactivo"])
        self.assertFalse(hay_filas_falsas(self.invernadero.pk))
        self.assertFalse(Invernadero.objects.get(pk=self.invernadero.pk).activo)


class ProdBajInvVistaTests(ConGeoref, TestCase):
    """Ventana de baja del invernadero (integración, PROD-BAJ-INV): confirmación previa, impedimentos de la regla 2, flujo
    principal y acceso por rol (SEG-13, D-30). La ventana viene en la página (sin JavaScript) y, con HTMX, sola."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.force_login(self.gerente)
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo)
        self.url = reverse("maestros:invernadero_baja", args=[self.invernadero.pk])
        self.ficha = reverse("maestros:invernadero", args=[self.invernadero.pk])

    def recargado(self):
        return Invernadero.objects.get(pk=self.invernadero.pk)

    def test_flujo_principal_la_ventana_pide_confirmar_y_no_cambia_nada(self):
        """PROD-BAJ-INV, ``MODALS['inv-baja']``: abrir la ventana (GET) muestra la confirmación sobre la ficha, sin cambiar
        ni auditar nada."""
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "¿Dar de baja Invernadero A?")
        self.assertContains(respuesta, "Sus sectores y sus insumos pasan a inactivos")
        self.assertContains(respuesta, "Invernadero A")  # la ficha queda detrás de la ventana
        self.assertContains(respuesta, 'data-cerrar-ventana')
        self.assertTrue(self.recargado().activo)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_flujo_principal_con_htmx_llega_solo_la_ventana(self):
        """Interfaz: un pedido de HTMX recibe solo la ventana, para insertarla sobre la ficha."""
        respuesta = self.client.get(self.url, headers={"HX-Request": "true"})
        self.assertContains(respuesta, "¿Dar de baja Invernadero A?")
        self.assertNotContains(respuesta, "<h1>")

    def test_flujo_principal_confirmar_da_de_baja_y_va_a_la_ficha(self):
        """PROD-BAJ-INV, ``ACT['inv-baja-ok']``: confirmar da de baja, audita y vuelve a la ficha con el aviso."""
        respuesta = self.client.post(self.url, follow=True)
        self.assertRedirects(respuesta, self.ficha)
        self.assertContains(respuesta, "Invernadero A se dio de baja.")
        self.assertFalse(self.recargado().activo)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=BAJA).count(), 1)

    def test_regla_2_con_impedimentos_la_ventana_los_dice_todos_y_no_ofrece_confirmar(self):
        """PROD-BAJ-INV, regla 2: la ventana informa todo lo que impide la baja, cada cosa con cómo resolverla, y solo
        ofrece «Entendido» (D-30: no se ofrece confirmar algo que se va a rechazar)."""
        lotes = impedimento("lotes_activos", "Tiene 2 lotes activos.", "Cosechalos o registrá su merma.")
        iot = impedimento("iot_activo", "El sistema IoT sigue activo.", "Dalo de baja en el bloque IoT.")
        with con_impedimentos(lambda invernadero: [lotes, iot]):
            respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "No se puede dar de baja Invernadero A")
        self.assertContains(respuesta, "Tiene 2 lotes activos. Cosechalos o registrá su merma.")
        self.assertContains(respuesta, "El sistema IoT sigue activo. Dalo de baja en el bloque IoT.")
        self.assertContains(respuesta, "Entendido")
        self.assertNotContains(respuesta, 'data-enviando="Dando de baja…"')

    def test_regla_2_un_impedimento_que_aparece_antes_de_confirmar_vuelve_a_la_ventana(self):
        """PROD-BAJ-INV, regla 2: si mientras la ventana estaba abierta apareció un impedimento, el POST no da de baja y la
        ventana vuelve con el motivo."""
        with con_impedimentos(lambda invernadero: [impedimento()]):
            respuesta = self.client.post(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Tiene 2 lotes activos. Cosechalos o registrá su merma.")
        self.assertTrue(self.recargado().activo)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_pre_b_un_invernadero_inactivo_vuelve_a_la_ficha_con_el_motivo(self):
        """PROD-BAJ-INV, precondición b y D-30: la ventana de uno ya inactivo lleva a la ficha con el motivo, sin 403."""
        inactivo = crear_invernadero("Viejo", activo=False)
        url = reverse("maestros:invernadero_baja", args=[inactivo.pk])
        respuesta = self.client.get(url, follow=True)
        self.assertRedirects(respuesta, reverse("maestros:invernadero", args=[inactivo.pk]))
        self.assertContains(respuesta, "El invernadero ya está dado de baja.")
        self.assertRedirects(self.client.post(url), reverse("maestros:invernadero", args=[inactivo.pk]))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_5_la_ficha_de_uno_dado_de_baja_ofrece_reactivar(self):
        """PROD-BAJ-INV, regla 5: «se reactiva con PROD-MOD-INV»; tras la baja la ficha ofrece «Reactivar»."""
        self.client.post(self.url)
        respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, reverse("maestros:invernadero_reactivar", args=[self.invernadero.pk]))
        self.assertNotContains(respuesta, self.url)

    def test_pre_a_otros_roles_y_sin_sesion_no_dan_de_baja(self):
        """PROD-BAJ-INV, precondición a y SEG-13: el Agrónomo y el Capataz reciben 403; sin sesión, a iniciar sesión."""
        for cuenta in (self.agronomo, crear_capataz()):
            self.client.force_login(cuenta)
            with self.subTest(cuenta=cuenta.email):
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertTrue(self.recargado().activo)

    def test_pre_a_un_invernadero_inexistente_da_404(self):
        """PROD-BAJ-INV y D-28: un id que no existe es 404."""
        self.assertEqual(self.client.get(reverse("maestros:invernadero_baja", args=[0])).status_code, 404)


class ProdBajInvTransportistasTests(ConGeoref, TestCase):
    """Precondición g y reglas 2 y 3 de PROD-BAJ-INV *(MAE-05, D-55)*: los transportistas ACTIVOS vinculados impiden la baja
    (código ``transportistas_activos``); los inactivos quedan como historial (D-39). Es un impedimento propio de `maestros`:
    va junto con los de los registrantes, sin quedarse con el primero."""

    TEXTO_UNO = "Tiene 1 transportista activo: Diego Ferreyra."
    COMO = "Trasladalos a otro invernadero o quitalos desde “Logística”."

    def setUp(self):
        self.gerente = crear_gerente()
        self.invernadero = crear_invernadero("Invernadero A")
        self.otro = crear_invernadero("Invernadero B")
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        self.carla = crear_transportista("carla@infoponia.com", nombre="Carla", apellido="Sosa")

    def baja(self):
        return invernaderos.baja_invernadero(self.gerente, self.invernadero.pk)

    def recargado(self):
        return Invernadero.objects.get(pk=self.invernadero.pk)

    def test_pre_g_con_un_transportista_activo_se_rechaza_con_su_texto_y_como_resolverlo(self):
        """PROD-BAJ-INV precondición g y regla 2: un Transportista activo vinculado impide la baja; el mensaje dice cuántos y
        quiénes, y cómo resolverlo (trasladarlos o quitarlos desde «Logística»)."""
        asignar_transportista(self.diego, self.invernadero)
        with con_impedimentos():
            error = error_de(self.baja)
        self.assertEqual(codigos(error), ["transportistas_activos"])
        self.assertEqual(error.messages, [f"{self.TEXTO_UNO} {self.COMO}"])

    def test_pre_g_el_texto_va_en_plural_con_los_nombres_por_apellido_y_nombre(self):
        """PROD-BAJ-INV precondición g: «Tiene {N} transportista(s) activo(s): {nombres}.» con N y los nombres, por apellido y
        nombre."""
        asignar_transportista(self.carla, self.invernadero)
        asignar_transportista(self.diego, self.invernadero)
        with con_impedimentos():
            error = error_de(self.baja)
        self.assertEqual(
            error.messages, [f"Tiene 2 transportistas activos: Diego Ferreyra, Carla Sosa. {self.COMO}"]
        )

    def test_pre_g_un_rechazo_no_cambia_nada(self):
        """PROD-BAJ-INV regla 2: con el impedimento no se da de baja, no se audita y la fila sigue."""
        asignar_transportista(self.diego, self.invernadero)
        with con_impedimentos():
            error_de(self.baja)
        self.assertTrue(self.recargado().activo)
        self.assertFalse(RegistroAuditoria.objects.exists())
        self.assertEqual(self.invernadero.transportistas_asignados.count(), 1)

    def test_pre_g_un_transportista_inactivo_no_impide_la_baja_y_la_fila_queda_como_historial(self):
        """PROD-BAJ-INV regla 3 y D-39: los inactivos vinculados no impiden la baja; la fila se conserva (D-55, punto 8)."""
        asignar_transportista(self.diego, self.invernadero)
        asignar_transportista(crear_transportista("inactivo@infoponia.com", activo=False), self.invernadero)
        Usuario.objects.filter(pk=self.diego.pk).update(is_active=False)
        with con_impedimentos():
            self.assertFalse(self.baja().activo)
        self.assertEqual(self.invernadero.transportistas_asignados.count(), 2)

    def test_pre_g_un_transportista_de_otro_invernadero_no_impide_la_baja(self):
        """PROD-BAJ-INV precondición g: solo cuentan los transportistas de ESTE invernadero."""
        asignar_transportista(self.diego, self.otro)
        with con_impedimentos():
            self.assertFalse(self.baja().activo)

    def test_pre_g_sin_transportistas_no_hay_impedimento(self):
        """PROD-BAJ-INV precondición g: un invernadero sin transportistas puede darse de baja (puede vender con retiro)."""
        with con_impedimentos():
            self.assertFalse(self.baja().activo)

    def test_regla_2_va_junto_con_los_impedimentos_de_los_registrantes(self):
        """PROD-BAJ-INV regla 2: el impedimento propio se suma a los de los registrantes; se informan todos."""
        asignar_transportista(self.diego, self.invernadero)
        with con_impedimentos(lambda invernadero: [impedimento()]):
            error = error_de(self.baja)
        self.assertCountEqual(codigos(error), ["lotes_activos", "transportistas_activos"])

    def test_regla_2_impedimentos_para_baja_incluye_a_los_transportistas_activos_sin_cambiar_nada(self):
        """PROD-BAJ-INV regla 2: la ventana recibe el impedimento (con su código, texto y cómo resolverlo); solo lectura."""
        asignar_transportista(self.diego, self.invernadero)
        with con_impedimentos():
            devueltos = invernaderos.impedimentos_para_baja(self.gerente, self.invernadero.pk)
        self.assertEqual(
            [(i.codigo, i.texto, i.como_resolver) for i in devueltos],
            [("transportistas_activos", self.TEXTO_UNO, self.COMO)],
        )
        self.assertTrue(self.recargado().activo)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_2_impedimentos_para_baja_no_cuenta_a_los_inactivos(self):
        """PROD-BAJ-INV regla 3 y D-39: la ventana no los menciona."""
        asignar_transportista(crear_transportista("inactivo@infoponia.com", activo=False), self.invernadero)
        with con_impedimentos():
            self.assertEqual(list(invernaderos.impedimentos_para_baja(self.gerente, self.invernadero.pk)), [])

    def test_regla_2_quitar_al_transportista_resuelve_el_impedimento(self):
        """PROD-BAJ-INV regla 2: «trasladalos o quitalos desde Logística»: quitado, la baja procede."""
        from maestros.servicios import transportistas

        asignar_transportista(self.diego, self.invernadero)
        transportistas.quitar_transportista(self.gerente, self.invernadero.pk, self.diego.pk)
        with con_impedimentos():
            self.assertFalse(self.baja().activo)

    def test_regla_2_el_impedimento_no_depende_de_los_registrantes(self):
        """D-55: el impedimento es de `maestros` y no un registrante: sigue aunque las pruebas (o `comercial`) reemplacen la
        lista de registrantes."""
        asignar_transportista(self.diego, self.invernadero)
        with con_impedimentos():
            self.assertEqual(
                [i.codigo for i in invernaderos.impedimentos_para_baja(self.gerente, self.invernadero.pk)],
                ["transportistas_activos"],
            )


class ProdBajInvTransportistasVistaTests(ConGeoref, TestCase):
    """La ventana de baja muestra el impedimento de los transportistas activos (PROD-BAJ-INV regla 2, D-30)."""

    def setUp(self):
        self.client.force_login(crear_gerente())
        self.invernadero = crear_invernadero("Invernadero A")
        asignar_transportista(crear_transportista(nombre="Diego", apellido="Ferreyra"), self.invernadero)
        self.url = reverse("maestros:invernadero_baja", args=[self.invernadero.pk])

    def test_regla_2_la_ventana_dice_los_transportistas_activos_y_no_ofrece_confirmar(self):
        """PROD-BAJ-INV regla 2: «Tiene 1 transportista activo: …» con cómo resolverlo, y solo «Entendido»."""
        with con_impedimentos():
            respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "No se puede dar de baja Invernadero A")
        self.assertContains(respuesta, "Tiene 1 transportista activo: Diego Ferreyra.")
        self.assertContains(respuesta, "Trasladalos a otro invernadero o quitalos desde “Logística”.")
        self.assertContains(respuesta, "Entendido")
        self.assertNotContains(respuesta, 'data-enviando="Dando de baja…"')

    def test_regla_2_confirmar_con_un_transportista_activo_no_da_de_baja_y_vuelve_a_la_ventana(self):
        """PROD-BAJ-INV regla 2: un POST manual lo rechaza el servicio y la ventana vuelve con el motivo."""
        with con_impedimentos():
            respuesta = self.client.post(self.url)
        self.assertContains(respuesta, "Tiene 1 transportista activo: Diego Ferreyra.")
        self.assertTrue(Invernadero.objects.get(pk=self.invernadero.pk).activo)
