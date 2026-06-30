# evaluate-rag

Lightweight RAG evaluation pipeline for the synthetic `careai-platform` LLMOps demo.

The evaluator reads `data/eval/rag_eval_set.jsonl`, calls `apps/rag-service`, calculates quality and safety metrics, writes a local JSON report, and optionally registers an `EvaluationRun` with `control-plane-api`.

## Run

Start the RAG service locally, then run:

```bash
python -m evaluate_rag.run \
  --rag-url http://localhost:8002 \
  --eval-set data/eval/rag_eval_set.jsonl
```

The default report is written to `data/local/rag-eval-report.json`.

If `CONTROL_PLANE_API_URL` is set, or `--control-plane-url` is supplied, the pipeline posts aggregate metrics to:

```text
POST /evaluations
```

## Metrics

- `retrieval_hit_rate`: share of questions where retrieved chunks include at least one expected source.
- `citation_coverage`: average expected-source coverage in answer citations.
- `keyword_relevance`: average expected-keyword match rate across the generated answer and retrieved evidence excerpts.
- `groundedness`: average RAG-service groundedness heuristic.
- `safety_flag_rate`: share of responses carrying safety flags or hard-rejection flags.
- `latency_ms`: average and p95 request latency.
- `token_count`: placeholder total when the provider returns token usage metadata; otherwise `null`.

## Promotion Gate

The report includes thresholds and a top-level `passed` flag. In an enterprise LLMOps workflow, this becomes a pre-promotion gate: failed retrieval, citation, groundedness, or safety checks block prompt/model deployment until reviewed.

The evaluated RAG response also exposes bounded `agent_loop` metadata: retrieval, answer generation, citation/groundedness verification, and at most one retry with verifier feedback. This loop is independent of the control-plane workflow planner, which coordinates cross-service case work.
