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

  // ---------- barra lateral en pantalla estrecha ----------
  var panel = document.getElementById("panel");

  document.addEventListener("click", function (e) {
    if (!panel) return;
    if (e.target.closest("[data-abrir-rail]")) panel.classList.add("is-open");
    else if (e.target.closest("[data-cerrar-rail]")) panel.classList.remove("is-open");
  });

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
  // Se guarda junto a su seccion porque solo se refiltra la que se esta
  // viendo: entre la bandeja y los cuatro catalogos hay del orden de 17.000
  // filas, y recorrerlas todas en cada pulsacion se nota.
  var refiltradores = [];

  function registrar(vista, fn) {
    refiltradores.push({ vista: vista, fn: fn });
  }

  function refiltrarVisible() {
    refiltradores.forEach(function (r) {
      if (r.vista.classList.contains("is-on")) r.fn();
    });
  }

  var buscador = document.getElementById("buscador");
  if (buscador) {
    var pendiente = 0;
    buscador.addEventListener("input", function () {
      textoBusqueda = buscador.value.trim().toLowerCase();
      // Con miles de filas, filtrar en cada pulsacion se atasca al teclear
      // rapido. Se espera a que la mano pare.
      clearTimeout(pendiente);
      pendiente = setTimeout(refiltrarVisible, 110);
    });
  }

  // ---------- atajos ----------
  document.addEventListener("keydown", function (e) {
    if (!buscador) return;

    if (e.key === "/" && document.activeElement !== buscador) {
      e.preventDefault();
      // En pantalla estrecha el campo esta fuera de la vista: se despliega
      // la barra antes de enfocarlo, para no escribir a ciegas.
      if (panel && window.matchMedia("(max-width: 900px)").matches) {
        panel.classList.add("is-open");
      }
      buscador.focus();
      buscador.select();
    } else if (e.key === "Escape") {
      if (document.activeElement === buscador && buscador.value) {
        buscador.value = "";
        textoBusqueda = "";
        refiltrarVisible();
      } else if (panel && panel.classList.contains("is-open")) {
        panel.classList.remove("is-open");
      }
    }
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

    // La vista que se abre puede llevar una busqueda vigente sin aplicar,
    // porque mientras estaba oculta no se refiltraba.
    refiltrarVisible();
  }

  // ---------- filtros de la bandeja ----------
  var bandeja = document.querySelector('.view[data-view="cambios"]');

  if (bandeja) {
    var filtroTienda = "";
    var filtroTipo = "";

    var filas = [].slice.call(bandeja.querySelectorAll("tbody tr"));
    // Con `.filtros-tienda [data-tienda]` y no `[data-tienda]` a secas: las
    // tarjetas del final llevan ese mismo atributo y falsearian las cifras.
    var pastillasTienda = [].slice.call(
      bandeja.querySelectorAll(".filtros-tienda [data-tienda]"));
    var pastillasTipo = [].slice.call(bandeja.querySelectorAll("[data-tipo]"));
    var tarjetas = [].slice.call(bandeja.querySelectorAll(".tarjeta"));

    // 'price' agrupa subidas y bajadas en un solo filtro.
    function encaja(fila, tipo) {
      var t = fila.getAttribute("data-tipo");
      return !tipo || t === tipo || (tipo === "price" && t.indexOf("price") === 0);
    }

    function pasaTienda(fila) {
      return !filtroTienda || fila.getAttribute("data-tienda") === filtroTienda;
    }

    function filtrarBandeja() {
      var visibles = 0;

      filas.forEach(function (fila) {
        var ok = pasaTienda(fila) && encaja(fila, filtroTipo) && coincide(fila);
        fila.style.display = ok ? "" : "none";
        if (ok) visibles++;
      });

      var vacio = bandeja.querySelector("[data-vacio]");
      if (vacio) vacio.classList.toggle("is-on", visibles === 0);

      // Contadores de las pastillas de tipo, sobre lo que deja pasar el
      // filtro de tienda y la busqueda: si contasen sobre el total, dirian
      // una cosa y la tabla mostraria otra.
      ["", "price", "new", "stock", "removed"].forEach(function (tipo) {
        var n = filas.filter(function (fila) {
          return pasaTienda(fila) && encaja(fila, tipo) && coincide(fila);
        }).length;
        var salida = bandeja.querySelector('[data-cuenta-tipo="' + tipo + '"]');
        if (salida) salida.textContent = numeroEs(n, 0);
      });

      recalcularCifras(visibles);
      pintarTarjetas();
    }

    // Al filtrar por una tienda, las cifras de cabecera pasan a ser las
    // suyas. Los porcentajes se ponderan por tamano de catalogo: cuatro
    // tiendas de 865 a 1.428 productos dan un numero falso con una media
    // simple.
    function recalcularCifras(visibles) {
      var elegidas = pastillasTienda.filter(function (p) {
        var nombre = p.getAttribute("data-tienda");
        return nombre && (!filtroTienda || nombre === filtroTienda);
      });
      if (!elegidas.length) return;

      var productos = 0, disp = 0, promo = 0, live = 0;
      elegidas.forEach(function (p) {
        var total = parseFloat(p.getAttribute("data-total")) || 0;
        productos += total;
        disp += parseFloat(p.getAttribute("data-disp")) * total;
        promo += parseFloat(p.getAttribute("data-promo")) * total;
        live += parseInt(p.getAttribute("data-live"), 10);
      });

      document.getElementById("c-productos").textContent = numeroEs(productos, 0);
      document.getElementById("c-live").textContent = live;
      document.getElementById("c-live-total").textContent = "/ " + elegidas.length;
      document.getElementById("c-disp").textContent =
        productos ? numeroEs(disp / productos, 1) : "0";
      document.getElementById("c-promo").textContent =
        productos ? numeroEs(promo / productos, 1) : "0";
      document.getElementById("c-cambios").textContent = numeroEs(visibles, 0);
    }

    function pintarTarjetas() {
      tarjetas.forEach(function (tarjeta) {
        var nombre = tarjeta.getAttribute("data-tienda");
        tarjeta.style.display = (!filtroTienda || nombre === filtroTienda) ? "" : "none";
      });
    }

    bandeja.addEventListener("click", function (e) {
      var pastilla = e.target.closest(".pastilla");
      if (!pastilla) return;

      if (pastilla.hasAttribute("data-tienda")) {
        filtroTienda = pastilla.getAttribute("data-tienda");
        pastillasTienda.forEach(function (p) {
          p.classList.toggle("is-active", p === pastilla);
        });
      } else if (pastilla.hasAttribute("data-tipo")) {
        filtroTipo = pastilla.getAttribute("data-tipo");
        pastillasTipo.forEach(function (p) {
          p.classList.toggle("is-active", p === pastilla);
        });
      }
      filtrarBandeja();
    });

    registrar(bandeja, filtrarBandeja);
    filtrarBandeja();
  }

  // ---------- vistas de tienda ----------
  [].slice.call(document.querySelectorAll('.view[data-view^="tienda/"]'))
    .forEach(function (vista) {
      var pestanaActiva = "catalogo";
      var sub = "";

      function encajaSub(fila) {
        var s = fila.getAttribute("data-sub");
        return !sub || s === sub || (sub === "price" && s.indexOf("price") === 0);
      }

      function filtrar() {
        var panelActivo = vista.querySelector('[data-panel="' + pestanaActiva + '"]');
        var visibles = 0;

        [].slice.call(panelActivo.querySelectorAll("tbody tr")).forEach(function (fila) {
          var ok = encajaSub(fila) && coincide(fila);
          fila.style.display = ok ? "" : "none";
          if (ok) visibles++;
        });

        var vacio = panelActivo.querySelector("[data-vacio]");
        if (vacio) vacio.classList.toggle("is-on", visibles === 0);

        // Contadores del subfiltro de tipo, en las dos pestanas de cambios
        // (24 h y 7 dias): los del catalogo son fijos y ya los imprime la
        // plantilla. Se buscan dentro del bloque de subfiltros de la pestana
        // activa y no en toda la vista, porque las dos tienen los mismos
        // `data-cuenta-sub` y si no siempre se repintarian los de la primera.
        var subfiltrosActivos = vista.querySelector('[data-para="' + pestanaActiva + '"]');
        if (pestanaActiva !== "catalogo" && subfiltrosActivos) {
          var filasCambios = [].slice.call(panelActivo.querySelectorAll("tbody tr"));
          ["", "new", "price", "stock", "removed"].forEach(function (clave) {
            var n = filasCambios.filter(function (fila) {
              var s = fila.getAttribute("data-sub");
              return !clave || s === clave || (clave === "price" && s.indexOf("price") === 0);
            }).length;
            var salida = subfiltrosActivos.querySelector('[data-cuenta-sub="' + clave + '"]');
            if (salida) salida.textContent = numeroEs(n, 0);
          });
        }
      }

      function cambiarPestana(clave) {
        pestanaActiva = clave;
        sub = "";

        vista.querySelectorAll("[data-pestana]").forEach(function (b) {
          b.classList.toggle("is-active", b.getAttribute("data-pestana") === clave);
        });
        vista.querySelectorAll("[data-panel]").forEach(function (p) {
          p.classList.toggle("u-oculto", p.getAttribute("data-panel") !== clave);
        });
        vista.querySelectorAll("[data-para]").forEach(function (f) {
          f.classList.toggle("u-oculto", f.getAttribute("data-para") !== clave);
          f.querySelectorAll("[data-sub]").forEach(function (b, i) {
            b.classList.toggle("is-active", i === 0);
          });
        });
        filtrar();
      }

      vista.addEventListener("click", function (e) {
        var boton = e.target.closest(".pastilla");
        if (!boton) return;

        if (boton.hasAttribute("data-pestana")) {
          cambiarPestana(boton.getAttribute("data-pestana"));
        } else if (boton.hasAttribute("data-sub")) {
          sub = boton.getAttribute("data-sub");
          boton.parentNode.querySelectorAll("[data-sub]").forEach(function (b) {
            b.classList.toggle("is-active", b === boton);
          });
          filtrar();
        }
      });

      // El buscador de la barra lateral filtra la vista abierta sin saber
      // como funciona por dentro: cada vista solo se apunta aqui.
      registrar(vista, filtrar);
      filtrar();
    });

  function desdeHash() {
    mostrar((location.hash || "#cambios").slice(1));
  }
  window.addEventListener("hashchange", desdeHash);
  desdeHash();
})();
