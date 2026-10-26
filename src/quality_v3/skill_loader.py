"""Explicit project-local Harness skill routing; see the module README."""
import hashlib
from pathlib import Path

SKILLS = Path(__file__).resolve().parent / 'skills'
ROUTES = {
    'review': [('two-hop-necessity', ['references/boundaries.md']),
               ('member-evidence-audit', [])],
    'scoring': [('semantic-score-review', ['references/scoring-boundaries.md'])],
    'inventory': [('support-inventory', [])],
}


def load_skills(role, expected_files=None):
    """Load only the named role's instructions and explicitly routed references.

    The returned hashes are sealed before evaluation. Runtime startup does not
    install global Codex skills or rely on native Harness auto-discovery.
    """
    if role not in ROUTES:
        raise ValueError('Unknown skill role')
    files = {}
    parts = []
    for name, references in ROUTES[role]:
        for relative in ['SKILL.md'] + references:
            path = (SKILLS / name / relative).resolve()
            if not path.is_relative_to(SKILLS.resolve()):
                raise ValueError('Skill path escaped project skill directory')
            data = path.read_bytes()
            key = path.relative_to(SKILLS).as_posix()
            files[key] = hashlib.sha256(data).hexdigest()
            parts.append('项目技能 ' + key + '\n' + data.decode('utf-8'))
    if expected_files is not None and files != expected_files:
        raise ValueError('Skill snapshot changed; start a new experiment version')
    return {'role': role, 'files': files, 'text': '\n\n'.join(parts),
            'discovery': 'explicit_role_route', 'global_installation': False}


def snapshot():
    return {role: load_skills(role)['files'] for role in ROUTES}
