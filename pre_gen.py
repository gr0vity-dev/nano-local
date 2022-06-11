#!./venv_nano_local/bin/python
from os import system, listdir
from os.path import exists
from math import ceil, log10
from time import time
from src.nano_rpc import NanoRpc, NanoTools
from src.nano_local_initial_blocks import InitialBlocks
from src.parse_nano_local_config import ConfigParser, Helpers
from src.nano_block_ops import BlockAsserts, BlockGenerator, BlockReadWrite
import copy
from interruptingcow import timeout
import logging
import time
import json
import inspect
from multiprocessing import Process, Queue, Value
import unittest
import pandas as pd
from tabulate import tabulate
import traceback



class PreGenLedger():

    def __init__(self, pre_gen_folder_name, pregen = True):
        #self.nano_rpc_all = NanoRpc("undefined") #used to hint at availabe functions whiel coding
        self.nano_tools = NanoTools()
        self.conf = ConfigParser()
        self.bg = BlockGenerator(default_rpc_index = 1, broadcast_blocks=False)
        self.ba = BlockAsserts(default_rpc_index = 1)
        self.brw = BlockReadWrite()
        self.nano_rpc_all = self.bg.get_rpc_all() #access all avilable rpcs at nano_rpc_all.node_name
        self.set_class_params(pre_gen_folder_name)
        self.validate(pregen)

    def set_class_params(self,pre_gen_folder_name ):
        self.pre_gen_path = f"./pregen_ledgers/{pre_gen_folder_name}"
        self.pre_gen_file_names = {"account_split" : {"json_file" : f"{self.pre_gen_path}/1_accounts_split.json" , "ledger_file" : f"{self.pre_gen_path}/1_data.ldb"},
                                   "bucket_funding" : {"json_file" : f"{self.pre_gen_path}/2_bucket_funding.json" , "ledger_file" : f"{self.pre_gen_path}/2_data.ldb"},
                                   "bucket_rounds" : {"json_file" : f"{self.pre_gen_path}/3_change_blocks_rounds.json" , "ledger_file" : f"{self.pre_gen_path}/3_data.ldb"} , }

        self.pre_gen_bucket_seed_prefix = "FACE" # {prefix}000.000{bucket_id} (example bucket_17_seed : FACE000000000000000000000000000000000000000000000000000000000017)
        self.pre_gen_account_min_end_balance = 100 * 10**30
        self.pre_gen_max_bucket = 6 #used to prefill buckets from 0 to 105 (at 105 you'll need at least pre_gen_account_min_end_balance=2**106 (~81.113) )
        self.pre_gen_start_index = 0 #skip # seeds and pre_generation at index # (should be 0 except for testing purposes)
        self.pre_gen_accounts = 10 #(must be smaller than (2**(pre_gen_splitting_depth+1) -2))
        self.pre_gen_bucket_saturation_main_index = 6
        self.pre_gen_bucket_saturation_indexes = [1,2,5]
        self.pre_gen_bucket_saturation_rounds = 10 # (pre_gen_bucket_saturation_rounds * pre_gen_accounts will be crated per index.  Example: 10*5000 * 4 = 200'000 )


    def validate(self, pregen):
        system(f"mkdir -p {self.pre_gen_path}")
        tc = unittest.TestCase()
        tc.assertGreater(self.pre_gen_account_min_end_balance, 2 ** (self.pre_gen_max_bucket+1))
        tc.assertGreater(self.pre_gen_max_bucket+1, self.pre_gen_bucket_saturation_main_index)
        for bucket_index in self.pre_gen_bucket_saturation_indexes :
            tc.assertGreater(self.pre_gen_max_bucket,bucket_index)
        if pregen : #folder must be empty when pregenerating new blocks
            tc.assertFalse(listdir(self.pre_gen_path))
        else : #folder must contain files from self.pre_gen_file_names
            tc.assertGreater(len(listdir(self.pre_gen_path)), 0)

    def get_pre_gen_files(self):
        response = copy.deepcopy(self.pre_gen_file_names)
        for key, files in self.pre_gen_file_names.items() :
            if not exists(files["json_file"]) : response[key].pop("json_file")

            if not exists(files["ledger_file"]) : response[key].pop("ledger_file")
            if response[key] == {} : response.pop(key)
        return response

    def get_prefixed_suffixed_seed(self, prefix, suffix) :
        return f'{prefix}{str(0)*(64 - len(str(suffix)) - len(str(prefix)))}{str(suffix)}'

    def get_bucket_seed(self, bucket_id) :
        bucket_prefix = "FACE"
        if bucket_id >= 0 and bucket_id <= 128 :
            return self.get_prefixed_suffixed_seed(bucket_prefix, bucket_id)






#PRE_GENERATE_BLOCKS
    def pre_gen_account_split(self, source_seed = None, source_private_key = None):
        #tc.assertFalse(source_seed == source_private_key == None) #if seed and key is none, account_splitting will use an account from config with enough available balance
        self.ba.assert_all_blocks_cemented()
        #starts with 1 account and doubles the number of accounts with each increasing splitting_depth. first account needs enough funding
        res = self.bg.blockgen_account_splitter("C0C0", self.pre_gen_accounts, source_seed= source_seed, final_account_balance_raw=self.pre_gen_account_min_end_balance)
        self.brw.write_blocks_to_disk(res, self.pre_gen_file_names["account_split"]["json_file"])

    def fund_bucket(self, bucket, source_seed, destination_index):
        destination_seed = self.get_bucket_seed(bucket)
        source = self.nano_rpc_all[1].generate_account(source_seed, 0)
        destination = self.nano_rpc_all[1].generate_account(destination_seed, destination_index)
        return self.bg.blockgen_single_account_opener(destination["account"], source["private"],destination_seed,  2**bucket, None, destination_index=destination_index, nano_rpc=self.nano_rpc_all[1] )

    def pre_gen_bucket_funding(self):
        #create 1 send block from each account of test_pregenerate_depth_12 to FADE0000000000....1 , ...2 , ...3

        self.ba.assert_all_blocks_cemented()
        seeds = self.brw.read_blocks_from_disk(self.pre_gen_file_names["account_split"]["json_file"], seeds=True)

        block_list_of_list = []
        for bucket_index in range(0,self.pre_gen_max_bucket+1) : # bucket 0 ==1 raw bucket 105 =~ 40.565 Nano
            start_index = self.pre_gen_start_index
            break_count = self.pre_gen_accounts

            destination_index = 0
            bucket_blocks = []
            for source_seed in seeds : #publish send and open blocks separately
                #create 5000 send blocks to each bucket FACE00000...1 ; FACE00000...2 ; ... ; FACE0000...125 from index 0 to 5000
                if destination_index < start_index :
                    #chose start_account to send from (for testing purposes, start_index default = 0)
                    destination_index = destination_index + 1
                    continue
                if destination_index > break_count : break
                res = self.fund_bucket(bucket_index, source_seed, destination_index )
                bucket_blocks.extend(res)
                destination_index = destination_index + 1
            block_list_of_list.append(bucket_blocks)
        self.brw.write_blocks_to_disk(block_list_of_list, self.pre_gen_file_names["bucket_funding"]["json_file"])

    def pre_gen_bucket_rounds(self):
        self.ba.assert_all_blocks_cemented()
        block_list_of_list = []
        block_list = []

        for round in range(0,self.pre_gen_bucket_saturation_rounds):
            random_rep = self.bg.set_single_change_rep() #generate a random account and set is as new rep
            if block_list != [] : block_list_of_list.append(block_list)
            block_list = []
            for bucket_index in self.pre_gen_bucket_saturation_indexes :
                bucket_seed = self.get_bucket_seed(bucket_index)
                for account_index in range(self.pre_gen_start_index, self.pre_gen_accounts):
                    block_list.append(self.bg.blockgen_single_change(bucket_seed, account_index))
        if block_list != [] : block_list_of_list.append(block_list)

        self.brw.write_blocks_to_disk(block_list_of_list,self.pre_gen_file_names["bucket_rounds"]["json_file"] )


#PUBLISH PRE_GENERATED_BLOCKS
    def publish_account_split(self) :
        blocks = self.brw.read_blocks_from_disk(self.pre_gen_file_names["account_split"]["json_file"], blocks = True)
        self.ba.assert_blocks_published(blocks, sync=True)

    def publish_bucket_funding(self) :
        block_list_of_list = self.brw.read_blocks_from_disk(self.pre_gen_file_names["bucket_funding"]["json_file"])
        #hashes = block_list_of_list["h"]
        blocks = block_list_of_list["b"]
        for i in range(0, len(blocks)):
            self.ba.assert_blocks_published(blocks[i], sync=False)
            #self.ba.assert_blocks_confirmed(hashes[i])

    def publish_bucket_rounds(self) :
        block_list_of_list = self.brw.read_blocks_from_disk(self.pre_gen_file_names["bucket_rounds"]["json_file"], blocks = True)
        for blocks in block_list_of_list :
            self.ba.assert_blocks_published(blocks, sync=False)

#ASSERT PRE_GENERATED_BLOCKS CONFIRMED
    def blocks_confirmed_account_split(self):
        block_hashes = self.brw.read_blocks_from_disk(self.pre_gen_file_names["account_split"]["json_file"], hashes = True)
        self.ba.assert_blocks_confirmed(block_hashes)

    def blocks_confirmed_bucket_funding(self):
        list_of_block_hashes = self.brw.read_blocks_from_disk(self.pre_gen_file_names["bucket_funding"]["json_file"], hashes = True)
        for block_hashes in list_of_block_hashes :
            self.ba.assert_blocks_confirmed(block_hashes)

    def blocks_confirmed_bucket_rounds(self):
        list_of_block_hashes = self.brw.read_blocks_from_disk(self.pre_gen_file_names["bucket_rounds"]["json_file"], hashes = True)
        for block_hashes in list_of_block_hashes :
            self.ba.assert_blocks_confirmed(block_hashes)

    def write_ledger_account_split(self):
        self.brw.write_ledger_to_disk(self.pre_gen_file_names["account_split"]["ledger_file"])

    def write_ledger_bucket_funding(self):
        self.brw.write_ledger_to_disk(self.pre_gen_file_names["bucket_funding"]["ledger_file"])

    def write_ledger_bucket_rounds(self):
        self.brw.write_ledger_to_disk(self.pre_gen_file_names["bucket_rounds"]["ledger_file"])


def main():
    pre_gen = PreGenLedger("Block_Propagation")

    pre_gen.pre_gen_account_split() #,source_seed=pre_gen.get_prefixed_suffixed_seed("ACDC", "27"))
    pre_gen.publish_account_split()
    pre_gen.blocks_confirmed_account_split()
    pre_gen.write_ledger_account_split()

    pre_gen.pre_gen_bucket_funding()
    pre_gen.publish_bucket_funding()
    pre_gen.blocks_confirmed_bucket_funding()
    pre_gen.write_ledger_bucket_funding()

    pre_gen.pre_gen_bucket_rounds()
    pre_gen.publish_bucket_rounds()
    pre_gen.blocks_confirmed_bucket_rounds()
    pre_gen.write_ledger_bucket_rounds()




if __name__ == "__main__":
    main()




    # # BOOTSTRAPPING TEST BY DELETING DATA.lDB FOR 1 NODE and monitor that node.
    # # REPEAT FOR PR and for NON PR node.

    # # pre_gen.setup_ledger(pre_gen.pre_gen_file_names["bucket_funding"]["ledger_file"])
    # # pre_gen.publish_bucket_rounds()
    # # pre_gen.blocks_confirmed_bucket_rounds()
    # # #main()