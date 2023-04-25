import logging
import os
import subprocess
import tomli
import tomli_w
import oyaml as yaml
import secrets
import json
import copy
from datetime import datetime
from math import ceil
from nanolib import Block
from extradict import NestedData

from nanolocal.common.nl_nanolib import NanoLibTools, raw_high_precision_multiply
from nanolocal.common.nl_rpc import NanoRpc

_default_path = "nanolocal"
_app_dir = os.environ.get("NL_APP_DIR",
                          os.path.dirname(os.path.dirname(__file__)))
_config_dir = os.path.join(_app_dir, "./services")
_config_path = os.path.join(_app_dir, "./nl_config.toml")
_default_compose_path = f"{_config_dir}/default_docker-compose.yml"
_dockerfile_path = os.path.join(_app_dir, "/nano_nodes/{node_name}")
_default_nanomonitor_config = os.path.join(_config_dir,
                                           "nanomonitor/default_config.php")
_nano_nodes_path = os.path.join(_app_dir, "./nano_nodes")
_tcp_analyzer_path = "./tcp_analyzer/"

#compose output file : nano-local/nano_nodes/docker-compose.yml


def str2bool(v):
    return str(v).lower() in ("yes", "true", "t", "1")


class ConfigReadWrite:

    def __init__(self):
        if not os.path.exists("nanolocal/nl_config.toml"):
            logging.warning("No config file exists. creating 'nl_config.toml'")
            subprocess.call(
                "cp -p nanolocal/nl_config.example.toml nanolocal/nl_config.toml",
                shell=True)

    def write_json(self, path, json_dict):
        with open(path, "w") as f:
            json.dump(json_dict, f)

    def append_json(self, path, json_dict):
        with open(path, "a") as f:
            json.dump(json_dict, f)
            f.write('\n')

    def read_json(self, path):
        with open(path, "r") as f:
            return json.load(f)

    def read_file(self, path):
        with open(path, "r") as f:
            return f.readlines()

    def write_list(self, path, list):
        with open(path, "w") as f:
            print(*list, sep="\n", file=f)

    def append_line(self, path, line):
        with open(path, 'a') as file:
            file.write(line)

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
            yaml.dump(json.loads(str(content).replace("'", '"')),
                      f,
                      default_flow_style=False)


class ConfigParser:

    preconfigured_peers = []

    def __init__(self):
        self.enabled_services = []
        self.conf_rw = ConfigReadWrite()
        self.nano_lib = NanoLibTools()
        self.config_dict = self.conf_rw.read_toml(_config_path)
        self.compose_dict = self.conf_rw.read_yaml(_default_compose_path)
        self.__config_dict_add_genesis_to_nodes()
        self.__config_dict_set_node_variables()  #modifies config_dict
        self.__config_dict_set_default_values()  #modifies config_dict
        self.__set_preconfigured_peers()
        self.__set_node_accounts()
        self.__set_balance_from_vote_weight()
        self.__set_special_account_data()
        #self.__set_docker_compose()

    def __set_node_accounts(self):
        available_supply = 340282366920938463463374607431768211455 - int(
            self.config_dict.get("burn_amount", 0)) - 1
        for node in self.config_dict["representatives"]["nodes"]:

            if "key" in node:
                account_data = self.nano_lib.key_expand(node["key"])
            else:
                account_data = self.nano_lib.nanolib_account_data(
                    seed=node["seed"], index=0)

            node["account"] = account_data["account"]
            node["account_data"] = account_data
            if "vote_weight_percent" in node:
                node["balance"] = raw_high_precision_multiply(
                    available_supply, node["vote_weight_percent"])

    def __set_special_account_data(self):
        self.config_dict["burn_account_data"] = {
            "account":
            "nano_1111111111111111111111111111111111111111111111111111hifc8npp"
        }
        self.config_dict["genesis_account_data"] = self.nano_lib.key_expand(
            self.config_dict["genesis_key"])
        self.config_dict["canary_account_data"] = self.nano_lib.key_expand(
            self.config_dict["canary_key"])

    def __config_dict_set_node_variables(self):
        self.config_dict.setdefault("env", "local")
        modified_config = False

        if "remote_address" not in self.config_dict:
            self.config_dict["remote_address"] = '127.0.0.1'

        if "host_port_peer" not in self.config_dict["representatives"]:
            self.config_dict["representatives"]["host_port_peer"] = 44000
        if "host_port_peer" not in self.config_dict["representatives"]:
            self.config_dict["representatives"]["host_port_rpc"] = 45000
        if "host_port_peer" not in self.config_dict["representatives"]:
            self.config_dict["representatives"]["host_port_ws"] = 47000

        if "node_prefix" not in self.config_dict["representatives"]:
            self.config_dict["representatives"]["node_prefix"] = "ns"

        host_port_inc = 0  #set incremental ports for nodes starting with 0
        for node in self.config_dict["representatives"]["nodes"]:

            if "name" not in node:
                node["name"] = f"{secrets.token_hex(6)}".lower()
                logging.warning(
                    f'no name set for a node. New name : {node["name"]}')
                modified_config = True
            node["name"] = node["name"].lower()

            if "seed" not in node and not self.is_genesis(node):
                node["seed"] = secrets.token_hex(32)
                logging.warning(
                    f'no seed set for a node. New seed : {node["seed"]}')
                modified_config = True

            #Add ports for each node
            node["name"] = self.get_node_prefix() + node["name"]

            if self.config_dict["env"] == "gcloud": host_port_inc = 0

            node["host_port_peer"] = self.config_dict["representatives"][
                "host_port_peer"] + host_port_inc
            node["host_port_rpc"] = self.config_dict["representatives"][
                "host_port_rpc"] + host_port_inc
            node["host_port_ws"] = self.config_dict["representatives"][
                "host_port_ws"] + host_port_inc

            if "host_ip" not in node:
                node["host_ip"] = self.config_dict["remote_address"]

            node[
                "rpc_url"] = f'http://{node["host_ip"]}:{node["host_port_rpc"]}'
            node["ws_url"] = f'ws://{node["host_ip"]}:{node["host_port_ws"]}'
            host_port_inc = host_port_inc + 1

        if modified_config:
            user_input = "nl_config.toml was modified. Save current version? This will change the structure (y/n)"
            if user_input == 'y':
                self.conf_rw.write_toml(_config_path, self.config_dict)

    def __config_dict_set_default_values(self):
        #self.config_dict = conf_rw.read_toml(_config_path)
        self.config_dict["NANO_TEST_EPOCH_1"] = "0x000000000000000f"

        self.config_dict.setdefault(
            "genesis_key",
            "12C91837C846F875F56F67CD83040A832CFC0F131AF3DFF9E502C0D43F5D2D15")
        self.config_dict.setdefault(
            "canary_key",
            "FB4E458CB13508353C5B2574B82F1D1D61367F61E88707F773F068FF90050BEE")
        self.config_dict.setdefault("epoch_count", 2)
        self.config_dict.setdefault("NANO_TEST_EPOCH_2", "0xfff0000000000000")
        self.config_dict.setdefault("NANO_TEST_EPOCH_2_RECV",
                                    "0xfff0000000000000")
        self.config_dict.setdefault("NANO_TEST_MAGIC_NUMBER", "LC")
        self.config_dict.setdefault(
            "NANO_TEST_CANARY_PUB",
            "CCAB949948224D6B33ACE0E078F7B2D3F4D79DF945E46915C5300DAEF237934E")

        #nanolooker
        self.config_dict.setdefault(
            "nanolooker_enable",
            str2bool(self.config_dict.get("nanolooker_enable", False)))
        self.config_dict.setdefault("nanolooker_port", 42000)
        self.config_dict.setdefault("nanolooker_node_name", "genesis")
        self.config_dict.setdefault("nanolooker_mongo_port", 27017)

        #nanomonitor, nanoticker, nano-vote-visualizer
        self.config_dict.setdefault(
            "nanomonitor_enable",
            str2bool(self.config_dict.get("nanomonitor_enable", False)))
        self.config_dict.setdefault(
            "nanoticker_enable",
            str2bool(self.config_dict.get("nanoticker_enable", False)))
        self.config_dict.setdefault(
            "nanovotevisu_enable",
            str2bool(self.config_dict.get("nanovotevisu_enable", False)))

        #prom-exporter
        self.config_dict.setdefault(
            "promexporter_enable",
            str2bool(self.config_dict.get("promexporter_enable", False)))
        self.config_dict.setdefault(
            "prom_gateway",
            str2bool(
                self.config_dict.get("prom_gateway", "nl_pushgateway:9091")))
        self.config_dict.setdefault("prom_runid", "default")

        #traffic control
        self.config_dict.setdefault(
            "tc_enable", str2bool(self.config_dict.get("tc_enable", False)))

        #tcpdump
        self.config_dict.setdefault(
            "tcpdump_enable",
            str2bool(self.config_dict.get("tcpdump_enable", False)))
        self.config_dict.setdefault(
            "tcpdump_filename",
            f"nl_tcpdump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pcap")

    def __config_dict_add_genesis_to_nodes(self):
        genesis_node_name = "genesis"
        genesis_node = next(
            (d for d in self.config_dict["representatives"]["nodes"]
             if d["name"] == genesis_node_name), None)

        if genesis_node:
            genesis_node.setdefault("key", self.config_dict["genesis_key"])
            genesis_node.setdefault("is_genesis", True)
            return

        self.config_dict["representatives"]["nodes"].insert(
            0, {
                "name": genesis_node_name,
                "key": self.config_dict["genesis_key"],
                "is_genesis": True
            })

    def __set_preconfigured_peers(self):
        for node in self.config_dict["representatives"]["nodes"]:
            if node["name"] not in self.preconfigured_peers:
                self.preconfigured_peers.append(node["name"])
        return self.preconfigured_peers

    def __is_principal_representative(self, available_supply, balance):
        response = False
        if int(balance) >= int(available_supply / 1000):
            response = True
        return response

    def __set_balance_from_vote_weight(self):
        available_supply = 340282366920938463463374607431768211455 - int(
            self.config_dict.get("burn_amount", 0)) - 1
        genesis_balance = available_supply
        for node_conf in self.get_nodes_config():
            if "vote_weight" in node_conf:
                node_conf["balance"] = raw_high_precision_multiply(
                    available_supply * node_conf["vote_weight"])
            #evaluate if a node is a PR
            #if a node has more than 0.1% of available supply it's considered a PR.
            #this is accurate in the case that all nodes are online. (which is reasonable in a private network)

            if "balance" in node_conf:
                genesis_balance = genesis_balance - int(node_conf["balance"])
                node_conf["is_pr"] = self.__is_principal_representative(
                    available_supply, node_conf["balance"])

        #add genesis_balance to config
        self.get_genesis_config(
        )["is_pr"] = self.__is_principal_representative(
            available_supply, genesis_balance)

    def value_in_dict(self, dict, value_l):
        for key, value in dict.items():
            if value == value_l:
                return {"found": True, "value": dict}
        return {"found": False, "value": None}

    def value_in_dict_array(self, dict_array, value_l):
        for dict in dict_array:
            dict_found = self.value_in_dict(dict, value_l)
            if dict_found["found"]:
                return dict_found
        return {"found": False, "value": None}

    def is_genesis(self, node_conf):
        if "is_genesis" in node_conf and node_conf["is_genesis"]:
            return True
        return False

    def recursive_pop_key_if_value(self, d, k, val):
        #if dict (d), search for key (k) that has value (val) and remove key-value pairfrom dict
        if k in d and d[k] == val:
            d.pop(k)
        for v in d.values():
            if isinstance(v, list):
                for el in v:
                    self.recursive_pop_key_if_value(el, k, val)
            elif isinstance(v, dict):
                return self.recursive_pop_key_if_value(v, k, val)
        return None

    def modify_nanolocal_config(self, nested_path: str, nested_value: str):
        #EXAMPLE, set "docker_tag"
        #nested_path : "representatives.nodes.*.docker_tag"
        #nested_value : "nanocurrency/..."

        #EXAMPLE, remove "docker_tag"
        #nested_path : "representatives.nodes.*.docker_tag"
        #nested_value : NULL

        config_l = NestedData(self.conf_rw.read_toml(_config_path))
        if nested_value is None:
            config_l.merge("DELETE_ME", nested_path)
        else:  #set value
            config_l.merge(nested_value, nested_path)

        #Remove al lkeys where value is "DELETE_ME"
        self.recursive_pop_key_if_value(config_l.data,
                                        nested_path.split(".")[-1:][0],
                                        "DELETE_ME")

        #update current config instance, so we don't need to reread from disk on each modification
        self.config_dict = config_l
        #save to disk aswell
        self.conf_rw.write_toml(_config_path, config_l.data)

    def set_prom_runid(self, runid):
        self.runid = runid

    # def account_from_seed(self, seed):
    #     seed_u = unhexlify(seed)
    #     index = 0x00000000.to_bytes(4, 'big')  # 1
    #     blake2b_state = hashlib.blake2b(digest_size=32)
    #     concat = seed_u + index
    #     blake2b_state.update(concat)
    #     # where `+` means concatenation, not sum: https://docs.python.org/3/library/hashlib.html#hashlib.hash.update
    #     # code line above is equal to `blake2b_state.update(seed); blake2b_state.update(index)`
    #     private_key = blake2b_state.digest()
    #     expanded_key = self.key_expand(hexlify(private_key))
    #     expanded_key["seed"] = seed
    #     return expanded_key

    def get_name_with_prefix(self, node_name):
        return self.get_node_prefix() + node_name

    def get_node_prefix(self):
        #set during initialisation in __config_dict_set_node_variables
        return self.config_dict["representatives"]["node_prefix"] + "_"

    def get_project_name(self):
        return self.get_node_prefix() + "nanolocal"

    def get_xnolib_localctx(self):
        ctx = {
            'peers': {
                node_conf["name"]: {
                    "ip": f'::ffff:{node_conf["host_ip"]}',
                    "port": node_conf["host_port_peer"],
                    "score": 1000,
                    "is_voting": node_conf["is_pr"]
                }
                for node_conf in self.get_nodes_config()
            },
            'repservurl': '',
            'genesis_pub': self.get_genesis_account_data()["public"],
            'epoch_v2_signing_account':
            self.config_dict["NANO_TEST_CANARY_PUB"],
            'genesis_block': self.get_genesis_block(as_json=True),
            'peerserviceurl': ''
        }

        return ctx

    def get_canary_pub_key(self):
        env = self.config_dict["env"]
        canary_pub = ""
        if env in ["gcloud", "local"]:
            canary_pub = self.nano_lib.key_expand(
                self.config_dict["canary_key"])["public"]
        elif env == "beta":
            canary_pub = "868C6A9F79D4506E029B378262B91538C5CB26D7C346B63902FFEB365F1C1947"
        elif env == "live":
            canary_pub = "7CBAF192A3763DAEC9F9BAC1B2CDF665D8369F8400B4BC5AB4BA31C00BAA4404"
        else:
            raise ValueError(
                f'"{env}" is not in the list of accepted valued ["local", "beta", "live"] for variable "env" in nl_config.toml'
            )
        return canary_pub

    def get_genesis_block(self, as_json=False):

        env = self.config_dict["env"]

        if env in ["gcloud", "local"]:
            genesis_account = self.get_genesis_account_data()
            block = Block(block_type="open",
                          account=genesis_account["account"],
                          representative=genesis_account["account"],
                          source=genesis_account["public"])

            block.solve_work(
                difficulty=self.config_dict["NANO_TEST_EPOCH_1"].replace(
                    "0x", ""))

            private_key = genesis_account["private"]
            block.sign(private_key)
            json_block = block.json()

        elif env == "beta":
            json_block = str({
                "type":
                "open",
                "source":
                "259A43ABDB779E97452E188BA3EB951B41C961D3318CA6B925380F4D99F0577A",
                "representative":
                "nano_1betagoxpxwykx4kw86dnhosc8t3s7ix8eeentwkcg1hbpez1outjrcyg4n1",
                "account":
                "nano_1betagoxpxwykx4kw86dnhosc8t3s7ix8eeentwkcg1hbpez1outjrcyg4n1",
                "work":
                "79d4e27dc873c6f2",
                "signature":
                "4BD7F96F9ED2721BCEE5EAED400EA50AD00524C629AE55E9AFF11220D2C1B00C3D4B3BB770BF67D4F8658023B677F91110193B6C101C2666931F57046A6DB806"
            }).replace("'", '"')

        elif env == "live":
            json_block = str({
                "type":
                "open",
                "source":
                "E89208DD038FBB269987689621D52292AE9C35941A7484756ECCED92A65093BA",
                "representative":
                "xrb_3t6k35gi95xu6tergt6p69ck76ogmitsa8mnijtpxm9fkcm736xtoncuohr3",
                "account":
                "xrb_3t6k35gi95xu6tergt6p69ck76ogmitsa8mnijtpxm9fkcm736xtoncuohr3",
                "work":
                "62f05417dd3fb691",
                "signature":
                "9F0C933C8ADE004D808EA1985FA746A7E95BA2A38F867640F53EC8F180BDFE9E2C1268DEAD7C2664F356E37ABA362BC58E46DBA03E523A7B5A19E4B6EB12BB02"
            }).replace("'", '"')
        else:
            raise ValueError(
                f'"{env}" is not in the list of accepted valued ["local", "beta", "live"] for variable "env" in nl_config.toml'
            )

        if as_json:
            return json.loads(json_block)

        return json_block

    def get_node_rpc(self, node_name):
        node_conf = self.get_node_config(node_name)
        return node_conf["rpc_url"]

    def get_nodes_rpc(self):
        api = []
        for node_name in self.get_nodes_name():
            node_conf = self.get_node_config(node_name)
            api.append(node_conf["rpc_url"])
        return api

    def get_nodes_rpc_port(self):
        api = {}
        for node_name in self.get_nodes_name():
            node_conf = self.get_node_config(node_name)
            api[node_name] = node_conf["rpc_url"].split(":")[2]
        return api

    def get_node_name_from_rpc_url(self, rpc_endpoint: NanoRpc):

        for node_name in self.get_nodes_name():
            node_conf = self.get_node_config(node_name)
            if rpc_endpoint.RPC_URL == node_conf["rpc_url"]: return node_name
        return None

    def get_remote_address(self):
        return self.config_dict["remote_address"]

    # def key_expand(self, private_key):

    #     signing_key = SigningKey(unhexlify(private_key))
    #     private_key = signing_key.to_bytes().hex()
    #     public_key = signing_key.get_verifying_key().to_bytes().hex()

    #     return {
    #         "private": private_key,
    #         "public": public_key,
    #         "account": self.h.public_key_to_nano_address(unhexlify(public_key))
    #     }

    def write_nanomonitor_config(self, node_name):
        nanomonitor_config = self.conf_rw.read_file(
            _default_nanomonitor_config)
        destination_path = str(
            os.path.join(
                _dockerfile_path,
                "nanoNodeMonitor/config.php")).format(node_name=node_name)
        node_config = self.get_node_config(node_name)
        nanomonitor_config[4] = f"$nanoNodeName = '{node_name}';"
        nanomonitor_config[5] = f"$nanoNodeRPCIP   = '{node_name}';"
        nanomonitor_config[
            7] = f"$nanoNodeAccount = '{node_config['account']}';"
        self.conf_rw.write_list(destination_path, nanomonitor_config)

    def get_all(self):
        return self.config_dict

    def get_genesis_node_name(self):
        return self.config_dict["representatives"]["nodes"][0]["name"]

    def get_genesis_config(self):
        genesis_name = self.get_genesis_node_name()
        return self.get_node_config(genesis_name)

    def get_node_config(self, node_name):
        result = self.value_in_dict_array(
            self.config_dict["representatives"]["nodes"], node_name)
        if result["found"]:
            return result["value"]

    def get_genesis_account_data(self):
        return self.config_dict["genesis_account_data"]

    def get_burn_account_data(self):
        return self.config_dict["burn_account_data"]

    def get_canary_account_data(self):
        return self.config_dict["canary_account_data"]

    def get_max_balance_key(self):
        #returns the privatekey for the node with the highest defined balance.
        nodes_conf = self.get_nodes_config()
        max_balance = max(
            int(x["balance"]) if "balance" in x else 0
            for x in self.get_nodes_config())
        node_conf = list(
            filter(lambda x: int(x.get("balance", 0)) == max_balance,
                   self.get_nodes_config()))
        return node_conf[0]["account_data"]["private"]

    def get_nodes_name(self):
        response = []
        for node in self.config_dict["representatives"]["nodes"]:
            response.append(node["name"])
        return response

    def get_nodes_config(self):
        res = []
        for node_name in self.get_nodes_name():
            #res[node_name] = self.get_node_config(node_name)
            res.append(self.get_node_config(node_name))
        return res

    def set_node_balance(self, node_name, balance):
        self.get_node_config(node_name)["balance"] = balance

    def skip_testcase(self, testcase_fullname):
        testcase_fullname = testcase_fullname.replace("testcases.", "")
        return not self.run_testcase(testcase_fullname)

    def any_true_test_method(self, test_class):
        run = self.get_testcases()
        for test_method, value in run["test_methods"].items():
            if str(test_method).startswith(test_class) and value == True:
                return True

    def any_true_testclass(self, test_module):
        run = self.get_testcases()
        for test_class, value in run["test_classes"].items():
            if str(test_class).startswith(test_module) and value == True:
                return True

    def run_testcase(self, testcase_fullname):

        run = self.get_testcases()
        split_name = testcase_fullname.split(".")
        test_module = testcase_fullname.split(
            ".")[0] if len(split_name) > 0 else None
        test_class = f'{test_module}.{testcase_fullname.split(".")[1]}' if len(
            split_name) > 1 else None
        test_case = f'{test_module}.{test_class}.{testcase_fullname.split(".")[2]}' if len(
            split_name) > 2 else None

        if testcase_fullname in run["test_methods"]:
            return run["test_methods"][testcase_fullname]
        #only execute entire class if testcases defined for the current testclass
        if not self.any_true_test_method(
                test_class) and test_class in run["test_classes"]:
            return run["test_classes"][test_class]
        if not self.any_true_testclass(
                test_module) and test_module in run["test_modules"]:
            return run["test_modules"][test_module]
        return False

    def get_testcases(self):
        #"skip_all" will display the testcases as being "skipped"
        #"ignore" will remove the testcases and tehy will not be displayed at all when running test or pytest
        run = {"test_methods": {}, "test_classes": {}, "test_modules": {}}

        if "testcases" not in self.config_dict:
            logging.warn("No testcases have been defined")
            return run

        for test_module in self.config_dict["testcases"]:
            if "ignore_module" in self.config_dict["testcases"][test_module]:
                logging.info(f"Module 'testcases.{test_module}' is ignored")
                # dont add module even some tests are defined
                continue

            if "skip_all" in self.config_dict["testcases"][test_module]:
                if self.config_dict["testcases"][test_module]["skip_all"]:
                    logging.info(
                        f"all tests from 'testcases.{test_module}' are skipped"
                    )
                    run["test_modules"][test_module] = False
                    continue
            else:
                run["test_modules"][test_module] = True

            for test_class in self.config_dict["testcases"][test_module]:
                if "skip_all" in self.config_dict["testcases"][test_module][
                        test_class]:
                    # list tests as skipped
                    if self.config_dict["testcases"][test_module][test_class][
                            "skip_all"]:
                        logging.info(
                            f"all tests from 'testcases.{test_module}.{test_class}' are skipped"
                        )
                        run["test_classes"][
                            f"{test_module}.{test_class}"] = False
                        continue
                else:
                    run["test_classes"][f"{test_module}.{test_class}"] = True

                for test_method, value in self.config_dict["testcases"][
                        test_module][test_class].items():
                    if len(test_method) > 0:
                        run["test_methods"][f"{test_module}.{test_class}.{test_method}"
                                           ] = value if value != {} else True

        return run

    # def set_docker_compose(self):
    #     #add prefix to the docker network
    #     self.compose_dict["networks"]["nano-local"][
    #         "name"] = self.get_node_prefix(
    #         ) + self.compose_dict["networks"]["nano-local"]["name"]

    #     for node in self.config_dict["representatives"]["nodes"]:
    #         self.compose_add_node(node["name"])
    #         self.compose_set_node_ports(node["name"])

    def set_docker_compose(self):
        default_service_names = [
            service for service in self.compose_dict["services"]
        ]

        self.compose_dict["networks"]["nano-local"][
            "name"] = self.get_node_prefix(
            ) + self.compose_dict["networks"]["nano-local"]["name"]

        #Add nodes and ports
        for node in self.config_dict["representatives"]["nodes"]:
            self.compose_add_node(node["name"])
            self.compose_set_node_ports(node["name"])

        if self.get_config_value("nanolooker_enable"):
            self.set_nanolooker_compose()

        if self.get_config_value("nanomonitor_enable"):
            self.set_nanomonitor_compose()

        if self.get_config_value("nanoticker_enable"):
            self.set_nanoticker_compose()

        if self.get_config_value("nanovotevisu_enable"):
            self.set_nanovotevisu_compose()

        if bool(self.get_config_value("promexporter_enable")):
            self.set_promexporter_compose()

        if bool(self.get_config_value("tcpdump_enable")):
            self.set_tcpdump_compose()

        #remove default container
        for service in default_service_names:
            self.compose_dict["services"].pop(service, None)

    def set_nanovotevisu_compose(self):
        nanoticker_compose = self.conf_rw.read_yaml(
            f'{_config_dir}/nanovotevisu/default_docker-compose.yml')
        self.compose_dict["services"]["nl_nanovotevisu"] = nanoticker_compose[
            "services"]["nl_nanovotevisu"]
        self.compose_dict["services"]["nl_nanovotevisu"]["build"]["args"][
            0] = f'REMOTE_ADDRESS={self.get_config_value("remote_address")}'
        self.compose_dict["services"]["nl_nanovotevisu"]["build"]["args"][
            1] = f'HOST_ACCOUNT={self.get_node_config(self.get_nodes_name()[0])["account"]}'
        self.enabled_services.append(
            f'nano-vote-visualizer enabled at {self.get_config_value("remote_address")}:42001'
        )

    def set_nanoticker_compose(self):
        nanoticker_compose = self.conf_rw.read_yaml(
            f'{_config_dir}/nanoticker/default_docker-compose.yml')
        self.compose_dict["services"]["nl_nanoticker"] = nanoticker_compose[
            "services"]["nl_nanoticker"]
        self.compose_dict["services"]["nl_nanoticker"]["build"]["args"][
            0] = f'REMOTE_ADDRESS={self.get_config_value("remote_address")}'
        self.enabled_services.append(
            f'nanoticker enabled at {self.get_config_value("remote_address")}:42002'
        )

    def set_nanolooker_compose(self):
        nanolooker_compose = self.conf_rw.read_yaml(
            f'{_config_dir}/nanolooker/default_docker-compose.yml')

        for container in nanolooker_compose["services"]:
            container_name = self.get_node_prefix(
            ) + nanolooker_compose["services"][container]["container_name"]
            #Add all containers from docker-compose file to our compose_dict
            self.compose_dict["services"][container] = nanolooker_compose[
                "services"][container]
            #add prefix to container_name defined in docker-compose file

            self.compose_dict["services"][container][
                "container_name"] = container_name

        nanolooker_node_config = self.get_node_config(
            self.get_name_with_prefix(
                self.config_dict["nanolooker_node_name"]))

        #in webbrowser: access websocket of the remote machine instead of localhost
        self.compose_dict["services"]["nl_nanolooker"]["build"]["args"][
            0] = f'REMOTE_ADDRESS={self.get_config_value("remote_address")}'
        self.compose_dict["services"]["nl_nanolooker"]["build"]["args"][
            1] = f'MONGO_CONTAINER={self.compose_dict["services"]["nl_nanolooker_mongo"]["container_name"]}'
        self.compose_dict["services"]["nl_nanolooker"]["build"]["args"][
            2] = f'MONGO_PORT={self.config_dict["nanolooker_mongo_port"]}'
        self.compose_dict["services"]["nl_nanolooker"]["build"]["args"][
            3] = f'NODE_WEBSOCKET_PORT={nanolooker_node_config["host_port_ws"]}'
        #set node for RPC
        self.compose_dict["services"]["nl_nanolooker"]["environment"][
            2] = f'RPC_DOMAIN=http://{nanolooker_node_config["name"]}:17076'
        #set correct port
        self.compose_dict["services"]["nl_nanolooker"]["ports"][
            0] = f'{self.config_dict["nanolooker_port"]}:3010'
        self.enabled_services.append(
            f'nanolooker enabled at {self.get_config_value("remote_address")}:{self.config_dict["nanolooker_port"]}'
        )

    def set_nanomonitor_compose(self):
        host_port_inc = 0
        for node in self.config_dict["representatives"]["nodes"]:
            nanomonitor_compose = self.conf_rw.read_yaml(
                f'{_config_dir}/nanomonitor/default_docker-compose.yml')
            container = nanomonitor_compose["services"]["default_monitor"]
            container_name = f'{node["name"]}_monitor'
            self.compose_dict["services"][container_name] = copy.deepcopy(
                container)
            self.compose_dict["services"][container_name][
                "container_name"] = container_name
            self.compose_dict["services"][container_name]["volumes"][
                0] = self.compose_dict["services"][container_name]["volumes"][
                    0].replace("default_monitor", node["name"])
            self.compose_set_nanomonitor_ports(container_name, host_port_inc)
            host_port_monitor = 46000 + host_port_inc
            self.enabled_services.append(
                f'nano-node-monitor enabled at {self.get_config_value("remote_address")}:{host_port_monitor}'
            )
            host_port_inc = host_port_inc + 1

    def set_promexporter_compose(self):

        host_ip = self.get_config_value("remote_address")
        if host_ip == '127.0.0.1':
            raise ValueError(
                "Please configure remote_address in nl_config.toml if you set promexporter_enable == True"
            )
        #Create prometheus, prom-gateway and grafana IF we use default prom-gateway
        if self.get_config_value("prom_gateway") == "nl_pushgateway:9091":
            promexporter_compose = self.conf_rw.read_yaml(
                f'{_config_dir}/promexporter/default_docker-compose.yml')
            for container in promexporter_compose["services"]:
                self.compose_dict["services"][
                    container] = promexporter_compose["services"][container]
            for volume in promexporter_compose["volumes"]:
                self.compose_dict["volumes"][volume] = promexporter_compose[
                    "volumes"][volume]

        #Create 1 exporter per node
        for node in self.config_dict["representatives"]["nodes"]:
            node_config = self.get_node_config(node["name"])
            node_rpc_port = node_config["host_port_rpc"]

            prom_gateway = self.get_config_value("prom_gateway")
            prom_runid = self.get_config_value("prom_runid")

            nanomonitor_compose = self.conf_rw.read_yaml(
                f'{_config_dir}/promexporter/default_exporter_docker-compose.yml'
            )
            container = nanomonitor_compose["services"]["default_exporter"]
            container_name = f'{node["name"]}_exporter'
            self.compose_dict["services"][container_name] = copy.deepcopy(
                container)
            self.compose_dict["services"][container_name][
                "container_name"] = container_name
            self.compose_dict["services"][container_name]["command"]

            self.compose_dict["services"][container_name][
                "command"] = f'--rpchost {host_ip} --rpc_port {node_rpc_port} --push_gateway {prom_gateway} --hostname {node["name"]} --runid {prom_runid} --interval 2'

            self.compose_dict["services"][container_name][
                "pid"] = f'service:{node["name"]}'

            self.enabled_services.append(
                f'{container_name} added for node {node["name"]}')

        self.enabled_services.append(
            f'promexporter enabled at {self.get_config_value("remote_address")}:42005'
        )

    def set_tcpdump_compose(self):

        tcp_analyzer_config_path = f'{_tcp_analyzer_path}/config.json'
        if not os.path.exists(tcp_analyzer_config_path):
            conf_source_path = f'{_config_dir}/tcpdump/tcp_analyzer_config.example.json'
            copy_conf = f'cp -p {conf_source_path} {tcp_analyzer_config_path}'
            os.system(copy_conf)

        tcp_analyzer_config = self.conf_rw.read_json(tcp_analyzer_config_path)
        tcp_analyzer_config["files_name_in"] = []

        tcpdump_compose = self.conf_rw.read_yaml(
            f'{_config_dir}/tcpdump/default_docker-compose.yml')
        container = tcpdump_compose["services"]["ns_tcpdump"]

        container_name = f'ns_tcpdump'
        pcap_file_name = f'{self.get_config_value("tcpdump_filename")}'

        #container_name = 'ns_tcpdump'

        self.compose_dict["services"][container_name] = container
        self.compose_dict["services"][container_name][
            "container_name"] = container_name

        #mount pcap file
        self.compose_dict["services"][container_name]["volumes"][
            0] = self.compose_dict["services"][container_name]["volumes"][
                0].replace("FILENAME", pcap_file_name)
        #network_mode
        self.compose_dict["services"][container_name]["network_mode"] = "host"

        #manually create the mounted file, otherwise docker-compose will create a directory
        pcap_file_path = f'{_nano_nodes_path}/{pcap_file_name}'
        tcp_analyzer_config["files_name_in"].append(pcap_file_path)
        subprocess.call(f'touch {pcap_file_path}', shell=True)
        self.enabled_services.append(
            f'TCPDUMP enabled ! This may lead to a decrease in performance!')
        self.conf_rw.write_json(tcp_analyzer_config_path, tcp_analyzer_config)

    def print_enabled_services(self):
        for service in self.enabled_services:
            logging.info(service)

    def get_config_value(self, key):
        if key not in self.config_dict:
            return None
        return self.config_dict[key]

    def write_docker_compose(self):
        self.conf_rw.write_yaml(f"{_nano_nodes_path}/docker-compose.yml",
                                self.compose_dict)

    def get_docker_tag(self, node_name):
        #takes the first non empty docker_tag.
        #First looks for the individual tag
        #then for the general tag
        #last uses teh default nanocurrency/nano-beta:latest tag

        individual_tag = self.get_representative_config(
            "docker_tag", node_name)
        general_tag = self.get_representative_config("docker_tag", None)

        if individual_tag["found"]:
            return individual_tag["value"]
        elif general_tag["found"]:
            return general_tag["value"]
        else:
            return "nanocurrency/nano-beta:latest"

    def compose_add_node(self, node_name):
        #Search for individual docker_tag, then individual executable, then shared docker-tag then shared-executable

        user_id = str(os.getuid())
        docker_tag = self.get_docker_tag(node_name)

        if self.config_dict[
                "tc_enable"]:  #installs iproute2 into the nano_node image
            container = self.compose_add_container(node_name,
                                                   "default_docker_custom")
            container["user"] = user_id
            container["build"]["args"][0] = f'NANO_IMAGE={docker_tag}'
            container["build"]["args"][1] = f'UID={user_id}'
            container["build"]["args"][
                2] = f'TC_ENABLE={str(self.config_dict["tc_enable"]).upper()}'

        elif user_id == "0":  #root
            container = self.compose_add_container(node_name,
                                                   "default_docker_root")
            container["image"] = f"{docker_tag}"

        elif user_id == "1000":
            container = self.compose_add_container(node_name, "default_docker")
            container["image"] = f"{docker_tag}"

            logging.warning(
                "No docker_tag or nano_node_path specified. use [latest] (nanocurrency/nano-test:latest)"
            )

        else:  #non standart user
            #we need to add the current user as user to the nano_node docker image

            container = self.compose_add_container(node_name,
                                                   "default_docker_custom")
            container["user"] = user_id
            #container["image"] = f"{docker_tag}"
            container["build"]["args"][0] = f'NANO_IMAGE={docker_tag}'
            container["build"]["args"][1] = f'UID={user_id}'

    def compose_set_node_ports(self, node_name):
        node_config = self.get_node_config(node_name)
        self.compose_dict["services"][node_name]["ports"] = [
            f'{node_config["host_port_peer"]}:17075',
            f'{node_config["host_port_rpc"]}:17076',
            f'{node_config["host_port_ws"]}:17078'
        ]

    def compose_set_nanomonitor_ports(self, container_name, port_i):
        host_port_monitor = 46000 + port_i
        self.compose_dict["services"][container_name]["ports"] = [
            f'{host_port_monitor}:80'
        ]

    def cp_dockerfile_and_nano_node(self, exec_path, node_name):
        #copy nano_node into working directory for Dockerfile
        dockerfile_path = _dockerfile_path.format(node_name=node_name)
        if exec_path.split(".")[-1] == "deb":
            copy_node = f"cp -p {exec_path} {dockerfile_path}/package.deb"
            copy_dockerfile = f"cp -p {_config_dir}/default_deb_Dockerfile {dockerfile_path}/Dockerfile"
        else:
            copy_node = f"cp -p {exec_path} {dockerfile_path}/nano_node"
            copy_dockerfile = f"cp -p {_config_dir}/default_Dockerfile {dockerfile_path}/Dockerfile"
        if os.path.exists(exec_path):
            os.system(copy_node)
            os.system(copy_dockerfile)
        else:
            logging.error(
                f'No nano_node could be found at [{exec_path}]. This container will fail on start'
            )

        return dockerfile_path

    def compose_add_container(self, node_name, default_container):
        #copies a default container and adds it as a new container
        self.compose_dict["services"][node_name] = copy.deepcopy(
            self.compose_dict["services"][default_container])
        self.compose_dict["services"][node_name]["container_name"] = node_name
        self.compose_dict["services"][node_name]["volumes"][
            0] = self.compose_dict["services"][node_name]["volumes"][
                0].replace("${default_docker}", node_name)
        return self.compose_dict["services"][node_name]

    def get_config_from_path(self, node_name, config_path_key):
        #returns None if no path is found
        config_dict_l = None
        if self.get_representative_config(
                config_path_key,
                node_name)["found"]:  #search by individual path
            config_dict_l = self.conf_rw.read_toml(
                self.get_representative_config(config_path_key,
                                               node_name)["value"])
        elif self.get_representative_config(
                config_path_key, None)["found"]:  #search by shared path
            config_dict_l = self.conf_rw.read_toml(
                self.get_representative_config(config_path_key, None)["value"])
        else:
            pass  #return None
        return config_dict_l

    def get_representative_config(self, node_key, node_name):
        #scan node config and match by name. Return the value of the key found in the config
        #response : {"found" : Bool, "value" = ...}
        if node_name is None and node_key is None:
            return {"found": False}

        if node_name is None:
            #shared config
            if node_key in self.config_dict["representatives"]:
                return {
                    "found": True,
                    "value": self.config_dict["representatives"][node_key]
                }
        else:
            #individual config
            representatives_config = self.value_in_dict_array(
                self.config_dict["representatives"]["nodes"], node_name)
            if representatives_config["found"] == True:
                if node_key in representatives_config["value"]:
                    return {
                        "found": True,
                        "value": representatives_config["value"][node_key]
                    }
        return {"found": False}