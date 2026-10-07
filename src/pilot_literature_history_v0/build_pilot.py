"""Build the initial candidate set; no model invocation or human-review claim.

Specification: [data README](../../data/pilot_literature_history_v0/README.md).
Inputs: [combinations](../../data/pilot_literature_history_v0/combinations.json),
[source snapshots](../../data/pilot_literature_history_v0/sources.json).
Outputs and machine path strings are documented in that README.
Protocol: [multi-step assessment](../../docs/benchmark-survey/09_多步骤评判与核心创新点回收.md).
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from original_materials import CONFIG as MATERIAL_CONFIG, render_originals, validate_materials

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "pilot_literature_history_v0"
TEMP = ROOT / "workspace" / "pilot_literature_history_v0"
SEED = 20261007
VERSION = "pilot-v0.4"
PRIMARY_VARIANTS = ("challenge", "anonymous_challenge", "unfamiliar_challenge")
# One surface form per family; substantive interventions remain independent records.
PRIMARY_BY_FAMILY = {
    "F-C01-H": "unfamiliar_challenge", "F-C01-L": "anonymous_challenge",
    "F-C02-H": "anonymous_challenge", "F-C02-L": "unfamiliar_challenge",
    "F-C03-H": "challenge", "F-C03-L": "anonymous_challenge",
    "F-C04-H": "challenge", "F-C04-L": "challenge",
    "F-C05-H": "unfamiliar_challenge", "F-C05-L": "challenge",
    "F-C06-H": "anonymous_challenge", "F-C06-L": "unfamiliar_challenge",
    "F-C07-H": "challenge", "F-C07-L": "challenge",
    "F-C08-H": "challenge", "F-C08-L": "challenge",
    "F-C09-H": "unfamiliar_challenge", "F-C09-L": "anonymous_challenge",
    "F-C10-H": "anonymous_challenge", "F-C10-L": "unfamiliar_challenge",
}

def select_primary_variants(rows):
    selected = []
    for row in rows:
        keep = PRIMARY_BY_FAMILY[row["family_id"]]
        if row["variant"] in PRIMARY_VARIANTS and row["variant"] != keep:
            continue
        if row["variant"] == "anonymous_control":
            continue
        row = copy.deepcopy(row)
        row["version"] = VERSION
        primary = next(r for r in rows if r["family_id"] == row["family_id"] and r["variant"] == keep)
        row["challenge_id"] = primary["id"]
        if row["variant"] == "no_context":
            row["input"]["question"] = primary["input"]["question"]
            row["query"] = copy.deepcopy(primary["query"])
            row["entity_mapping"] = copy.deepcopy(primary["entity_mapping"])
            row["construction"]["naming"] = primary["construction"]["naming"]
        reference = row["construction"]["comparison_reference"]
        if row["variant"] == keep:
            reference = "control"
        elif reference == "challenge":
            reference = keep
        row["construction"]["comparison_reference"] = reference
        selected.append(row)
    for row in selected:
        reference = row["construction"]["comparison_reference"]
        if not reference:
            row["paired_changes"] = None
            continue
        parent = next(r for r in selected if r["family_id"] == row["family_id"] and r["variant"] == reference)
        before = {f["fact_id"]: f for f in parent["facts"]}
        after = {f["fact_id"]: f for f in row["facts"]}
        row["paired_changes"] = {"parent_id": parent["id"],
            "added_fact_ids": sorted(set(after)-set(before)),
            "removed_fact_ids": sorted(set(before)-set(after)),
            "rewritten_fact_ids": sorted(k for k in set(before)&set(after) if before[k]!=after[k]),
            "question_changed": parent["input"]["question"] != row["input"]["question"],
            "answer_changed": parent["gold"]["answers"] != row["gold"]["answers"],
            "status_changed": parent["gold"]["status"] != row["gold"]["status"]}
    return selected

def validate_selection(rows, sources):
    ids = {r["id"] for r in rows}
    assert len(ids) == len(rows) == 86
    quotes = {q["quote_id"] for s in sources for q in s["quotes"]}
    for r in rows:
        validate_record(r, quotes)
        assert r["control_id"] in ids and r["challenge_id"] in ids
        if r["paired_changes"]:
            assert r["paired_changes"]["parent_id"] in ids
    for family, keep in PRIMARY_BY_FAMILY.items():
        group = [r for r in rows if r["family_id"] == family]
        assert [r["variant"] for r in group if r["variant"] in PRIMARY_VARIANTS] == [keep]
        assert any(r["variant"] == "control" for r in group)
        target = next(r for r in group if r["variant"] == keep)
        empty = next(r for r in group if r["variant"] == "no_context")
        assert empty["input"]["question"] == target["input"]["question"]
        assert not empty["input"]["documents"]
        assert target["paired_changes"]["parent_id"] == target["control_id"]
    assert Counter(r["domain"] for r in rows) == {"history": 43, "literature": 43}
POLICY = (
    "只依据本题材料回答。材料限定一个叙事或档案世界，可能含编者设定，"
    "不能用熟悉的作品、史书或现实知识覆盖材料，也不能补齐缺失关系。"
    "关系只按明确语义和给出的规则组合，不默认逆命题、因果或传递性。"
    "可答时给答案、支持材料ID和简短的关系/操作步骤；"
    "多种题意时列出解释与答案；缺依据时说明信息不足。"
)
CONTRACT = {"answer": "字符串或完整答案列表", "status": "answerable/ambiguous/insufficient",
            "evidence_ids": "引用的材料ID列表", "steps": "简短关系或操作记录，不要求自由长篇思维链"}

def digest(value):
    data = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

def fact(fid, subject, relation, obj, quote=None, text=None, dtype="entity", period=None):
    if text is None:
        prefix = f"本题馆年{period[0]}至{period[1]}年（含端点），" if period else ""
        text = prefix + f"{subject}的{relation}是{obj}。"
    return {"fact_id": fid, "subject": subject, "relation": relation, "object": obj,
            "text": text,
            "datatype": dtype, "period": period,
            "provenance": "source_paraphrase" if quote else "synthetic_editor_setting",
            "quote_ids": [quote] if quote else []}

def walk(start, *relations, time=None):
    return {"kind": "walk", "start": start,
            "relations": [{"relation": r[1:], "direction": "in"} if r.startswith("^")
                          else {"relation": r, "direction": "out"} for r in relations],
            "time": time}

def step(node, answer, supports, dependencies=None, operation="lookup", **extra):
    return {"node_id": node, "operation": operation, "expected_value": answer,
            "support_fact_ids": supports, "dependencies": dependencies or [], **extra}

def walk_paths(query, facts):
    paths = [(query["start"], [])]
    for index, rel in enumerate(query["relations"], 1):
        result = []
        for cursor, prior in paths:
            for f in facts:
                if f["relation"] != rel["relation"]:
                    continue
                start_key, end_key = ("subject", "object") if rel["direction"] == "out" else ("object", "subject")
                if f[start_key] != cursor:
                    continue
                period = f.get("period")
                if period and query.get("time") is not None and not(period[0] <= query["time"] <= period[1]):
                    continue
                value = f[end_key]
                result.append((value, prior + [step(f"n{index}", value, [f["fact_id"]],
                             [f"n{index-1}"] if index > 1 else [], relation=f["relation"],
                             direction=rel["direction"], upstream=cursor)]))
        paths = result
    return paths

def solve(query, facts):
    kind = query["kind"]
    if kind == "walk":
        paths = walk_paths(query, facts)
        answers = list(dict.fromkeys(value for value, _ in paths))
        return {"status": "answerable" if answers else "insufficient",
                "answers": answers, "proofs": [p for _, p in paths], "interpretations": []}
    if kind == "ambiguous":
        interpretations, proofs = [], []
        for alternative in query["alternatives"]:
            solved = solve(alternative["query"], facts)
            assert solved["status"] == "answerable"
            if query.get("alias"):
                identity=alternative["query"]["start"]
                alias_fact=next(f for f in facts if f["relation"]=="别名" and
                                f["subject"]==identity and f["object"]==query["alias"])
                revised=[]
                for proof in solved["proofs"]:
                    proof=copy.deepcopy(proof)
                    proof[0]["dependencies"]=["alias"]
                    revised.append([step("alias",identity,[alias_fact["fact_id"]],
                                         operation="resolve_alias",upstream=query["alias"],
                                         relation="别名",direction="in")]+proof)
                solved["proofs"]=revised
            interpretations.append({"label": alternative["label"], "answers": solved["answers"]})
            proofs.extend(solved["proofs"])
        return {"status": "ambiguous", "answers": list(dict.fromkeys(
                a for i in interpretations for a in i["answers"])), "proofs": proofs,
                "interpretations": interpretations}
    if kind == "compare":
        left = walk_paths(query["left"], facts)
        right = walk_paths(query["right"], facts)
        assert len(left) == len(right) == 1
        lv, lp = left[0]
        rv, rp = right[0]
        assert lv != rv, "No unlabelled ties"
        winning = lp if lv < rv else rp
        answer = winning[0]["expected_value"]
        nodes = []
        for prefix, proof in [("L", lp), ("R", rp)]:
            for item in proof:
                item = copy.deepcopy(item)
                item["node_id"] = prefix + item["node_id"]
                item["dependencies"] = [prefix + d for d in item["dependencies"]]
                nodes.append(item)
        nodes.append(step("compare", answer, [], ["L" + lp[-1]["node_id"], "R" + rp[-1]["node_id"]],
                          operation="earlier_than", compared_values=[lv, rv]))
        return {"status": "answerable", "answers": [answer], "proofs": [nodes], "interpretations": []}
    if kind == "sum_join":
        roster = [f for f in facts if f["subject"] == query["group"] and f["relation"] == "全部成员之一"]
        closure = next(f for f in facts if f["subject"] == query["group"] and f["relation"] == "名录完整")
        members = {f["object"] for f in roster}
        table_scope = next(f for f in facts if f["relation"] == "表列范围完整")
        nodes = [step("scope", query["items"], [table_scope["fact_id"]], operation="enumerate_scope"),
                 step("roster", sorted(members), [closure["fact_id"]] + [r["fact_id"] for r in roster],
                      operation="read_complete_roster")]
        totals = []
        for i, item in enumerate(query["items"]):
            author = next(f for f in facts if f["subject"] == item and f["relation"] == "作者")
            node = f"author{i}"
            nodes.append(step(node, author["object"], [author["fact_id"]], ["scope"]))
            selected = author["object"] in members
            nodes.append(step(f"filter{i}", selected, [], [node, "roster"], operation="member_test"))
            if selected:
                size = next(f for f in facts if f["subject"] == item and f["relation"] == "统计页数")
                totals.append(size["object"])
                nodes.append(step(f"pages{i}", size["object"], [size["fact_id"]],
                                  [f"filter{i}"], operation="read_pages"))
        nodes.append(step("sum", sum(totals), [], [n["node_id"] for n in nodes if n["node_id"].startswith("pages")],
                          operation="sum", unit="页"))
        return {"status": "answerable", "answers": [sum(totals)], "proofs": [nodes], "interpretations": []}
    if kind in ("entailment", "abduction"):
        book_paths = walk_paths(query["prefix"], facts)
        assert len(book_paths) == 1
        book, prefix = book_paths[0]
        rule = next(f for f in facts if f["relation"] == "规定收藏处")
        stamp = [f for f in facts if f["subject"] == book and f["relation"] == "带印"]
        if kind == "entailment":
            expected = "是" if any(f["object"] == rule["subject"] for f in stamp) else "不确定"
            observation = [f for f in facts if f["subject"] == book and f["relation"] == "已收藏处"]
            nodes = prefix + [step("check", expected, [rule["fact_id"]] +
                                  [f["fact_id"] for f in observation + stamp],
                                  [prefix[-1]["node_id"]], operation="open_world_entailment")]
            return {"status": "answerable", "answers": [expected], "proofs": [nodes],
                    "interpretations": [], "logical_truth": "true" if expected == "是" else "unknown"}
        # Explicitly bounded one-fact abduction, not arbitrary explanation.
        assumptions = [c for c in query["candidates"] if c["subject"] == book and
                       c["relation"] == "带印" and c["object"] == rule["subject"]]
        assert len(assumptions) == 1
        hypothesis = assumptions[0]
        answer = f"{book}带{hypothesis['object']}"
        nodes = prefix + [step("assume", answer, [], [prefix[-1]["node_id"]], operation="hypothesis"),
                          step("derive", query["goal"], [rule["fact_id"]], ["assume"],
                               operation="forward_rule_application")]
        return {"status": "answerable", "answers": [answer], "proofs": [nodes], "interpretations": [],
                "hypotheses": assumptions}
    raise ValueError(kind)

def depth(proof):
    depths = {}
    for node in proof:
        depths[node["node_id"]] = 1 + max((depths[d] for d in node["dependencies"]), default=0)
    return max(depths.values(), default=0)

def make_seed(combo, domain, question, query, core, target, scenes, decoys, risks, source_cluster):
    return {"family_id": f"F-{combo}-{domain}", "combination_id": combo,
            "domain": "literature" if domain == "L" else "history", "question": question,
            "query": query, "core_facts": core, "target_facts": target,
            "base_scene_ids": scenes, "decoy_answers": decoys,
            "knowledge_risks": risks, "source_cluster_id": source_cluster}

def source_seeds():
    seeds = []
    def add(*args): seeds.append(make_seed(*args))
    # C01: related but query-incompatible actor/condition branches.
    core = [
        fact("a", "赤兔", "该次送礼人", "李肃", "L1-B", "赤兔在该次馈赠中的送礼人是李肃。"),
        fact("b", "李肃", "该次引见将领", "吕布", "L1-D"),
        fact("c", "吕布", "该次拜认义父", "董卓", "L1-E")]
    branch = [
        fact("x", "赤兔", "该次讨论用马者", "李儒", "L1-A"),
        fact("y", "李儒", "献策对象", "董卓", "L1-A"),
        fact("z", "董卓", "弟弟", "董旻", "L1-F")]
    add("C01","L","赤兔在该次馈赠中的送礼人所引见的将领，这次拜认的义父是谁？",
        walk("赤兔","该次送礼人","该次引见将领","该次拜认义父"),core,core+branch,["S01"],
        ["董旻","李儒"],["赤兔与吕布的熟悉剧情","中间姓名或人物称号可能唤起知识"],"SRC-L1")
    core = [
        fact("a","项梁","拘捕求书之人","曹咎","H1-B"),
        fact("b","曹咎","该信收信人","司马欣","H1-B"),
        fact("c","司马欣","狱掾官署所在地","栎阳","H1-B")]
    branch = [fact("x","曹咎","狱掾官署所在地","蕲","H1-B"),
              fact("y","项梁","避仇同行者","项籍","H1-C"),
              fact("z","项籍","籍贯","下相","H1-A")]
    add("C01","H","项梁因拘捕求书之人所写的那封信，其收信人任职官署位于哪里？",
        walk("项梁","拘捕求书之人","该信收信人","狱掾官署所在地"),core,core+branch,["S01"],
        ["蕲","下相"],["人物名、官职和史记固定叙事可能触发记忆"],"SRC-H1")
    # C04: duplicated statement is not an independent source, but is alternative support.
    lcore = [fact("a","孙悟空","拜见的师父","须菩提祖师","L2-D"),
             fact("b","须菩提祖师","居住洞府","斜月三星洞","L2-C"),
             fact("c","斜月三星洞","所在山","灵台方寸山","L2-C")]
    ldup = fact("b2","须菩提祖师","居住洞府","斜月三星洞","L2-C",
                "斜月三星洞是须菩提祖师的洞府。")
    add("C04","L","孙悟空所拜见师父的洞府位于哪座山？",
        walk("孙悟空","拜见的师父","居住洞府","所在山"),lcore,lcore+[ldup],["S01"],
        ["花果山"],["祖师与洞府名称之间有强记忆关联"],"SRC-L2")
    hcore = [fact("a","项籍","季父","项梁","H1-A"),
             fact("b","项梁","父亲","项燕","H1-A"),
             fact("c","项燕","杀害者","王翦","H1-A","记载中，项燕为秦将王翦所杀。")]
    hdup = fact("b2","项梁","父亲","项燕","H1-A","项燕是项梁的父亲。")
    add("C04","H","项籍季父的父亲，记载为哪位秦将所杀？",
        walk("项籍","季父","父亲","杀害者"),hcore,hcore+[hdup],["S01"],
        ["章邯"],["项羽家系与名将事实可直接背出"],"SRC-H1")
    lcore = [fact("a","李肃","该次引见将领","吕布","L1-D"),
             fact("b","吕布","该次拜认义父","董卓","L1-E"),
             fact("c","董卓","弟弟","董旻","L1-F")]
    add("C05","L","李肃该次引见的将领所拜认义父的弟弟是谁？",
        walk("李肃","该次引见将领","该次拜认义父","弟弟"),lcore,lcore,["S01"],[],
        ["熟悉人物家系；逆关系不能按同一谓词反读"],"SRC-L1")
    add("C05","H","项籍季父的父亲的杀害者是谁？",
        walk("项籍","季父","父亲","杀害者"),hcore,hcore,["S01"],[],
        ["同一史料图在不同题目中复用，不能视为独立来源"],"SRC-H1")
    lcore = [fact("a","孙悟空","出生山","花果山","L2-B"),
             fact("b","花果山","国界归属","傲来国","L2-A"),
             fact("c","傲来国","部洲","东胜神洲","L2-A")]
    add("C07","L","孙悟空出生山所在国界对应哪个部洲？",
        walk("孙悟空","出生山","国界归属","部洲"),lcore,lcore,["S01"],
        ["灵台方寸山"],["出生地与求道地易串线；剧名和名号暗示答案"],"SRC-L2")
    hcore = [fact("a","张楚","称王者","陈胜","H2-C"),
             fact("b","陈胜","所任假王","吴广","H2-D"),
             fact("c","吴广","籍贯","阳夏","H2-A")]
    add("C07","H","张楚称王者所任假王的籍贯在哪里？",
        walk("张楚","称王者","所任假王","籍贯"),hcore,hcore,["S01"],
        ["阳城"],["陈涉、吴叔等别称及张楚知识能绕开材料"],"SRC-H2")
    # C08 explicitly mixes a source-derived branch and a fictional comparison branch.
    lcore = [fact("a","孙悟空","师父","须菩提祖师","L2-D"),
             fact("b","须菩提祖师","居住洞府","斜月三星洞","L2-C"),
             fact("c","斜月三星洞","所在山","灵台方寸山","L2-C"),
             fact("d","夜禾","师父","青砚子"),fact("e","青砚子","居住洞府","照云洞"),
             fact("f","照云洞","所在山","玄栈山")]
    add("C08","L","按本题世界，孙悟空师父的洞府位于哪座山？",
        walk("孙悟空","师父","居住洞府","所在山"),lcore,lcore,["S01"],
        ["灵台方寸山"],["须菩提与方寸山的记忆会与改接后材料冲突"],"MIXED-L2-C08")
    hcore = [fact("a","项籍","季父","项梁","H1-A"),
             fact("b","项梁","父亲","项燕","H1-A"),
             fact("c","项燕","杀害者","王翦","H1-A"),
             fact("d","白洵","季父","卫嶂"),fact("e","卫嶂","父亲","萧圻"),
             fact("f","萧圻","杀害者","庞崖")]
    add("C08","H","按本题世界，项籍季父的父亲的杀害者是谁？",
        walk("项籍","季父","父亲","杀害者"),hcore,hcore,["S01"],
        ["王翦"],["历史家系答案应随材料改接，不能凭记忆坚持旧答案"],"MIXED-H1-C08")
    return seeds

def synthetic_seeds():
    seeds = []
    for domain in ("L","H"):
        literary = domain == "L"
        # C02 bridges to people, then compares the actual formal event dates.
        a,b = ("霜河记","灯山集") if literary else ("北关仪式","南关仪式")
        p,q,x,y = ("霁川","浦溪","照岑","暮渚") if literary else ("衡岳","沧衡","文嶂","弥川")
        r = "正式编定者" if literary else "正式主使"
        date = "正式就任月份"
        formal_months=(9,11) if literary else (10,7)
        core = [fact("a",a,r,p),fact("b",p,date,formal_months[0],dtype="number"),
                fact("c",b,r,q),fact("d",q,date,formal_months[1],dtype="number")]
        extra = [fact("x",a,"试行负责人",x),fact("y",x,"试行就任月份",12,dtype="number"),
                 fact("z",b,"试行负责人",y),fact("w",y,"试行就任月份",2,dtype="number")]
        query = {"kind":"compare","left":walk(a,r,date),"right":walk(b,r,date)}
        seeds.append(make_seed("C02",domain,f"本题同年，{a}与{b}的{r}中，谁的{date}更早？",
                    query,core,core+extra,["S04","S24"],[y],
                    ["虚构事件控制熟悉度；需分清正式与试行"],f"SYN-C02-{domain}"))
        # C03: same alias, distinct identities, distinct legal paths.
        alias = "子衡" if literary else "沈恒"
        role1,role2 = ("校勘者","抄手") if literary else ("史官","武官")
        one,two = f"{alias}（{role1}）",f"{alias}（{role2}）"
        g1,g2,head1,head2,room1,room2 = ("听雪馆","照溪馆","岑照","澜素","松窗","竹轩")
        core = [fact("a",one,"别名",alias),fact("b",two,"别名",alias),
                fact("c",one,"所属馆",g1),fact("d",g1,"馆长",head1),fact("e",head1,"书房",room1),
                fact("f",two,"所属馆",g2),fact("g",g2,"馆长",head2),fact("h",head2,"书房",room2)]
        seeds.append(make_seed("C03",domain,f"{one}所属馆的馆长使用哪间书房？",
                    walk(one,"所属馆","馆长","书房"),core,core,["S01","S18"],[room2],
                    ["匿名化不能消除指代/身份歧义；两身份必须分别映射"],f"SYN-C03-{domain}"))
        # C06: a complete table and complete member roster make filtering/aggregation decidable.
        works = ["霜林稿","听泉录","南桥序"] if literary else ["关防册","郡兵簿","渡口志"]
        authors = ["汀和","谷舟","澜序"] if literary else ["陆简","沈珩","章砚"]
        group = "甲组"
        core = [fact("scope","本题卷本表","表列范围完整",True,dtype="boolean",
                     text="本题卷本表的三条卷本是全部统计对象，页数单位均为页。"),
                fact("complete",group,"名录完整",True,dtype="boolean",
                     text=f"本题所列{group}成员条目构成完整名录，没有未列出的该组成员。"),
                fact("m1",group,"全部成员之一",authors[0]),fact("m2",group,"全部成员之一",authors[1])]
        page_counts=[10,14,90] if literary else [8,17,75]
        for i,(work,author,pages) in enumerate(zip(works,authors,page_counts)):
            core.extend([fact(f"a{i}",work,"作者",author),
                         fact(f"p{i}",work,"统计页数",pages,dtype="number",
                              text=f"卷本表行：作品={work}；页数={pages}页。")])
        extra = [fact("x",authors[2],"乙组成员",True,dtype="boolean"),
                 fact("y",works[2],"评奖组关联",group,
                      text=f"{works[2]}曾由{group}评奖；评奖不表示作者是成员。")]
        query={"kind":"sum_join","group":group,"items":works}
        seeds.append(make_seed("C06",domain,"本题卷本表中，作者属于甲组的卷本合计多少页？",
                    query,core,core+extra,["S05","S06","S07","S32"],[sum(page_counts),page_counts[2]],
                    ["完整名录是任务设定，不根据史书未提到某人推断否定"],f"SYN-C06-{domain}"))
        # C09: fixed forward rules; reverse inference is unknown, abduction is hypothetical.
        person = "明昙" if literary else "墨原"
        book = "绛雪稿" if literary else "关防副册"
        group = "东阁" if literary else "北府"
        core = [fact("a",person,"校定卷",book),
                fact("b",book,"带印","朱印"),
                fact("c","朱印","规定收藏处",group,
                     text=f"本题规则：凡带朱印的卷本都收入{group}；没有声明逆向规则。")]
        seeds.append(make_seed("C09",domain,f"{person}校定的卷本按本题印记规则应收入哪里？",
                    walk(person,"校定卷","带印","规定收藏处"),core,core,["S03"],
                    ["青印"],["规则世界不借助现实藏书或印章知识"],f"SYN-C09-{domain}"))
        # C10: time-qualified bridge plus hierarchical if-conditions.
        book="寒桥札" if literary else "边郡副志"
        person1,person2="昔闻","青河"
        g1,g2="承露馆","听潮馆"
        periods=([1,3],[4,6]) if literary else ([4,6],[1,3])
        core=[fact("a",book,"当期校勘者",person1,period=periods[0]),
              fact("b",book,"当期校勘者",person2,period=periods[1]),
              fact("c",person1,"所属馆",g1),fact("d",person2,"所属馆",g2),
              fact("e",g1,"所属区","东区"),fact("f",g2,"所属区","西区"),
              fact("g","东区","首抄归档册","甲册",text="本题规则：首抄卷本若校勘馆属东区，归甲册。"),
              fact("h","西区","首抄归档册","乙册",text="本题规则：首抄卷本若校勘馆属西区，归乙册。"),
              fact("i","复抄","归档册","丙册",text="本题规则：复抄卷本无论馆区一律归丙册；以下问题指定首抄。")]
        extra=[fact("x",book,"当期复核者","浦遥",period=[4,6]),
               fact("y","浦遥","所属馆",g1)]
        query=walk(book,"当期校勘者","所属馆","所属区","首抄归档册",time=4)
        seeds.append(make_seed("C10",domain,f"按本题馆年4，{book}作为首抄卷本，应依据当期校勘者所属馆归入哪册？",
                    query,core,core+extra,["S01","S24","S25","S27"],["甲册" if literary else "乙册","丙册"],
                    ["合成馆年不等于真实历史年份；时间与复核/校勘角色分开"],f"SYN-C10-{domain}"))
    return seeds

SCENE_NOTES = {
    "S01":"逐跳查询 typed 关系，后跳用前跳结果。",
    "S03":"只沿题目明确给出的正向规则组合。",
    "S04":"分别取两侧负责人和日期，再比较。",
    "S05":"按完整成员名录筛选作者。",
    "S06":"遍历全部卷本及合格作者后聚合。",
    "S07":"已连接到页数后求和，单位为页。",
    "S08":"追加古籍原文背景；记录字符数，未冒称模型长窗验证。",
    "S09":"干扰分支共享实体，但使用非目标关系。",
    "S10":"同一事实有两处合法支持，接受任一完整证明。",
    "S12":"错用角色或正式/试行条件可形成另一条关联链。",
    "S13":"同类型人物可作错误中间节点，但关系不匹配。",
    "S15":"改写材料中的内部桥，不按现实记忆覆盖。",
    "S16":"当前历史原文的完整支持分布在噪声前、中、后；同段多跳不假装独立文档。",
    "S17":"背景重复；顺序变体只重排相同材料。",
    "S18":"同别名对应不同带角色身份，不能混成一人。",
    "S19":"沿事实的合法逆方向查前驱，非对称谓词。",
    "S20":"同材料匹配正向/逆向访问。",
    "S21":"仅有充分条件与结果，不足以推出前提。",
    "S22":"从两个允许假设中找能证明目标的最小单事实补充。",
    "S23":"开放世界的未知不同于否定或缺失任务材料。",
    "S24":"显式月份或闭合时间区间。",
    "S25":"同题换参考馆年，应沿当期校勘者更新。",
    "S26":"列出身份/时间解释及各自答案。",
    "S27":"先取当期校勘者、馆区，再应用首抄分支。",
    "S28":"无材料或全部桥接支持已删，保留末端也不能补链。",
    "S30":"内部桥更新后，下游结论必须同步改变。",
    "S32":"卷本表的作者列连接表外成员名录，再筛选页数。"
}

ATTACK_DESIGNS = {
    "C01":{"target_failure":"角色错配、同类型人物误接或答案对而依据错",
           "predicted_error_path":["在第一跳改用共享实体的非目标角色","沿其相关活动/官署关系继续","返回无关端点或碰巧相同答案"],
           "acceptance":"目标关系链完整；共享答案也不得用错误起点/角色证明。"},
    "C02":{"target_failure":"正式/试行角色错配及日期误比较",
           "predicted_error_path":["取试行负责人","取该人的月份","与正式负责人混合比较"],
           "acceptance":"两边均定位正式负责人，比较相同年和月份粒度。"},
    "C03":{"target_failure":"同名人物合并、歧义题强选单解",
           "predicted_error_path":["将别名当唯一身份","任取一个馆","只报告一间书房"],
           "acceptance":"分别引用身份对应的别名事实，列解释—答案；清晰身份题仅答该身份。"},
    "C04":{"target_failure":"把句级删除当事实级删除，或从记忆补齐断桥",
           "predicted_error_path":["只认固定参考句","删一处即拒答或删全部仍猜端点"],
           "acceptance":"删一处仍可答；删全部桥接支持才不足；删无关项保持。"},
    "C05":{"target_failure":"把有向关系当对称，或逆向访问漏前驱",
           "predicted_error_path":["以终点作主语沿原谓词正向读","猜熟悉的另一家系人物"],
           "acceptance":"相同事实逆序查合法前驱；正反题分别匹配起点和证明。"},
    "C06":{"target_failure":"评奖关联代替作者成员关系，漏分支或加总错误",
           "predicted_error_path":["根据作品评奖组直接选卷本","把非成员作者的卷本也纳入","得到错误总页数"],
           "acceptance":"表格作者列连接完整名录，逐条筛选再求和。"},
    "C07":{"target_failure":"长背景造成漏桥、重复频率或位置偏置",
           "predicted_error_path":["跳过远隔支持","将重复背景当优先事实","凭熟悉叙事补终点"],
           "acceptance":"各长度档和重排均用完整合法链保持答案；未做token匹配因果结论。"},
    "C08":{"target_failure":"坚持熟悉事实、忽略问题起点或只扫显眼端点",
           "predicted_error_path":["内部桥已经改接","继续沿记忆中的旧桥","输出旧终点；或换起点仍给同证明"],
           "acceptance":"双边交换后答案更新，保留度数；同答案两题须分别交出合法证明。"},
    "C09":{"target_failure":"肯定后件、未知当否定，或把溯因假设当事实",
           "predicted_error_path":["见已收藏处与正向规则","无逆向规则仍判必然带朱印"],
           "acceptance":"逆推问不确定；溯因只选允许的最小补充，并明确假设。"},
    "C10":{"target_failure":"旧任期、复核角色或复抄规则覆盖目标条件",
           "predicted_error_path":["取旧年校勘者/当期复核者","进入错误馆区","返回旧任期或错误分支的归档册；也可能碰巧同答案而依据错"],
           "acceptance":"按有效任期和首抄条件；换年更新，漏年报告解释。"}
}

def variant(seed, name, facts=None, query=None, question=None, scenes=None, **extra):
    return {"name":name, "facts":copy.deepcopy(facts if facts is not None else seed["target_facts"]),
            "query":copy.deepcopy(query if query is not None else seed["query"]),
            "question":question or seed["question"],
            "scene_ids":scenes if scenes is not None else seed["base_scene_ids"], **extra}

def identity_map(seed, mode):
    entities = {f["subject"] for f in seed["target_facts"]}
    entities.update(f["object"] for f in seed["target_facts"] if f["datatype"] == "entity")
    rng=random.Random(int(digest(seed["family_id"] + str(SEED))[:16],16))
    entities=sorted(entities)
    rng.shuffle(entities)
    # Opaque random codes do not encode hop order, role or answer status.
    codes=rng.sample(range(0x1000,0xffff),len(entities))
    if mode=="anonymous":
        mapping = {e:f"实体_{c:04X}" for e,c in zip(entities,codes)}
    chars="岚澄霁漪砚汀翎棠柚峤珩洵韶荻皎芷岑澜漱栩"
    names=[]
    while len(names)<len(entities):
        name="".join(rng.choice(chars) for _ in range(3))
        if name not in names and name not in entities:
            names.append(name)
    if mode != "anonymous":
        mapping = dict(zip(entities,names))
    # Keep prior assignments stable. Category words are not proper names;
    # supplementary people appearing only in source context get their own codes.
    for term in MATERIAL_CONFIG.get("preserved_category_terms", []):
        mapping.pop(term, None)
    extra_rng = random.Random(int(digest(seed["family_id"] + "source-context" + mode)[:16], 16))
    for entity in MATERIAL_CONFIG.get("supplementary_entities_by_family", {}).get(seed["family_id"], []):
        if entity in mapping:
            continue
        while True:
            candidate = (f"实体_{extra_rng.randrange(0x1000, 0xffff):04X}" if mode == "anonymous"
                         else "".join(extra_rng.choice(chars) for _ in range(3)))
            if candidate not in mapping.values() and candidate not in entities:
                mapping[entity] = candidate
                break
    return mapping

def replace_entities(value, mapping):
    if isinstance(value,str):
        if not mapping: return value
        pattern="|".join(re.escape(s) for s in sorted(mapping,key=len,reverse=True))
        return re.sub(pattern,lambda m:mapping[m.group()],value)
    if isinstance(value,list): return [replace_entities(v,mapping) for v in value]
    if isinstance(value,dict):
        # Relations and structural IDs are not entity names. Quote provenance stays in the audit view.
        return {k:(v if k in ("relation","fact_id","quote_ids","provenance","label")
                   else replace_entities(v,mapping)) for k,v in value.items()}
    return value

def make_variants(seed, combos):
    combo=seed["combination_id"]
    base=variant(seed,"control",facts=seed["core_facts"])
    target=variant(seed,"challenge",scenes=combos[combo]["planned_scene_ids"])
    extras=[]
    if combo=="C03":
        one,two=seed["core_facts"][0]["subject"],seed["core_facts"][1]["subject"]
        alias=seed["core_facts"][0]["object"]
        relations=[r["relation"] for r in seed["query"]["relations"]]
        target["query"]={"kind":"ambiguous","alias":alias,"alternatives":[
            {"label":one,"query":walk(one,*relations)},
            {"label":two,"query":walk(two,*relations)}]}
        target["question"]=f"档案中被称为{alias}者所属馆的馆长使用哪间书房？请给出可能的身份解释。"
        extras.append(variant(seed,"clarify_second",query=walk(two,*relations),
                      question=f"{two}所属馆的馆长使用哪间书房？",scenes=["S01","S18"]))
    elif combo=="C04":
        background=fact("neutral","封面","纸色","米白",text="封面纸色为米白；这里只记录纸色。")
        base["facts"].append(background)
        target["facts"].append(copy.deepcopy(background))
        target["scene_ids"]=["S01","S10"]
        extras.extend([
            variant(seed,"delete_one_support",facts=[f for f in target["facts"] if f["fact_id"]!="b"],scenes=["S01"]),
            variant(seed,"delete_all_bridge_supports",facts=[f for f in target["facts"] if f["fact_id"] not in ("b","b2")],scenes=["S01","S28"]),
            variant(seed,"delete_irrelevant",facts=[f for f in target["facts"] if f["fact_id"]!="neutral"],scenes=["S01","S10"])])
    elif combo=="C05":
        rels=seed["query"]["relations"]
        endpoint=solve(seed["query"],seed["core_facts"])["answers"][0]
        target["query"]={"kind":"walk","start":endpoint,"relations":[
            {"relation":r["relation"],"direction":"in"} for r in reversed(rels)],"time":None}
        target["question"]=("在该次记载中，谁引见了拜董旻之兄为义父的那位将领？"
                              if seed["domain"]=="literature" else
                              "被王翦所杀者之子，是哪个人的季父？")
    elif combo=="C07":
        target.update(noise_characters=4000)
        for length in (1000,12000):
            extras.append(variant(seed,f"noise_{length}",scenes=target["scene_ids"],noise_characters=length))
        extras.append(variant(seed,"reorder_same_noise",scenes=target["scene_ids"],
                              noise_characters=4000,reverse_documents=True))
    elif combo=="C08":
        byid={f["fact_id"]:f for f in target["facts"]}
        byid["b"]["object"],byid["e"]["object"]=byid["e"]["object"],byid["b"]["object"]
        for key in ("b","e"):
            f=byid[key]
            f["parent_quote_ids"]=f["quote_ids"]
            f["quote_ids"]=[]
            f["provenance"]="counterfactual_editor_override"
            f["text"]=f"{f['subject']}的{f['relation']}是{f['object']}。"
        target["changed_fact_ids"]=["b","e"]
        extras.append(variant(seed,"anonymous_control",facts=base["facts"],
                      scenes=base["scene_ids"],naming="anonymous"))
        other_start=byid["d"]["subject"]
        switched=copy.deepcopy(target)
        switched.update(name="switch_question_start",question=target["question"].replace(seed["query"]["start"],other_start))
        switched["query"]["start"]=other_start
        extras.append(switched)
        # A separate graph intervention: two starts, same endpoint, disjoint required predecessors.
        equal=copy.deepcopy(target)
        equal.update(name="same_answer_other_proof")
        terminal=byid["c"]["object"]
        f=next(f for f in equal["facts"] if f["fact_id"]=="f")
        f.update(object=terminal,text=f"{f['subject']}的{f['relation']}是{terminal}。")
        equal["query"]["start"]=other_start
        equal["question"]=target["question"].replace(seed["query"]["start"],other_start)
        equal["comparison_reference"]="same_answer_original_start"
        equal["degree_preserving_claim"]=False
        extras.append(equal)
        equal_first=copy.deepcopy(equal)
        equal_first.update(name="same_answer_original_start",question=seed["question"],
                           comparison_reference="control")
        equal_first["query"]["start"]=seed["query"]["start"]
        extras.append(equal_first)
    elif combo=="C09":
        core=copy.deepcopy(seed["core_facts"])
        book=core[0]["object"]; person=core[0]["subject"]; destination=core[2]["object"]
        observed=fact("observation",book,"已收藏处",destination)
        target["facts"]=[f for f in core if f["fact_id"]!="b"]+[observed]
        target["query"]={"kind":"entailment","prefix":walk(person,"校定卷")}
        target["question"]=f"{person}校定的卷本既已收入{destination}，能否仅凭本题材料确定它一定带朱印？请在是、否、不确定中作答。"
        target["scene_ids"]=["S03","S21","S23"]
        candidates=[{"subject":book,"relation":"带印","object":x} for x in ("朱印","青印")]
        extras.append(variant(seed,"bounded_abduction",facts=[f for f in core if f["fact_id"]!="b"],
                      query={"kind":"abduction","prefix":walk(person,"校定卷"),"goal":destination,"candidates":candidates},
                      question=f"要按本题规则证明{person}校定卷应收入{destination}，只允许补一条事实：该卷带朱印或该卷带青印。最小补充是哪条？这是待补假设，并非已知事实。",
                      scenes=["S03","S22"]))
    elif combo=="C10":
        target["scene_ids"]=["S01","S24","S27"]
        q=copy.deepcopy(seed["query"]);q["time"]=2
        extras.append(variant(seed,"time_2",query=q,question=seed["question"].replace("馆年4","馆年2"),
                      scenes=["S01","S24","S25","S27"]))
        targetq=copy.deepcopy(target["query"])
        extras.append(variant(seed,"time_unspecified",query={"kind":"ambiguous","alternatives":[
                    {"label":"馆年1至3（代表年2）","query":q},
                    {"label":"馆年4至6（代表年4）","query":targetq}]},
                    question=seed["question"].replace("按本题馆年4，", "未指定馆年，")+"请按材料的有效任期分别回答。",
                    scenes=["S01","S24","S26","S27"]))
    # Every family gets the same diagnostic modes. The no-context contract requires refusal.
    anon=copy.deepcopy(target);anon.update(name="anonymous_challenge",naming="anonymous")
    unfamiliar=copy.deepcopy(target);unfamiliar.update(name="unfamiliar_challenge",naming="unfamiliar")
    empty=copy.deepcopy(target);empty.update(name="no_context",facts=[],scene_ids=["S28"],
                                           noise_characters=0,reverse_documents=False,no_context=True)
    return [base,target,anon,unfamiliar,empty]+extras

def render_documents(seed, spec):
    docs=[];fact_to_doc={}
    table_facts=[f for f in spec["facts"] if f["relation"] in ("作者","统计页数")]
    for f in spec["facts"]:
        if f in table_facts: continue
        docid="D"+digest(seed["family_id"]+f["fact_id"])[:8]
        docs.append({"id":docid,"text":f["text"]});fact_to_doc[f["fact_id"]]=docid
    if table_facts:
        rows=[]
        for f in table_facts:
            if f["relation"]=="作者":
                size=next(g for g in table_facts if g["subject"]==f["subject"] and g["relation"]=="统计页数")
                rows.append(f"| {f['subject']} | {f['object']} | {size['object']} |")
        docid="D"+digest(seed["family_id"]+"table")[:8]
        docs.append({"id":docid,"text":"卷本表（统计页数单位：页）\n| 卷本 | 作者 | 统计页数 |\n| --- | --- | --- |\n"+"\n".join(rows)})
        for f in table_facts: fact_to_doc[f["fact_id"]]=docid
    length=spec.get("noise_characters",0)
    if seed["combination_id"]!="C07":
        docs.sort(key=lambda d:digest(seed["family_id"]+"presentation"+d["id"]))
    if length:
        raise ValueError("Classical background must use the literal source renderer")
    if spec.get("reverse_documents"): docs=list(reversed(docs))
    return docs,fact_to_doc

def empty_gold():
    return {"status":"insufficient","answers":[],"proofs":[],"interpretations":[]}

def build_record(seed, original, sources):
    spec=copy.deepcopy(original)
    mapping=identity_map(seed,spec["naming"]) if spec.get("naming") else {}
    for key in ("facts","query","question"):
        spec[key]=replace_entities(spec[key],mapping)
    # Keep interpretation labels aligned with renamed identity mentions.
    if spec["query"]["kind"]=="ambiguous":
        for alt in spec["query"]["alternatives"]:
            alt["label"]=replace_entities(alt["label"],mapping)
    gold=empty_gold() if spec.get("no_context") else solve(spec["query"],spec["facts"])
    if seed["family_id"] in MATERIAL_CONFIG["families"]:
        docs,ftd,ftd_all,audits=render_originals(seed,original,mapping)
        if seed["combination_id"]=="C08" and original["facts"] and next(f for f in original["facts"] if f["fact_id"]=="b")["object"] != next(f for f in seed["target_facts"] if f["fact_id"]=="b")["object"]:
            original_anchor=next(f for f in seed["target_facts"] if f["fact_id"]=="b")["quote_ids"]
            next(f for f in spec["facts"] if f["fact_id"]=="e")["parent_quote_ids"]=original_anchor
        for f in spec["facts"]:
            if f["quote_ids"]:
                f["provenance"]="source_annotation"
        if seed["family_id"]=="F-C07-L":
            spec["scene_ids"]=[x for x in spec["scene_ids"] if x!="S16"]
    else:
        assert all(not f["quote_ids"] for f in spec["facts"]), "Source-backed input requires literal material units"
        docs,ftd=render_documents(seed,spec)
        ftd_all={fid:[docid] for fid,docid in ftd.items()}
        audits={d["id"]:{"register":"vernacular","origin":"synthetic_editor_setting",
                "segments":[],"transformations":[],"annotated_fact_ids":[fid for fid,x in ftd.items() if x==d["id"]]}
                for d in docs}
    registers=sorted({a["register"] for a in audits.values()})
    if not registers:
        registers=["classical","vernacular"] if seed["combination_id"] in ("C04","C08") else ["classical"] if seed["family_id"] in MATERIAL_CONFIG["families"] else ["vernacular"]
    style="mixed" if len(registers)>1 else registers[0]
    for proof in gold["proofs"]:
        for node in proof:
            node["support_evidence_ids"]=list(dict.fromkeys(d for f in node["support_fact_ids"] for d in ftd_all[f]))
    itemid="Q"+digest(seed["family_id"]+original["name"])[:12]
    payload={"id":itemid,"instruction":POLICY,"question":spec["question"],
             "documents":docs,"output_contract":CONTRACT}
    quoteids={q for f in spec["facts"] for q in f["quote_ids"]+f.get("parent_quote_ids",[])}
    sourcelinks=[s["source_link"] for s in sources if any(q["quote_id"] in quoteids for q in s["quotes"])]
    return {"id":itemid,"version":"pilot-v0.1","family_id":seed["family_id"],
            "combination_id":seed["combination_id"],"domain":seed["domain"],
            "variant":original["name"],"split":"pilot_development_only",
            "scenario_ids":spec["scene_ids"],"scenario_annotations":{s:SCENE_NOTES[s] for s in spec["scene_ids"]},
            "scenario_link":"[场景单元](../../docs/benchmark-survey/07_场景总表与中文构题配方.md)",
            "attack_design":ATTACK_DESIGNS[seed["combination_id"]],
            "combination_link":"[先行组合表](combinations.json)",
            "source_cluster_id":seed["source_cluster_id"],"source_links":sourcelinks,
            "input":payload,"facts":spec["facts"],"query":spec["query"],"gold":gold,
            "fact_to_evidence":ftd,"fact_to_evidence_all":ftd_all,"entity_mapping":mapping,
            "material_annotations":audits,"material_registers":registers,"material_style":style,
            "material_label_scope":"prototype" if spec.get("no_context") else "current_input",
            "construction":{"random_seed":SEED,"naming":spec.get("naming","named"),
                            "noise_characters":spec.get("noise_characters",0),
                            "material_rendering":"literal_source_units" if seed["family_id"] in MATERIAL_CONFIG["families"] else "synthetic_vernacular",
                            "reverse_documents":spec.get("reverse_documents",False),
                            "changed_fact_ids":spec.get("changed_fact_ids",[]),
                            "comparison_reference":spec.get("comparison_reference",
                                None if original["name"]=="control" else "control" if original["name"] in ("challenge","anonymous_control") else "challenge"),
                            "degree_preserving_claim":original["name"] in ("challenge","anonymous_challenge","unfamiliar_challenge","switch_question_start") and seed["combination_id"]=="C08"},
            "knowledge_risks":seed["knowledge_risks"],
            "expected_wrong_answers":replace_entities(seed["decoy_answers"],mapping),
            "review":{"assistant_source_read":bool(sourcelinks),"independent_human_review":False,
                      "model_run":False,"status":"candidate"},
            "context_characters":sum(len(d["text"]) for d in docs),
            "minimum_proof_depth":min((depth(p) for p in gold["proofs"]),default=0)}

def degree_signature(facts):
    return Counter((f["subject"],f["relation"],"out") for f in facts),Counter(
        (f["object"],f["relation"],"in") for f in facts)

def validate_record(row, quoteids):
    inp=row["input"]
    assert set(inp)=={"id","instruction","question","documents","output_contract"}
    assert inp["id"]==row["id"]
    assert all(set(d)=={"id","text"} for d in inp["documents"])
    assert len({d["id"] for d in inp["documents"]})==len(inp["documents"])
    assert "http" not in inp["question"]+"".join(d["text"] for d in inp["documents"])
    assert len({f["fact_id"] for f in row["facts"]})==len(row["facts"])
    expected=empty_gold() if row["variant"]=="no_context" else solve(row["query"],row["facts"])
    actual=copy.deepcopy(row["gold"])
    for p in actual["proofs"]:
        for n in p: n.pop("support_evidence_ids",None)
    assert actual==expected,"gold/query mismatch"
    ids={f["fact_id"] for f in row["facts"]}
    docs={d["id"] for d in inp["documents"]}
    for f in row["facts"]:
        assert set(f["quote_ids"]+f.get("parent_quote_ids",[]))<=quoteids
        assert row["fact_to_evidence"][f["fact_id"]] in docs
        if f["provenance"]=="counterfactual_editor_override": assert not f["quote_ids"]
    for p in row["gold"]["proofs"]:
        seen=set()
        for n in p:
            assert set(n["dependencies"])<=seen
            assert n["node_id"] not in seen
            assert set(n["support_fact_ids"])<=ids
            assert set(n["support_evidence_ids"])<=docs
            assert n["support_evidence_ids"]==list(dict.fromkeys(d for f in n["support_fact_ids"] for d in row["fact_to_evidence_all"][f]))
            seen.add(n["node_id"])
    assert len(set(row["entity_mapping"].values()))==len(row["entity_mapping"])
    assert set(row["scenario_ids"])<=set(SCENE_NOTES)
    validate_materials(row)

def validate_dataset(rows, sources, combinations):
    assert len({r["id"] for r in rows})==len(rows)
    families={r["family_id"] for r in rows}
    assert len(families)==20
    for c in combinations:
        domain_set={r["domain"] for r in rows if r["combination_id"]==c["combination_id"]}
        assert domain_set=={"literature","history"}
        actual_scenes={s for r in rows if r["combination_id"]==c["combination_id"] for s in r["scenario_ids"]}
        assert set(c["planned_scene_ids"])<=actual_scenes
    quoteids={q["quote_id"] for s in sources for q in s["quotes"]}
    for r in rows: validate_record(r,quoteids)
    for family in sorted(families):
        by={r["variant"]:r for r in rows if r["family_id"]==family}
        base,target=by["control"],by["challenge"]
        combo=base["combination_id"]
        assert len(by)>=5 and by["no_context"]["gold"]["status"]=="insufficient"
        # Named entity replacement must commute with solving.
        for mode in ("anonymous_challenge","unfamiliar_challenge"):
            mapped=by[mode]
            assert mapped["gold"]["answers"]==replace_entities(target["gold"]["answers"],mapped["entity_mapping"])
            assert mapped["gold"]["status"]==target["gold"]["status"]
            for f,mf in zip(target["facts"],mapped["facts"]):
                assert mf["text"]==replace_entities(f["text"],mapped["entity_mapping"])
        if combo in ("C01","C02","C04","C06","C07","C10"):
            assert base["gold"]["answers"]==target["gold"]["answers"]
        if combo=="C04":
            assert len(target["gold"]["proofs"])==2
            assert len(by["delete_one_support"]["gold"]["proofs"])==1
            assert by["delete_all_bridge_supports"]["gold"]["status"]=="insufficient"
            assert by["delete_irrelevant"]["gold"]["answers"]==target["gold"]["answers"]
        if combo=="C07":
            assert by["reorder_same_noise"]["input"]["documents"]==list(reversed(target["input"]["documents"]))
            for name in ("noise_1000","noise_12000","reorder_same_noise"):
                assert by[name]["gold"]["answers"]==target["gold"]["answers"]
        if combo=="C08":
            assert degree_signature(base["facts"])==degree_signature(target["facts"])
            assert base["gold"]["answers"]!=target["gold"]["answers"]
            switch=by["switch_question_start"]
            assert switch["input"]["documents"]==target["input"]["documents"]
            assert switch["gold"]["answers"]!=target["gold"]["answers"]
            other=by["same_answer_other_proof"]
            assert other["gold"]["answers"]==base["gold"]["answers"]
            assert other["gold"]["proofs"][0][0]["support_fact_ids"]!=base["gold"]["proofs"][0][0]["support_fact_ids"]
            equal_first=by["same_answer_original_start"]
            assert other["input"]["documents"]==equal_first["input"]["documents"]
            assert other["gold"]["answers"]==equal_first["gold"]["answers"]
        if combo=="C09": assert target["gold"]["logical_truth"]=="unknown"
        if combo=="C10": assert by["time_2"]["gold"]["answers"]!=target["gold"]["answers"]
    covered=sorted({s for r in rows for s in r["scenario_ids"]})
    # Freeze source-derived atomic fact IDs against the cited quotation registry.
    assert all(q["text"] for s in sources for q in s["quotes"])
    return {"status":"passed","families":len(families),"records":len(rows),
            "combinations":len(combinations),"scene_ids":covered,"scene_count":len(covered),
            "domains":dict(Counter(r["domain"] for r in rows)),
            "answer_states":dict(Counter(r["gold"]["status"] for r in rows)),
            "variant_counts":dict(Counter(r["variant"] for r in rows)),
            "context_character_range":[min(r["context_characters"] for r in rows),max(r["context_characters"] for r in rows)],
            "proof_depths":dict(Counter(str(r["minimum_proof_depth"]) for r in rows)),
            "sources":len(sources),"independent_human_review":False,"model_runs":0}

def build_oracle(rows):
    inputs=[];golds=[]
    for row in rows:
        if row["variant"]!="control": continue
        for n in row["gold"]["proofs"][0]:
            if "relation" not in n: continue
            upstream,relation=n["upstream"],n["relation"]
            question=(f"按材料，{upstream}的{relation}是什么？" if n["direction"]=="out"
                      else f"按材料，哪个对象的{relation}是{upstream}？")
            time=row["query"].get("time")
            if time is not None: question=f"在本题馆年{time}，"+question
            itemid="O"+digest(row["id"]+n["node_id"])[:12]
            inputs.append({"id":itemid,"instruction":POLICY,"question":question,
                           "documents":row["input"]["documents"],"output_contract":CONTRACT})
            golds.append({"id":itemid,"parent_id":row["id"],"family_id":row["family_id"],
                          "node_id":n["node_id"],"correct_upstream":upstream,"answer":n["expected_value"],
                          "support_evidence_ids":n["support_evidence_ids"],
                          "source_link":"[母题与节点](benchmark.jsonl)","evaluation_scope":"control_lookup_nodes_only"})
    assert len({r["id"] for r in inputs})==len(inputs)
    return inputs,golds

def self_test(rows,sources):
    quotes={q["quote_id"] for s in sources for q in s["quotes"]}
    rejected=[]
    sample=next(r for r in rows if r["variant"]=="control")
    for name in ("wrong_gold","missing_support","leaked_metadata","dependency_cycle"):
        bad=copy.deepcopy(sample)
        if name=="wrong_gold": bad["gold"]["answers"]=["错误答案"]
        elif name=="missing_support": bad["gold"]["proofs"][0][0]["support_evidence_ids"]=["absent"]
        elif name=="leaked_metadata": bad["input"]["gold"]="leak"
        else: bad["gold"]["proofs"][0][0]["dependencies"]=["n3"]
        try: validate_record(bad,quotes)
        except AssertionError: rejected.append(name)
    assert len(rejected)==4
    for name in ("duplicate_surface_variant", "dangling_pair_reference"):
        bad = copy.deepcopy(rows)
        target = next(r for r in bad if r["family_id"] == "F-C04-H" and r["variant"] == "challenge")
        if name == "duplicate_surface_variant":
            index = next(i for i,r in enumerate(bad) if r["family_id"] == "F-C04-H" and r["variant"] == "no_context")
            duplicate = copy.deepcopy(target)
            duplicate["id"] = bad[index]["id"]
            duplicate["input"]["id"] = duplicate["id"]
            duplicate["variant"] = "unfamiliar_challenge"
            bad[index] = duplicate
        else:
            target["paired_changes"]["parent_id"] = "removed-record"
        try:
            validate_selection(bad, sources)
        except AssertionError:
            rejected.append(name)
    assert len(rejected) == 6
    source_sample=next(r for r in rows if r["variant"]=="control" and r["material_style"]=="classical")
    bad=copy.deepcopy(source_sample)
    bad["input"]["documents"][0]["text"]+="伪造的原文"
    try: validate_materials(bad)
    except AssertionError: rejected.append("fabricated_original_text")
    bad=copy.deepcopy(source_sample)
    fid=bad["gold"]["proofs"][0][0]["support_fact_ids"][0]
    bad["fact_to_evidence_all"][fid]=[]
    try: validate_record(bad,quotes)
    except AssertionError: rejected.append("omitted_original_support")
    assert len(rejected)==8
    return rejected

def review_book(rows,combos):
    lines=["# 首轮文学与历史题目审阅册","",
           "[数据入口](README.md) · [组合登记](combinations.json) · [完整机器数据](benchmark.jsonl) · [材料来源](sources.json)","",
           "这是可审阅的候选集；没有独立人工复核和模型实跑。各变体共享家族，不能计作独立原始问题。",
           "数字深度是参考证明的最长依赖链，不等于模型实际思考次数。长背景全文见对应模型输入记录。",""]
    for family in sorted({r["family_id"] for r in rows}):
        group=[r for r in rows if r["family_id"]==family]
        base=next(r for r in group if r["variant"]=="control")
        target=next(r for r in group if r["id"]==base["challenge_id"])
        lines.extend([f"## {family}｜{combos[base['combination_id']]['title']}","",
                      f"领域：{base['domain']}；组合：{base['combination_id']}；来源组：{base['source_cluster_id']}；材料文体：{target['material_style']}。",
                      "场景："+"、".join(f"[{s}](../../docs/benchmark-survey/07_场景总表与中文构题配方.md)" for s in target["scenario_ids"])+"。",
                      "材料归属："+("；".join(target["source_links"]) or "本项目原创合成档案，姓名和事件不作史实主张。"),"",
                      "**对照问句**："+base["input"]["question"],
                      "**保留挑战类型**："+target["variant"],
                      "**组合问句**："+target["input"]["question"],"",
                      "**组合材料**（目录背景仅在机器输入保存全文）：",""])
        for d in target["input"]["documents"]:
            if target["material_annotations"][d["id"]]["origin"]=="repeated_source_background":
                lines.append(f"- {d['id']}：古籍原文重复背景，{len(d['text'])}字符；出处见模型输入的对应标注。")
            else:
                lines.append(f"- {d['id']}："+d["text"].replace("\n"," / "))
        lines.extend(["","**合法参考证明**：",""])
        for index,proof in enumerate(target["gold"]["proofs"],1):
            lines.append(f"- 路径{index}："+"；".join(f"{n['node_id']}={n['expected_value']} [{','.join(n['support_evidence_ids']) or '操作/假设'}] ← {','.join(n['dependencies']) or '起点'}" for n in proof))
        lines.extend(["","| 变体 | 题目 ID | 场景单元 | 状态 / 答案 | 证明深度 |","| --- | --- | --- | --- | --- |"])
        for r in group:
            answer="、".join(map(str,r["gold"]["answers"])) or "材料不足"
            lines.append(f"| {r['variant']} | {r['id']} | {','.join(r['scenario_ids'])} | {r['gold']['status']} / {answer} | {r['minimum_proof_depth']} |")
        lines.extend(["","知识干扰风险："+"；".join(base["knowledge_risks"])+"。",
                      "预设错误候选："+str(target["expected_wrong_answers"])+"；仅为待测假设，未观察到攻击成功。",""])
        for r in group:
            if r["variant"] not in ("control","challenge"):
                lines.append(f"- **{r['variant']}**：{r['input']['question']}")
        lines.append("")
    (DATA/"题目审阅册.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    if not __debug__:
        raise RuntimeError("Validation requires assertions; do not run Python with -O.")
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    combinations=json.loads((DATA/"combinations.json").read_text(encoding="utf-8"))["combinations"]
    sources=json.loads((DATA/"sources.json").read_text(encoding="utf-8"))["sources"]
    combos={c["combination_id"]:c for c in combinations}
    seeds=sorted(source_seeds()+synthetic_seeds(),key=lambda s:s["family_id"])
    # These paraphrases require several quoted fragments, not only one short anchor.
    for s in seeds:
        for factskey in ("core_facts","target_facts"):
            for f in s[factskey]:
                if f["subject"]=="孙悟空" and f["relation"] in ("拜见的师父","师父"):
                    f["quote_ids"]=["L2-C","L2-D","L2-E"]
                if f["subject"]=="孙悟空" and f["relation"]=="出生山": f["quote_ids"]=["L2-B","L2-D"]
                if s["combination_id"]=="C01" and s["domain"]=="literature" and f["fact_id"]=="a":
                    f["quote_ids"]=["L1-B","L1-C"]
                if s["combination_id"]=="C07" and s["domain"]=="history" and f["fact_id"] in ("a","b"):
                    f["quote_ids"]=list(dict.fromkeys(f["quote_ids"]+["H2-A"]))
    for seed in seeds:
        units=MATERIAL_CONFIG["families"].get(seed["family_id"],[])
        for key in ("core_facts","target_facts"):
            for f in seed[key]:
                anchors=list(dict.fromkeys(segment["quote_id"] for u in units
                    if f["fact_id"] in u["fact_ids"]+u.get("also_supports",[])
                    for segment in u["segments"]))
                if anchors: f["quote_ids"]=anchors
    rows=[build_record(s,v,sources) for s in seeds for v in make_variants(s,combos)]
    for r in rows:
        r["control_id"]=next(b["id"] for b in rows if b["family_id"]==r["family_id"] and b["variant"]=="control")
        r["challenge_id"]=next(b["id"] for b in rows if b["family_id"]==r["family_id"] and b["variant"]=="challenge")
        parent_name=r["construction"]["comparison_reference"]
        if parent_name:
            parent=next(b for b in rows if b["family_id"]==r["family_id"] and b["variant"]==parent_name)
            before={f["fact_id"]:f for f in parent["facts"]}
            after={f["fact_id"]:f for f in r["facts"]}
            r["paired_changes"]={"parent_id":parent["id"],
                "added_fact_ids":sorted(set(after)-set(before)),"removed_fact_ids":sorted(set(before)-set(after)),
                "rewritten_fact_ids":sorted(k for k in set(before)&set(after) if before[k]!=after[k]),
                "question_changed":parent["input"]["question"]!=r["input"]["question"],
                "answer_changed":parent["gold"]["answers"]!=r["gold"]["answers"],
                "status_changed":parent["gold"]["status"]!=r["gold"]["status"]}
        else: r["paired_changes"]=None
    report=validate_dataset(rows,sources,combinations)
    generated_count = len(rows)
    rows = select_primary_variants(rows)
    validate_selection(rows, sources)
    report.update(version=VERSION, records=len(rows),
        domains=dict(Counter(r["domain"] for r in rows)),
        answer_states=dict(Counter(r["gold"]["status"] for r in rows)),
        variant_counts=dict(Counter(r["variant"] for r in rows)),
        proof_depths=dict(Counter(str(r["minimum_proof_depth"]) for r in rows)),
        scene_ids=sorted({s for r in rows for s in r["scenario_ids"]}),
        deduplication={"generated_records":generated_count,"removed_records":generated_count-len(rows),
                      "primary_by_family":PRIMARY_BY_FAMILY})
    report["scene_count"] = len(report["scene_ids"])
    report["material_style_counts"]=dict(Counter(r["material_style"] for r in rows))
    report["material_document_counts"]=dict(Counter(a["register"] for r in rows for a in r["material_annotations"].values()))
    oracle,oracle_gold=build_oracle(rows)
    report["oracle_tasks"]=len(oracle)
    report["negative_validation_tests"]=self_test(rows,sources) if args.self_test else []
    write_json(DATA/"seeds.json",{"version":VERSION,"construction_link":"[构建器](../../src/pilot_literature_history_v0/build_pilot.py)","seeds":seeds})
    write_jsonl(DATA/"benchmark.jsonl",rows)
    write_jsonl(DATA/"inputs.jsonl",[r["input"] for r in rows])
    write_jsonl(DATA/"oracle_inputs.jsonl",oracle)
    write_jsonl(DATA/"oracle_gold.jsonl",oracle_gold)
    review_book(rows,combos)
    report["output_hashes"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [DATA/f for f in
        ("seeds.json","benchmark.jsonl","inputs.jsonl","oracle_inputs.jsonl","oracle_gold.jsonl","题目审阅册.md")]}
    report["input_hashes"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [DATA/"sources.json",DATA/"combinations.json",DATA/"material_units.json",Path(__file__),Path(__file__).with_name("original_materials.py")]}
    report["file_links"]={"readme":"[检查说明](README.md)","dataset":"[数据说明](../../data/pilot_literature_history_v0/README.md)"}
    write_json(TEMP/"validation.json",report)
    print(json.dumps({k:v for k,v in report.items() if k not in ("output_hashes","input_hashes","variant_counts","file_links")},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
