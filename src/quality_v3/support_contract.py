"""Development-only support registration contract, version 0.5.

This module checks declared graph structure and exact quotation occurrences.
It cannot establish entailment, find omitted natural-language supports, or
authorize a deletion family. See the prior findings at
[validation](../../QA_Generator/validation/2026-10-22_质量修复与skills三轮迭代.md).
No historical experiment or production entry point imports this module.
"""
from __future__ import annotations

import copy
import hashlib
import json


VERSION = "support-inventory-v0.5"
ROLES = ("father", "mother", "parent")
STATUSES = ("support_proposed", "not_found", "unresolved")

_CITATION_SCHEMA = {
    "type": "object", "properties": {
        "context_id": {"type": "string", "minLength": 1},
        "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 1},
        "quote": {"type": "string", "minLength": 1}},
    "required": ["context_id", "start", "end", "quote"],
    "additionalProperties": False}
INVENTORY_SCHEMA = {
    "type": "object", "properties": {
        "contract_version": {"enum": [VERSION]},
        "request_digest": {"type": "string", "minLength": 64, "maxLength": 64},
        "facts": {"type": "array", "items": {
            "type": "object", "properties": {
                "fact_id": {"type": "string", "minLength": 1},
                "status": {"enum": list(STATUSES)},
                "support_groups": {"type": "array", "items": {
                    "type": "array", "minItems": 1, "items": _CITATION_SCHEMA}},
                "reason": {"type": "string", "minLength": 1}},
            "required": ["fact_id", "status", "support_groups", "reason"],
            "additionalProperties": False}},
        "proof_paths": {"type": "array", "items": {
            "type": "object", "properties": {
                "fact_ids": {"type": "array", "minItems": 1,
                             "items": {"type": "string", "minLength": 1}},
                "entity_ids": {"type": "array", "minItems": 2,
                               "items": {"type": "string", "minLength": 1}}},
            "required": ["fact_ids", "entity_ids"], "additionalProperties": False}},
        "reason": {"type": "string", "minLength": 1}},
    "required": ["contract_version", "request_digest", "facts", "proof_paths", "reason"],
    "additionalProperties": False}

INVENTORY_PROMPT = """只按当前 contexts 为每一 requested_edges 提交支持登记提案，不用百科或候选理由补证。
响应使用 contract_version 和 request_digest 原值。逐 fact_id 恰登记一项；status 为
support_proposed / not_found / unresolved。support_proposed 必须有非空 support_groups，
其余状态的 support_groups 为空。每组是共同支持该边的合取引文；多组表示替代支持提案，
不表示独立文献。逐条引文给 context_id、quote 和 Python Unicode 字符索引 [start,end)，
须严格等于当前文本对应片段。支持语义不明时用 unresolved，不把字面出现当关系成立。
proof_paths 明确为 {fact_ids:[...],entity_ids:[...]}，只使用 support_proposed 边，
从 query.start 开始按 query.steps 每步 child→parent 走完整路径；步骤 scope 优先采用
scope_by_step，否则用 query.scope。必须列全已登记请求边图中能组成的完整路径，不能用
反向单边、实体数组或 reason 代替。不在本合同中声称穷尽自然文本支持或已验收删证。
输出所给 JSON 合同。"""


class InventoryContractError(ValueError):
    """An input or response violates the public registration contract."""


def _require(condition, message):
    if not condition:
        raise InventoryContractError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _object(value, keys, where):
    _require(isinstance(value, dict) and set(value) == set(keys),
             f"{where}: unexpected or missing fields")


def _digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def stable_fact_id(edge):
    """Content ID for callers without a stable source ID; independent of text/order."""
    _require(isinstance(edge, dict) and all(k in edge for k in
             ("parent", "child", "parent_role", "scope")), "fact identity fields missing")
    return "F-" + _digest({k: edge[k] for k in ("parent", "child", "parent_role", "scope")})


def _request_digest(request):
    return _digest({k: v for k, v in request.items() if k != "request_digest"})


def make_inventory_request(question, query, contexts, requested_edges, entity_bindings):
    """Build a minimal request, accepting legacy id/parent_role/entity bindings.

    Source IDs are preserved, not regenerated when contexts are edited. Without
    one, the edge identity determines its ID. An ID must never name two edges.
    This constructor intentionally drops candidate reasons and retrieval hints.
    """
    _require(isinstance(requested_edges, list), "requested_edges must be an array")
    _require(isinstance(entity_bindings, list) and all(isinstance(e, dict) for e in entity_bindings),
             "entity_bindings must be an array of objects")
    _require(isinstance(contexts, list) and all(isinstance(c, dict) for c in contexts),
             "contexts must be an array of objects")
    edges = []
    for edge in requested_edges:
        _require(isinstance(edge, dict), "requested edge must be an object")
        if "fact_id" in edge and "id" in edge:
            _require(edge["fact_id"] == edge["id"], "conflicting fact_id and legacy id")
        normalized = {k: copy.deepcopy(edge.get(k))
                      for k in ("parent", "child", "parent_role", "scope")}
        if normalized["parent_role"] is None:
            normalized["parent_role"] = edge.get("role")
        normalized["fact_id"] = edge.get("fact_id", edge.get("id", stable_fact_id(normalized)))
        edges.append(normalized)
    entities = [{"id": e.get("id"), "name": e.get("name"),
                 "aliases": copy.deepcopy(e.get("aliases", []))} for e in entity_bindings]
    request = {
        "contract_version": VERSION, "question": question, "query": copy.deepcopy(query),
        "contexts": [{"context_id": c.get("context_id"), "text": c.get("text")} for c in contexts],
        "requested_edges": edges, "entity_bindings": entities}
    request["request_digest"] = _request_digest(request)
    validate_inventory_request(request)
    return request


def validate_inventory_request(request):
    """Reject ambiguous identifiers and invalid query/edge endpoints before calling a model."""
    _object(request, ("contract_version", "request_digest", "question", "query", "contexts",
                      "requested_edges", "entity_bindings"), "request")
    _require(request["contract_version"] == VERSION, "wrong request version")
    _require(request["request_digest"] == _request_digest(request), "request digest mismatch")
    _require(_text(request["question"]), "question must be nonempty")
    _require(isinstance(request["contexts"], list), "contexts must be an array")
    context_ids = set()
    for context in request["contexts"]:
        _object(context, ("context_id", "text"), "context")
        _require(_text(context["context_id"]) and context["context_id"] not in context_ids,
                 "invalid or duplicate context ID")
        _require(isinstance(context["text"], str), "context text must be a string")
        context_ids.add(context["context_id"])
    _require(isinstance(request["entity_bindings"], list), "entity_bindings must be an array")
    entity_ids = set()
    for entity in request["entity_bindings"]:
        _object(entity, ("id", "name", "aliases"), "entity")
        _require(_text(entity["id"]) and entity["id"] not in entity_ids,
                 "invalid or duplicate entity ID")
        _require(_text(entity["name"]), "entity name must be nonempty")
        _require(isinstance(entity["aliases"], list) and all(_text(a) for a in entity["aliases"]),
                 "entity aliases must be nonempty strings")
        entity_ids.add(entity["id"])
    query = request["query"]
    _require(isinstance(query, dict) and {"operation", "start", "steps"} <= set(query)
             and not set(query) - {"operation", "start", "steps", "scope", "scope_by_step"},
             "query fields invalid")
    _require(query["operation"] in ("parents", "parent_chain"), "unsupported query operation")
    _require(isinstance(query["start"], str) and query["start"] in entity_ids, "unknown query start")
    _require(isinstance(query["steps"], list) and bool(query["steps"])
             and all(s in ROLES for s in query["steps"]), "invalid query steps")
    scopes = query.get("scope_by_step")
    if scopes is not None:
        _require(isinstance(scopes, list) and len(scopes) == len(query["steps"])
                 and all(_text(s) for s in scopes), "scope_by_step must cover every step")
    if "scope" in query:
        _require(_text(query["scope"]), "query scope must be nonempty")
    _require(scopes is not None or _text(query.get("scope")), "query scope is required")
    _require(isinstance(request["requested_edges"], list), "requested_edges must be an array")
    fact_ids, identities = set(), set()
    for edge in request["requested_edges"]:
        _object(edge, ("fact_id", "parent", "child", "parent_role", "scope"), "edge")
        _require(_text(edge["fact_id"]) and edge["fact_id"] not in fact_ids,
                 "invalid or duplicate fact ID")
        _require(isinstance(edge["parent"], str) and edge["parent"] in entity_ids
                 and isinstance(edge["child"], str) and edge["child"] in entity_ids,
                 "edge references unknown entity ID")
        _require(edge["parent"] != edge["child"], "self-parent edge is invalid")
        _require(edge["parent_role"] in ROLES and _text(edge["scope"]), "edge role/scope invalid")
        identity = tuple(edge[k] for k in ("parent", "child", "parent_role", "scope"))
        _require(identity not in identities, "duplicate edge identity with different IDs")
        fact_ids.add(edge["fact_id"])
        identities.add(identity)
    return True


def _citation_key(citation):
    return tuple(citation[k] for k in ("context_id", "start", "end", "quote"))


def _validate_citation(citation, texts, where):
    _object(citation, ("context_id", "start", "end", "quote"), where)
    cid, start, end, quote = (citation[k] for k in ("context_id", "start", "end", "quote"))
    _require(isinstance(cid, str) and cid in texts, f"{where}: unknown context ID")
    _require(type(start) is int and type(end) is int and 0 <= start < end <= len(texts[cid]),
             f"{where}: invalid character interval")
    _require(_text(quote) and texts[cid][start:end] == quote,
             f"{where}: quote does not match exact occurrence")


def _enumerate_paths(request, active):
    """Enumerate only the supplied request graph, never natural-language evidence."""
    query = request["query"]
    scopes = query.get("scope_by_step")
    if scopes is None:
        scopes = [query.get("scope")] * len(query["steps"])
    paths = []

    def walk(entity_ids, fact_ids):
        index = len(fact_ids)
        if index == len(query["steps"]):
            paths.append({"fact_ids": fact_ids, "entity_ids": entity_ids})
            return
        for edge in request["requested_edges"]:
            if edge["fact_id"] not in active or edge["child"] != entity_ids[-1]:
                continue
            if query["steps"][index] != "parent" and edge["parent_role"] != query["steps"][index]:
                continue
            if edge["scope"] != scopes[index] or edge["parent"] in entity_ids:
                continue
            walk(entity_ids + [edge["parent"]], fact_ids + [edge["fact_id"]])

    walk([query["start"]], [])
    return sorted(paths, key=lambda p: (p["fact_ids"], p["entity_ids"]))


def validate_inventory(response, request):
    """Check the complete public contract or raise InventoryContractError.

    A valid return is a protocol result, never a semantic acceptance. Even a
    perfect structural response may contain a negation, identity-only support,
    wrong group semantics, or unregistered repetitions in natural text.
    """
    validate_inventory_request(request)
    _object(response, ("contract_version", "request_digest", "facts", "proof_paths", "reason"), "response")
    _require(response["contract_version"] == VERSION, "wrong response version")
    _require(response["request_digest"] == request["request_digest"], "response belongs to another request")
    _require(_text(response["reason"]), "response reason must be nonempty")
    _require(isinstance(response["facts"], list), "facts must be an array")
    expected = {e["fact_id"] for e in request["requested_edges"]}
    seen, active = set(), set()
    texts = {c["context_id"]: c["text"] for c in request["contexts"]}
    group_count = 0
    for fact in response["facts"]:
        _object(fact, ("fact_id", "status", "support_groups", "reason"), "fact registration")
        fid = fact["fact_id"]
        _require(isinstance(fid, str) and fid in expected and fid not in seen,
                 "unknown or duplicate registered fact ID")
        _require(fact["status"] in STATUSES and _text(fact["reason"]), "invalid status/reason")
        groups = fact["support_groups"]
        _require(isinstance(groups, list), "support_groups must be an array")
        _require(bool(groups) == (fact["status"] == "support_proposed"),
                 "support_proposed requires groups; not_found/unresolved require none")
        seen.add(fid)
        unique_groups = set()
        for group in groups:
            _require(isinstance(group, list) and bool(group), "empty support group")
            for citation in group:
                _validate_citation(citation, texts, "support citation")
            keys = [_citation_key(c) for c in group]
            _require(len(set(keys)) == len(keys), "duplicate citation in support group")
            group_key = tuple(sorted(keys))
            _require(group_key not in unique_groups, "duplicate support group")
            unique_groups.add(group_key)
            group_count += 1
        if groups:
            active.add(fid)
    _require(seen == expected, "missing requested edge registration")
    _require(isinstance(response["proof_paths"], list), "proof_paths must be an array")
    paths = []
    known_entities = {e["id"] for e in request["entity_bindings"]}
    for path in response["proof_paths"]:
        _object(path, ("fact_ids", "entity_ids"), "proof path")
        fids, eids = path["fact_ids"], path["entity_ids"]
        _require(isinstance(fids, list) and isinstance(eids, list)
                 and len(fids) == len(request["query"]["steps"]) and len(eids) == len(fids) + 1,
                 "proof must encode a complete query-length path")
        _require(all(isinstance(f, str) and f in active for f in fids), "proof uses undeclared/unproposed fact")
        _require(all(isinstance(e, str) and e in known_entities for e in eids), "proof uses unknown entity ID")
        _require(len(set(fids)) == len(fids) and len(set(eids)) == len(eids), "proof repeats fact/entity")
        key = (tuple(fids), tuple(eids))
        _require(key not in paths, "duplicate proof path")
        paths.append(key)
    expected_paths = _enumerate_paths(request, active)
    canonical = {(tuple(p["fact_ids"]), tuple(p["entity_ids"])) for p in expected_paths}
    _require(set(paths) == canonical, "proof direction/role/scope invalid or registered-graph path omitted")
    return {"contract_version": VERSION, "protocol_valid": True,
            "registered_edges": len(seen), "proposed_support_groups": group_count,
            "registered_graph_paths": expected_paths, "semantic_review_required": True,
            "semantic_validity_established": False, "natural_text_coverage_established": False,
            "release_ready": False}


def _deletion_map(request, deletions):
    _require(isinstance(deletions, list), "deletions must be an array of actual text spans")
    texts = {c["context_id"]: c["text"] for c in request["contexts"]}
    by_context = {cid: [] for cid in texts}
    for deletion in deletions:
        _validate_citation(deletion, texts, "text deletion")
        by_context[deletion["context_id"]].append(copy.deepcopy(deletion))
    for cid, spans in by_context.items():
        spans.sort(key=lambda d: d["start"])
        _require(all(left["end"] <= right["start"] for left, right in zip(spans, spans[1:])),
                 "overlapping or duplicate deletion intervals")
    return by_context


def apply_text_deletions(request, deletions):
    """Apply exact source-coordinate deletions, retaining context IDs and empty texts."""
    validate_inventory_request(request)
    by_context = _deletion_map(request, deletions)
    result = []
    for context in request["contexts"]:
        text, cursor, pieces = context["text"], 0, []
        for deletion in by_context[context["context_id"]]:
            pieces.append(text[cursor:deletion["start"]])
            cursor = deletion["end"]
        pieces.append(text[cursor:])
        result.append({"context_id": context["context_id"], "text": "".join(pieces)})
    return result


def retained_inventory(response, request, deletions, after_contexts=None):
    """Track registered original occurrences through actual deletions.

    Any overlap removes that citation's entire conjunctive group. Surviving
    occurrences move only by the known edit map; identical text elsewhere is
    never substituted. This is a conservative *registered-group* projection:
    cross-boundary new text and omitted source supports need semantic review.
    It does not accept deleted fact IDs as a substitute for text edits.
    """
    validate_inventory(response, request)
    by_context = _deletion_map(request, deletions)
    actual_contexts = apply_text_deletions(request, deletions)
    if after_contexts is not None:
        _require(after_contexts == actual_contexts,
                 "after_contexts differ from the actual declared text deletions")
    projected_request = make_inventory_request(
        request["question"], request["query"], actual_contexts,
        request["requested_edges"], request["entity_bindings"])
    projected = {"contract_version": VERSION, "request_digest": projected_request["request_digest"],
                 "facts": [], "proof_paths": [],
                 "reason": "原登记组经实际文本删除的保守投影；未核验新文本语义或支持穷尽。"}
    removed_groups = []
    for fact in response["facts"]:
        groups = []
        for group_index, group in enumerate(fact["support_groups"]):
            mapped, removed = [], False
            for citation in group:
                spans = by_context[citation["context_id"]]
                if any(d["start"] < citation["end"] and citation["start"] < d["end"] for d in spans):
                    removed = True
                    break
                shift = sum(d["end"] - d["start"] for d in spans if d["end"] <= citation["start"])
                mapped.append({**citation, "start": citation["start"] - shift, "end": citation["end"] - shift})
            if removed:
                removed_groups.append({"fact_id": fact["fact_id"], "group_index": group_index})
            else:
                groups.append(mapped)
        # Empty after projection is unresolved, never a semantic not_found claim.
        projected["facts"].append({"fact_id": fact["fact_id"],
            "status": "support_proposed" if groups else "unresolved", "support_groups": groups,
            "reason": "仅映射未被删除的原始引文 occurrence，空组需重新语义核验。"})
    active = {f["fact_id"] for f in projected["facts"] if f["support_groups"]}
    projected["proof_paths"] = _enumerate_paths(projected_request, active)
    report = validate_inventory(projected, projected_request)
    report["removed_registered_groups"] = removed_groups
    report["deletion_validity_established"] = False
    return {"request": projected_request, "inventory": projected, "report": report}
