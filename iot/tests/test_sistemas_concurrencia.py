# Pruebas de concurrencia de IOT-REG-SIS e IOT-MOD-SIS (docs/casos_de_uso/iot/sistema_iot.md, «Garantías mínimas»: «Un invernadero nunca
# queda con dos sistemas IoT que no estén dados de baja, aun cuando dos actores lo registren al mismo tiempo»; docs/patrones/bloqueos.md).
# Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). ``TransactionTestCase``: su ``flush`` vacía todas
# las tablas al terminar, así que cada prueba vuelve a asegurar los datos en ``setUp`` (docs/patrones/datos_de_migracion.md).

from django.db import transaction
from django.test import TransactionTestCase, tag

from core.enlaces import resumen_de
from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import NodoCentral, SistemaIoT
from iot.tests import fabricas
from iot.tests.fabricas import datos_de_sistema
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_invernadero_con_geografia_propia

sistemas = perezoso("iot.servicios.sistemas")


@tag("concurrencia")
class SistemasConcurrenciaTests(fabricas.ConCatalogoIot, TransactionTestCase):
    """Dos registros y dos regeneraciones a la vez."""

    def setUp(self):
        fabricas.asegurar_datos_de_iot()
        from maestros.tests.fabricas import asegurar_datos_de_maestros

        asegurar_datos_de_maestros()
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero_con_geografia_propia("Norte", agronomo=self.laura)

    def test_garantia_dos_registros_a_la_vez_en_el_mismo_invernadero_crean_un_solo_sistema(self):
        """IOT-REG-SIS garantía mínima y extensión 8a: uno lo logra y el otro recibe ``sistema_existente`` (nunca un 500, nunca dos sistemas)."""
        resultados = correr_a_la_vez(
            lambda: sistemas.registrar_sistema_iot(self.laura, datos_de_sistema(self.norte, nombre="Uno")),
            lambda: sistemas.registrar_sistema_iot(self.laura, datos_de_sistema(self.norte, nombre="Dos")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["sistema_existente"])
        self.assertEqual(SistemaIoT.objects.filter(invernadero=self.norte).count(), 1)
        self.assertEqual(NodoCentral.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_sistema_iot").count(), 1)

    def test_garantia_dos_registros_en_invernaderos_distintos_se_crean_los_dos(self):
        """El registro solo serializa por invernadero: dos invernaderos distintos conviven."""
        sur = crear_invernadero_con_geografia_propia("Sur", agronomo=self.laura)
        resultados = correr_a_la_vez(
            lambda: sistemas.registrar_sistema_iot(self.laura, datos_de_sistema(self.norte)),
            lambda: sistemas.registrar_sistema_iot(self.laura, datos_de_sistema(sur)),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))

    def test_ext_8b_el_registro_espera_a_la_reasignacion_y_se_rechaza(self):
        """IOT-REG-SIS extensión 8b: el alcance se verifica DESPUÉS de bloquear. Si a un invernadero sin Agrónomo se le asigna uno mientras el
        Gerente lo registra, y la asignación confirma primero, el registro se rechaza con ``fuera_de_alcance`` (nunca un 500)."""
        libre = crear_invernadero_con_geografia_propia("Libre")

        def asignar_agronomo():
            with transaction.atomic():
                invernadero = Invernadero.objects.select_for_update(no_key=True).get(pk=libre.pk)
                invernadero.agronomo = self.laura
                invernadero.save()
                RegistroAuditoria.objects.registrar(  # el punto de parada de ``correr_a_la_vez``: ya bloqueó y escribió, sin confirmar
                    usuario=self.gerente,
                    accion=RegistroAuditoria.Accion.MODIFICACION_INVERNADERO,
                    afectados=[invernadero],
                    detalle={"datos": {"motivo": "se asignó un Agrónomo"}},
                )

        resultados = correr_a_la_vez(
            asignar_agronomo,
            lambda: sistemas.registrar_sistema_iot(self.gerente, datos_de_sistema(libre)),
            primera="a",
            detener_antes_de=None,
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [])
        self.assertEqual([codigos(r) for r in rechazos], [["fuera_de_alcance"]])
        self.assertFalse(SistemaIoT.objects.exists())

    def test_regla_4_dos_regeneraciones_a_la_vez_se_ponen_en_fila(self):
        """IOT-MOD-SIS regla 4: las dos terminan y queda vigente el token de una sola; las dos se auditan."""
        sistema = fabricas.sistema(self.norte)
        resultados = correr_a_la_vez(
            lambda: sistemas.regenerar_token(self.laura, sistema.pk),
            lambda: sistemas.regenerar_token(self.laura, sistema.pk),
            primera="a",
        )
        exitos, rechazos, vigentes = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), vigentes), (2, 0, []))
        coinciden = [t for t in exitos if SistemaIoT.objects.filter(token_resumen=resumen_de(t)).exists()]
        self.assertEqual(len(coinciden), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="regeneracion_token_iot").count(), 2)
