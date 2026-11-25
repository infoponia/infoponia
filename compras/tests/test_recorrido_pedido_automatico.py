# Recorrido de punta a punta del pedido automático por stock bajo (CMP-07, CMP-AUT-PED y D-104): lo que haría una persona, hecho con el cliente de Django (docs/patrones/verificacion_a_mano.md,
# D-96). Es una sola prueba larga a propósito: el Gerente cambia el margen en la pantalla y queda auditado, el Agrónomo no puede, se corre ``proceso_diario --solo generar_pedidos_automaticos
# --fecha``, el Agrónomo ve el pedido y su aviso, el proveedor abre su enlace del correo, una segunda corrida no duplica y los estados 3a y 5a. Las reglas sueltas las prueban
# ``test_cmp_aut_ped.py`` y ``test_pedidos_automaticos_concurrencia.py``. No ve lo que solo un navegador ve (CSRF, encabezados, JavaScript): eso va como paso de «navegador real».

import re
from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from compras.models import Pedido
from compras.tests.fabricas import proveedor, tipo_de_insumo
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import CLAVE, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote
from maestros.models import PARAMETROS_DE_CONFIGURACION, ConfiguracionOperativa
from maestros.tests.fabricas import crear_agronomo, crear_invernadero


def correr(test, fecha):
    """``proceso_diario --solo generar_pedidos_automaticos --fecha`` con los correos ejecutados; devuelve lo que imprimió."""
    salida = StringIO()
    with test.captureOnCommitCallbacks(execute=True):
        call_command("proceso_diario", "--solo", "generar_pedidos_automaticos", "--fecha", fecha.isoformat(), stdout=salida)
    return salida.getvalue()


@override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test")
class RecorridoDePedidoAutomaticoTests(ConDatosDeInventario, TestCase):
    """Fuente: docs/casos_de_uso/compras/pedido_automatico.md, D-104, D-56 y D-36."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.gerente = crear_gerente()
        self.ana = crear_agronomo(email="ana@infoponia.com")
        self.otra = crear_agronomo(email="otra@infoponia.com")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        semillas = tipo_de_insumo("Semillas y plantines")
        self.lechuga = existencia(insumo("Lechuga", tipo=semillas, unidad="unidad"), self.norte, minimo=20, precio="12.50")
        lote(self.lechuga, 5)  # bajo el mínimo
        self.nutriente = existencia(insumo("Nutriente", tipo=semillas, unidad="kg"), self.norte, minimo=5, precio="100.00")
        lote(self.nutriente, 9)  # sobre el mínimo: no se pide
        self.proveedor_a = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com", especialidades=[semillas])
        self.proveedor_b = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com", especialidades=[semillas])
        self.config = reverse("configuracion:pantalla")
        self.guardar = reverse("configuracion:guardar_parametros")

    def parametros(self, **cambios):
        fila = ConfiguracionOperativa.objects.get()
        return {c: str(getattr(fila, c)) for c, *_ in PARAMETROS_DE_CONFIGURACION} | {k: str(v) for k, v in cambios.items()}

    def test_recorrido_completo_del_margen_la_corrida_y_los_estados(self):
        # Paso 1 · El Gerente ve el margen en «Compras» (valor inicial 20) y lo cambia a 50 (D-104 punto 3; ADM-MOD-CFG).
        self.client.login(username=self.gerente.email, password=CLAVE)
        pantalla = self.client.get(self.config)
        self.assertContains(pantalla, "Margen del pedido automático")
        self.assertEqual(pantalla.context["form"]["porc_margen_pedido_automatico"].value(), 20)
        self.client.post(self.guardar, self.parametros(porc_margen_pedido_automatico="50"))
        self.assertEqual(ConfiguracionOperativa.objects.get().porc_margen_pedido_automatico, 50)

        # Paso 2 · Un margen fuera de 0 a 100 no se guarda; el cambio queda en «Auditoría» con su etiqueta.
        invalido = self.client.post(self.guardar, self.parametros(porc_margen_pedido_automatico="150"))
        self.assertEqual(invalido.status_code, 200)
        self.assertEqual(ConfiguracionOperativa.objects.get().porc_margen_pedido_automatico, 50)
        registro = RegistroAuditoria.objects.get(accion="modificacion_configuracion")
        self.assertEqual(registro.detalle["cambios"], {"porc_margen_pedido_automatico": {"antes": 20, "despues": 50}})
        self.assertContains(self.client.get(reverse("core:auditoria_registro", args=[registro.pk])), "Margen del pedido automático (%)")

        # Paso 3 · El Agrónomo no entra a la configuración (precondición a: solo el Gerente).
        self.client.logout()
        self.client.login(username=self.ana.email, password=CLAVE)
        self.assertEqual(self.client.get(self.config).status_code, 403)
        self.assertEqual(self.client.post(self.guardar, self.parametros(porc_margen_pedido_automatico="0")).status_code, 403)
        self.assertEqual(ConfiguracionOperativa.objects.get().porc_margen_pedido_automatico, 50)

        # Paso 4 · Se corre el paso con una fecha (D-56): un pedido para Norte con la lechuga (20 × 1,5 − 5 = 25) y sin el nutriente.
        salida = correr(self, self.hoy)
        self.assertIn("Pedidos automáticos por stock bajo: procesados 1 · creados 1 · resueltos 0", salida)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.agronomo_id, self.ana.pk)
        (detalle,) = pedido.detalles.all()
        self.assertEqual((detalle.insumo_invernadero_id, int(detalle.cantidad_detalle)), (self.lechuga.pk, 25))
        self.assertEqual(pedido.fecha_limite_cotizaciones, self.hoy + timedelta(days=3))

        # Paso 5 · La auditoría lo registra como InfoPonia, con su origen y el margen; el Agrónomo lo ve en «Pedidos» y tiene su aviso.
        alta = RegistroAuditoria.objects.get(accion="alta_pedido")
        datos = alta.detalle["datos"]
        self.assertEqual((alta.usuario_id, alta.rol, datos["origen"], datos["porc_margen_pedido_automatico"]), (None, "infoponia", "automático", 50))
        self.assertContains(self.client.get(reverse("compras:pedidos")), str(pedido))
        self.assertContains(self.client.get(reverse("compras:pedido_ficha", args=[pedido.pk])), "Lechuga")
        (aviso,) = Notificacion.objects.filter(destinatario=self.ana)
        self.assertEqual(aviso.titulo, f"Pedido {pedido} creado automáticamente")

        # Paso 6 · Otra Agrónoma no ve el pedido (alcance por usuario).
        self.client.logout()
        self.client.login(username=self.otra.email, password=CLAVE)
        self.assertNotEqual(self.client.get(reverse("compras:pedido_ficha", args=[pedido.pk])).status_code, 200)

        # Paso 7 · Cada proveedor recibió su correo; abre su enlace sin cuenta y ve el pedido sin precios (CMP-ENV-COT).
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["info@este.com", "ventas@sur.com"])
        cuerpo = next(m.body for m in mail.outbox if m.to == ["ventas@sur.com"])
        token = re.search(r"https://sitio\.test/proveedor/([\w-]+)/", cuerpo).group(1)
        portal = Client().get(f"/proveedor/{token}/", follow=True)
        self.assertEqual(portal.status_code, 200)
        self.assertContains(portal, "Lechuga")
        self.assertNotContains(portal, "12,50")

        # Paso 8 · Una segunda corrida el mismo día no duplica nada (extensión 1a).
        correr(self, self.hoy)
        self.assertEqual((Pedido.objects.count(), len(mail.outbox), Notificacion.objects.filter(destinatario=self.ana).count()), (1, 2, 1))

        # Paso 9 · Extensión 3a: un insumo bajo el mínimo de una categoría que ningún proveedor atiende no genera pedido y avisa una sola vez al Agrónomo y al Gerente.
        existencia(insumo("Cal", unidad="kg"), self.norte, minimo=5)
        correr(self, self.hoy)
        correr(self, self.hoy)
        self.assertEqual(Pedido.objects.count(), 1)
        sin_proveedores = Notificacion.objects.filter(titulo__startswith="Sin proveedores para el pedido automático de Invernadero Norte")
        self.assertEqual(sorted(sin_proveedores.values_list("destinatario__email", flat=True)), sorted([self.ana.email, self.gerente.email]))

        # Paso 10 · Extensión 5a: un invernadero sin Agrónomo no genera pedido y avisa una sola vez al Gerente.
        huerfano = crear_invernadero("Invernadero Huérfano")
        existencia(insumo("Semilla de albahaca", tipo=self.lechuga.insumo.tipo_insumo, unidad="unidad"), huerfano, minimo=10)
        correr(self, self.hoy)
        correr(self, self.hoy)
        self.assertEqual(Pedido.objects.count(), 1)
        sin_agronomo = Notificacion.objects.filter(titulo__startswith="Pedido automático sin Agrónomo en Invernadero Huérfano")
        self.assertEqual([n.destinatario_id for n in sin_agronomo], [self.gerente.pk])

        # Paso 11 · Otro día, los avisos 3a y 5a se repiten una vez más (una vez por día).
        correr(self, self.hoy + timedelta(days=1))
        self.assertEqual((sin_proveedores.all().count(), sin_agronomo.all().count()), (4, 2))  # ``.all()``: un queryset ya iterado quedó en caché
