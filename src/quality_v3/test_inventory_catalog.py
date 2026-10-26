"""Exact catalog and no-repair controls; synthetic sources, no model calls.

Canonical boundary tests remain in [test_support_contract.py](test_support_contract.py).
"""
import copy
import unittest

from inventory_catalog import (
    CATALOG_SCHEMA, VERSION, CatalogContractError,
    build_catalog_request, materialize_inventory)
from support_contract import InventoryContractError, make_inventory_request, validate_inventory
from test_support_contract import fixture


def fixture_catalog():
    request, canonical = fixture()
    catalog = build_catalog_request(request)
    ids = {(s["context_id"], s["start"], s["end"], s["quote"]): s["span_id"]
           for s in catalog["span_catalog"]}
    response = {"contract_version": VERSION,
        "canonical_request_digest": catalog["canonical_request_digest"],
        "catalog_digest": catalog["catalog_digest"], "facts": copy.deepcopy(canonical["facts"]),
        "proof_paths": copy.deepcopy(canonical["proof_paths"]), "reason": canonical["reason"]}
    for fact in response["facts"]:
        for group in fact["support_groups"]:
            for i, citation in enumerate(group):
                group[i] = {"span_id": ids[tuple(citation[k] for k in ("context_id", "start", "end", "quote"))]}
    return request, canonical, catalog, response


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.request, self.canonical, self.catalog, self.response = fixture_catalog()

    def with_texts(self, contexts):
        return make_inventory_request(self.request["question"], self.request["query"], contexts,
                                      self.request["requested_edges"], self.request["entity_bindings"])

    def assert_partition(self, request, catalog):
        for context in request["contexts"]:
            for level in ("sentence", "clause"):
                pieces = sorted([s for s in catalog["span_catalog"]
                    if s["context_id"] == context["context_id"] and level in s["granularities"]],
                    key=lambda s: s["start"])
                self.assertEqual("".join(s["quote"] for s in pieces), context["text"])
                cursor = 0
                for piece in pieces:
                    self.assertEqual(piece["start"], cursor)
                    self.assertGreater(piece["end"], cursor)
                    self.assertEqual(piece["quote"], context["text"][piece["start"]:piece["end"]])
                    cursor = piece["end"]
                self.assertEqual(cursor, len(context["text"]))

    def test_complete_exact_partitions_preserve_punctuation_dialogue_and_newlines(self):
        request = self.with_texts([{"context_id": "T", "text":
            '  问：“乙的母亲是谁？”答：“甲，名册所记。”\r\n甲说：乙由甲所生；这不是梦境。尾注无句号  '}])
        catalog = build_catalog_request(request)
        self.assert_partition(request, catalog)
        sentences = [s["quote"] for s in catalog["span_catalog"] if "sentence" in s["granularities"]]
        self.assertEqual(sentences, ['  问：“乙的母亲是谁？”', '答：“甲，名册所记。”\r\n',
                                     '甲说：乙由甲所生；这不是梦境。', '尾注无句号  '])
        self.assertTrue(any(s["quote"] == '答：' for s in catalog["span_catalog"]))

    def test_empty_text_has_no_spans_whitespace_text_is_still_preserved(self):
        request = self.with_texts([{"context_id": "empty", "text": ""},
                                   {"context_id": "space", "text": " \t "}])
        catalog = build_catalog_request(request)
        self.assert_partition(request, catalog)
        self.assertFalse(any(s["context_id"] == "empty" for s in catalog["span_catalog"]))
        self.assertEqual(len(catalog["span_catalog"]), 1)

    def test_sentence_clause_same_interval_share_one_id(self):
        request = self.with_texts([{"context_id": "T", "text": "乙由甲所生。"}])
        spans = build_catalog_request(request)["span_catalog"]
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["granularities"], ["sentence", "clause"])

    def test_duplicate_text_occurrences_and_contexts_have_distinct_ids(self):
        request = self.with_texts([{"context_id": "T", "text": "乙由甲所生。乙由甲所生。"},
                                   {"context_id": "U", "text": "乙由甲所生。"}])
        spans = build_catalog_request(request)["span_catalog"]
        self.assertEqual(len(spans), 3)
        self.assertEqual(len({s["span_id"] for s in spans}), 3)
        self.assertEqual(len({s["quote"] for s in spans}), 1)

    def test_unicode_offsets_use_original_python_characters(self):
        request = self.with_texts([{"context_id": "T", "text": "📚乙由甲所生。乙的父亲是丙。"}])
        catalog = build_catalog_request(request)
        self.assert_partition(request, catalog)
        second = next(s for s in catalog["span_catalog"] if s["quote"] == "乙的父亲是丙。")
        self.assertEqual(second["start"], len("📚乙由甲所生。"))

    def test_deterministic_ids_without_mutating_canonical_request(self):
        original = copy.deepcopy(self.request)
        self.assertEqual(self.catalog, build_catalog_request(self.request))
        self.assertEqual(self.request, original)
        self.catalog["contexts"][0]["text"] = "changed copy"
        self.assertEqual(self.request, original)

    def test_ids_bound_to_full_canonical_request_even_when_text_unchanged(self):
        changed = make_inventory_request("另一个问句", self.request["query"], self.request["contexts"],
                                        self.request["requested_edges"], self.request["entity_bindings"])
        other = build_catalog_request(changed)
        self.assertTrue({s["span_id"] for s in self.catalog["span_catalog"]}.isdisjoint(
                        {s["span_id"] for s in other["span_catalog"]}))

    def test_response_schema_citations_require_only_span_id(self):
        citation = CATALOG_SCHEMA["properties"]["facts"]["items"]["properties"]["support_groups"]["items"]["items"]
        self.assertEqual(set(citation["properties"]), {"span_id"})
        self.assertEqual(citation["required"], ["span_id"])
        self.assertFalse(citation["additionalProperties"])


class MaterializationTests(unittest.TestCase):
    def setUp(self):
        self.request, self.canonical, self.catalog, self.response = fixture_catalog()

    def test_expansion_exactly_recovers_proposal_without_repair(self):
        original = copy.deepcopy(self.response)
        actual = materialize_inventory(self.response, self.catalog)
        self.assertEqual(actual, self.canonical)
        self.assertEqual(self.response, original)
        report = validate_inventory(actual, self.request)
        self.assertTrue(report["semantic_review_required"])
        self.assertFalse(report["semantic_validity_established"])

    def test_unknown_span_id_is_rejected_without_near_match(self):
        self.response["facts"][0]["support_groups"][0][0]["span_id"] += "x"
        with self.assertRaisesRegex(CatalogContractError, "unknown or cross-request"):
            materialize_inventory(self.response, self.catalog)

    def test_foreign_span_id_fails_even_after_response_binding_is_changed(self):
        foreign_request = make_inventory_request("另一个问句", self.request["query"], self.request["contexts"],
            self.request["requested_edges"], self.request["entity_bindings"])
        foreign_catalog = build_catalog_request(foreign_request)
        self.response["canonical_request_digest"] = foreign_catalog["canonical_request_digest"]
        self.response["catalog_digest"] = foreign_catalog["catalog_digest"]
        with self.assertRaisesRegex(CatalogContractError, "cross-request"):
            materialize_inventory(self.response, foreign_catalog)

    def test_response_digest_must_match_exact_catalog(self):
        for field in ("canonical_request_digest", "catalog_digest"):
            response = copy.deepcopy(self.response); response[field] = "0" * 64
            with self.subTest(field=field), self.assertRaisesRegex(CatalogContractError, "another"):
                materialize_inventory(response, self.catalog)

    def test_tampered_or_incomplete_directory_cannot_be_an_authority(self):
        for change in (lambda c: c["span_catalog"].pop(),
                       lambda c: c["span_catalog"][0].update(quote="伪造引文"),
                       lambda c: c["span_catalog"][0].update(start=1),
                       lambda c: c["span_catalog"][0].update(granularities=[]),
                       lambda c: c["span_catalog"].reverse(),
                       lambda c: c.update(catalog_digest="0" * 64)):
            catalog = copy.deepcopy(self.catalog); change(catalog)
            with self.subTest(change=change), self.assertRaisesRegex(CatalogContractError, "exact complete"):
                materialize_inventory(self.response, catalog)

    def test_source_text_tampering_fails_canonical_digest(self):
        self.catalog["contexts"][0]["text"] += "新事实"
        with self.assertRaisesRegex(InventoryContractError, "digest"):
            materialize_inventory(self.response, self.catalog)

    def test_extra_handwritten_quote_or_offsets_are_rejected(self):
        for key, value in (("quote", "乙是丙的父亲。"), ("start", 0), ("end", 7)):
            response = copy.deepcopy(self.response)
            response["facts"][0]["support_groups"][0][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(CatalogContractError, "schema"):
                materialize_inventory(response, self.catalog)

    def test_missing_fact_is_not_filled_in(self):
        self.response["facts"].pop()
        with self.assertRaisesRegex(InventoryContractError, "missing requested"):
            materialize_inventory(self.response, self.catalog)

    def test_empty_groups_are_not_repaired(self):
        for groups in ([], [[]]):
            response = copy.deepcopy(self.response); response["facts"][0]["support_groups"] = groups
            with self.subTest(groups=groups), self.assertRaises(InventoryContractError):
                materialize_inventory(response, self.catalog)

    def test_wrong_fact_status_is_not_overridden(self):
        for status in ("not_found", "unresolved", "supported"):
            response = copy.deepcopy(self.response); response["facts"][0]["status"] = status
            with self.subTest(status=status), self.assertRaises(InventoryContractError):
                materialize_inventory(response, self.catalog)

    def test_incomplete_or_reversed_paths_are_not_reconstructed(self):
        for change in (lambda r: r["proof_paths"].pop(),
                       lambda r: r["proof_paths"][0]["fact_ids"].reverse(),
                       lambda r: r["proof_paths"][0]["entity_ids"].reverse()):
            response = copy.deepcopy(self.response); change(response)
            with self.subTest(change=change), self.assertRaises(InventoryContractError):
                materialize_inventory(response, self.catalog)

    def test_duplicate_span_in_group_is_not_deduplicated(self):
        group = self.response["facts"][0]["support_groups"][0]
        group.append(copy.deepcopy(group[0]))
        with self.assertRaisesRegex(InventoryContractError, "duplicate citation"):
            materialize_inventory(self.response, self.catalog)

    def test_reordered_facts_and_groups_remain_as_submitted(self):
        self.response["facts"].reverse()
        self.response["facts"][-1]["support_groups"].reverse()
        materialized = materialize_inventory(self.response, self.catalog)
        self.assertEqual([f["fact_id"] for f in materialized["facts"]], ["F4", "F3", "F2", "F1"])
        groups = materialized["facts"][-1]["support_groups"]
        self.assertGreater(groups[0][0]["start"], groups[1][0]["start"])


if __name__ == "__main__":
    unittest.main()
