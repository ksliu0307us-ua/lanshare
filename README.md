# lanshare

Share a folder with any device on your Wi-Fi, straight from the terminal.
Open the printed address on your phone, tablet or another laptop and you get
a plain web page to download files from, and (if you allow it) upload to.

```
$ lanshare ~/Pictures/trip --upload --token
sharing /home/me/Pictures/trip
  on this network:  http://192.168.1.23:8008/?t=5cbLEicn8CM
  on this machine:  http://127.0.0.1:8008/?t=5cbLEicn8CM
  uploads: on   token: on
ctrl-c to stop
```

I wrote it because moving a few files between my phone and my laptop should
not require a cable, a cloud account, or a chat app I message myself on.

## Who it's for

Me, several times a week. Anyone who has two devices on the same network
and a file on the wrong one.

## Built with

- Python 3.9+, standard library only (`http.server`, `email` for multipart
  parsing). No dependencies.
- `pytest` for the tests, which start a real server on a random port.

## Install

```sh
git clone https://github.com/ksliu0307us-ua/lanshare.git
cd lanshare
pip install -e .
```

Or run it without installing: `python -m lanshare.cli ...`.

## Usage

```sh
lanshare                         # share the current folder, read-only
lanshare ~/Downloads             # share a folder
lanshare -u                      # allow uploads (a form appears on every page)
lanshare -t                      # require a random token in the URL
lanshare -t mysecret             # or a token you choose
lanshare -p 9000                 # another port
lanshare --host 127.0.0.1        # this machine only (useful for testing)
lanshare -q                      # don't log each request
```

Then open the "on this network" address on the other device. Subfolders
are browsable; files download with a tap. With `-u`, each page has an
"Upload here" button that saves into the folder you're looking at.

## What it does and doesn't protect

- **Nothing outside the shared folder is reachable.** Every path is resolved
  and checked against the root; `..`, encoded dots and symlinks that lead
  out are refused. Hidden files (dotfiles) are not listed.
- **Uploads never overwrite.** A second `photo.jpg` becomes `photo (2).jpg`.
  Uploaded file names are reduced to a safe base name.
- **The token is a shared secret in the URL**, good for keeping a nosy
  roommate out, not for a hostile network. Traffic is plain HTTP. Don't
  expose this to the internet; it's for a network you trust.
- Uploads are read into memory before being written, so very large files
  need that much RAM. Streaming is on the roadmap.

## Running the tests

```sh
pip install pytest
pytest
```

## Roadmap

See [ROADMAP.md](ROADMAP.md). Issues and PRs welcome.

## License

MIT. See [LICENSE](LICENSE).
