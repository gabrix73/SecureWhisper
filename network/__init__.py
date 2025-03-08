"""
Network package for P2P/Mesh chat application.
Contains Tor and mesh networking functionality.
"""

from .tor_manager import TorManager
from .mesh import MeshNetwork

__all__ = ['TorManager', 'MeshNetwork']
