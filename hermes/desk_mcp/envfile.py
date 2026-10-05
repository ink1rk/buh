"""Окружение ассистента для процесса MCP.

Hermes запускает сервер со своим урезанным env и не передаёт пароли ящиков.
Они остаются в /etc/assistant.env на этой же машине. В вывод процесса
значения не попадают: stdout занят протоколом.
"""
import os


def load_env_file(path=None):
    path = path if path is not None else os.environ.get(
        "ASSISTANT_ENV_FILE", "/etc/assistant.env")
    if not path or not os.path.isfile(path):
        return 0
    loaded = 0
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ[key] = value
            loaded += 1
    return loaded
