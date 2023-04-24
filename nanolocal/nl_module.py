#!./venv_nanolocal/bin/python

import json
import logging
from os.path import dirname, exists as path_exists
from os import getuid
from subprocess import call, run, check_output, CalledProcessError, STDOUT, PIPE
import copy
import time
import sys

from nanolocal.common.nl_parse_config import ConfigParser
from nanolocal.common.nl_parse_config import ConfigReadWrite
from nanolocal.common.nl_initialise import InitialBlocks
from nanolocal.common.nl_block_tools import BlockAsserts
from nanolocal.common.nl_nanolib import NanoLibTools
from nanolocal.common.nl_rpc import NanoRpc

# * create (this will create the one time resources that need creating)
# * start (this will start the nodes)
# * init (create an initial ledger structure common to all, epoch1 and 2 and canary blocks, etc)
# * test (run tests defined in nl_config.toml testcases)
# * pytest (run tests with pytest framework)
# * stop (stop all containers)
# * stop_nodes (stop the nodes but do not destroy anything)
# * restart (restart all nodes)
# * restart_wait_sync (restart all nodes and wait for 100% confirmed blocks)
# * reset (remove all blocks except genesis blocks by deleting data.ldb)
# * destroy (destroy all autogenerated resources, so that we can start from virgin state next time)

_conf_rw = ConfigReadWrite()
_nano_lib = NanoLibTools()
_conf = ConfigParser()
_default_path = "./nanolocal"
_node_path = {
    "container": f"{_default_path}/nano_nodes",
    "compose": f"{_default_path}/nano_nodes/docker-compose.yml"
}


class nl_runner():

    def __init__(self, loglevel="INFO"):
        self.set_log_level(loglevel)  #"DEBUG", "INFO", "WARNING", "ERROR"

    def get_default(self, config_name):
        """ Load config with default values"""
        #minimal node config if no file is provided in the nl_config.toml
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

    def create_node_folders(self, node_name):
        global _node_path

        commands = [
            f"cd {_default_path} && mkdir -p nano_nodes",
            f"cd {_default_path}/nano_nodes && mkdir -p {node_name}",
            f"cd {_default_path}/nano_nodes/{node_name} && mkdir -p NanoTest"
        ]

        if _conf.get_config_value("nanomonitor_enable"):
            commands.append(
                f"cd {_default_path}/nano_nodes/{node_name} && mkdir -p nanoNodeMonitor"
            )

        for command in commands:
            self.run_shell_command(command)

        _node_path[node_name] = {
            "data_path":
            f"{_default_path}/nano_nodes/{node_name}/NanoTest",
            "config_node_path":
            f"{_default_path}/nano_nodes/{node_name}/NanoTest/config-node.toml",
            "config_rpc_path":
            f"{_default_path}/nano_nodes/{node_name}/NanoTest/config-rpc.toml"
        }

    def write_config_node(self, node_name):
        config_node = _conf.get_config_from_path(node_name, "config_node_path")
        if config_node is None:
            logging.warning(
                "No config-node.toml found. minimal version was created")
            config_node = self.get_default("config_node")

        config_node["node"]["preconfigured_peers"] = _conf.preconfigured_peers
        _conf_rw.write_toml(_node_path[node_name]["config_node_path"],
                            config_node)

    def write_config_rpc(self, node_name):
        config_rpc = _conf.get_config_from_path(node_name, "config_rpc_path")
        if config_rpc is None:
            logging.warning(
                "No config-rpc.toml found. minimal version was created")
            config_rpc = self.get_default("config_rpc")

        _conf_rw.write_toml(_node_path[node_name]["config_rpc_path"],
                            config_rpc)

    def write_nanomonitor_config(self, node_name):
        if _conf.get_config_value("nanomonitor_enable"):
            _conf.write_nanomonitor_config(node_name)

    def write_docker_compose_env(self, compose_version):
        #Read default env file
        conf_variables = _conf.config_dict
        env_variables = []
        genesis_block = json.loads(_conf.get_genesis_block())
        s_genesis_block = str(genesis_block).replace("'", '"')

        #Set genesis block
        if compose_version == 1:
            env_variables.append(
                f"'NANO_TEST_GENESIS_BLOCK={s_genesis_block}'")
        elif compose_version == 2:
            env_variables.append(f"NANO_TEST_GENESIS_BLOCK={s_genesis_block}")

        env_variables.append(
            f'NANO_TEST_GENESIS_PUB="{genesis_block["source"]}"')
        env_variables.append(
            f'NANO_TEST_CANARY_PUB="{_conf.get_canary_pub_key()}"')

        for key, value in conf_variables.items():
            if key.startswith("NANO_TEST_"):
                env_variables.append(f'{key}="{value}"')

        _conf_rw.write_list(f'{_node_path["container"]}/dc_nano_local_env',
                            env_variables)

    def run_shell_command(self, command, ignore_error=""):
        logging.debug(f"Shell command : [{command}]")
        shell_reponse = run(command, shell=True, encoding="utf-8", stderr=PIPE)
        status = shell_reponse.returncode
        stderr = shell_reponse.stderr.replace("\n", "")

        if ignore_error == stderr:
            status = 0
        if status == 1:  #retry once
            print("======== RETRY =======\n", command, "| status:", status,
                  "| error:", shell_reponse.stderr)
            status = call(command, shell=True)
        elif status != 0:
            print(stderr)
            raise Exception(f"{command} failed with status:{status}")

    def subprocess_read_lines(self, command):
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

    def is_all_containers_online(self, node_names):

        containers_online = 0
        online_containers = []
        for container in node_names:
            cmd = f"docker ps |grep {container}$ | wc -l"
            res = int(self.subprocess_read_lines(cmd)[0:1][0])
            if res == 1:
                online_containers.append(container)
            containers_online = containers_online + res
        if len(node_names) == containers_online:
            return {
                "success": True,
                "online_containers": online_containers,
                "msg": f"All {containers_online} containers online"
            }
        else:
            return {
                "success": False,
                "online_containers": online_containers,
                "msg":
                f"{containers_online}/{len(node_names)} containers online"
            }

    def is_rpc_available(self, node_names, wait=True):
        repeat = True  #only query once if wait == false
        max_timeout_s = 15
        start_time = time.time()
        while len(node_names) > 0 and repeat:
            repeat = wait
            containers = copy.deepcopy(node_names)
            for container in containers:
                cmd_rpc_url = f"docker port {container} | grep 17076/tcp | awk '{{print $3}}'"
                response = self.subprocess_read_lines(cmd_rpc_url)
                #test that container is currently online
                if len(response) > 0:
                    #use the url defined in the config (allows to run in a dockerized github runner)
                    rpc_url = _conf.get_node_rpc(container)

                    if NanoRpc(rpc_url).is_online(timeout=3):
                        node_names.remove(container)
                    else:
                        log_message = f"RPC {rpc_url} not yet reachable for node {container} docker_version: {_conf.get_docker_tag(container)}"
                        if time.time() - start_time > max_timeout_s:
                            raise ValueError("TIMEOUT:" + log_message)
                        logging.warning(log_message)
                else:
                    log_message = f"No RPC ({response}) is available for  node {container} docker_version: {_conf.get_docker_tag(container)}"
                    if time.time() - start_time > max_timeout_s:
                        raise ValueError("TIMEOUT:" + log_message)
                    logging.warning(log_message)
                    time.sleep(1)

        logging.info(f"Nodes {_conf.get_nodes_name()} reachable")

    def get_nodes_name(self, node_name, as_string=True, suffix=""):
        result = [node_name]
        if as_string:
            result = node_name

        if node_name == 'all':
            result = [f'{x}{suffix}' for x in _conf.get_nodes_name()]
            if as_string:
                result = ' '.join(result)

        return result

    def validate_config(self, action):
        response = True
        if action == "create":
            for node in _conf.get_nodes_name():
                if _conf.get_docker_tag(None) == "" and _conf.get_docker_tag(
                        node) == "":
                    logging.error(
                        f"Config error : docker_tag can't be empty for node {node}"
                    )
                    response = False
        return response

    def prepare_nodes(self):
        #prepare genesis
        for node_name in _conf.get_nodes_name():
            self.prepare_node_env(node_name)

    def prepare_node_env(self, node_name):
        node_name = node_name.lower(
        )  #docker-compose requires lower case names
        self.create_node_folders(node_name)
        self.write_config_node(node_name)
        self.write_config_rpc(node_name)
        self.write_nanomonitor_config(node_name)

    def init_wallets(self):
        #self.start_nodes('all')  #fixes a bug on mac m1
        init_blocks = InitialBlocks(rpc_url=_conf.get_nodes_rpc()[0])
        for node_name in _conf.get_nodes_name():
            if node_name == _conf.get_genesis_node_name():
                init_blocks.create_node_wallet(
                    _conf.get_node_config(
                        _conf.get_genesis_node_name())["rpc_url"],
                    _conf.get_genesis_node_name(),
                    private_key=_conf.config_dict["genesis_key"])
            else:
                init_blocks.create_node_wallet(
                    _conf.get_node_config(node_name)["rpc_url"],
                    node_name,
                    seed=_conf.get_node_config(node_name)["seed"])

    def init_nodes(self):

        self.init_wallets()
        init_blocks = InitialBlocks(rpc_url=ConfigParser().get_nodes_rpc()[0])
        init_blocks.publish_initial_blocks()

    def create_nodes(self, compose_version):
        global _conf
        _conf = ConfigParser()
        if not self.validate_config('create'):
            return False
        self.prepare_nodes()
        self.write_docker_compose_env(compose_version)
        _conf.set_docker_compose()
        #_conf.set_docker_compose_services()
        _conf.write_docker_compose()
        _conf.print_enabled_services()
        if getuid not in [0, 1000]: self.build_nodes('all')
        return True
        #workaround to take changes from docker_tag into account

    def start_all(self, build_f):
        dir_nano_nodes = _node_path["container"]
        #self.run_shell_command(f'cd {dir_nano_nodes} && docker-compose pull')
        command = f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} up -d '
        if build_f:
            command = f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} up -d --build'
        self.run_shell_command(command)
        time.sleep(2)
        self.is_rpc_available(self.get_nodes_name('all', as_string=False))

    def start_prom(self, node_name):
        if not _conf.get_config_value("promexporter_enable"): return False
        dir_nano_nodes = _node_path["container"]
        prom_exporter = self.get_nodes_name(node_name, suffix="_exporter")
        command = f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} start {prom_exporter}'
        self.run_shell_command(command)
        return True

    def start_prom_stack(self):
        if not _conf.get_config_value("promexporter_enable"): return False
        if _conf.get_config_value("prom_gateway") == "nl_pushgateway:9091":
            dir_nano_nodes = _node_path["container"]
            command = f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} start nl_prometheus nl_grafana nl_pushgateway'
            self.run_shell_command(command)
        return True

    def stop_prom(self, node_name):
        if not _conf.get_config_value("promexporter_enable"): return False
        dir_nano_nodes = _node_path["container"]
        prom_exporter = self.get_nodes_name(node_name, suffix="_exporter")
        command = f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} stop {prom_exporter}'
        self.run_shell_command(command)
        return True

    def build_nodes(self, node_name):
        dir_nano_nodes = _node_path["container"]
        nodes = self.get_nodes_name(node_name)
        command = f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} build {nodes}'
        self.run_shell_command(command)
        logging.getLogger().success(f"nodes [{nodes}] built")

    def start_nodes(self, node):
        ''' start nodes '''
        dir_nano_nodes = _node_path["container"]
        nodes = self.get_nodes_name(node)
        command = f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} start {nodes}'
        self.run_shell_command(command)
        self.start_prom(
            node)  #prom depends on node PID. SHould be started after node
        self.is_rpc_available(self.get_nodes_name(node, as_string=False))

    def stop_all(self):
        ''' stop all services '''
        dir_nano_nodes = _node_path["container"]
        command = f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} stop'
        self.run_shell_command(command)

    def stop_nodes(self, node):
        ''' stop nodes '''
        #prom depends on node PID should be stopped before node.
        self.stop_prom(node)

        dir_nano_nodes = _node_path["container"]
        nodes = self.get_nodes_name(node)
        command = f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} stop {nodes}'
        self.run_shell_command(command)

    def down(self):
        ''' down nodes '''
        dir_nano_nodes = _node_path["container"]
        command = f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} down'
        if path_exists(_node_path["compose"]):
            self.run_shell_command(command)

    def restart_nodes(self, node_name):
        ''' restart nodes '''
        self.stop_nodes(node_name)
        self.start_nodes(node_name)

    def restart_wait_sync(self):
        ''' restart nodes and wait until 100% of blocks are confirmed'''
        ba = BlockAsserts()
        all_cemented = False
        while not all_cemented:
            try:
                block_count = ba.assert_all_blocks_cemented()
                all_cemented = True
            except AssertionError:
                logging.info("Not all blocks cemented... restarting nodes.")
                self.restart_nodes('all')
                time.sleep(10)
        logging.getLogger().success(
            f'All {block_count["cemented"]} blocks are cemented')

    def network_status(self, ):
        ''' get confirmed count for each node'''
        conf = ConfigParser()
        response = self.is_all_containers_online(conf.get_nodes_name())
        ba = BlockAsserts()
        logging.getLogger().info(
            ba.network_status(nodes_name=response["online_containers"]))
        logging.getLogger().info(response["msg"])

    def reset_nodes(self, node):

        self.stop_nodes(node)
        commands = []
        dir_nano_nodes = _node_path["container"]
        nodes = _conf.get_nodes_name() if node == 'all' else [node]
        for node in nodes:
            path = f'{dir_nano_nodes}/{node}'
            commands.append(f'cd {path} && rm -f $(find . -name "*.ldb")')

        for command in commands:
            print("DEBUG", command)
            self.run_shell_command(command)
        #self.start_nodes(node)

    def destroy_all(self):
        dir_nano_nodes = _node_path["container"]
        commands = [
            f'cd {dir_nano_nodes} && docker-compose -p {_conf.get_project_name()} down',  #stop all nodes
            f'rm -rf {_default_path}/nano_nodes',  #remove all nodes and their configs
            f'rm -rf  {_default_path}/__pycache__',
            'rm -rf ./venv_nanolocal'
        ]  #remove python virtual environemtn

        for command in commands:
            self.run_shell_command(command)

    def conf_edit(self, nested_path, nested_value):
        if nested_path is None:
            logging.getLogger().warning(
                "conf_edit nested_path can't be None. Abort")
            return False
        _conf.modify_nanolocal_config(nested_path, nested_value)
        return True

    def traffic_control(self, action, command, node):
        if not _conf.get_config_value("tc_enable"):
            logging.getLogger().warning("tc_enable is FALSE. Abort")
            return False

        nodes = _conf.get_nodes_name() if node == 'all' else [node]
        commands = []
        if action == "add":
            self.traffic_control("del", "", node)
            for node in nodes:
                commands.append(
                    f"docker exec -u 0 {node} tc qdisc add dev eth0 root handle 1: prio priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0"
                )
                commands.append(
                    f"docker exec -u 0 {node} tc qdisc add dev eth0 parent 1:2 handle 20: netem {command}"
                )
                commands.append(
                    f"docker exec -u 0 {node} tc filter add dev eth0 parent 1:0 protocol ip u32 match ip dport 17075 0xffff flowid 1:2"
                )
                # commands.append(
                #     f"docker exec {node} tc filter add dev eth0 parent 1:0 protocol ip prio 1 handle 0x10 basic match \"cmp(u16 at 0 layer transport eq 17076)\" flowid 1:2"
                # )

            ### Possible values ###
            # intf="dev eth0"
            # delay="delay 400ms 100ms 50%"
            # loss="loss random 0%"
            # corrupt="corrupt 0%"
            # duplicate="duplicate 0%"
            # reorder="reorder 0%"
            # rate="rate 512kbit"
            # tc qdisc add $intf root netem $delay $loss $corrupt $duplicate $reorder $rate

        elif action == "del":
            for node in nodes:
                commands.append(
                    f"docker exec -u 0 {node} tc qdisc del dev eth0 root")

        for command in commands:
            self.run_shell_command(
                command,
                ignore_error="Error: Cannot delete qdisc with handle of zero.")
        return True

    def run_pytest(self, output, args):
        modules = _conf.get_testcases()["test_modules"]
        for module in modules:
            module_path = f'{dirname(__file__)}/testcases/{module}.py'
            if output == "html":
                output = f"--html=./nanolocal/testcases/reports/report_latest_{module}.html --self-contained-html"
            elif output == "xml":
                output = f"--junitxml=./nanolocal/testcases/reports/report_latest_{module}.xml"
            else:
                output = ""
            print(f"venv_nanolocal/bin/pytest {args} {module_path} {output}")
            run([f"venv_nanolocal/bin/pytest {args} {module_path} {output}"],
                shell=True)

    def run_test(self):
        modules = _conf.get_testcases()["test_modules"]
        for module in modules:
            run([
                f"venv_nanolocal/bin/python -m unittest -v nanolocal.testcases.{module}"
            ],
                shell=True)

    def set_log_level(self, loglevel):
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] [%(levelname)s] - %(message)s',
            stream=sys.stdout)

        level = logging.getLevelName(loglevel.upper())
        if not isinstance(level, int):
            raise ValueError(f'Invalid log level: {loglevel}')

        logger = logging.getLogger()
        logger.setLevel(level)

        # set success level
        logging.SUCCESS = 25  # between WARNING and INFO
        logging.addLevelName(logging.SUCCESS, 'SUCCESS')
        setattr(
            logger, 'success',
            lambda message, *args: logger._log(logging.SUCCESS, message, args))

    def run_command(self,
                    command,
                    command_value="",
                    conf_edit_path=None,
                    conf_edit_value=None,
                    node="all",
                    compose_version=2,
                    build=False,
                    pytest_output="html",
                    pytest_args="-v -rpf"):

        if command == 'status':
            self.network_status()
        elif command == 'csi':  #c(reate) s(tart) i(nit)
            if self.create_nodes(compose_version):
                self.start_all(True)
                self.init_nodes()
                self.restart_nodes('all')
        elif command == 'create':
            if self.create_nodes(compose_version):
                logging.getLogger().success(
                    "./nano_nodes directory was created")

        elif command == 'build_nodes':
            self.stop_nodes(node)
            self.build_nodes(node)
            self.start_nodes(node)
            logging.getLogger().success("nodes built & started")

        elif command == 'start':
            self.start_all(build)
            logging.getLogger().success("all containers started")

        elif command == 'start_prom':
            if self.start_prom('all'):
                logging.getLogger().success("prom-exporter containers started")

        elif command == 'start_prom_stack':
            if self.start_prom_stack():
                logging.getLogger().success("prom-stack containers started")

        elif command == 'init':
            self.init_nodes()
            logging.getLogger().success("ledger initialized")

        elif command == 'tc':
            if self.traffic_control("add", command_value, node):
                logging.getLogger().success("traffic control set")

        elif command == 'tc_del':
            if self.traffic_control("del", "", node):
                logging.getLogger().success("traffic control removed")

        elif command == 'init_wallets':
            self.init_wallets()
            logging.getLogger().success("wallets initialized")

        elif command == 'stop':
            self.stop_all()
            logging.getLogger().success("all containers stopped")

        elif command == 'down':
            self.down()
            logging.getLogger().success("all containers removed")

        elif command == 'stop_nodes':
            self.stop_nodes(node)
            logging.getLogger().success("nodes stopped")

        elif command == 'restart':
            self.restart_nodes(node)
            logging.getLogger().success("nodes restarted")

        elif command == 'restart_wait_sync':
            self.restart_wait_sync()

        elif command == 'reset':
            self.reset_nodes(node)
            logging.getLogger().success("data.ldb deleted")

        elif command == 'destroy':
            self.destroy_all()
            logging.getLogger().success("all destroyed")

        elif command == 'conf_edit':
            if self.conf_edit(conf_edit_path, conf_edit_value):
                logging.getLogger().success("Config modified")

        elif command == 'pytest':
            self.run_pytest(pytest_output, pytest_args)

        elif command == 'test':
            self.run_test()
        else:
            print(f'Unknown command {command}')