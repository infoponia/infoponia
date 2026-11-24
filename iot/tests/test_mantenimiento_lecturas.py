# Pruebas de las cuatro lecturas de órdenes de mantenimiento de IOT-07, paso 2 (docs/casos_de_uso/iot/mantenimiento_automatico.md, «Lecturas (sin escribir, sin bloquear, sin consultas por fila)»;
# docs/modelo/produccion.md, «Listas fijas»: el orden de las órdenes). Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban, tomados del módulo dentro de cada prueba:
#   iot/servicios/hardware.py   mantenimientos_a_realizar(equipo) -> list[MantenimientoTecnico]            (ya existe, devuelve [] hasta IOT-07: ahora consulta)
#   iot/servicios/sistemas.py   ordenes_a_realizar_del_sistema(sistema) -> list[MantenimientoTecnico]      (ya existe, devuelve [] hasta IOT-07: ahora consulta)
#   iot/servicios/mantenimiento.py (NUEVO)
#       mantenimientos_del_equipo(equipo) -> list[MantenimientoTecnico]
#           todas las órdenes del equipo: primero las «a realizar» (fecha programada, prioridad —sin valor = media, aunque en un mantenimiento siempre hay—, id), después las demás por fecha de resolución,
#           de la más nueva a la más vieja (desempata el id, también de mayor a menor). Con el Técnico ya cargado (``select_related``): la ficha lo muestra.
#       mantenimientos_a_realizar_del_tecnico(tecnico) -> list[MantenimientoTecnico]
#           las «a realizar» asignadas a ese Técnico, en el orden de las órdenes (fecha programada, prioridad, id), con el invernadero (``select_related``) y los equipos (``prefetch_related``).
# Ninguna escribe, bloquea ni consulta por fila.

from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from inventario.tests.fabricas import perezoso
from iot.tests import fabricas
from iot.tests.escena_de_reglas import ConEscenaDeReglas
from maestros.tests.fabricas import crear_invernadero, crear_tecnico

hardware = perezoso("iot.servicios.hardware")
sistemas = perezoso("iot.servicios.sistemas")
mantenimiento = perezoso("iot.servicios.mantenimiento")


class LecturasDeMantenimientoBase(ConEscenaDeReglas, TestCase):
    """La escena de las reglas (Norte, su sistema, sensores y dos actuadores) más un Técnico."""

    def setUp(self):
        super().setUp()
        self.tecnico = crear_tecnico("tecnico@infoponia.com")
        self.hoy = timezone.localdate()

    def orden(self, equipos=None, **extra):
        """Una orden «a realizar» de Norte para el Técnico, con los ``equipos`` (por defecto, el ventilador)."""
        return fabricas.mantenimiento_tecnico(self.norte, self.tecnico, equipos or [self.ventilador], **extra)

    def en(self, dias):
        """Una fecha programada ``dias`` días a partir de hoy (la de creación es hoy: la base exige programada >= creación)."""
        return {"fecha_programada_orden": self.hoy + timedelta(days=dias)}

    def consultas(self, funcion):
        """Cuántas consultas hace ``funcion`` (y lo que devuelve)."""
        with CaptureQueriesContext(connection) as capturadas:
            resultado = funcion()
        return len(capturadas), resultado


class MantenimientosARealizarDelEquipoTests(LecturasDeMantenimientoBase):
    """`hardware.mantenimientos_a_realizar(equipo)`: la usan volver a activar (regla 8), la baja del equipo (precondición d) y la orden al escalar (4b.4b)."""

    def test_regla_8_sin_ordenes_devuelve_una_lista_vacia(self):
        """Sin órdenes, nada: lo que ya devolvía hasta IOT-07."""
        self.assertEqual(hardware.mantenimientos_a_realizar(self.ventilador), [])

    def test_regla_8_devuelve_las_a_realizar_que_incluyen_al_equipo_por_id(self):
        """Regla 8 de IOT-MOD-HDW y «Lecturas»: las órdenes «a realizar» que incluyen el equipo, ordenadas por `id`."""
        creada_primero = self.orden(**self.en(5))
        creada_despues = self.orden(**self.en(1))
        self.assertEqual(hardware.mantenimientos_a_realizar(self.ventilador), [creada_primero, creada_despues])

    def test_regla_8_una_orden_de_dos_equipos_cuenta_para_cada_uno(self):
        """R057 (1..*): una orden con el ventilador y la ventana cuenta para los dos."""
        orden = self.orden([self.ventilador, self.ventana])
        self.assertEqual(hardware.mantenimientos_a_realizar(self.ventilador), [orden])
        self.assertEqual(hardware.mantenimientos_a_realizar(self.ventana), [orden])

    def test_regla_8_una_cancelada_o_concretada_no_cuenta(self):
        """Solo las «a realizar»: una cancelada (o concretada) ya no impide nada ni se ofrece al volver a activar."""
        self.orden(estado="cancelada")
        self.orden(estado="concretada")
        vigente = self.orden()
        self.assertEqual(hardware.mantenimientos_a_realizar(self.ventilador), [vigente])

    def test_regla_8_una_orden_de_otro_equipo_no_cuenta(self):
        """Solo las órdenes que incluyen ESTE equipo."""
        self.orden([self.ventana])
        self.assertEqual(hardware.mantenimientos_a_realizar(self.ventilador), [])

    def test_regla_8_sin_consultas_por_fila(self):
        """«Lecturas»: una consulta para toda la lista, con 1 y con 5 órdenes (el código sale de los datos ya cargados)."""
        self.orden()
        con_una, ordenes = self.consultas(lambda: [o.codigo for o in hardware.mantenimientos_a_realizar(self.ventilador)])
        for _ in range(4):
            self.orden()
        con_cinco, ordenes = self.consultas(lambda: [o.codigo for o in hardware.mantenimientos_a_realizar(self.ventilador)])
        self.assertEqual(len(ordenes), 5)
        self.assertEqual(con_una, con_cinco)


class OrdenesARealizarDelSistemaTests(LecturasDeMantenimientoBase):
    """`sistemas.ordenes_a_realizar_del_sistema(sistema)`: la usa la baja del sistema (precondición d de IOT-BAJ-SIS)."""

    def test_regla_4_sin_ordenes_devuelve_una_lista_vacia(self):
        self.assertEqual(sistemas.ordenes_a_realizar_del_sistema(self.sistema), [])

    def test_regla_4_devuelve_las_a_realizar_de_cualquier_equipo_del_sistema_por_id(self):
        """Regla 4 de IOT-BAJ-SIS: las órdenes «a realizar» que incluyen algún equipo del sistema, por `id`."""
        de_la_ventana = self.orden([self.ventana])
        del_sensor = self.orden([self.temp])
        self.assertEqual(sistemas.ordenes_a_realizar_del_sistema(self.sistema), [de_la_ventana, del_sensor])

    def test_regla_4_una_orden_con_dos_equipos_del_sistema_cuenta_una_sola_vez(self):
        """«Sin repetir»: la unión por equipos no duplica la orden."""
        orden = self.orden([self.ventilador, self.ventana, self.temp])
        self.assertEqual(sistemas.ordenes_a_realizar_del_sistema(self.sistema), [orden])

    def test_regla_4_una_cancelada_no_cuenta(self):
        self.orden(estado="cancelada")
        self.assertEqual(sistemas.ordenes_a_realizar_del_sistema(self.sistema), [])

    def test_regla_4_una_orden_de_otro_sistema_no_cuenta(self):
        """Solo los equipos de ESTE sistema."""
        otro_invernadero = crear_invernadero("Sur", agronomo=self.laura)
        otro_sistema = fabricas.sistema(otro_invernadero)
        equipo_ajeno = fabricas.actuador(otro_sistema, self.tipo_ventilador, "sur/ventilador")
        fabricas.mantenimiento_tecnico(otro_invernadero, self.tecnico, [equipo_ajeno])
        self.assertEqual(sistemas.ordenes_a_realizar_del_sistema(self.sistema), [])

    def test_regla_4_sin_consultas_por_fila(self):
        """Una consulta para toda la lista, con 1 y con 5 órdenes."""
        self.orden()
        con_una, _ = self.consultas(lambda: [o.codigo for o in sistemas.ordenes_a_realizar_del_sistema(self.sistema)])
        for _ in range(4):
            self.orden()
        con_cinco, ordenes = self.consultas(lambda: [o.codigo for o in sistemas.ordenes_a_realizar_del_sistema(self.sistema)])
        self.assertEqual(len(ordenes), 5)
        self.assertEqual(con_una, con_cinco)


class MantenimientosDelEquipoTests(LecturasDeMantenimientoBase):
    """`mantenimiento.mantenimientos_del_equipo(equipo)`: la sección «Órdenes de mantenimiento» de la ficha (regla 6 de IOT-CNS-HDW)."""

    def test_regla_6_sin_ordenes_devuelve_una_lista_vacia(self):
        self.assertEqual(mantenimiento.mantenimientos_del_equipo(self.ventilador), [])

    def test_regla_6_primero_las_a_realizar_por_fecha_prioridad_e_id(self):
        """Las «a realizar» van primero: fecha programada (la más antigua primero), después prioridad (alta, media, baja) y después `id`."""
        tarde = self.orden(**self.en(3))
        baja = self.orden(prioridad_orden="baja", **self.en(1))
        alta = self.orden(prioridad_orden="alta", **self.en(1))
        media = self.orden(prioridad_orden="media", **self.en(1))
        otra_alta = self.orden(prioridad_orden="alta", **self.en(1))
        self.assertEqual(mantenimiento.mantenimientos_del_equipo(self.ventilador), [alta, otra_alta, media, baja, tarde])

    def test_regla_6_despues_las_demas_por_fecha_de_resolucion_de_la_mas_nueva_a_la_mas_vieja(self):
        """Las canceladas y concretadas van después, por `fecha_resolucion_orden` descendente (desempata el `id`, también descendente)."""
        vieja = self.orden(estado="cancelada", fecha_resolucion_orden=self.hoy - timedelta(days=10))
        reciente = self.orden(estado="concretada", fecha_resolucion_orden=self.hoy - timedelta(days=1))
        igual_que_la_reciente = self.orden(estado="cancelada", fecha_resolucion_orden=self.hoy - timedelta(days=1))
        vigente = self.orden(**self.en(2))
        self.assertEqual(
            mantenimiento.mantenimientos_del_equipo(self.ventilador), [vigente, igual_que_la_reciente, reciente, vieja]
        )

    def test_regla_6_solo_las_ordenes_que_incluyen_al_equipo(self):
        propia = self.orden([self.ventilador, self.ventana])
        self.orden([self.temp])
        self.assertEqual(mantenimiento.mantenimientos_del_equipo(self.ventana), [propia])

    def test_regla_6_trae_al_tecnico_cargado(self):
        """La ficha muestra el Técnico de cada orden: viene con `select_related`, sin consultas por fila."""
        self.orden()
        ordenes = mantenimiento.mantenimientos_del_equipo(self.ventilador)
        with self.assertNumQueries(0):
            self.assertEqual([o.tecnico.email for o in ordenes], ["tecnico@infoponia.com"])

    def test_regla_6_sin_consultas_por_fila(self):
        """Una consulta para toda la lista, con 1 y con 5 órdenes (mezcla de estados), leyendo lo que dibuja la ficha."""

        def leer():
            return [
                (o.codigo, o.get_tipo_mantenimiento_display(), o.get_estado_orden_display(), o.get_prioridad_orden_display(), o.tecnico.email)
                for o in mantenimiento.mantenimientos_del_equipo(self.ventilador)
            ]

        self.orden()
        con_una, _ = self.consultas(leer)
        self.orden(estado="cancelada")
        self.orden(estado="concretada")
        self.orden(**self.en(2))
        self.orden(**self.en(4))
        con_cinco, filas = self.consultas(leer)
        self.assertEqual(len(filas), 5)
        self.assertEqual(con_una, con_cinco)


class MantenimientosDelTecnicoTests(LecturasDeMantenimientoBase):
    """`mantenimiento.mantenimientos_a_realizar_del_tecnico(tecnico)`: el Inicio del Técnico y las asignaciones de su cuenta."""

    def test_regla_4_sin_ordenes_devuelve_una_lista_vacia(self):
        self.assertEqual(mantenimiento.mantenimientos_a_realizar_del_tecnico(self.tecnico), [])

    def test_regla_4_solo_las_a_realizar_de_ese_tecnico(self):
        """Las del Técnico, «a realizar»: ni las canceladas ni las concretadas ni las de otro Técnico."""
        propia = self.orden()
        self.orden(estado="cancelada")
        self.orden(estado="concretada")
        otro = crear_tecnico("otro.tecnico@infoponia.com")
        fabricas.mantenimiento_tecnico(self.norte, otro, [self.ventana])
        self.assertEqual(mantenimiento.mantenimientos_a_realizar_del_tecnico(self.tecnico), [propia])

    def test_regla_4_en_el_orden_de_las_ordenes_fecha_prioridad_id(self):
        """`docs/modelo/produccion.md`, «Listas fijas»: fecha programada (la más antigua primero), prioridad (alta, media, baja) e `id`."""
        tarde = self.orden(**self.en(3))
        baja = self.orden(prioridad_orden="baja", **self.en(1))
        alta = self.orden(prioridad_orden="alta", **self.en(1))
        self.assertEqual(mantenimiento.mantenimientos_a_realizar_del_tecnico(self.tecnico), [alta, baja, tarde])

    def test_regla_4_trae_el_invernadero_y_los_equipos_cargados(self):
        """«Con el invernadero y los equipos»: el Inicio los muestra sin consultar por orden."""
        self.orden([self.ventilador, self.ventana])
        ordenes = mantenimiento.mantenimientos_a_realizar_del_tecnico(self.tecnico)
        with self.assertNumQueries(0):
            self.assertEqual(ordenes[0].invernadero.nombre_invernadero, "Norte")
            self.assertEqual(sorted(e.identificador_equipo for e in ordenes[0].hardware.all()), ["norte/ventana", "norte/ventilador"])

    def test_regla_4_sin_consultas_por_fila(self):
        """Una cantidad fija de consultas con 1 y con 5 órdenes, leyendo invernadero y equipos de cada una."""

        def leer():
            return [
                (o.codigo, o.invernadero.nombre_invernadero, [e.identificador_equipo for e in o.hardware.all()])
                for o in mantenimiento.mantenimientos_a_realizar_del_tecnico(self.tecnico)
            ]

        self.orden()
        con_una, _ = self.consultas(leer)
        for dias in range(1, 5):
            self.orden([self.ventilador, self.ventana], **self.en(dias))
        con_cinco, filas = self.consultas(leer)
        self.assertEqual(len(filas), 5)
        self.assertEqual(con_una, con_cinco)
