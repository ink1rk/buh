#!/usr/bin/env python3
"""Запуск моста.

    python -m phone            # HTTP: приём с телефона и MCP по /mcp
    python -m phone --stdio    # MCP по stdio, для клиентов, которые сами
                               # запускают сервер (Cursor, Claude Desktop)
"""
import argparse

from . import store, tools
from .config import config
from .mcp import serve_stdio


def main():
    parser = argparse.ArgumentParser(prog="phone", description="Мост с iPhone и Apple Watch")
    parser.add_argument("--stdio", action="store_true", help="MCP по stdin/stdout")
    parser.add_argument("--host", default=config.host)
    parser.add_argument("--port", type=int, default=config.port)
    args = parser.parse_args()

    store.migrate()
    if args.stdio:
        serve_stdio(tools.server)
        return

    import uvicorn

    from .server import create_app
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
