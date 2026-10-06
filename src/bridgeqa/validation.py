"""Core structural checks. Does not establish factual or semantic validity."""

def require(condition, message):
    if not condition:
        raise ValueError(message)


def evidence_key(item):
    require(isinstance(item, dict), "evidence reference must be an object")
    require(isinstance(item.get("doc_id"), str), "evidence doc_id must be a string")
    require(type(item.get("sent_id")) is int, "sent_id must be an integer")
    return item["doc_id"], item["sent_id"]


def validate_samples_v01(rows):
    require(bool(rows), "dataset is empty")
    ids, pairs, seeds = set(), {}, {}
    for row in rows:
        sid = row.get("sample_id")
        require(isinstance(sid, str) and sid, "sample_id is required")
        require(sid not in ids, f"duplicate sample_id: {sid}")
        ids.add(sid)
        for field in ("seed_id", "split", "origin", "domain", "track", "variant", "question", "question_language", "language_condition"):
            require(isinstance(row.get(field), str) and row[field], f"{sid}: missing string {field}")
        require(row.get("schema_version") == "0.1", f"{sid}: unsupported schema_version")
        require(row["track"] == "context_attack", f"{sid}: v0.1 reference tool supports context_attack only")
        require(row["variant"] != "challenge", f"{sid}: challenge schema/scoring not implemented")
        require(row["variant"] in {"gold_only", "clean_control", "adversarial", "challenge"}, f"{sid}: invalid variant")
        require(row["split"] in {"example", "dev_public", "test_hidden"}, f"{sid}: invalid split")
        require(row["origin"] in {"native_zh", "translated_seed", "fictional_fixture"}, f"{sid}: invalid origin")
        require(row.get("topology") == "chain", f"{sid}: reference tool supports chain topology only")
        hop = row.get("hop_count")
        require(type(hop) is int and hop in {2, 3, 4}, f"{sid}: hop_count must be 2/3/4")
        language = row["language_condition"]
        require(len(language) == hop and set(language) <= {"Z", "E"}, f"{sid}: invalid language_condition")
        require(isinstance(row.get("answer"), dict) and isinstance(row["answer"].get("canonical_id"), str), f"{sid}: canonical answer required")
        docs = row.get("documents")
        require(isinstance(docs, list) and docs, f"{sid}: documents required")
        refs, doc_ids, sentence_lang = set(), set(), {}
        for doc in docs:
            did = doc.get("doc_id")
            require(isinstance(did, str) and did not in doc_ids, f"{sid}: invalid/duplicate doc_id")
            doc_ids.add(did)
            require(doc.get("language") in {"zh", "en"}, f"{sid}: unsupported doc language")
            require(isinstance(doc.get("sentences"), list) and doc["sentences"], f"{sid}: sentences required")
            for sentence in doc["sentences"]:
                ref = evidence_key({"doc_id": did, "sent_id": sentence.get("sent_id")})
                require(ref not in refs and ref[1] >= 0, f"{sid}: duplicate/invalid sentence")
                require(isinstance(sentence.get("text"), str) and sentence["text"], f"{sid}: sentence text required")
                refs.add(ref)
                sentence_lang[ref] = "Z" if doc["language"] == "zh" else "E"
        support = row.get("gold_support")
        require(isinstance(support, list) and support, f"{sid}: gold_support required")
        support_keys = [evidence_key(item) for item in support]
        require(len(set(support_keys)) == len(support_keys) and set(support_keys) <= refs, f"{sid}: invalid gold_support")
        path = row.get("reasoning_path")
        require(isinstance(path, list) and len(path) == hop, f"{sid}: path length mismatch")
        path_refs = set()
        for index, step in enumerate(path):
            require(step.get("hop") == index + 1, f"{sid}: unordered hop")
            for field in ("head", "relation", "tail"):
                require(isinstance(step.get(field), str) and step[field], f"{sid}: missing path {field}")
            if index:
                require(path[index - 1]["tail"] == step["head"], f"{sid}: disconnected chain")
            require(isinstance(step.get("evidence"), list) and step["evidence"], f"{sid}: hop evidence required")
            keys = {evidence_key(item) for item in step["evidence"]}
            require(keys <= refs, f"{sid}: unknown hop evidence")
            require(all(sentence_lang[key] == language[index] for key in keys), f"{sid}: evidence language mismatch")
            path_refs |= keys
        require(path[-1]["tail"] == row["answer"]["canonical_id"], f"{sid}: final entity mismatch")
        require(path_refs == set(support_keys), f"{sid}: gold support/path evidence mismatch")
        if row["variant"] == "adversarial":
            require(isinstance(row.get("attack"), dict), f"{sid}: attack metadata required")
            target = row["attack"].get("target_hop")
            require(type(target) is int and 1 <= target <= hop, f"{sid}: invalid target_hop")
        elif row["variant"] in {"clean_control", "gold_only"}:
            require(row.get("attack") is None, f"{sid}: control must have null attack")
        seeds.setdefault(row["seed_id"], set()).add(row["split"])
        pid = row.get("pair_id")
        if row["variant"] in {"clean_control", "adversarial"}:
            require(isinstance(pid, str) and pid, f"{sid}: pair_id required")
            pairs.setdefault(pid, []).append(row)
        elif row["variant"] == "gold_only":
            require(pid is None, f"{sid}: gold_only pair_id must be null")
    require(all(len(value) == 1 for value in seeds.values()), "seed split leakage detected")
    for pid, members in pairs.items():
        require(len(members) == 2 and {r["variant"] for r in members} == {"clean_control", "adversarial"}, f"{pid}: expected one control and one attack")
        left, right = members
        for field in ("seed_id", "split", "origin", "domain", "track", "question", "question_language", "answer", "hop_count", "topology", "gold_support", "reasoning_path", "language_condition", "crosslingual_mode"):
            require(left.get(field) == right.get(field), f"{pid}: paired invariant changed: {field}")
        def structure(row):
            return [(d["doc_id"], d["language"], [s["sent_id"] for s in d["sentences"]]) for d in row["documents"]]
        require(structure(left) == structure(right), f"{pid}: document/position/language structure changed")
        def gold_text(row):
            return {(d["doc_id"], s["sent_id"]): s["text"] for d in row["documents"] for s in d["sentences"] if (d["doc_id"], s["sent_id"]) in {evidence_key(e) for e in row["gold_support"]}}
        require(gold_text(left) == gold_text(right), f"{pid}: gold evidence text changed")
    return {"samples": len(rows), "seeds": len(seeds), "pairs": len(pairs), "semantic_validation": "not_performed"}


def validate_samples(rows):
    require(bool(rows), "dataset is empty")
    versions = {r.get("schema_version") for r in rows}
    require(len(versions) == 1, "mixed sample versions")
    if versions == {"0.2"}:
        from .protocol import validate_v02
        return validate_v02(rows)
    return validate_samples_v01(rows)
