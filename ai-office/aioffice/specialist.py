"""Sandboxed specialist worker. No Kubernetes token and no provider credentials."""
import json
import os
import urllib.request
import uuid

TRANSPORT = 'Specialist job reached the internal API. No shell, external tool, or paid transcription ran inside the job.'


def main():
    task_id = str(uuid.UUID(os.environ['TASK_ID']))
    base = os.environ['BROKER_URL'].rstrip('/')
    headers = {'Authorization': 'Bearer ' + os.environ['EXECUTION_TOKEN'], 'Content-Type': 'application/json'}
    with urllib.request.urlopen(urllib.request.Request(base + '/internal/tasks/' + task_id + '/specialist', headers=headers), timeout=20) as response:
        payload = json.load(response)
    content = (payload.get('content') or TRANSPORT)[:16000]
    body = json.dumps({'content': content}).encode()
    request = urllib.request.Request(base + '/internal/tasks/' + task_id + '/artifact', data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        if not json.load(response).get('saved'):
            raise RuntimeError('Artifact not saved')
    print('artifact-committed')


if __name__ == '__main__':
    main()
