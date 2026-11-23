# Pruebas de concurrencia del hardware (docs/casos_de_uso/iot/hardware.md, «Bloqueos» y «Identificador»; docs/patrones/bloqueos.md; D-40):
# dos altas con el mismo identificador, reactivar un equipo mientras otro toma su identificador, y la modificación de un tipo de actuador a la vez
# que el alta de un actuador de ese tipo (el orden de bloqueos «tipo, invernadero, sistema, equipo» evita el bloqueo cruzado). Dos hilos, dos
# conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). ``TransactionTestCase``: su ``flush`` vacía todas las tablas al terminar,
# así que cada prueba vuelve a asegurar los datos en ``setUp`` (docs/patrones/datos_de_migracion.md).

from django.test import TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import Hardware
from iot.tests import fabricas
from iot.tests.fabricas import accion_de_formulario as accion
from iot.tests.fabricas import datos_de, datos_de_equipo
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero_con_geografia_propia

hardware = perezoso("iot.servicios.hardware")
tipos = perezoso("iot.servicios.tipos_actuador")


@tag("concurrencia")
class HardwareConcurrenciaTests(fabricas.ConCatalogoIot, TransactionTestCase):
    """Altas, reactivaciones y modificación de tipos a la vez."""

    def setUp(self):
        fabricas.asegurar_datos_de_iot()
        from maestros.tests.fabricas import asegurar_datos_de_maestros

        asegurar_datos_de_maestros()
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero_con_geografia_propia("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)

    def alta(self, **extra):
        return lambda: hardware.alta_hardware(self.laura, self.sistema.pk, datos_de_equipo(**extra))

    def test_regla_2_dos_altas_con_el_mismo_identificador_crean_un_solo_equipo(self):
        """IOT-ALT-HDW regla 2 y precondición c: uno lo logra y el otro recibe el error del campo ``identificador`` (nunca un 500, nunca dos equipos)."""
        resultados = correr_a_la_vez(self.alta(identificador="norte/uno"), self.alta(identificador="NORTE/UNO", variable="humedad"), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(rechazos[0].error_dict["identificador"][0].code, "identificador_en_uso")
        self.assertEqual(Hardware.objects.filter(clase="sensor").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_hardware").count(), 1)

    def test_regla_2_dos_altas_con_identificadores_distintos_se_crean_las_dos(self):
        """El alta serializa por invernadero pero no rechaza lo que no choca: dos identificadores distintos conviven."""
        resultados = correr_a_la_vez(self.alta(identificador="norte/uno"), self.alta(identificador="norte/dos"), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))

    def test_regla_9_reactivar_un_equipo_mientras_otro_toma_su_identificador(self):
        """IOT-MOD-HDW regla 9: uno de los dos falla con su mensaje y el otro lo logra, sin 500: nunca dos equipos no dados de baja con el mismo identificador."""
        viejo = fabricas.sensor(self.sistema, "norte/uno", estado="inactivo")
        resultados = correr_a_la_vez(
            lambda: hardware.reactivar_hardware(self.laura, viejo.pk), self.alta(identificador="norte/uno"), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn(codigos(rechazos[0]), (["identificador_en_uso"],))
        self.assertEqual(Hardware.objects.filter(identificador_equipo__iexact="norte/uno").exclude(estado_hardware="inactivo").count(), 1)

    def test_regla_9_reactivar_primero_y_despues_dar_de_alta_el_mismo_identificador(self):
        """Lo mismo con el orden inverso: la reactivación confirma primero y el alta recibe el error del campo."""
        viejo = fabricas.sensor(self.sistema, "norte/uno", estado="inactivo")
        resultados = correr_a_la_vez(
            self.alta(identificador="norte/uno"), lambda: hardware.reactivar_hardware(self.laura, viejo.pk), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(Hardware.objects.filter(identificador_equipo__iexact="norte/uno").exclude(estado_hardware="inactivo").count(), 1)

    def modificar_el_tipo_con_una_accion_mas(self, tipo):
        """La modificación de ``tipo`` (agrega «Abrir»): lleva al recálculo de la compatibilidad de sus actuadores, que bloquea sus invernaderos."""
        datos = datos_de(tipo)
        datos.acciones.append(accion("Abrir", "ABRIR"))
        return lambda: tipos.modificar_tipo_actuador(self.gerente, tipo.pk, datos)

    def cruzar_con_la_modificacion_del_tipo(self, tipo, operacion_b):
        """Fuerza el cruce de D-82: la modificación del tipo (``a``) se detiene justo ANTES de bloquear el invernadero, con el tipo ya tomado; recién entonces
        arranca ``operacion_b``. Con el orden tipo, invernadero, sistema y equipo, ``b`` espera el tipo y no toma el invernadero: ``a`` sigue y no hay ciclo. Con el
        orden inverso, ``b`` toma el invernadero y espera el tipo mientras ``a`` espera el invernadero: la base detecta el ciclo y aborta una (``DeadlockDetected``)."""
        return correr_a_la_vez(
            self.modificar_el_tipo_con_una_accion_mas(tipo),
            operacion_b,
            primera="a",
            detener_antes_de=(api_alertas, "bloquear_invernadero_para_alertas"),
        )

    def test_d82_modificar_un_tipo_a_la_vez_que_se_da_de_alta_un_actuador_de_ese_tipo_no_se_cruzan(self):
        """D-82 (tipo, invernadero, sistema, equipo): modificar las acciones de un tipo recalcula la compatibilidad de sus actuadores (bloquea sus invernaderos, ya con el
        tipo tomado) y el alta de un actuador de ese tipo bloquea el tipo y después el invernadero. Con barrera: ``a`` se detiene con el tipo tomado y sin el invernadero;
        las dos terminan, sin bloqueo cruzado ni 500."""
        tipo = fabricas.tipo_actuador("Extractor")
        fabricas.actuador(self.sistema, tipo, "norte/existente")
        fabricas.equipo_anunciado(self.sistema, "norte/existente", ("ENCENDER", "APAGAR"))
        exitos, rechazos, otros = separar(self.cruzar_con_la_modificacion_del_tipo(tipo, self.alta_de_actuador(tipo)))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))

    def test_d82_modificar_un_tipo_a_la_vez_que_se_cambia_el_tipo_de_un_actuador_no_se_cruzan(self):
        """D-82 también vale al cambiar el tipo de un actuador (IOT-MOD-HDW regla 3): tipo antes que invernadero. Misma barrera; las dos terminan, sin 500."""
        tipo = fabricas.tipo_actuador("Extractor")
        otro = fabricas.tipo_actuador("Aspersor")
        fabricas.actuador(self.sistema, tipo, "norte/existente")
        movil = fabricas.actuador(self.sistema, otro, "norte/movil")
        cambio = lambda: hardware.modificar_hardware(  # noqa: E731
            self.laura, movil.pk, fabricas.datos_de_equipo_guardado(movil, tipo_actuador_id=tipo.pk)
        )
        exitos, rechazos, otros = separar(self.cruzar_con_la_modificacion_del_tipo(tipo, cambio))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))

    def alta_de_actuador(self, tipo):
        return lambda: hardware.alta_hardware(
            self.laura, self.sistema.pk, datos_de_equipo("actuador", identificador="norte/nuevo", tipo_actuador_id=tipo.pk)
        )

    def test_baja_del_tipo_a_la_vez_que_el_alta_de_un_actuador_se_rechaza_una_de_las_dos(self):
        """IOT-BAJ-TAC precondición c y contrato de ``bloquear_tipo_activo``: o el alta gana y la baja se rechaza porque ve el actuador, o la baja
        gana y el alta se rechaza porque el tipo está dado de baja. Nunca queda un actuador activo de un tipo dado de baja."""
        from iot.models import Actuador, TipoActuador

        tipo = fabricas.tipo_actuador("Extractor")
        resultados = correr_a_la_vez(
            lambda: tipos.baja_tipo_actuador(self.gerente, tipo.pk), self.alta_de_actuador(tipo), primera="b"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        inactivo = TipoActuador.objects.get(pk=tipo.pk).estado == "inactivo"
        self.assertEqual(Actuador.objects.filter(tipo_actuador=tipo).exclude(estado_hardware="inactivo").exists(), not inactivo)
