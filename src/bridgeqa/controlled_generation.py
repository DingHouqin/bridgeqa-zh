"""S1.3 synthetic construction only; never imported by the predictor.

Input: six reviewed-for-structure, human-unverified gold_only pilot rows.
Output: safe inputs and a separate source-derived construction/reference ledger.
Owner: S1.3 implementation. These facts are temporary fiction, not source quotes.
"""
import copy
from .protocol import INSTRUCTION, stable_hash, validate_input
from .validation import require

PROFILE = 'controlled-temporary-world-1'
GENERATOR = 'parallel-chain-sha256-v1'
SALT = 'bridgeqa-controlled-2026-10-06-v1'
MISSING = '本句未提供关系事实。'
NO_CONTEXT = '本题未提供事实材料。'


def fact_text(fact):
    return f'临时世界中，代号「{fact["head"]}」的{fact["relation"]}（限定：{fact["qualifier"] or "无"}）是代号「{fact["tail"]}」。'


def roster_codes(codes):
    """Order depends only on each code and a fixed salt, never node roles."""
    return sorted(codes, key=lambda code: (stable_hash([SALT, 'roster', code]), code))


def construct(samples):
    parents=sorted((s for s in samples if s['variant']=='gold_only'),key=lambda s:s['seed_id'])
    require(len(parents)==6 and [s['hop_count'] for s in parents]==[2,3,3,4,2,3], 'controlled requires frozen six pilot topologies')
    require(len({s['source_cluster'] for s in parents})==3,'controlled requires three source topology clusters')
    inputs=[];cases=[];worlds=[];used=set()
    for index,parent in enumerate(parents,1):
        h=parent['hop_count'];root_id=f'root-{index}'
        code_list=[]
        for n in range(2*(h+1)):
            code='N'+stable_hash([SALT,parent['sample_id'],'entity',n])[:8]
            require(code not in used,'opaque code collision');used.add(code);code_list.append(code)
        # Allocation is separate from presentation; no role enters roster order.
        a=code_list[:h+1];b=code_list[h+1:]
        steps=parent['proofs'][0]['steps']
        slots=[]
        for branch,nodes in (('A',a),('B',b)):
            for k,step in enumerate(steps,1):
                slots.append({'slot_id':f'{branch}{k}','kind':'fact','head':nodes[k-1],'relation':step['relation'],
                              'qualifier':step['qualifier'],'tail':nodes[k]})
        roster=roster_codes(code_list)
        roster_text='本临时世界代号名册：'+'、'.join(roster)+'。本句只列代号，不陈述任何关系。'
        base_order=sorted([s['slot_id'] for s in slots]+['roster'],key=lambda slot:stable_hash([SALT,parent['sample_id'],'presentation',slot]))
        # Both branches have h facts; the roster is a non-fact sentence.
        world={'root_id':root_id,'parent_sample_id':parent['sample_id'],'parent_seed_id':parent['seed_id'],
               'source_cluster':parent['source_cluster'],'hop_count':h,'a_nodes':a,'b_nodes':b,
               'source_mapping':[{'source_entity':step['head'],'code':a[k]} for k,step in enumerate(steps)]+[{'source_entity':steps[-1]['tail'],'code':a[-1]}],
               'source_provenance':copy.deepcopy(parent['provenance']),'base_facts':slots,
               'roster_codes':roster,'roster_text':roster_text,'base_order':base_order}
        worlds.append(world)
        question=parent['question'].replace('根据给定小说片段，','根据给定临时世界材料，').replace(steps[0]['head'],a[0])
        require(question!=parent['question'] and a[0] in question,'source root replacement failed')
        conditions=[('full',None),('order-shuffle',None)]+[('internal-reroute',k) for k in range(1,h)]+[('delete-hop',k) for k in range(1,h+1)]+[('no-context',None)]
        for condition,k in conditions:
            facts=copy.deepcopy(slots);order=list(base_order)
            if condition=='internal-reroute':
                next(f for f in facts if f['slot_id']==f'A{k}')['tail']=b[k]
            if condition=='order-shuffle':order=order[1:]+order[:1]  # non-identity, every slot re-indexed
            text_by_slot={f['slot_id']:fact_text(f) for f in facts}
            text_by_slot['roster']=roster_text
            if condition=='delete-hop':text_by_slot[f'A{k}']=MISSING
            if condition=='no-context':order=['no-context'];text_by_slot={'no-context':NO_CONTEXT}
            documents=[{'doc_id':f'd{n}','title':f'材料 {n}','language':'zh','sentences':[{'sent_id':0,'text':text_by_slot[slot]}]} for n,slot in enumerate(order,1)]
            public={'schema_version':'0.2','sample_id':'','question':question,'question_language':'zh','instruction':INSTRUCTION,'documents':documents}
            # Opaque IDs use only public question/documents; never condition/gold.
            public['sample_id']='q_'+stable_hash({'question':question,'documents':documents})[:24]
            validate_input(public);inputs.append(public)
            presentation=[{'slot_id':slot,'doc_id':f'd{n}','sent_id':0} for n,slot in enumerate(order,1)]
            by_slot={p['slot_id']:{'doc_id':p['doc_id'],'sent_id':p['sent_id']} for p in presentation}
            available=[by_slot[f['slot_id']] for f in facts if f['slot_id'] in by_slot and not (condition=='delete-hop' and f['slot_id']==f'A{k}')]
            answerable=condition in ('full','order-shuffle','internal-reroute')
            case={'sample_id':public['sample_id'],'root_id':root_id,'source_cluster':parent['source_cluster'],'condition':condition,
                  'intervention_hop':k,'hop_count':h,'expected_answerable':answerable,'input_sha256':stable_hash(public),
                  'presentation':presentation,'available_fact_support':available,'changed_slots':[f'A{k}'] if condition in ('internal-reroute','delete-hop') else []}
            if answerable:
                proof=[]
                for hop in range(1,h+1):
                    branch='B' if condition=='internal-reroute' and hop>k else 'A'
                    fact=next(f for f in facts if f['slot_id']==f'{branch}{hop}')
                    proof.append({'hop':hop,**{field:fact[field] for field in ('head','relation','tail','qualifier')},'evidence':[by_slot[fact['slot_id']]]})
                case['reference']={'schema_version':'0.2','sample_id':public['sample_id'],'seed_id':public['sample_id'],
                    'source_cluster':parent['source_cluster'],'pair_id':None,'split':'example','origin':'fictional_fixture','domain':'synthetic_temporary_world',
                    'variant':'gold_only','question':question,'question_language':'zh','hop_count':h,'documents':copy.deepcopy(documents),
                    'answer':{'text':proof[-1]['tail'],'aliases':[],'type':'entity'},'entity_aliases':{},'proofs':[{'steps':proof}],
                    'attack':None,'provenance':{'construction_method':'source-derived topology; all temporary-world statements and B branch are synthetic; not source quotations or human gold','sources':copy.deepcopy(parent['provenance']['sources'])},
                    'qc':{'status':'fixture_only','human_verified':False,'review_ids':[]}}
            else:case['expected_refusal']=True
            cases.append(case)
    reference={'schema_version':'controlled-reference-1','profile':PROFILE,'generator':GENERATOR,'salt':SALT,
               'visibility':'public-diagnostic_reference_never_model_input','method':'source-derived synthetic temporary worlds; no human semantic certification',
               'worlds':worlds,'cases':cases}
    return inputs,reference
