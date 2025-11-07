# Stage-Specific Model Benchmarking

This guide documents how to evaluate and configure different OpenAI models for each
orchestration stage. It builds on the configurable overrides introduced in
`agent/core/pipeline.py` and the reusable benchmarking script located at
`tests/benchmarks/run_stage_model_benchmark.py`.

> **Note:** The orchestration pipeline now defaults to Scaleway's OpenAI-compatible
> Generative API. To follow the OpenAI-focused workflow in this guide, set
> `LLM_PROVIDER=openai` and provide an `OPENAI_API_KEY` before running the
> benchmark script.

## Running the benchmark script

1. Ensure you have a valid `OPENAI_API_KEY` in your environment.
2. Optionally prepare a prompt fixture (defaults to
   `tests/benchmarks/stage_prompts.json`).
3. Execute the benchmark:

   ```bash
   python tests/benchmarks/run_stage_model_benchmark.py \
     --context-models gpt-4.1-mini gpt-5-codex \
     --retrieval-models gpt-4.1-mini gpt-5-codex \
     --execution-models gpt-5-codex gpt-5
   ```

   The script prints aggregated results and can persist them with `--output path/to/results.json`.

Each run captures completion status, latency, and token usage for every stage
and model combination, making it straightforward to compare trade-offs.

## Recommended defaults

Early trials using the fixture prompts suggest the following allocation strikes a
good balance between cost and quality:

| Stage             | Recommended model | Rationale |
| ----------------- | ----------------- | --------- |
| Context summary   | `scaleway/deepseek-r1-distill-llama-70b` | Strong reasoning quality with broad Scaleway availability. |
| Retrieval brief   | `scaleway/deepseek-r1-distill-llama-70b` | Keeps behaviour consistent across stages. |
| Execution plan    | `scaleway/deepseek-r1-distill-llama-70b` | Reliable code synthesis at a competitive price point. |

Configure these defaults via environment variables before launching the
orchestrator:

```bash
export CONTEXT_MODEL=scaleway/deepseek-r1-distill-llama-70b
export RETRIEVAL_MODEL=scaleway/deepseek-r1-distill-llama-70b
export EXECUTION_MODEL=scaleway/deepseek-r1-distill-llama-70b

You can replace these with any model identifier exposed by the Scaleway
Generative API. The environment variables are shared across providers, allowing
seamless switching via `LLM_PROVIDER`.
```

If the specified model rejects a request due to quota limits, the pipeline
automatically retries with the fallback model (`scaleway/llama-3-70b-instruct`).

## Updating production guidance

When new models become available or pricing changes, rerun the benchmark script
with the desired candidates. Capture the resulting JSON output alongside any
qualitative observations and update the table above so future runs benefit from
fresh data.
