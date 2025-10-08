import threading
import time
import random

import hashlib
import psutil

from .base62 import encode


# THIS IS AN IMPLEMENTATION OF THE SNOWFLAK ALGORITHM by X's( TWITTER) team


class Snowflake:

    """

    1 unused bit
        41 bits timestamp (ms since epoch)
        10 bits node ID
        12 bits sequence
    """

    NODE_ID_BITS = 10
    SEQUENCE_BITS = 12
    MAX_NODE_ID = (1 << NODE_ID_BITS) - 1
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1

    DEFAULT_EPOCH =1420070400000

    def __init__(self , node_id: int | None = None , epoch: int | None = None):

        self.epoch = epoch or self.DEFAULT_EPOCH

        self.node_id = node_id if node_id is not None else self._create_node_id()
        if self.node_id < 0 or self.node_id > self.MAX_NODE_ID:
            raise ValueError(f"Node ID must be between 0 and {self.MAX_NODE_ID}")

        self.last_timestamp = -1
        self.sequence = 0
        self.lock = threading.Lock()

    def _create_node_id(self):

        try:
            #   Hash mac address to get a node id
            macs = []
            for iface , addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == psutil.AF_LINK and addr.address:
                        macs.append(addr.address.replace(":" , "").replace("-" , ""))
            if macs:
                mac_str = "".join(macs)
                node_hash = int(hashlib.sha1(mac_str.encode()).hexdigest() , 16)
                node_id = node_hash % self.MAX_NODE_ID
            else:
                #will default to random interger
                node_id = random.SystemRandom().randint(0, self.MAX_NODE_ID)
        except Exception:
            node_id = random.SystemRandom().randint(0, self.MAX_NODE_ID)
        return node_id


    def _timestamp(self):
        return int(time.time() * 1000) -self.epoch

    def _wait_next_ms(self , current_timestamp):
        timestamp = self._timestamp()
        while timestamp <= current_timestamp:
            timestamp = self._timestamp()
        return timestamp

    def next_id(self):
        with self.lock:
            current_timestamp = self._timestamp()

            if current_timestamp < self.last_timestamp:
                raise Exception("Clock moved backwards. Refusing to generate id")

            if current_timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                if self.sequence == 0:
                    current_timestamp = self._wait_next_ms(current_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = current_timestamp

            _id = ((current_timestamp << (self.NODE_ID_BITS + self.SEQUENCE_BITS)) |
                  (self.node_id << self.SEQUENCE_BITS) |
                  self.sequence)
            return _id

    def next_id_base62(self):
        _id = self.next_id()
        return encode(_id)


