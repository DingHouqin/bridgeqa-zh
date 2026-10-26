"""Window coverage, deterministic assembly and isolated occurrence review tests.

Contract: [inventory_occurrences_v8.py](inventory_occurrences_v8.py).
All semantic review responses are scripted; these are not model quality claims.
"""
import copy
import json
import unittest

import inventory_occurrences_v8 as V
import inventory_coverage as C
import support_contract as K
from test_inventory_coverage import make_request


def units(request):
    return C.build_coverage_request(request)["unit_catalog"]


def by_quote(request, quote):
    return next(u for u in units(request) if u["quote"] == quote)


def empty_responses(envelopes, verdict="unsupported"):
    return [{"contract_version": V.VERSION, "window_id": e["window_id"],
        "window_digest": e["input"]["window_digest"], "occurrences": [
            {"anchor_unit_id": uid, "verdict": verdict, "support_group": None,
             "reason": "逐位置独立裁定，不因找到一处就停止。"}
            for uid in e["input"]["anchor_unit_ids"]]} for e in envelopes]


def positive(request, responses, envelopes, fid, anchor_quote, group_quotes, grounds):
    anchor = by_quote(request, anchor_quote)["unit_id"]
    target = next(r for e, r in zip(envelopes, responses)
                  if e["input"]["fact"]["fact_id"] == fid and anchor in e["input"]["anchor_unit_ids"])
    row = next(r for r in target["occurrences"] if r["anchor_unit_id"] == anchor)
    selected = [by_quote(request, q) for q in group_quotes]
    groundings = [{"entity_id": eid, "unit_id": by_quote(request, q)["unit_id"], "surface": surface}
                  for eid, q, surface in grounds]
    row.update(verdict="supported", support_group={"unit_ids": [u["unit_id"] for u in selected],
        "endpoint_groundings": groundings,
        "anchors": {key: {"unit_id": selected[0]["unit_id"], "surface": selected[0]["quote"]}
                    for key in V.ANCHOR_KEYS}, "reason": "仅本组原文支持的提案。"})
    return row


def fixture():
    request = make_request(); envelopes = V.build_occurrence_requests(request)
    responses = empty_responses(envelopes)
    first, tail, father = "宁珩的母亲是许蘅。", "许蘅生下宁珩。", "许蘅的父亲是沈澄。"
    positive(request, responses, envelopes, "M", first, [first], [("N", first, "宁珩"), ("X", first, "许蘅")])
    positive(request, responses, envelopes, "M", tail, [tail], [("N", tail, "宁珩"), ("X", tail, "许蘅")])
    positive(request, responses, envelopes, "F", father, [father], [("X", father, "许蘅"), ("S", father, "沈澄")])
    return request, envelopes, responses


def reviews(assembly):
    return [{"contract_version": V.REVIEW_VERSION, "review_id": e["group_id"],
        "group_review_digest": e["input"]["group_review_digest"], "support_verdict": "supported",
        "subject_verdict": "self_contained", "role_verdict": "matched", "scope_verdict": "in_scope",
        "anchor_verdict": "assertion_completion", "reason": "本anchor完成命名关系断言，本组原文完整。"}
        for e in V.build_group_review_requests(assembly)]


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.request, self.envelopes, self.responses = fixture()

    def test_every_fact_gets_all_disjoint_anchors_in_windows_of_at_most_eight(self):
        request = make_request([{"context_id": "T", "text": "景物。" * 19}])
        envelopes = V.build_occurrence_requests(request)
        self.assertEqual(len(envelopes), 6)
        for fid in ("M", "F"):
            chunks = [e["input"]["anchor_unit_ids"] for e in envelopes if e["input"]["fact"]["fact_id"] == fid]
            self.assertEqual([len(c) for c in chunks], [8, 8, 3])
            self.assertEqual([x for c in chunks for x in c], [u["unit_id"] for u in units(request)])
        assembly = V.assemble_inventory(request, empty_responses(envelopes))
        self.assertEqual(assembly["report"]["coverage_cells_registered"], 38)
        self.assertEqual(assembly["report"]["coverage_cells_expected"], 38)

    def test_each_call_has_only_one_target_fact_and_explicit_direction(self):
        for envelope in self.envelopes:
            item = envelope["input"]
            self.assertNotIn("requested_edges", item)
            self.assertNotIn("query", item)
            self.assertNotIn("proof_paths", item)
            self.assertIn("child是子辈", item["role_definition"])
            self.assertEqual(item["child_surface"], "宁珩" if item["fact"]["fact_id"] == "M" else "许蘅")
            self.assertEqual(item["parent_surface"], "许蘅" if item["fact"]["fact_id"] == "M" else "沈澄")
            self.assertEqual(item["source_units"], units(self.request))

    def test_occurrence_and_review_examples_retain_child_to_parent_direction(self):
        for prompt in (V.OCCURRENCE_PROMPT, V.GROUP_REVIEW_PROMPT):
            self.assertIn("child=乙,parent=甲,role=parent（乙→甲）", prompt)
            self.assertNotIn("对甲→乙", prompt)

    def test_relation_description_in_canonical_name_cannot_bypass_pure_display_filter(self):
        request = K.make_inventory_request("乙的父亲是谁？",
            {"operation": "parents", "start": "B", "steps": ["father"], "scope": "现实登记"},
            [{"context_id": "P", "text": "甲是乙的亲生家长。丙在窗前。"}],
            [{"fact_id": "AB", "parent": "A", "child": "B", "parent_role": "father", "scope": "现实登记"}],
            [{"id": "A", "name": "甲（丙之父）", "aliases": ["甲"]},
             {"id": "B", "name": "乙", "aliases": []}, {"id": "C", "name": "丙", "aliases": []}])
        envelopes = V.build_occurrence_requests(request)
        self.assertEqual(envelopes[0]["input"]["parent_surface"], "甲")
        self.assertNotIn("丙之父", json.dumps(envelopes, ensure_ascii=False))
        responses = empty_responses(envelopes)
        quote = "甲是乙的亲生家长。"
        positive(request, responses, envelopes, "AB", quote, [quote], [("B", quote, "乙"), ("A", quote, "甲")])
        assembly = V.assemble_inventory(request, responses)
        reviews_input = V.build_group_review_requests(assembly)
        self.assertEqual(reviews_input[0]["input"]["parent_surface"], "甲")
        self.assertNotIn("丙之父", json.dumps(reviews_input, ensure_ascii=False))
        raw = reviews(assembly); raw[0]["role_verdict"] = "unknown"
        self.assertEqual(V.validate_group_reviews(assembly, raw)["outcome"], "needs_adjudication")

    def test_missing_pure_display_is_explicit_without_exporting_descriptor(self):
        request = K.make_inventory_request("乙的父亲是谁？",
            {"operation": "parents", "start": "B", "steps": ["father"], "scope": "现实登记"},
            [{"context_id": "P", "text": "乙和丙坐在窗前。"}],
            [{"fact_id": "AB", "parent": "A", "child": "B", "parent_role": "father", "scope": "现实登记"}],
            [{"id": "A", "name": "甲（丙之父）", "aliases": []},
             {"id": "B", "name": "乙", "aliases": []}, {"id": "C", "name": "丙", "aliases": []}])
        envelopes = V.build_occurrence_requests(request)
        self.assertEqual(envelopes[0]["input"]["parent_surface"], "")
        self.assertEqual(envelopes[0]["input"]["surface_resolution"]["parent"], "unresolved")
        self.assertNotIn("丙之父", json.dumps(envelopes, ensure_ascii=False))

    def test_normal_proper_name_with_mother_character_is_still_exported_when_visible(self):
        request = K.make_inventory_request("乙的母亲是谁？",
            {"operation": "parents", "start": "B", "steps": ["mother"], "scope": "现实登记"},
            [{"context_id": "P", "text": "乙的母亲是贾母。"}],
            [{"fact_id": "AB", "parent": "A", "child": "B", "parent_role": "mother", "scope": "现实登记"}],
            [{"id": "A", "name": "贾母", "aliases": []}, {"id": "B", "name": "乙", "aliases": []}])
        self.assertEqual(V.build_occurrence_requests(request)[0]["input"]["parent_surface"], "贾母")

    def test_window_schema_binds_known_ids_and_array_size_without_character_arithmetic(self):
        envelope = self.envelopes[0]
        schema = envelope["output_schema"]["properties"]
        self.assertEqual(schema["window_id"]["enum"], [envelope["window_id"]])
        rows = schema["occurrences"]
        self.assertEqual(rows["minItems"], len(envelope["input"]["anchor_unit_ids"]))
        self.assertEqual(rows["maxItems"], rows["minItems"])
        self.assertEqual(rows["items"]["properties"]["anchor_unit_id"]["enum"], envelope["input"]["anchor_unit_ids"])
        self.assertNotIn("start", json.dumps(rows))

    def test_partition_preserves_dialogue_crlf_nonbmp_whitespace_and_occurrence_positions(self):
        request = make_request([{"context_id": "T", "text": '📚问：“谁，宁珩？”\r\n答：许蘅；尾注  '},
                                {"context_id": "E", "text": ""}, {"context_id": "W", "text": " \t "}])
        for context in request["contexts"]:
            selected = [u for u in units(request) if u["context_id"] == context["context_id"]]
            self.assertEqual("".join(u["quote"] for u in selected), context["text"])
            cursor = 0
            for u in selected:
                self.assertEqual(u["start"], cursor)
                self.assertEqual(context["text"][u["start"]:u["end"]], u["quote"])
                cursor = u["end"]
            self.assertEqual(cursor, len(context["text"]))

    def test_bad_window_sizes_rejected_and_requests_are_deterministic_copies(self):
        original = copy.deepcopy(self.request)
        self.assertEqual(V.build_occurrence_requests(self.request), self.envelopes)
        self.assertEqual(self.request, original)
        for size in (0, 9, True, None, 2.5):
            with self.subTest(size=size), self.assertRaises(V.OccurrenceContractError):
                V.build_occurrence_requests(self.request, size)

    def test_every_window_anchor_exactly_once_even_if_one_support_already_found(self):
        for mutation in (lambda rows: rows.pop(), lambda rows: rows.append(copy.deepcopy(rows[0])),
                         lambda rows: rows.__setitem__(1, copy.deepcopy(rows[0]))):
            response = copy.deepcopy(self.responses[0]); mutation(response["occurrences"])
            with self.subTest(mutation=mutation), self.assertRaisesRegex(V.OccurrenceContractError, "exactly once"):
                V.validate_occurrence_response(response, self.envelopes[0]["input"])

    def test_response_and_request_digests_cannot_migrate_across_fact_windows(self):
        with self.assertRaisesRegex(V.OccurrenceContractError, "another window"):
            V.validate_occurrence_response(self.responses[0], self.envelopes[1]["input"])
        request = copy.deepcopy(self.envelopes[0]["input"]); request["child_surface"] = "伪主体"
        with self.assertRaisesRegex(V.OccurrenceContractError, "digest"):
            V.validate_occurrence_response(self.responses[0], request)

    def test_supported_requires_group_and_unknown_cannot_carry_positive_group(self):
        for status, group_value in (("supported", None), ("unknown", self.responses[0]["occurrences"][0]["support_group"]),
                                    ("unsupported", self.responses[0]["occurrences"][0]["support_group"])):
            response = copy.deepcopy(self.responses[0]); response["occurrences"][0].update(verdict=status, support_group=group_value)
            with self.subTest(status=status), self.assertRaisesRegex(V.OccurrenceContractError, "needs a group"):
                V.validate_occurrence_response(response, self.envelopes[0]["input"])

    def test_unsupported_does_not_mean_a_unit_cannot_be_another_groups_antecedent(self):
        response = self.responses[0]
        header = by_quote(self.request, "家谱末尾又记：")["unit_id"]
        self.assertEqual(next(r for r in response["occurrences"] if r["anchor_unit_id"] == header)["verdict"], "unsupported")
        tail = next(r for r in response["occurrences"] if r["anchor_unit_id"] == by_quote(self.request, "许蘅生下宁珩。")["unit_id"])
        tail["support_group"]["unit_ids"].insert(0, header)
        self.assertTrue(V.validate_occurrence_response(response, self.envelopes[0]["input"])["protocol_valid"])

    def test_groundings_and_all_five_bases_must_be_exactly_inside_this_group(self):
        for field in V.ANCHOR_KEYS:
            response = copy.deepcopy(self.responses[0])
            response["occurrences"][0]["support_group"]["anchors"][field]["surface"] = "组外未引原文"
            with self.subTest(field=field), self.assertRaisesRegex(V.OccurrenceContractError, "basis is not exact"):
                V.validate_occurrence_response(response, self.envelopes[0]["input"])
        response = copy.deepcopy(self.responses[0])
        response["occurrences"][0]["support_group"]["endpoint_groundings"][0]["unit_id"] = by_quote(self.request, "许蘅生下宁珩。")["unit_id"]
        with self.assertRaisesRegex(V.OccurrenceContractError, "outside its group"):
            V.validate_occurrence_response(response, self.envelopes[0]["input"])

    def test_scope_uses_actual_semantic_basis_not_literal_metadata_label(self):
        # The original direct assertion need not spell the metadata 合成户籍.
        self.assertNotIn(self.request["requested_edges"][0]["scope"],
                         self.responses[0]["occurrences"][0]["support_group"]["anchors"]["scope"]["surface"])
        self.assertTrue(V.validate_occurrence_response(self.responses[0], self.envelopes[0]["input"])["protocol_valid"])
        response = copy.deepcopy(self.responses[0])
        response["occurrences"][0]["support_group"]["anchors"]["scope"]["surface"] = "合成户籍"
        with self.assertRaisesRegex(V.OccurrenceContractError, "scope basis is not exact"):
            V.validate_occurrence_response(response, self.envelopes[0]["input"])

    def test_question_and_speaker_components_can_support_name_only_answer_completion(self):
        request = K.make_inventory_request("乙的生父是谁？",
            {"operation": "parents", "start": "B", "steps": ["father"], "scope": "现实访谈"},
            [{"context_id": "I", "text": "记者问乙：“你的生父是谁？”乙回答：“甲。”"}],
            [{"fact_id": "AB", "parent": "A", "child": "B", "parent_role": "father", "scope": "现实访谈"}],
            [{"id": "A", "name": "甲", "aliases": []}, {"id": "B", "name": "乙", "aliases": []}])
        envelopes = V.build_occurrence_requests(request); responses = empty_responses(envelopes)
        quotes = [u["quote"] for u in units(request)]
        row = positive(request, responses, envelopes, "AB", "“甲。”", quotes,
                       [("B", "记者问乙：", "乙"), ("A", "“甲。”", "甲")])
        group = row["support_group"]
        for key in ("predicate", "parent_role"):
            group["anchors"][key] = {"unit_id": by_quote(request, "“你的生父是谁？”")["unit_id"], "surface": "生父"}
        group["anchors"]["parent"] = {"unit_id": by_quote(request, "“甲。”")["unit_id"], "surface": "甲"}
        assembly = V.assemble_inventory(request, responses)
        self.assertEqual(assembly["report"]["positive_occurrence_proposals"], 1)
        self.assertEqual(assembly["inventory"]["facts"][0]["status"], "support_proposed")
        self.assertEqual([r["verdict"] for r in assembly["occurrence_ledger"]],
                         ["unsupported", "unsupported", "unsupported", "supported"])
        self.assertEqual(len(V.build_group_review_requests(assembly)[0]["input"]["group_units"]), 4)

    def test_cross_context_number_identity_is_one_completed_conjunctive_occurrence(self):
        first = "宁珩的母亲是许蘅。"
        request = make_request([{"context_id": "M", "text": first},
            {"context_id": "F", "text": "许蘅的父亲，正是账册里编号为父17的人。"},
            {"context_id": "I", "text": "账册编号父17的人名叫沈澄。"}])
        envelopes = V.build_occurrence_requests(request); responses = empty_responses(envelopes)
        positive(request, responses, envelopes, "M", first, [first], [("N", first, "宁珩"), ("X", first, "许蘅")])
        selected = ["许蘅的父亲，", "正是账册里编号为父17的人。", "账册编号父17的人名叫沈澄。"]
        row = positive(request, responses, envelopes, "F", selected[1], selected,
                       [("X", selected[0], "许蘅"), ("S", selected[2], "沈澄")])
        row["support_group"]["anchors"]["parent"] = {"unit_id": by_quote(request, selected[2])["unit_id"], "surface": "沈澄"}
        assembly = V.assemble_inventory(request, responses)
        self.assertEqual(assembly["report"]["positive_occurrence_proposals"], 2)
        self.assertEqual(len(assembly["inventory"]["facts"][1]["support_groups"]), 1)
        self.assertEqual(len(assembly["inventory"]["facts"][1]["support_groups"][0]), 3)
        self.assertEqual(len(V.build_group_review_requests(assembly)[1]["input"]["group_units"]), 3)
        lookup = by_quote(request, selected[2])["unit_id"]
        self.assertEqual(next(r for r in assembly["occurrence_ledger"] if r["fact_id"] == "F" and
                              r["anchor_unit_id"] == lookup)["verdict"], "unsupported")


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.request, self.envelopes, self.responses = fixture()

    def test_declared_assembly_derives_facts_and_paths_without_model_authored_paths(self):
        original = copy.deepcopy(self.responses)
        assembly = V.assemble_inventory(self.request, self.responses)
        self.assertEqual([f["status"] for f in assembly["inventory"]["facts"]], ["support_proposed", "support_proposed"])
        self.assertEqual(assembly["inventory"]["proof_paths"], [{"fact_ids": ["M", "F"], "entity_ids": ["N", "X", "S"]}])
        self.assertEqual(assembly["report"]["positive_occurrence_proposals"], 3)
        self.assertEqual(self.responses, original)
        self.assertIn("explicit_contract", assembly["report"]["fact_status_and_paths_are"])
        self.assertFalse(assembly["report"]["semantic_validity_established"])

    def test_every_fact_window_required_unknown_duplicate_and_missing_windows_fail(self):
        for responses in (self.responses[:-1], self.responses + [self.responses[0]], [self.responses[0], self.responses[0]]):
            with self.subTest(responses=responses), self.assertRaises(V.OccurrenceContractError):
                V.assemble_inventory(self.request, responses)
        responses = copy.deepcopy(self.responses); responses[0]["window_id"] = "OW-foreign"
        with self.assertRaisesRegex(V.OccurrenceContractError, "cross-request"):
            V.assemble_inventory(self.request, responses)

    def test_unknown_is_never_aggregated_as_negative(self):
        responses = empty_responses(self.envelopes)
        responses[0]["occurrences"][0]["verdict"] = "unknown"
        assembly = V.assemble_inventory(self.request, responses)
        self.assertEqual([f["status"] for f in assembly["inventory"]["facts"]], ["unresolved", "not_found"])
        self.assertEqual(assembly["report"]["unknown_occurrences"], 1)
        self.assertEqual(V.validate_group_reviews(assembly, [])["outcome"], "needs_adjudication")

    def test_positive_and_unknown_keeps_proposed_edge_but_cannot_report_clean_review(self):
        responses = copy.deepcopy(self.responses)
        responses[0]["occurrences"][1]["verdict"] = "unknown"
        assembly = V.assemble_inventory(self.request, responses)
        self.assertEqual(assembly["inventory"]["facts"][0]["status"], "support_proposed")
        self.assertEqual(V.validate_group_reviews(assembly, reviews(assembly))["outcome"], "needs_adjudication")

    def test_no_positive_is_distinct_from_unknown_and_needs_source_review(self):
        # May represent a source with only future/conditional parent assertions.
        assembly = V.assemble_inventory(self.request, empty_responses(self.envelopes))
        self.assertTrue(all(f["status"] == "not_found" for f in assembly["inventory"]["facts"]))
        result = V.validate_group_reviews(assembly, [])
        self.assertEqual(result["outcome"], "no_positive_occurrences_requires_source_review")
        self.assertFalse(result["unknown_observed"])
        self.assertTrue(result["independent_source_coverage_review_required"])
        self.assertFalse(result["semantic_validity_established"])

    def test_actual_future_conditional_source_can_have_determinate_all_negative_proposals(self):
        request = make_request([{"context_id": "C", "text": "若将来核验成立，才会登记许蘅为宁珩母亲。当前未确认亲生关系。"}])
        envelopes = V.build_occurrence_requests(request)
        assembly = V.assemble_inventory(request, empty_responses(envelopes))
        result = V.validate_group_reviews(assembly, [])
        self.assertEqual(result["outcome"], "no_positive_occurrences_requires_source_review")
        self.assertEqual([f["status"] for f in result["inventory"]["facts"]], ["not_found", "not_found"])
        self.assertFalse(result["unknown_observed"])
        self.assertFalse(result["release_ready"])

    def test_zero_context_has_zero_calls_and_zero_cells_without_unknown(self):
        request = K.make_inventory_request(self.request["question"], self.request["query"], [],
            self.request["requested_edges"], self.request["entity_bindings"])
        self.assertEqual(V.build_occurrence_requests(request), [])
        assembly = V.assemble_inventory(request, [])
        self.assertEqual(assembly["report"]["coverage_cells_registered"], 0)
        self.assertEqual(assembly["occurrence_ledger"], [])
        self.assertFalse(V.validate_group_reviews(assembly, [])["unknown_observed"])

    def test_equal_canonical_groups_share_representation_but_keep_all_anchor_provenance(self):
        responses = copy.deepcopy(self.responses)
        first, header = by_quote(self.request, "宁珩的母亲是许蘅。"), by_quote(self.request, "家谱末尾又记：")
        row = responses[0]["occurrences"][0]
        row["support_group"]["unit_ids"].append(header["unit_id"])
        other = next(r for r in responses[0]["occurrences"] if r["anchor_unit_id"] == header["unit_id"])
        other.update(verdict="supported", support_group=copy.deepcopy(row["support_group"]))
        assembly = V.assemble_inventory(self.request, responses)
        self.assertEqual(assembly["report"]["positive_occurrence_proposals"], 4)
        self.assertEqual(assembly["report"]["canonical_unique_group_representations"], 3)
        pair = [r for r in assembly["occurrence_ledger"] if r["fact_id"] == "M" and
                r["anchor_unit_id"] in (first["unit_id"], header["unit_id"])]
        self.assertTrue(all(r["duplicate_footprint_review_required"] for r in pair))
        self.assertEqual(pair[0]["canonical_group_index"], pair[1]["canonical_group_index"])
        self.assertEqual(len(V.build_group_review_requests(assembly)), 4)
        self.assertFalse(assembly["report"]["distinct_support_occurrences_established"])
        raw_reviews = reviews(assembly)
        index = next(i for i, e in enumerate(V.build_group_review_requests(assembly))
                     if e["input"]["anchor_unit_id"] == header["unit_id"])
        raw_reviews[index]["anchor_verdict"] = "not_assertion_completion"
        result = V.validate_group_reviews(assembly, raw_reviews)
        self.assertEqual(result["outcome"], "proposal_rejected")
        self.assertEqual(len(result["occurrence_ledger"]), 8)

    def test_nested_real_restatement_reusing_first_claim_as_antecedent_is_preserved(self):
        first, again, father = "宁珩的母亲是许蘅。", "旁注再记她是宁珩的母亲。", "许蘅的父亲是沈澄。"
        request = make_request([{"context_id": "A", "text": first + again}, {"context_id": "B", "text": father}])
        envelopes = V.build_occurrence_requests(request); responses = empty_responses(envelopes)
        for anchor, selected in ((first, [first]), (again, [first, again])):
            positive(request, responses, envelopes, "M", anchor, selected,
                     [("N", first, "宁珩"), ("X", first, "许蘅")])
        positive(request, responses, envelopes, "F", father, [father], [("X", father, "许蘅"), ("S", father, "沈澄")])
        assembly = V.assemble_inventory(request, responses)
        self.assertEqual(len(assembly["inventory"]["facts"][0]["support_groups"]), 2)
        self.assertEqual(len(V.build_group_review_requests(assembly)), 3)
        self.assertEqual(V.validate_group_reviews(assembly, reviews(assembly))["outcome"], "model_group_reviews_passed")

    def test_repeated_identical_source_text_is_not_deduplicated_by_quote_string(self):
        request = make_request([{"context_id": "A", "text": "宁珩的母亲是许蘅。宁珩的母亲是许蘅。"},
                                {"context_id": "B", "text": "许蘅的父亲是沈澄。"}])
        envelopes = V.build_occurrence_requests(request); responses = empty_responses(envelopes)
        selected = [u for u in units(request) if u["quote"] == "宁珩的母亲是许蘅。"]
        for u in selected:
            row = next(r for r in responses[0]["occurrences"] if r["anchor_unit_id"] == u["unit_id"])
            row.update(verdict="supported", support_group={"unit_ids": [u["unit_id"]],
                "endpoint_groundings": [{"entity_id": eid, "unit_id": u["unit_id"], "surface": surface}
                    for eid, surface in (("N", "宁珩"), ("X", "许蘅"))],
                "anchors": {k: {"unit_id": u["unit_id"], "surface": u["quote"]} for k in V.ANCHOR_KEYS}, "reason": "原位置。"})
        assembly = V.assemble_inventory(request, responses)
        self.assertEqual(len(assembly["inventory"]["facts"][0]["support_groups"]), 2)
        self.assertEqual(assembly["report"]["duplicate_footprint_proposals"], [])

    def test_two_true_restatements_quoting_same_whole_passage_keep_both_proposals(self):
        responses = copy.deepcopy(self.responses)
        first, tail = by_quote(self.request, "宁珩的母亲是许蘅。"), by_quote(self.request, "许蘅生下宁珩。")
        for row in responses[0]["occurrences"]:
            if row["anchor_unit_id"] in (first["unit_id"], tail["unit_id"]):
                row["support_group"]["unit_ids"] = [first["unit_id"], tail["unit_id"]]
        assembly = V.assemble_inventory(self.request, responses)
        self.assertEqual(len(assembly["inventory"]["facts"][0]["support_groups"]), 1)
        positives = [r for r in assembly["occurrence_ledger"] if r["fact_id"] == "M" and r["verdict"] == "supported"]
        self.assertEqual(len(positives), 2)
        self.assertTrue(all(r["duplicate_footprint_review_required"] for r in positives))
        self.assertEqual(len(V.build_group_review_requests(assembly)), 3)
        result = V.validate_group_reviews(assembly, reviews(assembly))
        self.assertEqual(result["outcome"], "model_group_reviews_passed")
        self.assertFalse(result["distinct_support_occurrences_established"])

    def test_assembly_tampering_cannot_be_authorized_by_rehashing(self):
        assembly = V.assemble_inventory(self.request, self.responses)
        assembly["inventory"]["facts"][0]["status"] = "not_found"
        assembly["assembly_digest"] = V._digest({k: v for k, v in assembly.items() if k != "assembly_digest"})
        with self.assertRaisesRegex(V.OccurrenceContractError, "changed after"):
            V.build_group_review_requests(assembly)


class GroupReviewTests(unittest.TestCase):
    def setUp(self):
        self.request, self.envelopes, self.responses = fixture()
        self.assembly = V.assemble_inventory(self.request, self.responses)

    def test_isolated_review_contains_only_one_actual_positive_group_and_explicit_role(self):
        envelopes = V.build_group_review_requests(self.assembly)
        for envelope in envelopes:
            item = envelope["input"]
            self.assertNotIn("source_units", item)
            self.assertNotIn("contexts", item)
            self.assertNotIn("reason", item)
            self.assertNotIn("query", item)
            self.assertNotIn("occurrence_ledger", item)
            self.assertEqual(len(item["group_units"]), 1)
            self.assertIn("child是子辈", item["role_definition"])
            self.assertTrue(all(any(s in u["quote"] for u in item["group_units"])
                                for e in item["identity_forms"] for s in e["surfaces"]))

    def test_free_reasons_cannot_change_or_leak_into_even_opaque_review_requests(self):
        responses = copy.deepcopy(self.responses)
        responses[0]["occurrences"][0]["reason"] = "UNSUBMITTED_SOURCE_SECRET"
        responses[0]["occurrences"][0]["support_group"]["reason"] = "OTHER_GROUP_SECRET"
        changed = V.assemble_inventory(self.request, responses)
        self.assertEqual(V.build_group_review_requests(changed), V.build_group_review_requests(self.assembly))
        self.assertNotIn("SECRET", json.dumps(V.build_group_review_requests(changed)))

    def test_every_review_dimension_unknown_or_failure_is_preserved_not_counted_success(self):
        for field, bad in (("support_verdict", "unsupported"), ("subject_verdict", "missing"),
                           ("role_verdict", "mismatched"), ("scope_verdict", "out_of_scope"),
                           ("anchor_verdict", "not_assertion_completion")):
            for value in ("unknown", bad):
                raw = reviews(self.assembly); raw[0][field] = value
                with self.subTest(field=field, value=value):
                    result = V.validate_group_reviews(self.assembly, raw)
                    self.assertEqual(result["outcome"], "needs_adjudication" if value == "unknown" else "proposal_rejected")
                    self.assertEqual(result["group_reviews"][0]["response"][field], value)
                    self.assertEqual(result["inventory"], self.assembly["inventory"])
                    self.assertFalse(result["model_group_reviews_passed"])

    def test_missing_duplicate_foreign_and_bad_digest_reviews_are_hard_failures(self):
        good = reviews(self.assembly)
        for bad in (good[:-1], good + [good[0]], [good[0], good[0], good[2]]):
            with self.subTest(bad=bad), self.assertRaises(V.OccurrenceContractError):
                V.validate_group_reviews(self.assembly, bad)
        bad = copy.deepcopy(good); bad[0]["review_id"] = "OR-foreign"
        with self.assertRaisesRegex(V.OccurrenceContractError, "cross-assembly"):
            V.validate_group_reviews(self.assembly, bad)
        bad = copy.deepcopy(good); bad[0]["group_review_digest"] = "0" * 64
        with self.assertRaisesRegex(V.OccurrenceContractError, "another occurrence"):
            V.validate_group_reviews(self.assembly, bad)

    def test_positive_model_reviews_are_not_independent_source_acceptance(self):
        result = V.validate_group_reviews(self.assembly, reviews(self.assembly))
        self.assertEqual(result["outcome"], "model_group_reviews_passed")
        self.assertTrue(result["independent_source_coverage_review_required"])
        self.assertFalse(result["natural_text_coverage_established"])
        self.assertFalse(result["semantic_validity_established"])
        self.assertFalse(result["distinct_support_occurrences_established"])
        self.assertFalse(result["release_ready"])

    def test_identity_lookup_cannot_be_credited_as_second_parent_assertion(self):
        relation, lookup = "许蘅的父亲是编号父17的人。", "编号父17的人名叫沈澄。"
        request = make_request([{"context_id": "R", "text": relation}, {"context_id": "I", "text": lookup}])
        envelopes = V.build_occurrence_requests(request); responses = empty_responses(envelopes)
        for anchor in (relation, lookup):
            positive(request, responses, envelopes, "F", anchor, [relation, lookup],
                     [("X", relation, "许蘅"), ("S", lookup, "沈澄")])
        assembly = V.assemble_inventory(request, responses)
        self.assertEqual(assembly["report"]["positive_occurrence_proposals"], 2)
        self.assertEqual(assembly["report"]["canonical_unique_group_representations"], 1)
        self.assertEqual(len(V.build_group_review_requests(assembly)), 2)
        raw = reviews(assembly)
        index = next(i for i, e in enumerate(V.build_group_review_requests(assembly))
                     if e["input"]["anchor_unit_id"] == by_quote(request, lookup)["unit_id"])
        raw[index]["anchor_verdict"] = "not_assertion_completion"
        raw[index]["reason"] = "本unit仅将编号映射到姓名，不是新的亲属断言；关系档案为另一个unit。"
        result = V.validate_group_reviews(assembly, raw)
        self.assertEqual(result["outcome"], "proposal_rejected")
        self.assertEqual(len(result["occurrence_ledger"]), 4)


if __name__ == "__main__":
    unittest.main()
