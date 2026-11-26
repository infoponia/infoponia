# Base compartida de las pruebas de servicios de COM-08a (test_estado_de_pago, test_reevaluar_mora, test_com_vnc_pag, test_com_reg_cbr, test_cobranza_concurrencia, test_cobranza_vistas): un invernadero con su
# Vendedor, un lote y un Gerente, y ayudas para armar entregas de suministro concretadas (con y sin mora) y leer los avisos. Cada prueba arma sus propios datos.
# Fuente: docs/casos_de_uso/comercial/cobranza.md («Pruebas»). CON-04d: hereda `PlanDeCuentasMixin` porque cobrar y anular un cobro ahora asientan.

from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from comercial.models import AlertaComercial
from comercial.tests.fabricas import (
    entrega_de_suministro,
    entrega_en_mora,
    escenario_comercial,
    verificar_invariantes_de_cobros,
    verificar_invariantes_de_entregas,
)
from contabilidad.tests.fabricas import PlanDeCuentasMixin, verificar_invariantes_contables
from core.models import Notificacion
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def codigos(error):
    """Los códigos de un `ValidationError` con o sin `error_dict`."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


class BaseDeCobranza(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, un lote de 5.000 plantas y un Gerente. Una entrega de suministro armada con `concretada()` vale $ 1.000,00 (10 plantas a $ 100), con 10 días de plazo y $ 300,00 por día de atraso."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.gerente = crear_gerente()

    def setUp(self):
        cache.clear()
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_cobros)
        self.addCleanup(verificar_invariantes_contables)  # CON-04d: cobrar y anular un cobro asientan

    def concretada(self, **extra):
        """Una entrega de suministro concretada hoy (vence a los 10 días), de un suministro nuevo del cliente del escenario; con ``contrato=`` suma otra del mismo."""
        return entrega_de_suministro(self.e, self.lote, **extra)

    def en_mora(self, **extra):
        """Una entrega de suministro concretada que venció hace 3 días (concretada hace 13, plazo de 10)."""
        return entrega_en_mora(self.e, self.lote, **extra)

    def avisos(self, cuenta, titulo=""):
        """Las notificaciones de ``cuenta`` cuyo título empieza con ``titulo``, de la más vieja a la más nueva."""
        return list(Notificacion.objects.filter(destinatario=cuenta, titulo__startswith=titulo).order_by("pk"))

    def alertas_de(self, entrega_, *, activas=None):
        """Las `AlertaComercial` «pago en mora» de la entrega (todas, o solo las activas o las resueltas con ``activas=True/False``)."""
        vinculos = AlertaComercial.objects.filter(entrega_id=entrega_.pk, alerta__tipo_alerta="comercial_pago_en_mora").select_related("alerta").order_by("pk")
        if activas is not None:
            vinculos = vinculos.filter(alerta__estado_alerta="activa" if activas else "resuelta")
        return list(vinculos)

    def rechazo(self, funcion, *args, **kwargs):
        """El `ValidationError` que lanza ``funcion`` (la prueba falla si no lanza)."""
        with self.assertRaises(ValidationError) as c:
            funcion(*args, **kwargs)
        return c.exception

    def correos(self):
        """Los correos enviados hasta ahora."""
        return list(mail.outbox)

    def dentro_de(self, dias):
        """La fecha de hoy más ``dias``."""
        return HOY + timedelta(days=dias)
