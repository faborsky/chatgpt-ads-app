"""Commands: audiences, audience-detail, audience-create/add/remove/replace/merge/archive, audience-operation."""

from __future__ import annotations

import time

from oaiads import api, lint
from oaiads.formatting import _die, _err, fmt_ts, print_table, _truncate
from oaiads.commands.common import emit, parse_csv, print_plan, qarr, run_write, state_change

IDENTIFIER_TYPES = ["email", "phone", "email_sha256", "phone_number_sha256", "gaid"]
INTENDED_USES = ["inclusion", "exclusion", "bid_multiplier"]


def cmd_audiences(args) -> None:
    params = []
    if args.intended_use:
        params.append(("intended_use", args.intended_use))
    for aid in parse_csv(args.ids):
        params.append((qarr("custom_audience_ids"), aid))
    if args.granular:
        params.append(("matched_count_granularity", "granular"))
    if args.policy_revision:
        params.append(("policy_revision", args.policy_revision))
    data = api._api_call("GET", "/custom_audiences", params + [("limit", 500)])
    rows = data.get("data", [])
    if data.get("has_more"):
        rows = api._fetch_all("/custom_audiences", params, max_items=args.max_items)
    if not args.all:
        rows = [r for r in rows if r.get("status") != "archived"]

    def human(items):
        print_table([[a.get("id"), _truncate(a.get("name"), 34), a.get("status"), a.get("matched_user_count_range"),
                      a.get("uploaded_identifier_count_range"), a.get("invalid_identifier_count_range"),
                      a.get("membership_revision"), fmt_ts(a.get("updated_at"))[:10]] for a in items],
                    ["ID", "Name", "Status", "Matched users", "Uploaded", "Invalid", "Rev", "Updated"])
        note = f" eligible for {args.intended_use}" if args.intended_use else ""
        print(f"\n{len(items)} audience(s){note}." + (f" policy_revision: {data.get('policy_revision')}" if data.get("policy_revision") else ""))
        print("Counts are privacy-preserving ranges; 'none' = not available. Inclusion/bid multipliers need ~25 000 matched users; "
              "exclusion works with small/empty audiences. Not available for EEA/Switzerland targeting.")

    emit(rows, args, human)


def cmd_audience_detail(args) -> None:
    params = [("matched_count_granularity", "granular")] if args.granular else None
    emit(api._api_call("GET", f"/custom_audiences/{args.audience_id}", params), args,
         lambda a: print("\n".join(f"{k}: {v}" for k, v in a.items())))


def _file_fields(args) -> dict:
    """file_id + filename + mimetype + file_size (exact values from file-upload)."""
    if not args.file_id:
        return {}
    for f in ("filename", "mimetype", "file_size"):
        if getattr(args, f, None) in (None, ""):
            _die(f"ERROR: --{f.replace('_', '-')} is required with --file-id (use the values printed by file-upload).")
    return {"file_id": args.file_id, "filename": args.filename, "mimetype": args.mimetype, "file_size": int(args.file_size)}


def cmd_audience_create(args) -> None:
    findings: list = []
    lint.lint_name(args.name, "Audience", findings)
    body: dict = {"name": args.name}
    if args.description:
        body["description"] = args.description
    body.update(_file_fields(args))
    if args.file_id:
        if args.auto_resolve:
            body["identifier_resolution"] = "auto"
        elif args.identifier_type:
            body["identifier_type"] = args.identifier_type
        else:
            findings.append(("warn", "no --identifier-type given — the API defaults to email. For mixed CSV columns use --auto-resolve."))
    else:
        findings.append(("warn", "No file → creating an EMPTY audience (needs small-audience support on the account). "
                                 "Add members later with audience-add; usable for exclusion once ready."))
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    resp = run_write("POST", "/custom_audiences", body, args, "", idempotent=False,
                     note="Create returns an audience object (no operation to poll). If the response is lost, "
                          "check `audiences` before creating again — creates are NOT idempotent.")
    if resp is not None and not args.json:
        print(f"Audience created: {resp.get('id')} \"{resp.get('name')}\" status {resp.get('status')}. "
              "Poll with audience-detail until ready.")


def _identifiers_from_args(args) -> list[dict]:
    items = []
    for raw in parse_csv(args.identifiers) if args.identifiers else []:
        if ":" in raw and raw.split(":", 1)[0] in IDENTIFIER_TYPES:
            t, v = raw.split(":", 1)
        else:
            if not args.identifier_type:
                _die("ERROR: give --identifier-type or prefix each identifier as type:value (e.g. email:a@b.cz).")
            t, v = args.identifier_type, raw
        items.append({"identifier_type": t, "identifier": v.strip()})
    if args.identifiers_file:
        with open(args.identifiers_file, encoding="utf-8") as f:
            for line in f:
                v = line.strip()
                if v and not v.startswith("#"):
                    if not args.identifier_type:
                        _die("ERROR: --identifier-type is required with --identifiers-file.")
                    items.append({"identifier_type": args.identifier_type, "identifier": v})
    return items


def _membership(args, action: str) -> None:
    body: dict = {}
    idents = _identifiers_from_args(args)
    if args.file_id and idents:
        _die("ERROR: give a --file-id OR inline identifiers, not both.")
    if not args.file_id and not idents:
        _die("ERROR: give --file-id (from file-upload) or --identifiers / --identifiers-file.")
    if args.file_id:
        body["file_id"] = args.file_id
        if args.auto_resolve:
            body["identifier_resolution"] = "auto"
        elif args.identifier_type:
            body["identifier_type"] = args.identifier_type
    else:
        body["identifiers"] = idents
        if len(idents) > 10000:
            _err("ℹ > 10 000 inline identifiers switch to file-based processing server-side; prefer file-upload for bulk.")
    if args.expected_revision is not None:
        body["expected_revision"] = int(args.expected_revision)
    else:
        current = api._api_call("GET", f"/custom_audiences/{args.audience_id}")
        if current.get("membership_revision") is not None:
            body["expected_revision"] = int(current["membership_revision"])
        if current.get("status") not in ("ready",):
            _err(f"⚠ audience status is {current.get('status')} — membership ops expect a ready audience.")
    key = args.idempotency_key or api.new_idempotency_key()
    args.idempotency_key = key
    resp = run_write("POST", f"/custom_audiences/{args.audience_id}/{action}", body, args, "",
                     create=True, note=f"Idempotency-Key {key} — keep it with this request; reuse ONLY to retry the same body.")
    if resp is not None and not args.json:
        print(f"{action} accepted: operation {resp.get('operation_id')} status {resp.get('status')}. "
              f"Poll: audience-operation --audience-id {args.audience_id} --operation-id {resp.get('operation_id')} --wait")


def cmd_audience_add(args) -> None:
    _membership(args, "add")


def cmd_audience_remove(args) -> None:
    _membership(args, "remove")


def cmd_audience_replace(args) -> None:
    if not args.file_id:
        _die("ERROR: replace needs --file-id (a full snapshot uploaded with file-upload).")
    body: dict = {"file_id": args.file_id}
    if args.expected_revision is None:
        current = api._api_call("GET", f"/custom_audiences/{args.audience_id}")
        body["expected_revision"] = int(current.get("membership_revision") or 0)
    else:
        body["expected_revision"] = int(args.expected_revision)
    if args.auto_resolve:
        body["identifier_resolution"] = "auto"
    elif args.identifier_type:
        body["identifier_type"] = args.identifier_type
    for f in ("filename", "mimetype", "file_size"):
        if getattr(args, f, None):
            body[f] = int(args.file_size) if f == "file_size" else getattr(args, f)
    key = args.idempotency_key or api.new_idempotency_key()
    args.idempotency_key = key
    resp = run_write("POST", f"/custom_audiences/{args.audience_id}/replace", body, args, "", create=True,
                     note="REPLACES the whole membership with the file (audience id and campaign references stay). "
                          f"Idempotency-Key {key}.")
    if resp is not None and not args.json:
        print(f"replace accepted: operation {resp.get('operation_id')} status {resp.get('status')}.")


def cmd_audience_merge(args) -> None:
    ids = parse_csv(args.ids)
    if not (2 <= len(ids) <= 64):
        _die("ERROR: merge needs 2–64 audience ids.")
    findings: list = []
    lint.lint_name(args.name, "Audience", findings)
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    key = args.idempotency_key or api.new_idempotency_key()
    args.idempotency_key = key
    resp = run_write("POST", "/custom_audiences/merge", {"name": args.name, "custom_audience_ids": ids}, args, "",
                     create=True, note="Creates a NEW independent audience (sources unchanged, no future sync).")
    if resp is not None and not args.json:
        print(f"merge accepted: new audience {resp.get('custom_audience_id')} operation {resp.get('operation_id')} status {resp.get('status')}.")


def cmd_audience_archive(args) -> None:
    path = f"/custom_audiences/{args.audience_id}/archive"
    if not args.confirm:
        print_plan("POST", path, None, args, note="Archiving an audience is PERMANENT — it cannot be restored or targeted again.")
        return
    run_write("POST", path, None, args, f"Audience {args.audience_id} archived (permanent).", idempotent=True)


def cmd_audience_operation(args) -> None:
    path = f"/custom_audiences/{args.audience_id}/operations/{args.operation_id}"
    delays = [3, 5, 10, 20, 30, 60]
    attempt = 0
    deadline = time.time() + args.wait_timeout
    while True:
        op = api._api_call("GET", path)
        status = op.get("status")
        if not args.wait or status in ("succeeded", "failed") or time.time() > deadline:
            break
        delay = delays[min(attempt, len(delays) - 1)]
        _err(f"  {status}… next check in {delay}s")
        time.sleep(delay)
        attempt += 1
    emit(op, args, lambda o: print(f"operation {o.get('operation_id')} ({o.get('operation')}) on {o.get('custom_audience_id')}: {o.get('status')}"))
    if op.get("status") == "failed":
        _err("Operation failed — reconcile before submitting another change; contact support with the operation id if needed.")
