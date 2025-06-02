import docker
import time
import platform # Import platform module
import logging # It's good practice to log these attempts

logger = logging.getLogger(__name__)

# Attempt to initialize Docker client with fallback for Windows
try:
    logger.info("Attempting to connect to Docker via docker.from_env().")
    client = docker.from_env()
    # Perform a quick test to see if it's working
    if not client.ping(): # client.ping() returns True on success, raises on failure
        raise docker.errors.DockerException("client.ping() returned False with from_env()")
    logger.info("Successfully connected to Docker via docker.from_env().")
except Exception as e:
    logger.warning(f"Failed to connect via docker.from_env(): {e}")
    client = None # Ensure client is None before trying alternatives
    if platform.system() == "Windows":
        logger.info("Attempting to connect to Docker via known Windows named pipes...")
        named_pipes_to_try = [
            'npipe:////./pipe/dockerDesktopLinuxEngine', # For Docker Desktop with WSL2
            'npipe:////./pipe/docker_engine'           # For Docker Engine or older Docker Desktop
        ]
        for pipe in named_pipes_to_try:
            try:
                logger.info(f"Attempting connection via named pipe: {pipe}")
                temp_client = docker.DockerClient(base_url=pipe, timeout=5) # Lower timeout for faster checks
                if not temp_client.ping():
                    raise docker.errors.DockerException(f"client.ping() returned False with {pipe}")
                client = temp_client # Assign to the main client variable
                logger.info(f"Successfully connected to Docker via named pipe: {pipe}")
                break # Stop if successful
            except Exception as pipe_e:
                logger.warning(f"Failed to connect via {pipe}: {pipe_e}")

        if not client:
            logger.error("Failed to connect via all known Windows named pipes.")
            raise docker.errors.DockerException(
                "Could not connect to Docker daemon on Windows. "
                "Please ensure Docker Desktop is running and accessible, "
                "and that the named pipes are available if not using default from_env()."
            )
    else: # For non-Windows, if from_env fails, re-raise the original error or a more generic one
        logger.error(f"docker.from_env() failed on non-Windows OS ({platform.system()}). Ensure Docker is configured correctly and accessible.")
        # Re-raising the original exception 'e' preserves its specific type and message
        raise docker.errors.DockerException(f"Failed to connect to Docker on {platform.system()} via from_env(): {e}")


def list_vulnerable_apps():
    # In the future, this could list images based on some tagging convention or from the database
    # For now, it's a hardcoded list of what we plan to support initially.
    return [
        {"name": "DVWA", "image_name": "vulhub/dvwa", "description": "Damn Vulnerable Web Application"},
        # {"name": "OWASP Juice Shop", "image_name": "bkimminich/juice-shop", "description": "OWASP Juice Shop"} # Add later
    ]

def start_environment(image_name, instance_name_prefix="ptaf_env_"):
    """
    Starts a new container for the given docker image.
    Returns the container object and the port it's running on.
    """
    try:
        logger.info(f"Attempting to pull image: {image_name}")
        # Ensure client is available
        if not client:
            raise docker.errors.DockerException("Docker client not initialized.")

        client.images.pull(image_name)
        logger.info(f"Image {image_name} pulled successfully or already exists.")

        container_name = f"{instance_name_prefix}{image_name.replace('/', '_').replace(':', '_')}_{int(time.time())}"

        logger.info(f"Starting container {container_name} from image {image_name}...")
        container = client.containers.run(
            image_name,
            detach=True,
            name=container_name,
            publish_all_ports=True
        )
        logger.info(f"Container {container.short_id} started. Waiting for it to be ready...")
        time.sleep(10)

        container.reload()
        host_port = None
        if container.attrs['NetworkSettings']['Ports']:
            internal_port_key = '80/tcp'
            if internal_port_key in container.attrs['NetworkSettings']['Ports'] and \
                container.attrs['NetworkSettings']['Ports'][internal_port_key] is not None:
                host_port = container.attrs['NetworkSettings']['Ports'][internal_port_key][0]['HostPort']
            else:
                for port_info_list in container.attrs['NetworkSettings']['Ports'].values():
                    if port_info_list:
                        host_port = port_info_list[0]['HostPort']
                        break

        if not host_port:
            logger.warning(f"Could not determine host port for container {container.short_id}. Manual check needed.")
            container.stop()
            container.remove()
            return None, None

        logger.info(f"Container {container.short_id} running on http://localhost:{host_port}")
        return container, f"http://localhost:{host_port}"

    except docker.errors.ImageNotFound:
        logger.error(f"Docker image {image_name} not found.")
        return None, None
    except docker.errors.DockerException as e: # Catch DockerException explicitly
        logger.error(f"Docker operation error: {e}", exc_info=True) # exc_info=True for stack trace in log
        # Attempt to cleanup if container started but something else went wrong
        try:
            if 'container' in locals() and container and hasattr(container, 'stop'): # Check if container object exists and has stop method
                container.stop()
                container.remove()
        except Exception as cleanup_e: # Broad exception for cleanup attempt
            logger.error(f"Error during cleanup of container after failure: {cleanup_e}", exc_info=True)
        return None, None
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error in start_environment: {e}", exc_info=True)
        return None, None


def stop_environment(container_id_or_name):
    """
    Stops and removes a container.
    """
    try:
        if not client:
            raise docker.errors.DockerException("Docker client not initialized.")
        container = client.containers.get(container_id_or_name)
        logger.info(f"Stopping container {container.short_id} ({container.name})...")
        container.stop()
        logger.info(f"Removing container {container.short_id} ({container.name})...")
        container.remove()
        logger.info(f"Container {container.short_id} ({container.name}) stopped and removed.")
        return True
    except docker.errors.NotFound:
        logger.warning(f"Container {container_id_or_name} not found for stopping.")
        return False
    except docker.errors.DockerException as e: # Catch DockerException explicitly
        logger.error(f"Docker API Error while stopping/removing {container_id_or_name}: {e}", exc_info=True)
        return False
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error in stop_environment for {container_id_or_name}: {e}", exc_info=True)
        return False

def get_running_environment_details(container_id_or_name):
    """
    Gets details of a running container, including its mapped host port.
    """
    try:
        if not client:
            raise docker.errors.DockerException("Docker client not initialized.")
        container = client.containers.get(container_id_or_name)
        container.reload()

        host_port = None
        url = None

        if container.attrs['NetworkSettings']['Ports']:
            internal_port_key = '80/tcp'
            if internal_port_key in container.attrs['NetworkSettings']['Ports'] and \
                container.attrs['NetworkSettings']['Ports'][internal_port_key] is not None:
                host_port = container.attrs['NetworkSettings']['Ports'][internal_port_key][0]['HostPort']
            else:
                for port_info_list in container.attrs['NetworkSettings']['Ports'].values():
                    if port_info_list:
                        host_port = port_info_list[0]['HostPort']
                        break
            if host_port:
                url = f"http://localhost:{host_port}"

        return {
            "id": container.id,
            "name": container.name,
            "image": container.attrs['Config']['Image'],
            "status": container.status,
            "url": url,
            "ports": container.attrs['NetworkSettings']['Ports']
        }
    except docker.errors.NotFound:
        logger.warning(f"Container {container_id_or_name} not found for getting details.")
        return None
    except docker.errors.DockerException as e: # Catch DockerException explicitly
        logger.error(f"Docker API Error getting details for {container_id_or_name}: {e}", exc_info=True)
        return None
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error in get_running_environment_details for {container_id_or_name}: {e}", exc_info=True)
        return None

# Example Usage (for testing orchestrator.py directly)
if __name__ == '__main__':
    # Basic logging for direct script execution
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    logger.info("Orchestrator script direct execution started.")
    if not client:
        logger.error("Docker client failed to initialize. Exiting example usage.")
    else:
        logger.info("Docker client initialized successfully for direct execution.")
        logger.info("Available Vulnerable App Images:")
        apps = list_vulnerable_apps()
        for app_info in apps:
            logger.info(f"- {app_info['name']} (Image: {app_info['image_name']})")

        if not apps:
            logger.info("No vulnerable apps configured to test.")
        else:
            chosen_app_image = apps[0]['image_name']
            logger.info(f"\nTesting with {chosen_app_image}...")

            container_obj, access_url = start_environment(chosen_app_image)

            if container_obj and access_url:
                logger.info(f"Successfully started {chosen_app_image} with ID {container_obj.short_id} accessible at {access_url}")

                details = get_running_environment_details(container_obj.id)
                if details:
                    logger.info("\nContainer Details:")
                    for key, value in details.items():
                        logger.info(f"  {key}: {value}")

                logger.info(f"\nStopping {container_obj.short_id} in 10 seconds...")
                time.sleep(10)
                stop_environment(container_obj.id)
                logger.info(f"Test of {chosen_app_image} complete.")
            else:
                logger.error(f"Failed to start or get details for {chosen_app_image}.")
    logger.info("Orchestrator script direct execution finished.")
