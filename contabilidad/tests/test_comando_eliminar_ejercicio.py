# Pruebas del comando de uso único `eliminar_ejercicio_sin_apertura` (tarea CON-05, paso 6; decisión «Puesta en marcha contable», punto 4): borra el ejercicio que creó la puesta en marcha
# automática en producción (sin asientos). Sin opciones solo simula; con `--confirmar` bloquea, verifica con los datos bloqueados, audita `baja_ejercicio_contable` (actor `None`: InfoPonia,
# como dice la tarea) y borra, todo en una transacción. Solo la base de pruebas: nada contra Neon. Cada prueba arma sus propios datos.
import datetime
import io
from unittest import mock

from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from contabilidad.models import AsientoContable, EjercicioContable, MovimientoContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin, asiento_de_prueba, ejercicio
from core.models import RegistroAuditoria

Estado = EjercicioContable.Estado
Accion = RegistroAuditoria.Accion
INICIO = datetime.date(2026, 11, 26)
MOTIVO = "puesta en marcha automática reemplazada por CON-INI-EJE"


class FalloDePrueba(Exception):
    """Fallo forzado para probar «todo en una transacción»."""


def correr(*argumentos):
    """Corre el comando y devuelve lo que imprimió."""
    salida = io.StringIO()
    call_command("eliminar_ejercicio_sin_apertura", *argumentos, stdout=salida)
    return salida.getvalue()


def bajas():
    return RegistroAuditoria.objects.filter(accion=Accion.BAJA_EJERCICIO_CONTABLE)


class EliminarEjercicioSinAperturaTests(PlanDeCuentasMixin, TestCase):
    """El caso de producción: un solo ejercicio abierto, sin asientos y con el número 0."""

    def setUp(self):
        self.ej = ejercicio(Estado.ABIERTO, INICIO)

    def assert_sigue_todo(self, cantidad=1):
        self.assertEqual(EjercicioContable.objects.count(), cantidad)
        self.assertFalse(bajas().exists())

    # --- Simulación por defecto -------------------------------------------------------------------------------------------------------------------------

    def test_sin_confirmar_no_borra_nada_ni_audita_y_dice_que_borraria(self):
        """Sin opciones no escribe nada: muestra qué ejercicio borraría (con su rango) y cómo confirmar."""
        salida = correr()

        self.assert_sigue_todo()
        self.assertIn("26/11/2026", salida)
        self.assertIn("--confirmar", salida)
        self.assertIn("borraría", salida)

    def test_sin_confirmar_dice_por_que_no_puede_si_no_se_cumple_y_no_falla(self):
        """La simulación también informa el motivo cuando no se podría borrar (sin lanzar error ni borrar): acá, con un asiento."""
        asiento_de_prueba(self.ej, INICIO)

        salida = correr()

        self.assertEqual(EjercicioContable.objects.count(), 1)
        self.assertIn("no se puede", salida.lower())
        self.assertIn("asiento", salida)

    def test_sin_ningun_ejercicio_la_simulacion_lo_dice(self):
        """Sin ejercicios no hay nada que borrar: la simulación lo dice y no falla."""
        self.ej.delete()

        self.assertIn("ningún ejercicio", correr().lower())

    # --- Con --confirmar ----------------------------------------------------------------------------------------------------------------------------------

    def test_con_confirmar_borra_el_ejercicio_e_imprime_el_texto_de_la_tarea(self):
        """Con `--confirmar` borra el ejercicio y dice que la contabilidad queda sin iniciar y que se use «Iniciar ejercicio»."""
        pk = self.ej.pk

        salida = correr("--confirmar")

        self.assertFalse(EjercicioContable.objects.exists())
        self.assertIn("eliminado", salida)
        self.assertIn("La contabilidad queda sin iniciar", salida)
        self.assertIn("Iniciar ejercicio", salida)
        self.assertIn(str(pk), "".join(str(a["id"]) for a in bajas().get().afectados))

    def test_con_confirmar_audita_baja_ejercicio_contable_con_actor_none_y_los_tres_campos_a_none(self):
        """Auditoría: `baja_ejercicio_contable`, actor `None` (InfoPonia), el ejercicio en `afectados`, los tres campos de `cambios` a `None` y el motivo en `datos`."""
        antes = {
            "fecha_inicio_ejercicio": INICIO.isoformat(),
            "fecha_cierre_ejercicio": self.ej.fecha_cierre_ejercicio.isoformat(),
            "estado_ejercicio": "abierto",
        }

        correr("--confirmar")

        registro = bajas().get()
        self.assertIsNone(registro.usuario)
        self.assertEqual(registro.rol, "infoponia")
        self.assertEqual([a["id"] for a in registro.afectados], [self.ej.pk])
        self.assertEqual(registro.detalle["cambios"], {campo: {"antes": valor, "despues": None} for campo, valor in antes.items()})
        self.assertEqual(registro.detalle["datos"], {"motivo": MOTIVO})

    def test_la_accion_baja_ejercicio_contable_esta_clasificada_como_de_negocio(self):
        """Patrón de auditoría: la acción nueva está en `ACCIONES_DE_NEGOCIO` (el Gerente la ve en «Auditoría») y tiene etiqueta."""
        from core.models import ACCIONES_DE_NEGOCIO

        self.assertEqual(Accion.BAJA_EJERCICIO_CONTABLE, "baja_ejercicio_contable")
        self.assertIn(Accion.BAJA_EJERCICIO_CONTABLE, ACCIONES_DE_NEGOCIO)
        self.assertTrue(Accion.BAJA_EJERCICIO_CONTABLE.label)

    def test_dos_corridas_la_segunda_no_encuentra_nada(self):
        """Uso único: después de borrar, `--confirmar` otra vez se niega (no hay ejercicio) y no audita una segunda baja."""
        correr("--confirmar")

        with self.assertRaises(CommandError):
            correr("--confirmar")
        self.assertEqual(bajas().count(), 1)

    # --- Negativas: cada una sin borrar nada y con CommandError ------------------------------------------------------------------------------------------

    def test_se_niega_si_no_hay_ningun_ejercicio(self):
        """Ninguno: `CommandError` con el motivo."""
        self.ej.delete()

        with self.assertRaises(CommandError) as contexto:
            correr("--confirmar")
        self.assertIn("ningún ejercicio", str(contexto.exception).lower())
        self.assertFalse(bajas().exists())

    def test_se_niega_si_hay_mas_de_un_ejercicio(self):
        """Dos o más (aunque el otro sea cerrado): se niega, no borra ninguno y no audita."""
        ejercicio(Estado.CERRADO, datetime.date(2025, 1, 1))

        with self.assertRaises(CommandError) as contexto:
            correr("--confirmar")
        self.assertIn("más de un ejercicio", str(contexto.exception).lower())
        self.assert_sigue_todo(2)

    def test_se_niega_si_el_unico_ejercicio_esta_en_cierre_o_cerrado(self):
        """Solo un ejercicio «abierto»: uno en cierre o cerrado se niega."""
        for estado in (Estado.EN_CIERRE, Estado.CERRADO):
            with self.subTest(estado=estado):
                EjercicioContable.objects.all().delete()
                ejercicio(estado, datetime.date(2025, 1, 1))
                with self.assertRaises(CommandError) as contexto:
                    correr("--confirmar")
                self.assertIn("abierto", str(contexto.exception).lower())
                self.assert_sigue_todo()

    def test_se_niega_si_el_numero_de_asiento_esta_tomado(self):
        """`ultimo_numero_asiento != 0`: el número ya se usó (aunque el asiento no exista), se niega."""
        EjercicioContable.objects.filter(pk=self.ej.pk).update(ultimo_numero_asiento=1)

        with self.assertRaises(CommandError) as contexto:
            correr("--confirmar")
        self.assertIn("número", str(contexto.exception).lower())
        self.assert_sigue_todo()

    def test_se_niega_si_el_ejercicio_tiene_un_asiento_aunque_el_numero_este_en_cero(self):
        """Asientos: aunque `ultimo_numero_asiento` esté en 0 (dato inconsistente), si el ejercicio tiene un asiento el comando se niega con su propio `CommandError`, **antes** de intentar borrar:
        no depende del `PROTECT` de la base. No borra ni audita nada."""
        asiento = asiento_de_prueba(self.ej, INICIO)
        EjercicioContable.objects.filter(pk=self.ej.pk).update(ultimo_numero_asiento=0)

        with self.assertRaises(CommandError) as contexto:
            correr("--confirmar")

        self.assertIn("asiento", str(contexto.exception).lower())
        self.assert_sigue_todo()
        self.assertTrue(AsientoContable.objects.filter(pk=asiento.pk).exists())

    def test_se_niega_si_el_ejercicio_tiene_asientos_con_movimientos(self):
        """Asientos y movimientos: con asientos (y por lo tanto movimientos) el comando se niega y no queda ningún cambio."""
        asiento_de_prueba(self.ej, INICIO)
        self.assertTrue(MovimientoContable.objects.exists())

        with self.assertRaises(CommandError):
            correr("--confirmar")

        self.assert_sigue_todo()
        self.assertEqual(AsientoContable.objects.count(), 1)
        self.assertEqual(MovimientoContable.objects.count(), 2)

    def test_la_base_tambien_protege_el_ejercicio_con_asientos_aunque_el_comando_no_lo_verificara(self):
        """Defensa en profundidad: `AsientoContable.ejercicio` es `PROTECT`: borrar a la fuerza un ejercicio con asientos lo rechaza la base (`ProtectedError`), el asiento y sus movimientos
        siguen. Es lo que respalda al comando; el comando se niega antes (prueba de arriba)."""
        from django.db.models import ProtectedError

        asiento_de_prueba(self.ej, INICIO)

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.ej.delete()

        self.assertEqual((EjercicioContable.objects.count(), AsientoContable.objects.count(), MovimientoContable.objects.count()), (1, 1, 2))

    def test_no_se_confirma_con_una_opcion_desconocida(self):
        """Solo existe `--confirmar`: cualquier otra opción es un error de uso y no borra nada."""
        with self.assertRaises(CommandError):
            correr("--si")
        self.assert_sigue_todo()

    # --- Todo en una transacción y bloqueo --------------------------------------------------------------------------------------------------------------

    def test_si_falla_el_borrado_no_queda_la_auditoria(self):
        """Una transacción: si falla el borrado, también se deshace la auditoría de la baja (no queda un registro de algo que no pasó)."""
        with mock.patch.object(EjercicioContable, "delete", side_effect=FalloDePrueba):
            with self.assertRaises(FalloDePrueba):
                correr("--confirmar")

        self.assert_sigue_todo()

    def test_si_falla_la_auditoria_no_se_borra_el_ejercicio(self):
        """Una transacción: si falla la auditoría (que va antes del borrado), el ejercicio sigue."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=FalloDePrueba):
            with self.assertRaises(FalloDePrueba):
                correr("--confirmar")

        self.assert_sigue_todo()

    def test_la_auditoria_se_escribe_antes_de_borrar(self):
        """Orden de la tarea: audita y después borra (así la baja nombra un ejercicio que todavía existe cuando se registra)."""
        orden = []
        real_registrar = RegistroAuditoria.objects.registrar
        real_borrar = EjercicioContable.delete

        def registrar(*a, **k):
            orden.append(("auditar", EjercicioContable.objects.filter(pk=self.ej.pk).exists()))
            return real_registrar(*a, **k)

        def borrar(instancia, *a, **k):
            orden.append(("borrar", True))
            return real_borrar(instancia, *a, **k)

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=registrar), mock.patch.object(EjercicioContable, "delete", borrar):
            correr("--confirmar")

        self.assertEqual(orden, [("auditar", True), ("borrar", True)])

    def test_bloquea_los_ejercicios_dentro_de_la_transaccion(self):
        """Bloqueo: la verificación se hace con los ejercicios bloqueados (`select_for_update`), dentro de `atomic()`: la consulta de bloqueo corre en una transacción abierta."""
        from django.db import connection

        consultas = []

        def espiar(execute, sql, params, many, context):
            if "FOR NO KEY UPDATE" in sql and "contabilidad_ejerciciocontable" in sql:
                consultas.append(connection.in_atomic_block)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(espiar):
            correr("--confirmar")

        self.assertTrue(consultas, "no se bloquearon los ejercicios con FOR NO KEY UPDATE")
        self.assertTrue(all(consultas))

    def test_la_simulacion_no_bloquea_ni_escribe(self):
        """Sin `--confirmar` no hay `FOR NO KEY UPDATE` ni escrituras en el ejercicio."""
        from django.db import connection

        sentencias = []

        def espiar(execute, sql, params, many, context):
            sentencias.append(sql)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(espiar):
            correr()

        self.assertFalse([s for s in sentencias if "FOR NO KEY UPDATE" in s or s.lstrip().upper().startswith(("DELETE", "INSERT", "UPDATE"))])


class EliminarEjercicioSinAperturaMigracionTests(TestCase):
    """La migración `core/0054` solo cambia los `choices` de la acción: no toca datos."""

    def test_la_accion_nueva_es_un_choice_valido_del_campo(self):
        """`RegistroAuditoria.accion` acepta `baja_ejercicio_contable` (la prueba de que `choices` y la migración coinciden la hace `makemigrations --check`)."""
        valores = [valor for valor, _ in RegistroAuditoria._meta.get_field("accion").choices]
        self.assertIn("baja_ejercicio_contable", valores)
