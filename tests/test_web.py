from __future__ import annotations

import io
from unittest.mock import AsyncMock

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image
import pytest

from immich_dlna.config import Settings
from immich_dlna.dlna.catalog import ContentCatalog
from immich_dlna.dlna.connection_manager import ConnectionManagerService
from immich_dlna.dlna.content_directory import ContentDirectoryService
from immich_dlna.immich import ImmichClient, ImmichPerson
from immich_dlna.metrics import MetricsRegistry
from immich_dlna.web import _convert_image_to_jpeg, create_app


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        immich_url="http://mock-immich:2283/api",
        immich_api_token="dummy-token",
        immich_verify_ssl=False,
        http_host="0.0.0.0",
        http_port=8200,
        base_url="http://192.168.1.100:8200",
        friendly_name="Immich DLNA Web Test",
        server_uuid="test-uuid",
        log_level="INFO",
        ssdp_multicast_host="239.255.255.250",
        ssdp_port=1900,
        ssdp_max_age=1800,
        ssdp_notify_interval=300,
        metadata_cache_ttl_seconds=60,
        metadata_cache_max_entries=1000,
        immich_timeout_seconds=5.0,
        immich_stream_read_timeout_seconds=30.0,
        immich_max_concurrent_requests=10,
        enable_people=True,
        show_unnamed_people=False,
        enable_favorites=True,
        enable_tags=True,
        enable_years=True,
        image_quality="auto",
        prefer_jpeg=True,
        transcode_webp_to_jpeg=True,
    )


@pytest.fixture
def mock_immich_client() -> ImmichClient:
    client = AsyncMock(spec=ImmichClient)
    client.cache_hit_ratio.return_value = 0.85
    client.list_people.return_value = [
        ImmichPerson(
            person_id="p1",
            name="Alice",
            thumbnail_path="/thumbs/p1",
            is_favorite=True,
            is_hidden=False,
        )
    ]
    return client


@pytest.mark.asyncio
async def test_health_and_device_xml(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    cd_service = ContentDirectoryService(catalog=catalog)
    cm_service = ConnectionManagerService()
    metrics = MetricsRegistry()

    app = create_app(
        settings=mock_settings,
        content_directory_service=cd_service,
        connection_manager_service=cm_service,
        immich_client=mock_immich_client,
        metrics=metrics,
    )

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # Health
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["people_enabled"] is True

        # Device XML
        resp_xml = await client.get("/device.xml")
        assert resp_xml.status == 200
        text = await resp_xml.text()
        assert "Immich DLNA Web Test" in text
        assert "urn:schemas-upnp-org:device:MediaServer:1" in text
        assert "urn:schemas-upnp-org:service:ContentDirectory:1" in text
        assert "X_DLNACAP" in text
        assert "ProductCap" in text
        assert "iconList" in text
        assert "URLBase" not in text
        assert "/icon-48.jpg" in text
        assert "/icon-48.png" in text
        assert "/icon-48.bmp" in text

        # Icons (PNG, JPEG, BMP, and aliases)
        resp_icon48 = await client.get("/icon-48.png")
        assert resp_icon48.status == 200
        assert resp_icon48.headers.get("Content-Type") == "image/png"

        resp_icon120 = await client.get("/icon-120.png")
        assert resp_icon120.status == 200
        assert resp_icon120.headers.get("Content-Type") == "image/png"

        resp_icon_def = await client.get("/icon.png")
        assert resp_icon_def.status == 200

        resp_icon_jpg = await client.get("/icon-120.jpg")
        assert resp_icon_jpg.status == 200
        assert resp_icon_jpg.headers.get("Content-Type") == "image/jpeg"

        resp_icon_bmp = await client.get("/icon-120.bmp")
        assert resp_icon_bmp.status == 200
        assert resp_icon_bmp.headers.get("Content-Type") == "image/bmp"

        resp_icon_sm_jpg = await client.get("/icons/sm.jpg")
        assert resp_icon_sm_jpg.status == 200
        assert resp_icon_sm_jpg.headers.get("Content-Type") == "image/jpeg"

        resp_icon_32_png = await client.get("/icon-32.png")
        assert resp_icon_32_png.status == 200
        assert resp_icon_32_png.headers.get("Content-Type") == "image/png"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_soap_browse_people(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    cd_service = ContentDirectoryService(catalog=catalog)
    cm_service = ConnectionManagerService()
    metrics = MetricsRegistry()

    app = create_app(
        settings=mock_settings,
        content_directory_service=cd_service,
        connection_manager_service=cm_service,
        immich_client=mock_immich_client,
        metrics=metrics,
    )

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        soap_body = """<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
          <s:Body>
            <u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
              <ObjectID>people</ObjectID>
              <BrowseFlag>BrowseDirectChildren</BrowseFlag>
              <Filter>*</Filter>
              <StartingIndex>0</StartingIndex>
              <RequestedCount>50</RequestedCount>
              <SortCriteria></SortCriteria>
            </u:Browse>
          </s:Body>
        </s:Envelope>"""

        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": '"urn:schemas-upnp-org:service:ContentDirectory:1#Browse"',
        }

        resp = await client.post("/ContentDirectory/control", data=soap_body, headers=headers)
        assert resp.status == 200
        text = await resp.text()
        assert "BrowseResponse" in text
        assert "Meiste Fotos" in text
        assert "people:photos" in text
        assert "Nach Name (A-Z)" in text

        # Now browse into people:photos
        soap_subfolder = soap_body.replace("<ObjectID>people</ObjectID>", "<ObjectID>people:photos</ObjectID>")
        resp_sub = await client.post("/ContentDirectory/control", data=soap_subfolder, headers=headers)
        assert resp_sub.status == 200
        text_sub = await resp_sub.text()
        assert "Alice" in text_sub
        assert "person:p1" in text_sub
        assert "albumArtURI" in text_sub
    finally:
        await client.close()


def test_convert_image_to_jpeg() -> None:
    # Create a small RGB image and save as WebP
    img = Image.new("RGB", (32, 32), color=(255, 0, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP")
    webp_bytes = buffer.getvalue()

    # Transcode to JPEG
    jpeg_bytes, mime = _convert_image_to_jpeg(webp_bytes)
    assert mime == "image/jpeg"
    assert len(jpeg_bytes) > 0

    # Verify it is now a valid JPEG
    out_img = Image.open(io.BytesIO(jpeg_bytes))
    assert out_img.format == "JPEG"
    assert out_img.size == (32, 32)


@pytest.mark.asyncio
async def test_duplicate_user_agent_handling(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    import asyncio
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    cd_service = ContentDirectoryService(catalog=catalog)
    cm_service = ConnectionManagerService()
    metrics = MetricsRegistry()

    app = create_app(
        settings=mock_settings,
        content_directory_service=cd_service,
        connection_manager_service=cm_service,
        immich_client=mock_immich_client,
        metrics=metrics,
    )

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # Simulate Samsung Smart TV sending duplicate User-Agent headers
        reader, writer = await asyncio.open_connection(client.server.host, client.server.port)
        raw_req = (
            b"GET /device.xml HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"User-Agent: DLNADOC/1.50\r\n"
            b"User-Agent: SEC_HHP_[TV] Samsung SmartTV\r\n"
            b"\r\n"
        )
        writer.write(raw_req)
        await writer.drain()
        resp_data = await reader.read(1024)
        writer.close()
        await writer.wait_closed()

        assert b"HTTP/1.1 200 OK" in resp_data

        # Simulate Samsung Smart TV sending bare LF (\n) line endings in request/headers
        reader, writer = await asyncio.open_connection(client.server.host, client.server.port)
        raw_req_lf = (
            b"GET /health HTTP/1.1\n"
            b"Host: 127.0.0.1\n"
            b"User-Agent: SEC_HHP_[TV] Samsung\n"
            b"\n"
        )
        writer.write(raw_req_lf)
        await writer.drain()
        resp_data_lf = await reader.read(1024)
        writer.close()
        await writer.wait_closed()

        assert b"HTTP/1.1 200 OK" in resp_data_lf
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_explorer_ui_and_api_browse(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    cd_service = ContentDirectoryService(catalog=catalog)
    cm_service = ConnectionManagerService()
    metrics = MetricsRegistry()

    app = create_app(
        settings=mock_settings,
        content_directory_service=cd_service,
        connection_manager_service=cm_service,
        immich_client=mock_immich_client,
        metrics=metrics,
    )

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # Check UI HTML endpoint
        resp_ui = await client.get("/")
        assert resp_ui.status == 200
        assert "text/html" in resp_ui.headers.get("Content-Type", "")
        html_text = await resp_ui.text()
        assert "Immich Media Explorer" in html_text

        # Check API Browse endpoint
        resp_api = await client.get("/api/browse?id=0")
        assert resp_api.status == 200
        data = await resp_api.json()
        assert data["id"] == "0"
        assert len(data["containers"]) >= 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_samsung_soap_actions(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    cd_service = ContentDirectoryService(catalog=catalog)
    cm_service = ConnectionManagerService()
    metrics = MetricsRegistry()

    app = create_app(
        settings=mock_settings,
        content_directory_service=cd_service,
        connection_manager_service=cm_service,
        immich_client=mock_immich_client,
        metrics=metrics,
    )

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # 1. Test X_GetFeatureList
        soap_feat = """<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
          <s:Body>
            <u:X_GetFeatureList xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1" />
          </s:Body>
        </s:Envelope>"""
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": '"urn:schemas-upnp-org:service:ContentDirectory:1#X_GetFeatureList"',
        }
        resp = await client.post("/ContentDirectory/control", data=soap_feat, headers=headers)
        assert resp.status == 200
        text = await resp.text()
        assert "X_GetFeatureListResponse" in text
        assert "FeatureList" in text
        assert "EXT" in resp.headers
        assert "Server" in resp.headers

        # 2. Test Search (fallback safely with 0 results)
        soap_search = """<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
          <s:Body>
            <u:Search xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
              <ContainerID>0</ContainerID>
              <SearchCriteria></SearchCriteria>
              <Filter>*</Filter>
              <StartingIndex>0</StartingIndex>
              <RequestedCount>50</RequestedCount>
            </u:Search>
          </s:Body>
        </s:Envelope>"""
        headers_search = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": '"urn:schemas-upnp-org:service:ContentDirectory:1#Search"',
        }
        resp_search = await client.post("/ContentDirectory/control", data=soap_search, headers=headers_search)
        assert resp_search.status == 200
        text_search = await resp_search.text()
        assert "SearchResponse" in text_search
        assert "TotalMatches>0<" in text_search

        # 3. Test ConnectionManager GetProtocolInfo
        soap_proto = """<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
          <s:Body>
            <u:GetProtocolInfo xmlns:u="urn:schemas-upnp-org:service:ConnectionManager:1" />
          </s:Body>
        </s:Envelope>"""
        headers_proto = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": '"urn:schemas-upnp-org:service:ConnectionManager:1#GetProtocolInfo"',
        }
        resp_proto = await client.post("/ConnectionManager/control", data=soap_proto, headers=headers_proto)
        assert resp_proto.status == 200
        text_proto = await resp_proto.text()
        assert "GetProtocolInfoResponse" in text_proto
        assert "JPEG_LRG" in text_proto
        assert "JPEG_TN" in text_proto
        assert "video/mp4" in text_proto
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_explorer_endpoints(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    cd_service = ContentDirectoryService(catalog=catalog)
    cm_service = ConnectionManagerService()
    metrics = MetricsRegistry()

    app = create_app(
        settings=mock_settings,
        content_directory_service=cd_service,
        connection_manager_service=cm_service,
        immich_client=mock_immich_client,
        metrics=metrics,
    )

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # Explore HTML UI
        resp_ui = await client.get("/explore")
        assert resp_ui.status == 200
        text = await resp_ui.text()
        assert "Immich Media Explorer" in text
        assert "load-more-container" in text

        # API browse root (default count=500)
        resp_api = await client.get("/api/browse?id=0")
        assert resp_api.status == 200
        data = await resp_api.json()
        assert data["id"] == "0"
        assert data["total"] > 0
        assert len(data["containers"]) == data["total"]
    finally:
        await client.close()


