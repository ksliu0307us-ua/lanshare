import argparse
import secrets
import sys
from pathlib import Path

from . import server


def build_parser():
    p = argparse.ArgumentParser(
        prog="lanshare",
        description="share a folder with other devices on your local network",
    )
    p.add_argument("folder", nargs="?", default=".", help="folder to share (default: current)")
    p.add_argument("-p", "--port", type=int, default=8008)
    p.add_argument("--host", default="0.0.0.0", help="address to listen on (default: all interfaces)")
    p.add_argument("-u", "--upload", action="store_true", help="allow uploads into the folder")
    p.add_argument("-t", "--token", nargs="?", const="auto", metavar="SECRET",
                   help="require ?t=SECRET on every request; with no value, one is generated")
    p.add_argument("-q", "--quiet", action="store_true", help="don't log each request")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    folder = Path(args.folder).expanduser()
    token = secrets.token_urlsafe(8) if args.token == "auto" else args.token

    try:
        srv = server.make_server(folder, args.host, args.port, args.upload, token, args.quiet)
    except NotADirectoryError as e:
        print(f"error: not a folder: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"error: can't listen on {args.host}:{args.port}: {e.strerror}", file=sys.stderr)
        return 1

    ip = server.lan_ip() if args.host == "0.0.0.0" else args.host
    port = srv.server_address[1]
    q = f"?t={token}" if token else ""
    print(f"sharing {folder.resolve()}")
    print(f"  on this network:  http://{ip}:{port}/{q}")
    print(f"  on this machine:  http://127.0.0.1:{port}/{q}")
    print(f"  uploads: {'on' if args.upload else 'off'}   token: {'on' if token else 'off'}")
    print("ctrl-c to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
