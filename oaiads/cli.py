"""Argparse wiring + dispatch. Every subcommand is registered by exactly one
_cmd() call that both adds the parser and binds the handler — parser/dispatch
parity by construction."""

from __future__ import annotations

import argparse
import os
import signal
import sys

from oaiads import __version__, api
from oaiads.commands.account import (
    cmd_account, cmd_account_activate, cmd_account_pause, cmd_accounts, cmd_api_key_create, cmd_api_limits,
    cmd_brand_update, cmd_landing_check, cmd_negative_keywords, cmd_negative_keywords_add,
    cmd_negative_keywords_remove, cmd_negative_keywords_set, cmd_spend_limit_create, cmd_spend_limit_delete,
    cmd_spend_limit_update, cmd_spend_limits,
)
from oaiads.commands.adgroups import (
    BILLING_EVENTS, STRATEGIES, cmd_adgroup_activate, cmd_adgroup_archive, cmd_adgroup_create, cmd_adgroup_detail,
    cmd_adgroup_pause, cmd_adgroup_update, cmd_adgroups,
)
from oaiads.commands.ads import (
    CREATIVE_TYPES, REVIEW_STATUSES, cmd_ad_activate, cmd_ad_archive, cmd_ad_create, cmd_ad_detail, cmd_ad_pause,
    cmd_ad_preview, cmd_ad_review, cmd_ad_update, cmd_ads,
)
from oaiads.commands.agents import (
    cmd_business_agent_create, cmd_business_agent_detail, cmd_business_agent_preview, cmd_business_agent_publish,
    cmd_business_agent_tools, cmd_business_agent_update, cmd_business_agents,
)
from oaiads.commands.audiences import (
    IDENTIFIER_TYPES, INTENDED_USES, cmd_audience_add, cmd_audience_archive, cmd_audience_create, cmd_audience_detail,
    cmd_audience_merge, cmd_audience_operation, cmd_audience_remove, cmd_audience_replace, cmd_audiences,
)
from oaiads.commands.bulk import cmd_bulk_job, cmd_bulk_operations, cmd_bulk_submit
from oaiads.commands.campaigns import (
    BIDDING_TYPES, MODES, OBJECTIVES, cmd_campaign_activate, cmd_campaign_archive, cmd_campaign_create,
    cmd_campaign_detail, cmd_campaign_pause, cmd_campaign_update, cmd_campaigns,
)
from oaiads.commands.common import STATUS_CREATE, STATUS_UPDATE
from oaiads.commands.conversions import (
    cmd_capi_key_create, cmd_conversion_check, cmd_conversion_events, cmd_event_setting_create, cmd_event_settings,
    cmd_pixel_create, cmd_pixels,
)
from oaiads.commands.feeds import (
    cmd_feed_archive, cmd_feed_create, cmd_feed_products, cmd_feed_products_patch, cmd_feed_sftp,
    cmd_feed_sftp_activate, cmd_feed_sftp_create, cmd_feed_sftp_pause, cmd_feed_uploads, cmd_feeds,
)
from oaiads.commands.files import cmd_file_upload, cmd_image_upload
from oaiads.commands.insights import (
    GRANULARITIES, INCLUDES, LEVELS, SEGMENTS, cmd_conversion_insights, cmd_insights, cmd_pulse,
)
from oaiads.commands.leads import (
    cmd_lead_form_archive, cmd_lead_form_create, cmd_lead_form_detail, cmd_lead_form_publish, cmd_lead_form_test,
    cmd_lead_form_update, cmd_lead_forms, cmd_lead_sync_create, cmd_lead_sync_delete, cmd_lead_sync_detail,
    cmd_lead_syncs,
)
from oaiads.commands.partner import cmd_partner_data_upload, cmd_partner_data_upload_create
from oaiads.commands.plan import cmd_plan_apply
from oaiads.commands.raw import cmd_raw
from oaiads.commands.targeting import cmd_geo_search

LIST_STATUSES = ["active", "paused", "archived"]


# ---------------------------------------------------------------------------
# Visual signature — humans only (TTY, not --json), so pipes/agents get clean output.
# ---------------------------------------------------------------------------

_ART = [
    " ██████╗██╗  ██╗ █████╗ ████████╗ ██████╗ ██████╗ ████████╗    █████╗ ██████╗ ███████╗",
    "██╔════╝██║  ██║██╔══██╗╚══██╔══╝██╔════╝ ██╔══██╗╚══██╔══╝   ██╔══██╗██╔══██╗██╔════╝",
    "██║     ███████║███████║   ██║   ██║  ███╗██████╔╝   ██║      ███████║██║  ██║███████╗",
    "██║     ██╔══██║██╔══██║   ██║   ██║   ██║██╔═══╝    ██║      ██╔══██║██║  ██║╚════██║",
    "╚██████╗██║  ██║██║  ██║   ██║   ╚██████╔╝██║        ██║      ██║  ██║██████╔╝███████║",
    " ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝        ╚═╝      ╚═╝  ╚═╝╚═════╝ ╚══════╝",
]


def _print_banner() -> None:
    if not sys.stdout.isatty() or "--json" in sys.argv:
        return
    use_color = "NO_COLOR" not in os.environ
    green = "\033[38;5;71m" if use_color else ""
    dim = "\033[2m" if use_color else ""
    bold = "\033[1m" if use_color else ""
    reset = "\033[0m" if use_color else ""
    info = [
        "",
        f"{bold}ChatGPT Ads CLI{reset} v{__version__}",
        f"{dim}reklamy v ChatGPT — kampaně · insights · dry-run zápisy{reset}",
        f"{dim}./run.sh <příkaz> --help{reset}",
        f"{dim}by Jindřich Fáborský · AIFirst.cz{reset}",
        "",
    ]
    for art_line, info_line in zip(_ART, info):
        print(f"{green}{art_line}{reset}   {info_line}")
    print()


def _cmd(sub, name: str, func, help_: str, *, write: bool = False):
    """Add a subcommand; writes get --confirm (default = dry-run) and --idempotency-key."""
    sp = sub.add_parser(name, help=help_ + (" [write]" if write else ""))
    if write:
        sp.add_argument("--confirm", action="store_true", help="Actually send the write (default: dry-run plan only)")
        sp.add_argument("--idempotency-key", help="Reuse a key to retry the SAME request safely (creates get one automatically)")
    sp.add_argument("--json", action="store_true", help="JSON output")
    sp.set_defaults(func=func)
    return sp


def _list_args(sp, *, name_filter: bool = True, issues: bool = True) -> None:
    sp.add_argument("--status", choices=LIST_STATUSES, help="Client-side status filter (archived hidden by default)")
    sp.add_argument("--all", action="store_true", help="Include archived")
    if name_filter:
        sp.add_argument("--name", help="Server-side name filter (min 3 chars)")
    if issues:
        sp.add_argument("--include-issues", action="store_true", help="include[]=serving_issues")
    sp.add_argument("--order", choices=["asc", "desc"])
    sp.add_argument("--wide", action="store_true", help="Do not truncate names/URLs in tables")
    sp.add_argument("--max-items", type=int, default=api.LIST_HARD_CAP, help="Paging cap (default 5000)")


def _targeting_args(sp) -> None:
    sp.add_argument("--countries", help="ISO codes, comma-separated (targeting.locations.countries), e.g. CZ,SK")
    sp.add_argument("--location-ids", help="Location ids from geo-search, comma-separated (max 2500)")
    sp.add_argument("--exclude-location-ids", help="Excluded location ids")
    sp.add_argument("--audience-ids", help="Custom audience ids to INCLUDE (needs ~25k matched users; not EEA/CH)")
    sp.add_argument("--exclude-audience-ids", help="Custom audience ids to EXCLUDE (small audiences OK)")
    sp.add_argument("--platforms", help="Comma: web,ios_app,android_app (default all)")
    sp.add_argument("--targeting-json", help="Raw TargetingParams JSON (or @file) — overrides the flags above")


def _campaign_common_args(sp) -> None:
    sp.add_argument("--description")
    sp.add_argument("--lifetime-budget", help="Lifetime spend limit in ACCOUNT currency (min 1)")
    sp.add_argument("--daily-budget", help="Daily spend limit in ACCOUNT currency (min 1)")
    sp.add_argument("--start", help="Start: YYYY-MM-DD, ISO 8601 or unix seconds (default: now)")
    sp.add_argument("--end", help="End: YYYY-MM-DD, ISO 8601 or unix seconds")
    sp.add_argument("--conversion-event-setting-id", help="Event setting id(s) to link (comma). Reporting link on CPM/CPC; oCPC: exactly one standard setting")
    sp.add_argument("--query-string-template", help="landing_page_configuration.query_string_template (UTM template)")
    _targeting_args(sp)


def _adgroup_common_args(sp) -> None:
    sp.add_argument("--description")
    sp.add_argument("--hints", action="append", help="Context hints, comma-separated (repeatable; max 2000 total)")
    sp.add_argument("--hints-file", help="One context hint per line")
    sp.add_argument("--billing-event", choices=BILLING_EVENTS, help="impression (CPM campaigns) | click (CPC/oCPC)")
    sp.add_argument("--max-bid", help="Max bid PER EVENT in account currency (oCPC: the CPA bid)")
    sp.add_argument("--max-cpm", help="Convenience: max bid per 1 000 impressions (impression billing only)")
    sp.add_argument("--strategy", choices=STRATEGIES)
    sp.add_argument("--audience-multiplier", action="append", help="caud_id=2.0 (0.1–10×, repeatable)")
    sp.add_argument("--product-feed-id", help="product_set.product_feed_id (must match the campaign feed)")
    sp.add_argument("--product-filter", action="append", help="field:operator:v1|v2 (e.g. brand:in:Nike|Adidas, price:lte:100)")
    sp.add_argument("--product-set-json", help="Raw ProductSetParams JSON (or @file)")
    sp.add_argument("--query-string-template")


def _creative_args(sp) -> None:
    sp.add_argument("--type", choices=CREATIVE_TYPES, help="Default chat_card")
    sp.add_argument("--title", help="3–50 chars")
    sp.add_argument("--body", help="≤ 100 chars")
    sp.add_argument("--price", help="Price text (≤ 100) or {{product.price}}")
    sp.add_argument("--target-url", help="Landing page (https). Not for product_ad_template")
    sp.add_argument("--file-id", help="file_id from image-upload")
    sp.add_argument("--image-url", help="Upload this image on --confirm and use its file_id")
    sp.add_argument("--image-file", help="Upload this local image on --confirm and use its file_id")
    sp.add_argument("--crop", help="Square crop x,y,width,height as fractions 0–1 (chat_card)")
    sp.add_argument("--creative-json", help="Raw creative JSON (or @file); flags override its keys")
    sp.add_argument("--query-string-template")


def _insights_args(sp) -> None:
    sp.add_argument("--level", choices=LEVELS, default="account", help="Endpoint scope (default account)")
    sp.add_argument("--object-id", help="campaign/ad group/ad id for --level != account")
    sp.add_argument("--aggregation-level", choices=LEVELS, help="Row entity (default: one level below scope)")
    sp.add_argument("--granularity", choices=GRANULARITIES, default="daily")
    sp.add_argument("--since", help="YYYY-MM-DD (account timezone)")
    sp.add_argument("--until", help="YYYY-MM-DD or 'today' (default yesterday)")
    sp.add_argument("--days", type=int, default=7, help="Window length when --since is omitted (default 7)")
    sp.add_argument("--timezone", help="IANA tz for the date range (default: account timezone)")
    sp.add_argument("--fields", help="Comma-separated canonical fields (default: id, name, status, 6 metrics)")
    sp.add_argument("--filter", action="append", help='JSON, repeatable: {"field":"campaign.id","operator":"IN","value":["cmpn_1"]}')
    sp.add_argument("--sort", action="append", help="field:desc | field:asc | JSON (repeatable)")
    sp.add_argument("--segment", choices=SEGMENTS, help="Extra breakdown (enabled accounts)")
    sp.add_argument("--segment-first", action="store_true", help="override_segment_group_order = segment first")
    sp.add_argument("--include", choices=INCLUDES)
    sp.add_argument("--limit", type=int, default=100, help="Rows per page (1–2000)")
    sp.add_argument("--all", action="store_true", help="Follow cursors to the end")
    sp.add_argument("--max-items", type=int, default=20000)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatgpt_ads_cli",
        description="OpenAI Ads (ChatGPT Ads) CLI — Advertiser API v1. Writes default to a dry-run plan; add --confirm.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--account", default=None,
                        help="Named account: uses OPENAI_ADS_API_KEY_<NAME> from .env (default: OPENAI_ADS_API_KEY)")
    sub = parser.add_subparsers(dest="command", required=True)

    # ----- Account ---------------------------------------------------------
    _cmd(sub, "account", cmd_account, "Ad account: status, review, currency, tz, negative keywords, spend caps")
    sp = _cmd(sub, "accounts", cmd_accounts, "List ad accounts reachable with this key")
    sp.add_argument("--max-items", type=int, default=api.LIST_HARD_CAP)
    sp = _cmd(sub, "brand-update", cmd_brand_update, "Update account name / URL / favicon (starts brand review)", write=True)
    sp.add_argument("--name")
    sp.add_argument("--url")
    sp.add_argument("--favicon-file-id", help="file_id from image-upload --purpose account_favicon")
    _cmd(sub, "negative-keywords", cmd_negative_keywords, "Show account-level negative keywords")
    sp = _cmd(sub, "negative-keywords-set", cmd_negative_keywords_set, "REPLACE the negative keyword list (max 100)", write=True)
    sp.add_argument("--keywords", help="Comma-separated")
    sp.add_argument("--keywords-file", help="One keyword per line")
    sp = _cmd(sub, "negative-keywords-add", cmd_negative_keywords_add, "Add negative keywords (read-modify-write)", write=True)
    sp.add_argument("--keywords", required=True)
    sp = _cmd(sub, "negative-keywords-remove", cmd_negative_keywords_remove, "Remove negative keywords", write=True)
    sp.add_argument("--keywords", required=True)
    _cmd(sub, "spend-limits", cmd_spend_limits, "List account spend limit windows (the spend fuse)")
    sp = _cmd(sub, "spend-limit-create", cmd_spend_limit_create, "Create a spend limit window", write=True)
    sp.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    sp.add_argument("--end", required=True, help="YYYY-MM-DD EXCLUSIVE")
    sp.add_argument("--amount", required=True, help="Cap in account currency")
    sp.add_argument("--name")
    sp.add_argument("--io-id", help="Insertion order reference (optional)")
    sp = _cmd(sub, "spend-limit-update", cmd_spend_limit_update, "Edit a spend limit window", write=True)
    sp.add_argument("--window-id", required=True)
    sp.add_argument("--start")
    sp.add_argument("--end")
    sp.add_argument("--amount")
    sp.add_argument("--name")
    sp.add_argument("--io-id")
    sp = _cmd(sub, "spend-limit-delete", cmd_spend_limit_delete, "Delete a spend limit window", write=True)
    sp.add_argument("--window-id", required=True)
    _cmd(sub, "account-pause", cmd_account_pause, "Pause the whole ad account", write=True)
    _cmd(sub, "account-activate", cmd_account_activate, "Activate the ad account", write=True)
    _cmd(sub, "api-limits", cmd_api_limits, "Local request-budget usage vs documented rate limits")
    sp = _cmd(sub, "api-key-create", cmd_api_key_create, "Create another API key for this account (shown once)", write=True)
    sp.add_argument("--name", help="key_name")
    sp = _cmd(sub, "landing-check", cmd_landing_check, "Local landing-page check: reachability, robots.txt, favicon")
    sp.add_argument("--url", required=True)

    # ----- Campaigns -------------------------------------------------------
    sp = _cmd(sub, "campaigns", cmd_campaigns, "List campaigns")
    _list_args(sp)
    sp = _cmd(sub, "campaign-detail", cmd_campaign_detail, "Campaign detail incl. targeting & serving issues")
    sp.add_argument("--campaign-id", required=True)
    sp.add_argument("--with-children", action="store_true", help="Whole tree: ad groups AND their ads with review status")
    sp = _cmd(sub, "campaign-create", cmd_campaign_create, "Create a campaign (paused)", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--status", default="paused", choices=STATUS_CREATE)
    sp.add_argument("--bidding-type", choices=BIDDING_TYPES, help="impressions (CPM, default) | clicks (CPC) | conversions (oCPC)")
    sp.add_argument("--objective", choices=OBJECTIVES, help="Optional: reach | clicks | conversions")
    sp.add_argument("--billing-event-type", choices=["impression", "click"], help="Optional campaign-level billing event")
    sp.add_argument("--mode", choices=MODES, help="product_feed | business_agent")
    sp.add_argument("--product-feed-id", help="Linked feed id (implies --mode product_feed)")
    sp.add_argument("--business-agent-id", help="Published business agent id (implies --mode business_agent)")
    _campaign_common_args(sp)
    sp = _cmd(sub, "campaign-update", cmd_campaign_update, "Update a campaign", write=True)
    sp.add_argument("--campaign-id", required=True)
    sp.add_argument("--name")
    sp.add_argument("--status", choices=STATUS_UPDATE)
    sp.add_argument("--clear-end-time", action="store_true")
    sp.add_argument("--clear-targeting", action="store_true", help="targeting=null (all locations)")
    _campaign_common_args(sp)
    for action, fn in (("activate", cmd_campaign_activate), ("pause", cmd_campaign_pause), ("archive", cmd_campaign_archive)):
        sp = _cmd(sub, f"campaign-{action}", fn, f"{action.capitalize()} a campaign" + (" (IRREVERSIBLE)" if action == "archive" else ""), write=True)
        sp.add_argument("--campaign-id", required=True)
        if action == "archive":
            sp.add_argument("--force", action="store_true", help="Archive even when not paused")

    # ----- Ad groups -------------------------------------------------------
    sp = _cmd(sub, "adgroups", cmd_adgroups, "List ad groups (optionally by campaign)")
    sp.add_argument("--campaign-id")
    _list_args(sp)
    sp = _cmd(sub, "adgroup-detail", cmd_adgroup_detail, "Ad group detail incl. bidding, hints, issues")
    sp.add_argument("--ad-group-id", required=True)
    sp.add_argument("--with-children", action="store_true", help="Also list its ads")
    sp = _cmd(sub, "adgroup-create", cmd_adgroup_create, "Create an ad group (paused)", write=True)
    sp.add_argument("--campaign-id", required=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--status", default="paused", choices=STATUS_CREATE)
    _adgroup_common_args(sp)
    sp = _cmd(sub, "adgroup-update", cmd_adgroup_update, "Update an ad group", write=True)
    sp.add_argument("--ad-group-id", required=True)
    sp.add_argument("--name")
    sp.add_argument("--status", choices=STATUS_UPDATE)
    _adgroup_common_args(sp)
    for action, fn in (("activate", cmd_adgroup_activate), ("pause", cmd_adgroup_pause), ("archive", cmd_adgroup_archive)):
        sp = _cmd(sub, f"adgroup-{action}", fn, f"{action.capitalize()} an ad group" + (" (IRREVERSIBLE)" if action == "archive" else ""), write=True)
        sp.add_argument("--ad-group-id", required=True)
        if action == "archive":
            sp.add_argument("--force", action="store_true")

    # ----- Ads -------------------------------------------------------------
    sp = _cmd(sub, "ads", cmd_ads, "List ads (by ad group / campaign / whole account)")
    sp.add_argument("--ad-group-id")
    sp.add_argument("--campaign-id", help="All ads of a campaign (iterates its ad groups)")
    sp.add_argument("--review-status", choices=REVIEW_STATUSES)
    _list_args(sp)
    sp = _cmd(sub, "ad-detail", cmd_ad_detail, "Ad detail incl. creative, review reason, appeal, issues")
    sp.add_argument("--ad-id", required=True)
    sp = _cmd(sub, "ad-review", cmd_ad_review, "Review check: ads not approved / with serving issues")
    sp.add_argument("--ad-id", help="Single ad (default: scan)")
    sp.add_argument("--campaign-id")
    sp.add_argument("--ad-group-id")
    sp.add_argument("--name")
    sp.add_argument("--order", choices=["asc", "desc"])
    sp.add_argument("--max-items", type=int, default=api.LIST_HARD_CAP)
    sp = _cmd(sub, "ad-create", cmd_ad_create, "Create an ad (paused) — chat_card or product_ad_template", write=True)
    sp.add_argument("--ad-group-id", required=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--status", default="paused", choices=STATUS_CREATE)
    sp.add_argument("--force", action="store_true", help="Skip product_set sanity warnings")
    _creative_args(sp)
    sp = _cmd(sub, "ad-update", cmd_ad_update, "Update an ad (creative change → re-review)", write=True)
    sp.add_argument("--ad-id", required=True)
    sp.add_argument("--name")
    sp.add_argument("--status", choices=STATUS_UPDATE)
    _creative_args(sp)
    sp = _cmd(sub, "ad-preview", cmd_ad_preview, "Render an ad preview (iframe, valid ~24 h)")
    sp.add_argument("--ad-id", required=True)
    sp.add_argument("--out", help="Write HTML to this file")
    for action, fn in (("activate", cmd_ad_activate), ("pause", cmd_ad_pause), ("archive", cmd_ad_archive)):
        sp = _cmd(sub, f"ad-{action}", fn, f"{action.capitalize()} an ad" + (" (IRREVERSIBLE)" if action == "archive" else ""), write=True)
        sp.add_argument("--ad-id", required=True)
        if action == "archive":
            sp.add_argument("--force", action="store_true")

    # ----- Files -----------------------------------------------------------
    sp = _cmd(sub, "image-upload", cmd_image_upload, "Upload an image (URL or file) → file_id (direct write)")
    sp.add_argument("--url", help="Public image URL (or site URL with --purpose account_favicon)")
    sp.add_argument("--file", help="Local image file (≤ 16 MiB)")
    sp.add_argument("--purpose", choices=["account_favicon"], help="account_favicon for brand-update")
    sp = _cmd(sub, "file-upload", cmd_file_upload, "Upload a customer list (.csv/.txt) → file_id for audiences (direct write)")
    sp.add_argument("--file", required=True)
    sp.add_argument("--purpose", default="custom_audience", choices=["custom_audience"])

    # ----- Insights --------------------------------------------------------
    sp = _cmd(sub, "insights", cmd_insights, "Delivery insights (account/campaign/ad group/ad scope)")
    _insights_args(sp)
    sp = _cmd(sub, "conversion-insights", cmd_conversion_insights, "Attributed conversions (click-through + view-through)")
    sp.add_argument("--level", choices=LEVELS, default="campaign")
    sp.add_argument("--ids", help="entity ids, comma-separated")
    sp.add_argument("--granularity", choices=["none", "daily"], default="none")
    sp.add_argument("--breakdown", choices=["device", "country"])
    sp.add_argument("--group-by-entity", action="store_true")
    sp.add_argument("--include-zero", action="store_true")
    sp.add_argument("--since")
    sp.add_argument("--until")
    sp.add_argument("--days", type=int, default=7)
    sp.add_argument("--timezone")
    sp = _cmd(sub, "pulse", cmd_pulse, "Account digest: deltas vs previous period, spend caps, review issues")
    sp.add_argument("--days", type=int, default=7)

    # ----- Targeting -------------------------------------------------------
    sp = _cmd(sub, "geo-search", cmd_geo_search, "Search targetable locations (country/region/DMA ids)")
    sp.add_argument("--q", required=True)
    sp.add_argument("--country", help="Filter results to a country code")
    sp.add_argument("--limit", type=int, default=25)

    # ----- Audiences -------------------------------------------------------
    sp = _cmd(sub, "audiences", cmd_audiences, "List custom audiences (optionally eligibility for a use)")
    sp.add_argument("--intended-use", choices=INTENDED_USES)
    sp.add_argument("--ids", help="Comma-separated audience ids to check")
    sp.add_argument("--policy-revision")
    sp.add_argument("--granular", action="store_true", help="matched_count_granularity=granular")
    sp.add_argument("--all", action="store_true", help="Include archived")
    sp.add_argument("--max-items", type=int, default=api.LIST_HARD_CAP)
    sp = _cmd(sub, "audience-detail", cmd_audience_detail, "Audience status, counts, membership revision")
    sp.add_argument("--audience-id", required=True)
    sp.add_argument("--granular", action="store_true")
    sp = _cmd(sub, "audience-create", cmd_audience_create, "Create an audience (from file-upload or empty)", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--description")
    sp.add_argument("--file-id")
    sp.add_argument("--filename")
    sp.add_argument("--mimetype")
    sp.add_argument("--file-size")
    sp.add_argument("--identifier-type", choices=IDENTIFIER_TYPES)
    sp.add_argument("--auto-resolve", action="store_true", help="identifier_resolution=auto (mixed CSV columns)")
    for action, fn in (("add", cmd_audience_add), ("remove", cmd_audience_remove)):
        sp = _cmd(sub, f"audience-{action}", fn, f"{action.capitalize()} members (inline identifiers or file)", write=True)
        sp.add_argument("--audience-id", required=True)
        sp.add_argument("--identifiers", help="Comma-separated; optionally type:value (email:a@b.cz)")
        sp.add_argument("--identifiers-file", help="One identifier per line (needs --identifier-type)")
        sp.add_argument("--identifier-type", choices=IDENTIFIER_TYPES)
        sp.add_argument("--file-id", help="From file-upload")
        sp.add_argument("--auto-resolve", action="store_true")
        sp.add_argument("--expected-revision", help="membership_revision read before the change (default: fetched now)")
    sp = _cmd(sub, "audience-replace", cmd_audience_replace, "Replace whole membership from an uploaded file", write=True)
    sp.add_argument("--audience-id", required=True)
    sp.add_argument("--file-id", required=True)
    sp.add_argument("--filename")
    sp.add_argument("--mimetype")
    sp.add_argument("--file-size")
    sp.add_argument("--identifier-type", choices=IDENTIFIER_TYPES)
    sp.add_argument("--auto-resolve", action="store_true")
    sp.add_argument("--expected-revision")
    sp = _cmd(sub, "audience-merge", cmd_audience_merge, "Merge 2–64 audiences into a NEW audience", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--ids", required=True, help="Comma-separated source audience ids")
    sp = _cmd(sub, "audience-archive", cmd_audience_archive, "Archive an audience (PERMANENT)", write=True)
    sp.add_argument("--audience-id", required=True)
    sp = _cmd(sub, "audience-operation", cmd_audience_operation, "Poll a membership operation")
    sp.add_argument("--audience-id", required=True)
    sp.add_argument("--operation-id", required=True)
    sp.add_argument("--wait", action="store_true")
    sp.add_argument("--wait-timeout", type=int, default=600)

    # ----- Conversions -----------------------------------------------------
    sp = _cmd(sub, "pixels", cmd_pixels, "List conversion sources (pixels)")
    sp.add_argument("--max-items", type=int, default=api.LIST_HARD_CAP)
    sp = _cmd(sub, "pixel-create", cmd_pixel_create, "Create a web pixel (conversion source)", write=True)
    sp.add_argument("--name", required=True)
    sp = _cmd(sub, "capi-key-create", cmd_capi_key_create, "Create a Conversions API key (shown once)", write=True)
    sp.add_argument("--name", required=True)
    sp = _cmd(sub, "event-settings", cmd_event_settings, "List conversion event settings")
    sp.add_argument("--all", action="store_true", help="Include archived")
    sp.add_argument("--max-items", type=int, default=api.LIST_HARD_CAP)
    sp = _cmd(sub, "event-setting-create", cmd_event_setting_create, "Create a conversion event setting", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--event-type", required=True, help="order_created, lead_created, registration_completed, … or custom")
    sp.add_argument("--custom-event-name")
    sp.add_argument("--source-id", required=True, help="Conversion source id from pixels (exactly one)")
    sp.add_argument("--attribution-window", type=int, default=30)
    sp = _cmd(sub, "conversion-check", cmd_conversion_check, "Measurement health: pixel → event setting → campaign link (→ recent events)")
    sp.add_argument("--events", action="store_true", help="Also pull the recent pixel event stream per pixel")
    sp = _cmd(sub, "conversion-events", cmd_conversion_events, "Recent pixel events (debug stream, last ~15 min)")
    sp.add_argument("--pid", required=True, help="Pixel ID")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--wide", action="store_true", help="Full event_data_json column")

    # ----- Product feeds ---------------------------------------------------
    sp = _cmd(sub, "feeds", cmd_feeds, "List product feeds")
    sp.add_argument("--with-counts", action="store_true", help="include[]=product_count")
    sp.add_argument("--max-items", type=int, default=api.LIST_HARD_CAP)
    sp = _cmd(sub, "feed-create", cmd_feed_create, "Create a product feed shell", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--countries", help="ISO codes, comma-separated")
    sp = _cmd(sub, "feed-archive", cmd_feed_archive, "Archive a feed (permanent)", write=True)
    sp.add_argument("--feed-id", required=True)
    sp = _cmd(sub, "feed-uploads", cmd_feed_uploads, "Recent catalog uploads with diagnostics")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--paginate", action="store_true")
    sp = _cmd(sub, "feed-products", cmd_feed_products, "Query products in a feed (ad-group style filters)")
    sp.add_argument("--feed-id", required=True)
    sp.add_argument("--filter", action="append", help="field:operator:v1|v2")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--after")
    sp = _cmd(sub, "feed-products-patch", cmd_feed_products_patch, "Delta update: availability/price/title of variants", write=True)
    sp.add_argument("--feed-id", required=True)
    sp.add_argument("--products-json", help="JSON list (or @file) of {id, variants:[…]}")
    sp.add_argument("--product-id")
    sp.add_argument("--variant-id")
    sp.add_argument("--available", choices=["true", "false"])
    sp.add_argument("--availability-status", help="in_stock | out_of_stock (overrides --available)")
    sp.add_argument("--price", help="Amount in MINOR units (8999 = 89.99)")
    sp.add_argument("--currency", help="ISO 4217")
    sp.add_argument("--title")
    sp = _cmd(sub, "feed-sftp", cmd_feed_sftp, "Show SFTP access for a feed")
    sp.add_argument("--feed-id", required=True)
    sp = _cmd(sub, "feed-sftp-create", cmd_feed_sftp_create, "Create/ROTATE SFTP credentials (password shown once)", write=True)
    sp.add_argument("--feed-id", required=True)
    sp.add_argument("--auth-method", choices=["password", "ssh_key"], default="password")
    sp.add_argument("--ssh-public-key", help="Path or key text")
    for action, fn in (("activate", cmd_feed_sftp_activate), ("pause", cmd_feed_sftp_pause)):
        sp = _cmd(sub, f"feed-sftp-{action}", fn, f"{action.capitalize()} SFTP access", write=True)
        sp.add_argument("--feed-id", required=True)

    # ----- Lead forms & lead sync -----------------------------------------
    sp = _cmd(sub, "lead-forms", cmd_lead_forms, "List lead forms")
    sp.add_argument("--all", action="store_true")
    sp = _cmd(sub, "lead-form-detail", cmd_lead_form_detail, "Lead form detail (optionally a revision)")
    sp.add_argument("--lead-form-id", required=True)
    sp.add_argument("--rev-id")
    sp = _cmd(sub, "lead-form-create", cmd_lead_form_create, "Create a lead form DRAFT (3–5 fields)", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--privacy-url")
    sp.add_argument("--fields-json", required=True, help='JSON (or @file): [{"field_type":"text","label":"E-mail","required":true}, …]')
    sp = _cmd(sub, "lead-form-update", cmd_lead_form_update, "Save a new draft revision", write=True)
    sp.add_argument("--lead-form-id", required=True)
    sp.add_argument("--name")
    sp.add_argument("--privacy-url")
    sp.add_argument("--fields-json")
    sp.add_argument("--expected-draft-revision-id")
    sp = _cmd(sub, "lead-form-publish", cmd_lead_form_publish, "Publish the current draft", write=True)
    sp.add_argument("--lead-form-id", required=True)
    sp.add_argument("--expected-draft-revision-id")
    sp = _cmd(sub, "lead-form-archive", cmd_lead_form_archive, "Archive a lead form", write=True)
    sp.add_argument("--lead-form-id", required=True)
    sp = _cmd(sub, "lead-form-test", cmd_lead_form_test, "Send a synthetic signed test lead to the webhook", write=True)
    sp.add_argument("--lead-form-id", required=True)
    sp.add_argument("--expected-published-revision-id")
    sp = _cmd(sub, "lead-syncs", cmd_lead_syncs, "List lead-sync webhook subscriptions")
    sp.add_argument("--ad-account-id")
    sp = _cmd(sub, "lead-sync-create", cmd_lead_sync_create, "Provision lead delivery to an https webhook", write=True)
    sp.add_argument("--destination-url", required=True)
    sp.add_argument("--signing-secret", help="Optional whsec_… (generated when omitted)")
    sp.add_argument("--ad-account-id")
    sp = _cmd(sub, "lead-sync-detail", cmd_lead_sync_detail, "Lead-sync subscription status")
    sp.add_argument("--subscription-id", required=True)
    sp = _cmd(sub, "lead-sync-delete", cmd_lead_sync_delete, "Delete a lead-sync subscription", write=True)
    sp.add_argument("--subscription-id", required=True)

    # ----- Business agents -------------------------------------------------
    _cmd(sub, "business-agents", cmd_business_agents, "List Business Agents (branded chat agents)")
    sp = _cmd(sub, "business-agent-detail", cmd_business_agent_detail, "Business Agent detail")
    sp.add_argument("--business-agent-id", required=True)
    _cmd(sub, "business-agent-tools", cmd_business_agent_tools, "Tools installable into a Business Agent")
    for action, fn in (("create", cmd_business_agent_create), ("update", cmd_business_agent_update)):
        sp = _cmd(sub, f"business-agent-{action}", fn, f"{action.capitalize()} a Business Agent draft", write=True)
        if action == "update":
            sp.add_argument("--business-agent-id", required=True)
        sp.add_argument("--name", required=(action == "create"), help="≤ 50 chars")
        sp.add_argument("--instructions", help="≤ 4000 chars")
        sp.add_argument("--instructions-file")
        sp.add_argument("--description", help="≤ 300 chars")
        sp.add_argument("--privacy-url")
        sp.add_argument("--starter", action="append", help="Conversation starter (repeatable, max 12)")
        sp.add_argument("--feed-ids", help="Product feed ids, comma-separated")
        sp.add_argument("--tools", help="Tool ids, comma-separated (see business-agent-tools)")
        sp.add_argument("--connector-ids")
        sp.add_argument("--lead-form-id", help="Published lead form id ('' to unlink on update)")
        sp.add_argument("--lead-form-revision-id")
    sp = _cmd(sub, "business-agent-preview", cmd_business_agent_preview, "Preview a reply from the agent")
    sp.add_argument("--business-agent-id", required=True)
    sp.add_argument("--message", action="append", required=True, help="user:… / assistant:… (repeatable, max 10)")
    sp = _cmd(sub, "business-agent-publish", cmd_business_agent_publish, "Publish the agent draft", write=True)
    sp.add_argument("--business-agent-id", required=True)

    # ----- Plan (whole campaign tree from one JSON) -------------------------
    sp = _cmd(sub, "plan-apply", cmd_plan_apply, "Create campaign → ad groups → ads from one JSON plan (resumable)", write=True)
    sp.add_argument("--file", required=True, help="Plan JSON (see docs/plan-example.json)")
    sp.add_argument("--state", help="State file (default <plan>.state.json) — records created ids for resume")

    # ----- Bulk API --------------------------------------------------------
    sp = _cmd(sub, "bulk-submit", cmd_bulk_submit, "Submit a bulk job from JSON (dry-run = server validate_only)", write=True)
    sp.add_argument("--file", required=True, help="JSON file: {operations:[…]} or a bare list")
    sp.add_argument("--no-partial-failure", action="store_true", help="Stop after the first failure")
    sp.add_argument("--skip-validation", action="store_true", help="Dry-run without calling the API at all")
    sp.add_argument("--wait", action="store_true", help="Poll the job and print operation results")
    sp.add_argument("--wait-timeout", type=int, default=600)
    sp = _cmd(sub, "bulk-job", cmd_bulk_job, "Bulk job status")
    sp.add_argument("--job-id", required=True)
    sp.add_argument("--wait", action="store_true")
    sp.add_argument("--wait-timeout", type=int, default=600)
    sp = _cmd(sub, "bulk-operations", cmd_bulk_operations, "Per-operation results of a bulk job")
    sp.add_argument("--job-id", required=True)

    # ----- Partner data ----------------------------------------------------
    sp = _cmd(sub, "partner-data-upload-create", cmd_partner_data_upload_create, "Register a partner-data (.parquet) upload", write=True)
    sp.add_argument("--file", required=True)
    sp.add_argument("--data-type", default="identity_graph", choices=["identity_graph"])
    sp.add_argument("--snapshot-date", required=True, help="YYYY-MM-DD")
    sp = _cmd(sub, "partner-data-upload", cmd_partner_data_upload, "Partner-data upload status")
    sp.add_argument("--upload-id", required=True)

    # ----- Raw -------------------------------------------------------------
    sp = _cmd(sub, "raw", cmd_raw, "Call any endpoint: raw GET /campaigns --params '{\"limit\":5}'", write=True)
    sp.add_argument("method")
    sp.add_argument("path")
    sp.add_argument("--params", help="Query params JSON (lists repeat the key)")
    sp.add_argument("--body", help="JSON body (or @file)")

    return parser


def main() -> None:
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    _print_banner()
    parser = build_parser()
    args = parser.parse_args()           # --help / --version exit here, before .env is needed
    api.set_account(args.account)
    if args.command != "landing-check":  # the only command that never touches the API
        api.check_config()
        if len(api.configured_accounts()) > 1 and not getattr(args, "json", False):
            print(f"[account: {api.ACTIVE_ACCOUNT}]", file=sys.stderr)
    args.func(args)


if __name__ == "__main__":
    main()
