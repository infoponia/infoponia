# Pruebas de las restricciones de la base y del comportamiento de los modelos de `comercial` (COM-01, paso 1;
# docs/modelo/comercial.md): Cliente, DireccionCliente y Vehiculo. Cada restricción se prueba violada y no violada.

from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import Cliente, DireccionCliente, Vehiculo
from comercial.tests.fabricas import cliente, cuit_valido, vehiculo
from core.tests.fabricas import crear_gerente
from maestros.models import DireccionUrbana
from maestros.tests.fabricas import ConGeoref, crear_agronomo, crear_transportista, crear_vendedor, localidad


def _violada(prueba, **datos):
    """Crea un vehículo con ``datos`` y comprueba que la base lo rechaza (en un savepoint, para seguir usando la conexión)."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        vehiculo(**datos)


class ClienteRestriccionesTests(TestCase):
    """Restricciones de base de `Cliente` (docs/modelo/comercial.md, «Cliente»)."""

    def crear(self, **campos):
        base = {
            "tipo_cliente": "juridica",
            "cuit_cliente": cuit_valido(),
            "razon_social_cliente": "Acme S.A.",
            "nombre_cliente": "",
            "apellido_cliente": "",
        }
        base.update(campos)
        return Cliente.objects.create(**base)

    def test_regla_1_cuit_unico_entre_activos_e_inactivos(self):
        """MD-48 y regla 1 de COM-ALT-CLT: dos clientes con el mismo CUIT no caben, aunque uno esté inactivo."""
        existente = cliente(activo=False)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear(cuit_cliente=existente.cuit_cliente)

    def test_regla_1_cuit_distinto_se_crea(self):
        """Regla 1 de COM-ALT-CLT: con otro CUIT se crea sin problema."""
        cliente()
        self.assertEqual(self.crear().estado_cliente, "activo")

    def test_regla_1_cuit_de_11_digitos(self):
        """Modelo, «Cliente»: el CUIT son exactamente 11 dígitos; menos, más o letras, no."""
        for malo in ("3071234567", "3071234567a", "30-7123456"):
            with self.subTest(cuit=malo), self.assertRaises(IntegrityError), transaction.atomic():
                self.crear(cuit_cliente=malo)

    def test_regla_3_juridica_exige_razon_social_y_nada_mas(self):
        """Regla 3 de COM-ALT-CLT: jurídica ⇒ razón social no vacía, nombre y apellido vacíos."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear(razon_social_cliente="")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear(nombre_cliente="Marta")
        self.assertTrue(self.crear().pk)

    def test_regla_3_fisica_exige_nombre_y_apellido_sin_razon_social(self):
        """Regla 3 de COM-ALT-CLT: física ⇒ nombre y apellido no vacíos, razón social vacía."""
        fisica = {"tipo_cliente": "fisica", "razon_social_cliente": "", "nombre_cliente": "Marta", "apellido_cliente": "Gómez"}
        self.assertTrue(self.crear(**fisica).pk)
        for malo in ({"nombre_cliente": ""}, {"apellido_cliente": ""}, {"razon_social_cliente": "Acme"}):
            with self.subTest(malo=malo), self.assertRaises(IntegrityError), transaction.atomic():
                self.crear(**{**fisica, **malo})

    def test_str_y_nombre_visible(self):
        """Modelo: «razón social» o «Nombre Apellido» (texto de la auditoría)."""
        self.assertEqual(str(cliente(razon_social="Acme S.A.")), "Acme S.A.")
        self.assertEqual(str(cliente(tipo="fisica", nombre="Marta", apellido="Gómez")), "Marta Gómez")


class ClienteAlcanceTests(TestCase):
    """`ClienteQuerySet.en_alcance_de` (D-28; regla 3 de COM-CNS-CLT)."""

    def test_regla_3_el_gerente_y_el_vendedor_activos_ven_todos(self):
        """Regla 3 de COM-CNS-CLT: un cliente puede comprarle a varios Vendedores."""
        uno = cliente()
        for actor in (crear_gerente(), crear_vendedor()):
            with self.subTest(rol=actor.rol):
                self.assertEqual(list(Cliente.objects.en_alcance_de(actor)), [uno])

    def test_regla_3_otros_roles_cuentas_inactivas_y_anonimos_no_ven_nada(self):
        """D-28: cualquier otro rol, una cuenta inactiva o ``None``, ninguno."""
        cliente()
        for actor in (crear_agronomo(), crear_transportista(), crear_vendedor("inactivo@infoponia.com", activo=False), None):
            with self.subTest(actor=actor):
                self.assertFalse(Cliente.objects.en_alcance_de(actor).exists())


class DireccionClienteRestriccionesTests(ConGeoref, TestCase):
    """`DireccionCliente` (D-58): una dirección es de un solo cliente."""

    def nueva_direccion(self):
        return DireccionUrbana.objects.create(localidad=localidad(), calle="San Martín", numero_calle="123")

    def test_d58_una_direccion_es_de_un_solo_cliente(self):
        """D-58 punto 1 (Dirección → Cliente = 0..1): la misma dirección no se vincula a dos clientes."""
        direccion = self.nueva_direccion()
        DireccionCliente.objects.create(cliente=cliente(), direccion=direccion.direccion_ptr)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DireccionCliente.objects.create(cliente=cliente(), direccion=direccion.direccion_ptr)

    def test_d58_un_cliente_tiene_cero_o_mas_direcciones(self):
        """MD-128 (Cliente → Dirección = 0..*): un cliente sin direcciones y otro con dos."""
        sin, con = cliente(), cliente()
        for _ in range(2):
            DireccionCliente.objects.create(cliente=con, direccion=self.nueva_direccion().direccion_ptr)
        self.assertEqual(sin.direcciones.count(), 0)
        self.assertEqual(con.direcciones.count(), 2)


class VehiculoRestriccionesTests(TestCase):
    """Restricciones de base de `Vehiculo` (docs/modelo/comercial.md, «Vehiculo»)."""

    def test_regla_1_patente_unica_entre_activos_e_inactivos(self):
        """Regla 1 de COM-ALT-VEH: la patente es única, también entre inactivos."""
        vehiculo(patente="AE123CD", activo=False)
        _violada(self, patente="AE123CD")

    def test_regla_1_patente_con_formato(self):
        """Regla 1 de COM-ALT-VEH: AAA123 o AA123AA, en mayúsculas y sin espacios."""
        for buena in ("ABC123", "AE123CD"):
            with self.subTest(patente=buena):
                self.assertEqual(vehiculo(patente=buena).patente, buena)
        for mala in ("abc123", "AB1234C", "ABCD12", "AB 123", "A123BCD", "AE-12CD"):
            with self.subTest(patente=mala):
                _violada(self, patente=mala)

    def test_regla_3_capacidad_mayor_que_cero(self):
        """Regla 3 de COM-ALT-VEH: la capacidad es mayor que 0."""
        self.assertEqual(Vehiculo.objects.get(pk=vehiculo(capacidad="0.01").pk).capacidad_carga, Decimal("0.01"))
        for mala in ("0", "-5"):
            with self.subTest(capacidad=mala):
                _violada(self, capacidad=mala)

    def test_regla_3_capacidad_hasta_999999_con_dos_decimales(self):
        """Modelo, «Vehiculo»: ``DecimalField(8, 2)``, hasta 999.999,99 kg."""
        self.assertEqual(Vehiculo.objects.get(pk=vehiculo(capacidad="999999.99").pk).capacidad_carga, Decimal("999999.99"))

    def test_md118_en_ruta_exige_fecha_de_inicio(self):
        """MD-118: ``en_ruta`` verdadero ⇒ ``fecha_inicio_ruta`` no nula."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Vehiculo.objects.create(
                patente="AE123CD", tipo_vehiculo="moto", marca="Honda", modelo="XR", capacidad_carga=50, en_ruta=True
            )
        self.assertTrue(vehiculo(en_ruta_hoy=True).en_ruta)

    def test_post_a_un_vehiculo_inactivo_no_tiene_transportista(self):
        """Postcondición a de COM-BAJ-VEH y c de COM-MOD-VEH: inactivo ⇒ sin transportista."""
        transportista = crear_transportista()
        with self.assertRaises(IntegrityError), transaction.atomic():
            vehiculo(activo=False, transportista=transportista)
        self.assertTrue(vehiculo(activo=True, transportista=transportista).pk)
        self.assertTrue(vehiculo(activo=False).pk)

    def test_r073_un_transportista_tiene_a_lo_sumo_un_vehiculo(self):
        """R073: la base garantiza que un transportista no tiene dos vehículos; dos vehículos sin transportista sí caben."""
        transportista = crear_transportista()
        vehiculo(transportista=transportista)
        _violada(self, transportista=transportista)
        vehiculo()
        vehiculo()

    def test_str_es_tipo_y_patente(self):
        """Modelo: «Camioneta AE123CD»."""
        self.assertEqual(str(vehiculo(patente="AE123CD", tipo="camioneta")), "Camioneta AE123CD")


class VehiculoEstaEnRutaTests(TestCase):
    """`Vehiculo.esta_en_ruta(hoy)` (MD-118)."""

    def test_md118_en_ruta_hoy(self):
        """MD-118: ``en_ruta`` y ruta iniciada hoy ⇒ en ruta."""
        hoy = timezone.localdate()
        self.assertTrue(vehiculo(en_ruta_hoy=True).esta_en_ruta(hoy))

    def test_md118_ruta_de_ayer_sin_finalizar_ya_no_esta_en_ruta(self):
        """MD-118: una ruta que no se finalizó deja de estar vigente al terminar el día."""
        hoy = timezone.localdate()
        ayer = vehiculo()
        Vehiculo.objects.filter(pk=ayer.pk).update(en_ruta=True, fecha_inicio_ruta=hoy - timedelta(days=1))
        ayer.refresh_from_db()
        self.assertTrue(ayer.en_ruta)
        self.assertFalse(ayer.esta_en_ruta(hoy))

    def test_md118_sin_ruta_no_esta_en_ruta(self):
        """MD-118: sin ruta iniciada, no está en ruta."""
        self.assertFalse(vehiculo().esta_en_ruta(date.today()))


class VehiculoAlcanceTests(TestCase):
    """`VehiculoQuerySet.en_alcance_de` (D-28): solo el Gerente activo."""

    def test_solo_el_gerente_activo_ve_los_vehiculos(self):
        """COM-ALT/MOD/BAJ/CNS-VEH: actor Gerente; los demás roles, nada."""
        uno = vehiculo()
        self.assertEqual(list(Vehiculo.objects.en_alcance_de(crear_gerente())), [uno])
        for actor in (crear_vendedor(), crear_agronomo(), crear_transportista(), None):
            with self.subTest(actor=actor):
                self.assertFalse(Vehiculo.objects.en_alcance_de(actor).exists())
        self.assertFalse(Vehiculo.objects.en_alcance_de(crear_gerente("inactivo@infoponia.com", activo=False)).exists())
