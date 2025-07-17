# Acceptance & Assurance (AA) Procedure for Testing the Workspace Isolation Bridge in Serena

## 1. Introduction

This document provides a comprehensive, self-contained guide for drafting and executing an Acceptance/Assurance (AA) procedure to test the Workspace Isolation Bridge in the Serena project. It is designed for knowledge agents or engineers who do not have direct access to the codebase, but require all necessary context to understand, validate, and extend the testing process.

---

## 2. Project and Component Overview

### 2.1 Serena Project
- Python-based agent framework for IDE and model context protocol (MCP) integration.
- Supports multi-client, multi-workspace operation, especially with Claude Code and similar tools.
- Uses MCP servers for agent communication, with both local and remote server support (see `mcp.json`).

### 2.2 Workspace Isolation Bridge
- **Purpose:** Prevents connection conflicts and resource contention by providing a dedicated Serena MCP server instance per workspace.
- **Problem Solved:** Multiple clients (e.g., Claude Code workspaces) connecting to the same MCP server can cause shared state, resource contention, and unpredictable behavior. The bridge ensures each workspace is isolated.
- **Architecture:**
  - Each workspace connects to the bridge, which spawns and manages a dedicated Serena MCP server for that workspace.
  - Transparent proxy/relay for MCP communication.
  - Unique workspace IDs (e.g., `workspace_isolation_bridge_{pid}_{timestamp}`) for tracking and logging.
- **Key Features:**
  - Workspace isolation
  - Dedicated server lifecycle management
  - Scalability (unlimited concurrent workspaces)
  - Transparent to clients

---

## 3. Relevant Files and Directories

- **Bridge Implementation:**
  - `src/serena/wsl_bridge/wrapper.py` (main logic)
  - `src/serena/wsl_bridge/config.py` (configuration)
  - `src/serena/wsl_bridge/metrics.py` (performance tracking)
- **Scripts:**
  - `scripts/serena-wsl-bridge.py` (standalone script)
  - `scripts/validate-wsl-setup.sh` (validation)
  - `scripts/setup-wsl-bridge.sh` (setup)
- **Tests:**
  - `tests/test_wsl_bridge.py` (unit/integration tests)
  - `test_workspace_isolation_bridge.py` (root-level, may include additional scenarios)
- **Documentation:**
  - `serena-wiki/WSL-Bridge-Setup.md`
  - `serena-wiki/WSL_Bridge_Debug_Report.md`
  - `serena-wiki/WSL-MCP-Troubleshooting-Briefing.md`
  - `WSL_Bridge_Setup_Guide.md` (root)
- **Configuration:**
  - `~/.config/serena/workspace_isolation_bridge.json` (per-user config)
  - `mcp.json` (MCP server definitions)

---

## 4. Setup and Prerequisites

1. **Environment:**
   - Python 3.x environment with all Serena dependencies installed.
   - Access to WSL (if required by your deployment scenario).
   - Ensure `serena-workspace-isolation-bridge` is available in PATH.
2. **Configuration:**
   - Update your MCP client (e.g., Claude Code) to use the bridge as the MCP server command:
     ```json
     {
       "servers": {
         "serena": {
           "type": "stdio",
           "command": "serena-workspace-isolation-bridge",
           "args": ["--context", "ide-assistant"]
         }
       }
     }
     ```
   - Ensure `workspace_isolation_bridge.json` exists and is correctly configured.
3. **Logging:**
   - Confirm per-workspace log files are generated with unique workspace IDs.
4. **Documentation:**
   - Review all bridge-related documentation for troubleshooting and architecture understanding.

---

## 5. Testing Procedure

### 5.1 Programmatic Testing
- **Goal:** Validate bridge logic, server spawning, and isolation at the code level.
- **How:**
  - Run `tests/test_wsl_bridge.py` and `test_workspace_isolation_bridge.py`.
  - These tests may use direct function calls, mocks, or simulated MCP messages.
  - Check for:
    - Correct server instantiation per workspace
    - No cross-workspace state leakage
    - Proper server lifecycle (startup, monitoring, cleanup)
    - Accurate logging and metrics
- **Limitations:**
  - May not fully simulate real MCP protocol traffic or agent behavior.
  - Useful for regression and unit testing, but not sufficient for full assurance.

### 5.2 Protocol-Level (MCP) Testing
- **Goal:** Ensure the bridge behaves correctly when accessed via the full MCP protocol, as a real agent would.
- **How:**
  - Configure a real MCP client (e.g., Claude Code) to connect via the bridge.
  - Open multiple workspaces/clients simultaneously.
  - Perform typical agent operations (file edits, queries, etc.) in each workspace.
  - Observe:
    - Each workspace gets a dedicated server instance
    - No interference or shared state between workspaces
    - Bridge transparently proxies all MCP traffic
    - Server lifecycle is managed per workspace
    - Logs and metrics reflect correct isolation
- **Validation:**
  - Use `scripts/validate-wsl-setup.sh` and review logs for errors or conflicts.
  - Optionally, inject deliberate errors or simulate failures to test bridge robustness.

### 5.3 Manual/Exploratory Testing
- **Goal:** Catch edge cases and usability issues not covered by automated tests.
- **How:**
  - Manually start/stop workspaces, kill server processes, or disconnect clients.
  - Observe bridge recovery, cleanup, and error handling.
  - Review logs for unexpected behavior.

---

## 6. Verification and Reporting

- **Success Criteria:**
  - No connection conflicts or resource contention between workspaces
  - Each workspace has a dedicated, isolated server instance
  - Server lifecycle is managed independently per workspace
  - Logs and metrics confirm correct operation
  - All tests (programmatic and protocol-level) pass without errors
- **Documentation:**
  - Record test results, logs, and any issues found
  - Update documentation as needed
  - File bug reports for any failures or unexpected behavior

---

## 7. Addressing the Programmatic vs. Protocol-Level Testing Concern

- **Key Point:**
  - Programmatic (direct) testing is valuable for verifying internal logic, but may not capture all real-world scenarios, especially those involving protocol nuances, timing, or client behavior.
  - Protocol-level (MCP) testing is essential for full assurance, as it validates the bridge in the context it will actually be used.
- **Recommendation:**
  - Always perform both types of testing.
  - Use programmatic tests for fast feedback and regression checks.
  - Use protocol-level tests to ensure real agent compatibility, correct isolation, and robust error handling.
  - Manual/exploratory testing is recommended for additional coverage.

---

## 8. References and Further Reading

- `serena-wiki/WSL-Bridge-Setup.md`
- `serena-wiki/WSL_Bridge_Debug_Report.md`
- `serena-wiki/WSL-MCP-Troubleshooting-Briefing.md`
- `WSL_Bridge_Setup_Guide.md`
- `src/serena/wsl_bridge/`
- `tests/test_wsl_bridge.py`, `test_workspace_isolation_bridge.py`
- `scripts/validate-wsl-setup.sh`, `scripts/serena-wsl-bridge.py`
- `mcp.json`, `workspace_isolation_bridge.json`

---

## 9. Glossary

- **AA Procedure:** Acceptance/Assurance procedure; a formal process for verifying that a system meets its requirements and is ready for use.
- **MCP:** Model Context Protocol; the protocol used for agent communication in Serena.
- **Workspace Isolation Bridge:** The component that ensures each client/workspace gets a dedicated MCP server instance.

---

## 10. Appendix: Example MCP Server Config

```json
{
  "servers": {
    "serena": {
      "type": "stdio",
      "command": "serena-workspace-isolation-bridge",
      "args": ["--context", "ide-assistant"]
    }
  }
}
```

---

## 11. Assumptions for Execution (for the Knowledge Agent)

This document provides the conceptual framework and necessary context for drafting the AA procedure. When translating this into an executable procedure, the knowledge agent should make the following assumptions or seek further clarification:

- **Python Environment Setup:** Assume standard Python project setup practices. If a `requirements.txt` or `pyproject.toml` exists, assume `pip install -r requirements.txt` or `uv pip install -r requirements.txt` (given `uvx.exe` in `mcp.json`) is the method for dependency installation.
- **Script Execution:** Assume shell scripts (`.sh`) are executed using `bash` or `sh` (e.g., `bash scripts/validate-wsl-setup.sh`). Python scripts (`.py`) are executed with `python` (e.g., `python scripts/serena-wsl-bridge.py`).
- **Test Execution:** Assume Python tests are run using `pytest` (e.g., `pytest tests/test_wsl_bridge.py`).
- **Configuration File Creation:** If `workspace_isolation_bridge.json` does not exist, assume it needs to be created manually based on expected structure, or that a setup script (e.g., `scripts/setup-wsl-bridge.sh`) handles its initial creation.
- **MCP Client Configuration:** The specific steps to configure an external MCP client (e.g., Claude Code) are outside the scope of this document and would typically be found in the client's own documentation. The provided `mcp.json` snippet is for reference on how the bridge *should* be invoked by a client.

If any of these assumptions are incorrect or require more specific commands for the target environment, the knowledge agent should explicitly request that information.

---

This document is intended to be copied, extended, or adapted for use by knowledge agents, QA engineers, or system integrators working with the Serena Workspace Isolation Bridge.
