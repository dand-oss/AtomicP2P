import traceback

from LibreCisco.utils.manager import ThreadManager
from LibreCisco.utils import printText
from LibreCisco.peer.monitor.command import (
    HelpCmd, PauseCmd, PeriodCmd, ListCmd, ResetCmd, VerboseCmd, ManualCmd
)
from LibreCisco.peer.monitor.communication import CheckHandler


class Monitor(ThreadManager):

    def __init__(self, peer, loopDelay=10, verbose=False,
                 max_no_response_count=5):
        self.peer = peer
        super(Monitor, self).__init__(loopDelay=loopDelay,
                                      output_field=peer.output_field,
                                      auto_register=True)
        self.pkt_handlers = {}
        self.verbose = False
        self.pause = False
        self.max_no_response_count = max_no_response_count

    def run(self):
        while not self.stopped.wait(self.loopDelay):
            if self.pause is False:
                no_response_list = []
                handler = self.select_handler(CheckHandler.pkt_type)
                for (host, peer_info) in self.peer.peer_pool.items():
                    pkt = handler.on_send(target=host)
                    self.peer.pend_packet(sock=peer_info.conn, pkt=pkt)
                    if peer_info.status.no_response_count >= \
                            self.max_no_response_count:
                        no_response_list.append(peer_info)
                self.removeMonitorlist(no_response_list)

    def select_handler(self, pkt_type):
        if pkt_type in self.pkt_handlers:
            return self.pkt_handlers[pkt_type]
        return None

    def onProcess(self, msg_arr):
        msg_key = msg_arr[0].lower()
        msg_arr = msg_arr[1:]
        if msg_key in self.commands:
            return self.commands[msg_key].onProcess(msg_arr)
        return ''

    def on_recv_pkt(self, addr, pkt, conn):
        if not pkt.is_reject():
            peer_info = self.peer.get_peer_info_by_host(host=pkt.src)
            if peer_info is not None:
                peer_info.status.update()

    def removeMonitorlist(self, missing):
        for each in missing:
            try:
                self.peer.pend_socket_to_rm(each.conn)
                printText('{} has been remove from peer list.'.format(each))
            except Exception:
                printText(traceback.format_exc())

    def _register_handler(self):
        installing_handlers = [
            CheckHandler(self)
        ]
        for each in installing_handlers:
            self.pkt_handlers[type(each).pkt_type] = each

    def _register_command(self):
        self.commands = {
            'help': HelpCmd(self),
            'pause': PauseCmd(self),
            'period': PeriodCmd(self),
            'list': ListCmd(self),
            'reset': ResetCmd(self),
            'verbose': VerboseCmd(self),
            'manual': ManualCmd(self)
        }
