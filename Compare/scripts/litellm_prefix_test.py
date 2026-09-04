#!/usr/bin/env python3
"""Test litellm double-prefix trick for NIM model ids."""
import os, sys
KEY = None
for line in open("/home/z/my-project/.secrets/nim.env"):
    line = line.strip()
    if line.startswith("export NVIDIA_API_KEY="):
        KEY = line.split("=", 1)[1].strip().strip('"')

from litellm import completion

variants = [
    ("double-prefix", "openai/openai/gpt-oss-20b"),
    ("single-prefix", "openai/gpt-oss-20b"),
]
for name, model in variants:
    try:
        r = completion(model=model,
                       api_base="https://integrate.api.nvidia.com/v1",
                       api_key=KEY,
                       messages=[{"role": "user", "content": "Reply with just: OK"}],
                       max_tokens=10, timeout=60)
        content = r.choices[0].message.content
        sent_model = r.model
        print(f"[{name}] model_sent={sent_model} content={content!r} -> OK")
    except Exception as e:
        print(f"[{name}] FAIL: {str(e)[:150]}")
