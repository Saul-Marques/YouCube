import logging
import os
import yt_dlp
import tempfile
import json
import re
from aiohttp import web

CHUNK_SIZE = 16 * 1024
DATA_FOLDER = os.path.abspath("./data")


def is_file_name_valide(string: str) -> bool:
    return bool(re.match('^[a-zA-Z0-9]*$', string)) == True


def download(url: str) -> str:
    temp_dir = tempfile.TemporaryDirectory(prefix="youcube-")

    YDL_OPTIONS = {
        "format": "bestaudio/worstvideo+bestaudio/worstaudio/worstvideo+worstaudio/best",
        "outtmpl": os.path.join(temp_dir.name, "%(id)s.%(ext)s"),
        "default_search": "auto",
        "restrictfilenames": True,
        "noplaylist": True,  # currently playlist are not supported
        "source_address": "0.0.0.0"  # ipv6 addresses cause issues sometimes
    }

    ytdl = yt_dlp.YoutubeDL(YDL_OPTIONS)
    ytdl.download([url])

    if not os.path.exists(DATA_FOLDER):
        os.mkdir(DATA_FOLDER)

    id = os.listdir(temp_dir.name)[0].rsplit('.', 1)[0]

    final_file = os.path.join(DATA_FOLDER, id + ".dfpwm")

    if not os.path.exists(final_file):
        os.system(
            "ffmpeg -i {} -f dfpwm -ar 48000 -ac 1 {}".format(
                os.path.join(temp_dir.name, "*"),
                final_file
            )
        )

    return final_file


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    logging_handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt='[%(asctime)s %(levelname)s] [YouCube] %(message)s', datefmt="%H:%M:%S")
    logging_handler.setFormatter(formatter)

    logger.addHandler(logging_handler)

    return logger


def get_chunk(file: str, chunkindex: int) -> bytes:
    file = open(file, "rb")
    file.seek(chunkindex * CHUNK_SIZE)

    chunk = file.read(CHUNK_SIZE)
    file.close()

    return chunk


def get_peername_host(request: web.Request) -> str:
    peername = request.transport.get_extra_info('peername')

    if peername is not None:
        host, *_ = peername
        return host
    else:
        return None


class UntrustedProxy(Exception):
    def __str__(self) -> str:
        return "A client is not using a trusted proxy!"


def get_client_ip(request: web.Request, trusted_proxies: list) -> str:
    peername_host = get_peername_host(request)

    if trusted_proxies is None:
        return peername_host

    if peername_host in trusted_proxies:
        x_forwarded_for = request.headers.get('X-Forwarded-For')

        if x_forwarded_for is not None:
            x_forwarded_for = x_forwarded_for.split(",")[0]

        return x_forwarded_for or request.headers.get('True-Client-Ip')

    else:
        raise UntrustedProxy


class Server(object):
    def __init__(self, logger: logging.Logger, trusted_proxies: list) -> None:
        self.logger = logger
        self.trusted_proxies = trusted_proxies

    async def on_shutdown(self, app: web.Application):
        for ws in app["sockets"]:
            await ws.close()

    def init(self):
        app = web.Application()
        app["sockets"] = []
        app.router.add_get("/", self.wshandler)
        app.on_shutdown.append(self.on_shutdown)
        return app

    async def wshandler(self, request: web.Request):
        resp = web.WebSocketResponse()
        available = resp.can_prepare(request)
        if not available:
            return web.Response(body="You cannot access a WebSocket server directly. You need a WebSocket client.", content_type="text")

        await resp.prepare(request)

        try:
            request.app["sockets"].append(resp)

            prefix = f"[{get_client_ip(request, self.trusted_proxies)}] "
            self.logger.info(prefix + "Connected!")

            self.logger.debug(
                prefix +
                "My headers are: " +
                str(request.headers)
            )

            async for msg in resp:
                resp: web.WebSocketResponse
                if msg.type == web.WSMsgType.TEXT:
                    self.logger.debug(prefix + "Message: " + msg.data)
                    message: dict = json.loads(msg.data)

                    if message.get("action") == "request_media":
                        url = message.get("url")
                        file = download(url)

                        await resp.send_json({
                            "action": "media",
                            "file": os.path.basename(file).rsplit('.', 1)[0]
                        })

                    if message.get("action") == "get_chunk":
                        chunkindex = message.get("chunkindex")

                        file = message.get("file")

                        if is_file_name_valide(file):
                            file = os.path.join(
                                DATA_FOLDER,
                                message.get("file") +
                                ".dfpwm"
                            )

                            chunk = get_chunk(file, chunkindex)

                            if len(chunk) == 0:
                                await resp.send_str("mister, the media has finished playing")
                            else:
                                await resp.send_bytes(chunk)

                        else:
                            await resp.send_json({
                                "action": "error",
                                "message": "You dare not use special Characters"
                            })

                else:
                    return resp
            return resp

        finally:
            request.app["sockets"].remove(resp)
            self.logger.info(prefix + "Disconnected!")


def main() -> None:
    logger = setup_logging()
    port = int(os.environ.get("PORT", "5000"))
    trusted_proxies = os.environ.get("TRUSTED_PROXIES")

    proxies = None

    if trusted_proxies != None:
        proxies = []
        for proxy in trusted_proxies.split(","):
            proxies.append(proxy)

    server = Server(logger, proxies)

    web.run_app(server.init(), port=port)


if __name__ == "__main__":
    main()
