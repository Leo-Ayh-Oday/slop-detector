"""Integration tests for AI Slop Detector API endpoints.

Usage: python tests/test_api.py
Requires: server running on localhost:8766
"""

import json
import sys
import requests

BASE = "http://localhost:8766"
PASS = 0
FAIL = 0


def test(name):
    global PASS, FAIL
    def deco(fn):
        def wrapper():
            global PASS, FAIL
            try:
                fn()
                PASS += 1
                print(f"  PASS  {name}")
            except AssertionError as e:
                FAIL += 1
                print(f"  FAIL  {name}: {e}")
            except Exception as e:
                FAIL += 1
                print(f"  ERROR {name}: {e}")
        wrapper()
        return wrapper
    return deco


@test("Server health check")
def test_status():
    r = requests.get(f"{BASE}/api/status", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert "indexed" in data


@test("Reject empty repo URL")
def test_slop_empty():
    r = requests.post(f"{BASE}/api/slop", json={"repo_url": "", "branch": "main"})
    assert r.status_code == 400


@test("Reject non-GitHub URL (clone fails)")
def test_slop_bad_url():
    r = requests.post(f"{BASE}/api/slop",
                      json={"repo_url": "https://not-a-real-repo-12345.com/x", "branch": "main"})
    assert r.status_code == 400


@test("Analyze small public repo")
def test_slop_real_repo():
    r = requests.post(f"{BASE}/api/slop",
                      json={"repo_url": "https://github.com/beavis07/slop-detector", "branch": "main"},
                      timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "score" in data
    assert "verdict" in data
    assert "red_flags" in data
    assert "stats" in data
    assert "recommendations" in data
    assert isinstance(data["score"], int)
    assert 0 <= data["score"] <= 100
    assert data["verdict"] in ("clean", "suspicious", "likely_slop")
    print(f"    Score: {data['score']}, Verdict: {data['verdict']}, "
          f"Flags: {len(data['red_flags'])}")


@test("Valid activation code")
def test_activate_valid():
    r = requests.post(f"{BASE}/api/activate",
                      json={"activation_code": "SLOP-401I-C1F9"})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True


@test("Invalid activation code")
def test_activate_invalid():
    r = requests.post(f"{BASE}/api/activate",
                      json={"activation_code": "BAD-CODE-XXXX"})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is False


@test("Slop report has correct structure")
def test_slop_structure():
    r = requests.post(f"{BASE}/api/slop",
                      json={"repo_url": "https://github.com/beavis07/slop-detector", "branch": "main"},
                      timeout=30)
    data = r.json()
    for flag in data["red_flags"]:
        assert "id" in flag
        assert "label" in flag
        assert "severity" in flag
        assert flag["severity"] in ("high", "medium", "low")
        assert "score" in flag
        assert 0 <= flag["score"] <= 10
        assert "evidence" in flag
        assert isinstance(flag["evidence"], list)
    for rec in data["recommendations"]:
        assert isinstance(rec, str) and len(rec) > 0


@test("Score formula consistency")
def test_score_consistency():
    r = requests.post(f"{BASE}/api/slop",
                      json={"repo_url": "https://github.com/beavis07/slop-detector", "branch": "main"},
                      timeout=30)
    data = r.json()
    # Verify score matches weighted penalties approximately
    total_weight = 2.0 + 1.5 + 1.0 + 2.0 + 2.0 + 1.0 + 1.5 + 0.5 + 2.0  # = 13.5
    max_penalty = 10.0 * total_weight  # = 135.0
    raw = sum(f["score"] * {"commit_bombing": 2.0, "generic_naming": 1.5,
                             "over_commenting": 1.0, "no_tests": 2.0,
                             "hallucinated_imports": 2.0, "single_contributor": 1.0,
                             "template_structure": 1.5, "spray_pray_prs": 0.5,
                             "placeholder_todos": 2.0}.get(f["id"], 0)
              for f in data["red_flags"])
    expected = max(0, min(100, round(100 * (1 - raw / max_penalty))))
    assert expected == data["score"], f"Expected {expected}, got {data['score']}"
    print(f"    Raw penalty: {raw:.1f}/{max_penalty}, Score: {data['score']} [OK]")


if __name__ == "__main__":
    print("AI Slop Detector — API Integration Tests\n")

    # Check server first
    try:
        requests.get(f"{BASE}/api/status", timeout=3)
    except Exception:
        print("ERROR: Server not running. Start with: python server.py")
        sys.exit(1)

    test_status()
    test_slop_empty()
    test_slop_bad_url()
    test_slop_real_repo()
    test_slop_structure()
    test_score_consistency()
    test_activate_valid()
    test_activate_invalid()

    print(f"\n{'='*40}")
    print(f"Results: {PASS} passed, {FAIL} failed out of {PASS+FAIL} tests")
    if FAIL > 0:
        sys.exit(1)
