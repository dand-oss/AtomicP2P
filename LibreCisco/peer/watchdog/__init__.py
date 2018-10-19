import traceback
from LibreCisco.utils.manager import ThreadManager
from LibreCisco.utils import printText
from LibreCisco.peer.watchdog.check import CheckHandler


class Watchdog(ThreadManager):

    def __init__(self, peer, loopDelay=5):
        self.peer = peer
        super(Watchdog, self).__init__(loopDelay=loopDelay,
                                       output_field=peer.output_field,
                                       auto_register=True)
        self.connectlist = peer.connectlist

    def run(self):
        while not self.stopped.wait(self.loopDelay):
            for each in self.connectlist:
                addr = each.host[0]
                port = each.host[1]
                mes = {'msg': 123}
                try:
                    self.peer.sendMessage((addr, port), 'watchdog_check',
                                          **mes)
                except Exception as e:
                    printText(traceback.format_exc())

    def registerHandler(self):
        self.handler = {
            'watchdog_check': CheckHandler(self.peer)
        }

    def registerCommand(self):
        self.commands = {}

    def onProcess(self, msg_arr, **kwargs):
        return ''
