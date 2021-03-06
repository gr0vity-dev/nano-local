import logging
import os
import subprocess
import tomli
import tomli_w
import oyaml as yaml
import secrets
import json
import copy
import hashlib
from ed25519_blake2b import SigningKey
from binascii import hexlify, unhexlify
from base64 import b32encode, b32decode
import string
from pyblake2 import blake2b
from math import ceil


_app_dir = os.path.dirname(__file__).replace("/src", "") #<-- absolute dir the script is in
_config_dir = os.path.join(_app_dir, "./config")
_config_path = os.path.join(_app_dir, "./nano_local_config.toml")
_default_compose_path = os.path.join(_app_dir, "./config/default_docker-compose.yml")
_dockerfile_path = os.path.join(_app_dir, "./nano_nodes/{node_name}")
_default_nanomonitor_config = os.path.join(_config_dir, "nanomonitor/default_config.php")
_nano_nodes_path = os.path.join(_app_dir,  "./nano_nodes")


#compose output file : nano-local/nano_nodes/docker-compose.yml

class ConfigReadWrite:
    
    def __init__(self):
        if not os.path.exists("nano_local_config.toml") :
            logging.warning("No config file exists. creating 'nano_local_config.toml'")         
            subprocess.call("cp -p nano_local_config.example.toml nano_local_config.toml", shell=True)

    def write_json(self,path,json_dict):
         with open(path, "w") as f:
            json.dump(json_dict, f)

    def read_json(self,path):
         with open(path, "r") as f:
            return json.load(f)

    def read_file(self,path):
        with open(path, "r") as f:
            return f.readlines()

    def write_list(self,path,list):
        with open(path, "w") as f:
            print(*list, sep = "\n", file = f)

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


    maketrans = bytes.maketrans if hasattr(bytes, 'maketrans') else string.maketrans
    B32_ALPHABET = b'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    XRB_ALPHABET = b'13456789abcdefghijkmnopqrstuwxyz'
    XRB_ENCODE_TRANS = maketrans(B32_ALPHABET, XRB_ALPHABET)
    XRB_DECODE_TRANS = maketrans(XRB_ALPHABET, B32_ALPHABET)

    def bytes_to_xrb(self,value):
        return b32encode(value).translate(self.XRB_ENCODE_TRANS)

    def hex_to_xrb(self,value):
        return self.bytes_to_xrb(unhexlify(value))


    def xrb_to_bytes(self,value):
        return b32decode(value.translate(self.XRB_DECODE_TRANS))

    def xrb_to_hex(self,value):
        return hexlify(self.xrb_to_bytes(value))

    def address_checksum(self,address):
        address_bytes = address
        h = blake2b(digest_size=5)
        h.update(address_bytes)
        checksum = bytearray(h.digest())
        checksum.reverse()
        return checksum

    def public_key_to_nano_address(self,public_key):
        if not len(public_key) == 32:
            raise ValueError('public key must be 32 chars')

        padded = b'000' + public_key
        address = self.bytes_to_xrb(padded)[4:]
        checksum = self.bytes_to_xrb(self.address_checksum(public_key))
        return 'nano_' + address.decode('ascii') + checksum.decode('ascii')

    def percentile(self,data, percentile):
        n = len(data)
        p = n * percentile / 100
        if p.is_integer():
            return sorted(data)[int(p)]
        else:
            return sorted(data)[int(ceil(p)) - 1]

class ConfigParser :
    from src.nano_rpc import NanoTools
    preconfigured_peers = []
    nt = NanoTools()
    enabled_services = []

    def __init__(self, genesis_node_name = "nl_genesis"):
        self.h = Helpers()
        self.conf_rw = ConfigReadWrite()
        self.config_dict = self.conf_rw.read_toml(_config_path)
        self.compose_dict = self.conf_rw.read_yaml(_default_compose_path)
        self.__config_dict_set_node_variables()  #modifies config_dict
        self.__config_dict_set_default_values() #modifies config_dict
        self.__config_dict_add_genesis_to_nodes(genesis_node_name)
        self.__set_preconfigured_peers()
        self.__set_node_accounts()
        self.__set_balance_from_vote_weight()
        self.__set_special_account_data()
        self.__set_docker_compose(genesis_node_name) #also sets rpc_url in config_dict.representative.nodes.node_name.rpc_url



    def __set_node_accounts(self):
        available_supply = 340282366920938463463374607431768211455 - int(self.config_dict.get("burn_amount", 0)) - 1
        for node in self.config_dict["representatives"]["nodes"]:

            if "key" in node :
                account_data = self.key_expand(node["key"])
            else:
                account_data = self.account_from_seed(node["seed"]) #index 0

            node["account"] = account_data["account"]
            node["account_data"] = account_data
            if "vote_weight_percent" in node:
                node["balance"] = self.nt.raw_mul(available_supply, node["vote_weight_percent"])


    def __set_special_account_data(self):
        self.config_dict["burn_account_data"] = {"account" : "nano_1111111111111111111111111111111111111111111111111111hifc8npp"}
        self.config_dict["genesis_account_data"] = self.key_expand(self.config_dict["genesis_key"])
        self.config_dict["canary_account_data"] = self.key_expand(self.config_dict["canary_key"])


    def __config_dict_set_node_variables(self):

        for node in self.config_dict["representatives"]["nodes"]:
            if "name" not in node:
                node["name"] = f"nl_{secrets.token_hex(6)}"
                logging.warning (f'no name set for a node. New name : {node["name"].lower()}')
                #TODO write new config file with updates name to disk?
            node["name"] = node["name"].lower()

            if "seed" not in node:
                node["seed"] = secrets.token_hex(32)
                logging.warning (f'no seed set for a node. New seed : {node["seed"]}')

    def __config_dict_set_default_values(self) :
        #self.config_dict = conf_rw.read_toml(_config_path)
        self.config_dict["NANO_TEST_EPOCH_1"] = "0x000000000000000f"

        #set some default values if these are missing in the nano_local_config.toml
        if "genesis_key" not in self.config_dict : self.config_dict["genesis_key"] = "12C91837C846F875F56F67CD83040A832CFC0F131AF3DFF9E502C0D43F5D2D15"
        if "canary_key" not in self.config_dict : self.config_dict["canary_key"] = "FB4E458CB13508353C5B2574B82F1D1D61367F61E88707F773F068FF90050BEE"
        if "epoch_count" not in self.config_dict : self.config_dict["epoch_count"] = 2

        if "NANO_TEST_EPOCH_2" not in self.config_dict : self.config_dict["NANO_TEST_EPOCH_2"] = "0xfff0000000000000"
        if "NANO_TEST_EPOCH_2_RECV" not in self.config_dict : self.config_dict["NANO_TEST_EPOCH_2_RECV"] = "0xfff0000000000000"
        if "NANO_TEST_MAGIC_NUMBER" not in self.config_dict : self.config_dict["NANO_TEST_MAGIC_NUMBER"] = "LC"
        if "NANO_TEST_CANARY_PUB" not in self.config_dict : self.config_dict["NANO_TEST_CANARY_PUB"] = "CCAB949948224D6B33ACE0E078F7B2D3F4D79DF945E46915C5300DAEF237934E"

        if "nanolooker_enable" not in self.config_dict : self.config_dict["nanolooker_enable"] = False
        if "nanomonitor_enable" not in self.config_dict : self.config_dict["nanomonitor_enable"] = False
        if "nanoticker_enable" not in self.config_dict : self.config_dict["nanoticker_enable"] = False
        if "nanovotevisu_enable" not in self.config_dict : self.config_dict["nanovotevisu_enable"] = False
        if "remote_address" not in self.config_dict : self.config_dict["remote_address"] = '127.0.0.1'
        return self.config_dict

    def __config_dict_add_genesis_to_nodes(self, genesis_node_name) :
        self.config_dict["representatives"]["nodes"].insert(0, { "name" : genesis_node_name,
                                                                 "key" : self.config_dict["genesis_key"] })

    def __set_preconfigured_peers(self ):
        for node in self.config_dict["representatives"]["nodes"]:
            if node["name"] not in self.preconfigured_peers :
                self.preconfigured_peers.append(node["name"])
        return self.preconfigured_peers


    def __set_balance_from_vote_weight(self):
        available_supply = 340282366920938463463374607431768211455 - int(self.config_dict.get("burn_amount", 0)) - 1
        for node_conf in self.get_nodes_config():
            if "vote_weight" in node_conf :
                node_conf["balance"] = self.nt.raw_mul(available_supply * node_conf["vote_weight"])

    def account_from_seed(self, seed):
        seed_u =  unhexlify(seed)
        index = 0x00000000.to_bytes(4, 'big') # 1
        blake2b_state = hashlib.blake2b(digest_size=32)
        concat = seed_u+index
        blake2b_state.update(concat)
        # where `+` means concatenation, not sum: https://docs.python.org/3/library/hashlib.html#hashlib.hash.update
        # code line above is equal to `blake2b_state.update(seed); blake2b_state.update(index)`
        private_key = blake2b_state.digest()
        expanded_key = self.key_expand(hexlify(private_key))
        expanded_key["seed"] = seed
        return expanded_key

    def get_rpc_endpoints(self):
        api = []
        for node_name in self.get_nodes_name() :
            node_conf = self.get_node_config(node_name)
            api.append(node_conf["rpc_url"])
        return api


    def key_expand(self,private_key):

        signing_key = SigningKey(unhexlify(private_key))
        private_key = signing_key.to_bytes().hex()
        public_key = signing_key.get_verifying_key().to_bytes().hex()

        return {"private" : private_key, "public" : public_key, "account" : self.h.public_key_to_nano_address(unhexlify(public_key))}

    def write_nanomonitor_config(self, node_name):
        nanomonitor_config = self.conf_rw.read_file(_default_nanomonitor_config)
        destination_path = str(os.path.join(_dockerfile_path, "nanoNodeMonitor/config.php")).format(node_name=node_name)
        node_config = self.get_node_config(node_name)
        nanomonitor_config[4] = f"$nanoNodeName = '{node_name}';"
        nanomonitor_config[5] = f"$nanoNodeRPCIP   = '{node_name}';"
        nanomonitor_config[7] = f"$nanoNodeAccount = '{node_config['account']}';"
        self.conf_rw.write_list(destination_path,nanomonitor_config)

    def get_all(self):
        return self.config_dict

    def get_node_config(self, node_name):
        result = self.h.value_in_dict_array(self.config_dict["representatives"]["nodes"], node_name)
        if result["found"] : return result["value"]

    def get_genesis_account_data(self):
        return self.config_dict["genesis_account_data"]

    def get_burn_account_data(self):
        return self.config_dict["burn_account_data"]

    def get_canary_account_data(self):
        return self.config_dict["canary_account_data"]

    def get_max_balance_key(self):
        #returns the privatekey for the node with the highest defined balance.
        nodes_conf = self.get_nodes_config()
        max_balance = max(int(x["balance"]) if "balance" in x else 0 for x in self.get_nodes_config())
        node_conf = list(filter(lambda x: int(x.get("balance", 0)) == max_balance, self.get_nodes_config()))
        return node_conf[0]["account_data"]["private"]

    def get_nodes_name(self) :
        response = []
        for node in self.config_dict["representatives"]["nodes"]:
            response.append(node["name"])
        return response

    def get_nodes_config(self) :
        res = []
        for node_name in self.get_nodes_name():
            #res[node_name] = self.get_node_config(node_name)
            res.append(self.get_node_config(node_name))
        return res

    def set_node_balance(self,node_name, balance) :
        self.get_node_config(node_name)["balance"] = balance

    def skip_testcase(self, testcase_fullname) :
        testcase_fullname = testcase_fullname.replace("testcases.", "")
        return not self.run_testcase(testcase_fullname)

    def any_true_test_method(self, test_class):
        run = self.get_testcases()
        for test_method, value in run["test_methods"].items() :
            if str(test_method).startswith(test_class) and value == True :
                return True

    def any_true_testclass(self, test_module):
        run = self.get_testcases()
        for test_class, value in run["test_classes"].items() :
            if str(test_class).startswith(test_module) and value == True :
                return True


    def run_testcase(self,testcase_fullname) :

        run = self.get_testcases()
        split_name = testcase_fullname.split(".")
        test_module = testcase_fullname.split(".")[0] if len(split_name) >0 else None
        test_class = f'{test_module}.{testcase_fullname.split(".")[1]}' if len(split_name) >1 else None
        test_case = f'{test_module}.{test_class}.{testcase_fullname.split(".")[2]}' if len(split_name) >2 else None

        if testcase_fullname in run["test_methods"] : return run["test_methods"][testcase_fullname]
        #only execute entire class if testcases defined for the current testclass
        if not self.any_true_test_method(test_class) and test_class in run["test_classes"] : return run["test_classes"][test_class]
        if not self.any_true_testclass(test_module) and test_module in run["test_modules"] : return run["test_modules"][test_module]
        return False



    def get_testcases(self):
        #"skip_all" will display the testcases as being "skipped"
        #"ignore" will remove the testcases and tehy will not be displayed at all when running test or pytest

        run = {"test_methods" : {},
               "test_classes" : {},
               "test_modules" : {} }
        for test_module in self.config_dict["testcases"]:  
            if "ignore_module" in self.config_dict["testcases"][test_module]:
                logging.info(f"Module 'testcases.{test_module}' is ignored")
                # dont add module even some tests are defined               
                continue

            if "skip_all" in self.config_dict["testcases"][test_module] :
                if self.config_dict["testcases"][test_module]["skip_all"] :
                    logging.info(f"all tests from 'testcases.{test_module}' are skipped")
                    run["test_modules"][test_module] = False
                    continue
            else:
                 run["test_modules"][test_module] = True

            for test_class in self.config_dict["testcases"][test_module] :  
                if "skip_all" in self.config_dict["testcases"][test_module][test_class] :
                     # list tests as skipped
                    if self.config_dict["testcases"][test_module][test_class]["skip_all"] :
                        logging.info(f"all tests from 'testcases.{test_module}.{test_class}' are skipped")
                        run["test_classes"][f"{test_module}.{test_class}"] = False
                        continue
                else :
                    run["test_classes"][f"{test_module}.{test_class}"] = True

                for test_method, value in self.config_dict["testcases"][test_module][test_class].items() :
                    if len(test_method) > 0 : run["test_methods"][f"{test_module}.{test_class}.{test_method}"] = value if value != {} else True

        return run


    def __set_docker_compose(self, genesis_node_name):
        host_port_inc = 0
        for node in self.config_dict["representatives"]["nodes"]:
            self.compose_add_node(node["name"])
            self.compose_set_node_ports(node["name"], host_port_inc)
            host_port_inc = host_port_inc + 1

        if self.get_config_value("nanolooker_enable") :
            self.set_nanolooker_compose()

        if self.get_config_value("nanomonitor_enable") :
            self.set_nanomonitor_compose()

        if self.get_config_value("nanoticker_enable") :
            self.set_nanoticker_compose()

        if self.get_config_value("nanovotevisu_enable") :
            self.set_nanovotevisu_compose(genesis_node_name)


        #remove default container
        self.compose_dict["services"].pop("default_docker", None)
        self.compose_dict["services"].pop("default_build", None)

    def set_nanovotevisu_compose(self,genesis_node_name):
        nanoticker_compose = self.conf_rw.read_yaml ( f'{_config_dir}/nanovotevisu/default_docker-compose.yml')
        self.compose_dict["services"]["nl_nanovotevisu"] = nanoticker_compose["services"]["nl_nanovotevisu"]
        self.compose_dict["services"]["nl_nanovotevisu"]["build"]["args"][0] = f'REMOTE_ADDRESS={self.get_config_value("remote_address")}'
        self.compose_dict["services"]["nl_nanovotevisu"]["build"]["args"][1] = f'HOST_ACCOUNT={self.get_node_config(genesis_node_name)["account"]}'
        self.enabled_services.append(f'nano-vote-visualizer enabled at {self.get_config_value("remote_address")}:42001')
        

    def set_nanoticker_compose(self):
        nanoticker_compose = self.conf_rw.read_yaml ( f'{_config_dir}/nanoticker/default_docker-compose.yml')
        self.compose_dict["services"]["nl_nanoticker"] = nanoticker_compose["services"]["nl_nanoticker"]
        self.compose_dict["services"]["nl_nanoticker"]["build"]["args"][0] = f'REMOTE_ADDRESS={self.get_config_value("remote_address")}'
        self.enabled_services.append(f'nanoticker enabled at {self.get_config_value("remote_address")}:42002')

    def set_nanolooker_compose(self):
        nanolooker_compose = self.conf_rw.read_yaml ( f'{_config_dir}/nanolooker/default_docker-compose.yml')
        for container in nanolooker_compose["services"] :
            self.compose_dict["services"][container] = nanolooker_compose["services"][container]
        #in webbrowser: access websocket of the remote machine instead of localhost
        self.compose_dict["services"]["nl_nanolooker"]["build"]["args"][0] = f'REMOTE_ADDRESS={self.get_config_value("remote_address")}'
        #self.compose_dict["services"]["nl_nanolooker"]["environment"][3] = f'WEBSOCKET_DOMAIN=ws://{self.get_config_value("remote_address")}:47000'
        self.enabled_services.append(f'nanolooker enabled at {self.get_config_value("remote_address")}:42000')

    def set_nanomonitor_compose(self):
        host_port_inc = 0
        for node in self.config_dict["representatives"]["nodes"]:
                nanomonitor_compose = self.conf_rw.read_yaml ( f'{_config_dir}/nanomonitor/default_docker-compose.yml')
                container = nanomonitor_compose["services"]["default_monitor"]
                container_name = f'{node["name"]}_monitor'
                self.compose_dict["services"][container_name] = copy.deepcopy(container)
                self.compose_dict["services"][container_name]["container_name"] = container_name
                self.compose_dict["services"][container_name]["volumes"][0] =  self.compose_dict["services"][container_name]["volumes"][0].replace("default_monitor", node["name"])
                self.compose_set_nanomonitor_ports(container_name, host_port_inc)
                host_port_monitor = 46000 + host_port_inc
                self.enabled_services.append(f'nano-node-monitor enabled at {self.get_config_value("remote_address")}:{host_port_monitor}')
                host_port_inc = host_port_inc + 1

    def print_enabled_services(self):
        for service in self.enabled_services :
            logging.info(service)

    def get_config_value(self, key) :
        if key not in self.config_dict : return None
        return self.config_dict[key]

    def write_docker_compose(self):
        self.conf_rw.write_yaml( f"{_nano_nodes_path}/docker-compose.yml", self.compose_dict)


    def compose_add_node(self, node_name):
        #Search for individual docker_tag, then individual executable, then shared docker-tag then shared-executable

        if self.get_representative_config("docker_tag", node_name)["found"]: #search by individual docker_tag
            #default_docker
            container = self.compose_add_container(node_name, "default_docker")
            docker_tag = self.get_representative_config("docker_tag", node_name)["value"]
            container["image"] = f"{docker_tag}"

        elif self.get_representative_config("nano_node_path", node_name)["found"]: #search by individual nano_node_path
            #default_build
            container = self.compose_add_container(node_name, "default_build")
            dockerfile_path = self.cp_dockerfile_and_nano_node(self.get_representative_config("nano_node_path", node_name)["value"], node_name)
            container["build"] = f"{dockerfile_path}/."

        elif self.get_representative_config("docker_tag", None)["found"]: #search by shared docker_tag
            #default_docker
            container = self.compose_add_container(node_name, "default_docker")
            docker_tag = self.get_representative_config("docker_tag", None)["value"]
            container["image"] = f"{docker_tag}"

        elif self.get_representative_config("nano_node_path", None)["found"]: #search by shared nano_node_path
            #default_build
            container = self.compose_add_container(node_name, "default_build")
            dockerfile_path = self.cp_dockerfile_and_nano_node(self.get_representative_config("nano_node_path", None)["value"], node_name)
            container["build"] = f"{dockerfile_path}/."
        else:
            container = self.compose_add_container(node_name, "default_docker")
            container["image"] = f"nanocurrency/nano-beta:latest"
            logging.warning("No docker_tag or nano_node_path specified. use [latest] (nanocurrency/nano-test:latest)")

    def compose_set_node_ports(self, node_name, port_i):
        host_port_rpc = 45000 + port_i
        host_port_ws = 47000 + port_i
        self.compose_dict["services"][node_name]["ports"] = [f'{host_port_rpc}:17076', f'{host_port_ws}:17078']
        #hijack port settings to append config
        node_config = self.get_node_config(node_name)
        node_config["rpc_url"] = f'http://localhost:{host_port_rpc}'

    def compose_set_nanomonitor_ports(self, container_name, port_i):
        host_port_monitor = 46000 + port_i
        self.compose_dict["services"][container_name]["ports"] = [f'{host_port_monitor}:80']



    def cp_dockerfile_and_nano_node(self, exec_path, node_name):
        #copy nano_node into working directory for Dockerfile        
        dockerfile_path = _dockerfile_path.format(node_name=node_name)
        if exec_path.split(".")[-1] == "deb" :
            copy_node =        f"cp -p {exec_path} {dockerfile_path}/package.deb"        
            copy_dockerfile =  f"cp -p {_config_dir}/default_deb_Dockerfile {dockerfile_path}/Dockerfile"      
        else :
            copy_node =        f"cp -p {exec_path} {dockerfile_path}/nano_node"        
            copy_dockerfile =  f"cp -p {_config_dir}/default_Dockerfile {dockerfile_path}/Dockerfile"    
        if os.path.exists(exec_path) :
            os.system(copy_node)
            os.system(copy_dockerfile)
        else :
            logging.error(f'No nano_node could be found at [{exec_path}]. This container will fail on start' )


        return dockerfile_path

    def compose_add_container(self, node_name, default_container) :
        #copies a default container and adds it as a new container
        self.compose_dict["services"][node_name] = copy.deepcopy(self.compose_dict["services"][default_container])
        self.compose_dict["services"][node_name]["container_name"] = node_name
        self.compose_dict["services"][node_name]["volumes"][0] =  self.compose_dict["services"][node_name]["volumes"][0].replace(default_container, node_name)
        return self.compose_dict["services"][node_name]

    def get_config_from_path(self, node_name, config_path_key):
        #returns None if no path is found
        config_dict_l = None
        if self.get_representative_config(config_path_key, node_name)["found"]: #search by individual path
            config_dict_l = self.conf_rw.read_toml(self.get_representative_config(config_path_key, node_name)["value"])
        elif self.get_representative_config(config_path_key, None)["found"]: #search by shared path
            config_dict_l = self.conf_rw.read_toml(self.get_representative_config(config_path_key, None)["value"])
        else :
            pass #return None
        return config_dict_l



    def get_representative_config(self, node_key, node_name):
        #scan node config and match by name. Return the value of the key found in the config
        #response : {"found" : Bool, "value" = ...}
        if node_name is None and node_key is None:
            return {"found" : False }

        if node_name is None :
            #shared config
            if node_key in self.config_dict["representatives"] :
                return {"found" : True, "value" : self.config_dict["representatives"][node_key] }
        else :
            #individual config
            representatives_config = self.h.value_in_dict_array(self.config_dict["representatives"]["nodes"], node_name)
            if representatives_config["found"] == True:
                if node_key in representatives_config["value"]:
                    return {"found" : True, "value" : representatives_config["value"][node_key]}
        return {"found" : False }




