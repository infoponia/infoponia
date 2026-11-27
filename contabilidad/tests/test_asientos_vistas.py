# Pruebas de las pantallas del asiento manual y del contraasiento (CON-03b paso 4; CON-REG-ASI y CON-CTR-ASI, «Pantallas»; prototipo `VIEWS.k_new`, `ACT.mvadd`, `ACT.mvdel`,
# `ACT['asi-ok']`, `VIEWS.k_contra`, `ACT['contra-ok']`; D-30, D-61): acceso por rol, el formulario con filas que se agregan y se quitan (con y sin HTMX), el buscador de cuenta, los atajos,
# los errores por fila que conservan lo escrito, el resumen antes de confirmar, la precarga del asiento correcto, el contraasiento y los botones de la ficha y del libro. Con el cliente de
# Django; cada prueba arma sus datos y «hoy» es el 10/3/2027 (se fija `timezone.localdate`). Las reglas de los servicios están en `test_con_reg_asi.py` y `test_con_ctr_asi.py`.
import datetime
import html
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, CuentaContable, EjercicioContable
from contabilidad.servicios import asientos
from contabilidad.tests.fabricas import PlanDeCuentasMixin, asiento_de_prueba, ejercicio, origen_de_prueba, verificar_invariantes_contables
from core.models import Contador, Gerente, Notificacion, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
HOY = datetime.date(2027, 3, 10)
NUEVO = reverse("contabilidad:asiento_nuevo")
LIBRO = reverse("contabilidad:libro")
MOVIMIENTOS = [
    (cuentas.GASTOS_GENERALES, DEBE, Decimal("1000.00")),
    (cuentas.INSUMOS_EN_STOCK, DEBE, Decimal("500.50")),
    (cuentas.CAJA, HABER, Decimal("1500.50")),
]


def _texto(respuesta):
    return html.unescape(respuesta.content.decode())


def _etiqueta(codigo):
    cuenta = CuentaContable.objects.get(codigo_cuenta=codigo)
    return f"{cuenta.codigo_cuenta} · {cuenta.nombre_cuenta}"


def _form(descripcion="Asiento de apertura", fecha="2027-03-10", filas=None, **extra):
    """Lo que envía el formulario del asiento: por defecto, Caja al Debe y Capital Inicial al Haber por 1.000,00."""
    filas = filas if filas is not None else [(_etiqueta(cuentas.CAJA), "D", "1000,00"), (_etiqueta(cuentas.CAPITAL_INICIAL), "H", "1000,00")]
    datos = {"fecha": fecha, "descripcion": descripcion, "fila": [str(i) for i in range(len(filas))]}
    for i, (cuenta, tipo, importe) in enumerate(filas):
        datos.update({f"cuenta_{i}": cuenta, f"tipo_{i}": tipo, f"importe_{i}": importe})
    datos.update(extra)
    return datos


class VistaDeAsientosBase(PlanDeCuentasMixin, TestCase):
    """Un Contador, un Gerente, el ejercicio de 2026 «cerrado» y el de 2027 «abierto». «Hoy» es el 10/3/2027."""

    def setUp(self):
        patcher = mock.patch("django.utils.timezone.localdate", return_value=HOY)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com", nombre="Cora", apellido="Díaz")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com", nombre="Gabriela", apellido="Sosa")
        self.cerrado = ejercicio(Estado.CERRADO, datetime.date(2026, 1, 1))
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))

    def get(self, usuario, url, **parametros):
        self.client.force_login(usuario)
        return self.client.get(url, parametros)

    def post(self, usuario, url, datos, **extra):
        self.client.force_login(usuario)
        return self.client.post(url, datos, **extra)

    def mensajes(self, respuesta):
        return [str(m) for m in respuesta.context["messages"]]

    def ficha(self, asiento):
        return reverse("contabilidad:asiento", args=[asiento.ejercicio_id, asiento.numero_asiento])


class ConRegAsiVistaTests(VistaDeAsientosBase):
    """CON-REG-ASI, «Pantallas»: el formulario, el resumen y la confirmación."""

    # --- acceso (D-30) ---

    def test_regla_quien_registra_el_vendedor_recibe_403(self):
        """Solo el Contador y el Gerente entran a Contabilidad: el Vendedor recibe 403 en el formulario, en GET y en POST."""
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")

        self.assertEqual(self.get(vendedor, NUEVO).status_code, 403)
        self.assertEqual(self.post(vendedor, NUEVO, _form(accion="confirmar")).status_code, 403)
        self.assertFalse(AsientoContable.objects.exists())

    def test_ext_1a_el_gerente_con_contador_activo_ve_el_motivo_y_no_el_formulario(self):
        """Extensión 1a, punto 3 y D-30: el Gerente con un Contador activo ve «Lo registra el Contador» en lugar del formulario; un POST suyo es 403 y no escribe nada."""
        respuesta = self.get(self.gerente, NUEVO)

        self.assertEqual(respuesta.status_code, 200)
        contenido = _texto(respuesta)
        self.assertIn("Lo registra el Contador", contenido)
        self.assertNotIn("Revisar asiento", contenido)
        self.assertEqual(self.post(self.gerente, NUEVO, _form(accion="confirmar")).status_code, 403)
        self.assertFalse(AsientoContable.objects.exists())

    def test_ext_1a_el_gerente_sin_contador_activo_ve_el_formulario_y_registra(self):
        """Extensión 1a: sin Contador activo el Gerente ve el formulario y registra; queda como autor."""
        Contador.objects.update(is_active=False)

        self.assertIn("Revisar asiento", _texto(self.get(self.gerente, NUEVO)))
        self.post(self.gerente, NUEVO, _form(accion="confirmar"))

        asiento = AsientoContable.objects.get()
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE, afectados__contains=[{"id": asiento.pk}])
        self.assertEqual(registro.usuario_id, self.gerente.pk)

    # --- el formulario ---

    def test_flujo_principal_el_formulario_trae_hoy_dos_filas_el_buscador_de_cuenta_y_los_atajos(self):
        """Pasos 2 y 3: la fecha por defecto es hoy, hay dos filas (una al Debe y otra al Haber), la lista de cuentas del plan para el buscador y el atajo de venta previa (CON-05: el de
        «Asiento de apertura» se quitó; antes decía «los dos atajos»)."""
        contenido = _texto(self.get(self.contador, NUEVO))

        self.assertIn('value="2027-03-10"', contenido)
        self.assertIn('name="cuenta_0"', contenido)
        self.assertIn('name="cuenta_1"', contenido)
        self.assertNotIn('name="cuenta_2"', contenido)
        self.assertIn('<datalist id="cuentas-del-plan">', contenido)
        self.assertIn('<option value="1.1.01 · Caja">', contenido)
        self.assertEqual(contenido.count("<option value=\"") - contenido.count('<option value="D"') - contenido.count('<option value="H"'), CuentaContable.objects.count())
        self.assertNotIn("Asiento de apertura", contenido)
        self.assertIn("Venta de producción previa", contenido)

    def test_flujo_principal_se_puede_cancelar_volviendo_al_libro(self):
        """Extensión *a: el formulario ofrece cancelar y vuelve al libro sin registrar nada."""
        self.assertIn(f'href="{LIBRO}"', _texto(self.get(self.contador, NUEVO)))

    def test_agregar_una_fila_sin_javascript_vuelve_a_dibujar_la_pagina_y_conserva_lo_escrito(self):
        """`ACT.mvadd`: «Agregar una fila» es un botón del formulario; sin JavaScript vuelve a dibujar la página entera con una fila nueva y sin perder lo escrito ni validar."""
        respuesta = self.post(self.contador, NUEVO, _form(descripcion="Algo a medias", filas=[("", "D", ""), ("", "H", "")], accion="agregar"))

        contenido = _texto(respuesta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('name="cuenta_2"', contenido)
        self.assertIn("Algo a medias", contenido)
        self.assertIn("<html", contenido)
        self.assertNotIn("es obligatoria", contenido)  # no valida mientras se escribe

    def test_agregar_y_quitar_una_fila_con_htmx_solo_redibuja_el_cuerpo_del_formulario(self):
        """Interfaz (HTMX): con `HX-Request`, agregar o quitar una fila devuelve solo el cuerpo del formulario, para reemplazar `#cuerpo-asiento`."""
        agregada = self.post(self.contador, NUEVO, _form(accion="agregar"), HTTP_HX_REQUEST="true")
        quitada = self.post(self.contador, NUEVO, _form(filas=[(_etiqueta(cuentas.CAJA), "D", "1,00")] * 3, accion="quitar:1"), HTTP_HX_REQUEST="true")

        self.assertNotIn("<html", _texto(agregada))
        self.assertIn('name="cuenta_2"', _texto(agregada))
        self.assertNotIn("<html", _texto(quitada))
        self.assertNotIn('name="cuenta_1"', _texto(quitada))
        self.assertIn('name="cuenta_0"', _texto(quitada))
        self.assertIn('name="cuenta_2"', _texto(quitada))

    def test_quitar_una_fila_no_deja_menos_de_dos(self):
        """`ACT.mvdel` (el botón se deshabilita con dos filas): un envío manual para quitar con solo dos filas no las quita; con dos filas la pantalla ni muestra «Quitar»."""
        respuesta = self.post(self.contador, NUEVO, _form(accion="quitar:0"))

        contenido = _texto(respuesta)
        self.assertIn('name="cuenta_0"', contenido)
        self.assertIn('name="cuenta_1"', contenido)
        self.assertNotIn('value="quitar:', contenido)

    def test_quitar_una_fila_del_medio_conserva_las_demas_con_su_numero(self):
        """Con tres filas, quitar la del medio deja las otras dos con lo que tenían escrito."""
        filas = [(_etiqueta(cuentas.CAJA), "D", "10,00"), (_etiqueta(cuentas.BANCO), "D", "20,00"), (_etiqueta(cuentas.CAPITAL_INICIAL), "H", "30,00")]

        contenido = _texto(self.post(self.contador, NUEVO, _form(filas=filas, accion="quitar:1")))

        self.assertIn('value="10,00"', contenido)
        self.assertIn('value="30,00"', contenido)
        self.assertNotIn('value="20,00"', contenido)

    def test_ext_3a_quitada_el_atajo_de_apertura_ya_no_precarga_nada(self):
        """CON-REG-ASI, extensión 3a quitada (CON-05; reemplaza `test_ext_3a_el_atajo_de_apertura_precarga_la_descripcion_y_las_cuentas_sin_importes`): la apertura es CON-INI-EJE y ya no es un
        asiento manual; un `accion=atajo:apertura` escrito a mano no precarga la descripción ni las cuentas y no registra nada. La pantalla ya no ofrece el botón."""
        contenido = _texto(self.post(self.contador, NUEVO, _form(descripcion="", filas=[("", "D", ""), ("", "H", "")], accion="atajo:apertura")))

        self.assertNotIn('value="Asiento de apertura"', contenido)
        self.assertIn('name="cuenta_0" list="cuentas-del-plan" autocomplete="off" value=""', contenido)  # la fila sigue vacía: nada se precargó
        self.assertNotIn("atajo:apertura", contenido)
        self.assertFalse(AsientoContable.objects.exists())

    def test_ext_3b_el_atajo_de_venta_previa_precarga_caja_y_ventas(self):
        """Extensión 3b: «Venta de producción previa» sugiere Caja (Debe) y Ventas (Haber)."""
        contenido = _texto(self.post(self.contador, NUEVO, _form(descripcion="", filas=[("", "D", ""), ("", "H", "")], accion="atajo:venta_previa")))

        self.assertIn("Venta de producción previa a la puesta en marcha", contenido)
        self.assertIn(f'value="{_etiqueta(cuentas.CAJA)}"', contenido)
        self.assertIn(f'value="{_etiqueta(cuentas.VENTAS)}"', contenido)

    # --- resumen y confirmación ---

    def test_flujo_principal_revisar_muestra_el_resumen_sin_registrar_y_confirmar_registra(self):
        """Pasos 4 a 8: «Revisar» muestra el resumen (ejercicio, totales, diferencia, tipo de cada cuenta) sin registrar; «Confirmar» registra, avisa con el número y el ejercicio y lleva a la ficha."""
        resumen = self.post(self.contador, NUEVO, _form(accion="revisar"))

        contenido = _texto(resumen)
        self.assertEqual(resumen.status_code, 200)
        self.assertIn("Revisá el asiento", contenido)
        self.assertIn("Ejercicio 2", contenido)
        self.assertIn("$ 1.000,00", contenido)
        self.assertIn("Activo", contenido)
        self.assertIn("Patrimonio neto", contenido)
        self.assertIn("Balanceado", contenido)
        self.assertFalse(AsientoContable.objects.exists())

        confirmada = self.post(self.contador, NUEVO, _form(accion="confirmar"), follow=True)

        asiento = AsientoContable.objects.get()
        self.assertRedirects(confirmada, self.ficha(asiento))
        self.assertEqual((asiento.numero_asiento, asiento.ejercicio_id, asiento.descripcion_asiento), (1, self.abierto.pk, "Asiento de apertura"))
        self.assertIn("Asiento N.º 1 registrado en el ejercicio 2.", self.mensajes(confirmada))
        verificar_invariantes_contables()

    def test_el_resumen_lleva_lo_escrito_en_campos_ocultos_para_volver_a_editar(self):
        """El resumen reenvía lo escrito: «Volver a editar» devuelve el formulario con la fecha, la descripción y las filas tal cual."""
        datos = _form(descripcion="Arqueo de caja", accion="revisar")
        resumen = _texto(self.post(self.contador, NUEVO, datos))

        self.assertIn('name="accion" value="editar"', resumen)
        self.assertIn('name="descripcion" value="Arqueo de caja"', resumen)

        datos["accion"] = "editar"
        editado = _texto(self.post(self.contador, NUEVO, datos))
        self.assertIn('value="Arqueo de caja"', editado)
        self.assertIn('value="1000,00"', editado)
        self.assertFalse(AsientoContable.objects.exists())

    def test_enter_en_el_formulario_revisa_el_asiento(self):
        """Interfaz: el primer botón del formulario es «Revisar asiento» (oculto), el que dispara Enter; un envío sin `accion` revisa, no registra."""
        respuesta = self.post(self.contador, NUEVO, _form())

        self.assertIn("Revisá el asiento", _texto(respuesta))
        self.assertFalse(AsientoContable.objects.exists())

    def test_ext_5d_el_resumen_de_una_fecha_en_el_ejercicio_en_cierre_lo_indica(self):
        """Extensión 5d, punto 2: el resumen avisa que el asiento va al ejercicio en cierre, y se registra con el número de ese ejercicio."""
        EjercicioContable.objects.filter(pk=self.cerrado.pk).update(estado_ejercicio=Estado.EN_CIERRE)

        resumen = _texto(self.post(self.contador, NUEVO, _form(fecha="2026-12-01", accion="revisar")))
        self.post(self.contador, NUEVO, _form(fecha="2026-12-01", accion="confirmar"))

        self.assertIn("Va a un ejercicio en cierre", resumen)
        self.assertEqual(AsientoContable.objects.get().ejercicio_id, self.cerrado.pk)

    def test_regla_importe_acepta_coma_decimal_y_punto_de_mil(self):
        """Interfaz: el importe se escribe como «1.500,50», «1500,50» o «1500.50»; los tres dan 1.500,50."""
        for texto in ("1.500,50", "1500,50", "1500.50", "$ 1.500,50"):
            filas = [(_etiqueta(cuentas.CAJA), "D", texto), (_etiqueta(cuentas.CAPITAL_INICIAL), "H", texto)]
            self.post(self.contador, NUEVO, _form(filas=filas, accion="confirmar"))

        importes = {m.importe_movimiento for m in AsientoContable.objects.get(numero_asiento=1).movimientos.all()}
        self.assertEqual(importes, {Decimal("1500.50")})
        self.assertEqual(AsientoContable.objects.count(), 4)

    def test_regla_cuenta_se_puede_elegir_por_etiqueta_por_codigo_o_por_nombre(self):
        """Buscador de cuenta: sirve la etiqueta de la lista («1.1.01 · Caja»), el código solo o el nombre exacto."""
        filas = [("1.1.01", "D", "10,00"), ("capital inicial", "H", "10,00")]

        self.post(self.contador, NUEVO, _form(filas=filas, accion="confirmar"))

        codigos = sorted(m.cuenta.codigo_cuenta for m in AsientoContable.objects.get().movimientos.select_related("cuenta"))
        self.assertEqual(codigos, [cuentas.CAJA, cuentas.CAPITAL_INICIAL])

    # --- errores ---

    def test_ext_5_los_errores_vuelven_junto_a_cada_campo_y_conservan_lo_escrito(self):
        """Interfaz y patrón ABM: los errores salen todos juntos, junto a su campo y con el texto de la regla, y el formulario conserva lo escrito."""
        filas = [("9.9.99 · Cuenta rara", "D", "100,00"), (_etiqueta(cuentas.CAJA), "H", "-5,00")]

        respuesta = self.post(self.contador, NUEVO, _form(descripcion="", filas=filas, accion="revisar"))

        contenido = _texto(respuesta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("La descripción es obligatoria", contenido)
        self.assertIn("La cuenta contable 9.9.99 · Cuenta rara no existe", contenido)
        self.assertIn("El importe tiene que ser un número mayor que cero", contenido)
        self.assertIn('value="9.9.99 · Cuenta rara"', contenido)
        self.assertIn('value="-5,00"', contenido)
        self.assertFalse(AsientoContable.objects.exists())

    def test_ext_5b_el_desbalance_se_informa_con_la_diferencia(self):
        """Extensión 5b: el Debe y el Haber distintos no dejan revisar ni confirmar y el mensaje trae la diferencia."""
        filas = [(_etiqueta(cuentas.CAJA), "D", "1000,00"), (_etiqueta(cuentas.CAPITAL_INICIAL), "H", "950,00")]

        for accion in ("revisar", "confirmar"):
            contenido = _texto(self.post(self.contador, NUEVO, _form(filas=filas, accion=accion)))
            self.assertIn("no coinciden", contenido)
            self.assertIn("$ 50,00", contenido)
        self.assertFalse(AsientoContable.objects.exists())

    def test_ext_5c_una_cuenta_elegida_sin_importe_se_marca_y_una_fila_vacia_se_omite(self):
        """Extensión 5c: una fila con cuenta y sin importe se marca (no se ignora sin avisar); una fila totalmente vacía se omite."""
        sin_importe = [(_etiqueta(cuentas.CAJA), "D", ""), (_etiqueta(cuentas.CAPITAL_INICIAL), "H", "10,00")]
        con_vacia = [(_etiqueta(cuentas.CAJA), "D", "10,00"), (_etiqueta(cuentas.CAPITAL_INICIAL), "H", "10,00"), ("", "D", "")]

        self.assertIn("El importe tiene que ser un número mayor que cero", _texto(self.post(self.contador, NUEVO, _form(filas=sin_importe, accion="revisar"))))
        self.assertIn("Revisá el asiento", _texto(self.post(self.contador, NUEVO, _form(filas=con_vacia, accion="revisar"))))

    def test_ext_5e_una_fecha_que_el_ejercicio_no_admite_se_rechaza_con_su_motivo_en_el_campo_fecha(self):
        """Extensión 5e: una fecha en un ejercicio cerrado o posterior a hoy se rechaza junto al campo fecha, con el motivo y sin registrar."""
        cerrada = _texto(self.post(self.contador, NUEVO, _form(fecha="2026-06-01", accion="confirmar")))
        futura = _texto(self.post(self.contador, NUEVO, _form(fecha="2027-03-11", accion="confirmar")))

        self.assertIn("está cerrado y ya no recibe asientos", cerrada)
        self.assertIn("posterior a hoy", futura)
        self.assertFalse(AsientoContable.objects.exists())

    def test_una_fecha_vacia_o_mal_escrita_no_registra_y_se_marca(self):
        """Sin una fecha válida nunca se registra (ni con «Confirmar»); se marca el campo y se validan igual los demás."""
        for fecha in ("", "no es una fecha"):
            contenido = _texto(self.post(self.contador, NUEVO, _form(fecha=fecha, descripcion="", accion="confirmar")))
            self.assertIn("Indicá una fecha válida", contenido)
            self.assertIn("La descripción es obligatoria", contenido)
        self.assertFalse(AsientoContable.objects.exists())

    def test_ext_7b_si_el_ejercicio_cambia_mientras_se_confirma_vuelve_al_formulario_con_el_aviso(self):
        """Extensión 7b: si el servicio informa `cambio_simultaneo`, la pantalla vuelve al formulario con el mensaje junto a la fecha y no registra."""
        error = ErrorContable("cambio_simultaneo", "El ejercicio pasó a «cerrado» mientras registrabas.", campo="fecha")

        with mock.patch.object(asientos, "registrar_asiento_manual", side_effect=error):
            contenido = _texto(self.post(self.contador, NUEVO, _form(accion="confirmar")))

        self.assertIn("El ejercicio pasó a «cerrado» mientras registrabas.", contenido)
        self.assertIn('value="Asiento de apertura"', contenido)

    def test_los_textos_escritos_se_escapan(self):
        """Seguridad: la descripción y la cuenta se escapan en el formulario y en el resumen."""
        malo = "<script>alert(1)</script>"

        formulario = self.post(self.contador, NUEVO, _form(descripcion=malo, filas=[(malo, "D", "1"), ("", "H", "")], accion="revisar")).content.decode()

        self.assertNotIn(malo, formulario)
        self.assertIn("&lt;script&gt;", formulario)

    # --- precarga del asiento correcto (C4) ---

    def test_c4_corrige_precarga_las_lineas_del_asiento_anulado_y_la_descripcion_sugerida(self):
        """CON-REG-ASI extensión 1b: `?corrige=<id>` precarga las líneas del asiento anulado (no las invertidas) y «corrección del asiento N.º X», con el aviso de que las cambie."""
        original = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), MOVIMIENTOS, descripcion="Pago de la luz")
        contraasiento = asientos.contraasentar(self.contador, original.pk, datetime.date(2027, 3, 1), "Importe de más", hoy=HOY)

        contenido = _texto(self.get(self.contador, NUEVO, corrige=contraasiento.pk))

        self.assertIn('value="corrección del asiento N.º 1"', contenido)
        self.assertIn("Cargamos las mismas cuentas e importes del asiento N.º 1", contenido)
        self.assertIn(f'value="{_etiqueta(cuentas.GASTOS_GENERALES)}"', contenido)
        self.assertIn('value="1500,50"', contenido)
        self.assertIn('name="corrige" value="1"', contenido)

    def test_c4_el_asiento_correcto_se_registra_como_manual_comun_sin_vinculo(self):
        """C4: confirmar el formulario precargado registra un manual común, sin vínculo con el contraasiento."""
        original = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), MOVIMIENTOS, descripcion="Pago de la luz")
        asientos.contraasentar(self.contador, original.pk, datetime.date(2027, 3, 1), "Importe de más", hoy=HOY)
        filas = [(_etiqueta(cuentas.GASTOS_GENERALES), "D", "1000,00"), (_etiqueta(cuentas.CAJA), "H", "1000,00")]

        self.post(self.contador, NUEVO, _form(descripcion="corrección del asiento N.º 1", filas=filas, accion="confirmar", corrige="1"))

        correcto = AsientoContable.objects.get(numero_asiento=3)
        self.assertEqual(correcto.tipo, AsientoContable.Tipo.MANUAL)
        self.assertIsNone(correcto.anula_id)
        verificar_invariantes_contables()

    def test_c4_corrige_de_un_asiento_inexistente_es_404_y_del_gerente_con_contador_no_precarga(self):
        """Un `?corrige=` inexistente es 404; quien no puede registrar ve el motivo y no la precarga."""
        self.assertEqual(self.get(self.contador, NUEVO, corrige=987654).status_code, 404)
        original = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), MOVIMIENTOS, descripcion="Pago de la luz")

        contenido = _texto(self.get(self.gerente, NUEVO, corrige=original.pk))

        self.assertIn("Lo registra el Contador", contenido)
        self.assertNotIn("corrección del asiento", contenido)


class ConCtrAsiVistaTests(VistaDeAsientosBase):
    """CON-CTR-ASI, «Pantallas»: el formulario del contraasiento, su resumen, la confirmación y la ficha."""

    def setUp(self):
        super().setUp()
        self.original = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), MOVIMIENTOS, descripcion="Pago de la luz")
        self.url = reverse("contabilidad:contraasiento", args=[self.abierto.pk, self.original.numero_asiento])

    # --- acceso (D-30) ---

    def test_regla_quien_registra_solo_el_responsable_contrasienta_los_demas_reciben_403(self):
        """Regla «Quién registra» y D-30: el Vendedor y el Gerente con un Contador activo reciben 403, en GET y en POST; no se escribe nada."""
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        datos = {"fecha": "2027-03-10", "motivo": "Importe de más", "accion": "confirmar"}

        for usuario in (vendedor, self.gerente):
            with self.subTest(usuario=usuario):
                self.assertEqual(self.get(usuario, self.url).status_code, 403)
                self.assertEqual(self.post(usuario, self.url, datos).status_code, 403)
        self.assertEqual(AsientoContable.objects.count(), 1)

    def test_ext_1a_el_gerente_sin_contador_activo_contraasienta(self):
        """Extensión 1a: sin Contador activo el Gerente ve el formulario y contraasienta (sin avisarse a sí mismo)."""
        Contador.objects.update(is_active=False)

        self.assertEqual(self.get(self.gerente, self.url).status_code, 200)
        self.post(self.gerente, self.url, {"fecha": "2027-03-10", "motivo": "Importe de más", "accion": "confirmar"})

        self.assertEqual(AsientoContable.objects.filter(anula=self.original).count(), 1)
        self.assertFalse(Notificacion.objects.exists())

    def test_un_asiento_inexistente_es_404(self):
        """Un asiento que no existe es 404."""
        self.assertEqual(self.get(self.contador, reverse("contabilidad:contraasiento", args=[self.abierto.pk, 99])).status_code, 404)

    # --- el formulario ---

    def test_flujo_principal_el_formulario_muestra_el_asiento_los_movimientos_invertidos_y_hoy(self):
        """Pasos 2 y 3: el asiento a anular (número, fecha, descripción, importe), el contraasiento con el Debe y el Haber invertidos, la fecha de hoy por defecto y el motivo."""
        contenido = _texto(self.get(self.contador, self.url))

        self.assertIn("Contraasentar el asiento N.º 1", contenido)
        self.assertIn("Pago de la luz", contenido)
        self.assertIn("$ 1.500,50", contenido)
        self.assertIn('value="2027-03-10"', contenido)
        self.assertIn('name="motivo"', contenido)
        self.assertIn("Se avisa al Gerente", contenido)
        self.assertNotIn("no anula la operación que lo originó", contenido)

    def test_flujo_principal_los_movimientos_del_contraasiento_salen_invertidos(self):
        """Paso 2: la tabla del contraasiento pone al Haber lo que el original tenía al Debe y viceversa."""
        contenido = _texto(self.get(self.contador, self.url))
        caja = contenido[contenido.index("1.1.01 · Caja"):]
        gastos = contenido[contenido.index("5.1.07 · "):]

        self.assertLess(caja.index("$ 1.500,50"), caja.index("</tr>"))
        self.assertRegex(caja[: caja.index("</tr>")], r"mono\">\$ 1\.500,50</td><td class=\"right nowrap mono\"></td>")  # Caja: ahora al Debe
        self.assertRegex(gastos[: gastos.index("</tr>")], r"mono\"></td><td class=\"right nowrap mono\">\$ 1\.000,00")  # Gastos: ahora al Haber

    def test_flujo_principal_para_un_asiento_automatico_advierte_que_no_anula_la_operacion(self):
        """Paso 2 y C5: para un asiento automático el formulario lo advierte."""
        automatico = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 2), origen=origen_de_prueba())
        url = reverse("contabilidad:contraasiento", args=[self.abierto.pk, automatico.numero_asiento])

        self.assertIn("no anula la operación que lo originó", _texto(self.get(self.contador, url)))

    def test_ext_1b_un_contraasiento_no_se_puede_contraasentar_y_la_pantalla_lo_explica(self):
        """Extensión 1b: la pantalla de un contraasiento explica que no se anula y no ofrece el formulario."""
        contraasiento = asientos.contraasentar(self.contador, self.original.pk, datetime.date(2027, 3, 1), "Importe de más", hoy=HOY)
        url = reverse("contabilidad:contraasiento", args=[contraasiento.ejercicio_id, contraasiento.numero_asiento])

        respuesta = self.get(self.contador, url)

        self.assertEqual(respuesta.status_code, 200)
        contenido = _texto(respuesta)
        self.assertIn("Este asiento no se puede contraasentar", contenido)
        self.assertIn("un contraasiento no se anula", contenido)
        self.assertNotIn('name="motivo"', contenido)

    def test_ext_1b_un_asiento_ya_anulado_muestra_su_contraasiento_con_enlace(self):
        """Extensión 1b: un asiento ya anulado muestra el motivo y el enlace a su contraasiento."""
        contraasiento = asientos.contraasentar(self.contador, self.original.pk, datetime.date(2027, 3, 1), "Importe de más", hoy=HOY)

        contenido = _texto(self.get(self.contador, self.url))

        self.assertIn("Ya está anulado por el", contenido)
        self.assertIn(f'href="{self.ficha(contraasiento)}"', contenido)
        self.assertNotIn('name="motivo"', contenido)

    # --- resumen y confirmación ---

    def test_flujo_principal_revisar_muestra_el_resumen_y_confirmar_registra_avisa_y_ofrece_corregir(self):
        """Pasos 4 a 8: «Revisar» muestra el resumen sin registrar; «Confirmar» registra, avisa al Gerente y lleva a la ficha del contraasiento con la oferta de registrar el asiento correcto."""
        datos = {"fecha": "2027-03-01", "motivo": "Importe de más"}

        resumen = self.post(self.contador, self.url, {**datos, "accion": "revisar"})

        contenido = _texto(resumen)
        self.assertIn("Revisá el contraasiento del asiento N.º 1", contenido)
        self.assertIn("quedará marcado como anulado", contenido)
        self.assertIn("01/03/2027", contenido)
        self.assertEqual(AsientoContable.objects.count(), 1)

        confirmada = self.post(self.contador, self.url, {**datos, "accion": "confirmar"}, follow=True)

        contraasiento = AsientoContable.objects.get(anula=self.original)
        self.assertRedirects(confirmada, self.ficha(contraasiento) + "?corregir=1")
        self.assertIn("Asiento N.º 1 anulado con el contraasiento N.º 2.", self.mensajes(confirmada))
        contenido = _texto(confirmada)
        self.assertIn("¿Registrás ahora el asiento correcto?", contenido)
        self.assertIn(f"{NUEVO}?corrige={contraasiento.pk}", contenido)
        aviso = Notificacion.objects.get()
        self.assertEqual(aviso.destinatario_id, self.gerente.pk)
        verificar_invariantes_contables()

    def test_la_oferta_de_registrar_el_asiento_correcto_solo_aparece_recien_hecho_el_contraasiento(self):
        """Paso 8: la oferta viene con `?corregir=1` (recién hecho); al volver a abrir la ficha ya no se muestra."""
        contraasiento = asientos.contraasentar(self.contador, self.original.pk, datetime.date(2027, 3, 1), "Importe de más", hoy=HOY)

        self.assertIn("Registrar el asiento correcto", _texto(self.get(self.contador, self.ficha(contraasiento), corregir="1")))
        self.assertNotIn("Registrar el asiento correcto", _texto(self.get(self.contador, self.ficha(contraasiento))))
        self.assertNotIn("Registrar el asiento correcto", _texto(self.get(self.gerente, self.ficha(contraasiento), corregir="1")))

    def test_la_ficha_del_anulado_muestra_anulado_y_ya_no_ofrece_contraasentar(self):
        """La ficha del asiento anulado dice «Anulado» y ya no tiene el botón «Contraasentar»; la del contraasiento tampoco lo tiene."""
        contraasiento = asientos.contraasentar(self.contador, self.original.pk, datetime.date(2027, 3, 1), "Importe de más", hoy=HOY)

        anulado = _texto(self.get(self.contador, self.ficha(self.original)))
        del_contraasiento = _texto(self.get(self.contador, self.ficha(contraasiento)))

        self.assertIn("Anulado.", anulado)
        self.assertNotIn(self.url, anulado)
        self.assertNotIn(self.url, del_contraasiento)

    def test_ext_3a_falta_el_motivo_se_marca_junto_al_campo_y_conserva_la_fecha(self):
        """Extensión 3a: sin motivo no se revisa ni se confirma; el error sale junto al campo y se conserva la fecha elegida."""
        for accion in ("revisar", "confirmar"):
            contenido = _texto(self.post(self.contador, self.url, {"fecha": "2027-03-01", "motivo": "  ", "accion": accion}))
            self.assertIn("El motivo es obligatorio", contenido)
            self.assertIn('value="2027-03-01"', contenido)
        self.assertEqual(AsientoContable.objects.count(), 1)

    def test_ext_3b_el_resumen_de_una_fecha_en_el_ejercicio_en_cierre_lo_indica(self):
        """Extensión 3b, punto 2: el resumen indica que el contraasiento va al ejercicio en cierre, y se registra ahí."""
        EjercicioContable.objects.filter(pk=self.cerrado.pk).update(estado_ejercicio=Estado.EN_CIERRE)
        datos = {"fecha": "2026-12-01", "motivo": "Importe de más"}

        resumen = _texto(self.post(self.contador, self.url, {**datos, "accion": "revisar"}))
        self.post(self.contador, self.url, {**datos, "accion": "confirmar"})

        self.assertIn("Va a un ejercicio en cierre", resumen)
        self.assertEqual(AsientoContable.objects.get(anula=self.original).ejercicio_id, self.cerrado.pk)

    def test_ext_3c_una_fecha_cerrada_futura_o_mal_escrita_se_rechaza_junto_al_campo(self):
        """Extensión 3c: una fecha en un ejercicio cerrado, posterior a hoy o que no es una fecha se rechaza junto al campo fecha y no registra."""
        for fecha, texto in (("2026-06-01", "está cerrado y ya no recibe asientos"), ("2027-03-11", "posterior a hoy"), ("", "Indicá una fecha válida")):
            with self.subTest(fecha=fecha):
                contenido = _texto(self.post(self.contador, self.url, {"fecha": fecha, "motivo": "Importe de más", "accion": "confirmar"}))
                self.assertIn(texto, contenido)
        self.assertEqual(AsientoContable.objects.count(), 1)

    def test_ext_6a_si_otro_usuario_lo_anuló_mientras_tanto_vuelve_a_la_ficha_con_el_aviso(self):
        """Extensión 6a: si al confirmar el asiento ya fue anulado por otro, no se registra nada y la pantalla lleva a la ficha con el mensaje."""
        error = ErrorContable("asiento_no_anulable", "Ese asiento ya fue anulado: su contraasiento es el N.º 2.")

        with mock.patch.object(asientos, "contraasentar", side_effect=error):
            respuesta = self.post(self.contador, self.url, {"fecha": "2027-03-10", "motivo": "Importe de más", "accion": "confirmar"}, follow=True)

        self.assertRedirects(respuesta, self.ficha(self.original))
        self.assertIn("Ese asiento ya fue anulado: su contraasiento es el N.º 2.", self.mensajes(respuesta))

    def test_volver_a_editar_desde_el_resumen_conserva_la_fecha_y_el_motivo(self):
        """El resumen reenvía lo escrito: «Volver a editar» devuelve el formulario con la fecha y el motivo."""
        contenido = _texto(self.post(self.contador, self.url, {"fecha": "2027-03-01", "motivo": "Importe de más", "accion": "editar"}))

        self.assertIn('value="2027-03-01"', contenido)
        self.assertIn("Importe de más", contenido)
        self.assertEqual(AsientoContable.objects.count(), 1)

    def test_el_motivo_se_escapa(self):
        """Seguridad: el motivo se escapa en el formulario y en el resumen."""
        malo = "<script>alert(1)</script>"

        resumen = self.post(self.contador, self.url, {"fecha": "2027-03-01", "motivo": malo, "accion": "revisar"}).content.decode()

        self.assertNotIn(malo, resumen)
        self.assertIn("&lt;script&gt;", resumen)


class ConRegAsiBotonesPorRolTests(VistaDeAsientosBase):
    """D-30: ningún botón lleva a un 403. Las acciones se muestran solo a quien puede registrar."""

    def test_el_libro_ofrece_registrar_asiento_al_contador_y_al_gerente_sin_contador(self):
        """«Registrar asiento» en el libro: el Contador lo ve; el Gerente con un Contador activo ve «Lo registra el Contador»; sin Contador activo, el Gerente lo ve."""
        self.assertIn(f'href="{NUEVO}"', _texto(self.get(self.contador, LIBRO)))
        con_contador = _texto(self.get(self.gerente, LIBRO))
        self.assertNotIn(NUEVO, con_contador)
        self.assertIn("Lo registra el Contador", con_contador)
        Contador.objects.update(is_active=False)
        self.assertIn(f'href="{NUEVO}"', _texto(self.get(self.gerente, LIBRO)))

    def test_la_ficha_ofrece_contraasentar_solo_si_se_puede_anular_y_quien_mira_puede(self):
        """«Contraasentar» en la ficha: lo ve quien puede registrar cuando el asiento no es un contraasiento ni está anulado, también en un ejercicio cerrado; el Gerente con Contador activo ve «Lo registra el Contador»."""
        viejo = asiento_de_prueba(self.cerrado, datetime.date(2026, 6, 1), MOVIMIENTOS, descripcion="Gasto de 2026")
        url = reverse("contabilidad:contraasiento", args=[self.cerrado.pk, viejo.numero_asiento])

        self.assertIn(f'href="{url}"', _texto(self.get(self.contador, self.ficha(viejo))))
        del_gerente = _texto(self.get(self.gerente, self.ficha(viejo)))
        self.assertNotIn(url, del_gerente)
        self.assertIn("Lo registra el Contador", del_gerente)
