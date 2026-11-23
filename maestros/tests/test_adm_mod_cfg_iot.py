# Pruebas de ADM-MOD-CFG, sección «Módulo IoT» (IOT-04, paso 8; docs/casos_de_uso/maestros/configuracion.md, sección «ADM-MOD-CFG · Sección «Módulo IoT»»: reglas 2b, 3b, 4b, 5b y 7b; D-36, D-76 punto 10).
# Se escribieron ANTES que el código (`.claude/rules/pruebas.md`). Los 14 parámetros ya existen en ``ConfiguracionOperativa`` (IOT-01): acá se agregan al servicio ``modificar_configuracion``
# (maestros/servicios/configuracion.py) y a la pantalla (maestros/views.py, maestros/forms.py y la plantilla de parámetros). Las pruebas existentes de maestros no se modifican.
#
# Contrato nuevo del servicio: ``modificar_configuracion(actor, *, ahora=None, **valores)`` acepta también los 14 campos de ``PARAMETROS_IOT``; ``ahora`` es el reloj (un ``datetime`` con zona; por omisión,
# el actual) y solo sirve para la fecha de la advertencia 5b: así las pruebas nunca dependen de la hora real. ``Resultado.advertencias`` suma la 5b. Pantalla: ``FormularioConfiguracion`` sigue con
# sus 13 campos y un formulario aparte, ``FormularioConfiguracionIot`` (14 campos, en ``context["form_iot"]``), va dentro del mismo ``<form>``; la vista le pasa al servicio solo los campos IoT que
# vienen en el POST.

import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied
from django.test import TestCase, TransactionTestCase, tag
from django.urls import reverse

from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from core.tests.fabricas import CLAVE, crear_administrador, crear_capataz, crear_gerente
from maestros.forms import GRUPOS_IOT, FormularioConfiguracion
from maestros.models import PARAMETROS_DE_CONFIGURACION, PARAMETROS_IOT, ConfiguracionOperativa
from maestros.servicios import configuracion
from maestros.tests.fabricas import ConDatosDeMaestros, asegurar_datos_de_maestros, crear_agronomo, error_de

LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")
AHORA = datetime(2026, 11, 23, 12, 0, tzinfo=LOCAL)  # lunes, mediodía
CAMPOS_IOT = [campo for campo, *_ in PARAMETROS_IOT]
DECIMALES = ("histeresis_temperatura", "histeresis_temp_solucion")
URL = reverse("configuracion:pantalla")
URL_PARAMETROS = reverse("configuracion:guardar_parametros")
HTMX = {"HTTP_HX_REQUEST": "true"}
AVISO_IOT = "Parámetros guardados. Rigen desde el próximo intento y la próxima lectura."
AVISO_MAE_04 = "Se guardó la configuración."
MENSAJE_DECIMAL = "Ingresá un número entre 0 y 10, con un decimal como máximo."
MENSAJE_FIN = "El fin tiene que ser posterior al inicio."


def entero(minimo, maximo):
    return f"Ingresá un entero entre {minimo} y {maximo}."


def iot():
    """Los 14 parámetros IoT guardados, ``{campo: valor}``."""
    fila = ConfiguracionOperativa.objects.get()
    return {campo: getattr(fila, campo) for campo in CAMPOS_IOT}


def produccion():
    return {campo: getattr(ConfiguracionOperativa.objects.get(), campo) for campo, *_ in PARAMETROS_DE_CONFIGURACION}


def auditorias():
    return list(RegistroAuditoria.objects.filter(accion="modificacion_configuracion").order_by("id"))


def mensajes(error, campo):
    """Los mensajes de un campo de una ``ValidationError`` del servicio."""
    return [e.message for e in error.error_dict[campo]]


def guarda(gerente, **valores):
    return configuracion.modificar_configuracion(gerente, ahora=AHORA, **valores)


class AdmModCfgIotServicioTests(ConDatosDeMaestros, TestCase):
    """Las reglas 3b, 4b, 5b y 7b, y la auditoría, en el servicio."""

    def setUp(self):
        self.gerente = crear_gerente()

    # ---- precondición a y el alcance de la sección ----

    def test_pre_a_solo_un_gerente_activo_modifica_los_parametros_del_iot(self):
        """ADM-MOD-CFG precondición a y regla 1 (la sección IoT es del Gerente; el Agrónomo la ve en el panel, D-76 punto 9): cualquier otra cuenta recibe `PermissionDenied` y no cambia nada."""
        for actor in (crear_agronomo(), crear_capataz(), crear_administrador(), None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    guarda(actor, hora_fin_luz=20)
        self.assertEqual(iot()["hora_fin_luz"], 18)
        self.assertEqual(auditorias(), [])

    def test_regla_2b_se_modifican_los_catorce_parametros_con_su_antes_y_su_despues(self):
        """Regla 2b: los 14 parámetros del Módulo IoT se modifican con el mismo servicio; la auditoría los guarda todos con su antes y su después."""
        nuevos = dict(
            cant_reintentos_comando=5, segundos_intervalo_reintento=120, hora_inicio_luz=6, hora_fin_luz=20, lux_umbral_fotoperiodo=2000,
            minutos_sin_actividad=10, minutos_sin_comunicacion=6, minutos_antiguedad_lectura=15, cant_lecturas_confirmacion=4,
            histeresis_temperatura=Decimal("1.5"), histeresis_humedad=5, histeresis_luz=3000, histeresis_temp_solucion=Decimal("0.5"), dias_retencion_telemetria=30,
        )
        guarda(self.gerente, **nuevos)
        self.assertEqual(iot(), nuevos)
        (registro,) = auditorias()
        self.assertEqual(set(registro.detalle["cambios"]), set(CAMPOS_IOT))
        self.assertEqual(registro.detalle["cambios"]["hora_fin_luz"], {"antes": 18, "despues": 20})

    def test_regla_7b_lo_que_no_se_indica_queda_como_esta_y_los_del_iot_no_se_tocan_sin_pedirlos(self):
        """Regla 7b y MAE-04: un pedido solo con parámetros de producción no toca los del IoT (y al revés); lo que no se indica queda como está."""
        ConfiguracionOperativa.objects.filter(singleton=1).update(hora_fin_luz=20, histeresis_temperatura=Decimal("2.5"))
        guarda(self.gerente, porc_merma_maxima=25)
        self.assertEqual((iot()["hora_fin_luz"], iot()["histeresis_temperatura"]), (20, Decimal("2.5")))
        guarda(self.gerente, minutos_sin_actividad=9)
        self.assertEqual(produccion()["porc_merma_maxima"], 25)

    # ---- regla 3b: dominios ----

    def test_regla_3b_cada_dominio_acepta_su_borde_y_rechaza_uno_mas_afuera_con_su_mensaje(self):
        """Regla 3b: cada parámetro entero acepta el mínimo y el máximo de su dominio y rechaza uno más afuera con «Ingresá un entero entre {mín} y {máx}.» en su propio campo. (El fin del
        horario de luz se prueba con el inicio en 0 y el inicio, con el fin en 24, para no chocar con la regla 4b.)"""
        for campo, _, _, minimo, maximo in PARAMETROS_IOT:
            if campo in DECIMALES:
                continue
            ajuste = {"hora_fin_luz": {"hora_inicio_luz": 0}, "hora_inicio_luz": {"hora_fin_luz": 24}}.get(campo, {})
            for valor in (minimo, maximo):
                with self.subTest(campo=campo, acepta=valor):
                    guarda(self.gerente, **{campo: valor}, **ajuste)
                    self.assertEqual(iot()[campo], valor)
            for valor in (minimo - 1, maximo + 1):
                with self.subTest(campo=campo, rechaza=valor):
                    antes = iot()
                    error = error_de(lambda: guarda(self.gerente, **{campo: valor}, **ajuste))
                    self.assertEqual(list(error.error_dict), [campo])
                    self.assertEqual(mensajes(error, campo), [entero(minimo, maximo)])
                    self.assertEqual(iot(), antes)

    def test_regla_3b_los_dominios_de_la_tabla_de_md_112(self):
        """Regla 3b y `docs/modelo/iot.md`, «Parámetros IoT»: reintentos de 0 a 10; intervalo de 10 a 3600; inicio de la luz de 0 a 23 y fin de 1 a 24; umbral de luz de 1 a 100000; minutos sin actividad, sin
        comunicación y antigüedad de 1 a 1440; lecturas de confirmación de 1 a 10; histéresis de humedad de 0 a 30 y de luz de 0 a 20000; retención de 1 a 365."""
        dominios = {c: (mn, mx) for c, _, _, mn, mx in PARAMETROS_IOT}
        self.assertEqual(dominios["cant_reintentos_comando"], (0, 10))
        self.assertEqual(dominios["segundos_intervalo_reintento"], (10, 3600))
        self.assertEqual((dominios["hora_inicio_luz"], dominios["hora_fin_luz"]), ((0, 23), (1, 24)))
        self.assertEqual(dominios["lux_umbral_fotoperiodo"], (1, 100000))
        for campo in ("minutos_sin_actividad", "minutos_sin_comunicacion", "minutos_antiguedad_lectura"):
            self.assertEqual(dominios[campo], (1, 1440))
        self.assertEqual(dominios["cant_lecturas_confirmacion"], (1, 10))
        self.assertEqual((dominios["histeresis_humedad"], dominios["histeresis_luz"]), ((0, 30), (0, 20000)))
        self.assertEqual(dominios["dias_retencion_telemetria"], (1, 365))
        self.assertEqual([dominios[c] for c in DECIMALES], [(0, 10), (0, 10)])

    def test_regla_3b_un_entero_que_no_es_entero_da_el_mismo_mensaje_sin_500(self):
        """Regla 3b: vacío, solo espacios, `None`, texto, un decimal en un parámetro entero, un booleano o un texto enorme dan el mensaje del dominio en su campo; nunca un error del servidor."""
        for valor in ("", "   ", None, "abc", "1.5", "7,5", True, "9" * 500, "1e3", "٣"):
            with self.subTest(valor=valor):
                error = error_de(lambda: guarda(self.gerente, cant_reintentos_comando=valor))
                self.assertEqual(mensajes(error, "cant_reintentos_comando"), [entero(0, 10)])
        self.assertEqual(iot()["cant_reintentos_comando"], 3)

    def test_regla_3b_un_entero_escrito_como_texto_con_espacios_se_acepta(self):
        """Mismo criterio que MAE-04: «" 5 "» y «"5"» son 5 (el formulario manda texto)."""
        guarda(self.gerente, minutos_sin_actividad=" 9 ", minutos_sin_comunicacion="4")
        self.assertEqual((iot()["minutos_sin_actividad"], iot()["minutos_sin_comunicacion"]), (9, 4))

    # ---- regla 3b: las histéresis de temperatura admiten un decimal ----

    def test_regla_3b_las_histeresis_de_temperatura_admiten_un_decimal_con_coma_o_con_punto(self):
        """Regla 3b: la histéresis de la temperatura y la de la solución admiten un decimal: 1,5 entra (con coma o con punto, como número o como texto) y se guarda como `Decimal`; 0 y 10 son los bordes."""
        for campo in DECIMALES:
            for escrito, esperado in (("1,5", "1.5"), ("1.5", "1.5"), (Decimal("2.5"), "2.5"), ("0", "0"), ("10", "10"), ("10,0", "10"), (" 3,5 ", "3.5"), ("2", "2")):
                with self.subTest(campo=campo, escrito=escrito):
                    guarda(self.gerente, **{campo: escrito})
                    self.assertEqual(iot()[campo], Decimal(esperado))

    def test_regla_3b_las_histeresis_de_temperatura_rechazan_dos_decimales_fuera_de_dominio_y_texto(self):
        """Regla 3b: 1,55 (y 1.55, 1,05, 0,25) no entran: «Ingresá un número entre 0 y 10, con un decimal como máximo.»; tampoco -0,1, 10,1, 11, texto, vacío, `None`, varias comas ni un texto enorme: nunca un 500 y no se guarda nada."""
        for campo in DECIMALES:
            for escrito in ("1,55", "1.55", "1,05", "0,25", "-0,1", "-1", "10,1", "11", "abc", "", "  ", None, "1,5,5", "1.5.5", ",5", "5,", "1e1", "9" * 500, True):
                with self.subTest(campo=campo, escrito=escrito):
                    error = error_de(lambda: guarda(self.gerente, **{campo: escrito}))
                    self.assertEqual(list(error.error_dict), [campo])
                    self.assertEqual(mensajes(error, campo), [MENSAJE_DECIMAL])
            self.assertEqual(iot()[campo], Decimal("1.0"))

    # ---- regla 4b ----

    def test_regla_4b_el_fin_igual_o_anterior_al_inicio_da_error_en_hora_fin_luz_y_no_guarda_nada(self):
        """Regla 4b: el fin del horario de luz es posterior a su inicio. Fin igual al inicio y fin anterior dan el error en `hora_fin_luz` («El fin tiene que ser posterior al inicio.») y no se guarda nada,
        tampoco el otro parámetro válido del mismo pedido."""
        for inicio, fin in ((8, 8), (8, 7), (23, 22), (5, 5)):
            with self.subTest(inicio=inicio, fin=fin):
                error = error_de(lambda: guarda(self.gerente, hora_inicio_luz=inicio, hora_fin_luz=fin, minutos_sin_actividad=9))
                self.assertEqual(list(error.error_dict), ["hora_fin_luz"])
                self.assertEqual(mensajes(error, "hora_fin_luz"), [MENSAJE_FIN])
                self.assertEqual((iot()["hora_inicio_luz"], iot()["hora_fin_luz"], iot()["minutos_sin_actividad"]), (8, 18, 5))
        self.assertEqual(auditorias(), [])

    def test_regla_4b_se_valida_contra_el_valor_guardado_cuando_solo_cambia_uno_de_los_dos(self):
        """Regla 4b con un solo valor en el pedido: subir el inicio por encima del fin guardado (18) o bajar el fin por debajo del inicio guardado (8) dan el error en `hora_fin_luz` («indica qué valor corregir»: el fin)."""
        error = error_de(lambda: guarda(self.gerente, hora_inicio_luz=19))
        self.assertEqual(mensajes(error, "hora_fin_luz"), [MENSAJE_FIN])
        error = error_de(lambda: guarda(self.gerente, hora_fin_luz=8))
        self.assertEqual(mensajes(error, "hora_fin_luz"), [MENSAJE_FIN])
        guarda(self.gerente, hora_inicio_luz=17)
        self.assertEqual(iot()["hora_inicio_luz"], 17)

    def test_regla_4b_si_el_valor_ya_tiene_otro_error_no_se_apila_el_de_4b(self):
        """Un fin fuera de dominio (25) da solo el error de dominio, no también el de 4b: un error por campo."""
        error = error_de(lambda: guarda(self.gerente, hora_fin_luz=25))
        self.assertEqual(mensajes(error, "hora_fin_luz"), [entero(1, 24)])

    # ---- todo o nada ----

    def test_regla_6_todo_o_nada_un_error_del_iot_y_otro_de_produccion_se_informan_juntos_y_no_se_guarda_nada(self):
        """Regla 6 de ADM-MOD-CFG: un error en un parámetro del IoT y otro de producción en el mismo envío vuelven juntos, cada uno en su campo, y no se guarda ninguno de los dos ni un tercero válido; sin auditoría."""
        error = error_de(
            lambda: guarda(self.gerente, histeresis_humedad=31, porc_merma_maxima=0, dias_limite_cotizacion=9, minutos_sin_actividad=12)
        )
        self.assertEqual(set(error.error_dict), {"histeresis_humedad", "porc_merma_maxima"})
        self.assertEqual(mensajes(error, "histeresis_humedad"), [entero(0, 30)])
        self.assertEqual((iot()["minutos_sin_actividad"], produccion()["dias_limite_cotizacion"]), (5, 3))
        self.assertEqual(auditorias(), [])

    def test_regla_6_un_parametro_desconocido_sigue_siendo_un_error_de_programacion(self):
        """MAE-04: un campo desconocido no es un dato de la persona: `TypeError` (también si viene junto con uno del IoT)."""
        with self.assertRaises(TypeError):
            guarda(self.gerente, hora_fin_luz=20, parametro_inexistente=1)
        self.assertEqual(iot()["hora_fin_luz"], 18)

    # ---- regla 5b ----

    def test_regla_5b_bajar_la_retencion_advierte_con_la_fecha_limite_y_deja_guardar(self):
        """Regla 5b: al reducir los días de retención (de 7 a 3), el resultado advierte «La próxima revisión periódica borrará las lecturas anteriores al 20/11/2026, salvo las que originaron una alerta o una
        regla.» (hoy 23/11 menos 3 días, con el reloj inyectado) y guarda."""
        resultado = guarda(self.gerente, dias_retencion_telemetria=3)
        self.assertIn(
            "La próxima revisión periódica borrará las lecturas anteriores al 20/11/2026, salvo las que originaron una alerta o una regla.", resultado.advertencias
        )
        self.assertEqual(iot()["dias_retencion_telemetria"], 3)

    def test_regla_5b_la_fecha_se_calcula_en_la_zona_local_con_el_reloj_inyectado(self):
        """Regla 5b y D-76 punto 6 («medianoche local»): a las 22:00 locales del 23/11 (que son las 01:00 UTC del 24/11), con 1 día de retención la fecha límite es el 22/11/2026, no la de UTC. El reloj es `ahora`, nunca
        la hora real."""
        tarde = datetime(2026, 11, 24, 1, 0, tzinfo=ZoneInfo("UTC"))
        resultado = configuracion.modificar_configuracion(self.gerente, ahora=tarde, dias_retencion_telemetria=1)
        self.assertIn("anteriores al 22/11/2026", " ".join(resultado.advertencias))

    def test_regla_5b_sin_advertencia_si_la_retencion_sube_o_no_cambia(self):
        """Regla 5b: solo se advierte cuando se REDUCE: subir (7 a 30), no cambiar (7 a 7) o no tocarla no advierten."""
        for kwargs in ({"dias_retencion_telemetria": 30}, {"dias_retencion_telemetria": 30}, {"minutos_sin_actividad": 9}):
            with self.subTest(kwargs=kwargs):
                resultado = guarda(self.gerente, **kwargs)
                self.assertFalse([a for a in resultado.advertencias if "revisión periódica" in a])
        ConfiguracionOperativa.objects.filter(singleton=1).update(dias_retencion_telemetria=7)
        self.assertFalse(guarda(self.gerente, dias_retencion_telemetria=7).advertencias)

    def test_regla_5b_se_compara_con_el_valor_releido_despues_de_bloquear_y_convive_con_la_regla_5(self):
        """Regla 5b y regla 5 de MAE-04: bajar la retención y dejar el horizonte menor que la pre-reserva traen las dos advertencias; ninguna bloquea."""
        resultado = guarda(self.gerente, dias_retencion_telemetria=2, dias_horizonte_cosecha=5, dias_pre_reserva_suministro=14, dias_anticipacion_cosecha_suministro=3)
        self.assertEqual(len(resultado.advertencias), 2)
        self.assertEqual((iot()["dias_retencion_telemetria"], produccion()["dias_horizonte_cosecha"]), (2, 5))

    def test_regla_5b_no_advierte_si_el_pedido_se_rechaza(self):
        """Un pedido rechazado (todo o nada) no devuelve resultado: ni advertencia ni cambio, aunque la retención bajara."""
        error_de(lambda: guarda(self.gerente, dias_retencion_telemetria=2, hora_fin_luz=99))
        self.assertEqual(iot()["dias_retencion_telemetria"], 7)

    # ---- auditoría ----

    def test_post_b_la_auditoria_trae_antes_y_despues_con_las_histeresis_como_texto(self):
        """Postcondición b y D-36 (un `Decimal` no es un valor permitido): `modificacion_configuracion` con el antes y el después de cada parámetro que cambió; las histéresis de temperatura, como texto («1.0» → «1.5»)."""
        guarda(self.gerente, hora_fin_luz=20, histeresis_temperatura="1,5", histeresis_temp_solucion=2, dias_retencion_telemetria=30)
        (registro,) = auditorias()
        self.assertEqual(set(registro.detalle), {"cambios"})
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "hora_fin_luz": {"antes": 18, "despues": 20},
                "histeresis_temperatura": {"antes": "1.0", "despues": "1.5"},
                "histeresis_temp_solucion": {"antes": "1.0", "despues": "2.0"},
                "dias_retencion_telemetria": {"antes": 7, "despues": 30},
            },
        )
        self.assertEqual(registro.afectados[0]["modelo"], "maestros.configuracionoperativa")

    def test_post_b_los_parametros_del_iot_junto_con_los_de_produccion_van_en_un_solo_registro(self):
        """«Mismo servicio, mismo bloqueo, misma auditoría»: un pedido con parámetros de los dos grupos deja UN registro con todos los cambios."""
        guarda(self.gerente, porc_merma_maxima=25, minutos_sin_actividad=9)
        (registro,) = auditorias()
        self.assertEqual(set(registro.detalle["cambios"]), {"porc_merma_maxima", "minutos_sin_actividad"})

    def test_d28_sin_cambios_no_se_escribe_ni_se_audita(self):
        """D-28: pedir los valores ya guardados (también una histéresis escrita distinto: «1,0», «1.00», 1) no escribe ni audita."""
        guarda(self.gerente, hora_fin_luz=18, histeresis_temperatura="1,0", histeresis_temp_solucion="1.0", cant_reintentos_comando="3")
        guarda(self.gerente, histeresis_temperatura=1)
        self.assertEqual(auditorias(), [])

    def test_etiquetas_cada_parametro_del_iot_tiene_su_nombre_visible_en_la_auditoria(self):
        """Patrón de auditoría (D-36): las claves de `cambios` salen con su nombre visible en la pantalla de «Auditoría», no crudas."""
        guarda(self.gerente, hora_fin_luz=20, histeresis_luz=2500)
        (registro,) = auditorias()
        filas = dict((campo, (antes, despues)) for campo, antes, despues in registro.filas_de_cambios())
        self.assertEqual(filas["Horario de luz: fin (h)"], ("18", "20"))
        self.assertIn("Histéresis de intensidad lumínica (lux)", filas)


class AdmModCfgIotVistaTests(ConDatosDeMaestros, TestCase):
    """La pantalla: el formulario aparte de los 14, los avisos y los errores marcados."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.login(username=self.gerente.email, password=CLAVE)

    def trece(self, **cambios):
        """Los 13 parámetros de producción guardados, como los manda el formulario de MAE-04 (texto)."""
        return {c: str(v) for c, v in produccion().items()} | {k: str(v) for k, v in cambios.items()}

    def todos(self, **cambios):
        """Los 13 y los 14 guardados, como los manda el formulario completo (con las histéresis con coma, como las muestra)."""
        valores = {c: str(v).replace(".", ",") for c, v in iot().items()}
        return self.trece() | valores | {k: str(v) for k, v in cambios.items()}

    # ---- (1) los 13 y el formulario aparte ----

    def test_regla_2b_el_formulario_de_produccion_sigue_con_trece_campos_y_el_del_iot_trae_los_catorce(self):
        """MAE-04 no cambia: `FormularioConfiguracion` conserva sus 13 campos (ninguno del IoT); los 14 van en el formulario aparte (`context["form_iot"]`), que la pantalla dibuja dentro del mismo `<form>`."""
        self.assertEqual(len(FormularioConfiguracion().fields), 13)
        self.assertFalse(set(FormularioConfiguracion().fields) & set(CAMPOS_IOT))
        respuesta = self.client.get(URL)
        self.assertEqual(list(respuesta.context["form_iot"].fields), CAMPOS_IOT)
        self.assertEqual(len(respuesta.context["form"].fields), 13)

    def test_regla_2b_un_post_con_solo_los_trece_no_modifica_ningun_parametro_del_iot(self):
        """El POST de MAE-04 (solo los 13) sigue funcionando y no toca los 14, aunque tengan valores distintos de los iniciales: la vista le pasa al servicio solo los campos IoT que vienen. Sin auditoría de ellos."""
        ConfiguracionOperativa.objects.filter(singleton=1).update(hora_fin_luz=20, histeresis_temperatura=Decimal("2.5"), dias_retencion_telemetria=30)
        antes = iot()
        respuesta = self.client.post(URL_PARAMETROS, self.trece(porc_merma_maxima=25))
        self.assertRedirects(respuesta, URL, fetch_redirect_response=False)
        self.assertEqual(iot(), antes)
        (registro,) = auditorias()
        self.assertEqual(set(registro.detalle["cambios"]), {"porc_merma_maxima"})

    def test_regla_2b_la_pantalla_muestra_la_seccion_modulo_iot_con_sus_cinco_grupos_y_los_catorce_campos(self):
        """Sección «Módulo IoT» al final, con los cinco subgrupos de `CFGP` en su orden y cada campo con su etiqueta y su ayuda (`configuracion.md`); con los valores guardados (las histéresis, con coma)."""
        ConfiguracionOperativa.objects.filter(singleton=1).update(histeresis_temperatura=Decimal("1.5"), hora_fin_luz=20)
        html = self.client.get(URL).content.decode()
        self.assertGreater(html.index("Módulo IoT"), html.index("Entregas"))
        posiciones = [html.index(grupo) for grupo, _ in GRUPOS_IOT]
        self.assertEqual(posiciones, sorted(posiciones))
        for _, campos in GRUPOS_IOT:
            for campo, etiqueta, ayuda in campos:
                self.assertIn(etiqueta, html)
                self.assertIn(ayuda.replace("'", "&#x27;"), html)
        formulario = self.client.get(URL).context["form_iot"]
        self.assertEqual((formulario["hora_fin_luz"].value(), formulario["histeresis_temperatura"].value()), (20, "1,5"))
        self.assertEqual(html.count('<form id="form-parametros"'), 1)
        self.assertNotIn('<form id="form-parametros"', html[html.index("Módulo IoT") :])

    # ---- guardado con los 14 ----

    def test_regla_3b_el_guardado_completo_con_coma_decimal_guarda_los_catorce(self):
        """Flujo principal: el formulario completo (13 + 14, las histéresis con coma) guarda el cambio del IoT y deja el registro de auditoría con su antes y su después."""
        respuesta = self.client.post(URL_PARAMETROS, self.todos(hora_fin_luz="20", histeresis_temperatura="1,5"))
        self.assertRedirects(respuesta, URL, fetch_redirect_response=False)
        self.assertEqual((iot()["hora_fin_luz"], iot()["histeresis_temperatura"]), (20, Decimal("1.5")))
        (registro,) = auditorias()
        self.assertEqual(registro.detalle["cambios"]["histeresis_temperatura"], {"antes": "1.0", "despues": "1.5"})

    def test_regla_3b_una_histeresis_con_dos_decimales_o_con_texto_da_error_de_campo_sin_500(self):
        """Regla 3b en la pantalla: «1,55» y «abc» vuelven con el error en el campo (el mensaje del decimal), con lo escrito, y no se guarda nada; con y sin HTMX."""
        for escrito in ("1,55", "abc", "", "1,5,5"):
            for extra in ({}, HTMX):
                with self.subTest(escrito=escrito, htmx=bool(extra)):
                    respuesta = self.client.post(URL_PARAMETROS, self.todos(histeresis_temperatura=escrito), **extra)
                    self.assertEqual(respuesta.status_code, 200)
                    formulario = respuesta.context["form_iot"]
                    self.assertEqual(formulario.errors["histeresis_temperatura"], [MENSAJE_DECIMAL])
                    self.assertEqual(formulario["histeresis_temperatura"].value(), escrito)
                    self.assertContains(respuesta, MENSAJE_DECIMAL)
        self.assertEqual(iot()["histeresis_temperatura"], Decimal("1.0"))
        self.assertEqual(auditorias(), [])

    def test_regla_4b_el_fin_igual_al_inicio_marca_hora_fin_luz_y_no_guarda(self):
        """Regla 4b: «Poner el fin del horario de luz igual al inicio: error en el campo»: el error sale en `hora_fin_luz` con «El fin tiene que ser posterior al inicio.» y no se guarda nada (tampoco la producción)."""
        respuesta = self.client.post(URL_PARAMETROS, self.todos(hora_inicio_luz="8", hora_fin_luz="8", porc_merma_maxima="20"))
        self.assertEqual(respuesta.context["form_iot"].errors["hora_fin_luz"], [MENSAJE_FIN])
        self.assertContains(respuesta, MENSAJE_FIN)
        self.assertEqual((iot()["hora_fin_luz"], produccion()["porc_merma_maxima"]), (18, 15))

    def test_regla_6_un_error_del_iot_y_otro_de_produccion_se_marcan_los_dos_campos_y_no_se_guarda_nada(self):
        """Todo o nada en la pantalla: un error en un parámetro del IoT (`histeresis_humedad` 31) y otro de producción (`porc_merma_maxima` 101) en el mismo envío vuelven con los dos campos marcados, cada uno en su formulario
        y con lo escrito; no se guarda ninguno y se ve el aviso general de MAE-04."""
        for extra in ({}, HTMX):
            with self.subTest(htmx=bool(extra)):
                respuesta = self.client.post(URL_PARAMETROS, self.todos(histeresis_humedad="31", porc_merma_maxima="101", minutos_sin_actividad="9"), **extra)
                self.assertEqual(respuesta.context["form_iot"].errors["histeresis_humedad"], [entero(0, 30)])
                self.assertIn("porc_merma_maxima", respuesta.context["form"].errors)
                self.assertEqual(respuesta.context["form_iot"]["minutos_sin_actividad"].value(), "9")
                self.assertContains(respuesta, "no se guardó ningún cambio")
        self.assertEqual((iot()["minutos_sin_actividad"], produccion()["porc_merma_maxima"]), (5, 15))

    # ---- (9) los avisos al guardar ----

    def test_regla_7b_si_cambio_un_parametro_del_iot_el_aviso_dice_que_rige_desde_el_proximo_intento(self):
        """Aviso al guardar (el del prototipo): «Parámetros guardados. Rigen desde el próximo intento y la próxima lectura.» si cambió alguno del IoT; también si además cambió uno de producción, y no se muestra el de MAE-04."""
        for cambios in ({"hora_fin_luz": "20"}, {"hora_fin_luz": "20", "porc_merma_maxima": "20"}, {"histeresis_temperatura": "1,5"}):
            with self.subTest(cambios=cambios):
                ConfiguracionOperativa.objects.filter(singleton=1).update(hora_fin_luz=18, histeresis_temperatura=Decimal("1.0"), porc_merma_maxima=15)
                respuesta = self.client.post(URL_PARAMETROS, self.todos(**cambios), follow=True)
                self.assertContains(respuesta, AVISO_IOT)
                self.assertNotContains(respuesta, AVISO_MAE_04)

    def test_regla_7b_si_cambio_solo_produccion_o_nada_el_aviso_es_el_de_mae_04(self):
        """Si cambió solo un parámetro de producción, o ninguno, el aviso es el de MAE-04 («Se guardó la configuración.») y nunca el del IoT."""
        for cambios in ({"porc_merma_maxima": "20"}, {}):
            with self.subTest(cambios=cambios):
                ConfiguracionOperativa.objects.filter(singleton=1).update(porc_merma_maxima=15)
                respuesta = self.client.post(URL_PARAMETROS, self.todos(**cambios), follow=True)
                self.assertContains(respuesta, AVISO_MAE_04)
                self.assertNotContains(respuesta, AVISO_IOT)

    def test_regla_7b_con_htmx_el_aviso_del_iot_llega_tras_la_recarga(self):
        """Con HTMX, guardar responde `HX-Redirect` a la pantalla y el aviso llega al recargar (como en MAE-04)."""
        respuesta = self.client.post(URL_PARAMETROS, self.todos(hora_fin_luz="20"), **HTMX)
        self.assertEqual((respuesta.status_code, respuesta["HX-Redirect"]), (204, URL))
        self.assertContains(self.client.get(URL), AVISO_IOT)

    # ---- regla 5b en la pantalla ----

    def test_regla_5b_bajar_la_retencion_muestra_la_advertencia_al_guardar_y_subirla_no(self):
        """Regla 5b: «Bajar la retención a 1: la advertencia, y guarda.» Tras guardar, junto al aviso, se muestra «La próxima revisión periódica borrará las lecturas anteriores al …» (la fecha, con la hora actual);
        al subirla no aparece. (La fecha exacta con reloj inyectado se prueba en el servicio.)"""
        respuesta = self.client.post(URL_PARAMETROS, self.todos(dias_retencion_telemetria="1"), follow=True)
        self.assertContains(respuesta, "La próxima revisión periódica borrará las lecturas anteriores al ")
        self.assertContains(respuesta, "salvo las que originaron una alerta o una regla.")
        self.assertEqual(iot()["dias_retencion_telemetria"], 1)
        respuesta = self.client.post(URL_PARAMETROS, self.todos(dias_retencion_telemetria="30"), follow=True)
        self.assertNotContains(respuesta, "La próxima revisión periódica borrará")

    def test_regla_5b_la_advertencia_se_muestra_con_el_mismo_estilo_de_advertencia_que_la_de_la_regla_5_y_una_sola_vez(self):
        """Regla 5b («se muestra como la de la regla 5 (no bloquea)»): tras guardar con la retención bajada, la pantalla muestra «La próxima revisión periódica borrará las lecturas anteriores al … salvo las que
        originaron una alerta o una regla.» en un `<div class="alert alert-warn">`, el mismo estilo que usa la advertencia de la regla 5 de MAE-04 (y no el aviso verde de éxito de `core`); se ve una sola vez
        (con y sin HTMX), no se guarda como mensaje de `django.contrib.messages` y al subir la retención no aparece."""
        for extra in ({}, HTMX):
            with self.subTest(htmx=bool(extra)):
                ConfiguracionOperativa.objects.filter(singleton=1).update(dias_retencion_telemetria=7)
                self.client.post(URL_PARAMETROS, self.todos(dias_retencion_telemetria="1"), **extra)
                pantalla = self.client.get(URL)
                html = pantalla.content.decode()
                advertencia = re.search(r'<div class="alert alert-warn"[^>]*>(?:(?!</div>).)*?<div>(La próxima revisión periódica borrará las lecturas anteriores al \d\d/\d\d/\d{4}, salvo las que originaron una alerta o una regla\.)</div>', html, re.S)
                self.assertIsNotNone(advertencia, "la advertencia 5b no se renderiza con la clase alert-warn")
                self.assertNotRegex(html, r'<div class="alert alert-ok"[^>]*>(?:(?!</div>).)*?La próxima revisión periódica')
                self.assertNotContains(self.client.get(URL), "La próxima revisión periódica borrará")  # una sola vez
        self.client.post(URL_PARAMETROS, self.todos(dias_retencion_telemetria="30"))
        self.assertNotContains(self.client.get(URL), "La próxima revisión periódica borrará")

    def test_regla_5b_la_advertencia_de_la_retencion_no_viaja_como_mensaje_de_core(self):
        """`core` dibuja todo mensaje que no sea de error con el estilo de éxito: la advertencia 5b no puede ir por `django.contrib.messages` (no se toca `core`): se guarda en la sesión y la pantalla de
        configuración la muestra con su propia plantilla. Tras guardar, los mensajes pendientes son solo el aviso de guardado."""
        respuesta = self.client.post(URL_PARAMETROS, self.todos(dias_retencion_telemetria="1"))
        from django.contrib.messages import get_messages

        textos = [str(m) for m in get_messages(respuesta.wsgi_request)]
        self.assertEqual(textos, [AVISO_IOT])

    # ---- (8) permisos ----

    def test_pre_a_el_agronomo_recibe_403_en_la_pantalla_y_en_el_guardado_y_el_gerente_entra(self):
        """ADM-MOD-CFG precondición a (D-76 punto 9): la pantalla de configuración es del Gerente; el Agrónomo, 403 en la pantalla y en el guardado con parámetros del IoT, sin cambiar nada; el Gerente entra (200)."""
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.client.logout()
        agronomo = crear_agronomo()
        self.client.login(username=agronomo.email, password=CLAVE)
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.client.post(URL_PARAMETROS, self.todos(hora_fin_luz="20")).status_code, 403)
        self.assertEqual(iot()["hora_fin_luz"], 18)
        self.assertEqual(auditorias(), [])


@tag("concurrencia")
class AdmModCfgIotConcurrenciaTests(ConDatosDeMaestros, TransactionTestCase):
    """Dos guardados a la vez (D-76 punto 10 y patrón de singletons): bloqueo de la fila única (`FOR NO KEY UPDATE`), releída después de bloquear; el segundo calcula su «antes» contra lo ya guardado."""

    def setUp(self):
        asegurar_datos_de_maestros()  # el flush de la prueba anterior vació las filas únicas
        self.gerente = crear_gerente()

    def test_dos_guardados_de_parametros_distintos_no_pierden_ninguno_ni_dan_500(self):
        """Uno cambia un parámetro del IoT y el otro uno de producción: los dos quedan guardados, con su propio registro, sin error."""
        resultados = correr_a_la_vez(
            lambda: configuracion.modificar_configuracion(self.gerente, hora_fin_luz=20),
            lambda: configuracion.modificar_configuracion(self.gerente, porc_merma_maxima=25),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual((iot()["hora_fin_luz"], produccion()["porc_merma_maxima"]), (20, 25))
        self.assertEqual(len(auditorias()), 2)

    def test_dos_guardados_del_mismo_parametro_gana_el_ultimo_y_audita_contra_lo_releido(self):
        """Dos cambios de la misma histéresis a la vez: gana el último y el «antes» del segundo es el «después» del primero (las histéresis, como texto); nunca un 500."""
        resultados = correr_a_la_vez(
            lambda: configuracion.modificar_configuracion(self.gerente, histeresis_temperatura="1,5"),
            lambda: configuracion.modificar_configuracion(self.gerente, histeresis_temperatura="2,5"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(iot()["histeresis_temperatura"], Decimal("2.5"))
        self.assertEqual(
            [r.detalle["cambios"]["histeresis_temperatura"] for r in auditorias()],
            [{"antes": "1.0", "despues": "1.5"}, {"antes": "1.5", "despues": "2.5"}],
        )

    def test_regla_4b_se_valida_contra_la_fila_releida_despues_de_bloquear(self):
        """Regla 4b con concurrencia: el primero sube el inicio de la luz a 17; el segundo baja el fin a 12 (válido contra el inicio 8 que veía antes). Releída la fila, el fin queda por debajo del inicio y se rechaza sin tocar nada."""
        resultados = correr_a_la_vez(
            lambda: configuracion.modificar_configuracion(self.gerente, hora_inicio_luz=17),
            lambda: configuracion.modificar_configuracion(self.gerente, hora_fin_luz=12),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual((iot()["hora_inicio_luz"], iot()["hora_fin_luz"]), (17, 18))
