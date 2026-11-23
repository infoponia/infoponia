# Pruebas de las pantallas de clientes de `comercial` (COM-01, paso 5; docs/casos_de_uso/comercial/clientes.md, «Pantallas»): la lista, la
# ficha, el formulario (alta, modificación y reactivación, con y sin JavaScript), la ventana de baja, el parámetro ``volver``, los
# fragmentos de HTMX de las direcciones y el menú. Las reglas de negocio ya las prueban los servicios (``test_com_*_clt.py``): acá, los
# permisos, el flujo, los errores por campo, los botones y que nada valida al tipear.

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from comercial.models import Cliente, DireccionCliente
from comercial.tests.fabricas import cliente, direccion_de_cliente
from core.menu import menu_de
from core.models import Notificacion, RegistroAuditoria, Usuario
from core.tests.fabricas import crear_gerente
from maestros.models import Direccion
from maestros.tests.fabricas import (
    ConGeoref,
    crear_agronomo,
    crear_capataz_activo,
    crear_transportista,
    crear_vendedor,
    localidad,
)

HTMX = {"HTTP_HX_REQUEST": "true"}
CUIT = "30-71234567-1"


def datos(**extra):
    """El POST de un cliente jurídico válido, como lo manda el formulario."""
    base = {"tipo_cliente": "juridica", "cuit": CUIT, "razon_social": "Los Pinos", "nombre": "", "apellido": "", "email": "", "telefono": ""}
    base.update(extra)
    return base


def nueva(i, tipo="urbana", **extra):
    """Los campos de una dirección nueva ``nueva-<i>`` como los manda el formulario."""
    campos = {"tipo_direccion": tipo, "localidad": localidad().pk}
    campos.update({"calle": "San Martín", "numero_calle": "123"} if tipo == "urbana" else {"ruta": "Ruta 12", "kilometro": "1034"})
    campos.update(extra)
    return {f"nueva-{i}-{campo}": valor for campo, valor in campos.items()}


def corregida(direccion_id, tipo="urbana", **extra):
    """Los campos de la corrección de una dirección existente, como los manda el formulario (siempre van todas)."""
    campos = {"tipo_direccion": tipo, "localidad": localidad().pk}
    campos.update({"calle": "San Martín", "numero_calle": "123"} if tipo == "urbana" else {"ruta": "Ruta 12", "kilometro": "1034"})
    campos.update(extra)
    return {f"corregida-{direccion_id}-{campo}": valor for campo, valor in campos.items()}


def avisos(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class ClientesPermisosTests(ConGeoref, TestCase):
    """Quién entra a cada pantalla (SEG-13, D-30)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor()
        self.cliente = cliente(cuit="30712345671", razon_social="Los Pinos")
        self.urls = [
            reverse("comercial:clientes"),
            reverse("comercial:cliente_nuevo"),
            reverse("comercial:cliente", args=[self.cliente.pk]),
            reverse("comercial:cliente_modificar", args=[self.cliente.pk]),
            reverse("comercial:direccion_campos") + "?prefijo=nueva-0",
        ]

    def test_pre_a_el_vendedor_y_el_gerente_abren_las_pantallas(self):
        """Precondición a de COM-ALT/MOD/CNS-CLT: Vendedor y Gerente activos."""
        for usuario in (self.vendedor, self.gerente):
            self.client.force_login(usuario)
            for url in self.urls:
                with self.subTest(rol=usuario.rol, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_pre_a_los_demas_roles_reciben_403_y_el_anonimo_va_al_inicio_de_sesion(self):
        """Los demás roles, 403 (también en el inicio de «Comercial» y en la baja); sin sesión, a iniciar sesión."""
        extra = [reverse("comercial:inicio"), reverse("comercial:cliente_baja", args=[self.cliente.pk])]
        for usuario in (crear_agronomo(), crear_transportista(), crear_capataz_activo()):
            self.client.force_login(usuario)
            for url in (*self.urls, *extra):
                with self.subTest(rol=usuario.rol, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        for url in self.urls:
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_regla_baj_el_vendedor_no_da_de_baja_ni_ve_el_boton(self):
        """COM-BAJ-CLT (MD-47): la URL de la baja le da 403 al Vendedor (GET y POST) y la ficha no se la ofrece."""
        self.client.force_login(self.vendedor)
        url = reverse("comercial:cliente_baja", args=[self.cliente.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertNotContains(self.client.get(reverse("comercial:cliente", args=[self.cliente.pk])), url)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estado_cliente, "activo")

    def test_regla_baj_el_gerente_ve_el_boton_de_baja(self):
        """D-30: el Gerente sí lo ve en un cliente activo."""
        self.client.force_login(self.gerente)
        url = reverse("comercial:cliente_baja", args=[self.cliente.pk])
        self.assertContains(self.client.get(reverse("comercial:cliente", args=[self.cliente.pk])), f'href="{url}"')

    def test_d30_la_ficha_de_un_inactivo_ofrece_modificar_y_reactivar_pero_no_la_baja(self):
        """Regla 2 de MOD y regla 3 de BAJ: «Modificar» y «Reactivar» (que lleva al formulario), nunca la baja."""
        inactivo = cliente(cuit="30000000090", activo=False, razon_social="Cerrado")
        for usuario in (self.gerente, self.vendedor):
            self.client.force_login(usuario)
            respuesta = self.client.get(reverse("comercial:cliente", args=[inactivo.pk]))
            self.assertContains(respuesta, reverse("comercial:cliente_modificar", args=[inactivo.pk]))
            self.assertContains(respuesta, reverse("comercial:cliente_reactivar", args=[inactivo.pk]))
            self.assertNotContains(respuesta, reverse("comercial:cliente_baja", args=[inactivo.pk]))
            self.assertContains(respuesta, "Cliente dado de baja. Sus contratos vigentes siguen ejecutándose; no puede celebrar contratos nuevos.")

    def test_pre_a_un_cliente_inexistente_da_404(self):
        """D-28: un id inexistente es 404."""
        self.client.force_login(self.gerente)
        for nombre in ("cliente", "cliente_modificar", "cliente_reactivar", "cliente_baja"):
            self.assertEqual(self.client.get(reverse(f"comercial:{nombre}", args=[999999])).status_code, 404)


class ClientesListaYFichaTests(ConGeoref, TestCase):
    """COM-CNS-CLT en pantalla."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor()
        self.pinos = cliente(cuit="30712345671", razon_social="Verdulería Los Pinos", email="compras@pinos.com")
        self.marta = cliente(tipo="fisica", cuit="20123456786", nombre="Marta", apellido="Gómez")
        direccion_de_cliente(self.pinos)

    def test_regla_1_la_lista_muestra_cliente_cuit_con_guiones_contacto_y_direcciones(self):
        """Columnas de COM-01: cliente con su tipo, CUIT con guiones, contacto, direcciones activas y estado."""
        self.client.force_login(self.vendedor)
        respuesta = self.client.get(reverse("comercial:clientes"))
        self.assertContains(respuesta, "Verdulería Los Pinos")
        self.assertContains(respuesta, "30-71234567-1")
        self.assertContains(respuesta, "compras@pinos.com")
        self.assertContains(respuesta, "Sin correo")
        self.assertContains(respuesta, "Persona física")
        self.assertContains(respuesta, "Los clientes son de toda la organización: cualquier Vendedor les puede vender. Solo el Gerente los da de baja.")

    def test_regla_1_los_filtros_son_un_formulario_get_sin_triggers_al_tipear(self):
        """Interfaz: la búsqueda es un formulario GET común (funciona sin JavaScript) y no dispara nada al tipear."""
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("comercial:clientes"))
        self.assertContains(respuesta, '<form class="filters" method="get"')
        for disparador in ('hx-trigger="input', 'hx-trigger="keyup', "input delay", "keyup"):
            self.assertNotContains(respuesta, disparador)

    def test_regla_1_busca_y_filtra_por_estado(self):
        """Regla 1: ``?q=`` por nombre o CUIT y ``?estado=``."""
        self.client.force_login(self.gerente)
        url = reverse("comercial:clientes")
        self.assertContains(self.client.get(url, {"q": "30-7123"}), "Verdulería Los Pinos")
        self.assertNotContains(self.client.get(url, {"q": "30-7123"}), "Marta Gómez")
        self.assertContains(self.client.get(url, {"q": "zzz"}), "Ningún cliente coincide con la búsqueda.")
        self.assertNotContains(self.client.get(url, {"estado": "inactivo"}), "Verdulería Los Pinos")

    def test_regla_1_sin_clientes_dice_como_empezar(self):
        """Estado vacío (D-61): un texto que dice cómo registrar el primero."""
        DireccionCliente.objects.all().delete()
        Cliente.objects.all().delete()
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(reverse("comercial:clientes")), "Todavía no hay clientes.")

    def test_regla_2_la_ficha_muestra_datos_y_direcciones_y_no_inventa_tarjetas(self):
        """Regla 2: datos y direcciones; sin las tarjetas de contratos ni de deuda hasta que existan (D-25)."""
        self.client.force_login(self.vendedor)
        respuesta = self.client.get(reverse("comercial:cliente", args=[self.pinos.pk]))
        self.assertContains(respuesta, "30-71234567-1")
        self.assertContains(respuesta, "compras@pinos.com")
        self.assertContains(respuesta, "San Martín 123")
        self.assertNotContains(respuesta, "Contratos")
        self.assertNotContains(respuesta, "Deuda")

    def test_regla_5_sin_correo_la_ficha_dice_necesario_para_pactar_suministros(self):
        """Regla 5 y «Correo»: «Necesario para pactar suministros» junto al correo."""
        self.client.force_login(self.vendedor)
        self.assertContains(self.client.get(reverse("comercial:cliente", args=[self.marta.pk])), "Necesario para pactar suministros")

    def test_regla_6_un_cliente_sin_direcciones_dice_cuando_se_piden(self):
        """MD-128: «Sin direcciones. Se piden al registrar un envío o un suministro.»"""
        self.client.force_login(self.vendedor)
        self.assertContains(self.client.get(reverse("comercial:cliente", args=[self.marta.pk])), "Sin direcciones. Se piden al registrar un envío o un suministro.")


class ClientesAltaVistaTests(ConGeoref, TestCase):
    """COM-ALT-CLT en pantalla."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor()
        self.client.force_login(self.vendedor)
        self.url = reverse("comercial:cliente_nuevo")

    def test_flujo_principal_el_formulario_trae_los_textos_explicativos_y_no_valida_al_tipear(self):
        """Textos del extracto, el tipo de cliente con sus dos fichas y nada de ``hx-trigger`` en los campos de texto."""
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Son opcionales. Se piden recién para una compra-venta con envío o para un suministro.")
        self.assertContains(respuesta, "Persona jurídica")
        self.assertContains(respuesta, "Persona física")
        self.assertContains(respuesta, "Sin correo no se puede pactar un suministro.")
        self.assertContains(respuesta, "novalidate")
        for disparador in ('hx-trigger="input', 'hx-trigger="keyup', "input delay", "keyup"):
            self.assertNotContains(respuesta, disparador)

    def test_flujo_principal_registra_el_cliente_y_va_a_su_ficha_con_un_aviso(self):
        """Sin JavaScript: un POST común crea el cliente y redirige a su ficha con un aviso breve (D-29)."""
        respuesta = self.client.post(self.url, datos(email="compras@pinos.com"))
        creado = Cliente.objects.get()
        self.assertRedirects(respuesta, reverse("comercial:cliente", args=[creado.pk]))
        self.assertEqual(avisos(respuesta), ["Cliente registrado: Los Pinos."])
        self.assertEqual(creado.cuit_cliente, "30712345671")

    def test_flujo_principal_con_direcciones_urbana_y_rural(self):
        """Postcondición b: las direcciones del formulario se crean con el cliente."""
        self.client.post(self.url, {**datos(), **nueva(0), **nueva(1, "rural")})
        self.assertEqual(Cliente.objects.get().direcciones.count(), 2)

    def test_regla_6_un_bloque_de_direccion_vacio_se_ignora(self):
        """Un bloque de «Agregar dirección» que quedó sin usar no es un error ni crea nada."""
        vacio = {"nueva-0-tipo_direccion": "urbana", "nueva-0-calle": "", "nueva-0-numero_calle": "", "nueva-0-localidad": ""}
        self.client.post(self.url, {**datos(), **vacio})
        self.assertEqual(Cliente.objects.get().direcciones.count(), 0)

    def test_regla_6_agregar_direccion_redibuja_sin_guardar_y_conserva_lo_escrito(self):
        """Sin JavaScript, «Agregar dirección» suma un bloque nuevo, no guarda nada y conserva lo escrito."""
        respuesta = self.client.post(self.url, {**datos(razon_social="Escrito a medias"), **nueva(0), "agregar_direccion": "1"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Cliente.objects.exists())
        self.assertContains(respuesta, 'name="nueva-0-calle"')
        self.assertContains(respuesta, 'name="nueva-1-calle"')
        self.assertContains(respuesta, "Escrito a medias")
        self.assertContains(respuesta, "San Martín")

    def test_regla_6_actualizar_redibuja_sin_guardar(self):
        """«Actualizar» (sin JavaScript) reenvía el formulario sin guardar ni validar."""
        respuesta = self.client.post(self.url, {**datos(cuit="x"), **nueva(0), "actualizar": "1"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Cliente.objects.exists())
        self.assertNotContains(respuesta, "El CUIT no es válido")

    def test_regla_1_un_cuit_invalido_da_error_en_el_campo_y_conserva_lo_escrito(self):
        """Regla 1: el error va junto al campo y el formulario conserva lo escrito."""
        respuesta = self.client.post(self.url, datos(cuit="30-71234567-2", razon_social="Conservada", email="a@b.com"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El CUIT no es válido: revisá los números (11 dígitos, con su dígito verificador).")
        self.assertContains(respuesta, "Conservada")
        self.assertContains(respuesta, "a@b.com")
        self.assertFalse(Cliente.objects.exists())

    def test_regla_3_los_errores_de_cada_campo_van_a_su_campo(self):
        """Reglas 3 a 5: razón social, teléfono y correo, todos a la vez."""
        respuesta = self.client.post(self.url, datos(razon_social="", telefono="abc", email="mal"))
        self.assertContains(respuesta, "Ingresá la razón social.")
        self.assertContains(respuesta, "El teléfono solo puede tener números")
        self.assertContains(respuesta, "dirección de email válida")

    def test_regla_6_los_errores_de_una_direccion_van_al_campo_de_esa_direccion(self):
        """Regla 6: ``nueva-<i>-<campo>`` se muestra junto al campo de su bloque."""
        respuesta = self.client.post(self.url, {**datos(), **nueva(0, calle="")})
        self.assertContains(respuesta, "Ingresá la calle.")
        self.assertFalse(Cliente.objects.exists())

    def test_regla_6_una_direccion_repetida_se_informa(self):
        """Regla 6: «El cliente ya tiene esa dirección.»"""
        respuesta = self.client.post(self.url, {**datos(), **nueva(0), **nueva(1, calle="san martín")})
        self.assertContains(respuesta, "El cliente ya tiene esa dirección.")

    def test_regla_2_el_cuit_de_un_cliente_activo_ofrece_abrir_su_ficha(self):
        """Regla 2: aviso con «Abrir su ficha», que lleva a la ficha del cliente existente."""
        existente = cliente(cuit="30712345671")
        respuesta = self.client.post(self.url, datos())
        self.assertContains(respuesta, "Abrir su ficha")
        self.assertContains(respuesta, reverse("comercial:cliente", args=[existente.pk]))

    def test_regla_2_el_cuit_de_un_cliente_inactivo_ofrece_reactivarlo_y_avisa_al_gerente(self):
        """Regla 2: «Reactivarlo» lleva al formulario de reactivación; al Vendedor se le dice que se avisa al Gerente."""
        inactivo = cliente(cuit="30712345671", activo=False)
        respuesta = self.client.post(self.url, datos())
        self.assertContains(respuesta, "Reactivarlo")
        self.assertContains(respuesta, reverse("comercial:cliente_reactivar", args=[inactivo.pk]))
        self.assertContains(respuesta, "Se le avisa al Gerente.")

    def test_regla_7_volver_acepta_solo_urls_internas(self):
        """Regla 7: tras guardar vuelve a la URL interna de ``volver``; una externa se descarta y va a la ficha."""
        interna = reverse("comercial:clientes") + "?q=pinos"
        respuesta = self.client.post(self.url, {**datos(), "volver": interna})
        self.assertRedirects(respuesta, interna, fetch_redirect_response=False)
        Cliente.objects.all().delete()
        for externa in ("https://evil.example.com/", "//evil.example.com/", "javascript:alert(1)"):
            with self.subTest(volver=externa):
                Cliente.objects.all().delete()
                respuesta = self.client.post(self.url, {**datos(), "volver": externa})
                self.assertRedirects(respuesta, reverse("comercial:cliente", args=[Cliente.objects.get().pk]))

    def test_regla_7_el_formulario_conserva_el_parametro_volver_solo_si_es_interno(self):
        """Regla 7: el ``volver`` interno viaja en un campo oculto; uno externo se descarta."""
        self.assertContains(self.client.get(self.url, {"volver": "/comercial/clientes/"}), 'name="volver" value="/comercial/clientes/"')
        self.assertNotContains(self.client.get(self.url, {"volver": "https://evil.example.com/"}), 'name="volver"')

    def test_flujo_principal_el_formulario_tiene_un_boton_de_guardar_primero(self):
        """Interfaz: con Enter en un campo se guarda; el primer botón del formulario no es «Agregar dirección»."""
        contenido = self.client.get(self.url).content.decode()
        self.assertLess(contenido.index(">Guardar</button>"), contenido.index('name="agregar_direccion"'))


class ClientesModificarVistaTests(ConGeoref, TestCase):
    """COM-MOD-CLT en pantalla."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor()
        self.client.force_login(self.vendedor)
        self.cliente = cliente(cuit="30712345671", razon_social="Los Pinos")
        self.urbana = direccion_de_cliente(self.cliente)
        self.rural = direccion_de_cliente(self.cliente, "rural")
        self.url = reverse("comercial:cliente_modificar", args=[self.cliente.pk])

    def post(self, **extra):
        """Lo que manda el navegador: los datos del cliente y la corrección de cada dirección existente, sin cambios."""
        return self.client.post(
            self.url, {**datos(), **corregida(self.urbana.direccion_id), **corregida(self.rural.direccion_id, "rural"), **extra}
        )

    def test_flujo_principal_el_formulario_arranca_con_los_datos_y_las_direcciones_del_cliente(self):
        """Los datos guardados (CUIT con guiones) y cada dirección existente con sus campos."""
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'value="30-71234567-1"')
        self.assertContains(respuesta, 'value="Los Pinos"')
        self.assertContains(respuesta, f'name="corregida-{self.urbana.direccion_id}-calle"')
        self.assertContains(respuesta, 'value="San Martín"')
        self.assertContains(respuesta, f'name="corregida-{self.rural.direccion_id}-ruta"')

    def test_post_a_sin_cambios_no_audita_y_vuelve_a_la_ficha(self):
        """D-28: guardar sin cambiar nada no escribe ni audita."""
        respuesta = self.post()
        self.assertRedirects(respuesta, reverse("comercial:cliente", args=[self.cliente.pk]))
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_cliente").exists())

    def test_post_c_corrige_una_direccion(self):
        """Postcondición c: la corrección de una dirección se guarda en el lugar."""
        self.post(**corregida(self.urbana.direccion_id, calle="Belgrano", numero_calle="45"))
        self.assertEqual(Direccion.objects.get(pk=self.urbana.direccion_id).concreta().calle, "Belgrano")

    def test_post_e_desactivar_gana_a_la_correccion_que_el_formulario_manda_siempre(self):
        """Postcondición e: tildar «Desactivar al guardar» desactiva la dirección aunque su corrección viaje en el formulario."""
        self.post(desactivar=str(self.urbana.direccion_id))
        self.assertEqual(Direccion.objects.get(pk=self.urbana.direccion_id).estado_direccion, "inactivo")
        self.assertEqual(Direccion.objects.get(pk=self.rural.direccion_id).estado_direccion, "activo")

    def test_regla_4_borrar_una_direccion_sin_uso(self):
        """Regla 4: tildar «Borrar al guardar» borra una dirección que nada usa."""
        self.post(borrar=str(self.rural.direccion_id))
        self.assertFalse(Direccion.objects.filter(pk=self.rural.direccion_id).exists())

    def test_regla_4_con_una_direccion_en_uso_no_se_ofrece_borrar(self):
        """Regla 4: «Borrar» no se ofrece si un contrato la usa (con ``direcciones_en_uso`` simulada)."""
        from unittest import mock

        from comercial.servicios import clientes

        with mock.patch.object(clientes, "direcciones_en_uso", return_value={self.urbana.direccion_id}):
            respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "La usa un contrato: no se borra.")
        self.assertContains(respuesta, f'name="borrar" value="{self.rural.direccion_id}"')
        self.assertNotContains(respuesta, f'name="borrar" value="{self.urbana.direccion_id}"')

    def test_regla_6_una_direccion_inactiva_se_muestra_con_su_marca_sin_acciones(self):
        """Postcondición e: una inactiva se muestra con su marca y no se corrige ni se reactiva."""
        self.post(desactivar=str(self.urbana.direccion_id))
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Inactiva")
        self.assertNotContains(respuesta, f'name="corregida-{self.urbana.direccion_id}-calle"')

    def test_pre_b_un_cuit_de_otro_cliente_da_el_error_con_su_ficha(self):
        """Precondición b: el CUIT nuevo no puede ser el de otro cliente; el error ofrece abrir su ficha."""
        otro = cliente(cuit="30000000090")
        respuesta = self.post(cuit="30-00000009-0")
        self.assertContains(respuesta, "Abrir su ficha")
        self.assertContains(respuesta, reverse("comercial:cliente", args=[otro.pk]))

    def test_regla_2_se_puede_modificar_un_inactivo_y_sigue_inactivo(self):
        """Regla 2: modificar un cliente inactivo no lo reactiva."""
        Cliente.objects.filter(pk=self.cliente.pk).update(estado_cliente="inactivo")
        self.post(telefono="+54 376 400-1001")
        self.cliente.refresh_from_db()
        self.assertEqual((self.cliente.estado_cliente, self.cliente.telefono_cliente), ("inactivo", "+54 376 400-1001"))

    def test_regla_3_el_error_de_una_direccion_corregida_abre_su_bloque(self):
        """Regla 4 de ALT: el error de una corrección se ve junto a su campo."""
        respuesta = self.post(**corregida(self.urbana.direccion_id, calle=""))
        self.assertContains(respuesta, "Ingresá la calle.")


class ClientesReactivarVistaTests(ConGeoref, TestCase):
    """Reactivar (parte de COM-ALT-CLT) en pantalla."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor(nombre="Valeria", apellido="Ríos")
        self.inactivo = cliente(cuit="30712345671", razon_social="Los Pinos", activo=False)
        self.url = reverse("comercial:cliente_reactivar", args=[self.inactivo.pk])

    def test_regla_2_reactivar_abre_el_formulario_del_alta_con_los_datos_guardados(self):
        """Regla 2: «Reactivarlo» abre el mismo formulario del alta con los datos guardados."""
        self.client.force_login(self.vendedor)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Reactivar Los Pinos")
        self.assertContains(respuesta, 'value="30-71234567-1"')
        self.assertContains(respuesta, "se le avisa al Gerente")

    def test_post_c_el_vendedor_reactiva_con_datos_corregidos_y_el_gerente_recibe_el_aviso(self):
        """Postcondición c: queda activo con lo corregido y el Gerente recibe «Cliente reactivado: …»."""
        self.client.force_login(self.vendedor)
        respuesta = self.client.post(self.url, datos(razon_social="Los Pinos S.A.", telefono="+54 376 400-1001"))
        self.assertRedirects(respuesta, reverse("comercial:cliente", args=[self.inactivo.pk]))
        self.assertEqual(avisos(respuesta), ["Los Pinos S.A. está activo de nuevo. Se notificó al Gerente."])
        self.inactivo.refresh_from_db()
        self.assertEqual((self.inactivo.estado_cliente, self.inactivo.razon_social_cliente), ("activo", "Los Pinos S.A."))
        self.assertEqual(Notificacion.objects.get(destinatario=self.gerente).titulo, "Cliente reactivado: Los Pinos S.A.")

    def test_post_c_el_gerente_reactiva_sin_avisar_a_nadie(self):
        """Postcondición c: el aviso es solo cuando reactiva un Vendedor."""
        self.client.force_login(self.gerente)
        respuesta = self.client.post(self.url, datos())
        self.assertEqual(avisos(respuesta), ["Los Pinos está activo de nuevo."])
        self.assertFalse(Notificacion.objects.exists())

    def test_d30_reactivar_un_cliente_activo_vuelve_a_la_ficha_con_el_motivo(self):
        """D-30: sin 403; vuelve a la ficha con el motivo."""
        self.client.force_login(self.vendedor)
        activo = cliente(cuit="30000000090")
        respuesta = self.client.get(reverse("comercial:cliente_reactivar", args=[activo.pk]))
        self.assertRedirects(respuesta, reverse("comercial:cliente", args=[activo.pk]))
        self.assertEqual(avisos(respuesta), ["El cliente no está dado de baja."])


class ClientesBajaVistaTests(ConGeoref, TestCase):
    """COM-BAJ-CLT en pantalla."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.force_login(self.gerente)
        self.cliente = cliente(cuit="30712345671", razon_social="Los Pinos")
        self.url = reverse("comercial:cliente_baja", args=[self.cliente.pk])

    def test_regla_1_con_htmx_llega_solo_la_ventana_con_su_texto_y_sin_pendientes(self):
        """Con HTMX, solo la ventana; informa lo pendiente (hoy nada) y que se puede reactivar. Abrirla no cambia nada."""
        respuesta = self.client.get(self.url, **HTMX)
        self.assertNotContains(respuesta, "<html")
        self.assertContains(respuesta, "No podrá celebrar contratos nuevos. Lo que tenga pendiente sigue su curso. Se puede reactivar después.")
        self.assertContains(respuesta, "No tiene contratos ni entregas pendientes.")
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estado_cliente, "activo")

    def test_regla_1_sin_javascript_la_ventana_es_la_ficha_con_la_ventana_abierta(self):
        """Respaldo sin JavaScript: la ficha completa con la ventana abierta."""
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "<html")
        self.assertContains(respuesta, "¿Dar de baja a Los Pinos?")
        self.assertContains(respuesta, "data-cerrar-ventana")

    def test_regla_1_con_pendientes_los_lista_y_no_bloquea(self):
        """Regla 1: la baja informa lo pendiente y no se bloquea (con ``pendientes_del_cliente`` simulada)."""
        from unittest import mock

        from comercial.servicios import clientes

        with mock.patch.object(clientes, "pendientes_del_cliente", return_value=["2 entregas sin cobrar"]):
            respuesta = self.client.get(self.url, **HTMX)
            self.assertContains(respuesta, "2 entregas sin cobrar")
            respuesta = self.client.post(self.url)
        self.assertEqual(respuesta.status_code, 302)

    def test_post_a_confirmar_da_de_baja_y_vuelve_a_la_ficha_con_un_aviso(self):
        """Postcondición a: pasa a inactivo y vuelve a la ficha con un aviso."""
        respuesta = self.client.post(self.url)
        self.assertRedirects(respuesta, reverse("comercial:cliente", args=[self.cliente.pk]))
        self.assertEqual(avisos(respuesta), ["Los Pinos se dio de baja."])
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estado_cliente, "inactivo")

    def test_d30_la_baja_de_un_inactivo_vuelve_a_la_ficha_con_el_motivo(self):
        """D-30: sin 403; vuelve a la ficha con el motivo."""
        Cliente.objects.filter(pk=self.cliente.pk).update(estado_cliente="inactivo")
        respuesta = self.client.get(self.url)
        self.assertRedirects(respuesta, reverse("comercial:cliente", args=[self.cliente.pk]))
        self.assertEqual(avisos(respuesta), ["El cliente ya está dado de baja."])


class DireccionesFragmentosTests(ConGeoref, TestCase):
    """Los fragmentos de HTMX de las listas encadenadas (D-58, punto 7): solo GET, sin validar nada."""

    def setUp(self):
        self.client.force_login(crear_vendedor())
        self.loc = localidad()

    def test_d58_los_campos_cambian_con_el_tipo_y_conservan_lo_escrito(self):
        """``direccion/campos/``: calle y número (urbana) o ruta y kilómetro (rural), con el prefijo del bloque y sin perder lo escrito."""
        url = reverse("comercial:direccion_campos")
        urbana = self.client.get(url, {"prefijo": "nueva-0", "nueva-0-tipo_direccion": "urbana", "nueva-0-calle": "Mitre"}, **HTMX)
        self.assertContains(urbana, 'name="nueva-0-calle"')
        self.assertContains(urbana, 'value="Mitre"')
        self.assertNotContains(urbana, 'name="nueva-0-ruta"')
        rural = self.client.get(url, {"prefijo": "nueva-0", "nueva-0-tipo_direccion": "rural"}, **HTMX)
        self.assertContains(rural, 'name="nueva-0-ruta"')
        self.assertNotContains(rural, 'name="nueva-0-calle"')

    def test_d58_los_departamentos_salen_de_la_provincia_elegida_y_la_localidad_se_vacia(self):
        """``direccion/departamentos/``: los departamentos de Georef de la provincia, y la localidad sin opciones."""
        respuesta = self.client.get(
            reverse("comercial:direccion_departamentos"),
            {"prefijo": "corregida-5", "corregida-5-provincia": self.loc.departamento.provincia_id},
            **HTMX,
        )
        self.assertContains(respuesta, 'name="corregida-5-departamento"')
        self.assertContains(respuesta, self.loc.departamento.nombre_departamento)
        self.assertNotContains(respuesta, self.loc.nombre_localidad)

    def test_d58_las_localidades_salen_del_departamento_elegido(self):
        """``direccion/localidades/``: las localidades de Georef del departamento."""
        respuesta = self.client.get(
            reverse("comercial:direccion_localidades"),
            {"prefijo": "nueva-0", "nueva-0-departamento": self.loc.departamento_id},
            **HTMX,
        )
        self.assertContains(respuesta, 'name="nueva-0-localidad"')
        self.assertContains(respuesta, self.loc.nombre_localidad)

    def test_d58_un_prefijo_que_no_es_de_una_direccion_da_404(self):
        """Seguridad: el prefijo se valida (``nueva-<i>`` o ``corregida-<id>``)."""
        for prefijo in ("", "otra", 'nueva-0"><script>', "nueva-x"):
            with self.subTest(prefijo=prefijo):
                self.assertEqual(self.client.get(reverse("comercial:direccion_campos"), {"prefijo": prefijo}).status_code, 404)

    def test_d58_son_solo_get(self):
        """D-58 punto 7: un POST no está permitido (405)."""
        for nombre in ("direccion_campos", "direccion_departamentos", "direccion_localidades"):
            self.assertEqual(self.client.post(reverse(f"comercial:{nombre}") + "?prefijo=nueva-0").status_code, 405)

    def test_interfaz_los_selectores_piden_el_fragmento_sin_validar_y_sin_mover_el_scroll(self):
        """Interfaz (INV-02): ``hx-swap="innerHTML show:none"``, solo al cambiar un desplegable, con el prefijo de su bloque; sin
        ningún trigger sobre los campos de texto."""
        contenido = self.client.get(reverse("comercial:cliente_nuevo"), **{}).content.decode()
        self.assertNotIn("show:none", contenido)  # sin bloques de dirección no hay selectores
        contenido = self.client.post(reverse("comercial:cliente_nuevo"), {"agregar_direccion": "1"}).content.decode()
        self.assertIn('hx-swap="innerHTML show:none"', contenido)
        self.assertIn("hx-trigger=\"change\"", contenido)
        self.assertNotIn("keyup", contenido)
        self.assertNotIn("input delay", contenido)
        self.assertIn("hx-get=\"" + reverse("comercial:direccion_departamentos") + "\"", contenido)
        self.assertIn("&quot;prefijo&quot;: &quot;nueva-0&quot;", contenido)


class MenuDeComercialTests(TestCase):
    """La entrada «Comercial» del menú (``ComercialConfig.ready()``)."""

    def textos(self, rol):
        return [texto for texto, _, _ in menu_de(rol)]

    def test_menu_el_vendedor_ve_comercial_despues_del_panel_de_control(self):
        """El Vendedor no tiene «Producción»: «Comercial» queda después de «Panel de control»."""
        self.assertEqual(self.textos(Usuario.Rol.VENDEDOR), ["Panel de control", "Comercial"])
        self.assertIn(("Comercial", "comercial:inicio", "cart"), menu_de(Usuario.Rol.VENDEDOR))

    def test_menu_el_gerente_ve_comercial_despues_de_produccion(self):
        """El Gerente lo ve justo después de «Producción» o de lo que se registre pegado a ella (``IoT``, ``Alertas``…)."""
        textos = self.textos(Usuario.Rol.GERENTE)
        self.assertIn("Comercial", textos)
        self.assertGreater(textos.index("Comercial"), textos.index("Producción"))

    def test_menu_los_demas_roles_no_lo_ven_y_no_se_repite(self):
        """Los demás roles no tienen la entrada; ``ready()`` no la repite."""
        from django.apps import apps

        apps.get_app_config("comercial").ready()
        for rol in (Usuario.Rol.AGRONOMO, Usuario.Rol.CAPATAZ, Usuario.Rol.TECNICO, Usuario.Rol.TRANSPORTISTA):
            self.assertNotIn("Comercial", self.textos(rol))
        self.assertEqual(self.textos(Usuario.Rol.GERENTE).count("Comercial"), 1)
        self.assertEqual(self.textos(Usuario.Rol.VENDEDOR).count("Comercial"), 1)

    def test_menu_el_inicio_lleva_a_los_clientes_y_la_entrada_se_marca_activa(self):
        """«Comercial» abre en «Clientes»; el menú la marca activa en sus pantallas internas."""
        self.client.force_login(crear_vendedor())
        self.assertRedirects(self.client.get(reverse("comercial:inicio")), reverse("comercial:clientes"))
        pagina = self.client.get(reverse("comercial:clientes"))
        self.assertContains(pagina, 'aria-current="page"')
        self.assertContains(pagina, "Clientes")
        self.assertNotContains(pagina, "Vehículos")  # el Vendedor no tiene la pestaña

    def test_menu_el_gerente_ve_las_pestanas_clientes_y_vehiculos(self):
        """Pestañas de COM-01: «Clientes» y, solo para el Gerente, «Vehículos»."""
        self.client.force_login(crear_gerente())
        pagina = self.client.get(reverse("comercial:clientes"))
        self.assertContains(pagina, f'href="{reverse("comercial:vehiculos")}"')
