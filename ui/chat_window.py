import tkinter as tk
from tkinter import scrolledtext, messagebox
import asyncio
from typing import Callable, Optional
from network.mesh import MeshNetwork
from network.tor_manager import TorManager
from security.crypto import CryptoManager
from security.memory import SecureMemory

class ChatWindow:
    def __init__(
        self,
        mesh_network: MeshNetwork,
        tor_manager: TorManager,
        crypto: CryptoManager,
        secure_memory: SecureMemory
    ):
        self.mesh_network = mesh_network
        self.tor_manager = tor_manager
        self.crypto = crypto
        self.secure_memory = secure_memory
        self.root: Optional[tk.Tk] = None
        self.is_running = True

    async def run(self):
        self.root = tk.Tk()
        self.root.title("Secure Mesh Chat")
        self.root.geometry("600x800")

        # Status frame
        status_frame = tk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=5, pady=5)

        # Onion address
        onion_label = tk.Label(
            status_frame,
            text=f"Onion: {self.tor_manager.onion_address}",
            fg="green"
        )
        onion_label.pack(side=tk.LEFT)

        # Peer count
        peer_label = tk.Label(
            status_frame,
            text=f"Peers: {len(self.mesh_network.peers)}"
        )
        peer_label.pack(side=tk.RIGHT)

        # Chat area
        self.chat_area = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            height=30
        )
        self.chat_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Input area
        input_frame = tk.Frame(self.root)
        input_frame.pack(fill=tk.X, padx=5, pady=5)

        self.msg_entry = tk.Entry(input_frame)
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        send_btn = tk.Button(
            input_frame,
            text="Send",
            command=self._send_message
        )
        send_btn.pack(side=tk.RIGHT, padx=5)

        # Control buttons
        control_frame = tk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Button(
            control_frame,
            text="Clear Chat",
            command=self._clear_chat
        ).pack(side=tk.LEFT)

        tk.Button(
            control_frame,
            text="Network Status",
            command=self._show_status
        ).pack(side=tk.RIGHT)

        # Set up close handler
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start message receiver
        asyncio.create_task(self._receive_messages())

        # Start periodic UI updates
        asyncio.create_task(self._update_ui())

        while self.is_running:
            try:
                self.root.update()
                await asyncio.sleep(0.1)
            except tk.TclError:  # Window was closed
                break

    def _send_message(self):
        msg = self.msg_entry.get()
        if msg:
            asyncio.create_task(self.mesh_network.broadcast_message(msg))
            self.chat_area.insert(tk.END, f"You: {msg}\n")
            self.msg_entry.delete(0, tk.END)

    def _clear_chat(self):
        if messagebox.askyesno("Confirm", "Clear all messages?"):
            # Get current content before clearing
            content = self.chat_area.get("1.0", tk.END).encode()

            # Clear the chat area first
            self.chat_area.delete("1.0", tk.END)

            # Then securely wipe the content
            protected = self.secure_memory.protect_memory(content)
            self.secure_memory.secure_wipe(protected)

    def _show_status(self):
        status = f"""
Network Status:
--------------
Tor: {'Running' if self.tor_manager.tor_process else 'Stopped'}
Onion: {self.tor_manager.onion_address}
Active Peers: {len(self.mesh_network.peers)}
Buffered Messages: {len(self.mesh_network.message_buffer)}
"""
        messagebox.showinfo("Status", status)

    def _on_close(self):
        if messagebox.askyesno("Quit", "Are you sure you want to quit?"):
            self.is_running = False  # Stop the main loop
            if self.root:
                self.root.quit()  # Stop Tkinter
                self.root.destroy()  # Destroy the window

    async def _receive_messages(self):
        while self.is_running:
            # Process received messages
            await asyncio.sleep(0.1)

    async def _update_ui(self):
        while self.is_running:
            if not self.root:
                break

            try:
                # Update peer count
                peer_count = len(self.mesh_network.peers)
                self.root.nametowidget(".!frame.!label2").configure(
                    text=f"Peers: {peer_count}"
                )
            except tk.TclError:  # Window was closed
                break

            await asyncio.sleep(1)
