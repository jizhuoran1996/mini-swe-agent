# Notes / acceptance status

- `assets_ready: false` in the frozen input manifest. On the host where this was
  authored, `reference_model.pt`, `cases.json` and `preprocessed/case_*.npy` are
  **not mounted**, so `doctor` and `run` correctly refuse with exit `78`.
- No fake data, random weights, CPU fallback, download or host access is used.
- Only `solution/` and `output/` are written.
- When a real input tree becomes available (with `torch` + CUDA), `main.py run`
  performs the full 3-D sliding-window inference described in `solution/main.py`.
- Debug vs reference-large: the debug scope is 2 real cases; it does **not**
  prove the 42-case reference-large run. `reference_large_tested` remains false.
