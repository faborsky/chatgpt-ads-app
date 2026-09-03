#!/usr/bin/env python3
"""ChatGPT Ads CLI — thin entrypoint. Implementation lives in the oaiads/ package.

Re-exports for scripts that `import chatgpt_ads_cli as cli`.
"""

from oaiads.api import API_BASE, _api_call, _fetch_all, account_meta  # noqa: F401
from oaiads.cli import main

if __name__ == "__main__":
    main()
