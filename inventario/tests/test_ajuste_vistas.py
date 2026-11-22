# Pruebas de la pantalla «Ajustar stock de insumo» (INV-02, paso 8; CMP-AJT-STK; integración con el cliente de prueba de Django). Los selectores
# redibujan el formulario con HTMX (``HX-Request``: devuelve solo el formulario y NUNCA escribe); validar y calcular es solo con «Ver resumen» y, sin JavaScript, cada envío es un POST completo con su
# ``accion`` («actualizar», «agregar_lote», «calcular» y «confirmar»). Las reglas, los cálculos y la «huella» son del servicio (sus pruebas están en
# test_cmp_ajt_stk_*.py): acá se prueban permisos, errores por campo, el resumen, la advertencia 12b, el aviso 14a (extensión), el valor sin asiento (D-45)
# y los flujos principales de cada motivo. Solo el Agrónomo a cargo: otros roles y un Agrónomo ajeno reciben 403 (D-28).

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import RegistroAuditoria
from inventario.extensiones import OrdenQueReserva
from inventario.models import LoteInsumo, MovimientoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    faltante,
    insumo,
    lote,
    origen_falso,
    reservas_de_prueba,
    tipo_de_insumo,
    verificar_invariantes,
)
from inventario.tests.test_salida_por_consumo import consumo_simulado
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

HX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()
D = Decimal


def en(dias):
    return HOY + timedelta(days=dias)


class AjusteVistaBase(ConDatosDeInventario, TestCase):
    """Un Agrónomo con sesión y «Nutriente A» (L, controla vencimiento; precio 1500) y «Bolsas» (unidad) habilitados en su invernadero."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Paz")
        self.invernadero = crear_invernadero("Invernadero Uno", agronomo=self.agronomo)
        self.nutriente = insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l", controla_vencimiento=True)
        self.iin = existencia(self.nutriente, self.invernadero, minimo=0, precio="1500.00")
        self.client.force_login(self.agronomo)
        self.ruta = reverse("inventario:ajuste")
        self.lista = reverse("inventario:existencias")

    def datos(self, motivo, accion="calcular", **campos):
        base = {"invernadero": self.invernadero.pk, "insumo": self.nutriente.pk, "motivo": motivo, "accion": accion}
        base.update(campos)
        return base

    def calcular(self, motivo, **campos):
        return self.client.post(self.ruta, self.datos(motivo, "calcular", **campos))

    def confirmar_con(self, calculo, motivo, **campos):
        """Confirma con la huella y la firma que la pantalla mostró en ``calculo`` (lo que hace el botón «Confirmar ajuste»)."""
        contexto = calculo.context
        return self.client.post(
            self.ruta,
            self.datos(motivo, "confirmar", huella=contexto["huella"], firma=contexto["firma"], **campos),
            follow=True,
        )

    def stock(self, iin=None):
        from inventario.servicios import stock

        iin = iin or self.iin
        return stock.stock_actual_de([iin.pk])[iin.pk]


class AccesoAlAjusteVistaTests(AjusteVistaBase):
    """Quién llega al ajuste (SEG-13, D-28)."""

    def test_precondicion_a_un_agronomo_ajeno_recibe_403_con_cualquier_metodo_y_no_se_cambia_nada(self):
        """Precondición b de CMP-AJT-STK y D-28: el invernadero de otro Agrónomo da 403, también para un POST; no se escribe nada."""
        lote(self.iin, 5, vence=en(30))
        self.client.force_login(crear_agronomo(email="otro@infoponia.com"))
        datos = self.datos("rotura_o_perdida", "confirmar", lote_id="1", cantidad="1", huella="[[], \"0\"]", firma="x")
        self.assertEqual(self.client.get(self.ruta, {"invernadero": self.invernadero.pk}).status_code, 403)
        self.assertEqual(self.client.post(self.ruta, datos).status_code, 403)
        self.assertEqual(MovimientoInsumo.objects.count(), 1)  # solo el ingreso de la fábrica

    def test_precondicion_a_un_invernadero_que_no_existe_da_404_y_un_texto_da_403(self):
        """Un id inexistente es 404; un valor que no es un id no revela nada: 403."""
        self.assertEqual(self.client.get(self.ruta, {"invernadero": "99999999"}).status_code, 404)
        self.assertEqual(self.client.get(self.ruta, {"invernadero": "abc"}).status_code, 403)

    def test_regla_4a_un_insumo_que_no_esta_habilitado_en_el_invernadero_no_se_ofrece_ni_se_acepta(self):
        """Extensión 4a: solo se ofrecen los habilitados; uno no habilitado se ignora (queda sin elegir, no hay error 500)."""
        otro = insumo("Bolsas", tipo=self.nutriente.tipo_insumo, unidad="unidad")
        respuesta = self.client.get(self.ruta, {"invernadero": self.invernadero.pk, "insumo": otro.pk, "motivo": "carga_inicial"})
        self.assertIsNone(respuesta.context["existencia"])
        self.assertEqual([h.insumo.nombre_insumo for h in respuesta.context["habilitados"]], ["Nutriente A"])

    def test_cu_paso_4_una_semilla_dada_de_baja_con_existencia_activa_se_ofrece(self):
        """Cómo se aplica la ronda: el paso 4 ofrece las existencias activas aunque el insumo del catálogo esté inactivo (semilla dada de baja)."""
        semilla = insumo("Semilla de lechuga", tipo=tipo_de_insumo("Semillas viejas"), unidad="unidad", activo=False)
        existencia(semilla, self.invernadero)
        respuesta = self.client.get(self.ruta, {"invernadero": self.invernadero.pk})
        self.assertIn("Semilla de lechuga", [h.insumo.nombre_insumo for h in respuesta.context["habilitados"]])

    def test_flujo_principal_la_pantalla_vacia_pide_invernadero_insumo_y_motivo_y_no_ofrece_confirmar(self):
        """Pasos 1 a 3: sin elegir nada solo están los tres selectores (el insumo y el motivo deshabilitados); no hay botón de confirmar."""
        respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "Ajustar stock de insumo")
        self.assertContains(respuesta, "Elegí primero el invernadero")
        self.assertNotContains(respuesta, "Confirmar ajuste")
        self.assertEqual([g.nombre_invernadero for g in respuesta.context["invernaderos"]], ["Invernadero Uno"])

    def test_flujo_principal_elegido_el_insumo_muestra_el_stock_y_los_lotes_con_su_estado(self):
        """Pasos 4 a 6: el stock actual, el precio de referencia y los lotes con su estado («vence en 5 días», «Vencido hace 2 días», faltante)."""
        lote(self.iin, 30, vence=en(40))
        lote(self.iin, 10, vence=en(5))
        lote(self.iin, 4, vence=en(-2))
        faltante(self.iin, 3)
        respuesta = self.client.get(self.ruta, {"invernadero": self.invernadero.pk, "insumo": self.nutriente.pk})
        self.assertContains(respuesta, "41 L")  # 30 + 10 + 4 - 3
        self.assertContains(respuesta, "$ 1.500,00")
        self.assertContains(respuesta, "vence en 5 días")
        self.assertContains(respuesta, "Vencido hace 2 días")
        self.assertContains(respuesta, "Faltante sin lote")
        self.assertNotContains(respuesta, "Confirmar ajuste")  # todavía no hay motivo


class CargaInicialVistaTests(AjusteVistaBase):
    """Carga inicial (7a) con vencimiento: el flujo principal de punta a punta y sus errores por campo."""

    def test_flujo_principal_calcula_el_resumen_con_valor_sin_asiento_y_confirma(self):
        """Verificación a mano 2 y 3: 30 L con vencimiento a 40 días: el resumen muestra stock antes y después y el valor sin asiento; confirmar crea el lote."""
        calculo = self.calcular("carga_inicial", cantidad="30", vencimiento=en(40).isoformat())
        self.assertContains(calculo, "Qué se va a registrar")
        self.assertContains(calculo, "+ $ 45.000,00")
        self.assertContains(calculo, "no genera asiento contable")
        self.assertContains(calculo, "Confirmar ajuste")
        self.assertEqual(self.stock(), 0)  # calcular no escribe
        respuesta = self.confirmar_con(calculo, "carga_inicial", cantidad="30", vencimiento=en(40).isoformat())
        self.assertRedirects(respuesta, self.lista)
        self.assertContains(respuesta, "Ajuste registrado: Nutriente A queda con 30 L en Invernadero Uno.")
        self.assertEqual(self.stock(), 30)
        verificar_invariantes(self.iin)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="ajuste_stock").count(), 1)

    def test_post_h_la_carga_que_cubre_el_minimo_resuelve_la_alerta_bajo_el_minimo(self):
        """Verificación a mano 1 y 3: la alerta «bajo el mínimo» de un insumo con mínimo 20 se resuelve al cargar 40 L."""
        from inventario.models import InsumoInvernadero
        from inventario.servicios import alertas_de_stock

        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(cant_min_insumo=D("20"))
        alertas_de_stock.reevaluar_alertas_del_insumo(self.iin.pk)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_insumo_bajo_minimo", estado_alerta="activa").count(), 1)
        calculo = self.calcular("carga_inicial", cantidad="40", vencimiento=en(40).isoformat())
        self.confirmar_con(calculo, "carga_inicial", cantidad="40", vencimiento=en(40).isoformat())
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_insumo_bajo_minimo", estado_alerta="activa").count(), 0)

    def test_regla_cantidad_valida_los_decimales_de_la_unidad_van_como_error_del_campo(self):
        """Verificación a mano 2: 4 decimales en litros: error en «cantidad» con los decimales que admite la unidad; sin resumen ni confirmar."""
        respuesta = self.calcular("carga_inicial", cantidad="1,2345", vencimiento=en(40).isoformat())
        self.assertEqual(respuesta.context["errores"]["cantidad"], "La unidad L admite hasta 3 decimales.")
        self.assertContains(respuesta, 'class="err"')
        self.assertIsNone(respuesta.context["resumen"])
        self.assertNotContains(respuesta, "Confirmar ajuste")

    def test_ext_7a_3b_un_vencimiento_pasado_da_error_en_su_campo(self):
        """Verificación a mano 2 y extensión 7a.3b: «lo vencido no ingresa al stock», en el campo del vencimiento."""
        respuesta = self.calcular("carga_inicial", cantidad="5", vencimiento=en(-1).isoformat())
        self.assertEqual(respuesta.context["errores"]["vencimiento"], "Esa fecha ya pasó: lo vencido no ingresa al stock.")
        self.assertEqual(self.stock(), 0)

    def test_regla_vencimiento_obligatorio_si_el_insumo_lo_controla_pero_no_se_pide_si_no(self):
        """Un insumo que controla vencimiento exige la fecha; uno que no, no la muestra y el lote queda sin fecha."""
        sin_fecha = self.calcular("carga_inicial", cantidad="5")
        self.assertIn("vencimiento", sin_fecha.context["errores"])
        bolsas = insumo("Bolsas", tipo=self.nutriente.tipo_insumo, unidad="unidad")
        existencia(bolsas, self.invernadero)
        respuesta = self.client.post(
            self.ruta,
            {"invernadero": self.invernadero.pk, "insumo": bolsas.pk, "motivo": "carga_inicial", "accion": "calcular", "cantidad": "7"},
        )
        self.assertContains(respuesta, "Este insumo no controla vencimiento.")
        self.assertIsNotNone(respuesta.context["resumen"])

    def test_regla_cantidad_con_cero_o_vacia_son_errores_del_campo(self):
        """Cantidad vacía («Ingresá la cantidad.») o cero («mayor que cero»)."""
        self.assertEqual(self.calcular("carga_inicial", vencimiento=en(9).isoformat()).context["errores"]["cantidad"], "Ingresá la cantidad.")
        self.assertEqual(self.calcular("carga_inicial", cantidad="0", vencimiento=en(9).isoformat()).context["errores"]["cantidad"], "La cantidad tiene que ser mayor que cero.")


class RecuentoVistaTests(AjusteVistaBase):
    """Recuento físico por lote (CMP-AJT-STK, pasos 8 a 12; extensiones 10a, 10b y 10c)."""

    def setUp(self):
        super().setUp()
        self.grande = lote(self.iin, 30, vence=en(40))
        self.chico = lote(self.iin, 10, vence=en(5))

    def test_flujo_principal_lista_todos_los_lotes_para_contar(self):
        """Cómo se aplica la ronda: el recuento es del insumo entero y por lote: un campo de cantidad contada por cada lote registrado."""
        respuesta = self.client.get(self.ruta, {"invernadero": self.invernadero.pk, "insumo": self.nutriente.pk, "motivo": "recuento_fisico"})
        self.assertContains(respuesta, f'name="contado_{self.grande.pk}"')
        self.assertContains(respuesta, f'name="contado_{self.chico.pk}"')
        self.assertContains(respuesta, "Agregar lote nuevo")

    def test_flujo_principal_contar_8_en_el_lote_de_10_y_un_lote_nuevo_de_2_muestra_las_cinco_partes_y_confirma(self):
        """Verificación a mano 4: el resumen muestra la diferencia del lote, el lote nuevo y el stock antes y después; confirmar escribe un movimiento por lote."""
        campos = {
            f"contado_{self.chico.pk}": "8",
            f"contado_{self.grande.pk}": "30",
            "nuevos_n": "1",
            "nuevo_0_cantidad": "2",
            "nuevo_0_vencimiento": en(90).isoformat(),
        }
        calculo = self.calcular("recuento_fisico", **campos)
        resumen = calculo.context["resumen"]
        self.assertEqual([(c.lote.pk, c.diferencia) for c in resumen.lotes], [(self.chico.pk, D("-2"))])
        self.assertEqual([(n.cantidad, n.vencimiento) for n in resumen.lotes_nuevos], [(D("2"), en(90))])
        self.assertEqual((resumen.stock_antes, resumen.stock_despues, resumen.diferencia), (D("40"), D("40"), D("0")))
        self.assertContains(calculo, "Lotes que cambian")
        self.assertContains(calculo, "Lotes nuevos")
        respuesta = self.confirmar_con(calculo, "recuento_fisico", **campos)
        self.assertRedirects(respuesta, self.lista)
        self.chico.refresh_from_db()
        self.assertEqual(self.chico.cantidad_disponible, D("8"))
        self.assertEqual(LoteInsumo.objects.filter(insumo_invernadero=self.iin).count(), 3)
        verificar_invariantes(self.iin)

    def test_regla_los_lotes_que_se_dejan_en_blanco_no_cambian_y_una_fila_nueva_vacia_se_ignora(self):
        """Solo se anotan los lotes que difieren: los campos vacíos no son un 0, y una fila de lote nuevo sin datos no es un error."""
        respuesta = self.calcular("recuento_fisico", **{f"contado_{self.chico.pk}": "9", "nuevos_n": "2"})
        self.assertEqual([c.lote.pk for c in respuesta.context["resumen"].lotes], [self.chico.pk])
        self.assertEqual(respuesta.context["resumen"].lotes_nuevos, [])

    def test_ext_10a_contar_lo_mismo_que_lo_registrado_no_hay_nada_que_ajustar(self):
        """Extensión 12a: sin diferencias no hay resumen ni confirmar; el error general lo dice."""
        respuesta = self.calcular("recuento_fisico", **{f"contado_{self.chico.pk}": "10"})
        self.assertIn("No hay nada que ajustar: el recuento coincide con lo registrado.", respuesta.context["errores_generales"])
        self.assertIsNone(respuesta.context["resumen"])
        self.assertNotContains(respuesta, "Confirmar ajuste")

    def test_ext_10b_un_lote_nuevo_vencido_y_uno_sin_cantidad_dan_error_en_la_fila_que_corresponde(self):
        """Extensión 10b: el error de «lote nuevo» sale en la fila de la pantalla (con filas vacías en el medio, el número sigue el de la pantalla)."""
        respuesta = self.calcular(
            "recuento_fisico",
            nuevos_n="3",
            nuevo_1_cantidad="2",
            nuevo_1_vencimiento=en(-3).isoformat(),
            nuevo_2_vencimiento=en(20).isoformat(),
        )
        self.assertEqual(respuesta.context["errores"]["nuevo_1_vencimiento"], "Esa fecha ya pasó: lo vencido no ingresa al stock.")
        self.assertEqual(respuesta.context["errores"]["nuevo_2_cantidad"], "Ingresá la cantidad.")
        self.assertNotIn("nuevo_0_cantidad", respuesta.context["errores"])

    def test_ext_10c_subir_un_lote_vencido_da_error_en_su_campo(self):
        """Un lote vencido no puede contarse con más de lo registrado («lo vencido no ingresa al stock»)."""
        vencido = lote(self.iin, 2, vence=en(-4))
        respuesta = self.calcular("recuento_fisico", **{f"contado_{vencido.pk}": "5"})
        self.assertIn(f"contado_{vencido.pk}", respuesta.context["errores"])

    def test_agregar_lote_nuevo_suma_una_fila_sin_calcular_ni_escribir(self):
        """Sin JavaScript: «Agregar lote nuevo» (accion=agregar_lote) devuelve la pantalla con una fila más y los datos escritos conservados."""
        respuesta = self.client.post(
            self.ruta, self.datos("recuento_fisico", "agregar_lote", nuevos_n="1", **{f"contado_{self.chico.pk}": "8"})
        )
        self.assertEqual(respuesta.context["nuevos_n"], 2)
        self.assertContains(respuesta, 'name="nuevo_1_cantidad"')
        self.assertContains(respuesta, 'value="8"')
        self.assertIsNone(respuesta.context["resumen"])

    def test_regla_5_el_faltante_sin_lote_queda_en_cero_y_se_muestra_en_el_resumen(self):
        """Verificación a mano 7: un faltante de 6 se deja en cero con el recuento y el resumen lo dice; el stock vuelve a ser la suma de los lotes reales."""
        falta = faltante(self.iin, 6)
        self.assertEqual(self.stock(), 34)
        campos = {f"contado_{self.chico.pk}": "9"}
        calculo = self.calcular("recuento_fisico", **campos)
        self.assertContains(calculo, "Queda en cero: faltaban 6 L.")
        self.confirmar_con(calculo, "recuento_fisico", **campos)
        falta.refresh_from_db()
        self.assertEqual(falta.cantidad_disponible, D("0"))
        self.assertEqual(self.stock(), 39)
        verificar_invariantes(self.iin)


class OtrosMotivosVistaTests(AjusteVistaBase):
    """Rotura, vencimiento, corrección entre lotes y «otro»."""

    def setUp(self):
        super().setUp()
        self.a = lote(self.iin, 30, vence=en(40))
        self.b = lote(self.iin, 10, vence=en(5))

    def test_ext_7b_3b_una_rotura_con_mas_de_lo_disponible_da_error_con_lo_disponible(self):
        """Verificación a mano 5: el error del campo «cantidad» dice cuánto hay en el lote."""
        respuesta = self.calcular("rotura_o_perdida", lote_id=self.b.pk, cantidad="11")
        self.assertEqual(respuesta.context["errores"]["cantidad"], "El lote tiene 10 L disponibles.")
        self.assertEqual(self.stock(), 40)

    def test_ext_7b_2_una_rotura_sin_lote_da_error_en_el_campo_lote(self):
        """El lote afectado es obligatorio: el error sale en «lote» (el campo de la pantalla es lote_id)."""
        respuesta = self.calcular("rotura_o_perdida", cantidad="1")
        self.assertEqual(respuesta.context["errores"]["lote"], "Elegí el lote afectado.")

    def test_flujo_principal_una_rotura_descuenta_del_lote_y_el_resumen_muestra_el_valor_negativo(self):
        """Rotura de 4 L del lote de 10: valor − $ 6.000,00 (sin asiento) y el lote queda en 6."""
        campos = {"lote_id": str(self.b.pk), "cantidad": "4", "descripcion": "Se cayó el bidón"}
        calculo = self.calcular("rotura_o_perdida", **campos)
        self.assertContains(calculo, "−$ 6.000,00")
        self.confirmar_con(calculo, "rotura_o_perdida", **campos)
        self.b.refresh_from_db()
        self.assertEqual(self.b.cantidad_disponible, D("6"))
        verificar_invariantes(self.iin)

    def test_flujo_principal_la_correccion_entre_lotes_no_cambia_el_total_y_el_resumen_dice_que_no_tiene_valor(self):
        """Verificación a mano 5: el stock total no cambia y el resumen dice «Sin valor»."""
        campos = {"origen_id": str(self.a.pk), "destino_id": str(self.b.pk), "cantidad": "5"}
        calculo = self.calcular("correccion_entre_lotes", **campos)
        self.assertContains(calculo, "Sin valor: el stock total no cambia.")
        resumen = calculo.context["resumen"]
        self.assertEqual((resumen.stock_antes, resumen.stock_despues, resumen.con_valor), (D("40"), D("40"), False))
        self.confirmar_con(calculo, "correccion_entre_lotes", **campos)
        self.assertEqual((LoteInsumo.objects.get(pk=self.a.pk).cantidad_disponible, LoteInsumo.objects.get(pk=self.b.pk).cantidad_disponible), (D("25"), D("15")))
        self.assertEqual(self.stock(), 40)
        verificar_invariantes(self.iin)

    def test_ext_7d_3a_origen_y_destino_iguales_dan_error_en_el_destino(self):
        """Extensión 7d.3a: el destino tiene que ser distinto del origen (error en «destino»)."""
        respuesta = self.calcular("correccion_entre_lotes", origen_id=self.a.pk, destino_id=self.a.pk, cantidad="1")
        self.assertEqual(respuesta.context["errores"]["destino"], "El lote de destino tiene que ser distinto del de origen.")

    def test_ext_7c_vencimiento_solo_lista_los_lotes_vencidos_y_los_da_de_baja(self):
        """Verificación a mano 6: «Vencimiento» ofrece solo los vencidos; darlos de baja los deja en 0 y resuelve su alerta de vencido."""
        vencido = lote(self.iin, 5, vence=en(-3))
        from inventario.servicios import vencimientos

        vencimientos.revisar_vencimientos(HOY)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_insumo_vencido", estado_alerta="activa").count(), 1)
        respuesta = self.client.get(self.ruta, {"invernadero": self.invernadero.pk, "insumo": self.nutriente.pk, "motivo": "vencimiento"})
        self.assertEqual([lc.lote.pk for lc in respuesta.context["lotes_vencidos"]], [vencido.pk])
        calculo = self.calcular("vencimiento", lotes=[str(vencido.pk)])
        self.assertContains(calculo, "Qué se va a registrar")
        self.confirmar_con(calculo, "vencimiento", lotes=[str(vencido.pk)])
        vencido.refresh_from_db()
        self.assertEqual(vencido.cantidad_disponible, D("0"))
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_insumo_vencido", estado_alerta="activa").count(), 0)
        verificar_invariantes(self.iin)

    def test_flujo_principal_dar_de_baja_desde_el_lote_vencido_abre_el_ajuste_con_el_lote_marcado_y_el_resumen_listo(self):
        """Paso 8 de INV-02: el enlace «Dar de baja» de las existencias abre el ajuste con el motivo «vencimiento» y el lote marcado (con el resumen ya calculado)."""
        vencido = lote(self.iin, 5, vence=en(-3))
        respuesta = self.client.get(
            self.ruta, {"invernadero": self.invernadero.pk, "insumo": self.nutriente.pk, "motivo": "vencimiento", "lotes": vencido.pk}
        )
        self.assertContains(respuesta, f'value="{vencido.pk}" checked')
        self.assertIsNotNone(respuesta.context["resumen"])
        self.assertContains(respuesta, "Confirmar ajuste")

    def test_ext_7c_1a_sin_lotes_vencidos_la_pantalla_lo_informa(self):
        """Extensión 7c.1a: «Este insumo no tiene lotes vencidos en este invernadero.»"""
        respuesta = self.client.get(self.ruta, {"invernadero": self.invernadero.pk, "insumo": self.nutriente.pk, "motivo": "vencimiento"})
        self.assertContains(respuesta, "Este insumo no tiene lotes vencidos en este invernadero.")

    def test_ext_7e_otro_exige_sentido_y_descripcion_y_cada_sentido_muestra_sus_campos(self):
        """Extensión 7e: «Otro» pide si suma o resta y una descripción; «suma» pide cantidad y vencimiento; «resta», lote y cantidad."""
        respuesta = self.calcular("otro")
        self.assertEqual(respuesta.context["errores"]["sentido"], "Indicá si el ajuste suma o resta stock.")
        suma = self.client.get(self.ruta, {"invernadero": self.invernadero.pk, "insumo": self.nutriente.pk, "motivo": "otro", "sentido": "suma"})
        self.assertContains(suma, 'name="vencimiento"')
        resta = self.client.get(self.ruta, {"invernadero": self.invernadero.pk, "insumo": self.nutriente.pk, "motivo": "otro", "sentido": "resta"})
        self.assertContains(resta, 'name="lote_id"')
        sin_descripcion = self.calcular("otro", sentido="resta", lote_id=self.b.pk, cantidad="1")
        self.assertEqual(sin_descripcion.context["errores"]["descripcion"], "Contá qué pasó.")

    def test_flujo_principal_otro_que_suma_crea_un_lote_nuevo(self):
        """«Otro» que suma crea un lote y deja la descripción en el movimiento."""
        campos = {"sentido": "suma", "descripcion": "Donación", "cantidad": "3", "vencimiento": en(60).isoformat()}
        calculo = self.calcular("otro", **campos)
        self.confirmar_con(calculo, "otro", **campos)
        self.assertEqual(self.stock(), 43)
        verificar_invariantes(self.iin)

    def test_motivo_invalido_o_vacio_no_calcula_nada(self):
        """Sin un motivo de la lista la pantalla no muestra datos ni resumen (no hay error 500)."""
        respuesta = self.client.post(self.ruta, self.datos("inventado", cantidad="1"))
        self.assertEqual(respuesta.context["motivo"], "")
        self.assertNotContains(respuesta, "Confirmar ajuste")


class AdvertenciaYDesactualizadoVistaTests(AjusteVistaBase):
    """La advertencia 12b y el aviso de datos desactualizados (extensión 14a)."""

    def setUp(self):
        super().setUp()
        self.lote = lote(self.iin, 20, vence=en(40))
        self.origen = origen_falso()

    def orden(self, numero, cantidad):
        return OrdenQueReserva(numero, f"Siembra {numero}", D(cantidad), en(2), f"/o/{numero}")

    def test_ext_12b_un_ajuste_que_deja_el_stock_sin_cubrir_las_reservas_advierte_y_se_puede_confirmar(self):
        """Extensión 12b: la advertencia lista las órdenes sin cobertura; no bloquea: se confirma y queda la alerta «stock inconsistente» (postcondición i)."""
        campos = {"lote_id": str(self.lote.pk), "cantidad": "15"}
        with reservas_de_prueba(reservado={self.iin.pk: "10"}, ordenes={self.iin.pk: [self.orden(1, "10")]}):
            calculo = self.calcular("rotura_o_perdida", **campos)
            self.assertContains(calculo, "Con este ajuste el stock no cubre lo reservado")
            self.assertContains(calculo, "Siembra 1")
            self.assertEqual(calculo.context["resumen"].advertencia.stock_vigente, D("5"))
            respuesta = self.confirmar_con(calculo, "rotura_o_perdida", **campos)
        self.assertRedirects(respuesta, self.lista)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_stock_inconsistente", estado_alerta="activa").count(), 1)
        self.assertContains(respuesta, "sigue sin cubrir las reservas")

    def test_ext_12b_un_ajuste_que_cubre_las_reservas_no_advierte(self):
        """Sin reservas insuficientes no hay advertencia."""
        calculo = self.calcular("rotura_o_perdida", lote_id=self.lote.pk, cantidad="5")
        self.assertNotContains(calculo, "no cubre lo reservado")
        self.assertIsNone(calculo.context["resumen"].advertencia)

    def test_ext_14a_si_cambia_el_stock_mientras_tanto_no_se_cambia_nada_y_se_muestra_lo_vigente(self):
        """Extensión 14a y verificación a mano 13: otra operación consume del lote entre el resumen y la confirmación: «los datos cambiaron», sin error 500
        y sin cambios; el resumen se recalcula con lo vigente y con la huella nueva; confirmar de nuevo lo aplica."""
        campos = {"lote_id": str(self.lote.pk), "cantidad": "5"}
        calculo = self.calcular("rotura_o_perdida", **campos)
        consumo_simulado(self.agronomo, self.iin, [(self.lote.pk, D("3"))], self.origen)
        antes = MovimientoInsumo.objects.count()
        respuesta = self.client.post(
            self.ruta,
            self.datos("rotura_o_perdida", "confirmar", huella=calculo.context["huella"], firma=calculo.context["firma"], **campos),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Los datos cambiaron mientras tanto")
        self.assertEqual(MovimientoInsumo.objects.count(), antes)
        self.assertEqual(self.stock(), 17)
        self.assertNotEqual(respuesta.context["huella"], calculo.context["huella"])
        self.assertContains(respuesta, "Confirmar ajuste")
        final = self.confirmar_con(respuesta, "rotura_o_perdida", **campos)
        self.assertRedirects(final, self.lista)
        self.assertEqual(self.stock(), 12)
        verificar_invariantes(self.iin)

    def test_si_se_cambia_un_dato_despues_del_resumen_no_se_confirma_lo_que_no_se_vio(self):
        """Sin JavaScript: un dato cambiado después del resumen y un «Confirmar» sin recalcular no escribe: se recalcula y se avisa."""
        calculo = self.calcular("rotura_o_perdida", lote_id=self.lote.pk, cantidad="5")
        respuesta = self.client.post(
            self.ruta,
            self.datos("rotura_o_perdida", "confirmar", huella=calculo.context["huella"], firma=calculo.context["firma"], lote_id=self.lote.pk, cantidad="9"),
        )
        self.assertContains(respuesta, "Cambiaste datos después de ver el resumen")
        self.assertEqual(self.stock(), 20)
        self.assertEqual(respuesta.context["resumen"].diferencia, D("-9"))

    def test_una_huella_invalida_no_confirma_nada(self):
        """Una huella ausente o mal formada no escribe: se recalcula (no hay error 500)."""
        for huella in ("", "no es json", "[1]"):
            with self.subTest(huella=huella):
                respuesta = self.client.post(
                    self.ruta, self.datos("rotura_o_perdida", "confirmar", huella=huella, firma="x", lote_id=self.lote.pk, cantidad="1")
                )
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(self.stock(), 20)

    def test_confirmar_dos_veces_con_la_misma_huella_la_segunda_ve_los_datos_cambiaron(self):
        """Dos confirmaciones del mismo resumen (doble envío o dos sesiones): la primera aplica y la segunda ve «los datos cambiaron» sin duplicar."""
        campos = {"lote_id": str(self.lote.pk), "cantidad": "5"}
        calculo = self.calcular("rotura_o_perdida", **campos)
        self.confirmar_con(calculo, "rotura_o_perdida", **campos)
        segunda = self.client.post(
            self.ruta,
            self.datos("rotura_o_perdida", "confirmar", huella=calculo.context["huella"], firma=calculo.context["firma"], **campos),
        )
        self.assertContains(segunda, "Los datos cambiaron mientras tanto")
        self.assertEqual(self.stock(), 15)


class AjusteConHtmxVistaTests(AjusteVistaBase):
    """HTMX: solo el formulario, sin escribir. Cambiar un selector solo redibuja; validar y calcular es solo con «Ver resumen» (cambio de criterio del
    paso 8 de INV-02, pedido en la revisión a mano: nada se valida ni se calcula mientras se escribe)."""

    def setUp(self):
        super().setUp()
        self.a = lote(self.iin, 30, vence=en(40))

    def test_flujo_principal_ver_resumen_con_htmx_devuelve_solo_el_formulario_con_errores_y_resumen_sin_escribir(self):
        """«Ver resumen» (``accion=calcular``) devuelve el fragmento con el resumen y no escribe."""
        antes = (MovimientoInsumo.objects.count(), RegistroAuditoria.objects.count())
        respuesta = self.client.post(self.ruta, self.datos("rotura_o_perdida", lote_id=self.a.pk, cantidad="4"), **HX)
        self.assertNotContains(respuesta, "<html")
        self.assertNotContains(respuesta, 'id="ajuste-vivo"')
        self.assertContains(respuesta, "Qué se va a registrar")
        self.assertEqual((MovimientoInsumo.objects.count(), RegistroAuditoria.objects.count()), antes)

    def test_ver_resumen_con_htmx_muestra_los_errores_por_campo_incluso_de_los_vacios(self):
        """Al pedir el resumen, un campo vacío u obligatorio sin completar sí es un error por campo."""
        vacio = self.client.post(self.ruta, self.datos("carga_inicial"), **HX)
        self.assertIn("cantidad", vacio.context["errores"])
        self.assertIsNone(vacio.context["resumen"])

    def test_cambiar_un_selector_con_htmx_no_valida_ni_calcula(self):
        """Sin ``accion`` (cambio de invernadero, insumo, motivo o sentido) se redibujan los campos, sin errores ni resumen, aunque haya datos escritos."""
        datos = self.datos("rotura_o_perdida", lote_id=self.a.pk, cantidad="1,2345")
        datos.pop("accion")
        respuesta = self.client.post(self.ruta, datos, **HX)
        self.assertEqual(respuesta.context["errores"], {})
        self.assertEqual(respuesta.context["errores_generales"], [])
        self.assertIsNone(respuesta.context["resumen"])
        self.assertNotContains(respuesta, "Qué se va a registrar")
        self.assertContains(respuesta, 'id="cantidad"')  # los campos del motivo elegido sí aparecen

    def test_cambiar_el_motivo_con_htmx_descarta_el_resumen_anterior(self):
        """El resumen de un cálculo previo no sobrevive a un cambio de selector: hay que volver a pedirlo."""
        datos = self.datos("rotura_o_perdida", lote_id=self.a.pk, cantidad="4")
        self.assertContains(self.client.post(self.ruta, datos, **HX), "Qué se va a registrar")
        datos.pop("accion")
        self.assertNotContains(self.client.post(self.ruta, datos, **HX), "Qué se va a registrar")

    def test_un_post_comun_sin_accion_tampoco_calcula(self):
        """Sin JavaScript, «Continuar» (``actualizar``) y cualquier envío sin ``calcular`` ni ``confirmar`` solo redibujan la pantalla."""
        respuesta = self.client.post(self.ruta, self.datos("rotura_o_perdida", "actualizar", lote_id=self.a.pk, cantidad="4"))
        self.assertIsNone(respuesta.context["resumen"])
        self.assertEqual(respuesta.context["errores"], {})

    def test_agregar_lote_con_htmx_suma_una_fila_sin_validar(self):
        """«Agregar lote nuevo» por HTMX solo agrega la fila."""
        respuesta = self.client.post(self.ruta, self.datos("recuento_fisico", "agregar_lote", nuevos_n="0", nuevo_0_cantidad="1,2345"), **HX)
        self.assertEqual(respuesta.context["nuevos_n"], 1)
        self.assertEqual(respuesta.context["errores"], {})
        self.assertIsNone(respuesta.context["resumen"])

    def test_abrir_la_pantalla_con_get_calcula_sin_marcar_errores_de_campos_vacios(self):
        """El enlace «Dar de baja» (GET) muestra el resumen listo; un campo vacío no es un error mientras no se pida el resumen."""
        respuesta = self.client.get(self.ruta, {"invernadero": self.invernadero.pk, "insumo": self.nutriente.pk, "motivo": "carga_inicial"})
        self.assertEqual(respuesta.context["errores"], {})

    def test_el_pedido_de_htmx_sin_confirmar_nunca_escribe_aunque_traiga_la_huella(self):
        """Un pedido de HTMX no lleva ``accion=confirmar``: aunque traiga la huella y la firma de un resumen, no escribe."""
        calculo = self.calcular("rotura_o_perdida", lote_id=self.a.pk, cantidad="4")
        datos = self.datos("rotura_o_perdida", lote_id=self.a.pk, cantidad="4", huella=calculo.context["huella"], firma=calculo.context["firma"])
        datos.pop("accion")
        self.client.post(self.ruta, datos, **HX)
        self.assertEqual(self.stock(), 30)

    def test_la_pagina_no_refresca_al_escribir_y_los_botones_y_selectores_traen_su_pedido(self):
        """Ningún disparador de ``input`` en la pantalla; los selectores usan ``change`` y los botones «Ver resumen» y «Agregar lote» llevan su ``hx-vals``,
        sin ``hx-select`` (así «Ver resumen» actualiza los errores y el resumen). «Confirmar ajuste» queda como envío común, y sigue el respaldo sin JavaScript."""
        calculo = self.calcular("rotura_o_perdida", lote_id=self.a.pk, cantidad="4")
        self.assertContains(calculo, 'id="ajuste-vivo"')
        self.assertContains(calculo, 'hx-swap="innerHTML show:none"')
        self.assertNotContains(calculo, "input delay")
        self.assertNotContains(calculo, "hx-select")
        self.assertContains(calculo, 'hx-trigger="change"')
        self.assertContains(calculo, "hx-vals='{\"accion\": \"calcular\"}'")
        self.assertContains(calculo, 'value="calcular"')
        self.assertContains(calculo, 'value="confirmar"')
        self.assertNotContains(calculo, 'value="confirmar" hx-')
        self.assertContains(calculo, "<noscript>")
