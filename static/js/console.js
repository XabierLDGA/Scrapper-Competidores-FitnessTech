/* =========================================================================
   CONSOLA DE VIGILANCIA — comportamiento
   -------------------------------------------------------------------------
   Todo se renderiza en el servidor: aqui solo se decide que vista se ve, se
   filtra lo ya pintado y se animan las lecturas. No hay peticiones al
   servidor salvo el envio del formulario de sincronizacion.
   ========================================================================= */

(function () {
  "use strict";

  var quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var estrecho = function () { return window.matchMedia("(max-width: 900px)").matches; };

  var consola = document.getElementById("console");
  var vistas = document.getElementById("views");
  var caret = document.getElementById("caret");
  var crumb = document.getElementById("crumb");
  var sweep = document.getElementById("sweep");
  var buscador = document.getElementById("search");
  var envoltorioBusqueda = document.getElementById("search-shell");

  var secciones = Array.prototype.slice.call(document.querySelectorAll(".view"));
  var items = Array.prototype.slice.call(document.querySelectorAll(".navitem"));

  /* Formato espanol con punto de millar y coma decimal. No se usa
     toLocaleString porque en es-ES no agrupa los numeros de cuatro cifras
     y quedaria "3326" aqui frente a "3.326" en lo que pinta el servidor. */
  function numeroEs(valor, decimales) {
    var partes = Math.abs(valor).toFixed(decimales || 0).split(".");
    var entero = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return (valor < 0 ? "-" : "") + entero + (partes[1] ? "," + partes[1] : "");
  }

  /* ---------------------------------------------------------------- vistas */

  var VISTA_INICIAL = "panel";
  var activa = null;
  // El salto automatico al escribir en el buscador no debe llevarse el foco:
  // si lo hiciera, escribir despacio te echaria del campo a media palabra.
  var saltoDeBusqueda = false;

  function seccionDe(clave) {
    for (var i = 0; i < secciones.length; i++) {
      if (secciones[i].dataset.view === clave) return secciones[i];
    }
    return null;
  }

  function itemDe(clave) {
    for (var i = 0; i < items.length; i++) {
      if (items[i].dataset.view === clave) return items[i];
    }
    return null;
  }

  function moverCaret(item) {
    if (!item) { caret.classList.remove("is-on"); return; }
    caret.style.height = item.offsetHeight + "px";
    caret.style.transform = "translateY(" + item.offsetTop + "px)";
    caret.classList.add("is-on");
  }

  function lanzarBarrido() {
    if (quieto) return;
    sweep.style.setProperty("--sweep-to", vistas.clientHeight + "px");
    sweep.classList.remove("is-running");
    void sweep.offsetWidth; // fuerza el reinicio de la animacion
    sweep.classList.add("is-running");
  }

  function mostrar(clave, opciones) {
    var seccion = seccionDe(clave);
    if (!seccion) { seccion = seccionDe(VISTA_INICIAL); clave = VISTA_INICIAL; }
    if (activa === clave) return;

    activa = clave;
    secciones.forEach(function (s) { s.classList.toggle("is-on", s === seccion); });
    items.forEach(function (n) { n.classList.toggle("is-active", n.dataset.view === clave); });

    var item = itemDe(clave);
    moverCaret(item);
    crumb.textContent = item ? item.querySelector(".navitem__text").textContent : "Vista general";
    document.title = crumb.textContent + " — Vigilancia de mercado";

    vistas.scrollTop = 0;
    animarLecturas(seccion);
    lanzarBarrido();

    if (!opciones || !opciones.callado) {
      seccion.focus({ preventScroll: true });
    }
    if (estrecho()) consola.classList.remove("is-open");
  }

  function desdeHash() {
    var clave = decodeURIComponent((location.hash || "").replace(/^#/, ""));
    var callado = activa === null || saltoDeBusqueda;
    saltoDeBusqueda = false;
    mostrar(clave || VISTA_INICIAL, { callado: callado });
  }

  window.addEventListener("hashchange", desdeHash);

  /* ------------------------------------------------- lecturas que se animan */

  function contarHasta(el) {
    var destino = parseFloat(el.dataset.countup || "0");
    var decimales = parseInt(el.dataset.decimals || "0", 10);
    var pinta = function (v) { el.textContent = numeroEs(v, decimales); };

    if (quieto || !destino) { pinta(destino); return; }

    var inicio = null;
    var duracion = 640;
    var paso = function (t) {
      if (inicio === null) inicio = t;
      var p = Math.min((t - inicio) / duracion, 1);
      pinta(destino * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(paso);
      else pinta(destino);
    };
    requestAnimationFrame(paso);
  }

  function animarLecturas(seccion) {
    // Solo la primera vez que se abre una vista: si no, las cifras volvian a
    // contar desde cero en cada visita mientras los medidores, ya en su
    // sitio, se quedaban quietos.
    if (seccion.dataset.listo === "1") return;
    seccion.dataset.listo = "1";

    seccion.querySelectorAll("[data-countup]").forEach(contarHasta);
    // Los medidores y las barras arrancan a cero en el CSS y se rellenan al
    // entrar la vista, para que el movimiento cuente algo (la magnitud) y no
    // sea un adorno de carga.
    var pintar = function () {
      seccion.querySelectorAll(".meter__fill").forEach(function (f) {
        f.style.width = Math.min(100, parseFloat(f.dataset.fill || "0")) + "%";
      });
      seccion.querySelectorAll(".bars__item").forEach(function (b) {
        b.style.setProperty("--h", Math.min(100, parseFloat(b.dataset.h || "0")) + "%");
      });
    };
    if (quieto) pintar();
    else requestAnimationFrame(function () { requestAnimationFrame(pintar); });
  }

  /* -------------------------------------------------------- mapa de calor */

  var lectura = document.getElementById("heat-readout");
  var lecturaBase = lectura ? lectura.innerHTML : "";
  var mapa = document.getElementById("heat");

  function iluminar(fila, columna) {
    if (!mapa) return;
    mapa.querySelectorAll(".heat__col").forEach(function (c) {
      c.classList.toggle("is-lit", c.dataset.col === columna);
    });
    mapa.querySelectorAll(".heat__row").forEach(function (r) {
      r.classList.toggle("is-lit", r.dataset.row === fila);
    });
  }

  function leerCelda(celda) {
    var cuota = numeroEs(parseFloat(celda.dataset.share) * 100, 1);
    var unidades = parseInt(celda.dataset.count, 10);
    lectura.classList.add("is-lit");
    lectura.classList.toggle("is-rival", celda.dataset.rival === "1");
    lectura.innerHTML = unidades
      ? "<b>" + celda.dataset.name + "</b> · " + celda.dataset.band + " € · " +
        numeroEs(unidades, 0) + " productos · <em>" + cuota + " %</em> de su catálogo"
      : "<b>" + celda.dataset.name + "</b> · " + celda.dataset.band + " € · sin productos en este tramo";
    iluminar(celda.dataset.row, celda.dataset.col);
  }

  function soltarCelda() {
    lectura.classList.remove("is-lit", "is-rival");
    lectura.innerHTML = lecturaBase;
    iluminar(null, null);
  }

  if (mapa) {
    mapa.addEventListener("pointerover", function (e) {
      var celda = e.target.closest(".heat__cell");
      if (celda) leerCelda(celda);
    });
    mapa.addEventListener("pointerleave", soltarCelda);
    mapa.addEventListener("focusin", function (e) {
      var celda = e.target.closest(".heat__cell");
      if (celda) leerCelda(celda);
    });
    mapa.addEventListener("focusout", function (e) {
      if (!mapa.contains(e.relatedTarget)) soltarCelda();
    });
  }

  /* ------------------------------------------------------------ pestanas */

  document.addEventListener("click", function (e) {
    var pestana = e.target.closest(".tab");
    if (pestana) {
      var bloque = pestana.closest(".block");
      bloque.querySelectorAll(".tab").forEach(function (t) {
        var on = t === pestana;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      bloque.querySelectorAll(".panel").forEach(function (p) {
        p.classList.toggle("is-active", p.dataset.panel === pestana.dataset.tab);
      });
      return;
    }

    var plegar = e.target.closest('[data-action="fold"]');
    if (plegar) {
      var plegado = consola.classList.toggle("is-collapsed");
      try { localStorage.setItem("ft-rail", plegado ? "1" : "0"); } catch (err) { /* modo privado */ }
      return;
    }

    // Con el rail plegado el campo de busqueda no se ve: la lupa despliega y
    // deja el cursor dentro, en vez de dar foco a un campo invisible.
    if (consola.classList.contains("is-collapsed") && e.target.closest("#search-shell")) {
      e.preventDefault();
      consola.classList.remove("is-collapsed");
      try { localStorage.setItem("ft-rail", "0"); } catch (err) { /* modo privado */ }
      setTimeout(function () { buscador.focus(); }, 280);
      return;
    }

    if (e.target.closest('[data-action="open-rail"]')) { consola.classList.add("is-open"); return; }
    if (e.target.closest('[data-action="close-rail"]')) { consola.classList.remove("is-open"); return; }
  });

  /* ------------------------------------------------------------- busqueda */

  // Se indexa una sola vez: en cada pulsacion solo se comparan cadenas ya
  // cacheadas y solo se toca el DOM de las filas que cambian de estado.
  var filas = [];
  secciones.forEach(function (seccion) {
    var clave = seccion.dataset.view;
    var objetivo = clave.indexOf("objetivo/") === 0
      ? (itemDe(clave) ? itemDe(clave).dataset.target : null)
      : null;
    seccion.querySelectorAll("tr[data-search]").forEach(function (tr) {
      filas.push({ el: tr, texto: tr.dataset.search, vista: clave, objetivo: objetivo, oculta: false });
    });
  });

  var contadores = {};
  document.querySelectorAll("[data-count-for]").forEach(function (el) {
    contadores[el.dataset.countFor] = { el: el, base: el.textContent, cero: el.classList.contains("is-zero") };
  });

  function filtrar() {
    var q = buscador.value.trim().toLowerCase();
    envoltorioBusqueda.classList.toggle("is-filled", q.length > 0);

    var porVista = {};
    var porObjetivo = {};

    for (var i = 0; i < filas.length; i++) {
      var fila = filas[i];
      var visible = !q || fila.texto.indexOf(q) !== -1;
      if (fila.oculta !== !visible) {
        fila.el.classList.toggle("u-hide", !visible);
        fila.oculta = !visible;
      }
      if (visible) {
        porVista[fila.vista] = (porVista[fila.vista] || 0) + 1;
        if (fila.objetivo) porObjetivo[fila.objetivo] = (porObjetivo[fila.objetivo] || 0) + 1;
      }
    }

    // El contador del lateral pasa a decir cuantas coincidencias hay en cada
    // tienda; al vaciar la busqueda vuelve al tamano del catalogo.
    Object.keys(contadores).forEach(function (nombre) {
      var c = contadores[nombre];
      var hits = porObjetivo[nombre] || 0;
      c.el.textContent = q ? hits : c.base;
      c.el.classList.toggle("is-hit", !!q && hits > 0);
      c.el.classList.toggle("is-zero", q ? hits === 0 : c.cero);
    });

    // Aviso de "sin coincidencias" dentro de cada tabla ya pintada, y el
    // contador de su pestana, que si no seguiria diciendo 865 sobre una
    // tabla de 60 filas.
    document.querySelectorAll("[data-nomatch]").forEach(function (aviso) {
      var contenedor = aviso.parentElement;
      var total = contenedor.querySelectorAll("tr[data-search]").length;
      var ocultas = contenedor.querySelectorAll("tr[data-search].u-hide").length;
      aviso.classList.toggle("u-hide", !(q && total > 0 && ocultas === total));

      var bloque = contenedor.closest(".block");
      var etiqueta = bloque && bloque.querySelector('.tab[data-tab="' + contenedor.dataset.panel + '"] small');
      if (etiqueta) {
        if (etiqueta.dataset.base === undefined) etiqueta.dataset.base = etiqueta.textContent;
        etiqueta.textContent = q ? total - ocultas : etiqueta.dataset.base;
      }
    });

    // Si lo que se esta mirando no tiene ninguna coincidencia pero otra vista
    // si, se salta a ella: es el equivalente al despliegue automatico de las
    // tarjetas que hacia el panel anterior.
    if (q && !porVista[activa]) {
      var destino = Object.keys(porObjetivo)[0];
      if (destino) {
        for (var j = 0; j < items.length; j++) {
          if (items[j].dataset.target === destino) {
            saltoDeBusqueda = true;
            location.hash = items[j].dataset.view;
            break;
          }
        }
      }
    }
  }

  var pendiente = null;
  buscador.addEventListener("input", function () {
    clearTimeout(pendiente);
    pendiente = setTimeout(filtrar, 110);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== buscador) {
      e.preventDefault();
      if (estrecho()) consola.classList.add("is-open");
      // Con el rail plegado el campo esta ahi pero no se ve: se despliega
      // antes de enfocarlo para no escribir a ciegas.
      if (consola.classList.contains("is-collapsed")) {
        consola.classList.remove("is-collapsed");
        try { localStorage.setItem("ft-rail", "0"); } catch (err) { /* modo privado */ }
      }
      buscador.focus();
      buscador.select();
    } else if (e.key === "Escape") {
      if (document.activeElement === buscador && buscador.value) {
        buscador.value = "";
        filtrar();
      } else if (consola.classList.contains("is-open")) {
        consola.classList.remove("is-open");
      }
    }
  });

  /* ------------------------------------------------------------ telemetria */

  var reloj = document.getElementById("clock");
  var formatoHora = new Intl.DateTimeFormat("es-ES", {
    timeZone: "Europe/Madrid", hour: "2-digit", minute: "2-digit",
    // hourCycle h23 y no hour12:false: con lo segundo, algunos navegadores
    // pintan las 00:xx como "24:xx".
    second: "2-digit", hourCycle: "h23",
  });

  function tic() { reloj.textContent = formatoHora.format(new Date()); }
  tic();
  setInterval(tic, 1000);

  /* ------------------------------------------------------ sincronizacion */

  var formulario = document.getElementById("sync-form");
  formulario.addEventListener("submit", function () {
    var boton = formulario.querySelector("button");
    boton.disabled = true;
    boton.querySelector("span").textContent = "Sincronizando";
  });

  /* ------------------------------------------------------------- arranque */

  try {
    if (localStorage.getItem("ft-rail") === "1") consola.classList.add("is-collapsed");
  } catch (err) { /* modo privado */ }

  desdeHash();
  window.addEventListener("resize", function () { moverCaret(itemDe(activa)); });

  // Al plegar y desplegar cambian las alturas del menu; el indicador se
  // recoloca cuando la transicion ha terminado, no antes.
  consola.addEventListener("transitionend", function (e) {
    if (e.propertyName === "grid-template-columns") moverCaret(itemDe(activa));
  });
})();
