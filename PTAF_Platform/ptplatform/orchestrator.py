import docker
import time
import platform
import logging

logger = logging.getLogger(__name__)

try:
    logger.info("Attempting to connect to Docker via docker.from_env().")
    client = docker.from_env()
    if not client.ping():
        raise docker.errors.DockerException("client.ping() returned False with from_env()")
    logger.info("Successfully connected to Docker via docker.from_env().")
except Exception as e:
    logger.warning(f"Failed to connect via docker.from_env(): {e!r}", exc_info=True) # Added exc_info here too
    client = None
    if platform.system() == "Windows":
        logger.info("Attempting to connect to Docker via known Windows named pipes...")
        named_pipes_to_try = [
            'npipe:////./pipe/dockerDesktopLinuxEngine',
            'npipe:////./pipe/docker_engine'
        ]
        for pipe in named_pipes_to_try:
            try:
                logger.info(f"Attempting connection via named pipe: {pipe}")
                # Increased timeout and will log detailed error for this specific attempt
                temp_client = docker.DockerClient(base_url=pipe, timeout=10)
                logger.info(f"Pinging Docker daemon at {pipe}...")
                if not temp_client.ping():
                    logger.warning(f"Ping to {pipe} returned False/None.")
                    raise docker.errors.DockerException(f"client.ping() returned False/None with {pipe}")
                client = temp_client
                logger.info(f"Successfully connected to Docker via named pipe: {pipe}")
                break
            except Exception as pipe_e:
                # Log the full exception for this specific pipe attempt
                logger.error(f"Detailed error connecting via {pipe}: {pipe_e!r}", exc_info=True)
                client = None # Ensure client is None if this attempt failed

        if not client:
            logger.error("Failed to connect via all known Windows named pipes.")
            # This is the exception the user saw last
            raise docker.errors.DockerException(
                "Could not connect to Docker daemon on Windows. Please ensure Docker Desktop is running and accessible, "
                "and that the named pipes are available if not using default from_env(). "
                "Check logs for detailed errors from individual pipe connection attempts."
            )
    else:
        logger.error(f"docker.from_env() failed on non-Windows OS ({platform.system()}). Ensure Docker is configured correctly and accessible: {e!r}", exc_info=True)
        raise docker.errors.DockerException(f"Failed to connect to Docker on {platform.system()} via from_env(): {e!r}")


def list_vulnerable_apps():
    return [
        {"name": "DVWA", "image_name": "vulhub/dvwa", "description": "Damn Vulnerable Web Application"},
    ]

def start_environment(image_name, instance_name_prefix="ptaf_env_"):
    try:
        logger.info(f"Attempting to pull image: {image_name}")
        if not client:
            # This custom message might be more helpful if the above initialization failed
            logger.error("Cannot start environment: Docker client is not initialized. See previous connection errors.")
            raise docker.errors.DockerException("Docker client not initialized. Check connection logs.")

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
    except docker.errors.DockerException as e:
        logger.error(f"Docker operation error in start_environment: {e!r}", exc_info=True)
        try:
            if 'container' in locals() and container and hasattr(container, 'stop'):
                container.stop()
                container.remove()
        except Exception as cleanup_e:
            logger.error(f"Error during cleanup of container after failure in start_environment: {cleanup_e!r}", exc_info=True)
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error in start_environment: {e!r}", exc_info=True)
        return None, None


def stop_environment(container_id_or_name):
    try:
        if not client:
            logger.error("Cannot stop environment: Docker client is not initialized.")
            raise docker.errors.DockerException("Docker client not initialized. Check connection logs.")
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
    except docker.errors.DockerException as e:
        logger.error(f"Docker API Error while stopping/removing {container_id_or_name}: {e!r}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error in stop_environment for {container_id_or_name}: {e!r}", exc_info=True)
        return False

def get_running_environment_details(container_id_or_name):
    try:
        if not client:
            logger.error("Cannot get details: Docker client is not initialized.")
            raise docker.errors.DockerException("Docker client not initialized. Check connection logs.")
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
    except docker.errors.DockerException as e:
        logger.error(f"Docker API Error getting details for {container_id_or_name}: {e!r}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_running_environment_details for {container_id_or_name}: {e!r}", exc_info=True)
        return None

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

    logger.info("Orchestrator script direct execution started.")
    if not client: # This check will now happen after the robust initialization logic
        logger.error("Docker client failed to initialize after all attempts. Exiting example usage.")
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
