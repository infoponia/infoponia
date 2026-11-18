# Pruebas de AUD-CNS-REG · Consultar Registro de Auditoría (docs/casos_de_uso/auditoria.md, D-36).
#
# Servicios que se prueban (core/servicios.py), tomados de ``servicios`` dentro de cada prueba para que, mientras no
# existan, falle cada prueba por separado:
# - consultar_auditoria(actor, desde=None, hasta=None, quien_actuo=None, accion=None, afectado_id=None,
#   cuenta_id=None): registros que ``actor`` puede ver (regla 1, ``RegistroAuditoria.objects.visibles_para``),
#   filtrados (regla 2) y del más reciente al más viejo. ``desde`` y ``hasta`` son fechas, inclusive, en la zona
#   horaria del sistema; ``quien_actuo`` es el id de la cuenta que actuó o «infoponia»; ``afectado_id``, el id de
#   una cuenta afectada; ``cuenta_id``, una cuenta que actuó o fue afectada (el filtro de la ficha, regla 7).
#   Filtrar por una cuenta que no existe da Http404; el Gerente que filtra por una cuenta de Administrador recibe
#   PermissionDenied (D-28, D-36).
# - obtener_registro(actor, registro_id): un registro visible para ``actor``; inexistente, Http404; fuera del
#   alcance, PermissionDenied (D-28).
# - puede_ver_auditoria_de(actor, cuenta): si la ficha muestra «Ver auditoría» (regla 7).
#
# Las pantallas (lista y detalle de «Auditoría», y «Ver auditoría» en la ficha) se prueban en AudCnsRegVistaTests, después
# de escribirlas: no tienen reglas de negocio propias (CLAUDE.md).
#
# Los registros se escriben directo con el modelo (sin pasar por ``registrar`` ni por los servicios de cuentas),
# en el formato de D-36, para poder fijar la fecha y hora y para no depender de los servicios que prueban otros
# archivos.

from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import core.models as modelos
from core import servicios
from core.models import (
    Agronomo,
    Capataz,
    RegistroAuditoria,
    Tecnico,
    Transportista,
    Usuario,
    Vendedor,
    rol_de,
)
from core.tests.fabricas import (
    PATRON_INVITACION,
    administrador_inactivo,
    afectado,
    construir_url,
    crear_administrador,
    crear_capataz,
    crear_cuenta,
    crear_gerente,
)

Accion = RegistroAuditoria.Accion
ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
# Un detalle válido (D-36) para los registros que no necesitan uno en particular.
DETALLE_CAMBIO = {"cambios": {"telefono": {"antes": "", "despues": "1155554444"}}}


def anotar(usuario, accion, afectados, fecha_hora=None, detalle=None):
    """Escribe un registro de auditoría de ``usuario`` (``None`` si actuó InfoPonia) con los afectados en el
    formato de D-36 y lo devuelve. Con ``fecha_hora``, el registro queda con esa fecha y hora."""
    datos = {
        "usuario": usuario,
        "rol": modelos.ROL_INFOPONIA if usuario is None else rol_de(usuario),
        "accion": accion,
        "afectados": [afectado(cuenta) for cuenta in afectados],
        "detalle": detalle or {},
    }
    if fecha_hora is not None:
        datos["fecha_hora"] = fecha_hora
    return RegistroAuditoria.objects.create(**datos)


def ids(registros):
    """Los ids de ``registros``, en el orden en que vienen."""
    return [registro.pk for registro in registros]


def local(anio, mes, dia, hora=12, minuto=0):
    """Fecha y hora en la zona horaria del sistema (America/Argentina/Buenos_Aires)."""
    return datetime(anio, mes, dia, hora, minuto, tzinfo=ZONA)


class AudCnsRegServicioTests(TestCase):
    """Precondición, postcondición y reglas de AUD-CNS-REG en ``consultar_auditoria``, ``obtener_registro`` y
    ``puede_ver_auditoria_de``."""

    # ---- Precondición a ----

    def test_pre_a_rechaza_cuentas_que_no_son_gerente_ni_administrador_activos(self):
        """AUD-CNS-REG precondición a y SEG-13: solo consultan una cuenta activa de Gerente o de Administrador; los
        demás roles y las cuentas inactivas reciben PermissionDenied, al listar y al abrir un registro."""
        capataz = crear_capataz()
        registro = anotar(capataz, Accion.CAMBIO_CONTRASENA, [capataz])
        actores = [
            capataz,
            crear_cuenta(Agronomo, "agronomo@infoponia.com"),
            crear_cuenta(Vendedor, "vendedor@infoponia.com"),
            crear_cuenta(Transportista, "transportista@infoponia.com"),
            crear_cuenta(Tecnico, "tecnico@infoponia.com"),
            crear_gerente(activo=False),
            administrador_inactivo(),
        ]

        for actor in actores:
            with self.subTest(actor=actor.email):
                with self.assertRaises(PermissionDenied):
                    servicios.consultar_auditoria(actor)
                with self.assertRaises(PermissionDenied):
                    servicios.obtener_registro(actor, registro.pk)

    # ---- Regla 1: alcance ----

    def test_regla_1_administrador_ve_todos_los_registros(self):
        """AUD-CNS-REG regla 1: el Administrador consulta todos los registros, también los de otros
        Administradores, los del Gerente y los de las cuentas operativas."""
        administrador = crear_administrador()
        otro = crear_administrador(email="admin2@infoponia.com")
        gerente = crear_gerente()
        capataz = crear_capataz()
        registros = [
            anotar(administrador, Accion.BAJA, [otro]),
            anotar(administrador, Accion.ALTA, [gerente]),
            anotar(gerente, Accion.CAMBIO_CONTRASENA, [gerente]),
            anotar(gerente, Accion.MODIFICACION, [capataz]),
            anotar(capataz, Accion.CAMBIO_CONTRASENA, [capataz]),
            anotar(None, Accion.BAJA, [capataz]),
        ]

        self.assertCountEqual(ids(servicios.consultar_auditoria(administrador)), ids(registros))

    def test_regla_1_gerente_ve_lo_que_afecta_a_una_cuenta_operativa(self):
        """AUD-CNS-REG regla 1 (MD-58): el Gerente ve los registros de cuentas en los que fue afectada una cuenta de
        Agrónomo, Capataz, Vendedor, Transportista o Técnico, aunque haya actuado él, InfoPonia u otra cuenta, y
        aunque la cuenta afectada esté inactiva."""
        gerente = crear_gerente()
        inactiva = crear_capataz(email="inactiva@infoponia.com", is_active=False)
        visibles = [anotar(gerente, Accion.BAJA, [inactiva]), anotar(None, Accion.MODIFICACION, [inactiva])]
        for clase in (Agronomo, Capataz, Vendedor, Transportista, Tecnico):
            cuenta = crear_cuenta(clase, f"{clase.__name__.lower()}@infoponia.com")
            visibles.append(anotar(gerente, Accion.MODIFICACION, [cuenta]))

        self.assertCountEqual(ids(servicios.consultar_auditoria(gerente)), ids(visibles))

    def test_regla_1_gerente_ve_lo_que_hizo_una_cuenta_operativa(self):
        """AUD-CNS-REG regla 1: el Gerente ve los registros en los que actuó una cuenta operativa (por ejemplo, el
        cambio o la recuperación de su contraseña)."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        visibles = [
            anotar(capataz, Accion.CAMBIO_CONTRASENA, [capataz]),
            anotar(capataz, Accion.RECUPERACION_CONTRASENA, [capataz]),
        ]

        self.assertCountEqual(ids(servicios.consultar_auditoria(gerente)), ids(visibles))

    def test_regla_1_gerente_ve_la_vinculacion_de_su_cuenta_con_una_operativa(self):
        """AUD-CNS-REG regla 1: una vinculación en la que actuó el Gerente es visible si entre las afectadas hay
        una cuenta operativa (la otra cuenta de la persona)."""
        gerente = crear_gerente()
        agronomo = crear_cuenta(Agronomo, "agronomo@infoponia.com")
        vinculacion = anotar(gerente, Accion.VINCULACION, [gerente, agronomo])

        self.assertEqual(ids(servicios.consultar_auditoria(gerente)), [vinculacion.pk])

    def test_regla_1_gerente_no_ve_los_registros_solo_de_administradores_o_gerentes(self):
        """AUD-CNS-REG regla 1 (MD-58): el Gerente no consulta los registros de cuentas en los que solo
        intervienen Administradores o la cuenta del Gerente (las suyas y las de Gerentes anteriores), aunque
        haya actuado InfoPonia."""
        administrador = crear_administrador()
        otro = crear_administrador(email="admin2@infoponia.com")
        anterior = crear_gerente(email="anterior@infoponia.com", activo=False)
        gerente = crear_gerente()
        anotar(administrador, Accion.ALTA, [gerente])
        anotar(administrador, Accion.MODIFICACION, [anterior])
        anotar(administrador, Accion.BAJA, [otro])
        anotar(administrador, Accion.CAMBIO_CONTRASENA, [administrador])
        anotar(gerente, Accion.CAMBIO_CONTRASENA, [gerente])
        anotar(anterior, Accion.RECUPERACION_CONTRASENA, [anterior])
        anotar(None, Accion.BAJA, [anterior])

        self.assertEqual(ids(servicios.consultar_auditoria(gerente)), [])

    def test_regla_1_gerente_ve_las_acciones_que_no_son_de_cuentas(self):
        """AUD-CNS-REG regla 1 y D-36: el Gerente consulta todos los registros de los módulos de negocio. Un registro
        es «de cuentas» por su acción (``ACCIONES_DE_CUENTAS``): una acción fuera de ese conjunto es visible para el
        Gerente aunque solo intervengan él o un Administrador. Hoy no hay acciones de negocio, así que se simula
        pasando una acción de un conjunto al otro."""
        gerente = crear_gerente()
        administrador = crear_administrador()
        de_negocio = anotar(gerente, Accion.DESVINCULACION, [gerente])
        anotar(administrador, Accion.BAJA, [administrador])

        sin_desvinculacion = modelos.ACCIONES_DE_CUENTAS - {Accion.DESVINCULACION}
        con_desvinculacion = modelos.ACCIONES_DE_NEGOCIO | {Accion.DESVINCULACION}
        with (
            mock.patch.object(modelos, "ACCIONES_DE_CUENTAS", sin_desvinculacion),
            mock.patch.object(modelos, "ACCIONES_DE_NEGOCIO", con_desvinculacion),
        ):
            self.assertEqual(ids(servicios.consultar_auditoria(gerente)), [de_negocio.pk])

    def test_d36_cada_accion_esta_clasificada_en_cuentas_o_en_negocio(self):
        """D-36: cada valor de ``RegistroAuditoria.Accion`` está en ``ACCIONES_DE_CUENTAS`` o en
        ``ACCIONES_DE_NEGOCIO``, y en uno solo. Agregar una acción obliga a clasificarla: de eso depende qué ve el
        Gerente (regla 1). Los dos conjuntos tampoco nombran acciones que no existen (un error de tipeo o una
        acción borrada)."""
        for valor in Accion.values:
            with self.subTest(accion=valor):
                en_cuentas = valor in modelos.ACCIONES_DE_CUENTAS
                en_negocio = valor in modelos.ACCIONES_DE_NEGOCIO
                self.assertTrue(en_cuentas or en_negocio, "la acción no está clasificada")
                self.assertFalse(en_cuentas and en_negocio, "la acción está en los dos conjuntos")
        self.assertLessEqual(
            set(modelos.ACCIONES_DE_CUENTAS) | set(modelos.ACCIONES_DE_NEGOCIO), set(Accion.values)
        )

    def test_regla_1_visibles_para_otros_roles_o_inactivos_no_devuelve_nada(self):
        """AUD-CNS-REG regla 1: ``visibles_para`` es el único lugar del alcance (CLAUDE.md); para una cuenta que no
        es Gerente ni Administrador activos no devuelve ningún registro."""
        capataz = crear_capataz()
        anotar(capataz, Accion.CAMBIO_CONTRASENA, [capataz])

        for actor in (capataz, crear_gerente(activo=False), administrador_inactivo(), None):
            with self.subTest(actor=actor):
                self.assertFalse(RegistroAuditoria.objects.visibles_para(actor).exists())

    # ---- Regla 2: filtros y orden ----

    def test_regla_2_ordena_del_mas_reciente_al_mas_viejo(self):
        """AUD-CNS-REG regla 2: por defecto se muestran primero los registros más recientes; con la misma fecha y
        hora, primero el último que se agregó."""
        administrador = crear_administrador()
        viejo = anotar(administrador, Accion.BAJA, [administrador], fecha_hora=local(2026, 11, 1))
        nuevo = anotar(administrador, Accion.BAJA, [administrador], fecha_hora=local(2026, 11, 3))
        medio_1 = anotar(administrador, Accion.BAJA, [administrador], fecha_hora=local(2026, 11, 2))
        medio_2 = anotar(administrador, Accion.BAJA, [administrador], fecha_hora=local(2026, 11, 2))

        self.assertEqual(
            ids(servicios.consultar_auditoria(administrador)), [nuevo.pk, medio_2.pk, medio_1.pk, viejo.pk]
        )

    def test_regla_2_rango_de_fechas_inclusive_en_la_zona_del_sistema(self):
        """AUD-CNS-REG regla 2: el rango de fechas incluye el día «desde» y el día «hasta» completos, en la zona
        horaria del sistema (un registro de las 23:30 del día «hasta» en Buenos Aires, que en UTC ya es el día
        siguiente, entra; uno de las 00:10 del día siguiente, no)."""
        administrador = crear_administrador()
        antes = anotar(administrador, Accion.BAJA, [administrador], fecha_hora=local(2026, 11, 9, 23, 59))
        primero = anotar(administrador, Accion.BAJA, [administrador], fecha_hora=local(2026, 11, 10, 0, 0))
        ultimo = anotar(administrador, Accion.BAJA, [administrador], fecha_hora=local(2026, 11, 12, 23, 30))
        despues = anotar(administrador, Accion.BAJA, [administrador], fecha_hora=local(2026, 11, 13, 0, 10))

        with self.subTest("desde y hasta"):
            self.assertEqual(
                ids(servicios.consultar_auditoria(administrador, desde=date(2026, 11, 10), hasta=date(2026, 11, 12))),
                [ultimo.pk, primero.pk],
            )
        with self.subTest("solo desde"):
            self.assertEqual(
                ids(servicios.consultar_auditoria(administrador, desde=date(2026, 11, 13))), [despues.pk]
            )
        with self.subTest("solo hasta"):
            self.assertEqual(
                ids(servicios.consultar_auditoria(administrador, hasta=date(2026, 11, 9))), [antes.pk]
            )

    def test_regla_2_filtra_por_la_cuenta_que_actuo(self):
        """AUD-CNS-REG regla 2: el filtro por la cuenta que actuó deja solo sus registros, aunque otra cuenta la
        haya afectado a ella."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        propio = anotar(capataz, Accion.CAMBIO_CONTRASENA, [capataz])
        anotar(gerente, Accion.MODIFICACION, [capataz])

        self.assertEqual(ids(servicios.consultar_auditoria(gerente, quien_actuo=capataz.pk)), [propio.pk])

    def test_regla_2_filtra_por_infoponia_como_quien_actuo(self):
        """AUD-CNS-REG reglas 2 y 3: «infoponia» como cuenta que actuó deja los registros sin cuenta (los hizo
        InfoPonia)."""
        administrador = crear_administrador()
        del_sistema = anotar(None, Accion.BAJA, [administrador])
        anotar(administrador, Accion.BAJA, [administrador])

        self.assertEqual(
            ids(servicios.consultar_auditoria(administrador, quien_actuo="infoponia")), [del_sistema.pk]
        )

    def test_regla_2_filtra_por_accion(self):
        """AUD-CNS-REG regla 2: el filtro por acción deja solo los registros de esa acción."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        baja = anotar(gerente, Accion.BAJA, [capataz])
        anotar(gerente, Accion.MODIFICACION, [capataz])

        self.assertEqual(ids(servicios.consultar_auditoria(gerente, accion=Accion.BAJA)), [baja.pk])

    def test_regla_2_filtra_por_cuenta_afectada(self):
        """AUD-CNS-REG regla 2: el filtro por cuenta afectada deja los registros en los que esa cuenta figura
        entre las afectadas, sola o con otras; no los que solo hizo ella sobre otra cuenta."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        vendedor = crear_cuenta(Vendedor, "vendedor@infoponia.com")
        sola = anotar(gerente, Accion.BAJA, [capataz])
        con_otra = anotar(capataz, Accion.VINCULACION, [vendedor, capataz])
        anotar(gerente, Accion.BAJA, [vendedor])

        self.assertCountEqual(
            ids(servicios.consultar_auditoria(gerente, afectado_id=capataz.pk)), [sola.pk, con_otra.pk]
        )

    def test_regla_2_filtro_de_cuenta_que_actuo_o_fue_afectada(self):
        """AUD-CNS-REG reglas 2 y 7 y D-36: el filtro de la ficha deja los registros en los que la cuenta actuó o
        fue afectada."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        vendedor = crear_cuenta(Vendedor, "vendedor@infoponia.com")
        hizo = anotar(capataz, Accion.VINCULACION, [vendedor])
        recibio = anotar(gerente, Accion.MODIFICACION, [capataz])
        anotar(gerente, Accion.BAJA, [vendedor])

        self.assertCountEqual(ids(servicios.consultar_auditoria(gerente, cuenta_id=capataz.pk)), [hizo.pk, recibio.pk])

    def test_regla_2_los_filtros_se_combinan(self):
        """AUD-CNS-REG regla 2: los filtros se combinan; un registro tiene que cumplir todos."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        vendedor = crear_cuenta(Vendedor, "vendedor@infoponia.com")
        buscado = anotar(gerente, Accion.MODIFICACION, [capataz], fecha_hora=local(2026, 11, 10))
        anotar(gerente, Accion.MODIFICACION, [capataz], fecha_hora=local(2026, 11, 1))
        anotar(gerente, Accion.BAJA, [capataz], fecha_hora=local(2026, 11, 10))
        anotar(gerente, Accion.MODIFICACION, [vendedor], fecha_hora=local(2026, 11, 10))
        anotar(capataz, Accion.MODIFICACION, [capataz], fecha_hora=local(2026, 11, 10))

        resultado = servicios.consultar_auditoria(
            gerente,
            desde=date(2026, 11, 5),
            hasta=date(2026, 11, 15),
            quien_actuo=gerente.pk,
            accion=Accion.MODIFICACION,
            afectado_id=capataz.pk,
        )

        self.assertEqual(ids(resultado), [buscado.pk])

    def test_regla_1_los_filtros_no_amplian_el_alcance(self):
        """AUD-CNS-REG reglas 1 y 2: filtrar por la propia cuenta del Gerente no le muestra los registros que solo
        lo involucran a él o a un Administrador; solo los visibles."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        visible = anotar(gerente, Accion.MODIFICACION, [capataz])
        anotar(gerente, Accion.CAMBIO_CONTRASENA, [gerente])

        self.assertEqual(ids(servicios.consultar_auditoria(gerente, quien_actuo=gerente.pk)), [visible.pk])
        self.assertEqual(ids(servicios.consultar_auditoria(gerente, cuenta_id=gerente.pk)), [visible.pk])

    # ---- Cuentas por las que se puede filtrar (D-28 y D-36) ----

    def test_d28_gerente_que_filtra_por_un_administrador_recibe_403(self):
        """D-28 y D-36: filtrar por una cuenta de Administrador está fuera del alcance del Gerente (nunca aparece en
        un registro que él pueda ver) y da PermissionDenied, sea la cuenta que actuó, la afectada o la de la
        ficha."""
        gerente = crear_gerente()
        administrador = crear_administrador()

        for filtro in ("quien_actuo", "afectado_id", "cuenta_id"):
            with self.subTest(filtro=filtro):
                with self.assertRaises(PermissionDenied):
                    servicios.consultar_auditoria(gerente, **{filtro: administrador.pk})

    def test_d28_filtrar_por_una_cuenta_que_no_existe_da_404(self):
        """D-28: filtrar por un id de cuenta que no existe da Http404, para el Gerente y para el Administrador."""
        actores = (crear_gerente(), crear_administrador())
        inexistente = Usuario.objects.order_by("-pk").first().pk + 100

        for actor in actores:
            for filtro in ("quien_actuo", "afectado_id", "cuenta_id"):
                with self.subTest(actor=actor.email, filtro=filtro):
                    with self.assertRaises(Http404):
                        servicios.consultar_auditoria(actor, **{filtro: inexistente})

    def test_d36_gerente_filtra_por_si_mismo_y_por_un_gerente_anterior(self):
        """D-36: el Gerente puede filtrar por su propia cuenta y por la de un Gerente anterior (pueden aparecer en
        registros que él ve: por ejemplo, el Gerente anterior modificó a un Capataz), sin recibir un 403."""
        gerente = crear_gerente()
        anterior = crear_gerente(email="anterior@infoponia.com", activo=False)
        capataz = crear_capataz()
        del_anterior = anotar(anterior, Accion.MODIFICACION, [capataz])

        self.assertEqual(ids(servicios.consultar_auditoria(gerente, quien_actuo=anterior.pk)), [del_anterior.pk])
        self.assertEqual(ids(servicios.consultar_auditoria(gerente, quien_actuo=gerente.pk)), [])

    def test_d36_administrador_filtra_por_cualquier_cuenta(self):
        """D-36 y regla 1: el Administrador consulta todos los registros, así que puede filtrar por cualquier
        cuenta, también una operativa."""
        administrador = crear_administrador()
        capataz = crear_capataz()
        propio = anotar(capataz, Accion.CAMBIO_CONTRASENA, [capataz])

        self.assertEqual(ids(servicios.consultar_auditoria(administrador, cuenta_id=capataz.pk)), [propio.pk])

    # ---- Un registro ----

    def test_d28_obtener_registro_visible_inexistente_o_fuera_de_alcance(self):
        """AUD-CNS-REG regla 1 y D-28: un registro visible se devuelve; uno que no existe da Http404; uno fuera del
        alcance del Gerente, PermissionDenied."""
        gerente = crear_gerente()
        administrador = crear_administrador()
        capataz = crear_capataz()
        visible = anotar(gerente, Accion.MODIFICACION, [capataz])
        ajeno = anotar(administrador, Accion.ALTA, [gerente])

        self.assertEqual(servicios.obtener_registro(gerente, visible.pk), visible)
        self.assertEqual(servicios.obtener_registro(administrador, ajeno.pk), ajeno)
        with self.assertRaises(PermissionDenied):
            servicios.obtener_registro(gerente, ajeno.pk)
        with self.assertRaises(Http404):
            servicios.obtener_registro(gerente, ajeno.pk + 100)

    # ---- Regla 7: acceso desde la ficha ----

    def test_regla_7_puede_ver_auditoria_de_la_cuenta(self):
        """AUD-CNS-REG regla 7: el enlace «Ver auditoría» de la ficha se ofrece solo si quien mira puede filtrar por
        esa cuenta: el Gerente, por una cuenta operativa o de Gerente, no de Administrador; el Administrador, por
        cualquiera; ningún otro rol."""
        gerente = crear_gerente()
        administrador = crear_administrador()
        capataz = crear_capataz()

        self.assertTrue(servicios.puede_ver_auditoria_de(gerente, capataz))
        self.assertTrue(servicios.puede_ver_auditoria_de(gerente, gerente))
        self.assertFalse(servicios.puede_ver_auditoria_de(gerente, administrador))
        self.assertTrue(servicios.puede_ver_auditoria_de(administrador, gerente))
        self.assertTrue(servicios.puede_ver_auditoria_de(administrador, capataz))
        self.assertFalse(servicios.puede_ver_auditoria_de(capataz, capataz))
        gerente.is_active = False
        self.assertFalse(servicios.puede_ver_auditoria_de(gerente, capataz))

    # ---- Postcondición a y regla 6 ----

    def test_post_a_la_consulta_solo_lee(self):
        """AUD-CNS-REG postcondición a: consultar la lista (con filtros) y un registro no produce cambios: todas las
        sentencias son SELECT, como el pedido de recuperación de la 08."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        registro = anotar(gerente, Accion.MODIFICACION, [capataz])

        with CaptureQueriesContext(connection) as consultas:
            list(servicios.consultar_auditoria(gerente, cuenta_id=capataz.pk, accion=Accion.MODIFICACION))
            servicios.obtener_registro(gerente, registro.pk)

        escrituras = [
            consulta["sql"]
            for consulta in consultas.captured_queries
            if not consulta["sql"].lstrip().upper().startswith("SELECT")
        ]
        self.assertEqual(escrituras, [])

    def test_regla_6_la_consulta_no_se_audita(self):
        """AUD-CNS-REG regla 6 y SEG-14: consultar no agrega registros de auditoría."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        registro = anotar(gerente, Accion.MODIFICACION, [capataz])

        list(servicios.consultar_auditoria(gerente))
        servicios.obtener_registro(gerente, registro.pk)

        self.assertEqual(RegistroAuditoria.objects.count(), 1)


class AudCnsRegVistaTests(TestCase):
    """Flujos principales y reglas visibles de AUD-CNS-REG en las pantallas «Auditoría» (lista y detalle): alcance,
    filtros, paginado, solo lectura y la entrada desde la ficha de una cuenta (regla 7)."""

    def entrar(self, cuenta):
        """Abre la sesión de ``cuenta`` y devuelve el cliente de prueba."""
        self.client.force_login(cuenta)
        return self.client

    def lista(self, **filtros):
        """Pide la lista de auditoría con los filtros indicados (como parámetros de la URL)."""
        return self.client.get(reverse("core:auditoria"), filtros)

    @staticmethod
    def principal(respuesta):
        """Solo el contenido de la pantalla (el ``<main>``): el marco trae formularios POST propios (cerrar sesión,
        cambiar de cuenta) que no son de la pantalla."""
        texto = respuesta.content.decode()
        return texto[texto.index("<main") : texto.index("</main>")]

    # ---- Flujo principal ----

    def test_flujo_principal_el_administrador_ve_la_lista_del_mas_reciente_al_mas_viejo(self):
        """AUD-CNS-REG flujo principal y reglas 2 y 3: el Administrador abre «Auditoría» y ve fecha y hora, quién actuó
        con su rol en ese momento («InfoPonia» si actuó el Sistema), la acción y los afectados con su texto, del más
        reciente al más viejo, con un enlace al detalle de cada registro."""
        administrador = crear_administrador()
        gerente = crear_gerente()
        capataz = crear_capataz()
        viejo = anotar(gerente, Accion.MODIFICACION, [capataz], fecha_hora=local(2026, 11, 3, 9, 5))
        nuevo = anotar(None, Accion.BAJA, [capataz], fecha_hora=local(2026, 11, 10, 15, 30))
        self.entrar(administrador)

        respuesta = self.lista()

        self.assertEqual(respuesta.status_code, 200)
        contenido = self.principal(respuesta)
        self.assertLess(contenido.index("10/11/2026 15:30"), contenido.index("03/11/2026 09:05"))
        self.assertContains(respuesta, "InfoPonia")
        self.assertContains(respuesta, "Gabriela Sosa")
        self.assertContains(respuesta, "Gerente")  # el rol en ese momento
        self.assertContains(respuesta, "Modificación de cuenta")
        self.assertContains(respuesta, "Baja de cuenta")
        self.assertContains(respuesta, "Juan Pérez (capataz@infoponia.com)")
        self.assertContains(respuesta, reverse("core:auditoria_registro", args=[viejo.pk]))
        self.assertContains(respuesta, reverse("core:auditoria_registro", args=[nuevo.pk]))

    def test_flujo_principal_el_gerente_ve_solo_lo_de_su_alcance(self):
        """AUD-CNS-REG regla 1: el Gerente ve los registros de las cuentas operativas y no los que solo involucran a
        Administradores o a la cuenta del Gerente."""
        administrador = crear_administrador()
        gerente = crear_gerente()
        capataz = crear_capataz()
        visible = anotar(gerente, Accion.MODIFICACION, [capataz])
        ajeno = anotar(administrador, Accion.CAMBIO_CONTRASENA, [administrador])
        self.entrar(gerente)

        respuesta = self.lista()

        self.assertContains(respuesta, reverse("core:auditoria_registro", args=[visible.pk]))
        self.assertNotContains(respuesta, reverse("core:auditoria_registro", args=[ajeno.pk]))
        self.assertNotContains(respuesta, "Adrián Mena")

    def test_flujo_principal_detalle_con_cambios_y_datos(self):
        """AUD-CNS-REG flujo principal y regla 3: el detalle muestra fecha y hora, quién actuó con su rol del momento,
        la acción, los afectados con el texto guardado y la tabla Campo / Antes / Después (un valor nulo, como «—»);
        los datos de contexto van aparte."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        registro = anotar(
            gerente,
            Accion.REACTIVACION,
            [capataz],
            fecha_hora=local(2026, 11, 10, 15, 30),
            detalle={
                "cambios": {
                    "estado": {"antes": "inactivo", "despues": "activo"},
                    "grupo": {"antes": {"id": 4, "texto": "Grupo 4"}, "despues": None},
                },
                "datos": {"acceso": "invitacion"},
            },
        )
        self.entrar(gerente)

        respuesta = self.client.get(reverse("core:auditoria_registro", args=[registro.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Reactivación de cuenta")
        self.assertContains(respuesta, "10/11/2026 15:30:00")
        self.assertContains(respuesta, "Gabriela Sosa")
        self.assertContains(respuesta, "Juan Pérez (capataz@infoponia.com)")
        for texto in ("Campo", "Antes", "Después", "Estado", "Inactivo", "Activo", "Grupo de cuentas vinculadas"):
            self.assertContains(respuesta, texto)
        self.assertContains(respuesta, "Grupo 4")  # el texto que tenía el grupo en ese momento
        self.assertContains(respuesta, "—")  # el valor nuevo nulo
        self.assertContains(respuesta, "Datos del momento")
        self.assertContains(respuesta, "Forma de acceso")
        self.assertContains(respuesta, "Invitación por correo")

    def test_regla_3_registro_de_infoponia_se_muestra_como_infoponia(self):
        """AUD-CNS-REG regla 3: si actuó el Sistema (sin cuenta), en la lista y en el detalle figura «InfoPonia», sin
        rol."""
        administrador = crear_administrador()
        capataz = crear_capataz()
        registro = anotar(None, Accion.BAJA, [capataz])
        self.entrar(administrador)

        detalle = self.client.get(reverse("core:auditoria_registro", args=[registro.pk]))

        self.assertContains(detalle, "InfoPonia")
        self.assertNotContains(detalle, "Rol en ese momento")
        self.assertContains(self.lista(), "InfoPonia")

    def test_regla_3_los_textos_guardados_se_escapan(self):
        """AUD-CNS-REG regla 3: los nombres que alguien escribió en un alta se muestran como texto, nunca como HTML
        (ni en la lista ni en el detalle)."""
        administrador = crear_administrador()
        capataz = crear_capataz(first_name="<script>alert(1)</script>", last_name="Pérez")
        registro = anotar(administrador, Accion.ALTA, [capataz])
        self.entrar(administrador)

        for respuesta in (self.lista(), self.client.get(reverse("core:auditoria_registro", args=[registro.pk]))):
            with self.subTest(url=respuesta.request["PATH_INFO"]):
                self.assertNotContains(respuesta, "<script>alert(1)</script>")
                self.assertContains(respuesta, "&lt;script&gt;alert(1)&lt;/script&gt;")

    # ---- SEG-13: acceso ----

    def test_seg13_otros_roles_reciben_403_y_sin_sesion_va_al_inicio_de_sesion(self):
        """SEG-13 y precondición a: solo el Gerente y el Administrador entran; los demás roles reciben 403 (lista y
        detalle) y quien no tiene sesión va al inicio de sesión."""
        capataz = crear_capataz()
        registro = anotar(capataz, Accion.CAMBIO_CONTRASENA, [capataz])
        urls = (reverse("core:auditoria"), reverse("core:auditoria_registro", args=[registro.pk]))

        for url in urls:
            with self.subTest(url=url, quien="sin sesión"):
                self.assertRedirects(
                    self.client.get(url), f"{reverse('core:iniciar_sesion')}?next={url}", fetch_redirect_response=False
                )
        for cuenta in (capataz, crear_cuenta(Agronomo, "agronomo@infoponia.com"), crear_cuenta(Vendedor, "v@infoponia.com")):
            self.client.force_login(cuenta)
            for url in urls:
                with self.subTest(url=url, quien=cuenta.email):
                    self.assertEqual(self.client.get(url).status_code, 403)

    def test_seg13_el_menu_ofrece_auditoria_al_gerente_y_al_administrador(self):
        """AUD-CNS-REG: la entrada «Auditoría» del menú lateral la tienen el Gerente y el Administrador; el Agrónomo no."""
        for cuenta in (crear_gerente(), crear_administrador()):
            with self.subTest(cuenta=cuenta.email):
                self.client.force_login(cuenta)
                respuesta = self.client.get(reverse("core:auditoria"))
                self.assertContains(respuesta, "<span>Auditoría</span>")
                self.assertContains(respuesta, f'href="{reverse("core:auditoria")}"')
        self.client.force_login(crear_cuenta(Agronomo, "agronomo@infoponia.com"))
        self.assertNotContains(self.client.get(reverse("core:inicio")), "<span>Auditoría</span>")

    def test_d28_registro_fuera_de_alcance_da_403_e_inexistente_404(self):
        """AUD-CNS-REG regla 1 y D-28: abrir el detalle de un registro fuera del alcance del Gerente da 403; uno que no
        existe, 404."""
        administrador = crear_administrador()
        gerente = crear_gerente()
        ajeno = anotar(administrador, Accion.ALTA, [gerente])
        self.entrar(gerente)

        self.assertEqual(self.client.get(reverse("core:auditoria_registro", args=[ajeno.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("core:auditoria_registro", args=[ajeno.pk + 100])).status_code, 404)

    def test_d28_filtrar_por_una_cuenta_fuera_de_alcance_da_403_e_inexistente_404(self):
        """D-28 y D-36: filtrar la lista por un Administrador da 403 al Gerente y por una cuenta que no existe, 404
        (la cuenta que actuó, la afectada y la de la ficha)."""
        administrador = crear_administrador()
        gerente = crear_gerente()
        self.entrar(gerente)

        for parametro in ("actuo", "afectada", "cuenta"):
            with self.subTest(parametro=parametro):
                self.assertEqual(self.lista(**{parametro: administrador.pk}).status_code, 403)
                self.assertEqual(self.lista(**{parametro: administrador.pk + 100}).status_code, 404)

    # ---- Regla 2: filtros ----

    def test_regla_2_filtros_de_la_pantalla_se_combinan(self):
        """AUD-CNS-REG regla 2: la pantalla filtra por rango de fechas, cuenta que actuó, acción y cuenta afectada, y
        los filtros se combinan; el formulario conserva lo elegido."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        vendedor = crear_cuenta(Vendedor, "vendedor@infoponia.com", nombre="Vera", apellido="Díaz")
        buscado = anotar(gerente, Accion.MODIFICACION, [capataz], fecha_hora=local(2026, 11, 10))
        fuera_de_fecha = anotar(gerente, Accion.MODIFICACION, [capataz], fecha_hora=local(2026, 11, 1))
        otra_accion = anotar(gerente, Accion.BAJA, [capataz], fecha_hora=local(2026, 11, 10))
        otra_cuenta = anotar(gerente, Accion.MODIFICACION, [vendedor], fecha_hora=local(2026, 11, 10))
        otro_actor = anotar(capataz, Accion.MODIFICACION, [capataz], fecha_hora=local(2026, 11, 10))
        self.entrar(gerente)

        respuesta = self.lista(
            desde="2026-11-05",
            hasta="2026-11-15",
            actuo=gerente.pk,
            accion="modificacion",
            afectada=capataz.pk,
        )

        self.assertContains(respuesta, reverse("core:auditoria_registro", args=[buscado.pk]))
        for otro in (fuera_de_fecha, otra_accion, otra_cuenta, otro_actor):
            self.assertNotContains(respuesta, reverse("core:auditoria_registro", args=[otro.pk]))
        self.assertContains(respuesta, 'value="2026-11-05"')
        self.assertContains(respuesta, 'value="2026-11-15"')
        self.assertContains(respuesta, f'<option value="{gerente.pk}" selected>')

    def test_regla_2_filtra_por_infoponia_como_quien_actuo(self):
        """AUD-CNS-REG reglas 2 y 3: «InfoPonia» está entre las opciones de la cuenta que actuó y deja los registros del
        Sistema."""
        administrador = crear_administrador()
        del_sistema = anotar(None, Accion.BAJA, [administrador])
        de_una_cuenta = anotar(administrador, Accion.BAJA, [administrador])
        self.entrar(administrador)

        respuesta = self.lista(actuo="infoponia")

        self.assertContains(respuesta, reverse("core:auditoria_registro", args=[del_sistema.pk]))
        self.assertNotContains(respuesta, reverse("core:auditoria_registro", args=[de_una_cuenta.pk]))
        self.assertContains(respuesta, "InfoPonia (el Sistema)")

    def test_regla_2_las_opciones_de_cuenta_dependen_del_alcance(self):
        """AUD-CNS-REG regla 2 y D-36: el Gerente puede elegir todas las cuentas menos las de Administrador; el
        Administrador, todas."""
        administrador = crear_administrador()
        gerente = crear_gerente()
        crear_capataz()

        self.entrar(gerente)
        respuesta = self.lista()
        self.assertContains(respuesta, "Juan Pérez (Capataz)")
        self.assertContains(respuesta, "Gabriela Sosa (Gerente)")
        self.assertNotContains(respuesta, "Adrián Mena (Administrador)")

        self.entrar(administrador)
        self.assertContains(self.lista(), "Adrián Mena (Administrador)")

    def test_regla_2_filtro_mal_formado_informa_y_deja_la_lista_vacia(self):
        """AUD-CNS-REG regla 2: un rango de fechas al revés, una fecha que no es una fecha o una cuenta que no es un
        número se informan y la lista sale vacía, sin error del servidor."""
        administrador = crear_administrador()
        anotar(administrador, Accion.BAJA, [administrador])
        self.entrar(administrador)

        for filtros, mensaje in (
            ({"desde": "2026-11-15", "hasta": "2026-11-05"}, "La fecha «desde» es posterior a la fecha «hasta»."),
            ({"desde": "no-es-fecha"}, "Ingresá una fecha «desde» válida."),
            ({"actuo": "abc"}, "Elegí una cuenta de la lista."),
            ({"afectada": "abc"}, "Elegí una cuenta de la lista."),
            ({"cuenta": "-3"}, "Elegí una cuenta de la lista."),
        ):
            with self.subTest(filtros=filtros):
                respuesta = self.lista(**filtros)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, mensaje)
                self.assertContains(respuesta, "Corregí los filtros para ver registros.")

    def test_regla_2_pedido_de_htmx_recibe_solo_la_tabla(self):
        """AUD-CNS-REG regla 2 (D-24): un pedido de HTMX (los filtros y las páginas) recibe solo la tabla, sin el marco;
        el pedido normal, la pantalla entera."""
        administrador = crear_administrador()
        registro = anotar(administrador, Accion.BAJA, [administrador])
        self.entrar(administrador)

        parcial = self.client.get(reverse("core:auditoria"), headers={"HX-Request": "true"})
        completa = self.lista()

        self.assertContains(parcial, reverse("core:auditoria_registro", args=[registro.pk]))
        self.assertNotContains(parcial, "<html")
        self.assertNotContains(parcial, 'class="filters"')
        self.assertContains(completa, "<html")
        self.assertContains(completa, 'class="filters"')

    # ---- Paginado ----

    def test_regla_2_paginado_de_25_con_los_filtros_conservados(self):
        """AUD-CNS-REG regla 2 y D-36: la lista se pagina de a 25, del más reciente al más viejo; los enlaces de página
        conservan los filtros; una página fuera de rango muestra la última."""
        administrador = crear_administrador()
        registros = [
            anotar(administrador, Accion.MODIFICACION, [administrador], fecha_hora=local(2026, 11, 1 + n))
            for n in range(28)
        ]
        anotar(administrador, Accion.BAJA, [administrador])  # otra acción: no entra con el filtro
        self.entrar(administrador)

        primera = self.lista(accion="modificacion")
        segunda = self.lista(accion="modificacion", pagina=2)
        lejana = self.lista(accion="modificacion", pagina=99)

        self.assertContains(primera, "Registros 1 a 25 de 28")
        self.assertContains(primera, "Página 1 de 2")
        self.assertContains(primera, "accion=modificacion&amp;pagina=2")
        self.assertNotContains(primera, "Anterior")
        self.assertContains(primera, reverse("core:auditoria_registro", args=[registros[-1].pk]))
        self.assertNotContains(primera, reverse("core:auditoria_registro", args=[registros[0].pk]))
        self.assertContains(segunda, "Registros 26 a 28 de 28")
        self.assertContains(segunda, "accion=modificacion&amp;pagina=1")
        self.assertNotContains(segunda, "Siguiente")
        self.assertContains(segunda, reverse("core:auditoria_registro", args=[registros[0].pk]))
        self.assertContains(lejana, "Página 2 de 2")

    def test_regla_2_una_sola_pagina_no_muestra_paginado(self):
        """AUD-CNS-REG regla 2: con una sola página no hay enlaces de página."""
        administrador = crear_administrador()
        anotar(administrador, Accion.BAJA, [administrador])
        self.entrar(administrador)

        respuesta = self.lista()

        self.assertNotContains(respuesta, "Siguiente")
        self.assertNotContains(respuesta, "Anterior")
        self.assertContains(respuesta, "Registros 1 a 1 de 1")

    # ---- Regla 4: no se modifica ni se borra ----

    def test_regla_4_ninguna_pantalla_ofrece_modificar_ni_borrar(self):
        """AUD-CNS-REG regla 4: ni la lista ni el detalle tienen formularios POST ni acciones de modificar o borrar; el
        sistema responde 405 a cualquier otro método (la pantalla solo lee)."""
        administrador = crear_administrador()
        registro = anotar(administrador, Accion.MODIFICACION, [administrador], detalle=DETALLE_CAMBIO)
        self.entrar(administrador)
        urls = (reverse("core:auditoria"), reverse("core:auditoria_registro", args=[registro.pk]))

        for url in urls:
            with self.subTest(url=url):
                contenido = self.principal(self.client.get(url))
                self.assertNotIn("<form class=\"pop-form\"", contenido)
                self.assertNotIn('method="post"', contenido.lower())
                for palabra in ("Borrar", "Eliminar", "Editar", "Modificar"):
                    self.assertNotIn(palabra, contenido)
                for metodo in (self.client.post, self.client.put, self.client.patch, self.client.delete):
                    self.assertEqual(metodo(url).status_code, 405)
        self.assertEqual(RegistroAuditoria.objects.count(), 1)

    # ---- Regla 5: sin contraseñas ni enlaces ----

    @override_settings(CORREO_CONFIGURADO=True)
    def test_regla_5_ninguna_contrasena_ni_enlace_aparece_en_las_pantallas(self):
        """AUD-CNS-REG regla 5 y SEG-14: después de restablecer el acceso con una contraseña temporal y con una
        invitación, ni la contraseña temporal, ni el enlace o el token de la invitación, ni el resumen de ninguna
        contraseña aparecen en la lista ni en el detalle de ningún registro."""
        gerente = crear_gerente()
        con_temporal = crear_capataz()
        con_invitacion = crear_cuenta(Vendedor, "vendedor@infoponia.com")
        temporal = servicios.restablecer_contrasena(gerente, con_temporal.pk).contrasena_temporal
        servicios.restablecer_contrasena(
            gerente, con_invitacion.pk, acceso=servicios.ACCESO_INVITACION, construir_url=construir_url
        )
        token = PATRON_INVITACION.search(mail.outbox[0].body).group(2)
        secretos = [temporal, token, "/invitacion/", Usuario.objects.get(pk=con_temporal.pk).password]
        self.entrar(gerente)

        paginas = [self.lista()] + [
            self.client.get(reverse("core:auditoria_registro", args=[registro.pk]))
            for registro in RegistroAuditoria.objects.all()
        ]

        self.assertEqual(len(paginas), 3)
        for respuesta in paginas:
            for secreto in secretos:
                self.assertNotContains(respuesta, secreto)

    # ---- Regla 6 y postcondición a: solo lectura ----

    def test_regla_6_ver_la_lista_y_el_detalle_solo_lee_y_no_audita(self):
        """AUD-CNS-REG regla 6, SEG-14 y postcondición a: abrir la lista (con filtros) y el detalle no escribe en la
        base (solo SELECT, como en la 08) y no agrega registros de auditoría."""
        gerente = crear_gerente()
        capataz = crear_capataz()
        registro = anotar(gerente, Accion.MODIFICACION, [capataz], detalle=DETALLE_CAMBIO)
        self.entrar(gerente)
        self.lista()  # la primera vuelta abre la sesión de prueba: lo que se mide es la consulta

        with CaptureQueriesContext(connection) as consultas:
            self.assertEqual(self.lista(accion="modificacion", cuenta=capataz.pk).status_code, 200)
            self.assertEqual(self.client.get(reverse("core:auditoria_registro", args=[registro.pk])).status_code, 200)

        escrituras = [
            consulta["sql"]
            for consulta in consultas.captured_queries
            if not consulta["sql"].lstrip().upper().startswith("SELECT")
        ]
        self.assertEqual(escrituras, [])
        self.assertEqual(RegistroAuditoria.objects.count(), 1)

    # ---- Regla 7: desde la ficha de una cuenta ----

    def test_regla_7_la_ficha_ofrece_ver_auditoria_con_la_cuenta_ya_filtrada(self):
        """AUD-CNS-REG regla 7: desde la ficha de una cuenta (USR-CNS-USR), «Ver auditoría» abre la lista con el filtro
        de esa cuenta ya aplicado (actuó o fue afectada), para el Gerente y para el Administrador; la lista muestra
        la etiqueta del filtro con «Quitar filtro» y deja afuera lo de las otras cuentas."""
        administrador = crear_administrador()
        gerente = crear_gerente()
        capataz = crear_capataz()
        vendedor = crear_cuenta(Vendedor, "vendedor@infoponia.com", nombre="Vera", apellido="Díaz")
        hizo = anotar(capataz, Accion.CAMBIO_CONTRASENA, [capataz])
        recibio = anotar(gerente, Accion.MODIFICACION, [capataz])
        ajeno = anotar(gerente, Accion.BAJA, [vendedor])
        enlace = f'href="{reverse("core:auditoria")}?cuenta='

        for actor, cuenta in ((gerente, capataz), (administrador, gerente)):
            self.entrar(actor)
            ficha = self.client.get(reverse("core:usuario", args=[cuenta.pk]))
            with self.subTest(actor=actor.email):
                self.assertContains(ficha, f"{enlace}{cuenta.pk}")
                self.assertContains(ficha, "Ver auditoría")

        self.entrar(gerente)
        respuesta = self.client.get(f"{reverse('core:auditoria')}?cuenta={capataz.pk}")
        self.assertContains(respuesta, reverse("core:auditoria_registro", args=[hizo.pk]))
        self.assertContains(respuesta, reverse("core:auditoria_registro", args=[recibio.pk]))
        self.assertNotContains(respuesta, reverse("core:auditoria_registro", args=[ajeno.pk]))
        self.assertContains(respuesta, "(actuó o fue afectada)")
        self.assertContains(respuesta, "Quitar filtro")
        self.assertContains(respuesta, f'name="cuenta" value="{capataz.pk}"')

    def test_regla_7_quitar_filtro_vuelve_a_la_lista_sin_la_cuenta_y_con_el_resto(self):
        """AUD-CNS-REG regla 7: «Quitar filtro» saca el filtro de la cuenta y conserva los demás filtros; sin la cuenta
        la lista vuelve a mostrar todo lo del alcance."""
        administrador = crear_administrador()
        capataz = crear_capataz()
        anotar(administrador, Accion.BAJA, [capataz])
        self.entrar(administrador)

        respuesta = self.lista(cuenta=capataz.pk, accion="baja")

        self.assertContains(respuesta, f'href="{reverse("core:auditoria")}?accion=baja"')

    def test_regla_7_el_detalle_vuelve_a_la_lista_con_los_mismos_filtros(self):
        """AUD-CNS-REG regla 3: abrir un registro desde una lista filtrada y paginada y volver deja la misma lista (con
        sus filtros y su página)."""
        administrador = crear_administrador()
        registro = anotar(administrador, Accion.BAJA, [administrador])
        self.entrar(administrador)

        lista = self.lista(accion="baja", pagina=1)
        self.assertContains(lista, f"{reverse('core:auditoria_registro', args=[registro.pk])}?accion=baja&amp;pagina=1")

        detalle = self.client.get(reverse("core:auditoria_registro", args=[registro.pk]), {"accion": "baja", "pagina": 1})
        self.assertContains(detalle, f'href="{reverse("core:auditoria")}?accion=baja&amp;pagina=1"')
