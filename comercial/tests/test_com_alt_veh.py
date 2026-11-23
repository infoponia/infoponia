# Pruebas de COM-ALT-VEH, Alta Vehículo (COM-01, paso 4; docs/casos_de_uso/comercial/vehiculos.md): solo el Gerente, la patente
# (normalizada, con formato y única), el tipo, la marca y el modelo, la capacidad, el transportista (opcional, activo y sin otro
# vehículo), la notificación y la auditoría.
#
# Contrato que fijan estas pruebas (lo revisa el estudiante antes de implementar):
#   - ``DatosDeVehiculo(patente, tipo_vehiculo, marca, modelo, capacidad_carga, transportista_id=None)``, con ``desde_post(post)``.
#   - Errores por campo: ``patente`` (``obligatorio``, ``patente_invalida``, ``patente_repetida``), ``tipo_vehiculo``
#     (``tipo_invalido``), ``marca`` y ``modelo`` (``obligatorio``, ``demasiado_largo``), ``capacidad_carga``
#     (``capacidad_invalida``) y ``transportista`` (``transportista_invalido``, ``transportista_con_vehiculo``).
#   - ``texto_capacidad(Decimal) -> str``: «800 kg», «800,5 kg», «1.250,25 kg».

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase

from comercial.models import Vehiculo
from comercial.servicios import vehiculos
from comercial.servicios.vehiculos import DatosDeVehiculo
from comercial.tests.fabricas import datos_de_vehiculo, vehiculo
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.tests.fabricas import crear_agronomo, crear_transportista, crear_vendedor


def errores_de(prueba, llamada):
    """Ejecuta ``llamada`` y devuelve los errores que lanza como ``{campo: [ValidationError]}``."""
    with prueba.assertRaises(ValidationError) as contexto:
        llamada()
    return contexto.exception.error_dict


def codigos(errores, campo):
    """Los códigos del campo ``campo`` de un ``error_dict``."""
    return [e.code for e in errores.get(campo, [])]


class ComAltVehServicioTests(TestCase):
    """``alta_vehiculo(actor, datos)``."""

    def setUp(self):
        self.gerente = crear_gerente()

    def alta(self, **extra):
        return vehiculos.alta_vehiculo(self.gerente, datos_de_vehiculo(**extra))

    # -- precondición a --

    def test_pre_a_solo_el_gerente_activo_puede(self):
        """Precondición a: Gerente activo; el Vendedor, otros roles, una cuenta inactiva o ``None`` reciben ``PermissionDenied``."""
        for actor in (crear_vendedor(), crear_agronomo(), crear_transportista(), None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                vehiculos.alta_vehiculo(actor, datos_de_vehiculo())
        self.assertFalse(Vehiculo.objects.exists())

    # -- postcondición a --

    def test_post_a_crea_un_vehiculo_activo_sin_ruta_y_sin_transportista(self):
        """Postcondición a: «activo», sin ruta iniciada, con patente, tipo, marca, modelo y capacidad."""
        creado = self.alta()
        creado = Vehiculo.objects.get(pk=creado.pk)
        self.assertEqual(
            (creado.patente, creado.tipo_vehiculo, creado.marca, creado.modelo, creado.capacidad_carga),
            ("AE123CD", "camioneta", "Ford", "Ranger", Decimal("800.00")),
        )
        self.assertEqual((creado.estado_vehiculo, creado.en_ruta, creado.fecha_inicio_ruta), ("activo", False, None))
        self.assertIsNone(creado.transportista_id)

    # -- regla 1 (patente) --

    def test_regla_1_la_patente_se_normaliza_a_mayusculas_sin_espacios_ni_guiones(self):
        """Regla 1 (MD-129): sin distinguir mayúsculas y sin espacios ni guiones; se guarda en mayúsculas."""
        for escrita, guardada in (("ae-123 cd", "AE123CD"), (" abc 123 ", "ABC123"), ("Ab-C-123", "ABC123")):
            with self.subTest(escrita=escrita):
                Vehiculo.objects.all().delete()
                self.assertEqual(self.alta(patente=escrita).patente, guardada)

    def test_regla_1_la_patente_es_obligatoria_y_con_formato_argentino(self):
        """Regla 1: obligatoria (``obligatorio``); AAA123 o AA123AA (``patente_invalida``)."""
        self.assertEqual(codigos(errores_de(self, lambda: self.alta(patente="  ")), "patente"), ["obligatorio"])
        for mala in ("ABCD12", "AB1234C", "A123BCD", "123ABC", "AE.123.CD", "ABC1234"):
            with self.subTest(patente=mala):
                self.assertEqual(codigos(errores_de(self, lambda: self.alta(patente=mala)), "patente"), ["patente_invalida"])

    def test_regla_1_la_patente_es_unica_entre_activos_e_inactivos(self):
        """Regla 1 y precondición b: ``patente_repetida``, también contra un vehículo inactivo y sin distinguir cómo se escribió."""
        vehiculo(patente="AE123CD")
        vehiculo(patente="ABC123", activo=False)
        for escrita in ("AE123CD", "ae-123 cd", "abc 123"):
            with self.subTest(patente=escrita):
                self.assertEqual(codigos(errores_de(self, lambda: self.alta(patente=escrita)), "patente"), ["patente_repetida"])
        self.assertEqual(Vehiculo.objects.count(), 2)

    # -- reglas 2 y 3 --

    def test_regla_2_el_tipo_es_de_una_lista_cerrada(self):
        """Regla 2 (MD-129): camioneta, furgón, camión, utilitario y moto; otro valor es ``tipo_invalido``."""
        for tipo in Vehiculo.Tipo.values:
            with self.subTest(tipo=tipo):
                Vehiculo.objects.all().delete()
                self.assertEqual(self.alta(tipo_vehiculo=tipo).tipo_vehiculo, tipo)
        for malo in ("", "bicicleta", None):
            with self.subTest(tipo=malo):
                self.assertEqual(codigos(errores_de(self, lambda: self.alta(tipo_vehiculo=malo)), "tipo_vehiculo"), ["tipo_invalido"])

    def test_regla_2_la_marca_y_el_modelo_son_obligatorios_y_se_recortan(self):
        """Regla 2: dos textos obligatorios (``obligatorio``), recortados, de hasta 50 caracteres (``demasiado_largo``)."""
        errores = errores_de(self, lambda: self.alta(marca=" ", modelo=""))
        self.assertEqual((codigos(errores, "marca"), codigos(errores, "modelo")), (["obligatorio"], ["obligatorio"]))
        creado = self.alta(marca="  Ford ", modelo=" Ranger ")
        self.assertEqual((creado.marca, creado.modelo), ("Ford", "Ranger"))
        errores = errores_de(self, lambda: self.alta(patente="ABC123", marca="a" * 51, modelo="b" * 51))
        self.assertEqual((codigos(errores, "marca"), codigos(errores, "modelo")), (["demasiado_largo"], ["demasiado_largo"]))

    def test_regla_3_la_capacidad_acepta_coma_o_punto_y_hasta_dos_decimales(self):
        """Regla 3: en kg, con coma o punto decimal, hasta dos decimales; se guarda como ``Decimal``."""
        for escrita, esperada in (("800", "800.00"), ("800,5", "800.50"), ("800.5", "800.50"), ("0,01", "0.01"), ("999999,99", "999999.99")):
            with self.subTest(capacidad=escrita):
                Vehiculo.objects.all().delete()
                creado = self.alta(capacidad_carga=escrita)
                self.assertEqual(Vehiculo.objects.get(pk=creado.pk).capacidad_carga, Decimal(esperada))

    def test_regla_3_la_capacidad_tiene_que_ser_mayor_que_cero_y_valida(self):
        """Regla 3: ``capacidad_invalida`` con «Un número mayor que 0, en kg, con hasta 2 decimales.» si falta, es 0, negativa, no
        es un número, tiene más de dos decimales o se pasa de 999.999,99."""
        for mala in ("", "0", "0,00", "-5", "abc", "1,234", "1.234,5", "1000000", None):
            with self.subTest(capacidad=mala):
                errores = errores_de(self, lambda: self.alta(capacidad_carga=mala))
                self.assertEqual(codigos(errores, "capacidad_carga"), ["capacidad_invalida"])
        self.assertEqual(errores["capacidad_carga"][0].messages, ["Un número mayor que 0, en kg, con hasta 2 decimales."])

    def test_pre_b_junta_todos_los_errores_en_un_solo_rechazo(self):
        """Patrón ABM, sección 2, paso 2: un solo ``ValidationError`` con un error por campo, todos a la vez."""
        errores = errores_de(self, lambda: self.alta(patente="x", tipo_vehiculo="", marca="", capacidad_carga="0"))
        self.assertEqual(set(errores), {"patente", "tipo_vehiculo", "marca", "capacidad_carga"})
        self.assertFalse(Vehiculo.objects.exists())

    # -- regla 4, 5 y postcondición b (transportista) --

    def test_regla_5_sin_transportista_el_vehiculo_se_crea_y_no_se_notifica_a_nadie(self):
        """Regla 5: el transportista es opcional; sin transportista no participa de ninguna planificación y no hay aviso."""
        creado = self.alta(transportista_id="")
        self.assertIsNone(creado.transportista_id)
        self.assertFalse(Notificacion.objects.exists())

    def test_post_b_asigna_el_transportista_y_le_avisa(self):
        """Postcondición b y notificaciones: el transportista queda asociado y recibe «Tenés un vehículo asignado»."""
        transportista = crear_transportista()
        creado = self.alta(transportista_id=transportista.pk)
        self.assertEqual(Vehiculo.objects.get(pk=creado.pk).transportista_id, transportista.pk)
        aviso = Notificacion.objects.get(destinatario=transportista)
        self.assertEqual(aviso.titulo, "Tenés un vehículo asignado")
        self.assertEqual(aviso.detalle, "Desde ahora hacés tus entregas con camioneta AE123CD (800 kg).")
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_regla_4_un_transportista_sin_invernadero_se_puede_asignar(self):
        """Regla 4 («Transportista»): un Transportista sin invernadero se puede asignar (el aviso es de la pantalla)."""
        transportista = crear_transportista()  # sin ``TransportistaInvernadero``
        self.assertEqual(self.alta(transportista_id=transportista.pk).transportista_id, transportista.pk)

    def test_regla_4_el_transportista_tiene_que_ser_un_transportista_activo(self):
        """Regla 4: solo transportistas activos; una cuenta inactiva, de otro rol, inexistente o mal formada es
        ``transportista_invalido``."""
        casos = (
            crear_transportista("inactivo@infoponia.com", activo=False).pk,
            crear_agronomo().pk,
            999999,
            "abc",
        )
        for pk in casos:
            with self.subTest(transportista_id=pk):
                errores = errores_de(self, lambda: self.alta(transportista_id=pk))
                self.assertEqual(codigos(errores, "transportista"), ["transportista_invalido"])
        self.assertFalse(Vehiculo.objects.exists())

    def test_regla_4_un_transportista_con_otro_vehiculo_no_se_ofrece_ni_se_acepta(self):
        """Regla 4 y R073: ``transportista_con_vehiculo`` si ya tiene otro vehículo."""
        transportista = crear_transportista()
        vehiculo(transportista=transportista)
        errores = errores_de(self, lambda: self.alta(patente="ABC123", transportista_id=transportista.pk))
        self.assertEqual(codigos(errores, "transportista"), ["transportista_con_vehiculo"])
        self.assertEqual(Vehiculo.objects.count(), 1)
        self.assertEqual(Notificacion.objects.count(), 0)

    # -- postcondición c (auditoría) --

    def test_post_c_audita_el_alta_con_el_vehiculo_y_la_cuenta_del_transportista(self):
        """Postcondición c y D-36: ``alta_vehiculo`` con usuario, afectados (el vehículo y el transportista) y los datos cargados
        con «antes» nulo; la capacidad, como texto con dos decimales («800,00»); el transportista, como referencia."""
        transportista = crear_transportista(nombre="Diego", apellido="Ferreyra")
        creado = self.alta(transportista_id=transportista.pk)
        registro = RegistroAuditoria.objects.get(accion="alta_vehiculo")
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.afectados[0]["id"], creado.pk)
        self.assertIn(transportista.pk, [afectado["id"] for afectado in registro.afectados])
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["patente"], {"antes": None, "despues": "AE123CD"})
        self.assertEqual(cambios["tipo_vehiculo"], {"antes": None, "despues": "camioneta"})
        self.assertEqual(cambios["marca"], {"antes": None, "despues": "Ford"})
        self.assertEqual(cambios["modelo"], {"antes": None, "despues": "Ranger"})
        self.assertEqual(cambios["capacidad_carga"], {"antes": None, "despues": "800,00"})
        self.assertEqual(cambios["estado"], {"antes": None, "despues": "activo"})
        self.assertEqual(cambios["transportista"]["antes"], None)
        self.assertEqual(cambios["transportista"]["despues"]["id"], transportista.pk)

    def test_post_c_sin_transportista_no_figura_en_el_alta(self):
        """Postcondición c: sin transportista no hay cuenta afectada ni cambio de transportista."""
        creado = self.alta()
        registro = RegistroAuditoria.objects.get(accion="alta_vehiculo")
        self.assertEqual([afectado["id"] for afectado in registro.afectados], [creado.pk])
        self.assertNotIn("transportista", registro.detalle["cambios"])

    def test_post_c_un_rechazo_no_deja_registro(self):
        """D-22: si el alta falla, no queda registro."""
        errores_de(self, lambda: self.alta(patente="x"))
        self.assertFalse(RegistroAuditoria.objects.filter(accion="alta_vehiculo").exists())


class DatosDeVehiculoDesdePostTests(SimpleTestCase):
    """``DatosDeVehiculo.desde_post(post)``."""

    def test_arma_los_datos_del_formulario(self):
        """Los campos por su nombre; ``transportista`` (id) vacío es sin transportista."""
        post = QueryDict("patente=ae-123+cd&tipo_vehiculo=furgon&marca=Fiat&modelo=Ducato&capacidad_carga=1.250%2C25&transportista_id=7")
        datos = DatosDeVehiculo.desde_post(post)
        self.assertEqual(
            (datos.patente, datos.tipo_vehiculo, datos.marca, datos.modelo, datos.capacidad_carga, datos.transportista_id),
            ("ae-123 cd", "furgon", "Fiat", "Ducato", "1.250,25", "7"),
        )
        self.assertIn(DatosDeVehiculo.desde_post(QueryDict("transportista_id=")).transportista_id, ("", None))
        self.assertIn(DatosDeVehiculo.desde_post(QueryDict("")).transportista_id, ("", None))


class TextoDeCapacidadTests(SimpleTestCase):
    """``texto_capacidad(Decimal)``: lo usan la lista, la ficha, las notificaciones, «Logística» y la ficha de la cuenta."""

    def test_regla_3_kilogramos_con_coma_decimal_y_sin_ceros_de_mas(self):
        """«Texto de la capacidad»: «800 kg», «800,5 kg», «1.250,25 kg»."""
        for valor, texto in (
            (Decimal("800"), "800 kg"),
            (Decimal("800.00"), "800 kg"),
            (Decimal("800.50"), "800,5 kg"),
            (Decimal("1250.25"), "1.250,25 kg"),
            (Decimal("999999.99"), "999.999,99 kg"),
            (Decimal("0.01"), "0,01 kg"),
        ):
            with self.subTest(valor=valor):
                self.assertEqual(vehiculos.texto_capacidad(valor), texto)
