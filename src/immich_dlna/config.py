from __future__ import annotations

from dataclasses import dataclass
import os
import socket
from urllib.parse import urlsplit, urlunsplit
import uuid


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _parse_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def _detect_lan_ip() -> str:
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe_socket.connect(("1.1.1.1", 80))
        ip = probe_socket.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        probe_socket.close()

    try:
        hostname = socket.gethostname()
        for candidate in socket.gethostbyname_ex(hostname)[2]:
            if not candidate.startswith("127."):
                return candidate
    except OSError:
        pass
    return "127.0.0.1"


@dataclass(frozen=True, slots=True)
class Settings:
    immich_url: str
    immich_api_token: str
    immich_verify_ssl: bool = True
    http_host: str = "0.0.0.0"
    http_port: int = 8200
    base_url: str = "http://127.0.0.1:8200"
    friendly_name: str = "Immich"
    manufacturer: str = "Immich DLNA Bridge"
    manufacturer_url: str = "https://github.com/nicolasjweber/Immich-DLNA-Bridge"
    model_name: str = "Immich DLNA Bridge"
    model_description: str = "Immich DLNA Bridge for Smart TVs & Media Players"
    model_number: str = "1.0.0"
    model_url: str = "https://github.com/nicolasjweber/Immich-DLNA-Bridge"
    server_uuid: str = ""
    log_level: str = "INFO"
    ssdp_multicast_host: str = "239.255.255.250"
    ssdp_port: int = 1900
    ssdp_max_age: int = 1800
    ssdp_notify_interval: int = 300
    metadata_cache_ttl_seconds: int = 60
    metadata_cache_max_entries: int = 5000
    immich_timeout_seconds: float = 15.0
    immich_stream_read_timeout_seconds: float = 60.0
    immich_max_concurrent_requests: int = 16
    # Extended features
    enable_timeline: bool = False
    enable_people: bool = True
    show_unnamed_people: bool = False
    people_sort: str = "both"
    enable_favorites: bool = True
    enable_videos: bool = True
    enable_tags: bool = True
    tags_group_by_letter: str = "auto"
    enable_years: bool = True
    enable_year_all: bool = True
    enable_albums: bool = True
    image_quality: str = "auto"
    prefer_jpeg: bool = True
    transcode_webp_to_jpeg: bool = True
    number_people: bool = True
    number_years: bool = True
    number_assets: bool = True
    asset_title_format: str = "index_filename"

    @classmethod
    def from_env(cls) -> "Settings":
        immich_url = os.getenv("IMMICH_URL", "").strip().rstrip("/")
        if not immich_url:
            raise ValueError("IMMICH_URL environment variable is required.")

        parsed = urlsplit(immich_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"IMMICH_URL is invalid: {immich_url}")

        if not parsed.path or parsed.path == "/":
            immich_url = urlunsplit((parsed.scheme, parsed.netloc, "/api", "", ""))
        else:
            immich_url = immich_url.rstrip("/")

        immich_api_token = os.getenv("IMMICH_API_TOKEN", "").strip()
        if not immich_api_token:
            raise ValueError("IMMICH_API_TOKEN environment variable is required.")

        http_port = _parse_int(os.getenv("IMMICH_DLNA_HTTP_PORT"), 8200)
        http_host = os.getenv("IMMICH_DLNA_HTTP_HOST", "0.0.0.0").strip()

        configured_base_url = os.getenv("IMMICH_DLNA_BASE_URL", "").strip().rstrip("/")
        if configured_base_url:
            base_url = configured_base_url
        else:
            detected_ip = _detect_lan_ip()
            base_url = f"http://{detected_ip}:{http_port}"

        raw_uuid = os.getenv("IMMICH_DLNA_SERVER_UUID", "").strip()
        if raw_uuid:
            clean_uuid = raw_uuid[5:] if raw_uuid.startswith("uuid:") else raw_uuid
        else:
            namespace = uuid.NAMESPACE_DNS
            clean_uuid = str(uuid.uuid5(namespace, f"immich-dlna-v2:{base_url}"))

        image_quality = os.getenv("IMMICH_DLNA_IMAGE_QUALITY", "auto").strip().lower()
        if image_quality not in {"auto", "preview", "original"}:
            image_quality = "auto"

        people_sort = os.getenv("IMMICH_DLNA_PEOPLE_SORT", "both").strip().lower()
        if people_sort not in {"both", "photos", "name"}:
            people_sort = "both"

        asset_title_format = os.getenv("IMMICH_DLNA_ASSET_TITLE_FORMAT", "index_filename").strip().lower()
        if asset_title_format not in {"index_filename", "index_date_filename", "raw"}:
            asset_title_format = "index_filename"

        tags_group_env = os.getenv("IMMICH_DLNA_TAGS_GROUP_BY_LETTER", "auto").strip().lower()
        if tags_group_env in {"1", "true", "yes", "on"}:
            tags_group_by_letter = "true"
        elif tags_group_env in {"0", "false", "no", "off"}:
            tags_group_by_letter = "false"
        else:
            tags_group_by_letter = "auto"

        manufacturer = os.getenv("IMMICH_DLNA_MANUFACTURER", "Immich DLNA Bridge").strip() or "Immich DLNA Bridge"
        manufacturer_url = (
            os.getenv("IMMICH_DLNA_MANUFACTURER_URL", "https://github.com/nicolasjweber/Immich-DLNA-Bridge").strip()
            or "https://github.com/nicolasjweber/Immich-DLNA-Bridge"
        )
        model_name = os.getenv("IMMICH_DLNA_MODEL_NAME", "Immich DLNA Bridge").strip() or "Immich DLNA Bridge"
        model_description = (
            os.getenv("IMMICH_DLNA_MODEL_DESCRIPTION", "Immich DLNA Bridge for Smart TVs & Media Players").strip()
            or "Immich DLNA Bridge for Smart TVs & Media Players"
        )
        model_number = os.getenv("IMMICH_DLNA_MODEL_NUMBER", "1.0.0").strip() or "1.0.0"
        model_url = (
            os.getenv("IMMICH_DLNA_MODEL_URL", "https://github.com/nicolasjweber/Immich-DLNA-Bridge").strip()
            or "https://github.com/nicolasjweber/Immich-DLNA-Bridge"
        )

        return cls(
            immich_url=immich_url,
            immich_api_token=immich_api_token,
            immich_verify_ssl=_parse_bool(os.getenv("IMMICH_VERIFY_SSL"), True),
            http_host=http_host,
            http_port=http_port,
            base_url=base_url,
            friendly_name=os.getenv("IMMICH_DLNA_FRIENDLY_NAME", "Immich").strip() or "Immich",
            manufacturer=manufacturer,
            manufacturer_url=manufacturer_url,
            model_name=model_name,
            model_description=model_description,
            model_number=model_number,
            model_url=model_url,
            server_uuid=clean_uuid,
            log_level=os.getenv("IMMICH_DLNA_LOG_LEVEL", "INFO").strip().upper(),
            ssdp_multicast_host=os.getenv("IMMICH_DLNA_SSDP_MULTICAST_HOST", "239.255.255.250").strip(),
            ssdp_port=_parse_int(os.getenv("IMMICH_DLNA_SSDP_PORT"), 1900),
            ssdp_max_age=_parse_int(os.getenv("IMMICH_DLNA_SSDP_MAX_AGE"), 1800),
            ssdp_notify_interval=_parse_int(os.getenv("IMMICH_DLNA_SSDP_NOTIFY_INTERVAL"), 300),
            metadata_cache_ttl_seconds=_parse_int(os.getenv("IMMICH_DLNA_METADATA_CACHE_TTL"), 60),
            metadata_cache_max_entries=_parse_int(os.getenv("IMMICH_DLNA_METADATA_CACHE_MAX_ENTRIES"), 5000),
            immich_timeout_seconds=_parse_float(os.getenv("IMMICH_DLNA_TIMEOUT"), 15.0),
            immich_stream_read_timeout_seconds=_parse_float(
                os.getenv("IMMICH_DLNA_STREAM_READ_TIMEOUT"), 60.0
            ),
            immich_max_concurrent_requests=_parse_int(os.getenv("IMMICH_DLNA_MAX_CONCURRENT_REQUESTS"), 16),
            enable_timeline=_parse_bool(os.getenv("IMMICH_DLNA_ENABLE_TIMELINE"), False),
            enable_people=_parse_bool(os.getenv("IMMICH_DLNA_ENABLE_PEOPLE"), True),
            show_unnamed_people=_parse_bool(os.getenv("IMMICH_DLNA_SHOW_UNNAMED_PEOPLE"), False),
            people_sort=people_sort,
            enable_favorites=_parse_bool(os.getenv("IMMICH_DLNA_ENABLE_FAVORITES"), True),
            enable_videos=_parse_bool(os.getenv("IMMICH_DLNA_ENABLE_VIDEOS"), True),
            enable_tags=_parse_bool(os.getenv("IMMICH_DLNA_ENABLE_TAGS"), True),
            tags_group_by_letter=tags_group_by_letter,
            enable_years=_parse_bool(os.getenv("IMMICH_DLNA_ENABLE_YEARS"), True),
            enable_year_all=_parse_bool(os.getenv("IMMICH_DLNA_ENABLE_YEAR_ALL"), True),
            enable_albums=_parse_bool(os.getenv("IMMICH_DLNA_ENABLE_ALBUMS"), True),
            image_quality=image_quality,
            prefer_jpeg=_parse_bool(os.getenv("IMMICH_DLNA_PREFER_JPEG"), True),
            transcode_webp_to_jpeg=_parse_bool(os.getenv("IMMICH_DLNA_TRANSCODE_WEBP_TO_JPEG"), True),
            number_people=_parse_bool(os.getenv("IMMICH_DLNA_NUMBER_PEOPLE"), True),
            number_years=_parse_bool(os.getenv("IMMICH_DLNA_NUMBER_YEARS"), True),
            number_assets=_parse_bool(os.getenv("IMMICH_DLNA_NUMBER_ASSETS"), True),
            asset_title_format=asset_title_format,
        )
