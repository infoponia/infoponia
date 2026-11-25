# Recorrido de CON-03a (D-96, `docs/patrones/verificacion_a_mano.md`): una prueba larga con el cliente de Django que hace de punta a punta lo que hará la persona en la
# «Verificación a mano», por rol y por estado del ejercicio. Modelo: `test_recorrido_nucleo_contable.py`. Las pantallas se piden con «hoy» fijado (`timezone.localdate`) y el
# paso diario con `--fecha`: nada lee la hora sola.
# Contador: contabilidad sin poner en marcha → puesta en marcha → asientos (automático y manual) → libro (cronológica, por cuenta, ficha) y plan → un día después del fin del ejercicio
# el paso diario lo deja «en cierre» → alerta del Panel → el Gerente (con Contador) y el Vendedor no pueden cerrar → resumen y confirmación → cerrado → ya no recibe asientos.
# Gerente: sin Contador activo cierra él, y la asociación queda vacía.
import datetime
import io
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos
from contabilidad.tests.fabricas import (
    PlanDeCuentasMixin,
    asiento_de_prueba,
    origen_de_prueba,
    verificar_invariantes_contables,
)
from core.models import Agronomo, Contador, Gerente, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
LIBRO = reverse("contabilidad:libro")
EJERCICIOS = reverse("contabilidad:ejercicios")
PLAN = reverse("contabilidad:plan")
PANEL = reverse("core:inicio")
HOY = datetime.date(2026, 6, 15)  # el primer ejercicio empieza el 1/3/2026 y termina el 28/2/2027
UN_DIA_DESPUES = datetime.date(2027, 3, 1)


def _movimientos(importe):
    return [(cuentas.CAJA, DEBE, Decimal(importe)), (cuentas.VENTAS, HABER, Decimal(importe))]


class RecorridoDeLibroYCierreTests(PlanDeCuentasMixin, TestCase):
    """Recorrido por rol (Contador, Gerente con y sin Contador activo, Vendedor y otro rol) y por estado del ejercicio (sin ejercicios, abierto, en cierre, cerrado)."""

    def setUp(self):
        self.hoy = mock.patch("django.utils.timezone.localdate", return_value=HOY).start()
        self.addCleanup(mock.patch.stopall)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com")
        self.vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        self.agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")

    def ir(self, usuario, url, **parametros):
        self.client.force_login(usuario)
        return self.client.get(url, parametros)

    def poner_en_marcha(self):
        call_command("poner_en_marcha_contabilidad", "--fecha-inicio", "2026-03-01", stdout=io.StringIO())
        return EjercicioContable.objects.get()

    def test_recorrido_del_contador_de_la_puesta_en_marcha_al_cierre(self):
        # 1. CON-CNS-LGS regla 1 y CON-CNS-PCT: sin ejercicios, el libro y los ejercicios lo explican (no hay 500) y el plan se ve igual, sin saldos.
        self.assertIn("Todavía no hay ejercicios contables", self.ir(self.contador, LIBRO).content.decode())
        self.assertIn("Todavía no hay ejercicios contables", self.ir(self.contador, EJERCICIOS).content.decode())
        self.assertEqual(self.ir(self.contador, PLAN).status_code, 200)
        self.assertNotIn("terminó el", self.ir(self.contador, PANEL).content.decode())  # sin ejercicio en cierre no hay alerta

        # 2. Puesta en marcha (CON-ABR-EJE): el primer ejercicio, abierto, y dos asientos: un automático y un manual (CON-03b todavía no existe: se arma directo y se audita).
        primero = self.poner_en_marcha()
        automatico = asientos.registrar_asiento_automatico(self.contador, origen_de_prueba(), datetime.date(2026, 5, 20), _movimientos("1000.00"), hoy=HOY)
        primero.refresh_from_db()  # el servicio ya numeró el primero: se toma el número vigente
        manual = asiento_de_prueba(primero, datetime.date(2026, 6, 1), [(cuentas.GASTOS_GENERALES, DEBE, Decimal("50.00")), (cuentas.CAJA, HABER, Decimal("50.00"))], descripcion="Pago de la luz")
        RegistroAuditoria.objects.registrar(self.contador, RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE, [manual], {})
        self.assertEqual((automatico.numero_asiento, manual.numero_asiento), (1, 2))

        # 3. CON-CNS-LGS reglas 2 y 3: el libro cronológico (por defecto, el ejercicio abierto) muestra los dos asientos con sus insignias y totales; filtra por tipo.
        libro = self.ir(self.contador, LIBRO).content.decode()
        self.assertIn("Pago de la luz", libro)
        self.assertIn("Totales (2 asientos)", libro)
        self.assertIn("Automático", libro)
        self.assertNotIn("Pago de la luz", self.ir(self.contador, LIBRO, tipo="automatico").content.decode())

        # 4. Vista por cuenta: Caja (1.000 − 50 = 950) con saldo acumulado y enlace a la ficha; Ventas parte de cero.
        caja = self.ir(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.CAJA).content.decode()
        self.assertIn("$ 950,00", caja)
        self.assertIn(reverse("contabilidad:asiento", args=[primero.pk, 2]), caja)

        # 5. Ficha del asiento manual: quién lo registró sale de la auditoría; la del automático no lo muestra. El Contador ve «Contraasentar» (CON-03b).
        ficha = self.ir(self.contador, reverse("contabilidad:asiento", args=[primero.pk, 2])).content.decode()
        self.assertIn("Registrado por", ficha)
        self.assertIn("Contraasentar", ficha)
        self.assertNotIn("Registrado por", self.ir(self.contador, reverse("contabilidad:asiento", args=[primero.pk, 1])).content.decode())

        # 6. CON-CNS-PCT regla 4: el plan muestra el saldo de Caja y el enlace al libro por cuenta.
        self.assertIn("$ 950,00", self.ir(self.contador, PLAN).content.decode())

        # 7. SEG-13: el Vendedor y otro rol que no sea Contador ni Gerente reciben 403 en cada pantalla (también por la dirección escrita a mano).
        for usuario in (self.vendedor, self.agronomo):
            for url in (LIBRO, PLAN, EJERCICIOS, reverse("contabilidad:asiento", args=[primero.pk, 1]), reverse("contabilidad:cierre", args=[primero.pk])):
                self.assertEqual(self.ir(usuario, url).status_code, 403)

        # 8. El día siguiente al fin del ejercicio, el paso diario 5 lo deja «en cierre» y abre el siguiente (CON-ABR-EJE).
        self.hoy.return_value = UN_DIA_DESPUES
        call_command("proceso_diario", solo="abrir_ejercicio", fecha="2027-03-01", stdout=io.StringIO())
        primero.refresh_from_db()
        self.assertEqual(primero.estado_ejercicio, Estado.EN_CIERRE)
        segundo = EjercicioContable.objects.get(estado_ejercicio=Estado.ABIERTO)
        self.assertEqual(segundo.fecha_inicio_ejercicio, datetime.date(2027, 3, 1))

        # 9. Panel (disparador de CON-03a): el Contador ve la alerta con «Cerrar ejercicio»; el Gerente, con un Contador activo, no; el Vendedor tampoco.
        cierre = reverse("contabilidad:cierre", args=[primero.pk])
        panel = self.ir(self.contador, PANEL).content.decode()
        self.assertIn("El ejercicio 1 terminó el 28/02/2027", panel)
        self.assertIn(cierre, panel)
        self.assertNotIn("terminó el 28/02/2027", self.ir(self.gerente, PANEL).content.decode())
        self.assertNotIn("terminó el 28/02/2027", self.ir(self.vendedor, PANEL).content.decode())

        # 10. Ejercicios: el «en cierre» lleva «Cerrar ejercicio» para el Contador y no para el Gerente (con Contador activo); el libro del «en cierre» lleva su aviso.
        self.assertIn(cierre, self.ir(self.contador, EJERCICIOS).content.decode())
        self.assertNotIn(cierre, self.ir(self.gerente, EJERCICIOS).content.decode())
        self.assertIn("Todavía se pueden registrar asientos de ese período", self.ir(self.contador, LIBRO, ejercicio=primero.pk).content.decode())

        # 11. Mientras está «en cierre» un hecho de su rango entra en él (CON-ABR-EJE): asiento 3 del ejercicio 1.
        de_febrero = asientos.registrar_asiento_automatico(self.contador, origen_de_prueba(), datetime.date(2027, 2, 20), _movimientos("200.00"), hoy=UN_DIA_DESPUES)
        self.assertEqual((de_febrero.ejercicio_id, de_febrero.numero_asiento), (primero.pk, 3))

        # 12. CON-CRR-EJE regla 5: el Gerente con un Contador activo y el Vendedor no cierran, ni por GET ni por POST; nada cambia.
        for usuario in (self.gerente, self.vendedor):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(cierre).status_code, 403)
            self.assertEqual(self.client.post(cierre, {"confirmo": "1"}).status_code, 403)
        primero.refresh_from_db()
        self.assertEqual(primero.estado_ejercicio, Estado.EN_CIERRE)

        # 13. CON-CRR-EJE regla 4: el resumen (rango, 3 asientos, Debe y Haber de 1.250) y el aviso de que no se deshace.
        resumen = self.ir(self.contador, cierre).content.decode()
        self.assertIn("01/03/2026 al 28/02/2027", resumen)
        self.assertEqual(resumen.count("$ 1.250,00"), 2)
        self.assertIn("El cierre no se puede deshacer", resumen)

        # 14. C9: enviar sin la casilla marcada no cierra y marca el error.
        sin_confirmar = self.client.post(cierre, {})
        self.assertIn("Confirmá que revisaste el libro", sin_confirmar.content.decode())
        primero.refresh_from_db()
        self.assertEqual(primero.estado_ejercicio, Estado.EN_CIERRE)

        # 15. Confirmación (CON-CRR-EJE postcondiciones a, b y c): cerrado, asociado al Contador, auditado y con el aviso de éxito.
        self.client.force_login(self.contador)
        enviado = self.client.post(cierre, {"confirmo": "1"}, follow=True)
        self.assertRedirects(enviado, EJERCICIOS)
        self.assertEqual([str(m) for m in enviado.context["messages"]], ["Cerraste el ejercicio N.º 1. Ya no recibe asientos."])
        primero.refresh_from_db()
        self.assertEqual((primero.estado_ejercicio, primero.contador_id), (Estado.CERRADO, self.contador.pk))
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.MODIFICACION_EJERCICIO_CONTABLE, usuario=self.contador)
        self.assertEqual(registro.detalle["datos"], {"cerrado_por": "contador"})
        self.assertIn("Lo cerró", enviado.content.decode())
        self.assertNotIn(cierre, enviado.content.decode())  # ya no hay botón

        # 16. Estado «cerrado»: el libro se ve «solo de consulta», el Panel ya no tiene alerta, y cerrar otra vez vuelve a la lista con un aviso.
        self.assertIn("Sus asientos son solo de consulta", self.ir(self.contador, LIBRO, ejercicio=primero.pk).content.decode())
        self.assertNotIn("terminó el 28/02/2027", self.ir(self.contador, PANEL).content.decode())
        otra_vez = self.client.get(cierre, follow=True)
        self.assertEqual([str(m) for m in otra_vez.context["messages"]], ["El ejercicio N.º 1 no está en cierre: no se puede cerrar."])

        # 17. Regla 2: ya no recibe asientos. Un automático con fecha de su rango va al abierto, con la fecha de hoy y la aclaración (D-102).
        despues = asientos.registrar_asiento_automatico(self.contador, origen_de_prueba(), datetime.date(2027, 2, 25), _movimientos("1.00"), hoy=UN_DIA_DESPUES)
        self.assertEqual((despues.ejercicio_id, despues.fecha_asiento), (segundo.pk, UN_DIA_DESPUES))
        self.assertIn("el ejercicio de esa fecha ya está cerrado", despues.descripcion_asiento)
        self.assertEqual(AsientoContable.objects.filter(ejercicio=primero).count(), 3)

        # 18. Regla 3 (sin refundición): Caja arrastra al ejercicio siguiente (1.000 − 50 + 200 + 1 = 1.151) y Ventas empieza en cero.
        caja_2 = self.ir(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.CAJA, ejercicio=segundo.pk).content.decode()
        ventas_2 = self.ir(self.contador, LIBRO, vista="cuenta", cuenta=cuentas.VENTAS, ejercicio=segundo.pk).content.decode()
        self.assertIn("Arrastra los ejercicios anteriores", caja_2)
        self.assertIn("$ 1.150,00", caja_2)  # el saldo al inicio del ejercicio 2: 1.000 − 50 + 200
        self.assertIn("Empieza en cero cada ejercicio", ventas_2)

        # 19. Sin consultas que escriban: ninguna pantalla de consulta agregó registros de auditoría (solo el cierre y los asientos).
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_EJERCICIO_CONTABLE).count(), 2)  # el paso a «en cierre» y el cierre
        verificar_invariantes_contables()

    def test_recorrido_del_gerente_sin_contador_activo_cierra_el_y_la_asociacion_queda_vacia(self):
        # 1. Preparación: un ejercicio que ya terminó (paso diario) con un asiento, y sin Contador activo.
        primero = self.poner_en_marcha()
        asientos.registrar_asiento_automatico(None, origen_de_prueba(), datetime.date(2026, 5, 20), _movimientos("300.00"), hoy=HOY)
        self.hoy.return_value = UN_DIA_DESPUES
        call_command("proceso_diario", solo="abrir_ejercicio", fecha="2027-03-01", stdout=io.StringIO())
        Contador.objects.update(is_active=False)
        cierre = reverse("contabilidad:cierre", args=[primero.pk])

        # 2. El Gerente ve el libro y los ejercicios (siempre los consulta) y ahora también la alerta del Panel y el botón (D-85 punto 4).
        self.assertEqual(self.ir(self.gerente, LIBRO).status_code, 200)
        self.assertIn(cierre, self.ir(self.gerente, PANEL).content.decode())
        self.assertIn(cierre, self.ir(self.gerente, EJERCICIOS).content.decode())

        # 3. El resumen le aclara por qué cierra él; confirma y el ejercicio queda cerrado sin Contador asociado, con él en la auditoría.
        self.assertIn("porque no hay un Contador activo", self.ir(self.gerente, cierre).content.decode())
        self.client.post(cierre, {"confirmo": "1"})
        primero.refresh_from_db()
        self.assertEqual((primero.estado_ejercicio, primero.contador_id), (Estado.CERRADO, None))
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.MODIFICACION_EJERCICIO_CONTABLE, usuario=self.gerente)
        self.assertEqual(registro.detalle["datos"], {"cerrado_por": "gerente"})
        self.assertIn("Sin Contador asociado", self.ir(self.gerente, EJERCICIOS).content.decode())

        # 4. Un Contador nuevo (reemplazo, D-85 punto 4) vuelve a ser el responsable: el Gerente queda solo con la consulta y la pantalla se lo dice.
        crear_cuenta(Contador, email="nuevo@infoponia.com")
        self.assertIn("Los ejercicios los cierra el Contador", self.ir(self.gerente, EJERCICIOS).content.decode())
        verificar_invariantes_contables()
