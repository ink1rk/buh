"""External calendar and mail stay local until a provider and a writer exist."""

KINDS = ('calendar', 'email')


def registry(*, calendar_provider='', email_provider=''):
    return {'calendar': calendar_provider or '', 'email': email_provider or ''}


def plan_external(kind, provider):
    if kind not in KINDS:
        raise ValueError('Unsupported integration')
    if not provider:
        return {'outbound': False, 'state': 'waiting_external', 'reason': 'provider_not_configured'}
    # Naming a provider does not add a writer. No HTTP client is constructed here.
    return {'outbound': False, 'state': 'waiting_external', 'reason': 'writer_not_shipped'}


def approval_effect(*, allowed, decision, provider, kind):
    if decision == 'reject':
        return {'task_state': 'cancelled', 'outbound': False, 'reason': 'rejected'}
    if not allowed:
        return {'task_state': None, 'outbound': False, 'reason': 'denied'}
    plan = plan_external(kind, provider)
    if plan['outbound']:
        raise RuntimeError('External writes are not available in this release')
    return {'task_state': plan['state'], 'outbound': False, 'reason': plan['reason']}
