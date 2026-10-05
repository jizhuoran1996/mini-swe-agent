# GPUv1-D07 (debug variant) - real OmniDocBench page parsing to Markdown

This solution runs genuine Qwen2.5-VL-3B-Instruct image+text inference on CUDA in
bfloat16 and turns each requested document page into reusable Markdown that keeps
table markup (HTML) and mathematical formulas (LaTeX). It is the declared debug
variant of GPUv1-D07: four native OmniDocBench pages and the 3B model instead of
the reference-large 72B / 1651-page run. Nothing about the reference-large scale
is claimed here.

## Environment

- Python with PyTorch (CUDA build), Transformers, Pillow and NumPy already installed.
- A working CUDA device (the host controller supplies it). There is no CPU path:
  `run` and `infer` exit fatally if `torch.cuda.is_available()` is false.
- Model directory `/models/Qwen--Qwen2.5-VL-3B-Instruct` (read-only), revision
  `66285546d2b821cf421d4f5eb2576359d3770cd3`.
- Input `input/requests.jsonl` plus the page images it references (default
  `input/images/<id>.png`).

## Commands

```
python solution/main.py --help
python solution/main.py doctor --input input
python solution/main.py run   --input input --output output
python solution/main.py infer --image new_page.png --prompt "Convert this page to Markdown" --output output/new_page.json
```

`--model-dir` overrides the local model path on every subcommand.

### doctor

Checks the model config/tokenizer/processor files and weight shards, the Python
dependencies, CUDA availability, `requests.jsonl` and every referenced image
file. It loads no model and performs no training or inference. It prints every
missing item and returns exit code 78 when anything is missing, 0 when the
dependencies and inputs are all present.

### run

For each id in `requests.jsonl` (in file order), the page image is loaded, the
vision encoder runs on CUDA, and the model generates at most 512 new tokens with
greedy decoding (`do_sample=False`, `num_beams=1`), image preprocessing capped at
`max_pixels=262144`. The exact prompt is recorded in `config.json` and
`run.json`.

The run writes:

- `output/pages/<id>.md` - one Markdown file per requested id.
- `output/documents.jsonl` - `id`, `text`, `token_ids`, image SHA-256, image size,
  prompt length, generated token count, CUDA check for the vision tensors,
  relative Markdown path.
- `output/tables/<id>_<n>.html` - every HTML table block found in the generated
  page, extracted verbatim.
- `output/formula_manifest.jsonl` - `id`, index, kind (inline/display) and the
  LaTeX body of every formula present in the generated Markdown.
- `output/page_status.jsonl` - per-page success/failure with the error message
  when a page fails.
- `output/config.json` - frozen model/data revision, dtype, decoding and prompt.
- `output/run.json` - task id, scale flag, environment and GPU name, model and
  dataset revisions, decoding and image-processing settings, per-page records
  (SHA-256, token counts, table/formula counts, wall and CUDA-event timings,
  `pixel_values_is_cuda`), model load time, synchronized totals, peak GPU
  memory, and the requested/written/failed coverage lists.

Exit code is 0 when every requested page produced Markdown, 1 when at least one
page failed (the failure list is still written), 78 when a required input, model
file or dependency is absent.

### infer

Runs the same model on a page image that is not part of `requests.jsonl` and
writes a JSON document with the generated Markdown, the raw generated
`token_ids`, the image SHA-256, the CUDA vision-tensor check, and wall/CUDA-event
timings. It refuses to start if the image or prompt is missing.

## Honest limitations

- Debug variant only: 4 pages, 3B model. This is not the reference-large
  72B/1651-page run and no reference-large result is claimed.
- Quality metrics (OCR character error, reading-order and table quality) are not
  computed here because the OmniDocBench structural annotations are hidden from
  this container. The artifacts expose the raw generated Markdown, the extracted
  HTML tables and the LaTeX formulas so the external evaluator can score them.
- Generation is greedy and single-sample: no sampling, no ensembles, no
  hyperparameter search.
- The prompt is fixed and recorded; only the tests described above were run.
- Timings in `run.json` are wall-clock plus CUDA event values measured with
  explicit `torch.cuda.synchronize()`; they are specific to the machine that
  executes this code and are not a claim about other hardware.
- No network access, no package installation, no shell execution and no host
  file access are performed by this program; it only reads the declared input and
  model paths and writes into the given output directory.
