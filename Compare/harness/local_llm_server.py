#!/usr/bin/env python3
"""Local OpenAI-compatible server for inference-optimization/Qwen3.8-1.0B-A0.6B.

1.93GB RAM, 1B MoE (0.6B active) — CPU-only inference for the OFFLINE benchmark
round. Serves the same wire contract the SHS Code agents (and the forensic
bench proxy) already speak:

  POST /v1/chat/completions   (also /chat/completions)  — non-streaming + SSE
  GET  /v1/models             (also /models)
  GET  /health

Qwen3.5 wire format handled:
  - reasoning:  <think>...</think>            -> message.reasoning_content
  - tool calls: <function=NAME>
                   <parameter=K>value</parameter>
                </function>                    -> message.tool_calls[]
  - tool results rendered by the chat template as <tool_response> user turns

Any "model" name is accepted and echoed (the harness switches model names for
task-25; the local server serves exactly one model).
"""
import asyncio
import json
import os
import re
import threading
import time
from pathlib import Path

MODEL_DIR = "/home/z/my-project/models/Qwen3.8-1.0B-A0.6B"
PORT = int(os.environ.get("LOCAL_LLM_PORT", "8090"))
MODEL_NAME = os.environ.get("LOCAL_LLM_NAME", "local-qwen3-1b")

MAX_INPUT_TOKENS = 24000
MAX_NEW_TOKENS_CAP = 2048
DEFAULT_MAX_TOKENS = 3072
GEN_TIMEOUT_GUARD_S = 540.0  # proxy upstream timeout is 600s — stay under it

THINK_END = "</think>"
FUNC_RE = re.compile(r"<function=([A-Za-z0-9_.\-]+)>(.*?)</function>", re.DOTALL)
PARAM_RE = re.compile(r"<parameter=([^>\n]+)>(.*?)</parameter>", re.DOTALL)

import torch  # noqa: E402

torch.set_num_threads(2)
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass

from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

print(f"[local-llm] loading tokenizer from {MODEL_DIR}", flush=True)
TOK = AutoTokenizer.from_pretrained(MODEL_DIR)
CHAT_TEMPLATE = Path(MODEL_DIR, "chat_template.jinja").read_text()

print("[local-llm] loading model (bf16, cpu) — ~1.9GB", flush=True)
T0 = time.time()
MODEL = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.bfloat16)
MODEL.eval()
print(f"[local-llm] model loaded in {time.time()-T0:.1f}s, "
      f"params={sum(p.numel() for p in MODEL.parameters())/1e9:.2f}B", flush=True)

EOS_IDS = set()
for tid in ([MODEL.config.eos_token_id] if isinstance(MODEL.config.eos_token_id, int)
            else (MODEL.config.eos_token_id or [])):
    EOS_IDS.add(tid)
if not EOS_IDS:
    EOS_IDS.add(TOK.eos_token_id or 248044)

GEN_LOCK = threading.Lock()
GEN_STATE = {"tok_s": 8.0, "last_gen_s": 0.0, "requests": 0, "errors": 0}


# ---------------- message normalization ----------------

def normalize_messages(messages):
    """OpenAI wire messages -> what the jinja template expects.

    - assistant.tool_calls[].function.arguments arrives as a JSON STRING from
      the OpenAI SDK; the template iterates arguments|items and needs a dict.
    - The Qwen3.5 template requires the system message at index 0 and raises
      otherwise; OpenAI semantics allow system messages anywhere (SHS Code
      sends a last-position chat directive). Merge all system contents into
      one leading system message — same adaptation vLLM/llama.cpp make.
    """
    sys_parts = []
    rest = []
    for m in messages:
        m = dict(m)
        role = m.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            role = "user"
            m["role"] = "user"
        if role == "assistant" and m.get("tool_calls"):
            tcs = []
            for tc in m["tool_calls"]:
                tc = dict(tc)
                fn = dict(tc.get("function") or {})
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args) if args.strip() else {}
                    except json.JSONDecodeError:
                        args = {"_raw": args}
                fn["arguments"] = args if isinstance(args, dict) else {"_raw": str(args)}
                tc["function"] = fn
                tcs.append(tc)
            m["tool_calls"] = tcs
        # content can be a list of parts
        if isinstance(m.get("content"), list):
            m["content"] = "".join(
                p.get("text", "") for p in m["content"] if isinstance(p, dict))
        if role == "system":
            c = (m.get("content") or "").strip()
            if c:
                sys_parts.append(c)
        else:
            rest.append(m)
    out = []
    if sys_parts:
        out.append({"role": "system", "content": "\n\n".join(sys_parts)})
    out.extend(rest)
    return out


def truncate_messages(messages):
    """Hard cap input length: drop oldest non-system turns (middle-out)."""
    probe = TOK.apply_chat_template(normalize_messages(messages), tokenize=False,
                                    chat_template=CHAT_TEMPLATE)
    n = len(TOK.encode(probe))
    if n <= MAX_INPUT_TOKENS:
        return messages, n
    sys = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    while rest and n > MAX_INPUT_TOKENS:
        rest = rest[2:] if len(rest) > 2 else rest[1:]
        probe = TOK.apply_chat_template(normalize_messages(sys + rest), tokenize=False,
                                        chat_template=CHAT_TEMPLATE)
        n = len(TOK.encode(probe))
    note = {"role": "user", "content": "[context auto-truncated by local server]"}
    return sys + [note] + rest[-10:], n


# ---------------- generation ----------------

def build_prompt(messages, tools):
    msgs = normalize_messages(messages)
    kw = {}
    if tools:
        kw["tools"] = tools
    text = TOK.apply_chat_template(msgs, tokenize=False, chat_template=CHAT_TEMPLATE,
                                   **kw)
    return text


def generate_once(prompt_text, temperature, max_new_tokens):
    ids = TOK.encode(prompt_text, return_tensors="pt")
    max_new = min(int(max_new_tokens or DEFAULT_MAX_TOKENS), MAX_NEW_TOKENS_CAP)
    # time-guard: never plan more tokens than the proxy timeout allows
    budget = int(GEN_STATE["tok_s"] * GEN_TIMEOUT_GUARD_S)
    if budget > 256:
        max_new = min(max_new, budget)
    gen_kwargs = dict(max_new_tokens=max_new, do_sample=False,
                      pad_token_id=next(iter(EOS_IDS)))
    temp = float(temperature) if temperature is not None else 0.6
    if temp and temp > 0.0:
        gen_kwargs.update(do_sample=True, temperature=temp, top_p=0.95, top_k=20)
    t0 = time.time()
    with torch.no_grad():
        out = MODEL.generate(ids, **gen_kwargs)
    new = out[0][ids.shape[1]:]
    dt = time.time() - t0
    n_new = int(new.shape[0])
    if dt > 0 and n_new > 0:
        tps = n_new / dt
        # rolling estimate (EMA) for the time guard
        GEN_STATE["tok_s"] = round(0.5 * GEN_STATE["tok_s"] + 0.5 * tps, 2)
    text = TOK.decode(new, skip_special_tokens=True)
    return text, n_new, int(ids.shape[1]), dt


# ---------------- output parsing ----------------

def parse_value(v: str):
    v = v.strip()
    if not v:
        return ""
    if (v[0] in "{[\"" or v in ("true", "false", "null")) or re.fullmatch(r"-?\d+(\.\d+)?", v):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v
    return v


def parse_output(text: str):
    """Split reasoning/content, extract <function> blocks -> OpenAI message."""
    reasoning, content = "", text
    if THINK_END in text:
        idx = text.index(THINK_END)
        reasoning = text[:idx].strip()
        content = text[idx + len(THINK_END):].strip()

    tool_calls = []
    plain_parts = []
    last = 0
    for m in FUNC_RE.finditer(content):
        plain_parts.append(content[last:m.start()])
        last = m.end()
        name, body = m.group(1), m.group(2)
        args = {}
        for pm in PARAM_RE.finditer(body):
            args[pm.group(1).strip()] = parse_value(pm.group(2))
        tool_calls.append({
            "id": f"call_{len(tool_calls)+1}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        })
    plain_parts.append(content[last:])
    plain = "\n".join(p.strip() for p in plain_parts if p.strip()).strip()

    finish = "tool_calls" if tool_calls else "stop"
    msg = {"role": "assistant", "content": plain if plain else ""}
    if reasoning:
        msg["reasoning_content"] = reasoning
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg, finish


def completion_payload(req_model, msg, finish, ptoks, ctoks, stream=False):
    base = {
        "id": f"chatcmpl-local-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req_model or MODEL_NAME,
        "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
        "usage": {"prompt_tokens": ptoks, "completion_tokens": ctoks,
                  "total_tokens": ptoks + ctoks},
    }
    return base


# ---------------- API ----------------

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402

app = FastAPI(title="local-qwen3-1b")


@app.get("/health")
async def health():
    return {"ok": True, "model": MODEL_NAME, "tok_s": GEN_STATE["tok_s"],
            "requests": GEN_STATE["requests"], "errors": GEN_STATE["errors"]}


@app.get("/v1/models")
@app.get("/models")
async def models():
    return {"object": "list", "data": [{"id": MODEL_NAME, "object": "model",
                                        "owned_by": "local"}]}


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid json"})
    GEN_STATE["requests"] += 1
    messages = body.get("messages") or []
    tools = body.get("tools") or None
    if tools and not isinstance(tools, list):
        tools = None
    temperature = body.get("temperature")
    max_tokens = body.get("max_tokens") or body.get("max_completion_tokens") \
        or DEFAULT_MAX_TOKENS
    stream = bool(body.get("stream"))
    req_model = body.get("model") or MODEL_NAME

    if not messages:
        return JSONResponse(status_code=400, content={"error": "no messages"})

    # serialize generation — one model, two CPU cores
    def work():
        try:
            messages_t, _ = truncate_messages(messages)
            prompt = build_prompt(messages_t, tools)
            text, ctoks, ptoks, dt = generate_once(prompt, temperature, max_tokens)
            msg, finish = parse_output(text)
            return msg, finish, ptoks, ctoks
        except Exception as e:
            GEN_STATE["errors"] += 1
            raise

    loop = asyncio.get_event_loop()
    try:
        acq = GEN_LOCK.acquire(timeout=570)
        if not acq:
            return JSONResponse(status_code=503,
                                content={"error": "local model busy — try again"})
        try:
            msg, finish, ptoks, ctoks = await loop.run_in_executor(None, work)
        finally:
            GEN_LOCK.release()
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"error": f"generation failed: {e}"})

    if not stream:
        return completion_payload(req_model, msg, finish, ptoks, ctoks)

    # SSE streaming (chunked after generation; SHS uses non-streaming anyway)
    full = completion_payload(req_model, msg, finish, ptoks, ctoks)

    async def sse():
        cid = full["id"]
        chunk = {"id": cid, "object": "chat.completion.chunk", "created": full["created"],
                 "model": full["model"], "choices": [{"index": 0, "delta": {}, "finish_reason": None}]}
        yield f"data: {json.dumps(chunk)}\n\n"
        if msg.get("reasoning_content"):
            chunk["choices"][0]["delta"] = {"reasoning_content": msg["reasoning_content"]}
            yield f"data: {json.dumps(chunk)}\n\n"
        if msg.get("content"):
            for i in range(0, len(msg["content"]), 40):
                chunk["choices"][0]["delta"] = {"content": msg["content"][i:i+40]}
                yield f"data: {json.dumps(chunk)}\n\n"
        if msg.get("tool_calls"):
            chunk["choices"][0]["delta"] = {"tool_calls": msg["tool_calls"]}
            yield f"data: {json.dumps(chunk)}\n\n"
        chunk["choices"][0]["delta"] = {}
        chunk["choices"][0]["finish_reason"] = finish
        yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    print(f"[local-llm] serving {MODEL_NAME} on http://127.0.0.1:{PORT}/v1", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
