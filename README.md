# Python JetKVM client

Unofficial Python client for interacting with local JetKVM http API.

## Basic example

To run the basic example use the following command:

```
$ python -m examples.basic_usage http://192.168.x.y/
🔐 Enter your JetKVM password: 
✅ Login successful.
📟 Device Info:
  authMode: password
  deviceId: <something>
🔌 Setting up WebSocket connection...
🔌 Setting up WebRTC connection...
🌐 WebRTC connection established.
💬 Send JSON RPC messages
Video State: {'ready': True, 'width': 1920, 'height': 1080, 'fps': 0}
USB State: configured
Storage Space: {'bytesUsed': 106979328, 'bytesFree': 14055178240}
Active Extension: dc-power
DC Power State: {'isOn': True, 'voltage': 12.24, 'current': 0.13477, 'power': 1.65039}
```

Currently connecting to a device which is not on the same network (routed) seems not to work.