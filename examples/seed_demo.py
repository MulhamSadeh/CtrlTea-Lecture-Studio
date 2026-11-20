#!/usr/bin/env python3
"""Create a fully synthetic local lecture example; no student data or authentication."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parent

def main():
    ap = argparse.ArgumentParser(description="Seed a synthetic lecture in the local Ctrl+Tea preview")
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    args = ap.parse_args()
    url = args.url.rstrip("/")
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost") or parts.username or parts.password or not parts.port:
        ap.error("This example is local-only. Use http://127.0.0.1:<port> or http://localhost:<port>.")
    demo = json.loads((ROOT / "demo-lecture.json").read_text(encoding="utf-8"))
    with httpx.Client(base_url=url, timeout=30.0, trust_env=False) as c:
        status = c.get("/api/auth/status")
        status.raise_for_status()
        if status.json().get("enabled", True):
            ap.error("Authentication is enabled. Do not run a public/demo seeder against an account-enabled instance.")
        course = c.post("/api/courses", json={"name":demo["course"],"doctor":""})
        course.raise_for_status()
        cid=course.json()["id"]
        created=c.post(f"/api/courses/{cid}/lectures",json={"title":demo["title"],"number":demo["number"],"theme":"olive"})
        created.raise_for_status()
        lid=created.json()["id"]
        saved=c.put(f"/api/lectures/{lid}",json={"document":demo,"revision":0})
        saved.raise_for_status()
    print(f"Created synthetic demo course {cid} / lecture {lid}")
    print("Open the local dashboard to inspect the example.")

if __name__=="__main__":
    main()
