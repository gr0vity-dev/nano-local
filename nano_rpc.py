 
import requests
import json
import secrets
import math
import time
import logging
import os


class Api:

    # api_config = None
    # debug = False
   
    def __init__(self, url):       
        self.debug = True
        self.RPC_URL = url
    
    def post_with_auth(self, content):
        
        url = self.RPC_URL 
        headers = {"Content-type": "application/json", "Accept": "text/plain"}    
        response = requests.post(url, json=content, headers=headers)
        # print("request: {} \rrepsonse: {}".format(content["action"], response.text ))
        return response
 

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
    def get_account_data(self, seed):
        payload = self.generate_account(seed, 0)
        payload["success"] = True
        payload["error_message"] = ''
        
        return payload

    def get_account_data(self, seed, index):
        payload = self.generate_account(seed, index)
        payload["success"] = True
        payload["error_message"] = ''
        
        return payload

    def generate_account(self, seed, index):
        
        req_deterministic_key = {
            "action": "deterministic_key",
            "seed": seed,
            "index": index,
        }
        r = self.post_with_auth(req_deterministic_key)
        account_data = json.loads(r.text)
        
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
        r = self.post_with_auth(req_validate_account_number)
        data = json.loads(r.text)        
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
        r = self.post_with_auth(req_password_enter)
        data = json.loads(r.text)        
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
        r = self.post_with_auth(req_wallet_create)
        data = json.loads(r.text)        
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
        r = self.post_with_auth(req_wallet_add)
        data = json.loads(r.text)        
        # {
        #   "account": "nano_3e3j5tkog48pnny9dmfzj1r16pg8t1e76dz5tmac6iq689wyjfpi00000000"
        # }        
        return data
        
    def key_expand(self, private_key):        
        req_key_expand = {
            "action": "key_expand",
            "key": private_key
        }
        r = self.post_with_auth(req_key_expand)
        data = json.loads(r.text) 
        return data           


    def check_balance(self, account):
       
        multiplier = 10 ** 30
        req_account_balance = {
            "action": "account_balance",
            "account": account,
        }
        r = self.post_with_auth(req_account_balance)
        data = json.loads(r.text)
       
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
        r = self.post_with_auth(req_accounts_pending)
        accounts_pending = json.loads(r.text)     

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
    ):

        req_account_info = {
            "action": "account_info",
            "account": destination_account,
            "representative": "true",
            "pending": "true",
            "include_confirmed": "true"
        }
        r = self.post_with_auth(req_account_info)
        account_info = json.loads(r.text)

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
            "previous": previous
            # ,"difficulty": difficulty,
        }

        r = self.post_with_auth(req_block_create)
        block = json.loads(r.text)

        next_hash = block["hash"]

        req_process = {
            "action": "process",
            "json_block": "true",
            "subtype": subtype,
            "block": block["block"],
        }

        r = self.post_with_auth(req_process)
        return {"success" : True,
                "account" : destination_account, 
                "balance_raw": balance,
                "balance": self.truncate(int(balance) / (10 ** 30)), 
                "hash": next_hash,
                "amount_raw": amount_per_chunk_raw,
                "amount": self.truncate(int(amount_per_chunk_raw) / (10 ** 30))}
        # return next_hash

    def create_send_block(
        self,
        source_seed,
        source_index,
        destination_account,
        amount_per_chunk_raw
    ):
        if self.debug : t1 = time.time() 
        req_source_account = {
            "action": "deterministic_key",
            "seed": source_seed,
            "index": source_index,
        }
        r = self.post_with_auth(req_source_account)
        if self.debug : logging.info("req_source_account : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 

        source_account_data = json.loads(r.text)
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
        r = self.post_with_auth(req_account_info)
        account_info = json.loads(r.text)
        if self.debug : logging.info("post_with_auth : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 

        source_previous = account_info["frontier"]
        source_balance = account_info["balance"]
        current_rep = account_info["representative"]

        req_destination_key = {"action": "account_key",
                               "account": destination_account}
        r = self.post_with_auth(req_destination_key)
        destination_link = json.loads(r.text)["key"]
        if self.debug : logging.info("req_destination_key : {}".format(time.time() - t1))
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
            "previous": source_previous
            # ,"difficulty": difficulty,
        }

        r = self.post_with_auth(req_block_create)
        if self.debug : logging.info("req_block_create : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 
        send_block = json.loads(r.text)
        logging.info(send_block["hash"])


        req_process = {
            "action": "process",
            "json_block": "true",
            "subtype": "send",
            "block": send_block["block"],
        }
        r = self.post_with_auth(req_process)
        if self.debug : logging.info("req_process : {}".format(time.time() - t1))
        

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
                "amount": self.truncate(int(amount_per_chunk_raw) / (10 ** 30))
                }



    def create_send_block_pkey(
        self,
        private_key,
        source_account,
        destination_account,
        amount_per_chunk_raw
    ):
        if self.debug : t1 = time.time() 
       
        source_account_data = {    
            "private": private_key,
            "account": source_account,
        }

        req_account_info = {
            "action": "account_info",
            "account": source_account_data["account"],
            "representative": "true",
            "pending": "true",
            "include_confirmed": "true"
        }
        r = self.post_with_auth(req_account_info)
        account_info = json.loads(r.text)
        if self.debug : logging.info("post_with_auth : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 

        source_previous = account_info["frontier"]
        source_balance = account_info["balance"]
        current_rep = account_info["representative"]

        req_destination_key = {"action": "account_key",
                               "account": destination_account}
        r = self.post_with_auth(req_destination_key)
        destination_link = json.loads(r.text)["key"]
        if self.debug : logging.info("req_destination_key : {}".format(time.time() - t1))
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
            "previous": source_previous
            # ,"difficulty": difficulty,
        }

        r = self.post_with_auth(req_block_create)
        if self.debug : logging.info("req_block_create : {}".format(time.time() - t1))
        if self.debug : t1 = time.time() 
        send_block = json.loads(r.text)
        logging.info(send_block["hash"])


        req_process = {
            "action": "process",
            "json_block": "true",
            "subtype": "send",
            "block": send_block["block"],
        }
        r = self.post_with_auth(req_process)
        if self.debug : logging.info("req_process : {}".format(time.time() - t1))
        

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
                "amount": self.truncate(int(amount_per_chunk_raw) / (10 ** 30))
                }

    def create_epoch_block(
        self,
        epoch_link,
        genesis_private_key,
        genesis_account
    ):

        if self.debug : t1 = time.time()
        req_account_info = {
            "action": "account_info",
            "account": genesis_account,
            "representative": "true",
            "pending": "true",
            "include_confirmed": "true"
        }

        r = self.post_with_auth(req_account_info)
        account_info = json.loads(r.text)
        if self.debug : logging.info("post_with_auth : {}".format(time.time() - t1))
        if self.debug : t1 = time.time()

        req_block_create = {
            "action": "block_create",
            "json_block": "true",
            "type": "state",
            "balance": account_info["balance"],
            "key": genesis_private_key,
            "representative": account_info["representative"],
            "link": epoch_link,
            "previous": account_info["frontier"]
        }

        r = self.post_with_auth(req_block_create)
        if self.debug : logging.info("req_block_create : {}".format(time.time() - t1))
        if self.debug : t1 = time.time()
        epoch_block = json.loads(r.text)
        logging.info(epoch_block["hash"])

        req_process = {
            "action": "process",
            "json_block": "true",
            "subtype": "epoch",
            "block": epoch_block["block"],
        }
        r = self.post_with_auth(req_process)
        if self.debug : logging.info("req_process : {}".format(time.time() - t1))
        return {"success" : True,
                "account" : genesis_account,
                "hash": epoch_block["hash"]
                }

