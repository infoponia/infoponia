# Pruebas de la migración de datos 0008 (D-36): convierte los registros de auditoría que ya existen al formato
# obligatorio del detalle («cambios» con antes y después, «datos» de contexto, referencias {id, texto}) y agrega
# el texto y el rol a cada cuenta afectada. Es la única excepción deliberada a D-22 (solo agregar).
#
# Las funciones de conversión viven dentro del archivo de la migración (no importa código de la app, para que un
# cambio futuro de la app no la rompa); acá se cargan con importlib, porque el nombre del módulo empieza con un
# dígito. Se toman dentro de cada prueba para que, mientras la migración no exista, falle cada prueba por separado.
# Firma que se prueba:
# - a_formato_nuevo(accion, detalle, afectados, cuentas) -> (detalle, afectados); ``cuentas`` es
#   {id: {"texto": ..., "rol": ...}} con las cuentas actuales. Un registro ya convertido vuelve igual.
# - a_formato_viejo(accion, detalle, afectados) -> (detalle, afectados): la vuelta. Un registro viejo vuelve igual.

import importlib

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase, tag

ANTERIOR = ("core", "0007_invitacion_por_correo")
NOMBRE = "0008_formato_detalle_auditoria"
ESTA = ("core", NOMBRE)

# Cuentas actuales con las que la migración completa el texto y el rol de los afectados.
CUENTAS = {
    7: {"texto": "Laura Benítez (laura@infoponia.com)", "rol": "capataz"},
    8: {"texto": "Adrián Mena (admin@infoponia.com)", "rol": "administrador"},
    9: {"texto": "Pablo Ríos (pablo@infoponia.com)", "rol": "vendedor"},
}
AFECTADO_VIEJO = [{"modelo": "core.usuario", "id": 7}]
AFECTADO_NUEVO = [{"modelo": "core.usuario", "id": 7, "texto": "Laura Benítez (laura@infoponia.com)", "rol": "capataz"}]


def migracion():
    """El módulo de la migración 0008."""
    return importlib.import_module(f"core.migrations.{NOMBRE}")


def grupo(numero):
    """Referencia a un grupo en el formato nuevo."""
    return {"id": numero, "texto": f"Grupo {numero}"}


# Cada formato viejo con su conversión (D-36, mapeo aprobado en el plan de la tarea). Los nombres de acción son los
# valores de ``RegistroAuditoria.Accion``.
CASOS = [
    (
        "alta con la forma de acceso (tarea 08b)",
        "alta",
        {"rol": "capataz", "email": "laura@infoponia.com", "nombre": "Laura", "apellido": "Benítez", "acceso": "temporal"},
        {
            "cambios": {
                "rol": {"antes": None, "despues": "capataz"},
                "email": {"antes": None, "despues": "laura@infoponia.com"},
                "nombre": {"antes": None, "despues": "Laura"},
                "apellido": {"antes": None, "despues": "Benítez"},
            },
            "datos": {"acceso": "temporal"},
        },
    ),
    (
        "alta anterior a la forma de acceso",
        "alta",
        {"rol": "capataz", "email": "laura@infoponia.com", "nombre": "Laura", "apellido": "Benítez"},
        {
            "cambios": {
                "rol": {"antes": None, "despues": "capataz"},
                "email": {"antes": None, "despues": "laura@infoponia.com"},
                "nombre": {"antes": None, "despues": "Laura"},
                "apellido": {"antes": None, "despues": "Benítez"},
            },
        },
    ),
    (
        "modificación",
        "modificacion",
        {"apellido": ["Benítez", "Gómez"], "telefono": ["", "+54 376 400-1001"]},
        {
            "cambios": {
                "apellido": {"antes": "Benítez", "despues": "Gómez"},
                "telefono": {"antes": "", "despues": "+54 376 400-1001"},
            }
        },
    ),
    (
        "baja",
        "baja",
        {"estado": ["activo", "inactivo"]},
        {"cambios": {"estado": {"antes": "activo", "despues": "inactivo"}}},
    ),
    (
        "reactivación con salida del grupo",
        "reactivacion",
        {"estado": ["inactivo", "activo"], "acceso": "invitacion", "sale_del_grupo": 3},
        {
            "cambios": {
                "estado": {"antes": "inactivo", "despues": "activo"},
                "grupo": {"antes": grupo(3), "despues": None},
            },
            "datos": {"acceso": "invitacion"},
        },
    ),
    (
        "reactivación anterior a la forma de acceso",
        "reactivacion",
        {"estado": ["inactivo", "activo"]},
        {"cambios": {"estado": {"antes": "inactivo", "despues": "activo"}}},
    ),
    (
        "restablecimiento sin grupo",
        "restablecimiento",
        {"acceso": "temporal"},
        {"datos": {"acceso": "temporal"}},
    ),
    (
        "restablecimiento con salida del grupo",
        "restablecimiento",
        {"acceso": "temporal", "sale_del_grupo": 5},
        {"cambios": {"grupo": {"antes": grupo(5), "despues": None}}, "datos": {"acceso": "temporal"}},
    ),
    ("restablecimiento anterior a la forma de acceso", "restablecimiento", {}, {}),
    ("cambio de contraseña", "cambio_contrasena", {"era_temporal": True}, {"datos": {"era_temporal": True}}),
    (
        "recuperación",
        "recuperacion_contrasena",
        {"era_temporal": False, "invitacion_pendiente": True},
        {"datos": {"era_temporal": False, "invitacion_pendiente": True}},
    ),
    (
        "recuperación anterior a la invitación",
        "recuperacion_contrasena",
        {"era_temporal": False},
        {"datos": {"era_temporal": False}},
    ),
    (
        "aceptación de invitación",
        "aceptacion_invitacion",
        {"era_temporal": False, "invitacion_pendiente": True},
        {"datos": {"era_temporal": False, "invitacion_pendiente": True}},
    ),
    (
        "vinculación sin unir grupos",
        "vinculacion",
        {"grupo": 4, "grupo_unido": None},
        {"datos": {"grupo": grupo(4), "grupo_unido": None}},
    ),
    (
        "vinculación que une dos grupos",
        "vinculacion",
        {"grupo": 4, "grupo_unido": 6},
        {"datos": {"grupo": grupo(4), "grupo_unido": grupo(6)}},
    ),
    (
        "desvinculación",
        "desvinculacion",
        {"grupo": 4, "disuelto": True},
        {"datos": {"grupo": grupo(4), "disuelto": True}},
    ),
]


class ConversionTests(SimpleTestCase):
    """Funciones de conversión de la migración 0008 (D-36), sin base de datos."""

    def test_d36_convierte_cada_formato_viejo(self):
        """D-36: cada formato viejo del detalle pasa al nuevo según el mapeo aprobado, y la cuenta afectada suma su
        texto y su rol actuales."""
        for nombre, accion, viejo, nuevo in CASOS:
            with self.subTest(nombre):
                detalle, afectados = migracion().a_formato_nuevo(accion, viejo, AFECTADO_VIEJO, CUENTAS)
                self.assertEqual(detalle, nuevo)
                self.assertEqual(afectados, AFECTADO_NUEVO)

    def test_d36_convierte_todos_los_afectados(self):
        """D-36: todos los afectados suman su texto y su rol, también el de un Administrador; una cuenta que ya no
        estuviera (no debería pasar: las cuentas no se borran) queda con el texto «Cuenta <id>» y sin rol."""
        afectados = [
            {"modelo": "core.usuario", "id": 8},
            {"modelo": "core.usuario", "id": 9},
            {"modelo": "core.usuario", "id": 99},
        ]

        _, convertidos = migracion().a_formato_nuevo("vinculacion", {"grupo": 1, "grupo_unido": None}, afectados, CUENTAS)

        self.assertEqual(
            convertidos,
            [
                {"modelo": "core.usuario", "id": 8, "texto": "Adrián Mena (admin@infoponia.com)", "rol": "administrador"},
                {"modelo": "core.usuario", "id": 9, "texto": "Pablo Ríos (pablo@infoponia.com)", "rol": "vendedor"},
                {"modelo": "core.usuario", "id": 99, "texto": "Cuenta 99"},
            ],
        )

    def test_d36_la_conversion_es_idempotente(self):
        """D-36: un registro que ya está en el formato nuevo no cambia si se lo vuelve a convertir (correr la
        migración dos veces, o sobre registros escritos con el código nuevo, no los rompe)."""
        for nombre, accion, viejo, nuevo in CASOS:
            with self.subTest(nombre):
                detalle, afectados = migracion().a_formato_nuevo(accion, nuevo, AFECTADO_NUEVO, CUENTAS)
                self.assertEqual(detalle, nuevo)
                self.assertEqual(afectados, AFECTADO_NUEVO)

    def test_d36_la_vuelta_restaura_el_formato_viejo(self):
        """D-36: la función de vuelta de la migración devuelve cada registro a su formato viejo, y los afectados a
        ``{"modelo", "id"}``; un registro viejo no cambia si se lo vuelve a revertir."""
        for nombre, accion, viejo, nuevo in CASOS:
            with self.subTest(nombre):
                detalle, afectados = migracion().a_formato_viejo(accion, nuevo, AFECTADO_NUEVO)
                self.assertEqual(detalle, viejo)
                self.assertEqual(afectados, AFECTADO_VIEJO)
                detalle, afectados = migracion().a_formato_viejo(accion, viejo, AFECTADO_VIEJO)
                self.assertEqual(detalle, viejo)
                self.assertEqual(afectados, AFECTADO_VIEJO)

    def test_d36_el_resultado_cumple_el_formato_obligatorio(self):
        """D-36: lo que deja la migración cumple el formato que exige ``registrar``: solo «cambios» y «datos», y
        cada cambio con exactamente «antes» y «despues»."""
        for nombre, accion, viejo, _ in CASOS:
            with self.subTest(nombre):
                detalle, _ = migracion().a_formato_nuevo(accion, viejo, AFECTADO_VIEJO, CUENTAS)
                self.assertLessEqual(set(detalle), {"cambios", "datos"})
                for cambio in detalle.get("cambios", {}).values():
                    self.assertEqual(set(cambio), {"antes", "despues"})


@tag("migracion")
class MigracionDePuntaAPuntaTests(TransactionTestCase):
    """La migración 0008 corrida contra la base (D-36): se vuelve a la 0007, se crean registros en los formatos
    viejos con el modelo histórico, se migra hacia adelante y hacia atrás. Al terminar, la base vuelve a la última
    migración. Lleva la etiqueta «migracion»: en local se excluye junto con «concurrencia» (CLAUDE.md), porque
    desarma y vuelve a armar el esquema de la base de pruebas; el CI la corre."""

    def tearDown(self):
        """Deja la base en la última migración de cada app, como la encontró."""
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrar(self, destino):
        """Migra la base a ``destino`` y devuelve las apps del estado histórico de ese punto."""
        executor = MigrationExecutor(connection)
        executor.migrate([destino])
        executor.loader.build_graph()
        return executor.loader.project_state([destino]).apps

    def test_d36_migra_los_registros_viejos_y_vuelve(self):
        """D-36: con la base en la 0007, los registros viejos (una modificación y una vinculación) pasan al formato
        nuevo con la 0008, con el texto y el rol de sus cuentas; volver a la 0007 los deja como estaban."""
        apps = self.migrar(ANTERIOR)
        Usuario = apps.get_model("core", "Usuario")
        Registro = apps.get_model("core", "RegistroAuditoria")
        gerente = Usuario.objects.create(
            email="gerente@infoponia.com", first_name="Gabriela", last_name="Sosa", rol="gerente", password="!"
        )
        capataz = Usuario.objects.create(
            email="laura@infoponia.com", first_name="Laura", last_name="Gómez", rol="capataz", password="!"
        )
        modificacion = Registro.objects.create(
            usuario=gerente,
            rol="gerente",
            accion="modificacion",
            afectados=[{"modelo": "core.usuario", "id": capataz.pk}],
            detalle={"apellido": ["Benítez", "Gómez"]},
        )
        vinculacion = Registro.objects.create(
            usuario=capataz,
            rol="capataz",
            accion="vinculacion",
            afectados=[{"modelo": "core.usuario", "id": capataz.pk}, {"modelo": "core.usuario", "id": gerente.pk}],
            detalle={"grupo": 2, "grupo_unido": None},
        )
        migracion()  # falla acá, con un error claro, si la migración no existe

        apps = self.migrar(ESTA)
        Registro = apps.get_model("core", "RegistroAuditoria")
        laura = {"modelo": "core.usuario", "id": capataz.pk, "texto": "Laura Gómez (laura@infoponia.com)", "rol": "capataz"}
        gabriela = {
            "modelo": "core.usuario",
            "id": gerente.pk,
            "texto": "Gabriela Sosa (gerente@infoponia.com)",
            "rol": "gerente",
        }
        modificada = Registro.objects.get(pk=modificacion.pk)
        self.assertEqual(modificada.detalle, {"cambios": {"apellido": {"antes": "Benítez", "despues": "Gómez"}}})
        self.assertEqual(modificada.afectados, [laura])
        vinculada = Registro.objects.get(pk=vinculacion.pk)
        self.assertEqual(vinculada.detalle, {"datos": {"grupo": grupo(2), "grupo_unido": None}})
        self.assertEqual(vinculada.afectados, [laura, gabriela])

        apps = self.migrar(ANTERIOR)
        Registro = apps.get_model("core", "RegistroAuditoria")
        self.assertEqual(Registro.objects.get(pk=modificacion.pk).detalle, {"apellido": ["Benítez", "Gómez"]})
        self.assertEqual(
            Registro.objects.get(pk=modificacion.pk).afectados, [{"modelo": "core.usuario", "id": capataz.pk}]
        )
        self.assertEqual(Registro.objects.get(pk=vinculacion.pk).detalle, {"grupo": 2, "grupo_unido": None})
