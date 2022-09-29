#!./venv_nano_local/bin/python

import json
import logging
from os import system
from os.path import dirname
from subprocess import call, run, check_output, CalledProcessError, STDOUT
import argparse
import copy
import time

from src.parse_nano_local_config import ConfigParser
from src.parse_nano_local_config import ConfigReadWrite
from src.nano_local_initial_blocks import InitialBlocks
from src.nano_block_ops import BlockAsserts
from src.nano_rpc import NanoRpc

# * create (this will create the one time resources that need creating)
# * start (this will start the nodes)
# * init (create an initial ledger structure common to all, epoch1 and 2 and canary blocks, etc)
# * test (run tests defined in nano_local_config.toml testcases)
# * pytest (run tests with pytest framework)
# * stop (stop all containers)
# * stop_nodes (stop the nodes but do not destroy anything)
# * restart (restart all nodes)
# * restart_wait_sync (restart all nodes and wait for 100% confirmed blocks)
# * reset (remove all blocks except genesis blocks by deleting data.ldb)
# * destroy (destroy all autogenerated resources, so that we can start from virgin state next time)

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] - %(message)s')

_conf_rw = ConfigReadWrite()
_conf = ConfigParser()
_node_path = {"container": "./nano_nodes"}


def get_default(config_name):
    """ Load config with default values"""
    #minimal node config if no file is provided in the nano_local_config.toml
    if config_name == "config_node":
        return {
            "rpc": {
                "enable": True
            },
            "node": {
                "allow_local_peers": True,
                "enable_voting": True
            }
        }
    elif config_name == "config_rpc":
        return {"enable_control": True, "enable_sign_hash": True}
    else:
        return {}


def create_node_folders(node_name):
    global _node_path

    commands = [
        "mkdir -p nano_nodes", f"cd nano_nodes && mkdir -p {node_name}",
        f"cd nano_nodes/{node_name} && mkdir -p NanoTest"
    ]

    if _conf.get_config_value("nanomonitor_enable"):
        commands.append(
            f"cd nano_nodes/{node_name} && mkdir -p nanoNodeMonitor")

    for command in commands:
        system(command)

    _node_path[node_name] = {
        "data_path": f"./nano_nodes/{node_name}/NanoTest",
        "config_node_path":
        f"./nano_nodes/{node_name}/NanoTest/config-node.toml",
        "config_rpc_path": f"./nano_nodes/{node_name}/NanoTest/config-rpc.toml"
    }


def write_config_node(node_name):
    config_node = _conf.get_config_from_path(node_name, "config_node_path")
    if config_node is None:
        logging.warning(
            "No config-node.toml found. minimal version was created")
        config_node = get_default("config_node")

    config_node["node"]["preconfigured_peers"] = _conf.preconfigured_peers
    _conf_rw.write_toml(_node_path[node_name]["config_node_path"], config_node)


def write_config_rpc(node_name):
    config_rpc = _conf.get_config_from_path(node_name, "config_rpc_path")
    if config_rpc is None:
        logging.warning(
            "No config-rpc.toml found. minimal version was created")
        config_rpc = get_default("config_rpc")

    _conf_rw.write_toml(_node_path[node_name]["config_rpc_path"], config_rpc)


def write_nanomonitor_config(node_name):
    if _conf.get_config_value("nanomonitor_enable"):
        _conf.write_nanomonitor_config(node_name)


def write_docker_compose_env(compose_version):
    #Read default env file
    conf_variables = _conf.config_dict
    env_variables = []
    genesis_block = generate_genesis_open(conf_variables['genesis_key'])
    s_genesis_block = str(genesis_block).replace("'", '"')

    if compose_version == 1:
        env_variables.append(f"'NANO_TEST_GENESIS_BLOCK={s_genesis_block}'")
    elif compose_version == 2:
        env_variables.append(f"NANO_TEST_GENESIS_BLOCK={s_genesis_block}")
    env_variables.append(f'NANO_TEST_GENESIS_PUB="{genesis_block["source"]}"')
    env_variables.append(
        f'NANO_TEST_CANARY_PUB="{_conf.key_expand(conf_variables["canary_key"])["public"]}"'
    )

    for key, value in conf_variables.items():
        if key.startswith("NANO_TEST_"):
            env_variables.append(f'{key}="{value}"')

    _conf_rw.write_list(f'{_node_path["container"]}/dc_nano_local_env',
                        env_variables)


def subprocess_read_lines(command):
    try:
        res = check_output(command,
                           shell=True,
                           stderr=STDOUT,
                           encoding='UTF-8')
    except CalledProcessError as e:
        raise RuntimeError(
            f"command '{e.cmd}' return with error (code {e.returncode}): {e.output}"
        )
    return res.splitlines()


def generate_genesis_open(genesis_key):
    #TODO find a less intrusive way to create a legacy open block.
    try:
        docker_exec = f"docker run --name ln_get_genesis nanocurrency/nano-beta:latest nano_node --network=dev --debug_bootstrap_generate --key={genesis_key} "
        docker_stop_rm = """docker stop ln_get_genesis 1>/dev/null &&
                            docker rm ln_get_genesis 1>/dev/null &"""

        logging.info("run temporary docker conatiner for genesis generation")
        blocks = ''.join(subprocess_read_lines(docker_exec)[104:112])
        logging.info("stop and remove docker container")
        call(docker_stop_rm, shell=True)
        return json.loads(str(blocks))

    except Exception as e:
        logging.error(str(e))
        system(docker_stop_rm)


def is_rpc_available(node_names):
    while len(node_names) > 0:
        containers = copy.deepcopy(node_names)
        for container in containers:
            cmd_rpc_url = f"docker port {container} | grep 17076/tcp | awk '{{print $3}}'"
            rpc_url = "http://" + str(
                subprocess_read_lines(cmd_rpc_url)[0:1][0]).strip()
            if NanoRpc(rpc_url).is_online(timeout=3):
                node_names.remove(container)
            else:
                logging.warning(
                    f"RPC {rpc_url} not yet reachable for node {container} ")
    logging.info(f"Nodes {_conf.get_nodes_name()} started successfully")


def prepare_nodes(genesis_node_name):
    #prepare genesis
    prepare_node_env(genesis_node_name)
    for node_name in _conf.get_nodes_name():
        prepare_node_env(node_name)


def prepare_node_env(node_name):
    node_name = node_name.lower()  #docker-compose requires lower case names
    create_node_folders(node_name)
    write_config_node(node_name)
    write_config_rpc(node_name)
    write_nanomonitor_config(node_name)


def init_nodes(genesis_node_name="nl_genesis"):

    start_nodes()  #fixes a bug on mac m1
    init_blocks = InitialBlocks()
    for node_name in _conf.get_nodes_name():
        if node_name == genesis_node_name:
            init_blocks.create_node_wallet(
                _conf.get_node_config(genesis_node_name)["rpc_url"],
                genesis_node_name,
                private_key=_conf.config_dict["genesis_key"])
        else:
            init_blocks.create_node_wallet(
                _conf.get_node_config(node_name)["rpc_url"],
                node_name,
                seed=_conf.get_node_config(node_name)["seed"])

    init_blocks.publish_initial_blocks()


def create_nodes(compose_version, genesis_node_name="nl_genesis"):
    prepare_nodes(genesis_node_name=genesis_node_name)
    write_docker_compose_env(compose_version)
    _conf.set_docker_compose_services(genesis_node_name)
    _conf.write_docker_compose()
    _conf.print_enabled_services()


def start_all(build_f):
    dir_nano_nodes = _node_path["container"]
    command = f'cd {dir_nano_nodes} && docker-compose up -d'
    if build_f:
        command = f'cd {dir_nano_nodes} && docker-compose up -d --build'
    system(command)
    time.sleep(2)
    is_rpc_available(_conf.get_nodes_name())


def start_prom():
    if not _conf.get_config_value("promexporter_enable"): return
    dir_nano_nodes = _node_path["container"]
    prom_exporter = ' '.join([f'{x}_exporter' for x in _conf.get_nodes_name()])
    command = f'cd {dir_nano_nodes} && docker-compose start {prom_exporter}'
    system(command)


def start_prom_stack():
    if not _conf.get_config_value("promexporter_enable"): return
    if _conf.get_config_value("prom_gateway") == "nl_pushgateway:9091":
        dir_nano_nodes = _node_path["container"]
        command = f'cd {dir_nano_nodes} && docker-compose start nl_prometheus nl_grafana nl_pushgateway'
        system(command)


def stop_prom():
    if not _conf.get_config_value("promexporter_enable"): return
    dir_nano_nodes = _node_path["container"]
    prom_exporter = ' '.join([f'{x}_exporter' for x in _conf.get_nodes_name()])
    command = f'cd {dir_nano_nodes} && docker-compose stop {prom_exporter}'
    system(command)


def build_nodes():
    dir_nano_nodes = _node_path["container"]
    nodes = ' '.join(_conf.get_nodes_name())
    command = f'cd {dir_nano_nodes} && docker-compose build {nodes}'
    system(command)
    logging.getLogger().success(f"nodes [{nodes}] built")


def start_nodes():
    ''' start nodes '''
    dir_nano_nodes = _node_path["container"]
    nodes = ' '.join(_conf.get_nodes_name())
    command = f'cd {dir_nano_nodes} && docker-compose start {nodes}'
    system(command)
    start_prom()  #prom depends on node PID. SHould be started after node
    is_rpc_available(_conf.get_nodes_name())


def stop_all():
    ''' stop all services '''
    dir_nano_nodes = _node_path["container"]
    command = f'cd {dir_nano_nodes} && docker-compose stop'
    system(command)


def stop_nodes():
    ''' stop nodes '''
    stop_prom()  #prom depends on node PID should be stopped before node.
    dir_nano_nodes = _node_path["container"]
    nodes = ' '.join(_conf.get_nodes_name())
    command = f'cd {dir_nano_nodes} && docker-compose stop {nodes}'
    system(command)


def restart_nodes():
    ''' restart nodes '''
    stop_nodes()
    start_nodes()


def restart_wait_sync():
    ''' restart nodes and wait until 100% of blocks are confirmed'''
    ba = BlockAsserts()
    all_cemented = False
    while not all_cemented:
        try:
            block_count = ba.assert_all_blocks_cemented()
            all_cemented = True
        except AssertionError:
            logging.info("Not all blocks cemented... restarting nodes.")
            restart_nodes()
            time.sleep(10)
    logging.getLogger().success(
        f'All {block_count["cemented"]} blocks are cemented')


def reset_nodes():
    stop_nodes()
    dir_nano_nodes = _node_path["container"]
    commands = [
        f'cd {dir_nano_nodes} && find . -name "data.ldb"  -type f -delete',
        f'cd {dir_nano_nodes} && find . -name "wallets.ldb"  -type f -delete'
    ]

    for command in commands:
        system(command)
    start_nodes()


def destroy_all():
    dir_nano_nodes = _node_path["container"]
    commands = [
        f'cd {dir_nano_nodes} && docker-compose down',  #stop all nodes
        'rm -rf ./nano_nodes',  #remove all nodes and their configs
        'rm -rf ./__pycache__',
        'rm -rf ./venv_nano_local'
    ]  #remove python virtual environemtn

    for command in commands:
        system(command)


def run_pytest(output, args):
    modules = _conf.get_testcases()["test_modules"]
    for module in modules:
        module_path = f'{dirname(__file__)}/testcases/{module}.py'
        output = ""
        if (output) == "html":
            output = f"--html=./testcases/reports/report_latest_{module}.html --self-contained-html"
        elif (output) == "xml":
            output = f"--junitxml=./testcases/reports/report_latest_{module}.xml"
        print(f"venv_nano_local/bin/pytest {args} {module_path} {output}")
        run([f"venv_nano_local/bin/pytest {args} {module_path} {output}"],
            shell=True)


def run_test():
    modules = _conf.get_testcases()["test_modules"]
    for module in modules:
        run([f"venv_nano_local/bin/python -m unittest -v testcases.{module}"],
            shell=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-b',
                        '--build',
                        type=bool,
                        default=False,
                        help='build docker container for new executable')
    parser.add_argument(
        '--output',
        choices={"console", "html", "xml"},
        default="html",
        help=
        'create a report under ./testcases/reports in the specified format for each module'
    )
    parser.add_argument('--loglevel',
                        choices={"DEBUG", "INFO", "WARNING", "ERROR"},
                        default="INFO",
                        help='set log level. defaults to INFO')
    parser.add_argument('--args',
                        default="-v -rpf",
                        help='will be added after pytest. example -rfE')
    parser.add_argument(
        '--compose_version',
        type=int,
        default=2,
        choices={1, 2},
        help=
        'run $ docker-compose --version to identify the version. Defaults to 2'
    )
    parser.add_argument('--runid',
                        default="default",
                        help='if prom-exporter is enabled, sets the run id')
    parser.add_argument('command',
                        help='create , start, init, stop, reset, destroy',
                        default='create')
    return parser.parse_args()


# #DEBUG : put def parse_args() into comment and set the command you wish to run
# def parse_args():
#     return argClass

# class argClass:
#     command = "create"
#     compose_version = 2
#     loglevel = "INFO"
#     runid = ""


def set_log_level(loglevel):
    if loglevel == "DEBUG":
        logging.basicConfig(level=logging.DEBUG)
    elif loglevel == "INFO":
        logging.basicConfig(level=logging.INFO)
    elif loglevel == "WARNING":
        logging.basicConfig(level=logging.WARNING)
    elif loglevel == "ERROR":
        logging.basicConfig(level=logging.ERROR)

    # set success level
    logging.SUCCESS = 25  # between WARNING and INFO
    logging.addLevelName(logging.SUCCESS, 'SUCCESS')
    setattr(
        logging.getLogger(), 'success',
        lambda message, *args: logging.getLogger()._log(
            logging.SUCCESS, message, args))


def main():

    args = parse_args()
    set_log_level(args.loglevel)
    _conf.set_prom_runid(args.runid)

    if args.command == 'csi':  #c(reate) s(tart) i(nit)
        create_nodes(args.compose_version)
        start_all(True)
        init_nodes()
        restart_nodes()
    elif args.command == 'create':
        create_nodes(args.compose_version)
        logging.getLogger().success("./nano_nodes directory was created")

    elif args.command == 'build_nodes':
        stop_nodes()
        build_nodes()
        start_nodes()
        logging.getLogger().success("nodes built & started")

    elif args.command == 'start':
        start_all(args.build)
        logging.getLogger().success("all containers started")

    elif args.command == 'start_prom':
        start_prom()
        logging.getLogger().success("prom-exporter containers started")

    elif args.command == 'start_prom_stack':
        start_prom_stack()
        logging.getLogger().success("prom-stack containers started")

    elif args.command == 'init':
        init_nodes()
        #restart_nodes()
        logging.getLogger().success("ledger initialized")

    elif args.command == 'stop':
        stop_all()
        logging.getLogger().success("all containers stopped")

    elif args.command == 'stop_nodes':
        stop_nodes()
        logging.getLogger().success("nodes stopped")

    elif args.command == 'restart':
        restart_nodes()
        logging.getLogger().success("nodes restarted")

    elif args.command == 'restart_wait_sync':
        restart_wait_sync()

    elif args.command == 'reset':
        reset_nodes()
        logging.getLogger().success("data.ldb deleted")

    elif args.command == 'destroy':
        destroy_all()
        logging.getLogger().success("all destroyed")

    elif args.command == 'pytest':
        run_pytest(args.output, args.args)

    elif args.command == 'test':
        run_test()
    else:
        print(f'Unknown command {args.command}')


if __name__ == "__main__":
    main()