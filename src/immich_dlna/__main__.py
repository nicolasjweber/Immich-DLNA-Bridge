import os

# Set before any aiohttp imports
os.environ["AIOHTTP_NO_EXTENSIONS"] = "1"

from aiohttp import http_parser
http_parser.HttpRequestParser.lax = True

from immich_dlna.main import main

if __name__ == "__main__":
    main()
