// Comportamiento común de los formularios (sin scripts inline: lo permite la CSP).
// - data-confirmar="texto": pide confirmación antes de enviar.
// - data-un-envio: desactiva el botón mientras la petición está en curso
//   (evita el doble clic en pagar, quitar del carrito, registrar...).
// Sin innerHTML: solo propiedades seguras.
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
    var botones = formulario.querySelectorAll("button[type=submit]");
    botones.forEach(function (boton) {
        boton.disabled = true;
        boton.textContent = "Enviando…";
    });
});

// Si el navegador restaura la página desde su caché (botón Atrás), se
// reactivan los botones que quedaron desactivados.
window.addEventListener("pageshow", function () {
    document.querySelectorAll("form[data-enviando='1']").forEach(function (formulario) {
        delete formulario.dataset.enviando;
        formulario.querySelectorAll("button[type=submit]").forEach(function (boton) {
            boton.disabled = false;
        });
    });
});
