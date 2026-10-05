"""Мост в финансы: платежи из календаря и письма про деньги."""
import datetime


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class FakeClient:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        return FakeResponse(self.rows)

    def post(self, url, json=None):
        return FakeResponse({"id": 1, "duplicate": False})


def test_completed_payments_stay_out_of_the_schedule(monkeypatch):
    from core import finance_bridge
    from core.config import config

    today = datetime.datetime.now(config.tz).date()
    rows = [
        {"id": 1, "title": "Интернет", "amount": 890,
         "event_date": (today + datetime.timedelta(days=2)).isoformat(),
         "is_completed": False},
        {"id": 2, "title": "Уже оплачено", "amount": 500,
         "event_date": (today + datetime.timedelta(days=1)).isoformat(),
         "is_completed": True},
        {"id": 3, "title": "Далеко", "amount": 1000,
         "event_date": (today + datetime.timedelta(days=40)).isoformat()},
    ]
    monkeypatch.setattr(finance_bridge, "_client", lambda: FakeClient(rows))

    events = finance_bridge.finance_schedule(days=14)

    assert [e.summary for e in events] == ["Интернет · 890 ₽"]
    assert events[0].all_day
    assert events[0].account == "finance"


def test_a_dead_finance_api_does_not_break_the_schedule(monkeypatch):
    from core import finance_bridge

    class Dead:
        def __enter__(self):
            raise OSError("нет связи")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(finance_bridge, "_client", Dead)
    assert finance_bridge.finance_schedule() == []
