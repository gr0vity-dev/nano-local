from collections.abc import Mapping
import requests
import json
import secrets
import math
import time
import logging
import asyncio
import aiohttp

_account_info = {}

class Api:

    # api_config = None
    # debug = False
   
    def __init__(self, url):       
        self.debug = True
        self.RPC_URL = url
        self.aio_conn = None #aiohttp.TCPConnector(limit_per_host=100, limit=0, ttl_dns_cache=300)
        self.aio_results = []
    
    async def set_aio_connection(self):
        # 0.1s for 1million connections
        if self.aio_conn is None : 
            self.aio_conn = aiohttp.TCPConnector(limit_per_host=100, limit=0, ttl_dns_cache=300)         

    async def aio_post(self,parallel_requests, data):        
        semaphore = asyncio.Semaphore(parallel_requests)
        session = aiohttp.ClientSession(connector=self.aio_conn)

        async def post(el):
            async with semaphore:
                async with session.post(url=self.RPC_URL, json=json.loads(el), ssl=False) as response:
                    obj = json.loads(await response.read())                   
                    self.aio_results.append(obj)    
        
        await asyncio.gather(*(post(el) for el in data))
        await session.close()  
        
    
    
 
    def post_with_auth(self, content, max_retry=2, timeout = 3, silent = True):
        try :
            url = self.RPC_URL 
            headers = {"Content-type": "application/json", "Accept": "text/plain"}    
            r = requests.post(url, json=content, headers=headers, timeout=timeout)             
            r_json = json.loads(r.text)
            # print("request: {} \rrepsonse: {}".format(content["action"], r.text ))
            if "error" in r_json:
                msg = "error in post_with_auth |\n request: \n{}\nresponse:\n{}".format(content, r.text)
                if r_json["error"] == "Account not found" :
                    logging.debug(msg)
                else :
                    if silent : logging.debug(msg)
                    else : logging.warn(msg)
            return r_json
        except Exception as e:             
            if self.debug : logging.debug(f'Error str{e} ... {max_retry} Retrys left for post_with_auth : {content["action"]}')
            max_retry = max_retry - 1   
            if max_retry >= 0 : 
                time.sleep(0.5)  #100ms
                self.post_with_auth(content,max_retry,timeout=timeout)

    def is_online(self, timeout = 1):
        while timeout > 0 :
            try : 
                logging.debug("block_count: " + self.block_count(max_retry=0)["count"])
                return True
            except :
                timeout = timeout -1
                time.sleep(1)
        return False    
    
    def generate_seed(self):
        return secrets.token_hex(32)

    def generate_new_seed(self):
        return {'success': True,
                'seed': self.generate_seed(),
                'error_message': ''}

    def validate_seed(self, seed):
        result = {
            'seed': seed,
            'success': False,
            'error_message': ''
        }
        if len(seed) == 64:
            try:
                int(seed, 16)
                result['success'] = True

            except Exception:
                result['error_message'] = 'Wrong seed format'
        else:
            result['error_message'] = 'Wrong seed length'

        return result

    def get_active_difficulty(self):
        req_active_difficulty = {"action" : "active_difficulty"}
        return self.post_with_auth(req_active_difficulty)

    def get_account_data(self, seed):
        payload = self.generate_account(seed, 0)
        payload["success"] = True
        payload["error_message"] = ''
        
        return payload
    
    def publish(self, payload = None , payload_array = None, json_block = None, subtype = None, timeout = 3, sync = True) :  
        if json_block is not None:
            if subtype is None :
                logging.warning("It's dangerous to publish blocks without subtype!")
                payload = {
                    "action": "process",
                    "json_block": "true",
                    "block": json_block,
                }
            else :
                payload = {
                    "action": "process",
                    "json_block": "true",
                    "subtype": subtype,
                    "block": json_block,
                }
        if payload is not None:              
            return self.post_with_auth(json.loads(str(payload)), timeout=timeout)   
        
        if payload_array is not None :             
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.aio_post(1 if sync else 100, payload_array))            
            return self.aio_results

    def block_hash(self, json_block):
        req = {  
            "action": "block_hash",
            "json_block": "true", 
            "block": json_block
            }
        return self.post_with_auth(req) 
    
    def block_info(self, block_hash) :
        req = {  
            "action": "block_info",
            "json_block": "true",
            "hash": block_hash
            }
        return self.post_with_auth(req) 

    def block_confirmed(self, json_block = None , block_hash = None) :
        if json_block is not None :
            block_hash = self.block_hash(json_block)["hash"]
        if block_hash is None : 
            return False
        response = self.block_info(block_hash)
        if "error" in response : 
            return False
        return True if response["confirmed"] == "true" else False 

    def get_account_data(self, seed, index):
        payload = self.generate_account(seed, index)
        payload["success"] = True
        payload["error_message"] = ''
        
        return payload

    def block_count(self, max_retry = 2):
        req_block_count = {
            "action": "block_count"
        } 
        return self.post_with_auth(req_block_count, max_retry=max_retry) 
    
    def generate_account(self, seed, index):
        
        req_deterministic_key = {
            "action": "deterministic_key",
            "seed": seed,
            "index": index,
        }
        
        account_data = self.post_with_auth(req_deterministic_key)
        
        account_data = {
            "seed": seed,
            "index": index,
            "private": account_data["private"],
            "public": account_data["public"],
            "account": account_data["account"],
            "nano_prefix": account_data["account"][0:11],
            "nano_center": account_data["account"][11:59],
            "nano_suffix": account_data["account"][len(account_data["account"]) - 6:]
        }
        return account_data

    def validate_account_number(self, account):
        response = {"success" : False}
        req_validate_account_number = {
            "action": "validate_account_number",
            "account": account,
        }        
        data = self.post_with_auth(req_validate_account_number)  
        if data["valid"] == "1" :
            response["success"] = True            
        return response

    def unlock_wallet(self, wallet, password):
        response = {"success" : False}
        req_password_enter = {
        "action": "password_enter",
        "wallet": wallet,
        "password": password
        }        
        data = self.post_with_auth(req_password_enter)       
        if data["valid"] == "1" :
            response["success"] = True            
        return response

    def wallet_create(self, seed):
        # response = {"success" : False}
        if seed == None :
            req_wallet_create = {
            "action": "wallet_create"
        }
        else :
            req_wallet_create = {
                "action": "wallet_create",
                "seed": seed,
            }
        data = self.post_with_auth(req_wallet_create)        
        # {
        #     "wallet": "646FD8B5940AB5B1AD2C0B079576A4CF5A25E8ADB10C91D514547EF5C10C05B7",
        #     "last_restored_account": "nano_3mcsrncubmquwcwgiouih17fjo8183t497c3q9w6qtnwz8bp3fig5x8m4rkw",
        #     "restored_count": "1"
        # }          
        return data

    def wallet_add(self, wallet, private_key) :
        # response = {"success" : False}
        req_wallet_add = {
            "action": "wallet_add",
            "wallet": wallet,
            "key": private_key
        }
        data = self.post_with_auth(req_wallet_add)
        # {
        #   "account": "nano_3e3j5tkog48pnny9dmfzj1r16pg8t1e76dz5tmac6iq689wyjfpi00000000"
        # }        
        return data
        
    def key_expand(self, private_key):               
        req_key_expand = {
            "action": "key_expand",
            "key": private_key
        }
        data = self.post_with_auth(req_key_expand)     
        return data           

    def peers(self):
        req_peers = {
            "action": "peers"
        }
        data = self.post_with_auth(req_peers)     
        return data      

    def confirmation_quorum(self):
        req_confirmation_quorum = {  
            "action": "confirmation_quorum"      
        }     
        data = self.post_with_auth(req_confirmation_quorum)     
        return data 
    
    def representatives_online(self, weight = "false"):
        req_representatives_online = {  
            "action": "representatives_online"  ,
            "weight" :  str(weight).lower()   
        }     
        data = self.post_with_auth(req_representatives_online)     
        return data 

    def check_balance(self, account, include_only_confirmed = True):
       
        multiplier = 10 ** 30
        req_account_balance = {
            "action": "account_balance",
            "account": account,
            "include_only_confirmed" : include_only_confirmed
        }
        data = self.post_with_auth(req_account_balance)
       
        return {"account": account, 
                "balance_raw" : int(data["balance"]), 
                "balance": self.truncate(int(data["balance"]) / multiplier), 
                "pending": self.truncate(int(data["pending"]) / multiplier), 
                "total": self.truncate((int(data["balance"]) + int(data["pending"])) / multiplier)}

    def check_balances(self, seed):
        # check if there is any balance for account 0 to 50 accounts
        # {'index' : '' , 'account': '', 'balance': '', 'pending': ''}  ; spendable, total  Balance : 100 Nano . ! 95 Nano are currently not spendable. Your action is required.
        result = []
        for index in range(0, 51):
            nano_account = self.generate_account(seed, index)
            result.append(self.check_balance(nano_account["account"]))

    def truncate(self, number):
        if number > 0 :            
            return str('{:8f}'.format(number))
        else :
            return "0.00"

    def get_pending_blocks(
        self,
        nano_account,
        threshold,
        number_of_blocks
    ) :

        response = {"account" : nano_account,
                    "blocks" : None,
                    "success" : True,
                    "error_message" : "" }

        req_accounts_pending = {
            "action": "accounts_pending",
            "accounts": [nano_account],
            "threshold" : str(threshold),
            "sorting" : "true",
            "count": str(number_of_blocks)
        }       
        accounts_pending = self.post_with_auth(req_accounts_pending)  

        if "error" in accounts_pending:
            response["success"] = False
            response["error_message"] = accounts_pending["error"]
        elif accounts_pending["blocks"][nano_account] == "" :        
            response["success"] = False
            response["error_message"] = "no pending blocks"
        else :
            response["blocks"] = accounts_pending["blocks"][nano_account]
        
        return response
  
    def create_open_block(
        self,
        destination_account,
        open_private_key,
        amount_per_chunk_raw,
        rep_account,
        send_block_hash,
        broadcast = True
    ):

        req_account_info = {
            "action": "account_info",
            "account": destination_account,
            "representative": "true",
            "pending": "true",
            "include_confirmed": "true"
        }
        account_info = self.post_with_auth(req_account_info)

        if "error" in account_info:
            subtype = "open"
            previous = "0000000000000000000000000000000000000000000000000000000000000000"
            balance = str(amount_per_chunk_raw)
        else:
            subtype = "receive"
            previous = account_info["frontier"]
            balance = str(
                int(account_info["confirmed_balance"]) + int(amount_per_chunk_raw))

        # prepare open/receive block
        req_block_create = {
            "action": "block_create",
            "json_block": "true",
            "type": "state",
            "balance": balance,
            "account": destination_account,
            "key": open_private_key,
            "representative": rep_account,
            "link": send_block_hash,
            "previous": previous,
            "difficulty" : self.get_active_difficulty()["network_receive_current"]
        }
        block = self.post_with_auth(req_block_create)

        next_hash = block["hash"]
        req_process = {
                "action": "process",
                "json_block": "true",
                "subtype": subtype,
                "block": block["block"],
            }
        if broadcast:            
            publish = self.post_with_auth(req_process)
            req_process = True
        else :
            _account_info[destination_account] = {"frontier" : block["hash"] , "balance" :  balance,  "representative" : rep_account}
            #print("open_added" , destination_account, block["hash"], )
        
        return {"success" : True,
                "account" : destination_account, 
                "balance_raw": balance,
                "balance": self.truncate(int(balance) / (10 ** 30)), 
                "hash": next_hash,
                "amount_raw": amount_per_chunk_raw,
                "amount": self.truncate(int(amount_per_chunk_raw) / (10 ** 30)),
                "req_process": req_process       
                }      
        # return next_hash

    def create_send_block(
        self,
        source_seed,
        source_index,
        destination_account,
        amount_per_chunk_raw,
        broadcast = True
    ):
        if self.debug : t1 = time.time() 
        req_source_account = {
            "action": "deterministic_key",
            "seed": source_seed,
            "index": source_index,
        }
        if self.debug : logging.debug("req_source_account : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 

        source_account_data = self.post_with_auth(req_source_account)
        source_account_data = {
            "seed": source_seed,
            "index": source_index,
            "private": source_account_data["private"],
            "public": source_account_data["public"],
            "account": source_account_data["account"],
        }

        req_account_info = {
            "action": "account_info",
            "account": source_account_data["account"],
            "representative": "true",
            "pending": "true",
            "include_confirmed": "true"
        }
        account_info = self.post_with_auth(req_account_info)
        if self.debug : logging.debug("post_with_auth : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 

        source_previous = account_info["frontier"]
        source_balance = account_info["balance"]
        current_rep = account_info["representative"]

        req_destination_key = {"action": "account_key",
                               "account": destination_account}
        destination_link = self.post_with_auth(req_destination_key)["key"]
        if self.debug : logging.debug("req_destination_key : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 

        # prepare send block
        block_balance = str(int(source_balance) - int(amount_per_chunk_raw))
        req_block_create = {
            "action": "block_create",
            "json_block": "true",
            "type": "state",
            "balance": str(block_balance),
            "key": source_account_data["private"],
            "representative": current_rep,
            "link": destination_link,
            "link_as_account": destination_account,
            "previous": source_previous,
            "difficulty" : self.get_active_difficulty()["network_current"]
            # ,"difficulty": difficulty,
        }
        if self.debug : logging.debug("req_block_create : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 
        send_block = self.post_with_auth(req_block_create)
        logging.debug(send_block["hash"])

        req_process = {
                "action": "process",
                "json_block": "true",
                "subtype": "send",
                "block": send_block["block"],
            }

        if broadcast:            
            publish = self.post_with_auth(req_process)
            if self.debug : logging.debug("req_process : {}".format(time.time() - t1))
            req_process = True
        

        # prepare for next iteration
        #source_balance = block_balance
        #source_previous = next_hash

        # -------------- 2) END -------------------------
        return {"success" : True,
                "account" : source_account_data["account"], 
                "balance_raw": block_balance,
                "balance": self.truncate(int(block_balance) / (10 ** 30)), 
                "hash": send_block["hash"],
                "amount_raw": amount_per_chunk_raw,
                "amount": self.truncate(int(amount_per_chunk_raw) / (10 ** 30)),
                "req_process": req_process             
                }

    def create_send_block_pkey(
        self,
        private_key,
        destination_account,
        amount_per_chunk_raw,
        broadcast = True
    ):
        
        if self.debug : t1 = time.time() 

        key_expand = self.key_expand(private_key)
       
        source_account_data = {    
            "private": key_expand["private"],
            "account": key_expand["account"],
        }

        req_account_info = {
            "action": "account_info",
            "account": source_account_data["account"],
            "representative": "true",
            "pending": "true",
            "include_confirmed": "true"
        }

        
        account_info = self.post_with_auth(req_account_info)
        if self.debug : logging.debug("post_with_auth : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 

        if broadcast == False:
            if _account_info == {} :
                pass #first call
            else :
                account_info = _account_info[source_account_data["account"]]
            #print("found" , source_account_data["account"], account_info["frontier"])

        source_previous = account_info["frontier"]
        source_balance = account_info["balance"]
        current_rep = account_info["representative"]

        req_destination_key = {"action": "account_key",
                               "account": destination_account}
        destination_link = self.post_with_auth(req_destination_key)["key"]
        if self.debug : logging.debug("req_destination_key : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 

        # prepare send block
        block_balance = str(int(source_balance) - int(amount_per_chunk_raw))
        req_block_create = {
            "action": "block_create",
            "json_block": "true",
            "type": "state",
            "balance": str(block_balance),
            "key": source_account_data["private"],
            "representative": current_rep,
            "link": destination_link,
            "link_as_account": destination_account,
            "previous": source_previous,
            "difficulty" : self.get_active_difficulty()["network_current"] 
        }
        if self.debug : logging.debug("req_block_create : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 
        send_block = self.post_with_auth(req_block_create)
        logging.debug(send_block["hash"])

        
        req_process = {
                "action": "process",
                "json_block": "true",
                "subtype": "send",
                "block": send_block["block"],
            }
        if broadcast :
            publish = self.post_with_auth(req_process)
            if self.debug : logging.debug("req_process : {}".format(time.time() - t1))
            req_process = True
        else :
            _account_info[source_account_data["account"]] = {"frontier" : send_block["hash"] , "balance" :  block_balance,  "representative" : current_rep}
            #print("send_added" , source_account_data["account"], send_block["hash"])
        
        

        # prepare for next iteration
        #source_balance = block_balance
        #source_previous = next_hash

        # -------------- 2) END -------------------------
        return {"success" : True,
                "account" : source_account_data["account"], 
                "balance_raw": block_balance,
                "balance": self.truncate(int(block_balance) / (10 ** 30)), 
                "hash": send_block["hash"],
                "amount_raw": amount_per_chunk_raw,
                "amount": self.truncate(int(amount_per_chunk_raw) / (10 ** 30)),
                "req_process": req_process             
                }

    def create_epoch_block(
        self,
        epoch_link,
        genesis_private_key,
        genesis_account,
        broadcast = True
    ):

        if self.debug : t1 = time.time()
        req_account_info = {
            "action": "account_info",
            "account": genesis_account,
            "representative": "true",
            "pending": "true",
            "include_confirmed": "true"
        }

        account_info = self.post_with_auth(req_account_info)
        if self.debug : logging.debug("post_with_auth : {}".format(time.time() - t1))
        if self.debug : t1 = time.time()

        req_block_create = {
            "action": "block_create",
            "json_block": "true",
            "type": "state",
            "balance": account_info["balance"],
            "key": genesis_private_key,
            "representative": account_info["representative"],
            "link": epoch_link,
            "previous": account_info["frontier"],
            "difficulty" : self.get_active_difficulty()["network_current"]
        }

        if self.debug : logging.debug("req_block_create : {}".format(time.time() - t1))
        if self.debug : t1 = time.time()
        epoch_block = self.post_with_auth(req_block_create)
        logging.debug(epoch_block["hash"])

        req_process = {
                "action": "process",
                "json_block": "true",
                "subtype": "epoch",
                "block": epoch_block["block"],
            }
        if broadcast:           
            logging.debug(req_process)
            publish = self.post_with_auth(req_process)
            if self.debug : logging.debug("req_process : {}".format(time.time() - t1))
            req_process = True

        return {"success" : True,
                "account" : genesis_account,
                "hash": epoch_block["hash"],
                "req_process" : req_process
                }




class NanoTools:
    import gmpy2
    from gmpy2 import mpfr ,mpz
    from itertools import islice    

    gmpy2.get_context().precision=1000
      
    def raw_percent(self, raw, percent) :
        return self.mpz(self.mpz(str(raw)) * self.mpfr(str(percent)) / self.mpz('100'))
    
    def raw_add(self, val1, val2) :  
        #val1 + val2             
        return str(self.mpz(self.mpz(str(val1)) + self.mpz(str(val2)))) 
    
    def raw_sub(self, val1, val2) : 
        #val1 - val2       
        return str(self.mpz(self.mpz(str(val1)) - self.mpz(str(val2))))
    
    #For reference
    def where(self, array, value) :
        list(filter(lambda x: value in x, array)) 
    
    def where_not(self, array, value) :
        list(filter(lambda x: value not in x, array)) 
    
    def skip_take(self, list, skip_n, take_n):
        list(self.islice(list, skip_n, take_n)) #skip(skip_n).take(take_n)
    
