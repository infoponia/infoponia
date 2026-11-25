# Pruebas de las vistas de «Envasado» (COM-05a2, PROD-PNF-ENV; docs/casos_de_uso/produccion/envasado.md, «Pantallas» y «Pruebas»): permisos por rol, la lista con sus filtros y su orden, la carga
# (la página completa y, con HTMX, solo el bloque; sin JavaScript con «Actualizar»), el resumen como página, la confirmación, los mensajes de cada extensión (3b, 4a, 4b, 6a a 6c, 8a a 8d, 10a a 10c)
# y que `calcular/` y `revisar/` no escriben nada. El cliente de Django no ve el CSRF ni el JavaScript: eso va como paso de «navegador real» en la «Verificación a mano».

from datetime import timedelta
from html import unescape

from django.contrib.messages import get_messages
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from comercial.servicios import envasado
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    entrega,
    envase,
    escenario_comercial,
    marcar_concretada,
    reserva_lista,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
)
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_agronomo
from produccion.models import ReservaInsumo
from produccion.tests.fabricas import lote_maduro

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class Base(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 5000)
        self.agronomo = self.e.agronomo
        self.bandeja = envase(self.e.invernadero, 30)
        self.addCleanup(verificar_invariantes_de_entregas)

    def nueva(self, cantidad=100, dias=3, **opciones):
        venta = compra_venta(self.e, dias=dias, modalidad=opciones.pop("modalidad", "envio"))
        det = detalle(venta, self.e.variedad, cantidad)
        return entrega(venta, [reserva_lista(det, self.lote, cantidad)], **opciones)

    def entrar(self, usuario=None):
        self.client.force_login(usuario or self.agronomo)

    def url_carga(self, entrega_):
        return reverse("comercial:envasado_entrega", args=[entrega_.pk])

    def url_calcular(self, entrega_):
        return reverse("comercial:envasado_calcular", args=[entrega_.pk])

    def url_revisar(self, entrega_):
        return reverse("comercial:envasado_revisar", args=[entrega_.pk])

    def datos(self, entrega_, *filas, **extra):
        """Lo que envía el formulario: la huella vigente y `cantidad_<id>` por cada `(InsumoInvernadero, cantidad)`."""
        post = {"huella": envasado.huella_de(entrega_.pk)}
        post.update({f"cantidad_{i.pk}": str(c) for i, c in filas})
        post.update(extra)
        return post

    def mensajes(self, respuesta):
        return [str(m) for m in get_messages(respuesta.wsgi_request)]

    def activas(self, entrega_):
        return {r.insumo_invernadero_id: r.cantidad_reservada for r in ReservaInsumo.objects.filter(orden_id=entrega_.pk, estado="activa")}

    def planificar(self, entrega_, *filas):
        envasado.planificar_envasado(self.agronomo, envasado.CargaDeEnvasado(entrega_.pk, tuple(sorted((i.pk, str(c)) for i, c in filas)), envasado.huella_de(entrega_.pk)))


class PermisosTests(Base):
    def test_regla_solo_el_agronomo_a_cargo_entra_a_la_lista_y_a_la_carga(self):
        """Regla «Quién lo ejecuta»: el Gerente, el Vendedor, el Capataz y el Transportista reciben 403 (como «Cultivos», PRD-01)."""
        e1 = self.nueva()
        transportista = transportista_con_vehiculo(self.e.invernadero, "800")
        for usuario in (crear_gerente(), self.e.vendedor, self.e.capataz, transportista):
            self.entrar(usuario)
            for url in (reverse("comercial:envasado"), self.url_carga(e1), self.url_calcular(e1)):
                with self.subTest(rol=usuario.rol, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(self.url_revisar(e1), {}).status_code, 403)

    def test_regla_otro_agronomo_no_ve_la_entrega_ni_la_abre(self):
        """Invernadero de origen a cargo: otro Agrónomo no la ve en la lista y recibe 403 en la carga (D-28)."""
        e1 = self.nueva()
        otro = crear_agronomo(email="otro.agronomo@infoponia.com")
        self.entrar(otro)
        self.assertNotIn(e1.codigo, texto(self.client.get(reverse("comercial:envasado"))))
        self.assertEqual(self.client.get(self.url_carga(e1)).status_code, 403)
        self.assertEqual(self.client.post(self.url_revisar(e1), self.datos(e1, (self.bandeja, 5))).status_code, 403)

    def test_regla_sin_sesion_redirige_y_la_lista_solo_acepta_get(self):
        """Toda pantalla exige sesión; la lista no recibe POST (405) y `calcular/` y `revisar/` no reciben GET (405)."""
        e1 = self.nueva()
        self.assertEqual(self.client.get(reverse("comercial:envasado")).status_code, 302)
        self.entrar()
        self.assertEqual(self.client.post(reverse("comercial:envasado")).status_code, 405)
        self.assertEqual(self.client.get(self.url_calcular(e1)).status_code, 405)
        self.assertEqual(self.client.get(self.url_revisar(e1)).status_code, 405)

    def test_regla_una_entrega_inexistente_da_404(self):
        """Una entrega que no existe: 404."""
        self.entrar()
        self.assertEqual(self.client.get(reverse("comercial:envasado_entrega", args=[999999])).status_code, 404)


class ListaTests(Base):
    def ver(self, consulta="", **extra):
        self.entrar()
        return self.client.get(reverse("comercial:envasado") + consulta, **extra)

    def test_paso_2_lista_las_entregas_a_realizar_por_fecha_con_sus_columnas(self):
        """Paso 2: entrega y contrato, cliente con «Retiro»/transportista/«Sin transportista», contenido y peso, fecha y envasado («Sin planificar» / «Planificado»); por fecha y después id."""
        tarde = self.nueva(100, dias=6)
        pronto = self.nueva(50, dias=2, modalidad="retiro")
        self.nueva(10, dias=2, estado="concretada")
        self.nueva(10, dias=2, estado="cancelada")
        self.planificar(tarde, (self.bandeja, 10))
        html = texto(self.ver())
        self.assertEqual(sorted([tarde.codigo, pronto.codigo], key=html.index), [pronto.codigo, tarde.codigo])
        for esperado in (tarde.contrato_entrega.codigo, pronto.contrato_entrega.cliente.nombre_visible, "Retiro", "Sin transportista", "Sin planificar", "Planificado", "100 ", "Planificar envasado", "Modificar envasado"):
            self.assertIn(esperado, html)
        self.assertEqual(html.count("Planificar envasado"), 1)  # solo la de la entrega sin envasado; la otra dice «Modificar envasado»
        self.assertNotIn("Concretada", html)

    def test_paso_2_el_texto_explicativo_y_el_vacio(self):
        """Texto explicativo de `tabEnvasado` y extensión 2a: «No hay entregas para envasar.»"""
        html = texto(self.ver())
        self.assertIn("Las entregas las planifica InfoPonia. Reservá los envases de cada una: se descuentan del stock recién al concretarla.", html)
        self.assertIn("No hay entregas para envasar.", html)

    def test_variacion_2_el_filtro_de_fecha_programada_es_exacto(self):
        """Lista de tecnología, 2: filtro por fecha programada (formulario GET común con «Filtrar»)."""
        a = self.nueva(dias=2)
        b = self.nueva(dias=5)
        html = texto(self.ver(f"?fecha={a.fecha_programada_orden:%Y-%m-%d}"))
        self.assertIn(a.codigo, html)
        self.assertNotIn(b.codigo, html)
        self.assertIn('method="get"', html)
        self.assertIn(">Filtrar<", html)

    def test_variacion_2_el_filtro_de_invernadero_solo_aparece_con_mas_de_uno_y_los_valores_malos_se_ignoran(self):
        """Con un solo invernadero a cargo no hay selector; un id o una fecha mal formados no dan error."""
        self.nueva()
        self.assertNotIn('name="invernadero"', texto(self.ver()))
        self.assertEqual(self.ver("?invernadero=abc&fecha=zz").status_code, 200)

    def test_ext_3b_una_entrega_en_curso_dice_en_curso_sin_boton(self):
        """Extensión 3b: con envío, de hoy y con el vehículo del transportista en ruta, la fila dice «En curso» y no ofrece «Planificar envasado»."""
        en_ruta = transportista_con_vehiculo(self.e.invernadero, "800", en_ruta=True)
        e1 = self.nueva(dias=0, transportista=en_ruta)
        html = texto(self.ver())
        self.assertIn("En curso", html)
        self.assertNotIn(self.url_carga(e1), html)

    def test_ext_4b_una_entrega_atrasada_dice_atrasada(self):
        """Pantalla: la fecha programada con «Atrasada» si corresponde."""
        venta = compra_venta(self.e, dias=0)
        det = detalle(venta, self.e.variedad, 10)
        entrega(venta, [reserva_lista(det, self.lote, 10)], fecha=HOY - timedelta(days=2))
        self.assertIn("Atrasada", texto(self.ver()))

    def test_regla_la_lista_no_hace_consultas_por_fila(self):
        """`assertNumQueries` igual con una y con tres entregas."""
        self.nueva()
        self.ver()
        with CaptureQueriesContext(connection) as pocas:
            self.client.get(reverse("comercial:envasado"))
        self.nueva()
        self.nueva()
        with CaptureQueriesContext(connection) as muchas:
            self.client.get(reverse("comercial:envasado"))
        self.assertEqual(len(pocas), len(muchas))

    def test_regla_con_htmx_devuelve_solo_la_tabla(self):
        """Con `HX-Request` devuelve el fragmento de la tabla y varía por ese encabezado."""
        e1 = self.nueva()
        respuesta = self.ver(**HTMX)
        self.assertIn(e1.codigo, texto(respuesta))
        self.assertNotIn("<html", texto(respuesta))
        self.assertIn("HX-Request", respuesta.headers["Vary"])


class CargaTests(Base):
    def abrir(self, entrega_, **extra):
        self.entrar()
        return self.client.get(self.url_carga(entrega_), **extra)

    def test_paso_4_presenta_la_entrega_y_los_envases_con_lo_disponible_y_la_unidad(self):
        """Paso 4: cliente, destino, fecha, contenido y peso; los envases del invernadero con lo disponible y su unidad; sin cantidad sugerida; botones «Actualizar» y «Revisar»."""
        e1 = self.nueva(100)
        html = texto(self.abrir(e1))
        for esperado in (e1.codigo, e1.contrato_entrega.cliente.nombre_visible, "Bandeja PET 1 kg", "30", "unidad", "Actualizar", "Revisar", "Cancelar", 'name="huella"'):
            self.assertIn(esperado, html)
        self.assertNotIn("Confirmar envasado", html)

    def test_paso_4_el_buscador_filtra_los_envases_por_nombre_sin_select(self):
        """Variación 5: se buscan por nombre (no un `<select>` nativo para el envase)."""
        envase(self.e.invernadero, 10, nombre="Caja de cartón")
        e1 = self.nueva()
        self.entrar()
        html = texto(self.client.post(self.url_calcular(e1), self.datos(e1, busqueda="cart")))
        self.assertIn("Caja de cartón", html)
        self.assertNotIn("Bandeja PET 1 kg", html)
        self.assertNotIn('name="envase"', html)

    def test_ext_3a_una_entrega_con_envasado_abre_con_sus_reservas_y_lo_disponible_incluye_lo_propio(self):
        """Extensión 3a: la carga inicial son las reservas activas y lo disponible suma su propia cantidad (20 reservadas + 10 libres = 30)."""
        e1 = self.nueva()
        self.planificar(e1, (self.bandeja, 20))
        html = texto(self.abrir(e1))
        self.assertIn('value="20"', html)
        self.assertIn("30", html)

    def test_ext_3b_una_entrega_en_curso_informa_y_no_ofrece_el_formulario(self):
        """Extensión 3b: «… ya inició la ruta con esta entrega: su envasado no se puede cambiar. Los envases se confirman al concretarla.» y ningún botón de revisar."""
        en_ruta = transportista_con_vehiculo(self.e.invernadero, "800", en_ruta=True)
        e1 = self.nueva(dias=0, transportista=en_ruta)
        html = texto(self.abrir(e1))
        self.assertIn(f"{en_ruta.get_full_name()} ya inició la ruta con esta entrega: su envasado no se puede cambiar. Los envases se confirman al concretarla.", html)
        self.assertNotIn(">Revisar<", html)

    def test_ext_4a_sin_envases_habilitados_lo_dice_y_ofrece_habilitarlos(self):
        """Extensión 4a: «Este invernadero no tiene envases habilitados.» con el acceso a las existencias del invernadero (CMP-HAB-IIN)."""
        from inventario.models import InsumoInvernadero

        e1 = self.nueva()
        InsumoInvernadero.objects.filter(pk=self.bandeja.pk).update(estado_insumo_invernadero="inactivo")
        html = texto(self.abrir(e1))
        self.assertIn("Este invernadero no tiene envases habilitados.", html)
        self.assertIn(reverse("inventario:existencias"), html)

    def test_ext_4b_una_entrega_atrasada_lo_indica(self):
        """Extensión 4b: la entrega atrasada se marca y lo disponible se calcula a hoy."""
        venta = compra_venta(self.e, dias=0)
        det = detalle(venta, self.e.variedad, 10)
        e1 = entrega(venta, [reserva_lista(det, self.lote, 10)], fecha=HOY - timedelta(days=2))
        self.assertIn("atrasada", texto(self.abrir(e1)).lower())

    def test_ext_10a_una_entrega_concretada_o_cancelada_no_se_abre_y_vuelve_a_la_lista(self):
        """Extensión 10a (al abrirla por la URL): se informa su situación y se vuelve a la lista."""
        for estado in ("concretada", "cancelada"):
            with self.subTest(estado=estado):
                e1 = self.nueva(estado=estado)
                respuesta = self.abrir(e1)
                self.assertRedirects(respuesta, reverse("comercial:envasado"), fetch_redirect_response=False)
                self.assertTrue(any("ya no está a realizar" in m for m in self.mensajes(respuesta)))

    def test_regla_abrir_la_carga_no_escribe_nada(self):
        """Abrir la pantalla es una lectura: no crea reservas."""
        e1 = self.nueva()
        self.abrir(e1)
        self.assertEqual(ReservaInsumo.objects.count(), 0)


class CalcularTests(Base):
    def calcular(self, entrega_, post, **extra):
        self.entrar()
        return self.client.post(self.url_calcular(entrega_), post, **extra)

    def test_paso_5_agregar_un_envase_lo_suma_a_la_carga_con_lo_que_queda_y_no_escribe(self):
        """Pasos 5 y 6: «Agregar» suma el envase con su cantidad y lo disponible que le queda; `calcular/` no escribe."""
        e1 = self.nueva()
        html = texto(self.calcular(e1, self.datos(e1, agregar=self.bandeja.pk, **{f"nueva_{self.bandeja.pk}": "12"})))
        self.assertIn(f'name="cantidad_{self.bandeja.pk}"', html)
        self.assertIn('value="12"', html)
        self.assertIn("18", html)  # 30 - 12
        self.assertEqual(ReservaInsumo.objects.count(), 0)

    def test_ext_6a_una_cantidad_invalida_marca_el_error_en_su_fila(self):
        """Extensión 6a: «Ingresá una cantidad mayor que 0, un número entero (unidad).»; con decimales admitidos, la cantidad de decimales."""
        e1 = self.nueva()
        for mala in ("0", "-3", "2,5", "abc", ""):
            with self.subTest(cantidad=mala):
                html = texto(self.calcular(e1, self.datos(e1, (self.bandeja, mala))))
                self.assertIn("Ingresá una cantidad mayor que 0, un número entero (unidad).", html)

    def test_ext_6b_una_cantidad_que_supera_lo_disponible_lo_informa_con_la_ayuda(self):
        """Extensión 6b: «Supera lo disponible: quedan 30 unidades…» y la ayuda para pedir o ajustar stock."""
        e1 = self.nueva()
        html = texto(self.calcular(e1, self.datos(e1, (self.bandeja, 40))))
        self.assertIn("Supera lo disponible: quedan 30 unidades", html)
        self.assertIn("Si necesitás más, pedilo con un pedido de compra o, si el depósito tiene más de lo registrado, ajustá el stock.", html)
        self.assertIn("disabled", html)  # «Revisar» bloqueado mientras haya errores

    def test_ext_6c_agregar_un_envase_que_ya_esta_reemplaza_su_cantidad_con_aviso(self):
        """Extensión 6c: «Ya estaba en la lista: se reemplazó la cantidad.»; la carga tiene una sola fila del envase."""
        e1 = self.nueva()
        html = texto(self.calcular(e1, self.datos(e1, (self.bandeja, 5), agregar=self.bandeja.pk, **{f"nueva_{self.bandeja.pk}": "9"})))
        self.assertIn("Ya estaba en la lista: se reemplazó la cantidad.", html)
        self.assertEqual(html.count(f'name="cantidad_{self.bandeja.pk}"'), 1)
        self.assertIn('value="9"', html)

    def test_ext_5_6a_quitar_un_envase_lo_saca_de_la_carga(self):
        """Extensiones 5-6a: «Quitar» saca la fila; lo disponible del envase vuelve a ofrecerse para agregarlo."""
        e1 = self.nueva()
        html = texto(self.calcular(e1, self.datos(e1, (self.bandeja, 5), quitar=self.bandeja.pk)))
        self.assertNotIn(f'name="cantidad_{self.bandeja.pk}"', html)

    def test_regla_con_htmx_devuelve_solo_el_bloque_de_la_carga(self):
        """Con `HX-Request` redibuja solo el bloque (sin `<html`), con los botones sin envío en curso (D-29) y sin disparar nada al tipear."""
        e1 = self.nueva()
        respuesta = self.calcular(e1, self.datos(e1, (self.bandeja, 5)), **HTMX)
        html = texto(respuesta)
        self.assertNotIn("<html", html)
        self.assertIn("data-sin-envio-en-curso", html)
        self.assertNotIn('hx-trigger="input', html)
        self.assertNotIn('hx-trigger="change', html)
        self.assertIn("HX-Request", respuesta.headers["Vary"])

    def test_regla_sin_javascript_la_pagina_completa_trae_actualizar(self):
        """Respaldo sin JavaScript: sin `HX-Request`, la misma ruta devuelve la página completa con «Actualizar»."""
        e1 = self.nueva()
        html = texto(self.calcular(e1, self.datos(e1, (self.bandeja, 5))))
        self.assertIn("<html", html)
        self.assertIn("Actualizar", html)


class ResumenYConfirmacionTests(Base):
    def revisar(self, entrega_, post, **extra):
        self.entrar()
        return self.client.post(self.url_revisar(entrega_), post, **extra)

    def confirmar(self, entrega_, post):
        self.entrar()
        return self.client.post(self.url_carga(entrega_), post)

    def test_paso_8_el_resumen_es_una_pagina_con_lo_que_queda_y_no_escribe(self):
        """Paso 8: la entrega (cliente y fecha), por envase la cantidad y lo disponible que le queda, y «Confirmar envasado»; «Volver a la carga» (8d). No escribe."""
        e1 = self.nueva()
        html = texto(self.revisar(e1, self.datos(e1, (self.bandeja, 12))))
        for esperado in (e1.codigo, e1.contrato_entrega.cliente.nombre_visible, "Bandeja PET 1 kg", "12", "18", "Confirmar envasado", "Volver a la carga", "Cancelar"):
            self.assertIn(esperado, html)
        self.assertEqual(ReservaInsumo.objects.count(), 0)

    def test_ext_3a_el_resumen_de_una_modificacion_muestra_anterior_y_nueva_y_los_quitados(self):
        """Extensión 3a, paso 8: por envase, la cantidad reservada anterior y la nueva, y los envases que se quitan."""
        e1 = self.nueva()
        caja = envase(self.e.invernadero, 10, nombre="Caja de cartón")
        self.planificar(e1, (self.bandeja, 20), (caja, 4))
        html = texto(self.revisar(e1, self.datos(e1, (self.bandeja, 25))))
        self.assertIn("20", html)
        self.assertIn("25", html)
        self.assertIn("Caja de cartón", html)
        self.assertIn("Se quita", html)

    def test_ext_8a_sin_envases_vuelve_a_la_carga_con_el_mensaje(self):
        """Extensión 8a: «Indicá al menos un envase.»; vuelve a la carga, sin resumen."""
        e1 = self.nueva()
        html = texto(self.revisar(e1, self.datos(e1)))
        self.assertIn("Indicá al menos un envase.", html)
        self.assertNotIn("Confirmar envasado", html)

    def test_ext_8b_todos_quitados_avisa_y_deja_confirmar(self):
        """Extensión 8b: «La entrega va a quedar sin envasado planificado: al concretarla se declaran los envases usados.» y se puede confirmar."""
        e1 = self.nueva()
        self.planificar(e1, (self.bandeja, 20))
        html = texto(self.revisar(e1, self.datos(e1)))
        self.assertIn("La entrega va a quedar sin envasado planificado: al concretarla se declaran los envases usados.", html)
        self.assertIn("Confirmar envasado", html)

    def test_ext_8c_sin_cambios_lo_informa(self):
        """Extensión 8c: «No hay cambios para registrar.»"""
        e1 = self.nueva()
        self.planificar(e1, (self.bandeja, 20))
        self.assertIn("No hay cambios para registrar.", texto(self.revisar(e1, self.datos(e1, (self.bandeja, 20)))))

    def test_ext_6b_el_resumen_con_errores_vuelve_a_la_carga(self):
        """Con una fila con error no hay resumen: vuelve a la carga con el error por campo."""
        e1 = self.nueva()
        html = texto(self.revisar(e1, self.datos(e1, (self.bandeja, 99))))
        self.assertIn("Supera lo disponible", html)
        self.assertNotIn("Confirmar envasado", html)

    def test_paso_9_a_11_confirmar_registra_avisa_y_vuelve_a_la_lista(self):
        """Pasos 9 a 11: registra las reservas (postcondición a), avisa «Envasado de OT-… planificado.» y vuelve a la lista."""
        e1 = self.nueva()
        respuesta = self.confirmar(e1, self.datos(e1, (self.bandeja, 12), confirmar="1"))
        self.assertRedirects(respuesta, reverse("comercial:envasado"), fetch_redirect_response=False)
        self.assertEqual(self.mensajes(respuesta), [f"Envasado de {e1.codigo} planificado."])
        self.assertEqual(self.activas(e1), {self.bandeja.pk: 12})

    def test_ext_10a_confirmar_una_entrega_que_se_concreto_no_registra_y_lo_informa(self):
        """Extensión 10a: la entrega ya no está «a realizar»: no se registra nada, se informa su estado y se vuelve a la lista."""
        e1 = self.nueva()
        datos = self.datos(e1, (self.bandeja, 12), confirmar="1")
        marcar_concretada(e1)  # COM-06a: una concretada con sus cantidades y su monto (antes, solo el estado)
        respuesta = self.confirmar(e1, datos)
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(any("ya no está a realizar" in m for m in self.mensajes(respuesta)))
        self.assertEqual(ReservaInsumo.objects.count(), 0)

    def test_ext_10b_lo_disponible_bajo_conserva_los_datos_y_vuelve_a_la_carga(self):
        """Extensión 10b: otra operación redujo lo disponible: no se registra, se conservan los datos y se informa qué envase cambió y lo vigente."""
        e1 = self.nueva()
        datos = self.datos(e1, (self.bandeja, 25), confirmar="1")
        otra = self.nueva()
        self.planificar(otra, (self.bandeja, 20))
        respuesta = self.confirmar(e1, {**datos, "huella": envasado.huella_de(e1.pk)})
        html = texto(respuesta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Supera lo disponible: quedan 10 unidades", html)
        self.assertIn('value="25"', html)
        self.assertEqual(self.activas(e1), {})

    def test_ext_10c_otro_cambio_en_la_misma_entrega_vuelve_al_paso_4_con_las_reservas_vigentes(self):
        """Extensión 10c: «Mientras cargabas, el envasado de esta entrega cambió…»: no registra y vuelve a la carga con las reservas vigentes."""
        e1 = self.nueva()
        huella_vieja = envasado.huella_de(e1.pk)
        self.planificar(e1, (self.bandeja, 7))
        respuesta = self.confirmar(e1, {**self.datos(e1, (self.bandeja, 12), confirmar="1"), "huella": huella_vieja})
        self.assertRedirects(respuesta, self.url_carga(e1), fetch_redirect_response=False)
        self.assertTrue(any("cambió" in m for m in self.mensajes(respuesta)))
        self.assertEqual(self.activas(e1), {self.bandeja.pk: 7})

    def test_ext_3b_confirmar_una_entrega_en_curso_no_registra(self):
        """Extensión 10a (en curso): no se registra nada y se informa que el transportista ya inició la ruta."""
        en_ruta = transportista_con_vehiculo(self.e.invernadero, "800", en_ruta=True)
        e1 = self.nueva(dias=0, transportista=en_ruta)
        respuesta = self.confirmar(e1, self.datos(e1, (self.bandeja, 12), confirmar="1"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(any("ya inició la ruta" in m for m in self.mensajes(respuesta)))
        self.assertEqual(ReservaInsumo.objects.count(), 0)

    def test_regla_quitar_todo_y_confirmar_cancela_las_reservas(self):
        """Postcondición b: confirmar con todos los envases quitados deja la entrega sin envasado planificado (las reservas pasan a «cancelada»)."""
        e1 = self.nueva()
        self.planificar(e1, (self.bandeja, 20))
        respuesta = self.confirmar(e1, self.datos(e1, confirmar="1"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.activas(e1), {})
        self.assertEqual(ReservaInsumo.objects.filter(orden_id=e1.pk, estado="cancelada").count(), 1)
