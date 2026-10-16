"""Render a Job only from a fixed template and a checked task id."""

from __future__ import annotations

import re

TASK_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Placeholder digest. The launcher refuses to submit it to a cluster.
PLACEHOLDER_DIGEST = "sha256:" + "0" * 64

TEMPLATES: dict[str, dict] = {
    "researcher": {
        "image": f"registry.example.invalid/ai-office/agent-worker@{PLACEHOLDER_DIGEST}",
        "command": ["run-task"],
        "namespace": "ai-jobs",
        "service_account": "agent-job",
        "requests": {"cpu": "100m", "memory": "256Mi"},
        "limits": {"cpu": "1000m", "memory": "1Gi"},
        "active_deadline_seconds": 900,
        "placeholder": True,
    }
}


class TemplateError(Exception):
    pass


def render_job(template_name: str, task_id: str) -> dict:
    if template_name not in TEMPLATES:
        raise TemplateError("template is not on the allowlist")
    if not TASK_ID.fullmatch(task_id):
        raise TemplateError("task id contains characters that cannot be an argument")
    if any(token in task_id for token in (" ", ";", "|", "$", "`", "\n")):
        raise TemplateError("task id is not a single argument")
    spec = TEMPLATES[template_name]
    if spec["placeholder"]:
        raise TemplateError("image digest is still a placeholder")
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": f"agent-run-{task_id[:20].lower()}",
            "namespace": spec["namespace"],
            "labels": {"app.kubernetes.io/part-of": "ai-office", "ai-office/task": task_id[:63]},
        },
        "spec": {
            "backoffLimit": 1,
            "activeDeadlineSeconds": spec["active_deadline_seconds"],
            "ttlSecondsAfterFinished": 600,
            "template": {
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "serviceAccountName": spec["service_account"],
                    "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [
                        {
                            "name": "agent",
                            "image": spec["image"],
                            "command": list(spec["command"]),
                            "args": ["--task-id", task_id],
                            "resources": {"requests": spec["requests"], "limits": spec["limits"]},
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        }
                    ],
                }
            },
        },
    }
