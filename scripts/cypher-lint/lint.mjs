// Reads {"name": "cypher", ...} JSON on stdin (produced by backend/scripts/dump_cypher.py)
// and reports syntax/semantic errors from Neo4j's official Cypher language-support package.
import { lintCypherQuery } from '@neo4j-cypher/language-support';
import { readFileSync } from 'node:fs';

const queries = JSON.parse(readFileSync(0, 'utf8'));
let failures = 0;
for (const [name, query] of Object.entries(queries)) {
  const result = lintCypherQuery(query, {});
  const diagnostics = (result.diagnostics ?? result).filter((d) => d.severity === 1);
  if (diagnostics.length) {
    failures++;
    console.log(`✗ ${name}`);
    for (const d of diagnostics) console.log(`    ${d.message.split('\n')[0]} @ ${JSON.stringify(d.range?.start)}`);
  }
}
console.log(`${Object.keys(queries).length - failures}/${Object.keys(queries).length} queries passed`);
process.exit(failures ? 1 : 0);
