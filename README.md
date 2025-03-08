# SecureWhisper a secure P2P chat application
A secure P2P chat application with advanced mesh networking capabilities, designed for resilient and private communication.
## Key Features
- Mesh Networking Protocol
- Tor Integration
- Distributed Hash Table (DHT)
- Secure Communication Channels
- Health Monitoring Services

## Project Structure
```
.
├── network/
│   ├── __init__.py
│   ├── mesh.py
│   └── tor_manager.py
├── security/
│   ├── __init__.py
│   ├── crypto.py
│   └── memory.py
├── ui/
│   ├── __init__.py
│   └── chat_window.py
├── mesh_chat.py
├── test_health.py
└── libraries.html
```

## Required Dependencies
```python
# Install using pip
aiohttp
kademlia
pynacl
pysocks
pyspx
zstandard
```

## Running the Application
1. Install dependencies:
```bash
pip install aiohttp kademlia pynacl pysocks pyspx zstandard
```

2. Start the application:
```bash
python mesh_chat.py
```

3. Test health check:
```bash
python test_health.py
