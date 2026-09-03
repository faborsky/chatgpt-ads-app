"""Commands: partner-data-upload-create, partner-data-upload (Ads partner-data uploads — identity graph parquet)."""

from __future__ import annotations

import hashlib
import os

from oaiads import api
from oaiads.formatting import _die, _output_json
from oaiads.commands.common import emit, parse_iso_date, run_write


def cmd_partner_data_upload_create(args) -> None:
    path = args.file
    if not os.path.isfile(path):
        _die(f"ERROR: file not found: {path}")
    name = os.path.basename(path)
    if not name.endswith(".parquet"):
        _die("ERROR: partner data uploads must be .parquet files.")
    size = os.path.getsize(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    body = {"data_type": args.data_type, "snapshot_date": parse_iso_date(args.snapshot_date, "--snapshot-date").isoformat(),
            "file_name": name, "file_size_bytes": size, "sha256": h.hexdigest()}
    resp = run_write("POST", "/partner_data/uploads", body, args, "", idempotent=False,
                     note="Registers the upload and returns instructions/URL for the actual transfer (partner feature).")
    if resp is not None and not args.json:
        _output_json(resp)


def cmd_partner_data_upload(args) -> None:
    emit(api._api_call("GET", f"/partner_data/uploads/{args.upload_id}"), args, lambda u: _output_json(u))
