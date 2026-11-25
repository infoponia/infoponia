# Pruebas de los modelos de COM-07a (paso 1): los campos y las restricciones nuevas de `SolicitudRevision` (la aplicación de la indemnización y el aviso al cliente), `Anulacion` (hija de
# `OrigenDocumento`, con la copia de la resolución anulada), `Suministro.solicitud_resolucion`, las acciones y las etiquetas de auditoría de `core`, las fábricas nuevas y los invariantes
# nuevos de `verificar_invariantes_de_solicitudes`. Una prueba por restricción de la base (la viola y no la viola).
# Fuente: docs/modelo/comercial.md («SolicitudRevision», «Suministro», «Anulacion», «DiscrepanciaEntrega y LineaDiscrepancia»), D-69 puntos 5, 9, 10 y 17, D-36 (auditoría)
# y docs/casos_de_uso/comercial/solicitudes.md.

import ast
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.db import IntegrityError, models, transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import Anulacion, LineaDiscrepancia, SolicitudRevision, Suministro
from comercial.tests.fabricas import (
    anulacion,
    detalle_suministro,
    discrepancia,
    discrepancia_aceptada,
    entrega,
    escenario_comercial,
    marcar_concretada,
    queja_aceptada,
    reserva_lista,
    resolucion_del_suministro,
    solicitud_rechazada,
    suministro,
    verificar_invariantes_de_solicitudes,
)
from contabilidad.models import OrigenDocumento
from core.models import ACCIONES_DE_NEGOCIO, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


class Base(ConDatosDeInventario, TestCase):
    """Un suministro con un período de 10 plantas (mínimo 8, a $100) y su Gerente; cada prueba arma sus entregas y solicitudes."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.gerente = crear_gerente()
        cls.lote = lote_maduro(cls.e, 500)
        cls.suministro = suministro(cls.e)
        cls.detalle_sum = detalle_suministro(cls.suministro, cls.e.variedad, cantidad=10, minima=8)
        cls.reserva_sum = reserva_lista(None, cls.lote, 10, fecha_entrega=cls.detalle_sum.fecha_primer_entrega, detalle_suministro=cls.detalle_sum)

    def entrega_de_suministro(self):
        """La entrega concretada del período de la clase (10 plantas a $100 = $1.000,00), directo en la base."""
        return marcar_concretada(entrega(self.suministro, [self.reserva_sum]))

    def otra_entrega_de_suministro(self):
        """Otra entrega concretada del mismo suministro, con el período siguiente."""
        if not hasattr(self, "_reserva_siguiente"):
            siguiente = self.detalle_sum.fecha_primer_entrega + timedelta(days=7)
            self._reserva_siguiente = reserva_lista(None, self.lote, 10, fecha_entrega=siguiente, detalle_suministro=self.detalle_sum)
        return marcar_concretada(entrega(self.suministro, [self._reserva_siguiente]))

    def rompe(self, texto):
        with self.assertRaises(AssertionError) as c:
            verificar_invariantes_de_solicitudes()
        self.assertIn(texto, str(c.exception))

    def actualizar(self, solicitud, **campos):
        """Un `UPDATE` directo (la base es la que valida): devuelve la solicitud refrescada."""
        SolicitudRevision.objects.filter(pk=solicitud.pk).update(**campos)
        return SolicitudRevision.objects.get(pk=solicitud.pk)


# ---- SolicitudRevision: la aplicación de la indemnización (D-69, punto 9) ----


class SolicitudAplicacionTests(Base):
    def test_d69_9_una_aceptada_guarda_descontado_y_reintegrado(self):
        """Aceptada ⇔ `monto_descontado` y `monto_reintegrado` no nulos (D-69, punto 9): la fábrica la deja completa."""
        s = discrepancia_aceptada(self.entrega_de_suministro(), monto="100.00", reintegrado="30.00", medio="transferencia")
        self.assertEqual((s.monto_descontado, s.monto_reintegrado, s.medio_reintegro), (Decimal("70.00"), Decimal("30.00"), "transferencia"))

    def test_regla_aceptada_exige_los_dos_montos_y_una_no_aceptada_no_los_tiene(self):
        """Constraint `solicitud_aceptada_con_aplicacion`: aceptada sin montos o pendiente con montos se rechaza."""
        s = discrepancia(self.entrega_de_suministro())
        viola(self, lambda: self.actualizar(s, estado_solicitud="aceptada", fecha_resolucion=HOY, gerente=self.gerente, monto_indemnizacion=Decimal("10.00")))
        viola(self, lambda: self.actualizar(s, monto_descontado=Decimal("10.00")))
        viola(self, lambda: self.actualizar(discrepancia_aceptada(self.otra_entrega_de_suministro()), monto_reintegrado=None))

    def test_regla_los_montos_no_son_negativos(self):
        """Constraint `solicitud_montos_no_negativos`: ni lo descontado ni lo reintegrado pueden ser negativos (aunque la suma dé la indemnización)."""
        s = discrepancia_aceptada(self.entrega_de_suministro(), monto="100.00")
        viola(self, lambda: self.actualizar(s, monto_descontado=Decimal("-10.00"), monto_reintegrado=Decimal("110.00"), medio_reintegro="efectivo"))
        viola(self, lambda: self.actualizar(s, monto_descontado=Decimal("110.00"), monto_reintegrado=Decimal("-10.00")))

    def test_regla_descontado_mas_reintegrado_es_la_indemnizacion(self):
        """Constraint `solicitud_aplicacion_suma_indemnizacion`: aceptada ⇒ descontado + reintegrado = monto de la indemnización."""
        s = discrepancia_aceptada(self.entrega_de_suministro(), monto="100.00", reintegrado="30.00", medio="efectivo")
        viola(self, lambda: self.actualizar(s, monto_descontado=Decimal("60.00")))
        self.assertEqual(self.actualizar(s, monto_descontado=Decimal("40.00"), monto_reintegrado=Decimal("60.00")).monto_reintegrado, Decimal("60.00"))

    def test_regla_el_medio_va_si_y_solo_si_hay_reintegro(self):
        """Constraint `solicitud_medio_con_reintegro`: `medio_reintegro` no nulo ⇔ `monto_reintegrado > 0`."""
        con_reintegro = discrepancia_aceptada(self.entrega_de_suministro(), monto="100.00", reintegrado="40.00", medio="efectivo")
        viola(self, lambda: self.actualizar(con_reintegro, medio_reintegro=None))
        sin_reintegro = discrepancia_aceptada(self.otra_entrega_de_suministro(), monto="100.00")
        self.assertIsNone(sin_reintegro.medio_reintegro)
        viola(self, lambda: self.actualizar(sin_reintegro, medio_reintegro="efectivo"))

    def test_regla_el_medio_es_efectivo_o_transferencia(self):
        """Constraint `solicitud_medio_valido`: cualquier otro medio se rechaza."""
        s = discrepancia_aceptada(self.entrega_de_suministro(), monto="100.00", reintegrado="40.00", medio="efectivo")
        viola(self, lambda: self.actualizar(s, medio_reintegro="cheque"))
        self.assertEqual(self.actualizar(s, medio_reintegro="transferencia").medio_reintegro, "transferencia")

    def test_d69_17_el_aviso_al_cliente_es_de_la_lista_y_una_pendiente_no_lo_tiene(self):
        """Constraints `solicitud_aviso_valido` y `solicitud_pendiente_sin_aviso`: el aviso es `enviado`, `pendiente_envio` o `sin_correo`, y nulo mientras está pendiente."""
        pendiente = discrepancia(self.entrega_de_suministro())
        self.assertIsNone(pendiente.estado_aviso_cliente)
        viola(self, lambda: self.actualizar(pendiente, estado_aviso_cliente="enviado"))
        s = discrepancia_aceptada(self.otra_entrega_de_suministro())
        viola(self, lambda: self.actualizar(s, estado_aviso_cliente="perdido"))
        for valor in ("enviado", "pendiente_envio", "sin_correo", None):
            self.assertEqual(self.actualizar(s, estado_aviso_cliente=valor).estado_aviso_cliente, valor)

    def test_regla_una_rechazada_no_tiene_montos_y_su_aviso_es_libre(self):
        """Rechazada ⇒ montos nulos (`solicitud_aceptada_con_aplicacion`); su `estado_aviso_cliente` sí puede estar cargado."""
        s = solicitud_rechazada(discrepancia(self.entrega_de_suministro()))
        self.assertEqual((s.estado_solicitud, s.monto_descontado, s.monto_reintegrado, s.estado_aviso_cliente), ("rechazada", None, None, "enviado"))
        viola(self, lambda: self.actualizar(s, monto_descontado=Decimal("0.00")))

    def test_regla_las_restricciones_de_comercial_06a_siguen_vigentes(self):
        """Las tres restricciones de COM-06a no se reescribieron: una aceptada sin monto de indemnización y un monto en una no aceptada se rechazan."""
        s = discrepancia(self.entrega_de_suministro())
        viola(self, lambda: self.actualizar(s, monto_indemnizacion=Decimal("10.00")))
        viola(self, lambda: self.actualizar(s, estado_solicitud="aceptada", fecha_resolucion=HOY, gerente=self.gerente, monto_descontado=Decimal("0"), monto_reintegrado=Decimal("0")))


# ---- Suministro.solicitud_resolucion (D-69, punto 5) ----


class SuministroSolicitudResolucionTests(Base):
    def test_d69_5_solo_un_suministro_resuelto_puede_tener_la_solicitud_que_lo_resolvio(self):
        """Constraint `suministro_solicitud_resolucion_solo_resuelto`: un contrato «vigente» con `solicitud_resolucion` se rechaza; «resuelto» sí."""
        s = discrepancia_aceptada(self.entrega_de_suministro())
        viola(self, lambda: Suministro.objects.filter(pk=self.suministro.pk).update(solicitud_resolucion=s))
        resuelto = resolucion_del_suministro(self.suministro, s)
        self.assertEqual((resuelto.estado_suministro, resuelto.solicitud_resolucion_id), ("resuelto", s.pk))

    def test_d69_5_el_campo_nace_vacio_y_no_deja_relacion_inversa(self):
        """El campo es nulo al crear un suministro y `related_name="+"` no crea acceso inverso en la solicitud."""
        self.assertIsNone(Suministro.objects.get(pk=self.suministro.pk).solicitud_resolucion_id)
        self.assertFalse(hasattr(SolicitudRevision, "suministro_set"))

    def test_d69_5_la_clave_es_protect(self):
        """D-69, punto 5: `on_delete=PROTECT` (la solicitud que resolvió el contrato no se borra)."""
        self.assertIs(Suministro._meta.get_field("solicitud_resolucion").remote_field.on_delete, models.PROTECT)


# ---- Anulacion (MD-135, D-69 punto 10) ----


class AnulacionModeloTests(Base):
    def crear(self, solicitud=None, **campos):
        """Una `Anulacion` cruda, con la copia de una resolución «aceptada» por $100 y los `campos` pisados."""
        valores = dict(
            usuario=self.gerente,
            solicitud=solicitud,
            motivo_anulacion="Error de carga.",
            estado_anulado="aceptada",
            fecha_resolucion_anulada=HOY,
            gerente_anulado=self.gerente,
            monto_indemnizacion_anulado=Decimal("100.00"),
            monto_descontado_anulado=Decimal("100.00"),
            monto_reintegrado_anulado=Decimal("0.00"),
        )
        valores.update(campos)
        return Anulacion.objects.create(**valores)

    def setUp(self):
        self.solicitud = discrepancia_aceptada(self.entrega_de_suministro())

    def test_d69_10_es_hija_de_origen_documento_con_su_tipo(self):
        """MD-135: la anulación es hija directa de `OrigenDocumento`, con `tipo = anulacion` y la clave `origendocumento_ptr`."""
        a = self.crear(self.solicitud)
        self.assertEqual(Anulacion.TIPO_DE_ORIGEN, OrigenDocumento.Tipo.ANULACION)
        self.assertEqual(OrigenDocumento.objects.get(pk=a.pk).tipo, "anulacion")
        self.assertEqual(Anulacion._meta.pk.name, "origendocumento_ptr")

    def test_regla_el_motivo_es_obligatorio(self):
        """Constraint `anulacion_motivo_obligatorio`: el motivo no puede ser vacío (el largo y los espacios los verifica el servicio)."""
        viola(self, lambda: self.crear(self.solicitud, motivo_anulacion=""))
        self.assertEqual(self.crear(self.solicitud, motivo_anulacion="x" * 500).motivo_anulacion, "x" * 500)

    def test_regla_hasta_com_08b_toda_anulacion_es_de_una_solicitud(self):
        """Constraint `anulacion_con_solicitud` (COM-07a): `solicitud` no nula; COM-08b la reescribe como «exactamente uno de `solicitud` y `pago`»."""
        viola(self, lambda: self.crear(None))

    def test_regla_la_copia_lleva_el_estado_anulado_y_es_de_la_lista(self):
        """Constraints `anulacion_estado_con_solicitud` y `anulacion_estado_valido`: con solicitud, el estado anulado es `aceptada` o `rechazada`."""
        viola(self, lambda: self.crear(self.solicitud, estado_anulado=None, monto_indemnizacion_anulado=None))
        viola(self, lambda: self.crear(self.solicitud, estado_anulado="pendiente", monto_indemnizacion_anulado=None))

    def test_regla_aceptada_lleva_el_monto_y_rechazada_no(self):
        """Constraint `anulacion_aceptada_con_monto`: `estado_anulado = aceptada` ⇔ `monto_indemnizacion_anulado` no nulo."""
        viola(self, lambda: self.crear(self.solicitud, monto_indemnizacion_anulado=None))
        viola(self, lambda: self.crear(self.solicitud, estado_anulado="rechazada"))
        rechazada = self.crear(self.solicitud, estado_anulado="rechazada", monto_indemnizacion_anulado=None, monto_descontado_anulado=None, monto_reintegrado_anulado=None)
        self.assertEqual(rechazada.estado_anulado, "rechazada")

    def test_regla_el_medio_anulado_es_efectivo_o_transferencia(self):
        """Constraint `anulacion_medio_valido`."""
        viola(self, lambda: self.crear(self.solicitud, medio_reintegro_anulado="cheque"))
        self.assertEqual(self.crear(self.solicitud, medio_reintegro_anulado="transferencia", monto_reintegrado_anulado=Decimal("10.00")).medio_reintegro_anulado, "transferencia")

    def test_d69_10_una_solicitud_se_anula_mas_de_una_vez(self):
        """MD-135 (`related_name="anulaciones"`): una solicitud puede tener varias anulaciones, una por cada resolución."""
        self.crear(self.solicitud)
        self.crear(self.solicitud, motivo_anulacion="Otra vez.")
        self.assertEqual(self.solicitud.anulaciones.count(), 2)

    def test_d69_10_la_fabrica_copia_la_resolucion_y_vuelve_la_solicitud_a_pendiente(self):
        """La fábrica `anulacion` guarda la copia de lo anulado y deja la solicitud «pendiente», con el contador y los montos de las líneas vueltos atrás."""
        s = discrepancia_aceptada(self.otra_entrega_de_suministro(), monto="80.00", reintegrado="20.00", medio="efectivo", observaciones="Procede.")
        contador = Suministro.objects.get(pk=self.suministro.pk).cantidad_incumplimientos
        a = anulacion(s)
        s.refresh_from_db()
        self.assertEqual(
            (a.estado_anulado, a.monto_indemnizacion_anulado, a.monto_descontado_anulado, a.monto_reintegrado_anulado, a.medio_reintegro_anulado, a.observaciones_anuladas, a.gerente_anulado_id),
            ("aceptada", Decimal("80.00"), Decimal("60.00"), Decimal("20.00"), "efectivo", "Procede.", self.gerente.pk),
        )
        self.assertEqual((s.estado_solicitud, s.gerente_id, s.fecha_resolucion, s.monto_indemnizacion, s.estado_aviso_cliente), ("pendiente", None, None, None, None))
        self.assertEqual(Suministro.objects.get(pk=self.suministro.pk).cantidad_incumplimientos, contador - 1)
        self.assertEqual(list(LineaDiscrepancia.objects.filter(discrepancia_id=s.pk).values_list("monto_indemnizacion_linea", flat=True)), [None])
        verificar_invariantes_de_solicitudes()

    def test_d69_10_las_claves_son_protect(self):
        """`on_delete=PROTECT` en `solicitud`, `usuario` y `gerente_anulado` (las bajas son lógicas, `docs/modelo/comercial.md`, «Convenciones de esta ficha»)."""
        for campo in ("solicitud", "usuario", "gerente_anulado"):
            self.assertIs(Anulacion._meta.get_field(campo).remote_field.on_delete, models.PROTECT, campo)
        self.assertEqual(Anulacion._meta.get_field("usuario").remote_field.related_name, "anulaciones_hechas")

    def test_str_nombra_la_anulacion(self):
        """El texto de la auditoría (D-36): «Anulación #<id>»."""
        a = self.crear(self.solicitud)
        self.assertEqual(str(a), f"Anulación #{a.pk}")


# ---- las fábricas y los invariantes nuevos ----


class FabricasEInvariantesTests(Base):
    def test_las_fabricas_dejan_estados_coherentes_con_los_invariantes(self):
        """`discrepancia_aceptada`, `queja_aceptada` y `solicitud_rechazada` cumplen todos los invariantes (contador, montos, líneas) cuando se combinan en un mismo suministro."""
        discrepancia_aceptada(self.entrega_de_suministro(), monto="100.00")
        otra = self.otra_entrega_de_suministro()
        queja_aceptada(otra, "estado_mercaderia", monto="50.00", reintegrado="10.00", medio="efectivo")
        solicitud_rechazada(discrepancia(otra))
        self.assertEqual(Suministro.objects.get(pk=self.suministro.pk).cantidad_incumplimientos, 2)
        verificar_invariantes_de_solicitudes()

    def test_invariante_9_el_monto_a_cobrar_no_queda_negativo(self):
        """Lo descontado de una entrega no supera su total: con $1.500 descontados de $1.000, el invariante rompe."""
        entrega_ = self.entrega_de_suministro()
        self.assertEqual(entrega_.monto_total_entrega, Decimal("1000.00"))
        discrepancia_aceptada(entrega_, monto="1500.00", descontado="1500.00")
        self.rompe("el monto a cobrar queda negativo")

    def test_invariante_10_el_contador_es_la_cantidad_de_aceptadas(self):
        """`cantidad_incumplimientos` = solicitudes aceptadas del contrato: una aceptada sin sumar al contador rompe el invariante."""
        discrepancia_aceptada(self.entrega_de_suministro(), contar=False)
        self.rompe("incumplimientos y 1 solicitudes aceptadas")

    def test_invariante_11_el_monto_de_una_discrepancia_aceptada_es_la_suma_de_sus_lineas(self):
        """En una discrepancia aceptada, `monto_indemnizacion` = Σ `monto_indemnizacion_linea`."""
        s = discrepancia_aceptada(self.entrega_de_suministro(), monto="100.00")
        verificar_invariantes_de_solicitudes()
        LineaDiscrepancia.objects.filter(discrepancia_id=s.pk).update(monto_indemnizacion_linea=Decimal("5.00"))
        self.rompe("no es la suma de sus líneas")

    def test_invariante_12_una_pendiente_o_rechazada_no_tiene_montos_en_sus_lineas(self):
        """Una discrepancia pendiente con monto en una línea rompe el invariante, y una rechazada también."""
        s = discrepancia(self.entrega_de_suministro())
        LineaDiscrepancia.objects.filter(discrepancia_id=s.pk).update(monto_indemnizacion_linea=Decimal("3.00"))
        self.rompe("pendiente con montos en sus líneas")
        solicitud_rechazada(s)
        self.rompe("rechazada con montos en sus líneas")

    def test_los_invariantes_de_comercial_06a_y_06b_siguen_funcionando(self):
        """Una solicitud sin alerta rompe «con 0 alertas» (COM-06a), como antes."""
        discrepancia(self.entrega_de_suministro(), con_alerta=False)
        self.rompe("con 0 alertas")


# ---- la auditoría de `core` (D-36) ----


def _claves_del_diccionario(nombre):
    """Las claves de texto del diccionario `nombre` de la clase `RegistroAuditoria`, leídas del código (un literal con una clave repetida no falla en Python: se la pisa en silencio)."""
    arbol = ast.parse((Path(__file__).resolve().parents[2] / "core" / "models.py").read_text(encoding="utf-8"))
    for clase in (n for n in ast.walk(arbol) if isinstance(n, ast.ClassDef) and n.name == "RegistroAuditoria"):
        for nodo in clase.body:
            objetivos = [nodo.target] if isinstance(nodo, ast.AnnAssign) else getattr(nodo, "targets", [])
            if any(isinstance(o, ast.Name) and o.id == nombre for o in objetivos):
                return [k.value for k in nodo.value.keys if isinstance(k, ast.Constant)]
    raise AssertionError(f"No se encontró {nombre} en RegistroAuditoria.")


class AuditoriaDeSolicitudesTests(Base):
    CLAVES_NUEVAS = (
        "estado_solicitud", "monto_indemnizacion", "monto_indemnizacion_linea", "monto_descontado", "monto_reintegrado", "medio_reintegro", "observaciones_resolucion",
        "cantidad_incumplimientos", "monto_a_cobrar", "fecha_anulacion",
    )

    def test_d36_las_tres_acciones_nuevas_existen_y_son_de_negocio(self):
        """D-36: `evaluacion_discrepancia`, `resolucion_queja` y `anulacion_resolucion_solicitud` están en la lista cerrada y en `ACCIONES_DE_NEGOCIO`."""
        Accion = RegistroAuditoria.Accion
        for accion in (Accion.EVALUACION_DISCREPANCIA, Accion.RESOLUCION_QUEJA, Accion.ANULACION_RESOLUCION_SOLICITUD):
            self.assertIn(accion, Accion.values)
            self.assertIn(accion, ACCIONES_DE_NEGOCIO)
        self.assertEqual(
            (Accion.EVALUACION_DISCREPANCIA.value, Accion.RESOLUCION_QUEJA.value, Accion.ANULACION_RESOLUCION_SOLICITUD.value),
            ("evaluacion_discrepancia", "resolucion_queja", "anulacion_resolucion_solicitud"),
        )

    def test_d36_las_etiquetas_nuevas_estan_una_sola_vez(self):
        """D-36: cada campo nuevo tiene su etiqueta y la clave no está repetida en `ETIQUETAS` (un literal repetido pisaría la anterior sin avisar)."""
        claves = _claves_del_diccionario("ETIQUETAS")
        for clave in self.CLAVES_NUEVAS + ("fecha_resolucion", "gerente", "motivo_anulacion", "estado_aviso_cliente"):
            self.assertEqual(claves.count(clave), 1, clave)
            self.assertIn(clave, RegistroAuditoria.ETIQUETAS)

    def test_d36_los_valores_visibles_nuevos_estan_una_sola_vez(self):
        """D-36: `estado_solicitud` y `medio_reintegro` se muestran con su nombre y sin claves repetidas en `VALORES_VISIBLES`."""
        claves = _claves_del_diccionario("VALORES_VISIBLES")
        for clave in ("estado_solicitud", "medio_reintegro", "estado_aviso_cliente"):
            self.assertEqual(claves.count(clave), 1, clave)
        self.assertEqual(RegistroAuditoria.VALORES_VISIBLES["estado_solicitud"], {"pendiente": "Pendiente de revisión", "aceptada": "Aceptada", "rechazada": "Rechazada"})
        self.assertEqual(RegistroAuditoria.VALORES_VISIBLES["medio_reintegro"], {"efectivo": "Efectivo", "transferencia": "Transferencia"})

    def test_d36_un_registro_con_las_acciones_nuevas_se_guarda(self):
        """`RegistroAuditoria.objects.registrar` acepta las tres acciones con la solicitud como afectada y los campos nuevos en `cambios`."""
        s = discrepancia(self.entrega_de_suministro())
        for accion in (RegistroAuditoria.Accion.EVALUACION_DISCREPANCIA, RegistroAuditoria.Accion.RESOLUCION_QUEJA, RegistroAuditoria.Accion.ANULACION_RESOLUCION_SOLICITUD):
            registro = RegistroAuditoria.objects.registrar(
                usuario=self.gerente,
                accion=accion,
                afectados=[s],
                detalle={"cambios": {"estado_solicitud": {"antes": "pendiente", "despues": "aceptada"}, "monto_descontado": {"antes": None, "despues": "100.00"}}},
            )
            self.assertEqual(registro.accion, accion)

    def test_d52_el_tipo_anulacion_esta_en_origen_documento(self):
        """`OrigenDocumento.Tipo.ANULACION` existe para la migración de `choices` de `contabilidad` (D-69, punto 10)."""
        self.assertEqual(OrigenDocumento.Tipo.ANULACION.value, "anulacion")
        self.assertIn("anulacion", OrigenDocumento.Tipo.values)
