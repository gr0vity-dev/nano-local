#!./venv_nano_local/bin/python
from os import system
from math import ceil, log10
from time import time
from src.nano_rpc import NanoRpc, NanoTools
from src.parse_nano_local_config import ConfigParser, ConfigReadWrite
import copy
from interruptingcow import timeout
import logging
import time
import json
import unittest
import traceback



class BlockGenerator():

    single_change_rep = None

    def __init__(self, broadcast_blocks = False, default_rpc_index = 0) :
        self.default_rpc_index = default_rpc_index
        self.broadcast = broadcast_blocks
        self.single_account_open_counter = 0
        self.nt = NanoTools()
        self.conf = ConfigParser()
        self.nano_rpc_all = self.get_rpc_all()
        self.nano_rpc_default = self.nano_rpc_all[ min(default_rpc_index, len(self.nano_rpc_all) -1) ]

    def get_rpc_all(self):
        return [NanoRpc(x) for x in self.conf.get_rpc_endpoints()]

    def get_nano_rpc_default(self):
        return NanoRpc(self.conf.get_rpc_endpoints()[min(self.default_rpc_index, len(self.nano_rpc_all) -1)])
        #return self.nano_rpc_default

    def get_nano_rpc(self, nano_rpc=None) :
        #return default is no rpc is specified
        if nano_rpc is None : nano_rpc = self.get_nano_rpc_default()
        return nano_rpc

    def blockgen_single_account_opener(self, representative, source_key, destination_seed, send_amount, number_of_accounts, destination_index = 0, nano_rpc=None, accounts_keep_track = False):
        nano_rpc = self.get_nano_rpc(nano_rpc=nano_rpc)
        if accounts_keep_track :
            if self.single_account_open_counter >= number_of_accounts : return []
        self.single_account_open_counter = self.single_account_open_counter + 1
        destination = nano_rpc.generate_account(destination_seed, destination_index)

        send_block = nano_rpc.create_send_block_pkey(source_key,destination["account"],send_amount,broadcast=self.broadcast)
        open_block = nano_rpc.create_open_block(destination["account"],destination["private"],send_amount,representative,send_block["hash"], broadcast=self.broadcast)
        open_block["account_data"]["source_seed"] = destination_seed

        res = [ send_block, open_block ]
        print("accounts opened:  {:>6}".format(self.single_account_open_counter), end='\r')
        return res

    def set_single_change_rep(self, rep=None, nano_rpc=None):
        #returns random rep if rep is not specified
        if rep is not None : self.single_change_rep = rep
        elif rep is None and nano_rpc is not None : self.single_change_rep = nano_rpc.get_account_data(nano_rpc.generate_seed(), 0)["account"]
        else :
            nano_rpc = self.get_nano_rpc()
            self.single_change_rep = nano_rpc.get_account_data(nano_rpc.generate_seed(), 0)["account"]
        return self.single_change_rep

    def blockgen_single_change(self,source_seed=None,source_index=None, source_private_key = None, rep = None, nano_rpc = None) :
        nano_rpc = self.get_nano_rpc(nano_rpc=nano_rpc)
        if rep is None : rep = self.single_change_rep
        if rep is None : rep = nano_rpc.get_account_data(nano_rpc.generate_seed(), 0)["account"]

        if source_private_key is not None :
            return nano_rpc.create_change_block_pkey(source_private_key, rep, broadcast=self.broadcast)
        elif source_seed is not None and source_index is not None :
            return nano_rpc.create_change_block(source_seed, source_index, rep, broadcast=self.broadcast)
        else:
            raise ValueError(f"Either source_private_key({source_private_key})   OR   source_seed({source_seed}) and source_index({source_index}) must not be None")

    def recursive_split(self,seed_prefix, representative, source_private_key, number_of_accounts, splitting_depth, current_depth, final_account_balance_raw):
        seed = f'{seed_prefix}{str(0)*(64 - len(seed_prefix))}'
        blocks_current_depth = self.blockgen_single_account_opener(representative ,
                                                                   source_private_key,
                                                                   seed,
                                                                   int(self.nt.raw_mul((2**(splitting_depth - current_depth +1) -1) , final_account_balance_raw)),
                                                                   number_of_accounts,
                                                                   accounts_keep_track=True)

        blocks_next_depth = self.blockgen_account_splitter(seed_prefix,
                                                           number_of_accounts,
                                                           current_depth=current_depth+1,
                                                           representative=representative,
                                                           source_seed=seed,
                                                           final_account_balance_raw=final_account_balance_raw )
        return blocks_current_depth + blocks_next_depth #blocks_current_depth.extends(blocks_next_depth)

    def blockgen_account_splitter(self, seed_prefix, number_of_accounts, current_depth = 1, representative = None, source_seed = None, source_index = 0, source_private_key = None, final_account_balance_raw = 10 **30 , nano_rpc = None):
        '''create 2 new accounts from 1 account recursively until number_of_accounts is reached.
           each account sends its funds to 2 other accounts and keeps a minimum balance of {final_account_balance_raw}
           return 2 * {number_of_accounts} blocks
           '''
        splitting_depth = ceil(log10(number_of_accounts + 2) / log10(2)) -1
        if current_depth > splitting_depth : return [] #end of recursion is reached
        nano_rpc = self.get_nano_rpc(nano_rpc=nano_rpc)

        if current_depth == 1 :
            self.single_account_open_counter = 0
            if source_seed is None:  #find a seed with enough funding
                for node_conf in self.conf.get_nodes_config():
                    #find one representative that holds enough funds to cover all sends
                    if int(nano_rpc.check_balance(node_conf["account"])["balance_raw"]) > (number_of_accounts * final_account_balance_raw) : #raw
                        source_account_data = node_conf["account_data"]
                        break
            elif source_private_key is not None :
                source_account_data = nano_rpc.key_expand(source_private_key)
            else:
                source_account_data = nano_rpc.generate_account(source_seed, source_index)
            #source balance must be greater than
            unittest.TestCase().assertGreater(int(nano_rpc.check_balance(source_account_data["account"])["balance_raw"]), int(self.nt.raw_mul(number_of_accounts, final_account_balance_raw)))
            representative = nano_rpc.account_info(source_account_data["account"]) #keep the same representative for all opened accounts
        else :
            source_account_data = nano_rpc.generate_account(source_seed, 0)

        seed_prefix_A = f'{seed_prefix}A'  #Seed _A ... _AA / _BA...
        seed_prefix_B = f'{seed_prefix}B'  #Seed _B ... _AB / _BB...
        blocks_A = self.recursive_split(seed_prefix_A, representative, source_account_data["private"], number_of_accounts, splitting_depth, current_depth, final_account_balance_raw)
        blocks_B = self.recursive_split(seed_prefix_B, representative, source_account_data["private"], number_of_accounts, splitting_depth, current_depth, final_account_balance_raw)
        all_blocks =  blocks_A + blocks_B

        if current_depth == 1 :
            self.single_account_open_counter = 0 #reset counter for next call

        return all_blocks

    def get_hashes_from_blocks(self, blocks) :
        if isinstance(blocks, list):
            block_hashes = [ x["hash"] for x in blocks ]
            return block_hashes
        elif isinstance(blocks, dict):
            return blocks.get("hash", "")


class BlockAsserts():
    from multiprocessing import Value

    tc = unittest.TestCase()

    def __init__(self, default_rpc_index = 0) :
        self.conf = ConfigParser()
        self.nano_rpc_all = BlockGenerator().get_rpc_all()
        self.nano_rpc_default = self.nano_rpc_all[ min(default_rpc_index, len(self.nano_rpc_all) -1) ]
    
    def assert_nanoticker_reader(self, ledger_block_count, exit_after_s=180):
        system("docker restart nl_nanoticker")
        try:
            with timeout(exit_after_s, exception=RuntimeError) :
                while True :
                    res =  self.nano_rpc_default.request_get(f'http://{self.conf.get_remote_address()}:42002/json/stats.json')
                    if res["status_code"] == 200 :                    
                        if res["message"] is not None and "blockCountMin" in res["message"] :                        
                            min_block_count = res["message"]["blockCountMin"]                            
                            if min_block_count == ledger_block_count : break
                    time.sleep(1) 
        except RuntimeError as re :
            self.tc.fail(str(re))   
        self.tc.assertEqual(ledger_block_count, min_block_count)


    def assert_list_of_blocks_published(self, list_of_blocks, sync = True, is_running = Value('i', False), stop_event = None) :
       
        for blocks in list_of_blocks :
            if stop_event is not None and stop_event.is_set(): break
            self.assert_blocks_published(blocks,sync=sync)
        is_running.value = False

    
    def assert_blocks_published(self, blocks, sync = True):
        blocks_to_publish_count = len(blocks)
        rpc_block_count_start = self.nano_rpc_default.block_count()
        #print("start block_count" , rpc_block_count_start)
        res = self.nano_rpc_default.publish_blocks(blocks, json_data=True, sync=sync) #we don't care about the result
        #DEBUG PURPOSE; DISABLE  
        #self.assert_expected_block_count(blocks_to_publish_count+int(rpc_block_count_start["count"]))


    def assert_expected_block_count(self, expected_count, exit_after_s = 2) :
        try:
            with timeout(exit_after_s, exception=RuntimeError) :
                while True :
                    rpc_block_count_end = self.nano_rpc_default.block_count()
                    if int(rpc_block_count_end["count"]) == expected_count : break
                    time.sleep(0.2)
        except Exception as e:
            self.tc.fail(str(e))
        self.tc.assertGreaterEqual(int(rpc_block_count_end["count"]), expected_count ) #if other blocks arrive in the meantime


    def assert_single_block_confirmed(self, hash, sleep_on_stall_s =0.1, exit_after_s= 120, exit_on_first_stall = False):
        #Convert hash_string into list of 1 hash and reuse existing method that handles lists
        block_hashes = []
        block_hashes.append(hash)
        return self.assert_blocks_confirmed(block_hashes, sleep_on_stall_s=sleep_on_stall_s, exit_after_s= exit_after_s, exit_on_first_stall=exit_on_first_stall )


    def assert_blocks_confirmed(self, block_hashes, max_stall_duration_s = 6*60, sleep_on_stall_s =5, stall_timeout_max= 30*60, exit_after_s= 60*60, exit_on_first_stall = False, log_to_console = False):

        block_count = len(block_hashes)
        timeout_inc = 0
        try:
            with timeout(exit_after_s, exception=RuntimeError) :
                confirmed_count = 0
                while confirmed_count < block_count:
                    last_confirmed_count = confirmed_count
                    confirmed_hashes = self.nano_rpc_default.block_confirmed_aio(block_hashes, ignore_errors = ["Block not found"],)
                    block_hashes = list(set(block_hashes) - confirmed_hashes)
                    confirmed_count = confirmed_count + len(confirmed_hashes)
                    if confirmed_count != block_count  :
                        if log_to_console : print(f"{confirmed_count}/{block_count} blocks confirmed", end="\r")
                        time.sleep(sleep_on_stall_s)
                        #print(f"{confirmed_count}/{block_count} blocks confirmed....", end="\r")
                    if confirmed_count == last_confirmed_count : # stalling block_count
                        if exit_on_first_stall : return {"total_block_count" : block_count,
                                                        "confirmed_count" : confirmed_count,
                                                        "unconfirmed_count" : block_count - confirmed_count }

                        stall_timeout_max = stall_timeout_max - sleep_on_stall_s
                        stall_timeout_max = timeout_inc + sleep_on_stall_s
                        if timeout_inc >= max_stall_duration_s :
                            raise ValueError(f"No new confirmations for {max_stall_duration_s}s... Fail blocks_confirmed") #break if no new confirmatiosn for 6 minutes (default)
                    else : #reset stall timer
                        timeout_inc = 0
                    if stall_timeout_max <= 0 :
                       raise ValueError(f"Max timeout of {stall_timeout_max} seconds reached")
                print(f"{confirmed_count}/{block_count} blocks confirmed")
        except RuntimeError as re: #when timeout hits
            self.tc.fail(str(re))
        except ValueError as ve:
             self.tc.fail(str(ve))

        self.tc.assertEqual(confirmed_count, block_count)
        return confirmed_count

    def assert_all_blocks_cementing(self, exit_after_s = 30):
        try:
            with timeout(exit_after_s, exception=RuntimeError) :
                while True :
                    equal_count = True
                    for nano_rpc in self.nano_rpc_all :
                        block_count = nano_rpc.block_count()
                        equal_count = equal_count + ( block_count["count"] == block_count["cemented"] )
                    if equal_count : break
                    time.sleep(0.2)
        except RuntimeError as e :
            self.tc.fail(e)

    def assert_all_blocks_cemented(self):
        for nano_rpc in self.nano_rpc_all :
            block_count = nano_rpc.block_count()
            self.tc.assertEqual(block_count["count"], block_count["cemented"])
        return block_count

    def assert_blockgen_succeeded(self, blocks) :
        if isinstance(blocks, list):
            self.tc.assertEqual(len(list(filter(lambda x: x["success"] , blocks))), len(blocks))
        elif isinstance(blocks, dict):
            self.tc.assertTrue(blocks["success"])
        else :
            self.tc.fail("Blocks must be of list or dict type")

class BlockReadWrite():

    ba = BlockAsserts()
    conf_rw = ConfigReadWrite()
    cparse = ConfigParser()

    def write_ledger_to_disk(self, ledger_destinations):
        self.ba.assert_all_blocks_cemented()
        ledger_source = f"./nano_nodes/{self.cparse.get_nodes_name()[0]}/NanoTest/data.ldb"
        command = f"cp -p {ledger_source} {ledger_destinations}"
        system(command)

    def read_blocks_from_disk(self, path , seeds = False, hashes = False, blocks = False ) :
        res = self.conf_rw.read_json(path)
        if seeds : return res["s"]
        if hashes : return res["h"]
        if blocks : return res["b"]
        return res

    def write_blocks_to_disk(self, rpc_block_list, path):
        hash_list = []
        seed_list = []
        block_list = []


        if any(isinstance(i, list) for i in rpc_block_list[:2]) : #nested list :
            for block_list_i in rpc_block_list :
                self.ba.assert_blockgen_succeeded(block_list_i)
                block_list.append(list(map(lambda x: x["block"] , block_list_i)))
                seed_list.append(list(set([x["account_data"]["source_seed"] for x in block_list_i if x["account_data"]["source_seed"] is not None])))
                hash_list.append(list(map(lambda x: x["hash"] , block_list_i)))

        else :
            self.ba.assert_blockgen_succeeded(rpc_block_list)
            hash_list = list(map(lambda x: x["hash"], rpc_block_list))
            seed_list = list(set([x["account_data"]["source_seed"] for x in rpc_block_list if x["account_data"]["source_seed"] is not None])) #remove duplicate seeds with set
            block_list = list(map(lambda x: x["block"], rpc_block_list))

        res = {"h" : hash_list, "s" : seed_list, "b" : block_list}

        self.conf_rw.write_json(path, res)

