from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
import time
from typing import Any

import aiohttp

from immich_dlna.cache import TtlCache
from immich_dlna.config import Settings
from immich_dlna.metrics import MetricsRegistry


class ImmichError(RuntimeError):
    pass


_UUID_IN_PATH = re.compile(
    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?=/|$)"
)
_RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})
_METADATA_SEARCH_PAGE_SIZE = 1000

# Formats that TVs natively support over DLNA
_STANDARD_TV_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png"})


@dataclass(frozen=True, slots=True)
class ImmichAlbum:
    album_id: str
    name: str
    created_at: str
    asset_count: int
    album_thumbnail_asset_id: str | None = None


@dataclass(frozen=True, slots=True)
class ImmichPerson:
    person_id: str
    name: str
    thumbnail_path: str
    is_favorite: bool
    is_hidden: bool


@dataclass(frozen=True, slots=True)
class ImmichTag:
    tag_id: str
    name: str


@dataclass(frozen=True, slots=True)
class ImmichAsset:
    asset_id: str
    title: str
    original_mime_type: str
    is_video: bool
    created_at: str


class ImmichClient:
    def __init__(self, settings: Settings, metrics: MetricsRegistry | None = None) -> None:
        self.settings = settings
        self.metrics = metrics
        self.logger = logging.getLogger("immich_dlna.immich")
        self._json_session: aiohttp.ClientSession | None = None
        self._retired_json_sessions: list[aiohttp.ClientSession] = []
        self._stream_session: aiohttp.ClientSession | None = None
        self._retired_stream_sessions: list[aiohttp.ClientSession] = []
        self._session_lock = asyncio.Lock()

        # Caches
        self._asset_cache = TtlCache[ImmichAsset](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )
        self._album_list_cache = TtlCache[list[ImmichAlbum]](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )
        self._album_assets_cache = TtlCache[list[ImmichAsset]](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )
        self._people_list_cache = TtlCache[list[ImmichPerson]](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )
        self._person_assets_cache = TtlCache[list[ImmichAsset]](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )
        self._favorites_cache = TtlCache[list[ImmichAsset]](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )
        self._videos_cache = TtlCache[list[ImmichAsset]](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )
        self._tags_list_cache = TtlCache[list[ImmichTag]](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )
        self._tag_assets_cache = TtlCache[list[ImmichAsset]](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )
        self._timeline_refs_cache = TtlCache[list[tuple[str, bool]]](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )
        self._timeline_buckets_cache = TtlCache[list[dict[str, Any]]](
            settings.metadata_cache_ttl_seconds,
            settings.metadata_cache_max_entries,
        )

        self._ssl: bool | None = None if settings.immich_verify_ssl else False
        self._json_timeout = aiohttp.ClientTimeout(total=self.settings.immich_timeout_seconds)
        self._stream_timeout = aiohttp.ClientTimeout(
            total=None,
            connect=self.settings.immich_timeout_seconds,
            sock_connect=self.settings.immich_timeout_seconds,
            sock_read=self.settings.immich_stream_read_timeout_seconds,
        )

    async def start(self) -> None:
        await self._get_json_session()
        await self._get_stream_session()
        self.logger.info(
            "Immich client started url=%s verify_ssl=%s max_concurrent_requests=%s stream_read_timeout=%s",
            self.settings.immich_url,
            self.settings.immich_verify_ssl,
            self.settings.immich_max_concurrent_requests,
            self.settings.immich_stream_read_timeout_seconds,
        )

    async def close(self) -> None:
        async with self._session_lock:
            sessions = [session for session in (self._json_session, self._stream_session) if session is not None]
            sessions.extend(self._retired_json_sessions)
            sessions.extend(self._retired_stream_sessions)
            self._json_session = None
            self._retired_json_sessions = []
            self._stream_session = None
            self._retired_stream_sessions = []

        for session in sessions:
            await session.close()

    def _create_connector(self) -> aiohttp.TCPConnector:
        return aiohttp.TCPConnector(
            limit=self.settings.immich_max_concurrent_requests,
            limit_per_host=self.settings.immich_max_concurrent_requests,
            enable_cleanup_closed=True,
        )

    def _create_session(self, timeout: aiohttp.ClientTimeout) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(timeout=timeout, connector=self._create_connector())

    async def _get_json_session(self) -> aiohttp.ClientSession:
        session = self._json_session
        if session is not None and not session.closed:
            return session
        async with self._session_lock:
            session = self._json_session
            if session is None or session.closed:
                session = self._create_session(self._json_timeout)
                self._json_session = session
            return session

    async def _get_stream_session(self) -> aiohttp.ClientSession:
        session = self._stream_session
        if session is not None and not session.closed:
            return session
        async with self._session_lock:
            session = self._stream_session
            if session is None or session.closed:
                session = self._create_session(self._stream_timeout)
                self._stream_session = session
            return session

    async def _reset_json_session(self, reason: str) -> None:
        new_session = self._create_session(self._json_timeout)
        async with self._session_lock:
            previous_session = self._json_session
            self._json_session = new_session
            if previous_session is not None:
                self._retired_json_sessions.append(previous_session)
        await self.cleanup_retired_sessions()
        self.logger.warning("Reset Immich JSON session reason=%s", reason)

    async def _reset_stream_session(self, reason: str) -> None:
        new_session = self._create_session(self._stream_timeout)
        async with self._session_lock:
            previous_session = self._stream_session
            self._stream_session = new_session
            if previous_session is not None:
                self._retired_stream_sessions.append(previous_session)
        await self.cleanup_retired_sessions()
        self.logger.warning("Reset Immich stream session reason=%s", reason)

    @staticmethod
    def _split_closeable_retired_sessions(
        sessions: list[aiohttp.ClientSession],
    ) -> tuple[list[aiohttp.ClientSession], list[aiohttp.ClientSession]]:
        sessions_to_close: list[aiohttp.ClientSession] = []
        still_retired: list[aiohttp.ClientSession] = []
        for session in sessions:
            connector = session.connector
            if session.closed or connector is None or not getattr(connector, "_acquired", ()):
                sessions_to_close.append(session)
            else:
                still_retired.append(session)
        return sessions_to_close, still_retired

    async def cleanup_retired_sessions(self) -> None:
        async with self._session_lock:
            json_to_close, self._retired_json_sessions = self._split_closeable_retired_sessions(
                self._retired_json_sessions
            )
            stream_to_close, self._retired_stream_sessions = self._split_closeable_retired_sessions(
                self._retired_stream_sessions
            )

        for session in [*json_to_close, *stream_to_close]:
            await session.close()

    @staticmethod
    def _is_reconnect_worthy_error(error: BaseException) -> bool:
        return isinstance(
            error,
            (
                asyncio.TimeoutError,
                aiohttp.ClientConnectionError,
                aiohttp.ServerDisconnectedError,
                aiohttp.ServerTimeoutError,
            ),
        )

    @staticmethod
    def _is_retryable_status(status: int) -> bool:
        return status in _RETRYABLE_STATUS_CODES

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.settings.immich_api_token,
            "Accept": "application/json",
        }

    @staticmethod
    def _metric_target(path: str) -> str:
        normalized = _UUID_IN_PATH.sub("/{id}", path)
        return normalized or "/"

    def _observe_outgoing(self, method: str, path: str, status: str, duration_seconds: float) -> None:
        if self.metrics is None:
            return
        self.metrics.observe_outgoing(
            method=method,
            target=self._metric_target(path),
            status=status,
            duration_seconds=duration_seconds,
        )

    def _record_immich_error(self) -> None:
        if self.metrics is None:
            return
        self.metrics.increment_error("immich")

    def cache_hit_ratio(self) -> float:
        caches = (
            self._asset_cache,
            self._album_list_cache,
            self._album_assets_cache,
            self._people_list_cache,
            self._person_assets_cache,
            self._favorites_cache,
            self._videos_cache,
            self._tags_list_cache,
            self._tag_assets_cache,
            self._timeline_refs_cache,
            self._timeline_buckets_cache,
        )
        hits = sum(cache.hits for cache in caches)
        misses = sum(cache.misses for cache in caches)
        total = hits + misses
        if total == 0:
            return 0.0
        return hits / total

    async def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        retries: int = 1,
    ) -> Any:
        url = f"{self.settings.immich_url}{path}"
        attempt = 0
        while True:
            session = await self._get_json_session()
            started_at = time.perf_counter()
            try:
                async with session.request(
                    method,
                    url,
                    headers=self._headers(),
                    params=params,
                    json=json_body,
                    ssl=self._ssl,
                ) as response:
                    if response.status >= 400:
                        details = (await response.text())[:250]
                        self._observe_outgoing(method, path, str(response.status), time.perf_counter() - started_at)
                        self._record_immich_error()
                        if self._is_retryable_status(response.status) and attempt < retries:
                            attempt += 1
                            await self._reset_json_session(f"http_{response.status}:{path}")
                            await asyncio.sleep(0.2 * attempt)
                            continue
                        raise ImmichError(f"Immich {method} {path} failed: {response.status} {details}")
                    content_type = response.headers.get("Content-Type", "")
                    if "json" not in content_type.lower():
                        details = (await response.text())[:250]
                        self._observe_outgoing(method, path, str(response.status), time.perf_counter() - started_at)
                        self._record_immich_error()
                        raise ImmichError(
                            f"Immich {method} {path} returned non-JSON content type ({content_type}). "
                            f"Check IMMICH_URL points to Immich API (usually with /api). Response: {details}"
                        )
                    payload = await response.json()
                    self._observe_outgoing(method, path, str(response.status), time.perf_counter() - started_at)
                    return payload
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                self._observe_outgoing(method, path, "error", time.perf_counter() - started_at)
                self._record_immich_error()
                if attempt >= retries:
                    raise ImmichError(str(error)) from error
                attempt += 1
                if self._is_reconnect_worthy_error(error):
                    await self._reset_json_session(f"{type(error).__name__}:{path}")
                await asyncio.sleep(0.2 * attempt)
            except ImmichError as error:
                if attempt >= retries:
                    raise ImmichError(str(error)) from error
                attempt += 1
                await asyncio.sleep(0.2 * attempt)
            finally:
                await self.cleanup_retired_sessions()

    async def _request_stream(
        self,
        path: str,
        headers: dict[str, str],
        *,
        params: dict[str, str] | None = None,
        retries: int = 1,
    ) -> aiohttp.ClientResponse:
        url = f"{self.settings.immich_url}{path}"
        attempt = 0
        while True:
            session = await self._get_stream_session()
            started_at = time.perf_counter()
            try:
                response = await session.get(
                    url,
                    headers=headers,
                    params=params,
                    ssl=self._ssl,
                    timeout=self._stream_timeout,
                )
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                self._observe_outgoing("GET", path, "error", time.perf_counter() - started_at)
                self._record_immich_error()
                if attempt >= retries:
                    raise ImmichError(f"Immich stream request failed: {error}") from error
                attempt += 1
                if self._is_reconnect_worthy_error(error):
                    await self._reset_stream_session(f"{type(error).__name__}:{path}")
                await asyncio.sleep(0.2 * attempt)
                continue
            finally:
                await self.cleanup_retired_sessions()

            self._observe_outgoing("GET", path, str(response.status), time.perf_counter() - started_at)
            if response.status < 400:
                return response

            details = (await response.text())[:250]
            response.release()
            self._record_immich_error()
            if self._is_retryable_status(response.status) and attempt < retries:
                attempt += 1
                await self._reset_stream_session(f"http_{response.status}:{path}")
                await asyncio.sleep(0.2 * attempt)
                continue
            raise ImmichError(f"Immich stream {path} failed: {response.status} {details}")

    # ==========================
    # Albums
    # ==========================
    async def list_albums(self) -> list[ImmichAlbum]:
        cached = self._album_list_cache.get("albums")
        if cached is not None:
            return cached

        owned_payload = await self._request_json("/albums", params={"isOwned": "true"})
        shared_payload = await self._request_json("/albums", params={"isShared": "true"})

        albums_by_id: dict[str, ImmichAlbum] = {}
        for payload in (owned_payload, shared_payload):
            if not isinstance(payload, list):
                continue
            for album in payload:
                thumb_id = album.get("albumThumbnailAssetId")
                parsed_album = ImmichAlbum(
                    album_id=str(album.get("id", "")),
                    name=str(album.get("albumName", "Album")),
                    created_at=str(album.get("createdAt", "")),
                    asset_count=int(album.get("assetCount", 0)),
                    album_thumbnail_asset_id=str(thumb_id) if thumb_id else None,
                )
                if parsed_album.album_id:
                    albums_by_id[parsed_album.album_id] = parsed_album

        albums = list(albums_by_id.values())
        self._album_list_cache.set("albums", albums)
        return albums

    async def get_album_assets(self, album_id: str, sort_criteria: str = "") -> list[ImmichAsset]:
        cache_key = f"album:{album_id}"
        cached = self._album_assets_cache.get(cache_key)
        if cached is not None and not sort_criteria:
            return cached

        payload = await self._request_json(f"/albums/{album_id}")
        if int(payload.get("assetCount") or 0) == 0:
            if not sort_criteria:
                self._album_assets_cache.set(cache_key, [])
            return []

        album_order = str(payload.get("order", "")).strip().lower()
        search_request: dict[str, Any] = {
            "albumIds": [album_id],
            "size": _METADATA_SEARCH_PAGE_SIZE,
        }
        if not sort_criteria and album_order in {"asc", "desc"}:
            search_request["order"] = album_order

        assets = await self._search_metadata_all(search_request)
        for asset in assets:
            self._asset_cache.set(f"asset:{asset.asset_id}", asset)
        if not sort_criteria:
            self._album_assets_cache.set(cache_key, assets)
        return assets

    # ==========================
    # People / Persons
    # ==========================
    async def list_people(
        self,
        with_hidden: bool = False,
        show_unnamed: bool = False,
        sort_by: str = "photos",
    ) -> list[ImmichPerson]:
        cache_key = f"people:{with_hidden}:{show_unnamed}:{sort_by}"
        cached = self._people_list_cache.get(cache_key)
        if cached is not None:
            return cached

        people: list[ImmichPerson] = []
        page = 1
        page_size = 500

        while True:
            params = {
                "page": str(page),
                "size": str(page_size),
                "withHidden": "true" if with_hidden else "false",
            }
            payload = await self._request_json("/people", params=params)
            people_payload = payload.get("people", []) if isinstance(payload, dict) else payload
            if not isinstance(people_payload, list) or not people_payload:
                break

            for p in people_payload:
                person_id = str(p.get("id", ""))
                name = str(p.get("name", "")).strip()
                if not show_unnamed and not name:
                    continue
                display_name = name or f"Person {person_id[:8]}"
                thumbnail_path = str(p.get("thumbnailPath", ""))
                is_favorite = bool(p.get("isFavorite", False))
                is_hidden = bool(p.get("isHidden", False))

                people.append(
                    ImmichPerson(
                        person_id=person_id,
                        name=display_name,
                        thumbnail_path=thumbnail_path,
                        is_favorite=is_favorite,
                        is_hidden=is_hidden,
                    )
                )

            has_next = payload.get("hasNextPage", False) if isinstance(payload, dict) else False
            if not has_next or len(people_payload) < page_size:
                break
            page += 1

        if sort_by == "name":
            # Favorites first, then alphabetical by name
            sorted_people = sorted(people, key=lambda person: (not person.is_favorite, person.name.lower()))
        else:
            # Immich standard: Favorites first, then by most photos (natural order from GET /people)
            sorted_people = sorted(people, key=lambda person: not person.is_favorite)

        self._people_list_cache.set(cache_key, sorted_people)
        return sorted_people

    async def get_person_info(self, person_id: str) -> ImmichPerson | None:
        try:
            payload = await self._request_json(f"/people/{person_id}")
            name = str(payload.get("name", "")).strip() or f"Person {person_id[:8]}"
            return ImmichPerson(
                person_id=str(payload.get("id", person_id)),
                name=name,
                thumbnail_path=str(payload.get("thumbnailPath", "")),
                is_favorite=bool(payload.get("isFavorite", False)),
                is_hidden=bool(payload.get("isHidden", False)),
            )
        except ImmichError:
            return None

    async def get_person_assets(self, person_id: str, sort_criteria: str = "") -> list[ImmichAsset]:
        cache_key = f"person:{person_id}"
        cached = self._person_assets_cache.get(cache_key)
        if cached is not None and not sort_criteria:
            return cached

        search_request: dict[str, Any] = {
            "personIds": [person_id],
            "size": _METADATA_SEARCH_PAGE_SIZE,
            "order": "desc",
        }
        assets = await self._search_metadata_all(search_request)
        for asset in assets:
            self._asset_cache.set(f"asset:{asset.asset_id}", asset)
        if not sort_criteria:
            self._person_assets_cache.set(cache_key, assets)
        return assets

    async def open_person_thumbnail_stream(self, person_id: str) -> aiohttp.ClientResponse:
        headers = {
            "x-api-key": self.settings.immich_api_token,
            "Accept": "image/jpeg,image/*;q=0.9,*/*;q=0.1",
        }
        return await self._request_stream(f"/people/{person_id}/thumbnail", headers)

    # ==========================
    # Favorites
    # ==========================
    async def list_favorites(self) -> list[ImmichAsset]:
        cached = self._favorites_cache.get("favorites")
        if cached is not None:
            return cached

        search_request: dict[str, Any] = {
            "isFavorite": True,
            "size": _METADATA_SEARCH_PAGE_SIZE,
            "order": "desc",
        }
        assets = await self._search_metadata_all(search_request)
        for asset in assets:
            self._asset_cache.set(f"asset:{asset.asset_id}", asset)
        self._favorites_cache.set("favorites", assets)
        return assets

    # ==========================
    # Videos
    # ==========================
    async def list_videos(self) -> list[ImmichAsset]:
        cached = self._videos_cache.get("videos")
        if cached is not None:
            return cached

        search_request: dict[str, Any] = {
            "type": "VIDEO",
            "size": _METADATA_SEARCH_PAGE_SIZE,
            "order": "desc",
        }
        try:
            assets = await self._search_metadata_all(search_request)
        except ImmichError as err:
            self.logger.info("Search with type=VIDEO failed (%s), retrying with filter object", err)
            search_request = {
                "filter": {"type": {"eq": "VIDEO"}},
                "size": _METADATA_SEARCH_PAGE_SIZE,
                "order": "desc",
            }
            assets = await self._search_metadata_all(search_request)

        # Ensure only actual video items are included
        assets = [a for a in assets if a.is_video]

        for asset in assets:
            self._asset_cache.set(f"asset:{asset.asset_id}", asset)
        self._videos_cache.set("videos", assets)
        return assets


    # ==========================
    # Tags
    # ==========================
    async def list_tags(self) -> list[ImmichTag]:
        cached = self._tags_list_cache.get("tags")
        if cached is not None:
            return cached

        try:
            payload = await self._request_json("/tags")
            tags: list[ImmichTag] = []
            if isinstance(payload, list):
                for t in payload:
                    tag_id = str(t.get("id", ""))
                    name = str(t.get("name", "Tag")).strip()
                    if tag_id and name:
                        tags.append(ImmichTag(tag_id=tag_id, name=name))
            tags.sort(key=lambda item: item.name.lower())
            self._tags_list_cache.set("tags", tags)
            return tags
        except ImmichError as exc:
            self.logger.warning("Could not fetch tags: %s", exc)
            return []

    async def get_tag_assets(self, tag_id: str) -> list[ImmichAsset]:
        cache_key = f"tag:{tag_id}"
        cached = self._tag_assets_cache.get(cache_key)
        if cached is not None:
            return cached

        search_request: dict[str, Any] = {
            "tagIds": [tag_id],
            "size": _METADATA_SEARCH_PAGE_SIZE,
            "order": "desc",
        }
        assets = await self._search_metadata_all(search_request)
        for asset in assets:
            self._asset_cache.set(f"asset:{asset.asset_id}", asset)
        self._tag_assets_cache.set(cache_key, assets)
        return assets

    # ==========================
    # Timeline & Timeline by Year
    # ==========================
    async def list_timeline_buckets(self) -> list[dict[str, Any]]:
        cached = self._timeline_buckets_cache.get("buckets")
        if cached is not None:
            return cached

        bucket_payload = await self._request_json(
            "/timeline/buckets",
            params={
                "order": "desc",
                "visibility": "timeline",
                "isTrashed": "false",
                "withPartners": "true",
            },
        )
        if not isinstance(bucket_payload, list):
            bucket_payload = []
        self._timeline_buckets_cache.set("buckets", bucket_payload)
        return bucket_payload

    async def list_timeline_years(self) -> list[str]:
        buckets = await self.list_timeline_buckets()
        years_set: set[str] = set()
        for bucket in buckets:
            time_bucket = str(bucket.get("timeBucket", ""))
            if time_bucket and len(time_bucket) >= 4:
                year = time_bucket[:4]
                if year.isdigit():
                    years_set.add(year)
        return sorted(years_set, reverse=True)

    async def list_timeline_months_for_year(self, year: str) -> list[str]:
        buckets = await self.list_timeline_buckets()
        months: list[str] = []
        for bucket in buckets:
            time_bucket = str(bucket.get("timeBucket", ""))
            if time_bucket.startswith(f"{year}-"):
                months.append(time_bucket)
        return months

    async def get_timeline_year_assets(self, year: str) -> list[ImmichAsset]:
        cache_key = f"year_assets:{year}"
        cached = self._album_assets_cache.get(cache_key)
        if cached is not None:
            return cached

        months = await self.list_timeline_months_for_year(year)
        if not months:
            return []

        month_assets_list = await asyncio.gather(
            *[self.get_timeline_bucket_assets(month) for month in months],
            return_exceptions=True,
        )

        year_assets: list[ImmichAsset] = []
        for assets in month_assets_list:
            if isinstance(assets, Exception):
                self.logger.warning("Error fetching month assets for year %s: %s", year, assets)
                continue
            year_assets.extend(assets)

        self._album_assets_cache.set(cache_key, year_assets)
        return year_assets

    async def get_timeline_bucket_assets(self, time_bucket: str) -> list[ImmichAsset]:
        cache_key = f"bucket:{time_bucket}"
        cached = self._album_assets_cache.get(cache_key)
        if cached is not None:
            return cached

        assets_payload = await self._request_json(
            "/timeline/bucket",
            params={
                "timeBucket": time_bucket,
                "order": "desc",
                "visibility": "timeline",
                "isTrashed": "false",
                "withPartners": "true",
            },
        )
        ids = assets_payload.get("id", [])
        image_flags = assets_payload.get("isImage", [])
        assets: list[ImmichAsset] = []

        infos = await asyncio.gather(
            *[
                self.get_asset_info(
                    str(asset_id),
                    fallback_is_image=bool(image_flags[idx]) if idx < len(image_flags) else True,
                )
                for idx, asset_id in enumerate(ids)
            ],
            return_exceptions=True,
        )
        for info in infos:
            if isinstance(info, Exception):
                continue
            assets.append(info)

        self._album_assets_cache.set(cache_key, assets)
        return assets

    async def list_timeline_asset_refs(self) -> list[tuple[str, bool]]:
        cached = self._timeline_refs_cache.get("timeline")
        if cached is not None:
            return cached

        bucket_payload = await self.list_timeline_buckets()
        refs: list[tuple[str, bool]] = []
        for bucket in bucket_payload:
            time_bucket = str(bucket.get("timeBucket", ""))
            if not time_bucket:
                continue
            assets_payload = await self._request_json(
                "/timeline/bucket",
                params={
                    "timeBucket": time_bucket,
                    "order": "desc",
                    "visibility": "timeline",
                    "isTrashed": "false",
                    "withPartners": "true",
                },
            )
            ids = assets_payload.get("id", [])
            image_flags = assets_payload.get("isImage", [])
            for index, asset_id in enumerate(ids):
                is_image = True
                if index < len(image_flags):
                    is_image = bool(image_flags[index])
                refs.append((str(asset_id), is_image))

        self._timeline_refs_cache.set("timeline", refs)
        return refs

    # ==========================
    # Generic Search & Assets
    # ==========================
    async def _search_metadata_all(self, search_request: dict[str, Any]) -> list[ImmichAsset]:
        assets: list[ImmichAsset] = []
        next_page: int | None = None
        while True:
            page_request = dict(search_request)
            if next_page is not None:
                page_request["page"] = next_page

            search_payload = await self._request_json(
                "/search/metadata",
                method="POST",
                json_body=page_request,
            )
            search_assets_payload = search_payload.get("assets", {})
            items_payload = search_assets_payload.get("items", [])
            page_assets = [self._parse_asset(asset_payload) for asset_payload in items_payload]
            if not page_assets:
                break
            assets.extend(page_assets)

            next_page_token = search_assets_payload.get("nextPage")
            if next_page_token is None:
                break

            try:
                parsed_next_page = int(next_page_token)
            except (TypeError, ValueError):
                break

            if parsed_next_page <= 0 or parsed_next_page == next_page:
                break
            next_page = parsed_next_page

        return assets

    async def get_asset_info(self, asset_id: str, fallback_is_image: bool | None = None) -> ImmichAsset:
        cache_key = f"asset:{asset_id}"
        cached = self._asset_cache.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._request_json(f"/assets/{asset_id}")
        asset = self._parse_asset(payload, fallback_is_image=fallback_is_image)
        self._asset_cache.set(cache_key, asset)
        return asset

    async def open_asset_stream(
        self,
        asset_id: str,
        range_header: str | None,
        prefer_jpeg: bool = True,
    ) -> tuple[ImmichAsset, aiohttp.ClientResponse]:
        asset = await self.get_asset_info(asset_id)
        if asset.is_video:
            path = f"/assets/{asset_id}/video/playback"
            params = None
        else:
            # If TV prefer_jpeg is enabled and original mime is not standard JPEG/PNG
            # (e.g. HEIC, RAW, WEBP, AVIF), use Immich's high-res preview thumbnail endpoint
            if (
                prefer_jpeg
                and asset.original_mime_type.lower() not in _STANDARD_TV_IMAGE_MIMES
            ) or self.settings.image_quality == "preview":
                path = f"/assets/{asset_id}/thumbnail"
                params = {"size": "preview"}
            else:
                path = f"/assets/{asset_id}/original"
                params = None

        headers = {"x-api-key": self.settings.immich_api_token}
        if range_header:
            headers["Range"] = range_header

        try:
            response = await self._request_stream(path, headers, params=params)
        except ImmichError:
            # If preview failed, fallback to original
            if not asset.is_video and path != f"/assets/{asset_id}/original":
                response = await self._request_stream(f"/assets/{asset_id}/original", headers)
            else:
                raise

        return asset, response

    async def open_asset_thumbnail_stream(self, asset_id: str) -> aiohttp.ClientResponse:
        headers = {
            "x-api-key": self.settings.immich_api_token,
            "Accept": "image/jpeg,image/*;q=0.9,*/*;q=0.1",
        }
        return await self._request_stream(
            f"/assets/{asset_id}/thumbnail",
            headers,
            params={"size": "preview"},
        )

    @staticmethod
    def _parse_asset(payload: dict[str, Any], fallback_is_image: bool | None = None) -> ImmichAsset:
        asset_id = str(payload.get("id", ""))
        asset_type = str(payload.get("type", "IMAGE")).upper()
        if asset_type in {"VIDEO", "AUDIO"}:
            is_video = True
        elif asset_type in {"IMAGE", "OTHER"}:
            is_video = False
        elif fallback_is_image is not None:
            is_video = not fallback_is_image
        else:
            is_video = False

        mime_type = str(payload.get("originalMimeType", "")).strip()
        if not mime_type:
            mime_type = "video/mp4" if is_video else "image/jpeg"

        title = str(payload.get("originalFileName", "")).strip() or asset_id
        created_at = str(payload.get("fileCreatedAt") or payload.get("createdAt") or "")
        return ImmichAsset(
            asset_id=asset_id,
            title=title,
            original_mime_type=mime_type,
            is_video=is_video,
            created_at=created_at,
        )
