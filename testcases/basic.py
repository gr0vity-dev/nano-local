#!./venv_nano_local/bin/python
from os import popen
from math import ceil
from time import time
import unittest
from src.nano_block_ops import BlockGenerator, BlockAsserts, BlockReadWrite
from src.nano_rpc import NanoRpc, NanoTools
from src.parse_nano_local_config import ConfigReadWrite, ConfigParser, Helpers
import copy
from interruptingcow import timeout
import logging
import time
import json
import inspect
from multiprocessing import Process, Queue, Value

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


    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_9_publish_bucket_saturation"), "according to nano_local_config.toml")
    def test_9_publish_bucket_saturation(self):   
        from testcases.BlockPropagation.setup import Init
        ini = Init(9)
        
        ini.setup_ledger(ini.pre_gen_files["ledger_file"], use_nanoticker = not ini.debug)        
        blocks = self.brw.read_blocks_from_disk(ini.pre_gen_files["json_file"])
        mp_procs = []
        mp_q = Queue()
        h = Helpers()     
        
        if ini.debug :
            first_round_blocks = blocks["b"][0][:10]
            first_round_block_hashes = blocks["h"][0][:10]   
            spam_round_blocks = [x[:10] for x in blocks["b"][1:len(blocks["b"])]]  
        else:
            first_round_blocks = blocks["b"][0]
            first_round_block_hashes = blocks["h"][0]  
            spam_round_blocks = [x for x in blocks["b"][1:len(blocks["b"])]]  
        
        spam_block_count = sum([len(b) for b in spam_round_blocks])        

        t1 = time.time()
        #Every spam account broadcasts a recent change block, so priority should be reduced over older blocks      
        #   aio_http gets stuck if mp_ process follows non-mp_ process. Run everything in multiprocessing mode.
        proc_round1_spam = Process(target=self.ba.assert_blocks_published, args=(first_round_blocks,), kwargs={"sync" : True}) 
        proc_round1_confirmed = Process(target=self.ba.assert_blocks_confirmed, args=(first_round_block_hashes,)) #not important for this test

        proc_round1_spam.start()
        proc_round1_confirmed.start()

        proc_round1_spam.join()
        proc_round1_confirmed.join()
        
        first_round_duration = time.time() - t1
              
      
        #Start multiple processes in parallel.
        #1)Start spam with pre_generated blocks. All spam accounts have a recent transaction from blocks published in previous setp
        #2)Broadcast 1 genuine block from different accounts. Monitor confirmation duration for each block and move to next account.
        t2 = time.time()
        mp_spam_running = Value('i', True)
        spam_proc = Process(target=self.ba.assert_list_of_blocks_published, args=(spam_round_blocks,), kwargs={"sync" : False, "is_running" : mp_spam_running})
        legit_proc = Process(target=ini.online_bucket_main, args=(mp_q,mp_spam_running,))
        
        spam_proc.start()
        legit_proc.start()
        
        spam_proc.join()
        spam_duration = time.time() - t2 #measure time when spam has ended
        legit_proc.join() #wait for last confirmation after spam has ended

       
        #Convert result of online_bucket_main() from mp_q to list.
        mp_q.put(None)
        conf_duration = list(iter(mp_q.get, None))       
        test_duration = time.time() - t1

        res = { "confs":len(conf_duration),                
                "spam_s": spam_duration,
                "bps" : spam_block_count / spam_duration,
                "main_cps" : len(conf_duration) / test_duration,
                "min" :min(conf_duration),
                "max" : max(conf_duration),
                "timeouts": len(list(filter(lambda x: x >= 120, conf_duration))) ,  
                "perc_50":h.percentile(conf_duration,50),
                "perc_75":h.percentile(conf_duration,75),
                "perc_90":h.percentile(conf_duration,90),
                "perc_99":h.percentile(conf_duration,99),                  
                "spam_block_count" : spam_block_count,
                "round1_s" : first_round_duration,
                "test_s" : test_duration }    
       
        return res
    
    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_10_publish_bucket_saturation"), "according to nano_local_config.toml")
    def test_10_loop_t9_10x(self): 
        import pandas as pd
        import traceback
        from tabulate import tabulate

        res = []        
        for i in range (0,10) :
            try:            
                res.append(self.test_9_publish_bucket_saturation())             
                print(pd.DataFrame(res))  
            except Exception as e:
                traceback.print_exc()
                pass  

        ConfigReadWrite().write_list("./test0.txt", res)
        df = pd.DataFrame(res)
        
        content = tabulate(df.values.tolist(), list(df.columns), tablefmt="plain", floatfmt=".2f")
        open("./test_10_publish_bucket_saturation.txt", "w").write(content)
      



if __name__ == '__main__':
    unittest.main()