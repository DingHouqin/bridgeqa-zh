// Mounted by the official Harness loader through ../harness.patch.yml.
import {defineTool} from '@deepseek-ai/dsh-tools';
import {solvePath} from './logic.mjs';
import {writeFileSync} from 'node:fs';
export const name = 'bridgeqa-tools';
export const inject = ['tools'];
export function apply(ctx) {
  ctx.tools.register(defineTool({
    name: 'bridgeqa_check_parent_path',
    description: 'Check a proposed two-step child-to-parent graph query. This pure function only sees facts explicitly passed in payload_json; it cannot read any hidden gold or source. It does not validate natural-language entailment.',
    parameters: {payload_json: {type: 'string', required: true, description: 'JSON object with facts and query. Facts use id,parent,child,parent_role,scope. Query uses operation=parent_chain,start,steps,scope.'}},
    output: {schema: {type: 'string'}, render: (_args, value) => [{type: 'text', text: value}]},
    async execute(args) { return JSON.stringify(solvePath(JSON.parse(args.payload_json))); },
  }));
  // Optional program-owned integration gate. This is not a model-facing file tool.
  // The calling runner owns both environment fields and the exact artifact path.
  if (process.env.BRIDGEQA_TOOL_AUDIT_INPUT && process.env.BRIDGEQA_TOOL_AUDIT_FILE) {
    const destination = process.env.BRIDGEQA_TOOL_AUDIT_FILE;
    const encoded = process.env.BRIDGEQA_TOOL_AUDIT_INPUT;
    void (async () => {
      const result = await ctx.tools.execute({callId: 'bridgeqa-program-proof-gate',
        name: 'bridgeqa_check_parent_path', arguments: {payload_json: encoded}, signal: new AbortController().signal});
      writeFileSync(destination, JSON.stringify({visible_tools: ctx.tools.schemas().map(t => t.name), result}), 'utf8');
    })().catch(error => writeFileSync(destination, JSON.stringify({error_type: error.name, error: error.message}), 'utf8'));
  }
}
