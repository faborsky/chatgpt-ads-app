"""Commands: business-agents, business-agent-detail/create/update/preview/publish, business-agent-tools.

Business Agents are undocumented in the public guides but present in the OpenAPI spec (2.3.0):
a branded conversational agent that can be attached to a campaign (mode=business_agent)."""

from __future__ import annotations

from oaiads import api, lint
from oaiads.formatting import _die, _err, _output_json, fmt_ts, print_table, _truncate
from oaiads.commands.common import emit, parse_csv, parse_json_arg, print_plan, run_write

INSTRUCTIONS_MAX = 4000
DESCRIPTION_MAX = 300
NAME_MAX = 50


def cmd_business_agents(args) -> None:
    data = api._api_call("GET", "/business_agents")
    rows = data.get("data", data) if isinstance(data, dict) else data
    emit(rows, args, lambda items: print_table(
        [[a.get("id"), _truncate(a.get("name"), 28), a.get("status"), len(a.get("tools") or []), len(a.get("product_feed_ids") or []),
          a.get("lead_form_id") or "", "yes" if a.get("has_pending_changes") else "no", fmt_ts(a.get("published_at"))[:10]]
         for a in items],
        ["ID", "Name", "Status", "Tools", "Feeds", "Lead form", "Pending", "Published"]))


def cmd_business_agent_detail(args) -> None:
    emit(api._api_call("GET", f"/business_agents/{args.business_agent_id}"), args, lambda a: _output_json(a))


def cmd_business_agent_tools(args) -> None:
    data = api._api_call("GET", "/business_agent_tools")
    emit(data.get("data", []), args, lambda items: print_table(
        [[t.get("id"), t.get("type"), t.get("name"), _truncate(t.get("description"), 60)] for t in items],
        ["Tool ID", "Type", "Name", "Description"]))


def _agent_body(args, current: dict | None = None) -> dict:
    findings: list = []
    body: dict = {}
    cur = current or {}
    name = args.name if args.name is not None else cur.get("name")
    instructions = args.instructions if args.instructions is not None else cur.get("instructions")
    if args.instructions_file:
        with open(args.instructions_file, encoding="utf-8") as f:
            instructions = f.read().strip()
    if not name or len(name) > NAME_MAX:
        findings.append(("error", f"--name is required (1–{NAME_MAX} chars)."))
    if not instructions or len(instructions) > INSTRUCTIONS_MAX:
        findings.append(("error", f"--instructions / --instructions-file required (1–{INSTRUCTIONS_MAX} chars)."))
    body["name"], body["instructions"] = name, instructions
    desc = args.description if args.description is not None else cur.get("description")
    if desc:
        if len(desc) > DESCRIPTION_MAX:
            findings.append(("error", f"description max {DESCRIPTION_MAX} chars."))
        body["description"] = desc
    if args.privacy_url is not None:
        lint.lint_url(args.privacy_url, findings, "privacy_policy_url")
        body["privacy_policy_url"] = args.privacy_url
    elif cur.get("privacy_policy_url"):
        body["privacy_policy_url"] = cur["privacy_policy_url"]
    starters = []
    for s in args.starter or []:
        starters += [s] if not s.startswith("@") else []
    if args.starter is None and cur.get("conversation_starters"):
        starters = cur["conversation_starters"]
    if len(starters) > 12:
        findings.append(("error", "max 12 conversation starters."))
    if starters:
        body["conversation_starters"] = starters
    feeds = parse_csv(args.feed_ids) if args.feed_ids is not None else cur.get("product_feed_ids")
    if feeds:
        body["product_feed_ids"] = feeds
    tools = parse_csv(args.tools) if args.tools is not None else cur.get("tools")
    if tools:
        body["tools"] = tools
    if args.connector_ids:
        body["connector_ids"] = parse_csv(args.connector_ids)
    if args.lead_form_id == "":
        body["lead_form"] = None
    elif args.lead_form_id:
        rev = args.lead_form_revision_id
        if not rev:
            rev = api._api_call("GET", f"/lead_forms/{args.lead_form_id}").get("published_revision_id")
            if not rev:
                findings.append(("error", "lead form has no published revision — publish it first."))
        body["lead_form"] = {"lead_form_id": args.lead_form_id, "lead_form_revision_id": rev}
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    return body


def cmd_business_agent_create(args) -> None:
    body = _agent_body(args)
    resp = run_write("POST", "/business_agents", body, args, "", idempotent=False, note="Creates a DRAFT; publish with business-agent-publish.")
    if resp is not None and not args.json:
        print(f"Business agent draft created: {resp.get('id')} \"{resp.get('name')}\" status {resp.get('status')}.")


def cmd_business_agent_update(args) -> None:
    current = api._api_call("GET", f"/business_agents/{args.business_agent_id}")
    body = _agent_body(args, current)
    run_write("POST", f"/business_agents/{args.business_agent_id}", body, args,
              f"Business agent {args.business_agent_id} draft updated.", idempotent=True,
              note="Full replace: omitted optional fields reset to defaults (lead_form is kept unless --lead-form-id '' unlinks it).")


def cmd_business_agent_preview(args) -> None:
    messages = []
    for m in args.message or []:
        role, _, content = m.partition(":")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
        else:
            messages.append({"role": "user", "content": m})
    if not (1 <= len(messages) <= 10):
        _die("ERROR: give 1–10 --message values (optionally prefixed user:/assistant:).")
    resp = api._api_call("POST", f"/business_agents/{args.business_agent_id}/preview", json_body={"messages": messages}, idempotent=True)
    emit(resp, args, lambda r: print(f"[{(r.get('message') or {}).get('role')}] {(r.get('message') or {}).get('content')}"))


def cmd_business_agent_publish(args) -> None:
    run_write("POST", f"/business_agents/{args.business_agent_id}/publish", None, args,
              f"Business agent {args.business_agent_id} published.", idempotent=True,
              note="Publishing makes the current draft live for campaigns in mode=business_agent.")
