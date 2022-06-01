#!./venv_nano_local/bin/python
from math import ceil
from time import time
import unittest
from src.nano_rpc import Api, NanoTools
from src.nano_local_initial_blocks import InitialBlocks
from src.parse_nano_local_config import ConfigReadWrite, ConfigParser
import copy
from interruptingcow import timeout
import logging
import time
import json
import inspect


def is_not_in_config(module,qual_name, function_name) :
        return ConfigParser().skip_testcase('{}.{}.{}'.format( module, qual_name, function_name))

class NetworkChecks(unittest.TestCase):   

    def setUp(self) -> None:
        self.nano_tools = NanoTools()
        self.config_parse = ConfigParser() 
      

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_rpc_online"), "according to nano_local_config.toml")
    def test_rpc_online(self):              

        for node_name in self.config_parse.get_node_names() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            is_online = Api(node_rpc).is_online()

            self.assertTrue(is_online)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_peer_count"), "according to nano_local_config.toml")
    def test_peer_count(self):
        # check if all nodes are all connected to each_other. 
        for node_name in self.config_parse.get_node_names() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            peer_count = len(Api(node_rpc).peers()["peers"])
            self.assertEqual(peer_count, len(self.config_parse.get_node_names()) -1)    

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_block_count"), "according to nano_local_config.toml")
    def test_equal_block_count(self):
        # compare "block_count" for each node to the "block_count" of the first node.
        first_node_block_count = None
        for node_name in self.config_parse.get_node_names() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            block_count = Api(node_rpc).block_count()
            if first_node_block_count is None : first_node_block_count = copy.deepcopy(block_count) 
            self.assertDictEqual(block_count,first_node_block_count) 

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_online_stake_total"), "according to nano_local_config.toml")
    def test_equal_online_stake_total(self):
        # compare "confirmation_quorum" for each node to the "confirmation_quorum" of the first node.
        first_node_online_stake_total = None
        for node_name in self.config_parse.get_node_names() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            online_stake_total = Api(node_rpc).confirmation_quorum()["online_stake_total"]
            if first_node_online_stake_total is None : first_node_online_stake_total = copy.deepcopy(online_stake_total) 
            self.assertEqual(online_stake_total,first_node_online_stake_total)     
    
    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_confirmation_quorum"), "according to nano_local_config.toml")
    def test_equal_confirmation_quorum(self):
        # compare "confirmation_quorum" for each node to the "confirmation_quorum" of the first node. (excludes "peers_stake_total")
        first_node_confirmation_quorum = None
        for node_name in self.config_parse.get_node_names() :
            node_config = self.config_parse.get_node_config(node_name)
            
            confirmation_quorum = Api(node_config["rpc_url"]).confirmation_quorum()            
            confirmation_quorum.pop("peers_stake_total")
            if first_node_confirmation_quorum is None : first_node_confirmation_quorum = copy.deepcopy(confirmation_quorum) 
            self.assertDictEqual(confirmation_quorum,first_node_confirmation_quorum)  
    
    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_peers_stake_total"), "according to nano_local_config.toml")
    def test_equal_peers_stake_total(self):
        # Adds node vote weight to "peers_stake_total" and compares the value to all other nodes
        first_node_response = None
        for node_name in self.config_parse.get_node_names() :
            node_config = self.config_parse.get_node_config(node_name)            
            response = Api(node_config["rpc_url"]).confirmation_quorum()   
            #if node is an online representative, add its own vote weight to peers_stake_total 
            rep_weight = Api(node_config["rpc_url"]).representatives_online(weight=True)
            if node_config["account"] in rep_weight["representatives"] : 
                response["peers_stake_total"] = self.nano_tools.raw_add(response["peers_stake_total"],
                                                                        rep_weight["representatives"][node_config["account"]]["weight"] )
            
            if first_node_response is None : first_node_response = response["peers_stake_total"] 
            self.assertEqual(response["peers_stake_total"],first_node_response)  
    
    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_representatives_online"), "according to nano_local_config.toml")
    def test_equal_representatives_online(self):
        # Compares online representatives among all nodes
        first_node_response = None
        for node_name in self.config_parse.get_node_names() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            response = Api(node_rpc).representatives_online(weight=True)
            if first_node_response is None : first_node_response = copy.deepcopy(response) 
            self.assertDictEqual(response,first_node_response) 

class BlockPropagation(unittest.TestCase):
    def setUp(self) -> None:
        self.nano_rpc = Api("http://localhost:45000")
        self.nano_tools = NanoTools()
        self.conf = InitialBlocks().config 
        self.open_counter = 0
        self.splitting_depth = 9 #splitting_depth =9 creates 1022 accounts (2** (splitting_depth+1)) -2

    def get_accounts() :
        pass

    def open_account(self, representative, send_key, destination_seed, send_amount, account_info = None):
        self.open_counter = self.open_counter + 1
        destination = self.nano_rpc.generate_account(destination_seed, 0)     
        send_block = self.nano_rpc.create_send_block_pkey(send_key,
                                                          destination["account"],
                                                          send_amount * 10**30,
                                                          broadcast=False)       
       
        open_block = self.nano_rpc.create_open_block(destination["account"],
                                                     destination["private"],
                                                     send_amount * 10**30,
                                                     representative,
                                                     send_block["hash"],
                                                     broadcast=False)
        res = [ send_block["req_process"], open_block["req_process"] ]  
        print("accounts opened:  {:>6}".format(self.open_counter), end='\r')     
        return res
    
    def recursive_split(self,seed_prefix, representative, source_account, splitting_depth, current_depth):
        seed = f'{seed_prefix}{str(0)*(64 - len(seed_prefix))}' 
        blocks = self.open_account(representative , source_account["private"], seed, 2**(splitting_depth - current_depth +1) -1)          
        blocks_ab = self.account_splitting(seed_prefix, splitting_depth, current_depth=current_depth+1, representative=representative, source_seed=seed )      
        return blocks + blocks_ab

    def account_splitting(self, seed_prefix, splitting_depth, current_depth = 1, representative = None, source_seed = None, write_to_disk = False, folder = "storage" ):
        #split each account into 2 by sending half of the account funds to 2 other accounts.
        # at the end of teh split, each account will have 1 nano 
             
        if current_depth > splitting_depth : return [] #end of recursion is reached
        
        if current_depth == 1 :            
            lst_expected_length = 2**(splitting_depth +1) -2  
            for node in self.conf["node_account_data"]:
                #find one representative that holds enough funds to cover all sends
                if int(self.nano_rpc.check_balance(node["account"])["balance_raw"]) > (lst_expected_length * 10**30) : #raw
                    source_account = node
                    representative = source_account["account"] #keep the same representative for all opened accounts
                    break
        else :
            source_account = self.nano_rpc.generate_account(source_seed, 0)
            #print("source_seed", source_seed, "source_key", source_account["private"])
        
        seed_prefix_A = f'{seed_prefix}A'  #Seed _A ... _AA / _BA...
        seed_prefix_B = f'{seed_prefix}B'  #Seed _B ... _AB / _BB...

        lst = self.recursive_split(seed_prefix_A, representative, source_account, splitting_depth, current_depth)  + self.recursive_split(seed_prefix_B, representative, source_account, splitting_depth, current_depth)   
                        
        if current_depth == 1 : 
            print("")   
            self.assertEqual(len(lst), 2* lst_expected_length)  
            if write_to_disk :
                ConfigReadWrite().write_list(f"./testcases/{folder}/test_account_splitting_depth_{splitting_depth}.txt", [str(line).replace("'", '"') for line in lst])

        
        return lst

    def publish_blocks(self, file_name):
        
        blocks = ConfigReadWrite().read_file(file_name)
        blocks_to_publish_count = len(blocks)
        rpc_block_count_start = int(self.nano_rpc.block_count()["count"])  
        self.nano_rpc.publish(payload_array=blocks, sync = True) #we don't care about the result   
        rpc_block_count_end = int(self.nano_rpc.block_count()["count"])
        self.assertEqual(rpc_block_count_end - rpc_block_count_start, blocks_to_publish_count )
   
    
    def blocks_confirmed(self, file_name, min_timeout_s = 30, acceptable_tps = None):
        publish_commands = ConfigReadWrite().read_file(file_name) 
        block_count = len(publish_commands)
        sleep_duration_s = 2
        if acceptable_tps is not None :
            min_timeout_s = max(ceil(block_count / acceptable_tps), min_timeout_s)
        try:
            with timeout(min_timeout_s, exception=RuntimeError):
                confirmed_count = 0       
                while confirmed_count < block_count:                 
                    for command in copy.deepcopy(publish_commands):          
                        if self.nano_rpc.block_confirmed(json_block= json.loads(command)["block"]) : 
                            confirmed_count = confirmed_count +1 
                            publish_commands.remove(command)
                        print("confirmed blocks {:<6}".format(confirmed_count) , end='\r')
                    if confirmed_count != block_count  :
                        print(f"{confirmed_count}/{block_count} blocks confirmed.... Waiting for {sleep_duration_s}s")  
                        time.sleep(sleep_duration_s)
            print(f"{confirmed_count}/{block_count} blocks confirmed")   
        except RuntimeError as ex: #when timeout hits
            self.assertFalse(True, f'RuntimeError raised: {str(ex)}')
        print("")
        self.assertEqual(block_count , confirmed_count)               
   
    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_account_splitting_1022_step1"), "according to nano_local_config.toml")
    def test_account_splitting_1022_step1(self):        
        #with a splitting_depth of 9, accountsplitting creates 2+ 4+ 8 +16 + 32 + 64 + 128 + 256 + 512  = 1022 accounts
        print("create send and open blocks")       
        blocks = self.account_splitting('A0',self.splitting_depth, write_to_disk=True)                
        #self.assertEqual(len(blocks), 2*1022 )
    
    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_account_splitting_1022_step2"), "according to nano_local_config.toml")
    def test_account_splitting_1022_step2(self):
        print("publish blocks")
        self.publish_blocks(f"./testcases/storage/test_account_splitting_depth_{self.splitting_depth}.txt")

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_account_splitting_1022_step3"), "according to nano_local_config.toml")
    def test_account_splitting_1022_step3(self) :
        print("test if blocks are confirmed")
        self.blocks_confirmed(f"./testcases/storage/test_account_splitting_depth_{self.splitting_depth}.txt", acceptable_tps = 50)

  

    
   

if __name__ == '__main__':
    unittest.main()

