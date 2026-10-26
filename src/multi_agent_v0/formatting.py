"""Conservative syntax repair: insert only missing closing ] or } tokens.

Never edit string contents, delete fields, guess values, or repair semantic errors.
Raw responses and every inserted character are retained by the runner.
"""
import json
import copy


def normalize_origin_annotations(value):
    """Move only known commentary fields into root warnings; never change facts."""
    result = copy.deepcopy(value)
    edits = []
    root_warnings = result.setdefault('warnings', [])
    if not isinstance(root_warnings, list) or not isinstance(result.get('facts'), list):
        return value, []
    for fact in result['facts']:
        for key in ('note', 'notes', 'warnings', 'parent_role_note'):
            if key not in fact:
                continue
            annotation = fact.pop(key)
            if annotation:
                root_warnings.append(str(fact.get('id', '?')) + '/' + key + ': ' + json.dumps(annotation, ensure_ascii=False))
            edits.append({'fact_id': fact.get('id'), 'field': key, 'moved_to': 'root.warnings', 'original_value': annotation})
    return result, edits


def parse_with_closing_repair(text):
    try:
        return json.loads(text), []
    except json.JSONDecodeError:
        pass
    if len(text) > 200000:
        raise ValueError('Response too large for bounded syntax repair')
    stack, output, edits = [], [], []
    quoted = escaped = False
    matching = {'{': '}', '[': ']'}
    for pos, char in enumerate(text):
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in matching:
            stack.append(char)
        elif char in (']', '}'):
            while stack and matching[stack[-1]] != char:
                inserted = matching[stack.pop()]
                output.append(inserted)
                edits.append({'before_character': pos, 'inserted': inserted})
            if not stack:
                raise ValueError('Unmatched closing delimiter cannot be conservatively repaired')
            stack.pop()
        output.append(char)
    if quoted:
        raise ValueError('Unclosed string cannot be repaired without guessing content')
    while stack:
        inserted = matching[stack.pop()]
        output.append(inserted)
        edits.append({'before_character': len(text), 'inserted': inserted})
    if not edits or len(edits) > 100:
        raise ValueError('No bounded closing-only repair is available')
    repaired = ''.join(output)
    return json.loads(repaired), edits
