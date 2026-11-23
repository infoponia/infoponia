# Pruebas de COM-ALT-CLT, Alta Cliente, con su reactivación (COM-01, paso 3; docs/casos_de_uso/comercial/clientes.md): el alta, el
# CUIT repetido (activo o inactivo), el tipo de cliente, el teléfono, el correo, las direcciones (con la dirección idéntica y C6),
# la reactivación con el aviso al Gerente y la auditoría. ``DatosDeCliente.desde_post`` también.
#
# Contrato que fijan estas pruebas (lo revisa el estudiante antes de implementar):
#   - ``DatosDeCliente(tipo_cliente, cuit, razon_social="", nombre="", apellido="", telefono="", email="",
#     direcciones_nuevas=[dict], direcciones_corregidas=[(direccion_id, dict)], direcciones_desactivadas=[direccion_id],
#     direcciones_borradas=[direccion_id])``; cada dirección es el dict de ``maestros.servicios.direcciones.validar_direccion``.
#   - Errores por campo: ``tipo_cliente``, ``cuit``, ``razon_social``, ``nombre``, ``apellido``, ``telefono``, ``email`` y, para las
#     direcciones, ``nueva-<i>-<campo>`` y ``nueva-<i>`` (``direccion_repetida``). El error de CUIT repetido lleva el id en
#     ``error.params["cliente_id"]``.

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, QueryDict
from django.test import TestCase

from comercial.models import Cliente, DireccionCliente
from comercial.servicios import clientes
from comercial.servicios.clientes import DatosDeCliente
from comercial.tests.fabricas import CUIT_VALIDO, cliente, datos_de_cliente, datos_de_cliente_de, datos_de_direccion
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.models import Direccion
from maestros.tests.fabricas import (
    ConGeoref,
    crear_agronomo,
    crear_invernadero,
    crear_transportista,
    crear_vendedor,
    localidad,
)


def errores_de(prueba, llamada):
    """Ejecuta ``llamada`` y devuelve los errores que lanza como ``{campo: [ValidationError]}``."""
    with prueba.assertRaises(ValidationError) as contexto:
        llamada()
    return contexto.exception.error_dict


def codigos(errores, campo):
    """Los códigos del campo ``campo`` de un ``error_dict``."""
    return [e.code for e in errores.get(campo, [])]


class ComAltCltServicioTests(ConGeoref, TestCase):
    """``alta_cliente(actor, datos)``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor()

    def alta(self, actor=None, **extra):
        return clientes.alta_cliente(actor or self.vendedor, datos_de_cliente(**extra))

    # -- precondición a --

    def test_pre_a_el_vendedor_y_el_gerente_activos_pueden(self):
        """Precondición a: el actor es un Vendedor o un Gerente con la cuenta activa."""
        for cuit, actor in (("30712345671", self.vendedor), ("30000000090", self.gerente)):
            with self.subTest(rol=actor.rol):
                self.assertTrue(self.alta(actor, cuit=cuit).pk)
        self.assertEqual(Cliente.objects.count(), 2)

    def test_pre_a_otros_roles_cuentas_inactivas_y_anonimos_reciben_permission_denied(self):
        """Precondición a: cualquier otro rol, una cuenta inactiva o ``None`` no puede; no se crea nada."""
        inactivo = crear_vendedor("inactivo@infoponia.com", activo=False)
        for actor in (crear_agronomo(), crear_transportista(), inactivo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                clientes.alta_cliente(actor, datos_de_cliente())
        self.assertFalse(Cliente.objects.exists())

    # -- postcondición a y regla 1 (CUIT) --

    def test_post_a_crea_un_cliente_activo_con_sus_datos(self):
        """Postcondición a: cliente «activo» con su CUIT, su nombre y los datos de contacto."""
        creado = self.alta(telefono="+54 376 400-1001", email="compras@pinos.com")
        creado.refresh_from_db()
        self.assertEqual(creado.estado_cliente, Cliente.Estado.ACTIVO)
        self.assertEqual(creado.tipo_cliente, "juridica")
        self.assertEqual(creado.razon_social_cliente, "Verdulería Los Pinos S.R.L.")
        self.assertEqual((creado.telefono_cliente, creado.email_cliente), ("+54 376 400-1001", "compras@pinos.com"))
        self.assertEqual(creado.direcciones.count(), 0)

    def test_regla_1_el_cuit_se_acepta_con_o_sin_guiones_y_se_guarda_sin_ellos(self):
        """Regla 1: se acepta con o sin guiones; se guarda sin guiones."""
        for escrito in ("30-71234567-1", "30712345671", " 30 71234567 1 "):
            with self.subTest(escrito=escrito):
                Cliente.objects.filter(cuit_cliente="30712345671").delete()  # cada escritura crea el mismo cliente
                self.assertEqual(self.alta(cuit=escrito).cuit_cliente, "30712345671")

    def test_regla_1_el_cuit_es_obligatorio_y_con_digito_verificador(self):
        """Regla 1: obligatorio (``obligatorio``) y válido, con módulo 11 (``cuit_invalido``)."""
        self.assertEqual(codigos(errores_de(self, lambda: self.alta(cuit="")), "cuit"), ["obligatorio"])
        for malo in ("30-71234567-2", "3071234567", "abc", "11111111111"):
            with self.subTest(cuit=malo):
                self.assertEqual(codigos(errores_de(self, lambda: self.alta(cuit=malo)), "cuit"), ["cuit_invalido"])
        self.assertFalse(Cliente.objects.exists())

    def test_regla_2_el_cuit_de_un_cliente_activo_se_rechaza_con_su_id_para_abrir_su_ficha(self):
        """Regla 2: ``cuit_de_cliente_activo``; el error lleva el id del cliente para ofrecer «Abrir su ficha»."""
        existente = cliente(cuit="30712345671")
        errores = errores_de(self, lambda: self.alta(cuit="30-71234567-1"))
        self.assertEqual(codigos(errores, "cuit"), ["cuit_de_cliente_activo"])
        self.assertEqual(errores["cuit"][0].params["cliente_id"], existente.pk)
        self.assertEqual(Cliente.objects.count(), 1)

    def test_regla_2_el_cuit_de_un_cliente_inactivo_se_rechaza_con_su_id_para_reactivarlo(self):
        """Regla 2 (MD-48): ``cuit_de_cliente_inactivo`` con el id, para ofrecer «Reactivarlo»; no se crea otro."""
        existente = cliente(cuit="30712345671", activo=False)
        errores = errores_de(self, lambda: self.alta())
        self.assertEqual(codigos(errores, "cuit"), ["cuit_de_cliente_inactivo"])
        self.assertEqual(errores["cuit"][0].params["cliente_id"], existente.pk)
        self.assertEqual(Cliente.objects.count(), 1)

    # -- regla 3 (tipo), 4 (teléfono), 5 (correo) --

    def test_regla_3_el_tipo_tiene_que_ser_juridica_o_fisica(self):
        """Regla 3: ``tipo_invalido`` si no es persona jurídica ni física."""
        for tipo in ("", "otra", None):
            with self.subTest(tipo=tipo):
                self.assertEqual(codigos(errores_de(self, lambda: self.alta(tipo_cliente=tipo)), "tipo_cliente"), ["tipo_invalido"])

    def test_regla_3_la_juridica_exige_razon_social_y_la_fisica_nombre_y_apellido(self):
        """Regla 3: en la jurídica, la razón social; en la física, el nombre y el apellido (``obligatorio``)."""
        self.assertEqual(codigos(errores_de(self, lambda: self.alta(razon_social="  ")), "razon_social"), ["obligatorio"])
        errores = errores_de(self, lambda: self.alta(tipo_cliente="fisica", razon_social="", nombre="", apellido=" "))
        self.assertEqual((codigos(errores, "nombre"), codigos(errores, "apellido")), (["obligatorio"], ["obligatorio"]))

    def test_regla_3_se_conservan_solo_los_datos_del_tipo_elegido(self):
        """Regla 3 y modelo: los datos del otro tipo se vacían al guardar (la restricción de la base lo exige)."""
        juridica = self.alta(nombre="Marta", apellido="Gómez")
        self.assertEqual((juridica.nombre_cliente, juridica.apellido_cliente), ("", ""))
        fisica = self.alta(tipo_cliente="fisica", cuit="20-12345678-6", razon_social="Pinos SRL", nombre="Marta", apellido="Gómez")
        self.assertEqual((fisica.razon_social_cliente, fisica.nombre_cliente, fisica.apellido_cliente), ("", "Marta", "Gómez"))
        self.assertEqual(str(fisica), "Marta Gómez")

    def test_regla_4_el_telefono_es_opcional_y_sigue_el_formato_de_d21(self):
        """Regla 4: opcional; con otro formato, ``telefono_formato``; con pocos dígitos, ``telefono_digitos``."""
        self.assertTrue(self.alta(telefono="").pk)
        self.assertEqual(codigos(errores_de(self, lambda: self.alta(cuit="30000000090", telefono="abc")), "telefono"), ["telefono_formato"])
        self.assertEqual(codigos(errores_de(self, lambda: self.alta(cuit="30000000090", telefono="123")), "telefono"), ["telefono_digitos"])

    def test_regla_5_el_correo_es_opcional_y_valido(self):
        """Regla 5: opcional; con formato inválido, ``invalid`` (el validador de correo de Django)."""
        self.assertEqual(self.alta(email="").email_cliente, "")
        self.assertEqual(codigos(errores_de(self, lambda: self.alta(cuit="30000000090", email="sin-arroba")), "email"), ["invalid"])

    def test_d28_los_textos_se_recortan_y_no_pasan_del_largo_de_la_columna(self):
        """Modelo («Convenciones»): los textos se guardan recortados; pasarse del largo es ``demasiado_largo``, no un 500."""
        self.assertEqual(self.alta(razon_social="  Los Pinos  ").razon_social_cliente, "Los Pinos")
        self.assertEqual(codigos(errores_de(self, lambda: self.alta(cuit="30000000090", razon_social="a" * 151)), "razon_social"), ["demasiado_largo"])
        errores = errores_de(self, lambda: self.alta(cuit="30000000090", tipo_cliente="fisica", nombre="a" * 81, apellido="b" * 81))
        self.assertEqual((codigos(errores, "nombre"), codigos(errores, "apellido")), (["demasiado_largo"], ["demasiado_largo"]))

    def test_pre_a_junta_todos_los_errores_en_un_solo_rechazo(self):
        """Patrón ABM, sección 2, paso 2: un solo ``ValidationError`` con un error por campo, todos a la vez."""
        errores = errores_de(self, lambda: self.alta(cuit="x", razon_social="", telefono="abc", email="mal"))
        self.assertEqual(set(errores), {"cuit", "razon_social", "telefono", "email"})

    def test_regla_8_un_cliente_se_da_de_alta_sin_contratos_ni_direcciones(self):
        """Regla 8 (MD-40) y regla 6 (MD-128): sin contratos y sin direcciones."""
        creado = self.alta()
        self.assertEqual(creado.direcciones.count(), 0)

    # -- regla 6 y postcondición b (direcciones) --

    def test_post_b_crea_las_direcciones_urbanas_y_rurales_activas(self):
        """Postcondición b: las direcciones, urbanas o rurales, en las localidades elegidas, «activas» y vinculadas al cliente."""
        creado = self.alta(
            direcciones_nuevas=[
                datos_de_direccion("urbana", piso="2", barrio="Centro"),
                datos_de_direccion("rural", localidad_id=localidad("Posadas", "Capital", "Misiones").pk),
            ]
        )
        vinculos = list(creado.direcciones.select_related("direccion").order_by("pk"))
        self.assertEqual(len(vinculos), 2)
        urbana, rural = (vinculo.direccion.concreta() for vinculo in vinculos)
        self.assertEqual((urbana.ZONA, urbana.calle, urbana.piso, urbana.barrio), ("urbana", "San Martín", "2", "Centro"))
        self.assertEqual((rural.ZONA, rural.ruta, rural.localidad.nombre_localidad), ("rural", "Ruta 12", "Posadas"))
        self.assertTrue(all(vinculo.direccion.estado_direccion == "activo" for vinculo in vinculos))

    def test_regla_6_los_errores_de_una_direccion_van_por_campo_con_su_posicion(self):
        """Regla 6 y PROD-ALT-INV reglas 2 y 3: ``nueva-<i>-<campo>``, con los mismos códigos que el invernadero."""
        errores = errores_de(
            self,
            lambda: self.alta(
                direcciones_nuevas=[datos_de_direccion(), datos_de_direccion(calle="", numero_calle="x", localidad_id=999999999)]
            ),
        )
        self.assertEqual(codigos(errores, "nueva-1-calle"), ["obligatorio"])
        self.assertEqual(codigos(errores, "nueva-1-numero_calle"), ["numero_calle_formato"])
        self.assertEqual(codigos(errores, "nueva-1-localidad"), ["localidad_invalida"])
        self.assertFalse(any(campo.startswith("nueva-0") for campo in errores))
        self.assertFalse(Cliente.objects.exists())
        self.assertFalse(DireccionCliente.objects.exists())

    def test_regla_6_dos_direcciones_identicas_en_el_mismo_formulario_se_rechazan(self):
        """Regla 6 y D-58 punto 6: «no dos idénticas», también entre las del mismo formulario; el error es
        ``direccion_repetida``, en el campo de la dirección repetida (la segunda), sin distinguir mayúsculas ni espacios."""
        errores = errores_de(
            self,
            lambda: self.alta(
                direcciones_nuevas=[datos_de_direccion(), datos_de_direccion(calle="  SAN   martín ", barrio="Otro")]
            ),
        )
        self.assertEqual(codigos(errores, "nueva-1"), ["direccion_repetida"])
        self.assertNotIn("nueva-0", errores)
        self.assertFalse(Cliente.objects.exists())

    def test_regla_6_misma_calle_en_otra_localidad_no_es_repetida(self):
        """D-58 punto 6: la localidad es parte de la clave."""
        otra = localidad("Posadas", "Capital", "Misiones").pk
        creado = self.alta(direcciones_nuevas=[datos_de_direccion(), datos_de_direccion(localidad_id=otra)])
        self.assertEqual(creado.direcciones.count(), 2)

    def test_c6_la_direccion_de_un_cliente_nunca_es_la_de_un_invernadero(self):
        """C6 (D-58 punto 2): ``comercial`` crea siempre una dirección nueva, aunque los datos coincidan con los de un invernadero."""
        invernadero = crear_invernadero("Norte")
        hija = invernadero.direccion.concreta()
        creado = self.alta(
            direcciones_nuevas=[datos_de_direccion("urbana", calle=hija.calle, numero_calle=hija.numero_calle, localidad_id=hija.localidad_id)]
        )
        propia = creado.direcciones.get().direccion
        self.assertNotEqual(propia.pk, invernadero.direccion_id)
        self.assertEqual(Direccion.objects.count(), 2)
        invernadero.refresh_from_db()
        self.assertFalse(DireccionCliente.objects.filter(direccion_id=invernadero.direccion_id).exists())

    # -- postcondición d (auditoría) --

    def test_post_d_audita_el_alta_con_el_cliente_y_cada_direccion_creada(self):
        """Postcondición d y D-36: un ``alta_cliente`` con usuario, afectados (cliente y direcciones) y los datos cargados con
        «antes» nulo; el CUIT, con guiones; las direcciones creadas, en ``datos``."""
        creado = self.alta(email="compras@pinos.com", direcciones_nuevas=[datos_de_direccion(), datos_de_direccion("rural")])
        registro = RegistroAuditoria.objects.get(accion="alta_cliente")
        self.assertEqual(registro.usuario_id, self.vendedor.pk)
        ids = {afectado["id"] for afectado in registro.afectados}
        self.assertEqual(ids, {creado.pk, *creado.direcciones.values_list("direccion_id", flat=True)})
        self.assertEqual(registro.afectados[0]["id"], creado.pk)
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["cuit"], {"antes": None, "despues": CUIT_VALIDO})
        self.assertEqual(cambios["tipo_cliente"], {"antes": None, "despues": "juridica"})
        self.assertEqual(cambios["razon_social"], {"antes": None, "despues": "Verdulería Los Pinos S.R.L."})
        self.assertEqual(cambios["email"], {"antes": None, "despues": "compras@pinos.com"})
        self.assertEqual(cambios["estado"], {"antes": None, "despues": "activo"})
        self.assertNotIn("telefono", cambios)  # lo que no se cargó no va
        self.assertEqual(len(registro.detalle["datos"]["direcciones_creadas"]), 2)

    def test_post_d_un_rechazo_no_deja_registro(self):
        """D-22: si el alta falla, no queda ningún registro de auditoría."""
        errores_de(self, lambda: self.alta(cuit="x"))
        self.assertFalse(RegistroAuditoria.objects.filter(accion="alta_cliente").exists())


class ComAltCltReactivacionTests(ConGeoref, TestCase):
    """``reactivar_cliente(actor, cliente_id, datos)``: parte de COM-ALT-CLT (postcondición c y regla 2), no de MOD."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor(nombre="Valeria", apellido="Ríos")
        self.inactivo = cliente(cuit="30712345671", activo=False, razon_social="Los Pinos", telefono="")

    def reactivar(self, actor=None, **extra):
        return clientes.reactivar_cliente(actor or self.vendedor, self.inactivo.pk, datos_de_cliente_de(self.inactivo, **extra))

    def test_post_c_pasa_a_activo_con_los_datos_corregidos_sin_crear_otro(self):
        """Postcondición c: el cliente inactivo pasa a «activo» con los datos corregidos, en lugar de crearse uno nuevo."""
        reactivado = self.reactivar(telefono="+54 376 400-1001", razon_social="Los Pinos S.A.")
        self.assertEqual(reactivado.pk, self.inactivo.pk)
        reactivado.refresh_from_db()
        self.assertEqual(
            (reactivado.estado_cliente, reactivado.telefono_cliente, reactivado.razon_social_cliente),
            ("activo", "+54 376 400-1001", "Los Pinos S.A."),
        )
        self.assertEqual(Cliente.objects.count(), 1)

    def test_post_c_suma_las_direcciones_nuevas_que_se_hayan_cargado(self):
        """Regla 2 y «Reactivar» (cómo se aplica): suma las direcciones nuevas del formulario."""
        reactivado = self.reactivar(direcciones_nuevas=[datos_de_direccion()])
        self.assertEqual(reactivado.direcciones.count(), 1)

    def test_regla_2_un_cliente_activo_no_se_reactiva(self):
        """Regla 2: solo se reactiva uno inactivo; con uno activo, ``cliente_no_inactivo`` y no cambia nada."""
        activo = cliente()
        with self.assertRaises(ValidationError) as contexto:
            clientes.reactivar_cliente(self.vendedor, activo.pk, datos_de_cliente_de(activo))
        self.assertEqual([e.code for e in contexto.exception.error_list], ["cliente_no_inactivo"])
        self.assertFalse(RegistroAuditoria.objects.filter(accion="reactivacion_cliente").exists())

    def test_regla_2_el_cuit_corregido_no_puede_ser_el_de_otro_cliente(self):
        """Regla 1 aplicada a la reactivación: el CUIT corregido no puede ser el de otro cliente (con su id)."""
        otro = cliente(cuit="30000000090")
        errores = errores_de(self, lambda: self.reactivar(cuit="30000000090"))
        self.assertEqual(codigos(errores, "cuit"), ["cuit_de_cliente_activo"])
        self.assertEqual(errores["cuit"][0].params["cliente_id"], otro.pk)
        self.inactivo.refresh_from_db()
        self.assertEqual(self.inactivo.estado_cliente, "inactivo")

    def test_regla_2_conservar_el_propio_cuit_no_es_repetido(self):
        """Regla 1: el CUIT del propio cliente no cuenta como repetido."""
        self.assertEqual(self.reactivar(cuit="30-71234567-1").estado_cliente, "activo")

    def test_regla_2_el_vendedor_y_el_gerente_pueden_reactivar_otros_roles_no(self):
        """Regla 2: Vendedor y Gerente pueden; cualquier otro, ``PermissionDenied``."""
        for actor in (crear_agronomo(), crear_transportista(), None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                clientes.reactivar_cliente(actor, self.inactivo.pk, datos_de_cliente_de(self.inactivo))
        self.assertEqual(self.reactivar(actor=self.gerente).estado_cliente, "activo")

    def test_regla_2_inexistente_da_404(self):
        """D-28: un id inexistente es 404."""
        with self.assertRaises(Http404):
            clientes.reactivar_cliente(self.vendedor, 999999, datos_de_cliente())

    def test_post_c_si_reactiva_un_vendedor_el_gerente_recibe_la_notificacion(self):
        """Postcondición c y regla 2 (MD-47): título «Cliente reactivado: {cliente}» y el detalle del extracto."""
        self.reactivar(actor=self.vendedor)
        aviso = Notificacion.objects.get(destinatario=self.gerente)
        self.assertEqual(aviso.titulo, "Cliente reactivado: Los Pinos")
        self.assertEqual(
            aviso.detalle,
            "Valeria Ríos reactivó al cliente Los Pinos (CUIT 30-71234567-1). Si no correspondía, podés darlo de baja desde su ficha.",
        )
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_post_c_si_reactiva_el_gerente_no_se_notifica_a_nadie(self):
        """Postcondición c: el aviso es solo cuando reactiva un Vendedor."""
        self.reactivar(actor=self.gerente)
        self.assertFalse(Notificacion.objects.exists())

    def test_post_c_sin_gerente_activo_la_reactivacion_no_falla(self):
        """D-14: sin Gerente activo el aviso se omite y la reactivación no falla."""
        self.gerente.is_active = False
        self.gerente.save()
        self.assertEqual(self.reactivar(actor=self.vendedor).estado_cliente, "activo")
        self.assertFalse(Notificacion.objects.exists())

    def test_post_d_audita_la_reactivacion_con_su_propia_accion(self):
        """Postcondición d y D-36: ``reactivacion_cliente`` con el cambio de estado, los datos corregidos y las direcciones creadas."""
        self.reactivar(telefono="+54 376 400-1001", direcciones_nuevas=[datos_de_direccion()])
        registro = RegistroAuditoria.objects.get(accion="reactivacion_cliente")
        self.assertEqual(registro.usuario_id, self.vendedor.pk)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "inactivo", "despues": "activo"})
        self.assertEqual(registro.detalle["cambios"]["telefono"], {"antes": "", "despues": "+54 376 400-1001"})
        self.assertEqual(len(registro.detalle["datos"]["direcciones_creadas"]), 1)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_cliente").exists())

    def test_regla_2_los_errores_de_datos_dejan_al_cliente_inactivo(self):
        """Regla 2: si el formulario tiene errores no se reactiva nada."""
        errores_de(self, lambda: self.reactivar(telefono="abc"))
        self.inactivo.refresh_from_db()
        self.assertEqual(self.inactivo.estado_cliente, "inactivo")


class DatosDeClienteDesdePostTests(TestCase):
    """``DatosDeCliente.desde_post(post)``: arma los datos del formulario (el nombre de cada campo es el de la pantalla)."""

    def test_arma_los_datos_del_cliente(self):
        """Los campos simples: ``tipo_cliente``, ``cuit``, ``razon_social``, ``nombre``, ``apellido``, ``telefono`` y ``email``."""
        post = QueryDict("tipo_cliente=fisica&cuit=20-12345678-6&nombre=Marta&apellido=G%C3%B3mez&telefono=1&email=a%40b.com")
        datos = DatosDeCliente.desde_post(post)
        self.assertEqual(
            (datos.tipo_cliente, datos.cuit, datos.razon_social, datos.nombre, datos.apellido, datos.telefono, datos.email),
            ("fisica", "20-12345678-6", "", "Marta", "Gómez", "1", "a@b.com"),
        )
        self.assertEqual(
            (datos.direcciones_nuevas, datos.direcciones_corregidas, datos.direcciones_desactivadas, datos.direcciones_borradas),
            ([], [], [], []),
        )

    def test_arma_las_direcciones_nuevas_en_orden_corregidas_desactivadas_y_borradas(self):
        """``nueva-<i>-<campo>`` (por posición), ``corregida-<direccion_id>-<campo>``, ``desactivar`` y ``borrar`` (ids)."""
        post = QueryDict(
            "tipo_cliente=juridica&cuit=1&razon_social=X"
            "&nueva-1-tipo_direccion=rural&nueva-1-ruta=Ruta+12&nueva-1-kilometro=5&nueva-1-localidad=7"
            "&nueva-0-tipo_direccion=urbana&nueva-0-calle=San+Mart%C3%ADn&nueva-0-numero_calle=1&nueva-0-localidad=7"
            "&corregida-33-tipo_direccion=urbana&corregida-33-calle=Belgrano&corregida-33-localidad=7"
            "&desactivar=41&desactivar=42&borrar=50"
        )
        datos = DatosDeCliente.desde_post(post)
        self.assertEqual([d["tipo_direccion"] for d in datos.direcciones_nuevas], ["urbana", "rural"])
        self.assertEqual(datos.direcciones_nuevas[0]["calle"], "San Martín")
        self.assertEqual(datos.direcciones_nuevas[1]["ruta"], "Ruta 12")
        self.assertEqual(datos.direcciones_corregidas, [(33, {"tipo_direccion": "urbana", "calle": "Belgrano", "localidad": "7"})])
        self.assertEqual(datos.direcciones_desactivadas, [41, 42])
        self.assertEqual(datos.direcciones_borradas, [50])

    def test_ignora_ids_mal_formados(self):
        """Un id que no es un número se ignora (no rompe la pantalla)."""
        datos = DatosDeCliente.desde_post(QueryDict("desactivar=abc&borrar=&corregida-x-calle=1"))
        self.assertEqual((datos.direcciones_desactivadas, datos.direcciones_borradas, datos.direcciones_corregidas), ([], [], []))
