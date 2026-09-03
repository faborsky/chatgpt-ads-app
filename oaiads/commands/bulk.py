"""Commands: bulk-submit, bulk-job, bulk-operations (Bulk API — limited preview, not in the OpenAPI spec)."""

from __future__ import annotations

import time

from oaiads import api
from oaiads.formatting import _die, _err, _output_json, print_table, _truncate
from oaiads.commands.common import emit, parse_json_arg, print_plan

OP_TYPES = ["campaign.create", "campaign.update", "ad_group.create", "ad_group.update", "ad.create", "ad.update"]
TERMINAL = ("completed", "partially_failed", "failed")


def _validate_ops(ops: list) -> None:
    if not isinstance(ops, list) or not (1 <= len(ops) <= 1000):
        _die("ERROR: operations must be a list of 1–1 000 items.")
    ids, keys = set(), set()
    for i, op in enumerate(ops):
        oid = op.get("operation_id")
        if not oid or oid in ids:
            _die(f"ERROR: operations[{i}].operation_id missing or duplicate.")
        ids.add(oid)
        if op.get("type") not in OP_TYPES:
            _die(f"ERROR: operations[{i}].type must be one of {OP_TYPES}.")
        if not isinstance(op.get("input"), dict):
            _die(f"ERROR: operations[{i}].input must be an object.")
        if op["type"].endswith(".create"):
            k = op.get("idempotency_key")
            if not k or k in keys:
                _die(f"ERROR: operations[{i}] create needs a unique idempotency_key.")
            keys.add(k)
        else:
            if not op.get("target_resource_id"):
                _die(f"ERROR: operations[{i}] update needs target_resource_id.")
        status = op["input"].get("status")
        if status == "active" and op["type"].endswith(".create"):
            _err(f"⚠ operations[{i}] creates an ACTIVE {op['type'].split('.')[0]} — consider paused until verified.")


def cmd_bulk_submit(args) -> None:
    payload = parse_json_arg(args.file if args.file.startswith("@") else "@" + args.file, "--file")
    ops = payload.get("operations") if isinstance(payload, dict) else payload
    _validate_ops(ops)
    body = {"operations": ops, "partial_failure": not args.no_partial_failure, "validate_only": not args.confirm}
    key = args.idempotency_key or api.new_idempotency_key()
    if not args.confirm and not args.skip_validation:
        _err(f"Dry-run: submitting a validate_only job ({len(ops)} ops) — server-side validation, no ad resources change.")
    elif not args.confirm:
        print_plan("POST", "/bulk_mutation_jobs", {**body, "operations": f"<{len(ops)} operations>"}, args)
        return
    api.bulk_budget_wait_and_record()
    resp = api._api_call("POST", "/bulk_mutation_jobs", json_body=body, idempotency_key=key, soft=True)
    if isinstance(resp, dict) and "_error" in resp and resp["_error"].get("status") == 404:
        _die("ERROR: Bulk API returned 404 — it is a limited preview enabled per ad account. Ask your OpenAI account team.")
    if isinstance(resp, dict) and "_error" in resp:
        e = resp["_error"]
        _die(f"ERROR: HTTP {e.get('status')} {e.get('code') or ''}: {e.get('message')}")
    if args.json:
        _output_json({**resp, "_idempotency_key": key, "validate_only": body["validate_only"]})
    else:
        mode = "VALIDATION job" if body["validate_only"] else "job"
        print(f"Bulk {mode} {resp.get('id')} status {resp.get('status')} ({resp.get('operation_count')} ops). Idempotency-Key {key}")
        print(f"Poll: bulk-job --job-id {resp.get('id')} --wait   then: bulk-operations --job-id {resp.get('id')}")
    if args.wait:
        args.job_id = resp.get("id")
        cmd_bulk_job(args)


def cmd_bulk_job(args) -> None:
    delays = [2, 3, 5, 10, 15, 30]
    attempt = 0
    deadline = time.time() + args.wait_timeout
    while True:
        job = api._api_call("GET", f"/bulk_mutation_jobs/{args.job_id}")
        if not args.wait or job.get("status") in TERMINAL or time.time() > deadline:
            break
        d = delays[min(attempt, len(delays) - 1)]
        _err(f"  {job.get('status')}… next check in {d}s")
        time.sleep(d)
        attempt += 1
    emit(job, args, lambda j: print(f"job {j.get('id')}: {j.get('status')} ({j.get('operation_count')} ops) created {j.get('created_at')} completed {j.get('completed_at')}"))
    if args.wait and job.get("status") in TERMINAL:
        cmd_bulk_operations(args)


def cmd_bulk_operations(args) -> None:
    rows = api._fetch_all(f"/bulk_mutation_jobs/{args.job_id}/operations", max_items=5000, page_size=100)

    def human(items):
        print_table([[o.get("operation_id"), o.get("type"), o.get("status"), o.get("resource_id") or "", o.get("error_code") or "",
                      _truncate(o.get("error"), 50), "yes" if o.get("retryable") else "", o.get("retry_after_seconds") or ""]
                     for o in items],
                    ["Operation", "Type", "Status", "Resource", "Error code", "Error", "Retryable", "Retry after"])
        failed = [o for o in items if o.get("status") in ("failed", "skipped")]
        print(f"\n{len(items)} operation(s), {len(failed)} failed/skipped." +
              (" Retry: resubmit the same body with a NEW request-level Idempotency-Key, keeping create idempotency_keys." if failed else ""))

    emit(rows, args, human)
