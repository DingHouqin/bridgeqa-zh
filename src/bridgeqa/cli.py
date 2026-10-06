"""Usage: python -m bridgeqa.cli validate PATH | evaluate GOLD PREDICTIONS."""

import argparse
import json
import hashlib
import sys
from pathlib import Path
from .io import read_jsonl
from .validation import validate_samples
from .evaluation import evaluate


def main():
    parser = argparse.ArgumentParser(description="BridgeQA ZH local reference tools")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="check core sample/pair structure")
    validate.add_argument("samples")
    validate.add_argument("--full-schema", action="store_true", help="also run JSON Schema (development dependency)")
    score = commands.add_parser("evaluate", help="score canonical answers and paired fixtures")
    score.add_argument("samples")
    score.add_argument("predictions")
    score.add_argument("--output", help="write JSON result including original submission records")
    export = commands.add_parser("export-input", help="export white-listed 0.2 model inputs")
    export.add_argument("samples")
    export.add_argument("--output", required=True)
    baseline = commands.add_parser("baseline", help="run label-free public text rules (not an LLM)")
    baseline.add_argument("inputs")
    baseline.add_argument("--output", required=True)
    build = commands.add_parser("build", help="audit and build actual candidate run and offline demo")
    build.add_argument("--output", default="artifacts/midterm")
    controlled=commands.add_parser('controlled',help='audit/run/score the independent synthetic diagnostic')
    controlled.add_argument('--output',required=True)
    controlled.add_argument('--predictions',help='score a submitted JSONL; omit to actually run public rules')
    controlled.add_argument('--full-schema',action='store_true')
    serve = commands.add_parser("serve", help="rebuild and serve demo on loopback only")
    serve.add_argument("--output", default="artifacts/midterm")
    serve.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    try:
        if args.command=='controlled':
            from .controlled import (run_controlled,audit_controlled,evaluate_controlled,read_submission,check_output,
                                     write_strict_json,submission_evidence,parse_error_record)
            from .pilot import ROOT,write_json
            if args.predictions:
                audit_controlled(ROOT)
                inputs=read_jsonl(ROOT/'data/controlled/inputs.jsonl')
                reference=json.loads((ROOT/'data/controlled/reference.json').read_text(encoding='utf-8'))
                submission=Path(args.predictions)
                check_output(args.output,ROOT,submission)
                try:predictions=read_submission(submission)
                except ValueError as exc:
                    error_record=parse_error_record(submission,exc)
                    if args.full_schema:
                        import jsonschema
                        jsonschema.validate(error_record,json.loads((ROOT/'schemas/controlled/submission-error.schema.json').read_text(encoding='utf-8')))
                    write_strict_json(Path(args.output),error_record)
                    raise
                result=evaluate_controlled(inputs,reference,predictions)
                result['submission']=submission_evidence(submission)
            else:
                state=run_controlled(args.output,ROOT)
                result=state['score'];inputs=state['inputs'];reference=state['reference'];predictions=state['predictions']
            if args.full_schema:
                import jsonschema
                # Known malformed submissions remain scored zero. Validate the
                # rows accepted by runtime; do not turn local errors into a
                # rejected batch merely because schema QA was requested.
                valid_ids={c['sample_id'] for c in result['per_case'] if c['prediction_valid']}
                schema_predictions=[p for p in predictions if p['sample_id'] in valid_ids]
                for name,rows in (('reference',[reference]),('model-input',inputs),('prediction',schema_predictions),('score',[result])):
                    schema=json.loads((ROOT/'schemas/controlled'/f'{name}.schema.json').read_text(encoding='utf-8'))
                    validator=jsonschema.Draft202012Validator(schema)
                    for row in rows:validator.validate(row)
            if args.predictions:write_strict_json(Path(args.output),result)
            print(json.dumps({'counts':result['counts'],'contract_success':result['contract_success']['root_macro'],'bridge_sensitivity':result['bridge_sensitivity']['root_macro'],'output':args.output},ensure_ascii=False,indent=2))
            return 0
        if args.command in ("build","serve"):
            if args.command == "serve":
                from .server import serve
                serve(args.output,args.port)
                return 0
            from .pipeline import build_run
            print(json.dumps(build_run(Path(args.output)),ensure_ascii=False,indent=2))
            return 0
        if args.command == "baseline":
            from .baseline import predict
            from .pilot import write_jsonl
            inputs=read_jsonl(args.inputs)
            predictions=[predict(item) for item in inputs]
            write_jsonl(Path(args.output),predictions)
            print(json.dumps({"records":len(predictions),"output":args.output,"kind":"actual_rule_not_llm"}))
            return 0
        samples = read_jsonl(args.samples)
        if args.command == "validate":
            result = validate_samples(samples)
            if args.full_schema:
                import jsonschema
                version = samples[0]["schema_version"]
                root = Path(__file__).resolve().parents[2]
                schema_path = root / "schemas" / ("v0.2/sample.schema.json" if version == "0.2" else "sample.schema.json")
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                for sample in samples:
                    try:
                        jsonschema.validate(sample, schema)
                    except jsonschema.exceptions.ValidationError as exc:
                        raise ValueError(f"{sample.get('sample_id')}: JSON Schema: {exc.message}") from exc
                result["schema_validation"] = "full_json_schema_draft202012"
        elif args.command == "export-input":
            from .protocol import export_inputs
            inputs = export_inputs(samples)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in inputs), encoding="utf-8")
            result = {"exported": len(inputs), "output": str(output), "labels": "white_list_only"}
        else:
            result = evaluate(samples, read_jsonl(args.predictions))
            submission = Path(args.predictions)
            try:
                display_path = submission.resolve().relative_to(Path.cwd().resolve()).as_posix()
                path_kind = "repository_relative"
            except ValueError:
                display_path, path_kind = submission.name, "external_label_only"
            result["submission"] = {"path": display_path, "path_kind": path_kind, "sha256": hashlib.sha256(submission.read_bytes()).hexdigest()}
            if args.output:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    except (ValueError, OSError, KeyError, TypeError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
