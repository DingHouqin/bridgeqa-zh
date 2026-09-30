"""Reference canonical-answer and paired scoring for linear-chain fixtures."""

from collections import defaultdict
from .validation import evidence_key, require, validate_samples


def mean(values):
    return sum(values) / len(values) if values else None


def support_f1(gold, predicted):
    if not predicted:
        return 0.0
    hits = len(gold & predicted)
    return 2 * hits / (len(gold) + len(predicted))


def evaluate(samples, predictions):
    validate_samples(samples)
    gold_by_id = {row["sample_id"]: row for row in samples}
    pred_by_id = {}
    for row in predictions:
        sid = row.get("sample_id")
        require(isinstance(sid, str) and sid in gold_by_id, f"unknown prediction ID: {sid}")
        require(sid not in pred_by_id, f"duplicate prediction ID: {sid}")
        require(row.get("schema_version") == "0.1", f"{sid}: unsupported prediction version")
        require(row.get("status") in {"ok", "error", "abstain"}, f"{sid}: invalid prediction status")
        require(isinstance(row.get("run_id"), str), f"{sid}: run_id required")
        if row["status"] == "ok":
            require(isinstance(row.get("answer"), dict) and isinstance(row["answer"].get("canonical_id"), str), f"{sid}: answer required")
        require(isinstance(row.get("support"), list), f"{sid}: support list required")
        require(isinstance(row.get("submitted_steps"), list), f"{sid}: submitted_steps list required")
        available = {(d["doc_id"], s["sent_id"]) for d in gold_by_id[sid]["documents"] for s in d["sentences"]}
        keys = [evidence_key(item) for item in row["support"]]
        require(len(set(keys)) == len(keys) and set(keys) <= available, f"{sid}: duplicate/unknown predicted support")
        for index, step in enumerate(row["submitted_steps"], 1):
            require(isinstance(step, dict) and step.get("hop") == index, f"{sid}: steps must be ordered")
            require(all(isinstance(step.get(field), str) for field in ("head", "relation", "tail")), f"{sid}: incomplete submitted step")
        pred_by_id[sid] = row
    scored, by_variant, pairs = [], defaultdict(list), defaultdict(dict)
    for sample in samples:
        sid = sample["sample_id"]
        pred = pred_by_id.get(sid)
        valid = pred is not None and pred["status"] == "ok"
        correct = int(valid and pred["answer"]["canonical_id"] == sample["answer"]["canonical_id"])
        predicted_support = {evidence_key(e) for e in pred["support"]} if valid else set()
        f1 = support_f1({evidence_key(e) for e in sample["gold_support"]}, predicted_support)
        mismatch = None
        diagnosis = "steps_not_submitted"
        steps = pred["submitted_steps"] if valid else []
        if steps:
            diagnosis = "matches_submitted_path"
            for index, gold_step in enumerate(sample["reasoning_path"]):
                if index >= len(steps) or any(steps[index].get(k) != gold_step[k] for k in ("head", "relation", "tail")):
                    mismatch, diagnosis = index + 1, "submitted_path_mismatch"
                    break
            if mismatch is None and len(steps) > sample["hop_count"]:
                mismatch, diagnosis = sample["hop_count"] + 1, "extra_submitted_step"
        item = {"sample_id": sid, "seed_id": sample["seed_id"], "canonical_answer_em": correct, "support_f1": f1, "first_submitted_step_mismatch": mismatch, "step_diagnostic_status": diagnosis, "prediction_status": pred["status"] if pred else "missing"}
        scored.append(item)
        by_variant[sample["variant"]].append(item)
        if sample.get("pair_id"):
            pairs[sample["pair_id"]][sample["variant"]] = item
    seed_stats = defaultdict(list)
    for members in pairs.values():
        control, adv = members["clean_control"], members["adversarial"]
        c, a = control["canonical_answer_em"], adv["canonical_answer_em"]
        seed_stats[control["seed_id"]].append((c - a, c * (1 - a), c))
    drops, attacks, denominators = [], [], []
    for values in seed_stats.values():
        drops.append(mean([v[0] for v in values]))
        attacks.append(mean([v[1] for v in values]))
        denominators.append(mean([v[2] for v in values]))
    def seed_macro(items, field):
        grouped = defaultdict(list)
        for item in items:
            grouped[item["seed_id"]].append(item[field])
        return mean([mean(v) for v in grouped.values()])
    return {
        "reference_only": True,
        "note": "canonical IDs only; no text F1/CI/retrieval/semantic validity; submitted steps are observable outputs",
        "counts": {"samples": len(samples), "predictions": len(predictions), "missing": len(samples) - len(predictions), "pairs": len(pairs), "paired_seeds": len(seed_stats)},
        "by_variant_seed_macro": {variant: {"canonical_answer_em": seed_macro(items, "canonical_answer_em"), "support_f1": seed_macro(items, "support_f1")} for variant, items in by_variant.items()},
        "paired": {"seed_macro_drop_percentage_points": 100 * mean(drops) if drops else None, "seed_weighted_asr": sum(attacks) / sum(denominators) if sum(denominators) else None, "asr_weighting": "each_seed_total_weight_one_across_its_pairs"},
        "per_sample": scored
    }
