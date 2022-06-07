#!./venv_nano_local/bin/python

import json
import logging
import os
from src.parse_nano_local_config import ConfigParser
from src.parse_nano_local_config import ConfigReadWrite
from src.nano_local_initial_blocks import InitialBlocks
from src.nano_rpc import Api
import argparse
import copy
import subprocess

# * create (this will create the one time resources that need creating)
# * start (this will start the nodes)
# * init (create an initial ledger structure common to all, epoch1 and 2 and canary blocks, etc)
# * RunTest
# * stop (stop the nodes but do not destroy anything)
# * reset (remove all blocks except genesis blocks by deleting data.ldb)
# * destroy (destroy all autogenerated resources, so that we can start from virgin state next time)




_config_rw = None
_config_parse = None
_node_path = {"container" : "./nano_nodes"}


def get_default(config_name):
    #minimal node config if no file is provided in the nano_local_config.toml
    if config_name == "config_node" :
        return {"rpc" : {"enable" : True} ,
                       "node" : {"allow_local_peers" : True, "enable_voting" : True}}
    if config_name == "config_rpc" :
        return {"enable_control" : True, "enable_sign_hash" : True}

def create_node_folders(node_name):
    global _node_path

    commands = [ "mkdir -p nano_nodes",
                f"cd nano_nodes && mkdir -p {node_name}",
                f"cd nano_nodes/{node_name} && mkdir -p NanoTest" ]

    if _config_parse.get_config_value("nanomonitor_enable") :
        commands.append(f"cd nano_nodes/{node_name} && mkdir -p nanoNodeMonitor")

    for command in commands:
        os.system(command)

    _node_path[node_name] = {"data_path" :       f"./nano_nodes/{node_name}/NanoTest",
                            "config_node_path" : f"./nano_nodes/{node_name}/NanoTest/config-node.toml",
                            "config_rpc_path"  : f"./nano_nodes/{node_name}/NanoTest/config-rpc.toml"}



### Using the docker approch to create a wallet will result in blocks not being cemented...
# def create_node_wallet(node_name, private_key = None , seed = None):
#     #command = nano-workspace/build/nano_node --network test ##for custom biulds using dsiganos/nano-workspace
#     #comand = /usr/bin/nano_node ##when using existing docker-tags from nanocurrency/nano-test

#     wallet_create =    f"docker exec -it {node_name} /usr/bin/nano_node --wallet_create"
#     wallet_list =      f"docker exec -it {node_name} /usr/bin/nano_node --wallet_list | awk 'FNR == 1 {{print $3}}' | tr -d '\r' | tr -d '\n'"
#     os.system(wallet_create)
#     wallet =           os.popen(wallet_list).read()
#     account_create =   f"docker exec -it {node_name} /usr/bin/nano_node --account_create --wallet={wallet}"
#     change_seed =      f"docker exec -it {node_name} /usr/bin/nano_node --wallet_change_seed --wallet={wallet} --key={seed}"
#     wallet_add_adhoc = f"docker exec -it {node_name} /usr/bin/nano_node --wallet_add_adhoc --wallet={wallet} --key={private_key}"
#     account_get =      f"docker exec -it {node_name} /usr/bin/nano_node --wallet_list | awk 'FNR == 2 {{print $1}}' | tr -d '\r'"


#     if seed != None : os.system(change_seed)
#     elif private_key != None : os.system(wallet_add_adhoc)
#     else : os.system(account_create) #use the random default seed from wallet_create

#     account = os.popen(account_get).read()
#     logging.info(f"WALLET {wallet} CREATED FOR {node_name} WITH ACCOUNT {account}")

#     return {"wallet" : wallet, "account" : account}


def write_config_node(node_name):
    config_node = _config_parse.get_config_from_path(node_name, "config_node_path")
    if config_node is None :
        logging.warning("No config-node.toml found. minimal version was created")
        config_node = get_default("config_node")

    config_node["node"]["preconfigured_peers"] = _config_parse.preconfigured_peers
    _config_rw.write_toml(_node_path[node_name]["config_node_path"], config_node)

def write_config_rpc(node_name):
    config_rpc = _config_parse.get_config_from_path(node_name, "config_rpc_path")
    if config_rpc is None :
        logging.warning("No config-rpc.toml found. minimal version was created")
        config_rpc = get_default("config_rpc")

    _config_rw.write_toml(_node_path[node_name]["config_rpc_path"], config_rpc)

def write_nanomonitor_config(node_name):
    if _config_parse.get_config_value("nanomonitor_enable"):
         _config_parse.write_nanomonitor_config(node_name)

def write_docker_compose_env(compose_version):
    #Read default env file
    conf_variables = _config_parse.config_dict
    env_variables = []
    genesis_block = generate_genesis_open(conf_variables['genesis_key'])
    s_genesis_block = str(genesis_block).replace("'", '"')

    if compose_version == 1 :
        env_variables.append( f"'NANO_TEST_GENESIS_BLOCK={s_genesis_block}'")
    elif compose_version == 2 :
        env_variables.append( f"NANO_TEST_GENESIS_BLOCK={s_genesis_block}")
    env_variables.append( f'NANO_TEST_GENESIS_PUB="{genesis_block["source"]}"')
    env_variables.append( f'NANO_TEST_CANARY_PUB="{_config_parse.key_expand(conf_variables["canary_key"])["public"]}"')

    for key,value in conf_variables.items() :
        if key.startswith("NANO_TEST_") : env_variables.append(f'{key}="{value}"')

    _config_rw.write_list(f'{_node_path["container"]}/dc_nano_local_env', env_variables)


def generate_genesis_open(genesis_key):
    #TODO find a less intrusive way to create a legacy open block.
    try :
        docker_run =       "docker run -d --name ln_get_genesis nanocurrency/nano-test:latest"
        docker_exec =     f"docker exec -it ln_get_genesis /usr/bin/nano_node --network=dev --debug_bootstrap_generate --key={genesis_key}""" #dev net to speed up things
        docker_stop_rm = """docker stop ln_get_genesis &&
                            docker rm ln_get_genesis"""

        logging.info("run temporary docker conatiner for genesis generation")
        os.system(docker_run)
        blocks = ''.join(os.popen(docker_exec).readlines()[102:110])
        logging.info("stop and remove docker container")
        os.system(docker_stop_rm)
        return json.loads(str(blocks))

    except Exception as e:
         logging.error(str(e))
         os.system(docker_stop_rm)

def is_rpc_available(node_names):
    while len(node_names) > 0 :
        containers = copy.deepcopy(node_names)
        for container in containers:
            cmd_rpc_url = f"docker port {container} | grep 17076/tcp | awk '{{print $3}}'"
            rpc_url = "http://" + str(os.popen(cmd_rpc_url).readlines()[0:1][0]).strip()
            if Api(rpc_url).is_online(timeout=3) :               
                node_names.remove(container)
            else :
                logging.warning(f"RPC {rpc_url} not yet reachable for node {container} ")   
    logging.info(f"Nodes {ConfigParser().get_nodes_name()} started successfully")



def prepare_nodes(genesis_node_name):
    #prepare genesis
    prepare_node_env(genesis_node_name)
    for node_name in ConfigParser().get_nodes_name():
        prepare_node_env(node_name)


def prepare_node_env(node_name):
    node_name = node_name.lower()  #docker-compose requires lower case names
    create_node_folders(node_name)
    write_config_node(node_name)
    write_config_rpc(node_name)
    write_nanomonitor_config(node_name)



def init_nodes(genesis_node_name = "nl_genesis"):
    global _config_parse
    _config_parse = ConfigParser()

    start_nodes() #fixes a bug on mac m1
    init_blocks = InitialBlocks()
    for node_name in _config_parse.get_nodes_name():
        if node_name == genesis_node_name :
            init_blocks.create_node_wallet(_config_parse.get_node_config(genesis_node_name)["rpc_url"],
                                   genesis_node_name,
                                   private_key = _config_parse.config_dict["genesis_key"])
        else :
            init_blocks.create_node_wallet(_config_parse.get_node_config(node_name)["rpc_url"],
                                        node_name,
                                        seed = _config_parse.get_node_config(node_name)["seed"])

    init_blocks.publish_initial_blocks()

def create_nodes(compose_version, genesis_node_name = "nl_genesis"):
    global _config_rw, _config_parse
    _config_rw = ConfigReadWrite()
    _config_parse = ConfigParser()

    prepare_nodes(genesis_node_name = genesis_node_name)
    write_docker_compose_env(compose_version)
    _config_parse.write_docker_compose()

def start_all(build_f):
    global _config_parse
    if _config_parse is None : _config_parse = ConfigParser()

    dir_nano_nodes = _node_path["container"]
    command =  f'cd {dir_nano_nodes} && docker-compose up -d'
    if build_f :
        command =  f'cd {dir_nano_nodes} && docker-compose up -d --build'
    os.system(command)
    is_rpc_available(_config_parse.get_nodes_name())

def start_nodes():
    global _config_parse
    if _config_parse is None : _config_parse = ConfigParser()

    dir_nano_nodes = _node_path["container"]
    nodes = ' '.join(_config_parse.get_nodes_name())
    command =  f'cd {dir_nano_nodes} && docker-compose start {nodes}'
    os.system(command)
    is_rpc_available(_config_parse.get_nodes_name())
    

def stop_all():
    dir_nano_nodes = _node_path["container"]
    command =  f'cd {dir_nano_nodes} && docker-compose stop'
    os.system(command)

def stop_nodes():
    global _config_parse
    if _config_parse is None : _config_parse = ConfigParser()

    dir_nano_nodes = _node_path["container"]
    nodes = ' '.join(_config_parse.get_nodes_name())
    command =  f'cd {dir_nano_nodes} && docker-compose stop {nodes}'
    os.system(command)

def restart_nodes():
    stop_nodes()
    start_nodes()

def reset_nodes():
    stop_nodes()
    dir_nano_nodes = _node_path["container"]
    command = f'cd {dir_nano_nodes} && find . -name "data.ldb"  -type f -delete'
    os.system(command)
    start_nodes()

def destroy_all():
    dir_nano_nodes = _node_path["container"]
    commands =  [ f'cd {dir_nano_nodes} && docker-compose down', #stop all nodes
                  'rm -rf ./nano_nodes' , #remove all nodes and their configs
                  'rm -rf ./__pycache__',
                  'rm -rf ./venv_nano_local'] #remove python virtual environemtn

    for command in commands:
        os.system(command)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--build', type=bool, default = False,
                        help='build docker container for new executable')
    parser.add_argument('--output', choices={"console", "html", "xml"}, default = "html",
                        help='create a report under ./testcases/reports in the specified format for each module')
    parser.add_argument('--loglevel', choices={"DEBUG", "INFO", "WARNING", "ERROR"}, default = "INFO",
                        help='set log level. defaults to INFO')
    parser.add_argument('--args', default = "-v -rpf",
                        help='will be added after pytest. example -rfE')
    parser.add_argument('--compose_version', type=int, default = 2, choices={1,2},
                        help='run $ docker-compose --version to identify the version. Defaults to 2')
    parser.add_argument('command',
            help='create , start, init, csi, stop, reset, destroy', default = 'create')
    return parser.parse_args()


# #DEBUG : put def parse_args() into comment and set the command you wish to run
# def parse_args() :
#     return argClass
# class argClass :
#     command = "init"
#     compose_version = 2

def set_log_level(loglevel) :
    log_format = '[%(asctime)s] [%(levelname)s] - %(message)s'
    if loglevel == "DEBUG" :
        logging.basicConfig(level=logging.DEBUG , format=log_format)
    elif loglevel == "INFO" :
        logging.basicConfig(level=logging.INFO , format=log_format)
    elif loglevel == "WARNING" :
        logging.basicConfig(level=logging.WARNING , format=log_format)
    elif loglevel == "ERROR" :
        logging.basicConfig(level=logging.ERROR , format=log_format)

def main():   

    args = parse_args()
    set_log_level(args.loglevel)  
      
    if args.command == 'csi' : #c(reate) s(tart) i(nit)
        create_nodes(args.compose_version)
        start_all(True)
        init_nodes()
        restart_nodes()

    if args.command == 'create':
        create_nodes(args.compose_version)
        logging.info("./nano_nodes folder was created")

    elif args.command == 'start':
        start_all(args.build)

    elif args.command == 'init':
        init_nodes()
        restart_nodes()

    elif args.command == 'stop':
        stop_all()

    elif args.command == 'restart':
        restart_nodes()

    elif args.command == 'reset':
        reset_nodes()

    elif args.command == 'destroy':
        destroy_all()

    elif args.command == 'pytest' :
        modules = ConfigParser().get_testcases()["test_modules"]
        for module in modules :
            module_path = f'{os.path.dirname(__file__)}/testcases/{module}.py'
            output = ""
            if(args.output)  == "html" : output = f"--html=./testcases/reports/report_latest_{module}.html --self-contained-html"
            elif(args.output)  == "xml" : output = f"--junitxml=./testcases/reports/report_latest_{module}.xml"
            print(f"venv_nano_local/bin/pytest {args.args} {module_path} {output}")
            subprocess.run([f"venv_nano_local/bin/pytest {args.args} {module_path} {output}"], shell=True)

    elif args.command == 'test' :
        modules = ConfigParser().get_testcases()["test_modules"]
        for module in modules :
            subprocess.run([f"venv_nano_local/bin/python -m unittest -v testcases.{module}"], shell=True)


    else:
        print('Unknown command %s', args.command)


if __name__=="__main__":
    main()

