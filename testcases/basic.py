#!./venv_nano_local/bin/python
import unittest
from src.nano_rpc import Api
from src.parse_nano_local_config import ConfigParser
from src.parse_nano_local_config import ConfigReadWrite
from src.nano_local_initial_blocks import InitialBlocks
import copy



class NetworkChecks(unittest.TestCase):

    def setUp(self) -> None:
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
        # compare "confirmation_quorum" for each node to the "confirmation_quorum" of the first node.
        first_node_confirmation_quorum = None
        for node_name in self.config_parse.get_node_names() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            confirmation_quorum = Api(node_rpc).confirmation_quorum()
            if first_node_confirmation_quorum is None : first_node_confirmation_quorum = copy.deepcopy(confirmation_quorum) 
            self.assertDictEqual(confirmation_quorum,first_node_confirmation_quorum)  

   

if __name__ == '__main__':
    unittest.main()
