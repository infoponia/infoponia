# Pruebas de PROD-MOD-CLT · Modificar Cultivo (docs/casos_de_uso/maestros/cultivos.md): renombrar y reactivar. Cita D-22 y D-36
# (auditoría), D-28 (sin cambios no se audita), NOT-01 / D-42 (notificaciones, docs/api/notificaciones.md) y los puntos de extensión
# de docs/api/extensiones_de_maestros.md.
#
# Servicios que se prueban (maestros/servicios/cultivos.py), tomados del módulo dentro de cada prueba:
#   modificar_cultivo(actor, cultivo_id, *, nombre) -> Cultivo; reactivar_cultivo(actor, cultivo_id) -> Cultivo;
#   aviso_de_renombre(actor, cultivo_id) -> AvisoDeRenombre(cantidad_de_semillas, invernaderos).
# Puntos de extensión con registrantes falsos: ``_SEMILLAS`` (pares contar, renombrar) y ``_USOS_DE_CULTIVO``.
#
# Texto de la notificación (decidido con el estudiante el 20/11/2026; el caso de uso no lo fija): título «Cambió el cultivo
# {anterior}»; detalle «{Nombre Apellido de quien renombró} lo renombró a {nuevo}. Sus variedades siguen igual.». Una sola
# llamada a ``notificar_a_varios`` con ``excluir=actor``.

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase

from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    codigos_de,
    con_extension,
    crear_agronomo,
    crear_cultivo,
    crear_invernadero,
    crear_variedad,
    error_de,
)

from maestros.servicios import cultivos

MODIFICACION = RegistroAuditoria.Accion.MODIFICACION_CULTIVO
REACTIVACION = RegistroAuditoria.Accion.REACTIVACION_CULTIVO


class SemillasFalsas:
    """Un registrante falso de ``registrar_semillas_de_cultivo``: ``contar`` da ``cantidad`` y ``renombrar`` anota cada llamada
    (el actor, el nombre que ya tenía el cultivo, el anterior y si estaba dentro de una transacción)."""

    def __init__(self, cantidad=2):
        self.cantidad = cantidad
        self.llamadas = []

    def contar(self, cultivo):
        return self.cantidad

    def renombrar(self, actor, cultivo, nombre_anterior):
        self.llamadas.append((actor, cultivo.nombre_cultivo, nombre_anterior, connection.in_atomic_block))
        return self.cantidad

    def registrar(self):
        return con_extension("_SEMILLAS", (self.contar, self.renombrar))


class ProdModCltServicioTests(ConDatosDeMaestros, TestCase):
    """Reglas, precondiciones y postcondiciones de PROD-MOD-CLT."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Paz")
        self.cultivo = crear_cultivo("Lechuga")

    def renombrar(self, nombre, cultivo=None, actor=None):
        return cultivos.modificar_cultivo(actor or self.agronomo, (cultivo or self.cultivo).pk, nombre=nombre)

    # ---- precondiciones y reglas 1 y 2 ----

    def test_pre_a_un_gerente_no_modifica(self):
        """PROD-MOD-CLT precondición a: solo un Agrónomo activo."""
        with self.assertRaises(PermissionDenied):
            self.renombrar("Otro", actor=crear_gerente())

    def test_pre_a_un_capataz_no_modifica(self):
        """PROD-MOD-CLT precondición a."""
        with self.assertRaises(PermissionDenied):
            self.renombrar("Otro", actor=crear_capataz())

    def test_pre_a_un_cultivo_que_no_existe_da_404(self):
        """Un id inexistente da 404."""
        with self.assertRaises(Http404):
            cultivos.modificar_cultivo(self.agronomo, 999999, nombre="X")

    def test_regla_2_cualquier_agronomo_modifica_cualquier_cultivo(self):
        """PROD-MOD-CLT regla 2: no hay «a cargo»; un Agrónomo sin invernadero y otro con invernadero modifican."""
        otro = crear_agronomo(email="otro@infoponia.com")
        crear_invernadero("Inv", agronomo=otro)
        self.assertEqual(self.renombrar("Acelga", actor=otro).nombre_cultivo, "Acelga")

    def test_pre_b_el_nombre_nuevo_no_puede_repetirse(self):
        """PROD-MOD-CLT precondición b y regla 1: la regla 2 de PROD-ALT-CLT (sin distinguir mayúsculas ni espacios)."""
        crear_cultivo("Acelga")
        self.assertEqual(codigos_de(error_de(lambda: self.renombrar(" ACELGA ")), "nombre"), ["nombre_repetido"])
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.nombre_cultivo, "Lechuga")

    def test_pre_b_el_nombre_repetido_cuenta_tambien_entre_los_inactivos(self):
        """Regla 2 de PROD-ALT-CLT: activos o inactivos."""
        crear_cultivo("Acelga", activo=False)
        self.assertEqual(codigos_de(error_de(lambda: self.renombrar("Acelga")), "nombre"), ["nombre_repetido"])

    def test_pre_b_cambiar_solo_las_mayusculas_del_propio_nombre_se_permite(self):
        """El cultivo no choca consigo mismo."""
        self.assertEqual(self.renombrar("LECHUGA").nombre_cultivo, "LECHUGA")

    def test_regla_1_el_nombre_tiene_las_mismas_reglas_que_en_el_alta(self):
        """PROD-MOD-CLT regla 1: obligatorio, con contenido y de hasta 40 caracteres."""
        self.assertEqual(codigos_de(error_de(lambda: self.renombrar("")), "nombre"), ["obligatorio"])
        self.assertEqual(codigos_de(error_de(lambda: self.renombrar("---")), "nombre"), ["sin_contenido"])
        self.assertEqual(codigos_de(error_de(lambda: self.renombrar("x" * 41)), "nombre"), ["demasiado_largo"])

    # ---- regla 5 y 6 ----

    def test_regla_5_un_cultivo_inactivo_no_se_modifica(self):
        """PROD-MOD-CLT regla 5: solo se reactiva."""
        inactivo = crear_cultivo("Acelga", activo=False)
        error = error_de(lambda: self.renombrar("Otro", cultivo=inactivo))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["cultivo_inactivo"])

    def test_regla_6_reactivar_deja_el_cultivo_activo_sin_validaciones(self):
        """PROD-MOD-CLT regla 6 y postcondición c."""
        inactivo = crear_cultivo("Acelga", activo=False)
        self.assertEqual(cultivos.reactivar_cultivo(self.agronomo, inactivo.pk).estado_cultivo, "activo")

    def test_regla_6_reactivar_no_reactiva_sus_variedades(self):
        """PROD-MOD-CLT regla 6: se reactivan una por una con Modificar Variedad."""
        inactivo = crear_cultivo("Acelga", activo=False)
        variedad = crear_variedad(inactivo, "Común", activa=False)
        cultivos.reactivar_cultivo(self.agronomo, inactivo.pk)
        variedad.refresh_from_db()
        self.assertEqual(variedad.estado_variedad, "inactivo")

    def test_regla_6_reactivar_solo_vale_para_un_cultivo_inactivo(self):
        """Un cultivo activo no se reactiva (``cultivo_no_inactivo``)."""
        error = error_de(lambda: cultivos.reactivar_cultivo(self.agronomo, self.cultivo.pk))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["cultivo_no_inactivo"])

    def test_regla_2_reactivar_lo_hace_cualquier_agronomo_activo_y_no_el_gerente(self):
        """PROD-MOD-CLT regla 2 y precondición a, también para reactivar."""
        inactivo = crear_cultivo("Acelga", activo=False)
        with self.assertRaises(PermissionDenied):
            cultivos.reactivar_cultivo(crear_gerente(), inactivo.pk)
        self.assertTrue(cultivos.reactivar_cultivo(crear_agronomo(email="otro@infoponia.com"), inactivo.pk).activo)

    # ---- postcondición a y regla 3: semillas ----

    def test_post_a_el_cultivo_queda_con_el_nombre_nuevo(self):
        """PROD-MOD-CLT postcondición a."""
        self.renombrar("Lechuga criolla")
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.nombre_cultivo, "Lechuga criolla")

    def test_post_a_se_renombran_las_semillas_dentro_de_la_transaccion_con_el_cultivo_ya_renombrado(self):
        """PROD-MOD-CLT postcondición a y regla 3: ``renombrar_semillas`` recibe (actor, cultivo, nombre anterior); lo
        registra INV-03. El registrante ve el cultivo con su nombre nuevo."""
        falsas = SemillasFalsas()
        with falsas.registrar():
            self.renombrar("Lechuga criolla")
        self.assertEqual(falsas.llamadas, [(self.agronomo, "Lechuga criolla", "Lechuga", True)])

    def test_regla_3_el_sistema_informa_antes_de_confirmar_cuantas_semillas_cambian(self):
        """PROD-MOD-CLT regla 3: ``contar_semillas_a_renombrar`` sin cambiar nada."""
        with SemillasFalsas(cantidad=3).registrar():
            aviso = cultivos.aviso_de_renombre(self.agronomo, self.cultivo.pk)
        self.assertEqual(aviso.cantidad_de_semillas, 3)
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.nombre_cultivo, "Lechuga")
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_3_sin_registrantes_no_hay_semillas_que_renombrar(self):
        """«Cómo se aplica»: sin registrantes (hasta INV-03), 0 semillas."""
        aviso = cultivos.aviso_de_renombre(self.agronomo, self.cultivo.pk)
        self.assertEqual((aviso.cantidad_de_semillas, aviso.invernaderos), (0, []))

    def test_regla_3_si_el_renombre_de_las_semillas_falla_no_queda_nada(self):
        """D-22: todo o nada; sin cambio de nombre, sin notificaciones y sin registro de auditoría."""

        def falla(actor, cultivo, nombre_anterior):
            raise RuntimeError("falla de prueba")

        otro = crear_agronomo(email="otro@infoponia.com")
        inv = crear_invernadero("Inv", agronomo=otro)
        with con_extension("_SEMILLAS", (lambda c: 1, falla)), con_extension("_USOS_DE_CULTIVO", lambda c: {inv.pk}):
            with self.assertRaises(RuntimeError):
                self.renombrar("Lechuga criolla")
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.nombre_cultivo, "Lechuga")
        self.assertFalse(Notificacion.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.exists())

    # ---- postcondición b y regla 4: notificaciones ----

    def crear_invernadero_de_otro(self, nombre, email, **extra):
        otro = crear_agronomo(email=email, **extra)
        return otro, crear_invernadero(nombre, agronomo=otro)

    def test_post_b_se_notifica_al_agronomo_de_cada_invernadero_que_usa_el_cultivo(self):
        """PROD-MOD-CLT postcondición b y regla 4: título y detalle con el nombre anterior y el nuevo; dentro de la transacción."""
        uno, inv_uno = self.crear_invernadero_de_otro("Inv Uno", "uno@infoponia.com")
        dos, inv_dos = self.crear_invernadero_de_otro("Inv Dos", "dos@infoponia.com")
        with con_extension("_USOS_DE_CULTIVO", lambda c: {inv_uno.pk, inv_dos.pk}):
            self.renombrar("Lechuga criolla")
        for agronomo in (uno, dos):
            with self.subTest(agronomo=agronomo.email):
                notificacion = Notificacion.objects.get(destinatario_id=agronomo.pk)
                self.assertEqual(notificacion.titulo, "Cambió el cultivo Lechuga")
                self.assertEqual(notificacion.detalle, "Ana Paz lo renombró a Lechuga criolla. Sus variedades siguen igual.")
        self.assertEqual(Notificacion.objects.count(), 2)

    def test_regla_4_no_se_notifica_al_actor_aunque_use_el_cultivo(self):
        """PROD-MOD-CLT regla 4: «salvo al actor»."""
        propio = crear_invernadero("Propio", agronomo=self.agronomo)
        otro, inv_otro = self.crear_invernadero_de_otro("Inv Otro", "otro@infoponia.com")
        with con_extension("_USOS_DE_CULTIVO", lambda c: {propio.pk, inv_otro.pk}):
            self.renombrar("Lechuga criolla")
        self.assertEqual(list(Notificacion.objects.values_list("destinatario_id", flat=True)), [otro.pk])

    def test_regla_4_un_agronomo_con_dos_invernaderos_recibe_una_sola_notificacion(self):
        """NOT-01, regla 5 de la API: una llamada a ``notificar_a_varios``, sin repetir cuentas."""
        otro, inv_uno = self.crear_invernadero_de_otro("Inv Uno", "otro@infoponia.com")
        inv_dos = crear_invernadero("Inv Dos", agronomo=otro)
        with con_extension("_USOS_DE_CULTIVO", lambda c: {inv_uno.pk, inv_dos.pk}):
            self.renombrar("Lechuga criolla")
        self.assertEqual(Notificacion.objects.filter(destinatario_id=otro.pk).count(), 1)

    def test_regla_4_un_invernadero_sin_agronomo_o_con_el_agronomo_inactivo_no_notifica_a_nadie(self):
        """Un rol sin responsable (``None``) o una cuenta inactiva no recibe avisos; el cambio no se bloquea."""
        sin_agronomo = crear_invernadero("Sin Agrónomo")
        inactivo, inv_inactivo = self.crear_invernadero_de_otro("Inv Inactivo", "inactivo@infoponia.com", activo=False)
        with con_extension("_USOS_DE_CULTIVO", lambda c: {sin_agronomo.pk, inv_inactivo.pk}):
            self.renombrar("Lechuga criolla")
        self.assertFalse(Notificacion.objects.exists())
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.nombre_cultivo, "Lechuga criolla")

    def test_regla_4_un_invernadero_inactivo_no_notifica(self):
        """Regla 4: un invernadero usa la variedad si está activo; el registrante informa solo activos, y se vuelve a verificar."""
        otro, inv = self.crear_invernadero_de_otro("Inv Dado de baja", "otro@infoponia.com")
        inv.estado_invernadero = "inactivo"
        inv.save()
        with con_extension("_USOS_DE_CULTIVO", lambda c: {inv.pk}):
            self.renombrar("Lechuga criolla")
        self.assertFalse(Notificacion.objects.exists())

    def test_regla_4_sin_registrantes_no_se_notifica_a_nadie(self):
        """«Cómo se aplica»: sin registrantes, ningún invernadero usa el cultivo."""
        crear_invernadero("Otro", agronomo=crear_agronomo(email="otro@infoponia.com"))
        self.renombrar("Lechuga criolla")
        self.assertFalse(Notificacion.objects.exists())

    def test_regla_3_el_aviso_dice_a_que_invernaderos_se_notifica(self):
        """PROD-MOD-CLT regla 4 y prototipo: el formulario informa los invernaderos cuyo Agrónomo recibirá el aviso (sin el del actor)."""
        propio = crear_invernadero("Propio", agronomo=self.agronomo)
        otro, inv_otro = self.crear_invernadero_de_otro("Inv Otro", "otro@infoponia.com")
        with con_extension("_USOS_DE_CULTIVO", lambda c: {propio.pk, inv_otro.pk}):
            aviso = cultivos.aviso_de_renombre(self.agronomo, self.cultivo.pk)
        self.assertEqual([i.pk for i in aviso.invernaderos], [inv_otro.pk])

    def test_post_b_la_notificacion_no_se_audita(self):
        """D-42: el texto del aviso no va al registro de auditoría."""
        otro, inv = self.crear_invernadero_de_otro("Inv Otro", "otro@infoponia.com")
        with con_extension("_USOS_DE_CULTIVO", lambda c: {inv.pk}):
            self.renombrar("Lechuga criolla")
        self.assertEqual(RegistroAuditoria.objects.count(), 1)
        self.assertNotIn("Cambió el cultivo", str(RegistroAuditoria.objects.get().detalle))

    # ---- postcondición d: auditoría ----

    def test_post_d_renombrar_audita_el_cambio_de_nombre(self):
        """PROD-MOD-CLT postcondición d y D-36: usuario, rol, cultivo y el cambio con antes y después."""
        self.renombrar("Lechuga criolla")
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        self.assertEqual([a["id"] for a in registro.afectados], [self.cultivo.pk])
        self.assertEqual(registro.detalle["cambios"], {"nombre": {"antes": "Lechuga", "despues": "Lechuga criolla"}})

    def test_post_d_el_registro_dice_cuantas_semillas_se_renombraron(self):
        """PROD-MOD-CLT postcondición d: el log por semilla lo escribe ``renombrar_semillas`` (INV-03); este lleva la cuenta."""
        with SemillasFalsas(cantidad=4).registrar():
            self.renombrar("Lechuga criolla")
        self.assertEqual(RegistroAuditoria.objects.get(accion=MODIFICACION).detalle["datos"], {"semillas_renombradas": 4})

    def test_post_d_sin_semillas_el_registro_no_lleva_datos(self):
        """Sin semillas renombradas no hay «datos»."""
        self.renombrar("Lechuga criolla")
        self.assertNotIn("datos", RegistroAuditoria.objects.get(accion=MODIFICACION).detalle)

    def test_post_c_reactivar_audita_la_reactivacion_con_el_cambio_de_estado(self):
        """PROD-MOD-CLT postcondición c y d: acción ``reactivacion_cultivo``."""
        inactivo = crear_cultivo("Acelga", activo=False)
        cultivos.reactivar_cultivo(self.agronomo, inactivo.pk)
        registro = RegistroAuditoria.objects.get(accion=REACTIVACION)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "inactivo", "despues": "activo"})
        self.assertEqual([a["id"] for a in registro.afectados], [inactivo.pk])

    def test_d28_guardar_sin_cambios_no_escribe_no_audita_ni_notifica(self):
        """D-28: con el mismo nombre (o con espacios al borde) no hay cambio: ni auditoría, ni semillas, ni avisos."""
        otro, inv = self.crear_invernadero_de_otro("Inv Otro", "otro@infoponia.com")
        falsas = SemillasFalsas()
        with falsas.registrar(), con_extension("_USOS_DE_CULTIVO", lambda c: {inv.pk}):
            self.renombrar("Lechuga")
            self.renombrar("  Lechuga  ")
        self.assertEqual(falsas.llamadas, [])
        self.assertFalse(RegistroAuditoria.objects.exists())
        self.assertFalse(Notificacion.objects.exists())

    def test_flujo_principal_renombrar_y_volver_a_consultar(self):
        """PROD-MOD-CLT, flujo principal."""
        self.renombrar("Lechuga criolla")
        self.assertEqual([c.nombre_cultivo for c in cultivos.consultar_cultivos(self.agronomo)], ["Lechuga criolla"])
