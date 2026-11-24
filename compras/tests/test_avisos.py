# Pruebas de compras/servicios/avisos.py (CMP-02a, paso 4): la regla única de destinatarios (H21, D-87 punto 3). Fuente: D-87 punto 3, CMP-CNL-PED
# («Cancelaciones automáticas»: «a cada Agrónomo activo de los invernaderos de destino y, por cada destino sin Agrónomo activo, al Gerente; nunca
# se notifica a quien hizo la acción») y CMP-ENV-COT («Destinatario del aviso de pedido cubierto»). El módulo se toma dentro de cada prueba.

from django.test import TestCase

from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, perezoso
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

avisos = perezoso("compras.servicios.avisos")


class DestinatariosPorDestinoTests(ConDatosDeInventario, TestCase):
    """``destinatarios_por_destino(invernadero_ids, *, excluir=None) -> list[Usuario]``."""

    def setUp(self):
        self.ana = crear_agronomo(email="ana@infoponia.com")
        self.beto = crear_agronomo(email="beto@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.ana)
        self.sur = crear_invernadero("Sur", agronomo=self.beto)
        self.gerente = crear_gerente()

    def pks(self, destinatarios):
        return [d.pk for d in destinatarios]

    def test_h21_el_agronomo_activo_de_cada_invernadero_de_destino(self):
        """H21: cada Agrónomo activo de los invernaderos de destino, y nadie más cuando todos tienen Agrónomo."""
        self.assertEqual(sorted(self.pks(avisos.destinatarios_por_destino([self.norte.pk, self.sur.pk]))), sorted([self.ana.pk, self.beto.pk]))

    def test_h21_un_agronomo_a_cargo_de_dos_destinos_recibe_un_solo_aviso(self):
        """D-87 punto 3: sin repetidos."""
        otro = crear_invernadero("Otro", agronomo=self.ana)
        self.assertEqual(self.pks(avisos.destinatarios_por_destino([self.norte.pk, otro.pk])), [self.ana.pk])

    def test_h21_un_destino_sin_agronomo_avisa_al_gerente(self):
        """H21: por cada destino sin Agrónomo activo, el Gerente."""
        sin = crear_invernadero("Sin Agrónomo")
        self.assertEqual(sorted(self.pks(avisos.destinatarios_por_destino([self.norte.pk, sin.pk]))), sorted([self.ana.pk, self.gerente.pk]))

    def test_h21_el_gerente_recibe_un_solo_aviso_aunque_varios_destinos_no_tengan_agronomo(self):
        """D-87 punto 3: «el Gerente activo una sola vez»."""
        a, b = crear_invernadero("A"), crear_invernadero("B")
        self.assertEqual(self.pks(avisos.destinatarios_por_destino([a.pk, b.pk])), [self.gerente.pk])

    def test_h21_un_agronomo_inactivo_equivale_a_no_tener_agronomo(self):
        """H21 y CMP-ENV-COT: si el Agrónomo está inactivo, el aviso va al Gerente."""
        self.ana.is_active = False
        self.ana.save()
        self.assertEqual(self.pks(avisos.destinatarios_por_destino([self.norte.pk])), [self.gerente.pk])

    def test_h21_sin_gerente_activo_se_omite_sin_fallar(self):
        """D-14 y D-42: sin Gerente activo no hay a quién avisar y no falla."""
        self.gerente.is_active = False
        self.gerente.save()
        sin = crear_invernadero("Sin Agrónomo")
        self.assertEqual(self.pks(avisos.destinatarios_por_destino([sin.pk])), [])

    def test_h21_nunca_se_notifica_a_quien_hizo_la_accion(self):
        """H21: ``excluir`` saca a la cuenta que actuó; si era el Agrónomo de ese destino no se suma el Gerente por él."""
        self.assertEqual(self.pks(avisos.destinatarios_por_destino([self.norte.pk, self.sur.pk], excluir=self.ana)), [self.beto.pk])
        self.assertEqual(avisos.destinatarios_por_destino([self.norte.pk], excluir=self.ana), [])

    def test_h21_si_quien_actuo_es_el_gerente_no_se_le_avisa(self):
        """H21: el Gerente que actuó no recibe el aviso de un destino sin Agrónomo."""
        sin = crear_invernadero("Sin Agrónomo")
        self.assertEqual(avisos.destinatarios_por_destino([sin.pk], excluir=self.gerente), [])

    def test_h21_sin_destinos_no_hay_destinatarios(self):
        """Sin invernaderos de destino no hay a quién avisar."""
        self.assertEqual(avisos.destinatarios_por_destino([]), [])
