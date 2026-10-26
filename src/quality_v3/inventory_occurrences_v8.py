"""Windowed per-fact occurrence proposals with explicit deterministic assembly.

Uses exact source partitions from [inventory_coverage.py](inventory_coverage.py)
and canonical graph/citation validation from [support_contract.py](support_contract.py).
Neither predecessor nor any frozen batch is changed. Positive model proposals,
model group reviews and independent semantic acceptance remain distinct.
"""
from __future__ import annotations

import copy
import hashlib
import json

import jsonschema

import inventory_coverage as previous
import support_contract as canonical


VERSION = "support-occurrences-v0.8"
REVIEW_VERSION = "support-occurrence-group-review-v0.8"
MAX_ANCHOR_UNITS = 8
_S = {"type": "string", "minLength": 1}
_IDS = {"type": "array", "items": _S, "minItems": 1, "uniqueItems": True}
_GROUNDING = previous._object({"entity_id": _S, "unit_id": _S, "surface": _S})
_ANCHOR = previous._object({"unit_id": _S, "surface": _S})
ANCHOR_KEYS = ("child", "parent", "predicate", "parent_role", "scope")
_GROUP = previous._object({"unit_ids": _IDS,
    "endpoint_groundings": {"type": "array", "items": _GROUNDING, "minItems": 2, "maxItems": 2},
    "anchors": previous._object({key: _ANCHOR for key in ANCHOR_KEYS}), "reason": _S})
OCCURRENCE_SCHEMA = previous._object({"contract_version": {"enum": [VERSION]},
    "window_id": _S, "window_digest": _S,
    "occurrences": {"type": "array", "items": previous._object({"anchor_unit_id": _S,
        "verdict": {"enum": ["supported", "unsupported", "unknown"]},
        "support_group": {"anyOf": [_GROUP, {"type": "null"}]}, "reason": _S})}})

_ROLE_DEFINITIONS = {
    "father": "parent_surface是child_surface的父亲；child是子辈，parent是父辈，父辈男性角色须由组内语义建立。",
    "mother": "parent_surface是child_surface的母亲；child是子辈，parent是母辈，母亲角色须由组内语义建立。",
    "parent": "parent_surface是child_surface的父母之一；child是子辈，parent是上一辈，不要求确定父或母。"}

OCCURRENCE_PROMPT = """逐anchor查找唯一目标fact的支持出现位置。只审本窗口anchor_unit_ids，全部逐一输出，
不得找到第一条好句就停止。child_surface是子辈，parent_surface是其所问父母辈，
role_definition说明方向；姓名共现、别称表和作品记忆不增加关系。
展示surface为空或surface_resolution为unresolved时，不得从ID或元数据猜姓名/性别；
涉及该身份的关系无法裁定就用unknown，不能把未知当无支持。
核心问题：本unit是否完成一处可区分的目标关系断言，而不是它是否贡献任意支持成分。
一次陈述跨相邻units时只给完成目标人物/答语的那个唯一anchor为supported。
例如“甲生了两个儿子：”“长子乙，”，目标child=乙,parent=甲,role=parent（乙→甲），
只以完成乙身份的后者作anchor；前者仅谓词组件。儿子的性别不能确定甲为父亲或母亲。
问答中仅问题不是新的关系陈述；答句即使只是姓名，也可作为完成断言的anchor，但必须同组
引入实际问题、说话人/所问主体等前件。不能把同次问句/答案或句级/分句级当两次支持。
普通编号/姓名映射只是身份前件，不是新的亲属断言anchor：“甲的父亲=父17”应以亲属
档案中完成这条关系的unit为anchor，另context“父17=乙”仅补名字，不再算第二次。
问答答语因直接回答亲属问题可作为完成anchor，与普通身份lookup不同。
每anchor输出verdict=supported/unsupported/unknown；supported必须给support_group，
其余support_group=null。unsupported表示该unit不完成目标断言（可仍是别处支持组的前件）；
无法裁定是否另一次断言、角色、指代或范围时用unknown，不能当作没支持。
source_units全源只供选实际必要前件。支持组unit_ids必须包括本anchor及所需主体先行词、
问题/答句、说话人、编号身份映射、否定/更正/梦境/时间限定等实际原文，不能reason补证。
每组endpoint_groundings恰给child和parent各{entity_id,unit_id,surface}，surface用本组确切
出现的已登记纯姓名/唯一别称。anchors逐项给child/parent/predicate/parent_role/scope的
{unit_id,surface}原文依据；不可计算字符数、编引文或只引用scope标签。
scope按原文语义匹配fact.scope，不要求标签字面相等；普通直陈句可按实际语境作为范围依据，
若说话人/否定/梦境等限定对范围关键，必须引用该实际限定，不能把上下文之外的设定搬入组。
不同真重述各有完成anchor；允许复用相同前件，第二真陈述依赖第一句也不得因组嵌套省掉。
反之同一组内容选不同组件为anchor不自动证明两次断言；逐anchor保留提案供独立复核。
本阶段不写fact status或proof_paths。合同规定程序按全部窗口的原始裁定组装：任一supported
产生support_proposed，有unknown而无supported则unresolved，全unsupported才not_found；
路径只从这些请求提案边按query完整枚举。程序不会替你改变单个anchor判决或添加支持。
输出原contract_version/window_id/window_digest和给定schema。"""

GROUP_REVIEW_SCHEMA = previous._object({"contract_version": {"enum": [REVIEW_VERSION]},
    "review_id": _S, "group_review_digest": _S,
    "support_verdict": {"enum": ["supported", "unsupported", "unknown"]},
    "subject_verdict": {"enum": ["self_contained", "missing", "unknown"]},
    "role_verdict": {"enum": ["matched", "mismatched", "unknown"]},
    "scope_verdict": {"enum": ["in_scope", "out_of_scope", "unknown"]},
    "anchor_verdict": {"enum": ["assertion_completion", "not_assertion_completion", "unknown"]},
    "reason": _S})

GROUP_REVIEW_PROMPT = """独立审核唯一目标fact与本次anchor。只看group_units实际原引文，不借全文、
其他组、提案reason、别称表中的关系描述或标准答案。child_surface是子辈，parent_surface
是所问父母辈；role_definition明确child→parent方向。分别审关系、主体、父母角色与scope。
本anchor须完成一处可区分的目标关系断言：单纯背景、主体介绍、关系组件或问句不是另一次。
若“甲生了两个儿子：”后接“长子乙”，目标child=乙,parent=甲,role=parent（乙→甲），
完成anchor在后者，不能凭儿子性别确定甲的父/母角色；若问句后答“甲”，
答案可作完成anchor，但组内必须有问题/说话人/指代前件。允许正常倒装、问答和跨原文合取，
普通“编号父17的人名叫甲”只作身份lookup前件；关系档案“乙的父亲=父17”的完成unit
才是本次亲属断言anchor，不能把名字映射再计一次。问答的直接亲属答语与普通lookup要区分。
同一姓名或父母角色不能仅凭目标claim得出。组内每个surface定位存在不等于其语义成立。
允许共享前件和嵌套原文；只因组包含另一组不能拒绝真实第二陈述，也不能用不同组件冒充重复。
scope按组内原文语义判断，不要求标签字面相等；说话人、否定、梦境、时间限定若关键却未引，
应missing/unknown/out_of_scope，不要组外补足。普通姓名不能证明父亲性别；有女只确定parent。
逐维supported/unsupported/unknown等如schema输出；保留unknown，不修复、补引、删组或写路径。
返回原contract_version/review_id/group_review_digest并说明本组实际quote。"""


class OccurrenceContractError(canonical.InventoryContractError):
    """A window, source binding, assembly or isolated review is invalid."""


def _require(condition, message):
    if not condition:
        raise OccurrenceContractError(message)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _schema(value, schema, label):
    try:
        jsonschema.validate(value, schema)
    except jsonschema.ValidationError as exc:
        raise OccurrenceContractError(label + ": " + exc.message) from exc


def _display_surface(entity_id, names, forms, visible):
    """Display only a pure identity actually present in the selected source text."""
    candidates = [s for s in forms[entity_id] if any(s in quote for quote in visible)]
    preferred = names[entity_id]
    return preferred if preferred in candidates else sorted(candidates, key=lambda s: (-len(s), s))[0] if candidates else ""


def build_occurrence_requests(request, max_anchor_units=MAX_ANCHOR_UNITS):
    """One fact and at most eight disjoint anchors per independent model call."""
    canonical.validate_inventory_request(request)
    _require(type(max_anchor_units) is int and 1 <= max_anchor_units <= MAX_ANCHOR_UNITS,
             "anchor window size must be an integer from 1 to 8")
    units = previous.build_coverage_request(request)["unit_catalog"]
    names = {e["id"]: e["name"] for e in request["entity_bindings"]}
    forms = previous._identity_forms(request)
    visible = [u["quote"] for u in units]
    result = []
    for edge in request["requested_edges"]:
        for start in range(0, len(units), max_anchor_units):
            anchors = [u["unit_id"] for u in units[start:start + max_anchor_units]]
            window_id = "OW-" + _digest({"version": VERSION, "request": request["request_digest"],
                "fact_id": edge["fact_id"], "anchors": anchors})[:24]
            child_surface = _display_surface(edge["child"], names, forms, visible)
            parent_surface = _display_surface(edge["parent"], names, forms, visible)
            item = {"contract_version": VERSION, "canonical_request_digest": request["request_digest"],
                "window_id": window_id, "fact": copy.deepcopy(edge),
                "child_surface": child_surface, "parent_surface": parent_surface,
                "surface_resolution": {"child": "located" if child_surface else "unresolved",
                                       "parent": "located" if parent_surface else "unresolved"},
                "role_definition": _ROLE_DEFINITIONS[edge["parent_role"]],
                "identity_forms": [{"entity_id": eid, "surfaces": sorted(s for s in forms[eid]
                    if any(s in quote for quote in visible))} for eid in (edge["child"], edge["parent"])],
                "source_units": copy.deepcopy(units), "anchor_unit_ids": anchors}
            item["window_digest"] = _digest(item)
            schema = copy.deepcopy(OCCURRENCE_SCHEMA)
            schema["properties"]["window_id"] = {"enum": [window_id]}
            schema["properties"]["window_digest"] = {"enum": [item["window_digest"]]}
            rows = schema["properties"]["occurrences"]
            rows.update(minItems=len(anchors), maxItems=len(anchors))
            rows["items"]["properties"]["anchor_unit_id"] = {"enum": anchors}
            result.append({"window_id": window_id, "input": item,
                           "output_schema": schema, "skill": OCCURRENCE_PROMPT})
    return result


def _validate_window(request):
    keys = {"contract_version", "canonical_request_digest", "window_id", "fact", "child_surface",
            "parent_surface", "surface_resolution", "role_definition", "identity_forms", "source_units", "anchor_unit_ids", "window_digest"}
    _require(isinstance(request, dict) and set(request) == keys and request["contract_version"] == VERSION,
             "window input fields/version invalid")
    _require(request["window_digest"] == _digest({k: v for k, v in request.items() if k != "window_digest"}),
             "window input digest invalid")
    units = {u["unit_id"]: u for u in request["source_units"]}
    _require(len(units) == len(request["source_units"]) and 1 <= len(request["anchor_unit_ids"]) <= 8
             and len(set(request["anchor_unit_ids"])) == len(request["anchor_unit_ids"])
             and set(request["anchor_unit_ids"]) <= set(units), "invalid source/anchor unit set")
    return units


def _validate_group(group, anchor_id, request, units):
    ids = group["unit_ids"]
    _require(set(ids) <= set(units) and anchor_id in ids, "support group uses foreign unit or omits its anchor")
    edge = request["fact"]
    endpoints = {edge["child"], edge["parent"]}
    _require({g["entity_id"] for g in group["endpoint_groundings"]} == endpoints,
             "support group must ground child and parent exactly once")
    forms = {e["entity_id"]: set(e["surfaces"]) for e in request["identity_forms"]}
    for grounding in group["endpoint_groundings"]:
        _require(grounding["unit_id"] in ids, "endpoint grounding outside its group")
        _require(grounding["surface"] in forms[grounding["entity_id"]] and
                 grounding["surface"] in units[grounding["unit_id"]]["quote"],
                 "endpoint surface is not an exact pure identity in its group")
    for name, basis in group["anchors"].items():
        _require(basis["unit_id"] in ids and basis["surface"].strip() and
                 basis["surface"] in units[basis["unit_id"]]["quote"],
                 name + " basis is not exact source text inside its group")
    # This does not infer a predicate, gender or scope from a marker. All five
    # bases and the completion anchor still need isolated semantic review.


def validate_occurrence_response(response, window_request):
    """Bind every raw decision to exactly one expected anchor; no repairs."""
    units = _validate_window(window_request)
    _schema(response, OCCURRENCE_SCHEMA, "occurrence response schema invalid")
    _require(response["window_id"] == window_request["window_id"] and
             response["window_digest"] == window_request["window_digest"], "response belongs to another window")
    rows = response["occurrences"]
    _require(len(rows) == len(window_request["anchor_unit_ids"]) and
             {r["anchor_unit_id"] for r in rows} == set(window_request["anchor_unit_ids"]),
             "every window anchor must be decided exactly once")
    for row in rows:
        _require((row["support_group"] is not None) == (row["verdict"] == "supported"),
                 "supported needs a group; unsupported/unknown must not smuggle a positive group")
        if row["support_group"] is not None:
            _validate_group(row["support_group"], row["anchor_unit_id"], window_request, units)
    return {"protocol_valid": True, "anchor_decisions": len(rows),
            "supported_proposals": sum(r["verdict"] == "supported" for r in rows),
            "unknown_decisions": sum(r["verdict"] == "unknown" for r in rows),
            "semantic_validity_established": False, "natural_text_coverage_established": False,
            "release_ready": False}


def assemble_inventory(request, window_responses, max_anchor_units=MAX_ANCHOR_UNITS):
    """Derive fact status and graph paths under the declared aggregation contract.

    Raw per-anchor decisions are never changed. Canonical identical citation
    sets share one representation, with every proposal retained in the ledger.
    Duplicate footprints are review flags, never counted proven occurrences.
    """
    envelopes = build_occurrence_requests(request, max_anchor_units)
    _require(isinstance(window_responses, list) and len(window_responses) == len(envelopes),
             "all fact/source windows must have one response")
    by_id = {}
    for response in window_responses:
        _require(isinstance(response, dict) and response.get("window_id") not in by_id,
                 "duplicate or invalid window response")
        by_id[response.get("window_id")] = response
    _require(set(by_id) == {e["window_id"] for e in envelopes}, "unknown/cross-request window response")
    units = {u["unit_id"]: u for u in previous.build_coverage_request(request)["unit_catalog"]}
    ledger = []
    for envelope in envelopes:
        window = envelope["input"]; response = by_id[envelope["window_id"]]
        validate_occurrence_response(response, window)
        rows = {r["anchor_unit_id"]: r for r in response["occurrences"]}
        for anchor in window["anchor_unit_ids"]:
            row = copy.deepcopy(rows[anchor])
            row.update(fact_id=window["fact"]["fact_id"], window_id=window["window_id"],
                       canonical_group_index=None, duplicate_footprint_review_required=False)
            ledger.append(row)
    facts, duplicates = [], []
    for edge in request["requested_edges"]:
        rows = [r for r in ledger if r["fact_id"] == edge["fact_id"]]
        positives = [r for r in rows if r["verdict"] == "supported"]
        groups, footprints = [], {}
        for row in positives:
            group = row["support_group"]
            footprint = tuple(sorted(group["unit_ids"]))
            if footprint not in footprints:
                footprints[footprint] = {"index": len(groups), "rows": []}
                groups.append([{k: units[uid][k] for k in ("context_id", "start", "end", "quote")}
                               for uid in group["unit_ids"]])
            item = footprints[footprint]
            row["canonical_group_index"] = item["index"]; item["rows"].append(row)
        for footprint, item in footprints.items():
            if len(item["rows"]) > 1:
                for row in item["rows"]:
                    row["duplicate_footprint_review_required"] = True
                duplicates.append({"fact_id": edge["fact_id"], "canonical_group_index": item["index"],
                    "anchor_unit_ids": [r["anchor_unit_id"] for r in item["rows"]], "unit_ids": list(footprint)})
        status = "support_proposed" if positives else "unresolved" if any(
            r["verdict"] == "unknown" for r in rows) else "not_found"
        facts.append({"fact_id": edge["fact_id"], "status": status, "support_groups": groups,
                      "reason": "按冻结逐anchor原始裁定的公开聚合规则派生；不构成独立语义验收。"})
    active = {f["fact_id"] for f in facts if f["status"] == "support_proposed"}
    inventory = {"contract_version": canonical.VERSION, "request_digest": request["request_digest"],
        "facts": facts, "proof_paths": canonical._enumerate_paths(request, active),
        "reason": "facts与proof_paths依逐位置提案合同确定性派生，非LLM提交的路径也非自然文本穷尽证明。"}
    report = canonical.validate_inventory(inventory, request)
    report.update(contract_version=VERSION, coverage_cells_expected=len(units) * len(request["requested_edges"]),
        coverage_cells_registered=len(ledger), positive_occurrence_proposals=sum(r["verdict"] == "supported" for r in ledger),
        unknown_occurrences=sum(r["verdict"] == "unknown" for r in ledger),
        canonical_unique_group_representations=sum(len(f["support_groups"]) for f in facts),
        duplicate_footprint_proposals=duplicates, distinct_support_occurrences_established=False,
        fact_status_and_paths_are="derived_from_all_raw_occurrence_proposals_under_explicit_contract",
        independent_source_coverage_review_required=True)
    assembly = {"contract_version": VERSION, "canonical_request": copy.deepcopy(request),
        "max_anchor_units": max_anchor_units, "window_responses": copy.deepcopy(window_responses),
        "occurrence_ledger": ledger, "inventory": inventory, "report": report}
    assembly["assembly_digest"] = _digest(assembly)
    return assembly


def _validated_assembly(assembly):
    _require(isinstance(assembly, dict) and assembly.get("contract_version") == VERSION,
             "invalid assembly version")
    actual = assemble_inventory(assembly["canonical_request"], assembly["window_responses"], assembly["max_anchor_units"])
    _require(actual == assembly, "assembly was changed after raw occurrence decisions")
    return assembly["canonical_request"]


def build_group_review_requests(assembly):
    """One isolated review per positive anchor, including duplicate footprints."""
    request = _validated_assembly(assembly)
    units = {u["unit_id"]: u for u in previous.build_coverage_request(request)["unit_catalog"]}
    edges = {e["fact_id"]: e for e in request["requested_edges"]}
    names = {e["id"]: e["name"] for e in request["entity_bindings"]}
    forms = previous._identity_forms(request)
    result = []
    for row in assembly["occurrence_ledger"]:
        if row["verdict"] != "supported":
            continue
        edge, group = edges[row["fact_id"]], row["support_group"]
        selected = [copy.deepcopy(units[uid]) for uid in group["unit_ids"]]
        visible = [u["quote"] for u in selected]
        child_surface = _display_surface(edge["child"], names, forms, visible)
        parent_surface = _display_surface(edge["parent"], names, forms, visible)
        _require(bool(child_surface) and bool(parent_surface), "positive group lacks a visible pure endpoint display")
        # Free reasons are neither visible nor included in opaque request IDs.
        core = {"request_digest": request["request_digest"], "fact_id": row["fact_id"],
                "anchor_unit_id": row["anchor_unit_id"],
                **{k: group[k] for k in ("unit_ids", "endpoint_groundings", "anchors")}}
        review_id = "OR-" + _digest(core)[:24]
        item = {"contract_version": REVIEW_VERSION, "review_id": review_id,
            "fact": copy.deepcopy(edge), "child_surface": child_surface,
            "parent_surface": parent_surface, "role_definition": _ROLE_DEFINITIONS[edge["parent_role"]],
            "anchor_unit_id": row["anchor_unit_id"], "group_units": selected,
            "endpoint_groundings": copy.deepcopy(group["endpoint_groundings"]),
            "anchors": copy.deepcopy(group["anchors"]),
            "identity_forms": [{"entity_id": eid, "surfaces": sorted(s for s in forms[eid]
                if any(s in quote for quote in visible))} for eid in (edge["child"], edge["parent"])]}
        item["group_review_digest"] = _digest(item)
        schema = copy.deepcopy(GROUP_REVIEW_SCHEMA)
        schema["properties"]["review_id"] = {"enum": [review_id]}
        schema["properties"]["group_review_digest"] = {"enum": [item["group_review_digest"]]}
        result.append({"group_id": review_id, "input": item,
                       "output_schema": schema, "skill": GROUP_REVIEW_PROMPT})
    return result


def validate_group_reviews(assembly, reviews):
    """Keep all raw occurrence/review outcomes; never prune to manufacture success."""
    envelopes = build_group_review_requests(assembly)
    _require(isinstance(reviews, list) and len(reviews) == len(envelopes), "missing/extra positive occurrence review")
    by_id = {}
    for review in reviews:
        _require(isinstance(review, dict) and review.get("review_id") not in by_id, "duplicate/invalid occurrence review")
        by_id[review.get("review_id")] = review
    _require(set(by_id) == {e["group_id"] for e in envelopes}, "unknown/cross-assembly occurrence review")
    positive = [("support_verdict", "supported"), ("subject_verdict", "self_contained"),
                ("role_verdict", "matched"), ("scope_verdict", "in_scope"), ("anchor_verdict", "assertion_completion")]
    records, failed, unknown = [], False, bool(assembly["report"]["unknown_occurrences"])
    for envelope in envelopes:
        request, review = envelope["input"], by_id[envelope["group_id"]]
        _schema(review, GROUP_REVIEW_SCHEMA, "isolated occurrence review schema invalid")
        _require(review["group_review_digest"] == request["group_review_digest"], "review belongs to another occurrence")
        passed = all(review[k] == v for k, v in positive)
        failed |= any(review[k] not in (v, "unknown") for k, v in positive)
        unknown |= any(review[k] == "unknown" for k, _ in positive)
        records.append({"request": request, "response": copy.deepcopy(review), "model_group_review_passed": passed})
    passed = bool(envelopes) and not failed and not unknown
    outcome = ("proposal_rejected" if failed else "needs_adjudication" if unknown else
               "no_positive_occurrences_requires_source_review" if not envelopes else "model_group_reviews_passed")
    return {"contract_version": VERSION, "outcome": outcome,
        "model_group_reviews_passed": passed, "unknown_observed": unknown,
        "no_positive_occurrences": not envelopes, "group_reviews": records,
        "occurrence_ledger": copy.deepcopy(assembly["occurrence_ledger"]),
        "inventory": copy.deepcopy(assembly["inventory"]),
        "duplicate_footprint_proposals": copy.deepcopy(assembly["report"]["duplicate_footprint_proposals"]),
        "distinct_support_occurrences_established": False,
        "independent_source_coverage_review_required": True,
        "semantic_validity_established": False, "natural_text_coverage_established": False,
        "release_ready": False}
