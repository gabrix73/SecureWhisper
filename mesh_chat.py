
import os
import sys
import asyncio
import logging
import socket
from network.tor_manager import TorManager
from network.mesh import MeshNetwork
from ui.chat_window import ChatWindow
from security.memory import SecureMemory
from security.crypto import CryptoManager

class MeshChat:
    def __init__(self):
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('MeshChat')

        # Initialize components
        self.tor_manager = TorManager()
        self.mesh_network = MeshNetwork(base_port=12345, max_retry_ports=5)
        self.crypto = CryptoManager()
        self.secure_memory = SecureMemory()

    async def _verify_network(self) -> bool:
        """Verify network components are running"""
        try:
            # Try connecting to health check endpoint
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('127.0.0.1', 12345))
            sock.close()
            self.logger.info("Network connectivity verified")
            return True
        except Exception as e:
            self.logger.error(f"Network verification failed: {str(e)}")
            return False

    async def start(self):
        """Start application with robust error handling"""
        try:
            # Start Tor
            self.logger.info("Starting Tor...")
            await self.tor_manager.start()
            self.logger.info(f"Tor started with onion address: {self.tor_manager.onion_address}")

            # Initialize mesh network with retries
            max_retries = 3
            retry_delay = 2
            last_error = None

            for attempt in range(max_retries):
                try:
                    self.logger.info(f"Starting mesh network (attempt {attempt + 1}/{max_retries})...")
                    await self.mesh_network.start()

                    # Verify network is running
                    if await self._verify_network():
                        self.logger.info("Mesh network started and verified")
                        break
                    else:
                        raise Exception("Network verification failed")

                except Exception as e:
                    last_error = e
                    self.logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                    else:
                        raise Exception(f"Failed to start mesh network after {max_retries} attempts: {str(last_error)}")

            # Start GUI
            self.logger.info("Initializing GUI...")
            self.window = ChatWindow(
                self.mesh_network,
                self.tor_manager,
                self.crypto,
                self.secure_memory
            )

            self.logger.info("Application fully started")
            await self.window.run()

        except Exception as e:
            self.logger.error(f"Fatal error: {str(e)}")
            await self.cleanup()
            sys.exit(1)

    async def cleanup(self):
        """Cleanup with proper error handling"""
        self.logger.info("Starting cleanup...")

        cleanup_tasks = []

        # Stop Tor
        if hasattr(self, 'tor_manager'):
            cleanup_tasks.append(self.tor_manager.stop())

        # Stop mesh network
        if hasattr(self, 'mesh_network'):
            cleanup_tasks.append(self.mesh_network.stop())

        # Wipe sensitive data
        if hasattr(self, 'secure_memory'):
            self.secure_memory.wipe_all()

        # Wait for all cleanup tasks
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        self.logger.info("Cleanup completed")

if __name__ == "__main__":
    app = MeshChat()
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        app.logger.info("Received shutdown signal")
        asyncio.run(app.cleanup())
