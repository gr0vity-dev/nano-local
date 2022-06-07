#!./venv_nano_local/bin/python
from math import ceil
from time import time
import unittest
from src.nano_rpc import Api, NanoTools
from src.nano_local_initial_blocks import InitialBlocks
from src.parse_nano_local_config import ConfigReadWrite, ConfigParser, Helpers
import copy
from interruptingcow import timeout
import logging
import time
import json
import inspect
from multiprocessing import Process, Queue, Value
def is_not_in_config(module,qual_name, function_name) :
        return ConfigParser().skip_testcase('{}.{}.{}'.format( module, qual_name, function_name))

class NetworkChecks(unittest.TestCase):

    def setUp(self) -> None:
        self.nano_tools = NanoTools()
        self.config_parse = ConfigParser()


    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_rpc_online"), "according to nano_local_config.toml")
    def test_rpc_online(self):

        for node_name in self.config_parse.get_nodes_name() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            is_online = Api(node_rpc).is_online()

            self.assertTrue(is_online)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_peer_count"), "according to nano_local_config.toml")
    def test_peer_count(self):
        # check if all nodes are all connected to each_other.
        for node_name in self.config_parse.get_nodes_name() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            peer_count = len(Api(node_rpc).peers()["peers"])
            self.assertEqual(peer_count, len(self.config_parse.get_nodes_name()) -1)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_block_count"), "according to nano_local_config.toml")
    def test_equal_block_count(self):
        # compare "block_count" for each node to the "block_count" of the first node.
        first_node_block_count = None
        for node_conf in self.config_parse.get_nodes_config():               
            b_count = Api(node_conf.rpc_url).block_count()          
            if first_node_block_count is None : first_node_block_count = copy.deepcopy(b_count)
            self.assertDictEqual(b_count,first_node_block_count)
       

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_online_stake_total"), "according to nano_local_config.toml")
    def test_equal_online_stake_total(self):
        # compare "confirmation_quorum" for each node to the "confirmation_quorum" of the first node.
        first_node_online_stake_total = None
        for node_name in self.config_parse.get_nodes_name() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            online_stake_total = Api(node_rpc).confirmation_quorum()["online_stake_total"]
            if first_node_online_stake_total is None : first_node_online_stake_total = copy.deepcopy(online_stake_total)
            self.assertEqual(online_stake_total,first_node_online_stake_total)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
        "test_equal_confirmation_quorum"), "according to nano_local_config.toml")
    def test_equal_confirmation_quorum(self):
        # compare "confirmation_quorum" for each node to the "confirmation_quorum" of the first node. (excludes "peers_stake_total")
        first_node_confirmation_quorum = None
        for node_name in self.config_parse.get_nodes_name() :
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
        for node_name in self.config_parse.get_nodes_name() :
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
        for node_name in self.config_parse.get_nodes_name() :
            node_rpc = self.config_parse.get_node_config(node_name)["rpc_url"]
            response = Api(node_rpc).representatives_online(weight=True)
            if first_node_response is None : first_node_response = copy.deepcopy(response)
            self.assertDictEqual(response,first_node_response)

class BlockPropagation(unittest.TestCase):

    def setUp(self) -> None:       
        
        self.nano_tools = NanoTools()
        self.conf = InitialBlocks().config
        self.nano_rpc = {}
        self.set_rpcs()     
        self.open_counter = 0
        self.set_class_params()  

    def set_rpcs(self) :
        conf = ConfigParser()        
        for node_name in conf.get_nodes_name() :
            node_conf = conf.get_node_config(node_name)
            self.nano_rpc[node_conf["name"]] = Api(node_conf["rpc_url"])

    def set_class_params(self):
        self.online_splitting_depth = 9
        self.pre_gen_bucket_seed_prefix = "FACE" # {prefix}000.000{bucket_id} (example bucket_17_seed : FACE000000000000000000000000000000000000000000000000000000000017)
        self.pre_gen_splitting_depth = 12
        self.pre_gen_account_end_balance = 100 * 10**30
        self.pre_gen_max_bucket = 105 #used to prefill buckets from 0 to 105 (at 105 you'll need at least pre_gen_account_end_balance=2**106 (~81.113) )
        self.pre_gen_start_index = 0 #skip # seeds and pre_generation at index # (should be 0 except for testing purposes)
        self.pre_gen_accounts = 5000 #(must be smaller than (2**(pre_gen_splitting_depth+1) -2))
        self.pre_gen_bucket_saturation_main_index = 102
        self.pre_gen_bucket_saturation_indexes = [1,2,3,4]
        self.pre_gen_bucket_saturation_rounds = 10 # (pre_gen_bucket_saturation_rounds * pre_gen_accounts will be crated per index.  Example: 10*5000 * 4 = 200'000 )

    def open_account(self, representative, send_key, destination_seed, send_amount, final_account_balance_raw):
        self.open_counter = self.open_counter + 1
        destination = self.nano_rpc["nl_genesis"].generate_account(destination_seed, 0)
        send_block = self.nano_rpc["nl_genesis"].create_send_block_pkey(send_key,
                                                          destination["account"],
                                                          send_amount * final_account_balance_raw ,
                                                          broadcast=False)

        open_block = self.nano_rpc["nl_genesis"].create_open_block(destination["account"],
                                                     destination["private"],
                                                     send_amount * final_account_balance_raw,
                                                     representative,
                                                     send_block["hash"],
                                                     broadcast=False)
        open_block["req_process"]["seed"] = destination_seed
        res = [ send_block["req_process"], open_block["req_process"] ]
        print("accounts opened:  {:>6}".format(self.open_counter), end='\r')
        return res

    def get_bucket_seed(self, bucket_id) :
        bucket_prefix = "FACE"
        if bucket_id >= 0 and bucket_id <= 128 :
            return f'{bucket_prefix}{str(0)*(64 - len(str(bucket_id)) - len(bucket_prefix))}{str(bucket_id)}'

    def fund_bucket(self, bucket, source_seed, destination_index):
        destination_seed = self.get_bucket_seed(bucket)
        source = self.nano_rpc["nl_genesis"].generate_account(source_seed, 0)
        destination = self.nano_rpc["nl_genesis"].generate_account(destination_seed, destination_index)

        #print(send_seed, source["account"], destination["account"] )
        send_block = self.nano_rpc["nl_genesis"].create_send_block_pkey(source["private"],
                                                          destination["account"],
                                                          2**bucket ,
                                                          broadcast=False,
                                                          in_memory=True)

        open_block = self.nano_rpc["nl_genesis"].create_open_block(destination["account"],
                                                     destination["private"],
                                                     2**bucket,
                                                     destination["account"],
                                                     send_block["hash"],
                                                     broadcast=False)
        open_block["req_process"]["seed"] = destination_seed
        res = {"publish_send" : send_block["req_process"], "publish_open" : open_block["req_process"] }

        return res


    def recursive_split(self,seed_prefix, representative, source_account, splitting_depth, current_depth, final_account_balance_raw):
        seed = f'{seed_prefix}{str(0)*(64 - len(seed_prefix))}'
        blocks = self.open_account(representative , source_account["private"], seed, (2**(splitting_depth - current_depth +1) -1) , final_account_balance_raw)
        blocks_ab = self.account_splitting(seed_prefix, splitting_depth, current_depth=current_depth+1, representative=representative, source_seed=seed, final_account_balance_raw=final_account_balance_raw )
        return blocks + blocks_ab

    def account_splitting(self, seed_prefix, splitting_depth, current_depth = 1, representative = None, source_seed = None, write_to_disk = False, folder = "storage", final_account_balance_raw = 10 **30 ):
        #split each account into 2 by sending half of the account funds to 2 other accounts.
        # at the end of teh split, each account will have 1 nano

        if current_depth > splitting_depth : return [] #end of recursion is reached


        if current_depth == 1 :
            lst_expected_length = 2**(splitting_depth +1) -2
            for node in self.conf["node_account_data"]:
                #find one representative that holds enough funds to cover all sends
                if int(self.nano_rpc["nl_genesis"].check_balance(node["account"])["balance_raw"]) > (lst_expected_length * final_account_balance_raw) : #raw
                    source_account = node
                    representative = source_account["account"] #keep the same representative for all opened accounts
                    break
        else :
            source_account = self.nano_rpc["nl_genesis"].generate_account(source_seed, 0)
            #print("source_seed", source_seed, "source_key", source_account["private"])

        seed_prefix_A = f'{seed_prefix}A'  #Seed _A ... _AA / _BA...
        seed_prefix_B = f'{seed_prefix}B'  #Seed _B ... _AB / _BB...
        publish_commands_branch_A = self.recursive_split(seed_prefix_A, representative, source_account, splitting_depth, current_depth, final_account_balance_raw)
        publish_commands_branch_B = self.recursive_split(seed_prefix_B, representative, source_account, splitting_depth, current_depth, final_account_balance_raw)
        all_publish_commands =  publish_commands_branch_A + publish_commands_branch_B

        if current_depth == 1 :
            print("")
            self.assertEqual(len(all_publish_commands), 2* lst_expected_length)
            if write_to_disk :
                ConfigReadWrite().write_list(f"./testcases/{folder}/test_account_splitting_depth_{splitting_depth}.txt", [str(line).replace("'", '"') for line in all_publish_commands])

        return all_publish_commands

    def publish_blocks(self, publish_commands, json_data = False, sync = True, is_running = Value('i', False)):

        blocks_to_publish_count = len(publish_commands)
        rpc_block_count_start = int(self.nano_rpc["nl_genesis"].block_count()["count"])
        print(rpc_block_count_start)
        is_running.value = True
        self.nano_rpc["nl_genesis"].publish(payload_array=publish_commands, sync = sync, json_data=json_data) #we don't care about the result
        rpc_block_count_end = int(self.nano_rpc["nl_genesis"].block_count()["count"])
        print(rpc_block_count_end)
        is_running.value = False
        self.assertGreaterEqual(rpc_block_count_end - rpc_block_count_start, blocks_to_publish_count ) #if other blocks arrive in the meantime


    def blocks_confirmed(self, file_name = None, min_timeout_s = 30, acceptable_tps = None, sleep_duration_s = 2, publish_commands = None, percentage = 100):
        self.assertLessEqual(percentage, 100)
        self.assertGreaterEqual(percentage, 0)
        no_new_confirmations_timeout_s = 30

        if publish_commands is None :
            if file_name is not None :publish_commands = ConfigReadWrite().read_file(file_name)
            else : raise Exception("file_name and publish_commands must not both be None" )

        # block_hashes = list(map(lambda x: x.replace("\n", ""), ConfigReadWrite().read_file("./testcases/hashes.txt")))
        blocks = list(map(lambda x: x["block"], publish_commands))
        block_hashes = list(map(lambda x: x["hash"], self.nano_rpc["nl_pr1"].block_hash_aio(blocks)  ))
        block_count = len(block_hashes)

        if acceptable_tps is not None :
            min_timeout_s = max(ceil(block_count / acceptable_tps), min_timeout_s)

        try:
            timeout_inc = 0
            confirmed_count = 0
            while confirmed_count < (percentage / 100) * block_count:
                last_confirmed_count = confirmed_count
                confirmed_hashes = self.nano_rpc["nl_pr1"].block_confirmed_aio(block_hashes)
                block_hashes = list(set(block_hashes) - confirmed_hashes)
                confirmed_count = confirmed_count + len(confirmed_hashes)
                if confirmed_count != block_count  :
                    print(f"{confirmed_count}/{block_count} blocks confirmed....", end="\r")
                if confirmed_count == last_confirmed_count :
                    time.sleep(sleep_duration_s)
                    timeout_inc = timeout_inc + sleep_duration_s
                    if timeout_inc >= no_new_confirmations_timeout_s :
                        raise ValueError(f"No new confirmations for {no_new_confirmations_timeout_s}s... Fail blocks_confirmed") #break if no new confirmatiosn for 30 seconds
                else : #reset break timer
                    timeout_inc = 0

            print(f"{confirmed_count}/{block_count} blocks confirmed")
        except Exception as ex: #when timeout hits
            print(str(ex))
            self.fail(str(ex))
        print("")
        if percentage == 100 :
            self.assertEqual(confirmed_count, block_count)
        else :
            self.assertGreaterEqual(confirmed_count, (percentage / 100) * block_count)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_1_params_integrity"), "according to nano_local_config.toml")
    def test_1_params_integrity(self):
        self.assertGreater((2**(self.pre_gen_splitting_depth+1) -2), self.pre_gen_accounts)
        self.assertGreater((2**(self.pre_gen_splitting_depth+1) -2), self.pre_gen_accounts + self.pre_gen_start_index )
        self.assertGreater(self.pre_gen_account_end_balance, 2 ** (self.pre_gen_max_bucket+1))
        self.assertGreater(self.pre_gen_max_bucket, self.pre_gen_bucket_saturation_main_index)
        for bucket_index in self.pre_gen_bucket_saturation_indexes :
            self.assertGreater(self.pre_gen_max_bucket,bucket_index)


    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_account_splitting_1022_step1"), "according to nano_local_config.toml")
    def test_account_splitting_1022_step1(self):
        #with a splitting_depth of 9, accountsplitting creates 2+ 4+ 8 +16 + 32 + 64 + 128 + 256 + 512  = 1022 accounts
        print("create send and open blocks")
        all_publish_commands = self.account_splitting('A0',self.online_splitting_depth, write_to_disk=True)
        self.assertEqual(len(all_publish_commands), 2*1022 )

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_account_splitting_1022_step2"), "according to nano_local_config.toml")
    def test_account_splitting_1022_step2(self):
        print("publish blocks")
        blocks = ConfigReadWrite().read_file(f"./testcases/storage/test_account_splitting_depth_{self.online_splitting_depth}.txt")
        self.publish_blocks(blocks)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_account_splitting_1022_step3"), "according to nano_local_config.toml")
    def test_account_splitting_1022_step3(self) :
        print("test if blocks are confirmed")
        self.blocks_confirmed(file_name = f"./testcases/storage/test_account_splitting_depth_{self.online_splitting_depth}.txt", acceptable_tps = 50)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_4_pregenerate_depth_12"), "according to nano_local_config.toml")
    def test_4_pregenerate_depth_12(self):
        #with a splitting_depth of 9, accountsplitting creates 2+ 4+ 8 +16 + 32 + 64 + 128 + 256 + 512  = 1022 accounts
        print("create send and open blocks")
        splitting_depth = self.pre_gen_splitting_depth
        all_publish_commands = self.account_splitting('A0',splitting_depth, write_to_disk=True, final_account_balance_raw=self.pre_gen_account_end_balance, folder="pregenerated_blocks")
        self.assertEqual(len(all_publish_commands), 2* (2**(splitting_depth+1) -2) )

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_5_publish_depth_12"), "according to nano_local_config.toml")
    def test_5_publish_depth_12(self):
        splitting_depth = self.pre_gen_splitting_depth
        blocks = ConfigReadWrite().read_file(f"./testcases/pregenerated_blocks/test_account_splitting_depth_{splitting_depth}.txt")
        self.publish_blocks(blocks)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_6_distribute_to_buckets"), "according to nano_local_config.toml")
    def test_6_distribute_to_buckets(self):
        #create 1 send block from each account of test_pregenerate_depth_12 to FADE0000000000....1 , ...2 , ...3
        splitting_depth = self.pre_gen_splitting_depth
        publish_commands = ConfigReadWrite().read_file(f"./testcases/pregenerated_blocks/test_account_splitting_depth_{splitting_depth}.txt")
        seeds = []
        for command in publish_commands :
            try: seeds.append(json.loads(command)["seed"])
            except : pass

        data = {"buckets" : {}}
        for bucket_index in range(0,105+1) : # bucket 0 ==1 raw bucket 105 =~ 40.565 Nano
            start_index = self.pre_gen_start_index
            break_count = self.pre_gen_accounts

            destination_index = 0
            publish_commands_send = []
            publish_commands_open = []
            for source_seed in seeds : #publish send and open blocks separately
                #create 5000 send blocks to each bucket FACE00000...1 ; FACE00000...2 ; ... ; FACE0000...125 from index 0 to 5000
                if destination_index < start_index :
                    #chose start_account to send from (for testing purposes, start_index default = 0)
                    destination_index = destination_index + 1
                    continue
                if destination_index > break_count : break
                res = self.fund_bucket(bucket_index, source_seed, destination_index )
                publish_commands_send.append(res["publish_send"])
                publish_commands_open.append(res["publish_open"])
                destination_index = destination_index + 1
            data["buckets"][bucket_index] = {"send_commands" : publish_commands_send , "open_commands" : publish_commands_open}
        ConfigReadWrite().write_json(f"./testcases/pregenerated_blocks/start_{start_index}_{bucket_index}x{break_count-start_index}x2.json", data)
            #ConfigReadWrite().write_list(f"./testcases/pregenerated_blocks/open_bucket_{bucket_id}.txt", [str(line).replace("'", '"') for line in publish_commands_open])

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_7_publish_buckets"), "according to nano_local_config.toml")
    def test_7_publish_buckets(self):
        data = ConfigReadWrite().read_json("./testcases/pregenerated_blocks/start_0_105x5000x2.json")
        for bucket_id, value in data["buckets"].items() :
            self.publish_blocks(value["send_commands"], json_data=True, sync=False)
            self.publish_blocks(value["open_commands"], json_data=True, sync=False)


    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_8_pre_gen_bucket_saturation"), "according to nano_local_config.toml")
    def test_8_pre_gen_bucket_saturation(self):
        data = {"buckets" : {}} # {"buckets" : {"bucket_0" : {"round_0" : [publish_commands]},
                                #               "bucket_0" : {"round_1" : [publish_commands]},
                                #               "bucket_1" : {"round_0" : [publish_commands]}, ...}

        for bucket_index in self.pre_gen_bucket_saturation_indexes :
            bucket_seed = self.get_bucket_seed(bucket_index)
            data["buckets"][bucket_index] = {}
            for repeat_counter in range(0, self.pre_gen_bucket_saturation_rounds) :
                data["buckets"][bucket_index][repeat_counter] = []

                random_rep = self.nano_rpc["nl_genesis"].get_account_data(self.nano_rpc["nl_genesis"].generate_seed(), 0)["account"] #generate a random account and set is as new rep
                for account_index in range(self.pre_gen_start_index, self.pre_gen_accounts):
                    data["buckets"][bucket_index][repeat_counter].append(self.nano_rpc["nl_genesis"].create_change_block(bucket_seed, account_index, random_rep, broadcast=False)["req_process"])

        ConfigReadWrite().write_json(f"./testcases/pregenerated_blocks/bucket_saturation_{self.pre_gen_start_index}_{len(self.pre_gen_bucket_saturation_indexes) * (self.pre_gen_accounts-self.pre_gen_start_index) * self.pre_gen_bucket_saturation_rounds}_blocks.json", data)

    def publish_bucket_saturation(self, data):
        #Fetch and publish pre-generated blocks for bucket saturation. (10rounds of 5000blocks for bucket 1,2,3 and 4)
        for bucket_id, rounds in data["buckets"].items() :
            for round, publish_commands in rounds.items() :
                self.publish_blocks(publish_commands, json_data=True, sync=False)
        return True

    def get_publish_commands_from_bucket_saturation(self,data, json_data = False, take_rounds = []) :
        #returns a string object (like reading from flatfile)
        response = []
        for bucket_id, rounds in data["buckets"].items() :
            for round, publish_commands in rounds.items() :
                if len(take_rounds) > 0 :
                    if round not in take_rounds : continue
                for command in publish_commands :
                    if json_data :
                        response.append(command)
                    else:
                        response.append((str(command).replace("'", '"')))
        return response

    def online_bucket_main(self, queue, spam_running):
        #create online change blocks for 1 bucket and measure confirmation_times
        timeout_per_conf = 120
        main_bucket_seed = self.get_bucket_seed(self.pre_gen_bucket_saturation_main_index)
        random_rep = self.nano_rpc["nl_pr1"].get_account_data(self.nano_rpc["nl_pr1"].generate_seed(), 0)["account"] #generate a random account and set is as new rep

        for i in range(0,self.pre_gen_accounts) :
            if spam_running.value == False : return #publish while spam blocks are being published
            change_response = self.nano_rpc["nl_pr1"].create_change_block(main_bucket_seed, i,random_rep,broadcast=True)
           # print(change_response["hash"])
            t1 = time.time()

            try:
                with timeout(timeout_per_conf, exception=RuntimeError):
                    while (not self.nano_rpc["nl_pr1"].block_confirmed(block_hash = change_response["hash"])):
                        time.sleep(0.2)
            except RuntimeError:
                print (f"no confirmation after {timeout_per_conf} seconds")

            queue.put(time.time() -t1)

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_9_publish_bucket_saturation"), "according to nano_local_config.toml")
    def test_9_publish_bucket_saturation(self):       
        path = "./testcases/pregenerated_blocks/bucket_saturation_0_200000_blocks.json"
        data = ConfigReadWrite().read_json(path)
        q = Queue()

        #Every account broadcasts a recent change block.
        first_round_commands = self.get_publish_commands_from_bucket_saturation(data, json_data = True, take_rounds=["0"])
        self.publish_blocks(first_round_commands, sync=False, json_data = True)
        self.blocks_confirmed(publish_commands = first_round_commands, percentage = 90) #move on if 90% of blocks are confirmed

        #When Every spam account has a recent confirmation, broadcast the remaning spam.
        #At the same tiem broadcast 1 transaction per account with no recent activity. LRU priorisation_test
        spam_publish_commands = self.get_publish_commands_from_bucket_saturation(data, json_data = True, take_rounds=[str(x) for x in range(1, self.pre_gen_bucket_saturation_rounds) ])
                
        
        spam_running = Value('i', True)
        t1 = time.time()
        p1 = Process(target=self.publish_blocks, args=(spam_publish_commands,), kwargs={"sync" : False, "json_data" : True, "is_running" : spam_running})
        p2 = Process(target=self.online_bucket_main, args=(q,spam_running,))
        #p3 = Process(target=self.blocks_confirmed, kwargs= {"publish_commands"  : publish_commands}) # no need to wait for spam confirmation
       
        p1.start()
        p2.start()
        #p3.start()

        p1.join()
        p2.join()
        #p3.join()

        q.put(None)
        conf_duration = list(iter(q.get, None))


        h = Helpers()
        duration = time.time() - t1
        print({ "saturation_duration_s" : duration,
                "saturation_blocks_per_second" : len(spam_publish_commands) / duration,
                "main_bucket_confirmation_count" : len(conf_duration),
                "main_bucket_confirmations_per_second" : len(conf_duration) / duration,
                "main_bucket_min_duration" : min(conf_duration),
                "main_bucket_max_duration" : max(conf_duration),
                "main_bucket_percentiles" : {"50" : h.percentile(conf_duration,50),
                                             "75" : h.percentile(conf_duration,75),
                                             "90" : h.percentile(conf_duration,90),
                                             "99" : h.percentile(conf_duration,99)}
               })



if __name__ == '__main__':
    unittest.main()