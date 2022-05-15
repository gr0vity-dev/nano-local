import logging
import os
import tomli
import tomli_w
import oyaml as yaml
import secrets
import json
import copy

_app_dir = os.path.dirname(__file__).replace("/src", "") #<-- absolute dir the script is in
_config_dir = os.path.join(_app_dir, "./config")
_config_path = os.path.join(_app_dir, "./nano_local_config.toml") 
_default_compose_path = os.path.join(_app_dir, "./config/default_docker-compose.yml")  
_dockerfile_path = os.path.join(_app_dir, "./nano_nodes/{node_name}")
_nano_nodes_path = os.path.join(_app_dir,  "./nano_nodes")


#compose output file : nano-local/nano_nodes/docker-compose.yml

class ConfigReadWrite: 

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

class ConfigParser :

    preconfigured_peers = []

    def __init__(self, genesis_node_name = "nl_genesis"):   
        self.h = Helpers()
        self.conf_rw = ConfigReadWrite()
        self.config_dict = self.conf_rw.read_toml(_config_path)
        self.compose_dict = self.conf_rw.read_yaml(_default_compose_path)
        self.__config_dict_set_node_variables()  #modifies config_dict 
        self.__config_dict_set_default_values() #modifies config_dict
        self.__config_dict_add_genesis_to_nodes(genesis_node_name)
        self.__set_preconfigured_peers()    
        self.__set_docker_compose() #also sets rpc_url in config_dict.representative.nodes.node_name.rpc_url     

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
        return self.config_dict 
    
    def __config_dict_add_genesis_to_nodes(self, genesis_node_name) :
        self.config_dict["representatives"]["nodes"].insert(0, { "name" : genesis_node_name,
                                                                 "key" : self.config_dict["genesis_key"] })


    def __set_preconfigured_peers(self ):    
        for node in self.config_dict["representatives"]["nodes"]:            
            if node["name"] not in self.preconfigured_peers :
                self.preconfigured_peers.append(node["name"])    
        return self.preconfigured_peers      


    def get_node_config(self, node_name):
        result = self.h.value_in_dict_array(self.config_dict["representatives"]["nodes"], node_name)
        if result["found"] : return result["value"]   

    def get_node_names(self) :
        response = []
        for node in self.config_dict["representatives"]["nodes"]:
            response.append(node["name"])
        return response
    
    def __set_docker_compose(self):  
        host_port_inc = 0
        for node in self.config_dict["representatives"]["nodes"]:  
            self.compose_add_node(node["name"])
            self.compose_set_node_ports(node["name"], host_port_inc)
            host_port_inc = host_port_inc + 1  
        
        if self.config_dict["nanolooker_enable"] :
            nanolooker_compose = self.conf_rw.read_yaml ( f'{_config_dir}/nanolooker/docker-compose.yml')

            for container in nanolooker_compose["services"] :
                self.compose_dict["services"][container] = nanolooker_compose["services"][container]

        
        #remove default container
        self.compose_dict["services"].pop("default_docker", None)
        self.compose_dict["services"].pop("default_build", None)  

    def write_docker_compose(self):  
        self.conf_rw.write_yaml( f"{_nano_nodes_path}/docker-compose.yml", self.compose_dict)


    def compose_add_node(self, node_name):
        #Search for individual docker_tag, then individual executable, then shared docker-tag then shared-executable
        
        if self.get_representative_config("docker_tag", node_name)["found"]: #search by individual docker_tag   
            #default_docker
            container = self.compose_add_container(node_name, "default_docker")
            docker_tag = self.get_representative_config("docker_tag", node_name)["value"]
            container["image"] = f"nanocurrency/nano-test:{docker_tag}" 

        elif self.get_representative_config("nano_node_path", node_name)["found"]: #search by individual nano_node_path
            #default_build
            container = self.compose_add_container(node_name, "default_build")
            dockerfile_path = self.cp_dockerfile_and_nano_node(self.get_representative_config("nano_node_path", node_name)["value"], node_name)
            container["build"] = f"{dockerfile_path}/."       

        elif self.get_representative_config("docker_tag", None)["found"]: #search by shared docker_tag
            #default_docker
            container = self.compose_add_container(node_name, "default_docker")
            docker_tag = self.get_representative_config("docker_tag", None)["value"]
            container["image"] = f"nanocurrency/nano-test:{docker_tag}" 
        
        elif self.get_representative_config("nano_node_path", None)["found"]: #search by shared nano_node_path
            #default_build
            container = self.compose_add_container(node_name, "default_build")
            dockerfile_path = self.cp_dockerfile_and_nano_node(self.get_representative_config("nano_node_path", None)["value"], node_name)
            container["build"] = f"{dockerfile_path}/."  
        else:
            container = self.compose_add_container(node_name, "default_docker")
            container["image"] = f"nanocurrency/nano-test:latest" 
            logging.warning("No docker_tag or nano_node_path specified. use [latest] (nanocurrency/nano-test:latest)")
    
    def compose_set_node_ports(self, node_name, port_i):
        host_port_rpc = 45000 + port_i
        host_port_ws = 47000 + port_i
        self.compose_dict["services"][node_name]["ports"] = [f'{host_port_rpc}:17076', f'{host_port_ws}:17078'] 
        #hijack port settings to append config
        node_config = self.get_node_config(node_name)
        node_config["rpc_url"] = f'http://localhost:{host_port_rpc}'
        
    
    def cp_dockerfile_and_nano_node(self, nano_node_path, node_name):
        #copy nano_node into working directory for Dockerfile      
        dockerfile_path = _dockerfile_path.format(node_name=node_name)  
        copy_node =        f"cp -p {nano_node_path} {dockerfile_path}/nano_node"
        copy_dockerfile =  f"cp -p {_config_dir}/default_Dockerfile {dockerfile_path}/Dockerfile"        

        if os.path.exists(nano_node_path) :         
            os.system(copy_node)  
            os.system(copy_dockerfile)
        else :
            logging.error(f'No nano_node could be found at [{nano_node_path}]. This container will fail on start' )
        

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


   

