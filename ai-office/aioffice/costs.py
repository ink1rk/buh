"""Cursor estimates and the LiteLLM ledger are not a confirmed charge."""
import json
import urllib.request
from decimal import Decimal


def budget_blocks(week, month, reserve=Decimal('0.50')):
    return Decimal(week) + reserve > 20 or Decimal(month) + reserve > 100


def reconcile(*, estimated_usd, usage_api_status, litellm_spend_usd, dashboard_usd=None):
    """actual_confirmed is true only for a figure typed from the Cursor Dashboard.

    feature_unavailable, a token estimate, and LiteLLM spend never become a charge.
    """
    confirmed = usage_api_status == 'dashboard_confirmed' and dashboard_usd is not None
    return {
        'estimated_usd': None if estimated_usd is None else Decimal(estimated_usd),
        'usage_api_status': usage_api_status,
        'litellm_spend_usd': None if litellm_spend_usd is None else Decimal(litellm_spend_usd),
        'dashboard_usd': Decimal(dashboard_usd) if confirmed else None,
        'actual_confirmed': bool(confirmed),
    }


def budget_text(*, estimated, reserve_week, litellm_spend, usage_api_status):
    ledger = 'недоступен' if litellm_spend is None else f'${Decimal(litellm_spend):.4f}'
    return (
        f'Оценка Cursor по токенам: ${Decimal(estimated):.4f}. '
        f'Резерв за 7 дней: ${Decimal(reserve_week):.2f} из $20; за запрос $0.50. '
        f'Журнал LiteLLM: {ledger}. Статус usage API: {usage_api_status}. '
        'Это не счёт. Фактическое списание видно только в Cursor Dashboard.'
    )


def fetch_litellm_spend(url, key, timeout=3):
    """Read the local LiteLLM ledger. No provider key is sent."""
    if not url or not key:
        return None
    request = urllib.request.Request(
        url.rstrip('/') + '/global/spend',
        headers={'Authorization': 'Bearer ' + key},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if isinstance(body, dict) and 'spend' in body:
        return Decimal(str(body['spend']))
    return None
