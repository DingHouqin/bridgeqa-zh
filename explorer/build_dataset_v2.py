"""Deterministic explorer projection; see [publication contract](specs/09_第二版数据集发布.md)."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'artifacts/deletion-review-v2/batch-001'
DEST = ROOT / 'data/multi_agent_hongloumeng_v2'
VERSION = 'dataset-v2.0-development'
SOURCE_URL = 'https://archive.org/details/20210205_20210205_1123'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest(value):
    # Match the frozen Blind Solver context IDs, including JSON whitespace.
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def context_id(unit):
    return 'P' + digest(unit)[:10]

def write(name, value, lines=False):
    text = '\n'.join(json.dumps(row, ensure_ascii=False) for row in value)+'\n' if lines else json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    (DEST / name).write_text(text, encoding='utf-8', newline='\n')

def build():
    DEST.mkdir(parents=True, exist_ok=True)
    frozen_path = SOURCE / 'families.frozen.json'
    if not frozen_path.exists(): frozen_path = DEST / 'families.frozen.json'
    audit_path = SOURCE / 'post-audit/audit-blind-records.json'
    if not audit_path.exists(): audit_path = DEST / 'blind-audit.json'
    previous = read(DEST / 'publication.json') if (DEST / 'publication.json').exists() else {}
    source_audit_sha = hashlib.sha256(audit_path.read_bytes()).hexdigest() if audit_path.parent.name=='post-audit' else previous['original_audit_sha256']
    frozen = frozen_path.read_bytes()
    (DEST / 'families.frozen.json').write_bytes(frozen)
    families = json.loads(frozen)
    audits = read(audit_path)
    # Publish outcome evidence, without machine-specific local file paths.
    public_audits = [{k:v for k,v in a.items() if k not in {'result_file','reviewer_task'}} for a in audits]
    write('blind-audit.json', public_audits)
    audit_index = {(a['job']['family_id'], a['job'].get('variant_index')): a for a in public_audits}
    records, inputs, diagnostics, quotes = [], [], [], {}
    instruction = '只依据当前给定材料回答，不能用作品记忆或外部关系补回缺失支持。可答时返回答案与逐步关系及逐字引文；材料不足时明确说明。'
    output_contract = {'status':'answerable / insufficient_evidence / ambiguous', 'answers':'完整答案列表', 'evidence':'context_id 与逐字连续 quote', 'steps':'from、relation、to、evidence', 'reason':'简短依据'}
    relations = {'father':'父亲', 'mother':'母亲'}
    for family in families:
        fid = family['family_id']
        rawfacts = {f['id']: f for f in family['origin']['facts']}
        for variant_index, variant in enumerate(family['variants']):
            rid = f'{fid}-{variant_index:02d}'
            condition = variant['condition']
            audit = audit_index[(fid, variant_index)]
            docs = [{'id':context_id(m['unit_id']), 'text':m['text']} for m in variant['materials']]
            units = {m['unit_id']: m for m in variant['materials']}
            facts, mappings, annotations = [], {}, {}
            for material in variant['materials']:
                qid = material['unit_id']
                quote = {'quote_id':qid, 'text':material['original_text'], 'locator':f"第{material['chapter']}回；原始字符区间 [{material['start_character']}, {material['end_character_exclusive']})"}
                if qid in quotes:
                    assert quotes[qid] == quote
                quotes[qid] = quote
                annotations[context_id(qid)] = {'register':'vernacular','origin':'source_translation','segments':[{'quote_id':qid}], 'transformations':variant['deletion_log'], 'fragment_join':bool(material.get('composition_ranges')), 'annotated_fact_ids':[]}
            for fact_id in variant['active_fact_ids']:
                fact = rawfacts[fact_id]
                qids = sorted({q['unit_id'] for group in fact['evidence_sets'] for q in group if q['unit_id'] in units})
                assert qids, (rid, fact_id)
                mappings[fact_id] = [context_id(q) for q in qids]
                role = relations[fact['parent_role']]
                facts.append({'fact_id':fact_id, 'subject':fact['child'], 'relation':role, 'object':fact['parent'], 'text':f"{fact['child']}的{role}是{fact['parent']}。", 'datatype':'entity', 'period':None, 'provenance':'source_annotation', 'quote_ids':qids, 'scope':fact['scope'], 'registered_support_sets':fact['evidence_sets']})
                for qid in qids:
                    annotations[context_id(qid)]['annotated_fact_ids'].append(fact_id)
            proofs = []
            for proof in variant['gold']['proofs']:
                nodes = []
                for step, fact_id in enumerate(proof['facts']):
                    f = rawfacts[fact_id]
                    nodes.append({'node_id':f'n{step+1}', 'operation':'lookup', 'expected_value':proof['entities'][step+1], 'support_fact_ids':[fact_id], 'dependencies':[f'n{step}'] if step else [], 'relation':relations[f['parent_role']], 'direction':'out', 'upstream':proof['entities'][step], 'support_evidence_ids':mappings[fact_id]})
                proofs.append(nodes)
            status = 'insufficient' if variant['gold']['status']=='insufficient_evidence' else variant['gold']['status']
            base_ids = set(family['variants'][0]['active_fact_ids'])
            current_ids = set(variant['active_fact_ids'])
            scenes = ['S01'] + (['S28'] if status=='insufficient' else [])
            row = {'id':rid,'version':VERSION,'family_id':fid,'combination_id':'V2-PARENT','domain':'literature','variant':condition,'split':'pilot_development_only','scenario_ids':scenes,'scenario_annotations':{'S01':'按问题指定的父／母角色顺序连接两步；陈述范围逐跳保留。', **({'S28':'必要支持已删；原型事实不能补入当前题面。'} if status=='insufficient' else {})}, 'source_cluster_id':'HLM-ARCHIVE-120', 'source_links':[f'[Archive.org《红楼梦》]({SOURCE_URL})'], 'input':{'id':rid,'instruction':instruction,'question':family['question'],'documents':docs,'output_contract':output_contract}, 'facts':facts,'query':{'kind':'walk','start':family['query']['start'],'relations':[{'relation':relations[s],'direction':'out'} for s in family['query']['steps']],'time':None,'scope_by_step':family['query']['scope_by_step']},'gold':{'status':status,'answers':variant['gold']['answer_ids'],'proofs':proofs,'interpretations':[]}, 'fact_to_evidence':{f:ids[0] for f,ids in mappings.items()}, 'fact_to_evidence_all':mappings,'entity_mapping':{},'material_annotations':annotations,'material_registers':['vernacular'],'material_style':'vernacular','material_label_scope':'current_input','construction':{'naming':'named','noise_characters':0,'degree_preserving_claim':False,'changed_fact_ids':[],'material_rendering':'frozen_modern_source','condition':condition}, 'knowledge_risks':['熟悉人物与剧情可能诱使模型补回删去的亲属关系。','登记图不保证自然语言中的全部支持已被穷举；新版支持合同仍需复核。'], 'expected_wrong_answers':[], 'review':{'assistant_source_read':True,'independent_human_review':False,'model_run':True,'status':'requires_strong_review','independent_gpt_semantic_audit':'completed','formal_release':False,'gate_reason':'自然语言支持登记完整性尚未按新版合同重新认证。'}, 'context_characters':sum(len(d['text']) for d in docs),'minimum_proof_depth':variant['gold']['proof_depth'] or 0, 'control_id':f'{fid}-00','challenge_id':f'{fid}-01','paired_changes':None if variant_index==0 else {'parent_id':f'{fid}-00','added_fact_ids':sorted(current_ids-base_ids),'removed_fact_ids':sorted(base_ids-current_ids),'rewritten_fact_ids':[],'question_changed':False,'answer_changed':variant['gold']['answer_ids']!=family['variants'][0]['gold']['answer_ids'],'status_changed':variant['gold']['status']!=family['variants'][0]['gold']['status']}, 'attack_design':{'target_failure':'相似亲属分支错接，或依靠作品记忆补回材料中缺失的关系。','predicted_error_path':['偏离问题指定的父／母角色或人物起点','沿其他家系返回端点，或在缺证时继续猜答'],'acceptance':'答案与完整关系链均须由当前材料支持；材料不足时拒绝补事实。'}, 'source_member':{'variant_index':variant_index,'condition':condition,'deletion_log':variant['deletion_log'],'evidence_completeness':variant['evidence_completeness'],'historical_reference_review':family['reference_review']}, 'model_observation':audit}
            records.append(row)
            inputs.append({'id':rid,'question':family['question'],'contexts':[{'context_id':d['id'],'text':d['text']} for d in docs],'output_contract':output_contract})
        diagnostics.append({'id':f'{fid}-no-material','question':family['question'],'contexts':[],'output_contract':output_contract})
    assert len(records)==57 and len(diagnostics)==10
    write('benchmark.jsonl',records,True)
    write('inputs.jsonl',inputs,True)
    write('no_material_inputs.jsonl',diagnostics,True)
    write('oracle_inputs.jsonl',[],True)
    write('sources.json',{'version':VERSION,'sources':[{'source_id':'HLM-ARCHIVE-120','domain':'literature','title':'《红楼梦》120回通行本 · Archive.org来源快照','author_attribution':'传统署名曹雪芹等；本数据不评判作者归属','url':SOURCE_URL,'revision_url':SOURCE_URL,'retrieved_at':'2026-10-20','source_sha256':'a8caa27dc09c71620bf656a481a0ae1c1209039fcc5f58446ba4bca5469db48d','license_displayed':'Archive.org条目标示 Public Domain Mark 1.0；下载文本另保留维基文库许可说明。原著与网站编校贡献分别考虑。','quotes':list(quotes.values())}]})
    write('combinations.json',{'version':VERSION,'combinations':[{'combination_id':'V2-PARENT','title':'来源亲属两跳 · 干扰与删证对照','planned_scene_ids':['S01','S28'],'material_plan':'10个来源家族；每家族5个共同条件及适用的名称消失删证。','validation_goal':'完整证据链与缺证拒答分开；支持登记完整性待新版合同复核。'}]})
    write('publication.json',{'version':VERSION,'label':'第二版 · 多智能体红楼梦题集','published_for':'development_browsing','formal_release':False,'requires_review':57,'families':10,'records':57,'no_material_diagnostics':10,'model':'deepseek-flash','semantic_task_success':sum(a['semantic_task_success'] for a in public_audits if a['condition']!='no_material_diagnostic'),'semantic_task_total':57,'scoring_note':'历史机器严格评分与独立GPT语义审核分别保留，未用新版评分器重跑。','frozen_family_sha256':hashlib.sha256(frozen).hexdigest(),'original_audit_sha256':source_audit_sha,'projection_note':'题面、答案和条件保持冻结值；网页结构字段是投影，支持登记并非完整性认证。'})

if __name__ == '__main__':
    build()
