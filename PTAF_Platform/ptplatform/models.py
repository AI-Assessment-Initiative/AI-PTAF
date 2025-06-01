from .app import db
import datetime

class TestEnvironment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    docker_image = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return f'<TestEnvironment {self.name}>'

class Agent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Agent {self.name}>'

class Finding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_run_id = db.Column(db.Integer, db.ForeignKey('test_run.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    finding_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location_url = db.Column(db.String(500), nullable=True)
    evidence = db.Column(db.Text, nullable=True)
    severity = db.Column(db.String(50), nullable=False)
    cwe_id = db.Column(db.String(50), nullable=True)

    test_run = db.relationship('TestRun', backref=db.backref('findings', lazy='dynamic', cascade="all, delete-orphan"))

    def __repr__(self):
        return f'<Finding {self.id} - {self.finding_type} for TestRun {self.test_run_id}>'

class TestRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)
    environment_id = db.Column(db.Integer, db.ForeignKey('test_environment.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default="PENDING") # PENDING, STARTING, RUNNING, REPORTING, COMPLETED, FAILED, CLEANUP_FAILED
    results_summary = db.Column(db.Text, nullable=True)
    target_url = db.Column(db.String(500), nullable=True)

    # New fields for active container instance for this run
    active_container_id = db.Column(db.String(255), nullable=True)
    active_container_name = db.Column(db.String(255), nullable=True)

    agent = db.relationship('Agent', backref=db.backref('test_runs', lazy=True))
    environment = db.relationship('TestEnvironment', backref=db.backref('test_runs', lazy=True))

    def __repr__(self):
        return f'<TestRun {self.id} - Agent: {self.agent_id} Env: {self.environment_id} Status: {self.status}>'
