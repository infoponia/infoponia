# Pruebas de la lectura del ciclo (INV-03, paso 3): `inventario/servicios/ciclos.py` (docs/api/variedades.md, «Lectura (ciclos.py)»).
# Las etapas salen en el orden del catálogo (`TipoEtapa.puesto_global`), la duración del ciclo es la suma de sus etapas (MD-70, nunca se
# guarda) y la cosecha estimada llega al entrar en Maduración (regla 5 de PROD-ALT-VAR). Una consulta por tabla para toda la lista.

from django.test import TestCase

from inventario.tests.fabricas import ConDatosDeInventario, perezoso, variedad_con_semilla
from maestros.models import Ciclo, EtapaProductiva
from maestros.tests.fabricas import crear_cultivo, crear_variedad, tipo_etapa

ciclos = perezoso("inventario.servicios.ciclos")

COMPLETO = [("germinacion", 5), ("crecimiento", 10), ("floracion", 7), ("fructificacion", 8), ("maduracion", 20)]


class EtapasDeTests(ConDatosDeInventario, TestCase):
    """``etapas_de(variedad_ids)``: las etapas de cada variedad en el orden del catálogo."""

    def setUp(self):
        self.cultivo = crear_cultivo("Tomate")

    def test_api_etapas_en_el_orden_del_catalogo_aunque_se_hayan_creado_al_reves(self):
        """docs/api/variedades.md: las etapas salen por ``puesto_global`` (regla 4 de PROD-ALT-VAR), no por orden de creación."""
        variedad = crear_variedad(self.cultivo, "Cherry", perfil="frutos_pequenos")
        ciclo = Ciclo.objects.create(variedad=variedad)
        for codigo, dias in reversed(COMPLETO):
            EtapaProductiva.objects.create(ciclo=ciclo, tipo_etapa=tipo_etapa(codigo), duracion_estimada_dias=dias)
        etapas = ciclos.etapas_de([variedad.pk])[variedad.pk]
        self.assertEqual([e.codigo for e in etapas], [c for c, _ in COMPLETO])
        self.assertEqual([e.puesto_global for e in etapas], [1, 2, 3, 4, 5])

    def test_api_cada_etapa_trae_sus_datos(self):
        """docs/api/variedades.md: ``EtapaDelCiclo(etapa_id, tipo_id, codigo, nombre, puesto_global, duracion_dias)``."""
        variedad = variedad_con_semilla(self.cultivo, "Cherry", etapas=[("germinacion", 5), ("maduracion", 20)])
        germinacion, maduracion = ciclos.etapas_de([variedad.pk])[variedad.pk]
        guardada = EtapaProductiva.objects.get(ciclo__variedad=variedad, tipo_etapa__codigo="germinacion")
        self.assertEqual(germinacion.etapa_id, guardada.pk)
        self.assertEqual(germinacion.tipo_id, tipo_etapa("germinacion").pk)
        self.assertEqual((germinacion.codigo, germinacion.nombre, germinacion.duracion_dias), ("germinacion", "Germinación", 5))
        self.assertEqual((maduracion.codigo, maduracion.nombre, maduracion.duracion_dias), ("maduracion", "Maduración", 20))

    def test_api_cada_id_pedido_figura_aunque_no_tenga_etapas(self):
        """docs/api/variedades.md: todo id pedido figura en el resultado (lista vacía si no tiene etapas)."""
        variedad = crear_variedad(self.cultivo, "Sin ciclo", perfil="frutos_pequenos")
        self.assertEqual(ciclos.etapas_de([variedad.pk]), {variedad.pk: []})

    def test_api_una_sola_consulta_para_toda_la_lista(self):
        """docs/api/variedades.md: una consulta por tabla para toda la lista de ids, nunca una por variedad."""
        ids = [variedad_con_semilla(self.cultivo, f"V{n}", etapas=COMPLETO, perfil="frutos_pequenos").pk for n in range(4)]
        with self.assertNumQueries(1):
            resultado = ciclos.etapas_de(ids)
        self.assertEqual(set(resultado), set(ids))


class DuracionDelCicloTests(ConDatosDeInventario, TestCase):
    """``duracion_del_ciclo(variedad_ids)``: la suma de las duraciones (derivada, MD-70)."""

    def setUp(self):
        self.cultivo = crear_cultivo("Tomate")

    def test_regla_alt_var_5_la_duracion_es_la_suma_de_sus_etapas(self):
        """PROD-ALT-VAR regla 5: la duración del ciclo es la suma de sus etapas."""
        variedad = variedad_con_semilla(self.cultivo, "Cherry", etapas=COMPLETO, perfil="frutos_pequenos")
        self.assertEqual(ciclos.duracion_del_ciclo([variedad.pk]), {variedad.pk: 50})

    def test_regla_alt_var_5_cambiar_una_duracion_cambia_la_suma_sin_guardar_nada_mas(self):
        """MD-70: la duración del ciclo no se guarda; se recalcula de las etapas en cada llamada."""
        variedad = variedad_con_semilla(self.cultivo, "Cherry", etapas=[("germinacion", 5), ("maduracion", 20)])
        EtapaProductiva.objects.filter(ciclo__variedad=variedad, tipo_etapa__codigo="germinacion").update(duracion_estimada_dias=9)
        self.assertEqual(ciclos.duracion_del_ciclo([variedad.pk])[variedad.pk], 29)

    def test_api_una_variedad_sin_etapas_dura_cero_y_todo_id_figura(self):
        """docs/api/variedades.md: todo id pedido figura en el resultado."""
        variedad = crear_variedad(self.cultivo, "Sin ciclo", perfil="frutos_pequenos")
        self.assertEqual(ciclos.duracion_del_ciclo([variedad.pk]), {variedad.pk: 0})

    def test_api_una_sola_consulta_para_toda_la_lista(self):
        """docs/api/variedades.md: una consulta para toda la lista de ids."""
        ids = [variedad_con_semilla(self.cultivo, f"V{n}", etapas=COMPLETO, perfil="frutos_pequenos").pk for n in range(4)]
        with self.assertNumQueries(1):
            ciclos.duracion_del_ciclo(ids)


class DiasHastaMaduracionTests(ConDatosDeInventario, TestCase):
    """``dias_hasta_maduracion(variedad_ids)``: la suma de las etapas ANTERIORES a Maduración (la cosecha estimada)."""

    def setUp(self):
        self.cultivo = crear_cultivo("Tomate")

    def test_regla_alt_var_5_con_etapas_intermedias_suma_todas_las_anteriores_a_maduracion(self):
        """PROD-ALT-VAR regla 5: la cosecha estimada llega al entrar en Maduración, a los días que suman las etapas anteriores."""
        variedad = variedad_con_semilla(self.cultivo, "Cherry", etapas=COMPLETO, perfil="frutos_pequenos")
        self.assertEqual(ciclos.dias_hasta_maduracion([variedad.pk]), {variedad.pk: 30})

    def test_regla_alt_var_5_sin_etapas_intermedias_es_la_germinacion(self):
        """PROD-ALT-VAR regla 5: con solo Germinación y Maduración, son los días de la Germinación."""
        variedad = variedad_con_semilla(self.cultivo, "Cherry", etapas=[("germinacion", 7), ("maduracion", 30)])
        self.assertEqual(ciclos.dias_hasta_maduracion([variedad.pk]), {variedad.pk: 7})

    def test_regla_alt_var_5_la_duracion_de_maduracion_no_cuenta(self):
        """PROD-ALT-VAR regla 5: la Maduración misma no se suma; cambiar su duración no mueve la cosecha estimada."""
        variedad = variedad_con_semilla(self.cultivo, "Cherry", etapas=[("germinacion", 7), ("maduracion", 30)])
        EtapaProductiva.objects.filter(ciclo__variedad=variedad, tipo_etapa__codigo="maduracion").update(duracion_estimada_dias=90)
        self.assertEqual(ciclos.dias_hasta_maduracion([variedad.pk])[variedad.pk], 7)

    def test_api_una_sola_consulta_para_toda_la_lista(self):
        """docs/api/variedades.md: una consulta para toda la lista de ids."""
        ids = [variedad_con_semilla(self.cultivo, f"V{n}", etapas=COMPLETO, perfil="frutos_pequenos").pk for n in range(4)]
        with self.assertNumQueries(1):
            resultado = ciclos.dias_hasta_maduracion(ids)
        self.assertEqual(set(resultado.values()), {30})


class TiposDeEtapaDeTests(ConDatosDeInventario, TestCase):
    """``tipos_de_etapa_de(variedad)``: solo los tipos incluidos, en orden (los usa PRD-01 para pedir un sector por etapa)."""

    def test_api_solo_los_tipos_incluidos_y_en_orden(self):
        """docs/api/variedades.md: solo los tipos incluidos en el ciclo, en el orden del catálogo."""
        variedad = variedad_con_semilla(
            crear_cultivo("Tomate"), "Cherry", etapas=[("maduracion", 20), ("floracion", 7), ("germinacion", 5)], perfil="frutos_pequenos"
        )
        tipos = ciclos.tipos_de_etapa_de(variedad)
        self.assertEqual([t.codigo for t in tipos], ["germinacion", "floracion", "maduracion"])
        self.assertEqual([t.pk for t in tipos], [tipo_etapa(c).pk for c in ("germinacion", "floracion", "maduracion")])
