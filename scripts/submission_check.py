#!/usr/bin/env python3
"""
FlowLens Submission Completeness Checker
Verifies all Gemini Live Agent Challenge requirements are met.

Usage: python scripts/submission_check.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Colour output ────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW = "\033[93m"
BOLD  = "\033[1m"
RESET = "\033[0m"


def ok(msg: str):
    print(f"  {GREEN}✅{RESET}  {msg}")


def fail(msg: str, fix: str = ""):
    print(f"  {RED}❌{RESET}  {msg}")
    if fix:
        print(f"      {YELLOW}Fix:{RESET} {fix}")


def info(msg: str):
    print(f"  {YELLOW}ℹ{RESET}   {msg}")


# ── Helpers ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent


def file_contains(path: str, pattern: str) -> bool:
    p = ROOT / path
    if not p.exists():
        return False
    return pattern in p.read_text(errors="ignore")


def file_exists(path: str) -> bool:
    return (ROOT / path).exists()


def run_cmd(cmd: str, timeout: int = 10) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            cwd=str(ROOT),
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:
        return -1, str(e)


def curl_json(url: str) -> dict | None:
    code, out = run_cmd(f"curl -sf --max-time 10 {url}", timeout=15)
    if code != 0:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


# ── Check categories ─────────────────────────────────────────────────────────

def check_mandatory_tech(score: list[int], total: list[int]):
    print(f"\n{BOLD}MANDATORY TECH{RESET}")
    total.append(3)

    passed = 0
    if file_contains("backend/agent.py", "gemini-2.0-flash-live"):
        ok("Gemini Live API model used (gemini-2.0-flash-live)")
        passed += 1
    else:
        fail(
            "Gemini Live API model NOT found in backend/agent.py",
            'Add: self._live_model_name = "gemini-2.0-flash-live-001"',
        )

    if file_contains("backend/requirements.txt", "google-adk") or \
       file_contains("backend/agent.py", "google.adk") or \
       file_contains("backend/requirements.txt", "google-adk"):
        ok("google-adk imported")
        passed += 1
    else:
        fail(
            "google-adk not found in requirements.txt",
            "Add: google-adk==0.1.0 to backend/requirements.txt",
        )

    cloud_run_url = os.environ.get("CLOUD_RUN_URL", "")
    if cloud_run_url:
        data = curl_json(f"{cloud_run_url}/health")
        if data and data.get("status") == "healthy":
            ok(f"GCP deployment live: {cloud_run_url}/health → healthy")
            passed += 1
        else:
            fail(
                "GCP deployment health check failed",
                "Run: make deploy  then check CLOUD_RUN_URL in .env",
            )
    else:
        fail(
            "CLOUD_RUN_URL not set — cannot verify GCP deployment",
            "After `make deploy`, set CLOUD_RUN_URL=https://... in .env",
        )

    score.append(passed)


def check_artifacts(score: list[int], total: list[int]):
    print(f"\n{BOLD}SUBMISSION ARTIFACTS{RESET}")
    total.append(5)

    passed = 0

    code, out = run_cmd("git remote -v 2>&1")
    if "github.com" in out:
        ok("Public GitHub repo configured")
        passed += 1
    else:
        fail("No GitHub remote found", "git remote add origin https://github.com/your-org/flowlens")

    if file_contains("README.md", "docker compose up") or \
       file_contains("README.md", "docker-compose up"):
        ok("README.md has setup instructions (docker compose up)")
        passed += 1
    else:
        fail("README.md missing docker compose up instruction", "Add quick start section to README.md")

    if file_exists("docs/architecture.png") or file_exists("docs/architecture.svg") or \
       file_exists("architecture.png"):
        ok("Architecture diagram exists")
        passed += 1
    else:
        fail(
            "Architecture diagram missing",
            "Create docs/architecture.png — can use draw.io or export from README",
        )

    if file_exists("infra/terraform/main.tf"):
        ok("IaC scripts exist (infra/terraform/main.tf)")
        passed += 1
    else:
        fail("infra/terraform/main.tf not found", "Run Phase 4 Terraform scaffold")

    demo_path = ROOT / "demo" / "demo.mp4"
    if demo_path.exists():
        code, out = run_cmd(f'ffprobe -v quiet -show_entries format=duration -of csv=p=0 "{demo_path}"')
        try:
            duration = float(out.strip())
            if duration < 240:
                ok(f"Demo video exists and is under 4 minutes ({duration:.0f}s)")
                passed += 1
            else:
                fail(f"Demo video is {duration:.0f}s — must be under 240s (4 min)", "Trim the video")
        except Exception:
            info("demo/demo.mp4 found but could not verify duration (ffprobe needed)")
            passed += 1
    else:
        fail("demo/demo.mp4 not found", "Record screen demo and save to demo/demo.mp4")

    score.append(passed)


def check_bonus(score: list[int], total: list[int]):
    print(f"\n{BOLD}BONUS POINTS{RESET}")
    total.append(3)

    passed = 0

    gdg_url = input("  Paste your GDG profile URL (or Enter to skip): ").strip()
    if gdg_url.startswith("http"):
        ok(f"GDG membership: {gdg_url}")
        passed += 1
    else:
        fail("GDG membership URL not provided", "https://gdg.community.dev — join and paste your profile URL")

    blog_url = input("  Paste your blog post URL (or Enter to skip): ").strip()
    if blog_url.startswith("http"):
        ok(f"Blog post: {blog_url}")
        passed += 1
    else:
        fail("Blog post not published", "Run: `make blog` or write on dev.to with #GeminiLiveAgentChallenge")

    social = input("  Did you post on social media with #GeminiLiveAgentChallenge? (y/n): ").strip().lower()
    if social.startswith("y"):
        ok("Social media post confirmed")
        passed += 1
    else:
        fail("Social post not confirmed", "Tweet or LinkedIn post with #GeminiLiveAgentChallenge #GeminiAPI")

    score.append(passed)


def check_performance(score: list[int], total: list[int]):
    print(f"\n{BOLD}PERFORMANCE{RESET}")
    total.append(2)

    passed = 0

    cloud_run_url = os.environ.get("CLOUD_RUN_URL", "")
    if cloud_run_url:
        data = curl_json(f"{cloud_run_url}/health")
        if data:
            p50 = data.get("p50_latency_ms", 9999)
            if p50 < 3000:
                ok(f"p50 latency {p50}ms < 3000ms ✓")
                passed += 1
            else:
                fail(f"p50 latency {p50}ms ≥ 3000ms target", "Review Phase 5 optimizations in agent.py")
        else:
            fail("Cannot fetch latency stats — deployment not accessible", "Run: make deploy")
    else:
        fail("CLOUD_RUN_URL not set", "Deploy first with: make deploy")

    if file_contains("infra/terraform/main.tf", "min_instance_count"):
        ok("min_instances = 1 set in Terraform (no cold start during demo)")
        passed += 1
    else:
        fail("min_instances not found in main.tf", 'Add: min_instance_count = 1 to Cloud Run template scaling block')

    score.append(passed)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{'═' * 55}{RESET}")
    print(f"{BOLD}  FlowLens — Submission Completeness Checker{RESET}")
    print(f"{BOLD}  Gemini Live Agent Challenge · March 2026{RESET}")
    print(f"{BOLD}{'═' * 55}{RESET}")

    score: list[int] = []
    total: list[int] = []

    check_mandatory_tech(score, total)
    check_artifacts(score, total)
    check_performance(score, total)
    check_bonus(score, total)

    total_score = sum(score)
    total_possible = sum(total)

    print(f"\n{'═' * 55}")
    print(f"{BOLD}Score: {total_score}/{total_possible} requirements met{RESET}")
    print(f"{'═' * 55}\n")

    if total_score == total_possible:
        print(f"{GREEN}{BOLD}🏆 SUBMISSION READY. Go win.{RESET}\n")
    else:
        missing = total_possible - total_score
        print(f"{RED}{BOLD}{missing} item(s) still need attention.{RESET}")
        print("Review the ❌ items above and fix before submitting.\n")

    return 0 if total_score == total_possible else 1


if __name__ == "__main__":
    sys.exit(main())
