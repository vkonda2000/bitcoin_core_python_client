import os
import glob
import binascii
import datetime
import shutil
import mmap
import hashlib
import json
#from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

BLOCK_PATH=os.path.join(os.getenv('HOME'), '.bitcoin', 'blocks')

#rpc_connection = AuthServiceProxy("http://%s:%s@127.0.0.1:8332"%('alice', 'passw0rd'))

def getCount(count_bytes):
        txn_size = int(binascii.hexlify(count_bytes[0:1]), 16)

        if txn_size < 0xfd:
                return txn_size
        elif txn_size == 0xfd:
                txn_size = int(binascii.hexlify(count_bytes[1:3][::-1]), 16)
                return txn_size
        elif txn_size == 0xfe:
                txn_size = int(binascii.hexlify(count_bytes[1:5][::-1]), 16)
                return txn_size
        else:
                txn_size = int(binascii.hexlify(count_bytes[1:9][::-1]), 16)
                return txn_size

def getCountBytes(mptr: mmap):
        mptr_read = mptr.read(1)
        count_bytes = mptr_read
        txn_size = int(binascii.hexlify(mptr_read), 16)

        if txn_size < 0xfd:
                return count_bytes
        elif txn_size == 0xfd:
                mptr_read = mptr.read(2)
                count_bytes += mptr_read
                txn_size = int(binascii.hexlify(mptr_read[::-1]), 16)
                return count_bytes
        elif txn_size == 0xfe:
                mptr_read = mptr.read(4)
                count_bytes += mptr_read
                txn_size = int(binascii.hexlify(mptr_read[::-1]), 16)
                return count_bytes
        else:
                mptr_read = mptr.read(8)
                count_bytes += mptr_read
                txn_size = int(binascii.hexlify(mptr_read[::-1]), 16)
                return count_bytes

def getBlockHeaderHash(mptr: mmap, start: int):
        seek = start + 8
        mptr.seek(seek) ## ignore magic number and block size
        block_header = mptr.read(80)
        block_header_hash = hashlib.sha256(hashlib.sha256(block_header).digest()).digest()
        return bytes.decode(binascii.hexlify(block_header_hash[::-1]))

def getTxnHash(txn: bytes):
        txn_hash = hashlib.sha256(hashlib.sha256(txn).digest()).digest()
        return bytes.decode(binascii.hexlify(txn_hash[::-1]))

def getBlockPreHeader(mptr: mmap):
        block_pre_header = {}
        block_pre_header['magic_number'] = bytes.decode(binascii.hexlify(mptr.read(4)[::-1]))
        print('magic_number = %s' % block_pre_header['magic_number'])
        block_pre_header['block_length'] = int(binascii.hexlify(mptr.read(4)[::-1]), 16)
        return block_pre_header

def getBlockHeader(mptr: mmap):
        block_header = {}
        block_header['block_version'] = int(binascii.hexlify(mptr.read(4)[::-1]), 16)
        block_header['prev_block_hash'] = bytes.decode(binascii.hexlify(mptr.read(32)[::-1]))
        block_header['merkle_tree_root'] = bytes.decode(binascii.hexlify(mptr.read(32)[::-1]))
        block_header['timestamp'] = int(binascii.hexlify(mptr.read(4)[::-1]), 16)
        block_header['date_time'] = datetime.datetime.fromtimestamp(block_header['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        block_header['bits'] = bytes.decode(binascii.hexlify(mptr.read(4)[::-1]))
        block_header['nounce'] = bytes.decode(binascii.hexlify(mptr.read(4)[::-1]))
        return block_header

def getTransactionCount(mptr: mmap):
        count_bytes = getCountBytes(mptr)
        txn_count = getCount(count_bytes)
        return txn_count

def getCoinbaseTransaction(mptr: mmap):
        txn = {}
        txn_version = mptr.read(4)
        txn['version'] = int(binascii.hexlify(txn_version[::-1]), 16)
        count_bytes = getCountBytes(mptr)
        input_count = getCount(count_bytes)
        if input_count == 0:
                # post segwit
                txn['is_segwit'] = bool(int(binascii.hexlify(mptr.read(1)), 16))
                count_bytes = getCountBytes(mptr)
                txn['input_count'] = getCount(count_bytes)
        else:
                txn['input_count'] = input_count # this will be 1
        txn['input'] = []
        for index in range(txn['input_count']):
                txn_input = {}
                txn_input['prev_txn_hash'] = bytes.decode(binascii.hexlify(mptr.read(32)[::-1]))
                txn_input['prev_txn_out_index'] = int(binascii.hexlify(mptr.read(4)[::-1]), 16)
                count_bytes = getCountBytes(mptr)
                txn_input['coinbase_data_size'] = getCount(count_bytes)
                fptr1 = mptr.tell()
                count_bytes = getCountBytes(mptr)
                txn_input['coinbase_data_bytes_in_height'] = getCount(count_bytes)
                txn_input['coinbase_data_block_height'] = int(binascii.hexlify(mptr.read(txn_input['coinbase_data_bytes_in_height'])[::-1]), 16)
                fptr2 = mptr.tell()
                arbitrary_data_size = txn_input['coinbase_data_size'] - (fptr2 - fptr1)
                txn_input['coinbase_arbitrary_data'] = bytes.decode(binascii.hexlify(mptr.read(arbitrary_data_size)[::-1]))
                txn_input['sequence'] = int(binascii.hexlify(mptr.read(4)[::-1]), 16)
                txn['input'].append(txn_input)
        count_bytes = getCountBytes(mptr)
        txn['out_count'] = getCount(count_bytes)
        txn['out'] = []
        for index in range(txn['out_count']):
                txn_out = {}
                txn_out['satoshis'] = int(binascii.hexlify(mptr.read(8)[::-1]), 16)
                count_bytes = getCountBytes(mptr)
                txn_out['scriptpubkey_size'] = getCount(count_bytes)
                txn_out['scriptpubkey'] = bytes.decode(binascii.hexlify(mptr.read(txn_out['scriptpubkey_size'])))
                txn['out'].append(txn_out)
        if 'is_segwit' in txn and txn['is_segwit'] == True:
                for index in range(txn['input_count']):
                        count_bytes = getCountBytes(mptr)
                        txn['input'][index]['witness_count'] = getCount(count_bytes)
                        txn['input'][index]['witness'] = []
                        for inner_index in range(txn['input'][index]['witness_count']):
                                txn_witness = {}
                                count_bytes = getCountBytes(mptr)
                                txn_witness['size'] = getCount(count_bytes)
                                txn_witness['witness'] = bytes.decode(binascii.hexlify(mptr.read(txn_witness['size'])))
                                txn['input'][index]['witness'].append(txn_witness)
        txn['locktime'] = int(binascii.hexlify(mptr.read(4)[::-1]), 16)
        return txn

def getTransaction(mptr: mmap):
        txn = {}
        mptr_read = mptr.read(4)
        raw_txn = mptr_read
        txn['version'] = int(binascii.hexlify(mptr_read[::-1]), 16)
        mptr_read = getCountBytes(mptr)
        input_count = getCount(mptr_read)
        if input_count == 0:
                # post segwit
                txn['is_segwit'] = bool(int(binascii.hexlify(mptr.read(1)), 16))
                mptr_read = getCountBytes(mptr)
                txn['input_count'] = getCount(mptr_read)
        else:
                txn['input_count'] = input_count
        raw_txn += mptr_read

        txn['input'] = []
        for index in range(txn['input_count']):
                txn_input = {}
                mptr_read = mptr.read(32)
                raw_txn += mptr_read
                txn_input['prev_txn_hash'] = bytes.decode(binascii.hexlify(mptr_read[::-1]))
                mptr_read = mptr.read(4)
                raw_txn += mptr_read
                txn_input['prev_txn_out_index'] = int(binascii.hexlify(mptr_read[::-1]), 16)
                mptr_read = getCountBytes(mptr)
                raw_txn += mptr_read
                txn_input['scriptsig_size'] = getCount(mptr_read)
                mptr_read = mptr.read(txn_input['scriptsig_size'])
                raw_txn += mptr_read
                txn_input['scriptsig'] = bytes.decode(binascii.hexlify(mptr_read))
                mptr_read = mptr.read(4)
                raw_txn += mptr_read
                txn_input['sequence'] = int(binascii.hexlify(mptr_read[::-1]), 16)
                txn['input'].append(txn_input)
        mptr_read = getCountBytes(mptr)
        raw_txn += mptr_read
        txn['out_count'] = getCount(mptr_read)
        txn['out'] = []
        for index in range(txn['out_count']):
                txn_out = {}
                mptr_read = mptr.read(8)
                raw_txn += mptr_read
                txn_out['_satoshis'] = int(binascii.hexlify(mptr_read[::-1]), 16)
                mptr_read = getCountBytes(mptr)
                raw_txn += mptr_read
                txn_out['scriptpubkey_size'] = getCount(mptr_read)
                mptr_read = mptr.read(txn_out['scriptpubkey_size'])
                raw_txn += mptr_read
                txn_out['scriptpubkey'] = bytes.decode(binascii.hexlify(mptr_read))
                txn['out'].append(txn_out)
        if 'is_segwit' in txn and txn['is_segwit'] == True:
                for index in range(txn['input_count']):
                        mptr_read = getCountBytes(mptr)
                        txn['input'][index]['witness_count'] = getCount(mptr_read)
                        txn['input'][index]['witness'] = []
                        for inner_index in range(txn['input'][index]['witness_count']):
                                txn_witness = {}
                                mptr_read = getCountBytes(mptr)
                                txn_witness['size'] = getCount(mptr_read)
                                txn_witness['witness'] = bytes.decode(binascii.hexlify(mptr.read(txn_witness['size'])))
                                txn['input'][index]['witness'].append(txn_witness)
        mptr_read = mptr.read(4)
        raw_txn += mptr_read
        txn['locktime'] = int(binascii.hexlify(mptr_read[::-1]), 16)
        txn['txn_hash'] = getTxnHash(raw_txn)

#        check_raw_txn = rpc_connection.getrawtransaction(txn['txn_hash'])
#        print('checked raw txn = %s' % check_raw_txn)
#        print('txn_hash = %s' % txn['txn_hash'])
        return txn

def getBlock(mptr: mmap, start: int):
        block = {}
        block['block_header_hash'] = getBlockHeaderHash(mptr, start)
        print('block_header_hash = %s' % block['block_header_hash'])

        mptr.seek(start) ## ignore magic number and block size
        block['block_pre_header'] = getBlockPreHeader(mptr)
        if block['block_pre_header']['magic_number'] == '00000000':
                raise EOFError
        block['block_header'] = getBlockHeader(mptr)
        block['txn_count'] = getTransactionCount(mptr)

        txn_list = []
        txn_list.append(getCoinbaseTransaction(mptr))
        for index in range(1, block['txn_count']):
                txn = getTransaction(mptr)
                txn_list.append(txn)
        block['txn_list'] = txn_list
        return block
        

def blockFileParser():
        with open('blk01231.dat', 'rb') as latest_block_file:
                # load file to memory
                mptr = mmap.mmap(latest_block_file.fileno(), 0, prot=mmap.PROT_READ) #File is open read-only

                block_file = []
                try:
                        while True:
                                start = mptr.tell()
                                block_file.append(getBlock(mptr, start))
                except EOFError:
                        pass
#                print(json.dumps(block_file, indent=4))

if __name__ == '__main__':
        blockFileParser()
