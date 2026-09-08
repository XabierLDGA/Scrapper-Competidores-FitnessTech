# Workflows de n8n

El crawler de este repo **no envia notificaciones**. Los avisos los monta n8n
por su cuenta, y lo que hay aqui son copias versionadas de esos montajes: los
originales viven dentro del contenedor `n8n` del VPS, en una base SQLite,
donde no hay historial ni forma de ver que cambio ni cuando.

Son dos: el resumen semanal de toda la competencia y el aviso diario de la
comparativa contra Titanium.

## `notificacion-semanal`

Cada lunes a las 08:30 consulta el MySQL compartido, arma un email con los cambios de la
competencia de los ultimos 7 dias y lo manda a la lista de avisos
(direccion, marketing, marketplace y tech: diez buzones internos).

Cuenta los **cuatro tipos** de cambio -altas de catalogo, cambios de precio,
entradas y salidas de stock y bajas de catalogo-, los mismos que la pestana
*Cambios 7 dias* de la vista de tienda del panel. Hasta el 2026-09-04 la
consulta solo traia altas y precios, asi que el correo se dejaba fuera el
stock y las bajas aunque el crawler si las detectaba.

```
Schedule Trigger (semanal, lunes 08:30)
  -> Execute a SQL query   (los cuatro tipos de cambio de 7 dias, en cuatro
  |                         ramas UNION, excluyendo las tiendas propias)
  -> Code in JavaScript    (arma el HTML del email)
  -> If                    (corta si no hay nada que contar)
  -> Send an Email
```

| Fichero | Que es |
| --- | --- |
| `notificacion-semanal-email.js` | El codigo del nodo *Code in JavaScript*, que es lo unico que se toca a menudo |
| `notificacion-semanal.workflow.json` | El workflow entero, tal como lo exporta n8n |

El export lleva las credenciales **por nombre**, nunca sus valores: los
secretos siguen solo dentro de n8n.

## `comparativa-titanium-diaria`

Cada manana a las 08:00 mira si Titanium ha movido algo en los 67 productos
que producto ha emparejado con los nuestros (`titanium_pairs`, que puebla
`import_comparativa.py`). **Manda correo haya novedad o no**: los dias
tranquilos, que son casi todos, llega una version corta que dice que se ha
mirado y no hay cambios.

Lo que lo distingue del semanal es que no cuenta el cambio, cuenta el
**efecto sobre nuestra posicion**: no "Titanium bajo el Remo Sentado a
1.595 EUR", sino "estabamos 296 EUR por debajo, ahora estamos 304 por
encima". Ese vuelco es lo accionable para producto, y es la razon de que sea
un correo aparte y no un bloque mas en el de los lunes.

Las 08:00 y no antes: el crawl arranca a las 03:00 y ha llegado a tardar doce
minutos. El contenedor va en `Europe/Madrid` (`TZ` y `GENERIC_TIMEZONE`), asi
que son las 08:00 de aqui sin conversion de por medio.

Y las 08:00 y no las 03:15, aunque el crawl acabe mucho antes: el correo se
lee cuando alguien abre el buzon, no cuando estan los datos. Por eso el
semanal salio de las 00:00 del lunes -llegaba de madrugada, y encima tres
horas ANTES del crawl de ese mismo lunes, con datos hasta el domingo- y pasa
a las 08:30, media hora despues del diario para que el lunes no lleguen los
dos de golpe.

```
Schedule Trigger (diario, 08:00)
  -> Execute a SQL query   (precio, stock y bajas de 24 h, restringidos por
  |                         JOIN a titanium_pairs; trae ademas nuestro precio
  |                         vigente por subconsulta, para calcular la posicion)
  -> Code in JavaScript    (arma el HTML y el asunto, con novedad o sin ella)
  -> Send an Email
```

Aqui no hay nodo *If*, y es la diferencia con el semanal. Lo hubo: cortaba el
envio cuando la consulta no devolvia filas. Se quito el 2026-09-08 para que el
correo llegue todos los dias.

| Fichero | Que es |
| --- | --- |
| `comparativa-titanium.sql` | La consulta del nodo *Execute a SQL query* |
| `comparativa-titanium-email.js` | El codigo del nodo *Code in JavaScript* |
| `comparativa-titanium-diaria.workflow.json` | El workflow entero, tal como lo exporta n8n |

**Ojo al rojo/verde, que aqui no significa lo mismo en todas partes**, y es a
proposito:

- Las **pildoras** siguen el semaforo comercial, como el correo semanal: que
  Titanium **suba** es buena noticia (verde) y que baje, mala (rojo).
- Las **cifras** de diferencia siguen el signo del numero, como la pantalla de
  comparativa del panel: verde el positivo (somos mas caros), rojo el
  negativo.

**Casi siempre va a decir que no hay novedad, y es lo normal.** A 2026-09-07,
de los 135 cambios de precio que se le han detectado a Titanium desde agosto,
**ninguno** cae en los 67 productos emparejados: sus selectorizadas no se
mueven, lo que se mueve es el resto de su catalogo.

Justo por eso el correo sale igualmente. Cuando cortaba en seco no llegaba
practicamente nunca, y un silencio de semanas no se distingue de un crawler
averiado. El correo tranquilo es el latido: mientras llegue, el sistema mira.
El asunto los distingue de un vistazo, sin abrirlos:

```
Comparativa Titanium: sin cambios (08/09/2026)
Comparativa Titanium: 4 cambios (1 cambia la posicion)
```

El asunto lo arma el nodo *Code*, no el de envio, porque con cero filas la
plantilla de antes habria escrito "0 cambios (0 cambian la posicion)".

## El email (semanal)

Usa el mismo sistema visual que el panel (`static/css/panel.css`) en tema
claro: banda negra de marca, pildoras de tipo, cifras en monoespaciada y el
`antes -> ahora` con su porcentaje. Los colores van literales porque en un
email no valen las variables CSS, y las webfonts caen a Helvetica y a la
monoespaciada del sistema.

Ojo con el par rojo/verde: una **bajada** de precio de la competencia se
pinta en rojo y una **subida** en verde. Es la convencion del panel, y va al
reves de lo que uno esperaria de un grafico de precios.

## Como se despliega

No hay automatismo: se importa a mano.

```bash
scp n8n/notificacion-semanal.workflow.json deploy@168.119.241.200:/tmp/wf.json
ssh deploy@168.119.241.200
docker cp /tmp/wf.json n8n:/tmp/wf.json
docker exec -e N8N_RUNNERS_BROKER_PORT=5699 n8n n8n import:workflow --input=/tmp/wf.json
```

`N8N_RUNNERS_BROKER_PORT` hace falta porque el CLI levanta su propio broker
y choca con el puerto de la instancia que ya esta corriendo.

**Dos cosas que muerden despues de importar:**

1. El import **desactiva** el workflow ("Deactivating workflow..."). Hay que
   volver a activarlo.
2. Ni el import ni `update:workflow --active=true` surten efecto en la
   instancia que ya esta en marcha: n8n registra los triggers al arrancar.
   Lo mas seguro es entrar en la interfaz y darle al interruptor del
   workflow (apagar y encender), que lo re-registra sin reiniciar n8n y sin
   molestar al resto de workflows.

## Para probar el email sin enviarlo

`notificacion-semanal-email.js` es JavaScript corriente: se le puede pasar
un `$input` de mentira con filas reales sacadas de MySQL, quedarse con el
`html` que devuelve y abrirlo en el navegador. Asi se ve el correo sin
mandar nada a nadie.
