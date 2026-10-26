"""Auditable source-unit coverage proposals, followed by isolated group review.

Preserves [support_contract.py](support_contract.py) and
[inventory_catalog.py](inventory_catalog.py). Coverage is an explicit model
claim, never a programmatic proof of natural-language completeness.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

import jsonschema

import inventory_catalog as catalog
import support_contract as canonical


VERSION = "support-inventory-coverage-v0.7"
REVIEW_VERSION = "support-group-review-v0.7"
UNIT_STATUSES = ("support_anchor", "support_context", "not_supporting", "unresolved")
_FIELDS = ("question", "query", "contexts", "requested_edges", "entity_bindings")
_REQUEST_KEYS = ("contract_version", "canonical_request_digest", *_FIELDS,
                 "unit_catalog", "coverage_digest")
_REVIEW_REQUEST_KEYS = ("contract_version", "review_id", "fact",
                        "anchor_unit_id", "group_units", "entity_groundings",
                        "identity_forms", "group_review_digest")
_RELATION_WORD = re.compile(r"父|母|爹|娘|爸|妈|爷|奶|祖|子|女|夫|妻|兄|弟|姐|妹|生|育|所出|所养|诞|后裔|后代")


class CoverageContractError(canonical.InventoryContractError):
    """An incomplete or incorrectly bound coverage/review protocol."""


def _require(condition, message):
    if not condition:
        raise CoverageContractError(message)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _object(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


_STRING = {"type": "string", "minLength": 1}
_ID_LIST = {"type": "array", "items": _STRING, "minItems": 1, "uniqueItems": True}
_GROUNDING = _object({"entity_id": _STRING, "unit_id": _STRING, "surface": _STRING})
_GROUP = _object({"group_id": _STRING, "anchor_unit_id": _STRING,
                  "unit_ids": _ID_LIST,
                  "entity_groundings": {"type": "array", "items": _GROUNDING,
                                        "minItems": 2, "maxItems": 2},
                  "reason": _STRING})
_FACT = _object({"fact_id": _STRING, "status": {"enum": list(canonical.STATUSES)},
    "unit_coverage": {"type": "array", "items": _object({"unit_id": _STRING,
        "status": {"enum": list(UNIT_STATUSES)}})},
    "support_groups": {"type": "array", "items": _GROUP}, "reason": _STRING})
COVERAGE_SCHEMA = _object({"contract_version": {"enum": [VERSION]},
    "canonical_request_digest": _STRING, "coverage_digest": _STRING,
    "facts": {"type": "array", "items": _FACT},
    "proof_paths": copy.deepcopy(canonical.INVENTORY_SCHEMA["properties"]["proof_paths"]),
    "reason": _STRING})

COVERAGE_PROMPT = """只按当前原文为每条 requested_edges 提交可审计支持登记，不用百科或候选理由补证。
输出输入的 contract_version、canonical_request_digest、coverage_digest 原值。
每个 fact_id 恰一次，status=support_proposed/not_found/unresolved；提案有非空 support_groups，
其余无组。每条边必须在 unit_coverage 中逐项列全 unit_catalog 的全部 unit_id（包括无关
单元），每项仅 {unit_id,status}，status 为 support_anchor/support_context/not_supporting/
unresolved。不能找到一处即停止搜索；逐一检查同段末尾、独立回函、表格和后段复述。
support_groups 每组含 group_id、anchor_unit_id、unit_ids、entity_groundings、reason。
unit_ids 是共同支持该边的全部原引文单元；anchor_unit_id 必须在组内，指向本次关系陈述
出现的位置，不能选纯姓名或仅叙事背景作 anchor。每边同一 anchor 只能有一个组，句级与
分句级不再分开登记。不同位置的同义重述分别登记；共享指代前件可以在多个组中复用，
不能因共享主体就漏掉第二次关系陈述。目录单元是不重叠原文分区，不要求独立来源。
entity_groundings 恰含该边 parent 和 child 各一项 {entity_id,unit_id,surface}，surface
必须是该实体已登记姓名或唯一别称，并确切出现在本组某条原引文内，不计算字符数。
只有“父亲是甲”而没有乙主体时，必须把含乙的原前件一起引用。同理编号、代词、
省略主语需要同组的原文身份映射/先行词，不能在reason里添加。原文不能确定则 unresolved。
每个已被某组用作 anchor 的单元分类为 support_anchor；其他组内单元 support_context；
未入任何组的单元为 not_supporting 或 unresolved。未决单元不能称覆盖完整。
组内须说明 child→parent 关系、父母角色、否定/梦境/范围；名字共现不构成关系。
proof_paths 原样提交 {fact_ids,entity_ids}，只用 support_proposed 的请求边，按 query.start、
query.steps child→parent 走完，并列全已登记图中的完整路径；逐步优先 scope_by_step，
否则用 query.scope。不要声称程序证明了全部自然文本语义或删除有效性。按给定schema输出。"""


GROUP_REVIEW_SCHEMA = _object({"contract_version": {"enum": [REVIEW_VERSION]},
    "review_id": _STRING, "group_review_digest": _STRING,
    "support_verdict": {"enum": ["supported", "unsupported", "unknown"]},
    "subject_verdict": {"enum": ["self_contained", "missing", "unknown"]},
    "scope_verdict": {"enum": ["in_scope", "out_of_scope", "unknown"]},
    "anchor_verdict": {"enum": ["relation_occurrence", "not_relation_occurrence", "unknown"]},
    "reason": _STRING})

GROUP_REVIEW_PROMPT = """独立审核唯一目标 fact 与本次 group_units 原引文。输入只含本组引文和纯身份
姓名映射，不含其余全文、其他支持组、提案reason或标准答案。映射仅可识别同一姓名，
不能补入父母关系、性别、指代、编号或未引用原文。逐字查本组是否能证明指定 child→parent、
parent_role 和 scope。省略主体或代词须有本组原文先行词；父亲/母亲不能由姓名猜性别。
surface字面出现仅说明定位，不能代替语义。anchor_unit_id 必须指向此边的关系陈述出现处，
不能用纯姓名/背景单元冒充第二处支持。上下文无法确定用 unknown；明确否定或角色错误
用 unsupported。分别提交 support_verdict、subject_verdict、scope_verdict、anchor_verdict，
reason 指明本组具体原文。输出输入的 contract_version、review_id、group_review_digest 原值。
禁止修复提案、补引文、删除失败组后声称成功。"""


def build_coverage_request(request):
    """Return a deterministic, nonoverlapping, exact partition of every source.

    Even whitespace is retained; empty contexts have no units. No sentence IDs
    are selectable, so a sentence and its clause cannot become two alternatives.
    Distinct occurrences of identical text remain distinct units.
    """
    canonical.validate_inventory_request(request)
    units = []
    for context in request["contexts"]:
        text = context["text"]
        for start, end in catalog._segments(text, catalog._CLAUSE_ENDS):
            occurrence = {"context_id": context["context_id"], "start": start,
                          "end": end, "quote": text[start:end]}
            uid = "U-" + _digest({"version": VERSION,
                "request_digest": request["request_digest"], **occurrence})[:20]
            units.append({"unit_id": uid, **occurrence})
    _require(len({u["unit_id"] for u in units}) == len(units), "unit ID collision")
    result = {"contract_version": VERSION, "canonical_request_digest": request["request_digest"],
              **{k: copy.deepcopy(request[k]) for k in _FIELDS}, "unit_catalog": units}
    result["coverage_digest"] = _digest(result)
    return result


def _canonical_request(coverage_request):
    _require(isinstance(coverage_request, dict) and set(coverage_request) == set(_REQUEST_KEYS),
             "coverage request fields invalid")
    request = {"contract_version": canonical.VERSION,
               "request_digest": coverage_request["canonical_request_digest"],
               **{k: copy.deepcopy(coverage_request[k]) for k in _FIELDS}}
    canonical.validate_inventory_request(request)
    _require(coverage_request == build_coverage_request(request),
             "coverage request is not the exact complete source partition")
    return request


def _schema(value, schema, where):
    try:
        jsonschema.validate(value, schema)
    except jsonschema.ValidationError as exc:
        raise CoverageContractError(where + " schema invalid: " + exc.message) from exc


def _identity_forms(request):
    owners = {}
    for entity in request["entity_bindings"]:
        for surface in [entity["name"], *entity["aliases"]]:
            owners.setdefault(surface, set()).add(entity["id"])
    result = {}
    for entity in request["entity_bindings"]:
        pure = set()
        for surface in [entity["name"], *entity["aliases"]]:
            relational = bool(re.search(r"(?:之|的).*(?:父|母|子|女|祖|兄|弟|姐|妹)", surface))
            # Do not mistake a predicate inside a different proper name (e.g.
            # 贾母) for a relation. Conversely, 乙父甲 need not contain 的/之.
            for other, ids in owners.items():
                if (other and entity["id"] not in ids and other in surface
                        and _RELATION_WORD.search(surface.replace(other, ""))):
                    relational = True
                    break
            if owners[surface] == {entity["id"]} and not relational:
                pure.add(surface)
        result[entity["id"]] = pure
    return result


def _materialize(response, coverage_request):
    request = _canonical_request(coverage_request)
    _schema(response, COVERAGE_SCHEMA, "coverage response")
    _require(response["canonical_request_digest"] == request["request_digest"] and
             response["coverage_digest"] == coverage_request["coverage_digest"],
             "response belongs to another request/partition")
    units = {u["unit_id"]: u for u in coverage_request["unit_catalog"]}
    edges = {e["fact_id"]: e for e in request["requested_edges"]}
    forms = _identity_forms(request)
    inventory = {"contract_version": canonical.VERSION, "request_digest": request["request_digest"],
                 "facts": [], "proof_paths": copy.deepcopy(response["proof_paths"]),
                 "reason": response["reason"]}
    unresolved_cells = []
    seen = set()
    for fact in response["facts"]:
        fid = fact["fact_id"]
        _require(fid in edges and fid not in seen, "unknown or duplicate fact ID")
        seen.add(fid)
        edge = edges[fid]
        coverage = fact["unit_coverage"]
        _require(len(coverage) == len(units) and
                 {c["unit_id"] for c in coverage} == set(units),
                 "every requested edge must classify every source unit exactly once")
        groups, group_ids, anchors, used, footprints = [], set(), set(), set(), []
        for group in fact["support_groups"]:
            gid, anchor, ids = group["group_id"], group["anchor_unit_id"], group["unit_ids"]
            _require(gid not in group_ids, "duplicate group ID within fact")
            group_ids.add(gid)
            _require(set(ids) <= set(units), "unknown or cross-request unit ID")
            _require(anchor in ids, "anchor is not in its own support group")
            _require(anchor not in anchors, "same relation anchor cannot count as two alternative groups")
            anchors.add(anchor)
            footprint = set(ids)
            # The canonical validator already rejects exactly equal citation
            # sets. Strict nesting can otherwise disguise the same occurrence
            # using an extra background/name unit as a new anchor. This is a
            # conservative representation limit, not a semantic claim that a
            # true second statement with a reused antecedent does not exist.
            _require(not any(footprint < prior or prior < footprint for prior in footprints),
                     "strictly nested alternative groups need independent occurrence adjudication")
            footprints.append(footprint)
            used.update(ids)
            groundings = group["entity_groundings"]
            _require({g["entity_id"] for g in groundings} == {edge["parent"], edge["child"]},
                     "each group must ground both endpoint entities exactly once")
            for grounding in groundings:
                uid, entity, surface = (grounding[k] for k in ("unit_id", "entity_id", "surface"))
                _require(uid in ids, "endpoint grounding is outside its own group")
                _require(surface in forms[entity], "endpoint surface is not a unique registered identity")
                _require(surface in units[uid]["quote"], "endpoint surface is absent from the cited group unit")
            groups.append([{k: units[uid][k] for k in ("context_id", "start", "end", "quote")}
                           for uid in ids])
        for cell in coverage:
            uid, status = cell["unit_id"], cell["status"]
            expected = "support_anchor" if uid in anchors else "support_context" if uid in used else None
            _require(status == expected if expected else status in ("not_supporting", "unresolved"),
                     "unit classification contradicts submitted group membership/anchor")
            if status == "unresolved":
                unresolved_cells.append({"fact_id": fid, "unit_id": uid})
        _require(fact["status"] != "not_found" or not any(c["status"] == "unresolved" for c in coverage),
                 "not_found cannot conceal unresolved source units")
        inventory["facts"].append({"fact_id": fid, "status": fact["status"],
                                  "support_groups": groups, "reason": fact["reason"]})
    canonical.validate_inventory(inventory, request)
    return request, inventory, unresolved_cells


def materialize_inventory(response, coverage_request):
    """Expand exactly proposed units; never invent, prune, merge or repair a group/path."""
    return _materialize(response, coverage_request)[1]


def validate_coverage(response, coverage_request):
    """Return structural coverage diagnostics without certifying model exclusions."""
    request, inventory, unresolved = _materialize(response, coverage_request)
    report = canonical.validate_inventory(inventory, request)
    report.update(contract_version=VERSION, coverage_protocol_valid=True,
        coverage_cells_expected=len(request["requested_edges"]) * len(coverage_request["unit_catalog"]),
        coverage_cells_registered=sum(len(f["unit_coverage"]) for f in response["facts"]),
        unresolved_source_units=unresolved,
        unique_relation_anchor_proposals=sum(len(f["support_groups"]) for f in response["facts"]),
        all_units_classified_without_unknown=not unresolved,
        natural_text_coverage_established=False, semantic_validity_established=False,
        semantic_review_required=True, release_ready=False,
        representation_limits=["Strictly nested alternative groups are rejected conservatively; this does not establish absence of a second natural-text support.",
            "A clause may contain multiple assertions; anchor selection and every not_supporting label need independent semantic review."])
    return report


def _group_review_inputs(response, coverage_request):
    """One independently callable request per group, containing only its source units.

    Full contexts, other groups/claims, extraction explanations and paths are
    deliberately absent. Pure identity forms never establish relation semantics.
    """
    request, _, _ = _materialize(response, coverage_request)
    units = {u["unit_id"]: u for u in coverage_request["unit_catalog"]}
    edges = {e["fact_id"]: e for e in request["requested_edges"]}
    forms = _identity_forms(request)
    reviews = []
    for fact in response["facts"]:
        edge = edges[fact["fact_id"]]
        for group in fact["support_groups"]:
            review_id = "GR-" + _digest({"coverage_digest": coverage_request["coverage_digest"],
                "fact_id": fact["fact_id"], "anchor_unit_id": group["anchor_unit_id"],
                "unit_ids": group["unit_ids"], "entity_groundings": group["entity_groundings"]})[:24]
            group_units = [copy.deepcopy(units[uid]) for uid in group["unit_ids"]]
            # Group IDs and extraction reasons are model-controlled strings;
            # neither is evidence. Neither even changes the opaque review ID.
            visible = [u["quote"] for u in group_units]
            item = {"contract_version": REVIEW_VERSION, "review_id": review_id,
                "fact": copy.deepcopy(edge), "anchor_unit_id": group["anchor_unit_id"],
                "group_units": group_units,
                "entity_groundings": copy.deepcopy(group["entity_groundings"]),
                "identity_forms": [{"entity_id": eid, "surfaces": sorted(
                    s for s in forms[eid] if any(s in q for q in visible))}
                                   for eid in (edge["child"], edge["parent"])]}
            item["group_review_digest"] = _digest(item)
            reviews.append(item)
    return reviews


def build_group_review_requests(response, coverage_request):
    """Return freezeable caller envelopes; group_id is the globally unique review ID."""
    return [{"group_id": r["review_id"], "input": r,
             "output_schema": copy.deepcopy(GROUP_REVIEW_SCHEMA), "skill": GROUP_REVIEW_PROMPT}
            for r in _group_review_inputs(response, coverage_request)]


def validate_group_review(response, review_request):
    """Validate a frozen isolated review response; unknown remains unknown."""
    _require(isinstance(review_request, dict) and set(review_request) == set(_REVIEW_REQUEST_KEYS) and
             review_request.get("contract_version") == REVIEW_VERSION and
             review_request.get("group_review_digest") == _digest(
                 {k: v for k, v in review_request.items() if k != "group_review_digest"}),
             "group review request binding invalid")
    _schema(response, GROUP_REVIEW_SCHEMA, "group review response")
    _require(response["review_id"] == review_request["review_id"] and
             response["group_review_digest"] == review_request["group_review_digest"],
             "group review belongs to another proposal")
    return {"protocol_valid": True,
        "model_group_review_passed": all(response[k] == v for k, v in (
            ("support_verdict", "supported"), ("subject_verdict", "self_contained"),
            ("scope_verdict", "in_scope"), ("anchor_verdict", "relation_occurrence"))),
        "semantic_validity_established": False, "release_ready": False}


def validate_group_reviews(response, coverage_request, group_reviews):
    """Preserve every review; never drop a failed/unknown proposal to claim success.

    A clean model review is only a model-review outcome. Independent full-source
    semantic coverage acceptance is still required, including all not_supporting
    labels and multi-claim clauses that a simple partition cannot disambiguate.
    """
    report = validate_coverage(response, coverage_request)
    requests = _group_review_inputs(response, coverage_request)
    identities = [{"fact_id": f["fact_id"], "group_id": g["group_id"]}
                  for f in response["facts"] for g in f["support_groups"]]
    _require(isinstance(group_reviews, list) and len(group_reviews) == len(requests),
             "missing or extra isolated group review")
    by_id = {}
    for review in group_reviews:
        _require(isinstance(review, dict) and review.get("review_id") not in by_id,
                 "duplicate or invalid group review")
        by_id[review.get("review_id")] = review
    _require(set(by_id) == {r["review_id"] for r in requests}, "unknown or cross-request group review")
    validations = [validate_group_review(by_id[r["review_id"]], r) for r in requests]
    rejected = any(review[k] in values for review in group_reviews for k, values in (
        ("support_verdict", ("unsupported",)), ("subject_verdict", ("missing",)),
        ("scope_verdict", ("out_of_scope",)), ("anchor_verdict", ("not_relation_occurrence",))))
    unresolved = bool(report["unresolved_source_units"]) or any(
        f["status"] == "unresolved" for f in response["facts"]) or any(
        not v["model_group_review_passed"] for v in validations)
    # With no group, positive-only reviews say nothing about negative coverage.
    passed = bool(requests) and not rejected and not unresolved
    outcome = "proposal_rejected" if rejected else "model_group_reviews_passed" if passed else "needs_adjudication"
    return {"contract_version": VERSION, "outcome": outcome,
        "model_group_reviews_passed": passed, "coverage_report": report,
        "inventory": materialize_inventory(response, coverage_request),
        "raw_coverage_proposal": copy.deepcopy(response),
        "group_reviews": [{"request": r, "proposal_identity": identity,
                           "response": copy.deepcopy(by_id[r["review_id"]]),
                           "validation": v} for r, v, identity in zip(requests, validations, identities)],
        "independent_source_coverage_review_required": True,
        "semantic_validity_established": False, "natural_text_coverage_established": False,
        "release_ready": False}
