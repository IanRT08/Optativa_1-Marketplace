// Desactiva el botón de envío de los formularios marcados con data-un-envio
// mientras la petición está en curso (evita doble clic: compra, quitar del
// carrito, registro). Sin innerHTML: solo propiedades seguras.
document.addEventListener("submit", function (evento) {
    var formulario = evento.target;
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
