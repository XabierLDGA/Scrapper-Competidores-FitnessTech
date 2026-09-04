/* ==========================================================================
   Panel de vigilancia de mercado — FitnessTech

   Todo se renderiza en el servidor: esto solo decide que vista se ve y que
   filas quedan visibles dentro de ella. Sin dependencias ni build.
   ========================================================================== */

(function () {
  "use strict";

  // ---------- tema ----------
  var raiz = document.documentElement;

  function aplicarTema(tema) {
    raiz.dataset.theme = tema;
    try { localStorage.setItem("vig-theme", tema); } catch (e) {}
  }

  var botonTema = document.getElementById("tema");
  if (botonTema) {
    botonTema.addEventListener("click", function () {
      aplicarTema(raiz.dataset.theme === "dark" ? "light" : "dark");
    });
  }

  // ---------- reloj ----------
  var reloj = document.getElementById("reloj");

  function pintarHora() {
    if (!reloj) return;
    reloj.textContent = new Date().toLocaleTimeString("es-ES", {
      timeZone: "Europe/Madrid", hour: "2-digit", minute: "2-digit"
    });
  }
  pintarHora();
  setInterval(pintarHora, 20000);

  // ---------- numeros en formato espanol ----------
  // Punto para los miles, coma para los decimales. Se usa al repintar las
  // cifras de cabecera cuando se filtra por tienda, que es lo unico que el
  // servidor no puede formatear.
  function numeroEs(valor, decimales) {
    var texto = valor.toFixed(decimales || 0);
    var partes = texto.split(".");
    partes[0] = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return partes.length > 1 ? partes.join(",") : partes[0];
  }

  // ---------- busqueda ----------
  // Vive aqui, en el IIFE, porque la usan tanto la bandeja como cada vista
  // de tienda: el buscador de la barra lateral filtra la vista que este
  // abierta, sea cual sea.
  var textoBusqueda = "";

  function coincide(fila) {
    return !textoBusqueda
      || fila.getAttribute("data-busca").indexOf(textoBusqueda) !== -1;
  }

  // Cada vista registra aqui su funcion de refiltrado al construirse, para
  // que el buscador no tenga que saber como funciona ninguna por dentro.
  var refiltradores = [];

  var buscador = document.getElementById("buscador");
  if (buscador) {
    buscador.addEventListener("input", function () {
      textoBusqueda = buscador.value.trim().toLowerCase();
      refiltradores.forEach(function (fn) { fn(); });
    });
  }

  // ---------- barra lateral en pantalla estrecha ----------
  var panel = document.getElementById("panel");

  document.addEventListener("click", function (e) {
    if (!panel) return;
    if (e.target.closest("[data-abrir-rail]")) panel.classList.add("is-open");
    else if (e.target.closest("[data-cerrar-rail]")) panel.classList.remove("is-open");
  });

  // ---------- navegacion ----------
  var vistas = [].slice.call(document.querySelectorAll(".view"));
  var items = [].slice.call(document.querySelectorAll(".navitem[data-view]"));
  var titulo = document.getElementById("titulo");
  var subtitulo = document.getElementById("subtitulo");

  function mostrar(clave) {
    var vista = document.querySelector('.view[data-view="' + clave + '"]');
    if (!vista) { vista = vistas[0]; clave = vista.getAttribute("data-view"); }

    vistas.forEach(function (v) { v.classList.toggle("is-on", v === vista); });
    items.forEach(function (n) {
      n.classList.toggle("is-active", n.getAttribute("data-view") === clave);
    });

    if (titulo) titulo.textContent = vista.getAttribute("data-titulo") || "Cambios";
    if (subtitulo) subtitulo.textContent = vista.getAttribute("data-sub") || "";

    // Navegar cierra el menu: en movil la barra tapa la vista que se acaba
    // de elegir.
    if (panel) panel.classList.remove("is-open");
  }

  function desdeHash() {
    mostrar((location.hash || "#cambios").slice(1));
  }
  window.addEventListener("hashchange", desdeHash);
  desdeHash();
})();
