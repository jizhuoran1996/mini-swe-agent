#!/usr/bin/env python3
"""GPUv1-D04 (debug variant): deploy a natural-language SQLite query tool.

Pipeline
--------
1. Verify the frozen inputs (schema.sql / chinook.sqlite / requests.jsonl) against the
   manifest hashes; refuse to run when required inputs are missing.
2. Load Qwen2.5-Coder-0.5B-Instruct on CUDA in bfloat16 (greedy decoding, <=256 new
   tokens) from the read-only /models path declared in manifest.json.
3. For every question: build a schema+question prompt, generate SQL, extract a single
   read-only statement, validate it (SELECT/WITH only, no write/DDL keywords, single
   statement), execute it on a mode=ro SQLite connection with a 3 s progress-handler
   timeout, and archive SQL / raw model output / token ids / real results or a real
   execution error.
4. Write output/answers.jsonl and output/run.json (hashes, config, timings, GPU usage,
   per-question status, before/after database hash to prove read-only access).

No gold SQL is read, generated or invented anywhere in this program.  Agent-authored
answer text is never substituted for model output.

Subcommands
-----------
  doctor --input INPUT            inspect files/deps, no model execution, exit 78 if missing
  run    --input INPUT --output OUTPUT
  query  --database PATH --question TEXT --output JSON
"""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

TASK_ID = "GPUv1-D04"
REQUIRED_INPUTS = ["schema.sql", "chinook.sqlite", "requests.jsonl", "manifest.json"]
DEFAULT_MODEL_PATH = "/models/Qwen--Qwen2.5-Coder-0.5B-Instruct"
DEFAULT_MODEL_REVISION = "ea3f2471cf1b1f0db85067f1ef93848e38e88c25"
DEFAULT_MAX_NEW_TOKENS = 256
EXEC_TIMEOUT_S = 3.0
ROW_LIMIT = 50000

FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|pragma|vacuum|reindex|"
    r"replace|truncate|begin|commit|rollback|savepoint|grant|revoke|analyze)\b",
    re.I,
)
READONLY_START_RE = re.compile(r"^\s*(select|with)\b", re.I)


# --------------------------------------------------------------------------- helpers
def sha256_file(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(buf)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def strip_string_literals(sql):
    """Blank out quoted literals so keyword/';' checks cannot be fooled by strings."""
    out, i, n = [], 0, len(sql)
    while i < n:
        c = sql[i]
        if c in ("'", '"', "`"):
            q = c
            i += 1
            while i < n:
                if sql[i] == q:
                    if i + 1 < n and sql[i + 1] == q:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(" ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _scan_first_statement(cand):
    """Copy text up to the first unquoted ';'."""
    out, i, n = [], 0, len(cand)
    while i < n:
        c = cand[i]
        if c in ("'", '"', "`"):
            q = c
            out.append(c)
            i += 1
            while i < n:
                ch = cand[i]
                out.append(ch)
                if ch == q:
                    if i + 1 < n and cand[i + 1] == q:
                        out.append(cand[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
        elif c == ";":
            break
        else:
            out.append(c)
            i += 1
    return "".join(out)


def extract_sql(text):
    """Extract the first SELECT/WITH statement from raw model output."""
    if not text:
        return ""
    m = re.search(r"```(?:sql|sqlite)?\s*(.*?)```", text, re.S | re.I)
    cand = m.group(1) if m else text
    m = re.search(r"\b(select|with)\b", cand, re.I)
    if not m:
        return ""
    return _scan_first_statement(cand[m.start():]).strip()


def validate_sql(sql):
    """Return None when the SQL is an acceptable read-only single statement."""
    if not sql:
        return "empty SQL"
    s = strip_string_literals(sql)
    if not READONLY_START_RE.match(s):
        return "statement does not start with SELECT or WITH"
    bad = FORBIDDEN_RE.search(s)
    if bad:
        return "forbidden keyword present: %s" % bad.group(0)
    if ";" in s:
        return "multiple statements detected"
    return None


def _json_value(v):
    if isinstance(v, bytes):
        return v.hex()
    if isinstance(v, (int, float, str)) or v is None:
        return v
    return str(v)


def execute_sql(conn, sql, timeout=EXEC_TIMEOUT_S):
    """Execute one validated read-only statement; real errors are returned verbatim."""
    started = time.monotonic()

    def _handler():
        return 1 if (time.monotonic() - started) > timeout else 0

    conn.set_progress_handler(_handler, 2000)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in (cur.description or [])]
        rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 - real sqlite error is the deliverable
        return None, "%s: %s" % (type(exc).__name__, exc), time.monotonic() - started
    finally:
        conn.set_progress_handler(None, 0)
    truncated = len(rows) > ROW_LIMIT
    rows = rows[:ROW_LIMIT]
    payload = {
        "columns": cols,
        "rows": [[_json_value(v) for v in r] for r in rows],
        "row_count": len(rows),
        "truncated": truncated,
    }
    return payload, None, time.monotonic() - started


def open_readonly(db_path):
    conn = sqlite3.connect("file:%s?mode=ro" % Path(db_path).resolve(), uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def schema_from_sqlite(db_path):
    conn = open_readonly(db_path)
    try:
        rows = conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
    finally:
        conn.close()
    return "\n\n".join(r[2] for r in rows)


def read_requests(path):
    reqs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            qid = obj.get("id", obj.get("question_id", obj.get("qid")))
            question = (
                obj.get("question")
                or obj.get("question_text")
                or obj.get("nl_question")
                or obj.get("text")
            )
            if qid is None or question is None:
                raise ValueError("request missing id/question: %s" % line[:200])
            reqs.append({"id": str(qid), "question": str(question), "source": obj})
    return reqs


def model_info(input_dir):
    path, rev = DEFAULT_MODEL_PATH, DEFAULT_MODEL_REVISION
    mpath = Path(input_dir) / "manifest.json"
    if mpath.exists():
        try:
            man = json.loads(mpath.read_text(encoding="utf-8"))
            path = man.get("model_container_path", path)
            rev = man.get("model_revision", rev)
        except Exception:
            pass
    return path, rev


# --------------------------------------------------------------------------- doctor
def cmd_doctor(args):
    in_dir = Path(args.input)
    report = {"task_id": TASK_ID, "input_dir": str(in_dir), "checks": {}, "missing": []}

    manifest_hash = {}
    mpath = in_dir / "manifest.json"
    if mpath.exists():
        try:
            manifest_hash = json.loads(mpath.read_text(encoding="utf-8")).get("files", {}) or {}
        except Exception as exc:
            report["missing"].append("manifest.json unreadable: %s" % exc)

    for name in REQUIRED_INPUTS:
        p = in_dir / name
        entry = {"exists": p.exists()}
        if p.exists():
            entry["bytes"] = p.stat().st_size
            entry["sha256"] = sha256_file(p)
            if name in manifest_hash:
                entry["expected_sha256"] = manifest_hash[name]
                entry["hash_ok"] = entry["sha256"] == manifest_hash[name]
                if not entry["hash_ok"]:
                    report["missing"].append("%s hash mismatch" % name)
        else:
            report["missing"].append(name)
        report["checks"][name] = entry

    db = in_dir / "chinook.sqlite"
    if db.exists():
        with open(db, "rb") as f:
            report["checks"]["chinook.sqlite"]["sqlite_magic"] = (
                f.read(16) == b"SQLite format 3\x00"
            )

    model_path, revision = model_info(in_dir)
    mp = Path(model_path)
    model_files = {"dir_exists": mp.is_dir()}
    for fname in ("config.json", "tokenizer.json", "model.safetensors"):
        model_files[fname] = (mp / fname).exists()
        if not model_files[fname]:
            report["missing"].append("model file %s" % (mp / fname))
    model_files["revision"] = revision
    report["checks"]["model"] = model_files

    try:
        import torch  # noqa: WPS433 - imported lazily, no weights loaded
        report["checks"]["torch"] = {
            "version": torch.__version__,
            "cuda_available": bool(torch.cuda.is_available()),
            "device_count": torch.cuda.device_count(),
        }
        if not torch.cuda.is_available():
            report["missing"].append("CUDA device not available")
        else:
            report["checks"]["torch"]["device_name"] = torch.cuda.get_device_name(0)
    except Exception as exc:
        report["checks"]["torch"] = {"error": str(exc)}
        report["missing"].append("torch unavailable: %s" % exc)

    try:
        import transformers  # noqa: WPS433
        report["checks"]["transformers"] = {"version": transformers.__version__}
    except Exception as exc:
        report["checks"]["transformers"] = {"error": str(exc)}
        report["missing"].append("transformers unavailable: %s" % exc)

    report["available"] = not report["missing"]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["available"] else 78


# --------------------------------------------------------------------------- model
def load_model(model_path, revision):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this task but is not available")
    kw = {"local_files_only": True}
    try:
        tok = AutoTokenizer.from_pretrained(model_path, revision=revision, **kw)
        model = AutoModelForCausalLM.from_pretrained(
            model_path, revision=revision, torch_dtype=torch.bfloat16, **kw
        )
    except TypeError:
        tok = AutoTokenizer.from_pretrained(model_path, **kw)
        model = AutoModelForCausalLM.from_pretrained(
            model_path, torch_dtype=torch.bfloat16, **kw
        )
    model = model.to("cuda")
    model.eval()
    return tok, model


def build_prompt(tok, schema, question):
    messages = [
        {
            "role": "system",
            "content": (
                "You are a SQLite SQL expert. Given a database schema and a "
                "natural-language question, output exactly one read-only SQLite "
                "SELECT query that answers it. Use only tables and columns that "
                "exist in the schema. Output the SQL statement alone: no "
                "explanation, no markdown fences."
            ),
        },
        {
            "role": "user",
            "content": "### Database schema\n%s\n\n### Question\n%s\n\n### SQL"
            % (schema, question),
        },
    ]
    try:
        return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        return "%s\n\nQuestion: %s\nSQL:" % (schema, question)


def generate_sql(tok, model, schema, question, max_new_tokens):
    import torch

    prompt = build_prompt(tok, schema, question)
    enc = tok(prompt, return_tensors="pt", add_special_tokens=False).to("cuda")
    torch.cuda.synchronize()
    ev0 = torch.cuda.Event(enable_timing=True)
    ev1 = torch.cuda.Event(enable_timing=True)
    ev0.record()
    with torch.no_grad():
        out = model.generate(
            **enc,
            do_sample=False,
            num_beams=1,
            max_new_tokens=max_new_tokens,
            pad_token_id=tok.eos_token_id,
        )
    ev1.record()
    torch.cuda.synchronize()
    gpu_ms = ev0.elapsed_time(ev1)
    prompt_len = int(enc["input_ids"].shape[1])
    token_ids = out[0][prompt_len:].tolist()
    raw = tok.decode(token_ids, skip_special_tokens=True)
    return raw, token_ids, gpu_ms


def answer_question(tok, model, schema, question, conn, max_new_tokens):
    rec = {"raw": "", "token_ids": [], "sql": "", "results": None,
           "execution_error": None, "execution_status": "error"}
    t0 = time.monotonic()
    raw, token_ids, gpu_ms = generate_sql(tok, model, schema, question, max_new_tokens)
    rec["raw"] = raw
    rec["token_ids"] = token_ids
    rec["gen_seconds"] = time.monotonic() - t0
    rec["gpu_ms"] = gpu_ms
    sql = extract_sql(raw)
    rec["sql"] = sql
    reason = validate_sql(sql)
    if reason is not None:
        rec["execution_status"] = "rejected"
        rec["execution_error"] = "rejected: %s" % reason
        rec["exec_seconds"] = 0.0
        return rec
    results, err, secs = execute_sql(conn, sql)
    rec["exec_seconds"] = secs
    if err is not None:
        rec["execution_status"] = "error"
        rec["execution_error"] = err
    else:
        rec["execution_status"] = "ok"
        rec["results"] = results
    return rec


# --------------------------------------------------------------------------- run
def cmd_run(args):
    in_dir, out_dir = Path(args.input), Path(args.output)
    missing = [n for n in REQUIRED_INPUTS if not (in_dir / n).exists()]
    if missing:
        print(json.dumps({"error": "missing inputs", "missing": missing}), file=sys.stderr)
        return 78
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((in_dir / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest.get("files", {}) or {}
    input_hashes = {}
    for name in ("schema.sql", "chinook.sqlite", "requests.jsonl"):
        digest = sha256_file(in_dir / name)
        input_hashes[name] = {
            "sha256": digest,
            "expected": expected.get(name),
            "match": expected.get(name) is None or expected.get(name) == digest,
        }

    import torch
    if not torch.cuda.is_available():
        print(json.dumps({"error": "CUDA device required"}), file=sys.stderr)
        return 78

    model_path, revision = model_info(in_dir)
    tok, model = load_model(model_path, revision)

    schema = (in_dir / "schema.sql").read_text(encoding="utf-8", errors="replace")
    requests = read_requests(in_dir / "requests.jsonl")
    db_path = in_dir / "chinook.sqlite"
    db_hash_before = sha256_file(db_path)
    conn = open_readonly(db_path)

    records, per_question = [], []
    wall0 = time.monotonic()
    gen_total = exec_total = gpu_ms_total = 0.0
    counts = {"questions": 0, "ok": 0, "error": 0, "rejected": 0, "infrastructure_error": 0}

    try:
        for req in requests:
            counts["questions"] += 1
            try:
                rec = answer_question(tok, model, schema, req["question"], conn,
                                      args.max_new_tokens)
            except Exception as exc:  # noqa: BLE001
                counts["infrastructure_error"] += 1
                rec = {"raw": "", "token_ids": [], "sql": "", "results": None,
                       "execution_error": "infrastructure: %s: %s" % (type(exc).__name__, exc),
                       "execution_status": "infrastructure_error",
                       "gen_seconds": 0.0, "exec_seconds": 0.0, "gpu_ms": 0.0}
            out_rec = {
                "id": req["id"],
                "question": req["question"],
                "sql": rec["sql"],
                "raw": rec["raw"],
                "token_ids": rec["token_ids"],
                "execution_status": rec["execution_status"],
                "gen_seconds": rec["gen_seconds"],
                "exec_seconds": rec["exec_seconds"],
                "gpu_ms": rec["gpu_ms"],
            }
            if rec["results"] is not None:
                out_rec["results"] = rec["results"]
            if rec["execution_error"] is not None:
                out_rec["execution_error"] = rec["execution_error"]
            records.append(out_rec)
            gen_total += rec["gen_seconds"]
            exec_total += rec["exec_seconds"]
            gpu_ms_total += rec["gpu_ms"]
            status = rec["execution_status"]
            if status == "ok":
                counts["ok"] += 1
            elif status == "rejected":
                counts["rejected"] += 1
            elif status == "infrastructure_error":
                pass
            else:
                counts["error"] += 1
            per_question.append({
                "id": req["id"],
                "status": status,
                "sql": rec["sql"],
                "gen_seconds": round(rec["gen_seconds"], 4),
                "exec_seconds": round(rec["exec_seconds"], 4),
                "gpu_ms": round(rec["gpu_ms"], 3),
                "error": rec["execution_error"],
            })
    finally:
        conn.close()

    wall = time.monotonic() - wall0
    db_hash_after = sha256_file(db_path)

    with open(out_dir / "answers.jsonl", "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    props = torch.cuda.get_device_properties(0)
    run = {
        "task_id": TASK_ID,
        "variant": "debug_only",
        "goal": "generate read-only SQLite SQL with a local CUDA model and archive real results",
        "model": {
            "repo": manifest.get("model_repo"),
            "revision": revision,
            "path": model_path,
            "dtype": "bfloat16",
            "device": torch.cuda.get_device_name(0),
            "decoding": "greedy (do_sample=False, num_beams=1)",
            "max_new_tokens": args.max_new_tokens,
        },
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": props.name,
            "gpu_total_memory_gib": round(props.total_memory / 2 ** 30, 2),
        },
        "inputs": input_hashes,
        "database": {
            "path": str(db_path),
            "sha256_before": db_hash_before,
            "sha256_after": db_hash_after,
            "unchanged": db_hash_before == db_hash_after,
            "access_mode": "sqlite URI mode=ro + PRAGMA query_only=ON",
            "per_statement_timeout_s": EXEC_TIMEOUT_S,
        },
        "counts": counts,
        "timings_s": {
            "wall": round(wall, 4),
            "generation_total": round(gen_total, 4),
            "execution_total": round(exec_total, 4),
        },
        "gpu": {
            "generation_gpu_ms_total": round(gpu_ms_total, 3),
            "peak_allocated_gib": round(torch.cuda.max_memory_allocated() / 2 ** 30, 3),
        },
        "per_question": per_question,
        "notes": [
            "No gold SQL was available or used; agent text never replaces model output.",
            "Semantic correctness of generated SQL is not claimed; execution status and real "
            "errors are archived verbatim.",
            "Database file hash verified unchanged after the run.",
        ],
    }
    with open(out_dir / "run.json", "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2, ensure_ascii=False)

    print(json.dumps({"answers": str(out_dir / "answers.jsonl"),
                      "run": str(out_dir / "run.json"),
                      "counts": counts}, ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------- query
def cmd_query(args):
    db_path = Path(args.database)
    if not db_path.exists():
        print(json.dumps({"error": "database not found", "path": str(db_path)}), file=sys.stderr)
        return 78
    import torch
    if not torch.cuda.is_available():
        print(json.dumps({"error": "CUDA device required"}), file=sys.stderr)
        return 78

    model_path, revision = model_info(args.input) if args.input else (DEFAULT_MODEL_PATH,
                                                                       DEFAULT_MODEL_REVISION)
    tok, model = load_model(model_path, revision)
    schema = schema_from_sqlite(db_path)
    conn = open_readonly(db_path)
    try:
        rec = answer_question(tok, model, schema, args.question, conn, args.max_new_tokens)
    finally:
        conn.close()

    payload = {
        "task_id": TASK_ID,
        "command": "query",
        "database": str(db_path.resolve()),
        "question": args.question,
        "sql": rec["sql"],
        "execution_status": rec["execution_status"],
        "raw": rec["raw"],
        "token_ids": rec["token_ids"],
        "gen_seconds": rec["gen_seconds"],
        "exec_seconds": rec["exec_seconds"],
        "gpu_ms": rec["gpu_ms"],
        "model": {"path": model_path, "revision": revision, "dtype": "bfloat16",
                  "greedy": True, "max_new_tokens": args.max_new_tokens},
    }
    if rec["results"] is not None:
        payload["results"] = rec["results"]
    if rec["execution_error"] is not None:
        payload["execution_error"] = rec["execution_error"]
    out_path = Path(args.output)
    if out_path.parent and str(out_path.parent):
        out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(json.dumps({"output": str(out_path), "execution_status": rec["execution_status"]}))
    return 0 if rec["execution_status"] in ("ok", "error", "rejected") else 1


# --------------------------------------------------------------------------- cli
def build_parser():
    p = argparse.ArgumentParser(
        prog="main.py",
        description="GPUv1-D04 debug: natural-language SQLite query tool (local CUDA Qwen2.5-Coder).",
    )
    sub = p.add_subparsers(dest="command")

    pr = sub.add_parser("run", help="generate + execute SQL for every input question")
    pr.add_argument("--input", required=True, help="input directory")
    pr.add_argument("--output", required=True, help="output directory")
    pr.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)

    pd = sub.add_parser("doctor", help="inspect required inputs/dependencies without running the model")
    pd.add_argument("--input", required=True, help="input directory")

    pq = sub.add_parser("query", help="answer one new question against a database")
    pq.add_argument("--database", required=True)
    pq.add_argument("--question", required=True)
    pq.add_argument("--output", required=True, help="JSON output path")
    pq.add_argument("--input", default=None, help="optional input dir for manifest/model lookup")
    pq.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "query":
        return cmd_query(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
