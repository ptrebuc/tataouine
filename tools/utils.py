# Various utils and helpers common to all our scripts

import sys, os, array, time
import binascii
from subprocess import Popen, PIPE, STDOUT
from threading import Timer
import math
from smartcard.CardType import AnyCardType
from smartcard.CardRequest import CardRequest
from smartcard.util import toHexString, toBytes
import datetime
from Crypto.Cipher import AES
import hashlib, hmac

from copy import deepcopy

from builtins import input


# Import our ECC python primitives
sys.path.append(os.path.abspath(os.path.dirname(sys.argv[0])) + "/" + "../externals/libecc/scripts/")
from expand_libecc import *

### Ctrl-C handler
def handler(signal, frame):
    print("\nSIGINT caught: exiting ...")
    exit(0)

# Helper to communicate with the smartcard
def _connect_to_token():
    card = None
    try:
        card = connect_to_smartcard()
    except:
        card = None
    return card

def connect_to_token(token_type=None):
    card = _connect_to_token()
    while card == None:
        err_msg = "Error: Token undetected."
        if token_type != None:
            err_msg += " Please insert your '"+token_type+ "' token ..."
        sys.stderr.write('\r'+err_msg)
        sys.stderr.flush()
        time.sleep(1)
        card = _connect_to_token()
    return card    

# Helper to execute an external command
def sys_cmd(cmd):
    p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
    kill = lambda process: process.kill()
    timer = Timer(100, kill, [p])
    timer.start()
    out = p.stdout.read()
    if timer.is_alive():
        timer.cancel()
    p.wait()
    if p.returncode != 0:
        print("Error when executing command: "+cmd)
        print("Exec Trace:\n"+out)
        sys.exit(-1)
    return out

# Remove a file
def sys_rm_file(file_path):
    if os.path.isfile(file_path):
        os.remove(file_path)
    return

# Read a string from a file
def read_in_file(infilename):
    infile = open(infilename, 'rb')
    data = infile.read()
    infile.close()
    if is_python_2() == False:
        data = data.decode('latin-1')
    return data

# Save a string in a file
def save_in_file(data, outfilename):
    if is_python_2() == False:
        data = data.encode('latin-1')
    outfile = open(outfilename, 'wb')
    outfile.write(data)
    outfile.close()

# Helper to ask the user for something
def get_user_input(prompt):
    # Handle the Python 2/3 issue
    return input(prompt)

# Helper to generate a random string with proper entropy
def gen_rand_string(size):
    if is_python_2() == True:
        return os.urandom(size)
    else:
        return os.urandom(size).decode('latin-1')

# Helper to check the enctropy of a string
def check_pin_security_policy(instr):
    return True

# Send an APDU using the smartcard library
def send_apdu(cardservice, apdu):
    apdu = local_unhexlify(apdu)
    a = datetime.datetime.now()
    to_transmit = [ord(x) for x in apdu] 
    response, sw1, sw2 = cardservice.connection.transmit(to_transmit)
    b = datetime.datetime.now()
    delta = b - a
    print(">          "+local_hexlify(apdu))
    print("<          SW1=%02x, SW2=%02x, %s" % (sw1, sw2, local_hexlify(''.join([chr(r) for r in response]))))
    print("           |= APDU took %d ms" % (int(delta.total_seconds() * 1000)))
    return "".join(map(chr, response)), sw1, sw2

# Connect to a smartcard
def connect_to_smartcard():
    cardtype = AnyCardType()
    cardrequest = CardRequest(timeout=.2, cardType=cardtype)
    cardservice = cardrequest.waitforcard()
    cardservice.connection.connect()
    atr = cardservice.connection.getATR()
    print("ATR: "+toHexString(atr))
    return cardservice

# Get the curve and signature algorithm from a structured key
# [RB] FIXME: the algorithm and curve 'enum' values are hardcoded
# and supposed fixed in libecc. This is a bit tedious and error prone:
# we should ideally extract this information from the libecc headers.
def get_curve_from_key(structured_key_buffer):
    algo  = ord(structured_key_buffer[1])
    curve = ord(structured_key_buffer[2])
    prime = None
    a = None
    b = None
    gx = None
    gy = None
    order = None
    cofactor = None
    if algo == 1:
        # We only support ECDSA
        ret_alg = "ECDSA"
    else:
        ret_alg = None
    if curve == 1:
        ret_curve = "FRP256V1"
        prime = 0xF1FD178C0B3AD58F10126DE8CE42435B3961ADBCABC8CA6DE8FCF353D86E9C03
        a = 0xF1FD178C0B3AD58F10126DE8CE42435B3961ADBCABC8CA6DE8FCF353D86E9C00
        b = 0xEE353FCA5428A9300D4ABA754A44C00FDFEC0C9AE4B1A1803075ED967B7BB73F
        gx = 0xB6B3D4C356C139EB31183D4749D423958C27D2DCAF98B70164C97A2DD98F5CFF
        gy = 0x6142E0F7C8B204911F9271F0F3ECEF8C2701C307E8E4C9E183115A1554062CFB
        order = 0xF1FD178C0B3AD58F10126DE8CE42435B53DC67E140D2BF941FFDD459C6D655E1
        cofactor = 1
    elif curve == 8:
        ret_curve = "BRAINPOOLP256R1"
        prime = 76884956397045344220809746629001649093037950200943055203735601445031516197751
        a = 0x7D5A0975FC2C3057EEF67530417AFFE7FB8055C126DC5C6CE94A4B44F330B5D9
        b = 0x26DC5C6CE94A4B44F330B5D9BBD77CBF958416295CF7E1CE6BCCDC18FF8C07B6
        gx = 0x8BD2AEB9CB7E57CB2C4B482FFC81B7AFB9DE27E1E3BD23C23A4453BD9ACE3262
        gy = 0x547EF835C3DAC4FD97F8461A14611DC9C27745132DED8E545C1D54C72F046997
        order = 0xA9FB57DBA1EEA9BC3E660A909D838D718C397AA3B561A6F7901E0E82974856A7
        cofactor = 1
    elif curve == 4:
        ret_curve = "SECP256R1"
        prime = 115792089210356248762697446949407573530086143415290314195533631308867097853951
        a = 115792089210356248762697446949407573530086143415290314195533631308867097853948
        b = 41058363725152142129326129780047268409114441015993725554835256314039467401291
        gx = 48439561293906451759052585252797914202762949526041747995844080717082404635286
        gy = 36134250956749795798585127919587881956611106672985015071877198253568414405109
        order = 115792089210356248762697446949407573529996955224135760342422259061068512044369
        cofactor = 1
    else:
        ret_curve = None
    return (ret_alg, ret_curve, prime, a, b, gx, gy, order, cofactor)
        
def get_sig_len(structured_key_buffer):
    # We only support 64 bytes (r, s) as the signature length for now ...
    # [RB] FIXME: use a more flexible way to compute this from the key
    return 64

# Infer from the size of the local key bag if we use a SIG token or not
# [RB] FIXME: this is a bit hardcoded, we should use a more flexible way of dealing
# with this.
def is_sig_token_used(encrypted_platform_bin_file):
    data = read_in_file(encrypted_platform_bin_file)
    if(len(data) > 400):
        return False
    else:
        return True

# Encrypt the local pet key using PBKDF2
def enc_local_pet_key(pet_pin, salt, pbkdf2_iterations, master_symmetric_local_pet_key):
    ## Master symmetric 'pet key' to be used for local credential encryption on the platform
    # Use PBKDF2-SHA-512 to derive our local encryption keys
    dk = local_pbkdf2_hmac('sha512', pet_pin, salt, pbkdf2_iterations)
    # The encrypted key is the encryption with AES-ECB 128 of the generated keys.
    # We have 64 bytes to encrypt and the PBKDF2 results in 64 bytes, hence
    # we can encrypt each chunk with AES-ECB and an associated key
    cipher1 = local_AES.new(dk[:16],   AES.MODE_ECB)
    cipher2 = local_AES.new(dk[16:32], AES.MODE_ECB)
    cipher3 = local_AES.new(dk[32:48], AES.MODE_ECB)
    cipher4 = local_AES.new(dk[48:],   AES.MODE_ECB)
    enc_master_symmetric_local_pet_key = cipher1.encrypt(master_symmetric_local_pet_key[:16]) + cipher2.encrypt(master_symmetric_local_pet_key[16:32]) + cipher3.encrypt(master_symmetric_local_pet_key[32:48]) + cipher4.encrypt(master_symmetric_local_pet_key[48:])
    return enc_master_symmetric_local_pet_key

# Decrypt the local pet key using PBKDF2 (and using optionnaly the external token)
def dec_local_pet_key(pet_pin, salt, pbkdf2_iterations, enc_master_symmetric_local_pet_key, card, data_type):
    ## Master symmetric 'pet key' to be used for local credential encryption on the platform
    # Use PBKDF2-SHA-512 to derive our local encryption keys
    dk = local_pbkdf2_hmac('sha512', pet_pin, salt, pbkdf2_iterations)
    master_symmetric_local_pet_key = None
    # We locally dercypt the key
    if (card == None) or (enc_master_symmetric_local_pet_key != None):
        # The decrypted key is the decryption with AES-ECB 128 of the generated keys.
        # We have 64 bytes to encrypt and the PBKDF2 results in 64 bytes, hence
        # we can encrypt each chunk with AES-ECB and an associated key
        cipher1 = local_AES.new(dk[:16],   AES.MODE_ECB)
        cipher2 = local_AES.new(dk[16:32], AES.MODE_ECB)
        cipher3 = local_AES.new(dk[32:48], AES.MODE_ECB)
        cipher4 = local_AES.new(dk[48:],   AES.MODE_ECB)
        master_symmetric_local_pet_key = cipher1.decrypt(enc_master_symmetric_local_pet_key[:16]) + cipher2.decrypt(enc_master_symmetric_local_pet_key[16:32]) + cipher3.decrypt(enc_master_symmetric_local_pet_key[32:48]) + cipher4.decrypt(enc_master_symmetric_local_pet_key[48:])
    else:
        if (card != None):
            # Ask for the token to derive and get the local key
            resp, sw1, sw2 = token_ins(data_type, "TOKEN_INS_SELECT_APPLET").send(card)
            if (sw1 != 0x90) or (sw2 != 0x00):
                print("Token Error: bad response from the token when selecting applet")
                # This is an error
                sys.exit(-1)
            master_symmetric_local_pet_key, sw1, sw2 = token_ins(data_type, "TOKEN_INS_DERIVE_LOCAL_PET_KEY", data=dk).send(card)
            if (sw1 != 0x90) or (sw2 != 0x00):
                print("Token Error: bad response from the token when asking to derive local pet key")
                # This is an error
                sys.exit(-1)
    return master_symmetric_local_pet_key

# Decrypt our local private data
# [RB] FIXME: private and public keys lengths are hardcoded here ... we should be more flexible!
# Same for PBKDF2 iterations.
# These lengths should be infered from other files
def decrypt_platform_data(encrypted_platform_bin_file, pin, data_type, card):
    data = read_in_file(encrypted_platform_bin_file)
    index = 0
    decrypt_platform_data.iv = data[index:index+16]
    index += 16
    salt = data[index:index+16]
    index += 16
    hmac_tag = data[index:index+32]
    index += 32
    token_pub_key_data = data[index:index+99]
    index += 99
    platform_priv_key_data = data[index:index+35]
    index += 35
    platform_pub_key_data = data[index:index+99]
    index += 99
    firmware_sig_pub_key_data = None
    if (data_type == "dfu") or (data_type == "sig"):
        firmware_sig_pub_key_data = data[index:index+99]
        index += 99
    # Do we have other keys to decrypt (if we do not use a sig token)
    firmware_sig_priv_key_data = None
    firmware_sig_sym_key_data = None
    encrypted_local_pet_key_data = None
    if (len(data) > index):
        firmware_sig_priv_key_data = data[index:index+35]
        index += 35
        firmware_sig_sym_key_data = data[index:index+32]
        index += 32
        encrypted_local_pet_key_data = data[index:index+64]
        index += 64
    # Derive the decryption key
    pbkdf2_iterations = 4096
    dk = dec_local_pet_key(pin, salt, pbkdf2_iterations, encrypted_local_pet_key_data, card, data_type)
    # Now compute and check the HMAC, and decrypt local data
    hmac_key = dk[32:]
    # Check the mac tag
    hm = local_hmac.new(hmac_key, digestmod=hashlib.sha256)
    hm.update(decrypt_platform_data.iv + salt + token_pub_key_data + platform_priv_key_data + platform_pub_key_data)
    if firmware_sig_pub_key_data != None:
        hm.update(firmware_sig_pub_key_data)
    if firmware_sig_priv_key_data != None:
        hm.update(firmware_sig_priv_key_data)
    if firmware_sig_sym_key_data != None:
        hm.update(firmware_sig_sym_key_data)
    hmac_tag_ref = hm.digest()
    if hmac_tag != hmac_tag_ref:
        print("Error when decrypting local data with the PET pin: hmac not OK!")
        sys.exit(-1)
    # Decrypt
    enc_key = dk[:16]
    cipher = local_AES.new(enc_key, AES.MODE_CTR, iv=decrypt_platform_data.iv)
    dec_token_pub_key_data = cipher.decrypt(token_pub_key_data)
    dec_platform_priv_key_data = cipher.decrypt(platform_priv_key_data)
    dec_platform_pub_key_data = cipher.decrypt(platform_pub_key_data)
    dec_firmware_sig_pub_key_data = None
    if firmware_sig_pub_key_data != None:
        dec_firmware_sig_pub_key_data = cipher.decrypt(firmware_sig_pub_key_data)
    dec_firmware_sig_priv_key_data = None
    if firmware_sig_priv_key_data != None:
        dec_firmware_sig_priv_key_data = cipher.decrypt(firmware_sig_priv_key_data)
    dec_firmware_sig_sym_key_data = None
    if firmware_sig_sym_key_data != None:
        dec_firmware_sig_sym_key_data = cipher.decrypt(firmware_sig_sym_key_data)

    return dec_token_pub_key_data, dec_platform_priv_key_data, dec_platform_pub_key_data, dec_firmware_sig_pub_key_data, dec_firmware_sig_priv_key_data, dec_firmware_sig_sym_key_data, salt, pbkdf2_iterations

# This class handles forging APDUs
# NOTE: we only support *short APDUs*, which is sufficient
# for handling our custom secure channel.
class APDU:
    cla  = None
    ins  = None
    p1   = None
    p2   = None
    data = None
    le   = None
    apdu_buf = None
    def send(self, cardservice):
        if (len(self.data) > 255) or (self.le > 256):
            print("APDU Error: data or Le too large")
            sys.exit(-1)
        if self.le == 256:
            self.le = 0
        # Forge the APDU buffer provided our data
        # CLA INS P1 P2
        self.apdu_buf = chr(self.cla)+chr(self.ins)+chr(self.p1)+chr(self.p2)
        # Do we have data to send?
        if self.data != None:
            self.apdu_buf += chr(len(self.data))
            self.apdu_buf += self.data
            if self.le != None:
                self.apdu_buf += chr(self.le)
        else:
            if self.le != None:
                self.apdu_buf += chr(self.le)
            else:
                self.apdu_buf += '\x00'
        # Send the APDU through the communication channel
        resp, sw1, sw2 = send_apdu(cardservice, local_hexlify(self.apdu_buf))
        return (resp, sw1, sw2)
    def __init__(self, cla, ins, p1, p2, data, le):
        self.cla  = cla
        self.ins  = ins
        self.p1   = p1
        self.p2   = p2
        self.data = data
        self.le   = le
        return

# Python 2/3 hexlify helper
def local_hexlify(str_in):
    if is_python_2() == True:
        return binascii.hexlify(str_in)
    else:
        return (binascii.hexlify(str_in.encode('latin-1'))).decode('latin-1')
 

# Python 2/3 unhexlify helper
def local_unhexlify(str_in):
    if is_python_2() == True:
        return binascii.unhexlify(str_in)
    else:
        return (binascii.unhexlify(str_in.encode('latin-1'))).decode('latin-1')
        
# The common instructions
def token_common_instructions(applet_id): 
    return {
                             'TOKEN_INS_SELECT_APPLET'       : APDU(0x00, 0xA4, 0x04, 0x00, local_unhexlify(applet_id), 0x00),
                             'TOKEN_INS_SECURE_CHANNEL_INIT' : APDU(0x00, 0x00, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_UNLOCK_PET_PIN'      : APDU(0x00, 0x01, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_UNLOCK_USER_PIN'     : APDU(0x00, 0x02, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_SET_USER_PIN'        : APDU(0x00, 0x03, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_SET_PET_PIN'         : APDU(0x00, 0x04, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_SET_PET_NAME'        : APDU(0x00, 0x05, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_LOCK'                : APDU(0x00, 0x06, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_GET_PET_NAME'        : APDU(0x00, 0x07, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_GET_RANDOM'          : APDU(0x00, 0x08, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_DERIVE_LOCAL_PET_KEY': APDU(0x00, 0x09, 0x00, 0x00, None, 0x00),
                             # FIXME: to be removed, for debug purposes only!
                             'TOKEN_INS_ECHO_TEST'           : APDU(0x00, 0x0a, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_SECURE_CHANNEL_ECHO' : APDU(0x00, 0x0b, 0x00, 0x00, None, 0x00),
           }

# The AUTH token instructions
auth_token_instructions =  {
                             'TOKEN_INS_GET_KEY'             : APDU(0x00, 0x10, 0x00, 0x00, None, 0x00),                            
                           }

# The DFU token instructions
dfu_token_instructions =   { 
                             'TOKEN_INS_BEGIN_DECRYPT_SESSION' : APDU(0x00, 0x20, 0x00, 0x00, None, 0x00),                            
                             'TOKEN_INS_DERIVE_KEY'            : APDU(0x00, 0x21, 0x00, 0x00, None, 0x00),                            
                           }

# The SIG token instructions
sig_token_instructions =   {
                             'TOKEN_INS_BEGIN_SIGN_SESSION' : APDU(0x00, 0x30, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_DERIVE_KEY'         : APDU(0x00, 0x31, 0x00, 0x00, None, 0x00),                            
                             'TOKEN_INS_SIGN_FIRMWARE'      : APDU(0x00, 0x32, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_VERIFY_FIRMWARE'    : APDU(0x00, 0x33, 0x00, 0x00, None, 0x00),
                             'TOKEN_INS_GET_SIG_TYPE'       : APDU(0x00, 0x34, 0x00, 0x00, None, 0x00),
                           }

def token_ins(token_type, instruction, data=None, lc=None):
    token_instructions = None
    if token_type == "auth":
        token_instructions = token_common_instructions("45757477747536417070").copy()
        token_instructions.update(auth_token_instructions)
    elif token_type == "dfu":
        token_instructions = token_common_instructions("45757477747536417071").copy()
        token_instructions.update(dfu_token_instructions)
    elif token_type == "sig":
        token_instructions = token_common_instructions("45757477747536417072").copy()
        token_instructions.update(sig_token_instructions)
    else:
        print("Error: unknown token type "+token_type)
        sys.exit(-1)
    apdu = deepcopy(token_instructions[instruction])
    if (apdu.data == None) and (data != None):
        apdu.data = data
    if lc != None:
        apdu.lc = lc
    return apdu

# Python 2/3 abstraction layer for hash function
def local_sha256(arg_in):
    (a, b, c) = sha256(arg_in)
    return (a, b, c)

# Python 2/3 abstraction layer for HMAC
class local_hmac:
    hm = None
    def __init__(self, key, digestmod=hashlib.sha256):
        if is_python_2() == False: 
            key = key.encode('latin-1')
        self.hm = hmac.new(key, digestmod=digestmod)
        return
    def update(self, in_str):
        if is_python_2() == False: 
            in_str = in_str.encode('latin-1')
        if self.hm == None:
            return
        else:
            self.hm.update(in_str)
            return
    def digest(self):
        if self.hm == None:
            return None
        else:
            d = self.hm.digest()
            if is_python_2() == False:
                return d.decode('latin-1')
            else:
                return d
    @staticmethod
    def new(key, digestmod=hashlib.sha256):
        return local_hmac(key, digestmod=digestmod)

# Python 2/3 abstraction layer for AES
class local_AES:
    aes = None
    iv = None
    def  __init__(self, key, mode, iv=None, counter=None):
        if is_python_2() == False: 
            key = key.encode('latin-1')
        if iv != None:
            self.iv = iv
            if is_python_2() == False: 
                iv = iv.encode('latin-1')
            if mode == AES.MODE_CTR:
                if counter == None:
                    self.aes = AES.new(key, mode, counter=self.counter_inc)
                else:
                    self.aes = AES.new(key, mode, counter=counter)
            else:
                self.aes = AES.new(key, mode, iv)
            return
        else:
            if mode == AES.MODE_CTR:
                if counter == None:
                    self.iv = expand(inttostring(0), 128, "LEFT")
                    self.aes = AES.new(key, mode, counter=self.counter_inc)
                else:
                    self.aes = AES.new(key, mode, counter=counter)
            else:
                self.aes = AES.new(key, mode)
            return
    def counter_inc(self):
        curr_iv = expand(inttostring((stringtoint(self.iv))), 128, "LEFT")
        self.iv = expand(inttostring((stringtoint(self.iv)+1)), 128, "LEFT")
        if is_python_2() == False:
            curr_iv = curr_iv.encode('latin-1')
        return curr_iv
    def encrypt(self, data):
        if is_python_2() == False:
            data = data.encode('latin-1')
        ret = self.aes.encrypt(data)
        if is_python_2() == False:
            ret = ret.decode('latin-1')
        return ret
    def decrypt(self, data):
        if is_python_2() == False:
            data = data.encode('latin-1')
        ret = self.aes.decrypt(data)
        if is_python_2() == False:
            ret = ret.decode('latin-1')
        return ret
    @staticmethod
    def new(key, mode, iv=None, counter=None):
        return local_AES(key, mode, iv=iv, counter=counter)

# Python 2/3 abstraction layer for PBKDF2
def local_pbkdf2_hmac(hash_func, pin, salt, pbkdf2_iterations):
    if is_python_2() == False:
        pin = pin.encode('latin-1')
        salt = salt.encode('latin-1')
    dk = hashlib.pbkdf2_hmac(hash_func, pin, salt, pbkdf2_iterations)
    if is_python_2() == False:
        return dk.decode('latin-1')
    else:
        return dk

# PIN padding
def pin_padding(pin):
    if len(pin) > 15:
        print("PIN Error: bad length (> 15) %d" % (len(pin)))
        sys.exit(-1)
    padded_pin = pin+((15-len(pin))*"\x00")+chr(len(pin))
    return padded_pin

# Secure channel class
class SCP:
    initialized = False
    cardservice = None
    IV = None
    first_IV = None
    AES_Key = None
    HMAC_Key = None
    dec_firmware_sig_pub_key_data = None
    token_type = None
    pbkdf2_salt = None
    pbkdf2_iterations = None
    # Update the sessions keys (on some triggers such as provide/modify a PIN)
    def session_keys_update(self, pin):
        (mask, _, _) = local_sha256(pin+self.IV)
        self.AES_Key  = expand(inttostring(stringtoint(self.AES_Key)  ^ stringtoint(mask[:16])), 128, "LEFT")
        self.HMAC_Key = expand(inttostring(stringtoint(self.HMAC_Key) ^ stringtoint(mask)), 256, "LEFT")
        return
    # Encrypt/decrypt data with a key derived from the PIN
    def pin_decrypt_data(self, pin, data, iv):
         (h, _, _) = local_sha256(pin)
         (key, _, _) = local_sha256(self.first_IV+h)
         key = key[:16]
         aes = local_AES.new(key, AES.MODE_CBC, iv=iv)
         # [RB] FIXME: should be decrypt here ... To be moved
         dec_data = aes.encrypt(data)
         return dec_data
    def pin_encrypt_data(self, pin, data, iv):
         (h, _, _) = local_sha256(pin)
         (key, _, _) = local_sha256(self.first_IV+h)
         key = key[:16]
         aes = local_AES.new(key, AES.MODE_CBC, iv=iv)
         # [RB] FIXME: should be encrypt here ... To be moved
         enc_data = aes.decrypt(data)
         return enc_data
        
    # Send a message through the secure channel
    def send(self, orig_apdu, pin=None, update_session_keys=False, pin_decrypt=False):
        apdu = deepcopy(orig_apdu)
        print("=============================================")
        def counter_inc():
            curr_iv = expand(inttostring((stringtoint(self.IV))), 128, "LEFT")
            self.IV = expand(inttostring((stringtoint(self.IV)+1)), 128, "LEFT")
            if is_python_2() == True:
                return curr_iv
            else:
                return curr_iv.encode('latin-1')
        if self.initialized == False:
            # Secure channel not initialized, quit
            print("SCP Error: secure channel not initialized ...")
            return None, None, None
        # Initialize the hmac
        hm = local_hmac.new(self.HMAC_Key, digestmod=hashlib.sha256)
        hm.update(self.IV+chr(apdu.cla)+chr(apdu.ins)+chr(apdu.p1)+chr(apdu.p2))
        data_to_send = ""
        # Empty string means no data in our case!
        if apdu.data == "":
            apdu.data = None
        if apdu.data != None:
            print(">>>(encrypted)  "+"\033[1;42m["+local_hexlify(apdu.data)+"]\033[1;m")
            # Check length
            if len(apdu.data) > 255:
                 print("SCP Error: data size %d too big" % (len(apdu.data)))
                 return None, None, None
            # Encrypt the data
            aes = local_AES.new(self.AES_Key, AES.MODE_CTR, counter=counter_inc)
            enc_data = aes.encrypt(apdu.data)
            hm.update(chr(len(apdu.data))+enc_data)
            data_to_send += enc_data
            if len(apdu.data) % 16 == 0:
                counter_inc()
        else:
            print(">>>(encrypted)  "+"\033[1;42m"+"[]"+"\033[1;m")
            counter_inc()
        apdu.le = 0
        hm.update(chr(apdu.le))
        hm_tag = hm.digest()
        # Put the encrypted data plus the hmac tag
        apdu.data = data_to_send + hm_tag
        # Send the APDU on the line
        resp, sw1, sw2 = apdu.send(self.cardservice)
        # Save the old IV before reception for data encryption inside the channel
        old_IV = self.IV
        # Check the response HMAC
        if resp == None:
            print("SCP Error: bad response length (< 32) ...")
            return None, None, None
        if len(resp) < 32:
            print("SCP Error: bad response length %d (< 32) ..." % (len(resp)))
            return None, None, None
        if len(resp) > 256:
            print("SCP Error: response length %d too big" % (len(resp)))
            return None, None, None
        enc_resp_data = resp[:-32]
        resp_hmac_tag = resp[-32:]
        hm = local_hmac.new(self.HMAC_Key, digestmod=hashlib.sha256)
        hm.update(self.IV+chr(sw1)+chr(sw2))
        if len(enc_resp_data) > 0:
            hm.update(chr(len(enc_resp_data)))
            hm.update(enc_resp_data)
        if resp_hmac_tag != hm.digest():
            print("SCP Error: bad response HMAC")
            return None, None, None
        # Now decrypt the data
        if len(enc_resp_data) > 0:
            aes = local_AES.new(self.AES_Key, AES.MODE_CTR, counter=counter_inc)
            dec_resp_data = aes.decrypt(enc_resp_data)
            print("<<<(decrypted)  SW1=%02x, SW2=%02x, \033[1;43m[%s]\033[1;m" % (sw1, sw2, local_hexlify(dec_resp_data)))
            if len(enc_resp_data) % 16 == 0:
                counter_inc()
        else:
            counter_inc()
            dec_resp_data = None
            print("<<<(decrypted)  SW1=%02x, SW2=%02x, \033[1;43m[]\033[1;m" % (sw1, sw2))
        if (update_session_keys == True) and (sw1 == 0x90) and (sw2 == 0x00):
            # We need the PIN for this command
            if pin == None:
                print("SCP Error: asking for update_session_keys without providing the PIN!")
                return None, None, None
            self.session_keys_update(pin_padding(pin))
        # Do we have to decrypt data inside the channel?
        if (pin_decrypt == True) and (sw1 == 0x90) and (sw2 == 0x00):
            if pin == None:
                print("SCP Error: asking for pin_decrypt without providing the PIN!")
                return None, None, None
            dec_resp_data = self.pin_decrypt_data(pin, dec_resp_data, old_IV)
        return dec_resp_data, sw1, sw2

    # Initialize the secure channel
    def __init__(self, card, encrypted_platform_bin_file, pin, data_type):
        self.cardservice = card
        self.token_type = data_type
        # Decrypt local platform keys. We also keep the current salt and PBKDF2 iterations for later usage
        dec_token_pub_key_data, dec_platform_priv_key_data, dec_platform_pub_key_data, self.dec_firmware_sig_pub_key_data, _, _, self.pbkdf2_salt, self.pbkdf2_iterations = decrypt_platform_data(encrypted_platform_bin_file, pin, data_type, card) 
	# Get the algorithm and the curve
        ret_alg, ret_curve, prime, a, b, gx, gy, order, cofactor = get_curve_from_key(dec_platform_pub_key_data)
        if (ret_alg == None) or (ret_curve == None):
            print("SCP Error: unkown curve or algorithm in the structured keys ...")
            sys.exit(-1)
        # Instantiate it
        c = Curve(a, b, prime, order, cofactor, gx, gy, cofactor * order, ret_alg, None)
        # Generate a key pair for our ECDH
        ecdh_keypair = genKeyPair(c)
        # Sign the public part with our ECDSA private key
        ecdsa_pubkey = PubKey(c, Point(c, stringtoint(dec_platform_pub_key_data[3:3+32]), stringtoint(dec_platform_pub_key_data[3+32:3+64])))
        ecdsa_privkey = PrivKey(c, stringtoint(dec_platform_priv_key_data[3:]))
        ecdsa_keypair = KeyPair(ecdsa_pubkey, ecdsa_privkey)
        to_send = expand(inttostring(ecdh_keypair.pubkey.Y.x), 256, "LEFT")
        to_send += expand(inttostring(ecdh_keypair.pubkey.Y.y), 256, "LEFT")
        to_send += "\x00"*31+"\x01"
        (sig, k) = ecdsa_sign(sha256, ecdsa_keypair, to_send)
        to_send += sig
        # Mount the secure channel with the token
        # Note: the applet should have been already selected by our decrypt_platform_data procedure
        # since we have already exchanged data with the card
        apdu = token_ins("sig", "TOKEN_INS_SECURE_CHANNEL_INIT", data=to_send)
        resp, sw1, sw2 = apdu.send(self.cardservice)
        if (sw1 != 0x90) or (sw2 != 0x00):
            # This is an error
            print("SCP Error: bad response from the token")
            sys.exit(-1)
        if len(resp) != ((3*32) + 64):
            # This is not the response length we expect ...
            print("SCP Error: bad response from the token")
            sys.exit(-1)
        # Extract the ECDSA signature
        ecdsa_token_pubkey = PubKey(c, Point(c, stringtoint(dec_token_pub_key_data[3:3+32]), stringtoint(dec_token_pub_key_data[3+32:3+64])))
        ecdsa_token_sig = resp[3*32:]
        check_sig = ecdsa_verify(sha256, KeyPair(ecdsa_token_pubkey, None), resp[:3*32], ecdsa_token_sig)
        if check_sig == False:
            # Bad signature
            print("SCP Error: bad ECDSA signature in response from the token")
            return
        # Extract ECDH point and compute the scalar multiplication
        ecdh_shared_point = (ecdh_keypair.privkey.x) * Point(c, stringtoint(resp[:32]), stringtoint(resp[32:64]))
        ecdh_shared_secret = expand(inttostring(ecdh_shared_point.x), 256, "LEFT")
        # Derive our keys
        # AES Key = SHA-256("AES_SESSION_KEY" | shared_secret) (first 128 bits)
        (self.AES_Key, _, _) = local_sha256("AES_SESSION_KEY"+ecdh_shared_secret)
        self.AES_Key = self.AES_Key[:16]
        # HMAC Key = SHA-256("HMAC_SESSION_KEY" | shared_secret) (256 bits)
        (self.HMAC_Key, _, _) = local_sha256("HMAC_SESSION_KEY"+ecdh_shared_secret)
        # IV = SHA-256("SESSION_IV" | shared_secret) (first 128 bits)
        (self.IV, _, _) = local_sha256("SESSION_IV"+ecdh_shared_secret)
        self.IV = self.IV[:16]
        self.first_IV = self.IV
        # The secure channel is now initialized
        self.initialized = True
        return
    # ====== Common token helpers
    # Helper to unlock PET PIN
    def token_unlock_pet_pin(self, pet_pin):
        return self.send(token_ins(self.token_type, "TOKEN_INS_UNLOCK_PET_PIN", data=pin_padding(pet_pin)), pin=pet_pin, update_session_keys=True)
    # Helper to unlock user PIN
    def token_unlock_user_pin(self, user_pin = None):
        if user_pin == None:
            user_pin = get_user_input("Please provide "+self.token_type.upper()+" USER pin:\n")
        return self.send(token_ins(self.token_type, "TOKEN_INS_UNLOCK_USER_PIN", data=pin_padding(user_pin)), pin=user_pin, update_session_keys=True)
    # Helper to get the PET name
    def token_get_pet_name(self):
        return self.send(token_ins(self.token_type, "TOKEN_INS_GET_PET_NAME"))
    # Helper to lock the token
    def token_lock(self):
        return self.send(token_ins(self.token_type, "TOKEN_INS_LOCK"))
    # Helper to set the user PIN
    def token_set_user_pin(self, new_user_pin = None):
        if new_user_pin == None:
            new_user_pin =  get_user_input("Please provide the *new* "+self.token_type.upper()+" user PIN:\n")
        return self.send(token_ins(self.token_type, "TOKEN_INS_SET_USER_PIN", data=pin_padding(new_user_pin)), pin=new_user_pin, update_session_keys=True)
    # Helper to set the PET PIN
    def token_set_pet_pin(self, new_pet_pin = None):
        if new_pet_pin == None:
            new_pet_pin =  get_user_input("Please provide the *new* "+self.token_type.upper()+" PET PIN:\n")
        # We compute and send the PBKDF2 of the new PET PIN
        dk = local_pbkdf2_hmac('sha512', new_pet_pin, self.pbkdf2_salt, self.pbkdf2_iterations)
        return self.send(token_ins(self.token_type, "TOKEN_INS_SET_PET_PIN", data=pin_padding(new_pet_pin)+dk), pin=new_pet_pin, update_session_keys=True)
    # Helper to set the PET name
    def token_set_pet_name(self, new_pet_name = None):
        if new_pet_name == None:
            new_pet_name =  get_user_input("Please provide the *new* "+self.token_type.upper()+" PET name:\n")
        return self.send(token_ins(self.token_type, "TOKEN_INS_SET_PET_NAME", data=new_pet_name))   
    def token_get_random(self, size):
        if size > 255:
            # This is an error
            print("Token Error: bad length %d > 255 for TOKEN_INS_GET_RANDOM" % (size))
            return None, None, None
        return self.send(token_ins(self.token_type, "TOKEN_INS_GET_RANDOM", data=chr(size)))
    def token_echo_test(self, data):
        return self.send(token_ins(self.token_type, "TOKEN_INS_ECHO_TEST", data=data))
    def token_secure_channel_echo(self, data):
        return self.send(token_ins(self.token_type, "TOKEN_INS_SECURE_CHANNEL_ECHO", data=data))
    # ====== AUTH specific helpers
    def token_auth_get_key(self, pin):
        if self.token_type != "auth":
            print("AUTH Token Error: asked for TOKEN_INS_GET_KEY for non AUTH token ("+self.token_type.upper()+")")
            # This is an error
            return None, None, None
        return self.send(token_ins(self.token_type, "TOKEN_INS_GET_KEY"), pin=pin, pin_decrypt=True) 
    # ====== DFU specific helpers
    def token_dfu_begin_decrypt_session(self, ivivhmac):
        if self.token_type != "dfu":
            print("DFU Token Error: asked for TOKEN_INS_BEGIN_DECRYPT_SESSION for non DFU token ("+self.token_type.upper()+")")
            # This is an error
            return None, None, None
        return self.send(token_ins(self.token_type, "TOKEN_INS_BEGIN_DECRYPT_SESSION", data=ivivhmac)) 
    def token_dfu_derive_key(self):
        if self.token_type != "dfu":
            print("DFU Token Error: asked for TOKEN_INS_DERIVE_KEY for non DFU token ("+self.token_type.upper()+")")
            # This is an error
            return None, None, None
        return self.send(token_ins(self.token_type, "TOKEN_INS_DERIVE_KEY")) 
    # ====== SIG specific helpers
    def token_sig_begin_sign_session(self):
        if self.token_type != "sig":
            print("SIG Token Error: asked for TOKEN_INS_BEGIN_SIGN_SESSION for non SIG token ("+self.token_type.upper()+")")
            # This is an error
            return None, None, None
        return self.send(token_ins(self.token_type, "TOKEN_INS_BEGIN_SIGN_SESSION"))
    def token_sig_derive_key(self):
        if self.token_type != "sig":
            print("SIG Token Error: asked for TOKEN_INS_DERIVE_KEY for non SIG token ("+self.token_type.upper()+")")
            # This is an error
            return None, None, None
        return self.send(token_ins(self.token_type, "TOKEN_INS_DERIVE_KEY"))
    def token_sig_sign_firmware(self, to_sign):
        if self.token_type != "sig":
            print("SIG Token Error: asked for TOKEN_INS_SIGN_FIRMWARE for non SIG token ("+self.token_type.upper()+")")
            # This is an error
            return None, None, None
        return self.send(token_ins(self.token_type, "TOKEN_INS_SIGN_FIRMWARE", data=to_sign))
    def token_sig_verify_firmware(self, to_verify):
        if self.token_type != "sig":
            print("SIG Token Error: asked for TOKEN_INS_VERIFY_FIRMWARE for non SIG token ("+self.token_type.upper()+")")
            # This is an error
            return None, None, None
        return self.send(token_ins(self.token_type, "TOKEN_INS_VERIFY_FIRMWARE", data=to_verify))
    def token_sig_get_sig_type(self):
        if self.token_type != "sig":
            print("SIG Token Error: asked for TOKEN_INS_GET_SIG_TYPE for non SIG token ("+self.token_type.upper()+")")
            # This is an error
            return None, None, None
        return self.send(token_ins(self.token_type, "TOKEN_INS_GET_SIG_TYPE"))

# Helper to fully unlock a token, which is the first step to
# access advanced features of a token
def token_full_unlock(card, token_type, local_keys_path, pet_pin = None, user_pin = None, force_pet_name_accept = False):
    # ======================
    # Get the PET PIN for local ECDH keys decryption
    if pet_pin == None:
        pet_pin = get_user_input("Please provide "+token_type.upper()+" PET pin:\n")
    # Establish the secure channel with the token
    scp = SCP(card, local_keys_path, pet_pin, token_type)
    resp, sw1, sw2 = scp.token_unlock_pet_pin(pet_pin)
    resp, sw1, sw2 = scp.token_get_pet_name()
    if force_pet_name_accept == False:
        answer = None
        while answer != "y" and answer != "n":
            answer = get_user_input("\033[1;44m PET NAME CHECK!  \033[1;m\n\nThe PET name for the "+token_type.upper()+" token is '"+resp+"', is it correct? Enter y to confirm, n to cancel [y/n].")
        if answer != "y":
            sys.exit(-1)
    else:
        print("\033[1;44m PET NAME CHECK!  \033[1;m\n\nThe PET name for the "+token_type.upper()+" token is '"+resp+"' ...")
    resp, sw1, sw2 = scp.token_unlock_user_pin(user_pin)
    return scp

# The partition types
partitions_types = {
    'FW1'      : 0,
    'FW2'      : 1,
    'DFU1'     : 2,
    'DFU2'     : 3,
    'SHR'      : 4,
}