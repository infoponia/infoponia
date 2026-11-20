# Pruebas de MAE-02b para USR-BAJ-USR (Baja Usuario) en lo que le toca a maestros: la postcondición e (una alerta «invernadero
# sin {rol} activo» para el Gerente por cada invernadero a cargo), la regla 4 (la ventana informa lo que la cuenta tiene
# asignado), la regla 4 de 8.22 del modelo de dominio (MD-61: las alertas activas del Agrónomo pasan al Gerente), D-22
# (todo en la misma transacción) y D-36 (qué se audita). Fuentes: docs/casos_de_uso/usuarios.md, docs/modelo/maestros.md,
# D-40, D-41 y D-43. ``baja_usuario`` es de core: maestros se registra en ``core/extensiones.py`` desde
# ``MaestrosConfig.ready()`` (regla A4 de D-37). Contrato que fijan estas pruebas (``maestros/servicios/invernaderos.py``):
#   efectos_de_baja_de_cuenta(actor, cuenta) -> Efecto(afectados, datos)
#   asignaciones_de_cuenta(cuenta) -> list[Asignacion(texto, cantidad, que_pasa)]
# Cada prueba arma sus propios datos. Los tipos de alerta de prueba se registran con ``tipo_de_alerta_de_prueba``.

from unittest import mock

from django.db import transaction
from django.test import TestCase, TransactionTestCase, tag
from django.urls import reverse

from core import extensiones
from core import servicios as cuentas
from core.extensiones import Efecto
from core.models import RegistroAuditoria, Usuario, referencia
from core.tests.concurrencia import correr_a_la_vez, separar
from core.tests.fabricas import afectado, crear_administrador, crear_gerente
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
    crear_tecnico,
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


def alerta_de(prueba, **filtros):
    """La alerta que cumple ``filtros``; si no hay ninguna, la prueba falla con un mensaje (no con ``DoesNotExist``)."""
    alerta = Alerta.objects.filter(**filtros).first()
    prueba.assertIsNotNone(alerta, f"no hay ninguna alerta con {filtros}")
    return alerta


def activas(**filtros):
    """Los códigos de tipo de las alertas activas que cumplen ``filtros``, ordenados."""
    return sorted(Alerta.objects.filter(estado_alerta="activa", **filtros).values_list("tipo_alerta", flat=True))


class UsrBajUsrServicioTests(ConGeoref, TestCase):
    """``baja_usuario`` con invernaderos a cargo: postcondiciones d y e, regla 4 de USR-BAJ-USR y MD-61."""

    def setUp(self):
        self.gerente = crear_gerente()

    # ---- Postcondición e: la alerta «sin {rol}» de cada invernadero a cargo ----

    def test_post_e_crea_la_alerta_del_rol_en_cada_invernadero_a_cargo(self):
        """Postcondición e de USR-BAJ-USR: si la cuenta tenía invernaderos a cargo, quedó para el Gerente una alerta
        «invernadero sin {rol} activo» por cada uno."""
        capataz = crear_capataz_activo()
        norte = crear_invernadero("Invernadero Norte", capataz=capataz)
        sur = crear_invernadero("Invernadero Sur", capataz=capataz)

        cuentas.baja_usuario(self.gerente, capataz.pk)

        for invernadero in (norte, sur):
            with self.subTest(invernadero=invernadero.nombre_invernadero):
                self.assertEqual(
                    Alerta.objects.filter(
                        invernadero=invernadero, tipo_alerta="sin_capataz", estado_alerta="activa"
                    ).count(),
                    1,
                )
        self.assertEqual(Alerta.objects.count(), 2)

    def test_post_e_la_alerta_es_para_el_gerente(self):
        """Postcondición e de USR-BAJ-USR y regla 3 de 8.22: la alerta nace activa, no leída, para el Gerente y sin
        Agrónomo, con la descripción del tipo."""
        capataz = crear_capataz_activo()
        invernadero = crear_invernadero("Invernadero Sur", agronomo=crear_agronomo(), capataz=capataz)

        cuentas.baja_usuario(self.gerente, capataz.pk)

        alerta = alerta_de(self, invernadero=invernadero)
        self.assertEqual(alerta.tipo_alerta, "sin_capataz")
        self.assertEqual(alerta.descripcion_alerta, "Invernadero sin Capataz activo")
        self.assertTrue(alerta.para_gerente)
        self.assertIsNone(alerta.agronomo_id)
        self.assertEqual((alerta.estado_alerta, alerta.estado_lectura_alerta), ("activa", "no_leida"))

    def test_post_e_por_rol_agronomo_capataz_y_vendedor(self):
        """Postcondición e de USR-BAJ-USR: vale para cada rol del invernadero, y solo se crea la alerta del rol de la
        cuenta."""
        for atributo, crear in (
            ("agronomo", crear_agronomo),
            ("capataz", crear_capataz_activo),
            ("vendedor", crear_vendedor),
        ):
            with self.subTest(rol=atributo):
                cuenta = crear(email=f"{atributo}.asignado@infoponia.com")
                invernadero = crear_invernadero(f"Invernadero {atributo}", **{atributo: cuenta})

                cuentas.baja_usuario(self.gerente, cuenta.pk)

                self.assertEqual(activas(invernadero=invernadero), [f"sin_{atributo}"])

    def test_post_e_un_invernadero_inactivo_no_la_recibe(self):
        """Post e de PROD-BAJ-INV: un invernadero inactivo «dejó de generar alertas». Control: el activo de la misma
        cuenta sí recibe la suya."""
        capataz = crear_capataz_activo()
        activo = crear_invernadero("Invernadero Activo", capataz=capataz)
        inactivo = crear_invernadero("Invernadero Inactivo", activo=False, capataz=capataz)

        cuentas.baja_usuario(self.gerente, capataz.pk)

        self.assertEqual(activas(invernadero=activo), ["sin_capataz"])
        self.assertFalse(Alerta.objects.filter(invernadero=inactivo).exists())

    def test_post_e_no_duplica_una_alerta_ya_activa(self):
        """Regla 7 de 8.18 y D-41: a lo sumo una alerta de estado activa por invernadero y tipo. Si un invernadero ya tenía su
        «sin Capataz» activa, la baja no crea otra y deja la misma. Control: el otro invernadero de la cuenta, sin alerta,
        sí recibe la suya."""
        capataz = crear_capataz_activo()
        con_alerta = crear_invernadero("Invernadero A", capataz=capataz)
        sin_alerta = crear_invernadero("Invernadero B", capataz=capataz)
        existente = crear_alerta(
            con_alerta, "sin_capataz", clave_estado="", descripcion_alerta=NOMBRE_SIN_ROL["capataz"]
        )

        cuentas.baja_usuario(self.gerente, capataz.pk)

        self.assertEqual(list(Alerta.objects.filter(invernadero=con_alerta, estado_alerta="activa")), [existente])
        self.assertEqual(activas(invernadero=sin_alerta), ["sin_capataz"])

    def test_post_e_tecnico_sin_iot_no_crea_alerta(self):
        """Regla 3 de 8.22 y regla 5 de PROD-ALT-INV: la alerta del Técnico solo cuenta con sistema IoT. Control: el
        Capataz del mismo invernadero sí la crea."""
        tecnico = crear_tecnico()
        capataz = crear_capataz_activo()
        invernadero = crear_invernadero("Invernadero Sur", capataz=capataz, tecnico=tecnico)

        cuentas.baja_usuario(self.gerente, tecnico.pk)
        self.assertFalse(Alerta.objects.exists())

        cuentas.baja_usuario(self.gerente, capataz.pk)
        self.assertEqual(activas(invernadero=invernadero), ["sin_capataz"])

    def test_d43_solo_sincroniza_el_rol_de_la_cuenta(self):
        """D-43: la baja sincroniza solo la alerta del rol de la cuenta. El invernadero también está sin Agrónomo y sin
        Vendedor, pero esas alertas no se crean ahora (control: la del Capataz sí)."""
        capataz = crear_capataz_activo()
        invernadero = crear_invernadero("Invernadero Sur", capataz=capataz)

        cuentas.baja_usuario(self.gerente, capataz.pk)

        self.assertEqual(activas(invernadero=invernadero), ["sin_capataz"])

    def test_d43_una_cuenta_sin_invernaderos_a_cargo_no_genera_efectos(self):
        """D-43: una cuenta que no tiene invernaderos (o de un rol que no los tiene) deja un ``Efecto`` vacío y ninguna
        alerta. Control: la misma función, con un invernadero a cargo, sí cambia algo."""
        vendedor_libre = crear_vendedor()
        crear_invernadero("Invernadero Sur", agronomo=crear_agronomo())
        con_invernadero = crear_capataz_activo()
        crear_invernadero("Invernadero Norte", capataz=con_invernadero)

        with transaction.atomic():
            vacio = invernaderos.efectos_de_baja_de_cuenta(self.gerente, vendedor_libre)
            self.assertEqual(vacio, Efecto([], {}))
            self.assertEqual(Alerta.objects.count(), 0)
            # ``core`` la llama con la cuenta ya inactiva.
            Usuario.objects.filter(pk=con_invernadero.pk).update(is_active=False)
            invernaderos.efectos_de_baja_de_cuenta(self.gerente, con_invernadero)
            self.assertEqual(Alerta.objects.count(), 1)

    # ---- Postcondición d: la auditoría ----

    def test_post_d_audita_las_alertas_creadas_con_el_detalle_exacto(self):
        """Postcondición d de USR-BAJ-USR, D-36 y D6 de D-41: el detalle suma ``datos.alertas_creadas`` con una
        referencia por alerta, en el orden de los invernaderos."""
        capataz = crear_capataz_activo()
        norte = crear_invernadero("Invernadero Norte", capataz=capataz)
        sur = crear_invernadero("Invernadero Sur", capataz=capataz)

        cuentas.baja_usuario(self.gerente, capataz.pk)

        alerta_norte = alerta_de(self, invernadero=norte)
        alerta_sur = alerta_de(self, invernadero=sur)
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.BAJA)
        self.assertEqual(registro.afectados, [afectado(capataz), afectado_invernadero(norte), afectado_invernadero(sur)])
        self.assertEqual(
            registro.detalle,
            {
                "cambios": {"estado": {"antes": "activo", "despues": "inactivo"}},
                "datos": {"alertas_creadas": [referencia(alerta_norte), referencia(alerta_sur)]},
            },
        )

    def test_post_d_los_invernaderos_figuran_entre_los_afectados_solo_si_cambio_algo(self):
        """Postcondición d de USR-BAJ-USR y D-36: figuran entre los afectados los invernaderos donde cambió alguna alerta.
        El que ya tenía su alerta activa (nada cambió) no figura."""
        capataz = crear_capataz_activo()
        con_cambio = crear_invernadero("Invernadero A", capataz=capataz)
        sin_cambio = crear_invernadero("Invernadero B", capataz=capataz)
        crear_alerta(sin_cambio, "sin_capataz", clave_estado="", descripcion_alerta=NOMBRE_SIN_ROL["capataz"])

        cuentas.baja_usuario(self.gerente, capataz.pk)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.afectados, [afectado(capataz), afectado_invernadero(con_cambio)])

    def test_d22_si_falla_la_auditoria_no_quedan_alertas(self):
        """D-22: la baja, las alertas y su registro se guardan en la misma transacción. Cuando el registro falla, la alerta
        ya estaba creada (la prueba lo mide dentro) y se deshace con la baja."""
        capataz = crear_capataz_activo()
        crear_invernadero("Invernadero Sur", capataz=capataz)
        vistas = []

        def falla(*args, **kwargs):
            vistas.append(Alerta.objects.filter(estado_alerta="activa").count())
            raise FallaDePrueba("falla")

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=falla):
            with self.assertRaises(FallaDePrueba):
                cuentas.baja_usuario(self.gerente, capataz.pk)

        self.assertEqual(vistas, [1])
        self.assertEqual(Alerta.objects.count(), 0)
        self.assertTrue(Usuario.objects.get(pk=capataz.pk).is_active)

    # ---- MD-61 (regla 4 de 8.22): las alertas del Agrónomo pasan al Gerente ----

    def test_regla_8_22_4_las_agronomo_o_gerente_pasan_al_gerente(self):
        """Regla 4 de 8.22 (MD-61) y D-41: en la baja del Agrónomo, sus alertas activas de tipo ``AGRONOMO_O_GERENTE``
        quedan sin Agrónomo y para el Gerente. Siguen activas."""
        agronomo = crear_agronomo()
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        with tipos_de_agronomo():
            alerta = crear_alerta(invernadero, "prueba_o", para_gerente=False, agronomo=agronomo)

            cuentas.baja_usuario(self.gerente, agronomo.pk)

        alerta.refresh_from_db()
        self.assertIsNone(alerta.agronomo_id)
        self.assertTrue(alerta.para_gerente)
        self.assertEqual(alerta.estado_alerta, "activa")

    def test_regla_8_22_4_las_agronomo_y_gerente_quedan_solo_para_el_gerente(self):
        """Regla 4 de 8.22 (MD-61) y D-41: las de tipo ``AGRONOMO_Y_GERENTE`` (que iban a los dos) quedan, sin Agrónomo,
        solo para el Gerente."""
        agronomo = crear_agronomo()
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        with tipos_de_agronomo():
            alerta = crear_alerta(invernadero, "prueba_y", para_gerente=True, agronomo=agronomo)

            cuentas.baja_usuario(self.gerente, agronomo.pk)

        alerta.refresh_from_db()
        self.assertIsNone(alerta.agronomo_id)
        self.assertTrue(alerta.para_gerente)

    def test_regla_8_22_4_las_de_tipo_gerente_no_se_tocan(self):
        """Regla 3 de 8.22 y D-41: las de tipo ``GERENTE`` no se tocan. Control: la ``AGRONOMO_O_GERENTE`` del mismo
        invernadero sí cambia."""
        agronomo = crear_agronomo()
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        with tipos_de_agronomo():
            de_gerente = crear_alerta(invernadero, "prueba_g", para_gerente=True)
            de_agronomo = crear_alerta(invernadero, "prueba_o", para_gerente=False, agronomo=agronomo)

            cuentas.baja_usuario(self.gerente, agronomo.pk)

        de_gerente.refresh_from_db()
        de_agronomo.refresh_from_db()
        self.assertEqual((de_gerente.agronomo_id, de_gerente.para_gerente), (None, True))
        self.assertEqual((de_agronomo.agronomo_id, de_agronomo.para_gerente), (None, True))

    def test_regla_8_22_4_traspasa_aunque_el_invernadero_este_inactivo(self):
        """Regla 4 de 8.22 (MD-61): el traspaso no depende del estado del invernadero. Una alerta activa del Agrónomo en
        un invernadero inactivo (cargada fuera de la API) pasa al Gerente igual. Control: la del invernadero activo, también."""
        agronomo = crear_agronomo()
        activo = crear_invernadero("Invernadero Activo", agronomo=agronomo)
        inactivo = crear_invernadero("Invernadero Inactivo", activo=False, agronomo=agronomo)
        with tipos_de_agronomo():
            en_activo = crear_alerta(activo, "prueba_o", para_gerente=False, agronomo=agronomo)
            en_inactivo = crear_alerta(inactivo, "prueba_o", para_gerente=False, agronomo=agronomo)

            cuentas.baja_usuario(self.gerente, agronomo.pk)

        for alerta in (en_activo, en_inactivo):
            with self.subTest(invernadero=alerta.invernadero_id):
                alerta.refresh_from_db()
                self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (None, True))
                self.assertEqual(alerta.estado_alerta, "activa")

    def test_regla_8_22_4_no_queda_ninguna_alerta_activa_del_agronomo(self):
        """Regla 4 de 8.22 (MD-61): después de la baja del Agrónomo no queda ninguna alerta activa a su nombre, en ningún
        invernadero. Uno de sus invernaderos se dio de baja antes con ``baja_invernadero``, que resuelve todas las suyas
        (de estado y de evento). Control: antes de la baja de la cuenta había una activa."""
        agronomo = crear_agronomo()
        activo = crear_invernadero("Invernadero Activo", agronomo=agronomo)
        dado_de_baja = crear_invernadero("Invernadero Viejo", agronomo=agronomo)
        with tipos_de_agronomo():
            crear_alerta(activo, "prueba_o", para_gerente=False, agronomo=agronomo)
            crear_alerta(dado_de_baja, "prueba_o", para_gerente=False, agronomo=agronomo)
            invernaderos.baja_invernadero(self.gerente, dado_de_baja.pk)
            self.assertEqual(Alerta.objects.filter(agronomo=agronomo, estado_alerta="activa").count(), 1)

            cuentas.baja_usuario(self.gerente, agronomo.pk)

        self.assertEqual(Alerta.objects.filter(agronomo=agronomo, estado_alerta="activa").count(), 0)

    def test_post_d_audita_las_alertas_traspasadas_con_el_detalle_exacto(self):
        """Postcondición d de USR-BAJ-USR, D-36 y D6 de D-41: la baja del Agrónomo audita las alertas creadas («sin
        Agrónomo») y las traspasadas, cada una con su referencia; el invernadero figura entre los afectados."""
        agronomo = crear_agronomo()
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        with tipos_de_agronomo():
            de_agronomo = crear_alerta(invernadero, "prueba_o", para_gerente=False, agronomo=agronomo)
            de_los_dos = crear_alerta(invernadero, "prueba_y", para_gerente=True, agronomo=agronomo)

            cuentas.baja_usuario(self.gerente, agronomo.pk)

        sin_agronomo = alerta_de(self, tipo_alerta="sin_agronomo")
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.afectados, [afectado(agronomo), afectado_invernadero(invernadero)])
        self.assertEqual(
            registro.detalle,
            {
                "cambios": {"estado": {"antes": "activo", "despues": "inactivo"}},
                "datos": {
                    "alertas_creadas": [referencia(sin_agronomo)],
                    "alertas_traspasadas": [referencia(de_agronomo), referencia(de_los_dos)],
                },
            },
        )

    # ---- Regla 4 de USR-BAJ-USR: lo que la ventana informa ----

    def test_regla_4_informa_los_invernaderos_activos_a_cargo_y_que_pasa(self):
        """Regla 4 de USR-BAJ-USR: antes de confirmar se informa cuántos invernaderos tiene la cuenta y qué pasará con
        cada uno. Solo cuentan los activos (el inactivo ya no genera alertas)."""
        capataz = crear_capataz_activo()
        crear_invernadero("Sur", capataz=capataz)
        crear_invernadero("norte", capataz=capataz)
        crear_invernadero("Viejo", activo=False, capataz=capataz)

        asignaciones = invernaderos.asignaciones_de_cuenta(capataz)

        self.assertEqual(len(asignaciones), 1)
        # Por nombre sin distinguir mayúsculas, como la regla 5 de PROD-CNS-INV: «norte» va antes que «Sur».
        self.assertEqual(asignaciones[0].texto, "Invernaderos a cargo: norte, Sur")
        self.assertEqual(asignaciones[0].cantidad, 2)
        self.assertIn("Invernadero sin Capataz activo", asignaciones[0].que_pasa)

    def test_regla_4_una_cuenta_sin_invernaderos_no_informa_nada(self):
        """Regla 4 de USR-BAJ-USR: una cuenta sin invernaderos a cargo (o de un rol que no los tiene) no informa nada.
        Control: una con uno informa."""
        con_invernadero = crear_capataz_activo()
        crear_invernadero("Invernadero Sur", capataz=con_invernadero)

        self.assertEqual(invernaderos.asignaciones_de_cuenta(crear_vendedor()), [])
        self.assertEqual(invernaderos.asignaciones_de_cuenta(self.gerente), [])
        self.assertEqual(invernaderos.asignaciones_de_cuenta(crear_administrador()), [])
        self.assertEqual(len(invernaderos.asignaciones_de_cuenta(con_invernadero)), 1)

    def test_regla_4_el_agronomo_informa_las_alertas_que_pasan_al_gerente(self):
        """Regla 4 de USR-BAJ-USR y MD-61: el Agrónomo informa, además de sus invernaderos, sus alertas activas, que pasan
        al Gerente."""
        agronomo = crear_agronomo()
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        with tipos_de_agronomo():
            crear_alerta(invernadero, "prueba_o", para_gerente=False, agronomo=agronomo)
            crear_alerta(invernadero, "prueba_y", para_gerente=True, agronomo=agronomo)

            asignaciones = invernaderos.asignaciones_de_cuenta(agronomo)

        self.assertEqual([a.texto for a in asignaciones], ["Invernaderos a cargo: Invernadero Sur", "Alertas activas"])
        self.assertEqual(asignaciones[1].cantidad, 2)
        self.assertIn("Gerente", asignaciones[1].que_pasa)

    def test_regla_4_el_agronomo_sin_alertas_no_informa_alertas(self):
        """Regla 4 de USR-BAJ-USR: sin alertas activas no se informa la línea de alertas (``N > 0``). Control: con una
        alerta sí aparece, con ``cantidad=1``."""
        agronomo = crear_agronomo()
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)

        sin_alertas = invernaderos.asignaciones_de_cuenta(agronomo)
        crear_alerta(invernadero, "prueba_o", para_gerente=False, agronomo=agronomo)
        con_una = invernaderos.asignaciones_de_cuenta(agronomo)

        self.assertEqual([a.texto for a in sin_alertas], ["Invernaderos a cargo: Invernadero Sur"])
        self.assertEqual([(a.texto, a.cantidad) for a in con_una if a.texto == "Alertas activas"], [("Alertas activas", 1)])

    def test_regla_4_el_n_de_alertas_coincide_con_las_traspasadas(self):
        """Regla 4 de USR-BAJ-USR: el N que informa la ventana es lo que la baja efectivamente traspasa, también las alertas
        de un invernadero inactivo (cargadas fuera de la API). Mismas alertas, no solo la misma cantidad."""
        agronomo = crear_agronomo()
        activo = crear_invernadero("Invernadero Activo", agronomo=agronomo)
        inactivo = crear_invernadero("Invernadero Inactivo", activo=False, agronomo=agronomo)
        with tipos_de_agronomo():
            esperadas = [
                crear_alerta(activo, "prueba_o", para_gerente=False, agronomo=agronomo),
                crear_alerta(activo, "prueba_y", para_gerente=True, agronomo=agronomo),
                crear_alerta(inactivo, "prueba_o", para_gerente=False, agronomo=agronomo),
            ]
            informadas = [a for a in invernaderos.asignaciones_de_cuenta(agronomo) if a.texto == "Alertas activas"]

            cuentas.baja_usuario(self.gerente, agronomo.pk)

        traspasadas = RegistroAuditoria.objects.get().detalle.get("datos", {}).get("alertas_traspasadas", [])
        self.assertEqual([a.cantidad for a in informadas], [3])
        self.assertEqual(len(traspasadas), 3)
        self.assertEqual(sorted(ref["id"] for ref in traspasadas), sorted(a.pk for a in esperadas))

    def test_regla_4_informar_no_cambia_nada_ni_audita(self):
        """Regla 4 de USR-BAJ-USR y SEG-14: informar lo que tiene asignado no cambia nada, ni bloquea, ni audita. Control:
        el resultado no está vacío."""
        agronomo = crear_agronomo()
        invernadero = crear_invernadero("Invernadero Sur", agronomo=agronomo)
        with tipos_de_agronomo():
            alerta = crear_alerta(invernadero, "prueba_o", para_gerente=False, agronomo=agronomo)

            asignaciones = invernaderos.asignaciones_de_cuenta(agronomo)

        alerta.refresh_from_db()
        self.assertEqual(len(asignaciones), 2)
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (agronomo.pk, False))
        self.assertEqual(Alerta.objects.count(), 1)
        self.assertTrue(Usuario.objects.get(pk=agronomo.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    # ---- Registro en core (regla A4 de D-37) ----

    def test_d43_maestros_registra_sus_efectos_y_asignaciones(self):
        """D-43 y A4 de D-37: ``MaestrosConfig.ready()`` registra en ``core.extensiones`` los efectos de la baja y las
        asignaciones de la cuenta."""
        self.assertIn(invernaderos.efectos_de_baja_de_cuenta, extensiones._EFECTOS_DE_BAJA_DE_CUENTA)
        self.assertIn(invernaderos.asignaciones_de_cuenta, extensiones._ASIGNACIONES_DE_CUENTA)


class UsrBajUsrVistaTests(ConGeoref, TestCase):
    """USR-BAJ-USR en las pantallas con invernaderos a cargo (integración, regla 4 y postcondición e)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.force_login(self.gerente)

    def test_regla_4_la_ventana_de_baja_lista_los_invernaderos(self):
        """Regla 4 de USR-BAJ-USR: la ventana de baja (HTMX) lista los invernaderos a cargo y qué pasará con ellos. Abrirla
        no cambia nada."""
        capataz = crear_capataz_activo()
        crear_invernadero("Invernadero Sur", capataz=capataz)

        respuesta = self.client.get(reverse("core:usuario_baja", args=[capataz.pk]), headers={"HX-Request": "true"})

        self.assertContains(respuesta, "Lo que tiene asignado")
        self.assertContains(respuesta, "Invernaderos a cargo: Invernadero Sur")
        self.assertContains(respuesta, "Invernadero sin Capataz activo")
        self.assertEqual(Alerta.objects.count(), 0)
        self.assertTrue(Usuario.objects.get(pk=capataz.pk).is_active)

    def test_d25_sin_javascript_la_ficha_trae_la_ventana_con_los_invernaderos(self):
        """Regla 4 de USR-BAJ-USR sin JavaScript: pedida sin ``HX-Request``, la ficha de la cuenta trae la ventana de baja
        con la lista de invernaderos."""
        capataz = crear_capataz_activo()
        crear_invernadero("Invernadero Sur", capataz=capataz)

        respuesta = self.client.get(reverse("core:usuario_baja", args=[capataz.pk]))

        self.assertContains(respuesta, "<html")
        self.assertContains(respuesta, "Lo que tiene asignado")
        self.assertContains(respuesta, "Invernaderos a cargo: Invernadero Sur")

    def test_flujo_principal_baja_con_invernaderos_crea_las_alertas(self):
        """Flujo principal de USR-BAJ-USR y postcondición e: al confirmar, la cuenta queda inactiva, se avisa y cada
        invernadero a cargo queda con su alerta."""
        capataz = crear_capataz_activo()
        norte = crear_invernadero("Invernadero Norte", capataz=capataz)
        sur = crear_invernadero("Invernadero Sur", capataz=capataz)

        respuesta = self.client.post(reverse("core:usuario_baja", args=[capataz.pk]), follow=True)

        self.assertRedirects(respuesta, reverse("core:usuario", args=[capataz.pk]))
        self.assertContains(respuesta, "Se dio de baja la cuenta de Nombre Apellido.")
        self.assertFalse(Usuario.objects.get(pk=capataz.pk).is_active)
        self.assertEqual(activas(invernadero=norte), ["sin_capataz"])
        self.assertEqual(activas(invernadero=sur), ["sin_capataz"])


class _Pausa:
    """Punto de parada de las pruebas de concurrencia: ``correr_a_la_vez(..., detener_antes_de=(pausa, "punto"))`` detiene a
    la operación ``primera`` justo ANTES de llamarlo, con lo que haya tomado hasta ahí (el invernadero bloqueado y la alerta
    todavía sin confirmar)."""

    def punto(self):
        """No hace nada: solo es el lugar donde se detiene ``primera``."""


pausa = _Pausa()


@tag("concurrencia")
class UsrBajUsrConcurrenciaTests(TransactionTestCase):
    """Bloqueos de la baja de una cuenta con invernaderos a cargo (D-30, D-32, D-40 y D-43; docs/patrones/bloqueos.md): dos
    hilos, dos conexiones, el orden fijado con ``primera`` (``core/tests/concurrencia.py``). Orden: la cuenta, los
    invernaderos a cargo (en orden de id) y las alertas de cada uno. Cada prueba corre los dos órdenes. Usan su propia
    geografía: el ``flush`` de un ``TransactionTestCase`` vacía Georef."""

    def setUp(self):
        self.gerente = crear_gerente()

    def test_post_e_baja_del_capataz_y_reactivacion_del_invernadero_a_la_vez_dejan_la_alerta(self):
        """P5, postcondición e de USR-BAJ-USR y post e de PROD-BAJ-INV: se reactiva un invernadero inactivo mientras se da de
        baja a su Capataz. Con la reactivación primera (activo y sin confirmar, ve al Capataz activo y no crea la alerta), la
        lista de invernaderos a cargo no puede filtrar por estado: la baja espera el bloqueo del invernadero, lo relee activo y
        crea la alerta. Si filtrara por activos (el invernadero todavía figura inactivo), no lo vería y quedaría un
        invernadero activo con un Capataz inactivo y sin alerta. Con la baja primera, la reactivación espera y sincroniza
        con el Capataz ya inactivo. En los dos órdenes: una sola alerta activa «sin Capataz»."""
        for primera in ("a", "b"):
            with self.subTest(primera=primera):
                capataz = crear_capataz_activo(email=f"capataz.{primera}@infoponia.com")
                invernadero = crear_invernadero_con_geografia_propia(
                    f"Invernadero {primera}", activo=False, capataz=capataz
                )

                resultados = correr_a_la_vez(
                    lambda inv=invernadero: invernaderos.reactivar_invernadero(self.gerente, inv.pk),
                    lambda cuenta=capataz: cuentas.baja_usuario(self.gerente, cuenta.pk),
                    primera=primera,
                )

                exitos, rechazos, otros = separar(resultados)
                self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
                self.assertTrue(Invernadero.objects.get(pk=invernadero.pk).activo)
                self.assertFalse(Usuario.objects.get(pk=capataz.pk).is_active)
                self.assertEqual(
                    Alerta.objects.filter(
                        invernadero=invernadero, tipo_alerta="sin_capataz", estado_alerta="activa"
                    ).count(),
                    1,
                )

    def test_regla_8_22_4_baja_del_agronomo_y_alerta_nueva_a_la_vez_la_dejan_para_el_gerente(self):
        """P6, regla 4 de 8.22 (MD-61): un creador (IoT) crea una alerta ``AGRONOMO_O_GERENTE`` mientras se da de baja al
        Agrónomo. Con el creador primero (la alerta va al Agrónomo, todavía sin confirmar), la baja tiene que bloquear el
        invernadero ANTES de traspasar las alertas: espera al creador y, cuando sigue, ve su alerta y la pasa al Gerente. Sin
        ese bloqueo, ``bloquear_alertas_activas`` no ve la alerta sin confirmar y queda con el Agrónomo dado de baja. Con la
        baja primera, el creador espera y calcula el destinatario con el Agrónomo ya inactivo. En los dos órdenes: la
        alerta queda sin Agrónomo y para el Gerente."""
        tipo = tipo_falso("prueba_agronomo_o_gerente", destinatario=Destinatario.AGRONOMO_O_GERENTE)
        with tipo_de_alerta_de_prueba(tipo):
            for primera in ("a", "b"):
                with self.subTest(primera=primera):
                    agronomo = crear_agronomo(email=f"agronomo.{primera}@infoponia.com")
                    invernadero = crear_invernadero_con_geografia_propia(f"Invernadero {primera}", agronomo=agronomo)
                    baja = lambda cuenta=agronomo: cuentas.baja_usuario(self.gerente, cuenta.pk)  # noqa: E731

                    if primera == "a":  # el creador va primero y se detiene con la alerta sin confirmar
                        resultados = correr_a_la_vez(
                            self.crear_evento(invernadero, con_pausa=True),
                            baja,
                            primera="a",
                            detener_antes_de=(pausa, "punto"),
                        )
                    else:  # la baja va primero (se detiene al auditar) y el creador espera
                        resultados = correr_a_la_vez(baja, self.crear_evento(invernadero), primera="a")

                    exitos, rechazos, otros = separar(resultados)
                    self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
                    alerta = Alerta.objects.get(invernadero=invernadero, tipo_alerta="prueba_agronomo_o_gerente")
                    self.assertIsNone(alerta.agronomo_id)
                    self.assertTrue(alerta.para_gerente)
        with self.assertRaises(ValueError):
            tipo_de_alerta("prueba_agronomo_o_gerente")  # el tipo de prueba no quedó en el registro global

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
