import traceback
import requests
import json
import secrets
import time
import logging
import asyncio
import aiohttp
import threading
from nanolocal.common.nl_nanolib import NanoLibTools, get_account_public_key

# for block_creation, we store local frontier info, so that subsequant calls know about the most recent frontier without needing to publish the block to the ledger.
_FRONTIER_INFO = {}
#introduced to reduce number of RPC calls for static values (network difficulty)
_GLOBAL_CACHE = {}


def _start_async():
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever).start()
    return loop


_loop = None


# Submits awaitable to the event loop, but *doesn't* wait for it to
# complete. Returns a concurrent.futures.Future which *may* be used to
# wait for and retrieve the result (or exception, if one was raised)
def submit_async(awaitable):
    global _loop
    _loop = _start_async()
    res = asyncio.run_coroutine_threadsafe(awaitable, _loop)
    stop_async()
    return res


def stop_async():
    _loop.call_soon_threadsafe(_loop.stop)


class NanoRpc:

    # api_config = None
    # debug = False

    def __init__(self, url, username=None, password=None):
        self.debug = True
        self.RPC_URL = url
        self.RPC_USER = username
        self.RPC_PASSWORD = password
        self.aio_conn = None  #aiohttp.TCPConnector(limit_per_host=100, limit=0, ttl_dns_cache=300)
        self.aio_results = []
        self.nano_lib = NanoLibTools()

    def clear_in_mem_account_info(self):
        _FRONTIER_INFO.clear()
        return _FRONTIER_INFO

    def get_or_create_eventloop(self):
        try:
            return asyncio.get_event_loop()
        except RuntimeError as ex:
            if "There is no current event loop in thread" in str(ex):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return asyncio.get_event_loop()

    async def set_aio_connection(self):
        # 0.1s for 1million connections
        if self.aio_conn is None:
            self.aio_conn = aiohttp.TCPConnector(limit_per_host=50,
                                                 limit=50,
                                                 verify_ssl=False,
                                                 force_close=True)

    def exec_parallel_post(self, post_requests, sync=False):
        res = []
        errors = self.get_new_aio_error()
        if sync:
            self.get_or_create_eventloop().run_until_complete(
                self.post_requests_parallel(post_requests,
                                            sync=sync,
                                            aio_results=res,
                                            aio_errors=errors,
                                            include_request=True))
        else:
            submit_async(
                self.post_requests_parallel(post_requests,
                                            sync=sync,
                                            aio_results=res,
                                            aio_errors=errors,
                                            include_request=True))

        if errors["error_count"] > 0: print(json.dumps(errors, indent=4))
        return res

    def get_new_aio_error(self):
        return {"error_count": 0, "last_request": "", "last_error": ""}

    async def post_requests_parallel(self,
                                     data,
                                     sync=True,
                                     aio_results=[],
                                     include_request=False,
                                     ignore_errors=[],
                                     aio_errors=None):
        #data = [{"url" : "http://...", "request" : {"json_object"}}]
        parallel_requests = 1 if sync else 5
        semaphore = asyncio.Semaphore(parallel_requests)
        #session = aiohttp.ClientSession(connector=self.aio_conn)
        auth = aiohttp.BasicAuth(
            self.RPC_USER, self.RPC_PASSWORD
        ) if self.RPC_USER is not None and self.RPC_PASSWORD is not None else None
        async with aiohttp.ClientSession(connector=self.aio_conn,
                                         auth=auth) as session:

            async def do_req(el, aio_errors):

                async with semaphore:
                    async with session.post(url=el["url"],
                                            json=el["request"],
                                            ssl=False) as response:
                        obj = {"response": json.loads(await response.read())}

                        if include_request:
                            obj["request"] = el["request"]
                            obj["url"] = el["url"]
                        if obj is None:
                            print("Request failed", el)
                        if "error" in obj:
                            if not obj["error"] in ignore_errors:
                                aio_errors["error_count"] = aio_errors[
                                    "error_count"] + 1
                                aio_errors["last_error"] = obj["error"]
                                aio_errors["last_request"] = el
                        aio_results.append(obj)

            aio_errors = self.get_new_aio_error(
            ) if aio_errors != self.get_new_aio_error() else aio_errors
            await asyncio.gather(*(do_req(el, aio_errors) for el in data))
            #if aio_errors["error_count"] > 0 : print(json.dumps(aio_errors, indent=4))
        #await session.close()
        return aio_results

        #'Host': 'nanowallet.cc', 'Accept': '*/*', 'Accept-Encoding': 'gzip, deflate', 'User-Agent': 'Python/3.9 aiohttp/3.8.1', 'Authorization': 'Basic KCduYW5vX3ByJywpOignYV9sb25nX3A0c3N3b3JkX3doMWNoX2FjdHVhbGx5X3cwcmtzX25vdF9pMW5fZzF0Jywp', 'Content-Length': '122', 'Content-Type': 'application/json'

    async def aio_post(self,
                       data,
                       sync=True,
                       json_data=False,
                       include_request=False,
                       aio_results=[],
                       ignore_errors=[]):
        parallel_requests = 1 if sync else 5
        semaphore = asyncio.Semaphore(parallel_requests)

        auth = aiohttp.BasicAuth(
            self.RPC_USER, self.RPC_PASSWORD
        ) if self.RPC_USER is not None and self.RPC_PASSWORD is not None else None
        #async with aiohttp.ClientSession() as session:
        #async with aiohttp.ClientSession(headers=headers) as session:
        async with aiohttp.ClientSession(auth=auth) as session:

            async def do_req(el, aio_errors):
                async with semaphore:
                    try:
                        async with session.post(url=self.RPC_URL,
                                                json=el if json_data else
                                                json.loads(el)) as response:
                            obj = json.loads(await response.read())
                            if include_request:
                                obj["request"] = el if json_data else json.loads(
                                    el)
                            if obj is None:
                                print("Request failed", el)
                            if "error" in obj:
                                if not obj["error"] in ignore_errors:
                                    aio_errors["error_count"] = aio_errors[
                                        "error_count"] + 1
                                    aio_errors["last_error"] = obj["error"]
                                    aio_errors["last_request"] = el
                            aio_results.append(obj)
                    except:
                        traceback.print_exc()
                        #print(f"aio_post_count : {len(aio_results)}", end="\r")

            aio_errors = self.get_new_aio_error()
            await asyncio.gather(*(do_req(el, aio_errors) for el in data))
            if aio_errors["error_count"] > 0:
                print(json.dumps(aio_errors, indent=4))
        #await session.close()

    def request_get(self, url):
        try:
            headers = {
                "Content-type": "application/json",
                "Accept": "text/plain"
            }
            r = requests.get(url, headers=headers, timeout=1)
            response = {
                "status_code": r.status_code,
                "message": json.loads(r.text),
                "success": True
            }
        except Exception as e:
            response = {"success": False, "error_message": str(e)}
        return response

    def post_with_auth(self, content, max_retry=2, timeout=3, silent=True):
        try:
            url = self.RPC_URL
            headers = {
                "Content-type": "application/json",
                "Accept": "text/plain"
            }
            r = requests.post(url,
                              json=content,
                              headers=headers,
                              timeout=timeout)
            r_json = json.loads(r.text)

            # print("request: {} \rrepsonse: {}".format(content["action"], r.text ))ƒ
            if "error" in r_json:
                msg = "error in post_with_auth |\n request: \n{}\nresponse:\n{}".format(
                    content, r.text)
                if r_json["error"] == "Account not found":
                    logging.debug(msg)
                else:
                    if silent: logging.debug(msg)
                    else: logging.warn(msg)
            return r_json
        except Exception as e:
            if self.debug:
                logging.debug(
                    f'Error str{e} ... {max_retry} Retrys left for post_with_auth : {content["action"]}'
                )
            max_retry = max_retry - 1
            if max_retry >= 0:
                time.sleep(0.5)  #100ms
                self.post_with_auth(content, max_retry, timeout=timeout)

    def is_online(self, timeout=1):
        while timeout > 0:
            try:
                logging.debug("block_count: " +
                              self.block_count(max_retry=0)["count"])
                return True
            except:
                timeout = timeout - 1
                time.sleep(1)
        return False

    def generate_seed(self):
        return secrets.token_hex(32)

    def generate_new_seed(self):
        return {
            'success': True,
            'seed': self.generate_seed(),
            'error_message': ''
        }

    def validate_seed(self, seed):
        result = {'seed': seed, 'success': False, 'error_message': ''}
        if len(seed) == 64:
            try:
                int(seed, 16)
                result['success'] = True

            except Exception:
                result['error_message'] = 'Wrong seed format'
        else:
            result['error_message'] = 'Wrong seed length'

        return result

    def get_active_difficulty(self, request_only=False, use_cache=True):
        global _GLOBAL_CACHE
        req = {"action": "active_difficulty"}
        if request_only: return req
        if str(req) in _GLOBAL_CACHE and use_cache:
            result = _GLOBAL_CACHE[str(req)]
        else:
            result = self.post_with_auth(req)
            _GLOBAL_CACHE[str(req)] = result
        return result

    # def get_block_count(self ,request_only =False):
    #     req_active_difficulty = {"action" : "block_count"}
    #     return self.post_with_auth(req_active_difficulty)

    def get_account_data(self, seed, index=0):
        payload = self.generate_account(seed, index)
        payload["success"] = True
        payload["error_message"] = ''

        return payload

    def publish_blocks(self, blocks, json_data=True, sync=True):
        publish_commands = [{
            "action":
            "process",
            "json_block":
            "true",
            "subtype":
            block["subtype"],
            "block":
            (block if json_data else json.loads(block.replace("'", '"')))
        } for block in blocks]
        return self.__publish(payload_array=publish_commands,
                              json_data=json_data,
                              sync=sync)

    def publish_block(self, json_block, subtype=None):
        return self.__publish(
            json_block=json_block,
            subtype=subtype if subtype is not None else
            json_block["subtype"] if "subtype" in json_block else None)

    def send_publish_commands(self, publish_commands, sync=True):
        return self.__publish(payload_array=publish_commands,
                              json_data=True,
                              sync=sync)

    def __publish(self,
                  payload=None,
                  payload_array=None,
                  json_block=None,
                  subtype=None,
                  timeout=3,
                  sync=True,
                  json_data=False):
        if json_block is not None:
            if subtype is None:
                logging.warning(
                    "It's dangerous to publish blocks without subtype!")
                payload = {
                    "action": "process",
                    "json_block": "true",
                    "block": json_block,
                }
            else:
                payload = {
                    "action": "process",
                    "json_block": "true",
                    "subtype": subtype,
                    "block": json_block,
                }
        if payload is not None:
            return self.post_with_auth(json.loads(
                str(payload).replace("'", '"')),
                                       timeout=timeout)

        if payload_array is not None:
            res = []
            #loop = asyncio.get_event_loop()
            if sync:
                self.get_or_create_eventloop().run_until_complete(
                    self.aio_post(payload_array,
                                  sync=True,
                                  json_data=json_data,
                                  aio_results=res))
                #submit_async(self.aio_post(payload_array, sync=True, json_data=json_data, aio_results=res))
            else:
                submit_async(
                    self.aio_post(payload_array,
                                  sync=sync,
                                  json_data=json_data,
                                  aio_results=res))

            return res

    def block_hash_aio(self, json_blocks, sync=False):
        lst = []
        res = []
        for json_block in json_blocks:
            lst.append({
                "action": "block_hash",
                "json_block": "true",
                "block": json_block
            })
        #loop = asyncio.get_event_loop()
        if sync:
            submit_async(
                self.aio_post(lst, sync=sync, json_data=True, aio_results=res))
        else:
            self.get_or_create_eventloop().run_until_complete(
                self.aio_post(lst, sync=sync, json_data=True, aio_results=res))
        return res

    def block_info_aio(self, block_hashes, sync=False, ignore_errors=[]):
        lst = []
        res = []
        for block_hash in block_hashes:
            lst.append({
                "action": "block_info",
                "json_block": "true",
                "hash": block_hash
            })
        #loop = asyncio.get_event_loop()
        if sync:
            submit_async(
                self.aio_post(lst,
                              sync=sync,
                              json_data=True,
                              include_request=True,
                              aio_results=res,
                              ignore_errors=ignore_errors))
        else:
            self.get_or_create_eventloop().run_until_complete(
                self.aio_post(lst,
                              sync=sync,
                              json_data=True,
                              include_request=True,
                              aio_results=res,
                              ignore_errors=ignore_errors))
        return res

    def block_confirmed_aio(self, block_hashes, ignore_errors=[]):
        res = self.block_info_aio(block_hashes, ignore_errors=ignore_errors)
        confirmed_blocks = list(
            filter(
                lambda x: x is not None and "confirmed" in x and x["confirmed"]
                == "true", res))
        return set(map(lambda x: x["request"]["hash"],
                       confirmed_blocks))  #confirmed hashes

    def block_hash(self, json_block, request_only=False):
        req = {
            "action": "block_hash",
            "json_block": "true",
            "block": json_block
        }
        if request_only: return req
        return self.post_with_auth(req)

    def block_info(self, block_hash, request_only=False):
        req = {
            "action": "block_info",
            "json_block": "true",
            "hash": block_hash
        }
        if request_only: return req
        return self.post_with_auth(req)

    def confirmation_active(self, request_only=False):
        req = {"action": "confirmation_active"}
        if request_only: return req
        resp = self.post_with_auth(req)
        if resp["confirmations"] == "": resp["confirmations"] = []
        return resp

    def block_confirmed(self, json_block=None, block_hash=None):
        if json_block is not None:
            block_hash = self.block_hash(json_block)["hash"]
        if block_hash is None:
            return False
        response = self.block_info(block_hash)
        if response is None:
            return False
        if "error" in response:
            return False
        return True if response["confirmed"] == "true" else False

    def block_count(self, max_retry=2, request_only=False):
        req = {"action": "block_count"}
        if request_only: return req
        resp = self.post_with_auth(req, max_retry=max_retry)
        return resp

    def get_stats(self, type="counters", request_only=False):
        req = {"action": "stats", "type": str(type)}
        if request_only: return req
        resp = self.post_with_auth(req)
        return resp

    def version(self, request_only=False):
        req = {"action": "version"}
        if request_only: return req
        resp = self.post_with_auth(req)
        return resp

    def generate_account(self, seed, index, request_only=False):
        req = {
            "action": "deterministic_key",
            "seed": seed,
            "index": index,
        }
        if request_only: return req
        account_data = self.post_with_auth(req)
        print("")

        account_data = {
            "seed":
            seed,
            "index":
            index,
            "private":
            account_data["private"],
            "public":
            account_data["public"],
            "account":
            account_data["account"],
            "nano_prefix":
            account_data["account"][0:11],
            "nano_center":
            account_data["account"][11:59],
            "nano_suffix":
            account_data["account"][len(account_data["account"]) - 6:]
        }
        return account_data

    def validate_account_number(self, account, request_only=False):
        response = {"success": False}
        req = {
            "action": "validate_account_number",
            "account": account,
        }
        if request_only: return req
        data = self.post_with_auth(req)
        if data["valid"] == "1":
            response["success"] = True
        return response

    def unlock_wallet(self, wallet, password, request_only=False):
        response = {"success": False}
        req = {
            "action": "password_enter",
            "wallet": wallet,
            "password": password
        }
        if request_only: return req
        data = self.post_with_auth(req)
        if data["valid"] == "1":
            response["success"] = True
        return response

    def wallet_create(self, seed, request_only=False):
        # response = {"success" : False}
        if seed == None:
            req = {"action": "wallet_create"}
        else:
            req = {
                "action": "wallet_create",
                "seed": seed,
            }
        if request_only: return req
        data = self.post_with_auth(req)
        # {
        #     "wallet": "646FD8B5940AB5B1AD2C0B079576A4CF5A25E8ADB10C91D514547EF5C10C05B7",
        #     "last_restored_account": "nano_3mcsrncubmquwcwgiouih17fjo8183t497c3q9w6qtnwz8bp3fig5x8m4rkw",
        #     "restored_count": "1"
        # }
        return data

    def wallet_add(self, wallet, private_key, request_only=False):
        # response = {"success" : False}
        req = {"action": "wallet_add", "wallet": wallet, "key": private_key}
        if request_only: return req
        data = self.post_with_auth(req)
        # {
        #   "account": "nano_3e3j5tkog48pnny9dmfzj1r16pg8t1e76dz5tmac6iq689wyjfpi00000000"
        # }
        return data

    def key_expand(self, private_key, request_only=False):
        req = {"action": "key_expand", "key": private_key}
        if request_only: return req
        data = self.post_with_auth(req)
        return data

    def peers(self, request_only=False):
        req = {"action": "peers"}
        if request_only: return req
        data = self.post_with_auth(req)
        return data

    def confirmation_quorum(self, request_only=False):
        req = {"action": "confirmation_quorum"}
        if request_only: return req
        data = self.post_with_auth(req)
        return data

    def account_info(self, account, request_only=False):
        req = {
            "action": "account_info",
            "account": account,
            "representative": "true",
            "pending": "true",
            "include_confirmed": "true"
        }
        if request_only: return req
        data = self.post_with_auth(req)
        return data

    def block_create_rpc(self,
                         balance,
                         account,
                         key,
                         representative,
                         link,
                         previous,
                         request_only=False):
        if previous is None: previous = "0" * 64
        req = {
            "action": "block_create",
            "json_block": "true",
            "type": "state",
            "balance": str(balance),
            "account": account,
            "key": key,
            "representative": representative,
            "link": link,
            "previous": previous,
            "difficulty": self.get_active_difficulty()["network_minimum"]
        }
        if request_only: return req
        data = self.post_with_auth(req)
        return data

    def block_create(self,
                     balance,
                     account,
                     key,
                     representative,
                     link,
                     previous,
                     request_only=False):

        block = self.nano_lib.create_state_block(
            account,
            representative,
            previous,
            balance,
            link,
            key,
            difficulty=self.get_active_difficulty()["network_minimum"])

        return {
            "hash": block.block_hash,
            "difficulty": block.difficulty,
            "block": json.loads(block.json())
        }

    def representatives_online(self, weight="false", request_only=False):
        req = {
            "action": "representatives_online",
            "weight": str(weight).lower()
        }
        if request_only: return req
        data = self.post_with_auth(req)
        return data

    def check_balance(self,
                      account,
                      include_only_confirmed=True,
                      request_only=False):

        multiplier = 10**30
        req = {
            "action": "account_balance",
            "account": account,
            "include_only_confirmed": include_only_confirmed
        }
        if request_only: return req
        data = self.post_with_auth(req)

        return {
            "account":
            account,
            "balance_raw":
            int(data["balance"]),
            "balance":
            self.truncate(int(data["balance"]) / multiplier),
            "pending":
            self.truncate(int(data["pending"]) / multiplier),
            "total":
            self.truncate(
                (int(data["balance"]) + int(data["pending"])) / multiplier)
        }

    def check_balances(self, seed, start_index=0, end_index=50):
        # check if there is any balance for account 0 to 50 accounts
        # {'index' : '' , 'account': '', 'balance': '', 'pending': ''}  ; spendable, total  Balance : 100 Nano . ! 95 Nano are currently not spendable. Your action is required.
        result = []
        for index in range(start_index, end_index + 1):
            nano_account = self.generate_account(seed, index)
            result.append(self.check_balance(nano_account["account"]))
        return result

    def truncate(self, number):
        if number > 0:
            return str('{:8f}'.format(number))
        else:
            return "0.00"

    def account_key(self, account, request_only=False):
        req = {"action": "account_key", "account": account}
        if request_only: return req
        data = self.post_with_auth(req)  #["key"]
        return data

    def get_pending_blocks(self, nano_account, threshold, number_of_blocks):

        response = {
            "account": nano_account,
            "blocks": None,
            "success": True,
            "error_message": ""
        }

        req_accounts_pending = {
            "action": "accounts_pending",
            "accounts": [nano_account],
            "threshold": str(threshold),
            "sorting": "true",
            "count": str(number_of_blocks)
        }
        accounts_pending = self.post_with_auth(req_accounts_pending)

        if "error" in accounts_pending:
            response["success"] = False
            response["error_message"] = accounts_pending["error"]
        elif accounts_pending["blocks"][nano_account] == "":
            response["success"] = False
            response["error_message"] = "no pending blocks"
        else:
            response["blocks"] = accounts_pending["blocks"][nano_account]

        return response

    def create_block(self,
                     sub_type,
                     link=None,
                     destination_account=None,
                     representative=None,
                     source_seed=None,
                     source_index=None,
                     source_private_key=None,
                     amount_raw=None,
                     in_memory=False,
                     add_in_memory=False,
                     read_in_memory=False,
                     use_rpc=True):
        try:
            if in_memory:
                add_in_memory = True
                read_in_memory = True
            if source_private_key is not None:
                source_account_data = self.nano_lib.nanolib_account_data(
                    private_key=source_private_key)
            elif source_seed is not None and source_index is not None:
                source_account_data = self.nano_lib.nanolib_account_data(
                    seed=source_seed, index=source_index)

            if read_in_memory:
                if source_account_data["account"] in _FRONTIER_INFO:
                    source_account_info = _FRONTIER_INFO[
                        source_account_data["account"]]
                else:
                    source_account_info = self.account_info(
                        source_account_data["account"])
            else:
                source_account_info = self.account_info(
                    source_account_data["account"])

            if representative is None:
                representative = source_account_info["representative"]
            if "balance" in source_account_info:
                balance = source_account_info["balance"]
            if "frontier" in source_account_info:
                previous = source_account_info["frontier"]

            if sub_type == "open" or sub_type == "receive":
                #destination_account = source_account_data["account"]
                if "error" in source_account_info:
                    sub_type = "open"
                    previous = None
                    balance = amount_raw
                    link = link
                else:
                    sub_type = "receive"
                    previous = source_account_info["frontier"]
                    balance = int(
                        source_account_info["balance"]) + int(amount_raw)
                    link = link

            elif sub_type == "send":
                link = get_account_public_key(account_id=destination_account)
                balance = int(source_account_info["balance"]) - int(amount_raw)
                previous = source_account_info["frontier"]

            elif sub_type == "change":
                amount_raw = "0"
                destination_account = source_account_data["account"]
                link = link

            elif sub_type == "epoch":
                if use_rpc: pass
                else: balance = int(source_account_info["balance"])

            if use_rpc:
                block = self.block_create_rpc(balance,
                                              source_account_data["account"],
                                              source_account_data["private"],
                                              representative, link, previous)
            else:
                block = self.block_create(balance,
                                          source_account_data["account"],
                                          source_account_data["private"],
                                          representative, link, previous)

            block["private"] = source_account_data["private"]
            block["subtype"] = sub_type
            block["amount_raw"] = amount_raw

            if "error" in block:
                block["success"] = False
                block["block"] = {}
                block["hash"] = None
            else:
                block["success"] = True
                block["error"] = None
                if add_in_memory:
                    _FRONTIER_INFO[source_account_data["account"]] = {
                        "frontier": block["hash"],
                        "balance": balance,
                        "representative": representative
                    }
            block["block"]["subtype"] = sub_type

        except Exception as e:
            traceback.print_exc()
            block = {
                "success": False,
                "block": {},
                "hash": None,
                "subtype": sub_type,
                "error": str(e)
            }
        return block

    def get_published_state(self, block, broadcast):
        published = False
        if broadcast:
            publish = self.publish_block(block["block"],
                                         subtype=block["subtype"])
            if "hash" in publish: published = True

    def get_block_result(self,
                         block,
                         broadcast,
                         source_seed=None,
                         source_index=None,
                         exit_after_s=2):
        start_time = time.time()
        if not block["success"]:
            logging.warning(block["error"])
        if broadcast:
            #with timeout(exit_after_s, exception=RuntimeError) :

            publish = None
            while publish is None:
                if time.time() - start_time > exit_after_s: break
                publish = self.publish_block(block["block"],
                                             subtype=block["subtype"])
                if publish is None:
                    time.sleep(0.5)
                    broadcast = False
                    logging.error(f'block not published : {block["hash"]}')
                    continue
                broadcast = True if "hash" in publish else False

        result = {
            "success":
            block["success"],
            "published":
            broadcast,
            "balance_raw":
            block["block"]["balance"] if "balance" in block["block"] else "",
            "amount_raw":
            block["amount_raw"] if "amount_raw" in block else "0",
            "hash":
            block["hash"],
            "block":
            block["block"],
            "subtype":
            block["subtype"],
            "account_data": {
                "account":
                block["block"]["account"]
                if "account" in block["block"] else "",
                "private":
                block["private"] if "private" in block else "",
                "source_seed":
                source_seed,
                "source_index":
                source_index
            },
            "error":
            block["error"]
        }

        if not result["success"]: print(result)

        return result

    def create_open_block(self,
                          destination_account,
                          open_private_key,
                          amount_per_chunk_raw,
                          rep_account,
                          send_block_hash,
                          broadcast=True):
        block = self.create_block("receive",
                                  source_private_key=open_private_key,
                                  destination_account=destination_account,
                                  representative=rep_account,
                                  amount_raw=amount_per_chunk_raw,
                                  link=send_block_hash,
                                  in_memory=not broadcast)

        return self.get_block_result(block, broadcast)

    def create_send_block(self,
                          source_seed,
                          source_index,
                          destination_account,
                          amount_per_chunk_raw,
                          broadcast=True):
        block = self.create_block("send",
                                  source_seed=source_seed,
                                  source_index=source_index,
                                  destination_account=destination_account,
                                  amount_raw=amount_per_chunk_raw,
                                  in_memory=not broadcast)
        return self.get_block_result(block,
                                     broadcast,
                                     source_seed=source_seed,
                                     source_index=source_index)

    def create_change_block(self,
                            source_seed,
                            source_index,
                            new_rep,
                            broadcast=True):
        block = self.create_block("change",
                                  source_seed=source_seed,
                                  source_index=source_index,
                                  link="0" * 64,
                                  representative=new_rep,
                                  in_memory=not broadcast)

        return self.get_block_result(block,
                                     broadcast,
                                     source_seed=source_seed,
                                     source_index=source_index)

    def create_change_block_pkey(self,
                                 source_private_key,
                                 new_rep,
                                 broadcast=True):
        block = self.create_block("change",
                                  source_private_key=source_private_key,
                                  link="0" * 64,
                                  representative=new_rep,
                                  in_memory=not broadcast)
        return self.get_block_result(block, broadcast)

    def create_send_block_pkey(self,
                               private_key,
                               destination_account,
                               amount_per_chunk_raw,
                               broadcast=True):

        block = self.create_block("send",
                                  source_private_key=private_key,
                                  destination_account=destination_account,
                                  amount_raw=amount_per_chunk_raw,
                                  in_memory=not broadcast)
        return self.get_block_result(block, broadcast)

    def create_epoch_block(self,
                           epoch_link,
                           genesis_private_key,
                           genesis_account,
                           broadcast=True):

        #account_info = self.account_info(genesis_account)
        #epoch_block = self.block_create(account_info["balance"],genesis_account, genesis_private_key, account_info["representative"],epoch_link,account_info["frontier"] )
        #print(epoch_block)
        block = self.create_block("epoch",
                                  source_private_key=genesis_private_key,
                                  destination_account=genesis_account,
                                  link=epoch_link,
                                  in_memory=not broadcast)

        return self.get_block_result(block, broadcast)
