"""Command: plan-apply — build a whole campaign tree from ONE JSON plan.

campaign → ad groups (hints, bid, UTM) → ads (shared or per-ad image). Dry-run (default) lints
everything and prints the tree; nothing is sent. --confirm creates objects sequentially, each with
its own Idempotency-Key, and records progress in <plan>.state.json so an interrupted run resumes
(objects already created are skipped, keys are reused). Example plan: docs/plan-example.json.
"""

from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal

from oaiads import api, lint
from oaiads.commands.common import ARCHIVABLE_STATUSES  # noqa: F401  (kept for symmetry with state_change)
from oaiads.commands.common import money_flag, parse_time_to_unix
from oaiads.commands.files import upload_image
from oaiads.formatting import _die, _err, _output_json, amount_to_micros, fmt_money

PLAN_DOC = "docs/plan-example.json"


# ---------------------------------------------------------------------------
# Plan loading & state
# ---------------------------------------------------------------------------

def _load_plan(path: str) -> tuple[dict, str]:
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        _die(f"ERROR: cannot read plan {path}: {e}")
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"ERROR: plan is not valid JSON ({e}).")
    if not isinstance(plan, dict) or "campaign" not in plan or not isinstance(plan.get("ad_groups"), list):
        _die(f"ERROR: plan needs a 'campaign' object and an 'ad_groups' list (see {PLAN_DOC}).")
    return plan, hashlib.sha256(raw.encode()).hexdigest()[:16]


def _state_path(plan_path: str, override: str | None) -> str:
    return override or (os.path.splitext(plan_path)[0] + ".state.json")


def _load_state(path: str) -> dict:
    state = api._read_json(path, None)
    if not isinstance(state, dict):
        state = {}
    state.setdefault("created", {"files": {}, "campaign": None, "ad_groups": {}, "ads": {}})
    state.setdefault("keys", {"campaign": None, "ad_groups": {}, "ads": {}})
    state.setdefault("log", [])
    return state


def _save_state(path: str, state: dict) -> None:
    api._write_json_atomic(path, state)


def _resolve(base_dir: str, p: str | None) -> str | None:
    if not p:
        return None
    return p if os.path.isabs(p) else os.path.join(base_dir, p)


# ---------------------------------------------------------------------------
# Builders (plan dict → API bodies), sharing the CLI's lint rules
# ---------------------------------------------------------------------------

def _campaign_body(c: dict, findings: list) -> dict | None:
    if c.get("id"):
        return None  # attach to an existing campaign
    lint.lint_name(c.get("name"), "Campaign", findings)
    budget: dict = {}
    if c.get("lifetime_budget") is not None:
        budget["lifetime_spend_limit_micros"] = money_flag(str(c["lifetime_budget"]), "campaign.lifetime_budget", lint.BUDGET_MIN_MICROS)
    if c.get("daily_budget") is not None:
        budget["daily_spend_limit_micros"] = money_flag(str(c["daily_budget"]), "campaign.daily_budget", lint.BUDGET_MIN_MICROS)
    lint.lint_budget(budget or None, findings)
    start = parse_time_to_unix(str(c["start"]), "campaign.start") if c.get("start") else None
    end = parse_time_to_unix(str(c["end"]), "campaign.end") if c.get("end") else None
    lint.lint_times(start, end, findings)
    body: dict = {"name": c.get("name"), "status": c.get("status", "paused"), "budget": budget}
    if body["status"] not in ("active", "paused"):
        findings.append(("error", "campaign.status must be active|paused."))
    for k in ("description", "bidding_type", "objective", "billing_event_type", "mode", "product_feed_id", "business_agent_id"):
        if c.get(k) is not None:
            body[k] = c[k]
    if start:
        body["start_time"] = start
    if end:
        body["end_time"] = end
    else:
        findings.append(("warn", "campaign has no end date — with no spend-limit windows on self-serve accounts, an end_time is the fuse."))
    ids = c.get("conversion_event_setting_ids") or []
    if isinstance(ids, str):
        ids = [ids]
    if ids:
        body["conversion_event_setting_ids"] = list(ids)
    if body.get("bidding_type") == "conversions" and len(ids) != 1:
        findings.append(("error", "bidding_type=conversions needs exactly one conversion_event_setting_id."))
    if body.get("bidding_type") != "conversions" and not ids:
        findings.append(("warn", "no conversion_event_setting_ids — the campaign will report clicks only (link event settings)."))
    if c.get("targeting") is not None:
        body["targeting"] = c["targeting"]
    else:
        t: dict = {}
        if c.get("countries"):
            t.setdefault("locations", {})["countries"] = [str(x).upper() for x in c["countries"]]
        if c.get("location_ids"):
            t.setdefault("locations", {})["include"] = [{"id": str(i)} for i in c["location_ids"]]
        if c.get("exclude_location_ids"):
            t["excluded_locations"] = {"include": [{"id": str(i)} for i in c["exclude_location_ids"]]}
        if c.get("audience_ids"):
            t["custom_audiences"] = {"ids": list(c["audience_ids"])}
        if c.get("exclude_audience_ids"):
            t["excluded_custom_audiences"] = {"ids": list(c["exclude_audience_ids"])}
        if c.get("platforms"):
            t["platforms"] = {"included": list(c["platforms"])}
        if t:
            body["targeting"] = t
        else:
            findings.append(("warn", "campaign has no location targeting — it can serve in ALL available locations."))
    if c.get("query_string_template"):
        body["landing_page_configuration"] = {"query_string_template": c["query_string_template"]}
    if body["status"] == "active":
        findings.append(("warn", "campaign.status=active — everything created active will serve as soon as review passes."))
    return body


def _adgroup_body(g: dict, defaults: dict, campaign_bidding_type: str | None, base_dir: str, findings: list, label: str) -> dict:
    d = {**(defaults or {}), **g}
    lint.lint_name(d.get("name"), f"Ad group {label}", findings)
    bc: dict = {}
    billing = d.get("billing_event")
    if not billing:
        billing = "impression" if campaign_bidding_type == "impressions" else ("click" if campaign_bidding_type in ("clicks", "conversions") else None)
    if not billing:
        findings.append(("error", f"ad group {label}: billing_event (impression|click) is required when the campaign bidding type is unknown."))
    bc["billing_event_type"] = billing
    if d.get("max_bid") is not None and d.get("max_cpm") is not None:
        findings.append(("error", f"ad group {label}: give max_bid OR max_cpm, not both."))
    if d.get("max_cpm") is not None:
        bc["max_bid_micros"] = int(amount_to_micros(str(d["max_cpm"])) / 1000)
    if d.get("max_bid") is not None:
        bc["max_bid_micros"] = money_flag(str(d["max_bid"]), f"ad group {label}.max_bid", 1)
    if d.get("strategy"):
        bc["strategy"] = d["strategy"]
    if not bc.get("max_bid_micros") and bc.get("strategy", "fixed_bid") == "fixed_bid":
        findings.append(("error", f"ad group {label}: max_bid (or max_cpm) is required for fixed_bid."))
    if d.get("audience_multipliers"):
        bc["custom_audience_bid_multipliers"] = [
            {"custom_audience_id": aid, "bid_multiplier_micros": int(Decimal(str(m)) * 1_000_000)}
            for aid, m in dict(d["audience_multipliers"]).items()]
    if d.get("bidding_config"):
        bc = d["bidding_config"]
    hints: list[str] = list(d.get("hints") or [])
    hf = _resolve(base_dir, d.get("hints_file"))
    if hf:
        try:
            with open(hf, encoding="utf-8") as f:
                hints += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        except OSError as e:
            findings.append(("error", f"ad group {label}: cannot read hints_file {hf}: {e}"))
    lint.lint_context_hints(hints, findings)
    body: dict = {"name": d.get("name"), "status": d.get("status", "paused"), "bidding_config": bc}
    if d.get("description"):
        body["description"] = d["description"]
    if hints:
        body["context_hints"] = hints
    if d.get("product_set"):
        body["product_set"] = d["product_set"]
    if d.get("query_string_template"):
        body["landing_page_configuration"] = {"query_string_template": d["query_string_template"]}
    return body


def _ad_body(a: dict, defaults: dict, shared_image: dict | None, base_dir: str, findings: list, label: str) -> tuple[dict, dict | None]:
    """Returns (body, pending_upload) — pending_upload = {"file": path} | {"url": u} to resolve on --confirm."""
    d = {**(defaults or {}), **a}
    if not d.get("name"):
        # Ad names are internal — derive one so plans stay short: "<group/key> · <title>"
        d["name"] = f"{label} · {d.get('title') or 'ad'}"[:200]
    lint.lint_name(d.get("name"), f"Ad {label}", findings)
    creative: dict = {"type": d.get("type", "chat_card")}
    for k in ("title", "body", "price", "target_url", "file_id"):
        if d.get(k) is not None:
            creative[k] = d[k]
    if d.get("crop"):
        x, y, w, h = d["crop"]
        creative["image_crop"] = {"x": x, "y": y, "width": w, "height": h}
    pending = None
    if creative["type"] == "chat_card" and not creative.get("file_id"):
        if d.get("image_file"):
            pending = {"file": _resolve(base_dir, d["image_file"])}
        elif d.get("image_url"):
            pending = {"url": d["image_url"]}
        elif shared_image:
            pending = shared_image
        if pending:
            creative["file_id"] = "<uploaded on --confirm>"
            if pending.get("file") and not os.path.isfile(pending["file"]):
                findings.append(("error", f"ad {label}: image file not found: {pending['file']}"))
    if creative["type"] == "product_ad_template":
        creative.pop("file_id", None)
        creative.pop("target_url", None)
        creative.setdefault("title", "{{product.title}}")
        creative.setdefault("body", "{{product.body}}")
    lint.lint_creative(creative, findings)
    body: dict = {"name": d.get("name"), "status": d.get("status", "paused"), "creative": creative}
    if d.get("query_string_template"):
        body["landing_page_configuration"] = {"query_string_template": d["query_string_template"]}
    return body, pending


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

def cmd_plan_apply(args) -> None:
    plan, sha = _load_plan(args.file)
    base_dir = os.path.dirname(os.path.abspath(args.file))
    state_path = _state_path(args.file, args.state)
    state = _load_state(state_path)
    if state.get("plan_sha") and state["plan_sha"] != sha:
        _err(f"⚠ plan changed since the last run (state {state_path} was written for another version) — "
             "already-created objects are kept, new/changed ones are created as-is.")
    findings: list = []

    c = plan["campaign"]
    defaults = plan.get("defaults") or {}
    campaign_id = c.get("id") or state["created"].get("campaign")
    campaign_body = _campaign_body(c, findings)
    campaign_bidding_type = c.get("bidding_type") or ("impressions" if not c.get("id") else None)
    if c.get("id") and not state["created"].get("campaign"):
        existing = api._api_call("GET", f"/campaigns/{c['id']}")
        campaign_bidding_type = existing.get("bidding_type")

    shared_image = None
    if plan.get("image_file"):
        shared_image = {"file": _resolve(base_dir, plan["image_file"])}
        if not os.path.isfile(shared_image["file"]):
            findings.append(("error", f"shared image_file not found: {shared_image['file']}"))
    elif plan.get("image_url"):
        shared_image = {"url": plan["image_url"]}

    groups = []
    seen_keys = set()
    for i, g in enumerate(plan["ad_groups"]):
        key = str(g.get("key") or i)
        if key in seen_keys:
            findings.append(("error", f"duplicate ad group key '{key}'."))
        seen_keys.add(key)
        gbody = _adgroup_body(g, defaults.get("ad_group"), campaign_bidding_type, base_dir, findings, key)
        ads = []
        for j, a in enumerate(g.get("ads") or []):
            akey = f"{key}/{a.get('key') or j}"
            abody, pending = _ad_body(a, defaults.get("ad"), shared_image, base_dir, findings, akey)
            ads.append({"key": akey, "body": abody, "pending": pending})
        if not ads:
            findings.append(("warn", f"ad group '{key}' has no ads — it cannot serve."))
        groups.append({"key": key, "body": gbody, "ads": ads})
    if not groups:
        findings.append(("error", "plan has no ad_groups."))

    n_ads = sum(len(g["ads"]) for g in groups)
    n_writes = (0 if campaign_id else 1) + len([g for g in groups if g["key"] not in state["created"]["ad_groups"]]) + \
               len([a for g in groups for a in g["ads"] if a["key"] not in state["created"]["ads"]])
    tree = {
        "campaign": ({"existing_id": campaign_id} if campaign_id else campaign_body),
        "ad_groups": [{"key": g["key"], "created_id": state["created"]["ad_groups"].get(g["key"]), "body": g["body"],
                       "ads": [{"key": a["key"], "created_id": state["created"]["ads"].get(a["key"]), "body": a["body"]} for a in g["ads"]]}
                      for g in groups],
        "shared_image": shared_image, "writes_remaining": n_writes, "state_file": state_path,
    }
    errors = lint.report(findings)
    if errors:
        _die("Lint errors — fix the plan first (nothing was sent).")

    if not args.confirm:
        if args.json:
            _output_json({"executed": False, "plan": tree, "findings": [{"level": l, "message": m} for l, m in findings]})
        else:
            cur = api.cached_currency()
            print(f"PLAN {os.path.basename(args.file)} — dry-run, nothing sent. {n_writes} write(s) remaining "
                  f"({len(groups)} ad group(s), {n_ads} ad(s)); state: {state_path}")
            if campaign_id:
                print(f"campaign: attach to existing {campaign_id}")
            else:
                b = campaign_body
                budget = b["budget"]
                money = " ".join(f"{k.split('_')[0]} {fmt_money(v, cur)}" for k, v in budget.items())
                print(f"campaign: \"{b['name']}\" [{b['status']}] {b.get('bidding_type', 'impressions')} {money} "
                      f"targeting={json.dumps(b.get('targeting'), ensure_ascii=False)} end={b.get('end_time')} "
                      f"events={b.get('conversion_event_setting_ids')}")
            for g in groups:
                gb = g["body"]
                bc = gb["bidding_config"]
                done = " ✓" if state["created"]["ad_groups"].get(g["key"]) else ""
                print(f"  ├─ [{g['key']}]{done} \"{gb['name']}\" [{gb['status']}] {bc.get('billing_event_type')} "
                      f"{fmt_money(bc.get('max_bid_micros'), cur) if bc.get('max_bid_micros') else bc.get('strategy')}  "
                      f"hints {len(gb.get('context_hints') or [])}  utm={((gb.get('landing_page_configuration') or {}).get('query_string_template'))}")
                for a in g["ads"]:
                    cr = a["body"]["creative"]
                    adone = " ✓" if state["created"]["ads"].get(a["key"]) else ""
                    print(f"  │    [{a['key']}]{adone} \"{cr.get('title')}\" ({len(cr.get('title') or '')}) / "
                          f"\"{cr.get('body')}\" ({len(cr.get('body') or '')}) → {cr.get('target_url')}  img={cr.get('file_id')}")
            print("Add --confirm to create everything above (sequentially, idempotent, resumable).")
        return

    # ----- execute --------------------------------------------------------
    state["plan_sha"] = sha
    created = state["created"]
    keys = state["keys"]

    def log(msg: str) -> None:
        state["log"].append(msg)
        _save_state(state_path, state)
        if not args.json:
            print(msg)

    def ensure_file(pending: dict | None) -> str | None:
        if not pending:
            return None
        cache_key = pending.get("file") or pending.get("url")
        if cache_key in created["files"]:
            return created["files"][cache_key]
        resp = upload_image(url=pending.get("url"), path=pending.get("file"))
        created["files"][cache_key] = resp["file_id"]
        log(f"uploaded image {os.path.basename(cache_key)} → {resp['file_id']}")
        return resp["file_id"]

    if not campaign_id:
        keys["campaign"] = keys.get("campaign") or api.new_idempotency_key()
        _save_state(state_path, state)
        resp = api._api_call("POST", "/campaigns", json_body=campaign_body, idempotency_key=keys["campaign"])
        campaign_id = resp.get("id")
        created["campaign"] = campaign_id
        log(f"campaign created {campaign_id} \"{resp.get('name')}\" [{resp.get('status')}]")
    else:
        log(f"campaign: using {campaign_id}")

    for g in groups:
        gid = created["ad_groups"].get(g["key"])
        if not gid:
            keys["ad_groups"][g["key"]] = keys["ad_groups"].get(g["key"]) or api.new_idempotency_key()
            _save_state(state_path, state)
            body = {"campaign_id": campaign_id, **g["body"]}
            resp = api._api_call("POST", "/ad_groups", json_body=body, idempotency_key=keys["ad_groups"][g["key"]])
            gid = resp.get("id")
            created["ad_groups"][g["key"]] = gid
            log(f"  ad group [{g['key']}] created {gid} \"{resp.get('name')}\"")
        for a in g["ads"]:
            if created["ads"].get(a["key"]):
                continue
            body = {"ad_group_id": gid, **a["body"]}
            if a["pending"]:
                body["creative"]["file_id"] = ensure_file(a["pending"])
            keys["ads"][a["key"]] = keys["ads"].get(a["key"]) or api.new_idempotency_key()
            _save_state(state_path, state)
            resp = api._api_call("POST", "/ads", json_body=body, idempotency_key=keys["ads"][a["key"]])
            created["ads"][a["key"]] = resp.get("id")
            log(f"    ad [{a['key']}] created {resp.get('id')} review {resp.get('review_status')}")

    _save_state(state_path, state)
    if args.json:
        _output_json({"executed": True, "created": created, "state_file": state_path})
    else:
        print(f"Done: campaign {campaign_id}, {len(created['ad_groups'])} ad group(s), {len(created['ads'])} ad(s). "
              f"State: {state_path}. Next: ad-review --campaign-id {campaign_id} (review takes minutes), then activate bottom-up.")
