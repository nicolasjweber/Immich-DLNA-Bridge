from __future__ import annotations

import io
import logging
import re
import time
from typing import Any

import aiohttp
from aiohttp import http_parser, web, web_protocol
from PIL import Image


class SamsungFriendlyHttpRequestParser(http_parser.HttpRequestParserPy):
    """
    Tolerant HTTP request parser for Samsung Smart TVs and UPnP clients.

    1. lax = True (allows duplicate singleton headers such as User-Agent sent by Samsung TVs).
    2. Normalizes bare LF (\\n) and double CR (\\r\\r\\n) to standard CRLF (\\r\\n) in HTTP request line
       and headers, preventing aiohttp's strict 'Bad line ending, expected CRLF' 400 BadHttpMessage.
    """
    lax = True

    def feed_data(self, data: bytes) -> tuple[list[Any], bool, bytes]:
        if self._payload_parser is None and not self._upgraded and (data or self._tail):
            if self._tail:
                data = self._tail + data
                self._tail = b""
            # Find the header/body boundary: \\r\\n\\r\\n, \\n\\n, \\r\\n\\n, or \\n\\r\\n
            match = re.search(rb"(\r?\n\r?\n)", data)
            if match:
                header_part = data[:match.start()]
                body_part = data[match.end():]
                # Normalize line endings in header part
                header_part = re.sub(rb"(?<!\r)\n", rb"\r\n", header_part)
                header_part = header_part.replace(b"\r\r\n", b"\r\n")
                data = header_part + b"\r\n\r\n" + body_part
            else:
                # Partial headers chunk: normalize bare LF to CRLF
                data = re.sub(rb"(?<!\r)\n", rb"\r\n", data)
                data = data.replace(b"\r\r\n", b"\r\n")
        return super().feed_data(data)


http_parser.HttpRequestParserPy.lax = True
web_protocol.HttpRequestParser = SamsungFriendlyHttpRequestParser

from immich_dlna.config import Settings
from immich_dlna.dlna.connection_manager import ConnectionManagerService
from immich_dlna.dlna.content_directory import ContentDirectoryService
from immich_dlna.dlna.device_description import build_device_description
from immich_dlna.dlna.model import Container, MediaItem
from immich_dlna.dlna.scpd import CONNECTION_MANAGER_SCPD, CONTENT_DIRECTORY_SCPD
from immich_dlna.dlna.soap import extract_action_from_soap_header, parse_action_request
from immich_dlna.explorer_html import EXPLORER_HTML
from immich_dlna.icons import (
    ICON_32_BMP,
    ICON_32_JPEG,
    ICON_32_PNG,
    ICON_48_BMP,
    ICON_48_JPEG,
    ICON_48_PNG,
    ICON_120_BMP,
    ICON_120_JPEG,
    ICON_120_PNG,
)
from immich_dlna.immich import ImmichClient, ImmichError
from immich_dlna.metrics import MetricsRegistry


def _soap_response(status_code: int, payload: str) -> web.Response:
    return web.Response(
        status=status_code,
        text=payload,
        content_type="text/xml",
        charset="utf-8",
        headers={
            "EXT": "",
            "Server": "Linux/4.0 UPnP/1.0 DLNADOC/1.50 Immich-DLNA/1.0",
        },
    )


def _convert_image_to_jpeg(raw_bytes: bytes) -> tuple[bytes, str]:
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            rgb_im = img.convert("RGB")
            buffer = io.BytesIO()
            rgb_im.save(buffer, format="JPEG", quality=90)
            return buffer.getvalue(), "image/jpeg"
    except Exception:
        return raw_bytes, "image/jpeg"


def _dlna_media_headers(
    is_video: bool,
    is_thumbnail: bool = False,
    mime_type: str = "image/jpeg",
) -> dict[str, str]:
    headers = {
        "Accept-Ranges": "bytes",
        "realTimeInfo.dlna.org": "DLNA.ORG_TLSt=0",
    }
    if is_video:
        headers["transferMode.dlna.org"] = "Streaming"
        headers["contentFeatures.dlna.org"] = (
            "DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"
        )
    else:
        headers["transferMode.dlna.org"] = "Interactive"
        if "png" in mime_type.lower():
            headers["contentFeatures.dlna.org"] = (
                "DLNA.ORG_PN=PNG_LRG;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000"
            )
        elif is_thumbnail:
            headers["contentFeatures.dlna.org"] = (
                "DLNA.ORG_PN=JPEG_TN;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000"
            )
        else:
            headers["contentFeatures.dlna.org"] = (
                "DLNA.ORG_PN=JPEG_LRG;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000"
            )
    return headers


def create_app(
    settings: Settings,
    content_directory_service: ContentDirectoryService,
    connection_manager_service: ConnectionManagerService,
    immich_client: ImmichClient,
    metrics: MetricsRegistry,
) -> web.Application:
    @web.middleware
    async def cors_middleware(request: web.Request, handler: web.Handler) -> web.StreamResponse:
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, SUBSCRIBE"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    @web.middleware
    async def request_metrics_middleware(
        request: web.Request,
        handler: web.Handler,
    ) -> web.StreamResponse:
        started_at = time.perf_counter()
        status = 500
        try:
            response = await handler(request)
            status = response.status
            return response
        except web.HTTPException as error:
            status = error.status
            raise
        finally:
            route = request.path
            route_info = request.match_info.route
            if route_info is not None:
                resource = getattr(route_info, "resource", None)
                canonical = getattr(resource, "canonical", None)
                if canonical:
                    route = canonical
            metrics.observe_request(
                method=request.method,
                route=route,
                status=status,
                duration_seconds=time.perf_counter() - started_at,
            )
            if status >= 500:
                metrics.increment_error("server")

    app = web.Application(middlewares=[cors_middleware, request_metrics_middleware])
    logger = logging.getLogger("immich_dlna.http")

    async def _stream_upstream_response(
        request: web.Request,
        upstream: aiohttp.ClientResponse,
        default_content_type: str | None = None,
    ) -> web.StreamResponse:
        content_type = upstream.headers.get("Content-Type", default_content_type or "")
        is_video = "video" in content_type.lower()
        is_thumb = "/thumbnail" in request.path
        
        # If upstream image is WebP and transcoding is enabled, convert to JPEG for TV compatibility
        if (
            settings.transcode_webp_to_jpeg
            and "webp" in content_type.lower()
        ):
            try:
                body = await upstream.read()
                jpeg_bytes, _ = _convert_image_to_jpeg(body)
                resp_headers = {
                    "Content-Length": str(len(jpeg_bytes)),
                    "Cache-Control": "public, max-age=86400",
                    **_dlna_media_headers(is_video=False, is_thumbnail=is_thumb, mime_type="image/jpeg"),
                }
                return web.Response(
                    body=jpeg_bytes,
                    content_type="image/jpeg",
                    headers=resp_headers,
                )
            finally:
                upstream.release()
                await immich_client.cleanup_retired_sessions()

        passthrough_headers = {}
        for header_name in (
            "Content-Type",
            "Content-Length",
            "Content-Range",
            "Accept-Ranges",
            "ETag",
            "Last-Modified",
            "Cache-Control",
        ):
            value = upstream.headers.get(header_name)
            if value:
                passthrough_headers[header_name] = value

        if default_content_type and "Content-Type" not in passthrough_headers:
            passthrough_headers["Content-Type"] = default_content_type

        # Inject DLNA compliance headers for Samsung Smart TV
        dlna_hdrs = _dlna_media_headers(
            is_video=is_video,
            is_thumbnail=is_thumb,
            mime_type=passthrough_headers.get("Content-Type", "image/jpeg"),
        )
        for k, v in dlna_hdrs.items():
            if k not in passthrough_headers:
                passthrough_headers[k] = v

        response = web.StreamResponse(status=upstream.status, headers=passthrough_headers)
        await response.prepare(request)

        # Handle HEAD requests cleanly without reading/writing stream chunks
        if request.method == "HEAD":
            upstream.release()
            await immich_client.cleanup_retired_sessions()
            return response

        try:
            async for chunk in upstream.content.iter_chunked(64 * 1024):
                await response.write(chunk)
        except (ConnectionResetError, RuntimeError) as error:
            logger.warning("Client disconnected during upstream stream: %s", error)
        finally:
            upstream.release()
            await immich_client.cleanup_retired_sessions()

        try:
            await response.write_eof()
        except (ConnectionResetError, RuntimeError):
            pass
        return response

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "server": "Immich-DLNA",
            "people_enabled": settings.enable_people,
            "videos_enabled": settings.enable_videos,
            "favorites_enabled": settings.enable_favorites,
            "tags_enabled": settings.enable_tags,
            "years_enabled": settings.enable_years,
        })

    async def metrics_endpoint(_request: web.Request) -> web.Response:
        payload = metrics.render_prometheus(cache_hit_ratio=immich_client.cache_hit_ratio())
        return web.Response(
            body=payload,
            headers={"Content-Type": metrics.content_type},
        )

    async def device_xml(request: web.Request) -> web.Response:
        logger.info("Device description requested remote=%s", request.remote)
        xml_payload = build_device_description(settings)
        return web.Response(text=xml_payload, content_type="text/xml", charset="utf-8")

    async def content_directory_scpd(request: web.Request) -> web.Response:
        logger.info("ContentDirectory SCPD requested remote=%s", request.remote)
        return web.Response(text=CONTENT_DIRECTORY_SCPD, content_type="text/xml", charset="utf-8")

    async def connection_manager_scpd(request: web.Request) -> web.Response:
        logger.info("ConnectionManager SCPD requested remote=%s", request.remote)
        return web.Response(text=CONNECTION_MANAGER_SCPD, content_type="text/xml", charset="utf-8")

    async def event_subscription(request: web.Request) -> web.Response:
        service_name = "ContentDirectory" if request.path.startswith("/ContentDirectory/") else "ConnectionManager"
        logger.info(
            "%s event endpoint called method=%s remote=%s",
            service_name,
            request.method,
            request.remote,
        )
        headers: dict[str, str] = {}
        if request.method.upper() == "SUBSCRIBE":
            headers["SID"] = request.headers.get("SID", f"uuid:{settings.server_uuid}")
            headers["TIMEOUT"] = request.headers.get("TIMEOUT", "Second-1800")
        return web.Response(status=200, headers=headers)

    async def content_directory_control(request: web.Request) -> web.Response:
        body = await request.read()
        action = extract_action_from_soap_header(request.headers.get("SOAPAction"))
        if action is None:
            try:
                action, _ = parse_action_request(body)
            except ValueError:
                logger.warning("Rejected malformed ContentDirectory SOAP request from %s", request.remote)
                return web.Response(status=400, text="Malformed SOAP request.")

        logger.info("ContentDirectory action=%s remote=%s", action, request.remote)
        status_code, payload = await content_directory_service.handle(action, body)
        return _soap_response(status_code, payload)

    async def connection_manager_control(request: web.Request) -> web.Response:
        body = await request.read()
        action = extract_action_from_soap_header(request.headers.get("SOAPAction"))
        if action is None:
            try:
                action, _ = parse_action_request(body)
            except ValueError:
                logger.warning("Rejected malformed ConnectionManager SOAP request from %s", request.remote)
                return web.Response(status=400, text="Malformed SOAP request.")

        logger.info("ConnectionManager action=%s remote=%s", action, request.remote)
        status_code, payload = connection_manager_service.handle(action)
        return _soap_response(status_code, payload)

    async def media_asset(request: web.Request) -> web.StreamResponse:
        asset_id = request.match_info.get("asset_id", "")
        range_header = request.headers.get("Range")
        logger.info("Media proxy request asset_id=%s remote=%s has_range=%s", asset_id, request.remote, bool(range_header))

        try:
            asset, upstream = await immich_client.open_asset_stream(
                asset_id,
                range_header,
                prefer_jpeg=settings.prefer_jpeg,
            )
        except ImmichError as error:
            logger.error("Media proxy failed before stream asset_id=%s error=%s", asset_id, error)
            return web.Response(status=502, text="Failed to fetch media from Immich.")

        default_content_type = "video/mp4" if asset.is_video else "image/jpeg"
        return await _stream_upstream_response(
            request=request,
            upstream=upstream,
            default_content_type=default_content_type,
        )

    async def media_asset_thumbnail(request: web.Request) -> web.StreamResponse:
        asset_id = request.match_info.get("asset_id", "")
        logger.info("Thumbnail proxy request asset_id=%s remote=%s", asset_id, request.remote)
        try:
            upstream = await immich_client.open_asset_thumbnail_stream(asset_id)
        except ImmichError as error:
            logger.error("Thumbnail proxy failed asset_id=%s error=%s", asset_id, error)
            return web.Response(status=502, text="Failed to fetch thumbnail from Immich.")

        return await _stream_upstream_response(
            request=request,
            upstream=upstream,
            default_content_type="image/jpeg",
        )

    async def media_person_thumbnail(request: web.Request) -> web.StreamResponse:
        person_id = request.match_info.get("person_id", "")
        logger.info("Person thumbnail proxy request person_id=%s remote=%s", person_id, request.remote)
        try:
            upstream = await immich_client.open_person_thumbnail_stream(person_id)
        except ImmichError as error:
            logger.error("Person thumbnail proxy failed person_id=%s error=%s", person_id, error)
            return web.Response(status=502, text="Failed to fetch person thumbnail from Immich.")

        return await _stream_upstream_response(
            request=request,
            upstream=upstream,
            default_content_type="image/jpeg",
        )

    async def explorer_ui(_request: web.Request) -> web.Response:
        return web.Response(text=EXPLORER_HTML, content_type="text/html", charset="utf-8")

    async def api_browse(request: web.Request) -> web.Response:
        object_id = request.query.get("id", "0")
        try:
            start = int(request.query.get("start", "0"))
        except ValueError:
            start = 0
        try:
            count = int(request.query.get("count", "500"))
        except ValueError:
            count = 500

        entries, total = await content_directory_service.catalog.browse(
            object_id=object_id,
            browse_flag="BrowseDirectChildren",
            starting_index=start,
            requested_count=count,
        )
        containers = []
        items = []
        for entry in entries:
            if isinstance(entry, Container):
                containers.append({
                    "id": entry.object_id,
                    "title": entry.title,
                    "art": entry.album_art_uri or "",
                    "childCount": entry.child_count,
                })
            elif isinstance(entry, MediaItem):
                items.append({
                    "id": entry.object_id,
                    "title": entry.title,
                    "thumb": entry.thumbnail_url or "",
                    "res": entry.resource_url or "",
                    "isVideo": entry.is_video,
                })
        return web.json_response({
            "id": object_id,
            "total": total,
            "containers": containers,
            "items": items,
        })

    def _icon_response(request: web.Request, data: bytes, content_type: str) -> web.Response:
        logger.info("Device icon requested: path=%s remote=%s content_type=%s", request.path, request.remote, content_type)
        return web.Response(
            body=data,
            content_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    async def icon_48_jpg(request: web.Request) -> web.Response:
        return _icon_response(request, ICON_48_JPEG, "image/jpeg")

    async def icon_48_png(request: web.Request) -> web.Response:
        return _icon_response(request, ICON_48_PNG, "image/png")

    async def icon_48_bmp(request: web.Request) -> web.Response:
        return _icon_response(request, ICON_48_BMP, "image/bmp")

    async def icon_120_jpg(request: web.Request) -> web.Response:
        return _icon_response(request, ICON_120_JPEG, "image/jpeg")

    async def icon_120_png(request: web.Request) -> web.Response:
        return _icon_response(request, ICON_120_PNG, "image/png")

    async def icon_120_bmp(request: web.Request) -> web.Response:
        return _icon_response(request, ICON_120_BMP, "image/bmp")

    async def icon_32_jpg(request: web.Request) -> web.Response:
        return _icon_response(request, ICON_32_JPEG, "image/jpeg")

    async def icon_32_png(request: web.Request) -> web.Response:
        return _icon_response(request, ICON_32_PNG, "image/png")

    async def icon_32_bmp(request: web.Request) -> web.Response:
        return _icon_response(request, ICON_32_BMP, "image/bmp")

    app.router.add_get("/", explorer_ui)
    app.router.add_get("/explore", explorer_ui)
    app.router.add_get("/api/browse", api_browse)
    app.router.add_get("/health", health)
    app.router.add_get("/metrics", metrics_endpoint)
    app.router.add_get("/device.xml", device_xml)

    # 48x48 icon endpoints & aliases
    app.router.add_get("/icon-48.jpg", icon_48_jpg)
    app.router.add_get("/icon-48.png", icon_48_png)
    app.router.add_get("/icon-48.bmp", icon_48_bmp)
    app.router.add_get("/icons/sm.jpg", icon_48_jpg)
    app.router.add_get("/icons/sm.png", icon_48_png)
    app.router.add_get("/icons/sm.bmp", icon_48_bmp)

    # 120x120 icon endpoints & aliases
    app.router.add_get("/icon-120.jpg", icon_120_jpg)
    app.router.add_get("/icon-120.png", icon_120_png)
    app.router.add_get("/icon-120.bmp", icon_120_bmp)
    app.router.add_get("/icons/lrg.jpg", icon_120_jpg)
    app.router.add_get("/icons/lrg.png", icon_120_png)
    app.router.add_get("/icons/lrg.bmp", icon_120_bmp)
    app.router.add_get("/icon.jpg", icon_120_jpg)
    app.router.add_get("/icon.png", icon_120_png)
    app.router.add_get("/icon.bmp", icon_120_bmp)

    # 32x32 icon endpoints & aliases
    app.router.add_get("/icon-32.jpg", icon_32_jpg)
    app.router.add_get("/icon-32.png", icon_32_png)
    app.router.add_get("/icon-32.bmp", icon_32_bmp)

    app.router.add_get("/ContentDirectory/scpd.xml", content_directory_scpd)
    app.router.add_post("/ContentDirectory/control", content_directory_control)
    app.router.add_route("*", "/ContentDirectory/event", event_subscription)
    app.router.add_get("/ConnectionManager/scpd.xml", connection_manager_scpd)
    app.router.add_post("/ConnectionManager/control", connection_manager_control)
    app.router.add_route("*", "/ConnectionManager/event", event_subscription)
    app.router.add_get("/media/asset/{asset_id}", media_asset)
    app.router.add_get("/media/asset/{asset_id}/thumbnail", media_asset_thumbnail)
    app.router.add_get("/media/person/{person_id}/thumbnail", media_person_thumbnail)
    return app
