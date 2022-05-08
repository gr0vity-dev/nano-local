import logging
import os
import tomli
import tomli_w
#import yaml
import oyaml as yaml
# from ruamel.yaml import YAML
import secrets
import json
import copy

_script_dir = os.path.dirname(__file__) #<-- absolute dir the script is in
_config_path = os.path.join(_script_dir, "./nano_local_config.toml") 
_default_compose_path = os.path.join(_script_dir, "./default_docker-compose.yml")  
_config_dict = {} #conf_rw.read_toml(_config_path)
_compose_dict = {} #conf_rw.read_yaml(_default_compose_path)
_dockerfile_path = _script_dir.replace("config", "nano_nodes/{node_name}")
_nano_nodes_path = _script_dir.replace("config", "nano_nodes")


#compose output file : nano-local/nano_nodes/docker-compose.yml

class Config_rw:    

    def write_toml(self, path, content):
        with open(path, "wb") as f:    
            tomli_w.dump(content, f)

    def read_toml(self, path):
        try:
            with open(path, "rb") as f:
                toml_dict = tomli.load(f)
                return toml_dict
        except tomli.TOMLDecodeError as e:
            logging.error("Invalid config file! \n {}".format(str(e)))

    def read_yaml(self, path):
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def write_yaml(self, path, content):
        print(content)
        with open(path, 'w') as f:
            yaml.dump(json.loads(str(content).replace("'", '"')), f, default_flow_style = False)

class Helpers:

    def value_in_dict_array(self, dict_array, value_l) :
        for dict in dict_array :
            dict_found = self.value_in_dict(dict, value_l)
            if dict_found["found"] : return dict_found
        return {"found" : False, "value" : None}


    def value_in_dict(self, dict, value_l):
        for key,value in dict.items():
            if value==value_l:
                return {"found" : True, "value" : dict}
        return {"found" : False, "value" : None}   

h = Helpers()
conf_rw = Config_rw()
_config_dict = conf_rw.read_toml(_config_path)
_compose_dict = conf_rw.read_yaml(_default_compose_path)


def write_docker_compose(genesis_node_name = "nl_genesis"):
    set_docker_tag(genesis_node_name)
    set_docker_ports(genesis_node_name, 0)
    
    
    get_set_node_names()
    host_port_inc = 1
    for node in _config_dict["representatives"]["nodes"]:  
        set_docker_tag(node["name"])
        set_docker_ports(node["name"], host_port_inc)
        host_port_inc = host_port_inc + 1        

    
    #remove default containers
    _compose_dict["services"].pop("default_docker", None)
    _compose_dict["services"].pop("default_build", None)    

    conf_rw.write_yaml( f"{_nano_nodes_path}/docker-compose.yml", _compose_dict)
    os.system(f"cp -p dc_default_env {_nano_nodes_path}/dc_nano_local_env")

def get_set_node_names():
    response = []
    for node in _config_dict["representatives"]["nodes"]:
        if "name" not in node:
            container_name = f"nl_{secrets.token_hex(6)}"
            node["name"] = container_name
            logging.warn (f"no name set for a node. New name : {container_name}")
            #TODO write new config file with updates name to disk?
        node["name"] = node["name"].lower()
        response.append(node["name"])
    return response

def set_docker_tag(node_name):
    #Search for individual docker_tag, then individual executable, then shared docker-tag then shared-executable
    
    if get_representative_config("docker_tag", node_name)["found"]: #search by individual docker_tag   
        #default_docker
        container = add_docker_compose_container(node_name, "default_docker")
        docker_tag = get_representative_config("docker_tag", node_name)["value"]
        container["image"] = f"nanocurrency/nano-test:{docker_tag}" 

    elif get_representative_config("nano_node_path", node_name)["found"]: #search by individual nano_node_path
        #default_build
        container = add_docker_compose_container(node_name, "default_build")
        dockerfile_path = cp_dockerfile_and_nano_node(get_representative_config("nano_node_path", node_name)["value"], node_name)
        container["build"] = f"{dockerfile_path}/."       

    elif get_representative_config("docker_tag", None)["found"]: #search by shared docker_tag
        #default_docker
        container = add_docker_compose_container(node_name, "default_docker")
        docker_tag = get_representative_config("docker_tag", None)["value"]
        container["image"] = f"nanocurrency/nano-test:{docker_tag}" 
       
    elif get_representative_config("nano_node_path", None)["found"]: #search by shared nano_node_path
        #default_build
        container = add_docker_compose_container(node_name, "default_build")
        dockerfile_path = cp_dockerfile_and_nano_node(get_representative_config("nano_node_path", None)["value"], node_name)
        container["build"] = f"{dockerfile_path}/."  
    else:
        container = add_docker_compose_container(node_name, "default_docker")
        container["image"] = f"nanocurrency/nano-test:latest" 
        logging.warn("No docker_tag or nano_node_path specified. use [latest] (nanocurrency/nano-test:latest)")
   
def set_docker_ports(node_name, port_i):
    host_port_rpc = 45000 + port_i
    host_port_ws = 47000 + port_i
    _compose_dict["services"][node_name]["ports"] = [f'{host_port_rpc}:17076', f'{host_port_ws}:17078']  
   
def cp_dockerfile_and_nano_node(nano_node_path, node_name):
    #copy nano_node into working directory for Dockerfile  
    dockerfile_path = _dockerfile_path.format(node_name=node_name)  
    copy_node =        f"cp -p {nano_node_path} {dockerfile_path}/nano_node"
    copy_dockerfile =  f"cp -p {_script_dir}/Dockerfile {dockerfile_path}/Dockerfile"    
    print(copy_node)

    os.system(copy_node)
    os.system(copy_dockerfile)
    return dockerfile_path
 
def add_docker_compose_container(node_name, default_container) :
    #copies a default container and adds it as a new container
    _compose_dict["services"][node_name] = copy.deepcopy(_compose_dict["services"][default_container])
    _compose_dict["services"][node_name]["container_name"] = node_name
    _compose_dict["services"][node_name]["volumes"][0] =  _compose_dict["services"][node_name]["volumes"][0].replace(default_container, node_name)
    return _compose_dict["services"][node_name]

def get_config_from_path(node_name, config_path_key):
    #returns None if no path is found
    config_dict_l = None
    if get_representative_config(config_path_key, node_name)["found"]: #search by individual path
        config_dict_l = conf_rw.read_toml(get_representative_config(config_path_key, node_name)["value"])  
    elif get_representative_config(config_path_key, None)["found"]: #search by shared path
        config_dict_l = conf_rw.read_toml(get_representative_config(config_path_key, None)["value"])  
    else : 
        pass #return None  
    return config_dict_l

def get_preconfigured_peers():
    perconfigures_peers = []
    for node in _config_dict["representatives"]["nodes"]:
        perconfigures_peers.append(node["name"])    
    return perconfigures_peers   

def get_representative_config(node_key, node_name):
    #scan node config and match by name. Return the value of the key found in the config
    #response : {"found" : Bool, "value" = ...}
    if node_name is None and node_key is None:
        return {"found" : False } 

    if node_name is None :
        #shared config
        if node_key in _config_dict["representatives"] :
            return {"found" : True, "value" : _config_dict["representatives"][node_key] }
    else :
        #individual config
        representatives_config = h.value_in_dict_array(_config_dict["representatives"]["nodes"], node_name) 
        if representatives_config["found"] == True:   
            if node_key in representatives_config["value"]:
                return {"found" : True, "value" : representatives_config["value"][node_key]}
    return {"found" : False }

def get_env_variables() :
    #default
    env_variables = {"genesis_pkey": "12C91837C846F875F56F67CD83040A832CFC0F131AF3DFF9E502C0D43F5D2D15",                                           
                     "canary_pkey": "FB4E458CB13508353C5B2574B82F1D1D61367F61E88707F773F068FF90050BEE",
                     "epoch_count": 2,
                     "burn_amount": "200000000000000000000000000000000000000",
                     "NANO_TEST_GENESIS_PUB" : "37FCEA4DA94F1635484EFCBA57483C4C654F573B435C09D8AACE1CB45E63FFB1",
                     "NANO_TEST_EPOCH_1": "0xfff00000000000000",
                     "NANO_TEST_EPOCH_2": "0xfff0000000000000",
                     "NANO_TEST_EPOCH_2_RECV": "0xfff0000000000000",
                     "NANO_TEST_MAGIC_NUMBER": "LC"}

    #from config
    if "genesis_pkey" in _config_dict : env_variables["genesis_pkey"] = _config_dict["genesis_pkey"]
    if "canary_pkey" in _config_dict : env_variables["canary_pkey"] = _config_dict["canary_pkey"]
    if "epoch_count" in _config_dict : env_variables["epoch_count"] = _config_dict["epoch_count"]
    if "burn_amount" in _config_dict : env_variables["burn_amount"] = _config_dict["burn_amount"]
    if "NANO_TEST_EPOCH_1" in _config_dict : env_variables["NANO_TEST_EPOCH_1"] = _config_dict["NANO_TEST_EPOCH_1"]
    if "NANO_TEST_EPOCH_2" in _config_dict : env_variables["NANO_TEST_EPOCH_2"] = _config_dict["NANO_TEST_EPOCH_2"]
    if "NANO_TEST_EPOCH_2_RECV" in _config_dict : env_variables["NANO_TEST_EPOCH_2_RECV"] = _config_dict["NANO_TEST_EPOCH_2_RECV"]
    if "NANO_TEST_MAGIC_NUMBER" in _config_dict : env_variables["NANO_TEST_MAGIC_NUMBER"] = _config_dict["NANO_TEST_MAGIC_NUMBER"]
    if "NANO_TEST_PEER_NETWORK" in _config_dict : env_variables["NANO_TEST_PEER_NETWORK"] = _config_dict["NANO_TEST_PEER_NETWORK"]
    if "NANO_TEST_GENESIS_PUB" in _config_dict : env_variables["NANO_TEST_GENESIS_PUB"] = _config_dict["NANO_TEST_GENESIS_PUB"]
    if "NANO_TEST_CANARY_PUB" in _config_dict : env_variables["NANO_TEST_CANARY_PUB"] = _config_dict["NANO_TEST_CANARY_PUB"]
    
    env_variables["genesis_block"] = """'NANO_TEST_GENESIS_BLOCK={
        "type": "open",
        "source": "37FCEA4DA94F1635484EFCBA57483C4C654F573B435C09D8AACE1CB45E63FFB1",
        "representative": "xrb_1fzwxb8tkmrp8o66xz7tcx65rm57bxdmpitw39ecomiwpjh89zxj33juzt6p",
        "account": "xrb_1fzwxb8tkmrp8o66xz7tcx65rm57bxdmpitw39ecomiwpjh89zxj33juzt6p",
        "work": "4206a0ce90472a90",
        "signature": "492FBB6A8852FD6086739D151454A5A6A2920D9A6085FDA1F00690D46D9AEC7668A75ECCAA4F52220859E1F45558500A32735060E8B1D0611079B62751457A05"
    }'"""

    return env_variables  

