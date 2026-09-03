# SHS Code vs OpenCode vs OpenHands vs Hermes — নিয়ন্ত্রিত CLI বেঞ্চমার্ক

**তারিখ:** 2026-09-03 · **মডেল:** NVIDIA NIM (`integrate.api.nvidia.com/v1`)
**ক্যাটাগরি:** `fast` = `openai/gpt-oss-20b` · `agentic` = `minimaxai/minimax-m3` (JD-এর নির্দেশে — m3 live-verified থাকায় দুটোই নেওয়া হয়েছে)

---

## ফলাফল এক নজরে (fair scoring)

| ক্যাটাগরি | CLI | জয় | গড় সময় | স্কिप |
|---|---|---|---|---|
| fast | **openhands 1.11.0** | **7/8** 👑 | 138s | 0 |
| fast | SHS Code v2.2.0 | 6/8 | 326s | 0 |
| fast | opencode 1.18.27 | 1/8 | 415s | 0 |
| fast | hermes 0.21.0 | 0/8 | 266s | 0 |
| agentic | **SHS Code v2.2.0** | **6/8** 👑 | 346s | 0 |
| agentic | openhands 1.11.0 | 3/8 | 361s | 0 |
| agentic | opencode 1.18.27 | 0/2 | 540s (সব TO) | 6 |
| agentic | hermes 0.21.0 | 0/3 | ~14s (429-মৃত্যু) | 5 |

**মূল ইনসাইট:** ছোট দ্রুত মডেলে openhands সেরা; বড় agentic মডেলে (m3) **SHS Code সবচেয়ে ভালো scale করে** — openhands m3-এর ধীরগতিতে ৫৪০s ক্যাপে মরে যায় (৪টি TO), SHS Code করে মাত্র ২টি TO।

## প্রতি-টাস্ক টেবিল

Legend: PASS=fair-success · FAIL=কাজ করেনি বা constraint ভাঙা · TO=টাইমআউট · SKIPPED=নির্ধারিত ব্যর্থতা প্রমাণিত, রান বাদ

### fast — openai/gpt-oss-20b (ক্যাপ 420s)
| টাস্ক | shscode | opencode | openhands | hermes |
|---|---|---|---|---|
| A simple_coding | PASS (179s) | PASS (375s) | PASS (124s) | FAIL (91s) |
| C bug_diagnosis | PASS (205s) | TO | PASS (57s) | FAIL (157s) |
| D debugging | PASS (156s) | TO | FAIL (31s) | FAIL (110s) |
| E repo_exploration | FAIL* (392s) | TO | PASS (179s) | FAIL (417s) |
| H refactoring | PASS | TO | PASS (164s) | FAIL (198s) |
| I test_writing | PASS (TO+verified) | TO | PASS (196s) | TO |
| M git_workflow | PASS (TO+verified) | TO | FAIL** (124s) | FAIL (325s) |
| V complex_reasoning | FAIL*** (TO) | TO | PASS (232s) | FAIL (413s) |

### agentic — minimaxai/minimax-m3 (ক্যাপ 540s)
| টাস্ক | shscode | opencode | openhands | hermes |
|---|---|---|---|---|
| A simple_coding | FAIL† (454s) | TO | TO‡ | 429-মৃত্যু (15s) |
| C bug_diagnosis | PASS (237s) | TO | PASS (379s) | 429-মৃত্যু (13s) |
| D debugging | PASS (261s) | SKIPPED | PASS (132s) | 429-মৃত্যু (14s) |
| E repo_exploration | PASS (509s) | SKIPPED | TO | SKIPPED |
| H refactoring | PASS (402s) | SKIPPED | TO | SKIPPED |
| I test_writing | FAIL (356s) | SKIPPED | FAIL (409s) | SKIPPED |
| M git_workflow | PASS (264s) | SKIPPED | PASS (115s) | SKIPPED |
| V complex_reasoning | PASS (283s) | SKIPPED | FAIL (233s) | SKIPPED |

\* shscode E: EXPLORATION.md দারুণ বানিয়েছে (সব মডিউল কভার), কিন্তু এক্সপ্লোর করতে গিয়ে **seeded bug-ও ফিক্স করে ফেলেছে** → "কোড পরিবর্তন কোরো না" constraint ভাঙা — সৎ ব্যর্থতা।
\*\* openhands M: কমিট ঠিক ছিল (৩টি চেকই TRUE), কিন্তু working tree-তে অন্য পরিবর্তন রেখে গেছে।
\*\*\* shscode V (fast): coupon.py+টেস্ট বানিয়েছে, কিন্তু suite-এর ২টি seeded failure ঠিক করেনি (প্রম্পট full-suite-green চেয়েছিল)।
† shscode A (agentic): palindrome সঠিক, টেস্ট যোগ হয়েছে, কিন্তু seeded failures রয়ে গেছে।
‡ openhands A (agentic): সব চেক PASS ছিল, ৫৪০s ক্যাপে clean-exit আটকে গেছে — verification post-mortem-এ ৪টি চেকই TRUE।

## স্কোরিং পদ্ধতি (fair recompute)

`metrics.json`-এ `strict_success` (হার্নেসের কড়া সূত্র) এবং `fair_success` দুটোই আছে। fair সূত্র seeded-bug-aware: যে টাস্কে প্রম্পট full-suite-green **চায় না** (D, E, M) সেখানে baseline-এর ২টি seeded failure জেতার শর্ত নয়; A, C, I, V-তে প্রম্পট স্পষ্টভাবে full suite pass চায়, তাই সেখানে কড়া শর্ত বহাল।

## লক্ষণীয় ট্রেস-প্রমাণ (সব raw/তে আছে)

1. **gpt-oss harmony leak:** SHS Code-এ 20b মাঝে মাঝে `bash<|channel|>commentary` নামে টুল ধরে — এজেন্ট নিজেই recover করে (runs/simple_coding-shscode-fast-t1)।
2. **NIM m3 rate limit:** ~২-৩ concurrent-এর বেশি নেলে 429; ৪-CLI parallel ওয়েভ m3-এ অসম্ভব ছিল — agentic রাউন্ড সম্পূর্ণ serial চলেছে।
3. **hermes+m3 = 429-মৃত্যু:** ৩/৩ চেষ্টায় ১৩-১৫s-এ `HTTP 429` (retry window ~৩১s < cooldown ৬০s; ৬৫s refill wait-এর পরেও)। বাকি সেল SKIPPED-মার্ক, ফেক করা হয়নি।
4. **opencode+m3 = deterministic TO:** A ও C-তে ২/২ চেষ্টায় ৫৪০s, শূন্য টুল-আউটপুট — NIM m3 তার বিশাল system prompt সার্ভ করতেই পারে না।
5. **OOM casualty:** ৫-parallel ওয়েভে একবার opencode মেমোরিতে kill হয়েছিল (rc=-9, ৫১s) — solo re-run নেওয়া হয়েছে।
6. **Timeout-but-verified:** shscode fast I ও M — ৪২০s ক্যাপে SIGKILL, অথচ post-mortem verification-এ সব চেক PASS (কাজ শেষ, exit আটকেছিল)।

## পদ্ধতি (methodology)

- **Workspace:** প্রতি রানে `baseline.git` থেকে fresh clone (commit-লক) — seeded bug-যুক্ত ৪-মডিউল Python রিপো + ৯ টেস্ট (২টি ইচ্ছাকৃত ব্যর্থ)।
- **একই প্রম্পট, একই baseline, একই মডেল, একই ক্যাপ** — ক্যাটাগরিপ্রতি ইউনিফর্ম (fast 420s, agentic 540s; sandbox-এর execution-model সীমার ভেতরে)।
- **অবজেক্টিভ ভেরিফিকেশন:** প্রতি টাস্কে হার্নেস নিজে pytest চালায় + টাস্ক-নির্দিষ্ট semantic চেক (palindrome correctness, coupon logic, git commit hygiene, constraint-compliance) — agent-এর দাবি বিশ্বাস করা হয়নি।
- **ট্রেস:** প্রতি রানে `raw/stdout.log`, `raw/stderr.log`, `raw/events.jsonl` (timestamped), `diffs/final.diff`, `metrics.json`। যা CLI expose করে না (যেমন opencode/hermes-এর per-call token usage) সেটি `NOT EXPOSED`/null — কোনো কিছু বানানো হয়নি।
- **API key:** সব আর্টিফ্যাক্টে capture-time-এ redacted (`nvapi-***REDACTED***`)।

## সীমাবদ্ধতা

- NIM free-tier endpoint: congestion-এর ভ্যারিয়েন্স আছে (opencode fast A-তে ৩৭৫s, অন্য সময় ৭৪s)।
- Sandbox প্রতিটা shell-call শেষে detached process মেরে দেয় — তাই ম্যাট্রিক্স foreground ওয়েভে চলেছে; ৬০০s call-ক্যাপের ভেতরে ক্যাপ-বাজেট সেট করা হয়েছে।
- hermes/opencode-এর skipped সেলগুলো "হার" নয় — "নির্ধারিত অসামঞ্জস্য" (deterministic incompatibility); আলাদা করে রিপোর্ট করা হয়েছে।

## ডেটা ফাইল

- `data/all_runs.jsonl` — ৬৪ সারি (৫৩ রিয়েল রান + ১১ স্কিপ-রেকর্ড), প্রতি সারিতে সম্পূর্ণ মেটাডেটা + verification।
- `data/scorecard.json` — ক্যাটাগরি × CLI স্কোর।
- র-ট্রেস: এই রিপোর্টের উৎস `/home/z/my-project/bench/runs/<run_id>/` (GitHub-এ রান-আর্কাইভ আলাদা; এখানে সারাংশ-প্রমাণ)।
