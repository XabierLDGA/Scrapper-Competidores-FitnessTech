# Workflows de n8n

El crawler de este repo **no envia notificaciones**. El aviso lo monta n8n
por su cuenta, y lo que hay aqui es una copia versionada de ese montaje: el
original vive dentro del contenedor `n8n` del VPS, en una base SQLite, donde
no hay historial ni forma de ver que cambio ni cuando.

## `notificacion-semanal`

Cada lunes consulta el MySQL compartido, arma un email con los cambios de la
competencia de los ultimos 7 dias y lo manda a `tech@fitnesstech.es`.

Cuenta los **cuatro tipos** de cambio -altas de catalogo, cambios de precio,
entradas y salidas de stock y bajas de catalogo-, los mismos que la pestana
*Cambios 7 dias* de la vista de tienda del panel. Hasta el 2026-09-04 la
consulta solo traia altas y precios, asi que el correo se dejaba fuera el
stock y las bajas aunque el crawler si las detectaba.

```
Schedule Trigger (semanal, lunes)
  -> Execute a SQL query   (altas y cambios de precio de 7 dias, excluyendo
  |                         las tiendas propias)
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

## El email

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
