import argparse

from .httpd import Server
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="启动桥跨工况簿")
    parser.add_argument("--port", type=int, default=8765, help="本机 HTTP 端口")
    parser.add_argument("--db", default="var/girder.sqlite", help="SQLite 文件路径")
    args = parser.parse_args()
    with Server(("127.0.0.1", args.port), Store(args.db)) as server:
        print(f"桥跨工况簿已启动：http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
