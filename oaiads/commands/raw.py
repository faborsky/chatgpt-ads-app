"""Command: raw — escape hatch for any endpoint (future or OAuth-only ones: /me, /ad_account_creation_sessions, …)."""

from __future__ import annotations

from oaiads import api
from oaiads.formatting import _die, _output_json
from oaiads.commands.common import parse_json_arg, print_plan


def cmd_raw(args) -> None:
    method = args.method.upper()
    if method not in ("GET", "POST", "PATCH", "DELETE"):
        _die("ERROR: method must be GET, POST, PATCH or DELETE.")
    path = args.path if args.path.startswith("/") else "/" + args.path
    params = parse_json_arg(args.params, "--params")
    body = parse_json_arg(args.body, "--body")
    if isinstance(params, dict):
        # Array values go as key[]=v1&key[]=v2 — a bare repeated key is rejected with 400 invalid_type.
        params = [((k if k.endswith(api.ARRAY_SUFFIX) or not isinstance(vs, list) else k + api.ARRAY_SUFFIX), v)
                  for k, vs in params.items() for v in (vs if isinstance(vs, list) else [vs])]
    if method != "GET" and not args.confirm:
        print_plan(method, path, body, args, note="raw writes need --confirm; no lint, no idempotency unless --idempotency-key.")
        return
    resp = api._api_call(method, path, params, json_body=body, idempotency_key=args.idempotency_key,
                         idempotent=bool(args.idempotency_key))
    _output_json(resp)
