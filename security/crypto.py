from pyspx.shake_256f import generate_keypair, sign, verify
import hashlib
from typing import Tuple, Optional
import os

class CryptoManager:
    def __init__(self):
        self.signing_key: Optional[bytes] = None
        self.verify_key: Optional[bytes] = None
        
    def generate_keys(self) -> Tuple[bytes, bytes]:
        """Generate new signing keypair"""
        self.signing_key, self.verify_key = generate_keypair()
        return self.signing_key, self.verify_key
        
    def sign_message(self, message: bytes) -> bytes:
        """Sign a message using the signing key"""
        if not self.signing_key:
            raise ValueError("No signing key available")
        return sign(message, self.signing_key)
        
    def verify_signature(self, message: bytes, signature: bytes, 
                        public_key: bytes) -> bool:
        """Verify a message signature"""
        try:
            verify(message, signature, public_key)
            return True
        except:
            return False
            
    def hash_data(self, data: bytes) -> str:
        """Create SHA-256 hash of data"""
        return hashlib.sha256(data).hexdigest()
        
    def generate_nonce(self) -> bytes:
        """Generate a random nonce"""
        return os.urandom(32)
