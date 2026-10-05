import sys

from mcp_common.errors import IntegrationError
from mcp_common.runtime import serve

from ad.server import create_server


def main() -> None:
    try:
        server = create_server()
    except IntegrationError as exc:
        print(f"config: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    serve(server)


if __name__ == "__main__":
    main()
