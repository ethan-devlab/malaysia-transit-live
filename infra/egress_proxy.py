import asyncio

ALLOWED_HOSTS = frozenset(
    {
        "api.data.gov.my",
        "openapi-malaysia-transport.s3.ap-southeast-1.amazonaws.com",
    }
)
MAX_HEADER_BYTES = 8 * 1024


async def copy_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(64 * 1024):
        writer.write(data)
        await writer.drain()


async def reject(writer: asyncio.StreamWriter, status: bytes) -> None:
    writer.write(b"HTTP/1.1 " + status + b"\r\nConnection: close\r\n\r\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request_line = await reader.readline()
        if len(request_line) > MAX_HEADER_BYTES:
            await reject(writer, b"431 Request Header Fields Too Large")
            return
        try:
            method, target, _ = request_line.decode("ascii").strip().split(" ", 2)
        except ValueError:
            await reject(writer, b"400 Bad Request")
            return
        while True:
            header = await reader.readline()
            if len(header) > MAX_HEADER_BYTES:
                await reject(writer, b"431 Request Header Fields Too Large")
                return
            if header in {b"\r\n", b"\n", b""}:
                break
        host, separator, port = target.rpartition(":")
        if method != "CONNECT" or not separator or port != "443" or host.lower() not in ALLOWED_HOSTS:
            await reject(writer, b"403 Forbidden")
            return
        upstream_reader, upstream_writer = await asyncio.open_connection(host, int(port))
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await asyncio.gather(
            copy_stream(reader, upstream_writer),
            copy_stream(upstream_reader, writer),
            return_exceptions=True,
        )
        upstream_writer.close()
        await upstream_writer.wait_closed()
    finally:
        writer.close()
        await writer.wait_closed()


async def main() -> None:
    server = await asyncio.start_server(handle_client, "0.0.0.0", 8888)
    async with server:
        await server.serve_forever()


asyncio.run(main())
