from __future__ import annotations

from dataclasses import dataclass

ROOT_ID = "0"
TIMELINE_ID = "timeline"
YEARS_ID = "years"
ALBUMS_ID = "albums"
VIDEOS_ID = "videos"
PEOPLE_ID = "people"
FAVORITES_ID = "favorites"
TAGS_ID = "tags"

CONTAINER_CLASS = "object.container.storageFolder"
PHOTO_ALBUM_CONTAINER_CLASS = "object.container.album.photoAlbum"
IMAGE_CLASS = "object.item.imageItem.photo"
VIDEO_CLASS = "object.item.videoItem"


@dataclass(frozen=True, slots=True)
class Container:
    object_id: str
    parent_id: str
    title: str
    upnp_class: str = CONTAINER_CLASS
    child_count: int = 0
    searchable: bool = True
    storage_used: int = -1
    album_art_uri: str | None = None


@dataclass(frozen=True, slots=True)
class MediaItem:
    object_id: str
    parent_id: str
    title: str
    upnp_class: str
    resource_url: str
    thumbnail_url: str | None
    mime_type: str
    is_video: bool
    date: str | None = None


BrowseEntry = Container | MediaItem


ROOT_CONTAINER = Container(object_id=ROOT_ID, parent_id="-1", title="Immich", child_count=6)
TIMELINE_CONTAINER = Container(object_id=TIMELINE_ID, parent_id=ROOT_ID, title="Zeitleiste (Alle Fotos)")
YEARS_CONTAINER = Container(object_id=YEARS_ID, parent_id=ROOT_ID, title="Zeitleiste")
ALBUMS_CONTAINER = Container(object_id=ALBUMS_ID, parent_id=ROOT_ID, title="Alben")
VIDEOS_CONTAINER = Container(object_id=VIDEOS_ID, parent_id=ROOT_ID, title="Videos")
PEOPLE_CONTAINER = Container(object_id=PEOPLE_ID, parent_id=ROOT_ID, title="Personen")
PEOPLE_PHOTOS_ID = "people:photos"
PEOPLE_NAME_ID = "people:name"
PEOPLE_PHOTOS_CONTAINER = Container(object_id=PEOPLE_PHOTOS_ID, parent_id=PEOPLE_ID, title="Meiste Fotos")
PEOPLE_NAME_CONTAINER = Container(object_id=PEOPLE_NAME_ID, parent_id=PEOPLE_ID, title="Nach Name (A-Z)")
FAVORITES_CONTAINER = Container(object_id=FAVORITES_ID, parent_id=ROOT_ID, title="Favoriten")
TAGS_CONTAINER = Container(object_id=TAGS_ID, parent_id=ROOT_ID, title="Schlagwörter")
TAGS_ALL_ID = "tags:all"
TAGS_ALL_CONTAINER = Container(object_id=TAGS_ALL_ID, parent_id=TAGS_ID, title="00. Alle Schlagwörter")


def album_object_id(album_id: str) -> str:
    return f"album:{album_id}"


def parse_album_id(object_id: str) -> str | None:
    if not object_id.startswith("album:"):
        return None
    album_id = object_id.split(":", 1)[1]
    return album_id or None


def person_object_id(person_id: str) -> str:
    return f"person:{person_id}"


def parse_person_id(object_id: str) -> str | None:
    if not object_id.startswith("person:"):
        return None
    person_id = object_id.split(":", 1)[1]
    return person_id or None


def tag_object_id(tag_id: str) -> str:
    return f"tag:{tag_id}"


def parse_tag_id(object_id: str) -> str | None:
    if not object_id.startswith("tag:") or object_id.startswith("tag_group:"):
        return None
    tag_id = object_id.split(":", 1)[1]
    return tag_id or None


def tag_group_object_id(group: str) -> str:
    return f"tag_group:{group}"


def parse_tag_group_id(object_id: str) -> str | None:
    if not object_id.startswith("tag_group:"):
        return None
    group = object_id.split(":", 1)[1]
    return group or None


def year_object_id(year: str) -> str:
    return f"year:{year}"


def parse_year_id(object_id: str) -> str | None:
    if not object_id.startswith("year:") or object_id.startswith("year_all:"):
        return None
    year = object_id.split(":", 1)[1]
    return year or None


def year_all_object_id(year: str) -> str:
    return f"year_all:{year}"


def parse_year_all_id(object_id: str) -> str | None:
    if not object_id.startswith("year_all:"):
        return None
    year = object_id.split(":", 1)[1]
    return year or None


def month_object_id(month: str) -> str:
    return f"month:{month}"


def parse_month_id(object_id: str) -> str | None:
    if not object_id.startswith("month:"):
        return None
    month = object_id.split(":", 1)[1]
    return month or None


def asset_object_id(asset_id: str) -> str:
    return f"asset:{asset_id}"


def parse_asset_id(object_id: str) -> str | None:
    if not object_id.startswith("asset:"):
        return None
    asset_id = object_id.split(":", 1)[1]
    return asset_id or None
