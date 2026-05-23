"""
TCP proxy: listens on IPv4 (0.0.0.0:5435) and forwards to an IPv6 host.
Allows Docker containers (no IPv6) to reach Supabase's IPv6-only DB.

Usage:
    python3 scripts/ipv6_proxy.py
    # Or as a background daemon:
    nohup python3 scripts/ipv6_proxy.py &

Docker containers connect via host.docker.internal:5435.
"""
import socket
import threading
import sys

LISTEN_HOST  = "0.0.0.0"
LISTEN_PORT  = 5435
TARGET_HOST  = "db.zgfbwsvzcxxyrtavntxl.supabase.co"
TARGET_PORT  = 5432
BUFFER_SIZE  = 65536


def pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass


def handle(client: socket.socket) -> None:
    try:
        # Resolve target; Python resolves hostname and picks IPv6 if needed
        infos = socket.getaddrinfo(TARGET_HOST, TARGET_PORT,
                                   type=socket.SOCK_STREAM)
        af, socktype, proto, _, addr = infos[0]
        server = socket.socket(af, socktype, proto)
        server.settimeout(10)
        server.connect(addr)
        server.settimeout(None)
    except Exception as e:
        print(f"[proxy] Connect to {TARGET_HOST}:{TARGET_PORT} failed: {e}")
        client.close()
        return

    t1 = threading.Thread(target=pipe, args=(client, server), daemon=True)
    t2 = threading.Thread(target=pipe, args=(server, client), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    client.close()
    server.close()


def main() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(50)
    print(f"[proxy] Listening on {LISTEN_HOST}:{LISTEN_PORT} → {TARGET_HOST}:{TARGET_PORT}")
    sys.stdout.flush()
    while True:
        client, addr = srv.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
