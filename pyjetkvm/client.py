"""JetKVM client library for JetKVM local HTTP API and WebRTC."""

import asyncio
import base64
import json
import logging
from types import TracebackType
from typing import Any, Self

from aiohttp import ClientSession, CookieJar, WSMsgType
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCDataChannel, RTCConfiguration, RTCIceCandidate
from aiortc.rtcicetransport import candidate_from_aioice
from aioice.candidate import Candidate

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class JetKVMClient:
    """Async client for communicating with a JetKVM device over local HTTP API and WebRTC."""

    def __init__(self, base_url: str) -> None:
        """Initialize the JetKVM client with a base URL."""
        self.base_url: str = base_url.rstrip("/")
        self.session: ClientSession | None = None
        self.peer_connection: RTCPeerConnection | None = None
        self.rpc_channel: RTCDataChannel | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None  # Store the WebSocket object

    async def __aenter__(self) -> Self:
        """Enter async context and initialize the HTTP session."""
        self.session = ClientSession(cookie_jar=CookieJar(unsafe=True))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit async context and close all resources."""
        if self.rpc_channel:
            await self.rpc_channel.close()
        if self.peer_connection:
            await self.peer_connection.close()
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()

    async def setup_ws(self) -> None:
        """Set up the WebSocket connection for WebRTC signaling."""
        if self.ws:
            logger.warning("WebSocket connection already established.")
            return
        logger.debug("Connecting to WebSocket signaling channel...")
        self.ws = await self.session.ws_connect(f"{self.base_url}/webrtc/signaling/client")
        logger.info("WebSocket signaling channel connected.")

        # Wait for the device-metadata message
        async for msg in self.ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data["type"] == "device-metadata":
                    logger.debug(f"Received device metadata: {data['data']}")
                    break
            elif msg.type == WSMsgType.ERROR:
                logger.error("WebSocket error occurred.")
                raise RuntimeError("WebSocket error occurred while waiting for device-metadata.")

    async def setup_webrtc(self) -> None:
        """Set up a WebRTC connection and initialize the RPC channel."""
        if not self.ws:
            raise RuntimeError("WebSocket connection must be established before setting up WebRTC.")

        logger.debug("Initializing WebRTC connection...")

        # Configure ICE servers (empty list for local-only connections)
        ice_servers = []  # No STUN/TURN servers, local-only connections
        #self.peer_connection = RTCPeerConnection(RTCConfiguration(iceServers=ice_servers))
        self.peer_connection = RTCPeerConnection()

        # Add a dummy video track to match the frontend SDP
        logger.debug("Adding dummy video track...")
        #self.peer_connection.addTransceiver("video", direction="sendrecv")
        self.peer_connection._sctpLegacySdp = False
        # I think JetKVM requries a application track which is not supported by aiortc...
        # So that is probably why it fails later on.
        #self.peer_connection.addTransceiver("application", direction="sendrecv")

        # Create the RPC data channel
        self.rpc_channel = self.peer_connection.createDataChannel("rpc")
        logger.debug("Created RPC data channel.")

        # Event when connection is established
        connected_event = asyncio.Event()

        # Handle the RPC channel
        @self.rpc_channel.on("open")
        def on_open() -> None:
            logger.info("RPC channel is open.")

        @self.rpc_channel.on("message")
        def on_message(message):
            logger.debug("RPC message %s", message)

            #if isinstance(message, str) and message.startswith("pong"):
            #    elapsed_ms = (current_stamp() - int(message[5:])) / 1000
            #    print(" RTT %.2f ms" % elapsed_ms)


        @self.rpc_channel.on("close")
        def on_close() -> None:
            logger.warning("RPC channel is closed.")


        # Monitor ICE connection state
        @self.peer_connection.on("iceconnectionstatechange")
        async def on_ice_connection_state_change():
            logger.debug(f"ICE connection state: {self.peer_connection.iceConnectionState}")
            if self.peer_connection.iceConnectionState == "connected":
                logger.info("ICE connection established.")

        # Monitor connection state
        @self.peer_connection.on("connectionstatechange")
        async def on_connection_state_change():
            logger.debug(f"Connection state: {self.peer_connection.connectionState}")
            if self.peer_connection.connectionState == "connected":
                logger.info("WebRTC connection established.")
                connected_event.set()

        # Monitor SCTP state
        @self.peer_connection.sctp.on("statechange")
        async def on_sctp_state_change():
            logger.debug(f"SCTP state: {self.peer_connection.sctp.state}")
            if self.peer_connection.sctp.state == "connected":
                logger.info("SCTP transport established.")

        # Create an SDP offer
        offer: RTCSessionDescription = await self.peer_connection.createOffer()
        #offer_sdp = offer.sdp

        await self.peer_connection.setLocalDescription(offer)
        offer_sdp = self.peer_connection.localDescription.sdp
        logger.debug(f"SDP offer: {self.peer_connection.localDescription}")

        # Inject captured offer makes the server answer, obviously, but how can we get this offer correct?
        #with open("offer.txt", "r") as f:
        #    offer_sdp = f.read().replace('\n', '\r\n')

        logger.debug(f"Created SDP offer: {offer_sdp}")

        # Wrap the SDP in a JSON structure
        sdp_json = json.dumps({
            "type": "offer",
            "sdp": offer_sdp,
        }, separators=(',', ':'))

        # Base64 encode the JSON-wrapped SDP
        offer_base64 = base64.b64encode(sdp_json.encode("utf-8")).decode("utf-8")

        # Send the SDP offer to the server
        await self.ws.send_json({"type": "offer", "data": {"sd": offer_base64}})
        logger.debug("Sent SDP offer to the server: %s.", offer_base64)

        # Handle incoming WebSocket messages
        async def _handle_signaling():
            async for msg in self.ws:
                logger.debug(f"Received WebSocket message: {msg.data}")
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if "error" in data:
                        logger.error(f"Error from server: {data['error']}")
                        raise RuntimeError("Error from server during WebRTC setup.")
                    if data["type"] == "new-ice-candidate":
                        # Receive ICE candidate
                        candidate = Candidate.from_sdp(data["data"]["candidate"])
                        rtc_candidate = candidate_from_aioice(candidate)
                        rtc_candidate.sdpMid = data["data"]["sdpMid"]
                        rtc_candidate.sdpMLineIndex = data["data"]["sdpMLineIndex"]
                        
                        logger.debug(f"Received ICE candidate: {rtc_candidate}")
                        
                        await self.peer_connection.addIceCandidate(rtc_candidate)

                    elif data["type"] == "answer":
                        # Decode the base64 SDP answer
                        answer_json = json.loads(base64.b64decode(data["data"]).decode("utf-8"))
                        answer_sdp = answer_json["sdp"]
                        answer = RTCSessionDescription(sdp=answer_sdp, type="answer")
                        await self.peer_connection.setRemoteDescription(answer)
                        logger.debug("Set remote SDP description.")
                elif msg.type == WSMsgType.CLOSE:
                    logger.warning("WebSocket connection closed.")

                    break
        self._signaling_task = asyncio.create_task(_handle_signaling())
        await connected_event.wait()
        await asyncio.sleep(4)  # Wait for the connection to stabilize

    async def send_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request over the RPC channel."""
        if not self.rpc_channel:
            raise RuntimeError("RPC channel is not initialized")

        request_id = 1  # Increment or generate unique IDs as needed
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id,
        }
        logger.debug(f"Sending JSON-RPC request: {request}")
        self.rpc_channel.send(json.dumps(request))
        await asyncio.sleep(10)  # Give some time for the message to be sent

        # Wait for the response
        #response = await self._receive_rpc_response(request_id)
        if "error" in response:
            logger.error(f"JSON-RPC error: {response['error']}")
            raise ValueError(f"RPC error: {response['error']}")
        logger.debug(f"Received JSON-RPC response: {response}")
        return response["result"]

    async def _receive_rpc_response(self, request_id: int) -> dict[str, Any]:
        """Receive and parse the JSON-RPC response."""
        while True:
            message = await self.rpc_channel.recv()
            response = json.loads(message)
            if response.get("id") == request_id:
                return response

    async def is_setup(self) -> bool:
        """Return True if the JetKVM device is already configured."""
        async with self.session.get(f"{self.base_url}/device/status") as res:
            res.raise_for_status()
            data: dict[str, Any] = await res.json()
            logger.debug(f"Device status: {data}")
            return data.get("isSetup", False)

    async def login(self, password: str) -> dict[str, Any]:
        """Authenticate with a local password and store the session cookie."""
        logger.debug("Logging in...")
        async with self.session.post(
            f"{self.base_url}/auth/login-local",
            json={"password": password},
        ) as res:
            if res.status == 401:
                logger.error("Invalid password.")
                raise ValueError("Invalid password")
            res.raise_for_status()
            logger.info("Login successful.")
            return await res.json()

    async def get_device_info(self) -> dict[str, Any]:
        """Return basic device information after login."""
        async with self.session.get(f"{self.base_url}/device") as res:
            if res.status == 401:
                logger.error("Not authenticated.")
                raise PermissionError("Not authenticated")
            res.raise_for_status()
            data = await res.json()
            logger.debug(f"Device info: {data}")
            return data

    async def get_dc_power_state(self) -> dict[str, Any]:
        """Retrieve the current DC power state using JSON-RPC."""
        logger.debug("Fetching DC power state...")
        return await self.send_rpc("getDCPowerState", {})

    async def logout(self) -> dict[str, Any]:
        """Log out of the device and clear session cookies."""
        logger.debug("Logging out...")
        async with self.session.post(f"{self.base_url}/auth/logout") as res:
            res.raise_for_status()
            await self.session.cookie_jar.clear()
            logger.info("Logout successful.")
            return await res.json()
