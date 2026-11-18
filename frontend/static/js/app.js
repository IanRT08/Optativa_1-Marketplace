// Comportamiento común (sin scripts inline: lo permite la CSP; sin innerHTML).
// - data-confirmar="texto": pide confirmación en el cuadro #dialogo-confirmar
//   antes de enviar (data-confirmar-tipo="primario" si la acción no destruye nada).
// - data-un-envio: estado "cargando" del botón (deshabilitado + "Procesando...")
//   mientras la petición está en curso; evita el doble envío.
// - data-sin-cambios: el botón de guardar se habilita solo si algo cambió.
// - Mostrar/ocultar contraseña y cierre de mensajes (el éxito se oculta a los 6 s).
// - Menú compacto en pantallas chicas (botón "Menú").
// Se carga sin defer para marcar <html class="js"> antes de pintar (sin parpadeo del menú).
document.documentElement.classList.add("js");

var TEXTO_CARGANDO = "Procesando...";
var MS_AUTOCERRAR = 6000;

// Vuelve a enviar el formulario ya confirmado, con el mismo botón que lo envió.
function enviarConfirmado(formulario, boton) {
    formulario.dataset.confirmado = "1";
    if (typeof formulario.requestSubmit === "function") {
        formulario.requestSubmit(boton && boton.form === formulario ? boton : undefined);
    } else {
        formulario.submit();
    }
}

function pedirConfirmacion(formulario, pregunta, boton) {
    var dialogo = document.getElementById("dialogo-confirmar");
    if (!dialogo || typeof dialogo.showModal !== "function") {
        if (window.confirm(pregunta)) {
            enviarConfirmado(formulario, boton);
        }
        return;
    }
    var si = dialogo.querySelector("[data-respuesta='confirmar']");
    var no = dialogo.querySelector("[data-respuesta='cancelar']");
    var primario = formulario.getAttribute("data-confirmar-tipo") === "primario";
    si.className = "btn " + (primario ? "btn-primario" : "btn-peligro");
    dialogo.querySelector("#dialogo-texto").textContent = pregunta;
    var origen = boton || document.activeElement;

    function terminar(confirmado) {
        si.removeEventListener("click", alConfirmar);
        no.removeEventListener("click", alCancelar);
        dialogo.removeEventListener("cancel", alEscape);
        dialogo.close();
        if (confirmado) {
            enviarConfirmado(formulario, boton);
        } else if (origen && typeof origen.focus === "function") {
            origen.focus();
        }
    }
    function alConfirmar() { terminar(true); }
    function alCancelar() { terminar(false); }
    function alEscape(evento) { evento.preventDefault(); terminar(false); }

    si.addEventListener("click", alConfirmar);
    no.addEventListener("click", alCancelar);
    dialogo.addEventListener("cancel", alEscape);
    dialogo.showModal();
    no.focus();   // la opción segura queda enfocada
}

document.addEventListener("submit", function (evento) {
    var formulario = evento.target;

    var pregunta = formulario.getAttribute("data-confirmar");
    if (pregunta && formulario.dataset.confirmado !== "1") {
        evento.preventDefault();
        pedirConfirmacion(formulario, pregunta, evento.submitter);
        return;
    }
    delete formulario.dataset.confirmado;
    // La contraseña siempre viaja desde un campo de tipo password.
    formulario.querySelectorAll(".btn-ver-password[aria-pressed='true']").forEach(function (boton) {
        boton.click();
    });
    if (!formulario.hasAttribute("data-un-envio")) {
        return;
    }
    if (formulario.dataset.enviando === "1") {
        evento.preventDefault();
        return;
    }
    formulario.dataset.enviando = "1";
    // Se deshabilita después de que el navegador tome los datos del envío.
    window.setTimeout(function () {
        formulario.querySelectorAll("button[type=submit]").forEach(function (boton) {
            var texto = boton.querySelector(".btn-texto");
            if (texto && !boton.dataset.textoOriginal) {
                boton.dataset.textoOriginal = texto.textContent;
                texto.textContent = TEXTO_CARGANDO;
            }
            boton.disabled = true;
            boton.setAttribute("aria-disabled", "true");
        });
    }, 0);
});

// Si el navegador restaura la página desde su caché (botón Atrás), se
// reactivan los botones y vuelven a su texto.
window.addEventListener("pageshow", function () {
    document.querySelectorAll("form[data-confirmado]").forEach(function (formulario) {
        delete formulario.dataset.confirmado;
    });
    document.querySelectorAll("form[data-enviando='1']").forEach(function (formulario) {
        delete formulario.dataset.enviando;
        formulario.querySelectorAll("button[type=submit]").forEach(function (boton) {
            var texto = boton.querySelector(".btn-texto");
            if (texto && boton.dataset.textoOriginal) {
                texto.textContent = boton.dataset.textoOriginal;
                delete boton.dataset.textoOriginal;
            }
            boton.disabled = false;
            boton.removeAttribute("aria-disabled");
        });
        formulario.dispatchEvent(new Event("change"));   // data-sin-cambios vuelve a revisar
    });
});

// Mostrar/ocultar contraseña (botón con aria-pressed; la etiqueta no cambia).
document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".btn-ver-password").forEach(function (boton) {
        var campo = document.getElementById(boton.getAttribute("aria-controls"));
        if (!campo) {
            return;
        }
        boton.hidden = false;
        boton.addEventListener("click", function () {
            var mostrar = campo.type === "password";
            campo.type = mostrar ? "text" : "password";
            boton.setAttribute("aria-pressed", mostrar ? "true" : "false");
        });
    });
});

// Mensajes: botón para cerrar; el éxito con data-autocerrar se oculta solo a
// los 6 s y se pausa mientras el puntero o el foco están encima.
function cerrarAlerta(alerta, moverFoco) {
    if (!alerta || !alerta.isConnected) {
        return;
    }
    var contenedor = alerta.parentElement;
    function quitar() {
        if (!alerta.isConnected) {
            return;
        }
        alerta.remove();
        if (contenedor && contenedor.classList.contains("mensajes") && !contenedor.children.length) {
            contenedor.remove();
        }
        if (moverFoco) {
            var principal = document.getElementById("contenido");
            if (principal) {
                principal.focus();
            }
        }
    }
    alerta.classList.add("saliendo");
    var segundos = parseFloat(window.getComputedStyle(alerta).transitionDuration) || 0;
    if (segundos > 0) {
        alerta.addEventListener("transitionend", quitar, { once: true });
        window.setTimeout(quitar, segundos * 1000 + 50);
    } else {
        quitar();
    }
}

document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".alerta-cerrar").forEach(function (boton) {
        boton.hidden = false;
        boton.addEventListener("click", function () {
            cerrarAlerta(boton.closest(".alerta"), true);
        });
    });
    document.querySelectorAll(".alerta[data-autocerrar]").forEach(function (alerta) {
        var restante = MS_AUTOCERRAR;
        var inicio = 0;
        var temporizador = null;
        var pausas = 0;
        function correr() {
            inicio = Date.now();
            temporizador = window.setTimeout(function () { cerrarAlerta(alerta, false); }, restante);
        }
        function pausar() {
            if (pausas++ === 0) {
                window.clearTimeout(temporizador);
                restante = Math.max(restante - (Date.now() - inicio), 1500);
            }
        }
        function reanudar() {
            if (pausas > 0 && --pausas === 0) {
                correr();
            }
        }
        alerta.addEventListener("mouseenter", pausar);
        alerta.addEventListener("mouseleave", reanudar);
        alerta.addEventListener("focusin", pausar);
        alerta.addEventListener("focusout", reanudar);
        correr();
    });
});

// Formularios de edición (data-sin-cambios): "Guardar cambios" deshabilitado
// mientras los datos sean los que se cargaron. Si la página volvió con un
// error, se deja habilitado para poder reintentar.
function estadoFormulario(formulario) {
    var partes = [];
    new FormData(formulario).forEach(function (valor, nombre) {
        if (nombre !== "csrf_token") {
            partes.push(nombre + "=" + (typeof valor === "string" ? valor : valor.name));
        }
    });
    return partes.join("&");
}

document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form[data-sin-cambios]").forEach(function (formulario) {
        if (formulario.querySelector(".campo-error") || document.querySelector(".alerta-error")) {
            return;
        }
        var original = estadoFormulario(formulario);
        var botones = formulario.querySelectorAll("button[type=submit]");
        function revisar() {
            var igual = estadoFormulario(formulario) === original;
            botones.forEach(function (boton) {
                if (formulario.dataset.enviando !== "1") {
                    boton.disabled = igual;
                }
            });
        }
        formulario.addEventListener("input", revisar);
        formulario.addEventListener("change", revisar);
        revisar();
    });
});

// Al volver con errores, el foco va al primer campo con error (el lector de
// pantalla lee su etiqueta y el mensaje que tiene debajo).
document.addEventListener("DOMContentLoaded", function () {
    var campo = document.querySelector("[aria-invalid='true']");
    if (!campo) {
        var error = document.querySelector(".campo-error");
        var grupo = error && error.closest("fieldset, td, form");
        campo = grupo && grupo.querySelector("input:not([type=hidden]), select, textarea");
    }
    if (campo) {
        campo.focus();
    }
});

// Botones que muestran u ocultan una sección en pantallas chicas: el menú
// (.btn-menu) y "Más filtros" del catálogo (data-alterna="id").
// Sin JavaScript todo queda visible.
document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".btn-menu, [data-alterna]").forEach(function (boton) {
        var objetivo = document.getElementById(boton.getAttribute("aria-controls"));
        if (!objetivo) {
            return;
        }
        boton.hidden = false;
        function cambiar(abrir) {
            boton.setAttribute("aria-expanded", abrir ? "true" : "false");
            objetivo.classList.toggle("abierto", abrir);
        }
        boton.addEventListener("click", function () {
            cambiar(boton.getAttribute("aria-expanded") !== "true");
        });
        if (boton.classList.contains("btn-menu")) {
            document.addEventListener("keydown", function (evento) {
                if (evento.key === "Escape" && boton.getAttribute("aria-expanded") === "true") {
                    cambiar(false);
                    boton.focus();
                }
            });
        }
    });
});

// Filas de tabla que abren su detalle: un clic en cualquier parte de la fila
// equivale al enlace marcado con data-fila-enlace (Ctrl/Cmd o clic central:
// pestaña nueva). Los botones, campos y otros enlaces de la fila funcionan
// igual que antes, y seleccionar texto no navega. Con teclado se sigue usando
// el enlace, que es el único elemento enfocable.
function enlaceDeFila(evento) {
    var fila = evento.target.closest("tbody tr");
    if (!fila || evento.target.closest("a, button, input, select, textarea, label, summary")) { return null; }
    if (window.getSelection && String(window.getSelection()).length) { return null; }
    return fila.querySelector("a[data-fila-enlace]");
}
document.addEventListener("click", function (evento) {
    var enlace = enlaceDeFila(evento);
    if (!enlace) { return; }
    if (evento.ctrlKey || evento.metaKey || evento.shiftKey) {
        window.open(enlace.href, "_blank", "noopener");
    } else {
        window.location.assign(enlace.href);
    }
});
document.addEventListener("auxclick", function (evento) {
    var enlace = evento.button === 1 ? enlaceDeFila(evento) : null;
    if (enlace) { window.open(enlace.href, "_blank", "noopener"); }
});
