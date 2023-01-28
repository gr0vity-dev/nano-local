#!./venv_nano_local/bin/python

import time
import unittest
from itertools import islice
from math import ceil, floor

from nanolocal.common.nl_rpc import NanoRpc
from nanolocal.common.nl_parse_config import ConfigParser, ConfigReadWrite
from nanolocal.common.nl_nanolib import NanoLibTools, raw_high_precision_multiply

_CONFP = ConfigParser()


class BlockGenerator():

    single_change_rep = None

    def __init__(self,
                 rpc_url,
                 broadcast_blocks=False,
                 rpc_user=None,
                 rpc_password=None,
                 log_to_console=False):

        rpc_url = _CONFP.get_nodes_rpc()[0] if rpc_url is None else rpc_url

        self.broadcast = broadcast_blocks
        self.log_to_console = log_to_console
        self.single_account_open_counter = 0
        self.nano_lib = NanoLibTools()
        self.nano_rpc_default = NanoRpc(rpc_url,
                                        username=rpc_user,
                                        password=rpc_password)

    def get_nano_rpc_default(self):
        return self.nano_rpc_default

    def blockgen_single_account_opener(
            self,
            representative=None,
            source_key=None,  #
            source_seed=None,
            source_index=None,
            destination_key=None,  #
            destination_seed=None,
            destination_index=None,
            send_amount=1,
            number_of_accounts=1000,
            nano_rpc=None,
            accounts_keep_track=False,
            increment_index=False):
        nano_rpc = self.get_nano_rpc_default()
        if accounts_keep_track:
            if self.single_account_open_counter >= number_of_accounts:
                return []
            if increment_index:
                destination_index = self.single_account_open_counter
        self.single_account_open_counter = self.single_account_open_counter + 1

        destination = self.nano_lib.nanolib_account_data(
            private_key=destination_key,
            seed=destination_seed,
            index=destination_index)
        source = self.nano_lib.nanolib_account_data(private_key=source_key,
                                                    seed=source_seed,
                                                    index=source_index)

        send_block = nano_rpc.create_send_block_pkey(source["private"],
                                                     destination["account"],
                                                     send_amount,
                                                     broadcast=self.broadcast)

        open_block = nano_rpc.create_open_block(destination["account"],
                                                destination["private"],
                                                send_amount,
                                                representative,
                                                send_block["hash"],
                                                broadcast=self.broadcast)
        open_block["account_data"]["source_seed"] = destination_seed
        open_block["account_data"]["source_index"] = destination_index

        res = [send_block, open_block]
        if self.log_to_console:
            print("accounts opened:  {:>6}".format(
                self.single_account_open_counter),
                  end='\r')
        return res

    def set_single_change_rep(self, rep=None, nano_rpc: NanoRpc = None):
        #returns random rep if rep is not specified
        if rep is not None: self.single_change_rep = rep
        elif rep is None and nano_rpc is not None:
            self.single_change_rep = nano_rpc.get_account_data(
                nano_rpc.generate_seed(), 0)["account"]
        else:
            nano_rpc = self.get_nano_rpc_default()
            self.single_change_rep = nano_rpc.get_account_data(
                nano_rpc.generate_seed(), 0)["account"]
        return self.single_change_rep

    def blockgen_single_change(self,
                               source_seed=None,
                               source_index=None,
                               source_private_key=None,
                               rep=None,
                               nano_rpc=None):
        nano_rpc = self.get_nano_rpc_default()
        if rep is None: rep = self.single_change_rep
        if rep is None:
            rep = nano_rpc.get_account_data(nano_rpc.generate_seed(),
                                            0)["account"]

        if source_private_key is not None:
            return nano_rpc.create_change_block_pkey(source_private_key,
                                                     rep,
                                                     broadcast=self.broadcast)
        elif source_seed is not None and source_index is not None:
            return nano_rpc.create_change_block(source_seed,
                                                source_index,
                                                rep,
                                                broadcast=self.broadcast)
        else:
            raise ValueError(
                f"Either source_private_key({source_private_key})   OR   source_seed({source_seed}) and source_index({source_index}) must not be None"
            )

    def recursive_split(self, source_account_data, destination_seed,
                        representative, number_of_accounts, splitting_depth,
                        current_depth, final_account_balance_raw, split_count):

        blocks_current_depth = self.blockgen_single_account_opener(
            representative=representative,
            source_key=source_account_data["private"],
            destination_seed=destination_seed,
            #destination_index=source_dest_account_data["index"] + 1,
            accounts_keep_track=True,
            increment_index=True,
            number_of_accounts=number_of_accounts,
            send_amount=int(
                raw_high_precision_multiply(
                    (split_count**(splitting_depth - current_depth + 1) -
                     split_count) + 1, final_account_balance_raw)))

        if len(blocks_current_depth) == 0:
            return blocks_current_depth

        blocks_next_depth = self.blockgen_account_splitter(
            number_of_accounts=number_of_accounts,
            destination_seed=destination_seed,
            current_depth=current_depth + 1,
            representative=representative,
            source_private_key=blocks_current_depth[1]["account_data"]
            ["private"],
            final_account_balance_raw=final_account_balance_raw,
            split_count=split_count)
        return blocks_current_depth + blocks_next_depth  #blocks_current_depth.extends(blocks_next_depth)

    def get_spliting_depth(self, number_of_accounts, split_count):
        sum_l = 0
        for exponent in range(1, 128):
            sum_l = sum_l + (split_count**exponent)
            if sum_l >= number_of_accounts: break
        return exponent

    def get_accounts_for_depth(self, split_count, splitting_depth):
        accounts = 0
        for i in range(1, splitting_depth + 1):
            accounts = accounts + (split_count**i)
        return accounts

    def blockgen_account_splitter(self,
                                  source_private_key=None,
                                  source_seed=None,
                                  source_index=0,
                                  destination_seed=None,
                                  number_of_accounts=1000,
                                  current_depth=1,
                                  split_count=2,
                                  representative=None,
                                  final_account_balance_raw=10**30,
                                  nano_rpc=None):
        '''create {split_count} new accounts from 1 account recursively until {number_of_accounts} is reached.
           each account sends its funds to {split_count}  other accounts and keeps a minimum balance of {final_account_balance_raw}
           returns 2 * {number_of_accounts} blocks
           '''

        splitting_depth = self.get_spliting_depth(number_of_accounts,
                                                  split_count)

        if current_depth > splitting_depth:
            return []  #end of recursion is reached
        nano_rpc = self.get_nano_rpc_default()

        source_account_data = self.nano_lib.nanolib_account_data(
            private_key=source_private_key,
            seed=source_seed,
            index=source_index)
        if current_depth == 1:
            max_accounts_for_depth = self.get_accounts_for_depth(
                split_count, splitting_depth)
            print(
                f"Creating {number_of_accounts} of {max_accounts_for_depth} possible accounts for current splitting_depth : {splitting_depth} and split_count {split_count}"
            )
            self.single_account_open_counter = 0  #reset variable when multiple tests run successively
            unittest.TestCase().assertGreater(
                int(
                    nano_rpc.check_balance(
                        source_account_data["account"])["balance_raw"]),
                int(
                    raw_high_precision_multiply(number_of_accounts,
                                                final_account_balance_raw)))
            if representative is None:  #keep the same representative for all blocks
                representative = nano_rpc.account_info(
                    source_account_data["account"]
                )["representative"]  #keep the same representative for all opened accounts

        all_blocks = []
        for _ in range(0, split_count):
            all_blocks.extend(
                self.recursive_split(source_account_data, destination_seed,
                                     representative, number_of_accounts,
                                     splitting_depth, current_depth,
                                     final_account_balance_raw, split_count))

        if current_depth == 1:
            self.single_account_open_counter = 0  #reset counter for next call
        return all_blocks

    def get_hashes_from_blocks(self, blocks):
        if isinstance(blocks, list):
            block_hashes = [x["hash"] for x in blocks]
            return block_hashes
        elif isinstance(blocks, dict):
            return blocks.get("hash", "")

    def make_deep_forks(self,
                        source_seed,
                        source_index,
                        dest_seed,
                        amount_raw,
                        peer_count,
                        forks_per_peer=1,
                        max_depth=5,
                        current_depth=0):
        fork_blocks = {"gap": [], "forks": []}
        nano_rpc = self.get_nano_rpc_default()
        send_block = nano_rpc.create_block(
            "send",
            source_seed=source_seed,
            source_index=source_index,
            destination_account=nano_rpc.get_account_data(
                source_seed, source_index)["account"],
            amount_raw=amount_raw,
            read_in_memory=False,
            add_in_memory=True)

        fork_blocks["gap"].append(nano_rpc.get_block_result(send_block, False))

        fork_blocks["forks"] = self.recursive_fork_depth(
            source_seed,
            source_index,
            dest_seed,
            amount_raw,
            peer_count,
            forks_per_peer=forks_per_peer,
            max_depth=max_depth,
            current_depth=current_depth)

        return fork_blocks

    def recursive_fork_depth(self,
                             source_seed,
                             source_index,
                             dest_seed,
                             amount_raw,
                             peer_count,
                             forks_per_peer=1,
                             max_depth=5,
                             current_depth=0):
        res = []
        if current_depth >= max_depth: return res

        nano_rpc = self.get_nano_rpc_default()
        next_depth = current_depth + 1
        current_dest_start_index = (forks_per_peer * peer_count *
                                    next_depth) + next_depth
        previous_dest_start_index = (forks_per_peer * peer_count *
                                     current_depth) + current_depth

        #current_dest_start_index = (100 ** next_depth)
        #previous_dest_start_index = 100 ** current_depth

        for i in range(0, forks_per_peer * peer_count):
            dest_index = current_dest_start_index + i
            dest_account = nano_rpc.get_account_data(dest_seed,
                                                     dest_index)["account"]
            send_block = nano_rpc.create_block(
                "send",
                source_seed=source_seed,
                #source_index=source_index if current_depth == 0 else 100 ** current_depth,
                source_index=source_index
                if current_depth == 0 else previous_dest_start_index,
                destination_account=dest_account,
                amount_raw=amount_raw,
                read_in_memory=True,
                add_in_memory=False)

            receive_block = nano_rpc.create_block(
                "receive",
                source_seed=dest_seed,
                source_index=dest_index,
                destination_account=dest_account,
                representative=dest_account,
                amount_raw=amount_raw,
                link=send_block["hash"],
                read_in_memory=False,
                add_in_memory=True,
            )
            res.append(nano_rpc.get_block_result(send_block, False))
            res.append(nano_rpc.get_block_result(receive_block, False))

            next_res = self.recursive_fork_depth(dest_seed,
                                                 dest_index,
                                                 dest_seed,
                                                 amount_raw,
                                                 peer_count,
                                                 max_depth=max_depth,
                                                 current_depth=next_depth)
            res.extend(next_res)
        # print(
        #     ">>>>DEBUG", "Current_depth : {:>2}  results {:>6}".format(
        #         current_depth, len(res)))
        return res


class BlockAsserts():
    from multiprocessing import Value

    tc = unittest.TestCase()

    def __init__(self, rpc_url=None):
        rpc_url = _CONFP.get_nodes_rpc()[0] if rpc_url is None else rpc_url
        self.nano_rpc_default = NanoRpc(rpc_url)
        self.nano_rpc_all = self.get_rpc_all()

    def get_rpc_all(self):
        return [NanoRpc(x) for x in _CONFP.get_nodes_rpc()]

    def get_rpc_custom(self, rpc_urls):
        if rpc_urls is None: return self.get_rpc_all()
        return [NanoRpc(x) for x in rpc_urls]

    def assert_list_of_blocks_published(self,
                                        list_of_blocks,
                                        sync=True,
                                        is_running=Value('i', False),
                                        tps=450):
        for blocks in list_of_blocks:
            self.assert_blocks_published(blocks, sync=sync, tps=tps)
        is_running.value = False

    def assert_blocks_published(self, blocks, sync=True, tps=450):
        blocks_to_publish_count = len(blocks)
        rpc_block_count_start = int(
            self.nano_rpc_default.block_count()["count"])

        start_time = time.time()
        interval = 1

        for i in range(0, ceil(blocks_to_publish_count / tps)):
            blocks_subset = list(islice(blocks, i * tps, i * tps + tps))
            self.nano_rpc_default.publish_blocks(
                blocks_subset, json_data=True,
                sync=sync)  #we don't care about the result
            sleep_duration = max(
                0, start_time + (i + 1) * interval - time.time() +
                ((len(blocks_subset) - tps) / tps))
            time.sleep(sleep_duration)

        self.assert_expected_block_count(blocks_to_publish_count +
                                         rpc_block_count_start)

    def assert_publish_commands(self,
                                publish_commands,
                                sync=True,
                                bps=450,
                                assert_block_count=True):
        blocks_to_publish_count = 0  #len(publish_commands)
        rpc_block_count_start = int(
            self.nano_rpc_default.block_count()["count"])

        start_time = time.time()
        interval = 1

        for i, command in enumerate(publish_commands):
            blocks_to_publish_count = blocks_to_publish_count + len(command)
            #publish_commands_subset = list(islice(publish_commands, i * tps, i * tps + tps))
            #print("DEBUG", len(publish_commands_subset))
            self.nano_rpc_default.send_publish_commands(command, sync=sync)

            sleep_duration = max(
                0, start_time + (i + 1) * interval - time.time() +
                ((len(command) - bps) / bps))
            time.sleep(sleep_duration)

        if assert_block_count:
            self.assert_expected_block_count(blocks_to_publish_count +
                                             rpc_block_count_start)

    def assert_expected_block_count(self, expected_count, exit_after_s=5):
        start_time = time.time()
        #with timeout(exit_after_s, exception=RuntimeError) :
        while True:
            if time.time() - start_time > exit_after_s: break
            rpc_block_count_end = int(
                self.nano_rpc_default.block_count()["count"])
            if rpc_block_count_end >= expected_count: break
            time.sleep(0.2)
        self.tc.assertGreaterEqual(
            rpc_block_count_end,
            expected_count)  #if other blocks arrive in the meantime

    def assert_increasing_block_count(self, expected_count, exit_after_s=5):
        try:
            stall_time = time.time()
            #with timeout(exit_after_s, exception=RuntimeError) :
            prev_block_count = self.nano_rpc_default.block_count()["count"]
            while True:
                if time.time() - stall_time > exit_after_s: break
                rpc_block_count_end = int(
                    self.nano_rpc_default.block_count()["count"])
                if rpc_block_count_end > prev_block_count:  #reset stall_time on increased block_count
                    stall_time = time.time()
                if rpc_block_count_end >= expected_count: break
                time.sleep(0.2)
        except Exception as e:
            print("DEBUG assert_expected_block_count exception", str(e))
        self.tc.assertGreaterEqual(
            rpc_block_count_end,
            expected_count)  #if other blocks arrive in the meantime

    def assert_single_block_confirmed(self,
                                      hash,
                                      sleep_on_stall_s=0.1,
                                      exit_after_s=120,
                                      exit_on_first_stall=False):
        #Convert hash_string into list of 1 hash and reuse existing method that handles lists
        block_hashes = []
        block_hashes.append(hash)
        return self.assert_blocks_confirmed(
            block_hashes,
            sleep_on_stall_s=sleep_on_stall_s,
            exit_after_s=exit_after_s,
            exit_on_first_stall=exit_on_first_stall)

    def assert_blocks_confirmed(self,
                                block_hashes,
                                max_stall_duration_s=6 * 60,
                                sleep_on_stall_s=5,
                                stall_timeout_max=30 * 60,
                                exit_after_s=60 * 60,
                                exit_on_first_stall=False,
                                log_to_console=False):
        start_time = time.time()
        block_count = len(block_hashes)
        print(">>>DEBUG assert_blocks_confirmed:", block_hashes[0],
              block_count)

        timeout_inc = 0
        try:
            #with timeout(exit_after_s, exception=RuntimeError) :
            confirmed_count = 0
            while confirmed_count < block_count:
                if time.time() - start_time > exit_after_s: break
                last_confirmed_count = confirmed_count
                confirmed_hashes = self.nano_rpc_default.block_confirmed_aio(
                    block_hashes,
                    ignore_errors=["Block not found"],
                )
                block_hashes = list(set(block_hashes) - confirmed_hashes)
                confirmed_count = confirmed_count + len(confirmed_hashes)
                if confirmed_count != block_count:
                    if log_to_console:
                        print(
                            f"{confirmed_count}/{block_count} blocks confirmed",
                            end="\r")
                    time.sleep(sleep_on_stall_s)
                if confirmed_count == last_confirmed_count:  # stalling block_count
                    if exit_on_first_stall:
                        return {
                            "total_block_count": block_count,
                            "confirmed_count": confirmed_count,
                            "unconfirmed_count": block_count - confirmed_count
                        }

                    stall_timeout_max = stall_timeout_max - sleep_on_stall_s
                    stall_timeout_max = timeout_inc + sleep_on_stall_s
                    if timeout_inc >= max_stall_duration_s:
                        raise ValueError(
                            f"No new confirmations for {max_stall_duration_s}s... Fail blocks_confirmed"
                        )  #break if no new confirmatiosn for 6 minutes (default)
                else:  #reset stall timer
                    timeout_inc = 0
                if stall_timeout_max <= 0:
                    raise ValueError(
                        f"Max timeout of {stall_timeout_max} seconds reached")
            first_hash = list(confirmed_hashes
                              )[0] if confirmed_count > 0 else block_hashes[0]
            print(
                f"{confirmed_count}/{block_count} blocks confirmed in {round(time.time() - start_time, 2)} s [{first_hash}] ... [{self.nano_rpc_default.RPC_URL}]"
            )
        except RuntimeError as re:  #when timeout hits
            self.tc.fail(str(re))
        except ValueError as ve:
            self.tc.fail(str(ve))

        self.tc.assertEqual(confirmed_count, block_count)
        return confirmed_count

    def assert_expected_cemented(
        self,
        expected_count,
        rpc_urls=None,
        exit_after_s=30,
    ):
        rpcs = self.get_rpc_custom(rpc_urls)
        break_on_ext_iteration = False
        start_time = time.time()

        while True:
            if break_on_ext_iteration: break
            min_cemented = 1e38
            max_count = 1
            time.sleep(0.2)
            for nano_rpc in rpcs:
                block_count = nano_rpc.block_count()
                min_cemented = min(min_cemented, int(block_count["cemented"]))
                max_count = max(max_count, int(block_count["count"]))
            if expected_count == min_cemented:
                #prints the report when 100% is reached
                break_on_ext_iteration = True
            if time.time() - start_time > exit_after_s:
                self.tc.fail(
                    f"Timout after {exit_after_s}s {min_cemented}/{expected_count} blocks confirmed "
                )
            print("cemented {:>8}/{:<8}  expected: {} [{:4}%]".format(
                min_cemented,
                max_count,
                expected_count,
                floor(min_cemented / max_count * 10000) / 100,
                end="\r"))
            time.sleep(2)

    def assert_all_blocks_cemented(self):
        for nano_rpc in self.nano_rpc_all:
            block_count = nano_rpc.block_count()
            self.tc.assertEqual(block_count["count"], block_count["cemented"])
        return block_count

    def assert_blockgen_succeeded(self, blocks):
        #print(blocks)
        if isinstance(blocks, list):
            self.tc.assertEqual(
                len(list(filter(lambda x: x["success"], blocks))), len(blocks))
        elif isinstance(blocks, dict):
            self.tc.assertTrue(blocks["success"])
        else:
            self.tc.fail("Blocks must be of list or dict type")

    def network_status(self, nodes_name: list = None):
        if nodes_name == []: return ""

        max_count = 0
        nodes_block_count = []

        if nodes_name is not None:
            nodes_rpc = [
                NanoRpc(_CONFP.get_node_rpc(node)) for node in nodes_name
            ]
        else:
            nodes_rpc = self.nano_rpc_all

        for nano_rpc in nodes_rpc:
            block_count = nano_rpc.block_count()
            version_rpc_call = nano_rpc.version()
            max_count = int(block_count["count"]) if int(
                block_count["count"]) > max_count else max_count
            node_name = _CONFP.get_node_name_from_rpc_url(nano_rpc)
            nodes_block_count.append({
                "node_name": node_name,
                "count": block_count["count"],
                "cemented": block_count["cemented"]
            })

        node_version = f'{version_rpc_call["node_vendor"]} {version_rpc_call["build_info"].split(" ")[0]}'[
            0:20]

        report = [
            '{:<16} {:<20} {:>6.2f}% synced | {}/{} blocks cemented'.format(
                bc["node_name"], node_version,
                floor(int(bc["cemented"]) / max_count * 10000) / 100,
                bc["cemented"], bc["count"]) for bc in nodes_block_count
        ]
        return '\n' + '\n'.join(report)


class BlockReadWrite():

    def __init__(self, rpc_url=None):
        self.ba = BlockAsserts(rpc_url)
        self.conf_rw = ConfigReadWrite()

    def read_blocks_from_disk(self,
                              path,
                              seeds=False,
                              hashes=False,
                              blocks=False):
        res = self.conf_rw.read_json(path)
        if seeds: return res["s"]
        if hashes: return res["h"]
        if blocks: return res["b"]
        return res

    def write_blocks_to_disk(self, rpc_block_list, path):
        hash_list = []
        seed_list = []
        block_list = []

        if any(isinstance(i, list)
               for i in rpc_block_list[:2]):  #nested list :
            for block_list_i in rpc_block_list:
                self.ba.assert_blockgen_succeeded(block_list_i)
                block_list.append(list(map(lambda x: x["block"],
                                           block_list_i)))
                seed_list.append(
                    list(
                        set([
                            x["account_data"]["source_seed"]
                            for x in block_list_i
                            if x["account_data"]["source_seed"] is not None
                        ])))
                hash_list.append(list(map(lambda x: x["hash"], block_list_i)))

        else:
            self.ba.assert_blockgen_succeeded(rpc_block_list)
            hash_list.append(list(map(lambda x: x["hash"], rpc_block_list)))
            seed_list.append(
                list(
                    set([
                        x["account_data"]["source_seed"]
                        for x in rpc_block_list
                        if x["account_data"]["source_seed"] is not None
                    ])))  #remove duplicate seeds with set
            block_list.append(list(map(lambda x: x["block"], rpc_block_list)))

        #result is a list of lists always
        res = {"h": hash_list, "s": seed_list, "b": block_list}

        self.conf_rw.write_json(path, res)
