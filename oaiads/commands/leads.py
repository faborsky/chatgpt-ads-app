"""Commands: lead-forms, lead-form-detail/create/update/publish/archive/test, lead-syncs, lead-sync-create/detail/delete."""

from __future__ import annotations

import re

from oaiads import api, lint
from oaiads.formatting import _die, _err, _output_json, fmt_ts, print_table, _truncate
from oaiads.commands.common import emit, parse_json_arg, print_plan, run_write

FIELD_TYPES = ["text", "choice"]
_SIGNING_SECRET_RE = re.compile(r"^whsec_[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$")


def cmd_lead_forms(args) -> None:
    data = api._api_call("GET", "/lead_forms")
    rows = data.get("data", data) if isinstance(data, dict) else data
    if not args.all:
        rows = [r for r in rows if r.get("status") != "archived"]
    emit(rows, args, lambda items: print_table(
        [[f.get("id"), _truncate(f.get("name"), 30), f.get("status"), len(f.get("fields") or []), f.get("draft_revision_id"),
          f.get("published_revision_id") or "", "yes" if f.get("has_unpublished_changes") else "no", fmt_ts(f.get("updated_at"))[:10]]
         for f in items],
        ["ID", "Name", "Status", "Fields", "Draft rev", "Published rev", "Unpublished", "Updated"]))


def cmd_lead_form_detail(args) -> None:
    params = [("rev_id", args.rev_id)] if args.rev_id else None
    emit(api._api_call("GET", f"/lead_forms/{args.lead_form_id}", params), args, lambda f: _output_json(f))


def _fields_from_args(args) -> list:
    fields = parse_json_arg(args.fields_json, "--fields-json")
    if not isinstance(fields, list):
        _die("ERROR: --fields-json must be a JSON array of {field_type,label,required[,field_id,options]}.")
    findings: list = []
    if not (lint.LEAD_FIELDS_MIN <= len(fields) <= lint.LEAD_FIELDS_MAX):
        findings.append(("error", f"lead forms need {lint.LEAD_FIELDS_MIN}–{lint.LEAD_FIELDS_MAX} fields (got {len(fields)})."))
    for i, f in enumerate(fields):
        if f.get("field_type") not in FIELD_TYPES:
            findings.append(("error", f"fields[{i}].field_type must be text|choice."))
        if not f.get("label") or len(f["label"]) > 256:
            findings.append(("error", f"fields[{i}].label is required (≤ 256 chars)."))
        if "required" not in f:
            findings.append(("error", f"fields[{i}].required (true/false) is missing."))
        if f.get("field_type") == "choice" and not f.get("options"):
            findings.append(("error", f"fields[{i}] is a choice field without options [{{id,label}}]."))
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    return fields


def cmd_lead_form_create(args) -> None:
    body: dict = {"name": args.name, "fields": _fields_from_args(args)}
    if args.privacy_url:
        f: list = []
        lint.lint_url(args.privacy_url, f, "privacy_policy_url")
        if lint.report(f):
            _die("Lint errors — fix them first.")
        body["privacy_policy_url"] = args.privacy_url
    else:
        _err("⚠ No --privacy-url — lead forms collecting personal data should link a privacy policy.")
    resp = run_write("POST", "/lead_forms", body, args, "", idempotent=False, note="Creates a DRAFT; publish with lead-form-publish.")
    if resp is not None and not args.json:
        print(f"Lead form draft created: {resp.get('id')} draft revision {resp.get('draft_revision_id')}.")


def cmd_lead_form_update(args) -> None:
    current = api._api_call("GET", f"/lead_forms/{args.lead_form_id}")
    body: dict = {"name": args.name or current.get("name"),
                  "fields": _fields_from_args(args) if args.fields_json else current.get("fields"),
                  "expected_draft_revision_id": args.expected_draft_revision_id or current.get("draft_revision_id")}
    if args.privacy_url is not None:
        body["privacy_policy_url"] = args.privacy_url
    elif current.get("privacy_policy_url"):
        body["privacy_policy_url"] = current["privacy_policy_url"]
    if body["fields"]:
        body["fields"] = [{k: v for k, v in f.items() if k in ("field_id", "field_type", "label", "required", "options")}
                          for f in body["fields"]]
    resp = run_write("POST", f"/lead_forms/{args.lead_form_id}", body, args, "", idempotent=True,
                     note="Saves a NEW draft revision (full replace of name/fields).")
    if resp is not None and not args.json:
        print(f"Draft saved: revision {resp.get('draft_revision_id')} (unpublished changes: {resp.get('has_unpublished_changes')}).")


def cmd_lead_form_publish(args) -> None:
    rev = args.expected_draft_revision_id
    if not rev:
        rev = api._api_call("GET", f"/lead_forms/{args.lead_form_id}").get("draft_revision_id")
    resp = run_write("POST", f"/lead_forms/{args.lead_form_id}/publish", {"expected_draft_revision_id": rev}, args, "",
                     idempotent=True, note="Publishes the current draft — live for any Business Agent that selects it.")
    if resp is not None and not args.json:
        print(f"Published: revision {resp.get('published_revision_id')} status {resp.get('status')}.")


def cmd_lead_form_archive(args) -> None:
    path = f"/lead_forms/{args.lead_form_id}/archive"
    if not args.confirm:
        print_plan("POST", path, None, args, note="Archiving is permanent; fails if a published Business Agent still uses the form.")
        return
    run_write("POST", path, None, args, f"Lead form {args.lead_form_id} archived.", idempotent=True)


def cmd_lead_form_test(args) -> None:
    rev = args.expected_published_revision_id
    if not rev:
        rev = api._api_call("GET", f"/lead_forms/{args.lead_form_id}").get("published_revision_id")
        if not rev:
            _die("ERROR: the form has no published revision — publish first.")
    key = args.idempotency_key or api.new_idempotency_key()
    args.idempotency_key = key
    resp = run_write("POST", f"/lead_forms/{args.lead_form_id}/test_submissions",
                     {"expected_published_revision_id": rev}, args, "", create=True,
                     note="Sends a synthetic, signed lead to your lead-sync webhook (marked synthetic=true).")
    if resp is not None and not args.json:
        print(f"Test delivery: {resp.get('delivery_status')} (webhook delivery {resp.get('webhook_delivery_id')}, subscription {resp.get('subscription_id')}).")


# ---------------------------------------------------------------------------
# lead sync subscriptions (webhooks — Standard Webhooks HMAC-SHA256)
# ---------------------------------------------------------------------------

def cmd_lead_syncs(args) -> None:
    acct_id = args.ad_account_id or api.account_meta().get("id")
    if not acct_id:
        _die("ERROR: --ad-account-id required (could not resolve from /ad_account).")
    data = api._api_call("GET", "/lead_sync_subscriptions", [("ad_account_id", acct_id)])
    emit(data.get("data", []), args, lambda items: print_table(
        [[s.get("subscription_id"), s.get("status")] for s in items], ["Subscription", "Status"]))


def cmd_lead_sync_create(args) -> None:
    findings: list = []
    lint.lint_url(args.destination_url, findings, "destination_url")
    if not args.destination_url.startswith("https://"):
        findings.append(("error", "destination_url must be https://."))
    body: dict = {"ad_account_id": args.ad_account_id or api.account_meta().get("id"), "destination_url": args.destination_url}
    if args.signing_secret:
        if not _SIGNING_SECRET_RE.match(args.signing_secret):
            findings.append(("error", "signing_secret must look like whsec_ + 43 base64 chars (Standard Webhooks)."))
        body["signing_secret"] = args.signing_secret
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    key = args.idempotency_key or api.new_idempotency_key()
    args.idempotency_key = key
    if not args.confirm:
        print_plan("POST", "/lead_sync_subscriptions", {**body, "signing_secret": "<redacted>" if body.get("signing_secret") else None}, args,
                   note="The signing secret is returned ONCE — your receiver needs it to verify webhook-signature.")
        return
    resp = api._api_call("POST", "/lead_sync_subscriptions", json_body=body, idempotency_key=key, idempotent=False)
    if args.json:
        _output_json(resp)
    else:
        print(f"Lead sync subscription {resp.get('subscription_id')} status {resp.get('status')}")
        print(f"Signing secret (shown ONCE):\n{resp.get('signing_secret')}")
    _err("⚠ Verify every webhook: HMAC-SHA256 over the raw body (Standard Webhooks v1), check webhook-timestamp freshness, "
         "and require OpenAI-Subscription-Id to match the signed body.")


def cmd_lead_sync_detail(args) -> None:
    emit(api._api_call("GET", f"/lead_sync_subscriptions/{args.subscription_id}"), args,
         lambda s: print(f"{s.get('subscription_id')}: {s.get('status')}"))


def cmd_lead_sync_delete(args) -> None:
    path = f"/lead_sync_subscriptions/{args.subscription_id}"
    if not args.confirm:
        print_plan("DELETE", path, None, args, note="Stops lead delivery to the webhook.")
        return
    resp = api._api_call("DELETE", path, idempotent=True)
    emit(resp, args, lambda r: print(f"Subscription {args.subscription_id} deleted: {r.get('deleted', True)}"))
