# Pruebas de IOT-ENT-INF, extensión *b, pasos 4 a 6: resúmenes horarios, fotoperíodo y retención (IOT-04; docs/casos_de_uso/iot/entregar_informacion.md, «La revisión
# periódica»; D-71 y D-76, puntos 4 a 6). Se escribieron ANTES que el servicio (`.claude/rules/pruebas.md`). Los pasos 1 a 3 están en `test_revision_iot.py`.
#
# Servicio que se prueba: iot/servicios/revision.py, `revisar(ahora) -> ResumenDeRevision` (ver el encabezado de `test_revision_iot.py`).
#
# Ninguna prueba depende de la hora del día: ``revisar`` recibe ``ahora``. La zona del proyecto es Argentina (UTC-3, sin horario de verano), así que las horas
# locales se arman con ``ZoneInfo`` y los días se cuentan en esa zona. Valores iniciales de la Configuración Operativa: horario de luz de 8 a 18 h, umbral de luz de
# 1.000 lux, 5 minutos sin actividad y 7 días de retención.

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso, variedad_con_semilla, variedades_presentes_de_prueba
from iot.models import AlertaIot, FotoperiodoDiario, ResumenHorario, Telemetria
from iot.tests import fabricas
from maestros.models import Alerta, ConfiguracionOperativa
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_sector

revision = perezoso("iot.servicios.revision")
alertas_iot = perezoso("iot.servicios.alertas_iot")

LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")
ACCION = "revision_periodica_iot"


def local(dia, hora=0, minuto=0):
    """Una hora local de noviembre de 2026."""
    return datetime(2026, 11, dia, hora, minuto, tzinfo=LOCAL)


AHORA = local(23, 12)  # lunes, mediodía: hoy es el 23/11 y ayer, el 22/11


def lecturas_por_minuto(sensor, desde, hasta, valor):
    """Una lectura válida por minuto, de ``desde`` (inclusive) a ``hasta`` (exclusive). ``valor`` es un número o una función de la hora local. Se crean con
    ``bulk_create``: un día entero son 1.440 lecturas."""
    lecturas, momento = [], desde
    while momento < hasta:
        v = valor(momento) if callable(valor) else valor
        lecturas.append(
            Telemetria(
                sensor=sensor, medida_en=momento, valor_medido=Decimal(str(v)), valida=True, unidad_medida_telemetria=sensor.unidad_medida
            )
        )
        momento += timedelta(minutes=1)
    Telemetria.objects.bulk_create(lecturas)


def dia_de_luz(sensor, dia, desde=8, hasta=18):
    """Un día entero (de 0 a 24 h) con una lectura por minuto: 5.000 lux entre ``desde`` y ``hasta`` y 100 lux el resto (10 horas de luz por omisión)."""
    lecturas_por_minuto(sensor, local(dia), local(dia + 1), lambda m: 5000 if desde <= m.hour < hasta else 100)


class _Base(fabricas.ConCatalogoIot, TestCase):
    """Un invernadero «Norte» con su sistema activo y un sensor de temperatura; las ayudas que usan las tres clases."""

    def setUp(self):
        cache.clear()
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.temp = fabricas.sensor(self.sistema, "norte/sectorA/temperatura")

    def lectura(self, sensor, momento, valor="20", **extra):
        return fabricas.telemetria(sensor, valor, medida_en=momento, **extra)

    def resumen_de(self, sensor, momento):
        return ResumenHorario.objects.get(sensor=sensor, hora=momento)

    def revisar(self, ahora=AHORA):
        """Corre la revisión y devuelve el resumen del único sistema."""
        return revision.revisar(ahora).sistemas[0]


# ---------------------------------------------------------------------------------------------------------------------------------------------------
# *b.4 · resúmenes horarios (D-76, punto 4)
# ---------------------------------------------------------------------------------------------------------------------------------------------------


class RevisionResumenesServicioTests(_Base):
    """`revisar`, paso 4: por sensor y por hora, mínimo, promedio y máximo de las lecturas válidas, y las cantidades."""

    def test_regla_resumenes_la_hora_en_curso_se_calcula_con_minimo_promedio_y_maximo(self):
        """Extensión *b.4, regla «Resúmenes horarios» y postcondición v: el resumen de la hora en curso (12:00) guarda mínimo, promedio y máximo, la cantidad de lecturas y la
        de inválidas."""
        self.lectura(self.temp, local(23, 12, 10), "20")
        self.lectura(self.temp, local(23, 12, 20), "30")
        resumen = self.revisar()
        fila = self.resumen_de(self.temp, local(23, 12))
        self.assertEqual((fila.minimo, fila.promedio, fila.maximo), (Decimal("20"), Decimal("25"), Decimal("30")))
        self.assertEqual((fila.cantidad_lecturas, fila.cantidad_invalidas), (2, 0))
        self.assertEqual(resumen.resumenes, 1)

    def test_regla_resumenes_solo_las_validas_entran_en_el_minimo_el_promedio_y_el_maximo(self):
        """Regla «Resúmenes horarios»: mínimo, promedio y máximo son de las lecturas VÁLIDAS; las inválidas se cuentan aparte, y la cantidad de lecturas es la de todas."""
        self.lectura(self.temp, local(23, 12, 10), "20")
        self.lectura(self.temp, local(23, 12, 20), "30")
        self.lectura(self.temp, local(23, 12, 30), "999", valida=False)
        self.revisar()
        fila = self.resumen_de(self.temp, local(23, 12))
        self.assertEqual((fila.minimo, fila.promedio, fila.maximo), (Decimal("20"), Decimal("25"), Decimal("30")))
        self.assertEqual((fila.cantidad_lecturas, fila.cantidad_invalidas), (3, 1))

    def test_regla_resumenes_una_hora_solo_con_invalidas_deja_los_tres_valores_nulos(self):
        """D-76 punto 4: «nulos si no hubo» lecturas válidas; la hora igual se resume, con sus cantidades."""
        self.lectura(self.temp, local(23, 12, 10), "999", valida=False)
        self.revisar()
        fila = self.resumen_de(self.temp, local(23, 12))
        self.assertEqual((fila.minimo, fila.promedio, fila.maximo), (None, None, None))
        self.assertEqual((fila.cantidad_lecturas, fila.cantidad_invalidas), (1, 1))

    def test_regla_resumenes_recalcula_la_hora_en_curso_y_las_dos_anteriores(self):
        """D-76 punto 4: la cola del nodo guarda hasta 1 hora, así que se recalcula SIEMPRE la hora en curso y las dos anteriores (12, 11 y 10), aunque ya tengan resumen."""
        for hora in (12, 11, 10):
            self.lectura(self.temp, local(23, hora, 10), "24")
            ResumenHorario.objects.create(
                sensor=self.temp, hora=local(23, hora), minimo=Decimal("1"), promedio=Decimal("1"), maximo=Decimal("1"), cantidad_lecturas=99
            )
        resumen = self.revisar()
        for hora in (12, 11, 10):
            fila = self.resumen_de(self.temp, local(23, hora))
            self.assertEqual((fila.minimo, fila.maximo, fila.cantidad_lecturas), (Decimal("24"), Decimal("24"), 1), f"hora {hora}")
        self.assertEqual(resumen.resumenes, 3)

    def test_regla_resumenes_una_hora_vieja_con_resumen_no_se_toca(self):
        """D-76 punto 4: fuera de las tres últimas horas, solo se calcula la que NO tiene resumen; una que ya lo tiene queda como estaba."""
        self.lectura(self.temp, local(23, 9, 10), "24")
        ResumenHorario.objects.create(
            sensor=self.temp, hora=local(23, 9), minimo=Decimal("1"), promedio=Decimal("1"), maximo=Decimal("1"), cantidad_lecturas=99
        )
        self.revisar()
        fila = self.resumen_de(self.temp, local(23, 9))
        self.assertEqual((fila.minimo, fila.cantidad_lecturas), (Decimal("1"), 99))

    def test_regla_resumenes_una_hora_vieja_sin_resumen_se_calcula(self):
        """D-76 punto 4: «toda hora con lecturas que todavía no tenga resumen» se calcula: así la revisión se pone al día si no corrió y nada se borra sin resumir."""
        self.lectura(self.temp, local(23, 8, 10), "26")
        self.lectura(self.temp, local(20, 15, 40), "22")
        self.revisar()
        self.assertEqual(self.resumen_de(self.temp, local(23, 8)).cantidad_lecturas, 1)
        self.assertEqual(self.resumen_de(self.temp, local(20, 15)).minimo, Decimal("22"))

    def test_regla_resumenes_el_nivel_de_la_solucion_no_tiene_resumen(self):
        """Extensión *b.4 («salvo los de nivel de la solución») y `docs/modelo/iot.md`: «No hay resúmenes del nivel»."""
        nivel = fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        self.lectura(nivel, local(23, 12, 10))
        self.revisar()
        self.assertFalse(ResumenHorario.objects.filter(sensor=nivel).exists())

    def test_regla_resumenes_un_sensor_dado_de_baja_no_se_resume_y_uno_fuera_de_servicio_si(self):
        """Extensión *b.4 y D-76: «cada sensor no dado de baja»: el dado de baja queda afuera; el fuera de servicio, que sigue guardando lecturas, se resume."""
        baja = fabricas.sensor(self.sistema, "norte/baja", estado="inactivo")
        fuera = fabricas.sensor(self.sistema, "norte/fuera", estado="fuera_de_servicio")
        for sensor in (baja, fuera):
            self.lectura(sensor, local(23, 12, 10))
        self.revisar()
        self.assertFalse(ResumenHorario.objects.filter(sensor=baja).exists())
        self.assertTrue(ResumenHorario.objects.filter(sensor=fuera).exists())

    def test_regla_zona_una_lectura_de_las_22_locales_cae_en_la_hora_de_resumen_local(self):
        """D-76 punto 4 («las horas se cuentan en la zona del proyecto»): lecturas a las 22:00 y 22:30 locales del 22/11 (01:00 y 01:30 UTC del 23/11) se resumen en la hora
        local de las 22:00 del 22/11."""
        self.lectura(self.temp, local(22, 22, 0), "20")
        self.lectura(self.temp, local(22, 22, 30), "30")
        self.revisar()
        fila = self.resumen_de(self.temp, local(22, 22))
        self.assertEqual((fila.cantidad_lecturas, fila.promedio), (2, Decimal("25")))
        self.assertEqual(ResumenHorario.objects.count(), 1)

    def test_regla_resumenes_la_segunda_corrida_con_el_mismo_ahora_no_cambia_nada(self):
        """Regla común (idempotencia) y D-76 punto 4 (`update_or_create`): correrla dos veces no duplica resúmenes ni cuenta como cambiado lo que quedó igual."""
        self.lectura(self.temp, local(23, 12, 10), "20")
        self.lectura(self.temp, local(23, 8, 10), "26")
        primera = self.revisar()
        filas = ResumenHorario.objects.count()
        segunda = self.revisar()
        self.assertEqual((primera.resumenes, segunda.resumenes), (2, 0))
        self.assertEqual(ResumenHorario.objects.count(), filas)

    def test_regla_resumenes_las_lecturas_se_leen_con_una_agregacion_y_no_con_una_consulta_por_hora(self):
        """D-76 punto 4 / «La revisión periódica»: «las consultas son una agregación por sensor y hora (`TruncHour`), nunca una por hora»: resumir 6 horas pendientes consulta
        `iot_telemetria` la misma cantidad de veces que resumir una."""

        def lecturas_leidas(contexto):
            return [q for q in contexto.captured_queries if q["sql"].startswith("SELECT") and "iot_telemetria" in q["sql"]]

        self.lectura(self.temp, local(23, 12, 10))
        with CaptureQueriesContext(connection) as con_una_hora:
            self.revisar()
        for hora in range(4, 10):
            self.lectura(self.temp, local(23, hora, 10))
        with CaptureQueriesContext(connection) as con_seis_horas:
            self.revisar()
        self.assertEqual(len(lecturas_leidas(con_seis_horas)), len(lecturas_leidas(con_una_hora)))
        self.assertEqual(ResumenHorario.objects.filter(sensor=self.temp).count(), 7)


# ---------------------------------------------------------------------------------------------------------------------------------------------------
# *b.5 · fotoperíodo (D-76, punto 5)
# ---------------------------------------------------------------------------------------------------------------------------------------------------


class RevisionFotoperiodoServicioTests(_Base):
    """`revisar`, paso 5: el fotoperíodo de cada día cerrado de cada sensor de intensidad lumínica, con su comparación contra el rango del umbral efectivo (sin histéresis)."""

    def setUp(self):
        super().setUp()
        self.luz = fabricas.sensor(
            self.sistema, "norte/sectorA/luz", "intensidad_luz", valor_calibracion_min=0, valor_calibracion_max=100000
        )

    def con_umbral(self, minimo, maximo):
        """El invernadero tiene umbral efectivo con un fotoperíodo de ``minimo`` a ``maximo`` horas."""
        variedad = variedad_con_semilla(nombre="Crespa", fotoperiodo_min=str(minimo), fotoperiodo_max=str(maximo))
        self.enterContext(variedades_presentes_de_prueba({self.norte.pk: {variedad.pk}}))

    def fotoperiodo(self, dia, sensor=None):
        return FotoperiodoDiario.objects.get(sensor=sensor or self.luz, fecha=date(2026, 11, dia))

    def alertas_de_fotoperiodo(self, estado="activa"):
        return Alerta.objects.filter(tipo_alerta="iot_fotoperiodo_fuera_de_umbral", estado_alerta=estado)

    def alerta_activa_del_sensor(self):
        """Una alerta de fotoperíodo ya activa del sensor de luz (de una corrida anterior)."""
        return alertas_iot.asegurar_alerta_iot(
            self.norte.pk, self.sistema, "iot_fotoperiodo_fuera_de_umbral", f"sensor:{self.luz.pk}", "norte/sectorA/luz · vieja", hardware=self.luz
        ).alerta

    # ---- el cálculo ----

    def test_regla_fotoperiodo_un_dia_con_luz_de_8_a_18_y_una_lectura_por_minuto_da_10_horas(self):
        """D-76 punto 5 y regla «Fotoperíodo»: se suma el tiempo entre lecturas válidas consecutivas que superan el umbral de luz (1.000 lux): 8 a 18 h da 10,00 h, completo."""
        dia_de_luz(self.luz, 22)
        resumen = self.revisar()
        fila = self.fotoperiodo(22)
        self.assertEqual((fila.horas, fila.incompleto), (Decimal("10.00"), False))
        self.assertEqual(resumen.fotoperiodos, 1)

    def test_regla_fotoperiodo_una_lectura_invalida_no_suma_luz(self):
        """D-76 punto 5: «se toman las lecturas válidas del día»: una lectura inválida no cuenta aunque su valor supere el umbral. Día oscuro (100 lux) con una única lectura
        de 5.000 lux a las 12:00 marcada inválida: da 0,00 h y el día sigue completo (el par 11:59-12:01 son 2 minutos, dentro del plazo). Si la contara, daría 0,02 h."""
        lecturas_por_minuto(self.luz, local(22), local(23), 100)
        Telemetria.objects.filter(sensor=self.luz, medida_en=local(22, 12)).update(valor_medido=Decimal("5000"), valida=False)
        self.revisar()
        fila = self.fotoperiodo(22)
        self.assertEqual((fila.horas, fila.incompleto), (Decimal("0.00"), False))

    def test_regla_fotoperiodo_un_hueco_mayor_que_los_minutos_sin_actividad_lo_marca_incompleto_y_no_compara(self):
        """D-76 punto 5: dos lecturas seguidas más separadas que los minutos sin actividad (5) marcan el día `incompleto` y no se compara, aunque con ese día completo
        (10 h contra un mínimo de 12 h) sí habría alerta. El fotoperíodo se guarda igual."""
        self.con_umbral(12, 16)
        lecturas_por_minuto(self.luz, local(22), local(22, 12), lambda m: 5000 if m.hour >= 8 else 100)
        lecturas_por_minuto(self.luz, local(22, 12, 30), local(23), lambda m: 5000 if m.hour < 18 else 100)
        self.revisar()
        self.assertTrue(self.fotoperiodo(22).incompleto)
        self.assertFalse(Alerta.objects.filter(tipo_alerta="iot_fotoperiodo_fuera_de_umbral").exists())

    def test_regla_fotoperiodo_si_la_primera_o_la_ultima_lectura_esta_lejos_del_borde_del_dia_es_incompleto(self):
        """D-76 punto 5: también es incompleto si «la primera llega más tarde o la última más temprano que ese plazo desde el borde del día»."""
        lecturas_por_minuto(self.luz, local(20, 2), local(21), 100)  # 20/11: la primera llega a las 2:00
        lecturas_por_minuto(self.luz, local(21), local(21, 22), 100)  # 21/11: la última es de las 21:59
        self.revisar()
        self.assertTrue(self.fotoperiodo(20).incompleto)
        self.assertTrue(self.fotoperiodo(21).incompleto)

    def test_regla_fotoperiodo_justo_en_el_plazo_del_borde_el_dia_es_completo_y_un_minuto_mas_no(self):
        """D-76 punto 5, bordes: la primera lectura a los 5 minutos de la medianoche y la última a los 5 minutos del fin del día (23:55) están justo en el plazo: completo.
        Con la primera a los 6 minutos, incompleto."""
        lecturas_por_minuto(self.luz, local(21, 0, 5), local(21, 23, 56), 100)
        lecturas_por_minuto(self.luz, local(20, 0, 6), local(21), 100)
        self.revisar()
        self.assertFalse(self.fotoperiodo(21).incompleto)
        self.assertTrue(self.fotoperiodo(20).incompleto)

    def test_regla_fotoperiodo_un_dia_sin_lecturas_no_se_calcula(self):
        """D-76 punto 5: se calculan los «días con lecturas»; sin lecturas no hay `FotoperiodoDiario` (el sensor no informó ese día)."""
        resumen = self.revisar()
        self.assertFalse(FotoperiodoDiario.objects.exists())
        self.assertEqual(resumen.fotoperiodos, 0)

    def test_regla_fotoperiodo_solo_se_calcula_para_los_sensores_de_luz_no_dados_de_baja(self):
        """Extensión *b.5 y D-76: «cada sensor de intensidad lumínica no dado de baja»: ni un sensor de temperatura ni uno de luz dado de baja tienen fotoperíodo."""
        baja = fabricas.sensor(self.sistema, "norte/luz-baja", "intensidad_luz", estado="inactivo", valor_calibracion_min=0, valor_calibracion_max=100000)
        dia_de_luz(self.temp, 22)
        dia_de_luz(baja, 22)
        self.revisar()
        self.assertFalse(FotoperiodoDiario.objects.exists())

    # ---- cuándo se calcula un día ----

    def test_regla_fotoperiodo_el_dia_de_hoy_nunca_se_calcula(self):
        """D-76 punto 5 y paso 9 de la verificación a mano: «nunca el día en curso». Ni siquiera a las 23:59 de ese día."""
        lecturas_por_minuto(self.luz, local(23), local(23, 23, 59), 5000)
        self.revisar(local(23, 23, 59))
        self.assertFalse(FotoperiodoDiario.objects.filter(fecha=date(2026, 11, 23)).exists())

    def test_regla_fotoperiodo_el_de_ayer_recien_se_calcula_a_la_1_de_la_manana(self):
        """D-76 punto 5: un día D se calcula en la primera revisión con `ahora ≥ D+1 a la 01:00` (una hora de margen para la cola del nodo). A las 00:59 no; a la 01:00, sí."""
        dia_de_luz(self.luz, 23)
        self.revisar(local(24, 0, 59))
        self.assertFalse(FotoperiodoDiario.objects.filter(fecha=date(2026, 11, 23)).exists())
        self.revisar(local(24, 1, 0))
        self.assertEqual(self.fotoperiodo(23).horas, Decimal("10.00"))

    def test_regla_fotoperiodo_calcula_todos_los_dias_que_faltan_y_no_toca_los_ya_calculados(self):
        """D-76 punto 5: se calculan «todos los días con lecturas que no tienen `FotoperiodoDiario`», en orden de fecha; el que ya lo tiene queda como estaba."""
        for dia in (20, 21, 22):
            dia_de_luz(self.luz, dia)
        FotoperiodoDiario.objects.create(sensor=self.luz, fecha=date(2026, 11, 22), horas=Decimal("3.00"), incompleto=True)
        resumen = self.revisar()
        self.assertEqual((self.fotoperiodo(20).horas, self.fotoperiodo(21).horas), (Decimal("10.00"), Decimal("10.00")))
        self.assertEqual((self.fotoperiodo(22).horas, self.fotoperiodo(22).incompleto), (Decimal("3.00"), True))
        self.assertEqual(resumen.fotoperiodos, 2)

    def test_regla_zona_las_lecturas_de_las_22_locales_cuentan_en_el_dia_local(self):
        """D-76 punto 5 («en la zona horaria del invernadero»): un día local entero incluye las lecturas de las 22:00 a las 24:00 locales (que son del día siguiente en UTC).
        El único fotoperíodo es el del 22/11, con 10,00 h y completo."""
        dia_de_luz(self.luz, 22)
        self.revisar()
        self.assertEqual(list(FotoperiodoDiario.objects.values_list("fecha", flat=True)), [date(2026, 11, 22)])
        fila = self.fotoperiodo(22)
        self.assertEqual((fila.horas, fila.incompleto), (Decimal("10.00"), False))

    def test_regla_fotoperiodo_un_sensor_de_luz_fuera_de_servicio_no_genera_alerta(self):
        """D-76 punto 5 («el sensor está activo»): con el sensor de luz fuera de servicio se calcula y guarda el fotoperíodo (10 h, fuera de un mínimo de 12 h) pero no se genera
        la alerta."""
        self.con_umbral(12, 16)
        fuera = fabricas.sensor(
            self.sistema, "norte/fuera/luz", "intensidad_luz", estado="fuera_de_servicio", valor_calibracion_min=0, valor_calibracion_max=100000
        )
        dia_de_luz(fuera, 22)
        self.revisar()
        self.assertEqual(self.fotoperiodo(22, fuera).horas, Decimal("10.00"))
        self.assertFalse(self.alertas_de_fotoperiodo().exists())

    def test_regla_fotoperiodo_un_sensor_de_luz_fuera_de_servicio_no_resuelve_su_alerta(self):
        """D-76 punto 5: tampoco resuelve. Con la alerta activa, el fotoperíodo dentro del rango (10 h en 8 a 14) y el sensor fuera de servicio, la alerta sigue activa."""
        self.con_umbral(8, 14)
        fuera = fabricas.sensor(
            self.sistema, "norte/fuera/luz", "intensidad_luz", estado="fuera_de_servicio", valor_calibracion_min=0, valor_calibracion_max=100000
        )
        alerta = alertas_iot.asegurar_alerta_iot(
            self.norte.pk, self.sistema, "iot_fotoperiodo_fuera_de_umbral", f"sensor:{fuera.pk}", "vieja", hardware=fuera
        ).alerta
        dia_de_luz(fuera, 22)
        self.revisar()
        alerta.refresh_from_db()
        self.assertEqual(self.fotoperiodo(22, fuera).horas, Decimal("10.00"))
        self.assertEqual(alerta.estado_alerta, "activa")

    def con_fotoperiodo_vacio(self):
        """Dos variedades presentes cuyos fotoperíodos (8 a 10 h y 12 a 14 h) no se superponen: el umbral efectivo existe (temperatura, humedad y luz se superponen) pero su
        fotoperíodo es ``None``."""
        crespa = variedad_con_semilla(nombre="Crespa", fotoperiodo_min="8", fotoperiodo_max="10")
        lisa = variedad_con_semilla(nombre="Lisa", fotoperiodo_min="12", fotoperiodo_max="14")
        self.enterContext(variedades_presentes_de_prueba({self.norte.pk: {crespa.pk, lisa.pk}}))

    def test_regla_fotoperiodo_con_el_fotoperiodo_del_umbral_vacio_no_genera_alerta(self):
        """D-76 punto 5 («umbral efectivo con fotoperíodo no vacío»): sin fotoperíodo efectivo no se compara; el de 10 h se guarda y no hay alerta."""
        self.con_fotoperiodo_vacio()
        dia_de_luz(self.luz, 22)
        self.revisar()
        self.assertEqual(self.fotoperiodo(22).horas, Decimal("10.00"))
        self.assertFalse(self.alertas_de_fotoperiodo().exists())

    def test_regla_fotoperiodo_con_el_fotoperiodo_del_umbral_vacio_no_toca_una_alerta_activa(self):
        """D-76 punto 5 y «un día incompleto o sin umbral no toca la alerta»: la alerta activa sigue activa y no se crea otra."""
        self.con_fotoperiodo_vacio()
        alerta = self.alerta_activa_del_sensor()
        dia_de_luz(self.luz, 22)
        self.revisar()
        alerta.refresh_from_db()
        self.assertEqual(self.fotoperiodo(22).horas, Decimal("10.00"))
        self.assertEqual(alerta.estado_alerta, "activa")
        self.assertEqual(self.alertas_de_fotoperiodo().count(), 1)

    def test_post_z_una_corrida_que_solo_calculo_resumenes_y_fotoperiodos_no_deja_registro(self):
        """«Auditoría»: un registro «solo si generó o resolvió alertas o borró lecturas». Los resúmenes y los fotoperíodos no se auditan: una corrida que solo los calculó
        (sin umbral, sin alertas y sin nada para borrar) no crea ninguno."""
        dia_de_luz(self.luz, 22)
        self.lectura(self.temp, local(23, 12, 10))
        resumen = self.revisar()
        self.assertGreater(resumen.resumenes, 0)
        self.assertEqual(resumen.fotoperiodos, 1)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ACCION).exists())

    def test_regla_fotoperiodo_la_segunda_corrida_con_el_mismo_ahora_no_cambia_nada(self):
        """Regla común (idempotencia)."""
        dia_de_luz(self.luz, 22)
        self.revisar()
        segunda = self.revisar()
        self.assertEqual((segunda.fotoperiodos, segunda.alertas_generadas, segunda.alertas_resueltas), (0, 0, 0))
        self.assertEqual(FotoperiodoDiario.objects.count(), 1)

    # ---- la comparación con el umbral efectivo ----

    def test_regla_fotoperiodo_fuera_del_rango_genera_la_alerta_con_su_descripcion_y_su_origen(self):
        """Extensión *b.5 y postcondición w: 10 h contra un mínimo efectivo de 12 h genera «fuera de umbral efectivo» (fotoperíodo), clave `sensor:<id>`, origen en el sensor
        (R052), descripción «{identificador} · {horas} h de luz el {DD/MM} (mínimo efectivo {mín} h)»."""
        self.con_umbral(12, 16)
        dia_de_luz(self.luz, 22)
        resumen = self.revisar()
        alerta = self.alertas_de_fotoperiodo().get()
        self.assertEqual(alerta.clave_estado, f"sensor:{self.luz.pk}")
        self.assertEqual(alerta.descripcion_alerta, "norte/sectorA/luz · 10 h de luz el 22/11 (mínimo efectivo 12 h)")
        self.assertEqual(AlertaIot.objects.get(alerta=alerta).hardware_id, self.luz.pk)
        self.assertEqual(resumen.alertas_generadas, 1)

    def test_regla_fotoperiodo_por_encima_del_maximo_dice_maximo_efectivo(self):
        """Mismo texto de «La revisión periódica»: «(máximo efectivo {máx} h)» cuando se pasa del máximo."""
        self.con_umbral(6, 9)
        dia_de_luz(self.luz, 22)
        self.revisar()
        self.assertEqual(self.alertas_de_fotoperiodo().get().descripcion_alerta, "norte/sectorA/luz · 10 h de luz el 22/11 (máximo efectivo 9 h)")

    def test_regla_fotoperiodo_dentro_del_rango_resuelve_la_alerta_que_tenia(self):
        """Extensión *b.5: «dentro [del rango], la resuelve». El límite es inclusivo: 10 h con un máximo de 10 h está dentro."""
        self.con_umbral(8, 10)
        alerta = self.alerta_activa_del_sensor()
        dia_de_luz(self.luz, 22)
        resumen = self.revisar()
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertEqual(resumen.alertas_resueltas, 1)

    def test_regla_fotoperiodo_sin_umbral_efectivo_no_toca_la_alerta_pero_guarda_el_fotoperiodo(self):
        """D-76 punto 5: la comparación exige umbral efectivo con fotoperíodo; sin él (sin lotes ni siembras) no genera ni resuelve nada. El fotoperíodo se calcula y se guarda."""
        alerta = self.alerta_activa_del_sensor()
        dia_de_luz(self.luz, 22)
        self.revisar()
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "activa")
        self.assertEqual(self.fotoperiodo(22).horas, Decimal("10.00"))

    def test_regla_fotoperiodo_un_dia_incompleto_no_toca_la_alerta(self):
        """D-76 punto 5: «un día incompleto o sin umbral no toca la alerta»: la que estaba activa sigue activa."""
        self.con_umbral(8, 14)
        alerta = self.alerta_activa_del_sensor()
        lecturas_por_minuto(self.luz, local(22, 2), local(23), 5000)
        self.revisar()
        alerta.refresh_from_db()
        self.assertTrue(self.fotoperiodo(22).incompleto)
        self.assertEqual(alerta.estado_alerta, "activa")

    def test_regla_fotoperiodo_un_sensor_o_un_sector_fuera_de_servicio_no_se_compara(self):
        """D-76 punto 5 («el sensor está activo y su sector no está fuera de servicio»): el fotoperíodo se calcula, pero no genera alerta."""
        self.con_umbral(12, 16)
        sector = crear_sector(self.norte, estado="fuera_de_servicio")
        en_sector = fabricas.sensor(
            self.sistema, "norte/sectorB/luz", "intensidad_luz", sector=sector, valor_calibracion_min=0, valor_calibracion_max=100000
        )
        fuera = fabricas.sensor(
            self.sistema, "norte/fuera/luz", "intensidad_luz", estado="fuera_de_servicio", valor_calibracion_min=0, valor_calibracion_max=100000
        )
        dia_de_luz(en_sector, 22)
        dia_de_luz(fuera, 22)
        self.revisar()
        self.assertEqual((self.fotoperiodo(22, en_sector).horas, self.fotoperiodo(22, fuera).horas), (Decimal("10.00"), Decimal("10.00")))
        self.assertFalse(self.alertas_de_fotoperiodo().exists())

    def test_regla_fotoperiodo_compara_los_dias_en_orden_y_queda_el_ultimo(self):
        """D-76 punto 5: «si se puede comparar, en el orden de los días». El 20/11 con 10 h está fuera de un mínimo de 11 h (genera) y el 21/11 con 12 h está dentro (la
        resuelve): al terminar, la alerta queda resuelta."""
        self.con_umbral(11, 16)
        dia_de_luz(self.luz, 20)
        dia_de_luz(self.luz, 21, desde=8, hasta=20)
        resumen = self.revisar()
        self.assertEqual((self.fotoperiodo(20).horas, self.fotoperiodo(21).horas), (Decimal("10.00"), Decimal("12.00")))
        self.assertFalse(self.alertas_de_fotoperiodo().exists())
        self.assertEqual(self.alertas_de_fotoperiodo("resuelta").count(), 1)
        self.assertEqual((resumen.alertas_generadas, resumen.alertas_resueltas), (1, 1))


# ---------------------------------------------------------------------------------------------------------------------------------------------------
# *b.6 · retención (D-76, punto 6)
# ---------------------------------------------------------------------------------------------------------------------------------------------------


class RevisionRetencionServicioTests(_Base):
    """`revisar`, paso 6: se borran las lecturas anteriores a la medianoche local de hoy menos los días de retención (7: el 16/11 a las 00:00), salvo las que originaron una
    alerta o dispararon una regla. Los resúmenes y los fotoperíodos no se borran nunca."""

    def test_regla_retencion_borra_las_lecturas_anteriores_a_la_medianoche_de_hoy_menos_los_dias_de_retencion(self):
        """Extensión *b.6, regla «Retención» y postcondición x: con 7 días, se borra lo anterior al 16/11 00:00 local; justo a esa hora y después, se conserva (el borde es
        exclusivo). Se audita (la corrida borró lecturas)."""
        vieja = self.lectura(self.temp, local(15, 23, 59))
        justo = self.lectura(self.temp, local(16, 0, 0))
        despues = self.lectura(self.temp, local(16, 0, 1))
        resumen = self.revisar()
        self.assertFalse(Telemetria.objects.filter(pk=vieja.pk).exists())
        self.assertEqual(set(Telemetria.objects.values_list("pk", flat=True)), {justo.pk, despues.pk})
        self.assertEqual(resumen.lecturas_borradas, 1)
        datos = RegistroAuditoria.objects.get(accion=ACCION).detalle["datos"]
        self.assertEqual((datos["lecturas_borradas"], datos["alertas_generadas"], datos["alertas_resueltas"]), (1, [], []))

    def test_regla_zona_la_retencion_corta_en_la_medianoche_local_y_no_en_la_de_utc(self):
        """D-76 punto 6 («medianoche (local)»): una lectura del 15/11 a las 22:00 locales es del 16/11 a la 01:00 UTC; es anterior al corte local (16/11 00:00) y se borra. Si se
        cortara en UTC, se conservaría."""
        tarde = self.lectura(self.temp, local(15, 22, 0))
        despues = self.lectura(self.temp, local(16, 0, 0))
        self.revisar()
        self.assertFalse(Telemetria.objects.filter(pk=tarde.pk).exists())
        self.assertTrue(Telemetria.objects.filter(pk=despues.pk).exists())

    def test_post_z_una_corrida_que_solo_borra_lecturas_crea_el_registro_con_afectados_vacios(self):
        """«Auditoría»: un registro «solo si generó o resolvió alertas o borró lecturas». Aunque no haya alertas, borrar lecturas lo crea; sus afectados son las alertas, o sea,
        ninguno."""
        self.lectura(self.temp, local(1, 10, 0))
        self.revisar()
        registro = RegistroAuditoria.objects.get(accion=ACCION)
        self.assertEqual(registro.afectados, [])
        self.assertEqual(registro.detalle["datos"]["lecturas_borradas"], 1)

    def test_regla_retencion_rige_el_parametro_vigente_de_la_configuracion_operativa(self):
        """Regla 7b de ADM-MOD-CFG: la retención rige «desde la próxima revisión periódica». Con 1 día, se borra lo anterior al 22/11 00:00."""
        configuracion.obtener()
        ConfiguracionOperativa.objects.filter(singleton=1).update(dias_retencion_telemetria=1)
        vieja = self.lectura(self.temp, local(21, 23, 59))
        reciente = self.lectura(self.temp, local(22, 0, 0))
        self.revisar()
        self.assertEqual(list(Telemetria.objects.values_list("pk", flat=True)), [reciente.pk])
        self.assertFalse(Telemetria.objects.filter(pk=vieja.pk).exists())

    def test_regla_retencion_conserva_las_lecturas_que_originaron_una_alerta(self):
        """Regla «Retención» y extensión *b.6: se conservan las que tienen un `AlertaIot` (R053), sea cual sea el estado de la alerta (activa o resuelta)."""
        con_alerta_activa = self.lectura(self.temp, local(1, 10, 0))
        con_alerta_resuelta = self.lectura(self.temp, local(1, 10, 1))
        sin_alerta = self.lectura(self.temp, local(1, 10, 2))
        clave = f"sensor:{self.temp.pk}"
        alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, "iot_fuera_de_umbral", clave, "fuera", telemetria=con_alerta_activa)
        alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, "iot_solucion_fuera_de_rango", clave, "fuera", telemetria=con_alerta_resuelta)
        alertas_iot.resolver_alerta_iot(self.norte.pk, "iot_solucion_fuera_de_rango", clave)
        self.revisar()
        self.assertEqual(set(Telemetria.objects.values_list("pk", flat=True)), {con_alerta_activa.pk, con_alerta_resuelta.pk})
        self.assertFalse(Telemetria.objects.filter(pk=sin_alerta.pk).exists())

    def test_regla_retencion_conserva_las_lecturas_que_dispararon_una_regla(self):
        """Regla «Retención» y R062: se conservan las lecturas de `ReglaActuacion.telemetrias`."""
        disparo = self.lectura(self.temp, local(1, 10, 0))
        sin_regla = self.lectura(self.temp, local(1, 10, 1))
        regla = fabricas.regla(self.temp, fabricas.actuador(self.sistema, identificador="norte/ventilador"))
        regla.telemetrias.add(disparo)
        self.revisar()
        self.assertEqual(list(Telemetria.objects.values_list("pk", flat=True)), [disparo.pk])
        self.assertFalse(Telemetria.objects.filter(pk=sin_regla.pk).exists())

    def test_regla_retencion_nunca_borra_resumenes_ni_fotoperiodos(self):
        """Regla «Resúmenes horarios»: «no se borran por la retención»; tampoco los fotoperíodos (extensión *b.6)."""
        resumen_viejo = ResumenHorario.objects.create(sensor=self.temp, hora=local(1, 10), minimo=Decimal("1"), promedio=Decimal("1"), maximo=Decimal("1"), cantidad_lecturas=1)
        fotoperiodo_viejo = FotoperiodoDiario.objects.create(sensor=fabricas.sensor(self.sistema, "norte/luz", "intensidad_luz", valor_calibracion_min=0, valor_calibracion_max=100000), fecha=date(2026, 11, 1), horas=Decimal("10.00"))
        self.lectura(self.temp, local(1, 10, 5))
        self.revisar()
        self.assertTrue(ResumenHorario.objects.filter(pk=resumen_viejo.pk).exists())
        self.assertTrue(FotoperiodoDiario.objects.filter(pk=fotoperiodo_viejo.pk).exists())

    def test_regla_retencion_despues_de_muchos_dias_sin_correr_resume_y_calcula_antes_de_borrar(self):
        """D-76 punto 6: la retención va DESPUÉS de los pasos 4 y 5 de la misma corrida. Con la revisión sin correr más días que la retención (las lecturas son del 3/11 y hoy
        es el 23/11), una sola corrida resume cada hora y calcula el fotoperíodo del día antes de borrar: ninguna hora con lecturas queda sin resumen."""
        luz = fabricas.sensor(self.sistema, "norte/sectorA/luz", "intensidad_luz", valor_calibracion_min=0, valor_calibracion_max=100000)
        dia_de_luz(luz, 3)
        self.lectura(self.temp, local(3, 10, 5), "20")
        self.lectura(self.temp, local(3, 10, 10), "30")
        resumen = self.revisar()
        self.assertEqual(Telemetria.objects.count(), 0)
        self.assertEqual(resumen.lecturas_borradas, 1442)
        self.assertEqual(ResumenHorario.objects.filter(sensor=luz).count(), 24)
        fila = self.resumen_de(self.temp, local(3, 10))
        self.assertEqual((fila.minimo, fila.maximo, fila.cantidad_lecturas), (Decimal("20"), Decimal("30"), 2))
        self.assertEqual(FotoperiodoDiario.objects.get(sensor=luz, fecha=date(2026, 11, 3)).horas, Decimal("10.00"))

    def test_regla_retencion_la_segunda_corrida_con_el_mismo_ahora_no_borra_nada(self):
        """Regla común (idempotencia): lo ya borrado no se cuenta otra vez ni se audita otra vez."""
        self.lectura(self.temp, local(1, 10, 0))
        self.revisar()
        auditorias = RegistroAuditoria.objects.filter(accion=ACCION).count()
        segunda = self.revisar()
        self.assertEqual(segunda.lecturas_borradas, 0)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ACCION).count(), auditorias)
