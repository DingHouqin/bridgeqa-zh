"""A public, finite-grammar engineering baseline, never a language model.

Only accepts the label-free input contract. Developed on this pilot's grammar;
no hidden gold, source blueprint, aliases, IDs, or dataset files are accessed.
"""
import json
import re
import time
from .protocol import validate_input, normalize, RELATION_QUALIFIERS

ALGORITHM = "public-text-compositional-grammar-v3"
CJK = r"[\u3400-\u9fff]"


def task(question):
    """Compose local natural phrases; reject all unparsed residual text.

    Returns only root and exact relation/qualifier pairs, never an answer.
    This is a finite public grammar, not general Chinese language understanding.
    """
    oracle=re.fullmatch(r'独立单跳诊断（正确上游）：实体「([^」]+)」的「([^」]+)」是什么？限定：([^。]+)。只提交一跳；只用给定片段。',question)
    if oracle:
        root,relation,qualifier=oracle.groups()
        return root,[(relation,'' if qualifier=='无额外限定' else qualifier)]
    expression=question.removeprefix('根据给定小说片段，')
    expression=expression.removeprefix('根据给定临时世界材料，')
    adoption='在归附后的拜认事件中' in expression
    expression=expression.replace('在归附后的拜认事件中，','').replace('在归附后的拜认事件中','')
    marriage='还汉后，在本段配婚事件中被配给了谁' in expression
    expression=expression.replace('还汉后，在本段配婚事件中被配给了谁','的所配之夫')
    inlaw=any(s in expression for s in ('女婿中，驻守陕西的中郎将','驻守陕西的中郎将女婿'))
    expression=expression.replace('女婿中，驻守陕西的中郎将','女婿').replace('驻守陕西的中郎将女婿','女婿')
    expression=expression.replace('，其','的').replace('认谁为义父','所认义父').replace('被谁谋杀','的谋杀者')
    for ending in ('叫什么？','是什么？','是谁？','？'):
        if expression.endswith(ending):
            expression=expression[:-len(ending)];break
    root=None;predicates=[]
    for pattern,relation,qualifier in ((r'砍断(.+?)手腕之人','斩断手腕者',''),(r'将(.+?)刺于马下之人','刺于马下者',''),(r'骑赤兔马追赶(.+?)之人','追赶者','本段骑赤兔马追赶事件')):
        match=re.match(pattern,expression)
        if match:
            root=match.group(1);predicates.append((relation,qualifier));expression=expression[match.end():];break
    terms=sorted(RELATION_QUALIFIERS,key=len,reverse=True)
    if root is None:
        match=re.search('|'.join(map(re.escape,terms)),expression)
        if not match or not expression[:match.start()].rstrip('的'):return None,[]
        root=expression[:match.start()].removesuffix('的');expression=expression[match.start():]
    while expression:
        expression=expression.removeprefix('的')
        relation=next((r for r in terms if expression.startswith(r)),None)
        if relation is None:return None,[]
        qualifier=''
        if relation=='所认义父':
            if not adoption:return None,[]
            qualifier='归附后本段拜认事件'
        elif relation=='女婿':
            if not inlaw:return None,[]
            qualifier='驻守陕西的中郎将'
        elif relation=='所配之夫':
            if not marriage:return None,[]
            qualifier='还汉后本段配婚事件'
        elif RELATION_QUALIFIERS[relation]:return None,[]
        predicates.append((relation,qualifier));expression=expression[len(relation):]
    if not root or any(c in root for c in '，。？「」') or not 1<=len(predicates)<=4:return None,[]
    return root,predicates


def extract(documents):
    edges=[]
    for doc in documents:
        text="\n".join(s['text'] for s in doc['sentences'])
        # The identical identity disclaimer is visible in both pair conditions.
        if "合成练习附录" in text:continue
        evidence=[{'doc_id':doc['doc_id'],'sent_id':s['sent_id']} for s in doc['sentences']]
        def add(head,relation,tail,qualifier='',references=None):
            edges.append({'head':head,'relation':relation,'tail':tail,'qualifier':qualifier,'evidence':evidence if references is None else references})
        # Explicit public fact grammar supports unseen names and opaque codes.
        # Each fact cites its sentence. Scope is an exact qualifier string.
        for sentence in doc['sentences']:
            # Transparent temporary-world syntax: delimiters are not aliases.
            # Parse the entire declaration once; never re-extract it as prose.
            temporary=re.fullmatch(r'临时世界中，代号「(N[0-9a-f]{8})」的([^（]+)（限定：([^）]+)）是代号「(N[0-9a-f]{8})」。',sentence['text'])
            if temporary:
                head,relation,qualifier,tail=temporary.groups()
                qualifier='' if qualifier=='无' else qualifier
                if RELATION_QUALIFIERS.get(relation,None)==qualifier:
                    add(head,relation,tail,qualifier,[{'doc_id':doc['doc_id'],'sent_id':sentence['sent_id']}])
                continue
            pattern=r"([^，。\n「」]+?)的(作者|创办|位于|属于|刺于马下者|女儿|女婿|字|弟弟|所认义父|所配之夫|斩断手腕者|父亲|老师|谋杀者|追赶者)(?:（限定：([^）]*)）)?是([^，。\n「」]+)"
            for match in re.finditer(pattern,sentence['text']):
                head,relation,qualifier,tail=match.groups()
                add(head,relation,tail,qualifier or '',[{'doc_id':doc['doc_id'],'sent_id':sentence['sent_id']}])
        # Locally explicit classical predicates; names are captured from text.
        patterns=[
            (rf"部将({CJK}{{2,3}})，使铁锤.*?({CJK}{{2,3}})挥戟.*?砍断",'斩断手腕者'),
            (rf"名将({CJK}{{2,3}})。.*?被({CJK}{{2,3}})一戟刺于马下",'刺于马下者'),
            (rf"部将({CJK}{{2,3}})，.*?被({CJK}{{2,3}})手起一戟，刺于马下",'刺于马下者'),
            (rf"({CJK}{{2,3}})挥槊亲战({CJK}{{2,3}})。[^\n]*?\2纵赤兔马赶来",'追赶者'),
        ]
        for pattern, relation in patterns:
            for m in re.finditer(pattern,text,re.S):
                add(m.group(1),relation,m.group(2),'本段骑赤兔马追赶事件' if relation=='追赶者' else '')
        for identity in re.finditer(rf"({CJK}{{2,3}})未及回言，({CJK}{{2,3}})飞马",text):
            # Scope is this arrival/adoption event after ending prior service,
            # not an unconstrained '义父' anywhere in the body.
            event=rf"次日，({CJK})持[^。]+首级，往见[^。]+。{CJK}遂引\1见({CJK})。[^\n]*?\1纳\2坐[^\n]*?拜为义父"
            for adoption in re.finditer(event,text):
                father,child=identity.groups();short_child,short_father=adoption.groups()
                if child.endswith(short_child) and father.endswith(short_father):add(child,'所认义父',father,'归附后本段拜认事件')
        for leader in re.finditer(rf"刺史({CJK}{{2,3}})(?:$|\n)",text):
            for brother in re.finditer(rf"封弟({CJK}{{2,3}})为",text):add(leader.group(1),'弟弟',brother.group(1))
            for son_in_law in re.finditer(rf"其婿中郎将({CJK}{{2,3}})，守住陕西",text):
                add(leader.group(1),'女婿',son_in_law.group(1),'驻守陕西的中郎将')
        for murder in re.finditer(rf"({CJK}{{2,3}})谋杀({CJK}{{2,3}})，",text):add(murder.group(2),'谋杀者',murder.group(1))
        families=list(re.finditer(rf"(?:却说)?({CJK}{{2,3}})有[一二三四五六七八九十]+子",text))
        for index,family in enumerate(families):
            father=family.group(1)
            family_text=text[family.end():families[index+1].start() if index+1<len(families) else len(text)]
            for child in re.findall(rf"名({CJK}{{1,2}})，字",family_text):add(father[0]+child,'父亲',father)
        for name in re.finditer(rf"姓({CJK})，名({CJK}{{1,2}})，字({CJK}{{1,4}})，",text):add(name.group(1)+name.group(2),'字',name.group(3))
        for pupil in re.finditer(rf"姓({CJK})，名({CJK}{{1,2}})，(?:子|字)[^，]+，乃(?:中郎)?({CJK}{{2,3}})之徒",text):add(pupil.group(1)+pupil.group(2),'老师',pupil.group(3))
        for daughter in re.finditer(rf"乃({CJK}{{2,3}})庄也。今({CJK})女({CJK}{{2,3}})",text):
            if daughter.group(1).endswith(daughter.group(2)):add(daughter.group(1),'女儿',daughter.group(3))
        for actor in re.finditer(rf"({CJK}{{2,3}})兵分",text):
            for marriage in re.finditer(rf"送({CJK}{{2,3}})还汉。({CJK})乃以({CJK})配({CJK}{{2,3}})为妻",text):
                wife,a,w,husband=marriage.groups()
                if actor.group(1).endswith(a) and wife.endswith(w):add(wife,'所配之夫',husband,'还汉后本段配婚事件')
    return edges


def predict(model_input,run_id=ALGORITHM):
    validate_input(model_input)
    started=time.perf_counter()
    start,relations=task(model_input['question'])
    edges=extract(model_input['documents'])
    current=start; steps=[]; error=None
    for hop,(relation,qualifier) in enumerate(relations,1):
        choices=[e for e in edges if current is not None and normalize(e['head'])==normalize(current) and e['relation']==relation and e['qualifier']==qualifier]
        # Same semantic edge merges all evidence; distinct tails compete.
        distinct={}
        for edge in choices:
            key=normalize(edge['tail'])
            if key not in distinct:distinct[key]={**edge,'evidence':[]}
            for ref in edge['evidence']:
                if ref not in distinct[key]['evidence']:distinct[key]['evidence'].append(ref)
        if len(distinct)!=1:
            error='unsupported_or_ambiguous_text_relation';break
        edge=next(iter(distinct.values()));steps.append({'hop':hop,**edge});current=edge['tail']
    complete=bool(relations) and len(steps)==len(relations)
    support=[]
    for step in steps:
        for ref in step['evidence']:
            if ref not in support:support.append(ref)
    result={'schema_version':'0.2','sample_id':model_input['sample_id'],'run_id':run_id,'status':'ok' if complete else 'abstain',
            'answer':{'text':current} if complete else None,'support':support,'submitted_steps':steps,
            'error_message':error if relations else 'unsupported_question_grammar'}
    result['raw_output']=json.dumps(result,ensure_ascii=False,sort_keys=True)
    result['latency_ms']=round((time.perf_counter()-started)*1000,6)
    return result
