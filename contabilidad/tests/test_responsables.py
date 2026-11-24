# Pruebas de `contabilidad/servicios/responsables.py` (USR-11, D-85 punto 5): quién registra asientos y pagos. Contrato:
# docs/api/asientos.md, sección «Lectura». Cada prueba arma sus propios datos.

from django.test import TestCase

from contabilidad.servicios import responsables
from core.models import Agronomo, Capataz, Contador, Notificacion, Tecnico, Transportista, Vendedor
from core.tests.fabricas import crear_administrador, crear_cuenta, crear_gerente


class ResponsablesTests(TestCase):
    """D-85 punto 5: el Contador activo o, si no hay, el Gerente activo."""

    def test_d85_contador_activo_devuelve_el_activo(self):
        """``contador_activo`` devuelve el Contador activo, y ``None`` si no hay (los inactivos no cuentan)."""
        self.assertIsNone(responsables.contador_activo())
        crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)
        self.assertIsNone(responsables.contador_activo())
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        self.assertEqual(responsables.contador_activo().pk, contador.pk)

    def test_d85_responsable_es_el_contador_cuando_hay_uno(self):
        """D-85 punto 5: con Contador activo, él es el responsable aunque haya Gerente."""
        crear_gerente()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        self.assertEqual(responsables.responsable_contable().pk, contador.pk)

    def test_d85_sin_contador_el_responsable_es_el_gerente(self):
        """D-85 puntos 4 y 5: sin Contador activo, lo reemplaza el Gerente activo."""
        gerente = crear_gerente()
        crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        self.assertEqual(responsables.responsable_contable().pk, gerente.pk)

    def test_d85_sin_ninguno_no_hay_responsable(self):
        """D-85 punto 5: sin Contador ni Gerente activos, ``responsable_contable`` es ``None``."""
        crear_gerente(activo=False)

        self.assertIsNone(responsables.responsable_contable())

    def test_d85_puede_registrar_el_contador_activo_y_no_el_gerente(self):
        """D-85 punto 5: con Contador activo solo él registra; el Gerente no."""
        gerente = crear_gerente()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        self.assertTrue(responsables.puede_registrar_asientos(contador))
        self.assertFalse(responsables.puede_registrar_asientos(gerente))

    def test_d85_puede_registrar_el_gerente_sin_contador_activo(self):
        """D-85 punto 5: sin Contador activo, el Gerente activo registra; un Contador inactivo no."""
        gerente = crear_gerente()
        inactivo = crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        self.assertTrue(responsables.puede_registrar_asientos(gerente))
        self.assertFalse(responsables.puede_registrar_asientos(inactivo))

    def test_d85_ningun_otro_rol_puede_registrar(self):
        """D-85 punto 8: ni el Vendedor ni ningún otro rol ni el Administrador registran asientos, haya o no Contador."""
        crear_gerente()
        crear_cuenta(Contador, email="contador@infoponia.com")
        otros = [
            crear_cuenta(clase, email=f"{clase.__name__.lower()}@infoponia.com")
            for clase in (Agronomo, Capataz, Vendedor, Transportista, Tecnico)
        ]
        otros.append(crear_administrador())

        for cuenta in otros:
            with self.subTest(cuenta=cuenta.email):
                self.assertFalse(responsables.puede_registrar_asientos(cuenta))

    def test_d85_otros_roles_tampoco_registran_sin_contador(self):
        """D-85 punto 8: aunque no haya Contador, solo el Gerente lo reemplaza; el Vendedor no."""
        crear_gerente()
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")

        self.assertFalse(responsables.puede_registrar_asientos(vendedor))

    def test_d85_puede_registrar_rechaza_none_y_cuenta_que_se_desactivo(self):
        """``None`` no registra; una instancia vieja de un Contador que ya se dio de baja tampoco (se consulta la base)."""
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        gerente = crear_gerente()
        Contador.objects.filter(pk=contador.pk).update(is_active=False)

        self.assertFalse(responsables.puede_registrar_asientos(None))
        self.assertFalse(responsables.puede_registrar_asientos(contador))
        self.assertTrue(responsables.puede_registrar_asientos(gerente))

    def test_d85_notifica_al_contador_y_respeta_excluir(self):
        """D-85 puntos 5 y 7: la notificación va al responsable; si el responsable es ``excluir`` (el actor), no se crea."""
        crear_gerente()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        creada = responsables.notificar_al_responsable_contable("Título", "Detalle")
        self.assertEqual(creada.destinatario_id, contador.pk)
        self.assertEqual(Notificacion.objects.count(), 1)

        omitida = responsables.notificar_al_responsable_contable("Otro", "Detalle", excluir=contador)
        self.assertIsNone(omitida)
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_d85_notifica_al_gerente_sin_contador(self):
        """D-85 punto 4: sin Contador activo, el aviso va al Gerente."""
        gerente = crear_gerente()

        creada = responsables.notificar_al_responsable_contable("Título", "Detalle")

        self.assertEqual(creada.destinatario_id, gerente.pk)

    def test_d85_sin_responsable_no_falla_ni_notifica(self):
        """D-14 y D-85 punto 5: sin responsable no hace nada ni falla, pero un texto vacío sigue siendo error de uso."""
        self.assertIsNone(responsables.notificar_al_responsable_contable("Título", "Detalle"))
        self.assertEqual(Notificacion.objects.count(), 0)
        with self.assertRaises(ValueError):
            responsables.notificar_al_responsable_contable("", "Detalle")
