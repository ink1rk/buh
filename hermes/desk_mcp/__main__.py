"""stdio-MCP для Hermes.

    python -m desk_mcp yandex
    python -m desk_mcp gmail
    python -m desk_mcp calendar
    python -m desk_mcp notes
    python -m desk_mcp telegram
    python -m desk_mcp voice

Пароли читаются из ASSISTANT_ENV_FILE до импорта настроек. На stdout — только
JSON-RPC, поэтому сервер не печатает ни баннер, ни секреты.
"""
import sys

from desk_mcp.envfile import load_env_file

load_env_file()

from desk_mcp.servers import KINDS, build  # noqa: E402
from phone.mcp import serve_stdio  # noqa: E402


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    kind = args[0] if args else ""
    if kind not in KINDS:
        sys.stderr.write(
            "нужен сервер: " + ", ".join(KINDS) + "\n")
        return 2
    serve_stdio(build(kind))
    return 0


if __name__ == "__main__":
    sys.exit(main())
