"""Occurrence coverage and isolated review controls; no model calls.

The contract under test is [inventory_coverage.py](inventory_coverage.py).
These tests deliberately keep semantic counterexamples structurally possible:
model exclusions and entailment still need independent source review.
"""
import copy
import json
import unittest

import inventory_coverage as coverage
import support_contract as canonical


def make_request(texts=None, aliases=None):
    return canonical.make_inventory_request("宁珩母亲的父亲是谁？",
        {"operation": "parent_chain", "start": "N", "steps": ["mother", "father"], "scope": "合成户籍"},
        texts or [{"context_id": "A", "text": "宁珩的母亲是许蘅。家谱末尾又记：许蘅生下宁珩。"},
                  {"context_id": "B", "text": "许蘅的父亲是沈澄。"}],
        [{"fact_id": "M", "parent": "X", "child": "N", "parent_role": "mother", "scope": "合成户籍"},
         {"fact_id": "F", "parent": "S", "child": "X", "parent_role": "father", "scope": "合成户籍"}],
        [{"id": "N", "name": "宁珩", "aliases": aliases or []},
         {"id": "X", "name": "许蘅", "aliases": []},
         {"id": "S", "name": "沈澄", "aliases": []}])


def unit(request, quote, occurrence=0):
    return [u for u in request["unit_catalog"] if u["quote"] == quote][occurrence]


def group(request, gid, anchor, quotes, grounds):
    return {"group_id": gid, "anchor_unit_id": unit(request, anchor)["unit_id"],
        "unit_ids": [unit(request, q)["unit_id"] for q in quotes],
        "entity_groundings": [{"entity_id": eid, "unit_id": unit(request, q)["unit_id"], "surface": surface}
                              for eid, q, surface in grounds], "reason": "仅按组内原引文提出支持。"}


def relabel(response, request):
    for fact in response["facts"]:
        anchors = {g["anchor_unit_id"] for g in fact["support_groups"]}
        used = {uid for g in fact["support_groups"] for uid in g["unit_ids"]}
        fact["unit_coverage"] = [{"unit_id": u["unit_id"],
            "status": "support_anchor" if u["unit_id"] in anchors else
                      "support_context" if u["unit_id"] in used else "not_supporting"}
            for u in request["unit_catalog"]]


def fixture():
    source = make_request()
    request = coverage.build_coverage_request(source)
    first, tail, father = "宁珩的母亲是许蘅。", "许蘅生下宁珩。", "许蘅的父亲是沈澄。"
    response = {"contract_version": coverage.VERSION,
        "canonical_request_digest": request["canonical_request_digest"],
        "coverage_digest": request["coverage_digest"],
        "facts": [{"fact_id": "M", "status": "support_proposed", "support_groups": [
            group(request, "m0", first, [first], [("N", first, "宁珩"), ("X", first, "许蘅")]),
            group(request, "m1", tail, [tail], [("N", tail, "宁珩"), ("X", tail, "许蘅")])], "reason": "列两处母亲重述。"},
            {"fact_id": "F", "status": "support_proposed", "support_groups": [
            group(request, "f0", father, [father], [("X", father, "许蘅"), ("S", father, "沈澄")])], "reason": "父亲直接句。"}],
        "proof_paths": [{"fact_ids": ["M", "F"], "entity_ids": ["N", "X", "S"]}], "reason": "原样登记。"}
    relabel(response, request)
    return source, request, response


def successful_reviews(response, request):
    return [{"contract_version": coverage.REVIEW_VERSION, "review_id": r["input"]["review_id"],
        "group_review_digest": r["input"]["group_review_digest"], "support_verdict": "supported",
        "subject_verdict": "self_contained", "scope_verdict": "in_scope",
        "anchor_verdict": "relation_occurrence", "reason": "本组原文支持指定关系。"}
        for r in coverage.build_group_review_requests(response, request)]


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.source, self.request, self.response = fixture()

    def test_exact_nonoverlapping_partition_including_dialogue_crlf_unicode_and_spaces(self):
        source = make_request([{"context_id": "T", "text": '📚问：“宁珩，谁是母亲？”\r\n答：许蘅；尾注  '},
                               {"context_id": "E", "text": ""}, {"context_id": "W", "text": " \t "}])
        request = coverage.build_coverage_request(source)
        for context in source["contexts"]:
            pieces = [u for u in request["unit_catalog"] if u["context_id"] == context["context_id"]]
            self.assertEqual("".join(u["quote"] for u in pieces), context["text"])
            cursor = 0
            for piece in pieces:
                self.assertEqual(piece["start"], cursor)
                self.assertEqual(context["text"][cursor:piece["end"]], piece["quote"])
                cursor = piece["end"]
            self.assertEqual(cursor, len(context["text"]))

    def test_only_clause_units_no_sentence_overlay(self):
        quotes = [u["quote"] for u in self.request["unit_catalog"]]
        self.assertIn("家谱末尾又记：", quotes)
        self.assertIn("许蘅生下宁珩。", quotes)
        self.assertNotIn("家谱末尾又记：许蘅生下宁珩。", quotes)

    def test_repeated_identical_text_keeps_distinct_occurrences(self):
        source = make_request([{"context_id": "T", "text": "宁珩的母亲是许蘅。宁珩的母亲是许蘅。"}])
        units = coverage.build_coverage_request(source)["unit_catalog"]
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0]["quote"], units[1]["quote"])
        self.assertNotEqual(units[0]["unit_id"], units[1]["unit_id"])

    def test_full_request_binds_units_and_builder_does_not_mutate(self):
        original = copy.deepcopy(self.source)
        self.assertEqual(self.request, coverage.build_coverage_request(self.source))
        changed = copy.deepcopy(self.source); changed["question"] += "另问"
        changed["request_digest"] = canonical._request_digest(changed)
        other = coverage.build_coverage_request(changed)
        self.assertTrue({u["unit_id"] for u in other["unit_catalog"]}.isdisjoint(
                        u["unit_id"] for u in self.request["unit_catalog"]))
        self.assertEqual(original, self.source)

    def test_materializes_exact_proposed_groups_reasons_order_and_paths(self):
        original = copy.deepcopy(self.response)
        actual = coverage.materialize_inventory(self.response, self.request)
        self.assertEqual(actual["proof_paths"], self.response["proof_paths"])
        self.assertEqual(actual["reason"], self.response["reason"])
        self.assertEqual([g[0]["quote"] for g in actual["facts"][0]["support_groups"]],
                         ["宁珩的母亲是许蘅。", "许蘅生下宁珩。"])
        self.assertEqual(original, self.response)
        self.assertEqual(actual["facts"][0]["reason"], self.response["facts"][0]["reason"])

    def test_every_edge_must_classify_all_units_including_irrelevant_text(self):
        for change in (lambda rows: rows.pop(), lambda rows: rows.append(copy.deepcopy(rows[0])),
                       lambda rows: rows.__setitem__(1, copy.deepcopy(rows[0]))):
            response = copy.deepcopy(self.response); change(response["facts"][0]["unit_coverage"])
            with self.subTest(change=change), self.assertRaisesRegex(coverage.CoverageContractError, "every source unit"):
                coverage.validate_coverage(response, self.request)

    def test_unknown_and_foreign_unit_ids_cannot_be_selected(self):
        for uid in ("U-fake", "SP-old-sentence-id"):
            response = copy.deepcopy(self.response)
            response["facts"][0]["support_groups"][0]["unit_ids"][0] = uid
            with self.subTest(uid=uid), self.assertRaisesRegex(coverage.CoverageContractError, "unknown or cross-request"):
                coverage.materialize_inventory(response, self.request)

    def test_tampered_partition_even_with_recomputed_digest_is_rejected(self):
        request = copy.deepcopy(self.request); request["unit_catalog"].pop()
        request["coverage_digest"] = coverage._digest({k: v for k, v in request.items() if k != "coverage_digest"})
        with self.assertRaisesRegex(coverage.CoverageContractError, "exact complete"):
            coverage.materialize_inventory(self.response, request)

    def test_unknown_request_binding_is_rejected(self):
        for key in ("canonical_request_digest", "coverage_digest"):
            response = copy.deepcopy(self.response); response[key] = "0" * 64
            with self.subTest(key=key), self.assertRaisesRegex(coverage.CoverageContractError, "another request"):
                coverage.materialize_inventory(response, self.request)

    def test_same_anchor_cannot_be_repackaged_as_second_alternative(self):
        response = copy.deepcopy(self.response)
        duplicate = copy.deepcopy(response["facts"][0]["support_groups"][0]); duplicate["group_id"] = "m2"
        duplicate["unit_ids"].append(unit(self.request, "家谱末尾又记：")["unit_id"])
        response["facts"][0]["support_groups"].append(duplicate)
        relabel(response, self.request)
        with self.assertRaisesRegex(coverage.CoverageContractError, "same relation anchor"):
            coverage.materialize_inventory(response, self.request)

    def test_nested_group_with_extra_background_anchor_is_not_a_second_support(self):
        response = copy.deepcopy(self.response)
        duplicate = copy.deepcopy(response["facts"][0]["support_groups"][0])
        duplicate.update(group_id="m2", anchor_unit_id=unit(self.request, "家谱末尾又记：")["unit_id"])
        duplicate["unit_ids"].append(duplicate["anchor_unit_id"])
        response["facts"][0]["support_groups"].append(duplicate)
        relabel(response, self.request)
        with self.assertRaisesRegex(coverage.CoverageContractError, "strictly nested"):
            coverage.materialize_inventory(response, self.request)

    def test_equal_groups_with_distinct_anchors_already_fail_canonical_duplicate_guard(self):
        response = copy.deepcopy(self.response)
        groups = response["facts"][0]["support_groups"]
        groups[0]["unit_ids"].append(unit(self.request, "家谱末尾又记：")["unit_id"])
        duplicate = copy.deepcopy(groups[0]); duplicate.update(group_id="m2",
            anchor_unit_id=unit(self.request, "家谱末尾又记：")["unit_id"])
        groups.append(duplicate); relabel(response, self.request)
        with self.assertRaisesRegex(canonical.InventoryContractError, "duplicate support group"):
            coverage.materialize_inventory(response, self.request)

    def test_true_nested_restatement_is_a_declared_conservative_representation_limit(self):
        response = copy.deepcopy(self.response)
        first, repeated = response["facts"][0]["support_groups"]
        repeated["unit_ids"].extend(first["unit_ids"])
        relabel(response, self.request)
        with self.assertRaisesRegex(coverage.CoverageContractError, "independent occurrence adjudication"):
            coverage.materialize_inventory(response, self.request)
        clean_report = coverage.validate_coverage(self.response, self.request)
        self.assertTrue(any("does not establish absence" in s for s in clean_report["representation_limits"]))

    def test_distinct_claim_anchors_can_share_original_subject_antecedent(self):
        source = make_request([{"context_id": "A", "text": "宁珩见许蘅，她是宁珩的母亲，又生下宁珩。"},
                               {"context_id": "B", "text": "许蘅的父亲是沈澄。"}])
        request = coverage.build_coverage_request(source)
        response = copy.deepcopy(self.response)
        response.update(canonical_request_digest=request["canonical_request_digest"], coverage_digest=request["coverage_digest"])
        response["facts"][0]["support_groups"] = [group(request, gid, anchor, ["宁珩见许蘅，", anchor],
            [("N", "宁珩见许蘅，", "宁珩"), ("X", "宁珩见许蘅，", "许蘅")])
            for gid, anchor in (("m0", "她是宁珩的母亲，"), ("m1", "又生下宁珩。"))]
        father = "许蘅的父亲是沈澄。"
        response["facts"][1]["support_groups"] = [group(request, "f", father, [father],
            [("X", father, "许蘅"), ("S", father, "沈澄")])]
        relabel(response, request)
        actual = coverage.materialize_inventory(response, request)
        self.assertEqual(len(actual["facts"][0]["support_groups"]), 2)
        self.assertEqual(coverage.validate_coverage(response, request)["unique_relation_anchor_proposals"], 3)

    def test_bare_father_clause_cannot_borrow_subject_from_other_group_or_reason(self):
        source = make_request([{"context_id": "A", "text": "宁珩的母亲是许蘅。许蘅见宁珩，父亲是沈澄。"}])
        request = coverage.build_coverage_request(source)
        response = copy.deepcopy(self.response)
        response.update(canonical_request_digest=request["canonical_request_digest"], coverage_digest=request["coverage_digest"])
        first = "宁珩的母亲是许蘅。"
        response["facts"][0]["support_groups"] = [group(request, "m", first, [first],
            [("N", first, "宁珩"), ("X", first, "许蘅")])]
        response["facts"][1]["support_groups"] = [group(request, "f", "父亲是沈澄。", ["父亲是沈澄。"],
            [("X", "父亲是沈澄。", "许蘅"), ("S", "父亲是沈澄。", "沈澄")])]
        response["facts"][1]["reason"] = "许蘅是主体，全文和别组都出现过。"
        relabel(response, request)
        with self.assertRaisesRegex(coverage.CoverageContractError, "surface is absent"):
            coverage.materialize_inventory(response, request)

    def test_grounding_must_point_inside_same_group_not_outside_antecedent(self):
        grounding = self.response["facts"][0]["support_groups"][0]["entity_groundings"][0]
        grounding["unit_id"] = unit(self.request, "许蘅生下宁珩。")["unit_id"]
        with self.assertRaisesRegex(coverage.CoverageContractError, "outside its own group"):
            coverage.materialize_inventory(self.response, self.request)

    def test_missing_or_wrong_endpoint_groundings_are_rejected(self):
        for entity in ("S", "X"):
            response = copy.deepcopy(self.response)
            response["facts"][0]["support_groups"][0]["entity_groundings"][0]["entity_id"] = entity
            with self.subTest(entity=entity), self.assertRaisesRegex(coverage.CoverageContractError, "both endpoint"):
                coverage.materialize_inventory(response, self.request)

    def test_unregistered_surface_and_shared_alias_are_not_pure_identity_grounding(self):
        for surface in ("她", "母亲"):
            response = copy.deepcopy(self.response)
            response["facts"][0]["support_groups"][0]["entity_groundings"][0]["surface"] = surface
            with self.subTest(surface=surface), self.assertRaisesRegex(coverage.CoverageContractError, "unique registered identity"):
                coverage.materialize_inventory(response, self.request)
        source = copy.deepcopy(self.source)
        source["entity_bindings"][0]["aliases"] = ["同名"]
        source["entity_bindings"][1]["aliases"] = ["同名"]
        source["request_digest"] = canonical._request_digest(source)
        self.assertNotIn("同名", coverage._identity_forms(source)["N"])

    def test_unique_alias_is_grounded_exactly_and_becomes_invalid_when_shared(self):
        source = make_request([{"context_id": "A", "text": "小宁的母亲是许蘅。"},
                               {"context_id": "B", "text": "许蘅的父亲是沈澄。"}], aliases=["小宁"])
        request = coverage.build_coverage_request(source)
        response = copy.deepcopy(self.response)
        response.update(canonical_request_digest=request["canonical_request_digest"], coverage_digest=request["coverage_digest"])
        first, father = "小宁的母亲是许蘅。", "许蘅的父亲是沈澄。"
        response["facts"][0]["support_groups"] = [group(request, "m", first, [first],
            [("N", first, "小宁"), ("X", first, "许蘅")])]
        response["facts"][1]["support_groups"] = [group(request, "f", father, [father],
            [("X", father, "许蘅"), ("S", father, "沈澄")])]
        relabel(response, request)
        self.assertTrue(coverage.validate_coverage(response, request)["protocol_valid"])
        source["entity_bindings"][1]["aliases"].append("小宁")
        source["request_digest"] = canonical._request_digest(source)
        other = coverage.build_coverage_request(source)
        response.update(canonical_request_digest=other["canonical_request_digest"], coverage_digest=other["coverage_digest"])
        response["facts"][0]["support_groups"] = [group(other, "m", first, [first],
            [("N", first, "小宁"), ("X", first, "许蘅")])]
        response["facts"][1]["support_groups"] = [group(other, "f", father, [father],
            [("X", father, "许蘅"), ("S", father, "沈澄")])]
        relabel(response, other)
        with self.assertRaisesRegex(coverage.CoverageContractError, "unique registered identity"):
            coverage.materialize_inventory(response, other)

    def test_relation_bearing_alias_without_particles_is_filtered_but_proper_name_mother_is_kept(self):
        source = canonical.make_inventory_request("乙的父亲是谁？",
            {"operation": "parents", "start": "B", "steps": ["father"], "scope": "登记"},
            [{"context_id": "T", "text": "乙父甲。甲、乙和母辰同处一页。"}],
            [{"fact_id": "AB", "parent": "A", "child": "B", "parent_role": "father", "scope": "登记"}],
            [{"id": "A", "name": "甲", "aliases": ["乙父甲", "乙之父甲", "乙所出甲", "乙育有甲",
                                                       "乙生了甲", "乙养育甲"]},
             {"id": "B", "name": "乙", "aliases": []},
             {"id": "C", "name": "母辰", "aliases": ["母辰先生"]}])
        forms = coverage._identity_forms(source)
        self.assertEqual(forms["A"], {"甲"})
        self.assertEqual(forms["C"], {"母辰", "母辰先生"})
        # Predicate characters occurring only inside another proper name do
        # not turn a conventional identity extension into a relation claim.
        source["entity_bindings"][0]["aliases"].append("母辰甲")
        self.assertIn("母辰甲", coverage._identity_forms(source)["A"])

    def test_modern_birth_and_upbringing_descriptions_are_not_identity_forms(self):
        source = copy.deepcopy(self.source)
        source["entity_bindings"][0]["aliases"] = ["许蘅生了宁珩", "许蘅养育宁珩"]
        self.assertEqual(coverage._identity_forms(source)["N"], {"宁珩"})

    def test_cross_context_numbered_identity_is_in_same_conjunctive_group(self):
        source = make_request([{"context_id": "A", "text": "宁珩的母亲是许蘅。"},
            {"context_id": "B", "text": "许蘅的父亲，正是账册里编号为父17的那个人。"},
            {"context_id": "C", "text": "账册编号父17的人名叫沈澄。"}])
        request = coverage.build_coverage_request(source)
        response = copy.deepcopy(self.response)
        response.update(canonical_request_digest=request["canonical_request_digest"], coverage_digest=request["coverage_digest"])
        first = "宁珩的母亲是许蘅。"
        response["facts"][0]["support_groups"] = [group(request, "m", first, [first],
            [("N", first, "宁珩"), ("X", first, "许蘅")])]
        quoted = ["许蘅的父亲，", "正是账册里编号为父17的那个人。", "账册编号父17的人名叫沈澄。"]
        response["facts"][1]["support_groups"] = [group(request, "f", quoted[0], quoted,
            [("X", quoted[0], "许蘅"), ("S", quoted[2], "沈澄")])]
        relabel(response, request)
        actual = coverage.materialize_inventory(response, request)
        self.assertEqual(len(actual["facts"][1]["support_groups"]), 1)
        self.assertEqual(len(actual["facts"][1]["support_groups"][0]), 3)
        review = coverage.build_group_review_requests(response, request)[1]["input"]
        self.assertEqual([u["quote"] for u in review["group_units"]], quoted)
        response["facts"][1]["support_groups"][0]["unit_ids"].pop()
        relabel(response, request)
        with self.assertRaisesRegex(coverage.CoverageContractError, "outside its own group"):
            coverage.materialize_inventory(response, request)

    def test_duplicate_units_and_handwritten_locator_fields_are_not_silently_fixed(self):
        for change in (lambda g: g["unit_ids"].append(g["unit_ids"][0]),
                       lambda g: g.update(start=0), lambda g: g.update(quote="新添原文")):
            response = copy.deepcopy(self.response); change(response["facts"][0]["support_groups"][0])
            with self.subTest(change=change), self.assertRaisesRegex(coverage.CoverageContractError, "schema invalid"):
                coverage.materialize_inventory(response, self.request)

    def test_group_classification_cannot_claim_anchor_without_group_or_hide_used_unit(self):
        for status in ("support_context", "not_supporting", "unresolved"):
            response = copy.deepcopy(self.response)
            response["facts"][0]["unit_coverage"][0]["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(coverage.CoverageContractError, "classification contradicts"):
                coverage.materialize_inventory(response, self.request)

    def test_unresolved_units_are_explicit_and_not_found_cannot_hide_them(self):
        response = copy.deepcopy(self.response)
        fact = response["facts"][0]
        fact["support_groups"] = []; fact["status"] = "not_found"
        response["proof_paths"] = []; relabel(response, self.request)
        fact["unit_coverage"][0]["status"] = "unresolved"
        with self.assertRaisesRegex(coverage.CoverageContractError, "not_found cannot conceal"):
            coverage.materialize_inventory(response, self.request)
        fact["status"] = "unresolved"
        report = coverage.validate_coverage(response, self.request)
        self.assertFalse(report["all_units_classified_without_unknown"])
        self.assertEqual(len(report["unresolved_source_units"]), 1)

    def test_missing_facts_paths_and_inconsistent_status_are_never_repaired(self):
        for change in (lambda r: r["facts"].pop(), lambda r: r["proof_paths"].clear(),
                       lambda r: r["facts"][0].update(status="not_found")):
            response = copy.deepcopy(self.response); change(response)
            with self.subTest(change=change), self.assertRaises(canonical.InventoryContractError):
                coverage.materialize_inventory(response, self.request)

    def test_explicit_unit_exclusions_do_not_establish_semantic_coverage(self):
        # A malicious model labels the known tail restatement not_supporting.
        response = copy.deepcopy(self.response)
        response["facts"][0]["support_groups"].pop(); relabel(response, self.request)
        report = coverage.validate_coverage(response, self.request)
        self.assertTrue(report["coverage_protocol_valid"])
        self.assertFalse(report["natural_text_coverage_established"])
        self.assertFalse(report["semantic_validity_established"])
        self.assertFalse(report["release_ready"])
        merged = coverage.validate_group_reviews(response, self.request, successful_reviews(response, self.request))
        self.assertTrue(merged["independent_source_coverage_review_required"])
        self.assertFalse(merged["natural_text_coverage_established"])

    def test_empty_sources_are_not_automatically_semantically_accepted(self):
        source = make_request([{"context_id": "empty", "text": ""}])
        request = coverage.build_coverage_request(source)
        response = {"contract_version": coverage.VERSION,
            "canonical_request_digest": request["canonical_request_digest"], "coverage_digest": request["coverage_digest"],
            "facts": [{"fact_id": fid, "status": "not_found", "support_groups": [],
                       "unit_coverage": [], "reason": "无文本。"} for fid in ("M", "F")],
            "proof_paths": [], "reason": "无证据提案。"}
        merged = coverage.validate_group_reviews(response, request, [])
        self.assertEqual(merged["outcome"], "needs_adjudication")
        self.assertFalse(merged["model_group_reviews_passed"])


class IsolatedReviewTests(unittest.TestCase):
    def setUp(self):
        self.source, self.request, self.response = fixture()
        self.reviews = successful_reviews(self.response, self.request)

    def test_caller_envelopes_and_inputs_are_independently_freezeable(self):
        envelopes = coverage.build_group_review_requests(self.response, self.request)
        self.assertEqual(len(envelopes), 3)
        self.assertEqual(len({e["group_id"] for e in envelopes}), 3)
        for envelope in envelopes:
            self.assertEqual(set(envelope), {"group_id", "input", "output_schema", "skill"})
            self.assertEqual(envelope["group_id"], envelope["input"]["review_id"])
            self.assertNotIn("contexts", envelope["input"])
            self.assertNotIn("proof_paths", envelope["input"])
            self.assertNotIn("reason", envelope["input"])
            self.assertEqual(len(envelope["input"]["group_units"]), 1)
        first = envelopes[0]["input"]
        self.assertEqual(first["group_units"][0]["quote"], "宁珩的母亲是许蘅。")
        self.assertNotIn("S", {e["entity_id"] for e in first["identity_forms"]})
        self.assertNotIn("许蘅生下宁珩。", [u["quote"] for u in first["group_units"]])

    def test_model_controlled_group_id_cannot_leak_other_text_to_review(self):
        response = copy.deepcopy(self.response)
        leak = "UNSUBMITTED_FULL_CONTEXT_SECRET;OTHER_GROUP_RATIONALE_SECRET"
        response["facts"][0]["support_groups"][0]["group_id"] = leak
        envelopes = coverage.build_group_review_requests(response, self.request)
        serialized = json.dumps(envelopes, ensure_ascii=False)
        self.assertEqual(envelopes, coverage.build_group_review_requests(self.response, self.request))
        self.assertNotIn("UNSUBMITTED_FULL_CONTEXT_SECRET", serialized)
        self.assertNotIn("OTHER_GROUP_RATIONALE_SECRET", serialized)
        self.assertNotIn("proposal_group_id", serialized)
        merged = coverage.validate_group_reviews(response, self.request, successful_reviews(response, self.request))
        self.assertEqual(merged["group_reviews"][0]["proposal_identity"]["group_id"], leak)

    def test_identity_forms_only_contain_surfaces_in_this_exact_group(self):
        source = copy.deepcopy(self.source)
        source["entity_bindings"][0]["aliases"] = ["组外姓名", "乙所出甲", "未识别描述称号"]
        source["request_digest"] = canonical._request_digest(source)
        request = coverage.build_coverage_request(source)
        response = copy.deepcopy(self.response)
        # Rebind through the exact source quotes; no source or proposal repair.
        response.update(canonical_request_digest=request["canonical_request_digest"], coverage_digest=request["coverage_digest"])
        by_quote = {u["quote"]: u["unit_id"] for u in request["unit_catalog"]}
        old_units = {u["unit_id"]: u["quote"] for u in self.request["unit_catalog"]}
        for fact in response["facts"]:
            for g in fact["support_groups"]:
                g["anchor_unit_id"] = by_quote[old_units[g["anchor_unit_id"]]]
                g["unit_ids"] = [by_quote[old_units[uid]] for uid in g["unit_ids"]]
                for grounding in g["entity_groundings"]:
                    grounding["unit_id"] = by_quote[old_units[grounding["unit_id"]]]
        relabel(response, request)
        envelopes = coverage.build_group_review_requests(response, request)
        serialized = json.dumps(envelopes, ensure_ascii=False)
        for invisible in ("组外姓名", "乙所出甲", "未识别描述称号"):
            self.assertNotIn(invisible, serialized)
        for envelope in envelopes:
            visible = [u["quote"] for u in envelope["input"]["group_units"]]
            self.assertTrue(all(any(s in q for q in visible)
                for row in envelope["input"]["identity_forms"] for s in row["surfaces"]))

    def test_all_positive_group_reviews_still_require_independent_full_source_audit(self):
        original = copy.deepcopy(self.reviews)
        merged = coverage.validate_group_reviews(self.response, self.request, self.reviews)
        self.assertEqual(merged["outcome"], "model_group_reviews_passed")
        self.assertEqual(len(merged["group_reviews"]), 3)
        self.assertEqual(merged["raw_coverage_proposal"], self.response)
        self.assertFalse(merged["semantic_validity_established"])
        self.assertFalse(merged["natural_text_coverage_established"])
        self.assertFalse(merged["release_ready"])
        self.assertEqual(self.reviews, original)

    def test_every_unknown_dimension_is_pending_not_success(self):
        for field in ("support_verdict", "subject_verdict", "scope_verdict", "anchor_verdict"):
            reviews = copy.deepcopy(self.reviews); reviews[0][field] = "unknown"
            with self.subTest(field=field):
                merged = coverage.validate_group_reviews(self.response, self.request, reviews)
                self.assertEqual(merged["outcome"], "needs_adjudication")
                self.assertFalse(merged["model_group_reviews_passed"])
                self.assertEqual(merged["group_reviews"][0]["response"][field], "unknown")

    def test_failed_alternative_is_retained_even_with_another_supported_group(self):
        for field, verdict in (("support_verdict", "unsupported"), ("subject_verdict", "missing"),
                               ("scope_verdict", "out_of_scope"), ("anchor_verdict", "not_relation_occurrence")):
            reviews = copy.deepcopy(self.reviews); reviews[0][field] = verdict
            with self.subTest(field=field):
                merged = coverage.validate_group_reviews(self.response, self.request, reviews)
                self.assertEqual(merged["outcome"], "proposal_rejected")
                self.assertEqual(len(merged["inventory"]["facts"][0]["support_groups"]), 2)
                self.assertEqual(merged["group_reviews"][0]["response"][field], verdict)
                self.assertFalse(merged["model_group_reviews_passed"])

    def test_missing_duplicate_extra_and_foreign_reviews_are_rejected(self):
        for reviews in (self.reviews[:-1], self.reviews + [self.reviews[0]],
                        [self.reviews[0], self.reviews[0], self.reviews[2]]):
            with self.subTest(reviews=reviews), self.assertRaises(coverage.CoverageContractError):
                coverage.validate_group_reviews(self.response, self.request, reviews)
        reviews = copy.deepcopy(self.reviews); reviews[0]["review_id"] = "GR-foreign"
        with self.assertRaisesRegex(coverage.CoverageContractError, "cross-request"):
            coverage.validate_group_reviews(self.response, self.request, reviews)
        reviews = copy.deepcopy(self.reviews); reviews[0]["group_review_digest"] = "0" * 64
        with self.assertRaisesRegex(coverage.CoverageContractError, "another proposal"):
            coverage.validate_group_reviews(self.response, self.request, reviews)

    def test_free_extraction_reason_is_not_even_an_opaque_review_input(self):
        response = copy.deepcopy(self.response)
        response["facts"][0]["support_groups"][0]["reason"] = "改变了原组提案。"
        self.assertEqual(coverage.build_group_review_requests(response, self.request),
                         coverage.build_group_review_requests(self.response, self.request))
        merged = coverage.validate_group_reviews(response, self.request, self.reviews)
        self.assertEqual(merged["outcome"], "model_group_reviews_passed")
        self.assertEqual(merged["raw_coverage_proposal"], response)

    def test_unresolved_coverage_prevents_even_positive_group_review_success(self):
        response = copy.deepcopy(self.response)
        irrelevant = unit(self.request, "家谱末尾又记：")["unit_id"]
        next(c for c in response["facts"][0]["unit_coverage"] if c["unit_id"] == irrelevant)["status"] = "unresolved"
        merged = coverage.validate_group_reviews(response, self.request, self.reviews)
        self.assertEqual(merged["outcome"], "needs_adjudication")
        self.assertFalse(merged["model_group_reviews_passed"])

    def test_lexically_grounded_but_negated_group_needs_semantic_refusal(self):
        source = make_request([{"context_id": "A", "text": "宁珩的母亲并不是许蘅。"},
                               {"context_id": "B", "text": "许蘅的父亲是沈澄。"}])
        request = coverage.build_coverage_request(source)
        response = copy.deepcopy(self.response)
        response.update(canonical_request_digest=request["canonical_request_digest"], coverage_digest=request["coverage_digest"])
        first, father = "宁珩的母亲并不是许蘅。", "许蘅的父亲是沈澄。"
        response["facts"][0]["support_groups"] = [group(request, "m", first, [first],
            [("N", first, "宁珩"), ("X", first, "许蘅")])]
        response["facts"][1]["support_groups"] = [group(request, "f", father, [father],
            [("X", father, "许蘅"), ("S", father, "沈澄")])]
        relabel(response, request)
        self.assertTrue(coverage.validate_coverage(response, request)["protocol_valid"])
        reviews = successful_reviews(response, request)
        reviews[0].update(support_verdict="unsupported", reason="原文明确为并不是许蘅，否定目标母亲关系。")
        merged = coverage.validate_group_reviews(response, request, reviews)
        self.assertEqual(merged["outcome"], "proposal_rejected")
        self.assertEqual(merged["inventory"]["facts"][0]["status"], "support_proposed")
        self.assertEqual(merged["inventory"]["facts"][0]["support_groups"][0][0]["quote"], first)

    def test_direct_group_review_rejects_added_full_context_even_with_fresh_hash(self):
        request = coverage.build_group_review_requests(self.response, self.request)[0]["input"]
        request["contexts"] = self.source["contexts"]
        request["group_review_digest"] = coverage._digest({k: v for k, v in request.items() if k != "group_review_digest"})
        review = copy.deepcopy(self.reviews[0]); review["group_review_digest"] = request["group_review_digest"]
        with self.assertRaisesRegex(coverage.CoverageContractError, "request binding invalid"):
            coverage.validate_group_review(review, request)


if __name__ == "__main__":
    unittest.main()
