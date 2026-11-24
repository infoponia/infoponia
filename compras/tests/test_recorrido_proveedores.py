# Recorrido de punta a punta de «Compras» → «Proveedores» (CMP-01): los pasos de la antigua «Verificación a mano», hechos por una prueba con el cliente de Django, en el orden en que los haría
# una persona (docs/patrones/verificacion_a_mano.md). Cada paso nombra el caso de uso y la regla que verifica. Es una sola prueba larga a propósito: lo que se verifica es que el
# flujo completo encadena bien (alta, errores, baja, reactivación, modificación, auditoría y roles), no cada regla suelta (eso lo hacen test_cmp_*.py y test_proveedores_vistas.py).

from django.test import TestCase
from django.urls import reverse

from compras.models import Proveedor
from compras.tests.fabricas import con_guiones, cuit_valido, tipo_de_insumo
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.tests.fabricas import crear_agronomo


class RecorridoDeProveedoresTests(TestCase):
    """Fuente: docs/casos_de_uso/compras/proveedores.md (CMP-ALT-PRV, CMP-MOD-PRV, CMP-BAJ-PRV y CMP-CNS-PRV), D-30 y D-36."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.nutrientes = tipo_de_insumo("Nutrientes")
        self.herramientas = tipo_de_insumo("Herramientas")
        self.vieja = tipo_de_insumo("Descontinuada")
        self.client.force_login(self.gerente)

    def datos(self, **cambios):
        datos = {
            "tipo": "juridica",
            "cuit": con_guiones(cuit_valido(1)),
            "razon_social": "Semillas del Sur S. A.",
            "email": "ventas@semillasdelsur.com",
            "telefono": "376 400-1001",
            "especialidades": [self.nutrientes.pk, self.vieja.pk],
        }
        datos.update(cambios)
        return datos

    def auditoria(self, accion):
        return RegistroAuditoria.objects.filter(accion=accion)

    def test_recorrido_completo_del_gerente_y_del_agronomo(self):
        nuevo, lista = reverse("compras:proveedor_nuevo"), reverse("compras:proveedores")

        # Paso 1 · CMP-ALT-PRV: con dos especialidades. Te lleva a la ficha con el aviso.
        respuesta = self.client.post(nuevo, self.datos(), follow=True)
        sur = Proveedor.objects.get()
        self.assertRedirects(respuesta, reverse("compras:proveedor_ficha", args=[sur.pk]))
        self.assertContains(respuesta, "Registramos a Semillas del Sur S. A.")
        self.assertEqual(sur.especialidades.count(), 2)
        self.assertEqual(self.auditoria("alta_proveedor").count(), 1)

        # Paso 2 · CMP-ALT-PRV regla 2: el mismo CUIT se rechaza junto al campo, y todos los errores vienen juntos.
        respuesta = self.client.post(nuevo, self.datos(razon_social="Otra"))
        self.assertContains(respuesta, "Ya está registrado como Semillas del Sur S. A.")
        respuesta = self.client.post(nuevo, self.datos(cuit="30-71234567-2", email="", telefono="abc"))
        for texto in ("El CUIT no es válido", "Ingresá el correo", "El teléfono solo puede tener"):
            self.assertContains(respuesta, texto)
        self.assertEqual(Proveedor.objects.count(), 1)

        # Paso 3 · CMP-ALT-PRV regla 1: una persona física con nombre y apellido.
        self.client.post(nuevo, self.datos(tipo="fisica", cuit=cuit_valido(3), razon_social="", nombre="Ana", apellido="Gómez", telefono="", especialidades=[]))
        ana = Proveedor.objects.get(cuit_proveedor=cuit_valido(3))
        self.assertEqual((str(ana), ana.telefono_proveedor), ("Ana Gómez", ""))

        # Paso 4 · CMP-BAJ-PRV: dar de baja (la ventana pide confirmar; abrirla no cambia nada).
        baja = reverse("compras:proveedor_baja", args=[sur.pk])
        self.assertContains(self.client.get(baja), "¿Dar de baja a Semillas del Sur S. A.?")
        sur.refresh_from_db()
        self.assertTrue(sur.activo)
        respuesta = self.client.post(baja, follow=True)
        self.assertRedirects(respuesta, lista)
        self.assertContains(respuesta, "Semillas del Sur S. A. quedó inactivo.")
        self.assertNotContains(respuesta, reverse("compras:proveedor_ficha", args=[sur.pk]))  # ya no está entre los activos

        # Paso 5 · CMP-ALT-PRV regla 2 y post. c: volver a cargar su CUIT ofrece reactivarlo; reactivar con los datos nuevos no crea un segundo proveedor.
        respuesta = self.client.post(nuevo, self.datos(email="nuevo@semillasdelsur.com"))
        self.assertContains(respuesta, "Reactivar con estos datos")
        self.assertEqual(Proveedor.objects.filter(cuit_proveedor=cuit_valido(1)).count(), 1)
        respuesta = self.client.post(nuevo, {**self.datos(email="nuevo@semillasdelsur.com"), "reactivar_id": sur.pk}, follow=True)
        self.assertRedirects(respuesta, reverse("compras:proveedor_ficha", args=[sur.pk]))
        sur.refresh_from_db()
        self.assertEqual((sur.estado_proveedor, sur.email_proveedor), ("activo", "nuevo@semillasdelsur.com"))

        # Paso 6 · Reactivar desde la ficha de un inactivo: el formulario trae sus datos con el CUIT fijo.
        self.client.post(reverse("compras:proveedor_baja", args=[ana.pk]))
        reactivar = reverse("compras:proveedor_reactivar", args=[ana.pk])
        self.assertContains(self.client.get(reactivar), "El CUIT identifica al proveedor")
        self.client.post(reactivar, {"nombre": "Ana", "apellido": "Gómez", "email": "ana@mail.com", "telefono": ""}, follow=True)
        ana.refresh_from_db()
        self.assertEqual((ana.estado_proveedor, ana.email_proveedor), ("activo", "ana@mail.com"))

        # Paso 7 · CMP-MOD-PRV: modificar; sin cambios no se audita (D-28).
        editar = reverse("compras:proveedor_editar", args=[ana.pk])
        cambios = self.auditoria("modificacion_proveedor").count()
        self.client.post(editar, {"cuit": con_guiones(ana.cuit_proveedor), "nombre": "Ana", "apellido": "Gómez", "email": "ana@mail.com", "telefono": ""})
        self.assertEqual(self.auditoria("modificacion_proveedor").count(), cambios)
        self.client.post(editar, {"cuit": con_guiones(ana.cuit_proveedor), "nombre": "Ana", "apellido": "Gómez", "email": "ana.gomez@mail.com", "telefono": "376 400-2002"})
        self.assertEqual(self.auditoria("modificacion_proveedor").count(), cambios + 1)

        # Paso 8 · CMP-MOD-PRV regla 4: la categoría dada de baja no se ve ni se ofrece, pero su vínculo se conserva al modificar.
        self.vieja.estado_tipo_insumo = "inactivo"
        self.vieja.save()
        ficha = self.client.get(reverse("compras:proveedor_ficha", args=[sur.pk]))
        self.assertContains(ficha, "Nutrientes")
        self.assertNotContains(ficha, "Descontinuada")
        editar_sur = reverse("compras:proveedor_editar", args=[sur.pk])
        self.assertNotContains(self.client.get(editar_sur), "Descontinuada")
        self.client.post(editar_sur, self.datos(especialidades=[self.nutrientes.pk, self.herramientas.pk], email="nuevo@semillasdelsur.com"))
        self.assertEqual(set(sur.especialidades.all()), {self.nutrientes, self.herramientas, self.vieja})

        # Paso 9 · CMP-CNS-PRV regla 2: filtros por estado, texto (con o sin guiones) y categoría.
        self.assertContains(self.client.get(lista, {"q": cuit_valido(1)}), "Semillas del Sur S. A.")
        self.assertContains(self.client.get(lista, {"q": con_guiones(cuit_valido(1))}), "Semillas del Sur S. A.")
        self.assertNotContains(self.client.get(lista, {"categoria": self.herramientas.pk}), "Ana Gómez")
        self.assertContains(self.client.get(lista, {"categoria": self.herramientas.pk}), "Semillas del Sur S. A.")

        # Paso 10 · D-36: «Auditoría» muestra las acciones nuevas con nombres legibles.
        pantalla = self.client.get(reverse("core:auditoria"))
        for texto in ("Alta de proveedor", "Baja de proveedor", "Reactivación de proveedor", "Modificación de proveedor"):
            self.assertContains(pantalla, texto)
        registro = self.auditoria("modificacion_proveedor").latest("id")
        detalle = self.client.get(reverse("core:auditoria_registro", args=[registro.pk]))
        self.assertContains(detalle, "Categorías de insumos")

        # Paso 11 · CMP-CNS-PRV regla 5: el Agrónomo consulta y no ve botones de cambio; escribir da 403.
        self.client.post(reverse("compras:proveedor_baja", args=[ana.pk]))  # un inactivo, para ver también ese estado
        inactivo = Proveedor.objects.get(pk=ana.pk)
        self.client.force_login(self.agronomo)
        for proveedor_visto in (sur, inactivo):
            ficha = self.client.get(reverse("compras:proveedor_ficha", args=[proveedor_visto.pk]))
            self.assertEqual(ficha.status_code, 200)
            for ruta in ("proveedor_editar", "proveedor_baja", "proveedor_reactivar"):
                self.assertNotContains(ficha, reverse(f"compras:{ruta}", args=[proveedor_visto.pk]))
        self.assertContains(self.client.get(lista, {"estado": ""}), "Ana Gómez")
        for ruta in (nuevo, editar_sur, baja):
            self.assertEqual(self.client.get(ruta).status_code, 403)
        self.assertEqual(self.client.post(nuevo, self.datos(cuit=cuit_valido(9))).status_code, 403)
        self.assertFalse(Proveedor.objects.filter(cuit_proveedor=cuit_valido(9)).exists())
