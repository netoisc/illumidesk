import asyncio
import docker
import json
import logging
import os
import sys

from filelock import FileLock
from pathlib import Path

from quart import Quart
from quart import request
from quart.exceptions import BadRequest

from .course import Course
from .utils import SetupUtils


logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Quart("setup-course-app")

configs_path = os.environ.get('JUPYTERHUB_CONFIG_PATH', '/srv/jupyterhub')

Path(configs_path).mkdir(exist_ok=True, parents=True)

JSON_FILE_PATH = configs_path + '/jupyterhub_config.json'

cache = {'services': [], 'load_groups': {}}


def initialize_service_definition_file(service_definitions: dict):
    with Path(JSON_FILE_PATH).open('w+') as current_services:
        json.dump(service_definitions, current_services)
        logger.debug('Service definitions file initialized.')


def is_grader_service_running(grader_name: str) -> bool:
    docker_client = docker.from_env()
    try:
        container = docker_client.containers.get(grader_name)
        return True if container.status == 'running' else False
    except docker.errors.NotFound:
        return False


def validate_services_running(service_definitions: list) -> None:
    for service in service_definitions['services']:
        if not is_grader_service_running(f"grader-{service['name']}"):
            # remove it from the cache/file ? or maybe start de container?
            logger.info(
                f"Detected a service definition {service['name']} in the file that is not running as a container"
            )


# if the service definition control file does not exist then create it
if not Path(JSON_FILE_PATH).exists() or Path(JSON_FILE_PATH).stat().st_size == 0:
    initialize_service_definition_file(cache)
else:
    with Path(JSON_FILE_PATH).open('r') as file:
        try:
            cache = json.load(file)
            logger.debug(f'Service definition file found and loaded from: {JSON_FILE_PATH}')
            logger.info(f'Service definition file content: {cache}')
        except json.JSONDecodeError as e:
            logger.error(f'Error reading the service definition file: {e}. This file will be initialized...')
            initialize_service_definition_file(cache)

    # check for each service if there is a container grader service in running state and remove it if not
    validate_services_running()


@app.route("/", methods=['POST'])
async def main():
    data = await request.get_json()
    if data is None:
        raise BadRequest()
    logger.debug('Received data payload %s' % data)
    try:
        new_course = Course(**data)
        await new_course.setup()
        update_jupyterhub_config(new_course)

    except Exception as e:
        logger.error("Unable to complete course setup", exc_info=True)
        return {'error': 500, 'detail': str(e)}
    return {'message': 'OK', 'is_new_setup': new_course.is_new_setup}


@app.route("/config", methods=['GET'])
def config():
    return json.dumps(cache)


@app.route("/rolling-update", methods=['POST'])
async def restart():
    logger.debug('Received request to make a rolling-update.')
    utils = SetupUtils()
    try:
        logger.debug('Restarting jupyterhub...')
        await asyncio.sleep(3)
        utils.restart_jupyterhub()
    except Exception as e:
        logger.error("Unable to restart the container", exc_info=True)
        return {'error': 500}
    return {'message': 'OK'}


def update_jupyterhub_config(course: Course):
    """
    We can add groups and users with the REST API, but not services. Therefore
    add new services to the JupyterHub.services section within the jupyterhub
    configuration file (jupyterhub_config.py).

    """
    jupyterhub_config_json = Path(JSON_FILE_PATH)
    # Lock file to manage jupyterhub_config.py
    jupyterhub_lock = os.environ.get('JUPYTERHUB_CONFIG_PATH') + '/jhub.lock'
    new_service_config = course.get_service_config()
    load_group = {f'formgrade-{course.course_id}': [course.grader_name]}
    logger.debug(f'Course service definition: {new_service_config}')

    # find the service definition
    current_service_definition = None
    for service in cache['services']:
        if service['url'] == new_service_config['url']:
            logger.debug(f"service definition with url:{service['url']} found in json file")
            current_service_definition = service

    if current_service_definition and course.is_new_setup:
        logger.debug(f'Updating the api_token in service definition with: {course.token}')
        # update the service definition with the newest token
        current_service_definition['api_token'] = course.token
    elif current_service_definition is None:
        cache['services'].append(new_service_config)

    cache['load_groups'].update(load_group)
    lock = FileLock(str(jupyterhub_lock))
    with lock:
        with jupyterhub_config_json.open('r+') as config:
            json.dump(cache, config)
