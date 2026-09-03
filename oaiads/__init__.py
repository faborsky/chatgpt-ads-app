"""ChatGPT Ads CLI package (ChatGPT Ads — Advertiser API)."""
import warnings

# Silence urllib3's LibreSSL/OpenSSL warning BEFORE requests/urllib3 is imported
# by any submodule; must run first so stdout/stderr stays clean for --json.
warnings.filterwarnings("ignore", message=r".*OpenSSL.*")

__version__ = "1.3.2"
