"""Command line entry point. Run with: python -m newsintel --help"""
import argparse
import sys

from .pipeline import run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="newsintel",
        description="Collect tech news, label impact with free AI, email alerts and digests, keep a searchable archive.",
    )
    parser.add_argument("--dry-run", action="store_true", help="fetch and process, but send no email and write no files")
    parser.add_argument("--no-email", action="store_true", help="skip sending email; still write storage")
    parser.add_argument("--digest", action="store_true", help="send a digest email for --period")
    parser.add_argument("--period", choices=["day", "week", "month"], default="day",
                        help="digest period: day (default), week or month")
    parser.add_argument("--no-ai", action="store_true", help="do not call free AI models; use rule-based levels")
    parser.add_argument("--feed", help="process only the enabled feed with this exact name")
    parser.add_argument("--fixture", help="read this XML file instead of the network (offline testing)")
    parser.add_argument("--ignore-age", action="store_true", help="keep old items too (use with --fixture)")
    parser.add_argument("--test-email", action="store_true", help="send one test email to check email setup")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    opts = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    return run(opts)


if __name__ == "__main__":
    sys.exit(main())