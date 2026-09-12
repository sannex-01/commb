"""
CommB Command Line Interface (CLI)
Entrypoint for standalone Python package and terminal operations.
"""

import sys
import os
import argparse
import uvicorn
from app.core.config import settings


def run_start(args):
    """Launch the CommB FastAPI / Uvicorn server."""
    port = args.port or settings.PORT or 8422
    host = args.host or settings.HOST or "0.0.0.0"
    reload = args.reload
    workers = args.workers if not reload else 1

    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url
        settings.DATABASE_URL = args.db_url

    print("=" * 60)
    print(f"[*] Starting CommB Assistant v{settings.APP_VERSION}")
    print(f"[*] Server Address: http://{host}:{port}")
    print(f"[*] Admin Portal:   http://{host}:{port}/_/admin")
    print(f"[*] Database URL:   {settings.DATABASE_URL.split('://')[0]}://...")
    print(f"[*] Operating Mode: {settings.BOT_MODE}")
    print("=" * 60)

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )


def run_doctor(args):
    """Run system health and environment diagnostics."""
    import asyncio
    try:
        from doctor import run_diagnostics
        asyncio.run(run_diagnostics())
    except ImportError:
        # Fallback if running as an installed package
        from app.core.database import init_db
        async def quick_check():
            print("[*] Running CommB Doctor Diagnostic...")
            try:
                await init_db()
                print(f"  [OK] Database ({settings.DATABASE_URL.split('://')[0]}) initialized successfully!")
            except Exception as e:
                print(f"  [FAIL] Database initialization failed: {e}")
            print(f"  [OK] LLM Provider: {settings.LLM_PROVIDER}")
            print("[*] Preflight diagnostic complete.")
        asyncio.run(quick_check())


def run_version(args):
    """Display current version information."""
    print(f"CommB Platform v{settings.APP_VERSION}")


def main():
    """Main CLI entrypoint for `commb` command."""
    parser = argparse.ArgumentParser(
        prog="commb",
        description="CommB - Open-Source AI Commerce Bots & Omnichannel Customer Support Platform",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"CommB v{settings.APP_VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # `commb start`
    start_parser = subparsers.add_parser("start", help="Start the CommB application server")
    start_parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,
        help="Port to bind the server to (default: 8422 or $PORT)",
    )
    start_parser.add_argument(
        "-H", "--host",
        type=str,
        default=None,
        help="Host address to bind to (default: 0.0.0.0)",
    )
    start_parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Custom Database URL (e.g. postgresql+asyncpg://user:pass@host:5432/commb)",
    )
    start_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for local development",
    )
    start_parser.add_argument(
        "-w", "--workers",
        type=int,
        default=1,
        help="Number of worker processes (production)",
    )
    start_parser.set_defaults(func=run_start)

    # `commb doctor`
    doctor_parser = subparsers.add_parser("doctor", help="Run preflight diagnostics and health checks")
    doctor_parser.set_defaults(func=run_doctor)

    # `commb version`
    version_parser = subparsers.add_parser("version", help="Print the CommB version")
    version_parser.set_defaults(func=run_version)

    args = parser.parse_args()

    if not args.command:
        # Default behavior when running `commb` without arguments is to start the server
        args.port = None
        args.host = None
        args.db_url = None
        args.reload = False
        args.workers = 1
        run_start(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
