# Pruebas de las vistas de las solicitudes de revisión (COM-07a, paso 9; docs/casos_de_uso/comercial/solicitudes.md, «Pantallas»): permisos (el Vendedor en lectura, los demás roles 403), la lista con sus filtros y su contador, la
# ficha con el panel del Gerente, el resumen con HTMX y sin JavaScript, confirmar, el medio del reintegro, anular, el comprobante, «Reenviar aviso», el registrante del enlace de las alertas, el grupo «Solicitudes» del panel de control y la
# sección de la ficha del suministro. Verifican en el HTML que los botones y enlaces de acción aparecen **solo** para el rol y el estado que corresponden (D-30: ningún botón lleva a un 403). Solo el cliente de pruebas de Django.
# Fuente: docs/casos_de_uso/comercial/solicitudes.md («Pantallas», «El enlace de las alertas», «Lo que completa a otras tareas»), D-30, D-61, D-69.

from decimal import Decimal
from html import unescape

from django.test import override_settings
from django.urls import reverse

from comercial.models import IntentoFallido, SolicitudRevision
from comercial.servicios import registrantes, solicitudes
from comercial.tests.base_solicitudes import BaseDeSolicitudes
from comercial.tests.fabricas import queja_aceptada, transportista_con_vehiculo
from core.models import Usuario
from maestros import extensiones as extensiones_de_maestros
from maestros.models import Alerta

D = Decimal


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class BaseDeVistas(BaseDeSolicitudes):
    def ir(self, nombre, *args, usuario=None, **extra):
        self.client.force_login(usuario or self.gerente)
        return self.client.get(reverse(f"comercial:{nombre}", args=args), **extra)

    def enviar(self, nombre, *args, datos=None, usuario=None, **extra):
        self.client.force_login(usuario or self.gerente)
        return self.client.post(reverse(f"comercial:{nombre}", args=args), datos or {}, **extra)


class PermisosTests(BaseDeVistas):
    def test_los_demas_roles_y_los_anonimos_no_entran(self):
        """El Agrónomo y el Capataz reciben 403 en todas las pantallas de lectura; un anónimo, la pantalla de ingreso."""
        x = self.armar()
        for rol in (self.e.agronomo, self.e.capataz):
            for nombre, args in (("solicitudes", ()), ("solicitud", (x.solicitud.pk,)), ("solicitud_comprobante", (x.solicitud.pk,))):
                self.assertEqual(self.ir(nombre, *args, usuario=rol).status_code, 403, (rol, nombre))
        self.client.logout()
        self.assertEqual(self.client.get(reverse("comercial:solicitudes")).status_code, 302)

    def test_el_vendedor_lee_pero_no_resuelve_ni_anula(self):
        """El Vendedor abre la lista y la ficha de sus contratos; resolver, el resumen y anular son del Gerente (403)."""
        x = self.armar()
        self.assertEqual(self.ir("solicitudes", usuario=self.e.vendedor).status_code, 200)
        self.assertEqual(self.ir("solicitud", x.solicitud.pk, usuario=self.e.vendedor).status_code, 200)
        for nombre in ("solicitud_resolver_revisar", "solicitud_resolver"):
            self.assertEqual(self.enviar(nombre, x.solicitud.pk, datos={"decision": "aceptar"}, usuario=self.e.vendedor).status_code, 403, nombre)
        self.assertEqual(self.ir("solicitud_anular", x.solicitud.pk, usuario=self.e.vendedor).status_code, 403)
        self.assertEqual(SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, "pendiente")

    def test_la_ficha_de_otro_vendedor_es_403_con_mensaje_y_una_inexistente_404(self):
        """Regla 1 de COM-CNS-SRV: la solicitud de un contrato ajeno da 403; un id que no existe, 404."""
        from maestros.tests.fabricas import crear_vendedor

        x = self.armar()
        otro = crear_vendedor(email="otro@infoponia.com")
        self.assertEqual(self.ir("solicitud", x.solicitud.pk, usuario=otro).status_code, 403)
        self.assertEqual(self.ir("solicitud", 99999999).status_code, 404)

    def test_los_metodos_no_permitidos(self):
        """Resolver, el resumen y reenviar son POST; la ficha, la lista y el comprobante, de lectura."""
        x = self.armar()
        self.client.force_login(self.gerente)
        for nombre in ("solicitud_resolver", "solicitud_resolver_revisar", "solicitud_reenviar_aviso"):
            self.assertEqual(self.client.get(reverse(f"comercial:{nombre}", args=[x.solicitud.pk])).status_code, 405, nombre)
        self.assertEqual(self.client.post(reverse("comercial:solicitud", args=[x.solicitud.pk])).status_code, 405)


class ListaTests(BaseDeVistas):
    def test_la_lista_muestra_las_solicitudes_con_el_enlace_a_la_ficha_y_el_texto_explicativo(self):
        """La pestaña: el texto explicativo, una fila por solicitud con «Ver» y las pendientes primero; la pestaña está en la barra de «Comercial»."""
        d, q = self.armar(), self.armar(tipo="queja")
        self.resolver(q.solicitud)
        html = texto(self.ir("solicitudes"))
        for esperado in ("Las quejas las presenta el cliente", d.solicitud.codigo, q.solicitud.codigo, reverse("comercial:solicitud", args=[d.solicitud.pk]), "Discrepancia de cantidad", "Queja · estado de la mercadería", "Solicitudes de revisión"):
            self.assertIn(esperado, html)
        self.assertLess(html.index(d.solicitud.codigo), html.index(q.solicitud.codigo))  # la pendiente, primero

    def test_el_contador_rojo_de_la_pestana_es_solo_del_gerente(self):
        """«Contador de la pestaña»: el Gerente ve las pendientes en rojo; el Vendedor, sin número."""
        self.armar(), self.armar(tipo="queja")
        self.assertIn('status-danger">2<', self.ir("solicitudes").content.decode())
        self.assertNotIn('status-danger">2<', self.ir("solicitudes", usuario=self.e.vendedor).content.decode())

    def test_la_lista_filtra_por_la_url_y_con_htmx_devuelve_solo_la_tabla(self):
        """Los filtros viajan en la URL; con HTMX solo vuelve la tabla (sin la página entera)."""
        d, q = self.armar(), self.armar(tipo="queja")
        self.client.force_login(self.gerente)
        pagina = texto(self.client.get(reverse("comercial:solicitudes") + "?tipo=queja"))
        self.assertIn(q.solicitud.codigo, pagina)
        self.assertNotIn(d.solicitud.codigo, pagina)
        parcial = texto(self.client.get(reverse("comercial:solicitudes") + "?tipo=queja", HTTP_HX_REQUEST="true"))
        self.assertIn(q.solicitud.codigo, parcial)
        self.assertNotIn("<html", parcial)

    def test_una_lista_sin_resultados_lo_dice(self):
        """El estado vacío: sin solicitudes, el mensaje; con filtros que no encuentran nada, otro mensaje."""
        self.assertIn("Todavía no hay solicitudes de revisión.", texto(self.ir("solicitudes")))
        self.armar()
        self.assertIn("No hay solicitudes con estos filtros.", texto(self.client.get(reverse("comercial:solicitudes") + "?numero=99999")))

    def test_el_vendedor_ve_solo_las_solicitudes_de_sus_contratos(self):
        """Regla 1: la lista del Vendedor trae las de sus contratos."""
        from comercial.models import Suministro
        from maestros.tests.fabricas import crear_vendedor

        mia, ajena = self.armar(), self.armar()
        Suministro.objects.filter(pk=ajena.contrato.pk).update(vendedor=crear_vendedor(email="otro@infoponia.com"))
        html = texto(self.ir("solicitudes", usuario=self.e.vendedor))
        self.assertIn(mia.solicitud.codigo, html)
        self.assertNotIn(ajena.solicitud.codigo, html)


class FichaTests(BaseDeVistas):
    def test_el_gerente_ve_el_panel_para_decidir_con_sus_textos_y_el_boton_de_ver_resumen(self):
        """Paso 4: la ficha de una pendiente trae el panel «Evaluar la discrepancia» con la decisión, las observaciones, la indemnización «Sale de la cláusula», los incumplimientos y «Ver resumen»; no trae «Anular resolución»."""
        x = self.armar()
        html = texto(self.ir("solicitud", x.solicitud.pk))
        for esperado in ("Evaluar la discrepancia", "Hubo incumplimiento (aceptar)", "No hubo incumplimiento (rechazar)", "Aceptar significa que hubo un incumplimiento de la empresa", "Sale de la cláusula; no se puede modificar.",
                         "0 → 1 de 3 tolerados", "Ver resumen", reverse("comercial:solicitud_resolver_revisar", args=[x.solicitud.pk]), "Mínimo pactado", "$ 15,00"):
            self.assertIn(esperado, html)
        self.assertNotIn("Anular resolución", html)
        self.assertNotIn("Confirmar la decisión", html)

    def test_el_vendedor_ve_el_aviso_y_ni_el_panel_ni_los_botones_de_escritura(self):
        """Regla 4: al Vendedor, «La evalúa el Gerente» y nada para decidir ni anular (D-30: la acción que no puede hacer no se muestra)."""
        x = self.armar()
        html = texto(self.ir("solicitud", x.solicitud.pk, usuario=self.e.vendedor))
        self.assertIn("La evalúa el Gerente.", html)
        for ausente in ("Ver resumen", "Evaluar la discrepancia", reverse("comercial:solicitud_resolver_revisar", args=[x.solicitud.pk]), "Anular resolución"):
            self.assertNotIn(ausente, html)
        self.resolver(x.solicitud)
        resuelta = texto(self.ir("solicitud", x.solicitud.pk, usuario=self.e.vendedor))
        self.assertNotIn(reverse("comercial:solicitud_anular", args=[x.solicitud.pk]), resuelta)
        self.assertIn("Cuenta como incumplimiento", resuelta)

    def test_una_queja_sin_clausula_pide_el_monto_con_su_tope_y_una_por_retraso_no(self):
        """Extensión 4a: la queja por estado de la mercadería trae el campo del monto con el tope; la de retraso muestra la indemnización de la cláusula y los días."""
        manual = texto(self.ir("solicitud", self.armar(tipo="queja").solicitud.pk))
        self.assertIn('name="monto"', manual)
        self.assertIn("Resolver la queja", manual)
        self.assertIn("$ 500,00", manual)
        retraso = self.armar(tipo="queja", queja_tipo="retraso", entregada=10, retraso=3)
        html = texto(self.ir("solicitud", retraso.solicitud.pk))
        self.assertNotIn('name="monto"', html)
        for esperado in ("Días de retraso", "$ 30,00", "Sale de la cláusula"):
            self.assertIn(esperado, html)

    def test_la_ficha_destaca_el_intento_de_entrega_dentro_del_plazo(self):
        """Extensión 4b: con un intento dentro del plazo, el criterio; sin intentos, el texto de que no hay."""
        x = self.armar(tipo="queja", queja_tipo="retraso", entregada=10, retraso=3)
        self.assertIn("No hay intentos de entrega fallidos registrados.", texto(self.ir("solicitud", x.solicitud.pk)))
        IntentoFallido.objects.create(entrega=x.entrega, transportista=transportista_con_vehiculo(self.e.invernadero), fecha_programada=x.detalle.fecha_primer_entrega, motivo="cliente_ausente")
        self.assertIn("Hubo un intento de entrega dentro del plazo", texto(self.ir("solicitud", x.solicitud.pk)))

    def test_una_resuelta_ofrece_anular_y_muestra_la_decision_y_las_dos_partes_del_monto(self):
        """Regla 5: la decisión, el Gerente, la fecha, las observaciones, lo descontado y lo reintegrado con su medio y, para el Gerente, «Anular resolución»."""
        x = self.armar(por_planta="200.00")
        self.resolver(x.solicitud, observaciones="Procede.", medio="efectivo")
        html = texto(self.ir("solicitud", x.solicitud.pk))
        for esperado in ("Cuenta como incumplimiento", "Procede.", "$ 600,00", "$ 500,00", "$ 100,00", "Efectivo", reverse("comercial:solicitud_anular", args=[x.solicitud.pk]), "Anular resolución"):
            self.assertIn(esperado, html)
        self.assertNotIn("Ver resumen", html)

    def test_el_historial_de_resoluciones_anuladas_se_ve_en_la_ficha(self):
        """D-69, punto 10: cada anulación con la resolución anulada, quién la anuló y el motivo, sin leer la auditoría."""
        from comercial.tests.fabricas import anulacion

        x = self.armar()
        self.resolver(x.solicitud)
        anulacion(x.solicitud, motivo="Error de carga.")
        html = texto(self.ir("solicitud", x.solicitud.pk))
        for esperado in ("Historial de resoluciones anuladas", "Error de carga.", "Aceptada · $ 15,00"):
            self.assertIn(esperado, html)

    @override_settings(CORREO_CONFIGURADO=True)
    def test_reenviar_aviso_o_imprimir_comprobante_segun_el_estado_del_aviso(self):
        """9a: con el aviso «pendiente de envío», «Reenviar aviso» (el Gerente y el Vendedor); con «sin correo», «Imprimir comprobante»."""
        x = self.armar()
        with self.captureOnCommitCallbacks(execute=False):
            self.resolver(x.solicitud)
        for usuario in (self.gerente, self.e.vendedor):
            html = texto(self.ir("solicitud", x.solicitud.pk, usuario=usuario))
            self.assertIn("Reenviar aviso", html)
            self.assertIn(reverse("comercial:solicitud_reenviar_aviso", args=[x.solicitud.pk]), html)
        SolicitudRevision.objects.filter(pk=x.solicitud.pk).update(estado_aviso_cliente="sin_correo")
        html = texto(self.ir("solicitud", x.solicitud.pk))
        self.assertIn("Imprimir comprobante", html)
        self.assertNotIn("Reenviar aviso", html)


class ResolverTests(BaseDeVistas):
    def revisar(self, x, **datos):
        datos.setdefault("decision", "aceptar")
        return self.enviar("solicitud_resolver_revisar", x.solicitud.pk, datos=datos)

    def huella(self, x, **datos):
        return solicitudes.resumen_de_resolucion(self.gerente, x.solicitud.pk, solicitudes.DatosDeResolucion(datos.get("decision", "aceptar"), datos.get("observaciones", ""), datos.get("monto", ""), datos.get("medio_reintegro", ""))).huella

    def test_ver_resumen_sin_javascript_vuelve_la_ficha_con_el_resumen_y_el_boton_de_confirmar(self):
        """Sin JavaScript «Ver resumen» es un POST que vuelve la misma página con el resumen: el descuento, el nuevo monto a cobrar, los incumplimientos y «Confirmar la decisión» con la huella; nada se escribe."""
        x = self.armar()
        respuesta = self.revisar(x)
        html = texto(respuesta)
        for esperado in ("Evaluar la discrepancia", "Resumen", "Discrepancia aceptada, con indemnización de $ 15,00.", "el monto a cobrar pasa de $ 500,00 a $ 485,00", "Incumplimientos del contrato", "Confirmar la decisión",
                         reverse("comercial:solicitud_resolver", args=[x.solicitud.pk]), 'name="huella"', "Fuera de esta ronda"):
            self.assertIn(esperado, html)
        self.assertEqual(SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, "pendiente")

    def test_ver_resumen_con_htmx_devuelve_solo_el_resumen(self):
        """Con HTMX solo se redibuja el resumen (sin la ficha entera)."""
        x = self.armar()
        self.client.force_login(self.gerente)
        parcial = texto(self.client.post(reverse("comercial:solicitud_resolver_revisar", args=[x.solicitud.pk]), {"decision": "aceptar"}, HTTP_HX_REQUEST="true"))
        self.assertIn("Confirmar la decisión", parcial)
        self.assertNotIn("Evaluar la discrepancia", parcial)
        self.assertNotIn("<html", parcial)

    def test_con_errores_el_resumen_no_trae_el_boton_de_confirmar(self):
        """Pasos bloqueados: sin decisión, o rechazando sin observaciones, o con un monto inválido, el resumen lista el error y no ofrece «Confirmar la decisión»."""
        x = self.armar()
        for datos, mensaje in (({"decision": ""}, "Elegí si aceptás o rechazás."), ({"decision": "rechazar"}, "Las observaciones son obligatorias al rechazar")):
            html = texto(self.revisar(x, **datos))
            self.assertIn(mensaje, html)
            self.assertNotIn("Confirmar la decisión", html)
        q = self.armar(tipo="queja")
        html = texto(self.revisar(q, monto="9999"))
        self.assertIn("El monto supera el tope.", html)
        self.assertIn("$ 500,00", html)
        self.assertNotIn("Confirmar la decisión", html)

    def test_confirmar_acepta_y_vuelve_a_la_ficha_con_el_aviso(self):
        """Paso 8: confirmar registra la resolución y vuelve a la ficha con el aviso (el monto, avisados el Vendedor y el cliente); el contrato suma el incumplimiento."""
        x = self.armar()
        respuesta = self.enviar("solicitud_resolver", x.solicitud.pk, datos={"decision": "aceptar", "huella": self.huella(x), "observaciones": "Procede."})
        self.assertRedirects(respuesta, reverse("comercial:solicitud", args=[x.solicitud.pk]), fetch_redirect_response=False)
        pagina = texto(self.client.get(respuesta["Location"]))
        self.assertIn("aceptada: indemnización de $ 15,00. Se avisó al Vendedor y al cliente.", pagina)
        s = SolicitudRevision.objects.get(pk=x.solicitud.pk)
        self.assertEqual((s.estado_solicitud, s.monto_descontado, s.observaciones_resolucion), ("aceptada", D("15.00"), "Procede."))

    def test_confirmar_rechazando_sin_observaciones_vuelve_al_panel_con_el_error(self):
        """Extensión 5b: el error vuelve al panel con lo cargado; la solicitud sigue pendiente."""
        x = self.armar()
        respuesta = self.enviar("solicitud_resolver", x.solicitud.pk, datos={"decision": "rechazar", "huella": self.huella(x, decision="rechazar", observaciones="x")})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Las observaciones son obligatorias al rechazar", texto(respuesta))
        self.assertEqual(SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, "pendiente")

    def test_el_medio_del_reintegro_se_elige_en_el_resumen_y_sin_el_no_se_confirma(self):
        """Extensión 6d: con reintegro el resumen trae el medio y el desplegable; confirmar sin medio vuelve con el error y confirmar con medio registra."""
        x = self.armar(por_planta="200.00")
        html = texto(self.revisar(x))
        for esperado in ("se le reintegran $ 100,00", 'name="medio_reintegro"', "Efectivo", "Transferencia", "Confirmar la decisión"):
            self.assertIn(esperado, html)
        huella = self.huella(x)
        sin_medio = self.enviar("solicitud_resolver", x.solicitud.pk, datos={"decision": "aceptar", "huella": huella})
        self.assertEqual(sin_medio.status_code, 200)
        self.assertIn("Elegí el medio del reintegro", texto(sin_medio))
        con_medio = self.enviar("solicitud_resolver", x.solicitud.pk, datos={"decision": "aceptar", "huella": huella, "medio_reintegro": "transferencia"})
        self.assertEqual(con_medio.status_code, 302)
        self.assertEqual(SolicitudRevision.objects.get(pk=x.solicitud.pk).medio_reintegro, "transferencia")

    def test_si_cambio_un_dato_vuelve_al_paso_4_con_lo_que_cambio(self):
        """Extensión 8b: cambió algo desde el resumen: no se registra, vuelve la ficha con un aviso que dice qué cambió y el panel con los datos nuevos."""
        x = self.armar()
        huella = self.huella(x)
        queja_aceptada(x.entrega, "otro", monto="50.00")
        respuesta = self.enviar("solicitud_resolver", x.solicitud.pk, datos={"decision": "aceptar", "huella": huella})
        html = texto(respuesta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Mientras mirabas la solicitud cambió", html)
        self.assertIn("el monto a cobrar de la entrega", html)
        self.assertIn("Ver resumen", html)
        self.assertEqual(SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, "pendiente")

    def test_si_ya_estaba_resuelta_vuelve_a_la_ficha_con_la_decision_tomada(self):
        """Extensión 8a: ya no está pendiente: vuelve a la ficha con la decisión, el Gerente y la fecha, sin registrar nada."""
        x = self.armar()
        huella = self.huella(x)
        self.resolver(x.solicitud)
        respuesta = self.enviar("solicitud_resolver", x.solicitud.pk, datos={"decision": "aceptar", "huella": huella})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("ya no está pendiente de revisión: fue aceptada", texto(self.client.get(respuesta["Location"])))


class AnularTests(BaseDeVistas):
    def test_la_pagina_de_anular_dice_que_va_a_pasar_y_pide_el_motivo(self):
        """Paso 2: el estado nuevo, el contador y el monto a cobrar antes y después, el contraasiento «Fuera de esta ronda» y el motivo; el texto explicativo."""
        x = self.armar()
        self.resolver(x.solicitud)
        html = texto(self.ir("solicitud_anular", x.solicitud.pk))
        for esperado in ("La solicitud vuelve a pendiente para resolverla de nuevo", "1 → 0", "$ 485,00 → $ 500,00", "Fuera de esta ronda", 'name="motivo"', 'name="huella"', "Anular resolución"):
            self.assertIn(esperado, html)

    def test_con_un_bloqueo_solo_el_mensaje_y_volver(self):
        """Extensiones 2a a 2c: «No se puede anular» con el motivo y «Volver»; sin formulario ni botón de anular."""
        x = self.armar(por_planta="200.00")
        self.resolver(x.solicitud, medio="efectivo")
        html = texto(self.ir("solicitud_anular", x.solicitud.pk))
        self.assertIn("No se puede anular.", html)
        self.assertIn("ya se le reintegró al cliente", html)
        self.assertNotIn('name="motivo"', html)
        self.assertIn("Volver", html)

    def test_anular_vuelve_a_la_ficha_pendiente_y_se_puede_volver_a_resolver(self):
        """Pasos 5 a 7: confirma con el motivo, vuelve a la ficha con «volvió a pendiente» y el panel para volver a resolver; el historial muestra la anulación."""
        x = self.armar()
        self.resolver(x.solicitud)
        datos = solicitudes.datos_de_anulacion(self.gerente, x.solicitud.pk)
        respuesta = self.enviar("solicitud_anular", x.solicitud.pk, datos={"motivo": "Me equivoqué.", "huella": datos.huella})
        self.assertRedirects(respuesta, reverse("comercial:solicitud", args=[x.solicitud.pk]), fetch_redirect_response=False)
        pagina = texto(self.client.get(respuesta["Location"]))
        for esperado in ("volvió a pendiente de revisión. Ya podés volver a resolverla.", "Evaluar la discrepancia", "Ver resumen", "Me equivoqué."):
            self.assertIn(esperado, pagina)

    def test_anular_sin_motivo_vuelve_con_el_error(self):
        """Extensión 3a: el motivo vacío se pide debajo del campo y no se anula."""
        x = self.armar()
        self.resolver(x.solicitud)
        datos = solicitudes.datos_de_anulacion(self.gerente, x.solicitud.pk)
        respuesta = self.enviar("solicitud_anular", x.solicitud.pk, datos={"motivo": "  ", "huella": datos.huella})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("el motivo es obligatorio", texto(respuesta))
        self.assertEqual(SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_solicitud, "aceptada")

    def test_una_pendiente_no_se_anula_y_vuelve_a_la_ficha(self):
        """Una solicitud pendiente no tiene resolución: vuelve a la ficha con el mensaje."""
        x = self.armar()
        respuesta = self.ir("solicitud_anular", x.solicitud.pk)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("no hay una resolución para anular", texto(self.client.get(respuesta["Location"])))


class ComprobanteYAvisoTests(BaseDeVistas):
    def test_el_comprobante_imprimible_dice_el_total_el_descuento_y_que_no_tiene_validez_fiscal(self):
        """9a: la página para imprimir (el cliente sin correo): la entrega, las líneas, el total, lo descontado y lo reintegrado; «Comprobante interno, sin validez fiscal.»."""
        x = self.armar(por_planta="200.00")
        self.resolver(x.solicitud, medio="efectivo")
        for usuario in (self.gerente, self.e.vendedor):
            html = texto(self.ir("solicitud_comprobante", x.solicitud.pk, usuario=usuario))
            for esperado in ("Comprobante de indemnización", x.entrega.codigo, "$ 600,00", "$ 500,00", "$ 100,00", "efectivo", "Comprobante interno, sin validez fiscal.", "Imprimir comprobante"):
                self.assertIn(esperado, html)

    def test_el_comprobante_de_una_pendiente_es_404_y_el_de_un_contrato_ajeno_403(self):
        """Solo de una solicitud resuelta del alcance del actor."""
        from maestros.tests.fabricas import crear_vendedor

        x = self.armar()
        self.assertEqual(self.ir("solicitud_comprobante", x.solicitud.pk).status_code, 404)
        self.resolver(x.solicitud)
        self.assertEqual(self.ir("solicitud_comprobante", x.solicitud.pk, usuario=crear_vendedor(email="otro@infoponia.com")).status_code, 403)

    @override_settings(CORREO_CONFIGURADO=True)
    def test_reenviar_aviso_manda_el_correo_y_vuelve_a_la_ficha(self):
        """9a: «Reenviar aviso» (un POST) manda el comprobante y vuelve a la ficha con el resultado; sin aviso pendiente, el mensaje."""
        from django.core import mail

        x = self.armar()
        with self.captureOnCommitCallbacks(execute=False):
            self.resolver(x.solicitud)
        respuesta = self.enviar("solicitud_reenviar_aviso", x.solicitud.pk, usuario=self.e.vendedor)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual((len(mail.outbox), SolicitudRevision.objects.get(pk=x.solicitud.pk).estado_aviso_cliente), (1, "enviado"))
        self.assertIn("Se envió el aviso al cliente.", texto(self.client.get(respuesta["Location"])))
        repetido = self.enviar("solicitud_reenviar_aviso", x.solicitud.pk)
        self.assertIn("no está pendiente de envío", texto(self.client.get(repetido["Location"])))


class LoQueCompletaAOtrasTareasTests(BaseDeVistas):
    def test_el_enlace_de_las_alertas_de_discrepancia_y_de_queja_lleva_al_gerente_a_la_ficha_de_la_solicitud(self):
        """«El enlace de las alertas» (docs/api/alertas.md, sección 8): las dos alertas llevan al Gerente a la ficha de la solicitud, con «SR-0012 · Discrepancia · pendiente»; a cualquier otro rol, nada; y el registrante es uno solo."""
        d, q = self.armar(), self.armar(tipo="queja")
        alertas = list(Alerta.objects.select_related("invernadero").order_by("pk"))
        directo = solicitudes.enlaces_de_alertas(self.gerente, alertas)
        for x, tipo in ((d, "Discrepancia"), (q, "Queja")):
            alerta = Alerta.objects.get(vinculo_comercial__solicitud=x.solicitud.pk)
            self.assertEqual(directo[alerta.pk].url, reverse("comercial:solicitud", args=[x.solicitud.pk]))
            self.assertEqual(directo[alerta.pk].detalle, f"{x.solicitud.codigo} · {tipo} · pendiente")
        self.assertEqual(solicitudes.enlaces_de_alertas(self.e.vendedor, alertas), {})
        self.assertEqual(solicitudes.enlaces_de_alertas(self.gerente, []), {})
        registrados = [funcion for codigos, funcion in extensiones_de_maestros.enlaces_registrados() if {"comercial_discrepancia_entrega", "comercial_queja"} & set(codigos)]
        self.assertEqual(registrados, [solicitudes.enlaces_de_alertas])

    def test_el_enlace_ya_resuelto_dice_la_decision(self):
        """El detalle del enlace sigue a la solicitud: «SR-… · Discrepancia · aceptada» una vez resuelta."""
        x = self.armar()
        alerta = Alerta.objects.get(vinculo_comercial__solicitud=x.solicitud.pk)
        self.resolver(x.solicitud)
        self.assertEqual(solicitudes.enlaces_de_alertas(self.gerente, [alerta])[alerta.pk].detalle, f"{x.solicitud.codigo} · Discrepancia · aceptada")

    def test_el_grupo_solicitudes_del_panel_es_solo_del_gerente_y_lleva_a_la_lista_filtrada(self):
        """Panel de control: dentro de la sección «Comercial» (la de entregas), el indicador «Pendientes» del Gerente, con el enlace a la pestaña filtrada por pendientes; el Vendedor no lo ve (regla 4 de COM-CNS-SRV)."""
        self.armar(), self.armar(tipo="queja")
        hoy = registrantes.seccion_de_entregas(self.gerente).contexto["entregas"]
        self.assertEqual(hoy["solicitudes_pendientes"], 2)
        self.assertEqual(hoy["url_de_solicitudes_pendientes"], reverse("comercial:solicitudes") + "?estado=pendiente")
        self.assertIsNone(registrantes.seccion_de_entregas(self.e.vendedor).contexto["entregas"]["solicitudes_pendientes"])
        self.client.force_login(self.gerente)
        pagina = texto(self.client.get(reverse("core:inicio")))
        self.assertIn("Solicitudes de revisión", pagina)
        self.assertIn(reverse("comercial:solicitudes") + "?estado=pendiente", pagina)
        self.client.force_login(self.e.vendedor)
        self.assertNotIn("quejas y discrepancias a resolver", texto(self.client.get(reverse("core:inicio"))))

    def test_la_ficha_del_suministro_trae_la_seccion_solicitudes_de_revision(self):
        """Lo que completa a COM-03a (regla 8 de COM-CNS-SUM): número, fecha y entrega, tipo, estado y «Cuenta como incumplimiento», de la más reciente a la más antigua, con «Ver»."""
        x = self.armar()
        y = self.otra(x, tipo="queja")
        self.resolver(x.solicitud)
        html = texto(self.ir("suministro", x.contrato.pk))
        for esperado in ("Solicitudes de revisión", x.solicitud.codigo, y.solicitud.codigo, "Cuenta como incumplimiento", reverse("comercial:solicitud", args=[x.solicitud.pk]), reverse("comercial:solicitud", args=[y.solicitud.pk])):
            self.assertIn(esperado, html)
        self.assertLess(html.index(y.solicitud.codigo), html.index(x.solicitud.codigo))
