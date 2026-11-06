import threading
import urllib.error
import urllib.request
import uuid

import pytest

from lanshare import server


def multipart(fields, files):
    """Build a multipart/form-data body. fields: {name: value}, files: [(name, filename, bytes)]."""
    boundary = "----lanshare" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        )
    for name, filename, data in files:
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class Running:
    def __init__(self, root, **kw):
        self.srv = server.make_server(root, host="127.0.0.1", port=0, quiet=True, **kw)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def url(self, path="/"):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path="/"):
        with urllib.request.urlopen(self.url(path)) as r:
            return r.status, r.read()

    def post(self, path, body, ctype):
        req = urllib.request.Request(self.url(path), data=body, method="POST")
        req.add_header("Content-Type", ctype)
        req.add_header("Content-Length", str(len(body)))
        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(req) as r:
                return r.status, r.headers.get("Location")
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                return e.code, e.headers.get("Location")
            raise

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


@pytest.fixture
def shared(tmp_path):
    (tmp_path / "hello.txt").write_text("hi there")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.bin").write_bytes(b"\x00\x01\x02")
    (tmp_path / ".secret").write_text("hidden")
    (tmp_path.parent / "outside.txt").write_text("nope")
    return tmp_path


def status_of(exc):
    return exc.code


# --- browsing ------------------------------------------------------------------


def test_listing_and_download(shared):
    s = Running(shared)
    try:
        code, body = s.get("/")
        assert code == 200
        text = body.decode()
        assert "hello.txt" in text and "sub/" in text
        assert ".secret" not in text
        assert "Upload here" not in text  # uploads off by default

        code, body = s.get("/hello.txt")
        assert code == 200 and body == b"hi there"

        code, body = s.get("/sub/")
        assert "deep.bin" in body.decode() and "../" in body.decode()

        code, body = s.get("/sub/deep.bin")
        assert body == b"\x00\x01\x02"
    finally:
        s.stop()


def test_404_and_traversal_blocked(shared):
    s = Running(shared)
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            s.get("/missing.txt")
        assert status_of(e.value) == 404

        for bad in ("/../outside.txt", "/%2e%2e/outside.txt", "/sub/../../outside.txt"):
            with pytest.raises(urllib.error.HTTPError) as e:
                s.get(bad)
            assert status_of(e.value) in (403, 404), bad
    finally:
        s.stop()


def test_token_required(shared):
    s = Running(shared, token="abc123")
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            s.get("/")
        assert status_of(e.value) == 403
        with pytest.raises(urllib.error.HTTPError):
            s.get("/?t=wrong")
        code, body = s.get("/?t=abc123")
        assert code == 200
        assert "?t=abc123" in body.decode()  # links carry the token along
    finally:
        s.stop()


# --- uploads --------------------------------------------------------------------


def test_upload_disabled_by_default(shared):
    s = Running(shared)
    try:
        body, ctype = multipart({}, [("files", "x.txt", b"x")])
        with pytest.raises(urllib.error.HTTPError) as e:
            s.post("/upload", body, ctype)
        assert status_of(e.value) == 405
        assert not (shared / "x.txt").exists()
    finally:
        s.stop()


def test_upload_saves_files_and_redirects(shared):
    s = Running(shared, allow_upload=True)
    try:
        body, ctype = multipart({"dir": ""}, [("files", "a.txt", b"AAA"), ("files", "b.txt", b"BBB")])
        code, location = s.post("/upload", body, ctype)
        assert code == 303 and location == "/"
        assert (shared / "a.txt").read_bytes() == b"AAA"
        assert (shared / "b.txt").read_bytes() == b"BBB"
    finally:
        s.stop()


def test_upload_into_subfolder_and_no_overwrite(shared):
    s = Running(shared, allow_upload=True)
    try:
        body, ctype = multipart({"dir": "sub"}, [("files", "deep.bin", b"new")])
        code, location = s.post("/upload", body, ctype)
        assert location == "/sub/"
        assert (shared / "sub" / "deep.bin").read_bytes() == b"\x00\x01\x02"  # untouched
        assert (shared / "sub" / "deep (2).bin").read_bytes() == b"new"
    finally:
        s.stop()


def test_upload_filename_is_sanitized(shared):
    s = Running(shared, allow_upload=True)
    try:
        body, ctype = multipart({"dir": ""}, [("files", "../../evil.txt", b"x")])
        s.post("/upload", body, ctype)
        assert (shared / "evil.txt").exists()
        assert not (shared.parent / "evil.txt").exists()
    finally:
        s.stop()


def test_upload_outside_dir_refused(shared):
    s = Running(shared, allow_upload=True)
    try:
        body, ctype = multipart({"dir": ".."}, [("files", "x.txt", b"x")])
        with pytest.raises(urllib.error.HTTPError) as e:
            s.post("/upload", body, ctype)
        assert status_of(e.value) == 403
    finally:
        s.stop()


# --- helpers --------------------------------------------------------------------


def test_safe_filename():
    assert server.safe_filename("C:\\Users\\me\\pic.jpg") == "pic.jpg"
    assert server.safe_filename("../../x") == "x"
    assert server.safe_filename("..") == "upload"
    assert server.safe_filename('we<ird>:"name".txt') == "weirdname.txt"


def test_human_size():
    assert server.human_size(10) == "10 B"
    assert server.human_size(2048) == "2.0 KB"
    assert server.human_size(5 * 1024 ** 2) == "5.0 MB"
