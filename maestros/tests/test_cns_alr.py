# Pruebas de MAE-02c (CU-46, «Consultar Alerta»): el servicio de consulta (paso 1) y, más abajo, los datos del detalle (paso 2) y las
# vistas (paso 3). Fuente: docs/casos_de_uso/maestros/alertas.md (reglas R1 a R9), modelo de dominio (ficha ``Alerta``, regla 1 de 8.9
# y regla 7 de 8.18), D-28, D-41, D-42 y D-43, y MD-109 (la severidad la define el tipo y se guarda con la alerta).

from datetime import timedelta

from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.menu import menu_de
from core.models import RegistroAuditoria, Usuario
from core.tests.fabricas import CLAVE, crear_administrador, crear_capataz, crear_gerente
from maestros.models import Alerta
from maestros.servicios import alertas as api
from maestros.tests.fabricas import (
    ConGeoref,
    crear_agronomo,
    crear_alerta,
    crear_invernadero,
    crear_tecnico,
    crear_vendedor,
    tipo_de_alerta_de_prueba,
    tipo_falso,
)

CRITICA = Alerta.Severidad.CRITICA
ADVERTENCIA = Alerta.Severidad.ADVERTENCIA
INFORMATIVA = Alerta.Severidad.INFORMATIVA


def ids(alertas):
    """Los ids de una lista de alertas, en el mismo orden."""
    return [alerta.pk for alerta in alertas]


class CnsAlrServicioTests(ConGeoref, TestCase):
    """``consultar_alertas`` y ``filtros_de_alertas`` (CU-46, R1 a R5; paso 1 de MAE-02c)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.sur = crear_invernadero("Sur", agronomo=self.agronomo)
        self.norte = crear_invernadero("Norte")

    # ---- R1 y R2: quién recibe y alcance (``Alerta.objects.para``) ----

    def test_regla_r2_el_gerente_ve_solo_las_alertas_para_el_gerente(self):
        """R2 y D-28: el Gerente activo recibe las ``para_gerente``; una que es solo de un Agrónomo no figura."""
        suya = crear_alerta(self.sur, "sin_capataz", para_gerente=True)
        crear_alerta(self.sur, "prueba_agr", para_gerente=False, agronomo=self.agronomo)

        self.assertEqual(ids(api.consultar_alertas(self.gerente)), [suya.pk])

    def test_regla_r2_el_agronomo_ve_solo_las_suyas(self):
        """R2 y R049: el Agrónomo activo recibe las alertas de las que es destinatario y no las de otro Agrónomo."""
        suya = crear_alerta(self.sur, "prueba_agr", para_gerente=False, agronomo=self.agronomo)
        otro = crear_agronomo("otro.agronomo@infoponia.com")
        crear_alerta(self.norte, "prueba_otro", para_gerente=False, agronomo=otro)
        crear_alerta(self.sur, "sin_capataz", para_gerente=True)

        self.assertEqual(ids(api.consultar_alertas(self.agronomo)), [suya.pk])

    def test_regla_r2_un_agronomo_sin_invernadero_a_cargo_no_ve_ninguna(self):
        """R2: un Agrónomo sin invernaderos a cargo no es destinatario de nada."""
        crear_alerta(self.sur, "sin_capataz", para_gerente=True)
        sin_invernadero = crear_agronomo("sin.invernadero@infoponia.com")

        self.assertEqual(list(api.consultar_alertas(sin_invernadero)), [])

    def test_regla_r1_los_otros_roles_no_reciben_alertas(self):
        """R1 y regla 1 de 8.9: el Capataz, el Vendedor, el Técnico y el Administrador reciben notificaciones, no alertas."""
        crear_alerta(self.sur, "sin_capataz", para_gerente=True, agronomo=self.agronomo)
        cuentas = {
            "capataz": crear_capataz(),
            "vendedor": crear_vendedor(),
            "tecnico": crear_tecnico(),
            "administrador": crear_administrador(),
        }

        for rol, cuenta in cuentas.items():
            with self.subTest(rol=rol):
                self.assertEqual(list(api.consultar_alertas(cuenta)), [])

    def test_regla_r2_una_cuenta_inactiva_o_ninguna_no_ve_ninguna(self):
        """R2: una cuenta inactiva (de Gerente o de Agrónomo) o ``None`` no recibe alertas."""
        crear_alerta(self.sur, "sin_capataz", para_gerente=True, agronomo=self.agronomo)
        gerente_inactivo = crear_gerente("gerente.anterior@infoponia.com", activo=False)
        agronomo_inactivo = crear_agronomo("agronomo.inactivo@infoponia.com", activo=False)

        for cuenta in (gerente_inactivo, agronomo_inactivo, None):
            with self.subTest(cuenta=cuenta):
                self.assertEqual(list(api.consultar_alertas(cuenta)), [])

    # ---- R3: solo las activas ----

    def test_regla_r3_una_alerta_resuelta_no_figura(self):
        """R3: el listado trae las alertas con ``estado_alerta = activa``; una resuelta (leída o no) no figura."""
        activa = crear_alerta(self.sur, "sin_capataz")
        crear_alerta(self.sur, "sin_vendedor", resuelta=True)

        self.assertEqual(ids(api.consultar_alertas(self.gerente)), [activa.pk])

    def test_regla_r3_una_alerta_de_un_invernadero_inactivo_figura(self):
        """R3 solo habla del estado de la alerta: la consulta no agrega un filtro por el estado del invernadero (``para``
        tampoco lo hace). Una alerta activa de un invernadero inactivo figura. Anotado en «Cierre» para temas abiertos."""
        inactivo = crear_invernadero("Viejo", activo=False)
        alerta = crear_alerta(inactivo, "sin_capataz")

        self.assertEqual(ids(api.consultar_alertas(self.gerente)), [alerta.pk])

    # ---- R5: filtros ----

    def test_regla_r5_filtra_por_invernadero(self):
        """R5: con ``invernadero_id`` solo quedan las alertas de ese invernadero."""
        del_sur = crear_alerta(self.sur, "sin_capataz")
        crear_alerta(self.norte, "sin_capataz")

        self.assertEqual(ids(api.consultar_alertas(self.gerente, invernadero_id=self.sur.pk)), [del_sur.pk])

    def test_regla_r5_filtra_por_tipo(self):
        """R5: con ``tipo`` (el código) solo quedan las alertas de ese tipo."""
        capataz = crear_alerta(self.sur, "sin_capataz")
        crear_alerta(self.sur, "sin_vendedor")

        self.assertEqual(ids(api.consultar_alertas(self.gerente, tipo="sin_capataz")), [capataz.pk])

    def test_regla_r5_filtra_por_invernadero_y_por_tipo_a_la_vez(self):
        """R5: los dos filtros se combinan: hay que cumplir los dos."""
        buscada = crear_alerta(self.sur, "sin_capataz")
        crear_alerta(self.sur, "sin_vendedor")
        crear_alerta(self.norte, "sin_capataz")

        resultado = api.consultar_alertas(self.gerente, invernadero_id=self.sur.pk, tipo="sin_capataz")

        self.assertEqual(ids(resultado), [buscada.pk])

    def test_regla_r5_un_filtro_vacio_es_como_no_filtrar(self):
        """R5: ``None`` y el texto vacío (el formulario GET manda ``?invernadero=&tipo=``) no filtran."""
        a = crear_alerta(self.sur, "sin_capataz")
        b = crear_alerta(self.norte, "sin_vendedor")

        for filtros in ({}, {"invernadero_id": None, "tipo": None}, {"invernadero_id": "", "tipo": ""}):
            with self.subTest(filtros=filtros):
                self.assertCountEqual(ids(api.consultar_alertas(self.gerente, **filtros)), [a.pk, b.pk])

    def test_regla_r5_un_invernadero_o_un_tipo_ajeno_da_lista_vacia_sin_error(self):
        """R5 y D-28: un invernadero o un tipo que no figura entre las alertas del actor da una lista vacía, sin error y sin
        revelar si existe: el Agrónomo filtra por el invernadero de otro, por un id que no existe y por un tipo desconocido."""
        crear_alerta(self.sur, "prueba_agr", para_gerente=False, agronomo=self.agronomo)
        crear_alerta(self.norte, "sin_capataz", para_gerente=True)

        casos = {
            "invernadero ajeno": {"invernadero_id": self.norte.pk},
            "invernadero inexistente": {"invernadero_id": 999999},
            "tipo ajeno": {"tipo": "sin_capataz"},
            "tipo inexistente": {"tipo": "no_existe"},
        }
        for nombre, filtros in casos.items():
            with self.subTest(caso=nombre):
                self.assertEqual(list(api.consultar_alertas(self.agronomo, **filtros)), [])

    # ---- R4: orden y severidad ----

    def test_regla_r4_ordena_por_severidad_y_dentro_de_cada_nivel_la_mas_reciente_primero(self):
        """R4: crítica, advertencia, informativa; dentro de cada nivel, de la más reciente a la más antigua."""
        ahora = timezone.now()
        tipos = [
            tipo_falso("prueba_critica", severidad=CRITICA),
            tipo_falso("prueba_info", severidad=INFORMATIVA),
        ]
        with tipo_de_alerta_de_prueba(*tipos):
            info = crear_alerta(self.sur, "prueba_info", fecha_hora_alerta=ahora - timedelta(hours=1))
            adv_vieja = crear_alerta(self.sur, "sin_capataz", fecha_hora_alerta=ahora - timedelta(hours=3))
            crit_vieja = crear_alerta(self.sur, "prueba_critica", fecha_hora_alerta=ahora - timedelta(hours=5))
            adv_nueva = crear_alerta(self.sur, "sin_vendedor", fecha_hora_alerta=ahora - timedelta(hours=2))
            crit_nueva = crear_alerta(self.sur, "prueba_critica", fecha_hora_alerta=ahora - timedelta(hours=4))

            resultado = api.consultar_alertas(self.gerente)

        self.assertEqual(
            ids(resultado), [crit_nueva.pk, crit_vieja.pk, adv_nueva.pk, adv_vieja.pk, info.pk]
        )

    def test_regla_r4_con_fechas_iguales_desempata_la_de_id_mayor(self):
        """R4: con la misma fecha y hora, queda primero la creada después (id decreciente)."""
        momento = timezone.now()
        primera = crear_alerta(self.sur, "sin_capataz", fecha_hora_alerta=momento)
        segunda = crear_alerta(self.sur, "sin_vendedor", fecha_hora_alerta=momento)
        tercera = crear_alerta(self.sur, "sin_tecnico", fecha_hora_alerta=momento)

        self.assertEqual(ids(api.consultar_alertas(self.gerente)), [tercera.pk, segunda.pk, primera.pk])

    def test_md109_la_severidad_sale_del_tipo_registrado_y_no_de_la_alerta(self):
        """MD-109 y D-42 (misma regla que ``items_de_campana``): manda el tipo aunque la alerta guardara otra severidad."""
        with tipo_de_alerta_de_prueba(tipo_falso("prueba_critica", severidad=CRITICA)):
            crear_alerta(self.sur, "prueba_critica", nivel_severidad=INFORMATIVA)
            (alerta,) = api.consultar_alertas(self.gerente)

        self.assertEqual(alerta.severidad, CRITICA)

    def test_md109_un_tipo_no_registrado_usa_la_severidad_guardada_y_su_codigo_como_nombre(self):
        """MD-109: si el código ya no está registrado, no se rompe: severidad guardada con la alerta y, como nombre del
        tipo, el código (decidido al aprobar el plan de MAE-02c)."""
        crear_alerta(self.sur, "tipo_que_ya_no_existe", nivel_severidad=CRITICA)

        (alerta,) = api.consultar_alertas(self.gerente)

        self.assertEqual(alerta.severidad, CRITICA)
        self.assertEqual(alerta.nombre_tipo, "tipo_que_ya_no_existe")

    def test_regla_r6_un_tipo_registrado_muestra_su_nombre(self):
        """R6: el nombre del tipo es el del tipo registrado, no su código."""
        crear_alerta(self.sur, "sin_capataz")

        (alerta,) = api.consultar_alertas(self.gerente)

        self.assertEqual(alerta.nombre_tipo, "Invernadero sin Capataz activo")

    # ---- Eficiencia ----

    def test_arma_la_lista_con_una_sola_consulta(self):
        """Eficiencia: el invernadero viene con ``select_related``; no hay una consulta por fila (ni para la severidad ni para
        el nombre del tipo, que salen del registro en memoria)."""
        for tipo in ("sin_capataz", "sin_vendedor", "sin_tecnico"):
            crear_alerta(self.sur, tipo)

        with self.assertNumQueries(1):
            resultado = api.consultar_alertas(self.gerente)
            for alerta in resultado:
                alerta.invernadero.nombre_invernadero
                alerta.nombre_tipo
                alerta.severidad
            self.assertEqual(len(resultado), 3)

    # ---- Postcondición ajustada de CU-46 (propuesta A) ----

    def test_post_consultar_no_cambia_nada_ni_marca_leidas(self):
        """Postcondición de CU-46 con la propuesta A: el listado y la búsqueda no cambian nada (solo abrir el detalle marca
        «leída», regla 7 de 8.18)."""
        alerta = crear_alerta(self.sur, "sin_capataz")

        api.consultar_alertas(self.gerente)
        api.consultar_alertas(self.gerente, invernadero_id=self.sur.pk, tipo="sin_capataz")
        api.filtros_de_alertas(self.gerente)

        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.NO_LEIDA)
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.ACTIVA)

    # ---- R5: las opciones de los filtros ----

    def test_regla_r5_los_filtros_ofrecen_solo_invernaderos_y_tipos_de_las_alertas_activas_del_actor(self):
        """R5: las opciones son los invernaderos y los tipos de las alertas activas del actor, no todos los invernaderos ni
        todos los tipos: sin repetir, y sin los de las resueltas ni los de las alertas de otro destinatario."""
        crear_alerta(self.sur, "sin_capataz")
        crear_alerta(self.sur, "sin_vendedor")  # el mismo invernadero: no se repite
        crear_alerta(self.sur, "sin_tecnico", resuelta=True)  # resuelta: su tipo no se ofrece
        otro = crear_invernadero("Este")
        crear_alerta(otro, "prueba_solo_agr", para_gerente=False, agronomo=self.agronomo)  # no es del Gerente

        filtros = api.filtros_de_alertas(self.gerente)

        self.assertEqual(list(filtros.invernaderos), [(self.sur.pk, "Sur")])
        self.assertEqual(
            list(filtros.tipos),
            [("sin_capataz", "Invernadero sin Capataz activo"), ("sin_vendedor", "Invernadero sin Vendedor activo")],
        )

    def test_regla_r5_los_filtros_de_un_tipo_no_registrado_usan_el_codigo_como_nombre(self):
        """MD-109: un tipo que ya no está registrado se ofrece en el filtro con su código como nombre."""
        crear_alerta(self.sur, "tipo_que_ya_no_existe")

        filtros = api.filtros_de_alertas(self.gerente)

        self.assertEqual(list(filtros.tipos), [("tipo_que_ya_no_existe", "tipo_que_ya_no_existe")])

    def test_regla_r5_los_filtros_de_quien_no_recibe_alertas_son_vacios(self):
        """R1: un rol que no recibe alertas no tiene opciones de filtro."""
        crear_alerta(self.sur, "sin_capataz")

        filtros = api.filtros_de_alertas(crear_capataz())

        self.assertEqual((list(filtros.invernaderos), list(filtros.tipos)), ([], []))

    def test_regla_r5_los_filtros_se_arman_con_dos_consultas(self):
        """Eficiencia: una consulta con ``distinct`` para los invernaderos y otra para los tipos, sin hidratar las alertas."""
        for tipo in ("sin_capataz", "sin_vendedor", "sin_tecnico"):
            crear_alerta(self.sur, tipo)

        with self.assertNumQueries(2):
            filtros = api.filtros_de_alertas(self.gerente)
            self.assertEqual(len(filtros.invernaderos), 1)
            self.assertEqual(len(filtros.tipos), 3)

    # ---- Paso 2: ``detalle_de_alerta`` (R6 y R7) ----

    def test_regla_r7_abrir_marca_leida_y_avisa_que_era_nueva(self):
        """R7 (regla 7 de 8.18, propuesta A): abrir el detalle llama a ``abrir_alerta``: la lectura pasa a «leída», y el
        detalle informa la lectura de ANTES (``era_nueva``) para mostrar «Nueva» solo en esta visita."""
        alerta = crear_alerta(self.sur, "sin_capataz")

        detalle = api.detalle_de_alerta(self.gerente, alerta.pk)

        self.assertTrue(detalle.era_nueva)
        self.assertEqual(detalle.alerta.pk, alerta.pk)
        self.assertEqual(detalle.alerta.estado_lectura_alerta, Alerta.Lectura.LEIDA)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.LEIDA)

    def test_regla_r7_una_segunda_apertura_no_falla_y_ya_no_era_nueva(self):
        """R7: abrir una alerta ya leída no falla, la deja leída y ``era_nueva`` es falso."""
        alerta = crear_alerta(self.sur, "sin_capataz")
        api.detalle_de_alerta(self.gerente, alerta.pk)

        segunda = api.detalle_de_alerta(self.gerente, alerta.pk)

        self.assertFalse(segunda.era_nueva)
        self.assertEqual(segunda.alerta.estado_lectura_alerta, Alerta.Lectura.LEIDA)

    def test_regla_r7_abrir_no_cambia_el_estado_activa_o_resuelta(self):
        """Regla 7 de 8.18: los dos estados son independientes: abrir marca «leída» pero no toca ``estado_alerta`` ni
        ``fecha_resolucion``."""
        alerta = crear_alerta(self.sur, "sin_capataz")

        api.detalle_de_alerta(self.gerente, alerta.pk)

        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.ACTIVA)
        self.assertIsNone(alerta.fecha_resolucion)

    def test_regla_r7_una_alerta_resuelta_que_el_actor_recibe_se_puede_abrir(self):
        """R7 (decisión 3 de MAE-02c): una resuelta que el usuario recibe se abre (llega por un enlace viejo) y sigue
        «resuelta»; se marca «leída»."""
        alerta = crear_alerta(self.sur, "sin_capataz", resuelta=True)

        detalle = api.detalle_de_alerta(self.gerente, alerta.pk)

        self.assertEqual(detalle.alerta.estado_alerta, Alerta.Estado.RESUELTA)
        self.assertTrue(detalle.era_nueva)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.LEIDA)
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.RESUELTA)

    def test_regla_r7_una_alerta_inexistente_da_404(self):
        """R7 y D-28: un id que no existe da ``Http404``."""
        with self.assertRaises(Http404):
            api.detalle_de_alerta(self.gerente, 999999)

    def test_regla_r7_una_alerta_ajena_da_403_y_no_cambia_nada(self):
        """R7 y D-28: una alerta que el actor no recibe da ``PermissionDenied`` y su lectura no cambia, ni para el Agrónomo
        de otro invernadero ni para un rol que no recibe alertas."""
        otro = crear_agronomo("otro.agronomo@infoponia.com")
        alerta = crear_alerta(self.sur, "prueba_agr", para_gerente=False, agronomo=self.agronomo)

        for actor in (otro, crear_capataz(), crear_administrador()):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    api.detalle_de_alerta(actor, alerta.pk)
                alerta.refresh_from_db()
                self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.NO_LEIDA)

    def test_regla_r7_abrir_no_deja_registro_de_auditoria(self):
        """R7 y SEG-14: abrir una alerta no se audita (D-41, D-43)."""
        alerta = crear_alerta(self.sur, "sin_capataz")
        antes = RegistroAuditoria.objects.count()

        api.detalle_de_alerta(self.gerente, alerta.pk)

        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_regla_r6_el_detalle_trae_el_tipo_y_la_severidad(self):
        """R6: el nombre del tipo y la severidad del tipo registrado (o la guardada, MD-109), junto con la alerta."""
        with tipo_de_alerta_de_prueba(tipo_falso("prueba_critica", severidad=CRITICA)):
            registrada = crear_alerta(self.sur, "prueba_critica", nivel_severidad=INFORMATIVA)
            viejo = crear_alerta(self.sur, "tipo_que_ya_no_existe", nivel_severidad=ADVERTENCIA)

            detalle_registrada = api.detalle_de_alerta(self.gerente, registrada.pk)
            detalle_viejo = api.detalle_de_alerta(self.gerente, viejo.pk)

        self.assertEqual((detalle_registrada.nombre_tipo, detalle_registrada.severidad), ("Tipo prueba_critica", CRITICA))
        self.assertEqual((detalle_viejo.nombre_tipo, detalle_viejo.severidad), ("tipo_que_ya_no_existe", ADVERTENCIA))

    def test_regla_r6_destinatarios_solo_el_gerente(self):
        """R6 y R1: una alerta solo del Gerente lo dice."""
        alerta = crear_alerta(self.sur, "sin_capataz", para_gerente=True, agronomo=None)

        detalle = api.detalle_de_alerta(self.gerente, alerta.pk)

        self.assertEqual(detalle.destinatarios, ["Gerente"])

    def test_regla_r6_destinatarios_solo_el_agronomo_con_su_nombre(self):
        """R6 y R1: una alerta solo del Agrónomo lo nombra con su nombre completo."""
        alerta = crear_alerta(self.sur, "prueba_agr", para_gerente=False, agronomo=self.agronomo)

        detalle = api.detalle_de_alerta(self.agronomo, alerta.pk)

        self.assertEqual(detalle.destinatarios, [f"Agrónomo: {self.agronomo.get_full_name()}"])

    def test_regla_r6_destinatarios_los_dos(self):
        """R6 y regla 2 de 8.9: una alerta del Agrónomo y del Gerente (umbral de merma) nombra a los dos, el Gerente primero."""
        alerta = crear_alerta(self.sur, "prueba_ambos", para_gerente=True, agronomo=self.agronomo)

        detalle = api.detalle_de_alerta(self.gerente, alerta.pk)

        self.assertEqual(detalle.destinatarios, ["Gerente", f"Agrónomo: {self.agronomo.get_full_name()}"])

    def test_regla_r6_el_agronomo_destinatario_es_el_de_la_alerta_aunque_el_invernadero_ya_no_tenga_uno(self):
        """R6: los destinatarios salen de la alerta (``agronomo``), no del invernadero: si el invernadero se quedó sin
        Agrónomo después, la alerta sigue nombrando al que la recibió; y si la alerta no tiene Agrónomo, no se inventa uno
        con el del invernadero."""
        sin_agronomo = crear_invernadero("Sin agrónomo")  # ``invernadero.agronomo`` es None
        con_agronomo_en_la_alerta = crear_alerta(sin_agronomo, "prueba_agr", para_gerente=True, agronomo=self.agronomo)
        solo_gerente = crear_alerta(self.sur, "sin_capataz", para_gerente=True, agronomo=None)  # el invernadero tiene uno

        detalle = api.detalle_de_alerta(self.gerente, con_agronomo_en_la_alerta.pk)
        detalle_sur = api.detalle_de_alerta(self.gerente, solo_gerente.pk)

        self.assertEqual(detalle.destinatarios, ["Gerente", f"Agrónomo: {self.agronomo.get_full_name()}"])
        self.assertEqual(detalle_sur.destinatarios, ["Gerente"])

    def test_regla_r6_el_gerente_puede_ver_la_ficha_de_cualquier_invernadero_aun_inactivo(self):
        """R6 y D-28: ``invernadero_visible`` (decide el enlace «Ver invernadero»): el Gerente consulta todos los
        invernaderos, también uno inactivo."""
        inactivo = crear_invernadero("Viejo", activo=False)
        alerta = crear_alerta(inactivo, "sin_capataz")

        detalle = api.detalle_de_alerta(self.gerente, alerta.pk)

        self.assertTrue(detalle.invernadero_visible)

    def test_regla_r6_el_agronomo_ve_la_ficha_de_su_invernadero_activo_y_no_la_del_inactivo(self):
        """R6 y D-28 (``Invernadero.objects.en_alcance_de``): el Agrónomo consulta solo los invernaderos activos a su cargo.
        Si el invernadero de la alerta se dio de baja, la alerta se abre pero sin enlace a la ficha (D-30: ningún enlace
        lleva a un 403)."""
        activa = crear_alerta(self.sur, "prueba_agr", para_gerente=False, agronomo=self.agronomo)
        inactivo = crear_invernadero("Viejo", activo=False, agronomo=self.agronomo)
        de_inactivo = crear_alerta(inactivo, "prueba_agr", para_gerente=False, agronomo=self.agronomo)

        self.assertTrue(api.detalle_de_alerta(self.agronomo, activa.pk).invernadero_visible)
        self.assertFalse(api.detalle_de_alerta(self.agronomo, de_inactivo.pk).invernadero_visible)


HTMX = {"HTTP_HX_REQUEST": "true"}


class CnsAlrVistaTests(ConGeoref, TestCase):
    """Las pantallas de CU-46: el listado ``/alertas/``, el detalle ``/alertas/<id>/`` y la entrada «Alertas» del menú
    (paso 3 de MAE-02c). Fuente: R2 a R8 de docs/casos_de_uso/maestros/alertas.md y las decisiones 1 a 3 de la tarea."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.sur = crear_invernadero("Sur", agronomo=self.agronomo)
        self.norte = crear_invernadero("Norte")
        self.lista = reverse("alertas:lista")

    def cliente_de(self, cuenta):
        cliente = Client()
        self.assertTrue(cliente.login(email=cuenta.email, password=CLAVE))
        return cliente

    def detalle(self, alerta):
        return reverse("alertas:detalle", args=[alerta.pk])

    # ---- Permisos (decisión 2 de MAE-02c, D-28) ----

    def test_regla_r1_las_rutas_son_del_gerente_y_del_agronomo(self):
        """R1 y decisión 2: el Gerente y el Agrónomo activos entran al listado y al detalle."""
        alerta = crear_alerta(self.sur, "sin_capataz", para_gerente=True, agronomo=self.agronomo)

        for cuenta in (self.gerente, self.agronomo):
            with self.subTest(rol=cuenta.rol):
                cliente = self.cliente_de(cuenta)
                self.assertEqual(cliente.get(self.lista).status_code, 200)
                self.assertEqual(cliente.get(self.detalle(alerta)).status_code, 200)

    def test_regla_r1_los_otros_roles_reciben_403_y_no_cambian_nada(self):
        """Decisión 2: un Capataz, un Vendedor, un Técnico o un Administrador reciben 403 en las dos rutas, y la alerta sigue
        «no leída»."""
        alerta = crear_alerta(self.sur, "sin_capataz", para_gerente=True, agronomo=self.agronomo)
        cuentas = (crear_capataz(), crear_vendedor(), crear_tecnico(), crear_administrador())

        for cuenta in cuentas:
            with self.subTest(rol=cuenta.rol):
                cliente = self.cliente_de(cuenta)
                self.assertEqual(cliente.get(self.lista).status_code, 403)
                self.assertEqual(cliente.get(self.detalle(alerta)).status_code, 403)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.NO_LEIDA)

    def test_sin_sesion_redirige_al_ingreso(self):
        """Sin sesión, la redirección de siempre (``LoginRequiredMiddleware``), también en el detalle."""
        alerta = crear_alerta(self.sur, "sin_capataz")

        for url in (self.lista, self.detalle(alerta)):
            with self.subTest(url=url):
                respuesta = Client().get(url)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn("iniciar-sesion", respuesta["Location"])

    # ---- Listado (R2 a R5) ----

    def test_flujo_principal_el_gerente_ve_sus_alertas_activas_y_entra_al_detalle(self):
        """Flujo principal de CU-46: el listado trae las activas con severidad, descripción, invernadero, tipo y un punto de
        «no leída», y su descripción lleva al detalle. Una resuelta no figura."""
        alerta = crear_alerta(self.sur, "sin_capataz", descripcion_alerta="Sur sin capataz")
        crear_alerta(self.norte, "sin_vendedor", resuelta=True, descripcion_alerta="Norte resuelta")

        respuesta = self.cliente_de(self.gerente).get(self.lista)

        self.assertContains(respuesta, "Sur sin capataz")
        self.assertNotContains(respuesta, "Norte resuelta")
        self.assertContains(respuesta, "Advertencia")
        self.assertContains(respuesta, "Invernadero sin Capataz activo")
        self.assertContains(respuesta, "alerta-punto")
        self.assertContains(respuesta, f'href="{self.detalle(alerta)}"')

    def test_regla_r2_el_agronomo_ve_solo_las_suyas(self):
        """R2 y D-28: el Agrónomo ve las suyas y no las del Gerente."""
        crear_alerta(self.sur, "prueba_agr", para_gerente=False, agronomo=self.agronomo, descripcion_alerta="Mía")
        crear_alerta(self.sur, "sin_capataz", para_gerente=True, descripcion_alerta="Del Gerente")

        respuesta = self.cliente_de(self.agronomo).get(self.lista)

        self.assertContains(respuesta, "Mía")
        self.assertNotContains(respuesta, "Del Gerente")

    def test_regla_r5_filtra_por_invernadero_y_por_tipo_con_get(self):
        """R5: el filtro por invernadero y por tipo del formulario GET (el respaldo sin JavaScript)."""
        crear_alerta(self.sur, "sin_capataz", descripcion_alerta="Sur capataz")
        crear_alerta(self.sur, "sin_vendedor", descripcion_alerta="Sur vendedor")
        crear_alerta(self.norte, "sin_capataz", descripcion_alerta="Norte capataz")
        cliente = self.cliente_de(self.gerente)

        por_invernadero = cliente.get(self.lista, {"invernadero": self.sur.pk})
        por_tipo = cliente.get(self.lista, {"tipo": "sin_capataz"})
        por_los_dos = cliente.get(self.lista, {"invernadero": self.sur.pk, "tipo": "sin_capataz"})

        self.assertEqual(self.descripciones(por_invernadero), {"Sur capataz", "Sur vendedor"})
        self.assertEqual(self.descripciones(por_tipo), {"Sur capataz", "Norte capataz"})
        self.assertEqual(self.descripciones(por_los_dos), {"Sur capataz"})

    def descripciones(self, respuesta):
        """Cuáles de las descripciones de prueba aparecen en la respuesta."""
        todas = ("Sur capataz", "Sur vendedor", "Norte capataz")
        return {texto for texto in todas if texto in respuesta.content.decode()}

    def test_regla_r5_la_pagina_completa_ofrece_solo_invernaderos_y_tipos_con_alertas_y_conserva_la_eleccion(self):
        """R5: las opciones son las de las alertas activas del usuario (no «Norte», que no tiene), y lo elegido queda
        seleccionado."""
        crear_alerta(self.sur, "sin_capataz")

        respuesta = self.cliente_de(self.gerente).get(self.lista, {"invernadero": self.sur.pk, "tipo": "sin_capataz"})

        contenido = respuesta.content.decode()
        self.assertIn(f'<option value="{self.sur.pk}" selected>Sur</option>', contenido)
        self.assertIn('<option value="sin_capataz" selected>Invernadero sin Capataz activo</option>', contenido)
        self.assertNotIn("Norte", contenido)
        self.assertIn("Filtrar", contenido)

    def test_regla_r8_con_htmx_el_filtro_devuelve_solo_la_tabla(self):
        """R8: con ``HX-Request`` la respuesta es solo la tabla (sin el marco ni el formulario); sin él, la página completa."""
        crear_alerta(self.sur, "sin_capataz", descripcion_alerta="Sur capataz")
        cliente = self.cliente_de(self.gerente)

        parcial = cliente.get(self.lista, {"invernadero": self.sur.pk}, **HTMX)
        completa = cliente.get(self.lista, {"invernadero": self.sur.pk})

        self.assertContains(parcial, "Sur capataz")
        self.assertNotContains(parcial, "<html")
        self.assertNotContains(parcial, 'name="invernadero"')
        self.assertContains(completa, "<html")
        self.assertContains(completa, 'name="invernadero"')
        self.assertIn("HX-Request", parcial["Vary"])

    def test_regla_r5_un_filtro_vacio_no_filtra(self):
        """R5: el formulario GET manda ``?invernadero=&tipo=`` cuando no se elige nada: no filtra."""
        crear_alerta(self.sur, "sin_capataz", descripcion_alerta="Sur capataz")
        crear_alerta(self.norte, "sin_vendedor", descripcion_alerta="Norte vendedor")

        respuesta = self.cliente_de(self.gerente).get(self.lista + "?invernadero=&tipo=")

        self.assertContains(respuesta, "Sur capataz")
        self.assertContains(respuesta, "Norte vendedor")

    def test_regla_r5_un_invernadero_no_numerico_da_lista_vacia_sin_error(self):
        """R5: ``?invernadero=abc`` (o un número que no cabe en la base) no rompe: lista vacía con el mensaje del filtro."""
        crear_alerta(self.sur, "sin_capataz")
        cliente = self.cliente_de(self.gerente)

        for valor in ("abc", "1.5", "-3", "0", "9" * 30):
            with self.subTest(invernadero=valor):
                respuesta = cliente.get(self.lista, {"invernadero": valor})
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, "Ninguna alerta activa coincide con el filtro.")

    def test_regla_r3_los_mensajes_de_lista_vacia(self):
        """Sin alertas: «No hay alertas activas.»; con un filtro que no coincide: «Ninguna alerta activa coincide con el
        filtro.»."""
        cliente = self.cliente_de(self.gerente)
        sin_alertas = cliente.get(self.lista)
        crear_alerta(self.sur, "sin_capataz")
        sin_coincidencias = cliente.get(self.lista, {"invernadero": self.norte.pk})

        self.assertContains(sin_alertas, "No hay alertas activas.")
        self.assertNotContains(sin_alertas, "coincide con el filtro")
        self.assertContains(sin_coincidencias, "Ninguna alerta activa coincide con el filtro.")

    def test_regla_r5_un_invernadero_ajeno_no_revela_nada(self):
        """R5 y D-28: el Agrónomo que filtra por el invernadero de otro ve lo mismo que con un filtro sin coincidencias."""
        crear_alerta(self.sur, "prueba_agr", para_gerente=False, agronomo=self.agronomo)
        crear_alerta(self.norte, "sin_capataz", descripcion_alerta="Del Gerente")

        respuesta = self.cliente_de(self.agronomo).get(self.lista, {"invernadero": self.norte.pk})

        self.assertContains(respuesta, "Ninguna alerta activa coincide con el filtro.")
        self.assertNotContains(respuesta, "Del Gerente")

    def test_md109_un_tipo_ya_no_registrado_no_rompe_el_listado(self):
        """MD-109: una alerta de un código que ya no está registrado se muestra con su código y su severidad guardada."""
        crear_alerta(self.sur, "tipo_que_ya_no_existe", nivel_severidad=Alerta.Severidad.CRITICA)

        respuesta = self.cliente_de(self.gerente).get(self.lista)

        self.assertContains(respuesta, "tipo_que_ya_no_existe")
        self.assertContains(respuesta, "Crítica")

    # ---- Marca de lectura (decisión 1, propuesta A) ----

    def test_decision_1_el_listado_no_marca_nada_como_leido(self):
        """Decisión 1 y postcondición ajustada: listar y filtrar no cambia la lectura de ninguna alerta."""
        alerta = crear_alerta(self.sur, "sin_capataz")
        cliente = self.cliente_de(self.gerente)

        cliente.get(self.lista)
        cliente.get(self.lista, {"invernadero": self.sur.pk}, **HTMX)

        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.NO_LEIDA)

    def test_decision_1_el_detalle_marca_leida_y_muestra_nueva_solo_la_primera_vez(self):
        """Decisión 1 y R7: abrir el detalle marca la alerta «leída» y la sigue mostrando activa; «Nueva» solo aparece en la
        primera visita. El punto del listado desaparece."""
        alerta = crear_alerta(self.sur, "sin_capataz")
        cliente = self.cliente_de(self.gerente)

        primera = cliente.get(self.detalle(alerta))
        segunda = cliente.get(self.detalle(alerta))
        listado = cliente.get(self.lista)

        self.assertContains(primera, "Nueva")
        self.assertNotContains(segunda, "Nueva")
        self.assertNotContains(listado, "alerta-punto")
        self.assertContains(listado, alerta.descripcion_alerta)  # sigue activa
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.LEIDA)
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.ACTIVA)

    def test_decision_1_el_detalle_no_se_guarda_en_la_cache_ni_responde_a_head(self):
        """Abrir el detalle cambia la lectura: no se cachea y un HEAD (que no debería marcar nada) da 405."""
        alerta = crear_alerta(self.sur, "sin_capataz")
        cliente = self.cliente_de(self.gerente)

        self.assertEqual(cliente.head(self.detalle(alerta)).status_code, 405)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_lectura_alerta, Alerta.Lectura.NO_LEIDA)  # el HEAD no marcó nada
        self.assertIn("no-cache", cliente.get(self.detalle(alerta))["Cache-Control"])

    # ---- Detalle (R6 y R7) ----

    def test_regla_r6_el_detalle_muestra_la_informacion_completa(self):
        """R6: tipo, severidad, descripción, invernadero, fecha y hora, estado, lectura y a quién le llegó."""
        alerta = crear_alerta(
            self.sur, "sin_capataz", descripcion_alerta="Sur sin capataz", para_gerente=True, agronomo=self.agronomo
        )

        respuesta = self.cliente_de(self.gerente).get(self.detalle(alerta))

        for texto in (
            "Invernadero sin Capataz activo",
            "Advertencia",
            "Sur sin capataz",
            "Sur",
            "Activa",
            "Nueva",
            "Gerente, Agrónomo: Nombre Apellido",
            timezone.localtime(alerta.fecha_hora_alerta).strftime("%d/%m/%Y"),
        ):
            with self.subTest(texto=texto):
                self.assertContains(respuesta, texto)
        self.assertContains(respuesta, "Volver a alertas")

    def test_decision_3_una_alerta_resuelta_se_abre_y_dice_resuelta(self):
        """Decisión 3: el detalle abre una resuelta que el usuario recibe (enlace viejo) y la muestra como «Resuelta»; el
        listado no la trae."""
        alerta = crear_alerta(self.sur, "sin_capataz", resuelta=True, descripcion_alerta="Ya resuelta")
        cliente = self.cliente_de(self.gerente)

        detalle = cliente.get(self.detalle(alerta))

        self.assertContains(detalle, "Resuelta")
        self.assertNotContains(detalle, "Activa")
        self.assertNotContains(cliente.get(self.lista), "Ya resuelta")

    def test_regla_r7_una_alerta_inexistente_da_404_y_una_ajena_403(self):
        """R7 y D-28: 404 si el id no existe y 403 si la alerta es de otro destinatario, sin cambiar nada."""
        ajena = crear_alerta(self.norte, "sin_capataz", para_gerente=True)
        cliente = self.cliente_de(self.agronomo)

        self.assertEqual(cliente.get(reverse("alertas:detalle", args=[999999])).status_code, 404)
        self.assertEqual(cliente.get(self.detalle(ajena)).status_code, 403)
        ajena.refresh_from_db()
        self.assertEqual(ajena.estado_lectura_alerta, Alerta.Lectura.NO_LEIDA)

    def test_regla_r6_ver_invernadero_solo_si_el_usuario_tiene_acceso_a_la_ficha(self):
        """R6 y D-30: el enlace «Ver invernadero» aparece si la ficha es accesible; si no (un invernadero inactivo, para el
        Agrónomo), no hay enlace: ningún enlace lleva a un 403."""
        activa = crear_alerta(self.sur, "prueba_agr", para_gerente=False, agronomo=self.agronomo)
        inactivo = crear_invernadero("Viejo", activo=False, agronomo=self.agronomo)
        de_inactivo = crear_alerta(inactivo, "prueba_agr", para_gerente=False, agronomo=self.agronomo)
        cliente = self.cliente_de(self.agronomo)

        con_enlace = cliente.get(self.detalle(activa))
        sin_enlace = cliente.get(self.detalle(de_inactivo))

        self.assertContains(con_enlace, reverse("maestros:invernadero", args=[self.sur.pk]))
        self.assertContains(con_enlace, "Ver invernadero")
        self.assertEqual(sin_enlace.status_code, 200)
        self.assertNotContains(sin_enlace, "Ver invernadero")

    # ---- Menú ----

    def test_la_entrada_alertas_es_del_gerente_y_del_agronomo(self):
        """Entrada «Alertas» del menú: la ven el Gerente y el Agrónomo; el Vendedor y el Administrador (que tienen menú
        lateral) no. El Capataz y el Técnico usan el marco de celular, sin menú."""
        enlace = f'href="{self.lista}"'
        inicio = reverse("core:inicio")

        for cuenta in (self.gerente, self.agronomo):
            with self.subTest(rol=cuenta.rol):
                self.assertContains(self.cliente_de(cuenta).get(inicio), enlace)
        self.assertNotContains(self.cliente_de(crear_vendedor()).get(inicio), enlace)
        self.assertNotContains(self.cliente_de(crear_administrador()).get(reverse("core:usuarios")), enlace)

    def test_registrar_la_entrada_dos_veces_no_la_duplica(self):
        """``ready()`` puede correr más de una vez: la entrada «Alertas» no se repite en el menú de ningún rol."""
        apps.get_app_config("maestros").ready()

        for rol in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO):
            with self.subTest(rol=rol):
                textos = [texto for texto, _, _ in menu_de(rol)]
                self.assertEqual(textos.count("Alertas"), 1)
        self.assertEqual([t for t, _, _ in menu_de(Usuario.Rol.GERENTE)][:3], ["Panel de control", "Producción", "Alertas"])
