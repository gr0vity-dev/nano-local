#!./venv_nano_local/bin/python
import unittest
from src.nano_rpc import Api
from src.parse_nano_local_config import ConfigParser
from src.parse_nano_local_config import ConfigReadWrite
from src.nano_local_initial_blocks import InitialBlocks

class NetworkChecks(unittest.TestCase):

    def setUp(self) -> None:
        self.config = ConfigParser()   

    def test_rpc_online(self):        

        for node_name in self.config.get_node_names() :
            node_rpc = self.config.get_node_config(node_name)["rpc_url"]
            is_online = Api(node_rpc).is_online()

            self.assertTrue(is_online)

    def test_peer_count(self):
        # check if all nodes are all connected to each_other. 
        for node_name in self.config.get_node_names() :
            node_rpc = self.config.get_node_config(node_name)["rpc_url"]
            peer_count = len(Api(node_rpc).peers()["peers"])
            self.assertEqual(peer_count, len(self.config.get_node_names()) -1)        
  

if __name__ == '__main__':
    unittest.main()