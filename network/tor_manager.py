import os
import subprocess
import asyncio
import socket
import socks
from typing import Optional
import shutil
import platform
import sys
import stat

class TorManager:
    def __init__(self):
        self.tor_process: Optional[subprocess.Popen] = None
        self.onion_address: Optional[str] = None
        self.socks_port = 9052
        self.control_port = 9053
        self.base_dir = self._get_base_dir()

    def _get_base_dir(self) -> str:
        """Get the portable base directory for Tor files"""
        if getattr(sys, 'frozen', False):
            # If running as compiled executable
            base_path = os.path.dirname(sys.executable)
        else:
            # If running from source
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Use a hidden directory in the user's home
        return os.path.join(os.path.expanduser("~"), ".tormesh")

    def _secure_dir_permissions(self, path: str):
        """Set secure permissions on directory"""
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)  # 700

    def _get_tor_path(self) -> str:
        """Get platform-specific Tor binary path with fallbacks"""
        if platform.system() == 'Windows':
            tor_names = ['tor.exe']
        else:
            tor_names = ['tor']

        # Search in system paths first
        search_paths = [
            "/usr/bin",
            "/usr/local/bin",
            "/opt/homebrew/bin",  # For MacOS
            os.path.join(self.base_dir, "bin")
        ]

        # Add PATH directories
        if os.environ.get('PATH'):
            search_paths.extend(os.environ['PATH'].split(os.pathsep))

        for path in search_paths:
            for name in tor_names:
                tor_path = os.path.join(path, name)
                if os.path.exists(tor_path) and os.access(tor_path, os.X_OK):
                    return tor_path

        raise FileNotFoundError(
            "Tor binary not found. Please ensure Tor is installed."
        )

    async def start(self):
        """Start Tor with robust error handling and retries"""
        # Create base directory with secure permissions
        os.makedirs(self.base_dir, exist_ok=True)
        self._secure_dir_permissions(self.base_dir)

        # Create necessary subdirectories
        data_dir = os.path.join(self.base_dir, "data")
        hidden_service_dir = os.path.join(self.base_dir, "hidden_service")

        for directory in [data_dir, hidden_service_dir]:
            os.makedirs(directory, exist_ok=True)
            self._secure_dir_permissions(directory)

        # Create torrc configuration
        torrc_path = os.path.join(self.base_dir, "torrc")
        with open(torrc_path, "w") as f:
            f.write(f"""
SocksPort 127.0.0.1:{self.socks_port}
ControlPort 127.0.0.1:{self.control_port}
DataDirectory {data_dir}
HiddenServiceDir {hidden_service_dir}
HiddenServicePort 12345 127.0.0.1:12345
# Improve anonymity
UseEntryGuards 1
NumEntryGuards 4
# Improve resilience
CircuitBuildTimeout 60
LearnCircuitBuildTimeout 1
MaxCircuitDirtiness 600
NewCircuitPeriod 300
""")
        self._secure_dir_permissions(os.path.dirname(torrc_path))

        # Start Tor process with retries
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                tor_path = self._get_tor_path()
                print(f"Starting Tor from: {tor_path}")

                self.tor_process = subprocess.Popen(
                    [tor_path, "-f", torrc_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                # Wait for Tor to start and verify it's running
                if await self._wait_for_tor():
                    print(f"Tor started successfully on attempt {attempt + 1}")
                    return

            except Exception as e:
                print(f"Tor start attempt {attempt + 1} failed: {str(e)}")
                if self.tor_process:
                    self.tor_process.terminate()
                    await asyncio.sleep(1)

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise Exception(f"Failed to start Tor after {max_retries} attempts")

    async def _wait_for_tor(self) -> bool:
        """Wait for Tor to start with improved verification"""
        hostname_file = os.path.join(
            self.base_dir, "hidden_service", "hostname"
        )

        for _ in range(30):  # Wait up to 30 seconds
            # Check if process is still running
            if self.tor_process and self.tor_process.poll() is not None:
                if self.tor_process.stderr:
                    stderr = self.tor_process.stderr.read().decode()
                    raise Exception(f"Tor process died: {stderr}")
                raise Exception("Tor process died unexpectedly")

            # Check for hostname file
            if os.path.exists(hostname_file):
                try:
                    with open(hostname_file, "r") as f:
                        self.onion_address = f.read().strip()

                    # Verify SOCKS port is listening
                    sock = socket.socket()
                    try:
                        sock.connect(("127.0.0.1", self.socks_port))
                        sock.close()
                        return True
                    except:
                        pass
                except:
                    pass

            await asyncio.sleep(1)

        return False

    async def stop(self):
        """Stop Tor with graceful shutdown"""
        if self.tor_process:
            try:
                self.tor_process.terminate()
                try:
                    await asyncio.wait_for(
                        asyncio.create_task(self.tor_process.wait()),
                        timeout=5
                    )
                except asyncio.TimeoutError:
                    self.tor_process.kill()

                # Clear sensitive data
                if self.onion_address:
                    self.onion_address = None

                # Clean up temporary files securely
                if os.path.exists(self.base_dir):
                    try:
                        # Securely delete sensitive files
                        for root, dirs, files in os.walk(self.base_dir):
                            for f in files:
                                path = os.path.join(root, f)
                                with open(path, 'wb') as fd:
                                    fd.write(os.urandom(os.path.getsize(path)))
                        # Remove directory tree
                        shutil.rmtree(self.base_dir)
                    except:
                        pass
            except:
                pass  # Ensure cleanup doesn't raise errors
