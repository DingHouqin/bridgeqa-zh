// Pure graph check; no filesystem, network, hidden answer, or global data access.
// Scope and limits are documented in ../README.md.
export function solvePath(payload) {
  const {facts, query} = payload;
  if (!Array.isArray(facts) || facts.length > 200 || !query || query.operation !== 'parent_chain' ||
      !Array.isArray(query.steps) || query.steps.length !== 2 || typeof query.start !== 'string' || typeof query.scope !== 'string') {
    throw new Error('Expected a finite two-step parent_chain query');
  }
  const roles = ['father', 'mother', 'parent'];
  if (!query.steps.every(r => roles.includes(r))) throw new Error('Unsupported role');
  const ids = new Set();
  for (const f of facts) {
    if (![f.id, f.parent, f.child, f.scope].every(s => typeof s === 'string' && s.length) ||
        !roles.includes(f.parent_role) || f.parent === f.child || ids.has(f.id)) throw new Error('Invalid fact');
    ids.add(f.id);
  }
  let paths = [{entities: [query.start], facts: []}];
  for (const role of query.steps) {
    paths = paths.flatMap(p => facts.filter(f => f.child === p.entities.at(-1) && f.scope === query.scope &&
      (role === 'parent' || f.parent_role === role) && !p.entities.includes(f.parent) && !p.facts.includes(f.id))
      .map(f => ({entities: [...p.entities, f.parent], facts: [...p.facts, f.id]})));
  }
  const answer_ids = [...new Set(paths.map(p => p.entities.at(-1)))].sort();
  return {status: answer_ids.length === 0 ? 'insufficient_evidence' : answer_ids.length === 1 ? 'answerable' : 'ambiguous',
    answer_ids, proofs: paths, proof_depth: paths.length ? query.steps.length : null,
    world_semantics: 'positive_evidence_only_within_frozen_extracted_graph'};
}
