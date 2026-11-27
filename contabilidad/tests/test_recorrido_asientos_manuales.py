# Recorrido de CON-03b (D-96, `docs/patrones/verificacion_a_mano.md`): pruebas largas con el cliente de Django que hacen de punta a punta lo que hará la persona en la «Verificación a mano»,
# por rol y por estado del ejercicio. Modelo: `test_recorrido_libro_y_cierre.py`. Las reglas sueltas están en `test_con_reg_asi.py`, `test_con_ctr_asi.py` y `test_asientos_vistas.py`; acá se
# verifica que el flujo ENCADENA. «Hoy» se fija (`timezone.localdate`): nada lee la hora sola.
# Contador: formulario → atajo de apertura → resumen → asiento N.º 1 → los rechazos (desbalanceado, descripción, cuenta, fecha futura, fecha en ejercicio cerrado) → asientos en el ejercicio en cierre →
# contraasiento con aviso al Gerente y oferta del asiento correcto → contraasiento en el ejercicio en cierre → cierre del ejercicio → rechazos con el ejercicio cerrado → contraasiento de un asiento de un
# ejercicio cerrado → asiento ya anulado. Gerente sin Contador activo: opera y no se avisa a sí mismo; con un Contador activo vuelve a ser de solo lectura. Otros roles: sin acceso.
import datetime
import html
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from contabilidad import cuentas
from contabilidad.models import AsientoContable, CuentaContable, EjercicioContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio, verificar_invariantes_contables
from core.models import Agronomo, Contador, Gerente, Notificacion, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
Accion = RegistroAuditoria.Accion
HOY = datetime.date(2027, 3, 10)
LIBRO = reverse("contabilidad:libro")
NUEVO = reverse("contabilidad:asiento_nuevo")


def _texto(respuesta):
    return html.unescape(respuesta.content.decode())


def _etiqueta(codigo):
    cuenta = CuentaContable.objects.get(codigo_cuenta=codigo)
    return f"{cuenta.codigo_cuenta} · {cuenta.nombre_cuenta}"


def _form(descripcion, fecha, filas, **extra):
    """Lo que envía el formulario del asiento: `filas` es `[(codigo_de_cuenta | texto, "D"|"H", importe_escrito)]`."""
    datos = {"fecha": fecha, "descripcion": descripcion, "fila": [str(i) for i in range(len(filas))]}
    for i, (cuenta, tipo, importe) in enumerate(filas):
        datos.update({f"cuenta_{i}": _etiqueta(cuenta) if cuenta in {c.codigo_cuenta for c in CuentaContable.objects.all()} else cuenta, f"tipo_{i}": tipo, f"importe_{i}": importe})
    datos.update(extra)
    return datos


class RecorridoDeAsientosManualesTests(PlanDeCuentasMixin, TestCase):
    """Recorrido por rol (Contador, Gerente con y sin Contador activo, Vendedor, Agrónomo, anónimo) y por estado del ejercicio (abierto, en cierre, cerrado) y del asiento (activo, anulado)."""

    def setUp(self):
        mock.patch("django.utils.timezone.localdate", return_value=HOY).start()
        self.addCleanup(mock.patch.stopall)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com", nombre="Cora", apellido="Díaz")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com", nombre="Gabriela", apellido="Sosa")
        self.vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        self.agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")
        self.en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))  # hasta el 31/12/2026
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))

    def ir(self, usuario, url, **parametros):
        self.client.force_login(usuario)
        return self.client.get(url, parametros)

    def enviar(self, usuario, url, datos, **extra):
        self.client.force_login(usuario)
        return self.client.post(url, datos, **extra)

    def ficha(self, asiento):
        return reverse("contabilidad:asiento", args=[asiento.ejercicio_id, asiento.numero_asiento])

    def contraasentar_url(self, asiento):
        return reverse("contabilidad:contraasiento", args=[asiento.ejercicio_id, asiento.numero_asiento])

    def registrar(self, usuario, descripcion, fecha, filas):
        """Registra por la pantalla (revisar y confirmar) y devuelve el asiento nuevo."""
        antes = set(AsientoContable.objects.values_list("pk", flat=True))
        self.enviar(usuario, NUEVO, _form(descripcion, fecha, filas, accion="revisar"))
        self.enviar(usuario, NUEVO, _form(descripcion, fecha, filas, accion="confirmar"))
        return AsientoContable.objects.exclude(pk__in=antes).get()

    def test_recorrido_del_contador_del_formulario_al_contraasiento_y_el_cierre(self):
        gasto = [(cuentas.GASTOS_GENERALES, "D", "100,00"), (cuentas.CAJA, "H", "100,00")]

        # 1. CON-REG-ASI precondición a y D-30: el Contador ve «Registrar asiento» en el libro; el Gerente con Contador activo no, y lo lee «Lo registra el Contador»; el Vendedor no entra.
        self.assertIn(f'href="{NUEVO}"', _texto(self.ir(self.contador, LIBRO)))
        del_gerente = _texto(self.ir(self.gerente, LIBRO))
        self.assertNotIn(f'href="{NUEVO}"', del_gerente)
        self.assertIn("Lo registra el Contador", del_gerente)
        self.assertEqual(self.ir(self.vendedor, LIBRO).status_code, 403)

        # 2. CON-REG-ASI pasos 2 y 3: el formulario trae hoy, dos filas, el buscador de cuenta y los atajos.
        formulario = _texto(self.ir(self.contador, NUEVO))
        self.assertIn('value="2027-03-10"', formulario)
        self.assertIn('<option value="1.1.01 · Caja">', formulario)

        # 3. Extensión 3a quitada (CON-05): la pantalla ya no ofrece el atajo «Asiento de apertura» (la apertura es CON-INI-EJE) y escribir la acción a mano no precarga nada ni registra;
        #    el atajo de venta previa (3b) sigue.
        self.assertNotIn("atajo:apertura", formulario)
        self.assertIn("atajo:venta_previa", formulario)
        atajo = _texto(self.enviar(self.contador, NUEVO, _form("", "2027-03-10", [("", "D", ""), ("", "H", "")], accion="atajo:apertura")))
        self.assertNotIn('value="Asiento de apertura"', atajo)
        self.assertFalse(AsientoContable.objects.exists())

        # 4. Pasos 4 a 8: agrega una fila (Banco), revisa (resumen, sin registrar) y confirma; el asiento N.º 1 queda en el ejercicio abierto (el 2) y la ficha dice quién lo registró.
        apertura = [(cuentas.CAJA, "D", "1.500,00"), (cuentas.BANCO, "D", "500,00"), (cuentas.CAPITAL_INICIAL, "H", "2.000,00")]
        mas_filas = _texto(self.enviar(self.contador, NUEVO, _form("Asiento de apertura", "2027-03-10", apertura[:2], accion="agregar")))
        self.assertIn('name="cuenta_2"', mas_filas)
        resumen = _texto(self.enviar(self.contador, NUEVO, _form("Asiento de apertura", "2027-03-10", apertura, accion="revisar")))
        self.assertIn("Revisá el asiento", resumen)
        self.assertIn("$ 2.000,00", resumen)
        self.assertIn("Balanceado", resumen)
        self.assertFalse(AsientoContable.objects.exists())
        confirmada = self.enviar(self.contador, NUEVO, _form("Asiento de apertura", "2027-03-10", apertura, accion="confirmar"), follow=True)
        apertura_asiento = AsientoContable.objects.get()
        self.assertRedirects(confirmada, self.ficha(apertura_asiento))
        self.assertIn("Asiento N.º 1 registrado en el ejercicio 2.", [str(m) for m in confirmada.context["messages"]])
        ficha = _texto(confirmada)
        self.assertIn("Cora Díaz", ficha)
        self.assertIn("Manual", ficha)
        self.assertIn(f'href="{self.contraasentar_url(apertura_asiento)}"', ficha)  # un asiento activo se puede contraasentar

        # 5. El libro lo muestra y la vista por cuenta suma el saldo de Caja.
        self.assertIn("Asiento de apertura", _texto(self.ir(self.contador, LIBRO)))
        self.assertIn("$ 1.500,00", _texto(self.ir(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.CAJA)))

        # 6. Extensiones 5a, 5b, 5c, 5e y 7a: cada rechazo vuelve al formulario con su mensaje junto al campo, conserva lo escrito y no registra nada.
        rechazos = [
            (_form("", "2027-03-10", gasto, accion="confirmar"), "La descripción es obligatoria"),
            (_form("Gasto", "2027-03-10", [(cuentas.GASTOS_GENERALES, "D", "100,00"), (cuentas.CAJA, "H", "90,00")], accion="confirmar"), "no coinciden"),
            (_form("Gasto", "2027-03-10", [(cuentas.GASTOS_GENERALES, "D", "100,00"), (cuentas.CAJA, "H", "-100,00")], accion="confirmar"), "mayor que cero"),
            (_form("Gasto", "2027-03-10", [(cuentas.GASTOS_GENERALES, "D", "100,00"), ("9.9.99", "H", "100,00")], accion="confirmar"), "no existe en el plan de cuentas"),
            (_form("Gasto", "2027-03-11", gasto, accion="confirmar"), "posterior a hoy"),
            (_form("Gasto", "2024-06-01", gasto, accion="confirmar"), "anterior al primer ejercicio"),
            (_form("Gasto", "", gasto, accion="confirmar"), "Indicá una fecha válida"),
        ]
        for datos, texto in rechazos:
            with self.subTest(texto=texto):
                respuesta = self.enviar(self.contador, NUEVO, datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn(texto, _texto(respuesta))
                self.assertIn('name="cuenta_0"', _texto(respuesta))
        self.assertEqual(AsientoContable.objects.count(), 1)

        # 7. Extensión 5d y H1: con fecha en el ejercicio en cierre, el resumen lo indica y el asiento entra en ese ejercicio con su propia numeración.
        self.assertIn("Va a un ejercicio en cierre", _texto(self.enviar(self.contador, NUEVO, _form("Gasto A", "2026-12-01", gasto, accion="revisar"))))
        asiento_a = self.registrar(self.contador, "Gasto A", "2026-12-01", gasto)
        asiento_b = self.registrar(self.contador, "Gasto B", "2026-12-02", gasto)
        self.assertEqual((asiento_a.ejercicio_id, asiento_a.numero_asiento, asiento_b.numero_asiento), (self.en_cierre.pk, 1, 2))

        # 8. CON-CTR-ASI pasos 1 a 3: solo el Contador abre el contraasiento (el Gerente con Contador, el Vendedor y el Agrónomo reciben 403); el formulario trae el asiento, los movimientos invertidos y hoy.
        url = self.contraasentar_url(apertura_asiento)
        for usuario in (self.gerente, self.vendedor, self.agronomo):
            self.assertEqual(self.ir(usuario, url).status_code, 403)
        formulario = _texto(self.ir(self.contador, url))
        self.assertIn("Contraasentar el asiento N.º 1", formulario)
        self.assertIn('value="2027-03-10"', formulario)

        # 9. Extensión 3a, pasos 4 y 5: sin motivo no avanza; con motivo, el resumen muestra los movimientos invertidos sin registrar.
        self.assertIn("El motivo es obligatorio", _texto(self.enviar(self.contador, url, {"fecha": "2027-03-01", "motivo": "", "accion": "revisar"})))
        resumen = _texto(self.enviar(self.contador, url, {"fecha": "2027-03-01", "motivo": "Se cargó el Banco de más", "accion": "revisar"}))
        self.assertIn("quedará marcado como anulado", resumen)
        self.assertEqual(AsientoContable.objects.filter(anula__isnull=False).count(), 0)

        # 10. Pasos 6 a 8 y postcondición d: confirma; queda el contraasiento N.º 2 (con fecha 1/3), el original anulado, el Gerente avisado y la ficha ofrece registrar el asiento correcto.
        confirmado = self.enviar(self.contador, url, {"fecha": "2027-03-01", "motivo": "Se cargó el Banco de más", "accion": "confirmar"}, follow=True)
        contraasiento = AsientoContable.objects.get(anula=apertura_asiento)
        self.assertRedirects(confirmado, self.ficha(contraasiento) + "?corregir=1")
        self.assertEqual((contraasiento.numero_asiento, contraasiento.fecha_asiento, contraasiento.ejercicio_id), (2, datetime.date(2027, 3, 1), self.abierto.pk))
        ficha = _texto(confirmado)
        self.assertIn("Contraasiento", ficha)
        self.assertIn("¿Registrás ahora el asiento correcto?", ficha)
        aviso = Notificacion.objects.get()
        self.assertEqual((aviso.destinatario_id, aviso.titulo), (self.gerente.pk, "Contraasiento N.º 2 del asiento N.º 1"))
        self.assertIn("Lo registró Cora Díaz el 01/03/2027. Motivo: Se cargó el Banco de más", aviso.detalle)

        # 11. El original aparece anulado y sin «Contraasentar»; el libro lo filtra por «Solo anulados»; el contraasiento tampoco se puede contraasentar.
        anulado = _texto(self.ir(self.contador, self.ficha(apertura_asiento)))
        self.assertIn("Anulado.", anulado)
        self.assertNotIn(url, anulado)
        self.assertNotIn(self.contraasentar_url(contraasiento), _texto(self.ir(self.contador, self.ficha(contraasiento))))
        solo_anulados = _texto(self.ir(self.contador, LIBRO, anulados="si"))
        self.assertIn("Asiento de apertura", solo_anulados)
        self.assertNotIn("Se cargó el Banco de más", solo_anulados)

        # 12. CON-REG-ASI extensión 1b (C4): el enlace de la oferta precarga las líneas del asiento ANULADO; el asiento correcto se registra como un manual común, sin vínculo.
        precarga = _texto(self.ir(self.contador, NUEVO, corrige=contraasiento.pk))
        self.assertIn('value="corrección del asiento N.º 1"', precarga)
        self.assertIn('value="1500,00"', precarga)
        correcto = self.registrar(self.contador, "Asiento de apertura (corrección del asiento N.º 1)", "2027-03-10", [(cuentas.CAJA, "D", "1.500,00"), (cuentas.CAPITAL_INICIAL, "H", "1.500,00")])
        self.assertEqual((correcto.numero_asiento, correcto.tipo), (3, AsientoContable.Tipo.MANUAL))
        self.assertIsNone(correcto.anula_id)

        # 13. CON-CTR-ASI extensión 3b (C3): un asiento del abierto se contraasienta con fecha en el ejercicio en cierre; el resumen lo indica y el contraasiento toma el N.º 3 de ese ejercicio.
        url_a = self.contraasentar_url(asiento_a)
        datos = {"fecha": "2026-12-15", "motivo": "Gasto duplicado"}
        self.assertIn("Va a un ejercicio en cierre", _texto(self.enviar(self.contador, url_a, {**datos, "accion": "revisar"})))
        self.enviar(self.contador, url_a, {**datos, "accion": "confirmar"})
        contra_a = AsientoContable.objects.get(anula=asiento_a)
        self.assertEqual((contra_a.ejercicio_id, contra_a.numero_asiento), (self.en_cierre.pk, 3))

        # 14. Extensión 3c: fechas en el futuro o anteriores al primer ejercicio se rechazan junto al campo.
        url_b = self.contraasentar_url(asiento_b)
        for fecha, texto in (("2027-03-11", "posterior a hoy"), ("2024-06-01", "anterior al primer ejercicio")):
            self.assertIn(texto, _texto(self.enviar(self.contador, url_b, {"fecha": fecha, "motivo": "Gasto duplicado", "accion": "confirmar"})))
        self.assertIsNone(getattr(AsientoContable.objects.get(pk=asiento_b.pk), "contraasiento", None))

        # 15. CON-CRR-EJE (CON-03a): se cierra el ejercicio en cierre desde su pantalla.
        cierre = reverse("contabilidad:cierre", args=[self.en_cierre.pk])
        self.enviar(self.contador, cierre, {"confirmo": "1"})
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, Estado.CERRADO)

        # 16. Extensiones 5e y 3c con el ejercicio cerrado: ya no recibe asientos manuales ni contraasientos.
        self.assertIn("está cerrado y ya no recibe asientos", _texto(self.enviar(self.contador, NUEVO, _form("Gasto C", "2026-12-20", gasto, accion="confirmar"))))
        self.assertIn("está cerrado y ya no recibe asientos", _texto(self.enviar(self.contador, url_b, {"fecha": "2026-12-20", "motivo": "Gasto duplicado", "accion": "confirmar"})))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).ultimo_numero_asiento, 3)

        # 17. Regla «Qué se anula»: un asiento de un ejercicio cerrado SÍ se contraasienta (la fecha va a un ejercicio abierto); la ficha todavía ofrece «Contraasentar».
        self.assertIn(f'href="{url_b}"', _texto(self.ir(self.contador, self.ficha(asiento_b))))
        self.assertIn("podés contraasentarlo con una fecha de un ejercicio abierto o en cierre", _texto(self.ir(self.contador, self.ficha(asiento_b))))
        self.enviar(self.contador, url_b, {"fecha": "2027-03-10", "motivo": "Gasto duplicado", "accion": "confirmar"})
        contra_b = AsientoContable.objects.get(anula=asiento_b)
        self.assertEqual((contra_b.ejercicio_id, contra_b.numero_asiento), (self.abierto.pk, 4))
        self.assertEqual(Notificacion.objects.count(), 3)  # uno por cada contraasiento (N.º 1, A y B)

        # 18. Extensión 1b: un asiento ya anulado muestra su contraasiento y un envío manual no lo anula otra vez.
        pantalla = _texto(self.ir(self.contador, url_a))
        self.assertIn("Ya está anulado por el", pantalla)
        self.assertIn(f'href="{self.ficha(contra_a)}"', pantalla)
        self.enviar(self.contador, url_a, {"fecha": "2027-03-10", "motivo": "Otra vez", "accion": "confirmar"})
        self.assertEqual(AsientoContable.objects.filter(anula=asiento_a).count(), 1)

        # 19. Auditoría (postcondiciones d y e): cada asiento y cada movimiento tiene su registro, con el Contador como autor.
        asientos_creados = AsientoContable.objects.count()  # 1 apertura, A, B, 3 contraasientos, 1 correcto
        self.assertEqual(asientos_creados, 7)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=Accion.ALTA_ASIENTO_CONTABLE).count(), asientos_creados)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=Accion.ALTA_MOVIMIENTO_CONTABLE).count(), sum(a.movimientos.count() for a in AsientoContable.objects.all()))
        self.assertEqual(set(RegistroAuditoria.objects.filter(accion=Accion.ALTA_ASIENTO_CONTABLE).values_list("usuario_id", flat=True)), {self.contador.pk})
        verificar_invariantes_contables()

    def test_recorrido_del_gerente_sin_contador_activo_opera_y_con_contador_es_de_solo_lectura(self):
        gasto = [(cuentas.GASTOS_GENERALES, "D", "100,00"), (cuentas.CAJA, "H", "100,00")]
        Contador.objects.update(is_active=False)

        # 1. D-85 punto 4: sin Contador activo el Gerente ve «Registrar asiento» y el formulario.
        self.assertIn(f'href="{NUEVO}"', _texto(self.ir(self.gerente, LIBRO)))
        self.assertIn("Revisar asiento", _texto(self.ir(self.gerente, NUEVO)))

        # 2. Extensión 1a: registra el asiento y queda como autor, con rol Gerente.
        asiento = self.registrar(self.gerente, "Gasto del Gerente", "2027-03-10", gasto)
        registro = RegistroAuditoria.objects.get(accion=Accion.ALTA_ASIENTO_CONTABLE, afectados__contains=[{"id": asiento.pk}])
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        self.assertIn("Gabriela Sosa", _texto(self.ir(self.gerente, self.ficha(asiento))))

        # 3. CON-CTR-ASI extensión 1a, punto 3: contraasienta y NO se avisa a sí mismo (H21).
        self.enviar(self.gerente, self.contraasentar_url(asiento), {"fecha": "2027-03-10", "motivo": "Error de carga", "accion": "confirmar"})
        self.assertEqual(AsientoContable.objects.filter(anula=asiento).count(), 1)
        self.assertFalse(Notificacion.objects.exists())

        # 4. Llega un Contador activo: el Gerente vuelve a ser de solo lectura, sin acciones y con «Lo registra el Contador»; sus envíos son 403 y no escriben nada.
        nuevo_contador = crear_cuenta(Contador, email="contador.nuevo@infoponia.com")
        libro = _texto(self.ir(self.gerente, LIBRO))
        self.assertNotIn(f'href="{NUEVO}"', libro)
        self.assertIn("Lo registra el Contador", libro)
        self.assertIn("Lo registra el Contador", _texto(self.ir(self.gerente, NUEVO)))
        self.assertEqual(self.enviar(self.gerente, NUEVO, _form("Otro gasto", "2027-03-10", gasto, accion="confirmar")).status_code, 403)
        otro = self.registrar(nuevo_contador, "Gasto del Contador", "2027-03-10", gasto)
        self.assertEqual(self.ir(self.gerente, self.contraasentar_url(otro)).status_code, 403)
        self.assertEqual(self.enviar(self.gerente, self.contraasentar_url(otro), {"fecha": "2027-03-10", "motivo": "x", "accion": "confirmar"}).status_code, 403)
        self.assertNotIn(self.contraasentar_url(otro), _texto(self.ir(self.gerente, self.ficha(otro))))
        self.assertEqual(AsientoContable.objects.filter(anula=otro).count(), 0)
        verificar_invariantes_contables()

    def test_recorrido_de_los_roles_sin_acceso_y_de_quien_no_inicio_sesion(self):
        # 1. X3 y D-85 punto 8: el Vendedor y el Agrónomo no entran al formulario ni al contraasiento (403, en GET y en POST), y no se escribe nada.
        base = AsientoContable.objects.count()
        asiento = self.registrar(self.contador, "Gasto", "2027-03-10", [(cuentas.GASTOS_GENERALES, "D", "100,00"), (cuentas.CAJA, "H", "100,00")])
        for usuario in (self.vendedor, self.agronomo):
            self.assertEqual(self.ir(usuario, NUEVO).status_code, 403)
            self.assertEqual(self.enviar(usuario, NUEVO, _form("Gasto", "2027-03-10", [(cuentas.CAJA, "D", "1,00"), (cuentas.VENTAS, "H", "1,00")], accion="confirmar")).status_code, 403)
            self.assertEqual(self.ir(usuario, self.contraasentar_url(asiento)).status_code, 403)
            self.assertEqual(self.enviar(usuario, self.contraasentar_url(asiento), {"fecha": "2027-03-10", "motivo": "x", "accion": "confirmar"}).status_code, 403)
        self.assertEqual(AsientoContable.objects.count(), base + 1)

        # 2. Sin sesión se pide iniciar sesión (no se ve nada).
        self.client.logout()
        for url in (NUEVO, self.contraasentar_url(asiento)):
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertIn("/iniciar-sesion/", self.client.get(url)["Location"])

        # 3. Un asiento inexistente es 404 para el Contador.
        self.assertEqual(self.ir(self.contador, reverse("contabilidad:contraasiento", args=[self.abierto.pk, 99])).status_code, 404)
