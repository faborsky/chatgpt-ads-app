"""Commands: geo-search (GET /geo_lookup/search)."""

from __future__ import annotations

from oaiads import api
from oaiads.formatting import print_table
from oaiads.commands.common import emit


def cmd_geo_search(args) -> None:
    data = api._api_call("GET", "/geo_lookup/search", [("q", args.q), ("limit", min(max(args.limit, 1), 100))])
    rows = data.get("results", [])
    if args.country:
        rows = [r for r in rows if (r.get("country_code") or "").upper() == args.country.upper()]

    def human(items):
        print_table([[r.get("id"), r.get("type"), r.get("name"), r.get("canonical_name"), r.get("country_code"),
                      r.get("region_code") or "", r.get("parent_id") or ""] for r in items],
                    ["Location ID", "Type", "Name", "Canonical", "Country", "Region code", "Parent"])
        print(f"\n{len(items)} of {data.get('count', len(rows))} result(s) for '{args.q}'. "
              "Use ids with campaign-create --location-ids; whole countries via --countries CZ,SK. "
              "Full catalog: https://developers.openai.com/ads/openai-geotargets.csv")

    emit(rows, args, human)
