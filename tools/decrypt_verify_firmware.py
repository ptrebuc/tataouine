#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Decrypt a firmware and check its signature using
# the DFU token

import sys, os, array
import binascii
from subprocess import Popen, PIPE, STDOUT
from threading import Timer

# Import our local utils
from utils import *

def PrintUsage():
    executable = os.path.basename(__file__)
    print("Error when executing %s\n\tUsage:\t%s keys_path firmware_to_decrypt <only_info>" % (executable, executable))
    sys.exit(-1)

if __name__ == '__main__':
    # Register Ctrl+C handler
    signal.signal(signal.SIGINT, handler)
    # Get the arguments
    if len(sys.argv) < 3:
        PrintUsage()
    if len(sys.argv) > 4:
        PrintUsage()
    keys_path = sys.argv[1]
    firmware_to_decrypt_file = sys.argv[2]
    if not os.path.isfile(firmware_to_decrypt_file):
        print("Error: provided firmware file %s does not exist!" % (firmware_to_decrypt_file))
        sys.exit(-1)
    # Read the buffer from the file
    firmware_to_decrypt = read_in_file(firmware_to_decrypt_file)
    # Check if we only want to print the information
    ONLY_INFO = False
    if len(sys.argv) == 4:
        ONLY_INFO = True
    # Parse the header
    # Header = magic on 4 bytes || partition type on 4 bytes || version on 4 bytes || len of data after the header on 4 bytes || siglen on 4 bytes
    header = firmware_to_decrypt[:4*5]
    magic =  header[:4+(0*4)]
    partition_type =  header[4+(0*4):4+(1*4)]
    version = header[4+(1*4):4+(2*4)]
    data_len = header[4+(2*4):4+(3*4)]
    siglen = header[4+(3*4):4+(4*4)]

    def inverse_mapping(f):
        return f.__class__(map(reversed, f.items()))

    print("Magic         : 0x" + local_hexlify(magic))
    print("Partition type: '"  + inverse_mapping(partitions_types)[stringtoint(partition_type)]+"'")
    print("Version       : 0x" + local_hexlify(version))
    print("Data length   : 0x" + local_hexlify(data_len))
    print("Sig length    : 0x" + local_hexlify(siglen))

    # Now extract the signature and parse the content
    data_len = stringtoint(data_len)
    siglen = stringtoint(siglen)
    encapsulated_content = firmware_to_decrypt[4*5:-siglen]
    signature = firmware_to_decrypt[-siglen:]
    if len(encapsulated_content) != data_len:
        print("Error: encapsulated firmware length %d does not match the one in the header %d!" % (len(encapsulated_content), data_len))
        sys.exit(-1)
    # Now extract the signature information from the public key
    SCRIPT_PATH = os.path.abspath(os.path.dirname(sys.argv[0])) + "/"
    firmware_sig_pub_key_data = read_in_file(keys_path+"/SIG/token_sig_firmware_public_key.bin") 
    ret_alg, ret_curve, prime, a, b, gx, gy, order, cofactor = get_curve_from_key(firmware_sig_pub_key_data)
    # Sanity check: the algorithm should be ECDSA 
    if ret_alg != "ECDSA":
        print("Error: asked signature algorithm is not supported (not ECDSA)")
        sys.exit(-1)
    # Now check the signature
    (to_verify, _, _) = sha256(firmware_to_decrypt[:-siglen])

    # Verify ECDSA_VERIF(SHA-256(to_verify))
    c = Curve(a, b, prime, order, cofactor, gx, gy, cofactor * order, ret_alg, None)
    ecdsa_pubkey = PubKey(c, Point(c, stringtoint(firmware_sig_pub_key_data[3:3+32]), stringtoint(firmware_sig_pub_key_data[3+32:3+64])))
    ecdsa_keypair = KeyPair(ecdsa_pubkey, None)
    if ecdsa_verify(sha256, ecdsa_keypair, to_verify, signature) == False:
        print("Error: bad signature for %s" % (firmware_to_decrypt_file))
        sys.exit(-1) 
    else: 
        print("  [Signature for %s is OK!]  " % (firmware_to_decrypt_file))

    # The encapsulated content is [ IV + MAC(IV) + MAX_CHUNK_SIZE(4 bytes) + ENC(firmware) ]
    iv = encapsulated_content[:16]
    iv_hmac = encapsulated_content[16:16+32]
    firmware_chunk_size = stringtoint(encapsulated_content[16+32:16+32+4])
    encrypted_content = encapsulated_content[16+32+4:]


    print("IV            : 0x" + local_hexlify(iv))
    print("IV_HMAC       : 0x" + local_hexlify(iv_hmac))
    print("Chunk size    : %d" % (firmware_chunk_size))
    print("Signature     : 0x" + local_hexlify(signature))
    
    # If we only wanted information, we can quit here
    if ONLY_INFO == True:
        sys.exit(0)

    # Ask the DFU token to begin a session
    card = connect_to_token("DFU")
    scp_dfu = token_full_unlock(card, "dfu", keys_path+"/DFU/encrypted_platform_dfu_keys.bin") # pet_pin="1234", user_pin="1234", force_pet_name_accept = True)
    resp, sw1, sw2 = scp_dfu.token_dfu_begin_decrypt_session(iv+iv_hmac)
    if (sw1 != 0x90) or (sw2 != 0x00):
        print("Error:  DFU token APDU error ...")
        sys.exit(-1)

    # Now decrypt the firmware
    # Split the firmware in chunks
    n_chunks = int(len(encrypted_content) // firmware_chunk_size)
    if len(encrypted_content) % firmware_chunk_size != 0:
        n_chunks += 1

    decrypted_firmware = ""
    for i in range(0, n_chunks):
        print("\tXXXXXXXXXXXXXXXXX DECRYPTING CHUNK %04x XXXXXXXXXXXXXXXXX" % (i))
        chunk_key, sw1, sw2 = scp_dfu.token_dfu_derive_key()
        if (sw1 != 0x90) or (sw2 != 0x00):
            print("Error:  DFU token APDU error ...")
            sys.exit(-1)

        # Initialize IV to 0
        chunk_iv = inttostring(0)
        if i != n_chunks-1:
            chunk = encrypted_content[(i*firmware_chunk_size) : ((i+1)*firmware_chunk_size)]
        else:
            chunk = encrypted_content[(i*firmware_chunk_size):]
        aes = local_AES.new(chunk_key, AES.MODE_CTR, iv=chunk_iv)
        decrypted_firmware += aes.decrypt(chunk)
        print("\tXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")

    # Save the file
    save_in_file(decrypted_firmware, firmware_to_decrypt_file+".decrypted")