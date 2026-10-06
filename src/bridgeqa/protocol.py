"""Version 0.2: text proofs, candidate partitions, and label-free model inputs.

Runtime uses the standard library. This validator checks our explicit contract;
scripts/check_schemas.py additionally runs the full published JSON Schemas.
Neither check certifies facts, uniqueness, necessity, or attack semantics.
"""

import copy
import hashlib
import json
import unicodedata
from collections import defaultdict

from .validation import require, evidence_key

VERSION = "0.2"
# Public vocabulary, shared by instruction, schema and all safe-input exporters.
# Order is alphabetical by canonical term, never the path of a particular case.
RELATION_QUALIFIERS = {
    "作者": "", "创办": "", "刺于马下者": "", "女儿": "", "女婿": "驻守陕西的中郎将",
    "字": "", "属于": "", "弟弟": "", "所认义父": "归附后本段拜认事件",
    "所配之夫": "还汉后本段配婚事件", "斩断手腕者": "", "父亲": "", "老师": "",
    "谋杀者": "", "追赶者": "本段骑赤兔马追赶事件", "位于": "",
}
RELATION_PHRASES = {
    "作者": "作品的作者", "创办": "创办的机构", "刺于马下者": "将某人刺于马下之人",
    "女儿": "某人的女儿", "女婿": "女婿中驻守陕西的中郎将或驻守陕西的中郎将女婿",
    "字": "某人的字", "属于": "所属地区或组织", "弟弟": "某人的弟弟",
    "所认义父": "归附后的拜认事件中所认义父或认谁为义父",
    "所配之夫": "女子还汉后在本段配婚事件中被配给谁",
    "斩断手腕者": "砍断某人手腕之人", "父亲": "某人的父亲", "老师": "某人的老师",
    "谋杀者": "某人被谁谋杀", "追赶者": "骑赤兔马追赶某人之人", "位于": "所在地点",
}
VOCABULARY_HELP = "；".join(f"{r}（自然含义：{RELATION_PHRASES[r]}；限定：{q or '空字符串'}）" for r, q in sorted(RELATION_QUALIFIERS.items()))
INSTRUCTION = (
    "仅依据给定正文回答。输出JSON：sample_id、schema_version=0.2、run_id、status(ok/error/abstain)、"
    "answer{text}、support[{doc_id,sent_id}]、submitted_steps[{hop,head,relation,tail,qualifier,evidence}]。"
    "实体用正文名称；自然问句按语义填写下列规范关系，时间、事件和角色范围独立填写qualifier，"
    "没有限定时填空字符串。通用全集：" + VOCABULARY_HELP + "。"
    "每一步引用支持句；全局support恰为步骤引用的并集。资料不足、关系多解或无法解析时用"
    "status=abstain、answer=null，可保留已证实的连续前缀。不得使用外部知识或跨题记忆。"
    "临时世界事实只在所给世界内有效，不能按小说常识补全；正文代号标记的引号不是名称本体，"
    "答案和步骤填写引号内代码本体。代号名册和缺信息提示不陈述关系，不可作为步骤证据。"
)
SAMPLE_FIELDS = {
    "schema_version", "sample_id", "seed_id", "source_cluster", "pair_id", "split", "origin", "domain",
    "variant", "question", "question_language", "hop_count", "documents", "answer", "entity_aliases",
    "proofs", "attack", "provenance", "qc",
}
INPUT_FIELDS = {"schema_version", "sample_id", "question", "question_language", "documents", "instruction"}


def normalize(value):
    return "".join(unicodedata.normalize("NFKC", value).split()).casefold()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def unique_strings(value, label):
    require(isinstance(value, list) and all(nonempty(s) for s in value), f"invalid {label}")
    require(len({s.strip() for s in value}) == len(value), f"duplicate {label}")


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def refs(value):
    require(isinstance(value, list), "evidence must be a list")
    require(all(isinstance(e, dict) and set(e) == {"doc_id", "sent_id"} for e in value), "invalid evidence fields")
    keys = [evidence_key(e) for e in value]
    require(len(keys) == len(set(keys)), "duplicate evidence reference")
    return set(keys)


def texts(sample):
    return {(d["doc_id"], s["sent_id"]): s["text"] for d in sample["documents"] for s in d["sentences"]}


def alias_map(sample):
    mapping = {}
    for entity, aliases in sample["entity_aliases"].items():
        require(nonempty(entity), "empty entity")
        unique_strings(aliases, "entity aliases")
        canonical = normalize(entity)
        for name in [entity, *aliases]:
            key = normalize(name)
            require(key not in mapping or mapping[key] == canonical, f"ambiguous frozen alias: {name}")
            mapping[key] = canonical
    return mapping


def validate_documents(documents, neutral=False):
    require(isinstance(documents, list) and documents, "documents required")
    available, identifiers = set(), set()
    for index, doc in enumerate(documents, 1):
        require(isinstance(doc, dict) and set(doc) == {"doc_id", "title", "language", "sentences"}, "invalid document fields")
        did = doc["doc_id"]
        require(nonempty(did) and did not in identifiers, "duplicate/invalid doc ID")
        identifiers.add(did)
        require(isinstance(doc["title"], str) and doc["language"] == "zh", "0.2 documents must be Chinese")
        if neutral:
            require(did == f"d{index}" and doc["title"] == f"材料 {index}", "non-neutral document identifier/title")
        require(isinstance(doc["sentences"], list) and doc["sentences"], "sentences required")
        for sentence in doc["sentences"]:
            require(isinstance(sentence, dict) and set(sentence) == {"sent_id", "text"}, "invalid sentence fields")
            key = evidence_key({"doc_id": did, "sent_id": sentence["sent_id"]})
            require(key[1] >= 0 and key not in available, "invalid/duplicate sentence ID")
            require(nonempty(sentence["text"]), "empty sentence")
            available.add(key)
    return available


def validate_v02(rows):
    require(isinstance(rows, list) and rows, "dataset is empty")
    ids, pairs, seeds = set(), defaultdict(list), defaultdict(list)
    for sample in rows:
        require(isinstance(sample, dict) and set(sample) == SAMPLE_FIELDS, "invalid 0.2 sample fields")
        sid = sample["sample_id"]
        require(isinstance(sid, str) and len(sid) == 26 and sid.startswith("q_") and all(c in "0123456789abcdef" for c in sid[2:]) and sid not in ids, "duplicate/invalid opaque sample ID")
        ids.add(sid)
        require(sample["schema_version"] == VERSION, "mixed/unsupported schema version")
        for field in ("seed_id", "source_cluster", "domain", "question"):
            require(nonempty(sample[field]), f"{sid}: invalid {field}")
        require(sample["split"] in {"example", "dev_public", "test_hidden"}, "invalid split")
        require(sample["origin"] in {"fictional_fixture", "native_zh"}, "invalid origin")
        require(sample["variant"] in {"gold_only", "clean_control", "adversarial"}, "invalid variant")
        require(sample["question_language"] == "zh", "0.2 question must be Chinese")
        h = sample["hop_count"]
        require(type(h) is int and h in {2, 3, 4}, "invalid hop count")
        available = validate_documents(sample["documents"])
        require(all(d["doc_id"] == f"d{i}" for i, d in enumerate(sample["documents"], 1)), "sample document IDs must use neutral ordered dN slots")
        require(isinstance(sample["answer"], dict) and set(sample["answer"]) == {"text", "aliases", "type"}, "invalid answer")
        answer = sample["answer"]
        require(isinstance(answer["text"], str) and normalize(answer["text"]), "answer text required")
        unique_strings(answer["aliases"], "answer aliases")
        require(answer["type"] in {"entity", "date", "number", "string"}, "invalid answer type")
        require(isinstance(sample["entity_aliases"], dict), "entity_aliases required")
        amap = alias_map(sample)
        canonical = lambda s: amap.get(normalize(s), normalize(s))
        require(isinstance(sample["proofs"], list) and sample["proofs"], "proofs required")
        for proof in sample["proofs"]:
            require(isinstance(proof, dict) and set(proof) == {"steps"}, "invalid proof fields")
            steps = proof["steps"]
            require(isinstance(steps, list) and len(steps) == h, "proof length mismatch")
            for index, step in enumerate(steps, 1):
                require(isinstance(step, dict) and set(step) == {"hop", "head", "relation", "tail", "qualifier", "evidence"}, "invalid gold step fields")
                require(type(step["hop"]) is int and step["hop"] == index, "unordered gold hop")
                require(all(nonempty(step[f]) for f in ("head", "relation", "tail")), "empty gold step")
                require(isinstance(step["qualifier"], str), "invalid gold qualifier")
                require(refs(step["evidence"]) and refs(step["evidence"]) <= available, "invalid gold step evidence")
                if index > 1:
                    require(canonical(steps[index-2]["tail"]) == canonical(step["head"]), "disconnected gold proof")
            require(canonical(steps[-1]["tail"]) == canonical(answer["text"]), "gold final answer mismatch")
        qc = sample["qc"]
        require(isinstance(qc, dict) and set(qc) == {"status", "human_verified", "review_ids"}, "invalid qc fields")
        require(qc["status"] in {"candidate", "under_review", "accepted", "rejected", "fixture_only"}, "invalid qc status")
        require(type(qc["human_verified"]) is bool, "invalid qc")
        unique_strings(qc["review_ids"], "review IDs")
        require(qc["status"] != "accepted" or (qc["human_verified"] and qc["review_ids"]), "accepted requires recorded human verification")
        require(sample["origin"] != "fictional_fixture" or (sample["split"] == "example" and qc["status"] == "fixture_only" and not qc["human_verified"]), "fixture must remain example/fixture_only")
        provenance = sample["provenance"]
        require(isinstance(provenance, dict) and set(provenance) == {"construction_method", "sources"}, "invalid provenance")
        require(nonempty(provenance["construction_method"]) and isinstance(provenance["sources"], list), "invalid provenance types")
        for source in provenance["sources"]:
            require(isinstance(source, dict) and set(source) == {"source_id", "url", "citation", "version", "accessed_at", "license", "text_sha256"}, "invalid source fields")
            require(all(nonempty(v) for v in source.values()), "empty source metadata")
            require(len(source["text_sha256"]) == 64 and all(c in "0123456789abcdef" for c in source["text_sha256"]), "invalid source text hash")
        if sample["origin"] == "native_zh":
            require(len(provenance["sources"]) >= 2 and len(sample["documents"]) >= 2, "native candidate requires >=2 source documents")
            require(len({s["url"] for s in provenance["sources"]}) >= 2, "native candidate requires distinct source documents")
        if sample["variant"] == "gold_only":
            require(sample["pair_id"] is None and sample["attack"] is None, "gold_only cannot be paired/attacked")
        else:
            require(nonempty(sample["pair_id"]), "pair ID required")
            pairs[sample["pair_id"]].append(sample)
        if sample["variant"] == "adversarial":
            attack = sample["attack"]
            require(isinstance(attack, dict) and set(attack) == {"primary_type", "target_hop", "changed_sentences", "source_method"}, "invalid attack")
            require(attack["primary_type"] in {"false_bridge", "redundant", "misleading_relation"}, "unsupported attack mechanism")
            require(type(attack["target_hop"]) is int and 1 <= attack["target_hop"] <= h, "invalid attack hop")
            require(nonempty(attack["source_method"]), "attack source method required")
            require(refs(attack["changed_sentences"]) and refs(attack["changed_sentences"]) <= available, "invalid changed slots")
        else:
            require(sample["attack"] is None, "non-adversarial attack must be null")
        seeds[sample["seed_id"]].append(sample)
    for members in seeds.values():
        for field in ("split", "origin", "source_cluster"):
            require(len({r[field] for r in members}) == 1, f"seed {field} inconsistency/leakage")
        for field in ("question", "hop_count", "answer", "entity_aliases", "proofs", "domain", "provenance", "qc"):
            require(all(r[field] == members[0][field] for r in members), f"seed reference changed: {field}")
    audits = []
    for pid, members in pairs.items():
        require(len(members) == 2 and {r["variant"] for r in members} == {"clean_control", "adversarial"}, "pair requires one control and one attack")
        control = next(r for r in members if r["variant"] == "clean_control")
        attack = next(r for r in members if r["variant"] == "adversarial")
        for field in SAMPLE_FIELDS - {"sample_id", "variant", "attack", "documents"}:
            require(control[field] == attack[field], f"{pid}: invariant changed: {field}")
        structure = lambda r: [(d["doc_id"], d["title"], d["language"], [s["sent_id"] for s in d["sentences"]]) for d in r["documents"]]
        require(structure(control) == structure(attack), f"{pid}: document order/structure/presentation changed")
        before, after = texts(control), texts(attack)
        changed = {k for k in before if before[k] != after[k]}
        require(changed == refs(attack["attack"]["changed_sentences"]), f"{pid}: unregistered/unchanged attack slots")
        gold = set().union(*(refs(s["evidence"]) for p in control["proofs"] for s in p["steps"]))
        require(not changed & gold, f"{pid}: gold evidence changed")
        n1, n2 = sum(map(len, before.values())), sum(map(len, after.values()))
        delta = abs(n1-n2) / max(n1, n2)
        require(delta <= .05, f"{pid}: context character length difference >5%")
        audits.append({"pair_id": pid, "control_characters": n1, "attack_characters": n2, "relative_character_difference": delta, "token_counts": None, "token_matching": "not_measured", "changed_sentences": attack["attack"]["changed_sentences"], "semantic_review": "not_certified_by_program"})
    return {"samples": len(rows), "seeds": len(seeds), "source_clusters": len({r["source_cluster"] for r in rows}), "pairs": len(pairs), "pair_audits": audits, "semantic_validation": "not_performed", "schema_validation": "runtime_contract_checks"}


def export_inputs(rows):
    validate_v02(rows)
    result = []
    for sample in rows:
        mapping = {d["doc_id"]: f"d{i}" for i, d in enumerate(sample["documents"], 1)}
        # ID generation belongs to construction; export never derives it from gold.
        public = {"schema_version": VERSION, "question": sample["question"], "question_language": "zh", "instruction": INSTRUCTION,
                  "documents": [{"doc_id": mapping[d["doc_id"]], "title": f"材料 {i}", "language": "zh", "sentences": copy.deepcopy(d["sentences"])} for i, d in enumerate(sample["documents"], 1)]}
        public["sample_id"] = sample["sample_id"]
        validate_input(public)
        result.append(public)
    return result


def validate_input(row):
    require(isinstance(row, dict) and set(row) == INPUT_FIELDS, "model input has missing/extra fields")
    require(row["schema_version"] == VERSION and row["question_language"] == "zh", "invalid input version/language")
    require(isinstance(row["sample_id"], str) and row["sample_id"], "input ID required")
    # Fixed opaque identifier: samples cannot use seed/condition-encoded IDs.
    require(len(row["sample_id"]) == 26 and row["sample_id"].startswith("q_") and all(c in "0123456789abcdef" for c in row["sample_id"][2:]), "input ID must be opaque q_ + 24 hex")
    require(nonempty(row["question"]), "input question required")
    require(row["instruction"] == INSTRUCTION, "unexpected task instruction")
    validate_documents(row["documents"], neutral=True)
    return True


def score_sample(sample, prediction):
    valid = isinstance(prediction, dict) and prediction.get("status") == "ok" and prediction.get("schema_version") == VERSION
    answer = prediction.get("answer") if valid else None
    answer_ok = isinstance(answer, dict) and isinstance(answer.get("text"), str)
    em = int(answer_ok and normalize(answer["text"]) in {normalize(s) for s in [sample["answer"]["text"], *sample["answer"]["aliases"]]})
    diagnostics = []
    if not valid:
        diagnostics.append("missing" if prediction is None else "non_ok_or_invalid_version")
    if not answer_ok:
        diagnostics.append("invalid_answer")
    required = {"schema_version", "sample_id", "run_id", "status", "answer", "support", "submitted_steps"}
    allowed = required | {"raw_output", "error_message", "latency_ms"}
    prediction_format = valid and required <= set(prediction) <= allowed and nonempty(prediction.get("run_id"))
    if prediction_format:
        prediction_format = (isinstance(answer, dict) and set(answer) == {"text"} and isinstance(answer.get("text"), str)
                             and all(prediction.get(k) is None or isinstance(prediction[k], str) for k in ("raw_output", "error_message"))
                             and (prediction.get("latency_ms") is None or (type(prediction["latency_ms"]) in (int,float) and prediction["latency_ms"] >= 0)))
    if not prediction_format:
        diagnostics.append("invalid_prediction_format")
    available = set(texts(sample))
    try:
        predicted_support = refs(prediction.get("support")) if valid else set()
        require(predicted_support <= available, "unknown support")
        support_valid = prediction_format
    except (ValueError, TypeError, KeyError):
        predicted_support, support_valid = set(), False
        diagnostics.append("invalid_support")
    steps = prediction.get("submitted_steps") if valid else []
    if not isinstance(steps, list):
        steps = []
        diagnostics.append("invalid_steps")
    h = sample["hop_count"]
    if len(steps) != h:
        diagnostics.append("extra_steps" if len(steps) > h else "missing_steps")
    amap = alias_map(sample)
    canonical = lambda s: amap.get(normalize(s), normalize(s))
    proof_results = []
    for proof in sample["proofs"]:
        gold_support = set().union(*(refs(s["evidence"]) for s in proof["steps"]))
        hits = len(predicted_support & gold_support)
        precision = hits / len(predicted_support) if predicted_support else 0.0
        recall = hits / len(gold_support)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        prefix, mismatch = 0, None
        for i, gold in enumerate(proof["steps"]):
            matched = False
            if support_valid and i < len(steps):
                step = steps[i]
                try:
                    matched = (isinstance(step, dict) and set(step) == {"hop", "head", "relation", "tail", "qualifier", "evidence"} and type(step.get("hop")) is int and step["hop"] == i+1
                               and all(isinstance(step.get(k), str) for k in ("head", "relation", "tail", "qualifier"))
                               and canonical(step["head"]) == canonical(gold["head"])
                               and canonical(step["tail"]) == canonical(gold["tail"])
                               and step["relation"] == gold["relation"] and step["qualifier"] == gold["qualifier"]
                               and refs(step.get("evidence")) == refs(gold["evidence"]))
                    if matched and i:
                        matched = canonical(steps[i-1]["tail"]) == canonical(step["head"])
                except (ValueError, TypeError, KeyError):
                    matched = False
            if not matched:
                mismatch = i+1
                break
            prefix += 1
        sr = int(em and support_valid and len(steps) == h and prefix == h and predicted_support == gold_support)
        proof_results.append({"strict_sr": sr, "path_cfs": 100 * prefix / h, "support_precision": precision, "support_recall": recall, "support_f1": f1, "first_mismatch": mismatch})
    path = max(proof_results, key=lambda r: (r["path_cfs"], r["strict_sr"]))
    support = max(proof_results, key=lambda r: r["support_f1"])
    if path["first_mismatch"] is not None:
        diagnostics.append("proof_mismatch")
    return {"sample_id": sample["sample_id"], "seed_id": sample["seed_id"], "source_cluster": sample["source_cluster"],
            "answer_em": em, "support_precision": support["support_precision"], "support_recall": support["support_recall"], "support_f1": support["support_f1"],
            "strict_sr": max(r["strict_sr"] for r in proof_results), "path_cfs": path["path_cfs"], "first_submitted_step_mismatch": path["first_mismatch"],
            "prediction_status": prediction.get("status", "invalid") if isinstance(prediction, dict) else "missing", "diagnostics": diagnostics,
            "raw_prediction": copy.deepcopy(prediction)}


def average(values):
    return sum(values)/len(values) if values else None


METRICS = ("answer_em", "support_precision", "support_recall", "support_f1", "strict_sr", "path_cfs")


def summarize(samples, scored):
    by_id = {r["sample_id"]: r for r in scored}
    variants, pairs = defaultdict(list), defaultdict(dict)
    for sample in samples:
        variants[sample["variant"]].append(by_id[sample["sample_id"]])
        if sample["pair_id"]:
            pairs[sample["pair_id"]][sample["variant"]] = sample
    macro = {}
    for variant, items in variants.items():
        seeds = defaultdict(list)
        for item in items:
            seeds[item["seed_id"]].append(item)
        macro[variant] = {m: average([average([r[m] for r in group]) for group in seeds.values()]) for m in METRICS}
    attacks = defaultdict(list)
    for members in pairs.values():
        if set(members) != {"clean_control", "adversarial"}:
            continue  # Partitions with mismatched QC never create a new denominator.
        c, a = members["clean_control"], members["adversarial"]
        attacks[a["attack"]["primary_type"]].append((c["seed_id"], by_id[c["sample_id"]], by_id[a["sample_id"]]))
    paired = {}
    for mechanism, values in attacks.items():
        metrics = {}
        for metric in ("answer_em", "strict_sr"):
            seeds = defaultdict(list)
            for seed, c, a in values:
                seeds[seed].append((c[metric]-a[metric], c[metric]*(1-a[metric]), c[metric], c[metric]*a[metric]))
            means = [tuple(average([v[i] for v in group]) for i in range(4)) for group in seeds.values()]
            numerator = sum(c[metric]*(1-a[metric]) for _, c, a in values)
            denominator = sum(c[metric] for _, c, _ in values)
            weighted_denominator = sum(v[2] for v in means)
            metrics[metric] = {"drop_percentage_points": 100*average([v[0] for v in means]),
                               "asr_numerator": numerator, "asr_denominator": denominator, "raw_pair_asr": numerator/denominator if denominator else None,
                               "seed_weighted_asr": sum(v[1] for v in means)/weighted_denominator if weighted_denominator else None,
                               "robust_success": average([v[3] for v in means])}
        paired[mechanism] = {"pairs": len(values), "seeds": len({v[0] for v in values}), "metrics": metrics}
    return {"samples": len(samples), "seeds": len({r["seed_id"] for r in samples}), "source_clusters": len({r["source_cluster"] for r in samples}),
            "by_variant_seed_macro": macro, "paired_by_mechanism": paired,
            "metrics": {m: average([average([r[m] for r in scored if r["seed_id"] == seed]) for seed in {r["seed_id"] for r in scored}]) for m in METRICS}}


def evaluate_v02(samples, predictions):
    audit = validate_v02(samples)
    known = {s["sample_id"] for s in samples}
    indexed = {}
    for row in predictions:
        require(isinstance(row, dict) and isinstance(row.get("sample_id"), str) and row["sample_id"] in known, "unknown/invalid prediction sample_id")
        sid = row["sample_id"]
        require(sid not in indexed, "duplicate prediction sample_id")
        indexed[sid] = row
    scored = [score_sample(s, indexed.get(s["sample_id"])) for s in samples]
    partitions = {}
    for name in ("official", "candidate", "fixture", "rejected"):
        def partition(s):
            if s["origin"] == "fictional_fixture": return "fixture"
            if s["qc"]["status"] == "rejected": return "rejected"
            if s["qc"]["status"] == "accepted" and s["qc"]["human_verified"]: return "official"
            return "candidate"
        members = [s for s in samples if partition(s) == name]
        selected = {s["sample_id"] for s in members}
        partitions[name] = summarize(members, [r for r in scored if r["sample_id"] in selected])
    return {"schema_version": VERSION, "note": "candidate scores use unverified reference gold; rules are not LLMs; observable proofs are not internal reasoning",
            "counts": {"samples": len(samples), "predictions": len(predictions), "missing": len(samples)-len(predictions), "seeds": audit["seeds"], "source_clusters": audit["source_clusters"]},
            "partitions": partitions, "per_sample": scored}
