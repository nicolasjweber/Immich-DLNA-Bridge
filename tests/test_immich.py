from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from immich_dlna.config import Settings
from immich_dlna.immich import ImmichAsset, ImmichClient


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        immich_url="http://mock-immich:2283/api",
        immich_api_token="test-api-token",
        immich_verify_ssl=False,
        http_host="0.0.0.0",
        http_port=8200,
        base_url="http://192.168.1.100:8200",
        friendly_name="Immich DLNA Test",
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


@pytest.mark.asyncio
async def test_list_people_filtering_and_sorting(test_settings: Settings) -> None:
    client = ImmichClient(settings=test_settings)

    mock_people_payload = {
        "people": [
            {"id": "p1", "name": "Charlie", "thumbnailPath": "/p1", "isFavorite": False, "isHidden": False},
            {"id": "p2", "name": "", "thumbnailPath": "/p2", "isFavorite": False, "isHidden": False},  # Unnamed
            {"id": "p3", "name": "Alice", "thumbnailPath": "/p3", "isFavorite": True, "isHidden": False},   # Favorite
            {"id": "p4", "name": "Bob", "thumbnailPath": "/p4", "isFavorite": False, "isHidden": False},
        ],
        "total": 4,
        "hasNextPage": False,
    }

    with patch.object(client, "_request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_people_payload

        # sort_by="name": Unnamed filtered out, favorites first, then alphabetical
        people_name = await client.list_people(show_unnamed=False, sort_by="name")
        assert len(people_name) == 3
        assert people_name[0].name == "Alice"     # Favorite
        assert people_name[1].name == "Bob"       # Alphabetical
        assert people_name[2].name == "Charlie"   # Alphabetical

        # sort_by="photos": Unnamed filtered out, favorites first, then original order from Immich
        people_photos = await client.list_people(show_unnamed=False, sort_by="photos")
        assert len(people_photos) == 3
        assert people_photos[0].name == "Alice"     # Favorite
        assert people_photos[1].name == "Charlie"   # Preserves Immich order (photos count)
        assert people_photos[2].name == "Bob"


@pytest.mark.asyncio
async def test_list_people_include_unnamed(test_settings: Settings) -> None:
    client = ImmichClient(settings=test_settings)

    mock_people_payload = {
        "people": [
            {"id": "p_unnamed_1", "name": "", "thumbnailPath": "/p_unnamed", "isFavorite": False, "isHidden": False},
            {"id": "p_named", "name": "Alice", "thumbnailPath": "/p_named", "isFavorite": False, "isHidden": False},
        ],
        "total": 2,
        "hasNextPage": False,
    }

    with patch.object(client, "_request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_people_payload

        people = await client.list_people(show_unnamed=True)
        assert len(people) == 2
        names = [p.name for p in people]
        assert "Alice" in names
        assert any("Person " in name for name in names)


@pytest.mark.asyncio
async def test_get_person_assets(test_settings: Settings) -> None:
    client = ImmichClient(settings=test_settings)

    mock_search_payload = {
        "assets": {
            "total": 1,
            "count": 1,
            "items": [
                {
                    "id": "asset-123",
                    "type": "IMAGE",
                    "originalFileName": "IMG_9999.HEIC",
                    "originalMimeType": "image/heic",
                    "fileCreatedAt": "2024-01-01T10:00:00Z",
                }
            ],
            "nextPage": None,
        }
    }

    with patch.object(client, "_request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_search_payload

        assets = await client.get_person_assets("p1")
        assert len(assets) == 1
        assert assets[0].asset_id == "asset-123"
        assert assets[0].original_mime_type == "image/heic"
        assert assets[0].is_video is False


@pytest.mark.asyncio
async def test_list_timeline_years(test_settings: Settings) -> None:
    client = ImmichClient(settings=test_settings)

    mock_buckets = [
        {"timeBucket": "2025-01-01", "count": 10},
        {"timeBucket": "2024-12-01", "count": 20},
        {"timeBucket": "2024-05-01", "count": 15},
        {"timeBucket": "2023-08-01", "count": 5},
    ]

    with patch.object(client, "_request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_buckets

        years = await client.list_timeline_years()
        assert years == ["2025", "2024", "2023"]

        months_2024 = await client.list_timeline_months_for_year("2024")
        assert months_2024 == ["2024-12-01", "2024-05-01"]


@pytest.mark.asyncio
async def test_get_timeline_year_assets(test_settings: Settings) -> None:
    client = ImmichClient(settings=test_settings)
    mock_buckets = [
        {"timeBucket": "2024-12-01", "count": 1},
        {"timeBucket": "2024-05-01", "count": 1},
    ]

    async def fake_get_bucket(bucket: str):
        if bucket == "2024-12-01":
            return [
                ImmichAsset(
                    asset_id="a12",
                    title="Dec.jpg",
                    original_mime_type="image/jpeg",
                    is_video=False,
                    created_at="2024-12-25T10:00:00Z",
                )
            ]
        return [
            ImmichAsset(
                asset_id="a5",
                title="May.jpg",
                original_mime_type="image/jpeg",
                is_video=False,
                created_at="2024-05-01T10:00:00Z",
            )
        ]

    with patch.object(client, "list_timeline_buckets", new_callable=AsyncMock) as mock_b:
        mock_b.return_value = mock_buckets
        with patch.object(client, "get_timeline_bucket_assets", side_effect=fake_get_bucket):
            assets = await client.get_timeline_year_assets("2024")
            assert len(assets) == 2
            assert assets[0].asset_id == "a12"
            assert assets[1].asset_id == "a5"


@pytest.mark.asyncio
async def test_list_videos(test_settings: Settings) -> None:
    client = ImmichClient(settings=test_settings)
    mock_search_payload = {
        "assets": {
            "total": 1,
            "count": 1,
            "items": [
                {
                    "id": "vid-123",
                    "type": "VIDEO",
                    "originalFileName": "VID_0001.MP4",
                    "originalMimeType": "video/mp4",
                    "fileCreatedAt": "2024-03-01T10:00:00Z",
                }
            ],
            "nextPage": None,
        }
    }

    with patch.object(client, "_request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_search_payload

        assets = await client.list_videos()
        assert len(assets) == 1
        assert assets[0].asset_id == "vid-123"
        assert assets[0].original_mime_type == "video/mp4"
        assert assets[0].is_video is True

