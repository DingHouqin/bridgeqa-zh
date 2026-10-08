"""Source translations; [design](../../data/pilot_literature_history_v0/现代文翻译说明.md).

Units and aliases: [registry](../../data/pilot_literature_history_v0/material_units.json).
Fixed translations are separate from the unchanged source quotations.
"""
import hashlib
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / 'data/pilot_literature_history_v0'
CONFIG = json.loads((DATA / 'material_units.json').read_text(encoding='utf-8'))
SOURCES = json.loads((DATA / 'sources.json').read_text(encoding='utf-8'))['sources']
QUOTES = {q['quote_id']: q for source in SOURCES for q in source['quotes']}
TRANSLATIONS = {t['translation_id']: t for t in json.loads((DATA / 'modern_translations.json').read_text(encoding='utf-8'))['entries']}

def identifier(family, unit):
    return 'D' + hashlib.sha256((family + unit).encode('utf-8')).hexdigest()[:8]

def source_text(segments):
    parts = []
    for segment in segments:
        original = QUOTES[segment['quote_id']]['text']
        assert 0 <= segment['start'] < segment['end'] <= len(original)
        parts.append(original[segment['start']:segment['end']])
    return '\n'.join(parts)

def translated_text(segments):
    parts, ids = [], []
    for segment in segments:
        key = f"{segment['quote_id']}:{segment['start']}:{segment['end']}"
        translation = TRANSLATIONS[key]
        assert translation['source_text'] == source_text([segment])
        assert hashlib.sha256(translation['source_text'].encode()).hexdigest() == translation['source_sha256']
        assert hashlib.sha256(translation['modern_text'].encode()).hexdigest() == translation['modern_sha256']
        parts.append(translation['modern_text'])
        ids.append(key)
    return '\n'.join(parts), ids

def literal_replace(text, replacements):
    if not replacements:
        return text, []
    pattern = '|'.join(re.escape(s) for s in sorted(replacements, key=lambda x: (-len(x), x)))
    changes = []
    def change(match):
        before, after = match.group(), replacements[match.group()]
        changes.append({'start': match.start(), 'end': match.end(), 'before': before, 'after': after})
        return after
    return re.sub(pattern, change, text), changes

def apply_stage(text, stage):
    changes = stage['changes']
    for change in reversed(changes):
        assert text[change['start']:change['end']] == change['before']
        text = text[:change['start']] + change['after'] + text[change['end']:]
    return text

def render_originals(seed, spec, mapping):
    """Return model documents and separate audit fields; model sees only id/text."""
    family = seed['family_id']
    active = {f['fact_id']: f for f in spec['facts']}
    baseline = {f['fact_id']: f for f in seed['target_facts']}
    docs, audits, primary, complete = [], {}, {}, {fid: [] for fid in active}
    replacements = {}
    for canonical, renamed in mapping.items():
        for form in [canonical] + CONFIG.get('modern_entity_forms', {}).get(canonical, []):
            assert form not in replacements or replacements[form] == renamed
            replacements[form] = renamed
    # Contextual phrases prevent a short name such as 原 from modifying ordinary
    # words. Name/surname/courtesy-name descriptions are treated as one span.
    for form in CONFIG.get('modern_entity_context_forms', []):
        if form['canonical'] in mapping:
            replacements[form['before']] = form['replacement_template'].format(entity=mapping[form['canonical']])
    units = CONFIG['families'][family]
    # Restore the whole saved quotation in ordinary conditions. Only deletion
    # conditions use the registered smaller excerpts to actually remove the bridge.
    if seed['combination_id'] == 'C04' and 'b' in active:
        if seed['domain'] == 'history':
            units = [{'unit_id': 'kin-full', 'fact_ids': ['a', 'b', 'c'],
                      'segments': [{'quote_id': 'H1-A', 'start': 0, 'end': len(QUOTES['H1-A']['text'])}]}] + [u for u in units if 'b2' in u['fact_ids']]
        else:
            units = [u for u in units if 'a' in u['fact_ids']] + [{'unit_id': 'cave-full', 'fact_ids': ['b', 'c'],
                      'segments': [{'quote_id': 'L2-C', 'start': 0, 'end': len(QUOTES['L2-C']['text'])}]}] + [u for u in units if 'b2' in u['fact_ids']]
    for unit in units:
        fids = [fid for fid in unit['fact_ids'] if fid in active]
        if not fids:
            continue
        original, translation_ids = translated_text(unit['segments'])
        text, stages = original, []
        # Swap occupants, not the cave name inside a geographic clause. Otherwise
        # editing a cave also changes its mountain, contradicting the intended graph.
        if seed['combination_id'] == 'C08' and 'b' in unit['fact_ids'] and active['b']['object'] != baseline['b']['object']:
            before, after = baseline['b']['subject'], active['e']['subject']
            if seed['domain'] == 'history':
                text, changes = literal_replace(text, {before + '的父亲': after + '的父亲'})
            else:
                text, changes = literal_replace(text, {s: after for s in [before] + CONFIG.get('modern_entity_forms', {}).get(before, [])})
            assert len(changes) == 1
            stages.append({'kind': 'counterfactual_replace', 'fact_id': 'e', 'changes': changes})
            fids = ['e' if fid == 'b' else fid for fid in fids]
        for fid in fids:
            if seed['combination_id'] == 'C08' and fid == 'e' and 'b' in unit['fact_ids']:
                continue
            before, after = baseline[fid]['object'], active[fid]['object']
            if before == after:
                continue
            forms = [before] + CONFIG.get('modern_entity_forms', {}).get(before, [])
            target = after
            text, changes = literal_replace(text, {s: target for s in forms})
            assert len(changes) == 1, (family, unit['unit_id'], fid, changes)
            stages.append({'kind': 'counterfactual_replace', 'fact_id': fid, 'changes': changes})
        text, changes = literal_replace(text, replacements)
        if changes:
            stages.append({'kind': 'entity_rename', 'changes': changes})
        docid = identifier(family, 'original-' + unit['unit_id'])
        docs.append({'id': docid, 'text': text})
        audits[docid] = {'register': 'vernacular', 'origin': 'source_translation',
                        'segments': unit['segments'], 'transformations': stages,
                        'translation_ids': translation_ids,
                        'fragment_join': len(unit['segments']) > 1,
                        'annotated_fact_ids': fids}
        for fid in fids:
            primary.setdefault(fid, docid)
            complete[fid].append(docid)
        for fid in unit.get('also_supports', []):
            if fid in active:
                complete[fid].append(docid)
    # Mixed counterfactual branches and irrelevant cover colour retain their real status.
    for fid, fact in active.items():
        if fid in primary:
            continue
        assert not fact['quote_ids'], ('Source-backed fact has no literal unit', family, fid)
        baseline_text = fact['text']
        template_text, stages = baseline_text, []
        counterfactual = seed['combination_id'] == 'C08' and fid == 'b' and fact['object'] != baseline['b']['object']
        if counterfactual:
            template_text = baseline['e']['text']
            baseline_text, changes = literal_replace(template_text, {baseline['e']['subject']: fact['subject']})
            assert len(changes) == 1
            stages.append({'kind': 'counterfactual_replace', 'changes': changes})
        text, changes = literal_replace(baseline_text, replacements)
        if changes:
            stages.append({'kind': 'entity_rename', 'changes': changes})
        docid = identifier(family, fid)
        docs.append({'id': docid, 'text': text})
        primary[fid] = docid
        complete[fid].append(docid)
        audits[docid] = {'register': 'vernacular', 'origin': 'counterfactual_vernacular' if counterfactual else 'synthetic_editor_setting',
                        'segments': [], 'template_text': template_text, 'transformations': stages, 'annotated_fact_ids': [fid]}
    if seed['combination_id'] != 'C07':
        docs.sort(key=lambda d: hashlib.sha256((family + 'presentation' + d['id']).encode()).hexdigest())
    length = spec.get('noise_characters', 0)
    if length:
        qid = CONFIG['background_quote_by_domain'][seed['domain']]
        segment = {'quote_id': qid, 'start': 0, 'end': len(QUOTES[qid]['text'])}
        original, translation_ids = translated_text([segment])
        added = []
        for i, size in enumerate((length // 2, length - length // 2)):
            text = (original * (size // len(original) + 1))[:size]
            docid = identifier(family, f'background{i}')
            added.append({'id': docid, 'text': text})
            audits[docid] = {'register': 'vernacular', 'origin': 'repeated_translated_background',
                            'background_quote_id': qid, 'characters': size,
                            'translation_ids': translation_ids,
                            'segments': [], 'transformations': [], 'annotated_fact_ids': []}
        # Do not manufacture a third support document when the original has only two.
        docs = [docs[0], added[0], *docs[1:-1], added[1], docs[-1]]
    if spec.get('reverse_documents'):
        docs.reverse()
    return docs, primary, complete, audits

def validate_materials(row):
    audits = row['material_annotations']
    assert set(audits) == {d['id'] for d in row['input']['documents']}
    for doc in row['input']['documents']:
        audit = audits[doc['id']]
        if audit['origin'] == 'source_translation':
            expected, translation_ids = translated_text(audit['segments'])
            assert audit['translation_ids'] == translation_ids
            for stage in audit['transformations']:
                expected = apply_stage(expected, stage)
            assert doc['text'] == expected, 'original text/transform mismatch'
            assert audit['register'] == 'vernacular'
        elif audit['origin'] == 'repeated_translated_background':
            qid = audit['background_quote_id']
            original, translation_ids = translated_text([{'quote_id': qid, 'start': 0, 'end': len(QUOTES[qid]['text'])}])
            assert audit['translation_ids'] == translation_ids
            size = audit['characters']
            assert doc['text'] == (original * (size // len(original) + 1))[:size]
        else:
            assert audit['register'] == 'vernacular'
            if 'template_text' in audit:
                expected = audit['template_text']
                for stage in audit['transformations']:
                    expected = apply_stage(expected, stage)
                assert doc['text'] == expected
    if row['input']['documents']:
        registers = sorted({a['register'] for a in audits.values()})
        assert row['material_registers'] == registers
        assert row['material_style'] == ('mixed' if len(registers) > 1 else registers[0])
    for fid, primary in row['fact_to_evidence'].items():
        assert primary in row['fact_to_evidence_all'][fid]
        assert set(row['fact_to_evidence_all'][fid]) <= set(audits)
