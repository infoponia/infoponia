# Pruebas de los servicios de cuentas con el rol Contador (USR-11, D-85): alta (USR-ALT-USR), reactivación (USR-MOD-USR),
# baja (USR-BAJ-USR), consulta y alcance (USR-CNS-USR) y el invariante «un solo Contador activo» (SEG-15, D-85 punto 2),
# con sus pruebas de concurrencia. Fuente de las reglas: docs/casos_de_uso/usuarios_rol_contador.md y D-85.
# Todas llaman a los servicios a través del módulo (servicios.x). Cada prueba arma sus propios datos.

from types import SimpleNamespace
from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase, tag

from core import servicios
from core.models import Contador, RegistroAuditoria, Usuario
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import afectado, crear_administrador, crear_cuenta, crear_gerente


def datos_de_alta(**cambios):
    """Datos válidos para dar de alta un Contador; ``cambios`` pisa campos."""
    datos = {
        "rol": Usuario.Rol.CONTADOR,
        "nombre": "Carolina",
        "apellido": "Vega",
        "email": "carolina@infoponia.com",
        "telefono": "",
    }
    datos.update(cambios)
    return datos


def error_de_restriccion(nombre):
    """Un ``IntegrityError`` como el que arma psycopg al violar la restricción ``nombre``."""
    error = IntegrityError("falla simulada")
    error.__cause__ = Exception("error del driver")
    error.__cause__.diag = SimpleNamespace(constraint_name=nombre)
    return error


class AltaDeContadorTests(TestCase):
    """USR-ALT-USR con el rol Contador (D-85 puntos 2 y 3; SEG-15)."""

    def test_regla_1_gerente_da_de_alta_un_contador(self):
        """USR-ALT-USR regla 1 (D-85 punto 3): el Gerente da de alta la cuenta; es un ``Contador`` con rol «contador»."""
        gerente = crear_gerente()

        cuenta, _ = servicios.alta_usuario(gerente, **datos_de_alta())

        self.assertIsInstance(cuenta, Contador)
        self.assertEqual(Usuario.objects.get(pk=cuenta.pk).rol, "contador")
        self.assertTrue(cuenta.is_active)

    def test_post_e_audita_el_alta_con_el_rol_contador(self):
        """USR-ALT-USR postcondición e (D-36): el registro lleva el rol nuevo en los cambios y en el afectado; el alta
        del Contador no necesita una acción nueva de auditoría."""
        gerente = crear_gerente()

        cuenta, _ = servicios.alta_usuario(gerente, **datos_de_alta())

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.ALTA)
        self.assertEqual(registro.afectados, [afectado(cuenta)])
        self.assertEqual(registro.afectados[0]["rol"], "contador")
        self.assertEqual(registro.detalle["cambios"]["rol"], {"antes": None, "despues": "contador"})

    def test_regla_2_rechaza_el_alta_con_un_contador_activo(self):
        """SEG-15 y D-85 punto 2: con un Contador activo no se da de alta otro; error general con código «contador_activo»
        que nombra al activo; no crea nada ni audita."""
        gerente = crear_gerente()
        crear_cuenta(Contador, email="activo@infoponia.com", nombre="Mario", apellido="Rey")

        with self.assertRaises(ValidationError) as contexto:
            servicios.alta_usuario(gerente, **datos_de_alta())

        errores = contexto.exception.error_dict[NON_FIELD_ERRORS]
        self.assertEqual([e.code for e in errores], ["contador_activo"])
        self.assertIn("Ya hay un Contador activo", errores[0].message)
        self.assertIn("Mario Rey", errores[0].message)
        self.assertFalse(Usuario.objects.filter(email="carolina@infoponia.com").exists())
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_2_deja_dar_de_alta_con_uno_inactivo(self):
        """SEG-15 y D-85 punto 4: la restricción solo cuenta los activos; con un Contador dado de baja, se da de alta otro."""
        gerente = crear_gerente()
        crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        cuenta, _ = servicios.alta_usuario(gerente, **datos_de_alta())

        self.assertEqual(Contador.objects.filter(is_active=True).get().pk, cuenta.pk)

    def test_regla_1_el_administrador_no_da_de_alta_un_contador(self):
        """USR-ALT-USR regla 1 y D-85 punto 3: el Administrador da de alta solo al Gerente; el Contador no."""
        administrador = crear_administrador()

        with self.assertRaises(ValidationError) as contexto:
            servicios.alta_usuario(administrador, **datos_de_alta())

        self.assertIn("rol", contexto.exception.message_dict)
        self.assertFalse(Contador.objects.exists())

    def test_regla_2_integrity_error_de_un_solo_contador_activo_da_contador_activo(self):
        """SEG-15: si la base rechaza el alta por ``un_solo_contador_activo`` (otra operación ganó de mano), se informa
        como «contador_activo» con ``raise ... from error``; nunca un 500."""
        gerente = crear_gerente()
        error = error_de_restriccion("un_solo_contador_activo")

        with mock.patch.object(Usuario, "save", side_effect=error):
            with self.assertRaises(ValidationError) as contexto:
                servicios.alta_usuario(gerente, **datos_de_alta())

        self.assertEqual([e.code for e in contexto.exception.error_dict[NON_FIELD_ERRORS]], ["contador_activo"])
        self.assertIs(contexto.exception.__cause__, error)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)


class ReactivacionDeContadorTests(TestCase):
    """USR-MOD-USR regla 5 extendida al Contador (reactivación; D-85 punto 2)."""

    def test_regla_5_rechaza_reactivar_con_otro_contador_activo(self):
        """Reactivar un Contador con otro activo se rechaza con «contador_activo»; la cuenta sigue inactiva y no se audita."""
        gerente = crear_gerente()
        crear_cuenta(Contador, email="activo@infoponia.com", nombre="Mario", apellido="Rey")
        inactivo = crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        with self.assertRaises(ValidationError) as contexto:
            servicios.reactivar_usuario(gerente, inactivo.pk)

        self.assertEqual(contexto.exception.code, "contador_activo")
        self.assertIn("reactivar", contexto.exception.messages[0])
        self.assertIn("Mario Rey", contexto.exception.messages[0])
        self.assertFalse(Usuario.objects.get(pk=inactivo.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_5_reactiva_un_contador_sin_otro_activo(self):
        """Sin otro Contador activo, el Gerente lo reactiva; se audita con el rol «contador» y el cambio de estado."""
        gerente = crear_gerente()
        inactivo = crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        servicios.reactivar_usuario(gerente, inactivo.pk)

        self.assertTrue(Usuario.objects.get(pk=inactivo.pk).is_active)
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.REACTIVACION)
        self.assertEqual(registro.afectados[0]["rol"], "contador")
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "inactivo", "despues": "activo"})

    def test_regla_5_integrity_error_de_un_solo_contador_activo_da_contador_activo(self):
        """SEG-15: la restricción de la base, al reactivar, se traduce a «contador_activo»; nunca un 500."""
        gerente = crear_gerente()
        inactivo = crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)
        error = error_de_restriccion("un_solo_contador_activo")

        with mock.patch.object(Usuario, "save", side_effect=error):
            with self.assertRaises(ValidationError) as contexto:
                servicios.reactivar_usuario(gerente, inactivo.pk)

        self.assertEqual(contexto.exception.code, "contador_activo")
        self.assertIs(contexto.exception.__cause__, error)
        self.assertFalse(Usuario.objects.get(pk=inactivo.pk).is_active)

    def test_regla_5_el_administrador_no_reactiva_a_un_contador(self):
        """D-85 punto 3: la cuenta del Contador está fuera del alcance del Administrador (403)."""
        administrador = crear_administrador()
        inactivo = crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        with self.assertRaises(PermissionDenied):
            servicios.reactivar_usuario(administrador, inactivo.pk)


class BajaDeContadorTests(TestCase):
    """USR-BAJ-USR con el rol Contador: la baja no se bloquea por nada (D-85 punto 4)."""

    def test_regla_4_la_baja_del_contador_no_tiene_impedimentos(self):
        """D-85 punto 4: ni siquiera el último Contador activo impide la baja; no hay impedimentos."""
        gerente = crear_gerente()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        self.assertEqual(servicios.impedimentos_de_baja(gerente, contador.pk), [])

    def test_post_a_y_d_da_de_baja_y_audita_con_el_rol_contador(self):
        """USR-BAJ-USR postcondiciones a y d: la cuenta queda inactiva y la baja se audita con el rol «contador»."""
        gerente = crear_gerente()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        servicios.baja_usuario(gerente, contador.pk)

        self.assertFalse(Usuario.objects.get(pk=contador.pk).is_active)
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.BAJA)
        self.assertEqual(registro.afectados[0]["rol"], "contador")
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "activo", "despues": "inactivo"})

    def test_d85_reemplazo_son_dos_operaciones_baja_y_alta(self):
        """D-85 punto 4: tras la baja se puede dar de alta a otro Contador; el reemplazo son dos operaciones."""
        gerente = crear_gerente()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        servicios.baja_usuario(gerente, contador.pk)
        nuevo, _ = servicios.alta_usuario(gerente, **datos_de_alta())

        self.assertEqual(Contador.objects.filter(is_active=True).get().pk, nuevo.pk)

    def test_regla_1_el_administrador_no_da_de_baja_a_un_contador(self):
        """D-85 punto 3: el Contador está fuera del alcance del Administrador (403) y sigue activo."""
        administrador = crear_administrador()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        with self.assertRaises(PermissionDenied):
            servicios.baja_usuario(administrador, contador.pk)

        self.assertTrue(Usuario.objects.get(pk=contador.pk).is_active)


class ConsultaDeContadorTests(TestCase):
    """USR-CNS-USR con el rol Contador: lista, filtro y alcance (D-85 punto 3)."""

    def test_regla_1_el_gerente_ve_al_contador_en_la_lista_y_en_el_filtro(self):
        """USR-CNS-USR reglas 1 y 2: el Gerente ve al Contador y lo filtra por rol; el filtro lo ofrece."""
        gerente = crear_gerente()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        crear_cuenta(Contador, email="otro@infoponia.com", activo=False)

        todos = servicios.consultar_usuarios(gerente)
        solo_contadores = servicios.consultar_usuarios(gerente, rol="contador", estado="activo")

        self.assertIn(contador.pk, [c.pk for c in todos])
        self.assertEqual([c.pk for c in solo_contadores], [contador.pk])
        self.assertIn(("contador", "Contador"), servicios.roles_que_gestiona(gerente))
        self.assertEqual(servicios.obtener_cuenta(gerente, contador.pk).pk, contador.pk)

    def test_regla_1_el_administrador_no_ve_ni_abre_al_contador(self):
        """USR-CNS-USR regla 1 y D-85 punto 3: el Administrador no lo ve en la lista ni en el filtro, y su ficha da 403."""
        administrador = crear_administrador()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        self.assertNotIn(contador.pk, [c.pk for c in servicios.consultar_usuarios(administrador)])
        self.assertNotIn("contador", [valor for valor, _ in servicios.roles_que_gestiona(administrador)])
        with self.assertRaises(PermissionDenied):
            servicios.obtener_cuenta(administrador, contador.pk)


@tag("concurrencia")
class ContadorUnicoConcurrenciaTests(TransactionTestCase):
    """SEG-15 y D-85 punto 2: dos operaciones simultáneas no pueden dejar dos Contadores activos. La segunda recibe un
    rechazo con mensaje («contador_activo»), no un error 500. Cada operación corre en su hilo (``core/tests/concurrencia.py``)."""

    def assertQuedaUnSoloContador(self, resultados):
        """Una operación sale bien, la otra se rechaza con «contador_activo» y queda un solo Contador activo."""
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], "ninguna operación puede terminar con un error sin traducir")
        self.assertEqual(len(exitos), 1)
        self.assertEqual(len(rechazos), 1)
        self.assertIn("contador_activo", codigos(rechazos[0]))
        self.assertEqual(Contador.objects.filter(is_active=True).count(), 1)
        return rechazos[0]

    def altas_simultaneas(self):
        """Dos altas de Contador a la vez, con emails distintos; la primera se detiene al registrar la auditoría."""
        gerente = crear_gerente()
        return correr_a_la_vez(
            lambda: servicios.alta_usuario(gerente, **datos_de_alta(email="c1@infoponia.com")),
            lambda: servicios.alta_usuario(gerente, **datos_de_alta(email="c2@infoponia.com")),
            primera="a",
        )

    def test_seg15_altas_simultaneas_dejan_un_solo_contador_activo(self):
        """Camino del bloqueo: con un Contador anterior dado de baja hay filas que bloquear; la segunda alta espera,
        ve al nuevo y se rechaza desde la verificación (sin ``__cause__``). Sin ``_bloquear_contadores`` esta falla."""
        crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        rechazo = self.assertQuedaUnSoloContador(self.altas_simultaneas())

        self.assertIsNone(rechazo.__cause__)

    def test_seg15_altas_simultaneas_sin_contadores_previos_informan_contador_activo(self):
        """Camino de la restricción: sin ningún Contador previo no hay nada que bloquear; ``un_solo_contador_activo``
        rechaza la segunda alta y el servicio la traduce (``__cause__`` es el ``IntegrityError``)."""
        rechazo = self.assertQuedaUnSoloContador(self.altas_simultaneas())

        self.assertIsInstance(rechazo.__cause__, IntegrityError)

    def test_seg15_alta_y_reactivacion_simultaneas_dejan_un_solo_contador_activo(self):
        """Un alta y una reactivación de Contador a la vez toman el mismo bloqueo: una gana y la otra se rechaza."""
        gerente = crear_gerente()
        anterior = crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        resultados = correr_a_la_vez(
            lambda: servicios.alta_usuario(gerente, **datos_de_alta()),
            lambda: servicios.reactivar_usuario(gerente, anterior.pk),
            primera="a",
        )

        self.assertQuedaUnSoloContador(resultados)
