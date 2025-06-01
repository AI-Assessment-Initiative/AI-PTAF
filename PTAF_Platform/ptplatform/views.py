from flask import Blueprint, jsonify, request, render_template, url_for, redirect, flash
from .app import db # db is initialized in app.py
from .models import TestEnvironment, Agent, TestRun, Finding
from . import orchestrator
import datetime
import time
import logging # Import logging

# Get a logger instance for this module
logger = logging.getLogger(__name__)

main_blueprint = Blueprint('main', __name__)

@main_blueprint.route('/')
def index():
    # This is an API route, the UI index is ui_index
    return "Welcome to the AI Penetration Testing Assessment Platform API!"

# --- Test Environment API Endpoints ---
@main_blueprint.route('/api/environments/available', methods=['GET'])
def get_available_environments():
    logger.info("API: Listing available deployable environments.")
    return jsonify(orchestrator.list_vulnerable_apps())

@main_blueprint.route('/api/environments/stored', methods=['GET'])
def get_stored_environments():
    logger.info("API: Listing stored environment configurations from DB.")
    environments = TestEnvironment.query.all()
    return jsonify([{"id": env.id, "name": env.name, "docker_image": env.docker_image, "description": env.description} for env in environments])

@main_blueprint.route('/api/environments/stored', methods=['POST'])
def create_stored_environment():
    data = request.get_json()
    logger.info(f"API: Attempting to create stored environment: {data.get('name')}")
    if not data or not data.get('name') or not data.get('docker_image'):
        logger.warning(f"API: Failed to create stored environment {data.get('name')} - missing fields.")
        return jsonify({"error": "Name and docker_image are required"}), 400
    existing = TestEnvironment.query.filter_by(name=data['name']).first()
    if existing:
        logger.warning(f"API: Stored environment {data['name']} already exists.")
        return jsonify({"error": f"TestEnvironment with name '{data['name']}' already exists."}), 409
    new_env = TestEnvironment(name=data['name'], docker_image=data['docker_image'], description=data.get('description'))
    db.session.add(new_env)
    db.session.commit()
    logger.info(f"API: Stored environment '{new_env.name}' (ID: {new_env.id}) created.")
    return jsonify({"id": new_env.id, "name": new_env.name, "docker_image": new_env.docker_image}), 201

@main_blueprint.route('/api/environments/start/<env_name>', methods=['POST'])
def start_environment_api(env_name):
    logger.info(f"API: Manual request to start environment: {env_name}")
    # ... (rest of the logic is the same as before, add logging if desired)
    app_to_start = None
    available_apps = orchestrator.list_vulnerable_apps()
    for app_info in available_apps:
        if app_info['name'].lower() == env_name.lower():
            app_to_start = app_info
            break
    if not app_to_start:
        stored_env = TestEnvironment.query.filter(TestEnvironment.name.ilike(env_name)).first()
        if stored_env:
             app_to_start = {'name': stored_env.name, 'image_name': stored_env.docker_image}
        else:
            logger.warning(f"API: Environment '{env_name}' not found for manual start.")
            return jsonify({"error": f"Environment '{env_name}' not found or not configured for dynamic start."}), 404

    container, url = orchestrator.start_environment(app_to_start['image_name'])
    if container:
        logger.info(f"API: Manual environment '{app_to_start['name']}' (Container: {container.id}) starting at {url}.")
        return jsonify({"message": f"{app_to_start['name']} starting.", "container_id": container.id, "container_name": container.name, "url": url}), 202
    else:
        logger.error(f"API: Failed to manually start environment '{app_to_start['name']}'.")
        return jsonify({"error": f"Failed to start {app_to_start['name']}"}), 500

@main_blueprint.route('/api/environments/stop/<container_id_or_name>', methods=['POST'])
def stop_environment_api(container_id_or_name):
    logger.info(f"API: Manual request to stop container: {container_id_or_name}")
    success = orchestrator.stop_environment(container_id_or_name)
    if success:
        logger.info(f"API: Container {container_id_or_name} stopping process initiated successfully.")
        return jsonify({"message": f"Container {container_id_or_name} stopping process initiated."}), 200
    else:
        logger.error(f"API: Failed to stop or find container {container_id_or_name} manually.")
        return jsonify({"error": f"Failed to stop or find container {container_id_or_name}"}), 500

@main_blueprint.route('/api/environments/running', methods=['GET'])
def get_running_environments():
    logger.info("API: Listing all running platform environments.")
    # ... (rest of the logic is the same)
    running_platform_containers = []
    try:
        all_containers = orchestrator.client.containers.list(all=True)
        for c in all_containers:
            if c.name.startswith("ptaf_env_"):
                 details = orchestrator.get_running_environment_details(c.id)
                 if details:
                    running_platform_containers.append(details)
        return jsonify(running_platform_containers)
    except Exception as e:
        logger.error(f"API: Could not retrieve running containers: {str(e)}")
        return jsonify({"error": f"Could not retrieve running containers: {str(e)}"}), 500

# --- Agent API Endpoints ---
@main_blueprint.route('/api/agents', methods=['GET'])
def get_agents():
    logger.info("API: Listing all registered agents.")
    agents = Agent.query.all()
    return jsonify([{"id": agent.id, "name": agent.name, "description": agent.description} for agent in agents])

@main_blueprint.route('/api/agents', methods=['POST'])
def create_agent():
    data = request.get_json()
    logger.info(f"API: Attempting to create agent: {data.get('name')}")
    if not data or not data.get('name'):
        logger.warning(f"API: Failed to create agent {data.get('name')} - name is required.")
        return jsonify({"error": "Agent 'name' is required"}), 400
    existing = Agent.query.filter_by(name=data['name']).first()
    if existing:
        logger.warning(f"API: Agent {data['name']} already exists.")
        return jsonify({"error": f"Agent with name '{data['name']}' already exists."}), 409
    new_agent = Agent(name=data['name'], description=data.get('description'))
    db.session.add(new_agent)
    db.session.commit()
    logger.info(f"API: Agent '{new_agent.name}' (ID: {new_agent.id}) created.")
    return jsonify({"id": new_agent.id, "name": new_agent.name, "description": new_agent.description}), 201

# --- Test Run API Endpoints ---
@main_blueprint.route('/api/testruns', methods=['POST'])
def create_test_run():
    data = request.get_json()
    agent_id = data.get('agent_id')
    environment_id = data.get('environment_id')
    logger.info(f"API: Received request to create TestRun for Agent ID: {agent_id}, Environment ID: {environment_id}")

    if not agent_id or not environment_id:
        logger.warning("API: TestRun creation failed - agent_id or environment_id missing.")
        return jsonify({"error": "agent_id and environment_id are required"}), 400

    agent = Agent.query.get(agent_id)
    if not agent:
        logger.warning(f"API: TestRun creation failed - Agent ID {agent_id} not found.")
        return jsonify({"error": "Agent not found"}), 404

    environment_meta = TestEnvironment.query.get(environment_id)
    if not environment_meta:
        logger.warning(f"API: TestRun creation failed - Environment ID {environment_id} not found.")
        return jsonify({"error": "TestEnvironment metadata not found"}), 404

    new_run = TestRun(
        agent_id=agent.id,
        environment_id=environment_meta.id,
        status="STARTING",
        start_time=datetime.datetime.utcnow()
    )
    db.session.add(new_run)
    db.session.commit()
    logger.info(f"API: TestRun {new_run.id} created. Status: STARTING. Agent: {agent.name}, Env: {environment_meta.name}")

    try:
        logger.info(f"TestRun {new_run.id}: Starting environment {environment_meta.name} (Image: {environment_meta.docker_image})")
        container, url = orchestrator.start_environment(environment_meta.docker_image, instance_name_prefix=f"ptaf_run_{new_run.id}_")

        if not container or not url:
            new_run.status = "FAILED"
            new_run.results_summary = f"Failed to start environment {environment_meta.name}."
            new_run.end_time = datetime.datetime.utcnow()
            db.session.commit()
            logger.error(f"TestRun {new_run.id}: {new_run.results_summary}")
            return jsonify({"error": new_run.results_summary, "run_id": new_run.id}), 500

        new_run.target_url = url
        new_run.active_container_id = container.id
        new_run.active_container_name = container.name
        new_run.status = "RUNNING"
        db.session.commit()
        logger.info(f"TestRun {new_run.id}: Environment started. URL: {url}, Container: {container.name}. Status: RUNNING")

        callback_url = url_for('main.submit_finding', run_id=new_run.id, _external=True)
        logger.info(f"TestRun {new_run.id}: Simulating agent execution. Target: {url}, Agent: {agent.name}, Callback: {callback_url}")
        time.sleep(15)

        if agent.name == "Test Agent Alpha" and "dvwa" in environment_meta.docker_image.lower():
            logger.info(f"TestRun {new_run.id}: Simulating a finding by {agent.name}.")
            dummy_finding = Finding(
                test_run_id=new_run.id,
                finding_type="Simulated XSS via Test Engine",
                description="This is a simulated XSS finding created by the Test Execution Engine during a DVWA test.",
                location_url=f"{url}/vulnerabilities/xss_r/?name=test_engine_sim_{new_run.id}",
                evidence=f"<script>simulated_alert('TestRun {new_run.id} via Engine')</script>",
                severity="Medium",
                cwe_id="CWE-79"
            )
            db.session.add(dummy_finding)
            # We need to commit here to get dummy_finding.id if we want to log it,
            # but it's better to log 'pending commit' or commit along with TestRun update later.
            # For now, let's commit before logging the ID.
            db.session.commit() # Commit to get ID
            new_run.results_summary = "Simulated agent run. One dummy finding created by test engine."
            logger.info(f"TestRun {new_run.id}: Dummy finding (ID: {dummy_finding.id}) created by engine.")
        else:
            new_run.results_summary = "Simulated agent run. No findings generated by test engine."

        new_run.status = "REPORTING"
        db.session.commit()
        logger.info(f"TestRun {new_run.id}: Agent simulation finished. Status: REPORTING. Summary: {new_run.results_summary}")

        logger.info(f"TestRun {new_run.id}: Stopping environment container {new_run.active_container_name}.")
        cleanup_success = orchestrator.stop_environment(new_run.active_container_id)
        if not cleanup_success:
            logger.warning(f"TestRun {new_run.id}: Failed to stop/remove container {new_run.active_container_name}.")
            new_run.status = "CLEANUP_FAILED"
            new_run.results_summary += " | Warning: Environment cleanup failed."
        else:
            logger.info(f"TestRun {new_run.id}: Environment stopped successfully.")
            new_run.status = "COMPLETED"

        new_run.end_time = datetime.datetime.utcnow()
        db.session.commit()
        logger.info(f"TestRun {new_run.id}: Processing finished. Final Status: {new_run.status}. Duration: {new_run.end_time - new_run.start_time}")

        return jsonify({
            "message": "Test run executed.", "run_id": new_run.id, "status": new_run.status,
            "target_url": new_run.target_url, "summary": new_run.results_summary
        }), 201

    except Exception as e:
        logger.exception(f"TestRun {new_run.id}: EXCEPTION during execution.") # logger.exception includes stack trace
        new_run.status = "FAILED"
        new_run.results_summary = f"An unexpected error occurred: {str(e)}"
        new_run.end_time = datetime.datetime.utcnow()
        if new_run.active_container_id:
            try:
                logger.info(f"TestRun {new_run.id}: Attempting emergency cleanup of container {new_run.active_container_id} due to exception.")
                orchestrator.stop_environment(new_run.active_container_id)
            except Exception as cleanup_e:
                logger.error(f"TestRun {new_run.id}: Emergency cleanup also failed: {str(cleanup_e)}")
                new_run.results_summary += f" | Emergency Cleanup also failed: {str(cleanup_e)}"
        db.session.commit()
        return jsonify({"error": new_run.results_summary, "run_id": new_run.id}), 500

@main_blueprint.route('/api/testruns', methods=['GET'])
def get_test_runs():
    logger.info("API: Listing all test runs.")
    # ... (rest of the logic is the same)
    runs = TestRun.query.all()
    return jsonify([{
        "id": run.id, "agent_id": run.agent_id, "agent_name": run.agent.name,
        "environment_id": run.environment_id, "environment_name": run.environment.name,
        "status": run.status, "start_time": run.start_time.isoformat() if run.start_time else None,
        "target_url": run.target_url,
        "active_container_name": run.active_container_name
        } for run in runs])

@main_blueprint.route('/api/testruns/<int:run_id>', methods=['GET'])
def get_test_run(run_id):
    logger.info(f"API: Requesting details for TestRun ID: {run_id}")
    # ... (rest of the logic is the same)
    run = TestRun.query.get(run_id)
    if run:
        findings_data = [{
            "id": f.id, "timestamp": f.timestamp.isoformat(), "finding_type": f.finding_type,
            "description": f.description, "location_url": f.location_url,
            "evidence": f.evidence, "severity": f.severity, "cwe_id": f.cwe_id
        } for f in run.findings.all()]

        return jsonify({
            "id": run.id, "agent_id": run.agent_id, "agent_name": run.agent.name,
            "environment_id": run.environment_id, "environment_name": run.environment.name,
            "status": run.status, "start_time": run.start_time.isoformat() if run.start_time else None,
            "end_time": run.end_time.isoformat() if run.end_time else None,
            "target_url": run.target_url,
            "active_container_id": run.active_container_id,
            "active_container_name": run.active_container_name,
            "results_summary": run.results_summary,
            "findings": findings_data
        })
    logger.warning(f"API: TestRun ID {run_id} not found.")
    return jsonify({"error": "Test run not found"}), 404

@main_blueprint.route('/api/testruns/<int:run_id>/findings', methods=['POST'])
def submit_finding(run_id):
    logger.info(f"API: Received finding submission for TestRun ID: {run_id}")
    test_run = TestRun.query.get(run_id)
    if not test_run:
        logger.warning(f"API: Finding submission for TestRun ID {run_id} failed - TestRun not found.")
        return jsonify({"error": "TestRun not found"}), 404

    data = request.get_json()
    if not data:
        logger.warning(f"API: Finding submission for TestRun ID {run_id} failed - no data provided.")
        return jsonify({"error": "No data provided"}), 400

    required_fields = ["finding_type", "description", "severity"]
    for field in required_fields:
        if field not in data or not data[field]:
            logger.warning(f"API: Finding submission for TestRun ID {run_id} failed - missing field: {field}.")
            return jsonify({"error": f"Missing required field: {field}"}), 400

    new_finding = Finding(
        test_run_id=run_id,
        finding_type=data["finding_type"],
        description=data["description"],
        location_url=data.get("location_url"),
        evidence=data.get("evidence"),
        severity=data["severity"],
        cwe_id=data.get("cwe_id")
    )
    db.session.add(new_finding)
    db.session.commit()
    logger.info(f"API: Finding (Type: {new_finding.finding_type}, Severity: {new_finding.severity}) submitted and saved for TestRun ID {run_id}. New Finding ID: {new_finding.id}")
    return jsonify({"message": "Finding submitted successfully", "finding_id": new_finding.id}), 201

# --- UI Routes (largely unchanged, but ensure logging is present if desired, or rely on API logs) ---
# Adding basic logging to UI route handlers for visibility
@main_blueprint.route('/ui/')
def ui_index():
    logger.info("UI: Accessing Home page.")
    return render_template('index.html')

@main_blueprint.route('/ui/environments', methods=['GET'])
def ui_environments():
    logger.info("UI: Accessing Environments page.")
    available_apps = orchestrator.list_vulnerable_apps()
    stored_envs = TestEnvironment.query.order_by(TestEnvironment.name).all()
    return render_template('environments.html', available_apps=available_apps, stored_envs=stored_envs)

@main_blueprint.route('/ui/environments/create_stored', methods=['POST'])
def ui_create_stored_environment():
    name = request.form.get('name')
    logger.info(f"UI: Attempting to create stored environment config: {name}")
    try:
        docker_image = request.form.get('docker_image')
        description = request.form.get('description')
        if not name or not docker_image:
            flash('Name and Docker Image are required.', 'error')
            logger.warning(f"UI: Create stored env config failed for '{name}' - missing fields.")
        else:
            existing = TestEnvironment.query.filter_by(name=name).first()
            if existing:
                 flash(f"Configuration with name '{name}' already exists.", 'error')
                 logger.warning(f"UI: Stored env config '{name}' already exists.")
            else:
                new_env = TestEnvironment(name=name, docker_image=docker_image, description=description)
                db.session.add(new_env)
                db.session.commit()
                flash(f"Environment configuration '{name}' added successfully.", 'success')
                logger.info(f"UI: Stored env config '{name}' added.")
    except Exception as e:
        flash(f"Error adding environment configuration: {str(e)}", "error")
        logger.exception(f"UI: Error adding stored env config '{name}'.")
    return redirect(url_for('main.ui_environments'))


@main_blueprint.route('/ui/agents', methods=['GET'])
def ui_agents():
    logger.info("UI: Accessing Agents page.")
    agents = Agent.query.order_by(Agent.name).all()
    return render_template('agents.html', agents=agents)

@main_blueprint.route('/ui/agents/create', methods=['POST'])
def ui_create_agent():
    name = request.form.get('name')
    logger.info(f"UI: Attempting to register agent: {name}")
    try:
        description = request.form.get('description')
        if not name:
            flash('Agent name is required.', 'error')
            logger.warning(f"UI: Agent registration failed for '{name}' - name missing.")
        else:
            existing = Agent.query.filter_by(name=name).first()
            if existing:
                flash(f"Agent with name '{name}' already exists.", 'error')
                logger.warning(f"UI: Agent '{name}' already exists.")
            else:
                new_agent = Agent(name=name, description=description)
                db.session.add(new_agent)
                db.session.commit()
                flash(f"Agent '{name}' registered successfully.", 'success')
                logger.info(f"UI: Agent '{name}' registered.")
    except Exception as e:
        flash(f"Error registering agent: {str(e)}", "error")
        logger.exception(f"UI: Error registering agent '{name}'.")
    return redirect(url_for('main.ui_agents'))

@main_blueprint.route('/ui/testruns', methods=['GET'])
def ui_test_runs():
    logger.info("UI: Accessing Test Runs page.")
    agents = Agent.query.order_by(Agent.name).all()
    environments = TestEnvironment.query.order_by(TestEnvironment.name).all()
    test_runs_query = db.session.query(TestRun, Agent.name, TestEnvironment.name).        join(Agent, TestRun.agent_id == Agent.id).        join(TestEnvironment, TestRun.environment_id == TestEnvironment.id).        order_by(TestRun.id.desc()).all()
    test_runs_list = []
    for run, agent_name, env_name in test_runs_query:
        test_runs_list.append({
            'id': run.id, 'agent_name': agent_name, 'environment_name': env_name,
            'target_url': run.target_url, 'active_container_name': run.active_container_name,
            'status': run.status,
            'start_time': run.start_time.isoformat(sep=' ', timespec='seconds') if run.start_time else None,
            'end_time': run.end_time.isoformat(sep=' ', timespec='seconds') if run.end_time else None,
        })
    return render_template('test_runs.html', agents=agents, environments=environments, test_runs=test_runs_list)

@main_blueprint.route('/ui/testruns/create', methods=['POST'])
def ui_create_test_run():
    agent_id = request.form.get('agent_id')
    environment_id = request.form.get('environment_id')
    logger.info(f"UI: Attempting to create TestRun via UI. Agent ID: {agent_id}, Env ID: {environment_id}")

    if not agent_id or not environment_id:
        flash('Agent and Environment must be selected.', 'error')
        logger.warning("UI: Create TestRun failed - agent/env not selected.")
        return redirect(url_for('main.ui_test_runs'))

    from ptplatform.app import create_app
    app = create_app()
    with app.test_client() as client:
        # The API call itself is already logged extensively by the API endpoint, so no need to re-log success/failure here specifically.
        api_response = client.post('/api/testruns', json={
            'agent_id': agent_id,
            'environment_id': environment_id
        })
        response_data = api_response.get_json()

        if api_response.status_code == 201 and response_data.get("run_id"):
            flash(f"Test Run {response_data.get('run_id')} process initiated. Status: {response_data.get('status')}", 'success')
            logger.info(f"UI: TestRun {response_data.get('run_id')} initiated via UI. Final API status: {response_data.get('status')}")
        elif response_data and response_data.get("error"): # Check response_data before get
             flash(f"Failed to start Test Run: {response_data.get('error')}", 'error')
             logger.error(f"UI: TestRun initiation via UI failed. API Error: {response_data.get('error')}")
        else: # Fallback for other errors
            flash(f"Error starting test run. Status: {api_response.status_code}, Response: {api_response.data.decode()}", 'error')
            logger.error(f"UI: TestRun initiation via UI failed. API Status: {api_response.status_code}, Raw Resp: {api_response.data.decode()}")

    return redirect(url_for('main.ui_test_runs'))

@main_blueprint.route('/ui/testruns/<int:run_id>')
def ui_test_run_detail(run_id):
    logger.info(f"UI: Accessing details for TestRun ID: {run_id}")
    run_data_query = db.session.query(TestRun, Agent.name, TestEnvironment.name).        join(Agent, TestRun.agent_id == Agent.id).        join(TestEnvironment, TestRun.environment_id == TestEnvironment.id).        filter(TestRun.id == run_id).first()

    if run_data_query:
        run, agent_name, env_name = run_data_query
        findings_list = []
        for f in run.findings.order_by(Finding.id.asc()).all():
            findings_list.append({
                'id': f.id, 'timestamp': f.timestamp.isoformat(sep=' ', timespec='seconds'),
                'finding_type': f.finding_type, 'description': f.description,
                'location_url': f.location_url, 'evidence': f.evidence,
                'severity': f.severity, 'cwe_id': f.cwe_id
            })
        run_detail = {
            'id': run.id, 'agent_id': run.agent_id, 'agent_name': agent_name,
            'environment_id': run.environment_id, 'environment_name': env_name,
            'status': run.status,
            'start_time': run.start_time.isoformat(sep=' ', timespec='seconds') if run.start_time else None,
            'end_time': run.end_time.isoformat(sep=' ', timespec='seconds') if run.end_time else None,
            'target_url': run.target_url, 'active_container_id': run.active_container_id,
            'active_container_name': run.active_container_name,
            'results_summary': run.results_summary, 'findings': findings_list
        }
        return render_template('test_run_detail.html', run=run_detail)
    else:
        flash(f"Test Run with ID {run_id} not found.", 'error')
        logger.warning(f"UI: TestRun ID {run_id} not found for detail view.")
        return redirect(url_for('main.ui_test_runs'))
