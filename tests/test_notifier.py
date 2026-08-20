from unittest.mock import MagicMock, patch

from src.notifier import Notifier


def test_send_daily_digest_posts_expected_payload(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/webhook/digest")
    notifier = Notifier()

    new_products = [{"competitor": "Titanium Strength", "title": "Barra Z",
                      "sku": "TS-1", "url": "https://x/1"}]
    price_events = [{"competitor": "Fitness Tech", "title": "Rack", "sku": "FT-2",
                      "old_price": 100.0, "new_price": 90.0, "percent_change": -10.0}]

    with patch("src.notifier.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        notifier.send_daily_digest(new_products, price_events)

    assert mock_post.called
    args, kwargs = mock_post.call_args
    assert args[0] == "https://n8n.example/webhook/digest"
    assert kwargs["json"]["new_products"][0]["title"] == "Barra Z"
    assert kwargs["json"]["price_events"][0]["percent_change"] == -10.0
    assert kwargs["timeout"] == 10.0


def test_send_daily_digest_skips_when_webhook_not_configured(monkeypatch):
    monkeypatch.delenv("N8N_WEBHOOK_URL", raising=False)
    notifier = Notifier()

    with patch("src.notifier.httpx.post") as mock_post:
        notifier.send_daily_digest(
            [{"competitor": "X", "title": "Y", "url": "https://z"}], [])

    mock_post.assert_not_called()


def test_send_daily_digest_skips_when_nothing_to_report(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/webhook/digest")
    notifier = Notifier()

    with patch("src.notifier.httpx.post") as mock_post:
        notifier.send_daily_digest([], [])

    mock_post.assert_not_called()


def test_send_daily_digest_logs_and_continues_on_http_error(monkeypatch, caplog):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/webhook/digest")
    notifier = Notifier()

    with patch("src.notifier.httpx.post", side_effect=Exception("boom")):
        notifier.send_daily_digest(
            [{"competitor": "X", "title": "Y", "url": "https://z"}], [])
