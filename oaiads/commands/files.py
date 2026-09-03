"""Commands: image-upload (POST /upload), file-upload (POST /uploads). Direct writes — media only, no spend risk."""

from __future__ import annotations

import mimetypes
import os

from oaiads import api
from oaiads.formatting import _die, _err, _output_json

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_UPLOAD_BYTES = 16 * 1024 * 1024      # request body limit documented for the API
AUDIENCE_MAX_BYTES = 500_000_000


def upload_image(url: str | None = None, path: str | None = None, purpose: str | None = None) -> dict:
    """POST /upload — JSON with image_url, or multipart with a local file. Returns {"file_id": …}."""
    if bool(url) == bool(path):
        _die("ERROR: give exactly one of --url / --file.")
    if url:
        body: dict = {"image_url": url}
        if purpose:
            body["purpose"] = purpose
        return api._api_call("POST", "/upload", json_body=body)
    if not os.path.isfile(path):
        _die(f"ERROR: file not found: {path}")
    size = os.path.getsize(path)
    if size > MAX_UPLOAD_BYTES:
        _die(f"ERROR: {path} is {size / 1e6:.1f} MB — over the 16 MiB request limit. Host it and use --url.")
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMAGE_EXTS:
        _err(f"⚠ {ext or 'no extension'} is not a typical image type ({sorted(IMAGE_EXTS)}); the API may reject it.")
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    data = {"purpose": purpose} if purpose else None
    with open(path, "rb") as f:
        return api._api_call("POST", "/upload", files={"file": (os.path.basename(path), f, mime)}, data=data)


def cmd_image_upload(args) -> None:
    resp = upload_image(url=args.url, path=args.file, purpose=args.purpose)
    if args.json:
        _output_json(resp)
    else:
        print(f"file_id: {resp.get('file_id')}")
        if args.purpose == "account_favicon":
            print("Assign it with: brand-update --favicon-file-id <file_id> --confirm")
        else:
            print("Use it with: ad-create … --file-id <file_id>")


def cmd_file_upload(args) -> None:
    """POST /uploads — customer-list files for custom audiences (purpose=custom_audience)."""
    path = args.file
    if not os.path.isfile(path):
        _die(f"ERROR: file not found: {path}")
    size = os.path.getsize(path)
    if size == 0:
        _die("ERROR: zero-byte file — create an empty audience without a file instead (audience-create without --file-id).")
    if size > AUDIENCE_MAX_BYTES:
        _die(f"ERROR: file is {size} bytes; the limit is {AUDIENCE_MAX_BYTES}.")
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".csv", ".txt"):
        _die("ERROR: audience files must be UTF-8 .csv (text/csv) or .txt (text/plain).")
    mime = "text/csv" if ext == ".csv" else "text/plain"
    if ext == ".csv":
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            header = f.readline().strip().lower()
        known = {"email", "phone_number", "email_sha256", "phone_number_sha256", "gaid"}
        cols = [c.strip() for c in header.split(",")]
        if not set(cols) & known:
            _die(f"ERROR: CSV header must contain identifier columns {sorted(known)} (got '{header[:80]}').")
        if len(cols) > 1:
            _err("ℹ Mixed identifier columns — create/add with --auto-resolve (identifier_resolution=auto).")
    with open(path, "rb") as f:
        resp = api._api_call("POST", "/uploads", files={"file": (os.path.basename(path), f, mime)},
                             data={"purpose": args.purpose}, timeout=600)
    result = {"file_id": resp.get("file_id"), "filename": os.path.basename(path), "mimetype": mime, "file_size": size}
    if args.json:
        _output_json(result)
    else:
        print(f"file_id:   {result['file_id']}\nfilename:  {result['filename']}\nmimetype:  {result['mimetype']}\nfile_size: {size}")
        print("Use these exact values with audience-create / audience-replace (the API validates size + mimetype). "
              "Use the upload promptly — file ids are not permanent storage.")
