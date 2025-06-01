# Agent Interaction Protocol for PTAF

This document outlines the basic protocol for interaction between the PTAF platform and AI Penetration Testing Agents.

## Starting an Agent & Providing Target Information

When the PTAF platform initiates a test run with an agent, it will make the following information available to the agent primarily via **environment variables**:

*   **`PTAF_TARGET_URL`**:
    *   Description: The full URL of the root of the vulnerable web application the agent should target.
    *   Example: `http://localhost:32768` or `http://dvwa.ptaf.internal`
*   **`PTAF_TESTRUN_ID`**:
    *   Description: A unique identifier for the current test run. The agent MUST use this ID when reporting any findings back to the platform.
    *   Example: `123e4567-e89b-12d3-a456-426614174000` (A UUID is recommended, but an integer ID is used in the current DB schema)
*   **`PTAF_AGENT_CALLBACK_API_ENDPOINT`**:
    *   Description: The full URL of the API endpoint on the PTAF platform that the agent should use to POST its findings.
    *   Example: `http://localhost:5000/api/testruns/<PTAF_TESTRUN_ID>/findings` (If the platform is running on the host and agent is a local process) or `http://host.docker.internal:5000/api/testruns/<PTAF_TESTRUN_ID>/findings` (If the agent is running in a Docker container and the platform is on the host). The actual TestRun ID should be substituted in `<PTAF_TESTRUN_ID>`.
*   **`PTAF_SCOPE_NOTES`** (Optional):
    *   Description: A string containing any specific instructions, scope limitations, or hints for the agent for the current test run.
    *   Example: "Focus on reflected XSS in the comment submission forms. Do not attempt brute-force attacks."

The exact mechanism for launching the agent (e.g., executing a script, starting a Docker container) will be handled by the Test Execution Engine of the platform.

## Agent Reporting Findings

Agents report their findings to the platform by making an HTTP `POST` request to the URL provided in the `PTAF_AGENT_CALLBACK_API_ENDPOINT` environment variable.

*   **Method**: `POST`
*   **Endpoint**: Value of `PTAF_AGENT_CALLBACK_API_ENDPOINT`
*   **Content-Type**: `application/json`
*   **Body**: A JSON object representing a single finding. The agent should make one request per finding.

### Finding JSON Structure:

```json
{
  "finding_type": "string",       // Type of vulnerability (e.g., "XSS", "SQLi", "RCE", "Open Redirect", "Information Leakage")
  "description": "string",        // Detailed textual description of the vulnerability and its potential impact.
  "location_url": "string",       // The specific URL or path where the vulnerability was discovered.
  "evidence": "string",           // Supporting evidence. This could be the payload used, vulnerable parameters, reproduction steps, or relevant log snippets.
  "severity": "string",           // Severity level. Suggested values: "Critical", "High", "Medium", "Low", "Informational".
  "cwe_id": "string" (optional)   // Common Weakness Enumeration ID, e.g., "CWE-79" for XSS.
}
```

### Example POST Request Body:

```json
{
  "finding_type": "XSS",
  "description": "Reflected Cross-Site Scripting found on the search results page.",
  "location_url": "http://target.example.com/search.php?query=<script>alert(1)</script>",
  "evidence": "Payload: <script>alert(1)</script> was injected into the 'query' parameter. The script executed successfully upon page load.",
  "severity": "High",
  "cwe_id": "CWE-79"
}
```

The platform will store these findings and associate them with the corresponding `PTAF_TESTRUN_ID`.
