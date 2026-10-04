from __future__ import annotations

from immich_dlna.dlna.model import (
    album_object_id,
    asset_object_id,
    folder_object_id,
    month_object_id,
    parse_album_id,
    parse_asset_id,
    parse_folder_path,
    parse_month_id,
    parse_person_id,
    parse_tag_group_id,
    parse_tag_id,
    parse_year_all_id,
    parse_year_id,
    person_object_id,
    tag_group_object_id,
    tag_object_id,
    year_all_object_id,
    year_object_id,
)


def test_id_formatting_and_parsing() -> None:
    # Album
    aid = "abc-123"
    obj_id = album_object_id(aid)
    assert obj_id == "album:abc-123"
    assert parse_album_id(obj_id) == "abc-123"
    assert parse_album_id("timeline") is None

    # Person
    pid = "person-uuid-456"
    p_obj_id = person_object_id(pid)
    assert p_obj_id == "person:person-uuid-456"
    assert parse_person_id(p_obj_id) == "person-uuid-456"
    assert parse_person_id("album:abc-123") is None

    # Tag
    tid = "tag-789"
    t_obj_id = tag_object_id(tid)
    assert t_obj_id == "tag:tag-789"
    assert parse_tag_id(t_obj_id) == "tag-789"
    assert parse_tag_id("tags:all") is None
    assert parse_tag_id("tag_group:A") is None

    # Tag Group
    tg_obj_id = tag_group_object_id("A")
    assert tg_obj_id == "tag_group:A"
    assert parse_tag_group_id(tg_obj_id) == "A"
    assert parse_tag_group_id(tag_group_object_id("#")) == "#"
    assert parse_tag_group_id("tag:tag-789") is None
    assert parse_tag_group_id("tags:all") is None

    # Year
    y_obj_id = year_object_id("2025")
    assert y_obj_id == "year:2025"
    assert parse_year_id(y_obj_id) == "2025"
    assert parse_year_all_id(y_obj_id) is None

    # Year All (Whole Year)
    y_all_id = year_all_object_id("2025")
    assert y_all_id == "year_all:2025"
    assert parse_year_all_id(y_all_id) == "2025"
    assert parse_year_id(y_all_id) is None

    # Month
    m_obj_id = month_object_id("2025-08")
    assert m_obj_id == "month:2025-08"
    assert parse_month_id(m_obj_id) == "2025-08"

    # Asset
    as_id = "asset-999"
    as_obj_id = asset_object_id(as_id)
    assert as_obj_id == "asset:asset-999"
    assert parse_asset_id(as_obj_id) == "asset-999"

    # Folder
    fpath = "/usr/src/app/external/fritznas/2026-05 Urlaub & Geburtstag"
    f_obj_id = folder_object_id(fpath)
    assert f_obj_id.startswith("folder:")
    assert parse_folder_path(f_obj_id) == fpath
    assert parse_folder_path("album:abc-123") is None
    assert parse_folder_path("folders") is None
    assert parse_folder_path("folder:") is None

