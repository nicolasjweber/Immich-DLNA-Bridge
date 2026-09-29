from __future__ import annotations

import logging

from immich_dlna.dlna.soap import render_soap_fault, render_soap_response

SERVICE_NAMESPACE = "urn:schemas-upnp-org:service:ConnectionManager:1"


SOURCE_PROTOCOL_INFO = (
    "http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,"
    "http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_MED;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,"
    "http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,"
    "http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_SM;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,"
    "http-get:*:image/jpeg:*,"
    "http-get:*:image/png:DLNA.ORG_PN=PNG_LRG;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,"
    "http-get:*:image/png:DLNA.ORG_PN=PNG_TN;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,"
    "http-get:*:image/png:*,"
    "http-get:*:video/mp4:DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000,"
    "http-get:*:video/mp4:*,"
    "http-get:*:video/quicktime:*,"
    "http-get:*:*.*:*"
)


class ConnectionManagerService:
    def __init__(self) -> None:
        self.logger = logging.getLogger("immich_dlna.connection_manager")

    def handle(self, action_name: str) -> tuple[int, str]:
        if action_name == "GetProtocolInfo":
            payload = render_soap_response(
                SERVICE_NAMESPACE,
                action_name,
                {
                    "Source": SOURCE_PROTOCOL_INFO,
                    "Sink": "",
                },
            )
            return 200, payload

        if action_name == "GetCurrentConnectionIDs":
            payload = render_soap_response(SERVICE_NAMESPACE, action_name, {"ConnectionIDs": "0"})
            return 200, payload

        if action_name == "GetCurrentConnectionInfo":
            payload = render_soap_response(
                SERVICE_NAMESPACE,
                action_name,
                {
                    "RcsID": "-1",
                    "AVTransportID": "-1",
                    "ProtocolInfo": "",
                    "PeerConnectionManager": "",
                    "PeerConnectionID": "-1",
                    "Direction": "Output",
                    "Status": "OK",
                },
            )
            return 200, payload

        self.logger.warning("Unsupported ConnectionManager action requested: %s", action_name)
        return 500, render_soap_fault(401, "Invalid Action")
