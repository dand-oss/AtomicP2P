import os
import socket
import base64
from threading import Thread
from Crypto.Cipher import AES

from .manager import ThreadManager
from .logging import getLogger


class LocalMonitor(ThreadManager):
    def __init__(
        self, service, password, logger: "logging.Logger" = getLogger(__name__)
    ):
        super().__init__(loopDelay=0.5, logger=logger)
        self.service = service
        self.password = password
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("localhost", 17031))

    def registerHandler(self):
        pass

    def registerCommand(self):
        pass

    def new_cipher(self, key: str):
        return AES.new(key.encode(), AES.MODE_CBC, "0000000000000000".encode())

    def encrypt(self, raw_data):
        if len(raw_data) % 16 != 0:
            raw_data += " " * (16 - len(raw_data) % 16)
        return self.new_cipher(key=self.password).encrypt(raw_data.encode())

    def decrypt(self, enc_data):
        return self.new_cipher(key=self.password).decrypt(enc_data)

    def run(self):
        while not self.stopped.wait(self.loopDelay):
            try:
                (data, addr) = self.sock.recvfrom(1024)
                thread = Thread(target=self.command_recv, args=(data, addr))
                thread.start()
            except OSError as ose:
                if ose.errno == os.errno.EINVAL:
                    break

    def stop(self):
        super().stop()
        self.sock.close()

    def command_recv(self, enc_data, addr):
        if enc_data is not None and enc_data != "":
            raw_data = self.decrypt(enc_data=enc_data)
            result = self.service._on_command(raw_data.decode())[1]
            enc_result = self.encrypt(raw_data=result)
            res_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            res_sock.sendto(enc_result, ("localhost", 17032))
            res_sock.close()
