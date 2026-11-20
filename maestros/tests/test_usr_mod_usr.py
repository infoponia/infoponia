# Pruebas de MAE-02b para USR-MOD-USR (Modificar Usuario, la reactivación) en lo que le toca a maestros: la postcondición c
# (reactivar deja la cuenta activa y resuelve la alerta «invernadero sin {rol} activo» de su rol), D8 (al reactivar una
# cuenta de Agrónomo se aplica D4 de D-41: recibe las alertas que habían ido al Gerente por falta de Agrónomo), la
# postcondición d (qué se audita, D-36) y D-22 (todo en la misma transacción). Fuentes: docs/casos_de_uso/usuarios.md,
# docs/modelo/maestros.md, D-40, D-41 y D-43. ``reactivar_usuario`` es de core: maestros se registra en
# ``core/extensiones.py`` desde ``MaestrosConfig.ready()`` (regla A4 de D-37). Contrato que fijan estas pruebas
# (``maestros/servicios/invernaderos.py``): efectos_de_reactivacion_de_cuenta(actor, cuenta) -> Efecto(afectados, datos).
# Cada prueba arma sus propios datos. Los tipos de alerta de prueba se registran con ``tipo_de_alerta_de_prueba``.

from unittest import mock

from django.db import transaction
from django.test import TestCase, TransactionTestCase, tag
from django.urls import reverse

from core import extensiones
from core import servicios as cuentas
from core.models import RegistroAuditoria, Usuario, referencia
from core.tests.concurrencia import correr_a_la_vez, separar
from core.tests.fabricas import afectado, crear_gerente
from maestros.alertas import Destinatario, tipo_de_alerta
from maestros.models import Alerta, Invernadero
from maestros.servicios import alertas, invernaderos
from maestros.tests.fabricas import (
    ConGeoref,
    FallaDePrueba,
    crear_agronomo,
    crear_alerta,
    crear_capataz_activo,
    crear_invernadero,
    crear_invernadero_con_geografia_propia,
    crear_vendedor,
    tipo_de_alerta_de_prueba,
    tipo_falso,
)

NOMBRE_SIN_ROL = {atributo: f"Invernadero sin {nombre} activo" for atributo, nombre in Invernadero.ROLES}


def afectado_invernadero(invernadero):
    """Cómo queda un invernadero entre los afectados de un registro de auditoría (D-36)."""
    return {"modelo": "maestros.invernadero", "id": invernadero.pk, "texto": invernadero.nombre_invernadero}


def tipos_de_agronomo():
    """Los tres tipos de prueba según su destinatario (D-41), registrados solo mientras dura el bloque."""
    return tipo_de_alerta_de_prueba(
        tipo_falso("prueba_o", destinatario=Destinatario.AGRONOMO_O_GERENTE),
        tipo_falso("prueba_y", destinatario=Destinatario.AGRONOMO_Y_GERENTE),
        tipo_falso("prueba_g", destinatario=Destinatario.GERENTE),
    )


def sin_rol(invernadero, atributo, **extra):
    """La alerta «invernadero sin {rol} activo» de ``invernadero``, activa y para el Gerente, creada directo en la base."""
    return crear_alerta(
        invernadero,
        f"sin_{atributo}",
        clave_estado="",
        descripcion_alerta=NOMBRE_SIN_ROL[atributo],
        **extra,
    )


class UsrModUsrReactivacionServicioTests(ConGeoref, TestCase):
    """``reactivar_usuario`` con invernaderos a cargo: postcondiciones c y d de USR-MOD-USR y D8."""

    def setUp(self):
        self.gerente = crear_gerente()

    # ---- Postcondición c: se resuelve la alerta del rol ----

    def test_post_c_reactivar_resuelve_la_alerta_de_su_rol_en_cada_invernadero(self):
        """Postcondición c de USR-MOD-USR y regla 3 de 8.22: al reactivar la cuenta, la alerta «sin {rol} activo» de cada
        invernadero que sigue a su cargo pasa a «resuelta», con su fecha; sigue «no leída» (regla 7 de 8.18)."""
        capataz = crear_capataz_activo(activo=False)
        norte = crear_invernadero("Invernadero Norte", capataz=capataz)
        sur = crear_invernadero("Invernadero Sur", capataz=capataz)
        alertas_de_la_cuenta = [sin_rol(norte, "capataz"), sin_rol(sur, "capataz")]

        cuentas.reactivar_usuario(self.gerente, capataz.pk)

        for alerta in alertas_de_la_cuenta:
            with self.subTest(invernadero=alerta.invernadero_id):
                alerta.refresh_from_db()
                self.assertEqual(alerta.estado_alerta, "resuelta")
                self.assertIsNotNone(alerta.fecha_resolucion)
                self.assertEqual(alerta.estado_lectura_alerta, "no_leida")

    def test_post_c_no_resuelve_las_de_otros_roles(self):
        """D-43: la reactivación solo sincroniza el rol de la cuenta. La alerta «sin Vendedor» del mismo invernadero ya
        no corresponde (tiene un Vendedor activo), pero una sincronización completa la resolvería y esta no la toca.
        Control: la del Capataz se resuelve."""
        capataz = crear_capataz_activo(activo=False)
        invernadero = crear_invernadero("Invernadero Sur", capataz=capataz, vendedor=crear_vendedor())
        del_capataz = sin_rol(invernadero, "capataz")
        del_vendedor = sin_rol(invernadero, "vendedor")

        cuentas.reactivar_usuario(self.gerente, capataz.pk)

        del_capataz.refresh_from_db()
        del_vendedor.refresh_from_db()
        self.assertEqual(del_capataz.estado_alerta, "resuelta")
        self.assertEqual(del_vendedor.estado_alerta, "activa")
        self.assertIsNone(del_vendedor.fecha_resolucion)

    def test_post_c_invernadero_inactivo_no_cambia(self):
        """Post e de PROD-BAJ-INV: un invernadero inactivo no sincroniza sus alertas. Control: el activo de la misma cuenta
        sí resuelve la suya."""
        capataz = crear_capataz_activo(activo=False)
        activo = crear_invernadero("Invernadero Activo", capataz=capataz)
        inactivo = crear_invernadero("Invernadero Inactivo", activo=False, capataz=capataz)
        en_activo = sin_rol(activo, "capataz")
        en_inactivo = sin_rol(inactivo, "capataz")

        cuentas.reactivar_usuario(self.gerente, capataz.pk)

        en_activo.refresh_from_db()
        en_inactivo.refresh_from_db()
        self.assertEqual(en_activo.estado_alerta, "resuelta")
        self.assertEqual(en_inactivo.estado_alerta, "activa")

    # ---- D8: se aplica D4 de D-41 ----

    def test_d8_reactivar_al_agronomo_le_pasa_las_agronomo_o_gerente(self):
        """D8 (D4 de D-41): al reactivar al Agrónomo, las alertas ``AGRONOMO_O_GERENTE`` que habían ido al Gerente por falta
        de Agrónomo pasan a él y el Gerente deja de recibirlas."""
        agronomo = crear_agronomo(activo=False)
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        with tipos_de_agronomo():
            alerta = crear_alerta(invernadero, "prueba_o", para_gerente=True)

            cuentas.reactivar_usuario(self.gerente, agronomo.pk)

        alerta.refresh_from_db()
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (agronomo.pk, False))
        self.assertEqual(alerta.estado_alerta, "activa")

    def test_d8_suma_las_agronomo_y_gerente_y_el_gerente_sigue(self):
        """D8 (D4 de D-41): las ``AGRONOMO_Y_GERENTE`` suman al Agrónomo y el Gerente sigue recibiéndolas."""
        agronomo = crear_agronomo(activo=False)
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        with tipos_de_agronomo():
            alerta = crear_alerta(invernadero, "prueba_y", para_gerente=True)

            cuentas.reactivar_usuario(self.gerente, agronomo.pk)

        alerta.refresh_from_db()
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (agronomo.pk, True))

    def test_d8_las_de_tipo_gerente_no_se_tocan(self):
        """D8 (D4 de D-41): las de tipo ``GERENTE`` no se tocan. Control: la ``AGRONOMO_O_GERENTE`` del mismo invernadero
        sí pasa al Agrónomo."""
        agronomo = crear_agronomo(activo=False)
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        with tipos_de_agronomo():
            de_gerente = crear_alerta(invernadero, "prueba_g", para_gerente=True)
            de_agronomo = crear_alerta(invernadero, "prueba_o", para_gerente=True)

            cuentas.reactivar_usuario(self.gerente, agronomo.pk)

        de_gerente.refresh_from_db()
        de_agronomo.refresh_from_db()
        self.assertEqual((de_gerente.agronomo_id, de_gerente.para_gerente), (None, True))
        self.assertEqual((de_agronomo.agronomo_id, de_agronomo.para_gerente), (agronomo.pk, False))

    def test_d8_solo_en_los_invernaderos_que_sigue_teniendo_a_cargo(self):
        """D8: el Agrónomo recibe las alertas solo de los invernaderos que tiene a cargo. Control: en el suyo, sí."""
        agronomo = crear_agronomo(activo=False)
        otro_agronomo = crear_agronomo("otro.agronomo@infoponia.com")
        suyo = crear_invernadero("Invernadero Suyo", agronomo=agronomo)
        ajeno = crear_invernadero("Invernadero Ajeno", agronomo=otro_agronomo)
        with tipos_de_agronomo():
            en_suyo = crear_alerta(suyo, "prueba_o", para_gerente=True)
            en_ajeno = crear_alerta(ajeno, "prueba_o", para_gerente=True)

            cuentas.reactivar_usuario(self.gerente, agronomo.pk)

        en_suyo.refresh_from_db()
        en_ajeno.refresh_from_db()
        self.assertEqual((en_suyo.agronomo_id, en_suyo.para_gerente), (agronomo.pk, False))
        self.assertEqual((en_ajeno.agronomo_id, en_ajeno.para_gerente), (None, True))

    def test_d8_reactivar_al_agronomo_resuelve_su_alerta_de_rol(self):
        """Postcondición c de USR-MOD-USR: reactivar al Agrónomo resuelve la alerta «sin Agrónomo activo» del invernadero."""
        agronomo = crear_agronomo(activo=False)
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        sin_agronomo = sin_rol(invernadero, "agronomo")

        cuentas.reactivar_usuario(self.gerente, agronomo.pk)

        sin_agronomo.refresh_from_db()
        self.assertEqual(sin_agronomo.estado_alerta, "resuelta")

    # ---- Postcondición d: la auditoría ----

    def test_post_d_reactivar_audita_las_alertas_con_el_detalle_exacto(self):
        """Postcondición d de USR-MOD-USR, D-36 y D6 de D-41: la reactivación del Agrónomo audita, junto con la forma de
        acceso, las alertas resueltas y las traspasadas, cada una con su referencia; el invernadero figura entre los
        afectados."""
        agronomo = crear_agronomo(activo=False)
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        sin_agronomo = sin_rol(invernadero, "agronomo")
        with tipos_de_agronomo():
            de_agronomo = crear_alerta(invernadero, "prueba_o", para_gerente=True)
            de_los_dos = crear_alerta(invernadero, "prueba_y", para_gerente=True)

            cuentas.reactivar_usuario(self.gerente, agronomo.pk)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.REACTIVACION)
        self.assertEqual(registro.afectados, [afectado(agronomo), afectado_invernadero(invernadero)])
        self.assertEqual(
            registro.detalle,
            {
                "cambios": {"estado": {"antes": "inactivo", "despues": "activo"}},
                "datos": {
                    "acceso": "temporal",
                    "alertas_resueltas": [referencia(sin_agronomo)],
                    "alertas_traspasadas": [referencia(de_agronomo), referencia(de_los_dos)],
                },
            },
        )

    def test_d22_si_falla_la_auditoria_no_se_resuelven_alertas(self):
        """D-22: la reactivación, las alertas y su registro se guardan en la misma transacción. Cuando el registro falla,
        la alerta ya estaba resuelta (la prueba lo mide dentro) y vuelve a activa con la cuenta."""
        capataz = crear_capataz_activo(activo=False)
        invernadero = crear_invernadero("Invernadero Sur", capataz=capataz)
        alerta = sin_rol(invernadero, "capataz")
        vistas = []

        def falla(*args, **kwargs):
            vistas.append(Alerta.objects.filter(estado_alerta="resuelta").count())
            raise FallaDePrueba("falla")

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=falla):
            with self.assertRaises(FallaDePrueba):
                cuentas.reactivar_usuario(self.gerente, capataz.pk)

        alerta.refresh_from_db()
        self.assertEqual(vistas, [1])
        self.assertEqual(alerta.estado_alerta, "activa")
        self.assertFalse(Usuario.objects.get(pk=capataz.pk).is_active)

    # ---- Registro en core (regla A4 de D-37) ----

    def test_d43_maestros_registra_sus_efectos_de_reactivacion(self):
        """D-43 y A4 de D-37: ``MaestrosConfig.ready()`` registra en ``core.extensiones`` los efectos de la reactivación."""
        self.assertIn(invernaderos.efectos_de_reactivacion_de_cuenta, extensiones._EFECTOS_DE_REACTIVACION_DE_CUENTA)


class UsrModUsrReactivacionVistaTests(ConGeoref, TestCase):
    """Reactivar una cuenta con invernaderos a cargo en las pantallas (integración, postcondición c)."""

    def test_flujo_principal_reactivar_resuelve_las_alertas(self):
        """Flujo principal de USR-MOD-USR, postcondición c: al confirmar, la cuenta queda activa y la alerta de su rol, en
        cada invernadero a cargo, queda resuelta."""
        self.client.force_login(crear_gerente())
        capataz = crear_capataz_activo(activo=False)
        invernadero = crear_invernadero("Invernadero Sur", capataz=capataz)
        alerta = sin_rol(invernadero, "capataz")

        respuesta = self.client.post(reverse("core:usuario_reactivar", args=[capataz.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cuenta reactivada")
        alerta.refresh_from_db()
        self.assertTrue(Usuario.objects.get(pk=capataz.pk).is_active)
        self.assertEqual(alerta.estado_alerta, "resuelta")


class _Pausa:
    """Punto de parada de las pruebas de concurrencia: ``correr_a_la_vez(..., detener_antes_de=(pausa, "punto"))`` detiene a
    la operación ``primera`` justo ANTES de llamarlo, con lo que haya tomado hasta ahí (el invernadero bloqueado y la alerta
    todavía sin confirmar)."""

    def punto(self):
        """No hace nada: solo es el lugar donde se detiene ``primera``."""


pausa = _Pausa()


@tag("concurrencia")
class UsrModUsrConcurrenciaTests(TransactionTestCase):
    """Bloqueos de la reactivación de una cuenta con invernaderos a cargo (D-30, D-32, D-40 y D-43;
    docs/patrones/bloqueos.md): dos hilos, dos conexiones, el orden fijado con ``primera``
    (``core/tests/concurrencia.py``). Orden: la cuenta, los invernaderos a cargo (en orden de id) y las alertas de cada uno.
    Cada prueba corre los dos órdenes. Usan su propia geografía: el ``flush`` de un ``TransactionTestCase`` vacía Georef."""

    def setUp(self):
        self.gerente = crear_gerente()

    def crear_evento(self, invernadero, con_pausa=False):
        """Una operación de IoT simulada: crea una alerta de evento. Con ``con_pausa``, llama a ``pausa.punto()`` dentro de
        la transacción, después de crearla y antes de confirmar."""

        def operacion():
            with transaction.atomic():
                alerta = alertas.crear_alerta_de_evento(
                    invernadero.pk, "prueba_agronomo_o_gerente", "Lectura fuera de rango"
                )
                if con_pausa:
                    pausa.punto()
                return alerta

        return operacion

    def test_d8_reactivar_al_agronomo_y_alerta_nueva_a_la_vez_se_la_pasan(self):
        """P7, D8 (D4 de D-41): un creador (IoT) crea una alerta ``AGRONOMO_O_GERENTE`` mientras se reactiva al Agrónomo. Con
        el creador primero (el Agrónomo todavía está inactivo: la alerta va al Gerente, sin confirmar), la reactivación tiene
        que bloquear el invernadero ANTES de traspasar las alertas: espera al creador y, cuando sigue, ve su alerta y la pasa
        al Agrónomo. Sin ese bloqueo, ``bloquear_alertas_activas`` no ve la alerta sin confirmar y queda en el Gerente. Con la
        reactivación primera, el creador espera y calcula el destinatario con el Agrónomo ya activo. En los dos órdenes: la
        alerta queda con el Agrónomo y sin el Gerente."""
        tipo = tipo_falso("prueba_agronomo_o_gerente", destinatario=Destinatario.AGRONOMO_O_GERENTE)
        with tipo_de_alerta_de_prueba(tipo):
            for primera in ("a", "b"):
                with self.subTest(primera=primera):
                    agronomo = crear_agronomo(email=f"agronomo.{primera}@infoponia.com", activo=False)
                    invernadero = crear_invernadero_con_geografia_propia(f"Invernadero {primera}", agronomo=agronomo)
                    reactivar = lambda cuenta=agronomo: cuentas.reactivar_usuario(self.gerente, cuenta.pk)  # noqa: E731

                    if primera == "a":  # el creador va primero y se detiene con la alerta sin confirmar
                        resultados = correr_a_la_vez(
                            self.crear_evento(invernadero, con_pausa=True),
                            reactivar,
                            primera="a",
                            detener_antes_de=(pausa, "punto"),
                        )
                    else:  # la reactivación va primero (se detiene al auditar) y el creador espera
                        resultados = correr_a_la_vez(reactivar, self.crear_evento(invernadero), primera="a")

                    exitos, rechazos, otros = separar(resultados)
                    self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
                    alerta = Alerta.objects.get(invernadero=invernadero, tipo_alerta="prueba_agronomo_o_gerente")
                    self.assertEqual(alerta.agronomo_id, agronomo.pk)
                    self.assertFalse(alerta.para_gerente)
        with self.assertRaises(ValueError):
            tipo_de_alerta("prueba_agronomo_o_gerente")  # el tipo de prueba no quedó en el registro global
