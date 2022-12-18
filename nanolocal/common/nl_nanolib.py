from nanolib import Block, get_account_id, get_account_key_pair, AccountIDPrefix, generate_account_private_key, get_account_public_key
import gmpy2

gmpy2.get_context().precision = 1000  # makes the difference between
# 34000000000000000556857955178552229888 and
# 34000000000000000000000000000000000000


def raw_high_precision_multiply(raw, multiplier) -> int:
    raw_amount = str(
        gmpy2.mpz(gmpy2.mpz(str(raw)) * gmpy2.mpfr(str(multiplier))))
    return int(raw_amount)


def raw_high_precision_percent(raw, percent) -> int:
    raw_amount = gmpy2.mpz(
        gmpy2.mpz(str(raw)) * gmpy2.mpfr(str(percent)) / gmpy2.mpz('100'))
    return int(raw_amount)


class NanoLibTools():

    def get_account_from_public(self, public_key):
        return get_account_id(public_key=public_key,
                              prefix=AccountIDPrefix.NANO)

    def key_expand(self, private_key):
        account_key_pair = get_account_key_pair(private_key)
        account = get_account_id(public_key=account_key_pair.public,
                                 prefix=AccountIDPrefix.NANO)
        response = {
            "private": account_key_pair.private,
            "public": account_key_pair.public,
            "account": account
        }
        return response

    def nanolib_account_data(self, private_key=None, seed=None, index=0):
        if seed is not None:
            private_key = generate_account_private_key(seed, index)
        response = self.key_expand(private_key)

        if seed is not None:
            response["seed"] = seed
            response["index"] = index
        return response

    def get_state_block(self, account, representative, previous, balance,
                        link):

        return Block(block_type="state",
                     account=account,
                     representative=representative,
                     previous=previous,
                     balance=balance,
                     link=link)

    def create_state_block(self,
                           account,
                           representative,
                           previous,
                           balance,
                           link,
                           key,
                           difficulty=None):

        block = self.get_state_block(account, representative, previous,
                                     balance, link)
        block.solve_work(difficulty=difficulty)
        block.sign(key)
        return block
