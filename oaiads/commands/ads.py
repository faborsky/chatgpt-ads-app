"""Commands: ads, ad-detail, ad-review, ad-create/update, ad-preview, ad-activate/pause/archive."""

from __future__ import annotations

import os

from oaiads import api, lint
from oaiads.formatting import _die, _err, fmt_ts, print_table, _truncate
from oaiads.commands.common import (
    drop_archived, emit, issues_str, parse_json_arg, print_plan, qarr, run_write, state_change, trunc,
)
from oaiads.commands.files import upload_image

CREATIVE_TYPES = ["chat_card", "product_ad_template"]
# Serving-issue codes that only say "something in the hierarchy is paused" — expected while paused.
PAUSED_CODES = {"campaign_not_active", "ad_group_not_active", "ad_not_active", "campaign_not_started"}
REVIEW_STATUSES = ["in_review", "rejected", "approved"]


def _ads_for(args, include_issues: bool = True) -> list:
    params = []
    if include_issues:
        params.append((qarr("include"), "serving_issues"))
    if getattr(args, "name", None):
        if len(args.name) < 3:
            _die("ERROR: --name filter needs at least 3 characters.")
        params.append(("name", args.name))
    if getattr(args, "order", None):
        params.append(("order", args.order))
    if getattr(args, "campaign_id", None):
        rows = []
        for g in api._fetch_all("/ad_groups", [("campaign_id", args.campaign_id)]):
            rows += api._fetch_all("/ads", params + [("ad_group_id", g["id"])], max_items=args.max_items)
            for r in rows:
                r.setdefault("_ad_group_id", g["id"])
        return rows
    if getattr(args, "ad_group_id", None):
        params.append(("ad_group_id", args.ad_group_id))
    return api._fetch_all("/ads", params, max_items=args.max_items)


def cmd_ads(args) -> None:
    rows = drop_archived(_ads_for(args, include_issues=args.include_issues), args.status, args.all)
    if args.review_status:
        rows = [r for r in rows if r.get("review_status") == args.review_status]

    def human(items):
        print_table([[a.get("id"), trunc(a.get("name"), args, 30), a.get("status"), a.get("review_status"),
                      (a.get("creative") or {}).get("type"), trunc((a.get("creative") or {}).get("title"), args, 30),
                      trunc((a.get("creative") or {}).get("target_url"), args, 34), _truncate(issues_str(a), 36)]
                     for a in items],
                    ["ID", "Name", "Status", "Review", "Type", "Title", "URL", "Issues"])
        print(f"\n{len(items)} ad(s)" + ("" if args.all or args.status else " (archived hidden — use --all)"))

    emit(rows, args, human)


def cmd_ad_detail(args) -> None:
    a = api._api_call("GET", f"/ads/{args.ad_id}", [(qarr("include"), "serving_issues")])

    def human(a):
        cr = a.get("creative") or {}
        rv = a.get("review") or {}
        print(f"Ad {a.get('id')} — {a.get('name')}   status {a.get('status')}   review {a.get('review_status')}")
        print(f"  creative: {cr.get('type')}")
        print(f"    title:  {cr.get('title')}")
        print(f"    body:   {cr.get('body')}")
        if cr.get("price"):
            print(f"    price:  {cr.get('price')}")
        print(f"    url:    {cr.get('target_url')}")
        print(f"    image:  file {cr.get('file_id')}  {cr.get('image_url') or ''}" + (f"  crop {cr.get('image_crop')}" if cr.get("image_crop") else ""))
        if rv.get("reason") or rv.get("screenshot_url"):
            print(f"  review detail: {rv.get('status')}  reason {rv.get('reason')}  screenshot {rv.get('screenshot_url') or '-'}")
        if a.get("appeal"):
            ap = a["appeal"]
            print(f"  appeal: {ap.get('status')} requested {fmt_ts(ap.get('requested_at'))} resolved {fmt_ts(ap.get('resolved_at'))}")
        if a.get("landing_page_configuration"):
            print(f"  landing page config: {a['landing_page_configuration']}")
        print(f"  serving issues: {issues_str(a) or 'none'}")
        print(f"  created {fmt_ts(a.get('created_at'))}  updated {fmt_ts(a.get('updated_at'))}")

    emit(a, args, human)


def cmd_ad_review(args) -> None:
    """Ads that are not approved or have serving issues (the review-check scenario)."""
    if args.ad_id:
        rows = [api._api_call("GET", f"/ads/{args.ad_id}", [(qarr("include"), "serving_issues")])]
    else:
        args.include_issues = True
        rows = drop_archived(_ads_for(args), None)
    def real_issues(a):
        return [i for i in (a.get("serving_issues") or []) if (i.get("code") if isinstance(i, dict) else i) not in PAUSED_CODES]

    flagged = [a for a in rows if a.get("review_status") != "approved" or real_issues(a) or a.get("appeal")]
    paused_only = [a for a in rows if a not in flagged and a.get("serving_issues")]

    def human(items):
        if not items:
            print(f"✅ All {len(rows)} ad(s) approved, no serving issues"
                  + (f" ({len(paused_only)} not serving only because the campaign/ad group/ad is paused)." if paused_only else "."))
            return
        waiting = [a for a in items if a.get("review_status") == "in_review" and not real_issues(a) and not a.get("appeal")]
        problems = [a for a in items if a not in waiting]
        if problems:
            print(f"Problems ({len(problems)}) — rejected / serving issues / appeals:")
            print_table([[a.get("id"), _truncate(a.get("name"), 28), a.get("status"), a.get("review_status"),
                          (a.get("review") or {}).get("reason") or "", _truncate(issues_str(a), 50),
                          (a.get("appeal") or {}).get("status") or ""] for a in problems],
                        ["ID", "Name", "Status", "Review", "Reason", "Serving issues", "Appeal"])
        if waiting:
            print(f"\nWaiting for review ({len(waiting)}) — normal for minutes after create/edit:")
            for a in waiting:
                print(f"  {a.get('id')}  {_truncate(a.get('name'), 40)}  [{a.get('status')}]")
        print(f"\n{len(problems)} problem(s), {len(waiting)} in review, {len(rows) - len(items)} fine. "
              "Rejected ads: edit the creative (ad-update) → re-review runs automatically.")
        if any((a.get("review") or {}).get("reason", "").startswith(("crawler", "crawl", "robots", "landing", "missing_favicon")) for a in items):
            print("Landing-page reasons: run `landing-check --url <target_url>` to see what the crawler hits.")

    emit(flagged, args, human)


def _crop_from_arg(value: str | None) -> dict | None:
    if not value:
        return None
    parts = value.split(",")
    if len(parts) != 4:
        _die("ERROR: --crop format is x,y,width,height as fractions 0–1 (square: width==height).")
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError:
        _die("ERROR: --crop values must be numbers.")
    return {"x": x, "y": y, "width": w, "height": h}


def _creative_from_args(args, current: dict | None = None) -> dict:
    cr: dict = {}
    if current:
        for k in ("type", "title", "body", "price", "target_url", "file_id", "image_crop"):
            if current.get(k) is not None:
                cr[k] = current[k]
    if getattr(args, "creative_json", None):
        cr.update(parse_json_arg(args.creative_json, "--creative-json"))
    if getattr(args, "type", None):
        cr["type"] = args.type
    cr.setdefault("type", "chat_card")
    for flag, key in (("title", "title"), ("body", "body"), ("price", "price"), ("target_url", "target_url"),
                      ("file_id", "file_id")):
        val = getattr(args, flag, None)
        if val is not None:
            cr[key] = val
    crop = _crop_from_arg(getattr(args, "crop", None))
    if crop:
        cr["image_crop"] = crop
    if cr.get("type") == "product_ad_template":
        cr.pop("file_id", None)
        cr.pop("image_crop", None)
        cr.pop("target_url", None)
        cr.setdefault("title", "{{product.title}}")
        cr.setdefault("body", "{{product.body}}")
    return cr


def cmd_ad_create(args) -> None:
    findings: list = []
    lint.lint_name(args.name, "Ad", findings)
    creative = _creative_from_args(args)
    if args.image_url and args.image_file:
        _die("ERROR: give --image-url or --image-file, not both.")
    pending_upload = (args.image_url or args.image_file) and not creative.get("file_id")
    if pending_upload:
        creative["file_id"] = "<uploaded on --confirm>"
    lint.lint_creative(creative, findings)
    if creative.get("type") == "product_ad_template":
        group = api._api_call("GET", f"/ad_groups/{args.ad_group_id}")
        existing = [a for a in api._fetch_all("/ads", [("ad_group_id", args.ad_group_id)])
                    if (a.get("creative") or {}).get("type") == "product_ad_template" and a.get("status") != "archived"]
        if existing:
            findings.append(("error", f"ad group already has a non-archived product_ad_template ({existing[0]['id']}); max one."))
        if not group.get("product_set") and not args.force:
            findings.append(("warn", "ad group has no product_set — it inherits the campaign feed (fine for product_feed campaigns)."))
    if args.status == "active":
        findings.append(("warn", "Creating the ad ACTIVE (default paused) — it serves once approved and parents are active."))
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    body = {"ad_group_id": args.ad_group_id, "name": args.name, "status": args.status, "creative": creative}
    if args.query_string_template:
        body["landing_page_configuration"] = {"query_string_template": args.query_string_template}
    if not args.confirm:
        print_plan("POST", "/ads", body, args,
                   note=("--confirm uploads the image first, then creates the ad. " if pending_upload else "")
                        + "Review starts automatically (typically minutes); check with ad-review.")
        return
    if pending_upload:
        creative["file_id"] = upload_image(url=args.image_url, path=args.image_file)["file_id"]
        _err(f"Image uploaded: file_id {creative['file_id']}")
    resp = run_write("POST", "/ads", body, args, "", create=True)
    if resp is not None and not args.json:
        print(f"Ad created: {resp.get('id')} \"{resp.get('name')}\" status {resp.get('status')} review {resp.get('review_status')}.")


def cmd_ad_update(args) -> None:
    findings: list = []
    body: dict = {}
    current = api._api_call("GET", f"/ads/{args.ad_id}")
    if args.name is not None:
        lint.lint_name(args.name, "Ad", findings)
        body["name"] = args.name
    if args.status:
        body["status"] = args.status
    creative_flags = ("type", "title", "body", "price", "target_url", "file_id", "crop", "creative_json", "image_url", "image_file")
    if any(getattr(args, f, None) for f in creative_flags):
        creative = _creative_from_args(args, current.get("creative"))
        pending_upload = (args.image_url or args.image_file) and not args.file_id
        if pending_upload:
            creative["file_id"] = "<uploaded on --confirm>"
        lint.lint_creative(creative, findings)
        body["creative"] = creative
        findings.append(("warn", "Changing the creative re-triggers review; the ad may stop serving until re-approved."))
    else:
        pending_upload = False
    if args.query_string_template is not None:
        body["landing_page_configuration"] = {"query_string_template": args.query_string_template} if args.query_string_template else None
    if not body:
        _die("ERROR: nothing to update.")
    if body.get("status") == "archived":
        findings.append(("warn", "status=archived is IRREVERSIBLE. Prefer ad-archive."))
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    if not args.confirm:
        print_plan("POST", f"/ads/{args.ad_id}", body, args, note="creative is sent as the full merged object.")
        return
    if pending_upload:
        body["creative"]["file_id"] = upload_image(url=args.image_url, path=args.image_file)["file_id"]
        _err(f"Image uploaded: file_id {body['creative']['file_id']}")
    run_write("POST", f"/ads/{args.ad_id}", body, args, f"Ad {args.ad_id} updated.", idempotent=True,
              verify_path=f"/ads/{args.ad_id}")


def cmd_ad_preview(args) -> None:
    resp = api._api_call("POST", f"/ads/{args.ad_id}/preview", idempotent=True)
    items = resp.get("data") or []
    html = items[0].get("body", "") if items else ""
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(html if html.lstrip().lower().startswith("<!doctype") or "<html" in html.lower()
                    else f"<!doctype html><html><body style='margin:0;background:#f5f5f5'>{html}</body></html>")
        if not args.json:
            print(f"Preview written to {args.out} (expires ~24 h). Open it in a browser.")
            return
    if args.json:
        emit(resp, args)
    else:
        print(html or "(empty preview)")


def cmd_ad_activate(args) -> None:
    state_change("Ad", "/ads", args.ad_id, "activate", args)


def cmd_ad_pause(args) -> None:
    state_change("Ad", "/ads", args.ad_id, "pause", args)


def cmd_ad_archive(args) -> None:
    state_change("Ad", "/ads", args.ad_id, "archive", args)
