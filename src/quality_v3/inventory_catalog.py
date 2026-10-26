"""Exact source-span catalog adapter; development successor to numeric citations.

The canonical contract remains in [support_contract.py](support_contract.py).
This adapter does no semantic extraction and never repairs a model proposal.
"""
from __future__ import annotations

import copy
import hashlib
import json

import jsonschema

import support_contract as canonical


VERSION = "support-inventory-catalog-v0.6"
_REQUEST_KEYS = ("contract_version", "canonical_request_digest", "question", "query",
                 "contexts", "requested_edges", "entity_bindings", "span_catalog", "catalog_digest")
_CANONICAL_FIELDS = ("question", "query", "contexts", "requested_edges", "entity_bindings")
_SENTENCE_ENDS = frozenset("。！？!?．.\n\r")
_CLAUSE_ENDS = _SENTENCE_ENDS | frozenset("，,；;：:")
_CLOSERS = frozenset("”’\"'」』）)]}》〉】〕")


class CatalogContractError(canonical.InventoryContractError):
    """A catalog request or an ID-only proposal violates its exact binding."""


def _require(condition, message):
    if not condition:
        raise CatalogContractError(message)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


CATALOG_SCHEMA = copy.deepcopy(canonical.INVENTORY_SCHEMA)
_properties = CATALOG_SCHEMA["properties"]
_properties["contract_version"] = {"enum": [VERSION]}
_properties["canonical_request_digest"] = _properties.pop("request_digest")
_properties["catalog_digest"] = {"type": "string", "minLength": 64, "maxLength": 64}
_properties["facts"]["items"]["properties"]["support_groups"]["items"]["items"] = {
    "type": "object", "properties": {"span_id": {"type": "string", "minLength": 1}},
    "required": ["span_id"], "additionalProperties": False}
CATALOG_SCHEMA["required"] = [
    "contract_version", "canonical_request_digest", "catalog_digest", "facts", "proof_paths", "reason"]

CATALOG_PROMPT = """只依据当前 contexts 和精确 span_catalog 为每一 requested_edges 登记支持提案。
输出 contract_version、canonical_request_digest、catalog_digest 的输入原值。
逐 fact_id 恰登记一次，status=support_proposed/not_found/unresolved；support_proposed 的
support_groups 非空，其他状态为空。每组为支持该边所需全部引文的合取；多个组只是替代
支持提案，不代表独立来源。每条引用仅写 {"span_id":"输入目录中的ID"}，不要计算字符索引，
不要手写引文或生成新 span_id。片段不够时可在同一合取组联合引用多个原片段。
目录保留原标点、对话和否定；目录只是定位线索，不能以字面出现证明关系成立。
sentence 与 clause 片段会重叠；同一原文的句级与分句级引用不因此构成重复独立支持。
不借百科、候选理由或目录外内容补边；语义不明用 unresolved。
proof_paths 必须是 {fact_ids:[...],entity_ids:[...]}，只用 support_proposed 的请求边，
从 query.start 按 query.steps 每步 child→parent 走完整路径；scope_by_step 非空时逐步使用，
否则用 query.scope。列全已登记请求图中的完整路径，不把 reason 当路径，也不声称穷尽
自然文本所有支持或已经验收删证。按给定 JSON schema 输出。"""


def _segments(text, delimiters):
    """Partition original character positions without normalization or dropped characters."""
    result, start, index = [], 0, 0
    while index < len(text):
        if text[index] not in delimiters:
            index += 1
            continue
        end = index + 1
        # Keep repeated punctuation, closing dialogue marks and CRLF together.
        while end < len(text) and (text[end] in delimiters or text[end] in _CLOSERS):
            end += 1
        result.append((start, end))
        start, index = end, end
    if start < len(text):
        result.append((start, len(text)))
    return result


def _span_catalog(request):
    spans = []
    seen_ids = set()
    for context in request["contexts"]:
        text = context["text"]
        intervals = {}
        for level, separators in (("sentence", _SENTENCE_ENDS), ("clause", _CLAUSE_ENDS)):
            for start, end in _segments(text, separators):
                intervals.setdefault((start, end), []).append(level)
        for (start, end), levels in sorted(intervals.items()):
            occurrence = {"context_id": context["context_id"], "start": start,
                          "end": end, "quote": text[start:end]}
            span_id = "SP-" + _digest({"catalog_version": VERSION,
                "canonical_request_digest": request["request_digest"], **occurrence})[:24]
            _require(span_id not in seen_ids, "span ID collision")
            seen_ids.add(span_id)
            spans.append({"span_id": span_id, **occurrence, "granularities": levels})
    return spans


def build_catalog_request(request):
    """Build deterministic complete sentence/clause partitions of canonical sources.

    A span ID is bound to the full canonical request and original occurrence,
    including the context and character interval. Identical text at distinct
    positions has distinct IDs. Identical sentence/clause intervals share one
    ID with both granularities, avoiding duplicate directory entries.
    """
    canonical.validate_inventory_request(request)
    result = {"contract_version": VERSION, "canonical_request_digest": request["request_digest"],
              **{k: copy.deepcopy(request[k]) for k in _CANONICAL_FIELDS},
              "span_catalog": _span_catalog(request)}
    result["catalog_digest"] = _digest(result)
    return result


def _validated_canonical_request(catalog_request):
    _require(isinstance(catalog_request, dict) and set(catalog_request) == set(_REQUEST_KEYS),
             "catalog request has unexpected or missing fields")
    request = {"contract_version": canonical.VERSION,
               "request_digest": catalog_request["canonical_request_digest"],
               **{k: copy.deepcopy(catalog_request[k]) for k in _CANONICAL_FIELDS}}
    canonical.validate_inventory_request(request)
    # Regeneration also detects omitted spans, altered granularity and a forged
    # catalog digest. A digest alone is not an authority over source positions.
    _require(catalog_request == build_catalog_request(request),
             "catalog is not the exact complete catalog for its canonical request")
    return request


def materialize_inventory(response, catalog_request):
    """Expand only known span IDs, then enforce the unchanged canonical contract.

    No approximate quote matching, extra support groups, inferred paths or
    status changes occur here. Invalid proposals raise instead of being fixed.
    """
    request = _validated_canonical_request(catalog_request)
    try:
        jsonschema.validate(response, CATALOG_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise CatalogContractError("catalog response schema invalid: " + exc.message) from exc
    _require(response["canonical_request_digest"] == request["request_digest"]
             and response["catalog_digest"] == catalog_request["catalog_digest"],
             "response belongs to another canonical request/catalog")
    spans = {s["span_id"]: s for s in catalog_request["span_catalog"]}
    result = {"contract_version": canonical.VERSION, "request_digest": request["request_digest"],
              "facts": copy.deepcopy(response["facts"]),
              "proof_paths": copy.deepcopy(response["proof_paths"]), "reason": response["reason"]}
    for fact in result["facts"]:
        for group in fact["support_groups"]:
            for position, reference in enumerate(group):
                span_id = reference["span_id"]
                _require(span_id in spans, "unknown or cross-request span ID: " + span_id)
                group[position] = {k: spans[span_id][k] for k in ("context_id", "start", "end", "quote")}
    canonical.validate_inventory(result, request)
    return result
