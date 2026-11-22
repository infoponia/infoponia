# Pruebas de IOT-CNS-TAC · Consultar Tipo de Actuador (docs/casos_de_uso/iot/tipos_de_actuador.md, v0.3). Se escribieron ANTES que
# el servicio.
#
# Servicios que se prueban (iot/servicios/tipos_actuador.py), tomados del módulo dentro de cada prueba:
#   listar_tipos(actor) -> list[TipoActuador]   (con ``acciones_activas`` y ``cantidad_equipos`` ya cargados)
#   obtener_tipo(actor, tipo_id) -> TipoActuador
#   catalogo() -> list[dict]                    (capacidades con sus comandos y unidades)
#   acciones_permitidas(actor, tipo) -> frozenset
#     - Precondición a: actor que no es Gerente ni Agrónomo activos -> PermissionDenied.

from unittest import mock

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import Accion, TipoActuador
from iot.tests import fabricas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_tecnico, crear_vendedor

tipos = perezoso("iot.servicios.tipos_actuador")
EN_USO = "iot.servicios.tipos_actuador.acciones_en_uso"


class IotCnsTacServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondición, reglas y postcondición de IOT-CNS-TAC."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()

    # ---- precondición a y regla 1 ----

    def test_pre_a_el_gerente_y_el_agronomo_consultan(self):
        """IOT-CNS-TAC precondición a y regla 1."""
        for actor in (self.gerente, self.agronomo):
            with self.subTest(actor=actor):
                self.assertEqual(len(tipos.listar_tipos(actor)), 6)
                self.assertEqual(tipos.obtener_tipo(actor, TipoActuador.objects.first().pk).pk, TipoActuador.objects.first().pk)

    def test_pre_a_los_otros_roles_no_consultan(self):
        """IOT-CNS-TAC precondición a: el módulo da 403 a los demás roles."""
        for actor in (crear_capataz(), crear_vendedor(), crear_tecnico(), crear_administrador(), None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    tipos.listar_tipos(actor)
                with self.assertRaises(PermissionDenied):
                    tipos.obtener_tipo(actor, TipoActuador.objects.first().pk)

    def test_pre_a_una_cuenta_inactiva_no_consulta(self):
        """IOT-CNS-TAC precondición a: la cuenta tiene que estar activa."""
        self.agronomo.is_active = False
        self.agronomo.save()
        with self.assertRaises(PermissionDenied):
            tipos.listar_tipos(self.agronomo)

    def test_regla_1_se_consultan_todos_los_tipos_sin_alcance_por_invernadero(self):
        """IOT-CNS-TAC regla 1: un Agrónomo con un invernadero ve los tipos de equipos de todos, activos e inactivos."""
        crear_invernadero("Suyo", agronomo=self.agronomo)
        fabricas.tipo_actuador("Dado de baja", activo=False)
        nombres = [t.nombre_actuador for t in tipos.listar_tipos(self.agronomo)]
        self.assertEqual(len(nombres), 7)
        self.assertIn("Dado de baja", nombres)

    def test_regla_1_un_id_que_no_existe_da_404(self):
        """docs/patrones/abm.md, sección 6."""
        with self.assertRaises(Http404):
            tipos.obtener_tipo(self.gerente, 999999)

    # ---- regla 2: qué se ve ----

    def test_regla_2_los_activos_van_primero_y_despues_por_nombre(self):
        """«Cómo se aplica», «Consulta»: activos primero, después por nombre (sin distinguir mayúsculas)."""
        fabricas.tipo_actuador("abanico", activo=False)
        fabricas.tipo_actuador("Zeta")
        fabricas.tipo_actuador("alfa")
        nombres = [t.nombre_actuador for t in tipos.listar_tipos(self.gerente)]
        self.assertEqual(
            nombres, ["alfa", "Bomba", "Calefactor", "Luminaria", "Media sombra", "Ventana", "Ventilador", "Zeta", "abanico"]
        )

    def test_regla_2_de_cada_tipo_se_ven_nombre_tiempo_estado_y_codigo(self):
        """IOT-CNS-TAC regla 2 y «Consulta»: nombre, tiempo mínimo, estado y el código ``TAC-NN`` (el id con dos dígitos)."""
        tipo = fabricas.tipo_actuador("Extractor", 45, activo=False)
        visto = next(t for t in tipos.listar_tipos(self.gerente) if t.pk == tipo.pk)
        self.assertEqual((visto.nombre_actuador, visto.tiempo_minimo_entre_comandos, visto.estado), ("Extractor", 45, "inactivo"))
        self.assertEqual(visto.codigo, f"TAC-{tipo.pk:02d}")

    def test_regla_2_se_ven_las_acciones_activas_con_su_comando_capacidad_valor_unidad_y_rango(self):
        """IOT-CNS-TAC regla 2: cada acción activa con su comando y su capacidad, si requiere valor, su unidad, su mínimo y su máximo."""
        ventilador = next(t for t in tipos.listar_tipos(self.agronomo) if t.nombre_actuador == "Ventilador")
        acciones = {a.nombre_accion: a for a in ventilador.acciones_activas}
        self.assertEqual(list(acciones), ["Encender", "Apagar", "Fijar velocidad"])
        fijar = acciones["Fijar velocidad"]
        self.assertEqual((fijar.comando.codigo, fijar.comando.capacidad.nombre, fijar.requiere_valor), ("FIJAR_NIVEL", "Nivel", True))
        self.assertEqual((fijar.unidad_valor, fijar.valor_minimo, fijar.valor_maximo), ("%", 0, 100))
        self.assertFalse(acciones["Encender"].requiere_valor)

    def test_regla_2_las_acciones_inactivas_no_se_ven(self):
        """IOT-CNS-TAC regla 2: solo las activas."""
        tipo = fabricas.tipo_actuador("Extractor")
        Accion.objects.filter(tipo_actuador=tipo, nombre_accion="Apagar").update(estado="inactiva")
        visto = next(t for t in tipos.listar_tipos(self.gerente) if t.pk == tipo.pk)
        self.assertEqual([a.nombre_accion for a in visto.acciones_activas], ["Encender"])

    def test_regla_2_la_marca_en_uso_la_tiene_la_accion_usada_por_una_regla_o_un_comando_pendiente(self):
        """IOT-CNS-TAC regla 2: «en uso» sale de ``acciones_en_uso`` (se completa en IOT-05 e IOT-06; acá, con un reemplazo)."""
        tipo = fabricas.tipo_actuador("Extractor")
        encender = tipo.acciones.get(nombre_accion="Encender")
        with mock.patch(EN_USO, return_value={encender.pk: [tipos.UsoDeAccion("RGL-3", None)]}):
            visto = next(t for t in tipos.listar_tipos(self.gerente) if t.pk == tipo.pk)
        self.assertEqual({a.nombre_accion: a.en_uso for a in visto.acciones_activas}, {"Encender": True, "Apagar": False})

    def test_regla_2_hasta_iot_05_e_iot_06_ninguna_accion_esta_en_uso(self):
        """«Cómo se aplica», «Modificar»: en IOT-01, ninguna."""
        for tipo in tipos.listar_tipos(self.gerente):
            self.assertFalse(any(a.en_uso for a in tipo.acciones_activas))

    def test_regla_2_se_cuentan_los_actuadores_que_no_estan_dados_de_baja(self):
        """IOT-CNS-TAC regla 2: la cantidad de actuadores de ese tipo (no dados de baja) y la de los otros tipos queda aparte."""
        tipo = fabricas.tipo_actuador("Extractor")
        sistema = fabricas.sistema(crear_invernadero("Norte"))
        for estado in ("activo", "fuera_de_servicio", "inactivo"):
            fabricas.actuador(sistema, tipo, estado=estado)
        fabricas.actuador(sistema, fabricas.tipo_actuador("Otro"))
        cantidades = {t.nombre_actuador: t.cantidad_equipos for t in tipos.listar_tipos(self.gerente)}
        self.assertEqual((cantidades["Extractor"], cantidades["Otro"], cantidades["Bomba"]), (2, 1, 0))

    def test_regla_2_el_listado_hace_pocas_consultas(self):
        """Una consulta por cosa, no una por tipo ni por acción."""
        with self.assertNumQueries(2):
            for tipo in tipos.listar_tipos(self.gerente):
                [(a.comando.codigo, a.comando.capacidad.nombre, a.en_uso) for a in tipo.acciones_activas]

    # ---- el catálogo de capacidades (solo lectura) ----

    def test_regla_7_de_iot_alt_tac_el_catalogo_se_muestra_con_comandos_y_unidades(self):
        """IOT-ALT-TAC regla 7: capacidades con sus comandos, y de cada comando con valor su lista de unidades."""
        catalogo = tipos.catalogo()
        self.assertEqual([c["capacidad"].codigo for c in catalogo], ["encendido", "nivel", "posicion"])
        comandos = {x["comando"].codigo: x for c in catalogo for x in c["comandos"]}
        self.assertEqual(list(comandos), ["ENCENDER", "APAGAR", "FIJAR_NIVEL", "ABRIR", "CERRAR", "FIJAR_POSICION"])
        self.assertEqual([u for u, _ in comandos["FIJAR_NIVEL"]["unidades"]], ["%", "rpm", "L/min"])
        self.assertEqual([u for u, _ in comandos["FIJAR_POSICION"]["unidades"]], ["%", "°", "cm"])
        self.assertEqual(comandos["ENCENDER"]["unidades"], [])

    # ---- regla 3: quién administra ----

    def test_regla_3_el_gerente_modifica_y_da_de_baja_un_tipo_activo(self):
        """IOT-CNS-TAC regla 3: desde un tipo activo inicia IOT-MOD-TAC o IOT-BAJ-TAC."""
        tipo = TipoActuador.objects.get(nombre_actuador="Bomba")
        self.assertEqual(tipos.acciones_permitidas(self.gerente, tipo), frozenset({tipos.ACCION_MODIFICAR, tipos.ACCION_BAJA}))

    def test_regla_3_de_un_tipo_inactivo_el_gerente_solo_puede_reactivar(self):
        """IOT-CNS-TAC regla 3."""
        tipo = fabricas.tipo_actuador("Extractor", activo=False)
        self.assertEqual(tipos.acciones_permitidas(self.gerente, tipo), frozenset({tipos.ACCION_REACTIVAR}))

    def test_regla_3_el_agronomo_solo_consulta_y_no_ve_botones(self):
        """IOT-CNS-TAC regla 3 y D-30: ningún botón lleva a un 403."""
        for tipo in (TipoActuador.objects.get(nombre_actuador="Bomba"), fabricas.tipo_actuador("Extractor", activo=False)):
            self.assertEqual(tipos.acciones_permitidas(self.agronomo, tipo), frozenset())
        self.assertEqual(tipos.acciones_permitidas(None, tipo), frozenset())

    def test_regla_3_un_gerente_inactivo_no_tiene_acciones(self):
        """D-30: una cuenta inactiva no administra."""
        self.gerente.is_active = False
        self.gerente.save()
        self.assertEqual(tipos.acciones_permitidas(self.gerente, TipoActuador.objects.get(nombre_actuador="Bomba")), frozenset())

    # ---- regla 4 y postcondición a ----

    def test_regla_4_la_consulta_no_se_audita(self):
        """IOT-CNS-TAC regla 4 y SEG-14."""
        antes = RegistroAuditoria.objects.count()
        tipos.listar_tipos(self.gerente)
        tipos.obtener_tipo(self.agronomo, TipoActuador.objects.first().pk)
        tipos.catalogo()
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_post_a_la_consulta_no_cambia_nada(self):
        """IOT-CNS-TAC postcondición a: no se producen cambios en el Sistema."""
        antes = (TipoActuador.objects.count(), list(Accion.objects.values_list("id", "estado")))
        tipos.listar_tipos(self.gerente)
        self.assertEqual((TipoActuador.objects.count(), list(Accion.objects.values_list("id", "estado"))), antes)
