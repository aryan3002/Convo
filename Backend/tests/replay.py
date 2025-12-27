import argparse
import json
import sys
import urllib.request
from datetime import datetime


def load_prompts(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000/chat")
    parser.add_argument("--prompts", default="Backend/tests/prompts.json")
    parser.add_argument("--out", default="Backend/tests/replay_results.jsonl")
    args = parser.parse_args()

    prompts = load_prompts(args.prompts)
    results = []

    for prompt in prompts:
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "context": {"booking_state": "START"},
        }
        try:
            response = post_json(args.api, payload)
            results.append(
                {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "input": prompt,
                    "reply": response.get("reply"),
                    "action": response.get("action"),
                    "next_state": response.get("next_state"),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "input": prompt,
                    "error": str(exc),
                }
            )

    with open(args.out, "w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    print(f"Wrote {len(results)} results to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
