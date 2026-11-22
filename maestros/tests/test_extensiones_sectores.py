# Pruebas de los puntos de extensión de sectores y cultivos de MAE-03 (paso 2; docs/api/extensiones_de_maestros.md), con
# registrantes falsos (``mock.patch.object`` sobre las listas de módulo): sin registrantes dan su resultado neutro y se juntan
# los de todos los registrantes, sin quedarse con el primero.

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from maestros import extensiones
from maestros.extensiones import Aviso, Contenido, Impedimento, VariedadesDelCultivo


def _sector(pk):
    return SimpleNamespace(pk=pk)


class ExtensionesDeSectoresTests(SimpleTestCase):
    """Los siete puntos de sectores."""

    def test_ext_agujeros_sin_registrantes_da_cero_ocupados_y_comprometidos(self):
        """API, «Sectores»: sin registrantes, (0, 0) para cada sector."""
        self.assertEqual(extensiones.agujeros_registrados([1, 2]), {1: (0, 0), 2: (0, 0)})

    def test_ext_agujeros_suma_los_de_todos_los_registrantes(self):
        """API: se suman todos los registrantes; lo que no figura es (0, 0)."""
        with mock.patch.object(extensiones, "_AGUJEROS", [lambda ids: {1: (3, 1)}, lambda ids: {1: (2, 4), 2: (5, 0)}]):
            self.assertEqual(extensiones.agujeros_registrados([1, 2, 3]), {1: (5, 5), 2: (5, 0), 3: (0, 0)})

    def test_ext_agujeros_ignora_ids_que_no_se_pidieron(self):
        """Un registrante que devuelve de más no agrega sectores al resultado."""
        with mock.patch.object(extensiones, "_AGUJEROS", [lambda ids: {99: (1, 1)}]):
            self.assertEqual(extensiones.agujeros_registrados([1]), {1: (0, 0)})

    def test_ext_impedimentos_de_sector_sin_registrantes_no_hay_ninguno(self):
        """API: sin registrantes, ningún impedimento."""
        self.assertEqual(extensiones.impedimentos_registrados_de_sector(_sector(1)), [])

    def test_ext_impedimentos_de_sector_se_juntan_los_de_todos(self):
        """Reglas 2 y 3 de PROD-BAJ-SCT: se informan todos, sin quedarse con el primero."""
        a = Impedimento("agujeros_ocupados", "Tiene lotes.", "Sacalo de servicio.")
        b = Impedimento("hardware_activo", "Tiene un equipo.", "Quitale el sector.")
        with mock.patch.object(extensiones, "_IMPEDIMENTOS_DE_SECTOR", [lambda s: [a], lambda s: [b]]):
            self.assertEqual(extensiones.impedimentos_registrados_de_sector(_sector(1)), [a, b])

    def test_ext_contenido_sin_registrantes_esta_vacio(self):
        """API: sin registrantes, ningún contenido por sector."""
        self.assertEqual(extensiones.contenido_registrado([_sector(1)]), {1: []})

    def test_ext_contenido_junta_lotes_y_hardware_de_distintos_registrantes(self):
        """Regla 3 de PROD-CNS-SCT: lo de `produccion` y lo de `iot` aparece junto."""
        lote = Contenido("lote", "L-1", 10, None, None)
        equipo = Contenido("hardware", "Sensor", None, None, None)
        with mock.patch.object(
            extensiones, "_CONTENIDOS", [lambda ss: {1: [lote]}, lambda ss: {1: [equipo], 2: [equipo]}]
        ):
            self.assertEqual(extensiones.contenido_registrado([_sector(1), _sector(2)]), {1: [lote, equipo], 2: [equipo]})

    def test_ext_perfil_sin_registrantes_es_none(self):
        """API: sin registrantes el sector no tiene plantas (None)."""
        self.assertEqual(extensiones.perfiles_registrados([1]), {1: None})

    def test_ext_perfil_toma_el_que_informa_el_registrante(self):
        """API: el perfil familiar de las plantas del sector."""
        with mock.patch.object(extensiones, "_PERFILES", [lambda ids: {1: "Hoja verde", 2: None}]):
            self.assertEqual(extensiones.perfiles_registrados([1, 2]), {1: "Hoja verde", 2: None})

    def test_ext_avisos_de_cambio_de_tipo_sin_registrantes_no_hay_ninguno(self):
        """API: sin registrantes, ningún aviso."""
        self.assertEqual(extensiones.avisos_registrados_de_cambio_de_tipo(object(), object()), [])

    def test_ext_avisos_de_cambio_de_tipo_se_juntan_los_de_todos(self):
        """Reglas 4 de PROD-MOD-SCT y de PROD-BAJ-SCT: se juntan, sin quedarse con el primero."""
        a, b = Aviso("Lotes que pasan por la etapa", 2), Aviso("Siembras a realizar", 1)
        with mock.patch.object(extensiones, "_AVISOS_DE_CAMBIO_DE_TIPO", [lambda i, t: [a], lambda i, t: [b]]):
            self.assertEqual(extensiones.avisos_registrados_de_cambio_de_tipo(object(), object()), [a, b])

    def test_ext_vuelta_a_servicio_sin_registrantes_no_hace_nada(self):
        """API: sin registrantes, el cambio de estado funciona igual."""
        extensiones.aplicar_efectos_de_vuelta_a_servicio(object(), _sector(1))

    def test_ext_vuelta_a_servicio_llama_a_todos_con_actor_y_sector(self):
        """Postcondición b de PROD-MOD-SCT: cada registrante recibe (actor, sector)."""
        a, b = mock.Mock(), mock.Mock()
        actor, sector = object(), _sector(1)
        with mock.patch.object(extensiones, "_VUELTAS_A_SERVICIO", [a, b]):
            extensiones.aplicar_efectos_de_vuelta_a_servicio(actor, sector)
        a.assert_called_once_with(actor, sector)
        b.assert_called_once_with(actor, sector)

    def test_ext_efecto_de_baja_de_sector_sin_registrantes_no_hace_nada(self):
        """API, lote 5: sin registrantes la baja funciona igual."""
        extensiones.aplicar_efectos_de_baja_de_sector(object(), _sector(1))

    def test_ext_efecto_de_baja_de_sector_llama_a_todos_una_vez(self):
        """Postcondición b de PROD-BAJ-SCT: se llama una vez por registrante, con (actor, sector)."""
        a, b = mock.Mock(), mock.Mock()
        actor, sector = object(), _sector(1)
        with mock.patch.object(extensiones, "_EFECTOS_DE_BAJA_DE_SECTOR", [a, b]):
            extensiones.aplicar_efectos_de_baja_de_sector(actor, sector)
        a.assert_called_once_with(actor, sector)
        b.assert_called_once_with(actor, sector)

    def test_ext_registrar_devuelve_la_funcion_para_usarse_como_decorador(self):
        """Los registros de lista devuelven la función registrada."""
        with mock.patch.object(extensiones, "_AGUJEROS", []):
            funcion = lambda ids: {}  # noqa: E731
            self.assertIs(extensiones.registrar_agujeros_de_sector(funcion), funcion)


class ExtensionesDeCultivosTests(SimpleTestCase):
    """Los puntos de cultivos."""

    def test_ext_semillas_sin_registrantes_son_cero(self):
        """docs/casos_de_uso/maestros/cultivos.md, «Cómo se aplica»: sin registrantes, 0 semillas."""
        cultivo = object()
        with mock.patch.object(extensiones, "_SEMILLAS", []):  # `inventario` (INV-03) los registra en ready()
            self.assertEqual(extensiones.contar_semillas_a_renombrar(cultivo), 0)
            self.assertEqual(extensiones.renombrar_semillas(object(), cultivo, "Lechuga"), 0)

    def test_ext_semillas_se_suman_las_de_todos_los_registrantes(self):
        """API: contar y renombrar suman a todos los registrantes."""
        renombrar_a, renombrar_b = mock.Mock(return_value=2), mock.Mock(return_value=3)
        with mock.patch.object(extensiones, "_SEMILLAS", [(lambda c: 2, renombrar_a), (lambda c: 3, renombrar_b)]):
            self.assertEqual(extensiones.contar_semillas_a_renombrar(object()), 5)
            actor, cultivo = object(), object()
            self.assertEqual(extensiones.renombrar_semillas(actor, cultivo, "Vieja"), 5)
        renombrar_a.assert_called_once_with(actor, cultivo, "Vieja")

    def test_ext_uso_de_cultivo_sin_registrantes_no_hay_invernaderos(self):
        """Regla 4 de PROD-MOD-CLT: sin registrantes, ningún invernadero usa el cultivo."""
        with mock.patch.object(extensiones, "_USOS_DE_CULTIVO", []):  # `inventario` (INV-03) lo registra en ready()
            self.assertEqual(extensiones.invernaderos_que_usan_el_cultivo(object()), set())

    def test_ext_uso_de_cultivo_une_los_conjuntos_de_todos(self):
        """API: se juntan los ids de todos los registrantes, sin repetir."""
        with mock.patch.object(extensiones, "_USOS_DE_CULTIVO", [lambda c: {1, 2}, lambda c: {2, 3}]):
            self.assertEqual(extensiones.invernaderos_que_usan_el_cultivo(object()), {1, 2, 3})

    def test_ext_variedades_sin_registrante_da_none(self):
        """API: sin registrante (hasta INV-03) la pantalla usa lo propio de maestros."""
        with mock.patch.object(extensiones, "_VARIEDADES", []):
            self.assertIsNone(extensiones.variedades_registradas(object(), []))

    def test_ext_variedades_llama_al_registrante_con_actor_y_cultivos(self):
        """API: funcion(actor, cultivos) -> dict[id, VariedadesDelCultivo]."""
        resultado = {1: VariedadesDelCultivo("<b>+</b>", "<table></table>")}
        funcion = mock.Mock(return_value=resultado)
        actor, cultivos = object(), [object()]
        with mock.patch.object(extensiones, "_VARIEDADES", []):
            extensiones.registrar_variedades_de_cultivo(funcion)
            self.assertEqual(extensiones.variedades_registradas(actor, cultivos), resultado)
        funcion.assert_called_once_with(actor, cultivos)

    def test_ext_variedades_admite_un_solo_registrante(self):
        """API: una segunda llamada a registrar_variedades_de_cultivo lanza RuntimeError."""
        with mock.patch.object(extensiones, "_VARIEDADES", []):
            extensiones.registrar_variedades_de_cultivo(lambda a, c: {})
            with self.assertRaises(RuntimeError):
                extensiones.registrar_variedades_de_cultivo(lambda a, c: {})
