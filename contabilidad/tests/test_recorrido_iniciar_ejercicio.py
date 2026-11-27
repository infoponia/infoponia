# Recorrido de CON-05 (D-96, `docs/patrones/verificacion_a_mano.md`): CON-INI-EJE «Iniciar Ejercicio Contable» de punta a punta con el cliente de Django, como lo haría una persona, por rol y
# por estado. Una prueba larga a propósito: lo que se verifica es que el flujo ENCADENA bien. Sin ejercicio, la campana avisa al Contador; una operación con asiento muestra la ventana (con HTMX
# y sin él); el Contador inicia desde la alerta (formulario, errores, resumen, confirmación) y el libro muestra el asiento N.º 1 «Asiento de apertura» con la fecha de inicio; la alerta
# desaparece y la operación pendiente se puede registrar. Una segunda prueba arma el estado «el Gerente inicia porque no hay Contador activo» y una tercera, los roles sin acceso. Las reglas
# sueltas las prueban `test_con_ini_eje.py` y `test_contabilidad_no_iniciada.py`. Lo que solo ve un navegador (CSRF, `Origin`, JavaScript y la otra pestaña) va en la «Verificación a mano».
import datetime
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from contabilidad import cuentas
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin, verificar_invariantes_contables
from core.models import Agronomo, Contador, Gerente, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

HOY = datetime.date(2027, 3, 10)
HTMX = {"HTTP_HX_REQUEST": "true"}
INICIAR = reverse("contabilidad:iniciar")
NUEVO = reverse("contabilidad:asiento_nuevo")
LIBRO = reverse("contabilidad:libro")
EJERCICIOS = reverse("contabilidad:ejercicios")
CAMPANA = reverse("core:campana")
AVISO = "Falta iniciar la contabilidad"
VENTANA = "La operación no se registró."


def _apertura(**cambios):
    base = {
        "fecha_inicio": "2027-01-01",
        "importe_1.1.01": "1.000,00",
        "importe_1.1.03": "500,00",
        "importe_3.1.01": "1.200,00",
        "importe_2.1.01": "300,00",
    }
    base.update(cambios)
    return base


def _asiento_manual(accion="confirmar"):
    """El asiento manual que el Contador estaba por registrar cuando se encontró con la ventana: Gastos Generales contra Caja, 50,00."""
    return {
        "accion": accion,
        "fecha": "2027-03-10",
        "descripcion": "Pago de la luz",
        "fila": ["0", "1"],
        "cuenta_0": cuentas.GASTOS_GENERALES, "tipo_0": "D", "importe_0": "50,00",
        "cuenta_1": cuentas.CAJA, "tipo_1": "H", "importe_1": "50,00",
    }


class RecorridoDeIniciarEjercicioTests(PlanDeCuentasMixin, TestCase):
    """CON-INI-EJE de punta a punta: sin ejercicio → alerta → ventana → iniciar → libro → alerta que desaparece → la operación pendiente se registra."""

    def setUp(self):
        cache.clear()
        mock.patch("django.utils.timezone.localdate", return_value=HOY).start()
        self.addCleanup(mock.patch.stopall)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com", nombre="Cora", apellido="Díaz")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com")
        self.vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")

    def como(self, cuenta):
        self.client.force_login(cuenta)

    def test_recorrido_del_contador_de_la_alerta_a_la_operacion_pendiente(self):
        # 1. Regla 10: sin ejercicio, la campana del Contador muestra «Falta iniciar la contabilidad» con el acceso a la pantalla; la del Gerente (hay Contador) y la del Vendedor, no.
        self.como(self.contador)
        campana = self.client.get(CAMPANA, **HTMX)
        self.assertContains(campana, AVISO)
        self.assertContains(campana, f'href="{INICIAR}"')
        for otro in (self.gerente, self.vendedor):
            self.como(otro)
            self.assertNotContains(self.client.get(CAMPANA, **HTMX), AVISO)

        # 2. Pantallas: el libro y «Ejercicios» vacíos ofrecen «Iniciar ejercicio» y el libro no ofrece «Registrar asiento»; «Registrar asiento» abierto a mano explica y ofrece iniciar.
        self.como(self.contador)
        libro = self.client.get(LIBRO)
        self.assertContains(libro, "Todavía no hay ejercicios contables")
        self.assertContains(libro, f'href="{INICIAR}"')
        self.assertNotContains(libro, "Registrar asiento")
        self.assertContains(self.client.get(EJERCICIOS), f'href="{INICIAR}"')
        explicacion = self.client.get(NUEVO)
        self.assertContains(explicacion, "La contabilidad todavía no está iniciada")
        self.assertNotContains(explicacion, 'name="fila"')

        # 3. Regla 9 y extensión 1b: el Contador confirma una operación con asiento (el asiento manual) sin ejercicio: ventana con HTMX (con sus encabezados y el botón en otra pestaña) y página sin HTMX.
        ventana = self.client.post(NUEVO, _asiento_manual(), **HTMX)
        self.assertContains(ventana, VENTANA)
        self.assertEqual((ventana["HX-Retarget"], ventana["HX-Reswap"]), ("body", "beforeend"))
        self.assertContains(ventana, 'target="_blank"')
        pagina = self.client.post(NUEVO, _asiento_manual(), HTTP_REFERER=f"http://testserver{NUEVO}")
        self.assertContains(pagina, VENTANA)
        self.assertContains(pagina, f"{INICIAR}?volver=")
        self.assertFalse(AsientoContable.objects.exists())  # la operación no quedó registrada
        self.assertFalse(EjercicioContable.objects.exists())

        # 4. Paso 2: el Contador entra desde el aviso; ve el formulario con la fecha de hoy, el rango y las cinco cuentas.
        formulario = self.client.get(f"{INICIAR}?volver={NUEVO}")
        self.assertContains(formulario, 'value="2027-03-10"')
        self.assertContains(formulario, 'min="2026-03-11"')
        self.assertContains(formulario, f'name="volver" value="{NUEVO}"')

        # 5. «Calcular cierre» (HTMX, sin validar): el inicio 1/1/2027 cierra el 31/12/2027.
        calculado = self.client.post(INICIAR, _apertura(accion="calcular"), **HTMX)
        self.assertContains(calculado, "31/12/2027")
        self.assertNotContains(calculado, "<html")

        # 6. Extensiones 5a y 5c: una fecha futura y el capital en blanco se marcan juntos, sin perder lo escrito ni escribir nada.
        con_errores = self.client.post(INICIAR, _apertura(accion="revisar", fecha_inicio="2027-03-11", **{"importe_3.1.01": ""}))
        self.assertContains(con_errores, "La fecha de inicio no puede ser futura.")
        self.assertContains(con_errores, "El capital inicial es obligatorio")
        self.assertContains(con_errores, 'value="1.000,00"')
        self.assertFalse(EjercicioContable.objects.exists())

        # 7. Extensión 5d: Debe y Haber distintos: no deja continuar y dice la diferencia.
        self.assertContains(self.client.post(INICIAR, _apertura(accion="revisar", **{"importe_2.1.01": "250,00"})), "la diferencia es de $ 50,00")

        # 8. Paso 5: el resumen con el ejercicio, el asiento N.º 1 y los totales; «Volver a editar» devuelve el formulario con lo escrito.
        resumen = self.client.post(INICIAR, _apertura(accion="revisar"))
        for texto in ("01/01/2027", "31/12/2027", "N.º 1", "Asiento de apertura", "$ 1.500,00", "Confirmar e iniciar", "Volver a editar"):
            self.assertContains(resumen, texto)
        self.assertContains(self.client.post(INICIAR, _apertura(accion="editar")), 'value="500,00"')
        self.assertFalse(EjercicioContable.objects.exists())

        # 9. Pasos 6 a 8: confirma; la redirección lleva a la confirmación, con «Volver a la operación» porque llegó con `volver`.
        confirmacion = self.client.post(INICIAR, {**_apertura(accion="confirmar"), "volver": NUEVO}, follow=True)
        self.assertContains(confirmacion, "La contabilidad quedó iniciada")
        self.assertContains(confirmacion, "Ejercicio 1")
        self.assertContains(confirmacion, "Volver a la operación")
        self.assertContains(confirmacion, f'href="{NUEVO}"')

        # 10. Postcondiciones a a d: el ejercicio abierto desde el 1/1/2027, el asiento N.º 1 sin origen, cuatro movimientos balanceados y la auditoría con el Contador.
        ejercicio = EjercicioContable.objects.get()
        self.assertEqual((ejercicio.estado_ejercicio, ejercicio.fecha_cierre_ejercicio, ejercicio.ultimo_numero_asiento), ("abierto", datetime.date(2027, 12, 31), 1))
        apertura = AsientoContable.objects.get()
        self.assertEqual((apertura.numero_asiento, apertura.fecha_asiento, apertura.origen_id, apertura.descripcion_asiento), (1, datetime.date(2027, 1, 1), None, "Asiento de apertura"))
        self.assertEqual(sorted(RegistroAuditoria.objects.values_list("accion", flat=True).filter(usuario=self.contador)), ["alta_asiento_contable", "alta_ejercicio_contable"] + ["alta_movimiento_contable"] * 4)

        # 11. El libro muestra el asiento N.º 1 con la fecha de inicio y la ficha dice quién lo registró; «Ejercicios» lista el Ejercicio 1.
        libro = self.client.get(LIBRO)
        self.assertContains(libro, "Asiento de apertura")
        self.assertContains(libro, "01/01/2027")
        ficha = self.client.get(reverse("contabilidad:asiento", args=[ejercicio.pk, 1]))
        self.assertContains(ficha, "Asiento de apertura")
        self.assertContains(ficha, "Cora")
        self.assertContains(self.client.get(EJERCICIOS), "Ejercicio 1")

        # 12. Postcondición e: la alerta desaparece de la campana, «Registrar asiento» vuelve y el aviso del libro vacío no está.
        self.assertNotContains(self.client.get(CAMPANA, **HTMX), AVISO)
        self.assertContains(libro, "Registrar asiento")
        self.assertNotContains(libro, "Todavía no hay ejercicios contables")

        # 13. La operación pendiente se puede registrar: el mismo asiento manual entra como N.º 2.
        registrado = self.client.post(NUEVO, _asiento_manual())
        self.assertEqual(registrado.status_code, 302)
        self.assertEqual(AsientoContable.objects.order_by("numero_asiento").values_list("numero_asiento", flat=True)[1], 2)

        # 14. Extensión 2a: abrir o enviar de nuevo la pantalla dice que ya está iniciada y no crea otro ejercicio; el atajo «Asiento de apertura» ya no existe.
        self.assertContains(self.client.get(INICIAR), "La contabilidad ya está iniciada")
        self.assertContains(self.client.post(INICIAR, _apertura(accion="confirmar")), "La contabilidad ya está iniciada")
        self.assertEqual(EjercicioContable.objects.count(), 1)
        self.assertNotContains(self.client.get(NUEVO), "atajo:apertura")
        verificar_invariantes_contables()

    def test_recorrido_del_gerente_que_inicia_porque_no_hay_contador_activo(self):
        # 1. Con un Contador activo, el Gerente no inicia: ni ve la alerta ni abre la pantalla (403 con el motivo).
        self.como(self.gerente)
        self.assertNotContains(self.client.get(CAMPANA, **HTMX), AVISO)
        self.assertContains(self.client.get(INICIAR), "Lo inicia el Contador", status_code=403)

        # 2. Sin Contador activo, el Gerente es el responsable: ve la alerta, la ventana con el botón y la pantalla; inicia.
        Contador.objects.update(is_active=False)
        cache.clear()
        self.assertContains(self.client.get(CAMPANA, **HTMX), AVISO)
        self.assertContains(self.client.get(LIBRO), f'href="{INICIAR}"')
        self.assertContains(self.client.post(NUEVO, _asiento_manual(), **HTMX), 'target="_blank"')
        confirmada = self.client.post(INICIAR, _apertura(accion="confirmar"), follow=True)
        self.assertContains(confirmada, "La contabilidad quedó iniciada")

        # 3. Paso 8: el Gerente ve el enlace a «Registrar lote existente»; el log lo deja como autor con rol Gerente.
        self.assertContains(confirmada, reverse("produccion:registrar_lote_existente"))
        self.assertEqual(RegistroAuditoria.objects.get(accion="alta_ejercicio_contable").rol, "gerente")
        self.assertEqual(AsientoContable.objects.get().numero_asiento, 1)
        verificar_invariantes_contables()

    def test_recorrido_de_los_demas_roles_ven_el_aviso_sin_boton_y_no_entran(self):
        """Regla 1: la pantalla de iniciar da 403 al Vendedor, al Agrónomo y al Gerente con Contador activo aunque la escriban a mano, la alerta no les llega y quien no tiene cuenta va al login. (El aviso
        sin botón de la ventana para esos roles lo prueba `test_contabilidad_no_iniciada.py`, con una operación de prueba.)"""
        agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")
        for cuenta in (self.vendedor, agronomo, self.gerente):
            self.como(cuenta)
            self.assertEqual(self.client.get(INICIAR).status_code, 403)
            self.assertNotContains(self.client.get(CAMPANA, **HTMX), AVISO)
            self.assertNotContains(self.client.get(INICIAR), 'name="fecha_inicio"', status_code=403)
        self.client.logout()
        self.assertEqual(self.client.get(INICIAR).status_code, 302)
        self.assertFalse(EjercicioContable.objects.exists())
