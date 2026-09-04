const rows = $input.all().map(i => i.json);
if (!rows.length) return [{ json: { skip: true } }];

// ---------------------------------------------------------------------------
// Mismo sistema visual que el panel de vigilancia, en tema claro. Los colores
// son los tokens de static/css/panel.css, literales: en un email no valen las
// variables CSS. Y ojo con el par rojo/verde, que va al reves de lo que
// parece: una BAJADA de precio de la competencia se pinta en rojo (mala
// noticia para nosotros) y una SUBIDA en verde. Es la convencion del panel.
// ---------------------------------------------------------------------------
const BG = '#f4f6f6';        // --bg
const SURF = '#ffffff';      // --surface
const SURF2 = '#fafbfb';     // --surface-2
const INK = '#0c1112';       // --ink
const INK2 = '#59666b';      // --ink-2
const INK3 = '#8e9a9e';      // --ink-3
const LINE = '#e6eaeb';      // --line
const TEAL = '#00a7af';      // --accent
const TEAL_INK = '#00666b';  // --accent-ink
const TEAL_WASH = '#e6f6f7'; // --accent-wash, aplanado sobre blanco

const DOWN_BG = '#fdecec', DOWN_INK = '#b3261e';   // bajada de precio
const UP_BG = '#e7f6ee', UP_INK = '#127a4a';       // subida de precio
const NEW_BG = '#eaf1fe', NEW_INK = '#2b4ec2';     // alta de catalogo

// El panel usa Archivo italica para los titulos, IBM Plex Sans para el cuerpo
// e IBM Plex Mono para las cifras. En email no hay webfonts fiables, asi que
// se cae a la familia mas parecida que trae cada sistema.
const SANS = "font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;";
const MO = "font-family:'IBM Plex Mono',Consolas,Menlo,monospace;";
const TITULO = SANS + 'font-style:italic;font-weight:bold;text-transform:uppercase;letter-spacing:-.01em;';
const ROTULO = SANS + 'font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:' + INK3 + ';';

const fd = n => n.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
const hoy = new Date();
const rango = fd(new Date(hoy - 6048e5)) + ' - ' + fd(hoy);

// Formato espanol con separador de miles, igual que el filtro `eur` del
// panel: punto para los miles, coma para los decimales.
const eur = v => {
  const n = Number(v);
  if (!isFinite(n)) return '&mdash;';
  const partes = n.toFixed(2).split('.');
  partes[0] = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return partes[0] + ',' + partes[1] + ' &euro;';
};

const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// La pildora de tipo de cambio de la bandeja del panel.
function pildora(bg, ink, texto) {
  let s = '<span style="' + SANS + 'display:inline-block;background:' + bg + ';color:' + ink + ';';
  s += 'font-size:12px;padding:3px 9px;border-radius:999px;white-space:nowrap;">' + texto + '</span>';
  return s;
}

// Una tarjeta de cifra de las de la cabecera del panel.
function cifra(rotulo, valor) {
  let s = '<td width="33%" style="padding:0 5px;" valign="top">';
  s += '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:' + SURF + ';';
  s += 'border:1px solid ' + LINE + ';border-radius:14px;"><tr><td style="padding:13px 15px;">';
  s += '<div style="' + SANS + 'font-size:11px;color:' + INK3 + ';">' + rotulo + '</div>';
  s += '<div style="' + MO + 'font-size:22px;color:' + INK + ';padding-top:7px;">' + valor + '</div>';
  s += '</td></tr></table></td>';
  return s;
}

// El SKU va en su propia linea, como en la columna SKU del panel.
function sku(v) {
  return '<div style="' + MO + 'font-size:11px;color:' + INK3 + ';padding-top:5px;">'
    + esc(v || '&mdash;') + '</div>';
}

// Una fila de cambio: pildora a la izquierda y el detalle a la derecha, en vez
// de las cinco columnas del panel. Con 640px de ancho y moviles de por medio,
// cinco columnas se estrujan hasta ser ilegibles.
function fila(bg, ink, etiqueta, cuerpo, ultima) {
  let s = '<tr><td style="padding:13px 0;' + (ultima ? '' : 'border-bottom:1px solid ' + LINE + ';') + '">';
  s += '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>';
  s += '<td width="78" valign="top" style="padding-right:12px;">' + pildora(bg, ink, etiqueta) + '</td>';
  s += '<td valign="top">' + cuerpo + '</td>';
  s += '</tr></table></td></tr>';
  return s;
}

const g = {};
rows.forEach(r => { (g[r.competidor] = g[r.competidor] || []).push(r); });

const totalNuevos = rows.filter(r => r.tipo === 'nuevo').length;
const precios = rows.filter(r => r.tipo !== 'nuevo');
const bajadas = precios.filter(r => Number(r.ahora) < Number(r.antes)).length;
const subidas = precios.length - bajadas;

let h = '<div style="background:' + BG + ';padding:24px 12px;">';
h += '<table width="100%" cellpadding="0" cellspacing="0" border="0" align="center" ';
h += 'style="max-width:640px;margin:0 auto;background:' + SURF + ';border:1px solid ' + LINE + ';';
h += 'border-radius:14px;overflow:hidden;' + SANS + 'color:' + INK + ';">';

// Banda de marca: negra en los dos temas del panel, como la barra lateral.
h += '<tr><td style="background:#000000;padding:16px 26px;">';
h += '<span style="' + TITULO + 'font-size:16px;color:#ffffff;">Fitness Tech</span>';
h += '<span style="' + MO + 'font-size:11px;color:rgba(255,255,255,.45);"> &nbsp;Vigilancia de mercado</span>';
h += '</td></tr>';

// Cabecera.
h += '<tr><td style="padding:22px 26px 18px;border-bottom:1px solid ' + LINE + ';">';
h += '<div style="' + TITULO + 'font-size:19px;color:' + INK + ';">Cambios de la competencia</div>';
h += '<div style="' + SANS + 'font-size:13px;color:' + INK3 + ';padding-top:6px;">';
h += 'Resumen semanal &nbsp;&middot;&nbsp; ' + rango + '</div>';
h += '</td></tr>';

// Cifras de cabecera.
h += '<tr><td style="padding:18px 21px 4px;">';
h += '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>';
h += cifra('Altas', totalNuevos);
h += cifra('Subidas', subidas);
h += cifra('Bajadas', bajadas);
h += '</tr></table></td></tr>';

for (const k in g) {
  const altas = g[k].filter(r => r.tipo === 'nuevo');
  const cambios = g[k].filter(r => r.tipo !== 'nuevo');

  h += '<tr><td style="padding:22px 26px 0;">';
  h += '<div style="border-top:1px solid ' + LINE + ';padding-top:20px;">';
  h += '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:' + TEAL + ';"></span>';
  h += '<span style="' + SANS + 'font-size:15px;font-weight:bold;color:' + INK + ';">&nbsp; ' + esc(k) + '</span>';
  h += '<span style="' + SANS + 'font-size:12px;color:' + INK3 + ';"> &nbsp;&middot;&nbsp; ';
  h += altas.length + ' altas &nbsp;&middot;&nbsp; ' + cambios.length + ' de precio</span>';
  h += '</div></td></tr>';

  h += '<tr><td style="padding:4px 26px 0;">';
  h += '<table width="100%" cellpadding="0" cellspacing="0" border="0">';

  const total = altas.length + cambios.length;
  let i = 0;

  for (const r of altas) {
    i++;
    let c = '<div style="' + SANS + 'font-size:14px;line-height:1.4;color:' + INK + ';">';
    c += (r.url
      ? '<a href="' + esc(r.url) + '" style="color:' + INK + ';text-decoration:none;">' + esc(r.producto) + '</a>'
      : esc(r.producto));
    c += '</div>';
    c += sku(r.sku);
    c += '<div style="' + MO + 'font-size:12.5px;color:' + INK2 + ';padding-top:3px;">';
    c += (r.ahora != null ? eur(r.ahora) : 'Sin precio') + '</div>';
    h += fila(NEW_BG, NEW_INK, 'Alta', c, i === total);
  }

  for (const r of cambios) {
    i++;
    const sube = Number(r.ahora) > Number(r.antes);
    const bg = sube ? UP_BG : DOWN_BG;
    const ink = sube ? UP_INK : DOWN_INK;
    const antes = Number(r.antes);
    const pct = isFinite(antes) && antes !== 0
      ? ((Number(r.ahora) - antes) / antes * 100)
      : null;

    let c = '<div style="' + SANS + 'font-size:14px;line-height:1.4;color:' + INK + ';">' + esc(r.producto) + '</div>';
    c += sku(r.sku);
    c += '<div style="' + MO + 'font-size:12.5px;color:' + ink + ';padding-top:3px;">';
    c += eur(r.antes) + ' <span style="color:' + INK3 + ';">&rarr;</span> ' + eur(r.ahora);
    if (pct !== null) {
      c += ' &nbsp;<b>' + (pct > 0 ? '+' : '') + pct.toFixed(1).replace('.', ',') + ' %</b>';
    }
    c += '</div>';
    h += fila(bg, ink, sube ? 'Subida' : 'Bajada', c, i === total);
  }

  h += '</table></td></tr>';
}

// Llamada al panel, con el turquesa del boton Sincronizar.
h += '<tr><td style="padding:28px 26px 30px;text-align:center;">';
h += '<a href="https://fitnesstech.duckdns.org/competencia" style="' + SANS + 'display:inline-block;';
h += 'background:' + TEAL + ';color:#ffffff;text-decoration:none;font-size:14px;font-weight:bold;';
h += 'padding:13px 28px;border-radius:10px;">Abrir el panel</a>';
h += '<div style="' + SANS + 'font-size:12px;color:' + INK3 + ';padding-top:11px;">';
h += 'Todo el detalle, tienda por tienda</div>';
h += '</td></tr>';

// Pie.
h += '<tr><td style="padding:15px 26px;border-top:1px solid ' + LINE + ';background:' + SURF2 + ';">';
h += '<span style="' + ROTULO + '">Origen: MySQL &middot; Enviado cada lunes por n8n</span>';
h += '</td></tr>';

h += '</table></div>';

return [{ json: { html: h, skip: false, totalNuevos: totalNuevos, totalPrecios: precios.length, rango: rango } }];
