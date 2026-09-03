"""End-to-end CLI behaviour via subprocess (first-contact paths)."""

import os
import subprocess
import sys

from oaiads import __version__

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(APP_DIR, "chatgpt_ads_cli.py")


def _run(*argv, key="your-ads-api-key-here"):
    env = {k: v for k, v in os.environ.items() if not (k.startswith("OPENAI_ADS_") or k.startswith("OAIADS_"))}
    env["OAIADS_NO_DOTENV"] = "1"          # never read the developer's .env in tests
    env["OPENAI_ADS_API_KEY"] = key
    return subprocess.run([sys.executable, CLI, *argv], capture_output=True, text=True, env=env, cwd=APP_DIR, timeout=60)


def test_help_works_without_key():
    r = _run("--help")
    assert r.returncode == 0 and "usage:" in r.stdout


def test_version():
    r = _run("--version")
    assert r.returncode == 0 and __version__ in r.stdout


def test_write_subcommand_help_shows_confirm():
    r = _run("campaign-create", "--help")
    assert r.returncode == 0 and "--confirm" in r.stdout and "--idempotency-key" in r.stdout


def test_real_command_fails_cleanly_without_key():
    r = _run("campaigns")
    assert r.returncode == 1
    assert "OPENAI_ADS_API_KEY not set" in r.stderr and "Traceback" not in r.stderr


def test_json_error_path_keeps_stdout_empty():
    r = _run("campaigns", "--json")
    assert r.returncode == 1 and r.stdout.strip() == ""


def test_dry_run_needs_no_network():
    r = _run("campaign-create", "--name", "Offline plan", "--lifetime-budget", "10", "--json", key="sk-test")
    assert r.returncode == 0
    assert '"executed": false' in r.stdout
