# Pruebas de USR-VNC-CTA (Vincular y Desvincular Cuenta) y de lo que cita: SEG-01, SEG-09, SEG-11, SEG-14,
# D-17 y D-22 (docs/casos_de_uso/usuarios.md). Las de servicio llaman a core.servicios.vincular_cuenta,
# desvincular_cuenta y cuenta_para_cambiar; las de concurrencia (TransactionTestCase) corren dos operaciones
# a la vez con core/tests/concurrencia.py. Las de vista (integración) se agregan después de implementar los
# servicios. Cada prueba arma sus propios datos. Los servicios se llaman a través del módulo (servicios.x)
# para que, mientras no existan, cada prueba falle por separado en vez de romper la importación del archivo.
#
# Contrato que fijan estas pruebas (tarea 06b):
# - vincular_cuenta(actor, email, contrasena) devuelve la OTRA cuenta (la que se vinculó). Un actor
#   Administrador o inactivo lanza PermissionDenied. Email o contraseña vacíos: ValidationError por campo
#   («email», «contrasena») con código «required». Los demás rechazos son ValidationError generales
#   (NON_FIELD_ERRORS) con estos códigos: «misma_cuenta», «ya_vinculada» y «no_se_pudo_vincular» (el mensaje
#   genérico de SEG-06: email inexistente, contraseña incorrecta, cuenta inactiva, con contraseña temporal,
#   vencida o no, o de Administrador). «misma_cuenta» y «ya_vinculada» solo se informan para la cuenta
#   propia y las de su propio grupo, que la persona ya conoce (regla 7).
#   Orden de las verificaciones de vincular_cuenta (D-32):
#   1. Antes de bloquear: el actor puede vincular; email y contraseña presentes; «misma_cuenta» y
#      «ya_vinculada» (solo propia cuenta y propio grupo); y la contraseña de la otra cuenta, junto con que
#      sea vinculable. Se verifica ANTES de bloquear porque calcular el resumen de una contraseña es lento y
#      no se deben mantener bloqueos tomados durante ese cálculo. Se guarda el resumen leído en ese momento.
#   2. Después de bloquear los grupos y las cuentas, con los datos releídos:
#      a. la otra cuenta sigue siendo vinculable (activa, sin contraseña temporal, no Administrador) y su
#         resumen de contraseña es el mismo que se verificó → si no, «no_se_pudo_vincular»;
#      b. recién entonces, si cambió el grupo de alguna de las dos cuentas respecto de lo leído antes de
#         bloquear → «cambio_simultaneo».
#      La verificación 2a va antes que la 2b porque un restablecimiento que disuelve el grupo de la otra
#      cuenta también le cambia el grupo: la persona tiene que recibir el mensaje genérico (la cuenta ya no
#      se puede vincular), no «las cuentas cambiaron». Cambiar el grupo de una cuenta que sigue siendo
#      vinculable sí es «cambio_simultaneo».
#   Punto de enganche: servicios._bloquear_para_vincular(...) es lo que toma los bloqueos. Las pruebas lo
#   envuelven para ejecutar un cambio justo entre la verificación de la contraseña y el bloqueo, como si otra
#   operación hubiera terminado en ese intervalo.
# - desvincular_cuenta(actor, cuenta_id) devuelve la cuenta que salió del grupo. Una cuenta que no está en el
#   grupo del actor, o que no existe, lanza PermissionDenied (misma respuesta para las dos: no revela cuáles
#   existen). La propia cuenta del actor es válida («Salir del grupo», regla 8).
# - cuenta_para_cambiar(actor, cuenta_id) (SEG-09) devuelve la cuenta a la que se pasa. Fuera del grupo del
#   actor (o inexistente), PermissionDenied; en el grupo pero inactiva o con contraseña temporal,
#   ValidationError «cuenta_no_disponible». No escribe ni audita (SEG-14).
# - Auditoría de la vinculación: accion VINCULACION, afectados = las dos cuentas y las que cambiaron de grupo,
#   detalle {"grupo": id del grupo resultante, "grupo_unido": id del grupo que se absorbió, o None}. De la
#   desvinculación: accion DESVINCULACION, afectados = la cuenta que sale y, si el grupo se disolvió, la que
#   quedaba, detalle {"grupo": id, "disuelto": bool}. Nunca contraseñas.
# - Si dos grupos se unen, queda el de menor id.

from datetime import timedelta
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from core import servicios
from core.models import (
    Agronomo,
    Capataz,
    GrupoCuentas,
    RegistroAuditoria,
    Tecnico,
    Usuario,
    Vendedor,
)
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import (
    CLAVE,
    agrupar,
    contenido_de_auditoria,
    crear_administrador,
    crear_cuenta,
    crear_gerente,
    poner_temporal,
)

# Textos exactos de las pantallas del prototipo (modalHtml 'link' y link-do).
MENSAJE_NO_SE_PUDO_VINCULAR = (
    "No pudimos vincular la cuenta. Revisá el email y la contraseña, y volvé a intentarlo."
)
MENSAJE_MISMA_CUENTA = "No podés vincular una cuenta consigo misma."
MENSAJE_YA_VINCULADA = "Esa cuenta ya está vinculada a la tuya."
MENSAJE_CAMBIO_SIMULTANEO = "Las cuentas cambiaron mientras hacías esto. Volvé a intentarlo."


def grupo_de(cuenta):
    """El id del grupo de la cuenta, leído de la base (``None`` si no tiene grupo)."""
    return Usuario.objects.get(pk=cuenta.pk).grupo_id


def ids_afectados(registro):
    """Los ids de las cuentas afectadas de un registro de auditoría (todas son ``core.usuario``)."""
    assert all(a["modelo"] == "core.usuario" for a in registro.afectados), registro.afectados
    return {a["id"] for a in registro.afectados}


def grupos_con_menos_de_dos_cuentas():
    """Los grupos que violan D-17: un grupo que queda con una sola cuenta (o vacío) deja de existir."""
    return list(GrupoCuentas.objects.annotate(n=Count("cuentas")).filter(n__lt=2))


class UsrVncCtaServicioTests(TestCase):
    """Reglas, precondiciones y postcondiciones de USR-VNC-CTA en los servicios de vincular, desvincular y
    cambiar de cuenta."""

    def crear_par(self):
        """Un Agrónomo (quien opera) y un Vendedor (la otra cuenta), activos y sin grupo."""
        return (
            crear_cuenta(Agronomo, email="agronomo@infoponia.com"),
            crear_cuenta(Vendedor, email="vendedor@infoponia.com"),
        )

    def assertVinculacionRechazada(self, actor, email, contrasena, codigo, mensaje):
        """``vincular_cuenta`` falla con un error general del código y el mensaje indicados."""
        with self.assertRaises(ValidationError) as contexto:
            servicios.vincular_cuenta(actor, email, contrasena)
        self.assertEqual(codigos(contexto.exception), [codigo])
        self.assertEqual(contexto.exception.messages, [mensaje])

    def entre_la_verificacion_y_el_bloqueo(self, cambio):
        """Contexto que ejecuta ``cambio()`` justo después de verificar la contraseña de la otra cuenta y antes
        de bloquear, y sigue con el bloqueo de siempre: simula otra operación que terminó en ese intervalo
        (ver «Punto de enganche» del encabezado). Sin ``_bloquear_para_vincular`` falla con AttributeError.

        Límite de la simulación: ``cambio()`` corre en la misma conexión y dentro de la transacción del
        servicio, así que si el servicio se rechaza, el cambio se deshace con ella (en la realidad lo habría
        confirmado otra transacción). Estas pruebas verifican qué responde el servicio y que no escribe
        nada propio; que dos operaciones reales se esperen entre sí lo prueban las de concurrencia."""
        original = servicios._bloquear_para_vincular

        def cambiar_y_bloquear(*args, **kwargs):
            cambio()
            return original(*args, **kwargs)

        return mock.patch.object(servicios, "_bloquear_para_vincular", side_effect=cambiar_y_bloquear)

    # ---- Vincular: postcondición a (grupos) ----

    def test_post_a_sin_grupos_crea_un_grupo_con_las_dos(self):
        """USR-VNC-CTA postcondición a: si ninguna de las dos cuentas tenía grupo, se creó uno con las dos."""
        agronomo, vendedor = self.crear_par()

        otra = servicios.vincular_cuenta(agronomo, vendedor.email, CLAVE)

        self.assertEqual(otra.pk, vendedor.pk)
        self.assertEqual(GrupoCuentas.objects.count(), 1)
        self.assertIsNotNone(grupo_de(agronomo))
        self.assertEqual(grupo_de(agronomo), grupo_de(vendedor))

    def test_post_a_suma_la_otra_cuenta_a_mi_grupo(self):
        """USR-VNC-CTA postcondición a: si solo la cuenta de la persona tenía grupo, la otra se sumó a ese
        grupo (no se crea otro)."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        grupo = agrupar(agronomo, capataz)

        servicios.vincular_cuenta(agronomo, vendedor.email, CLAVE)

        self.assertEqual(GrupoCuentas.objects.count(), 1)
        for cuenta in (agronomo, capataz, vendedor):
            self.assertEqual(grupo_de(cuenta), grupo.pk)

    def test_post_a_me_sumo_al_grupo_de_la_otra_cuenta(self):
        """USR-VNC-CTA postcondición a: si solo la otra cuenta tenía grupo, la cuenta de la persona se sumó
        a ese grupo."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        grupo = agrupar(vendedor, capataz)

        servicios.vincular_cuenta(agronomo, vendedor.email, CLAVE)

        self.assertEqual(GrupoCuentas.objects.count(), 1)
        for cuenta in (agronomo, capataz, vendedor):
            self.assertEqual(grupo_de(cuenta), grupo.pk)

    def test_regla_3_une_dos_grupos_en_uno_y_borra_el_otro(self):
        """USR-VNC-CTA regla 3 y postcondición a: si cada cuenta ya pertenecía a un grupo distinto, los dos
        grupos se unen en uno solo (el de menor id) y el otro deja de existir."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        tecnico = crear_cuenta(Tecnico, email="tecnico@infoponia.com")
        primero = agrupar(agronomo, capataz)
        segundo = agrupar(vendedor, tecnico)
        self.assertLess(primero.pk, segundo.pk)

        servicios.vincular_cuenta(agronomo, vendedor.email, CLAVE)

        self.assertEqual(GrupoCuentas.objects.count(), 1)
        for cuenta in (agronomo, capataz, vendedor, tecnico):
            self.assertEqual(grupo_de(cuenta), primero.pk)

    def test_regla_3_cuenta_del_mismo_grupo_informa_que_ya_esta_vinculada(self):
        """USR-VNC-CTA regla 3 y regla 7: si las dos cuentas ya están en el mismo grupo, no hay nada que
        vincular y el Sistema lo dice. No cambia nada ni deja registro."""
        agronomo, vendedor = self.crear_par()
        grupo = agrupar(agronomo, vendedor)

        self.assertVinculacionRechazada(
            agronomo, vendedor.email, CLAVE, "ya_vinculada", MENSAJE_YA_VINCULADA
        )

        self.assertEqual(GrupoCuentas.objects.count(), 1)
        self.assertEqual(grupo_de(vendedor), grupo.pk)
        self.assertFalse(RegistroAuditoria.objects.exists())

    # ---- Vincular: precondiciones y reglas ----

    def test_pre_a_una_cuenta_inactiva_no_vincula(self):
        """USR-VNC-CTA precondición a: la persona está identificada con una de sus cuentas. Una cuenta
        inactiva ya no puede operar (SEG-13)."""
        _, vendedor = self.crear_par()
        inactiva = crear_cuenta(Capataz, email="capataz@infoponia.com", activo=False)

        with self.assertRaises(PermissionDenied):
            servicios.vincular_cuenta(inactiva, vendedor.email, CLAVE)

        self.assertFalse(GrupoCuentas.objects.exists())

    def test_regla_1_pide_el_email_y_la_contrasena(self):
        """USR-VNC-CTA regla 1: la persona indica el email y la contraseña de la otra cuenta; si falta alguno,
        el error queda en su campo."""
        agronomo, _ = self.crear_par()

        with self.assertRaises(ValidationError) as contexto:
            servicios.vincular_cuenta(agronomo, "", "")

        self.assertEqual(set(contexto.exception.error_dict), {"email", "contrasena"})
        self.assertEqual(codigos(contexto.exception), ["required", "required"])
        self.assertFalse(GrupoCuentas.objects.exists())

    def test_regla_4_no_vincula_una_cuenta_consigo_misma(self):
        """USR-VNC-CTA regla 4 y regla 7: una cuenta no se vincula consigo misma, y el Sistema lo dice."""
        agronomo, _ = self.crear_par()

        self.assertVinculacionRechazada(
            agronomo, agronomo.email, CLAVE, "misma_cuenta", MENSAJE_MISMA_CUENTA
        )

        self.assertFalse(GrupoCuentas.objects.exists())

    def test_regla_4_rechaza_cuenta_inactiva_con_mensaje_generico(self):
        """USR-VNC-CTA regla 4 y SEG-06: una cuenta inactiva no se vincula, aunque el email y la contraseña
        sean correctos; el mensaje es el genérico y no dice que está inactiva."""
        agronomo, _ = self.crear_par()
        inactiva = crear_cuenta(Capataz, email="capataz@infoponia.com", activo=False)

        self.assertVinculacionRechazada(
            agronomo, inactiva.email, CLAVE, "no_se_pudo_vincular", MENSAJE_NO_SE_PUDO_VINCULAR
        )

        self.assertIsNone(grupo_de(inactiva))
        self.assertFalse(GrupoCuentas.objects.exists())

    def test_regla_4_rechaza_cuenta_con_contrasena_temporal_con_mensaje_generico(self):
        """USR-VNC-CTA regla 4, SEG-04 y SEG-06: una cuenta con contraseña temporal no se vincula (quien la
        vincula elegiría su contraseña sin conocer la actual); mensaje genérico. La contraseña indicada es
        la correcta: lo único que falla es que es temporal."""
        agronomo, vendedor = self.crear_par()
        poner_temporal(vendedor)

        self.assertVinculacionRechazada(
            agronomo, vendedor.email, CLAVE, "no_se_pudo_vincular", MENSAJE_NO_SE_PUDO_VINCULAR
        )

        self.assertIsNone(grupo_de(vendedor))
        self.assertFalse(GrupoCuentas.objects.exists())

    def test_regla_4_rechaza_cuenta_con_temporal_vencida_con_mensaje_generico(self):
        """USR-VNC-CTA regla 4, SEG-04 y SEG-06: igual con la contraseña temporal vencida (8 días); la
        contraseña indicada es la correcta."""
        agronomo, vendedor = self.crear_par()
        poner_temporal(vendedor, hace=timedelta(days=8))

        self.assertVinculacionRechazada(
            agronomo, vendedor.email, CLAVE, "no_se_pudo_vincular", MENSAJE_NO_SE_PUDO_VINCULAR
        )

        self.assertIsNone(grupo_de(vendedor))

    def test_regla_5_rechaza_cuenta_de_administrador_con_mensaje_generico(self):
        """USR-VNC-CTA regla 5 y SEG-06: una cuenta de Administrador no se vincula, aunque el email y la
        contraseña sean correctos; el mensaje es el genérico y no revela que es de un Administrador."""
        agronomo, _ = self.crear_par()
        administrador = crear_administrador()

        self.assertVinculacionRechazada(
            agronomo, administrador.email, CLAVE, "no_se_pudo_vincular", MENSAJE_NO_SE_PUDO_VINCULAR
        )

        self.assertIsNone(grupo_de(administrador))
        self.assertFalse(GrupoCuentas.objects.exists())

    def test_regla_5_el_administrador_no_vincula(self):
        """USR-VNC-CTA regla 5: las cuentas de Administrador no tienen vínculos; quien opera con una no
        puede vincular nada (SEG-13)."""
        administrador = crear_administrador()
        _, vendedor = self.crear_par()

        with self.assertRaises(PermissionDenied):
            servicios.vincular_cuenta(administrador, vendedor.email, CLAVE)

        self.assertFalse(GrupoCuentas.objects.exists())

    def test_regla_5_la_base_impide_que_un_administrador_tenga_grupo(self):
        """USR-VNC-CTA regla 5 y D-17: aunque un servicio lo intentara, la restricción
        ``administrador_sin_grupo`` de la base impide que una cuenta de Administrador tenga grupo."""
        administrador = crear_administrador()
        grupo = GrupoCuentas.objects.create()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.filter(pk=administrador.pk).update(grupo=grupo)

        self.assertIsNone(grupo_de(administrador))

    def test_regla_7_contrasena_incorrecta_da_mensaje_generico(self):
        """USR-VNC-CTA regla 7 y SEG-06: con la contraseña incorrecta, el mensaje es el genérico y no cambia
        nada."""
        agronomo, vendedor = self.crear_par()

        self.assertVinculacionRechazada(
            agronomo, vendedor.email, "otra-clave-999", "no_se_pudo_vincular", MENSAJE_NO_SE_PUDO_VINCULAR
        )

        self.assertIsNone(grupo_de(vendedor))
        self.assertFalse(GrupoCuentas.objects.exists())

    def test_regla_7_email_inexistente_da_mensaje_generico(self):
        """USR-VNC-CTA regla 7 y SEG-06: un email que no existe da el mismo mensaje, con el mismo código,
        que una contraseña incorrecta: no se puede averiguar qué cuentas existen."""
        agronomo, _ = self.crear_par()

        self.assertVinculacionRechazada(
            agronomo, "nadie@infoponia.com", CLAVE, "no_se_pudo_vincular", MENSAJE_NO_SE_PUDO_VINCULAR
        )

        self.assertFalse(GrupoCuentas.objects.exists())

    def test_regla_7_ya_vinculada_solo_se_informa_para_el_propio_grupo(self):
        """USR-VNC-CTA regla 7 (aprobado en la planificación de la 06b): «misma cuenta» y «ya vinculada» solo
        se informan para la cuenta propia y las de su propio grupo, que la persona ya conoce, así que no
        revelan nada de una cuenta ajena. Una cuenta de OTRO grupo, con la contraseña incorrecta, recibe el
        mensaje genérico, exactamente como una que no tiene grupo o no existe; con la contraseña correcta se
        vincula, sin ninguna advertencia."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        tecnico = crear_cuenta(Tecnico, email="tecnico@infoponia.com")
        agrupar(agronomo, vendedor)
        agrupar(capataz, tecnico)

        # Del propio grupo y la propia cuenta: se informa, aunque la contraseña esté mal.
        self.assertVinculacionRechazada(
            agronomo, vendedor.email, "otra-clave-999", "ya_vinculada", MENSAJE_YA_VINCULADA
        )
        self.assertVinculacionRechazada(
            agronomo, agronomo.email, "otra-clave-999", "misma_cuenta", MENSAJE_MISMA_CUENTA
        )
        # De otro grupo, con la contraseña mal: genérico, sin decir nada del grupo de esa cuenta.
        self.assertVinculacionRechazada(
            agronomo, capataz.email, "otra-clave-999", "no_se_pudo_vincular", MENSAJE_NO_SE_PUDO_VINCULAR
        )
        # De otro grupo, con la contraseña correcta: se vincula (los dos grupos se unen).
        servicios.vincular_cuenta(agronomo, capataz.email, CLAVE)
        self.assertEqual(GrupoCuentas.objects.count(), 1)

    # ---- Vincular: lo que cambia entre la verificación y el bloqueo (orden fijado en D-32) ----

    def test_regla_7_si_la_otra_cuenta_cambio_su_contrasena_tras_la_verificacion_no_se_vincula(self):
        """USR-VNC-CTA regla 1 y regla 7: la contraseña de la otra cuenta se verifica antes de bloquear y se
        guarda su resumen. Si su dueño la cambia (voluntariamente) entre la verificación y el bloqueo, la
        contraseña que la persona indicó ya no es la de la cuenta: mensaje genérico, sin vincular ni
        auditar. Sin esta comprobación se vincularía una cuenta con una contraseña que ya no sirve."""
        agronomo, vendedor = self.crear_par()

        def el_duenio_cambia_su_contrasena():
            cuenta = Usuario.objects.get(pk=vendedor.pk)
            cuenta.set_password("clave-nueva-del-duenio-123")
            cuenta.save(update_fields=["password"])

        with self.entre_la_verificacion_y_el_bloqueo(el_duenio_cambia_su_contrasena):
            self.assertVinculacionRechazada(
                agronomo, vendedor.email, CLAVE, "no_se_pudo_vincular", MENSAJE_NO_SE_PUDO_VINCULAR
            )

        self.assertIsNone(grupo_de(vendedor))
        self.assertFalse(GrupoCuentas.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_4_si_deja_de_ser_vinculable_tras_el_bloqueo_gana_el_mensaje_generico(self):
        """USR-VNC-CTA regla 4 y SEG-11 (orden de D-32): si, entre la verificación y el bloqueo, un
        restablecimiento le pone una contraseña temporal a la otra cuenta y disuelve su grupo, la cuenta ya
        no es vinculable Y además su grupo cambió. Se informa lo primero («no_se_pudo_vincular»), no «las
        cuentas cambiaron»: el mensaje genérico es el que no revela nada de una cuenta ajena."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        grupo = agrupar(vendedor, capataz)

        def restablecimiento_que_disuelve_el_grupo():
            Usuario.objects.filter(grupo_id=grupo.pk).update(grupo=None)
            GrupoCuentas.objects.filter(pk=grupo.pk).delete()
            poner_temporal(vendedor)

        with self.entre_la_verificacion_y_el_bloqueo(restablecimiento_que_disuelve_el_grupo):
            self.assertVinculacionRechazada(
                agronomo, vendedor.email, CLAVE, "no_se_pudo_vincular", MENSAJE_NO_SE_PUDO_VINCULAR
            )

        self.assertIsNone(grupo_de(agronomo))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_3_si_el_grupo_cambio_y_la_cuenta_sigue_vinculable_da_cambio_simultaneo(self):
        """USR-VNC-CTA regla 3 y D-17 (orden de D-32): si, entre la verificación y el bloqueo, la otra cuenta
        entra a un grupo (otra vinculación) y sigue siendo vinculable, el grupo con el que se iba a trabajar
        ya no es el que se leyó: se rechaza con «cambio_simultaneo» y no cambia nada. Es la contracara de la
        prueba anterior: el cambio de grupo solo gana cuando la cuenta sigue siendo vinculable."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")

        with self.entre_la_verificacion_y_el_bloqueo(lambda: agrupar(vendedor, capataz)):
            self.assertVinculacionRechazada(
                agronomo, vendedor.email, CLAVE, "cambio_simultaneo", MENSAJE_CAMBIO_SIMULTANEO
            )

        # El cambio simulado corre dentro de la transacción del servicio y se deshace con el rechazo (ver
        # ``entre_la_verificacion_y_el_bloqueo``): acá solo importa que el servicio no sumó nada propio.
        self.assertIsNone(grupo_de(agronomo))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_3_integrity_error_al_unir_los_grupos_da_cambio_simultaneo(self):
        """USR-VNC-CTA regla 3 y D-17 (D-32): si la base rechaza la escritura al unir los grupos (por ejemplo,
        un grupo que otra operación borró), el ``IntegrityError`` se informa como «cambio_simultaneo»; nunca
        llega a la pantalla (sería un error 500). Se traduce con «raise ... from error», no cambia nada ni
        deja registro."""
        agronomo, vendedor = self.crear_par()
        error = IntegrityError("falla simulada")

        with mock.patch.object(GrupoCuentas.objects, "create", side_effect=error):
            with self.assertRaises(ValidationError) as contexto:
                servicios.vincular_cuenta(agronomo, vendedor.email, CLAVE)

        self.assertEqual(codigos(contexto.exception), ["cambio_simultaneo"])
        self.assertEqual(contexto.exception.messages, [MENSAJE_CAMBIO_SIMULTANEO])
        self.assertIs(contexto.exception.__cause__, error)
        self.assertIsNone(grupo_de(agronomo))
        self.assertIsNone(grupo_de(vendedor))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_seg01_vincula_con_el_email_en_mayusculas(self):
        """SEG-01: el email se compara sin distinguir mayúsculas, igual que al identificarse."""
        agronomo, vendedor = self.crear_par()

        otra = servicios.vincular_cuenta(agronomo, "  VENDEDOR@Infoponia.COM ", CLAVE)

        self.assertEqual(otra.pk, vendedor.pk)
        self.assertEqual(grupo_de(agronomo), grupo_de(vendedor))

    # ---- Vincular: postcondición c (auditoría) ----

    def test_post_c_vincular_audita_las_cuentas_afectadas(self):
        """USR-VNC-CTA postcondición c, SEG-14 y D-22: queda un registro con quién actuó, su rol, la acción
        y las dos cuentas afectadas."""
        agronomo, vendedor = self.crear_par()

        servicios.vincular_cuenta(agronomo, vendedor.email, CLAVE)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.VINCULACION)
        self.assertEqual(registro.usuario_id, agronomo.pk)
        self.assertEqual(registro.rol, "agronomo")
        self.assertEqual(ids_afectados(registro), {agronomo.pk, vendedor.pk})
        self.assertEqual(registro.detalle, {"grupo": grupo_de(agronomo), "grupo_unido": None})

    def test_post_c_unir_dos_grupos_audita_las_cuentas_que_cambiaron_de_grupo(self):
        """USR-VNC-CTA postcondición c y regla 3: al unir dos grupos, el registro incluye las dos cuentas y
        las que pasaron al otro grupo (las del grupo que se absorbió), y el detalle nombra los dos grupos."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        tecnico = crear_cuenta(Tecnico, email="tecnico@infoponia.com")
        primero = agrupar(agronomo, capataz)
        segundo = agrupar(vendedor, tecnico)

        servicios.vincular_cuenta(agronomo, vendedor.email, CLAVE)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(ids_afectados(registro), {agronomo.pk, vendedor.pk, tecnico.pk})
        self.assertEqual(registro.detalle, {"grupo": primero.pk, "grupo_unido": segundo.pk})

    def test_post_c_la_auditoria_no_guarda_ninguna_contrasena(self):
        """USR-VNC-CTA postcondición c, SEG-02 y SEG-14: ni la contraseña indicada ni los resúmenes de las
        cuentas aparecen en el registro."""
        agronomo, vendedor = self.crear_par()

        servicios.vincular_cuenta(agronomo, vendedor.email, CLAVE)

        contenido = contenido_de_auditoria(RegistroAuditoria.objects.get())
        self.assertNotIn(CLAVE, contenido)
        for cuenta in (agronomo, vendedor):
            self.assertNotIn(Usuario.objects.get(pk=cuenta.pk).password, contenido)

    def test_d22_vinculacion_fallida_no_deja_registro(self):
        """D-22: una vinculación rechazada no deja registro de auditoría ni crea un grupo."""
        agronomo, vendedor = self.crear_par()

        with self.assertRaises(ValidationError):
            servicios.vincular_cuenta(agronomo, vendedor.email, "otra-clave-999")

        self.assertFalse(RegistroAuditoria.objects.exists())
        self.assertFalse(GrupoCuentas.objects.exists())

    # ---- Desvincular ----

    def test_post_b_desvincular_disuelve_un_grupo_de_dos(self):
        """USR-VNC-CTA postcondición b: si el grupo queda con una sola cuenta, el grupo deja de existir y
        esa cuenta queda sin grupo."""
        agronomo, vendedor = self.crear_par()
        agrupar(agronomo, vendedor)

        servicios.desvincular_cuenta(agronomo, vendedor.pk)

        self.assertIsNone(grupo_de(agronomo))
        self.assertIsNone(grupo_de(vendedor))
        self.assertFalse(GrupoCuentas.objects.exists())

    def test_post_b_desvincular_de_un_grupo_de_tres_mantiene_el_grupo(self):
        """USR-VNC-CTA postcondición b: si el grupo conserva dos cuentas o más, sigue existiendo."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        grupo = agrupar(agronomo, vendedor, capataz)

        servicios.desvincular_cuenta(agronomo, vendedor.pk)

        self.assertIsNone(grupo_de(vendedor))
        self.assertEqual(grupo_de(agronomo), grupo.pk)
        self.assertEqual(grupo_de(capataz), grupo.pk)
        self.assertEqual(GrupoCuentas.objects.count(), 1)

    def test_regla_8_desvincula_una_cuenta_inactiva_del_grupo(self):
        """USR-VNC-CTA regla 8: la persona puede desvincular cualquier cuenta de su grupo, también una
        inactiva (la baja no saca a la cuenta del grupo: regla 2 de USR-BAJ-USR)."""
        agronomo, _ = self.crear_par()
        inactiva = crear_cuenta(Capataz, email="capataz@infoponia.com", activo=False)
        tecnico = crear_cuenta(Tecnico, email="tecnico@infoponia.com")
        agrupar(agronomo, inactiva, tecnico)

        servicios.desvincular_cuenta(agronomo, inactiva.pk)

        self.assertIsNone(grupo_de(inactiva))
        self.assertEqual(grupo_de(agronomo), grupo_de(tecnico))
        self.assertIsNotNone(grupo_de(agronomo))

    def test_regla_8_sale_del_grupo_con_la_cuenta_con_la_que_opera(self):
        """USR-VNC-CTA regla 8 (D-32, «Salir del grupo»): la persona también puede sacar del grupo la cuenta
        con la que está operando. Las demás siguen juntas."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        agrupar(agronomo, vendedor, capataz)

        servicios.desvincular_cuenta(agronomo, agronomo.pk)

        self.assertIsNone(grupo_de(agronomo))
        self.assertEqual(grupo_de(vendedor), grupo_de(capataz))
        self.assertIsNotNone(grupo_de(vendedor))

    def test_pre_c_rechaza_desvincular_una_cuenta_de_otro_grupo(self):
        """USR-VNC-CTA precondición c: la cuenta que se desvincula tiene que ser del mismo grupo que la
        cuenta con la que opera la persona. Una de otro grupo, una sin grupo o un id que no existe dan la
        misma respuesta (PermissionDenied): no se revela cuáles existen. No cambia nada."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        tecnico = crear_cuenta(Tecnico, email="tecnico@infoponia.com")
        solo = crear_cuenta(Tecnico, email="solo@infoponia.com")
        propio = agrupar(agronomo, vendedor)
        ajeno = agrupar(capataz, tecnico)

        for cuenta_id in (capataz.pk, solo.pk, 999999):
            with self.subTest(cuenta_id=cuenta_id):
                with self.assertRaises(PermissionDenied):
                    servicios.desvincular_cuenta(agronomo, cuenta_id)
        with self.subTest(actor="sin grupo"):
            with self.assertRaises(PermissionDenied):
                servicios.desvincular_cuenta(solo, agronomo.pk)

        self.assertEqual(grupo_de(agronomo), propio.pk)
        self.assertEqual(grupo_de(vendedor), propio.pk)
        self.assertEqual(grupo_de(capataz), ajeno.pk)
        self.assertEqual(grupo_de(tecnico), ajeno.pk)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_post_c_desvincular_audita_las_cuentas_afectadas(self):
        """USR-VNC-CTA postcondición c y SEG-14: queda un registro con quién actuó, la acción, la cuenta que
        salió y el grupo, indicando que no se disolvió."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        grupo = agrupar(agronomo, vendedor, capataz)

        servicios.desvincular_cuenta(agronomo, vendedor.pk)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.DESVINCULACION)
        self.assertEqual(registro.usuario_id, agronomo.pk)
        self.assertEqual(registro.rol, "agronomo")
        self.assertEqual(ids_afectados(registro), {vendedor.pk})
        self.assertEqual(registro.detalle, {"grupo": grupo.pk, "disuelto": False})

    def test_post_c_desvincular_que_disuelve_el_grupo_audita_las_dos_cuentas(self):
        """USR-VNC-CTA postcondición c y postcondición b: si la desvinculación disuelve el grupo, el
        registro incluye también la cuenta que quedaba sola, y lo indica."""
        agronomo, vendedor = self.crear_par()
        grupo = agrupar(agronomo, vendedor)

        servicios.desvincular_cuenta(agronomo, vendedor.pk)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(ids_afectados(registro), {agronomo.pk, vendedor.pk})
        self.assertEqual(registro.detalle, {"grupo": grupo.pk, "disuelto": True})
        self.assertNotIn(CLAVE, contenido_de_auditoria(registro))

    # ---- Cambiar de cuenta (SEG-09) ----

    def test_seg09_pasa_a_otra_cuenta_activa_del_grupo(self):
        """SEG-09: desde una cuenta se puede pasar a otra cuenta activa de su grupo."""
        agronomo, vendedor = self.crear_par()
        agrupar(agronomo, vendedor)

        destino = servicios.cuenta_para_cambiar(agronomo, vendedor.pk)

        self.assertEqual(destino.pk, vendedor.pk)

    def test_seg09_rechaza_una_cuenta_inactiva_del_grupo(self):
        """SEG-09: antes de cambiar se verifica que la cuenta siga activa (la baja no la saca del grupo,
        regla 2 de USR-BAJ-USR, y puede darse después de abrir el menú)."""
        agronomo, _ = self.crear_par()
        inactiva = crear_cuenta(Capataz, email="capataz@infoponia.com", activo=False)
        agrupar(agronomo, inactiva)

        with self.assertRaises(ValidationError) as contexto:
            servicios.cuenta_para_cambiar(agronomo, inactiva.pk)

        self.assertEqual(codigos(contexto.exception), ["cuenta_no_disponible"])

    def test_seg09_rechaza_una_cuenta_fuera_del_grupo(self):
        """SEG-09: antes de cambiar se verifica que la cuenta esté en el grupo. Una de otro grupo, una sin
        grupo o un id que no existe dan PermissionDenied, y quien no tiene grupo no puede cambiar a nadie."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        tecnico = crear_cuenta(Tecnico, email="tecnico@infoponia.com")
        solo = crear_cuenta(Tecnico, email="solo@infoponia.com")
        agrupar(agronomo, vendedor)
        agrupar(capataz, tecnico)

        for cuenta_id in (capataz.pk, solo.pk, 999999):
            with self.subTest(cuenta_id=cuenta_id):
                with self.assertRaises(PermissionDenied):
                    servicios.cuenta_para_cambiar(agronomo, cuenta_id)
        with self.subTest(actor="sin grupo"):
            with self.assertRaises(PermissionDenied):
                servicios.cuenta_para_cambiar(solo, agronomo.pk)

    def test_seg09_rechaza_una_cuenta_con_contrasena_temporal(self):
        """SEG-09, SEG-04 y SEG-11: no se pasa a una cuenta con contraseña temporal, por si la cuenta quedó
        en el grupo con una temporal (la pantalla «Elegí tu contraseña» no pide la actual: quien pasara
        podría elegir la contraseña de una cuenta que alguien restableció para recuperarla)."""
        agronomo, vendedor = self.crear_par()
        agrupar(agronomo, vendedor)
        poner_temporal(vendedor)

        with self.assertRaises(ValidationError) as contexto:
            servicios.cuenta_para_cambiar(agronomo, vendedor.pk)

        self.assertEqual(codigos(contexto.exception), ["cuenta_no_disponible"])

    def test_seg14_el_cambio_de_cuenta_no_se_audita(self):
        """SEG-14 y SEG-09: el cambio de cuenta vinculada no se audita ni cambia nada."""
        agronomo, vendedor = self.crear_par()
        grupo = agrupar(agronomo, vendedor)

        servicios.cuenta_para_cambiar(agronomo, vendedor.pk)

        self.assertFalse(RegistroAuditoria.objects.exists())
        self.assertEqual(grupo_de(agronomo), grupo.pk)
        self.assertEqual(grupo_de(vendedor), grupo.pk)


class UsrVncCtaConsultasTests(TestCase):
    """Consultas de solo lectura que usan las pantallas: las cuentas vinculadas de una cuenta (Mi perfil, el menú
    de cuenta y la ficha de quien gestiona) y la cuenta de mi grupo para la ventana de desvincular. Nada de
    esto se audita (SEG-14).

    Contrato: ``cuentas_vinculadas(cuenta, actor=None)`` devuelve una lista con las OTRAS cuentas del grupo de
    ``cuenta``, ordenada, sin consultar la base si no tiene grupo. Cada una lleva ``se_puede_pasar`` (SEG-09:
    activa, sin contraseña temporal y no Administrador) y, si se indica ``actor`` (quien gestiona la cuenta que
    se mira), ``en_alcance``: si está dentro de lo que ``actor`` gestiona (``en_alcance_de``), para decidir si
    se la enlaza a su ficha. ``obtener_cuenta_del_grupo(actor, cuenta_id)`` devuelve la propia cuenta o una de
    su grupo; cualquier otra, sin grupo o inexistente, ``PermissionDenied`` (D-32).
    """

    def test_regla_6_cuentas_vinculadas_lista_las_otras_cuentas_del_grupo(self):
        """USR-GST-PRF regla 1 y USR-CNS-USR regla 3: las cuentas vinculadas son las otras del grupo, sin la
        propia ni las de otros grupos."""
        agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        ajena = crear_cuenta(Tecnico, email="tecnico@infoponia.com")
        agrupar(agronomo, vendedor, capataz)
        agrupar(ajena, crear_cuenta(Tecnico, email="otro@infoponia.com"))

        otras = servicios.cuentas_vinculadas(agronomo)

        self.assertEqual({c.pk for c in otras}, {vendedor.pk, capataz.pk})
        self.assertEqual(len(otras), 2)

    def test_regla_6_cuentas_vinculadas_sin_grupo_esta_vacia_y_no_consulta_la_base(self):
        """USR-VNC-CTA regla 5 y D-17: una cuenta sin grupo (también la del Administrador) no tiene cuentas
        vinculadas, y saberlo no cuesta una consulta: el menú de cuenta lo pregunta en cada pantalla."""
        agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")
        administrador = crear_administrador()

        with self.assertNumQueries(0):
            self.assertEqual(servicios.cuentas_vinculadas(agronomo), [])
            self.assertEqual(servicios.cuentas_vinculadas(administrador), [])

    def test_seg09_cuentas_vinculadas_indica_a_cuales_se_puede_pasar(self):
        """SEG-09 y SEG-04: se puede pasar a una cuenta activa y sin contraseña temporal; no a una inactiva ni
        a una con temporal. El menú de cuenta y Mi perfil muestran «Cambiar» solo donde el servicio lo
        aceptaría."""
        agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")
        normal = crear_cuenta(Vendedor, email="normal@infoponia.com")
        inactiva = crear_cuenta(Capataz, email="inactiva@infoponia.com", activo=False)
        con_temporal = crear_cuenta(Tecnico, email="temporal@infoponia.com")
        agrupar(agronomo, normal, inactiva, con_temporal)
        poner_temporal(con_temporal)

        por_email = {c.email: c.se_puede_pasar for c in servicios.cuentas_vinculadas(agronomo)}

        self.assertEqual(
            por_email,
            {normal.email: True, inactiva.email: False, con_temporal.email: False},
        )

    def test_regla_6_cuentas_vinculadas_marca_las_que_estan_en_el_alcance_de_quien_mira(self):
        """USR-CNS-USR regla 3, USR-MOD-USR regla 7 y D-28: quien gestiona una cuenta ve sus vínculos en solo
        lectura; solo las cuentas que él gestiona (``en_alcance_de``) se pueden enlazar a su ficha. El
        Gerente no gestiona al Gerente ni a los Administradores; el Administrador no gestiona a los demás
        roles."""
        gerente = crear_gerente()
        administrador = crear_administrador()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        agrupar(capataz, gerente, vendedor)

        # El Gerente mira la ficha del Capataz: su propia cuenta de Gerente no está en su alcance.
        vistas_por_el_gerente = {
            c.email: c.en_alcance for c in servicios.cuentas_vinculadas(capataz, actor=gerente)
        }
        self.assertEqual(vistas_por_el_gerente, {gerente.email: False, vendedor.email: True})

        # El Administrador mira la ficha del Gerente: sus vínculos son de otros roles (fuera de su alcance).
        vistas_por_el_administrador = {
            c.email: c.en_alcance for c in servicios.cuentas_vinculadas(gerente, actor=administrador)
        }
        self.assertEqual(
            vistas_por_el_administrador,
            {capataz.email: False, vendedor.email: False},
        )

    def test_regla_6_el_administrador_enlaza_a_un_gerente_anterior_del_mismo_grupo(self):
        """USR-MOD-USR regla 7 y D-16: el Administrador gestiona todas las cuentas de Gerente (la activa y las
        anteriores), así que un Gerente anterior vinculado a otro Gerente sí está en su alcance."""
        administrador = crear_administrador()
        activo = crear_gerente()
        anterior = crear_gerente(email="anterior@infoponia.com", activo=False)
        agrupar(activo, anterior)

        vistas = {
            c.email: c.en_alcance for c in servicios.cuentas_vinculadas(activo, actor=administrador)
        }

        self.assertEqual(vistas, {anterior.email: True})

    def test_pre_c_obtener_cuenta_del_grupo_devuelve_la_propia_y_las_del_grupo(self):
        """USR-VNC-CTA precondición c y regla 8: la ventana de desvincular puede referirse a la propia cuenta
        («Salir del grupo») o a otra de su grupo, aunque esté inactiva."""
        agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")
        inactiva = crear_cuenta(Capataz, email="capataz@infoponia.com", activo=False)
        agrupar(agronomo, inactiva)

        self.assertEqual(servicios.obtener_cuenta_del_grupo(agronomo, agronomo.pk).pk, agronomo.pk)
        self.assertEqual(servicios.obtener_cuenta_del_grupo(agronomo, inactiva.pk).pk, inactiva.pk)

    def test_pre_c_obtener_cuenta_del_grupo_rechaza_cualquier_otra_con_permission_denied(self):
        """USR-VNC-CTA precondición c y D-32: una cuenta de otro grupo, una sin grupo o un id que no existe
        dan la misma respuesta, para que nadie pruebe ids y averigüe cuáles existen; quien no tiene grupo
        solo puede referirse a su propia cuenta, y el Administrador no tiene vínculos (regla 5)."""
        agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com")
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        ajena = crear_cuenta(Capataz, email="capataz@infoponia.com")
        sola = crear_cuenta(Tecnico, email="sola@infoponia.com")
        agrupar(agronomo, vendedor)
        agrupar(ajena, crear_cuenta(Tecnico, email="otro@infoponia.com"))
        administrador = crear_administrador()

        for cuenta_id in (ajena.pk, sola.pk, 999999):
            with self.subTest(cuenta_id=cuenta_id):
                with self.assertRaises(PermissionDenied):
                    servicios.obtener_cuenta_del_grupo(agronomo, cuenta_id)
        with self.subTest(actor="sin grupo"):
            with self.assertRaises(PermissionDenied):
                servicios.obtener_cuenta_del_grupo(sola, agronomo.pk)
            self.assertEqual(servicios.obtener_cuenta_del_grupo(sola, sola.pk).pk, sola.pk)
        with self.subTest(actor="administrador"):
            with self.assertRaises(PermissionDenied):
                servicios.obtener_cuenta_del_grupo(administrador, administrador.pk)


class UsrVncCtaVistaTests(TestCase):
    """Flujos principales de USR-VNC-CTA y SEG-09 con el cliente de prueba: Mi perfil, las ventanas de vincular y
    desvincular, el menú de cuenta, el cambio de cuenta y la ficha de quien gestiona. Las ventanas se piden de
    las dos formas: con HTMX (solo la ventana) y sin JavaScript (Mi perfil con la ventana abierta)."""

    HTMX = {"HX-Request": "true"}

    def entrar(self, cuenta):
        """Abre una sesión con ``cuenta`` y la devuelve."""
        self.client.force_login(cuenta)
        return cuenta

    def cookie_de_sesion(self):
        """El identificador de sesión que tiene el navegador."""
        return self.client.cookies["sessionid"].value

    def cuenta_en_sesion(self):
        """El id de la cuenta con la que opera el navegador, o ``None``."""
        return self.client.session.get("_auth_user_id")

    def crear_par(self):
        """Un Agrónomo (quien opera) y un Vendedor (la otra cuenta), activos y sin grupo."""
        return (
            crear_cuenta(Agronomo, email="agronomo@infoponia.com", nombre="Ana", apellido="Ibáñez"),
            crear_cuenta(Vendedor, email="vendedor@infoponia.com", nombre="Vera", apellido="Sáenz"),
        )

    # ---- Vincular ----

    def test_flujo_principal_vincula_desde_mi_perfil(self):
        """USR-VNC-CTA flujo principal (vPerfil y ventana 'link'): desde Mi perfil, la persona abre la ventana,
        indica el email y la contraseña de la otra cuenta y las dos quedan vinculadas. Abrir la ventana no
        cambia nada; al vincular vuelve a Mi perfil con el aviso y la cuenta en la lista; queda el registro
        de auditoría."""
        agronomo, vendedor = self.crear_par()
        self.entrar(agronomo)
        perfil = self.client.get(reverse("core:mi_perfil"))
        self.assertContains(perfil, "Todavía no vinculaste ninguna cuenta.")
        self.assertContains(perfil, "Vincular cuenta")

        ventana = self.client.get(reverse("core:vincular_cuenta"))  # sin JavaScript: Mi perfil con la ventana
        self.assertContains(ventana, "Ingresá el email y la contraseña de la otra cuenta")
        self.assertContains(ventana, "data-ventana")
        self.assertFalse(GrupoCuentas.objects.exists())

        respuesta = self.client.post(
            reverse("core:vincular_cuenta"),
            {"email": "vendedor@infoponia.com", "contrasena": CLAVE},
            follow=True,
        )

        self.assertRedirects(respuesta, reverse("core:mi_perfil"))
        self.assertContains(respuesta, "Cuenta vinculada: vendedor@infoponia.com (Vendedor).")
        self.assertContains(respuesta, "Cambiar</button>")  # la cuenta quedó en la lista, y se puede pasar a ella
        self.assertNotContains(respuesta, "Todavía no vinculaste ninguna cuenta.")
        self.assertEqual(grupo_de(agronomo), grupo_de(vendedor))
        self.assertIsNotNone(grupo_de(agronomo))
        self.assertEqual(
            RegistroAuditoria.objects.get().accion, RegistroAuditoria.Accion.VINCULACION
        )

    def test_flujo_principal_la_ventana_de_vincular_con_htmx_es_solo_la_ventana(self):
        """D-28 y D-24: con HTMX, la ventana de vincular llega sola (se inserta sobre Mi perfil) y abrirla no
        cambia nada; sin HTMX llega la pantalla entera. La contraseña no tiene valor precargado."""
        agronomo, _ = self.crear_par()
        self.entrar(agronomo)

        con_htmx = self.client.get(reverse("core:vincular_cuenta"), headers=self.HTMX)
        sin_htmx = self.client.get(reverse("core:vincular_cuenta"))

        self.assertContains(con_htmx, "data-ventana")
        self.assertNotContains(con_htmx, "<html")
        self.assertContains(sin_htmx, "<html")
        self.assertContains(sin_htmx, "Cambiar contraseña")  # Mi perfil, con la ventana encima
        self.assertFalse(GrupoCuentas.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_7_la_ventana_muestra_el_mensaje_generico(self):
        """USR-VNC-CTA regla 7 y SEG-06: si el email o la contraseña de la otra cuenta son incorrectos, la ventana
        vuelve con el mismo mensaje genérico, sin decir qué dato falló ni si la cuenta existe; conserva el email
        escrito, nunca la contraseña, y no cambia nada."""
        agronomo, _ = self.crear_par()
        self.entrar(agronomo)
        mensaje = "No pudimos vincular la cuenta. Revisá el email y la contraseña, y volvé a intentarlo."

        for causa, email, clave in (
            ("contraseña incorrecta", "vendedor@infoponia.com", "otra-clave-999"),
            ("email inexistente", "nadie@infoponia.com", CLAVE),
        ):
            with self.subTest(causa=causa):
                respuesta = self.client.post(
                    reverse("core:vincular_cuenta"), {"email": email, "contrasena": clave}
                )

                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, mensaje, count=1)
                self.assertContains(respuesta, f'value="{email}"')
                self.assertNotContains(respuesta, clave)
        self.assertFalse(GrupoCuentas.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_7_la_ventana_informa_la_cuenta_propia_y_la_ya_vinculada(self):
        """USR-VNC-CTA regla 7: cuando la cuenta indicada es la misma con la que opera, o ya está en su grupo, la
        ventana lo dice (no revela nada de una cuenta ajena)."""
        agronomo, vendedor = self.crear_par()
        agrupar(agronomo, vendedor)
        self.entrar(agronomo)

        propia = self.client.post(
            reverse("core:vincular_cuenta"), {"email": agronomo.email, "contrasena": CLAVE}
        )
        del_grupo = self.client.post(
            reverse("core:vincular_cuenta"), {"email": vendedor.email, "contrasena": CLAVE}
        )

        self.assertContains(propia, "No podés vincular una cuenta consigo misma.")
        self.assertContains(del_grupo, "Esa cuenta ya está vinculada a la tuya.")

    def test_regla_1_la_ventana_pide_el_email_y_la_contrasena(self):
        """USR-VNC-CTA regla 1: si falta el email o la contraseña, el error aparece junto a cada campo."""
        agronomo, _ = self.crear_par()
        self.entrar(agronomo)

        respuesta = self.client.post(reverse("core:vincular_cuenta"), {"email": "", "contrasena": ""})

        self.assertContains(respuesta, "Ingresá el email de la otra cuenta.")
        self.assertContains(respuesta, "Ingresá la contraseña de la otra cuenta.")

    # ---- Desvincular y salir del grupo ----

    def test_flujo_principal_desvincula_desde_mi_perfil(self):
        """USR-VNC-CTA flujo principal (ventana 'unlink'): la persona pide desvincular una cuenta de su grupo,
        la ventana pide confirmar (abrirla no cambia nada), y al confirmar la cuenta sale del grupo, con aviso y
        registro de auditoría. Las demás siguen juntas."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        agrupar(agronomo, vendedor, capataz)
        self.entrar(agronomo)
        url = reverse("core:desvincular_cuenta", args=[vendedor.pk])

        ventana = self.client.get(url)  # sin JavaScript
        self.assertContains(ventana, "¿Desvincular esta cuenta?")
        self.assertContains(ventana, "vendedor@infoponia.com")
        self.assertEqual(grupo_de(vendedor), grupo_de(agronomo))  # abrir la ventana no cambió nada

        respuesta = self.client.post(url, follow=True)

        self.assertRedirects(respuesta, reverse("core:mi_perfil"))
        self.assertContains(respuesta, "Se desvinculó vendedor@infoponia.com.")
        self.assertIsNone(grupo_de(vendedor))
        self.assertEqual(grupo_de(agronomo), grupo_de(capataz))
        self.assertEqual(
            RegistroAuditoria.objects.get().accion, RegistroAuditoria.Accion.DESVINCULACION
        )

    def test_regla_8_salir_del_grupo_desde_mi_perfil(self):
        """USR-VNC-CTA regla 8 (D-32): Mi perfil ofrece «Salir del grupo»; la ventana pregunta por la propia
        cuenta y, al confirmar, la cuenta con la que se opera sale del grupo."""
        agronomo, vendedor = self.crear_par()
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        agrupar(agronomo, vendedor, capataz)
        self.entrar(agronomo)
        self.assertContains(self.client.get(reverse("core:mi_perfil")), "Salir del grupo")
        url = reverse("core:desvincular_cuenta", args=[agronomo.pk])

        self.assertContains(self.client.get(url), "¿Salir del grupo de cuentas vinculadas?")
        respuesta = self.client.post(url, follow=True)

        self.assertContains(respuesta, "Saliste del grupo de cuentas vinculadas.")
        self.assertNotContains(respuesta, "Salir del grupo</a>")  # ya no tiene grupo
        self.assertIsNone(grupo_de(agronomo))
        self.assertEqual(grupo_de(vendedor), grupo_de(capataz))

    def test_d32_la_ventana_de_desvincular_de_una_cuenta_ajena_da_403(self):
        """D-32 y precondición c: una cuenta de otro grupo, una sin grupo y un id que no existe dan el mismo 403
        (también al abrir la ventana), para que nadie pruebe ids desde Mi perfil y averigüe cuáles existen. No
        cambia nada."""
        agronomo, vendedor = self.crear_par()
        ajena = crear_cuenta(Capataz, email="capataz@infoponia.com")
        sola = crear_cuenta(Tecnico, email="sola@infoponia.com")
        agrupar(agronomo, vendedor)
        agrupar(ajena, crear_cuenta(Tecnico, email="otro@infoponia.com"))
        self.entrar(agronomo)

        for cuenta_id in (ajena.pk, sola.pk, 999999):
            for metodo in (self.client.get, self.client.post):
                with self.subTest(cuenta_id=cuenta_id, metodo=metodo.__name__):
                    respuesta = metodo(reverse("core:desvincular_cuenta", args=[cuenta_id]))
                    self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(grupo_de(agronomo), grupo_de(vendedor))
        self.assertFalse(RegistroAuditoria.objects.exists())

    # ---- Cambiar de cuenta (SEG-09) ----

    def test_seg09_cambiar_de_cuenta_genera_sesion_nueva_y_llega_al_inicio(self):
        """SEG-09: desde el menú de cuenta se pasa a otra cuenta del grupo sin volver a identificarse. La sesión
        pasa a la otra cuenta con un identificador de sesión nuevo (no se reutiliza el de la cuenta
        anterior), la persona llega al inicio, que indica con qué rol y cuenta opera, y el cambio no se audita
        (SEG-14). No hay un aviso de éxito que repita lo que ya dice el inicio (D-32, 14/11/2026)."""
        agronomo, vendedor = self.crear_par()
        agrupar(agronomo, vendedor)
        self.entrar(agronomo)
        sesion_anterior = self.cookie_de_sesion()

        respuesta = self.client.post(
            reverse("core:cambiar_de_cuenta"), {"cuenta_id": vendedor.pk}, follow=True
        )

        self.assertRedirects(respuesta, reverse("core:inicio"))
        self.assertEqual(self.cuenta_en_sesion(), str(vendedor.pk))
        self.assertNotEqual(self.cookie_de_sesion(), sesion_anterior)
        # SEG-09: el inicio indica con qué rol y con qué cuenta se opera...
        self.assertRegex(
            respuesta.content.decode(),
            r'Operás como <b[^>]*>Vendedor</b> con la cuenta <span class="mono">vendedor@infoponia\.com</span>',
        )
        # ...y por eso no se suma un aviso breve que lo repita (antes: «Operás como Vendedor · Vera Sáenz»).
        self.assertNotContains(respuesta, "data-aviso")
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_seg09_la_sesion_anterior_ya_no_sirve_despues_del_cambio(self):
        """SEG-09: ``login()`` vacía la sesión anterior en el servidor, no solo en el navegador: quien conserva
        la cookie de antes del cambio ya no entra con ella."""
        agronomo, vendedor = self.crear_par()
        agrupar(agronomo, vendedor)
        self.entrar(agronomo)
        sesion_anterior = self.cookie_de_sesion()
        self.client.post(reverse("core:cambiar_de_cuenta"), {"cuenta_id": vendedor.pk})

        navegador_viejo = self.client_class()
        navegador_viejo.cookies["sessionid"] = sesion_anterior
        respuesta = navegador_viejo.get(reverse("core:inicio"))

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith(reverse("core:iniciar_sesion")))

    def test_seg09_cambiar_de_cuenta_solo_acepta_post(self):
        """SEG-09: cambiar de cuenta cambia la sesión, así que solo se hace con un POST (con CSRF); un GET no
        cambia nada."""
        agronomo, vendedor = self.crear_par()
        agrupar(agronomo, vendedor)
        self.entrar(agronomo)

        respuesta = self.client.get(reverse("core:cambiar_de_cuenta"), {"cuenta_id": vendedor.pk})

        self.assertEqual(respuesta.status_code, 405)
        self.assertEqual(self.cuenta_en_sesion(), str(agronomo.pk))

    def test_seg09_cambiar_a_una_cuenta_fuera_del_grupo_da_403(self):
        """SEG-09 y D-32: una cuenta de otro grupo, una sin grupo, un id que no existe o un dato mal formado dan
        403, y la sesión sigue con la cuenta de antes."""
        agronomo, vendedor = self.crear_par()
        ajena = crear_cuenta(Capataz, email="capataz@infoponia.com")
        agrupar(agronomo, vendedor)
        agrupar(ajena, crear_cuenta(Tecnico, email="otro@infoponia.com"))
        self.entrar(agronomo)

        for dato in (str(ajena.pk), "999999", "no-es-un-numero", ""):
            with self.subTest(cuenta_id=dato):
                respuesta = self.client.post(reverse("core:cambiar_de_cuenta"), {"cuenta_id": dato})
                self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.cuenta_en_sesion(), str(agronomo.pk))

    def test_seg09_cambiar_a_una_cuenta_inactiva_avisa_y_no_cambia(self):
        """SEG-09: si la cuenta se dio de baja después de abrir el menú, el cambio se rechaza con un aviso y la
        persona sigue con su cuenta, en su inicio."""
        agronomo, _ = self.crear_par()
        inactiva = crear_cuenta(Capataz, email="capataz@infoponia.com", activo=False)
        agrupar(agronomo, inactiva)
        self.entrar(agronomo)

        respuesta = self.client.post(
            reverse("core:cambiar_de_cuenta"), {"cuenta_id": inactiva.pk}, follow=True
        )

        self.assertRedirects(respuesta, reverse("core:inicio"))
        self.assertContains(respuesta, "No se puede pasar a esa cuenta ahora")
        self.assertEqual(self.cuenta_en_sesion(), str(agronomo.pk))

    def test_seg09_el_menu_de_cuenta_lista_el_grupo_y_deshabilita_las_inactivas(self):
        """SEG-09 (accountPop): el menú de cuenta lista las otras cuentas del grupo; a las activas se pasa con un
        botón, y las inactivas se ven deshabilitadas, con la insignia «Inactiva»."""
        agronomo, vendedor = self.crear_par()
        inactiva = crear_cuenta(Capataz, email="inactiva@infoponia.com", activo=False)
        agrupar(agronomo, vendedor, inactiva)
        self.entrar(agronomo)

        html = self.client.get(reverse("core:inicio")).content.decode()

        self.assertIn("Cambiar de cuenta", html)
        self.assertIn(f'action="{reverse("core:cambiar_de_cuenta")}"', html)
        self.assertRegex(html, r'<button class="acc-item" type="submit">\s*<div class="avatar"[^>]*>VEN</div>')
        self.assertRegex(
            html,
            r'(?s)<button class="acc-item" type="submit" disabled>.*?inactiva@infoponia\.com.*?Inactiva',
        )
        # La cuenta propia no figura en la lista de cuentas a las que se pasa.
        self.assertNotRegex(html, r'name="cuenta_id" value="%d"' % agronomo.pk)

    def test_seg09_el_menu_sin_vinculos_lo_dice(self):
        """SEG-09 (accountPop): sin cuentas vinculadas, el menú lo dice y manda a Mi perfil."""
        agronomo, _ = self.crear_par()
        self.entrar(agronomo)

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(
            respuesta, "No tenés cuentas vinculadas. Podés vincularlas desde Mi perfil."
        )

    def test_seg09_la_sesion_pasada_se_cierra_si_restablecen_la_cuenta(self):
        """SEG-09, SEG-11 y SEG-10: después de pasar a otra cuenta, la sesión guarda el resumen de contraseña de
        esa cuenta. Si el Gerente la restablece, Django cierra esa sesión en el pedido siguiente (no hace
        falta bloquear nada al cambiar de cuenta)."""
        agronomo, vendedor = self.crear_par()
        agrupar(agronomo, vendedor)
        gerente = crear_gerente()
        self.entrar(agronomo)
        self.client.post(reverse("core:cambiar_de_cuenta"), {"cuenta_id": vendedor.pk})
        self.assertEqual(self.client.get(reverse("core:inicio")).status_code, 200)

        servicios.restablecer_contrasena(gerente, vendedor.pk)

        respuesta = self.client.get(reverse("core:inicio"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith(reverse("core:iniciar_sesion")))

    # ---- El Administrador no tiene vínculos (regla 5) ----

    def test_regla_5_el_administrador_no_ve_vincular(self):
        """USR-VNC-CTA regla 5 y SEG-13: Mi perfil del Administrador dice que sus cuentas no se vinculan y no
        ofrece vincular; el menú de cuenta no tiene «Cambiar de cuenta»; las direcciones de vincular,
        desvincular y cambiar dan 403."""
        administrador = self.entrar(crear_administrador())

        perfil = self.client.get(reverse("core:mi_perfil"))
        self.assertContains(perfil, "Las cuentas de Administrador no se vinculan con otras.")
        self.assertNotContains(perfil, "Vincular cuenta")
        self.assertNotContains(self.client.get(reverse("core:usuarios")), "Cambiar de cuenta")
        self.assertEqual(self.client.get(reverse("core:vincular_cuenta")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("core:vincular_cuenta"), {"email": "x@infoponia.com", "contrasena": CLAVE}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("core:desvincular_cuenta", args=[administrador.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse("core:cambiar_de_cuenta"), {"cuenta_id": 1}).status_code, 403
        )

    # ---- La ficha de quien gestiona la cuenta (reglas 3 de USR-CNS-USR y 7 de USR-MOD-USR) ----

    def test_regla_6_la_ficha_muestra_los_vinculos_en_solo_lectura(self):
        """USR-CNS-USR regla 3, USR-MOD-USR regla 7 y USR-VNC-CTA regla 6: la ficha muestra las cuentas
        vinculadas con su rol, email y estado, en solo lectura: quien gestiona no las cambia, ni hay botones
        para vincular o desvincular. Sin vínculos lo dice; las del Administrador no se vinculan."""
        self.entrar(crear_gerente())
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com", nombre="Carla", apellido="Gómez")
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        sin_vinculos = crear_cuenta(Tecnico, email="sola@infoponia.com", nombre="Sofía", apellido="Roldán")
        agrupar(capataz, vendedor)

        ficha = self.client.get(reverse("core:usuario", args=[capataz.pk]))
        self.assertContains(ficha, "Cuentas vinculadas")
        self.assertContains(ficha, "vendedor@infoponia.com")
        self.assertContains(ficha, "Solo lectura: las vincula y desvincula su dueño desde Mi perfil.")
        self.assertNotContains(ficha, "Desvincular")
        self.assertNotContains(ficha, "Vincular cuenta")
        self.assertContains(
            self.client.get(reverse("core:usuario", args=[sin_vinculos.pk])), "Sin cuentas vinculadas."
        )
        administrador = self.entrar(crear_administrador())
        propia = self.client.get(reverse("core:usuario", args=[administrador.pk]))
        self.assertContains(propia, "Las cuentas de Administrador no se vinculan.")

    def test_regla_6_la_ficha_enlaza_solo_las_cuentas_del_alcance(self):
        """USR-MOD-USR regla 7 y D-28: de las cuentas vinculadas, solo las que están dentro del alcance de quien
        mira llevan un enlace a su ficha; las demás se ven sin enlace (llevaría a un 403). El Gerente no gestiona
        al Gerente: su propia cuenta, vinculada a la del Capataz, no tiene enlace."""
        gerente = self.entrar(crear_gerente())
        capataz = crear_cuenta(Capataz, email="capataz@infoponia.com")
        vendedor = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        agrupar(capataz, gerente, vendedor)

        ficha = self.client.get(reverse("core:usuario", args=[capataz.pk]))

        self.assertContains(ficha, f'href="{reverse("core:usuario", args=[vendedor.pk])}"')
        self.assertNotContains(ficha, f'href="{reverse("core:usuario", args=[gerente.pk])}"')
        self.assertContains(ficha, gerente.email)  # figura, solo que sin enlace

    # ---- SEG-11: los textos de restablecer, reactivar y baja ----

    def test_seg11_las_ventanas_dicen_que_la_cuenta_sale_de_su_grupo(self):
        """SEG-11 y regla 2 de USR-BAJ-USR (textos de modalHtml 'reset', 'react' y 'baja'): las ventanas de
        confirmación dicen que restablecer o reactivar saca a la cuenta de su grupo, y que la baja no cambia
        sus vínculos. Si la cuenta no tiene grupo, no lo dicen (sería falso)."""
        self.entrar(crear_gerente())
        con_grupo = crear_cuenta(Capataz, email="con@infoponia.com")
        inactiva_con_grupo = crear_cuenta(Vendedor, email="inactiva@infoponia.com", activo=False)
        sin_grupo = crear_cuenta(Tecnico, email="sin@infoponia.com")
        agrupar(con_grupo, inactiva_con_grupo)

        restablecer = self.client.get(
            reverse("core:usuario_restablecer", args=[con_grupo.pk]), headers=self.HTMX
        )
        reactivar = self.client.get(
            reverse("core:usuario_reactivar", args=[inactiva_con_grupo.pk]), headers=self.HTMX
        )
        baja = self.client.get(reverse("core:usuario_baja", args=[con_grupo.pk]), headers=self.HTMX)
        sin_vinculos = self.client.get(
            reverse("core:usuario_restablecer", args=[sin_grupo.pk]), headers=self.HTMX
        )

        self.assertContains(restablecer, "sale de su grupo")
        self.assertContains(reactivar, "sale de su grupo")
        self.assertContains(baja, "sus cuentas vinculadas no cambian")
        self.assertNotContains(sin_vinculos, "sale de su grupo")

    def test_seg11_restablecer_muestra_que_la_cuenta_salio_del_grupo(self):
        """SEG-11 y postcondición b de USR-MOD-USR: tras restablecer, la ventana de la contraseña temporal dice
        que la cuenta salió de su grupo, y la ficha que queda detrás ya no muestra el vínculo."""
        self.entrar(crear_gerente())
        cuenta = crear_cuenta(Capataz, email="con@infoponia.com")
        otra = crear_cuenta(Vendedor, email="otra@infoponia.com")
        agrupar(cuenta, otra)

        respuesta = self.client.post(reverse("core:usuario_restablecer", args=[cuenta.pk]))

        self.assertContains(respuesta, "salió de su grupo de cuentas vinculadas")
        self.assertContains(respuesta, "Sin cuentas vinculadas.")
        self.assertNotContains(respuesta, "otra@infoponia.com")
        self.assertIsNone(grupo_de(cuenta))

    def test_regla_3_modificar_avisa_que_cambiar_el_email_no_afecta_los_vinculos(self):
        """USR-MOD-USR regla 3 (fieldHtml 'email' del prototipo): el formulario de modificar avisa que cambiar el
        email no afecta las cuentas vinculadas."""
        self.entrar(crear_gerente())
        cuenta = crear_cuenta(Capataz, email="con@infoponia.com")

        respuesta = self.client.get(reverse("core:usuario_modificar", args=[cuenta.pk]))

        self.assertContains(respuesta, "Cambiar el email no afecta las cuentas vinculadas.")


class UsrVncCtaConcurrenciaTests(TransactionTestCase):
    """Operaciones simultáneas sobre un mismo grupo (D-17, D-30). Son ``TransactionTestCase`` porque cada
    operación corre en su propio hilo, con su propia conexión y transacción (ver
    ``core/tests/concurrencia.py``). Ninguna puede terminar con un error sin traducir (en pantalla sería un
    error 500), y al final ningún grupo queda con menos de dos cuentas."""

    def test_regla_3_dos_vinculaciones_simultaneas_no_pierden_cuentas(self):
        """USR-VNC-CTA regla 3 y D-17: una cuenta con grupo vincula a C mientras otra, sin grupo, también
        vincula a C. Si las dos avanzaran con lo que leyeron al principio, C quedaría en el grupo de una
        y las otras dos, separadas de ella. Con el bloqueo, la segunda espera, ve que el grupo de C cambió y
        se rechaza con «cambio_simultaneo». Las cuentas que ya estaban juntas siguen juntas y la que ganó
        queda con C."""
        a = crear_cuenta(Agronomo, email="a@infoponia.com")
        b = crear_cuenta(Vendedor, email="b@infoponia.com")
        c = crear_cuenta(Capataz, email="c@infoponia.com")
        d = crear_cuenta(Tecnico, email="d@infoponia.com")
        agrupar(a, b)

        resultados = correr_a_la_vez(
            lambda: servicios.vincular_cuenta(a, c.email, CLAVE),
            lambda: servicios.vincular_cuenta(d, c.email, CLAVE),
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], "ninguna operación puede terminar con un error sin traducir")
        self.assertEqual(len(exitos), 1)
        self.assertEqual(len(rechazos), 1)
        self.assertEqual(codigos(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(grupos_con_menos_de_dos_cuentas(), [])
        self.assertIsNotNone(grupo_de(a))
        self.assertEqual(grupo_de(a), grupo_de(b))  # las que ya estaban juntas siguen juntas
        ganadora = d if isinstance(resultados["a"], Exception) else a
        self.assertEqual(grupo_de(ganadora), grupo_de(c))
        self.assertIsNotNone(grupo_de(c))
        self.assertEqual(
            RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.VINCULACION).count(), 1
        )

    def test_post_b_dos_desvinculaciones_simultaneas_disuelven_el_grupo(self):
        """USR-VNC-CTA postcondición b: en un grupo de tres, la misma persona desvincula a B y a C a la
        vez. Si cada operación contara las cuentas que quedan antes de que termine la otra, las dos verían
        «quedan dos» y el grupo se quedaría con una sola cuenta. Con el bloqueo, la segunda espera, cuenta
        de nuevo y disuelve el grupo: las tres quedan sin grupo y el grupo deja de existir."""
        a = crear_cuenta(Agronomo, email="a@infoponia.com")
        b = crear_cuenta(Vendedor, email="b@infoponia.com")
        c = crear_cuenta(Capataz, email="c@infoponia.com")
        agrupar(a, b, c)

        resultados = correr_a_la_vez(
            lambda: servicios.desvincular_cuenta(a, b.pk),
            lambda: servicios.desvincular_cuenta(a, c.pk),
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], "ninguna operación puede terminar con un error sin traducir")
        self.assertEqual(len(exitos), 2)
        self.assertEqual(rechazos, [])
        for cuenta in (a, b, c):
            self.assertIsNone(grupo_de(cuenta))
        self.assertFalse(GrupoCuentas.objects.exists())
        registros = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.DESVINCULACION)
        self.assertEqual(registros.count(), 2)
        self.assertEqual(sorted(r.detalle["disuelto"] for r in registros), [False, True])

    def test_seg11_restablecer_y_vincular_a_la_vez_no_dejan_la_temporal_en_el_grupo(self):
        """SEG-11, SEG-04 y regla 4 de USR-VNC-CTA: el Gerente restablece la contraseña de X (que está en un
        grupo) mientras otra persona vincula a X con su contraseña de antes. Pase lo que pase, ninguna
        cuenta con contraseña temporal queda en un grupo y ningún grupo queda con una sola cuenta. Si el
        restablecimiento gana, la vinculación se rechaza con el mensaje genérico (la cuenta ya tiene una
        temporal); si gana la vinculación, la cuenta nueva queda en el grupo cuando X sale de él."""
        gerente = crear_gerente()
        x = crear_cuenta(Agronomo, email="x@infoponia.com")
        v = crear_cuenta(Vendedor, email="v@infoponia.com")
        c = crear_cuenta(Capataz, email="c@infoponia.com")
        agrupar(x, v)

        resultados = correr_a_la_vez(
            lambda: servicios.restablecer_contrasena(gerente, x.pk),
            lambda: servicios.vincular_cuenta(c, x.email, CLAVE),
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], "ninguna operación puede terminar con un error sin traducir")
        self.assertNotIsInstance(resultados["a"], Exception, "el restablecimiento siempre se hace")
        for rechazo in rechazos:
            self.assertEqual(codigos(rechazo), ["no_se_pudo_vincular"])
        ahora = Usuario.objects.get(pk=x.pk)
        self.assertTrue(ahora.tiene_contrasena_temporal)
        self.assertIsNone(ahora.grupo_id)
        self.assertFalse(
            Usuario.objects.filter(
                fecha_contrasena_temporal__isnull=False, grupo__isnull=False
            ).exists()
        )
        self.assertEqual(grupos_con_menos_de_dos_cuentas(), [])
        if rechazos:
            self.assertIsNone(grupo_de(c))
        else:
            self.assertEqual(grupo_de(c), grupo_de(v))  # c entró al grupo y X salió después
            self.assertIsNotNone(grupo_de(c))

    def test_d32_restablecer_al_gerente_mientras_modifica_su_cuenta_vinculada_no_hace_deadlock(self):
        """D-32 (límite conocido) y D-30: el Gerente G, vinculado con su cuenta de Agrónomo X, modifica los datos de
        X mientras el Administrador restablece la contraseña de G (que saca a G de su grupo y lo disuelve, SEG-11).

        Orden fijo (``primera="a"``): la modificación tiene tomada la fila de X y se detiene antes de confirmar; recién
        entonces arranca el restablecimiento, que toma la fila de G y queda esperando la de X; ahí se libera la
        modificación. Al confirmar, la clave foránea de su auditoría necesita un bloqueo ``FOR KEY SHARE`` sobre la
        fila de G (quien actúa). Si el restablecimiento tiene G con ``FOR UPDATE``, cada una espera a la otra y
        PostgreSQL aborta una: un error 500. Con ``FOR NO KEY UPDATE`` no chocan: las dos terminan bien."""
        administrador = crear_administrador()
        gerente = crear_gerente()
        agronomo = crear_cuenta(Agronomo, email="agronomo@infoponia.com", nombre="Ana", apellido="Ibáñez")
        agrupar(gerente, agronomo)

        resultados = correr_a_la_vez(
            lambda: servicios.modificar_usuario(
                gerente, agronomo.pk, "Ana María", "Ibáñez", agronomo.email, "+54 376 400-1001"
            ),
            lambda: servicios.restablecer_contrasena(administrador, gerente.pk),
            primera="a",
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], "ninguna operación puede terminar con un error sin traducir (un deadlock)")
        self.assertEqual(rechazos, [])
        self.assertEqual(len(exitos), 2)
        self.assertEqual(Usuario.objects.get(pk=agronomo.pk).first_name, "Ana María")
        restablecido = Usuario.objects.get(pk=gerente.pk)
        self.assertTrue(restablecido.tiene_contrasena_temporal)
        self.assertIsNone(restablecido.grupo_id)
        self.assertIsNone(grupo_de(agronomo))
        self.assertFalse(GrupoCuentas.objects.exists())
