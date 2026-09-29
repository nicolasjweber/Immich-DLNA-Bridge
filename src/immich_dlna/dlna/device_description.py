from __future__ import annotations

from xml.etree import ElementTree as ET

from immich_dlna.config import Settings

UPNP_DEVICE_NS = "urn:schemas-upnp-org:device-1-0"
DLNA_DEVICE_NS = "urn:schemas-dlna-org:device-1-0"
SEC_DEVICE_NS = "http://www.sec.co.kr/dlna"

ET.register_namespace("dlna", DLNA_DEVICE_NS)
ET.register_namespace("sec", SEC_DEVICE_NS)


def _add_service(
    service_list: ET.Element,
    service_type: str,
    service_id: str,
    scpd_url: str,
    control_url: str,
    event_sub_url: str,
) -> None:
    service = ET.SubElement(service_list, "service")
    ET.SubElement(service, "serviceType").text = service_type
    ET.SubElement(service, "serviceId").text = service_id
    ET.SubElement(service, "SCPDURL").text = scpd_url
    ET.SubElement(service, "controlURL").text = control_url
    ET.SubElement(service, "eventSubURL").text = event_sub_url


def build_device_description(settings: Settings) -> str:
    root = ET.Element("root", {"xmlns": UPNP_DEVICE_NS})
    spec_version = ET.SubElement(root, "specVersion")
    ET.SubElement(spec_version, "major").text = "1"
    ET.SubElement(spec_version, "minor").text = "0"

    device = ET.SubElement(root, "device")
    ET.SubElement(device, "deviceType").text = "urn:schemas-upnp-org:device:MediaServer:1"
    ET.SubElement(device, "friendlyName").text = settings.friendly_name
    ET.SubElement(device, "manufacturer").text = "Immich-DLNA"
    ET.SubElement(device, "manufacturerURL").text = "https://github.com/immich-app/immich"
    ET.SubElement(device, "modelDescription").text = "Immich DLNA Bridge for Smart TVs"
    ET.SubElement(device, "modelName").text = "Immich-DLNA"
    ET.SubElement(device, "modelNumber").text = "1.0"
    ET.SubElement(device, "serialNumber").text = settings.server_uuid
    ET.SubElement(device, "UDN").text = f"uuid:{settings.server_uuid}"
    ET.SubElement(device, f"{{{DLNA_DEVICE_NS}}}X_DLNADOC").text = "DMS-1.50"
    ET.SubElement(device, f"{{{DLNA_DEVICE_NS}}}X_DLNACAP").text = "image-upload,image-download,av-upload,av-download"
    ET.SubElement(device, f"{{{SEC_DEVICE_NS}}}ProductCap").text = "smi,smpte,dha"
    ET.SubElement(device, f"{{{SEC_DEVICE_NS}}}X_ProductCap").text = "smi,smpte,dha"
    ET.SubElement(device, "presentationURL").text = "/"

    icon_list = ET.SubElement(device, "iconList")
    for size in (48, 120, 32):
        # 1. JPEG (preferred by Samsung Tizen Smart TVs and universal UPnP players)
        icon_jpg = ET.SubElement(icon_list, "icon")
        ET.SubElement(icon_jpg, "mimetype").text = "image/jpeg"
        ET.SubElement(icon_jpg, "width").text = str(size)
        ET.SubElement(icon_jpg, "height").text = str(size)
        ET.SubElement(icon_jpg, "depth").text = "24"
        ET.SubElement(icon_jpg, "url").text = f"/icon-{size}.jpg"

        # 2. PNG (standard modern format)
        icon_png = ET.SubElement(icon_list, "icon")
        ET.SubElement(icon_png, "mimetype").text = "image/png"
        ET.SubElement(icon_png, "width").text = str(size)
        ET.SubElement(icon_png, "height").text = str(size)
        ET.SubElement(icon_png, "depth").text = "24"
        ET.SubElement(icon_png, "url").text = f"/icon-{size}.png"

        # 3. BMP (fallback recognized by embedded TV media renderers)
        icon_bmp = ET.SubElement(icon_list, "icon")
        ET.SubElement(icon_bmp, "mimetype").text = "image/bmp"
        ET.SubElement(icon_bmp, "width").text = str(size)
        ET.SubElement(icon_bmp, "height").text = str(size)
        ET.SubElement(icon_bmp, "depth").text = "24"
        ET.SubElement(icon_bmp, "url").text = f"/icon-{size}.bmp"


    service_list = ET.SubElement(device, "serviceList")
    _add_service(
        service_list,
        service_type="urn:schemas-upnp-org:service:ContentDirectory:1",
        service_id="urn:upnp-org:serviceId:ContentDirectory",
        scpd_url="/ContentDirectory/scpd.xml",
        control_url="/ContentDirectory/control",
        event_sub_url="/ContentDirectory/event",
    )
    _add_service(
        service_list,
        service_type="urn:schemas-upnp-org:service:ConnectionManager:1",
        service_id="urn:upnp-org:serviceId:ConnectionManager",
        scpd_url="/ConnectionManager/scpd.xml",
        control_url="/ConnectionManager/control",
        event_sub_url="/ConnectionManager/event",
    )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
