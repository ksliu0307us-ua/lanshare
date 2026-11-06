# Roadmap

Roughly in order. Open an issue if you want one sooner.

## Soon

- [ ] QR code in the terminal for the share URL (a small QR encoder, stdlib only), so phones don't have to type it
- [ ] Stream uploads to disk instead of reading the whole body into memory
- [ ] Share a single file (`lanshare report.pdf`) with a one-file page
- [ ] "Download folder as zip" link on each listing
- [ ] Drag-and-drop and upload progress on the page (small inline JS)
- [ ] `--open` to launch the local URL in the browser right away

## Next

- [ ] Paste box: send a snippet of text between devices without making a file
- [ ] Range requests so video and audio can seek, and interrupted downloads resume
- [ ] Optional HTTPS with a self-signed cert (`--tls`) for networks you trust less
- [ ] Dark mode and a tidier mobile layout
- [ ] Read-only vs upload-only modes (a drop box that doesn't list files)
- [ ] mDNS / `lanshare.local` so the address is stable

## Later / maybe

- [ ] Discovery: `lanshare --find` lists other lanshare instances on the network
- [ ] A system tray helper for Windows and macOS
- [ ] Publish to PyPI

## Housekeeping

- [ ] Tests for the CLI argument handling and the printed addresses
- [ ] GitHub Actions running `pytest` on Linux, macOS and Windows (socket and path quirks differ)
- [ ] Type hints and a `mypy` pass
- [ ] CHANGELOG.md starting at 0.2.0
