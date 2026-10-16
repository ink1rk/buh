"""Calendar writes exist for Google and Yandex. Mail still has no writer."""

KINDS = ('calendar', 'email')
CALENDARS = ('google', 'yandex')


def registry(*, calendar_provider='', email_provider=''):
    return {'calendar': calendar_provider or '', 'email': email_provider or ''}


def plan_external(kind, provider):
    if kind not in KINDS:
        raise ValueError('Unsupported integration')
    if not provider:
        return {'outbound': False, 'state': 'waiting_external', 'reason': 'provider_not_configured'}
    return {'outbound': False, 'state': 'waiting_external', 'reason': 'writer_not_shipped'}


def plan_calendar(provider, credentials):
    if provider not in CALENDARS:
        return {'outbound': False, 'state': 'waiting_external', 'reason': 'provider_not_configured'}
    if not credentials:
        return {'outbound': False, 'state': 'waiting_external', 'reason': 'credentials_missing'}
    return {'outbound': True, 'state': 'running', 'reason': 'ready'}


def approval_effect(*, allowed, decision, provider, kind, credentials=False):
    if decision == 'reject':
        return {'task_state': 'cancelled', 'outbound': False, 'reason': 'rejected'}
    if not allowed:
        return {'task_state': None, 'outbound': False, 'reason': 'denied'}
    if kind == 'calendar':
        return plan_calendar(provider, credentials)
    plan = plan_external(kind, provider)
    if plan['outbound']:
        raise RuntimeError('Mail writes are not available in this release')
    return {'task_state': plan['state'], 'outbound': False, 'reason': plan['reason']}
