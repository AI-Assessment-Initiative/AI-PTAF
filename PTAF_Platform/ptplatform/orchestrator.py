import docker
import time

client = docker.from_env()

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
        print(f"Attempting to pull image: {image_name}")
        client.images.pull(image_name)
        print(f"Image {image_name} pulled successfully or already exists.")

        # Ensure unique container name to avoid conflicts
        # For simplicity, using image name and timestamp; a more robust naming/management strategy would be needed for concurrent tests
        container_name = f"{instance_name_prefix}{image_name.replace('/', '_').replace(':', '_')}_{int(time.time())}"

        print(f"Starting container {container_name} from image {image_name}...")
        # Standard port for DVWA is 80. We need to map it to a host port.
        # Using publish_all_ports=True for simplicity here, letting Docker assign a random host port.
        # For more control, specify port mapping: ports={'80/tcp': None} for random or {'80/tcp': specific_port}
        container = client.containers.run(
            image_name,
            detach=True,
            name=container_name,
            publish_all_ports=True # Expose all container ports to random host ports
        )
        print(f"Container {container.short_id} started. Waiting for it to be ready...")
        # Brief wait for the container to initialize - a more robust health check would be better
        time.sleep(10) # DVWA container can take a moment to start up its web server

        # Reload container attributes to get port information
        container.reload()
        # Assuming the service within the container runs on port 80 (standard for DVWA)
        # This logic might need adjustment based on the specific image and its exposed ports.
        # If multiple ports are exposed, we'd need to identify the correct one.
        host_port = None
        if container.attrs['NetworkSettings']['Ports']:
            # Taking the first port binding found for '80/tcp'
            # For vulhub/dvwa, the internal port is 80
            internal_port_key = '80/tcp'
            if internal_port_key in container.attrs['NetworkSettings']['Ports'] and \
                container.attrs['NetworkSettings']['Ports'][internal_port_key] is not None:
                host_port = container.attrs['NetworkSettings']['Ports'][internal_port_key][0]['HostPort']
            else: # Fallback if 80/tcp is not found or not mapped as expected, try first available
                for port_info_list in container.attrs['NetworkSettings']['Ports'].values():
                    if port_info_list:
                        host_port = port_info_list[0]['HostPort']
                        break

        if not host_port:
            print(f"Warning: Could not determine host port for container {container.short_id}. Manual check needed.")
            # Attempt to stop the container if port finding failed to avoid dangling resources
            container.stop()
            container.remove()
            return None, None

        print(f"Container {container.short_id} running on http://localhost:{host_port}")
        return container, f"http://localhost:{host_port}"

    except docker.errors.ImageNotFound:
        print(f"Error: Docker image {image_name} not found.")
        return None, None
    except docker.errors.APIError as e:
        print(f"Docker API Error: {e}")
        # Attempt to cleanup if container started but something else went wrong
        try:
            if 'container' in locals() and container:
                container.stop()
                container.remove()
        except docker.errors.NotFound:
            pass # Container might not exist or already removed
        return None, None

def stop_environment(container_id_or_name):
    """
    Stops and removes a container.
    """
    try:
        container = client.containers.get(container_id_or_name)
        print(f"Stopping container {container.short_id} ({container.name})...")
        container.stop()
        print(f"Removing container {container.short_id} ({container.name})...")
        container.remove()
        print(f"Container {container.short_id} ({container.name}) stopped and removed.")
        return True
    except docker.errors.NotFound:
        print(f"Error: Container {container_id_or_name} not found.")
        return False
    except docker.errors.APIError as e:
        print(f"Docker API Error: {e}")
        return False

def get_running_environment_details(container_id_or_name):
    """
    Gets details of a running container, including its mapped host port.
    """
    try:
        container = client.containers.get(container_id_or_name)
        container.reload() # Ensure attributes are up-to-date

        host_port = None
        url = None

        if container.attrs['NetworkSettings']['Ports']:
            internal_port_key = '80/tcp' # Assuming DVWA's default port
            if internal_port_key in container.attrs['NetworkSettings']['Ports'] and \
                container.attrs['NetworkSettings']['Ports'][internal_port_key] is not None:
                host_port = container.attrs['NetworkSettings']['Ports'][internal_port_key][0]['HostPort']
            else: # Fallback if 80/tcp is not found or not mapped as expected
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
        print(f"Error: Container {container_id_or_name} not found.")
        return None
    except docker.errors.APIError as e:
        print(f"Docker API Error: {e}")
        return None

# Example Usage (for testing orchestrator.py directly)
if __name__ == '__main__':
    print("Available Vulnerable App Images:")
    apps = list_vulnerable_apps()
    for app_info in apps:
        print(f"- {app_info['name']} (Image: {app_info['image_name']})")

    if not apps:
        print("No vulnerable apps configured to test.")
    else:
        chosen_app_image = apps[0]['image_name'] # Test with DVWA
        print(f"\nTesting with {chosen_app_image}...")

        container_obj, access_url = start_environment(chosen_app_image)

        if container_obj and access_url:
            print(f"Successfully started {chosen_app_image} with ID {container_obj.short_id} accessible at {access_url}")

            details = get_running_environment_details(container_obj.id)
            if details:
                print("\nContainer Details:")
                for key, value in details.items():
                    print(f"  {key}: {value}")

            print(f"\nStopping {container_obj.short_id} in 10 seconds...")
            time.sleep(10)
            stop_environment(container_obj.id)
            print(f"Test of {chosen_app_image} complete.")
        else:
            print(f"Failed to start or get details for {chosen_app_image}.")
