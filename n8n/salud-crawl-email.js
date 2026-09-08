const filas = $input.all().map(i => i.json);

// ---------------------------------------------------------------------------
// El aviso de fallos del crawl. Va solo a tech@: no es una noticia de
// mercado como los otros dos correos, es una averia que hay que arreglar.
//
// Al reves que el diario de Titanium, este SI se calla cuando no hay nada.
// El latido diario ya lo da aquel; este solo debe sonar cuando toca hacer
// algo, o se convierte en un correo mas que nadie abre.
//
// Mismo sistema visual que el panel en tema claro, con una diferencia: aqui
// el rojo no es "la competencia ha bajado el precio", es "esto esta roto".
// ---------------------------------------------------------------------------
const BG = '#f4f6f6';
const SURF = '#ffffff';
const SURF2 = '#fafbfb';
const INK = '#0c1112';
const INK3 = '#8e9a9e';
const LINE = '#e6eaeb';
const TEAL = '#00a7af';

const ROJO_BG = '#fdecec', ROJO = '#b3261e';
const AMBAR_BG = '#fdf4e3', AMBAR = '#8d6100';

const SANS = "font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;";
const MO = "font-family:'IBM Plex Mono',Consolas,Menlo,monospace;";
const TITULO = SANS + 'font-style:italic;font-weight:bold;text-transform:uppercase;letter-spacing:-.01em;';
const ROTULO = SANS + 'font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:' + INK3 + ';';

const hoy = new Date();
const fd = n => n.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
const hm = v => {
  const d = v instanceof Date ? v : new Date(v);
  return isNaN(d) ? String(v) : d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
};

const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const miles = v => String(Number(v) || 0).replace(/\B(?=(\d{3})+(?!\d))/g, '.');

// La fila `resumen` viene siempre; el resto son los problemas de verdad.
const resumen = filas.find(f => f.tipo === 'resumen') || { hoy: 0, normal: 0 };
const problemas = filas.filter(f => f.tipo !== 'resumen');

if (!problemas.length) return [{ json: { skip: true } }];

// Ninguna lectura en toda la noche no es "una tienda caida", es que el crawl
// no ha llegado a correr: contenedor parado, MySQL inalcanzable o la maquina
// entera. Merece otro titular, porque lo que hay que mirar es otra cosa.
const nadaEnAbsoluto = Number(resumen.hoy) === 0;

function pildora(bg, ink, texto) {
  let s = '<span style="' + SANS + 'display:inline-block;background:' + bg + ';color:' + ink + ';';
  s += 'font-size:12px;padding:3px 9px;border-radius:999px;white-space:nowrap;">' + texto + '</span>';
  return s;
}

function cifra(rotulo, valor, ink) {
  let s = '<td width="50%" style="padding:0 4px;" valign="top">';
  s += '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:' + SURF + ';';
  s += 'border:1px solid ' + LINE + ';border-radius:14px;"><tr><td style="padding:13px 14px;">';
  s += '<div style="' + SANS + 'font-size:11px;color:' + INK3 + ';">' + rotulo + '</div>';
  s += '<div style="' + MO + 'font-size:22px;color:' + (ink || INK) + ';padding-top:7px;">' + valor + '</div>';
  s += '</td></tr></table></td>';
  return s;
}

// Que se pinta en cada fila segun el tipo de fallo.
function pinta(f) {
  if (f.tipo === 'sin_lecturas') {
    return {
      etiqueta: 'Sin datos', bg: ROJO_BG, ink: ROJO,
      detalle: 'Ni una sola lectura hoy. Un dia normal deja ' + miles(f.normal) + '.',
    };
  }
  if (f.tipo === 'pocas_lecturas') {
    const pct = Number(f.normal) ? Math.round(Number(f.hoy) / Number(f.normal) * 100) : 0;
    return {
      etiqueta: 'A medias', bg: AMBAR_BG, ink: AMBAR,
      detalle: miles(f.hoy) + ' lecturas de las ' + miles(f.normal) + ' de un dia normal ('
        + pct + ' %). El catalogo se ha descargado incompleto.',
    };
  }
  return {
    etiqueta: 'Error', bg: ROJO_BG, ink: ROJO,
    detalle: esc(f.detalle) + '<br><span style="color:' + INK3 + ';">A las ' + hm(f.cuando) + '</span>',
  };
}

const tiendas = [...new Set(problemas.map(f => f.tienda).filter(Boolean))];

let h = '<div style="background:' + BG + ';padding:24px 12px;">';
h += '<table width="100%" cellpadding="0" cellspacing="0" border="0" align="center" ';
h += 'style="max-width:640px;margin:0 auto;background:' + SURF + ';border:1px solid ' + LINE + ';';
h += 'border-radius:14px;overflow:hidden;' + SANS + 'color:' + INK + ';">';

// Banda de marca: negra en los dos temas del panel, como la barra lateral.
h += '<tr><td style="background:#000000;padding:16px 26px;">';
h += '<span style="' + TITULO + 'font-size:16px;color:#ffffff;">Fitness Tech</span>';
h += '<span style="' + MO + 'font-size:11px;color:rgba(255,255,255,.45);"> &nbsp;Salud del crawl</span>';
h += '</td></tr>';

h += '<tr><td style="padding:22px 26px 18px;border-bottom:1px solid ' + LINE + ';">';
h += '<div style="' + TITULO + 'font-size:19px;color:' + ROJO + ';">';
h += (nadaEnAbsoluto ? 'El crawl no ha corrido' : 'El crawl ha fallado') + '</div>';
h += '<div style="' + SANS + 'font-size:13px;color:' + INK3 + ';padding-top:6px;">';
h += 'Ultimas 24 horas &nbsp;&middot;&nbsp; ' + fd(hoy) + '</div>';
h += '</td></tr>';

h += '<tr><td style="padding:18px 22px 4px;">';
h += '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>';
h += cifra('Lecturas de hoy', miles(resumen.hoy) + ' <span style="font-size:13px;color:' + INK3 + ';">de '
  + miles(resumen.normal) + '</span>', nadaEnAbsoluto ? ROJO : INK);
h += cifra('Tiendas afectadas', tiendas.length);
h += '</tr></table></td></tr>';

if (nadaEnAbsoluto) {
  h += '<tr><td style="padding:20px 26px 0;">';
  h += '<div style="' + SANS + 'font-size:14px;line-height:1.55;color:' + INK + ';">';
  h += 'No hay ni una lectura de hoy, asi que no es una tienda concreta: o el contenedor ';
  h += '<span style="' + MO + 'font-size:13px;">crawler</span> esta parado, o no alcanza el MySQL. ';
  h += 'Los datos del panel son los de ayer.';
  h += '</div></td></tr>';
}

h += '<tr><td style="padding:14px 26px 0;">';
h += '<table width="100%" cellpadding="0" cellspacing="0" border="0">';
problemas.forEach((f, i) => {
  const p = pinta(f);
  let c = '<div style="' + SANS + 'font-size:14px;line-height:1.4;color:' + INK + ';">' + esc(f.tienda) + '</div>';
  c += '<div style="' + MO + 'font-size:12.5px;color:' + p.ink + ';padding-top:4px;">' + p.detalle + '</div>';

  h += '<tr><td style="padding:13px 0;' + (i === problemas.length - 1 ? '' : 'border-bottom:1px solid ' + LINE + ';') + '">';
  h += '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>';
  h += '<td width="86" valign="top" style="padding-right:12px;">' + pildora(p.bg, p.ink, p.etiqueta) + '</td>';
  h += '<td valign="top">' + c + '</td>';
  h += '</tr></table></td></tr>';
});
h += '</table></td></tr>';

h += '<tr><td style="padding:24px 26px 28px;text-align:center;">';
h += '<a href="https://fitnesstech.duckdns.org/competencia" style="' + SANS + 'display:inline-block;';
h += 'background:' + TEAL + ';color:#ffffff;text-decoration:none;font-size:14px;font-weight:bold;';
h += 'padding:13px 28px;border-radius:10px;">Abrir el panel</a>';
h += '<div style="' + SANS + 'font-size:12px;color:' + INK3 + ';padding-top:11px;">';
h += 'La ultima lectura de cada tienda, para ver hasta donde llego</div>';
h += '</td></tr>';

h += '<tr><td style="padding:15px 26px;border-top:1px solid ' + LINE + ';background:' + SURF2 + ';">';
h += '<span style="' + ROTULO + '">Solo se envia cuando hay algo roto</span>';
h += '</td></tr>';

h += '</table></div>';

const asunto = nadaEnAbsoluto
  ? 'Crawl: no ha corrido (' + fd(hoy) + ')'
  : 'Crawl: fallos en ' + tiendas.length + (tiendas.length === 1 ? ' tienda' : ' tiendas')
    + ' (' + tiendas.join(', ') + ')';

return [{
  json: {
    html: h,
    asunto: asunto,
    skip: false,
    total: problemas.length,
    tiendas: tiendas.length,
    fecha: fd(hoy),
  },
}];
