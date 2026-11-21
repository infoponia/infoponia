# Pruebas de ADM-MOD-CFG (Modificar Configuración Operativa, MAE-04): precondición, reglas 1 a 7, postcondiciones a y b, D-28
# (sin cambios no audita) y la concurrencia del mismo Gerente en dos pedidos. Fuente: docs/casos_de_uso/maestros/configuracion.md.
# Servicio: ``maestros/servicios/configuracion.py``.

from django.core.exceptions import PermissionDenied
from django.test import TestCase, TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from maestros.models import PARAMETROS_DE_CONFIGURACION, ConfiguracionOperativa
from maestros.servicios import configuracion
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    asegurar_datos_de_maestros,
    codigos_de,
    crear_agronomo,
    error_de,
)

CAMPOS = [c for c, *_ in PARAMETROS_DE_CONFIGURACION]


def actuales():
    """Los 13 parámetros guardados, ``{campo: valor}``."""
    fila = ConfiguracionOperativa.objects.get()
    return {campo: getattr(fila, campo) for campo in CAMPOS}


def auditorias():
    """Los registros de ``modificacion_configuracion``, del más viejo al más nuevo."""
    return list(RegistroAuditoria.objects.filter(accion="modificacion_configuracion").order_by("id"))


class AdmModCfgServicioTests(ConDatosDeMaestros, TestCase):
    """ADM-MOD-CFG: las reglas del servicio."""

    def setUp(self):
        self.gerente = crear_gerente()

    # ---- precondición a y regla 1 ----

    def test_pre_a_solo_un_gerente_activo_modifica(self):
        """ADM-MOD-CFG precondición a y regla 1: cualquier otra cuenta, o ninguna, recibe ``PermissionDenied``."""
        gerente_inactivo = crear_gerente(email="baja@infoponia.com", activo=False)
        for actor in (crear_agronomo(), crear_capataz(), crear_administrador(), gerente_inactivo, None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    configuracion.modificar_configuracion(actor, porc_merma_maxima=20)
        self.assertEqual(actuales()["porc_merma_maxima"], 15)
        self.assertEqual(auditorias(), [])

    def test_regla_1_obtener_devuelve_la_fila_unica_con_los_valores_actuales(self):
        """Regla 1: al entrar se muestran los valores actuales; ``obtener`` lee la fila vigente cada vez (regla 7)."""
        self.assertEqual(configuracion.obtener().porc_merma_maxima, 15)
        configuracion.modificar_configuracion(self.gerente, porc_merma_maxima=20)
        self.assertEqual(configuracion.obtener().porc_merma_maxima, 20)

    def test_regla_1_obtener_crea_la_fila_si_faltara(self):
        """Regla 1 y patrón de singletons (red de seguridad): sin fila, ``obtener`` la crea con los valores iniciales."""
        ConfiguracionOperativa.objects.all().delete()
        fila = configuracion.obtener()
        self.assertEqual(ConfiguracionOperativa.objects.count(), 1)
        self.assertEqual(fila.dias_horizonte_cosecha, 30)

    # ---- regla 3: dominios ----

    def test_regla_3_dominios(self):
        """Regla 3: cada parámetro rechaza lo que está fuera de su dominio, con el error en su propio campo, y acepta el
        mínimo del dominio."""
        for campo, _, _, minimo, maximo in PARAMETROS_DE_CONFIGURACION:
            if campo == "dias_anticipacion_cosecha_suministro":
                continue  # su máximo es la regla 4
            with self.subTest(campo=campo, valor=minimo - 1):
                error = error_de(lambda: configuracion.modificar_configuracion(self.gerente, **{campo: minimo - 1}))
                self.assertEqual(list(error.error_dict), [campo])
                self.assertEqual(codigos_de(error, campo), ["minimo"])
            if maximo is not None:
                with self.subTest(campo=campo, valor=maximo + 1):
                    error = error_de(lambda: configuracion.modificar_configuracion(self.gerente, **{campo: maximo + 1}))
                    self.assertEqual(codigos_de(error, campo), ["maximo"])
            with self.subTest(campo=campo, extremo=minimo):
                # Con la pre-reserva en su mínimo, la anticipación vigente (3) la superaría (regla 4): se baja a 0 a la vez.
                extra = {"dias_anticipacion_cosecha_suministro": 0} if campo == "dias_pre_reserva_suministro" else {}
                configuracion.modificar_configuracion(self.gerente, **{campo: minimo}, **extra)
                self.assertEqual(actuales()[campo], minimo)

    def test_regla_3_merma_de_1_a_100_y_tolerancia_de_0_a_100(self):
        """Regla 3: merma 0 y 101 rechazados, 100 aceptado; tolerancia 100 aceptada."""
        configuracion.modificar_configuracion(self.gerente, porc_merma_maxima=100, porc_tolerancia_cobertura_pedido=100)
        self.assertEqual(actuales()["porc_merma_maxima"], 100)
        self.assertEqual(actuales()["porc_tolerancia_cobertura_pedido"], 100)
        error = error_de(lambda: configuracion.modificar_configuracion(self.gerente, porc_merma_maxima=0))
        self.assertEqual(codigos_de(error, "porc_merma_maxima"), ["minimo"])
        error = error_de(lambda: configuracion.modificar_configuracion(self.gerente, porc_merma_maxima=101))
        self.assertEqual(codigos_de(error, "porc_merma_maxima"), ["maximo"])

    def test_regla_3_vacio_o_no_entero_se_rechaza(self):
        """Regla 3: todos los valores son enteros y obligatorios. Vacío, decimales, texto o un booleano dan error de campo."""
        casos = (("", "obligatorio"), ("  ", "obligatorio"), (None, "obligatorio"), ("abc", "no_entero"),
                 ("1.5", "no_entero"), (1.5, "no_entero"), (True, "no_entero"), ("1e3", "no_entero"))
        for valor, codigo in casos:
            with self.subTest(valor=valor):
                error = error_de(lambda: configuracion.modificar_configuracion(self.gerente, dias_limite_cotizacion=valor))
                self.assertEqual(codigos_de(error, "dias_limite_cotizacion"), [codigo])

    def test_regla_3_acepta_enteros_escritos_como_texto(self):
        """Regla 3: la pantalla envía texto; «20» y « 5 » valen como 20 y 5."""
        configuracion.modificar_configuracion(self.gerente, porc_merma_maxima="20", dias_limite_cotizacion=" 5 ")
        self.assertEqual(actuales()["porc_merma_maxima"], 20)
        self.assertEqual(actuales()["dias_limite_cotizacion"], 5)

    def test_regla_3_el_parametro_de_faltante_es_un_parametro_mas(self):
        """Regla 2 y 3 (MD-89): la vigencia del enlace de decisión ante un faltante se guarda y es de 1 o más."""
        configuracion.modificar_configuracion(self.gerente, dias_vigencia_enlace_faltante=5)
        self.assertEqual(actuales()["dias_vigencia_enlace_faltante"], 5)
        error = error_de(lambda: configuracion.modificar_configuracion(self.gerente, dias_vigencia_enlace_faltante=0))
        self.assertEqual(codigos_de(error, "dias_vigencia_enlace_faltante"), ["minimo"])

    # ---- regla 4 ----

    def test_regla_4_anticipacion_del_suministro_mayor_que_la_pre_reserva_se_rechaza(self):
        """Regla 4: la anticipación de cosecha del suministro no supera la pre-reserva; el error va en el campo de la
        anticipación y no se guarda nada."""
        error = error_de(lambda: configuracion.modificar_configuracion(
            self.gerente, dias_pre_reserva_suministro=5, dias_anticipacion_cosecha_suministro=6))
        self.assertEqual(list(error.error_dict), ["dias_anticipacion_cosecha_suministro"])
        self.assertEqual(codigos_de(error, "dias_anticipacion_cosecha_suministro"), ["supera_pre_reserva"])
        self.assertEqual(actuales()["dias_pre_reserva_suministro"], 14)

    def test_regla_4_igual_a_la_pre_reserva_se_acepta(self):
        """Regla 4: «no puede superar»: igual vale."""
        configuracion.modificar_configuracion(
            self.gerente, dias_pre_reserva_suministro=5, dias_anticipacion_cosecha_suministro=5)
        self.assertEqual(actuales()["dias_anticipacion_cosecha_suministro"], 5)

    def test_regla_4_se_compara_con_la_pre_reserva_guardada_si_no_se_envia_la_otra(self):
        """Regla 4: si solo se envía la anticipación, se compara con la pre-reserva vigente (14)."""
        error = error_de(
            lambda: configuracion.modificar_configuracion(self.gerente, dias_anticipacion_cosecha_suministro=15))
        self.assertEqual(codigos_de(error, "dias_anticipacion_cosecha_suministro"), ["supera_pre_reserva"])

    # ---- regla 5 ----

    def test_regla_5_horizonte_menor_que_la_pre_reserva_advierte_y_guarda(self):
        """Regla 5: el horizonte menor que la pre-reserva se advierte y se deja guardar."""
        resultado = configuracion.modificar_configuracion(
            self.gerente, dias_horizonte_cosecha=10, dias_pre_reserva_suministro=14)
        self.assertEqual(actuales()["dias_horizonte_cosecha"], 10)
        self.assertEqual(len(resultado.advertencias), 1)
        self.assertIn("pre-reserva", resultado.advertencias[0])

    def test_regla_5_sin_horizonte_menor_no_hay_advertencia(self):
        """Regla 5: con el horizonte igual o mayor que la pre-reserva no hay advertencia."""
        resultado = configuracion.modificar_configuracion(
            self.gerente, dias_horizonte_cosecha=14, dias_pre_reserva_suministro=14)
        self.assertEqual(resultado.advertencias, [])

    def test_regla_5_advertencias_de_calcula_sin_guardar(self):
        """Regla 5: ``advertencias_de`` sirve a la pantalla para advertir al mostrar, sin tocar la base."""
        menor = {"dias_horizonte_cosecha": 3, "dias_pre_reserva_suministro": 4}
        igual = {"dias_horizonte_cosecha": 4, "dias_pre_reserva_suministro": 4}
        self.assertEqual(len(configuracion.advertencias_de(menor)), 1)
        self.assertEqual(configuracion.advertencias_de(igual), [])

    # ---- regla 6: todo o nada ----

    def test_regla_6_un_valor_invalido_no_guarda_ninguno_y_marca_todos_los_campos_con_error(self):
        """Regla 6: con dos campos inválidos y uno válido, se devuelven los dos errores juntos y no se guarda ni el válido."""
        antes = actuales()
        error = error_de(lambda: configuracion.modificar_configuracion(
            self.gerente, porc_merma_maxima=0, dias_limite_cotizacion="", dias_aviso_vencimiento=20))
        self.assertEqual(set(error.error_dict), {"porc_merma_maxima", "dias_limite_cotizacion"})
        self.assertEqual(actuales(), antes)
        self.assertEqual(auditorias(), [])

    def test_regla_6_un_campo_desconocido_se_rechaza(self):
        """Un parámetro que no existe es un error de programación, no un dato: ``TypeError``."""
        with self.assertRaises(TypeError):
            configuracion.modificar_configuracion(self.gerente, parametro_inexistente=1)

    # ---- postcondiciones ----

    def test_post_a_actualiza_solo_los_parametros_indicados(self):
        """Postcondición a: se actualizan los parámetros indicados y los demás quedan igual; devuelve la configuración."""
        antes = actuales()
        resultado = configuracion.modificar_configuracion(self.gerente, porc_merma_maxima=25, dias_limite_cotizacion=4)
        despues = actuales()
        cambiaron = {c for c in CAMPOS if antes[c] != despues[c]}
        self.assertEqual(cambiaron, {"porc_merma_maxima", "dias_limite_cotizacion"})
        self.assertEqual(resultado.configuracion.porc_merma_maxima, 25)

    def test_post_b_audita_con_el_antes_y_el_despues_de_cada_parametro(self):
        """Postcondición b y D-36: un registro con usuario, la configuración como afectada y, de cada parámetro modificado,
        su valor anterior y su valor nuevo; no figuran los que no cambiaron."""
        configuracion.modificar_configuracion(
            self.gerente, porc_merma_maxima=25, dias_limite_cotizacion=4, dias_aviso_vencimiento=15)
        (registro,) = auditorias()
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.detalle, {"cambios": {
            "porc_merma_maxima": {"antes": 15, "despues": 25},
            "dias_limite_cotizacion": {"antes": 3, "despues": 4},
        }})
        self.assertEqual([(a["modelo"], a["id"]) for a in registro.afectados],
                         [("maestros.configuracionoperativa", ConfiguracionOperativa.objects.get().pk)])

    def test_d28_sin_cambios_no_escribe_ni_audita(self):
        """D-28: guardar los mismos valores no escribe ni deja registro de auditoría (aunque lleguen como texto)."""
        resultado = configuracion.modificar_configuracion(self.gerente, **{c: str(v) for c, v in actuales().items()})
        self.assertEqual(auditorias(), [])
        self.assertEqual(resultado.configuracion.porc_merma_maxima, 15)

    def test_d28_la_advertencia_se_devuelve_aunque_no_haya_cambios(self):
        """Regla 5: con un horizonte menor que la pre-reserva ya guardado, guardar igual sigue advirtiendo."""
        configuracion.modificar_configuracion(self.gerente, dias_horizonte_cosecha=10)
        resultado = configuracion.modificar_configuracion(self.gerente, dias_horizonte_cosecha=10)
        self.assertEqual(len(resultado.advertencias), 1)
        self.assertEqual(len(auditorias()), 1)


@tag("concurrencia")
class AdmModCfgConcurrenciaTests(ConDatosDeMaestros, TransactionTestCase):
    """Bloqueo de la fila única (patrón de singletons; D-09 permite un solo Gerente activo, así que el choque es de la
    misma cuenta en dos pedidos). Gana el último y el segundo calcula su «antes» contra lo ya modificado."""

    def setUp(self):
        asegurar_datos_de_maestros()  # el flush de la prueba anterior vació las filas únicas
        self.gerente = crear_gerente()

    def test_regla_6_dos_modificaciones_a_la_vez_gana_la_ultima_y_audita_contra_lo_releido(self):
        """El segundo pedido espera el bloqueo, relee y su «antes» es el «después» del primero; nunca un error 500."""
        resultados = correr_a_la_vez(
            lambda: configuracion.modificar_configuracion(self.gerente, porc_merma_maxima=20),
            lambda: configuracion.modificar_configuracion(self.gerente, porc_merma_maxima=30),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(actuales()["porc_merma_maxima"], 30)
        self.assertEqual(
            [r.detalle["cambios"]["porc_merma_maxima"] for r in auditorias()],
            [{"antes": 15, "despues": 20}, {"antes": 20, "despues": 30}],
        )

    def test_d28_el_segundo_pedido_con_el_mismo_valor_ya_guardado_no_audita(self):
        """D-28 con bloqueo: si el primero ya dejó el valor que pide el segundo, el segundo no cambia nada y no audita."""
        resultados = correr_a_la_vez(
            lambda: configuracion.modificar_configuracion(self.gerente, porc_merma_maxima=20),
            lambda: configuracion.modificar_configuracion(self.gerente, porc_merma_maxima=20),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(len(auditorias()), 1)

    def test_regla_4_se_valida_contra_la_fila_releida_despues_de_bloquear(self):
        """Regla 4 con concurrencia: el primero baja la pre-reserva a 2; el segundo pide una anticipación de 3 (válida
        contra el 14 que veía antes). Releída la fila, supera la pre-reserva y se rechaza sin tocar nada."""
        resultados = correr_a_la_vez(
            lambda: configuracion.modificar_configuracion(
                self.gerente, dias_pre_reserva_suministro=2, dias_anticipacion_cosecha_suministro=2),
            lambda: configuracion.modificar_configuracion(self.gerente, dias_anticipacion_cosecha_suministro=3),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["supera_pre_reserva"])
        self.assertEqual(actuales()["dias_anticipacion_cosecha_suministro"], 2)
