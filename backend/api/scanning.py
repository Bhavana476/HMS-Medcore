"""Upload malware scanning through a ClamAV daemon (clamd INSTREAM protocol).

Disabled when CLAMAV_HOST is empty (local development). When it is configured,
a scanner that cannot be reached rejects the upload rather than skipping the scan."""
import socket
import struct
from django.conf import settings

class ScanUnavailable(Exception): pass

def scan_bytes(content,timeout=15):
    """Return None if clean, or the signature name if infected. Raises ScanUnavailable."""
    if not settings.CLAMAV_HOST: return None
    try:
        with socket.create_connection((settings.CLAMAV_HOST,settings.CLAMAV_PORT),timeout=timeout) as sock:
            sock.sendall(b'zINSTREAM\0')
            for start in range(0,len(content),64*1024):
                chunk=content[start:start+64*1024]
                sock.sendall(struct.pack('!L',len(chunk))+chunk)
            sock.sendall(struct.pack('!L',0))
            reply=b''
            while not reply.endswith(b'\0'):
                part=sock.recv(4096)
                if not part: break
                reply+=part
    except OSError:
        raise ScanUnavailable('The virus scanner is unavailable.') from None
    text=reply.rstrip(b'\0').decode(errors='replace')
    if text.endswith('OK'): return None
    if text.endswith('FOUND'): return text.split(':',1)[-1].replace('FOUND','').strip()
    raise ScanUnavailable('The virus scanner returned an unexpected reply.')
