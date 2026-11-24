# Pruebas de IOT-CNS-RGL · Consultar Regla de Actuación (docs/casos_de_uso/iot/reglas_de_actuacion.md, con «Cómo se aplica en la ronda «IoT 1»») y de lo que cita: D-28, D-75 (punto 7) y D-78 (punto 8).
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban (iot/servicios/reglas.py), tomados del módulo dentro de cada prueba:
#   texto_de_regla(regla) -> str                       «Cuando {sensor} {identificador} {condición}, {actuador} {identificador}: {acción}[ {valor} {unidad}]» (prototipo ``rglText``)
#   buscar_reglas(actor, invernadero_id, filtros=None) -> [FilaDeRegla(regla, codigo, texto, evaluacion, ultimo_disparo, motivos)]
#       ``filtros``: ``FiltrosDeReglas(estado, sensor_id, actuador_id)`` (vacío no filtra); ``codigo``: «RGL-{id}»; ``evaluacion``: «Se cumple», «Confirmando {n} de {N}», «No se cumple»,
#       «Sin evaluar» o «Confirmada · esperando al actuador»; ``ultimo_disparo``: el último ``Comando`` de la regla o ``None``; ``motivos``: ``[Motivo(clave, texto)]``.
#   ficha_de_regla(actor, regla_id) -> FichaDeRegla(fila, comandos)       el historial de comandos de la regla, del más reciente al más viejo
#   acciones_permitidas(actor, regla) -> frozenset                         ``modificar`` y ``baja`` (activa) o ``reactivar`` (inactiva), solo a quien opera el invernadero (D-30)
# Claves de ``Motivo``: ``actuador_fuera_de_servicio``, ``accion_incompatible``, ``sin_umbral``, ``modo_local``, ``sector_fuera_de_servicio``, ``sensor_fuera_de_servicio`` y ``sistema_desconectado``.

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz
from inventario.tests.fabricas import variedad_con_semilla, variedades_presentes_de_prueba
from iot.models import NodoCentral, ReglaActuacion
from iot.tests import fabricas
from iot.tests.escena_de_reglas import ConEscenaDeReglas, reglas
from maestros.tests.fabricas import crear_agronomo, crear_sector, crear_tecnico


class IotCnsRglServicioTests(ConEscenaDeReglas, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-CNS-RGL."""

    def setUp(self):
        super().setUp()
        self.regla = self.alta()
        self.crespa = variedad_con_semilla(nombre="Crespa")

    def umbral(self):
        """Un umbral efectivo para «Norte» (para que la regla no avise «sin umbral»)."""
        return variedades_presentes_de_prueba({self.norte.pk: {self.crespa.pk}})

    def fila(self, regla=None):
        with self.umbral():
            filas = reglas.buscar_reglas(self.laura, self.norte.pk)
        return next(f for f in filas if f.regla.pk == (regla or self.regla).pk)

    def claves(self, regla=None):
        return {m.clave for m in self.fila(regla).motivos}

    # ---- alcance (regla 1) ----

    def test_regla_1_otros_roles_reciben_403_y_otro_invernadero_da_404(self):
        """Precondición a y regla 1: Agrónomo o Gerente activos; D-28 para lo que no se consulta."""
        for otro in (crear_tecnico(), crear_capataz()):
            with self.assertRaises(PermissionDenied):
                reglas.buscar_reglas(otro, self.norte.pk)
        ajeno = crear_agronomo("otro@infoponia.com")
        with self.assertRaises(Http404):
            reglas.buscar_reglas(ajeno, self.norte.pk)
        with self.assertRaises(Http404):
            reglas.ficha_de_regla(ajeno, self.regla.pk)

    def test_regla_1_el_gerente_consulta_todos_los_invernaderos(self):
        """Regla 1 (la de IOT-CNS-HDW): el Gerente consulta todos, aunque haya Agrónomo activo."""
        self.assertEqual([f.regla.pk for f in reglas.buscar_reglas(self.gerente, self.norte.pk)], [self.regla.pk])

    def test_post_a_la_consulta_no_cambia_nada_y_no_se_audita(self):
        """Postcondición a y regla 6 (SEG-14): no escribe ni audita."""
        antes = RegistroAuditoria.objects.count()
        reglas.buscar_reglas(self.laura, self.norte.pk)
        reglas.ficha_de_regla(self.laura, self.regla.pk)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    # ---- regla 2 (qué se ve de cada regla) ----

    def test_regla_2_texto_codigo_y_datos_de_la_regla(self):
        """Regla 2 y prototipo ``rglText``: el texto con el sensor, la condición, el actuador, la acción y, si lleva, el valor con su unidad."""
        fila = self.fila()
        self.assertEqual(fila.codigo, f"RGL-{self.regla.pk}")
        self.assertEqual(fila.texto, "Cuando Temperatura norte/temp supera el máximo del umbral efectivo, Ventilador norte/ventilador: Encender")
        con_valor = self.alta(actuador=self.ventana, valor="40", condicion="vuelve_al_rango")
        self.assertEqual(
            reglas.texto_de_regla(con_valor), "Cuando Temperatura norte/temp vuelve a quedar dentro del umbral efectivo, Ventana norte/ventana: Fijar posición 40 %"
        )
        baja = self.alta(sensor=self.hum, condicion="baja_del_minimo")
        self.assertIn("baja del mínimo del umbral efectivo", reglas.texto_de_regla(baja))

    def test_regla_2_la_evaluacion_se_muestra_como_el_prototipo(self):
        """Regla 2 y prototipo ``ultB``: «Se cumple», «Confirmando n de N» (N, de la Configuración Operativa), «No se cumple» y «Sin evaluar»."""
        casos = (
            ("sin_evaluar", 0, "Sin evaluar"),
            ("no_cumplida", 0, "No se cumple"),
            ("no_cumplida", 2, "Confirmando 2 de 3"),
            ("cumplida", 0, "Se cumple"),
        )
        for evaluacion, contador, texto in casos:
            ReglaActuacion.objects.filter(pk=self.regla.pk).update(ultima_evaluacion=evaluacion, contador_confirmacion=contador)
            self.assertEqual(self.fila().evaluacion, texto, (evaluacion, contador))

    def test_regla_2_una_regla_confirmada_que_espera_al_actuador_no_dice_confirmando_3_de_3(self):
        """D-78 punto 8: una regla ocupada queda «no cumplida» con el contador en la confirmación; se muestra «Confirmada · esperando al actuador» (corrección del prototipo, L7)."""
        ReglaActuacion.objects.filter(pk=self.regla.pk).update(ultima_evaluacion="no_cumplida", contador_confirmacion=3)
        self.assertEqual(self.fila().evaluacion, "Confirmada · esperando al actuador")

    def test_regla_2_el_ultimo_disparo_es_el_ultimo_comando_de_la_regla(self):
        """Regla 2: la fecha y hora, el comando emitido y su resultado; sin comandos, ``None``. Los comandos manuales del mismo actuador no cuentan."""
        self.assertIsNone(self.fila().ultimo_disparo)
        viejo = fabricas.comando(self.ventilador, self.encender, estado="ejecutado", regla=self.regla, emitido_en=fabricas.INSTANTE_BASE)
        nuevo = fabricas.comando(self.ventilador, self.apagar, estado="fallido", regla=self.regla, emitido_en=fabricas.INSTANTE_BASE.replace(hour=15))
        fabricas.comando(self.ventilador, self.encender, estado="ejecutado", emitido_en=fabricas.INSTANTE_BASE.replace(hour=20))
        self.assertEqual(self.fila().ultimo_disparo.pk, nuevo.pk)
        self.assertNotEqual(viejo.pk, nuevo.pk)

    def test_regla_2_sin_motivos_cuando_la_regla_puede_emitir(self):
        """Regla 2: con umbral, actuador activo y compatible, nodo remoto y sistema activo, no hay motivos."""
        self.assertEqual(self.claves(), set())

    def test_regla_2_motivo_actuador_fuera_de_servicio(self):
        """Regla 2: «actuador fuera de servicio»."""
        type(self.ventilador).objects.filter(pk=self.ventilador.pk).update(estado_hardware="fuera_de_servicio")
        self.assertEqual(self.claves(), {"actuador_fuera_de_servicio"})

    def test_regla_2_motivo_accion_incompatible_con_el_nodo(self):
        """Regla 2: «acción incompatible con el nodo»."""
        self.ventilador.acciones_incompatibles.add(self.encender)
        self.assertEqual(self.claves(), {"accion_incompatible"})

    def test_regla_2_motivo_sin_umbral_efectivo(self):
        """Regla 2: «sin umbral efectivo»; el invernadero no tiene variedades presentes."""
        filas = reglas.buscar_reglas(self.laura, self.norte.pk)
        self.assertEqual({m.clave for m in filas[0].motivos}, {"sin_umbral"})

    def test_regla_2_motivo_nodo_en_modo_local(self):
        """Regla 2: «nodo en modo local»."""
        NodoCentral.objects.filter(sistema=self.sistema).update(modo="local")
        self.assertEqual(self.claves(), {"modo_local"})

    def test_regla_2_motivo_sensor_en_un_sector_fuera_de_servicio(self):
        """D-75 punto 7 y extensión 5d: el sensor de la temperatura de un sector fuera de servicio no se evalúa."""
        sector = crear_sector(self.norte, "Sector A", "germinacion", 50, estado="fuera_de_servicio")
        en_sector = fabricas.sensor(self.sistema, "norte/sa", sector=sector)
        otra = self.alta(sensor=en_sector)
        self.assertEqual(self.claves(otra), {"sector_fuera_de_servicio"})

    def test_regla_2_motivos_sensor_fuera_de_servicio_y_sistema_desconectado(self):
        """Extensiones 3c y \\*a: un sensor con falla informada y un sistema desconectado tampoco evalúan reglas."""
        type(self.temp).objects.filter(pk=self.temp.pk).update(estado_hardware="fuera_de_servicio")
        self.assertEqual(self.claves(), {"sensor_fuera_de_servicio"})
        type(self.temp).objects.filter(pk=self.temp.pk).update(estado_hardware="activo")
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        self.assertEqual(self.claves(), {"sistema_desconectado"})

    def test_regla_2_los_motivos_se_suman(self):
        """Regla 2: si hay más de un motivo, se muestran todos."""
        type(self.ventilador).objects.filter(pk=self.ventilador.pk).update(estado_hardware="fuera_de_servicio")
        NodoCentral.objects.filter(sistema=self.sistema).update(modo="local")
        self.assertEqual(self.claves(), {"actuador_fuera_de_servicio", "modo_local"})

    # ---- regla 3 (filtros) ----

    def test_regla_3_se_filtra_por_estado_sensor_y_actuador(self):
        """Regla 3: por estado (las dadas de baja se muestran con el filtro, lo que difiere del prototipo), por sensor y por actuador."""
        humedad = self.alta(sensor=self.hum)
        ventana = self.alta(actuador=self.ventana, valor="10")
        baja = self.alta(condicion="baja_del_minimo")
        ReglaActuacion.objects.filter(pk=baja.pk).update(estado_regla="inactiva")

        def ids(**filtros):
            return {f.regla.pk for f in reglas.buscar_reglas(self.laura, self.norte.pk, reglas.FiltrosDeReglas(**filtros))}

        self.assertEqual(ids(), {self.regla.pk, humedad.pk, ventana.pk, baja.pk})
        self.assertEqual(ids(estado="activa"), {self.regla.pk, humedad.pk, ventana.pk})
        self.assertEqual(ids(estado="inactiva"), {baja.pk})
        self.assertEqual(ids(sensor_id=self.hum.pk), {humedad.pk})
        self.assertEqual(ids(actuador_id=self.ventana.pk), {ventana.pk})
        self.assertEqual(ids(estado="activa", sensor_id=self.temp.pk, actuador_id=self.ventilador.pk), {self.regla.pk})
        self.assertEqual(ids(estado="cualquiera"), {self.regla.pk, humedad.pk, ventana.pk, baja.pk})  # un filtro desconocido se ignora

    def test_regla_3_solo_las_del_invernadero_elegido(self):
        """Alcance por invernadero: las reglas de otro invernadero no aparecen."""
        otro = crear_agronomo("sur@infoponia.com")
        from maestros.tests.fabricas import crear_invernadero

        sur = crear_invernadero("Sur", agronomo=otro)
        sistema_sur = fabricas.sistema(sur)
        fabricas.regla(fabricas.sensor(sistema_sur, "sur/temp"), fabricas.actuador(sistema_sur, identificador="sur/ventilador"))
        self.assertEqual([f.regla.pk for f in reglas.buscar_reglas(self.gerente, self.norte.pk)], [self.regla.pk])

    def test_regla_3_orden_por_id(self):
        """Orden estable: por id."""
        segunda = self.alta(sensor=self.hum)
        self.assertEqual([f.regla.pk for f in reglas.buscar_reglas(self.laura, self.norte.pk)], [self.regla.pk, segunda.pk])

    # ---- regla 4 (ficha) ----

    def test_regla_4_la_ficha_trae_el_historial_de_comandos_de_la_regla(self):
        """Regla 4: los comandos que generó la regla, del más reciente al más viejo; no los de otras reglas ni los manuales."""
        primero = fabricas.comando(self.ventilador, self.encender, estado="ejecutado", regla=self.regla, emitido_en=fabricas.INSTANTE_BASE)
        segundo = fabricas.comando(self.ventilador, self.apagar, estado="cancelado", regla=self.regla, emitido_en=fabricas.INSTANTE_BASE.replace(hour=15))
        fabricas.comando(self.ventilador, self.encender, estado="ejecutado", emitido_en=fabricas.INSTANTE_BASE.replace(hour=18))
        ficha = reglas.ficha_de_regla(self.laura, self.regla.pk)
        self.assertEqual([c.pk for c in ficha.comandos], [segundo.pk, primero.pk])
        self.assertEqual(ficha.fila.regla.pk, self.regla.pk)

    def test_regla_4_la_ficha_de_una_regla_inactiva_tambien_se_ve(self):
        """Regla 4 y «Lo que difiere del prototipo»: las dadas de baja se consultan."""
        ReglaActuacion.objects.filter(pk=self.regla.pk).update(estado_regla="inactiva")
        self.assertEqual(reglas.ficha_de_regla(self.laura, self.regla.pk).fila.regla.estado_regla, "inactiva")

    # ---- regla 5 (acciones) ----

    def test_regla_5_quien_opera_ve_modificar_y_baja_y_quien_solo_consulta_ninguna(self):
        """Regla 5 y D-30: el Agrónomo a cargo, las acciones de una regla activa; el Gerente con Agrónomo activo, ninguna; sin Agrónomo, sí."""
        self.assertEqual(reglas.acciones_permitidas(self.laura, self.regla), {"modificar", "baja"})
        self.assertEqual(reglas.acciones_permitidas(self.gerente, self.regla), frozenset())
        self.norte.agronomo = None
        self.norte.save()
        self.assertEqual(reglas.acciones_permitidas(self.gerente, self.regla), {"modificar", "baja"})

    def test_regla_5_una_regla_inactiva_solo_ofrece_reactivar_y_con_el_sistema_dado_de_baja_nada(self):
        """Regla 6 de MOD y D-30: «Reactivar» como única acción; si el sistema está dado de baja, ninguna (no llevaría a un 403 ni a un error)."""
        ReglaActuacion.objects.filter(pk=self.regla.pk).update(estado_regla="inactiva")
        self.regla.refresh_from_db()
        self.assertEqual(reglas.acciones_permitidas(self.laura, self.regla), {"reactivar"})
        self.sistema.estado_sistema = "inactivo"
        self.sistema.save()
        self.assertEqual(reglas.acciones_permitidas(self.laura, self.regla), frozenset())

    # ---- rendimiento ----

    def test_la_lista_no_hace_consultas_por_fila(self):
        """Sin consultas por fila: las consultas de la lista no crecen con la cantidad de reglas."""
        with CaptureQueriesContext(connection) as una:
            reglas.buscar_reglas(self.laura, self.norte.pk)
        for sensor in (self.hum, fabricas.sensor(self.sistema, "norte/luz", "intensidad_luz")):
            self.alta(sensor=sensor)
            fabricas.comando(self.ventana, self.fijar, estado="ejecutado", regla=ReglaActuacion.objects.last())
        with CaptureQueriesContext(connection) as tres:
            reglas.buscar_reglas(self.laura, self.norte.pk)
        self.assertEqual(len(tres), len(una))
