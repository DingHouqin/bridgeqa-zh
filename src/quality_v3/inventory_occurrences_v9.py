"""Flat occurrence selections with transparent exact-source materialization.

The semantic validator and isolated reviews are unchanged delegates from
[inventory_occurrences_v8.py](inventory_occurrences_v8.py). Opaque grounding
IDs select actual pure-name occurrences; they never establish a relation.
"""
from __future__ import annotations

import copy

import inventory_occurrences_v8 as CORE


VERSION = "support-occurrences-v0.9"
REVIEW_VERSION = CORE.REVIEW_VERSION
MAX_ANCHOR_UNITS = CORE.MAX_ANCHOR_UNITS
GROUP_REVIEW_SCHEMA = CORE.GROUP_REVIEW_SCHEMA
GROUP_REVIEW_PROMPT = CORE.GROUP_REVIEW_PROMPT
ANCHOR_KEYS = CORE.ANCHOR_KEYS
OccurrenceContractError = CORE.OccurrenceContractError
_require, _digest, _schema = CORE._require, CORE._digest, CORE._schema
_S = {"type": "string", "minLength": 1}
_NULL_ID = {"anyOf": [_S, {"type": "null"}]}
_UNIT_FIELDS = ("predicate_unit_id", "parent_role_unit_id", "scope_unit_id")
_SELECTION_FIELDS = ("child_grounding_id", "parent_grounding_id", *_UNIT_FIELDS)
_ROW = CORE.previous._object({"anchor_unit_id": _S,
    "verdict": {"enum": ["supported", "unsupported", "unknown"]},
    "group_unit_ids": {"type": "array", "items": _S, "uniqueItems": True},
    **{key: copy.deepcopy(_NULL_ID) for key in _SELECTION_FIELDS}, "reason": _S})
OCCURRENCE_SCHEMA = CORE.previous._object({"contract_version": {"enum": [VERSION]},
    "window_id": _S, "window_digest": _S,
    "occurrences": {"type": "array", "items": _ROW}})

OCCURRENCE_PROMPT = """按当前窗口逐anchor检查唯一目标fact，全部anchor各输出一行，不得找到第一处就停止。
child_surface是子辈，parent_surface是所问父母辈；方向按role_definition，不能用作品记忆、
姓名、身份表或目标claim补关系/性别。展示surface为空或surface_resolution=unresolved时，
不能从ID猜姓名；无法裁定用unknown，不能把未知当无支持。
每行只输出schema的平坦字段：anchor_unit_id,verdict,group_unit_ids,child_grounding_id,
parent_grounding_id,predicate_unit_id,parent_role_unit_id,scope_unit_id,reason。
verdict为supported/unsupported/unknown。supported要选非空group_unit_ids，含本anchor与
全部必要原文前件；child_grounding_id和parent_grounding_id从grounding_catalog选择，必须
分别属于本fact的child和parent且其unit在本组；三项predicate/parent_role/scope_unit_id
选本组实际提供该语义的原unit。不要抄surface、编偏移或嵌套support_group。
unsupported和unknown必须group_unit_ids=[]，其余五个选择字段全部null。unknown不能补姓名。
grounding_catalog仅是原文纯身份的实际位置目录，不能由目录条目推出亲属关系。程序会把所选
grounding ID展开为该位置的精确纯surface，把三项unit ID展开成实际完整unit原文；这些是
透明定位转换，不表示语义已经成立，仍须另一个只看到本组的模型逐维复核。
核心问题是本unit是否完成一次可区分的目标亲属断言，而非贡献任意支持成分。
“甲生下乙，亲属身份是乙的母亲。”是一次逐步完成角色的陈述；仅生下片段不足以确定
mother时，以完成母亲角色的后片段作唯一anchor，不把前后组件同一footprint登记两次。
“甲生了两个儿子：”“长子乙，”对于child=乙,parent=甲,role=parent（乙→甲），
只以完成乙身份的后者作anchor，前者仅谓词组件。儿子的性别不证明甲是父或母。
问答中问题只是前件，直接亲属答语即使仅姓名也可完成断言；需同组引用实际问题、说话人
与所问主体。普通编号姓名lookup仅补身份，不是新亲属断言：“乙的父亲=父17”应以该关系
档案完成unit为anchor，“父17=甲”只作前件，不能另计一次；不要与直接亲属问答混同。
支持组必须含主体先行词、指代、编号映射、问答、说话人以及实际关键的否定/更正/梦境/
时间限定；不能reason补证。只有“父亲是甲”而没有乙，须把含乙的实际前件一起选入组。
更正/撤销中的“他的父亲应为甲”须同组保留实际命名child的原句与撤销/更正范围；
不能从fact或其他组取主体，也不能把未选的旧原句中的姓名伪定位到更正片段。
scope按原文语义匹配fact.scope，普通来源类别不要求原文逐字同标签；不能只因未出现
“合成户籍”等元数据字面就拒绝真实直陈句，关键范围限制仍须本组原文。
不同真重述各有完成anchor，允许共享相同主体前件，允许第二真陈述组包含第一组；不能
因嵌套省掉第二次。句/分句或同次问答组件不能重复计数。同组换不同anchor不自动证明重复。
每fact的全部窗口直到全文末尾都须逐格看原文；填满行数本身不证明尾部真重述已找到。
本阶段不写facts/status/proof_paths。程序只按全部原始裁定公开聚合，不修复或删除失败。
返回输入contract_version/window_id/window_digest原值；仅输出schema JSON。"""


def _grounding_catalog(window):
    """Enumerate each exact occurrence of a uniquely registered pure identity."""
    result = []
    for identity in window["identity_forms"]:
        entity_id = identity["entity_id"]
        for surface in identity["surfaces"]:
            _require(isinstance(surface, str) and bool(surface), "empty grounding identity")
            for unit in window["source_units"]:
                cursor = 0
                while True:
                    position = unit["quote"].find(surface, cursor)
                    if position < 0:
                        break
                    item = {"entity_id": entity_id, "unit_id": unit["unit_id"],
                        "surface": surface, "context_id": unit["context_id"],
                        "start": unit["start"] + position,
                        "end": unit["start"] + position + len(surface)}
                    item["grounding_id"] = "G-" + _digest({"contract_version": VERSION,
                        "canonical_request_digest": window["canonical_request_digest"], **item})[:24]
                    result.append(item)
                    cursor = position + 1
    return result


def _core_window(window):
    result = {k: copy.deepcopy(v) for k, v in window.items()
              if k not in ("grounding_catalog", "window_id", "window_digest")}
    result["contract_version"] = CORE.VERSION
    result["window_id"] = "OW-" + _digest({"version": CORE.VERSION,
        "request": result["canonical_request_digest"], "fact_id": result["fact"]["fact_id"],
        "anchors": result["anchor_unit_ids"]})[:24]
    result["window_digest"] = _digest(result)
    return result


def _response_schema(window):
    result = copy.deepcopy(OCCURRENCE_SCHEMA)
    properties = result["properties"]
    properties["window_id"] = {"enum": [window["window_id"]]}
    properties["window_digest"] = {"enum": [window["window_digest"]]}
    rows = properties["occurrences"]
    rows.update(minItems=len(window["anchor_unit_ids"]), maxItems=len(window["anchor_unit_ids"]))
    fields = rows["items"]["properties"]
    fields["anchor_unit_id"] = {"enum": window["anchor_unit_ids"]}
    unit_ids = [u["unit_id"] for u in window["source_units"]]
    fields["group_unit_ids"]["items"] = {"enum": unit_ids}
    for field in _UNIT_FIELDS:
        fields[field] = {"enum": [None, *unit_ids]}
    for role in ("child", "parent"):
        fields[role + "_grounding_id"] = {"enum": [None, *[g["grounding_id"]
            for g in window["grounding_catalog"] if g["entity_id"] == window["fact"][role]]]}
    return result


def build_occurrence_requests(request, max_anchor_units=MAX_ANCHOR_UNITS):
    """Build flat contracts from the unchanged trusted canonical partitions."""
    result = []
    for envelope in CORE.build_occurrence_requests(request, max_anchor_units):
        window = copy.deepcopy(envelope["input"])
        window.pop("window_digest")
        window["contract_version"] = VERSION
        window["window_id"] = "OW-" + _digest({"version": VERSION,
            "request": request["request_digest"], "fact_id": window["fact"]["fact_id"],
            "anchors": window["anchor_unit_ids"]})[:24]
        window["grounding_catalog"] = _grounding_catalog(window)
        window["window_digest"] = _digest(window)
        result.append({"window_id": window["window_id"], "input": window,
            "output_schema": _response_schema(window), "skill": OCCURRENCE_PROMPT})
    return result


def _validate_window(window):
    _require(isinstance(window, dict) and window.get("contract_version") == VERSION,
             "window input fields/version invalid")
    expected_keys = {"contract_version", "canonical_request_digest", "window_id", "fact", "child_surface",
        "parent_surface", "surface_resolution", "role_definition", "identity_forms", "source_units",
        "anchor_unit_ids", "window_digest", "grounding_catalog"}
    _require(set(window) == expected_keys, "window input fields/version invalid")
    _require(window["window_digest"] == _digest({k: v for k, v in window.items() if k != "window_digest"}),
             "window input digest invalid")
    core = _core_window(window)
    units = CORE._validate_window(core)
    expected_id = "OW-" + _digest({"version": VERSION, "request": window["canonical_request_digest"],
        "fact_id": window["fact"]["fact_id"], "anchors": window["anchor_unit_ids"]})[:24]
    _require(window["window_id"] == expected_id, "window ID binding invalid")
    _require(window["grounding_catalog"] == _grounding_catalog(window),
             "grounding catalog differs from exact source identity occurrences")
    _require(len({g["grounding_id"] for g in window["grounding_catalog"]}) == len(window["grounding_catalog"]),
             "duplicate grounding catalog ID")
    return core, units


def _materialize(response, window):
    core, units = _validate_window(window)
    _schema(response, _response_schema(window), "flat occurrence response schema invalid")
    _require(response["window_id"] == window["window_id"] and response["window_digest"] == window["window_digest"],
             "response belongs to another window")
    rows = response["occurrences"]
    _require(len(rows) == len(window["anchor_unit_ids"]) and
             {r["anchor_unit_id"] for r in rows} == set(window["anchor_unit_ids"]),
             "every window anchor must be decided exactly once")
    catalog = {g["grounding_id"]: g for g in window["grounding_catalog"]}
    converted = []
    for row in rows:
        group = None
        if row["verdict"] == "supported":
            ids = row["group_unit_ids"]
            _require(bool(ids) and row["anchor_unit_id"] in ids,
                     "supported group is empty or omits its anchor")
            _require(all(row[key] is not None for key in _SELECTION_FIELDS),
                     "supported row has null grounding or semantic unit selection")
            groundings = []
            for role in ("child", "parent"):
                grounding = catalog[row[role + "_grounding_id"]]
                _require(grounding["entity_id"] == window["fact"][role], "grounding has wrong child/parent identity")
                _require(grounding["unit_id"] in ids, "endpoint grounding outside its group")
                groundings.append({k: grounding[k] for k in ("entity_id", "unit_id", "surface")})
            anchors = {role: {"unit_id": grounding["unit_id"], "surface": grounding["surface"]}
                       for role, grounding in zip(("child", "parent"), groundings)}
            for key in ("predicate", "parent_role", "scope"):
                uid = row[key + "_unit_id"]
                _require(uid in ids, key + " unit outside its group")
                anchors[key] = {"unit_id": uid, "surface": units[uid]["quote"]}
            group = {"unit_ids": copy.deepcopy(ids), "endpoint_groundings": groundings,
                     "anchors": anchors, "reason": row["reason"]}
        else:
            _require(row["group_unit_ids"] == [] and all(row[key] is None for key in _SELECTION_FIELDS),
                     "unsupported/unknown must have empty group and null selections")
        converted.append({"anchor_unit_id": row["anchor_unit_id"], "verdict": row["verdict"],
                          "support_group": group, "reason": row["reason"]})
    result = {"contract_version": CORE.VERSION, "window_id": core["window_id"],
              "window_digest": core["window_digest"], "occurrences": converted}
    report = CORE.validate_occurrence_response(result, core)
    return result, report


def validate_occurrence_response(response, window_request):
    """Validate all flat selections, then validate their exact v8 expansion."""
    _, report = _materialize(response, window_request)
    report.update(contract_version=VERSION, program_materialized=True,
        materialization="selected_exact_pure_groundings_and_complete_source_units",
        independent_semantic_review_required=True)
    return report


def assemble_inventory(request, window_responses, max_anchor_units=MAX_ANCHOR_UNITS):
    """Regenerate trusted windows; preserve every flat response and expansion."""
    envelopes = build_occurrence_requests(request, max_anchor_units)
    _require(isinstance(window_responses, list) and len(window_responses) == len(envelopes),
             "all fact/source windows must have one response")
    by_id = {}
    for response in window_responses:
        _require(isinstance(response, dict) and response.get("window_id") not in by_id,
                 "duplicate or invalid window response")
        by_id[response.get("window_id")] = response
    _require(set(by_id) == {e["window_id"] for e in envelopes}, "unknown/cross-request window response")
    converted = [_materialize(by_id[e["window_id"]], e["input"])[0] for e in envelopes]
    core = CORE.assemble_inventory(request, converted, max_anchor_units)
    report = copy.deepcopy(core["report"])
    report.update(contract_version=VERSION, program_materialized=True,
        materialization="selected_exact_pure_groundings_and_complete_source_units",
        independent_semantic_review_required=True)
    result = {"contract_version": VERSION, "canonical_request": copy.deepcopy(request),
        "max_anchor_units": max_anchor_units, "window_responses": copy.deepcopy(window_responses),
        "converted_window_responses": converted, "core_assembly": core,
        "inventory": copy.deepcopy(core["inventory"]), "occurrence_ledger": copy.deepcopy(core["occurrence_ledger"]),
        "report": report}
    result["assembly_digest"] = _digest(result)
    return result


def _validated_assembly(assembly):
    _require(isinstance(assembly, dict) and assembly.get("contract_version") == VERSION,
             "invalid assembly version")
    expected = assemble_inventory(assembly["canonical_request"], assembly["window_responses"],
                                  assembly["max_anchor_units"])
    _require(expected == assembly, "assembly was changed after raw flat occurrence decisions")
    return assembly["core_assembly"]


def build_group_review_requests(assembly):
    """Delegate unchanged isolated reviews only after raw-envelope validation."""
    return CORE.build_group_review_requests(_validated_assembly(assembly))


def validate_group_reviews(assembly, reviews):
    """No positive proposal or review is dropped, repaired or called acceptance."""
    result = CORE.validate_group_reviews(_validated_assembly(assembly), reviews)
    result.update(contract_version=VERSION, program_materialized=True)
    return result
