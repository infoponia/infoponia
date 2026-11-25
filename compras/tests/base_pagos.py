# Andamiaje compartido por las pruebas del pago a proveedores de CMP-05 (no tiene pruebas propias): ``PagosBase`` agrega, sobre el escenario de ``RecepcionBase`` (la orden aprobada de Ana con A en
# Norte y B en Norte 2), un Contador activo, un ejercicio abierto y los auxiliares para recibir, pagar y mirar lo que cambió.
#
# Montos del escenario (D-89): A tiene dos líneas (Fertilizante 10 kg a $100,00 y Maceta 20 u a $200,00): todo recibido son $300,00. B tiene una (Tomate 8 u a $80,00).

from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.core.cache import cache

from compras.errores import ErrorDeCompras
from compras.models import Pago, Recepcion
from compras.tests.base_recepciones import RecepcionBase
from contabilidad.models import AsientoContable
from contabilidad.tests.fabricas import ejercicio_abierto
from core.models import Contador, Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_cuenta
from inventario.tests.fabricas import perezoso

pagos = perezoso("compras.servicios.pagos")
D = Decimal


class PagosBase(RecepcionBase):
    """Ver el encabezado del archivo. ``self.contador`` es el Contador activo; para probar «sin Contador» una prueba lo da de baja con ``self.sin_contador()``."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.abierto = ejercicio_abierto()

    # --- armar lo que hay para pagar ---

    def recibir_a(self, actor=None):
        """Recibe todo lo de A (Fertilizante 10 y Maceta 20): A queda para pagar $300,00."""
        return self.registrar(actor or self.ana, [self.linea(self.l_fert, 10, self.vence), self.linea(self.l_maceta, 20)])

    def recibir_b(self, actor=None):
        """Recibe todo lo de B (Tomate 8): B queda para pagar $80,00."""
        return self.registrar(actor or self.ana, [self.linea(self.l_tomate, 8)], proveedor=self.proveedor_b, invernadero=self.norte2)

    def recibir_a_con_faltante(self):
        """Recibe 4 de 10 del Fertilizante y 20 de 20 de la Maceta, y cierra con faltante lo que falta del Fertilizante: A queda para pagar 40,00 + 200,00 = $240,00."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence), self.linea(self.l_maceta, 20)])
        with self.captureOnCommitCallbacks(execute=True):
            from compras.servicios import recepciones

            recepciones.cerrar_con_faltante(self.ana, [(self.l_fert.pk, "El proveedor no repone.")])

    def otra_pagable(self, n, total="60.00", cantidad=6):
        """Una segunda orden aprobada (proveedor ``n``) recibida entera por Ana: devuelve ``(orden, proveedor)``; queda para pagar ``total``."""
        orden, linea, _ = self.otra_orden(self.ana, self.norte, nombre_de_insumo=f"Insumo {n}", cantidad=cantidad, total=total, n=n)
        self.registrar(self.ana, [self.linea(linea, cantidad)], orden=orden, proveedor=linea.proveedor, invernadero=self.norte)
        return orden, linea.proveedor

    def sin_contador(self):
        """Da de baja al Contador: desde ahora el responsable contable es el Gerente (D-85 punto 4)."""
        Contador.objects.filter(pk=self.contador.pk).update(is_active=False)

    # --- pagar ---

    def pagar(self, actor=None, proveedor=None, medio="transferencia", fecha=None, orden=None, hoy=None):
        """``registrar_pago`` con los correos ejecutados; por defecto lo hace el Contador y paga a A por transferencia con fecha de hoy. Devuelve el ``Pago``."""
        with self.captureOnCommitCallbacks(execute=True):
            return pagos.registrar_pago(
                actor or self.contador, (orden or self.orden).pk, (proveedor or self.proveedor).pk, medio, fecha or self.hoy, hoy=hoy
            )

    def error_de_pago(self, actor=None, proveedor=None, medio="transferencia", fecha=None, orden=None, clase=ErrorDeCompras):
        """La excepción de ``clase`` que lanza ``registrar_pago`` (falla la prueba si no lanza ninguna)."""
        with self.assertRaises(clase) as contexto:
            with self.captureOnCommitCallbacks(execute=True):
                pagos.registrar_pago(actor or self.contador, (orden or self.orden).pk, (proveedor or self.proveedor).pk, medio, fecha or self.hoy)
        return contexto.exception

    def instantanea_de_pagos(self):
        """Lo que no debe cambiar si el pago se rechaza o falla: pagos, asientos, auditoría, notificaciones y correos."""
        return (Pago.objects.count(), AsientoContable.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count(), len(mail.outbox))

    def sin_cambios_de_pagos(self, antes):
        self.assertEqual(self.instantanea_de_pagos(), antes)

    # --- mirar ---

    def asiento_del_pago(self, pago):
        return AsientoContable.objects.get(origen_id=pago.pk)

    def avisos_de_pago(self, destinatario):
        """Las notificaciones «Proveedor para pagar» de ``destinatario``, de la más antigua a la más reciente."""
        return list(Notificacion.objects.filter(destinatario=destinatario, titulo="Proveedor para pagar").order_by("id"))

    def fechar_recepciones(self, dias_atras):
        """Pone a todas las recepciones registradas hasta ahora la fecha de hoy menos ``dias_atras`` (para probar el «listo desde» sin tocar el reloj)."""
        Recepcion.objects.update(fecha_recepcion=self.hoy - timedelta(days=dias_atras))
