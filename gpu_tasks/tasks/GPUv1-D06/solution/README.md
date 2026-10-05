# GPUv1-D06 (debug variant) -- per-question understanding catalog for a full road short clip

This solution runs the authentic local **Qwen2.5-VL-3B-Instruct** (BF16, `AutoProcessor`)
on a **real CUDA device**, feeding **all sampled frames of each request** as one ordered
multi-image context (never only the first frame). Greedy decoding, at most 128 new tokens
per question, and `max_pixels <= 65536` per frame.

It is the declared **debug** variant: 8 uniformly sampled frames out of the 16 native
VKITTI2 frames and 3 designer questions. **No Video-MME score and no reference-large
result is claimed.**

## Commands

```bash
python solution/main.py --help                                             # no model loading
python solution/main.py doctor --input input                               # 0 = ready, 78 = missing items
python solution/main.py run    --input input              --output output
python solution/main.py infer  --input input/requests.jsonl --output output_infer
```

* `doctor` inspects `input/requests.jsonl`, `input/manifest.json`, `input/frames/*.png`,
the model directory at `/models/Qwen--Qwen2.5-VL-3B-Instruct`, `torch`/CUDA,
`transformers` Qwen2.5-VL classes and Pillow. It performs **no** training or inference and
returns exit code **78** if anything is missing.
* `run` reads `input/requests.jsonl` and writes `output/answers.jsonl` and `output/run.json`.
* `infer` is the same pipeline for a new JSONL with new frame sequences and new questions
(re-running it on the same JSONL is exactly the independent *generation recomputation*
check).

Every inference path requires CUDA; the process exits with code 3 instead of falling back
to CPU.

## Input format (`requests.jsonl`, one JSON object per line)

```json
{"videoID": "0001",
 "frames": ["frames/00000.png", "frames/00002.png", "..."],
 "questions": [{"questionID": "q1", "question": "Is the road clear ahead?"}]}
```

Aliases accepted: `video_id`/`video`/`id`; `sampled_frames`/`frame_paths`/`images`;
`qa`/`queries`. Frame paths may be absolute or relative to the input directory.

## Output format

`answers.jsonl` -- one line per question:

```json
{"videoID": "...", "questionID": "...", "answer": "...", "token_ids": [..],
 "used_frame_ids": [..], "used_frame_paths": [..], "num_frames": 8,
 "frame_shapes": [[w,h],..], "prompt_tokens": N, "generated_tokens": M,
 "latency_s": .., "max_pixels_per_frame": 65536, "max_new_tokens": 128, "do_sample": false}
```

`run.json` -- model repo/revision/path, dtype, device, library versions, frame/processor
protocol, per-request coverage, real synchronised timings, peak GPU memory, and an explicit
`checks` block:

* `frames_covered` -- every frame of every request was fed to the model,
* `questions_covered` -- one answer per question,
* `vision_encoder_on_cuda` -- `pixel_values` actually placed on CUDA,
* `generation_executed_on_gpu` -- CUDA peak memory grew during decoding,
* `fresh_input_no_answer_leakage` -- no reference answer / prior output is in context,
* `no_cpu_fallback`.

## Frame handling

Each frame is loaded as RGB, down-scaled (aspect preserved) so that
`width * height <= 65536` and both sides are multiples of the 28-pixel Qwen2.5-VL
grid, so the processor's own resampling is a no-op and the pixel budget is enforced
before the vision tower. With 8 frames this is far below the 40960 total-token budget.

## Honest limitations

* **Temporal-answer correctness is not self-certified.** The solution proves that the
  visual encoding and generation really happened on CUDA over all sampled frames; whether
  individual answers are temporally *correct* must be established by a human or an
  independent oracle and is explicitly out of scope here.
* This is the **debug scale only** (one short clip, 8 frames, 3 questions). It does not
  reproduce the 900-video / 2,700-QA Video-MME catalog, the Qwen2.5-VL-72B reference
  model, or the 64k long-video configuration.
* Only one run is executed per invocation; no hyper-parameter search, no ensembles, no
  sampling. Decoding is deterministic greedy.
* No `qwen-vl-utils` dependency is used: images are pre-fitted and passed directly to the
  HF processor, so the pipeline stays inside `transformers`.
* This task is pure inference; there are no gradients, optimizers or training RNG state to
  save. Reproducibility artefacts are the recorded model revision, dtype, device,
  processor settings and the SHA-256 of the input requests file.
