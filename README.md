# AI Slop Detector

Detect AI-generated code patterns in any GitHub repository. One click, instant report.

## How it works

1. Extension sends the repo URL to a local Python server
2. Server clones the repo, scans all source files with tree-sitter
3. 9 heuristic detectors check for AI slop patterns
4. Returns a 0-100 score with red flags and recommendations

**Your code never leaves your machine.** No API keys, no cloud, fully local.

## Quick Start

```bash
pip install -r requirements.txt
python server.py
```

Then load the extension:

1. Open `edge://extensions` (or `chrome://extensions`)
2. Enable **Developer mode**
3. Click **Load unpacked** → select the `extension/` folder
4. Browse any GitHub repo → click the extension icon → **Analyze Repository**

## Pricing

**3 free analyses** included. Unlimited analyses: ~~$9.9~~ **$5** — one-time payment, lifetime updates.

### How to get an activation code

1. 微信转账 ¥35 或 PayPal $5 至 **2115464137@qq.com**
2. 备注留你的邮箱，或 DM 我：V2EX [@Leo-Ayh-Oday](https://v2ex.com)
3. 收到激活码后在扩展里粘贴 → 永久解锁

> 付款后 24 小时内发码。有问题直接加微信 **Leo_Ayh**。

## Scoring

| Score | Verdict |
|-------|---------|
| 80-100 | Clean |
| 40-79 | Suspicious |
| 0-39 | Likely AI Slop |

## 9 Detection Signals

- **Commit Bombing** — all code in 1-2 massive commits
- **Generic Naming** — `data`, `temp`, `result` everywhere
- **Over-commenting** — obvious comments, comment-to-code ratio >40%
- **No Tests** — zero tests but README claims "production-ready"
- **Hallucinated Imports** — importing packages that don't exist
- **Single Contributor** — only one author in git history
- **Template Structure** — matching stock scaffold with no changes
- **Spray-and-Pray PRs** — lots of single-commit branches named `fix`, `update`, `wip`
- **Placeholder TODOs** — `# TODO`, `pass`, `NotImplementedError` density

## Requirements

- Python 3.10+
- Git (for cloning repos)
- Chrome or Edge browser

## License

MIT
