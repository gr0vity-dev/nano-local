 
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
    
    # def post_with_auth(self, content):
        
    #     url = self.RPC_URL 
    #     headers = {"Content-type": "application/json", "Accept": "text/plain"}    
    #     response = requests.post(url, json=content, headers=headers)
    #     # print("request: {} \rrepsonse: {}".format(content["action"], response.text ))
    #     return response
 
    def post_with_auth(self, content, max_retry=2):
        try :
            url = self.RPC_URL 
            headers = {"Content-type": "application/json", "Accept": "text/plain"}    
            r = requests.post(url, json=content, headers=headers)
            # print("request: {} \rrepsonse: {}".format(content["action"], r.text ))
            if "error" in r.text:
                if self.debug : logging.warn("error in post_with_auth |\n request: \n{}\nresponse:\n{}".format(content, r.text)) 
            return json.loads(r.text)
        except : 
            if self.debug : logging.warn("{} Retrys left for post_with_auth : {}".format(max_retry, content["action"]))
            max_retry = max_retry - 1   
            if max_retry >= 0 : 
                time.sleep(0.1)  #100ms
                self.post_with_auth(content,max_retry)

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


    def check_balance(self, account):
       
        multiplier = 10 ** 30
        req_account_balance = {
            "action": "account_balance",
            "account": account,
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
            "previous": previous
            # ,"difficulty": difficulty,
        }
        block = self.post_with_auth(req_block_create)

        next_hash = block["hash"]

        req_process = {
            "action": "process",
            "json_block": "true",
            "subtype": subtype,
            "block": block["block"],
        }

        publish = self.post_with_auth(req_process)
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
            "previous": source_previous
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
        publish = self.post_with_auth(req_process)
        if self.debug : logging.debug("req_process : {}".format(time.time() - t1))
        

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
            "previous": source_previous
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
        publish = self.post_with_auth(req_process)
        if self.debug : logging.debug("req_process : {}".format(time.time() - t1))
        

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
            "previous": account_info["frontier"]
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
        publish = self.post_with_auth(req_process)
        if self.debug : logging.debug("req_process : {}".format(time.time() - t1))
        return {"success" : True,
                "account" : genesis_account,
                "hash": epoch_block["hash"]
                }

