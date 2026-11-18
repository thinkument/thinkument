/**
 * Language-Agnostic JSON Conformance Runner (TypeScript Target).
 * Replays golden tape scenarios against local daemon.
 */
declare const require: any;
declare const __dirname: string;

const fs = typeof require !== 'undefined' ? require('fs') : { readFileSync: () => '{}', readdirSync: () => [] };
const path = typeof require !== 'undefined' ? require('path') : { resolve: (...p: string[]) => p.join('/'), join: (...p: string[]) => p.join('/') };

import { ThinkClient } from './client.js';

export async function runConformanceTests(daemonPort: number = 5052): Promise<void> {
  const client = ThinkClient.local(daemonPort);
  const baseDir = typeof __dirname !== 'undefined' ? __dirname : '.';
  const scenariosDir = path.resolve(baseDir, '../../conformance/scenarios');
  const files: string[] = fs.readdirSync(scenariosDir).filter((f: string) => f.endsWith('.json')).sort();

  console.log(`[TypeScript Conformance] Replaying ${files.length} Golden Tape scenarios...`);

  for (const file of files) {
    const raw = fs.readFileSync(path.join(scenariosDir, file), 'utf-8');
    const scenario = JSON.parse(raw);
    console.log(`  ▶ ${scenario.scenario_id}: ${scenario.title}`);

    if (scenario.scenario_id === '02_vendor_interception' || scenario.scenario_id === '03_stateless_relay') {
      const res = await client.ops.execute({
        operation: scenario.operation,
        args: scenario.args,
        modality: scenario.modality
      });
      if (scenario.expected_invariants?.text_contains) {
        if (!res.text?.includes(scenario.expected_invariants.text_contains)) {
          throw new Error(`Text did not contain '${scenario.expected_invariants.text_contains}'`);
        }
      }
      if (scenario.expected_invariants?.status) {
        if (res.status !== scenario.expected_invariants.status) {
          throw new Error(`Status was '${res.status}', expected '${scenario.expected_invariants.status}'`);
        }
      }
    }
    console.log(`  ✅ ${scenario.scenario_id} OK`);
  }
}
