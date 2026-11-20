# Pruebas de las notificaciones y la campana (NOT-01, D-42; contrato en docs/api/notificaciones.md). Paso 1: el modelo.
# Paso 2: la API de core/notificaciones.py. Paso 3: los puntos de extensión. Paso 4: la campana.

import re
from datetime import timedelta
from unittest import mock

from django.db import transaction
from django.db.models import QuerySet
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core import extensiones, notificaciones
from core.models import (
    Agronomo,
    Capataz,
    Gerente,
    Notificacion,
    RegistroAuditoria,
    Tecnico,
    Transportista,
    Usuario,
    Vendedor,
)
from core.tests.fabricas import CLAVE, crear_administrador, crear_capataz, crear_cuenta, crear_gerente


class NotificacionModeloTests(TestCase):
    """Modelo ``core.Notificacion`` (D-42)."""

    def setUp(self):
        self.gerente = crear_gerente()

    def test_d42_nace_sin_leer(self):
        """D-42: ``leida`` es falso al crear."""
        notificacion = Notificacion.objects.create(destinatario=self.gerente, titulo="T", detalle="D")
        self.assertFalse(notificacion.leida)

    def test_d42_la_fecha_hora_es_la_de_la_creacion_y_tiene_zona(self):
        """D-42: ``fecha_hora`` es la de la creación, con zona horaria."""
        antes = timezone.now()
        notificacion = Notificacion.objects.create(destinatario=self.gerente, titulo="T", detalle="D")
        self.assertIsNotNone(notificacion.fecha_hora.tzinfo)
        self.assertGreaterEqual(notificacion.fecha_hora, antes)
        self.assertLessEqual(notificacion.fecha_hora, timezone.now())

    def test_d42_se_ordena_de_la_mas_reciente_a_la_mas_antigua(self):
        """D-42: ``Meta.ordering`` de la más reciente a la más antigua."""
        ahora = timezone.now()
        for titulo, hace in (("vieja", 3), ("nueva", 1), ("media", 2)):
            Notificacion.objects.create(
                destinatario=self.gerente, titulo=titulo, detalle="D", fecha_hora=ahora - timedelta(hours=hace)
            )
        self.assertEqual(list(Notificacion.objects.values_list("titulo", flat=True)), ["nueva", "media", "vieja"])

    def test_d42_el_orden_desempata_por_id_la_creada_despues_primero(self):
        """D-42: dos notificaciones del mismo instante: queda primera la creada después."""
        instante = timezone.now()
        primera = Notificacion.objects.create(destinatario=self.gerente, titulo="1", detalle="D", fecha_hora=instante)
        segunda = Notificacion.objects.create(destinatario=self.gerente, titulo="2", detalle="D", fecha_hora=instante)
        self.assertEqual(list(Notificacion.objects.all()), [segunda, primera])

    def test_d42_tiene_el_indice_por_destinatario_y_fecha_hora(self):
        """D-42: índice por ``(destinatario, fecha_hora)``."""
        campos = [tuple(indice.fields) for indice in Notificacion._meta.indexes]
        self.assertIn(("destinatario", "fecha_hora"), campos)

    def test_d42_la_cuenta_con_notificaciones_no_se_borra(self):
        """D-42: el destinatario es una clave protegida: no se borra nunca."""
        from django.db.models import ProtectedError

        capataz = crear_capataz()
        Notificacion.objects.create(destinatario=capataz, titulo="T", detalle="D")
        with self.assertRaises(ProtectedError):
            capataz.delete()


class _FallaDePrueba(Exception):
    """Para forzar que una transacción falle a mitad de camino."""


class NotificacionApiTests(TestCase):
    """API de ``core/notificaciones.py`` (D-42; docs/api/notificaciones.md)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.capataz = crear_capataz()
        self.agronomo = crear_cuenta(Agronomo, email="agro@infoponia.com")

    # ---- notificar ----

    def test_api_notificar_crea_una_notificacion_sin_leer_para_la_cuenta(self):
        """API, ``notificar``: crea una notificación para la cuenta y la devuelve."""
        notificacion = notificaciones.notificar(self.capataz, "Título", "Detalle")
        self.assertEqual(Notificacion.objects.count(), 1)
        self.assertEqual(notificacion.destinatario_id, self.capataz.pk)
        self.assertEqual((notificacion.titulo, notificacion.detalle), ("Título", "Detalle"))
        self.assertFalse(notificacion.leida)

    def test_api_notificar_acepta_una_cuenta_de_cualquiera_de_sus_roles(self):
        """API, ``notificar``: acepta ``Usuario`` o cualquiera de sus roles (``Agronomo``)."""
        como_usuario = Usuario.objects.get(pk=self.agronomo.pk)
        notificaciones.notificar(self.agronomo, "A", "D")
        notificaciones.notificar(como_usuario, "B", "D")
        self.assertEqual(Notificacion.objects.filter(destinatario_id=self.agronomo.pk).count(), 2)

    def test_api_notificar_rechaza_un_titulo_vacio_o_en_blanco(self):
        """API, ``notificar``: ``ValueError`` si el título está vacío (o solo espacios)."""
        for titulo in ("", "   "):
            with self.subTest(titulo=titulo), self.assertRaises(ValueError):
                notificaciones.notificar(self.capataz, titulo, "Detalle")
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_api_notificar_rechaza_un_detalle_vacio_o_en_blanco(self):
        """API, ``notificar``: ``ValueError`` si el detalle está vacío (o solo espacios)."""
        for detalle in ("", "   "):
            with self.subTest(detalle=detalle), self.assertRaises(ValueError):
                notificaciones.notificar(self.capataz, "Título", detalle)
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_api_notificar_acepta_el_largo_maximo_y_rechaza_uno_mas(self):
        """API, ``notificar`` y D-42: título hasta 120 y detalle hasta 500; uno más da ``ValueError``."""
        notificaciones.notificar(self.capataz, "t" * 120, "d" * 500)
        with self.assertRaises(ValueError):
            notificaciones.notificar(self.capataz, "t" * 121, "Detalle")
        with self.assertRaises(ValueError):
            notificaciones.notificar(self.capataz, "Título", "d" * 501)
        self.assertEqual(Notificacion.objects.count(), 1)

    # ---- notificar_al_gerente ----

    def test_api_notificar_al_gerente_la_crea_para_el_gerente_activo(self):
        """API, ``notificar_al_gerente``: la crea para el Gerente activo y la devuelve."""
        notificacion = notificaciones.notificar_al_gerente("Título", "Detalle")
        self.assertEqual(notificacion.destinatario_id, self.gerente.pk)
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_d14_notificar_al_gerente_sin_gerente_activo_no_hace_nada_y_no_falla(self):
        """D-14 y API: sin Gerente activo devuelve ``None``, no crea nada y no falla."""
        self.gerente.is_active = False
        self.gerente.save(update_fields=["is_active"])
        self.assertIsNone(notificaciones.notificar_al_gerente("Título", "Detalle"))
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_d14_notificar_al_gerente_sin_ningun_gerente_no_falla(self):
        """D-14: tampoco falla si nunca hubo un Gerente."""
        Usuario.objects.filter(pk=self.gerente.pk).delete()
        self.assertIsNone(notificaciones.notificar_al_gerente("Título", "Detalle"))

    def test_d09_notificar_al_gerente_no_la_crea_para_un_gerente_anterior_inactivo(self):
        """D-09 y API: con un Gerente inactivo y uno activo, solo recibe el activo."""
        self.gerente.is_active = False
        self.gerente.save(update_fields=["is_active"])
        nuevo = crear_gerente(email="nuevo.gerente@infoponia.com")
        notificacion = notificaciones.notificar_al_gerente("Título", "Detalle")
        self.assertEqual(notificacion.destinatario_id, nuevo.pk)

    # ---- notificar_a_varios ----

    def test_api_notificar_a_varios_crea_una_por_cuenta(self):
        """API, ``notificar_a_varios``: una notificación por cuenta, y devuelve la lista."""
        creadas = notificaciones.notificar_a_varios([self.capataz, self.agronomo], "Título", "Detalle")
        self.assertEqual(len(creadas), 2)
        self.assertEqual({n.destinatario_id for n in creadas}, {self.capataz.pk, self.agronomo.pk})
        self.assertEqual(Notificacion.objects.count(), 2)

    def test_api_notificar_a_varios_no_repite_cuentas(self):
        """API: sin repetir cuentas, aunque la misma llegue como ``Usuario`` y como su rol."""
        como_usuario = Usuario.objects.get(pk=self.capataz.pk)
        creadas = notificaciones.notificar_a_varios([self.capataz, como_usuario, self.capataz], "T", "D")
        self.assertEqual(len(creadas), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario_id=self.capataz.pk).count(), 1)

    def test_api_notificar_a_varios_ignora_los_none(self):
        """API: sin ``None`` en la lista (un rol sin responsable)."""
        creadas = notificaciones.notificar_a_varios([None, self.capataz, None], "T", "D")
        self.assertEqual([n.destinatario_id for n in creadas], [self.capataz.pk])

    def test_api_notificar_a_varios_excluye_la_cuenta_indicada(self):
        """API: sin la cuenta ``excluir`` (el actor), aunque llegue como ``Usuario`` y no como su rol."""
        como_usuario = Usuario.objects.get(pk=self.gerente.pk)
        creadas = notificaciones.notificar_a_varios([self.gerente, self.capataz], "T", "D", excluir=como_usuario)
        self.assertEqual([n.destinatario_id for n in creadas], [self.capataz.pk])
        self.assertFalse(Notificacion.objects.filter(destinatario=self.gerente).exists())

    def test_api_notificar_a_varios_con_lista_vacia_devuelve_lista_vacia(self):
        """API: una lista vacía (o solo ``None``) no crea nada ni falla."""
        self.assertEqual(notificaciones.notificar_a_varios([], "T", "D"), [])
        self.assertEqual(notificaciones.notificar_a_varios([None], "T", "D"), [])
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_api_notificar_a_varios_valida_el_texto_aunque_no_haya_cuentas(self):
        """API: un título vacío es un error de uso, también con la lista vacía."""
        with self.assertRaises(ValueError):
            notificaciones.notificar_a_varios([], "", "D")

    def test_api_notificar_a_varios_no_crea_ninguna_si_el_texto_es_invalido(self):
        """API: ``ValueError`` por el texto, y no queda ninguna a medias."""
        with self.assertRaises(ValueError):
            notificaciones.notificar_a_varios([self.capataz, self.agronomo], "t" * 121, "D")
        self.assertEqual(Notificacion.objects.count(), 0)

    # ---- de_la_cuenta ----

    def test_api_de_la_cuenta_devuelve_solo_las_suyas_mas_recientes_primero(self):
        """API, ``de_la_cuenta``: las del usuario, más recientes primero, y solo las suyas."""
        ahora = timezone.now()
        vieja = Notificacion.objects.create(
            destinatario=self.capataz, titulo="vieja", detalle="D", fecha_hora=ahora - timedelta(hours=2)
        )
        nueva = Notificacion.objects.create(
            destinatario=self.capataz, titulo="nueva", detalle="D", fecha_hora=ahora - timedelta(hours=1)
        )
        Notificacion.objects.create(destinatario=self.gerente, titulo="ajena", detalle="D")
        self.assertEqual(list(notificaciones.de_la_cuenta(self.capataz)), [nueva, vieja])

    def test_api_de_la_cuenta_devuelve_un_queryset(self):
        """API: devuelve un ``QuerySet`` (la campana lo recorta y lo cuenta)."""
        self.assertIsInstance(notificaciones.de_la_cuenta(self.capataz), QuerySet)

    # ---- marcar_vistas ----

    def test_api_marcar_vistas_marca_leidas_las_indicadas_y_devuelve_la_cantidad(self):
        """API, ``marcar_vistas``: marca las del usuario con esos ids y devuelve la cantidad marcada."""
        a = Notificacion.objects.create(destinatario=self.capataz, titulo="a", detalle="D")
        b = Notificacion.objects.create(destinatario=self.capataz, titulo="b", detalle="D")
        c = Notificacion.objects.create(destinatario=self.capataz, titulo="c", detalle="D")
        self.assertEqual(notificaciones.marcar_vistas(self.capataz, [a.pk, b.pk]), 2)
        for notificacion in (a, b, c):
            notificacion.refresh_from_db()
        self.assertEqual((a.leida, b.leida, c.leida), (True, True, False))

    def test_api_marcar_vistas_ignora_las_ajenas(self):
        """API: ``marcar_vistas`` ignora las notificaciones de otra cuenta."""
        ajena = Notificacion.objects.create(destinatario=self.gerente, titulo="ajena", detalle="D")
        propia = Notificacion.objects.create(destinatario=self.capataz, titulo="propia", detalle="D")
        self.assertEqual(notificaciones.marcar_vistas(self.capataz, [ajena.pk, propia.pk]), 1)
        ajena.refresh_from_db()
        self.assertFalse(ajena.leida)

    def test_api_marcar_vistas_ignora_ids_que_no_existen_y_las_ya_leidas(self):
        """API: un id inexistente no falla y una ya leída no se cuenta otra vez."""
        leida = Notificacion.objects.create(destinatario=self.capataz, titulo="l", detalle="D", leida=True)
        self.assertEqual(notificaciones.marcar_vistas(self.capataz, [leida.pk, 999999]), 0)

    def test_api_marcar_vistas_con_lista_vacia_devuelve_cero(self):
        """API: sin ids no marca nada."""
        Notificacion.objects.create(destinatario=self.capataz, titulo="a", detalle="D")
        self.assertEqual(notificaciones.marcar_vistas(self.capataz, []), 0)
        self.assertFalse(Notificacion.objects.filter(leida=True).exists())

    # ---- pendientes_del_gerente ----

    def test_d14_pendientes_sin_registrantes_es_cero_y_lista_vacia(self):
        """D-14 y D-42: sin contadores registrados, la suma es 0 y el detalle, vacío."""
        with mock.patch.object(extensiones, "_CONTADORES_DE_PENDIENTES", []):
            self.assertEqual(notificaciones.pendientes_del_gerente(), (0, []))

    def test_d14_pendientes_suma_los_contadores_y_conserva_el_detalle(self):
        """D-42: ``(total, detalle)`` con la suma de todos los contadores y sus ``(descripción, cantidad)``."""
        uno = lambda: [("Alertas activas para el Gerente", 3)]  # noqa: E731
        otro = lambda: [("Órdenes de compra por aprobar", 2), ("Solicitudes de revisión", 1)]  # noqa: E731
        with mock.patch.object(extensiones, "_CONTADORES_DE_PENDIENTES", [uno, otro]):
            total, detalle = notificaciones.pendientes_del_gerente()
        self.assertEqual(total, 6)
        self.assertEqual(
            detalle,
            [
                ("Alertas activas para el Gerente", 3),
                ("Órdenes de compra por aprobar", 2),
                ("Solicitudes de revisión", 1),
            ],
        )

    def test_d14_pendientes_descarta_las_cantidades_en_cero(self):
        """API: el detalle trae solo las cantidades mayores que cero."""
        contador = lambda: [("Con algo", 2), ("Sin nada", 0)]  # noqa: E731
        with mock.patch.object(extensiones, "_CONTADORES_DE_PENDIENTES", [contador]):
            self.assertEqual(notificaciones.pendientes_del_gerente(), (2, [("Con algo", 2)]))

    # ---- transacción y auditoría ----

    def test_regla_1_si_la_transaccion_del_caso_de_uso_falla_no_queda_nada(self):
        """API, regla de uso 1: dentro de ``transaction.atomic()`` que falla no queda ninguna notificación.

        Alcanza con una ``TestCase``: el ``atomic`` interno es un punto de guardado que se deshace al fallar. Por eso
        no hace falta un ``TransactionTestCase`` ni el mixin de ``docs/patrones/datos_de_migracion.md`` (``core`` no
        carga datos por migración)."""
        with self.assertRaises(_FallaDePrueba):
            with transaction.atomic():
                notificaciones.notificar(self.capataz, "Uno", "D")
                notificaciones.notificar_al_gerente("Dos", "D")
                notificaciones.notificar_a_varios([self.agronomo], "Tres", "D")
                raise _FallaDePrueba()
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_regla_2_las_notificaciones_no_se_auditan(self):
        """D-42 y API, regla de uso 2: notificar no escribe en el registro de auditoría."""
        antes = RegistroAuditoria.objects.count()
        notificaciones.notificar(self.capataz, "Título", "Detalle")
        notificaciones.notificar_al_gerente("Título", "Detalle")
        notificaciones.notificar_a_varios([self.agronomo], "Título", "Detalle")
        self.assertEqual(RegistroAuditoria.objects.count(), antes)


class ExtensionesCampanaTests(TestCase):
    """Puntos de extensión de la campana en ``core/extensiones.py`` (D-42): se prueban con registrantes falsos, sin
    ``maestros``."""

    def setUp(self):
        self.usuario = crear_capataz()

    def _item(self, severidad, titulo="T", leida=False):
        return extensiones.ItemDeAlerta(severidad, titulo, "D", "/x/", leida)

    def test_d42_sin_fuentes_no_hay_alertas(self):
        """D-42: sin fuentes registradas, ``alertas_para`` devuelve una lista vacía."""
        with mock.patch.object(extensiones, "_FUENTES_DE_ALERTAS", []):
            self.assertEqual(extensiones.alertas_para(self.usuario), [])

    def test_d42_item_de_alerta_tiene_los_cinco_campos_de_la_api(self):
        """API: ``ItemDeAlerta`` es un namedtuple (severidad, titulo, detalle, url, leida)."""
        self.assertEqual(extensiones.ItemDeAlerta._fields, ("severidad", "titulo", "detalle", "url", "leida"))

    def test_d42_la_fuente_recibe_el_usuario(self):
        """D-42: cada fuente se llama con el usuario para el que se arma la campana."""
        fuente = mock.Mock(return_value=[])
        with mock.patch.object(extensiones, "_FUENTES_DE_ALERTAS", [fuente]):
            extensiones.alertas_para(self.usuario)
        fuente.assert_called_once_with(self.usuario)

    def test_d42_junta_las_alertas_de_todas_las_fuentes(self):
        """D-42: junta lo de todas las fuentes."""
        una = lambda usuario: [self._item("advertencia", "A")]  # noqa: E731
        otra = lambda usuario: [self._item("advertencia", "B")]  # noqa: E731
        with mock.patch.object(extensiones, "_FUENTES_DE_ALERTAS", [una, otra]):
            titulos = [item.titulo for item in extensiones.alertas_para(self.usuario)]
        self.assertEqual(titulos, ["A", "B"])

    def test_d42_ordena_por_severidad_critica_advertencia_informativa(self):
        """D-42: crítica, advertencia, informativa, venga como venga de las fuentes."""
        fuente = lambda usuario: [  # noqa: E731
            self._item("informativa", "i"),
            self._item("critica", "c"),
            self._item("advertencia", "a"),
        ]
        with mock.patch.object(extensiones, "_FUENTES_DE_ALERTAS", [fuente]):
            titulos = [item.titulo for item in extensiones.alertas_para(self.usuario)]
        self.assertEqual(titulos, ["c", "a", "i"])

    def test_d42_dentro_de_cada_nivel_conserva_el_orden_de_cada_fuente(self):
        """D-42: «dentro de cada nivel, como vengan»: el orden previo no se pierde."""
        una = lambda usuario: [  # noqa: E731
            self._item("advertencia", "a1"),
            self._item("critica", "c1"),
            self._item("advertencia", "a2"),
        ]
        otra = lambda usuario: [self._item("critica", "c2"), self._item("advertencia", "a3")]  # noqa: E731
        with mock.patch.object(extensiones, "_FUENTES_DE_ALERTAS", [una, otra]):
            titulos = [item.titulo for item in extensiones.alertas_para(self.usuario)]
        self.assertEqual(titulos, ["c1", "c2", "a1", "a2", "a3"])

    def test_d42_una_severidad_desconocida_va_al_final(self):
        """Una severidad que no es ninguna de las tres no se pierde: queda después de las conocidas."""
        fuente = lambda usuario: [self._item("rara", "r"), self._item("informativa", "i")]  # noqa: E731
        with mock.patch.object(extensiones, "_FUENTES_DE_ALERTAS", [fuente]):
            titulos = [item.titulo for item in extensiones.alertas_para(self.usuario)]
        self.assertEqual(titulos, ["i", "r"])

    def test_d42_registrar_fuente_es_idempotente_y_devuelve_la_funcion(self):
        """D-37 (A4): ``ready()`` puede correr más de una vez; registrar dos veces la misma no la duplica."""
        fuente = lambda usuario: [self._item("critica")]  # noqa: E731
        with mock.patch.object(extensiones, "_FUENTES_DE_ALERTAS", []):
            self.assertIs(extensiones.registrar_fuente_de_alertas(fuente), fuente)
            extensiones.registrar_fuente_de_alertas(fuente)
            self.assertEqual(len(extensiones.alertas_para(self.usuario)), 1)

    def test_d42_contadores_de_pendientes_juntos_en_el_orden_de_registro(self):
        """D-42: ``contadores_de_pendientes`` junta los de todos los registrantes, en el orden de registro."""
        uno = lambda: [("Uno", 1)]  # noqa: E731
        dos = lambda: [("Dos", 2), ("Tres", 3)]  # noqa: E731
        with mock.patch.object(extensiones, "_CONTADORES_DE_PENDIENTES", []):
            extensiones.registrar_contador_de_pendientes(uno)
            extensiones.registrar_contador_de_pendientes(dos)
            extensiones.registrar_contador_de_pendientes(uno)  # idempotente
            self.assertEqual(extensiones.contadores_de_pendientes(), [("Uno", 1), ("Dos", 2), ("Tres", 3)])

    def test_d37_core_no_importa_a_maestros(self):
        """Regla A1 de D-37: ni ``core.extensiones`` ni ``core.notificaciones`` importan ``maestros``."""
        import inspect
        import re

        for modulo in (extensiones, notificaciones):
            importa = re.search(r"^\s*(from|import)\s+maestros\b", inspect.getsource(modulo), re.MULTILINE)
            self.assertIsNone(importa, modulo.__name__)


HTMX = {"HTTP_HX_REQUEST": "true"}


def alerta(severidad="advertencia", titulo="Invernadero sin Capataz activo", leida=False, url="/produccion/1/"):
    """Un ``ItemDeAlerta`` de prueba."""
    return extensiones.ItemDeAlerta(severidad, titulo, "Invernadero Norte", url, leida)


class CampanaVistaTests(TestCase):
    """La campana del marco (NOT-01, D-42): el panel, el punto, las pestañas y marcar como leídas al cerrar."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.capataz = crear_capataz()
        self.otro = crear_cuenta(Agronomo, email="agro@infoponia.com")
        self.client = Client()
        self.client.login(email=self.capataz.email, password=CLAVE)
        self.url = reverse("core:campana")
        self.url_vista = reverse("core:campana_vista")
        # Sin las fuentes y los contadores reales (los de maestros): cada prueba registra los suyos.
        fuentes = mock.patch.object(extensiones, "_FUENTES_DE_ALERTAS", [])
        fuentes.start()
        self.addCleanup(fuentes.stop)

    def _con_alertas(self, *items):
        """Registra una fuente falsa que devuelve ``items`` para cualquier usuario."""
        extensiones.registrar_fuente_de_alertas(lambda usuario: list(items))

    def _notificar(self, destinatario, titulo, **extra):
        return Notificacion.objects.create(destinatario=destinatario, titulo=titulo, detalle="Detalle", **extra)

    def _panel(self):
        return self.client.get(self.url, **HTMX)

    # ---- el panel ----

    def test_d42_solo_ve_las_suyas(self):
        """D-42: las notificaciones salen de ``core.Notificacion`` del usuario: nunca las de otra cuenta."""
        self._notificar(self.capataz, "Mía")
        self._notificar(self.gerente, "Del Gerente")
        self._notificar(self.otro, "Del Agrónomo")
        contenido = self._panel().content.decode()
        self.assertIn("Mía", contenido)
        self.assertNotIn("Del Gerente", contenido)
        self.assertNotIn("Del Agrónomo", contenido)

    def test_d42_la_mas_reciente_arriba(self):
        """D-42: las notificaciones se listan de la más reciente a la más antigua."""
        ahora = timezone.now()
        self._notificar(self.capataz, "AAA vieja", fecha_hora=ahora - timedelta(hours=3))
        self._notificar(self.capataz, "BBB nueva", fecha_hora=ahora - timedelta(hours=1))
        self._notificar(self.capataz, "CCC media", fecha_hora=ahora - timedelta(hours=2))
        contenido = self._panel().content.decode()
        self.assertLess(contenido.index("BBB nueva"), contenido.index("CCC media"))
        self.assertLess(contenido.index("CCC media"), contenido.index("AAA vieja"))

    def test_d42_el_panel_muestra_las_30_mas_recientes(self):
        """D-42, «Tamaño»: el panel muestra las 30 más recientes; la 31 no aparece ni se manda para marcar."""
        ahora = timezone.now()
        for n in range(31):
            self._notificar(self.capataz, f"Aviso numero {n:02d}", fecha_hora=ahora - timedelta(minutes=n))
        respuesta = self._panel()
        contenido = respuesta.content.decode()
        self.assertIn("Aviso numero 29", contenido)
        self.assertNotIn("Aviso numero 30", contenido)
        ids = re.search(r'data-ids="([^"]*)"', contenido).group(1).split(",")
        self.assertEqual(len(ids), 30)

    def test_d42_la_pestana_de_notificaciones_cuenta_solo_las_sin_leer(self):
        """D-42: «Notificaciones (n sin leer)», y sin ninguna sin leer no lleva el número."""
        self._notificar(self.capataz, "Uno")
        self._notificar(self.capataz, "Dos")
        self._notificar(self.capataz, "Leída", leida=True)
        self.assertContains(self._panel(), "Notificaciones (2 sin leer)")
        Notificacion.objects.filter(destinatario=self.capataz).update(leida=True)
        contenido = self._panel().content.decode()
        self.assertNotIn("sin leer", contenido)
        self.assertIn("Notificaciones</a>", contenido)

    def test_d42_la_pestana_de_alertas_lista_y_cuenta_todas_las_activas_leidas_o_no(self):
        """D-42: «Alertas (n)» lista y cuenta todas las activas, también las ya leídas."""
        self._con_alertas(alerta(titulo="Una", leida=True), alerta(titulo="Dos", leida=False))
        contenido = self._panel().content.decode()
        self.assertIn("Alertas (2)", contenido)
        self.assertIn("Una", contenido)
        self.assertIn("Dos", contenido)

    def test_d42_la_alerta_lleva_al_enlace_que_dio_su_fuente_y_muestra_su_severidad(self):
        """D-42: cada alerta es un enlace a su ``url``, con el color de su severidad."""
        self._con_alertas(alerta(severidad="critica", url="/produccion/7/"))
        contenido = self._panel().content.decode()
        self.assertIn('href="/produccion/7/"', contenido)
        self.assertIn("sev-critica", contenido)

    def test_d42_las_alertas_van_por_severidad_critica_advertencia_informativa(self):
        """D-42: el orden de la pestaña de alertas es crítica, advertencia, informativa."""
        self._con_alertas(
            alerta("informativa", "III"), alerta("critica", "CCC"), alerta("advertencia", "AAA")
        )
        contenido = self._panel().content.decode()
        self.assertLess(contenido.index("CCC"), contenido.index("AAA"))
        self.assertLess(contenido.index("AAA"), contenido.index("III"))

    def test_d42_un_rol_sin_fuentes_muestra_alertas_cero_y_sus_notificaciones(self):
        """D-42, «Quién ve la campana»: un rol sin fuentes (el Capataz hoy) muestra «Alertas (0)» y sus notificaciones."""
        self._notificar(self.capataz, "Para el Capataz")
        contenido = self._panel().content.decode()
        self.assertIn("Alertas (0)", contenido)
        self.assertIn("No hay alertas activas.", contenido)
        self.assertIn("Para el Capataz", contenido)

    def test_d42_sin_notificaciones_dice_que_no_tiene(self):
        """Prototipo (``myNotif``): sin notificaciones, «No tiene notificaciones.»."""
        self.assertContains(self._panel(), "No tiene notificaciones.")

    def test_d42_la_pestana_por_defecto_es_alertas_si_hay_y_si_no_notificaciones(self):
        """Prototipo: ``S.ntab||(al.length?'al':'no')``: sin pedir pestaña, la de alertas si hay alertas."""
        self.assertIn('data-pestana="notificaciones"', self._panel().content.decode())
        self._con_alertas(alerta())
        self.assertIn('data-pestana="alertas"', self._panel().content.decode())

    def test_d42_la_pestana_pedida_manda_y_la_de_notificaciones_cuenta_como_vista(self):
        """D-42: ``?pestana=notificaciones`` abre esa pestaña, y como se ve, el panel queda marcado como visto."""
        self._con_alertas(alerta())
        contenido = self.client.get(self.url, {"pestana": "notificaciones"}, **HTMX).content.decode()
        self.assertIn('data-pestana="notificaciones"', contenido)
        self.assertIn('data-vistas="1"', contenido)
        otra = self.client.get(self.url, {"pestana": "alertas"}, **HTMX).content.decode()
        self.assertNotIn('data-vistas="1"', otra)

    def test_d42_abrir_el_panel_no_marca_nada_como_leido(self):
        """D-42: se marca al cerrar el panel, no al abrirlo (la apertura es una consulta, SEG-14)."""
        notificacion = self._notificar(self.capataz, "Sin leer")
        self._panel()
        self.client.get(self.url)
        notificacion.refresh_from_db()
        self.assertFalse(notificacion.leida)

    def test_d42_el_panel_lleva_la_hora_si_es_de_hoy_y_el_dia_si_no(self):
        """Prototipo (``when2``): la hora (HH:MM) si es de hoy, y día y mes (dd/mm) si no."""
        hoy = timezone.localtime().replace(hour=9, minute=5, second=0, microsecond=0)
        ayer = hoy - timedelta(days=3)
        self._notificar(self.capataz, "De hoy", fecha_hora=hoy if hoy <= timezone.now() else timezone.now())
        self._notificar(self.capataz, "De antes", fecha_hora=ayer)
        contenido = self._panel().content.decode()
        self.assertIn(ayer.strftime("%d/%m"), contenido)
        self.assertRegex(contenido, r'when2">\d\d:\d\d<')

    # ---- sin HTMX: la página completa ----

    def test_d42_sin_htmx_es_una_pagina_completa_con_las_dos_pestanas_y_cerrar(self):
        """D-42, sin JavaScript: el botón es un enlace a la página completa, con las dos pestañas y un «Cerrar»."""
        respuesta = self.client.get(self.url)
        self.assertTemplateUsed(respuesta, "core/campana.html")
        self.assertTemplateUsed(respuesta, "core/base_con_sesion.html")
        contenido = respuesta.content.decode()
        self.assertIn("Alertas (0)", contenido)
        self.assertIn("Notificaciones", contenido)
        self.assertIn(f'action="{self.url_vista}"', contenido)
        self.assertIn(">Cerrar<", contenido)

    def test_d42_con_htmx_es_solo_el_panel_sin_el_marco(self):
        """D-42: con HTMX llega el panel, no la página entera."""
        respuesta = self._panel()
        self.assertTemplateUsed(respuesta, "core/_campana_panel.html")
        self.assertTemplateNotUsed(respuesta, "core/base_con_sesion.html")

    def test_d42_el_cerrar_de_la_pagina_completa_manda_los_ids_solo_si_se_ve_la_pestana_de_notificaciones(self):
        """D-42: «las que se vieron»: la página manda los ids de las notificaciones solo si muestra esa pestaña."""
        notificacion = self._notificar(self.capataz, "Sin leer")
        en_alertas = self.client.get(self.url, {"pestana": "alertas"}).content.decode()
        self.assertNotIn(f'name="ids" value="{notificacion.pk}"', en_alertas)
        en_notificaciones = self.client.get(self.url, {"pestana": "notificaciones"}).content.decode()
        self.assertIn(f'name="ids" value="{notificacion.pk}"', en_notificaciones)

    # ---- el botón y el punto ----

    def _inicio(self):
        return self.client.get(reverse("core:inicio")).content.decode()

    def test_d42_el_boton_de_la_campana_esta_en_el_marco_de_todos_los_roles_operativos(self):
        """D-42, «Quién ve la campana»: todos los roles, con el marco de escritorio o el de celular."""
        for clase in (Gerente, Agronomo, Capataz, Vendedor, Transportista, Tecnico):
            with self.subTest(rol=clase.__name__):
                cuenta = clase.objects.filter(is_active=True).first() or crear_cuenta(
                    clase, email=f"{clase.__name__.lower()}@infoponia.com"
                )
                cliente = Client()
                cliente.login(email=cuenta.email, password=CLAVE)
                self.assertIn('id="campana-boton"', cliente.get(reverse("core:inicio")).content.decode())

    def test_d42_el_boton_sin_nada_pendiente_no_tiene_punto_ni_cantidad(self):
        """D-42: sin alertas no leídas ni notificaciones sin leer, no hay punto."""
        contenido = self._inicio()
        self.assertNotIn("dotn", contenido)
        self.assertIn('aria-label="Alertas y notificaciones"', contenido)

    def test_d42_el_punto_aparece_con_una_notificacion_sin_leer_y_lo_dice_por_texto(self):
        """D-42: punto rojo con una notificación sin leer; el ``aria-label`` también lo dice."""
        self._notificar(self.capataz, "Sin leer")
        contenido = self._inicio()
        self.assertIn("dotn", contenido)
        self.assertIn('aria-label="Alertas y notificaciones: 1 sin leer"', contenido)

    def test_d42_el_punto_aparece_con_una_alerta_activa_no_leida(self):
        """D-42: punto rojo si hay alguna alerta activa NO leída."""
        self._con_alertas(alerta(leida=False))
        self.assertIn("dotn", self._inicio())

    def test_d42_una_alerta_ya_leida_no_prende_el_punto_aunque_siga_activa(self):
        """D-42: el punto es por alertas no leídas; una leída sigue en la lista pero no prende el punto."""
        self._con_alertas(alerta(leida=True))
        self.assertNotIn("dotn", self._inicio())
        self.assertIn("Alertas (1)", self._panel().content.decode())

    def test_d42_el_punto_se_apaga_cuando_se_leyeron_todas_las_notificaciones(self):
        """D-42: con todas leídas, el punto desaparece."""
        self._notificar(self.capataz, "Leída", leida=True)
        self.assertNotIn("dotn", self._inicio())

    def test_d42_el_administrador_no_tiene_campana(self):
        """usuarios.md, «Pantallas»: el Administrador solo ve «Cuentas», sin campana: sin botón y la pantalla da 403."""
        administrador = crear_administrador()
        cliente = Client()
        cliente.login(email=administrador.email, password=CLAVE)
        self.assertNotIn("campana-boton", cliente.get(reverse("core:usuarios")).content.decode())
        self.assertEqual(cliente.get(self.url).status_code, 403)
        self.assertEqual(cliente.post(self.url_vista, {"ids": [1]}).status_code, 403)

    def test_d42_en_el_marco_de_celular_el_boton_mide_al_menos_44_px(self):
        """D-42, paso 4: en los roles de campo el botón mide 44 px (la regla está en la hoja de estilos)."""
        from pathlib import Path

        css = (Path(__file__).resolve().parents[1] / "static/core/css/infoponia.css").read_text(encoding="utf-8")
        regla = re.search(r"\.field \.icon-btn\{([^}]*)\}", css)
        self.assertIsNotNone(regla)
        self.assertIn("min-height:44px", regla.group(1))
        self.assertIn("min-width:44px", regla.group(1))
        self.assertIn('class="shell field"', self._inicio().replace("\n", " "))

    # ---- cerrar: marcar como leídas ----

    def test_d42_cerrar_marca_leidas_solo_las_mostradas(self):
        """D-42: al cerrar se marcan solo las notificaciones que se mandan (las mostradas); las demás siguen sin leer."""
        mostrada = self._notificar(self.capataz, "Mostrada")
        no_mostrada = self._notificar(self.capataz, "No mostrada")
        self.client.post(self.url_vista, {"ids": [mostrada.pk]}, **HTMX)
        mostrada.refresh_from_db()
        no_mostrada.refresh_from_db()
        self.assertTrue(mostrada.leida)
        self.assertFalse(no_mostrada.leida)

    def test_d42_otro_usuario_no_puede_marcar_las_ajenas(self):
        """D-42 y API: ``marcar_vistas`` ignora las ajenas, también si llegan por el POST."""
        ajena = self._notificar(self.gerente, "Del Gerente")
        propia = self._notificar(self.capataz, "Propia")
        self.client.post(self.url_vista, {"ids": [ajena.pk, propia.pk]}, **HTMX)
        ajena.refresh_from_db()
        propia.refresh_from_db()
        self.assertFalse(ajena.leida)
        self.assertTrue(propia.leida)

    def test_d42_cerrar_ignora_ids_mal_formados(self):
        """D-42: un id que no es un número no rompe el pedido ni marca nada."""
        notificacion = self._notificar(self.capataz, "Sin leer")
        respuesta = self.client.post(self.url_vista, {"ids": ["abc", "", "-1", "1;2"]}, **HTMX)
        self.assertEqual(respuesta.status_code, 200)
        notificacion.refresh_from_db()
        self.assertFalse(notificacion.leida)

    def test_d42_cerrar_con_htmx_devuelve_el_boton_actualizado_sin_el_punto(self):
        """D-42: tras cerrar, HTMX recibe el botón ya sin el punto si no queda nada sin leer."""
        notificacion = self._notificar(self.capataz, "Sin leer")
        respuesta = self.client.post(self.url_vista, {"ids": [notificacion.pk]}, **HTMX)
        contenido = respuesta.content.decode()
        self.assertIn('id="campana-boton"', contenido)
        self.assertNotIn("dotn", contenido)
        self.assertNotIn("<html", contenido)

    def test_d42_cerrar_deja_el_punto_si_quedan_sin_leer_fuera_del_panel(self):
        """D-42: una notificación que no se mostró sigue sin leer, y el botón conserva el punto."""
        self._notificar(self.capataz, "Mostrada")
        self._notificar(self.capataz, "Más allá del tope")
        mostrada = Notificacion.objects.filter(titulo="Mostrada").get()
        respuesta = self.client.post(self.url_vista, {"ids": [mostrada.pk]}, **HTMX)
        self.assertIn("dotn", respuesta.content.decode())

    def test_d42_cerrar_no_marca_leidas_las_alertas(self):
        """D-42: marcar una alerta como leída es de MAE-02b (``abrir_alerta``): cerrar la campana no la toca."""
        self._con_alertas(alerta(leida=False))
        respuesta = self.client.post(self.url_vista, {"ids": []}, **HTMX)
        self.assertIn("dotn", respuesta.content.decode())

    def test_d42_cerrar_sin_htmx_vuelve_a_la_pantalla_de_origen(self):
        """D-42, sin JavaScript: «Cerrar» marca y vuelve a la pantalla de la que se vino."""
        notificacion = self._notificar(self.capataz, "Sin leer")
        respuesta = self.client.post(self.url_vista, {"ids": [notificacion.pk], "next": "/usuarios/"})
        self.assertRedirects(respuesta, "/usuarios/", fetch_redirect_response=False)
        notificacion.refresh_from_db()
        self.assertTrue(notificacion.leida)

    def test_d42_cerrar_sin_htmx_no_redirige_a_un_sitio_externo_ni_a_la_campana(self):
        """Seguridad: ``next`` de otro sitio, o la propia campana, se ignora y se vuelve al inicio."""
        for destino in ("https://ejemplo.com/", "//ejemplo.com/", "/campana/", "/campana/vista/", "javascript:alert(1)"):
            with self.subTest(destino=destino):
                respuesta = self.client.post(self.url_vista, {"ids": [], "next": destino})
                self.assertRedirects(respuesta, reverse("core:inicio"), fetch_redirect_response=False)

    def test_d42_el_enlace_del_boton_lleva_la_pantalla_de_origen(self):
        """D-42, sin JavaScript: el enlace del botón recuerda de qué pantalla se vino, para volver al cerrar."""
        contenido = self.client.get(reverse("core:inicio")).content.decode()
        self.assertIn(f'href="{self.url}?next=/"', contenido)

    # ---- acceso ----

    def test_d42_sin_sesion_redirige_al_inicio_de_sesion(self):
        """SEG-08 y D-25: toda pantalla exige sesión; el panel y el POST también."""
        anonimo = Client()
        for respuesta in (anonimo.get(self.url), anonimo.post(self.url_vista, {"ids": [1]})):
            self.assertEqual(respuesta.status_code, 302)
            self.assertIn(reverse("core:iniciar_sesion"), respuesta["Location"])

    def test_d42_cada_pantalla_acepta_solo_su_metodo(self):
        """El panel solo se lee (GET) y marcar solo se escribe (POST): lo demás da 405."""
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(self.client.get(self.url_vista).status_code, 405)

    def test_d42_la_campana_no_audita(self):
        """D-42 y SEG-14: abrir y cerrar la campana no escribe en el registro de auditoría."""
        notificacion = self._notificar(self.capataz, "Sin leer")
        antes = RegistroAuditoria.objects.count()
        self._panel()
        self.client.post(self.url_vista, {"ids": [notificacion.pk]}, **HTMX)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
