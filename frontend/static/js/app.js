// Comportamiento común (sin scripts inline: lo permite la CSP; sin innerHTML).
// - data-confirmar="texto": pide confirmación antes de enviar.
// - data-un-envio: estado "cargando" del botón (deshabilitado + "Procesando...")
//   mientras la petición está en curso; evita el doble envío.
// - Menú compacto en pantallas chicas (botón "Menú").
// Se carga sin defer para marcar <html class="js"> antes de pintar (sin parpadeo del menú).
document.documentElement.classList.add("js");

var TEXTO_CARGANDO = "Procesando...";

document.addEventListener("submit", function (evento) {
    var formulario = evento.target;

    var pregunta = formulario.getAttribute("data-confirmar");
    if (pregunta && !window.confirm(pregunta)) {
        evento.preventDefault();
        return;
    }
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
