# ARAA Threat Model

## 1. Assets
* **Credentials:** Provider API keys, database credentials, JWT secrets.
* **Internal Network:** Local services, database, Redis cache, internal subnets.
* **Tenant Data:** Stored research tasks, checkpoints, evidence items, and generated reports.
* **Compute / Financial Budget:** Token usage, external API calls, execution time.

## 2. Threat Actors & Attacker Capabilities
* **Untrusted Web Content:** External web pages, blogs, and documents scraped during research that may contain indirect prompt injection attacks.
* **Malicious User Input:** Direct prompt injection attempts in task descriptions.
* **Compromised Tool / MCP Server:** External tool servers attempting to return malicious instructions or exfiltrate state.

## 3. The "Lethal Trifecta" Mitigation
The lethal trifecta occurs when an agent possesses:
1. Access to private/internal data.
2. Exposure to untrusted content.
3. An unrestricted communication/egress channel.

### ARAA Architectural Defense:
* **Separation of Policy:** The Policy Engine sits strictly outside the LLM. The model only *proposes* actions; the policy engine *authorizes* them.
* **Untrusted Data Boundaries:** All fetched web content and tool observations are tagged with `trust_level="untrusted"` and delimited so that instructions inside cannot override system instructions.
* **Sandboxed Code Execution:** Code execution runs inside an isolated container with `--net=none` (no network egress), read-only root filesystems, and strict memory/CPU limits.
* **Human Approval for Side Effects:** Any action that communicates externally or alters state requires explicit human approval with exact argument hashing.
