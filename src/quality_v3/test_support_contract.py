"""Support-contract regressions and deletion-occurrence controls; no provider calls.

The synthetic fixtures below make no claims about literary source facts. Legacy
inventory inputs are disclosed regressions from
[R3 fixtures](../../workspace/quality-v3/round-3/new-cases.json).
"""
import copy
import json
from pathlib import Path
import unittest

from support_contract import (
    VERSION, INVENTORY_SCHEMA, InventoryContractError, apply_text_deletions,
    make_inventory_request, retained_inventory, stable_fact_id, validate_inventory)


def citation(request, quote, occurrence=0, context_id="T"):
    text = next(c["text"] for c in request["contexts"] if c["context_id"] == context_id)
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(quote, start + 1)
    return {"context_id": context_id, "start": start, "end": start + len(quote), "quote": quote}


def fixture():
    entities = [{"id": letter, "name": name, "aliases": ["老" + name]}
                for letter, name in zip("ABCD", "甲乙丙丁")]
    edges = [
        {"id": "F1", "parent": "B", "child": "C", "parent_role": "father", "scope": "档案"},
        {"id": "F2", "parent": "A", "child": "B", "parent_role": "mother", "scope": "档案"},
        {"id": "F3", "parent": "D", "child": "C", "parent_role": "mother", "scope": "档案"},
        {"id": "F4", "parent": "A", "child": "D", "parent_role": "mother", "scope": "档案"}]
    request = make_inventory_request(
        "丙的父母中任一人的母亲是谁？", {"operation": "parents", "start": "C",
         "steps": ["parent", "mother"], "scope": "档案"},
        [{"context_id": "T", "text": "乙是丙的父亲。甲是乙的母亲。乙是丙的父亲。丁是丙的母亲。甲是丁的母亲。"}],
        edges, entities)
    quotes = ["乙是丙的父亲。", "甲是乙的母亲。", "丁是丙的母亲。", "甲是丁的母亲。"]
    response = {"contract_version": VERSION, "request_digest": request["request_digest"],
        "facts": [{"fact_id": "F" + str(i + 1), "status": "support_proposed",
                   "support_groups": [[citation(request, quote)]], "reason": "待独立语义核验"}
                  for i, quote in enumerate(quotes)],
        "proof_paths": [{"fact_ids": ["F1", "F2"], "entity_ids": ["C", "B", "A"]},
                        {"fact_ids": ["F3", "F4"], "entity_ids": ["C", "D", "A"]}],
        "reason": "两个请求图路径，不代表所有自然文本支持已穷尽"}
    response["facts"][0]["support_groups"].append([citation(request, quotes[0], occurrence=1)])
    return request, response


class RequestTests(unittest.TestCase):
    def test_generated_id_survives_context_and_order_changes(self):
        request, _ = fixture()
        edges = [{k: v for k, v in edge.items() if k != "fact_id"} for edge in request["requested_edges"]]
        first = make_inventory_request(request["question"], request["query"], request["contexts"], edges,
                                       request["entity_bindings"])
        second = make_inventory_request(request["question"], request["query"], [], list(reversed(edges)),
                                        request["entity_bindings"])
        self.assertEqual({e["fact_id"] for e in first["requested_edges"]},
                         {e["fact_id"] for e in second["requested_edges"]})
        changed = copy.deepcopy(edges[0]); changed["scope"] = "另一档案"
        self.assertNotEqual(stable_fact_id(edges[0]), stable_fact_id(changed))

    def test_legacy_ids_and_entity_bindings_preserved(self):
        request, _ = fixture()
        self.assertEqual(request["requested_edges"][0]["fact_id"], "F1")
        self.assertEqual(request["entity_bindings"][0], {"id": "A", "name": "甲", "aliases": ["老甲"]})

    def test_conflicting_source_ids_rejected(self):
        request, _ = fixture()
        edges = copy.deepcopy(request["requested_edges"])
        edges[0]["id"] = "different"
        with self.assertRaisesRegex(InventoryContractError, "conflicting"):
            make_inventory_request(request["question"], request["query"], request["contexts"], edges,
                                   request["entity_bindings"])

    def test_illegal_edges_rejected_before_model_call(self):
        request, _ = fixture()
        mutations = [lambda edges: edges[0].update(child="unknown"),
                     lambda edges: edges[0].update(parent="C"),
                     lambda edges: edges[1].update(fact_id="F1"),
                     lambda edges: edges.append({**edges[0], "fact_id": "duplicate-edge"}),
                     lambda edges: edges[0].update(parent_role="spouse")]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                edges = copy.deepcopy(request["requested_edges"]); mutate(edges)
                with self.assertRaises(InventoryContractError):
                    make_inventory_request(request["question"], request["query"], request["contexts"], edges,
                                           request["entity_bindings"])

    def test_scope_by_step_requires_every_step(self):
        request, _ = fixture()
        query = {**request["query"], "scope_by_step": ["档案"]}
        with self.assertRaisesRegex(InventoryContractError, "scope_by_step"):
            make_inventory_request(request["question"], query, request["contexts"], request["requested_edges"],
                                   request["entity_bindings"])

    def test_malformed_constructor_collections_raise_contract_error(self):
        request, _ = fixture()
        for key in ("contexts", "requested_edges", "entity_bindings"):
            for value in (None, ["wrong object"]):
                args = {k: copy.deepcopy(request[k]) for k in
                        ("question", "query", "contexts", "requested_edges", "entity_bindings")}
                args[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(InventoryContractError):
                    make_inventory_request(**args)

    def test_r3_legacy_inventory_inputs_construct_without_history_changes(self):
        root = Path(__file__).resolve().parents[2]
        payloads = json.loads((root / "workspace/quality-v3/round-3/new-cases.json").read_text(encoding="utf-8"))
        for case in payloads["inventory_cases"]:
            payload = case["payload"]
            request = make_inventory_request(payload["question"], payload["query"], payload["contexts"],
                payload["candidate_edges"], payload["entity_bindings"])
            self.assertEqual(len(request["requested_edges"]), len(payload["candidate_edges"]))
            self.assertNotIn("candidate_edges", request)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.request, self.response = fixture()

    def assert_invalid(self, mutate, pattern=None):
        answer = copy.deepcopy(self.response); mutate(answer)
        with self.assertRaisesRegex(InventoryContractError, pattern or ".+"):
            validate_inventory(answer, self.request)

    def test_valid_graph_never_certifies_semantics_or_release(self):
        report = validate_inventory(self.response, self.request)
        self.assertTrue(report["protocol_valid"])
        self.assertEqual(report["proposed_support_groups"], 5)
        self.assertEqual(len(report["registered_graph_paths"]), 2)
        for field in ("release_ready", "semantic_validity_established", "natural_text_coverage_established"):
            self.assertFalse(report[field])
        self.assertTrue(report["semantic_review_required"])

    def test_missing_request_edge_rejected_even_if_not_on_current_proof(self):
        self.assert_invalid(lambda answer: answer["facts"].pop(), "missing requested")

    def test_each_requested_edge_has_explicit_status(self):
        answer = copy.deepcopy(self.response)
        answer["facts"][3].update(status="not_found", support_groups=[])
        answer["proof_paths"].pop()
        self.assertTrue(validate_inventory(answer, self.request)["protocol_valid"])

    def test_duplicate_and_unknown_fact_ids_rejected(self):
        self.assert_invalid(lambda answer: answer["facts"].append(copy.deepcopy(answer["facts"][0])), "duplicate")
        self.assert_invalid(lambda answer: answer["facts"][0].update(fact_id="unknown"), "unknown")

    def test_empty_support_group_or_empty_proposal_rejected(self):
        for groups in ([], [[]]):
            self.assert_invalid(lambda answer: answer["facts"][0].update(support_groups=groups))

    def test_nonproposed_status_cannot_smuggle_groups(self):
        for status in ("not_found", "unresolved"):
            self.assert_invalid(lambda answer: answer["facts"][0].update(status=status))

    def test_status_does_not_claim_semantic_support(self):
        self.assert_invalid(lambda answer: answer["facts"][0].update(status="supported"))

    def test_quote_must_match_specific_character_occurrence(self):
        self.assert_invalid(lambda answer: answer["facts"][0]["support_groups"][0][0].update(start=1), "occurrence")
        self.assert_invalid(lambda answer: answer["facts"][0]["support_groups"][0][0].update(context_id="other"), "unknown")
        self.assert_invalid(lambda answer: answer["facts"][0]["support_groups"][0][0].update(start=True), "interval")

    def test_duplicate_group_and_citation_rejected(self):
        self.assert_invalid(lambda answer: answer["facts"][0]["support_groups"].append(
            copy.deepcopy(answer["facts"][0]["support_groups"][0])), "duplicate support")
        self.assert_invalid(lambda answer: answer["facts"][0]["support_groups"][0].append(
            copy.deepcopy(answer["facts"][0]["support_groups"][0][0])), "duplicate citation")

    def test_full_directed_paths_required_in_structured_field(self):
        mutations = [lambda answer: answer["proof_paths"].pop(),
                     lambda answer: answer["proof_paths"][0].update(fact_ids=["F2", "F1"], entity_ids=["A", "B", "C"]),
                     lambda answer: answer["proof_paths"][0].update(fact_ids=["F1"], entity_ids=["C", "B"]),
                     lambda answer: answer["proof_paths"][0].update(entity_ids=["C", "D", "A"]),
                     lambda answer: answer["proof_paths"].append(copy.deepcopy(answer["proof_paths"][0]))]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assert_invalid(mutation)

    def test_entity_names_cannot_replace_canonical_ids_in_paths(self):
        self.assert_invalid(lambda answer: answer["proof_paths"][0].update(entity_ids=["丙", "乙", "甲"]), "unknown entity")

    def test_narrative_correct_path_does_not_rescue_malformed_structured_paths(self):
        self.assert_invalid(lambda answer: answer.update(reason="C→B→A 和 C→D→A", proof_paths=[]), "omitted")

    def test_scope_by_step_is_used_even_with_different_top_level_scope(self):
        request = make_inventory_request(self.request["question"],
            {**self.request["query"], "scope": "其他范围", "scope_by_step": ["档案", "档案"]},
            self.request["contexts"], self.request["requested_edges"], self.request["entity_bindings"])
        answer = {**self.response, "request_digest": request["request_digest"]}
        self.assertTrue(validate_inventory(answer, request)["protocol_valid"])
        bad = make_inventory_request(self.request["question"],
            {**request["query"], "scope_by_step": ["档案", "其他范围"]},
            request["contexts"], request["requested_edges"], request["entity_bindings"])
        answer = {**answer, "request_digest": bad["request_digest"]}
        with self.assertRaisesRegex(InventoryContractError, "scope"):
            validate_inventory(answer, bad)

    def test_explicit_null_scope_by_step_uses_top_level_scope(self):
        request = make_inventory_request(self.request["question"],
            {**self.request["query"], "scope_by_step": None}, self.request["contexts"],
            self.request["requested_edges"], self.request["entity_bindings"])
        answer = {**self.response, "request_digest": request["request_digest"]}
        report = validate_inventory(answer, request)
        self.assertEqual(report["registered_graph_paths"], self.response["proof_paths"])
        projected = retained_inventory(answer, request, [])
        self.assertEqual(projected["inventory"]["proof_paths"], self.response["proof_paths"])

    def test_role_mismatch_cannot_be_hidden_by_connected_endpoints(self):
        request = make_inventory_request(self.request["question"],
            {**self.request["query"], "steps": ["father", "mother"]}, self.request["contexts"],
            self.request["requested_edges"], self.request["entity_bindings"])
        answer = {**self.response, "request_digest": request["request_digest"]}
        with self.assertRaisesRegex(InventoryContractError, "role"):
            validate_inventory(answer, request)

    def test_stale_or_mutated_request_cannot_be_reused(self):
        self.assert_invalid(lambda answer: answer.update(request_digest="0" * 64), "another request")
        request = copy.deepcopy(self.request); request["contexts"][0]["text"] += "新句"
        with self.assertRaisesRegex(InventoryContractError, "digest"):
            validate_inventory(self.response, request)

    def test_schema_is_a_serializable_strict_new_version(self):
        schema = json.loads(json.dumps(INVENTORY_SCHEMA))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["contract_version"]["enum"], [VERSION])
        self.assertEqual(schema["properties"]["proof_paths"]["items"]["type"], "object")

    def test_exact_negated_text_still_requires_semantic_review(self):
        request = make_inventory_request(self.request["question"], self.request["query"],
            [{"context_id": "T", "text": "登记员否定“乙是丙的父亲”。"}],
            self.request["requested_edges"], self.request["entity_bindings"])
        answer = copy.deepcopy(self.response)
        answer["request_digest"] = request["request_digest"]
        answer["proof_paths"] = []
        for fact in answer["facts"]:
            fact.update(status="unresolved", support_groups=[])
        answer["facts"][0].update(status="support_proposed", support_groups=[[
            citation(request, "登记员否定“乙是丙的父亲”。")]])
        report = validate_inventory(answer, request)
        self.assertTrue(report["protocol_valid"])
        self.assertFalse(report["semantic_validity_established"])
        self.assertTrue(report["semantic_review_required"])

    def test_offsets_count_unicode_characters_including_non_bmp(self):
        text = "📚" + self.request["contexts"][0]["text"]
        request = make_inventory_request(self.request["question"], self.request["query"],
            [{"context_id": "T", "text": text}], self.request["requested_edges"], self.request["entity_bindings"])
        answer = copy.deepcopy(self.response); answer["request_digest"] = request["request_digest"]
        for fact in answer["facts"]:
            for group in fact["support_groups"]:
                for quote in group:
                    quote["start"] += 1; quote["end"] += 1
        self.assertTrue(validate_inventory(answer, request)["protocol_valid"])
        answer["facts"][0]["support_groups"][0][0]["start"] += 1
        answer["facts"][0]["support_groups"][0][0]["end"] += 1
        with self.assertRaisesRegex(InventoryContractError, "occurrence"):
            validate_inventory(answer, request)


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.request, self.response = fixture()

    def test_deleting_one_duplicate_does_not_rebind_it_to_remaining_occurrence(self):
        deleted = citation(self.request, "乙是丙的父亲。")
        result = retained_inventory(self.response, self.request, [deleted])
        remaining = result["inventory"]["facts"][0]["support_groups"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0][0]["start"], len("甲是乙的母亲。"))
        self.assertEqual(result["report"]["removed_registered_groups"], [{"fact_id": "F1", "group_index": 0}])
        self.assertEqual(len(result["inventory"]["proof_paths"]), 2)

    def test_unregistered_duplicate_never_substitutes_for_removed_group(self):
        response = copy.deepcopy(self.response)
        response["facts"][0]["support_groups"].pop()
        result = retained_inventory(response, self.request, [citation(self.request, "乙是丙的父亲。")])
        self.assertIn("乙是丙的父亲。", result["request"]["contexts"][0]["text"])
        self.assertEqual(result["inventory"]["facts"][0]["status"], "unresolved")
        self.assertEqual(len(result["inventory"]["proof_paths"]), 1)
        self.assertTrue(result["report"]["semantic_review_required"])
        self.assertFalse(result["report"]["deletion_validity_established"])

    def test_conjunctive_group_is_removed_when_only_one_member_is_deleted(self):
        response = copy.deepcopy(self.response)
        response["facts"][0]["support_groups"] = [[citation(self.request, "乙是丙的父亲。"),
                                                   citation(self.request, "乙是丙的父亲。", occurrence=1)]]
        result = retained_inventory(response, self.request, [citation(self.request, "乙是丙的父亲。", occurrence=1)])
        self.assertEqual(result["inventory"]["facts"][0]["support_groups"], [])

    def test_partial_quote_overlap_removes_group_without_weakening_quote(self):
        deleted = citation(self.request, "丙的父亲")
        result = retained_inventory(self.response, self.request, [deleted])
        self.assertEqual(len(result["inventory"]["facts"][0]["support_groups"]), 1)

    def test_adjacent_deletion_shifts_occurrence_without_removing_it(self):
        deleted = citation(self.request, "乙是丙的父亲。")
        result = retained_inventory(self.response, self.request, [deleted])
        self.assertEqual(result["inventory"]["facts"][1]["support_groups"][0][0]["start"], 0)
        self.assertEqual(result["inventory"]["facts"][1]["support_groups"][0][0]["quote"], "甲是乙的母亲。")

    def test_actual_text_and_declared_deletions_must_agree(self):
        deleted = citation(self.request, "乙是丙的父亲。")
        unchanged = copy.deepcopy(self.request["contexts"])
        with self.assertRaisesRegex(InventoryContractError, "after_contexts"):
            retained_inventory(self.response, self.request, [deleted], after_contexts=unchanged)
        after = apply_text_deletions(self.request, [deleted])
        self.assertTrue(retained_inventory(self.response, self.request, [deleted], after_contexts=after)["report"]["protocol_valid"])

    def test_ids_cannot_masquerade_as_text_deletions(self):
        with self.assertRaises(InventoryContractError):
            retained_inventory(self.response, self.request, [{"fact_id": "F1"}])

    def test_overlapping_duplicate_and_outside_deletions_rejected(self):
        first = citation(self.request, "乙是丙的父亲。")
        cases = [[first, copy.deepcopy(first)], [first, citation(self.request, "丙的父亲")],
                 [{**first, "quote": "不存在"}]]
        for deletions in cases:
            with self.subTest(deletions=deletions):
                with self.assertRaises(InventoryContractError):
                    retained_inventory(self.response, self.request, deletions)

    def test_multi_edit_coordinates_are_original_and_order_independent(self):
        deletions = [citation(self.request, "乙是丙的父亲。", occurrence=1),
                     citation(self.request, "乙是丙的父亲。")]
        result = retained_inventory(self.response, self.request, deletions)
        reversed_result = retained_inventory(self.response, self.request, list(reversed(deletions)))
        self.assertEqual(result, reversed_result)
        self.assertEqual(len(result["inventory"]["proof_paths"]), 1)
        self.assertEqual(result["inventory"]["proof_paths"][0]["fact_ids"], ["F3", "F4"])
        self.assertEqual(result["inventory"]["facts"][2]["support_groups"][0][0]["start"], len("甲是乙的母亲。"))

    def test_whole_context_deletion_leaves_explicit_unresolved_edges(self):
        text = self.request["contexts"][0]["text"]
        result = retained_inventory(self.response, self.request, [{"context_id": "T", "start": 0,
                                                                 "end": len(text), "quote": text}])
        self.assertEqual(result["request"]["contexts"], [{"context_id": "T", "text": ""}])
        self.assertTrue(all(f["status"] == "unresolved" for f in result["inventory"]["facts"]))
        self.assertEqual(result["inventory"]["proof_paths"], [])

    def test_no_edits_keeps_registration_but_still_requires_semantic_review(self):
        result = retained_inventory(self.response, self.request, [])
        self.assertEqual(result["request"]["request_digest"], self.request["request_digest"])
        self.assertEqual(result["inventory"]["proof_paths"], self.response["proof_paths"])
        self.assertTrue(result["report"]["semantic_review_required"])


if __name__ == "__main__":
    unittest.main()
