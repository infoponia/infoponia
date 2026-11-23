# Pruebas de la API pública de direcciones de `maestros` (COM-01, paso 2; D-58 y docs/api/direcciones.md): validar, crear,
# corregir en el lugar, inactivar, borrar, ``datos_de_la_direccion`` y ``clave_de_ubicacion``. Los mensajes y los códigos de
# error son los mismos que ya da el alta del invernadero (D-39).

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from maestros.models import Direccion, DireccionRural, DireccionUrbana, Invernadero
from maestros.servicios import direcciones
from maestros.servicios.direcciones import DireccionValidada
from maestros.tests.fabricas import ConGeoref, crear_invernadero, localidad


def urbana(**extra):
    """Datos válidos de una dirección urbana (los nombres son los del formulario del invernadero)."""
    datos = {"tipo_direccion": "urbana", "calle": "San Martín", "numero_calle": "123", "localidad": localidad().pk}
    datos.update(extra)
    return datos


def rural(**extra):
    """Datos válidos de una dirección rural."""
    datos = {"tipo_direccion": "rural", "ruta": "Ruta 12", "kilometro": "1034,5", "localidad": localidad().pk}
    datos.update(extra)
    return datos


class ValidarDireccionTests(ConGeoref, TestCase):
    """``validar_direccion(datos) -> DireccionValidada`` (docs/api/direcciones.md, «Funciones»)."""

    def errores(self, datos):
        """Los errores por campo (``{campo: [códigos]}``) que lanza ``validar_direccion``."""
        with self.assertRaises(ValidationError) as contexto:
            direcciones.validar_direccion(datos)
        return {campo: [e.code for e in lista] for campo, lista in contexto.exception.error_dict.items()}

    def test_d58_urbana_valida_devuelve_zona_localidad_y_campos_limpios(self):
        """D-58 punto 3: una urbana válida; los textos se recortan y los datos de la zona rural se descartan."""
        validada = direcciones.validar_direccion(
            urbana(calle="  San Martín ", piso=" 2 ", ruta="Ruta 12", kilometro="5", lote_rural="L1")
        )
        self.assertIsInstance(validada, DireccionValidada)
        self.assertEqual(validada.zona, "urbana")
        self.assertEqual(validada.localidad, localidad())
        self.assertEqual(
            validada.campos,
            {
                "calle": "San Martín",
                "numero_calle": "123",
                "piso": "2",
                "departamento_unidad": "",
                "barrio": "",
                "referencias": "",
            },
        )

    def test_d58_rural_valida_descarta_los_datos_de_la_urbana(self):
        """D-58 punto 3: una rural válida con ``lote_rural`` opcional; los datos de la urbana se descartan."""
        validada = direcciones.validar_direccion(rural(calle="San Martín", numero_calle="1"))
        self.assertEqual(validada.zona, "rural")
        self.assertEqual(validada.campos, {"ruta": "Ruta 12", "kilometro": "1034,5", "lote_rural": ""})

    def test_regla_2_de_prod_alt_inv_el_tipo_es_obligatorio_y_valido(self):
        """Regla 2 de PROD-ALT-INV: ``tipo_invalido`` si no es urbana ni rural."""
        for tipo in ("", "otra", None):
            with self.subTest(tipo=tipo):
                self.assertEqual(self.errores(urbana(tipo_direccion=tipo))["tipo_direccion"], ["tipo_invalido"])

    def test_regla_2_de_prod_alt_inv_cada_obligatorio_de_la_urbana(self):
        """Regla 2 de PROD-ALT-INV: la calle y el número son obligatorios (``obligatorio``)."""
        for campo in ("calle", "numero_calle"):
            with self.subTest(campo=campo):
                self.assertEqual(self.errores(urbana(**{campo: "   "}))[campo], ["obligatorio"])

    def test_regla_2_de_prod_alt_inv_cada_obligatorio_de_la_rural(self):
        """Regla 2 de PROD-ALT-INV: la ruta y el kilómetro son obligatorios."""
        for campo in ("ruta", "kilometro"):
            with self.subTest(campo=campo):
                self.assertEqual(self.errores(rural(**{campo: ""}))[campo], ["obligatorio"])

    def test_d39_formatos_invalidos_con_su_codigo(self):
        """D-39: número de calle, kilómetro y textos sin contenido, con el código del validador."""
        self.assertEqual(self.errores(urbana(numero_calle="abc"))["numero_calle"], ["numero_calle_formato"])
        self.assertEqual(self.errores(rural(kilometro="4.5"))["kilometro"], ["kilometro_formato"])
        for campo in ("calle", "piso", "departamento_unidad", "barrio", "referencias"):
            with self.subTest(campo=campo):
                self.assertEqual(self.errores(urbana(**{campo: "---"}))[campo], ["sin_contenido"])
        for campo in ("ruta", "lote_rural"):
            with self.subTest(campo=campo):
                self.assertEqual(self.errores(rural(**{campo: "---"}))[campo], ["sin_contenido"])

    def test_d39_largo_excedido_con_demasiado_largo(self):
        """D-39: pasarse del largo de la columna es ``demasiado_largo``, no un 500."""
        self.assertEqual(self.errores(urbana(calle="a" * 101))["calle"], ["demasiado_largo"])
        self.assertEqual(self.errores(rural(ruta="a" * 101))["ruta"], ["demasiado_largo"])
        self.assertEqual(self.errores(urbana(referencias="a" * 201))["referencias"], ["demasiado_largo"])

    def test_regla_3_de_prod_alt_inv_la_localidad_tiene_que_existir(self):
        """Regla 3 de PROD-ALT-INV y MD-88: ``localidad_invalida`` si falta, no es un número o no existe."""
        for valor in ("", None, "abc", 999999999):
            with self.subTest(localidad=valor):
                self.assertEqual(self.errores(urbana(localidad=valor))["localidad"], ["localidad_invalida"])

    def test_d58_junta_todos_los_errores(self):
        """Patrón ABM, paso 2: un solo ``ValidationError`` con un error por campo, todos a la vez."""
        errores = self.errores({"tipo_direccion": "urbana", "calle": "", "numero_calle": "", "localidad": ""})
        self.assertEqual(set(errores), {"calle", "numero_calle", "localidad"})

    def test_d58_acepta_provincia_y_departamento_sin_usarlos(self):
        """API de direcciones: ``provincia`` y ``departamento`` sirven solo para filtrar la lista; no molestan."""
        validada = direcciones.validar_direccion(urbana(provincia="1", departamento="2"))
        self.assertEqual(validada.zona, "urbana")

    def test_d58_no_escribe_en_la_base(self):
        """API de direcciones: ``validar_direccion`` valida sin tocar la base (salvo leer la localidad)."""
        direcciones.validar_direccion(urbana())
        self.assertFalse(Direccion.objects.exists())


class CrearCorregirInactivarYBorrarTests(ConGeoref, TestCase):
    """``crear_direccion``, ``corregir_direccion``, ``inactivar_direccion`` y ``borrar_direccion``."""

    def crear(self, datos):
        return direcciones.crear_direccion(direcciones.validar_direccion(datos))

    def test_d58_crea_una_urbana_activa(self):
        """D-58 punto 3: la urbana nace activa, con la localidad y sus datos."""
        hija = self.crear(urbana(piso="2", departamento_unidad="B", barrio="Centro", referencias="Frente a la plaza"))
        self.assertIsInstance(hija, DireccionUrbana)
        hija.refresh_from_db()
        self.assertEqual(hija.estado_direccion, Direccion.Estado.ACTIVO)
        self.assertEqual(hija.localidad, localidad())
        self.assertEqual(
            (hija.calle, hija.numero_calle, hija.piso, hija.departamento, hija.barrio, hija.referencias),
            ("San Martín", "123", "2", "B", "Centro", "Frente a la plaza"),
        )

    def test_d58_crea_una_rural_activa(self):
        """D-58 punto 3: la rural nace activa; ``lote_rural`` se guarda en ``lote``."""
        hija = self.crear(rural(lote_rural="L7"))
        self.assertIsInstance(hija, DireccionRural)
        hija.refresh_from_db()
        self.assertEqual((hija.ruta, hija.kilometro, hija.lote), ("Ruta 12", "1034,5", "L7"))
        self.assertEqual(hija.estado_direccion, Direccion.Estado.ACTIVO)

    def test_d58_corrige_en_el_lugar_en_la_misma_zona(self):
        """API de direcciones: corregir cambia la misma fila (misma urbana con urbana), incluida la localidad."""
        hija = self.crear(urbana())
        otra = localidad("Posadas", "Capital", "Misiones")
        corregida = direcciones.corregir_direccion(
            hija, direcciones.validar_direccion(urbana(calle="Belgrano", numero_calle="45", localidad=otra.pk))
        )
        self.assertEqual(corregida.pk, hija.pk)
        corregida.refresh_from_db()
        self.assertEqual((corregida.calle, corregida.numero_calle, corregida.localidad), ("Belgrano", "45", otra))
        self.assertEqual(DireccionUrbana.objects.count(), 1)

    def test_d58_corrige_una_rural_en_el_lugar(self):
        """API de direcciones: lo mismo en la zona rural."""
        hija = self.crear(rural())
        direcciones.corregir_direccion(hija, direcciones.validar_direccion(rural(ruta="Ruta 14", kilometro="7")))
        hija.refresh_from_db()
        self.assertEqual((hija.ruta, hija.kilometro), ("Ruta 14", "7"))

    def test_d58_corregir_con_otra_zona_lanza_value_error_y_no_cambia_nada(self):
        """API de direcciones, «Cambio de zona»: es otra dirección; con otra zona ``corregir_direccion`` lanza ``ValueError``."""
        hija = self.crear(urbana())
        with self.assertRaises(ValueError):
            direcciones.corregir_direccion(hija, direcciones.validar_direccion(rural()))
        hija.refresh_from_db()
        self.assertEqual(hija.calle, "San Martín")
        self.assertFalse(DireccionRural.objects.exists())

    def test_d58_cambio_de_zona_crea_la_nueva_cambia_el_vinculo_y_recien_despues_borra(self):
        """API de direcciones, «Cambio de zona»: con el vínculo (aquí el invernadero) apuntando a la vieja, el PROTECT impide
        borrarla; cambiado el vínculo, se borra."""
        invernadero = crear_invernadero("Norte")
        vieja = invernadero.direccion
        nueva = self.crear(rural())
        with self.assertRaises(ProtectedError):
            direcciones.borrar_direccion(vieja)
        invernadero.direccion = nueva.direccion_ptr
        invernadero.save()
        direcciones.borrar_direccion(vieja)
        self.assertFalse(Direccion.objects.filter(pk=vieja.pk).exists())
        self.assertTrue(Direccion.objects.filter(pk=nueva.pk).exists())

    def test_d58_inactivar_pasa_a_inactivo_y_es_idempotente(self):
        """API de direcciones: ``estado_direccion = inactivo``; si ya lo estaba, no hace nada."""
        hija = self.crear(urbana())
        direcciones.inactivar_direccion(hija)
        hija.refresh_from_db()
        self.assertEqual(hija.estado_direccion, Direccion.Estado.INACTIVO)
        direcciones.inactivar_direccion(hija)
        hija.refresh_from_db()
        self.assertEqual(hija.estado_direccion, Direccion.Estado.INACTIVO)

    def test_d58_inactivar_acepta_la_direccion_base(self):
        """API de direcciones: ``inactivar_direccion(direccion)`` sirve con la ``Direccion`` base o con la hija."""
        hija = self.crear(rural())
        direcciones.inactivar_direccion(Direccion.objects.get(pk=hija.pk))
        hija.refresh_from_db()
        self.assertEqual(hija.estado_direccion, Direccion.Estado.INACTIVO)

    def test_d58_borrar_elimina_la_hija_y_su_direccion(self):
        """API de direcciones: borra la hija y su ``Direccion``."""
        hija = self.crear(urbana())
        pk = hija.pk
        direcciones.borrar_direccion(hija)
        self.assertFalse(Direccion.objects.filter(pk=pk).exists())
        self.assertFalse(DireccionUrbana.objects.filter(pk=pk).exists())

    def test_d58_borrar_con_algo_que_la_referencia_lanza_protected_error(self):
        """API de direcciones: ``ProtectedError`` si algo la referencia (quien llama borra antes su vínculo)."""
        invernadero = crear_invernadero("Norte")
        with self.assertRaises(ProtectedError):
            direcciones.borrar_direccion(invernadero.direccion.concreta())
        self.assertTrue(Invernadero.objects.filter(pk=invernadero.pk).exists())


class DatosYClaveDeUbicacionTests(ConGeoref, TestCase):
    """``datos_de_la_direccion`` y ``clave_de_ubicacion`` (D-58 punto 6)."""

    def crear(self, datos):
        return direcciones.crear_direccion(direcciones.validar_direccion(datos))

    def test_d58_datos_de_la_direccion_urbana_con_none_en_los_vacios(self):
        """API de direcciones: los datos con los nombres del servicio y ``None`` en los vacíos."""
        self.assertEqual(
            direcciones.datos_de_la_direccion(self.crear(urbana(departamento_unidad="B"))),
            {"calle": "San Martín", "numero_calle": "123", "piso": None, "departamento_unidad": "B", "barrio": None, "referencias": None},
        )

    def test_d58_datos_de_la_direccion_rural(self):
        """API de direcciones: ``lote_rural`` es el nombre del servicio de ``DireccionRural.lote``."""
        self.assertEqual(
            direcciones.datos_de_la_direccion(self.crear(rural(lote_rural="L7"))),
            {"ruta": "Ruta 12", "kilometro": "1034,5", "lote_rural": "L7"},
        )

    def test_d58_invernaderos_sigue_exportando_datos_de_la_direccion(self):
        """API de direcciones: ``invernaderos.py`` importa la función de ``direcciones.py`` (``forms.py`` la sigue importando de ahí)."""
        from maestros.servicios import invernaderos

        self.assertIs(invernaderos.datos_de_la_direccion, direcciones.datos_de_la_direccion)

    def test_d58_la_clave_ignora_mayusculas_y_espacios(self):
        """D-58 punto 6: misma zona, localidad y ubicación, sin distinguir mayúsculas y con los espacios recortados y unificados."""
        una = self.crear(urbana(calle="San Martín", numero_calle="123", piso="2", departamento_unidad="B"))
        otra = self.crear(urbana(calle="  SAN   MARTÍN ", numero_calle="123", piso="2", departamento_unidad=" b "))
        self.assertEqual(direcciones.clave_de_ubicacion(una), direcciones.clave_de_ubicacion(otra))

    def test_d58_la_clave_ignora_barrio_y_referencias(self):
        """D-58 punto 6: el barrio y las referencias describen, no ubican."""
        una = self.crear(urbana(barrio="Centro", referencias="Frente a la plaza"))
        otra = self.crear(urbana(barrio="Norte", referencias=""))
        self.assertEqual(direcciones.clave_de_ubicacion(una), direcciones.clave_de_ubicacion(otra))

    def test_d58_la_clave_cambia_con_la_localidad(self):
        """D-58 punto 6: la misma calle en otra localidad no es idéntica."""
        una = self.crear(urbana())
        otra = self.crear(urbana(localidad=localidad("Posadas", "Capital", "Misiones").pk))
        self.assertNotEqual(direcciones.clave_de_ubicacion(una), direcciones.clave_de_ubicacion(otra))

    def test_d58_la_clave_cambia_con_cada_dato_de_ubicacion(self):
        """D-58 punto 6: calle, número, piso y departamento (urbana); ruta, kilómetro y lote (rural) forman la ubicación."""
        base = direcciones.clave_de_ubicacion(self.crear(urbana(piso="2", departamento_unidad="B")))
        for cambio in ({"calle": "Belgrano"}, {"numero_calle": "124"}, {"piso": "3"}, {"departamento_unidad": "C"}):
            with self.subTest(cambio=cambio):
                otra = self.crear(urbana(**{"piso": "2", "departamento_unidad": "B", **cambio}))
                self.assertNotEqual(direcciones.clave_de_ubicacion(otra), base)
        base_rural = direcciones.clave_de_ubicacion(self.crear(rural(lote_rural="L1")))
        for cambio in ({"ruta": "Ruta 14"}, {"kilometro": "1"}, {"lote_rural": "L2"}):
            with self.subTest(cambio=cambio):
                otra = self.crear(rural(**{"lote_rural": "L1", **cambio}))
                self.assertNotEqual(direcciones.clave_de_ubicacion(otra), base_rural)

    def test_d58_la_clave_distingue_urbana_de_rural_y_es_comparable(self):
        """D-58 punto 6: la zona es parte de la clave; la clave es una tupla comparable."""
        urbana_ = direcciones.clave_de_ubicacion(self.crear(urbana()))
        rural_ = direcciones.clave_de_ubicacion(self.crear(rural()))
        self.assertIsInstance(urbana_, tuple)
        self.assertNotEqual(urbana_, rural_)
        self.assertEqual(len({urbana_, rural_}), 2)
