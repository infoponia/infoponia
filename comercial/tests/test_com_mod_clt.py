# Pruebas de COM-MOD-CLT, Modificar Cliente (COM-01, paso 3; docs/casos_de_uso/comercial/clientes.md): datos, CUIT, tipo, cliente
# inactivo, direcciones (agregar, corregir en el lugar, cambio de zona, desactivar, borrar, dirección en uso e idéntica), el
# correo con suministro vigente (se completa en COM-03, acá con ``mock.patch``) y la auditoría.
#
# ``modificar_cliente(actor, cliente_id, datos)``: ``datos`` es el mismo ``DatosDeCliente`` del alta. ``direcciones_corregidas``
# son pares (id de la ``Direccion``, datos nuevos); ``desactivadas`` y ``borradas``, ids de ``Direccion``. Errores de una
# corrección: ``corregida-<id>-<campo>`` y ``corregida-<id>`` (``direccion_repetida``); una dirección que no es del cliente, o una
# en uso que se quiere borrar, es un error del campo ``direcciones`` (``direccion_invalida`` y ``direccion_en_uso``).

from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase

from comercial.models import Cliente, DireccionCliente
from comercial.servicios import clientes
from comercial.tests.fabricas import cliente, datos_de_cliente_de, datos_de_direccion, direccion_de_cliente
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.models import Direccion, DireccionRural, DireccionUrbana
from maestros.tests.fabricas import ConGeoref, crear_agronomo, crear_transportista, crear_vendedor, localidad


def errores_de(prueba, llamada):
    """Ejecuta ``llamada`` y devuelve los errores que lanza como ``{campo: [ValidationError]}``."""
    with prueba.assertRaises(ValidationError) as contexto:
        llamada()
    return contexto.exception.error_dict


def codigos(errores, campo):
    """Los códigos del campo ``campo`` de un ``error_dict``."""
    return [e.code for e in errores.get(campo, [])]


class ComModCltServicioTests(ConGeoref, TestCase):
    """``modificar_cliente(actor, cliente_id, datos)``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor()
        self.cliente = cliente(cuit="30712345671", razon_social="Los Pinos", telefono="", email="")

    def modificar(self, actor=None, cliente_=None, **extra):
        cliente_ = cliente_ or self.cliente
        cliente_.refresh_from_db()
        return clientes.modificar_cliente(actor or self.vendedor, cliente_.pk, datos_de_cliente_de(cliente_, **extra))

    def auditoria(self):
        return RegistroAuditoria.objects.filter(accion="modificacion_cliente")

    # -- precondiciones --

    def test_pre_a_el_vendedor_y_el_gerente_activos_pueden(self):
        """Precondición a: Vendedor o Gerente con la cuenta activa."""
        for actor in (self.vendedor, self.gerente):
            with self.subTest(rol=actor.rol):
                self.assertEqual(self.modificar(actor, telefono=f"+54 376 400-10{actor.pk:02d}").pk, self.cliente.pk)

    def test_pre_a_otros_roles_inactivos_y_anonimos_reciben_permission_denied(self):
        """Precondición a: cualquier otro rol, una cuenta inactiva o ``None``."""
        inactivo = crear_vendedor("inactivo@infoponia.com", activo=False)
        for actor in (crear_agronomo(), crear_transportista(), inactivo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                clientes.modificar_cliente(actor, self.cliente.pk, datos_de_cliente_de(self.cliente))

    def test_pre_a_un_cliente_inexistente_da_404(self):
        """D-28: un id inexistente es 404."""
        with self.assertRaises(Http404):
            clientes.modificar_cliente(self.vendedor, 999999, datos_de_cliente_de(self.cliente))

    def test_pre_b_el_cuit_nuevo_no_puede_ser_el_de_otro_cliente_activo_o_inactivo(self):
        """Precondición b: ``cuit_de_cliente_activo`` o ``cuit_de_cliente_inactivo`` con el id del otro cliente."""
        activo = cliente(cuit="30000000090")
        inactivo = cliente(cuit="30000000120", activo=False)
        for cuit, codigo, otro in (("30000000090", "cuit_de_cliente_activo", activo), ("30-00000012-0", "cuit_de_cliente_inactivo", inactivo)):
            with self.subTest(codigo=codigo):
                errores = errores_de(self, lambda: self.modificar(cuit=cuit))
                self.assertEqual(codigos(errores, "cuit"), [codigo])
                self.assertEqual(errores["cuit"][0].params["cliente_id"], otro.pk)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.cuit_cliente, "30712345671")

    def test_pre_b_cambiar_el_cuit_a_uno_libre_y_valido_se_puede(self):
        """Precondición b: con un CUIT libre y válido, cambia (se guarda sin guiones y se audita con ellos)."""
        self.modificar(cuit="30-00000009-0")
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.cuit_cliente, "30000000090")
        self.assertEqual(
            self.auditoria().get().detalle["cambios"]["cuit"], {"antes": "30-71234567-1", "despues": "30-00000009-0"}
        )

    def test_regla_1_los_datos_siguen_las_reglas_del_alta(self):
        """Regla 1: el CUIT inválido, la razón social vacía, el teléfono y el correo se validan igual que en el alta."""
        errores = errores_de(self, lambda: self.modificar(cuit="x", razon_social="", telefono="abc", email="mal"))
        self.assertEqual(set(errores), {"cuit", "razon_social", "telefono", "email"})

    # -- postcondición a, regla 2 --

    def test_post_a_actualiza_los_datos_indicados(self):
        """Postcondición a: se actualizaron los datos indicados."""
        self.modificar(razon_social="Los Pinos S.A.", telefono="+54 376 400-1001", email="compras@pinos.com")
        self.cliente.refresh_from_db()
        self.assertEqual(
            (self.cliente.razon_social_cliente, self.cliente.telefono_cliente, self.cliente.email_cliente),
            ("Los Pinos S.A.", "+54 376 400-1001", "compras@pinos.com"),
        )

    def test_regla_3_de_alt_cambiar_el_tipo_se_permite_vacia_los_datos_del_otro_y_se_audita(self):
        """«Tipo de cliente» (cómo se aplica): cambiarlo corrige un error de carga; se conservan solo los datos del tipo elegido."""
        self.modificar(tipo_cliente="fisica", razon_social="Los Pinos", nombre="Marta", apellido="Gómez")
        self.cliente.refresh_from_db()
        self.assertEqual(
            (self.cliente.tipo_cliente, self.cliente.razon_social_cliente, self.cliente.nombre_cliente, self.cliente.apellido_cliente),
            ("fisica", "", "Marta", "Gómez"),
        )
        cambios = self.auditoria().get().detalle["cambios"]
        self.assertEqual(cambios["tipo_cliente"], {"antes": "juridica", "despues": "fisica"})
        self.assertEqual(cambios["razon_social"], {"antes": "Los Pinos", "despues": ""})
        self.assertEqual(cambios["nombre"], {"antes": "", "despues": "Marta"})

    def test_regla_2_se_puede_modificar_un_cliente_inactivo_y_no_lo_reactiva(self):
        """Regla 2: un cliente inactivo se modifica y sigue inactivo."""
        inactivo = cliente(cuit="30000000090", activo=False, razon_social="Viejo")
        self.modificar(cliente_=inactivo, razon_social="Nuevo")
        inactivo.refresh_from_db()
        self.assertEqual((inactivo.razon_social_cliente, inactivo.estado_cliente), ("Nuevo", "inactivo"))
        self.assertFalse(RegistroAuditoria.objects.filter(accion="reactivacion_cliente").exists())

    def test_d28_sin_cambios_no_se_escribe_ni_se_audita(self):
        """D-28 y patrón ABM, paso 5: si nada cambia, no hay registro de auditoría."""
        self.modificar()
        self.assertFalse(self.auditoria().exists())

    def test_post_f_audita_con_el_cliente_y_los_cambios_antes_y_despues(self):
        """Postcondición f y D-36: ``modificacion_cliente`` con usuario, el cliente afectado y los cambios con antes y después."""
        self.modificar(telefono="+54 376 400-1001")
        registro = self.auditoria().get()
        self.assertEqual(registro.usuario_id, self.vendedor.pk)
        self.assertEqual([afectado["id"] for afectado in registro.afectados], [self.cliente.pk])
        self.assertEqual(registro.detalle["cambios"], {"telefono": {"antes": "", "despues": "+54 376 400-1001"}})

    # -- direcciones --

    def test_post_b_agrega_una_direccion_activa(self):
        """Postcondición b: la dirección agregada queda creada en estado «activo»."""
        self.modificar(direcciones_nuevas=[datos_de_direccion()])
        vinculo = self.cliente.direcciones.get()
        self.assertEqual(vinculo.direccion.estado_direccion, "activo")
        registro = self.auditoria().get()
        self.assertEqual(len(registro.detalle["datos"]["direcciones_creadas"]), 1)
        self.assertIn(vinculo.direccion_id, [afectado["id"] for afectado in registro.afectados])

    def test_regla_6_una_direccion_nueva_igual_a_una_activa_se_rechaza_pero_no_a_una_inactiva(self):
        """Regla 6 de ALT y D-58 punto 6: no dos idénticas **activas**; una inactiva no cuenta."""
        existente = direccion_de_cliente(self.cliente)
        errores = errores_de(self, lambda: self.modificar(direcciones_nuevas=[datos_de_direccion(calle="SAN MARTÍN")]))
        self.assertEqual(codigos(errores, "nueva-0"), ["direccion_repetida"])
        self.modificar(direcciones_desactivadas=[existente.direccion_id])
        self.modificar(direcciones_nuevas=[datos_de_direccion()])
        self.assertEqual(self.cliente.direcciones.count(), 2)

    def test_post_c_corrige_en_el_lugar_una_direccion_que_nada_usa(self):
        """Postcondición c y regla 4: una dirección que nada usa se corrige en el lugar (misma fila, misma zona)."""
        vinculo = direccion_de_cliente(self.cliente, piso="1")
        antes = vinculo.direccion_id
        self.modificar(direcciones_corregidas=[(antes, datos_de_direccion(calle="Belgrano", numero_calle="45"))])
        self.assertEqual(self.cliente.direcciones.get().direccion_id, antes)
        hija = DireccionUrbana.objects.get(pk=antes)
        self.assertEqual((hija.calle, hija.numero_calle, hija.piso), ("Belgrano", "45", ""))
        registro = self.auditoria().get()
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["direcciones_corregidas"]], [antes])

    def test_post_c_corregir_una_direccion_a_otra_igual_a_una_activa_se_rechaza(self):
        """Regla 6: la corrección no puede dejar dos direcciones activas idénticas (``corregida-<id>``: ``direccion_repetida``)."""
        direccion_de_cliente(self.cliente)
        otra = direccion_de_cliente(self.cliente, calle="Belgrano", numero_calle="45")
        errores = errores_de(self, lambda: self.modificar(direcciones_corregidas=[(otra.direccion_id, datos_de_direccion())]))
        self.assertEqual(codigos(errores, f"corregida-{otra.direccion_id}"), ["direccion_repetida"])

    def test_post_c_los_errores_de_una_correccion_van_por_campo(self):
        """Regla 6: ``corregida-<id>-<campo>`` con los mismos códigos del alta."""
        vinculo = direccion_de_cliente(self.cliente)
        errores = errores_de(
            self, lambda: self.modificar(direcciones_corregidas=[(vinculo.direccion_id, datos_de_direccion(calle=""))])
        )
        self.assertEqual(codigos(errores, f"corregida-{vinculo.direccion_id}-calle"), ["obligatorio"])

    def test_post_c_el_cambio_de_zona_crea_la_nueva_apunta_el_vinculo_y_borra_la_anterior(self):
        """«Dirección usada» y API «Cambio de zona»: la nueva dirección (rural), el vínculo apuntando a ella y la anterior
        borrada; en la auditoría va en ``direcciones_corregidas`` con la referencia nueva."""
        vinculo = direccion_de_cliente(self.cliente)
        vieja = vinculo.direccion_id
        self.modificar(direcciones_corregidas=[(vieja, datos_de_direccion("rural"))])
        vinculo.refresh_from_db()
        self.assertNotEqual(vinculo.direccion_id, vieja)
        self.assertFalse(Direccion.objects.filter(pk=vieja).exists())
        self.assertTrue(DireccionRural.objects.filter(pk=vinculo.direccion_id).exists())
        registro = self.auditoria().get()
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["direcciones_corregidas"]], [vinculo.direccion_id])

    def test_post_e_desactiva_una_direccion_y_no_se_reactiva(self):
        """Postcondición e: queda «inactiva» (y se conserva); desactivar una ya inactiva no falla ni audita de más."""
        vinculo = direccion_de_cliente(self.cliente)
        self.modificar(direcciones_desactivadas=[vinculo.direccion_id])
        self.assertEqual(Direccion.objects.get(pk=vinculo.direccion_id).estado_direccion, "inactivo")
        self.assertEqual(
            [r["id"] for r in self.auditoria().get().detalle["datos"]["direcciones_desactivadas"]], [vinculo.direccion_id]
        )
        self.modificar(direcciones_desactivadas=[vinculo.direccion_id])
        self.assertEqual(self.auditoria().count(), 1)

    def test_regla_4_borra_una_direccion_que_nada_usa_con_su_vinculo(self):
        """Regla 4: una dirección que nada usa puede borrarse (primero su ``DireccionCliente``, después la dirección)."""
        vinculo = direccion_de_cliente(self.cliente)
        direccion_id = vinculo.direccion_id
        self.modificar(direcciones_borradas=[direccion_id])
        self.assertFalse(DireccionCliente.objects.filter(pk=vinculo.pk).exists())
        self.assertFalse(Direccion.objects.filter(pk=direccion_id).exists())
        self.assertEqual(
            [r["id"] for r in self.auditoria().get().detalle["datos"]["direcciones_borradas"]], [direccion_id]
        )

    def test_regla_4_una_direccion_en_uso_se_corrige_creando_otra_y_la_anterior_queda_inactiva(self):
        """Postcondición d y regla 4 (con ``direcciones_en_uso`` simulada: COM-02 y COM-03 le suman sus consultas): la corrección
        crea otra dirección con su vínculo, la anterior pasa a «inactiva» (sigue vinculada) y va en ``direcciones_reemplazadas``."""
        vinculo = direccion_de_cliente(self.cliente)
        vieja = vinculo.direccion_id
        with mock.patch.object(clientes, "direcciones_en_uso", return_value={vieja}) as en_uso:
            self.modificar(direcciones_corregidas=[(vieja, datos_de_direccion(calle="Belgrano", numero_calle="45"))])
        en_uso.assert_called()
        self.assertEqual(Direccion.objects.get(pk=vieja).estado_direccion, "inactivo")
        self.assertTrue(DireccionCliente.objects.filter(cliente=self.cliente, direccion_id=vieja).exists())
        nueva = self.cliente.direcciones.exclude(direccion_id=vieja).get().direccion
        self.assertEqual((nueva.estado_direccion, nueva.concreta().calle), ("activo", "Belgrano"))
        registro = self.auditoria().get()
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["direcciones_reemplazadas"]], [vieja])
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["direcciones_creadas"]], [nueva.pk])

    def test_regla_4_una_direccion_en_uso_no_se_borra(self):
        """Regla 4: una dirección que usa una venta o un detalle no se borra (``direccion_en_uso`` en ``direcciones``)."""
        vinculo = direccion_de_cliente(self.cliente)
        with mock.patch.object(clientes, "direcciones_en_uso", return_value={vinculo.direccion_id}):
            errores = errores_de(self, lambda: self.modificar(direcciones_borradas=[vinculo.direccion_id]))
        self.assertEqual(codigos(errores, "direcciones"), ["direccion_en_uso"])
        self.assertTrue(Direccion.objects.filter(pk=vinculo.direccion_id).exists())

    def test_regla_4_una_direccion_en_uso_se_puede_desactivar(self):
        """Postcondición e: desactivar se puede siempre, también con la dirección en uso."""
        vinculo = direccion_de_cliente(self.cliente)
        with mock.patch.object(clientes, "direcciones_en_uso", return_value={vinculo.direccion_id}):
            self.modificar(direcciones_desactivadas=[vinculo.direccion_id])
        self.assertEqual(Direccion.objects.get(pk=vinculo.direccion_id).estado_direccion, "inactivo")

    def test_d58_direcciones_en_uso_sin_compra_ventas_devuelve_un_conjunto_vacio(self):
        """«Dirección usada»: sin compra-ventas con envío (COM-02 cuenta las suyas; COM-03 suma los suministros), ninguna está en uso. Con
        datos: ``test_clientes_con_compra_ventas.py``."""
        self.assertEqual(clientes.direcciones_en_uso([1, 2, 3]), set())

    def test_regla_4_las_direcciones_de_otro_cliente_o_inexistentes_se_rechazan(self):
        """Regla 4: solo se tocan las direcciones de este cliente (``direccion_invalida`` en ``direcciones``)."""
        ajena = direccion_de_cliente(cliente(cuit="30000000090"))
        for campo, valor in (
            ("direcciones_desactivadas", [ajena.direccion_id]),
            ("direcciones_borradas", [ajena.direccion_id]),
            ("direcciones_corregidas", [(ajena.direccion_id, datos_de_direccion())]),
            ("direcciones_desactivadas", [999999]),
        ):
            with self.subTest(campo=campo, valor=valor):
                errores = errores_de(self, lambda: self.modificar(**{campo: valor}))
                self.assertEqual(codigos(errores, "direcciones"), ["direccion_invalida"])
        self.assertEqual(Direccion.objects.get(pk=ajena.direccion_id).estado_direccion, "activo")

    def test_regla_4_una_direccion_inactiva_no_se_corrige(self):
        """Cómo se aplica: una inactiva se muestra con su marca y no se reactiva ni se corrige (``direccion_invalida``)."""
        vinculo = direccion_de_cliente(self.cliente)
        self.modificar(direcciones_desactivadas=[vinculo.direccion_id])
        errores = errores_de(
            self, lambda: self.modificar(direcciones_corregidas=[(vinculo.direccion_id, datos_de_direccion(calle="Otra"))])
        )
        self.assertEqual(codigos(errores, "direcciones"), ["direccion_invalida"])

    def test_c6_las_direcciones_nuevas_de_un_cliente_nunca_son_las_de_un_invernadero(self):
        """C6 (D-58): ``comercial`` nunca vincula una dirección existente: las de los clientes y las de los invernaderos no se cruzan."""
        from maestros.tests.fabricas import crear_invernadero

        invernadero = crear_invernadero("Norte")
        self.modificar(direcciones_nuevas=[datos_de_direccion()])
        self.assertFalse(DireccionCliente.objects.filter(direccion_id=invernadero.direccion_id).exists())

    # -- regla 3 (correo con suministro vigente, se completa en COM-03) --

    def test_regla_3_el_correo_con_suministro_vigente_no_se_puede_quitar(self):
        """Regla 3: ``email`` con ``correo_con_suministro_vigente`` cuando ``impide_quitar_el_correo`` dice que sí (en COM-01
        siempre dice que no; COM-03 le suma la consulta)."""
        con_correo = cliente(cuit="30000000090", email="compras@pinos.com")
        with mock.patch.object(clientes, "impide_quitar_el_correo", return_value=True) as impide:
            errores = errores_de(self, lambda: self.modificar(cliente_=con_correo, email=""))
        impide.assert_called_once()
        self.assertEqual(codigos(errores, "email"), ["correo_con_suministro_vigente"])
        con_correo.refresh_from_db()
        self.assertEqual(con_correo.email_cliente, "compras@pinos.com")

    def test_regla_3_si_nadie_lo_impide_el_correo_se_quita_y_si_no_se_quita_ni_se_pregunta(self):
        """Regla 3: sin suministro vigente se puede quitar; si no se está quitando (o no tenía), no se consulta."""
        con_correo = cliente(cuit="30000000090", email="compras@pinos.com")
        with mock.patch.object(clientes, "impide_quitar_el_correo", return_value=False) as impide:
            self.modificar(cliente_=con_correo, email="")
            impide.assert_called_once()
        with mock.patch.object(clientes, "impide_quitar_el_correo", return_value=True) as impide:
            self.modificar(cliente_=con_correo, email="")  # ya no tenía: no es quitarlo
            self.modificar(cliente_=self.cliente, email="otro@pinos.com")
            impide.assert_not_called()

    def test_regla_3_impide_quitar_el_correo_devuelve_false_en_com_01(self):
        """«Correo con suministro vigente»: en COM-01 devuelve siempre ``False`` (COM-03 le suma la consulta)."""
        self.assertIs(clientes.impide_quitar_el_correo(self.cliente), False)

    def test_regla_2_modificar_un_inactivo_no_cambia_su_estado_ni_su_cuit(self):
        """Regla 2 de MOD: modificar un cliente inactivo no cambia su estado ni su CUIT."""
        inactivo = cliente(cuit="30000000090", activo=False)
        self.modificar(cliente_=inactivo, telefono="+54 376 400-1001")
        inactivo.refresh_from_db()
        self.assertEqual((inactivo.estado_cliente, inactivo.cuit_cliente), (Cliente.Estado.INACTIVO, "30000000090"))


class ComModCltRetiradasTests(ConGeoref, TestCase):
    """La pantalla manda siempre la corrección de cada dirección existente; si se la desactiva o se la borra, esa corrección no cuenta."""

    def setUp(self):
        self.vendedor = crear_vendedor()
        self.cliente = cliente(cuit="30712345671", razon_social="Los Pinos")
        self.vinculo = direccion_de_cliente(self.cliente)

    def modificar(self, **extra):
        self.cliente.refresh_from_db()
        corregida = (self.vinculo.direccion_id, datos_de_direccion(calle="Belgrano", numero_calle="45"))
        return clientes.modificar_cliente(
            self.vendedor, self.cliente.pk, datos_de_cliente_de(self.cliente, direcciones_corregidas=[corregida], **extra)
        )

    def test_post_e_desactivar_gana_a_la_correccion_enviada_para_la_misma_direccion(self):
        """Postcondición e: la dirección se desactiva y no se corrige (queda con sus datos)."""
        self.modificar(direcciones_desactivadas=[self.vinculo.direccion_id])
        hija = DireccionUrbana.objects.get(pk=self.vinculo.direccion_id)
        self.assertEqual((hija.estado_direccion, hija.calle), ("inactivo", "San Martín"))

    def test_regla_4_borrar_gana_a_la_correccion_enviada_para_la_misma_direccion(self):
        """Regla 4: la dirección se borra y la corrección enviada no la toca (ni da error de «dirección inválida»)."""
        self.modificar(direcciones_borradas=[self.vinculo.direccion_id])
        self.assertFalse(Direccion.objects.filter(pk=self.vinculo.direccion_id).exists())

    def test_regla_4_una_correccion_con_los_mismos_datos_no_cambia_nada(self):
        """D-28: corregir una dirección con lo que ya tiene no escribe ni audita."""
        clientes.modificar_cliente(
            self.vendedor,
            self.cliente.pk,
            datos_de_cliente_de(self.cliente, direcciones_corregidas=[(self.vinculo.direccion_id, datos_de_direccion())]),
        )
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_cliente").exists())
