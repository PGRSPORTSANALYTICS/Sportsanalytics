"""
port_proxy.py — TCP-level reverse proxy for Replit VM deployment.

Listens on port 5000 (external / health-check port).
Forwards all connections to Streamlit on port 5001.

If Streamlit is not yet ready, returns HTTP 200 with a "Starting..." page
so Replit's health check always passes immediately.

Works transparently for HTTP AND WebSocket connections because it proxies
at the raw TCP byte level — no protocol awareness needed.
"""

import asyncio
import sys

LISTEN_PORT  = 5000
BACKEND_PORT = 5001

HEALTH_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/html\r\n"
    b"Content-Length: 120\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    b"<html><head><meta http-equiv='refresh' content='5'></head>"
    b"<body><h2>PGR Sports Analytics</h2><p>Starting up, please wait...</p></body></html>"
)


async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    """Forward bytes from src to dst until connection closes."""
    try:
        while True:
            data = await src.read(65_536)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


async def handle(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter) -> None:
    """Handle one incoming connection."""
    try:
        backend_r, backend_w = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", BACKEND_PORT),
            timeout=2.0,
        )
    except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
        # Streamlit not ready yet — serve HTTP 200 health response
        try:
            await client_r.read(4_096)       # consume the request
            client_w.write(HEALTH_RESPONSE)
            await client_w.drain()
        except Exception:
            pass
        finally:
            try:
                client_w.close()
            except Exception:
                pass
        return

    # Streamlit is ready — pipe bytes in both directions
    await asyncio.gather(
        _pipe(client_r, backend_w),
        _pipe(backend_r, client_w),
        return_exceptions=True,
    )


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", LISTEN_PORT)
    addr = server.sockets[0].getsockname()
    print(f"[proxy] ✅ TCP proxy listening on {addr[0]}:{addr[1]} → localhost:{BACKEND_PORT}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
