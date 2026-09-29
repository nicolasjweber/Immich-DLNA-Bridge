from __future__ import annotations

from xml.etree import ElementTree as ET

from immich_dlna.dlna.didl import DIDL_NS, render_entries
from immich_dlna.dlna.model import Container, MediaItem


def test_render_container_with_album_art() -> None:
    avatar_url = "http://192.168.1.50:8200/media/person/p123/thumbnail"
    container = Container(
        object_id="person:p123",
        parent_id="people",
        title="Alice",
        child_count=42,
        album_art_uri=avatar_url,
    )
    xml_str = render_entries([container])
    root = ET.fromstring(xml_str)

    containers = root.findall(f".//{{{DIDL_NS}}}container")
    assert len(containers) == 1
    c = containers[0]
    assert c.attrib["id"] == "person:p123"
    assert c.attrib["parentID"] == "people"
    assert c.attrib["childCount"] == "42"

    titles = c.findall(".//{http://purl.org/dc/elements/1.1/}title")
    assert len(titles) == 1
    assert titles[0].text == "Alice"

    # Verify albumArtURI is present
    art_elements = c.findall(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI")
    assert len(art_elements) >= 1
    assert any(elem.text == avatar_url for elem in art_elements)

    # Verify profileID="JPEG_TN"
    dlna_profile_arts = [elem for elem in art_elements if elem.attrib.get("{urn:schemas-dlna-org:metadata-1-0/}profileID") == "JPEG_TN"]
    assert len(dlna_profile_arts) == 1


def test_render_media_items() -> None:
    photo = MediaItem(
        object_id="asset:photo1",
        parent_id="person:p123",
        title="Family Photo.jpg",
        upnp_class="object.item.imageItem.photo",
        resource_url="http://192.168.1.50:8200/media/asset/photo1",
        thumbnail_url="http://192.168.1.50:8200/media/asset/photo1/thumbnail",
        mime_type="image/jpeg",
        is_video=False,
    )
    video = MediaItem(
        object_id="asset:video1",
        parent_id="person:p123",
        title="Vacation.mp4",
        upnp_class="object.item.videoItem",
        resource_url="http://192.168.1.50:8200/media/asset/video1",
        thumbnail_url="http://192.168.1.50:8200/media/asset/video1/thumbnail",
        mime_type="video/mp4",
        is_video=True,
        date="2024-05-12",
    )

    xml_str = render_entries([photo, video])
    root = ET.fromstring(xml_str)
    items = root.findall(f".//{{{DIDL_NS}}}item")
    assert len(items) == 2

    # Check photo item
    p_item = items[0]
    p_res = p_item.find(f".//{{{DIDL_NS}}}res")
    assert p_res is not None
    assert p_res.text == photo.resource_url
    assert "image/jpeg" in p_res.attrib["protocolInfo"]
    assert "JPEG_LRG" in p_res.attrib["protocolInfo"]

    # Check video item
    v_item = items[1]
    v_res = v_item.find(f".//{{{DIDL_NS}}}res")
    assert v_res is not None
    assert v_res.text == video.resource_url
    assert "video/mp4" in v_res.attrib["protocolInfo"]
    assert "DLNA.ORG_OP=01" in v_res.attrib["protocolInfo"]  # Video seeking support

    # Check dc:date element on video
    v_date = v_item.find(".//{http://purl.org/dc/elements/1.1/}date")
    assert v_date is not None
    assert v_date.text == "2024-05-12"


def test_render_container_omits_child_count_when_zero() -> None:
    container = Container(
        object_id="people",
        parent_id="0",
        title="People",
        child_count=0,
    )
    xml_str = render_entries([container])
    root = ET.fromstring(xml_str)
    c = root.find(f".//{{{DIDL_NS}}}container")
    assert c is not None
    assert "childCount" not in c.attrib
