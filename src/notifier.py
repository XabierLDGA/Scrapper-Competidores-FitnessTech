import logging
import os
from typing import Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, slack_token: Optional[str] = None,
                 slack_channel: Optional[str] = None):
        self.slack_token = slack_token or os.getenv("SLACK_BOT_TOKEN")
        self.slack_channel = slack_channel or os.getenv("SLACK_CHANNEL", "#product")
        self.client = WebClient(token=self.slack_token) if self.slack_token else None

    def send_slack_new_product(self, product: dict, competitor: str):
        """Notifica un producto nuevo a Slack."""
        if not self.client:
            logger.warning("Slack no configurado, saltando notificacion")
            return

        try:
            self.client.chat_postMessage(
                channel=self.slack_channel,
                text=f"Nuevo producto: {product['title']}",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f":new: *{competitor}* acaba de publicar:\n\n*{product['title']}*\n"
                                    f"EUR {product['price']:.2f}",
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Ver producto"},
                                "url": product["url"],
                            }
                        ],
                    },
                ],
            )
            logger.info(f"Notificacion Slack enviada para {product['title']}")
        except SlackApiError as e:
            logger.error(f"Error enviando Slack: {e.response['error']}")

    def send_slack_price_change(self, product: dict, old_price: float,
                                 new_price: float, percent_change: float, competitor: str):
        """Notifica un cambio de precio a Slack.

        percent_change se recibe ya calculado por ChangeDetector: no se
        recalcula aqui para no tener una tercera copia de esa formula.
        """
        if not self.client:
            return

        emoji = ":chart_with_upwards_trend:" if percent_change > 0 else ":chart_with_downwards_trend:"
        direction = "subio" if percent_change > 0 else "bajo"

        try:
            self.client.chat_postMessage(
                channel=self.slack_channel,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{emoji} *{competitor}* cambio precio:\n\n*{product['title']}*\n"
                                    f"EUR {old_price:.2f} -> EUR {new_price:.2f} "
                                    f"({direction} {abs(percent_change):.1f}%)",
                        },
                    }
                ],
            )
        except SlackApiError as e:
            logger.error(f"Error enviando Slack: {e.response['error']}")

    def send_daily_digest(self, new_products: list, price_events: list):
        """Envia un resumen diario a Slack."""
        if not self.client or (not new_products and not price_events):
            return

        text_parts = []
        if new_products:
            text_parts.append(f"{len(new_products)} productos nuevos")
        if price_events:
            text_parts.append(f"{len(price_events)} cambios de precio")

        try:
            self.client.chat_postMessage(
                channel=self.slack_channel,
                text=f"Resumen diario: {', '.join(text_parts)}",
            )
            logger.info(f"Digest enviado: {len(new_products)} nuevos, {len(price_events)} precios")
        except SlackApiError as e:
            logger.error(f"Error enviando digest: {e.response['error']}")
