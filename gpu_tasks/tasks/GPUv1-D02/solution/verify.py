#!/usr/bin/env python3
"""Independent verification + quality reporting for GPUv1-D02 outputs.

Produces (in --output):
  verification.json  : coverage, reload equality, independent greedy token
                       recomputation, live HTTP service checks.
  quality_report.json: ROUGE-like / summary-correctness report.  GovReport
                       test references are NOT provided, so reference ROUGE is
                       explicitly reported as not computable; only intrinsic
                       checks (copying, emptiness, compression, overlap) are
                       reported and they are NOT a formal quality claim.

Run: python solution/verify.py --input input --output output
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/models/Qwen--Qwen2.5-0.5B-Instruct"
MARKER = "\ue000"
SYSTEM_PROMPT = (
    "You are a careful assistant that writes accurate, readable summaries of "
    "long U.S. government reports."
)
USER_TEMPLATE = (
    "Write a concise, faithful summary of the following U.S. government report "
    "in 3 to 5 sentences. Keep the main topic, key findings, and any "
    "recommendations stated in the report.\n\n"
    "Report:\n" + MARKER + "\n\nSummary:"
)


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def prompt_parts(tok) -> tuple:
    text = tok.apply_chat_template(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": USER_TEMPLATE}],
        tokenize=False, add_generation_prompt=True,
    )
    head, tail = text.split(MARKER)
    return (tok(head, add_special_tokens=False)["input_ids"],
            tok(tail, add_special_tokens=False)["input_ids"])


def greedy_recompute(model, tok, head, tail, document, max_in=2048, max_new=128):
    """Independent token-by-token greedy loop (KV cache), returns new ids."""
    doc_ids = tok(document, add_special_tokens=False)["input_ids"][:max_in]
    ids = head + doc_ids + tail
    cur = torch.tensor([ids], dtype=torch.long, device="cuda")
    past = None
    generated: List[int] = []
    with torch.inference_mode():
        for _ in range(max_new):
            out = model(input_ids=cur, past_key_values=past, use_cache=True,
                        attention_mask=torch.ones((1, ids.__len__() + len(generated)), dtype=torch.long, device="cuda"))
            nxt = int(torch.argmax(out.logits[0, -1]))
            generated.append(nxt)
            if nxt == tok.eos_token_id:
                break
            past = out.past_key_values
            cur = torch.tensor([[nxt]], dtype=torch.long, device="cuda")
    return generated


def serve_checks(output_dir: str) -> Dict[str, Any]:
    port = 8231
    proc = subprocess.Popen(
        [sys.executable, "solution/main.py", "serve", "--input", "input",
         "--output", output_dir, "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    res: Dict[str, Any] = {"spawned": True, "ready_after_cuda_load": False}

    def req(path, method="GET", body=None, timeout=10):
        r = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())

    try:
        for _ in range(120):
            try:
                st, h = req("/health")
                res["health"] = h
                res["ready_after_cuda_load"] = bool(h.get("ready") and h.get("device") == "cuda")
                break
            except Exception:
                time.sleep(0.5)
        docs = read_jsonl("input/requests.jsonl")
        st, r1 = req("/infer", "POST", {"id": "verify-new-1", "document": docs[0]["document"]})
        res["new_request"] = {"status": st, "id": r1["id"], "num_new_tokens": r1["num_new_tokens"],
                              "truncated": r1["truncated"], "nonempty": bool(r1["summary"].strip())}
        time.sleep(5)
        st, r2 = req("/infer", "POST", {"id": "verify-new-2", "document": docs[5]["document"]})
        res["after_idle_request"] = {"status": st, "id": r2["id"], "num_new_tokens": r2["num_new_tokens"]}
        try:
            req("/infer", "POST", {"id": "bad"})
            res["bad_request_status"] = 200
        except urllib.error.HTTPError as e:
            res["bad_request_status"] = e.code
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            out = proc.communicate(timeout=30)[0]
        except subprocess.TimeoutExpired:
            proc.kill()
            out = proc.communicate()[0]
        res["exit_code"] = proc.returncode
        res["sigterm_clean"] = proc.returncode == 0 and "stopped" in out
        s = socket.socket()
        s.settimeout(2)
        try:
            s.connect(("127.0.0.1", port))
            res["port_closed"] = False
        except Exception:
            res["port_closed"] = True
        s.close()
    return res


# --------------------------------------------------------------------------- #
# lightweight intrinsic quality metrics (no references available)
# --------------------------------------------------------------------------- #
def word_ngrams(words, n):
    return [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]


def rouge_n_f1(pred_words, ref_words, n):
    p, r = word_ngrams(pred_words, n), word_ngrams(ref_words, n)
    if not p or not r:
        return 0.0
    from collections import Counter
    cp, cr = Counter(p), Counter(r)
    overlap = sum((cp & cr).values())
    if overlap == 0:
        return 0.0
    prec, rec = overlap / len(p), overlap / len(r)
    return 2 * prec * rec / (prec + rec)


def lcs_word_len(a, b):
    """Longest common contiguous word run length (copy detection)."""
    bset = {}
    for i, w in enumerate(b):
        bset.setdefault(w, []).append(i)
    best = 0
    for i, w in enumerate(a):
        for j in bset.get(w, ()):  # only matching first words
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            best = max(best, k)
    return best


def build_quality_report(rows, docs) -> Dict[str, Any]:
    per = []
    for r, d in zip(rows, docs):
        summ = r["summary"]
        sw = summ.split()
        dw = d["document"].split()
        per.append({
            "id": r["id"],
            "summary_chars": len(summ),
            "summary_words": len(sw),
            "compression_ratio_words": (len(sw) / len(dw)) if dw else None,
            "empty": not bool(summ.strip()),
            "summary_exact_substring_of_document": summ in d["document"],
            "summary_is_document_prefix": d["document"].startswith(summ) if summ else False,
            "longest_common_word_run_with_document": lcs_word_len(sw, dw),
            "distinct_3gram_ratio": (
                len(set(word_ngrams(sw, 3))) / max(1, len(word_ngrams(sw, 3)))
            ),
            "rouge1_f1_vs_source_document": rouge_n_f1(sw, dw, 1),
            "rouge2_f1_vs_source_document": rouge_n_f1(sw, dw, 2),
        })
    copied = [p for p in per if p["summary_exact_substring_of_document"]
              or p["summary_is_document_prefix"]]
    return {
        "report_type": "summary_quality_and_correctness",
        "scale": "debug_only",
        "formal_large_tested": False,
        "reference_summaries_available": False,
        "rouge_vs_reference": {
            "computable": False,
            "reason": ("input/requests.jsonl contains only id/document; GovReport "
                       "reference summaries are not provided, so reference ROUGE "
                       "cannot and is not claimed to pass."),
        },
        "rouge_vs_source_document_note": (
            "rougeN_f1_vs_source_document is a transparency metric describing "
            "lexical overlap with the (truncated) source text. It is NOT a "
            "summary-correctness or reference-ROUGE score."),
        "copying_guard": {
            "summaries_that_are_document_substring_or_prefix": len(copied),
            "violation_ids": [p["id"] for p in copied],
            "status": "pass" if not copied else "fail",
            "max_longest_common_word_run": max(
                (p["longest_common_word_run_with_document"] for p in per), default=0),
        },
        "empty_summaries": [p["id"] for p in per if p["empty"]],
        "per_summary": per,
        "disclaimer": ("Debug-variant intrinsic checks only. No reference "
                       "summaries exist here; no formal summary-quality or "
                       "ROUGE pass is asserted."),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="input")
    ap.add_argument("--output", default="output")
    ap.add_argument("--skip-serve", action="store_true")
    ap.add_argument("--max-recompute", type=int, default=16)
    args = ap.parse_args()

    in_rows = read_jsonl(os.path.join(args.input, "requests.jsonl"))
    summaries = read_jsonl(os.path.join(args.output, "summaries.jsonl"))
    reloaded = read_jsonl(os.path.join(args.output, "reloaded.jsonl"))

    ids_in = [r["id"] for r in in_rows]
    ids_sum = [r["id"] for r in summaries]
    coverage = {
        "num_input": len(ids_in),
        "num_summaries": len(ids_sum),
        "missing": sorted(set(ids_in) - set(ids_sum)),
        "extra": sorted(set(ids_sum) - set(ids_in)),
        "duplicates": len(ids_sum) - len(set(ids_sum)),
        "complete": sorted(ids_in) == sorted(ids_sum) and len(ids_sum) == len(set(ids_sum)),
    }

    rmap = {r["id"]: r for r in reloaded}
    reload_mismatch = []
    for s in summaries:
        r = rmap.get(s["id"])
        if r is None or r["token_ids"] != s["token_ids"] or r["summary"] != s["summary"]:
            reload_mismatch.append(s["id"])
    reload_check = {
        "num_reloaded": len(reloaded),
        "mismatched_ids": reload_mismatch,
        "equal": not reload_mismatch and len(reloaded) == len(summaries),
    }

    # Independent greedy token recomputation with a from-disk model and a
    # hand-written token-by-token argmax loop (does not call main.py's code).
    tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16, local_files_only=True).to("cuda").eval()
    head, tail = prompt_parts(tok)
    docmap = {r["id"]: r["document"] for r in in_rows}
    recompute = {"checked": 0, "matched": 0, "mismatches": []}
    for s in summaries[: args.max_recompute]:
        got = greedy_recompute(model, tok, head, tail, docmap[s["id"]],
                               max_new=128)
        recompute["checked"] += 1
        if got == s["token_ids"]:
            recompute["matched"] += 1
        else:
            recompute["mismatches"].append(
                {"id": s["id"], "stored_len": len(s["token_ids"]), "recomputed_len": len(got),
                 "first_diff": next((i for i, (a, b) in enumerate(zip(got, s["token_ids"])) if a != b), None)})
    recompute["all_match"] = recompute["checked"] == recompute["matched"]
    del model
    torch.cuda.empty_cache()

    serve = {"skipped": True} if args.skip_serve else serve_checks(args.output)

    verification = {
        "task_id": "GPUv1-D02",
        "coverage": coverage,
        "reload_check": reload_check,
        "greedy_token_recompute": recompute,
        "serve_checks": serve,
        "all_checks_pass": bool(
            coverage["complete"] and reload_check["equal"] and recompute["all_match"]
            and (serve.get("skipped") or (
                serve.get("ready_after_cuda_load") and serve.get("new_request", {}).get("status") == 200
                and serve.get("after_idle_request", {}).get("status") == 200
                and serve.get("sigterm_clean") and serve.get("port_closed")))),
    }
    with open(os.path.join(args.output, "verification.json"), "w", encoding="utf-8") as fh:
        json.dump(verification, fh, ensure_ascii=False, indent=2)

    quality = build_quality_report(summaries, in_rows)
    with open(os.path.join(args.output, "quality_report.json"), "w", encoding="utf-8") as fh:
        json.dump(quality, fh, ensure_ascii=False, indent=2)

    print(json.dumps({k: verification[k] for k in
                      ["coverage", "reload_check", "greedy_token_recompute"]}, ensure_ascii=False))
    print("serve_checks:", json.dumps(serve, ensure_ascii=False))
    print("quality copying_guard:", json.dumps(quality["copying_guard"], ensure_ascii=False))
    print("ALL_CHECKS_PASS:", verification["all_checks_pass"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
