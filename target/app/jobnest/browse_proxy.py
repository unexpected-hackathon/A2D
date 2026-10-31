"""브라우저용 HTTP 프록시 (원격·macOS·Windows에서 시연 화면 보기).

시연 네트워크 안에서 시연 DNS로 이름을 풀어 주므로, 노트북 브라우저가 이 프록시를 쓰면
*.jobnest.test가 그대로 열린다. 호스트에는 127.0.0.1에만 열고, SSH 터널로 붙는다.
시연 도메인과 시연 DNS가 가리키는 외부 이름만 허용한다(열린 프록시가 되지 않게).
"""

import asyncio
import os

from . import config as c

PORT = int(os.environ.get("BROWSE_LISTEN_PORT", "8888"))
ALLOWED = set(c.ALL_HOSTS)


def allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    return host in ALLOWED or host.endswith("." + c.DOMAIN)


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()


async def reply(writer: asyncio.StreamWriter, status: str, text: str = "") -> None:
    body = text.encode()
    writer.write(f"HTTP/1.1 {status}\r\nContent-Type: text/plain; charset=utf-8\r\n"
                 f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
    await writer.drain()
    writer.close()


async def handle(creader: asyncio.StreamReader, cwriter: asyncio.StreamWriter) -> None:
    try:
        head = await creader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
        cwriter.close()
        return
    lines = head.decode("latin-1").split("\r\n")
    try:
        method, target, version = lines[0].split(" ", 2)
    except ValueError:
        return await reply(cwriter, "400 Bad Request")

    if method.upper() == "CONNECT":  # HTTPS
        host, _, port = target.rpartition(":")
        port = int(port or 443)
    elif target.startswith("http://"):  # 평문 HTTP
        rest = target[len("http://"):]
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        port = int(port or 80)
    else:
        return await reply(cwriter, "400 Bad Request", "프록시 형식 요청만 받습니다.")

    if not allowed(host):
        return await reply(cwriter, "403 Forbidden", f"시연 도메인만 허용합니다: {host}")
    try:
        ureader, uwriter = await asyncio.wait_for(asyncio.open_connection(host, port), 10)
    except (OSError, asyncio.TimeoutError) as e:
        return await reply(cwriter, "502 Bad Gateway", f"{host}:{port} 연결 실패: {e}")

    if method.upper() == "CONNECT":
        cwriter.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await cwriter.drain()
    else:
        # 원래 형식으로 바꾸고 연결을 한 번 쓰고 닫는다(다른 호스트 요청이 섞이지 않게).
        out = [f"{method} /{path} {version}"]
        out += [ln for ln in lines[1:] if ln and ln.split(":", 1)[0].lower()
                not in ("connection", "proxy-connection", "keep-alive")]
        out.append("Connection: close")
        uwriter.write(("\r\n".join(out) + "\r\n\r\n").encode("latin-1"))
        await uwriter.drain()

    await asyncio.gather(pipe(creader, uwriter), pipe(ureader, cwriter))


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", PORT)
    print(f"[browse] HTTP 프록시 :{PORT}, 허용 도메인 *.{c.DOMAIN}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
