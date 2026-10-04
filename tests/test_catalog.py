from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from immich_dlna.config import Settings
from immich_dlna.dlna.catalog import ContentCatalog
from immich_dlna.dlna.model import (
    ALBUMS_ID,
    FAVORITES_ID,
    PEOPLE_ID,
    PEOPLE_NAME_ID,
    PEOPLE_PHOTOS_ID,
    ROOT_ID,
    TAGS_ALL_ID,
    TAGS_ID,
    TIMELINE_ID,
    VIDEOS_ID,
    YEARS_ID,
    Container,
    MediaItem,
    tag_group_object_id,
    tag_object_id,
)
from immich_dlna.immich import ImmichAlbum, ImmichAsset, ImmichClient, ImmichPerson, ImmichTag


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        immich_url="http://mock-immich:2283/api",
        immich_api_token="dummy-token",
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


@pytest.fixture
def mock_immich_client() -> ImmichClient:
    client = AsyncMock(spec=ImmichClient)
    client.list_people.return_value = [
        ImmichPerson(
            person_id="p1",
            name="Alice",
            thumbnail_path="/thumbs/p1",
            is_favorite=True,
            is_hidden=False,
        ),
        ImmichPerson(
            person_id="p2",
            name="Bob",
            thumbnail_path="/thumbs/p2",
            is_favorite=False,
            is_hidden=False,
        ),
    ]
    client.get_person_info.return_value = ImmichPerson(
        person_id="p1",
        name="Alice",
        thumbnail_path="/thumbs/p1",
        is_favorite=True,
        is_hidden=False,
    )
    client.get_person_assets.return_value = [
        ImmichAsset(
            asset_id="a1",
            title="Alice Birthday.jpg",
            original_mime_type="image/jpeg",
            is_video=False,
            created_at="2024-05-01T12:00:00Z",
        ),
        ImmichAsset(
            asset_id="a2",
            title="Alice Video.mp4",
            original_mime_type="video/mp4",
            is_video=True,
            created_at="2024-05-01T12:30:00Z",
        ),
    ]
    client.list_favorites.return_value = [
        ImmichAsset(
            asset_id="fav1",
            title="Sunset.jpg",
            original_mime_type="image/jpeg",
            is_video=False,
            created_at="2024-06-01T20:00:00Z",
        )
    ]
    client.list_albums.return_value = [
        ImmichAlbum(
            album_id="alb1",
            name="Summer Vacation",
            created_at="2024-07-01T00:00:00Z",
            asset_count=25,
            album_thumbnail_asset_id="thumb1",
        )
    ]
    client.get_album_assets.return_value = [
        ImmichAsset(
            asset_id="alb_a1",
            title="Beach.jpg",
            original_mime_type="image/jpeg",
            is_video=False,
            created_at="2024-07-02T10:00:00Z",
        )
    ]
    client.list_tags.return_value = [
        ImmichTag(tag_id="t1", name="Landscape")
    ]
    client.get_tag_assets.return_value = [
        ImmichAsset(
            asset_id="tag_a1",
            title="Mountain.jpg",
            original_mime_type="image/jpeg",
            is_video=False,
            created_at="2024-08-01T08:00:00Z",
        )
    ]
    client.list_timeline_years.return_value = ["2024", "2023"]
    client.list_timeline_months_for_year.return_value = ["2024-08-01", "2024-07-01"]
    client.get_timeline_bucket_assets.return_value = [
        ImmichAsset(
            asset_id="bucket_a1",
            title="August Day.jpg",
            original_mime_type="image/jpeg",
            is_video=False,
            created_at="2024-08-15T15:00:00Z",
        )
    ]
    client.get_timeline_year_assets.return_value = [
        ImmichAsset(
            asset_id="year_a1",
            title="Summer Party.jpg",
            original_mime_type="image/jpeg",
            is_video=False,
            created_at="2024-08-15T15:00:00Z",
        )
    ]
    client.list_videos.return_value = [
        ImmichAsset(
            asset_id="v1",
            title="Summer Vacation.mp4",
            original_mime_type="video/mp4",
            is_video=True,
            created_at="2024-08-20T18:00:00Z",
        )
    ]
    return client


@pytest.mark.asyncio
async def test_browse_root(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    # By default, full timeline is disabled for Smart TV performance
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    entries, total = await catalog.browse(ROOT_ID, "BrowseDirectChildren", 0, 50)
    assert total == 6
    object_ids = [e.object_id for e in entries]
    assert TIMELINE_ID not in object_ids
    assert YEARS_ID in object_ids
    assert entries[0].object_id == YEARS_ID
    assert entries[0].title == "Zeitleiste"
    assert ALBUMS_ID in object_ids
    assert VIDEOS_ID in object_ids
    assert PEOPLE_ID in object_ids
    assert FAVORITES_ID in object_ids
    assert TAGS_ID in object_ids


@pytest.mark.asyncio
async def test_browse_root_with_timeline_enabled(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    from dataclasses import replace
    settings_with_timeline = replace(mock_settings, enable_timeline=True)
    catalog = ContentCatalog(settings=settings_with_timeline, immich_client=mock_immich_client)
    entries, total = await catalog.browse(ROOT_ID, "BrowseDirectChildren", 0, 50)
    assert total == 7
    object_ids = [e.object_id for e in entries]
    assert TIMELINE_ID in object_ids
    assert entries[0].object_id == TIMELINE_ID
    assert entries[0].title == "Zeitleiste (Alle Fotos)"


@pytest.mark.asyncio
async def test_browse_root_with_albums_disabled(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    from dataclasses import replace
    settings = replace(mock_settings, enable_albums=False)
    catalog = ContentCatalog(settings=settings, immich_client=mock_immich_client)
    entries, total = await catalog.browse(ROOT_ID, "BrowseDirectChildren", 0, 50)
    assert total == 5
    object_ids = [e.object_id for e in entries]
    assert ALBUMS_ID not in object_ids
    assert entries[0].object_id == YEARS_ID
    assert entries[0].title == "Zeitleiste"


@pytest.mark.asyncio
async def test_browse_videos(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    entries, total = await catalog.browse(VIDEOS_ID, "BrowseDirectChildren", 0, 50)
    assert total == 1
    assert isinstance(entries[0], MediaItem)
    assert entries[0].is_video is True
    assert "Summer Vacation.mp4" in entries[0].title



@pytest.mark.asyncio
async def test_browse_people_both(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    entries, total = await catalog.browse(PEOPLE_ID, "BrowseDirectChildren", 0, 50)
    assert total == 2
    assert isinstance(entries[0], Container)
    assert entries[0].object_id == PEOPLE_PHOTOS_ID
    assert entries[0].title == "Meiste Fotos"
    assert entries[1].object_id == PEOPLE_NAME_ID
    assert entries[1].title == "Nach Name (A-Z)"

    # Browse into Most Photos (numbered to preserve popularity on TV)
    p_entries, p_total = await catalog.browse(PEOPLE_PHOTOS_ID, "BrowseDirectChildren", 0, 50)
    assert p_total == 2
    assert p_entries[0].object_id == "person:p1"
    assert p_entries[0].title == "01. Alice"
    assert p_entries[0].album_art_uri == "http://192.168.1.100:8200/media/person/p1/thumbnail"

    # Browse into By Name (A-Z) (NOT numbered so natural alphabetical sort is clean)
    n_entries, n_total = await catalog.browse(PEOPLE_NAME_ID, "BrowseDirectChildren", 0, 50)
    assert n_total == 2
    assert n_entries[0].object_id == "person:p1"
    assert n_entries[0].title == "Alice"


@pytest.mark.asyncio
async def test_browse_people_single_sort(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    from dataclasses import replace
    settings_name = replace(mock_settings, people_sort="name")
    catalog = ContentCatalog(settings=settings_name, immich_client=mock_immich_client)
    entries, total = await catalog.browse(PEOPLE_ID, "BrowseDirectChildren", 0, 50)
    assert total == 2
    assert entries[0].object_id == "person:p1"
    assert entries[0].title == "Alice"


@pytest.mark.asyncio
async def test_browse_people_uncheck_numbering(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    from dataclasses import replace
    settings_no_num = replace(mock_settings, number_people=False)
    catalog = ContentCatalog(settings=settings_no_num, immich_client=mock_immich_client)
    p_entries, _ = await catalog.browse(PEOPLE_PHOTOS_ID, "BrowseDirectChildren", 0, 50)
    assert p_entries[0].title == "Alice"


@pytest.mark.asyncio
async def test_browse_person_assets(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    entries, total = await catalog.browse("person:p1", "BrowseDirectChildren", 0, 50)
    assert total == 2
    assert isinstance(entries[0], MediaItem)
    assert entries[0].object_id == "asset:a1"
    assert entries[0].parent_id == "person:p1"
    assert entries[0].title == "001. Alice Birthday.jpg"
    assert entries[0].is_video is False

    assert entries[1].object_id == "asset:a2"
    assert entries[1].parent_id == "person:p1"
    assert entries[1].title == "002. Alice Video.mp4"
    assert entries[1].is_video is True


@pytest.mark.asyncio
async def test_browse_assets_title_format_options(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    from dataclasses import replace

    # Format with date prefix: "001. 2024-05-01 - Alice Birthday.jpg"
    settings_date = replace(mock_settings, asset_title_format="index_date_filename")
    catalog_date = ContentCatalog(settings=settings_date, immich_client=mock_immich_client)
    entries, _ = await catalog_date.browse("person:p1", "BrowseDirectChildren", 0, 50)
    assert entries[0].title == "001. 2024-05-01 - Alice Birthday.jpg"

    # Raw format (no numbering)
    settings_raw = replace(mock_settings, number_assets=False)
    catalog_raw = ContentCatalog(settings=settings_raw, immich_client=mock_immich_client)
    entries_raw, _ = await catalog_raw.browse("person:p1", "BrowseDirectChildren", 0, 50)
    assert entries_raw[0].title == "Alice Birthday.jpg"


@pytest.mark.asyncio
async def test_browse_favorites(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    entries, total = await catalog.browse(FAVORITES_ID, "BrowseDirectChildren", 0, 50)
    assert total == 1
    assert entries[0].object_id == "asset:fav1"
    assert entries[0].title == "001. Sunset.jpg"


@pytest.mark.asyncio
async def test_browse_albums(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    entries, total = await catalog.browse(ALBUMS_ID, "BrowseDirectChildren", 0, 50)
    assert total == 1
    assert entries[0].object_id == "album:alb1"
    assert entries[0].title == "Summer Vacation"
    assert entries[0].album_art_uri == "http://192.168.1.100:8200/media/asset/thumb1/thumbnail"

    # Browse album assets
    album_assets, a_total = await catalog.browse("album:alb1", "BrowseDirectChildren", 0, 50)
    assert a_total == 1
    assert album_assets[0].object_id == "asset:alb_a1"
    assert album_assets[0].title == "001. Beach.jpg"


@pytest.mark.asyncio
async def test_browse_years_and_months(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    # Years (numbered descending: 01. 2024, 02. 2023 so TV displays newest first)
    years, y_total = await catalog.browse(YEARS_ID, "BrowseDirectChildren", 0, 50)
    assert y_total == 2
    assert years[0].object_id == "year:2024"
    assert years[0].title == "01. 2024"
    assert years[1].object_id == "year:2023"
    assert years[1].title == "02. 2023"

    # Year 2024 contains "00. Ganzes Jahr 2024" first, then the month folders
    entries, m_total = await catalog.browse("year:2024", "BrowseDirectChildren", 0, 50)
    assert m_total == 3
    assert entries[0].object_id == "year_all:2024"
    assert entries[0].title == "00. Ganzes Jahr 2024"
    assert entries[1].object_id == "month:2024-08-01"
    assert entries[1].title == "08. August 2024"
    assert entries[2].object_id == "month:2024-07-01"
    assert entries[2].title == "07. Juli 2024"

    # Browse whole year at once
    y_assets, ya_total = await catalog.browse("year_all:2024", "BrowseDirectChildren", 0, 50)
    assert ya_total == 1
    assert y_assets[0].object_id == "asset:year_a1"
    assert y_assets[0].title == "001. Summer Party.jpg"

    # Assets for August 2024
    m_assets, ma_total = await catalog.browse("month:2024-08-01", "BrowseDirectChildren", 0, 50)
    assert ma_total == 1
    assert m_assets[0].object_id == "asset:bucket_a1"
    assert m_assets[0].title == "001. August Day.jpg"


@pytest.mark.asyncio
async def test_browse_year_without_whole_year(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    from dataclasses import replace
    settings_no_all = replace(mock_settings, enable_year_all=False)
    catalog = ContentCatalog(settings=settings_no_all, immich_client=mock_immich_client)
    entries, m_total = await catalog.browse("year:2024", "BrowseDirectChildren", 0, 50)
    assert m_total == 2
    assert entries[0].object_id == "month:2024-08-01"


@pytest.mark.asyncio
async def test_browse_years_without_numbering(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    from dataclasses import replace
    settings_no_num = replace(mock_settings, number_years=False)
    catalog = ContentCatalog(settings=settings_no_num, immich_client=mock_immich_client)
    years, y_total = await catalog.browse(YEARS_ID, "BrowseDirectChildren", 0, 50)
    assert y_total == 2
    assert years[0].title == "2024"
    assert years[1].title == "2023"


@pytest.mark.asyncio
async def test_browse_tags_flat(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    entries, total = await catalog.browse(TAGS_ID, "BrowseDirectChildren", 0, 50)
    assert total == 1
    assert entries[0].object_id == "tag:t1"
    assert entries[0].title == "Landscape"
    assert entries[0].parent_id == TAGS_ID


@pytest.mark.asyncio
async def test_browse_tags_grouped_auto(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    # Generate 105 tags across multiple letters and special characters
    many_tags = [
        ImmichTag(tag_id=f"t_hash_{i}", name=f"202{i}") for i in range(5)
    ] + [
        ImmichTag(tag_id=f"t_a_{i}", name=f"Apple {i}") for i in range(25)
    ] + [
        ImmichTag(tag_id="t_umlaut_a", name="Ägypten")
    ] + [
        ImmichTag(tag_id=f"t_b_{i}", name=f"Beach {i}") for i in range(30)
    ] + [
        ImmichTag(tag_id=f"t_k_{i}", name=f"Katze {i}") for i in range(44)
    ]
    assert len(many_tags) == 105
    mock_immich_client.list_tags.return_value = many_tags

    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    entries, total = await catalog.browse(TAGS_ID, "BrowseDirectChildren", 0, 50)
    assert total == 5  # "00. Alle Schlagwörter", "01. 0-9 & Symbole", "A", "B", "K"
    assert entries[0].object_id == TAGS_ALL_ID
    assert entries[0].title == "00. Alle Schlagwörter (105)"
    assert entries[0].child_count == 105

    assert entries[1].object_id == tag_group_object_id("#")
    assert entries[1].title == "01. 0-9 & Symbole (5)"
    assert entries[1].child_count == 5

    assert entries[2].object_id == tag_group_object_id("A")
    assert entries[2].title == "A (26)"  # 25 Apple + 1 Ägypten
    assert entries[2].child_count == 26

    assert entries[3].object_id == tag_group_object_id("B")
    assert entries[3].title == "B (30)"

    assert entries[4].object_id == tag_group_object_id("K")
    assert entries[4].title == "K (44)"

    # Browse into letter group A
    a_entries, a_total = await catalog.browse(tag_group_object_id("A"), "BrowseDirectChildren", 0, 50)
    assert a_total == 26
    # Ägypten should be present and all parent_ids should point to tag_group:A
    tag_titles = [e.title for e in a_entries]
    assert "Ägypten" in tag_titles
    assert all(e.parent_id == tag_group_object_id("A") for e in a_entries)

    # Browse into "00. Alle Schlagwörter"
    all_entries, all_total = await catalog.browse(TAGS_ALL_ID, "BrowseDirectChildren", 0, 200)
    assert all_total == 105
    assert len(all_entries) == 105
    assert all(e.parent_id == TAGS_ALL_ID for e in all_entries)


@pytest.mark.asyncio
async def test_browse_tags_grouped_forced(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    from dataclasses import replace
    settings_forced = replace(mock_settings, tags_group_by_letter="true")
    # Only 2 tags, but forced grouping is active
    mock_immich_client.list_tags.return_value = [
        ImmichTag(tag_id="t1", name="Alpha"),
        ImmichTag(tag_id="t2", name="Beta"),
    ]
    catalog = ContentCatalog(settings=settings_forced, immich_client=mock_immich_client)
    entries, total = await catalog.browse(TAGS_ID, "BrowseDirectChildren", 0, 50)
    assert total == 3  # "00. Alle Schlagwörter (2)", "A (1)", "B (1)"
    assert entries[0].object_id == TAGS_ALL_ID
    assert entries[1].object_id == tag_group_object_id("A")
    assert entries[2].object_id == tag_group_object_id("B")


@pytest.mark.asyncio
async def test_browse_tag_assets(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)
    entries, total = await catalog.browse("tag:t1", "BrowseDirectChildren", 0, 50)
    assert total == 1
    assert isinstance(entries[0], MediaItem)
    assert entries[0].object_id == "asset:tag_a1"
    assert entries[0].parent_id == "tag:t1"
    assert entries[0].title == "001. Mountain.jpg"


@pytest.mark.asyncio
async def test_browse_tag_metadata(mock_settings: Settings, mock_immich_client: ImmichClient) -> None:
    mock_immich_client.list_tags.return_value = [
        ImmichTag(tag_id="t1", name="Architecture"),
        ImmichTag(tag_id="t2", name="Art"),
    ]
    catalog = ContentCatalog(settings=mock_settings, immich_client=mock_immich_client)

    # Tags container metadata
    t_meta, _ = await catalog.browse(TAGS_ID, "BrowseMetadata", 0, 50)
    assert len(t_meta) == 1
    assert t_meta[0].object_id == TAGS_ID
    assert t_meta[0].title == "Schlagwörter"

    # All tags metadata
    all_meta, _ = await catalog.browse(TAGS_ALL_ID, "BrowseMetadata", 0, 50)
    assert len(all_meta) == 1
    assert all_meta[0].object_id == TAGS_ALL_ID
    assert all_meta[0].title == "00. Alle Schlagwörter (2)"

    # Tag group metadata
    grp_meta, _ = await catalog.browse(tag_group_object_id("A"), "BrowseMetadata", 0, 50)
    assert len(grp_meta) == 1
    assert grp_meta[0].object_id == tag_group_object_id("A")
    assert grp_meta[0].title == "A (2)"

    # Single tag metadata
    single_meta, _ = await catalog.browse("tag:t1", "BrowseMetadata", 0, 50)
    assert len(single_meta) == 1
    assert single_meta[0].object_id == "tag:t1"
    assert single_meta[0].title == "Architecture"

