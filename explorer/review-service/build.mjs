// [Service publishing](README.md).
import {mkdirSync,copyFileSync} from 'node:fs';
mkdirSync('dist/server',{recursive:true});mkdirSync('dist/.openai',{recursive:true});
for(const name of ['worker.js','review-model.js','plan.js'])copyFileSync(name,'dist/server/'+(name==='worker.js'?'index.js':name));
copyFileSync('.openai/hosting.json','dist/.openai/hosting.json');
console.log('Built shared review service');
