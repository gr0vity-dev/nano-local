#!./venv_nano_local/bin/python
import unittest
from src.nano_block_ops import BlockGenerator, BlockAsserts, BlockReadWrite
from src.parse_nano_local_config import ConfigReadWrite, ConfigParser, Helpers
import time
import json
from multiprocessing import Process, Queue, Value
import traceback



def is_not_in_config(module,qual_name, function_name) :
    return ConfigParser().skip_testcase('{}.{}.{}'.format( module, qual_name, function_name))

class ReplayLedgers(unittest.TestCase):
    from testcases.setup.spam import Init

    def setUp(self) -> None:
        self.bg = BlockGenerator(broadcast_blocks=True, default_rpc_index=1)
        self.ba = BlockAsserts(default_rpc_index=1)
        self.brw = BlockReadWrite()
        self.conf = ConfigParser()
        self.nano_rpc = self.bg.get_nano_rpc_default()

    # @unittest.skipIf(is_not_in_config(__module__, __qualname__,
    #    "test_N1_1_publish_10_change_blocks"), "according to nano_local_config.toml")
    # def test_N1_1_publish_10_change_blocks(self):
    #     ini = self.Init(1)
    #     ini.setup_ledger(ini.pre_gen_files["ledger_file"], use_nanoticker = False)
    #     blocks = self.brw.read_blocks_from_disk(ini.pre_gen_files["json_file"])

    #     first_round_blocks = blocks["b"][0][:10]
    #     first_round_block_hashes = blocks["h"][0][:10]
    #     self.ba.assert_blocks_published(first_round_blocks)
    #     self.ba.assert_blocks_confirmed(first_round_block_hashes, sleep_on_stall_s=0.5, log_to_console=True)


    # @unittest.skipIf(is_not_in_config(__module__, __qualname__,
    #    "test_N1_2_publish_bucket_saturation"), "according to nano_local_config.toml")
    def Nspam_bucket_saturation(self):
        ini = self.Init(2)

        ini.setup_ledger(ini.pre_gen_files["ledger_file"], use_nanoticker = not ini.debug)
        blocks = self.brw.read_blocks_from_disk(ini.pre_gen_files["json_file"])
        block_count_start = self.bg.get_nano_rpc_default().block_count()
        mp_procs = []
        mp_q = Queue()
        h = Helpers()

        first_round_blocks = blocks["b"][0]
        #first_round_block_hashes = blocks["h"][0]
        spam_round_blocks = [x for x in blocks["b"][1:len(blocks["b"])]]
        spam_block_count = sum([len(b) for b in spam_round_blocks])

        t1 = time.time()
        #Every spam account broadcasts a recent change block, so priority should be reduced over older blocks
        #   aio_http gets stuck if mp_ process follows non-mp_ process. Run everything in multiprocessing mode.
        proc_round1_spam = Process(target=self.ba.assert_blocks_published, args=(first_round_blocks,), kwargs={"sync" : True})
        #proc_round1_confirmed = Process(target=self.ba.assert_blocks_confirmed, args=(first_round_block_hashes,)) #not important for this test

        proc_round1_spam.start()
        #proc_round1_confirmed.start()

        proc_round1_spam.join()
        #proc_round1_confirmed.join()

        first_round_duration = time.time() - t1


        #Start multiple processes in parallel.
        #1)Start spam with pre_generated blocks. All spam accounts have a recent transaction from blocks published in previous setp
        #2)Broadcast 1 genuine block from different accounts. Monitor confirmation duration for each block and move to next account.
        t2 = time.time()
        mp_spam_running = Value('i', True)
        spam_proc = Process(target=self.ba.assert_list_of_blocks_published, args=(spam_round_blocks,), kwargs={"sync" : False, "is_running" : mp_spam_running})
        legit_proc = Process(target=ini.online_bucket_main, args=(mp_q, ini.single_tx_timeout ,mp_spam_running,))

        spam_proc.start()
        legit_proc.start()

        spam_proc.join()
        spam_duration = time.time() - t2 #measure time when spam has ended
        legit_proc.join() #wait for last confirmation after spam has ended
        block_count_end = self.bg.get_nano_rpc_default().block_count()

        #Convert result of online_bucket_main() from mp_q to list.
        mp_q.put(None)
        conf_lst = list(iter(mp_q.get, None))
        confirmations = [x["conf_duration"] for x in conf_lst if x["timeout"] == False]
        print(confirmations[:25])
        timeouts = [x for x in conf_lst if x["timeout"]]

        test_duration = time.time() - t1

        res = { "confs":len(confirmations),
                "timeouts": len(timeouts) ,
                "timeout_%": (len(timeouts) / (len(timeouts) + len(confirmations))) *100,               
                "bps" : spam_block_count / spam_duration,
                "main_cps" : len(confirmations) / test_duration,
                "min" : min(confirmations),
                "max" : max(confirmations),   
                "perc_50":h.percentile(confirmations,50),
                "perc_75":h.percentile(confirmations,75),
                "perc_90":h.percentile(confirmations,90),
                "perc_99":h.percentile(confirmations,99),
                "spam_block_count" : spam_block_count,
                "timeout_s" : ini.single_tx_timeout,
                "spam_s": spam_duration,
                "round1_s" : first_round_duration,
                "test_s" : test_duration,
                "blocks_start" : block_count_start["count"] if block_count_start is not None else -1,
                "blocks_end" : block_count_end["count"] if block_count_end is not None else -1,
                "blocks_cemented" : block_count_end["cemented"] if block_count_end is not None else -1}

        print(json.dumps(res, indent=4))
        return res

    @unittest.skipIf(is_not_in_config(__module__, __qualname__,
       "test_Nspam_loop_x10"), "according to nano_local_config.toml")
    def test_Nspam_loop_x10(self):      
        ini = self.Init(2)

        res = []
        for i in range (0,10) :
            try:
                res.append(self.Nspam_bucket_saturation())
                print(self.flatjson_to_table(res))
            except Exception as e:
                traceback.print_exc()
                pass
        self.create_report(res)
       
    
    def flatjson_to_table(self, content):
        import pandas as pd        
        from tabulate import tabulate        

        df = pd.DataFrame(content)
        return tabulate(df.values.tolist(), list(df.columns), tablefmt="plain", floatfmt=".3f")

    
    
    def create_report(self, content) :       
        from datetime import datetime
        from os import system
        import sys
        caller = sys._getframe(1).f_code.co_name
        system(f"mkdir -p ./nano_nodes/testruns")
        system(f"mkdir -p ./nano_nodes/testruns/{caller}")

        version = [] ; version.append(self.nano_rpc.version())
      
        content = self.flatjson_to_table(version) + "\n\n" + self.flatjson_to_table(content)

        day_of_year = datetime.now().strftime('%j')
        exec_time = datetime.now().strftime("%H%M%S")
        file_path_dir = f"nano_nodes/testruns/{caller}"
        file_path = f'{file_path_dir}/{day_of_year}_{exec_time}.txt'
        

        f = open(file_path, "w")
        f.write(content)
        f.close()
        print(f"Stats available at {file_path}" )


if __name__ == '__main__':
    unittest.main()