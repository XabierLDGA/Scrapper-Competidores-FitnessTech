const rows = $input.all().map(i => i.json);
const hayCambios = rows.length > 0;

// ---------------------------------------------------------------------------
// El aviso diario de la comparativa contra Titanium. A diferencia del correo
// semanal, que enumera cambios, este cuenta el EFECTO del cambio sobre nuestra
// posicion: no "Titanium bajo el Remo Sentado a 1.595 EUR", sino "estabamos
// 296 EUR por debajo y ahora estamos 304 por encima". Eso es lo accionable
// para producto y la razon de que sea un correo aparte.
//
// **Sale todos los dias, tambien cuando no hay nada que contar.** Antes se
// cortaba en seco -el nodo Code devolvia `skip` y el If paraba el envio-, y
// como Titanium casi nunca toca los productos emparejados, el correo no
// llegaba practicamente nunca. Un silencio de semanas no se distingue de un
// crawler averiado, asi que ahora los dias tranquilos mandan un correo corto
// que dice justo eso: se ha mirado y no hay novedad. El resto del cuerpo del
// email no necesito cambios para esto, porque con cero filas ya se armaba
// solo: `g` queda vacio, los totales a cero y los bucles no iteran.
//
// Mismo sistema visual que el panel en tema claro. Los colores son los tokens
// de static/css/panel.css, literales: en un email no valen las variables CSS.
//
// Ojo al rojo/verde, que aqui conviven dos criterios distintos a proposito:
//   - Las PILDORAS siguen el semaforo comercial, como en el correo semanal:
//     que Titanium SUBA es buena noticia (verde) y que baje, mala (rojo).
//   - Las CIFRAS de diferencia siguen el signo del numero, como la pantalla
//     de comparativa: verde el positivo (somos mas caros), rojo el negativo.
// ---------------------------------------------------------------------------
const BG = '#f4f6f6';
const SURF = '#ffffff';
const SURF2 = '#fafbfb';
const INK = '#0c1112';
const INK3 = '#8e9a9e';
const LINE = '#e6eaeb';
const TEAL = '#00a7af';

const ROJO_BG = '#fdecec', ROJO = '#b3261e';
const VERDE_BG = '#e7f6ee', VERDE = '#127a4a';
const STOCK_BG = '#fdf4e3', STOCK_INK = '#8d6100';
const GONE_BG = '#f2f0ee', GONE_INK = '#6b6259';

const SANS = "font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;";
const MO = "font-family:'IBM Plex Mono',Consolas,Menlo,monospace;";
const TITULO = SANS + 'font-style:italic;font-weight:bold;text-transform:uppercase;letter-spacing:-.01em;';
const ROTULO = SANS + 'font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:' + INK3 + ';';

const hoy = new Date();
const fd = n => n.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });

const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// Formato espanol con separador de miles, igual que el filtro `eur` del panel.
const eur = v => {
  const n = Number(v);
  if (!isFinite(n)) return '&mdash;';
  const p = n.toFixed(2).split('.');
  p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return p[0] + ',' + p[1] + ' &euro;';
};

const dispo = v => (Number(v) ? 'Disponible' : 'Agotado');

function pildora(bg, ink, texto) {
  let s = '<span style="' + SANS + 'display:inline-block;background:' + bg + ';color:' + ink + ';';
  s += 'font-size:12px;padding:3px 9px;border-radius:999px;white-space:nowrap;">' + texto + '</span>';
  return s;
}

function cifra(rotulo, valor) {
  let s = '<td width="33%" style="padding:0 4px;" valign="top">';
  s += '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:' + SURF + ';';
  s += 'border:1px solid ' + LINE + ';border-radius:14px;"><tr><td style="padding:13px 14px;">';
  s += '<div style="' + SANS + 'font-size:11px;color:' + INK3 + ';">' + rotulo + '</div>';
  s += '<div style="' + MO + 'font-size:22px;color:' + INK + ';padding-top:7px;">' + valor + '</div>';
  s += '</td></tr></table></td>';
  return s;
}

// La posicion antes y despues del cambio de precio. `null` cuando no se puede
// calcular: la maquina nuestra no esta publicada (la gama Advanced entera) o
// falta algun precio.
function posicion(r) {
  // El descarte de nulos va ANTES de convertir, y es lo que parece de mas:
  // Number(null) es 0, no NaN, asi que sin esto una maquina nuestra sin
  // publicar (ft_precio NULL en la consulta) se leeria como si costase 0 EUR
  // y el correo anunciaria que estamos 2.395 EUR por debajo de Titanium.
  if (r.ft_precio == null || r.ti_antes == null || r.ti_ahora == null) return null;
  const ft = Number(r.ft_precio);
  const antes = Number(r.ti_antes);
  const ahora = Number(r.ti_ahora);
  if (!isFinite(ft) || !isFinite(antes) || !isFinite(ahora)) return null;
  return { antes: ft - antes, ahora: ft - ahora };
}

const lado = d => (d > 0 ? 'por encima' : d < 0 ? 'por debajo' : 'al mismo precio');

// Como se pinta cada fila: etiqueta, colores y detalle.
function pinta(r) {
  if (r.tipo === 'stock') {
    return {
      etiqueta: 'Stock', bg: STOCK_BG, ink: STOCK_INK, vuelco: false,
      detalle: dispo(r.antes_ok) + ' <span style="color:' + INK3 + ';">&rarr;</span> ' + dispo(r.ahora_ok),
    };
  }

  if (r.tipo === 'baja') {
    return {
      etiqueta: 'Baja', bg: GONE_BG, ink: GONE_INK, vuelco: false,
      detalle: 'Titanium la ha retirado de su catalogo',
    };
  }

  // Semaforo comercial: que Titanium suba nos favorece.
  const sube = Number(r.ti_ahora) > Number(r.ti_antes);
  const bg = sube ? VERDE_BG : ROJO_BG;
  const ink = sube ? VERDE : ROJO;

  let d = 'Titanium: ' + eur(r.ti_antes) + ' <span style="color:' + INK3 + ';">&rarr;</span> ' + eur(r.ti_ahora);

  const p = posicion(r);
  let vuelco = false;
  if (p) {
    // El vuelco es la noticia: pasar de estar por debajo a estar por encima
    // (o al reves) cambia el argumento comercial; una bajada que solo recorta
    // distancia, no.
    vuelco = (p.antes > 0) !== (p.ahora > 0);
    d += '<br>Estabamos <b>' + eur(Math.abs(p.antes)) + ' ' + lado(p.antes) + '</b>';
    d += ', ahora <b>' + eur(Math.abs(p.ahora)) + ' ' + lado(p.ahora) + '</b>';
  } else {
    d += '<br><span style="color:' + INK3 + ';">Nuestra maquina no esta publicada: sin posicion que comparar</span>';
  }

  return { etiqueta: sube ? 'Suben' : 'Bajan', bg: bg, ink: ink, detalle: d, vuelco: vuelco };
}

function fila(p, r, ultima) {
  let c = '<div style="' + SANS + 'font-size:14px;line-height:1.4;color:' + INK + ';">';
  c += esc(r.ft_title);
  if (p.vuelco) {
    c += ' &nbsp;' + pildora(ROJO_BG, ROJO, 'Cambia la posicion');
  }
  c += '</div>';
  c += '<div style="' + MO + 'font-size:11px;color:' + INK3 + ';padding-top:5px;">' + esc(r.ft_sku);
  c += ' &nbsp;&middot;&nbsp; ' + (r.titanium_url
    ? '<a href="' + esc(r.titanium_url) + '" style="color:' + INK3 + ';">' + esc(r.titanium_title) + '</a>'
    : esc(r.titanium_title)) + '</div>';
  c += '<div style="' + MO + 'font-size:12.5px;color:' + p.ink + ';padding-top:4px;">' + p.detalle + '</div>';

  let s = '<tr><td style="padding:13px 0;' + (ultima ? '' : 'border-bottom:1px solid ' + LINE + ';') + '">';
  s += '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>';
  s += '<td width="78" valign="top" style="padding-right:12px;">' + pildora(p.bg, p.ink, p.etiqueta) + '</td>';
  s += '<td valign="top">' + c + '</td>';
  s += '</tr></table></td></tr>';
  return s;
}

const g = {};
rows.forEach(r => { (g[r.gama] = g[r.gama] || []).push(r); });

const pintados = rows.map(pinta);
const totalPrecios = rows.filter(r => r.tipo === 'precio').length;
const totalVuelcos = pintados.filter(p => p.vuelco).length;
const totalOtros = rows.length - totalPrecios;

let h = '<div style="background:' + BG + ';padding:24px 12px;">';
h += '<table width="100%" cellpadding="0" cellspacing="0" border="0" align="center" ';
h += 'style="max-width:640px;margin:0 auto;background:' + SURF + ';border:1px solid ' + LINE + ';';
h += 'border-radius:14px;overflow:hidden;' + SANS + 'color:' + INK + ';">';

// Banda de marca: negra en los dos temas del panel, como la barra lateral.
h += '<tr><td style="background:#000000;padding:16px 26px;">';
h += '<span style="' + TITULO + 'font-size:16px;color:#ffffff;">Fitness Tech</span>';
h += '<span style="' + MO + 'font-size:11px;color:rgba(255,255,255,.45);"> &nbsp;Comparativa Titanium</span>';
h += '</td></tr>';

h += '<tr><td style="padding:22px 26px 18px;border-bottom:1px solid ' + LINE + ';">';
h += '<div style="' + TITULO + 'font-size:19px;color:' + INK + ';">';
h += (hayCambios ? 'Titanium ha movido ficha' : 'Sin novedad en los vigilados') + '</div>';
h += '<div style="' + SANS + 'font-size:13px;color:' + INK3 + ';padding-top:6px;">';
h += 'Ultimas 24 horas &nbsp;&middot;&nbsp; ' + fd(hoy) + '</div>';
h += '</td></tr>';

if (hayCambios) {
  h += '<tr><td style="padding:18px 22px 4px;">';
  h += '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>';
  h += cifra('Cambios de precio', totalPrecios);
  h += cifra('Cambian la posicion', totalVuelcos);
  h += cifra('Stock y bajas', totalOtros);
  h += '</tr></table></td></tr>';
} else {
  // Tres ceros en las tarjetas no dicen nada; una frase si. Lo que importa
  // del correo tranquilo es que se sepa que se ha mirado.
  h += '<tr><td style="padding:22px 26px 4px;">';
  h += '<div style="' + SANS + 'font-size:14px;line-height:1.55;color:' + INK + ';">';
  h += 'Titanium no ha tocado ni el precio ni la disponibilidad de ninguno de los ';
  h += 'productos emparejados con los nuestros, y no ha retirado ninguno de su catalogo.';
  h += '</div>';
  h += '<div style="' + SANS + 'font-size:13px;line-height:1.5;color:' + INK3 + ';padding-top:10px;">';
  h += 'Nuestra posicion frente a ellos sigue como estaba. Este correo llega cada ';
  h += 'manana aunque no haya cambios: si algun dia no llega, es que algo ha fallado.';
  h += '</div></td></tr>';
}

for (const gama in g) {
  h += '<tr><td style="padding:22px 26px 0;">';
  h += '<div style="border-top:1px solid ' + LINE + ';padding-top:20px;">';
  h += '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:' + TEAL + ';"></span>';
  h += '<span style="' + SANS + 'font-size:15px;font-weight:bold;color:' + INK + ';">&nbsp; ' + esc(gama) + '</span>';
  h += '<span style="' + SANS + 'font-size:12px;color:' + INK3 + ';"> &nbsp;&middot;&nbsp; ' + g[gama].length + ' cambios</span>';
  h += '</div></td></tr>';

  h += '<tr><td style="padding:4px 26px 0;">';
  h += '<table width="100%" cellpadding="0" cellspacing="0" border="0">';
  g[gama].forEach((r, i) => { h += fila(pinta(r), r, i === g[gama].length - 1); });
  h += '</table></td></tr>';
}

// Llamada al panel, con el turquesa del boton Sincronizar.
h += '<tr><td style="padding:28px 26px 30px;text-align:center;">';
h += '<a href="https://fitnesstech.duckdns.org/competencia#comparativa" style="' + SANS + 'display:inline-block;';
h += 'background:' + TEAL + ';color:#ffffff;text-decoration:none;font-size:14px;font-weight:bold;';
h += 'padding:13px 28px;border-radius:10px;">Abrir la comparativa</a>';
h += '<div style="' + SANS + 'font-size:12px;color:' + INK3 + ';padding-top:11px;">';
h += 'Las cuatro gamas enfrentadas, maquina a maquina</div>';
h += '</td></tr>';

h += '<tr><td style="padding:15px 26px;border-top:1px solid ' + LINE + ';background:' + SURF2 + ';">';
h += '<span style="' + ROTULO + '">Emparejamiento de producto &middot; Enviado cada dia por n8n</span>';
h += '</td></tr>';

h += '</table></div>';

// El asunto lo arma el JS y no el nodo Send an Email, que con cero cambios
// habria escrito "0 cambios (0 cambian la posicion)".
const plural = (n, sing, pl) => n + ' ' + (n === 1 ? sing : pl);
const asunto = hayCambios
  ? 'Comparativa Titanium: ' + plural(rows.length, 'cambio', 'cambios')
    + ' (' + plural(totalVuelcos, 'cambia', 'cambian') + ' la posicion)'
  : 'Comparativa Titanium: sin cambios (' + fd(hoy) + ')';

return [{
  json: {
    html: h,
    asunto: asunto,
    total: rows.length,
    totalPrecios: totalPrecios,
    totalVuelcos: totalVuelcos,
    fecha: fd(hoy),
  },
}];
