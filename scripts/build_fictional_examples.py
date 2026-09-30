"""Rebuild public fictional fixtures; never read or modify real/private data."""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "examples"


def ref(doc):
    return {"doc_id": doc, "sent_id": 0}


def doc(identifier, text, language="zh"):
    return {"doc_id": identifier, "title": f"虚构资料 {identifier}", "language": language, "sentences": [{"sent_id": 0, "text": text}]}


def sample(identifier, variant, pattern):
    path = [
        {"hop": 1, "head": "xingqiao_tu", "relation": "creator", "tail": "lin_mu", "evidence": [ref("d1")]},
        {"hop": 2, "head": "lin_mu", "relation": "founded", "tail": "beilan_institute", "evidence": [ref("d2")]},
        {"hop": 3, "head": "beilan_institute", "relation": "located_in", "tail": "qingyu", "evidence": [ref("d3")]},
    ]
    docs = [doc("d1", "《星桥图》的作者是林牧。"), doc("d2", "林牧创办了北澜研究所。"), doc("d3", "北澜研究所位于青屿市。")]
    if pattern == "ZEZ":
        docs[1] = doc("d2", "Lin Mu founded the Beilan Institute.", "en")
    if variant == "clean_control":
        docs += [doc("d4", "《星桥图》的画框采用银色。"), doc("d5", "南泽研究所的馆藏以书籍为主。"), doc("d6", "海临市每年举办冬季读书活动。")]
    if variant == "adversarial":
        docs += [doc("d4", "《星桥图》的修复者是林墨。"), doc("d5", "林墨创办了南泽研究所。"), doc("d6", "南泽研究所位于海临市。")]
    return {
        "schema_version": "0.1", "sample_id": identifier, "seed_id": "fictional_seed_001",
        "pair_id": None if variant == "gold_only" else f"fictional_pair_{pattern}",
        "split": "example", "origin": "fictional_fixture", "domain": "fictional_fixture",
        "track": "context_attack", "variant": variant,
        "question": "《星桥图》的作者创办的研究所位于哪座城市？", "question_language": "zh",
        "answer": {"canonical_id": "qingyu", "text": "青屿市", "aliases": ["青屿", "Qingyu"], "type": "entity"},
        "topology": "chain", "hop_count": 3, "documents": docs,
        "gold_support": [ref("d1"), ref("d2"), ref("d3")], "reasoning_path": path,
        "language_condition": pattern, "crosslingual_mode": "none" if pattern == "ZZZ" else "controlled_parallel",
        "attack": None if variant != "adversarial" else {"primary_type": "false_bridge", "target_hop": 1, "secondary_tags": ["role_confusion", "entity_confusion"], "source_method": "handwritten_fictional", "expected_decoy_answer": "hailin", "changed_sentences": [ref("d4"), ref("d5"), ref("d6")]},
        "provenance": {"is_fictional": True, "source_dataset": None, "source_id": None, "sources": [], "construction_method": "handwritten_fictional", "translation_revision": "fixture_v1" if pattern == "ZEZ" else None},
        "qc": {"status": "fixture_only", "human_verified": False, "review_ids": [], "length_matched": False},
    }


def extended_sample(identifier, variant, hops):
    row = sample(identifier, variant, "ZZZ")
    row["seed_id"] = f"fictional_seed_{hops}hop"
    row["pair_id"] = f"fictional_pair_{hops}hop"
    row["hop_count"] = hops
    row["language_condition"] = "Z" * hops
    if hops == 2:
        row["question"] = "林牧创办的研究所位于哪座城市？"
        row["reasoning_path"] = row["reasoning_path"][1:]
        for index, step in enumerate(row["reasoning_path"], 1):
            step["hop"] = index
        row["gold_support"] = [ref("d2"), ref("d3")]
        row["documents"] = [d for d in row["documents"] if d["doc_id"] != "d1"]
        if variant == "adversarial":
            row["documents"][2] = doc("d4", "林牧曾在南泽研究所做讲座。")
    elif hops == 4:
        row["question"] = "《星桥图》的作者创办的研究所所在的城市属于哪个省？"
        row["reasoning_path"].append({"hop": 4, "head": "qingyu", "relation": "belongs_to_province", "tail": "yunlan", "evidence": [ref("d7")]})
        row["documents"].insert(3, doc("d7", "青屿市属于云澜省。"))
        row["gold_support"].append(ref("d7"))
        row["answer"] = {"canonical_id": "yunlan", "text": "云澜省", "aliases": ["云澜"], "type": "entity"}
        if variant == "adversarial":
            row["documents"][-1] = doc("d6", "南泽研究所位于海临市，海临市属于墨辰省。")
            row["attack"]["expected_decoy_answer"] = "mochen"
    else:
        raise ValueError("Extended fixtures support 2 or 4 hops only")
    return row


def main():
    samples = [sample("example_001", "gold_only", "ZZZ"), sample("example_002", "clean_control", "ZZZ"), sample("example_003", "adversarial", "ZZZ"), sample("example_004", "clean_control", "ZEZ"), sample("example_005", "adversarial", "ZEZ"), extended_sample("example_006", "clean_control", 2), extended_sample("example_007", "adversarial", 2), extended_sample("example_008", "clean_control", 4), extended_sample("example_009", "adversarial", 4)]
    predictions = []
    for row in samples:
        wrong = row["sample_id"] == "example_003"
        steps = [{k: s[k] for k in ("hop", "head", "relation", "tail")} for s in row["reasoning_path"]]
        if wrong:
            steps = [{"hop": 1, "head": "xingqiao_tu", "relation": "creator", "tail": "lin_mo"}, {"hop": 2, "head": "lin_mo", "relation": "founded", "tail": "nanze_institute"}, {"hop": 3, "head": "nanze_institute", "relation": "located_in", "tail": "hailin"}]
        predictions.append({"schema_version": "0.1", "sample_id": row["sample_id"], "run_id": "handwritten_fixture_not_model", "status": "ok", "answer": {"canonical_id": "hailin" if wrong else row["answer"]["canonical_id"], "text": "海临市" if wrong else row["answer"]["text"]}, "support": [ref("d4"), ref("d5"), ref("d6")] if wrong else copy.deepcopy(row["gold_support"]), "submitted_steps": steps})
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("samples.jsonl", samples), ("predictions.jsonl", predictions)):
        (OUT / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    public_input = {k: copy.deepcopy(samples[1][k]) for k in ("schema_version", "sample_id", "question", "question_language", "documents")}
    (OUT / "model-input.json").write_text(json.dumps(public_input, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote 9 fictional samples (2/3/4 hops), 9 handwritten predictions, and 1 input example.")


if __name__ == "__main__":
    main()
