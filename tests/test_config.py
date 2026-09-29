from __future__ import annotations

import os
from unittest import mock

import pytest

from immich_dlna.config import Settings


def test_settings_from_env_defaults() -> None:
    env = {
        "IMMICH_URL": "http://192.168.1.50:2283",
        "IMMICH_API_TOKEN": "secret-token",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
        assert settings.immich_url == "http://192.168.1.50:2283/api"
        assert settings.immich_api_token == "secret-token"
        assert settings.enable_timeline is False
        assert settings.enable_albums is True
        assert settings.enable_videos is True
        assert settings.enable_year_all is True
        assert settings.number_people is True
        assert settings.number_years is True
        assert settings.number_assets is True
        assert settings.asset_title_format == "index_filename"


def test_settings_from_env_custom_sort_options() -> None:
    env = {
        "IMMICH_URL": "http://192.168.1.50:2283/api",
        "IMMICH_API_TOKEN": "secret-token",
        "IMMICH_DLNA_ENABLE_TIMELINE": "true",
        "IMMICH_DLNA_ENABLE_ALBUMS": "false",
        "IMMICH_DLNA_ENABLE_VIDEOS": "false",
        "IMMICH_DLNA_ENABLE_YEAR_ALL": "false",
        "IMMICH_DLNA_NUMBER_PEOPLE": "false",
        "IMMICH_DLNA_NUMBER_YEARS": "false",
        "IMMICH_DLNA_NUMBER_ASSETS": "0",
        "IMMICH_DLNA_ASSET_TITLE_FORMAT": "index_date_filename",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
        assert settings.enable_timeline is True
        assert settings.enable_albums is False
        assert settings.enable_videos is False
        assert settings.enable_year_all is False
        assert settings.number_people is False
        assert settings.number_years is False
        assert settings.number_assets is False
        assert settings.asset_title_format == "index_date_filename"


def test_settings_from_env_invalid_format_fallback() -> None:
    env = {
        "IMMICH_URL": "http://192.168.1.50:2283",
        "IMMICH_API_TOKEN": "secret-token",
        "IMMICH_DLNA_ASSET_TITLE_FORMAT": "invalid_unknown_mode",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
        assert settings.asset_title_format == "index_filename"
