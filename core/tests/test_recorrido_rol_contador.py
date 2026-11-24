# Recorrido de punta a punta del rol Contador (USR-11, D-85) con el cliente de Django, como lo haría una persona y por rol y
# estado (D-96, docs/patrones/verificacion_a_mano.md). Una prueba larga a propósito: lo que verifica es que el flujo
# completo encadena bien. Las reglas sueltas las prueban test_usr_11_rol_contador.py, test_rol_contador_vistas.py,
# test_modelos_contador.py y contabilidad/tests/test_responsables.py. No ve lo que solo un navegador ve (CSRF, JavaScript,
# aspecto): eso va como paso de «navegador real» en la «Verificación a mano» de la tarea.

from django.test import Client, TestCase
from django.urls import reverse

from contabilidad.servicios import responsables
from core.models import Contador, RegistroAuditoria, Usuario
from core.tests.fabricas import crear_administrador, crear_gerente

NUEVA = "huerta-hidro-2026"


class RecorridoDeRolContadorTests(TestCase):
    """Alta, un solo activo, primer ingreso, alcance por rol, baja, reemplazo y reactivación del Contador."""

    def alta(self, cliente, email="carolina@infoponia.com", nombre="Carolina"):
        """Envía el alta de un Contador con contraseña temporal y devuelve la respuesta."""
        return cliente.post(
            reverse("core:usuario_nuevo"),
            {"rol": "contador", "nombre": nombre, "apellido": "Vega", "email": email, "telefono": ""},
        )

    def test_recorrido_del_contador_de_punta_a_punta(self):
        gerente = crear_gerente()
        administrador = crear_administrador()
        cliente_gerente = Client()
        cliente_gerente.force_login(gerente)

        # Paso 1 · USR-ALT-USR, D-85 punto 3: sin Contador, el Gerente es el responsable contable.
        self.assertEqual(responsables.responsable_contable().pk, gerente.pk)
        self.assertTrue(responsables.puede_registrar_asientos(gerente))
        self.assertContains(cliente_gerente.get(reverse("core:usuario_nuevo")), 'value="contador"')

        # Paso 2 · USR-ALT-USR flujo principal: el Gerente da de alta al Contador y se le informa la temporal una vez.
        respuesta = self.alta(cliente_gerente)
        self.assertContains(respuesta, "Cuenta creada")
        temporal = respuesta.context["contrasena_temporal"]
        contador = Contador.objects.get(email="carolina@infoponia.com")
        self.assertTrue(contador.is_active)

        # Paso 3 · D-85 punto 5: ahora el responsable es el Contador y el Gerente deja de registrar.
        self.assertEqual(responsables.responsable_contable().pk, contador.pk)
        self.assertTrue(responsables.puede_registrar_asientos(contador))
        self.assertFalse(responsables.puede_registrar_asientos(gerente))

        # Paso 4 · SEG-15 y D-85 punto 2: un segundo Contador activo se rechaza con el mensaje y lo escrito queda.
        segundo = self.alta(cliente_gerente, email="otra@infoponia.com", nombre="Otra")
        self.assertEqual(segundo.status_code, 200)
        self.assertContains(segundo, "Ya hay un Contador activo: Carolina Vega")
        self.assertContains(segundo, "otra@infoponia.com")
        self.assertFalse(Usuario.objects.filter(email="otra@infoponia.com").exists())

        # Paso 5 · USR-CNS-USR: el Gerente lo ve en la lista (filtrada por rol) y abre su ficha.
        lista = cliente_gerente.get(reverse("core:usuarios"), {"rol": "contador", "estado": "activo"})
        self.assertContains(lista, "Carolina Vega")
        self.assertContains(cliente_gerente.get(reverse("core:usuario", args=[contador.pk])), "Contador")

        # Paso 6 · USR-INI-SES regla 4 y SEG-04: el Contador entra con la temporal, la reemplaza y llega a su inicio.
        cliente_contador = Client()
        entrada = cliente_contador.post(
            reverse("core:iniciar_sesion"), {"username": "carolina@infoponia.com", "password": temporal}, follow=True
        )
        self.assertRedirects(entrada, reverse("core:elegir_contrasena"))
        cliente_contador.post(
            reverse("core:elegir_contrasena"), {"contrasena_nueva": NUEVA, "contrasena_repetida": NUEVA}
        )
        inicio = cliente_contador.get(reverse("core:inicio"))
        self.assertEqual(inicio.status_code, 200)

        # Paso 7 · SEG-13 y D-85 punto 6: su marco dice Contador, su menú es solo el Panel y no hay Estadísticas.
        self.assertEqual(inicio.context["rol_visible"], "Contador")
        self.assertEqual(inicio.context["sigla"], "CON")
        self.assertEqual([e["texto"] for e in inicio.context["menu"]], ["Panel de control", "Compras"])  # «Compras» la registra CMP-03 (D-87 punto 6: solo las órdenes, en lectura)
        self.assertNotContains(inicio, "Estadísticas")

        # Paso 8 · SEG-13: otros módulos le dan 403 por la dirección escrita a mano.
        for nombre in ("core:usuarios", "core:auditoria", "maestros:invernaderos", "comercial:inicio", "compras:pedidos"):
            with self.subTest(pantalla=nombre):
                self.assertEqual(cliente_contador.get(reverse(nombre)).status_code, 403)

        # Paso 9 · D-85 punto 3: el Administrador no lo ve en la lista ni abre su ficha.
        cliente_administrador = Client()
        cliente_administrador.force_login(administrador)
        self.assertNotContains(cliente_administrador.get(reverse("core:usuarios")), "Carolina Vega")
        self.assertEqual(cliente_administrador.get(reverse("core:usuario", args=[contador.pk])).status_code, 403)

        # Paso 10 · USR-BAJ-USR y D-85 punto 4: la baja del Contador no tiene impedimentos y deja al Gerente como responsable.
        ventana = cliente_gerente.get(reverse("core:usuario_baja", args=[contador.pk]))
        self.assertContains(ventana, 'data-enviando="Dando de baja…"')
        cliente_gerente.post(reverse("core:usuario_baja", args=[contador.pk]))
        self.assertFalse(Usuario.objects.get(pk=contador.pk).is_active)
        self.assertEqual(responsables.responsable_contable().pk, gerente.pk)
        self.assertTrue(responsables.puede_registrar_asientos(gerente))
        self.assertFalse(responsables.puede_registrar_asientos(contador))

        # Paso 11 · USR-BAJ-USR regla 2 y SEG-06: la cuenta dada de baja ya no usa su sesión.
        self.assertEqual(cliente_contador.get(reverse("core:inicio")).status_code, 302)

        # Paso 12 · D-85 punto 4: el reemplazo son dos operaciones; ahora se da de alta otro Contador.
        nuevo = self.alta(cliente_gerente, email="otra@infoponia.com", nombre="Otra")
        self.assertContains(nuevo, "Cuenta creada")
        otro = Contador.objects.get(email="otra@infoponia.com")
        self.assertEqual(responsables.responsable_contable().pk, otro.pk)

        # Paso 13 · USR-MOD-USR regla 5: reactivar al primero con otro activo se rechaza y la ventana no ofrece confirmar.
        ventana = cliente_gerente.get(reverse("core:usuario_reactivar", args=[contador.pk]))
        self.assertContains(ventana, "ya hay un Contador activo")
        self.assertNotContains(ventana, 'data-enviando="Reactivando…"')
        rechazo = cliente_gerente.post(reverse("core:usuario_reactivar", args=[contador.pk]))
        self.assertContains(rechazo, "ya hay un Contador activo")
        self.assertFalse(Usuario.objects.get(pk=contador.pk).is_active)

        # Paso 14 · SEG-14 y D-36: el alta, el cambio de contraseña del primer ingreso y la baja quedaron en «Auditoría», y el
        # Gerente los ve (el Contador es un rol operativo).
        acciones = list(
            RegistroAuditoria.objects.visibles_para(gerente)
            .filter(afectados__contains=[{"modelo": "core.usuario", "id": contador.pk}])
            .values_list("accion", flat=True)
        )
        self.assertEqual(
            sorted(acciones),
            sorted(
                [
                    RegistroAuditoria.Accion.ALTA,
                    RegistroAuditoria.Accion.CAMBIO_CONTRASENA,
                    RegistroAuditoria.Accion.BAJA,
                ]
            ),
        )
        self.assertContains(cliente_gerente.get(reverse("core:auditoria")), "Contador")
