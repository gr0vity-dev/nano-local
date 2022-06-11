#!./venv_nano_local/bin/python
import unittest
from src.nano_block_ops import BlockGenerator, BlockAsserts, BlockReadWrite
from src.nano_rpc import NanoRpc, NanoTools
from src.parse_nano_local_config import ConfigParser
import copy


def is_not_in_config(module,qual_name, function_name) :
    return ConfigParser().skip_testcase('{}.{}.{}'.format( "basic", qual_name, function_name))

class NetworkChecks(unittest.TestCase):

    def setUp(self) -> None:
        self.nano_tools = NanoTools()
        self.config_parse = ConfigParser()


    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_rpc_online"), "according to nano_local_config.toml")
    def test_rpc_online(self):

        for node_name in self.config_parse.get_nodes_name() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            is_online = NanoRpc(node_rpc).is_online()

            self.assertTrue(is_online)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_peer_count"), "according to nano_local_config.toml")
    def test_peer_count(self):
        # check if all nodes are all connected to each_other.
        for node_name in self.config_parse.get_nodes_name() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            peer_count = len(NanoRpc(node_rpc).peers()["peers"])
            self.assertEqual(peer_count, len(self.config_parse.get_nodes_name()) -1)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_all_blocks_confirmed"), "according to nano_local_config.toml")
    def test_all_blocks_confirmed(self):
        # check if all nodes are all connected to each_other.
        for node_name in self.config_parse.get_nodes_name() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            block_count = NanoRpc(node_rpc).block_count()
            self.assertEqual(block_count["count"], block_count["cemented"])

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_block_count"), "according to nano_local_config.toml")
    def test_equal_block_count(self):
        # compare "block_count" for each node to the "block_count" of the first node.
        first_node_block_count = None
        for node_conf in self.config_parse.get_nodes_config():
            b_count = NanoRpc(node_conf["rpc_url"]).block_count()
            if first_node_block_count is None : first_node_block_count = copy.deepcopy(b_count)
            self.assertDictEqual(b_count,first_node_block_count)


    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_online_stake_total"), "according to nano_local_config.toml")
    def test_equal_online_stake_total(self):
        # compare "confirmation_quorum" for each node to the "confirmation_quorum" of the first node.
        first_node_online_stake_total = None
        for node_name in self.config_parse.get_nodes_name() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            online_stake_total = NanoRpc(node_rpc).confirmation_quorum()["online_stake_total"]
            if first_node_online_stake_total is None : first_node_online_stake_total = copy.deepcopy(online_stake_total)
            self.assertEqual(online_stake_total,first_node_online_stake_total)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_confirmation_quorum"), "according to nano_local_config.toml")
    def test_equal_confirmation_quorum(self):
        # compare "confirmation_quorum" for each node to the "confirmation_quorum" of the first node. (excludes "peers_stake_total")
        first_node_confirmation_quorum = None
        for node_name in self.config_parse.get_nodes_name() :
            node_config = self.config_parse.get_node_config(node_name)

            confirmation_quorum = NanoRpc(node_config["rpc_url"]).confirmation_quorum()
            confirmation_quorum.pop("peers_stake_total")
            if first_node_confirmation_quorum is None : first_node_confirmation_quorum = copy.deepcopy(confirmation_quorum)
            self.assertDictEqual(confirmation_quorum,first_node_confirmation_quorum)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_peers_stake_total"), "according to nano_local_config.toml")
    def test_equal_peers_stake_total(self):
        # Adds node vote weight to "peers_stake_total" and compares the value to all other nodes
        first_node_response = None
        for node_name in self.config_parse.get_nodes_name() :
            node_config = self.config_parse.get_node_config(node_name)
            response = NanoRpc(node_config["rpc_url"]).confirmation_quorum()
            #if node is an online representative, add its own vote weight to peers_stake_total
            rep_weight = NanoRpc(node_config["rpc_url"]).representatives_online(weight=True)
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
        for node_name in self.config_parse.get_nodes_name() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            response = NanoRpc(node_rpc).representatives_online(weight=True)
            if first_node_response is None : first_node_response = copy.deepcopy(response)
            self.assertDictEqual(response,first_node_response)

class BlockPropagation(unittest.TestCase):

    def setUp(self) -> None:
        self.bg = BlockGenerator(broadcast_blocks=True, default_rpc_index=1)
        self.ba = BlockAsserts(default_rpc_index=1)
        self.brw = BlockReadWrite()
        self.conf = ConfigParser()
        self.nano_rpc = self.bg.get_nano_rpc_default()


    def split_account(self, accounts, max_conf_stall_duration_s = 6*60):

        block_count_start = int(self.ba.assert_all_blocks_cemented()["count"])
        source_private_key= self.conf.get_max_balance_key()
        #starts with 1 account and doubles the number of accounts with each increasing splitting_depth. first account needs enough funding
        blocks = self.bg.blockgen_account_splitter("CA531", accounts, source_private_key=source_private_key, final_account_balance_raw=10)
        block_count_end = int(self.nano_rpc.block_count()["count"])

        self.assertEqual(block_count_start + 2*accounts, block_count_end)
        self.ba.assert_blocks_confirmed( self.bg.get_hashes_from_blocks(blocks), max_stall_duration_s=max_conf_stall_duration_s)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_1_account_split_10"), "according to nano_local_config.toml")
    def test_1_account_split_10(self):
        self.split_account(10, max_conf_stall_duration_s=15)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_1_account_split_1000"), "according to nano_local_config.toml")
    def test_1_account_split_1000(self):
        self.split_account(1000, max_conf_stall_duration_s=15)


if __name__ == '__main__':
    unittest.main()