# Pruebas de IOT-ENT-INF, parte del anuncio de equipos (IOT-03; extensión 1c y postcondiciones r y s; «El anuncio» de
# docs/casos_de_uso/iot/entregar_informacion.md; docs/api/nodo/mensajes.md, sección 4). Se escribieron ANTES que el servicio (`.claude/rules/pruebas.md`).
#
# Servicio que se prueba (iot/servicios/anuncios.py):
#   registrar_anuncio(sistema_id, equipos, ahora) -> ResultadoDeAnuncio(equipos, actuadores, sin_registrar)
#     ``equipos`` son ``EquipoRecibido`` (ya con la forma verificada por la traducción); ``actuadores`` es una lista de ``ActuadorAnunciado(identificador,
#     compatibilidad, acciones_incompatibles)`` por identificador; ``sin_registrar`` son los identificadores anunciados sin equipo vigente.

from datetime import datetime, timezone

from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.api.traduccion import EquipoRecibido
from iot.models import Actuador, EquipoAnunciado
from iot.servicios.hardware import identificadores_anunciados_libres
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

anuncios = perezoso("iot.servicios.anuncios")
nodo = perezoso("iot.servicios.nodo")

AHORA = datetime(2026, 11, 21, 17, 5, 0, tzinfo=timezone.utc)
TIPO = "iot_configuracion_incompatible"


def sensor_anunciado(identificador):
    return EquipoRecibido(identificador, "sensor", ())


def actuador_anunciado(identificador, *comandos):
    return EquipoRecibido(identificador, "actuador", tuple(comandos))


class IotEntInfAnuncioServicioTests(fabricas.ConCatalogoIot, TestCase):
    """El nodo anuncia sus equipos y los comandos que soporta cada actuador; InfoPonia los registra y recalcula la compatibilidad."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.tipo_ventilador = fabricas.tipo_actuador("Ventilador de prueba", acciones=[("Encender", "ENCENDER"), ("Apagar", "APAGAR")])
        self.tipo_ventana = fabricas.tipo_actuador(
            "Ventana de prueba", acciones=[("Abrir", "ABRIR"), ("Cerrar", "CERRAR"), ("Fijar posición", "FIJAR_POSICION", 0, 100, "%")]
        )
        self.ventilador = fabricas.actuador(self.sistema, self.tipo_ventilador, "norte/sectorA/ventilador")
        self.ventana = fabricas.actuador(self.sistema, self.tipo_ventana, "norte/sectorA/ventana")

    def anunciar(self, *equipos, ahora=AHORA):
        return anuncios.registrar_anuncio(self.sistema.pk, list(equipos), ahora)

    def completo(self):
        return self.anunciar(
            sensor_anunciado("norte/sectorA/temperatura"),
            actuador_anunciado("norte/sectorA/ventilador", "ENCENDER", "APAGAR", "FIJAR_NIVEL"),
            actuador_anunciado("norte/sectorA/ventana", "ABRIR", "CERRAR"),
            sensor_anunciado("norte/sectorB/co2"),
        )

    def auditorias(self):
        return RegistroAuditoria.objects.filter(accion="entrega_informacion_iot")

    def test_post_r_quedan_registrados_los_equipos_anunciados_con_sus_comandos(self):
        """Postcondición r: los equipos anunciados quedan con su identificador, su clase, la hora del anuncio y, en los actuadores, sus comandos del catálogo."""
        self.completo()
        self.assertEqual(EquipoAnunciado.objects.filter(sistema=self.sistema).count(), 4)
        ventilador = EquipoAnunciado.objects.get(identificador_equipo="norte/sectorA/ventilador")
        self.assertEqual((ventilador.clase, ventilador.anunciado_en), ("actuador", AHORA))
        self.assertEqual(sorted(ventilador.comandos.values_list("codigo", flat=True)), ["APAGAR", "ENCENDER", "FIJAR_NIVEL"])
        self.assertEqual(EquipoAnunciado.objects.get(identificador_equipo="norte/sectorA/temperatura").comandos.count(), 0)

    def test_ext_1c_cada_anuncio_reemplaza_al_anterior(self):
        """Mensajes.md, sección 4: un equipo que deja de anunciarse deja de figurar como anunciado."""
        self.completo()
        self.anunciar(sensor_anunciado("norte/sectorA/temperatura"))
        self.assertEqual(list(EquipoAnunciado.objects.values_list("identificador_equipo", flat=True)), ["norte/sectorA/temperatura"])

    def test_post_s_un_actuador_con_todos_los_comandos_queda_compatible(self):
        """Postcondición s: el ventilador anunció ENCENDER y APAGAR: compatible, sin acciones incompatibles ni alerta."""
        self.completo()
        self.ventilador.refresh_from_db()
        self.assertEqual((self.ventilador.compatibilidad, self.ventilador.acciones_incompatibles.count()), ("compatible", 0))
        self.assertFalse(Alerta.objects.filter(tipo_alerta=TIPO, clave_estado=f"hw:{self.ventilador.pk}").exists())

    def test_post_s_un_actuador_al_que_le_falta_un_comando_queda_incompatible_con_su_alerta(self):
        """Postcondición s: la ventana no anunció FIJAR_POSICION: incompatible, con la acción «Fijar posición» marcada y la alerta «configuración incompatible»."""
        self.completo()
        self.ventana.refresh_from_db()
        self.assertEqual(self.ventana.compatibilidad, "incompatible")
        self.assertEqual([a.nombre_accion for a in self.ventana.acciones_incompatibles.all()], ["Fijar posición"])
        self.assertEqual(Alerta.objects.filter(tipo_alerta=TIPO, estado_alerta="activa").count(), 1)

    def test_post_s_un_nuevo_anuncio_con_el_comando_resuelve_la_alerta(self):
        """Postcondición s: si quedó compatible y tenía la alerta, pasó a «resuelta»."""
        self.completo()
        self.anunciar(actuador_anunciado("norte/sectorA/ventana", "ABRIR", "CERRAR", "FIJAR_POSICION"))
        self.ventana.refresh_from_db()
        self.assertEqual(self.ventana.compatibilidad, "compatible")
        self.assertFalse(Alerta.objects.filter(tipo_alerta=TIPO, estado_alerta="activa").exists())

    def test_ext_1c_un_actuador_que_deja_de_anunciarse_queda_sin_verificar_y_se_resuelve_su_alerta(self):
        """Mensajes.md, sección 4: el que no figura en el anuncio queda «sin verificar», sin acciones incompatibles, y su alerta se resuelve."""
        self.completo()
        self.anunciar(sensor_anunciado("norte/sectorA/temperatura"))
        self.ventana.refresh_from_db()
        self.assertEqual((self.ventana.compatibilidad, self.ventana.acciones_incompatibles.count()), ("sin_verificar", 0))
        self.assertFalse(Alerta.objects.filter(tipo_alerta=TIPO, estado_alerta="activa").exists())

    def test_ext_1c_el_anuncio_vacio_deja_todo_sin_verificar(self):
        """Mensajes.md, sección 4: una lista vacía es válida (el nodo no tiene equipos): todos los actuadores quedan sin verificar y no queda ningún anunciado."""
        self.completo()
        self.anunciar()
        self.assertEqual(EquipoAnunciado.objects.count(), 0)
        self.assertEqual(set(Actuador.objects.values_list("compatibilidad", flat=True)), {"sin_verificar"})

    def test_ext_1c_los_identificadores_sin_registrar_no_generan_alertas_y_se_ofrecen_en_el_alta(self):
        """Extensión 1c.4: los anunciados sin equipo registrado no generan alertas; la consulta de IOT-02 los lista (regla 14 de IOT-ALT-HDW)."""
        resultado = self.completo()
        self.assertEqual(resultado.sin_registrar, ["norte/sectorA/temperatura", "norte/sectorB/co2"])
        self.assertFalse(Alerta.objects.filter(tipo_alerta="iot_dispositivo_no_registrado").exists())
        self.assertEqual([a.identificador for a in identificadores_anunciados_libres(self.sistema)], ["norte/sectorA/temperatura", "norte/sectorB/co2"])

    def test_ext_1c_la_respuesta_lista_los_actuadores_registrados_por_identificador(self):
        """Mensajes.md, sección 4 y ejemplo `anuncio`: cada actuador registrado (no dado de baja), por identificador, con su compatibilidad y los nombres de sus
        acciones incompatibles; `equipos` es la cantidad anunciada."""
        fabricas.actuador(self.sistema, identificador="norte/sectorA/vieja", estado="inactivo")
        resultado = self.completo()
        self.assertEqual(resultado.equipos, 4)
        self.assertEqual(
            [(a.identificador, a.compatibilidad, a.acciones_incompatibles) for a in resultado.actuadores],
            [
                ("norte/sectorA/ventana", "incompatible", ["Fijar posición"]),
                ("norte/sectorA/ventilador", "compatible", []),
            ],
        )

    def test_ext_1c_el_identificador_anunciado_se_compara_sin_distinguir_mayusculas(self):
        """Mensajes.md, sección 0: la comparación del identificador no distingue mayúsculas."""
        self.anunciar(actuador_anunciado("NORTE/SECTORA/VENTILADOR", "ENCENDER", "APAGAR"))
        self.ventilador.refresh_from_db()
        self.assertEqual(self.ventilador.compatibilidad, "compatible")

    def test_ext_1c_un_equipo_dado_de_baja_se_ofrece_como_sin_registrar(self):
        """Regla 14 de IOT-ALT-HDW: un identificador anunciado que era de un equipo dado de baja (y de ninguno vigente) figura como sin registrar."""
        fabricas.sensor(self.sistema, "norte/sectorA/temp-vieja", estado="inactivo")
        resultado = self.anunciar(sensor_anunciado("norte/sectorA/temp-vieja"))
        self.assertEqual(resultado.sin_registrar, ["norte/sectorA/temp-vieja"])

    def test_ext_1c_el_anuncio_no_cambia_el_ultimo_mensaje_de_los_equipos(self):
        """«El anuncio»: no es un mensaje «sobre» un equipo: no cambia `ultimo_mensaje_en`."""
        self.completo()
        self.ventilador.refresh_from_db()
        self.assertIsNone(self.ventilador.ultimo_mensaje_en)

    def test_post_z_un_anuncio_que_cambia_la_compatibilidad_se_audita_con_una_clave_por_actuador(self):
        """Postcondición z y D-36: `datos` (mensaje `anuncio`, sin identificador, alertas generadas) y `cambios` con una clave «compatibilidad de <identificador>»
        por actuador que cambió; afectados, los actuadores y la alerta."""
        self.completo()
        [registro] = self.auditorias()
        self.assertEqual(registro.detalle["datos"]["mensaje"], "anuncio")
        self.assertIsNone(registro.detalle["datos"]["identificador"])
        self.assertEqual(len(registro.detalle["datos"]["alertas_generadas"]), 1)
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "compatibilidad de norte/sectorA/ventana": {"antes": "sin_verificar", "despues": "incompatible"},
                "compatibilidad de norte/sectorA/ventilador": {"antes": "sin_verificar", "despues": "compatible"},
            },
        )
        self.assertEqual(
            {(a["modelo"], a["id"]) for a in registro.afectados if a["modelo"] == "iot.actuador"},
            {("iot.actuador", self.ventana.pk), ("iot.actuador", self.ventilador.pk)},
        )

    def test_post_z_un_anuncio_que_no_cambia_la_compatibilidad_no_se_audita(self):
        """«Auditoría»: se audita solo si cambió la compatibilidad de algún actuador: repetir el mismo anuncio no deja registro."""
        self.completo()
        self.completo()
        self.assertEqual(self.auditorias().count(), 1)

    def test_ext_astar_un_sistema_desconectado_no_registra_el_anuncio(self):
        """Extensión *a: el anuncio se procesa entero o nada: con el sistema desconectado, `SistemaDesconectado` y no cambia nada."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        with self.assertRaises(nodo.SistemaDesconectado):
            self.completo()
        self.assertEqual(EquipoAnunciado.objects.count(), 0)
