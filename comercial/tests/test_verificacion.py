# Pruebas del cargador de datos de verificación de `comercial` (`comercial/verificacion.py`; CLAUDE.md, «Datos para la verificación a mano»):
# deja cuentas, un invernadero con un transportista agregado y otro sin invernadero, clientes en cada estado y un vehículo dado de baja,
# llamando a los servicios; no duplica nada, no carga el vehículo de los pasos 7 a 9 y no pasa la contraseña por la salida ni por la
# auditoría. La guarda de «solo la base local» ya la prueba `core`.

from django.test import TestCase

from comercial import verificacion as cargador
from comercial.models import Cliente, Vehiculo
from core import verificacion
from core.models import RegistroAuditoria, Usuario
from core.tests.fabricas import crear_gerente
from core.verificacion import ErrorDeCarga
from maestros.models import Invernadero, TransportistaInvernadero
from maestros.tests.fabricas import ConGeoref

CLAVE = "Zanahoria-71290"


class ComercialVerificacionTests(ConGeoref, TestCase):
    """`comercial.verificacion.cargar`: usa los servicios de las apps y es idempotente."""

    def setUp(self):
        self.gerente = crear_gerente()

    def test_d_verificacion_deja_las_cuentas_con_la_contrasena_de_quien_trabaja(self):
        """Cuentas ``<rol>@prueba5.local`` (el número propio de este cargador) con la contraseña recibida."""
        resumen = cargador.cargar(CLAVE)
        for correo in ("vendedor", "transportista", "transportista2"):
            self.assertTrue(Usuario.objects.get(email=f"{correo}@prueba5.local").check_password(CLAVE))
        self.assertIn("vendedor@prueba5.local · vendedor", resumen.cuentas)
        self.assertEqual(resumen.pendiente, ())

    def test_d_verificacion_un_transportista_en_el_invernadero_y_el_otro_sin_invernadero(self):
        """Los dos estados que pide la verificación: uno agregado desde «Logística» (MAE-05) y otro sin invernadero."""
        cargador.cargar(CLAVE)
        invernadero = Invernadero.objects.get(nombre_invernadero="Invernadero Comercial")
        con = Usuario.objects.get(email="transportista@prueba5.local")
        sin = Usuario.objects.get(email="transportista2@prueba5.local")
        self.assertEqual(TransportistaInvernadero.objects.get(transportista_id=con.pk).invernadero_id, invernadero.pk)
        self.assertFalse(TransportistaInvernadero.objects.filter(transportista_id=sin.pk).exists())

    def test_d_verificacion_clientes_en_cada_estado(self):
        """Una jurídica con correo y dos direcciones (urbana y rural), una física sin correo y una jurídica dada de baja."""
        cargador.cargar(CLAVE)
        con = Cliente.objects.get(cuit_cliente="30500000011")
        self.assertEqual((con.estado_cliente, bool(con.email_cliente), con.direcciones.count()), ("activo", True, 2))
        fisica = Cliente.objects.get(cuit_cliente="20500000032")
        self.assertEqual((fisica.tipo_cliente, fisica.email_cliente, fisica.estado_cliente), ("fisica", "", "activo"))
        self.assertEqual(Cliente.objects.get(cuit_cliente="30500000046").estado_cliente, "inactivo")

    def test_d_verificacion_un_vehiculo_dado_de_baja_y_ninguno_activo(self):
        """Un vehículo inactivo para probar «Reactivar»; el AE123CD de los pasos 7 a 9 lo registra la persona."""
        cargador.cargar(CLAVE)
        self.assertEqual(list(Vehiculo.objects.values_list("patente", "estado_vehiculo")), [("ZZZ999", "inactivo")])

    def test_d_verificacion_llama_a_los_servicios_y_quedan_los_registros_de_auditoria(self):
        """Nada con inserciones directas: quedan las altas y las bajas auditadas, como en una pantalla."""
        cargador.cargar(CLAVE)
        acciones = set(RegistroAuditoria.objects.values_list("accion", flat=True))
        self.assertTrue({"alta_cliente", "baja_cliente", "alta_vehiculo", "baja_vehiculo"} <= acciones)

    def test_d_verificacion_es_idempotente(self):
        """Una segunda corrida no duplica nada ni falla."""
        cargador.cargar(CLAVE)
        antes = (Usuario.objects.count(), Cliente.objects.count(), Vehiculo.objects.count(), Invernadero.objects.count(), RegistroAuditoria.objects.count())
        resumen = cargador.cargar(CLAVE)
        despues = (Usuario.objects.count(), Cliente.objects.count(), Vehiculo.objects.count(), Invernadero.objects.count(), RegistroAuditoria.objects.count())
        self.assertEqual(antes, despues)
        self.assertEqual(resumen.creado, ())

    def test_d_verificacion_com_02_los_dos_invernaderos_con_su_lote_en_maduracion_y_uno_sin_capataz(self):
        """COM-02: «Verificación Comercial Norte» (con Capataz) y «Sur» (sin Capataz), del mismo Vendedor, cada uno con un lote de «Lechuga (prueba)
        Crespa» en Maduración (100 y 80 plantas) y la alerta «sin Capataz activo» del Sur para el Gerente; lo carga con los servicios."""
        from maestros.models import Alerta
        from produccion.models import Lote

        cargador.cargar(CLAVE)
        vendedor = Usuario.objects.get(email="vendedor@prueba5.local")
        norte = Invernadero.objects.get(nombre_invernadero=cargador.NORTE)
        sur = Invernadero.objects.get(nombre_invernadero=cargador.SUR)
        self.assertEqual((norte.vendedor_id, sur.vendedor_id), (vendedor.pk, vendedor.pk))
        self.assertEqual((norte.capataz_id is not None, sur.capataz_id), (True, None))
        lotes = {l.invernadero_id: l for l in Lote.objects.select_related("etapa__tipo_etapa")}
        self.assertEqual((lotes[norte.pk].cantidad_actual, lotes[sur.pk].cantidad_actual), (100, 80))
        self.assertEqual({l.etapa.tipo_etapa.codigo for l in lotes.values()}, {"maduracion"})
        self.assertTrue(Alerta.objects.filter(invernadero=sur, tipo_alerta="sin_capataz", estado_alerta="activa").exists())
        for correo in ("agronomo", "capataz", "vendedor2"):
            self.assertTrue(Usuario.objects.get(email=f"{correo}@prueba5.local").check_password(CLAVE))

    def test_d_verificacion_com_02_el_stock_maduro_alcanza_para_la_primera_venta_de_la_verificacion(self):
        """Pasos 2 y 3 de la verificación a mano: para dentro de 3 días la variedad tiene 100 plantas disponibles (solo el lote del invernadero CON Capataz)."""
        from datetime import timedelta

        from django.utils import timezone

        from comercial.servicios import stock_maduro
        from maestros.models import Variedad

        cargador.cargar(CLAVE)
        variedad = Variedad.objects.get(nombre_variedad="Crespa", cultivo__nombre_cultivo=cargador.CULTIVO)
        invernaderos = list(Invernadero.objects.filter(nombre_invernadero__in=[cargador.NORTE, cargador.SUR]).values_list("pk", flat=True))
        disponible = stock_maduro.disponible([variedad.pk], invernaderos, timezone.localdate() + timedelta(days=3), "compra_venta")
        self.assertEqual(disponible[variedad.pk].total, 100)

    def test_d_verificacion_sin_gerente_activo_lo_dice(self):
        """Sin Gerente activo no se puede cargar nada: ``ErrorDeCarga`` con un mensaje claro."""
        self.gerente.is_active = False
        self.gerente.save()
        with self.assertRaises(ErrorDeCarga):
            cargador.cargar(CLAVE)

    def test_d_verificacion_la_contrasena_no_va_a_la_salida_ni_a_la_auditoria(self):
        """Nunca imprime ni devuelve la contraseña ni la guarda en la auditoría."""
        resumen = cargador.cargar(CLAVE)
        texto = " ".join((*resumen.creado, *resumen.cuentas, *resumen.pendiente))
        self.assertNotIn(CLAVE, texto)
        self.assertFalse(any(CLAVE in str(registro.detalle) for registro in RegistroAuditoria.objects.all()))

    def test_d_verificacion_esta_registrado_con_el_orden_20(self):
        """``ComercialConfig.ready()`` lo registra en ``core.verificacion`` con el orden 20, después de `maestros`, `iot` y `produccion`."""
        registrado = {c.codigo: c for c in verificacion.cargadores()}
        self.assertEqual(registrado["comercial"].orden, 20)
        self.assertEqual([c.codigo for c in verificacion.cargadores()].count("comercial"), 1)
        self.assertGreater(registrado["comercial"].orden, max(c.orden for c in registrado.values() if c.codigo != "comercial"))
