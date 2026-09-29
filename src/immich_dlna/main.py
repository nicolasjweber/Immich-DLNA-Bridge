from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

# Ensure aiohttp uses the pure Python parser with lax mode enabled so Samsung Smart TVs
# sending duplicate User-Agent headers do not trigger 400 BadHttpMessage
os.environ["AIOHTTP_NO_EXTENSIONS"] = "1"

from aiohttp import http_parser, web

http_parser.HttpRequestParser.lax = True

from immich_dlna.config import Settings
from immich_dlna.dlna.catalog import ContentCatalog
from immich_dlna.dlna.connection_manager import ConnectionManagerService
from immich_dlna.dlna.content_directory import ContentDirectoryService
from immich_dlna.immich import ImmichClient
from immich_dlna.logging_config import configure_logging
from immich_dlna.metrics import MetricsRegistry
from immich_dlna.ssdp import SsdpServer
from immich_dlna.web import create_app


async def run_server() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    logger = logging.getLogger("immich_dlna")

    logger.info("Initializing Immich-DLNA service name=%s uuid=%s", settings.friendly_name, settings.server_uuid)
    logger.info(
        "Features: People=%s, UnnamedPeople=%s, Favorites=%s, Tags=%s, Years=%s, PreferJPEG=%s",
        settings.enable_people,
        settings.show_unnamed_people,
        settings.enable_favorites,
        settings.enable_tags,
        settings.enable_years,
        settings.prefer_jpeg,
    )

    metrics = MetricsRegistry()
    immich_client = ImmichClient(settings=settings, metrics=metrics)
    catalog = ContentCatalog(settings=settings, immich_client=immich_client)
    content_directory_service = ContentDirectoryService(catalog=catalog)
    connection_manager_service = ConnectionManagerService()

    app = create_app(
        settings=settings,
        content_directory_service=content_directory_service,
        connection_manager_service=connection_manager_service,
        immich_client=immich_client,
        metrics=metrics,
    )
    runner = web.AppRunner(app)

    ssdp_server = SsdpServer(settings=settings, metrics=metrics)
    stop_event = asyncio.Event()

    def _trigger_stop() -> None:
        logger.info("Shutdown requested")
        stop_event.set()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _trigger_stop)
    else:
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: _trigger_stop())
        except Exception:
            pass

    await immich_client.start()
    await runner.setup()
    site = web.TCPSite(runner, host=settings.http_host, port=settings.http_port)
    await site.start()
    logger.info("HTTP service listening on %s:%s (base_url=%s)", settings.http_host, settings.http_port, settings.base_url)

    try:
        await ssdp_server.start()
        logger.info("SSDP service listening on %s:%s", settings.ssdp_multicast_host, settings.ssdp_port)
    except Exception as exc:
        logger.warning("SSDP multicast listener failed to start (check port 1900 or host network mode): %s", exc)

    logger.info("Immich-DLNA bridge is up and running.")

    try:
        await stop_event.wait()
    finally:
        logger.info("Stopping services...")
        await ssdp_server.stop()
        await runner.cleanup()
        await immich_client.close()
        logger.info("Immich-DLNA stopped cleanly.")


def main() -> None:
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
