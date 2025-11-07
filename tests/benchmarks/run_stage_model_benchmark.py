"""CLI utility to compare orchestration stage models."""
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from openai import OpenAI

from agent.core.pipeline import (
    DEFAULT_MODEL,
    ExecutionPlan,
    RetrievalBrief,
    ContextSummary,
    run_context_summary,
    run_execution_plan,
    run_retrieval_brief,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPTS_PATH = ROOT / "tests" / "benchmarks" / "stage_prompts.json"


def _load_prompts(path: Path) -> Dict[str, Mapping[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Prompt fixture missing at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("Prompt fixture must be a mapping")
    return {str(k): v for k, v in data.items() if isinstance(v, Mapping)}


def _serialise_usage(obj: Optional[Any]) -> Optional[Dict[str, int]]:
    if obj is None:
        return None
    if hasattr(obj, "as_dict"):
        return obj.as_dict()  # type: ignore[return-value]
    if isinstance(obj, Mapping):
        return {k: int(v) for k, v in obj.items() if isinstance(v, (int, float))}
    return None


def _serialise_dataclass(obj: Any) -> Dict[str, Any]:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, Mapping):
        return dict(obj)
    raise TypeError("Unsupported payload type for serialisation")


def _run_stage(
    stage: str,
    models: Sequence[str],
    runner,
    *,
    system_prompt: str,
    user_prompt: str,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for model in models:
        record: Dict[str, Any] = {"model": model, "stage": stage}
        start = time.perf_counter()
        try:
            result = runner(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_override=model,
            )
            duration = time.perf_counter() - start
            record["status"] = "ok"
            record["duration_seconds"] = round(duration, 3)
            usage = getattr(result, "usage", None)
            record["usage"] = _serialise_usage(usage)
            record["response"] = _serialise_dataclass(getattr(result, "raw", result))
            if isinstance(result, ContextSummary):
                record["summary"] = result.summary
            if isinstance(result, RetrievalBrief):
                record["brief"] = result.brief
                record["focus_paths"] = result.focus_paths
            if isinstance(result, ExecutionPlan):
                record["plan_steps"] = result.plan
                record["patches"] = result.code_patches
        except Exception as exc:  # pragma: no cover - diagnostic path
            record["status"] = "error"
            record["error"] = str(exc)
        results.append(record)
    return results


def _prepare_models(raw: Optional[Sequence[str]]) -> Sequence[str]:
    if not raw:
        return [DEFAULT_MODEL]
    cleaned = []
    for item in raw:
        item = (item or "").strip()
        if item:
            cleaned.append(item)
    return cleaned or [DEFAULT_MODEL]


def benchmark(
    *,
    prompts_path: Path,
    context_models: Sequence[str],
    retrieval_models: Sequence[str],
    execution_models: Sequence[str],
    max_snippets: int,
    output_path: Optional[Path],
) -> Dict[str, Any]:
    prompts = _load_prompts(prompts_path)
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    system_prompt = str(prompts.get("system", {}).get("prompt", ""))
    context_prompt = prompts.get("context_summary", {})
    retrieval_prompt = prompts.get("retrieval_brief", {})
    execution_prompt = prompts.get("execution_plan", {})

    results: Dict[str, Any] = {
        "prompts_path": str(prompts_path),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stages": {},
    }

    results["stages"]["context_summary"] = _run_stage(
        "context_summary",
        context_models,
        lambda **kwargs: run_context_summary(client, **kwargs),
        system_prompt=system_prompt or str(context_prompt.get("system") or ""),
        user_prompt=str(context_prompt.get("user") or ""),
    )

    results["stages"]["retrieval_brief"] = _run_stage(
        "retrieval_brief",
        retrieval_models,
        lambda **kwargs: run_retrieval_brief(
            client,
            vector_store=None,
            query_text=str(retrieval_prompt.get("query_text") or ""),
            max_snippets=max_snippets,
            **kwargs,
        ),
        system_prompt=system_prompt or str(retrieval_prompt.get("system") or ""),
        user_prompt=str(retrieval_prompt.get("user") or ""),
    )

    results["stages"]["execution_plan"] = _run_stage(
        "execution_plan",
        execution_models,
        lambda **kwargs: run_execution_plan(client, **kwargs),
        system_prompt=system_prompt or str(execution_prompt.get("system") or ""),
        user_prompt=str(execution_prompt.get("user") or ""),
    )

    if output_path:
        output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return results


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompts",
        type=Path,
        default=DEFAULT_PROMPTS_PATH,
        help="Path to stage prompt fixture (default: %(default)s)",
    )
    parser.add_argument(
        "--context-models",
        nargs="*",
        help="Models to benchmark for the context summary stage",
    )
    parser.add_argument(
        "--retrieval-models",
        nargs="*",
        help="Models to benchmark for the retrieval brief stage",
    )
    parser.add_argument(
        "--execution-models",
        nargs="*",
        help="Models to benchmark for the execution plan stage",
    )
    parser.add_argument(
        "--max-snippets",
        type=int,
        default=3,
        help="Maximum number of retrieved snippets when querying the vector store",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write benchmark results as JSON",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    context_models = _prepare_models(args.context_models)
    retrieval_models = _prepare_models(args.retrieval_models)
    execution_models = _prepare_models(args.execution_models)

    results = benchmark(
        prompts_path=args.prompts,
        context_models=context_models,
        retrieval_models=retrieval_models,
        execution_models=execution_models,
        max_snippets=args.max_snippets,
        output_path=args.output,
    )

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
