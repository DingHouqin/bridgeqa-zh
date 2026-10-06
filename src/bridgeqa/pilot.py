"""Reproducible candidate construction from fixed Chinese literary sources.

All snippets are actual, offset-addressed source spans. Graph deletion checks
only test declared proofs, never certify semantic necessity or human review.
"""
import copy
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path

from .protocol import stable_hash, validate_v02, export_inputs, refs
from .validation import require
from .script_conversion import Converter

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ACCESS_SHA256 = "0750898690d31e67ad317ebfb1328527e8a0ba93aa1ce9778bcff5066124a72a"


class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active, self.buffer, self.paragraphs = False, [], []

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self.active, self.buffer = True, []

    def handle_data(self, data):
        if self.active:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "p" and self.active:
            self.paragraphs.append("".join(self.buffer))
            self.active = False


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2)+"\n").encode("utf-8"))


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows).encode("utf-8"))


def source_access_record(path):
    """Verify a frozen historical record; never infer access events from mtime."""
    raw = Path(path).read_bytes()
    require(len(raw) == 1948 and sha_bytes(raw) == SOURCE_ACCESS_SHA256, "source access record hash mismatch")
    record = json.loads(raw)
    require(record["schema_version"] == "source-access-record-1" and
            record["kind"] == "frozen_historical_record_not_independent_time_verification", "source access record contract mismatch")
    sources = record["sources"]
    require(len(sources) == 7 and len({r["source_id"] for r in sources}) == 7, "source access record coverage mismatch")
    return raw, {r["source_id"]: r for r in sources}


def prepare_sources(root, output, write=True):
    archive = root / "docs/plan/draft/source-snapshots"
    registry = json.loads((archive/"download-manifest.json").read_text(encoding="utf-8"))
    access_raw, access = source_access_record(root/"data/pilot/source-access-record.json")
    require(set(access) == {"sgyy-"+item["chapter"] for item in registry}, "source access record differs from source registry")
    require(all(access["sgyy-"+item["chapter"]]["url"] == item["url"] for item in registry), "source access record URL mismatch")
    if write:
        output.mkdir(parents=True, exist_ok=True)
        (output/"source-access-record.json").write_bytes(access_raw)
    else:
        source_access_record(output/"source-access-record.json")
    sources, paragraphs = {}, {}
    for item in registry:
        chapter = item["chapter"]
        html_path = root / Path(item["path"].replace("\\", "/"))
        raw = html_path.read_bytes()
        require(sha_bytes(raw) == item["sha256"], f"source archive bytes changed: {chapter}")
        parser = Paragraphs(); parser.feed(raw.decode("utf-8"))
        paragraphs[chapter] = parser.paragraphs
        text = "\n\n".join(parser.paragraphs).encode("utf-8")
        text_path = output/"sources"/f"chapter-{chapter}.txt"
        if write:
            text_path.parent.mkdir(parents=True, exist_ok=True);text_path.write_bytes(text)
        else:
            require(text_path.read_bytes() == text, "source extraction bytes mismatch")
        source_id = "sgyy-"+chapter
        accessed = access[source_id]["accessed_at"]
        sources[chapter] = {"source_id": source_id, "url": item["url"], "citation": f"《三國演義》毛本，第{chapter}回；羅貫中原著，毛綸/毛宗崗修訂；維基文庫貢獻者",
                            "version": "oldid="+item["url"].split("oldid=")[-1], "accessed_at": accessed,
                            "license": "CC-BY-SA-4.0 digital text; attribution and modification notice in NOTICE.md", "text_sha256": sha_bytes(text),
                            "html_sha256": sha_bytes(raw), "html_path": html_path.relative_to(root).as_posix(), "text_path": text_path.relative_to(root).as_posix() if text_path.is_relative_to(root) else "sources/"+text_path.name,
                            "history_url": item["url"].split("&oldid=")[0]+"&action=history", "extraction": "HTMLParser p/data in page order; charrefs decoded; whitespace retained; Unicode codepoint offsets"}
    return sources, paragraphs


def locate(paragraphs, sources, identifier, chapter, needle, partial=False):
    matches = [(i, p.index(needle), p) for i,p in enumerate(paragraphs[chapter]) if needle in p]
    require(len(matches) == 1, f"span must have exactly one paragraph match: {identifier}")
    index, start, paragraph = matches[0]
    require(paragraph.count(needle) == 1, f"span has repeated occurrence: {identifier}")
    text = paragraph[start:start+len(needle)]
    return {"span_id": identifier, "source_id": sources[chapter]["source_id"], "chapter": chapter, "paragraph_index": index,
            "paragraph_sha256": sha_bytes(paragraph.encode("utf-8")), "char_start": start, "char_end": start+len(text), "text": text,
            "text_sha256": sha_bytes(text.encode("utf-8")), "partial_sentence": partial, "review": "pending_human"}


def make_spans(paragraphs, sources):
    selections = [
        ("e1", "005", "北海太守孔融部將武安國，使鐵鎚飛馬而出。呂布揮戟拍馬來迎。戰到十餘合，一戟砍斷安國手腕，棄鎚於地而走。", False),
        ("e2", "005", "匡視之，乃河內名將方悅。兩馬相交，無五合，被呂布一戟刺於馬下，挺戟直衝過來。", False),
        ("e3", "005", "上黨太守張楊部將穆順，出馬挺鎗迎戰，被呂布手起一戟，刺於馬下。", False),
        ("e4", "005", "公孫瓚揮槊親戰呂布。戰不數合，瓚敗走。呂布縱赤兔馬趕來。", False),
        ("e5a", "003", "董卓未及回言，呂布飛馬直殺過來。", False),
        ("e5b", "003", "次日，布持丁原首級，往見李肅。肅遂引布見卓。卓大喜，置酒相待。卓先下拜曰：「卓今得將軍，如旱苗之得甘雨也。」布納卓坐而拜之曰：「公若不棄，布請拜為義父。」卓以金甲錦袍賜布，暢飲而散。", False),
        ("e6a", "003", "卻說前將軍斄鄉侯西涼刺史董卓", True),
        ("e6b", "003", "卓自是威勢越大，自領前將軍事，封弟董旻為左將軍鄠侯", True),
        ("e7a", "003", "使其婿中郎將牛輔，守住陝西", True),
        ("e8", "009", "胡赤兒謀殺牛輔，奪其金寶。", False),
        ("e9", "007", "卻說孫堅有四子，皆吳夫人所生：長子名策，字伯符；次子名權，字仲謀；三子名翊，字叔弼；四子名匡，字季佐。", False),
        ("e10", "002", "吳郡富春人也：姓孫，名堅，字文臺，乃孫武子之後。", False),
        ("e11", "029", "此人姓顧，名雍，子元嘆，乃中郎蔡邕之徒。", False),
        ("e12", "071", "林木之間，乃蔡邕莊也。今邕女蔡琰", True),
        ("e13a", "071", "曹操兵分三路而進", True),
        ("e13b", "071", "左賢王懼操之勢，送蔡琰還漢。操乃以琰配董祀為妻。", False),
    ]
    return {args[0]: locate(paragraphs, sources, *args) for args in selections}


# Historical pre-S1 blueprint labels retained solely for original ID derivation.
BLUEPRINTS = [
    ("s1", "sg-lubu-dongzhuo", "武安國", [("斬斷手腕者", "呂布", ["e1"]), ("投董卓後認作義父", "董卓", ["e5a","e5b"])]),
    ("s2", "sg-lubu-dongzhuo", "方悅", [("刺於馬下者", "呂布", ["e2"]), ("投董卓後認作義父", "董卓", ["e5a","e5b"]), ("弟弟", "董旻", ["e6a","e6b"])]),
    ("s3", "sg-lubu-dongzhuo", "穆順", [("刺於馬下者", "呂布", ["e3"]), ("投董卓後認作義父", "董卓", ["e5a","e5b"]), ("駐陝西的中郎將女婿", "牛輔", ["e6a","e7a"])]),
    ("s4", "sg-lubu-dongzhuo", "公孫瓚", [("本段騎赤兔馬追趕者", "呂布", ["e4"]), ("投董卓後認作義父", "董卓", ["e5a","e5b"]), ("駐陝西的中郎將女婿", "牛輔", ["e6a","e7a"]), ("謀殺者", "胡赤兒", ["e8"])]),
    ("s5", "sg-sunjian-family", "孫權", [("父親", "孫堅", ["e9"]), ("字", "文臺", ["e10"])]),
    ("s6", "sg-caiyong-family", "顧雍", [("老師", "蔡邕", ["e11"]), ("女兒", "蔡琰", ["e12"]), ("還漢後曹操所配之夫", "董祀", ["e13a","e13b"])])
]
ALIASES = {"武安國":["武安国"], "方悅":["方悦"], "穆順":["穆顺"], "公孫瓚":["公孙瓒"], "呂布":["吕布","布"], "董卓":["卓"], "董旻":[], "牛輔":["牛辅"], "胡赤兒":["胡赤儿"], "孫權":["孙权","權"], "孫堅":["孙坚","堅"], "文臺":["文台"], "顧雍":["顾雍"], "蔡邕":["邕"], "蔡琰":["琰"], "董祀":[]}
NATURAL_QUESTIONS = {
    "s1": "根据给定小说片段，在归附后的拜认事件中，砍断武安国手腕之人认谁为义父？",
    "s2": "根据给定小说片段，在归附后的拜认事件中，将方悦刺于马下之人所认义父的弟弟叫什么？",
    "s3": "根据给定小说片段，在归附后的拜认事件中，将穆顺刺于马下之人所认义父的女婿中，驻守陕西的中郎将叫什么？",
    "s4": "根据给定小说片段，骑赤兔马追赶公孙瓒之人在归附后的拜认事件中所认义父，其驻守陕西的中郎将女婿被谁谋杀？",
    "s5": "根据给定小说片段，孙权父亲的字是什么？",
    "s6": "根据给定小说片段，顾雍老师的女儿还汉后，在本段配婚事件中被配给了谁？",
}
NEUTRAL_RELATIONS = {
    "投董卓後認作義父": ("所认义父", "归附后本段拜认事件"),
    "駐陝西的中郎將女婿": ("女婿", "驻守陕西的中郎将"),
    "本段騎赤兔馬追趕者": ("追赶者", "本段骑赤兔马追赶事件"),
    "還漢後曹操所配之夫": ("所配之夫", "还汉后本段配婚事件"),
}


def appendix(root, relations, mechanism, adversarial):
    prefix = "合成練習附錄：下列同名練習角色不是本題原著人物，關係只對附錄角色有效。"
    names = [root, "金河", "柳川", "陳嶼", "季青"]
    clauses = []
    for i, relation in enumerate(relations):
        if mechanism == "misleading_relation":
            label = "同鄉" if adversarial else "目錄"
        elif mechanism == "redundant":
            label = "兵器研究記錄" if adversarial else "讀書目錄記錄"
        else:
            label = relation if adversarial else ("資料索引標題記錄欄目"*4)[:len(relation)]
        clauses.append(f"練習「{names[i]}」的「{label}」記作「{names[i+1]}」。")
    return prefix+"".join(clauses)


def construct_rows(sources, spans, converter=None):
    """Pure reconstruction used by both generation and joint derivation audit."""
    convert = converter.convert if converter else lambda text: text
    aliases = converter.aliases(ALIASES)[0] if converter else ALIASES
    rows, reviews = [], []
    for seed, cluster, start, edges in BLUEPRINTS:
        start = convert(start)
        # converter=None deliberately retains the historical pre-S1 questions,
        # relation labels and visible bytes to reconstruct the dcda-era IDs.
        edges = [(NEUTRAL_RELATIONS.get(relation, (convert(relation), ""))[0] if converter else relation,
                  convert(tail), identifiers, NEUTRAL_RELATIONS.get(relation, ("", ""))[1] if converter else "")
                 for relation, tail, identifiers in edges]
        steps, documents, span_bindings, chapters = [], [], [], set()
        head = start
        for hop, (relation, tail, identifiers, qualifier) in enumerate(edges, 1):
            did = f"d{hop}"
            sentences = []
            for i, identifier in enumerate(identifiers):
                span = spans[identifier]; chapters.add(span["chapter"])
                sentences.append({"sent_id": i, "text": convert(span["text"])})
                span_bindings.append({"doc_id":did, "sent_id":i, "span_id":identifier})
            documents.append({"doc_id":did, "title":f"材料 {hop}", "language":"zh", "sentences":sentences})
            steps.append({"hop":hop,"head":head,"relation":relation,"tail":tail,"qualifier":qualifier,"evidence":[{"doc_id":did,"sent_id":i} for i in range(len(sentences))]})
            head=tail
        relation_text = "的".join(f"「{e[0]}」" for e in edges)
        question = convert(f"依據給定《三國演義》原文片段（合成附錄不屬原著人物），{start}的{relation_text}是誰或什麼？")
        if converter:
            question = NATURAL_QUESTIONS[seed]
        entities = [start,*[e[1] for e in edges]]
        base={"schema_version":"0.2","sample_id":"","seed_id":seed,"source_cluster":cluster,"pair_id":None,"split":"dev_public","origin":"native_zh","domain":"classical_literature_narrative","variant":"gold_only","question":question,"question_language":"zh","hop_count":len(edges),"documents":documents,"answer":{"text":head,"aliases":[a for a in aliases[head] if len(a)>1],"type":"entity"},"entity_aliases":{e:aliases[e] for e in entities},"proofs":[{"steps":steps}],"attack":None,"provenance":{"construction_method":("assistant_frozen_natural_questions; neutral_relations_exact_qualifiers; glyph_derived_spans; synthetic_assistant_appendix; no_human_review" if converter else "assistant_candidate_questions; glyph_derived_spans; synthetic_assistant_appendix; no_human_review"),"sources":[{k:v for k,v in sources[ch].items() if k in {"source_id","url","citation","version","accessed_at","license","text_sha256"}} for ch in sorted(chapters)]},"qc":{"status":"candidate","human_verified":False,"review_ids":[]}}
        mechanisms=["false_bridge"]+(["redundant"] if seed=="s1" else [])+(["misleading_relation"] if seed=="s2" else [])
        variants=[(None,"gold_only")]+[(m,v) for m in mechanisms for v in ("clean_control","adversarial")]
        sample_ids=[]
        for mechanism, variant in variants:
            row=copy.deepcopy(base);row["variant"]=variant
            if mechanism:
                did=f"d{len(edges)+1}"
                row["documents"].append({"doc_id":did,"title":f"材料 {len(edges)+1}","language":"zh","sentences":[{"sent_id":0,"text":convert(appendix(start,[e[0] for e in edges],mechanism,variant=="adversarial"))}]})
                row["pair_id"]=f"{seed}:{mechanism}"
                if variant=="adversarial":row["attack"]={"primary_type":mechanism,"target_hop":1,"changed_sentences":[{"doc_id":did,"sent_id":0}],"source_method":"synthetic_assistant_appendix"}
            # Derive opaque identifiers exclusively from model-visible text.
            row["sample_id"]="q_"+stable_hash([row["question"],row["documents"]])[:24]
            rows.append(row);sample_ids.append(row["sample_id"])
        deletion=[]
        for step in steps:
            removed=refs(step["evidence"])
            remaining=[s for s in steps if not refs(s["evidence"]) & removed]
            # Declared chain connectivity, not a model experiment or semantic proof.
            reachable={start}
            for edge in remaining:
                if edge["head"] in reachable:reachable.add(edge["tail"])
            deletion.append({"removed_hop":step["hop"],"removed_evidence":step["evidence"],"declared_answer_reachable":head in reachable,"type":"declared_graph_only; not_semantic_certification"})
        reviews.append({"seed_id":seed,"source_cluster":cluster,"sample_ids":sample_ids,"start":start,"reference_chain":steps,"span_bindings":span_bindings,"source_documents":len(chapters),"deletion_checks":deletion,
                        "human_review":{"source_identity":"pending","pronoun_resolution":"pending","unique_answer":"pending","shortest_necessary_chain":"pending","remove_evidence_semantics":"pending","attack_excludability":"pending","naturalness_and_strength":"pending","reviewers":[]},
                        "known_risks":["single novel, three shared source-graph clusters","names/pronouns and time roles require independent review","original snippets may expose semantic shortcuts; graph checks cannot rule them out","explicit synthetic identity may make attacks weak","partial/non-contiguous source spans disclosed"]})
    return rows, reviews


def derivation_records(spans, sources, converter):
    derived = []
    for span in spans.values():
        text, changes = converter.convert(span["text"], changes=True)
        derived.append({"span_id": span["span_id"], "source_id": span["source_id"],
                        "original_text_sha256": span["text_sha256"], "text": text,
                        "text_sha256": sha_bytes(text.encode("utf-8")),
                        "profile_sha256": converter.profile["profile_sha256"], "changes": changes,
                        "presentation": "简体字形转换，非原始字节；原offset仅属于原文"})
    current_sources = copy.deepcopy(sources)
    for source in current_sources.values():
        source["citation"] = converter.convert(source["citation"])
    originals, _ = construct_rows(sources, spans)
    rows, reviews = construct_rows(current_sources, spans, converter)
    _, history = converter.aliases(ALIASES)
    bindings = []
    for original, current in zip(originals, rows):
        bindings.append({"seed_id": current["seed_id"], "variant": current["variant"], "pair_id": current["pair_id"],
                         "original_sample_id": original["sample_id"], "sample_id": current["sample_id"],
                         "original_visible_sha256": stable_hash([original["question"], original["documents"]]),
                         "visible_sha256": stable_hash([current["question"], current["documents"]]),
                         "proof_sha256": stable_hash(current["proofs"]),
                         "answer_alias_sha256": stable_hash([current["answer"], current["entity_aliases"]]),
                         "metadata_sha256": stable_hash(current["provenance"]), "sample_sha256": stable_hash(current)})
    ledger = {"version": "glyph-derivation-v1", "profile": converter.profile,
              "source_access_record_sha256": SOURCE_ACCESS_SHA256,
              "original_spans_sha256": stable_hash(list(spans.values())), "derived_spans_sha256": stable_hash(derived),
              "entities": history, "samples": bindings, "review_ledger_sha256": stable_hash(reviews),
              "display_exceptions": ["original HTML/TXT/spans and historical evidence", "source URLs, machine IDs and hashes"],
              "question_profile": "natural-compositional-v2; neutral relation and explicit qualifier; historical IDs retain pre-S1 grammar",
              "limitations": "natural questions remove explicit intermediate names; real names and source snippets may still permit knowledge shortcuts; no human semantic certification"}
    return current_sources, derived, rows, reviews, ledger


def build_pilot(root=ROOT, output=None):
    root = Path(root)
    output = Path(output) if output is not None else root/"data/pilot"
    converter = Converter(root)
    sources, paragraphs = prepare_sources(root, output)
    spans = make_spans(paragraphs, sources)
    sources, derived, rows, reviews, derivation = derivation_records(spans, sources, converter)
    audit=validate_v02(rows)
    write_jsonl(output/"samples.jsonl",rows)
    write_jsonl(output/"model-inputs.jsonl",export_inputs(rows))
    write_json(output/"source-manifest.json",list(sources.values()))
    write_json(output/"spans.json",list(spans.values()))
    write_json(output/"derived-spans.json",derived)
    write_json(output/"derivation-ledger.json",derivation)
    write_json(output/"review-ledger.json",reviews)
    write_json(output/"pair-audit.json",audit)
    write_json(output/"construction-manifest.json",{"seeds":6,"source_graph_clusters":3,"works":1,"source_chapters":7,"source_spans":len(spans),"hop_distribution":{"2":2,"3":3,"4":1},"samples":len(rows),"pairs":audit["pairs"],"formal_accepted_seeds":0,"human_review":"pending","token_counts":None,"samples_sha256":sha_bytes((output/"samples.jsonl").read_bytes()),"input_sha256":sha_bytes((output/"model-inputs.jsonl").read_bytes()),"derived_spans_sha256":sha_bytes((output/"derived-spans.json").read_bytes()),"derivation_ledger_sha256":sha_bytes((output/"derivation-ledger.json").read_bytes()),"conversion_profile_sha256":converter.profile["profile_sha256"],"source_access_record_sha256":SOURCE_ACCESS_SHA256,"method":"fixed-revision original span extraction; frozen glyph derivation; frozen natural questions; neutral relations and exact qualifiers; candidate blueprint; explicit synthetic appendix; declared graph deletion only","source_registry":"docs/plan/draft/source-snapshots/download-manifest.json"})
    return audit


def audit_pilot(root=ROOT, path=None):
    root=Path(root)
    path=Path(path) if path else root/"data/pilot"
    converter=Converter(root)
    source_access_record(path/"source-access-record.json")
    sources=json.loads((path/"source-manifest.json").read_text(encoding="utf-8"))
    paragraphs={}
    for source in sources:
        raw=(root/source["html_path"]).read_bytes()
        require(sha_bytes(raw)==source["html_sha256"],"archived HTML hash mismatch")
        text_path=path/"sources"/Path(source["text_path"]).name
        require(sha_bytes(text_path.read_bytes())==source["text_sha256"],"source text hash mismatch")
        p=Paragraphs();p.feed(raw.decode("utf-8"));paragraphs[source["source_id"]]=p.paragraphs
    spans=json.loads((path/"spans.json").read_text(encoding="utf-8"))
    for span in spans:
        paragraph=paragraphs[span["source_id"]][span["paragraph_index"]]
        require(sha_bytes(paragraph.encode("utf-8"))==span["paragraph_sha256"],"paragraph hash mismatch")
        exact=paragraph[span["char_start"]:span["char_end"]]
        require(exact==span["text"] and sha_bytes(exact.encode("utf-8"))==span["text_sha256"],"source span mismatch")
    from .io import read_jsonl
    rows=read_jsonl(path/"samples.jsonl")
    result=validate_v02(rows)
    manifest=json.loads((path/"construction-manifest.json").read_text(encoding="utf-8"))
    require(sha_bytes((path/"samples.jsonl").read_bytes())==manifest["samples_sha256"],"dataset hash mismatch")
    require(sha_bytes((path/"model-inputs.jsonl").read_bytes())==manifest["input_sha256"],"input hash mismatch")
    require(read_jsonl(path/"model-inputs.jsonl")==export_inputs(rows),"exported model inputs differ")
    expected_sources, parsed = prepare_sources(root, path, write=False)
    expected_spans = make_spans(parsed, expected_sources)
    require(spans == list(expected_spans.values()), "original span registry differs from fixed extraction")
    expected_span_bytes = (json.dumps(list(expected_spans.values()), ensure_ascii=False, indent=2)+"\n").encode("utf-8")
    require((path/"spans.json").read_bytes() == expected_span_bytes, "original span bytes mismatch")
    expected_sources, derived, expected_rows, expected_reviews, derivation = derivation_records(expected_spans, expected_sources, converter)
    require(sources == list(expected_sources.values()), "source metadata differs from fixed derivation")
    require(json.loads((path/"derived-spans.json").read_text(encoding="utf-8")) == derived, "derived spans mismatch")
    require(json.loads((path/"derivation-ledger.json").read_text(encoding="utf-8")) == derivation, "derivation ledger mismatch")
    require(rows == expected_rows, "converted sample/proof/alias/metadata mismatch")
    require(manifest["conversion_profile_sha256"] == converter.profile["profile_sha256"], "conversion profile hash mismatch")
    require(manifest["source_access_record_sha256"] == SOURCE_ACCESS_SHA256, "source access record manifest mismatch")
    require(manifest["derived_spans_sha256"] == sha_bytes((path/"derived-spans.json").read_bytes()), "derived spans file hash mismatch")
    require(manifest["derivation_ledger_sha256"] == sha_bytes((path/"derivation-ledger.json").read_bytes()), "derivation ledger file hash mismatch")
    bound={s["span_id"]:s for s in derived}
    ledger=json.loads((path/"review-ledger.json").read_text(encoding="utf-8"))
    require(ledger == expected_reviews, "review ledger differs from fixed derivation")
    by_seed={s["seed_id"]:s for s in rows if s["variant"]=="gold_only"}
    require(len(ledger)==len(by_seed) and {r["seed_id"] for r in ledger}==set(by_seed),"review ledger seed coverage mismatch")
    source_by_id={s["source_id"]:s for s in sources}
    for row in rows:
        for source in row["provenance"]["sources"]:
            require(source["source_id"] in source_by_id and source=={k:source_by_id[source["source_id"]][k] for k in source},"sample source metadata differs from source registry")
    for review in ledger:
        sample=by_seed[review["seed_id"]]
        sample_text={(d["doc_id"],s["sent_id"]):s["text"] for d in sample["documents"] for s in d["sentences"]}
        require({(b["doc_id"],b["sent_id"]) for b in review["span_bindings"]}==set(sample_text),"gold text span coverage mismatch")
        require(review["reference_chain"]==sample["proofs"][0]["steps"],"review chain differs from sample proof")
        for binding in review["span_bindings"]:
            require(sample_text[binding["doc_id"],binding["sent_id"]]==bound[binding["span_id"]]["text"],"sample does not equal glyph-derived source span")
        require(len(review["deletion_checks"])==sample["hop_count"],"deletion record coverage mismatch")
        for step,check in zip(review["reference_chain"],review["deletion_checks"]):
            require(check["removed_hop"]==step["hop"] and check["removed_evidence"]==step["evidence"],"deletion record mismatch")
            reachable={review["start"]}
            removed=refs(step["evidence"])
            for edge in review["reference_chain"]:
                if not refs(edge["evidence"]) & removed and edge["head"] in reachable:reachable.add(edge["tail"])
            actual=sample["answer"]["text"] in reachable
            require(actual==check["declared_answer_reachable"] and not actual,"declared graph has deletion shortcut")
        require(sample["qc"]=={"status":"candidate","human_verified":False,"review_ids":[]},"pilot must remain unreviewed candidate")
    result.update({"source_spans_verified":len(spans),"derived_spans_verified":len(derived),"source_access_record_sha256":SOURCE_ACCESS_SHA256,"conversion_profile_sha256":converter.profile["profile_sha256"],"source_chapters_verified":len(sources),"works":1,"human_review":"pending","semantic_necessity":"not_certified"})
    return result
