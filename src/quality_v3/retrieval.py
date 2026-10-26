"""Literal per-edge support-location hints; never a relation extractor."""
import hashlib
import re


def edge_windows(contexts, candidate_edges, entity_bindings, radius=1):
    """Find every child-name/alias occurrence, retaining sentence neighbours.

    Offsets are in the actual provided member. Negations, dreams and spurious
    names are deliberately retained: a window is not evidence that an edge is
    true, independent, or exhaustive over unnamed anaphora.
    """
    if radius < 0:
        raise ValueError('Negative sentence radius')
    if len({c['context_id'] for c in contexts}) != len(contexts):
        raise ValueError('Duplicate current context')
    entities={e['id']:e for e in entity_bindings}
    result=[]
    for edge in candidate_edges:
        child=entities.get(edge['child'],{'name':edge['child'],'aliases':[]})
        surfaces=sorted(set([child['name']]+child.get('aliases',[])),key=lambda value:(-len(value),value))
        found=[]
        for c in contexts:
            text=c['text']
            sentences=[m.span() for m in re.finditer(r'[^。！？\n]+[。！？\n]?|[。！？\n]',text)]
            seen=set()
            for surface in surfaces:
                if not surface:
                    continue
                cursor=0
                while (at:=text.find(surface,cursor)) >= 0:
                    cursor=at+1
                    indices=[i for i,(a,b) in enumerate(sentences) if a<=at<b]
                    if not indices:
                        continue
                    i=indices[0];start=sentences[max(0,i-radius)][0]
                    end=sentences[min(len(sentences)-1,i+radius)][1]
                    if (start,end) in seen:
                        continue
                    seen.add((start,end))
                    found.append({'context_id':c['context_id'],'start':start,'end':end,
                                  'text':text[start:end], 'matched_surface':surface,
                                  'context_sha256':hashlib.sha256(text.encode()).hexdigest(),
                                  'status':'unverified_retrieval_window'})
        result.append({'edge_id':edge['id'],'candidate_edge':dict(edge),'windows':found,
                       'not_a_truth_or_independence_verdict':True})
    return result


def query_and_proof_card(payload):
    """Make already-submitted query/proof order explicit, without fixing it."""
    query=payload['query'];claim=payload['candidate']
    lines=['查询起点：'+str(query.get('start'))]
    roles={'father':'父亲','mother':'母亲','parent':'父母之一'}
    for i,role in enumerate(query.get('steps',[])):
        subject='查询起点' if i==0 else f'第{i-1}步得到的人'
        lines.append(f'第{i}步：查找{subject}的{roles.get(role,role)}。')
    lines.append('候选原样声明status='+str(claim['status'])+'；答案='+str(claim['answer_ids']))
    facts={f['id']:f for f in claim.get('facts',[])}
    for p in claim.get('proofs',[]):
        if 'facts' in p:
            for i,fid in enumerate(p['facts']):
                f=facts.get(fid,{})
                lines.append(f'提交顺序{i}：fact_id={fid}；child={f.get("child")}；parent={f.get("parent")}；role={f.get("parent_role")}；scope={f.get("scope")}。')
        elif 'from' in p:
            lines.append(f'提交步骤（原顺序）：{p.get("from")} --{p.get("relation")}--> {p.get("to")}。')
    lines.append('这是原始声明的展开，不是程序裁定；不得重排或修订后冒充被审版本。')
    return '\n'.join(lines)
