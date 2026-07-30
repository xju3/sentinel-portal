from app.services.notification_outbox import retry_delay_seconds


def test_outbox_retry_delay_is_exponential_and_bounded(monkeypatch):
    monkeypatch.setattr(
        "app.services.notification_outbox.settings."
        "notification_outbox_initial_backoff_seconds",
        2.0,
    )
    monkeypatch.setattr(
        "app.services.notification_outbox.settings."
        "notification_outbox_max_backoff_seconds",
        10.0,
    )

    assert retry_delay_seconds(1) == 2.0
    assert retry_delay_seconds(2) == 4.0
    assert retry_delay_seconds(3) == 8.0
    assert retry_delay_seconds(4) == 10.0
    assert retry_delay_seconds(100) == 10.0
