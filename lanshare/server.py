"""A small HTTP server that shares one folder on the local network.

GET  /            directory listing (HTML), or a file download
GET  /sub/        listing of a subfolder
POST /upload      multipart form upload into the shared folder (only with uploads enabled)

Everything is resolved against the shared root and anything that escapes it
(`..`, absolute paths, symlinks pointing outside) is refused with 403.
"""

import html
import mimetypes
import os
import secrets
import socket
import urllib.parse
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as email_policy
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_UPLOAD = 2 * 1024 ** 3  # 2 GiB; larger than this and the request is refused


def lan_ip():
    """Best guess at the address other devices on the network can reach."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packets are sent for UDP connect
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def safe_filename(name):
    """Keep just the final path component, strip anything odd."""
    name = name.replace("\\", "/").split("/")[-1].strip()
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')
    if name in ("", ".", ".."):
        name = "upload"
    return name[:200]


def unique_path(folder, name):
    candidate = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 2
    while candidate.exists():
        candidate = folder / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:48rem;margin:1.5rem auto;padding:0 1rem;color:#222}}
h1{{font-size:1.2rem;word-break:break-all}} table{{width:100%;border-collapse:collapse}}
td{{padding:.4rem .3rem;border-bottom:1px solid #eee;vertical-align:top}}
td.size,td.date{{color:#777;white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}}
a{{text-decoration:none;color:#0645ad;word-break:break-all}} form{{margin:1rem 0;padding:1rem;background:#f6f6f6;border-radius:8px}}
input[type=file]{{max-width:100%}} .note{{color:#777;font-size:.9rem}}
</style></head><body>
<h1>{title}</h1>
{upload}
<table>{rows}</table>
<p class="note">lanshare</p>
</body></html>"""

UPLOAD_FORM = """<form method="post" action="/upload{token_q}" enctype="multipart/form-data">
<input type="hidden" name="dir" value="{dir}">
<input type="file" name="files" multiple required>
<button type="submit">Upload here</button>
</form>"""


class ShareHandler(SimpleHTTPRequestHandler):
    # set by make_server
    root = Path(".")
    allow_upload = False
    token = None
    quiet = False

    def log_message(self, fmt, *args):
        if not self.quiet:
            super().log_message(fmt, *args)

    # -- helpers -----------------------------------------------------------

    def _authorized(self):
        if not self.token:
            return True
        query = urllib.parse.urlparse(self.path).query
        given = urllib.parse.parse_qs(query).get("t", [None])[0]
        return secrets.compare_digest(given or "", self.token)

    def _token_q(self):
        return f"?t={self.token}" if self.token else ""

    def _resolve(self, url_path):
        """Map a URL path to a real path under root, or None if it escapes."""
        rel = urllib.parse.unquote(urllib.parse.urlparse(url_path).path)
        rel = rel.lstrip("/")
        if "\x00" in rel:
            return None
        target = (self.root / rel).resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            return None
        return target

    def _send_html(self, body, status=HTTPStatus.OK):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status, text):
        self._send_html(f"<h1>{status.value} {html.escape(text)}</h1>", status)

    # -- GET ---------------------------------------------------------------

    def do_GET(self):
        if not self._authorized():
            return self._error(HTTPStatus.FORBIDDEN, "missing or wrong token")
        target = self._resolve(self.path)
        if target is None:
            return self._error(HTTPStatus.FORBIDDEN, "outside the shared folder")
        if target.is_dir():
            return self._listing(target)
        if target.is_file():
            return self._send_file(target)
        return self._error(HTTPStatus.NOT_FOUND, "not found")

    def _listing(self, folder):
        rel = folder.relative_to(self.root)
        rel_str = "" if str(rel) == "." else str(rel).replace(os.sep, "/")
        rows = []
        tq = self._token_q()
        if rel_str:
            parent = "/" + "/".join(rel_str.split("/")[:-1])
            parent = parent if parent != "/" else ""
            rows.append(f'<tr><td><a href="{parent}/{tq}">../</a></td><td></td><td></td></tr>')
        entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        for p in entries:
            if p.name.startswith("."):
                continue
            href = "/" + urllib.parse.quote(f"{rel_str}/{p.name}".lstrip("/"))
            try:
                st = p.stat()
            except OSError:
                continue
            when = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            if p.is_dir():
                rows.append(f'<tr><td><a href="{href}/{tq}">{html.escape(p.name)}/</a></td><td class="size"></td><td class="date">{when}</td></tr>')
            else:
                rows.append(f'<tr><td><a href="{href}{tq}" download>{html.escape(p.name)}</a></td><td class="size">{human_size(st.st_size)}</td><td class="date">{when}</td></tr>')
        if not rows:
            rows.append('<tr><td class="note">empty folder</td></tr>')

        upload = ""
        if self.allow_upload:
            upload = UPLOAD_FORM.format(token_q=tq, dir=html.escape(rel_str))
        title = "/" + rel_str if rel_str else self.root.name or "/"
        self._send_html(PAGE.format(title=html.escape(title), upload=upload, rows="\n".join(rows)))

    def _send_file(self, path):
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        size = path.stat().st_size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", f'attachment; filename="{safe_filename(path.name)}"')
        self.end_headers()
        with path.open("rb") as f:
            chunk = f.read(64 * 1024)
            while chunk:
                self.wfile.write(chunk)
                chunk = f.read(64 * 1024)

    # -- POST --------------------------------------------------------------

    def do_POST(self):
        if not self._authorized():
            return self._error(HTTPStatus.FORBIDDEN, "missing or wrong token")
        if not self.allow_upload:
            return self._error(HTTPStatus.METHOD_NOT_ALLOWED, "uploads are disabled (start with --upload)")
        if urllib.parse.urlparse(self.path).path != "/upload":
            return self._error(HTTPStatus.NOT_FOUND, "not found")

        ctype = self.headers.get("Content-Type", "")
        if not ctype.startswith("multipart/form-data"):
            return self._error(HTTPStatus.BAD_REQUEST, "expected multipart/form-data")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "upload too large or empty")

        body = self.rfile.read(length)
        msg = BytesParser(policy=email_policy).parsebytes(
            b"Content-Type: " + ctype.encode("latin-1") + b"\r\n\r\n" + body
        )

        dest = self.root
        saved = []
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            filename = part.get_filename()
            if name == "dir" and not filename:
                sub = part.get_content().strip()
                resolved = self._resolve("/" + sub)
                if resolved is None or not resolved.is_dir():
                    return self._error(HTTPStatus.FORBIDDEN, "bad upload folder")
                dest = resolved
            elif filename:
                data = part.get_payload(decode=True)
                target = unique_path(dest, safe_filename(filename))
                target.write_bytes(data)
                saved.append(target.name)

        if not saved:
            return self._error(HTTPStatus.BAD_REQUEST, "no files in upload")

        back = "/" + str(dest.relative_to(self.root)).replace(os.sep, "/").strip(".") + "/"
        back = back.replace("//", "/") + self._token_q()
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", back)
        self.end_headers()


def make_server(root, host="0.0.0.0", port=8008, allow_upload=False, token=None, quiet=False):
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    handler = partial(ShareHandler, directory=str(root))
    handler_cls = type("BoundShareHandler", (ShareHandler,), {
        "root": root, "allow_upload": allow_upload, "token": token, "quiet": quiet,
    })
    handler = partial(handler_cls, directory=str(root))
    return ThreadingHTTPServer((host, port), handler)
