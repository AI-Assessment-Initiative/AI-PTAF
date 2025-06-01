# PTAF Agent Development Guide

This guide provides information for developers looking to create AI Penetration Testing Agents that can integrate with the PTAF (AI Penetration Testing Assessment Framework) platform.

## 1. Introduction to PTAF

The PTAF platform is designed to automate the assessment of AI-driven penetration testing agents. It provides:
-   Orchestration of vulnerable test environments.
-   A mechanism to initiate test runs with registered agents against these environments.
-   A protocol for agents to report their findings.
-   A way to view test run progress and results.

The goal is to provide a standardized way to evaluate the capabilities and safety of AI pentesting agents based on the criteria outlined in the AI-PTAF framework (see `criteria.md` and `README.md` in the main repository).

## 2. Agent Interaction Protocol

All interactions between your agent and the PTAF platform (how to receive target information and how to submit findings) are detailed in the [AGENT_INTERACTION_PROTOCOL.md](AGENT_INTERACTION_PROTOCOL.md). Please review this document thoroughly.

Key aspects include:
-   Receiving target URL and test run ID via environment variables (`PTAF_TARGET_URL`, `PTAF_TESTRUN_ID`).
-   Receiving the callback API endpoint for submitting findings via an environment variable (`PTAF_AGENT_CALLBACK_API_ENDPOINT`).
-   Submitting findings as JSON objects via HTTP POST requests to the callback endpoint.

## 3. Agent Registration

Before an agent can be used in a test run, it must be "registered" with the platform.

*   **Current Mechanism:**
    *   Registration is currently a metadata-only process. You add your agent's name and a brief description to the platform's database via the Web UI (under "Agents" > "Register New Agent") or via the `/api/agents` POST API endpoint.
    *   This step **does not** involve uploading your agent's code or specifying how to execute it.

## 4. Agent Selection for Test Runs

Once registered, your agent will appear in the list of available agents when initiating a new test run from the Web UI (under "Test Runs" > "Start New Test Run"). The platform user can then select your agent and a target environment to start an assessment.

## 5. Agent Execution (Current Status and Future Roadmap)

This is a critical section to understand the current capabilities and future direction.

*   **Current Status: Simulated Execution**
    *   As of the current version, the PTAF platform's Test Execution Engine **simulates** agent activity.
    *   When a test run is started:
        1.  The platform deploys the target environment.
        2.  It updates the test run status (e.g., to "RUNNING").
        3.  It **does not actually launch or execute your external agent process/code.**
        4.  It currently includes a `time.sleep()` to mimic processing time and, for specific agent name/environment pairs (e.g., "Test Agent Alpha" on DVWA), it might create a *dummy finding* directly in the database. This is for testing the platform's finding-handling pipeline.
        5.  The platform then proceeds to clean up the environment.
    *   Therefore, your actual agent code **will not be called or run** by the platform in its present state. The `PTAF_*` environment variables described in the interaction protocol are logged by the platform but not yet injected into a live agent process.

*   **Future Roadmap: True Agent Execution**

    To enable the platform to execute agents automatically, the following enhancements are envisioned:

    *   **Execution Mechanism Definition:** The platform will need to know *how* to run your agent. We are considering two primary approaches:
        1.  **Containerized Agents (Preferred):**
            *   Agents are packaged as Docker images.
            *   During agent registration (or an update step), you would provide the Docker image name (e.g., `yourusername/my-ai-agent:latest`).
            *   The Test Execution Engine would then use `docker run` to start your agent's container.
            *   The necessary `PTAF_TARGET_URL`, `PTAF_TESTRUN_ID`, `PTAF_AGENT_CALLBACK_API_ENDPOINT`, and `PTAF_SCOPE_NOTES` environment variables would be injected into your agent's container by the platform during startup.
            *   Your agent's Docker container would need network access to the `PTAF_TARGET_URL` and the `PTAF_AGENT_CALLBACK_API_ENDPOINT`. The platform will need to manage Docker networking to facilitate this (e.g. by ensuring the platform and agent containers are on the same Docker network, or by using `host.docker.internal` for callbacks if the platform runs on the host).
        2.  **Script-Based Agents:**
            *   Agents are provided as a set of scripts with a defined entry point.
            *   During registration, you would provide the command needed to start the agent (e.g., `python /path/to/agent/main.py` or `./run_agent.sh`).
            *   The platform would execute this command, setting the `PTAF_*` environment variables in the execution shell.
            *   This approach requires careful consideration of dependencies and execution environments.

    *   **Agent Output/Log Collection:** Beyond structured findings, the platform might also need to collect stdout/stderr logs from the agent for debugging or more detailed reporting. For containerized agents, `docker logs` could be used.

    *   **Agent Lifecycle Management:** The platform would manage starting, monitoring (e.g., for timeouts or crashes), and stopping the agent process/container.

    *   **Updating the `Agent` Model:** The `Agent` database model would need new fields to store this execution information (e.g., `docker_image_name`, `execution_command`).

## 6. Developing Your Agent

Given the current simulated execution:
1.  Focus on implementing the **findings submission** part of the [AGENT_INTERACTION_PROTOCOL.md](AGENT_INTERACTION_PROTOCOL.md). You can test this by manually running your agent and having it POST findings to the platform's `/api/testruns/<run_id>/findings` endpoint.
    *   You would first create a test run via the UI/API to get a valid `<run_id>`.
    *   Then, manually start the target environment (or use one started by the platform if you can grab its URL).
    *   Then, run your agent, providing it the `PTAF_TARGET_URL`, `PTAF_TESTRUN_ID`, and `PTAF_AGENT_CALLBACK_API_ENDPOINT` manually.
2.  Prepare your agent to receive the `PTAF_*` environment variables.
3.  Consider packaging your agent as a Docker container for future compatibility.

We welcome feedback on the proposed agent execution mechanisms.

## 7. Contribution
If you are interested in contributing to the development of the true agent execution capabilities, please check the project's main `README.md` for contribution guidelines.
