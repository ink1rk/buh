"""Render digest-pinned Kubernetes resources, with no embedded credentials.

Proxy URL, owner ids and provider keys come from the environment. An empty
AI_OFFICE_HTTP_PROXY omits proxy egress instead of inventing an address.
"""
import json
import os
import pathlib
import sys
from urllib.parse import urlparse

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
images = json.loads(pathlib.Path(sys.argv[2]).read_text())
PROXY = os.environ.get('AI_OFFICE_HTTP_PROXY', '').strip()
NO_PROXY = os.environ.get('AI_OFFICE_NO_PROXY', 'localhost,127.0.0.1,::1,10.0.0.0/8,.svc,.cluster.local')
ALLOWED = os.environ.get('AI_OFFICE_ALLOWED_USER_IDS', '').strip()
raw_tz = os.environ.get('AI_OFFICE_OWNER_TIMEZONE', '').strip()
OWNER_TZ = 'Europe/Moscow' if raw_tz.lower() in {'', '+3', '+03', '+03:00', 'utc+3', 'gmt+3', 'msk'} else raw_tz
API_CIDR = os.environ.get('AI_OFFICE_KUBE_API', '10.43.0.1/32')


def resource(kind, name, ns, spec=None, **extra):
    api = {'NetworkPolicy': 'networking.k8s.io/v1', 'Deployment': 'apps/v1', 'StatefulSet': 'apps/v1',
           'Role': 'rbac.authorization.k8s.io/v1', 'RoleBinding': 'rbac.authorization.k8s.io/v1'}.get(kind, 'v1')
    obj = {'apiVersion': api, 'kind': kind, 'metadata': {'name': name, 'namespace': ns, 'labels': {'app.kubernetes.io/part-of': 'ai-office'}}, **extra}
    if spec is not None:
        obj['spec'] = spec
    return obj


def write(name, objects):
    (out / name).write_text(json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': objects}, indent=2) + '\n')


def proxy_env():
    values = {'NO_PROXY': NO_PROXY, 'OWNER_TIMEZONE': OWNER_TZ, 'POLLING_ENABLED': 'true', 'ALLOWED_USER_IDS': ALLOWED}
    if PROXY:
        values.update({'HTTP_PROXY': PROXY, 'HTTPS_PROXY': PROXY, 'http_proxy': PROXY, 'https_proxy': PROXY, 'NODE_USE_ENV_PROXY': '1'})
    return [{'name': key, 'value': value} for key, value in values.items()]


def proxy_rule():
    if not PROXY:
        return []
    host = urlparse(PROXY).hostname
    port = urlparse(PROXY).port or 8080
    if not host:
        raise SystemExit('AI_OFFICE_HTTP_PROXY has no host')
    return [{'to': [{'ipBlock': {'cidr': host + '/32'}}], 'ports': [{'protocol': 'TCP', 'port': port}]}]


secure = {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}}
pg_container = {'name': 'postgres', 'image': images['postgres'], 'ports': [{'containerPort': 5432}],
                'env': [{'name': 'POSTGRES_PASSWORD', 'valueFrom': {'secretKeyRef': {'name': 'postgres-admin', 'key': 'password'}}},
                        {'name': 'PGDATA', 'value': '/var/lib/postgresql/data/pgdata'}],
                'securityContext': secure, 'resources': {'requests': {'cpu': '250m', 'memory': '256Mi'}, 'limits': {'cpu': '2', 'memory': '2Gi'}},
                'volumeMounts': [{'name': 'data', 'mountPath': '/var/lib/postgresql/data'}, {'name': 'run', 'mountPath': '/var/run/postgresql'}, {'name': 'tmp', 'mountPath': '/tmp'}],
                'readinessProbe': {'exec': {'command': ['pg_isready', '-U', 'postgres']}, 'initialDelaySeconds': 5, 'periodSeconds': 5},
                'livenessProbe': {'exec': {'command': ['pg_isready', '-U', 'postgres']}, 'initialDelaySeconds': 30, 'periodSeconds': 10}}
pg_pod = {'automountServiceAccountToken': False, 'securityContext': {'runAsNonRoot': True, 'runAsUser': 999, 'runAsGroup': 999, 'fsGroup': 999, 'seccompProfile': {'type': 'RuntimeDefault'}},
          'containers': [pg_container], 'volumes': [{'name': 'run', 'emptyDir': {}}, {'name': 'tmp', 'emptyDir': {}}]}
write('postgres.json', [resource('Service', 'postgres', 'ai-data', {'selector': {'app': 'postgres'}, 'ports': [{'port': 5432, 'targetPort': 5432}], 'clusterIP': 'None'}),
                        resource('StatefulSet', 'postgres', 'ai-data', {'serviceName': 'postgres', 'replicas': 1, 'selector': {'matchLabels': {'app': 'postgres'}},
                                 'template': {'metadata': {'labels': {'app': 'postgres'}}, 'spec': pg_pod},
                                 'volumeClaimTemplates': [{'metadata': {'name': 'data'}, 'spec': {'accessModes': ['ReadWriteOnce'], 'storageClassName': 'local-path', 'resources': {'requests': {'storage': '10Gi'}}}}]})])
gateway = resource('Deployment', 'gateway', 'ai-core', {
    'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': {'app': 'gateway'}},
    'template': {'metadata': {'labels': {'app': 'gateway'}}, 'spec': {
        'automountServiceAccountToken': False, 'terminationGracePeriodSeconds': 150,
        'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001, 'runAsGroup': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}},
        'containers': [{'name': 'gateway', 'image': images['app'], 'imagePullPolicy': 'Never', 'ports': [{'containerPort': 8080}],
                        'securityContext': secure, 'env': proxy_env(), 'envFrom': [{'secretRef': {'name': 'gateway-secrets'}}],
                        'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'}, 'limits': {'cpu': '1', 'memory': '512Mi'}},
                        'volumeMounts': [{'name': 'tmp', 'mountPath': '/tmp'}],
                        'readinessProbe': {'httpGet': {'path': '/health/ready', 'port': 8080}, 'initialDelaySeconds': 10, 'periodSeconds': 5},
                        'livenessProbe': {'httpGet': {'path': '/health/live', 'port': 8080}, 'initialDelaySeconds': 20, 'periodSeconds': 10}}],
        'volumes': [{'name': 'tmp', 'emptyDir': {'sizeLimit': '64Mi'}}]}}})
gateway['spec']['template']['spec']['containers'][0]['env'].append({'name': 'CALENDAR_PROVIDERS', 'value': 'google,yandex'})
gateway['spec']['template']['spec']['containers'][0]['envFrom'].append({'secretRef': {'name': 'calendar-secrets', 'optional': True}})
if 'cursor' in images:
    gateway['spec']['template']['spec']['containers'][0]['env'].extend([
        {'name': 'LLM_ENABLED', 'value': 'true'}, {'name': 'CURSOR_BRIDGE_URL', 'value': 'http://cursor-bridge.ai-integrations.svc.cluster.local:8081'}])
    gateway['spec']['template']['spec']['containers'][0]['envFrom'].append({'secretRef': {'name': 'cursor-client'}})
write('gateway.json', [gateway, resource('Service', 'gateway', 'ai-core', {'selector': {'app': 'gateway'}, 'ports': [{'port': 8080, 'targetPort': 8080}]})])
dns = {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}}, 'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
       'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]}
proxy_rules = proxy_rule()
core_selector = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'ai-core'}}, 'podSelector': {'matchLabels': {'app': 'gateway'}}}
job_selector = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'ai-jobs'}},
                'podSelector': {'matchExpressions': [{'key': 'app', 'operator': 'In', 'values': ['agent-smoke', 'specialist']}]}}
postgres_to = {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'ai-data'}}, 'podSelector': {'matchLabels': {'app': 'postgres'}}}], 'ports': [{'protocol': 'TCP', 'port': 5432}]}
policies = [resource('NetworkPolicy', 'default-deny', ns, {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress']}) for ns in ('ai-core', 'ai-data', 'ai-jobs')]
policies += [resource('NetworkPolicy', 'gateway-allowed', 'ai-core', {'podSelector': {'matchLabels': {'app': 'gateway'}}, 'policyTypes': ['Ingress', 'Egress'],
    'ingress': [{'from': [job_selector], 'ports': [{'protocol': 'TCP', 'port': 8080}]}],
    'egress': [dns, *proxy_rules, postgres_to]}),
    resource('NetworkPolicy', 'postgres-from-gateway', 'ai-data', {'podSelector': {'matchLabels': {'app': 'postgres'}}, 'policyTypes': ['Ingress'], 'ingress': [{'from': [core_selector], 'ports': [{'protocol': 'TCP', 'port': 5432}]}]}),
    resource('NetworkPolicy', 'jobs-to-core', 'ai-jobs', {'podSelector': {'matchExpressions': [{'key': 'app', 'operator': 'In', 'values': ['agent-smoke', 'specialist']}]}, 'policyTypes': ['Egress'], 'egress': [dns, *proxy_rules, {'to': [core_selector], 'ports': [{'protocol': 'TCP', 'port': 8080}]}]})]
write('network.json', policies)
resources = ['network.json', 'postgres.json', 'gateway.json']
if (out / 'namespace-guards.json').exists():
    resources.insert(0, 'namespace-guards.json')
if 'cursor' in images:
    cursor = resource('Deployment', 'cursor-bridge', 'ai-integrations', {
        'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': {'app': 'cursor-bridge'}},
        'template': {'metadata': {'labels': {'app': 'cursor-bridge'}}, 'spec': {
            'automountServiceAccountToken': False, 'terminationGracePeriodSeconds': 90,
            'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001, 'runAsGroup': 10001, 'fsGroup': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}},
            'containers': [{'name': 'cursor', 'image': images['cursor'], 'imagePullPolicy': 'Never', 'securityContext': secure,
                            'env': [item for item in proxy_env() if item['name'] in ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'NODE_USE_ENV_PROXY')],
                            'envFrom': [{'secretRef': {'name': 'cursor-provider'}}],
                            'ports': [{'containerPort': 8081}], 'volumeMounts': [{'name': 'tmp', 'mountPath': '/tmp'}],
                            'resources': {'requests': {'cpu': '200m', 'memory': '384Mi'}, 'limits': {'cpu': '2', 'memory': '1536Mi'}},
                            'readinessProbe': {'httpGet': {'path': '/health/ready', 'port': 8081}, 'initialDelaySeconds': 5, 'periodSeconds': 5},
                            'livenessProbe': {'httpGet': {'path': '/health/live', 'port': 8081}, 'initialDelaySeconds': 20, 'periodSeconds': 10}}],
            'volumes': [{'name': 'tmp', 'emptyDir': {'sizeLimit': '512Mi'}}]}}})
    write('cursor.json', [cursor, resource('Service', 'cursor-bridge', 'ai-integrations', {'selector': {'app': 'cursor-bridge'}, 'ports': [{'port': 8081, 'targetPort': 8081}]})])
    cursor_selector = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'ai-integrations'}}, 'podSelector': {'matchLabels': {'app': 'cursor-bridge'}}}
    extra = [resource('NetworkPolicy', 'default-deny', 'ai-integrations', {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress']}),
             resource('NetworkPolicy', 'cursor-bridge-allowed', 'ai-integrations', {'podSelector': {'matchLabels': {'app': 'cursor-bridge'}}, 'policyTypes': ['Ingress', 'Egress'],
                 'ingress': [{'from': [core_selector, {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'ai-core'}}, 'podSelector': {'matchLabels': {'app': 'job-launcher'}}}], 'ports': [{'protocol': 'TCP', 'port': 8081}]}],
                 # The SDK's native HTTP/2 sockets use the mandatory host TUN.
                 # VM nft guard prevents direct eth0 egress even on TUN failure.
                 'egress': [dns, *proxy_rules, {'to': [{'ipBlock': {'cidr': '0.0.0.0/0', 'except': ['10.0.0.0/8', '127.0.0.0/8', '169.254.0.0/16', '172.16.0.0/12', '192.168.0.0/16']}}], 'ports': [{'protocol': 'TCP', 'port': 443}]}]}),
             resource('NetworkPolicy', 'gateway-to-cursor', 'ai-core', {'podSelector': {'matchLabels': {'app': 'gateway'}}, 'policyTypes': ['Egress'], 'egress': [{'to': [cursor_selector], 'ports': [{'protocol': 'TCP', 'port': 8081}]}]})]
    write('cursor-network.json', extra)
    resources.extend(['cursor-network.json', 'cursor.json'])
launcher_env = [{'name': 'LAUNCHER_ENABLED', 'value': 'true'}, {'name': 'APP_IMAGE', 'value': images['app']},
                {'name': 'POLLING_ENABLED', 'value': 'false'}]
launcher_env.extend(item for item in proxy_env() if item['name'] in ('ALLOWED_USER_IDS', 'OWNER_TIMEZONE', 'NO_PROXY'))
launcher_env_from = [{'secretRef': {'name': 'launcher-secrets'}}]
if 'cursor' in images:
    launcher_env.extend([{'name': 'LLM_ENABLED', 'value': 'true'}, {'name': 'CURSOR_BRIDGE_URL', 'value': 'http://cursor-bridge.ai-integrations.svc.cluster.local:8081'}])
    launcher_env_from.append({'secretRef': {'name': 'cursor-client'}})
launcher = resource('Deployment', 'job-launcher', 'ai-core', {
    'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': {'app': 'job-launcher'}},
    'template': {'metadata': {'labels': {'app': 'job-launcher'}}, 'spec': {
        'serviceAccountName': 'job-launcher', 'automountServiceAccountToken': True, 'terminationGracePeriodSeconds': 30,
        'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001, 'runAsGroup': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}},
        'containers': [{'name': 'launcher', 'image': images['app'], 'imagePullPolicy': 'Never',
                        'command': ['python', '-m', 'aioffice.launcher'], 'securityContext': secure,
                        'env': launcher_env, 'envFrom': launcher_env_from,
                        'resources': {'requests': {'cpu': '50m', 'memory': '128Mi'}, 'limits': {'cpu': '500m', 'memory': '256Mi'}},
                        'volumeMounts': [{'name': 'tmp', 'mountPath': '/tmp'}]}],
        'volumes': [{'name': 'tmp', 'emptyDir': {'sizeLimit': '64Mi'}}]}}})
role = {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'Role', 'metadata': {'name': 'job-launcher', 'namespace': 'ai-jobs'},
        'rules': [{'apiGroups': ['batch'], 'resources': ['jobs'], 'verbs': ['get', 'list', 'create']},
                  {'apiGroups': [''], 'resources': ['secrets'], 'verbs': ['get', 'create']}]}
binding = {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'RoleBinding', 'metadata': {'name': 'job-launcher', 'namespace': 'ai-jobs'},
           'subjects': [{'kind': 'ServiceAccount', 'name': 'job-launcher', 'namespace': 'ai-core'}],
           'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': 'job-launcher'}}
account = {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {'name': 'job-launcher', 'namespace': 'ai-core'}}
write('launcher.json', [account, role, binding, launcher])
launcher_selector = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'ai-core'}}, 'podSelector': {'matchLabels': {'app': 'job-launcher'}}}
launcher_egress = [dns, postgres_to, {'to': [{'ipBlock': {'cidr': API_CIDR}}], 'ports': [{'protocol': 'TCP', 'port': 443}]}]
if 'cursor' in images:
    launcher_egress.append({'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'ai-integrations'}}, 'podSelector': {'matchLabels': {'app': 'cursor-bridge'}}}], 'ports': [{'protocol': 'TCP', 'port': 8081}]})
write('launcher-network.json', [
    resource('NetworkPolicy', 'launcher-allowed', 'ai-core', {'podSelector': {'matchLabels': {'app': 'job-launcher'}}, 'policyTypes': ['Egress'], 'egress': launcher_egress}),
    resource('NetworkPolicy', 'postgres-from-launcher', 'ai-data', {'podSelector': {'matchLabels': {'app': 'postgres'}}, 'policyTypes': ['Ingress'], 'ingress': [{'from': [launcher_selector], 'ports': [{'protocol': 'TCP', 'port': 5432}]}]}),
])
resources.extend(['launcher-network.json', 'launcher.json'])
if 'litellm' in images:
    # No DATABASE_URL: the image does not ship the Prisma query engine, and this
    # pod has no provider credentials. Spend stays in the LiteLLM process.
    config = ('model_list: []\n'
              'general_settings:\n'
              '  master_key: os.environ/LITELLM_MASTER_KEY\n'
              '  store_model_in_db: false\n'
              'litellm_settings:\n'
              '  drop_params: true\n'
              '  set_verbose: false\n')
    configmap = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'litellm-config', 'namespace': 'ai-integrations'}, 'data': {'config.yaml': config}}
    litellm = resource('Deployment', 'litellm', 'ai-integrations', {
        'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': {'app': 'litellm'}},
        'template': {'metadata': {'labels': {'app': 'litellm'}}, 'spec': {
            'automountServiceAccountToken': False,
            'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001, 'runAsGroup': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}},
            'containers': [{'name': 'litellm', 'image': images['litellm'], 'imagePullPolicy': 'Never',
                            'command': ['/app/.venv/bin/litellm', '--config', '/config/config.yaml', '--port', '4000', '--host', '0.0.0.0'],
                            'securityContext': {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}},
                            'env': [{'name': 'HOME', 'value': '/tmp'}] + [item for item in proxy_env() if item['name'] in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY')],
                            'envFrom': [{'secretRef': {'name': 'litellm-secrets'}}],
                            'ports': [{'containerPort': 4000}],
                            'volumeMounts': [{'name': 'config', 'mountPath': '/config', 'readOnly': True}, {'name': 'tmp', 'mountPath': '/tmp'}],
                            'resources': {'requests': {'cpu': '200m', 'memory': '1Gi'}, 'limits': {'cpu': '1', 'memory': '2Gi'}},
                            'readinessProbe': {'httpGet': {'path': '/health/readiness', 'port': 4000}, 'initialDelaySeconds': 20, 'periodSeconds': 10},
                            'livenessProbe': {'httpGet': {'path': '/health/liveliness', 'port': 4000}, 'initialDelaySeconds': 40, 'periodSeconds': 20}}],
            'volumes': [{'name': 'config', 'configMap': {'name': 'litellm-config'}}, {'name': 'tmp', 'emptyDir': {'sizeLimit': '256Mi'}}]}}})
    write('litellm.json', [configmap, litellm, resource('Service', 'litellm', 'ai-integrations', {'selector': {'app': 'litellm'}, 'ports': [{'port': 4000, 'targetPort': 4000}]})])
    litellm_selector = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'ai-integrations'}}, 'podSelector': {'matchLabels': {'app': 'litellm'}}}
    write('litellm-network.json', [
        resource('NetworkPolicy', 'litellm-allowed', 'ai-integrations', {'podSelector': {'matchLabels': {'app': 'litellm'}}, 'policyTypes': ['Ingress', 'Egress'],
                  'ingress': [{'from': [core_selector, launcher_selector], 'ports': [{'protocol': 'TCP', 'port': 4000}]}],
                  'egress': [dns, postgres_to, *proxy_rules]}),
        resource('NetworkPolicy', 'postgres-from-litellm', 'ai-data', {'podSelector': {'matchLabels': {'app': 'postgres'}}, 'policyTypes': ['Ingress'],
                  'ingress': [{'from': [litellm_selector], 'ports': [{'protocol': 'TCP', 'port': 5432}]}]}),
        resource('NetworkPolicy', 'gateway-to-litellm', 'ai-core', {'podSelector': {'matchLabels': {'app': 'gateway'}}, 'policyTypes': ['Egress'],
                  'egress': [{'to': [litellm_selector], 'ports': [{'protocol': 'TCP', 'port': 4000}]}]}),
    ])
    gateway['spec']['template']['spec']['containers'][0]['env'].append({'name': 'LITELLM_URL', 'value': 'http://litellm.ai-integrations.svc.cluster.local:4000'})
    gateway['spec']['template']['spec']['containers'][0]['envFrom'].append({'secretRef': {'name': 'litellm-reader'}})
    write('gateway.json', [gateway, resource('Service', 'gateway', 'ai-core', {'selector': {'app': 'gateway'}, 'ports': [{'port': 8080, 'targetPort': 8080}]})])
    resources.extend(['litellm-network.json', 'litellm.json'])
(out / 'kustomization.yaml').write_text('apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n' + ''.join('  - ' + x + '\n' for x in resources))

