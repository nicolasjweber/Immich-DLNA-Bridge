from __future__ import annotations

from xml.etree import ElementTree as ET

from immich_dlna.dlna.model import BrowseEntry, Container, MediaItem

DIDL_NS = "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
DC_NS = "http://purl.org/dc/elements/1.1/"
UPNP_NS = "urn:schemas-upnp-org:metadata-1-0/upnp/"
DLNA_NS = "urn:schemas-dlna-org:metadata-1-0/"
SEC_NS = "http://www.sec.co.kr/"

ET.register_namespace("", DIDL_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("upnp", UPNP_NS)
ET.register_namespace("dlna", DLNA_NS)
ET.register_namespace("sec", SEC_NS)


def _protocol_info(item: MediaItem) -> str:
    if item.is_video:
        return "http-get:*:video/mp4:DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"
    if item.mime_type.lower() in {"image/jpeg", "image/jpg"}:
        return "http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000"
    if item.mime_type.lower() == "image/png":
        return "http-get:*:image/png:DLNA.ORG_PN=PNG_LRG;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000"
    return f"http-get:*:{item.mime_type}:DLNA.ORG_OP=01;DLNA.ORG_CI=0"


def render_entries(entries: list[BrowseEntry]) -> str:
    root = ET.Element(f"{{{DIDL_NS}}}DIDL-Lite")
    for entry in entries:
        if isinstance(entry, Container):
            attrs = {
                "id": entry.object_id,
                "parentID": entry.parent_id,
                "restricted": "1",
                "searchable": "1" if entry.searchable else "0",
            }
            if entry.child_count > 0:
                attrs["childCount"] = str(entry.child_count)

            container_element = ET.SubElement(
                root,
                f"{{{DIDL_NS}}}container",
                attrs,
            )
            title = ET.SubElement(container_element, f"{{{DC_NS}}}title")
            title.text = entry.title
            upnp_class = ET.SubElement(container_element, f"{{{UPNP_NS}}}class")
            upnp_class.text = entry.upnp_class
            if entry.storage_used >= 0:
                storage_used = ET.SubElement(container_element, f"{{{UPNP_NS}}}storageUsed")
                storage_used.text = str(entry.storage_used)

            if entry.album_art_uri:
                album_art_tn = ET.SubElement(
                    container_element,
                    f"{{{UPNP_NS}}}albumArtURI",
                    {f"{{{DLNA_NS}}}profileID": "JPEG_TN"},
                )
                album_art_tn.text = entry.album_art_uri
                album_art = ET.SubElement(container_element, f"{{{UPNP_NS}}}albumArtURI")
                album_art.text = entry.album_art_uri
                icon = ET.SubElement(container_element, f"{{{UPNP_NS}}}icon")
                icon.text = entry.album_art_uri
            continue

        item = ET.SubElement(
            root,
            f"{{{DIDL_NS}}}item",
            {
                "id": entry.object_id,
                "parentID": entry.parent_id,
                "restricted": "1",
            },
        )
        title = ET.SubElement(item, f"{{{DC_NS}}}title")
        title.text = entry.title
        upnp_class = ET.SubElement(item, f"{{{UPNP_NS}}}class")
        upnp_class.text = entry.upnp_class

        if entry.date:
            date_element = ET.SubElement(item, f"{{{DC_NS}}}date")
            date_element.text = entry.date

        if entry.thumbnail_url:
            album_art_tn = ET.SubElement(
                item,
                f"{{{UPNP_NS}}}albumArtURI",
                {f"{{{DLNA_NS}}}profileID": "JPEG_TN"},
            )
            album_art_tn.text = entry.thumbnail_url
            album_art = ET.SubElement(item, f"{{{UPNP_NS}}}albumArtURI")
            album_art.text = entry.thumbnail_url

        resource = ET.SubElement(item, f"{{{DIDL_NS}}}res", {"protocolInfo": _protocol_info(entry)})
        resource.text = entry.resource_url

    return ET.tostring(root, encoding="unicode")
