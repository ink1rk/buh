#!/usr/bin/env python3
"""Запуск моста и забор данных из первоисточников Apple.

    python -m phone                         HTTP: приём и MCP по /mcp
    python -m phone --stdio                 MCP по stdin/stdout
    python -m phone import-health FILE      выгрузка Здоровья (export.zip)
    python -m phone import-backup [DIR]     звонки и iMessage из копии iPhone
    python -m phone import-messages chat.db переписка из базы Messages
    python -m phone import-calls FILE       журнал звонков CallHistory
    python -m phone mac-sync [--watch]      новое с Mac, само
"""
import argparse
import json
import sys

from . import store
from .config import config


def _print(result):
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


def _progress(read):
    print(f"прочитано {read} записей…", file=sys.stderr, flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="phone",
        description="Мост с iPhone и Apple Watch: данные из Здоровья, "
                    "баз Mac и резервной копии, наружу — MCP.")
    parser.add_argument("--stdio", action="store_true",
                        help="MCP по stdin/stdout")
    parser.add_argument("--host", default=config.host)
    parser.add_argument("--port", type=int, default=config.port)
    sub = parser.add_subparsers(dest="cmd")

    health = sub.add_parser("import-health",
                            help="залить export.zip или export.xml из Здоровья")
    health.add_argument("path", help="архив или XML выгрузки")
    health.add_argument("--device", default="iPhone")
    health.add_argument("--since", default=None,
                        help="брать только записи после этой даты (ГГГГ-ММ-ДД)")

    bak = sub.add_parser("import-backup",
                         help="звонки и переписка из локальной копии iPhone")
    bak.add_argument("path", nargs="?", help="папка копии; пусто — последняя")
    bak.add_argument("--device", default=None)

    messages = sub.add_parser("import-messages",
                              help="прочитать chat.db / sms.db")
    messages.add_argument("path")
    messages.add_argument("--device", default="Mac")

    calls = sub.add_parser("import-calls",
                           help="прочитать CallHistory.storedata")
    calls.add_argument("path")
    calls.add_argument("--device", default="Mac")

    mac = sub.add_parser("mac-sync",
                         help="забрать новое из баз Mac")
    mac.add_argument("--watch", action="store_true",
                     help="следить и забирать по мере появления")
    mac.add_argument("--interval", type=int, default=30)
    mac.add_argument("--url", help="адрес моста, если он на другой машине")
    mac.add_argument("--token", help="токен устройства для --url")
    mac.add_argument("--messages", help="путь к chat.db")
    mac.add_argument("--calls", help="путь к CallHistory.storedata")

    args = parser.parse_args(argv)

    store.migrate()

    if args.stdio:
        from . import tools
        from .mcp import serve_stdio
        serve_stdio(tools.server)
        return

    if args.cmd == "import-health":
        from . import ingest
        from .apple import sync
        since = ingest.parse_time(args.since) if args.since else None
        device = sync.ensure_device(args.device)
        _print(sync.pull_health(args.path, device["id"], since=since,
                                progress=_progress))
        return

    if args.cmd == "import-backup":
        from .apple import sync
        device = sync.ensure_device(args.device) if args.device else None
        _print(sync.pull_backup(args.path, device_id=device["id"] if device else None))
        return

    if args.cmd == "import-messages":
        from .apple import sync
        device = sync.ensure_device(args.device, kind="mac")
        _print(sync.pull_messages(args.path, device["id"]))
        return

    if args.cmd == "import-calls":
        from .apple import sync
        device = sync.ensure_device(args.device, kind="mac")
        _print(sync.pull_calls(args.path, device["id"]))
        return

    if args.cmd == "mac-sync":
        from .apple import sync
        if args.watch:
            sync.watch(interval=args.interval, url=args.url, token=args.token,
                       messages_path=args.messages, calls_path=args.calls)
            return
        if args.url:
            _print(sync.push_remote(args.url, args.token or "",
                                    args.messages, args.calls))
            return
        _print(sync.pull_mac(messages_path=args.messages, calls_path=args.calls))
        return

    import uvicorn
    from .server import create_app
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
