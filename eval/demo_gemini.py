#!/usr/bin/env python3
"""
Minimal Gemini demo for VCBench.

This script evaluates a small slice of VCBench end-to-end:
1. Load `data/vcbench_eval.jsonl`
2. Upload each source video to Gemini
3. Truncate the visible portion to the query timestamp
4. Write raw per-query-point predictions to JSONL

Then run:
  python eval/unify_results.py <raw.jsonl> <unified.jsonl>
  python eval/compute_metrics.py <unified.jsonl> data/vcbench_eval.jsonl

Environment:
  export GEMINI_API_KEY=...
"""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_FPS = 1
DEFAULT_MAX_OUTPUT_TOKENS = 128
DEFAULT_TEMPERATURE = 0
PROMPT_SUFFIX = " Answer with ONLY a single integer number, nothing else."


def upload_video(client, video_path):
    myfile = client.files.upload(file=video_path)
    while True:
        myfile = client.files.get(name=myfile.name)
        if myfile.state == "ACTIVE":
            return myfile
        if str(myfile.state) == "FAILED":
            raise RuntimeError(f"Gemini file processing failed: {myfile.name}")
        time.sleep(2)


def query_gemini(client, model, myfile, query_time, question, fps):
    video_part = types.Part.from_uri(file_uri=myfile.uri, mime_type="video/mp4")
    video_part.video_metadata = types.VideoMetadata(
        fps=fps,
        start_offset="0s",
        end_offset=f"{query_time}s",
    )

    prompt = (
        "The video clip ends at the exact moment being asked about. "
        f"{question}{PROMPT_SUFFIX}"
    )
    resp = client.models.generate_content(
        model=model,
        contents=[video_part, prompt],
        config=types.GenerateContentConfig(
            temperature=DEFAULT_TEMPERATURE,
            max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        ),
    )

    raw_text = resp.text
    finish_reason = None
    block_reason = None

    if resp.candidates:
        c = resp.candidates[0]
        finish_reason = str(c.finish_reason) if c.finish_reason else None
        if raw_text is None and c.content and c.content.parts:
            raw_text = c.content.parts[0].text

    if hasattr(resp, "prompt_feedback") and resp.prompt_feedback:
        block_reason = str(resp.prompt_feedback)

    token_info = {}
    if resp.usage_metadata:
        u = resp.usage_metadata
        token_info = {
            "prompt_tokens": u.prompt_token_count,
            "output_tokens": u.candidates_token_count,
            "total_tokens": u.total_token_count,
        }

    return raw_text, finish_reason, block_reason, token_info


def main():
    parser = argparse.ArgumentParser(description="Minimal VCBench Gemini demo")
    parser.add_argument(
        "--video-dir",
        required=True,
        help="Root directory containing {source_dataset}/{video_path}",
    )
    parser.add_argument(
        "--input",
        default="data/vcbench_eval.jsonl",
        help="Path to vcbench_eval.jsonl",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Raw JSONL output path (default: outputs/vcbench_gemini_demo_<ts>.jsonl)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of query points to run for the demo",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Gemini model name",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=DEFAULT_FPS,
        help="FPS metadata passed to Gemini",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY before running this demo.")

    client = genai.Client(api_key=api_key)
    video_dir = Path(args.video_dir)
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else Path("outputs") / (
        f"vcbench_gemini_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open() as f:
        data = [json.loads(line) for line in f if line.strip()]

    if args.limit > 0:
        data = data[: args.limit]

    print(f"Demo questions: {len(data)}")
    print(f"Model: {args.model}")
    print(f"Video root: {video_dir}")
    print(f"Output: {output_path}")

    completed = 0
    total_tokens = 0

    with output_path.open("w") as out_f:
        for idx, item in enumerate(data, 1):
            video_path = video_dir / item["source_dataset"] / item["video_path"]
            if not video_path.exists():
                print(f"[{idx}/{len(data)}] SKIP missing video: {video_path}")
                continue

            print(
                f"[{idx}/{len(data)}] q_id={item['q_id']} "
                f"query_time={item['query_time']}s"
            )

            myfile = upload_video(client, str(video_path))
            try:
                raw_text, finish_reason, block_reason, token_info = query_gemini(
                    client=client,
                    model=args.model,
                    myfile=myfile,
                    query_time=item["query_time"],
                    question=item["question"],
                    fps=args.fps,
                )
            finally:
                try:
                    client.files.delete(name=myfile.name)
                except Exception:
                    pass

            prediction = raw_text.strip() if raw_text else None
            total_tokens += token_info.get("total_tokens", 0) or 0

            result = {
                **item,
                "prediction": prediction,
                "raw_response": raw_text,
                "finish_reason": finish_reason,
                "block_reason": block_reason,
                "prompt_tokens": token_info.get("prompt_tokens"),
                "output_tokens": token_info.get("output_tokens"),
                "total_tokens": token_info.get("total_tokens"),
            }
            out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
            out_f.flush()
            completed += 1

            print(
                f"  pred={prediction}, gt={item['count']}, "
                f"tokens={token_info.get('total_tokens', '?')}"
            )

    print(f"Done: {completed}/{len(data)}")
    print(f"Total tokens: {total_tokens}")
    print(f"Raw results: {output_path}")
    print()
    print("Next:")
    print(
        f"  python eval/unify_results.py {output_path} "
        f"{output_path.with_name(output_path.stem + '_unified.jsonl')}"
    )
    print(
        f"  python eval/compute_metrics.py "
        f"{output_path.with_name(output_path.stem + '_unified.jsonl')} {input_path}"
    )


if __name__ == "__main__":
    main()
