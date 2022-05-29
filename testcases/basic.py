#!./venv_nano_local/bin/python
import unittest
from src.nano_rpc import Api, NanoTools
from src.nano_local_initial_blocks import InitialBlocks
from src.parse_nano_local_config import ConfigReadWrite
import copy



class NetworkChecks(unittest.TestCase):

    def setUp(self) -> None:
        self.nano_tools = NanoTools()
        self.config_parse = ConfigParser()   

    def test_rpc_online(self):        

        for node_name in self.config_parse.get_node_names() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            is_online = Api(node_rpc).is_online()

            self.assertTrue(is_online)

    def test_peer_count(self):
        # check if all nodes are all connected to each_other. 
        for node_name in self.config_parse.get_node_names() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            peer_count = len(Api(node_rpc).peers()["peers"])
            self.assertEqual(peer_count, len(self.config_parse.get_node_names()) -1)    

    def test_equal_block_count(self):
        # compare "block_count" for each node to the "block_count" of the first node.
        first_node_block_count = None
        for node_name in self.config_parse.get_node_names() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            block_count = Api(node_rpc).block_count()
            if first_node_block_count is None : first_node_block_count = copy.deepcopy(block_count) 
            self.assertDictEqual(block_count,first_node_block_count) 

    def test_equal_online_stake_total(self):
        # compare "confirmation_quorum" for each node to the "confirmation_quorum" of the first node.
        first_node_online_stake_total = None
        for node_name in self.config_parse.get_node_names() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            online_stake_total = Api(node_rpc).confirmation_quorum()["online_stake_total"]
            if first_node_online_stake_total is None : first_node_online_stake_total = copy.deepcopy(online_stake_total) 
            self.assertEqual(online_stake_total,first_node_online_stake_total)     
    
    def test_equal_confirmation_quorum(self):
        # compare "confirmation_quorum" for each node to the "confirmation_quorum" of the first node. (excludes "peers_stake_total")
        first_node_confirmation_quorum = None
        for node_name in self.config_parse.get_node_names() :
            node_config = self.config_parse.get_node_config(node_name)
            
            confirmation_quorum = Api(node_config["rpc_url"]).confirmation_quorum()            
            confirmation_quorum.pop("peers_stake_total")
            if first_node_confirmation_quorum is None : first_node_confirmation_quorum = copy.deepcopy(confirmation_quorum) 
            self.assertDictEqual(confirmation_quorum,first_node_confirmation_quorum)  
    
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

    def open_account(self, representative, send_key, destination_seed, send_amount, account_info = None):

        
        destination = self.nano_rpc.generate_account(destination_seed, 0)
        #print("soiurce_key", send_key , "destination_seed", destination_seed)
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
        return res

    def account_splitting(self, seed_prefix, max_depth, current_depth = 0, representative = None, source_seed = None, write_to_disk = False ):
        # search for an account that has
        # A - AA - AAA...
        #        - AAB...
        #   - AB - ABA...
        #        - ABB...
        
              
        if current_depth > max_depth : return []
        
        if current_depth == 0 : 
            #find account that holds 2**power_of_2 nano and send 1 nano to each account
            lst_expected_length = 2**(max_depth +2) -2  
            for node in self.conf["node_account_data"]:
                if int(self.nano_rpc.check_balance(node["account"])["balance_raw"]) > (lst_expected_length * 10**30) : #raw
                    source_account = node
                    representative = source_account["account"]
                    #print("source_key", source_account["private"])
                    break
        else :
            source_account = self.nano_rpc.generate_account(source_seed, 0)
            #print("source_seed", source_seed, "source_key", source_account["private"])
        
        seed_prefix_A = f'{seed_prefix}A'        
        seed_A = f'{seed_prefix_A}{str(0)*(63 - len(seed_prefix))}' 
        blocks_A = self.open_account(source_account["account"] , source_account["private"], seed_A, max_depth - current_depth)       
        blocks_Aab = self.account_splitting(seed_prefix_A, max_depth, current_depth=current_depth+1, representative=representative, source_seed=seed_A )      
        
        seed_prefix_B = f'{seed_prefix}B' 
        seed_B = f'{seed_prefix_B}{str(0)*(63 - len(seed_prefix))}' 
        blocks_B = self.open_account(source_account["account"] , source_account["private"], seed_B, max_depth - current_depth)
        blocks_Bab = self.account_splitting(seed_prefix_B, max_depth, current_depth=current_depth+1, representative=representative, source_seed=seed_B)    
        
        lst = blocks_A + blocks_B + blocks_Aab + blocks_Bab

                 
        if current_depth == 0 :    
            self.assertEqual(len(lst), 2* lst_expected_length)  
            if write_to_disk :
                ConfigReadWrite().write_list(f"./nano_nodes/publish_{2* lst_expected_length}_blocks.txt", [str(line).replace("'", '"') for line in lst])


        return lst
        
    def publish_blocks(self, file_name):
        lines = ConfigReadWrite().read_file(file_name)
        for publish_command in lines:          
            response = self.nano_rpc.publish(publish_command)
            self.assertFalse("error" in response)
            
    
    def test_account_splitting_1022(self):
        #accountsplitting creates 2+ 4+ 8 +16 + ... + 512 = 1022 = (2**10 -2) = 1024 -2 accounts
        pow_2 = 10       
        blocks = self.account_splitting('A0',pow_2-2, write_to_disk=True)                
        #self.assertEqual(len(blocks), 2*1022 )
    
    def test_publish_blocks(self):
        self.publish_blocks("./nano_nodes/publish_2044_blocks.txt")


if __name__ == '__main__':
    unittest.main()


