# Pruebas de COM-CNS-CLT, Consultar Cliente (COM-01, paso 3; docs/casos_de_uso/comercial/clientes.md): la búsqueda (CUIT, razón
# social, nombre y apellido), el filtro por estado, el orden, las páginas de 50, la ficha con las direcciones activas e inactivas,
# el alcance y los botones (``acciones_permitidas``).
#
# ``buscar_clientes(actor, texto="", estado="", pagina=1)`` devuelve la ``Page`` de Django; ``ficha_del_cliente(actor, id)`` una
# ``FichaDelCliente(cliente, direcciones_activas, direcciones_inactivas)`` (las direcciones son las hijas, urbana o rural);
# ``acciones_permitidas(actor, cliente)``, un conjunto con ``ACCION_MODIFICAR``, ``ACCION_BAJA`` y ``ACCION_REACTIVAR``.

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase

from comercial.servicios import clientes
from comercial.tests.fabricas import cliente, cuit_valido, direccion_de_cliente
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.models import Direccion
from maestros.tests.fabricas import ConGeoref, crear_agronomo, crear_transportista, crear_vendedor


class ComCnsCltBusquedaTests(TestCase):
    """``buscar_clientes``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor()
        self.pinos = cliente(cuit="30712345671", razon_social="Verdulería Los Pinos")
        self.marta = cliente(tipo="fisica", cuit="20123456786", nombre="Marta", apellido="Gómez")
        self.baja = cliente(cuit="30000000090", razon_social="Cerrado S.A.", activo=False)

    def buscar(self, texto="", estado="", pagina=1, actor=None):
        return [c.pk for c in clientes.buscar_clientes(actor or self.gerente, texto, estado, pagina).object_list]

    def test_regla_1_sin_filtros_trae_a_todos_ordenados_por_nombre_visible(self):
        """Regla 1 y orden: por nombre visible (sin distinguir mayúsculas) y después id: «Cerrado», «Marta Gómez», «Verdulería»."""
        self.assertEqual(self.buscar(), [self.baja.pk, self.marta.pk, self.pinos.pk])

    def test_regla_1_busca_por_cuit_con_o_sin_guiones_desde_2_digitos(self):
        """Regla 1 («desde 2 dígitos, con o sin guiones»): un dígito solo no busca por CUIT."""
        self.assertEqual(self.buscar("30-71"), [self.pinos.pk])
        self.assertEqual(self.buscar("3071234"), [self.pinos.pk])
        self.assertEqual(self.buscar("30-71234567-1"), [self.pinos.pk])
        self.assertEqual(self.buscar("20"), [self.marta.pk])
        self.assertEqual(self.buscar("3"), [])

    def test_regla_1_busca_por_razon_social_o_por_nombre_y_apellido_sin_distinguir_mayusculas(self):
        """Regla 1: ``icontains`` sobre la razón social, el nombre, el apellido y «Nombre Apellido»."""
        self.assertEqual(self.buscar("los PINOS"), [self.pinos.pk])
        self.assertEqual(self.buscar("marta"), [self.marta.pk])
        self.assertEqual(self.buscar("gómez"), [self.marta.pk])
        self.assertEqual(self.buscar("Marta Gómez"), [self.marta.pk])
        self.assertEqual(self.buscar("zzz"), [])

    def test_regla_1_filtra_por_estado(self):
        """Regla 1: filtro por estado (``activo`` o ``inactivo``; vacío, todos)."""
        self.assertEqual(self.buscar(estado="activo"), [self.marta.pk, self.pinos.pk])
        self.assertEqual(self.buscar(estado="inactivo"), [self.baja.pk])
        self.assertEqual(self.buscar("pinos", "inactivo"), [])

    def test_regla_1_las_paginas_son_de_50(self):
        """«Consulta»: 50 por página; una página inexistente devuelve la última."""
        for _ in range(48):
            cliente(cuit=cuit_valido())
        pagina = clientes.buscar_clientes(self.gerente, "", "", 1)
        self.assertEqual((len(pagina.object_list), pagina.paginator.num_pages, pagina.paginator.count), (50, 2, 51))
        self.assertEqual(len(clientes.buscar_clientes(self.gerente, "", "", 2).object_list), 1)
        self.assertEqual(len(clientes.buscar_clientes(self.gerente, "", "", 99).object_list), 1)
        self.assertEqual(len(clientes.buscar_clientes(self.gerente, "", "", "x").object_list), 50)

    def test_regla_3_el_vendedor_ve_todos_los_clientes(self):
        """Regla 3: un cliente puede comprarle a varios Vendedores; el Vendedor ve todos."""
        self.assertEqual(self.buscar(actor=self.vendedor), [self.baja.pk, self.marta.pk, self.pinos.pk])

    def test_pre_a_otros_roles_inactivos_y_anonimos_reciben_permission_denied(self):
        """Precondición a: solo Vendedor y Gerente activos."""
        inactivo = crear_vendedor("inactivo@infoponia.com", activo=False)
        for actor in (crear_agronomo(), crear_transportista(), inactivo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                clientes.buscar_clientes(actor, "", "", 1)

    def test_post_a_consultar_no_registra_ningun_cambio(self):
        """Postcondición a y SEG-14: las consultas no se auditan."""
        self.buscar("pinos")
        self.assertFalse(RegistroAuditoria.objects.exists())


class ComCnsCltFichaTests(ConGeoref, TestCase):
    """``ficha_del_cliente`` y ``acciones_permitidas``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor()
        self.cliente = cliente(cuit="30712345671", razon_social="Los Pinos")

    def test_regla_2_la_ficha_muestra_los_datos_y_las_direcciones_activas_e_inactivas(self):
        """Regla 2: los datos del cliente y sus direcciones, activas e inactivas, separadas."""
        activa = direccion_de_cliente(self.cliente)
        inactiva = direccion_de_cliente(self.cliente, calle="Belgrano", numero_calle="45")
        Direccion.objects.filter(pk=inactiva.direccion_id).update(estado_direccion="inactivo")
        ficha = clientes.ficha_del_cliente(self.vendedor, self.cliente.pk)
        self.assertEqual(ficha.cliente.pk, self.cliente.pk)
        self.assertEqual([d.pk for d in ficha.direcciones_activas], [activa.direccion_id])
        self.assertEqual([d.pk for d in ficha.direcciones_inactivas], [inactiva.direccion_id])
        self.assertEqual(ficha.direcciones_activas[0].calle, "San Martín")  # son las hijas, con sus datos

    def test_regla_2_la_ficha_de_un_cliente_sin_direcciones_las_trae_vacias(self):
        """MD-128: un cliente sin direcciones tiene las dos listas vacías."""
        ficha = clientes.ficha_del_cliente(self.gerente, self.cliente.pk)
        self.assertEqual((ficha.direcciones_activas, ficha.direcciones_inactivas), ([], []))

    def test_regla_2_la_ficha_de_un_inactivo_se_puede_consultar(self):
        """Regla 2 de CNS (cliente inactivo): aparece en las consultas."""
        inactivo = cliente(cuit="30000000090", activo=False)
        self.assertEqual(clientes.ficha_del_cliente(self.vendedor, inactivo.pk).cliente.pk, inactivo.pk)

    def test_regla_3_el_gerente_y_el_vendedor_activos_ven_la_ficha_otros_no(self):
        """Regla 3 y D-28: otros roles, una cuenta inactiva o ``None`` reciben ``PermissionDenied``; un id inexistente, 404."""
        for actor in (self.gerente, self.vendedor):
            self.assertEqual(clientes.ficha_del_cliente(actor, self.cliente.pk).cliente.pk, self.cliente.pk)
        for actor in (crear_agronomo(), crear_transportista(), crear_vendedor("inactivo@infoponia.com", activo=False), None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                clientes.ficha_del_cliente(actor, self.cliente.pk)
        with self.assertRaises(Http404):
            clientes.ficha_del_cliente(self.gerente, 999999)

    def test_pre_a_las_acciones_del_gerente_son_modificar_y_dar_de_baja_en_un_activo(self):
        """Patrón ABM, sección 6: el Gerente ve «Modificar» y «Dar de baja» en un cliente activo."""
        self.assertEqual(
            clientes.acciones_permitidas(self.gerente, self.cliente), {clientes.ACCION_MODIFICAR, clientes.ACCION_BAJA}
        )

    def test_pre_a_las_acciones_del_gerente_en_un_inactivo_son_modificar_y_reactivar(self):
        """Regla 2 de MOD y regla 3 de BAJ: la ficha de un inactivo muestra «Modificar» y «Reactivar» (y no la baja)."""
        inactivo = cliente(cuit="30000000090", activo=False)
        self.assertEqual(
            clientes.acciones_permitidas(self.gerente, inactivo), {clientes.ACCION_MODIFICAR, clientes.ACCION_REACTIVAR}
        )

    def test_regla_3_de_baj_el_vendedor_no_ve_la_baja(self):
        """«Baja»: el Vendedor no ve el botón de baja (ningún botón lleva a un 403, D-30)."""
        inactivo = cliente(cuit="30000000090", activo=False)
        self.assertEqual(clientes.acciones_permitidas(self.vendedor, self.cliente), {clientes.ACCION_MODIFICAR})
        self.assertEqual(
            clientes.acciones_permitidas(self.vendedor, inactivo), {clientes.ACCION_MODIFICAR, clientes.ACCION_REACTIVAR}
        )

    def test_pre_a_otros_roles_no_tienen_acciones(self):
        """D-30: cualquier otro rol, una cuenta inactiva o ``None``: ninguna acción."""
        for actor in (crear_agronomo(), crear_transportista(), crear_vendedor("inactivo@infoponia.com", activo=False), None):
            with self.subTest(actor=actor):
                self.assertEqual(clientes.acciones_permitidas(actor, self.cliente), set())
