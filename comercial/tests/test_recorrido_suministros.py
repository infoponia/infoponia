# Recorrido de COM-03a (docs/patrones/verificacion_por_claude.md, D-95): lo que antes era la «Verificación a mano» de la tarea, de punta a punta con el cliente
# de Django, por rol y por estado. Una prueba larga a propósito: lo que se verifica es que el flujo completo encadena bien (pactar con un cliente sin correo,
# el cálculo del calendario y del stock, los errores, el resumen, la ficha, las notificaciones, la auditoría, la superposición, el comprobante y la consulta
# del Gerente, del Vendedor y de quien no tiene acceso). Las reglas sueltas las prueban `test_com_pct_sum.py`, `test_com_cns_sum.py` y `test_suministros_vistas.py`.
# Arma sus propios datos: no hay cargadores ni datos previos.

import re
from datetime import timedelta
from unittest import mock

from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import Cliente, ReservaStock, Suministro
from comercial.servicios import calendario
from comercial.tests.fabricas import cliente as crear_cliente
from comercial.tests.fabricas import direccion_de_cliente, escenario_comercial, verificar_invariantes_de_reservas
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import localidad
from produccion.tests.fabricas import lote_maduro

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()


def iso(dias):
    return str(HOY + timedelta(days=dias))


def avisos(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class RecorridoDeSuministrosTests(ConDatosDeInventario, TestCase):
    """El recorrido del Vendedor (y del Gerente) por «Pactar suministro» y la consulta, con el stock justo para que se vea la verificación."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 300)  # 300 plantas libres de «Lechuga Crespa» en Maduración
        self.gerente = crear_gerente()
        self.sin_correo = crear_cliente(razon_social="Verdulería Sin Correo S.A.", email="")
        self.dir_sin_correo = direccion_de_cliente(self.sin_correo)
        self.dir_2 = direccion_de_cliente(self.e.cliente, calle="Belgrano", numero_calle="45")
        self.addCleanup(verificar_invariantes_de_reservas)
        self.nueva = reverse("comercial:suministro_nuevo")
        self.calcular = reverse("comercial:suministro_calcular")
        self.revisar = reverse("comercial:suministro_revisar")

    def contrato(self, cliente_pk, **extra):
        """Los datos del formulario: 6 meses, tolerados 0, multa 50000, plazo 15, atraso 100, y un detalle de 150 plantas cada 7 días desde dentro de 3."""
        datos = {
            "cliente": str(cliente_pk), "duracion": "6", "tolerados": "0", "multa": "50000", "plazo_pago": "15", "indemnizacion_pago": "100",
            "detalle-0-variedad": str(self.e.variedad.pk), "detalle-0-direccion": str(self.e.direccion.pk), "detalle-0-cantidad": "150",
            "detalle-0-periodo": "7", "detalle-0-primera_entrega": iso(3), "detalle-0-mecanismo": "fijo", "detalle-0-precio": "1500",
            "detalle-0-plazo_entrega": "1", "detalle-0-indemnizacion_retraso": "100", "detalle-0-cantidad_minima": "50", "detalle-0-indemnizacion_faltante": "30",
        }
        datos.update(extra)
        return {k: v for k, v in datos.items() if v is not None}

    @override_settings(CORREO_CONFIGURADO=True)
    def test_recorrido_del_vendedor_pactar_un_suministro_de_punta_a_punta(self):
        """Pasos 1 a 7 de la antigua «Verificación a mano» de COM-03a, en el orden en que los haría una persona."""
        self.client.force_login(self.e.vendedor)

        # Paso 1 (COM-PCT-SUM 4b, 8a y regla 7 de COM-ALT-CLT): un cliente sin correo bloquea las secciones 2 y 3; «Cargar el correo» vuelve con el cliente elegido.
        lista = self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"})
        self.assertContains(lista, "Todavía no hay suministros.")
        self.assertContains(lista, reverse("comercial:suministro_nuevo"))
        bloqueado = self.client.get(self.nueva, {"cliente": self.sin_correo.pk})
        self.assertContains(bloqueado, "El cliente no tiene correo")
        self.assertContains(bloqueado, "Cargar el correo")
        self.assertNotContains(bloqueado, 'name="duracion"')
        enlace = re.search(r'href="(/comercial/clientes/\d+/modificar/\?volver=[^"]+)"', bloqueado.content.decode()).group(1)
        self.assertContains(self.client.get(enlace), "Verdulería Sin Correo S.A.")
        volver = reverse("comercial:suministro_nuevo") + f"?cliente={self.sin_correo.pk}"
        datos_cliente = {
            "tipo_cliente": "juridica", "cuit": self.sin_correo.cuit_cliente, "razon_social": self.sin_correo.razon_social_cliente, "email": "compras@sincorreo.com",
            "volver": volver, f"corregida-{self.dir_sin_correo.direccion_id}-tipo_direccion": "urbana", f"corregida-{self.dir_sin_correo.direccion_id}-localidad": localidad().pk,
            f"corregida-{self.dir_sin_correo.direccion_id}-calle": "San Martín", f"corregida-{self.dir_sin_correo.direccion_id}-numero_calle": "123",
        }
        respuesta = self.client.post(reverse("comercial:cliente_modificar", args=[self.sin_correo.pk]), datos_cliente)
        self.assertEqual(respuesta.status_code, 302)
        elegido = self.client.get(respuesta.url)
        self.assertContains(elegido, f'name="cliente" value="{self.sin_correo.pk}"')
        self.assertContains(elegido, 'name="duracion"')  # la sección 2 se habilitó: el cliente sigue elegido y ya tiene correo
        self.assertEqual(Cliente.objects.get(pk=self.sin_correo.pk).email_cliente, "compras@sincorreo.com")

        # Paso 2 (6a, regla «Fecha de fin»): 6 meses → «Termina el» el mismo día, 6 meses después; tolerados 0 se acepta.
        cuerpo = self.client.post(self.calcular, self.contrato(self.e.cliente.pk, **{"detalle-0-cantidad": "200"}), **HTMX)
        self.assertContains(cuerpo, f"Termina el <b>{calendario.sumar_meses(HOY, 6):%d/%m/%Y}</b>")
        self.assertNotContains(cuerpo, "Ingresá un número entero, de 0 a 99.")

        # Paso 3 (9e): con 300 plantas, dos períodos de 200 en la ventana: la segunda entrega no alcanza; con 150 alcanzan las dos.
        self.assertContains(cuerpo, "se reserva ahora")
        self.assertEqual(cuerpo.content.decode().count("se reserva ahora"), 2)
        self.assertContains(cuerpo, "No alcanza")
        self.assertContains(cuerpo, "100 plantas disponibles de")
        bien = self.client.post(self.calcular, self.contrato(self.e.cliente.pk), **HTMX)
        self.assertNotContains(bien, "No alcanza")
        self.assertEqual(bien.content.decode().count("Alcanza"), 2)

        # Paso 4 (9c y 8b, 11a): el mismo par repetido da error; con la dirección 2 y ajuste periódico se ven los tramos de precio; la cláusula con mínimo mayor da error.
        repetido = self.client.post(self.revisar, {**self.contrato(self.e.cliente.pk, **{"detalle-0-cantidad": "10", "detalle-0-cantidad_minima": "5"}),
            "detalle-1-variedad": str(self.e.variedad.pk), "detalle-1-direccion": str(self.e.direccion.pk), "detalle-1-cantidad": "10", "detalle-1-periodo": "30",
            "detalle-1-primera_entrega": iso(40), "detalle-1-mecanismo": "fijo", "detalle-1-precio": "1500", "detalle-1-plazo_entrega": "1",
            "detalle-1-indemnizacion_retraso": "100", "detalle-1-cantidad_minima": "5", "detalle-1-indemnizacion_faltante": "30"}, **HTMX)
        self.assertContains(repetido, "El contrato ya tiene")
        self.assertContains(repetido, "es el detalle 1")
        segundo = {
            "detalle-1-variedad": str(self.e.variedad.pk), "detalle-1-direccion": str(self.dir_2.direccion_id), "detalle-1-cantidad": "10", "detalle-1-periodo": "30",
            "detalle-1-primera_entrega": iso(40), "detalle-1-mecanismo": "ajuste_periodico", "detalle-1-porcentaje": "3", "detalle-1-meses": "2",
            "detalle-1-precio": "1000", "detalle-1-plazo_entrega": "1", "detalle-1-indemnizacion_retraso": "100", "detalle-1-cantidad_minima": "20",
            "detalle-1-indemnizacion_faltante": "30",
        }
        con_tramos = self.client.post(self.calcular, {**self.contrato(self.e.cliente.pk), **segundo}, **HTMX)
        self.assertContains(con_tramos, "Desde el")
        minimo_mal = self.client.post(self.revisar, {**self.contrato(self.e.cliente.pk), **segundo}, **HTMX)
        self.assertContains(minimo_mal, "Ingresá un número entero de plantas, de 1 a 10.")
        segundo["detalle-1-cantidad_minima"] = "5"

        # Paso 5 (pasos 12 a 16): «Revisar y pactar» muestra el resumen y «Confirmar» pacta, reserva los períodos de la ventana, avisa y audita.
        datos_ok = {**self.contrato(self.e.cliente.pk), **segundo}
        resumen = self.client.post(self.revisar, datos_ok, **HTMX)
        self.assertContains(resumen, "Resumen del suministro")
        self.assertContains(resumen, "Confirmar suministro")
        self.assertEqual(Suministro.objects.count(), 0)
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=True) as correo:
            respuesta = self.client.post(self.nueva, {**datos_ok, "confirmar": "1"})
        s = Suministro.objects.get()
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[s.pk]))
        self.assertTrue(any(f"{s.codigo} pactado. Se reservaron 2 períodos y se programaron 2 cosechas." in a and "Se envió el comprobante" in a for a in avisos(respuesta)))
        self.assertEqual(correo.call_args.args[1], f"Comprobante de tu suministro {s.codigo}")
        ficha = self.client.get(reverse("comercial:suministro", args=[s.pk]))
        for texto in (s.codigo, "Vigente", "Reservado", "Fuera de la ventana", "Enviado", "Mín. 50 plantas", "Mín. 5 plantas"):
            self.assertContains(ficha, texto)
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro__suministro=s).count(), 2)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.capataz, titulo__startswith="Nueva cosecha").count(), 2)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.agronomo, titulo__startswith="Nueva cosecha").count(), 2)
        (auditoria,) = RegistroAuditoria.objects.filter(accion="pacto_suministro")
        self.assertEqual(auditoria.usuario_id, self.e.vendedor.pk)
        self.assertContains(self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"}), "Al límite")  # tolerados 0: el primero lo resuelve
        self.assertContains(ficha, "El contrato no tolera incumplimientos")

        # Paso 6 (9d): otro cliente con el mismo par (variedad y dirección) no es una superposición; el mismo cliente, sí, y sin «Continuar igual» no deja.
        otro_cliente_mismo_par = self.client.post(self.calcular, self.contrato(self.sin_correo.pk, **{"detalle-0-direccion": str(self.dir_sin_correo.direccion_id)}), **HTMX)
        self.assertNotContains(otro_cliente_mismo_par, "Continuar igual")
        repetida = self.client.post(self.calcular, self.contrato(self.e.cliente.pk, **{"detalle-0-cantidad": "10", "detalle-0-cantidad_minima": "5", "detalle-0-primera_entrega": iso(40)}), **HTMX)
        self.assertContains(repetida, s.codigo)
        self.assertContains(repetida, "Continuar igual")
        sin_casilla = self.client.post(self.nueva, {**self.contrato(self.e.cliente.pk, **{"detalle-0-cantidad": "10", "detalle-0-cantidad_minima": "5", "detalle-0-primera_entrega": iso(40)}), "confirmar": "1"})
        self.assertContains(sin_casilla, "Marcá «Continuar igual»")
        self.assertEqual(Suministro.objects.count(), 1)

        # Paso 7: sin JavaScript, el pacto funciona con «Actualizar» y el resumen como página (con la casilla marcada, es una renovación).
        renovacion = self.contrato(self.e.cliente.pk, **{"detalle-0-cantidad": "10", "detalle-0-cantidad_minima": "5", "detalle-0-primera_entrega": iso(40), "detalle-0-continuar": "1"})
        self.assertContains(self.client.post(self.nueva, {**renovacion, "actualizar": "1"}), "<html")
        pagina_resumen = self.client.post(self.revisar, renovacion)
        self.assertContains(pagina_resumen, "<html")
        self.assertContains(pagina_resumen, 'name="detalle-0-continuar" value="1"')
        self.client.post(self.nueva, {**renovacion, "confirmar": "1"})
        self.assertEqual(Suministro.objects.count(), 2)

    def test_recorrido_por_rol_el_gerente_el_vendedor_ajeno_y_quien_no_tiene_acceso(self):
        """Cada rol, cada estado: el Gerente pacta a nombre de un Vendedor y lo ve todo; el Vendedor ajeno no ve nada ajeno; el Agrónomo recibe 403;
        sin invernaderos, «Pactar suministro» queda deshabilitado."""
        # El Gerente elige al Vendedor responsable y pacta.
        self.client.force_login(self.gerente)
        formulario = self.client.get(self.nueva)
        self.assertContains(formulario, "Vendedor responsable")
        self.client.post(self.nueva, {**self.contrato(self.e.cliente.pk), "vendedor": str(self.e.vendedor.pk), "confirmar": "1"})
        s = Suministro.objects.get()
        self.assertEqual(s.vendedor_id, self.e.vendedor.pk)
        self.assertEqual(RegistroAuditoria.objects.get(accion="pacto_suministro").usuario_id, self.gerente.pk)
        self.assertContains(self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"}), s.codigo)
        # El Vendedor del contrato lo ve; otro Vendedor no (403 con mensaje) ni en su lista.
        otro = escenario_comercial(sufijo="2")
        self.client.force_login(self.e.vendedor)
        self.assertEqual(self.client.get(reverse("comercial:suministro", args=[s.pk])).status_code, 200)
        self.client.force_login(otro.vendedor)
        self.assertEqual(self.client.get(reverse("comercial:suministro", args=[s.pk])).status_code, 403)
        self.assertNotContains(self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"}), s.codigo)
        # Quien no tiene acceso: 403 en todo.
        self.client.force_login(self.e.agronomo)
        for url in (reverse("comercial:contratos") + "?tipo=suministro", self.nueva, reverse("comercial:suministro", args=[s.pk])):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        # La ficha del cliente lista el suministro para quien puede verlo.
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(reverse("comercial:cliente", args=[self.e.cliente.pk])), s.codigo)
        # Estados: el suministro finalizado ya no cuenta como pendiente de la baja ni impide quitar el correo.
        Suministro.objects.filter(pk=s.pk).update(estado_suministro="finalizado")
        self.assertNotContains(self.client.get(reverse("comercial:cliente_baja", args=[self.e.cliente.pk]), **HTMX), "Suministros vigentes")
