# Pruebas de concurrencia de los servicios de tipos de actuador (IOT-01, paso 3; docs/patrones/bloqueos.md y
# docs/casos_de_uso/iot/tipos_de_actuador.md, «Bloqueos»): dos altas con el mismo nombre, la baja y la modificación a la vez, y dos
# modificaciones al mismo nombre. Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Son
# ``TransactionTestCase``: su ``flush`` vacía todas las tablas al terminar (también el catálogo del IoT, las categorías del sistema y
# los tipos de etapa), así que cada prueba vuelve a asegurar esos datos en ``setUp`` (docs/patrones/datos_de_migracion.md).

from django.test import TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from inventario.tests.fabricas import perezoso
from iot.models import Accion, TipoActuador
from iot.tests import fabricas
from iot.tests.fabricas import accion_de_formulario as accion
from iot.tests.fabricas import datos_de, datos_de_tipo
from core.tests.fabricas import crear_gerente

tipos = perezoso("iot.servicios.tipos_actuador")


@tag("concurrencia")
class TiposActuadorConcurrenciaTests(fabricas.ConCatalogoIot, TransactionTestCase):
    """Alta, modificación y baja de un tipo a la vez. El Gerente es uno solo (D-09): las dos operaciones son de dos pedidos suyos."""

    def setUp(self):
        fabricas.asegurar_datos_de_iot()  # el flush de la prueba anterior vació el catálogo y los tipos
        from maestros.tests.fabricas import asegurar_datos_de_maestros

        asegurar_datos_de_maestros()
        self.gerente = crear_gerente()

    def test_regla_2_dos_altas_con_el_mismo_nombre_crean_un_solo_tipo(self):
        """IOT-ALT-TAC regla 2 y docs/patrones/abm.md, sección 2, paso 6: la segunda alta no ve el tipo sin confirmar, espera en el
        índice único de la base y, cuando la primera confirma, recibe el error del campo ``nombre``: nunca un 500."""
        resultados = correr_a_la_vez(
            lambda: tipos.alta_tipo_actuador(self.gerente, datos_de_tipo("Extractor")),
            lambda: tipos.alta_tipo_actuador(self.gerente, datos_de_tipo("extractor")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(rechazos[0].error_dict["nombre"][0].code, "nombre_repetido")
        self.assertEqual(TipoActuador.objects.filter(nombre_actuador__iexact="extractor").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_tipo_actuador").count(), 1)
        self.assertEqual(Accion.objects.filter(tipo_actuador__nombre_actuador__iexact="extractor").count(), 2)

    def test_regla_2_dos_altas_con_nombres_distintos_se_crean_las_dos(self):
        """El alta no bloquea nada: dos nombres distintos conviven."""
        resultados = correr_a_la_vez(
            lambda: tipos.alta_tipo_actuador(self.gerente, datos_de_tipo("Extractor")),
            lambda: tipos.alta_tipo_actuador(self.gerente, datos_de_tipo("Aspersor")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))

    def test_regla_2_dos_modificaciones_al_mismo_nombre_dejan_un_solo_tipo_con_ese_nombre(self):
        """IOT-MOD-TAC regla 2: dos tipos renombrados a la vez al mismo nombre; la base respalda la unicidad y el segundo recibe el error del
        campo (nunca un 500)."""
        uno, otro = fabricas.tipo_actuador("Uno"), fabricas.tipo_actuador("Otro")
        nuevo, minuscula = datos_de(uno), datos_de(otro)
        nuevo.nombre, minuscula.nombre = "Repetido", "repetido"
        resultados = correr_a_la_vez(
            lambda: tipos.modificar_tipo_actuador(self.gerente, uno.pk, nuevo),
            lambda: tipos.modificar_tipo_actuador(self.gerente, otro.pk, minuscula),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(rechazos[0].error_dict["nombre"][0].code, "nombre_repetido")
        self.assertEqual(TipoActuador.objects.filter(nombre_actuador__iexact="repetido").count(), 1)

    def test_regla_7_la_modificacion_espera_a_la_baja_y_se_rechaza_porque_ve_el_tipo_inactivo(self):
        """IOT-MOD-TAC regla 7 e IOT-BAJ-TAC: la modificación bloquea el tipo, espera a que la baja confirme, lo relee inactivo y se
        rechaza con ``tipo_inactivo``: no queda un tipo dado de baja con cambios a medias. Las dos terminan, sin 500."""
        tipo = fabricas.tipo_actuador("Extractor")
        datos = datos_de(tipo)
        datos.acciones.append(accion("Girar", "ABRIR"))
        resultados = correr_a_la_vez(
            lambda: tipos.baja_tipo_actuador(self.gerente, tipo.pk),
            lambda: tipos.modificar_tipo_actuador(self.gerente, tipo.pk, datos),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["tipo_inactivo"])
        tipo.refresh_from_db()
        self.assertEqual(tipo.estado, "inactivo")
        self.assertEqual(tipo.acciones.count(), 2)

    def test_regla_5_la_baja_espera_a_la_modificacion_y_las_dos_terminan(self):
        """IOT-MOD-TAC e IOT-BAJ-TAC: la baja espera a que la modificación confirme y se aplica sobre el tipo ya modificado."""
        tipo = fabricas.tipo_actuador("Extractor")
        datos = datos_de(tipo)
        datos.nombre = "Extractor 2"
        resultados = correr_a_la_vez(
            lambda: tipos.modificar_tipo_actuador(self.gerente, tipo.pk, datos),
            lambda: tipos.baja_tipo_actuador(self.gerente, tipo.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        tipo.refresh_from_db()
        self.assertEqual((tipo.nombre_actuador, tipo.estado), ("Extractor 2", "inactivo"))

    def test_pre_c_la_baja_espera_a_quien_crea_un_actuador_y_se_rechaza_porque_lo_ve(self):
        """IOT-BAJ-TAC precondición c y contrato de ``bloquear_tipo_activo`` (para IOT-02): quien crea un actuador bloquea el tipo ANTES de
        insertarlo; la baja espera, cuenta los equipos después de bloquear y se rechaza. Sin ese bloqueo, el ``INSERT`` solo toma
        ``FOR KEY SHARE`` (no choca con el ``FOR NO KEY UPDATE`` de la baja) y se daría de baja un tipo con un equipo."""
        from maestros.tests.fabricas import crear_invernadero_con_geografia_propia

        tipo = fabricas.tipo_actuador("Extractor")
        sistema = fabricas.sistema(crear_invernadero_con_geografia_propia("Norte"))

        def crear_actuador():
            from django.db import transaction

            with transaction.atomic():
                bloqueado = tipos.bloquear_tipo_activo(tipo.pk)
                return fabricas.actuador(sistema, bloqueado)

        resultados = correr_a_la_vez(
            crear_actuador,
            lambda: tipos.baja_tipo_actuador(self.gerente, tipo.pk),
            primera="a",
            detener_antes_de=(fabricas, "actuador"),
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["equipos_activos"])
        tipo.refresh_from_db()
        self.assertEqual(tipo.estado, "activo")
