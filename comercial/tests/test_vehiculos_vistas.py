# Pruebas de las pantallas de vehículos de `comercial` (COM-01, paso 5; docs/casos_de_uso/comercial/vehiculos.md, «Pantallas»): la lista, la
# ficha, el formulario (alta y modificación), la ventana de baja y la reactivación. Las reglas de negocio ya las prueban los servicios
# (``test_com_*_veh.py``): acá, los permisos (solo el Gerente), el flujo, los errores por campo y los botones.

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from comercial.models import Vehiculo
from comercial.tests.fabricas import vehiculo
from core.models import Notificacion
from core.tests.fabricas import crear_gerente
from maestros.tests.fabricas import (
    ConGeoref,
    asignar_transportista,
    crear_agronomo,
    crear_capataz_activo,
    crear_invernadero,
    crear_transportista,
    crear_vendedor,
)

HTMX = {"HTTP_HX_REQUEST": "true"}


def datos(**extra):
    """El POST de un vehículo válido, como lo manda el formulario."""
    base = {"patente": "ae-123 cd", "tipo_vehiculo": "camioneta", "marca": "Ford", "modelo": "Ranger", "capacidad_carga": "800", "transportista_id": ""}
    base.update(extra)
    return base


def avisos(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class VehiculosPermisosTests(ConGeoref, TestCase):
    """Solo el Gerente (SEG-13, D-30)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vehiculo = vehiculo(patente="AE123CD")
        self.urls = [
            reverse("comercial:vehiculos"),
            reverse("comercial:vehiculo_nuevo"),
            reverse("comercial:vehiculo", args=[self.vehiculo.pk]),
            reverse("comercial:vehiculo_modificar", args=[self.vehiculo.pk]),
            reverse("comercial:vehiculo_baja", args=[self.vehiculo.pk]),
        ]

    def test_pre_a_el_gerente_abre_las_pantallas(self):
        """Precondición a de COM-ALT/MOD/BAJ/CNS-VEH: Gerente activo."""
        self.client.force_login(self.gerente)
        for url in self.urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_pre_a_el_vendedor_y_los_demas_roles_reciben_403_en_todas_las_rutas(self):
        """Precondición a: el Vendedor no abre «Vehículos» ni por la URL (GET y POST); tampoco los demás roles."""
        extra = reverse("comercial:vehiculo_reactivar", args=[self.vehiculo.pk])
        for usuario in (crear_vendedor(), crear_agronomo(), crear_transportista(), crear_capataz_activo()):
            self.client.force_login(usuario)
            for url in self.urls:
                with self.subTest(rol=usuario.rol, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(extra).status_code, 403)
            self.assertEqual(self.client.post(self.urls[1], datos()).status_code, 403)
        self.assertEqual(Vehiculo.objects.count(), 1)

    def test_pre_a_sin_sesion_va_al_inicio_de_sesion(self):
        """Sin sesión: redirige a iniciar sesión."""
        for url in self.urls:
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_pre_a_el_vendedor_no_ve_la_pestana_vehiculos(self):
        """D-30: la pestaña «Vehículos» es solo del Gerente (el Vendedor no la ve, nadie llega por un enlace a un 403)."""
        self.client.force_login(crear_vendedor())
        self.assertNotContains(self.client.get(reverse("comercial:clientes")), reverse("comercial:vehiculos"))

    def test_pre_a_un_vehiculo_inexistente_da_404(self):
        """D-28: un id inexistente es 404."""
        self.client.force_login(self.gerente)
        for nombre in ("vehiculo", "vehiculo_modificar", "vehiculo_baja"):
            self.assertEqual(self.client.get(reverse(f"comercial:{nombre}", args=[999999])).status_code, 404)


class VehiculosListaYFichaTests(ConGeoref, TestCase):
    """COM-CNS-VEH en pantalla."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.force_login(self.gerente)
        self.norte = crear_invernadero("Norte")
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        asignar_transportista(self.diego, self.norte)
        self.camioneta = vehiculo(patente="AE123CD", capacidad="800.5", transportista=self.diego)
        self.sin = vehiculo(patente="ABC123", tipo="moto", activo=False)

    def test_regla_1_la_lista_muestra_las_columnas_de_com_01(self):
        """Columnas: patente, tipo y modelo, capacidad (con su texto), transportista con su invernadero, situación y estado; el texto
        explicativo de la pestaña."""
        respuesta = self.client.get(reverse("comercial:vehiculos"))
        self.assertContains(respuesta, "AE123CD")
        self.assertContains(respuesta, "Camioneta")
        self.assertContains(respuesta, "800,5 kg")
        self.assertContains(respuesta, "Diego Ferreyra")
        self.assertContains(respuesta, "Norte")
        self.assertContains(respuesta, "Sin transportista")
        self.assertContains(respuesta, "Con estos vehículos los transportistas hacen las entregas con envío. Cada vehículo tiene a lo sumo un transportista y trabaja para el invernadero de él.")
        self.assertContains(respuesta, "Entregas a realizar")  # la columna la suma COM-05a2 (antes de ella, esta prueba afirmaba que no estaba)

    def test_regla_1_filtra_por_texto_estado_e_invernadero(self):
        """Regla 1: ``?q=``, ``?estado=`` e ``?invernadero=``."""
        url = reverse("comercial:vehiculos")
        self.assertNotContains(self.client.get(url, {"q": "diego"}), "ABC123")
        self.assertNotContains(self.client.get(url, {"estado": "inactivo"}), "AE123CD")
        self.assertNotContains(self.client.get(url, {"invernadero": self.norte.pk}), "ABC123")
        self.assertContains(self.client.get(url, {"q": "zzz"}), "Ningún vehículo coincide con la búsqueda.")

    def test_regla_1_la_lista_en_ruta_muestra_la_situacion(self):
        """MD-118: «En ruta» solo para el que la inició hoy."""
        vehiculo(patente="ABC999", transportista=crear_transportista("otro@infoponia.com"), en_ruta_hoy=True)
        self.assertContains(self.client.get(reverse("comercial:vehiculos")), "En ruta")

    def test_regla_2_la_ficha_muestra_datos_transportista_e_invernadero(self):
        """Regla 2: datos, transportista, invernadero y la situación; sin la tarjeta de carga asignada hasta COM-05 (D-25)."""
        respuesta = self.client.get(reverse("comercial:vehiculo", args=[self.camioneta.pk]))
        self.assertContains(respuesta, "AE123CD")
        self.assertContains(respuesta, "Ford Ranger")
        self.assertContains(respuesta, "800,5 kg")
        self.assertContains(respuesta, "Diego Ferreyra")
        self.assertContains(respuesta, "Norte")
        self.assertContains(respuesta, "En el invernadero")
        self.assertNotContains(respuesta, "Carga asignada")

    def test_d30_la_ficha_ofrece_las_acciones_segun_el_estado(self):
        """D-30: activo, «Modificar» y «Dar de baja»; inactivo, solo «Reactivar» (no se modifica ni se vuelve a dar de baja)."""
        activo = self.client.get(reverse("comercial:vehiculo", args=[self.camioneta.pk]))
        self.assertContains(activo, reverse("comercial:vehiculo_modificar", args=[self.camioneta.pk]))
        self.assertContains(activo, reverse("comercial:vehiculo_baja", args=[self.camioneta.pk]))
        self.assertNotContains(activo, reverse("comercial:vehiculo_reactivar", args=[self.camioneta.pk]))
        inactivo = self.client.get(reverse("comercial:vehiculo", args=[self.sin.pk]))
        self.assertContains(inactivo, reverse("comercial:vehiculo_reactivar", args=[self.sin.pk]))
        self.assertNotContains(inactivo, reverse("comercial:vehiculo_modificar", args=[self.sin.pk]))
        self.assertNotContains(inactivo, reverse("comercial:vehiculo_baja", args=[self.sin.pk]))

    def test_regla_2_un_transportista_sin_invernadero_se_avisa_en_la_ficha(self):
        """Regla 4 de ALT: sin invernadero, no recibe entregas hasta que se lo agregue a uno."""
        suelto = vehiculo(patente="ZZZ999", transportista=crear_transportista("suelto@infoponia.com"))
        self.assertContains(self.client.get(reverse("comercial:vehiculo", args=[suelto.pk])), "No recibe entregas hasta que se lo agregue a uno, en «Logística».")


class VehiculosFormularioVistaTests(ConGeoref, TestCase):
    """COM-ALT-VEH y COM-MOD-VEH en pantalla."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.force_login(self.gerente)
        self.norte = crear_invernadero("Norte")
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        self.carla = crear_transportista("carla@infoponia.com", nombre="Carla", apellido="Sosa")
        asignar_transportista(self.diego, self.norte)  # Carla queda sin invernadero
        self.url = reverse("comercial:vehiculo_nuevo")

    def test_flujo_principal_el_formulario_trae_los_textos_y_ofrece_a_los_libres(self):
        """Textos del extracto y solo los transportistas activos sin otro vehículo, con su invernadero o «sin invernadero»."""
        vehiculo(patente="ABC123", transportista=crear_transportista("ocupado@infoponia.com", nombre="Oscar", apellido="Ocupado"))
        crear_transportista("inactivo@infoponia.com", nombre="Ines", apellido="Inactiva", activo=False)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Peso máximo que lleva en el día, en un solo viaje. Los envases no cuentan.")
        self.assertContains(respuesta, "Solo transportistas activos sin otro vehículo. El vehículo trabaja para el invernadero de su transportista.")
        self.assertContains(respuesta, "Diego Ferreyra · Norte")
        self.assertContains(respuesta, "Carla Sosa · sin invernadero")
        self.assertNotContains(respuesta, "Oscar Ocupado")
        self.assertNotContains(respuesta, "Ines Inactiva")
        self.assertContains(respuesta, 'name="marca"')
        self.assertContains(respuesta, 'name="modelo"')  # son dos campos (MD-129)
        self.assertContains(respuesta, "novalidate")

    def test_flujo_principal_registra_el_vehiculo_normaliza_la_patente_y_avisa_al_transportista(self):
        """Sin JavaScript: un POST común crea el vehículo (patente normalizada), notifica al transportista y va a la ficha con un aviso."""
        respuesta = self.client.post(self.url, datos(transportista_id=self.diego.pk))
        creado = Vehiculo.objects.get()
        self.assertRedirects(respuesta, reverse("comercial:vehiculo", args=[creado.pk]))
        self.assertEqual(avisos(respuesta), ["Vehículo registrado: AE123CD."])
        self.assertEqual(creado.transportista_id, self.diego.pk)
        self.assertEqual(Notificacion.objects.get(destinatario=self.diego).titulo, "Tenés un vehículo asignado")

    def test_regla_1_los_errores_van_por_campo_y_el_formulario_conserva_lo_escrito(self):
        """Reglas 1 a 3: cada error junto a su campo, todos a la vez, y lo escrito se conserva."""
        respuesta = self.client.post(self.url, datos(patente="x", marca="", capacidad_carga="0", modelo="Conservado"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ingresá una patente argentina: AAA123 o AA123AA.")
        self.assertContains(respuesta, "Ingresá la marca.")
        self.assertContains(respuesta, "Un número mayor que 0, en kg, con hasta 2 decimales.")
        self.assertContains(respuesta, "Conservado")
        self.assertFalse(Vehiculo.objects.exists())

    def test_regla_1_una_patente_repetida_se_informa(self):
        """Regla 1: ``patente_repetida`` junto al campo."""
        vehiculo(patente="AE123CD")
        self.assertContains(self.client.post(self.url, datos()), "Ya hay un vehículo con esa patente.")

    def test_regla_4_un_transportista_sin_invernadero_se_puede_asignar_y_el_aviso_lo_dice(self):
        """Regla 4: se acepta; el formulario avisa «No recibe entregas hasta que se lo agregue a un invernadero, en "Logística".»"""
        respuesta = self.client.post(self.url, datos(transportista_id=self.carla.pk, actualizar="1"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No recibe entregas hasta que se lo agregue a un invernadero, en «Logística».")
        self.assertFalse(Vehiculo.objects.exists())  # «Actualizar» no guarda
        self.client.post(self.url, datos(transportista_id=self.carla.pk))
        self.assertEqual(Vehiculo.objects.get().transportista_id, self.carla.pk)

    def test_regla_4_un_transportista_con_vehiculo_se_rechaza_con_su_texto(self):
        """Regla 4: si lo eligió a la vez otro vehículo, ``transportista_con_vehiculo`` junto al campo (no se ofrece, pero se puede forzar)."""
        vehiculo(patente="ABC123", transportista=self.diego)
        self.assertContains(self.client.post(self.url, datos(transportista_id=self.diego.pk)), "Ese transportista ya tiene otro vehículo.")

    def test_flujo_principal_modificar_arranca_con_los_datos_y_el_transportista_actual(self):
        """Modificar: los datos guardados (capacidad sin ceros de más) y el transportista actual en la lista."""
        existente = vehiculo(patente="AE123CD", capacidad="800", transportista=self.diego)
        respuesta = self.client.get(reverse("comercial:vehiculo_modificar", args=[existente.pk]))
        self.assertContains(respuesta, 'value="AE123CD"')
        self.assertContains(respuesta, 'value="800"')
        self.assertContains(respuesta, "Diego Ferreyra · Norte")

    def test_flujo_principal_modificar_guarda_y_avisa_al_saliente_y_al_entrante(self):
        """Modificar: cambia datos y transportista; los dos reciben su aviso; vuelve a la ficha."""
        existente = vehiculo(patente="AE123CD", transportista=self.diego)
        url = reverse("comercial:vehiculo_modificar", args=[existente.pk])
        respuesta = self.client.post(url, datos(patente="AE123CD", marca="Fiat", transportista_id=self.carla.pk))
        self.assertRedirects(respuesta, reverse("comercial:vehiculo", args=[existente.pk]))
        self.assertEqual(avisos(respuesta), ["Se guardaron los cambios de AE123CD."])
        existente.refresh_from_db()
        self.assertEqual((existente.marca, existente.transportista_id), ("Fiat", self.carla.pk))
        self.assertEqual(Notificacion.objects.count(), 2)

    def test_pre_b_un_vehiculo_en_ruta_no_se_modifica_y_la_pantalla_dice_por_que(self):
        """Precondición b: el servicio lo rechaza con el texto del extracto, arriba del formulario."""
        en_ruta = vehiculo(patente="AE123CD", en_ruta_hoy=True)
        respuesta = self.client.post(reverse("comercial:vehiculo_modificar", args=[en_ruta.pk]), datos(patente="AE123CD", marca="Fiat"))
        self.assertContains(respuesta, "El vehículo está en ruta: el producto de las entregas de hoy está cargado.")
        en_ruta.refresh_from_db()
        self.assertEqual(en_ruta.marca, "Ford")

    def test_regla_4_un_vehiculo_inactivo_no_se_modifica_vuelve_a_la_ficha_con_el_motivo(self):
        """Regla 4: sin 403; vuelve a la ficha con el motivo (D-30)."""
        inactivo = vehiculo(patente="AE123CD", activo=False)
        respuesta = self.client.get(reverse("comercial:vehiculo_modificar", args=[inactivo.pk]))
        self.assertRedirects(respuesta, reverse("comercial:vehiculo", args=[inactivo.pk]))
        self.assertEqual(avisos(respuesta), ["El vehículo está dado de baja: solo se puede reactivar."])

    def test_flujo_principal_el_formulario_no_valida_al_tipear(self):
        """Interfaz: ningún disparador sobre los campos de texto."""
        contenido = self.client.get(self.url).content.decode()
        for disparador in ('hx-trigger="input', 'hx-trigger="keyup', "input delay", "keyup"):
            self.assertNotIn(disparador, contenido)


class VehiculosBajaYReactivacionVistaTests(ConGeoref, TestCase):
    """COM-BAJ-VEH y la reactivación de COM-MOD-VEH en pantalla."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.force_login(self.gerente)
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        self.vehiculo = vehiculo(patente="AE123CD", transportista=self.diego)
        self.url = reverse("comercial:vehiculo_baja", args=[self.vehiculo.pk])

    def test_flujo_principal_con_htmx_llega_solo_la_ventana_y_abrirla_no_cambia_nada(self):
        """Con HTMX, solo la ventana, que ofrece confirmar; el vehículo sigue activo."""
        respuesta = self.client.get(self.url, **HTMX)
        self.assertNotContains(respuesta, "<html")
        self.assertContains(respuesta, "Dar de baja AE123CD")
        self.assertContains(respuesta, "Dar de baja</button>")
        self.vehiculo.refresh_from_db()
        self.assertEqual(self.vehiculo.estado_vehiculo, "activo")

    def test_flujo_principal_sin_javascript_la_ventana_es_la_ficha_con_la_ventana_abierta(self):
        """Respaldo sin JavaScript: la ficha completa con la ventana abierta."""
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "<html")
        self.assertContains(respuesta, "data-cerrar-ventana")

    def test_post_a_confirmar_da_de_baja_y_avisa_al_transportista(self):
        """Postcondiciones a y b: inactivo y sin transportista, el transportista avisado, y vuelve a la ficha con un aviso."""
        respuesta = self.client.post(self.url)
        self.assertRedirects(respuesta, reverse("comercial:vehiculo", args=[self.vehiculo.pk]))
        self.assertEqual(avisos(respuesta), ["El vehículo AE123CD se dio de baja."])
        self.vehiculo.refresh_from_db()
        self.assertEqual((self.vehiculo.estado_vehiculo, self.vehiculo.transportista_id), ("inactivo", None))
        self.assertEqual(Notificacion.objects.get(destinatario=self.diego).titulo, "Tu vehículo se dio de baja")

    def test_pre_b_en_ruta_la_ventana_no_ofrece_confirmar(self):
        """Precondición b (MD-118): la ventana lo dice y no ofrece confirmar."""
        en_ruta = vehiculo(patente="ABC123", en_ruta_hoy=True)
        respuesta = self.client.get(reverse("comercial:vehiculo_baja", args=[en_ruta.pk]), **HTMX)
        self.assertContains(respuesta, "El vehículo está en ruta")
        self.assertNotContains(respuesta, "Dar de baja</button>")

    def test_pre_c_con_entregas_a_realizar_la_ventana_no_ofrece_confirmar(self):
        """Precondición c y regla 1 (con ``entregas_a_realizar_del_transportista`` simulada: lo completa COM-05)."""
        from unittest import mock

        from comercial.servicios import vehiculos

        with mock.patch.object(vehiculos, "entregas_a_realizar_del_transportista", return_value=["entrega"]):
            respuesta = self.client.get(self.url, **HTMX)
        self.assertContains(respuesta, "Su transportista tiene entregas a realizar. Reasignalas antes de dar de baja el vehículo.")
        self.assertNotContains(respuesta, "Dar de baja</button>")

    def test_d30_la_baja_de_un_inactivo_vuelve_a_la_ficha_con_el_motivo(self):
        """D-30: sin 403; vuelve a la ficha con el motivo."""
        inactivo = vehiculo(patente="ABC123", activo=False)
        respuesta = self.client.get(reverse("comercial:vehiculo_baja", args=[inactivo.pk]))
        self.assertRedirects(respuesta, reverse("comercial:vehiculo", args=[inactivo.pk]))
        self.assertEqual(avisos(respuesta), ["El vehículo ya está dado de baja."])

    def test_post_c_reactivar_deja_el_vehiculo_activo_sin_transportista_con_un_aviso(self):
        """Postcondición c de MOD: «Reactivar» es un POST sin ventana; queda activo y sin transportista."""
        inactivo = vehiculo(patente="ABC123", activo=False)
        respuesta = self.client.post(reverse("comercial:vehiculo_reactivar", args=[inactivo.pk]))
        self.assertRedirects(respuesta, reverse("comercial:vehiculo", args=[inactivo.pk]))
        self.assertEqual(avisos(respuesta), ["El vehículo ABC123 está activo de nuevo. Quedó sin transportista."])
        inactivo.refresh_from_db()
        self.assertEqual((inactivo.estado_vehiculo, inactivo.transportista_id), ("activo", None))

    def test_post_c_reactivar_es_solo_post_y_uno_activo_se_rechaza_con_el_motivo(self):
        """Reactivar: un GET no está permitido (405); uno activo vuelve a la ficha con el motivo."""
        url = reverse("comercial:vehiculo_reactivar", args=[self.vehiculo.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        respuesta = self.client.post(url)
        self.assertRedirects(respuesta, reverse("comercial:vehiculo", args=[self.vehiculo.pk]))
        self.assertEqual(avisos(respuesta), ["El vehículo no está dado de baja."])
