"""Commands: feeds, feed-create, feed-archive, feed-uploads, feed-products, feed-products-patch,
feed-sftp, feed-sftp-create, feed-sftp-activate, feed-sftp-pause."""

from __future__ import annotations

from oaiads import api
from oaiads.formatting import _die, _err, _output_json, print_table, _truncate
from oaiads.commands.common import emit, parse_csv, parse_json_arg, print_plan, qarr, run_write

AVAILABILITY = ["in_stock", "out_of_stock"]


def cmd_feeds(args) -> None:
    params = [(qarr("include"), "product_count")] if args.with_counts else []
    rows = api._fetch_all("/feeds", params, max_items=args.max_items)
    emit(rows, args, lambda items: print_table(
        [[f.get("feed_id"), _truncate(f.get("name"), 30), ",".join(f.get("countries") or []), ",".join(f.get("currencies") or []),
          f.get("product_count", ""), f.get("campaign_count", ""), "yes" if f.get("sftp_configured") else "no",
          "yes" if f.get("hosted_url_configured") else "no", (f.get("updated_at") or "")[:10]] for f in items],
        ["Feed ID", "Name", "Countries", "Currencies", "Products", "Campaigns", "SFTP", "Hosted URL", "Updated"]))


def cmd_feed_create(args) -> None:
    body: dict = {"name": args.name}
    if args.countries:
        body["countries"] = [c.upper() for c in parse_csv(args.countries)]
    resp = run_write("POST", "/feeds", body, args, "", idempotent=False,
                     note="Creates the feed shell; the catalog itself goes in via SFTP (feed-sftp-create) or Ads Manager.")
    if resp is not None and not args.json:
        print(f"Feed created: {resp.get('feed_id')} \"{resp.get('name')}\". Next: feed-sftp-create --feed-id {resp.get('feed_id')} …")


def cmd_feed_archive(args) -> None:
    path = f"/feeds/{args.feed_id}/archive"
    if not args.confirm:
        print_plan("POST", path, None, args, note="Archiving a feed is permanent; product_feed campaigns using it stop serving.")
        return
    run_write("POST", path, None, args, f"Feed {args.feed_id} archived.", idempotent=True)


def cmd_feed_uploads(args) -> None:
    params = [("limit", min(max(args.limit, 1), 100))]
    if args.paginate:
        params.append(("paginate", "true"))
    data = api._api_call("GET", "/feeds/uploads", params)
    rows = data.get("uploads") or data.get("latest_uploads") or []
    if data.get("truncated"):
        _err("⚠ upload list truncated by the API; use --paginate for cursors.")

    def human(items):
        table = []
        for u in items:
            diag = "; ".join(f"{d.get('severity')}:{d.get('code')}({d.get('rows_affected')})" for d in (u.get("diagnostics") or [])[:3])
            table.append([u.get("feed_id"), u.get("upload_id"), u.get("status"), (u.get("uploaded_at") or "")[:19],
                          u.get("rows_accepted"), u.get("rows_rejected"), u.get("rows_ads_eligible"), _truncate(diag, 60)])
        print_table(table, ["Feed", "Upload", "Status", "Uploaded", "Accepted", "Rejected", "Ads-eligible", "Diagnostics"])
        if any(u.get("rows_ads_eligible") in (0, None) for u in items):
            print("\nℹ 0 ads-eligible rows usually means is_ads_eligible=true is missing in the catalog.")

    emit(rows, args, human)


def cmd_feed_products(args) -> None:
    body: dict = {"limit": min(max(args.limit, 1), 500)}
    filters = []
    for spec in args.filter or []:
        parts = spec.split(":", 2)
        if len(parts) != 3:
            _die("ERROR: --filter format is field:operator:value1|value2")
        filters.append({"field": parts[0], "operator": parts[1], "values": [v for v in parts[2].split("|") if v]})
    if filters:
        body["filters"] = filters
    if args.after:
        body["after"] = args.after
    data = api._api_call("POST", f"/feeds/{args.feed_id}/products/query", json_body=body, idempotent=True)
    rows = data.get("data", [])

    def human(items):
        print_table([[p.get("product_id"), p.get("item_id") or "", _truncate(p.get("title"), 40), p.get("brand") or "",
                      p.get("price") or "", _truncate(p.get("target_url"), 40)] for p in items],
                    ["Product", "Item", "Title", "Brand", "Price", "URL"])
        print(f"\nmatched {data.get('matched_count')} of {data.get('total_count')} products"
              + (f"; more: --after {data.get('last_id')}" if data.get("has_more") else ""))

    emit(rows, args, human)


def cmd_feed_products_patch(args) -> None:
    """PATCH /feeds/{id}/products — delta updates (availability/price/title) for existing variants."""
    if args.products_json:
        products = parse_json_arg(args.products_json, "--products-json")
        if isinstance(products, dict) and "products" in products:
            products = products["products"]
    else:
        if not (args.product_id and args.variant_id):
            _die("ERROR: give --products-json (or @file) or --product-id + --variant-id with --available/--status/--price/--title.")
        variant: dict = {"id": args.variant_id}
        if args.title:
            variant["title"] = args.title
        if args.price is not None:
            if not args.currency:
                _die("ERROR: --currency is required with --price (ISO 4217).")
            variant["price"] = {"amount": int(args.price), "currency": args.currency.upper()}
        avail: dict = {}
        if args.available is not None:
            avail["available"] = args.available == "true"
        if args.availability_status:
            avail["status"] = args.availability_status
        if avail:
            variant["availability"] = avail
        if len(variant) == 1:
            _die("ERROR: nothing to change on the variant.")
        products = [{"id": args.product_id, "variants": [variant]}]
    if not isinstance(products, list) or not products:
        _die("ERROR: products must be a non-empty list.")
    seen = set()
    for p in products:
        for v in p.get("variants") or []:
            key = (p.get("id"), v.get("id"))
            if key in seen:
                _die(f"ERROR: variant {key} repeated in one request.")
            seen.add(key)
            price = v.get("price")
            if price and (not isinstance(price.get("amount"), int) or price["amount"] < 0):
                _die("ERROR: price.amount must be a non-negative integer in MINOR units (8999 = 89.99).")
    resp = run_write("PATCH", f"/feeds/{args.feed_id}/products", {"products": products}, args, "", idempotent=True,
                     note="Delta update; needs delta-feed access on the account (403 product_feed_delta_api_disabled otherwise).")
    if resp is not None and not args.json:
        print(f"Feed {resp.get('id')}: accepted={resp.get('accepted')} — downstream indexing is asynchronous.")
        if not resp.get("accepted"):
            _err("⚠ accepted=false — check ids and fields; the change was not taken.")


def cmd_feed_sftp(args) -> None:
    emit(api._api_call("GET", f"/feeds/{args.feed_id}/sftp_access"), args,
         lambda s: print(f"enabled: {s.get('enabled')}\nconnection: {s.get('connection_uri')}\nauth: {s.get('authentication_method')}"))


def cmd_feed_sftp_create(args) -> None:
    body: dict = {"authentication_method": args.auth_method}
    if args.auth_method == "ssh_key":
        if not args.ssh_public_key:
            _die("ERROR: --ssh-public-key (path or key text) is required for ssh_key.")
        key = args.ssh_public_key
        try:
            with open(key, encoding="utf-8") as f:
                key = f.read().strip()
        except OSError:
            pass
        body["ssh_public_key"] = key
    path = f"/feeds/{args.feed_id}/sftp_access"
    if not args.confirm:
        print_plan("POST", path, body, args, note="Creates OR REPLACES the SFTP credentials — existing uploaders lose access. Password shown once.")
        return
    resp = api._api_call("POST", path, json_body=body, idempotent=False)
    if args.json:
        _output_json(resp)
    else:
        print(f"SFTP access: {resp.get('connection_uri')} ({resp.get('authentication_method')}), enabled={resp.get('enabled')}")
        if resp.get("password"):
            print(f"Password (shown ONCE):\n{resp['password']}")
    _err("⚠ Store the SFTP credentials in a secret manager; this rotated any previous credentials.")


def cmd_feed_sftp_activate(args) -> None:
    run_write("POST", f"/feeds/{args.feed_id}/sftp_access/activate", None, args, "SFTP access activated.", idempotent=True)


def cmd_feed_sftp_pause(args) -> None:
    run_write("POST", f"/feeds/{args.feed_id}/sftp_access/pause", None, args, "SFTP access paused.", idempotent=True)
