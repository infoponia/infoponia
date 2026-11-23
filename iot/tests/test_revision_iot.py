# Pruebas de IOT-ENT-INF, extensión *b, pasos 1 a 3 y reglas comunes de la revisión periódica (IOT-04; docs/casos_de_uso/iot/entregar_informacion.md, «La revisión
# periódica»; D-71 y D-76). Se escribieron ANTES que el servicio (`.claude/rules/pruebas.md`). Los pasos 4 a 6 (resúmenes, fotoperíodo, retención) están en
# `test_revision_resumenes.py` y los correos, en `test_revision_correos.py`.
#
# Servicio que se prueba:
#   iot/servicios/revision.py:  revisar(ahora) -> ResumenDeRevision(ahora, sistemas, correos)
#       sistemas: ResumenDeSistema(sistema, alertas_generadas, alertas_resueltas, resumenes, fotoperiodos, lecturas_borradas, error)   (enteros; error es None o texto)
#       correos:  ResumenDeCorreos(enviados, fallidos, pendientes_sin_servidor)
#       ResumenDeRevision.hubo_fallos -> bool
#
# Ninguna prueba depende de la hora del día: ``revisar`` recibe ``ahora`` y las pruebas usan siempre el mismo. La zona del proyecto es Argentina (UTC-3).

from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from core.models import Gerente, RegistroAuditoria, referencia
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import AlertaIot, Hardware, NodoCentral
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

revision = perezoso("iot.servicios.revision")
alertas_iot = perezoso("iot.servicios.alertas_iot")

LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")
AHORA = datetime(2026, 11, 23, 12, 0, tzinfo=LOCAL)  # lunes, mediodía
ACCION = "revision_periodica_iot"


class RevisionIotServicioTests(fabricas.ConCatalogoIot, TestCase):
    """`revisar(ahora)`: sensores sin actividad (*b.1), nodo sin comunicación (*b.2) y «no registrado» sin mensajes (*b.3), más lo que vale para todos los pasos
    (un sistema activo por transacción, el que falla no frena a los demás, idempotencia y auditoría). Valores iniciales: 5 minutos sin actividad y 3 sin comunicación."""

    def setUp(self):
        cache.clear()
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.temp = fabricas.sensor(self.sistema, "norte/sectorA/temperatura")

    # ---- ayudas ----

    def mensaje_hace(self, equipo, minutos):
        """El último mensaje del equipo llegó hace ``minutos`` minutos."""
        Hardware.objects.filter(pk=equipo.pk).update(ultimo_mensaje_en=AHORA - timedelta(minutes=minutos))

    def comunicacion_hace(self, minutos):
        """El nodo se comunicó por última vez hace ``minutos`` minutos."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=AHORA - timedelta(minutes=minutos))

    def alertas(self, tipo, estado="activa"):
        return Alerta.objects.filter(tipo_alerta=tipo, estado_alerta=estado)

    def no_registrado(self, identificador="norte/otro", ultimo_mensaje_hace=None):
        """Una alerta «dispositivo no registrado» activa de ``identificador``, con su último mensaje rechazado hace ``ultimo_mensaje_hace`` minutos."""
        alerta = alertas_iot.asegurar_alerta_iot(
            self.norte.pk,
            self.sistema,
            "iot_dispositivo_no_registrado",
            f"id:{identificador.lower()}",
            f"El nodo envió una lectura de «{identificador}» (24), que no está registrado.",
        ).alerta
        if ultimo_mensaje_hace is not None:
            AlertaIot.objects.filter(alerta=alerta).update(ultimo_mensaje_en=AHORA - timedelta(minutes=ultimo_mensaje_hace))
        return alerta

    def un_segundo_invernadero(self, nombre="Sur", **extra):
        """Otro invernadero con su sistema activo y su sensor, para las pruebas con más de un sistema."""
        invernadero = crear_invernadero(nombre, agronomo=crear_agronomo(f"{nombre.lower()}@infoponia.com"))
        sistema = fabricas.sistema(invernadero, **extra)
        return invernadero, sistema, fabricas.sensor(sistema, f"{nombre.lower()}/temperatura")

    # ---- *b.1: sensores sin actividad ----

    def test_ext_bstar_1_justo_en_el_plazo_no_genera_la_alerta(self):
        """Extensión *b.1 y D-76 punto 1: el sensor genera la alerta solo si su último mensaje es ANTERIOR a `ahora − minutos_sin_actividad`; justo en el plazo (5 min), no."""
        self.mensaje_hace(self.temp, 5)
        revision.revisar(AHORA)
        self.assertFalse(self.alertas("iot_dispositivo_sin_actividad").exists())

    def test_ext_bstar_1_un_minuto_despues_del_plazo_genera_la_alerta_con_su_descripcion_y_su_origen(self):
        """Extensión *b.1 y postcondición u: pasado el plazo (6 min) se genera «dispositivo sin actividad», clave `hw:<id>`, con la descripción de «La revisión
        periódica», origen en el sensor (R052) y el sistema."""
        self.mensaje_hace(self.temp, 6)
        resumen = revision.revisar(AHORA)
        alerta = self.alertas("iot_dispositivo_sin_actividad").get()
        self.assertEqual(alerta.clave_estado, f"hw:{self.temp.pk}")
        self.assertEqual(alerta.descripcion_alerta, "norte/sectorA/temperatura · sin lecturas desde las 11:54 del 23/11")
        vinculo = AlertaIot.objects.get(alerta=alerta)
        self.assertEqual((vinculo.sistema, vinculo.hardware_id, vinculo.telemetria_id), (self.sistema, self.temp.pk, None))
        self.assertEqual(resumen.sistemas[0].alertas_generadas, 1)

    def test_ext_bstar_1_los_sensores_sin_confirmar_no_generan_la_alerta(self):
        """Extensión *b.1 y regla «Inactividad»: «Los sensores "sin confirmar" no generan esta alerta» (`ultimo_mensaje_en` nulo, aunque sea viejo el sensor)."""
        self.assertIsNone(self.temp.ultimo_mensaje_en)
        revision.revisar(AHORA)
        self.assertFalse(self.alertas("iot_dispositivo_sin_actividad").exists())

    def test_ext_bstar_1_solo_los_sensores_activos_generan_la_alerta(self):
        """Extensión *b.1 («cada sensor activo»): un sensor fuera de servicio, uno dado de baja y un actuador con mensajes viejos no generan «sin actividad»."""
        fuera = fabricas.sensor(self.sistema, "norte/fuera", estado="fuera_de_servicio")
        baja = fabricas.sensor(self.sistema, "norte/baja", estado="inactivo")
        actuador = fabricas.actuador(self.sistema, identificador="norte/ventilador")
        for equipo in (fuera, baja, actuador):
            self.mensaje_hace(equipo, 60)
        revision.revisar(AHORA)
        self.assertFalse(self.alertas("iot_dispositivo_sin_actividad").exists())

    def test_ext_bstar_1_la_alerta_ya_activa_no_se_duplica(self):
        """Regla «Alertas»: a lo sumo una alerta activa por equipo y tipo. Con el sensor todavía sin actividad, otra corrida deja la misma alerta."""
        self.mensaje_hace(self.temp, 30)
        revision.revisar(AHORA)
        revision.revisar(AHORA + timedelta(minutes=5))
        self.assertEqual(self.alertas("iot_dispositivo_sin_actividad").count(), 1)

    # ---- *b.2: nodo sin comunicación ----

    def test_ext_bstar_2_justo_en_el_plazo_no_genera_la_alerta(self):
        """Extensión *b.2 y D-76 punto 2: el nodo genera la alerta solo si su última comunicación es ANTERIOR a `ahora − minutos_sin_comunicacion`; justo en 3 min, no."""
        self.comunicacion_hace(3)
        revision.revisar(AHORA)
        self.assertFalse(self.alertas("iot_nodo_sin_comunicacion").exists())

    def test_ext_bstar_2_un_minuto_despues_del_plazo_genera_la_alerta_sin_hardware_ni_telemetria(self):
        """Extensión *b.2 y postcondición u: pasado el plazo (4 min) se genera «nodo sin comunicación», clave `nodo:<id>`, sin hardware ni telemetría de origen, con la
        descripción «{nombre del nodo} · sin comunicación desde las HH:MM del DD/MM»."""
        self.comunicacion_hace(4)
        resumen = revision.revisar(AHORA)
        alerta = self.alertas("iot_nodo_sin_comunicacion").get()
        self.assertEqual(alerta.clave_estado, f"nodo:{self.nodo.pk}")
        self.assertEqual(alerta.descripcion_alerta, "Nodo de prueba · sin comunicación desde las 11:56 del 23/11")
        vinculo = AlertaIot.objects.get(alerta=alerta)
        self.assertEqual((vinculo.sistema, vinculo.hardware_id, vinculo.telemetria_id), (self.sistema, None, None))
        self.assertEqual(resumen.sistemas[0].alertas_generadas, 1)

    def test_ext_bstar_2_un_nodo_que_nunca_se_comunico_no_genera_la_alerta(self):
        """Extensión *b.2 y regla «Inactividad»: «Un nodo que todavía no se comunicó no genera esta alerta» (`ultima_comunicacion` nula)."""
        self.assertIsNone(self.nodo.ultima_comunicacion)
        revision.revisar(AHORA)
        self.assertFalse(self.alertas("iot_nodo_sin_comunicacion").exists())

    # ---- *b.3: «dispositivo no registrado» sin mensajes ----

    def test_ext_bstar_3_la_alerta_se_resuelve_recien_cuando_el_ultimo_mensaje_es_mas_viejo_que_el_plazo(self):
        """Extensión *b.3 y D-76 punto 3: con el último mensaje rechazado justo en el plazo (5 min) sigue activa; un minuto después (6 min), pasa a «resuelta»."""
        alerta = self.no_registrado(ultimo_mensaje_hace=5)
        revision.revisar(AHORA)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "activa")
        AlertaIot.objects.filter(alerta=alerta).update(ultimo_mensaje_en=AHORA - timedelta(minutes=6))
        resumen = revision.revisar(AHORA)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertEqual(resumen.sistemas[0].alertas_resueltas, 1)

    def test_ext_bstar_3_cada_identificador_se_resuelve_por_su_propio_ultimo_mensaje(self):
        """Extensión *b.3: «la última alerta "dispositivo no registrado" de un identificador»: la de un identificador con mensajes recientes sigue activa."""
        vieja = self.no_registrado("norte/vieja", ultimo_mensaje_hace=20)
        reciente = self.no_registrado("norte/reciente", ultimo_mensaje_hace=1)
        revision.revisar(AHORA)
        vieja.refresh_from_db()
        reciente.refresh_from_db()
        self.assertEqual((vieja.estado_alerta, reciente.estado_alerta), ("resuelta", "activa"))

    # ---- los sistemas que se revisan ----

    def test_regla_un_sistema_desconectado_o_dado_de_baja_no_se_revisa(self):
        """Regla común de «La revisión periódica»: «Los desconectados y los dados de baja no se revisan»: no generan alertas ni figuran en el resumen."""
        _, desconectado, sensor_desconectado = self.un_segundo_invernadero("Sur", estado="desconectado")
        _, de_baja, sensor_de_baja = self.un_segundo_invernadero("Este", estado="inactivo")
        for sensor in (sensor_desconectado, sensor_de_baja):
            self.mensaje_hace(sensor, 60)
        resumen = revision.revisar(AHORA)
        self.assertFalse(Alerta.objects.exists())
        self.assertEqual([r.sistema.pk for r in resumen.sistemas], [self.sistema.pk])

    def test_regla_los_sistemas_se_revisan_en_orden_de_id(self):
        """Regla común: «cada sistema IoT activo, en su propia transacción, en orden de id»."""
        _, sur, _ = self.un_segundo_invernadero("Sur")
        _, este, _ = self.un_segundo_invernadero("Este")
        resumen = revision.revisar(AHORA)
        self.assertEqual([r.sistema.pk for r in resumen.sistemas], [self.sistema.pk, sur.pk, este.pk])

    def test_regla_sin_sistemas_activos_el_resumen_viene_vacio(self):
        """Salida del comando: «No hay sistemas IoT activos» sale de un resumen sin sistemas, sin error."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        resumen = revision.revisar(AHORA)
        self.assertEqual(resumen.sistemas, [])
        self.assertFalse(resumen.hubo_fallos)

    def test_regla_un_invernadero_inactivo_no_recibe_alertas_y_no_rompe(self):
        """Docs/api/alertas.md, sección 2 (post e de PROD-BAJ-INV): con el invernadero inactivo la API de `maestros` devuelve `None`; la revisión sigue sin error."""
        inactivo = crear_invernadero("Viejo", activo=False)
        sistema = fabricas.sistema(inactivo)
        sensor = fabricas.sensor(sistema, "viejo/temperatura")
        self.mensaje_hace(sensor, 60)
        NodoCentral.objects.filter(sistema=sistema).update(ultima_comunicacion=AHORA - timedelta(minutes=60))
        resumen = revision.revisar(AHORA)
        self.assertFalse(Alerta.objects.filter(invernadero=inactivo).exists())
        propio = next(r for r in resumen.sistemas if r.sistema.pk == sistema.pk)
        self.assertEqual((propio.error, propio.alertas_generadas), (None, 0))
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ACCION).exists())

    def test_regla_un_sistema_que_falla_no_frena_a_los_demas_y_queda_en_el_resumen(self):
        """D-71 punto 2 y D-76: si un sistema falla, `logger.exception` (registrador `iot.revision`), se informa y se sigue con los demás. Su transacción se deshace."""
        sur, sistema_sur, sensor_sur = self.un_segundo_invernadero("Sur")
        self.mensaje_hace(self.temp, 30)
        self.mensaje_hace(sensor_sur, 30)
        real = alertas_iot.asegurar_alerta_iot

        def falla_en_norte(invernadero_id, sistema, *args, **kwargs):
            if sistema.pk == self.sistema.pk:
                raise RuntimeError("falla de prueba")
            return real(invernadero_id, sistema, *args, **kwargs)

        with mock.patch("iot.servicios.alertas_iot.asegurar_alerta_iot", side_effect=falla_en_norte):
            with self.assertLogs("iot.revision", level="ERROR"):
                resumen = revision.revisar(AHORA)
        norte, sur_resumen = resumen.sistemas
        self.assertIn("falla de prueba", norte.error)
        self.assertEqual((sur_resumen.error, sur_resumen.alertas_generadas), (None, 1))
        self.assertTrue(resumen.hubo_fallos)
        self.assertEqual(list(Alerta.objects.values_list("invernadero_id", flat=True)), [sur.pk])
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ACCION).count(), 1)

    # ---- idempotencia ----

    def test_regla_dos_corridas_seguidas_con_el_mismo_ahora_no_duplican_nada(self):
        """Regla común: «es idempotente: dos corridas seguidas con el mismo `ahora` no cambian nada la segunda vez (ni alertas, ni auditoría)»."""
        self.mensaje_hace(self.temp, 30)
        self.comunicacion_hace(10)
        self.no_registrado(ultimo_mensaje_hace=30)
        primera = revision.revisar(AHORA).sistemas[0]
        alertas, vinculos, auditorias = Alerta.objects.count(), AlertaIot.objects.count(), RegistroAuditoria.objects.filter(accion=ACCION).count()
        segunda = revision.revisar(AHORA).sistemas[0]
        self.assertEqual((primera.alertas_generadas, primera.alertas_resueltas), (2, 1))
        self.assertEqual((segunda.alertas_generadas, segunda.alertas_resueltas), (0, 0))
        self.assertEqual((Alerta.objects.count(), AlertaIot.objects.count()), (alertas, vinculos))
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ACCION).count(), auditorias)

    # ---- auditoría (postcondición z) ----

    def test_post_z_un_registro_por_sistema_con_las_alertas_generadas_y_resueltas(self):
        """Postcondición z y «Auditoría»: acción `revision_periodica_iot`, actor `None` (InfoPonia), un registro por sistema con `datos` (origen, sistema, ahora, alertas
        generadas y resueltas, lecturas borradas) y como afectados, las alertas. El detalle solo tiene `datos` (D-36)."""
        self.mensaje_hace(self.temp, 30)
        self.comunicacion_hace(10)
        resuelta = self.no_registrado(ultimo_mensaje_hace=30)
        revision.revisar(AHORA)
        registro = RegistroAuditoria.objects.get(accion=ACCION)
        self.assertIsNone(registro.usuario)
        self.assertEqual(set(registro.detalle), {"datos"})
        datos = registro.detalle["datos"]
        generadas = self.alertas("iot_dispositivo_sin_actividad") | self.alertas("iot_nodo_sin_comunicacion")
        self.assertEqual(
            {clave: valor for clave, valor in datos.items() if not clave.startswith("alertas")},
            {"origen": "revision_periodica", "sistema": referencia(self.sistema), "ahora": AHORA.isoformat(), "lecturas_borradas": 0},
        )
        self.assertEqual({a["id"] for a in datos["alertas_generadas"]}, set(generadas.values_list("pk", flat=True)))
        self.assertEqual([a["id"] for a in datos["alertas_resueltas"]], [resuelta.pk])
        self.assertEqual({a["modelo"] for a in registro.afectados}, {"maestros.alerta"})
        self.assertEqual({a["id"] for a in registro.afectados}, {*generadas.values_list("pk", flat=True), resuelta.pk})

    def test_post_z_sin_cambios_la_revision_no_deja_registro(self):
        """«Auditoría»: un registro «solo si generó o resolvió alertas o borró lecturas»; una corrida que no cambió nada no audita."""
        self.mensaje_hace(self.temp, 1)
        self.comunicacion_hace(1)
        revision.revisar(AHORA)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ACCION).exists())

    def test_post_z_cada_sistema_deja_su_propio_registro(self):
        """«Auditoría»: «un registro por sistema y por corrida»."""
        _, sur, sensor_sur = self.un_segundo_invernadero("Sur")
        self.mensaje_hace(self.temp, 30)
        self.mensaje_hace(sensor_sur, 30)
        revision.revisar(AHORA)
        sistemas = [r.detalle["datos"]["sistema"]["id"] for r in RegistroAuditoria.objects.filter(accion=ACCION).order_by("pk")]
        self.assertEqual(sistemas, [self.sistema.pk, sur.pk])


class RevisionIotZonaYAhoraTests(fabricas.ConCatalogoIot, TestCase):
    """Zona horaria de las descripciones y contrato de ``ahora`` (uno ingenuo no se acepta; en la auditoría va como texto y el registro se lee y se muestra)."""

    def setUp(self):
        cache.clear()
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.temp = fabricas.sensor(self.sistema, "norte/sectorA/temperatura")

    def alertas(self, tipo):
        return Alerta.objects.filter(tipo_alerta=tipo, estado_alerta="activa")

    def mensaje_hace(self, equipo, minutos):
        Hardware.objects.filter(pk=equipo.pk).update(ultimo_mensaje_en=AHORA - timedelta(minutes=minutos))

    def test_regla_zona_la_descripcion_de_sin_actividad_y_de_sin_comunicacion_sale_en_hora_local(self):
        """D-76 y «La revisión periódica» («desde las {HH:MM} del {DD/MM}»): el último mensaje es de las 22:00 locales del 22/11, que son las 01:00 UTC del 23/11; la
        descripción dice 22:00 del 22/11, no la hora UTC."""
        ahora = datetime(2026, 11, 22, 22, 10, tzinfo=LOCAL)
        Hardware.objects.filter(pk=self.temp.pk).update(ultimo_mensaje_en=datetime(2026, 11, 22, 22, 0, tzinfo=LOCAL))
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=datetime(2026, 11, 22, 22, 0, tzinfo=LOCAL))
        revision.revisar(ahora)
        self.assertEqual(
            self.alertas("iot_dispositivo_sin_actividad").get().descripcion_alerta,
            "norte/sectorA/temperatura · sin lecturas desde las 22:00 del 22/11",
        )
        self.assertEqual(
            self.alertas("iot_nodo_sin_comunicacion").get().descripcion_alerta, "Nodo de prueba · sin comunicación desde las 22:00 del 22/11"
        )

    def test_regla_ahora_sin_zona_horaria_se_rechaza_sin_cambiar_nada(self):
        """D-71 punto 2 («recibe `ahora`»): `revisar` exige un `datetime` con zona; uno ingenuo es un error de programación (`ValueError`) y no deja nada hecho."""
        self.mensaje_hace(self.temp, 30)
        with self.assertRaises(ValueError):
            revision.revisar(datetime(2026, 11, 23, 12, 0))
        self.assertFalse(Alerta.objects.exists())

    def test_post_z_ahora_va_como_texto_y_el_registro_se_lee_y_se_muestra(self):
        """D-36 (un `datetime` no es un valor permitido en el detalle): `ahora` se guarda como texto ISO. El registro se arma con `filas_de_datos` y la pantalla de
        auditoría del Gerente lo muestra (200) sin `ValueError`, con la etiqueta «Hora de la revisión»."""
        self.mensaje_hace(self.temp, 30)
        revision.revisar(AHORA)
        registro = RegistroAuditoria.objects.get(accion=ACCION)
        self.assertEqual(registro.detalle["datos"]["ahora"], AHORA.isoformat())
        filas = dict(registro.filas_de_datos())
        self.assertIn("2026-11-23", filas["Hora de la revisión"])
        self.client.force_login(Gerente.objects.get())
        respuesta = self.client.get(reverse("core:auditoria_registro", args=[registro.pk]))
        self.assertContains(respuesta, "Hora de la revisión")
