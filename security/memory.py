
import nacl.bindings
import ctypes
import platform

class SecureMemory:
    def __init__(self):
        self.protected_blocks = []
        
    def protect_memory(self, data: bytes) -> bytearray:
        """Protect memory block from being swapped to disk"""
        protected = bytearray(data)
        self.protected_blocks.append(protected)
        
        if platform.system() != 'Windows':
            try:
                # Lock memory to prevent swapping
                libc = ctypes.CDLL('libc.so.6')
                libc.mlock(
                    ctypes.c_void_p(protected.__array_interface__['data'][0]),
                    len(protected)
                )
            except:
                pass
                
        return protected
        
    def secure_wipe(self, data: bytearray):
        """Securely wipe memory block"""
        if data in self.protected_blocks:
            self.protected_blocks.remove(data)
            
        nacl.bindings.sodium_memzero(data)
        
    def wipe_all(self):
        """Wipe all protected memory blocks"""
        for block in self.protected_blocks[:]:
            self.secure_wipe(block)
