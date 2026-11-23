# Recorrido de punta a punta de «Compras» → «Pedidos» y del portal del proveedor (CMP-02a): los pasos de la antigua «Verificación a mano», hechos por una prueba con el cliente de Django, en el
# orden en que los haría una persona (docs/patrones/verificacion_a_mano.md, D-96). Cada paso nombra el caso de uso y la regla que verifica. Es una sola prueba larga a propósito: lo que se
# verifica es que el flujo completo encadena bien (un Agrónomo arma un pedido para dos invernaderos, invita a dos proveedores, cada uno cotiza una vez desde su enlace, el aviso de pedido cubierto
# sale una sola vez, el Gerente consulta sin poder cambiar nada y la auditoría muestra «Proveedor (mediante enlace)»); las reglas sueltas las prueban ``test_cmp_*.py`` y ``test_pedidos_vistas.py``.
# Los correos salen en ``on_commit``: en un ``TestCase`` (que está dentro de una transacción) se lo reemplaza por una llamada inmediata, que es lo que pasa en producción.

import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.db import connection, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from compras.models import Cotizacion, EnlaceProveedor, Pedido
from compras.tests.fabricas import proveedor, tipo_de_insumo
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.models import InsumoInvernadero
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo, crear_invernadero


@override_settings(CORREO_CONFIGURADO=True)
class RecorridoDePedidosTests(ConDatosDeInventario, TestCase):
    """Fuente: docs/casos_de_uso/compras/pedidos.md (CMP-RLZ-PED, CMP-ENV-COT y CMP-CNS-PED), D-87, D-88, D-89 y D-36."""

    def setUp(self):
        envio_inmediato = mock.patch.object(transaction, "on_commit", lambda funcion, **kwargs: funcion())
        envio_inmediato.start()
        self.addCleanup(envio_inmediato.stop)
        self.ana = crear_agronomo(email="ana@infoponia.com")
        self.otra = crear_agronomo(email="otra@infoponia.com")
        self.gerente = crear_gerente()
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.ana)
        semillas = tipo_de_insumo("Semillas y plantines")
        self.lechuga = existencia(insumo("Lechuga", tipo=semillas, unidad="unidad", descripcion="Plantín"), self.norte, minimo=20, precio="12.50")
        lote(self.lechuga, 5)  # bajo el mínimo: sugerida 15
        self.nutriente = existencia(insumo("Nutriente", unidad="kg"), self.sur, minimo=5, precio="100.00")
        lote(self.nutriente, 9)  # sobre el mínimo: del catálogo, no bajo el mínimo
        self.sustrato = insumo("Sustrato", unidad="kg")  # del catálogo, sin habilitar en ningún invernadero
        self.proveedor_a = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com", especialidades=[semillas])
        self.proveedor_b = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.inactivo = proveedor("Agro Norte S. R. L.", n=3, activo=False)
        fila = configuracion.obtener()
        fila.porc_tolerancia_cobertura_pedido = 0
        fila.save(update_fields=["porc_tolerancia_cobertura_pedido"])
        self.nuevo = reverse("compras:pedido_nuevo")
        self.client.force_login(self.ana)

    def auditoria(self, accion):
        return RegistroAuditoria.objects.filter(accion=accion)

    def datos_del_portal(self, pedido, **cambios):
        """El formulario del portal: cotiza todo el pedido por el total de cada línea, con la validez pasada la fecha límite."""
        datos = {"accion": "enviar", "modo": "total", "validez": (pedido.fecha_limite_cotizaciones + timedelta(days=5)).isoformat(), "observaciones": ""}
        for detalle in pedido.detalles.all():
            datos.update({f"cantidad_{detalle.pk}": str(detalle.cantidad_detalle.normalize()), f"precio_{detalle.pk}": "100.00", f"plazo_{detalle.pk}": "3"})
        datos.update(cambios)
        return datos

    def test_recorrido_completo_del_agronomo_los_proveedores_y_el_gerente(self):
        # Paso 1 · Inicio del Agrónomo (``panelAgr``): ve lo que está bajo el mínimo y «Pedir» lo lleva al pedido con la cantidad sugerida (extensión 1a).
        inicio = self.client.get(reverse("core:inicio"))
        self.assertContains(inicio, "Insumos bajo el mínimo")
        self.assertContains(inicio, f"{self.nuevo}?iin={self.lechuga.pk}")
        desde_la_alerta = self.client.get(self.nuevo, {"iin": self.lechuga.pk})
        self.assertEqual([(f["iin"].pk, f["cantidad"]) for f in desde_la_alerta.context["filas"]], [(self.lechuga.pk, "15")])

        # Paso 2 · CMP-RLZ-PED extensión 3a: agrega del catálogo un insumo de otro invernadero (el nutriente, sobre el mínimo) y quita y vuelve a agregar un renglón.
        base = {"detalle_iin": [self.lechuga.pk], "detalle_cantidad": ["15"]}
        respuesta = self.client.post(self.nuevo, {**base, "accion": "agregar_catalogo", "catalogo_iin": self.nutriente.pk})
        self.assertEqual([f["iin"].pk for f in respuesta.context["filas"]], [self.lechuga.pk, self.nutriente.pk])

        # Paso 3 · Extensión 3a.1a: un insumo del catálogo que no está habilitado; con datos inválidos se informa junto al campo y no se pierde el pedido…
        habilitar = {"accion": "habilitar", "hab_invernadero": self.sur.pk, "hab_insumo": self.sustrato.pk, "hab_minimo": "2", "hab_precio": "0"}
        respuesta = self.client.post(self.nuevo, {"detalle_iin": [self.lechuga.pk, self.nutriente.pk], "detalle_cantidad": ["15", "3"], **habilitar})
        self.assertContains(respuesta, "precio mayor que 0")
        self.assertEqual(len(respuesta.context["filas"]), 2)
        # … y con datos válidos se habilita (CMP-HAB-IIN, con su auditoría) y vuelve al pedido con el insumo agregado.
        respuesta = self.client.post(self.nuevo, {"detalle_iin": [self.lechuga.pk, self.nutriente.pk], "detalle_cantidad": ["15", "3"], **habilitar, "hab_precio": "30.00"})
        sustrato = InsumoInvernadero.objects.get(insumo=self.sustrato, invernadero=self.sur)
        self.assertEqual([f["iin"].pk for f in respuesta.context["filas"]], [self.lechuga.pk, self.nutriente.pk, sustrato.pk])
        self.assertEqual(self.auditoria("habilitacion_insumo_invernadero").count(), 1)

        # Paso 4 · Reglas 4a y 4b: una cantidad inválida, un renglón repetido y un pedido sin proveedores ni fecha válida se rechazan juntos, junto a cada campo, sin perder lo escrito.
        mal = {"detalle_iin": [self.lechuga.pk, self.lechuga.pk, sustrato.pk], "detalle_cantidad": ["15", "2", "0"], "proveedor": [], "fecha_limite": timezone.localdate().isoformat(), "accion": "revisar"}
        respuesta = self.client.post(self.nuevo, mal)
        for texto in ("ya figura en el pedido para ese invernadero", "Ingresá una cantidad mayor que cero", "al menos a un proveedor", "La fecha límite tiene que ser desde el"):
            self.assertContains(respuesta, texto)
        self.assertEqual(Pedido.objects.count(), 0)

        # Paso 5 · Pasos 6 a 9: los proveedores se filtran por lo que se pide (el propuesto), «seleccionar todos» marca los de la lista y el inactivo nunca aparece; el resumen agrupa por invernadero.
        filtrado = self.client.post(self.nuevo, {"detalle_iin": [self.lechuga.pk], "detalle_cantidad": ["15"], "filtro": "", "accion": "filtrar"})
        self.assertEqual([p["proveedor"].pk for p in filtrado.context["proveedores"]], [self.proveedor_a.pk])
        todos = self.client.post(self.nuevo, {"detalle_iin": [self.lechuga.pk], "detalle_cantidad": ["15"], "filtro": "todos", "accion": "todos"})
        self.assertEqual({p["proveedor"].pk for p in todos.context["proveedores"]}, {self.proveedor_a.pk, self.proveedor_b.pk})
        self.assertNotContains(todos, "Agro Norte S. R. L.")
        pedido_completo = {
            "detalle_iin": [self.lechuga.pk, self.nutriente.pk],
            "detalle_cantidad": ["20", "3"],
            "proveedor": [self.proveedor_a.pk, self.proveedor_b.pk],
            "fecha_limite": (timezone.localdate() + timedelta(days=3)).isoformat(),
            "filtro": "todos",
        }
        resumen = self.client.post(self.nuevo, {**pedido_completo, "accion": "revisar"})
        for texto in ("Invernadero Norte", "Invernadero Sur", "$ 250,00", "$ 300,00", "$ 550,00", "Confirmar pedido"):
            self.assertContains(resumen, texto)
        self.assertEqual((Pedido.objects.count(), mail.outbox), (0, []))

        # Paso 6 · CMP-RLZ-PED pasos 10 a 13: se registra, cada proveedor recibe SU enlace (sin precios de referencia) y se llega a la ficha.
        respuesta = self.client.post(self.nuevo, {**pedido_completo, "accion": "confirmar"}, follow=True)
        pedido = Pedido.objects.get()
        self.assertRedirects(respuesta, reverse("compras:pedido_ficha", args=[pedido.pk]))
        self.assertContains(respuesta, f"Enviamos el pedido {pedido} a 2 proveedores.")
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["info@este.com", "ventas@sur.com"])
        enlaces = {m.to[0]: re.search(r"https?://[^/]+(/proveedor/[\w-]+/)", m.body).group(1) for m in mail.outbox}
        self.assertEqual(len(set(enlaces.values())), 2)
        for correo in mail.outbox:
            for prohibido in ("12,50", "100,00", "550", "precio", "Precio"):
                self.assertNotIn(prohibido, correo.body)
        self.assertEqual(self.auditoria("alta_pedido").count(), 1)
        self.assertEqual({e.estado_envio for e in EnlaceProveedor.objects.all()}, {"enviado"})

        # Paso 7 · CMP-CNS-PED: el Agrónomo ve su ficha con los invitados; el Gerente la ve en modo consulta; otro Agrónomo y el Capataz no.
        ficha = reverse("compras:pedido_ficha", args=[pedido.pk])
        self.assertContains(self.client.get(ficha), "No cotizó")
        self.client.force_login(self.gerente)
        for url in (reverse("compras:pedidos"), ficha):
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertNotContains(self.client.get(reverse("compras:pedidos")), "Nuevo pedido")
        self.assertEqual(self.client.get(self.nuevo).status_code, 403)
        for cuenta in (self.otra, crear_capataz()):
            self.client.force_login(cuenta)
            self.assertEqual(self.client.get(ficha).status_code, 403)

        # Paso 8 · CMP-ENV-COT: el proveedor A (sin cuenta) abre su enlace en otro navegador: la dirección que queda no lleva el token y el portal no muestra precios de referencia ni a los otros.
        portal_a = Client()
        entrada = portal_a.get(enlaces["ventas@sur.com"])
        self.assertRedirects(entrada, "/proveedor/enlace/", fetch_redirect_response=False)
        pagina = portal_a.get("/proveedor/enlace/")
        for texto in ("Lechuga", "Nutriente", "Invernadero Norte", "Invernadero Sur", "Semillas del Sur S. A."):
            self.assertContains(pagina, texto)
        for prohibido in ("12,50", "Viveros del Este", "Sustrato"):
            self.assertNotContains(pagina, prohibido)
        detalles = {d.insumo_invernadero_id: d for d in pedido.detalles.all()}
        d_lechuga, d_nutriente = detalles[self.lechuga.pk], detalles[self.nutriente.pk]

        # Paso 9 · CMP-ENV-COT 6a, 6b, 6c y 9a: cantidad 0, precio con tres decimales, plazo 0 y validez anterior a la fecha límite se rechazan juntos; nada se registra.
        mala = self.datos_del_portal(pedido, accion="revisar", validez=timezone.localdate().isoformat(), **{f"cantidad_{d_lechuga.pk}": "0", f"precio_{d_lechuga.pk}": "10.123", f"plazo_{d_lechuga.pk}": "0"})
        respuesta = portal_a.post("/proveedor/enlace/", mala)
        for texto in ("mayor que cero", "hasta 2 decimales", "plazo en días", "Tiene que valer como mínimo hasta el"):
            self.assertContains(respuesta, texto)
        self.assertEqual(Cotizacion.objects.count(), 0)

        # Paso 10 · CMP-ENV-COT 9 a 13: revisa (resumen con la advertencia), envía una línea con total y la otra con total y una cantidad MAYOR que la pedida (P2); recibe el acuse y ve «Recibimos su cotización».
        valida = self.datos_del_portal(pedido, **{f"cantidad_{d_nutriente.pk}": "4", f"precio_{d_nutriente.pk}": "120.00", f"cantidad_{d_lechuga.pk}": "20", f"precio_{d_lechuga.pk}": "250.00"})
        self.assertContains(portal_a.post("/proveedor/enlace/", {**valida, "accion": "revisar"}), "una sola vez")
        respuesta = portal_a.post("/proveedor/enlace/", valida, follow=True)
        self.assertContains(respuesta, "Recibimos su cotización")
        cotizacion_a = Cotizacion.objects.get(proveedor=self.proveedor_a)
        self.assertEqual(cotizacion_a.monto_cotizacion, Decimal("370.00"))
        self.assertEqual(cotizacion_a.lineas.get(detalle_pedido=d_nutriente).cantidad_cotizada, Decimal("4"))
        self.assertEqual(mail.outbox[-1].to, ["ventas@sur.com"])
        self.assertIn("370,00", mail.outbox[-1].body)

        # Paso 11 · CMP-ENV-COT 2b y 11b: al volver a abrir el enlace ve su cotización en solo lectura y no puede enviar otra.
        solo_lectura = portal_a.get("/proveedor/enlace/")
        for texto in ("Ya envió su cotización", "$ 370,00"):
            self.assertContains(solo_lectura, texto)
        self.assertNotContains(solo_lectura, "Revisar y enviar")
        self.assertContains(portal_a.post("/proveedor/enlace/", valida, follow=True), "Ya envió su cotización")
        self.assertEqual(Cotizacion.objects.filter(proveedor=self.proveedor_a).count(), 1)

        # Paso 12 · CMP-ENV-COT 11c: con la cotización de A (20 y 4 contra 20 y 3) el pedido quedó cubierto por primera vez: un aviso para el Agrónomo; sigue «en cotización».
        avisos = Notificacion.objects.filter(titulo__contains=str(pedido))
        self.assertEqual([n.destinatario_id for n in avisos], [self.ana.pk])
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado_pedido, "en_cotizacion")

        # Paso 13 · El proveedor B cotiza con el precio unitario (D-89): el total se calcula (3 × 40,10 = 120,30); como el pedido ya estaba cubierto no hay otro aviso.
        portal_b = Client()
        portal_b.get(enlaces["info@este.com"])
        unitario = self.datos_del_portal(pedido, modo="unitario", **{f"cantidad_{d_lechuga.pk}": "20", f"precio_{d_lechuga.pk}": "12.00", f"cantidad_{d_nutriente.pk}": "3", f"precio_{d_nutriente.pk}": "40.10"})
        self.assertContains(portal_b.post("/proveedor/enlace/", unitario, follow=True), "Recibimos su cotización")
        cotizacion_b = Cotizacion.objects.get(proveedor=self.proveedor_b)
        self.assertEqual(cotizacion_b.monto_cotizacion, Decimal("360.30"))  # 20 × 12,00 + 3 × 40,10
        self.assertEqual(avisos.count(), 1)

        # Paso 14 · CMP-CNS-PED regla 6: el Agrónomo y el Gerente ven las dos cotizaciones en solo lectura desde que llegaron, con «Cotizó» y los enlaces «Usado»; nadie puede cambiar nada.
        for cuenta in (self.ana, self.gerente):
            self.client.force_login(cuenta)
            respuesta = self.client.get(ficha)
            for texto in ("Cotizaciones recibidas", "$ 370,00", "$ 360,30", "Usado"):
                self.assertContains(respuesta, texto)
            self.assertEqual(self.client.post(ficha).status_code, 405)

        # Paso 15 · La auditoría: el alta del pedido (del Agrónomo) y las dos cotizaciones con origen «Proveedor (mediante enlace)»; nada del token ni de su resumen.
        self.client.force_login(self.gerente)
        pantalla = self.client.get(reverse("core:auditoria"))
        for texto in ("Alta de pedido de cotización", "Alta de cotización", "Proveedor (mediante enlace)"):
            self.assertContains(pantalla, texto)
        registro = self.auditoria("alta_cotizacion").latest("id")
        self.assertEqual((registro.usuario_id, registro.rol), (None, "proveedor_enlace"))
        self.assertContains(self.client.get(reverse("core:auditoria_registro", args=[registro.pk])), "Proveedor (mediante enlace)")
        with connection.cursor() as cursor:
            for ruta in enlaces.values():
                token = ruta.strip("/").split("/")[-1]
                for tabla in ("compras_enlaceproveedor", "core_registroauditoria"):
                    cursor.execute(f"SELECT count(*) FROM {tabla} t WHERE t::text LIKE %s", [f"%{token}%"])
                    self.assertEqual(cursor.fetchone()[0], 0, f"El token aparece en {tabla}")

        # Paso 16 · CMP-CNS-PRV regla 4 y CMP-MOD-PRV regla 2: la ficha del proveedor lista el pedido y su CUIT ya no se edita.
        ficha_a = self.client.get(reverse("compras:proveedor_ficha", args=[self.proveedor_a.pk]))
        self.assertContains(ficha_a, str(pedido))
        self.assertTrue(self.client.get(reverse("compras:proveedor_editar", args=[self.proveedor_a.pk])).context["cuit_fijo"])

        # Paso 17 · D-88 punto 2: pasada la fecha límite el enlace ya no sirve ni para ver, y el pedido figura con la fecha límite vencida.
        Pedido.objects.filter(pk=pedido.pk).update(fecha_pedido=timezone.localdate() - timedelta(days=8), fecha_limite_cotizaciones=timezone.localdate() - timedelta(days=1))
        vencido = portal_a.get("/proveedor/enlace/")
        self.assertContains(vencido, "Este enlace no se puede usar")
        self.assertNotContains(vencido, "$ 370,00")
        self.client.force_login(self.ana)
        self.assertContains(self.client.get(reverse("compras:pedidos")), "Fecha límite vencida")
