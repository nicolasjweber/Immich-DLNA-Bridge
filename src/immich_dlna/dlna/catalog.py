from __future__ import annotations

import asyncio
from datetime import datetime
import logging

from immich_dlna.config import Settings
from immich_dlna.dlna.model import (
    ALBUMS_CONTAINER,
    ALBUMS_ID,
    FAVORITES_CONTAINER,
    FAVORITES_ID,
    IMAGE_CLASS,
    PEOPLE_CONTAINER,
    PEOPLE_ID,
    PEOPLE_NAME_CONTAINER,
    PEOPLE_NAME_ID,
    PEOPLE_PHOTOS_CONTAINER,
    PEOPLE_PHOTOS_ID,
    ROOT_CONTAINER,
    ROOT_ID,
    TAGS_CONTAINER,
    TAGS_ID,
    TIMELINE_CONTAINER,
    TIMELINE_ID,
    VIDEO_CLASS,
    VIDEOS_CONTAINER,
    VIDEOS_ID,
    YEARS_CONTAINER,
    YEARS_ID,
    BrowseEntry,
    Container,
    MediaItem,
    album_object_id,
    asset_object_id,
    month_object_id,
    parse_album_id,
    parse_asset_id,
    parse_month_id,
    parse_person_id,
    parse_tag_id,
    parse_year_all_id,
    parse_year_id,
    person_object_id,
    tag_object_id,
    year_all_object_id,
    year_object_id,
)
from immich_dlna.immich import ImmichAsset, ImmichClient, ImmichError

_STANDARD_TV_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png"})


_GERMAN_MONTHS = (
    "",
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


def _format_month_title(time_bucket: str) -> str:
    # time_bucket is usually YYYY-MM-DD
    try:
        dt = datetime.strptime(time_bucket[:7], "%Y-%m")
        return f"{dt.month:02d}. {_GERMAN_MONTHS[dt.month]} {dt.year}"
    except (ValueError, IndexError):
        return time_bucket[:7]


class ContentCatalog:
    def __init__(self, settings: Settings, immich_client: ImmichClient) -> None:
        self.settings = settings
        self.immich_client = immich_client
        self.logger = logging.getLogger("immich_dlna.catalog")
        self._asset_parent_cache: dict[str, str] = {}

    def _root_containers(self) -> list[Container]:
        containers: list[Container] = []
        if self.settings.enable_timeline:
            containers.append(TIMELINE_CONTAINER)
        if self.settings.enable_years:
            containers.append(YEARS_CONTAINER)
        if self.settings.enable_albums:
            containers.append(ALBUMS_CONTAINER)
        if self.settings.enable_videos:
            containers.append(VIDEOS_CONTAINER)
        if self.settings.enable_people:
            containers.append(PEOPLE_CONTAINER)
        if self.settings.enable_favorites:
            containers.append(FAVORITES_CONTAINER)
        if self.settings.enable_tags:
            containers.append(TAGS_CONTAINER)
        return containers

    async def browse(
        self,
        object_id: str,
        browse_flag: str,
        starting_index: int,
        requested_count: int,
        sort_criteria: str = "",
    ) -> tuple[list[BrowseEntry], int]:
        try:
            if browse_flag == "BrowseDirectChildren" and object_id in {TIMELINE_ID, "1"}:
                if not self.settings.enable_timeline:
                    return [], 0
                return await self._browse_timeline_paged(starting_index, requested_count)

            if browse_flag == "BrowseMetadata":
                entry = await self._browse_metadata(object_id)
                all_entries = [entry] if entry is not None else []
            else:
                all_entries = await self._browse_children(object_id, sort_criteria=sort_criteria)
        except ImmichError as error:
            self.logger.error("Immich browse fallback object_id=%s error=%s", object_id, error)
            all_entries = self._empty_fallback_for(object_id)

        total_matches = len(all_entries)
        paged_entries = all_entries[starting_index : starting_index + requested_count]
        return paged_entries, total_matches

    async def _browse_metadata(self, object_id: str) -> BrowseEntry | None:
        if object_id in {ROOT_ID, "-1"}:
            root = ROOT_CONTAINER
            return Container(
                object_id=ROOT_ID,
                parent_id="-1",
                title=self.settings.friendly_name,
                child_count=len(self._root_containers()),
            )
        if object_id in {TIMELINE_ID, "1"}:
            if not self.settings.enable_timeline:
                return None
            return TIMELINE_CONTAINER
        if object_id == YEARS_ID:
            return YEARS_CONTAINER
        if object_id in {ALBUMS_ID, "2"}:
            if not self.settings.enable_albums:
                return None
            return ALBUMS_CONTAINER
        if object_id == VIDEOS_ID:
            return VIDEOS_CONTAINER
        if object_id == PEOPLE_ID:
            return PEOPLE_CONTAINER
        if object_id == PEOPLE_PHOTOS_ID:
            return PEOPLE_PHOTOS_CONTAINER
        if object_id == PEOPLE_NAME_ID:
            return PEOPLE_NAME_CONTAINER
        if object_id == FAVORITES_ID:
            return FAVORITES_CONTAINER
        if object_id == TAGS_ID:
            return TAGS_CONTAINER

        # Person metadata
        person_id = parse_person_id(object_id)
        if person_id is not None:
            person = await self.immich_client.get_person_info(person_id)
            if person is not None:
                avatar_url = f"{self.settings.base_url}/media/person/{person.person_id}/thumbnail"
                return Container(
                    object_id=person_object_id(person.person_id),
                    parent_id=PEOPLE_ID,
                    title=person.name,
                    album_art_uri=avatar_url,
                )
            return None

        # Album metadata
        album_id = parse_album_id(object_id)
        if album_id is not None:
            albums = await self.immich_client.list_albums()
            for album in albums:
                if album.album_id == album_id:
                    cover_url = (
                        f"{self.settings.base_url}/media/asset/{album.album_thumbnail_asset_id}/thumbnail"
                        if album.album_thumbnail_asset_id
                        else None
                    )
                    return Container(
                        object_id=album_object_id(album.album_id),
                        parent_id=ALBUMS_ID,
                        title=album.name,
                        child_count=album.asset_count,
                        album_art_uri=cover_url,
                    )
            return None

        # Tag metadata
        tag_id = parse_tag_id(object_id)
        if tag_id is not None:
            tags = await self.immich_client.list_tags()
            for tag in tags:
                if tag.tag_id == tag_id:
                    return Container(
                        object_id=tag_object_id(tag.tag_id),
                        parent_id=TAGS_ID,
                        title=tag.name,
                    )
            return None

        # Year metadata
        year = parse_year_id(object_id)
        if year is not None:
            return Container(
                object_id=year_object_id(year),
                parent_id=YEARS_ID,
                title=year,
            )

        # Whole year metadata
        year_all = parse_year_all_id(object_id)
        if year_all is not None:
            return Container(
                object_id=year_all_object_id(year_all),
                parent_id=year_object_id(year_all),
                title=f"00. Ganzes Jahr {year_all}",
            )

        # Month metadata
        month = parse_month_id(object_id)
        if month is not None:
            year_prefix = month[:4]
            return Container(
                object_id=month_object_id(month),
                parent_id=year_object_id(year_prefix),
                title=_format_month_title(month),
            )

        # Asset metadata
        asset_id = parse_asset_id(object_id)
        if asset_id is not None:
            asset = await self.immich_client.get_asset_info(asset_id)
            fallback_parent = TIMELINE_ID if self.settings.enable_timeline else (YEARS_ID if self.settings.enable_years else ROOT_ID)
            parent_id = self._asset_parent_cache.get(asset.asset_id, fallback_parent)
            return self._to_media_item(asset, parent_id)

        return None

    async def _browse_children(self, object_id: str, sort_criteria: str = "") -> list[BrowseEntry]:
        if object_id in {ROOT_ID, "-1"}:
            return self._root_containers()

        if object_id in {TIMELINE_ID, "1"}:
            return []

        # ==========================
        # People container
        # ==========================
        if object_id == PEOPLE_ID:
            if self.settings.people_sort == "both":
                return [PEOPLE_PHOTOS_CONTAINER, PEOPLE_NAME_CONTAINER]
            sort_by = "photos" if self.settings.people_sort == "photos" else "name"
            return await self._get_people_entries(parent_id=PEOPLE_ID, sort_by=sort_by)

        if object_id == PEOPLE_PHOTOS_ID:
            return await self._get_people_entries(parent_id=PEOPLE_PHOTOS_ID, sort_by="photos")

        if object_id == PEOPLE_NAME_ID:
            return await self._get_people_entries(parent_id=PEOPLE_NAME_ID, sort_by="name")

        person_id = parse_person_id(object_id)
        if person_id is not None:
            assets = await self.immich_client.get_person_assets(person_id, sort_criteria=sort_criteria)
            parent_id = person_object_id(person_id)
            total = len(assets)
            return [
                self._to_media_item(asset, parent_id, index=idx, total_count=total)
                for idx, asset in enumerate(assets, start=1)
            ]

        # ==========================
        # Videos container
        # ==========================
        if object_id == VIDEOS_ID:
            assets = await self.immich_client.list_videos()
            total = len(assets)
            return [
                self._to_media_item(asset, VIDEOS_ID, index=idx, total_count=total)
                for idx, asset in enumerate(assets, start=1)
            ]

        # ==========================
        # Favorites container
        # ==========================
        if object_id == FAVORITES_ID:
            assets = await self.immich_client.list_favorites()
            total = len(assets)
            return [
                self._to_media_item(asset, FAVORITES_ID, index=idx, total_count=total)
                for idx, asset in enumerate(assets, start=1)
            ]

        # ==========================
        # Albums container
        # ==========================
        if object_id in {ALBUMS_ID, "2"}:
            if not self.settings.enable_albums:
                return []
            albums = await self.immich_client.list_albums()
            sorted_albums = sorted(albums, key=lambda album: album.created_at, reverse=True)
            entries: list[BrowseEntry] = []
            for album in sorted_albums:
                cover_url = (
                    f"{self.settings.base_url}/media/asset/{album.album_thumbnail_asset_id}/thumbnail"
                    if album.album_thumbnail_asset_id
                    else None
                )
                entries.append(
                    Container(
                        object_id=album_object_id(album.album_id),
                        parent_id=ALBUMS_ID,
                        title=album.name,
                        child_count=album.asset_count,
                        album_art_uri=cover_url,
                    )
                )
            return entries

        album_id = parse_album_id(object_id)
        if album_id is not None:
            assets = await self.immich_client.get_album_assets(album_id, sort_criteria=sort_criteria)
            parent_id = album_object_id(album_id)
            total = len(assets)
            return [
                self._to_media_item(asset, parent_id, index=idx, total_count=total)
                for idx, asset in enumerate(assets, start=1)
            ]

        # ==========================
        # Tags container
        # ==========================
        if object_id == TAGS_ID:
            tags = await self.immich_client.list_tags()
            return [
                Container(
                    object_id=tag_object_id(tag.tag_id),
                    parent_id=TAGS_ID,
                    title=tag.name,
                )
                for tag in tags
            ]

        tag_id = parse_tag_id(object_id)
        if tag_id is not None:
            assets = await self.immich_client.get_tag_assets(tag_id)
            parent_id = tag_object_id(tag_id)
            total = len(assets)
            return [
                self._to_media_item(asset, parent_id, index=idx, total_count=total)
                for idx, asset in enumerate(assets, start=1)
            ]

        # ==========================
        # Years container
        # ==========================
        if object_id == YEARS_ID:
            years = await self.immich_client.list_timeline_years()
            total = len(years)
            return [
                Container(
                    object_id=year_object_id(year),
                    parent_id=YEARS_ID,
                    title=self._format_year_title(year, index=idx, total_count=total),
                )
                for idx, year in enumerate(years, start=1)
            ]

        year_all = parse_year_all_id(object_id)
        if year_all is not None:
            assets = await self.immich_client.get_timeline_year_assets(year_all)
            parent_id = year_all_object_id(year_all)
            total = len(assets)
            return [
                self._to_media_item(asset, parent_id, index=idx, total_count=total)
                for idx, asset in enumerate(assets, start=1)
            ]

        year = parse_year_id(object_id)
        if year is not None:
            entries: list[BrowseEntry] = []
            if self.settings.enable_year_all:
                entries.append(
                    Container(
                        object_id=year_all_object_id(year),
                        parent_id=year_object_id(year),
                        title=f"00. Ganzes Jahr {year}",
                    )
                )
            months = await self.immich_client.list_timeline_months_for_year(year)
            for month in months:
                entries.append(
                    Container(
                        object_id=month_object_id(month),
                        parent_id=year_object_id(year),
                        title=_format_month_title(month),
                    )
                )
            return entries

        month = parse_month_id(object_id)
        if month is not None:
            assets = await self.immich_client.get_timeline_bucket_assets(month)
            parent_id = month_object_id(month)
            total = len(assets)
            return [
                self._to_media_item(asset, parent_id, index=idx, total_count=total)
                for idx, asset in enumerate(assets, start=1)
            ]

        return []

    async def _get_people_entries(self, parent_id: str, sort_by: str) -> list[BrowseEntry]:
        people = await self.immich_client.list_people(
            show_unnamed=self.settings.show_unnamed_people,
            sort_by=sort_by,
        )
        should_number = self.settings.number_people and sort_by == "photos"
        width = max(2, len(str(len(people)))) if should_number else 2
        entries: list[BrowseEntry] = []
        for idx, person in enumerate(people, start=1):
            avatar_url = f"{self.settings.base_url}/media/person/{person.person_id}/thumbnail"
            title = f"{idx:0{width}d}. {person.name}" if should_number else person.name
            entries.append(
                Container(
                    object_id=person_object_id(person.person_id),
                    parent_id=parent_id,
                    title=title,
                    album_art_uri=avatar_url,
                )
            )
        return entries

    async def _browse_timeline_paged(
        self,
        starting_index: int,
        requested_count: int,
    ) -> tuple[list[BrowseEntry], int]:
        refs = await self.immich_client.list_timeline_asset_refs()
        total_matches = len(refs)
        if not refs:
            return [], 0
        paged_refs = refs[starting_index : starting_index + requested_count]
        infos = await asyncio.gather(
            *[
                self.immich_client.get_asset_info(asset_id, fallback_is_image=is_image)
                for asset_id, is_image in paged_refs
            ],
            return_exceptions=True,
        )
        entries: list[BrowseEntry] = []
        for offset, info in enumerate(infos):
            if isinstance(info, Exception):
                self.logger.warning("Skipping timeline asset due to metadata error: %s", info)
                continue
            idx = starting_index + offset + 1
            entries.append(self._to_media_item(info, TIMELINE_ID, index=idx, total_count=total_matches))
        return entries, total_matches

    def _format_year_title(
        self,
        year: str,
        index: int | None = None,
        total_count: int | None = None,
    ) -> str:
        if not self.settings.number_years or index is None:
            return year
        pad_width = 2 if (total_count or 0) < 100 else len(str(total_count))
        return f"{index:0{pad_width}d}. {year}"

    def _format_asset_title(
        self,
        asset: ImmichAsset,
        index: int | None = None,
        total_count: int | None = None,
    ) -> str:
        if not self.settings.number_assets or index is None or self.settings.asset_title_format == "raw":
            return asset.title

        width = max(3, len(str(total_count))) if total_count is not None else 3
        idx_str = f"{index:0{width}d}"

        if self.settings.asset_title_format == "index_date_filename":
            date_prefix = asset.created_at[:10] if asset.created_at else ""
            if date_prefix:
                return f"{idx_str}. {date_prefix} - {asset.title}"
            return f"{idx_str}. {asset.title}"

        # default: "index_filename"
        return f"{idx_str}. {asset.title}"

    def _to_media_item(
        self,
        asset: ImmichAsset,
        parent_id: str,
        index: int | None = None,
        total_count: int | None = None,
    ) -> MediaItem:
        self._asset_parent_cache[asset.asset_id] = parent_id

        # Determine advertised mime_type for DLNA:
        # If TV prefer_jpeg is active and image is HEIC/RAW/WebP, advertise image/jpeg
        # so Samsung TV attempts to decode and render it with DLNA JPEG profile
        mime_type = asset.original_mime_type or "application/octet-stream"
        if not asset.is_video and self.settings.prefer_jpeg:
            if mime_type.lower() not in _STANDARD_TV_IMAGE_MIMES or self.settings.image_quality == "preview":
                mime_type = "image/jpeg"

        created_date = asset.created_at[:10] if asset.created_at else None
        title = self._format_asset_title(asset, index=index, total_count=total_count)
        return MediaItem(
            object_id=asset_object_id(asset.asset_id),
            parent_id=parent_id,
            title=title,
            upnp_class=VIDEO_CLASS if asset.is_video else IMAGE_CLASS,
            resource_url=f"{self.settings.base_url}/media/asset/{asset.asset_id}",
            thumbnail_url=f"{self.settings.base_url}/media/asset/{asset.asset_id}/thumbnail",
            mime_type=mime_type,
            is_video=asset.is_video,
            date=created_date,
        )

    def _empty_fallback_for(self, object_id: str) -> list[BrowseEntry]:
        if object_id in {ROOT_ID, "-1"}:
            return self._root_containers()
        return []
