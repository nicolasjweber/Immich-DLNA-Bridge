# Immich DLNA Bridge

A lightweight, high-performance **DLNA/UPnP Media Server bridge** running in Docker that connects to your [Immich](https://immich.app/) photo library and exposes your photos and videos to Smart TVs (Samsung Tizen, LG webOS, Sony Bravia, Android TV, etc.) and DLNA/UPnP clients on your home network.

Unlike baseline DLNA servers that only offer a flat timeline and albums, this bridge features full support for **People / Persons browsing** (complete with face crop thumbnails on your TV screen), **Favorites**, **Tags**, **Dedicated Videos**, and **Timeline by Year & Month**, combined with automatic image format compatibility (serving high-resolution JPEG previews and on-the-fly transcoding for iPhone HEIC, camera RAW, and WebP files so your TV displays every photo without errors).

---

## Key Features

- **People / Persons Selection**:
  - Automatically queries Immich face recognition data.
  - Displays each recognized person with their name and face crop avatar on your TV.
  - Opens a person folder to reveal all photos and videos featuring that person (newest first).
  - **Dual Sorting Options**: Provides both **Most Photos** (Immich app standard) and **By Name (A-Z)** categories, configurable via `IMMICH_DLNA_PEOPLE_SORT` (`both`, `photos`, or `name`).
  - Configurable: favorites appear first, with an option to filter out unnamed/unassigned faces (`IMMICH_DLNA_SHOW_UNNAMED_PEOPLE=false`).
- **Timeline by Year & Month**:
  - Large photo libraries (10,000+ pictures) can lag TV remotes when browsed as a single flat list.
  - Browse neatly categorized folders: `Zeitleiste` -> `01. 2026` -> `01. Januar 2026` -> photos.
  - Includes an optional `00. Ganzes Jahr <year>` subfolder inside each year to view the entire year at once.
- **Albums**:
  - Full album browsing (both owned and shared partner albums).
  - Album cover art is automatically displayed on the TV container tile.
  - Preserves the custom album sort order configured in Immich.
- **Dedicated Videos Folder**:
  - Direct access to all video clips stored in Immich in a single, convenient folder.
- **Favorites & Tags**:
  - Instant access to starred / favorite media and photos organized by Immich tags.
  - **Tag Letter Grouping**: For large tag collections, tags are automatically organized into letter folders (`A`, `B`, ..., `Z`), plus a `00. Alle Schlagwörter` folder. This completely avoids item truncation on Smart TVs with strict limits (such as Samsung Tizen's 200-item folder cap).
- **Smart TV & Universal Client Optimizations**:
  - **Zero-Padded Chronological Ordering**: Many Smart TVs (such as Samsung Tizen) force alphabetical (A-Z) sorting on all folder contents. The bridge intelligently prefixes entries with zero-padded indices (`01. 2026`, `001. IMG_0001.jpg`, `01. Alice`), preserving the natural chronological and popularity order.
  - **Container Cover Art**: Emits UPnP `<upnp:albumArtURI dlna:profileID="JPEG_TN">` and `<upnp:icon>` on folders (face crops for people, covers for albums).
  - **Seamless Image Compatibility**: Smart TVs often lack native decoders for iPhone HEIC/HEIF, camera RAW (.cr2, .arw, .nef, .dng), and WebP files. The bridge automatically serves Immich's high-resolution JPEG previews and includes on-the-fly transcoding with Pillow so no photo ever displays as a broken icon.
  - **Video Seeking & Streaming**: Supports HTTP byte-range requests (`206 Partial Content`) and marks streams with `DLNA.ORG_OP=01` so fast-forward, rewind, and seeking work smoothly on TV media players.
- **Integrated Web Explorer**:
  - Built-in web UI available directly at `http://<your-server-ip>:8200/` to test and browse your library from any web browser without needing a DLNA player.
- **Lightweight & Fast**:
  - Pure Python asyncio architecture with in-memory TTL caching to keep TV browsing instant and reduce load on your Immich server.
  - Integrated Prometheus metrics at `/metrics`.

---

## DLNA Container Structure

```text
Immich (Root: 0)
├── Zeitleiste                  -> Fast year/month navigation (Recommended for TVs)
│   ├── 01. 2026
│   │   ├── 00. Ganzes Jahr 2026 -> All media from 2026 at once
│   │   └── 01. Januar 2026      -> Media from Jan 2026
│   ├── 02. 2025
│   │   ├── 00. Ganzes Jahr 2025
│   │   ├── 12. Dezember 2025
│   │   └── 08. August 2025
├── Alben                       -> All owned and shared albums (with album covers)
│   ├── Summer Vacation 2025
│   └── Family Reunion
├── Videos                      -> All video clips in Immich
├── Personen                    -> Face recognition (with face avatars)
│   ├── Meiste Fotos            -> Popularity ranking ("01. Alice", "02. Bob")
│   │   ├── 01. Alice           -> All photos & videos of Alice
│   │   └── 02. Bob             -> All photos & videos of Bob
│   └── Nach Name (A-Z)         -> Alphabetical sorting ("Alice", "Bob")
│       ├── Alice
│       └── Bob
├── Favoriten                   -> All starred / favorite assets
├── Schlagwörter                -> Browse by Immich tags (letter folders for large collections)
│   ├── 00. Alle Schlagwörter (443)
│   ├── 01. 0-9 & Symbole (4)
│   ├── A (24)
│   ├── B (30)
│   └── ...
└── Zeitleiste (Alle Fotos)     -> Optional full flat media stream (disabled by default for TV speed)
```

---

## Quickstart (Docker Compose)

### 1. Clone or Download Repository

```bash
git clone https://github.com/<your-username>/immich-dlna.git
cd immich-dlna
```

### 2. Configure Environment

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` with your Immich instance details:
```ini
# Address of your Immich instance (LAN IP or domain)
IMMICH_URL=http://192.168.1.50:2283

# Your Immich API Token (Created in Immich Web UI -> Account Settings -> API Keys)
IMMICH_API_TOKEN=your_secret_api_key_here

# Friendly name displayed on your TV
IMMICH_DLNA_FRIENDLY_NAME=Immich
```

### 3. Launch the Container

```bash
docker compose up -d
```

Check the logs to verify startup:
```bash
docker compose logs -f
```

---

## Deployment & Network Notes

### 1. Host Networking is Required
UPnP/DLNA relies on SSDP multicast discovery packets over UDP port 1900 to `239.255.255.250`. 
Docker bridge networks isolate multicast traffic. Therefore, **`network_mode: host`** is configured in `docker-compose.yml` so TVs on your local network can discover the media server.

### 2. Running on Proxmox VE (LXC or VM)
If running Docker on Proxmox VE:
- **LXC Container**:
  - Ensure the LXC network interface (e.g. `eth0`) is attached to your LAN bridge (`vmbr0`).
  - Verify that the Proxmox firewall does not block UDP port `1900` or TCP port `8200`.
  - Multicast snooping on the Proxmox bridge (`vmbr0`) must allow SSDP traffic (default setting).
- **Virtual Machine (VM)**:
  - Standard bridged networking (`vmbr0`) works immediately with `network_mode: host`.

### 3. Running on a NAS (Synology, TrueNAS, Unraid)
- Configure the container to use the host network (`--net=host` or `network_mode: host`).
- Ensure no other service on the NAS is already bound to TCP port `8200` (can be customized via `IMMICH_DLNA_HTTP_PORT`).

---

## How to Browse on Your Smart TV

1. Ensure your Smart TV is connected to the same home LAN (Wi-Fi or Ethernet) as your Docker host.
2. Open the **Sources**, **Input**, or **Media Player** menu on your TV:
   - **Samsung Smart TV**: Press the **Home** or **Source** button and select **Immich** under *Connected Devices*.
   - **LG webOS TV**: Open the **Home Dashboard** or **Device Connector** and choose **Immich**.
   - **Sony Bravia / Android TV / Google TV**: Open the built-in **Media Player** app (or VLC / Nova Video Player) and browse local network servers.
3. Select any category:
   - **Zeitleiste**: Fast year and month navigation.
   - **Alben**: View albums with their original cover photos.
   - **Videos**: Browse all video clips in Immich.
   - **Personen**: Browse face avatars of family and friends, then select a person to see all their pictures.
   - **Favoriten**: Showcase your favorite photos and videos.
   - **Schlagwörter**: Browse photos organized by tags.
4. Select any photo or video to start playback or a full-screen slideshow!

---

## Built-in Web Explorer

The bridge includes an integrated web explorer for testing and browsing your library directly in a browser:
- Open `http://<your-server-ip>:8200/` (or `/explore`) in your web browser.
- You can navigate folders, preview high-resolution images, inspect thumbnails, and stream videos directly.
- Health check endpoint: `http://<your-server-ip>:8200/health`
- Prometheus metrics: `http://<your-server-ip>:8200/metrics`

---

## Configuration Reference

| Environment Variable | Default | Description |
|---|---|---|
| `IMMICH_URL` | *Required* | Base URL to Immich (e.g. `http://192.168.1.50:2283`). `/api` is automatically appended if missing. |
| `IMMICH_API_TOKEN` | *Required* | API key generated in Immich Account Settings. |
| `IMMICH_VERIFY_SSL` | `true` | Verify TLS certificates for HTTPS connections (`false` for self-signed certificates). |
| `IMMICH_DLNA_FRIENDLY_NAME` | `Immich` | Name of the media server displayed in DLNA client menus. |
| `IMMICH_DLNA_HTTP_PORT` | `8200` | HTTP port used for DLNA control, media streaming, and web explorer. |
| `IMMICH_DLNA_BASE_URL` | *Auto-detected* | Public URL advertised to DLNA clients (e.g. `http://192.168.1.60:8200`). |
| `IMMICH_DLNA_SERVER_UUID` | *Auto-generated* | Persistent UUID for the DLNA device. |
| `IMMICH_DLNA_ENABLE_TIMELINE` | `false` | Enables full flat "Zeitleiste (Alle Fotos)" container (disabled by default for TV performance). |
| `IMMICH_DLNA_ENABLE_YEARS` | `true` | Enables hierarchical "Zeitleiste" container (organized by Year & Month). |
| `IMMICH_DLNA_ENABLE_YEAR_ALL` | `true` | Enables the "00. Ganzes Jahr <year>" container inside each year. |
| `IMMICH_DLNA_ENABLE_ALBUMS` | `true` | Enables albums browsing. |
| `IMMICH_DLNA_ENABLE_VIDEOS` | `true` | Enables dedicated "Videos" container. |
| `IMMICH_DLNA_ENABLE_PEOPLE` | `true` | Enables the "Personen" container (face recognition). |
| `IMMICH_DLNA_SHOW_UNNAMED_PEOPLE` | `false` | When `false`, hides unnamed face detections to keep TV browsing clean. |
| `IMMICH_DLNA_PEOPLE_SORT` | `both` | People sorting mode: `both` (subfolders for Most Photos & By Name), `photos`, or `name`. |
| `IMMICH_DLNA_NUMBER_PEOPLE` | `true` | Prefixes people in *Meiste Fotos* with popularity rank (`01. Alice`). |
| `IMMICH_DLNA_NUMBER_YEARS` | `true` | Prefixes years in *Zeitleiste* with descending index so newest year is top on TV (`01. 2026`). |
| `IMMICH_DLNA_NUMBER_ASSETS` | `true` | Prefixes photos & videos with zero-padded index (`001. IMG_001.jpg`). |
| `IMMICH_DLNA_ASSET_TITLE_FORMAT` | `index_filename` | Title format for assets: `index_filename`, `index_date_filename`, or `raw`. |
| `IMMICH_DLNA_ENABLE_FAVORITES` | `true` | Enables the "Favoriten" container. |
| `IMMICH_DLNA_ENABLE_TAGS` | `true` | Enables the "Schlagwörter" container. |
| `IMMICH_DLNA_TAGS_GROUP_BY_LETTER` | `auto` | Group tags into letter subfolders (`auto` when >100 tags, `true`, or `false`). Prevents TV 200-item cutoff. |
| `IMMICH_DLNA_IMAGE_QUALITY` | `auto` | `auto` (serves JPEG previews for HEIC/RAW/WebP, original for JPEG/PNG), `preview`, or `original`. |
| `IMMICH_DLNA_PREFER_JPEG` | `true` | Advertises `image/jpeg` with DLNA profile `JPEG_LRG` for TV compatibility. |
| `IMMICH_DLNA_TRANSCODE_WEBP_TO_JPEG` | `true` | Automatically converts WebP to JPEG on the fly if Immich outputs WebP. |
| `IMMICH_DLNA_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `IMMICH_DLNA_METADATA_CACHE_TTL` | `60` | TTL in seconds for cached Immich metadata. |

---

## Troubleshooting

### TV does not detect the DLNA server
- Make sure `network_mode: host` is enabled in `docker-compose.yml`.
- Verify UDP port `1900` is not blocked by a local firewall on the host (`ufw`, `iptables`, or Proxmox firewall).
- If your host has multiple network interfaces, set `IMMICH_DLNA_BASE_URL=http://<YOUR_LAN_IP>:8200` in `.env`.
- Check if the server is responding by running `curl http://localhost:8200/device.xml` on the host.

### Photos do not display on TV
- Many Smart TVs cannot decode HEIC (iPhone) or RAW files over DLNA. Ensure `IMMICH_DLNA_IMAGE_QUALITY=auto` and `IMMICH_DLNA_PREFER_JPEG=true` (both defaults). This delivers high-res JPEG previews generated by Immich.

### Videos fail to seek or fast-forward
- Seeking relies on HTTP byte-range requests. This bridge forwards the HTTP `Range` header and responds with `206 Partial Content`, enabling video seeking across TV media players.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
