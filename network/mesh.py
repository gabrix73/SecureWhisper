import asyncio
from kademlia.network import Server
import socket
import zstandard as zstd
from typing import List, Dict, Optional, Set
import time
import logging
from dataclasses import dataclass
from contextlib import asynccontextmanager
from aiohttp import web
import threading

@dataclass
class PeerState:
    last_seen: float
    failed_attempts: int = 0
    is_active: bool = True

class MeshNetwork:
    def __init__(self, base_port: int = 12345, max_retry_ports: int = 5):
        self.base_port = base_port
        self.max_retry_ports = max_retry_ports
        self.port: Optional[int] = None
        self.dht = Server()
        self.peers: Dict[str, PeerState] = {}
        self.message_buffer: List[Dict] = []
        self.is_running = False
        self.known_messages: Set[str] = set()
        self.retry_interval = 30
        self.peer_timeout = 300
        self.logger = logging.getLogger('MeshNetwork')
        self._http_runner = None

    async def _start_http_server(self):
        """Start minimal HTTP server for health checks"""
        if self._http_runner:
            return True

        app = web.Application()
        app.router.add_get('/', lambda _: web.Response(text="Mesh network running"))
        app.router.add_get('/health', lambda _: web.Response(text="OK"))

        self._http_runner = web.AppRunner(app)
        try:
            await self._http_runner.setup()
            site = web.TCPSite(self._http_runner, '0.0.0.0', self.base_port)
            await site.start()
            self.logger.info(f"✅ HTTP health check server started on port {self.base_port}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to start HTTP server: {str(e)}")
            if self._http_runner:
                await self._http_runner.cleanup()
                self._http_runner = None
            return False

    async def _verify_port_active(self, port: int, timeout: int = 5) -> bool:
        """Wait for port to become active with shorter timeout"""
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                # Use the DHT's bootstrap functionality to verify
                await self.dht.bootstrap([('127.0.0.1', port)])
                self.logger.info(f"✅ Port {port} is active and responding")
                return True
            except Exception as e:
                self.logger.debug(f"Port verification attempt failed: {str(e)}")
                await asyncio.sleep(0.5)
        self.logger.error(f"❌ Port {port} did not become active within {timeout} seconds")
        return False

    async def _cleanup_port(self, port: int):
        """Cleanup a port before trying to use it"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', port))
            sock.close()
        except Exception as e:
            self.logger.debug(f"Port cleanup failed: {str(e)}")
            await asyncio.sleep(1)

    async def start(self) -> None:
        """Start mesh network with robust port handling"""
        # First try to start HTTP server on base port
        self.logger.info(f"🚀 Starting HTTP health check server on port {self.base_port}")
        if not await self._start_http_server():
            self.logger.warning("⚠️ Could not start HTTP server on base port")

        # Try ports for DHT
        for port_offset in range(self.max_retry_ports):
            test_port = self.base_port + port_offset + 1  # Start from base_port + 1
            self.logger.info(f"🔍 Attempting to start DHT on port {test_port}")

            # Cleanup port before use
            await self._cleanup_port(test_port)

            try:
                await self.dht.listen(test_port)
                self.port = test_port
                self.is_running = True

                # Start maintenance tasks
                asyncio.create_task(self._peer_maintenance())
                asyncio.create_task(self._handle_message_buffer())
                asyncio.create_task(self._heartbeat())

                # Short wait before verification
                await asyncio.sleep(1)

                # Verify DHT is listening
                if await self._verify_port_active(test_port):
                    self.logger.info(f"✅ DHT started successfully on port {test_port}")
                    return
                else:
                    raise RuntimeError(f"DHT failed to bind to port {test_port}")

            except Exception as e:
                self.logger.error(f"❌ Failed to start on port {test_port}: {str(e)}")
                if self.dht:
                    try:
                        await self.dht.stop()
                    except:
                        pass
                self.is_running = False
                continue

        raise RuntimeError(f"Could not find available port in range {self.base_port+1}-{self.base_port + self.max_retry_ports}")

    async def stop(self) -> None:
        """Stop mesh network gracefully"""
        self.logger.info("Stopping mesh network")
        self.is_running = False

        # Stop HTTP server
        if self._http_runner:
            await self._http_runner.cleanup()
            self._http_runner = None

        # Stop DHT
        if self.dht:
            await self.dht.stop()

        await asyncio.sleep(1)  # Allow tasks to complete
        self.logger.info("Mesh network stopped")

    async def broadcast_message(self, message: str) -> None:
        """Broadcast message to all peers with deduplication"""
        msg_hash = hash(message)
        if msg_hash in self.known_messages:
            return

        self.known_messages.add(msg_hash)
        compressed = self._compress_message(message)

        failed_peers = []
        for peer, state in self.peers.items():
            if not state.is_active:
                continue

            try:
                async with self._peer_connection(peer) as conn:
                    await self._send_message(conn, compressed)
            except Exception as e:
                self.logger.warning(f"Failed to send to {peer}: {str(e)}")
                state.failed_attempts += 1
                if state.failed_attempts >= 3:
                    state.is_active = False
                failed_peers.append((peer, compressed))

        # Add failed deliveries to buffer
        for peer, msg in failed_peers:
            self.message_buffer.append({
                "peer": peer,
                "message": msg,
                "attempts": 0,
                "timestamp": time.time()
            })

    @asynccontextmanager
    async def _peer_connection(self, peer: str):
        """Context manager for peer connections with timeout"""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(peer, self.port),
            timeout=10
        )
        try:
            yield (reader, writer)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _send_message(self, conn, data: bytes) -> None:
        """Send message with length prefix"""
        reader, writer = conn
        # Send length prefix
        writer.write(len(data).to_bytes(4, 'big'))
        writer.write(data)
        await writer.drain()

    async def _peer_maintenance(self) -> None:
        """Maintain peer list and handle failures"""
        while self.is_running:
            current_time = time.time()
            # Remove stale peers
            self.peers = {
                peer: state
                for peer, state in self.peers.items()
                if current_time - state.last_seen < self.peer_timeout
            }

            # Reset failed attempts periodically
            for state in self.peers.values():
                if not state.is_active and state.failed_attempts > 0:
                    state.failed_attempts = max(0, state.failed_attempts - 1)
                if state.failed_attempts == 0:
                    state.is_active = True

            await asyncio.sleep(60)

    async def _handle_message_buffer(self) -> None:
        """Process buffered messages with exponential backoff"""
        while self.is_running:
            current_time = time.time()
            for msg in self.message_buffer[:]:  # Copy to allow modification
                if msg["attempts"] < 5:  # Try 5 times with increasing delays
                    try:
                        await self._send_to_peer(msg["peer"], msg["message"])
                        self.message_buffer.remove(msg)
                    except Exception:
                        msg["attempts"] += 1
                        # Exponential backoff
                        await asyncio.sleep(2 ** msg["attempts"])
                elif current_time - msg["timestamp"] > 3600:  # Remove after 1 hour
                    self.message_buffer.remove(msg)

            await asyncio.sleep(self.retry_interval)

    async def _heartbeat(self) -> None:
        """Send periodic heartbeats to peers"""
        while self.is_running:
            for peer, state in self.peers.items():
                if not state.is_active:
                    continue

                try:
                    async with self._peer_connection(peer) as conn:
                        await self._send_message(conn, b"PING")
                    state.last_seen = time.time()
                    state.failed_attempts = 0
                except Exception:
                    state.failed_attempts += 1
                    if state.failed_attempts >= 3:
                        state.is_active = False

            await asyncio.sleep(30)  # Heartbeat every 30 seconds

    def _compress_message(self, message: str) -> bytes:
        """Compress message using zstd with error handling"""
        try:
            compressor = zstd.ZstdCompressor(level=3)  # Balanced compression
            return compressor.compress(message.encode())
        except Exception as e:
            self.logger.error(f"Compression failed: {str(e)}")
            # Fallback to uncompressed
            return message.encode()

    def _decompress_message(self, data: bytes) -> str:
        """Decompress message with error handling"""
        try:
            decompressor = zstd.ZstdDecompressor()
            return decompressor.decompress(data).decode()
        except Exception as e:
            self.logger.error(f"Decompression failed: {str(e)}")
            # Try to return as-is if decompression fails
            return data.decode(errors='replace')

    async def _send_to_peer(self, peer: str, data: bytes):
        async with self._peer_connection(peer) as conn:
            await self._send_message(conn, data)
            self.logger.info(f"Message sent to {peer}") #Added logging

    async def _verify_port_available(self, port: int) -> bool:
        """Verify if a port is available"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('0.0.0.0', port))
            sock.close()
            return True
        except:
            return False

    async def _wait_for_port_active(self, port: int, timeout: int = 30) -> bool:
        """Wait for port to become active"""
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect(('127.0.0.1', port))
                sock.close()
                return True
            except:
                await asyncio.sleep(1)
        return False
